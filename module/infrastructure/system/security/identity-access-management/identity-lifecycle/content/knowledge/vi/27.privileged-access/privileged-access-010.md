# Giảm quyền đặc biệt trong Privileged Access: từ đặc quyền thường trực đến quyền tối thiểu có kiểm chứng

**Giảm quyền đặc biệt** (*privilege reduction* hoặc *privileged access minimization*) là hoạt động **loại bỏ, thu hẹp hoặc giới hạn thời gian sử dụng các quyền có khả năng tác động lớn đến hệ thống, dữ liệu và cơ chế bảo mật**. Mục tiêu không phải tước hết khả năng làm việc của quản trị viên, mà bảo đảm **đúng chủ thể, đúng thao tác, đúng tài nguyên, đúng thời điểm và đúng căn cứ nghiệp vụ** mới có thể sử dụng đặc quyền.

Ví dụ, kỹ sư trực vận hành cần xem trạng thái cụm máy chủ hằng ngày nhưng chỉ thỉnh thoảng khởi động lại một dịch vụ production. Nếu họ giữ vai trò `GlobalAdministrator` mọi lúc, quyền thực tế vượt xa nhiệm vụ thường nhật. Một thiết kế hợp lý có thể giữ `ProductionViewer` thường trực, còn quyền `service:restart` chỉ được kích hoạt trong một khung bảo trì **Just-in-Time (JIT)**, trên một dịch vụ xác định, sau phê duyệt và xác thực phù hợp. Khi phiên kết thúc, quyền và những đường truy cập còn hiệu lực phải **được thu hồi và kiểm chứng**.

Bài thuộc chương **Privileged access** của module **Identity and Access Management (IAM) — Identity Lifecycle**, nghiên cứu quản lý danh tính theo **Joiner–Mover–Leaver (JML)**. Nội dung gắn giảm đặc quyền với **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, PAM, kiểm toán và ngăn quyền truy cập tồn dư**. Người học sẽ biết nhận diện quyền nhạy cảm, phân tích những đường cấp quyền ẩn, xây quy trình giảm quyền không gây gián đoạn không cần thiết, và chứng minh *actual access* tại ứng dụng đích đã thu hẹp đúng như mong muốn.

> **Nguyên tắc:** Xóa một role khỏi màn hình quản trị **không đủ** để kết luận đặc quyền đã biến mất. Cần phân biệt **entitlement, quyền kế thừa, quyền kích hoạt, phiên/token/credential và việc ứng dụng thực sự cho phép thao tác**.

## 1. Privileged access là gì và tại sao phải giảm?

### 1.1. Đặc quyền khác quyền làm việc thông thường như thế nào?

Một **privileged permission** cho phép thực hiện hành động có ảnh hưởng lớn đến hệ thống, bảo mật, dữ liệu hoặc các identity khác. Mức độ đặc quyền phụ thuộc **phạm vi và hậu quả của thao tác**, không chỉ tên role.

| Ví dụ quyền | Vì sao có thể là đặc quyền? | Hướng giới hạn |
| --- | --- | --- |
| `iam:assign-admin` | Có thể trao quyền cao cho tài khoản khác. | Chỉ admin được ủy quyền, có phê duyệt/giám sát thay đổi. |
| `users:disable` | Có thể khóa danh tính người khác và gây gián đoạn. | Scope tenant/đơn vị, ticket và audit. |
| `secrets:read-all` | Có thể truy xuất credential của nhiều hệ thống. | Chỉ đọc secret cụ thể khi công việc cần. |
| `database:superuser` | Có thể đổi schema, dữ liệu, role và bỏ qua nhiều kiểm soát nội bộ. | Tách read-only, vận hành schema và quyền break-glass. |
| `cloud:owner` | Có quyền rất rộng với tài nguyên cloud hoặc gán quyền. | Gán role hẹp theo project/resource và JIT khi cần. |
| `k8s:cluster-admin` | Có thể điều khiển tài nguyên trên toàn cluster. | Namespace-scoped Role/RoleBinding và thao tác tối thiểu. |
| `payment:release` | Có thể giải ngân/chấp nhận giao dịch tài chính nhạy cảm. | Hạn mức, SoD và phê duyệt từng giao dịch. |
| `audit-log:delete` | Có thể cản trở điều tra và trách nhiệm giải trình. | Hạn chế rất chặt, tách nhiệm vụ và bảo vệ log. |
| `production:deploy` | Có thể thay đổi chương trình đang phục vụ khách hàng. | Pipeline có phê duyệt, scope dịch vụ và traceability. |

**Không phải mọi quyền ghi đều là đặc quyền**, và **quyền chỉ đọc đôi khi vẫn cực kỳ nhạy cảm**, ví dụ đọc khóa bí mật, dữ liệu cá nhân quy mô lớn hoặc hồ sơ tài chính toàn công ty. Phải đánh giá **tác động, phạm vi, khả năng leo thang và khả năng che giấu thao tác**.

### 1.2. “Giảm quyền” gồm những hành động nào?

- **Remove:** loại bỏ entitlement không còn căn cứ.
- **Downgrade:** đổi role rộng thành role chỉ chứa quyền cần thiết.
- **Scope:** giới hạn hành động theo resource, tenant, namespace, môi trường hoặc dữ liệu.
- **Time-bound:** đặt hạn sử dụng, JIT và cơ chế tự kết thúc phiên/quyền.
- **Separate:** tách tài khoản thường ngày và tài khoản quản trị; tách trách nhiệm xung đột.
- **Constrain:** yêu cầu step-up MFA, thiết bị phù hợp, phê duyệt, SoD, phiên được ghi nhận.
- **Replace:** thay quyền admin thủ công bằng workflow/pipeline hoặc capability hẹp có kiểm soát.
- **Revoke:** thu hồi role, credential, session/token và đường truy cập còn tồn tại.
- **Verify:** đọc trạng thái thực tế tại target và thử các hành động phải bị chặn.

**Đổi mật khẩu** hoặc **bật MFA** cải thiện bảo vệ credential, nhưng **không tự làm ít permission hơn**. Một tài khoản vẫn có quyền admin toàn tổ chức sau khi bật MFA vẫn là một tài khoản có **standing privilege**.

### 1.3. Standing privilege và privilege on demand

**Standing privilege** là đặc quyền được gán/khả dụng tương đối thường trực, không cần kích hoạt riêng cho từng nhu cầu. **On-demand/JIT privilege** có thể chỉ xuất hiện hoặc chỉ khả dụng khi có yêu cầu đủ điều kiện và hết hạn theo chính sách.

Không có nghĩa mọi tổ chức phải đạt **zero standing privileges** bằng mọi giá. Đó là một mục tiêu thiết kế có thể phù hợp cho quyền nhạy cảm; hệ thống còn cần tính đến khả năng phản ứng sự cố, giới hạn nền tảng và an toàn vận hành. Những ngoại lệ phải **rõ chủ sở hữu, phạm vi, lý do, thời hạn và kiểm toán**.

## 2. Tách identity, account, entitlement, credential và session

Một trong những nguyên nhân khiến giảm quyền thất bại là coi “xóa admin” chỉ là gỡ một dòng role. Thực tế, một người có thể giữ nhiều đường truy cập độc lập.

| Đối tượng | Ví dụ | Điều xảy ra khi giảm quyền |
| --- | --- | --- |
| **Person/identity** | IAM identity `person-2048`. | Vẫn có thể là nhân viên active dù bị gỡ quyền admin. |
| **Account ở IdP** | `idp-user-581`. | Dùng xác thực tập trung; disable account là hành động khác gỡ admin role. |
| **Privileged account** | `lan-admin` hoặc tài khoản PAM liên kết cá nhân. | Có thể phải khóa, đổi role hoặc thu hồi hoàn toàn. |
| **Entitlement/role** | `CloudOwner`, `DBAdmin`, `ProjectEditor`. | Thay đổi assignment và các quyền kế thừa. |
| **Local account** | Administrator tại máy chủ hoặc tài khoản DB native. | Có thể tồn tại ngoài SCIM/IdP, cần inventory riêng. |
| **Credential** | Mật khẩu, SSH key, certificate, API key, access key. | Cần xác định ai có thể sử dụng sau khi gỡ role. |
| **Session** | SSH/RDP/DB session, PAM checkout, ứng dụng web session. | Phiên có thể tiếp tục hoạt động nếu không có cơ chế revoke. |
| **Token** | Access/refresh token, personal access token, workload token. | Có thời hạn và quy tắc thu hồi riêng. |
| **Policy/grant path** | Role hierarchy, nested group, direct grant, resource policy. | Phải kiểm tra mọi đường quyền còn dẫn đến hành động nhạy cảm. |

### 2.1. Ví dụ quyền đến từ ba đường

~~~text
Identity: person-2048
   ├─ IdP group: production-operators
   │     └─ Cloud role: ResourceOperator
   │            └─ Permission: service:restart
   ├─ Direct grant at cloud project
   │     └─ Permission: service:restart
   └─ Local privileged account: lan-ops
         └─ Role: ClusterAdmin
                └─ Permission: service:restart, iam:manage, ...

Gỡ production-operators:
   -> Đường group có thể biến mất
   -> Direct grant và local privileged account vẫn còn
   -> Effective privilege chưa được thu hồi đầy đủ
~~~

**Đường cấp quyền** (*grant path*) quan trọng hơn cách UI hiển thị một role. Một user không còn group “Admin” vẫn có thể làm thao tác admin qua **role khác, local account, API token hoặc quyền owner đối với tài nguyên**.

## 3. Quy trình chuẩn để giảm đặc quyền

Giảm quyền cần có thứ tự để vừa tránh **overprivilege** vừa tránh **mất khả năng vận hành hợp lệ**.

~~~mermaid
flowchart TD
    I["Inventory accounts, roles, grants, sessions, credentials"] --> C["Classify privileged actions + business owners"]
    C --> U["Understand actual usage + dependencies"]
    U --> D["Define desired least-privilege access"]
    D --> R{"Risk/SoD/approval/impact review"}
    R -->|Chưa đạt| Q["Sửa scope hoặc phương án chuyển đổi"]
    Q --> D
    R -->|Đạt| P["Pilot + test negative/positive cases"]
    P --> E["Deploy narrow roles / JIT / policy controls"]
    E --> X["Revoke redundant grants, keys, sessions"]
    X --> V["Readback actual effective access"]
    V --> G{"Đạt desired state?"}
    G -->|Có| A["Close with audit + periodic review"]
    G -->|Không| F["Contain risk, assign remediation owner"]
    F --> V
~~~

### 3.1. Bước 1 — Tìm quyền thực tế chứ không chỉ quyền theo ticket

Nguồn dữ liệu có thể gồm:
- IAM/IGA identity và assignment inventory.
- IdP/Directory groups, nested groups, app assignments.
- PAM account/session inventory.
- SCIM User/Group ở target nếu có.
- Cloud IAM policies, project/resource roles, local ACL.
- Database grants, Kubernetes RBAC, hệ thống CI/CD, secrets manager.
- Local accounts, SSH authorized keys, access keys, service principals.
- Sessions và tokens đã cấp, theo khả năng hệ thống.
- Phê duyệt và thông tin owner/business purpose.

**SCIM không tiêu chuẩn hóa toàn bộ loại entitlement** nói trên. Nếu một target chỉ hỗ trợ User/Group, cần thêm API hoặc báo cáo của ứng dụng để biết role đặc quyền và quyền trực tiếp.

### 3.2. Bước 2 — Phân loại theo mức nguy hiểm và độ rộng

Một cách lập bảng ưu tiên:

| Nhóm | Ví dụ | Hướng kiểm soát |
| --- | --- | --- |
| **Identity/Security control plane** | Gán admin, sửa chính sách MFA, sửa secret/trust. | Rất chặt; tách admin, phê duyệt, session và log độc lập. |
| **Cloud/platform control plane** | Owner/subscription admin, cluster-admin. | Tài nguyên hẹp, JIT/JEA, kiểm soát thay đổi. |
| **Production operations** | Deploy, restart, thay cấu hình production. | Cấp theo project/cluster, môi trường, ticket, thời hạn. |
| **Sensitive data access** | Export dữ liệu nhạy cảm, DB superuser. | Scope dataset/row, masking, SoD, session trace. |
| **Business high impact** | Duyệt hoặc giải ngân thanh toán, sửa tài khoản nhà cung cấp. | Hạn mức, maker–checker và audit theo giao dịch. |
| **Emergency/break-glass** | Tài khoản khôi phục khi IdP/PAM lỗi. | Tách biệt, bảo vệ credential, chỉ kích hoạt trong sự cố. |

Độ ưu tiên không chỉ dựa trên tên “administrator”. Quyền đọc secret hay gán role có thể nguy hiểm hơn quyền ghi một bảng dữ liệu ít nhạy cảm.

### 3.3. Bước 3 — Xác định nhu cầu nghiệp vụ tối thiểu

Cần hỏi **owner của hệ thống và công việc**:

1. Hành động chính xác nào phải thực hiện?
2. Trên tài nguyên/tenant/môi trường nào?
3. Có thể dùng thao tác ít quyền hơn hoặc workflow tự động không?
4. Tần suất và khung thời gian sử dụng?
5. Dữ liệu/khóa nào người dùng có thể tiếp cận gián tiếp?
6. Có xung đột SoD hoặc yêu cầu four-eyes không?
7. Nếu gỡ quyền, ứng dụng/đội vận hành có phương án khôi phục an toàn không?
8. Quyền nào cần cho **ngày thường**, quyền nào chỉ cần **sự cố hiếm gặp**?

Log hoạt động thực tế hữu ích để nhận diện quyền ít dùng, nhưng **không đủ làm căn cứ duy nhất để xóa**: quyền phục hồi khi sự cố có thể không xuất hiện trong log nhiều tháng mà vẫn cần một cơ chế dự phòng được thiết kế đúng.

## 4. Giảm role rộng và thu hẹp phạm vi tài nguyên

### 4.1. Thay admin toàn cục bằng role hẹp

Giả sử engineer có `CloudOwner` trên toàn tenant chỉ để xem log và restart một workload.

| Trước | Sau |
| --- | --- |
| `CloudOwner` toàn tenant. | `ServiceLogReader` ở đúng service/namespace. |
| Có thể gán quyền người khác. | Không có `iam:assign-role`. |
| Có thể sửa mọi tài nguyên. | `service:restart` chỉ qua JIT khi ticket được duyệt. |
| Đặc quyền luôn khả dụng. | Quyền cao chỉ active trong phiên được phép. |
| Khó phân biệt mục đích từng thao tác. | Ticket, resource ID, action và session gắn với audit. |

**Không cần tạo một role riêng cho từng nút bấm**, nhưng nên tạo các capability/role theo nhóm thao tác ổn định và gắn resource scope rõ ràng. Vai trò quá hẹp, quá nhiều hoặc khó vận hành có thể dẫn tới việc người dùng tìm đường vòng; thiết kế cần có governance và trải nghiệm hợp lý.

### 4.2. Resource scope và điều kiện ABAC

Một quyền `secrets:read` vẫn có thể quá rộng. Hãy giới hạn:

~~~text
PERMIT secret:read IF
    subject.accountActive
    AND subject.hasApprovedRole("SecretConsumer")
    AND resource.secretId in subject.approvedSecretRefs
    AND resource.tenantId == subject.tenantId
    AND environment.workloadOrDeviceIdentityVerified
    AND request.purpose matches approved workflow
~~~

Đây là **pseudocode chính sách**, không phải cú pháp của cloud IAM hay sản phẩm vault cụ thể. `request.purpose` chỉ có giá trị khi có căn cứ như ticket/approval hoặc workflow được kiểm chứng; một chuỗi lý do do người dùng nhập không tự nâng quyền.

### 4.3. Tách permission cấp quyền cho người khác

Permission như `iam:grant-admin`, `role:write`, `policy:edit` hoặc quyền thay trust/identity provider có thể dùng để **mở rộng đặc quyền** ngay cả khi role ban đầu trông có vẻ hẹp.

Khi thiết kế least privilege, ngoài thao tác nghiệp vụ còn phải tính:
- Ai có quyền **gán quyền**?
- Ai có quyền **sửa policy/role hierarchy**?
- Ai có quyền **tạo credential** hoặc impersonate?
- Ai có thể **thay đổi audit/logging**?
- Ai có quyền tạo **service principal** hoặc gán quyền cho workload?
- Ai có thể **ủy quyền lại** mà không cần approval?

**Giảm quyền thao tác mà để nguyên quyền tự nâng quyền** thường không đạt mục tiêu.

### 4.4. Role hierarchy và multiple grant paths

Nếu `PlatformAdmin >= PlatformOperator >= PlatformViewer`, người có `PlatformAdmin` kế thừa mọi permission junior. Nhưng quyền có thể đến qua các nhánh khác, ví dụ direct project grant.

~~~text
EffectivePermission(user) =
  union(permissions inherited via assigned roles)
  union(direct/resource grants)
  union(valid delegated/JIT grants)
  subject to applicable deny/ABAC/session controls
~~~

Đây là mô hình khái niệm. Thu hồi một role không tự thu hồi permission có **đường cấp khác**. Cần đánh giá policy engine cụ thể, deny precedence, nested groups và effective authorization.

## 5. JIT và JEA: giảm thời gian và chức năng của đặc quyền

**Just-in-Time (JIT)** tập trung vào **khi nào** quyền được kích hoạt; **Just-Enough Administration (JEA)** tập trung vào **được thao tác gì**. Hai cách bổ sung nhau.

### 5.1. JIT không chỉ là đặt expiration trong ticket

Một luồng JIT đáng tin cần:

1. Identity/account active, được liên kết đúng người.
2. Người dùng đủ điều kiện yêu cầu privilege này.
3. Ticket/task/incident được xác định, có lý do và phạm vi.
4. Approval theo policy, đánh giá SoD và người duyệt độc lập khi cần.
5. MFA/step-up phù hợp rủi ro; cân nhắc phishing-resistant MFA cho quyền cao.
6. Role/capability được kích hoạt **đúng resource và khoảng thời gian**.
7. Thao tác được enforcement tại target và có log/monitor.
8. Hết hạn hoặc dừng ticket thì deactivate/revoke quyền.
9. Đánh giá active session/token/credential có thể còn sử dụng.
10. Readback actual access và đóng workflow khi đạt tiêu chí.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Engineer
    participant P as PAM/JIT Portal
    participant A as Approver/Policy
    participant I as IdP/MFA
    participant T as Target/PEP
    U->>P: Yêu cầu restart service X trong 45 phút
    P->>A: Kiểm tra eligibility, SoD, ticket, scope
    A-->>P: Approve có giới hạn
    P->>I: Yêu cầu xác thực/step-up
    I-->>P: Kết quả AuthN hợp lệ theo policy
    P->>T: Activate service:restart trên resource X
    U->>T: Thao tác đã được phép
    T->>T: Kiểm tra actor, action, resource, session
    T-->>P: Audit outcome
    P->>T: Deactivate/revoke khi hết hạn hoặc bị hủy
    T-->>P: Readback permission/session state
    P-->>U: Hoàn tất và lưu evidence
~~~

**Đến 45 phút** không tự chứng minh đặc quyền đã mất: token/access key/phiên có thể tiếp tục được chấp nhận. Kiểm tra cơ chế **session termination, role removal, token TTL, credential revocation hoặc request-time policy** của target.

### 5.2. JEA: trao một năng lực nhỏ thay vì toàn quyền

Ví dụ người trực cần **restart dịch vụ X**, không cần shell root vô hạn:

| Cách rộng | Cách thu hẹp |
| --- | --- |
| SSH root vào mọi máy production. | Chạy workflow restart được kiểm soát cho service X. |
| Database superuser để chạy một migration. | Migration service account chỉ có quyền schema cần thiết, đúng DB. |
| Cluster-admin để đọc status pod. | Role chỉ đọc tài nguyên cần thiết trong namespace cụ thể. |
| Global IAM admin để thêm một user vào group. | Delegated group membership management chỉ cho group được chỉ định. |
| Owner toàn subscription để xem metrics. | Reader/Monitoring role trong resource group được phép. |

Tên role và khả năng thực tế **phụ thuộc nền tảng**. Không tự triển khai một policy hẹp nếu quyền bên trong cho phép tạo role cao hơn, sửa binary/script chạy với đặc quyền hoặc vượt sang namespace khác.

### 5.3. Eligible, activated và effective

| Trạng thái | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Eligible** | Có thể yêu cầu quyền khi đủ điều kiện. | Engineer được phép xin quyền restart qua PAM. |
| **Active** | Một grant/capability đã kích hoạt theo workflow. | Ticket cho phép restart từ 10:00 đến 10:45. |
| **Effective** | Target thực sự chấp nhận thao tác theo policy hiện tại. | API chỉ cho restart service X; từ chối service Y. |
| **Revoked** | Quyền kích hoạt/credential liên quan đã bị vô hiệu hóa theo phạm vi cần thiết. | API restart ngoài ticket bị từ chối sau 10:45. |

JIT làm giảm **thời lượng exposure**; JEA làm giảm **độ rộng permission**. Một JIT `GlobalAdmin` trong nhiều giờ vẫn có thể quá rộng; một role hẹp nhưng luôn active có thể không phù hợp với chức năng đặc biệt nhạy cảm.

## 6. PAM, credential vault và privileged session

**Privileged Access Management (PAM)** quản lý các đường truy cập đặc quyền, có thể gồm yêu cầu/duyệt quyền, cấp credential, vault, brokered session, giám sát và ghi lại hành động. Nhưng PAM là **một thành phần kiểm soát**, không tự bảo đảm mọi quyền ngoài PAM đã biến mất.

### 6.1. Credential checkout và session brokering

Hai mô hình thường gặp:

- **Credential checkout:** người được phép lấy hoặc sử dụng một credential đặc quyền trong thời hạn chính sách. Cần biết credential có thể bị sao chép, ghi nhớ hoặc tiếp tục sử dụng ngoài PAM không; rotation/revocation phải phù hợp.
- **Brokered/proxied session:** PAM kết nối tới target thay người dùng, có thể giảm việc lộ credential và kiểm soát phiên/hành động. Cần kiểm tra khả năng target vẫn cho truy cập trực tiếp bằng credential khác hay không.

**Ghi hình session không làm quyền trở nên ít hơn.** Session recording phục vụ kiểm toán/điều tra; việc giới hạn action, scope và time phải thực hiện riêng.

### 6.2. Tài khoản dùng chung và accountability

Một account `root` hoặc `Administrator` truyền thống có thể được nhiều người sử dụng. Điều này gây khó liên kết thao tác với identity người thực.

Nếu nền tảng bắt buộc duy trì account chung hoặc break-glass:
- Chỉ dùng qua PAM/broker khi khả thi.
- Xác thực người yêu cầu bằng danh tính cá nhân, ghi actor/ticket.
- Giới hạn người và thời gian sử dụng.
- Bảo vệ/rotate credential sau sử dụng khi cần.
- Giám sát hoạt động và lưu dấu vết phiên theo chính sách.
- Đánh giá lại khả năng chuyển sang **named privileged accounts** hoặc delegated capabilities.

**Không gán tài khoản chung cho một người trên hệ thống IAM chỉ để làm đẹp inventory**, trong khi thực tế nhiều người vẫn dùng chung credential.

### 6.3. Session termination là kiểm soát riêng

Khi hạ quyền, có thể cần:
- Thu hồi PAM approval/grant.
- Ngắt phiên đang active theo khả năng sản phẩm.
- Revoke session tokens hoặc short-lived credentials.
- Rotate credential cũ nếu có người đã biết hoặc có thể tiếp tục sử dụng.
- Kiểm tra local account và access key ngoài PAM.
- Xác minh request mới bị chặn.

Mức độ thu hồi **tức thời** khác nhau giữa hệ thống. Đặt **revocation SLA** theo rủi ro; không hứa “gỡ role là mọi SSH/DB session kết thúc ngay”.

## 7. MFA và điều kiện ngữ cảnh cho quyền đặc biệt

Một account admin có thể yêu cầu **phishing-resistant MFA**, step-up gần thời điểm thực hiện thao tác, thiết bị quản lý hoặc điều kiện rủi ro. Tuy nhiên:

- **MFA là AuthN:** chứng minh người dùng kiểm soát authenticator theo chính sách.
- **Authorization:** xác định role, resource, action, thời gian và workflow.
- **PAM/JIT:** kiểm soát activation và phiên đặc quyền.
- **Audit:** quan sát ai làm gì và có đúng căn cứ không.

Ví dụ:

~~~text
mayDeleteProductionSecret =
    subject.lifecycleStatus == ACTIVE
    AND subject.hasApprovedPermission("secret:delete")
    AND resource.secretId in approvedChange.scope
    AND approvedChange.status == APPROVED
    AND approvedChange.isActiveAt(now)
    AND authentication.methodSatisfies(PRIVILEGED_MFA_POLICY)
    AND authentication.recentEnough
    AND noApplicableSoDConflict
~~~

**Dùng MFA mạnh nhưng vẫn có `secret:delete-all` toàn tổ chức** là một hệ thống có bảo vệ đăng nhập tốt nhưng **chưa giảm đặc quyền đủ**. Ngược lại, role hẹp nhưng đăng nhập bằng credential yếu cũng có rủi ro. Cần cả hai.

### 7.1. Step-up không phải tự động tăng quyền

Một token OIDC chứa `amr/acr` có thể cung cấp tín hiệu về phương thức/mức assurance nếu IdP và ứng dụng thống nhất ngữ nghĩa. Nó **không tự chứng minh** actor đã được duyệt quyền admin hay target có thể bỏ qua resource scope. Ứng dụng phải kiểm tra token/issuer/audience, ràng buộc phiên và thực hiện authorization riêng.

### 7.2. Session của admin nên tách khỏi phiên thường ngày

Tổ chức có thể dùng **privileged account riêng**, browser profile/thiết bị quản trị hoặc môi trường truy cập an toàn theo chính sách. Ưu điểm là giảm khả năng một phiên ứng dụng thường ngày hoặc phishing thấp cấp trở thành đường đi trực tiếp tới admin.

Nhưng việc tạo account riêng cũng phát sinh **identity binding, credential lifecycle và inventory**. Khi Mover/Leaver, phải thu hồi **tài khoản thường và tất cả privileged accounts liên kết**, không chỉ account SSO chính.

## 8. Separation of Duties và phòng tự nâng quyền

**Segregation of Duties (SoD)** hạn chế một chủ thể thực hiện hoặc nắm đồng thời các chức năng xung đột. Trong giảm đặc quyền, SoD đặc biệt quan trọng vì một quyền có thể được dùng để **tự phê duyệt quyền cao hơn**.

### 8.1. Ví dụ xung đột

| Cặp năng lực | Rủi ro | Cách kiểm soát |
| --- | --- | --- |
| Tạo tài khoản + tự cấp GlobalAdmin. | Tự nâng quyền hoặc tạo backdoor identity. | Approval độc lập và tách grant authority. |
| Sửa mã nguồn + tự phê duyệt release production. | Thay đổi không được rà soát. | Four-eyes/branch protection/release workflow. |
| Tạo giao dịch + phê duyệt cùng giao dịch. | Gian lận hoặc sai sót không được phát hiện. | Transaction-level maker–checker. |
| Quản trị secret vault + xóa audit log. | Khả năng che giấu truy cập credential. | Tách quyền log và quyền vault. |
| Quản lý chính sách MFA + vô hiệu hóa logging. | Hạ bảo vệ mà không có dấu vết. | Role separation và kiểm toán độc lập. |

**Static SoD (SSD)** thường ngăn phân công các role xung đột; **Dynamic SoD (DSD)** giới hạn kích hoạt đồng thời; **transaction-level SoD** kiểm tra quan hệ trên giao dịch cụ thể. Cần hiểu mô hình thực thi của ứng dụng. Một senior role có thể kế thừa cả hai permission xung đột, vì vậy chỉ kiểm tra role được gán trực tiếp có thể bỏ sót rủi ro.

### 8.2. Quyền thay đổi policy là một đặc quyền nhạy cảm

Nếu người giữ `ReportReader` có thể sửa policy để biến mình thành `ReportAdmin`, việc hạ quyền đọc/ghi trên báo cáo không có nhiều ý nghĩa.

Khi phân tích giảm quyền, cần hỏi:
- User có thể thay đổi **IAM role mappings** hoặc group assignment?
- Có thể sửa **PDP policy** hoặc resource policy?
- Có thể tạo **API key** cho tài khoản khác?
- Có thể giả danh/service account impersonation?
- Có thể tự cấp **JIT eligibility** hoặc phê duyệt ticket của mình?
- Có thể vô hiệu hóa **MFA, monitoring hoặc log retention**?

**Đường leo thang đặc quyền** phải được tính vào *effective risk*, không chỉ số role.

## 9. Quan hệ RBAC/ABAC, IdP/SSO và SCIM

~~~mermaid
flowchart LR
    HR["HRIS/Contractor source"] --> IAM["IAM/IGA: JML, approvals, desired access"]
    IAM --> PAM["PAM/JIT: eligibility + activation"]
    IAM --> PROV["SCIM/API/manual provisioning"]
    PROV --> APP["Targets: account, group, roles, policies"]
    IAM --> IDP["IdP: identity, SSO, MFA"]
    IDP --> APP
    PAM --> APP
    APP --> AUTHZ["RBAC/ABAC/PEP: effective authorization"]
    AUTHZ --> RECON["Reconciliation + audit"]
    RECON --> IAM
~~~

**Cần tách nhiệm vụ của từng lớp:**

| Lớp | Làm được gì? | Không đủ để chứng minh điều gì? |
| --- | --- | --- |
| **HRIS/IAM** | Xác định quan hệ làm việc, owner và desired access. | Target đã thực thi tất cả thay đổi. |
| **IdP/SSO** | Xác thực account, MFA, phát session/token/claims. | User có quyền trên mọi tài nguyên. |
| **SCIM** | Tạo/cập nhật/disable User/Group theo provider capability. | Mọi privileged role, local key và session đã bị gỡ. |
| **RBAC** | Gom permission vào role và kế thừa theo hierarchy. | Resource scope và tình trạng ngữ cảnh luôn hợp lệ. |
| **ABAC** | Giới hạn theo subject/resource/action/environment. | Entitlement cũ ở ứng dụng khác tự bị xóa. |
| **PAM/JIT** | Quản lý activation/credential/session đặc quyền theo thiết kế. | Đường trực tiếp ngoài PAM đã bị chặn. |
| **PEP/ứng dụng** | Thực thi quyết định trên tài nguyên/action. | Quyết định đúng nếu dữ liệu role/attribute sai. |
| **IGA/reconciliation** | Đối chiếu actual vs desired và mở remediation. | Một ticket đóng nghĩa là đã hết mọi token. |

### 9.1. SCIM Group khác privileged role nội bộ

SCIM chuẩn hóa User/Group và thao tác provisioning phổ biến, nhưng **không có nghĩa một SCIM Group tương đương một privileged role trong mọi SaaS, database, cloud hay Kubernetes**. Một app có thể:
- Dùng SCIM Groups để ánh xạ role.
- Dùng API riêng để gán admin role.
- Còn **direct grants** ngoài group.
- Giữ admin account local không phụ thuộc IdP.
- Tạo session/token được quản lý bởi bộ phận khác.

Khi gỡ group ở IdP hoặc qua SCIM, cần xác minh **đúng target privileged capability** đã mất.

### 9.2. SSO thành công không phải authorization thành công

Một người bị hạ từ admin xuống viewer vẫn có thể đăng nhập qua SSO và đọc dữ liệu hợp lệ. Đây là kết quả mong muốn: **giảm đặc quyền nhưng không chặn toàn bộ công việc**. Ngược lại, người dùng có role admin trong ứng dụng nhưng đã nghỉ việc phải bị chặn theo JML; không dùng role cũ làm lý do kích hoạt account.

## 10. Joiner: bắt đầu không có đặc quyền dư thừa

Joiner thường được provision **baseline quyền cho công việc hàng ngày**. Nếu một vai trò mới cần quyền nhạy cảm, không nên tự cấp admin toàn tổ chức chỉ vì job title chứa “Engineer”, “Manager” hoặc “Administrator”.

### 10.1. Workflow onboarding cho privileged access

1. HRIS/sponsor xác nhận identity, quan hệ và thời gian bắt đầu.
2. IAM/IGA xác minh person/account binding, tenant và bộ phận.
3. Business owner định nghĩa **role nền** và **nhu cầu privileged eligibility** riêng.
4. Áp least privilege/SoD, approval và hạn dùng nếu có.
5. Cấp regular account; tạo privileged account **chỉ nếu có căn cứ** và gắn owner.
6. Thiết lập phishing-resistant MFA/step-up, PAM enrollment hoặc cơ chế tương ứng theo policy.
7. Không kích hoạt privilege trước mốc hiệu lực, trừ ngoại lệ onboarding được duyệt.
8. Provision target roles/permissions đúng scope; kiểm chứng readback.
9. Kiểm tra một **hành động cho phép** và một **hành động phải bị từ chối**.
10. Ghi audit, hướng dẫn truy cập quyền cao qua đường chính thức.

### 10.2. Phân biệt eligibility và assignment thường trực

~~~text
Employee: new platform engineer
Standing role: production-observer
Privileged eligibility: may request scoped restart operator
Activation conditions:
   - approved incident/change ticket
   - approved cluster/service
   - short time window
   - MFA assurance satisfied
   - no applicable SoD conflict
~~~

Ví dụ trên là **mô hình khái niệm**, không phải thông tin credential hoặc lệnh production. Người mới có thể làm nhiệm vụ quan sát ngay khi account active, nhưng quyền restart chỉ xuất hiện khi có nhiệm vụ cụ thể.

### 10.3. Không dùng employee identifier làm bí mật khởi tạo

Employee number, email hoặc tên manager chỉ là dữ liệu nhận diện/thuộc tính, không phải bằng chứng đủ để tạo privileged account, reset MFA hoặc cấp quyền. **Identity proofing và authenticator binding** cần quy trình được phê duyệt. Một account admin được cấp cho **nhầm người** vẫn nguy hiểm dù role hẹp.

## 11. Mover: giảm quyền cũ trước khi quyền mới mở rộng

Mover là sự kiện một người đổi vai trò, bộ phận, môi trường phụ trách hoặc trách nhiệm. Đây là nguồn lớn của **privilege accumulation**: quyền mới được thêm, nhưng quyền cũ không được gỡ.

### 11.1. Mô hình KEEP / REMOVE / GRANT / REVIEW

| Phân loại | Ví dụ | Quy tắc |
| --- | --- | --- |
| **KEEP** | Quyền đọc tài liệu chung còn hợp lệ. | Duy trì theo assignment hiện hành. |
| **REMOVE** | Production Admin của nhóm cũ. | Thu hồi đúng hiệu lực, kiểm tra session/token. |
| **GRANT** | Quyền Finance Report Reader mới. | Chỉ cấp theo policy/approval/SoD. |
| **REVIEW** | Break-glass eligibility, JIT grant đang active, quyền dự án tạm. | Xác định owner, thời hạn và căn cứ còn hiệu lực. |

Đối với role nhạy cảm, cần xem **thứ tự chuyển đổi**: tránh giai đoạn người dùng đồng thời giữ hai quyền xung đột do quyền mới được cấp trước khi quyền cũ được thu hồi. Có thể yêu cầu phê duyệt hoặc workflow giảm quyền cũ/kiểm chứng rồi mới kích hoạt quyền mới, tùy yêu cầu liên tục công việc.

### 11.2. Một ví dụ Mover từ Operations sang Finance

~~~mermaid
sequenceDiagram
    autonumber
    participant HR as HRIS
    participant IAM as IAM/IGA
    participant PAM as PAM/JIT
    participant IDP as IdP/SSO
    participant APP as Applications / Cloud / DB
    HR->>IAM: Mover effectiveAt: Operations -> Finance
    IAM->>IAM: Tính KEEP/REMOVE/GRANT, SoD, scope
    IAM->>PAM: Hủy eligibility/activation production không còn hợp lệ
    IAM->>IDP: Gỡ nhóm/role cũ, cập nhật attributes
    IAM->>APP: SCIM/API/manual revoke direct + inherited target grants
    IAM->>APP: Kiểm soát session/token/credential còn dùng
    IAM->>APP: Cấp role Finance đã được phê duyệt khi hợp lệ
    APP-->>IAM: Readback actual roles + negative access tests
    IAM->>IAM: Đóng hoặc mở remediation theo trạng thái
~~~

**Không tự suy ra nhóm cũ biến mất khỏi IdP thì privileged session ở database đã ngừng.** Target có thể cho tồn tại session đến hết thời hạn hoặc credential hoạt động độc lập.

### 11.3. Nhiều assignment và thời gian bàn giao

Một người có thể còn nhiệm vụ trực vận hành hợp lệ trong bảy ngày sau khi chuyển nhóm. Thay vì giữ `GlobalAdmin` vô hạn, có thể thiết kế:
- Project/cluster scope rõ.
- Hạn `effectiveUntil`.
- Quyền hẹp theo action/incident.
- Owner phê duyệt và theo dõi SoD.
- Revoke/readback vào mốc hết hạn.
- Không dùng assignment ngoại lệ để tránh trách nhiệm bàn giao.

**Một quyền đang được dùng hợp lệ có thể cần giữ ngắn hạn**. Giảm đặc quyền phải dựa trên nhu cầu công việc, không xóa máy móc khiến việc vận hành an toàn thất bại.

## 12. Leaver: đặc quyền phải mất cùng quyền truy cập bắt buộc

Với Leaver, mục tiêu thường là **chặn khả năng truy cập theo quan hệ làm việc đã kết thúc**, bao gồm tất cả privileged accounts và đường credential liên quan.

### 12.1. Checklist offboarding đặc quyền

| Đối tượng | Hành động cần đánh giá | Readback phải chứng minh |
| --- | --- | --- |
| **Identity/IdP** | Disable/chặn account chính đúng effective time. | Login mới theo SSO bị từ chối. |
| **Privileged accounts** | Disable named admin accounts và local accounts còn liên kết. | Không tạo phiên quản trị mới được. |
| **PAM/JIT eligibility** | Gỡ quyền được xin elevation. | Không thể yêu cầu/kích hoạt quyền admin qua PAM. |
| **Active PAM sessions** | Hủy/đóng phiên theo khả năng sản phẩm. | Session không còn cho thao tác. |
| **Cloud/DB/Kubernetes grants** | Gỡ role, group, direct grants và federation/impersonation quyền cũ. | Effective permission không còn đường cấp. |
| **Tokens/SSH keys/certificates** | Revoke hoặc rotate phù hợp rủi ro/khả năng target. | Credential liên quan không còn dùng được theo phạm vi yêu cầu. |
| **Service identities** | Chuyển ownership và thu hồi quyền cá nhân. | Người cũ không thể quản lý secret/role của workload. |
| **Local apps/API** | Disable/deprovision các account và personal tokens ngoài SSO. | Không còn access path tồn dư. |
| **Audit** | Liên kết HR event, actor, target, timestamp và kết quả. | Có thể giải trình và mở remediation nếu chưa đạt. |

### 12.2. Tại sao disable IdP chưa đủ?

Một local DB superuser, personal access token hoặc SSH key có thể không cần đăng nhập SSO trong từng request. Nếu chỉ disable IdP, các đường này có thể tiếp tục hoạt động. Với nhiều ứng dụng, access token đã phát hành có thể còn hiệu lực cho tới `exp` hoặc khi resource server nhận được tín hiệu chặn.

**Phải kiểm tra thực tế mỗi hệ thống đích**, không đóng Leaver chỉ vì cổng SSO trả “Account disabled”.

### 12.3. Rehire và quyền cũ

Tái tuyển không đồng nghĩa khôi phục đặc quyền trước đó. Cần identity correlation đúng người, quan hệ làm việc mới, approval mới, scope mới và kiểm chứng MFA/binding. Một người có cùng email hoặc employee ID không được tự nhận lại `CloudOwner` hoặc `DBAdmin` đã từng có.

## 13. Tài khoản dịch vụ và workload: giảm đặc quyền mà không cắt nhầm dịch vụ

**Service account, workload identity và máy–máy credential** có thể nắm đặc quyền rất lớn, đôi khi tồn tại lâu hơn bất kỳ nhân viên nào. Chúng cần inventory, owner và lifecycle riêng.

### 13.1. Ví dụ một workload bị cấp quá rộng

~~~text
Workload: billing-etl
Current role: DatabaseSuperuser
Actual function:
  - SELECT dữ liệu hóa đơn thuộc tenant-vn
  - INSERT vào bảng tổng hợp đã chỉ định
  - Không tạo user/schema, không xem secret khác

Desired access:
  - SELECT đúng bảng/view và tenant được phép
  - INSERT đúng bảng đích
  - Không có DDL, role management hoặc unrestricted export
  - Workload identity binding + credential rotation/revocation
~~~

Nếu chỉ thay role `DatabaseSuperuser` bằng `DatabaseReadWriteAll`, quyền vẫn có thể quá rộng. Cần phân tích **câu lệnh/tài nguyên** thực tế, khả năng vượt scope và tác động tới job.

### 13.2. Owner con người nghỉ việc

Khi engineer quản lý service account Mover/Leaver:
1. Xác định owner team/business purpose của workload.
2. Thu hồi quyền cá nhân của người cũ vào CI/CD, secret manager, cloud IAM và config.
3. Rotate credential nếu người cũ từng có thể trích xuất hoặc còn bản sao.
4. Kiểm tra workload có cần tiếp tục hoạt động không.
5. Giữ quyền tối thiểu hợp lệ cho workload nếu còn nhu cầu.
6. Chuyển owner và xác minh không còn truy cập qua account người cũ.
7. Deprovision workload khi dịch vụ kết thúc.

**Không tự xóa tài khoản dịch vụ đang chạy chỉ vì một cá nhân rời công ty**, nhưng không để **orphaned workload identity** thiếu người chịu trách nhiệm hoặc secret chưa được quản lý.

### 13.3. Non-human AuthN khác MFA của người

Workload có thể dùng managed identity, workload federation, mTLS hoặc private-key JWT. Điều này chứng minh quyền kiểm soát credential/trust của workload, **không tự đồng nghĩa MFA của một người**. Phải xây policy theo loại chủ thể: human privileged access có MFA và PAM; workload có trust binding, short-lived credential, scope, provenance và audit phù hợp.

## 14. Break-glass: giữ khả năng khẩn cấp nhưng không tạo cửa hậu

Trong sự cố IdP/PAM mất khả dụng, tổ chức có thể cần đường **break-glass** để khôi phục hệ thống. Mục tiêu của giảm quyền không phải xóa mọi khả năng khôi phục; mà là **giảm số account, đối tượng và thời gian đặc quyền khẩn cấp không kiểm soát**.

Một break-glass design cần:
- **Mục đích và tình huống kích hoạt** được mô tả trước.
- Account/credential được bảo vệ độc lập và giới hạn người có thể sử dụng.
- Tách biệt phù hợp với dependency có thể lỗi; không thiết kế một phương án khẩn cấp luôn phụ thuộc đúng IdP đang gặp sự cố.
- Phạm vi tài nguyên vừa đủ, hạn chế lạm dụng.
- Cơ chế cảnh báo, audit, session recording khi khả thi.
- Quy trình phê duyệt/ủy quyền khẩn cấp phù hợp tính sẵn sàng.
- Rotation/revocation và review sau sử dụng.
- Kiểm thử định kỳ, kiểm soát storage và recovery.

**Không cấp `GlobalAdmin` thường trực cho mọi thành viên trực vận hành “đề phòng sự cố”**. Nếu phải duy trì một số quyền khẩn cấp rộng hơn, hãy coi chúng là ngoại lệ nhạy cảm với owner, chứng cứ và giám sát rõ.

### 14.1. Tránh fail-open khi PAM hoặc PDP lỗi

Nếu PAM không phục vụ hoặc policy engine timeout, một thiết kế nguy hiểm là bỏ qua tất cả kiểm soát và cho mọi admin vào trực tiếp. Thay vào đó, quy định **fail-safe** cho đường thông thường và cơ chế break-glass **riêng, đã được đánh giá**.

**Bỏ qua chữ ký token, tắt MFA toàn tenant hoặc disable audit** không phải phương án giảm đặc quyền an toàn.

## 15. Cách phân tích và thu hồi các đường quyền ẩn

### 15.1. Role hierarchy và nested group

Một user có thể nhận quyền `secrets:read` qua role senior hoặc group lồng nhau. Gỡ một group không đủ nếu còn:
- Another senior role inheriting same permission.
- Direct grant trên resource policy.
- Local account có role tương đương.
- Token/credential có scope độc lập.
- Delegated role, impersonation hoặc trust relationship.
- Temporary exemption vẫn còn hiệu lực.

**Đường quyền effective** cần được tìm ở **target permission engine** chứ không chỉ ở công cụ IAM.

### 15.2. “Không thấy role admin” vẫn có thể là admin

Một user có thể sở hữu project, resource group, workload/service principal hoặc có quyền chỉnh policy. Họ có thể **gán quyền cho chính mình** hoặc tạo credential mới có privilege cao.

Khi tìm privileged exposure, nên tìm cả các permission **quản lý quyền, sửa policy, impersonation, tạo token/secret và thay đổi cơ chế bảo vệ**. Không chỉ lọc danh sách tên role chứa “Admin”.

### 15.3. Token và phiên hiện hành

Một access token có thể biểu thị scope/role tại thời điểm phát hành. Khi IAM gỡ role:
- Với token tự chứa, resource server có thể vẫn chấp nhận đến hết hạn.
- Với introspection hoặc request-time policy, quyền có thể được đánh giá lại.
- Refresh token có thể cấp token mới nếu chưa revoke và policy cho phép.
- PAM/SSH/DB session có thể tồn tại theo lifecycle riêng.
- Direct API key có thể không liên quan tới IdP user session.

**Không có bảo đảm chung rằng thay đổi nhóm IdP lan ngay tới mọi ứng dụng**. Cần chọn chiến lược theo sensitivity: short-lived tokens, revocation, session termination, policy re-evaluation hoặc containment, rồi readback.

### 15.4. Data-plane và control-plane quyền khác nhau

- **Control plane:** sửa policy, role, account, cấu hình, resource.
- **Data plane:** đọc/sửa dữ liệu hoặc gọi chức năng nghiệp vụ.

Một role có quyền đọc dữ liệu nhạy cảm toàn bộ có thể rủi ro cao dù không điều khiển control plane; một role chỉ sửa policy có thể mở đường tới mọi dữ liệu. Phải đánh giá **tác động trực tiếp và khả năng leo thang gián tiếp**.

## 16. Thực thi giảm quyền theo thay đổi có kiểm soát

Giảm quyền hàng loạt không nên triển khai chỉ bằng một danh sách “admin chưa dùng trong 90 ngày” rồi xóa ngay, vì quyền phục hồi hiếm dùng hoặc các dependency ẩn có thể cần thiết.

### 16.1. Một quy trình rollout từng bước

| Giai đoạn | Công việc | Bằng chứng hoàn tất |
| --- | --- | --- |
| **Discover** | Thu thập identity, privileged accounts, roles, grant paths và usage. | Inventory có owner, target, scope, last reviewed. |
| **Design** | Định nghĩa role/JIT/JEA/scoped alternative theo yêu cầu công việc. | Desired access policy và threat/SoD review. |
| **Approve** | Business owner và security owner xác nhận. | Ticket/approval, effectiveAt, fallback. |
| **Pilot** | Kiểm thử trong môi trường phù hợp hoặc nhóm nhỏ. | Positive/negative test và impact findings. |
| **Cutover** | Provision quyền hẹp, bật policy enforcement. | Readback role mới và thao tác hợp lệ hoạt động. |
| **Revoke** | Gỡ role rộng, direct grants, token/credential paths không còn căn cứ. | API/trust/session state sau thu hồi. |
| **Verify** | Kiểm tra thao tác lẽ ra bị chặn và telemetry. | Effective access đúng policy. |
| **Sustain** | Access review, expiry, exception lifecycle, drift detection. | Remediation owner và báo cáo định kỳ. |

### 16.2. Kiểm thử cả cho phép và từ chối

Một thay đổi chỉ được xem là an toàn nếu:
- **Positive tests:** người dùng/workload vẫn làm được thao tác cần thiết trên tài nguyên được duyệt.
- **Negative tests:** không thể thực hiện hành động không cần thiết hoặc trên resource ngoài scope.
- **Boundary tests:** hết thời gian, đổi tenant/project, thay role, JIT bị hủy.
- **Failure tests:** PDP/PAM không khả dụng, token cũ, thuộc tính thiếu hoặc stale.
- **JML tests:** Mover/Leaver có tác động thực tế khi đến effective time.

**Dấu hiệu giảm quyền thành công không phải tỷ lệ HTTP 403 tăng**, mà là đúng phạm vi **những thao tác không được phép bị chặn trong khi công việc hợp lệ vẫn hoạt động**.

### 16.3. Rollback không được khôi phục quyền rộng vô điều kiện

Nếu role mới quá hẹp và cản công việc, rollback có thể là một **exception time-bound** hoặc thêm một permission cần thiết theo review, **không** mặc định tái cấp `GlobalAdmin` vĩnh viễn.

Nếu phải dùng quyền rộng trong sự cố, áp PAM/JIT, owner và audit, đặt mốc hết hạn, rồi phân tích root cause để cải tiến role design.

## 17. Pseudocode xác định giảm đặc quyền hiệu quả

Pseudocode dưới đây minh họa cách kiểm soát một thay đổi, không phải phần mềm production hay cú pháp tiêu chuẩn của IAM/PAM.

~~~text
function reducePrivilege(identity, target, desiredPolicy):
    assert identity is verified and target is in scope
    current = discoverActualAccess(identity, target)

    paths = enumerateGrantPaths(
        directRoles=current.directRoles,
        inheritedRoles=current.roleHierarchy,
        nestedGroups=current.groups,
        resourcePolicies=current.resourcePolicies,
        delegatedAccess=current.delegations,
        credentials=current.credentials,
        sessions=current.sessions
    )

    proposed = calculateLeastPrivilege(
        businessNeed=desiredPolicy.approvedTasks,
        permittedActions=desiredPolicy.actions,
        resourceScope=desiredPolicy.scope,
        validTime=desiredPolicy.timeWindow,
        policyConstraints=desiredPolicy.conditions
    )

    impact = simulatePositiveAndNegativeCases(paths, proposed)
    require impact.legitimateOperationsRemainPossible
    require impact.disallowedPrivilegeNoLongerEffective
    require approvalsAndSoDChecksPass(identity, proposed)

    provisionNarrowAccess(identity, target, proposed)
    verifyApprovedWorkflows(identity, target)

    revokeRedundantEntitlements(identity, target, current, proposed)
    reviewSessionsTokensAndCredentials(identity, target)
    verifyActualEffectiveAccess(identity, target, proposed)

    if anyUnapprovedAccessPathStillWorks:
        openRemediationWithOwnerAndContainment()
        return PENDING_RECONCILIATION

    recordAuditEvidence()
    return VERIFIED
~~~

**Hạn chế:** nhiều hệ thống không có API enumerating all grant paths, không bảo đảm atomic update xuyên ứng dụng và không thể xác minh bằng cách thử mọi API. Thực tế cần kết hợp inventory, provider-specific query, log, policy simulation, targeted negative tests và quy trình remediation.

### 17.1. Nguyên tắc không cấp đặc quyền mới trong quá trình “giảm quyền”

Một workflow giảm quyền có thể cần một **automation identity** để thực hiện revocation. Identity đó cũng phải được quản trị:
- Quyền cấp/thu hồi được giới hạn theo target/role.
- Không cho script tự gán `GlobalAdmin` cho chính nó.
- Credential/time window và owner rõ ràng.
- Log actor, request ID, target account và kết quả.
- Kiểm soát chống tác động nhầm tenant hoặc account.
- SoD/approval cho thay đổi đặc quyền nhạy cảm.

**Công cụ giảm quyền không được trở thành một tài khoản siêu quyền không kiểm soát.**

## 18. Ví dụ khai báo access JIT có scope

Một cấu hình nội bộ minh họa:

~~~yaml
requestId: pam-jit-2026-041
subject:
  iamIdentityId: person-2048
  idpAccountRef: idp-user-581
  privilegedAccountRef: ops-admin-2048
target:
  application: production-platform
  tenant: tenant-vn
  resource: cluster-vn-2/service-catalog
grant:
  action: service:restart
  role: ScopedRestartOperator
  standing: false
  validFrom: 2026-12-02T10:00:00+07:00
  validUntil: 2026-12-02T10:45:00+07:00
conditions:
  approvedTicketRef: INC-2026-482
  requirePrivilegedMfa: true
  allowDirectCredentialCheckout: false
  requireNoSoDConflict: true
review:
  owner: production-platform-owner
  approvalRef: APPROVAL-882
  verificationStatus: PENDING
~~~

Đây **không phải YAML của sản phẩm PAM cụ thể** và không tự tạo quyền khi lưu. Giá trị như `allowDirectCredentialCheckout: false` chỉ có tác dụng khi access broker và target thật sự áp policy tương ứng. **Đặc biệt cần kiểm chứng rằng đường đăng nhập trực tiếp ngoài PAM không bỏ qua workflow JIT**.

### 18.1. Ví dụ minh họa kết quả audit

~~~json
{
  "eventId": "privilege-reduction-2026-310",
  "correlationId": "iam-mover-2048",
  "identityId": "person-2048",
  "targetRef": "production-platform",
  "before": {
    "effectiveAdminActions": ["service:restart", "iam:assign-role", "secret:read-all"],
    "scope": "tenant-wide",
    "grantType": "STANDING"
  },
  "after": {
    "standingActions": ["service:status:read"],
    "eligibleJitActions": ["service:restart"],
    "scope": "cluster-vn-2/service-catalog"
  },
  "execution": {
    "ownerRef": "production-platform-owner",
    "approvalRef": "APPROVAL-882",
    "roleRevocation": "SUCCEEDED",
    "sessionTokenReview": "COMPLETED"
  },
  "verification": {
    "actualAccessReadback": "PASSED",
    "deniedActionsTested": ["iam:assign-role", "secret:read-all"],
    "status": "VERIFIED"
  }
}
~~~

**Đây là schema audit nội bộ minh họa**, không phải log chuẩn của SCIM, OIDC hoặc PAM. `sessionTokenReview: COMPLETED` chỉ có ý nghĩa nếu được gắn bằng chứng cụ thể; không nên ghi “Completed” bằng thủ công khi chưa kiểm tra target. Không ghi mật khẩu, private key, full token, OTP hay nội dung nhạy cảm của session vào sự kiện báo cáo không cần thiết.

## 19. Kiểm toán, access review và trách nhiệm giải trình

### 19.1. Một grant đặc quyền cần có dữ liệu gì?

| Trường | Mục tiêu |
| --- | --- |
| Identity và account ID | Liên kết đúng người/workload với account đích. |
| Role/grant ID và scope | Biết quyền cụ thể được cấp ở đâu. |
| Business justification | Tại sao cần quyền; nhiệm vụ nào. |
| Owner/approver | Ai chịu trách nhiệm và phê duyệt. |
| Source assignment và JML event | Quyền phát sinh từ sự kiện nhân sự/công việc nào. |
| Time window/expiration | Khi nào quyền có hiệu lực và phải mất. |
| AuthN assurance/condition | Điều kiện truy cập nhạy cảm nào phải đạt. |
| Grant path | Quyền trực tiếp, kế thừa, group, policy hay session. |
| Provisioning/execution result | Lệnh cấp/gỡ có được target chấp nhận không. |
| Readback/negative test | Quyền ngoài scope có thực sự bị chặn không. |
| Remediation owner/status | Nếu còn residual access, ai xử lý trước khi nào. |

### 19.2. Access review nên tập trung vào effective privilege

Một kỳ rà soát chỉ liệt kê “User nào có role `Admin`” sẽ bỏ sót:
- Role tên khác nhưng có `iam:grant-admin`.
- Nested group/role hierarchy gián tiếp.
- Resource-based policy grant.
- Local root/DB admin và API keys.
- Service principals và workload identities.
- PAM/JIT eligibility không sử dụng nhưng vẫn có thể activate.
- Tokens/privileged sessions có khả năng tiếp tục dùng.

Access review cần cung cấp **quyền effective và lý do**, ưu tiên quyền có **impact lớn hoặc không có usage/căn cứ rõ**, nhưng không tự kết luận “không dùng” nghĩa là không cần.

### 19.3. Tách log quyết định và log thực thi

- **Decision log:** ai đã phê duyệt quyền/scope và vì sao.
- **Provisioning log:** connector đã cấp/gỡ entitlement nào.
- **PAM activation log:** ai xin JIT, dùng account nào, trong thời gian nào.
- **Target enforcement log:** thao tác nào được Permit/Deny thực tế.
- **Readback/reconciliation evidence:** target hiện còn những đường quyền nào.
- **Incident/remediation log:** khi thực thi thất bại, owner nào khắc phục.

Một log `SCIM PATCH 200` **không thay thế** log kiểm chứng rằng user không còn quyền làm thao tác admin tại hệ thống đích.

## 20. Chỉ số giảm đặc quyền và cách tránh tối ưu sai

| Chỉ số | Định nghĩa tham khảo | Cần cảnh giác |
| --- | --- | --- |
| **Standing privileged identities** | Số identity/account có đặc quyền cao thường trực trong phạm vi. | Chỉ đếm tên role `Admin` mà bỏ quyền tương đương. |
| **Privileged exposure hours** | Tổng thời gian đặc quyền nhạy cảm active theo target/identity trong phạm vi. | Không tính session/token sống sau khi grant hết hạn. |
| **JIT adoption** | Tỷ lệ hoạt động đặc quyền phù hợp được thực hiện qua workflow JIT. | Có thể tăng tỷ lệ bằng cách chuyển hết admin sang JIT nhưng scope vẫn quá rộng. |
| **Over-scoped grants** | Grant có action/resource vượt nhu cầu được phê duyệt. | Không xét data sensitivity và khả năng tự nâng quyền. |
| **Privilege removal latency** | Từ mốc phải hạ/thu hồi đến lúc effective access thực sự không còn. | Lấy thời điểm ticket đóng/IdP group update làm mốc. |
| **Privileged account owner coverage** | Tỷ lệ account có owner, purpose, approval, review và expiration khi cần. | Shared/service accounts không có owner nhưng vẫn chạy. |
| **Orphaned privileged accounts** | Account đặc quyền không có owner/quan hệ hợp lệ. | Bỏ sót local accounts, vault credential và workload identity. |
| **SoD conflict closure** | Xung đột đã được giải quyết/được quản trị ngoại lệ đúng policy. | Chỉ kiểm tra assigned roles mà bỏ inherited permissions. |
| **Break-glass usage anomaly** | Lần dùng account khẩn cấp bất thường/thiếu căn cứ. | Mọi lần dùng đều phải được đánh giá, không mặc định là gian lận. |
| **Negative access test pass rate** | Tỷ lệ hành động không còn được phép bị target thực sự chặn. | Test thiếu endpoint/bulk/API token hoặc bị thay session giả. |
| **Residual privileged access** | Quyền hoặc credential tồn dư sau Mover/Leaver/expiration. | Chỉ kiểm tra SSO login failure. |
| **Production disruption from reduction** | Sự cố do giảm quyền thiếu hiểu biết dependency. | Không vì giữ availability mà để admin toàn quyền vĩnh viễn. |

**Không có một ngưỡng toàn cầu** cho số admin hoặc thời gian JIT. Đánh giá theo nghiệp vụ, khả năng nền tảng, môi trường, mức nhạy cảm và chính sách tổ chức. Mục tiêu là **giảm rủi ro trong khi duy trì tác vụ hợp lệ**, không đơn thuần làm đẹp chỉ số.

### 20.1. Những dấu hiệu cần cảnh báo sớm

- Số role admin thường trực tăng liên tục sau Mover.
- Một user vừa có quyền cấp admin vừa phê duyệt yêu cầu của chính mình.
- JIT ticket hết hạn nhưng role/session/token vẫn active.
- Account đặc quyền không có owner hoặc không có người đăng nhập hợp lệ.
- Nhóm IdP đã gỡ nhưng app direct grant hoặc local account còn.
- Service identity có quyền admin toàn tenant nhưng owner đã nghỉ việc.
- Break-glass account được dùng ngoài incident window.
- Token hoặc SSH key không được inventory nhưng vẫn được chấp nhận.
- Policy change cho phép tạo credential/admin mà thiếu impact approval.
- Không thể xuất trình bằng chứng **denied privileged action** sau thu hồi.

## 21. Tình huống thực tế: từ GlobalAdmin thường trực sang quyền có thời hạn

**Bối cảnh:** Doanh nghiệp có IAM/IGA, IdP SSO, ứng dụng DevOps, hệ thống cloud, SCIM connector và PAM. Kỹ sư **Lan** có IAM identity `person-2048`. Lan đang được gán `GlobalCloudAdmin` từ giai đoạn triển khai ban đầu để hỗ trợ mọi dự án, nhưng hiện chỉ vận hành `cluster-vn-2`.

### 21.1. Trước khi giảm

Inventory phát hiện:
- Role `GlobalCloudAdmin` trực tiếp ở cloud tenant.
- Group `production-admins` trong IdP.
- Một privileged account local `lan-ops` ở hệ thống legacy.
- PAM đã hỗ trợ JIT nhưng Lan chưa bắt buộc dùng.
- Hai API tokens được phát hành trước, chưa rõ target/scope.
- Công việc thường nhật: xem log, kiểm tra status, thỉnh thoảng restart một service.

**Nếu chỉ gỡ `GlobalCloudAdmin` mà bỏ các đường khác**, Lan có thể vẫn còn quyền admin qua group, local account hoặc token. Quy trình phải xác định **tất cả grant paths** và target đã biết.

### 21.2. Thiết kế desired access

| Nhu cầu | Quyền mong muốn | Hình thức |
| --- | --- | --- |
| Xem trạng thái/log | `service:status:read`, `logs:read`. | Standing, scoped `cluster-vn-2`. |
| Restart service | `service:restart`. | JIT 45 phút, đúng service/ticket. |
| Cấp role IAM | Không cần. | Thu hồi. |
| Đọc mọi secret | Không cần. | Thu hồi. |
| Quản lý app legacy | Chỉ khi có nhiệm vụ. | Chuyển PAM hoặc loại bỏ local admin sau review. |
| API automation | Chỉ scope workload riêng. | Tách user token khỏi workload credential, rotate khi cần. |

### 21.3. Cutover và kiểm chứng

1. IAM/PAM thiết lập role hẹp, cấu hình JIT/step-up và approval.
2. Lan kiểm thử **xem log** và **restart service được phê duyệt**.
3. IAM gỡ `GlobalCloudAdmin`, IdP `production-admins` nếu không còn căn cứ và privileged grants cũ.
4. Đội vận hành xử lý local account, session và API tokens theo inventory.
5. Negative tests: Lan **không thể gán IAM role, không đọc được secret ngoài scope và không restart service khác**.
6. Test hết hạn: sau JIT window, restart không còn được chấp nhận.
7. Ghi evidence; mở ticket remediation nếu quyền còn tồn dư.

### 21.4. Mover và Leaver sau đó

Khi Lan chuyển sang nhóm Data, PAM eligibility production và mọi role/quyền cluster cũ phải được đánh giá lại, không giữ chỉ vì đã được thiết kế JIT trước đó. Khi Lan rời tổ chức, IdP và tất cả privileged/local accounts, credential và active sessions phải bị xử lý theo Leaver, trong khi các service identities có owner team riêng cần được bàn giao.

**Bài học:** Chuyển từ standing admin sang JIT **giảm thời gian đặc quyền khả dụng**, nhưng chỉ hoàn thành khi **scope, đường cấp quyền, session và credential** đều phản ánh desired state.

## 22. Những sai lầm phổ biến khi “giảm quyền”

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ đổi tên role `Admin` thành `Operator`. | Permission thực tế không giảm. | So sánh effective permission trước/sau. |
| Chỉ bật MFA cho account admin. | Credential được bảo vệ hơn nhưng quyền vẫn quá rộng. | Thu hẹp role/scope/time song song AuthN. |
| Chỉ gỡ group IdP mà bỏ direct grants. | Còn quyền ở cloud/DB/app. | Enumerate grant paths và target readback. |
| Để JIT cấp `GlobalAdmin` vô hạn. | Đặc quyền vẫn quá rộng. | JEA, scope và expiration cưỡng chế. |
| Cho quyền tự approve JIT của mình. | Bỏ qua SoD. | Approval độc lập và chính sách eligibility. |
| PAM ghi hình phiên nhưng không hạn chế hành động. | Có audit nhưng vẫn có thể làm mọi việc. | Policy enforcement/JEA và role narrowing. |
| Hạ quyền mà không biết tác vụ vận hành. | Đứt quy trình, rollback thành admin vĩnh viễn. | Usage/dependency review, pilot, positive tests. |
| Coi absence of usage = không cần. | Xóa khả năng khôi phục cần thiết. | Thiết kế break-glass được kiểm soát. |
| Bỏ qua token, SSH key, certificate, PAT. | Đặc quyền vẫn được dùng ngoài UI. | Credential inventory, revocation/rotation. |
| Đóng JML khi IdP disable. | Local account/session/tokens tồn dư. | Deprovision và kiểm chứng từng target. |
| Xóa workload khi owner nghỉ việc. | Dịch vụ quan trọng gián đoạn. | Owner handover và workload lifecycle riêng. |
| Coi SCIM Group = mọi privileged entitlement. | Role ứng dụng/cloud còn. | Provider-specific entitlement inventory. |
| Không kiểm tra SoD qua role hierarchy. | Một senior role cho cả quyền xung đột. | Permission closure và transaction checks. |
| Timeout PAM/PDP thì mở admin direct. | Fail-open. | Break-glass riêng, giới hạn và audit. |
| Không xử lý stale token/session. | Role đã gỡ nhưng quyền vẫn effective. | Session/token policy và negative test. |
| Rollback bằng cấp lại GlobalAdmin không hạn. | Quay về trạng thái overprivileged. | Ngoại lệ hẹp, time-bound, root-cause review. |
| Chỉ đánh giá một ứng dụng/scope. | Đặc quyền lan qua tenant, region, môi trường khác. | Inventory cross-target, namespace và resource policy. |
| Chỉ xem HTTP 200 của provisioning là thành công. | Có thể còn quyền chưa thu hồi. | Readback actual state và kiểm tra hành động bị từ chối. |

## 23. Checklist áp dụng và bài tập tự kiểm tra

### 23.1. Checklist giảm quyền đặc biệt theo vòng đời IAM

- [ ] Có inventory **người, privileged accounts, service/workload identities và local accounts**.
- [ ] Xác định từng permission đặc biệt theo **tác động, khả năng cấp lại quyền và scope**, không chỉ tên role.
- [ ] Mỗi grant có **owner, mục đích, căn cứ, approval, effective time và kỳ review**.
- [ ] Đã tính **role hierarchy, nested group, direct grants, resource policies và đường impersonation**.
- [ ] Phân biệt **eligibility, standing assignment, activation, effective access**.
- [ ] Ưu tiên role/capability hẹp; JEA cho hành động và resource; JIT cho đặc quyền hiếm dùng.
- [ ] JIT có ticket, approval/SoD, MFA/step-up, expiration và verified deactivation.
- [ ] Credential vault/session PAM có inventory và đánh giá đường truy cập ngoài PAM.
- [ ] Privileged admin session/credential có bảo vệ, logging và cơ chế thu hồi phù hợp.
- [ ] Không tự coi MFA/SSO success là authorization hoặc proof of least privilege.
- [ ] Các ứng dụng target áp **RBAC/ABAC** ở resource/API, không chỉ ẩn nút UI.
- [ ] **SCIM User/Group** được đối chiếu với app-specific privileged roles và direct grants.
- [ ] Joiner có quyền nền đúng công việc; quyền cao chỉ khi có căn cứ và active policy.
- [ ] Mover áp **KEEP/REMOVE/GRANT/REVIEW**, gỡ quyền cũ trước/đúng lúc quyền mới có hiệu lực.
- [ ] Leaver xử lý IdP, privileged/local accounts, tokens/keys/sessions và đường ngoài SSO.
- [ ] Service identity có owner/team, trust, credential rotation và lifecycle riêng.
- [ ] Break-glass được chuẩn bị, giới hạn và kiểm toán, không là bypass thường trực.
- [ ] Có positive tests bảo đảm công việc hợp lệ tiếp tục và negative tests chứng minh overprivilege bị chặn.
- [ ] Quy định **revocation SLA**, xử lý eventual consistency và owner cho residual access.
- [ ] Audit liên kết HR/approval, identity, target, grant paths, activation và verified outcome.
- [ ] Reconciliation so sánh **desired permission và actual effective access** trên từng target.

### 23.2. Tình huống A — Hạ role nhưng còn quyền

Lan bị gỡ `GlobalCloudAdmin` nhưng vẫn có quyền `iam:assign-role` qua một resource policy. Hãy giải thích **grant path** là gì, cần kiểm tra những nguồn nào và tại sao nhìn vào danh sách role gán trực tiếp chưa đủ.

### 23.3. Tình huống B — JIT hết hạn mà token còn sống

Engineer được activate `service:restart` trong 30 phút. Role JIT đã tự hết hạn, nhưng access token phát hành trước đó vẫn gọi API restart thành công. Hãy mô tả khác nhau giữa **grant expiration**, **token validity** và **PEP enforcement**, rồi đề xuất giải pháp và tiêu chí verified.

### 23.4. Tình huống C — Mover với SoD xung đột

Nhân viên chuyển từ nhóm tạo giao dịch sang nhóm phê duyệt. Nếu IAM cấp `PaymentApprover` ngay mà chưa thu hồi `PaymentCreator`, có thể xảy ra rủi ro gì? Hãy đề xuất thứ tự thu hồi/cấp, SoD và transaction-level control phù hợp.

### 23.5. Tình huống D — PAM chỉ ghi hình session

Tổ chức bật session recording cho mọi DBA nhưng vẫn cho DBA dùng tài khoản superuser đọc mọi bảng. Điều này đã đạt “giảm quyền đặc biệt” chưa? Hãy phân biệt **accountability, JEA/resource scope và password/session protection**.

### 23.6. Tình huống E — Leaver và tài khoản local

IdP đã disable tài khoản nhân viên nghỉ việc, nhưng `local-db-admin` còn tồn tại và SSH key chưa thu hồi. Hãy lập checklist inventory, revoke/rotate, session checks và bằng chứng cần có trước khi đóng offboarding.

### 23.7. Tình huống F — Service account owner rời công ty

Workload `billing-etl` có quyền DatabaseSuperuser. Engineer owner nghỉ việc. Hãy phân biệt **quyền cá nhân**, **owner handover**, **credential exposure**, **role downgrade của workload** và thời điểm phù hợp để deprovision.

### 23.8. Tình huống G — Break-glass và availability

Khi IdP/PAM ngừng hoạt động, đội vận hành đề xuất bật lại `GlobalAdmin` thường trực cho mọi người trực ca. Hãy chỉ ra lỗ hổng và mô tả một phương án **break-glass tách biệt, giới hạn, có audit và post-incident review**.

### 23.9. Tình huống H — Role hẹp nhưng có quyền nâng quyền

Một role mới `SupportOperator` chỉ có vài permission, trong đó có `policy:edit` và khả năng tạo service principal. Vì sao role này vẫn có thể **rất đặc quyền**? Hãy thiết kế cách đánh giá khả năng tự nâng quyền, phân tách nhiệm vụ và test negative paths.

### 23.10. Tình huống I — Quyền sản xuất ít được dùng

Một quyền recovery production không xuất hiện trong audit log sáu tháng. Có thể xóa ngay không? Hãy trình bày cách phân biệt **standing privilege không cần** với **khả năng khẩn cấp cần duy trì có kiểm soát**, và một thiết kế JIT/break-glass thay thế.

**Điểm cần ghi nhớ:** **Giảm quyền đặc biệt** là giảm **độ rộng hành động/tài nguyên**, **thời gian khả dụng**, **số chủ thể được trao quyền** và **đường leo thang hoặc truy cập dư thừa**. RBAC/ABAC, PAM/JIT/JEA, MFA, SoD và credential/session controls phải phối hợp với nhau; không kỹ thuật nào đơn lẻ bảo đảm hoàn tất. Trong IAM **Joiner–Mover–Leaver**, chỉ có thể coi đặc quyền đã được thu hồi khi **account, entitlement, group/role hierarchy, token, session, credential và target enforcement** đều được đánh giá theo phạm vi bắt buộc, có **readback/reconciliation và dấu vết kiểm toán** chứng minh quyền không còn căn cứ thực sự đã bị chặn.

