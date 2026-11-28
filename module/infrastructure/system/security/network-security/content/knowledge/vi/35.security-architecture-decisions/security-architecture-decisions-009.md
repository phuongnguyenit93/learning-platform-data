# Khi nào dùng managed service trong kiến trúc bảo mật mạng?

## 1. Bài toán kiến trúc: mua năng lực vận hành hay tự sở hữu toàn bộ?

Một doanh nghiệp cần bảo vệ dịch vụ Internet, mạng nội bộ, DNS, VPN, danh tính kết nối, IDS/IPS và workloads trên cloud. Đội ngũ có thể **tự triển khai và vận hành** firewall, WAF, DNS, PKI, SIEM, VPN concentrator hoặc thuê một **managed service** từ nhà cung cấp. Câu hỏi đúng không phải "managed service có bảo mật hơn không?" mà là: **trong bối cảnh cụ thể, phương án nào đạt mục tiêu kiểm soát rủi ro, độ sẵn sàng, khả năng kiểm chứng và tổng chi phí ở mức chấp nhận được?**

Managed service giúp chuyển giao một phần công việc như provisioning, patching, capacity management, scaling, giám sát, phản ứng sự cố, nâng phiên bản hoặc backup. Nhưng việc thuê quản lý **không chuyển giao toàn bộ trách nhiệm**: tổ chức vẫn phải quyết định ai được truy cập, dữ liệu nào được bảo vệ, cấu hình rule gì, phát hiện thất bại bằng cách nào, ai được phép thay đổi chính sách và làm gì khi nhà cung cấp gặp sự cố.

Ngược lại, tự vận hành cho phép kiểm soát sâu hệ thống, vị trí đặt dữ liệu và quy trình, nhưng đòi hỏi kỹ năng, đội trực, khả năng cập nhật bảo mật, quy trình thay đổi và năng lực ứng cứu. Một thiết bị mua đứt **không tự trở thành giải pháp bảo mật** nếu thiếu người trực cảnh báo hoặc không duy trì cấu hình đúng.

### 1.1. Những câu hỏi bài học phải trả lời

1. **Năng lực nào là khác biệt cốt lõi?** Tổ chức cần tự sở hữu policy/telemetry/crypto keys hay chỉ cần kết quả bảo vệ có thể kiểm chứng?
2. **Rủi ro lớn nhất là gì?** DDoS volumetric, bot/HTTP abuse, lateral movement, DNS poisoning, CA/key compromise, identity misuse, mất telemetry, nhà cung cấp outage?
3. **Yêu cầu kỹ thuật ra sao?** Độ trễ, throughput, số rule/policy, multi-region, IPv6, traffic inspection, certificate/mTLS, NAT, VPN, failover, data retention?
4. **Ai thực sự trực vận hành?** Có chuyên gia 24/7 cho triage, tuning, patch, rotation, incident response và change review không?
5. **Ranh giới tin cậy nằm ở đâu?** Nhà cung cấp có đọc plaintext, metadata, khóa riêng, logs, danh tính hoặc quản trị mạng?
6. **Có thể chứng minh hệ thống hoạt động đúng không?** Có audit trail, export logs, synthetic checks, negative tests, SLA/SLO và thực nghiệm failover không?
7. **Nếu vendor tăng giá, đổi chính sách hoặc gặp sự cố thì sao?** Có khả năng di chuyển, tắt service, truy hồi cấu hình/chứng cứ, khôi phục policy không?

### 1.2. Mục tiêu học tập

Sau bài học, người học có thể:

- Phân biệt **self-managed, cloud-managed, managed platform, MSP/MSSP, SaaS security service, co-managed và outsourced operations**.
- Áp dụng **shared responsibility**, xác định bên chịu trách nhiệm chính, bên thực thi và cách xác minh từng security control.
- Đánh giá managed firewall/WAF, DDoS protection, DNS, PKI, VPN/ZTNA, IDS/IPS, telemetry/SIEM, cloud network và Kubernetes/mesh.
- So **TCO, đơn vị chi phí, SLA, SLO, RTO/RPO, blast radius, latency và giới hạn dịch vụ** một cách định lượng có điều kiện.
- Sử dụng **hard gates + ma trận trọng số + kịch bản rủi ro + pilot có tiêu chí thoát** để đưa ra quyết định.
- Thiết kế observability, incident response, vendor access governance, private connectivity, key custody và **exit strategy** trước khi ký hợp đồng.
- Viết **Architecture Decision Record (ADR)** rõ phương án chọn, giả định, trade-off, bằng chứng, rủi ro còn lại và thời điểm xem xét lại.

Bài thuộc chương **Quyết định kiến trúc bảo mật mạng** của module **SECURITY_NETWORK_SECURITY**: gắn các lớp bảo vệ như segmentation, firewall, VPN, IDS/IPS, DNS, wireless, cloud network và phân tích lưu lượng với quyết định kiến trúc thực tế.

> **Nguyên tắc:** các cấu hình, bảng giá, SLO và ví dụ trong bài là mô hình học tập, **không phải cam kết hiện hành của nhà cung cấp hoặc giá chào hàng thật**. Trước khi triển khai, phải đối chiếu điều khoản, loại dịch vụ, khu vực, policy và tài liệu cập nhật của đơn vị liên quan. Không chạy thử nghiệm quét/stress, chặn mạng hoặc đổi routing trên production khi chưa được phê duyệt.

## 2. Managed service nghĩa là gì, và không nghĩa là gì?

### 2.1. Những mô hình vận hành

| Mô hình | Ai vận hành hạ tầng/platform? | Ai xác định security policy? | Ví dụ theo khái niệm |
|---|---|---|---|
| **Self-managed** | Đội nội bộ quản lý phần lớn vòng đời | Đội nội bộ | Tự triển khai firewall/Suricata, resolver DNS, VPN gateway |
| **Managed infrastructure** | Provider vận hành hạ tầng nền | Khách hàng và provider tùy control | Cloud networking, managed load balancer |
| **Managed security platform** | Provider cập nhật/scale platform | Khách hàng cấu hình policy/intent | Managed WAF, DDoS edge, cloud firewall |
| **MSP — Managed Service Provider** | Bên thứ ba vận hành hệ IT theo hợp đồng | Có thể chia sẻ | Network operations, VPN infrastructure administration |
| **MSSP — Managed Security Service Provider** | Bên thứ ba giám sát/điều hành security functions | Phân vai detection, escalation, response | Managed SOC, alert triage, IDS/IPS monitoring |
| **Co-managed** | Đội nội bộ và nhà cung cấp cùng thực hiện | Phải tách vai chi tiết | Nhà cung cấp vận hành sensor, SOC nội bộ duyệt containment |
| **SaaS control** | Provider quản lý application stack và platform | Khách hàng quản lý tenant, identity, policy, dữ liệu | SaaS DNS security, cloud SWG, managed telemetry |

**Cloud-hosted không tự đồng nghĩa managed**: một VM tự cài OpenVPN hoặc firewall trên cloud vẫn là **self-managed workload**, dù cloud provider quản lý máy chủ vật lý. Một sản phẩm bán theo thuê bao cũng chưa chắc kèm nhân sự trực phản ứng sự cố.

### 2.2. Phân biệt product, platform và dịch vụ có người trực

Một managed WAF có thể tự cập nhật signature/rule sets và scale edge capacity, nhưng **không mặc nhiên có SOC 24/7 phân tích false positive** hoặc người thực hiện emergency exception thay khách hàng. Một MSSP có thể tiếp nhận alerts, nhưng **không có quyền quyết định cô lập host** nếu hợp đồng chưa giao quyền đó.

Đừng viết ADR "vendor chịu trách nhiệm bảo mật" theo kiểu chung chung. Phải tách:

- **Ownership:** ai là accountable owner cho rủi ro kinh doanh?
- **Implementation:** ai cấu hình rules, certificates, service accounts, access policy?
- **Operations:** ai patch, scale, trực sự cố, backup, rotation và kiểm tra định kỳ?
- **Evidence:** ai phát hiện misconfiguration, xuất log, cung cấp audit trail, xác nhận control?
- **Escalation:** ai phê duyệt emergency change, contact path, time-to-acknowledge?
- **Recovery:** ai khôi phục service, rollback, thông báo khách hàng và giữ bằng chứng?

### 2.3. "Managed" không bằng "zero configuration"

Nhà cung cấp có thể quản lý platform nhưng khách hàng vẫn phải thiết lập **DNS delegation, firewall rules, WAF policies, CA trust, OAuth/SSO, private routes, resource permissions, SIEM export, application onboarding và failover**. Cấu hình sai ở tenant có thể vô hiệu lợi ích của dịch vụ được quản lý.

## 3. Shared responsibility: ranh giới không thể mơ hồ

### 3.1. Bảng trách nhiệm mẫu

| Công việc / control | Provider thường có thể chịu | Khách hàng vẫn cần kiểm soát/xác minh |
|---|---|---|
| Datacenter/physical network | Physical access, thiết bị nền | Chọn region/availability, đánh giá phụ thuộc |
| Managed firewall platform | Lifecycle service, appliance patching, scaling theo gói | Policy, rule review, subnet zones, risk acceptance |
| WAF threat intelligence rules | Managed rule feeds/update mechanisms | Tuning, exceptions, app-specific rules, false-positive testing |
| DDoS edge mitigation | Detection/filtering/capacity theo contract | Origin bypass defense, incident workflow, service health SLO |
| DNS authoritative availability | Cluster/anycast/zone serving service | Records/TTL/delegation/DNSSEC/key ownership/zone changes |
| VPN/ZTNA platform | Gateway updates, uptime/availability | IdP, user/device access, conditional access, resource authorization |
| Managed PKI | Certificate issuance/renew service tùy sản phẩm | Domain validation/authorization, private-key custody, SAN/use, deployment |
| Managed IDS/IPS/SOC | Sensor platform, detection content, monitoring theo scope | Asset inventory, ground truth, incident severity, containment approval |
| Telemetry/SIEM backend | Ingestion/index/query platform | Log sources, retention, access, detection quality, evidence preservation |
| Compliance attestations | Provider chứng minh control trong phạm vi của họ | Tổ chức chứng minh end-to-end control và xử lý dữ liệu đúng mục đích |

**Đây là mẫu khái niệm, không phải hợp đồng chuẩn.** Chi tiết có thể đảo khác giữa các sản phẩm. Ví dụ provider có thể quản lý khóa khi dùng managed certificate, nhưng khách hàng có thể buộc phải **sở hữu khóa trong HSM riêng** theo compliance. Đọc từng dịch vụ, service tier, add-on và điều khoản xử lý sự cố.

### 3.2. Trust boundary đi qua đâu?

~~~mermaid
flowchart LR
    U["Users / endpoints"] --> D["DNS, Internet, provider edge"]
    D --> P["Managed security control"]
    P --> O["Customer origin / private service"]
    O --> DB["Data + identities"]
    C["Customer SOC / platform team"] -. "Policy, identity, audit, approvals" .-> P
    V["Provider operations"] -. "Platform patching / scaling" .-> P
    L["Logs and evidence"] -. "Export and monitoring" .-> C
    P --> L
~~~

Điểm đáng xem:

1. **Data plane:** packet/HTTP payload đi qua đâu, ai có thể terminate TLS hoặc nhìn plaintext?
2. **Control plane:** ai có quyền thay DNS records, WAF rules, routing, TLS certificates hoặc khóa?
3. **Management plane:** ai truy cập dashboard/API và bằng SSO/MFA/PAM nào?
4. **Observability plane:** raw logs/flow records lưu ở đâu, có đủ để IR không và ai được truy cập?
5. **Key plane:** TLS private keys, DNSSEC keys, API tokens, VPN credentials thuộc ai?

### 3.3. Provider compromise cũng là threat scenario

Mọi quyền mà nhà cung cấp có — chỉnh rule, thay route, cập nhật policy, đọc logs, terminate TLS, deploy code hoặc truy cập khóa — đều tạo **supply-chain và privileged-access exposure**. Kiểm soát phù hợp có thể gồm least privilege, SSO/MFA, scoped service accounts, approval flow, immutable audit, dual control, key custody separation và khả năng thu hồi kết nối nhà cung cấp.

Một provider có chứng nhận compliance vẫn có thể gặp outage hoặc compromise; khách hàng phải **thiết kế với khả năng provider không khả dụng hoặc control plane bị thay đổi ngoài ý muốn**.

## 4. Khi nào managed service thường là lựa chọn mạnh?

Những dấu hiệu dưới đây là **lý do để đưa managed option vào shortlist**, chưa phải kết luận mua ngay.

### 4.1. Nhu cầu hạ tầng thay đổi nhanh và quy mô lớn

- Dịch vụ Internet có traffic biến động lớn theo giờ/sự kiện; cần edge scale hoặc multi-region.
- Nhiều endpoints/regions khiến self-hosted appliances cần capacity planning, HA clustering và vận hành 24/7.
- WAF/DDoS/DNS cần **global placement, low-latency routing và threat feeds** mà tổ chức nhỏ khó tự xây đủ.
- Onboarding hàng trăm/một nghìn workloads đòi automation, API, IAM và fleet certificate rotation.

Không suy "managed luôn có unlimited capacity": các dịch vụ có **quotas, rate limits, vùng hỗ trợ, bandwidth tiers, contract fair-use, packet inspection limits** và những kiểu tấn công chưa nằm trong phạm vi bảo vệ.

### 4.2. Đội ngũ không đủ năng lực vận hành chuyên biệt

Đội nội bộ có thể đủ chuyên môn thiết kế rules nhưng không thể **trực 24/7, duy trì detector, ứng cứu tức thời hoặc nâng phiên bản firewall**. Managed operations hỗ trợ lấp khoảng trống này nếu có **runbook, service-level commitments và escalation** thực sự.

Tuy nhiên cần giữ **internal owner hiểu hệ thống và có quyền audit**. Nếu không ai nội bộ biết policy hoạt động thế nào, việc thuê ngoài có thể khiến tổ chức phụ thuộc hoàn toàn khi provider gặp sự cố.

### 4.3. Tính chuẩn hóa cao và dễ mô tả interface

Managed phù hợp hơn khi control có **hợp đồng kỹ thuật rõ**: DNS authoritative availability, certificate issuance/rotation, common WAF patterns, DDoS mitigation hoặc metrics ingestion. Khi business logic quá đặc thù, một managed product đóng có thể không hỗ trợ những điều kiện cần.

### 4.4. Có thể xác minh độc lập

Tổ chức có khả năng chạy **synthetic user journeys, allowed/denied flow tests, config export, rule diff, audit trail, control-plane health và DR drills**. Mua dịch vụ dễ nhưng không đo được kết quả là một **black box**, không đạt mục tiêu kiến trúc.

### 4.5. Chi phí tổng hợp và rủi ro thấp hơn khả năng tự vận hành

Managed đáng xem khi subscription + integration + traffic/log costs + retained staffing + vendor risk **thấp hơn hoặc dễ kiểm soát hơn** chi phí triển khai/vận hành tự quản lý cho cùng security outcome.

Một sản phẩm free/open-source **không đồng nghĩa zero TCO**: còn có nhân sự, patching, HA, storage, threat intel, observability, incident response, kiểm toán và downtime.

## 5. Khi nào không nên hoặc chưa nên dùng managed service?

### 5.1. Không đáp ứng hard requirements

Một dịch vụ có thể có uptime và features hấp dẫn nhưng **không được phép chọn** nếu vi phạm điều kiện bắt buộc:

- Dữ liệu hoặc lưu lượng không được phép **rời một khu vực/jurisdiction, trust zone hoặc hệ thống cách ly**.
- Nhà cung cấp không cho phép tổ chức giữ **quyền kiểm soát khóa mã hóa** theo yêu cầu.
- Không đáp ứng **thẩm quyền audit, forensic export, evidence retention hoặc legal hold**.
- Kiểm soát phải chạy **offline/air-gapped** và vẫn hoạt động khi kết nối Internet/provider control plane mất.
- Giao thức/thiết bị yêu cầu chuyên biệt, không tương thích proxy, TLS inspection hay cloud routing.
- Không có SLA, hỗ trợ kỹ thuật, quyền truy cập hoặc điều khoản xử lý sự cố đủ mức đã duyệt.
- Quy định hợp đồng/đối tác không cho phép bên thứ ba truy cập metadata hoặc plaintext của hệ thống.

**Hard gate không phải điểm số.** Một managed solution trượt điều kiện pháp lý hoặc an toàn bắt buộc không được chọn chỉ vì rẻ hoặc tổng điểm tính năng cao.

### 5.2. Latency và kết nối đặc thù

Một managed secure web gateway/proxy nằm xa users/servers có thể làm tăng **round-trip time, jitter, TLS handshake overhead hoặc detour traffic**. Với network control công nghiệp, truyền thông thời gian thực, hệ thống xử lý cực thấp độ trễ hoặc uplink không ổn định, tự kiểm soát tại site/hybrid có thể phù hợp hơn.

Không kết luận chỉ từ khoảng cách địa lý: hiệu năng còn phụ thuộc peering, route selection, congestion, CDN placement, protocol và client behavior. **Đo ở user vantage với tải/đường đi đại diện**, không lấy marketing latency làm số liệu sản xuất.

### 5.3. Khả năng tùy chỉnh/giải thích không đủ

Tổ chức có thể cần:

- Rules theo deep protocol/industrial network không có trong managed product.
- Truy cập raw PCAP hay inline packet context để kiểm thử/điều tra.
- Tùy chỉnh detector/IPS signatures hoặc inline fail-open/fail-closed theo safety requirements.
- Tích hợp policy-as-code cụ thể, approval và promotion workflow.
- Chạy OS/network agent hoặc crypto primitive chưa được nhà cung cấp hỗ trợ.

Nếu managed platform **chỉ cung cấp kết luận "blocked" mà không có rule ID, reason, source identity hoặc export khả dụng**, khó chứng minh kiểm soát đã hoạt động đúng.

### 5.4. Vendor concentration risk

Khi một bên đồng thời cung cấp **DNS, CDN/WAF, DDoS mitigation, IAM, certificate issuance và log storage**, một outage/control-plane compromise có thể ảnh hưởng nhiều lớp bảo vệ cùng lúc. Mua nhiều tên sản phẩm từ **cùng hạ tầng/control plane** chưa tạo độc lập thực sự.

Cần phân tích **correlated failure domains**, shared dependency, regional footprint, IAM/root credential và recovery options. Đôi khi kiến trúc hai providers còn tốn chi phí/vận hành nhiều hơn và gây lệch policy, nên đa nhà cung cấp cũng không mặc nhiên an toàn.

### 5.5. Năng lực nội bộ mạnh với hạ tầng ổn định

Nếu đội nội bộ đã có firewall team/SOC 24/7, nền tảng HA được tự động hóa, security updates đúng hạn, DR được kiểm thử và policy chất lượng cao, thì **self-managed có thể hợp lý** về khả năng kiểm soát và chi phí. Đừng chuyển sang managed chỉ vì nhãn "cloud-native".

### 5.6. Không thể thực hiện exit

Nếu hệ thống phụ thuộc **API độc quyền, rule language khó chuyển đổi, identity format riêng, logs không export hoặc dữ liệu không thể xóa/di chuyển**, tổ chức có thể mất quyền thương lượng và khả năng khôi phục khi nhà cung cấp thay đổi. Nếu **exit cost/timeline vượt risk appetite**, cần thiết kế adapter, chuẩn hóa export và diễn tập từ sớm hoặc chọn phương án khác.

## 6. Từ yêu cầu bảo mật đến tiêu chí quyết định đo được

### 6.1. Chuyển mong muốn thành kiểm chứng

| Mong muốn mơ hồ | Tiêu chí đủ cụ thể để đánh giá |
|---|---|
| "Chống DDoS tốt" | Traffic scenarios được định nghĩa, protection scope L3/L4/L7, origin bypass controls, detection/mitigation visibility và khả năng thử nghiệm được cấp phép |
| "WAF thông minh" | Coverage theo route, rule IDs, false-positive review, exception TTL, synthetic positive/negative tests |
| "DNS ổn định" | Availability SLI từ nhiều regions, query correctness, delegation/DNSSEC, control-plane outage procedures |
| "VPN bảo mật" | MFA/device posture, least privilege, session revocation, split tunnel/IPv6 policy, auth and app-level tests |
| "Đủ compliance" | Data classification, jurisdiction, sub-processors, access/audit/retention mapping tới controls liên quan |
| "SOC xử lý nhanh" | 24/7 coverage, measurable triage/notification/escalation times, verified incident exercises |
| "Chi phí thấp" | 3-year TCO với scenarios peak traffic, log growth, incident response, egress, support, exit |
| "Có thể chuyển provider" | Export config/policy/logs, portability proof, cutover/rollback rehearsal, contract deletion obligation |

### 6.2. Ưu tiên theo rủi ro kinh doanh

Đối với mỗi use case, mô tả **assets, threat actors, attack paths, impact và risk acceptance**. Ví dụ DDoS trước public API có thể gây ngừng kinh doanh, trong khi IDS cho mạng lab có thể chấp nhận log trễ và downtime nhiều hơn.

Đừng cho cả hai bài toán cùng một weight/SLA chỉ vì dùng chung thuật ngữ "bảo mật mạng".

### 6.3. Biến kiểm thử thành điều kiện phê duyệt

Một security architecture option chỉ nên qua vòng pilot khi có:

1. **Pass/fail criteria** gắn với business/application.
2. **Positive control**: lưu lượng được phép vẫn chạy đúng.
3. **Negative control**: lưu lượng trái policy bị chặn tại đúng PEP.
4. **Measurement validity**: logs và metrics có mẫu số/timestamp/vantage tin cậy.
5. **Change/rollback plan**: có cách khôi phục an toàn khi rule gây outage.
6. **Data handling**: biết plaintext/metadata/key được xử lý ở đâu và bởi ai.
7. **Ownership**: RACI, on-call/escalation, bản ghi risk acceptance.

## 7. Hard gates: lọc trước khi tính điểm

### 7.1. Mẫu cổng đánh giá

| Gate | Câu hỏi | Khi không đạt |
|---|---|---|
| **G1 — Legal/data residency** | Dữ liệu/logs, keys và truy cập bên thứ ba đáp ứng quy định? | Không chọn cho workload đó |
| **G2 — Security ownership** | Có quyền audit, export, review policies và chứng minh control? | Không chọn nếu là yêu cầu bắt buộc |
| **G3 — Network compatibility** | Protocol, IPv6, VPN/PKI, latency và traffic paths hỗ trợ? | Thiết kế lại/hybrid hoặc loại |
| **G4 — Availability/failover** | Dependency, outage mode, SLO/RTO/RPO phù hợp hệ trọng yếu? | Loại hoặc bổ sung control độc lập |
| **G5 — Incident operations** | Có báo sự cố, log preservation, support và contact 24/7 nếu cần? | Loại hoặc ký service tier phù hợp |
| **G6 — Identity/key governance** | SSO/MFA/PAM/SCIM, key custody, break-glass, offboarding khả thi? | Loại nếu không giảm được rủi ro |
| **G7 — Budget/exit viability** | TCO worst-case và exit/rollback nằm trong giới hạn? | Chọn option khác hoặc thay scope |

Mỗi gate phải có **owner, evidence reference, PASS/FAIL/UNKNOWN và expiration date**. `UNKNOWN` không được tự coi là PASS; nếu thiếu bằng chứng, yêu cầu demo/contract hoặc pilot. Một gate có thể không áp dụng với hệ thống nhất định; ghi **N/A cùng lý do**, không loại tùy tiện.

### 7.2. Ví dụ policy-as-intent

~~~yaml
# MẪU QUYẾT ĐỊNH, không phải tệp triển khai.
use_case: public-api-waf
criticality: high
hard_gates:
  data_processing_locations:
    requirement: approved-regions-only
    status: pending-evidence
  strict_origin_tls_validation:
    requirement: must-support
    status: pending-demo
  logs_and_rule_ids:
    requirement: export-within-incident-window
    status: pending-pilot
  origin_bypass_protection:
    requirement: documented-and-testable
    status: pending-review
  exit:
    requirement: policy-export-and-safe-cutover
    status: pending-plan
decision: do-not-approve-until-required-gates-pass
~~~

## 8. Ma trận chấm điểm có trọng số: dùng sau hard gates

### 8.1. Công thức

Khi các phương án đều **đạt hard gates**, có thể đánh giá theo tiêu chí có trọng số:

\[
S(o)=\sum_{i=1}^{n} w_i\,r_i(o),
\qquad \sum_{i=1}^{n}w_i=1
\]

Trong đó \(o\) là phương án, \(w_i\) là trọng số, \(r_i\) là điểm **đã chuẩn hóa** (ví dụ 1–5, càng cao càng tốt). Điểm giúp **so sánh có hệ thống**, không thay risk acceptance hoặc bằng chứng kỹ thuật.

### 8.2. Bộ tiêu chí tham khảo

| Tiêu chí | Trọng số minh họa | Định nghĩa 5 điểm |
|---|---:|---|
| Security coverage & auditability | 25% | Controls phù hợp threat model, đo được, có evidence và tuning |
| Availability & resilience | 20% | SLO/DR/bypass/incident behavior đã chứng minh qua pilot |
| Operations capability | 15% | Đội trực, patch/scale/on-call, escalation rõ và đủ quyền |
| Performance & compatibility | 15% | Latency/pps/throughput/protocols đạt requirement ở peak |
| TCO & predictability | 15% | Có dự toán và worst-case margin kiểm chứng, exit cost rõ |
| Portability & control | 10% | Policy/log export, open interfaces, reversible cutover |
| **Tổng** | **100%** | |

### 8.3. Ví dụ điểm **giả định** sau khi PASS tất cả gates

| Tiêu chí | Weight | Self-managed | Managed A | Hybrid |
|---|---:|---:|---:|---:|
| Security coverage | 0,25 | 3 | 4 | 4 |
| Availability | 0,20 | 3 | 5 | 4 |
| Operations | 0,15 | 2 | 4 | 4 |
| Performance | 0,15 | 5 | 3 | 4 |
| TCO | 0,15 | 3 | 4 | 3 |
| Portability | 0,10 | 5 | 2 | 4 |
| **Weighted score (1–5)** | **1,00** | **3,35** | **3,85** | **3,85** |

Các con số do bài học **tự đặt để minh họa cách tính**, không đại diện nhà cung cấp nào. Ví dụ self-managed:

\[
0{,}25(3)+0{,}20(3)+0{,}15(2)+0{,}15(5)+0{,}15(3)+0{,}10(5)=3{,}35.
\]

Với những con số giả định trên, **managed A và hybrid cùng đạt 3,85** nhưng có điểm mạnh khác nhau; tổng điểm bằng nhau không có nghĩa mức rủi ro tương đồng. Cần phân tích độ nhạy, uncertainty và risk appetite.

### 8.4. Không dùng score để che hard gate

Nếu Managed A **không cho xuất logs trong thời hạn điều tra bắt buộc**, nó **không đạt G2/G5** dù được 4,7/5 ở các tiêu chí còn lại. Phải loại hoặc đưa ra một kiến trúc bù trừ đạt gate trước khi so điểm.

### 8.5. Sensitivity analysis

Thử thay trọng số availability từ 20% lên 35% với việc giảm các trọng số khác theo ưu tiên kinh doanh, hoặc tăng TCO trong kịch bản traffic/log growth. Nếu phương án thắng liên tục thay đổi theo các giả định dễ dịch chuyển, **ADR phải ghi quyết định là conditional và yêu cầu đo thêm**.

Không tự coi điểm số có hai chữ số sau dấu phẩy là độ chính xác thực: mức tin cậy của **dữ liệu và cách gán điểm** quan trọng hơn tính toán.

## 9. Total Cost of Ownership: so chi phí vận hành đúng cách

### 9.1. Những nhóm chi phí không được bỏ sót

| Nhóm | Self-managed thường có | Managed service thường có |
|---|---|---|
| Initial implementation | Thiết bị, license, HA setup, CI/CD, hardening, integration | Onboarding, DNS/routing changes, migration, identity/agent integration |
| Infrastructure | Servers/VMs, rack, links, storage, appliance lifecycle | Platform subscription, traffic/request/seat/event-based charges |
| Operations | FTE, 24/7 on-call, patching, rules, capacity, renewals | Retained FTE, provider management, change reviews, incident coordination |
| Telemetry | SIEM/logging pipelines, PCAP, storage, backups, retention | Ingest/export, query, log storage, egress, data processing fees |
| Resilience | Secondary sites, HA, DR tests, overprovisioning | Higher service tier, multiple regions/providers, failover orchestration |
| Security compliance | Audit, pen-test, rule review, vulnerability handling | Vendor due diligence, audit artifacts, data processing agreements, compliance gap controls |
| Incident response | Forensics staff/tools, downtime, external responders | Retainer, premium response, support tier, customer-owned recovery |
| Change/exit | Hardware refresh, migration of automation/operating procedures | Policy export, data retrieval, DNS/cert migration, provider lock-in, deletion verification |

### 9.2. Mô hình so sánh theo chu kỳ

\[
\begin{aligned}
TCO_{\mathrm{self}} &= CapEx_{\mathrm{amortized}} + Staff + Infra + Licenses + HA/DR\\
&\quad + Monitoring + IR + Audit + ExpectedOutageImpact,\\
TCO_{\mathrm{managed}} &= Subscription + Usage + Integration + RetainedStaff\\
&\quad + NetworkEgress + Logs + PremiumSupport + ExitReserve\\
&\quad + ExpectedOutageImpact.
\end{aligned}
\]

**Đừng cộng một khoản hai lần:** ví dụ `Infra` đã bao gồm HA thì không thêm HA/DR nữa; `Subscription` đã bao gồm SOC response thì không tính lại như premium support. Chọn **horizon 3–5 năm** phù hợp vòng đời thiết bị/hợp đồng, dùng NPV khi so dòng tiền dài hạn và lãi suất chiết khấu đáng kể.

### 9.3. Ví dụ số **giả định** (đơn vị: triệu đồng/năm)

| Khoản | Self-managed | Managed |
|---|---:|---:|
| Đầu tư/setup chia đều 3 năm | 120 | 40 |
| Staff trực tiếp giữ lại | 360 | 120 |
| Infrastructure + HA/DR | 180 | 0 (bao gồm subscription theo giả định) |
| Licenses/subscription | 75 | 350 |
| Usage-based traffic/logging/egress | 50 | 180 |
| Security audit/support/IR reserve | 65 | 70 |
| **Tổng dự toán/năm** | **850** | **760** |

Trong kịch bản cơ sở, managed thấp hơn **90 triệu đồng/năm**. Nhưng nếu peak traffic/log export tăng làm usage cost tăng thêm **150 triệu đồng/năm**, managed thành **910 triệu đồng/năm**, cao hơn self-managed **60 triệu**. Đổi lại có thể là năng lực DDoS/availability tốt hơn; phải xét **rủi ro còn lại và outcome**, không chỉ chi phí.

Các số này **không phải báo giá**, và không bao gồm thuế, tỷ giá, giá vốn, lợi ích vô hình, NPV hay giá trị kỳ vọng của outage nếu các khoản đó chưa được mô hình hóa. Đừng lấy chúng làm ngân sách thật.

### 9.4. Dự báo biến động và "bill shock"

Một dịch vụ có thể thu phí theo:

- **Requests / WAF inspections:** traffic bot/attack tăng cũng có thể ảnh hưởng lượng request tính phí tùy điều khoản.
- **Bandwidth / egress:** số GB qua CDN/proxy/tunnel, routing giữa regions.
- **Log ingest / retention / query:** log verbosity, security events trong attack, giữ logs cho IR.
- **Endpoint/users/seats:** devices tăng, MDM/EDR integration, contractor accounts.
- **Keys/certificates:** số cert issued/renewed, HSM operations, CA signing requests.
- **Protected IPs / rules / private tunnels:** scale theo topology.
- **Premium support/response:** severity, service tier, 24/7 analyst coverage.

Kiểm tra **pricing units, minimum commitments, burst tiers, included quotas, overage alerts, data-export charges và renewal terms**. Không giả định DDoS mitigation miễn phí mọi loại attack traffic hoặc giá "per request" áp y hệt cho requests bị chặn.

### 9.5. Giá của một sự cố có xác suất

Chi phí kỳ vọng của gián đoạn có thể mô hình hóa sơ bộ:

\[
E[\mathrm{loss}]=\sum_j P(\mathrm{incident}_j)\times Impact_j.
\]

Đây là một công cụ ra quyết định, **không phải xác suất đáng tin nếu không có dữ liệu**. Dùng các kịch bản lower/base/upper bound, nêu assumptions và confidence. Managed có thể đắt hơn phí định kỳ nhưng giảm rủi ro outage nghiêm trọng; cũng có thể tạo correlated provider failure mới.

## 10. SLA, SLO, RTO, RPO: hợp đồng không thay phép đo

### 10.1. Định nghĩa đúng

| Khái niệm | Câu hỏi | Cách dùng |
|---|---|---|
| **SLA** | Provider cam kết điều gì và có remedy nào nếu vi phạm? | Contractual measure, exclusions, support credits |
| **SLI** | Mình đo thực tế user/business success thế nào? | Synthetic và real traffic, eligibility/time window |
| **SLO** | Mức mục tiêu nội bộ cho user journey là bao nhiêu? | Error budget, incident priorities, release risk |
| **RTO** | Sau gián đoạn, cần phục hồi chức năng trong bao lâu? | DR plan, cutover/rollback deadline |
| **RPO** | Có thể mất bao nhiêu dữ liệu/trạng thái đã lưu? | Backup/config/log replication, data recovery |
| **MTTR** | Thời gian trung bình khắc phục/khôi phục theo định nghĩa nào? | Metric vận hành, cần chỉ rõ population/window |
| **MTTD/MTTA** | Mất bao lâu phát hiện và thừa nhận/cấp người xử lý? | SOC escalation và response workflow |

**SLA credit không trả lại toàn bộ thiệt hại kinh doanh.** Ví dụ provider có SLA 99,95% ở scope của họ, nhưng client vẫn không dùng được API vì DNS delegate sai hoặc origin down. SLI của người dùng có thể thấp hơn dù provider vẫn đáp ứng SLA theo hợp đồng.

### 10.2. Ví dụ availability và error budget

Nếu một dịch vụ đặt **SLO 99,9% time-based** trong 30 ngày (43.200 phút), ngân sách gián đoạn theo mô hình đó là:

\[
(1-0{,}999)\times 43.200=43{,}2\ \text{phút}.
\]

Không tự áp 43,2 phút vào **request-based SLO** hoặc một SLA tính monthly billing periods với exclusions khác. Đọc chính xác definitions về planned maintenance, partial outages, dependencies, minimum volume, no-data và service credits.

### 10.3. Fail-open hay fail-closed?

Một managed security service outage đặt tổ chức trước lựa chọn:

| Thành phần | Fail-open: có thể tiếp tục lưu lượng | Fail-closed: có thể chặn lưu lượng |
|---|---|---|
| Secure web gateway/SWG | Người dùng đi thẳng Internet, **mất inspection** | Giảm rủi ro bypass nhưng làm việc bị gián đoạn |
| WAF/edge proxy | Bypass WAF sang origin nếu có route | Ngăn access, có thể gây outage toàn site |
| Identity-aware proxy | Bỏ qua check sẽ phá zero-trust | Deny khi không verify được identity |
| Private PKI/OCSP | Soft fail khi revocation service unavailable có thể được một số client cho phép | Hard fail làm nhiều clients bị từ chối |
| DNS security | Dùng resolver fallback không filter có thể làm giảm protection | Chặn phân giải/ứng dụng nếu không có resolver |

**Đây là các trade-offs chứ không phải cấu hình chung.** Với giao dịch nhạy cảm, fail-open có thể vi phạm hard gate; với safety-critical systems, fail-closed ở một gateway có thể tạo nguy hiểm. Quyết định theo **threat model, safety, business criticality và chính sách**; diễn tập hậu quả thực tế.

### 10.4. Hợp đồng cần ghi chi tiết

Không chỉ hỏi "uptime 99,9%?" mà còn:

1. **Measurement boundary:** tính tại provider edge, customer tenant hay end-to-end?
2. **Coverage:** region, IPv4/IPv6, DNS/API/control plane/data plane có nằm trong SLA không?
3. **Exclusions:** attack traffic, customer misconfiguration, maintenance, dependencies?
4. **Remedy:** service credit, escalation, exit rights, data return, incident notice?
5. **Support:** response targets và quyền kích hoạt emergency action khi attack đang diễn ra?
6. **Resilience:** multi-AZ/region, control-plane outage handling, key/certificate renewal?
7. **Evidence:** audit/log export, logs retention, forensic preservation, data deletion?

## 11. Phụ thuộc mới: provider control plane, connectivity và identity

### 11.1. Managed solution cũng cần hoạt động khi control plane hỏng

Đánh giá khác nhau giữa:

- **Data plane failure:** traffic không được phục vụ hoặc inspection không hoạt động.
- **Control plane failure:** không đổi rule/DNS/cert/identity được, nhưng data plane có thể vẫn chạy với cấu hình hiện tại.
- **Management plane failure:** dashboard/API/SSO không truy cập được, không thể xem hoặc can thiệp.
- **Logging/telemetry failure:** hệ thống có thể chạy nhưng SOC bị mù.
- **Billing/quota suspension:** tài nguyên bị giới hạn hoặc chính sách sử dụng thay đổi theo contract.

Một dịch vụ cam kết "multi-region" chưa chắc **control plane, audit export và identity provider** cũng đa vùng/độc lập.

### 11.2. Bản đồ phụ thuộc

~~~mermaid
flowchart TD
    USER["Clients"] --> DNS["Authoritative DNS"]
    DNS --> EDGE["Managed edge / WAF / DDoS"]
    EDGE --> ORIGIN["Customer origin"]
    OPS["Customer security team"] --> SSO["SSO/MFA"]
    SSO --> CP["Provider control plane"]
    CP -. "Rules and cert changes" .-> EDGE
    EDGE -. "Telemetry" .-> LOG["Managed log platform"]
    LOG --> SOC["SOC / incident response"]
    ORIGIN --> DB["Backend and data"]
~~~

Nếu Identity Provider mất và đội vận hành không thể đăng nhập provider console, vấn đề có thể trở nên nguy hiểm đúng lúc cần thay WAF rule. Thiết kế **break-glass access** phải vừa tồn tại vừa được bảo vệ (hardware MFA, restricted approvals, immutable audit), không chỉ là một tài khoản shared-admin với mật khẩu không kiểm soát.

### 11.3. Failure-mode matrix

| Sự cố | Ảnh hưởng khả dĩ | Bằng chứng/test cần |
|---|---|---|
| Provider edge region down | Route failover, latency/outage | Multi-vantage synthetic, region cutover tabletop |
| Control plane/API down | Rules không deploy, cert rotation trễ | Read-only status + change freeze/runbook |
| SSO federation down | Team không vào console | Break-glass drill với audit |
| Log export pipeline down | Mất điều tra/chứng minh policy | Freshness/no-data alerts và buffer plan |
| Managed CA renewal fails | Cert hết hạn gây TLS outage | Served-cert expiry & renewal failure alerts |
| Quota/rate limit exceeded | Requests/detections/logs bị drop hoặc tăng phí | Controlled capacity estimates, overage alarms |
| Region data residency drift | Compliance violation | Contract, region config, data location evidence |
| Provider config compromise | Rule allow rộng, route/cert bị sửa | IaC drift detection, immutable audit, scoped roles |
| DNS delegation wrong | User không resolve đúng dù edge healthy | DNS integrity monitoring, rollback procedure |
| Provider termination/change of terms | Không đủ thời gian di chuyển | Tested export/exit plan, notice period |

**Không suy cả provider bị lỗi từ một client timeout.** Kiểm tra DNS, proxy, firewall, origin, identity, route và phép đo độc lập để xác định fault domain.

## 12. Observability và quyền kiểm toán là tiêu chí chọn nhà cung cấp

### 12.1. Tối thiểu cần quan sát gì?

Đối với WAF/firewall:

- Source/destination zone hoặc identity theo khả năng, action ALLOW/DENY, rule ID, policy version, UTC.
- Traffic counts/bytes/requests, blocked vs allowed, false-positive indicators, config change audit.
- Session/NAT/flow mapping nếu cần quy kết endpoint theo thời gian.

Đối với DNS:

- Query health/latency/rcode, zone/delegation changes, DNSSEC validation/serving context.
- Logs theo tenant và mục đích, hạn chế raw query names nếu chứa dữ liệu cá nhân.

Đối với ZTNA/VPN:

- User/device identity, connection/session IDs, policy decision, resource accessed.
- MFA/device posture evidence và revocation outcomes.

Đối với IDS/IPS/SOC:

- Detection provenance, sensor mode, confidence, rule/signature version, actual enforcement action.
- Triage/escalation timestamps, ticket owner, incident disposition, evidence retention.

### 12.2. Telemetry có thể mất đúng lúc bị tấn công

Trong DDoS/HTTP flood hoặc sự cố provider, logs có thể **sampling, rate limiting, delayed ingestion hoặc dropped events**. Đừng coi số "0 alerts" là không có traffic xấu khi collector đã down. Cần:

1. Cơ chế **no-data/heartbeat** riêng.
2. Biết **sampling semantics** và total counts trước sampling.
3. Có **raw export hoặc forensics access** trong các cửa sổ incident.
4. Gắn **timestamp UTC, timezone, request IDs và control version**.
5. Có retention phù hợp IR và quyền truy cập giới hạn cho dữ liệu nhạy cảm.

### 12.3. Kiểm soát việc mở plaintext

Một managed WAF/SWG/TLS inspection service có thể terminate TLS và nhìn thấy HTTP headers/body; đây là **trust boundary mới**, có nguy cơ ghi nhận cookies, bearer tokens, PII. Khi evaluation:

- Xác định dữ liệu nào được inspect, lưu log, sample và chia sẻ với sub-processors.
- Kiểm tra **encrypted at rest/in transit, key custody, role-based access, tenant isolation**.
- Xây chính sách **redaction, data minimization, retention và legal hold**.
- Không triển khai interception trái phép, không bỏ certificate pinning hoặc xác minh server identity.
- Nếu không cần plaintext, ưu tiên metadata/endpoint telemetry và explicit privacy-preserving policies.

### 12.4. Phải tự kiểm chứng control từ hai phía

Ví dụ managed WAF báo blocked 1.000 requests nhưng người dùng hợp lệ cũng không đăng nhập được. SOC cần so **client synthetic success, WAF rule IDs, origin application errors và sampled requests**; không coi "nhiều blocks" tự động là hiệu quả.

Với IDS out-of-band, `alert count` **không đồng nghĩa packets đã bị chặn**. Với DDoS mitigation, `clean traffic passed` không tự chứng minh frontend TLS/certificate hoặc backend application còn đáp ứng.

## 13. Managed firewall và network segmentation: khi nào nên thuê?

### 13.1. Các lựa chọn

- **Virtual/physical firewall tự quản lý:** đội nội bộ tự cài/patch/scale/rule management.
- **Cloud-native managed firewall:** cloud vận hành network enforcement service, khách hàng xác định policy/rules/route.
- **Provider-managed appliance:** nhà cung cấp vận hành thiết bị/firewall theo hợp đồng MSP/MSSP.
- **Distributed host/CNI policies:** mỗi workload/Pod có policy, đôi khi được managed orchestration hỗ trợ.

### 13.2. Khi managed mạnh

Managed firewall có lợi khi tổ chức cần **auto scale across cloud networks, patching không sở hữu appliance, traffic inspection theo tập trung, triển khai multi-AZ và tích hợp API/IaC**. Nhưng phải kiểm tra:

1. **Topology/route insertion:** tất cả paths được yêu cầu có thực sự đi qua firewall?
2. **East–west vs north–south:** firewall có quan sát lateral traffic hay chỉ Internet egress?
3. **Stateful semantics:** đang-established sessions có chịu rule mới không?
4. **NAT/routing:** source identity/port mappings có bị mất hoặc cần flow logs bổ sung?
5. **IPv6, UDP/QUIC, VPN, private connectivity:** có coverage tương đương IPv4/TCP không?
6. **PPS/conntrack/throughput:** giới hạn có thể đến trước bps capacity.
7. **Failover/fail-open/closed:** traffic flow khi managed enforcement unavailable ra sao?
8. **Rule change rollback:** ai có quyền emergency deploy, có diff/audit không?

### 13.3. Khi self-managed/hybrid có ưu thế

Nếu môi trường có **giao thức OT chuyên biệt, nội mạng cách ly, network taps/PCAP bắt buộc, low-latency deterministic paths hoặc team firewall chuyên sâu**, tự quản lý hoặc hybrid có thể đem lại khả năng kiểm soát lớn hơn.

**Không dùng managed firewall để thay toàn bộ segmentation design.** Nếu các subnet/Pod cùng trust zone được phép giao tiếp ngang, một firewall ở public edge sẽ không tự ngăn lateral movement.

### 13.4. Test để quyết định

| Kiểm thử | Nguồn được phép → đích | Kỳ vọng |
|---|---|---|
| Positive user path | Approved client → API | ALLOW, TLS và app success |
| Negative lateral path | Unauthorized workload → DB | DENY ở đúng policy point |
| IPv6 parity | Unauthorized IPv6 client → protected service | DENY theo intent |
| Egress restriction | Restricted subnet → unapproved destination | DENY, có rule/flow evidence |
| Failure mode | Tabletop/sandbox provider edge unavailable | Behavior/rollback tương thích yêu cầu |
| Auditability | Policy change → event/log export | Operator, policy version, timestamp đầy đủ |

Test phải ở lab/canary/authorized maintenance, không tạo production outage chỉ để chứng minh một case.

## 14. Managed WAF, bot protection và API security

### 14.1. Vì sao nhiều đội chọn managed WAF?

WAF cần **tuning nhanh theo application routes, cập nhật rule/signature sets, scaling trước traffic spike và quản trị false positives**. Managed WAF phù hợp khi:

- Ứng dụng public, nhiều releases/ngôn ngữ/framework, traffic phức tạp.
- Đội không đủ nguồn lực vận hành WAF rules 24/7 và DDoS L7 triage.
- Edge/CDN placement mang lợi ích latency/availability thực sự được đo.
- API policies, JWT auth checks, rate limiting hoặc bot signals được hỗ trợ **đúng yêu cầu**.

Không suy WAF giải quyết authorization vulnerabilities, insecure deserialization, business logic abuse hoặc insider misuse. WAF là **control bổ trợ**, không thay code/API security, identity và least privilege.

### 14.2. Phân tích trust boundary khi TLS termination

~~~mermaid
flowchart LR
    CLIENT["Public client"] -->|"HTTPS session A"| WAF["Managed WAF / CDN"]
    WAF -->|"Origin TLS session B"| API["Customer ingress and API"]
    API --> APP["Application authentication/authorization"]
    AUTH["Customer IAM"] -. "Scoped admin and service tokens" .-> WAF
    SOC["Customer SOC"] -. "Rules, logs and exception review" .-> WAF
~~~

Cần xem WAF **đọc plaintext ở edge**, secrets/logged headers, PII handling, TLS certificate/private key custody, inspection exceptions và strict validation **edge → origin**. Nếu WAF đúng nhưng origin vẫn public và chấp nhận direct traffic bypass, attacker có thể tránh control.

### 14.3. Managed rule tuning phải thuộc workflow

- Mỗi rule/exception có **owner, scope, reason, test evidence và expiry/TTL**.
- Triển khai canary hoặc monitor-only trước blocking khi có thể.
- Chạy positive tests cho user hợp lệ và negative tests cho mẫu request sai chính sách trong lab.
- Ghi 403/429, block action và **user impact**, không lấy số blocks làm KPI duy nhất.
- Kết hợp alert nếu **origin request rate lệch so edge rate** hoặc direct-origin path xuất hiện.

### 14.4. Khi self-managed tốt hơn

Khi app ở private network, traffic thấp, quy tắc API đặc thù, có team bảo mật ứng dụng mạnh, hoặc chi phí per request/log rất cao và không cần global edge, reverse proxy/WAF self-managed có thể hợp lý. Tuy nhiên phải chứng minh **patch, rule feeds, high availability, operational ownership và emergency response**.

### 14.5. Kết luận riêng cho WAF

Chọn managed khi nó giảm **rủi ro vận hành/tuning/scale** và có **proof of end-to-end effectiveness**, không chỉ vì "có AI". Yêu cầu vendor chứng minh các tình huống app thực tế, không dùng demo traffic do họ tự chọn làm nguồn duy nhất.

## 15. Managed DDoS mitigation: lợi thế dung lượng không loại bỏ rủi ro thiết kế

### 15.1. DDoS cần nhìn nhiều tầng

- **L3/L4 volumetric:** bandwidth/pps, reflection/amplification, SYN/UDP floods.
- **L7:** HTTP/API floods, expensive routes, bots, cache bypass.
- **Control-plane/identity exhaustion:** login, rate limiting, session creation hoặc backend dependencies.

Một DDoS protection vendor có hạ tầng mạng lớn có thể hấp thụ traffic tốt hơn một site nhỏ, nhưng cần kiểm tra **coverage, upstream paths, integration, activation time, mitigation behavior và application false positives**.

### 15.2. Khi managed DDoS thường đáng ưu tiên

Đặc biệt với public Internet service, khi một attack vượt khả năng ingress link của site, **on-prem appliance nằm sau link không thể tự cứu đường truyền đã bão hòa**. Upstream/edge mitigation là phương án cần đưa vào thiết kế, có thể qua provider-managed service.

Tuy nhiên phải xác định: traffic có **thực sự qua mitigation network** hay attacker có thể gửi thẳng tới origin IP/alternate ISP? Đường bypass có thể làm cơ chế edge vô hiệu, ngay cả khi WAF/DDoS vendor báo đang mitigate.

### 15.3. Bản thiết kế cần kiểm tra

~~~text
Internet
  |
  v
Provider edge mitigation
  |
  +--> Clean traffic via approved connection
             |
             v
      Customer origin (protected ingress)
             |
             +--> App / API / dependency

Unprotected direct-to-origin path:
  MUST be blocked unless explicitly approved
~~~

Các yếu tố quyết định:

1. **Traffic steering:** DNS, BGP, tunnel hoặc cloud integration, tùy dịch vụ.
2. **Time to mitigate:** detection, escalation, automatic vs on-demand routing.
3. **False positives:** legitimate clients có được phục vụ không?
4. **Capacity and quotas:** contract coverage, overages, protected IPs, network limits.
5. **Application health:** WAF/edge success không đồng nghĩa API/business success.
6. **Incident support:** ai được quyền kích hoạt mode, đưa IOC/rule, rollback?
7. **Visibility:** upstream offered traffic, dropped/allowed, clean throughput và attack timelines.

### 15.4. Không tự làm stress test lên Internet

Kiểm thử DDoS thường cần **provider-sanctioned exercise** hoặc lab traffic generator được giới hạn, không chạy floods tự phát trên production, public IP hoặc hệ thống bên thứ ba. Trong ADR, có thể dùng **capacity evidence, contract, provider exercise reports và controlled functional tests**; không buộc phải phát sinh real attack traffic để chứng minh mọi claim.

### 15.5. Managed hay hybrid?

Một lựa chọn thường gặp là **upstream managed volumetric mitigation + app-specific rate limiting/WAF + origin access control do khách hàng sở hữu**. Nó phân công đúng tầng: provider có capacity, tổ chức có business context và authorization. Cần quản trị rule conflicts và đảm bảo logs cross-layer correlate được.

## 16. Managed DNS và DNS security: tách authoritative, recursive, filtering

### 16.1. Ba loại dịch vụ khác nhau

| Loại | Chức năng | Quyết định managed dựa vào |
|---|---|---|
| **Authoritative DNS** | Phục vụ records cho zones doanh nghiệp | Global availability, anycast, DNSSEC, automation, delegation |
| **Recursive resolver** | Phân giải thay client | Privacy, caching, validation, resolver placement |
| **DNS security/filtering** | Chính sách deny/sinkhole/observe domains | Device/user identity, policy controls, threat intel, logs |

Đây là những **trust boundaries khác nhau**. Một managed authoritative DNS không tự bảo vệ nhân viên khỏi phishing domains; một DNS filtering service không tự bảo đảm public zone/delegation đúng.

### 16.2. Khi managed authoritative DNS phù hợp

Nhiều zones/regions, yêu cầu availability cao, tích hợp API/IaC, certificate challenges và geo/health routing có thể khiến managed DNS phù hợp. Nhưng cần:

- **Registrar/account takeover defense**, domain lock, MFA, change approval, DNSSEC lifecycle.
- Rõ quyền **zone export**, DNS record portability, TTL changes/negative caching, rollback.
- SOA/NS/delegation drift và phục hồi khi control plane unavailable.
- Multi-provider DNS nếu được chọn phải có **record synchronization, DNSSEC signing consistency và testing**; không tự cho rằng hai providers có cùng zone data.

### 16.3. Khi managed recursive/filtering phù hợp

Tổ chức có endpoints phân tán, remote work, nhiều thiết bị và cần policy theo **device/user/identity** có thể dùng managed DNS security. Phải kiểm tra:

- Resolver thực sự được sử dụng hay browser/OS dùng DoH/DoT ngoài policy?
- Split-horizon/private domains và VPN routing có đúng?
- IPv4/IPv6 resolver paths, failover và captive portal behavior?
- False positives có làm app/updater/medical device ngừng hoạt động?
- Resolver queries/logs có chứa dữ liệu nhạy cảm, được giữ ở đâu?
- Một DNS block có được bypass khi app dùng IP literal, cached address hoặc non-DNS channels?

### 16.4. Khi self-managed đáng cân nhắc

Nội mạng **air-gapped/OT**, private split-horizon phức tạp, custom DNS policy, data residency chặt hoặc team đã vận hành reliable authoritative/recursive infrastructure. Tuy vậy self-managed resolver cần **DNSSEC validation, patching, logging, capacity, cache poisoning defense và HA**; một VM DNS duy nhất là single point of failure.

### 16.5. Kiểm thử không chỉ bằng NXDOMAIN

**Truy vấn hợp lệ** phải resolve chính xác/đúng TTL và DNSSEC policy; **domain bị cấm** phải bị xử lý đúng theo sản phẩm (NXDOMAIN, refused, block page/sinkhole, v.v.). Không suy mọi `NXDOMAIN` là policy deny: có thể tên không tồn tại thật.

## 17. Managed PKI và certificate lifecycle

### 17.1. Các tầng trong PKI

- **Public certificate issuance/renewal:** CA public, ACME/certificate manager.
- **Private CA:** cấp certificate cho workloads, devices, mTLS identities.
- **Key management/HSM:** sinh/lưu private keys, signing operations, rotation.
- **Certificate deployment:** LB/ingress, service mesh, VPN appliances, endpoints.
- **Trust distribution:** browser/OS/Java/IoT roots, policy và revocation.

Managed issuance có thể **giảm lỗi renewal**, nhưng không tự thay **SAN/hostname validation, origin TLS verification, client truststore, key custody và CA trust governance**.

### 17.2. Khi chọn managed PKI

Chọn shortlist khi có nhiều certs/short-lived workload identities, cần rotation automation, audit issuance, CA availability và fleet management. Một private CA managed có thể giảm burden vận hành CA servers nhưng tổ chức vẫn phải:

1. Xác định **ai được cấp certificate cho tên/danh tính nào**.
2. Kiểm soát enrollment/authentication, template/EKU, SAN, issuance approval.
3. Quản lý **CA root trust** trên client; không mặc định trust mọi certificate do cùng CA phát hành cho mọi service.
4. Xác định **private-key exportability**, provider access, HSM boundary và backup/DR.
5. Chuẩn bị revocation/expiry/issuer change, OCSP/CRL availability nếu có.
6. Giữ logs và quy trình key compromise/incident response.

### 17.3. Khi tự quản lý PKI hoặc hybrid

Nếu yêu cầu **offline root CA, sovereign key custody, dedicated HSM hoặc protocol/certificate profile đặc biệt**, tổ chức có thể giữ root HSM offline/self-managed và dùng managed intermediates/deployment cho một số workloads. Nhưng trust split này tăng complexity: ai ký, ai revoke, ai backup key material, ai vận hành overlap trust khi thay root?

**Đừng chuyển toàn bộ CA private keys qua nhà cung cấp chỉ vì API dễ dùng** nếu không có đánh giá legal, encryption/key custody và khả năng revocation khi thoát dịch vụ.

### 17.4. Test vận hành

- Issuance chỉ cho identity được phê duyệt; unauthorized CSR/enrollment bị reject.
- Đúng `SAN`, `EKU`, validity và certificate policy.
- TLS endpoints **thực sự serve certificate mới**, không chỉ certificate đã được cấp.
- Client truststores/Java/mesh identities xác minh đúng chain.
- Rotation trong controlled pilot không tạo downtime ngoài SLO.
- Renewal/control plane unavailable có **expiry/continuity strategy**.
- Revoke/retire/incident response không để credentials cũ dùng ngoài policy.

## 18. Managed VPN, ZTNA và SASE/SSE

### 18.1. Phân biệt network access và application access

**VPN** thường tạo network tunnel hoặc secure access path. **ZTNA** thường gắn quyền truy cập ứng dụng với identity, device posture và policy context thay vì đưa user vào cả một mạng rộng. **SSE/SASE** là nhóm kiến trúc/sản phẩm kết hợp nhiều chức năng truy cập/bảo vệ; **tên thương mại không bảo đảm** từng control được triển khai đúng.

### 18.2. Khi managed access service có lợi

- Remote workforce rộng, nhiều quốc gia, thiết bị managed/unmanaged và công ty có contractors.
- Đội nội bộ không muốn duy trì VPN gateways/PoPs, patching, license và capacity 24/7.
- Cần tích hợp IdP, MFA, device posture, conditional access và per-app policy tập trung.
- Có private apps trên multi-cloud, branch sites, on-prem và muốn nhất quán access controls.

Nhưng cần đánh giá **network path, last-mile latency, tunneling overhead, split tunnel/always-on policy, DNS routing, IPv6, client device compatibility và agent update lifecycle**.

### 18.3. Những điều managed access không tự giải quyết

| Rủi ro | Điều cần làm |
|---|---|
| Stolen identity/session | MFA, phishing-resistant factors khi phù hợp, session revocation, detection |
| Overbroad app policy | Least privilege theo resource/action; review entitlements |
| Compromised device | Device posture/EDR, managed/unmanaged device policy |
| Alternate direct path | Firewall/segmentation ngăn VPN/ZTNA bypass |
| DNS split-horizon lỗi | Resolver routing, private names, DoH/IPv6 coverage |
| Control-plane outage | Session behavior, break-glass, recovery plan |
| Privacy/location data | Data minimization, log access, contract/data residency |
| Legacy OT/industrial protocols | Vendor support, latency, protocol and safety assessment |

### 18.4. Bảng phép thử

1. Authorized user + compliant device → **đúng một ứng dụng**: ALLOW.
2. Same user → ứng dụng không có entitlement: DENY.
3. Revoked user/device credential → mất quyền theo session policy, cả existing sessions khi yêu cầu.
4. Direct-to-app IP không qua access broker → DENY ngoài approved bypass.
5. IPv6/alternate NIC/split tunnel không tạo đường vào private network trái policy.
6. IdP outage/control plane down → behavior đúng fail-closed hoặc continuity policy.
7. Latency/time-to-connect từ vùng người dùng thực tế đạt SLO.

**VPN tunnel up không đồng nghĩa ứng dụng thành công**. Giám sát nên đo identity-aware synthetic journey, không chỉ gateway heartbeat.

### 18.5. Khi self-managed VPN phù hợp

Khi lượng users ổn định, địa điểm cố định, có đội operations giàu kinh nghiệm và yêu cầu network isolation/sovereign key custody mạnh, self-managed VPN có thể tối ưu. Tuy nhiên phải duy trì **key lifecycle, MFA, patching, high availability, client distribution, tunnel routes và on-call**. Không giữ VPN concentrator cũ chưa vá chỉ vì "nằm trong mạng nội bộ".

## 19. Managed IDS/IPS, SOC và telemetry/SIEM

### 19.1. Detection vs prevention

- **IDS out-of-band** phát hiện hoặc cảnh báo; không tự chặn packets.
- **IPS inline** có thể block/drop/reject theo policy và mode.
- **SOC/MSSP** phân tích, tương quan, escalates và đôi khi thực thi containment nếu được giao quyền.
- **SIEM/log platform** lưu/tìm kiếm/correlate events; không bảo đảm alerts chính xác khi log sources thiếu.

Một MSSP có SOC 24/7 nhưng không có quyền vào firewall **không thể cam kết chặn attack trong 5 phút** trừ khi contract có integration/approved runbook và người nhận xử lý kịp thời.

### 19.2. Khi managed SOC/IDS hấp dẫn

- Volume alerts nhiều, không đủ người vận hành 24/7.
- Cần threat intel/detection engineering và triage expertise.
- Nhiều nguồn dữ liệu cloud, endpoint, firewall, DNS, IAM, VPN.
- Cần chuẩn hóa incident handling, alert severity và escalation.

Nhưng phải đòi **định nghĩa dịch vụ chính xác**: số lượng use cases, phạm vi assets/log sources, giờ trực, detection engineering, triage, proactive hunt, IR assistance, access to raw evidence và data location.

### 19.3. RACI cho một sự cố

| Hoạt động | MSSP/SOC thuê ngoài | Đội nội bộ/owner |
|---|---|---|
| Receive/deduplicate events | Có thể chịu trách nhiệm chính | Xác minh nguồn/log coverage |
| Triage và severity | Có thể thực hiện | Cung cấp business context, accept severity/escalation |
| Containment proposal | Đưa khuyến nghị và IOC | Phê duyệt risk và production impact |
| Execute firewall/EDR action | Chỉ nếu được cấp quyền rõ | Trách nhiệm kiểm soát hiệu lực và rollback |
| Preserve forensic evidence | Theo hợp đồng/scope | Quản lý privacy/legal hold, chain of custody |
| Recovery/rebuild | Có thể hỗ trợ | System/application owner quyết định và thực hiện |
| Post-incident improvements | Đề xuất detection content | Chốt risk treatment, owner và budget |

Đây là phân vai ví dụ; hợp đồng phải cụ thể hóa **người trực, thời hạn escalation và quyền tương tác khi khẩn cấp**.

### 19.4. Những tiêu chí kỹ thuật ít được hỏi

1. Provider có nhận **raw logs** hay chỉ vendor-normalized events? Có mất field trọng yếu như NAT port, process ID, rule ID?
2. Detection logic có thể được **review/export/test** hay là black box?
3. Data retention đủ incident discovery window không? Có sampling/ingest delays không?
4. Alert "resolved" có nghĩa issue đã xử lý hay chỉ ticket đã đóng?
5. Có incident drill để đo **TTD/notification/escalation/containment** không?
6. Cách provider bảo vệ **customer logs có PII/secrets** và tenant isolation?
7. Khi ngừng hợp đồng, có **full log export/detection rules/playbooks** cần để tiếp tục vận hành không?

### 19.5. Đừng đánh giá SOC chỉ bằng số alerts

SOC có nhiều alerts chưa chắc tốt; alert fatigue và false positives làm response chậm. Cần đo **coverage, actionable detections, time-to-detect, response outcomes, false negative scenarios, customer impact và missing telemetry**. Tổ chức vẫn phải sở hữu threat model và tài sản ưu tiên.

## 20. Cloud network, Kubernetes, service mesh và wireless: hybrid thường thiết thực

### 20.1. Cloud networking và managed Kubernetes

Cloud provider thường quản lý phần physical fabric và cung cấp VPC/VNet, managed LB/NAT, DNS hoặc Kubernetes control plane. Nhưng khách hàng vẫn chịu trách nhiệm **subnets, routes, network ACL/security groups, identities, endpoint configurations, NetworkPolicy semantics và workloads** theo service.

**Managed Kubernetes control plane không đồng nghĩa toàn bộ cluster an toàn**: node images, CNI, Pod identities, admission, service mesh mTLS, secrets, ingress và logging có thể vẫn do khách hàng quản lý hoặc thêm add-on riêng.

### 20.2. Khi nào ưu tiên managed control

Managed control phù hợp khi **API declarative, auto scaling, regional availability, integration với platform identities, supported CNI/mesh capabilities và upgrade support** giúp giảm operational burden có chứng cứ. Ngược lại, nếu cần custom dataplane kernel modules, nonstandard CNI, offline root CA, deterministic latency hoặc node-level packet capture, có thể cần self-managed hoặc specialized hybrid.

### 20.3. Service mesh mTLS

Một managed service mesh có thể hỗ trợ **workload certificate rotation, proxy lifecycle, mTLS policy và telemetry**. Nhưng:

- Một Pod có thể dùng **plaintext fallback** nếu policy permissive; phải test thực tế.
- `NetworkPolicy` có **allow rules cộng dồn**, nên tạo policy deny riêng không phủ quyết allow khác.
- Workload identity hợp lệ **không tự cho phép mọi operation**; authorization vẫn cần thiết.
- Sidecar/ambient dataplane có resource costs (CPU/memory/latency), failure domains và version skew.
- Provider quản lý control plane nhưng khách hàng có thể còn phải patch ingress gateways, proxies hoặc nodes.

### 20.4. Managed wireless security

Managed WLAN/controller có thể giảm gánh nặng AP firmware, RF configuration, RADIUS integration và fleet inventory. Nhưng tổ chức cần quản trị:

- WPA2/3-Enterprise/802.1X, credential/certificate lifecycle và NAC policy.
- Guest/corporate/IoT segmentation, VLAN, mDNS/bonjour exceptions.
- Rogue AP detection và site-specific radio/coverage issues.
- Cloud controller outage, local survivability, captive portal behavior.
- Privacy/location telemetry và management roles.

Một cloud-managed AP vẫn có thể mở **guest-to-corporate lateral path** nếu VLAN/firewall policy sai. Physical coverage/safety và endpoint trust không thể thuê ngoài hoàn toàn.

### 20.5. OT/air-gapped systems

Trong OT/critical infrastructure, yêu cầu safety, deterministic traffic, vendor protocol và downtime constraints có thể khiến **local enforcement/self-managed hoặc hybrid** phù hợp hơn cloud-only managed path. Nếu dùng managed monitoring, ưu tiên **passive sensor, local buffering, one-way transfer/approved boundary và vendor safety playbook** khi cần; tránh chèn inline proxy vào control loop mà không đánh giá an toàn.

Không đồng nhất **"air-gapped"** với không có nguy cơ: removable media, maintenance paths, vendor access và configuration drift vẫn tạo risk. Nhưng yêu cầu offline có thể là hard gate loại nhiều managed SaaS.

## 21. Governance, compliance và dữ liệu xuyên biên giới

### 21.1. Data residency không đơn giản là chọn một region

Khi dùng managed service, dữ liệu có thể xuất hiện ở:

- **Data plane:** HTTP body/headers, packet metadata, DNS queries, VPN flows.
- **Logs/telemetry:** request IDs, user IDs, IP addresses, URLs, error payloads.
- **Backups/DR:** replicas, cold storage, snapshots và disaster recovery sites.
- **Support/ticketing:** log bundles gửi cho vendor support ở khu vực khác.
- **Control plane/analytics:** config, metadata, metrics, threat intelligence processing.
- **Sub-processors:** các bên xử lý phụ được vendor sử dụng theo hợp đồng.

Một lựa chọn `Region A` cho data plane **không tự chứng minh mọi log, backup và support access đều ở Region A**. Cần data flow map, contract, vendor disclosures và evidence. **Tuân thủ pháp luật luôn phụ thuộc jurisdiction, loại dữ liệu và thời điểm**; đội pháp lý/compliance cần xác nhận yêu cầu hiện hành thay vì áp một câu chung cho mọi doanh nghiệp.

### 21.2. Những bằng chứng cần khi due diligence

| Chủ đề | Câu hỏi | Evidence cần review |
|---|---|---|
| Shared responsibility | Ai cấu hình, patch, giám sát, ứng cứu? | Service scope/RACI |
| Audit and certifications | Kiểm soát nào được kiểm toán và trong kỳ nào? | SOC reports/ISO certificates và phạm vi liên quan |
| Data access | Nhân viên vendor có quyền vào tenant/logs/keys không? | RBAC/PAM/support access policies |
| Encryption and keys | Ai giữ/rotate/revoke private keys, backup keys? | Architecture/key custody docs |
| Data processing | Logs/packet contents được lưu đâu, bao lâu? | DPA, retention, sub-processor list |
| Incident notification | Thời hạn và kênh thông báo sự cố/vi phạm? | Contract clauses, escalation paths |
| DR/security testing | Có chứng minh failover và vulnerability management? | Redacted audit/exercise reports, support test |
| Export/exit | Lấy lại policy/logs/config và xóa dữ liệu thế nào? | Export API/docs, deletion attestation |

Một chứng nhận chung của provider **không chứng minh tenant đã bật logging, MFA, encryption, least privilege hoặc segmentation đúng**. Phải có **customer-side control evidence**.

### 21.3. Quy định về quyền tiếp cận metadata và plaintext

Ngay cả khi vendor không giải mã HTTP, DNS query logs, network flow, user connection timing và địa chỉ IP có thể là dữ liệu nhạy cảm trong bối cảnh cụ thể. Định nghĩa:

- Mục đích thu, data minimization, masking/pseudonymization.
- Chính sách truy cập, log review, retention, incident preservation.
- Quyền user/tenant, xử lý yêu cầu dữ liệu theo pháp luật.
- Đường truyền encrypted và quản lý key.
- Giới hạn vendor support access, approvals và audit trail.

Tránh dùng "dịch vụ không lưu dữ liệu" như một bảo đảm khi chưa xác minh **logs mặc định, abuse detection, analytics và support diagnostics**.

### 21.4. Phê duyệt rủi ro còn lại

Không có phương án rủi ro bằng không. ADR nên nêu **residual risks, likelihood/impact theo phương pháp tổ chức, owner, mitigation và ngày đánh giá lại**. Risk acceptance phải do **người có thẩm quyền chịu tác động** phê duyệt, không chỉ kỹ sư lập sơ đồ.

## 22. Contract và vận hành: yêu cầu điều khoản có thể kiểm thử

### 22.1. Contract phải đi cùng operating model

Một hợp đồng "24/7 managed security" dễ gây hiểu nhầm nếu không quy định:

- Ai nhận alert khi 02:00, thời gian phản hồi **bằng đơn vị nào**?
- Ai gọi điện/bật escalation khi severity tăng?
- Ai được sửa firewall/WAF rule, revoke certificate, isolate endpoint?
- Nếu vendor đề xuất thay đổi gây outage, ai phê duyệt và rollback?
- Nếu SIEM logs mất, ai chịu trách nhiệm phục hồi chain of custody?
- Nếu phát hiện compromise của vendor account, ai khóa access và thông báo?
- Nếu nhà cung cấp ngừng hoạt động trong một vùng, có runbook chuyển hướng không?

### 22.2. RACI cụ thể theo hoạt động

Trong RACI, **R** = thực hiện, **A** = chịu trách nhiệm cuối cùng, **C** = được tham vấn, **I** = được thông báo. Một hoạt động nên có **một accountable owner rõ**, tránh nhiều người tưởng người khác chịu trách nhiệm.

| Hoạt động | Customer security | Customer platform/app | Provider |
|---|---|---|---|
| Define security objectives/risk acceptance | **A** | C | C |
| Configure application-specific WAF policy | A | **R** | C/R theo contract |
| Patch managed WAF infrastructure | I | I | **A/R** |
| Monitor user-visible application SLI | A | **R** | C |
| Respond to provider platform incident | C | I | **A/R** |
| Approve production firewall exception | **A** | C | R nếu được giao |
| Preserve managed logs for IR | **A** | I | R theo service agreement |
| Certificate issuance/rotation | A | R | R cho phần service-managed |
| Validate end-to-end authorization | A | **R** | C |
| Plan/test vendor exit | **A** | **R** | C/R về export |

Bảng chỉ là mô hình học tập: trước ký, tổ chức phải **tùy chỉnh trách nhiệm và thẩm quyền**. Một bên thứ ba không thể thực hiện thay đổi nếu chưa được giao role/permission.

### 22.3. Những điều khoản đáng yêu cầu

1. **Detailed scope:** regions, devices, protected endpoints, protocol/version, performance limits.
2. **SLA definitions:** data/control plane, measurements, exclusions, service credits.
3. **Incident notice:** categories, timeline, escalation, breach notification obligations.
4. **Data ownership/access:** raw logs, policy config, evidence exports, retention/legal hold.
5. **Security commitments:** vulnerability handling, patch SLAs, sub-processors, secure access.
6. **Change management:** planned maintenance, emergency update rights, rollback responsibilities.
7. **Cost protections:** quota visibility, burst/overage thresholds, renewal conditions.
8. **Exit rights:** export formats, transition support, deletion, key destruction, notice.
9. **Dispute/review:** audit rights, service review, controls that may change.

Không tự giả định vendor sẽ đồng ý tất cả điều khoản: cần **review pháp lý/mua sắm** và quyết định trade-off nếu một điều kiện không thương lượng được.

## 23. Lock-in và exit strategy: thiết kế trước khi cần rời đi

### 23.1. Những kiểu lock-in

| Loại | Ví dụ | Cách giảm |
|---|---|---|
| **Policy language** | WAF rules/managed detections chỉ hỗ trợ DSL riêng | Policy intent chuẩn hóa, test cases độc lập |
| **Control-plane API** | IaC resources không có mapping sang provider khác | Abstraction/adapters và versioned IaC |
| **Data/logging** | Export bị giới hạn, field schema độc quyền | Normalize logs ở customer-controlled pipeline |
| **Identity** | User/device/service identity chỉ vendor hiểu | Federation, standard identity mapping, export |
| **Network routing** | Proprietary tunnels, DNS zone/vendor routing features | Document failover, alternate connectivity |
| **PKI/keys** | Non-exportable keys hoặc CA trust riêng | Key custody decision, planned reissuance/overlap |
| **Operations knowledge** | SOP/changepolicy chỉ nằm ở vendor | Customer-owned runbooks, drills, joint reviews |
| **Commercial** | Minimum volume/long commitment/exit fees | Contract negotiation và reserve budget |

Lock-in không luôn xấu: một dịch vụ tích hợp có thể cải thiện reliability và security. Nhưng **giá trị của sự tích hợp phải bù được rủi ro mất khả năng thay đổi**, được ghi rõ trong ADR.

### 23.2. Exit plan tối thiểu

~~~mermaid
flowchart TD
    A["Define policy and data portability requirements"] --> B["Keep tested exports / normalized schema"]
    B --> C["Build target provider or self-managed equivalent"]
    C --> D["Pilot parallel route and compare decisions"]
    D --> E{"Security and SLO equivalence?"}
    E -- "Không" --> FIX["Fix policy/telemetry/identity gaps"]
    FIX --> D
    E -- "Có" --> F["Approved cutover with rollback"]
    F --> G["Revoke vendor access, rotate credentials"]
    G --> H["Confirm data deletion, retention and evidence custody"]
~~~

### 23.3. Phải trả lời "di chuyển cái gì?"

Với managed WAF:

- Domain/DNS delegation, certificates/CA, edge-to-origin trust, routes/allowlists.
- Rules, exceptions, rate limits, bot policies và false-positive regressions.
- Logs/indicators, incident history, alert connectors, billing/cutover.

Với managed SOC/SIEM:

- Log sources/collectors, normalization, detection rules, dashboards/playbooks.
- Case records, chain of custody, legal hold, retention, query/export APIs.
- Analyst escalation contacts, service roles và SSO.

Với managed PKI:

- Root/intermediate trust, issuance policy, key custody, certificate inventory.
- Client truststore migration, revocation, overlap trust window và reissuance plan.
- TLS/mTLS application reconfiguration, cert expiration and rollback.

### 23.4. Những rủi ro khi "dual run"

Chạy hai WAF/DNS/identity systems cùng lúc có thể gây **policy divergence, double logging/charges, certificate mismatches và race conditions**. Dual run phải có **scope, decision authority và cutover criteria**; không tự cho hai nguồn policy đồng thời được quyền chỉnh cùng một route.

### 23.5. Exit rehearsal

Để đánh giá portability thực, thử trong lab:

1. Export một policy bundle được phép.
2. Triển khai vào test target **không dùng secrets production**.
3. So kết quả ALLOW/DENY với bộ regression tests.
4. Tái dựng log schema/correlation IDs.
5. Kiểm tra DNS/TLS/app success và rollback.
6. Ghi time/cost/data gaps và owner của các thiếu sót.

Nếu migration không thể mô phỏng dù với một ứng dụng mẫu, **"có API export" chưa phải bằng chứng có thể rời provider**.

## 24. Mẫu Architecture Decision Record (ADR)

ADR là tài liệu có thể kiểm toán giải thích **vì sao chọn phương án**, không phải quảng cáo nhà cung cấp.

### 24.1. Cấu trúc gợi ý

~~~markdown
# ADR-NETSEC-009: Managed WAF cho Public API (ví dụ)

## Status
PROPOSED — chưa phê duyệt, không phải production decision.

## Context
- Dịch vụ: public API, multi-region, yêu cầu user-facing SLO.
- Rủi ro: HTTP abuse, false-positive blocks, DDoS L7, origin bypass.
- Giới hạn: latency, privacy, authorized regions, incident logging.

## Options
1. Self-managed ingress WAF + internal on-call.
2. Managed edge WAF + private origin protections.
3. Hybrid edge WAF + app authorization/rate-limit controls.

## Hard gates
- Data/location/access policy: PENDING.
- Origin TLS identity and bypass prevention: PENDING.
- Audit logs with rule IDs and export: PENDING.
- Rollback/DR and service continuity: PENDING.

## Evidence
- Pilot test IDs and positive/negative outcomes: PENDING.
- 3-year TCO sensitivity: PENDING.
- Vendor contract/RACI review: PENDING.

## Proposed decision
Conditional shortlist; do not go live until hard gates PASS.

## Consequences
- Gains: edge capacity, managed rule feed, simpler patch operations.
- Costs/risks: TLS termination at provider, per-request pricing,
  correlated provider outage, false positives, API and policy lock-in.

## Owners / Review
- Security owner, application owner, platform owner.
- Review after pilot, at renewal and after material incident.
~~~

### 24.2. ADR cần làm rõ 5 điều

1. **Giả định nào có thể sai?** Ví dụ traffic growth, latency, provider visibility.
2. **Bằng chứng nào sẽ làm đổi quyết định?** Gate fail, TCO overrun, missing log export.
3. **Những phương án nào bị loại và tại sao?** Không dựng đối thủ rơm.
4. **Ai chịu rủi ro còn lại?** Có người phê duyệt, ngày rà soát, mitigation.
5. **Làm thế nào rút lại quyết định?** Rollback và exit rõ ràng.

### 24.3. Quy tắc cập nhật

ADR không bất biến khi:

- Dịch vụ mở thêm region, sensitive data hoặc customer segment.
- Threat landscape/risk appetite thay đổi.
- Provider đổi service scope, ownership, pricing hoặc policy.
- Một outage/incident cho thấy giả định sai.
- New managed capability xuất hiện hoặc self-managed team trưởng thành.

Thay vì viết đè lịch sử, tạo **revision/superseding ADR** và liên kết evidence để người kiểm toán có thể hiểu quyết định ở từng thời điểm.

## 25. Case study 1 — Public commerce API: managed WAF/DDoS hay tự vận hành?

### 25.1. Bối cảnh giả định

Một nền tảng commerce có public API phục vụ nhiều khu vực. Traffic tăng đột ngột trong chiến dịch khuyến mại; đội nội bộ có hai kỹ sư infrastructure, chưa duy trì WAF rules hoặc đội trực chống DDoS chuyên trách. Sự cố trước đây từng làm nghẽn uplink origin. Doanh nghiệp cần bảo vệ đăng nhập, checkout và API nhưng cũng có yêu cầu **privacy và strict TLS verification**.

Thông số dưới đây **chỉ minh họa**:

~~~text
Service: commerce-api.example.test (mô phỏng)
Traffic profile: highly variable, peak season significant
Threat concerns: volumetric DDoS + L7 abuse + checkout bot traffic
Business SLI: eligible checkout success and p99 latency
Current on-call: limited, no dedicated DDoS upstream capacity
Origin: cloud private subnet with public ingress to be restricted
Compliance: logs must be restricted and exportable
Decision deadline: after controlled pilot, not today
~~~

### 25.2. Phương án so sánh

| Phương án | Ưu điểm | Rủi ro |
|---|---|---|
| Self-managed WAF ở origin | App-specific tuning/control; có thể giảm phí per request | Không cứu uplink khi volumetric DDoS đã bão hòa; operational burden cao |
| Managed edge WAF/DDoS | Upstream capacity, edge placement, vendor patch/rule feeds | TLS termination trust, false positives, origin bypass, usage costs |
| Hybrid: managed edge + private origin/app controls | Provider hấp thụ edge volumetric, customer giữ authz/business policies | Cần phối hợp hai control planes, log correlation và kiểm thử policy |

### 25.3. Hard gates trước pilot

1. Allowed data regions / log retention / vendor support access đáp ứng privacy requirement.
2. Edge→origin **strict certificate and hostname validation**, không tắt vì private CA.
3. Origin chỉ nhận lưu lượng từ **đường được phê duyệt**, không public direct bypass.
4. WAF rules và block decisions có **rule ID, UTC time, export/API**, hỗ trợ forensic.
5. Có workflow emergency rule disable/rollback với **owner + audit + TTL**.
6. Có contractual cost ceiling/overage visibility và capacity assumptions khi peak.
7. Service SLO được đo **end-to-end**, không chỉ vendor edge response.

Nếu bất cứ hard gate bắt buộc nào FAIL, không chọn managed edge bằng cách **cộng thêm điểm throughput** để bù.

### 25.4. Pilot kiến trúc

~~~mermaid
flowchart LR
    USER["Approved clients / synthetic probes"] --> EDGE["Managed DDoS + WAF edge"]
    EDGE --> ORIGIN["Restricted origin ingress"]
    ORIGIN --> APP["App authn/authz + rate limits"]
    EDGE -. "Rule IDs + clean/blocked metrics" .-> SOC["Customer SOC"]
    APP -. "Success/error/latency" .-> SOC
    DNS["Managed DNS or current resolver"] --> EDGE
~~~

Điều cần đo:

- **Positive:** hợp lệ checkout/login/API từ các vùng, IPv4/IPv6 và client runtime.
- **Negative:** unauthorized direct-to-origin, denied admin route, bot/rate-limit examples trong lab.
- **TLS:** client→edge và edge→origin verification độc lập; không chỉ kiểm "HTTPS padlock".
- **Performance:** client p95/p99, error rate/availability và origin processing; so trước/sau cùng tải hợp lệ.
- **Operations:** simulate rule false positive, approval/rollback/audit và vendor escalation.
- **Cost:** requests/log ingest/egress ở bình thường + peak, không giả định traffic attack luôn miễn phí.

### 25.5. Quyết định có điều kiện

Nếu pilot đạt hard gates, managed edge+hybrid controls có thể là **phương án hợp lý** vì thiếu năng lực upstream/24x7 nội bộ. Tuy nhiên, ADR phải ghi:

~~~text
Decision: CONDITIONAL HYBRID (training scenario)
Provider scope: DDoS edge + managed WAF operation
Customer scope: origin protections, app authz, identity, monitoring
Unresolved: contract cost cap and support escalation evidence
Go-live gate: positive/negative TLS+policy tests, log export, rollback drill
Review trigger: major traffic change, false-positive incident, renewal
~~~

**Bài học:** managed mạnh khi mang lại năng lực không thể sao chép dễ bằng nội bộ, nhưng **security outcome phụ thuộc origin, app và khả năng kiểm chứng độc lập**.

## 26. Case study 2 — OT plant: managed cloud inspection có hợp lý không?

### 26.1. Bối cảnh giả định

Một nhà máy có vùng điều khiển vận hành 24/7, các PLC/gateway sử dụng giao thức chuyên biệt và quy trình bảo trì rất hạn chế. Một nhà cung cấp đề xuất đưa **toàn bộ traffic OT qua cloud security inspection proxy** để nâng khả năng phát hiện. Đội OT lo ngại latency/deterministic timing, vendor protocol support và phụ thuộc Internet.

### 26.2. Hard gates quan trọng hơn marketing features

| Gate | Yêu cầu | Kết quả giả định với cloud-only inline |
|---|---|---|
| Safety | Không gây gián đoạn control loops | **UNKNOWN/khó chứng minh** |
| Offline survivability | Vẫn điều khiển được khi Internet down | **FAIL** nếu mọi traffic phải qua cloud |
| Protocol fidelity | Không biến đổi traffic công nghiệp | **UNKNOWN** |
| Low latency/jitter | Đạt worst-case deterministic requirement | **UNKNOWN** |
| Evidence/privacy | Logs được bảo vệ trong vùng yêu cầu | **UNKNOWN** |
| OT owner approval | Có đánh giá hazard và vendor support | **PENDING** |

Với những điều kiện giả định, **không được chọn cloud-only inline** chỉ vì nó chấm cao trong bảng SOC features. Cần thiết kế khác hoặc cung cấp bằng chứng mới để giải quyết hard gates.

### 26.3. Phương án hybrid có thể thử

~~~mermaid
flowchart LR
    OT["OT devices / PLCs"] --> LOCAL["Local segmentation / OT firewall"]
    LOCAL --> CTRL["Local control servers"]
    LOCAL -. "Passive SPAN/TAP" .-> SEN["Local passive sensor"]
    SEN --> BUF["Approved on-site buffer"]
    BUF -. "Scoped telemetry through approved boundary" .-> SOC["Managed SOC analytics"]
    OTO["OT owner / safety lead"] -. "Approvals and safety review" .-> LOCAL
~~~

Trong mô hình này, **critical control traffic không phụ thuộc live cloud inspection**. Một local passive sensor hoặc approved OT monitoring stack có thể gửi **metadata/event summaries** qua boundary được kiểm soát tới managed SOC, nhưng phải kiểm tra network isolation, data sensitivity, buffering và failover.

### 26.4. Kiểm thử cần thiết

- Network control loops không bị thêm inline dependency ngoài thiết kế.
- Khi mất Internet/SOC service, thiết bị vẫn vận hành theo safety requirements; logs local được buffer theo capacity policy.
- Traffic monitoring **không phát sinh active scans** hoặc gửi payload ngoài scope.
- Cảnh báo IDS out-of-band được phân biệt với enforcement của local firewall.
- Các updates của sensor/service có approval và rollback với OT safety lead.
- Data leakage/supply-chain risks của management connection được kiểm soát.

### 26.5. Kết luận giả định

**Self-managed local enforcement + managed SOC cho telemetry chọn lọc** có thể hợp lý hơn cloud inline trong use case này, *nếu* toàn bộ hard gates đạt. Không coi đây là thiết kế chuẩn cho mọi OT: từng plant/process có hazard analysis, vendor constraints và architecture khác.

**Bài học:** với hệ safety-critical, **offline survivability và tác động vật lý** có thể là hard gate quan trọng hơn subscription cost hay số detection signatures.

## 27. Case study 3 — SaaS SOC/SIEM với data residency và khó thoát dịch vụ

### 27.1. Bối cảnh giả định

Một tổ chức có khoảng vài trăm endpoints, network firewalls, VPN và cloud workloads, đội SOC nội bộ chỉ trực giờ hành chính. Managed SOC/SIEM được đề xuất để giám sát 24/7. Tuy nhiên logs chứa **user identifiers, DNS query names, VPN source addresses và incident artifacts**; quy định nội bộ yêu cầu những loại dữ liệu nhất định chỉ được lưu trong approved jurisdiction.

Provider A có detection contents tốt nhưng không cung cấp raw event export đầy đủ; provider B hỗ trợ export nhưng dữ liệu phân tích đi qua region chưa rõ. Self-managed SIEM có kiểm soát log tốt nhưng quá tải nhân lực.

### 27.2. Ma trận bằng chứng

| Requirement | Provider A | Provider B | Self-managed |
|---|---|---|---|
| 24/7 triage | Có theo đề xuất, cần kiểm chứng | Có theo đề xuất | Thiếu người hiện tại |
| Residency/processor mapping | Cần DPA cụ thể | **UNKNOWN** cho analytics path | Kiểm soát nội bộ thuận tiện hơn |
| Raw log/evidence export | **Không đủ** theo giả định | Có nhưng cần pilot | Do nội bộ quản lý |
| Rule/detection portability | Proprietary/unknown | Có mapping một phần | Có thể tự version |
| Incident escalations | Chưa diễn tập | Chưa diễn tập | Biết owner nhưng thiếu on-call |
| 3-year TCO/worst-case | Chưa tính | Chưa tính | Chưa tính personnel growth |

Không có căn cứ để kết luận ngay "mua Provider A" hay "tự vận hành rẻ hơn".

### 27.3. Hướng giải quyết

1. **Đóng hard gates**: kiểm tra pháp lý/jurisdiction/processor path cho logs, audit và export/retention.
2. Thử **minimization/pseudonymization** tại customer-controlled collectors nếu hợp lệ và không phá điều tra.
3. Yêu cầu provider có **raw export, detection provenance, case retention/chain of custody**.
4. Thiết kế **customer-owned canonical log pipeline** hoặc durable copy theo data policy, không cho provider là bản chứng cứ duy nhất.
5. Diễn tập **alert triage → notify customer → authorization → containment → evidence preservation**.
6. Tính **log growth/egress/retention costs**, SOC retained FTE và exit expense.
7. Nếu data cannot leave approved zone, cân nhắc **local SIEM + MSSP remote analysis đúng phạm vi** hoặc regional managed platform có bằng chứng residency.

### 27.4. Exit test của một detection

~~~text
Input:
  Synthetic lab firewall deny, VPN auth, endpoint process event.

Provider SOC:
  Creates incident alert with severity and evidence refs.

Export:
  Download normalized + raw events and rule/detection definitions if allowed.

Customer copy:
  Reproduce correlation using customer-owned test pipeline.

Validation:
  Same relevant time range/asset mapping and investigation outcome.

If export insufficient:
  Portability gate remains FAIL/UNKNOWN; do not approve until resolved.
~~~

### 27.5. Kết luận giả định

Một lựa chọn **hybrid SOC** có thể kết hợp đội managed 24/7 với **customer-owned log/evidence boundary**, nếu data flows và rights phù hợp. Nếu không có cách export/keep evidence theo yêu cầu, provider bị loại cho use case đó dù detection marketing hấp dẫn.

**Bài học:** đừng chọn managed SOC bằng số lượng signatures hoặc khẩu hiệu "AI SOC". Chọn bằng **detection coverage, incident outcomes, dữ liệu thuộc quyền ai và có thể tiếp tục điều tra khi hợp đồng kết thúc hay không**.

## 28. Runbook 10 bước quyết định và triển khai managed service

Runbook này áp dụng cho các lựa chọn **managed/self-managed/hybrid** liên quan bảo mật mạng. Không thực thi production changes như một phần của nghiên cứu thị trường; mọi network changes phải theo phê duyệt và change-control của tổ chức.

### Bước 1 — Xác định business outcome và ranh giới

~~~text
Decision ID: ADR-NETSEC-009
Service: e.g., public API / private network / OT site
Owner: application + security + platform accountable persons
Threat model: attacks, assets, expected blast radius
User SLI/SLO: defined and measurable
Data classifications: metadata / payload / credentials / keys
Required regions: documented
Dependencies: DNS, IAM, VPN, TLS, cloud, monitoring, support
Risk acceptance authority: documented
~~~

Một quyết định thiếu **business context** có thể dẫn tới mua platform rất mạnh nhưng đặt sai điểm network enforcement.

### Bước 2 — Liệt kê phương án thật sự khả thi

Ít nhất:

1. **Self-managed:** công cụ hiện hữu + năng lực vận hành/đầu tư cần bổ sung.
2. **Managed A:** service tier và vùng triển khai cụ thể.
3. **Hybrid/co-managed:** managed capacity/platform với customer-owned policy/telemetry hoặc ngược lại.
4. **Do nothing/keep current:** làm baseline, nhưng phải ghi **rủi ro không thay đổi**.

Không so managed product đầy đủ với self-managed bản tối thiểu chưa có HA/24x7 nếu business requirement cần HA/24x7 ở cả hai.

### Bước 3 — Vẽ trust, control và data flows

~~~mermaid
flowchart TD
    CLIENT["Client or workload"] --> NET["Network boundary / DNS / identity"]
    NET --> PEP["Managed or self-managed enforcement"]
    PEP --> APP["Application / protected service"]
    POLICY["Customer security owner"] -. "Policy and risk decisions" .-> PEP
    VENDOR["Provider ops if managed"] -. "Service lifecycle" .-> PEP
    PEP -. "Flow/decision/audit telemetry" .-> EVID["Customer evidence and monitoring"]
    EVID --> SOC["SOC and incident commander"]
~~~

Đánh dấu ở từng hop:

- Traffic có plaintext không; ai có quyền đọc?
- Có TLS termination/re-encryption và strict hostname/CA validation không?
- Ai có quyền chỉnh rule, DNS records, identity entitlements, routes và certificates?
- Nếu control plane unavailable, data plane có hoạt động/fail theo policy không?
- Lưu logs ở đâu, giữ bao lâu và có xuất ngay khi IR cần không?

### Bước 4 — Áp hard gates

Mỗi option ghi `PASS`, `FAIL`, `PENDING` hoặc `N/A + reason` cho legal/data, trust/key, coverage, availability, observability, response và exit. Những điều kiện **bắt buộc** còn PENDING thì **chưa approve production deployment**.

### Bước 5 — Tính TCO với rủi ro

Dùng ít nhất:

- **Base**: traffic/log/seat bình thường.
- **Peak**: seasonal demand và attack/incident data volume theo contract.
- **Failure**: outage, premium response, failover, retained on-call và IR.
- **Exit**: export/policy translation/cert rotation/cutover/retention.

Giữ currency, horizon, unit prices, rate assumptions, tax/discount conventions nhất quán. Nếu không có giá/contract thật, ghi **estimate/unknown**, không tự đặt "giá thực tế".

### Bước 6 — Chấm điểm và kiểm tra độ nhạy

Chọn weights theo business criticality, ghi nguồn điểm (vendor demo/independent tests/internal measurements). Nếu một option chỉ dẫn đầu khi giả định ít chắc chắn, yêu cầu **pilot để giảm uncertainty**.

### Bước 7 — Pilot giới hạn, có positive/negative tests

Ví dụ:

~~~yaml
# Test plan mẫu, không apply vào system.
pilot:
  allowed_assets:
    - application-lab
    - identity-lab
  traffic:
    production_load_testing: prohibited-without-separate-approval
    rate: low-volume
  measurements:
    - eligible-user-success
    - latency-p95-p99
    - actual-allowed-and-denied-network-flows
    - tls-identity-and-origin-verification
    - management-api-audit-trail
    - telemetry-completeness-and-export
    - estimated-billing-units
  exercises:
    - false-positive-rule-rollback
    - control-plane-unavailable-tabletop
    - alert-triage-escalation
    - evidence-export-and-vendor-exit
  result: pending-execution
~~~

**Không tạo tải DDoS hoặc cố tình outage trên production**. Những tính năng gây thay đổi mạng cần sandbox/canary, maintenance window và phê duyệt. Có thể dùng **contractual evidence, architecture review và disaster tabletop** thay cho fault injection rủi ro cao.

### Bước 8 — Chốt RACI, hợp đồng và SOP

Trước go-live, xác định:

- Rule owner, security accountable owner, application owner.
- Nhiệm vụ provider patch/scale/monitor và support tier.
- On-call pager/escalation khi provider security incident hoặc false positive.
- IAM/SSO/MFA/PAM, service accounts, emergency/break-glass.
- Audit/log retention, raw export, chain of custody và privacy review.
- Policy-as-code/version control/change approval, TTL exceptions, rollback.
- Chi phí/quotas/renewal, exit notices và data deletion requirements.

### Bước 9 — Rollout theo canary, kiểm chứng độc lập

~~~mermaid
flowchart TD
    G["Gates approved + pilot passed"] --> CAN["Canary rollout limited routes/users"]
    CAN --> TEST["Positive/negative tests + user-visible SLI"]
    TEST --> Q{"Healthy and policy correct?"}
    Q -- "Không" --> RB["Approved rollback or safe bypass per policy"]
    Q -- "Có" --> SCALE["Expand to approved traffic segments"]
    SCALE --> OBS["Monitor control/data/logging planes"]
    OBS --> RET["Periodic drift, TCO, contract and exit review"]
~~~

Không bật **unrestricted bypass** khi managed security fails trừ khi threat model cho phép và có compensating controls. Rollback phải được thiết kế trước, không quyết định tùy hứng giữa outage.

### Bước 10 — Review định kỳ và khi có trigger

Một ADR phải được đánh giá lại khi:

- New regulatory/data classification requirements.
- Major traffic/region/protocol expansion.
- Provider outage, compromise, service deprecation hoặc pricing change.
- Significant false positives/negative detection coverage.
- Internal team capabilities hoặc system architecture thay đổi.
- Contract renewal, DR test hoặc failed exit rehearsal.

Ghi **decision history, những giả định đã thay và evidence mới**, tránh mặc định "đã mua thì luôn đúng".

## 29. Ma trận 50 trường hợp kiểm thử lựa chọn managed service

Các test dưới đây là **kế hoạch kiểm chứng**, không phải kết quả thực nghiệm. Chạy positive/negative network flows trong lab/canary được cấp phép; các kịch bản outage/DDoS/compromise nên dùng **tabletop, config review, contract evidence hoặc diễn tập do provider phê duyệt** thay vì gây hại cho production.

| ID | Kiểm thử / mục tiêu | Evidence hoặc phương pháp | Điều kiện PASS |
|---|---|---|---|
| **GATE-01** | Data residency hợp lệ | Data-flow map, DPA, region/sub-processor scope | Không có path trái hard requirement |
| **GATE-02** | Key custody đáp ứng yêu cầu | HSM/KMS/CA access & export model | Không cấp quyền key trái chính sách |
| **GATE-03** | Audit/forensic export được hỗ trợ | Demo xuất evidence theo incident window | Có source fields/timestamps cần thiết |
| **GATE-04** | Network/protocol compatibility | API/IPv6/UDP/OT/mesh matrix | Phạm vi bắt buộc được hỗ trợ |
| **GATE-05** | Availability/failure mode phù hợp | Architecture review/tabletop DR | RTO/SLO/fail mode không trái policy |
| **GATE-06** | Support/incident escalation đủ | Contract, contact drill | Có owner, severity, response scope rõ |
| **GATE-07** | Identity governance/SSO/PAM | Tenant role & break-glass review | Least privilege/MFA/audit áp được |
| **GATE-08** | Exit thực tế khả thi | Test export/cutover/retention | Không có blocker ở requirement bắt buộc |
| **SEC-01** | Allowed network flow | Approved client → app/API | ALLOW + TLS/app success |
| **SEC-02** | Unauthorized lateral flow | Lab non-entitled identity → service | DENY ở đúng PEP |
| **SEC-03** | WAF false-positive protection | Benign test transaction + policy changes | Legitimate traffic vẫn thành công |
| **SEC-04** | WAF/APIs reject disallowed action | Safe lab negative input + audit logs | DENY đúng rule, không chỉ server outage |
| **SEC-05** | Direct-origin bypass prevented | Authorized lab request tới origin path | DENY ngoài approved edge route |
| **SEC-06** | Strict TLS identity across segments | Client→edge và edge→origin checks | SAN/CA/trust chain đạt cả hai |
| **SEC-07** | IPv6/network route parity | IPv4/IPv6 test from permitted vantage | Không có unprotected alternate path |
| **SEC-08** | mTLS/workload authz boundaries | Approved vs unapproved test principals | Identity hợp lệ vẫn bị giới hạn role |
| **SEC-09** | DNS security coverage & bypass | Resolver/DoH/IPv6 config audit | DNS policy applied trong modeled paths |
| **SEC-10** | Vendor privileged access monitored | Scoped role change, audit trail | Phê duyệt, MFA, log và revocation hoạt động |
| **OPS-01** | Patch lifecycle rõ | Vendor/customer RACI and patch record | Không có critical owner gap |
| **OPS-02** | 24/7 support thực thi | Tabletop escalation outside business hours | Contact/ack/escalation theo agreement |
| **OPS-03** | Policy change reproducibility | IaC/API config diff and rollback | Có version, operator và approval |
| **OPS-04** | Rule false-positive rollback | Simulated blocked legitimate request | Restore theo thời gian/RBAC quy định |
| **OPS-05** | Incident triage có chất lượng | Synthetic multi-source event | Dùng asset context, không chỉ raw alert count |
| **OPS-06** | IPS detection vs blocking đúng | Sensor mode and PEP logs | Phân biệt detect-only với enforce |
| **OPS-07** | Containment authorization rõ | Tabletop host/flow isolate request | Không action ngoài delegated authority |
| **OPS-08** | Certificate/PKI renewal continuity | Controlled renewal and served-cert probe | Cert mới serve và trusted trước expiry |
| **OPS-09** | Provider control plane down | Tabletop with blocked management API | Có continuity/response plan |
| **OPS-10** | Identity provider outage recovery | Break-glass drill with proper audit | Access emergency vẫn least privilege |
| **TCO-01** | Baseline cost đủ thành phần | 3-year self/managed/hybrid model | Staff/infra/support/logs/integration có đủ |
| **TCO-02** | Peak traffic scenario | Cost worksheet with peak assumptions | Overage/rate units được định nghĩa |
| **TCO-03** | Log storage/egress growth | Forecast retention/incident spikes | Có alert/cap hoặc risk reserve |
| **TCO-04** | SLA exclusion impact | Contract review + business SLO comparison | Hiểu chênh lệch SLA vs user SLI |
| **TCO-05** | Weighted-score sensitivity | Change weights/uncertain scores | Decision không dựa precision giả |
| **TCO-06** | Failure and exit cost | DR/IR/contract/transition costing | Rủi ro chi phí còn lại có owner |
| **EXIT-01** | Policy/rule export format | Export lab rules to neutral schema | Cần đủ conditions/actions/version |
| **EXIT-02** | Logs/evidence export | Retrieve sample raw+normalized records | Không mất identifiers/UTC dùng cho IR |
| **EXIT-03** | Identity federation portability | Move approved test identity to alternate | Roles/policy mapped and verified |
| **EXIT-04** | DNS/certificate cutover readiness | Lab route and TLS handshake regression | Hostname/CA/TTL/rollback phù hợp |
| **EXIT-05** | Key management separation | KMS/HSM/CA exit plan tabletop | No orphaned trust/secrets; new keys ready |
| **EXIT-06** | Dual-run consistency | Compare same allowed/denied test set | Không policy divergence không giải thích |
| **EXIT-07** | Data deletion/retention after exit | Contract/audit deletion process | Có confirmation và legal hold exceptions |
| **OBS-01** | End-to-end synthetic coverage | Multi-region/identity client probes | Đo đúng business flow, không chỉ edge UP |
| **OBS-02** | No-data health | Simulate missing telemetry in lab | UNKNOWN/coverage alert, không false-green |
| **OBS-03** | WAF/firewall rule evidence | Review allow/deny events | Có rule ID, action, actor, UTC, source |
| **OBS-04** | NAT/VPN/source attribution | Sample mapping records and timestamps | Truy ra đúng asset theo time window |
| **OBS-05** | Logging privacy | Redaction/retention/access review | Không leak raw tokens/PII ngoài scope |
| **OBS-06** | Independent validation | Compare vendor and customer telemetry | Có thể phát hiện false positives/missing requests |
| **OBS-07** | Outage blast radius | Fault-tree/tabletop provider dependency | Common control-plane risk có mitigation |
| **OBS-08** | Capacity limits & sampling | Load profile review, vendor metrics | Biết pps/bps/conntrack/log drop thresholds |
| **OBS-09** | ADR evidence handoff | Independent security/owner review | Quyết định, alternatives, risks, owners rõ |

### 29.1. PASS, FAIL, INCONCLUSIVE và N/A

**PASS**: test được tiến hành trong phạm vi, evidence đủ từ đúng enforcement/observation point, outcome phù hợp policy và có người chịu trách nhiệm xác minh.

**FAIL**: hard gate bắt buộc không đạt, đường trái phép vẫn ALLOW, endpoint hợp lệ bị chặn ngoài ý định, không thể export evidence theo yêu cầu, cost/DR/exit vượt risk tolerance hoặc thiếu permission cho một control thiết yếu.

**INCONCLUSIVE**: không đủ logs, target down, test không vào đúng route, vendor claim chưa kiểm chứng, missing contract terms hoặc chưa biết sampling/clock skew. Không tự chuyển `UNKNOWN` thành PASS.

**N/A**: chỉ khi tiêu chí thật sự không áp dụng và có **lý do đã được owner duyệt**; ví dụ HTTP/3 tests không áp dụng cho dịch vụ chỉ hỗ trợ MQTT/TCP, nhưng IPv6 có thể vẫn liên quan.

### 29.2. Phân biệt bằng chứng kỹ thuật và bằng chứng hợp đồng

Một pilot cho thấy **TLS và app hoạt động** chưa chứng minh vendor đảm bảo đúng **service credit, breach notification hoặc data deletion** trong hợp đồng. Ngược lại có hợp đồng cam kết log export không chứng minh API export trả **đầy đủ trường cần thiết**. Phải dùng hai loại chứng cứ độc lập.

### 29.3. Mẫu kết quả kiểm thử

~~~yaml
test_id: EXIT-02
decision_id: ADR-NETSEC-009
environment: authorized-sandbox
provider_option: managed-option-A
status: pending-execution
owner: security-architecture-team
time_utc: pending
preconditions:
  - approved-test-dataset
  - restricted-evidence-repository
  - provider-export-api-access-approved
expected:
  raw_events_available: true
  normalized_fields_with_action_and-rule_id: true
  original_utc_timestamps_preserved: true
  no_unapproved_personal_data_export: true
evidence_required:
  - export-request-id-and-version
  - data-schema-mapping
  - sample-event-integrity-check
  - ownership-and-permissions-review
result: INCONCLUSIVE_UNTIL_TESTED
~~~

Không ghi kết quả PASS khi mẫu mới là template. Không chép raw log chứa credentials hoặc dữ liệu nhân sự vào bài học/ADR công khai.

## 30. Bài tập áp dụng và đáp án gợi ý

### Bài 1 — Cloud-hosted có luôn managed không?

Doanh nghiệp tự cài và patch firewall trên một VM cloud. Nhà cung cấp quản lý datacenter vật lý. Đây có phải managed firewall đầy đủ?

**Đáp án:** không. Đây thường là **self-managed firewall workload trên cloud infrastructure**. Provider quản lý hạ tầng bên dưới, customer vẫn patch/config/HA/monitor/firewall rule.

### Bài 2 — MSSP có tự được cô lập endpoint?

Hợp đồng ghi "24/7 SOC monitoring", không có delegated containment permissions. MSSP phát hiện host đáng ngờ. Họ có mặc nhiên được quyền isolate host sản xuất không?

**Đáp án:** không. Cần quy định **quyền thực thi và phê duyệt** rõ, kênh escalation và emergency runbook. SOC monitoring không tự tương đương containment authority.

### Bài 3 — SLA vs user SLO

Provider edge có SLA 99,95% nhưng origin API bị lỗi vì DB down. Khách hàng thấy API availability 96%. Provider có mặc nhiên vi phạm SLA edge?

**Đáp án:** không. Phải xem boundary/terms của SLA; **user SLI** có thể fail do dependency ngoài scope provider.

### Bài 4 — Time-based budget

SLO 99,9% time-based trong 30 ngày (43.200 phút) cho phép bao nhiêu phút gián đoạn theo mô hình đơn giản?

**Đáp án:** \((1-0{,}999)\times43.200=43{,}2\) phút. Không trộn với request-based error budget.

### Bài 5 — Hard gate

Provider A có tổng score 4,8/5 nhưng không cho export logs trong kỳ legal hold bắt buộc. Provider B score 3,9/5 và đáp ứng gate. Có thể chọn A vì điểm cao hơn không?

**Đáp án:** không nếu log export là **hard gate**. A phải sửa điều khoản/thiết kế để đạt gate trước khi vào vòng so điểm.

### Bài 6 — Weighted score

Với weights security 50%, availability 30%, TCO 20%, một option đạt 4, 5, 3 điểm trên thang 1–5. Điểm tổng là bao nhiêu?

**Đáp án:** \(0{,}5(4)+0{,}3(5)+0{,}2(3)=4{,}1\). Cần nêu rằng weight và điểm do decision owners đặt, không phải chứng minh phương án thật.

### Bài 7 — TCO tăng đột biến

Managed A dự toán 760 triệu/năm, self-managed 850 triệu. Usage/egress của managed tăng thêm 150 triệu do peak. So sánh lại.

**Đáp án:** managed thành **910 triệu/năm**, cao hơn self-managed **60 triệu** trong scenario này. Kết luận còn phụ thuộc security outcome và expected losses.

### Bài 8 — Volumetric DDoS tại on-prem

Một firewall on-prem đủ CPU/pps nhưng uplink Internet chỉ 1 Gbit/s và đang bị flood vượt capacity. Tăng số core firewall có chắc giải quyết được không?

**Gợi ý:** không. Đường truyền bị nghẽn **trước firewall**; nên đánh giá upstream/cloud/ISP mitigation và origin route protection.

### Bài 9 — Managed WAF bảo vệ đúng domain nhưng origin mở

Public site qua WAF báo 100% traffic được lọc, nhưng attacker vẫn truy cập được origin public IP. Điều gì sai trong kiến trúc?

**Đáp án:** tồn tại **direct-to-origin bypass**; cần enforce origin chỉ nhận approved path và xác minh route/TLS, không chỉ tin dashboard edge.

### Bài 10 — False positive

WAF managed chặn 10.000 bot requests nhưng 5% người dùng hợp lệ không checkout được. Có được coi WAF thành công chỉ vì số block lớn?

**Đáp án:** không. Cần đo eligible-user success, rule IDs và false-positive impact, rollback/tuning hẹp.

### Bài 11 — DNS authoritative và DNS security

Doanh nghiệp mua managed authoritative DNS. Nó có mặc nhiên ngăn máy nhân viên truy cập phishing sites không?

**Đáp án:** không. Authoritative hosting khác **recursive DNS filtering**; cần thiết kế endpoint/resolver security riêng.

### Bài 12 — DoH

Network team triển khai DNS filtering nhưng browsers dùng DoH ngoài tổ chức. Filter logs ghi rất ít queries. Có thể kết luận người dùng không truy vấn domain nào không?

**Gợi ý:** không. Kiểm tra managed browser/resolver policy, encrypted DNS paths, cache và logging coverage.

### Bài 13 — Managed PKI

Provider tự renew certificate, nhưng LB vẫn trình cert cũ đã hết hạn. Managed issuance có đủ để nói mTLS/HTTPS healthy không?

**Đáp án:** không. Phải test **served cert** và đường trust/rotation/reload ở đúng TLS termination point.

### Bài 14 — Client certificate và authorization

Hai microservices có client cert từ cùng CA. Service A có được gọi mọi API của Service B chỉ vì mTLS PASS không?

**Đáp án:** không. Identity được xác minh chưa thay business authorization; cần resource/action policies.

### Bài 15 — Managed VPN

VPN tunnel healthy nhưng ứng dụng private không gọi được do route/ACL sai. Có thể báo private access SLI 100% không?

**Đáp án:** không. Cần synthetic **application journey** từ approved identity và xem DNS/routes/firewall/app outcome.

### Bài 16 — SOC báo alert nhưng không chặn

MSSP dùng IDS passive, gửi 200 alerts. Có thể kết luận 200 packets độc hại đã bị chặn không?

**Đáp án:** không. IDS detection-only khác IPS inline. Xác minh sensor mode và independent PEP actions.

### Bài 17 — Data residency

Provider có tùy chọn "store data in Region X", nhưng support tickets chứa unredacted customer logs được xử lý ở region khác. Có thể đánh dấu residency PASS không?

**Gợi ý:** chưa. Phải xét **toàn bộ data flows, support access, backups, sub-processors và contract** theo yêu cầu áp dụng.

### Bài 18 — Control plane outage

WAF edge vẫn phục vụ traffic nhưng provider API không hoạt động, đội SOC không deploy emergency rule được. Những năng lực nào bị ảnh hưởng?

**Gợi ý:** **control-plane/change management** bị ảnh hưởng dù data plane có thể đang up; cần continuity, escalation và risk acceptance.

### Bài 19 — Fail-open

Khi cloud SWG outage, client tự truy cập Internet trực tiếp để tránh outage. Hành vi này luôn tốt không?

**Đáp án:** không. Có thể bypass inspection/zero trust; cần quyết định fail-open/closed theo threat model và business/safety requirements.

### Bài 20 — Vendor concentration

DNS, WAF, DDoS, logging và identity console đều phụ thuộc cùng một provider control plane. Có thể gọi đây là năm lớp độc lập không?

**Đáp án:** không. Có **correlated failure domain**; cần fault tree, exit/failover và phân tích common dependencies.

### Bài 21 — Multi-provider DNS

Hai DNS providers phục vụ cùng zone nhưng automation chỉ cập nhật một bên. Đây là high availability tốt không?

**Gợi ý:** chưa. Record divergence, DNSSEC signing/delegation consistency và stale routes có thể tạo outages; cần đồng bộ/test.

### Bài 22 — OT offline hard gate

Managed proxy yêu cầu mọi PLC traffic đi qua cloud, trong khi plant phải tiếp tục vận hành khi Internet down. Có nên chấp nhận vì vendor có nhiều signatures?

**Đáp án:** không nếu offline survivability là hard gate; xem local enforcement/passive sensor và approved telemetry hybrid.

### Bài 23 — Exit thực chất

Managed WAF cung cấp API export ra JSON nhưng rules dùng DSL độc quyền, không thể import vào target khác và không có regression suite. Có thể ghi "portable" không?

**Đáp án:** chưa. Cần policy intent mapping, lab import, ALLOW/DENY comparison và cutover/rollback test.

### Bài 24 — No-data

Provider SOC dashboard báo zero incidents nhưng log forwarder đã ngừng từ ba ngày trước. Có nên coi hệ thống an toàn?

**Đáp án:** không. Cần telemetry coverage/heartbeat, `UNKNOWN`, alert mất dữ liệu và điều tra lỗ hổng quan sát.

### Bài 25 — Kiến trúc tổng hợp

Một doanh nghiệp có **public API**, **nhân viên remote**, **factory OT** và **cloud/Kubernetes microservices**. Hãy xây ADR cho managed vs self-managed vs hybrid với:

- Ít nhất **7 hard gates**.
- **6 tiêu chí chấm điểm** và nguồn evidence.
- TCO 3 năm với 3 kịch bản base/peak/outage.
- **4 positive flows và 6 negative flows**.
- RACI và on-call/escalation.
- Một **exit drill** với logs/rules/trust và hồi quy an ninh.

**Gợi ý:** public API có thể shortlist managed edge DDoS/WAF, remote access cân nhắc managed ZTNA với IdP/least privilege của khách hàng, OT ưu tiên local safety controls, cloud workloads dùng cloud-managed infrastructure nhưng kiểm soát NetworkPolicy/mTLS/app authz nội bộ. Mọi lựa chọn phải **PASS hard gates và được kiểm chứng theo đúng workload**, không kết luận chung một provider tốt cho mọi hệ thống.

## 31. Checklist quyết định managed vs self-managed vs hybrid

### 31.1. Context và threat model

- [ ] Có **business service owner, security accountable owner, criticality, scope và ADR ID**.
- [ ] Đã xác định **assets, user journeys, threats, data sensitivity, network trust zones và attack paths**.
- [ ] Đã mô hình hóa **east–west, north–south, edge, VPN, DNS, IPv4/IPv6, cloud/OT paths**.
- [ ] Có **SLI/SLO/RTO/RPO** hoặc yêu cầu availability/safety phù hợp với loại dịch vụ.
- [ ] Đã phân biệt **managed infrastructure, managed security platform, MSSP, SaaS và co-managed**.
- [ ] Biết ai **sở hữu policy, quyết định risk acceptance, cấp quyền, deploy và rollback**.

### 31.2. Hard gates

- [ ] Data residency, contract, privacy, sub-processors và support access đáp ứng **quy định áp dụng**.
- [ ] Protocol/traffic/throughput/pps/latency/IPv6 requirements được hỗ trợ.
- [ ] Đã kiểm tra nhà cung cấp có đáp ứng **offline survivability/safety** nếu bắt buộc.
- [ ] Key/certificate custody, CA trust, SSO/MFA/PAM và break-glass phù hợp.
- [ ] Raw audit/flow logs, source IDs, rule IDs và forensic evidence export đáp ứng kỳ hạn điều tra.
- [ ] Provider data/control/management plane outage behavior được phân tích.
- [ ] Hỗ trợ incident escalation, bảo quản bằng chứng và thông báo sự cố đáp ứng yêu cầu.
- [ ] Quyền kiểm toán và phạm vi certifications phù hợp **đúng sản phẩm/region** chứ không chỉ tổ chức provider.
- [ ] TCO/contract/exit không vượt risk appetite hoặc có risk acceptance chính thức.
- [ ] `PENDING/UNKNOWN` cho gate bắt buộc không được tự coi như `PASS`.

### 31.3. Technical coverage và bảo mật vận hành

- [ ] Firewall/IPS/WAF enforcement được xác minh tại **đúng PEP**, không chỉ UI configured.
- [ ] Lưu lượng được phép **vẫn chạy**, trái policy **thực sự bị từ chối** bằng evidence phù hợp.
- [ ] Có kiểm soát **direct-to-origin bypass, alternative route, IPv6, VPN/DoH/QUIC paths** theo threat model.
- [ ] TLS, certificate SAN/CA, edge→origin verification và mTLS identity đúng từng segment.
- [ ] Application authorization riêng không bị nhầm với network access hoặc mTLS authentication.
- [ ] IDS detect-only không bị báo thành enforcement, WAF block counts không bị nhầm hiệu quả kinh doanh.
- [ ] DNS authoritative/recursive/filtering được phân biệt, có trust/logging/false-positive coverage.
- [ ] Managed PKI không bỏ qua **issued vs served cert, expiry, rotation và client truststore**.
- [ ] Cloud/Kubernetes/service mesh coverage được xác minh trên thực tế, không chỉ resource YAML tồn tại.
- [ ] Không để provider privileges hoặc tenant support sessions vượt least privilege.

### 31.4. Performance, resilience, monitoring

- [ ] Có baseline cho **latency p95/p99, successful throughput, errors và user-visible availability**.
- [ ] Có đo packet rate/connection rate/conntrack/queue và capacity, không chỉ bps.
- [ ] Fail-open/closed và bypass policy được mô tả trước, có compensating controls khi cần.
- [ ] Provider multi-region/failover claims có evidence/thí nghiệm không gây hại.
- [ ] Đã phân tích **common dependencies/correlated failure domains** và vendor concentration.
- [ ] Có alert **no-data/telemetry coverage**, tránh dashboard xanh giả khi logs mất.
- [ ] Audit và incident events có timestamp UTC, source/identity, policy revision và correlation.
- [ ] Có export logs để **SOC nội bộ kiểm chứng độc lập**, không chỉ provider summary.
- [ ] Có plan khi SSO/control plane/log plane hoặc certificate renewal unavailable.

### 31.5. TCO và commercial risk

- [ ] So same-scope **self-managed, managed, hybrid và baseline status quo**.
- [ ] Dự toán 3–5 năm bao gồm staff, patch/HA/DR, licenses, support, integration, telemetry và IR.
- [ ] Managed usage units/quotas/overages, log export và network egress costs được đọc trong contract.
- [ ] Có các kịch bản **base/peak/incident/failure/exit**, không dùng duy nhất con số bình quân.
- [ ] Nêu assumptions, currency, inflation/tax/NPV khi cần và tránh double counting.
- [ ] Chấm điểm chỉ **sau hard gates** và sensitivity analysis đã được xem xét.
- [ ] SLA/SLO và service credit có boundary/exclusions rõ; không suy credit bù outage hoàn toàn.

### 31.6. Vendor governance, portability và IR

- [ ] Hợp đồng có RACI/SLAs với **incident severity, notification, triage, remediation, escalation**.
- [ ] Có role-based control và audit cho rule changes, certificate/key actions, routing và DNS.
- [ ] Policy-as-code hoặc config export được **version và review** với approval/rollback.
- [ ] Có TTL/owner cho exceptions và emergency changes; không để bypass tồn tại vô thời hạn.
- [ ] Có kế hoạch **vendor compromise**: revoke support access, rotate credentials, verify rules/routes.
- [ ] Có **exit plan** cho DNS, WAF rules, security policies, logs, identity, certificates và monitoring.
- [ ] Đã diễn tập một **policy/log export → target import → regression tests**.
- [ ] Có retention, key/data deletion and legal hold handling sau khi kết thúc hợp đồng.
- [ ] Có ngày review ADR, trigger xem lại và owner cho residual risks.

### 31.7. Dấu hiệu không nên ký go-live

Một option **chưa đủ điều kiện triển khai** khi có một trong những tình huống nghiêm trọng:

- Không có cơ sở xử lý/chuyển dữ liệu hợp pháp theo yêu cầu đã xác định.
- Không ai chịu trách nhiệm xử lý một firewall rule sai vào giờ cao điểm.
- Nhà cung cấp chỉ có "green dashboard" mà không cung cấp logs cần cho IR.
- Dịch vụ không có cách khôi phục khi control plane/SSO bị lỗi, dù hệ thống là critical.
- Muốn đưa dịch vụ online phải **tắt TLS certificate verification** hoặc mở origin trực tiếp.
- Chưa biết billing units trong trường hợp attack traffic spike.
- Không có phương án thu hồi vendor access/khôi phục policies sau compromise.
- Không xuất được config/identities/evidence theo yêu cầu bắt buộc.
- Chưa kiểm tra positive and negative flows từ đúng user/route/identity.

**Kết luận:** Managed service nên được chọn **khi dịch vụ mang lại năng lực bảo mật và vận hành mà tổ chức khó hoặc không hợp lý khi tự xây**, đồng thời **hard gates, chất lượng kiểm soát, quan sát, chi phí và quyền rút lui** đều đáp ứng bằng chứng. Self-managed phù hợp hơn khi cần kiểm soát sâu, vận hành offline, giao thức đặc thù và có đội ngũ đủ năng lực; hybrid thường hữu ích để kết hợp capacity/automation của provider với **policy, dữ liệu, danh tính và trách nhiệm rủi ro** do khách hàng giữ. Không có một nhãn "managed" nào thay được **threat model, shared responsibility, kiểm thử ALLOW/DENY và ADR có chủ sở hữu**.

## 32. Tài liệu chuẩn và đọc thêm

Các tài liệu sau là **nguồn tham khảo định hướng phương pháp**; không thay hợp đồng, tài liệu phiên bản hiện hành của dịch vụ cụ thể hoặc đánh giá pháp lý theo địa phương. Mỗi provider có service scopes và trách nhiệm khác nhau.

### 32.1. Quản trị rủi ro, zero trust, shared responsibility

- [NIST Cybersecurity Framework (CSF) 2.0](https://www.nist.gov/cyberframework): quản trị rủi ro, xác định, bảo vệ, phát hiện, ứng phó và khôi phục.
- [NIST SP 800-53 Rev. 5 — Security and Privacy Controls](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final): kiểm soát kỹ thuật và quy trình cho hệ thống thông tin.
- [NIST SP 800-207 — Zero Trust Architecture](https://csrc.nist.gov/pubs/sp/800/207/final): policy decision/enforcement, identity và least privilege.
- [NIST SP 800-30 Rev. 1 — Guide for Conducting Risk Assessments](https://csrc.nist.gov/pubs/sp/800/30/r1/final): đánh giá threat/likelihood/impact và giới hạn của nhận định rủi ro.
- [Cloud Security Alliance — Cloud Controls Matrix](https://cloudsecurityalliance.org/research/cloud-controls-matrix): đối chiếu kiểm soát cloud và shared responsibility.
- [AWS — Shared Responsibility Model](https://aws.amazon.com/compliance/shared-responsibility-model/): ví dụ cách nhà cung cấp cloud phân chia trách nhiệm theo dịch vụ.
- [Microsoft Azure — Shared responsibility in the cloud](https://learn.microsoft.com/en-us/azure/security/fundamentals/shared-responsibility): kiểm soát và trách nhiệm khác nhau giữa các mô hình cloud.
- [Google Cloud — Shared responsibility and shared fate](https://cloud.google.com/architecture/framework/security/shared-responsibility-shared-fate): mô hình trách nhiệm và thực thi bảo mật cloud.

### 32.2. Mạng, DDoS, DNS, certificate và telemetry

- [NIST SP 800-41 Rev. 1 — Guidelines on Firewalls and Firewall Policy](https://csrc.nist.gov/pubs/sp/800/41/r1/final): nguyên tắc lập chính sách và vận hành firewall; đọc cùng hướng dẫn hiện hành.
- [NIST SP 800-52 Rev. 2 — Guidelines for TLS Implementations](https://csrc.nist.gov/pubs/sp/800/52/r2/final): TLS configuration và policy assessment.
- [NIST SP 800-81 Rev. 2 — Secure Domain Name System (DNS) Deployment Guide](https://csrc.nist.gov/pubs/sp/800/81/r2/final): DNS deployment/trust và vận hành.
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446): TLS handshake, peer authentication và protected transport.
- [RFC 9525 — Service Identity in TLS](https://www.rfc-editor.org/rfc/rfc9525): hostname/certificate identity verification.
- [Kubernetes — Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/): cách enforcement và giới hạn CNI/NetworkPolicy.
- [OWASP — Web Application Firewall](https://owasp.org/www-community/Web_Application_Firewall): vai trò của WAF trong defense-in-depth.
- [Prometheus — Monitoring Distributed Systems / SRE](https://sre.google/sre-book/monitoring-distributed-systems/): mô hình availability, latency, traffic, errors và monitoring quality.

### 32.3. Vận hành, sự cố, chi phí, hợp đồng và portability

- [NIST SP 800-61 Rev. 3 — Incident Response Recommendations](https://csrc.nist.gov/pubs/sp/800/61/r3/final): incident coordination và recovery planning.
- [NIST SP 800-137 — Information Security Continuous Monitoring](https://csrc.nist.gov/pubs/sp/800/137/final): đo và giám sát security controls.
- [NIST SP 800-86 — Integrating Forensic Techniques into Incident Response](https://csrc.nist.gov/pubs/sp/800/86/final): thu thập/chứng minh evidence và chain of custody.
- [FinOps Foundation — Framework](https://www.finops.org/framework/): quản trị chi phí cloud/usage, ownership và tối ưu theo mục tiêu.
- [OpenTelemetry — Concepts](https://opentelemetry.io/docs/concepts/): telemetry portability và cấu trúc dữ liệu quan sát.
- [CISA — Zero Trust Maturity Model](https://www.cisa.gov/zero-trust-maturity-model): định hướng tổ chức bảo vệ identity, networks, workloads và data.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): structured evidence, bảo vệ dữ liệu và logging security.
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): bảo vệ và rotation keys/tokens/credentials.

