# Khoanh vùng máy chủ hoặc subnet khi ứng phó sự cố mạng

## 1. Vì sao cần khoanh vùng trong một sự cố mạng?

Một máy chủ Production bị phát hiện mở kết nối tới đích chưa phê duyệt; đồng thời, những máy khác cùng mạng xuất hiện đăng nhập quản trị bất thường. Nếu đội ứng phó chỉ **tắt cảnh báo** hoặc **khởi động lại máy**, kẻ tấn công có thể tiếp tục dùng credential bị đánh cắp để di chuyển sang nơi khác. Nếu vội **ngắt toàn bộ subnet**, dịch vụ thanh toán, hệ thống xác thực và kênh giám sát có thể cùng gián đoạn. Đây là bài toán **network containment**: giới hạn đường đi của rủi ro một cách **hiệu quả, có bằng chứng, ít tác động nhất có thể và có cơ chế khôi phục an toàn**.

Thuộc chương **Ứng phó sự cố mạng** của module **SECURITY_NETWORK_SECURITY**, chủ đề này kết hợp phân đoạn mạng, firewall, VPN, IDS/IPS, DNS, bảo mật cloud, quan sát lưu lượng và mô hình hóa mối đe dọa. Tính chất của laptop bị nhiễm malware, virtual machine, Kubernetes worker node, domain controller, database subnet và mạng OT/IoT rất khác nhau. Vì vậy, **không có một thao tác cô lập chung cho mọi hệ thống**.

### Mục tiêu học tập

1. Phân biệt **containment, host isolation, subnet quarantine, eradication và recovery**.
2. Lựa chọn phạm vi **máy chủ, port, flow, VLAN/subnet, security zone** dựa trên risk và blast radius.
3. Hiểu cơ chế thực thi bằng **EDR, NAC/802.1X, switch ACL, firewall, cloud SG/NACL, VPN/ZTNA, hypervisor, Kubernetes CNI/NetworkPolicy**.
4. Đánh giá **east-west, local L2, IPv4/IPv6, NAT, DNS, gateway, VPN và alternative interfaces**.
5. Bảo vệ **forensic evidence, identity/credential revocation, SOC visibility và business-critical dependencies**.
6. Thiết kế runbook, danh sách **ALLOW/DENY** có thể kiểm thử, cơ chế rollback và điều kiện phục hồi.
7. Thực hành **mô phỏng offline** và diễn tập các tình huống rủi ro khác nhau.

## 2. Khái niệm nền tảng và giới hạn

| Khái niệm | Ý nghĩa | Không nên nhầm |
| --- | --- | --- |
| **Containment/khoanh vùng** | Giảm đường giao tiếp hoặc quyền dùng trong thời gian incident | Malware/attacker đã bị loại bỏ |
| **Host isolation** | Hạn chế kết nối tới/từ một endpoint, server, VM hoặc workload | Đã vô hiệu hóa mọi credential mà host từng có |
| **Subnet quarantine** | Áp hạn chế ở subnet/prefix/VLAN/VRF/security zone | Tất cả máy trong subnet bị compromise |
| **Microsegmentation** | Kiểm soát luồng ở phạm vi workload/identity nhỏ | VLAN là phương pháp duy nhất |
| **Eradication** | Xử lý persistence, root cause, malware và lỗ hổng | Chỉ cắt được Internet |
| **Recovery** | Phục hồi dịch vụ từ trạng thái tin cậy và xác minh | Chỉ gỡ một firewall rule |
| **Blast radius** | Tập tài nguyên/tác vụ chịu ảnh hưởng bởi incident hoặc containment | Chỉ số IP bị chặn |
| **Quarantine zone** | Vùng có quyền hạn chế, thường còn đường remediation/DFIR nếu được phép | Mạng có quyền Internet tự do |
| **EDR isolation** | Tính năng agent giới hạn network connectivity theo product | Agent luôn đáng tin khi host/root đã bị chiếm |
| **NAC** | Network access control dùng identity/port/session posture | Application object authorization |
| **Control plane** | Thành phần triển khai rule/route/policy | Data plane thực sự đang chặn packet |
| **Data plane** | Host stack, switch, firewall, virtual network/CNI thực thi traffic | Rule vừa được lưu là đã áp mọi nơi |

### 2.1. Cô lập mạng không thay thế thu hồi quyền

Nếu attacker đã lấy **API token, cloud STS session, VPN credentials, mTLS private key hoặc database password** từ host, bản sao có thể được dùng tại nơi khác. Khi cần, phải phối hợp **IAM revoke, session invalidation, account disable, application resource authorization và credential rotation**. Xóa VM/Pod hoặc đóng NIC không tự thu hồi external tokens.

### 2.2. Network reachability khác application authorization

Một firewall chỉ cho phép TCP/443 tới Payments không thể biết request ấy có **quyền hoàn tiền cho người dùng khác** không. Ngược lại, API có xác thực mạnh vẫn cần giới hạn đường vào để giảm lateral movement. Containment nên kết hợp **L3/L4 network controls và L7/workload identity** tùy threat model.

## 3. Quyết định cô lập host hay subnet

| Bối cảnh có bằng chứng | Phương án nên đánh giá | Ưu thế | Đánh đổi |
| --- | --- | --- | --- |
| Một laptop có EDR malware alert đáng tin | **Host EDR isolation** | Đúng đối tượng, tác động hẹp | Agent bị lỗi/tamper, Wi-Fi/other NIC, đường ngoại lệ |
| Một VM cloud nghi bị compromise | **VM/ENI SG + IAM revoke** | Giới hạn network của instance | Shared SG, active flows, cloud control-plane lag |
| Một Pod có runtime alert; các replica khác sạch | **Pod-/namespace-level policy** | Giữ dịch vụ qua replicas còn lại | CNI enforcement, label/selector drift, node compromise |
| Nhiều máy cùng VLAN lan truyền malware | **Subnet/VLAN zone containment** | Ngăn fan-out trong vùng | Phụ thuộc chung, L2 traffic, business disruption |
| Switch edge có thiết bị lạ | **NAC port quarantine/role change** | Khống chế trước khi vào mạng | Nhầm uplink/trunk, alternate Wi-Fi, MAC spoofing |
| Database subnet có dịch chuyển ngang | **Internal firewall/microsegmentation** | Chặn unauthorized east-west | HA/quorum, backup/replication, rule order |
| Domain controller hoặc DNS nghi compromise | **Kế hoạch đặc thù + IC approval** | Giảm nguy cơ identity propagation | Cắt control dependency gây outage diện rộng |
| Telemetry mất từ một region | **Tăng giám sát/guardrails theo risk, chưa mặc định cắt region** | Tránh tự gây outage | Visibility gap cần xử lý ngay |

Không được dựa chỉ vào **IP address**: DHCP, NAT, cloud IP reuse, Kubernetes Pod churn và multi-homed endpoints có thể gây nhận dạng sai. Dùng **asset/instance/ENI/Pod UID, authenticated service identity, switch port, EDR agent ID** và historical time mapping.

### 3.1. Cây quyết định vận hành

~~~mermaid
flowchart TD
    S["Bằng chứng an ninh mới"] --> C{"Compromise/lan truyền đang diễn ra với confidence cao?"}
    C -- "Không chắc" --> E["Giữ chứng cứ, tăng telemetry và khoanh luồng hẹp nếu phù hợp"]
    C -- "Có" --> I{"Định danh chính xác host/workload?"}
    I -- "Có" --> H["Cô lập host/workload + revoke credentials liên quan"]
    I -- "Không" --> Z["Xác định affected subnet / zone / paths"]
    Z --> B{"Lan truyền nghiêm trọng qua nhiều máy?"}
    B -- "Có" --> Q["IC phê duyệt subnet/zone containment có ngoại lệ tối thiểu"]
    B -- "Chưa" --> F["Chặn peer/protocol/egress được xác minh và mở điều tra"]
    H --> V["Verify DENY, necessary ALLOW, audit, reassess"]
    Q --> V
    F --> V
    E --> V
~~~

Sơ đồ là **khung phân tích**, không bắt buộc phải chờ hoàn tất mọi bước nếu malware/worm đang lan nhanh. Emergency containment theo quy trình có thể ưu tiên hành động trước rồi ghi lại approval/evidence ngay khi an toàn.

### 3.2. Cô lập theo giai đoạn

Có thể bắt đầu bằng **deny destination C2 hoặc một service protocol**, tiến tới host isolation nếu nguồn rủi ro chưa khống chế, rồi subnet quarantine nếu phát hiện nhiều host affected. Ngược lại, khi sự cố high-confidence có tốc độ lan truyền lớn, có thể phải chọn **zone-level emergency deny** trước, sau đó thu hẹp khi có evidence mới. Mọi bước phải có **scope, TTL/reassessment, owner và rollback plan**.

## 4. Ranh giới mạng trước/sau khi containment

### 4.1. Topology tham chiếu

~~~mermaid
flowchart LR
    U["User VLAN"] --> FW["Segmentation firewall"]
    FW --> A["App subnet / VLAN 30"]
    A --> DB["DB subnet"]
    A --> I["Identity/DNS/NTP/logging"]
    A --> E["Egress gateway/Internet"]
    X["Suspected host"] -. "Cùng app subnet" .-> A
~~~

Nếu hai host trong cùng broadcast domain giao tiếp trực tiếp qua **L2 switch**, một ACL chỉ ở **gateway router** có thể không nhìn thấy traffic đó. Cần kiểm tra **VLAN, host firewall, distributed virtual switch, private VLAN/port isolation và east-west enforcement**. Nếu app subnet có nhiều replicas, chặn tất cả dễ làm giảm availability không cần thiết.

### 4.2. Topology mong muốn sau containment

~~~mermaid
flowchart LR
    X["Suspected host"] --> P["Host/switch/firewall quarantine PEP"]
    P -->|"DENY"| R["Other hosts, DB, unauthorized Internet"]
    P -->|"ALLOW nếu được phê duyệt"| M["EDR/SOC/remediation services"]
    C["Clean app replicas"] --> F["Segmentation firewall"]
    F --> D["Production DB"]
~~~

**Sơ đồ là policy intent**, không khẳng định đã chặn thật. Cần xác minh traffic tại **enforcement points** và **đích**, gồm cả **IPv4/IPv6, Wi-Fi/other NIC, VPN/overlay, public IP/NAT, storage network và out-of-band management**.

## 5. Quyền quyết định và trách nhiệm của đội ứng phó

| Vai trò | Trách nhiệm chính |
| --- | --- |
| Incident commander | Phê duyệt phạm vi, ưu tiên security/availability, duy trì quyết định và tình trạng |
| SOC/DFIR | Kiểm chứng incident, IOC/TTP, timeline, bảo toàn bằng chứng |
| Network/firewall team | ACL, VLAN/VRF, route, firewall, NAT, kiểm tra data-plane |
| EDR/endpoint team | Isolate agent/device, host evidence, remediation status |
| Cloud/platform team | Cloud IAM/SG/NACL, VM, Kubernetes CNI, security zones |
| App/DB owners | Dependency, HA/quorum, transaction safety, service SLI |
| IAM/PKI | Disable accounts, revoke tokens/sessions, rotate keys/certs |
| NOC/SRE/observability | Đo outage, network/service SLO, alerting và recovery |
| Data owner/legal/privacy | Quy trình dữ liệu nhạy cảm/regulatory response khi áp dụng |

### 5.1. Record quyết định containment

~~~text
INCIDENT ID / UTC / SEVERITY:
Source of evidence, confidence, affected asset IDs:
Suspected threat: exfil / ransomware / lateral movement / unknown
Affected subnet/CIDR/VLAN/account/cluster/zone:
Authorized operator / approving incident commander:
Proposed isolation: PEP, direction, source, destination, protocol:
Approved exceptions for DFIR/remediation, including expiry:
Business dependencies, HA/DR and outage expectations:
Expected security DENY and necessary business ALLOW:
Evidence preservation / logs / verification:
Rollback condition, owner, reassessment time:
~~~

### 5.2. Emergency exception không phải mở cửa hậu vô hạn

Một security engineer có quyền sửa firewall không đương nhiên có thẩm quyền **ngắt cả subnet chứa domain controllers/production databases**. Cần **JIT permissions, MFA, break-glass audit, separation of duties** và emergency change procedure. Trong tình huống rủi ro đang lan nhanh, việc containment khẩn vẫn phải **ghi scope, thời điểm và hậu kiểm**.

## 6. Preflight: kiểm kê host, mạng và phụ thuộc

1. **Host identity:** EDR agent ID, VM/cloud instance/ENI, hostname, IP/MAC, switch port, Pod UID, ServiceAccount, region, owner.
2. **Time:** incident start, DHCP lease/NAT history, log event UTC, IP/Pod assignment validity.
3. **Topology:** L2 broadcast domain, gateway, VLAN/VRF, route, stateful firewall, SG/NACL/CNI, tunnel.
4. **Traffic flows:** ingress/egress, east-west, peer services, critical ports, return traffic, protocol versions.
5. **Dependencies:** DNS, DHCP, NTP, IdP/AD/Kerberos, KMS, EDR management, SIEM logs, backups, DB quorum/replication, monitoring.
6. **Availability:** replicas, active DB transactions, VIP failover, cluster quorum, long-lived TCP/gRPC sessions.
7. **Alternates:** IPv6, secondary NIC, Wi-Fi, VPN/split tunnel, storage network, BMC/out-of-band control.
8. **Control access:** Who can apply/read back rules when IdP or VPN is unavailable?
9. **Evidence:** volatile memory, active sockets, process tree, network flows, system/cloud audit and chain of custody.
10. **Recovery:** clean image, entitlement/credential rotation, policy rollback and ALLOW/DENY tests.

### 6.1. Không kiểm chứng containment chỉ bằng ping

ICMP bị chặn không chứng minh TCP/443, UDP/53, VPN tunnel hoặc connection đang mở đã bị cắt. Ngược lại **ping thành công** có thể chỉ là management exception hợp lệ. Xác minh theo **threat-specific flows** và tại **đúng điểm thực thi**.

### 6.2. Xác định đúng đối tượng trước khi block

Một rule chặn IP có thể ảnh hưởng **DHCP-reassigned user, shared NAT gateway, load balancer hay nhiều Pods cùng node**. Với subnet, tính đúng **CIDR/mask**, xét overlapping routes và address family. Ưu tiên **stable asset IDs** và ACL scope hẹp nếu implementation hỗ trợ.

## 7. Bảo toàn bằng chứng trước, trong và sau khi cô lập

Một incident responder cần cân nhắc **giảm thiệt hại ngay** với **giữ chứng cứ dễ mất**. Nếu có attacker đang mã hóa dữ liệu hoặc exfiltrate, chờ thu đủ memory dump trước khi cắt kết nối có thể gây hậu quả lớn. Ngược lại, tắt nguồn một server trong khi chưa đánh giá có thể làm mất **RAM, active sockets, process state, decryption keys và volatile logs**.

### 7.1. Những nguồn bằng chứng cần phân loại

| Nguồn | Ví dụ | Vì sao thời gian quan trọng? |
| --- | --- | --- |
| EDR/host | Process tree, parent-child, signed binaries, process/network events | Process có thể thoát; agent bị ngắt sau isolation |
| RAM/volatile state | Running processes, sockets, ephemeral keys, malicious in-memory activity | Mất khi reboot/power-off, cực kỳ nhạy cảm |
| Network flows | Source/destination, ports, protocol, bytes, NAT state | Flow buffers/translation table có thời gian giữ ngắn |
| Packet capture | Packet headers/payload tùy khả năng/authorization | Capture sau containment không cho nội dung trước đó |
| Firewall/IDS/IPS | Rule action, connection state, signature, timestamps | Đổi policy có thể thay counter/correlation |
| Cloud control/audit | Instance/ENI, SG changes, assumed role, object accesses | Resource IDs có thể được thay hoặc xóa |
| Kubernetes | Pod UID, node, labels, audit, security context, CNI drops | Pod reschedule và IP reuse gây sai attribution |
| App/DB | User/resource/action, failed/successful requests, transaction IDs | Network ALLOW không chứng minh data access |
| Identity/PKI | Authentication, token issuance, certificate principal | Credential có thể được dùng từ thiết bị khác |

### 7.2. Chain of custody

Với evidence cần phục vụ điều tra chính thức, ghi **người thu, thời gian UTC, nguồn, scope, công cụ/phiên bản, checksum nếu phù hợp, nơi lưu, encryption/access, mọi lần chuyển giao**. Không gửi **memory dumps, raw bearer tokens, private keys, decrypted PCAP hoặc thông tin khách hàng** vào ticket/nhóm chat không được kiểm soát.

### 7.3. Chọn trình tự tùy mức cấp bách

- **High-confidence ransomware đang lan:** Cô lập trước theo emergency policy; lưu **minimal rapid snapshots/log pointers** nếu không làm chậm containment nghiêm trọng.
- **Suspicious but low-confidence connection:** Có thể thu **EDR telemetry, flow history, process association** rồi chọn rule hẹp hơn.
- **Critical DB/identity host:** Phối hợp app owner để tránh **cluster quorum loss hoặc transaction corruption**; ưu tiên ngắt **malicious path** thay vì tắt nguồn tùy tiện.
- **Cloud ephemeral workloads:** Dùng **snapshot/quarantine/decommission plan** phù hợp provider; không tạo bản sao chứa malware rồi kết nối vào Production.

### 7.4. Containment có thể làm thay đổi bằng chứng

Một **host network isolation** có thể cắt command-and-control session và làm malware thay hành vi, đồng thời cắt collector connection. Một **firewall ACL** có thể thay source NAT/session counters. Ghi **before/after state, policy revision, log filters, precise activation time**, không gán tất cả post-change errors thành hành vi của attacker.

## 8. Cô lập tại host bằng EDR và host firewall

EDR isolation thường là cách nhanh để cách ly **một endpoint có agent đang quản lý**. Nó có thể giới hạn inbound/outbound network traffic và duy trì một số kết nối tới **EDR management/sensor hoặc remediation endpoints** theo implementation.

### 8.1. Những điều phải kiểm tra ở EDR

1. **Agent online/healthy?** Máy có mất heartbeat, tamper protection hoặc root/kernel compromise không?
2. **Isolation scope?** Có bao phủ **IPv4/IPv6, Ethernet/Wi-Fi/VPN, local subnet, host networking** không?
3. **Exceptions?** Vendor management, DHCP/DNS, remediation, DFIR remote shell có thể được phép?
4. **Applies to active sessions?** New connections bị chặn nhưng sockets cũ bị reset hay vẫn tồn tại?
5. **Policy enforcement** ở host network stack nào? Có alternative boot path/OS bypass không?
6. **Recovery?** Nếu agent chết hoặc command channel mất, có console/out-of-band alternative không?

**Đừng khẳng định mọi sản phẩm EDR cô lập giống nhau.** Cách giữ cloud management connectivity và hỗ trợ isolated-host investigation khác theo vendor/platform/version.

### 8.2. Host firewall là lớp bổ sung

Host firewall (Windows Defender Firewall, nftables/iptables, pf hoặc host network policy tương đương) có thể **deny inbound/outbound flows theo interface, process, direction, address và port** tùy OS/capabilities. Với incident response, dùng **policy/management system được phê duyệt**, có backup và rollback; tránh áp lệnh firewall thô dẫn đến **khóa chính phiên quản trị đang cần**.

~~~text
HOST QUARANTINE POLICY - conceptual, not executable
subject: incident-host-asset-423
outbound:
  DENY: any new peer not explicitly approved
  ALLOW: EDR management only (verified destinations)
  ALLOW: required SOC evidence channel if approved
inbound:
  DENY: general application and remote admin traffic
  ALLOW: secured DFIR jump endpoint only if necessary
exceptions:
  owner: incident-commander
  expiry: controlled, short-lived
audit:
  log denies and permitted management traffic
~~~

**Cẩn thận với default-deny:** Một số endpoint cần DNS/NTP/KMS để hoàn thành remediation, nhưng mở rộng “allow DNS to anywhere” có thể tạo đường exfil. Chỉ cấp **đúng destination và function đã kiểm chứng**.

### 8.3. Khi host đã bị chiếm quyền cao

Nếu attacker có quyền kernel/root hoặc điều khiển EDR agent, host firewall **có thể bị vô hiệu hóa**. Lúc này phải có điểm enforcement **bên ngoài host**: switch ACL/NAC, hypervisor virtual firewall, cloud ENI SG, upstream firewall hoặc network segmentation. Không dựa vào một policy cài trên chính máy nghi compromised để chứng minh nó đã bị cô lập.

### 8.4. Multi-homed host

Server có NIC cho **application traffic, backup/storage, management network**, hoặc laptop có cả Wi-Fi và Ethernet. Cô lập một NIC có thể không chặn đường khác. Inventory **all interfaces, virtual NICs, tunnels, link-local, IPv6, cloud public/private ENIs** và loại trừ những đường quản trị thật sự cần theo policy.

### 8.5. Tắt nguồn hay giữ máy?

Tắt nguồn có thể ngăn thêm một số hành vi và bảo toàn dữ liệu trên disk, nhưng **mất volatile evidence**, thay đổi trạng thái cluster và không thu hồi thông tin xác thực đã bị copy. Quyết định **power-off/reboot** cần theo incident commander, forensic goals, business impact và yêu cầu an toàn vật lý — không coi “tắt máy” là phương án host isolation duy nhất.

## 9. Cô lập ở switch, NAC, 802.1X và Wi-Fi

Với máy trong campus/office, **network access control** có thể chuyển thiết bị sang **quarantine VLAN, dynamic ACL/security role** hoặc ngắt quyền truy cập switch port/SSID sau khi nhận posture/incident signal.

### 9.1. Sơ đồ NAC

~~~mermaid
flowchart LR
    E["Suspected endpoint"] --> SW["Access switch / AP"]
    SW --> NAC["NAC / RADIUS policy"]
    NAC -->|"Incident role"| Q["Quarantine VLAN / ACL"]
    Q -->|"ALLOW có giới hạn"| REM["Remediation / SOC"]
    Q -->|"DENY"| PROD["Production networks"]
~~~

### 9.2. Cấp lại VLAN và role có thể làm đổi IP

Khi NAC chuyển host từ VLAN người dùng sang quarantine VLAN, **DHCP lease, IP/subnet, DNS và default gateway** có thể thay đổi. Existing sockets thường bị ảnh hưởng; monitoring agent có thể báo offline tạm thời. Không kết luận actor đã biến mất chỉ vì **IP cũ không còn trong flow log**. Correlate bằng **MAC/802.1X identity, switch port/session ID, EDR agent ID, timestamp**.

### 9.3. Tránh chặn nhầm uplink hoặc trunk

Một port trên switch có thể kết nối **hypervisor, access point hoặc downstream switch**, không phải một laptop. Chuyển VLAN/cắt trunk có thể cô lập hàng trăm thiết bị. Phải phân biệt **access port vs trunk, topology/LLDP, port-channel/bonding, VM virtual interfaces** trước khi thao tác.

### 9.4. Bảo vệ ở L2

Traffic giữa hai hosts cùng VLAN có thể không đi qua router. Các cơ chế như **private VLAN, port isolation, dynamic ACL, switch-level microsegmentation và endpoint firewall** có thể cần thiết. **ARP, IPv6 neighbor discovery và multicast** vẫn là những cơ chế local network cần hiểu; chặn tràn lan các control packets có thể khiến network/routing mất khả năng hoạt động.

### 9.5. Wi-Fi và thiết bị di động

Một laptop bị quarantine trên SSID doanh nghiệp vẫn có thể chuyển sang **cellular hotspot hoặc kết nối mạng khác**. NAC chỉ kiểm soát **mạng mà nó quản lý**; identity/EDR/session revocation mới hạn chế quyền tới backend từ các mạng khác.

## 10. Cô lập tại hypervisor, VM và cloud instance

Trong hạ tầng ảo hóa, điểm enforcement nằm ở **vSwitch/distributed firewall, virtual NIC, security group hoặc upstream firewall**, nên có thể vẫn chặn traffic khi guest OS đã bị attacker điều khiển.

### 10.1. Hạn chế phạm vi theo VM/ENI

| Cơ chế | Phạm vi | Điều cần kiểm tra |
| --- | --- | --- |
| Hypervisor virtual switch port ACL | VM vNIC/port group | VLAN mapping, migration/vMotion, offload và policy sync |
| Distributed firewall/microsegmentation | Workload/VM identity hoặc security group | East-west enforcement cùng host, rule order, tag source |
| Cloud instance/ENI security group | Interface và security group rules theo provider | Shared SG, multiple ENIs, stateful semantics và existing flows |
| Cloud network ACL | Subnet/boundary, có thể stateless | Inbound/outbound và return-path ephemeral ports |
| Host firewall in guest | Guest network stack | Root compromise có thể tắt |
| Cloud firewall/egress gateway | Network path trong VPC/VNet | Routes, NAT, private endpoints và bypass |

**Một security group có thể được chia sẻ bởi hàng chục instances.** Sửa chính group đó có thể chặn tất cả members. Thường cần **dedicated quarantine group/policy** áp chính xác tài sản, sau khi kiểm tra implicit/default rules và cloud provider semantics. Không cho rằng cách attach/detach SG giống nhau trên mọi cloud.

### 10.2. Control-plane và data-plane consistency

API trả “update succeeded” chưa chắc mọi luồng đang chạy đã bị cắt tức thì. Đo **config/readback, propagation, stateful connection behavior, network flow logs, denied attempts và backend access**. Nhiều cloud security groups là **stateful**, còn subnet ACL có thể **stateless**; cần xem nhà cung cấp cụ thể về existing flows, tracking, rule evaluation và return packets.

### 10.3. VM snapshot và clone cách ly

Nếu cần forensic snapshot, bảo đảm **evidence integrity, encryption/permissions và approved retention**. Bản clone nghi compromise nên chạy ở **isolation investigation network**, không tự attach vào Production VPC/VNet hay được cấp metadata/IAM role mạnh. Một snapshot chỉ của disk không thay thế **volatile memory/active network state**, và snapshot live có consistency implications cho database.

### 10.4. Metadata/instance role

Host isolation có thể chặn traffic nhưng attacker đã lấy được temporary cloud credentials qua metadata/STS. Xem **role/session validity, IAM/resource policy và audit**; cân nhắc deny/revoke theo provider. Không coi việc vô hiệu instance interface là thu hồi mọi cloud API permissions.

## 11. Cô lập ở Layer 3/4 firewall và chính sách phân đoạn

Firewall giữa security zones là điểm tự nhiên để khoanh **source subnet, destination subnet, ports và direction**. Nhưng firewall chỉ thực thi trên đường traffic **thật sự đi qua nó**, và stateful policy có thể có connection tracking khác nhau.

### 11.1. Chọn điểm thực thi

~~~text
Host A and Host B in same VLAN:
  A ---> L2 switch ---> B
  Edge/router ACL may not see this flow.

Host A in VLAN 20, DB in VLAN 40:
  A ---> L3 gateway/internal firewall ---> DB
  Segmentation rule can deny if route traverses firewall.

Multi-region or private link:
  A ---> local route/peering/transit gateway ---> remote
  Identify every policy point; no implicit central firewall guarantee.
~~~

### 11.2. Quy tắc theo hướng

- **Ingress deny:** Chặn tài sản/người dùng truy cập host/subnet bị cô lập từ bên ngoài scope.
- **Egress deny:** Chặn host/subnet bị nghi compromise truy cập các destinations không phê duyệt.
- **East-west deny:** Chặn lateral movement trong vùng/các security zones.
- **Return traffic:** Stateful firewall có thể cho phép responses của established flows theo connection tracking; stateless ACL cần return path rules chính xác.

**Chặn chỉ inbound** nhưng cho toàn bộ outbound có thể không ngăn exfil. **Chặn chỉ egress ra Internet** mà để east-west vào DB không ngăn lateral movement. Mỗi threat hypothesis cần policy theo đúng hướng.

### 11.3. Mẫu intent ở firewall

~~~yaml
# Pseudocode policy intent; KHÔNG phải manifest vendor.
incident: IR-EXAMPLE-001
subject:
  asset_id: app-host-423
  environment: prod
  observed_ipv4: 10.30.1.25
network:
  quarantine_zone: incident-apps
defaults:
  inbound: DENY
  outbound: DENY
exceptions:
  - from: incident-apps
    to: edr-management
    protocols: [TCP]
    ports: [443]
    reason: verified-response-channel
  - from: authorized-forensic-jump
    to: incident-apps
    protocols: [TCP]
    ports: [managed-ir-service-port]
    reason: approved-investigation
audit:
  record_rule_revision: true
  record_allow_and_deny_metadata: true
  expiry_requires_review: true
~~~

Đây là **policy-as-data** để thảo luận, không thể áp trực tiếp lên firewall hoặc Kubernetes. Các rule thật phải dùng **verified network objects, exact address/port definitions, security zones, route and NAT mapping, logging** tương thích product.

### 11.4. Rule order, shadowing và exception creep

Một DENY hẹp có thể **bị shadow bởi ALLOW rộng phía trước**, hoặc route đi qua firewall khác. Một exception “ALLOW any DNS or HTTPS for investigation” có thể giữ đường exfil qua DoH/proxy. Cần kiểm tra **effective rule order, hit counters, policy optimizer/zone semantics, NAT placement, network path và allowed destination identity**. Exceptions có **owner, scope, lý do và expiry**; không giữ vô hạn sau incident.

### 11.5. Existing connections có bị cắt ngay không?

Không tự kết luận. Với stateful firewall, các **established sessions** có thể giữ state đến timeout hoặc bị flush; thay ACL ở một chiều có thể không chặn đường **asymmetric return**. Xác minh bằng các **new and existing connection tests có quyền**, policy readback, state table (theo privilege) và backend request logs. Chỉ xóa state table nếu được phép và đã đánh giá tác động vì có thể gây outage rộng.

## 12. Khoanh vùng subnet bằng VLAN, VRF, route và ACL

Subnet containment thường có rủi ro cao hơn host isolation vì có thể ảnh hưởng cả **nhóm máy sạch, shared services và mạng điều hành**. Muốn thực hiện đúng phải hiểu **địa chỉ IP/prefix, broadcast domain, route table, VRF, policy routing và interface-level ACL**.

### 12.1. Layer 2 và Layer 3 không cùng phạm vi

| Điều khiển | Chặn được gì? | Giới hạn |
| --- | --- | --- |
| **Switchport shutdown** | Toàn bộ traffic trên port đó | Nhầm uplink/trunk có thể cắt nhiều thiết bị |
| **Quarantine VLAN** | Đổi network domain của endpoint/port | DHCP/ARP/ND/route phải đổi; alternate NIC vẫn hoạt động |
| **Private VLAN/port isolation** | Một số host-to-host communication cùng Layer 2 | Phải xác minh topology và uplink exemptions |
| **Interface/router ACL** | Luồng qua L3 interface/gateway | Không thấy same-VLAN traffic không qua gateway |
| **VRF separation** | Tách routing tables/tenant domains | Route leaks, shared services và tunnels có thể nối các VRF |
| **Internal/virtual firewall** | Chặn giữa zones/vNIC/workloads | Chỉ hữu hiệu nếu traffic thực qua enforcement point |
| **Blackhole route** | Có thể drop traffic tới prefix tại route point | Quá rộng, không bảo vệ mọi local/east-west path |

**Không tự chặn ARP, ICMPv6 Neighbor Discovery hoặc DHCP toàn diện** khi cần mạng hoạt động để điều tra. Những control-plane packets hỗ trợ địa chỉ và reachability; chặn sai có thể làm toàn bộ VLAN mất kết nối và gây khó rollback.

### 12.2. Đặc tả ranh giới cho subnet nghi nhiễm

~~~text
Zone: incident-vlan-30
CIDR: 10.30.1.0/24           (example private address)
Members: 23 virtual machines (inventory at 10:00 UTC)
Gateway: segment firewall

DENY:
  incident-zone -> internal admin/database networks
  incident-zone -> arbitrary Internet destinations
  other user zones -> incident-zone

ALLOW only if approved:
  incident-zone -> secured EDR management endpoints
  authorized DFIR jump service -> explicitly selected hosts
  DNS/NTP/remediation services needed to preserve investigation

VERIFY:
  intra-VLAN traffic, IPv6, secondary NICs, tunnels, stored credentials
  all firewall/ACL and cloud endpoints on the path
~~~

**Địa chỉ trong ví dụ là mạng private, không phải chính sách Production.** Đừng cho phép toàn subnet tới bất kỳ Internet host chỉ để EDR nhận lệnh; phải xác định **vendor egress endpoint, proxy/NAT, certificate validation và quyền operator** phù hợp.

### 12.3. Asymmetric routing và multi-path

Trong mạng có ECMP, peering hoặc nhiều firewalls, **request đi firewall A nhưng response đi firewall B**; một số stateful controls sẽ không có state phù hợp. Khi cài containment:

1. Xác định **forward and return paths** từ source và destination.
2. Kiểm tra **pre/post NAT, policy-based routing, asymmetric network path**.
3. Không dùng một traceroute đơn lẻ làm chứng minh mọi route/port.
4. Xác minh traffic ở **hai phía**, và trạng thái sessions được thực thi theo vendor.
5. Kiểm thử đường qua **DR site/secondary link/IPv6** khi có.

### 12.4. Route leak và shared services

Một VRF quarantine vẫn có thể kết nối tới Production qua **route import/export, transit hub, shared DNS proxy, service mesh gateway, private link hoặc NAT**. Audit **route tables và permitted service-specific exceptions**, không chỉ so tên VRF. Với dịch vụ dùng chung, kiểm tra **reverse access** để không biến remediation service thành đường quay lại mạng khác.

### 12.5. Khôi phục không chỉ thay VLAN về cũ

Sau quarantine, endpoint có thể giữ **DHCP lease, DNS cache, application connection pools hoặc stale routes**. Phục hồi phải xác minh **IP assignment, gateway, DNS, NAC role, L3/L4 policies, service identity và app health**. Không để một máy đã được gỡ quarantine khỏi NAC nhưng **vẫn thuộc nhóm deny trên firewall** làm sự cố giả.

## 13. Cloud VPC/VNet: security group, NACL và network firewall

Nền tảng cloud thường phân tách **security policy gắn NIC/instance** với **subnet/network-level ACL**, route, transit/peering và cloud firewall. Các tên và behavior cụ thể phụ thuộc AWS/Azure/GCP/provider.

### 13.1. Những ranh giới tiêu biểu

| Cấp | Điểm kiểm soát | Điều cần xác minh |
| --- | --- | --- |
| Instance/ENI/VM | Security group/NSG, host firewall | Shared rule objects, multiple interfaces, priority/default policies |
| Subnet | NACL/NSG/subnet policy | Stateful vs stateless, bidirectional return ports |
| VPC/VNet | Network firewall, route tables, peering/transit | Bypass via private endpoints, NAT, alternate routes |
| Organization/project | Cloud IAM and security policy | Cross-account resource/API permissions |
| Storage/API control plane | Bucket/resource policy, identity grants | Network deny không vô hiệu token đã sao chép |
| DNS/metadata endpoints | Private resolver/identity metadata access | Provider routing và service endpoints đặc thù |

### 13.2. Stateful security groups và stateless NACL (không khái quát sai provider)

Trong **AWS VPC**, security groups được mô tả là **stateful** còn network ACL là **stateless**. Vì vậy NACL cần tính **return path/ephemeral ports**; SG xử lý response theo connection tracking với quy tắc cụ thể. Nhưng không suy **Azure NSG, GCP VPC firewall và các cloud khác** dùng chính xác cùng object semantics, rule order hoặc hỗ trợ deny như nhau.

### 13.3. Cloud SG không nên sửa shared group bừa bãi

Nếu SG tên **app-prod-shared** gắn cho 200 instances, sửa SG thành DENY/outbound zero có thể gây outage 200 instances. Với một instance nghi nhiễm, đánh giá **dedicated quarantine policy/SG** áp cho đúng attachment sau khi xét rules/defaults; kiểm tra **tất cả ENIs và security groups áp dụng cùng lúc**.

### 13.4. Cô lập subnet cloud có thể ảnh hưởng managed services

Database subnet hoặc application subnet có thể chứa **managed DB, load balancer interfaces, node endpoints, private DNS resolver và storage interface endpoints**. Một NACL phủ toàn subnet có thể làm **quorum/replication/control-plane connections** thất bại. Phải inventory **provider-managed ENIs, dependencies và failover paths** trước khi áp.

### 13.5. Cloud network containment khác IAM containment

Một EC2/VM/Pod đã lấy temporary cloud credentials có thể bị xóa/chặn network nhưng token vẫn còn dùng được từ nơi khác. Cần **revoke/deny account/session role theo provider, thu hẹp trust, kiểm tra CloudTrail/audit/object access**. Tương tự, xóa public IP không tự loại bỏ quyền dùng cloud API.

### 13.6. Multi-account/region

Traffic có thể đi qua **transit gateways, peering, service endpoints, inter-region networks hoặc shared egress**. Một rule chỉ trong region A không bảo vệ route ở region B. Kiểm tra **cloud account/project owner, policy replication và failover tests**, tránh cắt toàn bộ transit shared cho nhiều tenants khi chỉ một subnet affected.

## 14. Kubernetes: Pod, namespace, node và CNI isolation

Kubernetes Pod có IP riêng trong nhiều CNI implementations; nhưng **Pod IP có thể thay đổi**, nhiều containers trong Pod dùng chung network namespace, node có nhiều workloads và có các đường **hostNetwork/metadata/sidecar** cần xem riêng.

### 14.1. Chọn đơn vị containment

| Target | Có thể làm | Cảnh báo |
| --- | --- | --- |
| Một Pod | Selector/identity-based ingress/egress policy hoặc CNI host-specific action | Label bị sửa, IP reuse, proxy bypass, CNI enforcement |
| Một Deployment | Scale/quarantine replicas, rollout clean version, tighten service identity | Kéo tất cả replicas sạch vào outage nếu không cần |
| Một namespace | Default-deny và exact allowed flows | DNS, control sidecars, multi-tenant workloads, ops impact |
| Một node | Cordon/taint/drain và network quarantine theo incident plan | **Cordon/drain không phải network isolation**, volumes/quorum; attacker trên node root có thể xem nhiều Pods |
| Cluster/zone | Security control tại CNI/cloud firewall/VPC | Blast radius rất lớn, cần IC/owner approval |
| Service mesh | Inbound peer identity DENY, egress restrictions | L7/mTLS policy chỉ ở proxy/data path không bị bypass |

### 14.2. NetworkPolicy minh họa cho namespace cô lập

Một ví dụ **Kubernetes NetworkPolicy ingress + egress default deny** cho các Pods trong namespace **incident-quarantine**; nó chỉ phát huy tác dụng nếu **CNI hỗ trợ NetworkPolicy và namespace thật có scope phù hợp**.

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: quarantine-default-deny
  namespace: incident-quarantine
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
~~~

**Đây không phải hướng dẫn đặt trực tiếp lên namespace Production hiện có.** Nó có thể cắt toàn bộ service traffic, DNS, identity/monitoring và proxy control plane. Chỉ dùng trong lab hoặc namespace quarantine được thiết kế sẵn với approved exceptions và quy trình kiểm thử. Nếu muốn quarantine **một Pod**, phải tạo selector **đủ ổn định** và hiểu labels/Pod replacements; không đổi nhãn tùy ý để làm mất nhận dạng tài sản.

### 14.3. Cảnh báo về union semantics của NetworkPolicy

Trong Kubernetes NetworkPolicy chuẩn, nhiều policies cho phép traffic có thể **cộng dồn theo kiểu additive**; một default-deny không tự thắng mọi rule ALLOW khác đang chọn cùng Pods. Không thể dùng một policy riêng rồi mặc định nó **override** một allow-all hiện có. Cần kiểm tra **effective allowed flows**, policies khác, **CNI-specific deny constructs nếu hỗ trợ**, và point enforcement.

### 14.4. DNS và service mesh trong quarantine

Nhiều Pods cần DNS, service mesh CA/xDS/SDS, observability hoặc secrets broker. Nếu policy quá chặt, Pod có thể:

- Không resolve service names.
- Không gia hạn mTLS certificate hoặc nhận proxy config.
- Không gửi logs/metrics tới SIEM.
- Không hoàn thành app readiness, khiến Kubernetes thay thế liên tục.

Nếu những đường này là exception cần thiết, hãy **ALLOW đúng namespace/pods/ports/destination** đã xác minh; đừng mở rộng egress toàn bộ chỉ vì DNS/CA không hoạt động. Với **NodeLocal DNSCache, hostNetwork proxies hoặc CNI-specific datapath**, selectors và semantics có thể khác mẫu thông thường.

### 14.5. Cordon và drain không thay containment

**kubectl cordon** chủ yếu ngăn scheduling Pod mới, không ngắt network của Pods đang chạy. **kubectl drain** di chuyển/evict workloads theo khả năng, có thể khiến compromised workload **chạy lại trên node sạch** hoặc làm ảnh hưởng stateful services nếu chưa có admission/isolation plan. Khi nghi **node compromised**, cần cô lập node ở **network/hypervisor/cloud layer**, bảo vệ evidence, rồi quyết định rebuild và xử lý workloads.

### 14.6. Runtime compromise và identities

Nếu app Pod bị RCE, attacker có thể sử dụng **ServiceAccount token, cloud workload identity hoặc mTLS session** đã có. NetworkPolicy chỉ giảm reachability; IAM/RBAC/mesh resource authorization vẫn cần review và revoke. Không để compromised Pod truy cập **Kubernetes API, metadata identity service, runtime socket hoặc shared volumes** ngoài chức năng.

## 15. VPN, ZTNA, remote access và mạng người dùng

Một máy đang có **VPN tunnel hoặc ZTNA app session** có thể tiếp tục dùng credential từ các network paths khác sau khi bị cô lập trên LAN. Để containment đạt hiệu lực:

1. Xác định user/device identity và **active VPN/ZTNA sessions**.
2. Revoke/disconnect sessions theo cơ chế sản phẩm, không chỉ chặn một physical interface.
3. Kiểm tra **split tunnel, DNS resolution, remote desktop/bastion, client proxy**.
4. Hạn chế quyền tới **resource/app cụ thể**, không cho người dùng broad subnet access mặc định.
5. Đối chiếu **IdP account status, MFA, device posture, JIT/PAM grants và cloud login sessions**.
6. Kiểm tra **server-side revocation** khi token có thể được dùng ngoài gateway.

### 15.1. VPN disconnect chưa chắc cắt phiên ứng dụng

Một backend sử dụng **JWT/self-contained token** có thể tiếp tục chấp nhận token đã cấp qua một API public khác, dù VPN tunnel đã bị ngắt. Với long-lived **SSH/RDP/gRPC/WebSocket** cần thiết kế **active-session disconnect/recheck** ở broker/app/server, không suy network route change hủy mọi quyền.

### 15.2. Không cô lập cả subnet remote users theo một account nghi nhiễm

Đằng sau một corporate NAT hoặc carrier NAT có thể có nhiều users; một IP bên ngoài không đủ định danh account. Ưu tiên cô lập **device identity, user session, credential và resource access**, dùng IP/ASN như tín hiệu phụ. Nếu risk chưa rõ, giám sát thêm để tránh gây outage nhiều người không liên quan.

### 15.3. Wireless và IoT/OT

Thiết bị Wi-Fi, IoT hoặc OT có thể không chạy EDR. Có thể dùng **SSID/VLAN/NAC role/firewall policy** để quarantine, nhưng với **OT/ICS, thiết bị y tế hoặc mạng an toàn vật lý**, việc chặn packet hoặc reboot có thể gây tác động vật lý. Phải phối hợp **operator, safety owner, maintenance window và vendor guidance**; không triển khai lệnh mạng chủ động theo runbook IT thông thường nếu chưa được phê duyệt.

## 16. IPv4, IPv6, DNS, NAT và đường bypass

### 16.1. IPv6 là một phần của phạm vi containment

Nếu host bị block theo IPv4 nhưng vẫn có **global IPv6 address hoặc tunnel**, nó có thể kết nối ra ngoài theo IPv6. Kiểm tra:

- IPv6 enablement, address scope, default route, neighbor discovery.
- Firewall/SG/NACL/CNI policy hỗ trợ IPv6 hay không.
- DNS **A và AAAA** records, ứng dụng **Happy Eyeballs** hoặc fallback.
- IPv6 overlay/transition tunnels theo topology nếu được dùng.

**Không tự tắt IPv6 trên toàn mạng** để chữa một incident vì có thể hỏng dịch vụ, discovery và routing; thay vào đó xác minh và áp **equivalent policy coverage** cho IP families cần bảo vệ.

### 16.2. NAT và proxy attribution

Một egress NAT public IP có thể đại diện nhiều hosts. Muốn chặn riêng compromised host, cần map **pre-NAT source, source port, destination tuple, session time, ENI/pod/host identity**. Chặn **public egress IP của NAT** tại Internet có thể ảnh hưởng toàn bộ organization và không chặn **internal lateral traffic**.

### 16.3. DNS không phải access control

Xóa DNS record của host nghi nhiễm hoặc sinkhole một domain có thể giúp giảm một số đường liên lạc, nhưng attacker có thể gọi **direct IP, cached address, alternate resolver, DoH/DoT hoặc private link**. DNS-based controls cần kết hợp network deny, application identity và egress restriction. Không dùng “domain không resolve” làm bằng chứng mọi hoạt động đã chấm dứt.

### 16.4. Loopback, link-local và metadata

Lệnh block subnet ở router không chặn traffic **localhost** và có thể không chặn **link-local/metadata service** tùy provider/CNI. Nếu attacker chiếm app process, nó có thể sử dụng các **local credentials, Unix sockets hoặc cloud instance metadata** còn được phép. Đánh giá riêng **host/process isolation và IAM**.

### 16.5. Alternate paths

Những đường cần kiểm tra theo kiến trúc:

| Alternate path | Vì sao rule có thể bỏ sót? | Biện pháp |
| --- | --- | --- |
| Secondary Ethernet/Wi-Fi | Interface không thuộc VLAN/ACL bị chặn | Device/port inventory, EDR/NAC across interfaces |
| VPN/split tunnel | Traffic tunneled ra điểm khác | Session revoke, tunnel/egress policy |
| Cloud private endpoint | Không qua Internet egress firewall | Private endpoint/resource policy và route review |
| Same-subnet L2 | Không đi qua router ACL | Switch/host/distributed firewall |
| IPv6 | Chỉ có IPv4 deny | Equivalent IPv6 rules + test |
| Service mesh passthrough | Proxy authZ chỉ áp khi traffic đi qua proxy | CNI/network enforcement + app auth |
| OOB/storage/backup | Separate NIC/VLAN không nằm security zone | Owner-reviewed dedicated network policy |
| Public API token use elsewhere | Credential đã bị copy khỏi host | IAM/resource-side revoke |

## 17. Dịch vụ thiết yếu và ngoại lệ tối thiểu khi quarantine

Một host đã bị cô lập có thể cần **kênh điều tra và phục hồi**, nhưng mỗi exception đều là một **đường traffic attacker có khả năng lạm dụng** nếu host còn compromised.

### 17.1. Những phụ thuộc thường phải đánh giá

| Dịch vụ | Tại sao có thể cần | Rủi ro mở exception rộng |
| --- | --- | --- |
| **EDR management** | Nhận lệnh, giữ telemetry, lấy evidence | Cấp arbitrary outbound HTTPS |
| **Secure DFIR collector** | Gửi forensic metadata/triage | Exfiltration qua collector path nếu upload không kiểm soát |
| **DNS** | Resolve approved remediation endpoints | DNS tunneling/alternate resolver |
| **NTP** | Giữ timestamp/crypto validity | Không cần thiết nếu chỉ open ngắn và time sync đã ổn |
| **IdP/AD/Kerberos** | Một số workflows điều tra cần auth | Compromised host tiếp tục thử credential abuse |
| **KMS/secrets manager** | Một số ứng dụng cần key để chạy | Host compromised tiếp tục lấy secrets |
| **Log collector/SIEM** | Bảo toàn operational visibility | Log injection hoặc raw secret leakage |
| **Package/patch repository** | Remediation có kiểm soát | Arbitrary downloads/updates từ Internet |
| **Database/storage quorum** | Tránh hỏng cluster/stateful apps | Cho attacker tiếp tục tới dữ liệu nhạy cảm |
| **Cloud metadata/control API** | Agent/provider operations | Temporary credential issuance có thể bị lạm dụng |

### 17.2. Quy tắc cấp ngoại lệ

1. Chỉ rõ **source asset, destination identity/address, protocol, port, direction và time window**.
2. Nêu **business/DFIR reason**, người phê duyệt và biện pháp kiểm soát phía nhận.
3. Cho phép **đường quản trị được bảo vệ** thay vì arbitrary remote shell.
4. Kiểm tra **DNS/proxy chain**: ALLOW tới proxy không được biến thành truy cập Internet không giới hạn.
5. Ghi logs cho **ALLOW và DENY** ở mức cần thiết, bảo vệ metadata/PII.
6. **Expire/review** ngoại lệ khi evidence đã thu hoặc host chuyển sang recovery.

### 17.3. Không dùng ngoại lệ “chữa cháy” để duy trì credential nguy hiểm

Nếu máy bị nghi compromise vẫn cần access tới **Production database secrets**, giải pháp an toàn thường là **failover workload sạch** hoặc **read-only/controlled remediation path**, không tiếp tục cho máy đó sử dụng quyền cũ. App owner và incident commander phải đánh giá **data integrity và availability**.

## 18. Policy matrix: xác định DENY, ALLOW và trạng thái UNKNOWN

Mỗi quyết định containment cần một **bảng luồng cụ thể**, không chỉ ghi “isolate subnet A”. Bảng này giúp kỹ sư networking chuyển sang cấu hình đúng điểm enforcement, app owner dự đoán tác động, SOC kiểm chứng và IC quyết định khi phải đánh đổi.

### 18.1. Ví dụ ứng dụng thanh toán

Giả định một host ở subnet ứng dụng nghi bị compromise; replicas sạch đã được kiểm tra và vẫn vận hành. Bảng minh họa:

| Source | Destination | Protocol / port | Mong muốn | Lý do |
| --- | --- | --- | --- | --- |
| Suspected host | Production DB | TCP/DB port phù hợp | **DENY** | Giới hạn đường đọc dữ liệu nhạy cảm |
| Suspected host | Internal app/admin subnets | Any ngoài ngoại lệ | **DENY** | Chặn lateral movement |
| Suspected host | Unapproved Internet destinations | Any | **DENY** | Hạn chế exfil |
| Suspected host | Approved EDR management | TLS/verified endpoint | **ALLOW có điều kiện** | Giữ kênh điều tra nếu cần |
| Authorized IR jump host | Suspected host DFIR service | Specific secured port | **ALLOW có điều kiện** | Điều tra có kiểm toán |
| Clean app replica | Production DB | Approved service port | **ALLOW** | Duy trì dịch vụ hợp lệ |
| Dev subnet | Production DB | Any | **DENY** | Giữ segmentation bình thường |
| Unknown source | Quarantined host | Any | **DENY** | Giảm đường truy cập mới |
| Suspected host | Cloud identity/metadata | Theo policy | **REVIEW/DENY nếu không cần** | Ngăn lấy temporary credentials |
| Any | Unmapped alternate path | Unknown | **UNKNOWN** | Cần bổ sung evidence, không coi là DENY |

**Không suy các tên “DB port”, “EDR TLS” hay “IR service” thành port/vendor cụ thể** khi chưa xác minh. Một port số đúng không đủ nếu **đích là một shared proxy** có thể forward đến nơi khác.

### 18.2. Rule theo identity hay theo địa chỉ?

Với máy trạm có IP động, security control có thể dùng **EDR device ID hoặc 802.1X identity**, đáng tin hơn IP snapshot. Với Kubernetes, dùng **workload namespace/ServiceAccount/Pod identity** khi CNI hỗ trợ. Với cloud, có thể dùng **instance/ENI SG**. Dù dùng identity, vẫn cần kiểm chứng **scope và enforcement**: một nhãn workload bị attacker có quyền chỉnh có thể khiến policy không còn chọn đúng Pod.

### 18.3. Deny intent không được coi là kết quả

Một firewall change ticket có thể ghi **DENY** nhưng policy bị shadow, route đi đường khác, CNI không hỗ trợ hoặc một flow đã established tiếp tục. Ghi riêng:

~~~text
CONTROL INTENT:       DENY host-423 -> Prod DB
CONTROL APPROVED:     10:01:00Z
CONTROL PUBLISHED:    10:01:05Z
PEP EFFECTIVE STATE:  confirmed at 10:01:08Z
NEW FLOW TEST:        denied at 10:01:10Z
EXISTING SESSION:     terminated/denied/unknown (with evidence)
ALTERNATE PATH TEST:  IPv6/NAT/other NIC, if applicable
BUSINESS ALLOW:       clean-app -> DB verified
~~~

Các timestamp là **minh họa**, không phải SLA chuẩn.

## 19. Kiểm chứng containment trên data plane

### 19.1. Bốn lớp kiểm chứng

1. **Control plane:** Rule/role đã được hệ thống chấp nhận, đúng object/identity/scope/version.
2. **Data plane:** Packet/connection qua enforcement point bị DENY theo semantics, counters/logs phù hợp.
3. **Destination/server:** Đích không nhận unauthorized request/operation; logs không có thành công sau cutoff.
4. **Business:** Tài sản sạch/luồng thiết yếu vẫn hoạt động trong SLO, không có collateral damage ngoài phê duyệt.

~~~mermaid
flowchart LR
    A["Approved containment policy"] --> B["PEP readback"]
    B --> C["Network ALLOW/DENY test"]
    C --> D["Destination/application audit"]
    D --> E["Business SLI and alerts"]
    E --> F["Evidence + confidence + remaining gaps"]
~~~

### 19.2. Bảng kiểm thử kết nối

| Test | Kỳ vọng | Nơi ghi bằng chứng |
| --- | --- | --- |
| New TCP connection từ suspected host tới DB | DENY | SG/firewall/CNI/endpoint logs, DB access audit |
| Established DB session từ trước change | Terminate/restrict theo incident policy | Stateful connection table, DB logs, session metrics |
| East-west sang host cùng VLAN | DENY | Switch/distributed firewall/host sensor |
| External HTTPS tới unapproved destination | DENY | Egress firewall/NAT/flow logs |
| IPv6 peer/Internet path | DENY tương đương nếu mạng dùng IPv6 | IPv6 firewall/flow records |
| EDR management từ isolated host | ALLOW nếu exception được duyệt | Agent heartbeat + verified endpoint connection |
| Authorized forensic jump access | ALLOW đúng source/method/time | Bastion/PEP/audit logs |
| Clean app replica tới DB | ALLOW | App SLI và DB authenticated access |
| Unsupported/unknown protocol/route | UNKNOWN cần kiểm tra hoặc DENY theo policy | Coverage inventory và logs |

Test cần diễn ra **chỉ trong môi trường được phép**, bằng **synthetic/harmless transactions**. Không gửi payload exfil hay quét mạng trái phép để “chứng minh” DENY. Khi cần thử một existing session, chuẩn bị **dedicated harmless test session**, không ngắt giao dịch khách hàng.

### 19.3. Đo effective containment latency

Thời gian từ quyết định tới hiệu lực có thể gồm:

\[
T_{\text{effective}} =
T_{\text{approval}} +
T_{\text{control-publish}} +
T_{\text{data-plane-converge}} +
T_{\text{active-session-disconnect}}
\]

Đây là mô hình **đơn giản hóa**; các bước có thể song song hoặc không có cơ chế disconnect tự động. Nếu active session không bị cắt, **effective latency cho flow đó có thể không được giới hạn** bởi thời điểm API trả success. Đo **decision/submit/ACK/readback/observed-deny** riêng.

### 19.4. Không tuyên bố “cô lập 100%” khi chưa đủ visibility

Nếu thiếu sensor trên một subnet/IPv6 path hoặc không quan sát được backplane, báo **PARTIALLY_VERIFIED/UNKNOWN** cùng danh sách blind spots. Không dùng absence of flow logs làm bằng chứng có DENY, nhất là khi collector đang lỗi.

## 20. Forensic visibility sau khi cắt mạng

### 20.1. Những thay đổi quan sát thường gặp

- EDR agent có thể mất **heartbeat** vì exception chưa mở, hoặc vẫn báo online qua vendor cloud dù user traffic đã bị chặn.
- Firewall **DENY counters** tăng; đừng coi điều đó là có malware nếu ứng dụng sạch liên tục retry tới dependency đã bị cắt.
- NetFlow/VPC flow logs vẫn có **flow records đến muộn**, dù containment đang có hiệu lực.
- Kết nối tới C2 có thể biến mất, nhưng **DNS cache, scheduled tasks, dropped packets** còn xuất hiện.
- Ứng dụng có thể tăng **HTTP 5xx, timeout, gRPC UNAVAILABLE** do egress deny hợp lệ.
- Cloud audit vẫn có API calls từ **stolen credentials bên ngoài host**, không đi qua host network nữa.

### 20.2. Kết hợp nguồn telemetry

| Nguồn | Cho biết gì? | Không cho biết chắc |
| --- | --- | --- |
| Firewall/SG/NACL/CNI | Enforcement action, flow/matching policy | Backend đã từ chối đúng object-level action |
| EDR | Host/process/network isolation status theo agent | Host kernel không còn bị attacker kiểm soát |
| VPC/NetFlow/IPFIX | IP/port/bytes/flow metadata tại điểm đo | Packet payload hoặc user identity đầy đủ |
| IDS/IPS | Detection hits, anomaly signatures, block status | Intrusion thành công từ một alert duy nhất |
| DNS/Proxy | Domain/query metadata, destination handling | Không có direct IP/DoH/alternate resolver |
| Application/DB | Authenticated API actions, business resource, DB sessions | Traffic đã bị chặn trước app có tồn tại hay không |
| IAM/STS/IdP | Sessions, token use, privilege/resource changes | Host có bị cô lập vật lý hay không |
| NAC/Switch | Port state, VLAN/role, packets, MAC/802.1X session | Máy không có cellular/secondary NIC |

### 20.3. Không trộn observed time với received time

Flow logs có thể được tạo theo interval và ghi lên log sink muộn. Khi một record có event_end trước 10:00 nhưng ingested sau containment lúc 10:02, **không chứng minh traffic đã chạy qua DENY lúc 10:02**. Cần dùng **event start/end time, ingestion delay, source semantics, clock quality**.

### 20.4. Điều tra không được làm lộ thêm bí mật

Memory dump/PCAP đôi khi chứa **access tokens, private keys, session cookies, mật khẩu hoặc dữ liệu cá nhân**. Chỉ lấy khi được phép, giới hạn scope/retention, dùng **evidence vault và RBAC**, tuyệt đối không dán raw secrets vào ticket/chat công khai. Với proxy/TLS keylogs, không bật trên Production chỉ để có thêm plaintext nếu không có ngoại lệ bảo mật cực kỳ kiểm soát.

## 21. Kết hợp cô lập mạng với identity, endpoint và ứng dụng

Một incident có thể trải nhiều trust boundaries: **host bị RCE → ServiceAccount token bị copy → cloud IAM permission → object storage access**, hoặc **VPN credentials bị lấy → truy cập API từ máy khác**. Network containment một host mới chỉ xử lý một phần.

### 21.1. Ma trận containment đa lớp

| Rủi ro | Network action | Identity/endpoint/app action |
| --- | --- | --- |
| Host phát C2 traffic | Deny C2/host isolation | EDR triage, process evidence, credential inventory |
| Stolen VPN credential | Chặn session/target route khi cần | IdP disable/revoke, MFA/device binding, server-side session invalidation |
| Cloud STS token bị lộ | Hạn chế VM egress/private endpoints | IAM deny/revoke theo provider, audit object access |
| Kubernetes SA token bị lộ | Quarantine Pod/namespace | RBAC/service identity review, token-bound lifecycle, backend deny |
| mTLS private key của workload bị lộ | Chặn path compromised workload | Rotate leaf credentials, deny peer principal, active session review |
| Ransomware lateral movement | Segment host/subnet, disable SMB/admin paths | Host rebuild, restore backup, IAM/AD privilege review |
| Exfil từ DB service | Chặn unauthorized egress | App authorization, DB accounts, storage audit, data owner incident |

### 21.2. Tại sao địa chỉ IP không đủ chứng minh attacker?

Một IP public có thể là **corporate NAT, VPN concentrator, CDN, proxy hoặc shared mobile carrier**. Một Pod IP có thể được tái sử dụng sau phút. Khi thu hồi credential, cần gắn đúng **issuer/subject/session/resource**, không chỉ chặn IP nguồn quan sát được. Đồng thời kiểm tra **data-plane DENY** vì auth revocation không bảo vệ endpoint không có application auth.

### 21.3. Quản lý credential đã được dùng trên host

Inventory **SSH private keys, service passwords, API tokens, kubeconfig, cloud session credentials, certificate keys, database accounts** theo chính sách và bằng chứng có được. Revoke/rotate theo **scope, dependency và priority**; không đưa raw secrets vào báo cáo. **Leaf key compromise** khác **CA signing key compromise**, nên không tự rotate toàn CA khi chỉ có một workload key bị lộ.

### 21.4. Ngăn tái sử dụng compromised image

Một host đã được network-isolate không nên tự quay lại Production chỉ bằng reboot và scan “clean”. Xem **persistence, firmware/boot integrity khi liên quan, patch root cause, image provenance, secrets rotation và trust attestation**; khôi phục từ **known-good image** khi cần. Với Kubernetes, không để deployment controller lập lại compromised Pod trên node khác bằng **cùng image/config/secrets** mà chưa kiểm soát.

## 22. Tự động hóa containment có giới hạn an toàn

SOAR/EDR/NAC/cloud controller có thể nhận cảnh báo và tự áp quarantine. Nhưng **automatic subnet-wide quarantine** là hành động tác động cao; một false positive, parser lỗi hoặc malicious alert injection có thể gây outage diện rộng.

### 22.1. Phân tầng automation

| Tier | Ví dụ hành động | Mức kiểm soát |
| --- | --- | --- |
| **Observe** | Thu evidence, tăng sampling/telemetry, tạo case | Có thể tự động với quyền đọc hẹp |
| **Soft contain** | Chặn một verified malicious destination/identity scope hẹp | Rule chất lượng cao, TTL, audit |
| **Host quarantine** | EDR isolate một device đã được xác minh | High-confidence trigger, exact asset ID, revert path |
| **Zone containment** | Firewall/ACL hạn chế subnet hoặc security zone | IC/dual approval theo business impact, dry-run |
| **Emergency broad deny** | Cô lập vùng lớn khi worm đang lan | Emergency authority, continuous review, safe restoration |

### 22.2. Automation guards

1. **Không tin alert payload tự khai:** Validate source, signature/auth, event schema, time/sequence, asset identity.
2. **Blast-radius estimator:** Trước khi block, đếm resources/critical dependencies chịu ảnh hưởng theo inventory đã kiểm chứng.
3. **Allow/deny protected objects:** Không auto-block **control plane, DNS/IdP, payment DB, SOC management** ngoài emergency policy.
4. **Rate limits:** Không để một detector phát 10.000 events dẫn tới 10.000 firewall updates.
5. **Idempotency:** Một incident/device action lặp phải có cùng desired state, không tạo ACL chồng chéo.
6. **Dry-run/canary:** Preview policies và kiểm thử trước khi mở rộng.
7. **Time-boxed exception:** TTL có owner; không tự hết hạn quarantine của compromised host nếu chưa có approval/recovery.
8. **Readback/effective verification:** API ACK không thay bằng chứng thực thi.
9. **Kill switch và rollback:** Người trực có quyền dừng automation nếu parser/identity mapping lỗi.
10. **Full audit:** Ai/điều gì tạo decision, rule version, approvals, effect, risk gap.

### 22.3. False positives nguy hiểm hơn một cảnh báo sai thông thường

Nếu detector nhầm **shared NAT IP** là attacker và automation cô lập một subnet chứa domain controllers, hậu quả có thể lớn hơn một đợt quét cổng ban đầu. Vì vậy **precision, verified asset binding và impact budget** phải được kiểm thử; một anomaly score đơn lẻ không nên được phép thay đổi routing hoặc firewall của Production diện rộng.

### 22.4. Không tạo đường vòng để “phục hồi” không có hạn

Trong outage do containment, có thể cần exception để service critical hoạt động. Nhưng mở **ANY/ANY internet egress, wildcard IAM hoặc mTLS permissive toàn mesh** có thể trả lại attacker đúng đường đã bị khóa. Exception phải **chỉ một function, có chủ, expiry và log**, và được IC/security approver xét.

## 23. Định lượng tác động và điều kiện ra khỏi trạng thái quarantine

### 23.1. Các metric vận hành

| Metric | Ý nghĩa |
| --- | --- |
| Time to contain | Từ trigger đủ tin cậy tới effective block của flows mục tiêu |
| Policy propagation lag | Từ approved change tới data plane áp đủ trên relevant points |
| Unauthorized flow success after cutoff | Dấu hiệu containment chưa hiệu lực hoặc bypass |
| Business SLI impact | HTTP success/p95/p99, DB connectivity, queue lag, DNS/IdP health |
| Collateral-denied flows | Số luồng hợp lệ bị chặn do policy quá rộng |
| SOC visibility continuity | EDR heartbeat, log ingestion, missingness và sampling |
| Active sessions remaining | Existing SSH/DB/VPN/gRPC sessions chưa terminate/recheck |
| Credential revocation coverage | Phạm vi credentials đã disable so với inventory |
| Time to safe recovery | Từ containment tới restored business access sau attestation |
| Quarantine exception lifetime | Ngoại lệ tồn tại bao lâu, có owner/approval không |

### 23.2. Business continuity trước khi đổi subnet

Đo tình trạng **replication, DB quorum, auto-failover, storage connectivity, queue backlog, autoscaler, load balancer endpoints**. Một subnet quarantine có thể gây **partial failure** khó phát hiện hơn full outage, ví dụ worker still Ready nhưng không truy cập message broker, khiến transactions treo. Cần những **synthetic business checks** được phép.

### 23.3. Không tự gỡ quarantine khi traffic giảm

Mức flow DENY giảm có thể do **attacker dừng lại, host offline, agent mất log hoặc rule chặn hoạt động**; không chứng minh malware đã bị loại. Điều kiện recovery cần **forensic assessment, clean build/patch, credential reset, entitlement review, policy validation và approver sign-off**.

### 23.4. Có thể cần duy trì cô lập lâu

Một host đang chờ DFIR/legal review có thể ở quarantine nhiều ngày. Cần **đủ patch/log retention, credential expiry monitoring, dữ liệu backup được bảo vệ và exception review định kỳ**; không biến quarantine network thành một “vùng tin cậy mới” có Internet rộng và admin access mặc định.

## 24. Runbook đầy đủ: khoanh vùng một host hoặc subnet

Một runbook tốt có **đầu vào, người có thẩm quyền, điểm quyết định, cơ chế thực thi, kiểm tra hiệu lực, fallback và exit criteria**. Không biến nó thành tập lệnh shell chạy trực tiếp trên mọi host: kiến trúc mạng, OS, CNI, cloud và mục tiêu điều tra luôn khác nhau.

### 24.1. Sơ đồ vòng đời

~~~mermaid
flowchart TD
    A["Detection/alert/incident intake"] --> B["Validate evidence, asset identity, scope"]
    B --> C{"Urgent active compromise?"}
    C -- "Có" --> D["Emergency containment authorization"]
    C -- "Chưa rõ" --> E["Targeted evidence and risk assessment"]
    D --> F["Choose minimal effective PEP / quarantine tier"]
    E --> F
    F --> G["Preserve evidence and record change"]
    G --> H["Apply host/zone/network/identity controls"]
    H --> I["Read back policy + test DENY/ALLOW"]
    I --> J{"Effective and business SLI acceptable?"}
    J -- "Không" --> K["Escalate, narrow/fix policy, safe rollback"]
    K --> I
    J -- "Có" --> L["Monitor, investigate, eradicate, rebuild"]
    L --> M{"Recovery criteria and approval satisfied?"}
    M -- "Chưa" --> L
    M -- "Có" --> N["Canary restore + validate access and DENY baseline"]
    N --> O["Close incident + postmortem + rule cleanup"]
~~~

### 24.2. Giai đoạn 0 — tiếp nhận và xác thực tín hiệu

**Tối thiểu:** incident ID, who reported, current business impact, affected asset ID, observed flows, UTC time, source confidence, quality/coverage of telemetry, criticality. Tránh dựa một alert “IP suspicious” để đổi subnet routing nếu không có identity/time mapping hoặc bằng chứng cấp bách.

**Các dấu hiệu cần ưu tiên containment nhanh:** verified ransomware worm lateral movement, active exfil from sensitive assets, compromised privileged management endpoint, confirmed malware with remote movement capability hoặc ongoing unauthorized admin sessions. Có thể cần hành động khẩn theo policy trước khi toàn bộ forensic collection hoàn tất.

### 24.3. Giai đoạn 1 — chọn scope và enforcement

Chọn **nhỏ nhất mà chặn được đường nguy hiểm**:

1. Một **destination/protocol** nếu biết chính xác malicious path và host cần hoạt động để điều tra.
2. Một **host/VM/Pod** nếu asset compromise được xác định.
3. **Security group/segment/subnet** nếu nhiều hosts affected hoặc không thể phân biệt nguồn đủ nhanh.
4. **Cross-zone emergency deny** nếu có worm/compromise lan rộng và IC chấp nhận business impact.

Ghi cụ thể **host ID, interface/port, source/destination, direction, IPv4/IPv6, route, NAT, allowed DFIR/management**. Mỗi phạm vi cần ràng buộc **thời gian đánh giá lại và người chịu trách nhiệm**.

### 24.4. Giai đoạn 2 — bảo toàn bằng chứng

Ưu tiên **EDR timeline, process/network metadata, current sessions, memory nếu phù hợp và an toàn, firewall/flow logs, identity/cloud audit**. Với high-confidence compromise, **không trì hoãn containment để lấy thêm bằng chứng nếu thiệt hại đang tăng**. Ghi trạng thái trước/sau thay đổi và bảo vệ evidence storage.

### 24.5. Giai đoạn 3 — triển khai thay đổi có kiểm soát

- **Host:** EDR isolate, host firewall hoặc external switch/hypervisor/cloud policy nếu host không đáng tin.
- **Subnet:** firewall/ACL/VRF/VLAN quarantine, kiểm tra intra-subnet L2 và routing đa điểm.
- **Cloud:** SG/NSG/NACL/route với review stateful semantics, shared objects và attachments.
- **Containers:** CNI/NetworkPolicy/mesh policy; không dùng cordon/drain thay isolation.
- **Remote access:** ZTNA/VPN sessions revoke, IdP/credentials, server-side token acceptance.

Luôn giữ **rollback path độc lập** khi thay đổi có thể cắt chính kết nối quản trị: console/OOB management hoặc pre-approved JIT break-glass, theo tài sản.

### 24.6. Giai đoạn 4 — kiểm tra hiệu lực

1. Đọc **effective policy and status** ở PEP.
2. Thử **new harmless connection** từ source mục tiêu tới forbidden destination (chỉ nơi được phép).
3. Kiểm tra **existing session** theo yêu cầu và vendor state semantics.
4. Đối chiếu **destination/application audit** không có unauthorized success sau cutoff.
5. Kiểm tra **sibling routes, same-VLAN, IPv6, VPN/overlay, private endpoint** theo inventory.
6. Kiểm tra **authorized DFIR/remediation và clean app flows** vẫn ALLOW.
7. Theo dõi **business SLI** và collateral-deny logs; lập ticket cho unknown paths.

### 24.7. Giai đoạn 5 — điều tra, eradication và phục hồi

1. Từ evidence xác định **root cause/initial access, persistence, compromised accounts/tokens, data impact**.
2. **Rebuild/patch** affected host/workload từ nguồn tin cậy theo mức rủi ro.
3. **Revoke/rotate credentials** và cập nhật IAM/RBAC/resource policies nếu cần.
4. Kiểm tra **vulnerability fix, EDR health, service owner approval**, dependencies và HA.
5. Phục hồi từng bước **canary/limited scope**, trước tiên xác minh business ALLOW cùng unauthorized DENY.
6. **Retire exception rules** dùng cho investigation đúng thời hạn; ghi rollback hash/change.
7. Ghi **timeline, detection gaps, containment effectiveness, false positives, remaining risk và postmortem**.

### 24.8. Mẫu bảng giao ca

~~~text
CASE ID / IC / TIME UTC:
Threat hypothesis + confidence:
Affected identities / host IDs / subnet CIDRs:
Active containment: EDR, NAC, SG, firewall, NetworkPolicy, IAM:
Policy version, attachment points, IPv4/IPv6, bypass review:
Observed unauthorized DENY and business ALLOW evidence:
Active sessions and credentials still pending revocation:
Essential exceptions and expiry:
App/service SLO, user impact, data/forensic status:
Pending investigation, owner, next review, escalation path:
Recovery criteria and named approvers:
~~~

### 24.9. Phản ứng khi containment gây outage

Khi ứng dụng quan trọng lỗi sau change, không tự mở **ANY/ANY** để “khôi phục ngay”. Xác định **điểm bị DENY**, sửa **destination/protocol cụ thể** hoặc failover sang clean replica; đánh giá business urgency với IC. Nếu phải rollback, đảm bảo **đường attacker bị ngăn bằng biện pháp thay thế** hoặc có quyết định risk acceptance tạm có hạn. Tất cả ngoại lệ cần audit.

## 25. Case study A — endpoint bị ransomware nghi lan qua SMB

**Bối cảnh giả định:** Một laptop doanh nghiệp được EDR xác định chạy mã độc có khả năng mã hóa và mở nhiều connections tới các Windows file servers qua giao thức chia sẻ tệp. Một số máy cùng VLAN có hàng loạt failed access, SOC chưa xác định được dữ liệu đã bị sửa. Không tiến hành malware execution thật để kiểm thử.

### 25.1. Mối đe dọa và phạm vi

~~~mermaid
flowchart LR
    X["Compromised laptop"] --> L["User VLAN / local switching"]
    L --> F["Shared file server"]
    L --> A["AD/identity infrastructure"]
    L --> U["Other endpoints"]
    SOC["SOC/EDR"] -. "Contain command" .-> X
    NAC["NAC/switch policy"] -. "Quarantine access port" .-> L
~~~

**Giả thuyết:** Có lateral movement/unauthorized file activity. **Chưa xác minh:** Tất cả máy trong VLAN nhiễm, malware dùng SMB thành công, hoặc user credentials đã bị lộ.

### 25.2. Quyết định ban đầu

1. Xác minh **agent ID, endpoint, switch port/SSID, IP/MAC + DHCP history, affected shares**.
2. Nếu EDR alert đủ tin, áp **host isolation** và kiểm tra management telemetry.
3. Nếu host kernel/EDR bị nghi tamper, dùng **NAC/switch/host-external firewall** làm enforcement bổ sung.
4. Nếu nhiều endpoints đang lan, IC cân nhắc **temporary east-west SMB deny** hoặc quarantine cả user VLAN theo dependency analysis.
5. Đồng thời kiểm tra **AD credentials, endpoint process, file server access audit**, mở incident theo mức độ thiệt hại thực.

### 25.3. Dữ liệu kiểm chứng

| Câu hỏi | Evidence |
| --- | --- |
| Laptop còn mở SMB connections mới? | Switch/firewall/EDR flow logs, controlled harmless probes |
| Các file servers có activity trái phép tiếp tục? | Server object access/SMB logs, data owner confirmation |
| Có device khác cùng dấu hiệu? | EDR fleet/search, NAC telemetry, network flows |
| Credential của user đã bị dùng ngoài host? | AD/IdP/Kerberos/VPN logs, privileged session audit |
| Quarantine có chặn log collector? | EDR heartbeat, SOC evidence ingestion |
| Dịch vụ sạch có bị collateral deny? | File server SLI, authorized client tests |

### 25.4. Phục hồi

Không đưa laptop trở lại VLAN chỉ vì **malware process ngừng chạy**. Cần **forensic review, approved rebuild/patch, credential reset, EDR clean posture, user access audit và network allow/deny regression**. Nếu có file bị mã hóa, phối hợp backup/data owner để restore và xác minh integrity.

**Bài học:** Khi nguồn được định danh, **host isolation là đòn bẩy đầu tiên**; nếu có bằng chứng lan nhiều hosts, mở rộng containment theo threat path, không vội chặn cả doanh nghiệp từ một alert đơn lẻ.

## 26. Case study B — cloud web VM nghi exfil, nhưng security group dùng chung

**Bối cảnh giả định:** Một EC2-like web VM nghi truyền dữ liệu lớn tới external destination chưa được phê duyệt. VM là thành viên của **security group app-prod-shared** cùng 40 servers, với ENI thứ hai nối tới storage network.

### 26.1. Rủi ro nếu sửa shared SG

Nếu team xóa outbound ALLOW của shared SG, **40 servers cùng mất kết nối** tới DB/KMS/updates. Nếu chỉ chặn public IP ở Internet gateway, VM vẫn có thể truy cập storage/private endpoints và có thể đã bị đánh cắp IAM credentials. Cần lựa chọn **targeted instance/ENI policy**.

### 26.2. Kế hoạch có chứng cứ

1. Xác minh **instance/ENI IDs, all attached SGs, private/public IPs, instance profile/IAM role, subnets, region và owner**.
2. Kiểm tra **VPC flow semantics, NAT mapping, app/DB/object storage audit và out-of-band console**.
3. Gán **dedicated quarantine policy** đúng asset với provider-supported semantics, hoặc dùng external network firewall/instance isolation nếu đổi SG không đảm bảo DENY.
4. Xem **existing connections**, temporary IAM sessions, multi-ENI/storage paths và private endpoints.
5. Giữ approved **forensic/EDR egress** nếu an toàn, log và expiry.
6. Xác nhận các **40 clean servers** vẫn ALLOW, suspected VM bị DENY tới data/Internet, app capacity còn đủ.

### 26.3. Mẫu runbook outcome

~~~text
Affected: web-vm-07 / ENI-a / ENI-b
Unchanged: 40 other instances sharing original SG
Unauthorized destinations: blocked at verified enforcement point
External API credential use: separately disabled/reviewed by IAM owner
Forensic evidence: snapshots/logs protected in separate account/zone
Business: load balancer reroutes to clean web replicas
Remaining: private endpoint and active-session checks
~~~

**Bài học:** Trong cloud, **SG attachment và identity scope** quan trọng hơn tên rule. Chặn đúng instance/ENI và revoke credential giúp hạn chế blast radius, không phá shared group một cách mù quáng.

## 27. Case study C — nhiều Pod cùng namespace bị nghi lateral movement

**Bối cảnh giả định:** Kubernetes namespace **orders-prod** chứa nhiều microservices. Một Pod thuộc Deployment Orders có runtime alert và kết nối tới services ngoài expected service graph. Traffic giữa Pods sử dụng CNI và service mesh mTLS; một số Pods có **hostNetwork** và DNS dùng **NodeLocal DNSCache**.

### 27.1. Điều cần xác định

- Alert gắn với **Pod UID, namespace, node, ServiceAccount, image digest** hay chỉ Pod IP?
- Có những Pods/replicas khác cũng hiện cùng dấu hiệu hay không?
- NetworkPolicy hiện tại đã có **ALLOW all** hoặc CNI-specific policies không?
- Có **mesh peer authorization** cho RPC trái quyền hay chỉ mTLS authentication?
- **HostNetwork, metadata, runtime socket, shared volumes** có là đường bypass không?
- Pod compromise có đi kèm **ServiceAccount token/cloud credential** bị lấy?

### 27.2. Kế hoạch scope nhỏ

1. Kiểm tra **effective CNI policy và existing NetworkPolicies** theo selected Pod labels/identity.
2. Cân nhắc **targeted Pod quarantine** nếu chỉ một Pod affected và có thể ổn định selector.
3. Nếu nhiều Pods/namespace compromised, chuẩn bị **namespace isolation** có approved DNS/EDR/mesh exceptions hoặc giải pháp hẹp hơn bằng CNI.
4. Chặn **unauthorized peer identity** tại mesh/server-side policy, kiểm tra active connections.
5. Đánh giá **controller auto-recreate** và image/config trước khi delete/evict Pod.
6. Kiểm tra **node-level compromise**; nếu có, cô lập node/network ngoài Pod, không chỉ sửa NetworkPolicy.

### 27.3. Phát hiện sai lầm khi chỉ tạo default-deny

Một admin tạo policy **default-deny** cho Pods, nhưng vẫn có **allow-all-egress** policy đang chọn cùng Pod. Trong NetworkPolicy chuẩn, ALLOW policies có thể additive, nên traffic vẫn đi. Mẫu fix cần **review toàn bộ effective policies và data-plane tests**, không tuyên bố default deny đã thắng.

### 27.4. Kết quả mong muốn

| Kiểm thử | Kỳ vọng |
| --- | --- |
| Suspected Pod → unauthorized internal service | DENY |
| Suspected Pod → metadata/STS outside approved path | DENY hoặc hạn chế theo incident policy |
| Suspected Pod → authorized DFIR agent | ALLOW nếu ngoại lệ được duyệt |
| Clean Orders replica → Payments API | ALLOW với mTLS và app authZ đúng |
| Dev namespace → Production service admin RPC | DENY |
| IPv6/hostNetwork/NodeLocal paths | Không có bypass ngoài scope đã ghi |

**Bài học:** Cô lập Kubernetes cần hiểu **Pod lifecycle, CNI semantics và workload identity**. NetworkPolicy, cordon/drain, mTLS và IAM đều có mục tiêu riêng; không có thành phần nào một mình đảm bảo mọi đường đã đóng.

## 28. Case study D — database subnet và nguy cơ phá quorum

**Bối cảnh giả định:** Ba nodes database Production tạo một cụm đồng thuận, cùng với storage replication và backup network. SOC thấy một node có credential theft alert; firewall team đề xuất **DENY toàn bộ DB subnet** để an toàn.

### 28.1. Tác động có thể xảy ra

Nếu cô lập toàn subnet:

- DB replication/cluster membership có thể mất; **quorum** không đạt nếu topology cụ thể đòi hỏi.
- App payments/orders có thể mất cả read/write, gây timeout/queue backlog.
- Backup/storage/monitoring traffic bị cắt, mất khả năng restore/evidence.
- Failing nodes có thể reconnect/tự elect leader gây rủi ro availability hoặc split brain theo database.
- Attack surface ngoài DB subnet có thể vẫn tồn tại nếu **stolen credentials** đã bị copy ra ngoài.

### 28.2. Cách giảm phạm vi

1. **IC + DBA/SRE + IAM + Network** xác định node/credential/operation bị nghi compromised.
2. Giữ **forensic evidence** và đánh giá khả năng **failover sang clean node** theo sản phẩm cụ thể.
3. Nếu một node affected, ưu tiên **isolation node/ENI ở mức hẹp**, đồng thời thay role/credential, **không tắt mọi node**.
4. Nếu cả cluster bị xâm nhập, dùng **business continuity/DR decision** có owner, đánh giá data integrity và recovery point.
5. Không cho compromised node giữ **database admin/session credentials** chỉ để cluster trông healthy.
6. Kiểm thử **clean app connectivity, quorum state, replication lag, read/write SLI** và unauthorized DENY.

### 28.3. Bài học

**Containment sai phạm vi có thể gây sự cố availability lớn hơn mức rủi ro ban đầu.** Nhưng không phải vì sợ downtime mà để attacker tiếp tục truy cập Prod database: cần **quyết định có thẩm quyền, kiểm soát hẹp hoặc DR**, với bằng chứng rõ.

## 29. Lab Python offline: mô phỏng host isolation so với subnet quarantine

Lab dưới đây sử dụng **Python 3.10+ với topology và kết nối tổng hợp trong bộ nhớ**. Nó **không đọc file, không mở socket, không gọi cloud/Kubernetes, không áp firewall, không quét mạng và không đụng hệ thống thật**. Mục đích là so sánh **scope, unauthorized DENY và collateral business impact** để người học thấy vì sao cùng một incident có thể cần chọn host-level thay vì subnet-level.

### 29.1. Mô hình

Có bốn nhóm:

- **app-07**: host nghi compromise trong subnet ứng dụng Production.
- **app-08**: clean replica cùng subnet; vẫn cần kết nối tới DB.
- **prod-db**: dịch vụ database nhạy cảm ở zone khác.
- **edr-hub** và **ir-jump**: endpoint được phê duyệt làm việc với host cách ly.

Các giả định:

1. **Host quarantine:** Chặn new flows chạm tới host **app-07**, trừ chính xác hai kênh IR được phép.
2. **Subnet quarantine:** Chặn new flows chạm tới **bất kỳ host nào** trong app-prod zone, trừ các ngoại lệ IR cho app-07.
3. Phân biệt **blocked threat path** với **blocked legitimate dependency**.
4. **Không mô phỏng existing connection state, asymmetric routing, IPv6, NAT, protocol parsing hay policy union**.

### 29.2. Code Python mô phỏng

~~~python
from dataclasses import dataclass


@dataclass(frozen=True)
class Asset:
    asset_id: str
    zone: str
    suspected_compromise: bool


@dataclass(frozen=True)
class Connection:
    source: str
    destination: str
    channel: str
    business_required: bool
    threat_relevant: bool


ASSETS = {
    "app-07": Asset("app-07", "app-prod", True),
    "app-08": Asset("app-08", "app-prod", False),
    "prod-db": Asset("prod-db", "data-prod", False),
    "edr-hub": Asset("edr-hub", "soc", False),
    "ir-jump": Asset("ir-jump", "soc", False),
    "internet": Asset("internet", "external", False),
}

FLOWS = [
    Connection("app-07", "prod-db", "DB", False, True),
    Connection("app-07", "internet", "HTTPS", False, True),
    Connection("app-07", "edr-hub", "EDR_MGMT", False, False),
    Connection("ir-jump", "app-07", "IR_MGMT", False, False),
    Connection("app-08", "prod-db", "DB", True, False),
]


@dataclass(frozen=True)
class ContainmentPlan:
    name: str
    scope: str  # "host" or "zone"
    target: str
    allow_ir_exceptions: bool


def affected_assets(plan: ContainmentPlan) -> frozenset[str]:
    if plan.scope == "host":
        if plan.target not in ASSETS:
            raise ValueError("Unknown host")
        return frozenset({plan.target})
    if plan.scope == "zone":
        result = frozenset(
            a.asset_id for a in ASSETS.values()
            if a.zone == plan.target
        )
        if not result:
            raise ValueError("Unknown or empty zone")
        return result
    raise ValueError("Unsupported scope")


APPROVED_EXCEPTION_PAIRS = frozenset({
    ("app-07", "edr-hub", "EDR_MGMT"),
    ("ir-jump", "app-07", "IR_MGMT"),
})


def outcome(plan: ContainmentPlan, flow: Connection) -> str:
    affected = affected_assets(plan)
    touches_isolated_asset = (
        flow.source in affected
        or flow.destination in affected
    )
    if not touches_isolated_asset:
        return "ALLOW_UNCHANGED"

    key = (flow.source, flow.destination, flow.channel)
    if plan.allow_ir_exceptions and key in APPROVED_EXCEPTION_PAIRS:
        return "ALLOW_IR_EXCEPTION"
    return "DENY"


def summarize(plan: ContainmentPlan) -> dict:
    denied = [f for f in FLOWS if outcome(plan, f) == "DENY"]
    denied_required = [f for f in denied if f.business_required]
    denied_threat = [f for f in denied if f.threat_relevant]
    return {
        "scope": sorted(affected_assets(plan)),
        "denied_threat_flows": len(denied_threat),
        "denied_business_flows": len(denied_required),
        "approved_ir_flows": sum(
            outcome(plan, f) == "ALLOW_IR_EXCEPTION"
            for f in FLOWS
        ),
    }


host_plan = ContainmentPlan(
    name="isolate-one-host",
    scope="host",
    target="app-07",
    allow_ir_exceptions=True,
)
subnet_plan = ContainmentPlan(
    name="isolate-app-zone",
    scope="zone",
    target="app-prod",
    allow_ir_exceptions=True,
)

for plan in (host_plan, subnet_plan):
    print(plan.name, summarize(plan))

assert summarize(host_plan)["denied_threat_flows"] == 2
assert summarize(host_plan)["denied_business_flows"] == 0
assert summarize(host_plan)["approved_ir_flows"] == 2
assert summarize(subnet_plan)["denied_threat_flows"] == 2
assert summarize(subnet_plan)["denied_business_flows"] == 1
assert outcome(host_plan, FLOWS[-1]) == "ALLOW_UNCHANGED"
assert outcome(subnet_plan, FLOWS[-1]) == "DENY"
~~~

Kết quả dự kiến:

~~~text
isolate-one-host {'scope': ['app-07'], 'denied_threat_flows': 2, 'denied_business_flows': 0, 'approved_ir_flows': 2}
isolate-app-zone {'scope': ['app-07', 'app-08'], 'denied_threat_flows': 2, 'denied_business_flows': 1, 'approved_ir_flows': 2}
~~~

### 29.3. Cách diễn giải kết quả

Cả hai phương án đều chặn **hai threat-relevant paths** từ app-07 theo mô hình. Nhưng subnet plan còn chặn **app-08 → prod-db**, là một kết nối hợp lệ được đánh dấu business required. Vì vậy, nếu tình huống chỉ có bằng chứng compromise **app-07**, host plan là một lựa chọn có blast radius nhỏ hơn trong topology giả định.

**Kết quả không chứng minh subnet quarantine là sai trong mọi tình huống**: nếu attacker đã lan sang app-08 hoặc có host-level enforcement bị vô hiệu hóa, zone containment có thể cần thiết. Quyết định phụ thuộc **threat urgency, host identity trust, hidden paths, technical enforcement coverage và IC authority**.

### 29.4. Giới hạn bắt buộc khi chuyển từ lab tới thực

1. **Static assets:** Không có DHCP/IP reuse, Pod reschedule, cloud ENI lifecycle hoặc MAC spoofing.
2. **Simple flow set:** Không có return packets, session tracking, ACK, NAT/conntrack, local L2, multicast/ARP.
3. **No IPv6/VPN/alternate NIC:** Không thể kết luận coverage đầy đủ nếu topology thực có nhiều đường.
4. **No service dependency graph:** Ứng dụng có thể có hàng trăm dependencies ngoài DB.
5. **No IAM or secret state:** DENY network không xử lý token bị copy ra ngoài.
6. **No timestamp/detection quality:** Code không phân biệt threat confirmed, telemetry stale hay flow log sampling.
7. **No rule interactions:** Production có SG allow union, firewall rule order, NetworkPolicy additive semantics và vendor-specific control behavior.
8. **No automation:** Không apply security groups, isolation ACL hoặc điều khiển thiết bị.
9. **No forensic preservation:** Dữ liệu lab không chứa RAM/packet evidence và không có chain of custody.
10. **No business transaction semantics:** Một luồng DB được phép không chứng minh payment thành công.

### 29.5. Bài tập mở rộng

1. Thêm **criticality và user_count** cho assets, tính blast-radius score nhưng không tự xem nó là quyết định.
2. Thêm **IPv4/IPv6 paths** và xác minh plan chặn cả hai khi được yêu cầu.
3. Mô phỏng **existing connection** khác new connection, policy stateful vs stateless.
4. Thêm **shared SG** cho nhiều instances và một hành động nguy hiểm sửa policy object chung.
5. Thêm **alternate ENI/storage network** để kiểm tra host plan bị bypass.
6. Thêm **time-aware identity mapping** thay cho một IP không đổi.
7. Thêm **policy propagation timestamps** và effective DENY tests.
8. Thêm **approved exceptions có expiry**, không cho exception tràn sang service khác.
9. Thêm **quorum nodes** và kiểm tra DB availability impact trước subnet-level isolation.
10. Thêm **evidence confidence** và NO_DATA, yêu cầu người dùng xác nhận khi coverage thiếu.
11. Phân biệt **APPROVED vs APPLIED vs VERIFIED** thay vì một cờ boolean.
12. Mô phỏng **safe recovery** chỉ sau clean image, credential rotation và sign-off.

**Không dùng output của mô hình offline để tự động áp thay đổi Production.** Nó chỉ giúp người học nhận diện cần hỏi gì trước khi chọn containment.

## 30. Ma trận kiểm thử containment và recovery

Chỉ kiểm thử trên **lab/staging hoặc tài sản/hệ thống có quyền**, với synthetic harmless traffic. Các hành động có thể gây ngừng dịch vụ như **host isolation, NACL subnet, VLAN/VRF, node quarantine hoặc connection table reset** cần có **approval, canary, window, rollback**. Không tự quét cổng, tạo malware traffic hay exfil thật để chứng minh mạng đã an toàn.

| Test ID | Tình huống | Kết quả/bằng chứng kỳ vọng |
| --- | --- | --- |
| IR-01 | Chỉ một host có high-confidence compromise | Chọn host-level containment trước nếu điểm chặn đủ hiệu quả |
| IR-02 | Nhiều hosts trong subnet có dấu lan truyền nhanh | IC đánh giá zone containment và business dependencies |
| IR-03 | Asset có IP DHCP thay đổi | Enforcement gắn đúng device/asset, không cô lập IP đã tái sử dụng |
| IR-04 | Public NAT IP dùng chung nhiều endpoints | Không block tất cả từ một actor chưa xác minh |
| IR-05 | Host có Wi-Fi và Ethernet | Isolation scope bao phủ hai interfaces theo yêu cầu |
| IR-06 | Host dùng IPv6 global route | IPv6 DENY tương đương, không chỉ IPv4 |
| IR-07 | Host có VPN split tunnel | VPN session/route và backend token kiểm soát riêng |
| IR-08 | Host có cloud metadata/STS access | IAM/resource policies và metadata path được đánh giá |
| IR-09 | Host EDR isolation thành công theo console | External network/data-plane DENY được kiểm chứng |
| IR-10 | EDR agent offline/tampered | Có external enforcement alternative và forensic response |
| IR-11 | Isolation giữ EDR management channel | ALLOW đúng verified endpoints, không arbitrary HTTPS |
| IR-12 | Wrong endpoint/agent ID selected | Preflight identity guard chặn thao tác sai |
| IR-13 | NAC chuyển laptop sang quarantine role/VLAN | Network reachability thay đúng, DHCP/DNS/identity được xem |
| IR-14 | Port trên switch là uplink/trunk | Blast-radius guard không chặn nhầm hàng trăm devices |
| IR-15 | Same-VLAN lateral connection | Switch/host/distributed enforcement DENY, router ACL alone không đủ |
| IR-16 | ARP/IPv6 ND/DHCP cần cho quarantine network | Các control-plane flows cần thiết hoạt động có giới hạn |
| IR-17 | VM dùng shared security group | Không sửa shared object gây outage clean instances |
| IR-18 | VM có nhiều ENIs | Đánh giá/kiểm thử mọi đường gắn với host bị cô lập |
| IR-19 | Cloud SG stateful với existing session | Kiểm tra vendor semantics, session termination/deny thực |
| IR-20 | Subnet NACL stateless | Return-path/ephemeral ports được xét, không phá management vô ý |
| IR-21 | Cloud private endpoint bypass Internet firewall | Resource/private network policy thực thi đúng |
| IR-22 | DR/secondary region dùng route khác | Coverage ở mọi region liên quan, không còn bypass |
| IR-23 | L3 ACL chặn inter-VLAN nhưng not L2 | Test ghi rõ same-subnet limitation và control bổ sung |
| IR-24 | Route leak giữa quarantine VRF và Prod | DENY tại đúng điểm L3/firewall, không route leak trái phép |
| IR-25 | Asymmetric return path qua firewall khác | Rule/state/path audit, không suy hiệu lực từ một chiều |
| IR-26 | Rule DENY bị ALLOW ưu tiên cao hơn | Effective rule review phát hiện shadowing |
| IR-27 | New TCP connection tới DB từ compromised host | DENY có firewall/DB evidence |
| IR-28 | Established DB session trước containment | Terminate/restrict theo incident policy được chứng minh |
| IR-29 | Clean replica cùng subnet truy cập DB | ALLOW không ảnh hưởng business nếu host-level containment |
| IR-30 | Whole subnet quarantine chặn clean replica | Collateral impact được dự đoán và phê duyệt hoặc scope thu nhỏ |
| IR-31 | Host không resolve DNS sau quarantine | Kiểm tra exception có kiểm soát; không mở DNS any/any |
| IR-32 | EDR/DFIR collector mất heartbeat | Tách mất visibility khỏi tình trạng host an toàn |
| IR-33 | Host bị suspected root/kernel compromise | Không dựa duy nhất vào host firewall/EDR status |
| IR-34 | Kubernetes Pod targeted quarantine | Đúng Pod identity/labels/UID và CNI data plane DENY |
| IR-35 | Kubernetes default-deny cộng allow-all policy | Test phát hiện NetworkPolicy additive ALLOW |
| IR-36 | Kubernetes node chỉ bị cordon | Không gán tình trạng "isolated" khi Pods vẫn có network |
| IR-37 | Pod rescheduled với identity mới | CNI/mesh policy vẫn chặn phạm vi bị compromise |
| IR-38 | HostNetwork/NodeLocal path trong cluster | Không giả định NetworkPolicy tiêu chuẩn bao trùm mọi path |
| IR-39 | mTLS peer identity revoked | New peer requests bị DENY, existing sessions được đánh giá |
| IR-40 | VPN user disabled nhưng JWT API còn hợp lệ | Resource-server revocation và direct origin bypass được kiểm tra |
| IR-41 | Stolen cloud STS credential | Host isolate không được coi là credential revoked |
| IR-42 | Quarantine VM nhưng SG shared vẫn có other grants | Effective attachment/all SG rules được audit |
| IR-43 | BMC/out-of-band management | Chỉ approved incident access; không bỏ quên host admin path |
| IR-44 | Storage/backup network tách riêng | Đánh giá xem có bypass hoặc data loss qua network này |
| IR-45 | DNS record bị xóa nhưng direct IP còn hoạt động | Detection không dùng DNS absence làm containment proof |
| IR-46 | Flow log đến sau thời điểm cô lập | Phân biệt event-time và ingestion-time trước kết luận bypass |
| IR-47 | Collector mất quyền IAM/KMS ghi logs | Data-quality incident, không khẳng định không còn traffic |
| IR-48 | Cloud/VM snapshot tạo ở network không an toàn | Forensic clone giữ ở isolated evidence environment |
| IR-49 | Memory dump chứa tokens/private keys | Evidence vault/RBAC/retention, không đưa raw vào ticket |
| IR-50 | User/shared NAT có legitimate traffic | Security deny scope hẹp, không tạo false broad outage |
| IR-51 | Malware alert high-confidence đang exfil | Emergency path nhanh, evidence/approval được ghi đúng |
| IR-52 | Low-confidence anomaly chưa chứng minh compromise | Không auto-block cả subnet, có triage/targeted evidence |
| IR-53 | SOAR nhận alert giả hoặc duplicate | Source verification và idempotency, không tạo ACL lặp |
| IR-54 | Automation nhắm core DNS/IdP subnet | Protected object/approval guard ngăn collateral block |
| IR-55 | Changes đã ACK nhưng packets vẫn pass | Effective data-plane validation phát hiện thiếu enforcement |
| IR-56 | App healthy trước change nhưng gRPC lỗi sau containment | Business SLI/connection dependency triage và safe fix |
| IR-57 | DB quorum sẽ mất khi chặn subnet | DBA/IC duyệt failover hoặc scope hẹp, không tự ngắt |
| IR-58 | Trạng thái compromise được giải quyết | Clean rebuild, secrets rotate, sign-off trước khôi phục |
| IR-59 | Host scan “clean” nhưng account bị lộ còn valid | Backend/IAM revoke vẫn bắt buộc |
| IR-60 | Đã restore network nhưng ACL ngoại lệ còn hiệu lực | Retire exceptions, verify unauthorized DENY and desired ALLOW |
| IR-61 | Incident kéo dài nhiều ngày | Exception TTL/review, EDR evidence health và ownership không mất |
| IR-62 | Recovery diễn ra ở DR site khác region | Effective policy và restored service security đồng nhất |
| IR-63 | Rule thay ở firewall nhưng app route đi direct peering | Test đường vòng phát hiện bypass chưa xử lý |
| IR-64 | Wi-Fi/4G/cellular vẫn có kết nối sau NAC quarantine | Device/session revoke, không tự xem NAC là global isolation |
| IR-65 | Service mesh mTLS cert vẫn được dùng sau Pod cô lập | Peer deny/credential rotation/active session checks |
| IR-66 | Detection alert auto-resolved sau network drop | Không đồng nghĩa malware eradicated; incident vẫn mở |
| IR-67 | IC yêu cầu khôi phục sớm vì SLO | Risk acceptance/alternate mitigation có audit, không mở ANY/ANY vô hạn |
| IR-68 | Cùng subnet có mixed production/tenant data | Inventory, classification và blast-radius review trước quarantine |
| IR-69 | Host chứa nhiều critical workloads/hypervisor | Không cô lập uplink/host chung mà thiếu impact approval |
| IR-70 | Authorized DFIR channel qua proxy chung | Verify no unauthorized proxy tunneling/egress path |

### 30.1. Bản ghi kiểm thử tiêu chuẩn

~~~text
TEST ID / INCIDENT ID / CHANGE ID:
ENV / ACCOUNT / REGION / VPC / VLAN / SUBNET / HOST ID:
DETECTION SOURCE, CONFIDENCE, TIME UTC:
APPROVER / OPERATOR / TEST OWNER:
PEP (EDR/NAC/FIREWALL/SG/NACL/CNI/APP) AND POLICY VERSION:
SOURCE/DESTINATION / IP FAMILY / PROTOCOL / DIRECTION:
THREAT-RELEVANT EXPECTED DENY:
BUSINESS-REQUIRED EXPECTED ALLOW:
NEW CONNECTION RESULT / EXISTING SESSION RESULT:
PEP RULE READBACK / NETWORK FLOW LOG / DESTINATION AUDIT:
CONTROL-PLANE ACK TIME / DATA-PLANE ENFORCEMENT TIME:
ALTERNATE NETWORK PATH TESTS / UNVERIFIED PATHS:
EDR/SIEM AVAILABILITY / DATA QUALITY:
SERVICE SLO / COLLATERAL IMPACT:
ROLLBACK/TRUSTED RECOVERY/EXCEPTION EXPIRY:
RESULT: PASS / FAIL / PARTIALLY_VERIFIED / NOT_TESTED:
REMAINING RISK / OWNER / NEXT REVIEW:
~~~

### 30.2. Kiểm thử ba chiều

**Tối thiểu phải chứng minh cả ba:** (1) traffic trái quyền từ affected asset đến tài nguyên quan trọng **DENY**, (2) traffic cần thiết từ clean services hoặc secure DFIR path **ALLOW**, (3) alternate paths **được kiểm tra hoặc được ghi UNKNOWN**. Chỉ đọc thấy firewall rule tồn tại không đủ.

### 30.3. Thử nghiệm không được tạo sự cố mới

Không flood mạng, scan tài sản bên thứ ba, phát malware thật hoặc chuyển dữ liệu khách hàng làm payload để chứng minh deny. Dùng **test service, synthetic tokens, harmless connection attempt và lab**. Với Production, mọi thao tác active test phải theo **scope/approval**, chuẩn bị emergency rollback và application SLI monitoring.

## 31. Những hiểu nhầm thường gặp về khoanh vùng mạng

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Cô lập host là đã loại bỏ malware.” | Containment giới hạn kết nối; eradication/recovery là các giai đoạn riêng. |
| “Xóa một Pod/VM là đã thu hồi mọi token.” | Credentials và cloud sessions có thể còn được backend chấp nhận. |
| “Không ping được nghĩa là máy đã cô lập hoàn toàn.” | ICMP khác TCP/UDP, local routes, existing sessions và IPv6. |
| “Tắt Internet là ngăn được mọi lateral movement.” | East-west trong VLAN/cluster/private network vẫn có thể chạy. |
| “Chặn inbound là đủ chống exfiltration.” | Egress hoặc existing connections có thể còn mở. |
| “Chặn outbound là đủ chống lateral movement.” | Remote incoming paths, allowed proxies và local L2 vẫn cần xét. |
| “Router ACL chặn được mọi traffic cùng VLAN.” | Same-L2 switched traffic có thể không qua router. |
| “Một subnet chỉ có các máy nghi nhiễm.” | Có thể chứa shared services và clean workloads. |
| “Một public IP bằng một máy attacker.” | NAT/VPN/CDN/shared address có thể chứa nhiều identities. |
| “Pod IP hiện tại cho biết ai dùng IP hôm qua.” | IP có thể tái sử dụng, cần historical Pod UID/asset mapping. |
| “Một security group chỉ gắn với một VM.” | Shared groups có thể áp nhiều instances/ENIs. |
| “Security group đổi là mọi established session bị cắt ngay.” | Stateful connection tracking và hiệu lực phụ thuộc provider. |
| “Network ACL stateless tự nhận biết return packets.” | Return-path/ephemeral ports phải xét theo semantics. |
| “Đã đổi VLAN thì tất cả NIC của máy bị chặn.” | Wi-Fi/secondary NIC/VPN/cellular có thể còn đường khác. |
| “VRF có tên quarantine là không thể sang Prod.” | Route leaks, shared services, transit/peering có thể nối VRFs. |
| “Chặn IPv4 là đủ vì client thường dùng IPv4.” | IPv6/dual-stack có thể có route và DNS AAAA. |
| “Xóa DNS record là không kết nối được tới host.” | Direct IP, cached DNS, DoH/alternate resolvers vẫn tồn tại. |
| “Kubernetes cordon là network isolation.” | Cordon ngăn scheduling mới, không chặn traffic của Pods đang chạy. |
| “Drain node tự động vô hiệu compromised workload.” | Có thể reschedule Pod/image/secrets sang node khác. |
| “Default-deny NetworkPolicy luôn thắng allow-all.” | Các ALLOW NetworkPolicies chuẩn có thể additive. |
| “Service mesh mTLS đảm bảo mọi traffic đều qua proxy.” | Có excluded paths, hostNetwork, ambient/no-sidecar hoặc CNI bypass. |
| “mTLS cert valid nghĩa là Pod chưa bị compromise.” | Compromised process có thể sử dụng identity hợp lệ. |
| “EDR isolate luôn an toàn dù attacker có kernel root.” | Agent/host controls có thể bị tamper; cần external enforcement. |
| “EDR offline chứng minh attacker đã tắt nó.” | Cũng có thể do network policy, agent fault hoặc telemetry gap. |
| “Một EDR isolation command ACK chứng minh không còn flow.” | Cần effective data-plane/server-side validation. |
| “Firewall DENY hit tăng là malware vẫn đang chạy.” | Clean application retry hoặc health probes có thể tạo hits. |
| “Flow log đến sau change nghĩa là rule bị bypass.” | Event time và ingestion time có thể chênh lệch. |
| “Tất cả 443 là HTTPS an toàn.” | Port không chứng minh protocol/identity, proxy tunneling có thể xảy ra. |
| “Mở DNS/HTTPS ANY để EDR liên lạc là exception nhỏ.” | Có thể giữ rộng exfil path; cần verified endpoints. |
| “Chặn API IP đồng nghĩa revoke IAM.” | Attacker có thể dùng tokens ở IP/host khác. |
| “Tắt máy là cách tốt nhất để giữ evidence.” | Mất RAM/sockets/volatile state; cân nhắc severity và forensics. |
| “Memory dump có thể gửi vào ticket thường.” | Có thể chứa keys, tokens, PII; cần evidence vault/RBAC. |
| “Snapshot disk chứng minh trạng thái memory.” | Disk snapshot không giữ volatile memory, consistency cần đánh giá. |
| “Trước khi cách ly phải thu thập mọi bằng chứng.” | High-confidence active harm có thể cần containment ngay. |
| “Chặn toàn subnet luôn an toàn hơn chặn một host.” | Collateral outage/quorum loss có thể làm khủng hoảng lớn hơn. |
| “Business critical nên không bao giờ được cô lập.” | Có thể cần emergency action/DR, với phê duyệt và phạm vi phù hợp. |
| “Một connection bị firewall block chứng minh app không thể bị lạm dụng.” | Còn alternative paths, cached tokens và application authorization. |
| “IP allowlist là chứng cứ định danh user.” | NAT/IP reuse không bằng cryptographic session/workload identity. |
| “Mất SIEM alerts nghĩa là containment thành công.” | Collector/permissions bị mất có thể gây blind spot. |
| “Automation anomaly score cao có thể ngắt mọi subnet.” | Cần confidence, blast-radius guard, approval, scope và rollback. |
| “Sửa được outage thì có thể mở ANY/ANY lâu dài.” | Exception phải time-boxed, owner-reviewed và còn deny threat path. |
| “Host hết traffic nghĩa là an toàn để phục hồi.” | Có thể offline/collector missing; phải xử lý root cause/credentials. |
| “Khôi phục mạng là hoàn tất incident.” | Recovery gồm clean state, entitlement, data integrity, SLO và postmortem. |

## 32. Câu hỏi ôn tập và bài tập tình huống

1. **Containment khác eradication ở đâu?** Containment hạn chế rủi ro đang diễn ra; eradication loại bỏ nguyên nhân/persistence.
2. **Khi nào chọn host isolation?** Khi định danh được nguồn compromised và host-level/external enforcement đủ chặn threat paths.
3. **Khi nào cân nhắc subnet containment?** Khi nhiều hosts cùng vùng affected hoặc threat lan nhanh không thể kiểm soát bằng host-level scope đủ nhanh.
4. **Vì sao cần IC approval?** Thao tác subnet/zone có thể tác động an toàn, business continuity, identity và logging.
5. **Tại sao ping không đủ kiểm chứng?** Nó chỉ thử một protocol/path, không bao phủ existing TCP, UDP hay IPv6.
6. **EDR isolation có giới hạn nào?** Agent health/tamper, coverage của interfaces, exceptions và session semantics.
7. **Vì sao external enforcement quan trọng khi kernel bị chiếm?** Attacker có thể thao túng host firewall/agent.
8. **Cô lập bằng NAC có thể làm đổi điều gì?** VLAN/role/DHCP/IP/route và network reachability.
9. **Port trunk khác access port trong phản ứng ra sao?** Chặn trunk có thể ngắt nhiều thiết bị, blast radius lớn.
10. **Tại sao ACL tại gateway không luôn chặn host cùng VLAN?** Traffic local L2 có thể đi qua switch trực tiếp.
11. **SG dùng chung nguy hiểm thế nào?** Sửa SG có thể ảnh hưởng nhiều instances ngoài mục tiêu.
12. **NACL stateless cần xét gì?** Return traffic, ports, both directions và route.
13. **Cloud instance bị cô lập mạng thì STS token đã copy có hết hiệu lực?** Không mặc định.
14. **NetworkPolicy default deny có thắng ALLOW khác không?** Không mặc định với additive semantics.
15. **Cordon/drain có thay cô lập node không?** Không; drain còn có thể tái triển khai compromised workload.
16. **Tại sao cần kiểm tra IPv6?** Alternate address family có thể bypass IPv4-only policies.
17. **DNS record biến mất có nghĩa host không thể reach?** Không; cached/direct IP/private links vẫn tồn tại.
18. **Quarantine network phải có ngoại lệ nào?** Chỉ những remediation/EDR/forensic/control paths được phê duyệt và cần thiết.
19. **Tại sao EDR heartbeat mất không chắc là compromise?** Có thể bị chính network isolation hoặc telemetry lỗi.
20. **Tại sao phải giữ log event time và ingested time riêng?** Tránh kết luận bypass từ records được giao muộn.
21. **Một active TLS session có thể còn sau firewall change không?** Có thể, tùy stateful tracking và enforcement.
22. **Tại sao không chặn broad DNS/IdP/AD subnet khi chưa phân tích?** Có thể phá cả xác thực, name resolution và recovery.
23. **Vì sao database cần xem quorum?** Ngắt node/subnet có thể ảnh hưởng consistency/availability của cụm.
24. **Cách xác minh clean app flows?** Synthetic harmless app requests, DB/app logs và business SLI.
25. **Một firewall DENY có đủ chứng minh exfil đã dừng?** Chỉ trong đúng path/flow được thử; cần xem alternate paths và data logs.
26. **Một endpoint bị ransomware có nên reboot ngay?** Cân nhắc hiện trạng harm, volatile evidence, business effect và incident plan.
27. **Chặn IP của VPN proxy có thể ảnh hưởng ai?** Nhiều users/devices chia sẻ NAT/egress IP.
28. **Tại sao SOP phải phân biệt new vs existing connections?** Rule change có thể không ngắt sockets đã established.
29. **Quyết định không tìm thấy logs là DENY hay UNKNOWN?** Thường là UNKNOWN/coverage gap nếu thiếu data-plane evidence.
30. **Khi nào được gỡ quarantine?** Sau forensic/remediation/credential reset/validation và phê duyệt theo policy.
31. **Vai trò của automation blast-radius guard là gì?** Tránh một alert/config lỗi dẫn tới chặn quá nhiều tài sản.
32. **Nếu business outage do containment, nên làm gì?** Xác định flow cần thiết, sửa scope hẹp/DR, giữ unauthorized DENY, audit ngoại lệ.

### Bài tập cuối chương

Một doanh nghiệp vận hành **mạng người dùng, VPN/ZTNA, hai app subnets, Kubernetes cluster, database subnet, DNS/AD, cloud private endpoints và Internet egress gateway**. SOC nhận ba tín hiệu: một laptop có verified malware alert, một Pod Production kết nối tới peer lạ và từ DB subnet xuất hiện nhiều outbound flows chưa được giải thích.

Hãy soạn **network incident containment plan** gồm:

1. Inventory asset IDs, VLAN/subnet/VRF, IP families, NAT/ENI/Pod UID và user/workload identities.
2. Vẽ **data flow và trust boundaries** trước/ sau containment cho mỗi đối tượng.
3. Chọn **host vs subnet/zone containment** theo confidence, severity, business impact.
4. Chỉ rõ **PEP**: EDR/NAC/switch/firewall/cloud SG/NACL/CNI/service mesh/VPN.
5. Liệt kê **denied flows và approved exceptions**, cả forward/return path.
6. Kiểm tra **same-subnet L2, alternate interfaces, IPv6, cloud private endpoints và split tunnel**.
7. Bảo vệ **DNS, IdP, SIEM, EDR management và database quorum** theo threat model, không mở rộng quá mức.
8. Ghi **forensic evidence plan** và chain of custody, quyết định volatile data khi cần.
9. Lập **credential/session revocation plan**, gồm cloud STS, VPN/ZTNA, Kubernetes ServiceAccount và mTLS.
10. Xây dựng **test matrix** với ALLOW/DENY/new-vs-existing flows, CNI/SG propagation, app business SLI.
11. Tạo runbook **change approval, emergency containment, rollback, restoration và postmortem**.
12. Đề xuất dashboard **effective containment latency, bypass risk, collateral deny, app SLO, telemetry coverage**.

**Tiêu chí chấm:** Bản thiết kế phải bảo vệ **tài nguyên quan trọng khỏi actor có thể bị compromise** nhưng không tự làm sập toàn bộ hệ thống khi một host affected. Các quyết định cần **phạm vi rõ, bằng chứng ở data plane, điều kiện kiểm chứng và phương án recovery có sign-off**. Không coi việc đổi firewall rule thành công là đích cuối.

## 33. Checklist khoanh vùng máy chủ hoặc subnet an toàn

- [ ] Incident có **ID, severity, source evidence, confidence, UTC timeline và owner**?
- [ ] Đã phân biệt **host compromise xác định** với chỉ một tín hiệu behavior bất thường?
- [ ] Có người **incident commander/security approver** cho phạm vi/rủi ro containment?
- [ ] Biết tài sản qua **EDR agent ID, instance/ENI, Pod UID, switch port, ServiceAccount**, không chỉ IP?
- [ ] Đã xác minh **DHCP/NAT/POD-IP historical mapping**, subnet CIDR và owners?
- [ ] Đã vẽ **ingress/egress/east-west path**, L2 same-VLAN, routing/peering?
- [ ] Đã inventory **IPv4/IPv6, VPN/tunnel, Wi-Fi/alternate NIC, metadata/private endpoints**?
- [ ] Phạm vi được chọn là **điểm nhỏ nhất đủ hiệu quả**, hoặc có phê duyệt emergency rộng?
- [ ] Có **pre-change config snapshot**, rollback path và chính sách emergency access?
- [ ] Đã cân nhắc **volatile memory/process/sockets, PCAP, EDR, cloud/K8s/audit logs**?
- [ ] Forensic evidence có **RBAC, encryption, retention, checksum/chain of custody khi phù hợp**?
- [ ] Có bảo vệ **DNS/DHCP/NTP, IdP/AD, EDR/IR/SIEM, KMS, storage/quorum** theo use case?
- [ ] Mọi exception có **source/destination/port/protocol/time/owner/approval** cụ thể?
- [ ] Không có exception rộng **ANY/ANY, wildcard proxy, arbitrary DNS/HTTPS** ngoài chính sách đã duyệt?
- [ ] EDR/host firewall coverage được kiểm tra cùng **external PEP** khi host không đáng tin?
- [ ] Nếu NAC, đã biết **switch access port vs uplink/trunk**, DHCP/VLAN effects?
- [ ] Nếu firewall, đã kiểm tra **rule order, shadowing, state table, NAT, forward/return paths**?
- [ ] Nếu VRF/VLAN, đã kiểm tra **route leaks, L2 local traffic và shared services**?
- [ ] Nếu cloud, đã kiểm tra **shared SG/NSG, multi-ENI, NACL statefulness, private endpoints**?
- [ ] Nếu Kubernetes, đã kiểm tra **CNI support, additive policies, hostNetwork/NodeLocal, Pod/controller lifecycle**?
- [ ] Nếu VPN/ZTNA, đã xử lý **active sessions, end-user/resource authorization và copied bearer tokens**?
- [ ] Đã đánh giá **IAM/STS, API keys, kubeconfig/ServiceAccount, mTLS/PKI và DB credentials** liên quan?
- [ ] Không tự xem **network DENY** là đã thu hồi cloud/session/identity grants?
- [ ] Có **policy intent vs effective PEP readback** rõ ràng?
- [ ] Có thử **new denied connections và existing sessions**, đúng loại protocol?
- [ ] Các luồng không được phép qua **IPv6/alternate interfaces/DR region** đã được kiểm chứng hoặc ghi UNKNOWN?
- [ ] Đã đối chiếu **destination app/DB audit** để biết unauthorized requests còn thành công không?
- [ ] **Clean workloads và approved IR/remediation** vẫn hoạt động trong SLO?
- [ ] **Collector/EDR/SIEM heartbeat** còn khả dụng; không biến NO_DATA thành “safe”?
- [ ] Đã ghi **policy propagation và effective containment time**, không chỉ API ACK?
- [ ] Auto containment có **source integrity, idempotency, blast-radius guard, kill switch và approval**?
- [ ] Có kiểm soát **quarantine exceptions/expiry** và review trong incident dài ngày?
- [ ] Có kế hoạch **forensic investigation, root cause, trusted rebuild/patch, credential rotation**?
- [ ] Recovery có **app/data integrity, identity posture và approval** trước khi đưa host về zone bình thường?
- [ ] Có **canary restore**, kiểm tra legitimate ALLOW và unauthorized DENY sau change?
- [ ] Đã gỡ **obsolete exception/routing rules**, cập nhật inventory và detection coverage?
- [ ] Postmortem ghi **collateral impact, blind spots, false positives, remaining risk, owners và deadlines**?

**Kết luận:** **Khoanh vùng máy chủ hoặc subnet** là bài toán giới hạn đường di chuyển của rủi ro mà không phá vỡ tùy tiện các hệ thống sạch. Một phản ứng tốt bắt đầu từ **định danh đúng tài sản và threat path**, chọn **host- hoặc zone-level enforcement** tương xứng, giữ **chứng cứ và các phụ thuộc điều hành cần thiết**, đồng thời **thu hồi credential/phiên có thể bị lộ**. Phải kiểm tra **L2/L3, ingress/egress, return path, cloud/Kubernetes, IPv4/IPv6 và các đường bypass**, phân biệt **cấu hình đã áp** với **unauthorized traffic thật sự bị từ chối**. Chỉ phục hồi khi **nguyên nhân đã được xử lý, quyền được kiểm tra lại, các luồng hợp lệ hoạt động và những đường trái quyền vẫn bị chặn**.
