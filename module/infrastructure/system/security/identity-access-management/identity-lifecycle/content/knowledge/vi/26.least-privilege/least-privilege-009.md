# Phát hiện quyền thừa trong Least Privilege: từ dấu hiệu đến bằng chứng và thu hồi an toàn

## 1. Quyền thừa là gì và vì sao cần chủ động phát hiện?

**Least Privilege** (*nguyên tắc đặc quyền tối thiểu*) yêu cầu một chủ thể chỉ được nắm **những quyền cần thiết, trong phạm vi phù hợp và trong khoảng thời gian cần thiết** để thực hiện nhiệm vụ đã được phê duyệt. **Quyền thừa** (*excessive privileges*, *overprivileged access*) là quyền vượt quá nhu cầu hoặc chính sách còn hiệu lực, bao gồm quyền thao tác quá rộng, quyền trên tài nguyên không liên quan, quyền được giữ quá lâu hoặc những kết hợp quyền tạo rủi ro không chấp nhận được.

Ví dụ, một nhân viên chỉ cần **đọc báo cáo** nhưng vẫn giữ quyền **xóa báo cáo**, hoặc một kỹ sư đã chuyển dự án nhưng còn quyền quản trị kho mã nguồn dự án cũ. Cả hai có thể đăng nhập hợp lệ; vấn đề nằm ở **authorization**, không nhất thiết là lỗi xác thực.

Trong quản lý **Identity and Access Management (IAM)** theo vòng đời **Joiner–Mover–Leaver (JML)**, quyền thừa thường tích lũy qua nhiều lần tạo tài khoản, cấp nhóm, chuyển vai trò, phê duyệt ngoại lệ và thay đổi nhân sự. Một sự kiện HR được xử lý thành công tại IdP chưa chứng minh tất cả hệ thống đích đã thu hồi các quyền không còn cần thiết.

**Phát hiện quyền thừa** là quá trình:

1. **Kiểm kê** danh tính, tài khoản, quan hệ, grant và quyền ở các hệ thống.
2. **Tính quyền kỳ vọng** từ công việc, chính sách, phê duyệt và thời điểm hiệu lực.
3. **Xác định quyền đã cấp và quyền thực sự có hiệu lực** ở từng tài nguyên.
4. **Phân tích tín hiệu** như sử dụng, mức nhạy cảm, quyền rộng, vi phạm phân tách nhiệm vụ và chủ sở hữu.
5. **Phân loại bằng chứng và độ tin cậy** trước khi kết luận quyền nào thừa.
6. **Thu hồi hoặc thu hẹp có kiểm soát**, kiểm tra cả tác động nghiệp vụ và quyền còn tồn dư.

**Không được đánh đồng “ít sử dụng” với “chắc chắn thừa”.** Một quyền khẩn cấp ít dùng, một công việc cuối quý hoặc tài khoản dự phòng có thể cần thiết. Ngược lại, quyền quản trị thường xuyên được sử dụng vẫn có thể **quá rộng** nếu nhiệm vụ thực tế chỉ cần một tập thao tác nhỏ.

## 2. Các chiều của quyền thừa

Quyền thừa không chỉ có nghĩa số lượng role nhiều. Nó có nhiều chiều:

| Chiều đánh giá | Ví dụ | Câu hỏi phát hiện |
| --- | --- | --- |
| **Hành động (action)** | Có DELETE nhưng công việc chỉ cần READ | Chủ thể cần thực hiện những thao tác nào? |
| **Tài nguyên (resource)** | Có quyền mọi repository thay vì một dự án | Những tài nguyên nào thực sự thuộc nhiệm vụ? |
| **Phạm vi tổ chức (tenant/org)** | Quyền admin ở nhiều tenant | Quyền có vượt organization được duyệt không? |
| **Mức đặc quyền** | Permanent cloud administrator | Có thể dùng quyền thấp hơn hoặc JIT/PAM không? |
| **Thời gian** | Quyền bàn giao không có hạn | Sau mốc nào quyền phải mất hiệu lực? |
| **Quan hệ lao động** | Mover giữ group công việc cũ | Quan hệ/phân công cấp quyền còn hợp lệ không? |
| **Con đường cấp quyền** | Role trực tiếp ngoài nhóm IdP | Có đường quyền bị bỏ sót khi chỉ xem group không? |
| **Kết hợp quyền** | Vừa tạo vừa phê duyệt khoản thanh toán | Có vi phạm Separation of Duties không? |
| **Danh tính máy** | Bot chỉ đọc nhưng có scope quản trị toàn API | Workload cần quyền nào để hoàn thành job? |
| **Khả năng cấp tiếp quyền** | Service principal có quyền sửa IAM policy | Quyền hiện có có thể leo thang thành quyền cao hơn? |

Một quyền có thể không thừa theo **hành động** nhưng thừa theo **tài nguyên**; hoặc đúng theo cả hai nhưng thừa theo **thời hạn**. Do đó, so sánh quyền bằng tên role đơn giản thường không đủ.

## 3. Bốn lớp dữ liệu: expected, assigned, effective và used access

Đây là phân biệt quan trọng nhất của bài.

| Lớp | Nội dung | Cách dùng |
| --- | --- | --- |
| **Expected access** | Những quyền **nên có** theo công việc, policy, phê duyệt và thời điểm hiện tại | Đường chuẩn để tìm quyền thiếu/thừa |
| **Assigned access** | Những role, group, ACL, grant, policy và membership **đã cấu hình** | Bằng chứng cấp quyền ở hệ thống quản trị |
| **Effective access** | Những hành động mà hệ thống **thực sự có thể cho phép** sau khi kết hợp mọi policy, điều kiện và đường quyền | Cơ sở quan trọng để xác định rủi ro thật |
| **Used/observed access** | Những hành động được thấy trong log/telemetry ở khoảng thời gian quan sát | Tín hiệu để thu hẹp quyền và xác định tần suất |

Ví dụ, Lan được duyệt **READ repository Atlas**. Dữ liệu thực tế:

~~~text
Expected:
    READ repository Atlas

Assigned:
    Group project-atlas-developers
    Direct role RepositoryAdmin tại Atlas

Effective:
    READ, WRITE, DELETE, MANAGE_ACCESS tại Atlas

Observed 90 ngày:
    READ 210 lần
    WRITE 0 lần
    DELETE 0 lần
    MANAGE_ACCESS 0 lần
~~~

**Phần quyền vượt expected là ứng viên quyền thừa mạnh**, đặc biệt nếu direct role admin không có phê duyệt. Log chỉ giúp tăng mức tự tin rằng quyền chưa cần thiết trong khoảng quan sát, không tự chứng minh Lan sẽ không cần WRITE trong nhiệm vụ sắp tới.

### Ma trận sai lệch

| Expected | Effective | Ý nghĩa |
| --- | --- | --- |
| ALLOW | ALLOW | Đúng theo phép kiểm tra đang xét |
| ALLOW | DENY | Thiếu quyền hoặc lỗi cấp phát/chính sách |
| DENY | ALLOW | **Quyền thừa hoặc lỗi authorization** cần xử lý |
| DENY | DENY | Đúng theo phép kiểm tra đang xét |
| UNKNOWN | ALLOW/DENY | Chưa đủ dữ liệu về nhu cầu; không thể kết luận |
| ALLOW/DENY | UNKNOWN | Không quan sát/không tính được quyền thực tế; cần đối soát |

Một lần kiểm tra không bao phủ toàn bộ hành động và tài nguyên. Khi nói “đã xác minh”, phải nêu **phạm vi và thời điểm** của bằng chứng.

## 4. Phân loại quyền thừa để tìm đúng nguyên nhân

| Nhóm phát hiện | Dấu hiệu | Mức chắc chắn khi chưa điều tra |
| --- | --- | --- |
| **Quyền ngoài role hiện hành** | Role cũ không còn trong expected access | Cao nếu nguồn nhiệm vụ và mapping đã xác minh |
| **Quyền sau Leaver** | Account/token còn ALLOW sau mốc cắt | Rất đáng ưu tiên khi có bằng chứng quyền thật |
| **Quyền vượt phê duyệt** | Assigned/effective lớn hơn grant đã duyệt | Cao nếu dữ liệu approval đầy đủ |
| **Đặc quyền rộng/wildcard** | Admin, * hoặc quyền trên toàn organization | Tín hiệu rủi ro, cần xem toàn bộ policy/deny/boundary |
| **Quyền không sử dụng** | Không thấy hoạt động trong cửa sổ đo | Chỉ là ứng viên, cần kiểm tra log và chu kỳ nghiệp vụ |
| **Quyền không có owner** | User/service account, grant hoặc nhóm không có người chịu trách nhiệm | Lỗi quản trị và tăng rủi ro |
| **Quyền có thời hạn nhưng chưa thu hồi** | approvalUntil đã qua | Cao nếu giờ hiệu lực và ngoại lệ rõ |
| **Quyền trực tiếp ngoài chuẩn** | ACL/role cục bộ không xuất phát từ IGA | Cần xác minh có phê duyệt ngoài luồng không |
| **Kết hợp độc hại (toxic combination)** | Vừa tạo vừa phê duyệt giao dịch | Có thể vi phạm SoD dù cả hai quyền đều đang dùng |
| **Quyền có khả năng tự nâng cấp** | Có thể sửa role, IAM policy, secret hoặc tạo credential khác | Cần mô phỏng chuỗi quyền, không chỉ tên role |

Các trường hợp có thể đồng thời tồn tại. Một service account có quyền wildcard và không có owner vừa là **overprivileged candidate** vừa là **orphaned identity risk**.

## 5. Kiểm kê danh tính và quyền: không chỉ đọc nhóm ở IdP

Để phát hiện đầy đủ, cần biết **ai hoặc cái gì có quyền qua đường nào**:

- **Con người:** employee, contractor, intern, partner, guest và người có nhiều hợp đồng.
- **Tài khoản:** IdP account, SaaS local account, database user, repository account, cloud identity.
- **Nhóm và role:** nhóm IdP, SCIM Group, role ứng dụng, role cloud, role Kubernetes, nested group.
- **ACL và chia sẻ trực tiếp:** quyền thư mục, tài liệu, bucket, repository, workspace và object.
- **OAuth grant:** scope, audience, consent, refresh token, Personal Access Token (PAT).
- **Credential đặc biệt:** API key, SSH key, certificate, session, break-glass account.
- **Workload:** service account, managed identity, CI/CD job, service principal, robot, integration.
- **Nguồn quyền:** role cấp tự động theo policy, phê duyệt riêng, quyền trực tiếp, ngoại lệ khẩn cấp, kế thừa.

**Không giả định IdP hoặc SCIM là nơi nắm mọi quyền.** Một tài khoản SaaS có thể giữ local role hoặc token riêng ngay cả khi người dùng đã rời nhóm IdP. Một đối tượng còn sở hữu file hoặc quyền chia sẻ trực tiếp có thể có effective access khác với kết quả đọc group.

Mỗi phát hiện cần mang đủ **namespace/tenant và target system**. Hai đối tượng cùng tên username ở hai hệ thống chưa chắc thuộc cùng một người.

## 6. Liên kết person–employment–identity–account đúng cách

Phát hiện quyền thừa trở nên nguy hiểm nếu gán quyền của tài khoản A cho người B. Trong vòng đời IAM nên phân biệt:

| Thực thể | Ví dụ | Vai trò |
| --- | --- | --- |
| **Person** | person-482 | Con người được tổ chức nhận diện |
| **Employment/relation** | emp-482-org-a | Hợp đồng/quan hệ có ngày hiệu lực và chủ bảo trợ |
| **IAM identity** | iam-482 | Danh tính số quản trị |
| **IdP subject** | issuer + sub | Định danh do IdP phát hành |
| **Application account** | SaaS user id u-482 | Bản ghi tại một hệ thống cụ thể |
| **Workload identity** | svc-report-exporter | Danh tính máy với owner và mục đích riêng |

Chỉ dùng **email, họ tên hoặc số điện thoại** để tự nối tài khoản có thể sai do thay đổi, tái sử dụng alias hoặc trùng tên. Khi ghép OIDC subject, cần xét **issuer + sub**. Khi dùng SCIM, **server id** ở SP khác với **externalId** do provisioning client cung cấp; cần lưu mapping cùng tenant/nguồn.

Một người có thể có **hai employment hợp lệ**. Khi quan hệ org-a kết thúc, IAM phải rút quyền của org-a nhưng vẫn có thể giữ quyền hợp lệ từ org-b. **Không gom mọi role của một person thành một danh sách quyền không có ngữ cảnh tổ chức.**

Nếu account mapping mơ hồ, phát hiện phải mang trạng thái **UNVERIFIED_IDENTITY_LINK** và chuyển điều tra, không tự động revoke hoặc cấp quyền.

## 7. Nguồn dữ liệu để phát hiện quyền thừa

| Nguồn | Cung cấp dữ liệu gì? | Điều không nên suy diễn |
| --- | --- | --- |
| **HRIS / sponsor system** | Quan hệ làm việc, loại lao động, start/end date, department, manager | Không biết mọi quyền hiện hành của ứng dụng |
| **IAM/IGA** | Quyền kỳ vọng, phê duyệt, policy, chiến dịch rà soát | Phê duyệt không chứng minh target đã thực thi |
| **IdP/SSO** | Identity, group, account state, authenticator, session metadata | Group IdP không bao phủ mọi local ACL/token |
| **SCIM/API provisioning** | User/Group và trạng thái đồng bộ tại SP | SCIM success không tự chứng minh token đã revoke |
| **PDP/PIP/PEP** | Policy version, attribute, quyết định ALLOW/DENY, enforcement | Log decision không luôn phản ánh dữ liệu đã truy xuất |
| **SaaS/cloud/database** | Role, policy, ACL, owner, grant thực tế | Quyền được gán chưa chắc có thể thực thi sau explicit deny |
| **Audit log** | Truy cập được thấy trong cửa sổ quan sát | Không có log không đồng nghĩa không sử dụng |
| **Asset/resource catalog** | Sensitivity, owner, tenant, criticality | Nhãn tài nguyên có thể thiếu hoặc chưa được cập nhật |
| **Service catalog** | Workload, owner team, môi trường, nhiệm vụ | Workload không tự gắn với employment của owner |

**Nguồn có thẩm quyền theo từng thuộc tính** là nền tảng. HRIS có thể quyết định end date, IGA quyết định approval, tài nguyên quyết định ownership, còn target cung cấp quan sát về quyền đã cấp. Không chọn bản ghi có updatedAt mới nhất từ mọi nguồn mà bỏ qua trách nhiệm dữ liệu.

## 8. Quy trình phát hiện quyền thừa từ đầu đến cuối

~~~mermaid
flowchart TD
    S["HRIS / Sponsor / IGA<br/>Nhu cầu và phê duyệt"] --> E["Tính expected access<br/>theo identity, job, thời điểm"]
    T["IdP / SCIM / SaaS / Cloud / DB"] --> O["Thu thập assigned và observed access"]
    L["Access logs / Policy decisions"] --> U["Phân tích mức sử dụng và telemetry"]
    E --> M["Identity correlation và chuẩn hóa<br/>role, tenant, resource, action"]
    O --> M
    M --> F["Tính effective access theo policy"]
    F --> D{"Expected khác effective?"}
    D -->|"Có"| C["Ứng viên quyền thừa / thiếu quyền"]
    D -->|"Không"| K["Kiểm tra tín hiệu rủi ro khác"]
    U --> K
    K --> C
    C --> R["Đánh giá bằng chứng, rủi ro, owner<br/>false positive và ngoại lệ"]
    R --> P["Đề xuất least privilege remediation"]
    P --> A["Phê duyệt, thu hồi/thu hẹp có kiểm soát"]
    A --> V["Đọc lại tại target + thử ALLOW/DENY"]
    V --> G{"Đã đạt trạng thái mong muốn?"}
    G -->|"Có"| Z["Audit và đóng phát hiện"]
    G -->|"Chưa/không rõ"| X["Giữ mở, phân công xử lý và deadline"]
    X --> R
~~~

Khi thực tế không thể tính toàn bộ effective access, cần tách **assigned access inventory** khỏi **effective access đã kiểm chứng**. Không tự gắn nhãn đã xác minh cho quyền chỉ mới được liệt kê trong cấu hình.

## 9. Tính quyền hiệu lực: một role không phải toàn bộ câu chuyện

**Effective access** là kết quả phối hợp các chính sách có thể bao gồm:

- **RBAC:** role, group, role hierarchy và permission mapping.
- **ABAC:** trạng thái lao động, dự án, mức clearance, thời điểm, đặc tính tài nguyên và ngữ cảnh.
- **PBAC:** policy combining tại Policy Decision Point (PDP), điều kiện deny ưu tiên và obligations.
- **ACL/ReBAC:** quyền chủ sở hữu, quyền được chia sẻ trực tiếp và quan hệ trong đồ thị.
- **Scope và audience:** giới hạn của OAuth access token tại API.
- **Ranh giới cloud:** explicit deny, organization policy, permissions boundary, session policy hoặc policy cấp tài nguyên tùy nền tảng.
- **Trạng thái credential:** tài khoản bị disable, token bị thu hồi hoặc phiên hết hạn.

Ví dụ quyền cloud có một biểu thức wildcard **không chứng minh chủ thể đang ALLOW mọi thao tác** nếu còn ranh giới tổ chức, explicit deny hoặc điều kiện resource. Tuy nhiên wildcard là **tín hiệu đáng kiểm tra sâu** vì nếu những ranh giới khác thay đổi, phạm vi quyền có thể trở nên nguy hiểm.

### Mô hình hóa quyền theo bộ bốn

~~~text
Entitlement:
    subject = iam-482
    action = REPORT_READ
    resource = project-atlas/*
    tenant = org-a
    source = approved-role:ReportReader
    effectiveFrom = 2026-10-01T00:00:00+07:00
    effectiveUntil = not-set-by-source

Decision:
    allowed = verifiedIdentity
              AND tokenValidForAPI
              AND currentEmploymentRelationForOrgA
              AND policyGrantsReportRead
              AND requestedResourceBelongsToAtlas
              AND noHigherPriorityDeny
~~~

Đây là mô hình minh họa. “effectiveUntil chưa đặt” chỉ có nghĩa không có hạn nếu nguồn có thẩm quyền xác nhận điều đó; **giá trị thiếu do lỗi dữ liệu** không được mặc nhiên chuyển thành quyền vô thời hạn.

## 10. Phát hiện quyền thừa bằng so sánh quyền kỳ vọng và quyền đã cấp

**Diff expected–assigned** là tín hiệu phát hiện mang tính quy tắc. Có thể tính expected từ **job role, department, organization, project assignment, approved access request và ngoại lệ có hạn**.

Ví dụ:

| Tài khoản | Quyền expected | Quyền assigned | Kết luận sơ bộ |
| --- | --- | --- | --- |
| Lan, Analyst org-a | READ Atlas | READ Atlas | Khớp |
| Lan, Analyst org-a | READ Atlas | READ Atlas + ADMIN Atlas | Admin là ứng viên thừa |
| Bình, đã Mover sang Nova | READ Nova | READ Atlas + READ Nova | Atlas có thể là quyền tồn dư |
| Hòa, Leaver org-a | Không còn quyền org-a | PAT còn active ở org-a | Cần điều tra và xử lý ưu tiên |
| svc-exporter | EXPORT đúng một workspace | ADMIN toàn SaaS | Có thể thu hẹp quyền máy |

Đây là **đối chiếu quyền mục tiêu**, chưa phải bằng chứng quyền thật nếu assigned chưa được áp dụng hoặc có các lớp deny. Cần xác minh:

1. Expected access có được tính từ **bản ghi nguồn mới nhất và đúng thời điểm hiệu lực** không?
2. Có **approval hoặc ngoại lệ ngoài chuẩn** mà tập expected chưa bao phủ không?
3. Role được ánh xạ sang những action/resource nào ở target?
4. Có quyền trực tiếp, nhóm lồng nhau hoặc ownership bị bỏ sót không?
5. Khi gọi API thật, PEP có ALLOW hay DENY?

**Sửa expected access chỉ để khớp một quyền thừa sẵn có là sai phương pháp.** Quyền mục tiêu phải căn cứ vào nhu cầu nghiệp vụ và phê duyệt độc lập.

## 11. Phát hiện quyền thừa từ log sử dụng

**Usage analysis** tìm những quyền đã cấp nhưng không thấy sử dụng trong một khoảng quan sát thích hợp. Đây là cách tốt để xác định ứng viên thu hẹp, đặc biệt với quyền đặc quyền và quyền có chi phí/rủi ro cao.

Các tín hiệu:

- Hành động nhạy cảm như DELETE, ADMIN hoặc MANAGE_ACCESS chưa được dùng.
- Một role admin được cấp liên tục nhưng người dùng chỉ thực hiện thao tác đọc.
- Client có OAuth scope **write** nhưng chỉ gọi endpoint READ.
- Workload có quyền truy cập nhiều API nhưng chỉ gọi một API.
- Group/ACL tồn tại lâu dù không có lần truy cập hợp lệ nào được thấy.

### Vì sao “0 lần sử dụng” không phải kết luận chắc chắn?

- **Cửa sổ log ngắn** hơn chu kỳ nghiệp vụ: cuối tháng, cuối quý, cuối năm.
- **Nguồn log không đầy đủ**: ứng dụng không ghi object-level action, batch job hoặc truy cập qua đường khác.
- **Retention ngắn** hoặc log đã bị xoay/xóa.
- **Quyền dự phòng** được giữ để phục hồi hoặc ứng phó sự cố.
- **Policy cho phép nhưng không phát sinh nhu cầu** trong giai đoạn đo.
- **Thao tác hợp lệ bị chặn trước PEP**, do đó không có successful-use event.

Vì vậy, nên lưu thông tin **quan sát bao lâu, những hệ thống/endpoint nào được bao phủ, sự kiện nào được tính là sử dụng và mức tin cậy của telemetry**. Không tự động thu hồi quyền quan trọng chỉ vì thiếu log.

## 12. Cửa sổ quan sát, chu kỳ nghiệp vụ và sự kiện hiếm

Một tổ chức có thể phân loại quyền theo **nhịp sử dụng dự kiến**:

| Loại quyền | Chu kỳ có thể gặp | Cần kiểm tra trước khi kết luận unused |
| --- | --- | --- |
| Dashboard đọc hàng ngày | Ngày/tuần | Log API có đầy đủ không? |
| Xuất báo cáo tháng | Tháng | Đã quan sát qua một hoặc nhiều kỳ kết sổ? |
| Khóa sổ quý | Quý | Kỳ cao điểm có nằm trong log? |
| Audit cuối năm | Năm | Có nhiệm vụ theo lịch và phê duyệt còn hợp lệ? |
| Break-glass | Chỉ khi khẩn cấp | Quy trình kiểm tra, owner, giám sát và bảo vệ ngoài băng |
| Bảo trì định kỳ | Theo lịch bảo trì | Owner xác nhận lịch và nhu cầu kỹ thuật |
| Workload DR/failover | Chỉ khi dự phòng | Có kiểm thử phục hồi và khả năng chuyển trạng thái hợp lệ? |

**Không có ngưỡng 30/60/90 ngày mặc định đúng cho mọi quyền**. Có thể dùng một ngưỡng để **tạo cảnh báo rà soát**, nhưng quyết định thu hồi cần dựa trên loại tài nguyên, chu kỳ nhiệm vụ, khả năng quan sát và rủi ro.

Một quyền hiếm dùng không nhất thiết phải duy trì thường trực. Có thể giảm rủi ro bằng **Just-in-Time (JIT), Privileged Access Management (PAM), thời hạn và phê duyệt khi cần**, thay vì giữ Administrator 24/7.

## 13. Phát hiện quyền rộng và đặc quyền cao

Một số dấu hiệu dễ nhận diện bằng rule:

| Tín hiệu cấu hình | Rủi ro có thể có | Cần đối chiếu thêm |
| --- | --- | --- |
| **Admin/Owner** dài hạn | Có thể sửa quyền, cấu hình hoặc dữ liệu | Nhu cầu vận hành, scope, JIT/PAM có dùng được không? |
| **Wildcard action/resource** | Khả năng cho phép nhiều thao tác/tài nguyên | Explicit deny, boundary, điều kiện và tenant |
| **Cross-account/trust role** | Có thể truy cập thêm tài khoản cloud | Trust policy, principal, external condition, chuỗi assume role |
| **Permission to manage IAM** | Có thể cấp thêm quyền cho mình/người khác | SoD, approval, boundary và đường leo thang |
| **Secret read/decrypt** | Truy cập credential có thể mở hệ thống khác | Phạm vi secret, key policy, cách quản lý |
| **Database superuser** | Quyền trên nhiều schema và bảng | Tác vụ DBA thật, tách tài khoản ứng dụng |
| **Kubernetes cluster-admin** | Toàn quyền cluster | Namespace/role tối thiểu và workload boundary |
| **SaaS organization owner** | Quản lý user, billing hoặc dữ liệu toàn tenant | Owner hợp lệ, tài khoản dự phòng và kiểm toán |

Quyền “có thể thay đổi IAM” còn cần được kiểm tra theo **khả năng nâng quyền gián tiếp**, ví dụ sửa trust policy, tạo credential mới, thay quyền service account hoặc đọc secret dẫn tới hệ thống khác.

Không chỉ xem tên policy là “ReadOnly”. Quyền thật phải được tính từ **nội dung policy, điều kiện, resource policy, kế thừa và thực thi**. Một role do nội bộ đặt tên Reader vẫn có thể bao gồm WRITE.

## 14. Phân tách nhiệm vụ (SoD) và kết hợp quyền độc hại

**Separation of Duties (SoD)** ngăn một người nắm những năng lực xung đột mà nếu kết hợp có thể bỏ qua kiểm soát nghiệp vụ.

| Quyền A | Quyền B | Rủi ro |
| --- | --- | --- |
| Tạo nhà cung cấp | Phê duyệt thanh toán cho nhà cung cấp đó | Tự tạo và tự phê duyệt giao dịch |
| Tạo tài khoản | Phê duyệt cấp đặc quyền cho tài khoản vừa tạo | Tự tạo đường vào có quyền cao |
| Phát triển code | Tự phê duyệt và triển khai production ngoài quy trình | Bỏ qua đánh giá độc lập |
| Tạo chính sách IAM | Xóa hoặc sửa log kiểm toán liên quan | Che giấu thay đổi quyền |
| Quản lý khóa bí mật | Thực hiện giao dịch sử dụng khóa không kiểm soát | Khó phân tách quyền quản trị với sử dụng |

**SoD vi phạm ngay cả khi cả hai quyền đều được sử dụng thường xuyên**, nên phân tích unused permission không thể phát hiện đầy đủ. Cần có **SoD rule matrix**, phạm vi tài nguyên, actor, approval và cơ chế kiểm soát bù trừ nếu tổ chức phê duyệt ngoại lệ.

Nên phân biệt **SoD tĩnh** (không được giữ hai role cùng lúc) và **SoD động** (có thể giữ role nhưng không được tự phê duyệt chính giao dịch do mình tạo). PDP/PEP hoặc workflow nghiệp vụ phải thực thi đúng loại kiểm soát đã chọn.

## 15. Role mining: phát hiện vai trò thừa và gộp quyền sai

**Role mining** phân tích phân bổ quyền và mẫu sử dụng giữa nhiều chủ thể để phát hiện:

- Role không có ai sử dụng/không còn owner;
- Role nhiều quyền bất thường so với nhóm cùng chức năng;
- Nhiều role gần giống nhau nhưng chồng chéo và khó quản trị;
- Direct entitlement nằm ngoài mô hình role chuẩn;
- Quyền kế thừa không rõ nguồn, không có phê duyệt;
- Một nhóm người có quyền admin dù nhiệm vụ tương tự nhóm chỉ đọc.

Ví dụ, cùng job code **DataAnalyst**, 20 người có quyền **READ_REPORTS**, nhưng 1 người có thêm **MANAGE_USERS** và **DELETE_DATA**. Đây là **outlier** để rà soát, không tự chứng minh cá nhân đó sai: họ có thể là team lead hoặc có nhiệm vụ hỗ trợ tạm thời đã được duyệt.

**Role mining nên là công cụ phát hiện ứng viên**, không phải bộ phận tự tạo role/entitlement mới chỉ từ hành vi sử dụng. Log phản ánh thói quen và có thể chứa những hành vi đã vượt policy, nên **không được biến một hành vi sai thành bằng chứng hợp lệ của nhu cầu cấp quyền**.

## 16. ABAC, PBAC và PDP giúp phát hiện quyền thừa

Một quyền được gán tại IdP hoặc ứng dụng có thể bị giới hạn bởi điều kiện **Attribute-Based Access Control (ABAC)**:

~~~text
ALLOW READ(report) IF:
    subject.employmentStatus == ACTIVE
    AND subject.organizationId == report.organizationId
    AND report.projectId IN subject.approvedProjects
    AND subject.hasEntitlement("REPORT_READ", report.projectId)
    AND noHigherPriorityDeny
~~~

**Policy-Based Access Control (PBAC)** tổ chức các quy tắc thành policy có kiểm soát. **PDP (Policy Decision Point)** tính Permit/Deny/NotApplicable/Indeterminate; **PEP (Policy Enforcement Point)** chặn hoặc cho request, còn **PIP** cung cấp attribute và **PAP** quản lý policy.

Quyền thừa có thể do:

- **Gán role rộng**, nhưng PDP vẫn chặn đúng: nguy cơ tiềm ẩn khi policy thay đổi.
- **Thiếu điều kiện tenant**: API ALLOW request ngoài organization dù token có scope read.
- **Attribute stale**: Mover/Leaver đã xảy ra nhưng PIP còn project/role cũ.
- **PEP bypass**: API download hoặc batch job không hỏi PDP.
- **Permit cache quá hạn**: quyết định cũ tiếp tục cho phép truy cập.
- **Combining policy sai**: Permit lấn át emergency Deny ngoài ý muốn.

Để phát hiện chính xác, cần kiểm thử **quyền hiệu lực tại resource server**, không chỉ liệt kê role hoặc kiểm tra màn hình người dùng có ẩn nút hay không.

## 17. OAuth/OIDC: quyền thừa qua scope, grant và token

Trong **OAuth 2.0**, một client có thể được cấp **scope** rộng hơn chức năng cần, ví dụ **reports:write** dù chỉ tổng hợp báo cáo đọc. Trong **OpenID Connect (OIDC)**, scopes **openid, profile, email** phục vụ nhận dạng/claims theo giao thức; chúng không phải role nghiệp vụ.

| Dấu hiệu | Rủi ro | Kiểm tra cần có |
| --- | --- | --- |
| Client có **admin/write scope** nhưng chỉ cần read | Token có khả năng thao tác quá rộng | Registration, consent/grant, API scope contract |
| **offline_access** không có nhu cầu | Refresh token sống qua nhiều phiên | Grant và refresh-token lifecycle |
| Access token có nhiều audience/resource ngoài yêu cầu | Phạm vi ảnh hưởng rộng khi token lộ | Resource binding, aud, policy issuer |
| User-delegated token dùng role cũ | Mover vẫn có thể truy cập cũ | Policy freshness và token revocation |
| PAT ứng dụng ngoài IdP | Đường truy cập tồn dư sau Leaver | Inventory PAT và revoke tại sản phẩm |
| Client credentials toàn organization | Workload có nhiều quyền | Owner, tenant scope, secret và action minimization |

**Scope là điều kiện của token/client, không tự mô tả toàn bộ quyền trên tài nguyên.** Token có **reports:read** không chứng minh người gọi được đọc mọi report. Cần kiểm tra audience, subject, tenant, role/entitlement và resource ownership.

**Revoke refresh token không nhất thiết chặn ngay access token JWT đã cấp.** Với token tự chứa được xác minh offline, API có thể chấp nhận tới hạn nếu thiếu denylist, security epoch, introspection hoặc policy recheck. Khi đánh giá quyền thừa sau Mover/Leaver, phải tính cả những token và phiên còn được chấp nhận.

## 18. IdP, SSO và SCIM: nơi nào chỉ báo quyền, nơi nào thực sự áp dụng?

**Identity Provider (IdP)** quản lý xác thực, group và phiên SSO theo kiến trúc. **SCIM** giúp đồng bộ **User/Group** tới ứng dụng. Nhưng không phải mọi sản phẩm ánh xạ group thành role theo cùng cách.

Một quy trình có thể ghi:

~~~text
HR event:        Mover approved
IGA expected:    Remove AtlasAdmin; Add NovaReader
IdP groups:      AtlasAdmin removed
SCIM group:      Request succeeded
SaaS local ACL:  AtlasAdmin still directly assigned
OAuth PAT:       Token with admin scope still active
Effective:       DELETE Atlas still ALLOW
~~~

Đây là một **phát hiện quyền thừa có giá trị**: một hoặc nhiều bước đồng bộ thành công không xóa được quyền tại nơi thực thi.

Khi đối soát, cần đọc lại **account, group, local role, direct ACL, ownership, PAT/session và API decision**. Nếu target không hỗ trợ đọc quyền, ghi **UNVERIFIED** và ngoại lệ với owner thay vì tuyên bố toàn bộ quyền đã được thu hồi.

**SSO không thay authorization; SCIM deactivate không phải cơ chế thu hồi mọi token**. Những khẳng định “đã tắt account ở IdP nên chắc chắn hết quyền” cần được kiểm chứng thực tế.

## 19. Joiner: phát hiện quyền cấp thừa ngay từ lúc tạo account

**Joiner** là thời điểm tốt nhất để ngăn overprivilege trở thành thói quen:

1. HRIS/nguồn bảo trợ xác minh **identity, employment, organization, ngày bắt đầu và công việc**.
2. IAM/IGA tính **role baseline** theo job/department/project với quyền tối thiểu.
3. Chủ tài nguyên phê duyệt quyền ngoài baseline hoặc đặc quyền cao.
4. Provision account qua IdP, SCIM/API; không mặc định tạo local admin.
5. Kiểm tra **tất cả group và ACL mặc định** mà ứng dụng cấp khi account mới xuất hiện.
6. Tính effective access và thử **đường được phép + đường phải từ chối** trên tài nguyên kiểm thử.
7. Đối chiếu account đã tạo với expected access và ghi ngoại lệ.

### Những dấu hiệu sai lệch Joiner

| Dấu hiệu | Hậu quả | Phát hiện |
| --- | --- | --- |
| Account nhận group admin mặc định | Nâng đặc quyền ngoài nhiệm vụ | Diff baseline và group target |
| Vai trò cũ của nhân viên được tuyển lại tự khôi phục | Quyền không còn căn cứ | So employment mới với grant cũ |
| Account được active trước ngày bắt đầu | Truy cập sớm | Kiểm tra effectiveAt và trạng thái target |
| Mapping người–account sai do email trùng | Quyền người khác gán nhầm | Correlation theo ID đáng tin |
| SCIM Group không khớp role thực tế | Thiếu hoặc thừa quyền | Readback và policy/API tests |

Không coi một **SCIM 201 Created** hoặc lần SSO thành công là bằng chứng Joiner đạt least privilege. **Quyền thừa chỉ được xác định sau khi đối chiếu với nhiệm vụ và quyền hiệu lực**.

## 20. Mover: nơi quyền thừa thường tích lũy

**Mover** đổi vai trò, phòng ban, dự án, organization hoặc mức đặc quyền. Rủi ro phổ biến nhất là **chỉ cộng quyền mới mà không rút quyền cũ** (*privilege creep*).

Ví dụ một kỹ sư chuyển từ Atlas sang Nova:

| Quyền | Trước Mover | Sau Mover mong muốn | Dấu hiệu thừa |
| --- | --- | --- | --- |
| READ Atlas | Có | Không | Vẫn đọc Atlas sau mốc hiệu lực |
| ADMIN Atlas | Có theo nhiệm vụ cũ | Không | Direct ACL/admin token còn tồn tại |
| READ Nova | Chưa có | Có sau khi duyệt | Cần cấp, không phải quyền thừa |
| ADMIN Nova | Không | Không trừ khi duyệt | Role mặc định quá rộng |

### Quy trình phát hiện quyền tích lũy

1. Lấy assignment mới nhất với **sourceVersion/effectiveAt**.
2. Tính lại **expected access toàn phần**, không chỉ delta cấp quyền.
3. Lấy group, role, ACL, grant, token và entitlement ở target.
4. Tìm quyền chỉ tồn tại do **role cũ hoặc exception hết hạn**.
5. Kiểm tra hệ thống có giai đoạn bàn giao được duyệt hay không.
6. Đề xuất thu hồi các quyền cũ không còn căn cứ, có kế hoạch rollback/khôi phục theo quy trình.
7. Sau thay đổi, kiểm thử **Nova ALLOW**, **Atlas DENY** và đối soát tại resource server.

Đối với quyền bàn giao có thời hạn, lưu **approver, owner, resource, action, expiresAt**. Một ngoại lệ ghi “tạm thời” nhưng không có hạn là ứng viên quyền thừa cần rà soát.

## 21. Leaver: phát hiện quyền tồn dư và đường vào ngoài IdP

Khi kết thúc quan hệ làm việc, **expected access** từ quan hệ đó thường chuyển về **không còn quyền**, trừ những quan hệ độc lập vẫn hợp lệ hoặc ngoại lệ nghiệp vụ được ủy quyền.

Các chỉ báo rủi ro sau Leaver:

- **IdP account disabled nhưng SaaS local user vẫn active**.
- **SCIM User active=false** nhưng PAT/API key vẫn được API chấp nhận.
- Refresh token/grant vẫn có thể cấp access token mới.
- JWT access token còn hiệu lực ở resource server vì chỉ kiểm tra chữ ký và hạn.
- Cloud service principal hoặc key từng do người nghỉ việc quản lý chưa có owner mới.
- Nhóm, direct ACL, repository ownership, delegated mailbox hoặc chia sẻ tài liệu chưa thu hồi.
- Session của ứng dụng không kết thúc khi logout IdP.
- Account được tạo lại bởi **retry Joiner/Mover cũ** sau khi Leaver đã phát sinh.

**Khóa account không phải bằng chứng toàn bộ quyền đã biến mất.** Cần xác định **đường quyền còn có thể sử dụng** và thời điểm thực tế API từ chối.

### Người có nhiều hợp đồng

Nếu person vẫn có quan hệ hợp lệ với org-b nhưng đã Leaver org-a, không tự khóa toàn bộ identity nếu chính sách không yêu cầu. Phải rút **đúng quyền của employment/org-a** và giữ những quyền được phê duyệt độc lập ở org-b. Không dùng một trường employmentStatus tổng quát để mở hoặc đóng quyền ở mọi tenant.

## 22. Tài khoản dịch vụ và workload identity: quyền thừa không có người dùng đăng nhập

**Service account** và **workload identity** thường chạy tự động nên không có hành vi đăng nhập tương tác giống nhân viên. Các chủ thể này có thể dùng client credentials, managed identity, certificate, khóa riêng hoặc workload federation.

| Dấu hiệu | Ví dụ | Biện pháp phát hiện |
| --- | --- | --- |
| Quyền quá rộng | Bot chỉ đọc nhưng là organization admin | So job purpose với policy và scope |
| Dùng chung credential | Hai workload dùng một secret hoặc service principal | Inventory deployment và secret references |
| Không có owner | Job cũ còn client credentials hoạt động | Service catalog vs cloud IAM |
| Cross-environment | CI dev có thể sửa production | Kiểm tra resource policy, environment boundary |
| Token dài hạn | Key/PAT không có expiration hoặc rotation | Credential age, last-use và grant inventory |
| Không còn nhiệm vụ | Service đã decommission nhưng quyền còn | Deployment inventory và access logs |
| Có thể leo thang quyền | Workload được sửa IAM hoặc đọc secret của admin | Phân tích chuỗi privilege escalation |

Một workload ít dùng vẫn có thể cần cho **disaster recovery**. Một bot còn hoạt động production có thể cần được **chuyển owner** khi nhân viên quản lý nó nghỉ việc, không nhất thiết xóa lập tức. Tuy nhiên, quyền của nhân viên cũ, PAT cá nhân và secret họ có thể biết cần được rà soát.

**Không buộc workload bấm MFA push của con người** mỗi API call. Kiểm soát phù hợp là danh tính máy tách biệt, scope tối thiểu, audience, hạn, môi trường, owner và khả năng thu hồi.

## 23. Quyền đặc quyền: từ standing admin sang JIT/PAM

**Standing privilege** là quyền cao được giữ thường trực, kể cả khi không thực hiện nhiệm vụ đặc quyền. Với tài nguyên nhạy cảm, có thể giảm rủi ro bằng:

- **Privileged Access Management (PAM):** kiểm soát và ghi nhận việc dùng đặc quyền.
- **Just-in-Time (JIT):** cấp quyền tại thời điểm có nhiệm vụ hợp lệ, hết hạn tự động.
- **Just-Enough-Administration (JEA):** chỉ cho các thao tác quản trị cần thiết.
- **Step-up/phishing-resistant MFA:** chứng minh mức xác thực thích hợp trước thao tác đặc quyền.
- **Separation of Duties:** tách người yêu cầu, người phê duyệt và người thực hiện khi cần.
- **Session monitoring:** theo dõi hành động có rủi ro theo quyền hạn và pháp lý.

Ví dụ, kỹ sư hỗ trợ sản xuất chỉ cần restart một service khi có incident. Thay vì giữ **cloud administrator 24/7**, có thể tạo role giới hạn service và cấp trong 60 phút sau khi được phê duyệt. **60 phút chỉ là ví dụ**, không phải SLA chung.

Phát hiện cần so sánh **quyền thường trực** với **khả năng cấp quyền động đáp ứng nhiệm vụ**. Nếu quy trình JIT không hoạt động ổn định, phải khắc phục tính khả dụng trước khi thu hồi quyền cứu hộ quan trọng, tránh gây rủi ro vận hành.

## 24. Đánh giá rủi ro và mức độ ưu tiên xử lý

Không phải mọi quyền thừa có mức độ nguy hiểm như nhau. Có thể dùng một mô hình điểm **nội bộ, minh bạch và được hiệu chỉnh**, nhưng không coi điểm số là bằng chứng tuyệt đối.

Ví dụ các yếu tố:

| Yếu tố | Mức thấp | Mức cao |
| --- | --- | --- |
| **Độ nhạy tài nguyên** | Báo cáo công khai nội bộ | Dữ liệu cá nhân, tài chính, production |
| **Độ rộng thao tác** | READ một resource | DELETE, MANAGE_ACCESS, wildcard |
| **Độ rộng phạm vi** | Một dự án | Toàn organization/multi-tenant |
| **Đường khai thác** | Có MFA mạnh, JIT, network restriction | Credential dài hạn, bearer token không ràng buộc |
| **Trạng thái chủ thể** | Người ACTIVE và approval hợp lệ | Leaver, ownerless workload |
| **Thời hạn** | Quyền ngắn và có expiry | Standing admin không có hạn |
| **Bằng chứng** | Effective access được xác minh | Chỉ suy từ tên role hoặc log không đầy đủ |
| **SoD/leo thang quyền** | Không có kết hợp nguy hiểm | Có thể tự cấp quyền hoặc phê duyệt giao dịch |

Mô hình điểm **minh họa**:

~~~text
riskCandidate = 0
riskCandidate += resourceSensitivityScore
riskCandidate += privilegeBreadthScore
riskCandidate += tenantExposureScore
riskCandidate += standingDurationScore
riskCandidate += toxicCombinationScore
riskCandidate += identityLifecycleRiskScore

evidenceConfidence = classifyEvidence(
    authoritativeExpectedAccess,
    targetEffectiveAccess,
    telemetryCoverage,
    mappingConfidence
)

prioritizeReview(riskCandidate, evidenceConfidence)
~~~

Không có hệ số cố định cho mọi doanh nghiệp. **Mức rủi ro** và **độ chắc chắn của bằng chứng** nên là hai trường độc lập: một quyền có nguy cơ cao nhưng chưa xác minh cần được điều tra khẩn, không tự động kết luận người đó vi phạm.

## 25. Mã giả phát hiện quyền thừa

Mã giả dưới đây mô tả một detector **không tự xóa quyền**:

~~~text
detectExcessAccess(identity, target, observationWindow):
    link = resolveVerifiedIdentityToTargetAccount(identity, target)
    if link.isAmbiguous:
        return finding("UNVERIFIED_MAPPING", severity="REVIEW")

    source = loadAuthoritativeEmploymentAndAssignments(identity)
    expected = calculateExpectedAccess(
        source,
        approvedEntitlements(identity, target),
        effectiveTime=now()
    )

    assigned = readAssignedGrantsGroupsRolesAndACLs(target, link)
    effective = evaluateOrQueryEffectiveAccess(target, link, assigned)
    usage = loadUsageEventsWithCoverage(target, link, observationWindow)

    if expected.isUnknown or effective.isUnknown:
        return finding(
            "INSUFFICIENT_EVIDENCE",
            confidence="LOW",
            remediation="VERIFY_SOURCE_OR_TARGET"
        )

    candidates = effective.permissionsMinus(expected.permissions)
    candidates += findExpiredGrants(assigned)
    candidates += findToxicCombinations(effective, approvedSoDRules)
    candidates += findPrivilegedUnusedPermissions(
        effective, usage, target.observationCoverage
    )

    for candidate in deduplicate(candidates):
        attachEvidence(
            candidate,
            sourceVersion=source.version,
            targetState=effective,
            usageCoverage=usage.coverage,
            approvalRecords=expected.approvals,
            identityLink=link
        )
        assignRiskOwnerAndReviewStatus(candidate)

    return candidates
~~~

**Quan trọng:** Hàm **permissionsMinus** ở đây biểu diễn **so sánh tập quyền theo action/resource/tenant/thời gian**, không chỉ trừ tên role. Trong hệ thống có ABAC, deny, boundary, wildcard hoặc role hierarchy, cần dùng policy evaluator/graph đáng tin để tính phạm vi tương đương. Nếu không tính được chính xác, đánh dấu **ESTIMATED/UNKNOWN**, không giả lập đã có chứng cứ.

Detector cũng cần xử lý **event đến trễ, dữ liệu phân trang, API quota, token hết hạn, phiên bản policy khác nhau và quyền truy cập để đọc target**. Phát hiện tự động là bước tạo ứng viên, còn thu hồi phải theo mức rủi ro và quy trình được ủy quyền.

## 26. SQL minh họa phát hiện role không còn được phê duyệt

Giả sử có hai bảng trừu tượng:

- **approved_entitlements**: quyền đã phê duyệt theo subject, target, tenant, action/resource và khoảng hiệu lực.
- **assigned_entitlements**: quyền đang được cấu hình tại ứng dụng.

Truy vấn minh họa phát hiện những bản ghi assigned **không có approval tương ứng đang hiệu lực**:

~~~sql
SELECT
    a.subject_id,
    a.target_system,
    a.tenant_id,
    a.resource_pattern,
    a.action,
    a.grant_id
FROM assigned_entitlements AS a
WHERE NOT EXISTS (
    SELECT 1
    FROM approved_entitlements AS p
    WHERE p.subject_id = a.subject_id
      AND p.target_system = a.target_system
      AND p.tenant_id = a.tenant_id
      AND p.resource_pattern = a.resource_pattern
      AND p.action = a.action
      AND p.valid_from <= CURRENT_TIMESTAMP
      AND (p.valid_until IS NULL OR CURRENT_TIMESTAMP < p.valid_until)
      AND p.approval_status = 'APPROVED'
);
~~~

**Đây không phải câu SQL chạy được ngay trong một schema thật.** Nó giả định hai bảng đã chuẩn hóa với quyền atomic, cùng namespace và time semantics; **NULL valid_until** chỉ có nghĩa không có hạn khi dữ liệu đã được xác minh. Không áp dụng trực tiếp cho quyền wildcard, nested role, deny policy, ABAC hoặc IAM inheritance mà chưa tính effective access. Kết quả là **ứng viên thiếu approval**, không tự chứng minh quyền đã được PEP ALLOW.

Khi hệ thống có nhiều employment/tenant, thêm ràng buộc theo **employment relation** và đảm bảo bản ghi có quyền từ quan hệ hợp lệ được xử lý đúng.

## 27. Quy trình access review và chứng thực lại quyền

**Access certification/recertification** là quy trình chủ tài nguyên, manager hoặc owner xác nhận quyền còn phù hợp. Nó hỗ trợ phát hiện quyền thừa khi kết hợp dữ liệu kỹ thuật:

1. Chọn phạm vi review theo **risk tier**: admin, dữ liệu nhạy cảm, tài khoản lâu không hoạt động, Leaver, service account.
2. Chuẩn hóa identity, account, role, action/resource và thời hạn để reviewer hiểu **quyền thực sự cho phép làm gì**.
3. Hiển thị **nguồn phê duyệt, lý do, mức sử dụng, chủ tài nguyên và các đường cấp quyền**.
4. Yêu cầu lựa chọn rõ: **giữ**, **thu hẹp**, **thu hồi**, **cần xác minh**, hoặc **ngoại lệ có hạn**.
5. Có cơ chế **escalation** khi owner không trả lời; không mặc định duy trì mọi quyền vô thời hạn.
6. Thực thi quyết định tại target bằng connector/API được phép.
7. Đọc lại **quyền thực tế**, không chỉ trạng thái ticket hoàn tất.
8. Lưu bằng chứng người duyệt, thời điểm, policy và kết quả để phục vụ kiểm toán.

**Manager xác nhận “vẫn cần quyền” không tự đủ** nếu manager không biết permission nằm trong role hoặc không có thẩm quyền với dữ liệu. Với quyền rủi ro cao, có thể yêu cầu **resource owner hoặc chủ kiểm soát** phê duyệt.

Thực hành tốt là cung cấp cho người duyệt **bối cảnh cụ thể**, không phải một danh sách hàng nghìn mã quyền không có diễn giải.

## 28. Ngăn kết luận sai và giảm false positive

Những tình huống dễ báo động nhầm:

| Phát hiện ban đầu | Nguyên nhân hợp lệ có thể có | Cách xác minh |
| --- | --- | --- |
| Role chưa dùng 90 ngày | Đóng sổ năm hoặc DR | Kiểm tra lịch nghiệp vụ và owner |
| Group khác baseline job | Nhân viên đang kiêm nhiệm được duyệt | Kiểm tra assignment/approval hiện hành |
| Quyền admin trên account dự phòng | Break-glass theo quy trình | Kiểm soát truy cập, owner, vault, alert và drill |
| Role wildcard | Boundary và explicit deny giới hạn mạnh | Tính effective actions thực tế |
| Log không thấy DELETE | Endpoint chưa có audit đủ mức | Kiểm tra coverage và sampling |
| Account không có hoạt động | Credential đã được dùng ở đường không ghi nhận | Kiểm tra các nguồn log và target |
| Group vẫn còn sau Mover | Quyền bàn giao có hạn được phê duyệt | Kiểm tra expiresAt và resource owner |
| User không có department | Contractor thuộc nguồn sponsor khác HRIS | Xác minh loại identity và authority matrix |

**False positive thấp không phải mục tiêu duy nhất**: việc bỏ sót quyền sau Leaver nguy hiểm hơn vài cảnh báo cần xác minh. Hệ thống cần cân bằng precision, recall, chi phí rà soát và rủi ro của từng loại quyền, có khả năng kiểm tra kết quả sau cải tiến.

Khi dữ liệu không rõ, dùng trạng thái **NEEDS_EVIDENCE**; không được tạo một kết luận chắc chắn bằng cách điền thuộc tính còn thiếu bằng giá trị mặc định thuận tiện.

## 29. Thu hồi quyền thừa một cách an toàn

**Phát hiện** không đồng nghĩa **thu hồi lập tức** trong mọi trường hợp. Một quy trình remediation tốt gồm:

~~~mermaid
flowchart TD
    D["Finding: quyền có thể thừa"] --> E["Xác minh identity, quyền expected, effective và owner"]
    E --> C{"Bằng chứng đủ và loại rủi ro?"}
    C -->|"Leaver / quyền khẩn cấp rõ"| Q["Chặn theo playbook được ủy quyền"]
    C -->|"Cần xác minh nghiệp vụ"| R["Resource owner / IGA review"]
    R --> A{"Quyết định?"}
    A -->|"Cần giữ"| X["Ngoại lệ có phạm vi, owner, hạn và review"]
    A -->|"Thu hẹp/thu hồi"| P["Kế hoạch thay đổi, phê duyệt, tác động"]
    P --> I["Thực thi ở nguồn cấp và target"]
    Q --> I
    I --> V["Readback role/ACL/token + test quyền thật"]
    V --> T{"Target đạt expected?"}
    T -->|"Đạt"| Z["Audit và đóng finding"]
    T -->|"Chưa/unknown"| O["Giữ mở, điều tra, hạn khắc phục"]
    O --> I
    X --> F["Theo dõi expiry và recertification"]
~~~

Các bước cụ thể:

1. Xác định **đường cấp quyền**: IdP group, SCIM Group, direct ACL, cloud policy, OAuth grant hay PAT.
2. Tính **phạm vi ảnh hưởng** của revoke: người, dịch vụ, job, lịch bảo trì, sự kiện business.
3. Kiểm tra quyền liên quan **production, break-glass hoặc hệ thống phục hồi**.
4. Chọn thay đổi ít gây gián đoạn: **thu hẹp role, giới hạn resource, thêm thời hạn, chuyển sang JIT** khi phù hợp.
5. Thực thi ở **nguồn quản trị đúng** để tránh connector khác cấp lại quyền ở lần đồng bộ sau.
6. Revoke/rotate **credential, session hoặc token** khi quyền thật sự cần bị chặn ngay.
7. Đọc lại **assigned và effective access**, kiểm thử các thao tác được phép và phải bị từ chối.
8. Theo dõi lỗi nghiệp vụ và có kế hoạch khôi phục **qua phê duyệt mới**, không tự đặt lại quyền admin cũ.

Với sự cố unauthorized allow đang diễn ra, có thể cần **chặn khẩn cấp** trước khi hoàn tất review thông thường, theo playbook và quyền hạn của tổ chức.

## 30. Trạng thái phát hiện và ngoại lệ

Để quản lý công việc rõ ràng, một finding có thể có các trạng thái:

| Trạng thái | Ý nghĩa |
| --- | --- |
| **DETECTED** | Có tín hiệu cần kiểm tra |
| **NEEDS_EVIDENCE** | Chưa rõ identity, effective access, approval hoặc log coverage |
| **CONFIRMED_EXCESS** | Đủ bằng chứng vượt expected/policy |
| **APPROVED_EXCEPTION** | Được phê duyệt giữ tạm thời, có hạn và owner |
| **REMEDIATION_PENDING** | Đã quyết định thu hồi/thu hẹp nhưng chưa thực thi |
| **REMEDIATED_UNVERIFIED** | Đã gửi thay đổi nhưng chưa chứng minh quyền thật |
| **VERIFIED_CLOSED** | Target và PEP/API xác nhận trạng thái mong muốn |
| **BLOCKED** | Không thể xử lý do phụ thuộc/quyền/connector, có owner |

Một quyền có thể hợp lệ trong trường hợp **khẩn cấp** nhưng vẫn phải được đánh giá: ngoại lệ nên gắn **resource, action, identity, justification, approver, expiration và biện pháp kiểm soát bù trừ**.

**Không để nhãn APPROVED_EXCEPTION trở thành cách che mọi quyền thừa**. Ngoại lệ phải được review và hết hiệu lực; nếu đã quá hạn, detector phải cảnh báo lại.

## 31. Xử lý event đến trễ và race condition

Các nguồn HRIS, IGA, IdP, SCIM, SaaS và cloud không cập nhật đồng thời. Có thể xảy ra:

~~~text
09:00  HRIS: Lan chuyển Atlas -> Nova (sourceVersion=18)
09:01  IGA: remove Atlas; add Nova
09:02  SCIM: remove Atlas group at SaaS
09:03  Old provisioning retry from sourceVersion=17
09:04  SaaS: Atlas group bị thêm lại nếu không chặn event cũ
09:05  Detector: phát hiện quyền Atlas còn ALLOW
~~~

**Cơ chế chống tái cấp quyền** cần:

- Mọi job có **sourceEventId, sourceVersion và effectiveAt**.
- Trước khi retry, kiểm tra **expected access hiện hành**.
- Event cũ không được ghi đè trạng thái đã được quyết định bởi version mới.
- Đối soát định kỳ để phát hiện update bị bỏ lỡ.
- Lưu **quyền chưa xác minh** khi connector timeout; không coi request thành công nếu không có readback.
- Phân biệt quyền theo nhiều hợp đồng để không thu hồi nhầm quyền vẫn hợp lệ.

Điều này quan trọng với Leaver: một retry Joiner cũ không được **kích hoạt lại tài khoản** sau khi quan hệ đã chấm dứt.

## 32. Kiểm toán: bản ghi phát hiện phải đủ giải thích

Một bản ghi nên giúp trả lời: **quyền nào**, **do ai cấp**, **vượt nhu cầu nào**, **ở đâu**, **lúc nào**, **bằng chứng gì**, **đã làm gì** và **ai chịu trách nhiệm**.

Ví dụ JSON minh họa, không phải schema bắt buộc:

~~~json
{
  "findingId": "excess-access-2026-009",
  "identityRef": "iam-482",
  "employmentRef": "emp-org-a-01",
  "targetSystem": "reports-saas",
  "targetTenant": "org-a",
  "targetAccountRef": "saas-user-482",
  "permission": {
    "action": "DELETE_REPORT",
    "resourceScope": "project-atlas",
    "grantSource": "direct-role:ReportAdmin"
  },
  "expectedDecision": "DENY",
  "observedEffectiveDecision": "ALLOW",
  "lastObservedUse": null,
  "usageCoverage": "READ_AND_WRITE_EVENTS_ONLY",
  "sourceVersion": "iga-17",
  "targetReadbackAt": "2026-11-23T09:40:00+07:00",
  "riskCategory": "HIGH",
  "evidenceConfidence": "HIGH_FOR_PERMISSION_DRIFT",
  "findingStatus": "CONFIRMED_EXCESS",
  "ownerTeam": "identity-governance",
  "remediation": "REMOVE_DIRECT_ADMIN_ROLE",
  "revokeConfirmedAt": null
}
~~~

Trong ví dụ, **lastObservedUse = null** không có nghĩa chắc chắn chưa từng dùng, nhất là khi **usageCoverage** không bao phủ đầy đủ sự kiện DELETE. Trường **revokeConfirmedAt = null** thể hiện việc thu hồi chưa được xác minh, không phải lỗi JSON.

Không log **mật khẩu, bearer access token, refresh token, private key, seed OTP hay nguyên dữ liệu nhân sự**. Audit nên lưu tham chiếu identity/account, policy/version, nguồn quyền, target, kết quả kiểm tra và trạng thái exception với phân quyền truy cập log.

## 33. KPI phát hiện và giảm quyền thừa

| Chỉ số | Mục đích | Lưu ý |
| --- | --- | --- |
| **Overprivileged identities** | Số danh tính có finding đã xác minh | Không gộp ứng viên chưa xác minh |
| **High-risk standing privileges** | Quyền cao tồn tại thường trực | Phân biệt break-glass hợp lệ |
| **Expired grants still effective** | Quyền có hạn nhưng vẫn ALLOW | Đo ở target, không chỉ IGA |
| **Mover residual permissions** | Quyền cũ còn sau chuyển vai trò | Gắn với effectiveAt |
| **Leaver residual access** | Quyền vẫn dùng được sau mốc cắt | Ưu tiên theo độ nhạy |
| **Unused privileged grants** | Ứng viên thu hẹp đặc quyền | Công bố cửa sổ và coverage log |
| **SoD toxic combinations** | Vi phạm phân tách nhiệm vụ | Xét scope và bù trừ được duyệt |
| **Ownerless workload identities** | Bot/secret không có chủ quản | Không tự xóa workload đang cần |
| **Time to verified revocation** | Độ trễ từ quyết định revoke tới lúc target từ chối | Theo SLA/risk tier |
| **Confirmed finding precision** | Chất lượng tín hiệu phát hiện | Có quy tắc chọn mẫu và feedback |
| **Unverified target percentage** | Phần quyền không thể đối soát | Không coi UNKNOWN là an toàn |
| **JIT adoption for privileged roles** | Chuyển từ quyền thường trực sang cấp khi cần | Theo nhiệm vụ/ứng dụng |

**Một số lượng finding lớn không tự chứng minh hệ thống kém hơn**: có thể do tăng coverage và phát hiện tốt hơn. Đánh giá hiệu quả nên kết hợp **mức độ nghiêm trọng đã xác minh, thời gian xử lý, phạm vi kiểm soát và tỷ lệ quyền tồn dư**.

Không có một KPI hay SLA tuyệt đối đúng cho mọi tổ chức; cần phân loại theo tài nguyên, regulatory requirements và đặc thù vận hành.

## 34. Kiểm thử detector và quy trình thu hồi

Một bộ kiểm thử cần có cả **tình huống phải phát hiện** và **không nên tự kết luận**:

| Case | Điều kiện | Expected |
| --- | --- | --- |
| T01 | Analyst chỉ được READ nhưng có direct DELETE role | Finding ứng viên quyền thừa |
| T02 | Mover đã hết quyền Atlas nhưng API vẫn ALLOW | Confirmed residual access |
| T03 | Leaver org-a vẫn có PAT gọi API org-a | High-priority finding |
| T04 | Employee ACTIVE org-b nhưng Leaver org-a | Chỉ phát hiện quyền thừa org-a |
| T05 | Role admin đã không sử dụng 90 ngày, log đầy đủ chưa? | Cần review, không tự revoke chỉ từ absence |
| T06 | Break-glass có owner/hạn/test và approval hợp lệ | Đánh giá exception riêng |
| T07 | Cấu hình wildcard bị explicit deny giới hạn | Tính effective access, không kết luận full admin |
| T08 | SoD vừa tạo vừa approve cùng giao dịch | Finding dù cả hai quyền đều được dùng |
| T09 | Group đã xóa ở IdP nhưng direct ACL còn | Phát hiện residual tại target |
| T10 | SCIM request trả success nhưng API vẫn ALLOW quyền cũ | Giữ finding tới readback |
| T11 | Connector timeout khi đọc quyền | UNKNOWN, không suy quyền đã hết |
| T12 | Event Mover version cũ tới sau Leaver | Không tái cấp quyền qua retry |
| T13 | Workload dev gọi tài nguyên production | Finding nếu effective access vượt policy |
| T14 | Account trùng email nhưng identity link mơ hồ | Không auto-map hoặc revoke nhầm |
| T15 | Role được dùng thường xuyên nhưng quyền rộng hơn nhiệm vụ | Vẫn có thể là quyền thừa |
| T16 | Detector xác nhận đã remove role nhưng token JWT cũ còn ALLOW | Chưa được verified closed |

### Kiểm thử ở ba lớp

1. **Rule/unit tests:** expected permission, thời gian, SoD và đánh giá finding.
2. **Integration tests:** connector lấy role, group, ACL, token metadata và mapping đúng.
3. **Authorization tests tại target:** kiểm tra API cho phép/từ chối trên tài nguyên kiểm thử; đảm bảo không bỏ sót đường API phụ.

Chỉ kiểm thử dữ liệu cấu hình không chứng minh PEP đã từ chối quyền. Khi thử nghiệm, sử dụng tài khoản và tài nguyên **được tổ chức cho phép**, tránh gây tác động tới người dùng sản xuất.

## 35. Tình huống thực hành: đặc quyền còn sau khi chuyển vai trò

**Bối cảnh:** Hạnh là kỹ sư vận hành ở Dự án Atlas, từng có quyền **RepositoryAdmin** và một PAT với scope **repo:write** để xử lý sự cố. Ngày 01/12, Hạnh chuyển sang vai trò phân tích dữ liệu tại Dự án Nova. IGA phê duyệt quyền mới: **READ Nova**, không còn quyền Atlas.

Sau thay đổi:

- HRIS và project registry xác nhận Mover đã có hiệu lực.
- IdP đã xóa nhóm AtlasAdmin.
- SCIM đồng bộ User và Group thành công.
- Kho mã nguồn vẫn giữ **direct role RepositoryAdmin** cho account của Hạnh.
- PAT còn hiệu lực và vẫn có thể gọi API ghi dữ liệu Atlas.

### Bước 1: Xác nhận loại finding

Đây không chỉ là quyền **không sử dụng**. Có bằng chứng **expected = DENY** và **effective = ALLOW** đối với một hành động không còn trong nhiệm vụ. Vì vậy, quyền Atlas là **ứng viên quyền thừa ưu tiên cao**; sau khi kiểm chứng direct role/PAT và không có ngoại lệ hợp lệ, có thể xác nhận là quyền tồn dư.

### Bước 2: Tìm nguồn phát sinh

| Dữ liệu | Quan sát | Kết luận |
| --- | --- | --- |
| Employment/project assignment | Hạnh đã sang Nova | Căn cứ quyền Atlas đã hết |
| IdP group | AtlasAdmin đã xóa | Một đường cấp quyền đã thu hồi |
| SCIM group | Đồng bộ thành công | Không chứng minh direct ACL/PAT mất hiệu lực |
| SaaS direct role | RepositoryAdmin còn | Quyền trực tiếp ngoài nhóm |
| PAT | Scope repo:write còn dùng được | Đường access độc lập cần revoke |
| API test | Ghi Atlas vẫn ALLOW | Bằng chứng effective access còn |

### Bước 3: Đề xuất và thực thi

1. Xác nhận không có **ngoại lệ bàn giao Atlas** được phê duyệt.
2. Thu hồi direct role RepositoryAdmin tại kho mã nguồn.
3. Revoke PAT/credential riêng còn quyền Atlas, theo quy trình của nền tảng.
4. Kiểm tra các session/token khác hoặc quyền chia sẻ trực tiếp còn tồn tại.
5. Thử với tài nguyên kiểm thử: **WRITE Atlas = DENY**, **READ Nova = ALLOW** khi đã được cấp.
6. Lưu **target readback, token status, thời điểm từ chối thực tế, approval và owner** trước khi đóng finding.

### Câu hỏi tự kiểm tra

**Câu 1:** Vì sao xóa nhóm IdP chưa đủ?

**Trả lời:** SaaS còn direct role và PAT riêng. Cần xác minh mọi đường quyền và khả năng API thực thi.

**Câu 2:** Nếu PAT không được sử dụng 90 ngày, có thể kết luận chắc chắn thừa không?

**Trả lời:** Không chỉ từ log. Nhưng trong tình huống này **căn cứ Mover và quyền hiệu lực vượt expected** mới là bằng chứng mạnh hơn.

**Câu 3:** Nếu Hạnh có quyền hợp lệ tại Nova, có nên vô hiệu toàn bộ identity không?

**Trả lời:** Không. Cần thu hồi quyền Atlas và giữ quyền Nova đã phê duyệt.

**Câu 4:** Tại sao phải kiểm tra token sau khi xóa role?

**Trả lời:** Token hoặc session đã cấp có thể còn được chấp nhận tùy ứng dụng. Không được coi thay đổi role là revocation thành công nếu API vẫn ALLOW.

**Câu 5:** Nếu công cụ không đọc được trạng thái PAT thì finding đã đóng chưa?

**Trả lời:** Chưa. Ghi **UNVERIFIED**, phân công owner và tiếp tục kiểm tra bằng phương thức được phê duyệt.

## 36. Checklist triển khai phát hiện quyền thừa

| Câu hỏi | Bằng chứng cần có |
| --- | --- |
| Có định nghĩa quyền kỳ vọng theo nhiệm vụ và mốc hiệu lực? | HRIS, assignment, policy và approval |
| Identity/account có liên kết đúng người và tenant? | Stable person/employment/identity/target IDs |
| Đã kiểm kê cả tài khoản máy và người? | Human, service, third-party, privileged identities |
| Đã lấy hết đường cấp quyền? | Group, role, direct ACL, ownership, policy, PAT, OAuth grant |
| Có phân biệt assigned và effective access? | Target readback, policy evaluation, PEP/API tests |
| Đã phân biệt used/unused với cần thiết/không cần thiết? | Log coverage, chu kỳ nghiệp vụ và owner review |
| Có phân tích wildcard, admin và leo thang quyền? | Effective privilege paths và resource boundaries |
| Có phát hiện toxic combination/SoD? | SoD matrix, workflow và phạm vi giao dịch |
| Có kiểm tra tenant/resource/action/time? | RBAC/ABAC/PBAC và policy ở backend |
| Có so sánh đủ JML? | Joiner baseline, Mover revoke, Leaver residual |
| Có phát hiện quyền qua SSO/SCIM ngoài IdP? | Local role, direct ACL, PAT, account/session |
| Có xem xét OAuth scope/grant/token? | Audience, refresh token, access token và revocation |
| Có kiểm soát credential service account? | Owner, environment, purpose, TTL, secret lifecycle |
| Có đánh giá false positive và blind spots? | Coverage, confidence và NEEDS_EVIDENCE |
| Có ngoại lệ hợp lệ và hết hạn? | Resource owner, approver, justification, expiresAt |
| Thu hồi có kế hoạch và phê duyệt phù hợp? | Change record, tác động, rollback/restore |
| Có readback sau thu hồi? | Assigned/effective state ở target, test ALLOW/DENY |
| Có chống retry/event cũ tái cấp quyền? | Source version, effectiveAt, reconciliation |
| Có audit và KPI? | Finding, evidence, owner, policy version, verified revocation |

## 37. Tổng kết

**Phát hiện quyền thừa** là năng lực cốt lõi để thực thi **Least Privilege** trong IAM. Nó không dừng ở việc tìm role **Admin** hoặc những quyền “không thấy sử dụng”: cần **đối chiếu quyền kỳ vọng, đã cấp, thực sự có hiệu lực và hành vi được quan sát** theo **chủ thể, tài nguyên, hành động, tenant và thời điểm**. Cần kết hợp phát hiện **quyền vượt nhiệm vụ, đặc quyền thường trực, vi phạm SoD, quyền trực tiếp ngoài chuẩn, quyền không có owner và quyền tồn dư sau thay đổi nhân sự**.

Trong vòng đời **Joiner–Mover–Leaver**, **HRIS và nguồn bảo trợ** cho biết quan hệ làm việc; **IAM/IGA** tính quyền mục tiêu và phê duyệt; **IdP/SSO/MFA** đảm bảo xác thực; **SCIM** hỗ trợ User/Group provisioning; **RBAC/ABAC/PBAC** kiểm soát điều kiện cấp quyền; còn **PEP/resource server** quyết định hiệu lực thật. **Tài khoản dịch vụ và workload** cần đánh giá owner, quyền, secret và vòng đời riêng. Chỉ khi finding có **bằng chứng đáng tin, được xử lý theo rủi ro, đọc lại trạng thái tại target và kiểm thử quyền thực tế**, tổ chức mới giảm **quyền truy cập tồn dư** mà không làm mất những quyền nghiệp vụ còn hợp lệ.
