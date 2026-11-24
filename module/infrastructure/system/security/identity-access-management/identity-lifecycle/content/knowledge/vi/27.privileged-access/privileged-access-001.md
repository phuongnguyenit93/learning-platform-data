# Privileged access là gì? Hiểu và kiểm soát quyền truy cập đặc quyền trong IAM

**Privileged access (truy cập đặc quyền)** là khả năng một **chủ thể** — con người, dịch vụ hoặc workload — thực hiện những hành động có **tác động đặc biệt lớn** đến hệ thống, dữ liệu, bảo mật hoặc hoạt động của tổ chức. Các hành động này có thể bao gồm quản trị tài khoản và quyền của người khác, thay đổi chính sách truy cập, đọc bí mật, triển khai mã lên production, điều chỉnh hạ tầng, xóa dữ liệu quan trọng hoặc vô hiệu hóa cơ chế giám sát.

Điểm quan trọng: **Đặc quyền không chỉ là tài khoản mang tên `admin` hay `root`.** Một vai trò có khả năng cấp thêm quyền cho chính mình, đọc khóa ký token, sửa pipeline triển khai hoặc thay đổi chính sách phân quyền cũng có thể là **đặc quyền**, dù tên role chỉ là `operator` hoặc `maintainer`. Cần đánh giá **tác động thực tế nếu quyền bị lạm dụng**, chứ không dựa vào nhãn hiển thị.

Bài học thuộc chương **Privileged access** của mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, nghiên cứu **quản lý vòng đời danh tính IAM theo Joiner–Mover–Leaver (JML)**: xác minh, tạo tài khoản, cấp đúng quyền, rà soát và thu hồi khi thay đổi vai trò hoặc kết thúc quan hệ làm việc. Truy cập đặc quyền liên kết với **IdP, SSO, MFA, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán** và đặc biệt là việc **giảm quyền truy cập tồn dư** sau Mover/Leaver.

**Thông điệp cốt lõi:** Quyền đặc quyền phải được **cấp cho đúng chủ thể, đúng lý do, đúng phạm vi, đúng thời điểm**, được theo dõi trong lúc sử dụng và **thu hồi thực sự khi không còn căn cứ**. Xác thực thành công hoặc một yêu cầu cấp quyền đã được phê duyệt **không đủ** để khẳng định người dùng được phép thực hiện mọi thao tác quản trị.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **privileged access** và nhận diện quyền có tác động cao dù tên role không chứa chữ `admin`.
2. Phân biệt **privileged identity, privileged account, privileged entitlement, privileged credential** và **privileged session**.
3. Xác định các hình thức đặc quyền ở **directory/IdP, hệ điều hành, cloud, database, Kubernetes, ứng dụng, CI/CD và secret manager**.
4. Hiểu **least privilege, separation of duties (SoD), just-in-time (JIT), just-enough access/administration (JEA)** và yêu cầu kiểm soát theo thời hạn.
5. Phân biệt trách nhiệm của **PAM, PIM, IAM/IGA, IdP/SSO, MFA, SCIM, RBAC/ABAC**.
6. Mô tả luồng **yêu cầu → phê duyệt → nâng quyền → sử dụng → thu hồi → kiểm toán**.
7. Giải thích vì sao **phiên, token, khóa, secret, nhóm quyền và direct grant** phải được xét khi Mover/Leaver.
8. Áp dụng nguyên tắc kiểm soát đặc quyền cho **service account, workload identity, automation và break-glass**.
9. Đánh giá các tình huống rủi ro: **quyền thường trực, tài khoản dùng chung, credential bị lộ, ownerless service account, privilege escalation và quyền truy cập tồn dư**.

## 2. Thế nào là một quyền “đặc quyền”?

Quyền truy cập thông thường cho phép người dùng làm công việc trong phạm vi đã xác định, ví dụ đọc các ticket được giao hoặc cập nhật thông tin khách hàng thuộc dự án của mình. **Quyền đặc quyền** cho phép thực hiện thao tác mà nếu bị sử dụng sai có thể **thay đổi đáng kể trạng thái bảo mật, tính toàn vẹn, tính sẵn sàng hoặc quyền của các chủ thể khác**.

Một quyền đáng được phân loại là đặc quyền khi nó có một hoặc nhiều tính chất:

- **Thay đổi quyền:** Tạo tài khoản, gán nhóm quản trị, cấp quyền API hoặc chỉnh sửa policy.
- **Mở rộng đặc quyền gián tiếp:** Gán role cho chính mình, thay đổi pipeline sẽ chạy với quyền cao, sửa cấu hình identity federation.
- **Truy cập bí mật:** Đọc/đổi private key, mật khẩu dịch vụ, token ký hoặc khóa giải mã.
- **Thay đổi hệ thống trọng yếu:** Cập nhật cấu hình production, firewall, DNS, cơ sở dữ liệu, image hoặc ứng dụng.
- **Tác động dữ liệu lớn:** Xuất, xóa hoặc khôi phục khối lượng dữ liệu nhạy cảm vượt phạm vi thông thường.
- **Tác động giám sát:** Xóa log, thay đổi cảnh báo, tắt kiểm soát an ninh hoặc sửa bằng chứng kiểm toán.
- **Tác động khả dụng:** Dừng cụm dịch vụ, đổi backup, xóa tài nguyên, thay đổi đường truy cập của nhiều người.

**Ví dụ đối chiếu:**

| Thao tác | Có thể là quyền thường? | Khi nào cần xem là đặc quyền hoặc rủi ro cao? |
|---|---|---|
| Đọc ticket của mình | Có | Khi có quyền xem mọi ticket chứa dữ liệu nhạy cảm |
| Sửa thông tin dự án được giao | Có | Khi có thể thay đổi quyền của mọi thành viên |
| Xem báo cáo tài chính | Tùy nghiệp vụ | Khi có thể export toàn bộ dữ liệu hoặc vượt tenant |
| Tạo user mới | Thường là đặc quyền quản trị | Đặc biệt nếu tự gán role hoặc bỏ qua phê duyệt |
| Quản lý nhóm IdP | Thường là đặc quyền | Nhóm có thể cấp quản trị hệ thống khác |
| Deploy production | Thường là đặc quyền | Có thể đưa mã mới chạy với quyền hệ thống cao |
| Đọc secret production | Đặc quyền nhạy cảm | Bí mật có thể cho phép truy cập hệ thống khác |
| Thay đổi policy IAM | Đặc quyền rất nhạy cảm | Có thể mở đường cấp quyền không giới hạn |
| Sửa cấu hình backup | Đặc quyền | Có thể làm mất khả năng phục hồi sau sự cố |

**Không có danh sách tuyệt đối** áp dụng cho mọi tổ chức. Ví dụ, quyền đọc báo cáo tổng hợp ít nhạy cảm có thể bình thường; quyền đọc cùng loại báo cáo chứa thông tin khách hàng toàn quốc có thể cần quản trị như quyền rủi ro cao. Phân loại dựa trên **phạm vi tài nguyên, độ nhạy, khả năng lan truyền tác động và cách dùng quyền**.

## 3. Phân biệt Authentication, Authorization và Privileged access

Một hệ thống an toàn phải tách ba câu hỏi:

1. **Authentication:** Chủ thể đang yêu cầu là ai và đã chứng minh quyền kiểm soát authenticator thế nào?
2. **Authorization:** Chủ thể đó có được phép thực hiện **action trên resource trong context này** không?
3. **Privileged access control:** Nếu action có tác động cao, đã có **căn cứ nghiệp vụ, mức xác thực, phê duyệt, giới hạn thời gian/phạm vi và cơ chế giám sát bổ sung** theo chính sách chưa?

~~~text
Đăng nhập qua SSO hợp lệ                 -> Authentication PASS
Có role quản trị được cấp từ trước       -> Cần kiểm Authorization
Yêu cầu xóa dữ liệu production           -> Có thể cần JIT + approval + step-up
Thao tác thực sự tại API                 -> PEP kiểm quyền trên resource
Kết thúc nhiệm vụ                        -> Gỡ quyền và chấm dứt phiên liên quan
~~~

### 3.1. MFA không tự tạo đặc quyền

Nhân viên đã xác thực bằng passkey hoặc MFA mạnh **vẫn không trở thành administrator** nếu không có role/entitlement phù hợp. MFA tăng mức tin cậy vào phiên xác thực; việc cấp quyền cần cơ sở riêng.

### 3.2. Có role admin không có nghĩa mọi action đều được phép

Một user có role `db_admin` ở môi trường **staging** không mặc nhiên được truy cập **production**. Một role `tenant_admin` tại tenant A không được tự tạo quyền ở tenant B. Một người có quyền quản lý hạ tầng có thể vẫn **không được phép đọc dữ liệu khách hàng thô**.

**Phân quyền phải xét:** subject, action, resource, tenant/environment, thời gian, trạng thái JML, lý do và điều kiện xác thực/phiên theo chính sách.

## 4. Năm khái niệm thường bị nhầm lẫn

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Privileged identity** | Identity của chủ thể có thể được trao quyền đặc biệt | Nhân viên quản trị hệ thống hoặc workload triển khai |
| **Privileged account** | Account tại hệ thống đích có khả năng quản trị | Account root cục bộ, domain admin, cloud admin |
| **Privileged entitlement** | Grant/permission/role có tác động cao | `iam.role.grant`, `cluster.admin` |
| **Privileged credential** | Phương tiện xác thực cho account/quyền đó | Private key, mật khẩu quản trị, client certificate |
| **Privileged session** | Phiên hoạt động trong đó quyền đặc biệt được sử dụng | Phiên quản trị production qua bastion/PAM |

Một **identity có thể có nhiều account** và chỉ một số account mang đặc quyền. Một account có thể có quyền quản trị nhưng credential tạm thời đã hết hạn; một session còn sống có thể vẫn thực hiện quyền đã được nâng trước đó.

**Vì vậy, “đã xóa role ở IAM” không tự chứng minh credential, session hoặc tài khoản cục bộ đã mất khả năng truy cập.**

### 4.1. Account thường và account đặc quyền tách riêng

Tổ chức có thể dùng:

~~~text
Human identity: P-2048 (nhân viên vận hành)
  ├─ everyday account: user-P-2048
  │    └─ đọc ticket, email và dashboard theo nhiệm vụ
  └─ privileged persona/account: admin-P-2048
       └─ chỉ kích hoạt hoặc sử dụng khi có yêu cầu quản trị được duyệt
~~~

Mô hình hai account **có thể giảm rủi ro** khi quyền quản trị không tồn tại trong mọi phiên thường ngày, nhưng chỉ hiệu quả nếu hai account có **mapping chủ thể, credential/phiên, chính sách đăng nhập và quy trình thu hồi** rõ ràng. Không phải mọi nền tảng cần hoặc hỗ trợ hai account vật lý; có thể dùng **elevation tạm thời trên cùng identity** theo thiết kế được đánh giá.

## 5. Các loại privileged access thường gặp

| Phạm vi | Ví dụ quyền | Tác động nếu bị lạm dụng |
|---|---|---|
| **Directory/IdP** | Quản trị user, group, federation, MFA enrollment | Tạo/chiếm identity, cấp quyền cho người khác |
| **IAM/IGA/PIM/PAM** | Duyệt grant, sửa policy, quản trị vault/session | Tự cấp quyền, vô hiệu hóa kiểm soát |
| **Hệ điều hành/server** | root, local administrator, sudo role | Đọc/sửa file hệ thống, dịch vụ và credential |
| **Cloud control plane** | Quản trị IAM role/policy, resource và billing | Mở rộng quyền, thay/xóa hạ tầng |
| **Kubernetes/container platform** | Cluster admin, RBAC binding, secrets | Thay deployment, đọc secret, điều khiển workload |
| **Database** | DBA, owner schema, quản lý role/backup | Truy xuất hoặc sửa dữ liệu và audit |
| **CI/CD/Source control** | Sửa protected pipeline, release signing, deploy | Đưa mã độc hoặc cấu hình sai lên production |
| **Secret manager/HSM/KMS** | Quản lý key, secret policy, signer | Chiếm quyền ở nhiều hệ thống phụ thuộc |
| **Ứng dụng nghiệp vụ** | Global admin, export toàn tenant, policy admin | Thay đổi quyền và dữ liệu nhạy cảm |
| **Network/Security** | Firewall, VPN/ZTNA, EDR, SIEM settings | Mở đường truy cập hoặc tắt giám sát |
| **Backup/DR** | Xóa/khôi phục backup, thay retention | Phá khả năng phục hồi hoặc sửa dữ liệu khôi phục |
| **Machine/workload** | Service principal quyền cao, automation token | Tác động liên tục, khó truy vết nếu không có owner |

### 5.1. Đặc quyền gián tiếp (indirect privilege)

Một người không có `production.admin` nhưng có quyền sửa workflow CI/CD chạy với service account production vẫn có thể **gây tác động tương đương quản trị production**. Quyền thay đổi **policy, group membership, token signing key hoặc secret access** cũng có thể tạo đường nâng quyền gián tiếp.

Khi kiểm kê quyền, cần hỏi:

> “Chủ thể này có thể trực tiếp **hoặc gián tiếp** tạo ra hành động nào nếu sử dụng tối đa quyền đang có?”

Không đánh giá chỉ bằng một danh sách role name. Cần xét **chuỗi ủy quyền, phụ thuộc hệ thống và khả năng cấp lại quyền**.

## 6. Đặc quyền thường trực và đặc quyền theo yêu cầu

**Standing privilege** là quyền đặc biệt luôn được gán hoặc luôn có thể sử dụng mà không cần phê duyệt/activation tại thời điểm thực hiện. Nó có thể tạo “cửa sổ rủi ro” dài vì credential bị lộ hoặc phiên bị chiếm sẽ cho khả năng tác động ngay.

**Just-in-Time (JIT) privileged access** chỉ cấp/kích hoạt quyền trong **thời gian cần thiết**, có thể cần approval, MFA step-up, ticket hoặc điều kiện rủi ro. **Just-Enough Access/Administration** giới hạn **hành động và tài nguyên** mà người được nâng quyền có thể thực hiện, không nhất thiết cung cấp full admin.

| Khía cạnh | Standing privilege | JIT/Scoped elevation |
|---|---|---|
| Thời gian | Thường gán lâu dài | Có thời điểm bắt đầu/kết thúc |
| Phạm vi | Có thể rất rộng nếu quản trị không tốt | Theo nhiệm vụ/resource/môi trường |
| Approval tại thời điểm sử dụng | Có thể không có | Có thể yêu cầu theo rủi ro |
| Cửa sổ credential bị lạm dụng | Dài nếu credential còn hợp lệ | Có thể ngắn hơn, nhưng không bằng 0 |
| Audit | Biết ai có role; có thể thiếu lý do từng lần dùng | Có thể gắn request/approval/session |
| Thu hồi | Phải gỡ assignment và các đường truy cập | Có thể hết TTL, nhưng vẫn phải kiểm session/token |
| Khả năng vận hành | Dễ thao tác nếu luôn có quyền | Cần portal/workflow và phương án sự cố |

**JIT không tự bảo đảm an toàn** nếu người dùng có thể tự phê duyệt, nâng lên global admin hoặc session tiếp tục dùng được sau khi grant hết hạn. Phải kiểm tra **effective access** ở hệ thống đích.

### 6.1. Just Enough khác Just in Time

- **Just in Time:** *Được sử dụng vào lúc nào và trong bao lâu?*
- **Just Enough:** *Được làm những hành động nào, trên những tài nguyên nào?*

Một yêu cầu “root access 30 phút” là JIT nhưng **chưa chắc là just-enough**. Với nhiệm vụ restart một service, nên đánh giá phương án cấp **chỉ quyền restart service đó**, kèm giám sát và giới hạn phù hợp.

## 7. Least privilege, Need-to-Know và Separation of Duties

Ba nguyên tắc bổ sung lẫn nhau:

### 7.1. Least privilege

Chỉ cấp quyền **tối thiểu** để thực hiện nhiệm vụ được duyệt. Không mặc định cấp global admin cho người chỉ cần xem trạng thái.

Ví dụ kỹ thuật viên hỗ trợ tài khoản:

~~~text
Nhiệm vụ: Reset phương thức xác thực cho user đã xác minh

Không mặc định cần:
  - Xóa mọi user
  - Sửa policy cấp đặc quyền
  - Đọc token signing keys
  - Quản trị mọi tenant

Nên cân nhắc:
  - Quyền thao tác cụ thể trên user thuộc scope hỗ trợ
  - Quy trình kiểm chứng danh tính trước reset
  - Hạn thời gian và audit từng lần hỗ trợ
~~~

### 7.2. Need-to-know/need-to-use

Một người có trách nhiệm vận hành backup không đương nhiên cần xem dữ liệu giải mã trong mọi backup. Một database administrator có thể cần tối ưu chỉ mục mà không cần tải bản sao dữ liệu khách hàng. Nên **tách quyền quản trị nền tảng khỏi quyền đọc dữ liệu nhạy cảm** khi kỹ thuật cho phép.

### 7.3. Separation of Duties (SoD)

Tách những chức năng có thể xung đột để tránh một người **tự thực hiện và tự phê duyệt** một hành động nhạy cảm.

| Tổ hợp quyền | Vì sao rủi ro? | Hướng kiểm soát |
|---|---|---|
| Tạo user + tự duyệt role admin | Tự mở đường cấp quyền | Approval độc lập, role governance |
| Đổi policy + tự triển khai + xóa audit | Có thể che giấu việc mở quyền | SoD, change control, log độc lập |
| Tạo nhà cung cấp + giải ngân | Có nguy cơ gian lận | Phân tách nhiệm vụ nghiệp vụ |
| Quản lý secret + sửa ứng dụng sử dụng secret | Có thể mạo danh workload | Giới hạn vai trò, review, giám sát |
| Xóa backup + quản trị production | Tăng tác động ransomware/sự cố | Privilege separation và bảo vệ immutable backup |

**SoD có thể là static hoặc dynamic.** Với static SoD, một subject không được gán hai role xung đột. Với dynamic SoD, có thể được gán nhưng không được kích hoạt/áp dụng hai quyền xung đột trong cùng giao dịch theo chính sách.

## 8. PAM, PIM và IAM/IGA khác nhau thế nào?

| Thành phần | Mục tiêu chính | Ví dụ trách nhiệm |
|---|---|---|
| **IAM** | Danh tính, authentication và authorization tổng thể | Account, IdP/SSO, MFA, access policy |
| **IGA – Identity Governance and Administration** | Governance, lifecycle, review/approval, SoD | Joiner/Mover/Leaver, access certification |
| **PIM – Privileged Identity Management** | Quản lý **ai đủ điều kiện và khi nào được kích hoạt vai trò đặc quyền** | Eligible roles, JIT activation, approval, expiry |
| **PAM – Privileged Access Management** | Bảo vệ và kiểm soát **việc sử dụng truy cập/credential/phiên đặc quyền** | Vault, credential checkout, session broker/recording |
| **PDP/PEP của authorization** | Đánh giá và thực thi quyền trên request cụ thể | Role, scope, resource policy, step-up |
| **SIEM/Audit** | Giám sát và truy vết hoạt động nhạy cảm | Alert, change evidence, session events |

Các thuật ngữ **PAM/PIM** có thể được nhà cung cấp dùng với phạm vi chồng chéo. Một sản phẩm có thể tích hợp cả vault, JIT roles, approval và session management. Khi thiết kế, nên mô tả **năng lực thực tế và điểm kiểm soát** thay vì dựa vào nhãn sản phẩm.

### 8.1. Kiến trúc tham chiếu

~~~mermaid
flowchart TD
    H["HR / VMS<br/>Joiner–Mover–Leaver"] --> I["IAM / IGA<br/>Identity + desired access"]
    I --> IDP["IdP / SSO + MFA<br/>Xác thực chủ thể"]
    I --> PIM["PIM / Role governance<br/>Eligibility + activation"]
    T["Ticket / Business approval<br/>Mục đích, scope, TTL"] --> PIM
    IDP --> PIM
    PIM --> PAM["PAM / Privileged session<br/>Broker hoặc vault"]
    PAM --> PEP["Target/API PEP<br/>Kiểm RBAC/ABAC"]
    PEP --> R["Production resource<br/>Server, cloud, DB..."]
    I --> S["SCIM / API provisioning<br/>Account/group/role"]
    S --> R
    PIM --> A["Audit / Monitoring<br/>Grant + activation"]
    PAM --> A
    PEP --> A
    A --> V["Readback / Reconciliation<br/>Effective access"]
    V --> I
~~~

**Sơ đồ là mô hình logic.** Nhiều sản phẩm có thể gộp các chức năng hoặc dùng cơ chế khác. **SCIM** đồng bộ account/nhóm ở những target hỗ trợ; nó **không tự thu hồi mọi phiên, SSH key, database role hay token riêng của ứng dụng**.

## 9. Vòng đời một yêu cầu privileged access

Một luồng hợp lệ có thể đi theo các bước:

1. **Request:** Subject xác định nhiệm vụ, hệ thống, action, phạm vi và thời gian cần quyền.
2. **Eligibility:** IAM/PIM xác nhận identity, trạng thái account/engagement, role nền và quyền được phép yêu cầu.
3. **Risk evaluation:** Xét môi trường production, dữ liệu nhạy cảm, SoD, thiết bị, thời điểm, dấu hiệu rủi ro.
4. **Approval:** Người có thẩm quyền phê duyệt theo chính sách; không nhất thiết mọi yêu cầu cần cùng mức phê duyệt.
5. **Step-up:** Có thể yêu cầu MFA mạnh hoặc xác thực mới cho hành động nhạy cảm.
6. **Activation/provisioning:** Bật role hoặc cấp credential/permission **có giới hạn phạm vi và TTL**.
7. **Usage:** Người dùng thực hiện công việc qua PEP/PAM/target; audit ghi hành động.
8. **Expiry/revoke:** Hết hạn hoặc bị thu hồi khi nhiệm vụ kết thúc, policy thay đổi hoặc subject không còn eligible.
9. **Verification:** Kiểm session, token, group, target role và quyền thực tế.
10. **Review:** Đối soát hành động, sự cố và tính cần thiết của đặc quyền cho lần sau.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người vận hành
    participant I as IdP / SSO
    participant P as PIM / Approval
    participant M as PAM / Session
    participant T as Target / API
    participant A as Audit / Reconciliation

    U->>I: Xác thực danh tính
    I-->>U: Phiên xác thực hợp lệ
    U->>P: Yêu cầu quyền có ticket, scope, TTL
    P->>P: Kiểm eligibility, SoD, owner, policy
    P-->>U: Yêu cầu approval/step-up khi cần
    U->>P: Hoàn tất điều kiện được duyệt
    P->>M: Kích hoạt privilege theo phạm vi/TTL
    U->>M: Bắt đầu phiên quản trị được phép
    M->>T: Kết nối/ủy quyền theo cơ chế phù hợp
    T-->>M: Kết quả thao tác
    M-->>A: Session/action evidence
    P->>T: Thu hồi grant khi hết hạn hoặc theo sự kiện
    P->>M: Chấm dứt phiên nếu chính sách yêu cầu
    A->>T: Readback quyền thực tế
    T-->>A: Kết quả kiểm chứng
~~~

**Không nên đồng nhất** một sự kiện “activation success” với quyền được cấp đúng ở target, hoặc “revoke requested” với quyền đã mất hiệu lực. Cần có **đọc lại và kiểm chứng theo mục tiêu bảo mật**.

## 10. Căn cứ cấp quyền: Eligibility khác Activation

Một hệ thống có thể đặt một nhân viên vào trạng thái **eligible**: có quyền *yêu cầu* kích hoạt vai trò, nhưng chưa được sử dụng đặc quyền ngay lập tức.

| Trạng thái | Ý nghĩa | Điều kiện cần |
|---|---|---|
| `NOT_ELIGIBLE` | Chưa có căn cứ yêu cầu role | Phê duyệt nghiệp vụ/JML |
| `ELIGIBLE` | Được phép gửi yêu cầu kích hoạt | Đúng công việc, tenant, role, thời hạn |
| `ACTIVATION_REQUESTED` | Có yêu cầu cụ thể | Ticket, justification, scope |
| `PENDING_APPROVAL` | Đang chờ người có thẩm quyền | SoD, risk, owner |
| `ACTIVE_UNTIL_T` | Quyền được kích hoạt tới một mốc | Phiên/credential phù hợp policy |
| `EXPIRED_OR_REVOKED` | Grant không còn hợp lệ | Readback tại target, xử lý session |
| `EXCEPTION_REVIEW` | Chưa chứng minh quyền đã bị thu hồi | Owner, kiểm soát bù trừ, thời hạn |

Tên trạng thái chỉ là **ví dụ mô hình**, không phải schema chuẩn. Người dùng đang **ELIGIBLE** nhưng chưa **ACTIVE** không nên được API cho phép thực hiện quyền quản trị chỉ vì role xuất hiện trong một hồ sơ quản trị.

### 10.1. Time-bound scope không chỉ là TTL

Một grant nên ghi các thuộc tính như:

~~~text
Subject:       P-2048
Role:          database_maintenance
Environment:   production
Resource:      db-orders-01
Allowed action: index.manage, performance.inspect
Reason:        Approved change CHG-9812
Valid from:    2026-12-05T20:00:00+07:00
Valid until:   2026-12-05T21:00:00+07:00
Approval:      Data Platform owner
Audit ref:     PRV-2026-892
~~~

Nếu ứng dụng chỉ lưu `role=admin` và bỏ scope/TTL, chính sách thực tế có thể mở quyền rộng hơn yêu cầu đã duyệt. Thời gian hết hạn của approval phải được liên kết với **grant và phiên/credential** qua cơ chế thích hợp.

## 11. Xác thực mạnh cho phiên đặc quyền

Privileged access là mục tiêu hấp dẫn của **phishing, credential stuffing, key theft và session hijacking**. Một chiến lược phổ biến gồm:

- **MFA mạnh, ưu tiên chống phishing** cho thao tác quản trị quan trọng khi điều kiện cho phép.
- **Step-up authentication:** Yêu cầu xác thực mới hoặc mạnh hơn khi kích hoạt quyền nhạy cảm.
- **Conditional access:** Xét thiết bị được quản lý, trạng thái bảo mật, rủi ro đăng nhập và môi trường.
- **Separate administrative context:** Giảm việc dùng credential quản trị trong hoạt động email/web thường nhật.
- **Session timeout và revalidation:** Không cho một phiên đặc quyền sống lâu vô hạn.
- **Token validation:** Kiểm đúng issuer, audience, expiry, privilege scope và trạng thái theo thiết kế.
- **Recovery controls:** Helpdesk và account recovery không được là đường vòng dễ dàng để kẻ tấn công thiết lập lại authenticator admin.

### 11.1. Phishing-resistant MFA không thay thế quyền tối thiểu

Khóa bảo mật hoặc passkey có thể giảm nguy cơ bị lừa cung cấp credential. Nhưng nếu người quản trị có quyền xóa toàn bộ backup chỉ để vận hành một ứng dụng nhỏ, **đặc quyền vẫn quá rộng** dù login được bảo vệ tốt.

### 11.2. Thiết bị quản trị và trình duyệt

Một số tổ chức dùng **Privileged Access Workstation (PAW)** hoặc môi trường quản trị được quản lý chặt chẽ, nhằm tách hoạt động có đặc quyền khỏi duyệt web/email thường. Đây là kiểm soát bổ sung phụ thuộc mức rủi ro và khả năng vận hành, không phải một nhãn bảo đảm rằng mọi session trên máy đó đều an toàn.

## 12. Quản lý privileged credentials và bí mật

**Credential đặc quyền** có thể là mật khẩu root/administrator, SSH private key, cloud access key, certificate, service principal secret, database password hoặc token.

Các nguyên tắc:

1. **Không chia sẻ credential con người.** Từng cá nhân nên có danh tính có thể truy vết.
2. **Secret lưu ở nơi được bảo vệ:** Vault/secret manager hoặc phương án tương đương, không commit vào repository hay ticket.
3. **Scope giới hạn:** Credential chỉ truy cập đúng target/môi trường/tác vụ.
4. **Rotation theo chính sách và sự kiện rủi ro:** Secret bị lộ, người biết secret rời tổ chức, workload thay đổi.
5. **Hạn chế credential tĩnh:** Ưu tiên cơ chế định danh và credential ngắn hạn/managed identity khi hệ thống hỗ trợ.
6. **Kiểm kê owner và phụ thuộc:** Không để secret không ai chịu trách nhiệm.
7. **Audit việc sử dụng:** Biết ứng dụng/actor nào lấy credential, trong giao dịch nào.
8. **Thu hồi thực tế:** Gỡ secret khỏi vault mà credential **vẫn còn hiệu lực tại target** thì chưa đủ.

### 12.1. “Vault password” và “thay mật khẩu ở target” là hai bước khác

Một vault có thể kiểm soát **ai được xem/checkout mật khẩu**, nhưng nếu mật khẩu trước đó đã bị sao chép hoặc lưu ngoài vault, việc gỡ quyền checkout **không làm bản sao cũ vô hiệu**. Tổ chức có thể cần **rotate credential ở hệ thống đích** và xác minh account không còn đường truy cập.

### 12.2. TLS certificate, signing key và admin credential

Không nhầm:

- **TLS certificate/private key:** Bảo vệ kết nối hoặc định danh endpoint.
- **Token signing private key:** Có thể ảnh hưởng nhiều ứng dụng xác thực/federation.
- **Client credential:** Xác thực service với Authorization Server hoặc API.
- **Human admin authenticator:** Chứng minh người vận hành đang kiểm soát phiên.
- **Privileged role/grant:** Quyết định **được làm gì**, khác với credential dùng để chứng minh **là ai**.

Một signing key bị lộ có thể có tác động lớn hơn một tài khoản quản trị đơn lẻ tùy kiến trúc. Phải phân loại dựa trên **hệ thống phụ thuộc và blast radius**.

## 13. Privileged session management

Ngoài việc cấp quyền, tổ chức có thể cần bảo vệ **phiên sử dụng** quyền đó. Các năng lực của **Privileged Session Management (PSM)**, tùy nền tảng, gồm:

| Kiểm soát | Mục đích | Lưu ý |
|---|---|---|
| **Session broker/bastion** | Đưa truy cập qua điểm được kiểm soát | Không đồng nghĩa chặn mọi đường trực tiếp nếu firewall còn mở |
| **Credential injection/proxy** | Giảm nhu cầu lộ password/secret cho operator | Phải bảo vệ broker và phân quyền tới target |
| **Session authorization** | Chỉ kết nối đúng target và thời hạn | Không dùng một approval cho mọi máy |
| **Activity logging** | Ghi ai thao tác, thời điểm, tài nguyên | Không ghi bí mật/PII quá mức cần thiết |
| **Command/action controls** | Chặn thao tác rủi ro khi khả năng nền tảng hỗ trợ | Không mặc định chặn được mọi giao thức hoặc API |
| **Session recording** | Phục vụ điều tra và kiểm toán | Có yêu cầu quyền riêng tư, retention, masking |
| **Termination/revocation** | Chấm dứt phiên theo timeout/JML/risk | Cần xác minh target thực sự dừng quyền |
| **Concurrent session limits** | Giảm lạm dụng hoặc truy cập ngoài dự kiến | Không thay thế quyền tối thiểu |

**Ghi hình phiên không phải kiểm soát phòng ngừa đầy đủ.** Nếu một account có thể xóa production trong một thao tác, bản ghi chỉ giúp điều tra sau khi sự cố xảy ra. Cần kết hợp **điều kiện cấp quyền, PEP và hạn chế hành động**.

### 13.1. Quyền riêng tư và bí mật trong session recording

Phiên quản trị có thể hiển thị **password, API token, dữ liệu khách hàng hoặc thông tin y tế**. Hệ thống ghi nhận cần **giới hạn truy cập, mã hóa, masking theo khả năng, thời hạn lưu và quy trình mở xem có phê duyệt**. Không giả định ghi càng nhiều dữ liệu càng an toàn.

## 14. RBAC, ABAC và PBAC cho privileged access

**RBAC** xác định nhóm quyền theo vai trò, ví dụ `backup_operator`. **ABAC** dùng thuộc tính subject/resource/context, ví dụ môi trường production, chủ sở hữu dịch vụ hoặc trạng thái MFA. **PBAC** tổ chức những điều kiện đó thành chính sách được đánh giá và thực thi.

Ví dụ quyết định:

~~~text
PERMIT maintenance.restart nếu và chỉ nếu:
  subject.kind == HUMAN
  AND subject.accountStatus == ACTIVE
  AND subject.engagementStatus == ACTIVE
  AND role(subject, service_maintainer)
  AND subject được phê duyệt cho resource.serviceId
  AND request.action == "service.restart"
  AND activation.status == ACTIVE
  AND activation.expiresAt > currentTime
  AND activation.scope bao gồm đúng environment/resource
  AND authenticationAssurance đáp ứng policy
  AND không vi phạm SoD/risk policy

Nếu thiếu thuộc tính bắt buộc:
  -> DENY hoặc xử lý an toàn theo chính sách
~~~

### 14.1. Role admin của một tenant không phải global admin

Ví dụ `tenant_admin@tenant-A` có thể sửa user nội bộ A, nhưng không được tự sửa user ở tenant B. API phải kiểm **tenant của subject, scope grant và tenant của resource** bằng dữ liệu backend đáng tin.

### 14.2. Đặc quyền tại API phải được kiểm từng hành động

Dù client đã có màn hình “Admin”, việc ẩn nút không tạo authorization. Mỗi endpoint sửa policy, cấp role, reset MFA, export dữ liệu hoặc xóa tài nguyên phải có **PEP/kiểm quyền** ở backend.

### 14.3. Mã giả minh họa quyết định nâng quyền

~~~python
from dataclasses import dataclass
from datetime import datetime, timezone

@dataclass(frozen=True)
class PrivilegedGrant:
    subject_id: str
    resource_id: str
    action: str
    expires_at: datetime
    approval_valid: bool
    activation_active: bool

def can_execute_privileged_action(subject, grant, resource, action, now):
    """
    Pseudocode: dữ liệu subject/grant/resource phải đến từ
    hệ thống đáng tin; không lấy trực tiếp từ client body.
    """
    if subject is None or grant is None or resource is None:
        return False
    if not subject["account_active"] or not subject["engagement_active"]:
        return False
    if not subject["assurance_satisfied"]:
        return False

    if not grant.approval_valid or not grant.activation_active:
        return False
    if now >= grant.expires_at:
        return False
    if grant.subject_id != subject["canonical_id"]:
        return False
    if grant.resource_id != resource["id"]:
        return False
    if grant.action != action:
        return False
    if subject["tenant_id"] != resource["tenant_id"]:
        return False

    # Policy thực tế còn cần SoD, risk, credential/session,
    # trạng thái grant hiện hành và authorization của target.
    return True
~~~

**Đây không phải mã PAM production.** Nó mô tả các loại điều kiện cần kiểm; không triển khai xác thực token/cryptography, policy kết hợp, đồng thời hóa trạng thái hay thu hồi session. Trong hệ thống thật, cần **PDP/PEP, thư viện bảo mật và kiểm thử tích hợp** phù hợp.

## 15. Privileged access trong Joiner lifecycle

**Joiner** là quá trình tiếp nhận nhân viên, nhà thầu hoặc account kỹ thuật mới. Tổ chức cần xác định **người đó có thật sự cần đặc quyền từ ngày đầu không**, thay vì mặc định nhân viên IT được cấp admin rộng.

~~~text
HR/VMS -> identity proofing + engagement
IAM/IGA -> canonical identity + account mapping
IdP/SSO -> authentication + MFA enrollment
Role governance -> nhiệm vụ + privileged eligibility
PIM/PAM -> quyền nâng khi cần, giới hạn scope/TTL
Target -> role/permission thực tế
Audit -> readback và trạng thái quyền
~~~

### 15.1. Ví dụ Joiner: kỹ sư SRE mới

Kỹ sư Lan gia nhập nhóm vận hành nền tảng. Trong tuần đầu, Lan cần xem metric/log ở môi trường staging, nhưng **chưa có căn cứ cho full production admin**.

Một thiết kế:

1. HR xác nhận Lan, mốc bắt đầu và manager.
2. IAM tạo identity và account đúng người; đăng ký authenticator an toàn.
3. Cấp role quan sát/log đọc theo nhiệm vụ.
4. Đưa Lan vào nhóm **eligible** cho quyền thao tác production hạn chế nếu chính sách/onboarding yêu cầu.
5. Khi có ticket bảo trì, Lan yêu cầu JIT role có scope target và TTL.
6. Manager/application owner hoặc người được ủy quyền phê duyệt.
7. Sau activation, target áp role; PAM/PEP ghi phiên và action.
8. Hết thời hạn, grant được thu hồi; readback kiểm quyền quản trị đã mất.

**Không copy nguyên quyền của kỹ sư cũ** vì người trước có thể đang giữ exception, credential khẩn cấp hoặc quyền tích lũy sau nhiều năm.

### 15.2. Điều kiện kích hoạt trước ngày làm việc

Account có thể được chuẩn bị trước ngày bắt đầu, nhưng **truy cập production** phải tôn trọng `engagement.effectiveAt` và policy. Đăng ký MFA hoặc hoàn tất onboarding kỹ thuật không tự cho phép vượt mốc hiệu lực.

## 16. Privileged access trong Mover lifecycle

**Mover** xảy ra khi nhân viên đổi nhóm, nhiệm vụ, dự án, địa điểm, vai trò hoặc loại hợp đồng. Đây là nguồn thường gặp của **privilege creep**: quyền mới được cấp nhưng quyền cũ không bị gỡ.

Ví dụ nhân viên An chuyển từ **Platform Operations** sang **Analytics**:

| Trạng thái | Quyền có thể có | Hành động |
|---|---|---|
| Trước Mover | `cluster.admin@staging`, `deploy.production` theo JIT | Phù hợp vai trò cũ nếu đã duyệt |
| Sau Mover mong muốn | `data.read@project-B`, `analytics.job.run` | Cấp theo nhiệm vụ mới |
| Quyền cần thu hồi | Eligibility PIM cũ, role CI/CD, cluster role, SSH key | Gỡ quyền/credential không còn căn cứ |
| Ngoại lệ có căn cứ | On-call chuyển giao trong thời gian ngắn | Cần owner, time-bound, review và kiểm SoD |

### 16.1. Thay role không đồng nghĩa kết thúc phiên đặc quyền

Nếu An đang có một phiên shell/database đã nâng quyền hoặc token có claim `admin` từ trước Mover, việc gỡ role ở IdP **chưa chắc chấm dứt ngay** truy cập.

Cần xử lý:

- Quyền **eligible** và **active** trong PIM.
- Role/group/ACL đã provision ở target.
- Phiên đặc quyền qua PAM/bastion và phiên trực tiếp ngoài PAM.
- Token, refresh token, SSH keys, API keys, cloud sessions.
- Cache permission và nhóm ở API/IdP/directory.
- Direct grants và quyền kế thừa từ role khác.
- Trách nhiệm với service account mà An từng quản lý.

**Mục tiêu:** Tính lại **desired privileged access**, so với **effective privileged access**, và thu hồi đúng những quyền không còn căn cứ.

### 16.2. Nhiều engagement hợp lệ

Nếu An chuyển nhóm chính nhưng vẫn được phê duyệt tham gia nhiệm vụ on-call 7 ngày, không tự giữ mọi admin privilege vô thời hạn. Nên biểu diễn **grant riêng theo nhiệm vụ, owner, mục đích và mốc hết hạn**, tránh nhầm giữa chuyển giao hợp lệ và quyền tồn dư.

## 17. Privileged access trong Leaver lifecycle

**Leaver** là biến cố chấm dứt quan hệ làm việc/hợp đồng hoặc quyền của một engagement. Với quyền đặc quyền, quy trình không thể chỉ đổi mật khẩu account thường hoặc disable IdP và chờ token hết hạn.

### 17.1. Các lớp thu hồi

~~~mermaid
flowchart TD
    H["HR/VMS<br/>Leaver effective event"] --> I["IAM/IGA<br/>Identify all accounts & grants"]
    I --> P["PIM<br/>Revoke eligibility/active roles"]
    I --> D["IdP / Directory<br/>Disable account và nhóm"]
    I --> M["PAM<br/>Stop session/check-out access"]
    I --> T["Target systems<br/>Role, ACL, local admin"]
    I --> K["Secrets / credentials<br/>Rotate/revoke where needed"]
    I --> A["AS / apps<br/>Session, token, PAT"]
    P --> V["Readback effective access"]
    D --> V
    M --> V
    T --> V
    K --> V
    A --> V
    V --> O{"All required controls<br/>verified?"}
    O -->|Có| C["Close with audit evidence"]
    O -->|Không| X["Pending + compensating controls<br/>owner/expiry/escalation"]
~~~

### 17.2. Những câu hỏi phải trả lời

1. Có bao nhiêu account gắn với **canonical identity**? Có account riêng admin hay account local không?
2. Subject còn role **eligible** để có thể tái kích hoạt đặc quyền không?
3. Có **active grant** hoặc quyền quản trị tồn tại trực tiếp ở target không?
4. **Phiên quản trị** đã được chấm dứt chưa? Còn khả năng kết nối ngoài PAM không?
5. Token/credential nào được cấp trước Leaver còn hiệu lực?
6. Có **SSH key, certificate, API key, personal access token, database password** hoặc secret đã từng được người đó biết?
7. Có **service account** người đó quản lý hoặc từng có quyền đọc credential?
8. Các ứng dụng/đối tác/cloud tenant có local permission chưa đồng bộ qua SCIM không?
9. Đã có **readback** quyền hiệu dụng và ngoại lệ có owner chưa?

**Disable IdP là một bước, không phải bằng chứng hoàn chỉnh về thu hồi.** Nếu target nhận token JWT offline hoặc có local admin không liên kết IdP, đường truy cập có thể tồn tại.

### 17.3. Credential từng bị biết phải đánh giá rủi ro

Một quản trị viên nghỉ việc có thể từng checkout root password hoặc có bản sao private key. Chỉ xóa quyền xem secret trong vault không làm bản sao cũ mất hiệu lực. Tùy mức rủi ro và policy, cần **rotate credential ở target, thu hồi khóa/chứng thư, thay owner và xác minh không còn đường truy cập**.

Không rotate bừa tất cả secret gây gián đoạn sản xuất; cần **kiểm kê phụ thuộc và kế hoạch thay đổi an toàn**, nhưng phải ưu tiên credential có thể gây tác động lớn hoặc đã có dấu hiệu lộ.

### 17.4. Leaver của engagement không nhất thiết xóa identity

Một contractor có hai hợp đồng A và B, trong đó A kết thúc trước. Nếu quyền `database.admin@A` hết căn cứ nhưng `report.read@B` còn hợp lệ, phải gỡ **đặc quyền A**, giữ quyền B đúng phạm vi nếu policy cho phép và đảm bảo không thể dùng account active của B để gọi API/DB của A.

## 18. Tài khoản dịch vụ và workload đặc quyền

Không phải mọi privileged access đều có một người đang đăng nhập. **Workload identity/service account** có thể chạy job, quản lý hạ tầng, deploy ứng dụng, ký artifact hoặc gọi API qua OAuth Client Credentials.

| Đặc điểm | Human privileged access | Workload privileged access |
|---|---|---|
| Subject | Người dùng/contractor được xác minh | Workload/service principal có ID riêng |
| Authenticator | MFA/passkey/credential phù hợp | Managed identity, key, certificate, client auth |
| Phê duyệt | Request/manager/role owner | Owner kỹ thuật/change workflow |
| Mục đích | Thao tác vận hành cụ thể | Tác vụ hệ thống được xác định |
| Giới hạn | Target, action, TTL, session | Scope/audience, môi trường, deployment, TTL |
| Kiểm toán | Ai, phiên nào, ticket nào | Workload nào, deployment nào, owner nào |
| Lifecycle | Joiner–Mover–Leaver | Provision–rotate–retire và chuyển owner khi nhân viên thay đổi |

### 18.1. Không dùng mật khẩu nhân viên cho job

Một job có `client_id=deploy-prod` không nên dùng mật khẩu của nhân viên DevOps để đăng nhập như một người. Cần cấp **workload identity độc lập**, quyền tối thiểu, owner và credential management có kiểm soát.

### 18.2. Quyền service principal có thể rất lớn

Một service principal có quyền sửa role IAM toàn tenant có thể mở đường tấn công tương đương human admin. Khi inventory, không bỏ qua **non-human identities** chỉ vì không có màn hình đăng nhập người dùng.

### 18.3. Khi owner nghỉ việc

Workload có thể vẫn cần hoạt động. Trước khi đổi owner/credential:

1. Xác minh workload còn phục vụ hệ thống nào và có change owner có thẩm quyền không.
2. Rà soát quyền hiện có, bí mật từng được owner cũ biết và các dependency.
3. Chuyển owner, hạn chế quyền không còn căn cứ và rotate/revoke theo rủi ro.
4. Kiểm thử tác vụ production sau thay đổi, ghi audit.
5. Nếu workload đã nghỉ sử dụng, tiến hành deprovision và kiểm target.

**Không đồng nhất “người tạo service account đã Leaver” với “service account phải xóa ngay”**; cũng không để account máy **mồ côi vĩnh viễn**.

## 19. Break-glass: đặc quyền khẩn cấp

**Break-glass access** là đường truy cập được thiết kế cho **tình huống khẩn cấp** khi các cơ chế thông thường không sử dụng được hoặc không đáp ứng thời gian phục hồi, ví dụ IdP/PAM gặp sự cố nghiêm trọng.

Break-glass có thể là một account hoặc quy trình được bảo vệ đặc biệt. Nó cần:

- **Chỉ định rõ tình huống được sử dụng**, không phải cách bỏ qua quy trình vì tiện.
- **Credential/authenticator được bảo vệ và kiểm tra định kỳ**, có khả năng truy cập khi hệ thống thông thường gặp sự cố.
- **Giới hạn số subject, target, hành động** theo khả năng thực tế.
- **Logging/cảnh báo độc lập** và cơ chế ghi nhận khi đường log chính lỗi.
- **Phê duyệt hoặc hậu kiểm** theo chính sách khẩn cấp.
- **Thu hồi/rotate và review sau sử dụng**.
- **Diễn tập kiểm soát** để tránh chỉ phát hiện credential break-glass đã hết hạn lúc có sự cố thật.

### 19.1. Break-glass khác standing admin không kiểm soát

Một account khẩn cấp có thể phải tồn tại sẵn vì yêu cầu khả dụng, nhưng nó **không được sử dụng như tài khoản cá nhân thường ngày**. Nếu người dùng dùng break-glass để khỏi chờ approval, tổ chức đang phá vỡ mục tiêu quản trị đặc quyền.

### 19.2. Không tạo “master bypass” tùy ý

Một header hoặc biến cấu hình như `X-Emergency: true` do client tự gửi **không chứng minh tình trạng khẩn cấp**. Chức năng đặc biệt phải có cơ chế xác thực, phạm vi, logging và workflow đã thiết kế — không biến lỗi hạ tầng thành `PERMIT_ALL`.

## 20. Những đường nâng quyền gián tiếp cần kiểm kê

Một hệ thống có thể bị mở rộng quyền dù không có người đăng nhập trực tiếp bằng `root`. Ví dụ:

| Quyền ban đầu | Đường tác động có thể có | Câu hỏi quản trị |
|---|---|---|
| Sửa membership group IdP | Thêm bản thân vào role admin | Có kiểm SoD, role owner và audit? |
| Sửa CI/CD workflow | Thay logic chạy bằng credential production | Pipeline được bảo vệ và review độc lập? |
| Đọc signing key/token secret | Giả mạo hoặc gây tác động tới xác thực | Ai được truy cập và rotation ra sao? |
| Quản lý secret vault | Truy cập credential dịch vụ khác | Scope secret và owner có rõ không? |
| Sửa cloud IAM policy | Mở quyền cho chính workload/user | Phê duyệt, permission boundary và audit? |
| Quản lý K8s RBAC/secrets | Điều khiển workload và lấy credential | Cluster/namespace policy có đủ chặt? |
| Đổi backup retention | Giảm khả năng phục hồi | SoD với production admin và monitoring? |
| Quản lý SSO app registration | Thay redirect/trust/credential client | Change control và giới hạn scope? |

**Bài học:** “Không có quyền admin trực tiếp” **không chứng minh** subject không thể gây tác động cấp admin. Đánh giá cần tính **blast radius và quyền gián tiếp** trong kiến trúc.

## 21. Mô hình dữ liệu một yêu cầu đặc quyền

Một request cần đủ thông tin để quyết định, triển khai và kiểm toán. Ví dụ minh họa:

~~~json
{
  "requestId": "PRV-2026-0892",
  "subject": {
    "kind": "HUMAN",
    "canonicalId": "P-2048",
    "tenantId": "company-vn",
    "accountStatus": "ACTIVE",
    "engagementStatus": "ACTIVE"
  },
  "requestedAccess": {
    "action": "service.restart",
    "resourceId": "payment-worker-prod-1",
    "environment": "production",
    "role": "service_maintainer",
    "validForMinutes": 30
  },
  "justification": {
    "changeId": "CHG-9812",
    "reason": "Bảo trì đã được duyệt"
  },
  "controls": {
    "requiresStepUp": true,
    "requiresApproval": true,
    "requiresManagedSession": true
  },
  "approval": {
    "status": "PENDING",
    "approverRole": "production-service-owner"
  }
}
~~~

**Đây là ví dụ schema học tập, không phải API tiêu chuẩn.** Dữ liệu `accountStatus` và `engagementStatus` phải đến từ **nguồn đáng tin**; client không thể tự điền `ACTIVE` để được cấp quyền. Tương tự, `approval.status=PENDING` không được hiểu thành đã có quyền.

### 21.1. Metadata tối thiểu cho grant

Khi grant được phê duyệt, nên có:

- Canonical subject ID và account/target mapping.
- Resource/environment/tenant được phép.
- Action/role cụ thể và thời hạn.
- Căn cứ phê duyệt, người phê duyệt, risk/SoD outcome.
- Mức xác thực và điều kiện device/session.
- Cơ chế cấp quyền tại target, ID grant/session.
- Thời điểm expire/revoke và kết quả **readback**.
- Correlation ID nối request, activation, session, revocation và audit.

Không cần lưu **mật khẩu, OTP, private key hoặc token nguyên văn** để chứng minh các mốc này.

## 22. Rủi ro và mối đe dọa của privileged access

| Mối đe dọa | Biểu hiện | Giảm thiểu |
|---|---|---|
| **Credential theft/phishing** | Mật khẩu admin hoặc token bị lộ | MFA chống phishing, quản lý credential, bảo vệ phiên |
| **Standing privilege abuse** | Quyền admin tồn tại không cần thiết | JIT, TTL, certification và giảm role |
| **Privilege escalation** | Subject cấp thêm quyền cho chính mình | SoD, giới hạn admin policy, audit |
| **Shared privileged account** | Không phân biệt người thực hiện | Identity riêng, session binding, PAM |
| **Unmanaged SSH/API key** | Key tiếp tục dùng được sau Leaver | Inventory, rotation/revoke, TTL |
| **Indirect access** | Sửa pipeline hoặc secret để tác động production | Đánh giá privilege chain, change review |
| **Session hijacking** | Dùng phiên/token sau khi user đăng xuất | Session protection, timeout, token lifecycle |
| **Ownerless service account** | Workload có quyền cao không ai review | Owner, purpose, rotation và lifecycle |
| **Cross-tenant privilege** | Admin A thao tác trên tenant B | Tenant-bound grants và API authorization |
| **SoD conflict** | Cùng người tạo, duyệt và xóa audit | Phê duyệt độc lập, role separation |
| **Privilege creep after Mover** | Nhóm cũ còn quyền admin | Recompute desired vs effective, readback |
| **Incomplete Leaver** | IdP disabled nhưng local root/secret còn sống | Multi-target deprovision, session/token checks |
| **PAM bypass** | Operator kết nối thẳng target ngoài broker | Network policy và target enforcement |
| **Break-glass misuse** | Dùng quyền khẩn cấp cho công việc thường ngày | Giới hạn sử dụng, alert và hậu kiểm |
| **Audit tampering** | Người có quyền xóa dấu vết chính mình | Bảo vệ log độc lập, SoD và retention |

### 22.1. Ưu tiên kiểm soát theo tác động

Một danh sách quyền rất dài không nhất thiết đồng nghĩa với rủi ro cao nhất. Nên xem:

- **Privilege impact:** Có thể thay đổi hệ thống trọng yếu hoặc quyền người khác?
- **Blast radius:** Một credential có ảnh hưởng bao nhiêu tenant/ứng dụng?
- **Reachability:** Có thể dùng đặc quyền từ môi trường/phương thức nào?
- **Persistence:** Grant/session/key có tồn tại lâu không?
- **Detectability:** Có ghi nhận actor và phát hiện hành vi bất thường?
- **Recoverability:** Nếu quyền bị lạm dụng, có thể khôi phục và điều tra?
- **Business necessity:** Quyền có thật sự cần thiết cho nhiệm vụ đang giao không?

Điều này hỗ trợ ưu tiên **giảm quyền cao tác động**, không chỉ giảm tổng số tài khoản có nhãn admin.

## 23. Định nghĩa “thu hồi đặc quyền thành công”

Một thao tác `removeRole` trả **HTTP 200** chỉ chứng minh API đích đã nhận/xử lý request theo contract của nó, không bảo đảm mọi đường truy cập bị chặn.

### 23.1. Đường truy cập thực tế có thể gồm

~~~text
Human / Workload identity
  ├─ IdP account + eligible role
  ├─ Active JIT grant
  ├─ Cloud / directory / DB role
  ├─ Local administrator account
  ├─ Session ở PAM, bastion hoặc target
  ├─ SSH key, certificate, password, API key
  ├─ Refresh/access token, PAT, cloud session
  ├─ Nested group, direct ACL, policy exception
  └─ Ability to modify CI/CD, role policy hoặc secret
~~~

### 23.2. Những loại bằng chứng cần phân biệt

| Bằng chứng | Thể hiện | Không tự thể hiện |
|---|---|---|
| **IAM desired state** | Quyền nên còn hay phải mất | Target đã áp chưa |
| **PIM role removal** | Eligibility/activation đã thay | Phiên hoặc local role chắc chắn đã kết thúc |
| **IdP disable** | Login mới ở IdP có thể bị chặn | Token cũ/API key/local login đã hết |
| **PAM session termination** | Phiên được quản lý qua PAM đã dừng | Đường SSH trực tiếp không qua PAM |
| **Secret rotation** | Credential cũ bị đổi ở target khi thành công | Các credential khác không còn |
| **SCIM/API response** | Thao tác provisioning/deprovision nhận phản hồi | Quyền hiệu dụng ở mọi resource đúng |
| **Target readback** | Role/ACL/trạng thái thực tế tại đích | Token/phiên ngoài đường quan sát đã xử lý |
| **Authorized negative test** | Request không còn được phép theo phạm vi test | Không có mọi đường bypass khác |

**Kết luận:** Với quyền nhạy cảm, cần **định nghĩa tiêu chí hoàn tất và bằng chứng đầu-cuối**, không chỉ đếm số lệnh revoke được gửi.

## 24. Kiểm toán và giám sát đặc quyền

Một hệ thống kiểm toán cần giải thích **ai được cấp quyền, vì sao, sử dụng lúc nào, trên resource nào và quyền được thu hồi khi nào**.

### 24.1. Sự kiện đáng ghi

| Sự kiện | Dữ liệu cần thiết | Tránh |
|---|---|---|
| Privileged request | Subject, role/action, scope, reason, TTL | Password, private key |
| Approval/denial | Approver, SoD, policy version, decision | Thông tin cá nhân không liên quan |
| Activation | Grant ID, thời gian, scope, mức xác thực | Token nguyên văn |
| Credential checkout | Actor, target, session/reference | Secret gốc |
| Session start/end | Actor, resource, thời gian, kết quả | Nội dung nhạy cảm không cần thiết |
| Privileged action | Action, resource, kết quả, correlation ID | Sao chép toàn bộ dữ liệu nghiệp vụ |
| Expiry/revocation | Mốc, nguyên nhân, kết quả tại target | Tuyên bố hoàn tất khi chưa readback |
| JML change | Identity, engagement, mốc hiệu lực, owner | Hồ sơ HR đầy đủ |
| Policy/group change | Ai đổi, trước/sau, nguồn phê duyệt | Credential và thông tin bí mật |
| Incident/break-glass | Lý do khẩn cấp, người sử dụng, hậu kiểm | Bỏ log “vì đang khẩn cấp” |

### 24.2. Ví dụ audit record

~~~json
{
  "eventType": "PRIVILEGE_ACTIVATION",
  "time": "2026-12-05T20:00:00+07:00",
  "actorId": "P-2048",
  "subjectId": "P-2048",
  "target": "payment-worker-prod-1",
  "actionScope": ["service.restart"],
  "environment": "production",
  "grantId": "GRANT-883",
  "requestId": "PRV-2026-0892",
  "approvalRef": "CHG-9812",
  "policyVersion": "privileged-service-v5",
  "expiresAt": "2026-12-05T20:30:00+07:00",
  "result": "ACTIVATED",
  "correlationId": "CORR-107"
}
~~~

Ví dụ không chứa credential thật và **không chứng minh grant đã được thu hồi**; khi expire/revoke phải có **sự kiện và readback riêng**. Với delegation, audit còn cần phân biệt **actor thực hiện** và **subject được đại diện**.

### 24.3. Các chỉ số giám sát

- **Standing high-risk privileges:** Số grant đặc quyền tồn tại thường trực và không có nhu cầu hiện hành.
- **JIT adoption / time-to-expire:** Tỷ lệ thao tác quản trị qua grant có TTL và thời gian quyền còn mở.
- **Approval traceability:** Tỷ lệ grant có request, owner và approval đúng chính sách.
- **Privileged MFA coverage:** Mức áp dụng xác thực mạnh phù hợp trên đường admin thực tế.
- **Privileged session coverage:** Phần truy cập có log/broker khi được yêu cầu.
- **Unowned privileged accounts:** Account quyền cao không có identity/service owner.
- **Stale eligibility after Mover:** Role eligible cũ vẫn có thể kích hoạt trái policy.
- **Leaver residual access:** Credential, token, session hoặc role còn hiệu lực sau mốc cần thu hồi.
- **Time to verified revoke:** Từ biến cố đến khi target xác nhận quyền không còn.
- **Break-glass use and review:** Các lần dùng khẩn cấp và tình trạng hậu kiểm.
- **SoD violations:** Xung đột quyền hoặc phê duyệt sai người.
- **Credential exposure/rotation findings:** Secret có dấu hiệu lộ, không còn owner hoặc chưa được rotate theo chính sách.

**Không nên tối ưu chỉ số “activation success” bằng cách bỏ approval hoặc tăng quyền.** Hiệu quả cần được đo đồng thời qua **khả năng vận hành hợp lệ và khả năng ngăn/thu hồi đặc quyền sai**.

## 25. Tình huống thực hành A: role quản trị tồn dư sau Mover

**Bối cảnh:** Bình chuyển từ Platform Operations sang Data Analytics. HR đã cập nhật vai trò mới và IAM gỡ nhóm `platform-operators`. Tuy nhiên Bình vẫn nằm trong tập **eligible** để kích hoạt `cloud-admin@production` ở PIM. Trong một sự cố, Bình có thể yêu cầu activation dù không còn nhiệm vụ vận hành.

**Vấn đề:** Mover chỉ cập nhật **một nhóm** mà bỏ sót **privileged eligibility**. Nếu approval dựa trên policy cũ, tài khoản có thể tái nhận đặc quyền.

**Hướng xử lý:**

1. Xác nhận biến cố Mover và phạm vi nhiệm vụ mới.
2. Recompute **desired eligibility** và active grants theo role mới.
3. Gỡ eligibility không còn căn cứ ở PIM, role/cloud group liên quan.
4. Kiểm **direct grants**, phiên và token đã được cấp.
5. Test Bình không thể kích hoạt `cloud-admin@production` khi không còn đủ điều kiện.
6. Lưu readback từ PIM và target, cùng sự kiện audit.

**Bài học:** Thu hồi **role đang active** mà bỏ **khả năng kích hoạt lại** vẫn tạo quyền truy cập tồn dư.

## 26. Tình huống thực hành B: Leaver từng biết mật khẩu dùng chung

**Bối cảnh:** Một quản trị viên nghỉ việc. Công ty disable tài khoản SSO của người đó, nhưng hệ thống database legacy dùng account `db_maint_shared` với mật khẩu từng được quản trị viên checkout từ vault.

**Rủi ro:** Disable SSO không vô hiệu hóa mật khẩu đã biết. Nếu account shared vẫn chấp nhận kết nối, cựu nhân viên có thể còn đường truy cập nếu mạng và các lớp kiểm soát khác cho phép.

**Hướng xử lý:**

1. Kiểm kê account legacy, người đã từng có khả năng biết credential và target đang sử dụng.
2. Đánh giá khẩn cấp theo mức độ nhạy cảm dữ liệu và khả năng truy cập bên ngoài.
3. Rotate mật khẩu **tại database đích**, cập nhật vault và ứng dụng phụ thuộc theo quy trình an toàn.
4. Hạn chế/kết thúc session còn dùng credential cũ theo khả năng target.
5. Kiểm tra mạng/bastion và các đường truy cập ngoài PAM.
6. Xem xét chuyển sang **account định danh riêng, credential ngắn hạn hoặc cơ chế quản trị có thể truy vết**.
7. Readback credential cũ không còn tác dụng và audit đã ghi.

**Bài học:** Vault không thể thu hồi một bí mật **đã rời khỏi vault** nếu hệ thống đích vẫn tin bí mật đó.

## 27. Tình huống thực hành C: service principal có quyền hơn nhu cầu

**Bối cảnh:** Một pipeline chỉ cần deploy một dịch vụ ở staging, nhưng service principal của pipeline có quyền quản trị toàn bộ cloud subscription production. Pipeline do một nhóm nhiều người có quyền sửa.

**Rủi ro:** Quyền sửa pipeline tạo **đường đặc quyền gián tiếp**. Credential bị lộ hoặc thay đổi code có thể ảnh hưởng nhiều hệ thống hơn mục đích.

**Hướng xử lý:**

- Xác minh workload ID, owner và những người được sửa pipeline.
- Chuyển credential sang cơ chế workload federation/managed identity phù hợp khi nền tảng hỗ trợ.
- Giới hạn role tới **staging resource** và những action deployment cần thiết.
- Tách policy giữa staging/production và bảo vệ release production.
- Áp review/approval cho thay đổi pipeline nhạy cảm.
- Rotate/revoke credential production cũ sau migration có kiểm chứng.
- Test workload không thể thao tác ngoài audience/resource được phép.

**Bài học:** **Chủ thể có đặc quyền** có thể là workload, và người có quyền **điều khiển workload** cũng cần được xét trong threat model.

## 28. Tình huống thực hành D: break-glass bị dùng thay quy trình thường

**Bối cảnh:** Đội vận hành thường xuyên dùng account khẩn cấp để bỏ qua bước xin JIT, vì cho rằng ticket quá chậm. Account có quyền rộng và ít được ghi nhận.

**Phân tích:** Đây không còn là break-glass đúng mục đích. Một ngoại lệ thường xuyên chứng tỏ **workflow bình thường có vấn đề**, nhưng giải pháp không phải duy trì quyền không kiểm soát.

**Cần làm gì?**

1. Phân loại tình huống nào thật sự khẩn cấp, tình huống nào là vận hành có lịch.
2. Cải tiến JIT workflow, predefined scope hoặc automated approvals khi rủi ro cho phép.
3. Giới hạn người/thiết bị được sử dụng break-glass và cơ chế alert.
4. Kiểm thử khả dụng của credential khẩn cấp theo lịch.
5. Định kỳ review từng phiên khẩn cấp; xử lý lý do sử dụng sai.
6. Rotate/revoke secret và kiểm đặc quyền tồn dư sau sử dụng.

## 29. Tình huống thực hành E: JIT hết hạn nhưng phiên vẫn thao tác được

**Bối cảnh:** Khánh được cấp `database_admin` 30 phút. Lúc 21:00, PIM báo activation hết hạn, nhưng một phiên database được mở từ 20:40 vẫn tiếp tục cho phép chạy thao tác admin đến 22:00.

**Vấn đề:** **TTL của grant không nhất thiết bằng TTL của phiên hoặc token mà target đang tin.** Nếu chính sách đòi hết quyền ở 21:00, hệ thống chưa hoàn tất thu hồi.

**Cách xử lý:**

1. Xác định chính sách về phiên đã được nâng quyền khi grant hết hạn.
2. Kiểm target/session có re-evaluate quyền khi thao tác hay chỉ kiểm lúc login.
3. Áp giới hạn phiên hoặc chấm dứt khi hết hạn theo cơ chế được hỗ trợ.
4. Đánh giá token/credential đã phát; không chỉ đọc trạng thái PIM.
5. Thử negative case sau expiry và lưu bằng chứng.
6. Cập nhật kiến trúc/runbook nếu không thể bảo đảm thu hồi tức thời.

**Bài học:** JIT chỉ thực sự giới hạn cửa sổ rủi ro khi **khả năng sử dụng đặc quyền** cũng bị giới hạn và kiểm chứng được.

## 30. Câu hỏi tự kiểm tra

**Câu 1.** Một nhân viên không có role `admin` nhưng có thể sửa CI/CD pipeline chạy bằng service account production. Họ có cần được xem là có khả năng đặc quyền không?

**Gợi ý:** Có thể có **indirect privileged access**; cần đánh giá quyền và blast radius thực tế của pipeline.

**Câu 2.** Người dùng đăng nhập qua SSO và MFA mạnh. Có đủ điều kiện xóa database production chưa?

**Gợi ý:** Chưa. Cần authorization theo nhiệm vụ, role/grant, target, scope, JIT/approval và điều kiện bổ sung.

**Câu 3.** Khác biệt giữa JIT và just-enough access?

**Gợi ý:** JIT giới hạn **thời gian**; just-enough giới hạn **hành động và phạm vi**. Cả hai cần được kết hợp khi phù hợp.

**Câu 4.** PIM báo role đã hết hạn, nhưng target vẫn có session admin. Có thể coi đã thu hồi không?

**Gợi ý:** Không nếu session còn thực hiện quyền trái policy. Cần readback hiệu lực tại target.

**Câu 5.** Một kỹ sư chuyển bộ phận. Ngoài group admin, cần kiểm gì?

**Gợi ý:** Eligible/active grants, role cục bộ, direct ACL, token, session, SSH/API key và service account liên quan.

**Câu 6.** Vì sao không nên dùng tài khoản `root` chung để mọi kỹ sư đăng nhập?

**Gợi ý:** Khó quy trách nhiệm, credential có thể bị sao chép, khó thu hồi cá nhân; nên dùng danh tính riêng và cơ chế quản trị có kiểm soát.

**Câu 7.** Khi người quản trị service principal rời công ty, có nên xóa ngay principal production không?

**Gợi ý:** Không tự động. Cần đánh giá workload và phụ thuộc, chuyển owner, rà soát/rotate credential, giảm quyền và thử chức năng.

**Câu 8.** Break-glass có nên luôn bỏ mọi logging để thao tác nhanh?

**Gợi ý:** Không. Cần khả năng sử dụng khẩn cấp **cùng** kiểm toán và hậu kiểm theo phương án độc lập/an toàn.

**Câu 9.** Token cũ vẫn có quyền gọi API sau Leaver dù IdP disable. Vì sao?

**Gợi ý:** API có thể đang tin token đã phát offline; cần chiến lược thu hồi hoặc kiểm trạng thái hiện hành theo yêu cầu.

**Câu 10.** Người quản trị tenant A có được thao tác tenant B nếu role name là `admin`?

**Gợi ý:** Không tự động. Scope và resource tenant phải được kiểm tại PEP/API.

**Câu 11.** Vault đã xóa quyền checkout password cho người Leaver. Mật khẩu cũ đã chắc chắn vô hiệu chưa?

**Gợi ý:** Chưa. Nếu họ biết bản sao và target chưa rotate, credential cũ vẫn có thể hợp lệ.

**Câu 12.** “Đã gửi yêu cầu revoke” có đồng nghĩa “đã không còn quyền” không?

**Gợi ý:** Không. Phải xem kết quả tại target, session/token, ACL, credential và bằng chứng xác minh.

## 31. Checklist nhận diện và kiểm soát privileged access

- [ ] **Định nghĩa đúng:** Quyền đặc quyền được phân loại theo tác động thực tế, không chỉ theo role name?
- [ ] **Inventory:** Có danh sách privileged identities, accounts, roles, credentials, sessions, workloads và owner?
- [ ] **Mapping:** Account quản trị/local/cloud được ánh xạ đúng canonical identity hoặc workload ID?
- [ ] **Least privilege:** Quyền giới hạn action, resource, tenant và environment?
- [ ] **Standing privilege:** Đã giảm quyền thường trực không có căn cứ, cân nhắc JIT/JEA?
- [ ] **Eligibility:** Quyền được phép kích hoạt được quản trị riêng khỏi active grant và có expiry/review?
- [ ] **Approval/SoD:** Có căn cứ nghiệp vụ, người duyệt và kiểm xung đột phù hợp rủi ro?
- [ ] **Authentication:** MFA mạnh, step-up và device/session conditions được áp cho đường đặc quyền?
- [ ] **Credential:** Password/key/certificate/secret được bảo vệ, có owner, rotation và khả năng revoke?
- [ ] **PAM/PIM:** Vault, activation, broker/session và policy không bị nhầm là một kiểm soát duy nhất?
- [ ] **PEP/API:** Mọi action đặc quyền có kiểm quyền backend, bao gồm đường batch/automation?
- [ ] **Tenant/resource:** Không mở rộng quyền vì tên role `admin` hoặc token hợp lệ?
- [ ] **Indirect privilege:** Có xem quyền sửa group, pipeline, secret và policy là đường tác động đặc quyền?
- [ ] **Joiner:** Không clone quyền của người cũ; account/eligible role đúng người, đúng nhiệm vụ/mốc?
- [ ] **Mover:** Gỡ eligible và active grants, quyền cục bộ, session/token và direct grants hết căn cứ?
- [ ] **Leaver:** Disable account chỉ là một bước; đã thu hồi credential, role, session, token và target quyền tồn dư?
- [ ] **Workload:** Service account có owner kỹ thuật, scope, credential lifecycle và phương án khi owner nghỉ?
- [ ] **Break-glass:** Có phương án khẩn cấp, kiểm tra khả dụng, alert, hậu kiểm và thu hồi sau sử dụng?
- [ ] **Audit:** Có request, approval, actor, scope, activation, action, revocation và correlation ID?
- [ ] **Privacy:** Không ghi password, secret, token nguyên văn hoặc nội dung ghi hình phiên quá mức?
- [ ] **Readback:** Có bằng chứng quyền hiệu dụng bị chặn sau TTL/Mover/Leaver thay vì chỉ nhận API response?
- [ ] **Monitoring:** Có chỉ số standing privilege, stale role, JIT, SoD, ownerless account và residual access?
- [ ] **Exception:** Tất cả ngoại lệ có owner, lý do, thời hạn, kiểm soát bù trừ và lịch đóng?
- [ ] **Governance:** Role, policy và privileged access được rà soát định kỳ theo thay đổi JML và rủi ro?

## 32. Kết luận

**Privileged access là quyền truy cập có khả năng tác động lớn đến hệ thống, dữ liệu, các chủ thể khác hoặc chính cơ chế bảo mật.** Nó có thể tồn tại dưới dạng **role, direct grant, account, credential, phiên quản trị hay quyền gián tiếp qua automation/workload**, không chỉ một tài khoản tên `admin`.

Quản trị hiệu quả bắt đầu bằng **nhận diện chủ thể và blast radius**, sau đó áp **least privilege, SoD, MFA, giới hạn phạm vi, JIT/just-enough access, bảo vệ credential, quản lý phiên và kiểm toán**. **IAM/IGA, IdP/SSO, PAM/PIM, SCIM và RBAC/ABAC** phải phối hợp nhưng không thay thế trách nhiệm của nhau.

Đối với **Joiner**, chỉ cấp đặc quyền đã có căn cứ; đối với **Mover**, thu hồi cả khả năng kích hoạt lại quyền cũ; đối với **Leaver**, kiểm account, role, phiên, token, secret và quyền tại target. **Kết quả cuối cùng phải là quyền hiệu dụng được xác minh**, không phải chỉ một yêu cầu revoke thành công. Đó là cách quản lý vòng đời danh tính **cấp đúng quyền, giảm nguy cơ lạm dụng và ngăn quyền truy cập tồn dư**.
