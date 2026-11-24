# Privileged review: rà soát và tái chứng nhận quyền truy cập đặc quyền trong IAM

Một quản trị viên chuyển sang vị trí kinh doanh nhưng vẫn thuộc nhóm quản trị production. Một tài khoản dịch vụ có quyền xóa dữ liệu toàn bộ tenant dù ứng dụng chỉ cần đọc một bảng. Tài khoản khẩn cấp break-glass chưa được sử dụng nhiều tháng nhưng khóa truy cập đang được nhiều người biết. Các trường hợp này có thể không tạo ra lỗi đăng nhập nào; thậm chí hệ thống vận hành bình thường. Rủi ro nằm ở chỗ **quyền đặc quyền tiếp tục tồn tại mà không còn được chứng minh là cần thiết và được kiểm soát**.

**Privileged review** là hoạt động kiểm kê, đánh giá và tái chứng nhận các quyền truy cập có thể quản trị, thay đổi cấu hình bảo mật, truy xuất dữ liệu nhạy cảm ở quy mô lớn, cấp quyền cho người khác hoặc làm gián đoạn dịch vụ. Rà soát cần trả lời không chỉ **ai có quyền** mà còn **quyền đó có thật sự cần, có hợp lệ trong thời điểm hiện tại, được sử dụng qua những đường nào, có giới hạn đủ hẹp và đã được thu hồi đúng khi không còn nhu cầu hay chưa**.

Bài học thuộc chương **Privileged access**, chủ đề **Privileged review**, trong mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Mô-đun nghiên cứu quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**, từ xác minh và tạo tài khoản đến cấp quyền, rà soát, thu hồi khi đổi vai trò, kết hợp **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán** và giảm quyền truy cập tồn dư.

Sau bài học, người học có thể:

- Định nghĩa privileged review và phân biệt nó với kiểm tra đăng nhập, kiểm toán log hoặc access review thông thường.
- Xác định đầy đủ danh mục **tài khoản, vai trò, nhóm, token, bí mật, phiên, delegation và đường nâng đặc quyền** cần rà soát.
- Thiết kế tiêu chí đủ điều kiện, **reviewer độc lập, evidence package, quyết định tái chứng nhận và hành động khắc phục**.
- Đọc **effective privileges** thay vì chỉ các role được gán trực tiếp, bao gồm vai trò kế thừa, nhóm lồng nhau, quyền cấp tiếp và phiên tồn dư.
- Gắn kết review với **Joiner–Mover–Leaver, PAM/JIT, IdP/SSO, SCIM, workload identity và SoD**.
- Xác minh thu hồi trên hệ thống thực thi, quản lý ngoại lệ, xây dựng báo cáo và chỉ số kiểm soát rủi ro.

## 1. Privileged review là gì và vì sao phải làm?

**Quyền đặc quyền (privileged access)** là khả năng thực hiện các hành động có tác động bảo mật, vận hành hoặc dữ liệu lớn hơn quyền nghiệp vụ thông thường. Nó có thể thuộc về một cá nhân, tài khoản dịch vụ, tiến trình, workload hoặc một tổ hợp quyền cho phép nâng cấp đặc quyền.

**Privileged review** là quy trình đánh giá có căn cứ để xác định:

1. **Danh tính và chủ sở hữu:** principal này là ai, thuộc người/workload nào, ai chịu trách nhiệm?
2. **Quyền thực tế:** có thể thực hiện hành động gì, với tài nguyên nào, thông qua đường truy cập nào?
3. **Nhu cầu hợp lệ:** nhiệm vụ hiện tại có yêu cầu quyền này không, phạm vi và thời hạn có phù hợp không?
4. **Rủi ro:** quyền có thể gây nâng quyền, phá hủy, xuất dữ liệu, cấp tiếp đặc quyền hoặc vượt phân tách nhiệm vụ không?
5. **Cơ chế bảo vệ:** MFA, PAM, JIT, session control, logging, credential management và giới hạn điều kiện có được thực thi?
6. **Quyết định:** giữ, thu hẹp, chuyển sang JIT, thay quyền, đình chỉ hoặc thu hồi?
7. **Xác minh:** thay đổi đã được áp dụng ở hệ thống đích và mọi đường truy cập liên quan chưa?

Rà soát có giá trị vì **quyền từng được cấp đúng trong quá khứ không bảo đảm còn đúng ở hiện tại**. Nhiệm vụ thay đổi, dự án kết thúc, đối tác chấm dứt hợp đồng, tài khoản được di chuyển, khóa bị chia sẻ hoặc ứng dụng đổi mô hình permission đều có thể khiến quyền trở nên quá mức.

### 1.1. Ví dụ đơn giản

| Tình huống | Nhìn bề ngoài | Câu hỏi của privileged review |
| --- | --- | --- |
| Nhân viên còn thuộc nhóm Domain Admins. | Account đăng nhập bình thường. | Vị trí hiện tại có yêu cầu quyền quản trị domain không? |
| Engineer có quyền Owner ở cloud subscription. | Là thành viên của đội phát triển. | Có cần Owner toàn subscription hay chỉ Contributor/role hẹp ở resource group? |
| Service principal có quyền quản lý mọi secret. | Pipeline vẫn chạy đúng. | Workload dùng những secret nào và ai là owner hợp lệ? |
| Break-glass account hiếm dùng. | Không có hoạt động bất thường. | Có phương thức kiểm soát, giám sát, kiểm thử và người chịu trách nhiệm không? |
| Nhân viên đã nghỉ vẫn có local admin account. | IdP chính đã disabled. | Đường truy cập cục bộ đã bị khóa và phiên/token có còn hiệu lực không? |

**Không thấy hoạt động đăng nhập không chứng minh quyền đã được thu hồi.** Review phải xem cả khả năng thực hiện hành động và trạng thái credential/phiên.

## 2. Phân biệt privileged review với những hoạt động liên quan

| Hoạt động | Câu hỏi trọng tâm | Giới hạn nếu dùng thay privileged review |
| --- | --- | --- |
| **Access review / recertification** | Quyền còn cần thiết và được phê duyệt không? | Nếu chỉ nhìn role thông thường, có thể bỏ sót quyền nâng đặc quyền gián tiếp. |
| **Privileged review** | Toàn bộ quyền đặc biệt, đường sử dụng, owner, SoD và kiểm soát thực tế có phù hợp không? | Cần phạm vi sâu hơn user-role assignment đơn thuần. |
| **PAM session monitoring** | Phiên đặc quyền đã thực hiện những hành động gì? | Chỉ thấy phiên đi qua PAM, có thể không thấy đường đi vòng. |
| **Vulnerability assessment** | Hệ thống có lỗ hổng kỹ thuật nào? | Không chứng minh user còn cần quyền admin. |
| **Configuration audit** | Policy/nhóm/role được cấu hình thế nào? | Không tự trả lời căn cứ công việc và thời điểm hết hạn. |
| **Identity lifecycle review** | Joiner, Mover, Leaver đã cập nhật tài khoản đúng chưa? | Có thể bỏ sót tài khoản phụ và workload độc lập. |
| **Incident investigation** | Sự cố cụ thể đã xảy ra ra sao? | Thường có phạm vi/thời điểm cụ thể, không thay cho tái chứng nhận định kỳ. |

Một privileged review tốt **dùng dữ liệu từ PAM, IAM/IGA, log và cấu hình**, nhưng không đồng nhất với bất kỳ nguồn đơn lẻ nào.

## 3. Thế nào là đặc quyền trong từng nền tảng?

Không chỉ tài khoản có tên admin mới là đặc quyền. **Mức tác động có thể quan trọng hơn tên role**.

| Loại hệ thống | Ví dụ quyền cần rà soát | Rủi ro đáng chú ý |
| --- | --- | --- |
| **Directory / AD DS** | Domain Admins, Enterprise Admins, quản lý group/OU, reset password, quyền thay ACL. | Chiếm đoạt hoặc nâng quyền trên nhiều tài khoản. |
| **IdP / IAM / IGA** | Global administrator, quản lý MFA, reset authenticator, thêm app, thay access policy. | Vượt kiểm soát xác thực và cấp quyền toàn tổ chức. |
| **Cloud IAM** | Owner, Administrator, policy edit, role assignment, tạo credential. | Leo thang đặc quyền theo account/subscription/project. |
| **Kubernetes** | cluster-admin, sửa RoleBinding/ClusterRoleBinding, đọc Secret, exec vào pod nhạy cảm. | Mở rộng quyền trên namespace/cluster hoặc chiếm workload. |
| **Database** | Superuser, CREATE USER, GRANT, DROP, đọc/ghi dữ liệu toàn hệ thống. | Trích xuất dữ liệu, phá hủy hoặc tự cấp quyền. |
| **SaaS nghiệp vụ** | Tenant admin, user/role management, mass export, audit configuration. | Lộ dữ liệu và thay đổi phân quyền ngoài IAM. |
| **Secrets/KMS/PKI** | Đọc/ghi mọi secret, thay key policy, ký/xoay khóa, cấp chứng chỉ. | Chiếm credential hoặc kiểm soát trust. |
| **CI/CD** | Thay deployment pipeline, approval gate, production secret, signing pipeline. | Đưa mã/hình ảnh độc hại vào production. |
| **Network/security** | Firewall administrator, thay WAF, SIEM hoặc EDR policy. | Vô hiệu hóa phòng vệ, mở đường truy cập. |
| **Ứng dụng nội bộ** | Tạo người dùng, sửa role, override phê duyệt, thay cấu hình tenant. | SoD conflict, truy cập dữ liệu trái phạm vi. |

**Quyền quản lý quyền** thường mang tính đặc biệt. Một người không có tên role “admin” nhưng có thể tự gán role admin hoặc sửa trust/policy vẫn có khả năng nâng đặc quyền và phải nằm trong phạm vi rà soát.

### 3.1. Phân loại theo tác động, không chỉ nhãn

Một cách phân loại rủi ro nội bộ có thể xét:

- **Identity control:** có thể reset MFA, đổi owner, tạo/khóa user hoặc cấp role.
- **Credential control:** có thể đọc secret, phát token, cấp khóa hoặc ký bằng khóa nhạy cảm.
- **Data control:** có thể đọc/xuất/sửa/xóa dữ liệu ở phạm vi lớn hoặc nhạy cảm.
- **Operational control:** có thể dừng dịch vụ, thay cấu hình production hay đường mạng.
- **Audit control:** có thể xóa log hoặc vô hiệu hóa giám sát.
- **Privilege escalation:** có thể tạo hoặc giả mạo principal khác, thay chính sách hay assume role mạnh hơn.

Một permission có thể nằm trong nhiều nhóm. Tổ chức cần tự xây **danh mục privileged entitlements và risk tier**; không nên chỉ dựa vào một danh sách tên role cứng.

## 4. Tài khoản, quyền và những đường truy cập cần đưa vào scope

Privileged review thất bại ngay từ đầu nếu chỉ xuất danh sách tài khoản admin thông thường.

| Đối tượng | Ví dụ | Cần xác minh |
| --- | --- | --- |
| **Named privileged account** | alice-admin, dba-operator. | Liên kết đúng Person/Engagement và nhiệm vụ. |
| **Secondary account** | Tài khoản quản trị phụ, tài khoản riêng production. | Có nằm trong inventory và vòng đời JML không? |
| **Shared/emergency account** | break-glass, tài khoản khôi phục. | Ai quản lý, cách sử dụng, rotate, audit và kiểm thử? |
| **Service account** | svc-backup, svc-sync. | Workload, owner, credential và scope thực tế. |
| **Workload identity** | Service principal, managed identity, Kubernetes ServiceAccount. | Phạm vi trust, role bindings và owner. |
| **Directory group** | Nhóm quản trị, nhóm lồng nhau. | Thành viên hiệu lực, quyền kế thừa và đối tượng ngoài nhóm trực tiếp. |
| **Cloud role/policy binding** | Owner ở subscription, permission set ở tài khoản cloud. | Scope, role assumption, trust policy và quyền cấp tiếp. |
| **App-local role** | Admin được cấp trực tiếp trong SaaS. | Có ngoài IdP group/SCIM/IGA hay không? |
| **Delegated access** | Truy cập được ủy quyền từ owner khác. | Delegation có expiry và quy trình thu hồi không? |
| **API credential / PAT** | Access token dài hạn, API key, certificate. | Chủ sở hữu, quyền, thời hạn và khả năng thu hồi. |
| **Session đang hoạt động** | PAM session, application admin session. | Có thể vẫn hoạt động sau khi role bị thu hồi không? |

Các tài khoản không có owner, bị bỏ qua trong dữ liệu xuất hoặc không ánh xạ được sang subject/workload **không được tự coi là vô hại**. Phải có quy trình xác minh và biện pháp giảm thiểu theo rủi ro.

## 5. Effective privileges: quyền thực tế quan trọng hơn quyền được gán

**Assigned privilege** là quyền gắn trực tiếp với chủ thể/tài khoản theo một bản ghi cụ thể. **Effective privilege** là tập khả năng thực tế có thể sử dụng sau khi tính quyền trực tiếp, kế thừa, quan hệ nhóm, điều kiện, trust và quyền được kích hoạt.

~~~text
Principal A
    ├── Direct app role: reports-reader
    ├── Directory group: operations-team
    │      └── Nested group: production-operators
    │             └── Permission: change deployment
    ├── Cloud role: assume deployment-admin (có điều kiện)
    ├── Delegation: manage secrets for project-X
    └── PAT cũ: token scope rộng của một ứng dụng

=> Chỉ xem Direct app role sẽ bỏ sót nhiều đường đặc quyền.
~~~

### 5.1. Những nguồn làm mở rộng quyền

1. **Nested groups:** thành viên gián tiếp có thể có quyền không xuất hiện trong danh sách thành viên trực tiếp.
2. **Role hierarchy:** role cấp cao kế thừa permission của role thấp theo thiết kế provider.
3. **Role assumption/delegation:** principal có quyền nhận role mạnh hơn qua điều kiện trust.
4. **Policy attachment/inheritance:** policy cấp tổ chức, account, project, resource hoặc quyền trực tiếp kết hợp nhau.
5. **Owner/control-plane privilege:** người có thể chỉnh policy hoặc quản lý credential có khả năng tạo đường nâng quyền.
6. **Local grants:** database/SaaS có quyền riêng ngoài group IdP và IGA.
7. **Active sessions/tokens:** quyền cũ có thể còn được thực thi qua session/PAT sau khi membership thay đổi.

Không thể tính mọi hệ thống bằng phép cộng permission đơn giản. Có những cơ chế **explicit deny, resource policy, permission boundary, session policy, điều kiện ABAC hoặc SoD** khiến quyền thực tế hẹp hoặc rộng hơn nhận xét chỉ dựa trên role name.

### 5.2. Đọc quyền trực tiếp và kiểm khả năng thực thi

Ví dụ tài khoản Cloud A không có role Owner trực tiếp, nhưng có quyền **gán Owner cho chính mình**. Privileged review phải xem đây là một **đường nâng quyền** cần xử lý, không kết luận tài khoản chỉ có role Reader là an toàn.

Với hệ thống nhạy cảm, có thể sử dụng phương pháp phân tích **privilege graph/path** được tổ chức phê duyệt để phát hiện đường leo thang. Việc kiểm thử quyền thực tế phải thực hiện trong phạm vi được ủy quyền, tránh thử thao tác phá hủy hoặc truy xuất dữ liệu không cần thiết.

## 6. Inventory: tìm đầy đủ các đặc quyền cần review

Trước vòng review, xây dựng **inventory thống nhất** với ID chủ thể và nguồn dữ liệu được đối chiếu.

~~~mermaid
flowchart LR
    HR["HRIS / hợp đồng<br/>Person + Engagement + JML"] --> IGA["IGA / Identity correlation"]
    IDP["IdP / Directory<br/>Groups + admin roles"] --> IGA
    PAM["PAM / JIT<br/>Privileged sessions + secrets"] --> IGA
    CLOUD["Cloud / K8s / DB / SaaS<br/>Actual grants"] --> IGA
    KEYS["Service registry / token issuer<br/>Workload + credential owner"] --> IGA
    IGA --> INV["Privileged access inventory<br/>Effective scope + owner + risk"]
    INV --> REV["Review + Attestation"]
    REV --> REM["Remediation + Reconciliation"]
    REM --> AUD["Audit / Exceptions / KPIs"]
~~~

### 6.1. Mỗi dòng inventory nên trả lời

| Trường | Mục đích |
| --- | --- |
| **principalId, accountId** | Định danh tài khoản/principal tại provider. |
| **subjectId / engagementId** | Liên kết con người và quan hệ hiện tại, nếu là human account. |
| **workloadId / ownerTeam** | Chủ sở hữu và ứng dụng của non-human identity. |
| **targetSystem / tenantId** | Hệ thống, tổ chức, environment hoặc cloud account. |
| **privilegeId / permissionSet** | Đúng đặc quyền và khả năng thực thi. |
| **resourceScope** | Những tài nguyên/namespace/project chịu tác động. |
| **grantSource / inheritancePath** | Quyền đến từ direct, group, role, delegation, policy hay PAM. |
| **assignmentStatus / accessMode** | Standing, eligible, time-bound, JIT active, disabled... |
| **approvedPurpose / approvalRef** | Căn cứ nghiệp vụ/điều phối. |
| **owner / reviewerCandidate** | Chủ sở hữu đặc quyền và người rà soát độc lập. |
| **grantedAt / effectiveAt / expiresAt** | Thời điểm cấp, hiệu lực và hết hạn. |
| **lastUsedAt / lastVerifiedAt** | Dữ liệu quan sát việc sử dụng và kiểm chứng. |
| **riskTier / reviewDueAt** | Mức rủi ro và kỳ rà soát. |
| **mfa / pam / logging controls** | Các biện pháp kiểm soát đã xác minh. |

**Không lưu raw password, token, private key hoặc session cookie** trong inventory. Những trường credential chỉ nên là tham chiếu tới hệ thống quản lý bí mật có phân quyền.

### 6.2. Đối chiếu account mồ côi

Một account có đặc quyền nhưng không xác định được owner/subject nên được gắn trạng thái **UNKNOWN_OWNER** hoặc ngoại lệ tương ứng; không tự gán nó cho người có email gần giống. Đối chiếu cần dựa trên **ID bền vững, nguồn sở hữu và bằng chứng liên kết**.

## 7. Định nghĩa scope và ưu tiên theo rủi ro

Privileged review không nhất thiết bắt đầu bằng việc phân tích mọi hệ thống cùng độ sâu. Có thể chia lớp theo tác động và khả năng nâng đặc quyền.

| Tier minh họa | Đặc điểm | Trọng tâm review |
| --- | --- | --- |
| **Critical** | Có thể chiếm domain/IdP, đổi trust, tạo credential admin, kiểm soát khóa ký hoặc xóa log. | Owner, SoD, JIT, sự tồn tại quyền thường trực, session/secret, xác minh thường xuyên và xử lý khẩn. |
| **High** | Quản trị production, dữ liệu nhạy cảm hoặc cấp quyền app rộng. | Scope, approval, credential, audit và direct entitlements. |
| **Elevated** | Quyền triển khai/chỉnh dữ liệu trong một dự án hoặc dịch vụ. | Đúng nhiệm vụ, scope, thời hạn và quyền kế thừa. |
| **Routine** | Quyền thông thường, ít tác động. | Có thể do quy trình access review chung quản lý; cần phân loại đúng. |

Đây là **thang đo nội bộ minh họa**, không phải phân hạng chuẩn của một quy định. Tổ chức cần xác định tiêu chí: độ nhạy dữ liệu, khả năng thay policy, phạm vi tenant, khả năng thay credential, blast radius, mức phơi lộ và tính thường trực.

### 7.1. Review theo chu kỳ và theo sự kiện

Hai cơ chế nên bổ sung nhau:

- **Periodic review:** đánh giá theo lịch đã được chính sách và mức rủi ro quy định.
- **Event-driven review:** kích hoạt khi Mover/Leaver, thay owner, thay role, thêm app, xâm nhập credential, thay trust, thay classification hoặc phát hiện grant không rõ nguồn.

Không có một chu kỳ **30/90/180 ngày** mặc nhiên phù hợp cho mọi hệ thống. Các giá trị có thể là lựa chọn của tổ chức dựa trên rủi ro và yêu cầu tuân thủ. **Một Leaver cần thu hồi quyền đúng hiệu lực, không chờ vòng review định kỳ**.

## 8. Ai được làm reviewer? Trách nhiệm và tính độc lập

Rà soát có thể mất ý nghĩa nếu người đang giữ quyền tự đánh dấu **“tôi vẫn cần quyền này”** và đó là bằng chứng duy nhất.

| Vai trò | Trách nhiệm |
| --- | --- |
| **Identity owner / subject** | Giải thích nhiệm vụ và phạm vi công việc hiện tại; không tự là người phê duyệt độc lập. |
| **Line manager / sponsor** | Xác nhận quan hệ làm việc và nhu cầu công việc. |
| **Application/system owner** | Hiểu permission và tác động vận hành của quyền. |
| **Data owner** | Xác nhận phạm vi dữ liệu nhạy cảm cần truy cập. |
| **Privileged Access/PAM owner** | Đánh giá cách kích hoạt, session, credential và giới hạn thời gian. |
| **Security / IAM governance** | Xây chính sách, rủi ro, SoD, kiểm soát ngoại lệ và giám sát vòng review. |
| **Independent reviewer / second approver** | Cung cấp đánh giá độc lập cho quyền rủi ro cao. |
| **Implementation owner** | Thực thi grant/revoke theo quyết định, không tự hợp thức hóa quyền. |
| **Audit** | Đánh giá bằng chứng, tính đầy đủ và hiệu quả kiểm soát; thường không thay người phê duyệt nghiệp vụ. |

### 8.1. Tránh self-review và xung đột lợi ích

Ví dụ quản trị viên IdP có quyền thay MFA policy và tự sửa danh sách reviewer. Nếu họ cũng tự phê duyệt quyền của mình, việc rà soát không còn độc lập. Với quyền có tác động lớn, cần tách **owner xác nhận nhu cầu**, **reviewer đánh giá quyền**, **người thực thi** và **kiểm chứng kết quả** tùy rủi ro.

**Manager không luôn hiểu hết permission kỹ thuật.** Manager có thể xác nhận nhu cầu công việc, nhưng app/security owner phải diễn giải phạm vi kỹ thuật của quyền. Một hộp chọn “Approve” không đủ nếu reviewer không được cung cấp thông tin để hiểu đang giữ quyền gì.

### 8.2. Khi reviewer cũng là Leaver/Mover

Tuyến review phải được cập nhật theo quan hệ quản lý có hiệu lực. Nếu reviewer đã rời tổ chức, bị đình chỉ hoặc chuyển vai trò không còn thẩm quyền, workflow cần **chuyển giao** tới người duyệt đủ quyền; không gửi lại yêu cầu cho account cũ hoặc tự chấp thuận do thiếu người duyệt.

## 9. Evidence package: reviewer cần nhìn những bằng chứng nào?

Một review chỉ hiển thị **tên nhóm và nút Approve/Reject** thường thiếu ngữ cảnh.

### 9.1. Bảng bằng chứng tối thiểu

| Dữ liệu | Câu hỏi mà bằng chứng giúp trả lời |
| --- | --- |
| **Subject/Engagement/Account** | Đúng người hoặc workload nào? Còn hợp lệ không? |
| **Business purpose** | Tác vụ hiện tại có đòi quyền này không? |
| **Permission và effective scope** | Có thể làm gì, trên tenant/resource/environment nào? |
| **Grant source** | Quyền từ yêu cầu, nhóm, kế thừa, local role hay manual override? |
| **Approval và policy version** | Quyền được ai cấp, theo căn cứ nào, còn hiệu lực không? |
| **Role owner và risk tier** | Ai sở hữu ý nghĩa và tác động của quyền? |
| **Last use / usage patterns** | Có dữ liệu quan sát sử dụng không, nguồn log và khoảng thời gian nào? |
| **MFA/PAM/JIT/session controls** | Cơ chế bảo vệ đã kiểm chứng hay chỉ được khai báo? |
| **Credential age/rotation metadata** | Credential có còn hợp lệ và quản trị đúng không? |
| **SoD và escalation findings** | Có tổ hợp quyền xung đột hoặc khả năng cấp tiếp không? |
| **JML changes và expiry** | Mover/Leaver, thay hợp đồng hoặc assignment hết hạn? |
| **Existing exceptions / incident** | Có lỗ hổng hoặc trường hợp cần khắc phục khẩn không? |

### 9.2. Bằng chứng sử dụng có giới hạn

**LastUsedAt** không phải bằng chứng duy nhất để giữ hoặc thu hồi quyền:

- Một tài khoản break-glass hợp lệ có thể không dùng trong thời gian dài.
- Một role đặc quyền được sử dụng thường xuyên không chứng minh nó cần ở mức toàn tenant.
- Không có log có thể do hệ thống không thu thập đầy đủ, không phải không có hành động.
- Người dùng có thể sử dụng quyền do lỗi quy trình hoặc để tiện thao tác, chưa chắc đúng nhu cầu.

Review phải dựa trên **mục đích công việc, tác động quyền, thẩm quyền owner và bằng chứng kỹ thuật**. Dữ liệu sử dụng là tín hiệu hỗ trợ, không thay thế quyết định.

## 10. Quy trình privileged review đầu-cuối

~~~mermaid
flowchart TD
    A["Xác định review scope<br/>risk tier + dueAt"] --> B["Discovery / inventory<br/>account + role + token + delegation"]
    B --> C["Identity correlation<br/>Person/Engagement hoặc Workload/Owner"]
    C --> D["Tính effective privileges<br/>scope + escalation paths"]
    D --> E["Chuẩn bị evidence package<br/>usage + approval + JML + controls"]
    E --> F["Reviewer độc lập<br/>xác nhận nhu cầu + SoD"]
    F --> G{"Decision"}
    G -->|"Keep có căn cứ"| H["Đặt review/expiry tiếp theo<br/>ghi attestation"]
    G -->|"Reduce/Convert to JIT"| I["Remediation theo policy"]
    G -->|"Revoke / Suspend"| I
    G -->|"Không rõ"| J["Exception có owner<br/>giới hạn rủi ro + deadline"]
    I --> K["Provision/Deprovision<br/>IdP/SCIM/PAM/app/cloud"]
    K --> L["Readback + verify effective access<br/>session/token/secret"]
    L --> M{"Verified?"}
    M -->|"Có"| N["Đóng review + audit"]
    M -->|"Không"| J
    J --> L
    H --> N
~~~

### 10.1. Pha 1 – Chuẩn bị

1. Xác định hệ thống, tenant, môi trường, risk tier và kỳ review.
2. Lấy inventory và đối chiếu danh tính theo ID ổn định.
3. Tính quyền trực tiếp, kế thừa, ủy quyền và quyền nâng cấp đặc quyền.
4. Kiểm người sở hữu và phân người review phù hợp.
5. Thu thập evidence package có độ mới thích hợp.
6. Gắn cờ các trường hợp **Leaver, orphan, credential nghi lộ, grant mới bất thường** để xử lý theo runbook riêng thay vì chờ hoàn tất vòng định kỳ.

### 10.2. Pha 2 – Attestation

1. Reviewer đọc nhiệm vụ hiện tại và permission thực tế.
2. Xác minh owner, engagement, risk, SoD và điều kiện bảo vệ.
3. Chọn quyết định rõ **giữ, thu hẹp, chuyển JIT, thu hồi hoặc cần điều tra**.
4. Ghi lý do cụ thể, scope, thời hạn và người phê duyệt.
5. Với quyền rủi ro cao, kích hoạt bước review độc lập bổ sung theo chính sách.

### 10.3. Pha 3 – Khắc phục và xác minh

1. Tạo tác vụ kỹ thuật để thực thi quyết định.
2. Thu hồi/đổi role qua cơ chế đúng provider: directory, SCIM, local API, cloud IAM, PAM.
3. Thu hồi quyền trong **group, role direct, delegation và credential** theo phạm vi.
4. Xử lý phiên/token đang còn sống nếu chính sách và tính năng yêu cầu.
5. Đọc lại trạng thái ở từng đích, kiểm **effective permissions**.
6. Chỉ đóng khi đã có bằng chứng, hoặc ghi ngoại lệ chưa hoàn tất với owner và hạn xử lý.

## 11. Các quyết định review và cách thực thi

| Quyết định | Ý nghĩa | Hành động cụ thể |
| --- | --- | --- |
| **RETAIN** | Quyền vẫn cần thiết và phù hợp kiểm soát. | Lưu lý do, owner, scope, expiry và kỳ review mới. |
| **REDUCE_SCOPE** | Vẫn cần tác vụ nhưng quyền quá rộng. | Thu hẹp action, resource, tenant hoặc environment. |
| **REPLACE_ROLE** | Role hiện tại không tối thiểu. | Thay bằng role đã được duyệt, kiểm SoD và quyền kế thừa. |
| **CONVERT_TO_JIT** | Nhu cầu chỉ phát sinh khi làm tác vụ. | Bỏ standing privilege; dùng JIT/PAM có thời hạn và phê duyệt. |
| **REVOKE** | Không còn căn cứ quyền. | Xóa/disable assignment và xác minh ở đích. |
| **SUSPEND_PENDING_REVIEW** | Chưa chắc nhu cầu hoặc phát hiện rủi ro. | Hạn chế quyền theo policy; đặt owner, deadline và điều kiện phục hồi. |
| **INVESTIGATE** | Dữ liệu owner/identity/permission mơ hồ. | Mở exception, bổ sung bằng chứng, không auto-approve. |
| **ACCEPT_EXCEPTION** | Chấp nhận rủi ro trong phạm vi, thời hạn được duyệt. | Ghi approver đủ thẩm quyền, lý do, kiểm soát bù và lịch hết hạn. |

**Retain không đồng nghĩa gia hạn vô hạn.** Nếu quyền vốn có expiresAt, review cần xác nhận có gia hạn hay không và tại sao. Với quyền đặc biệt, nên đặt **điểm tái kiểm tra** và cơ chế thu hồi khi có thay đổi JML.

### 11.1. Không dùng “Revoke” thiếu phạm vi

Khi quyết định thu hồi role, cần biết nó đang được cấp bởi **những nguồn nào**. Xóa một group ở IdP có thể chưa đủ nếu ứng dụng có local admin role hoặc service principal còn token khác. Ngược lại, xóa toàn bộ account production của một workload đang được dùng hợp lệ có thể gây sự cố dịch vụ; cần thiết kế thay thế hoặc thu hẹp quyền phù hợp.

## 12. Review quyền thường trực và quyền Just-in-Time

**Standing privilege** là đặc quyền đang có sẵn thường xuyên hoặc có thể sử dụng mà không cần kích hoạt theo mỗi nhu cầu. **JIT eligible access** là khả năng yêu cầu/kích hoạt quyền trong thời gian và điều kiện đã định.

| Cơ chế | Cần rà soát |
| --- | --- |
| **Standing admin** | Có cần quyền liên tục không? Có thể thu hẹp hoặc chuyển JIT? |
| **JIT eligibility** | Người dùng có còn đủ điều kiện được kích hoạt quyền không? |
| **JIT activation** | Lần kích hoạt nào, thời gian, phê duyệt, scope và session? |
| **PAM vault access** | Ai có thể xem/lấy credential hoặc mở phiên quản trị? |
| **PAM session policy** | MFA, recording/log, time limit, command restriction và termination? |
| **Emergency role** | Có dùng ngoài mục đích khẩn cấp không? Kỳ kiểm thử và hậu kiểm? |

**Đừng cho rằng “không có standing admin” đồng nghĩa không có rủi ro** nếu một người có quyền tự kích hoạt admin mà không cần kiểm soát phù hợp. Review phải đánh giá cả **quyền eligible, cơ chế kích hoạt và các điều kiện hạn chế**.

### 12.1. Xem xét thời gian thực của quyền

Một role JIT chỉ kích hoạt 60 phút có thể làm giảm thời gian phơi lộ; nhưng nếu hệ thống để **refresh token, session cookie hoặc quyền trực tiếp** tồn tại sau 60 phút, giới hạn danh nghĩa chưa được thực thi đầy đủ.

Cần đối chiếu **activation ended** với **privilege no longer usable**. Tùy sản phẩm, điều này có thể yêu cầu thu hồi session, token hoặc kiểm lại role tại API sau khi privilege hết hạn.

## 13. Break-glass và quyền khẩn cấp: review đặc biệt

Tài khoản **break-glass** tồn tại để khôi phục khả năng quản trị trong những tình huống nghiêm trọng như IdP/PAM mất sẵn sàng. Vì vậy, nó có thể cần tồn tại dù hiếm dùng; giải pháp không phải cứ không thấy log đăng nhập là xóa.

### 13.1. Nội dung review break-glass

- **Mục đích:** chỉ dành cho những loại sự cố nào?
- **Owner và người phê duyệt sử dụng:** ai chịu trách nhiệm quản lý và kích hoạt?
- **Bảo quản credential:** có cơ chế chống truy cập trái phép, có thể kiểm chứng người đã sử dụng không?
- **Tách biệt phụ thuộc:** tài khoản dự phòng có phụ thuộc chính IdP/PAM đang cần cứu không?
- **MFA hoặc biện pháp bảo vệ phù hợp:** thiết kế tránh tạo điểm lỗi đơn và bảo đảm kiểm soát rủi ro.
- **Monitoring:** mỗi lần dùng có cảnh báo tới security/on-call và ghi log hay không?
- **Test:** có kiểm thử theo lịch được phê duyệt mà không gây thao tác phá hủy?
- **Post-use:** có điều tra, rotate/recover credential và rà soát hoạt động sau lần dùng?
- **Expiry/ownership:** người giữ trách nhiệm có còn hợp lệ và có bàn giao khi Mover/Leaver?

### 13.2. Không đánh đồng tài khoản break-glass và admin thường xuyên

Một tài khoản khẩn có quyền rất rộng có thể là cần thiết theo kế hoạch continuity, nhưng **không được dùng để xử lý ticket thường ngày**. Mọi sử dụng ngoài kịch bản định nghĩa nên được cảnh báo và điều tra. Review có thể giữ account nhưng **không chấp thuận cách lưu credential, số người biết hoặc quy trình giám sát hiện tại**; khi đó cần khắc phục kiểm soát chứ không chỉ đổi quyết định thành Retain.

## 14. Review service account và workload identity

Tài khoản không phải con người thường ít xuất hiện trong HRIS và dễ bị bỏ qua trong những đợt access review theo phòng ban.

### 14.1. Bằng chứng cho non-human identity

| Thuộc tính | Cần xác minh |
| --- | --- |
| **principalId / serviceAccountId** | Đây là principal kỹ thuật nào, thuộc nền tảng nào? |
| **workloadId / applicationId** | Job, pipeline, daemon hoặc ứng dụng nào sử dụng? |
| **ownerTeam / technicalOwner** | Ai duy trì, phê duyệt và sẽ nhận cảnh báo? |
| **resourceScope / permissionSet** | Có ít quyền cần thiết hay là role admin toàn tenant? |
| **credential type** | Managed identity, federated token, key/cert/secret nào? |
| **rotation / expiry / last use** | Credential còn an toàn và có theo dõi không? |
| **environment** | Quyền thuộc dev, staging hay production? |
| **deployment/trust configuration** | Principal có thể được workload nào assume hoặc sử dụng? |
| **decommission plan** | Khi ngừng dịch vụ, ai thu hồi quyền và credential? |

### 14.2. Ví dụ pipeline bị cấp quyền quá mức

Pipeline chỉ cần triển khai ứng dụng **orders-api** trong namespace **orders-prod**, nhưng đang sử dụng service principal có quyền **Owner** toàn subscription cloud.

Review nên:

1. Xác nhận service principal thực sự được job nào sử dụng.
2. Xác định thao tác cần thiết: đọc artifact, cập nhật deployment, đọc một số secret cụ thể.
3. Liệt kê quyền thực tế gồm role assignment, secret access và khả năng cấp tiếp.
4. Thiết kế role hẹp theo resource và action, kiểm thử trên môi trường được phép.
5. Chuyển sang workload identity/token ngắn hạn khi khả năng hệ thống và threat model phù hợp.
6. Thu hồi role Owner dư thừa, kiểm tra pipeline chạy đúng với quyền mới.
7. Xác minh không còn credential hoặc trust cũ có thể dùng quyền rộng.

**Không kéo dài quyền của nhân viên đã nghỉ chỉ để giữ pipeline chạy.** Workload phải có principal và owner riêng.

### 14.3. Owner chuyển công việc hoặc rời tổ chức

Khi người phụ trách workload Mover/Leaver, phải:

- Chuyển **ownerTeam** và trách nhiệm vận hành cho người được phê duyệt.
- Rà soát credential có từng được chia sẻ hoặc gắn với PAT cá nhân không.
- Thay hoặc thu hồi bí mật khi có rủi ro hợp lý, dùng danh tính máy được quản trị.
- Kiểm lại role/permission theo nhu cầu workload hiện hành.
- Không xóa vội workload còn phục vụ nghiệp vụ hợp lệ nhưng phải có biện pháp hạn chế nếu owner chưa rõ.

## 15. Privileged review trong Joiner–Mover–Leaver

### 15.1. Joiner: không cấp admin từ ngày tạo tài khoản

Một nhân viên mới có thể được pre-provision vào directory hoặc IdP trước ngày bắt đầu. Việc tài khoản tồn tại **không phải căn cứ kích hoạt role đặc biệt**.

Luồng đề xuất:

1. HRIS xác minh Person, Engagement, Start date, worker type và bộ phận.
2. IAM xác định subject ID và liên kết đúng account trong từng provider.
3. Đánh giá liệu nhiệm vụ thực sự cần quyền đặc biệt hay có thể dùng role hẹp.
4. Owner phê duyệt role/scope; Security/PAM kiểm SoD và biện pháp bổ sung.
5. Nếu cần, cấp **eligibility** trước nhưng chỉ cho kích hoạt khi engagement có hiệu lực và các điều kiện thỏa.
6. Bật MFA/step-up, session monitoring và expiry theo policy.
7. Đối soát quyền thực tế và tạo lịch review dựa trên rủi ro.

**Không bật standing admin chỉ vì nhân viên thuộc nhóm IT.** Các nhiệm vụ helpdesk, triển khai ứng dụng và quản trị domain có phạm vi quyền khác nhau.

### 15.2. Mover: tái chứng nhận ngay khi vai trò đổi

Khi nhân viên đổi phòng ban, dự án, manager hoặc loại quan hệ:

- Tính lại **required privilege** theo nhiệm vụ mới.
- Phát hiện các standing roles, JIT eligibilities và local grants từ nhiệm vụ cũ.
- Chuyển approval owner và tuyến duyệt đang chờ.
- Thu hồi quyền không còn chính đáng, xử lý session/token cũ khi cần.
- Chỉ cấp đặc quyền mới sau khi eligibility, SoD và scope được phê duyệt.
- Xác minh tại ứng dụng/cloud/resource thay vì chỉ đọc group IdP.

Ví dụ người chuyển từ **Database Operations** sang **Product Management** có thể vẫn cần xem một số dashboard nhưng **không còn lý do quản trị database production**. Nếu chỉ thêm role viewer mới, quyền DBA cũ trở thành quyền tồn dư.

### 15.3. Leaver: thu hồi khẩn không chờ lịch review

Khi engagement kết thúc, cần chặn khả năng sử dụng đặc quyền của người đó:

| Phạm vi | Việc cần kiểm |
| --- | --- |
| **Directory/IdP** | Disable account, privileged groups và quản trị viên phụ. |
| **Cloud/IAM/PAM** | Role, eligibility, active elevation, sessions và role assumption. |
| **SaaS/SCIM** | Admin app-local, User active state, nhóm và delegated grants. |
| **Credentials** | API key, PAT, secret, certificate và token liên quan. |
| **Workload ownership** | Bàn giao owner/credential của job còn hợp lệ. |
| **Incident visibility** | Có dấu hiệu sử dụng đặc quyền gần hoặc sau mốc termination? |

**IdP disable thành công không mặc nhiên đóng phiên admin ở mọi SaaS** hoặc hủy access token đã phát hành. Mỗi đường truy cập cần được xử lý theo chức năng provider và đối soát.

### 15.4. Rehire, contractor và tạm đình chỉ

- **Rehire:** xác minh cùng Person nhưng dùng Engagement mới; không tự kích hoạt lại grant/secret từ giai đoạn cũ.
- **Contractor:** quyền đặc biệt phải bám hợp đồng, sponsor, phạm vi và ngày hết hạn.
- **Suspended/On leave:** policy có thể yêu cầu tạm dừng quyền; khi trở lại cần đánh giá lại, không tự mở mọi role.
- **Manager change:** thay người phê duyệt không đồng nghĩa người mới tự được đặc quyền của manager cũ.

## 16. Kết nối privileged review với IdP, SSO, SCIM và PAM

Một hệ thống có thể có nhiều nơi chứa thông tin quyền:

| Hệ thống | Dữ liệu cung cấp cho review | Cần kiểm ở hệ thống khác |
| --- | --- | --- |
| **HRIS / hợp đồng** | Employment status, manager, vị trí, effective date. | Không tự cho biết role thực tế ở SaaS. |
| **IGA** | Request, approval, SoD, expected entitlements, review workflow. | Phải đối soát quyền đã cấp tại đích. |
| **IdP / directory** | Tài khoản, nhóm, app assignment, sign-in và MFA. | Không thấy mọi app-local role hoặc PAT. |
| **SSO SAML/OIDC** | Xác thực và claim/role snapshot ở thời điểm phát hành. | Không chứng minh role trong phiên cũ đã được thu hồi. |
| **SCIM** | User/Group provisioning và trạng thái cập nhật theo provider. | Không chuẩn hóa mọi permission admin, local session hay secret. |
| **PAM/PIM** | Vault access, eligible role, elevation, session và credential controls. | Có thể thiếu đường truy cập trực tiếp không đi qua PAM. |
| **Application/resource API** | Admin role trực tiếp, hành vi và khả năng thực thi quyền. | Cần gắn đúng subject và nguồn approval. |

### 16.1. Vì sao không chỉ dựa vào SSO claim?

Một OIDC token có thể chứa claim **groups** vào lúc người dùng đăng nhập; sau đó nhóm đã bị thu hồi nhưng token còn hiệu lực đến khi hết hạn. Một SaaS cũng có thể lưu role trong session độc lập. Do đó, privileged review phải xem xét **thời hạn session/token, quyền tại API, cơ chế invalidation và direct assignment ngoài IdP**.

### 16.2. Vì sao SCIM success chưa đủ?

Một thao tác PATCH xóa thành viên khỏi SCIM Group có thể thành công, nhưng:

- Ứng dụng có local role cấp trực tiếp.
- Quyền được kế thừa từ một group khác.
- Phiên cũ còn giữ role.
- API key độc lập vẫn có scope quản trị.
- Provider cập nhật không đồng bộ tới các vùng.

**Review chỉ được đóng với mức độ xác minh đúng phạm vi**, hoặc phải ghi rõ đường truy cập chưa kiểm và ngoại lệ có owner.

## 17. SoD, toxic combinations và đường nâng quyền

**Separation of Duties (SoD)** giúp ngăn một người vừa thực hiện vừa phê duyệt những bước xung đột trong một giao dịch hoặc quy trình.

| Tổ hợp quyền | Rủi ro | Cần kiểm |
| --- | --- | --- |
| Tạo nhà cung cấp + duyệt thanh toán. | Gian lận quy trình tài chính. | Static/dynamic SoD theo nghiệp vụ. |
| Tạo user + tự gán role admin. | Nâng quyền qua control plane. | Tách người thực hiện và reviewer. |
| Quản trị log + xóa log nhạy cảm. | Che giấu dấu vết hoạt động. | Giới hạn quyền, bảo vệ log độc lập. |
| Quản lý khóa + phê duyệt việc sử dụng khóa. | Lạm dụng secret/PKI. | Dual control và audit khi phù hợp. |
| Sửa CI pipeline + tự bỏ qua gate phê duyệt. | Đưa artifact chưa kiểm soát vào production. | Bảo vệ workflow, ký và approval độc lập. |

### 17.1. Review quyền kế thừa và quyền cấp tiếp

Một chủ thể có thể giữ từng quyền nhìn bề ngoài vô hại nhưng kết hợp thành đường nâng đặc quyền. Ví dụ có khả năng sửa role binding và tạo workload sử dụng binding đó. Vì vậy, review cần tính **khả năng cấp tiếp, giả danh, assume role hoặc sửa policy** – không chỉ xem quyền CRUD trên dữ liệu.

### 17.2. DSD và hành động thực tế

**Dynamic SoD** có thể ngăn kích hoạt đồng thời những role xung đột trong cùng phiên hoặc giao dịch, nếu ứng dụng hỗ trợ. Nhưng hệ thống chỉ dùng group tĩnh có thể không biết liệu một người thực hiện cả hai bước trong cùng giao dịch. Khi đó cần kiểm SoD ở **workflow/transaction** và audit, không tuyên bố việc xóa một group đã xử lý hết mọi rủi ro.

## 18. Rà soát tài khoản ngủ yên và quyền không được sử dụng

**Dormant privileged access** là quyền hoặc account còn tồn tại nhưng không có dấu hiệu sử dụng trong một khoảng thời gian được policy xác định.

### 18.1. Quyền ngủ yên là tín hiệu, không phải kết luận

Review cần phân loại:

- **Role không còn nhiệm vụ:** có thể thu hồi.
- **Role dùng khi sự cố:** cần xác nhận mục đích, kiểm soát và thử nghiệm có kế hoạch.
- **Service account theo lịch thưa:** cần xem lịch job và telemetry có đủ không.
- **Account chuyển sang nền tảng khác:** cần xác nhận đã decommission và không còn đường cũ.
- **Log thiếu dữ liệu:** không được coi lastUsedAt rỗng là không dùng.

### 18.2. Xử lý quyền không hoạt động

1. Kiểm owner và nhiệm vụ hiện tại.
2. Xác định khoảng quan sát và độ bao phủ log.
3. Đánh giá tác động nếu thu hồi hoặc hạ scope.
4. Nếu không còn căn cứ, thu hồi qua quy trình có phê duyệt.
5. Với break-glass, kiểm owner/continuity thay vì xóa máy móc.
6. Đối soát session, credential và role ở provider sau thực thi.

## 19. Rà soát credential, secret và session đặc quyền

Đặc quyền có thể được sử dụng qua những vật mang quyền không hiển thị trong User/Group inventory:

- Password/secret của shared service account.
- API key, Personal Access Token (PAT), refresh token.
- Khóa SSH, certificate và credentials gắn với máy.
- OAuth client credential, cloud access key.
- PAM credential checkout hoặc phiên đang chạy.
- Offline recovery token, break-glass credential.

### 19.1. Câu hỏi review credential

| Câu hỏi | Vì sao quan trọng |
| --- | --- |
| Secret được lưu ở đâu và ai có thể lấy? | Quyền đọc secret có thể tương đương quyền giả danh principal. |
| Credential có owner/workload cụ thể không? | Tránh bí mật dùng chung không ai chịu trách nhiệm. |
| TTL/rotation phù hợp không? | Giảm thời gian credential bị lộ có thể được sử dụng. |
| Có bản sao ở CI logs, code hoặc ticket không? | Các bản sao có thể vượt ngoài hệ thống PAM/secret manager. |
| Token có scope/audience/issuer đúng không? | Credential bị giới hạn theo API/tài nguyên nào? |
| Khi revoke account, credential có bị vô hiệu hóa theo provider không? | Tránh đường truy cập tồn dư. |
| Ai có thể phát token/secret mới? | Có đường nâng quyền từ quyền tạo credential không? |

Không yêu cầu reviewer **xem raw password hoặc xuất private key** để chứng minh credential tồn tại. Nên dùng metadata được bảo vệ như ID, owner, trạng thái, rotationAt, expiresAt, lastUseAt và xác minh của vault/issuer.

### 19.2. Session dài sau khi role bị thu hồi

Khi chấm dứt JIT elevation hoặc Leaver, không nên chỉ gỡ group và tin rằng các phiên đang tồn tại tự hết. Cần xem sản phẩm có hỗ trợ **session termination, token revocation, access evaluation lại tại mỗi request hoặc rút ngắn thời hạn token**. Nếu không, ghi nhận giới hạn kỹ thuật và biện pháp giảm thiểu.

## 20. Ra quyết định khi review có nguy cơ gián đoạn dịch vụ

Thu hồi privileged access đôi khi ảnh hưởng production. Đây không phải lý do giữ quyền vô hạn, nhưng cũng không nên xóa account máy trước khi xác định phụ thuộc.

### 20.1. Safe change sequence

1. **Khẳng định nhu cầu mục tiêu**: tác vụ/workload vẫn cần chức năng gì?
2. **Đề xuất quyền thay thế hẹp hơn** với owner phê duyệt.
3. **Kiểm thử** ở môi trường hoặc luồng được ủy quyền, không dùng hành động phá hủy để thử.
4. **Chuyển dependency** sang principal mới hoặc role hẹp theo change plan.
5. **Thu hồi quyền rộng** theo kế hoạch đã được phê duyệt.
6. **Đọc lại effective permission** tại provider và xác minh tác vụ hợp lệ vẫn chạy.
7. **Giám sát hậu thay đổi** và rollback có kiểm soát nếu cần.
8. **Đóng ngoại lệ** chỉ sau khi nguy cơ quyền dư đã được loại bỏ hoặc chấp nhận hợp lệ có thời hạn.

### 20.2. Không hợp thức hóa ngoại lệ lâu dài

Nếu một job vẫn phụ thuộc vào role admin quá rộng, review có thể ghi **exception** trong thời hạn xác định để triển khai thay thế. Exception phải có owner, rủi ro, biện pháp giảm thiểu, hạn hoàn tất và thẩm quyền chấp nhận; không nên đánh dấu Retain vĩnh viễn chỉ vì “không thể sửa ngay”.

## 21. Review theo sự kiện: phát hiện thay đổi quyền bất thường

Ngoài chu kỳ định kỳ, cần kích hoạt review khi có tín hiệu:

| Sự kiện | Review cần làm |
| --- | --- |
| **Manager/department/job thay đổi** | Kiểm privileged eligibility và quyền cũ; chuyển reviewer đúng thẩm quyền. |
| **Employee/Contractor Leaver** | Thu hồi ngay, điều tra đặc quyền độc lập, active sessions và PAT. |
| **Thay owner service account** | Xác minh workload còn cần, bàn giao secret và quyền. |
| **Grant role admin mới** | Kiểm approval, SoD, scope, thời hạn và nguồn tạo. |
| **Kích hoạt JIT bất thường** | Kiểm lý do, thiết bị, thời gian, session và hành vi. |
| **Privilege escalation path được phát hiện** | Đánh giá tác động, chặn đường và sửa policy. |
| **Key/token nghi lộ** | Thu hồi hoặc rotate phù hợp, đánh giá tài nguyên bị ảnh hưởng. |
| **Thay role definition** | Tái đánh giá tất cả principal chịu quyền kế thừa mới. |
| **Nhà cung cấp SaaS thay mô hình permission** | Cập nhật mapping và effective access review. |
| **Đổi cấu hình trust/SSO hoặc federation** | Kiểm issuer, scope, client roles và đường đăng nhập ngoài ý muốn. |

### 21.1. Sự kiện đến muộn không được tái cấp quyền

Giả sử Mover cần giảm admin role nhưng connector bị timeout. Sau đó HRIS phát Leaver, tài khoản đã bị vô hiệu hóa. Một job Mover cũ chạy lại không được khôi phục admin role. Phải xử lý bằng **source version, effectiveAt, idempotency và xác minh authoritative state hiện tại** trước thao tác quyền.

## 22. Tái chứng nhận qua nhiều hệ thống và reconciliation

**Reconciliation** so sánh **expected privileged access** với **actual effective access** tại hệ thống đích.

### 22.1. Những chênh lệch thường gặp

| Drift | Ví dụ | Quy trình xử lý |
| --- | --- | --- |
| **Excess privilege** | Người đã Mover vẫn có database admin. | Ưu tiên thu hồi, kiểm session và lý do tồn dư. |
| **Missing approved privilege** | PAM đã duyệt nhưng role JIT không kích hoạt được. | Sửa đúng connector/policy, không cấp admin toàn cục. |
| **Orphan principal** | Cloud service principal không có owner. | Điều tra, giới hạn rủi ro, xác định workload hoặc decommission. |
| **Direct local grant** | SaaS có admin role ngoài IdP group. | Đưa vào inventory và thu hồi/chuẩn hóa quản trị. |
| **Stale eligibility** | Mover vẫn có thể request JIT admin cũ. | Tính lại eligibility và policy. |
| **Expired assignment active** | Role tạm vẫn dùng được sau expiresAt. | Thu hồi và xác minh ở API/resource. |
| **Session/token drift** | Quyền bị gỡ nhưng token còn scope cũ. | Session/token mitigation và log giới hạn thời gian. |
| **Group nesting** | Thành viên gián tiếp vẫn được admin. | Xác định membership hiệu lực và mọi đường cấp. |

### 22.2. Không đóng review chỉ từ một lớp thành công

~~~text
Review decision: REVOKE
    ↓
IGA remediation task: SENT
    ↓
SCIM Group PATCH: HTTP 204
    ↓
Application local role: vẫn ACTIVE
    ↓
PAM session: còn mở
    ↓
Effective access: CHƯA REVOKED
~~~

Để xác minh thu hồi, cần kết hợp trạng thái **account/role/group** và các **đường thực thi có liên quan**. Nếu không thể xác minh một hệ thống, phải nói rõ hạn chế; không suy luận từ hệ thống khác.

## 23. Case study 1: Mover còn đặc quyền production

**Bối cảnh giả định:** Minh từng là kỹ sư SRE có quyền thay policy production thông qua cloud role **ProductionAdmin**. Ngày **01/12**, Minh chuyển sang nhóm phân tích sản phẩm và chỉ cần đọc dashboard vận hành. HRIS cập nhật Mover đúng giờ, nhưng một assignment cloud không nằm trong connector IGA.

| Thời điểm | Sự kiện | Tình trạng/rủi ro |
| --- | --- | --- |
| **30/11 16:00** | HRIS ghi Mover, effectiveAt = 01/12 08:00. | Căn cứ nghiệp vụ đã có. |
| **01/12 08:00** | IGA tính bỏ privileged eligibility và role SRE. | Expected privilege không còn ProductionAdmin. |
| **01/12 08:02** | IdP group SRE đã gỡ. | Chỉ chứng minh group này đổi. |
| **01/12 08:05** | Cloud inventory vẫn thấy direct ProductionAdmin assignment. | Privilege drift do đường grant trực tiếp. |
| **01/12 08:07** | Reviewer và Security xác nhận Minh không còn nhiệm vụ production. | Quyết định REVOKE, không phải Retain. |
| **01/12 08:10** | IAM/cloud owner thu hồi direct role; kiểm token/session đang hoạt động. | Cần đánh giá cửa sổ quyền cũ. |
| **01/12 08:13** | Readback cloud cho thấy không còn role, privilege simulation/kiểm thử được phép xác nhận từ chối thao tác admin. | Có bằng chứng thu hồi trong phạm vi. |
| **01/12 08:15** | Ghi kết quả, nguồn grant thủ công và biện pháp ngăn tái cấp. | Hành động khắc phục mang tính hệ thống. |

### 23.1. Bài học

1. **Tài khoản vẫn xác thực bình thường** không có nghĩa quyền hợp lệ.
2. **Gỡ IdP group chưa đủ** khi có direct cloud role.
3. Review phải đọc **effective privileges** từ nguồn thực thi.
4. Mover cần hành động **event-driven**, không chờ kỳ review tiếp theo.
5. Cần xác định tại sao quyền được cấp ngoài IGA và có bao nhiêu principal tương tự.
6. Đóng review sau **revoke verified**, không sau khi gửi ticket.

## 24. Case study 2: Service principal đặc quyền không còn owner

**Bối cảnh giả định:** một service principal tên **svc-data-export** từng phục vụ job chuyển dữ liệu. Job đã chuyển sang hệ thống mới nhưng principal vẫn có quyền đọc mọi cơ sở dữ liệu và phát access key. Kỹ sư tạo principal đã nghỉ việc từ hai tháng trước.

### 24.1. Review phát hiện

| Bằng chứng | Kết quả |
| --- | --- |
| Service catalog | Không còn job production đăng ký sử dụng principal. |
| Owner mapping | Owner gắn với Employee đã Leaver; không có ownerTeam hiện hành. |
| Cloud IAM | Role dữ liệu rộng và quyền tạo credential. |
| Last used | Không có hoạt động trong 45 ngày; log có khoảng thiếu coverage. |
| Secret manager | Một credential chưa tới hạn xoay và chưa rõ consumer. |
| PAM/IGA inventory | Principal không thuộc kỳ review của human accounts. |

### 24.2. Quy trình xử lý

1. **Không tự coi lastUsedAt rỗng là chắc chắn không được dùng**; xác minh lịch job, service catalog và owners liên quan.
2. Gán owner tạm thời cho việc điều tra và hạn xử lý rõ.
3. Dùng phương pháp kiểm tra được phép để xác định workload có còn phụ thuộc hay không.
4. Nếu đã ngừng hoàn toàn, thu hồi role và credential, disable/decommission principal theo chính sách.
5. Nếu còn nhu cầu, chuyển owner, thiết kế role hẹp và credential quản lý phù hợp trước khi thu hồi quyền rộng.
6. Kiểm lại quyền cloud, token/secret và nhật ký; xác nhận không còn đường sử dụng ngoài phạm vi.
7. Ghi sự cố và cải thiện cơ chế **chuyển giao workload owner khi Leaver**.

**Bài học:** privileged review phải bao gồm **non-human identities**, không chỉ danh sách nhân viên từ HRIS.

## 25. Case study 3: Break-glass account được giữ nhưng kiểm soát phải thay

**Bối cảnh giả định:** đội bảo mật review tài khoản emergency-admin cấp toàn tenant. Tài khoản hiếm khi đăng nhập nhưng nhiều quản trị viên từng biết cùng một password; không có cảnh báo riêng khi dùng.

Quyết định đúng **không nhất thiết là xóa tài khoản** vì tổ chức vẫn cần phương án khôi phục khi IdP/PAM lỗi. Thay vào đó:

1. Xác định use case khẩn cấp được cho phép.
2. Đánh giá điểm lỗi phụ thuộc và số người có thể truy cập credential.
3. Chuyển quản lý credential vào cơ chế phù hợp, hạn chế số người và lưu bằng chứng sử dụng.
4. Thiết lập cảnh báo đến đội chịu trách nhiệm khi account được dùng.
5. Kiểm thử khôi phục trong phạm vi an toàn và có phê duyệt.
6. Thực hiện hậu kiểm và rotate khi sử dụng hoặc nghi lộ theo policy.
7. Đặt hạn review tiếp theo, owner và bằng chứng.

Kết quả có thể là **RETAIN WITH REMEDIATION**: duy trì năng lực emergency access nhưng không chấp nhận cơ chế bảo vệ hiện tại. Không được ghi **COMPLIANT** nếu các vấn đề chính còn mở mà không có ngoại lệ được phê duyệt.

## 26. Giả mã điều phối privileged review

~~~text
startPrivilegedReview(scope, reviewPolicy):
    targets = discoverAuthorizedPrivilegedTargets(scope)
    inventory = collectDirectAndDerivedPrivilegeGrants(targets)
    correlated = linkToVerifiedPersonsEngagementsOrWorkloadOwners(inventory)

    for privilege in correlated:
        if privilege.identityMappingIsAmbiguous:
            openIdentityExceptionAndConsiderRiskMitigation(privilege)
            continue

        effective = calculateEffectivePrivilegeAndEscalationPaths(privilege)
        risk = assessPrivilegeRisk(effective, reviewPolicy)

        if privilege.subjectIsTerminated or privilege.credentialCompromised:
            triggerUrgentRevocationRunbook(privilege)
            continue

        evidence = createLeastDataEvidencePackage(
            privilege, effective, risk, usageCoverage, approvals, controls
        )
        reviewer = assignIndependentEligibleReviewer(evidence)
        requestAttestation(reviewer, evidence, reviewDueAt(risk))

onReviewDecision(decision):
    verifyReviewerAuthorityAndNoSelfApproval(decision)
    verifyDecisionIsCurrent(decision.subject, decision.target)

    if decision.action == "RETAIN":
        recordReasonScopeExpiryAndNextReview(decision)
    else if decision.action in ["REVOKE", "REDUCE", "CONVERT_TO_JIT"]:
        planAuthorizedSafeRemediation(decision)
        executeViaCorrectProviderAndTrackEachTarget(decision)
        verifyEffectiveAccessCredentialAndSessionState(decision)
    else:
        openTrackedExceptionWithOwnerDeadlineAndCompensatingControls(decision)

    recordImmutableAuditReferencesWithoutSecrets(decision)
~~~

Đây là **giả mã kiến trúc**, không phải phần mềm thực thi. Một hệ thống thực cần xử lý phân trang, retry, idempotency, rate limit, version/ETag, concurrency, quyền reviewer, quy trình change management và trạng thái từng đích. Quan trọng nhất: **sự kiện Mover/Leaver mới phải được ưu tiên hơn attestation hoặc retry cũ**.

### 26.1. Không chấp nhận attestation trên snapshot cũ

Giả sử reviewer giữ quyền lúc 09:00 theo dữ liệu Employee ACTIVE, nhưng HRIS phát Leaver có hiệu lực 08:30 và sự kiện tới muộn. Workflow cần **kiểm lại trạng thái có thẩm quyền khi xử lý quyết định**, tránh một approval cũ mở lại role đã thu hồi.

## 27. Nhật ký kiểm toán và bằng chứng tái chứng nhận

Rà soát đặc quyền phải có khả năng chứng minh **phạm vi đã kiểm, bằng chứng reviewer nhìn thấy, quyết định, người phê duyệt, thao tác sửa và trạng thái cuối cùng**.

### 27.1. Bộ trường nên có

| Trường | Mục đích |
| --- | --- |
| **reviewId / campaignId / eventId** | Phân biệt kỳ review và sự kiện kích hoạt. |
| **principalId / subjectId / engagementId / workloadId** | Xác định đúng danh tính con người hoặc máy. |
| **targetSystem / tenantId / accountId** | Nêu rõ hệ thống, tenant và tài khoản. |
| **privilegeId / effectivePermissionSet / scope** | Mô tả quyền đang được đánh giá. |
| **grantSource / inheritancePath** | Nguồn trực tiếp, gián tiếp, delegation hoặc eligible JIT. |
| **riskTier / policyVersion / sodResults** | Căn cứ đánh giá rủi ro. |
| **reviewerId / reviewerRole / approvalRef** | Chứng minh thẩm quyền và tính độc lập. |
| **evidenceSnapshotAt / sourceVersions** | Biết dữ liệu nào đã được xem và độ mới. |
| **reviewDecision / reason / decisionAt** | Kết luận và lý do cụ thể. |
| **remediationTaskId / providerResponse** | Truy vết thay đổi kỹ thuật. |
| **verifiedAt / verificationMethod** | Bằng chứng quyền đã khớp trạng thái mong đợi. |
| **exceptionId / owner / dueAt** | Theo dõi ngoại lệ, giới hạn rủi ro và thời hạn. |

Ví dụ sự kiện audit dạng nội bộ, dữ liệu định danh giả:

~~~json
{
  "eventType": "PRIVILEGED_ACCESS_REVIEW_COMPLETED",
  "reviewId": "priv-review-202612-041",
  "principalId": "cloud-principal-715",
  "subjectId": "person-1042",
  "engagementId": "EMP-5812",
  "targetSystem": "production-cloud",
  "tenantId": "tenant-a",
  "privilegeId": "ProductionAdmin",
  "resourceScope": "subscription-prod-a",
  "grantSource": "DIRECT_ROLE_ASSIGNMENT",
  "riskTier": "CRITICAL",
  "evidenceSnapshotAt": "2026-12-01T01:05:00Z",
  "reviewerId": "security-reviewer-2088",
  "decision": "REVOKE",
  "decisionReason": "Mover: no longer has production operations duties",
  "remediationTaskId": "iam-revoke-772",
  "providerResult": "SUCCESS",
  "effectiveAccessResult": "REVOKED_VERIFIED",
  "verifiedAt": "2026-12-01T01:13:00Z",
  "exceptionId": null
}
~~~

Schema trên là **ví dụ minh họa**, không phải định dạng chuẩn của IAM/PAM hoặc bất kỳ provider cụ thể. Kết quả **REVOKED_VERIFIED** phải có chứng cứ kiểm tra; chỉ thay chuỗi trạng thái trong log không tạo ra bảo đảm kỹ thuật.

### 27.2. Bảo vệ dữ liệu review

Evidence package có thể chứa thông tin vị trí nhân sự, danh mục admin, đường nâng quyền hoặc metadata credential nhạy cảm. Chỉ cung cấp theo **need-to-know**, có audit ai đã xem và lịch lưu giữ hợp lệ. Không đưa raw password, private key, token hay session cookie vào ticket, export hoặc bản chụp màn hình.

## 28. Chỉ số đo hiệu quả privileged review

| Chỉ số | Công thức/phương pháp gợi ý | Điều phản ánh |
| --- | --- | --- |
| **Privileged inventory coverage** | Principal/grant thuộc phạm vi được phát hiện và liên kết ÷ tổng ước tính có bằng chứng. | Độ đầy đủ của danh mục. |
| **Owner coverage** | Privileged principal có owner hợp lệ ÷ tổng principal đã kiểm. | Tài khoản mồ côi. |
| **Review completion on time** | Review có quyết định hợp lệ đúng hạn ÷ tổng đến hạn. | Kỷ luật review. |
| **Reviewer independence coverage** | Review rủi ro cao đáp ứng quy tắc độc lập ÷ tổng thuộc phạm vi. | Nguy cơ self-approval. |
| **Excess privilege findings** | Số grant vượt nhu cầu, quá scope hoặc không có approval. | Privilege creep và role rộng. |
| **Standing-to-JIT conversion** | Grant thường trực được chuyển sang JIT sau đánh giá ÷ số grant đủ điều kiện. | Giảm cửa sổ đặc quyền. |
| **Mean/percentile revoke latency** | Từ quyết định/hiệu lực tới lúc revoke được verified. | Tốc độ giảm rủi ro. |
| **Mover/Leaver privileged residue** | Grant/credential/session còn được xác minh có hiệu lực sau mốc thu hồi. | Truy cập tồn dư. |
| **Dormant privileged grants** | Quyền không có căn cứ sử dụng trong kỳ, có xét độ bao phủ log. | Quyền thừa tiềm năng. |
| **SoD/escalation findings** | Đường nâng quyền hoặc tổ hợp xung đột chưa xử lý. | Rủi ro cấp tiếp/tự cấp quyền. |
| **Exception aging** | Ngoại lệ quá hạn, có owner hoặc thiếu biện pháp giảm thiểu. | Nợ bảo mật. |
| **Remediation verified rate** | Quyết định Reduce/Revoke/JIT có readback phù hợp ÷ tổng cần sửa. | Review có tạo thay đổi thực tế hay không. |
| **Non-human privileged owner coverage** | Service principals có workload/owner/credential policy hợp lệ. | Rủi ro từ tài khoản máy. |
| **Break-glass control verification** | Tài khoản khẩn có owner, monitoring, kiểm thử và hậu kiểm đúng hạn. | Khả năng continuity có kiểm soát. |

Không đặt mục tiêu dựa duy nhất vào số **Approve** nhanh hoặc số ticket đã đóng. Một chiến dịch có **100% attestation** nhưng **0% xác minh thu hồi** chưa chứng minh quyền đã an toàn.

### 28.1. Phạm vi và giới hạn dữ liệu

Khi báo cáo, phải ghi rõ **provider nào đã được kiểm, provider nào thiếu API, loại account nào không có log, token nào không thể thu hồi tức thì và phạm vi xác minh thực tế**. Tránh tuyên bố “không còn đặc quyền tồn dư” nếu vẫn có những vùng chưa quan sát được.

## 29. Sai lầm thường gặp khi làm privileged review

| Sai lầm | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| **Chỉ lấy danh sách admin từ IdP** | Bỏ sót local roles, cloud IAM, service accounts. | Inventory đa nguồn, tính effective grants. |
| **Reviewer tự phê duyệt quyền của mình** | Xung đột lợi ích. | Tách reviewer và người giữ quyền. |
| **Hiển thị tên role mà không có permission** | Quyết định không hiểu tác động. | Evidence package có scope và effective access. |
| **Retain vì từng được cấp trước đây** | Hợp thức hóa privilege creep. | Xác minh nhiệm vụ và approval hiện tại. |
| **Thu hồi ngay mọi account không dùng gần đây** | Có thể phá break-glass hoặc batch job hợp lệ. | Đánh giá purpose, lịch chạy, log coverage. |
| **Duy trì admin vì sợ ngắt production** | Quyền rộng không có hạn khắc phục. | Safe change plan và exception có hạn. |
| **Bỏ qua JIT eligibility** | Principal có thể tự kích hoạt quyền đặc biệt. | Review cả eligibility và activation. |
| **Chỉ nhìn Group membership trực tiếp** | Bỏ sót nested groups, role assumption. | Tính effective privilege và escalation paths. |
| **Tin 200/204 từ SCIM là hoàn tất** | App-local admin hoặc token vẫn có quyền. | Readback và kiểm session/API. |
| **Không cập nhật reviewer khi Mover** | Quyết định do người không còn thẩm quyền. | Manager/owner mapping có hiệu lực. |
| **Chờ lịch review khi Leaver xảy ra** | Người nghỉ vẫn có quyền nhạy cảm. | Event-driven revocation ngay. |
| **Không kiểm credential và PAT** | Quyền ngoài tài khoản SSO tồn dư. | Inventory credential và token lifecycle. |
| **Không ghi trạng thái ngoại lệ** | Task chưa xử lý bị coi là hoàn tất. | Exception có owner, deadline và kiểm soát bù. |
| **Thu thập raw secret làm bằng chứng** | Tạo điểm lộ credential mới. | Chỉ lưu metadata/reference được bảo vệ. |

## 30. Checklist thực hiện Privileged review

1. Đã có **danh mục privileged roles/permissions** theo tác động và risk tier, không chỉ theo tên admin chưa?
2. Có kiểm kê **human admin, secondary account, break-glass, service/workload principal, API key, PAT và delegation** không?
3. Có liên kết account tới **subjectId + engagementId** hoặc **workloadId + ownerTeam** đáng tin cậy không?
4. Có thu thập **direct, inherited, nested group, role-assumption, local grants và escalation paths** không?
5. Có ghi đúng **resource/tenant/environment scope**, khả năng cấp tiếp quyền và hiệu lực thời gian không?
6. Review scope và kỳ rà soát có được ưu tiên theo **rủi ro**, không chỉ theo số user không?
7. Có quy trình **event-driven** khi Mover, Leaver, thay owner, grant mới, incident và role definition đổi không?
8. Reviewer có đủ ngữ cảnh về **permission, purpose, owner, approval, usage coverage, credential và SoD** không?
9. Có cơ chế chống **self-review/self-approval** và thay reviewer khi họ không còn thẩm quyền không?
10. Mỗi quyết định Retain/Reduce/Revoke/JIT có **lý do, scope, expiry và authority** không?
11. Có đánh giá cả **JIT eligibility, active elevation, PAM vault access và privileged session** không?
12. Với break-glass, có kiểm **mục đích, bảo quản credential, giám sát, kiểm thử và hậu kiểm** không?
13. Với service principal, có owner/workload, scope tối thiểu, credential lifecycle và decommission plan không?
14. **Joiner** có tránh cấp standing admin trước Start date hoặc khi chưa có phê duyệt không?
15. **Mover** có thu hồi role cũ và cập nhật owner/reviewer, không chỉ cấp role mới không?
16. **Leaver** có thu hồi quyền trên IdP, directory, cloud, SaaS, PAM và credential/session/token theo phạm vi không?
17. Rehire có được xét theo **engagement mới**, không tự phục hồi quyền đặc biệt cũ không?
18. Có kiểm **SoD, role hierarchy, local admin, quyền sửa policy/secret/credential** và đường nâng quyền không?
19. Có quy trình **safe change** khi thu hồi quyền workload production, tránh giữ admin vô hạn do phụ thuộc không?
20. Có chống **stale event, retry Mover sau Leaver và attestation dựa trên snapshot cũ** không?
21. Sau quyết định Reduce/Revoke, có **đọc lại role/group và kiểm effective access** tại hệ thống đích không?
22. Có xử lý **application session, OAuth tokens, PAT, API keys, certificates** còn tồn dư theo khả năng không?
23. Ngoại lệ chưa Verified có **owner, mức rủi ro, deadline, biện pháp giảm thiểu và cảnh báo** không?
24. Có lưu audit về **reviewer, evidence version, decision, approval, remediation và kết quả xác minh** mà không lộ secret không?
25. Có đo **coverage, completion, excess privilege, revoke latency, orphan/service accounts, SoD và remediation verified rate** không?
26. Có báo cáo trung thực **hệ thống, quyền và đường truy cập chưa quan sát được** thay vì kết luận an toàn tuyệt đối không?

**Ghi nhớ:** **Privileged review là quá trình tái chứng nhận quyền đặc biệt dựa trên nhu cầu hiện tại, phạm vi tác động và bằng chứng thực tế**, không chỉ kiểm danh sách admin hay ký duyệt theo chu kỳ. Cần rà soát **cả con người và workload, quyền trực tiếp và kế thừa, standing và JIT, break-glass, token/credential và khả năng nâng đặc quyền**. Khi gắn review với **Joiner–Mover–Leaver, IdP/SSO, SCIM, PAM, RBAC/ABAC và SoD**, tổ chức có thể thu hẹp hoặc thu hồi quyền đúng lúc. Giá trị cuối cùng không nằm ở số quyết định **RETAIN/REVOKE** được ghi, mà ở **quyền thực tế đã được xác minh**, các ngoại lệ được quản trị và khả năng giải trình bằng audit trail đáng tin cậy.
