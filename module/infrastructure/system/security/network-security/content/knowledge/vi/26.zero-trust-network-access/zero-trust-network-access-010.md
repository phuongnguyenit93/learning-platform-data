# Bảo vệ tài nguyên quản trị trong Zero Trust Network Access

## 1. Vì sao tài nguyên quản trị phải được bảo vệ khác biệt?

Trong hệ thống doanh nghiệp, một nhân viên có thể dùng trình duyệt truy cập trang nội bộ để xử lý công việc, nhưng một người quản trị lại có thể dùng **SSH**, **Remote Desktop Protocol (RDP)**, **Kubernetes API**, **cloud console**, bảng điều khiển firewall, hệ thống DNS, PKI hay backup để thay đổi cách cả hạ tầng hoạt động. Khi tài nguyên quản trị bị xâm nhập, tác động không chỉ là lộ một dữ liệu đơn lẻ: kẻ tấn công có thể tạo tài khoản đặc quyền, sửa chính sách mạng, lấy khóa ký, thay đổi route hoặc vô hiệu hóa giám sát.

**Zero Trust Network Access (ZTNA)** tiếp cận bài toán bằng nguyên tắc: **không cấp niềm tin lâu dài chỉ vì người dùng đang ở mạng nội bộ, đã kết nối VPN hoặc có địa chỉ IP cho phép**. Mỗi yêu cầu quản trị phải dựa trên **danh tính, thiết bị, ngữ cảnh, quyền đối với đúng tài nguyên và tín hiệu rủi ro**; được thực thi tại một điểm kiểm soát mà người dùng không thể đi vòng.

Một mô hình yếu thường là:

~~~text
Administrator --VPN--> entire management subnet
                        |-- SSH to all servers
                        |-- RDP to jump hosts
                        |-- Network device console
                        |-- Kubernetes/API endpoints
                        +-- Secrets and backup management
~~~

Ở mô hình đó, VPN có thể bảo vệ kênh đến mạng doanh nghiệp, nhưng sau khi kết nối, **quyền kết nối ngang** có thể quá rộng và khó phân biệt hành động hợp lệ với lạm dụng. Mô hình ZTNA tốt hơn phải giới hạn **đúng người, đúng thiết bị, đúng thời gian, đúng hệ thống, đúng thao tác**, và duy trì tính sẵn sàng của đường khôi phục khẩn cấp.

### Mục tiêu học tập

Sau bài, người học có thể:

1. Nhận diện và phân loại các **tài sản quản trị trọng yếu** thuộc network/cloud/container infrastructure.
2. Giải thích **control plane, management plane, data plane** và vùng tin cậy của đường quản trị.
3. Áp dụng mô hình **Policy Decision Point (PDP), Policy Enforcement Point (PEP)** và signals liên tục của ZTNA.
4. Phối hợp **phishing-resistant MFA**, device posture, conditional access, just-in-time access, PAM/PIM và least privilege.
5. Thiết kế đường SSH/RDP, cloud console, Kubernetes API và thiết bị mạng **không lộ trực tiếp Internet** khi không cần.
6. Phân biệt **network reachability, authentication, authorization, approval và audit**.
7. Bảo vệ non-human identities, automation và các kênh quản trị ngoài băng.
8. Xây quy trình **break-glass/recovery** không biến tài khoản khẩn cấp thành ngoại lệ luôn được mở rộng.
9. Thiết kế **allow/deny tests**, theo dõi phiên và phản ứng sự cố khi nghi ngờ credential/device compromise.
10. Triển khai theo từng giai đoạn có rollback, giảm rủi ro tự khóa đội vận hành khỏi hệ thống.

Chủ đề nằm trong chương **Zero Trust Network Access** của module **SECURITY_NETWORK_SECURITY**: kết hợp phân đoạn, firewall, VPN, IDS/IPS, DNS, TLS/PKI, xác thực kết nối và bảo mật mạng cloud để hạn chế **quyền điều khiển hệ thống qua mặt phẳng quản trị**.

> **Giới hạn thực hành:** địa chỉ và tên miền ở ví dụ là địa chỉ giả lập; lệnh được phân loại rõ thành **chỉ đọc** hoặc **cấu hình minh họa**. Không thử đăng nhập vào tài nguyên, rà quét management ports, sửa IAM/firewall hay bật/tắt MFA ngoài hệ thống và thẩm quyền được giao. Các thay đổi trên quản trị từ xa phải có đường khôi phục được kiểm thử.

## 2. Định nghĩa và phân loại tài nguyên quản trị

**Tài nguyên quản trị** là giao diện, API, hệ thống, credential hoặc dịch vụ cho phép quan sát hay thay đổi trạng thái hạ tầng, chính sách truy cập, cấu hình bảo mật hoặc dữ liệu vận hành có quyền cao.

| Nhóm | Ví dụ | Hậu quả nếu lộ đặc quyền |
|---|---|---|
| **Máy chủ/hệ điều hành** | SSH, RDP, Windows Admin Center, WinRM, remote shell | Chạy lệnh, thay binary, lấy secrets, pivot |
| **Kubernetes/container platform** | kube-apiserver, cluster admin, kubelet, runtime socket, GitOps | Tạo Pod đặc quyền, đọc Secrets, thay NetworkPolicy |
| **Cloud control plane** | AWS/Azure/GCP consoles/APIs, IAM, organization policies | Tạo public exposure, thay IAM, xóa logs, lấy snapshots |
| **Thiết bị mạng** | Firewall, router, switch, SD-WAN, VPN concentrator, Wi-Fi controller | Đổi ACL/routes, điều hướng lưu lượng, tắt inspection |
| **Identity/trust infrastructure** | IdP, directory, SSO, MFA admin, CA/PKI, HSM/KMS | Phát identity/credential giả, phá chuỗi xác thực |
| **DNS/secret infrastructure** | DNS control panel, Vault/secrets manager, certificate automation | Chuyển đích lưu lượng, lộ token/private key |
| **Dữ liệu/backup** | Database admin, object storage admin, backup console, DR orchestration | Lộ/sửa dữ liệu, phá khả năng phục hồi |
| **Ảo hóa/ngoài băng** | Hypervisor console, BMC/IPMI/Redfish, serial console | Chiếm quyền dưới OS, thay firmware hoặc boot |
| **DevOps/observability** | CI/CD runners, deployment tokens, SIEM/EDR admin, logging config | Đưa mã độc vào supply chain, xóa bằng chứng |
| **Network/security policy** | Security groups, NSG, transit gateway, network ACLs, WAF rules | Mở đường bypass, tạo lateral movement |

**Không phải mọi đường quản trị đều là một cổng TCP/22 hoặc 3389.** Có những quyền nguy hiểm được thực thi qua web/API, automation token hoặc quyền điều hành **control plane** của cloud provider. Đổi cổng SSH/RDP hay đặt tên subnet `management-private` không tự bảo vệ những đường đó.

### 2.1. Nhóm theo mức tác động

Một phân loại thực dụng:

- **Tier 0 / quyền gốc:** IdP/SSO administration, CA/KMS, directory administrators, root cloud org, secrets root, hypervisor/BMC và hệ thống quản trị nền tảng quyết định danh tính/quyền của tất cả các tầng.
- **Tier 1 / hạ tầng sản xuất:** cluster admins, network firewall controllers, production databases, deployment controls và security monitoring có quyền rộng.
- **Tier 2 / quản trị ứng dụng:** service deployment trong một namespace, non-production admin, dashboard vận hành giới hạn.

Đây chỉ là **ví dụ phân tầng theo rủi ro**, không phải tiêu chuẩn tier áp dụng đồng nhất ở mọi tổ chức. Điểm quan trọng là: **không để một credential hoặc thiết bị ở tầng ít tin cậy hơn tự do quản trị tầng trọng yếu hơn**.

### 2.2. Tài sản có tính “quyền dẫn xuất”

Một hệ thống không trực tiếp mang tên “admin” vẫn có thể cho phép **quyền quản trị gián tiếp**, ví dụ:

- Repository/pipeline có thể deploy IAM role đặc quyền.
- Kubernetes Pod có thể mount runtime socket để điều khiển node.
- Backup service có thể phục hồi/sửa image hệ thống trọng yếu.
- DNS admin có thể đổi domain dùng cho SSO hoặc PKI validation.
- Cloud automation runner có quyền thay route/firewall.

Vì vậy asset inventory phải mô hình hóa **quan hệ ai có thể cấp quyền cho ai**, không chỉ liệt kê URL quản trị.

## 3. Control plane, management plane và data plane

| Plane | Công việc điển hình | Ví dụ | Kiểm soát |
|---|---|---|---|
| **Data plane** | Xử lý lưu lượng/nghiệp vụ thật | Web API, packet forwarding, database queries | WAF, L7 authz, segmentation, TLS |
| **Control plane** | Định nghĩa desired state, cấp policy/route | Kubernetes API, cloud control APIs, SDN controller | Strong authn, PIM, RBAC, approval, audit |
| **Management plane** | Quản trị, chẩn đoán, cập nhật, phục hồi | SSH/RDP, out-of-band console, monitoring/backup admin | ZTNA, PAM, PAW, isolation, session evidence |

Các khái niệm **có thể giao nhau**. Cloud console vừa là giao diện quản trị vừa là control plane. Kubernetes API là control plane nhưng cũng là tài nguyên quản trị. Không cần ép mỗi hệ thống thuộc đúng một nhãn; cần xác định **những thao tác có tác động điều khiển** và cách hạn chế quyền.

### 3.1. Kiến trúc truy cập theo quyết định và thực thi

~~~mermaid
flowchart LR
    ADM["Administrator / PAW"] --> SSO["IdP + phishing-resistant MFA"]
    ADM --> Z["ZTNA client / access portal"]
    SSO --> PDP["Policy Decision Point"]
    DEV["Device posture / EDR"] --> PDP
    JIT["JIT request / approval / risk"] --> PDP
    PDP -->|"Permit limited action / TTL"| PEP["Policy Enforcement Point"]
    Z --> PEP
    PEP -->|"Target-specific session"| T["SSH/RDP/K8s API/Cloud console"]
    T --> LOG["Audit + session telemetry"]
    PEP --> LOG
~~~

Mô hình trên minh họa **luồng quyết định logic**, không hàm ý mọi sản phẩm ZTNA đều có cùng portal, client agent hoặc cú pháp policy. Một số giải pháp đưa PEP vào application proxy, identity-aware gateway, service connector hoặc native IAM control của cloud.

### 3.2. PDP và PEP làm gì?

**PDP** tập hợp policy và ngữ cảnh (identity, MFA, device posture, sensitivity, approval, location/risk, time) để quyết định một yêu cầu có đủ điều kiện không. **PEP** phải thực thi quyết định trên đường truy cập tới tài nguyên: chỉ tạo/cho phép kênh và hành động phù hợp, giám sát hoặc ngắt khi chính sách yêu cầu.

**Policy trong dashboard mà đường SSH/RDP vẫn mở trực tiếp ngoài PEP thì không phải enforcement hoàn chỉnh.** Cần chặn bypass ở firewall, private routing, identity/API policy và quyền trên endpoint, rồi kiểm thử từ nguồn không qua ZTNA.

### 3.3. Session không phải quyền vĩnh viễn

Một quyết định cho phép có thể giới hạn:

~~~text
Subject: alice-admin@example.test (ví dụ)
Device: managed privileged workstation, EDR healthy
Resource: prod-db-admin-01
Protocol: SSH
Role: diagnostics-read-only
Valid: 15 minutes
Approval: change ticket CHG-LAB-015
Session: auditable, no clipboard/file transfer unless approved
Reevaluate: posture degradation, identity revocation, expiry
~~~

Đây là **mô hình ý định**, không phải policy schema có thể áp dụng nguyên văn. Thời lượng và điều kiện re-evaluation phải phù hợp rủi ro và khả năng kỹ thuật, không mặc định mọi giao thức hỗ trợ ngắt phiên tức thời như nhau.

## 4. ZTNA không phải VPN đổi tên

Một VPN site-to-site hoặc remote-access VPN thường xây dựng **kênh mạng** tới tổ chức. ZTNA tập trung vào **quyền đối với tài nguyên cụ thể** và ngữ cảnh từng phiên. Hai cơ chế có thể **kết hợp**, không phải lúc nào cũng thay thế một-một.

| Câu hỏi | VPN truyền thống (mẫu tổng quát) | ZTNA theo tài nguyên |
|---|---|---|
| Quyền được cấp | Có thể là một số network prefixes/routes | Một ứng dụng/hostname/port hoặc operation được duyệt |
| Thiết bị | Có thể có certificate/MFA/posture nếu được cấu hình | Device/risk thường là tín hiệu policy trọng tâm |
| Xác thực | Khi thiết lập tunnel, có thể thêm điều kiện | Theo ứng dụng/phiên/identity và chính sách |
| Reachability | Có thể tạo nhiều đường east–west rộng | Giảm bề mặt bằng kết nối chỉ tới đích được duyệt |
| Lateral movement | Rủi ro nếu routes/ACL quá rộng | Giảm nếu PEP không bị bypass và policies đủ hẹp |
| Giám sát | Tunnel traffic, VPN auth/session | Quyết định user/device/resource + session telemetry |

**Không mô tả mọi VPN là “không có MFA” hoặc “cho vào toàn bộ LAN”.** Nhiều VPN triển khai certificate, MFA và firewall phân đoạn tốt. Khác biệt cốt lõi là **mô hình cấp quyền và điểm thực thi**, không phải nhãn sản phẩm.

### 4.1. Ví dụ hai đường vào

~~~mermaid
flowchart TD
    A["Remote administrator"] --> VPN["VPN / mạng công ty"]
    VPN -. "Nếu routes rộng + ACL yếu" .-> ALL["Management subnet / nhiều hệ thống"]
    A --> ZTNA["Identity-aware access broker"]
    ZTNA --> ONE["Chỉ prod-db-admin-01:SSH"]
    ZTNA -. "Không cấp mạng rộng" .-> BLOCK["Other management endpoints"]
~~~

Mục tiêu không phải cấm mọi IP routing, mà là **không xem VPN connectivity như quyền quản trị**. Dù có VPN, áp dụng **MFA, JIT role, firewall ACLs, server authn/authz và session audit** tại từng đích.

## 5. Xác thực danh tính quản trị: ưu tiên chống phishing

Quyền quản trị cần được gắn với **danh tính cá nhân có thể truy vết** và cơ chế xác thực phù hợp rủi ro. Các tài khoản dùng chung như `admin`, `root` hoặc `administrator` khiến việc quy trách nhiệm khó hơn, đặc biệt khi mật khẩu được chia sẻ qua ticket hoặc chat.

### 5.1. Những nguyên tắc nền tảng

- **Danh tính cá nhân:** một người dùng danh tính riêng để đề nghị phiên quản trị; quyền được cấp qua role/entitlement có thể thu hồi.
- **MFA mạnh, chống phishing khi khả thi:** FIDO2/WebAuthn passkeys hoặc security keys được xác thực với đúng origin là ví dụ điển hình. TOTP/OTP vẫn có ích trong một số môi trường nhưng **không có cùng mức chống phishing** nếu người dùng có thể nhập mã vào trang giả.
- **SSO và identity lifecycle:** joiner/mover/leaver processes; khóa tài khoản ngay khi offboard hoặc phát hiện rủi ro.
- **Step-up authentication:** với hành động rủi ro cao (thay IAM, xuất khóa, xóa backup, đổi firewall), có thể cần xác thực lại theo chính sách và sản phẩm hỗ trợ.
- **Đường khôi phục riêng:** IdP outage không nên dẫn đến cả đội mất toàn bộ khả năng khôi phục, nhưng break-glass phải được bảo vệ nghiêm ngặt.

### 5.2. Phân biệt đăng nhập và được cấp quyền

~~~text
IdP xác nhận:
  Đây là tài khoản người quản trị thuộc tổ chức.

Device checks xác nhận:
  Thiết bị đạt điều kiện phù hợp tại thời điểm đánh giá.

PAM/PIM xác nhận:
  Người này có quyền tạm thời với tài nguyên cụ thể.

Target xác nhận:
  Session/role được phép chạy đúng nhóm lệnh hoặc API.

Audit xác nhận:
  Ai truy cập, điều kiện nào, lúc nào và đã làm gì.
~~~

Một người đăng nhập SSO thành công **không được tự trở thành cloud account owner, Kubernetes cluster-admin hay quản trị firewall**. ZTNA không làm mất nhu cầu kiểm soát **RBAC/ABAC** tại đích.

### 5.3. Quản trị các identity providers cũng là Tier 0

Người có quyền sửa authentication policy, đăng ký MFA factors, reset credential hoặc tạo federation trust ở IdP có thể ảnh hưởng quyền vào **mọi tài nguyên đang tin IdP**. Đừng để chính đường quản trị IdP phụ thuộc hoàn toàn vào cấu hình mà một người khác có thể tự thay khi chưa có approval/quorum. Thiết kế tách nhiệm vụ và audit đặc biệt cho **reset MFA, đăng ký thiết bị bảo mật, cấp emergency roles và thay trust federation**.

## 6. Device posture và Privileged Access Workstation (PAW)

**Danh tính mạnh không đủ** nếu thiết bị quản trị đã bị nhiễm mã độc. Một tài khoản có FIDO2 MFA vẫn có thể bị chiếm quyền **phiên hợp lệ** bằng malware trên máy đã đăng nhập hoặc bị lạm dụng qua remote assistance. ZTNA cần xét **tư thế bảo mật thiết bị** (*device posture*) và mức độ tin cậy của workstation.

### 6.1. Những tín hiệu thường dùng

| Tín hiệu | Cách diễn giải | Giới hạn cần ghi nhớ |
|---|---|---|
| Device enrollment/certificate | Thiết bị thuộc inventory quản lý | Không tự chứng minh không bị xâm nhập |
| EDR/anti-malware health | Agent đang hoạt động và báo trạng thái | Agent có thể bị bypass, mất kết nối hoặc báo trễ |
| OS/security patch level | Hệ điều hành đáp ứng baseline tối thiểu | Không loại bỏ zero-day |
| Disk encryption | Giảm rủi ro lộ dữ liệu khi thiết bị mất | Không bảo vệ hoàn toàn phiên đang mở |
| Screen lock & local privilege | Hạn chế sử dụng trái phép thiết bị | Có thể bị malware vượt qua |
| MDM/compliance state | Thiết bị tuân thủ một bộ policy | Compliance chỉ là **một tín hiệu** |
| Hardware-backed key / secure boot | Bổ sung trust cho khóa và đường khởi động theo hỗ trợ | Phụ thuộc implementation và attestation |
| Network/risk context | Kết nối mới, hành vi bất thường, impossible travel | Geolocation/IP có thể sai do VPN/NAT |

**Không xem posture là chứng minh thiết bị sạch tuyệt đối.** Đó là đánh giá rủi ro có điều kiện; cần log provenance, freshness, tamper resistance và mô hình xử lý khi tín hiệu stale.

### 6.2. PAW giảm giao thoa giữa duyệt web và quản trị

**Privileged Access Workstation (PAW)** là thiết bị/môi trường dành cho thao tác đặc quyền, được harden và giới hạn ứng dụng/đường truy cập. Ý định:

- Không dùng cùng profile/browser session để duyệt Internet không tin cậy và quản trị Tier 0.
- Chỉ cài công cụ cần thiết, hạn chế local admin, bảo vệ secrets và clipboard theo risk.
- Không cho máy không được quản lý truy cập thẳng BMC, firewall admin hoặc production SSH.
- Có EDR, patching, secure boot, encryption và kiểm soát thiết bị ngoại vi phù hợp.
- Tách credentials, sessions và audit của môi trường quản trị với công việc hằng ngày.

PAW có thể là workstation chuyên dụng, virtualized secure workspace hoặc giải pháp tương đương theo threat model; **tên “PAW” không tự tạo bảo mật** nếu nó dùng chung credential, thiếu quản lý thiết bị hoặc vẫn mở Internet rộng.

### 6.3. Chuyển trạng thái khi posture xấu

~~~mermaid
flowchart TD
    START["User yêu cầu phiên admin"] --> CHECK{"Identity/MFA và device posture hợp lệ?"}
    CHECK -- "Không" --> NO["Từ chối hoặc remediation route"]
    CHECK -- "Có" --> JIT["Kiểm tra quyền JIT/approval"]
    JIT --> PEP["Mở phiên resource-scoped"]
    PEP --> RECHECK{"Có thay đổi risk/posture/session TTL?"}
    RECHECK -- "Có" --> REVOKE["Re-evaluate / revoke theo khả năng kỹ thuật"]
    RECHECK -- "Không" --> MON["Giám sát phiên"]
    MON --> RECHECK
~~~

**Revoke trong portal không luôn chấm dứt lập tức một SSH shell hoặc RDP session đã thiết lập.** Cần kiểm thử cơ chế session termination, credential TTL, target logout, network enforcement và cache của từng sản phẩm.

## 7. Least privilege, JIT, JEA và quản lý đặc quyền

**Privileged Access Management (PAM)** thường quản lý các tài khoản, credentials, session và thao tác đặc quyền. **Privileged Identity Management (PIM)** tập trung vào vòng đời/activation các vai trò đặc quyền. **Just-in-Time (JIT)** giới hạn thời gian có quyền, còn **Just Enough Administration (JEA)** giới hạn thao tác được thực hiện.

### 7.1. Vì sao quyền thường trực làm tăng rủi ro?

Một tài khoản có quyền `cluster-admin` hoặc sửa IAM production **24/7** vẫn nguy hiểm ngay cả khi hiếm dùng. Nếu token, session hoặc thiết bị bị chiếm lúc không ai quản trị, attacker có thể tận dụng quyền có sẵn mà không cần một bước cấp quyền mới.

JIT thay bằng quy trình:

1. Người quản trị gửi yêu cầu cho một **resource/role/action**.
2. Hệ thống xác minh identity, MFA, device posture, business reason và rủi ro.
3. Reviewer hoặc chính sách tự động duyệt theo mức nhạy cảm và **separation of duties**.
4. Broker/PIM cấp quyền tạm thời hoặc session vào đúng target.
5. Hết TTL, quyền/credential được thu hồi; log và evidence được lưu.

### 7.2. Cấp quyền theo thao tác thay vì quyền tổng quát

| Nhu cầu | Quyền phù hợp | Tránh |
|---|---|---|
| Đọc log ứng dụng | `get/list` logs đúng scope | `cluster-admin`, quyền đọc mọi Secret |
| Restart một Deployment | Patch/rollout đúng namespace/workload khi cho phép | Quyền deploy toàn cluster |
| Điều tra lỗi firewall | Read-only config/flow logs | Quyền sửa rules toàn bộ thiết bị |
| Đổi chứng thư một dịch vụ | Quyền quản lý certificate/Secret đã duyệt | Quyền đọc/export toàn bộ PKI private keys |
| Khôi phục database | Role backup/restore theo quy trình | Tài khoản root DBA luôn trực tuyến |
| Điều tra cloud incident | Read-only/audit forensic role và JIT escalation | Owner/admin thường trực mọi subscription/account |

**Một quyền “read-only” có thể vẫn nhạy cảm** nếu cho phép đọc Secrets, private keys, customer data hoặc backup snapshots. Cần đánh giá data classification, không chỉ HTTP GET hay tên role.

### 7.3. Approval không thay cho enforcement

Một ticket đã duyệt chỉ chứng minh **quy trình có quyết định**; nếu PEP/IAM/target không buộc người dùng có đúng role và TTL, người đó vẫn có thể dùng một đường khác. Các yếu tố **approval, identity, resource entitlement, connection enforcement và audit** phải liên kết với cùng một session hoặc change.

### 7.4. Tách nhiệm vụ cho Tier 0

Ví dụ một kỹ sư có thể **đề xuất** thay đổi IdP trust hoặc CA policy, nhưng người khác phải **duyệt**, và hệ thống thực thi **chỉ phiên role đã duyệt**. Không để một người tự cấp quyền, duyệt chính mình, xóa audit và tạo break-glass credential mà không có kiểm soát bù trừ.

## 8. Phân đoạn management network và chống bypass PEP

Mục tiêu ZTNA là **đúng đích có thể truy cập được khi được cấp quyền**, không phải một đường mặc định vào toàn bộ mạng quản trị.

### 8.1. Ba lớp cần phối hợp

1. **Network control:** private subnets/VLAN/VRF, deny inbound mặc định, cloud SG/NSG, ACL, firewall, route tới management network qua gateway.
2. **Identity/session control:** MFA, device posture, JIT/PAM/PIM, session broker, short-lived credentials.
3. **Target control:** OS/SSH/RDP settings, local RBAC/sudo/JEA, IAM permissions, API authorization, audit và patch management.

~~~mermaid
flowchart LR
    USER["Remote admin + PAW"] --> ZTNA["ZTNA broker / PEP"]
    ZTNA -->|":22 limited target"| LNX["Linux management host"]
    ZTNA -->|":3389 limited target"| WIN["Windows management host"]
    ZTNA -->|"API scope"| K8S["Kubernetes API"]
    NET["Untrusted user network"] -. "No direct route" .-> LNX
    NET -. "No direct route" .-> WIN
    NET -. "No direct route" .-> K8S
    FW["Cloud/on-prem firewall"] -. "Enforce source/destination" .-> ZTNA
~~~

### 8.2. Public IP không phải điều kiện cần cho quản trị

Một VM không cần public IPv4/IPv6 chỉ để SSH từ xa nếu tổ chức có **ZTNA connector, private relay, cloud-managed session broker, site-to-site link hoặc bastion** phù hợp. Tuy nhiên việc “không có public IP” **không tự đủ**: VPN/peering/transit, misconfigured LB hoặc một compromised Pod cùng VPC vẫn có thể kết nối.

### 8.3. Source network không phải identity

Cloud security group chỉ cho phép SSH từ IP của broker giúp giảm surface, nhưng **IP đó không chứng minh quản trị viên nào đã đăng nhập hoặc họ có quyền chạy sudo**. Broker phải liên kết session tới identity mạnh và target tiếp tục enforce role/credentials.

### 8.4. Kiểm tra đường ngoài dự kiến

| Đường bypass | Nguy cơ | Kiểm soát |
|---|---|---|
| Public SSH/RDP trên NIC phụ | Người dùng vào thẳng không qua broker | Inventory tất cả NIC/public IP/firewall |
| VPN route đến toàn management CIDR | Có thể lateral movement sau VPN | Destination ACL + app-specific PEP |
| Jump host có hai NIC | Có thể bridge/proxy qua vùng ít tin cậy | Hardening, egress allowlist, host firewall |
| Kubernetes Pod hostNetwork/privileged | Có thể tới node/admin endpoints | Admission, CNI/host firewall, identity |
| Cloud console role thường trực | Vượt ZTNA network gateway qua public cloud API | Native IAM conditional access/PIM |
| BMC management interface | Bypass OS firewall/hypervisor access control | OOB VRF/VLAN, separate credentials, PEP |
| DR site mạng quản trị mở rộng | Policy chỉ áp primary region | Kiểm thử tương đương mọi site |

**Điểm kiểm soát phải nằm trên tất cả đường vào thực tế**, kể cả cloud-native APIs và đường cứu hộ. Một policy trong ZTNA portal không thể chặn tài khoản IAM vẫn được đăng nhập trực tiếp vào cloud control plane nếu native IAM không có điều kiện tương ứng.

## 9. SSH: bảo vệ shell quản trị Linux/Unix

SSH là giao thức bảo vệ kênh truyền và xác thực server/client theo cấu hình. Với tài nguyên quản trị Linux, một thiết kế ZTNA cần bổ sung **session-level authorization, short-lived credentials và phân đoạn**.

### 9.1. Kiến trúc truy cập ưu tiên

~~~text
Administrator on managed PAW
  -> IdP with phishing-resistant MFA
  -> JIT approval / authorized role
  -> ZTNA/PAM broker with session audit
  -> Private SSH endpoint (approved port only)
  -> OS identity / sudo policy / command restrictions
~~~

Trên Linux server, broker nên kết nối bằng account/credential có **quyền tối thiểu**; target SSH daemon vẫn cần xác thực server host key, client identity, file permissions và audit. Nếu sản phẩm cung cấp SSH certificate ngắn hạn, phải quản lý **CA signing keys, principal mapping, TTL, revocation và target trust**.

### 9.2. SSH host keys và user keys/certificates

| Thành phần | Xác thực điều gì? | Rủi ro nếu thiếu |
|---|---|---|
| **Server host key** | Client nhận diện đúng máy đích SSH | MITM/đăng nhập nhầm host |
| **User public key/certificate** | Server xác minh credential của client | Password spraying/key theft nếu quản lý yếu |
| **PAM/IdP/broker entitlement** | Account có quyền quản trị target/session không | Một key hợp lệ có thể đi quá nhiều máy |
| **Sudo/JEA/OS authorization** | Lệnh nào được thực thi sau khi vào máy | SSH thành công thành root toàn hệ thống |
| **Session audit** | Ai vào, lúc nào, lệnh/hoạt động nào được ghi | Khó điều tra, đặc biệt với shared account |

**Không dùng `StrictHostKeyChecking=no` chỉ để bỏ cảnh báo host key.** Một kết nối ZTNA hợp lệ vẫn cần kiểm tra danh tính host và phát hiện key rotation trái phép.

### 9.3. Mẫu cấu hình SSH hardening để review

~~~text
# MẪU THAM KHẢO cho sshd_config; KHÔNG tự áp dụng trên máy từ xa.
# Luôn xác minh alternative admin access và rollback trước khi thay đổi.
PermitRootLogin no
PubkeyAuthentication yes
PasswordAuthentication no
AllowGroups ops-ssh-approved
X11Forwarding no
AllowTcpForwarding no
~~~

**Các lựa chọn trên không phù hợp mọi môi trường.** Ví dụ bật `PasswordAuthentication no` khi chưa triển khai public-key/certificate login hợp lệ sẽ tự khóa người quản trị; `AllowGroups` sai có thể loại tất cả users; một số automation/tunnel cần TCP forwarding theo thiết kế đã duyệt. Kiểm tra `sshd -T`/config test theo runbook và có **console/out-of-band recovery** trước khi reload dịch vụ.

### 9.4. Vấn đề agent forwarding, file transfer và port forwarding

SSH hỗ trợ **agent forwarding**, local/remote/dynamic port forwarding, SCP/SFTP. Những khả năng này có thể được dùng hợp lệ, nhưng cũng tạo đường **đi vòng phân đoạn mạng, chuyển file nhạy cảm hoặc lạm dụng SSH agent**. Chỉ bật theo nhu cầu và scope; nếu cần bắt buộc một lệnh, dùng **forced commands, certificate restrictions hoặc broker policy** thích hợp.

**Một shell SSH đầy đủ không đồng nghĩa “just enough administration”.** Nếu người dùng có `sudo ALL=(ALL) ALL`, giới hạn cổng ở gateway không ngăn họ thay đổi hệ thống sau khi đăng nhập.

## 10. RDP/Windows và quản trị từ xa có đặc quyền

RDP phục vụ desktop/console remote access trên Windows và một số môi trường khác. Như SSH, RDP dùng authentication/encryption theo cấu hình, nhưng **có đường RDP không có nghĩa được cấp quyền hợp lệ**.

### 10.1. Các lớp nên phối hợp

- Hạn chế **direct Internet RDP**; dùng broker/gateway/managed remote access tới đúng máy.
- Xác minh **server identity/TLS certificate** và cấu hình Network Level Authentication (NLA) theo Windows policy/phiên bản.
- Bắt buộc đăng nhập bằng account có quyền cụ thể, MFA tại gateway/identity layer và có thể step-up cho tác vụ nhạy cảm.
- Hạn chế **clipboard, drive redirection, printer/USB, file transfer** theo data classification.
- Áp dụng **Windows LAPS/managed local admin credentials**, local group policy và JEA/PowerShell remoting delegation phù hợp.
- Bảo vệ credential delegation, session lock, EDR và remote desktop session logs.

### 10.2. Khi nào cần privileged desktop?

RDP tới một host được ủy quyền có thể cho phép sử dụng **trình quản trị cloud, Active Directory, firewall web console** ngay từ host đó. Đây là **jump path** đặc biệt nhạy cảm: người vận hành có thể đăng nhập qua broker đúng quy trình, sau đó từ máy đích **đi sang những hệ thống khác không qua PEP ban đầu**.

Phòng vệ gồm **egress restrictions từ jump host, web allowlist, application control, PAW role separation, short-lived credentials, không lưu reusable tokens trên jump host và ghi nhận phiên**. Không sử dụng một jump server dùng chung có quyền truy cập mọi Tier 0 asset chỉ vì thuận tiện.

### 10.3. Khác biệt giữa kết nối và phiên người dùng

Gateway có thể đóng đường mạng nhưng một tài khoản Windows vẫn còn session/token/quyền trong một số tình huống. Cần kiểm tra cách **logoff session, thu hồi role, vô hiệu hóa token và cập nhật endpoint** thực sự hoạt động, thay vì coi kết thúc VPN là đủ.

## 11. Kubernetes API và hệ sinh thái container

Kubernetes API là control plane trọng yếu. Với đủ quyền, một actor có thể **tạo Pod đặc quyền, thay Service/Ingress/NetworkPolicy, đọc Kubernetes Secrets hoặc sửa RBAC**, từ đó mở đường kiểm soát workloads/nodes.

### 11.1. Threat model

~~~mermaid
flowchart LR
    PAW["Admin workstation / CI"] --> IDP["SSO/MFA or workload identity"]
    IDP --> PEP["Authorized API entry path"]
    PEP --> APIS["Kubernetes API server"]
    APIS --> RBAC["RBAC + admission"]
    RBAC --> RES["Pods, RBAC, Secrets, networking"]
    OTHER["Unapproved network or Pod"] -. "No admin API entitlement" .-> APIS
~~~

**Kubernetes NetworkPolicy thông thường kiểm soát Pod traffic theo CNI; nó không tự bảo vệ toàn bộ Kubernetes API server hoặc cloud-managed control plane.** Phải dùng **API endpoint exposure settings, identity provider integration, RBAC, admission policies, audit và network allowlists** theo môi trường.

### 11.2. RBAC chỉ đủ khi phạm vi hẹp

Ví dụ role **chỉ đọc pod metadata** ở namespace lab:

~~~yaml
# MẪU KUBERNETES ROLE: tạo/sửa resource nếu kubectl apply.
# Không triển khai production nếu chưa review, không cấp quyền Secrets.
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: pod-observer
  namespace: ztna-lab
rules:
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list", "watch"]
~~~

Một Role **không cấp quyền cho ai** cho tới khi có RoleBinding thích hợp:

~~~yaml
# MẪU LAB: group identity phải được xác nhận đến từ IdP hợp lệ.
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: pod-observers
  namespace: ztna-lab
subjects:
  - kind: Group
    name: ztna-lab-pod-observers
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: pod-observer
  apiGroup: rbac.authorization.k8s.io
~~~

**Ranh giới:** `get/list/watch pods` không cho đọc `pods/log`, `secrets` hay `pods/exec` theo ví dụ này. Nhưng **pod metadata cũng có thể nhạy cảm**; đánh giá cụ thể trước khi cấp quyền.

### 11.3. Những quyền dễ bị đánh giá thấp

| Quyền Kubernetes | Vì sao có thể nguy hiểm |
|---|---|
| `create pods`, `patch deployments` | Có thể chạy code dưới service account/host privileges nếu admission yếu |
| `get secrets` | Có thể lấy credentials/khóa và pivot |
| `create/patch rolebindings` | Có thể cấp quyền IAM/RBAC cho chủ thể khác |
| `pods/exec` | Có thể truy cập môi trường đang chạy, secrets và dữ liệu |
| `nodes/proxy`, kubelet APIs | Có thể truy cập API/agent ở node theo quyền cụ thể |
| `impersonate` | Có thể thực hiện thao tác nhân danh chủ thể khác theo phạm vi |
| `create tokenreviews` và access review APIs | Cần giới hạn theo mục đích; không đồng nghĩa quyền admin |

Không dùng danh sách này để suy mọi quyền đều dẫn đến toàn quyền. Rủi ro phụ thuộc **admission, PodSecurity, network policy, service account, cluster add-ons và namespace isolation**; cần đánh giá đường leo quyền cụ thể.

### 11.4. Chỉ đọc xác minh người đang có quyền nào

~~~bash
# Chỉ đọc trên cluster lab được phép.
kubectl config current-context
kubectl auth can-i --list -n ztna-lab
kubectl auth can-i get pods -n ztna-lab
kubectl auth can-i get secrets -n ztna-lab
kubectl get roles,rolebindings -n ztna-lab
~~~

`kubectl auth can-i` kiểm tra **quyền theo Kubernetes authorization** của identity hiện tại (và quyền được cluster cung cấp theo ngữ cảnh). Nó **không chứng minh** thiết bị đã compliant, MFA đã dùng, mạng không có bypass hoặc phiên được duyệt qua PAM. Những yếu tố này phải thu từ các lớp khác.

### 11.5. Service accounts và automation

Không phát một kubeconfig `cluster-admin` dùng vô hạn cho tất cả pipeline. Tách **CI identities theo repository/environment/action**, quyền chỉ đúng namespace/resource, token TTL/rotation phù hợp, tránh lưu kubeconfig trong image/artifact. Audit quyền `serviceAccountName`, workload identity và quyền đọc secrets.

## 12. Cloud management APIs và console

Cloud IAM và API quản trị thường **truy cập qua control plane công khai của provider** và không nhất thiết đi qua một private ZTNA gateway do tổ chức vận hành. Vì vậy một kiến trúc ZTNA đúng phải áp thêm **native identity/conditional access, PIM, organization guardrails và audit**.

### 12.1. Các lớp kiểm soát cần có

| Lớp | Mục tiêu | Ví dụ thực hành |
|---|---|---|
| **Federated identity** | Đăng nhập cloud bằng identity có lifecycle rõ | SSO, MFA chống phishing, short sessions |
| **Native IAM** | Cho phép đúng resource/actions | Scoped roles/policies, deny guardrails |
| **JIT activation** | Giảm đặc quyền thường trực | PIM/PAM workflow, approval, TTL |
| **Organization boundary** | Giới hạn những hành động không được phép dù role bị mở quá rộng | Org policies/SCP/management groups theo provider |
| **Resource/network security** | Ngăn public exposure/đường bypass | SG/NSG/firewall, private endpoints, audit |
| **Detection/audit** | Nhìn được quản trị API changes | Cloud audit logs, identity events, alerts |

### 12.2. Một ví dụ quyền “nhìn không đổi” chưa chắc an toàn

Người có quyền list VM instances có thể xem IPs/tags; người có quyền đọc snapshot hoặc Secret có thể lấy dữ liệu thực. Cần phân biệt **read-only metadata, read-only sensitive data và control-plane write actions**. Không tự cấp toàn bộ `*ReadOnlyAccess*` rồi kết luận không có rủi ro tiết lộ thông tin.

### 12.3. Những sự kiện phải giám sát đặc biệt

- Tạo/sửa service principals, access keys, trust relationships hoặc federation config.
- Gán owner/administrator role và mở rộng quyền ở organization/subscription/account/project.
- Tắt audit logs, thay retention, xóa immutable storage/backup policy.
- Thêm public IP/LB, mở security group/NSG `0.0.0.0/0` hoặc `::/0` cho admin ports.
- Sửa route để bypass firewall/egress inspection.
- Export/download secrets, KMS/PKI admin changes và snapshot sharing.

**Kết nối an toàn đến console không đủ** khi API credentials đã bị lộ. Tất cả **human và non-human API paths** phải nằm trong chính sách IAM/guardrails, không chỉ portal web.

## 13. Thiết bị mạng, hypervisor và hệ thống ngoài băng

Router, firewall, switch, VPN concentrator, wireless controller, hypervisor và **Baseboard Management Controller (BMC)** có khả năng làm thay đổi **luồng kết nối vật lý/ảo hóa** hoặc trạng thái boot của máy. Với tài sản này, **chỉ một thao tác sai** có thể ngắt quản trị từ xa hay mở đường vượt qua segmentation.

### 13.1. Management VLAN/VRF và out-of-band

~~~mermaid
flowchart TD
    PAW["PAW được quản lý"] --> PEP["Admin broker / PAM"]
    PEP -->|"Authenticated management path"| MGMT["Dedicated management VRF/VLAN"]
    MGMT --> R["Router / firewall admin"]
    MGMT --> H["Hypervisor admin"]
    MGMT --> BMC["BMC / IPMI / Redfish"]
    PUB["Guest / Internet"] -. "Denied direct admin network" .-> MGMT
    OPS["Emergency site access"] -. "Break-glass, audited" .-> BMC
~~~

Một vùng **out-of-band (OOB)** hỗ trợ quản trị khi hệ thống dữ liệu chính gặp lỗi, nhưng vẫn có thể là **một mạng rất nhạy cảm**. Tách OOB khỏi Internet và tenant networks; kiểm soát routing, ACL, firmware, TLS, default credentials, session logs và đường khôi phục.

### 13.2. Thiết bị cũ và giao thức quản trị yếu

Một số thiết bị chỉ hỗ trợ giao thức quản trị cũ, certificate validation hạn chế, hoặc không có MFA native. Có thể cần **secure jump gateway, console server, network isolation và maintenance procedures** làm compensating controls. Không vì thiết bị cũ mà mở Telnet/HTTP plaintext công khai; nếu không thể nâng cấp, giảm nguồn truy cập và lưu bằng chứng/rủi ro chấp nhận có thời hạn.

### 13.3. Tránh tự khóa khỏi thiết bị mạng

Thay ACL cho firewall đang kiểm soát chính đường ZTNA có thể **cắt luôn phiên quản trị và đường rollback**. Các thay đổi nguy hiểm phải có:

1. Kênh OOB/physical recovery được kiểm tra trước.
2. Candidate configuration và diff đã review.
3. Cơ chế **commit-confirmed/timed rollback** nếu thiết bị hỗ trợ.
4. Kiểm thử đường hợp lệ và đường bị cấm ngay sau thay đổi.
5. Người giám sát thứ hai hoặc approval khi thay Tier 0 network policy.

**Commit-confirmed không phổ quát** trên mọi vendor/firmware, nên không dựa vào cú pháp giả định.

## 14. PKI, secrets, DNS và backup: nơi đặc quyền có thể lan tỏa

### 14.1. Hạ tầng định danh và khóa

PKI CA, HSM/KMS, vault và certificate automation có thể cấp/truy cập **khóa dùng để xác thực hệ thống khác**. Một người có quyền export CA signing key hoặc cấp chứng thư arbitrary host có thể làm suy yếu mô hình identity của toàn mạng.

Kiểm soát đề xuất:

- Tách **CA administrator, certificate requester, certificate approver và key custodian**.
- Bảo vệ key bằng HSM/KMS hoặc cơ chế tương ứng theo threat model; hạn chế export.
- JIT role cho key policy changes, CA enrollment policies và trust bundle updates.
- Logging phát hành/revoke certificate và thay đổi trusted CA.
- Định kỳ kiểm tra **certificate templates, wildcard issuance và quyền đọc private keys**.
- Có key compromise/revocation runbook và khả năng phục hồi trust anchors.

**mTLS không thể giữ vững danh tính** nếu chính CA hoặc quy trình cấp identity đã bị chiếm quyền.

### 14.2. Quản trị DNS và tuyến mạng

Đổi DNS record cho `login.example.test` hoặc API nội bộ có thể làm người dùng truy cập endpoint khác. DNS admin là quyền có tác động **routing và trust**; cần role hẹp theo zone/record, change review, audit, DNSSEC khi phù hợp và monitoring các record nhạy cảm. DNSSEC xác thực dữ liệu DNS trong mô hình hỗ trợ, **không thay TLS certificate verification hoặc quyền sửa zone**.

### 14.3. Backup/DR và quyền xóa bằng chứng

Backup consoles có thể phục hồi, xuất hoặc xóa toàn bộ dữ liệu; tài khoản quản trị backup có thể phá kế hoạch khôi phục sau ransomware. Nên áp:

- Phân quyền **backup operator, restore operator, delete/retention administrator** rõ ràng.
- Immutable/offline/air-gapped copies theo khả năng, retention lock và bảo vệ quyền xóa.
- JIT + approval hai bên cho destructive operations theo mức rủi ro.
- MFA/PAW cho backup admin console, audit thay đổi và giám sát thất bại của backup jobs.
- Định kỳ **thử restore** bằng môi trường tách biệt, kiểm tra RPO/RTO.

**Một bản backup hiện hữu không có nghĩa khả năng khôi phục đã được chứng minh.** ZTNA phải bảo vệ cả **người có quyền phá hoặc làm lệch quá trình khôi phục**.

## 15. Machine identities và automation không có người ngồi trước màn hình

Không phải mọi hành động quản trị do con người đăng nhập qua browser. Terraform, GitOps, CI/CD, configuration management, security agents và scheduled jobs thường gọi control APIs bằng **workload identities**.

### 15.1. Nguy cơ với token lâu hạn

Một token CI có quyền `Administrator` không hết hạn có thể bị lấy từ repository secret, runner logs, máy build hoặc artifact. Nếu đường API cloud/Kubernetes nằm ngoài ZTNA broker cho người dùng, **token đó vẫn có quyền quản trị** dù mọi nhân viên đều bật MFA.

Mục tiêu:

- Dùng **workload identity federation hoặc short-lived credentials** khi provider hỗ trợ.
- Scope theo project/repository/workflow/environment/resource/action.
- Tách **plan/read** với **apply/write** và prod với staging.
- Không để untrusted pull request nhận production deploy credential.
- Bảo vệ runner/agent, artifact, outbound network và secret mounting.
- Gắn audit identity tới **job ID, commit/revision, actor, approval và target**.

### 15.2. Non-human identities cũng cần ZTNA principles

| Nguyên tắc | Áp dụng cho automation |
|---|---|
| Identity rõ | Service principal/workload identity riêng cho mỗi pipeline có quyền khác nhau |
| Least privilege | Chỉ actions/resource được duyệt, không cấp `*` vô hạn |
| Temporal access | Token ngắn hạn, rotation/revocation |
| Context | Workflow/environment/branch/runner attestation khi được hỗ trợ |
| Policy enforcement | IAM/admission/API policies, không dựa VPN-only |
| Audit | Provenance của API calls, build/job ID và change approval |
| Recovery | Thu hồi token, rotate key, pipeline rollback, forensic evidence |

### 15.3. Không dùng human session để chạy automation

Một pipeline không nên giữ refresh token hoặc browser cookie của quản trị viên cá nhân. Nếu nhân viên rời tổ chức hoặc tài khoản bị khóa, pipeline mất ổn định; còn nếu token bị lộ, khó phân biệt hoạt động máy với con người. Sử dụng **machine identity riêng** và có lifecycle owner.

### 15.4. Token relay và identity federation

Federation có thể xác nhận workload identity từ CI provider, Kubernetes ServiceAccount hoặc identity provider khác. Nhưng phải xác minh **issuer, audience, subject restrictions, token lifetime và trust configuration**; chỉ tin mọi token từ một issuer rộng có thể cấp quyền cho các repository/workflows không được phê duyệt.

## 16. Session monitoring, audit trail và bảo vệ riêng tư

Một hệ thống quản trị an toàn cần **quan sát được quyền đã cấp và hành động đã làm**, không chỉ ghi nhận “login success”.

### 16.1. Bộ dữ liệu theo phiên

~~~yaml
# Mẫu record tổng hợp minh họa; không phải schema của một sản phẩm.
session_id: pam-lab-session-0001
time_start_utc: "2026-11-28T06:00:00Z"
human_identity: admin-lab-01
identity_assurance: phishing-resistant-mfa
device_id: paw-lab-03
device_posture: compliant-at-decision-time
resource_id: prod-linux-admin-lab
resource_protocol: ssh
granted_role: diagnostics-read-only
approval_ref: CHG-LAB-015
grant_ttl_minutes: 15
policy_revision: admin-access-v12
decision: allow
session_end_reason: pending
artifact_links:
  - restricted-session-audit-reference
~~~

Các giá trị ở trên là **giả lập**. Những trường như `device_posture` cần **timestamp, nguồn và TTL freshness**, không chỉ một chuỗi compliant do client tự khai. Không nhúng passwords, token, MFA seed, clipboard chứa dữ liệu khách hàng vào log.

### 16.2. Ba luồng log phải liên kết

| Nguồn | Thông tin chính | Điều chưa chứng minh riêng lẻ |
|---|---|---|
| **IdP/MFA** | Ai đã đăng nhập, factor/phương thức, sự kiện rủi ro | Quyền nào được thực thi tại target |
| **ZTNA/PAM/PEP** | Quyết định, tài nguyên, phiên, TTL, approval, device | Lệnh thực tế trên OS nếu không có target logs |
| **Target/cloud API** | SSH commands/sudo, Windows events, Kubernetes audit, cloud control-plane changes | Người dùng con người nếu chỉ ghi một shared service account |

Correlate bằng **session ID, trace/request ID, target resource, actor identity và UTC timestamps**. Nếu dùng một shared local admin account trên target, broker cần giữ ánh xạ có kiểm toán từ **human identity → issued/checked-out credential → target session**, đồng thời hướng tới tài khoản cá nhân khi có thể.

### 16.3. Ghi hình phiên có lợi ích và giới hạn

Session recording giúp điều tra hoạt động tương tác qua SSH/RDP khi được pháp luật/chính sách cho phép, nhưng không bảo đảm bắt được **mọi tác vụ background, API call từ token hoặc dữ liệu qua đường bypass**. Bản ghi có thể chứa secrets và dữ liệu nhạy cảm, nên phải được mã hóa, phân quyền, lưu theo retention và bảo vệ khỏi sửa/xóa.

### 16.4. Cảnh báo sự kiện rủi ro cao

- JIT admin activation trái thời gian làm việc hoặc không có ticket phù hợp.
- Đăng ký mới MFA factor/security key cho tài khoản Tier 0.
- Đăng nhập admin từ thiết bị chưa quản lý hoặc posture thay đổi giữa phiên.
- Tạo API key/role vượt phạm vi, sửa federation hoặc tắt logging.
- Phiên SSH/RDP cấp cao kéo dài ngoài TTL hoặc sử dụng port forwarding bất thường.
- Sửa firewall/VPN/route/IdP/PKI để mở đường quản trị ngoài policy.
- Truy cập BMC/OOB từ mạng không thuộc danh sách nguồn được duyệt.
- Thay backup retention/immutable settings hoặc xóa recovery points.

**Không tự phán đoán malicious chỉ từ một tín hiệu đơn lẻ** như địa lý IP hay giờ truy cập. Kết hợp context, change approval và telemetry của chính tài nguyên.

## 17. Break-glass và đường khôi phục khi IdP/ZTNA gặp sự cố

Đối với management plane, **chính sách từ chối mọi người không có đường cứu hộ** có thể dẫn tới mất khả năng khắc phục sự cố, kể cả khi nguyên nhân chỉ là lỗi IdP/DNS/CA hoặc policy deploy sai. Một thiết kế Zero Trust trưởng thành cần **break-glass có giám sát**.

### 17.1. Đặc điểm tài khoản khẩn cấp an toàn hơn

- Chỉ sử dụng để **khôi phục hệ thống**, không dùng cho công việc hằng ngày.
- Số lượng tối thiểu; có owner, người giám sát và quy trình activation rõ.
- Credentials được bảo vệ bằng vault/HSM/offline secure handling theo nguy cơ; tránh password chung dán trên wiki.
- **Tách phụ thuộc** khỏi đúng hệ thống đang cần phục hồi ở mức khả thi; ví dụ nếu IdP down, không để mọi đường cứu hộ đều yêu cầu IdP đó.
- Nếu không thể áp dụng MFA giống tài khoản thường trong một sự cố, phải có **compensating controls** như custody, multi-person approval, restricted source, session recording và immediate alerts.
- Sau dùng: rotate/reseal credentials, review actions, xác minh không tạo persistence, ghi post-incident report.

### 17.2. Break-glass không đồng nghĩa permanent bypass

~~~mermaid
flowchart TD
    OUT["Sự cố mất IdP/ZTNA hoặc mất liên lạc"] --> ACT["Kích hoạt quy trình khẩn cấp được duyệt"]
    ACT --> VALID["Xác minh danh tính/custody ngoài đường lỗi"]
    VALID --> OOB["Mở đúng OOB/console recovery path"]
    OOB --> FIX["Khôi phục policy, mạng hoặc identity"]
    FIX --> CLOSE["Đóng emergency access + rotate"]
    CLOSE --> AUDIT["Independent audit/post-incident review"]
~~~

Nếu một tài khoản break-glass luôn có thể đăng nhập cloud/SSH từ Internet mà không có monitoring và có credential dài hạn dễ lấy, đó là **đường tấn công thường trực**, không phải giải pháp tin cậy.

### 17.3. Diễn tập recovery là bắt buộc

Thử ở môi trường được phê duyệt:

- IdP và ZTNA broker unavailable;
- MFA enrollment/service bị gián đoạn;
- Firewall ACL mới vô tình chặn broker;
- Cloud IAM policy bị deploy sai;
- Certificate CA/trust bundle hết hạn hoặc thay đổi lỗi;
- Thiết bị mạng cần OOB khi data-plane connectivity không hoạt động.

**Test kết quả khôi phục và đóng đường cứu hộ**; không chỉ xác nhận “có mật khẩu khẩn cấp trong vault”. Các diễn tập nên tránh làm mất tính sẵn sàng production khi chưa có phương án an toàn.

## 18. Threat modeling cho đường quản trị

Tài nguyên quản trị thường có **blast radius lớn** vì một account/console có thể thay đổi mạng, IAM, backup hoặc logging. Threat model phải kiểm tra cả **con người, máy quản trị, credential, kết nối, PEP và API path**.

### 18.1. Ma trận tài sản, rủi ro, phòng vệ

| Tài sản/rủi ro | Con đường tấn công khả dĩ | Kiểm soát chính | Evidence |
|---|---|---|---|
| **Cloud global admin** bị phishing | Trang SSO giả, session/token theft | Phishing-resistant MFA, conditional access, JIT, token limits | IdP events, role activation logs |
| **SSH server** lộ Internet | Public IP + SG/firewall mở | Private route/PEP, host key verification, short-lived SSH certs | Effective routes, public exposure, SSH audit |
| **RDP jump host** bị lạm dụng | Shared credentials, clipboard/drive redirection | Broker, PAW, managed local admin, restriction, recording | PAM session + Windows events |
| **Kubernetes API** bị takeover | Leaked kubeconfig, broad RBAC, public API | Federated identity, network restrictions, RBAC/admission, audit | API audit, `can-i`, control endpoint settings |
| **Firewall admin** bị chiếm | Weak device password/legacy management | OOB network, MFA broker, least privilege, config review | Config diff, admin logs, OOB ACL |
| **BMC/hypervisor** trực tiếp từ user LAN | Management VLAN/VRF không cách ly | Dedicated management network + PEP, firmware hardening | Reachability tests, route/ACL |
| **PKI signing key** bị export | CA admin scope rộng hoặc vault IAM yếu | Key custody, HSM, role separation, audit | CA/KMS access events |
| **Backup bị xóa** | Backup admin role thường trực | Immutable retention, JIT destructive approval | Retention policy, delete events |
| **CI/CD service principal** bị lộ | Long-lived token, untrusted PR runner | Federation, workflow-scoped identity, no prod secrets in forks | Pipeline audit, IAM trust conditions |
| **ZTNA connector/PEP** bị bypass | NIC/NodePort/alternate route ngoài broker | Network allowlist, route coverage, target RBAC | Negative direct-path tests |
| **Quyền ở target** rộng hơn ticket | SSH login role có sudo root hoặc cloud IAM wildcard | JEA/sudo restrictions, native IAM least privilege | Permission test, command/API audit |
| **Thiết bị mất compliance giữa phiên** | Stale posture, active session tồn tại | Re-evaluation, session TTL/revocation, EDR response | Posture timeline, session termination test |
| **Break-glass bị lạm dụng** | Credential luôn mở, ít audit | Custody, dual control, limited source/alert | Emergency activation records |
| **DNS/IdP outage** khóa đội vận hành | Phụ thuộc duy nhất vào SSO/broker | OOB recovery, redundancy, rehearsed runbook | Recovery exercise, RTO |
| **Cross-site DR** nới lỏng policy | Backup site không áp cùng firewall/IAM | Policy-as-code, multi-site regression tests | Effective controls mỗi site |

### 18.2. Sơ đồ đường tấn công và các chốt chặn

~~~mermaid
flowchart TD
    ATT["Attacker / compromised endpoint"] --> CRED["Credential hoặc session bị chiếm"]
    CRED --> MFA{"Phishing-resistant auth / active session policy"}
    MFA -- "Deny" --> STOP["Không mở phiên mới"]
    MFA -- "Pass hoặc session đã có" --> PEP{"PEP + posture + JIT"}
    PEP -- "Deny" --> STOP
    PEP -- "Permit specific target" --> TGT["Management endpoint"]
    ALT["Direct network path nếu tồn tại"] -. "Bypass PEP" .-> TGT
    TGT --> AUTH{"Native target authorization"}
    AUTH -- "Deny" --> STOP
    AUTH -- "Allow action" --> CTRL["Control-plane change"]
    CTRL --> LOG["Audit + detection + rollback"]
~~~

Rủi ro không biến mất khi một chốt kiểm soát hoạt động: session đã cấp có thể bị chiếm, quyền target có thể sai hoặc một đường mạng khác có thể bypass. Do đó nên đánh giá **phòng vệ theo chuỗi** và kiểm thử từng lối vào.

### 18.3. Đánh giá theo khả năng tác động

Khi ưu tiên triển khai, cân nhắc:

- **Impact:** quyền sửa IAM/PKI/router/backup có thể ảnh hưởng bao nhiêu tài sản?
- **Exposure:** management endpoint có public listener, VPN-only, private PEP hay OOB?
- **Credential lifetime:** session/bearer token/SSH key có thể dùng bao lâu?
- **Lateral path:** một máy bị chiếm có gọi tiếp management plane khác không?
- **Detectability:** có logs/response owners và rollback không?
- **Recoverability:** mất IdP/PEP thì tổ chức phục hồi ra sao?

Không dùng một điểm số tổng hợp duy nhất để bỏ qua một rủi ro nghiêm trọng như **CA key export không được kiểm toán** hoặc **Tier 0 console public**.

## 19. Quan sát cấu hình bằng lệnh chỉ đọc

Các lệnh sau chỉ phục vụ **thiết bị/cluster/account lab được quản lý hoặc được phép kiểm tra**. Không quét các IP hoặc dải port bên ngoài. Các API read operations có thể trả dữ liệu nhạy cảm; hạn chế quyền và redaction khi chia sẻ evidence.

### 19.1. Kiểm tra listener và route trên Linux lab

~~~bash
# Chạy trên Linux server/lab được cấp quyền.
# Các lệnh chỉ xem cấu hình mạng/socket, không sửa firewall.
ip -br address
ip route show
ip -6 route show
ss -lnt

# Xem process/bind port có thể cần quyền quản trị và phải được cho phép.
sudo ss -lntp
~~~

Nếu SSH lắng nghe `0.0.0.0:22` hoặc `[::]:22`, đó là **bind trên các interfaces của host**, chưa đủ kết luận Internet có thể kết nối. Cần xem **public IP, cloud route, SG/NSG/host firewall và đường tới target**.

### 19.2. Quan sát cấu hình SSH mà không thay đổi trạng thái

~~~bash
# Trên lab host có OpenSSH server và được quyền quan sát.
sudo sshd -T

# Xem fingerprint public host key theo đường file của host lab.
# Ví dụ này có thể cần quyền đọc; KHÔNG xuất private host key.
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
~~~

`sshd -T` hiển thị effective configuration tổng quát; những rule `Match` có thể phụ thuộc user/host/source và tham số `-C` của phiên bản OpenSSH. Không dùng một output làm bằng chứng mọi account có cùng chính sách. **Không xuất `/etc/ssh/ssh_host_*_key` private keys** vào ticket hoặc log.

### 19.3. Kiểm tra khả năng của identity Kubernetes

~~~bash
# Chỉ đọc trên Kubernetes cluster lab.
kubectl config current-context
kubectl auth can-i --list -n ztna-lab
kubectl auth can-i get pods -n ztna-lab
kubectl auth can-i create deployments -n ztna-lab
kubectl auth can-i get secrets -n ztna-lab
kubectl get rolebindings,roles -n ztna-lab
~~~

Đọc kết quả `kubectl auth can-i` **không nên thay cho kiểm tra actual API endpoint exposure, MFA, session source, admission controls hoặc impersonation rights**. Một account không thể đọc Secrets trực tiếp vẫn có thể có quyền deploy một Pod với khả năng đọc dữ liệu nếu admission và service account controls yếu.

### 19.4. Kiểm tra một SSH endpoint được phê duyệt

~~~bash
# Chỉ thử trên một host lab đã được cấp quyền.
# Không nhập mật khẩu trên host không được xác minh.
ssh -o BatchMode=yes \
    -o ConnectTimeout=5 \
    -o StrictHostKeyChecking=yes \
    admin-readonly@ssh.lab.example.test "id"
~~~

Lệnh mở một SSH session thật để thực hiện `id`, nên **không thuộc nhóm chỉ đọc về mạng thuần túy**, dù command trên target chỉ truy vấn identity. Nó có thể thất bại do thiếu key hoặc known_hosts; **không tắt host key checking để làm test vượt qua**. Nếu lab chưa thiết lập DNS/account/key được phê duyệt, chỉ dùng dữ liệu cấu hình và reachability analysis.

### 19.5. Read-only inventory của cloud management surfaces

Trên cloud, không có một lệnh chung portable cho AWS/Azure/GCP. Để đánh giá bằng API có quyền, cần thu:

~~~text
Cloud account/project/subscription scope
Human admin identities and group memberships
High-privilege roles and standing assignments
MFA/conditional-access status where available
Public API endpoints and IP allowlists
Public IP/host listeners for SSH/RDP/admin panels
Service principals and access key age/rotation state
Organization guardrail policies
Cloud audit logs, retention and alerting status
Emergency users and recovery paths (metadata only)
~~~

Không trích nguyên **access keys, client secrets, refresh tokens hoặc private key material** để “chứng minh đã kiểm toán”. Dùng metadata/credential identifiers, age/owner và audit events.

### 19.6. Không chạy network scanners bừa bãi

Khi muốn chứng minh “SSH/RDP không phơi Internet”, **inventory + effective route/firewall analysis** là bằng chứng nền tảng. Một phép kết nối giới hạn từ nguồn Internet test do tổ chức sở hữu có thể bổ sung, nhưng không chạy scan hàng loạt lên public IP hoặc đối tác khi chưa được phê duyệt. Không coi một timeout là bằng chứng tuyệt đối do target có thể tắt hoặc kiểm tra sai đường.

## 20. Ma trận kiểm thử bảo vệ tài nguyên quản trị

Mỗi test cần ghi **source identity, device identity, resource, protocol/action, conditions, enforcement point và expected result**. Đặc biệt với test DENY, phải có **positive control** và evidence từ đúng lớp thay vì chỉ quan sát timeout.

| Test ID | Chính sách cần chứng minh | Cách thử trong lab được phép | PASS khi |
|---|---|---|---|
| **INV-01** | Inventory đầy đủ management entry points | So cloud, SSH/RDP, OOB, K8s, network device inventory | Không có endpoint ngoài owner/policy |
| **INV-02** | Không có public management port ngoài phê duyệt | Effective route, NIC, listener, firewall review | Không có Internet direct path sai policy |
| **ID-01** | Người quản trị được xác thực danh tính riêng | IdP log và login flow lab | Phân biệt từng human actor |
| **ID-02** | MFA chống phishing được dùng ở Tier 0 | Verify IdP authentication method từ sự kiện test | Factor/method thỏa policy |
| **ID-03** | Account đã thu hồi không đăng nhập mới | Test disabled lab identity | Không có session mới |
| **DEV-01** | Thiết bị chưa quản lý không vào admin app | Request từ unmanaged test device | PDP/PEP từ chối |
| **DEV-02** | Posture không đạt ngăn mở phiên | Simulate noncompliance được phê duyệt | PEP deny hoặc remediation route |
| **DEV-03** | Posture degrade trong phiên được xử lý | Diễn tập TTL/recheck trong lab | Re-evaluate/revoke theo capability và policy |
| **JIT-01** | Không có standing admin access | Kiểm tra entitlement trước activation | Không thực hiện admin actions |
| **JIT-02** | JIT quyền đúng target/action | Activate role có approval và test | Chỉ đúng resource/action được phép |
| **JIT-03** | Quyền hết hạn được thu hồi | Test sau TTL theo phiên lab | Không cấp phiên mới; existing session theo policy |
| **JIT-04** | Tách người yêu cầu và người duyệt | Review approval workflow | Không tự duyệt trường hợp yêu cầu dual control |
| **SSH-01** | Không có direct-to-SSH bypass | Test network path ngoài broker có phép | Bị chặn tại network control |
| **SSH-02** | SSH host identity được xác minh | Kiểm tra host key fingerprint/cert | Không bỏ qua host key verification |
| **SSH-03** | Role quản trị OS có phạm vi giới hạn | Test approved read-only command | Không có `sudo`/shell quyền vượt role |
| **SSH-04** | Port/agent forwarding không vượt scope | Review policy và controlled lab tunnel behavior | Không tạo đường lateral ngoài approval |
| **RDP-01** | Direct RDP public bị chặn | Review LB/firewall/source test | Chỉ broker/đường được duyệt |
| **RDP-02** | RDP session data redirection đúng policy | Test clipboard/drive theo môi trường test | Không copy tài liệu nhạy cảm sai quyền |
| **K8S-01** | Kubernetes admin API chỉ có authorized identities | RBAC + endpoint exposure review | Unapproved actor bị deny |
| **K8S-02** | Không dùng cluster-admin ngoài nhu cầu | `kubectl auth can-i` và role audit | Namespace-admin không leo quyền |
| **CLOUD-01** | Cloud IAM admin actions cần điều kiện | Test lab role activation/missing MFA | Unapproved action bị native IAM từ chối |
| **CLOUD-02** | Nonhuman token không có wildcard write | Audit service principal trust/action scope | Chỉ pipeline và resource được duyệt |
| **NET-01** | Firewall/network device admin path chỉ từ broker | Review ACL/VRF/source tests | Guest/VPN không tự tới console |
| **OOB-01** | OOB recovery không public ngoài quyền | Network inventory/ACL test | BMC/console không reachable từ Internet |
| **PKI-01** | CA/KMS key operations cần quyền tách biệt | Role/audit review, test non-export | Unapproved principal không export/change key |
| **BKP-01** | Destructive backup operations có bảo vệ | Test policy trên backup lab | Không xóa/đổi retention không đủ approval |
| **BYPASS-01** | Alternate NIC/IPv6 không vượt PEP | IPv4/IPv6 effective path review | Không có secondary entry point ngoài policy |
| **BYPASS-02** | VPN không mở full management CIDR | VPN routes/ACL + negative test | Chỉ designated assets/ports |
| **BYPASS-03** | Jump host không tạo unrestricted pivot | Egress policy/route inspection | Không proxy tiếp tới mọi privileged assets |
| **AUD-01** | Session gắn với người thật | IdP→PAM→target events correlation | Actor/session/target/action truy vết |
| **AUD-02** | Log không thể bị user admin dễ dàng xóa | Separation/storage/immutability review | Audit controls hoạt động |
| **BRK-01** | Break-glass dùng được khi IdP lỗi | Recovery simulation có quyền | Khôi phục đúng RTO |
| **BRK-02** | Emergency credential được đóng sau dùng | Review rotation/alerts/ticket | Không còn phiên/quyền khẩn cấp thừa |
| **DR-01** | Failover không mở management path | So chính sách primary/DR và test | Deny/allow parity, không tự public |

### 20.1. Kết quả PASS / FAIL / INCONCLUSIVE

- **PASS:** chứng minh *request hợp lệ được xử lý đúng* và *request không hợp lệ bị chính sách dự định từ chối*, cùng resource/actor/policy revision, trạng thái device và evidence.
- **FAIL:** có một đường quản trị trái phép thành công, privileged role được cấp vượt scope/TTL hoặc không có bằng chứng đáng tin về identity.
- **INCONCLUSIVE:** target tắt, DNS lỗi, sai địa chỉ/source, không có logs, device/posture chưa được xác minh, hoặc test bị firewall chặn **trước điểm PEP mà bài test muốn đánh giá**.

**Ví dụ:** SSH timeout từ Internet không đủ kết luận “ZTNA policy hoạt động”. Nếu firewalld đã drop traffic trước broker hoặc server không chạy, phép thử không chứng minh việc **ZTNA PEP từ chối một người dùng không có quyền**. Cần một test khác tại đúng PEP.

### 20.2. Mẫu bằng chứng cho một phép thử

~~~yaml
test_id: JIT-SSH-DENY-LAB-01
environment: authorized-isolated-lab
time_utc: pending
identity: admin-lab-unapproved
device: managed-lab-workstation
target: prod-linux-admin-lab
protocol: ssh
requested_role: privileged-shell
requested_duration_minutes: 15
expected:
  no_standing_privilege: true
  without_approval: deny
  direct_network_path: deny
  target_os_privilege: not_granted
positive_control:
  identity: approved-lab-admin
  resource: same-lab-host
  action: allowed-read-only-command
  expected: allow
evidence:
  - idp-mfa-method-and-device-posture
  - jit-policy-and-decision
  - pep-session-result
  - target-authentication-log
  - network-direct-path-check
result: pending-execution
~~~

Không ghi password, bearer token, MFA seed, private key hoặc bản ghi dữ liệu khách hàng trong hồ sơ test. Đây là **mẫu dự kiến**, không phải bằng chứng thực thi.

## 21. Case study 1 — VPN hợp lệ nhưng quản trị firewall bị lạm dụng

### 21.1. Bối cảnh giả định

Một doanh nghiệp cho đội kỹ thuật kết nối VPN để hỗ trợ từ xa. Người dùng có MFA VPN; sau khi vào tunnel, firewall cho phép các client trong VPN subnet tới toàn bộ **management VLAN** trên SSH, HTTPS và RDP. Một kỹ sư dùng chung local admin account của firewall và một hệ thống monitoring.

Trong diễn tập được cấp phép, một laptop quản trị bị coi là không đáng tin cậy (posture fail) vẫn có thể đi qua VPN đến giao diện quản lý firewall vì **chính sách VPN chỉ xác minh tại kết nối tunnel**, còn đường management chưa có broker/resource-level policy.

**Tình huống giả định này không khẳng định VPN/MFA luôn yếu.** Điểm sai là **scope route và quyền sau khi VPN kết nối** không đủ hẹp.

### 21.2. Con đường rủi ro

~~~mermaid
flowchart LR
    LAP["Laptop đã có VPN"] --> VPN["VPN authenticated"]
    VPN --> CIDR["Full management subnet route"]
    CIDR --> FW["Firewall admin UI"]
    CIDR --> BMC["BMC console"]
    CIDR --> SSH["Linux admin SSH"]
    PAM["No resource JIT/target audit"] -. "Management gap" .-> CIDR
~~~

### 21.3. Sai lệch và lớp bảo vệ cần bổ sung

| Sai lệch | Tác động | Biện pháp |
|---|---|---|
| VPN client có route tới cả VLAN | Mở lateral movement tới nhiều assets | ACL từ đúng broker tới đúng target |
| User có quyền admin thường trực | Tài khoản bị chiếm có thể sửa config | JIT role + approval và timeout |
| Local account dùng chung | Không truy vết được actor thực | Personal identities hoặc PAM credential mapping |
| Không kiểm tra device posture | Thiết bị nguy cơ cao vẫn dùng quyền | Managed PAW + conditional access |
| Không có log tại thiết bị | Khó kiểm tra thay đổi policy | Device config audit, central logs, session ID |
| BMC chung VLAN với SSH | Một client VPN có thể gọi console thấp hơn OS | Dedicated OOB segmentation |

### 21.4. Phương án thay đổi

1. Inventory toàn bộ assets trên management VLAN, các đường truy cập cloud/VPN/peering và users.
2. Phân loại Tier 0/1/2, tách VLAN/VRF/OOB theo rủi ro.
3. Thiết lập resource-specific PEP/broker và native endpoint RBAC.
4. Chuyển khỏi shared local admin khi có thể, dùng PIM/PAM và MFA/PAW.
5. Giới hạn firewall: chỉ designated broker source tới target ports, không để VPN user subnet gọi trực tiếp.
6. Đảm bảo console recovery ngoài đường đang bị thay đổi, có rollback.
7. Canary cho một nhóm admins/thiết bị, đo operational latency/SLO và test các luồng bị cấm.
8. Thu hồi quyền cũ, tắt direct routes còn thừa, theo dõi session/ACL logs.

### 21.5. Before/after matrix

| Luồng | Trước (giả định) | Sau (mục tiêu cần kiểm chứng) |
|---|---|---|
| Approved PAW → broker → firewall admin | Có thể truy cập | ALLOW với MFA + JIT + audit |
| User VPN → firewall admin direct | Có thể truy cập | DENY |
| Unmanaged laptop → broker | Có thể không được xét posture | DENY/remediation |
| Approved user → BMC ngoài scope | Có thể truy cập | DENY |
| Emergency OOB recovery | Chưa được kiểm thử | AVAILABLE với break-glass controls |

**Bài học:** tunnel authentication là một lớp quan trọng nhưng **không tự phân quyền mọi tài nguyên sau tunnel**. ZTNA bảo vệ management plane khi có **enforcement tại từng tài nguyên và đóng các tuyến bypass**.

## 22. Case study 2 — Con người bị khóa, pipeline vẫn có cloud admin token

### 22.1. Bối cảnh giả định

Một nhóm cloud đã triển khai phishing-resistant MFA, PAW và JIT approval cho **đăng nhập console bằng người dùng**. Tuy nhiên deployment pipeline vẫn giữ một service principal token dài hạn, cho phép sửa cloud IAM và security groups. Pipeline được cấu hình để mọi job từ một repository có quyền truy cập secret này, kể cả những nhánh chưa được review.

Một contributor không có cloud admin entitlement có thể đưa một thay đổi hạ tầng vào quy trình CI trong lab; runner sẽ dùng **machine credential có quyền quá rộng** để gọi API. Dù họ không hề đăng nhập cloud console và không có phishing-resistant MFA của admin, **control plane vẫn nhận request được ký bằng machine credential**.

> Đây là một kịch bản để phân tích trust boundary, không phải hướng dẫn khai thác CI hay vượt cơ chế xác thực. Không thử trên repository hoặc cloud account không được cấp quyền.

### 22.2. Đường quyền bị bỏ sót

~~~mermaid
flowchart LR
    USER["Human admins"] --> MFA["SSO/FIDO2 + PAW"]
    MFA --> PIM["JIT cloud role"]
    PIM --> API["Cloud management API"]
    PR["Unreviewed pipeline input"] -. "Vào CI job" .-> CI["Build/deploy runner"]
    CI -->|"Standing privileged machine token"| API
    GUARD["Missing workflow/branch/environment restrictions"] -. "Authorization gap" .-> CI
~~~

### 22.3. Root cause

| Lớp | Cấu hình đúng mong muốn | Lỗi giả định |
|---|---|---|
| Identity | Human và machine identities tách biệt, lifecycle rõ | Pipeline dùng quyền admin không giới hạn |
| Authentication | Token federation theo job và context | Long-lived static client secret |
| Authorization | Role chỉ đúng resources/actions | Có quyền IAM + network admin quá rộng |
| CI trust | Protected branches, review, environment approval | Unreviewed workflow có thể gọi prod |
| Network | API path và resource guardrails | Public cloud API chỉ tin credential, không có guardrail |
| Audit | Repo/commit/job/actor/approval correlation | Chỉ ghi service principal chung |

### 22.4. Thiết kế cải thiện

1. Phân loại jobs: **lint/plan/read-only** khác **production apply**.
2. Dùng **short-lived federated workload identity** có restrictions theo repository, branch/tag/workflow/environment và audience khi provider hỗ trợ.
3. Chỉ những protected deployment environments đã có approval mới được assume production role.
4. Scope IAM theo resource/action; tách quyền đọc, deploy, IAM administration và security policy changes.
5. Dùng organization-wide guardrails để ngăn việc tắt audit logs hoặc mở admin ports sai policy.
6. Bảo vệ runner/container, không tiết lộ tokens trong logs/artifacts hoặc cache không đáng tin.
7. Liên kết cloud audit event với **CI job, commit, reviewer và change ID**.
8. Thu hồi long-lived token, theo dõi các lần dùng cũ và chạy regression tests.

### 22.5. Expected test evidence

~~~yaml
case: pipeline-control-plane-privilege-lab
expected:
  unreviewed_branch_can_assume_prod_admin: false
  plan_job_has_write_iam_permission: false
  approved_deploy_job_has_scoped_role: true
  token_lifetime: short-lived-per-workflow
  audit_has_actor_job_and_revision: true
  manual_cloud_admin_requires_jit_and_mfa: true
  emergency_rollback_available: true
result: pending-execution
~~~

**Bài học:** nếu ZTNA chỉ kiểm soát **con người vào console** mà bỏ **máy tự động gọi API**, một đường quản trị quyền cao vẫn còn. Zero Trust phải áp dụng cho cả **human và non-human access**.

## 23. Troubleshooting và ứng phó sự cố liên quan quản trị

### 23.1. Những triệu chứng thường gặp

| Triệu chứng | Giả thuyết | Kiểm tra có kiểm soát |
|---|---|---|
| IdP cho đăng nhập nhưng PEP deny | Role/JIT/approval/device không đạt | PDP decision ID, TTL, posture, target |
| MFA thành công nhưng SSH không vào | Host key, credential mapping, host firewall, target auth | IdP/PEP log, SSH auth log, route |
| VPN vào được nhưng ZTNA không mở target | VPN connectivity khác resource authorization | PEP policy/entitlement, path và app health |
| SSH hoạt động từ Internet ngoài broker | Secondary NIC, firewall mở, public IPv6, route bypass | Public IP/route/firewall + approved negative test |
| RDP thành công nhưng local admin bị từ chối | Windows group/role/JEA/LAPS policy | Target OS authorization events |
| Kubernetes API 403 | Native RBAC/admission hoặc token scope thiếu | `kubectl auth can-i`, K8s audit |
| Cloud API AccessDenied | IAM explicit deny, missing role, MFA/conditions, scope | Identity and audit event policy result |
| Cấp JIT nhưng target vẫn deny | Delay propagation, role mismatch, cached session | Activation timestamp, native target entitlements |
| Hết TTL nhưng phiên vẫn dùng được | Session không bị terminate, local credential còn tồn tại | PEP termination capabilities và target logs |
| PAW bị đánh dấu không compliant | EDR offline, MDM stale, OS baseline, certificate | Device signal freshness/owner |
| Người dùng mới được reset MFA nhưng không vào được | Policy factor attestation/registration chưa hoàn tất | IdP authentication methods, activation ticket |
| Broker outage làm admin mất quyền | Không có HA, dependency DNS/IdP/PKI lỗi | Broker health, runbook, approved break-glass |
| OOB console không truy cập được | Management VRF/ACL/power/vendor console lỗi | OOB route, physical recovery test |
| Tài khoản khẩn cấp vào được từ mọi nơi | Emergency path quá rộng | Firewall source restrictions, audit/rotation |
| Admin actions không có người thật trong log | Shared account/service principal, thiếu correlation | PAM session mapping, cloud audit |
| SSH key/cert hết hạn | TTL đúng nhưng rotation thất bại | CA cert issuance, trust and clock sync |
| Công cụ agent tự ngắt sau thay route | Traffic đi qua firewall/PEP đang thay đổi | Session path, rollback route, OOB |
| Một số assets không hiện trong ZTNA portal | Inventory/connector enrollment hoặc class sai | Target inventory vs route/LB metadata |
| DR site cho quản trị viên bypass MFA | Khác IdP, emergency fallback hoặc policy drift | DR access policies, source tests |
| Pipeline thay firewall nhưng human admin không có quyền | Machine identity có role khác | CI federation/IAM scope, job audit |
| Session recording không thấy thao tác | Không đi qua broker, recording chưa bật hoặc API actions | Effective session path và audit logging |
| Truy cập đã bị chặn nhưng vẫn có cloud API calls | Long-lived tokens/session reuse/nonhuman path | Token/role inventory và API audit events |

### 23.2. Trình tự chẩn đoán một request quản trị

1. **Ai?** Human identity hay machine workload? IdP issuer, role, group và session ID nào?
2. **Từ đâu?** Thiết bị nào, posture gần nhất, nguồn mạng và thời gian UTC?
3. **Tới đâu?** Resource ID, management interface, protocol, action và sensitivity tier?
4. **Quyền?** Standing entitlement, JIT activation, approval, effective target IAM/RBAC?
5. **Đường mạng?** DNS, private/public address, route, firewall, VPN/PEP và IPv6 path?
6. **Xác thực kênh?** TLS certificate, SSH host key, device/agent trust, JWT/session token?
7. **PEP có xử lý request không?** Có session/decision log hay traffic đi vòng?
8. **Target có cho phép không?** SSH/RDP/OS/Cloud/Kubernetes API authorization logs?
9. **Tình trạng phiên?** TTL, active sessions, revocation propagation, reused credentials?
10. **Khôi phục và xác nhận:** đúng runbook, test luồng ALLOW và DENY, log evidence và rollback.

### 23.3. Không mở quyền rộng để giải quyết một lỗi

Nếu người quản trị không vào được target, **không tự thêm `0.0.0.0/0` vào firewall, bật password login, tắt MFA, cấp cluster-admin hoặc lưu một API key không hết hạn** chỉ để khôi phục nhanh. Dùng đường khôi phục được duyệt và điều tra đúng lớp:

- DNS resolution thất bại khác policy deny.
- TLS/SSH host key mismatch khác JIT authorization deny.
- PEP allow nhưng native IAM deny khác CNI/firewall drop.
- Network timeout không chứng minh MFA/identity policy đã quyết định.
- Cloud API 403 không chắc do ZTNA gateway; có thể do IAM guardrail.

### 23.4. Nếu nghi ngờ phiên quản trị bị chiếm

Ưu tiên theo incident response runbook và quyền được giao:

1. Thu giữ **IdP/PAM/PEP/target/cloud audit events** có liên quan, đồng bộ timestamp.
2. Xác định identity, device, sessions, access keys và resources có thể bị ảnh hưởng.
3. **Ngăn mở phiên mới** và thu hồi những credentials/roles nghi vấn theo chính sách.
4. Đánh giá **các phiên đã mở** có cần terminate tại target không; token/key có còn hiệu lực?
5. Kiểm tra IAM grants, persistence, firewall/route changes, PKI/Secrets và backup retention.
6. Khôi phục đúng cấu hình và quyền bằng change control; rotate credentials khi cần.
7. Kiểm tra lại negative paths/bypass, báo cáo tác động và bài học phòng ngừa.

**Không xóa logs hay “dọn máy” trước khi bảo toàn bằng chứng** theo quy trình điều tra của tổ chức.

## 24. Runbook triển khai bảo vệ management plane bằng ZTNA

### Bước 1 — Lập inventory tài sản và quyền dẫn xuất

Thu phạm vi:

- Tất cả SSH/RDP/WinRM, web admin panels, Kubernetes/cloud APIs và thiết bị mạng.
- Management subnets/VLAN/VRF, public IPs, secondary NICs, VPN/peering routes, IPv4/IPv6.
- PKI/IdP, backup, BMC/OOB và mọi đường break-glass.
- Human roles, shared accounts, machine identities, CI pipelines và permanent tokens.
- System owners, impact tier, business recovery priority, SLO và data classification.

Ưu tiên **Tier 0 và những đường Internet-facing** có tác động lớn. Đừng bắt đầu bằng chính sách chặn hàng loạt khi chưa biết đường quản trị hiện có.

### Bước 2 — Vẽ kiến trúc trust boundaries

Với mỗi tài nguyên, mô tả:

~~~yaml
# Policy-as-intent cho design review; KHÔNG phải schema ZTNA có thể apply.
resource: linux-prod-lab-01
owner: platform-team
classification: high-privilege
management_protocol: ssh
network_location: private-management-subnet
allowed_path: managed-paw-via-ztna-broker
allowed_human_role: diagnostics-read-only
authentication: phishing-resistant-mfa
device_requirement: enrolled-and-healthy
privilege_activation:
  type: just-in-time
  duration_minutes: 15
  approval: change-owner-for-sensitive-operations
target_controls:
  - verified-ssh-host-key
  - limited-os-account-and-sudo
  - no-direct-public-exposure
  - session-audit
emergency_access: approved-out-of-band-recovery
evidence_required:
  - identity-and-device-decision
  - pep-session-id
  - native-target-audit
  - direct-path-negative-test
~~~

Phải định rõ **PDP, PEP, target-native authorization và emergency path**. Nếu cloud console không thể đi qua proxy của bạn, native IAM/conditional-access phải là một PEP tương ứng cho API đó.

### Bước 3 — Chuẩn hóa identities và device assurance

1. Bỏ tài khoản dùng chung khi có thể; phân quyền theo human identity hoặc giữ PAM mapping/audit bù trừ.
2. Triển khai phishing-resistant MFA cho Tier 0 theo khả năng, với enrollment/recovery được kiểm soát.
3. Thiết lập PAW, MDM/EDR baseline và posture freshness.
4. Tách machine identities; chuyển khỏi token lâu hạn sang short-lived federation nếu có thể.
5. Kiểm tra offboarding, device compromise và cách revoke active session thực sự.

### Bước 4 — Thiết lập role và quyền tạm thời

- Mô hình **read-only, operational, security-policy-change, emergency** roles theo resource.
- Loại bỏ standing high-privilege access, dùng JIT/JEA và approval khi cần.
- Đặt session/credential TTL, giới hạn phạm vi **host, port, application hoặc API action**.
- Giới hạn tác vụ đặc biệt như **export key, sửa IAM trust, xóa backup, mở public firewall**.
- Áp dụng quy trình separation of duties cho high-risk changes.

### Bước 5 — Chặn các đường đi vòng

- Giới hạn public IPv4/IPv6, security group/NSG, host firewall, network ACL.
- Không mở cả management CIDR qua VPN nếu chỉ cần một target.
- Kiểm soát egress từ jump hosts và connectors; xác minh không tạo proxy pivot.
- Giới hạn direct access tới BMC, hypervisor, Kubernetes API, cloud control APIs.
- Phối hợp **native RBAC/IAM và admission/guardrails** vì network PEP không kiểm soát mọi hành động.
- Đảm bảo không làm mất **OOB recovery path** trước khi bật deny.

### Bước 6 — Canary và kiểm thử dương/âm

Triển khai trước trên **một tập tài nguyên lab/canary**:

~~~text
Positive:
  Approved admin + healthy PAW + valid JIT -> specific SSH target: ALLOW
  Approved CI job + scoped workload role -> allowed API action: ALLOW
  Approved emergency operator -> OOB recovery during drill: ALLOW

Negative:
  Unmanaged device -> admin resource: DENY
  VPN-only identity -> direct SSH target: DENY
  Approved admin -> unauthorized target: DENY
  Expired JIT role -> privileged API action: DENY
  Unreviewed CI workflow -> production admin role: DENY
  Wrong network path/IPv6 alternate -> target: DENY
~~~

**Positive control phải có backend khỏe và quyền hợp lệ**; nếu SSH daemon không chạy, một negative test timeout không chứng minh PEP hoạt động. Sau khi được phép, còn phải kiểm tra user không thực hiện được những **tác vụ ngoài role**.

### Bước 7 — Triển khai theo nhóm có rollback

~~~mermaid
flowchart TD
    A["Asset + identity inventory"] --> B["Threat model và trust boundaries"]
    B --> C["PDP/PEP, IAM/RBAC, PAM/JIT design"]
    C --> D["Network isolation + break-glass review"]
    D --> E["Lab allow/deny tests và recovery drill"]
    E --> F{"Security và RTO/SLO đạt?"}
    F -- "Không" --> G["Sửa thiết kế / rollback"]
    G --> D
    F -- "Có" --> H["Canary theo tier/resource"]
    H --> I["Monitor identity, sessions, target audit"]
    I --> J{"Bypass hoặc operational regression?"}
    J -- "Có" --> G
    J -- "Không" --> K["Mở rộng rollout + periodic review"]
~~~

Mỗi thay đổi phải có **scope asset/role, approver, policy version, expected allow/deny, time window, OOB recovery contact, rollback steps và post-deployment review**. Chú ý thay đổi firewall, VPN route, IdP policies hoặc CA trust có thể **ngắt luôn đường quản trị để phục hồi chúng**.

### Bước 8 — Giám sát lâu dài và thu hồi quyền thừa

Định kỳ so sánh desired state và effective state:

- Có public management endpoint mới hay policy drift?
- Những admin nào còn standing rights không dùng?
- Service account/CI role nào không có owner hoặc đã quá tuổi?
- MFA method, device posture và session termination có theo baseline?
- Bản ghi ZTNA/PAM có correlate được target/cloud audit không?
- Có emergency credential nào vừa được dùng nhưng chưa rotate?
- DR region, OOB và hybrid VPN có giữ cùng security posture?
- Những chính sách exception có ngày hết hạn và chủ trách nhiệm?

Kết thúc một đợt triển khai không có nghĩa bảo vệ vĩnh viễn: workload, nhân sự, routes, cloud API và device posture tiếp tục thay đổi. **Continuous verification** cần là hoạt động vận hành có owner và metrics cụ thể.

## 25. Bài tập tự kiểm tra và tình huống thiết kế

### Bài 1 — VPN có tương đương ZTNA?

Một nhân viên đã đăng nhập VPN với MFA và có route tới `10.40.40.0/24` chứa toàn bộ management hosts. Đã đủ để khẳng định họ chỉ có quyền quản trị các hệ thống được phép chưa?

*Đáp án gợi ý:* chưa. VPN xác thực/thiết lập kênh và có thể có ACL, nhưng route tới cả subnet không tự giới hạn **resource/action**. Cần firewall, target RBAC, ZTNA/PAM JIT và kiểm thử đường trực tiếp.

### Bài 2 — Phân biệt authentication và authorization

Một quản trị viên có FIDO2 MFA thành công nhưng không có role sửa IAM cloud. Họ có nên gọi được API `CreateAccessKey` không?

*Đáp án:* không. Xác thực mạnh chứng minh danh tính, còn quyền thao tác phải do native IAM/PIM policy quyết định.

### Bài 3 — Device posture

Thiết bị đã được MDM đăng ký nhưng EDR mất kết nối từ hôm trước. Có thể coi `managed = compliant` và cấp quyền Tier 0 không?

*Gợi ý:* không mặc định. Posture phải xét **freshness, EDR/OS baseline, device risk** và chính sách của loại tài nguyên; có thể deny hoặc yêu cầu remediation.

### Bài 4 — PAW

Người quản trị sử dụng cùng laptop để mở các website không tin cậy và đăng nhập CA administration. PAW giúp giảm rủi ro nào?

*Gợi ý:* giảm nguy cơ malware/credential theft/phishing trên workstation đa mục đích ảnh hưởng quyền Tier 0; cần cùng device management, role separation, identity và session controls.

### Bài 5 — Source IP trong SSH allowlist

SSH server chỉ nhận IP của ZTNA broker. Như vậy user nào kết nối qua broker cũng được root shell không?

*Đáp án:* không. IP chỉ giúp hạn chế network path; broker và SSH server vẫn cần **xác thực human/credential, phân quyền OS/sudo và session audit**.

### Bài 6 — JIT expiry

Một user kích hoạt admin role trong 15 phút. Sau khi hết TTL, một SSH session đã mở vẫn chạy được. Có thể kết luận toàn bộ cơ chế JIT bị vô hiệu không?

*Gợi ý:* phải xem policy có yêu cầu **active-session termination** hay chỉ chặn cấp phiên mới; kiểm tra khả năng kỹ thuật và target credential validity. Nếu yêu cầu chấm dứt tức thời mà không thực thi, đó là FAIL cần sửa.

### Bài 7 — SCP/SSH port forwarding

Người quản trị chỉ được phép SSH tới một server, nhưng đã được mở khả năng remote port forwarding. Điều gì cần đánh giá?

*Gợi ý:* khả năng tạo tunnel/pivot vượt qua mạng phân đoạn, agent forwarding, SFTP/file transfer, egress của target, host firewall và broker audit.

### Bài 8 — RDP clipboard

Một PAW truy cập jump host có quyền xem cấu hình PKI; người dùng có thể copy private key về desktop. Chỉ có MFA ở gateway đủ chưa?

*Đáp án:* chưa. Cần JEA, phân quyền key export, clipboard/drive redirection controls, target authorization, session monitoring, HSM/no-export khi phù hợp.

### Bài 9 — Kubernetes API

Một người chỉ cần xem Pod status trong `ztna-lab` nhưng được cấp `cluster-admin`. Sai ở đâu?

*Gợi ý:* quyền quá rộng so với nhu cầu. Dùng Role/RoleBinding đúng namespace/resource/verbs và chặn quyền leo quyền ngoài ý định.

### Bài 10 — Cloud API ngoài portal

Doanh nghiệp bắt buộc quản trị viên dùng ZTNA portal để vào cloud console, nhưng một access key dài hạn vẫn gọi API admin trực tiếp. Đây là vấn đề gì?

*Đáp án:* non-human/direct API bypass; cần native IAM, short-lived credentials, conditional access, org guardrails và pipeline identity controls.

### Bài 11 — Read-only không có nghĩa vô hại

Tại sao một account “read-only cloud backup” vẫn có thể gây ảnh hưởng bảo mật?

*Gợi ý:* có thể đọc bản sao dữ liệu nhạy cảm hoặc metadata chứa secrets. Phải xem resource permissions và data sensitivity, không chỉ verbs GET/List.

### Bài 12 — BMC và OOB

Server đã tắt public SSH và sử dụng broker, nhưng BMC/Redfish console vẫn mở từ user LAN. Tài nguyên đã an toàn chưa?

*Đáp án:* chưa. BMC có quyền dưới OS, cần network isolation/PEP, credentials riêng, firmware hardening và OOB audit.

### Bài 13 — Break-glass

IdP down khiến ZTNA broker không xác thực được người quản trị. Có nên bật công khai SSH với password mặc định để khôi phục không?

*Đáp án:* không. Sử dụng **break-glass/OOB đã được bảo vệ và diễn tập**, custody, emergency verification, restricted source, logging, post-use rotation.

### Bài 14 — Tài khoản dùng chung

Ba kỹ sư đăng nhập một firewall bằng `admin` chung. Logs chỉ ghi `admin changed ACL`. Thiếu gì để điều tra trách nhiệm?

*Gợi ý:* danh tính từng người, approval/JIT session ID, PAM credential checkout mapping, IP/device provenance và audit tại target.

### Bài 15 — CI quyền production

Một CI job nhận production cloud role ở mọi branch và mọi event. Các điều kiện trust nào cần thiết?

*Gợi ý:* short-lived federation, giới hạn issuer/audience/subject, protected branch/environment, approval, role/action/resource scope, runner isolation và API audit.

### Bài 16 — Backup immutable

Backup service có immutable storage nhưng backup administrator vẫn có quyền sửa retention lock policy. Những kiểm soát nào bổ sung?

*Gợi ý:* separation of duties, high-risk JIT approval, IAM deny guardrails, tamper-resistant audit, recovery tests và credential custody.

### Bài 17 — Negative test sai

Một tester truy cập SSH từ Internet và bị timeout, sau đó đánh dấu “ZTNA authentication DENY: PASS”. Nhận định này có đúng không?

*Đáp án:* không. Timeout có thể do route/firewall/server down. Muốn chứng minh **ZTNA authentication/authorization**, cần test ở đúng PEP với target healthy và logs quyết định.

### Bài 18 — Đường IPv6

Một VM có private IPv4 nhưng có global IPv6 và firewall IPv6 cho TCP/22 từ `::/0`. Thiết kế “không Internet SSH” đã đạt chưa?

*Đáp án:* chưa. Phải xét IPv6 route/interface/security policy riêng, đóng đường trực tiếp nếu ngoài phạm vi và kiểm thử nguồn không được phép.

### Bài 19 — Policy của máy thay đổi giữa phiên

Một PAW lúc vào phiên đạt EDR health, nhưng sau đó agent bị vô hiệu hóa. ZTNA nên có hành vi gì?

*Gợi ý:* thu tín hiệu posture mới, đánh giá session risk, re-auth/revoke/terminate theo khả năng PEP và yêu cầu bảo mật; có logs và kế hoạch xử lý session còn sống.

### Bài 20 — Thiết kế tổng hợp

Thiết kế bảo vệ **cloud IAM console, Kubernetes API, firewall UI, Linux SSH và BMC** cho đội Platform gồm ba administrator, có CI/CD pipeline và DR site. Hãy đề xuất **bốn ALLOW flows, sáu DENY flows**, break-glass path và tiêu chí test.

*Gợi ý:* ALLOW managed PAW+FIDO2+JIT→một target, CI scoped role→một deployment API, approved auditor→read-only audit, emergency operator→OOB theo quy trình. DENY unmanaged device, direct public SSH/RDP/BMC, VPN-only lateral access, unapproved role elevation, CI unreviewed branch→prod, role expired→new session, DR bypass. Ghi rõ PEP, IAM/RBAC, identity, TTL, logs và positive controls.

## 26. Checklist bảo vệ tài nguyên quản trị theo Zero Trust

### 26.1. Inventory và phân tầng

- [ ] Liệt kê mọi management interfaces: **SSH, RDP, WinRM, Kubernetes/cloud APIs, network devices, BMC/hypervisor, IdP, PKI, DNS, backups và CI systems**.
- [ ] Ghi **owner, impact tier, public/private exposure, protocol, IPv4/IPv6, connection path, dependencies và RTO/RPO**.
- [ ] Phân loại quyền dẫn xuất: asset nào có thể cấp quyền, sửa route, phát chứng thư, đọc Secret hoặc xóa backup?
- [ ] Có ownership cho machine identities, shared/service accounts và emergency accounts.

### 26.2. Danh tính, thiết bị và quyền

- [ ] Ưu tiên **phishing-resistant MFA** cho tài khoản đặc quyền; bảo vệ enrollment/reset.
- [ ] Mỗi human admin có identity riêng và lifecycle offboarding/revocation được thực thi.
- [ ] Tier 0 admins sử dụng **PAW/managed privileged workspace** theo rủi ro.
- [ ] PDP có posture, source, risk và freshness từ nguồn tin cậy; không chỉ một cờ `compliant` tự khai.
- [ ] Sử dụng **JIT/PIM/PAM** và role/action scope thay standing admin khi có thể.
- [ ] Có step-up/dual control cho IAM, PKI, backup, route/firewall và high-risk operations.
- [ ] Không cấp quyền đọc Secret/backup chỉ vì role có tên “read-only”.
- [ ] Hạn chế local admin, sudo, PowerShell remoting và quyền file transfer/port forwarding theo nhiệm vụ.

### 26.3. Chặn bypass và bảo vệ target

- [ ] Không có **public direct SSH/RDP/BMC** ngoài ngoại lệ đã được duyệt và kiểm soát.
- [ ] Cloud SG/NSG/firewall, private routes/VRF/VLAN/OOB giới hạn đúng **source broker và target**.
- [ ] VPN không tự mở toàn bộ management CIDR/ports sau khi vào tunnel.
- [ ] ZTNA/PAM PEP nằm trên các đường vào thực, kể cả **secondary NIC/IPv6, DR, VPN/peering và jump hosts**.
- [ ] Cloud console/API có **native IAM/conditional access/organization guardrails**, kể cả khi không đi qua broker.
- [ ] Kubernetes API dùng RBAC/admission/audit và bảo vệ API endpoint; không nhầm CNI NetworkPolicy là control toàn API server.
- [ ] Server có SSH host key verification, TLS certificates và OS/application authorization thích hợp.
- [ ] OOB/BMC có network isolation, credentials riêng, firmware baseline và emergency audit.
- [ ] CI/CD và workloads dùng **short-lived machine identities**, permissions hẹp, workflow/environment approval và audit.
- [ ] Không để credentials/token lâu hạn trong image, repository, CI logs hoặc shared chat.

### 26.4. Phiên và giám sát

- [ ] Session ID liên kết **human, device, resource, approval, TTL, role và native target action**.
- [ ] Phân biệt **PDP decision, PEP enforcement và target authorization**, không coi portal allow là target allow.
- [ ] Đã kiểm tra khả năng **kết thúc phiên còn sống** khi quyền hết hạn/thiết bị không compliant.
- [ ] Logs có timestamps UTC, ownership, không ghi passwords, private keys, tokens hay dữ liệu khách hàng không cần thiết.
- [ ] Central audit được bảo vệ khỏi sửa/xóa bởi đúng đối tượng đang được giám sát.
- [ ] Alert các sự kiện rủi ro: **high-privilege grants, MFA reset, key export, route/firewall changes, backup delete, unapproved OOB access**.
- [ ] Bản ghi màn hình/phiên được quản lý retention và quyền riêng tư; API/noninteractive actions cũng được audit.

### 26.5. Kiểm thử, vận hành và khôi phục

- [ ] Có **positive tests** chứng minh admins và CI jobs hợp lệ vẫn thực hiện đúng việc.
- [ ] Có **negative tests** cho wrong identity, unmanaged device, expired JIT, wrong target, direct path và IPv6 bypass.
- [ ] Có test cho **least privilege tại target**, không chỉ khả năng mở network socket.
- [ ] Có **break-glass/OOB recovery path** tách phụ thuộc hợp lý, diễn tập và đóng/rotate sau sử dụng.
- [ ] Khi rollout firewall/IdP/PEP policy, đã chuẩn bị **canary, config diff, approver, rollback và kênh cứu hộ**.
- [ ] Periodic review thu hồi quyền thừa, kiểm tra policy drift, service account age và DR parity.
- [ ] Incident response có phương pháp revoke active sessions, rotating credentials, điều tra persistence và bảo toàn evidence.

**Kết luận:** bảo vệ tài nguyên quản trị theo Zero Trust không chỉ là đặt SSH/RDP sau VPN hoặc đăng nhập console bằng MFA. Cần **xác minh danh tính và thiết bị, cấp đúng quyền theo tài nguyên/tác vụ/thời gian, bắt buộc mọi đường truy cập qua điểm kiểm soát phù hợp, thực thi quyền ngay tại target và theo dõi được hoạt động**. Đồng thời phải bảo vệ cloud APIs, pipeline automation, OOB/PKI/backup và duy trì **đường khôi phục an toàn khi hệ thống kiểm soát gặp sự cố**. Chỉ khi kiểm thử cả **truy cập được phép lẫn bị cấm**, các ranh giới quản trị mới có giá trị thực tiễn.

### Tài liệu tham khảo

- [NIST SP 800-207 — Zero Trust Architecture](https://csrc.nist.gov/pubs/sp/800/207/final): nguyên tắc zero trust, PDP/PEP, policy decision và enforcement.
- [NIST SP 800-53 Rev. 5 — Security and Privacy Controls](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final): nhóm kiểm soát access control, identity, audit, incident response và contingency.
- [NIST SP 800-63B — Digital Identity Guidelines: Authentication](https://pages.nist.gov/800-63-4/sp800-63b.html): xác thực, phishing resistance và authenticator assurance.
- [CISA — Zero Trust Maturity Model](https://www.cisa.gov/zero-trust-maturity-model): identity, devices, networks, applications/workloads và data.
- [CISA — Secure Cloud Business Applications (SCuBA)](https://www.cisa.gov/resources-tools/services/secure-cloud-business-applications-scuba-project): baseline quản trị cloud SaaS và identity.
- [FIDO Alliance — Passkeys](https://fidoalliance.org/passkeys/): xác thực chống phishing theo chuẩn FIDO2/WebAuthn.
- [OpenSSH Manual — sshd_config](https://man.openbsd.org/sshd_config): cấu hình SSH server và giới hạn authentication/forwarding.
- [OpenSSH Manual — ssh](https://man.openbsd.org/ssh): host key verification, key-based authentication và session options.
- [Kubernetes Documentation — Role-Based Access Control](https://kubernetes.io/docs/reference/access-authn-authz/rbac/): Roles, RoleBindings và phép kiểm tra quyền.
- [Kubernetes Documentation — Auditing](https://kubernetes.io/docs/tasks/debug/debug-cluster/audit/): audit events của Kubernetes API.
- [Microsoft — Securing privileged access](https://learn.microsoft.com/en-us/security/privileged-access-workstations/privileged-access-strategy): chiến lược bảo vệ tài khoản và thiết bị đặc quyền.
- [AWS IAM — Security best practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html): federated identity, MFA, temporary credentials và least privilege.
- [Google Cloud — Identity and Access Management](https://cloud.google.com/iam/docs/overview): quản lý IAM roles và principal access.
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): bảo vệ credentials/secrets và lifecycle.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): audit và dữ liệu nhạy cảm trong log.








