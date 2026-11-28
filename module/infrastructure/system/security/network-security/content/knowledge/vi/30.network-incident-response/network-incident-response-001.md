# Network incident response lifecycle — Vòng đời ứng phó sự cố mạng

Một hệ thống thương mại điện tử bất ngờ có tỷ lệ HTTP 5xx tăng cao. NOC nhận thấy băng thông inbound lên đột biến; SOC nhận cảnh báo số kết nối tới một địa chỉ lạ tăng; đội ứng dụng báo API không thể kết nối database. Nếu chỉ nhìn lưu lượng, nhóm có thể vội kết luận đang bị DDoS và chặn cả subnet của khách hàng. Nhưng nguyên nhân cũng có thể là thay đổi định tuyến, cấu hình firewall sai, chứng chỉ TLS hết hạn, lỗi DNS, hoặc một workload bị chiếm quyền đang quét mạng nội bộ. **Cùng một triệu chứng có thể dẫn đến các hành động ứng phó rất khác nhau.**

**Network incident response lifecycle** là cách tổ chức các hoạt động **chuẩn bị, phát hiện, phân tích, quyết định, cô lập/giảm tác động, xử lý nguyên nhân, phục hồi và cải tiến** trong những sự cố ảnh hưởng tới kết nối, tính sẵn sàng, tính toàn vẹn hoặc tính bí mật của hệ thống mạng. Vòng đời không phải checklist chạy một chiều: khi tìm thấy chứng cứ mới, nhóm có thể phải quay lại điều tra, mở rộng phạm vi cô lập, điều chỉnh truyền thông hoặc dừng phục hồi.

Bài thuộc chương **Ứng phó sự cố mạng** của module **SECURITY_NETWORK_SECURITY**. Nội dung kết nối kiến thức phân đoạn mạng, firewall, VPN, IDS/IPS, xác thực kết nối, DNS, Wi-Fi, cloud networking, packet capture, lưu lượng, threat modeling và giám sát xâm nhập để hình thành một quy trình xử lý sự cố an toàn, có chứng cứ và có thể kiểm toán.

**Nguyên tắc:** **Ổn định tình hình và bảo vệ con người/hệ thống trước; xác minh bằng chứng thay vì suy đoán; áp thay đổi có phạm vi, người chịu trách nhiệm và đường hoàn tác; giữ lại đủ chứng cứ hợp lệ; chỉ tuyên bố phục hồi khi có tiêu chí đo được.**

## 1. Mục tiêu học tập

Sau bài này, bạn cần:

1. Mô tả các giai đoạn của **network incident response lifecycle** và lý do chúng có thể diễn ra đồng thời hoặc lặp lại.
2. Phân biệt **network event, alert, anomaly, security incident, outage** và khái niệm **severity, scope, confidence**.
3. Thiết kế năng lực chuẩn bị: asset inventory, network diagrams, logging, phân vai, playbook, quyền khẩn cấp và diễn tập.
4. Phân tích sự cố từ **network flow, DNS, firewall, IDS/IPS, WAF, VPN, TLS, cloud flow logs, Kubernetes/CNI và ứng dụng**.
5. Xây dựng timeline, giả thuyết và evidence log với **độ tin cậy, clock synchronization, chain of custody**.
6. Lựa chọn containment phù hợp: cô lập host/VLAN/Pod, giới hạn ACL, thu hồi phiên, giảm DDoS, bảo vệ origin và hạn chế lateral movement.
7. Tách **containment** khỏi **eradication**, **recovery** và **post-incident improvement**.
8. Cân bằng các rủi ro **mất chứng cứ, lan rộng tấn công, outage, business continuity và an toàn vận hành**.
9. Phối hợp SOC/NOC/SRE/IT/IAM/cloud/application/Legal theo một command structure rõ.
10. Tự thiết kế incident runbook, ma trận positive/negative tests, chỉ số phản ứng và checklist bàn giao.

## 2. Phạm vi: sự cố mạng không chỉ là “mạng bị down”

Sự cố mạng có thể liên quan một hoặc nhiều thuộc tính **Confidentiality, Integrity, Availability (CIA)**:

| Nhóm | Ví dụ | Dấu hiệu quan sát | Điều chưa thể suy ra |
|---|---|---|---|
| **Availability** | DDoS, link saturation, lỗi BGP/route, DNS outage | Packet loss, timeout, jitter, 5xx, interface drops | Không phải mọi spike là tấn công |
| **Confidentiality** | DNS tunneling, exfiltration qua HTTPS, truy cập VPN trái quyền | Egress bất thường, volume lớn, DNS queries lạ | Traffic lớn không chứng minh exfiltration |
| **Integrity** | DNS poisoning, route hijack, config ACL bị thay | Trả DNS sai, route/path thay đổi, audit config | Một record khác lạ có thể là thay đổi hợp lệ |
| **Lateral movement** | Thiết bị bị chiếm cố truy cập SMB/RDP/SSH sang hệ thống khác | New east–west flows, auth failures | Một scan nội bộ có thể là asset discovery đã phê duyệt |
| **Control-plane compromise** | IAM/API/firewall policy bị sửa trái phép | Audit logs, allow-all rule, connector thay đổi | Thay đổi không có ticket không tự chứng minh malicious |
| **Policy failure** | CNI NetworkPolicy không enforce, VPN split tunnel sai | Flow được phép ngoài baseline | Có thể do kiến trúc hoặc cấu hình không chủ đích |
| **Hybrid/cloud incident** | Public endpoint vô tình mở, peering route sai | VPC flow logs, cloud config drift | Một IP public không tự là lộ dữ liệu nếu không reachable |

### 2.1. Event, alert và incident khác nhau

- **Event:** một sự kiện quan sát được, ví dụ firewall từ chối TCP/445.
- **Alert:** điều kiện giám sát phát hiện, ví dụ 1.000 kết nối bị từ chối trong 5 phút.
- **Anomaly:** khác biệt so với baseline, ví dụ DNS requests tăng gấp nhiều lần.
- **Security incident:** diễn biến có căn cứ cần xử lý vì rủi ro/ảnh hưởng an ninh, theo tiêu chí tuyên bố của tổ chức.
- **Operational outage:** suy giảm dịch vụ do lỗi kỹ thuật; có thể cần incident management nhưng không nhất thiết là security incident.
- **Confirmed compromise:** kết luận nghiêm trọng hơn, cần chứng cứ về xâm nhập hoặc lạm dụng thực tế, không chỉ alert.

Một alert có thể **false positive**; một sự cố có thể có **nhiều alerts**; nhiều sự cố vận hành và an ninh có thể **đồng thời xảy ra**. Quy trình cần cơ chế nâng/hạ mức độ khi có chứng cứ mới.

### 2.2. Phạm vi trách nhiệm

Network IR xử lý **đường truyền và network controls**, nhưng không tự thay:

- **Host/endpoint incident response**: malware, persistence, memory/disk forensics.
- **Identity incident response**: IdP compromise, credential/session theft, IAM/PAM.
- **Application IR**: lỗ hổng API, BOLA, input validation và quyền tenant.
- **Data breach response**: xác định dữ liệu bị truy cập/xuất, nghĩa vụ thông báo và privacy.
- **Business continuity/DR**: dịch vụ tối quan trọng, RTO/RPO, failover và khôi phục hoạt động.

Những nhóm này cần phối hợp vì một đường mạng bất thường thường là **triệu chứng**, không phải toàn bộ nguyên nhân.

## 3. Vòng đời tổng quan

Một khung ứng phó phổ biến gồm **Preparation → Detection & Analysis → Containment → Eradication → Recovery → Lessons Learned**. Đây là **mô hình học tập thực dụng**, không phải khẳng định mọi tiêu chuẩn đều có đúng sáu ô hoặc bắt các tổ chức chạy tuần tự. Các phương pháp hiện đại thường đặt **quản trị rủi ro, phối hợp, học hỏi và cải tiến** xuyên suốt.

~~~mermaid
flowchart LR
    PRE["0. Prepare / Sẵn sàng"] --> DET["1. Detect & Analyze"]
    DET --> TRI["2. Triage, declare, scope"]
    TRI --> CON["3. Contain / Reduce harm"]
    CON --> ERA["4. Eradicate / Fix root cause"]
    ERA --> REC["5. Recover / Validate"]
    REC --> LEARN["6. Learn & improve"]
    LEARN -.-> PRE
    CON -.->|"Chứng cứ mới"| DET
    REC -.->|"Tái phát / test fail"| TRI
~~~

**Không đồng nhất “khắc phục nhanh” với “điều tra đã xong”.** Một rule tạm chặn traffic có thể giảm tác động nhưng không loại bỏ tài khoản bị lộ hay cấu hình route sai; phục hồi một service thành công không chứng minh đối thủ đã mất mọi foothold.

### 3.1. Bảng đầu ra theo giai đoạn

| Giai đoạn | Câu hỏi chính | Đầu ra tối thiểu |
|---|---|---|
| **Prepare** | Ai làm gì, có công cụ/quyền/telemetry gì? | Inventory, runbooks, access, escalation, tabletop evidence |
| **Detect & Analyze** | Điều gì khác thường, bắt đầu từ đâu, xác suất gì? | Signals, timeline, hypotheses, confidence, impacted assets |
| **Triage & Declare** | Có cần kích hoạt incident, severity nào, ai chỉ huy? | Incident ID, commander, scope, priority, communication plan |
| **Contain** | Làm gì để giảm tổn hại ngay mà không mở rộng outage? | Approved temporary controls, owner, rollback và evidence |
| **Eradicate** | Nguyên nhân/lỗ hổng/credentials nào phải xử lý? | Fix, credential rotation, clean-state validation |
| **Recover** | Dịch vụ và an ninh đã về trạng thái chấp nhận được chưa? | SLO checks, threat/flow checks, monitoring plan, formal sign-off |
| **Learn** | Vì sao phát hiện muộn/chặn chưa đúng; phòng tái phát? | RCA, action items, owners, deadlines, tests, updated playbooks |

### 3.2. Vòng phản hồi

Nếu khi khôi phục một firewall rule mở lại outbound traffic mà C2 connections xuất hiện, **quay lại containment và phân tích**. Nếu phát hiện thêm subnet/tenant bị ảnh hưởng, phải **mở rộng scope, thông báo và evidence collection**, không giữ severity ban đầu vì muốn báo cáo đẹp.

## 4. Giai đoạn 0 — Preparation: chuẩn bị trước khi xảy ra sự cố

Ứng phó không bắt đầu vào lúc đèn đỏ xuất hiện trên dashboard. Chất lượng điều tra phụ thuộc những công việc đã chuẩn bị khi hệ thống còn bình thường.

### 4.1. Tài sản và data flow

Tối thiểu phải biết:

| Đầu vào | Ví dụ | Lý do |
|---|---|---|
| **Asset inventory / ownership** | Router, firewall, VPC, cluster, WAF, VPN, DNS resolver, server/app | Xác định ai quyết định và cô lập đúng tài sản |
| **Network topology** | VLAN, subnet, routing, peering, NAT, VPN, LB, ingress/egress | Không chặn nhầm đường đang phục vụ sản phẩm |
| **Critical flows** | Web→API, API→DB, backup, identity, DNS, telemetry | Biết luồng nào không được làm gián đoạn tùy tiện |
| **Trust boundaries** | Tenant zone, prod/dev, management, internet, OT DMZ | Xác định blast radius và lateral paths |
| **Identity/policy mapping** | Service accounts, VPN groups, bastions, firewall ACL owners | Revocation và least privilege |
| **Dependencies** | IdP, CA, DNS, time source, cloud API, SIEM, ticketing | Biết sự cố nào có thể gây mất visibility/command |
| **Data classification** | PII, secrets, payment logs, backups, regulated assets | Quy định evidence handling và legal engagement |
| **Recovery dependencies** | Out-of-band access, clean backups, config snapshots | Tránh mất khả năng phục hồi sau containment |

**Network diagram có thể cũ.** Phải có quy trình cập nhật khi thay routes, NAT, cloud regions, Kubernetes services hoặc service mesh egress paths; nếu không, “chặn subnet X” có thể ảnh hưởng tài nguyên ngoài dự tính.

### 4.2. Telemetry và khả năng lưu giữ

Những nguồn dữ liệu thường có ích:

- **Firewalls/ACL/security groups:** allow/deny, rule ID, before/after NAT addresses khi có.
- **NetFlow/IPFIX/sFlow/VPC flow logs:** 5-tuples, bytes/packets/direction, timestamps và action, theo đặc tính mỗi nguồn.
- **DNS resolver logs:** query/response type, resolver/client identity nếu được ghi, TTL và errors.
- **Proxy/WAF/Ingress/Gateway:** hostname/path/route, status, auth result, source identity đáng tin, upstream latency.
- **IDS/IPS/EDR/NDR:** detections, confidence, signatures, flow context, process attribution khi hỗ trợ.
- **VPN/ZTNA/IdP:** logins, device/user identity, sessions, MFA, PDP/PEP decisions và revocations.
- **Switch/router/NIC:** interface errors, saturation, drops, routing changes, BGP/BFD/session state.
- **Kubernetes/CNI/service mesh:** Pod/namespace identity, policy verdict, ingress/egress, audit và control plane changes.
- **Hosts/applications:** process/service health, auth events, TLS errors, business request IDs.
- **Packet capture:** chỉ khi cần packet-level evidence; raw PCAP có rủi ro dữ liệu nhạy cảm cao.

**Không phải log nào cũng chứa mọi trường.** Cloud flow logs có thể là sampled/aggregated/rejected theo gói dịch vụ; firewall logs có thể ghi IP đã NAT; DNS cache có thể khiến một request không tạo query mới. Việc **không có log** không tự chứng minh **không có hoạt động**.

### 4.3. Đồng bộ thời gian

Một timeline đáng tin phải ghi:

- Múi giờ hiển thị và timestamp dạng có timezone, ưu tiên ISO 8601/UTC cho trao đổi giữa hệ thống.
- Nguồn đồng hồ của appliance, VM, container, cloud services và sensor.
- Độ lệch đã biết của những nguồn không đồng bộ và độ trễ ingest log.
- Sự khác nhau giữa **event time**, **collector receive time**, **alert time** và **analyst observation time**.

~~~text
2026-11-28T03:15:18Z  Firewall: deny TCP/445 from asset A
2026-11-28T03:15:27Z  IDS: suspected lateral-movement pattern
2026-11-28T03:15:42Z  SOC: analyst acknowledges alert

Chỉ là dữ liệu minh họa.
Nếu firewall lệch đồng hồ -25 giây, thứ tự thực cần hiệu chỉnh.
~~~

Không chỉnh sửa timestamp của evidence thô để timeline trông gọn. Lưu **raw timestamp và normalized timestamp** ở bản phân tích riêng, ghi rõ phương pháp chuẩn hóa.

### 4.4. Phân vai: ai được phép ra quyết định?

| Vai trò | Trách nhiệm | Giới hạn |
|---|---|---|
| **Incident Commander (IC)** | Ưu tiên, điều phối, quyết định escalation và tổng hợp trạng thái | Không tự phải vận hành mọi hệ thống |
| **SOC / Security IR** | Phân tích indicators, compromise hypotheses, chứng cứ và phạm vi | Không chặn mạng production khi chưa đúng quy trình quyền |
| **NOC / Network engineer** | Routing, firewall, DNS, traffic paths, ACL và capacity | Phải biết business dependencies/rollback |
| **SRE / Infrastructure** | Service health, rollback, backups, failover, availability | Không xóa evidence vì muốn phục hồi nhanh |
| **IAM / Endpoint** | Credential revoke, device isolation, EDR và session controls | Cần tránh khóa chính account break-glass |
| **Cloud / Kubernetes platform** | VPC/SG/NSG, CNI/Pods, managed services | Cloud provider boundaries và shared responsibility |
| **Application owner** | User impact, backend AuthZ, business validation và data evidence | Không tự kết luận mọi 403 là firewall deny |
| **Legal / Privacy / Compliance** | Data breach assessment, retention, obligations và approval | Không cung cấp lời khuyên pháp lý trong bài này |
| **Communications owner** | Thông báo nội bộ/khách hàng/đối tác theo phê duyệt | Không suy đoán quy mô ảnh hưởng khi chưa kiểm chứng |

Với một sự cố nhỏ, một người có thể kiêm nhiều vai trò; với P1/SEV1 nên phân rõ **IC, technical leads, evidence custodian và người cập nhật stakeholders**.

### 4.5. Runbooks, quyền khẩn cấp và out-of-band

- Chuẩn bị **read-only access** tới những telemetry quan trọng.
- Có **break-glass access** giới hạn, được giám sát, dùng được khi IdP/VPN/PEP chính bị lỗi.
- Bảo vệ **backup config của firewall/router/cloud IaC** và lưu phiên bản triển khai.
- Lập danh sách on-call, vendor/provider escalation và kênh liên lạc dự phòng.
- Tạo test data/PCAP lab để kiểm tra parser và huấn luyện, không cần truy cập payload production.
- Thử những thay đổi cô lập thường gặp trên staging/lab trước khi phải dùng trong lúc khẩn cấp.

**Một break-glass route không được biến thành bypass không hạn chế thường trực.** Cần approval, TTL, audit, scope và quy trình đóng ngoại lệ.

## 5. Giai đoạn 1 — Detection: nhận diện tín hiệu bất thường

Kênh phát hiện có thể là alert, người dùng báo lỗi, SRE nhận SLO breach, threat intelligence, DNS anomalies, EDR, cloud posture hoặc network device syslog.

### 5.1. Network signals hữu ích

| Dấu hiệu | Có thể liên quan | Cần đối chiếu |
|---|---|---|
| SYN rate tăng, nhiều source IP | DDoS/SYN flood hoặc flash crowd | Capacity, traffic legitimacy, SYN-ACK ratio, edge telemetry |
| Egress tới destination chưa từng thấy | C2, telemetry mới, SaaS update | Asset owner, app deploy, process identity |
| Lượng DNS TXT/long labels tăng | Tunneling, misconfig, service discovery | DNS resolver, expected domain/protocol, authorized workloads |
| Nhiều new east–west connections | Scan/lateral movement hoặc health discovery | Change tickets, endpoint processes, auth logs |
| VPN logins ở vị trí/thời điểm bất thường | Credential misuse hoặc employee travel | MFA/IdP, device binding, actual access sessions |
| TLS handshake failures tăng | CA/certificate issues, client misconfig, probe abuse | Expiry, trust chain, SNI, app release |
| BGP route flaps/next hop thay đổi | Route leak, upstream failure, config change | RIB/FIB, change logs, provider notice |
| Packet loss/choke ở interface | DDoS, capacity, NIC/optic/hardware failure | Interface counters, traffic composition, physical health |
| Firewall rule mới mở rộng | Misconfiguration hoặc malicious change | Cloud audit, actor, approval, policy diff |
| Sudden absence of telemetry | Sensor outage/tampering hoặc network failure | Heartbeat, pipeline health, separate signal |

### 5.2. Detection rule khác nguyên nhân gốc

Ví dụ `high DNS NXDOMAIN rate` có thể do:

- Malware domain generation algorithm.
- Misconfigured service đang retry query sai.
- Split-horizon DNS record thiếu sau thay đổi.
- Telemetry/agent mới sinh tên thử nghiệm.
- Một sự cố resolver upstream.

**Alert chỉ gợi ý hướng điều tra**, không phải kết luận. Cần tách **observation**, **hypothesis**, **supporting evidence** và **contradicting evidence**.

## 6. Giai đoạn 2 — Triage và declaration

Triage quyết định **có sự cố nào cần kích hoạt**, ưu tiên phản ứng, người phụ trách, những gì đã biết và những gì còn chưa biết.

### 6.1. Hồ sơ sự cố ban đầu

~~~yaml
# Ví dụ dữ liệu ghi nhận trong ticket; không phải schema của SIEM vendor.
incidentId: "NET-IR-EXAMPLE-001"
title: "API latency và new outbound connections bất thường"
firstObservedUtc: "2026-11-28T03:15:00Z"
declaredUtc: "2026-11-28T03:25:00Z"
classification: "suspected-security-incident"
severity: "SEV2-provisional"
confidence: "medium"
affectedAssets:
  - "orders-api (lab inventory ID)"
  - "egress gateway (lab inventory ID)"
customerImpact: "Đang xác minh"
incidentCommander: "assigned-by-oncall-roster"
technicalLead: "assigned-by-incident-commander"
evidenceCustodian: "assigned-by-security-team"
communicationsOwner: "assigned-by-incident-commander"
currentDecision: "investigate-and-protect-availability"
nextReviewUtc: "2026-11-28T03:40:00Z"
~~~

Đây là **mẫu minh họa**, không phải một vụ thật. Sự nghiêm trọng SEV2 chỉ mang tính ví dụ; **thang severity phải do tổ chức quy định**.

### 6.2. Severity, impact và confidence là ba trục khác nhau

| Trục | Câu hỏi | Ví dụ |
|---|---|---|
| **Severity / priority** | Phản ứng nhanh, escalation ở mức nào? | Hệ thống thanh toán không phục vụ → ưu tiên cao |
| **Impact / scope** | Bao nhiêu user, host, subnet, region, tenant và dữ liệu? | 1 namespace khác với toàn cloud account |
| **Confidence** | Bằng chứng hỗ trợ giả thuyết mạnh đến đâu? | Chỉ một IDS alert khác với kết hợp EDR + flow + audit |

Có thể cần SEV1 **dù confidence ban đầu thấp** nếu dịch vụ quan trọng bị gián đoạn nghiêm trọng. Ngược lại, một alert rất chắc chắn về hành vi scan trong lab được phê duyệt có thể không là incident nghiêm trọng.

### 6.3. Những câu hỏi trong 15 phút đầu (định hướng, không phải deadline bắt buộc)

1. Dịch vụ nào **hiện đang không đạt SLO** hoặc ảnh hưởng safety?
2. Có dấu hiệu **đang exfiltrate hoặc lan rộng** không?
3. Nguồn nào báo đầu tiên, thời điểm nào và đồng hồ có đồng bộ không?
4. Có **change/deploy/network maintenance** nào gần đây?
5. Những subnet/identities/hosts nào là **confirmed**, **suspected**, **not yet assessed**?
6. Có thể dùng một hành động nhỏ, hoàn tác được để **giảm thiệt hại ngay** không?
7. Ai ra quyết định cô lập và ai có quyền thực thi?
8. Việc thu evidence có làm lộ PII/credential hoặc tăng sự cố không?
9. Cần báo cho nhóm data/privacy/legal ngay không, hay chỉ ghi nhận khả năng?
10. Thời điểm cập nhật tiếp theo là khi nào?

### 6.4. Ghi nhận uncertainty

Một bản tóm tắt hữu ích có thể là:

> **Đã quan sát:** new outbound TCP connections từ API Pod A tới IP chưa nằm trong dependency inventory. **Chưa xác minh:** hoạt động này là C2 hay telemetry do phiên bản mới. **Ảnh hưởng:** latency p95 tăng; chưa có bằng chứng exfiltration. **Hành động:** cô lập đường egress đích cụ thể sau review, thu flow/EDR/app logs; kiểm tra business dependency và rollback.

Đừng viết “attacker đã lấy dữ liệu” khi chỉ biết có kết nối tới một IP lạ. Cũng đừng vì chưa chắc chắn mà trì hoãn mọi containment trong tình huống rủi ro lan rộng cao; hãy ghi **rationale và độ bất định**.

## 7. Giai đoạn 2 mở rộng — Scoping và phân tích giả thuyết

Một incident thường có **nhiều giả thuyết cạnh tranh**. Ví dụ Orders API mất database connection:

| Giả thuyết | Evidence ủng hộ | Evidence bác bỏ/cần có |
|---|---|---|
| Firewall policy vừa đổi chặn TCP/5432 | Rule diff, denies cùng thời điểm | DB firewall không có deny, SYN/ACK tới được |
| DNS trả sai IP | NXDOMAIN, DNS answer khác | Resolver/app vẫn resolve đúng Pod/DB endpoint |
| Route/NAT lỗi | Asymmetric paths, NAT exhaustion, route flaps | Packets tới hai chiều ổn định |
| TLS certificate/trust lỗi | Handshake alerts, certificate expiry | TCP và TLS handshake thành công |
| DB quá tải | Connection pool exhaustion, queueing | DB healthy, connect từ nguồn đối chứng thành công |
| Workload bị compromise | Process lạ, identity misuse, egress chưa biết | Change ticket xác nhận legitimate new client |
| DDoS hoặc external load spike | Ingress rate tăng, edge drops | Traffic vẫn trong bình thường tại app edge |

### 7.1. Evidence graph

~~~mermaid
flowchart TD
    ALERT["Alert: API timeouts"] --> H1["H1: network policy change"]
    ALERT --> H2["H2: DNS / routing error"]
    ALERT --> H3["H3: malicious outbound traffic"]
    LOG["Firewall & cloud audit logs"] --> H1
    DNS["Resolver logs & answer timeline"] --> H2
    EDR["Endpoint/process + CNI flow verdict"] --> H3
    H1 --> TEST["Test controlled hypothesis"]
    H2 --> TEST
    H3 --> TEST
    TEST --> DEC["Scoped containment / fix decision"]
~~~

**Một log không đủ đại diện toàn mạng.** Cần biết mỗi sensor nhìn gì và không nhìn gì. Ví dụ DNS resolver log không thấy DoH đi trực tiếp tới public endpoint; PCAP ở node NIC có thể chỉ thấy VXLAN outer UDP; firewall phía sau SNAT có thể không biết source Pod ban đầu.

### 7.2. Tạo timeline tối thiểu

Ghi:

~~~text
T-20m: change approved cho cloud route table
T-10m: DNS error rate tăng ở một region
T0:    customer-facing request errors vượt SLO
T+3m:  SOC nhận network anomaly alert
T+7m:  NOC xác nhận một route khác expected topology
T+10m: IC mở incident và giao owner
T+14m: reversible mitigation, kiểm tra health

Minh họa giả định, không phải thời gian chuẩn.
Mỗi event cần nguồn evidence, timestamp, uncertainty.
~~~

Không tính “Time to Detect” từ thời điểm kẻ tấn công **thật sự bắt đầu** nếu chưa xác định được mốc đó; có thể báo riêng **first known activity**, **first alert** và **detection/acknowledgement time**.

## 8. Điều phối và truyền thông ngay trong lúc phân tích

Khi incident đang diễn ra, thông tin không thống nhất gây lỗi thao tác giống như network misconfiguration.

### 8.1. Kênh thông tin và nhịp cập nhật

- Một **incident channel/ticket** có mã sự cố và ownership rõ.
- Tách **technical working notes** khỏi **status cho stakeholder**.
- Ghi ai đang thay firewall/router/DNS/IAM, thời điểm, change ID và rollback conditions.
- Chốt **mốc cập nhật kế tiếp** theo severity; không biến thời điểm minh họa thành SLA chung.
- Có người duyệt thông báo khách hàng/đối tác và nội dung privacy/legal khi liên quan.
- Giữ bản tóm tắt **facts, impact, current mitigation, next decision, uncertainties**.

### 8.2. Mẫu cập nhật ngắn

~~~text
Incident: NET-IR-EXAMPLE-001
Status: Investigating / Mitigating
User impact: API requests tại region A bị timeout tăng cao
Confirmed: TLS gateway healthy; egress flows từ API tới DB thay đổi
Not yet confirmed: route change hay malicious activity
Mitigation: rollback network route đang được peer review
Risk: rollback có thể ảnh hưởng backup traffic
Next update: theo nhịp được IC xác nhận
Evidence owner: SOC analyst; change owner: NOC lead
~~~

Không đưa raw tokens, mật khẩu, private keys, địa chỉ quản trị nhạy cảm hoặc toàn bộ PCAP vào kênh có người không cần xem.

## 9. Evidence collection: đủ chứng cứ, đúng quyền và đúng thời điểm

Điều tra sự cố mạng thường kết hợp **metadata, logs, config state, identity state và khi cần packet capture**. Nên ưu tiên cách thu thập ít can thiệp nhất mà vẫn đủ trả lời câu hỏi.

### 9.1. Thứ tự ưu tiên bằng chứng theo mục tiêu

| Câu hỏi | Nguồn ưu tiên | Khi nào cần bổ sung |
|---|---|---|
| Ai thay firewall/route? | Cloud/network audit, versioned IaC diff, change ticket | Config snapshot, approval & actor review |
| Gói có bị chặn ở network boundary? | Firewall/SG/CNI flow verdict, interface counters | Bounded PCAP ở điểm trước/sau boundary |
| DNS trả đích nào lúc lỗi? | Resolver query/answer logs, authoritative config | PCAP DNS trong scope nếu logs thiếu |
| User nào đăng nhập VPN/ZTNA? | IdP, VPN/ZTNA session logs, MFA/PEP decision | Host/device logs nếu nghi session hijack |
| Data có rời hệ thống? | Proxy/egress logs, app/DB audit, DLP events | PCAP có phê duyệt và evidence privacy controls |
| TLS bị lỗi ở hop nào? | Proxy/app TLS logs, certificate metadata | Short bounded handshake capture nếu cần |
| Có lateral movement? | EDR process/network context, east–west flows, identity logs | Host forensics và selected network capture |
| DDoS từ đâu, tác động gì? | Edge/WAF/LB traffic counters, provider logs, app SLO | Flow sampling/PCAP headers tại edge được phê duyệt |

**Đừng chỉ lấy packet capture làm “nguồn sự thật tuyệt đối”.** PCAP tại một vị trí có thể không thấy đường ngược, NAT trước/sau, overlay inner packets hoặc data drop ở sensor; payload TLS có thể mã hóa.

### 9.2. Evidence matrix

~~~yaml
# Mẫu tracking nội bộ cho một chứng cứ, không phải schema pháp lý.
evidenceId: "NET-IR-EXAMPLE-001-E07"
incidentId: "NET-IR-EXAMPLE-001"
source: "cloud-firewall-audit"
sourceOwner: "network-platform"
observedTimeUtc: "2026-11-28T03:17:12Z"
collectedTimeUtc: "2026-11-28T03:31:02Z"
collector: "authorized-analyst-id"
collectionMethod: "approved-read-only-export"
originalFormat: "JSON"
storageLocation: "restricted-evidence-vault"
integrityDigest: "SHA-256 recorded in evidence register"
timeOffsetKnown: "documented-separately"
sensitivity: "internal-confidential"
scopeCaveat: "logs only this firewall resource; not all network paths"
custodian: "security-ir-lead"
~~~

Chỉ là dữ liệu minh họa. Một digest thật phải chứa **giá trị hash tính từ bytes gốc**; dòng “SHA-256 recorded…” không phải hash có thể xác minh.

### 9.3. Chain of custody và bảo vệ dữ liệu

- Ghi **ai thu, từ đâu, lúc nào, bằng cách nào**, đã dùng tool/version nào.
- Giữ **file gốc bất biến theo chính sách**, phân tích trên bản sao được kiểm soát.
- Tạo **cryptographic digest** cho từng artifact có thể hash và xác minh khi chuyển giao.
- Dùng kho evidence có RBAC, encryption, retention và access audit.
- Với logs có thể thay đổi do rolling retention, cần ưu tiên **export được phê duyệt** trước khi chúng bị xóa.
- Tách **sự thật quan sát** khỏi phần **diễn giải** trong báo cáo.
- Khi có yêu cầu legal hold, không tự xóa log/PCAP hoặc thay thời gian lưu.

**Không tự ý sao chép ổ đĩa, memory, payload mạng của người khác, hay credential của tài khoản khác** chỉ vì có một alert; việc thu thập nhạy cảm cần scope và quyền cụ thể, và có thể cần các nhóm pháp lý/privacy liên quan.

### 9.4. Packet capture trong IR: có giới hạn và biết điểm mù

Một PCAP ngắn có thể giúp xác định SYN/SYN-ACK, RST, TCP retransmissions, ICMP Packet Too Big, DNS resolution hoặc TLS handshake metadata.

Nhưng:

- Filter `tcp port 443` không bao phủ DNS/ICMP/UDP QUIC.
- Filter `src host client and tcp dst port 443` có thể bỏ **toàn bộ chiều trả về**.
- Snaplen nhỏ **không bảo đảm khử dữ liệu cá nhân**, trong khi snaplen quá ngắn làm thiếu headers.
- NAT, VLAN, IPv6, VXLAN/Geneve, IPsec, NIC offload và SPAN drops có thể làm packet trông khác trên wire.
- Full payload có thể chứa bearer tokens, nội dung người dùng và secrets của protocol chưa mã hóa.
- Một “PCAP rỗng” không chứng minh không có traffic.

Mọi live capture phải có **authorization, interface/vantage point, filter, time/count/file-size caps, disk quota, storage ACL và kế hoạch xóa**. Trong nhiều tình huống, flow/EDR/app logs an toàn hơn và đủ làm evidence.

### 9.5. Lệnh read-only giúp ghi nhận hiện trạng

Các lệnh sau chỉ nên dùng **trên hệ thống/lab được phép** và bằng quyền đã cấp. Chúng **không sửa firewall/route/Kubernetes policy**. Nội dung IP, process, user/namespace trong output vẫn có thể nhạy cảm; không gửi nguyên văn ra nơi công khai.

~~~bash
# Linux: đọc địa chỉ, route và network interfaces.
ip -br address
ip -4 route show
ip -6 route show
ip -s link show

# Đọc các socket, trạng thái TCP và tiến trình nếu có đủ quyền.
ss -tan

# Xem thông tin DNS do systemd-resolved cung cấp, nếu có.
resolvectl status

# Quan sát NTP/time sync state nếu host có timedatectl.
timedatectl status
~~~

Ở Windows PowerShell:

~~~powershell
# Chỉ đọc cấu hình mạng và các kết nối đang tồn tại.
Get-NetIPConfiguration
Get-DnsClientServerAddress
Get-NetRoute | Select-Object DestinationPrefix, NextHop, InterfaceAlias, RouteMetric
Get-NetTCPConnection | Select-Object LocalAddress, LocalPort, RemoteAddress, RemotePort, State
Get-Date -Format o
~~~

Trên Kubernetes:

~~~bash
# Đảm bảo đang quan sát đúng cluster và namespace.
kubectl config current-context
kubectl get pods -n orders -o wide
kubectl get services -n orders
kubectl get endpointslices -n orders
kubectl get networkpolicy -n orders

# Chỉ đọc labels/placement và trạng thái thay đổi gần đây.
kubectl get pods -n orders --show-labels
kubectl get events -n orders --sort-by=.lastTimestamp
~~~

**Các lệnh đọc không chứng minh hệ thống an toàn**; một kube-apiserver hiển thị NetworkPolicy không bảo đảm CNI đã enforce datapath. Cũng không bật `kubectl debug`, `pods/exec`, privileged containers hoặc thay routes chỉ để thu log khi chưa có approval.

### 9.6. Vì sao không in secrets để debug?

Trong điều tra network access, có thể chỉ cần trạng thái chứng chỉ, issuer, expiry hoặc auth deny reason. Không nên:

- Export plaintext VPN credentials, IdP tokens, Kubernetes Secrets hoặc TLS private keys vào ticket.
- Dump HTTP Authorization headers/cookies của toàn bộ traffic.
- Chụp memory ứng dụng production không có incident authority rõ.
- Dùng `curl -k`, `--insecure` hoặc tắt certificate verification để “chứng minh connectivity”.

Nếu cần forensic secrets, sử dụng quy trình xử lý riêng với phạm vi, custody và hạn chế người xem; không đưa dữ liệu này vào bản báo cáo diễn giải phổ thông.

## 10. Quyết định Containment: giảm thiệt hại mà không tạo sự cố lớn hơn

**Containment** là hành động **giảm khả năng tấn công lan rộng hoặc giảm tác động đang xảy ra** khi chưa nhất thiết xử lý xong nguyên nhân.

Ví dụ:

- Cô lập endpoint bị nghi compromise khỏi production network nhưng giữ kênh forensic/quản trị được phê duyệt.
- Chặn một luồng **egress đáng ngờ** theo destination IP/port/protocol và source cụ thể.
- Hạn chế lateral movement bằng segmentation, CNI NetworkPolicy hoặc firewall rule hẹp.
- Thu hồi phiên VPN/ZTNA hoặc service account credential bị nghi lạm dụng.
- Kích hoạt DDoS mitigation/rate limiting hoặc chuyển traffic qua scrubbing service theo hợp đồng.
- Tạm dừng một route/peering sai và quay về config version ổn định.
- Disable một compromised admin account theo phối hợp IAM khi có bằng chứng/quy trình phù hợp.

**Containment không đồng nghĩa “rút cáp toàn bộ”.** Hành động sai scope có thể cắt DNS, identity, payment, backup, egress cần thiết hoặc đường cứu hộ của chính nhóm IR.

### 10.1. Ma trận lựa chọn hành động

| Đối tượng / điều kiện | Hành động có thể cân nhắc | Rủi ro phụ | Tiêu chí hoàn tác |
|---|---|---|---|
| Một laptop nghi malware | EDR network isolation; chỉ giữ quản trị cần thiết | Cắt telemetry/pháp chứng nếu làm sai | Host sạch, identity được rotate, owner xác nhận |
| Một source IP gây traffic xấu | Block/rate-limit tại edge nếu có bằng chứng | NAT/shared IP có thể chặn user tốt | Traffic analysis và impact check |
| Một destination C2 nghi vấn | Egress deny từ workload cụ thể | Shared CDN/IP có thể chứa dịch vụ hợp lệ | Xác minh dependency và remediation |
| DDoS vào public endpoint | WAF rules, CDN/rate limit, scrubbing | False positives, hỏng API clients | Edge traffic/SLO trở lại bình thường |
| Lateral movement trong một subnet | Microsegmentation theo host/tag/port | Gián đoạn discovery/backup/admin | Positive business flows pass và negative test vẫn deny |
| Firewall rule mở quá rộng | Rollback rule/ACL về phiên bản được phê duyệt | Có thể tác động deployment vừa đổi | Peer review, health probes, audit |
| VPN/ZTNA session compromise | Revoke session và credential; step-up khi cần | Người dùng hợp lệ bị gián đoạn | Credential sạch, access policy được test |
| Cloud public endpoint vừa bị mở | Restrict ingress/SG và origin, xử lý IAM change | Cắt monitoring hoặc partner integration | Chủ dịch vụ xác nhận và exposure test |
| Kubernetes Pod bị chiếm | Quarantine network flows/scale control theo runbook | Pod reschedule, mất volatile evidence | Clean image/secrets và new-flow tests |
| Route hijack/leak nghi vấn | Provider/network escalation, route policy rollback | Traffic blackhole hoặc route flap | Routing convergence được đo và sign-off |

**Đây là các lựa chọn**, không phải lệnh thực hiện ngay. Mọi containment cần dựa vào quyền, hệ thống cụ thể và rủi ro business/safety.

### 10.2. Thang tác động containment

~~~mermaid
flowchart TD
    ALERT["Threat/impact ongoing"] --> URG{"Rủi ro mất dữ liệu hoặc lan rộng cao?"}
    URG -->|"Có"| FAST["Cô lập khẩn theo delegated authority"]
    URG -->|"Chưa xác định"| SELECT["Collect limited evidence + approve scoped control"]
    FAST --> CHECK["Xác minh blast radius và monitoring"]
    SELECT --> CHECK
    CHECK --> GOOD{"Giảm rủi ro mà critical flows vẫn hoạt động?"}
    GOOD -->|"Không"| ROLL["Rollback/adjust có kiểm soát và escalate"]
    GOOD -->|"Có"| STABLE["Duy trì containment có TTL/owner"]
    STABLE --> ROOT["Điều tra và xử lý root cause"]
    ROLL --> SELECT
~~~

Trong tình huống nguy hiểm cho an toàn con người hoặc khả năng kiểm soát critical infrastructure, cần theo **safety runbook và delegated incident authority**; có thể phải containment ngay trước khi thu đầy đủ evidence. Ngược lại, tắt host có thể làm mất volatile state; nếu còn thời gian và an toàn, forensic owner cần quyết định **collect-before-isolate** hay **isolate-first**.

### 10.3. Chọn deny scope: đừng chỉ nhìn IP

- Một IP public có thể là **shared egress NAT** của nhiều khách hàng hoặc một CDN host.
- Source IP quan sát **sau SNAT** có thể đại diện nhiều Pods hoặc tenant khác nhau.
- IPv6/alternate DNS record có thể tạo đường khác với IPv4.
- Chặn FQDN bằng DNS alone có thể không chặn direct IP/DoH/custom resolver.
- Một deny mới có thể bị **allow policy khác** ghi hiệu lực theo semantics của firewall/CNI đang dùng.
- Trong Kubernetes NetworkPolicy chuẩn, policies **cộng dồn allow**; không có explicit deny chuẩn để áp như ACL có priority.
- Khi service mesh tham gia, cần đánh giá proxy/waypoint/egress gateway và workload identity để không chặn nhầm kênh.

Tốt hơn là ghi: **source identity/workload, destination, protocol/port, enforcement point, lifetime, owner, expected denies và business flows phải giữ**.

### 10.4. Emergency change record

~~~yaml
# Template cho change approval/tracking, KHÔNG phải cloud firewall schema.
changeId: "NET-IR-EXAMPLE-001-C03"
incidentId: "NET-IR-EXAMPLE-001"
reason: "Suspected unauthorized egress from one API workload"
control: "temporarily-deny-specified-egress-flow"
scope:
  source: "orders-api-workload-identity"
  destination: "approved-investigation-indicator"
  protocol: "TCP"
  port: 443
owner: "network-incident-lead"
approver: "delegated-incident-commander"
rollbackArtifact: "versioned-policy-before-change"
expectedProtectedFlows:
  - "orders-api to database TCP/5432"
  - "orders-api to approved DNS resolver"
expiry: "reviewed-incident-temporary-window"
validation:
  positiveControl: "business critical flow stays healthy"
  negativeControl: "specific suspect egress flow is denied"
~~~

Các giá trị ở trên mang tính minh họa. **Không copy YAML này vào production**; trước khi thực thi phải dùng syntax của firewall/CNI/provider thực và điền giá trị đã phê duyệt.

### 10.5. Một control có thể giảm tấn công nhưng làm mất visibility

Ví dụ cô lập host khỏi mọi network có thể ngăn exfiltration, nhưng cũng cắt EDR telemetry, forensic transfer, time sync và remote access để điều tra. Đội IR cần **quarantine zone** hoặc out-of-band channel được thiết kế trước; không tùy tiện mở lại Internet cho host chỉ vì khó thu log.

## 11. Giai đoạn 3 — Eradication: loại bỏ nguyên nhân và foothold

Sau khi đã giảm tác động, đội ứng phó cần xác định và xử lý **nguyên nhân gốc hoặc điều kiện giúp sự cố xảy ra**:

| Root cause / góp phần | Eradication cần cân nhắc | Bằng chứng xác minh |
|---|---|---|
| Credential/session bị lộ | Revoke tokens, rotate keys, khóa tài khoản bị compromise, review quyền | Identity/session logs, controlled reauth tests |
| Server hoặc container bị malware | Forensic review, rebuild từ image đáng tin, vá lỗ hổng, thay secrets | EDR, image integrity, clean deployment evidence |
| Firewall/ACL sai | Sửa IaC/rule có peer review, đóng đường public hoặc broad allow | Effective rule, negative/positive network tests |
| DNS bị chỉnh trái phép | Khôi phục authoritative records/config, sửa quyền update, điều tra resolver cache | DNS answers từ nhiều vantage points, audit diff |
| BGP/route policy sai | Rollback route/filter, phối hợp upstream/provider | RIB/FIB convergence, BGP monitoring, service reachability |
| VPN/remote access cấu hình quá rộng | Giới hạn groups/routes, kiểm tra MFA/device posture | VPN session/can-i-access tests và ACL evidence |
| App/API authorization thiếu | Sửa code, enforce object/tenant AuthZ, kiểm tra dữ liệu bị ảnh hưởng | App tests, audit trail và data access report |
| Cloud/Kubernetes policy drift | Khôi phục desired state, sửa quyền IaC/control-plane, audit actor | Versioned policy, control plane audit, flow verdict |
| Unpatched edge appliance | Vendor-guided patch/replacement và review compromise | Firmware/integrity evidence, post-patch tests |
| DDoS ongoing | Mitigation scaling/scrubbing, origin protection và tuning | Edge telemetry, protected service SLO |

**Containment tạm thời không phải eradication.** Chặn một IP nghi C2 không giải quyết được process độc hại còn nằm trong host; remove một malware binary có thể không giải quyết credential mà attacker đã lấy; rollback firewall có thể chưa khắc phục được nguyên nhân permission escalation.

### 11.1. Root cause và contributing factors

Một phân tích tốt tách:

- **Direct technical cause:** ví dụ route table mới gửi backend traffic qua đường sai.
- **Trigger:** deploy/maintenance/compromise event dẫn đến biểu hiện.
- **Contributing factors:** policy review thiếu, telemetry không bao phủ IPv6, credential TTL quá dài.
- **Detection gap:** warning tồn tại từ trước nhưng không được route đến đúng on-call.
- **Recovery gap:** backup config cũ, thiếu canary, runbook không có rollback.

Không ép mọi incident phải có duy nhất một nguyên nhân; các sự cố phức tạp thường là **chuỗi yếu tố**, và những yếu tố về quy trình/hệ thống cũng quan trọng.

### 11.2. Quyết định rebuild hay “clean in place”

Với host nghi compromise ở mức cao, không mặc định **xóa một process rồi tái sử dụng ngay** là sạch. Có thể cần:

1. Đánh giá mức tin cậy của hệ điều hành/runtime, credential stores và filesystem.
2. Lưu những chứng cứ cần thiết theo quy trình trước khi rebuild.
3. Reprovision từ nguồn đáng tin, bảo đảm image/version/config integrity.
4. Rotate credentials có thể đã bị lộ và chặn đường tấn công ban đầu.
5. Test network reachability/AuthZ mới trước khi đưa trở lại production.

Việc rebuild không tự chứng minh không có data loss hoặc credential replay nơi khác. Cần scoping những systems đã được tài khoản/host đó truy cập.

## 12. Giai đoạn 4 — Recovery: khôi phục dịch vụ và kiểm tra an ninh

**Recovery** đưa dịch vụ trở lại trạng thái hoạt động được phê duyệt, **không tái mở lỗ hổng**.

### 12.1. Hai nhóm tiêu chí phải đồng thời đạt

| Nhóm | Tiêu chí minh họa |
|---|---|
| **Business/SRE** | HTTP success, p95/p99 latency, error budget, throughput, data correctness, queue backlog |
| **Network** | Reachability hợp lệ, routing/DNS đúng, firewall/CNI effective policies, drops bình thường |
| **Identity** | Compromised sessions bị thu hồi; legitimate accounts access đúng; MFA/PKI hoạt động |
| **Security** | Indicators không còn hoạt động, source ngoài quyền vẫn bị deny, forensic evidence được giữ |
| **Data** | DB consistency/restore checks, data access impact được đánh giá, không tự khẳng định chưa có exfiltration |
| **Operations** | Rollback path, monitoring tăng cường, owner on-call và incident command rõ |

Một load balancer báo backend healthy chưa đủ nếu toàn bộ traffic đang bị chặn ở DNS hoặc auth; một `curl 200` từ máy admin cũng không chứng minh tenants/regions khác hoạt động.

### 12.2. Phục hồi theo làn sóng

~~~mermaid
flowchart TD
    FIX["Root cause / foothold đã xử lý"] --> PRECHECK["Verify clean config, identity, evidence retained"]
    PRECHECK --> CANARY["Canary: một workload / region / client cohort"]
    CANARY --> TEST{"Business positive + security negative tests PASS?"}
    TEST -->|"Không"| BACK["Stop rollout, reassess / rollback / contain"]
    TEST -->|"Có"| RAMP["Mở rộng từng vùng / tier"]
    RAMP --> MON["Enhanced monitoring + session/flow audits"]
    MON --> EXIT{"Exit criteria và owner sign-off?"}
    EXIT -->|"Chưa"| TEST
    EXIT -->|"Đạt"| POST["Transition to post-incident follow-up"]
~~~

### 12.3. Positive/negative tests quan trọng như nhau

Ví dụ sau containment lateral movement:

- **Positive:** Orders API vẫn kết nối DB TCP/5432 theo đường/identity đã cấp.
- **Negative:** Pod ngoài nhóm trusted vẫn **không** kết nối được DB/5432.
- **Positive:** DNS resolution qua approved resolver còn hoạt động.
- **Negative:** direct public origin hoặc egress tới indicator bị chặn.
- **Positive:** tài khoản hợp lệ đăng nhập VPN/ZTNA đúng app.
- **Negative:** tài khoản bị revoke không tạo/giữ phiên trái policy.

Một test thất bại cần **điểm đối chứng**: khi DB chưa khởi động, timeout từ Pod không được phép không chứng minh firewall chặn. Tìm **verdict và evidence tại enforcement point**, không chỉ suy từ response.

### 12.4. Kết thúc mitigation tạm như thế nào?

Không để emergency rules tồn tại vô hạn:

1. Xác định **owner, expiry, lý do** của mỗi exception/quarantine.
2. Xem xét có phải chuyển thành **permanent baseline policy** hay rollback.
3. Kiểm thử **traffic bình thường và traffic phải deny** trước/sau khi gỡ.
4. Ghi effective policy/config version và monitoring window sau đổi.
5. Review những changed routes/DNS/SG/ACL mà sự cố đã để lại.

Chỉ tuyên bố “resolved” khi incident command chấp thuận **service health, risk level và monitoring**; tài liệu này không đặt một thời gian cố định thay tổ chức.

## 13. Giai đoạn 5 — Lessons learned và cải tiến liên tục

Post-incident review không chỉ là kể lại “ai đã thao tác gì”; nó là phương pháp tìm **điểm mà hệ thống/kiểm soát thất bại hoặc thiếu khả năng quan sát**.

### 13.1. Nội dung post-incident review

- **Executive summary:** impact, thời gian, mức độ nghiêm trọng, xác định có data/security compromise không.
- **Timeline:** event time, detect time, declare time, contain time, recovery time, uncertainty.
- **Evidence:** nguồn dữ liệu, confidence, gaps, dữ liệu cần giữ theo retention.
- **What worked:** signals và containment giúp giảm thiệt hại.
- **What didn't:** alert noise, thiếu owner, change control, runbook sai, network path chưa inventory.
- **Root cause/contributing factors:** phân tích kỹ thuật và quy trình không quy chụp cá nhân.
- **Security/privacy assessment:** dữ liệu/tenant bị ảnh hưởng, báo cáo theo legal/privacy policy.
- **Corrective actions:** owner, deadline, test, acceptance criteria và phương pháp xác minh.
- **Follow-up metrics:** detection quality, time-to-contain, recurrence, effectiveness của rule.

### 13.2. Action item phải kiểm chứng được

| Action item quá chung | Action item có thể kiểm chứng |
|---|---|
| “Tăng monitoring” | Bổ sung alert cloud SG mở public ingress cho prod DB; thử negative test và route tới on-call |
| “Sửa firewall” | Version hóa rule allow API→DB, xóa broad CIDR, có test từ trusted và untrusted source |
| “Cải thiện ứng phó” | Diễn tập containment + rollback trong staging và cập nhật owner/approval |
| “Giảm thời gian phát hiện” | Đo first known suspicious activity → detection → acknowledgement, rồi tune signal |
| “Bảo vệ chứng cứ” | Bật kho evidence restricted, encryption, audit download và retention tự động |

**Đóng incident** không có nghĩa **đóng luôn mọi corrective action**. Các vấn đề dài hạn cần người phụ trách theo dõi đến khi validation pass.

### 13.3. Đừng biến postmortem thành truy cứu lỗi cá nhân

Một config change có thể là trigger, nhưng vì sao nó đi được tới production? Có thiếu peer review, safe rollout, topology diagram, canary, policy testing, dependency inventory hay monitoring? Tập trung **cơ chế phòng ngừa và phản hồi**; đánh giá trách nhiệm cụ thể theo quy định tổ chức, tránh suy diễn khi chưa có bằng chứng.

## 14. Lưu ý về “lifecycle”: rẽ nhánh theo mức nguy cấp

Không nhất thiết phải có một trình tự cố định “thu xong mọi chứng cứ rồi mới chặn”. Một sơ đồ quyết định tốt có nhánh:

~~~mermaid
flowchart TD
    OBS["Sự kiện bất thường"] --> TRI{"Impact / active threat / safety?"}
    TRI -->|"Nguy cơ khẩn cấp"| CON["Contain trong phạm vi delegated authority"]
    TRI -->|"Cần xác minh"| ANA["Thu evidence ít can thiệp + triage"]
    ANA --> DEC{"Có dấu hiệu incident đủ để kích hoạt?"}
    DEC -->|"Không"| CLOSE["Ghi event / theo dõi / tune detector"]
    DEC -->|"Có"| CON
    CON --> ANA2["Mở rộng điều tra và lưu evidence"]
    ANA2 --> ROOT["Fix root cause/credentials/config"]
    ROOT --> REC["Canary recovery + security tests"]
    REC --> REV{"Tái phát/đường mới?"}
    REV -->|"Có"| CON
    REV -->|"Không"| LES["Lessons learned, actions, exercises"]
    LES --> PRE["Improve readiness"]
~~~

Nếu rủi ro an toàn con người/OT là yếu tố quyết định, cần phối hợp **safety engineering và incident authority** trước các thao tác mạng; một containment làm mất điều khiển có thể gây hậu quả nghiêm trọng hơn luồng đang nghi vấn.

## 15. Playbook A — DDoS hoặc traffic surge tại public edge

### 15.1. Kịch bản

SLO của API giảm, CPU load balancer và ingress request rate tăng, các cuộc gọi hợp lệ bắt đầu timeout. Có nhiều IP nguồn và một số HTTP paths bị gọi với tần suất lớn.

### 15.2. Những điều phải xác minh

1. **Availability:** user impact thực tế, region/tenant nào, backend SLO và giới hạn bandwidth.
2. **Traffic composition:** L3/L4 packets, SYN/UDP, L7 HTTP requests, source networks, ASN/regions, cache misses và API paths.
3. **Legitimacy:** có chiến dịch marketing/flash crowd, mobile client release hoặc retry storm không?
4. **Edge & origin:** CDN/WAF/load balancer có đang tiếp nhận traffic và **origin có bị bypass** không?
5. **Controls hiện tại:** rate limiting/WAF/scrubbing/challenge/blocklist có đang hoạt động đúng?
6. **Telemetry:** counters, packet loss, request latencies, WAF decisions và backend response rates.

### 15.3. Containment có phạm vi

- Kích hoạt **dịch vụ DDoS mitigation/scrubbing** đã được thiết kế hoặc theo quy trình provider.
- Tune WAF/rate limits cho một endpoint/nhóm requests khi đủ căn cứ; tránh block toàn bộ ASN/region không có phân tích.
- Bảo vệ origin chỉ nhận traffic từ edge được phép, nhất là khi attacker có thể đi trực tiếp origin IP.
- Giảm retry amplification giữa gateway và backend; kiểm tra client retries và idempotency.
- Nếu cần scale, xác minh giới hạn backend/DB, không chỉ tăng edge capacity khiến downstream quá tải hơn.

**Không kết luận chắc là DDoS chỉ từ nhiều request.** Một surge hợp lệ có thể cần capacity scaling chứ không phải chặn khách hàng.

### 15.4. Recovery và bằng chứng

- So request success/latency và response errors trước/sau mitigation.
- Negative test: traffic mô phỏng đúng signature bị chặn ở lab/approved test path.
- Positive test: người dùng thật từ các vùng quan trọng vẫn vào được.
- Theo dõi mitigation expiry và tránh để một emergency rule làm tăng false positive lâu dài.

## 16. Playbook B — Nghi lateral movement giữa các segment

### 16.1. Kịch bản

EDR báo một máy làm việc kết nối bất thường tới nhiều máy chủ nội bộ qua SMB/RDP/SSH. IDS ghi scan-like behavior; NOC thấy east–west flows tăng.

### 16.2. Scoping

Tìm bằng chứng:

| Nguồn | Câu hỏi |
|---|---|
| EDR host/network | Process/user nào tạo kết nối, có dấu hiệu compromise khác? |
| Firewall/CNI flow | Source/destination identities, protocol/port, allow/deny và thời gian |
| IdP/VPN/AD/auth logs | Có failed/successful logins, privilege change hoặc token reuse không? |
| Asset inventory | Những đích nào là management/backup/identity servers quan trọng? |
| Change/scheduled scans | Có vulnerability scanning/asset discovery được phê duyệt không? |

Đừng suy mọi kết nối TCP/445 hoặc SSH đều là lateral movement; backup, domain administration và software distribution cũng có traffic tương tự. Phân tích **process, identity, authorization và thời điểm**.

### 16.3. Containment

- Cô lập **host nguồn nghi vấn** bằng EDR/quarantine network theo quyền đã cấp, giữ kênh điều tra.
- Thu hồi/giới hạn tài khoản và sessions bị nghi compromise theo IAM runbook.
- Thu hẹp east–west ACL theo **source/destination/identity/protocol**.
- Bảo vệ systems nhạy cảm như domain controllers, backup controllers, key stores và management plane.
- Không tạo deny-all toàn VLAN khi chưa đánh giá DNS, monitoring, backup, OT/safety và break-glass dependencies.

### 16.4. Eradication và recovery

- Xác minh host compromise, rebuild/patch khi cần, rotate credentials.
- Review group memberships, RDP/SMB/SSH administration policy, stale allow rules.
- Đưa host trở lại network bằng canary và xác minh **trusted flows work / untrusted flows blocked**.
- Theo dõi khả năng tái xuất hiện new east–west flows trong một cửa sổ hậu kiểm phù hợp.

## 17. Playbook C — DNS anomalies, resolver outage hoặc DNS abuse

### 17.1. Kịch bản

Một ứng dụng không resolve được domain nội bộ hoặc DNS request rate tăng, có nhiều queries với labels dài và bất thường.

**Có ít nhất ba nhóm nguyên nhân cạnh tranh**:

1. DNS infrastructure lỗi: authoritative server, forwarder, cache, split DNS, record/TTL/change sai.
2. Ứng dụng hoặc service discovery misconfiguration: retry loop, broken search domains, deploy sai.
3. Malicious activity: DNS tunneling, domain generation, resolver abuse hoặc poisoning.

### 17.2. Evidence hữu ích

- Resolver response codes: NOERROR, NXDOMAIN, SERVFAIL, timeout.
- Client source identity, query volume, names/types, resolver path và TTL.
- DNSSEC validation status khi hệ thống triển khai và có logging phù hợp.
- Query từ DNS-over-HTTPS/TLS clients có thể **không xuất hiện trên resolver UDP/53**.
- Application DNS cache/OS stub resolver, NodeLocal DNSCache, split-horizon và IPv6 AAAA.
- Recent changes: DNS zone, delegation, resolver config, cloud DNS forwarding, NetworkPolicy egress.

### 17.3. Mitigation theo nguyên nhân

| Nguyên nhân | Giải pháp có thể dùng | Cần đề phòng |
|---|---|---|
| DNS zone/record sai | Rollback authoritative record/TTL theo phê duyệt | Cache còn TTL cũ, application resolver cache |
| Resolver quá tải | Failover/scale đúng kiến trúc | Failover sang resolver không đáng tin |
| Pod thiếu egress DNS | Fix allow rules đúng CoreDNS/NodeLocal path | Không mở `egress: - {}` toàn namespace |
| Suspicious resolver abuse | Rate controls, isolate source, sinkhole theo chính sách | Chặn nhầm legitimate domain hoặc phá evidence |
| NXDOMAIN storm do app | Sửa client config/retry behavior | Đừng coi là C2 nếu chưa có chứng cứ |

**DNS sinkhole** có thể giúp containment/telemetry trong những môi trường được phê duyệt, nhưng có rủi ro đổi semantics, khiến malware/legitimate apps phát hiện đường đi mới hoặc làm gián đoạn tên dùng chung. Không thực hiện tùy tiện trên public DNS/third-party domains.

## 18. Playbook D — Firewall, route, VPN hoặc certificate change gây outage

### 18.1. Kịch bản

Ngay sau khi thay security group hoặc route table, API lỗi ngắt quãng; một nhóm user VPN không vào được admin application. Có thể là lỗi availability do policy change, hoặc một hành động không được phép nhằm mở/chặn kết nối.

### 18.2. Các bước tối thiểu

1. Xác minh change request, actor, approved scope và **version before/after**.
2. Kiểm tra **effective policy** tại tất cả layers: edge firewall, cloud SG, host firewall, CNI, VPN và app proxy.
3. So path từ hai phía: source/destination ở trước và sau NAT, IPv4/IPv6, TLS identity, DNS resolution.
4. Dùng positive control từ source được phép và negative control từ source không được phép.
5. Với route issue, kiểm tra state RIB/FIB, next hops, asymmetric path và provider/upstream maintenance.
6. Với certificate issue, xem issuer/chain/SAN/SNI/expiry, clock skew và trust bundle rotation.
7. Chỉ rollback thay đổi **đã xác định liên quan** sau peer review hoặc emergency authority.

### 18.3. Bảo vệ trong khi rollback

Nếu firewall mới vô tình chặn API, rollback có thể phục hồi nhanh, nhưng đừng rollback sang một rule cũ cho phép **mọi Internet source vào database** nếu đó là cấu hình chưa an toàn. Thay vào đó cân nhắc một rule hẹp có test, hoặc restoration plan được phê duyệt cùng security owner.

**Availability và security có thể xung đột trong vài phút quan trọng.** Ghi quyết định/rationale và kiểm chứng hai phía; không xem “đã có HTTP 200” là điều kiện duy nhất đóng incident.

## 19. Playbook E — Cloud/Kubernetes network incident

### 19.1. Kịch bản

Pods trong namespace `orders` kết nối được từ một node nhưng không kết nối được từ node khác sau CNI upgrade. Đồng thời một cloud VPC flow log cho thấy direct connection tới Pod/NodePort không dự kiến.

### 19.2. Các lớp cần phân biệt

| Lớp | Câu hỏi |
|---|---|
| Cloud route / SG / NACL | Đường giữa subnets/zones và public/private endpoints có đúng? |
| Node/host | Kernel, hostNetwork, kubelet/CRI, iptables/nftables hoặc eBPF datapath khỏe? |
| CNI | NetworkPolicy ingress/egress được enforce và không drift? |
| Kubernetes Service | ClusterIP/EndpointSlice selectors, kube-proxy/eBPF service routing đúng? |
| DNS | CoreDNS, NodeLocal DNSCache, service name resolve đúng? |
| Workload | Pod readiness, ports, mTLS/sidecar/waypoint và app logs? |
| IAM/control plane | Audit ai đổi deployments, labels, NetworkPolicies, SG/routing? |

### 19.3. Những bẫy phổ biến

- Một NetworkPolicy `default-deny` không tự bảo vệ mọi **hostNetwork/node traffic**.
- Policies Kubernetes **cộng dồn allow**; thêm default-deny không xóa quyền allow rộng của policy khác.
- `namespaceSelector` và `podSelector` đặt trong **hai phần tử peer** là OR, có thể mở rộng scope.
- Traffic tới Service VIP có thể trải qua DNAT/SNAT khác với Pod IP.
- Ambient/sidecar mesh có thể thêm proxy/tunnel ports và capture paths khác.
- IPv6 hoặc secondary interfaces có thể cần enforcement riêng.
- CNI engine không hỗ trợ NetworkPolicy vẫn có thể để Kubernetes API **chấp nhận manifest**.

### 19.4. Containment phù hợp

- Giới hạn theo **workload identity/labels và namespace** khi CNI hỗ trợ đúng.
- Cô lập source Pod/host bằng kiểm soát đã thiết kế; tránh delete ngay Pod nếu cần giữ volatile evidence và chưa có kế hoạch.
- Kiểm tra có **immutable deployment/Image/SBOM/CI actor** thay vì xem Pod restart là xử lý sạch.
- Nếu lỗi bắt đầu từ network policy/config rollout, rollback theo version có tests và health checks.
- Tách **cloud SG/firewall** khỏi **NetworkPolicy** và **application AuthZ**, không tin một layer bao phủ layer khác.

## 20. Playbook F — Nghi data exfiltration qua network egress

### 20.1. Kịch bản

Một service account hoặc Pod bắt đầu gửi nhiều bytes tới public endpoint không nằm trong dependency inventory. Cảnh báo có thể đến từ proxy, VPC flow logs, DLP, DNS/EDR hoặc application export logs.

**Không suy exfiltration chỉ từ egress volume.** Backup, software updates, telemetry, object storage replication và CDN transfers cũng có thể tạo traffic lớn.

### 20.2. Câu hỏi điều tra

1. **Source identity và process** nào phát traffic, có change ticket hợp lệ?
2. Destination IP/FQDN có shared CDN, cloud object store hoặc dịch vụ đã đăng ký không?
3. Có bằng chứng **data objects đã bị đọc/export** từ application/DB/storage logs không?
4. Kênh là HTTPS/TLS, VPN, DNS, SFTP hay custom? Log nào thực sự nhìn được content?
5. Traffic bắt đầu lúc nào, tổng bytes theo nguồn/dest là gì, đã dừng hay chưa?
6. User/service account có quyền gì, credential/session có bị compromise không?
7. Data classification và privacy/legal response obligations nào cần xem xét?

### 20.3. Containment và quản lý evidence

- Thu hẹp outbound theo source identity/destination/protocol, sau review business dependencies.
- Thu hồi/rotate credential có dấu hiệu lạm dụng, nếu cần phối hợp application/DB/IdP.
- Dùng **flow/proxy/application/DB/DLP logs** làm nguồn chính trước khi yêu cầu raw encrypted/cleartext packet payload.
- Theo dõi các endpoint/egress paths thay thế sau chặn, nhưng không mở rộng giám sát vượt scope.
- Phân loại mức độ chắc chắn: **suspected egress**, **confirmed unauthorized access**, **confirmed data transfer**, **confirmed exposure** là các trạng thái khác nhau.

Không công bố “toàn bộ dữ liệu đã bị lấy” chỉ vì thấy tổng outbound bytes; packet overhead, encryption, multiplexing và application semantics làm việc quy đổi bytes thành dữ liệu rất dễ sai.

## 21. Những tình huống cần liên hệ nhà cung cấp hoặc nhóm chuyên trách

| Tình huống | Nhóm liên quan | Thông tin cần chuẩn bị |
|---|---|---|
| DDoS vượt capacity edge | ISP/CDN/scrubbing provider, NOC, SRE | Time window, destination, volume, ASNs, business impact |
| BGP route leak/hijack nghi vấn | Routing/ISP/cloud connectivity team | Prefix/AS-path, RIB snapshot, affected peers, timestamps |
| VPN/ZTNA compromise | IAM/identity platform, endpoint, SOC | User/device/session IDs, auth evidence, revocation scope |
| Cloud control-plane access misuse | Cloud security/IAM, provider support | Resource IDs, audit event IDs, actors/roles, changes |
| OT/ICS network incident | OT safety team, plant operations, specialized IR | Safety boundaries, approved change windows, critical protocols |
| Possible data breach | Legal/privacy/compliance, app/data owner | Known data sets, evidence confidence, affected individuals/tenants |
| Critical supply-chain / edge appliance | Vendor response, vulnerability management | Device versions, vendor advisories, indicators, rollback |

**Không tự ý đưa raw PCAP, account credentials hoặc sensitive configuration cho một bên thứ ba** chỉ vì họ tham gia điều tra. Dùng kênh và quyền chia sẻ theo hợp đồng/quy trình được phê duyệt.

## 22. Threat model: 25 lỗi thường gặp trong Network IR

| ID | Rủi ro | Hậu quả | Phòng ngừa / bằng chứng |
|---|---|---|---|
| IR01 | **Không có asset owner** | Không ai phê duyệt containment | Inventory, on-call contacts, RACI |
| IR02 | **Mạng/topology stale** | Chặn nhầm dependency hoặc bỏ bypass | Updated routes, diagrams, service maps |
| IR03 | **Tin một alert là compromise** | Kết luận sai, gây outage | Corroboration, hypotheses/confidence |
| IR04 | **Không tuyên bố incident kịp** | Thiếu IC, bỏ lỡ escalation | Declaration criteria và on-call |
| IR05 | **Không xác định scope** | Bỏ sót subnet/tenant/cloud region | Evidence coverage matrix |
| IR06 | **Clock drift/ingest lag** | Timeline sai, RCA sai | Raw timestamps, normalized time, clock health |
| IR07 | **Chỉ dùng PCAP một điểm** | Sai kết luận về chiều packet | Vantage-point coverage, flow controls |
| IR08 | **PCAP chứa credential/PII** | Secondary data breach | Approval, minimization, encrypted vault |
| IR09 | **Rotation overwrite evidence** | Không còn dữ liệu chứng minh | Capture bounds, custody và retention |
| IR10 | **Host bị tắt trước volatile triage** | Mất process/network state | Evidence-vs-safety decision log |
| IR11 | **Containment quá rộng** | DNS/identity/payment/backup outage | Scope, positive controls, rollback |
| IR12 | **Chặn shared NAT/CDN IP** | Chặn khách hàng hợp lệ | Identity-aware investigation, allowlist review |
| IR13 | **Policy chỉ IPv4** | Attacker/flow dùng IPv6 | Dual-stack controls/tests |
| IR14 | **Origin bypass PEP/WAF** | Phòng vệ edge không bao phủ | Direct path negative tests |
| IR15 | **NetworkPolicy union hiểu sai** | Allow rule khác mở lại traffic | Enumerate selecting policies |
| IR16 | **Chỉ chặn C2 IP, không xử lý host** | Foothold còn nguyên | Host rebuild/EDR, token rotation |
| IR17 | **JWT/credential vẫn dùng được** | Attack tiếp diễn sau “khóa user” | Active session and token revoke tests |
| IR18 | **DDoS false positive** | Legitimate flash crowd bị chặn | Baseline and canary mitigation |
| IR19 | **Chỉ có availability check** | App đã lên nhưng policy/data chưa sạch | Business + security recovery gates |
| IR20 | **Emergency bypass quên tắt** | Bề mặt tấn công mới tồn tại | Expiring exceptions, owner review |
| IR21 | **Phân vai mơ hồ** | Hai đội cùng thay rule xung đột | IC, change owner, single timeline |
| IR22 | **Đánh giá tác động data sai** | Thông báo quá sớm/quá muộn | Legal/privacy process, verified data scope |
| IR23 | **Log pipeline outage không phát hiện** | Có tấn công nhưng telemetry im lặng | Collector heartbeat/coverage alerts |
| IR24 | **RCA đổ lỗi cá nhân** | Không sửa được control gaps | Contributing factors, measurable actions |
| IR25 | **Tuyên bố resolved quá sớm** | Sự cố tái phát/đường tấn công còn mở | Recovery gates + enhanced monitoring |

### 22.1. Phân loại theo tác động

Không có một thứ tự tuyệt đối cho mọi incident. Khi chọn ưu tiên, cân nhắc **active harm**, critical service impact, blast radius, khả năng containment đảo ngược, độ tin cậy evidence và business/safety obligations. Ví dụ:

- Sự cố **DDoS đang làm mất truy cập cấp cứu/OT** có thể cần ưu tiên availability và safety.
- Một **compromised cloud admin account** có thể cần thu hồi ngay dù hệ thống chưa có outage.
- Một **DNS config error nhỏ** có thể có priority thấp nếu không ảnh hưởng production nhưng vẫn phải review change root cause.

## 23. Ma trận kiểm thử lifecycle và runbooks

Đây là các **tình huống tabletop/lab hoặc môi trường được phê duyệt**, không phải hướng dẫn tạo tấn công thật. Mỗi test ghi **expected decision, owner, bằng chứng** và tác động dự kiến.

| ID | Kiểm thử | Kết quả mong muốn | Bằng chứng |
|---|---|---|---|
| P01 | Alert vượt ngưỡng, on-call nhận | Được tạo incident/ticket khi đạt criteria | Alert, ticket, timestamps |
| N01 | Alert là maintenance đã được phê duyệt | Không tự coi là compromise | Change ticket và evidence |
| P02 | IC được assign khi declaration | Có owner và nhịp cập nhật | Incident log |
| N02 | Không có primary on-call | Escalate sang backup contact | Escalation simulation |
| P03 | Flow từ asset đúng hiển thị | Có source/dest/port/time/owner | Flow collector + asset inventory |
| N03 | Route bị NAT làm thay IP | Analyst nhận diện mapping | NAT tables/logs vs flow |
| N04 | IPv6 connection không có trong IPv4 sensor | Phát hiện coverage gap | IPv6 path test và log |
| P04 | Hai nguồn log đồng bộ thời gian | Timeline khớp sai số cho phép | Time sync, event IDs |
| N05 | Sensor lệch clock | Phân tích ghi raw và normalized time | Offset documentation |
| N06 | PCAP có packet drops | Không kết luận “không có packet” | Sensor counters và positive control |
| P05 | Evidence export được bảo vệ | Hash, custodian, restricted vault | Evidence register |
| N07 | Người không có quyền tải PCAP | Bị từ chối | RBAC/access audit |
| P06 | Cô lập nguồn nghi compromise | Flow đáng ngờ dừng theo control | Enforcement verdict và source state |
| N08 | Containment chặn nhầm DNS | Canary phát hiện và rollback hẹp | DNS test/SLO/config diff |
| N09 | Emergency rule mở toàn VPC | Review phát hiện và reject/thu hẹp | Change approval/policy diff |
| P07 | DDoS mitigation có surge hợp lệ | Duy trì user success/SLO | Edge/WAF/app metrics |
| N10 | WAF rule chặn người dùng tốt | Phát hiện false positive và tune | Request cohorts/decision logs |
| P08 | Network policy mới chặn đúng lateral flow | Trusted business flow vẫn hoạt động | Positive & negative flow tests |
| N11 | K8s NetworkPolicy khác allow rộng | Detect union/overlap trước sign-off | Effective policy inventory |
| P09 | Compromised session revoke | Không còn tạo/giữ access ngoài policy | IdP/PEP/app timeline |
| N12 | JWT còn hạn dù user disabled | Phát hiện revocation gap | API token lifecycle test |
| P10 | Khôi phục firewall config an toàn | Route đúng, app health PASS | Config version and SLO |
| N13 | Rollback mở lại public DB | Security negative test fail, dừng rollout | Public-source test/ACL |
| P11 | DNS zone fix đúng | Resolver answers và app hoạt động | DNS logs + app tests |
| N14 | DNS cache/DoH lệch | Không kết luận chỉ từ UDP/53 | Client resolver evidence |
| P12 | CA/certificate remediation đúng | TLS verify thành công từ app clients | Cert chain/SAN/expiry evidence |
| N15 | Tester dùng `verify=false` | Reject kết quả làm bằng chứng TLS integrity | Test review |
| N16 | SIEM ingest mất log | Heartbeat alert được kích hoạt | Pipeline status + separate sensor |
| P13 | Post-incident review có actions | Owners/deadlines/acceptance checks | Action tracker |
| N17 | Containment exception hết hạn | Tự gỡ hoặc được review theo policy | Policy audit và expiry |
| P14 | Dịch vụ phục hồi canary | Latency, errors, security denials đúng | Canary SLO/security checks |
| N18 | Khôi phục app nhưng suspicious egress còn | Không đóng incident | Egress flow evidence |
| N19 | Data transfer chỉ nghi vấn | Báo cáo giữ đúng độ bất định | Confidence/evidence matrix |
| P15 | Sự cố đa-region | IC nhận diện all impacted regions | Cross-region telemetry |
| N20 | Break-glass dùng trong incident | Bị giới hạn, audit và thu hồi | Approval/session logs |

### 23.1. Test thất bại phải có negative evidence đúng lớp

Ví dụ **source không kết nối DB** có thể do:

- Firewall/network deny (đúng kỳ vọng).
- Database service chết (availability failure).
- DNS sai (naming failure).
- TLS certificate sai (auth/transport failure).
- User/DB role không có quyền (application/data AuthZ).

Chỉ gọi test **security deny PASS** khi biết **đúng enforcement point từ chối** hoặc có bằng chứng mạnh và đối chứng từ nguồn hợp lệ. Một timeout không tự chứng minh segmentation hoạt động.

## 24. Chỉ số hiệu quả của network incident response

### 24.1. Tránh dùng một KPI duy nhất

| KPI | Cách hiểu | Lưu ý để không đo sai |
|---|---|---|
| **Time to detect (TTD)** | Từ first known suspicious event đến detection | “First known” có thể thay đổi khi có evidence mới |
| **Time to acknowledge** | Từ alert routed đến người trực nhận xử lý | Không đồng nghĩa đã phân tích chính xác |
| **Time to declare** | Từ dấu hiệu đầu tiên đến incident declaration | Phụ thuộc chính sách declaration |
| **Time to contain** | Từ mốc định nghĩa đến khi control giảm tác động được xác minh | Không tự đồng nghĩa đã eradicated |
| **Time to recover / restore** | Từ incident tới khi dịch vụ đạt recovery criteria | Phải đo riêng business và security gates |
| **Impact duration** | Khoảng user/service bị ảnh hưởng | Có thể khác thời gian incident mở ticket |
| **False positive / negative rate** | Detector đúng sai theo mẫu đã được xác minh | False negatives khó đo nếu không có ground truth |
| **Coverage** | % critical flows/assets có telemetry và runbook | “Có dashboard” không chứng minh mọi flow được nhìn thấy |
| **Evidence quality** | Timeline, coverage, integrity và privacy compliance | Không tối đa hóa raw data volume |
| **Recovery regression** | Số incident tái phát do remediation/rollback | Cần phân biệt cùng nguyên nhân và sự cố mới |
| **Action closure** | % corrective actions đã test PASS đúng hạn | Đánh dấu “done” không bằng validation thực |
| **Customer/SLO impact** | Error rate, p95/p99, availability, business transactions | Quan trọng ngang thời gian SOC đóng ticket |

### 24.2. Công thức minh họa các mốc thời gian

Nếu có:

~~~text
T0 = earliest known malicious/suspicious activity (có thể ước lượng)
T1 = first detector alert
T2 = analyst acknowledgement
T3 = incident declaration
T4 = containment effect verified
T5 = service recovery criteria met
T6 = incident closure / transition to follow-up

TTD     = T1 - T0  (chỉ khi T0 đủ tin cậy)
TTACK   = T2 - T1
TTCONT  = T4 - T0 hoặc T4 - T3, nhưng phải ghi rõ định nghĩa
TTREC   = T5 - T0 hoặc T5 - T3, cũng phải ghi rõ
~~~

Không so TTD/MTTR giữa các nhóm nếu họ định nghĩa **mốc bắt đầu và kết thúc khác nhau**. Ngoài median, nên xem **p95/p99, incident severity, failure domain, tỷ lệ phát hiện trước khi khách hàng báo lỗi** và độ chính xác.

### 24.3. Bảng điều khiển cần phục vụ quyết định

Một SOC/NOC joint dashboard hữu ích có thể thể hiện:

- Incident active theo severity, affected assets/regions/tenants và current owner.
- Alerts theo signal type, confidence, false positives và sensor health.
- Critical flows health, packet loss, latency và traffic drops.
- Network config drifts, recent firewall/router/SG changes, policy verdicts.
- Active quarantine rules và **expiry/approver**.
- Credential/session revocations còn chờ enforcement.
- Evidence completeness, telemetry gaps và time sync alerts.
- Recovery gate status và follow-up action owners.

Dashboard không thay **incident log và command decisions**; các số đo cần liên kết tới evidence nguồn và cập nhật rõ khi giả thuyết thay đổi.

## 25. Tình huống xuyên suốt: nghi sự cố an ninh nhưng nguyên nhân là thay đổi mạng

### 25.1. Bối cảnh giả định

Một dịch vụ xử lý đơn hàng gồm:

- Public HTTPS gateway nhận request từ khách hàng.
- `orders-api` chạy trong Kubernetes, cần truy cập `orders-db` TCP/5432.
- DNS resolver nội bộ và service mesh mTLS cho một số giao tiếp.
- Cloud VPC dùng NAT gateway và các security groups theo tầng.
- SOC thu EDR/IDS, DNS, VPC flow logs; NOC theo dõi routing/firewall; SRE theo dõi SLO.

Sau một lần deploy, Orders API có nhiều connection timeouts. VPC flow logs cho thấy tăng các kết nối tới một IP không quen. IDS đánh dấu một số flow là “possible C2”. SRE thấy queue depth tăng. NOC phát hiện một thay đổi route table có giờ gần trùng.

### 25.2. Chuỗi điều tra mẫu

| Thời điểm tương đối | Quan sát / quyết định | Độ tin cậy |
|---|---|---|
| T0 | p95 latency vượt SLO, on-call alert | Cao: dashboard/app metrics |
| T+3m | IDS cảnh báo unusual outbound | Vừa: cần xác minh false positive |
| T+6m | SOC nhận flow tới IP lạ từ NAT gateway | Vừa: source sau NAT không xác định Pod |
| T+9m | NOC thấy route change từ maintenance | Cao: cloud audit cho thấy config change |
| T+12m | IC tuyên bố incident hỗn hợp availability/security suspected | Phù hợp impact; hypothesis chưa chắc |
| T+15m | Tra NAT/Pod flow và EDR xác nhận IP lạ là telemetry của release mới | Tăng confidence đối với giả thuyết benign |
| T+18m | TCP/5432 bị route sai qua network path khác, firewall deny | Cao: đối chiếu route, flow verdict, change diff |
| T+22m | Scoped rollback route sau peer review, kiểm tra DNS/DB flow | Mitigation được xác minh |
| T+28m | API và DB đạt SLO; negative network tests PASS | Recovery gate |
| Sau đó | Review vì sao canary/mapping route thiếu và alert false positive | Follow-up hành động cụ thể |

Đây là **case study hư cấu**, thời gian chỉ để học cách dựng timeline, không phải SLA mà tổ chức nào cũng phải đáp ứng.

### 25.3. Những lựa chọn sai thường gặp

- **Chặn toàn bộ egress TCP/443** vì thấy một IP lạ, làm ngừng telemetry, certificate validation và cloud API hợp lệ.
- **Bỏ qua alert IDS** chỉ vì có change window, trong khi vẫn có thể xảy ra compromise đồng thời.
- **Rollback toàn bộ network policy** về trạng thái broad allow từng tồn tại để chạy lại nhanh.
- **Đổ lỗi database** chỉ vì app nhận timeout, không có evidence ở TCP/route level.
- **Tuyên bố security incident đã được loại trừ hoàn toàn** chỉ từ một source benign; các indicators khác chưa được review.
- **Xóa PCAP/logs** khi app hồi phục và làm mất chứng cứ sự cố.

### 25.4. Kết luận đúng theo evidence

**Kết luận tối thiểu:** lỗi route/firewall gây timeout TCP/5432 và đã được khắc phục bằng thay đổi có kiểm soát. Một số traffic được IDS đánh dấu là telemetry của release mới theo evidence đã kiểm tra. Chưa được suy rằng **không có bất kỳ malicious activity khác** nếu sensor scope còn giới hạn; incident commander định nghĩa remaining monitoring và data/security assessment.

### 25.5. Hành động cải tiến

1. Thêm canary **API→DB TCP/5432 connectivity** từ mỗi zone/node có liên quan.
2. Bổ sung **route policy review** và automated diff đối với critical database paths.
3. Liên kết VPC NAT logs với Pod/workload identity để giảm false attribution.
4. Tuning IDS detection cho legitimate telemetry mới có owner, không tắt toàn bộ class alert.
5. Update critical dependency inventory, source/dest IP transformation maps và recovery runbook.
6. Diễn tập “route rollback khi IDS cảnh báo C2 đồng thời” để kiểm tra phối hợp SOC/NOC/SRE.

## 26. Trường hợp phát hiện compromise thật: điều gì thay đổi?

Giữ cùng bối cảnh nhưng giả sử thay vì traffic telemetry hợp lệ, EDR xác nhận process bất thường trên `orders-api`, IAM audit ghi service account token bị dùng ở môi trường không dự kiến và outbound flows liên tục sau khi app rollback.

Khi đó:

1. **Update declaration:** từ nghi vấn chuyển sang confirmed compromise theo chứng cứ, nâng severity nếu rủi ro lan rộng/data cao.
2. **Contain source:** network quarantine/workload isolation theo quyền, giữ kênh evidence; chặn egress liên quan.
3. **Revoke identity:** thu hồi/rotate service account credentials và những secrets có khả năng bị lộ.
4. **Scope lateral movement:** xem API access, management/control-plane audit, DB activities, other Pods/nodes và tenant boundaries.
5. **Preserve evidence:** lưu EDR/process/network logs, forensic artifacts được phép, digests và chain of custody.
6. **Eradicate:** rebuild workload từ image được kiểm tra, vá root vulnerability và thắt quyền IAM/CNI/egress.
7. **Recover:** canary service mới, business positive tests và security negative tests; tránh dùng lại credential/token cũ.
8. **Assess data impact:** application/DB audit có cho thấy unauthorized access hoặc data transfer? Có cần legal/privacy escalation?
9. **Monitor:** flow indicators/credential use không tái phát trong phạm vi observation đã định nghĩa.

**Một route rollback đơn thuần không đủ** nếu attacker vẫn có credential hợp lệ hoặc foothold khác. Incident lifecycle chuyển sang xử lý **host, identity, network và dữ liệu song song**, chứ không chỉ availability remediation.

## 27. Bài tập thực hành dành cho nhóm SOC/NOC/SRE

Không cần tấn công thật. Có thể dùng tabletop, log mẫu và PCAP lab đã được phê duyệt.

### 27.1. Câu hỏi tình huống

1. Ba tín hiệu nào giúp phân biệt DDoS, flash crowd và retry storm?
2. Một alert flow tới IP lạ đủ để tuyên bố exfiltration chưa? Cần evidence nào từ app/DB/EDR?
3. Vì sao PCAP ở **phía sau SNAT** có thể không nhận ra Pod nguồn?
4. Khi EDR báo một host có malicious process đang tạo kết nối, chọn isolate trước hay memory capture trước dựa vào yếu tố gì?
5. Nếu firewall deny rule cô lập một subnet làm DNS và backup lỗi, ai phê duyệt và dựa trên tiêu chí nào để rollback?
6. Vì sao timeout tới database từ source không được phép **không đủ** để kết luận NetworkPolicy hoạt động?
7. Nếu chứng chỉ gateway đã hết hạn, thay certificate có phải eradicate root cause chưa? Cần kiểm tra vòng đời/rotation?
8. Khi user VPN bị disable, session RDP đang mở còn hoạt động, bước nào bị thiếu?
9. Sự khác nhau giữa **containment complete**, **eradication complete** và **recovery complete**?
10. Nêu hai loại timestamp cần lưu để phân biệt event xảy ra và SIEM nhận được.
11. Nếu outage đã hết nhưng data access scope chưa rõ, có được đóng security incident không?
12. Với cloud SG mở public 5432, hãy nêu positive/negative tests và dấu hiệu phải escalate Legal/Privacy.
13. Khi Kubernetes NetworkPolicy `default-deny` được tạo mà attacker Pod vẫn kết nối DB, cần kiểm tra những gì?
14. Tại sao metrics **time-to-contain** không nên thay cho **SLO/customer impact**?
15. Hãy đề xuất năm action items cụ thể, có owner và bằng chứng validation, sau sự cố route sai.

### 27.2. Gợi ý trả lời những điểm trọng tâm

- **Phân biệt DDoS/flash crowd/retry storm:** xác định request legitimacy, user behaviors, HTTP paths, retries, source distribution, WAF decisions, backend load và marketing/change events. Không kết luận chỉ từ request rate.
- **Exfiltration:** outbound volume là dấu hiệu, chưa chứng minh data contents hoặc unauthorized access; cần app/DB/proxy/DLP/EDR evidence, nguồn và scope rõ.
- **Isolate hay collect trước:** ưu tiên active harm/safety, khả năng lan rộng, tính dễ mất volatile evidence, khả năng thu thập từ quarantine và delegated authority.
- **NetworkPolicy default-deny:** kiểm tra CNI enforce, selectors, policyTypes, additive union, hostNetwork, node traffic, Service/NAT path, IPv6 và connectivity positive/negative.
- **Tuyên bố recovery:** cần app SLO đạt, policy allow/deny đúng, credentials sạch, data impact được đánh giá ở mức đủ để IC ký hoặc chuyển follow-up theo quy định.

### 27.3. Mẫu bảng tabletop

~~~text
Scenario: suspicious lateral movement from workload A
Inject 1: CNI flow log shows new A -> DB TCP/5432
Inject 2: Application owner reports a scheduled migration
Inject 3: IAM audit shows unknown role assignment
Inject 4: Emergency deny rule interrupts reporting jobs

Participants:
  SOC analyst, NOC lead, SRE owner, IAM, IC

Expected outcomes:
  - Distinguish verified from suspected events.
  - Document owner/approval for containment.
  - Retain evidence without exporting tokens/payloads.
  - Restore critical legitimate flows while denying untrusted source.
  - Record revision history, recovery gates, action items.

Evaluation:
  Evidence completeness, time to coordinated decision,
  customer SLO impact, correctness of isolation,
  recovery test results, quality of follow-up actions.
~~~

## 28. Checklist trước–trong–sau network incident

### 28.1. Trước sự cố — Preparation

- [ ] Có asset inventory, owners, topology và critical data flows theo từng môi trường.
- [ ] Có RACI/IC, SOC/NOC/SRE/IAM/App/Legal escalations, backup contacts.
- [ ] Có on-call và out-of-band/break-glass access có approval, TTL và audit.
- [ ] Firewall, routing, VPN, ZTNA, WAF, DNS, cloud và Kubernetes configs được version hóa.
- [ ] Biết NAT/SNAT/DNAT, overlay/VLAN, dual-stack, service mesh và other bypass paths.
- [ ] Có telemetry từ network devices, flow logs, DNS, proxy, identity, EDR, application và CNI.
- [ ] Có collector heartbeat/health alerts và time sync monitoring.
- [ ] Có restricted evidence storage, encryption, retention và chain-of-custody process.
- [ ] Đã diễn tập DDoS, lateral movement, DNS, route/security group misconfig và credential revoke.
- [ ] Có quy trình emergency change, canary, test, rollback và business owners.

### 28.2. Khi phát hiện — Detection & Analysis

- [ ] Phân biệt event, alert, anomaly, outage và security incident theo criteria.
- [ ] Ghi incident ID, severity, confidence, affected scope, IC và next review.
- [ ] Tách **observations**, **hypotheses**, **unknowns** và **contradicting evidence**.
- [ ] Kiểm tra recent deploy/maintenance nhưng không coi change ticket là bằng chứng không có attacker.
- [ ] Dựng timeline với UTC/raw timestamp, known clock offsets và log ingestion delay.
- [ ] Xác định source/destination trước/sau NAT, IPv4/IPv6 và capture vantage point.
- [ ] Kiểm tra sensor coverage, packet drops và log gaps trước khi suy “không có activity”.
- [ ] Thu logs/evidence ít can thiệp nhất, đúng quyền và bảo vệ raw PCAP/credentials.
- [ ] Phối hợp IAM/EDR/App/DB/Privacy nếu incident có yếu tố identity/data.
- [ ] Có một nơi ghi decision và một communication owner cập nhật stakeholders.

### 28.3. Cô lập và xử lý — Containment & Eradication

- [ ] Mỗi action có **reason, scope, owner, approver, rollback, expiration và validation**.
- [ ] Với active harm/safety risk, hành động khẩn theo delegated authority có ghi nhận.
- [ ] Tránh block all traffic khi có thể giảm bằng control nhỏ hơn và đủ hiệu quả.
- [ ] Không chặn shared CDN/NAT IP hoặc toàn VLAN nếu chưa đánh giá user/business impact.
- [ ] Kiểm tra DNS, identity, backup, monitoring, OT và management dependencies.
- [ ] Giữ đường forensic được phê duyệt, không vô tình phá evidence có giá trị.
- [ ] Kiểm tra policy ở đúng enforcement point: firewall, CNI, mesh, gateway, VPN.
- [ ] Không mặc định default-deny Kubernetes ghi đè all other allow policies.
- [ ] Không chỉ chặn indicator mà bỏ root cause, malware foothold hoặc compromised credentials.
- [ ] Rebuild/rotate/revoke/patch/root-cause remediation có sign-off theo role.
- [ ] Không mở direct origin bypass hoặc tắt TLS verification để phục hồi nhanh.

### 28.4. Khôi phục và học hỏi — Recovery & Improve

- [ ] Có positive tests chứng minh legitimate business flows hoạt động trở lại.
- [ ] Có negative tests chứng minh suspicious/untrusted flows bị deny đúng lớp.
- [ ] App SLO, DNS, routes, TLS, data integrity và identity access được xác minh.
- [ ] Các active sessions/credentials bị revoke được kiểm tra, không chỉ login mới.
- [ ] Canary rollout và monitoring window có owner; có khả năng rollback an toàn.
- [ ] Emergency rules được gỡ/chuyển thành baseline có review, không sống vô thời hạn.
- [ ] Data/privacy/security impact được đánh giá theo evidence và đúng quy trình.
- [ ] IC xác nhận exit criteria và còn theo dõi những unknowns/accepted risks nào.
- [ ] Post-incident review có timeline, root cause/contributing factors và evidence caveats.
- [ ] Corrective actions có owner, deadline, expected result và acceptance tests.
- [ ] Đã cập nhật threat model, monitoring, network diagram, inventory và runbooks.
- [ ] Đã đo TTD, acknowledge, contain, recover, user/SLO impact theo định nghĩa rõ.
- [ ] Raw evidence được giữ/xóa theo policy, legal hold và kiểm soát bản sao.

**Ghi nhớ:** **Network incident response lifecycle là vòng lặp giảm thiệt hại dựa trên bằng chứng**, từ chuẩn bị và phát hiện, qua phân tích, tuyên bố sự cố, cô lập có kiểm soát, loại bỏ nguyên nhân, phục hồi rồi cải tiến. **Containment không phải eradication; service lên lại không có nghĩa threat đã biến mất; absence of logs không phải absence of attack.** Một chương trình ứng phó mạnh cần **ownership rõ, telemetry đa lớp, evidence custody, quyết định có phạm vi và rollback, positive/negative recovery tests, truyền thông chính xác và corrective actions được kiểm chứng**, đồng thời bảo vệ an toàn vận hành, dữ liệu và quyền riêng tư.
