# Xử lý quyền thừa trong IAM: phát hiện, thu hồi và kiểm chứng truy cập hiệu lực

## 1. Bối cảnh, mục tiêu và phạm vi

**Quyền thừa** (*excessive privileges/excess access*) là những quyền một danh tính đang có nhưng **không còn cần thiết, không được phê duyệt hoặc vượt quá phạm vi công việc và chính sách hiện hành**. Một người có thể đăng nhập đúng danh tính nhưng vẫn được xem dữ liệu, thao tác hoặc quản trị hệ thống vượt nhu cầu. Đây là vấn đề **authorization** và **access governance**, không nhất thiết là lỗi xác thực.

Trong chương **IAM operations** của module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, xử lý quyền thừa là một công việc vận hành liên tục của quản lý **vòng đời danh tính** theo mô hình **Joiner–Mover–Leaver (JML)**. Quyền có thể thừa ngay từ lúc tạo tài khoản, tích lũy khi thay đổi vai trò hoặc tồn tại sau khi người dùng nghỉ việc. Bài học gắn việc xử lý quyền thừa với **Identity Provider (IdP), Single Sign-On (SSO), SCIM, RBAC/ABAC, tài khoản dịch vụ, quyền đặc quyền, kiểm toán và giảm quyền truy cập tồn dư**.

Một runbook tốt không kết thúc khi quản trị viên bấm “Remove role”. Nó kết thúc khi có thể chứng minh rằng:

1. Quyền hiện tại của chủ thể đã được đối chiếu với **quyền thực sự nên có** tại thời điểm đang xét.
2. Quyền trái chính sách hoặc không còn nhu cầu đã được thu hồi hoặc bị hạn chế bằng biện pháp có thẩm quyền.
3. Các đường truy cập khác như nhóm lồng nhau, quyền gán trực tiếp, tài khoản cục bộ, session/token, khóa API và đặc quyền tạm thời đã được kiểm tra.
4. Quyền cần thiết vẫn hoạt động đúng phạm vi, không gây mất quyền hợp lệ một cách không kiểm soát.
5. Ticket, quyết định, thao tác, kết quả kiểm chứng và ngoại lệ còn mở đều có bằng chứng để kiểm toán.

**Kết quả học tập:** người đọc biết xây dựng quy trình phát hiện excessive access, đánh giá mức độ rủi ro, phối hợp chủ sở hữu tài nguyên, thu hồi theo thứ tự an toàn, khôi phục khi thu hồi nhầm và đo hiệu quả giảm quyền tồn dư.

> **Lưu ý về chính sách:** Các ví dụ về mức ưu tiên, lịch rà soát, quy trình phê duyệt và thời hạn xử lý là minh họa. Trong hệ thống thật, cần áp dụng chính sách nội bộ, phân loại dữ liệu, yêu cầu pháp lý và khả năng kỹ thuật của từng nền tảng; không có một ngưỡng hoặc lệnh thu hồi chuẩn chung cho mọi IAM.

## 2. Định nghĩa quyền, quyền thừa và quyền truy cập hiệu lực

### 2.1. Những khái niệm dễ nhầm

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Identity** | Chủ thể có định danh ổn định thuộc người hoặc workload | Nhân viên `person-1042`, workload `svc-billing` |
| **Account** | Bản ghi tại IdP hoặc một ứng dụng, có thể không đồng nhất với identity | IdP user, tài khoản SaaS cục bộ |
| **Entitlement** | Quyền truy cập hoặc khả năng thực hiện hành động | `finance-read`, `repo-write`, admin |
| **Role (RBAC)** | Nhóm quyền gắn với nhiệm vụ/đơn vị | `support-agent` gồm đọc, cập nhật ticket trong phạm vi |
| **Attribute/Policy (ABAC)** | Điều kiện xác định quyền theo thuộc tính và ngữ cảnh | Chỉ xem hóa đơn thuộc đơn vị được duyệt |
| **Grant trực tiếp** | Quyền gán riêng cho một danh tính/tài khoản | User được owner gán `invoice-approve` ngoài nhóm |
| **Quyền kế thừa** | Quyền đến từ nhóm, role lồng nhau hoặc policy cấp cao | User trong nhóm A, A thuộc nhóm B có quyền admin |
| **Effective access** | Tập khả năng truy cập **thực tế** sau khi tổng hợp grant, policy, deny, ngữ cảnh và token/phiên | User vẫn xem được dữ liệu qua session cũ |
| **Desired state** | Tập quyền đúng cần tồn tại theo nguồn, vai trò, phê duyệt, thời điểm và chính sách | Finance reader tại đơn vị hiện tại |
| **Residual access** | Quyền truy cập tồn dư sau thay đổi hoặc kết thúc nhu cầu | Leaver còn API key hoặc role trong SaaS |
| **Orphan account** | Tài khoản không có chủ sở hữu/sponsor hợp lệ được đối chiếu | App account của nhà thầu đã hết hợp đồng |

**Quyền thừa** là sai lệch giữa **actual/effective access** với **desired access** đã được phê duyệt. Khác biệt không luôn hiện rõ ở danh sách nhóm IdP: một ứng dụng có thể cấp role trực tiếp, token có scope riêng hoặc policy phân quyền trên dữ liệu chi tiết.

### 2.2. Các dạng quyền thừa thường gặp

| Dạng quyền thừa | Tình huống | Vì sao khó phát hiện |
|---|---|---|
| **Role quá rộng** | Nhân viên chỉ cần đọc nhưng có quyền chỉnh sửa/xóa | Bộ role mặc định không tách đúng công việc |
| **Role cũ sau Mover** | Chuyển Finance nhưng vẫn có Support admin | Workflow chỉ cấp mới, không thu hồi cũ |
| **Grant trực tiếp ngoài IdP** | Owner ứng dụng cấp user riêng bằng giao diện | Không xuất hiện trong nhóm/role chuẩn ở IdP |
| **Nhóm lồng nhau** | Thành viên nhóm chung vô tình kế thừa quyền cao | Review chỉ nhìn nhóm cấp một |
| **Quyền tạm hết hạn** | Quyền hỗ trợ sự cố vẫn còn sau khi ticket đóng | Thiếu TTL hoặc công việc thu hồi không chạy |
| **Quyền SoD xung đột** | Một người vừa tạo vừa duyệt thanh toán | Từng role riêng có lý do nhưng kết hợp rủi ro |
| **Tài khoản Leaver còn hoạt động** | SSO chặn nhưng SaaS local login/API token còn | Nhiều đường xác thực không qua IdP |
| **Service account quyền quá rộng** | Job đọc báo cáo nhưng có quyền quản trị tenant | Workload grant được cấp để tránh lỗi ban đầu |
| **Dormant entitlement** | Quyền nhạy cảm tồn tại lâu dù ít hoặc không dùng | Không có telemetry hoặc use log chưa đầy đủ |
| **Break-glass/JIT không thu hồi** | Quyền khẩn cấp vẫn còn sau incident | Không có expiry/hậu kiểm hoặc cơ chế cưỡng chế |

**Quan trọng:** quyền không sử dụng trong một khoảng thời gian **không tự động chứng minh** nó thừa. Có quyền chỉ được dùng khi quyết toán, xử lý sự cố hoặc theo chu kỳ. Cần chủ sở hữu nghiệp vụ đánh giá nhu cầu, tần suất, tài liệu phê duyệt và khả năng thay thế trước khi thu hồi.

## 3. Quyền thừa phát sinh ở đâu trong kiến trúc IAM?

~~~mermaid
flowchart LR
    HR[HRIS / Nguồn nhà thầu] --> JML[Điều phối IAM JML]
    JML --> POLICY[RBAC / ABAC / SoD / Approval]
    POLICY --> IDP[IdP và Directory]
    POLICY --> SCIM[SCIM / API provisioning]
    IDP -->|OIDC / SAML SSO| APPS[Ứng dụng nghiệp vụ]
    SCIM --> APPS
    APPS --> LOCAL[Local role / direct grants]
    IDP --> PAM[PAM và quyền đặc quyền]
    JML --> WORKLOAD[Workload / Service identities]
    IDP --> AUDIT[Audit / SIEM]
    APPS --> AUDIT
    PAM --> AUDIT
    WORKLOAD --> AUDIT
    AUDIT --> RECON[Đối soát desired và actual]
    RECON --> JML
~~~

Luồng trên có nhiều mặt phẳng điều khiển:

- **Nguồn nhân sự/sponsor** xác nhận chủ thể, trạng thái quan hệ lao động, thời gian hiệu lực và đơn vị công việc.
- **Policy IAM** quyết định entitlement theo RBAC, ABAC, sự phê duyệt của owner, thời hạn và phân tách nhiệm vụ.
- **IdP/Directory** quản lý tài khoản, nhóm và xác thực tập trung. **SSO** chỉ chứng minh luồng đăng nhập; bản thân nó không bảo đảm mọi role phía ứng dụng đều chính xác.
- **SCIM/API** đồng bộ user, group hoặc trạng thái tới ứng dụng; vendor có thể có giới hạn và hành vi riêng. Request thành công chưa chứng minh mọi quyền hiệu lực đã thay đổi.
- **Ứng dụng đích** có thể giữ role cục bộ, policy tài nguyên, nested group, token/phiên hoặc API key độc lập.
- **PAM, cloud IAM và workload identity** có các grants/trust/credential riêng, không nhất thiết được bao phủ bởi HR–IdP–SCIM.
- **Audit/Reconciliation** giúp so sánh trạng thái phải có với trạng thái đích thực tế và truy trách nhiệm giải quyết sai lệch.

Một **MFA hoặc SSO login thành công** không đủ để xác định quyền đúng. Một **SCIM PATCH gỡ nhóm báo 200** cũng không đủ nếu session ứng dụng vẫn chứa claim có quyền cũ.

## 4. Nguyên tắc đánh giá: least privilege, SoD và vòng đời quyền

### 4.1. Least privilege và giới hạn phạm vi

**Least privilege** yêu cầu cấp đúng mức quyền để thực hiện nhiệm vụ, trên đúng tài nguyên, trong đúng thời gian. Không chỉ hỏi “có cần vào ứng dụng không?”, mà còn hỏi:

1. Chủ thể cần **hành động** gì: xem, tạo, cập nhật, xóa, phê duyệt, quản trị?
2. Trên **đối tượng** nào: toàn bộ tenant, một project, một bộ phận hay một tập dữ liệu?
3. Dựa vào **điều kiện** nào: thiết bị hợp lệ, network, location, môi trường, thời gian, loại dữ liệu?
4. Trong **thời hạn** nào: vĩnh viễn theo vai trò, tạm thời theo dự án hay chỉ khi JIT elevation?
5. **Ai phê duyệt** nhu cầu và ai có trách nhiệm rà soát?

Nếu một role “read-only” thực chất bao gồm quyền xuất hàng loạt dữ liệu nhạy cảm, tên role không phản ánh đúng rủi ro. Phải kiểm tra quyền hiệu lực và mục tiêu chính sách tại ứng dụng.

### 4.2. Separation of Duties (SoD)

**SoD** ngăn một chủ thể nắm các quyền có thể kết hợp để vượt kiểm soát nghiệp vụ, chẳng hạn tạo nhà cung cấp rồi tự phê duyệt thanh toán. Lỗi không phải lúc nào cũng là một role đơn lẻ quá rộng; có thể là **tổ hợp** hai role đều hợp lệ riêng lẻ.

Ví dụ:

| Quyền A | Quyền B | Nguy cơ kết hợp | Kiểm soát |
|---|---|---|---|
| Tạo yêu cầu chi | Duyệt yêu cầu chi | Tự tạo và tự duyệt | SoD rule, tách approver |
| Quản lý account | Sửa audit log | Khó truy vết thay đổi | Tách nhiệm vụ, ghi log bất biến |
| Deploy production | Tự phê duyệt change | Bỏ qua review thay đổi | Approval độc lập |
| Tạo tài khoản ứng dụng | Gán quyền admin | Self-elevation hoặc cấp cho người khác | PAM/dual control |

Ngoại lệ SoD cần phê duyệt của owner rủi ro, biện pháp bù trừ, giới hạn phạm vi và ngày hết hạn; không cho phép ngoại lệ vô thời hạn chỉ bằng một ghi chú trong ticket.

### 4.3. Mỗi grant nên có vòng đời

Một entitlement cần biết **nguồn cấp**, **căn cứ chính sách/phê duyệt**, **owner**, **thời điểm cấp**, **khi nào phải rà soát**, **điều kiện hết hạn** và **cơ chế thu hồi**. Nếu thiếu các trường này, quyền rất dễ trở thành quyền thừa khi người dùng chuyển vai trò hoặc khi ứng dụng thay owner.

## 5. Hợp đồng vận hành và dữ liệu đầu vào

### 5.1. Sự kiện kích hoạt xử lý quyền thừa

| Trigger | Ví dụ | Nguồn tham chiếu |
|---|---|---|
| **MOVER** | Nhân viên đổi phòng ban, promotion/demotion, chuyển dự án | HR/sponsor và approval quyền mới |
| **LEAVER** | Nhân viên nghỉ, nhà thầu kết thúc hợp đồng | Source lifecycle và thời điểm hiệu lực |
| **ACCESS_REVIEW** | Owner đánh dấu “Remove” hoặc phát hiện quyền chưa xác minh | Quyết định review và snapshot |
| **SoD violation** | Cùng subject có hai role xung đột | Policy SoD và đồ thị entitlement |
| **SECURITY_FINDING** | Phát hiện tài khoản có quyền admin bất thường | SOC/SIEM/PAM |
| **POLICY_CHANGE** | Quyền mặc định cũ bị thu hẹp | Phiên bản chính sách và kế hoạch migration |
| **PRIVILEGE_EXPIRATION** | Quyền JIT, break-glass hoặc quyền dự án hết hạn | TTL/grant record |
| **RECONCILIATION_DRIFT** | Actual state ở app khác desired state | Snapshot target và bộ điều phối |

### 5.2. Thông tin tối thiểu

Mỗi ticket cần nêu rõ: `ticket_id`, `subject_id` bất biến, loại danh tính, trạng thái JML tại thời điểm kiểm tra, ứng dụng/tài nguyên, entitlement và đường cấp quyền, loại sự kiện, `effective_at` có múi giờ, source/version, ảnh hưởng nghiệp vụ, owner, phê duyệt và bằng chứng trước/sau xử lý.

Không dùng duy nhất email hoặc tên hiển thị làm khóa vì email có thể đổi hoặc được cấp lại. Các định danh như IdP object ID, SCIM `externalId` và ID account đích cần được liên kết chắc chắn; nếu mapping mơ hồ, dừng thay đổi và xác minh.

### 5.3. RACI tham khảo

| Vai trò | Trách nhiệm |
|---|---|
| **HR / Nguồn chủ quản** | Xác nhận trạng thái nhân sự, nhà thầu, vai trò và thời điểm hiệu lực |
| **Quản lý/sponsor** | Xác nhận nhu cầu công việc và quyền nào có thể bỏ |
| **Chủ sở hữu ứng dụng/dữ liệu** | Quyết định phạm vi quyền hợp lệ, phê duyệt ngoại lệ hoặc kế hoạch thu hồi |
| **IAM Operations** | Tính chênh lệch, thực thi thu hồi, reconcile và giữ bằng chứng kỹ thuật |
| **Security/SOC/PAM** | Phân loại rủi ro, xử lý quyền đặc quyền và tình huống nghi xâm nhập |
| **Audit/Compliance** | Kiểm tra độc lập kết quả, nguồn phê duyệt và ngoại lệ còn tồn tại |

**Nguyên tắc trách nhiệm:** người có quyền không tự phê duyệt việc giữ quyền đặc quyền của chính mình. IAM thực thi quyền theo quyết định hợp lệ; với trường hợp rủi ro cao phải áp biện pháp containment theo quyền đã được thiết lập trong quy trình.

## 6. SOP-EP01 — Phát hiện và lập danh sách quyền thừa

**Trigger:** bất kỳ sự kiện nào trong mục 5.1. **Owner:** IAM Operations phối hợp owner tài nguyên. **Đầu ra:** tập entitlement nghi thừa có đường dẫn bằng chứng, độ nhạy và trạng thái xử lý.

1. **Xác nhận đối tượng:** kiểm tra subject ID, tài khoản IdP/app tương ứng, nguồn HR/sponsor và trạng thái JML hiện hành.
2. **Thu thập actual state:** lấy account enabled/disabled, nhóm trực tiếp, nhóm lồng nhau, role, policy, grant cục bộ, cloud grants, API key, service principal, quyền tài nguyên và quyền tạm thời.
3. **Đọc desired state:** lấy bản chính sách RBAC/ABAC đúng phiên bản, approved access requests, SoD rules, giới hạn dữ liệu và ngày hết hạn.
4. **Tính sai lệch:** xác định quyền có mặt ở actual nhưng vắng ở desired, role vượt mức cần thiết, quyền hết hạn, SoD conflict, orphan account và trạng thái Leaver chưa bị vô hiệu hóa.
5. **Xác định đường cấp quyền:** direct grant, group membership, inherited role, app-local, JIT/PAM hay token scope. Một quyền có thể có **nhiều đường cấp** nên gỡ một nhóm chưa chắc thu hồi được quyền.
6. **Thu thập use telemetry phù hợp:** hoạt động gần đây, các lần elevation, last access, tài nguyên sử dụng, chu kỳ công việc. Không suy quyền thừa chỉ từ không thấy usage.
7. **Gán mức rủi ro và owner:** theo độ nhạy dữ liệu, khả năng xóa/sửa, phạm vi tài nguyên, đặc quyền, trạng thái Leaver, SoD và mức ảnh hưởng khi gỡ.
8. **Tạo kế hoạch điều tra:** mỗi candidate có ID, nguồn, bằng chứng, tình trạng review, owner và deadline; không thay đổi nhầm quyền được phê duyệt khi dữ liệu còn mâu thuẫn.

### 6.1. Bảng so sánh desired–actual

| Thành phần | Desired state | Actual state | Kết luận ban đầu |
|---|---|---|---|
| Nhân sự Finance | `finance-reader` tại đơn vị A | `finance-reader` ở đơn vị A | Phù hợp |
| Nhân sự Finance | Không còn quyền Support | Vẫn có `support-editor` | Nghi quyền tồn dư sau Mover |
| Quyền phê duyệt | Chỉ Finance approver đã duyệt | Grant `invoice-approve-all` trực tiếp | Quyền thừa/nguy cơ SoD |
| Người đã nghỉ việc | Không đăng nhập được | IdP disabled, SaaS local user active | Deprovision chưa hoàn tất |
| Service account báo cáo | Read-only trên một bucket | Write + admin trên toàn project | Vượt phạm vi workload |

Đây mới là **danh sách cần kiểm tra**. Quyết định thu hồi cuối cùng phải xét owner, approval, quyền được dùng theo chu kỳ, ngoại lệ và ảnh hưởng sản xuất.

## 7. Tính quyền truy cập hiệu lực thay vì chỉ nhìn group

### 7.1. Vì sao actual state phức tạp?

Một chủ thể có thể nhận quyền từ nhiều đường:

~~~mermaid
flowchart TB
    USER[Identity / Account] --> DG[Direct Grant]
    USER --> G1[Nhóm A]
    G1 --> G2[Nhóm B lồng nhau]
    G2 --> ROLE[RBAC Role]
    USER --> APP[App-local Role]
    USER --> TEMP[PAM / JIT Grant]
    ROLE --> RESOURCE[Tài nguyên]
    DG --> RESOURCE
    APP --> RESOURCE
    TEMP --> RESOURCE
    POLICY[ABAC / Deny / Context] --> RESOURCE
    TOKEN[Session / Token Claims] --> RESOURCE
~~~

**Quyền hiệu lực** là kết quả thực tế sau khi áp chính sách của từng nền tảng. Không thể giả định một công thức chung như “union tất cả allow” nếu hệ thống có explicit deny, priority, policy boundary, điều kiện ngữ cảnh hoặc ràng buộc tài nguyên.

### 7.2. Cách kiểm tra quyền còn tồn tại

1. Xác định **tài nguyên và hành động** cần thu hồi, ví dụ `customer.export` trên dữ liệu phòng Support.
2. Truy các đường grant dẫn tới hành động đó: nhóm, role, policy, direct permission, inherited quyền ở project/organization và trust/assume-role nếu có.
3. Đọc quyết định authorization thực tế bằng policy simulator/audit hoặc phép thử được phép. Không dùng dữ liệu thật của người khác để “thử quyền” vượt phạm vi.
4. Kiểm tra **cơ chế session/token/cache**: role đã gỡ ở IAM nhưng access token hoặc session do ứng dụng phát trước đó có thể còn hiệu lực.
5. Nếu có nhiều đường cấp, phải gỡ **toàn bộ những đường không còn hợp lệ**; đừng kết luận chỉ bằng việc không còn thấy nhóm trong IdP.
6. Lưu snapshot trước và sau, phiên bản policy và cách kiểm chứng để auditor đối chiếu.

### 7.3. Quyền token khác với trạng thái directory

OIDC/OAuth 2.0 token, SAML assertion, cookie phiên, personal access token, refresh token và API key có thời hạn và cơ chế thu hồi khác nhau. Gỡ một RBAC role ở IdP không chắc làm token đã phát hành mất hiệu lực ngay. Với truy cập nhạy cảm hoặc Leaver, cần dùng phương thức revoke session/token ở đúng hệ thống hỗ trợ, cập nhật policy tại resource server hoặc chờ hết hạn có kiểm soát theo rủi ro và thiết kế.

**Không** nhầm token đã hết hạn với credential đã bị thu hồi; cũng không nhầm việc user không thể SSO lại với việc mọi API token độc lập đã bị vô hiệu hóa.

## 8. SOP-EP02 — Xác minh quyền thừa và phân loại rủi ro

**Mục tiêu:** xác định có thực sự thừa không, ảnh hưởng là gì và cần thu hồi khẩn hay xử lý theo kế hoạch.

### 8.1. Các câu hỏi xác minh

- **Nguồn quyền:** được cấp từ workflow IAM, trực tiếp ở app, quyền kế thừa hay phiên khẩn cấp?
- **Lý do ban đầu:** role cơ sở, công việc mới/cũ, dự án, ca trực, điều tra sự cố hay service dependency?
- **Phê duyệt hiện tại:** owner nào còn xác nhận nhu cầu? Có thời hạn/ngoại lệ rõ ràng không?
- **Tính hiệu lực:** quyền có thực sự cho phép truy cập, hay bị deny/ABAC giới hạn trong tình huống hiện tại?
- **Mức rủi ro:** dữ liệu nhạy cảm, quyền admin, xóa/sửa, SoD conflict, người đã nghỉ việc, tài khoản orphan?
- **Tác động thu hồi:** job, dịch vụ, vận hành cuối kỳ hay quy trình on-call có phụ thuộc quyền này không?
- **Cách thu hồi:** gỡ nhóm, role app, local grant, token, policy, service credential hoặc thay đổi owner?

### 8.2. Ví dụ phân loại ưu tiên

| Mức tham khảo | Tình huống | Xử lý |
|---|---|---|
| **P0** | Leaver còn quyền truy cập tài nguyên nhạy cảm hoặc account nghi bị chiếm quyền vẫn có admin | Chặn lối vào theo quy trình ứng phó, IAM/SOC xử lý phối hợp, xác minh độc lập |
| **P1** | Mover giữ quyền admin cũ trái SoD; token cá nhân của cựu nhà thầu còn dùng được | Ưu tiên thu hồi và kiểm tra đường truy cập khác |
| **P2** | Quyền ghi dữ liệu được cấp nhầm nhưng chưa ghi nhận lạm dụng và không có rủi ro tức thời cao | Chủ ứng dụng quyết định và thu hồi có kiểm thử |
| **P3** | Role read-only dư ít nhạy cảm phát hiện qua review, cần xác minh nhiệm vụ định kỳ | Đặt owner/deadline và thu hồi theo quy trình review |

Các mức này không phải quy tắc cố định. **Mức rủi ro** và **mức ưu tiên xử lý** chịu ảnh hưởng của quy mô, khả năng bị lạm dụng, điều kiện truy cập, thời gian phát hiện và tác động tới hệ thống.

### 8.3. Xác minh ngoại lệ có hợp lệ không

Một ngoại lệ chỉ nên được giữ khi có **mục đích cụ thể, phạm vi tối thiểu, người chấp nhận rủi ro, thời hạn hết hiệu lực, biện pháp bù trừ và lịch rà soát**. Ticket “để thuận tiện” hoặc approval cũ không có thời hạn không đủ để hợp thức hóa quyền admin đang tồn dư.

## 9. SOP-EP03 — Lên kế hoạch thu hồi và phê duyệt

### 9.1. Lập kế hoạch theo từng đường grant

1. Chọn entitlement/tài nguyên cần gỡ, target system, ID chính xác và nguyên nhân xử lý.
2. Liệt kê **tất cả đường cấp** dẫn đến quyền thừa: role trực tiếp, nhóm lồng nhau, policy kế thừa, local role, JIT grant, token và credential.
3. Đánh giá phụ thuộc nghiệp vụ, job và người dùng khác trước khi sửa **nhóm hoặc role dùng chung**. Gỡ quyền của một nhóm có thể ảnh hưởng cả trăm người.
4. Đặt trình tự thu hồi: quyền nhạy cảm, quyền trực tiếp, quyền kế thừa, session/token và xác minh. Với Leaver/compromise, ưu tiên chặn truy cập trước.
5. Chọn người phê duyệt theo policy: manager, chủ sở hữu dữ liệu, application owner, PAM/SOC khi đặc quyền, HR khi trạng thái nhân sự có tranh chấp.
6. Chuẩn bị kiểm chứng: GET actual state, policy evaluation, sign-in/audit logs hoặc phép thử truy cập âm tính có quyền phù hợp.
7. Lập phương án phục hồi nếu thu hồi nhầm: khôi phục **chính xác grant hợp lệ** sau phê duyệt, không tự hoàn tác toàn bộ snapshot role cũ.

### 9.2. Phân biệt hành động khẩn và thay đổi theo lịch

Với **nguy cơ truy cập trái phép đang xảy ra**, SOC/IAM có thể kích hoạt quy trình containment đã được ủy quyền: disable account, revoke credential/session, gỡ quyền admin trực tiếp tại đích. Với **quyền thừa chưa có dấu hiệu lạm dụng**, lên lịch thay đổi có owner, thông báo tác động và xác minh nghiệp vụ.

Không để phê duyệt kéo dài vô hạn khi Leaver còn quyền truy cập. Trường hợp owner ứng dụng không đáp ứng, áp escalation và biện pháp hạn chế rủi ro được quy định, đồng thời ghi rõ target chưa xử lý.

## 10. SOP-EP04 — Thu hồi quyền có kiểm soát

**Trigger:** quyền thừa đã được xác nhận hoặc có lệnh containment hợp lệ. **Owner:** IAM Operations, chủ ứng dụng hoặc PAM theo phạm vi. **Điều kiện đóng:** trạng thái đích và quyền hiệu lực được xác minh.

### 10.1. Trình tự chuẩn

1. **Chụp hiện trạng:** lưu danh sách grants liên quan, role, nhóm, tài nguyên, trạng thái account, session/token và phiên bản policy; không lưu bí mật thô.
2. **Kiểm tra lại thời điểm thực thi:** xác nhận chủ thể, trạng thái JML mới nhất, ticket và phê duyệt còn hiệu lực. Tránh xử lý Mover cũ ghi đè Leaver mới.
3. **Thu hồi đúng phạm vi:** gỡ direct grant, membership, role, entitlement hay policy binding **đúng resource**, tránh sửa quyền dùng chung ngoài kế hoạch.
4. **Đồng bộ IdP/SCIM/API:** xử lý thông qua source of truth và connector; nếu thao tác thủ công tại ứng dụng do sự cố connector, ghi ngoại lệ và đảm bảo reconciliation không tự cấp lại quyền.
5. **Xử lý session/token:** với quyền rủi ro cao hoặc khi policy yêu cầu hiệu lực ngay, thu hồi session/refresh token/API key hoặc thay đổi quyết định phía resource server theo khả năng đích.
6. **Kiểm tra mọi đường cấp còn lại:** nested group, inherited role, local privilege, PAM elevation, service principal và API key; đặc biệt với user Leaver và quyền đặc quyền.
7. **Đối chiếu actual–desired:** đọc lại target và kiểm chứng người dùng **không còn thực hiện được hành động bị thu hồi**, đồng thời quyền hợp lệ còn hoạt động.
8. **Lưu evidence:** request/event ID, người thao tác, phản hồi API, thời điểm, verification result, owner và ngoại lệ chưa xử lý.
9. **Giám sát sau thay đổi:** phát hiện retry job cũ tự cấp lại role, sync drift, truy cập thất bại ảnh hưởng nghiệp vụ và session tồn dư.

### 10.2. Các mức kết quả khác nhau

| Mốc | Ý nghĩa | Có đủ để đóng? |
|---|---|---|
| `REQUESTED` | Chủ sở hữu đã yêu cầu remove | Chưa |
| `APPROVED` | Quyết định thu hồi được phê duyệt | Chưa |
| `APPLIED` | Connector/API báo đã gỡ grant | Chưa chắc |
| `VERIFIED_STATE` | Resource đích không còn grant sai và đồng bộ phù hợp | Cần kiểm tra effective access khi thích hợp |
| `VERIFIED_EFFECTIVE` | Hành động bị thu hồi không còn được phép, quyền hợp lệ giữ nguyên | Có thể đóng target theo chính sách |
| `EXCEPTION_OPEN` | Còn đường grant, token hoặc đích chưa xác minh | Không báo đã thu hồi toàn bộ |

Không coi `200 OK` hay `204 No Content` từ SCIM là bằng chứng rằng phiên trước đó bị hủy ngay; việc thu hồi phiên tùy cơ chế ứng dụng.

### 10.3. Minh họa thao tác SCIM gỡ nhóm

~~~http
PATCH /scim/v2/Groups/group-84 HTTP/1.1
Authorization: Bearer [REDACTED]
Content-Type: application/scim+json

{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:PatchOp"
  ],
  "Operations": [
    {
      "op": "remove",
      "path": "members[value eq \"target-user-42\"]"
    }
  ]
}
~~~

Đây là **ví dụ tham khảo SCIM 2.0**, không phải lời khuyên chạy trực tiếp trên môi trường thật. Thực tế phải xác minh `group_id`, `target_user_id`, filter/path được vendor hỗ trợ, quyền connector và tác động tới những thành viên khác. Sau thao tác cần đọc lại group, role và quyền hiệu lực của user tại ứng dụng; nếu ứng dụng dùng quyền kế thừa hoặc giữ session cũ thì việc xóa membership chưa chắc đủ.

## 11. Xử lý quyền thừa trong từng pha Joiner–Mover–Leaver

### 11.1. Joiner — ngăn overprovisioning từ đầu

Quyền thừa có thể hình thành ngay khi tạo danh tính nếu role nền quá rộng, hệ thống dùng template cũ hoặc workflow gán mặc định quyền admin để tránh lỗi onboarding.

**Runbook:**

1. Xác thực Joiner, người bảo trợ, ngày bắt đầu, đơn vị và job code từ nguồn có thẩm quyền.
2. Tính baseline RBAC/ABAC và kiểm tra SoD; các quyền ngoài baseline cần approval riêng.
3. Kiểm tra SCIM/IdP/ứng dụng không gán role mặc định quá rộng; tránh Just-in-Time provisioning tạo account có quyền rộng hơn yêu cầu.
4. So sánh actual với desired ở từng app và phát hiện direct grant không nằm trong request.
5. Nếu thừa, thu hồi trước khi bàn giao truy cập nhạy cảm; xác minh lại tính phù hợp của role.

**Ví dụ:** nhân viên kiểm thử được tạo account SaaS với role `tenant-admin` mặc định, trong khi nhiệm vụ chỉ cần `project-read`. Lỗi nằm ở template/role mapping của app; sửa provisioning rule tại nguồn và thu hồi admin ở account đã tạo, đồng thời quét các Joiner trước đó dùng cùng template.

### 11.2. Mover — nguy cơ tích lũy quyền cao nhất

Mover thay đổi bộ phận, cấp bậc, dự án, địa điểm hoặc nhiệm vụ. Nhiều hệ thống tự động **thêm quyền mới** nhưng không tự xóa quyền cũ hoặc có giai đoạn chuyển tiếp không được giới hạn.

**Runbook:**

1. Chụp entitlement trước thay đổi gồm direct, inherited, app-local, PAM, API token và quyền tạm.
2. Xác định role/thuộc tính **cũ → mới**, ngày hiệu lực, approval mới và điều kiện SoD.
3. Chia thành `KEEP`, `REVOKE`, `GRANT`, `REVIEW`; tránh sao chép toàn bộ quyền cũ sang vai trò mới.
4. Thu hồi các grant cũ không còn hợp lệ, ưu tiên những quyền có rủi ro cao hoặc xung đột với role mới.
5. Cấp quyền mới đã được duyệt; nếu cần thời gian chuyển giao hai role, phải có owner, hạn kết thúc và giám sát.
6. Xử lý claim/token/session nếu role cũ còn hiệu lực tại ứng dụng.
7. Đối chiếu cả quyền **đã thêm** và quyền **đã gỡ**, kiểm tra SoD sau thay đổi.

**Ví dụ:** nhân viên chuyển từ Support sang Finance. Workflow thêm `finance-reader` thành công nhưng vẫn để `support-editor` và quyền xuất dữ liệu khách hàng. Đây là **Mover chưa hoàn tất**, dù nhân viên vào được ứng dụng Finance.

### 11.3. Leaver — quyền nào còn lại đều cần điều tra

Khi HR/sponsor xác nhận người nghỉ việc hoặc nhà thầu hết hạn, mục tiêu là ngăn truy cập theo thời điểm hiệu lực, không chỉ gỡ nhóm. Tài khoản Leaver có thể còn:

- Phiên SSO hoặc session tại SaaS đang sống.
- Local account không phụ thuộc IdP.
- API key, SSH key, personal access token, refresh token hoặc OAuth consent.
- Cloud role, PAM elevation, repository permissions, quyền owner và delegation.
- Quyền ở ứng dụng không hỗ trợ SCIM/deprovision tự động.

**Runbook Leaver:** xác minh sự kiện đúng người/đúng giờ → chặn IdP/SSO/VPN/PAM → thu hồi phiên và credential độc lập → gỡ grants tại ứng dụng → đối soát mọi target → lưu evidence và xử lý ngoại lệ. Với Leaver khẩn cấp, dùng đường chặn trực tiếp tại ứng dụng nếu connector đang lỗi; không chờ SCIM hồi phục mới xử lý lối vào khác. Dữ liệu cần giữ theo pháp lý/chính sách phải được bàn giao đúng người, không giữ account Leaver active chỉ để truy xuất dữ liệu.

### 11.4. Reactivation và tái tuyển dụng

Khi nhân viên trở lại, không tự khôi phục mọi quyền lịch sử chỉ vì account đã từng tồn tại. Phải xác minh quan hệ lao động mới, owner, role, ngày hiệu lực và approval hiện hành. Quyền cũ có thể đã hết hạn, vi phạm SoD hoặc không phù hợp với nhiệm vụ mới.

## 12. RBAC, ABAC và cách sửa thiết kế tạo ra quyền thừa

### 12.1. RBAC: sửa role thay vì gỡ tay lặp đi lặp lại

Nếu nhiều người liên tục xuất hiện cùng một quyền dư, nguyên nhân thường là **role design**: role quá rộng, lồng nhóm sai, catalog không có role đọc/ghi riêng hoặc role cũ không được retirement.

**Ví dụ phân tách role:**

| Role ban đầu | Vấn đề | Thiết kế phù hợp hơn |
|---|---|---|
| `finance-staff` có đọc, sửa và duyệt toàn bộ hóa đơn | Quá rộng và SoD xung đột | `finance-reader`, `invoice-editor`, `invoice-approver` với phê duyệt độc lập |
| `support-all` có quyền xuất tất cả dữ liệu khách hàng | Không giới hạn phạm vi | `support-case-reader` theo team và điều kiện xuất dữ liệu riêng |
| `dev-admin` dùng cho build thông thường | Gồm quyền production không cần thiết | Role build/deploy tách môi trường và JIT admin |

Việc đổi role catalog phải theo **change management**: inventory người đang dùng, đánh giá ảnh hưởng, canary, version policy, thông báo owner và kiểm chứng sau rollout. Không âm thầm chỉnh role dùng chung nếu có thể làm mất quyền hợp lệ của nhiều người.

### 12.2. ABAC: giới hạn đúng đối tượng và ngữ cảnh

ABAC có thể thu hẹp quyền theo department, project, data classification, location, device posture và thời gian. Tuy nhiên thuộc tính sai hoặc stale cũng gây cấp quyền rộng. Chẳng hạn một policy cho `department = any` hoặc một thuộc tính group được đồng bộ sai có thể tạo phạm vi truy cập lớn hơn role gợi ý.

Kiểm tra:

1. Thuộc tính từ nguồn nào, có được xác minh và cập nhật đúng phiên bản không?
2. Điều kiện `allow` có giới hạn hành động/tài nguyên theo nhu cầu không?
3. Quy tắc `deny`, policy boundary, precedence có hoạt động theo semantics của nền tảng không?
4. Session/token chứa claim cũ có tiếp tục cho phép truy cập không?
5. Phép thử cho trường hợp **được phép** và **không được phép** đã bao phủ tài nguyên nhạy cảm chưa?

Không dùng ABAC như một lời bảo đảm chung rằng “mọi quyền đều được giới hạn”; phải kiểm thử policy cụ thể ở nơi thực thi authorization.

### 12.3. Phân biệt sửa policy với sửa từng tài khoản

- **Quyền chỉ sai ở một tài khoản:** điều tra direct grant, exception hoặc mapping.
- **Quyền sai ở cả role/nhóm:** sửa catalog/policy và đánh giá phạm vi tác động.
- **Quyền sai do dữ liệu nguồn:** HR/sponsor hoặc owner thuộc tính phải sửa authoritative record.
- **Quyền app không khớp IdP:** kiểm tra SCIM/API và quyền cục bộ, sau đó reconcile.
- **Quyền bị cấp lại sau khi gỡ:** tìm job provisioning/retry, template hoặc policy còn cho phép grant.

## 13. SCIM/API, đồng bộ và lỗi thu hồi quyền

SCIM thường hỗ trợ đồng bộ user/group; nhưng không bảo đảm mọi entitlement ứng dụng đều được biểu diễn qua SCIM. Một SaaS có thể duy trì role riêng không nằm trong group SCIM hoặc chỉ đồng bộ theo chu kỳ.

| Tín hiệu | Khả năng nguyên nhân | Biện pháp |
|---|---|---|
| API 401/403 | Connector credential hết hạn hoặc thiếu scope | Sửa tại vault/config theo owner; không tăng quyền rộng tùy tiện |
| API 404 | Mapping user/group sai, resource đã đổi ID | Đối chiếu ID bất biến và actual state |
| API 409 | Conflict hoặc trùng định danh | Không tự gộp theo email; xác minh owner |
| API 412 | Resource/version đã đổi | Đọc lại ETag/version rồi tính diff mới nếu có hỗ trợ |
| API 429 | Rate limit | Tôn trọng `Retry-After`, backoff có jitter và ưu tiên revoke rủi ro |
| API 5xx/timeout | Lỗi tạm hoặc kết quả chưa rõ | Readback trước retry; thao tác idempotent |
| API 2xx nhưng quyền còn | Async job, cache, direct grant hoặc role ngoài SCIM | Reconcile actual và quyền hiệu lực, xử lý grant còn lại |
| Quyền bị cấp lại | Source policy/connector cũ đang “desired = allow” | Sửa nguồn hoặc workflow và version guard |

**Không giả định một phép PATCH nhóm tương đương revoke quyền tức thì.** Cần kiểm tra scope SCIM của ứng dụng, role mapping và session/token. Với app chỉ xử lý thủ công, mở việc cho application owner, có SLA/owner/bằng chứng và theo dõi đến khi hoàn tất.

### 13.1. Event ordering và idempotency

Trong quy trình JML, sự kiện có thể đến trễ, trùng hoặc sai thứ tự. Nếu một job Mover cũ retry sau khi HR phát Leaver, hệ thống có thể cấp lại nhóm cũ cho người đã nghỉ. Mỗi thao tác cần gắn `event_id`, `subject_id`, `source_version`, `target_id`; trước khi áp thay đổi, kiểm tra lifecycle mới nhất. Cần đảm bảo job cấp quyền cũ **không được phép** ghi đè trạng thái Terminated và job thu hồi không bị xếp sau các job cấp quyền không còn hợp lệ.

## 14. Tài khoản đặc quyền, JIT/PAM và break-glass

Quyền đặc quyền có ảnh hưởng rộng và thường là trọng tâm của excessive access. Ví dụ:

- Tenant/global admin được gán vĩnh viễn cho người chỉ cần sửa một ứng dụng.
- Cloud IAM policy cho phép `*` actions trên `*` resources dù job chỉ cần đọc một bucket.
- Production access của kỹ sư vẫn còn sau khi hoàn tất hỗ trợ sự cố.
- Quyền break-glass tồn tại sau khi incident đã đóng.
- Tài khoản admin dùng chung không cho phép quy trách nhiệm cá nhân.

### 14.1. Quy trình xử lý

1. Xác định quyền thực tế và các đường elevation: standing role, nested group, assume-role, PAM/JIT, trust và token.
2. Đánh giá hành động/đối tượng cần thiết, tần suất, phê duyệt và điều kiện khẩn cấp.
3. Ưu tiên **quyền có thời hạn**, phê duyệt khi sử dụng và giám sát hành động; giảm standing privilege khi hệ thống hỗ trợ.
4. Thu hồi quyền admin dư, kiểm tra session còn sống và các credential đã cấp; rotate secret nếu đánh giá rủi ro chỉ ra cần thiết.
5. Kiểm tra SoD, phê duyệt chéo và khả năng truy vết qua log PAM/cloud.
6. Với break-glass, rà soát hậu sự kiện, kết thúc grant tạm, xoay credential khi chính sách yêu cầu và chứng minh không còn bypass.

**Không tắt tài khoản break-glass thiết yếu mà chưa xét mô hình khả dụng khẩn cấp của tổ chức.** Thay vào đó, xác minh tài khoản đúng số lượng, owner, bảo vệ bí mật, điều kiện kích hoạt, giám sát và quyền tối thiểu theo thiết kế đã duyệt.

## 15. Service account, workload identity và tài khoản không phải con người

Tài khoản dịch vụ không có vòng đời nhân sự giống người dùng, nhưng vẫn cần **lifecycle của workload**: tạo, gán owner, cấp quyền, rotate credential, thay đổi ứng dụng/owner và decommission. Nhiều trường hợp service account có quyền thừa vì người vận hành cấp admin để giải quyết lỗi tích hợp ban đầu.

### 15.1. SOP xử lý quyền thừa của service identity

1. Kiểm tra **owner kỹ thuật và owner nghiệp vụ**, service dependency, môi trường, dữ liệu và yêu cầu hoạt động.
2. Liệt kê API scopes, IAM policies, trust relationships, resource grants, secret/token, role delegation và môi trường được phép sử dụng.
3. Xác định hành động thực tế của workload qua log có độ tin cậy phù hợp, kết hợp tài liệu thiết kế và owner; không lấy “chưa thấy sử dụng” làm lý do duy nhất để xóa.
4. Đề xuất thu hẹp policy theo **action, resource, environment và thời gian**; phân tách môi trường dev/test/prod nếu đang dùng chung.
5. Thử trên môi trường kiểm thử/canary khi có thể; lập kế hoạch thay đổi an toàn cho production.
6. Thu hồi grant thừa và credential cũ qua vault/cloud IAM đúng owner; giám sát lỗi job, quyền bị từ chối và sự cố ngoài dự kiến.
7. Nếu workload đã ngừng, xác minh không còn dependency rồi disable identity, role/trust, secret và key; lưu evidence.

### 15.2. Ưu tiên credential ngắn hạn

Managed identity, workload federation hoặc credential ngắn hạn có thể giảm sự phụ thuộc vào khóa tĩnh. Tuy nhiên bản thân workload identity **vẫn có thể bị cấp quá quyền**: cần review policy, resource scope, trust và owner. Đổi từ secret tĩnh sang managed identity không thay thế việc kiểm soát least privilege.

### 15.3. Khi nhân viên tạo workload đã nghỉ việc

Không mặc định xóa service account đang vận hành production, nhưng cũng không để nhân viên cũ tiếp tục giữ quyền chủ sở hữu hoặc key cá nhân. Chuyển owner theo phê duyệt, kiểm tra dependency, rotate credential khi phù hợp, thu hồi quyền cá nhân và làm sạch quyền grant cũ không còn hợp lệ.

## 16. Thu hồi nhầm quyền, ngoại lệ và biện pháp phục hồi

### 16.1. Vì sao cần phương án phục hồi?

Thu hồi một quyền có thể làm batch job, báo cáo cuối kỳ, kết nối hệ thống hoặc nhiệm vụ on-call thất bại. Điều này không phải lý do để giữ quyền rộng mãi, nhưng yêu cầu điều tra dependency và xác minh tác động trước khi thay đổi (trừ tình huống phải containment khẩn cấp).

**Ví dụ:** role `reporting-admin` của nhân viên kế toán chứa cả quyền đọc báo cáo cuối tháng và quyền quản trị user. Nếu gỡ toàn bộ role đúng ngày chốt sổ, nghiệp vụ có thể gián đoạn. Phương án tốt hơn là tách `report-reader` khỏi admin, phê duyệt role hẹp, thử truy cập rồi thu hồi `reporting-admin`.

### 16.2. SOP xử lý khi thu hồi ảnh hưởng quyền hợp lệ

1. Thu thập error ID, thời gian, resource và hành động bị từ chối; xác định lỗi thật sự do thu hồi hay do sự cố khác.
2. Đối chiếu ticket và desired state mới nhất, hỏi owner nghiệp vụ về nhu cầu thực tế.
3. Nếu quyền cần giữ đã bị gỡ nhầm, cấp lại **chính xác quyền tối thiểu được phê duyệt**, có thời hạn khi phù hợp.
4. Nếu quyền cũ quá rộng, tạo role hẹp hoặc ABAC đúng phạm vi thay vì phục hồi toàn bộ admin.
5. Kiểm thử lại luồng nghiệp vụ được phép và hành động không được phép; ghi chi tiết thay đổi và người duyệt.
6. Bổ sung dependency vào role catalog và quy trình change để tránh lặp.

**Không tự động rollback mọi thay đổi** khi một app báo lỗi; đặc biệt không được tái cấp quyền cũ cho Leaver, người đang bị security hold hoặc Mover có SoD conflict.

### 16.3. Ngoại lệ thu hồi chưa hoàn tất

Trường hợp ứng dụng lỗi SCIM, không hỗ trợ API hoặc chủ ứng dụng chưa xác nhận, ghi `EXCEPTION_OPEN` kèm: quyền còn tồn tại, mức độ rủi ro, owner, thời hạn, biện pháp giảm thiểu, bằng chứng, cách kiểm tra lại và escalation. Báo cáo cần phân biệt **đã gửi lệnh**, **đã thực hiện** và **đã kiểm chứng**.

## 17. Pseudocode phát hiện và xử lý excessive access

Pseudocode dưới là khung tư duy cho reconciliation engine. Nó **không phải mã chạy trực tiếp** trên IdP hay ứng dụng.

~~~text
reconcile_excess_access(subject_id, target_id):
    lifecycle = read_authoritative_lifecycle(subject_id)
    mapping = resolve_identity_mapping(subject_id, target_id)
    if mapping.ambiguous:
        open_exception("IDENTITY_MAPPING_UNCERTAIN")
        return

    source_version = lifecycle.version
    desired = evaluate_policy(
        lifecycle, approvals, role_catalog, attributes, sod_rules
    )
    actual = read_target_access(
        target_id, mapping, include_direct_and_inherited=True
    )
    effective = evaluate_effective_access(
        target_id, mapping, actual, known_sessions_and_tokens
    )

    candidates = find_excess_and_conflicting_grants(
        actual, effective, desired
    )
    for grant in candidates:
        risk = classify_risk(grant, lifecycle, data_classification)
        decision = request_authorized_review(grant, risk)

        if decision == "APPROVED_EXCEPTION":
            enforce_expiry_scope_and_compensating_controls(grant)
            continue

        if decision == "REVOKE":
            if lifecycle.version != read_latest_lifecycle(subject_id).version:
                restart_reconciliation_from_latest_state()
                return

            apply_scoped_revocation_idempotently(grant)
            revoke_related_sessions_when_required(grant, risk)
            verify_actual_and_effective_access(target_id, desired)
            record_audit_with_evidence(grant, risk)
        else:
            keep_open_with_owner_deadline(grant)
~~~

**Điểm kỹ thuật cần có khi triển khai:**

- **Idempotency:** chạy lại một ticket không làm thay đổi sai đối tượng hoặc tái cấp quyền.
- **Version guard:** sự kiện Mover/Joiner cũ không ghi đè trạng thái Leaver mới.
- **Source of truth:** HR/sponsor xác nhận lifecycle; IAM policy và application owner xác nhận entitlement; target xác nhận actual.
- **Retry có giới hạn:** API timeout có thể đã thực thi, nên đọc lại trạng thái trước khi gửi lại; tôn trọng rate limit.
- **Target-level evidence:** mỗi app/tài nguyên phải có kết quả kiểm chứng riêng.
- **Privacy:** chỉ lưu tham chiếu log, không đưa mật khẩu, session cookie, access token hoặc thông tin nhân sự nhạy cảm vào ticket.
- **Phê duyệt độc lập:** automation có thể đề xuất candidate, nhưng trường hợp nhạy cảm và ngoại lệ phải theo chính sách phân quyền quyết định.

## 18. Audit, chỉ số và tiêu chí đóng ticket

### 18.1. Chỉ số nên theo dõi

| Metric | Ý nghĩa |
|---|---|
| **Excess entitlement count** | Số grant ngoài desired, chia theo quyền đọc/ghi/admin và chủ thể |
| **Age of excess privilege** | Thời gian quyền thừa tồn tại sau khi không còn hợp lệ |
| **Residual access after Mover/Leaver** | Số trường hợp vẫn có quyền thực tế sau thời điểm thay đổi vòng đời |
| **Time to verified revocation** | Từ phát hiện/thời điểm có hiệu lực đến lúc target được xác minh đã thu hồi |
| **Direct grant outside catalog** | Quyền gán trực tiếp không đi qua role/phê duyệt chuẩn |
| **SoD conflicts** | Số tổ hợp role vi phạm phân tách nhiệm vụ |
| **Privileged standing access** | Số grant admin thường trực thay vì JIT/thời hạn |
| **Orphan/service identity without owner** | Tài khoản không có sponsor/owner đủ thẩm quyền |
| **Exception overdue** | Ngoại lệ đã quá hạn nhưng quyền vẫn còn |
| **Regrant recurrence** | Quyền bị gỡ nhưng hệ thống khác cấp lại do mapping/retry cũ |
| **Access review verified closure** | Quyết định review đã thực thi và **verified**, không chỉ được đánh dấu Remove |

Chỉ số cần tách **quyền đang chờ owner quyết định**, **quyền đã phê duyệt thu hồi**, **quyền đã áp thao tác**, **quyền đã verified**. Một tỷ lệ “đã hoàn thành review” cao không có ý nghĩa nếu ứng dụng vẫn giữ các grant.

### 18.2. Mẫu audit record

~~~yaml
ticket_id: IAM-EXCESS-EXAMPLE-045
subject_id: person-1042
lifecycle_event: MOVER
source_system: HRIS
source_version: 18
effective_at: "2026-11-24T09:00:00+07:00"
target_system: support-app
resource_ref: support-project-a
entitlement: support-editor
grant_paths:
  - group:support-base
  - app-direct-role:support-editor
desired_state_ref: desired-access-045
actual_before_ref: actual-access-before-045
owner_decision_ref: app-owner-approval-045
risk_category: STALE_MOVER_PRIVILEGE
remediation:
  actions:
    - remove-group-membership
    - revoke-app-direct-role
    - revoke-app-session-if-required
  operator_ref: iam-operator-09
  executed_at: "2026-11-24T09:05:00+07:00"
verification:
  actual_after_ref: actual-access-after-045
  access_to_revoked_resource: DENIED
  authorized_finance_access: VERIFIED
  evidence_ref: access-check-045
exceptions: []
status: VERIFIED
~~~

Đây là dữ liệu **giả lập**; trong hệ thống thật phải lưu evidence liên kết với ticket/approval/policy version, đối tượng, hành động, API result, readback và kết quả xác minh quyền hiệu lực. Không lưu token, password, secret hay PII không cần thiết. Audit và retention phải tuân thủ chính sách riêng tư.

### 18.3. Tiêu chí đóng sự cố

- Đã đối chiếu đúng chủ thể, lifecycle mới nhất và mọi tài khoản/đích liên quan.
- Quyền thừa được chủ tài nguyên xác nhận, SoD và approval hợp lệ đã được kiểm tra.
- Tất cả đường cấp grant không hợp lệ đã gỡ hoặc chặn theo chính sách.
- Session/token, cloud policy, PAM, local role và service identity được kiểm tra khi liên quan.
- Trạng thái actual và quyền hiệu lực được kiểm chứng; quyền hợp lệ còn hoạt động đúng phạm vi.
- Bằng chứng có owner, timestamp, request ID; ngoại lệ còn mở có deadline và biện pháp kiểm soát.
- Không có job/policy cũ tự tái cấp quyền đã thu hồi trong khoảng giám sát phù hợp.

## 19. Các tình huống luyện tập

### Tình huống A — Mover vẫn có quyền chỉnh sửa ở bộ phận cũ

Một nhân viên chuyển từ Support sang Finance. IdP đã thêm `finance-reader` nhưng vẫn giữ `support-editor`; ở ứng dụng Support còn một direct grant. Người dùng đăng nhập SSO bình thường và có thể sửa ticket Support.

**Cách xử lý:** dùng sự kiện Mover mới nhất để tính desired, xác định cả group grant và direct grant, thu hồi theo owner, xử lý session nếu cần, xác minh thao tác sửa ticket bị từ chối trong khi quyền đọc Finance vẫn hợp lệ. Kiểm tra nguyên nhân quy trình Mover chỉ thêm role mới.

### Tình huống B — Leaver bị disable IdP nhưng API key còn chạy

Nhà thầu kết thúc hợp đồng. IdP disabled, nhưng API key cá nhân vẫn tải được dữ liệu từ SaaS.

**Cách xử lý:** coi đây là deprovisioning còn tồn dư, ưu tiên revoke API key tại SaaS, kiểm tra local login/session, role và owner; ghi evidence request bị từ chối sau revoke. Không đánh dấu Leaver đã hoàn tất chỉ dựa vào trạng thái IdP.

### Tình huống C — Nhân viên kế toán có hai quyền xung đột

Một nhân viên được cấp `invoice-create` và `invoice-approve` cho cùng phạm vi dữ liệu. Mỗi grant riêng lẻ đều từng có approval, nhưng tổ hợp vi phạm SoD.

**Cách xử lý:** xác nhận rule và scope, tham vấn owner nghiệp vụ, tách nhiệm vụ hoặc thu hồi một grant, đặt quy trình approval độc lập. Nếu tổ chức cho phép ngoại lệ tạm, yêu cầu owner rủi ro, hạn hết và biện pháp bù trừ có thể kiểm toán.

### Tình huống D — Quyền admin của workload trên toàn cloud project

Service account của một job chỉ đọc báo cáo nhưng có `project-admin` trên cả môi trường production.

**Cách xử lý:** xác định dependency, action thực tế và owner; thiết kế role read-only đúng resource, thử trên môi trường/canary, thu hồi admin và xác minh job còn chạy đúng. Rà các service account khác tạo từ cùng template. Không dùng inactivity đơn thuần để kết luận có thể xóa account.

### Tình huống E — SCIM báo gỡ nhóm thành công nhưng user vẫn truy cập

Connector trả 204 sau PATCH gỡ nhóm. Ứng dụng vẫn cho xuất dữ liệu qua role gán trực tiếp và session cũ.

**Cách xử lý:** phân biệt APPLIED với VERIFIED. Đối chiếu app-local role, role kế thừa và token/session; gỡ tất cả đường cấp không còn hợp lệ, thực hiện revoke session theo khả năng, xác minh thao tác xuất dữ liệu bị deny.

### Tình huống F — Quyền JIT admin còn sau incident

Một kỹ sư dùng PAM/JIT để sửa sự cố production. Incident đã đóng nhưng policy grant không có TTL và tài khoản vẫn được nâng quyền.

**Cách xử lý:** kết thúc quyền nâng cấp, kiểm tra phiên đặc quyền, giám sát log hành động và hậu kiểm break-glass/JIT. Sửa cấu hình expiry và quy trình đóng incident để bảo đảm grants có thời hạn.

### Tình huống G — Quyền vừa bị thu hồi đã tự xuất hiện lại

Owner gỡ role cũ tại ứng dụng nhưng sau vài phút connector IAM lại cấp lại vì catalog RBAC vẫn tính role đó là desired.

**Cách xử lý:** không tiếp tục gỡ thủ công vô hạn. Điều tra source/role mapping, event version, override và policy hiện hành; sửa desired state với owner, reconcile lại và theo dõi để chứng minh không còn regrant.

## 20. Checklist cuối cùng và nguyên tắc cần nhớ

| Giai đoạn | Câu hỏi nghiệm thu |
|---|---|
| **Identify** | Đã xác minh subject, owner, JML state và nguồn grant? |
| **Inventory** | Đã xét direct, inherited, local, token, PAM và workload grants? |
| **Desired state** | Có policy RBAC/ABAC, SoD, approval và thời hạn hợp lệ? |
| **Risk** | Đã phân loại quyền nhạy cảm, dữ liệu, SoD và tác động sản xuất? |
| **Decision** | Owner có thẩm quyền đã xác nhận revoke/retain/exception? |
| **Plan** | Có thứ tự thu hồi, dependency và cách xác minh/khôi phục nhầm? |
| **Apply** | Thao tác tại đúng target/source và không ghi đè lifecycle mới hơn? |
| **Verify** | Đã kiểm tra actual **và** effective access? |
| **Closure** | Có audit, bằng chứng, giám sát regrant và owner cho ngoại lệ? |

**Quyền thừa được xử lý triệt để khi quyền hiệu lực thực tế phù hợp với công việc, trạng thái vòng đời và quyết định có thẩm quyền.** Người vận hành cần xem toàn bộ đường cấp quyền, không giới hạn ở nhóm IdP; thu hồi quyền cũ khi Mover, chặn truy cập còn sót khi Leaver, kiểm soát service identity/đặc quyền và kiểm chứng từng ứng dụng sau thao tác. Chính việc đối soát và đóng bằng chứng giúp biến nguyên tắc least privilege thành một quy trình IAM operations có thể vận hành, đo lường và kiểm toán.
