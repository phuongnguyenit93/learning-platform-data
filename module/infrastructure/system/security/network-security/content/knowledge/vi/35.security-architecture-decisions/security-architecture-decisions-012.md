# Khả năng rollback cấu hình mạng — Thiết kế đường lui an toàn cho kiến trúc bảo mật

Hãy hình dung một đội vận hành đang cập nhật firewall để cho phép dịch vụ thanh toán truy cập cơ sở dữ liệu qua TCP/5432. Sau khi triển khai, lưu lượng hợp lệ đi qua, nhưng một vùng mạng khách cũng bất ngờ truy cập được database. Đội vận hành nhấn **Rollback** trên công cụ quản lý policy và nhận thông báo “success”. Tuy nhiên, một firewall trong cặp HA chưa đồng bộ; phiên TCP tạo trước khi rule bị thu hồi vẫn còn trong session table; đồng thời cấu hình NAT đã được một workflow khác cập nhật sau bản snapshot. Kết nối trái quyền vẫn có thể tồn tại dù phiên bản policy hiển thị đã trở lại như cũ.

Trong một tình huống khác, kỹ sư đổi default route trên router biên rồi mất luôn kết nối quản trị. Bản sao cấu hình có sẵn nhưng chỉ truy cập được qua chính đường mạng vừa bị hỏng. **Có backup không đồng nghĩa có khả năng rollback.**

**Khả năng rollback cấu hình mạng (network configuration rollbackability)** là thuộc tính thiết kế thể hiện việc tổ chức có thể **phát hiện, ra quyết định và quay lại một trạng thái mạng đã được chấp nhận về chức năng và bảo mật** sau một thay đổi không đạt yêu cầu, với **thời gian, độ gián đoạn, độ mất dữ liệu và rủi ro lan rộng** nằm trong mức được phê duyệt. Khái niệm này rộng hơn nút “Revert” của một công cụ cấu hình.

Bài học thuộc chương **Quyết định kiến trúc bảo mật mạng**, module **SECURITY_NETWORK_SECURITY**. Nội dung kết nối phân đoạn mạng, firewall, routing, VPN, IDS/IPS, DNS, xác thực kết nối, cloud network, Kubernetes, network telemetry và incident response nhằm xây dựng kiến trúc **an toàn khi thay đổi và có thể phục hồi**.

> **Nguyên tắc:** Một rollback chỉ thành công khi **trạng thái cấu hình và trạng thái thực tế** được xác minh đủ để đáp ứng **business positive tests, security negative tests, operational health và auditability**. Không được đồng nhất “cấu hình cũ đã được nạp” với “toàn bộ traffic và quyền truy cập đã trở về đúng”.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **backup, revert, rollback, roll-forward, failover, restore và disaster recovery**.
2. Xác định **rollback target, recovery objective, blast radius, rollback trigger, precondition, verification gate** ngay khi thiết kế kiến trúc.
3. Mô hình hóa sự khác nhau giữa **desired/candidate/running/saved config**, **RIB/FIB**, **connection state**, **NAT state** và **business behavior**.
4. Đánh giá các cơ chế **candidate + commit, commit-confirmed/timed revert, configuration checkpoints, versioned Git/IaC, device backup và out-of-band rescue**.
5. Phân tích rollback cho **firewall/ACL, NAT, BGP/OSPF/static routes, VPN, DNS, HA, cloud routing/security groups, Kubernetes NetworkPolicy và service mesh**.
6. Nhận diện rủi ro từ **partial deployment, concurrent changes, policy drift, immutable artifacts, key rotation, TTL/caches, session persistence và distributed convergence**.
7. Thiết kế **canary, phased deployment, stop conditions, verification và rollback runbook** có người chịu trách nhiệm.
8. Xây dựng phương pháp thử rollback an toàn tại lab/staging, gồm **positive và negative controls**, telemetry và fault injection có giới hạn.
9. Viết **Architecture Decision Record (ADR)** so sánh phương án theo rủi ro, chi phí và khả năng phục hồi.
10. Đánh giá **readiness, độ tin cậy phục hồi, thời gian rollback, residual exposure** bằng các chỉ số rõ định nghĩa.

## 2. Tại sao rollbackability là một quyết định kiến trúc?

Trong một hệ thống mạng đơn giản, đổi một rule rồi đổi lại có vẻ đủ. Trong mạng doanh nghiệp, một yêu cầu nhỏ có thể tạo các thay đổi liên quan:

- Policy firewall ở đường ingress và egress.
- Address/service objects, ACLs, groups và application identities.
- SNAT/DNAT, NAT exemptions, session table.
- VRFs, route maps, static routes, BGP announcements và FIB/hardware programming.
- DNS records/cache, certificate validation, VPN tunnels và remote access routes.
- Load balancer, cloud security group/NACL, peering, gateway.
- CNI datapath, Kubernetes NetworkPolicy, service mesh authorization và mTLS.
- Logging, monitoring, emergency exceptions, HA synchronization.

**Một thiết bị có thể rollback trong một giây, nhưng toàn bộ hệ thống có thể cần lâu hơn để đạt trạng thái chấp nhận được.** Phải tính năng lực phục hồi ở cấp **end-to-end service path**, không chỉ ở một thiết bị.

### 2.1. Sơ đồ phụ thuộc

~~~mermaid
flowchart TD
    APP["Ứng dụng / người dùng"] --> DNS["DNS / discovery"]
    APP --> IAM["Identity / TLS trust"]
    APP --> PATH["Đường mạng thực"]
    PATH --> R["RIB / FIB / VRF / VPN"]
    PATH --> FW["Firewall policy & session table"]
    PATH --> NAT["SNAT / DNAT / mappings"]
    PATH --> CNI["Cloud / CNI / mesh controls"]
    FW --> HA["HA sync / control-plane state"]
    R --> HA
    GOV["Version, approval, rollback, OOB, evidence"] -.-> R
    GOV -.-> FW
    GOV -.-> NAT
    GOV -.-> CNI
    HEALTH["Business + security verification"] -.-> APP
~~~

Mỗi mũi tên là một **phụ thuộc cần xác nhận** khi rollback. Mô hình không giả định mọi sản phẩm xử lý NAT, policy và route theo thứ tự giống nhau.

### 2.2. Giá trị bảo mật

Rollbackability không chỉ phục vụ availability. Một thay đổi có thể:

- Vô tình mở Internet → database hoặc management plane.
- Bypass IDS/IPS/WAF vì thay route/traffic steering.
- Làm quyền truy cập giữa tenant/subnet rộng hơn thiết kế.
- Tắt log hoặc đẩy flow sang đường không được giám sát.
- Mất phân quyền remote access hoặc mTLS identity boundary.
- Xóa hoặc kéo dài một emergency exception sai.

**Rollback phục hồi khả năng phòng vệ** là yêu cầu quan trọng ngang khôi phục kết nối. Nếu rollback lại tạo một policy yếu hơn, cần chọn **safe rollback target** hoặc **compensating control**, không mặc nhiên khôi phục snapshot cũ.

## 3. Thuật ngữ: rollback không phải restore hay failover

| Thuật ngữ | Ý nghĩa | Bẫy cần tránh |
|---|---|---|
| **Config backup** | Bản sao trạng thái cấu hình tại một mốc | File có thể không đủ/cũ/không restore được |
| **Checkpoint/snapshot** | Điểm lưu trạng thái có thể quay lại theo cơ chế nền tảng | Có thể không bao phủ sessions/other devices |
| **Revert** | Hoàn tác một tập thay đổi/cấu hình | Không chắc đảo tất cả tác động vật lý/bên ngoài |
| **Rollback** | Đưa hệ thống về trạng thái chấp nhận được sau thay đổi lỗi | Có thể gồm nhiều bước và verification |
| **Roll-forward** | Triển khai một sửa đổi mới thay vì quay về phiên bản trước | Cần rủi ro/approval và tests riêng |
| **Failover** | Chuyển traffic/role sang node/đường dự phòng | Nếu config sai sync cả cluster, failover không giúp |
| **Restore** | Nạp dữ liệu/config từ một bản lưu | Không đảm bảo hiệu ứng policy/routing đã hội tụ |
| **Disaster recovery (DR)** | Khôi phục khi hạ tầng/failure domain lớn bị mất | Thường cần phương án thay thế toàn hệ thống |
| **Compensating control** | Biện pháp giảm nguy cơ khi chưa rollback trực tiếp được | Phải có owner, hạn dùng và theo dõi |
| **Last-known-good** | Trạng thái đã được kiểm chứng tại một mốc | Không mặc định là trạng thái an toàn cho nhu cầu hiện tại |

### 3.1. Mục tiêu không nhất thiết là byte-for-byte giống trước

Nếu sau T0 đã có một sửa lỗi bảo mật hợp lệ (change B), rồi change A làm hỏng route, **khôi phục snapshot T0** có thể xóa cả sửa lỗi bảo mật B. Khi đó, rollback phù hợp là **revert phần sai của A** trên state có B, không phải reset toàn bộ môi trường về T0.

~~~text
T0: baseline policy version P0
T1: Change B = vá quyền quản trị → P1
T2: Change A = sai route → P2
T3: Phát hiện lỗi do A

Mục tiêu:
  Quay về P1 + route phù hợp, GIỮ bản vá B.

Không mặc định:
  Restore P0 và vô tình mở lại lỗ hổng trước đó.
~~~

### 3.2. Ba loại trạng thái phải xét

1. **Configuration state:** rules, routes, objects, certificates, VRF, BGP policy, IAM policy.
2. **Runtime state:** RIB/FIB, conntrack, NAT sessions, VPN/HA state, caches, controller convergence.
3. **Observed behavior:** application SLO, reachability, denied paths, authentication và telemetry.

Một thao tác có thể thay đổi (1) nhưng (2) và (3) chưa khôi phục. Báo cáo rollback phải ghi rõ lớp nào đã được xác minh.

## 4. Định nghĩa “rollback thành công” bằng các bất biến

### 4.1. Bất biến bảo mật và nghiệp vụ

Ví dụ hệ thống Orders:

~~~text
Bất biến nghiệp vụ:
  A1. Orders API tới PostgreSQL TCP/5432 hoạt động.
  A2. DNS/IdP/telemetry/backup paths còn hoạt động.
  A3. Dịch vụ đáp ứng tiêu chí latency/error được chủ sở hữu đặt.

Bất biến bảo mật:
  S1. Internet không kết nối trực tiếp DB.
  S2. Guest/untrusted workloads không tới DB TCP/5432.
  S3. Management plane chỉ được truy cập qua bastion + AAA phù hợp.
  S4. Traffic không bypass lớp security inspection bắt buộc.
  S5. IPv4 và IPv6 đều có policy phù hợp.
  S6. Mọi emergency exceptions có owner/expiry/audit.
~~~

Mỗi bất biến cần **nguồn kiểm tra, owner và bằng chứng**. Một kiểm tra `curl 200` không thể thay cho những bất biến khác.

### 4.2. Positive và negative gates

| Gate | Trả lời | Bằng chứng |
|---|---|---|
| **Positive business** | Luồng được phép vẫn vận hành? | App health, DB connection, DNS, transaction trace |
| **Negative security** | Luồng không có quyền vẫn bị từ chối? | Enforcement verdict + healthy destination control |
| **Control-plane** | Policies, routing adjacencies, advertised prefixes đúng? | Config ID, RIB, BGP/OSPF state |
| **Data-plane** | Gói thực đi qua đường và NAT đúng? | FIB, flow logs, NAT translations, packet counters |
| **Operational** | HA, monitoring, OOB, capacity khỏe? | Device health, syslog heartbeat, SLO |
| **Forensic/audit** | Thay đổi và quyết định truy vết được? | Change log, approvals, integrity and timestamps |

**Một negative test timeout** chưa chứng minh firewall chặn: server down, DNS sai hoặc route blackhole đều có thể timeout. Phải so với **positive control từ nguồn được phép** và **log quyết định tại enforcement point**.

## 5. Rollback objectives: định lượng trước khi thay đổi

Không có ngưỡng duy nhất cho mọi hệ thống. Các mục tiêu nên do owner chốt theo mức quan trọng:

| Mục tiêu | Nội dung | Ví dụ định nghĩa tốt |
|---|---|---|
| **Target rollback state** | Phiên bản/policy/behavior sẽ quay về | “P1 + route R7; giữ mitigation M2” |
| **Maximum acceptable rollback duration** | Từ trigger đến khi **verified recovered** | Một giới hạn tính theo business SLO |
| **Blast radius** | Assets/zones/tenants/regions có thể ảnh hưởng | Một VRF/region trước, không global |
| **Detection deadline** | Khi nào thấy rollback trigger | Theo telemetry/review intervals |
| **Rollback execution owner** | Ai thực thi và điều phối | Network lead + IC/approval |
| **Independent verification** | Ai xác minh security/business gates | SRE/app owner và security reviewer |
| **OOB viability** | Đường vào khi in-band network hỏng | Console/management độc lập đã được kiểm tra |
| **Exception policy** | Compensating controls và hạn dùng | Owner/expiry/monitoring rõ |

### 5.1. Thời gian phục hồi tổng hợp

Một mô hình tư duy:

\[
T_{\text{verified rollback}} =
T_{\text{detect}} +
T_{\text{decide}} +
T_{\text{execute}} +
T_{\text{converge}} +
T_{\text{validate}}
\]

Các thành phần có thể chồng lấn, và **không phải công thức SLA chuẩn**. Nó nhắc rằng một rollback command chạy vài giây không chứng minh **routing convergence, HA sync, session recovery và business verification** đều hoàn thành.

### 5.2. RTO/RPO có liên hệ nhưng không thay mọi tiêu chí

- **RTO (Recovery Time Objective)** liên quan thời gian phục hồi dịch vụ sau gián đoạn.
- **RPO (Recovery Point Objective)** liên quan mức mất dữ liệu có thể chấp nhận, không trực tiếp đo tính đúng của ACL/routing.
- Network rollback cần thêm **security exposure duration**, policy integrity, route propagation và authenticated access checks.

Khi ứng dụng có dữ liệu trạng thái, rollback mạng có thể khiến **retries, duplicate requests hoặc replication lag**; cần phối hợp application/database owners để bảo vệ tính toàn vẹn, không tự sửa payload hoặc database.

## 6. Mô hình threat/risk khi rollback thất bại

### 6.1. Failure tree

~~~mermaid
flowchart TD
    BAD["Rollback không đạt trạng thái an toàn"] --> C["Config không quay về đúng"]
    BAD --> R["Runtime state chưa khôi phục"]
    BAD --> V["Không có khả năng xác minh"]
    C --> C1["Backup lỗi / snapshot cũ"]
    C --> C2["Partial commit / concurrent changes"]
    C --> C3["Controller reapply desired state sai"]
    R --> R1["RIB/FIB chưa hội tụ"]
    R --> R2["NAT/session/cache vẫn cũ"]
    R --> R3["HA nodes không đồng nhất"]
    V --> V1["Sensor/clock/source identity thiếu"]
    V --> V2["Không có negative tests"]
    V --> V3["Management/OOB đã mất"]
~~~

### 6.2. Vấn đề không hiển nhiên

- **File backup có nhưng secrets không thể restore** vì được quản lý ngoài thiết bị.
- **Candidate config đã revert** nhưng session table vẫn giữ luồng có quyền trước đó.
- **BGP policy trở lại** nhưng route advertisement chưa hội tụ trên peers.
- **Cloud API thành công** nhưng route/SG updates có độ trễ áp dụng theo vùng.
- **Kubernetes policy được rollback** nhưng CNI datapath vẫn lệch do lỗi controller.
- **Certificate cũ** không còn trust hoặc đã bị revoke; rollback TLS trust có thể tạo lỗ hổng.
- **NAT pool cũ** không còn được gán hoặc endpoint IP đã chuyển chủ.
- **GitOps reconciler** tự áp lại phiên bản lỗi ngay sau sửa thủ công.
- **Route management** bị mất và không có OOB để thực hiện restore.
- **Restore snapshot trước đó** làm mất những emergency mitigation hợp lệ mới hơn.

Thiết kế rollback phải xét toàn bộ failure modes liên quan thay đổi, thay vì chỉ giả định thiết bị “hỗ trợ undo”.

## 7. Kiến trúc baseline: version, ownership và safe checkpoints

### 7.1. Source of truth không phải telemetry source

| Thành phần | Có gì | Giới hạn |
|---|---|---|
| **Source of truth (Git/IaC/CMDB)** | Desired policy, topology, owner, dependency | Có thể lệch running state |
| **Device config/version** | Candidate/running/committed/startup | Không chắc dataplane hiện thực đúng |
| **Controller state** | Các resources/policies đang được reconciliation | Có thể reapply lỗi hoặc trễ |
| **Network telemetry** | Forwarding/session/flow behavior | Có thể sampled, thiếu vantage/identity |
| **Application telemetry** | Thực tế user/business transaction | Không tự chứng minh network deny |
| **Audit trail** | Ai thay gì lúc nào theo logs | Không đầy đủ nếu collector outage/clock skew |

Một phiên bản được gọi **last-known-good** chỉ khi đã có **security/business verification phù hợp tại mốc đó**, không chỉ là commit cuối cùng deploy thành công.

### 7.2. Checkpoint bao gồm những gì?

~~~yaml
# PSEUDO-CHECKPOINT: metadata cho thiết kế, KHÔNG PHẢI manifest thiết bị.
checkpointId: "NET-ARCH-LAB-012-C18"
environment: "approved-lab"
approvedBy: "change-authority"
capturedAtUtc: "2026-11-28T09:00:00Z"
components:
  - id: "edge-router-a"
    desiredVersion: "git-commit-reference"
    runningVersion: "device-checkpoint-reference"
    forwardStateDigest: "RIB/FIB reference, not exact restoration artifact"
  - id: "firewall-ha-pair"
    policyPackage: "verified-policy-version"
    haConfigSync: "verified"
  - id: "cloud-network"
    desiredVersion: "IaC module revision"
  - id: "kubernetes-network"
    desiredVersion: "GitOps/network-policy release"
securityInvariants:
  - "Untrusted zone cannot reach database"
businessInvariants:
  - "Orders API reaches approved database service"
recovery:
  oobOwner: "network-oncall"
  rollbackArtifact: "encrypted-versioned-backup"
  verificationPlan: "approved test-matrix"
evidence:
  repository: "restricted-evidence-vault"
  actualSha256Digests: "recorded-per-artifact"
limitations:
  - "Runtime sessions and external DNS caches are not part of checkpoint"
~~~

**Đây là mẫu mô tả**, không phải schema thực thi, và một field dạng `actualSha256Digests: recorded...` không phải digest thật. Khi lưu artifact thực tế, phải tính hash từ đúng bytes và hạn chế truy cập.

### 7.3. Backup/restoration readiness

Một kế hoạch đạt yêu cầu phải trả lời:

1. Backup chứa **cả rule objects, NAT maps, route policy, identity references, certificates và secrets dependencies** hay chỉ một phần?
2. Nó có phù hợp **OS/firmware/cluster mode/version** đang chạy?
3. Các khóa/credentials bị rotate hoặc revoke sau backup sẽ xử lý thế nào?
4. Restore là atomic hay cần nhiều lệnh, có khả năng chỉ hoàn thành một phần?
5. Backup được **mã hóa và RBAC**, có kiểm tra integrity/digest và audit?
6. Đã diễn tập restore trong **lab/staging** thay vì chỉ nhìn file tồn tại?
7. Có thể thực hiện restore khi **IdP, VPN, DNS, routing hoặc management network đang lỗi** không?

Không đưa backup raw của firewall/router vào ticket công khai vì có thể chứa passwords, PSKs, private keys, address maps và chi tiết hạ tầng.

## 8. Cơ chế rollback: những lựa chọn kiến trúc phổ biến

### 8.1. Candidate configuration và commit transaction

Một số hệ thống cho phép chỉnh **candidate configuration** trước khi commit. Mô hình này giúp:

- Review diff trước khi policy ảnh hưởng traffic.
- Validate syntax và một số constraints trước apply.
- Lưu transaction/commit history và rollback tới revision.
- Giảm nguy cơ những thao tác rời rạc bị nhìn thấy như trạng thái trung gian.

Nhưng **candidate/commit không luôn là transaction nguyên tử end-to-end**: có thể có nhiều devices, controllers, line cards, policy engines và external systems; một commit thành công chưa chắc mọi dataplane nodes đã nhận cùng phiên bản.

### 8.2. Commit-confirmed hoặc timed revert

Trên những nền tảng hỗ trợ, một commit có thể đi kèm cơ chế **tự động revert nếu không được xác nhận trong khoảng thời gian giới hạn**:

~~~mermaid
flowchart TD
    C["Reviewed candidate"] --> S["Commit with revert timer (nếu hỗ trợ)"]
    S --> A["Check management/OOB"]
    A --> T["Business + security + dataplane tests"]
    T --> G{"Acceptance gates PASS?"}
    G -->|"Có"| OK["Confirm commit đúng window"]
    G -->|"Không / mất kết nối"| RB["Automatic/manual revert theo platform"]
    RB --> V["Verify runtime, HA, routing, flows"]
    OK --> E["Archive version and evidence"]
~~~

**Giới hạn quan trọng:**

- Không phải mọi hãng/router/firewall/controller có commit-confirmed.
- Timer và semantics khi failover/reboot/HA sync khác nhau theo sản phẩm và version.
- Revert cấu hình **không rollback các side effects**: BGP convergence, DNS caches, NAT sessions, revocation, external API calls.
- Nếu người vận hành **confirm quá sớm**, timed revert không giúp khi một negative security test sau đó mới phát hiện lỗi.
- Commit-confirmed **không thay thế out-of-band access**, backups và validation.

Không đưa một chuỗi lệnh vendor-specific như thể hoạt động được trên mọi OS. Trước khi dùng, phải đọc tài liệu phiên bản thực và thực hành trong lab có permission.

### 8.3. Snapshot và restore

Snapshot phù hợp khi:

- Platform có cơ chế export/import đủ thành phần và version.
- Phạm vi thay đổi độc lập, có thể restore đúng dependency set.
- Có thể kiểm tra integrity và restore compatibility.
- Phương án phục hồi không lệ thuộc vào service đang có nguy cơ hỏng.

Tuy nhiên snapshot quá cũ có thể **xóa security fixes** hoặc secrets rotations hợp lệ mới hơn. Restore có thể cần **targeted merge** thay vì overwrite toàn bộ.

### 8.4. Git revert / IaC rollback

Với mô hình infrastructure as code:

1. Mọi desired-state change nằm trong version control.
2. Pull request có review và policy checks.
3. Pipeline triển khai version được phê duyệt, ghi artifact ID.
4. Rollback có thể là revert commit, deploy phiên bản trước hoặc patch mới.
5. **Reconciliation** phải đưa runtime về trạng thái mới, không chỉ đổi Git.

**Không đồng nhất `git revert` với network rollback**. Git chỉ sửa versioned source; thiết bị và controllers vẫn có thể ở phiên bản cũ, lỗi, drift hoặc đang offline.

### 8.5. Manual rescue / out-of-band

Với mạng quan trọng, cần phương án **không phụ thuộc đường điều khiển đang thay**:

- Console access, out-of-band management network hoặc remote hands theo quy trình.
- Break-glass identity được bảo vệ, có audit và scope.
- Local recovery artifact và danh sách bước tối thiểu được diễn tập.
- Kênh liên lạc thứ hai giữa change authority và implementer.
- Power/reboot/failover chỉ khi được phép; không tự thực hiện thao tác có thể xóa volatile evidence.

**OOB path phải được kiểm tra thực**, chứ không chỉ đánh dấu có thiết bị console server trong inventory.

### 8.6. Khi rollback không an toàn: roll-forward hoặc compensating control

Có những tình huống rollback một phần mềm/certificate có thể **mở lại lỗ hổng vừa được vá**, hoặc IP/NAT resource cũ không còn hợp lệ. Khi đó:

- Có thể cần **roll-forward** bằng cấu hình mới được review và test.
- Dùng **temporary narrow deny/segmentation** để giảm exposure trong lúc phục hồi.
- Không reset secrets/trust bundles về bản đã bị revoke/compromise.
- Có incident authority, owner, expiry và evidence cho giải pháp tạm.
- Theo dõi residual risk, không gọi mọi service healthy là an toàn hoàn toàn.

## 9. Thiết kế out-of-band và đường quản trị cứu hộ

### 9.1. Vấn đề tự khóa

Nếu operator quản trị router qua chính VPN/VRF/default route đang thay, việc deploy có thể cắt phiên. Nếu cùng một IdP, DNS hoặc firewall kiểm soát cả production và rescue path, **đường cứu hộ có thể cùng chịu lỗi**.

Thiết kế OOB phù hợp cần xét:

| Lớp | Câu hỏi |
|---|---|
| **Connectivity** | Đường console/management có độc lập với routing/ACL đang sửa? |
| **Identity** | Khi IdP chính lỗi, có break-glass được bảo vệ và audit? |
| **Power/location** | Khi site/link chính mất, console/management có điện và lối vào? |
| **Authorization** | Ai được sử dụng, phê duyệt và kết thúc phiên? |
| **Recovery artifact** | Có thể truy cập backup/version/recovery instruction khi site offline? |
| **Testing** | Đã thử OOB có kiểm soát gần đây theo lịch? |
| **Privacy** | Admin credentials/logs được bảo vệ, không mở management public? |

### 9.2. Tránh xây đường cứu hộ thành cửa hậu

Một OOB path không nên là public SSH không MFA, shared password phổ biến hoặc tài khoản không được giám sát. Nó cần **least privilege, credential management, privileged access logging, break-glass review và định kỳ thử/rotate**.

### 9.3. Mô hình failure domain

~~~mermaid
flowchart LR
    OP["Operator / change authority"] --> IN["In-band VPN / IdP / routing"]
    OP --> OOB["Independent OOB / break-glass"]
    IN --> EDGE["Edge router / firewall"]
    OOB --> EDGE
    EDGE --> PROD["Production services"]
    SAFE["Recovery artifact & approval"] -.-> OOB
~~~

**“Độc lập” là mục tiêu tương đối**; nếu cả OOB và in-band dùng một cloud account hoặc một physical link, hãy ghi rõ common-mode failure. Mọi thiết kế có giới hạn chi phí và vận hành cần được đưa vào ADR.

## 10. Firewall/ACL rollback: policy đúng chưa đủ, sessions phải đúng

### 10.1. Những gì phải quay lại

| Yếu tố | Khi revert cấu hình | Xác minh sau rollback |
|---|---|---|
| Rule order/actions | Được đưa về revision phù hợp | Effective match/deny/allow |
| Address/service objects | Có thể ảnh hưởng nhiều policy | Dependencies và expanded scope |
| Zones/interfaces | Có thể khác do route/interface change | Source/destination zone thực |
| User/dynamic tags | Dữ liệu đồng bộ ngoài firewall có thể trễ | Identity membership, tag resolution |
| Security profiles | IPS/App-ID/TLS inspection có còn áp? | Inspection path và logs |
| Stateful sessions | Có thể **còn tồn tại** sau rule revert | Session lifecycle/revocation policy |
| NAT/route association | Có thể là change riêng | 5-tuple trước/sau NAT, return path |
| HA policy sync | Nodes có thể nhận phiên bản khác nhau | Per-node applied config version |

### 10.2. Statefulness và quyền truy cập đã được cấp

Một số firewall cho phép **existing established sessions** tiếp tục khi thay policy; một số khác reevaluate hoặc có cách xóa sessions. Không có một hành vi chung cho mọi vendor.

Vì vậy khi rollback một **overly permissive allow**, cần:

1. Xác minh rule mới đã hết hiệu lực tại đúng dataplane.
2. Đánh giá **existing sessions** đã được tạo trong khoảng policy lỗi.
3. Theo quy trình được phê duyệt, quyết định có cần kết thúc những sessions rủi ro hay không.
4. Không xóa toàn bộ session table mù quáng vì có thể gây outage lớn.
5. Positive control: legitimate flows vẫn hoạt động.
6. Negative control: unauthorized new flows và các phiên cũ liên quan không còn quyền ngoài ý định.

**Một successful deny với kết nối mới không chứng minh mọi established connection trái quyền đã bị xử lý.**

### 10.3. Shadowing và additivity

Khi revert một rule hẹp, **một rule allow rộng khác** vẫn có thể cho traffic qua. Reviewer cần kiểm effective policy với các quy tắc:

- Firewall/ACL ordering và first-match/last-match theo platform.
- Overlapping objects, dynamic groups, profile attachments.
- Host/zone policies và cloud security groups có thể là các layers cộng dồn/khác semantics.
- Kubernetes NetworkPolicy chuẩn có **additive allow**, không có explicit deny theo priority.

Không kết luận quyền đã đóng chỉ từ việc rule mang tên “temporary allow” đã bị xóa.

## 11. NAT rollback: bản dịch địa chỉ và phiên hoạt động

### 11.1. Vì sao NAT khó hơn thay một object?

SNAT/DNAT/PAT có thể ảnh hưởng:

- Những IP public đang được cấp và route về.
- Connection mappings, source ports, port exhaustion và session timeout.
- Firewall policy evaluation order trên từng nền tảng.
- VPN traffic selectors/NAT exemptions và cloud egress.
- Partner allowlists dựa trên public source IP.
- Log correlation giữa source workload và translated address.

Ví dụ lab:

~~~text
Before NAT:
  10.20.1.7:51123 → 198.51.100.20:443
After SNAT:
  203.0.113.50:62010 → 198.51.100.20:443

Rollback policy:
  Restore IP/pool rule?                     Có thể
  Restore active NAT mappings tự động?      Không chắc
  Partner firewall đã cập nhật allowlist?  Phụ thuộc
  Established application sessions?        Phụ thuộc
~~~

Địa chỉ là ví dụ thuộc dải dành cho tài liệu, không phải mục tiêu hoạt động thật.

### 11.2. Khi NAT pool bị thay

Một rollback an toàn cần:

1. Xác minh địa chỉ/pool cũ **vẫn thuộc quyền và vẫn được route**.
2. Ghi thời điểm, mappings và active sessions đang chịu ảnh hưởng.
3. Xem upstream firewall/partner allowlists có thay đổi tương ứng không.
4. Ước lượng connection churn, retries, API idempotency và application impact.
5. Xác minh logging attribution trước/sau NAT vẫn hoạt động.
6. Test cả IPv4, IPv6/NAT64 nếu kiến trúc áp dụng.

**Không khôi phục một public IP đã được thu hồi/cấp cho tenant khác** chỉ vì nó nằm trong bản backup.

## 12. Routing rollback: không chỉ trả lại prefix

### 12.1. RIB, FIB và hội tụ

Router có **control-plane state** (neighbor sessions, routing protocols, RIB) và **data-plane state** (FIB/kernel/ASIC forwarding, ACL offload). Sau khi revert route/policy:

- BGP/OSPF có thể cần thời gian hội tụ theo topology/timers.
- Peers/upstream có thể chưa nhận lại advertisements.
- PBR/ECMP/VRF có thể giữ đường đi không mong muốn.
- ASIC/hardware route programming có thể khác trạng thái control plane.
- Stateful firewall có thể drop traffic nếu đường đi/về trở nên bất đối xứng.
- Route leak hoặc default-route blackhole có thể tiếp tục gây tác động.

### 12.2. BGP: những gì cần so

| Yếu tố | Before/baseline | Sau rollback |
|---|---|---|
| Neighbor state | Đúng peers/roles | Không chỉ Established, còn reachability |
| Prefix import/export | Allowlist theo policy | Không quảng bá/nhận prefixes ngoài scope |
| Route preference | Intended path/communities | Selected paths và backup paths đúng |
| Default route | Đường và VRF đúng | Management/traffic không bị blackhole |
| RIB/FIB | Prefix present và installed | Data plane test thực từ nguồn đại diện |
| BFD/convergence | Health và timing expected | Không có route flapping bất thường |
| ISP/provider | Expected filtering/propagation | Có xác nhận nếu change liên quan upstream |

**RPKI origin validation** có thể giảm nguy cơ origin prefix bất hợp lệ ở Internet edge theo triển khai, nhưng **không chứng minh toàn bộ AS-path an toàn** và không thay route-policy rollback tests.

### 12.3. OSPF/IGP và route redistribution

Khi revert changes về costs, areas, summaries hoặc redistribution:

- Xác minh adjacencies và link-state database.
- Kiểm tra prefix leak giữa VRFs/areas.
- Đánh giá loops, blackholes và failover path.
- Đảm bảo **return path** qua stateful controls hợp lệ.
- Theo dõi overload/route churn, không lấy “OSPF Full” làm chỉ số ứng dụng khỏe.

### 12.4. Quyết định rollback hay giữ tạm route an toàn

Nếu route cũ đi qua một firewall đã bị compromise hoặc dead link, rollback nguyên trạng có thể tạo rủi ro cao. Có thể dùng **safe route alternative** đã được owner phê duyệt, giữ security inspection và test; ghi đây là **roll-forward/compensating action**, không gọi “đã trở về baseline”.

## 13. HA, cluster và multi-device rollback

### 13.1. HA không đồng nghĩa “còn bản cấu hình dự phòng”

Trong một cặp firewall active/standby, policy sai có thể **được đồng bộ ngay sang standby**. Khi failover, traffic tiếp tục đi qua **cùng policy sai**. Vì vậy:

- Kiểm tra roles và health của tất cả nodes.
- Xác định policy/config sync semantics theo vendor.
- Lưu version và backup **ngoài cluster**.
- Ghi session/state synchronization behavior, nhất là khi rollback deny.
- Tránh ép failover production nếu không có maintenance window và safety review.

Một rollout thực sự có thể chỉ hỗ trợ **atomic policy update cả cluster**, không có canary trên một node. Khi đó cần tests preflight sâu hơn và timed recovery/OOB độc lập.

### 13.2. Multi-device partial commit

Giả sử thay đổi được phân phối:

~~~text
Change A:
  Router R1: update route        APPLIED
  Firewall F1: allow new flow    APPLIED
  Firewall F2: deny old flow     FAILED
  Cloud Gateway G1: NAT update   PENDING
~~~

Đây là **partial success**; trạng thái mạng nằm giữa hai thiết kế, có thể **mở một đường bất thường hoặc tạo blackhole**.

Một kiến trúc tốt cần:

1. **Dependency graph** và thứ tự triển khai đã review.
2. Per-device/region **transaction/version status**.
3. Cơ chế **idempotent operations**, retry có giới hạn và kiểm tra state trước khi gửi lại.
4. Hành động phục hồi khi một bước fail, có thể rollback subset hoặc roll-forward.
5. Gating bảo mật giữa các bước, không để broad allow tạm tồn tại quá lâu.
6. Khả năng stop rollout và giữ telemetry khi control plane mất liên lạc.

### 13.3. Không phải mọi platform có distributed transaction

“Two-phase commit” hoặc atomic commit là khả năng cụ thể ở một số controllers/định dạng tài nguyên. **Đừng giả định** tất cả firewall/cloud/Kubernetes/network OS hỗ trợ **atomic transaction xuyên nhà sản xuất**. Khi không có atomicity:

- Chia thành **phases có kiểm chứng**.
- Chọn thứ tự “không tạo exposure mới” nếu khả thi.
- Chấp nhận một khoảng giảm availability chỉ khi owner phê duyệt và có kế hoạch.
- Theo dõi state từng thiết bị và **reconcile sau lỗi**.

### 13.4. Ví dụ thứ tự cho migration

~~~mermaid
flowchart TD
    B["Baseline + backup + OOB"] --> P["Provision new safe path (closed by default)"]
    P --> V["Validate path without broadening privilege"]
    V --> S["Steer canary traffic with auth/policy intact"]
    S --> G{"Business + security gates?"}
    G -->|"PASS"| W["Expand waves then decommission old"]
    G -->|"FAIL"| X["Stop, revert steer, validate old path"]
    X --> R["Reconcile all device/controller versions"]
    W --> A["Audit final desired/effective state"]
~~~

Trong nhiều hạ tầng, **provision trước, steer sau, decommission cuối** giảm rủi ro. Nhưng nếu old path có exposure nghiêm trọng hoặc tài nguyên quá hạn, trình tự phải được thay đổi theo incident risk assessment.

## 14. Cloud networking: rollback giữa nhiều control planes

### 14.1. Những tài nguyên thường liên quan

| Thành phần | Thay đổi | Điểm đặc biệt khi rollback |
|---|---|---|
| **Security groups / NSG** | Quyền ingress/egress gắn interface/resource | Multiple attachments, statefulness và policy semantics |
| **Network ACLs** | Luật theo subnet, có thể stateless trên một số clouds | Return traffic/ephemeral ports cần xét |
| **Route tables** | VPC/VNet route/next hop/peering | Per-subnet attachment, convergence |
| **NAT gateway / public IP** | Source translation và outbound identity | Allocated IP/ports, partner allowlists |
| **Transit/peering gateway** | Liên kết networks/tenants | Route propagation và shared blast radius |
| **Private endpoints** | Thay public path bằng private route/DNS | Split DNS, service identity, ownership |
| **LB/WAF/CDN** | Entry point, backends và inspection | Origin bypass, cache/connection draining |
| **Cloud firewall service** | Centralized effective policy | Multi-region propagation và precedence |
| **IAM/API roles** | Ai có quyền cập nhật network controls | Break-glass, scoped automation, audit |

### 14.2. Eventual consistency và applied state

Một cloud API trả kết quả thành công có thể chỉ cho biết request được nhận; một số thay đổi cần thời gian propagate tới network dataplane hoặc các vùng. Vì vậy rollback cần:

- Ghi **request ID, resource ID, phiên bản desired state**.
- Đọc lại **effective attachments/routes/policies**, không chỉ response code.
- Test luồng từ **đúng subnet/region/tenant** đại diện.
- Đo propagation và cloud audit/flow logs, nhận diện log ingest delay.
- Theo dõi **new/existing connection semantics** của tài nguyên cụ thể.

Không thiết lập một thời gian hội tụ “mặc định 30 giây” cho mọi cloud provider; phải xác định từ tài liệu nền tảng và thử nghiệm phù hợp.

### 14.3. Không rollback một số nhận dạng đã bị thu hồi

Ví dụ rollback một stack cũ có thể cố tạo lại:

- Public IP đã bị release/reassign.
- IAM role hoặc service account credential đã bị revoke.
- Certificate hết hạn hoặc private key bị lộ.
- Private endpoint/peering không còn được provider cho phép.

Khi đó rollback nguyên trạng **không khả thi hoặc không an toàn**; cần phương án khôi phục thay thế đã được kiến trúc sẵn.

## 15. Kubernetes và CNI: Git revert chưa chứng minh dataplane

### 15.1. Đối tượng nào tạo đường mạng?

Trong Kubernetes/network security:

- **NetworkPolicy** chọn Pods và quy định allowed ingress/egress theo chuẩn.
- **Services/EndpointSlices** giúp chọn backend, service routing có thể thay đổi.
- **Ingress/Gateway/mesh proxy** quyết định TLS termination/HTTP routes.
- **CNI/dataplane** thực thi flow, có thể dùng iptables/nftables/eBPF.
- **Cloud LB/SG/NACL/routes** vẫn là các lớp khác ngoài Pod policies.
- **HostNetwork/node traffic** và nhiều NICs có thể có semantics khác Pod traffic.

**Rollback NetworkPolicy manifest** mới là một bước; phải xác minh CNI thực thi trên nodes/Pod identities, và các allow policies khác có thể **cộng dồn cho cùng Pod**.

### 15.2. Kubernetes NetworkPolicy standard không có explicit deny ưu tiên

NetworkPolicy chuẩn thường có mô hình:

- Một Pod được cô lập theo hướng ingress/egress khi các policies liên quan áp dụng.
- Các policy allowed flows **cộng dồn (union)**.
- Không có explicit deny rule/priority trong API NetworkPolicy chuẩn; CNI mở rộng có thể có semantics khác.

Do vậy khi rollback một allow policy rộng, cần enumerate **mọi policy còn chọn Pod**, cùng selectors/namespace labels và flow verdict. Việc xóa một YAML policy không đủ nếu một allow-all policy khác vẫn tồn tại.

### 15.3. GitOps/controller drift

Một sự cố thường gặp:

~~~text
Git desired state:            Version K7 (policy mới an toàn)
Cluster actual state:         Version K6 (policy cũ còn hiệu lực)
Human emergency patch:        Version K6a (deny tạm)
GitOps auto reconcile:        Re-applies K7 hoặc K6 tuỳ commit

Nếu không phối hợp controller:
  Manual rollback có thể bị overwrite.
~~~

Giải pháp kiến trúc: **một source of truth có quy trình emergency override**, owner/controller visibility, revision pinning, rollout pause/unpause đúng quyền và sau đó reconcile. Không nên tắt toàn bộ GitOps controller vô thời hạn; cần phương án quản trị ngoại lệ.

### 15.4. Rollback CNI upgrade khác rollback policy

Nếu thay đổi gồm **CNI binary/datapath upgrade**, restore một NetworkPolicy YAML có thể không sửa được lỗi kernel/eBPF map/iptables path. Phải đánh giá:

- Compatibility giữa CNI version, Kubernetes/OS/kernel và node pool.
- Rollout theo node groups/canary, khả năng drain/rollback an toàn.
- Workload reschedule, address/IPAM, DNS/Service routing.
- Bảo toàn reachability của control-plane/etcd/observability.
- Positive/negative test từ **nodes khác nhau**, IPv4/IPv6 khi áp dụng.

Không thao tác privileged Pods, sửa kernel settings hoặc xóa dataplane state trực tiếp trong production nếu chưa có runbook/quyền.

## 16. Service mesh, mTLS và policy rollback

### 16.1. Các lớp thường gặp

Một flow có thể đi qua:

~~~mermaid
flowchart LR
    C["Client workload"] --> NC["CNI / node policy"]
    NC --> SP["Sidecar / ambient proxy"]
    SP --> GW["Mesh ingress/egress gateway"]
    GW --> SV["Server workload"]
    AUTH["mTLS trust / workload identity / authorization"] -.-> SP
    AUTH -.-> GW
    CFG["Service mesh control plane"] -.-> SP
    CFG -.-> GW
~~~

Rollback có thể ảnh hưởng:

- DestinationRule/traffic policy, retry, circuit breaker, outlier detection.
- mTLS mode/peer authentication và certificate distribution.
- Authorization policies theo workload identity/namespace/trust domain.
- Egress gateway và service routing.
- Certificate trust bundle/CA rotation và key material.

### 16.2. Tại sao mTLS rollback cần thận trọng?

Nếu một CA/certificate đã bị **revoke hoặc nghi compromise**, rollback trust store để “cho kết nối hoạt động lại” có thể **khôi phục lòng tin với credential không an toàn**. Cần phối hợp PKI/IAM:

1. Kiểm tra root/intermediate/leaf trust và credential lifecycle.
2. Xác minh danh tính service cần được cho phép, không chỉ TLS handshake.
3. Có kế hoạch chuyển trust an toàn và hiệu lực certificates còn lại.
4. Tránh áp broad `PERMISSIVE` hoặc bỏ authorization chỉ để giảm lỗi.
5. Test handshake và policy từ both trusted/untrusted workloads.

**Độ khỏe TLS kết nối không thay thế application authorization.** Mesh mTLS xác thực peer workload không mặc định cấp quyền đọc dữ liệu ở layer nghiệp vụ.

### 16.3. “Rollback traffic split” và retries

Canary routing trong mesh/gateway có thể rollback bằng cách đưa traffic về upstream cũ, nhưng:

- Connection pooling/HTTP2/QUIC có thể tiếp tục dùng phiên đang tồn tại.
- Retries/timeout/circuit breaking có thể khuếch đại tải.
- Một subset requests có thể vẫn đi qua backend mới do stickiness/session state.
- Origin/DB schema có thể đã đổi không tương thích với version cũ.

**Rollback mạng không thể thay cho ứng dụng rollback** nếu các dependency đã tiến hóa không tương thích.

## 17. DNS rollback: TTL, cache và split-horizon

### 17.1. DNS không có nút “hoàn tác mọi client cache”

Đổi một A/AAAA/CNAME/SRV/HTTPS record về giá trị cũ có thể làm authoritative DNS đúng, nhưng:

- Recursive resolver giữ bản ghi cũ trong cache tới TTL.
- Application/browser/OS có DNS cache riêng.
- Một số CDNs dùng geo/weighted responses, khác view.
- DNS64/NAT64 và split-horizon có thể trả endpoint khác theo mạng.
- Negative caching (NXDOMAIN/NODATA) có thể trì hoãn phục hồi.

### 17.2. DNS rollback cần plan riêng

| Bước | Mục tiêu |
|---|---|
| Thu snapshot zone và current TTL | Biết records, alias chain và phiên bản |
| Kiểm quyền authoritative DNS | Tránh sửa nhầm account/zone |
| Đánh giá TTL/cache window | Ước lượng propagation/residual requests |
| Cân nhắc old/new backends đồng thời | Giảm lỗi khi clients chưa update |
| Xác minh từ multiple resolvers/views | Tránh suy global từ một query |
| Test application/certificate identity | IP đúng không đủ khi TLS/SNI sai |
| Ghi historical answers và changes | Có provenance khi postmortem |

**Không làm DNS cutover mà không biết HTTPS/SVCB/AAAA và TLS certificate coverage**, vì một số clients có thể tiếp tục dùng địa chỉ/certificate khác.

### 17.3. Ví dụ split-horizon

~~~text
Internal view:
  db.example.test → 10.30.8.15
External view:
  db.example.test → NXDOMAIN

Nếu rollback nhầm external/public zone thành:
  db.example.test → 203.0.113.22

thì có thể tiết lộ endpoint hoặc tạo đường truy cập không dự định.
Đừng chỉ test từ internal resolver.
~~~

## 18. VPN/remote access rollback

### 18.1. Các state liên quan

- IKE/IPsec phase states, proposals, rekey/session lifetimes.
- Peer identity/certificates/PSKs và cryptographic policy.
- Traffic selectors, route-based VPN tunnels, split/full tunnel.
- AAA/MFA/ZTNA policy, device posture, active sessions.
- DNS resolvers/routing được đẩy tới clients.
- NAT-T, MTU/MSS, DPD, route return paths.

### 18.2. Nguy cơ tự cắt quyền điều tra

Nếu operator đang kết nối quản trị thông qua VPN cần rollback, phiên có thể bị ngắt trước khi sửa xong. Cần **OOB/bastion độc lập**, quyền khẩn hợp lệ và đảm bảo đường quay lại.

### 18.3. Rollback không tái cấp quyền cho credential xấu

Nếu thay đổi mới nhất đã **revoke tài khoản bị compromise**, không được restore toàn bộ policy/version cũ làm account đó hoạt động trở lại. Chọn safe target có revocation intact và test **active sessions**, không chỉ login mới.

### 18.4. Test cả hai hướng

| Positive | Negative |
|---|---|
| User có quyền truy cập đúng ứng dụng | Disabled/revoked account không còn quyền |
| DNS/Split tunnel theo policy | Unapproved subnet không reachable |
| mTLS/IdP trust đúng | Weak TLS/old VPN credentials không được chấp nhận |
| Session monitoring hoạt động | Direct management bypass bị chặn |

## 19. Thứ tự rollback nhiều thành phần: thiết kế từ dependency graph

Không có một thứ tự đúng cho mọi network. Thứ tự phải xuất phát từ:

- **Đường network hiện tại** (forward/return, NAT, VRF).
- **Lớp enforcement** (firewall, security group, CNI, mesh, WAF).
- **Identity/trust** (PKI, VPN, IdP, certs).
- **Các hệ thống đã đổi cùng thời điểm** (DNS, load balancer, service).
- **Rủi ro tạm thời** trong mỗi trạng thái trung gian.

### 19.1. Dependency graph trước rollback

Ví dụ:

~~~mermaid
flowchart TD
    S["Restore safe source identity"] --> P["Restore minimal firewall policy"]
    P --> NAT["Confirm NAT and return path"]
    NAT --> RT["Revert route steering if needed"]
    RT --> LB["Re-enable canary service flow"]
    LB --> V["Business + security validation"]
    C["DNS / TLS compatibility"] -.-> LB
    H["OOB / HA / telemetry"] -.-> P
    H -.-> RT
~~~

Sơ đồ mang tính minh họa. Nếu route cũ bypass firewall hoặc nguồn nhận dạng bị compromise, thứ tự phải thay đổi theo **risk assessment**. Thứ tự khôi phục không phải cứ “router trước firewall” hay ngược lại.

### 19.2. An toàn ở các trạng thái trung gian

Một anti-pattern phổ biến:

1. Mở firewall allow-all để “đảm bảo network path”.
2. Khôi phục routing.
3. Đóng lại policy ở bước cuối.

Nếu bước 2 thất bại hoặc kéo dài, allow-all có thể tồn tại. Thay vào đó, cần **policy tối thiểu được phê duyệt từ đầu**, kiểm tra luồng canary trước khi steer traffic và có timeout/expiry cho ngoại lệ (khi khả thi).

### 19.3. Rollback plan là một state machine

~~~mermaid
stateDiagram-v2
    [*] --> Prepared
    Prepared --> RollingOut: approval + prechecks
    RollingOut --> Validating: changes applied
    RollingOut --> RollbackDecision: deployment error
    Validating --> Stable: all gates PASS
    Validating --> RollbackDecision: security/business gate fails
    RollbackDecision --> Reverting: safe previous state exists
    RollbackDecision --> Compensating: previous state unsafe/unavailable
    Reverting --> VerifyingRecovery: revert applied
    Compensating --> VerifyingRecovery: mitigation applied
    VerifyingRecovery --> Stable: security and business gates PASS
    VerifyingRecovery --> IncidentResponse: recovery fails or active harm
    IncidentResponse --> VerifyingRecovery: coordinated remediation
    Stable --> [*]
~~~

**Transition nào cũng phải có owner**. Khi chưa có xác nhận trạng thái, không “đánh dấu completed” chỉ vì nút rollback đã được nhấn.

## 20. Canary, staged rollout và giảm blast radius

### 20.1. Canary là một quyết định phân vùng rủi ro

Một canary có thể dựa trên:

| Đơn vị canary | Phù hợp với | Giới hạn |
|---|---|---|
| **Một lab/staging device** | Kiểm tra syntax/candidate/version | Không tái hiện hết production traffic |
| **Một subnet/VRF** | Segmentation, route policy | Shared object/route có thể ảnh hưởng toàn mạng |
| **Một site/region** | Cloud/hybrid rollout | Cross-region dependencies và data flows |
| **Một source identity/group** | Firewall allowlist, access policy | NAT/identity tag có thể biến động |
| **Một prefix hẹp** | Controlled BGP steering | Route export/aggregation có thể có tác động rộng |
| **Một node pool** | CNI/cluster networking updates | Service rescheduling có thể ảnh hưởng nodes khác |
| **Một ứng dụng hoặc request cohort** | LB/mesh routing | Shared state, session stickiness |

### 20.2. Điều kiện cho phép mở rộng

Trước khi đưa thay đổi lên thêm vùng:

1. **Đúng desired/effective version** trên canary, không có drift.
2. Cả **business positive** và **security negative** tests đạt.
3. RIB/FIB, NAT, connection state, HA và route failover khỏe.
4. Log pipeline/IDS/IPS/WAF và time sync có coverage.
5. Các chỉ số lỗi/latency/packet drop nằm trong gate đã duyệt.
6. **Rollback window và OOB path** vẫn khả dụng cho wave kế tiếp.
7. Có người chịu trách nhiệm phê duyệt mở rộng hoặc một automated policy gate đã tiền phê duyệt.

### 20.3. Không thể canary?

Một default route duy nhất ở shared edge hoặc thay trust bundle toàn hệ thống có thể không chia nhỏ được. Giải pháp thay thế:

- Làm **dry-run/policy simulation** với known traffic matrix.
- Diễn tập rollback ở lab tương thích version.
- Chọn maintenance window, giảm concurrent changes.
- Chuẩn bị **timed rollback/OOB/console** độc lập.
- Có người giám sát SLO và security controls thời gian thực.
- Đưa quyết định có rủi ro không thể kiểm chứng vào ADR/approver.

**Không cố tuyên bố canary** nếu kỹ thuật dùng vẫn làm thay đổi toàn mạng.

## 21. Thiết kế rollback triggers và stop conditions

### 21.1. Trigger phải đo được

| Trigger | Quan sát | Phản ứng |
|---|---|---|
| **Unauthorized path opened** | Untrusted segment có thể vào DB | Dừng rollout, revert/contain theo incident authority |
| **Management path lost** | SSH/API tới thiết bị không còn khả dụng | OOB/timed revert, không gửi blind commands |
| **BGP prefix leak** | Prefix ngoài export policy được advertise | Withdraw/revert theo routing runbook |
| **Route blackhole/loop** | FIB mismatch, packet drops, app timeout | Dừng steer/rollback path |
| **Security inspection bypass** | Flows qua path không có required sensor | Revert routing/policy hoặc đặt control bù trừ |
| **TLS identity failure** | Hostname/chain/mTLS rejects tăng | Chuyển về trusted service path, không tắt verification |
| **NAT pool exhaustion** | New connections thất bại, port usage cao | Revert translation plan nếu pool cũ còn hợp lệ |
| **HA node drift** | Config/roles không đồng bộ | Ngừng expand, khôi phục cluster integrity |
| **Application SLO regression** | Error budget bị vượt theo ngưỡng owner | Rollback/canary stop |
| **Telemetry blind spot** | SIEM/flow collector ngừng ingest | Không được sign off security acceptance |
| **Out-of-scope effect** | Tenant/subnet khác bị đổi reachability | Stop và đánh giá blast radius |
| **Loss of emergency stop** | Operator không liên lạc được với owner/safety | Dừng triển khai theo runbook |

**Threshold định lượng** phải do service/security owners thiết lập trước: tài liệu không tự đặt con số latency/packet loss chung cho mọi hệ thống.

### 21.2. Trigger an ninh có thể ưu tiên hơn SLO

Nếu app healthy nhưng Internet→DB mở ngoài ý định, không được đánh dấu change “thành công”. Cần containment/rollback theo delegated authority ngay cả khi business metrics đang đẹp.

Ngược lại, nếu một rule deny xuất hiện trong log nhưng business service vẫn unreachable vì DNS outage độc lập, chỉ revert firewall có thể **không giải quyết lỗi**. Correlation phải dựa trên evidence, không chạy rollback mù theo alert.

### 21.3. Emergency authority và pause

Runbook phải phân biệt:

- **Pause rollout:** dừng các bước tiếp theo, giữ state hiện tại để triage.
- **Rollback/revert:** thực hiện thay đổi nhằm khôi phục.
- **Contain:** giảm active harm bằng control hẹp trong lúc chưa biết root cause.
- **Escalate to incident:** phối hợp SOC/NOC/SRE/IAM/Legal khi có compromise/ảnh hưởng dữ liệu.

Không có một “rollback button” thay thế quyết định phù hợp với **security, safety, data integrity và business continuity**.

## 22. Quy trình mẫu: rollback trong cửa sổ thay đổi

### 22.1. Preflight

- Confirm asset IDs, topology, firmware/version, owner và môi trường.
- Thu **checkpoint verified**, git/commit IDs, RIB/FIB/HA/NAT snapshots phù hợp.
- Xác minh **OOB và backup** với người chịu trách nhiệm cụ thể.
- Đo baseline SLO, security denies, cloud/CNI flow coverage.
- Review dependency graph và concurrent changes.
- Chuẩn bị **rollback targets**, trigger thresholds, change window.
- Định nghĩa rõ **ai thực thi và ai xác nhận security/business gates**.

### 22.2. Deploy có kiểm soát

~~~text
T0:    Approved change bắt đầu
T+1:   Apply candidate / canary / scoped route/policy
T+2:   Check in-band & OOB management
T+4:   Check device/config applied versions, HA sync
T+6:   Check business positive tests
T+8:   Check security negative tests
T+10:  Monitor convergence, sessions, DNS/TLS dependencies
T+12:  Decision: confirm, expand, pause, revert, or compensate
T+20:  Reconcile versions, audit evidence, ongoing monitoring

Mốc thời gian chỉ là VÍ DỤ cho lab, không phải SLA hay
thời điểm commit-confirmed hợp lệ trên mọi vendor.
~~~

### 22.3. Khi trigger xuất hiện

1. Ghi **time/source of signal**, scope, owner và current applied state.
2. Thông báo change authority/IC, dừng rollout tiếp theo.
3. Phân loại **rollback safe?** theo existing security fixes, secrets/certs, shared state, resource ownership.
4. Chọn **targeted revert**, roll-forward hoặc compensating control được phê duyệt.
5. Dùng OOB/timed revert khi cần, không thao tác mù.
6. Ghi per-component applied/reverted version và state convergence.
7. Chạy **positive/negative tests**, kiểm established sessions, HA/route/NAT/telemetry.
8. Chỉ đóng khi verification và ownership sign-off đạt.

### 22.4. Khi rollback cũng thất bại

Không nên:

- Reset mọi firewall/session tables không có impact review.
- Revert toàn bộ Git repository làm mất những security changes độc lập.
- Disable IDS/IPS hoặc TLS verification để ép service healthy.
- Tiếp tục repeat apply/revert vô hạn khi control plane không nhận.
- Hủy logs/PCAP “cho sạch”.

Thay vào đó, chuyển **incident response**, giữ evidence, xác định last verified safe state và dùng **recovery path có delegated authority**.

## 23. Thử nghiệm rollback trong lab: hai tình huống đối chứng

### 23.1. Lab topology

~~~mermaid
flowchart LR
    A["Allowed client A"] --> FW["Lab firewall"]
    U["Untrusted client U"] --> FW
    FW --> R["Lab router"]
    R --> D["Lab DB service TCP/5432"]
    O["OOB admin / backup"] -.-> FW
    O -.-> R
    SIEM["Lab logs + flow sensor"] -.-> FW
    SIEM -.-> R
~~~

**Lab phải do tổ chức sở hữu hoặc được phê duyệt**. Không thử làm mất route trên production, không gửi probes tới public IP/CDN/third-party không thuộc quyền.

### 23.2. Test A — Revert firewall allow quá rộng

1. Baseline: A→D TCP/5432 ALLOW, U→D TCP/5432 DENY.
2. Trong **lab**, tạo một candidate thay đổi khiến U được allow ngoài ý định.
3. Verification trước confirm phát hiện negative test fail.
4. Kích hoạt revert theo cơ chế platform lab.
5. Đọc lại effective policy; test **new connections** từ A/U.
6. Nếu có established sessions tạo trong policy lỗi, kiểm việc xử lý theo vendor semantics.
7. So logs/HA nodes để xác nhận không có allow path khác còn tồn tại.

**PASS** khi A vẫn truy cập hợp lệ, U bị từ chối tại đúng enforcement point và không còn phiên trái quyền theo tiêu chí đã phê duyệt. “Policy version cũ đã hiện” là **chưa đủ**.

### 23.3. Test B — Revert route change gây mất quản trị

1. Baseline: admin quản trị router qua đường test, OOB có thể dùng độc lập.
2. Lab tạo candidate route làm mất in-band management, theo một kịch bản an toàn đã duyệt.
3. Xác minh timeout qua in-band nhưng OOB hoạt động.
4. Dùng timed revert/console restore đã test trong lab.
5. Xác minh RIB/FIB, return path, application và security inspection.
6. Ghi route convergence, thời gian đến restored health và các sessions bị ảnh hưởng.

**PASS** khi OOB vẫn hoạt động và toàn bộ acceptance gates phục hồi. Không thực hiện fault injection này lên router production nếu không có thiết kế/safety approval riêng.

### 23.4. Cách dùng synthetic tests khi không được phép tạo outage

Có thể kiểm năng lực bằng:

- Tạo **config diff lỗi giả định** rồi chạy semantic policy lint/policy simulation.
- Dùng **containerized/router emulator hoặc virtual lab** tương thích chức năng.
- Replay firewall/flow logs synthetic để kiểm rule/alert/rollback decision.
- Diễn tập tabletop OOB loss và concurrent changes.
- Test backup restore trong staging nhưng không ép production failover.

Synthetic tests kiểm **logic và thao tác**, không bảo đảm performance/data-plane equivalence với thiết bị thật. Báo cáo phải ghi rõ phần nào đã thực nghiệm, phần nào chỉ tabletop.

## 24. Ma trận kiểm thử rollbackability theo tầng

Các test là **mẫu chọn lựa**, không bắt buộc tất cả trên mỗi change. Mỗi test cần owner, scope, expected result, evidence pointer và các preconditions cụ thể.

| ID | Kiểm thử | Kết quả mong muốn | Evidence |
|---|---|---|---|
| P01 | Backup của thiết bị được lưu | Đúng version, hash và quyền đọc | Backup register |
| N01 | Backup bị thiếu secret dependency | Preflight báo không đủ để restore | Restore drill report |
| P02 | OOB management từ kênh độc lập | Có thể vào theo RBAC và audit | Console login audit |
| N02 | In-band route bị mất trong lab | Timed revert/OOB hoạt động | Management/rollback timeline |
| P03 | Commit-confirmed được mô phỏng theo vendor | Unconfirmed config revert theo expectation | Commit history |
| N03 | Timer hết hạn nhưng external state còn | Không gọi service recovered ngay | Flow/RIB/app checks |
| P04 | Restore policy hẹp A→DB | A được phép | Firewall verdict + DB health |
| N04 | Untrusted U→DB sau rollback | Bị deny tại đúng rule | Deny log + positive control |
| N05 | Old established allow sessions | Được đánh giá/revoke theo policy | Session inspection |
| N06 | Rule overlap vẫn allow dù revert rule | Detect effective policy gap | Policy evaluation |
| P05 | NAT pool cũ còn hợp lệ | Translation/reachability đúng | NAT allocation/log |
| N07 | Public IP cũ đã được reassigned | Reject unsafe rollback target | Resource ownership |
| P06 | BGP import/export restored | Prefix đúng, không leak | RIB/advertised routes |
| N08 | RIB đúng nhưng FIB sai | Không sign off | Data-plane probes |
| N09 | Reverse path bị lệch qua firewall stateful | Detect asymmetry | Bidirectional flow logs |
| P07 | VPN legitimate user tới app | ALLOW đúng entitlement | VPN/IdP/app logs |
| N10 | Revoked VPN credential sau rollback | Vẫn bị từ chối | Active-session revocation test |
| P08 | DNS rollback trả record đúng từng view | Resolver/app tests PASS | DNS logs/answers |
| N11 | DNS cache còn stale answer | Monitoring/overlap plan xử lý | Multiple resolvers/app views |
| P09 | HA pair consistent version | Config/role/health đúng | Per-node evidence |
| N12 | HA standby có cùng bad policy | Failover không được coi rollback | HA sync/snapshot |
| P10 | Cloud SG/route applied version | Data-plane path đúng region | Cloud audit/flow logs |
| N13 | API success nhưng chưa propagated | Chờ gating/không sign off | Effective state/readbacks |
| P11 | K8s NetworkPolicy revert | Trusted flow ALLOW | CNI verdict |
| N14 | Một allow policy khác còn mở đường | Detect additive union | All policies + negative probe |
| N15 | GitOps overwrite manual rollback | Phát hiện drift/reconciliation conflict | Controller audit |
| P12 | Service mesh mTLS trusted peers | Handshake and auth PASS | Proxy/application logs |
| N16 | Old compromised CA được rollback | Reject insecure trust restoration | PKI policy check |
| P13 | Canary rollout rollback | Old safe path restored | SLO/flow/path evidence |
| N17 | Route steer rollback nhưng sessions sticky | Ghi residual state/monitor | LB/session logs |
| P14 | Multi-device changes rollback đầy đủ | Versions and data-plane converge | Per-component audit |
| N18 | Partial rollback trên một firewall | Không close; escalate/reconcile | Cross-device diff |
| N19 | Concurrent Change B bị snapshot xóa | Reject blind full restore | Git/change graph |
| P15 | Negative test trong monitoring window | Unauthorized path blocked | Policy verdict |
| N20 | DB down làm test U timeout | Không coi deny PASS | Healthy DB control |
| N21 | IPv4 PASS nhưng IPv6 bypass | Gap được phát hiện | Dual-stack probes/logs |
| N22 | Security inspection path bị bypass | Rollback không được sign off | Sensor path validation |
| P16 | Evidence thời điểm có timezone | Correlation đúng mốc | UTC/raw offsets |
| N23 | SIEM không ingest sau rollback | Acceptance fail cho security audit | Collector heartbeat |
| P17 | Emergency exception hết hạn | Review/removal theo policy | TTL/audit |
| N24 | Rollback làm lộ management plane | Trigger containment/stop | Independent access test |
| P18 | Post-rollback service SLO | Owner xác nhận recovered | Health dashboards |
| N25 | Traffic tới tenant ngoài scope | Stop and investigate blast radius | Scope/tenant flow audit |
| N26 | “Success” chỉ dựa vào CLI status | Gate fail nếu chưa runtime validation | Test/gate status |

**44 kịch bản trong ma trận**: 18 positive (P01–P18) và 26 negative (N01–N26). Kịch bản phải được **chọn và giới hạn** theo sản phẩm/rủi ro; không thử cố ý làm mất kết nối production chỉ vì có một dòng trong bảng.

### 24.1. Không đánh giá rollback từ một tín hiệu

Ví dụ firewall policy rollback và client U bị TCP timeout:

- U có route tới DB thật không?
- DB đang listening/healthy, client A có nối thành công không?
- Firewall thật sự nhận và **deny** packet hay một router đã blackhole?
- U có IPv6/VPN/peering path thay thế không?
- Có established sessions trước policy rollback không?

Chỉ khi evidence trả lời đủ những câu hỏi liên quan mới khẳng định **security invariant** được khôi phục.

## 25. ADR — ghi lại quyết định lựa chọn cơ chế rollback

**Architecture Decision Record (ADR)** cần làm rõ **bối cảnh, lựa chọn, tiêu chí, hệ quả và cách xác minh**. Không chỉ ghi “dùng công cụ X vì team quen”.

### 25.1. Mẫu ADR đầy đủ

~~~markdown
# ADR-NET-012: Chiến lược rollback cho edge firewall và router

## Status
Proposed / Accepted / Superseded

## Context
- Production có 2 edge routers, firewall HA, các private routes
  và policy được triển khai qua controller.
- Route/PBR thay đổi có thể cắt đường quản trị in-band.
- Mọi thay đổi phải giữ network access của business flows được phép
  và duy trì deny đối với guest/Internet -> DB.
- Có cloud/Kubernetes dependencies nhưng không có atomic commit chung.

## Decision drivers
- Security invariants, blast radius, verified recovery time.
- OOB availability và independent access.
- Per-device/version traceability, HA consistency.
- Partial failure handling, concurrent changes.
- Operating cost, operator training, vendor/version support.

## Options
A. Manual config backup + command-by-command revert.
B. Native candidate/commit-confirmed + independent OOB.
C. Versioned IaC/GitOps + staged rollout + policy tests + OOB.
D. Full snapshot restore toàn cụm.

## Decision
Chọn B + C khi thiết bị hỗ trợ đã được kiểm chứng,
kèm A như recovery fallback trong lab và OOB.
Không chọn D như mặc định do nguy cơ xóa changes hợp lệ mới.

## Consequences
Pros: auditability, rollback trigger rõ, staged verification.
Cons: tăng complexity và yêu cầu bảo trì pipeline/OOB,
      cần diễn tập và quan sát per-device effective state.

## Failure modes and residual risk
- HA sync sai, controller reapply desired state.
- Existing sessions/route convergence không revert tức thì.
- DNS caches và external partner NAT allowlists.

## Verification
- Test restore in staging; test loss-of-inband scenario in lab.
- Critical business positive và security negative controls.
- Cloud/Kubernetes path và HA version verification.

## Owners / date / review trigger
Architect, SOC, NOC, SRE, security approver.
Review khi vendor/firmware thay, topology đổi hoặc xảy ra incident.
~~~

Đây là **mẫu Markdown có nội dung giả định**, không phải quyết định đã được phê duyệt trong bất kỳ tổ chức nào.

### 25.2. So sánh lựa chọn theo tiêu chí

| Tiêu chí | Manual revert | Native commit-confirmed | Versioned IaC + gated rollout | Snapshot restore |
|---|---|---|---|---|
| **Auditability** | Phụ thuộc thao tác/logs | Commit history theo platform | Cao nếu protected repository/pipeline | Snapshot history theo platform |
| **Mất in-band connection** | Cần OOB/manual access | Có thể tự revert sau timeout | Vẫn cần OOB nếu control path hỏng | Cần recovery channel |
| **Multi-device consistency** | Khó khi nhiều thiết bị | Không luôn atomic cross-device | Cần orchestration/per-component state | Có thể overwrite nhiều dependency |
| **Semantic policy tests** | Thường ngoài công cụ | Cần bổ sung | Dễ tích hợp vào pipeline | Cần bổ sung |
| **Concurrent changes** | Dễ rollback nhầm | Platform-specific conflict handling | Git diff/rebase/reconcile rõ hơn | Có nguy cơ xóa changes mới |
| **Data-plane/session state** | Không tự xử lý | Không tự xử lý | Không tự xử lý | Không tự xử lý |
| **Tốc độ thao tác** | Tùy nhân sự | Có thể nhanh khi hỗ trợ | Nhanh nếu pipeline mature | Có thể nhanh nhưng risk cao |
| **Chi phí vận hành** | Training/on-call | Vendor feature/training | CI/CD, policy model, controllers | Storage/restore drills |
| **Tính di động** | Cần thay CLI theo hãng | Vendor-dependent | IaC abstractions vẫn cần provider specifics | Snapshot thường vendor/version-bound |
| **Security recovery evidence** | Cần thiết kế riêng | Có config history | Có thể gắn test artifacts | Cần chứng minh sau restore |

**Không có một phương án thắng trong mọi môi trường.** Với edge quan trọng, các cơ chế thường phải **bổ sung nhau**; vendor-native features giảm lỗi config, GitOps cung cấp review/audit, OOB xử lý khi mạng quản trị đã hỏng và runtime tests chứng minh kết quả.

### 25.3. Decision scoring chỉ là hỗ trợ

Có thể chấm từng lựa chọn trên các trục **security recovery**, **operational reliability**, **time to verify**, **multi-system coordination**, **cost**. Nhưng nếu phương án không đáp ứng tiêu chí tối thiểu **“không thể khôi phục khi mất in-band management”**, không được chọn chỉ vì điểm tổng cao.

Nên tách:

- **Non-negotiable safety gates:** không khôi phục credential bị lộ, có authorization, có security tests, management rescue khả thi.
- **Weighted trade-offs:** chi phí, thời gian, công cụ hiện có, maintainability.
- **Known residual risks:** drift, external dependencies và session handling.

## 26. Mức trưởng thành của rollback architecture

| Cấp độ | Đặc điểm | Rủi ro còn tồn tại | Bước cải tiến tiếp |
|---|---|---|---|
| **0 — Ad hoc** | Operator ghi nhớ lệnh ngược; backup không đều | Revert sai, không biết trạng thái | Inventory, versioned backups |
| **1 — Documented** | Change ticket và rollback steps có owner | Chưa chứng minh restore hoạt động | Restore drill, OOB test |
| **2 — Repeatable** | Checkpoints, consistent approvals, pre/post tests | Dependency coverage chưa đủ | Policy simulation, canary |
| **3 — Controlled** | Candidate/commit features, semantic review, gates | Multi-device and runtime gaps | Per-component reconciliation, state tests |
| **4 — Resilient** | OOB, rollback orchestration, evidence-rich monitoring, drills | External/common-mode failures | Chaos/tabletop, continuous risk review |

Đây là **khung trưởng thành tự xây dựng cho bài học**, không phải điểm số chứng nhận hay tiêu chuẩn chính thức. Một tổ chức có thể có các mức khác nhau ở từng vùng mạng.

### 26.1. Câu hỏi chấm readiness

1. Biết **cấu hình nào đang thực thi** trên mỗi router/firewall/node?
2. Có bản snapshot/desired state **được hash và kiểm quyền**?
3. Có thể khôi phục nếu route/AAA/VPN chính lỗi?
4. Có thể revert **một change** mà không xóa changes hợp lệ khác?
5. Có negative tests cho trust boundaries quan trọng?
6. Có visibility về **sessions/HA convergence/RIB/FIB/route paths**?
7. Có runbook khi **automation/commit-confirmed không hoạt động**?
8. Đã diễn tập restore ở lab tương ứng firmware/architecture?
9. Có audit ai approve/execute/verify rollback?
10. Có close-out cho emergency exception/temporary remediation?

Một câu trả lời “chúng tôi có file backup” chỉ đạt một phần rất nhỏ của readiness.

## 27. Các chỉ số đo độ tin cậy của rollback

### 27.1. Nhóm chỉ số cần theo dõi

| Metric | Định nghĩa gợi ý | Diễn giải cẩn trọng |
|---|---|---|
| **Rollback readiness coverage** | % critical devices/paths có tested restore + OOB + gates | Định nghĩa “tested” và mẫu số rõ |
| **Verified rollback success rate** | % tình huống rollback đạt all acceptance criteria | Không tính CLI success thay business/security |
| **Time to verified recovery** | Từ trigger tới security + business sign-off | Bao gồm convergence và validation |
| **Time to contain exposure** | Từ phát hiện unauthorized reachability tới khi chặn có evidence | Khác service recovery time |
| **Rollback trigger detection latency** | Từ failure onset tới alert/decision | Onset có thể khó xác định |
| **Out-of-band recovery availability** | % drill OOB thành công theo scope | Không bảo đảm ở mọi disaster |
| **Backup restore pass rate** | % versioned artifacts restore đúng trong lab | Snapshot existence không đủ |
| **Policy invariant coverage** | % critical boundaries có negative tests | Không có test không nghĩa đang an toàn |
| **Concurrent-change reconciliation rate** | % rollback không ghi đè changes hợp lệ | Cần version/change ancestry rõ |
| **Post-rollback drift count** | Desired/effective mismatches sau recovery | Phân biệt intentional exception |
| **Residual exposure duration** | Thời gian trust boundary sai còn tồn tại | Có thể tiếp tục sau config revert |
| **Repeat failure rate** | Sự cố cùng nguyên nhân tái phát | Cần action tracking đến validation |

### 27.2. Đừng thưởng cho ít rollback một cách tuyệt đối

Nếu KPI là “0 rollback” hoặc “deploy không phải revert”, đội có thể:

- Bỏ qua negative tests để không phát hiện lỗi.
- Gọi roll-forward chưa kiểm chứng là completed.
- Cố duy trì policy không an toàn vì sợ bị ghi nhận failure.
- Không diễn tập đường rollback thực tế.

Đánh giá tốt phải cân bằng **change failure rate, time-to-recover, customer impact, security regression và evidence quality**. Một rollback sớm, đúng và giới hạn blast radius có thể là dấu hiệu **kiến trúc đang hoạt động đúng**.

### 27.3. Tính thời gian theo các mốc rõ

~~~text
T0 = change begins
T1 = first observed regression
T2 = rollback trigger confirmed / decision made
T3 = revert/compensating action applied
T4 = data-plane convergence verified
T5 = business + security gates signed off
T6 = incident/change closure (có thể trễ hơn nhiều)

Detection latency = T1 - actual onset (nếu biết)
Decision latency  = T2 - T1
Execution time    = T3 - T2
Convergence time  = T4 - T3
Verification time = T5 - T4
Verified rollback duration = T5 - T2 (nếu định nghĩa từ trigger)

Các mốc là ví dụ; clock offsets và ingest delay cần được ghi.
~~~

**T5 quan trọng hơn T3** cho đánh giá khả năng phục hồi thực tế.

## 28. Threat model: 28 nguyên nhân rollback mất an toàn

| ID | Rủi ro | Hậu quả | Thiết kế giảm thiểu |
|---|---|---|---|
| RB01 | **Backup không tồn tại** | Không có điểm quay lại | Automated backups + monitoring |
| RB02 | **Backup có nhưng không restore được** | Recovery thất bại khi cấp bách | Version-specific restore drills |
| RB03 | **Backup chứa plaintext secrets** | Rò rỉ credentials/topology | Encryption/RBAC/audit |
| RB04 | **Mất in-band management** | Không thao tác revert | Independent OOB / timed revert |
| RB05 | **OOB phụ thuộc cùng IdP/VPN** | Common-mode failure | Break-glass and independence review |
| RB06 | **Confirm commit quá sớm** | Mất timed rollback trước khi test | Business+security gates before confirm |
| RB07 | **Partial commit nhiều thiết bị** | Blackhole/exposure | Per-device state and recovery graph |
| RB08 | **Concurrent changes** | Revert xóa fix hợp lệ | Targeted diff/reconcile |
| RB09 | **GitOps reapply bad config** | Manual emergency revert bị overwrite | Controlled reconciliation |
| RB10 | **HA sync sai / cả hai đều sai** | Failover không có tác dụng | Independent checkpoint and node checks |
| RB11 | **Sessions cũ còn mở** | Quyền trái phép còn tồn tại | Existing-flow validation and scoped revoke |
| RB12 | **NAT mappings tồn tại** | Source attribution/connectivity khác | State monitoring and mapping analysis |
| RB13 | **Old public IP bị reassigned** | Rollback ngoài quyền/resource | Ownership checks, alternative design |
| RB14 | **BGP chưa hội tụ** | Prefix leak/blackhole | RIB/FIB/peer verification |
| RB15 | **Route return asymmetry** | Firewall stateful drop | Bidirectional path analysis |
| RB16 | **DNS caches chưa hết TTL** | Some clients vẫn tới backend sai | Dual-backend/TTL/runout plan |
| RB17 | **Old CA/credential compromised** | Khôi phục quyền attacker | Safe new trust state |
| RB18 | **Policy rộng khác còn tồn tại** | Deleting rule không deny | Effective policy/union analysis |
| RB19 | **IPv6 bị bỏ qua** | Bypass security invariant | Dual-stack scope/tests |
| RB20 | **Inspection path bị bypass** | Mất IDS/IPS/WAF coverage | End-to-end path verification |
| RB21 | **Cloud propagation delay** | API success nhưng rule chưa active | Effective state + flow test |
| RB22 | **CNI dataplane drift** | Manifest rollback không enforce | CNI verdict/node coverage |
| RB23 | **Mesh retries/session stickiness** | Traffic vẫn dùng old/new backend | Proxy/session monitoring |
| RB24 | **Negative test chỉ có timeout** | Tưởng deny PASS | Healthy destination and enforcement verdict |
| RB25 | **Sensor pipeline outage** | Không thể chứng minh restoration | Heartbeat and independent telemetry |
| RB26 | **Emergency bypass quên gỡ** | Cửa hậu dài hạn | Owner, expiry, cleanup audit |
| RB27 | **Rollback test trên production thiếu safety** | Gây outage hoặc mất dữ liệu | Staging/tabletop/approved window |
| RB28 | **Đóng change khi CLI success** | Không phát hiện exposure còn sót | Independent sign-off, runtime gates |

### 28.1. Các rủi ro cần phân loại theo mức

Hậu quả của RB04 (mất OOB) ở lab thường là trì hoãn, nhưng trên critical OT/safety infrastructure có thể rất nghiêm trọng. RB17 (khôi phục trust đã compromise) có thể duy trì unauthorized access dù dịch vụ khỏe. **Rủi ro phải được lượng giá theo tài sản và context**, không chấm cố định bằng mã ID.

### 28.2. Phân biệt sự cố mới và lỗi rollback

Nếu trong lúc rollback xảy ra một lỗi DNS độc lập, có thể phải mở incident phụ hoặc hợp nhất theo governance. Không ép tất cả các lỗi cùng time window thành hậu quả của rollback nếu thiếu evidence. Timeline, change logs, approved actions và cross-source telemetry giúp quy nguyên nhân.

## 29. Troubleshooting: rollback xong nhưng hệ thống vẫn bất thường

| Triệu chứng | Giả thuyết cần phân biệt | Hành động quan sát an toàn |
|---|---|---|
| Git đã revert nhưng flows vẫn sai | Controller chưa reconcile, apply failed, policy layer khác | Desired vs actual vs effective versions |
| Firewall rule cũ đã phục hồi nhưng U vẫn vào DB | Existing session, allow khác, bypass path | Session/flow verdict + enumerate rules |
| New sessions bị deny nhưng old session vẫn sống | Stateful policy semantics | Scoped session lifecycle review |
| BGP neighbor Established nhưng traffic timeout | Prefix không đúng, FIB chưa hội tụ, route return sai | RIB/FIB, import/export, bidirectional flows |
| Route đã revert nhưng management SSH không vào được | AAA/VRF/source ACL/session/PBR vẫn lỗi | OOB console, audit, route get |
| HA active OK nhưng failover gây outage | Standby config stale/same bad config, capacity thiếu | Per-node versions, HA health |
| NAT pool restore nhưng partner API thất bại | IP old invalid, partner allowlist, existing sessions | Resource ownership, NAT/flow + partner logs |
| DNS authoritative đúng nhưng một vùng vẫn lỗi | Resolver cache, split DNS, AAAA/HTTPS record | Multi-view DNS/app logs, TTL |
| TLS handshake lỗi sau rollback trust | CA đã revoke/expired, SAN mismatch, clock skew | Safe PKI validation, no insecure mode |
| VPN user vào được nhưng app không | Selectors/route/DNS/IdP/AuthZ mismatch | VPN gateway/app logs, approved flow tests |
| Cloud SG API trả success nhưng public exposure còn | Propagation, other SG/NACL/route, direct origin | Effective attachments and external controlled tests |
| CNI NetworkPolicy đã revert, Pod vẫn reachable | Additive allow, hostNetwork, wrong selector, CNI failure | All policies + CNI verdict |
| Service mesh rollback mà requests vẫn tới canary | Sticky connections, retries, gateway state | Proxy/route and request ID logs |
| Route khôi phục nhưng IDS không thấy traffic | Path bypass, tunnel, sensor outage | Flow path and collector heartbeat |
| App trả 200 nhưng DB có truy cập trái quyền | Missing security negative tests | DB/ACL policy, identity/app audit |
| Rollback làm mất một security fix gần đây | Snapshot cũ, concurrent change not merged | Version ancestry and change graph |
| Recovery kéo dài bất thường | Convergence, auto-reapply, stale sessions, dependencies | Timeline by component and health |
| Tất cả logs im lặng | Monitoring outage hoặc không có traffic | Independent heartbeat and known-good control |
| PCAP không thấy response | Wrong interface/filter, asymmetric route, packet drops | Capture scope, counters, logs |
| Một region recovered, region khác chưa | Per-region policy propagation/route attachments | Region-specific effective tests |

### 29.1. Chẩn đoán theo đúng lớp

~~~mermaid
flowchart TD
    START["Rollback command reported success"] --> D{"Desired/running versions match target?"}
    D -->|"Không"| CFG["Reconcile controller/device versions"]
    D -->|"Có"| P{"Dataplane path + sessions correct?"}
    P -->|"Không"| FLOW["Inspect RIB/FIB/NAT/HA/session/CNI"]
    P -->|"Có"| S{"Business + security gates PASS?"}
    S -->|"Không"| DEP["Check DNS/TLS/IAM/app/alternate paths"]
    S -->|"Có"| AUD{"Telemetry & audit healthy?"}
    AUD -->|"Không"| LOG["Restore observability / independent verification"]
    AUD -->|"Có"| DONE["Verified recovery with sign-off"]
    CFG --> P
    FLOW --> S
    DEP --> AUD
~~~

Không biến sơ đồ thành vòng lặp tự động vô hạn: mỗi lần retry cần xác minh state, giới hạn thời gian và người chịu trách nhiệm; khi có active harm phải chuyển incident response.

## 30. Lệnh chỉ đọc hỗ trợ xác minh trong lab

Không có một lệnh chung trên mọi router/firewall. Cisco, Junos, FortiOS, PAN-OS, VyOS, FRRouting, cloud và CNI đều có CLI/API/policy semantics riêng. Chỉ sử dụng **show/get/list/describe** tương ứng theo tài liệu phiên bản thực và quyền của bạn; không áp lệnh cấu hình chỉ để kiểm chứng.

### 30.1. Linux: routing, source path và interface status

~~~bash
# Chỉ đọc trạng thái host Linux thuộc quyền.
ip -br address
ip -4 route show
ip -6 route show
ip rule show
ip -s link show

# Route decision của chính Linux host, không đại diện mọi router upstream.
ip -4 route get 198.51.100.20
ip -6 route get 2001:db8:20::20

# Read-only TCP sockets; không làm thay đổi connections.
ss -tan
~~~

**Không suy route table trên host là toàn bộ đường end-to-end** nếu có VRF, container namespace, PBR, tunnels hoặc stateful firewall ở giữa.

### 30.2. Windows: network snapshot read-only

~~~powershell
Get-NetIPConfiguration
Get-NetRoute | Select-Object DestinationPrefix, NextHop, InterfaceAlias, RouteMetric
Get-DnsClientServerAddress
Get-NetTCPConnection | Select-Object LocalAddress, LocalPort, RemoteAddress, RemotePort, State
Get-Date -Format o
~~~

Output có thể chứa IP nội bộ, DNS và active sessions; áp data classification và không đưa nguyên văn vào kênh public.

### 30.3. Kubernetes API state

~~~bash
# Chỉ trên cluster/namespace lab hoặc tài sản được ủy quyền.
kubectl config current-context
kubectl get networkpolicy -n orders
kubectl get pods -n orders -o wide
kubectl get services -n orders
kubectl get endpointslices -n orders
kubectl get events -n orders --sort-by=.lastTimestamp
~~~

Các lệnh này giúp đọc **API state**; không chứng minh CNI đã enforce hoặc Pod traffic thực sự đi qua đâu. Khi cần xác minh policy deny, cần **CNI flow verdict và một known-good positive control** trong phạm vi thử nghiệm.

### 30.4. Firewall/router từ các sản phẩm khác nhau

Một runbook nên ghi **loại trạng thái phải đọc**, thay vì giả định command chung:

~~~text
Device-specific read-only inventory:
  - Running/candidate/committed configuration version
  - Configuration history/checkpoints
  - HA roles, config sync, health state
  - Firewall effective rules and session table
  - NAT mappings and translation failures
  - Routing table, RIB/FIB, VRF, BGP/OSPF neighbors
  - Interface errors, drops, utilization and MTU
  - AAA/admin sessions and syslog delivery

Actual commands:
  Must be selected and approved for vendor + OS version.
~~~

**Ngay cả các lệnh “show” có thể in secrets hoặc dữ liệu nhạy cảm** nếu toàn bộ config được hiển thị. Ưu tiên hạn chế fields và access scope.

### 30.5. Không nhầm debug với sửa lỗi

Trong bài học này không cần:

- Thay route mặc định trên production.
- Clear toàn bộ firewall sessions hoặc BGP neighbors.
- Reboot HA node để “thử rollback”.
- Tắt TLS certificate verification, IPS hoặc MFA.
- Export plaintext full running config lên chat.
- Flush DNS caches toàn tổ chức khi chưa có impact approval.
- Xóa CNI/eBPF dataplane state thủ công.

Các thao tác đó có thể biến validation thành sự cố thứ hai. Nếu bắt buộc, phải có **runbook vendor-specific, quyền và change/incident approval** riêng.

## 31. Tình huống thực tế mô phỏng: rollback firewall và route không đồng bộ

### 31.1. Bối cảnh

Hệ thống Orders chạy qua hai vùng:

~~~mermaid
flowchart LR
    WEB["Web clients"] --> LB["Public LB/WAF"]
    LB --> API["Orders API / zone-app"]
    API --> FW["HA firewall pair"]
    FW --> RT["Core router / VRF-data"]
    RT --> DB["PostgreSQL / zone-data"]
    OOB["Independent OOB / break-glass"] -.-> FW
    OOB -.-> RT
    SOC["SOC / NOC / SRE logs"] -.-> FW
    SOC -.-> RT
~~~

Yêu cầu hợp lệ: **Orders API** tới DB TCP/5432, guest/untrusted zone bị chặn. Thay đổi C12 gồm:

1. Firewall object group cho phép một source list mới.
2. Một static/PBR route thay path tới data zone.
3. NAT exemption mới cho flow trong VPN service.

Các bước được triển khai qua ba công cụ khác nhau; không có distributed transaction chung.

### 31.2. Timeline giả định

| Thời gian tương đối | Sự kiện | Nhận định |
|---|---|---|
| T-30m | Backup/config versions, OOB và baseline test hoàn tất | Đã có recovery preconditions |
| T0 | Firewall object group deploy | Một nhóm source ngoài ý định cũng được allow |
| T+2m | Route steering sang path mới | API kết nối được DB, nhưng security inspection bypass |
| T+4m | NAT exemption apply ở một gateway; gateway còn lại pending | Partial commit |
| T+6m | Negative test từ untrusted zone tới DB **thành công** | Security invariant fail |
| T+7m | IC/change authority dừng mở rộng rollout | Đúng response |
| T+8m | Workflow Git revert object group | Desired state thay; runtime chưa nhất quán |
| T+10m | HA active/standby nhận khác effective rules; old session còn | Chưa thể sign off |
| T+13m | Targeted reconcile route/NAT/firewall với approver | Khôi phục theo dependency graph |
| T+18m | Business positive và security negative tests PASS | Service + policy recovery |
| T+22m | SIEM/HA/RIB/FIB/flow monitoring xác nhận | Verified rollback |

Đây là **kịch bản hư cấu**, thời gian chỉ để học phân tích; không có ngưỡng SLA mặc định.

### 31.3. Ba thất bại cần tách

1. **Policy exposure:** object group mới rộng hơn approval, untrusted source được phép.
2. **Data-plane bypass:** route mới bỏ qua inspection path mong muốn.
3. **Partial state:** NAT và HA/candidate versions không đồng nhất khi revert.

Một Git revert có thể sửa (1) trên desired state nhưng **không tự sửa (2), (3)**. Nếu chỉ nhìn control plane, đội vận hành có thể tuyên bố “đã rollback” quá sớm.

### 31.4. Kế hoạch ứng phó hợp lý

- **Stop rollout**, bảo toàn before/after config snapshots, event timestamps và source/NAT logs.
- Contain unauthorized DB path trong phạm vi cần thiết và có rollback/incident authority.
- Xác định safe target giữ nguyên các security fixes hợp lệ khác.
- Kiểm OOB và per-device effective version, HA state.
- Targeted revert route steer/policy/NAT theo dependency graph, kiểm cả return path.
- Xem xét established sessions tạo khi policy quá rộng và xử lý theo platform/approval.
- Chạy positive control (Orders API→DB, DNS, auth, monitoring) và negative controls (guest/Internet→DB, IPv6, alternate route).
- Chỉ sign off khi business SLO, security denials, sensors và audit đều có evidence.

### 31.5. Không suy dữ liệu đã bị lấy

Một unauthorized connection được phép chứng minh **exposure/unauthorized reachability**, không tự chứng minh data exfiltration. Nếu có chứng cứ truy cập database, phối hợp application/DB audit, SOC và privacy/legal theo incident response; không đợi rollback xong mới xử lý dữ liệu nhạy cảm.

## 32. Bài tập so sánh hai kiến trúc rollback

### Kiến trúc A — Backup thủ công và SSH

- Một bản backup hằng tuần trong kho nội bộ.
- Không có commit-confirmed/timed revert.
- Management plane truy cập qua cùng default route.
- Rollback thực hiện từng thiết bị, không ghi version linkage.
- Có app smoke test nhưng không có security negative tests.

### Kiến trúc B — Revisions, gates và OOB

- Versioned desired state, per-device checkpoints, restore drill.
- Candidate/timed revert nơi platform hỗ trợ.
- Independent OOB có MFA/break-glass và audit.
- Canaries/phased rollout, per-device effective-state checks.
- Positive business và negative security tests.
- Reconcile concurrent changes, expiry emergency policies.

**Câu hỏi:**

1. Kiến trúc nào có **rollbackability** tốt hơn và vì sao không thể chỉ dựa vào số phút chạy lệnh?
2. Nếu backup tuần trước đã chứa một certificate bị revoke, có nên restore nguyên trạng?
3. Mạng có single router và không thể canary: nên bổ sung những kiểm soát nào?
4. Nếu Git đã revert nhưng controller tự áp lại phiên bản lỗi, thiếu control nào?
5. Nếu HA standby đã sync bad config, failover giúp gì?
6. Nếu rule mới bị xóa nhưng established sessions vẫn truy cập được DB, test còn thiếu gì?
7. Khi DNS đã rollback nhưng clients còn cache, recovery plan cần gì?
8. Một IP NAT cũ đã bị release, vì sao rollback pool cũ không an toàn?
9. Nên lưu những mốc nào để tính **verified recovery time**?
10. Hãy viết một đoạn ADR chọn phương án phù hợp với edge service của một doanh nghiệp vừa, nêu trade-offs và residual risk.

**Gợi ý:** Kiến trúc B thường dễ kiểm soát hơn vì có **đường cứu hộ, versioned recovery target và verification gates**. Nhưng vẫn có thể thất bại khi cloud/controller external state khác hoặc OOB cùng failure domain. Một quyết định tốt cần ghi **rủi ro còn lại**, không tuyên bố “đã có hệ thống rollback tự động nên chắc chắn an toàn”.

## 33. Checklist ra quyết định và vận hành rollback

### 33.1. Thiết kế kiến trúc trước khi có sự cố

- [ ] Có sơ đồ topology, trust boundaries, critical flows, owners và dependencies.
- [ ] Đã định nghĩa **safe rollback target**, không mặc định “snapshot cũ nhất”.
- [ ] Phân biệt desired/candidate/running/committed, RIB/FIB và actual data-plane state.
- [ ] Có versioned config, encrypted backups, hashes và restore compatibility check.
- [ ] Backup đã được **thử restore** trên môi trường phù hợp, không chỉ lưu trữ.
- [ ] Có independent management/OOB path hoạt động khi route/VPN chính hỏng.
- [ ] Break-glass access có RBAC, audit, credential protection và quy trình đóng.
- [ ] Có phương án khi commit-confirmed/timed revert **không được vendor hỗ trợ**.
- [ ] Có per-device/region/state audit cho HA và multi-device deployments.
- [ ] Đã mô tả common-mode failures giữa in-band và out-of-band.
- [ ] Có Git/IaC desired state và cơ chế reconcile emergency/manual changes.
- [ ] Có kế hoạch tránh snapshot restore xóa các security fixes hợp lệ mới hơn.
- [ ] Có phương án **roll-forward/compensating controls** nếu rollback unsafe.
- [ ] Thiết kế security gates cho IPv4/IPv6, VPN/peering, alt routes và management.
- [ ] Có ownership và review chu kỳ cho emergency exception/temporary policy.
- [ ] ADR ghi các phương án, trade-offs, rủi ro tồn dư và acceptance criteria.

### 33.2. Trước khi áp change có khả năng phải rollback

- [ ] Change ID, affected assets, blast radius, approval và implementation owner rõ.
- [ ] Xác định source/destination identity, NAT, routing, firewall zones/objects.
- [ ] Xác định các thành phần **không rollback nguyên tử** cùng thiết bị.
- [ ] Kiểm per-device versions, HA health, controller sync, route neighbor states.
- [ ] Snapshot/config artifacts có thể truy cập qua recovery path nếu mất in-band.
- [ ] Đã ghi concurrent changes, dependency graph, route return path và commit windows.
- [ ] Có baseline SLO/app health và critical business positive tests.
- [ ] Có negative tests cho unauthorized segments/identities/IPv6 paths.
- [ ] Có telemetry/counters/flow logs, log pipeline heartbeat và time sync.
- [ ] Có rollback triggers dựa trên **security/availability/observability**.
- [ ] Có canary/phased rollout hoặc cách bù trừ khi không thể canary.
- [ ] Có người chịu trách nhiệm ra quyết định pause/revert/roll-forward.
- [ ] Đã thử OOB và emergency stop procedure trong lịch/phạm vi được phép.
- [ ] Không yêu cầu tool/trust bypass, privileged access hoặc exploit ngoài scope.

### 33.3. Khi rollback đang diễn ra

- [ ] Dừng rollout tiếp theo, ghi quyết định và thời điểm trigger.
- [ ] Xác định safe target theo **changes hợp lệ gần nhất**, không dùng snapshot mù.
- [ ] Nếu có active harm, phối hợp containment và incident command.
- [ ] Phân biệt **config revert** với **runtime/session convergence**.
- [ ] Áp hành động theo dependency graph và vendor-specific approved runbook.
- [ ] Khi mất in-band, dùng OOB/timed revert thay vì gửi lệnh mù.
- [ ] Ghi applied versions và transaction status theo từng device/region/node.
- [ ] Giám sát HA roles, policy sync, BGP/OSPF, RIB/FIB, NAT và session tables.
- [ ] Không reset toàn bộ sessions/routers/PKI trust nếu chưa đánh giá impact.
- [ ] Đảm bảo controller/GitOps không ghi đè rescue changes sai thời điểm.
- [ ] Giữ identity revocations và security fixes phải tồn tại sau rollback.
- [ ] Kiểm DNS TTL/cache, TLS trust, external partner allowlists và cloud resource ownership.
- [ ] Có health checks và khả năng dừng khi xuất hiện failures ngoài dự kiến.
- [ ] Bảo toàn evidence, config diffs, audit logs và action timeline.

### 33.4. Sau rollback — xác minh mới là kết thúc

- [ ] Đúng **effective config version**, không chỉ CLI báo success.
- [ ] Per-node HA đồng nhất và routing dataplane đã hội tụ theo tiêu chí.
- [ ] NAT session/translation có source/destination hợp lệ, không còn stale exposure.
- [ ] Business positive tests PASS: app/API/DB, DNS, identity, telemetry.
- [ ] Security negative tests PASS tại **đúng enforcement point**, có healthy control.
- [ ] Unauthorized existing sessions được đánh giá hoặc chấm dứt theo policy.
- [ ] IPv4 và IPv6, alternate VPN/peering, management paths không bypass security.
- [ ] TLS/mTLS verification và access-control boundaries không bị giảm để “phục hồi”.
- [ ] Cloud/Kubernetes/service mesh actual state được kiểm, controller drift đã reconcile.
- [ ] SLO/error rate, packet loss/latency, route stability trong monitoring window.
- [ ] Evidence có actor/time/commit IDs, per-component applied states và integrity digests.
- [ ] Emergency exceptions có owner/expiry; rollback không làm mất security fixes khác.
- [ ] Business owner, security reviewer và incident/change authority sign off.
- [ ] Ghi những limits, untested regions và accepted residual risks với người chịu trách nhiệm.
- [ ] Post-incident review có root cause/contributing factors, action item và replay test.

## 34. Những câu cần hỏi trong buổi review kiến trúc

Nếu chỉ có vài phút cho một cuộc thảo luận về rollbackability, ưu tiên những câu sau:

1. **“Nếu cấu hình này làm mất luôn đường quản trị thì ai và bằng đường nào có thể cứu?”**
2. **“Trạng thái nào là trạng thái an toàn để trở về, và có security fix nào không được mất?”**
3. **“Nếu chỉ một trong năm thiết bị áp thành công thì hệ thống nằm ở trạng thái gì?”**
4. **“Controller, HA, DNS caches, NAT sessions và route convergence sẽ hành xử thế nào sau revert?”**
5. **“Làm sao chứng minh luồng bị cấm đã bị chặn mà không nhầm timeout với firewall deny?”**
6. **“Nếu rollback không khả thi, có phương án roll-forward hoặc compensating control an toàn không?”**
7. **“Đã thực sự thử khôi phục ở lab nào tương thích với phiên bản production?”**
8. **“Điểm kết thúc là command success, service SLO, hay security + business sign-off?”**
9. **“Ai là người ra quyết định và ai xác minh độc lập khi có sự cố?”**
10. **“Phần nào của plan còn là giả định chưa từng được kiểm tra?”**

Nếu không thể trả lời, ADR nên ghi **design gap** và ưu tiên xử lý trước thay đổi có blast radius lớn.

**Ghi nhớ:** **Khả năng rollback cấu hình mạng là năng lực phục hồi kiến trúc được thiết kế trước, đo bằng trạng thái đã được xác minh sau thay đổi — không phải sự tồn tại của backup, câu lệnh revert hay một nút Undo.** Cần **safe target, versioned restore, đường OOB, phân tích phụ thuộc nhiều thiết bị, kiểm soát session/NAT/routing/HA và các cloud/Kubernetes/DNS/PKI dependencies**, cùng **canary, rollback triggers, positive business và negative security tests, audit và diễn tập thường xuyên**. Nếu quay về trạng thái cũ làm mở lại lỗ hổng, hãy chọn **roll-forward hoặc compensating control có phê duyệt** thay vì đánh đổi an toàn để đạt “rollback success”.
