# Host Security: Đánh giá bảo mật máy chủ có bằng chứng trong Platform Assurance

## 1. Bài toán: máy chủ đã được hardening có thật sự an toàn?

Một đội vận hành Invoice SaaS khai báo cấu hình an toàn cho toàn bộ máy chủ: đăng nhập quản trị chỉ qua bastion, kernel đã được vá, tường lửa nội bộ giới hạn cổng cần thiết, agent giám sát hoạt động, dữ liệu được mã hóa và workload không có quyền root. Báo cáo compliance thể hiện phần lớn host đạt baseline. Tuy nhiên, trong một đợt điều tra, nhóm phát hiện một VM cũ còn nhận SSH từ Internet; một Kubernetes worker node chưa reboot sau cập nhật kernel; một agent EDR ngừng gửi events dù service vẫn báo trạng thái running; và một snapshot backup còn chứa secret đã thu hồi.

Vấn đề không chỉ là **thiếu security controls** mà còn là **thiếu bằng chứng chứng minh các controls đang hoạt động trên đúng tập host, tại đúng thời điểm**.

**Host security (bảo mật máy chủ)** là các biện pháp bảo vệ hệ điều hành, firmware, tài nguyên phần cứng/ảo hóa, dịch vụ hệ thống, local identities, network interfaces, processes, files, storage, audit và runtime state của một máy chủ trước việc truy cập, thay đổi hoặc lạm dụng trái phép.

**Host security assurance** là hoạt động đánh giá có cấu trúc rằng các biện pháp đó **được thiết kế phù hợp, triển khai đúng, hoạt động có hiệu lực và được giám sát liên tục**, sử dụng evidence có provenance, freshness, scope và khả năng tái kiểm tra.

Trong module **SECURITY_SECURITY_ASSURANCE**, nội dung này phục vụ mục tiêu xây dựng cách đánh giá có bằng chứng rằng hệ thống đáp ứng mục tiêu bảo mật qua phân tích rủi ro, security requirements, controls, kiểm thử, audit và khắc phục. Bài không dừng ở danh sách “các setting nên bật”; nó giải thích **làm thế nào chứng minh host posture và residual risk trên một hệ thống thật**.

Chuỗi lập luận trung tâm:

**Business service → host/asset identity → threat & security requirement → approved host baseline → effective host state → adversarial/negative verification → evidence → finding/remediation → retest → continuous assurance.**

### Kịch bản xuyên suốt

Các ví dụ dùng Invoice SaaS giả định với Java/Spring APIs, export workers, PostgreSQL, Kubernetes nodes, VM bastion, cloud IAM, object storage và monitoring. Tên thiết bị, hostname, command output, version và finding ID đều là minh họa, không phản ánh một môi trường thật.

## 2. Phân biệt host security, host hardening và platform assurance

| Khái niệm | Trọng tâm | Bằng chứng cần |
| --- | --- | --- |
| **Host security** | Các controls bảo vệ một host và những workload/identities của nó. | Effective permissions, services, kernel state, network và audit. |
| **Host hardening** | Giảm attack surface và thiết lập secure defaults. | Versioned baseline, applied settings, readback. |
| **Configuration assurance** | Đối chiếu expected, deployed và effective settings. | Config state, process/load behavior, drift detection. |
| **Vulnerability management** | Tìm, phân loại, xử lý các lỗ hổng trên host/packages. | Advisory applicability, affected assets, verified fixed state. |
| **Patch management** | Lập kế hoạch, áp dụng và kích hoạt updates. | Package/firmware version, reboot, regression tests. |
| **Platform assurance** | Đánh giá chuỗi tin cậy platform/OS/virtualization và shared infrastructure. | Control effectiveness liên tầng, trusted evidence và risk. |
| **Security assurance** | Lập luận tổng thể mục tiêu bảo mật được đáp ứng tới đâu. | Claim–Argument–Evidence, limitations, accepted risk. |

### Một cấu hình đúng chưa đủ

File baseline quy định SSH chỉ cho phép public-key authentication; nhưng sshd process có thể đang dùng file khác, một port forwarding proxy bỏ qua bastion, hoặc local root credentials có thể truy cập qua hypervisor console. **Approved configuration** không tự chứng minh **effective attack surface**.

### Một scanner xanh cũng chưa đủ

Kết quả “0 high findings” có thể do host không được inventory, scanner thiếu quyền, agent không chạy hoặc vendor đã backport fix không khớp version matcher. Cần biết **mẫu số, phạm vi, trạng thái nguồn đo và cách kiểm chứng thực tế**.

## 3. “Host” là gì trong các mô hình triển khai khác nhau?

Không phải hệ thống nào cũng cho tổ chức cùng quyền kiểm soát máy chủ.

| Mô hình | Host được xem xét | Trách nhiệm có thể thuộc tổ chức | Phần thường thuộc provider |
| --- | --- | --- | --- |
| **Bare metal/on-prem** | Firmware, hardware, hypervisor nếu có, OS. | Gần như toàn bộ boot, OS, network, access, storage, physical process. | Có thể là vendor hardware/software support. |
| **IaaS VM** | Guest OS/instance và workload. | Guest patch, local identities, configuration, disk encryption controls, virtual network, workload credentials. | Physical host, hypervisor infrastructure, một phần cloud fabric. |
| **Managed Kubernetes** | Worker nodes/nodes pools, containers; control plane phần lớn do provider quản. | Node image/version theo dịch vụ, workloads, service accounts, CNI/policies tùy platform, pod security. | Managed control plane/underlying hardware theo hợp đồng. |
| **Self-managed Kubernetes** | Control plane, worker nodes, guest OS, etcd. | Cluster OS/hardening/patch/identities/network, workloads và recovery. | Physical fabric nếu dùng IaaS. |
| **PaaS/serverless** | Runtime boundary được nhà cung cấp vận hành. | Application config, package/runtime selection (nếu chọn được), IAM, data access, function permissions và logs. | OS/hypervisor patch, host isolation, physical infrastructure. |
| **Managed database** | Provider host/OS/engine bên dưới. | DB roles/config/client security/engine options theo quyền, data protection, backup contracts. | Host OS/physical security, managed engine maintenance theo SLA. |

### Quy tắc shared responsibility

Không kết luận “host được bảo vệ” chỉ vì cloud provider công bố hardening. Với IaaS, guest OS thuộc trách nhiệm người thuê; với managed service, đòi evidence phù hợp **service contract và assurance report của provider** cho phần provider quản, đồng thời kiểm chứng các controls thuộc phía mình.

### Scope khi không có host-level access

Với serverless, có thể không thu được boot measurement hay kernel audit từ host vật lý. Trạng thái phải là **provider-managed/covered by supplier assurance** với evidence và limitations tương ứng, không giả tạo PASS bằng một lệnh không thể chạy.

## 4. Threat model ở ranh giới máy chủ

Một host có nhiều đường truy cập hơn cổng HTTP công khai:

- Network exposure: SSH/RDP/WinRM, service ports, out-of-band management.
- Local access: OS users, sudo/admin groups, remote sessions, debug shells.
- Workload compromise: ứng dụng bị khai thác và chiếm quyền process.
- Kernel/driver/firmware vulnerability: privilege escalation hoặc persistence.
- Host-to-host lateral movement: shared credentials, unrestricted egress, weak segmentation.
- Hypervisor/VM/container escape hoặc co-residency risks theo platform.
- Storage/backup compromise: disk, swap, crash dumps, snapshots, images.
- Supply-chain/configuration tampering: packages, boot artifacts, agents, scripts, IaC.
- Telemetry evasion: agent disabled, audit policy bị sửa, collector offline.
- Administrative misuse: break-glass abuse, unmanaged accounts, direct console access.

### Một DFD ở mức host

~~~mermaid
flowchart LR
    U["External user / partner"] --> G["Approved gateway"]
    G --> H["Invoice API host / workload"]
    A["Admin with privileged access"] --> B["Bastion / JIT access"]
    B --> H
    H --> D["Database / export storage"]
    H --> S["Secret and identity services"]
    H --> L["Host audit / EDR / log shipper"]
    L --> C["Security monitoring"]
    P["Cloud / hypervisor control plane"] --> H
    O["Backup / snapshot service"] --> H
    X["Untrusted workload input"] --> H
~~~

Mỗi mũi tên đặt câu hỏi: **ai có thể tạo kết nối, với identity nào, qua control nào, dữ liệu gì được xử lý và ai có thể sửa bằng chứng?** Một host có firewall đúng vẫn có thể bị lạm dụng nếu service identity hoặc quyền cloud control plane quá rộng.

### Attacker capabilities

Phân biệt **remote anonymous**, **authenticated tenant**, **compromised application process**, **malicious local user**, **privileged administrator** và **provider/control-plane compromise**. Một điều kiện kiểm thử PASS với remote anonymous không suy ra local root hoặc compromised process cũng bị chặn.

## 5. Security objectives và testable host requirements

| Objective | Requirement mẫu | Cần chứng minh |
| --- | --- | --- |
| **Confidentiality** | Chỉ identities được cấp quyền mới đọc dữ liệu/secrets trên host. | File/ACL/IAM, encryption, negative access tests. |
| **Integrity** | Boot, system binaries, configuration và packages không bị sửa trái phép. | Trusted boot/config provenance, integrity monitoring, change audit. |
| **Availability** | Critical services được hardening mà vẫn đạt recovery/SLO. | Health, backups, failover, controlled maintenance tests. |
| **Least privilege** | Admin/workload chỉ có quyền cần theo purpose. | OS groups/sudo/capabilities/cloud roles và denied-use results. |
| **Attack-surface reduction** | Tắt hoặc cô lập dịch vụ/cổng không cần thiết. | Listening services, actual firewall/network reachability. |
| **Patch effectiveness** | Host đang chạy fixed kernel/packages trong scope advisory. | OS build, running kernel, reboot/live-patch evidence. |
| **Detection/accountability** | Security-relevant events được thu đủ, an toàn, chính xác thời gian. | Audit source health, canary event, SIEM correlation. |
| **Resilience/recoverability** | Có đường khôi phục sạch và xác minh dữ liệu/identity. | Tested restore/rebuild, backup encryption và access controls. |

### Viết requirement có thể kiểm tra

Không viết duy nhất “hosts must be hardened”. Ví dụ tốt hơn:

**REQ-HOST-SSH-01:** “Production Linux hosts thuộc nhóm ứng dụng không cho phép SSH password authentication từ public Internet; quyền quản trị phải qua approved access path, được kiểm bằng effective daemon config, network reachability và logs trong kỳ.”

**REQ-HOST-KERNEL-02:** “Mọi production nodes bị ảnh hưởng bởi advisory A phải chạy fixed kernel/firmware state theo vendor, không chỉ có package installed chờ reboot.”

**REQ-HOST-AUDIT-03:** “Mọi host trong inventory phải tạo và gửi canary security event qua nguồn giám sát hoạt động; trường hợp collector không hoạt động được đánh dấu UNKNOWN/FAIL theo chính sách.”

### Traceability

Mỗi requirement cần map tới asset class, severity/risk, baseline, evaluation method, evidence source, owner và retest condition. Nếu không có asset/owner, việc đo sẽ thiếu mẫu số.

## 6. Asset inventory và host identity

Phân tích host security bắt đầu bằng xác định **host nào tồn tại và mang dữ liệu/quyền gì**.

### Các định danh hữu ích

- Cloud instance ID/resource URI/subscription/account/region.
- Bare-metal serial/asset tag, hardware model, ownership.
- VM ID/hypervisor cluster, image lineage.
- Hostname/FQDN/DNS/IP **như thuộc tính có thể thay đổi**, không là identity duy nhất.
- OS distribution/build/kernel, architecture và patch channel.
- Kubernetes node UID/pool/cluster, machine image, node labels/taints.
- Business service/team owner, data classification và criticality.
- Environment: production, staging, DR, ephemeral/build hosts.
- IAM/service accounts, local admin groups, management interfaces.
- Decommission status, backup/snapshot relationships và recent observations.

### Tại sao hostname không đủ?

Hostname có thể được tái sử dụng sau rebuild; IP có thể thay khi autoscale. Nếu finding gắn với IP nhưng instance đã bị thay, cần **historical mapping theo thời gian** để biết vulnerability đã được sửa, instance nào còn tồn tại, và backup/logs của host cũ còn phải kiểm soát không.

### Nguồn inventory độc lập

Đối chiếu **cloud compute API, hypervisor inventory, Kubernetes node APIs, endpoint management/EDR, DHCP/DNS/network discovery theo scope, CMDB và IaC**. Không chỉ lấy danh sách từ chính scanner đang muốn đo coverage.

### Một sai lầm dashboard

EDR báo 150/150 registered hosts healthy nhưng cloud inventory có 164 active instances; 14 instances không có agent cần được ghi **coverage gap**, không được tự loại khỏi mẫu số.

## 7. Phân loại và ưu tiên host theo rủi ro

| Host tier | Ví dụ | Rủi ro quan trọng | Assurance depth |
| --- | --- | --- | --- |
| **Tier 0 / privileged control** | Identity infrastructure, domain controllers, bastion, signing/build servers. | Kiểm soát nhiều identities/systems, lateral movement. | Strong admin controls, integrity, independent audit, recovery. |
| **Tier 1 / sensitive data path** | Invoice API nodes, DB hosts, export processing. | Confidential data/transaction integrity/tenant boundary. | Host + workload IAM, encryption, access tests, patch/EDR. |
| **Tier 2 / supporting** | Batch workers, metrics collectors, integration proxies. | Lateral movement, telemetry gaps và data leakage. | Risk-based baseline, egress, source health. |
| **Temporary/ephemeral** | CI runners, autoscaled workers, test environments. | Transient secrets, unmanaged images, short-lived blind spots. | Image attestation, bootstrap checks, lifecycle events. |

Các tier là **minh họa**, không tự thay risk classification của tổ chức. Một “supporting” telemetry host có quyền thu sensitive logs có thể trở thành **high-value target**. Business impact và privilege phải quyết định depth thực tế.

### Nguyên tắc

Không đếm mỗi host như một đơn vị rủi ro bằng nhau. Một compromised signing host có thể ảnh hưởng nhiều production workloads dù chỉ là một asset.

## 8. Chuỗi tin cậy: firmware, UEFI và Secure Boot

Bảo mật host bắt đầu trước khi OS chạy. Các tầng thường có:

1. Firmware/UEFI và cấu hình boot.
2. Firmware trust anchors, bootloader và boot artifacts.
3. Kernel/hypervisor và early boot policies.
4. OS services, local authentication và process startup.
5. Application workloads và management agents.

**Secure Boot** thường xác minh chữ ký của các thành phần boot được hỗ trợ theo trust policy; **measured boot** có thể ghi các phép đo vào TPM PCRs để phục vụ attestation. Hai khái niệm liên quan nhưng không tương đương: một máy “Secure Boot enabled” không tự có một hệ thống remote attestation đầy đủ.

### Yêu cầu cần xác minh

- Hardware/VM support và threat model có yêu cầu Secure Boot/TPM không?
- Firmware/bootloader/kernel signature trust chain được cấu hình đúng theo platform?
- Boot key databases, policy, recovery paths và updates được quản trị thế nào?
- Có hỗ trợ measured boot/TPM và baseline/reference measurements không?
- Một host có thể boot từ removable/alternate media hoặc recovery path không được kiểm soát?
- Firmware/microcode versions có known vulnerabilities hoặc support gaps không?
- Nếu attestation được dùng, verifier có biết device identity, nonce/freshness và reference policy không?

### Không tự kết luận từ một cờ

“SecureBoot=true” là một observation cần kiểm provenance. Nó không chứng minh toàn bộ kernel modules đã được xác thực, memory integrity không bị phá hoặc operator không thể đổi firmware settings. Cần evidence **phù hợp platform, boot history và policy**.

### Giới hạn bảo đảm

TPM attestation có thể hỗ trợ đánh giá **measured state** nhưng không tự chứng minh mọi phần mềm không có vulnerability hoặc không có runtime compromise sau boot. Assurance argument cần nêu chính xác **PCRs/policies, device/VM type, verifier, freshness và giả định tin cậy**.

## 9. OS/kernel runtime: package đã cài hay fix đang hoạt động?

Một kernel update có thể được cài thành công nhưng **running kernel** vẫn là bản cũ cho tới reboot. Với live patch technologies, phạm vi hotfix cũng có thể giới hạn và phải xác minh trạng thái applied/covered patches theo vendor.

| Stage | Evidence | Chưa thể kết luận |
| --- | --- | --- |
| **Candidate selected** | Vendor advisory, affected/fixed versions. | Host đã nhận fix. |
| **Downloaded** | Package cache/repository record. | Package installed. |
| **Installed** | OS/package transaction và installed build. | Kernel/driver/process đã load fix. |
| **Activation pending** | Reboot/restart scheduled, process uses old library. | Vulnerability đã được remediated. |
| **Effective fix** | Running kernel/build/package/vendor backport evidence, process reload. | Mọi dependent service vẫn functioning và regression-free. |
| **Verified** | Readback + targeted security checks + service health. | Toàn bộ tổ chức đã fix nếu chỉ test một host. |

### Version semantics

Không so version strings bằng cách đơn giản như “2.10 lớn hơn 2.9” hoặc lấy upstream version để phán backported distro package. Dùng **vendor/distribution advisory, exact package build/revision, supported kernel và effective state**.

### Kết luận đúng

“Kernel patch installed on host H” khác “host H đang chạy fixed kernel phù hợp advisory A”. Với agents/plugins/daemon đã nạp thư viện cũ, **process restart hoặc workload replacement** có thể cần thiết.

## 10. Host security lifecycle

~~~mermaid
flowchart TD
    A["Approved platform baseline and image"] --> B["Provision / enroll host identity"]
    B --> C["Boot trust and first configuration"]
    C --> D["Apply OS security policies and accounts"]
    D --> E["Patch, agents, network and storage controls"]
    E --> F["Verify effective host runtime state"]
    F --> G["Serve authorized workloads"]
    G --> H["Monitor drift, events, vulnerabilities"]
    H --> I{"Compliant and evidence current?"}
    I -- "No / unknown" --> J["Incident, finding, isolation or remediation"]
    J --> E
    I -- "Yes" --> K["Versioned assurance evidence"]
    K --> L["Rebuild / rotate / decommission when needed"]
    L --> B
~~~

### Bốn thời kỳ có đặc tính khác nhau

**Provisioning:** identity enrollment, bootstrap secret delivery và golden image trust.

**Steady state:** patch, access controls, telemetry, configuration drift, incident monitoring.

**Recovery/rebuild:** clean artifacts, credential rotation, restore/attestation và reintegration.

**Decommission:** revoke identities, detach storage, remove DNS/network permissions, handle residual disks/snapshots/logs và retention.

### Một host đã xóa không kết thúc mọi rủi ro

Volume, snapshot, AMI/image template, backup hoặc secret có thể tồn tại sau termination. Decommission evidence phải bao phủ **associated data and credentials**, không chỉ cloud instance state = terminated.

## 11. Local identity, groups và nguyên tắc đặc quyền tối thiểu

Host có thể có local users, service accounts, OS groups, sudoers/admin privileges, machine accounts và identities đến từ directory/identity providers. Để đánh giá đúng, không thể chỉ nhìn số lượng tài khoản.

### Kiểm soát cần có theo threat model

- Mọi local/remote account có purpose, owner và lifecycle rõ.
- Administrative privileges chỉ cấp cho actor và thời gian cần thiết.
- Disable/remove default, shared hoặc orphan accounts khi không cần và theo quy trình.
- Service identities không đăng nhập tương tác nếu không có nhu cầu hợp lệ.
- Authentication dùng mechanism được phê duyệt, không lưu passwords/keys dạng plaintext trong scripts.
- Quyền OS group, sudoers, Windows local administrators và service logon permissions được kiểm tra hiệu lực.
- Credentials/keys của accounts bị decommission được revoke/rotate.
- Break-glass accounts có emergency workflow, monitoring, time-bounded use và periodic tests.
- Privilege elevation event được ghi audit và cảnh báo khi cần.

### Account tồn tại chưa chắc là rủi ro, nhưng quyền thiếu quản trị là rủi ro

Một system account dùng cho daemon có thể cần thiết; câu hỏi là **nó có login shell, SSH access, write privileges, tokens hoặc group grants ngoài purpose không**. Ngược lại, một người không có local account có thể có quyền quản trị qua cloud control plane hoặc SSO mapping.

### Effective privilege

“App chạy non-root” không đủ nếu nó có Linux capabilities mạnh, host filesystem mounts, cloud role đặc quyền hoặc access tới container runtime socket. Cần xét quyền **tổng hợp trên host, workload và cloud**.

## 12. Quản trị từ xa: SSH, RDP, WinRM, bastion và JIT

Remote administration là một trong các đường tấn công giá trị cao vào host.

| Control domain | Question | Evidence phù hợp |
| --- | --- | --- |
| **Entry** | Host có thể quản trị từ mạng nào? | Effective firewall/cloud security group + bounded reachability. |
| **Identity** | Ai đăng nhập và dùng authentication nào? | Effective daemon/policy, access logs, SSO integration. |
| **Privilege** | Sau login, actor có thể nâng quyền gì? | OS groups/sudo/JEA/JIT policy và denied tests. |
| **Session** | Session timeout/recording/audit theo policy? | Session metadata/events; redact secrets. |
| **Break glass** | Có đường emergency độc lập và giám sát không? | Approved runbook, controlled drill, audit. |
| **Credential** | Keys/certs/passwords được cấp, rotate, revoke ra sao? | Inventory, lifecycle event và old-key rejection test. |
| **Path bypass** | Có direct console, VPN, cloud session manager, out-of-band management? | Route list, privileged action map, provider APIs. |

### Linux SSH

Một baseline có thể yêu cầu không cho password login hoặc direct root login. Nhưng không nên đọc một dòng từ file sshd_config và kết luận ngay: daemon có thể dùng **Include, Match blocks, command-line overrides hoặc configuration file khác**. Với OpenSSH, phương pháp kiểm cần xem **effective daemon configuration trong đúng connection context**, service process/state và network exposure.

### Windows RDP/WinRM

Kiểm Network Level Authentication, encryption/profile, local group permissions, firewall scope, privileged logon rights, remote management policy và audit. Một registry/GPO setting có thể bị override hoặc chưa áp; cần effective policy và test view.

### “Port 22 closed” không chứng minh quản trị được kiểm soát

Host có thể mở cloud console/session manager, privileged API, Kubernetes exec hoặc hypervisor access. Một **host access map** cần bao gồm mọi đường hợp lệ và các đường chưa được duyệt.

## 13. JIT/PAM, break-glass và administrative evidence

**Just-in-time (JIT) privileged access** và **Privileged Access Management (PAM)** có thể giới hạn thời gian/quyền quản trị, nhưng vẫn cần kiểm chứng runtime:

1. Request có identity và business justification.
2. Approval đúng role hoặc cơ chế emergency được duyệt.
3. Grant thực sự scoped theo host/action/time window.
4. Action được thực thi dưới identity có attribution, không dùng tài khoản chung vô danh.
5. Grant bị thu hồi theo expiration/revocation policy.
6. Audit trail liên kết request→approval→session→commands/category→revocation.
7. Evidence không chứa raw passwords/session tokens.

### Break-glass không đồng nghĩa bypass mọi thứ

Emergency account có thể cần tồn tại để cứu hệ thống khi IdP down, nhưng nên có **custody control, alerting, session accountability, recovery rehearsal và credential rotation sau dùng**. Nếu test chưa bao giờ thử recovery path, không nên tự kết luận “break-glass is effective”.

### Khi không có PAM

Có thể áp policy theo OS groups, SSH certificates, short-lived cloud sessions và access logs. Mức assurance phụ thuộc threat/risk; không mặc định mua một sản phẩm PAM là control tự động có hiệu lực.

## 14. Linux hardening: dịch vụ, quyền và kernel policy

Một Linux host cần baseline phù hợp distribution/version/workload. Những nhóm kiểm soát quan trọng:

| Area | Kiểm tra | Sai lầm thường gặp |
| --- | --- | --- |
| **OS support** | Distribution/release được vendor hỗ trợ, patch channel. | Dùng EOL image nhưng scanner có ít findings. |
| **Running services** | Chỉ daemon cần thiết chạy và listen. | Disable package nhưng service khác vẫn mở port. |
| **Package provenance** | Signed trusted repositories/packages, version pinning. | Script tải binary không kiểm provenance. |
| **Filesystem perms** | Owner, group, mode, ACL, service home/temp access. | World-readable secret hoặc writable binary directory. |
| **Sudo/polkit** | Nâng quyền theo least privilege. | Wildcard/admin unrestricted rules cho app user. |
| **Kernel settings** | Network/memory/process controls theo security baseline. | Copy sysctl từ benchmark khác, gây outage. |
| **Linux capabilities** | Processes giữ capabilities tối thiểu. | Không-root nhưng CAP_SYS_ADMIN hoặc ambient capabilities mạnh. |
| **MAC** | SELinux/AppArmor profiles enforced phù hợp. | Profile tồn tại nhưng complain/permissive hoặc workload unconfined. |
| **Audit** | Auditd/journald và shipper có integrity/coverage. | Service healthy nhưng events không đến SIEM. |
| **Temporary files** | Mounts/permissions, race protection, cleanup. | Secret trong /tmp/shared không được bảo vệ. |
| **Core dumps/swap** | Data sensitivity, encryption, retention/access. | Crash dump chứa memory secrets ngoài kiểm soát. |
| **Time** | NTP/time sync và event consistency. | Clock drift làm audit khó correlation. |

### Tính tương thích là quan trọng

Ví dụ đặt filesystem read-only ở container có thể khiến app ghi tệp tạm thất bại; tắt một service quan trọng có thể làm mất telemetry; thay sysctl liên quan networking có thể phá cluster networking. Security hardening cần **functional/resilience tests**, rollback plan và exception governance.

### Không áp lệnh sửa trực tiếp một cách mù quáng

Với production, ưu tiên **golden image/immutable rebuild, configuration management và approved change** thay vì chỉnh tay khắp máy chủ rồi cố đo compliance sau. Một emergency fix tại chỗ phải có owner, log, evidence và reconciliation vào desired baseline.

## 15. Windows host security: policy, local admins và endpoint controls

Đối với Windows Server, các nguồn policy và controls có thể bao gồm domain Group Policy, local policy, security baselines, Microsoft Defender/EDR, firewall, BitLocker (khi phù hợp), event logs và management agents.

### Các câu hỏi nên đánh giá

- OS build/support và cumulative updates đã thực sự có hiệu lực?
- Local Administrators membership có đúng approved users/groups, kể cả nested domain groups?
- RDP/WinRM access được giới hạn bởi identity, network và logon rights?
- Remote management auth/protocol và delegated privileges có theo policy?
- Defender/EDR protection/tamper configuration và agent telemetry thực sự healthy?
- Windows Firewall active profiles/rules có đúng network context?
- Account lockout/session policies và security event auditing có được áp hiệu lực?
- Service accounts, scheduled tasks và privileged services có managed credentials?
- SMB/file shares/NTFS ACL và backup/storage access có đúng data classification?
- Device encryption/BitLocker recovery/key escrow phù hợp threat model?
- Có local policy/GPO precedence hoặc conflicting policy làm sai expected state?

### GPO có thể chưa áp hoặc bị override

Một GPO được link không có nghĩa một host đã nhận và enforce đúng. Cần **resultant/effective policy**, policy refresh status, local overrides, group membership và behavior tests. Với cloud-joined hoặc hybrid endpoints, còn có nhiều management channels.

### Không đo EDR bằng icon trên desktop

Trạng thái service running không bảo đảm definitions/sensors, policy, cloud connection, tamper detection và event pipeline đều hoạt động. Một controlled security event với SIEM/EDR readback có giá trị hơn một screenshot “agent installed”.

## 16. Mandatory Access Control: SELinux, AppArmor và sandbox profiles

**Discretionary Access Control (DAC)** dùng owner/group/file permissions; **Mandatory Access Control (MAC)** như SELinux/AppArmor có thể ràng buộc process dù account có permissions khác. Assurance cần hiểu **policy enforcement mode và coverage**.

| Đặc tính | Kiểm tra |
| --- | --- |
| **Availability** | Kernel/OS hỗ trợ, module/profile được cài. |
| **Mode** | Enforcing, permissive/complain, disabled tùy nền tảng. |
| **Coverage** | Services/processes nào thuộc domain/profile, có unconfined paths không? |
| **Policy** | Quyền truy cập file/network/capabilities theo purpose. |
| **Exceptions** | Allow rules bổ sung có scope/approval/expiry? |
| **Telemetry** | Denials/audit events có đến collector không? |
| **Compatibility** | App hoạt động khi enforcing, không tạo emergency disable vĩnh viễn? |

### Đừng so sánh chỉ bằng một nhãn

Một host báo SELinux enforcing nhưng workload chính chạy unconfined có thể không đạt control mục tiêu. AppArmor có nhiều profiles; việc module được load chưa chứng minh process cần bảo vệ đã gắn profile phù hợp.

### Negative tests cần giới hạn

Trong sandbox, dùng một synthetic process với quyền bị cấm để xác minh deny/audit. Không cố truy cập production data hoặc escalate permissions ngoài RoE; không tắt MAC để “xem app có chạy không” trên host thật nếu chưa có approved change.

## 17. Host firewall, segmentation và egress control

Host firewall bổ sung cho cloud firewall/network policies và application authorization. Một rule ở một lớp có thể không áp đường khác.

### Security invariants

- Public-facing host chỉ listen trên cổng cần cho service và trong network segment cho phép.
- Management ports không exposed rộng ngoài approved management path.
- East–west connections được hạn theo source workload/identity/port khi phù hợp.
- Outbound egress chỉ phục vụ destinations/purposes được duyệt đối với critical workloads.
- Firewall configuration có owner, approval, audit và no unreviewed broad exceptions.
- IPv4/IPv6, multiple interfaces, namespace, overlay networking và provider security group đều được xét.

### Readback nhiều lớp

**Listening port ≠ remotely reachable port.** Một service lắng nghe trên 0.0.0.0 có thể được firewall chặn; một port không hiện tại thời điểm scan có thể được mở theo schedule/sidecar. Cần **host listening inventory + effective firewall + bounded test từ view được phê duyệt**.

### Rủi ro egress

Một process đã bị compromise thường cần tiếp xúc với internal control plane, secret store hoặc outbound service. Egress restrictions có thể giảm blast radius, nhưng **không thay code/identity controls** và cần xét DNS/proxies/cloud metadata access theo môi trường.

### Đừng dùng port scan vô hạn

Production scanning phải tuân RoE và giới hạn traffic. Có thể dùng **effective firewall APIs, host inspection và limited canary connectivity tests** thay vì dò toàn bộ dải IP hoặc tạo nhiều connections.

## 18. Host storage encryption và data at rest

Host có thể chứa dữ liệu trong disks, volumes, swap, temp files, crash dumps, logs, snapshots và caches.

### Những mục tiêu cần phân biệt

| Target | Threat | Control/evidence |
| --- | --- | --- |
| **Primary disk/volume** | Theft/snapshot/unauthorized disk access. | Encryption status, key identity/policy, attachment/snapshot scope. |
| **Swap/pagefile** | Memory secrets bị ghi ra disk. | Encryption/config, lifecycle and access. |
| **Core/crash dump** | Process memory chứa credentials/PII. | Dump policy, protected storage, redaction/retention. |
| **Temporary files** | Batch exports/sensitive content tồn tại sau request. | Permissions, lifecycle cleanup, encryption. |
| **Backup/snapshot** | Historical sensitive data còn truy cập được. | Backup encryption, storage policy, restore control, retention. |
| **Golden images/templates** | Embedded secrets hoặc outdated packages nhân bản. | Image scanning, provenance, secret absence, revocation. |

### Disk encryption không đủ với privileged runtime

Full-disk encryption chủ yếu bảo vệ một số tình huống **offline/data-at-rest**. Khi host đang chạy và volume đã mở khóa, một actor có OS/root/cloud permissions phù hợp có thể đọc plaintext. Cần identity controls, permissions, process isolation, audit và key management.

### Keys và recovery

Xác minh key custody/rotation/recovery và access controls theo threat model. Một encrypted volume vô ích cho availability nếu key bị mất và không có recovery, hoặc vô ích cho confidentiality nếu key grants quá rộng.

## 19. Secrets trên host, process memory và metadata services

Secrets có thể xuất hiện ở environment variables, process arguments, unit files, local config, mounted files, credential providers, systemd credentials, Windows credential stores, container mounts và cloud instance metadata.

### Câu hỏi reviewer

1. Secret đến từ nguồn nào, quyền truy cập/rotation ra sao?
2. Có được ghi log, crash dump, diagnostics hoặc process args không?
3. File chứa secret có ownership/mode/ACL đúng?
4. Workload identity có quyền lấy **chỉ secret cần** không?
5. Một host bị compromise có thể lấy secrets của hosts/tenants khác không?
6. Token lấy qua metadata service có scope và trust boundaries phù hợp?
7. Sau rotate/revoke, old credential còn được chấp nhận bao lâu?
8. Host/snapshot decommission có xử lý residual secrets?

### Không copy environment toàn bộ làm evidence

Tránh lệnh và scripts thu cả environment hoặc process memory vào ticket. Dùng **metadata**, một số allowlisted config states, secret version IDs và **controlled negative authentication tests**; không xuất raw credentials.

### Một sai lầm thường gặp

“Dùng secret manager” không tự bảo đảm least privilege. Nếu VM role có thể đọc mọi secrets của account, một lỗi RCE trong Invoice API có thể mở rộng tác động. Cần effective IAM grants, resource policies, scope và audit.

## 20. Patch management, update dependencies và reboot

Host patching phải phối hợp với **service availability, kernel/driver compatibility, maintenance, host identity, workload scheduling và rollback**.

### Các phụ thuộc kỹ thuật

- Firmware/UEFI hoặc hypervisor prerequisites theo vendor.
- Kernel updates, modules, drivers và runtime version/ABI.
- OS package manager, repositories, signatures và servicing stack.
- Container runtime/Kubernetes node version skew và CNI/CSI.
- Agent EDR/backup/logging compatibility với kernel mới.
- High-availability quorum, replica placement và workload drain.
- Disk/storage encryption và boot recovery key availability.
- Required reboot/restart để activated state khớp installed state.

### Thứ tự triển khai thường cần phân tích

**Advisory applicability → select supported fix → validate prerequisites → test image/host → canary node → controlled drain/reboot/replace → verify running state → confirm services/EDR/audit → progressive rollout → close finding with evidence.**

Không có một thứ tự nâng chung cho mọi vendor/platform; dùng **supported upgrade path của sản phẩm cụ thể**.

### Prioritization khác execution order

Một kernel vulnerability rất cấp bách nhưng cần reboot critical nodes; có thể cần containment tạm thời đồng thời chuẩn bị capacity/maintenance. Độ nguy hiểm quyết định urgency, còn prerequisites/quorum quyết định thứ tự thực hiện. Không để khó triển khai biến thành lý do hoãn không thời hạn mà không có risk owner decision.

### Rollback và residual risk

Rollback host image/kernel có thể phục hồi service nhưng đưa vulnerability quay lại. Ticket **availability restored** không đồng nghĩa **security remediated**; cần reclassify trạng thái, interim controls và retest sau fix phù hợp.

## 21. Vulnerability assessment và applicability trên host

Một vulnerability scanner có thể nhận diện package versions, kernel builds, services và configuration weaknesses. Tuy nhiên **finding là đầu vào**, chưa tự chứng minh host vulnerable hoặc fixed.

### Điều cần đối chiếu

| Input | Ý nghĩa | Sai lầm |
| --- | --- | --- |
| **Vendor advisory** | Affected/fixed versions, prerequisites, supported branches. | Lấy upstream version thay distro-specific backport. |
| **SBOM/package inventory** | Packages và dependency components trên host/image. | Không biết process đang load library nào. |
| **Kernel/driver/firmware inventory** | Effective low-level code. | Dựa vào installed package khi reboot pending. |
| **Reachability/exposure** | Service/path/identity có thể bị tác động? | Cho rằng internal host tuyệt đối không có attacker. |
| **Exploit signals** | Known exploitation, incident intelligence, asset exposure. | Dùng severity score đơn độc làm business risk. |
| **Compensating control** | Isolation, restricted access hoặc reduced feature. | Gọi “mitigated” bằng cấu hình chưa test hiệu lực. |
| **Owner/release** | Thay đổi được triển khai tới đúng asset nào? | Scan source repo rồi đánh dấu live host fixed. |

### CVE, CVSS và known-exploited signals

CVE giúp nhận diện vulnerability; CVSS mô tả characteristics severity theo phiên bản/rubric; các danh sách known exploited vulnerabilities hoặc mô hình exploit probability có thể hỗ trợ ưu tiên khi phù hợp. Chúng **không thay asset-specific impact, exposure, effective version và required evidence**.

### Finding lifecycle

**DETECTED → APPLICABILITY_PENDING → CONFIRMED/NOT_AFFECTED → APPROVED_FIX/EXCEPTION → DEPLOYED → EFFECTIVE_STATE_VERIFIED → RETESTED/CLOSED**. Một scanner không còn tìm thấy host vì host bị mất kết nối phải được xem là **coverage gap**, không tự là remediation.

## 22. Attack-surface inventory: services, processes, ports và management planes

Một host có thể không lộ trực tiếp Internet nhưng vẫn là mắt xích của đường tấn công từ workload, internal network hoặc control plane.

### Surface register nên có

- Host/instance ID, interface, IP family, hostname và environment.
- Listening service/process, process owner, binary path và provenance.
- Bind address, protocol/port, exposed zones, allowed source identities.
- Business purpose, associated workload/asset owner.
- Authentication/authorization boundary trước service.
- TLS/certificate/mTLS identity nếu có.
- Network path từ approved viewpoints, cloud firewall/host firewall.
- Debug/admin endpoints, kernel sockets, container runtime APIs.
- Planned removal hoặc risk-approved exception.

### Đừng tự gắn mức rủi ro chỉ từ số cổng

Một host chỉ mở port 443 vẫn có thể chạy ứng dụng rất dễ tổn thương; một host có nhiều internal system services không nhất thiết rủi ro hơn nếu chúng bị cô lập và kiểm quyền phù hợp. **Mục tiêu là mỗi reachable service phải có purpose, owner và effective control**.

### Hidden management planes

Cloud session APIs, hypervisor console, serial port, IPMI/BMC, Kubernetes exec, container socket và backup agents có thể là đường quản trị thực tế dù SSH/RDP đóng. Kiểm những đường này trong phạm vi thẩm quyền, không chỉ làm port scan.

## 23. Host audit và security logging

Một host có thể tạo events từ nhiều lớp: kernel/audit subsystem, authentication, sudo/UAC, service management, process execution, package update, file integrity, firewall và EDR. Security assurance cần đo **khả năng quan sát đủ và chính xác**.

| Event class | Mục đích | Evidence |
| --- | --- | --- |
| **Authentication** | Ai login thành công/thất bại, từ đâu. | Auth logs/events, principal, source, time. |
| **Privilege escalation** | Sudo, UAC, group membership, JIT/break-glass usage. | Policy decision và privileged session audit. |
| **Process/service lifecycle** | Dịch vụ bị tắt, process lạ hoặc binary thay. | Service manager, process events, EDR. |
| **Security config change** | Firewall/MAC/audit/SSH policy thay đổi. | Change event + versioned config readback. |
| **Package/boot change** | Kernel/firmware reboot/update, Secure Boot status. | Package history, boot/attestation source. |
| **Sensitive file access** | Key/secret/config artifacts bị đọc/sửa trái phép. | Scoped audit rules, not blanket data capture. |
| **Network** | Policy denies hoặc bất thường egress. | Firewall/flow events với privacy controls. |
| **Collector health** | Log shipper/sensor bị mất hoặc chậm. | Source heartbeat, canary, ingestion lag. |

### Cấu hình audit không bằng kết quả audit

Linux audit rules được tải hay Windows event policy bật chỉ là một bước. Cần tạo **security-relevant test event** trong sandbox, xác minh nó xuất hiện ở centralized collector/SIEM với host ID, event type, identity, timestamp và không lộ bí mật.

### Khi source chết

Agent/collector service “running” nhưng pipeline mất route, permissions hoặc parser có thể dẫn đến telemetry gap. Không ghi “no incidents” khi không biết events có đến hay không. Đánh dấu **UNKNOWN evidence/operating effectiveness** theo policy và khôi phục source.

## 24. Time synchronization và tính đáng tin của sự kiện

Thời gian ảnh hưởng mạnh đến audit, incident analysis, token expiry, certificate validation, cross-host correlation và forensic evidence.

### Những vấn đề cần xét

- Host sử dụng nguồn time sync được quản lý theo platform.
- Clock offset và drift nằm trong tolerance được duyệt.
- Timezone/UTC event formatting nhất quán cho correlation.
- Boot/reboot hoặc VM pause/resume không tạo sequence đánh lừa.
- Audit records có timestamp, source/host ID, event sequence hoặc correlation khi có.
- NTP/time sync configuration thay đổi có audit và alert phù hợp.
- Log collectors xử lý out-of-order/delayed events và timezone conversion đúng.

### Một bằng chứng có timestamp không tự mới

Nếu host clock sai 40 phút, bản ghi tưởng là “sau patch” có thể thực ra trước khi reboot. Đánh giá evidence freshness cần **clock confidence, collector receive time và host event time** khi cần.

### Không chỉ bật NTP rồi coi PASS

Configuration bật time sync nhưng host offline hoặc source sai có thể tiếp tục drift. Dùng readback của **actual synchronization state** và cross-source correlation trên asset critical.

## 25. Endpoint detection/response và anti-tamper

EDR/host intrusion detection có thể giám sát process, files, network và behavior. Nhưng “agent installed” không đồng nghĩa **sensor bảo vệ và evidence pipeline** đạt yêu cầu.

### Controls cần kiểm

1. Host coverage: những eligible hosts nào có agent theo baseline?
2. Agent/runtime version và signatures/rules được hỗ trợ, chưa bị EOL?
3. Sensor đang hoạt động, policy đúng group/asset class?
4. Tamper protection/privilege boundary của agent được bật và kiểm tra?
5. Agent có cloud connection, heartbeat và gửi đúng event types?
6. Alert routing/detection rules có SOC owner và SLA?
7. User/admin có thể disable/uninstall agent theo quyền nào?
8. Agent error/resource consumption có ảnh hưởng critical availability?
9. Có fallback/threat detection khác khi agent tạm mất?
10. Retention, data minimization và privacy controls có phù hợp không?

### Canary test

Sử dụng một **vendor-approved benign test event** hoặc synthetic event được security team chấp thuận trong sandbox để xác minh event được phát hiện và chuyển tới SIEM/EDR console. Không cần chạy malware thật, vô hiệu hóa agent trên production hoặc giả lập destructive attacks để chứng minh.

### Evidence có lớp

**Agent registration → active sensor → policy loaded → expected canary observed → alert delivered → SOC response**. Các mốc có thể độc lập; mất mốc nào phải ghi limitation rõ.

### Nếu host không hỗ trợ agent

Appliance, minimal image hoặc managed serverless có thể không hỗ trợ agent truyền thống. Cần documented applicability, provider telemetry/controls và compensating assurance. Không cho FAIL máy móc nếu control objective được đáp ứng bằng mô hình khác đã đánh giá.

## 26. File integrity, binary provenance và host supply chain

Host security không thể bảo vệ bằng cấu hình nếu executable/config/boot artifact bị thay trái phép.

### Chuỗi kiểm soát

**Trusted package/image source → signature/provenance verification → approved build/release → installed files → running process/binary → integrity observations → monitored changes.**

| Layer | Evidence | Hạn chế |
| --- | --- | --- |
| **Package repository** | Signed metadata, vendor/channel, approved versions. | Repository trusted không làm mọi package không có bug. |
| **Golden image** | Versioned image ID, build provenance, baseline tests. | VM có thể drift sau deploy. |
| **Binary file integrity** | Approved hashes, code-signing validation, file change events. | Hash tại T không chứng minh không bị thay ở T+1. |
| **Running process** | Executable path, mapped modules, running version/process identity. | Process có thể load deleted/old library hoặc injected memory. |
| **Kernel/boot** | Secure Boot/measured boot/TPM policy evidence. | Không tự phủ toàn bộ runtime integrity. |
| **Configuration** | Approved hashes và effective daemon config. | Config hash match không chứng minh control behavior. |

### Đừng dùng checksum sai phạm vi

Một SHA-256 của image hoặc file chứng minh **identity của bytes so với reference**, không chứng minh bytes không có vulnerability hoặc host đang chạy chính xác bytes đó. Cần verify reference trust, artifact→runtime mapping và security tests.

### Host-based integrity monitoring

Theo dõi changes ở security-critical files (authentication policy, sudoers, system binaries, audit configuration, startup services) với expected-change workflow, nguồn events đáng tin và suppression hợp lý. Đừng thu toàn bộ customer data hoặc thiết lập giám sát quá mức vượt privacy requirements.

## 27. Hypervisor, virtual machines và cloud control plane

Hypervisor/VM boundary ảnh hưởng isolation, snapshots, virtual devices, admin consoles và host identity. Khả năng đọc evidence phụ thuộc shared-responsibility model.

### Những bề mặt cần xem

- Hypervisor platform/update/support và segmentation giữa management/workload planes.
- Quản lý golden VM images và template provenance.
- VM escape/guest-to-host risk từ unsupported drivers/tools.
- Cloud control-plane identities có quyền create snapshot, attach volume, modify instance profile hoặc invoke console.
- Network security groups/subnets và provider metadata/service endpoints.
- Disk/volume encryption, KMS grants và snapshot sharing.
- VM migration/live migration và host placement expectations.
- Guest agents, hypervisor tools và patch compatibility.
- Decommission, disk remanence và snapshots lâu dài.

### Ví dụ không nên bỏ qua

Một VM có OS user không quyền admin nhưng cloud IAM role của người vận hành cho phép **snapshot volume và attach vào VM khác**. Trong threat model phù hợp, đây là đường đọc dữ liệu không cần đăng nhập guest OS. Host assurance phải nhìn **control plane privilege** bên cạnh local file ACL.

### Provider-managed boundaries

Không tự đoán provider đã đáp ứng tiêu chuẩn cụ thể từ tên dịch vụ. Dùng published responsibility model, provider audit/supplier assurance và tổ chức kiểm chứng phần thuộc quyền mình. Nêu rõ **inherited controls, gaps và kỳ áp dụng**.

## 28. Container host và ranh giới kernel chia sẻ

Containers thường chia sẻ kernel host (trong mô hình Linux container thông dụng), nên một compromise trong container có thể đe dọa node nếu isolation/configuration yếu hoặc có kernel vulnerability.

### Host risks đặc thù

- Privileged containers, hostPID/hostNetwork và host namespaces.
- Mount host filesystem hoặc container runtime socket vào workload.
- Linux capabilities vượt mức, device access và seccomp unconfined.
- Kernel/LSM profiles không tương thích hoặc không enforce.
- Container runtime, shim và node agents có vulnerabilities.
- Image provenance/old binaries, supply-chain tampering.
- Cloud instance role/node identity có quyền rộng hơn pod identity.
- Shared ephemeral storage, logs, secrets và metadata service exposure.

### Đừng gộp “pod hardening” với “node hardening”

Pod chạy non-root có thể vẫn là đường tấn công nếu **node kernel cũ, container runtime socket exposed hoặc node IAM quá rộng**. Ngược lại, node an toàn không tự bảo đảm code trong pod chống BOLA hay injection.

### Cách đánh giá nhiều lớp

**Image digest → Pod security context → admission policy → actual node/kernel/runtime → network/IAM → controlled behavior**. Không một lớp nào thay được các lớp còn lại.

## 29. Kubernetes worker nodes và host assurance

Managed Kubernetes worker nodes có lịch update/drain/replacement riêng. Cần xem **cluster version, node OS image, kubelet/container runtime, networking/storage agents và workloads**.

| Item | Assessor cần hỏi |
| --- | --- |
| **Node pool** | Node image/build, OS/kernel version nào approved? |
| **Version skew** | Control plane/kubelet/add-ons CNI/CSI tương thích theo vendor/platform? |
| **Bootstrap** | Node identity/credentials được cấp như thế nào? |
| **Node IAM** | Node role có quyền gì; pod identity có tách đúng? |
| **Network** | CNI/host firewall/metadata access có enforced? |
| **Host hardening** | SELinux/AppArmor/seccomp, OS services và audit được quản? |
| **Kubelet/API** | Endpoint/control plane connection protected; authN/authZ đúng? |
| **Runtime** | Container runtime/shim versions, sandbox capability/privilege exposure. |
| **Patch** | Reboot/drain/replacement đã kích hoạt effective fixed version? |
| **Workload placement** | Critical pods/replicas/quorum/PDB và capacity khi node thay. |
| **Telemetry** | EDR/audit/log agents là DaemonSet hay host agent; source health từng node? |
| **Recovery** | Có thể rebuild node từ approved image, revoke old credentials? |

### Rolling updates và mixed nodes

Cluster có thể chứa node pool A đã cập nhật và B chưa cập nhật. Nếu một workload critical vẫn được schedule trên node B, chỉ nhìn “new node image available” không đủ. Cần **per-node actual version, pod placement và criticality**.

### Node access surface

Cloud session manager, SSH, Kubernetes node authorizer, kubelet credentials và container runtime socket đều là đường quản trị tiềm năng. Không mặc định SSH tắt = không thể quản lý node hoặc không có privileged paths.

## 30. CI/CD build hosts, ephemeral runners và sự tin cậy của artifact

Build servers/runners là hosts có đặc quyền đặc biệt vì chúng có thể tạo binaries, container images, signed artifacts và deploy credentials. Một compromised runner có thể tác động tới production mà không đi qua application authorization.

### Security questions

- Runner có **ephemeral/immutable rebuild** hay dùng lâu dài giữa nhiều jobs?
- Jobs từ trust level thấp (untrusted PR) có chia sẻ host/secrets/cache với production build?
- Quyền deploy/signing credentials có **scoped and short-lived** không?
- Toolchain/image/package provenance có được xác minh?
- Có cách attacker sửa artifact sau security scan nhưng trước signing/deploy không?
- Cache/artifact storage có isolation, integrity và retention controls?
- Host services, user privileges, Docker socket hoặc host mounts có quá rộng?
- Logs/artifacts có lộ env vars, tokens và private keys?
- Build job/run identity được nối tới commit, provenance, artifact digest và deployed runtime?
- Có audit trail khi runner bị reprovision, bị compromise hoặc bị destroy?

### Rule of thumb

Đối với build từ untrusted inputs, cần **isolation và không cấp production secrets trực tiếp** theo policy. Artifact signing/deployment identity phải tách khỏi job có risk cao nếu kiến trúc yêu cầu.

### Evidence chain

**Source commit → approved build environment/runner image → dependency resolution → generated artifact → attestation/signature → registry → production image digest**. Một host build compliant snapshot không tự chứng minh artifact được tạo từ đúng source hoặc không bị can thiệp ở các bước sau.

## 31. Backup, disaster recovery và rebuild sạch

Host compromise hoặc ransomware scenario có thể cần **rebuild from trusted image**, không chỉ restart. Backup cũng là tài sản chứa dữ liệu/credentials nhạy cảm.

### Các controls

1. Defined **RPO/RTO** và restore targets theo business requirements.
2. Backup/snapshot coverage theo host volumes, configuration và key dependencies.
3. Backup encryption, access separation, retention và immutability/WORM khi phù hợp.
4. Restore testing trong isolated environment; không chỉ backup job succeeded.
5. Golden image/boot trust và patch baseline để rebuild không tái tạo vulnerability.
6. Credential/key rotation/revocation sau incident.
7. Forensic retention/legal hold nếu cần, song song privacy minimization.
8. Network/IAM re-enrollment và removal of compromised machine identities.
9. Service/data-integrity checks sau restore.
10. Audit/recovery evidence và owner sign-off.

### Một lỗi recovery điển hình

Khôi phục VM từ snapshot cũ có thể **mang lại stale vulnerability, SSH keys, local admin account và credential đã bị lộ**. Vì vậy recovered service có thể available nhưng chưa đủ điều kiện security assurance; cần retest host integrity/patch/identity/telemetry trước reintegration.

### Không giả định có thể rollback mọi trạng thái

Firmware/OS updates, database schema/data writes, encryption keys và cloud policy thay đổi có thể không đảo ngược đơn giản. Kế hoạch phải phân biệt **rebuild, rollback, roll-forward và restore** với prerequisites thực tế.

## 32. Desired, deployed, loaded, effective và observed host state

Một host assessment dễ sai nếu xem mọi bằng chứng như cùng một loại.

| State | Ví dụ | Điều còn thiếu |
| --- | --- | --- |
| **Approved baseline** | “SSH password login disabled; agent audit mandatory.” | Host nào đã áp? |
| **Configured on disk** | sshd configuration file có setting theo baseline. | Daemon có nạp config đó và overrides không? |
| **Control plane applied** | Firewall resource/security group đã được lưu. | Effective rules, interface/routes nào? |
| **Loaded runtime** | sshd effective config, running kernel, EDR policy loaded. | Có đường bypass nào? |
| **Observed behavior** | Approved negative login/network test bị DENY. | Test có bao phủ paths/actors khác không? |
| **Monitored state** | Agent/collector có canary, status và timestamps. | Có missed events/host population không? |

### Cấu hình và behavior có thể mâu thuẫn

Một daemon report “password authentication disabled” nhưng một alternate management access path vẫn cho remote access với credential yếu. Cần **host access map** cho đúng claim. Hoặc host firewall báo deny nhưng một load balancer/proxy chuyển tiếp traffic qua khác network boundary.

### Kết luận trung thực

**“Control configured”** chỉ hỗ trợ configuration claim. **“Behavior validated”** hỗ trợ control effectiveness trong conditions đã thử. **“All eligible hosts compliant”** đòi population/cadence/source health rõ; không suy từ một host demo.

## 33. Kiểm tra Linux host bằng các phép đọc an toàn

Ví dụ các lệnh dưới đây mang tính **read-only/diagnostic** trong hệ thống Linux được ủy quyền. Chúng không tự tạo bản báo cáo assurance hoàn chỉnh, và mỗi lệnh phụ thuộc distribution, permissions và version. Không chạy trực tiếp trên tài sản ngoài scope hoặc thu raw secrets.

~~~bash
# OS/kernel and boot state identifiers.
uname -a
cat /etc/os-release
cat /proc/sys/kernel/osrelease

# Local account and process context for the current operator.
id
ps -eo user,pid,comm --sort=user

# Listening TCP services; may not resolve every process without privileges.
ss -lnt

# Services and relevant service manager metadata.
systemctl list-units --type=service --state=running
systemctl status sshd --no-pager

# Display a selected unit's effective security-related properties.
systemctl show invoice-api.service \
  -p User -p Group -p NoNewPrivileges \
  -p ProtectSystem -p ProtectHome -p PrivateTmp

# Read current kernel boot identifier (if exposed by the OS).
cat /proc/sys/kernel/random/boot_id

# Audit subsystem status if audit tooling/permissions permit.
auditctl -s
~~~

### Quan trọng: lệnh này **không tự chứng minh PASS**

- **uname -a:** xác định running kernel, nhưng cần vendor advisory/package revision để xét fix.
- **Kernel release readback:** nên đối chiếu với vendor advisory/package build; tránh thu boot arguments hoặc process arguments không cần thiết vì chúng có thể chứa thông tin nhạy cảm.
- **ps:** process names không chứng minh không có process độc hại; arguments có thể chứa secrets, nên ví dụ chỉ in comm.
- **ss -lnt:** listener status không là reachability theo network path; UDP, IPv6 và namespaces phải xét.
- **systemctl status:** systemd service name khác theo distro; daemon có thể được quản lý không qua systemd.
- **systemctl show:** property snapshot của unit, chưa bảo đảm mọi request/process/capability thỏa control.
- **auditctl:** có thể cần privilege và không có trên một số images; source-health còn phải xác nhận central ingestion.

### Effective SSH settings cần connection context

Với OpenSSH, có thể dùng diagnostic của daemon với **kiểu truy vấn effective configuration** phù hợp phiên bản và context, dưới quyền được cấp, để kiểm Include/Match overrides. Không nên public toàn bộ output vì có thể lộ mạng nội bộ/cấu hình authentication. Hãy ghi **kết quả allowlisted** như password auth enabled/disabled, root login allowance và source/version, sau đó kiểm tra authorized negative login trong sandbox nếu RoE cho phép.

### Firewall observations

Trên Linux, cách đọc effective firewall phụ thuộc nftables/iptables/firewalld/ufw/cloud platform. Không trộn các công cụ một cách giả định; xác định **framework đang enforce**, rule precedence và actual network context, rồi kiểm read-only và safe controlled connectivity.

## 34. Windows host: PowerShell readback theo least privilege

Các lệnh minh họa sau dùng Windows PowerShell/PowerShell với modules tương ứng; **không nhằm thay đổi configuration**. Quyền, Windows edition và security agent của hệ thống quyết định câu lệnh nào khả dụng.

~~~powershell
# Version and last boot: support patch activation assessment.
Get-CimInstance Win32_OperatingSystem |
  Select-Object Caption, Version, BuildNumber, LastBootUpTime

# Local groups: the example avoids dumping credentials.
Get-LocalGroupMember -Group "Administrators" |
  Select-Object Name, ObjectClass, PrincipalSource

# Windows firewall profiles' current reported configuration.
Get-NetFirewallProfile |
  Select-Object Name, Enabled, DefaultInboundAction, DefaultOutboundAction

# Windows Defender status where the corresponding module is present.
Get-MpComputerStatus |
  Select-Object AMServiceEnabled, AntivirusEnabled,
                RealTimeProtectionEnabled, AntivirusSignatureVersion

# Recent system event metadata; narrow by provider/event type in production.
Get-WinEvent -ListLog Security |
  Select-Object LogName, IsEnabled, RecordCount, LastWriteTime
~~~

### Diễn giải kết quả

**Get-LocalGroupMember** không thay kiểm nested directory group memberships, JIT, remote management hoặc effective privileges. **Get-MpComputerStatus** không chứng minh toàn bộ EDR telemetry; một host có thể dùng third-party provider. **Get-NetFirewallProfile** không cho biết mọi cloud/security appliance rule; effective reachability cần xem toàn đường mạng.

### Những lưu ý an toàn

Security event logs có thể chứa usernames, IPs và sensitive references; chỉ thu metadata/test events được phép và bảo vệ evidence. Không xuất security hives, password hashes, token stores hay toàn bộ registry để phục vụ bài học host assurance.

## 35. Systemd service sandbox: cấu hình minh họa và kiểm chứng

Một Linux service chạy Java export worker có thể được hardening bằng systemd restrictions. Ví dụ bên dưới **không phải cấu hình áp dụng phổ quát**; phải được thử trên hệ thống hỗ trợ systemd và ứng dụng có đường ghi phù hợp.

~~~ini
# /etc/systemd/system/invoice-export-worker.service
# Illustrative only; approved deployment/identity required.
[Unit]
Description=Invoice Export Worker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=invoice-exporter
Group=invoice-exporter
WorkingDirectory=/opt/invoice-export
ExecStart=/usr/bin/java -jar /opt/invoice-export/worker.jar
Restart=on-failure
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
RestrictSUIDSGID=yes
LockPersonality=yes
CapabilityBoundingSet=
AmbientCapabilities=
StateDirectory=invoice-exporter
ReadWritePaths=/var/lib/invoice-exporter

# Environment/credentials should be provided through an approved
# secret and workload identity mechanism, not a plaintext unit file.

[Install]
WantedBy=multi-user.target
~~~

### Những điều phải xác minh

1. User/group tồn tại, không có login/admin grants ngoài purpose.
2. Java runtime, libraries, mount paths và file writes tương thích.
3. Service không cần capabilities đã bị loại; workload có thể vẫn cần network/socket access.
4. Không ghi secret plaintext vào unit, environment logs hoặc process args.
5. Unit đã được systemd load và restart/reload sau change theo procedure.
6. Effective unit properties/actual process identity đúng.
7. System security vẫn có **host firewall, service authorization, IAM, patch và audit**.
8. Negative tests xác minh worker không thể đọc data/secret ngoài quyền trong sandbox.

### “Security score” của systemd

Một số bản systemd cung cấp công cụ phân tích security exposure của unit. Kết quả có thể hỗ trợ tìm opportunities nhưng **không thay threat model hoặc chứng minh không có bug**. A score đẹp không bao phủ application code, container host, cloud IAM hoặc data access.

### File path là một control target

Ngay cả khi root filesystem được bảo vệ, service cần writable state dir. Quyền sở hữu và dữ liệu tại đó phải được kiểm; nếu export files chứa PII và còn lưu lâu, một sandbox setting không giải quyết retention/privacy requirements.

## 36. Mẫu YAML Host Security Control Register

Record dưới đây mô tả **cách đánh giá** một control, không tự chạy scanner và không tạo evidence thật.

~~~yaml
schema_version: "1.0"
record_type: "host_security_control"
control_id: "HOST-PRIV-001"
service_name: "SECURITY_SECURITY_ASSURANCE"
domain: "Platform assurance / Host security"
description: >
  Production Invoice API and export worker hosts
  use approved least-privilege execution identities.
security_objectives:
  - "Confidentiality"
  - "Integrity"
  - "Least privilege"
threats:
  - "T-HOST-LATERAL-MOVEMENT"
  - "T-HOST-PRIVILEGE-ESCALATION"
scope:
  environments:
    - "production"
  host_classes:
    - "kubernetes-worker-node"
    - "invoice-api-vm"
    - "export-worker-vm"
  exclude_if:
    - "provider-managed-physical-host-with-inherited-evidence"
requirements:
  - id: "REQ-HOST-PRIV-01"
    expected: "service-process-not-administrative"
  - id: "REQ-HOST-PRIV-02"
    expected: "no-unauthorized-capabilities-or-host-mounts"
  - id: "REQ-HOST-PRIV-03"
    expected: "workload-cloud-role-scoped-to-purpose"
evidence_sources:
  - "independent-cloud-and-cluster-inventory"
  - "actual-host-or-pod-process-identity-readback"
  - "effective-iam-and-resource-policy-observation"
  - "approved-synthetic-denied-action-tests"
validation:
  require_source_health: true
  require_release_and_host_identity: true
  require_observation_freshness: true
  stale_or_missing_evidence: "UNKNOWN"
  status: "NOT_TESTED"
  evidence_refs: []
exception_policy:
  require_risk_owner: true
  require_expiry: true
  require_compensating_control_evidence: true
owners:
  application: "Invoice Application Team"
  platform: "Platform Operations"
  assessor: "Security Assurance"
  risk: "Invoice Security Risk Owner"
retest_triggers:
  - "instance-rebuild"
  - "iam-policy-change"
  - "container-runtime-upgrade"
  - "security-incident"
  - "new-host-or-service-identity"
~~~

### Đánh giá control này

Nếu application process là non-root nhưng cloud role vẫn cho phép xóa mọi database backups, control **least privilege chưa đạt**. Nếu không có readback của production hosts, status phải **UNKNOWN**, không tự PASS vì thiết kế YAML hợp lệ.

## 37. JSON host evidence envelope: provenance, freshness và giới hạn

Một observation nên mô tả **trạng thái** và **nguồn chứng cứ**, không sao chép bí mật.

~~~json
{
  "schemaVersion": "1.0",
  "eventType": "host_security_assurance_observation",
  "observationId": "host-obs-example-001",
  "assessmentTime": "2026-11-28T03:00:00Z",
  "host": {
    "assetId": "cloud-instance-example",
    "hostClass": "linux-vm",
    "environment": "production",
    "region": "region-example",
    "service": "invoice-api",
    "lifecycleState": "ACTIVE"
  },
  "controlId": "REQ-HOST-KERNEL-02",
  "expectedState": "VENDOR_FIXED_RUNNING_KERNEL",
  "observed": {
    "installedPatchState": "PATCH_INSTALLED",
    "runningKernelFixedState": "UNKNOWN",
    "activation": "REBOOT_NOT_CONFIRMED"
  },
  "source": {
    "name": "authorized-host-readback",
    "version": "illustrative",
    "health": "OBSERVED",
    "collectorIdentity": "read-only-evidence-agent"
  },
  "result": "UNKNOWN",
  "reason": "Installed package evidence does not establish effective boot state",
  "evidenceRef": "restricted://evidence/host-obs-example-001",
  "containsSecretValues": false
}
~~~

### Vì sao UNKNOWN là kết quả đúng?

Có installed patch nhưng không có readback running kernel/activation; một assessor không thể khẳng định vulnerability fixed. Nếu log source healthy nhưng asset identity không chắc, vẫn chưa đủ evidence. Trường `region-example` và các IDs là placeholders, không mô tả tài sản thật.

### Một schema tốt cần

`asset_id`, `control_id`, `requirement`, `expected`, `observed`, `method`, `source`, `source_version`, `observed_at`, `asset_release`, `scope`, `source_health`, `test_result`, `status`, `evidence_ref` và `limitations`. Nếu lưu secret metadata, không ghi secret value.

## 38. Claim–Argument–Evidence cho Host Security

### Claim mẫu

> “Trong các production hosts và Kubernetes worker nodes thuộc inventory P của Invoice SaaS tại kỳ T, các controls trọng yếu về boot/patch activation, remote management, least privilege, network restrictions và security telemetry đã được triển khai và kiểm chứng hiệu lực theo baseline được phê duyệt; exceptions và evidence gaps được công bố riêng.”

### Argument

1. Population host/roles/service relationships được đối chiếu độc lập.
2. Controls có requirement, version, target class và expected behavior.
3. Firmware/OS/runtime versions và host identities đang hoạt động được xác minh.
4. Remote access, privileges và network paths được kiểm effective state.
5. Detection/audit/EDR sources có health và expected canary outcomes.
6. Patches có evidence activated/fixed theo vendor, không chỉ installed.
7. Negative/compatibility/recovery tests đủ cho critical threat paths.
8. Findings/unknowns/risk exceptions có owner/expiry/retest.
9. Evidence có provenance/timestamp và còn applicable sau rollout.

### Evidence matrix

| Claim element | Stronger evidence | Limited evidence |
| --- | --- | --- |
| All relevant hosts inventoried. | Independent cloud/hypervisor/node inventory reconciliation. | Scanner says all registered devices healthy. |
| Boot trust valid. | Platform-specific effective boot/attestation with policy and freshness. | Firmware checkbox without identity/context. |
| Kernel vulnerability remediated. | Running fixed build + vendor applicability + tests. | Patch installed/package cache. |
| Remote access controlled. | Effective SSH/RDP policy + management path + denied test. | SSH config file only. |
| Privilege scoped. | Effective OS/IAM grants + denied-use test. | Process UID or role name only. |
| Host networking restricted. | Host/cloud firewall + verified reachability. | One firewall rule screenshot. |
| Security telemetry operational. | Canary event to collector + source health + audit integrity. | EDR installed/heartbeat only. |
| Recovery secure. | Clean rebuild/restore drill + identity rotation and tests. | “Backup successful” log. |

### Claim phải có giới hạn

Một node pool được kiểm không chứng minh DR region hoặc physical hypervisor provider-owned cũng đáp ứng cùng control. Nếu control được inherited, cần nguồn supplier assurance tương ứng và giới hạn; không giả định “provider secure” là bằng chứng đủ.

### Không gọi PASS khi hai nguồn mâu thuẫn

Nếu image scanning nói kernel fixed nhưng runtime readback trên một host cho thấy old kernel, không chọn kết quả CI xanh để đóng. Ghi **evidence conflict** và điều tra build/version/host mapping hoặc reboot state.

## 39. Bộ kiểm thử Host Security: positive, negative, failure-mode

Ma trận là **tài liệu học tập**, không phải chỉ thị thực hiện trên production. Các tests cần được chọn theo host type, RoE, asset/data classification, criticality và service availability. Dùng synthetic identities, dedicated test hosts, benign canaries và approved security procedures.

| Test ID | Kịch bản | Expected evidence/outcome |
| --- | --- | --- |
| **HS-T01** | VM inventory thiếu host đang chạy trong cloud account. | Independent reconciliation phát hiện coverage gap. |
| **HS-T02** | Một host được gán hostname/IP tái sử dụng sau rebuild. | Stable instance/asset identity ngăn attribution nhầm. |
| **HS-T03** | Server EOL/unsupported OS xuất hiện ở production. | Asset risk finding, supported replacement/exception. |
| **HS-T04** | Secure Boot flag bật nhưng measured-boot attestation không hợp lệ. | Phân biệt flag và verified trust chain; no false PASS. |
| **HS-T05** | Firmware/UEFI version chưa thỏa vendor prerequisite. | Patch/applicability blocker được ghi. |
| **HS-T06** | OS update installed nhưng running kernel còn phiên bản cũ. | Activation gap và remediation tracking. |
| **HS-T07** | Live patch claimed nhưng không cover affected function/advisory. | Vendor coverage review, effective state chưa verified. |
| **HS-T08** | Một production host bật SSH password authentication ngoài policy. | Effective config + limited denied auth test phát hiện. |
| **HS-T09** | SSH config file đúng nhưng Match/Include override sai. | Effective daemon/context check phát hiện. |
| **HS-T10** | Remote admin không qua bastion do cloud console path. | Host access map/permissions review ghi alternate path. |
| **HS-T11** | Local admin account orphan sau nhân viên rời nhóm. | Joiner/mover/leaver reconciliation và revocation. |
| **HS-T12** | Service account non-root vẫn có dangerous capabilities. | Effective privilege assessment FAIL. |
| **HS-T13** | Windows local Administrators group chứa nested broad domain group. | Effective membership review phát hiện gap. |
| **HS-T14** | RDP/WinRM truy cập ngoài approved network. | Firewall/remote management policy + bounded test. |
| **HS-T15** | SELinux/AppArmor profile tồn tại nhưng process unconfined. | Enforcement/coverage audit không PASS. |
| **HS-T16** | Host firewall có rule nhưng IPv6/interface phụ bypass. | Effective network paths test phát hiện. |
| **HS-T17** | Cloud firewall private nhưng host có management port public qua route khác. | Cross-layer reachability/asset mapping. |
| **HS-T18** | Egress từ test workload tới forbidden canary. | Deny theo approved network control. |
| **HS-T19** | Host secret file world-readable theo ACL trong test fixture. | Permission/control FAIL, không copy secret value. |
| **HS-T20** | Secret manager rotate nhưng stale credential vẫn accepted. | Revocation/use test phát hiện chưa effective. |
| **HS-T21** | Disk encryption enabled nhưng snapshot bị share rộng. | Effective snapshot/IAM policy finding. |
| **HS-T22** | Crash dumps chứa canary sensitive marker ngoài retention policy. | Dump privacy/access test FAIL. |
| **HS-T23** | Audit service running nhưng canary event không tới SIEM. | Source/collector health FAIL/UNKNOWN. |
| **HS-T24** | EDR agent service healthy nhưng security test event không được ghi. | Operating effectiveness gap; no false PASS. |
| **HS-T25** | Host clock lệch vượt accepted tolerance. | Audit/time sync finding, freshness recalculated. |
| **HS-T26** | File integrity tool phát hiện thay đổi approved config ngoài change window. | Traceable alert, owner và root-cause investigation. |
| **HS-T27** | Container workload dùng hostPath/docker socket ngoài permission baseline. | Pod/node runtime control finding. |
| **HS-T28** | Node pool image đã fixed nhưng một old node vẫn chạy workload. | Per-node runtime/placement gap PARTIAL. |
| **HS-T29** | Kubernetes patch drain gây thiếu quorum trong sandbox. | Controlled stop, recovery/availability gate. |
| **HS-T30** | EDR agent không hỗ trợ kernel version mới. | Compatibility gate/telemetry readiness FAIL. |
| **HS-T31** | CI runner từ untrusted job được cấp deploy credential. | Isolation/secret access negative test FAIL. |
| **HS-T32** | Artifact scan green nhưng build host provenance không đúng. | Supply-chain assertion pending/inconclusive. |
| **HS-T33** | Restored VM mang old local key đã revoke. | Identity cleanup và old-key denial test. |
| **HS-T34** | Backup job succeeded nhưng test restore không giải mã được. | Recovery assurance FAIL. |
| **HS-T35** | Một host bị terminate nhưng disk/snapshot còn accessible ngoài scope. | Decommission lifecycle finding. |
| **HS-T36** | Source collector mất quyền trong một production region. | UNKNOWN coverage, independent population reconciliation. |
| **HS-T37** | Golden image policy đạt nhưng emergency instance dùng unapproved image. | Image provenance/exception finding. |
| **HS-T38** | A host receives policy after rollout but process did not reload. | Effective loaded/running configuration drift. |
| **HS-T39** | Rollback kernel/image làm vulnerability cũ tái xuất hiện. | Finding reopened và residual risk assessed. |
| **HS-T40** | Security canary PASS nhưng unauthorized admin path vẫn active. | Coverage limitation/alternate-path test detects. |

### Một test record đầy đủ

Ví dụ **HS-T06**:

- **Requirement:** production nodes affected by advisory A must use fixed effective kernel.
- **Host identity:** immutable instance/node ID, environment, region, service, release.
- **Preconditions:** package update applied, reboot may be pending.
- **Expected:** running kernel/build matches vendor fixed state.
- **Observed:** actual kernel version, package build, boot identifier, reboot time.
- **Decision:** PASS nếu applicability/readback đạt; PARTIAL/FAIL nếu fix chưa active; UNKNOWN nếu source lỗi.
- **Evidence:** vendor advisory, host readback time, collector/source, change ticket, service health.
- **Owner:** platform team, reviewer/retest authority theo policy.

Không được coi việc host “có package mới trên disk” là PASS nếu requirement yêu cầu running kernel; cũng không nên dùng phiên bản upstream để kết luận vendor backport sai.

### Ý nghĩa của negative tests

Negative tests không có nghĩa phải thử phá hệ thống. Có thể là **denied login bằng test account, denied secret access bằng test service role, forbidden canary egress hoặc policy rejection of a synthetic privileged container**. Kết quả an toàn hơn và dễ lặp lại hơn thử khai thác thật trên production.

## 40. Case study: Invoice SaaS và Host Security Assurance

### 40.1. Kiến trúc giả định

Invoice SaaS có hai Kubernetes regions, một bastion host, một nhóm Windows build runners, các Linux VMs cho export worker đặc thù, managed database và object storage. Data flow:

~~~mermaid
flowchart LR
    U["Customer / API client"] --> IN["Gateway / ingress"]
    IN --> API["Invoice API pods on worker nodes"]
    API --> DB["Managed database"]
    API --> Q["Export job queue"]
    Q --> WK["Linux export worker VM"]
    WK --> ST["Private export storage"]
    OPS["Ops identities"] --> PAM["Bastion / JIT management"]
    PAM --> API
    PAM --> WK
    CI["Windows/ephemeral build runners"] --> ART["Artifact registry"]
    ART --> API
    ART --> WK
    API --> SOC["Audit + EDR / SIEM"]
    WK --> SOC
    CI --> SOC
~~~

### 40.2. Security objectives

| Requirement | Target | Method |
| --- | --- | --- |
| **HOST-REQ-01** | All production guest OS/kernel versions supported and fixed for applicable advisories. | Per-host vendor mapping, effective kernel/reboot readback. |
| **HOST-REQ-02** | Remote admin only via approved identities/routes. | Effective access map, PAM/OS/network checks. |
| **HOST-REQ-03** | Workload host privileges least required. | Process UID/capabilities, IAM and host mount review. |
| **HOST-REQ-04** | Sensitive data protected on disks/snapshots/temporary files. | Effective encryption, permissions and retention. |
| **HOST-REQ-05** | Host EDR/audit events delivered with trusted timestamps. | Canary events, source health, coverage reconciled. |
| **HOST-REQ-06** | Builds originate from approved runners and produce attested artifacts. | Build runner identity, provenance and digest mapping. |
| **HOST-REQ-07** | Recovery/rebuild returns hosts to trusted, patched state. | Restore/rebuild drill + rotation and functional tests. |

### 40.3. Mười findings giả định

| ID | Observation | Đánh giá ban đầu |
| --- | --- | --- |
| **F-HS-01** | Một Linux export VM vẫn dùng running kernel cũ sau installed update. | Confirmed activation gap; risk theo advisory/exposure. |
| **F-HS-02** | Bastion policy yêu cầu keys nhưng một VM cho SSH password từ management subnet rộng. | Remote access deviation; cần actual authorization test. |
| **F-HS-03** | Worker process non-root nhưng có quyền đọc tất cả export buckets qua VM cloud role. | Least-privilege gap, possible increased blast radius. |
| **F-HS-04** | EDR registration báo healthy nhưng host này không tạo event tại SIEM. | Telemetry operating-effectiveness gap. |
| **F-HS-05** | Một worker node pool dùng old OS image, workloads vẫn được schedule. | Partial patch rollout; affected node inventory. |
| **F-HS-06** | Break-glass local admin account chưa rotate sau incident drill. | Credential lifecycle finding; current validity cần xác minh. |
| **F-HS-07** | Build runner còn cache credentials từ privileged deployment stage. | Potential CI host isolation/secret exposure. |
| **F-HS-08** | Daily backup job success nhưng restore drill lỗi key unavailable. | Recovery assurance FAIL. |
| **F-HS-09** | Former export VM đã terminate nhưng attached snapshot được share sai scope. | Data-at-rest/IAM remanence risk. |
| **F-HS-10** | Inventory từ EDR bỏ 12 ephemeral nodes của region B. | Incomplete denominator, cannot claim 100% coverage. |

### 40.4. Không biến deviation thành exploit story

F-HS-03 không tự chứng minh attacker đã lấy được customer exports; nó cho thấy **effective privilege quá rộng** và có thể tăng blast radius. F-HS-04 không chứng minh EDR đã bị bypass do malware; nguồn log có thể lỗi network/parser. F-HS-08 chứng minh **recovery test thất bại theo scenario**, không suy mọi backups đều unusable.

### 40.5. Triage theo rủi ro và phụ thuộc

**Immediate containment** có thể gồm giới hạn SSH exposure, tạm thu hẹp VM role, xác minh access anomalies và bảo vệ snapshots, với owner approval. **Permanent remediation** gồm fixed kernel activation, node pool replacement, EDR pipeline repair, clean build runner isolation, tested key/restore procedure và stable inventory.

**Patch priority** khác **execution sequence**: một kernel fix cấp bách nhưng reboot critical nodes phải tuân quorum/capacity constraints. Thay đổi IAM có thể khiến export workers mất quyền cần thiết; phải test functional and denied actions. Không hy sinh kiểm chứng data integrity để đổi trạng thái dashboard nhanh.

### 40.6. Remediation plan minh họa

1. Reconcile toàn bộ host population từ cloud/cluster/VM inventory, so với EDR registrations.
2. Assign owner và classify risk theo protected data, identity privilege, external exposure.
3. Xác minh vendor advisories, actual running kernel/firmware và patch prerequisites.
4. Apply controlled OS/node updates với canary, drain/quorum và reboot verification.
5. Siết SSH/bastion/JIT access, revoke stale break-glass credential theo policy.
6. Review VM/service cloud IAM và test allowed/denied actions trong synthetic environment.
7. Khôi phục audit/EDR source-health và verify benign canary event to SIEM.
8. Restrict old snapshots/backup, validate encrypted restore và key availability.
9. Tách trusted production build runners khỏi untrusted code jobs, trace artifact provenance.
10. Verify actual host state, workloads, CI artifacts và security/availability regression tests.
11. Reassess remaining residual risk/exceptions, close only verified findings.

### 40.7. Retest matrix

| Finding | Closure evidence | Tình trạng ví dụ |
| --- | --- | --- |
| F-HS-01 | Running fixed kernel, effective advisory applicability, service health. | PENDING |
| F-HS-02 | Effective SSH policies, bounded denied access from unauthorized viewpoint. | PENDING |
| F-HS-03 | Role/resource grants and synthetic denied-use + permitted functionality. | PENDING |
| F-HS-04 | Canary security event arrives SIEM with correlation/timestamps; source healthy. | PENDING |
| F-HS-05 | Per-node fixed image/kernel and workloads placement reconciled. | PENDING |
| F-HS-06 | Credentials rotated/revoked, emergency workflow tested, audit. | PENDING |
| F-HS-07 | Isolated runners, secrets not exposed, build provenance verified. | PENDING |
| F-HS-08 | Verified restore, valid keys, integrity and RPO/RTO observations. | PENDING |
| F-HS-09 | Snapshot access reviewed/restricted, retention/deletion according policy. | PENDING |
| F-HS-10 | Independent host inventory complete with EDR/collector mapping. | PENDING |

**PENDING** là trạng thái đúng bởi case study chỉ có dữ liệu giả định; không có thao tác kiểm thử runtime thật.

### 40.8. Kết luận assurance có điều kiện

> “Các baseline host security đã được xác định, nhưng inventory độc lập và observations cho thấy các lỗ hổng coverage/operating effectiveness ở patch activation, remote access, IAM, EDR, recovery và supply-chain hosts. Chưa đủ bằng chứng công bố toàn bộ production hosts compliant. Cần hoàn thành remediation/retest trên từng affected asset và đánh giá residual risk theo thẩm quyền.”

Một kết luận như vậy có ích vì nêu **scope, loại bằng chứng, gaps, next actions** và không biến các giả thuyết root cause thành sự thật đã được xác minh.

## 41. Measurement: KPI/KRI cho Host Security Assurance

Metrics nên tách **coverage, control effectiveness, data confidence và risk exposure**, thay vì chỉ cung cấp “Host compliance score”.

| Metric ID | Định nghĩa | Giới hạn/cảnh báo |
| --- | --- | --- |
| **HS-M01 Asset discovery coverage** | Independently known eligible hosts có active identity/inventory mapping / eligible population. | Mẫu số thiếu khiến 100% giả. |
| **HS-M02 Approved baseline coverage** | Required host classes có applicable approved baseline / required classes. | Baseline tồn tại không có nghĩa applied. |
| **HS-M03 Effective patch coverage** | Affected hosts chạy vendor-fixed state đã verified / in-scope affected hosts. | Installed package chưa tính fixed. |
| **HS-M04 Unsupported OS exposure** | Số/criticality/tuổi EOL hosts trong active population. | Không chỉ đếm, xét Internet/privileged exposure. |
| **HS-M05 Secure boot/attestation coverage** | Applicable hosts với valid boot evidence / applicable hosts. | Một flag không bằng remote attestation. |
| **HS-M06 Remote admin policy conformance** | Management paths effective và approved / in-scope paths. | Chỉ SSH không phủ cloud console. |
| **HS-M07 Privilege review coverage** | Critical host identities/roles có effective grants review / required identities. | Membership không tự bằng access denial. |
| **HS-M08 Excessive privilege findings** | Confirmed risky broad grants theo asset/risk tier. | Không suy exploit đã xảy ra. |
| **HS-M09 Network exposure coverage** | Required routes/ports được verified theo policy / route population. | Host scan snapshot bỏ ephemeral paths. |
| **HS-M10 EDR/sensor operating coverage** | Eligible hosts với valid sensor policy và delivered canary/source health / all eligible hosts. | Agent installed không tự PASS. |
| **HS-M11 Security audit completeness** | Expected event sources/canary types được thu đúng window / required sources. | Clock/collector gaps cần tách. |
| **HS-M12 Evidence freshness** | Material host observations trong approved SLA / required observations. | Critical dynamic controls cần cadence phù hợp. |
| **HS-M13 Host drift detection latency** | Time from unauthorized change to confirmed detection, by criticality. | Source lag và timestamps đáng tin. |
| **HS-M14 Host drift remediation latency** | Time from confirmed drift to verified effective fix. | Ticket close khác runtime retest. |
| **HS-M15 Patch activation gap** | Hosts installed patch nhưng chưa boot/load fixed state / hosts requiring activation. | Live patch cases cần vendor-specific criteria. |
| **HS-M16 Host recovery test effectiveness** | Required recovery scenarios đạt restore/rebuild/security checks / scenarios đến hạn. | Backup success không là restore success. |
| **HS-M17 Build host trust coverage** | In-scope CI runners với approved image/identity/provenance / runners được xác định độc lập. | Untrusted jobs và privileged signing phải phân nhóm. |
| **HS-M18 Exceptions overdue** | Open exceptions hết hạn, theo impact/owner. | Exception không là security PASS. |
| **HS-M19 Host decommission completeness** | Terminated assets đã revoke identities, xử lý disks/snapshots/records / assets đến hạn. | Terminated instance vẫn có residual data. |
| **HS-M20 Effective negative-test coverage** | Threat-driven host control scenarios có valid observed results / required scenarios. | Test PASS chỉ theo scope/preconditions. |

### Ví dụ coverage

Giả sử cloud/cluster inventory xác định **200 eligible hosts**; 180 có agent reported healthy, 10 agent unhealthy, 10 không được agent quản. Không được báo “100% EDR” bằng 180/180. Tối thiểu phải công bố **registration coverage 190/200** nếu 10 unhealthy vẫn registered, và **operating sensor coverage chỉ được xác minh đối với số host có policy/canary evidence đầy đủ**.

### Không dùng một tỷ lệ thay risk

Một signing host bị compromise có thể gây hậu quả lớn hơn nhiều ordinary workers. Metrics cần phân tầng theo business criticality, privilege, data sensitivity và effective exposure. **Critical gate failure không được trung bình hóa**.

### Precision/uncertainty

Một scanner quét được 100 hosts nhưng 25 hosts có stale observations không được xem như 100 valid observations. Báo riêng **PASS, FAIL, PARTIAL, UNKNOWN, N/A, accepted exceptions** và source health.

## 42. Evidence quality, bảo mật dữ liệu và độ tin cậy của nguồn đo

Một host security report có thể chứa OS versions, usernames, nội bộ network topology, file paths, privileged service identities và vulnerability details. Evidence cần đủ để xác minh control nhưng không tạo **một kho thông tin nhạy cảm mới thiếu bảo vệ**.

| Quality | Câu hỏi đánh giá |
| --- | --- |
| **Relevance** | Evidence hỗ trợ đúng control, host, version và requirement? |
| **Completeness** | Bao phủ toàn asset population, regions, rings và host classes? |
| **Accuracy** | Observed kernel/user/capabilities/policy đúng effective state? |
| **Freshness** | Thu sau thay đổi cấu hình/patch/role cuối cùng liên quan? |
| **Provenance** | Tool/source/collector identity, version, host ID và timestamp rõ? |
| **Integrity** | Có audit trail hoặc cơ chế phát hiện sửa/xóa report? |
| **Repeatability** | Có safe method/expected outcome để authorized assessor chạy lại? |
| **Independence** | Có source khác kiểm chéo critical claims? |
| **Confidentiality** | Raw secrets/customer data đã tránh thu hoặc redact? |
| **Limitations** | Unknown hosts, inaccessible controls, provider-inherited assumptions rõ? |

### Source trust là một giả định cần kiểm

Một compromised host có thể tự báo “healthy” cho collector; do đó các claims quan trọng có thể cần **independent cloud control-plane evidence, boot attestation, immutable remote logs hoặc behavior tests** thay vì chỉ tin agent trong host.

### Tách collector health khỏi policy health

Collector có thể nhận heartbeat nhưng không thấy event loại cần kiểm do cấu hình, schema drift hoặc route sai. Trạng thái **source alive** không đồng nghĩa **security sensor effective**. Dùng canary end-to-end và reconciliation.

### Bảo vệ kho evidence

Chỉ lưu allowlisted metadata và redacted test artifacts; hạn quyền theo project/incident; theo dõi người đọc/sửa; giữ retention, deletion và legal hold theo chính sách. Không tải toàn bộ hosts' environment, SSH private keys, credential stores hoặc memory dumps vào issue tracker để chứng minh posture.

### Hash không chứng minh kết luận đúng

Checksum giúp xác nhận một tệp evidence không đổi sau khi thu; nó không chứng minh host ID đúng, collector không bị compromise, baseline phù hợp threat hay source có coverage. Assurance phải đánh giá cả **cách thu, nguồn và security argument**.

## 43. Ownership, RACI và separation of duties

Host security có thể trải qua OS, platform, network, IAM, EDR, CI/CD, business service và nhà cung cấp cloud. Không nên để một finding thiếu owner vì “không thuộc team nào”.

| Vai trò | Trách nhiệm |
| --- | --- |
| **Business/service owner** | Tài sản/criticality/SLO và risk objectives; chấp nhận impact của thay đổi. |
| **Host/OS operations** | OS baseline, accounts, services, patch activation, repair/rebuild. |
| **Cloud/virtualization owner** | VM/control-plane privileges, snapshots, cloud images, virtual networks. |
| **Kubernetes/platform owner** | Node pool, kubelet/runtime, workloads scheduling, admission, capacity. |
| **Identity/PAM owner** | Admin paths, JIT, break-glass, credential lifecycle. |
| **Security architecture/AppSec** | Host threat model, control design, accepted hardening patterns. |
| **EDR/SOC owner** | Agent coverage, detection sources, response escalation và telemetry integrity. |
| **Backup/DR/data owner** | Recovery, key availability, snapshot/backup protection, test restore. |
| **CI/CD/supply-chain owner** | Runner isolation, build host trust, signatures/provenance. |
| **Security assurance assessor** | Evidence completeness, qualified PASS/FAIL, independent challenge/retest. |
| **Risk owner** | Residual risk acceptance, exceptions theo thẩm quyền. |

### RACI minh họa

**R:** Responsible — thực hiện. **A:** Accountable — chịu trách nhiệm cuối cùng. **C:** Consulted — tham vấn. **I:** Informed — được thông báo.

| Hoạt động | OS/Platform | Security | SOC | Assurance | Risk owner |
| --- | :---: | :---: | :---: | :---: | :---: |
| Host baseline và patch compatibility | **A/R** | C | I | C | I |
| Threat/requirement mapping | C | **A/R** | C | C | I |
| Inventory/privilege/net readback | **A/R** | C | R | C | I |
| EDR canary và source health | C | C | **A/R** | C | I |
| Host remediation/rebuild | **A/R** | C | C | I | I |
| Independent evidence/retest review | C | C | C | **A/R** | I |
| Business risk/exception acceptance | C | C | C | C | **A/R** |

### Thẩm quyền phải rõ

Người làm host patch không tự nhận quyền **chấp nhận mọi residual risk**. Người giữ break-glass credentials không nên tự kiểm toán việc dùng chúng mà không có oversight. Với high-impact controls, cần separation of duties hoặc compensating independent review theo governance.

### Shared responsibility

Với provider-managed infrastructure, xác định role owner theo hợp đồng. Đơn vị nội bộ vẫn cần **owner để theo dõi inherited evidence/assurance gaps**, không bỏ trống chỉ vì provider vận hành phần cứng.

## 44. Exception và residual risk khi host không thể đáp ứng baseline

Một host legacy có thể không hỗ trợ Secure Boot, một appliance không hỗ trợ EDR, hoặc một driver phụ thuộc kernel cũ. Các trường hợp này không nên bị “sửa” bằng cách đánh dấu compliant.

### Exception record cần

1. Exact asset(s), host class, environment, account/region, service/data classification.
2. Security requirement/baseline control chưa đạt và technical evidence.
3. Vulnerability/threat, attack preconditions, impact và exposure.
4. Nguyên nhân không thể áp baseline ngay: vendor compatibility, business availability hoặc design constraint.
5. Existing effective controls và evidence.
6. Interim mitigations: segmentation, restricted admin, compensating telemetry, isolation hoặc replacement strategy.
7. Tests chứng minh interim controls có hiệu lực theo threat.
8. Owner thực hiện, risk owner/approval authority, due date/expiry.
9. Remediation/replacement plan, milestones và validation criteria.
10. Reassessment triggers: known exploitation, incident, Internet exposure, new version, role change.
11. Regulatory/contractual implications với chuyên trách phù hợp.
12. Điều kiện đóng exception khi fix/retest thành công.

### Không dùng “accepted” thay “secure”

**ACCEPTED_RISK** chỉ nói risk được chấp thuận trong phạm vi/thời hạn; yêu cầu kỹ thuật có thể vẫn chưa đạt. Nếu benchmark tool report host là noncompliant nhưng exception hợp lệ, trình bày **technical status + exception status** riêng.

### Compensating control cũng phải đo

Một VM không thể lên kernel mới và được đặt trong isolated subnet; cần xác minh **routes/egress, identity and lateral movement restrictions**, không chỉ ghi “isolated network” trong ticket. Nếu bypass mới xuất hiện, phải đánh giá lại exception ngay.

### Tránh waiver vô thời hạn

Một exception không expiry/owner/monitoring có thể trở thành cấu hình thường trực trái risk appetite. Rà lại theo criticality và threat landscape, không đợi một cuộc audit định kỳ nếu incident/exploit signals thay đổi.

## 45. Host compromise, incident response và trusted recovery

Một số security incidents khiến ta **không thể tin hoàn toàn evidence từ host nghi bị compromise**. Đó là lúc assurance phải kết hợp incident response, forensic preservation và clean rebuild.

### Trình tự khái niệm

~~~mermaid
flowchart TD
    A["Suspicious host telemetry / confirmed indicator"] --> B["Incident triage and authorization"]
    B --> C["Contain host/network/identities safely"]
    C --> D["Preserve minimal forensic evidence under policy"]
    D --> E["Assess compromise scope and trust of observations"]
    E --> F["Revoke/rotate credentials and tokens"]
    F --> G["Rebuild from approved image or trusted recovery"]
    G --> H["Verify boot, OS, patches, IAM, services and EDR"]
    H --> I["Restore and reconcile approved data/workloads"]
    I --> J["Reintegrate with monitoring and positive/negative tests"]
    J --> K["Update risk, findings and assurance claims"]
~~~

### Tại sao không chỉ “clean malware and return”?

Một attacker có privilege đủ có thể đổi configs, accounts, binaries, kernel modules, scheduled tasks hoặc audit sources. Nếu không thể xác minh integrity, **rebuild từ nguồn tin cậy** có thể cho mức assurance cao hơn cố sửa từng file, tùy incident plan/platform.

### Containment an toàn

Không tự tắt host đang giữ database quorum hoặc services quan trọng mà không theo incident authority, SLO constraints và recovery plan. Cần phối hợp SOC, platform, data owner và business. Bảo quản evidence khi cần cho điều tra nhưng tránh thu dữ liệu khách hàng vượt mục đích.

### Recover không đồng nghĩa security restored

Sau restore, cần verify **host identity/re-enrollment, patch effective version, secure boot/integrity khi áp dụng, admin/session credentials, cloud/IAM grants, network controls, EDR audit canary và data integrity**. Không dùng “VM boot successful” làm closure.

## 46. Continuous host assurance và trigger cập nhật

Host landscape đổi liên tục: cloud autoscaling, VM replacement, Kubernetes node rotation, vendor patches, IAM grants, emergency access, agent health, CI runner lifecycle và vulnerability advisories.

### Các trigger quan trọng

- Host/VM/node được create, replace, migrate hoặc decommission.
- Golden image, kernel, firmware, hypervisor/guest agent hoặc driver upgrade.
- Host process/service/capability, SSH/RDP/PAM policy thay.
- Cloud IAM role/metadata settings, snapshot/backup permissions đổi.
- Host/network firewall, CNI/ingress hoặc out-of-band management exposure đổi.
- New endpoint/EDR agent version, source health loss, alert rule update.
- Build runner/image/signing identity và CI secrets scope thay.
- Known exploited vulnerability, pentest finding, incident/forensic alert.
- Backup/restore/recovery test failure, key rotation hoặc recovery role update.
- Exception tới hạn hoặc threat model thay vì new asset/data classification.

### Control loop

~~~mermaid
flowchart TD
    A["Approved host baseline and independent inventory"] --> B["Event-driven / scheduled host assessment"]
    B --> C["Collect boot, OS, privilege, net, storage and audit states"]
    C --> D["Reconcile asset ID, source health and evidence freshness"]
    D --> E{"Required controls verified effective?"}
    E -- "PASS within scope" --> F["Versioned assurance record"]
    E -- "FAIL or PARTIAL" --> G["Finding, risk treatment, owner, fix"]
    E -- "UNKNOWN" --> H["Source repair / additional test / escalation"]
    G --> I["Approved patch/rebuild/policy change"]
    H --> C
    I --> C
    F --> J["Monitor drift, new assets, incident and exception expiry"]
    J --> B
~~~

### Hai cách thu bằng chứng bổ sung

**Event-driven:** phát hiện host new/delete, kernel update, policy changes, agent disconnect và identity grants gần thời gian thực. Rủi ro là missed/out-of-order events, collector permissions và queue lag.

**Periodic independent reconciliation:** định kỳ đối chiếu active host population từ nguồn khác để phát hiện assets/events bị bỏ sót. Rủi ro là khoảng trống giữa hai snapshots. Kết hợp cả hai giúp nâng confidence.

### Không phản ứng tự động mù quáng

Auto-isolation/reboot có thể phá availability/quorum hoặc forensic evidence. Policy cần **risk-tiered automation, safe stop criteria, exception handling, incident authority và rollback**, không mặc định mọi deviation đều lập tức kill VM.

### Host assurance là một claim có thời hạn

Ngày T, host H có thể đạt policy; ngày T+1, node mới được autoscale từ image cũ hoặc IAM permission thay. Evidence phải có **as-of timestamp, applicability, release/host identity và triggers** để người đọc không xem PASS là vĩnh viễn.

## 47. Dùng standards và baselines đúng cách

Các tài liệu như **CIS Benchmarks**, vendor security baselines, **NIST SP 800-53** (những control families liên quan configuration, access control, auditing, system integrity, recovery) và hướng dẫn hardening của nhà cung cấp có thể giúp lập host requirements. Tuy nhiên, **chọn benchmark/phiên bản phải phù hợp host class, workload, compliance obligations và operational constraints**.

### Ba lớp không được nhầm

1. **External guidance:** gợi ý security settings, control objectives hoặc measurement patterns.
2. **Organization-approved baseline:** mapping guidance tới threat/risk/requirements và exceptions hợp lệ.
3. **Operating evidence:** host thực thi control và behavior tests đạt trong scope/time.

### Ví dụ

Một benchmark đề xuất disable một kernel feature để giảm attack surface. Ứng dụng dùng feature đó cho container networking. Đội vận hành không nên bật/tắt một cách mù quáng; cần **compatibility review, threat impact, supported mitigation, exception/risk owner** và test theo phiên bản/platform.

### Không tự tuyên bố compliance

“CIS scan đạt 90%” không có nghĩa tổ chức đã đáp ứng tất cả yêu cầu của một certification hoặc regulatory regime. Cần nêu **benchmark edition/version/profile, applicability, assessed population, control failures, inherited controls, exceptions, evidence quality và audit authority**.

### Hệ thống managed

Nếu provider điều hành host OS và không cấp kernel access, có thể đánh giá **supplier assurance/inherited controls** đúng phạm vi và phần customer còn quản được. Không tạo report root-level host hardening giả bằng một agent chạy bên trong application container.

## 48. Anti-patterns và những ngộ nhận Host Security

| Anti-pattern | Vấn đề | Cách cải thiện |
| --- | --- | --- |
| **Host scanner green = hosts secure** | Scope/permissions/rules có thể thiếu. | Independent inventory và source-health tests. |
| **Installed patch = running fix** | Kernel/process chưa reboot/reload. | Running version/vendor evidence và retest. |
| **Newest upstream version là thước đo duy nhất** | Vendor backports/revision semantics khác. | Distribution-specific advisory mapping. |
| **SSH port closed = no remote admin** | Cloud console, bastion bypass, Kubernetes exec. | Host access map nhiều mặt phẳng. |
| **Password disabled in file = effective** | Include/Match/service config overrides. | Effective daemon config + bounded negative test. |
| **Local users ít = least privilege** | Cloud IAM/role assumption và service capabilities. | Effective OS + cloud resource grants. |
| **Non-root = host isolated** | Runtime socket/host mounts/capabilities vẫn mạnh. | Cross-layer host/pod/IAM analysis. |
| **One firewall rule means segmentation** | IPv6, CNI, routes, peer settings bỏ sót. | Effective policy + controlled reachability. |
| **Encrypted disk = privileged actor không đọc được** | Volume unlocked trong runtime. | Identity, memory/secrets controls và audit. |
| **Kubernetes Secret = encryption hoàn toàn** | Encoding/permissions/etcd/API scope chưa đủ. | Encryption/access/rotation theo platform. |
| **TPM installed = trustworthy host** | Attestation, reference measurements, freshness chưa có. | Full platform-specific trust argument. |
| **Secure Boot enabled = no malware** | Runtime compromise vẫn có thể. | Defense in depth, integrity, EDR. |
| **EDR service running = detection works** | Telemetry có thể không đến SIEM. | Benign canary và source-health correlation. |
| **No alerts = no incidents** | Sensor gaps hoặc detection missing. | Coverage/telemetry evidence và threat analysis. |
| **Backup success = recoverable** | Key/restore không hoạt động hoặc image bị nhiễm. | Restore/rebuild drills và security tests. |
| **Snapshot attached to no VM = deleted** | Historical data có thể vẫn tồn tại/share. | Inventory/retention/decommission controls. |
| **Golden image compliant forever** | Runtime drift và old autoscale pool. | Per-instance re-evaluation/events. |
| **Cloud provider manages everything** | Guest OS/IAM/config vẫn thuộc customer. | Shared responsibility mapping. |
| **One host PASS = all nodes PASS** | Mixed node pools/regions/DR. | Per-population runtime readback. |
| **Exception approved = technically fixed** | Control gap còn tồn tại. | Technical status và risk decision riêng. |
| **CI runner only builds, not security critical** | Supply-chain/signing/deploy credentials rủi ro cao. | Runner isolation/provenance/identity. |
| **Hardening bằng cách kill mọi service** | Có thể phá availability/audit. | Risk-based baseline và compatibility tests. |
| **Copy all environment to ticket** | Lộ production secrets. | Allowlisted metadata và protected evidence. |
| **One global host score** | High-value privileged host có thể bị che. | Criticality stratification/gates. |
| **Rollback recovers security** | Old vulnerable image/account có thể quay lại. | Reopen finding, rotate credentials, retest. |

### Năm câu hỏi cần đặt khi nghe “host đã hardened”

**Host nào và phiên bản nào?** **Control nào đã được approve?** **Effective process/kernel/identity/network state là gì?** **Ai thu evidence khi nào, từ nguồn có khỏe không?** **Có negative test, ngoại lệ hoặc unassessed hosts không?**

Nếu không trả lời được, status phù hợp có thể là **PENDING/UNKNOWN**, không nên tạo một “certified secure” report.

## 49. Checklist đánh giá Host Security có bằng chứng

Checklist dưới đây hỗ trợ đánh giá theo rủi ro; mỗi dòng cần **PASS, FAIL, PARTIAL, UNKNOWN hoặc NOT APPLICABLE có lý do**, evidence ref, owner và recheck trigger.

1. **Authorization/scope:** quyền đánh giá, RoE, targets và test methods rõ?
2. **Business service:** host hỗ trợ capability/data nào và thuộc risk tier nào?
3. **Inventory:** cloud/hypervisor/Kubernetes/CMDB có reconciliation độc lập?
4. **Host identity:** instance/node ID ổn định, lifecycle, owner, region, release?
5. **OS support:** distribution/build/channel trong vendor supported lifecycle?
6. **Firmware/boot:** UEFI/Secure Boot/TPM requirements áp đúng hardware/VM?
7. **Attestation:** nếu dùng, freshness/reference/verifier/host binding hợp lệ?
8. **Kernel activation:** running fixed version, not only installed patch?
9. **Driver/firmware dependencies:** prerequisites và activated states được xét?
10. **Local identities:** orphan/default/shared accounts và service account purpose?
11. **Admin privileges:** OS groups/sudo/UAC và cloud privileged grants đúng?
12. **Remote management:** SSH/RDP/WinRM/bastion/console paths được inventory?
13. **Credential methods:** public-key/certs/MFA/JIT/session controls theo policy?
14. **Break-glass:** custody, alert, approved test, post-use rotation?
15. **Services/ports:** chỉ các services có purpose/owner và exposure approved?
16. **Host firewall:** IPv4/IPv6/interfaces/host cloud overlay rules effective?
17. **Egress:** critical destinations/metadata services constrained theo threat?
18. **Linux hardening:** file perms/capabilities/sudo/kernel settings tương thích?
19. **Windows hardening:** resultant policy, local admins, endpoint/firewall effective?
20. **MAC controls:** SELinux/AppArmor mode, profiles, unconfined exceptions?
21. **VM/hypervisor:** cloud console/instance profile/snapshot control-plane rights?
22. **Container host:** kernel/runtime/socket/host mounts/capabilities isolation?
23. **Kubernetes nodes:** node pool images/version skew/placement/patch/agents?
24. **CI/CD hosts:** runner isolation, untrusted inputs, secrets và provenance?
25. **Encryption at rest:** disks/swap/dumps/snapshots and key policy đúng?
26. **Secrets:** store/access/rotation/revoke, no raw dumps in diagnostics/logs?
27. **Build & file integrity:** trusted packages/binaries/images and change monitoring?
28. **EDR:** agent and policy coverage, approved canary, source-health verified?
29. **Audit:** auth, privilege, package, config, incident events delivered correctly?
30. **Time:** host sync/clock quality và correlation đủ theo SLA?
31. **Monitoring gaps:** stale sensors, missed hosts, source permissions báo UNKNOWN?
32. **Patch treatment:** risk priority, upgrade dependencies, canary, reboot/restart?
33. **Recovery:** backup encryption/key/restore/rebuild, RPO/RTO test?
34. **Decommission:** revoke identities, disks/snapshots and residual data handling?
35. **Evidence provenance:** source/tool/version/asset/time/collector identity rõ?
36. **Evidence security:** reports có hạn quyền, redaction, retention đúng?
37. **Requirements:** controls map threats, security objectives và ownership?
38. **Negative tests:** forbidden access/network/action bị deny trong valid fixture?
39. **Config drift:** actual runtime so với approved baseline, owner và change ID?
40. **Exceptions:** risk owner/scope/expiry/mitigation và retest criteria rõ?
41. **Deployment:** fixed image/runtime có hiệu lực trên all in-scope hosts/rings?
42. **Incident readiness:** containment, forensic preservation, clean recovery?
43. **Continuous assessment:** new host/config/patch/role/incident triggers?
44. **Claim conclusion:** PASS chỉ trong asset population/time/evidence thực?

### Ví dụ không nên chấm PASS

Nếu 3 trong 40 critical nodes không có EDR telemetry vì không được inventory, không chấm **100% EDR** trên 37 nodes còn lại. Nếu host patch đã cài nhưng chưa reboot, ghi **activation pending**. Nếu cloud provider chịu host OS nhưng chưa có supplier assurance evidence, ghi **provider-inherited evidence pending**, không giả lập local root test.

## 50. Bài tập tình huống và gợi ý giải

### Bài tập A — Installed update nhưng running kernel cũ

VM đã cài security update; CMDB và patch tool báo “Patched”, nhưng runtime kernel vẫn ở bản bị advisory ảnh hưởng.

**Gợi ý:** Phân biệt installed vs activated; tra vendor fix/build và reboot/live-patch semantics, kiểm effective kernel, lập maintenance/availability plan, retest sau activation. Trạng thái hiện tại chưa VERIFIED_FIXED.

### Bài tập B — SSH config đúng nhưng remote login vẫn sai policy

File cấu hình chính disable password login, song một Match block trong include file cho phép password từ một network rộng.

**Gợi ý:** Kiểm effective daemon config theo connection context, actual process/route và approved negative authentication trên test host. Không chỉ grep một file.

### Bài tập C — Non-root service có quyền quá rộng

Invoice worker chạy UID 10001 và không có sudo, nhưng container mount runtime socket, cloud role đọc mọi tenant exports.

**Gợi ý:** Least privilege nhiều tầng: process capabilities/mounts, socket access, IAM resource policies và data/tenant authorization. UID không-root chưa đủ.

### Bài tập D — EDR có heartbeat nhưng không phát hiện canary

Dashboard báo agent healthy ở 100 VMs; security team tạo benign test event theo procedure nhưng SIEM không nhận gì ở 12 hosts.

**Gợi ý:** Tách agent registration, active sensor, policy, event generation, ingestion và alerting. Kiểm source health, routing, parser/clock; 12 hosts chưa đạt operating-evidence claim.

### Bài tập E — Một host chưa nằm trong inventory

Cloud API cho thấy 61 production instances, endpoint management ghi 60 registered hosts.

**Gợi ý:** Dùng stable instance IDs đối chiếu, xác minh lifecycle/owner, tìm unmanaged host và tạo coverage finding. Không dùng 60/60 làm full coverage.

### Bài tập F — Secure Boot enabled nhưng host vẫn có rủi ro

Một VM bật Secure Boot nhưng chạy unsupported OS với outdated privileged service.

**Gợi ý:** Boot trust không tự chứng minh runtime packages an toàn. Cần OS lifecycle, patch, privilege, network và detection controls theo threat model.

### Bài tập G — Cloud snapshots được share ngoài scope

Một VM bị decommission nhưng snapshot còn ở cloud account với resource policy cho phép principal không được duyệt đọc.

**Gợi ý:** Host data lifecycle chưa kết thúc. Xác minh permissions, ownership, retention, encryption/key grants, revoke share hoặc xóa theo approved policy; đánh giá incident exposure và evidence.

### Bài tập H — Node pool chỉ cập nhật một nửa

Kubernetes có 20 worker nodes, 10 đã reboot với fixed image, 10 vẫn dùng old kernel vì workloads khó drain.

**Gợi ý:** Báo effective coverage theo node/critical workloads, không theo approved image rollout. Đánh giá risk, availability/quorum, rollout plan, temporary controls và verify node/pod placement sau thay.

### Bài tập I — Windows RDP chỉ cho phép admin nhưng local group sai

GPO hạn chế RDP; local Administrators group chứa một nested directory group với nhiều tài khoản không nên có quyền.

**Gợi ý:** Review effective/nested membership, logon rights và access path; separate identity/approval, apply least privilege và test denied access với synthetic account.

### Bài tập J — Secret rotated nhưng old token vẫn dùng được

Secret manager ghi new version, host vẫn có daemon giữ old credential trong memory, backend vẫn chấp nhận key cũ.

**Gợi ý:** Rotation có các pha store→load→accept new→revoke old; xác minh effective process, token rejection, session behavior, logs và data scope; không in raw key vào ticket.

### Bài tập K — Docker socket được mount vào workload

Một pod chạy non-root nhưng có quyền gọi container runtime socket trên node.

**Gợi ý:** Đây có thể là một privilege-escalation surface nghiêm trọng tùy runtime/socket permissions. Đánh giá actual mount, socket ACL, pod IAM và node trust boundary; bỏ mount/thiết kế API thay thế khi có thể, retest.

### Bài tập L — Backup job thành công nhưng restore thất bại

Backup dashboard xanh; test restore VM trong isolated environment thất bại vì encryption key không còn khả dụng.

**Gợi ý:** Backup existence khác recoverability. Verify key custody, restore dependency, RPO/RTO và clean image; báo FAIL cho recovery objective cho đến khi drill đạt.

### Bài tập M — Build runner dùng chung cho untrusted pull requests

Một runner nhận community PR jobs và production signing jobs, có persistent cache và shared credentials.

**Gợi ý:** Thiết kế isolation theo trust level, short-lived/scoped tokens, protected signing identity, immutable runner images, provenance; kiểm logs/cache/artifacts và test secrets không accessible bởi untrusted context.

### Bài tập N — Chỉ nhìn cổng TCP để đánh giá egress

Một scanner phát hiện không có public management port, nhóm tuyên bố host không thể bị quản trị trái phép.

**Gợi ý:** Cloud APIs, session manager, hypervisor console, Kubernetes exec, service roles và host runtime socket cũng là management paths. Cần access map cross-plane, effective role policies và scope-limited tests.

### Bài tập O — Trạng thái SELinux là enforcing nhưng app unconfined

Host report SELinux enabled/enforcing, một process nhạy cảm lại chạy ở unconfined domain.

**Gợi ý:** Enforcing mode là một observation; control mục tiêu yêu cầu **process coverage và correct policy domain**. Đánh giá application profile, file access, audit denials và compatibility theo baseline.

### Bài tập P — Time drift làm sai kết luận patch

Host clock lệch 35 phút, audit log cho thấy reboot “trước” package update dù operator nói ngược lại.

**Gợi ý:** So host clock, collector receive timestamps, package history và boot ID; điều chỉnh evidence confidence. Time sync là một prerequisite cho audit/provenance đáng tin.

### Bài tập Q — Incident host được “clean” rồi đưa lại production

Đội vận hành xóa file độc hại và restart service, nhưng chưa verify root trust, unauthorized accounts, credential exposure hay EDR integrity.

**Gợi ý:** Không mặc định restored security. Phối hợp incident authority, đánh giá compromise scope/forensic evidence, rotate/revoke, rebuild from trusted image nếu cần, retest boot/OS/IAM/network/EDR và data integrity.

### Bài tập R — Một exception tồn tại nhiều năm

Legacy server thiếu một critical host control, exception được ký từ hai năm trước, không có expiry hoặc compensating control tests.

**Gợi ý:** Không cho compliant tự động. Reassess asset/exposure, current threats và business constraints; thực hiện containment được test, lập replacement/upgrade roadmap, risk owner re-approval có expiry/retest triggers.

### Bài tập S — “Golden image compliant” nhưng autoscale VM mới không đúng

Image pipeline có kiểm tra baseline, nhưng cloud launch template trỏ tới version cũ cho một auto scaling group.

**Gợi ý:** Trace approved image→launch template→actual instance image/OS version→services, đóng loop IaC/drift monitoring. Tính mọi active instances và kiểm deployed/running state.

### Bài tập T — Cloud provider quản host vật lý

Một managed database không cho xem kernel/firmware của physical hosts; auditor yêu cầu máy chủ phải có một host-agent screenshot.

**Gợi ý:** Xác định shared responsibility, provider-managed/inherited controls và supplier assurance; phía khách hàng vẫn xác minh DB engine/settings, IAM, data access, encryption, backup contract. Không giả tạo host-level evidence không có quyền thu.

## 51. Kết luận

**Host Security** trong **Platform assurance** không phải một danh sách cố định các nút “bật/tắt hardening”, mà là việc bảo vệ và **chứng minh hiệu lực** của các ranh giới từ firmware/boot, OS/kernel, local/remote identities, privileges, services, network, files/secrets, storage, auditing và endpoint detection tới hypervisor, Kubernetes nodes và CI/CD hosts.

Đối với **SECURITY_SECURITY_ASSURANCE**, một báo cáo đáng tin cần nối được **business assets → host population → threat/security requirements → approved baseline → actual/effective runtime state → controlled tests → versioned evidence → findings/remediation/retest**. Những yêu cầu như “kernel fixed”, “admin access restricted”, “least privilege” hoặc “EDR healthy” phải được kiểm chứng bằng **đúng source và phương pháp**, không chỉ bằng ảnh chụp cấu hình, package installed hoặc scanner score.

Những chỗ thường tạo kết luận sai nhất là **host inventory thiếu, installed patch chưa activated, Secure Boot flag bị coi là full integrity proof, cloud IAM rộng dù process non-root, port scan bỏ qua management planes, EDR heartbeat không có events, snapshot/backup còn residual secrets, runner có quyền signing quá rộng và configuration drift trong progressive rollout**.

Vì host và quyền thay đổi liên tục, assurance phải có **provenance, freshness, population completeness, source-health, test limitations, risk-tiered exceptions và reassessment triggers**. Một host chưa thể đánh giá phải được ghi UNKNOWN; một control chưa đạt nhưng được chấp nhận rủi ro phải được ghi EXCEPTION; chỉ kết luận PASS trong phạm vi tài sản, phiên bản, phương pháp và kỳ có đủ bằng chứng.

**Mục tiêu cuối cùng là biến hardening trên giấy thành khả năng chứng minh bằng thực tế rằng máy chủ đang bảo vệ danh tính, dữ liệu và workload theo những security objectives đã phê duyệt — đồng thời liên tục phát hiện, khắc phục và kiểm chứng lại khi host, nền tảng và các đường tấn công thay đổi.**
