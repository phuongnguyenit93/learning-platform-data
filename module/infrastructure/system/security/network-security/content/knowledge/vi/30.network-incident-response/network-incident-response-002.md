# Triage cảnh báo lưu lượng bất thường

**Triage cảnh báo lưu lượng bất thường** là quá trình tiếp nhận, xác minh, bổ sung ngữ cảnh và ưu tiên xử lý những tín hiệu mạng khác lệ thường hoặc vi phạm chính sách. Mục tiêu ban đầu **không phải khẳng định chắc chắn có tấn công**, mà là nhanh chóng trả lời: *Cảnh báo dựa trên bằng chứng gì? Luồng có thực sự xảy ra không? Nguồn và đích là ai? Có rủi ro đối với hệ thống hoặc dữ liệu nào? Bước an toàn tiếp theo là gì?*

Ví dụ, hệ thống giám sát phát hiện máy chủ ứng dụng truyền **1,2 GB qua HTTPS** trong một giờ, gấp nhiều lần baseline. Đây có thể là xuất dữ liệu trái phép, nhưng cũng có thể là backup được duyệt, phát hành artifact, đồng bộ báo cáo hoặc sự thay đổi của proxy/NAT làm số đếm khác đi. Một SOC analyst cần kiểm tra **chiều truyền, nguồn tiến trình, địa chỉ sau NAT, tài khoản đích, lịch công việc và quyền của chủ thể** trước khi phân loại.

Trong chương **Ứng phó sự cố mạng** thuộc module **SECURITY_NETWORK_SECURITY**, bài học kết nối telemetry, packet capture, IDS/IPS, firewall, phân đoạn mạng, VPN/ZTNA, DNS, TLS, cloud/Kubernetes và kiểm soát egress. Đây là **bước ra quyết định có cấu trúc** giữa một detector và hoạt động incident response, không phải cuộc săn tìm mọi dấu hiệu đáng ngờ bằng mọi giá.

> **Nguyên tắc:** Một **alert** là giả thuyết cần kiểm tra; một **observable** là dữ kiện được sensor ghi nhận; một **incident** là sự kiện hoặc tập sự kiện được xác định có ảnh hưởng/đe dọa cần ứng phó theo tiêu chí của tổ chức. Đừng dùng ba khái niệm này thay nhau.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Trình bày mục tiêu, đầu vào, đầu ra và các quyết định của **network security alert triage**.
2. Phân biệt **anomaly, detection, false positive, true positive, benign true positive, incident** và giới hạn bằng chứng.
3. Đọc các trường cốt lõi của **firewall, NetFlow/IPFIX, IDS/IPS, DNS, proxy, TLS, VPN/ZTNA, EDR, cloud và Kubernetes**.
4. Xác định **5-tuple, directionality, NAT, DHCP, identity, workload, thời gian và sensor placement** để tránh gán nhầm nguồn.
5. Dùng **baseline theo ứng dụng, vai trò, thời điểm và kỳ vận hành** thay vì một ngưỡng cố định.
6. Đánh giá riêng **mức độ chắc chắn (confidence)** và **mức độ ưu tiên/tác động (severity/priority)**.
7. Triage những nhóm phổ biến: **scan, kết nối lặp/beacon-like, DNS bất thường, HTTPS upload, lateral movement, traffic spike và DDoS**.
8. Thu thập chứng cứ tối thiểu, bảo toàn nguyên bản và quản lý **chain of custody** khi cần.
9. Đưa ra quyết định **đóng cảnh báo, theo dõi, điều tra sâu, chuyển cấp hoặc containment** với quyền hạn rõ ràng.
10. Dùng playbook, log mẫu, truy vấn phân tích và bộ kiểm thử synthetic để đánh giá chất lượng triage.

## 2. Alert triage nằm ở đâu trong vòng đời ứng phó?

Một vòng đời thực hành thường gồm **chuẩn bị → phát hiện/tiếp nhận → triage/xác minh → phân tích sâu → containment → loại bỏ nguyên nhân/phục hồi → lessons learned**. Những giai đoạn có thể chồng lấn, và containment khẩn cấp có thể được kích hoạt trước khi phân tích đầy đủ khi rủi ro rõ ràng và có thẩm quyền.

~~~mermaid
flowchart TD
    A["Detector / user report / vendor alert"] --> B["Intake: validate source & timestamp"]
    B --> C["Normalize evidence + deduplicate"]
    C --> D["Enrich: asset, identity, topology, baseline"]
    D --> E{"Enough reliable evidence?"}
    E -->|"Không"| F["Collect bounded evidence / mark unknown"]
    F --> D
    E -->|"Có"| G{"What is the risk and impact?"}
    G -->|"Benign/known authorized"| H["Close with rationale + tuning"]
    G -->|"Unclear but meaningful"| I["Monitor or escalate investigation"]
    G -->|"Credible active threat"| J["Escalate / authorized containment"]
    H --> K["Case record + feedback"]
    I --> K
    J --> K
~~~

### 2.1. Triage khác hunting và forensic investigation

| Hoạt động | Câu hỏi | Kỳ vọng đầu ra |
| --- | --- | --- |
| **Detection** | Có tín hiệu phù hợp luật/thống kê không? | Alert chứa observable và rule |
| **Triage** | Alert đáng tin/cần xử lý gấp không? | Classification, confidence, priority, owner, next action |
| **Threat hunting** | Có hành vi chưa bị detector nhận diện không? | Giả thuyết, truy vấn, findings hoặc detection mới |
| **Incident investigation** | Điều gì xảy ra, phạm vi/tác động đến đâu? | Timeline, affected assets, attack path, evidence |
| **Containment/remediation** | Giảm tác động và xử lý nguyên nhân bằng cách nào? | Thay đổi được phê duyệt, xác minh, rollback |
| **Content tuning** | Luật cảnh báo cần cải thiện thế nào? | Rule version, tests, coverage metrics |

**Triage không phải forensic attribution về con người hoặc động cơ.** Một kết nối tới một địa chỉ có uy tín xấu không đủ xác định người dùng cố ý liên quan đến hành vi đó.

### 2.2. Những kết quả triage có thể chấp nhận

- **Confirmed benign/authorized:** tín hiệu thật nhưng là workflow hợp lệ có bằng chứng.
- **False positive/detection error:** luật, dữ liệu hoặc normalization sai.
- **Suspicious, needs investigation:** chưa đủ để kết luận nhưng có rủi ro đáng kể.
- **Likely/confirmed incident:** đủ bằng chứng theo tiêu chí tổ chức để kích hoạt response.
- **Insufficient visibility:** không quan sát được field quan trọng; tạo nhiệm vụ bổ sung telemetry.
- **Duplicate/related to existing case:** gộp để tránh phản ứng lặp.

**Thiếu bằng chứng không phải bằng chứng an toàn.** Đóng case vì “không có dữ liệu” chỉ phù hợp khi chính sách quy định và đã ghi rõ giới hạn quan sát/rủi ro.

## 3. Các loại lưu lượng bất thường và giả thuyết đối lập

| Tín hiệu | Giả thuyết đáng ngờ | Giả thuyết hợp lệ cần loại trừ |
| --- | --- | --- |
| Nhiều kết nối đến nhiều ports/hosts | Reconnaissance/lateral movement | Vulnerability scanner có ticket, monitoring |
| Lưu lượng outbound cao | Data exfiltration | Backup, replication, artifact publish |
| Nhiều inbound requests/TCP SYN | DoS/DDoS | Campaign, load test được duyệt, client retries |
| Kết nối định kỳ tới domain lạ | Beaconing | Health check, telemetry agent, license check |
| DNS queries tăng đột biến | DNS abuse/tunneling | Resolver loop, search-domain/ndots, retry |
| TCP resets hoặc retransmissions nhiều | Chặn/gián đoạn do tấn công | Packet loss, MTU, backend overload |
| Internal SSH/RDP/SMB tăng | Lateral movement | Admin patching, inventory/backup |
| VPN/ZTNA session từ ngữ cảnh mới | Account misuse | Đi công tác, đổi ISP, roaming |
| HTTPS tới cloud host mới | C2/exfil hoặc app mới | CDN shift, SaaS rollout, OS update |
| IPv6 traffic mới không qua proxy | Unmonitored egress | Dual-stack enablement có change ticket |

Triage tốt **đặt ít nhất một giả thuyết lành tính bên cạnh giả thuyết đe dọa** và tìm dữ liệu có khả năng phân biệt chúng. Không phải để hạ mức độ cảnh giác, mà để tránh hành động sai từ detector đơn tín hiệu.

### 3.1. Phân loại theo trục

- **Hướng:** inbound, outbound, east–west, host-to-pod, SaaS-to-SaaS.
- **Tầng:** L3/L4 flow, DNS, TLS, HTTP/API, ứng dụng/dữ liệu.
- **Phạm vi:** một thiết bị, một user, một workload, cả subnet/region hoặc cluster.
- **Tính liên tục:** bùng nổ đột ngột, định kỳ, kéo dài, lặp trong nhiều ngày.
- **Tác động:** availability, confidentiality, integrity, identity compromise hoặc policy gap.

Một đột biến traffic nội bộ tới database có thể quan trọng hơn một lượng lớn CDN traffic Internet thông thường, tùy dữ liệu và tài sản liên quan.

## 4. Intake: chuẩn hóa một cảnh báo ngay lúc tiếp nhận

Một alert không nên chỉ chứa dòng “Possible attack: high traffic”. Ít nhất phải có **định danh sự kiện, detector/rule, khoảng thời gian, nguồn/đích, loại quan sát, ngưỡng, mức độ tin cậy và liên kết tới evidence gốc**.

### 4.1. Mẫu alert giả lập

~~~json
{
  "event_type": "network_anomaly_alert",
  "synthetic": true,
  "alert_id": "LAB-NET-00042",
  "detected_at": "2026-11-28T02:18:10Z",
  "window_start": "2026-11-28T02:00:00Z",
  "window_end": "2026-11-28T02:15:00Z",
  "rule_id": "large-outbound-deviation-v3",
  "sensor": "lab-egress-flow-collector-01",
  "source_ip_before_nat": "10.20.4.17",
  "source_port_before_nat": 51243,
  "destination_ip": "203.0.113.42",
  "destination_port": 443,
  "transport": "TCP",
  "observed_client_to_server_bytes": 1288490188,
  "flow_direction_verified": true,
  "baseline_p95_bytes": 134217728,
  "device_id": null,
  "user_id": null,
  "http_payload_observed": false,
  "data_classification": "unknown",
  "initial_priority": "medium",
  "notes": "Example-only address and synthetic measurements"
}
~~~

Địa chỉ **203.0.113.42** thuộc dải TEST-NET dành cho tài liệu; **không phải một đích Internet có thật cần kiểm tra**. Số lượng byte minh họa và chưa nói được dữ liệu đã chuyển thành công, người thực hiện, ứng dụng hay loại payload.

### 4.2. Các kiểm tra đầu tiên

1. Alert do **sensor/detector đáng tin** tạo? Có vấn đề parser hoặc deployment mới không?
2. Timestamp ở **UTC hay local**, collector có time drift không?
3. Source IP là **trước hay sau NAT**, pod IP hay node/public IP?
4. Alert cho biết **observed bytes hay estimated/sample-weighted bytes**?
5. Source/destination “client” được hiểu theo **session originator** hay interface traffic direction?
6. Event có trùng với case khác, một scan được phê duyệt hoặc maintenance window không?
7. Có **asset criticality, business owner và sensitivity** của hệ thống chưa?
8. Có dấu hiệu dịch vụ đang gián đoạn hoặc data access đang tiếp tục không?

### 4.3. Không tin mức severity của vendor như quyết định cuối

Một rule có severity **High** vì số lượng connections có thể là backup; một rule severity **Low** đến database chứa secrets lại có thể cần ưu tiên cao. **Giữ nguyên vendor severity làm dữ liệu đầu vào**, nhưng tạo **triage priority** dựa trên bằng chứng và bối cảnh.

## 5. Telemetry sources: mỗi nguồn thấy gì?

| Nguồn | Có thể biết | Không nên suy ra |
| --- | --- | --- |
| **NetFlow/IPFIX/sFlow** | Endpoint IP/ports, flow metrics, protocol, sampling | HTTP URL/payload/user chắc chắn |
| **Firewall/NAT** | Allow/deny, translation, session, zone | Transfer file hoặc application auth hoàn tất |
| **IDS/IPS/NDR** | Signature/anomaly, packet fields, alerts | Một signature match luôn là incident |
| **PCAP** | Packet headers và plaintext nếu có quyền/capture point | Luôn đọc được TLS 1.3 encrypted payload |
| **DNS resolver** | Query, RCODE, DNS response, resolver/source | DNS query nghĩa là đã kết nối |
| **Proxy/SWG** | CONNECT, host/URL/HTTP method khi quan sát, user, policy | CONNECT-only log luôn thấy HTTPS body |
| **TLS metadata** | Handshake/version/SNI khi không bị che, timing | Luôn thấy server certificate hoặc true SNI |
| **VPN/ZTNA** | Identity/session/device, tunnel/app assignment | Mọi traffic đã đi đúng enforcement path |
| **Endpoint EDR** | Process, parent, network socket, device state | Mọi flow từ NAT chắc chắn thuộc một user |
| **IAM/IdP** | Login/MFA/risk/group/identity changes | Login thành công nghĩa là ứng dụng đã được truy cập |
| **Cloud flow/audit** | Cloud role/ENI/route, object/API actions | Tất cả Pod/application payload |
| **Kubernetes/CNI** | Pod/namespace/node, policy verdict, service routing | Mọi CNI đều thực thi cùng NetworkPolicy |
| **Application/DB** | Request/operation/tenant/object, HTTP status | Packet bị chặn trước ứng dụng |

### 5.1. Đặt sensor ở đâu quyết định giá trị

~~~mermaid
flowchart LR
    EP["Endpoint / EDR"] --> POD["Private service / Pod"]
    POD --> NODE["CNI/node routing"]
    NODE --> NAT["NAT / Firewall"]
    NAT --> PROXY["SWG / Egress gateway if traversed"]
    PROXY --> INTERNET["External destination"]
    DNS["DNS resolver"] -. "Queries" .-> NODE
    DB[("Database audit")] -. "Data reads" .-> POD
    EP -. "Process info" .-> SOC["SIEM"]
    NODE -. "CNI flow/policy" .-> SOC
    NAT -. "Flow/NAT" .-> SOC
    PROXY -. "HTTP/CONNECT if visible" .-> SOC
    DB -. "Business object context" .-> SOC
~~~

Sơ đồ minh họa một số điểm; không phải mọi environment có path **NAT → proxy** theo đúng thứ tự này. Một proxy thường có thể nằm **trước NAT**, hoặc client dùng explicit proxy từ đầu; cloud private endpoint có thể bỏ qua Internet gateway. Vì vậy phải **xác minh actual packet path**, không mặc định sơ đồ là cấu hình của hệ thống.

### 5.2. Sensor blind spots là dữ liệu quan trọng

Không có firewall log có thể do **sampling, logging disabled, IPv6 path, private endpoint, policy bypass hoặc không có traffic**. Khi triage, nên ghi rõ trường nào **observed**, trường nào **inferred**, trường nào **unknown**.

### 5.3. Quy tắc tương quan

Một sự kiện firewall và một sự kiện EDR chỉ được gắn cùng session nếu **source identity/device mapping, thời gian, địa chỉ/port và NAT context** khớp trong sai số được nêu. **Cùng public IP không đủ** để xác định cùng người dùng.

## 6. Baseline: bất thường so với điều gì?

Anomaly không tồn tại độc lập; nó là độ lệch so với một **baseline hoặc policy kỳ vọng**. Một cơ sở dữ liệu có backup 50 GB ban đêm không thể dùng cùng ngưỡng outbound với laptop của nhà thầu chỉ đọc portal nội bộ.

### 6.1. Các chiều baseline

| Chiều | Ví dụ | Tác dụng |
| --- | --- | --- |
| Asset/role | API server, laptop, DNS resolver, CI runner | Mỗi loại có lưu lượng khác |
| Time | Giờ hành chính, cuối tháng, patch Tuesday | Bắt seasonality |
| Destination | Enterprise SaaS, partner API, unknown host | Phân biệt kênh được duyệt |
| Protocol | DNS, HTTPS, SSH, SMB, QUIC | Ý nghĩa của bytes/flows khác nhau |
| Direction | Client→server vs server→client | Phân biệt upload/download |
| Identity/process | Backup service, browser, shell | Biết workflow tạo traffic |
| Deployment/change | Upgrade, release, DR failover | Giải thích spike có owner |
| Network zone | Prod VPC, DMZ, VPN, office | Trust boundary và độ nhạy khác |

### 6.2. Bảng số liệu ví dụ

| Workload | P95 outbound trong 15 phút (giả lập) | Một observation | Cần triage |
| --- | ---: | ---: | --- |
| Sales laptop | 150 MB | 1,2 GB | Đúng user/process/đích/data không? |
| CI artifact publisher | 6 GB | 8 GB | Có release và artifact repo được duyệt không? |
| Backup service | 120 GB | 128 GB | Lịch backup, bucket/role đúng không? |
| DNS resolver | 2 triệu queries | 6 triệu queries | Retry loop, client mới hay abuse? |
| Production API | 20.000 req/s | 32.000 req/s | Marketing launch, retry storm hay overload? |

Các số chỉ phục vụ minh họa; **không phải threshold mặc định**. Detector nên có baseline đủ mẫu, chất lượng timestamp/sampling, version và workflow owners.

### 6.3. Phân biệt volume, frequency và behavior

- **Volume anomaly:** bytes/packets tăng.
- **Frequency anomaly:** nhiều connections/queries/requests bất thường.
- **Distribution anomaly:** nhiều đích/ports/regions mới.
- **Sequence anomaly:** data export, tạo archive, outbound upload nối tiếp.
- **Authorization anomaly:** nguồn không được phép dù số bytes rất nhỏ.

Một secret nhỏ có thể đáng lo hơn nhiều GB video public được xuất bản hợp lệ. Không bắt mọi alert vượt ngưỡng bytes mới được xem xét.

### 6.4. Baseline nhiễm và data drift

Nếu một hành vi không hợp lệ đã xảy ra nhiều tuần, baseline có thể “học” nó thành bình thường. Hãy kết hợp **danh mục tài nguyên được phép, data classification, thay đổi cấu hình có duyệt và rule theo policy**, không chỉ anomaly statistics.

## 7. Confidence, severity, priority và urgency

Một cảnh báo có thể **rất chắc chắn là traffic lạ** nhưng tác động thấp; ngược lại, một quan sát còn thiếu chứng cứ trên hệ thống cực kỳ quan trọng có thể vẫn cần kiểm tra gấp.

### 7.1. Tách ba trục

| Trục | Câu hỏi | Giá trị minh họa |
| --- | --- | --- |
| **Confidence** | Bằng chứng có đáng tin không; có chắc phản ánh hành vi nghi vấn? | Low / Medium / High |
| **Impact / Severity** | Nếu giả thuyết đúng, hệ thống và dữ liệu nào bị ảnh hưởng? | Informational / Low / Medium / High / Critical |
| **Priority / Urgency** | Có cần hành động sớm tới đâu theo playbook và rủi ro đang diễn ra? | P1–P4 theo quy ước nội bộ |

**Không có một bảng ánh xạ chung cho mọi SOC.** Việc cấp P1/P2 hoặc gọi SEV1/SEV2 phải phù hợp định nghĩa, giờ trực, SLA và thẩm quyền ứng phó của tổ chức.

### 7.2. Các tiêu chí tăng priority

- Dấu hiệu **active exploitation, lateral movement** hoặc traffic vẫn đang tiếp tục.
- Nguồn/đích là **identity provider, domain controller, database nhạy cảm, control plane, backup hệ thống hoặc firewall**.
- Có bằng chứng **truy cập dữ liệu Restricted, credential use bất thường, unauthorized role change**.
- Hành vi xuất hiện trên **nhiều endpoints hoặc nhiều vùng mạng** cùng thời gian.
- Có **service degradation, DDoS, mất khả năng truy cập khách hàng**.
- Asset **Internet-facing** hoặc có quyền cao; exploitability cao khi có lỗ hổng tương ứng.
- Dữ liệu chứng cứ độc lập và không nằm trong approved workflow.

### 7.3. Tiêu chí giảm mức ưu tiên hợp lý

- Có **approved change/load test/backup** khớp thời gian, user/service account, đích, protocol và volume.
- Alert là **duplicate của case đã được xử lý**, không có thông tin mới.
- Parser/sensor đã có lỗi confirmed gây duplicate/field swap.
- Traffic tới môi trường lab cô lập, không có quyền tới production và có test owner.

**Không hạ priority chỉ vì IP đích thuộc nhà cung cấp lớn** hoặc traffic đi qua HTTPS hợp lệ.

### 7.4. Ma trận ví dụ

| Confidence | Impact nếu đúng | Trạng thái ban đầu có thể chọn |
| --- | --- | --- |
| Low | Low | Enrich/monitor, chưa containment mạnh |
| High | Low | Xác minh workflow, điều chỉnh rule nếu cần |
| Low | Critical | Triage ưu tiên cao để bổ sung bằng chứng, bảo vệ tài sản |
| High | Critical | Escalate ngay, containment theo playbook/thẩm quyền |
| Medium | High | Investigate bounded, đặt mốc phản hồi và owner |

Một case **Low confidence / Critical impact** không nên bị auto-close; nó đòi **xác minh sớm** chứ không mặc nhiên chặn toàn bộ hạ tầng.

## 8. Quy trình triage 15 phút đầu: ví dụ khung thời gian

**15 phút** ở đây chỉ là **khung luyện tập** để sắp xếp thao tác, không phải SLA bắt buộc hoặc cam kết một incident phải được xử lý xong trong thời gian đó. Với sự cố nghiêm trọng cần tuân thủ escalation SLA thực tế.

### Giai đoạn A – Tiếp nhận và bảo đảm liên lạc

1. Ghi alert ID, source detector, event window, asset/identity ban đầu.
2. Xác định alert là **duplicate, suppression hoặc case có owner chưa**.
3. Xem runbook/criticality của service; nếu có **gián đoạn lớn hoặc dấu hiệu tấn công đang diễn ra**, báo người trực theo quy định.
4. Đặt **case owner**, timestamp và giới hạn phạm vi điều tra.

### Giai đoạn B – Xác minh telemetry

1. Mở record gốc để kiểm tra parser, timezone, bytes direction và field types.
2. Kiểm tra source **pre/post NAT**, IP family, network zone và sensor vantage.
3. Xác định service port/protocol và liệu gói tin có **được chấp nhận hay từ chối**.
4. Kiểm tra baseline theo role và change calendar.

### Giai đoạn C – Enrichment tối thiểu

1. Map IP nguồn tới **asset, owner, device ID, Pod UID hoặc cloud instance** tại **thời điểm xảy ra**, không dùng snapshot hiện tại thay thế vô điều kiện.
2. Map user/service identity từ VPN/IdP/EDR khi có bằng chứng đúng.
3. Xác định đích là internal, SaaS approved tenant, public IP, partner hay unrecognized.
4. Kiểm tra DNS, proxy/TLS metadata và các EDR/IDS findings gần thời điểm đó.

### Giai đoạn D – Quyết định triage ban đầu

Ghi một trong các kết quả:

- **Benign with evidence**: có owner/ticket và luồng khớp.
- **Needs more evidence**: yêu cầu nguồn log hoặc người có quyền.
- **Suspicious escalate**: có dấu hiệu rủi ro đáng kể.
- **Immediate incident response**: thỏa tiêu chí nghiêm trọng theo playbook và thẩm quyền.

Mọi quyết định cần **rationale, observed facts, unknowns, scope, case owner và next review time**. Không cần cố tạo một kết luận cuối ngay khi mới tiếp nhận.

## 9. 5-tuple, directionality và trạng thái kết nối

### 9.1. 5-tuple là gì?

Một flow TCP/UDP thường được nhận diện khái quát bằng:

~~~text
(source_ip, source_port, destination_ip, destination_port, transport_protocol)

Example (fictional):
10.20.4.17:51243 -> 203.0.113.42:443 TCP
~~~

Tùy collector còn có **interface, VLAN/VPC, VRF, zone, direction, flow start/end, TCP flags, packet/byte counters** và NAT fields. Trên IPv6, địa chỉ có thể thay đổi theo cơ chế cấp phát/temporary addresses.

### 9.2. Cần phân biệt connection originator và bytes direction

Flow exporter khác nhau có thể định nghĩa **source/destination theo packet đầu tiên, flow direction hoặc interface observation**. Một counter gọi là **bytes_out** có thể là bytes **ra một interface**, không phải bytes **user upload**.

Để không quy kết sai:

- Đọc schema thực và vị trí sensor.
- Nếu cần upload analysis, tìm **client-to-server bytes** đã xác minh.
- Nếu chỉ biết tổng, ghi **direction unknown**, không tự chia ngược.
- Kiểm tra packet/flow sampling và aggregation.
- Đối chiếu retransmissions, proxy reuse, HTTP/2 multiplexing khi đánh giá volume.

### 9.3. TCP flags và kết nối chưa hoàn thành

| Quan sát | Giải thích có thể | Không được kết luận |
| --- | --- | --- |
| SYN nhiều, SYN-ACK ít | Scan, firewall drop, backend unreachable, SYN flood | Đã đăng nhập hoặc khai thác thành công |
| TCP handshake xong | Đường L4 tới listener hoạt động | HTTP request đã được chấp thuận |
| RST nhiều | App đóng kết nối, firewall, policy, client retries | Mọi RST đều là tấn công |
| Retransmissions tăng | Loss, congestion, path MTU, middlebox | Chắc chắn có malware |
| FIN/ACK đóng bình thường | Connection hoàn tất ở L4 | File upload đã lưu thành công |
| Connections ngắn liên tiếp | Health checks, retries, telemetry, scan | Đó chắc chắn là beacon |

**TCP handshake thành công không chứng minh TLS handshake, authentication hoặc application action thành công**.

### 9.4. UDP và QUIC

UDP không có TCP handshake. Các cảm biến có thể **ước lượng phiên theo timeouts**; một UDP flow không có server response có nhiều cách giải thích. HTTP/3 thường dựa trên QUIC/UDP, nhưng không được đồng nhất mọi UDP 443 với HTTP/3 hoặc malicious traffic.

### 9.5. Return path/asymmetry

Một sensor có thể chỉ nhìn **một chiều** do định tuyến bất đối xứng, load balancing hoặc mirror configuration. Nếu không thấy response, hãy kiểm tra **capture vantage và return route** trước khi kết luận đích không phản hồi.

## 10. NAT, DHCP, VPN và định danh đúng nguồn

### 10.1. Một public IP có thể đại diện hàng nghìn phiên

Ở văn phòng hoặc VPC, nhiều endpoints đi qua **source NAT**. Từ firewall ngoài chỉ thấy cùng một egress IP; để truy nguồn cần **pre-NAT source, translated port, timestamp, zone** và thông tin DHCP/asset.

~~~mermaid
flowchart LR
    A["Laptop A 10.20.4.17"] --> NAT["NAT gateway 198.51.100.10"]
    B["Laptop B 10.20.4.18"] --> NAT
    NAT -->|"198.51.100.10:62011"| X["External 203.0.113.42:443"]
    NAT -. "Translation logs" .-> SOC["SOC correlation"]
    A -. "EDR/device ID" .-> SOC
    B -. "EDR/device ID" .-> SOC
~~~

Địa chỉ công khai trong sơ đồ thuộc các dải TEST-NET dùng minh họa. **Không suy một IP NAT là một user** hoặc coi địa chỉ trước NAT luôn còn được giữ trong cloud flow logs.

### 10.2. DHCP và địa chỉ động

IP **10.20.4.17** hôm nay có thể thuộc máy khác ngày trước. Khi tra DHCP/asset inventory, luôn dùng **time window của alert**, kết hợp MAC/host/device ID khi tin cậy, và cân nhắc MAC randomization.

### 10.3. VPN/ZTNA identity

VPN gateway có thể ánh xạ user với assigned pool IP; ZTNA broker có thể ghi user-resource-session. Nhưng:

- VPN login không tự chứng minh mọi flow từ endpoint đi qua VPN.
- ZTNA allow/deny không tự kiểm soát **đường VPN hoặc public backend khác**.
- Một service account hoặc shared privileged session không nên được gán cho người cụ thể khi chưa có audit phù hợp.

### 10.4. Containers và cloud workload

Pod IP có thể được tái cấp khi Pods thay thế. Cloud autoscaling cũng thay instance/IP. Triage workload nên dùng **Pod UID, namespace, service account, cloud role, ENI/NIC, deployment revision và node**, tùy dữ liệu sẵn có; tránh chỉ ghi địa chỉ IP.

### 10.5. Định danh phải có confidence

| Bằng chứng | Mức tin cậy thường có thể đạt |
| --- | --- |
| Public NAT IP không có mapping | Không đủ xác định người dùng |
| Pre-NAT IP + matching DHCP lease | Gợi ý đúng device tại thời điểm, cần xác minh |
| Device ID + EDR process/socket event | Mạnh hơn về process và endpoint |
| IdP session + VPN assignment + timestamp | Có thể gắn user login và tunnel, không tự gắn mọi packet |
| Pod UID + CNI flow + workload identity | Mạnh hơn về nguồn workload |
| Proxy authenticated user + request ID | Mạnh hơn về request qua proxy, nếu auth chain đáng tin |

Không ép kết luận khi chưa có bằng chứng; ghi **source_identity=unknown** thay vì điền tên người dựa vào một IP dùng chung.

## 11. Triage DNS anomalies

DNS có thể báo sớm những thay đổi bất thường, nhưng **DNS query không đồng nghĩa một kết nối hay dữ liệu chuyển ra ngoài đã xảy ra**.

### 11.1. Triệu chứng thường thấy

- Số lượng truy vấn tăng nhanh hoặc nhiều **NXDOMAIN/SERVFAIL**.
- Nhiều hostname mới, subdomain dài hoặc có tính ngẫu nhiên.
- Resolver queries tới domain thuộc diện cảnh báo uy tín thấp.
- Client hỏi public resolver thay vì resolver được phê duyệt.
- DNS response thay đổi, có dấu hiệu misrouting/cache poisoning trong bối cảnh phù hợp.
- Nhiều queries tới một service sau rollout Kubernetes/ndots/search-domain.

### 11.2. Cần đối chiếu gì?

| Dữ liệu | Mục đích |
| --- | --- |
| Query name/type, RCODE, response timing | Xem mẫu lỗi và domain thực sự được hỏi |
| Source client/device/Pod | Xác định app/process và phiên |
| Resolver config/change logs | Có thay forwarder/search suffix/upstream không? |
| DNS answers và TTL | Liên kết hostname/IP, không suy vĩnh viễn |
| Flow/proxy sau DNS | Client có kết nối thật tới IP/host không? |
| Kubernetes CoreDNS/NodeLocal metrics | Phân biệt search-domain retries và lỗi hạ tầng |
| Approved service catalog | Domain mới có thuộc ứng dụng được cấp không? |

### 11.3. Không dùng độ dài subdomain như chứng cứ duy nhất

Hostname dài có thể đến từ telemetry, CDN, service discovery, tracking có chính sách riêng hoặc một hành vi đáng ngờ. **Cần baseline, process, query frequency, domain ownership và network flow corroboration**. Không mặc nhiên gọi đây là DNS tunneling.

### 11.4. DNS over HTTPS/DoT

Khi client dùng **DoH/DoT**, corporate DNS logs có thể không thấy query. Đây là **visibility gap** hoặc policy exception chứ không tự là bằng chứng ác ý. Kiểm tra approved resolver policy, endpoint agent/proxy observability, IPv4/IPv6 và việc có direct public resolver path không.

### 11.5. Câu hỏi khi phát hiện DNS spike

1. Lỗi RCODE là gì, có upstream outage không?
2. Bao nhiêu clients tham gia?
3. Có thay đổi DNS configuration hoặc ứng dụng?
4. Truy vấn đến domains đã biết và được duyệt không?
5. Có connections/HTTP requests thực tế theo sau không?
6. Chỉ Pod trên một node hay cả cluster?
7. Có tín hiệu EDR/IDS khác cùng thời điểm không?

## 12. Triage HTTPS/TLS anomalies

HTTPS hợp lệ về mật mã không đồng nghĩa hợp lệ về **user/resource authorization**. Nhưng passive network monitoring cũng **không thể mặc nhiên đọc payload HTTPS**.

### 12.1. Các tín hiệu có thể quan sát

- Destination IP/port, flow duration, bytes theo chiều khi có.
- TLS version/handshake features và SNI **nếu không bị che**.
- Domain do managed DNS/proxy ghi nhận, cần mapping theo thời điểm.
- HTTP Host/path/method **chỉ khi có proxy/app observability được phép**.
- EDR process và user context ở endpoint.
- SaaS tenant/account audit và source data events khi tích hợp.

### 12.2. Giới hạn TLS 1.3 và ECH

Trong TLS 1.3, **server certificate được mã hóa ở handshake**; passive observer không có TLS endpoint context không nên tự tuyên bố đã đọc certificate. **Encrypted ClientHello (ECH)** có thể che true target hostname; outer SNI không nhất thiết là ứng dụng thực.

### 12.3. HTTPS upload anomaly

Một flow **1,2 GB outbound** tới cloud provider có thể đáng chú ý. Để triage:

1. Xác minh **client-to-server bytes** và collector sampling.
2. Gắn user/device/process; loại trừ NAT attribution sai.
3. Kiểm tra approved **backup/release/ETL schedule**.
4. Kiểm tra destination **tenant/account**, không chỉ IP/domain.
5. Đối chiếu source **file/DB/object read/export events**.
6. Kiểm tra SaaS audit: upload thành công? Chia sẻ ra ngoài? Bằng quyền nào?
7. Đánh giá application authorization, data classification, người nhận và ticket.

Nếu chỉ có TLS flow metadata, kết luận phù hợp là **unusual encrypted outbound flow** chứ không phải “đã chuyển tài liệu nhạy cảm”.

### 12.4. Repeated short TLS connections

Nhiều TLS sessions ngắn hoặc lặp lại có thể do **browser, retry, health check, telemetry, license check, misconfigured client hoặc beacon-like behavior**. Cần kiểm tra **periodicity, jitter, process lineage, destination stability, response sizes, app owner và related alerts**, không suy chỉ từ “mỗi 60 giây một lần”.

### 12.5. Protocol/port mismatch

Không phải mọi TCP 443 đều là HTTPS, và HTTP/3 thường dùng QUIC/UDP 443. Một detector suy HTTP POST từ cổng 443 là sai nếu không có **HTTP-aware evidence**. Tương tự, không thấy HTTP path ở CONNECT-only proxy log không phải lỗi khi proxy chỉ làm tunnel.

## 13. Triage scan, port sweep và reconnaissance-like alerts

Một cảnh báo scan thường đến từ **nhiều kết nối tới ports/hosts**, tỷ lệ failed handshake cao, tăng số SYN hoặc IDS signature. Nhưng một **vulnerability scanner được ủy quyền, inventory agent, load balancer health check hoặc ứng dụng cấu hình sai** cũng có thể có hình dạng gần giống.

### 13.1. Những metrics cần kiểm tra

| Metric | Hữu ích để | Giới hạn |
| --- | --- | --- |
| Distinct destination IPs | Nhìn mức phân tán theo hosts | Một service discovery tool hợp lệ cũng có thể thử nhiều hosts |
| Distinct destination ports | Nhìn phạm vi nhiều services | Một application dùng port range hợp lệ |
| SYN/SYN-ACK/reset ratios | Đánh giá kết nối hoàn chỉnh | Packet loss/firewall ảnh hưởng |
| Sessions per minute | Phát hiện spike | Job có thể chạy định kỳ |
| Source process/host identity | Liên kết công cụ hoặc user | NAT có thể che nguồn |
| Target asset criticality | Ưu tiên kiểm tra | Không chứng minh khai thác |
| Approved scan ticket/window | Giải thích hành vi hợp lệ | Ticket phải khớp source, scope, thời điểm |

### 13.2. Phân biệt authorized vulnerability scanning

Một công cụ quản lý lỗ hổng hợp lệ nên có **source scanners, target scopes, owner, cửa sổ chạy và change ticket**. Nếu một Pod/endpoint không thuộc scanner inventory xuất hiện với pattern tương tự, vẫn cần triage.

Không mặc định allowlist toàn bộ traffic từ scanner IP: khi scanner bị chiếm quyền hoặc cấu hình target sai, **approved identity + scope + time** mới là bằng chứng phù hợp.

### 13.3. Gợi ý xử lý

1. Xem **source zone, identity, process và owner**.
2. So với scanner change calendar và targets được phê duyệt.
3. Xác định có **successful sessions** tới hosts nhạy cảm không.
4. Đối chiếu EDR/auth logs trên những hosts đích.
5. Nếu có lateral activity và không thuộc kế hoạch, **escalate**.
6. Không tiến hành scan đáp trả hoặc thử khai thác để “xác minh” nếu chưa được cấp quyền.

### 13.4. Phân biệt probe với compromise

Một SYN tới TCP 22 chỉ cho thấy thử kết nối ở L4. Ngay cả khi SSH banner xuất hiện, điều đó không chứng minh đã xác thực hoặc chiếm quyền. Cần **SSH authentication logs, EDR events và account/session evidence**.

## 14. Triage beacon-like traffic và nghi vấn Command-and-Control

**Beacon-like traffic** thường là chuỗi kết nối tới một hoặc một nhóm đích với chu kỳ tương đối ổn định, nhưng nhiều tác vụ hợp lệ cũng có **heartbeat, health check, monitoring, software update, license polling**.

### 14.1. Những đặc điểm để lập giả thuyết

- Lặp theo chu kỳ, có/không có jitter.
- Kích thước request/response tương đối nhỏ hoặc ổn định.
- Destination domain/IP mới so với baseline.
- Process phát sinh không phù hợp business role.
- Sự kiện xuất hiện sau **suspicious execution/EDR alert**.
- Có authentication failures, remote command activity hoặc data access ngay sau đó.

**Không cần một “chu kỳ chuẩn” để kết luận beacon**. Thuật toán phát hiện periodicity phụ thuộc độ dài quan sát, missing samples và hành vi ứng dụng.

### 14.2. Khi triage cần hỏi

1. Có **đúng một process entity ID** gắn các kết nối không?
2. Domain/IP có thuộc nhà cung cấp ứng dụng/telemetry hợp lệ không?
3. Có **license/update/health check** theo lịch không?
4. Có file, registry, scheduled task hoặc service configuration mới tương ứng?
5. EDR, DNS và proxy logs có cùng host, cùng thời điểm?
6. Có dữ liệu/mẫu lệnh ở tầng ứng dụng mà sensor được quyền quan sát không?
7. Traffic còn đang diễn ra, scope bao nhiêu endpoints?

### 14.3. Không gán nhãn C2 chỉ từ reputation

Một IP có thể là cloud/CDN shared hosting; domain mới có thể thuộc tổ chức triển khai SaaS. Reputation và TLS fingerprints giúp **ưu tiên truy vấn**, không đủ làm attribution hay xác nhận malware.

### 14.4. Khi nên chuyển cấp

Nếu có **process trái phép, persistent execution artifact, outbound recurring connection tới infrastructure liên quan threat intel đã xác minh và hoạt động nội bộ trái quyền**, cần báo IR team theo threshold. Bảo toàn evidence trước khi thay đổi nếu điều kiện an toàn cho phép; containment khẩn cấp vẫn ưu tiên khi nguy cơ đang gây hại.

## 15. Triage east–west, lateral movement và truy cập đặc quyền

Trong môi trường nội bộ, **RDP/SSH/SMB/WinRM/database ports** có thể mang nghiệp vụ quản trị hợp lệ hoặc hoạt động di chuyển ngang sau xâm nhập. Không đánh đồng **kết nối qua port quản trị** với thành công đăng nhập.

### 15.1. Những dấu hiệu kết hợp

| Quan sát | Bằng chứng bổ sung |
| --- | --- |
| Endpoint A bắt đầu kết nối tới nhiều server | Inventory role và change/patch ticket |
| Nhiều SSH/RDP login failures | Host auth logs, source identity |
| Một login thành công sau chuỗi thất bại | Identity owner, MFA/PAM, session context |
| Access tới domain controller từ host không có nhu cầu | Firewall/EDR, AD audit, management zone policy |
| SMB traffic từ user device đến database subnet | File-sharing workflow thật hay policy violation? |
| Một privileged token/service account xuất hiện từ host mới | IAM/auth evidence và device posture |
| Nhiều Pods gọi dịch vụ quản trị trên nodes | CNI flow/Pod UID, workload service account, host policies |

### 15.2. Sử dụng microsegmentation như một lớp xác minh

Nếu network policy quy định **sales laptops không được gọi production database TCP 5432**, dù chỉ một kết nối **allow** tới đích đó cũng có thể là **policy gap** đáng xem. Không cần chờ vượt bytes threshold.

### 15.3. Phân biệt hành vi admin được duyệt

Một kỳ patching có thể tạo nhiều SSH/WinRM sessions. Cần xem:

- Access từ **bastion/PAM source** được phê duyệt hay laptop tùy ý?
- Ticket/runbook có nêu targets và time window?
- Session có step-up MFA/JIT theo chính sách không?
- Auth thành công trên host nào, command/action nào theo audit sẵn có?

### 15.4. Rủi ro đặc biệt ở Kubernetes

Kubernetes **service account** không tự là danh tính user cho mọi lưu lượng, còn Pod IP có thể đổi theo deployment. Triage east–west cần **namespace, Pod UID, workload identity, NetworkPolicy/mesh policy verdict, node và hostNetwork exceptions**.

### 15.5. Cẩn trọng khi containment

Chặn SMB/DC, SSH bastion hay storage replication bừa bãi có thể làm toàn doanh nghiệp ngừng hoạt động. Với nghi vấn lateral movement, ưu tiên **isolate đúng endpoint/workload, revoke đúng credential hoặc tạo rule hẹp** theo IR owner và kế hoạch rollback.

## 16. Triage traffic spike, DoS và DDoS

Một đột biến inbound requests/SYN/packets có thể là **traffic tăng hợp lệ, bot traffic, retry storm, misconfiguration hoặc DDoS**. Điều tra trước hết phải xác nhận **dịch vụ có mất khả dụng hay gần cạn capacity không**.

### 16.1. Tín hiệu mạng

- Packets/second, bits/second, requests/second theo listener.
- Concurrent connections, SYN backlog, accept queue, TLS handshake rate.
- Load balancer 4xx/5xx, upstream resets, latency p95/p99.
- Source ASN/geography/IP distribution nếu được phép sử dụng.
- Cache hit ratio, WAF/rate-limit decisions.
- Node CPU/network saturation và backend dependency health.

### 16.2. Các câu hỏi quan trọng

1. Spike có tập trung vào **một hostname/path/API** không?
2. Có change/campaign/flash sale hoặc load test được duyệt?
3. App đã ghi nhận tăng traffic thật, hay chỉ firewall counter đổi?
4. Có nhiều nguồn hay một faulty client retry liên tục?
5. Có amplification/reflection pattern hoặc spoofed-source risk?
6. Đã bật upstream DDoS/WAF/rate limiting ở đúng điểm chưa?
7. Đường public IPv4/IPv6 có khác nhau?
8. Có nguy cơ nhầm **đặt rate limit quá thấp** gây denial-of-service cho người dùng thật?

### 16.3. Phản ứng

Nếu availability đang bị ảnh hưởng, escalate tới **SRE/on-call và network/security owner**. Áp mitigation thông qua upstream DDoS provider, WAF, rate limits hoặc LB theo playbook; đo **user impact và false positives**, giữ rollback. Không dùng việc thử flood để xác minh production đang chịu được bao nhiêu.

### 16.4. Dữ liệu thiếu không phải tấn công

Một dashboard hiển thị bandwidth gấp đôi có thể do **đổi sampling interval, counter reset, metric duplication hoặc chuyển điểm quan sát**. Xác minh đơn vị và collector trước khi tuyên bố traffic thật tăng.

## 17. Triage outbound spikes và nghi vấn data exfiltration

**Outbound spikes** đáng xem khi dữ liệu được truyền ra một vùng/tài khoản không có quyền. Nhưng **volume không đủ** để kết luận exfiltration, đặc biệt với HTTPS.

### 17.1. Quy trình tương quan theo nguồn

~~~mermaid
flowchart TD
    FLOW["Large outbound flow"] --> DIR{"Upload direction verified?"}
    DIR -->|"Không"| META["Normalize counters, sampling and NAT"]
    DIR -->|"Có"| WHO["Resolve device/user/workload/process"]
    META --> WHO
    WHO --> DEST["Verify SaaS service AND account/tenant"]
    DEST --> DATA["Check data source read/export + classification"]
    DATA --> APP{"Approved business transfer?"}
    APP -->|"Có và đầy đủ evidence"| ALLOW["Document authorized workflow"]
    APP -->|"Không rõ"| REVIEW["Investigate, preserve evidence"]
    APP -->|"Unauthorized and active"| IR["Authorized block/contain + impact assessment"]
~~~

### 17.2. HTTPS nhìn thấy gì?

Passive network sensors có thể thấy **IP/port/timing/bytes** nhưng không mặc nhiên thấy **HTTP POST, URL, file hay nội dung TLS**. Để xác minh cần:

- Proxy/SWG L7 logs nếu proxy là TLS endpoint được phép.
- Endpoint file/process events.
- Cloud/SaaS tenant/account audit.
- Database/export logs hoặc app data access.
- DLP classifier và data labels khi có source đáng tin.

**Một cloud provider uy tín không đồng nghĩa account đích là của doanh nghiệp.** Enterprise/personal tenants có thể dùng cùng một domain.

### 17.3. Khi nào cần điều tra khẩn?

Nếu có **sensitive data access**, destination account không được duyệt, upload có bằng chứng hoàn tất và source identity/process đáng ngờ, hãy escalate sớm. Mức độ tác động còn phụ thuộc **dữ liệu nào thực sự chuyển, quyền người nhận, khả năng share và policy/contract**.

### 17.4. Không bỏ sót transfers không qua Internet

Một workload cloud có thể copy object sang **cross-account private endpoint** hoặc SaaS-to-SaaS integration. Employee proxy sẽ không thấy các sự kiện đó; dùng **cloud IAM/storage audit và SaaS API logs**.

### 17.5. Không truy cập tài khoản đích trái phép

Nếu nghi dữ liệu đã được chuyển tới tài khoản cá nhân, SOC không được tự truy cập/xóa dữ liệu ở account đó khi không có thẩm quyền. Phối hợp **legal/privacy, data owner, vendor response** và incident process.

## 18. Correlate với IDS/IPS, EDR, identity và threat intelligence

### 18.1. Signature match là gì?

IDS/IPS có thể báo vì packet/flow khớp signature. **Signature alert không tự chứng minh exploit thành công**: có thể là probe, payload vô hại trong lab, false positive, rule quá rộng hoặc traffic đã bị firewall drop.

### 18.2. Bốn câu hỏi khi xem IDS event

1. Signature ID/version/metadata và **nội dung rule** mô tả điều gì?
2. Sensor có thấy traffic **trước hay sau firewall**, một hay hai chiều?
3. Action **alert/drop/reject** là quyết định ở đâu; traffic đã tới đích chưa?
4. Host/app logs có evidence của **successful authentication, process execution, file access, unexpected service response** không?

### 18.3. EDR bổ sung process lineage

EDR có thể liên kết socket với **process, parent process, command context, signer, user/device, persistence findings** tùy khả năng. Một alert network kết hợp EDR process anomaly thường đáng điều tra hơn network flow đơn lẻ.

**Không suy một process có chữ ký hợp lệ là không thể bị lạm dụng**, hoặc một unsigned process chắc chắn độc hại.

### 18.4. Identity và privileged events

Xem:

- IdP sign-in và MFA result, nhưng không lưu token/credentials trong case.
- VPN/ZTNA session assignment.
- Privileged access approval/JIT events.
- Role/group changes và cloud IAM API actions.
- Authentication successes/failures từ host/app liên quan.

**Một IdP login hợp lệ không chứng minh ứng dụng đích đã cấp quyền dữ liệu**. Cần app authorization evidence riêng.

### 18.5. Threat intelligence

Reputation feeds, known malicious infrastructure hoặc indicator lists có thể giúp enrichment. Trước khi dùng làm bằng chứng mạnh:

- Kiểm tra **feed timestamp, confidence, TTL, false-positive history**.
- Xem IP có thuộc **shared CDN/cloud** không.
- Xác nhận indicator có phù hợp **network layer và observation time**.
- Tránh tự suy attribution tới một nhóm tấn công từ một IP hoặc fingerprint.

### 18.6. Kết hợp độc lập, không cộng lặp

Một network flow được nhiều sensors sao chép thành ba alerts **không phải ba bằng chứng độc lập**. Ngược lại, **EDR process event + database export audit + proxy upload** có thể cung cấp các góc nhìn độc lập hơn.

## 19. Cloud, Kubernetes, service mesh và telemetry phân tán

### 19.1. Cloud egress/inbound không đi qua một gateway duy nhất

Một VPC/VNet có thể có **Internet NAT gateway, private endpoint, peering, load balancer, transit gateway hoặc service-to-service API**. Security group và subnet ACL cũng có điểm enforcement khác CNI policy.

Khi alert xuất phát từ cloud:

1. Xác định **account, region, VPC/VNet, subnet, NIC/ENI, instance/Pod và cloud role**.
2. Kiểm tra route tables/security groups/network ACL đã thay lúc nào.
3. Đối chiếu cloud flow logs với **cloud API audit và service logs**.
4. Ghi rõ log là **accepted/rejected traffic** hay chỉ sampled flows.
5. Kiểm tra **IPv6 và private endpoint** nếu Internet egress monitor không thấy.

### 19.2. Kubernetes attribution

Một packet từ **10.244.2.17** có thể thuộc Pod A tại thời điểm alert nhưng Pod đó đã bị thay; tra cứu hiện tại có thể trả Pod khác. Cần:

- **Pod UID, namespace, name, node và workload controller** tại event time.
- CNI/eBPF/OVS policy verdict hoặc flow log khi có.
- **ServiceAccount/workload identity** và PodSecurity/admission context.
- Service VIP/EndpointSlice và NAT translation, kể cả kube-proxy replacement.
- hostNetwork/secondary interfaces và direct-node paths.

### 19.3. Service mesh

Trong mesh, một proxy hoặc dataplane có thể báo **mTLS peer identity, source/destination service, routing outcome và authorization verdict**. Nhưng:

- Mesh mTLS thành công không chứng minh **API user authorization**.
- Một HTTP 403 có thể do **mesh policy hoặc backend**, cần log theo request ID.
- Không phải mọi Pod/port đều tham gia mesh hoặc được same policy kiểm soát.
- Sidecar/ambient/waypoint modes có policy hooks và coverage khác nhau.

### 19.4. Container/image update là false positive phổ biến

CI/CD rollout, image pull, service discovery change, backup snapshot, autoscaling và health probes có thể tăng flow counts. Gắn **deployment revision, change ticket và owner** vào timeline để phân biệt thay đổi hợp lệ với lạm dụng.

### 19.5. Node-level saturation và dịch vụ nền

Một host có thể thấy nhiều **TCP retries hoặc DNS timeouts** do node bị overload, conntrack full hoặc CNI agent lỗi. Trước khi gọi đó là tấn công, kiểm tra **node metrics, kernel/network errors và service health** theo quyền được cấp.

## 20. Thu thập packet capture và bảo toàn chứng cứ

**Packet capture (PCAP)** có thể hỗ trợ xác minh flags, packet timing, retransmissions, protocol fields và network path. Nhưng chỉ thu được những packets đi qua **đúng capture point**, và dữ liệu TLS mã hóa không tự thành plaintext.

### 20.1. Quyết định có cần PCAP không?

Không phải alert nào cũng cần bắt gói. Dùng logs hiện có khi đủ; cân nhắc PCAP nếu:

- Cần phân biệt **handshake/transport failure** với ứng dụng lỗi.
- Phải xác minh **direction, retransmission, NAT, route asymmetry**.
- IDS alert có packet evidence nhưng parser không rõ.
- Cần phục vụ forensic workflow với quyền phê duyệt.

**PCAP có thể chứa credentials, cookies, nội dung plaintext của giao thức khác HTTPS và dữ liệu cá nhân**. Chỉ capture trong phạm vi đã duyệt, giới hạn host/port/time và lưu giữ có kiểm soát.

### 20.2. Ví dụ kiểm tra PCAP lab đã có sẵn

Các lệnh **chỉ đọc file capture lab**, không khởi động bắt packet mới:

~~~bash
# File được giả định do lab tạo hợp lệ: lab-traffic.pcapng.
# Xem thống kê/metadata trước khi đi sâu.
capinfos lab-traffic.pcapng

# Đọc TCP SYN/ACK/RST để xác minh trạng thái kết nối.
tshark -r lab-traffic.pcapng \
  -Y 'tcp.flags.syn == 1 || tcp.flags.reset == 1' \
  -T fields -e frame.time -e ip.src -e ip.dst \
  -e tcp.srcport -e tcp.dstport -e tcp.flags

# Xem truy vấn DNS nếu thực sự có DNS packets trong file.
tshark -r lab-traffic.pcapng \
  -Y 'dns.flags.response == 0' \
  -T fields -e frame.time -e ip.src -e dns.qry.name
~~~

Lệnh minh họa dùng **Wireshark/TShark và capinfos nếu đã cài**. Không đảm bảo mọi pcapng chứa IPv4, TCP hoặc DNS plaintext; với IPv6, cần dùng **ipv6.src/ipv6.dst** và hiểu capture flags. **Không in toàn payload hoặc secrets** lên màn hình/ticket chỉ để tra header.

### 20.3. Capture scope tối thiểu nếu đã được phê duyệt

Nếu forensic lead yêu cầu thu gói mới, xác định trước:

1. **Mục đích chính xác** và incident ID.
2. Source/destination/port/protocol và khoảng thời gian.
3. Capture point, interface, mirror direction và topology.
4. Băng thông và rủi ro mất packet/cạn disk.
5. Quyền lưu file, encryption và retention.
6. Cách ghi **start/end time, operator, hash** và đường chuyển chứng cứ.

Không tự thu traffic của toàn mạng, chiếm quyền trên hosts hoặc gửi bản capture chứa dữ liệu nhạy cảm sang dịch vụ ngoài tổ chức.

### 20.4. Chain of custody

Khi có yêu cầu pháp chứng, case record nên lưu:

| Trường | Ý nghĩa |
| --- | --- |
| Evidence ID | Định danh duy nhất và incident liên quan |
| Source | Hệ thống/sensor/interface/capture scope |
| Collector | Người/hệ thống thu và quyền được cấp |
| Acquisition time | Mốc UTC và time synchronization context |
| Integrity hash | Ví dụ SHA-256 của file evidence |
| Storage location | Kho kiểm soát truy cập, encryption và retention |
| Transfers | Ai nhận, khi nào, vì mục đích gì |
| Transformations | Parser/filter/tool version, giữ bản gốc |

**Hash xác minh tính toàn vẹn file từ lúc hash được tạo, không tự chứng minh sensor đã thấy mọi packet hoặc timestamp chính xác.** Bản đã lọc/đã cắt phải được phân biệt với original evidence.

### 20.5. Cảnh giác với packet reassembly

Fragmentation, TCP retransmission, capture loss, out-of-order packets và TLS/HTTP multiplexing ảnh hưởng việc dựng lại stream. Không kết luận một file đã truyền hoàn tất từ vài packets nếu thiếu **application/receiver evidence**.

## 21. SIEM correlation và truy vấn minh họa

Triage có thể dùng các phép tổng hợp nhỏ, có giới hạn về time window để tránh query chi phí lớn hoặc làm quá tải hệ thống log. Các mẫu sau **chỉ là pseudo SQL trên schema đã chuẩn hóa**, không phải truy vấn chạy được ở mọi SIEM.

### 21.1. Schema logic

~~~text
normalized_network_events(
    timestamp_utc,
    event_id,
    src_ip_original,
    src_port_original,
    dst_ip,
    dst_port,
    transport,
    flow_direction,
    bytes_client_to_server,
    packets,
    connection_result,
    asset_id,
    identity_id,
    sensor_id,
    environment
)
~~~

Nếu **bytes_client_to_server, identity_id hoặc src_ip_original** không được cung cấp, phải để NULL/unknown. **Không chuyển bytes total thành upload bytes** chỉ để có số đưa vào dashboard.

### 21.2. Phát hiện nguồn kết nối tới nhiều đích

~~~sql
-- PSEUDO SQL, chạy trên synthetic/authorized analytics dataset.
SELECT
    src_ip_original,
    COUNT(DISTINCT dst_ip) AS distinct_hosts,
    COUNT(DISTINCT dst_port) AS distinct_ports,
    COUNT(*) AS observed_connections
FROM normalized_network_events
WHERE timestamp_utc >= :window_start_utc
  AND timestamp_utc < :window_end_utc
  AND src_ip_original IS NOT NULL
  AND transport = 'TCP'
GROUP BY src_ip_original;
~~~

**Không tự gán scan chỉ vì distinct_hosts cao**. Kết quả cần ghép scanner inventory, backup/monitoring job và TCP outcomes. Dữ liệu pre-NAT thiếu có thể làm attribution sai.

### 21.3. Tổng hợp upload bytes đã xác minh

~~~sql
-- PSEUDO SQL, chỉ dùng field direction được collector xác minh.
SELECT
    asset_id,
    identity_id,
    dst_ip,
    dst_port,
    SUM(bytes_client_to_server) AS bytes_up_observed
FROM normalized_network_events
WHERE timestamp_utc >= :window_start_utc
  AND timestamp_utc < :window_end_utc
  AND bytes_client_to_server IS NOT NULL
  AND transport IN ('TCP', 'UDP')
GROUP BY asset_id, identity_id, dst_ip, dst_port;
~~~

Trước khi SUM, phải **deduplicate cùng session từ sensors trùng** và hiểu sampling/multiplexing. Không gọi tổng số byte này là **data exfiltration amount**.

### 21.4. Truy vấn đối chiếu theo thời gian

Một sequence triage có thể dùng window:

~~~text
T-15m..T:
  Network alert triggered

T-30m..T+15m:
  Source asset identity mapping (NAT/DHCP/Pod UID)
  EDR network socket/process events
  IdP/VPN/ZTNA session state
  DNS/Proxy/TLS metadata
  Destination application/cloud audit
  Change calendar and asset owner approvals
~~~

Các cửa sổ chỉ là **điểm bắt đầu**, phải thay theo latency logs, event delays và threat scenario. Một account token bị dùng nhiều ngày có thể yêu cầu lookback dài hơn sau khi được escalation phê duyệt.

### 21.5. Time normalization

- Chuyển timestamps sang UTC và giữ **original timezone** nếu có.
- Ghi **ingestion time** riêng với **event time**.
- Kiểm tra clock drift của node/collector, NTP status.
- Tính đến delayed SaaS API audit, batching và flow expiration.
- Không nối sự kiện chỉ vì hai timestamps in ra giống nhau khi clocks chưa đồng bộ.

### 21.6. Tránh tìm kiếm vô hạn

Đặt **query scope** theo case và nguồn dữ liệu. Nếu cần mở rộng toàn tổ chức, nêu giả thuyết và xin thẩm quyền theo IR process, không tùy tiện lấy toàn bộ traffic hoặc hồ sơ người dùng.

## 22. Hồ sơ triage: checklist và chuẩn báo cáo

Một case được người khác tiếp nhận phải phân biệt rõ **observed fact**, **inference**, **unknown**, **decision** và **next action**.

### 22.1. Mẫu case record

~~~yaml
networkIncidentTriageCase:
  caseId: LAB-NET-00042
  sourceAlertId: LAB-NET-00042
  status: investigating
  priority: P2-example-only
  assignedTeam: soc-network-triage
  firstSeenUtc: "2026-11-28T02:00:00Z"
  lastSeenUtc: "2026-11-28T02:15:00Z"
  detection:
    rule: large-outbound-deviation-v3
    detectorSeverity: medium
    signal: outbound-volume-above-role-baseline
  scope:
    environment: synthetic-training-lab
    sourceAsset: unresolved
    sourceIdentity: unknown
    destinationIp: 203.0.113.42
    destinationAccount: unknown
    affectedBusinessService: under-review
  observedFacts:
    - flow-collector-recorded-verified-client-to-server-bytes
    - destination-tcp-443
  hypotheses:
    - authorized-backup-or-build
    - unauthorized-data-transfer
    - telemetry-or-nat-misattribution
  unknowns:
    - user-or-workload-at-event-time
    - destination-tenant-account
    - source-data-classification
    - actual-upload-completion
  evidence:
    - id: flow-event-001
      source: lab-flow-collector-01
      integrity: exported-and-hashed-per-lab-procedure
  decision:
    confidence: low
    impactIfTrue: high
    action: enrich-and-escalate-if-confirmed
  nextSteps:
    - resolve-nat-dhcp-or-workload-identity
    - check-approved-business-transfer
    - correlate-endpoint-and-proxy-logs
  privacy:
    no-credentials-in-case: true
    retention: follow-approved-policy
~~~

YAML này là **hồ sơ giả lập trung lập với sản phẩm**, không phải cấu hình cho SIEM hoặc API incident management. Các trường thiếu được để **unknown**, tránh điền thông tin đoán từ IP/domain.

### 22.2. Checklist trước khi quyết định

| Câu hỏi | Trạng thái cần ghi |
| --- | --- |
| Alert có thực sự xảy ra? | Confirmed observation / parser issue |
| Sensor thấy đúng đường traffic? | Vantage và visibility limits |
| Source identity được xác minh? | Verified / suspected / unknown |
| Destination/resource được xác minh? | Service, account/tenant nếu có |
| Baseline và business change có liên quan? | Matched / not matched / unknown |
| Có thêm evidence độc lập? | EDR, IdP, DNS, proxy, app, cloud |
| Traffic có thành công không? | L4 / TLS / app outcome phân biệt |
| Có tác động/hoạt động vẫn tiếp tục? | Scope và urgency |
| Có quyền containment ngay không? | Playbook/approval/owner |
| Evidence đã được bảo vệ? | Source, timestamp, hash nếu cần |

### 22.3. Cách viết kết luận chuẩn

Ví dụ **không nên viết**:

> Máy user-42 đã gửi 1,2 GB dữ liệu khách hàng cho hacker qua HTTPS.

Nếu evidence chỉ từ flow collector, phù hợp hơn là:

> Collector ghi nhận một luồng TCP/443 với khoảng 1,2 GB theo chiều client→server trong khung thời gian đã nêu, cao hơn baseline. Nguồn người dùng, loại dữ liệu và tài khoản đích chưa được xác minh. Đã yêu cầu correlation NAT/EDR/proxy và data owner review.

### 22.4. Không đưa bí mật vào ticket

Tránh ghi **access tokens, cookies, SSH keys, private keys, password, raw PII, file payload** vào hệ thống incident ticket hoặc chat không được bảo vệ. Nếu evidence nhạy cảm cần lưu trữ, dùng kho chuyên dụng với ACL, mã hóa, retention và access audit.

## 23. Escalation và containment: lựa chọn đúng với độ chắc chắn

Triage giúp xác định **đội nào có quyền phản ứng và nên làm gì**, không cho phép analyst tự động sửa production firewall, cô lập host hoặc vô hiệu user khi chưa có policy/phê duyệt.

### 23.1. Phân quyền thực hành

| Vai trò | Trách nhiệm |
| --- | --- |
| **SOC L1/Triage** | Intake, verify, enrich, case record, priority ban đầu |
| **SOC L2/Incident analyst** | Correlation sâu hơn, hypotheses, forensic coordination |
| **Network/SRE** | Firewall/route/LB/DNS diagnostics và thay đổi hạ tầng được duyệt |
| **Endpoint/Identity team** | EDR containment, account/token revocation theo thẩm quyền |
| **Cloud/Kubernetes team** | CNI/cloud IAM/network policy, Pod/node changes có kiểm soát |
| **Application/Data owner** | Xác minh workflow, data class, business authorization/impact |
| **Incident commander** | Ưu tiên, quyết định phối hợp, stakeholder/communications |
| **Legal/Privacy** | Nghĩa vụ thông báo, bảo mật chứng cứ, quyền riêng tư khi liên quan |

### 23.2. Các phương án giảm thiểu theo rủi ro

- **Block đích/port cụ thể** nếu có evidence và firewall policy thích hợp.
- **Quarantine một endpoint/workload** thay vì khóa cả subnet khi nghi compromise.
- **Revoke một token/session hoặc role** thay vì disable toàn tổ chức.
- **Rate-limit/WAF/DDoS mitigation** ở upstream cho availability event.
- **Disable external share hoặc cloud IAM grant cụ thể** qua quyền được cấp.
- **Isolate backup, identity hoặc management servers** chỉ sau đánh giá hậu quả vận hành.

### 23.3. Kiểm tra blast radius và rollback

Trước thay đổi, ghi:

1. Nhóm người dùng/service nào sẽ bị ảnh hưởng?
2. Rule áp **nguồn/đích/protocol/port/zone/IP family** nào?
3. Có backend dùng chung IP/CDN hoặc NAT không?
4. Lưu lượng hợp lệ nào có thể bị chặn?
5. Có cách quan sát hiệu lực deny và báo lỗi khách hàng không?
6. Ai phê duyệt và khi nào rollback?

Không chặn một IP cloud shared hosting chỉ vì một event nếu nó phục vụ nhiều ứng dụng hợp lệ mà chưa cân nhắc tác động.

### 23.4. Nếu threat đang gây hại ngay

Theo quy trình khẩn cấp có sẵn, **đẩy ưu tiên lên incident commander/IR** và triển khai containment trong phạm vi được phân quyền; đừng đợi có đủ mọi log rồi mới báo. Đồng thời bảo toàn evidence tối thiểu trong khả năng.

### 23.5. Xác minh sau containment

Một biện pháp có hiệu lực khi:

- Luồng bị nghi ngờ bị **chặn hoặc giảm rõ ràng ở đúng điểm**.
- Hệ thống hợp lệ không bị gián đoạn ngoài mức được duyệt.
- Không còn **đường bypass khác**: VPN, IPv6, cloud private route, NodePort, proxy khác.
- Tài khoản/credential đang bị lạm dụng không còn quyền.
- Logs và case timeline ghi thay đổi, owner, bằng chứng, rollback.

## 24. Quy trình ra quyết định và automation có giới hạn

Automation hữu ích để **chuẩn hóa enrichment, deduplication, asset lookup, baseline retrieval** và giảm thời gian triage. Nhưng action nguy hiểm cần giới hạn theo quyền, confidence và impact.

### 24.1. Giả mã triage phòng vệ

~~~text
function triageNetworkAlert(alert):
    validateSourceSchemaAndClock(alert)
    if isConfirmedParserError(alert):
        return CLOSE_FALSE_POSITIVE_WITH_EVIDENCE

    related = findExistingCasesUsingTrustedKeys(alert)
    if isExactDuplicate(alert, related):
        return LINK_TO_EXISTING_CASE

    facts = normalizeObservedFlowFields(alert)
    scope = resolveAssetAndIdentityAtEventTime(facts)
    baseline = getRoleAndServiceBaseline(scope, alert.window)
    enrichment = correlateAuthorizedTelemetry(
        facts, scope, dns, firewall, edr, identity, proxy, cloud, app
    )

    findings = explainDifferencesFromBaseline(
        observedFacts=facts,
        businessContext=baseline,
        corroboration=enrichment
    )
    unknowns = recordMissingAndUnreliableFields()

    impact = assessAssetCriticalityAndPossibleImpact(scope, findings)
    confidence = assessEvidenceQualityAndIndependence(findings)
    urgency = assignPriorityWithOrganizationPolicy(
        impact, confidence, observedActivityStillActive()
    )

    case = createEvidenceLinkedCase(
        observed=facts,
        inferred=findings,
        unknown=unknowns,
        priority=urgency
    )

    if confirmedAuthorizedWorkflow(case):
        return CLOSE_BENIGN_WITH_OWNER_AND_TUNING
    if immediateHarmLikelyAndAuthorizedEmergencyCriteriaMet(case):
        escalateToIncidentCommander(case)
        return REQUEST_APPROVED_CONTAINMENT
    if credibleConcern(case):
        return ESCALATE_FOR_INVESTIGATION
    return MONITOR_AND_COLLECT_BOUNDED_EVIDENCE
~~~

### 24.2. Automation không nên tự suy đoán

- Không tạo **data exfil confirmed** chỉ từ bytes cao.
- Không gán một user từ **shared NAT public IP**.
- Không coi **TLS SNI luôn hiện rõ** trong ECH hoặc TLS 1.3 metadata thiếu.
- Không coi IDS signature **block** là bằng chứng exploit thành công.
- Không coi **DNS query** là HTTP connection.
- Không tự khóa người dùng chỉ vì một score anomaly thiếu evidence.

### 24.3. Rule governance

Mỗi automation/rule nên có **owner, version, test cases, approval, exception process, timeout, data retention, metrics và rollback**. Với action như isolate endpoint, IAM revoke hoặc cloud firewall change, cần **explicitly authorized playbook** và audit.

### 24.4. Khi phản ứng phải ngừng tự động

Nên yêu cầu human approval hoặc incident commander khi:

- Cần chặn broad subnet, shared proxy/CDN hoặc core infrastructure.
- Cần tác động tới identity provider, database backup hoặc critical workloads.
- Event identity/data source chưa đáng tin.
- Policy action có thể dẫn đến data loss hoặc outage.
- Sự cố liên quan nghĩa vụ pháp lý và điều tra nhân sự.

## 25. Runbook: cảnh báo HTTPS outbound cao từ production application

**Tình huống giả lập:** SIEM báo một application server **10.20.4.17** có khoảng **1,2 GB theo chiều client→server qua TCP 443** đến một public address trong 15 phút. Alert được gắn mức ưu tiên trung bình, còn hệ thống vận hành bình thường. Người trực chưa biết đây là backup hợp lệ hay data transfer trái quyền.

### 25.1. Bước 1 – Xác nhận sự kiện

1. Kiểm tra **flow start/end, direction, units, sampling, duplicate**.
2. Đối chiếu **firewall accept/deny và actual NAT translation**.
3. Xác định server đúng là **application server ở event time** bằng asset/cloud inventory.
4. Xem **sensor vantage** và traffic có thể đi qua proxy/NAT nào.
5. Ghi dữ liệu chưa quan sát: **HTTP method, file names, tenant account, data class**.

Nếu collector thực ra chỉ ghi tổng bytes của cả hai chiều hoặc source IP là NAT shared, **hạ confidence của attribution**, không tiếp tục khẳng định “server upload 1,2 GB” như một fact.

### 25.2. Bước 2 – Xác định workflow

Hỏi application owner/SRE:

- Có backup, scheduled export, build artifact, patch/update hoặc data sync lúc đó không?
- Service account, deployment revision và job schedule nào tạo traffic?
- Có thay đổi DNS/CDN/provider account gần thời điểm đó không?
- Đích được duyệt là **đúng SaaS tenant/cloud account** hay chỉ provider domain?
- Có business transfer ticket/contract/data owner approval không?

Không cần gửi toàn bộ packet capture cho business owner nếu chỉ cần xác minh ticket hoặc application log.

### 25.3. Bước 3 – Correlate telemetry

| Dấu hiệu | Nguồn | Diễn giải |
| --- | --- | --- |
| Process mở socket TCP 443 | EDR/node/app | Gắn traffic với process hoặc workload |
| Data export/read trước kết nối | DB/object/file audit | Có thể có nguồn dữ liệu liên quan |
| Request tới storage account nào | Proxy/SaaS API | Phân biệt enterprise/personal account |
| Upload hoàn tất | Application/SaaS object audit | Bằng chứng truyền thành công mạnh hơn L4 |
| Có cloud IAM change trước đó | Cloud audit | Khả năng mở quyền mới |
| Có EDR alert khác | Endpoint telemetry | Tăng rủi ro process/session |
| Có proxy/VPN/IPv6 path thay thế | Network inventory | Loại trừ đường ngoài sensor |

### 25.4. Bước 4 – Quyết định

**Nhánh A: Authorized transfer.** Job backup đã duyệt, identity đúng, destination account đúng, dữ liệu đúng class và time window. Ghi benign true positive; tune baseline theo **job/owner/destination**, không allow mọi HTTPS.

**Nhánh B: Suspicious, chưa đủ bằng chứng.** Chỉ có flow lớn và đích cloud chung. Giữ case investigating, bổ sung app/identity/audit, không kết luận exfil.

**Nhánh C: Credible unauthorized transfer.** Sensitive data read/export + account ngoài quyền + upload success + không có approval, có thể tiếp tục. Escalate IR, đề xuất **block account/destination hoặc revoke đúng identity** theo thẩm quyền; xác định phạm vi dữ liệu và legal/privacy obligations.

### 25.5. Bước 5 – Sau containment

- Xác minh transfer trái quyền ngừng theo **network/proxy/SaaS logs**.
- Kiểm tra không còn **cloud private endpoint, IPv6 hay VPN bypass** phù hợp case.
- Không làm gián đoạn những backups hợp lệ ngoài phạm vi.
- Bảo toàn evidence, ghi owner/rule/version/thời điểm.
- Tạo follow-up để sửa **excess permissions, tenant restriction, logging gap**.

## 26. Case study: DDoS hay traffic spike hợp lệ?

Một API thương mại điện tử có traffic tăng từ **3.000 req/s lên 20.000 req/s** trong vài phút, đồng thời latency p99 tăng và HTTP 503 xuất hiện. WAF báo số rule matches tăng. Network team nhận alert **Possible DDoS**.

### 26.1. Dữ liệu ban đầu

~~~json
{
  "synthetic": true,
  "case_id": "LAB-AVAIL-001",
  "time": "2026-11-28T02:30:00Z",
  "public_service": "api.shop.example.test",
  "requests_per_second_baseline": 3000,
  "requests_per_second_observed": 20000,
  "http_503_rate": 0.18,
  "affected_component": "public-api-gateway",
  "waf_rule_matches": "elevated",
  "source_distribution": "multiple-geographic-regions",
  "known_business_change": "campaign-launch-under-review",
  "interpretation": "availability-risk-not-attributed"
}
~~~

### 26.2. Những giả thuyết đối lập

1. **Campaign traffic hợp lệ** do marketing launch nhưng capacity thấp.
2. **Client retry storm** từ SDK bị lỗi hoặc backend 503 khiến retries tăng.
3. **Bot/abusive application traffic** gây tải bất thường.
4. **Network-layer DDoS** tới listener.
5. **Monitoring error** do thay collector hoặc duplicate metrics.

### 26.3. Điều tra theo thứ tự

1. Xác nhận request counts/bytes trên **CDN/LB, gateway và backend** có nhất quán không.
2. Hỏi marketing/release owner về **launch ticket và load forecast**.
3. Kiểm tra top paths, response codes, request methods, user session patterns (trong phạm vi log).
4. Đối chiếu backend CPU, connection pools, database saturation, error budgets.
5. Kiểm tra WAF **rule verdicts**, false-positive rate và geographic distribution.
6. Kiểm tra retry metrics, client versions và ứng dụng có tự tạo loop không.
7. Xem lượng traffic từ **một nguồn so với nhiều nguồn**, song không dùng geography làm chứng cứ duy nhất.
8. Đánh giá rate-limit scope: per user/token/IP có đúng với NAT/proxy context không?

### 26.4. Quyết định và phản ứng

Nếu backend đang quá tải nghiêm trọng, ưu tiên khôi phục **availability** theo playbook. Biện pháp có thể gồm **upstream mitigation, autoscaling hợp lệ, cache, rate limits có kiểm soát, disable faulty release hoặc retry backoff**. Không cần xác nhận chắc chắn mọi request là tấn công trước khi xử lý suy giảm dịch vụ.

**Đối với traffic hợp lệ bị WAF chặn nhầm**, cần điều chỉnh cụ thể rule có evidence, không tắt WAF toàn bộ. Đối với volumetric attack confirmed, phối hợp nhà cung cấp DDoS và incident commander.

### 26.5. Kết luận case minh họa

Sau correlation, giả định phát hiện **campaign traffic hợp lệ** cộng với **client retry bug** làm tăng tải. Case được phân loại **benign traffic spike với availability incident**: không có bằng chứng DDoS, nhưng có sự cố vận hành cần remediation. Đây là ví dụ cho thấy **không phải incident nào có network anomaly cũng là security attack**, và vẫn cần hành động khắc phục.

### 26.6. Lessons learned

- Đồng bộ calendar marketing/release với SOC/SRE.
- Theo dõi retry/backoff, rate limits và backend saturation.
- Giữ evidence tách biệt cho **request load, WAF decisions và service health**.
- Xây tiêu chí severity theo **user impact**, không chỉ tần suất alert.
- Kiểm tra positive và negative test của WAF/rate limits sau tuning.

## 27. Case study: truy cập RDP/SMB tăng sau một VPN session

Một VPN gateway báo user đăng nhập từ thiết bị mới được đăng ký. Ít phút sau, firewall thấy cùng assigned VPN IP mở nhiều kết nối tới các hệ thống thuộc subnet quản trị qua TCP 3389 và 445. Một NDR rule tạo alert **Possible lateral movement**.

### 27.1. Fact ban đầu

~~~text
Alert ID:           LAB-LATERAL-014
VPN assigned IP:    10.77.0.42
Source identity:    unverified until session correlation
Target zone:        restricted-admin-lab
Ports observed:     TCP 3389 / TCP 445
Host auth outcome:  unknown
Change ticket:      not yet checked
EDR signal:         pending
Environment:        authorized synthetic lab
~~~

Các ports chỉ là **dịch vụ thường gặp**, không khẳng định đã truy cập Windows host thành công.

### 27.2. Tách ba tầng

| Tầng | Quan sát cần lấy | Không suy ra |
| --- | --- | --- |
| VPN | IdP/MFA, assigned IP, device, session ID | Mọi flow chắc chắn do user tương tác |
| Network | Source→targets/ports, SYN/ACK/reset, firewall verdict | Đã đăng nhập RDP/SMB |
| Host/app | Windows/SSH auth events, PAM tickets, EDR process | Mọi login là thao tác trái phép |

### 27.3. Hai giả thuyết

**Giả thuyết lành tính:** Một quản trị viên đang thực hiện **inventory/patching** theo lịch bằng managed device và đi qua PAM/bastion đã duyệt.

**Giả thuyết rủi ro:** Một user account/session hoặc endpoint bị compromise, cố thử truy cập quản trị ngoài quyền, có thể dẫn tới lateral movement.

### 27.4. Phương pháp phân biệt

1. Map assigned VPN IP theo **session timestamp**, không theo trạng thái hiện tại.
2. Xác định device ID, posture và MFA/session authentication.
3. Kiểm tra tickets/PAM và targets thực tế được phép.
4. Ghi network outcomes (SYN-only, established, denied).
5. Xem host auth logs để phân biệt **login success/failure**.
6. Xem EDR trên source để biết **process lineage và user context**.
7. Xem các hoạt động tương tự ở nhiều destinations/users.
8. Kiểm tra privileged role/group mới được cấp hoặc thay đổi policy.

### 27.5. Phản ứng giả định

Nếu tickets và host logs chứng minh authorized patching, đóng **benign with evidence** và cập nhật scan/maintenance correlation. Nếu phát hiện **unauthorized successful privileged login** hoặc process compromise, escalate IR và đề xuất **revoke session/credential, isolate đúng endpoint, protect targets** theo thẩm quyền.

### 27.6. Bài học

Một alert “RDP/SMB spike” nằm ở **network layer**. Muốn xác nhận **lateral movement**, phải kết hợp identity, authentication, host activity và business context. Chặn toàn bộ cổng 445 trong production chỉ từ một alert có thể làm hỏng AD/file-sharing workloads.

## 28. Ma trận kiểm thử triage trong lab được cấp phép

Các tình huống sau chỉ sử dụng **synthetic logs, test endpoints, PCAP được tạo trong lab có quyền và dữ liệu không nhạy cảm**. Không quét máy chủ bên thứ ba, không làm DDoS, không gửi dữ liệu thật ra ngoài, không thử đánh cắp phiên hoặc thực hiện khai thác. Các ca liên quan tới scan, malware-like behavior, exfiltration hoặc DDoS nên được **mô phỏng bằng records/traffic test giới hạn** thay vì tạo tấn công thật.

### 28.1. Các ca kiểm thử

| Mã | Tình huống | Kết quả triage mong đợi |
| --- | --- | --- |
| T-01 | Alert có source/destination/timestamp đầy đủ | Intake và case ID được tạo chính xác |
| T-02 | Collector đổi trường bytes mà parser chưa cập nhật | Phát hiện parser issue; không suy data exfil |
| T-03 | Cùng flow xuất hiện ở 2 sensors | Deduplicate, không gấp đôi lượng traffic |
| T-04 | Event time UTC khác ingestion time | Timeline tách hai mốc đúng |
| T-05 | Source IP chỉ là public NAT shared | Identity=unknown cho đến khi có NAT mapping |
| T-06 | Pre-NAT + source port + timestamp khớp NAT event | Gắn đúng endpoint với confidence có căn cứ |
| T-07 | DHCP lease đổi owner sau thời điểm alert | Tra source tại event time, không lấy owner hiện tại |
| T-08 | VPN pool IP đã cấp cho user khác ở thời điểm khác | Phân biệt VPN session IDs và timestamps |
| T-09 | IPv6 temporary address thuộc cùng endpoint lab | Correlate IPv6/device đúng, không suy từ IPv4 |
| T-10 | Pod IP tái sử dụng sau redeployment | Dùng Pod UID/namespace/node tại thời điểm |
| T-11 | Server backup lớn theo change ticket | Benign true positive với approved workflow |
| T-12 | Developer publish artifact theo lịch | Baseline theo role/process giảm false positive |
| T-13 | Laptop upload lớn ngoài lịch, tenant unknown | Suspicious/needs enrichment; chưa kết luận exfil |
| T-14 | File lab Restricted upload tới unapproved test account có audit success | Tăng confidence và escalate theo policy |
| T-15 | File lab Secret nhỏ ra test account chưa duyệt | Không bỏ qua do volume thấp |
| T-16 | Flow 1 GB nhưng client-to-server direction unknown | Không gọi 1 GB là upload confirmed |
| T-17 | DNS query tới domain mới, không có network flow | Không khẳng định kết nối xảy ra |
| T-18 | CoreDNS queries tăng do search-domain/ndots | Phân biệt retry/search behavior với abuse |
| T-19 | DNS SERVFAIL tăng vì upstream resolver outage | Network incident/availability, không suy DNS attack |
| T-20 | Approved DoH resolver dùng bởi app đã phê duyệt | Visibility limit có ghi nhận, không tự gắn malicious |
| T-21 | TLS 1.3 passive record thiếu server certificate | Không bịa cert evidence từ ciphertext |
| T-22 | ECH-enabled lab traffic không lộ true SNI | Detection không phụ thuộc true hostname quan sát thụ động |
| T-23 | CONNECT-only proxy log cho HTTPS | Không suy HTTP POST/file content |
| T-24 | HTTP/2 nhiều requests trên một TLS flow | Không đồng nhất một flow với một upload |
| T-25 | UDP 443 test traffic | Ghi transport/protocol theo bằng chứng, không suy HTTPS 100% |
| T-26 | Nhiều TCP SYN tới các hosts trong scope scanner lab | So với scanner ticket và source identity |
| T-27 | Scan-like pattern từ host không nằm trong scanner inventory | Escalate/enrich, không kết luận exploit success |
| T-28 | SYN nhiều nhưng không thấy SYN-ACK vì asymmetric route | Kiểm tra vantage/return path trước kết luận |
| T-29 | TCP handshake thành công nhưng application 403 | Tách network reachability và app authorization |
| T-30 | Failed SSH logins từ host không được phép | Ghép host logs/identity và network flow |
| T-31 | RDP connections từ bastion đúng lịch patch | Benign with PAM/ticket evidence |
| T-32 | RDP connections từ endpoint mới, privileged login thành công trái scope | Escalate incident và cân nhắc containment |
| T-33 | Beacon-like interval của approved monitoring agent | Baseline/process owner giải thích |
| T-34 | Recurring outbound connections + EDR alert không liên quan baseline | Investigation có priority phù hợp |
| T-35 | Flow tới cloud CDN IP có reputation thay đổi | Không gán malware chỉ từ IP reputation |
| T-36 | Public API request spike đồng thời marketing campaign | Phân biệt traffic hợp lệ với abuse |
| T-37 | Retry storm do client SDK bug | Availability case, sửa retry/backoff |
| T-38 | CDN/WAF chặn requests nhưng backend không ghi nhận | Xác định deny ở edge, không tự kết luận exploit |
| T-39 | WAF rule false positive làm khách hàng lỗi | Review rule, canary và rollback đúng scope |
| T-40 | DDoS-like synthetic metrics ảnh hưởng availability | Escalate SRE/network/IR theo severity |
| T-41 | Cloud private endpoint copy object mẫu cross-account | Dựa IAM/object audit, không chỉ Internet gateway |
| T-42 | SaaS-to-SaaS transfer test không có flow tại office firewall | Nhận diện coverage gap và SaaS API logs |
| T-43 | Kubernetes Pod egress bất thường nhưng shared node NAT | Correlate CNI flow với Pod UID/workload identity |
| T-44 | Kubernetes hostNetwork traffic khác Pod-based policy | Ghi host-specific coverage limit |
| T-45 | Firewall flow count tăng do sampling configuration | Xác minh schema và multiplier |
| T-46 | PCAP lab bị mất packets hoặc thiếu reverse direction | Không kết luận dựa trên stream thiếu |
| T-47 | Two alerts same source nhưng unrelated application paths | Không merge case chỉ theo IP NAT |
| T-48 | High-impact asset, evidence còn yếu | Ưu tiên enrichment sớm mà không auto-block |
| T-49 | Confirmed malicious-like event trong lab với containment giả lập | Escalation, owner, evidence và rollback đúng |
| T-50 | Playbook muốn chặn shared CDN IP | Bắt buộc blast-radius/human approval |
| T-51 | User/device được disable giữa phiên test | Đo session termination thực và log |
| T-52 | Source logs chứa test credentials vô tình | Redaction và data handling, không đưa vào ticket |
| T-53 | Evidence export được hash, copy và lọc | Ghi original/derivative riêng, chain of custody |
| T-54 | Triage workflow có alarm duplicate và parser issue | MTTT cải thiện mà không mất trường hợp thật |
| T-55 | Rule tuning làm giảm false positive nhưng cũng mất negative test | Không được deploy khi security acceptance fail |

### 28.2. Các yêu cầu nghiệm thu

Đối với mỗi test, báo cáo tối thiểu:

1. **Environment/scope được cấp phép**, test owner và case ID.
2. Detector/rule version, sensor vantage và original event link.
3. Source/destination fields và **semantics của IP/NAT/bytes/timestamp**.
4. Asset/user/workload identity ở thời điểm sự kiện, kèm confidence.
5. Một giả thuyết benign và một giả thuyết cần cảnh giác khi thích hợp.
6. Corroborating sources hoặc lý do chưa có.
7. **Observed facts / inferred findings / unknowns** được tách riêng.
8. Severity/priority và lý do.
9. Quyết định: close/monitor/investigate/escalate/approved containment.
10. Evidence integrity/privacy handling và next review point.

### 28.3. Negative tests phải chứng minh điều gì?

Một detector chưa tốt nếu chỉ phát hiện lưu lượng **bình thường tăng** mà bỏ qua **truy cập trái policy dù bytes thấp**, hoặc nếu nó chặn mọi job backup. Cần kiểm thử:

- **True suspicious activity** được ưu tiên phù hợp.
- **Benign spike** được xác minh, không bị containment bừa bãi.
- **Telemetry thiếu** được đánh dấu unknown và tạo nhiệm vụ thu thập.
- **Attribution sai do NAT/Pod IP** bị phát hiện trước kết luận.
- **Security controls** không vô tình bị bypass sau tuning.

### 28.4. Đo hiệu quả quy trình

| Chỉ số | Ý nghĩa |
| --- | --- |
| **MTTA** – Mean Time to Acknowledge | Thời gian tiếp nhận alert |
| **Time to initial triage decision** | Thời gian tới phân loại đầu tiên |
| **MTTD** – Mean Time to Detect | Độ trễ từ hoạt động tới detection |
| **MTTC** – Mean Time to Contain | Độ trễ tới containment có hiệu lực |
| **False-positive rate/precision** | Chất lượng rule trong cases đã review |
| **Escalation accuracy** | Cases chuyển cấp đủ bằng chứng và đúng đối tượng |
| **Attribution coverage** | % events có nguồn đúng asset/user/workload |
| **Telemetry visibility gaps** | DNS/TLS/IPv6/cloud/private endpoint chưa được thấy |
| **Duplicate alert ratio** | Nhiễu do rule và multi-sensor |
| **Case documentation completeness** | Khả năng handoff/audit |
| **Business impact from false containment** | Chất lượng quyết định và rollback |

**Các chỉ số có thể bị méo nếu định nghĩa hoặc data sources không nhất quán.** Ví dụ giảm số alerts bằng cách tắt logging không phải cải thiện detection.

## 29. Sai lầm thường gặp và câu hỏi tự kiểm tra

### 29.1. Những sai lầm cần tránh

| Sai lầm | Vì sao nguy hiểm | Thay thế |
| --- | --- | --- |
| “Alert High = Incident High” | Severity do detector đặt không xét asset/context | Tách confidence, impact và priority |
| “Traffic spike là tấn công” | Backup, campaign, retry và deployment đều tạo spike | Baseline + change/owner review |
| “Không có log nghĩa là không có traffic” | Blind spot, sampling, alternate routes | Ghi visibility limit và kiểm tra paths |
| “IP NAT là danh tính user” | Nhiều endpoints cùng public IP | NAT/DHCP/IdP/EDR correlation theo thời điểm |
| “Pod IP hiện tại luôn là Pod lúc alert” | IP có thể tái sử dụng | Pod UID và time-based workload inventory |
| “Bytes_out luôn là upload bytes” | Interface/sensor semantics khác nhau | Verified client-to-server direction |
| “Một flow TCP 443 nghĩa là HTTP POST” | TLS payload mã hóa, cổng không định danh app | Proxy/app L7 evidence |
| “TCP handshake thành công nghĩa là login thành công” | L4 không xác minh auth | Host/application authentication logs |
| “DNS query nghĩa là request tới server” | Resolve có thể không theo sau bởi connection | Flow/proxy/app corroboration |
| “TLS 1.3 luôn lộ server certificate” | Certificate handshake đã mã hóa | Đọc đúng phiên bản và vantage |
| “ECH vẫn cho thấy hostname thật” | Outer SNI có thể khác true destination | Alternative endpoint/proxy telemetry |
| “Reputation xấu chứng minh malware” | Shared hosting và feed stale | Corroborate process/behavior/source |
| “Heartbeat định kỳ chắc chắn là C2” | Monitoring/license checks cũng định kỳ | Process, owner, baseline và EDR |
| “RDP/SMB connections = lateral success” | Port reachability khác authentication | PAM/host auth and EDR evidence |
| “IDS signature = exploit successful” | Có thể chỉ thấy probe hoặc drop | Host/application aftermath |
| “Proxy CONNECT cho thấy URL/body” | Tunnel-only không giải mã | Ghi đúng visibility |
| “Chặn toàn bộ CDN IP để dừng một flow” | Nhiều ứng dụng dùng chung IP | Rule hẹp và blast-radius review |
| “NAT traffic luôn qua Internet SWG” | Cloud/private/IPv6/VPN routes khác | Inventory network paths |
| “DDoS dashboard cao thì phải block mọi nguồn” | Legitimate spikes và false positives | SRE + WAF/DDoS provider policy |
| “Asset criticality thấp nên bỏ mọi signal” | Có thể là staging foothold/lateral path | Xem exposure/relationships/context |
| “Một score mô hình thay thế điều tra” | Bias, stale baseline và missing data | Explainable evidence/human review |
| “Không cần giữ original evidence” | Khó đối chiếu parser/filter hoặc chain of custody | Original + derivative + hash |
| “Cứ lấy full PCAP của toàn công ty” | Privacy/credential/risk quá lớn | Bounded capture và approval |
| “Containment luôn tốt, không cần rollback” | Có thể ngắt backup/identity/core services | Owner, impact, narrow change, rollback |
| “Tuning giảm alert volume là thành công” | Có thể mất true-positive detections | Positive/negative acceptance tests |
| “Ứng dụng trả 403 nghĩa là firewall chặn” | Có thể là mesh/app authz | Layer-specific policy verdict |

### 29.2. Câu hỏi ôn tập

**Câu 1.** Vì sao một cảnh báo chưa phải là một incident?  
*Gợi ý:* Alert chỉ là tín hiệu; cần đánh giá bối cảnh, tác động và tiêu chí ứng phó.

**Câu 2.** Confidence và severity có khác nhau không?  
*Gợi ý:* Một cái nói độ chắc của bằng chứng, một cái nói tác động nếu giả thuyết đúng.

**Câu 3.** Một TCP flow lớn qua 443 có chứng minh upload file không?  
*Gợi ý:* Không. Cần direction, proxy/app events, transfer completion và data evidence.

**Câu 4.** Tại sao phải dùng NAT mapping theo thời gian thay vì chỉ public IP?  
*Gợi ý:* Shared NAT có nhiều endpoints, port translations thay đổi.

**Câu 5.** Nếu chỉ nhìn một chiều packet do asymmetric routing, có thể kết luận không có response không?  
*Gợi ý:* Không. Kiểm tra capture vantage và return path.

**Câu 6.** DNS query tới hostname lạ xác nhận gì?  
*Gợi ý:* Chỉ xác nhận query được sensor thấy, không nhất thiết kết nối hay transfer.

**Câu 7.** Tại sao SNI không thể luôn dùng làm hostname thật?  
*Gợi ý:* TLS visibility, ECH và proxy-side connection behavior.

**Câu 8.** Một IDS signature match có chứng minh exploit success không?  
*Gợi ý:* Không. Phải xem firewall disposition, host/app logs và outcome.

**Câu 9.** Khi phát hiện nhiều SSH/RDP attempts, nguồn nào giúp xác minh login thành công?  
*Gợi ý:* Authentication/PAM/host logs, EDR process.

**Câu 10.** Vì sao một cloud provider domain uy tín chưa bảo đảm transfer hợp lệ?  
*Gợi ý:* Unapproved tenant/account và dữ liệu ngoài quyền.

**Câu 11.** Đối với DDoS alert, business SLO có vai trò gì?  
*Gợi ý:* Availability/latency và customer impact quyết định urgency.

**Câu 12.** Một Pod IP hiện tại có thể dùng để xác định Pod lúc alert tuần trước không?  
*Gợi ý:* IP tái sử dụng; tra Pod UID/node/time.

**Câu 13.** Tại sao cần giữ bản gốc của PCAP?  
*Gợi ý:* Parser/filter có thể thay; chain of custody và integrity.

**Câu 14.** Khi nào nên escalate ngay dù confidence chưa cao?  
*Gợi ý:* Critical asset, active harm/availability impact hoặc IR emergency criteria.

**Câu 15.** Vì sao không nên tự block IP CDN từ một alert đơn lẻ?  
*Gợi ý:* Shared hosting, business blast radius và false positives.

**Câu 16.** Một alert còn thiếu user identity có được tự điền tên người từ public IP không?  
*Gợi ý:* Không; ghi unknown và bổ sung NAT/IdP/EDR mapping.

**Câu 17.** Benign true positive khác false positive thế nào?  
*Gợi ý:* Tín hiệu thực và khớp rule nhưng workflow hợp lệ so với detector/parser sai.

**Câu 18.** Tại sao ít alerts hơn không nhất thiết là detection tốt hơn?  
*Gợi ý:* Có thể do tắt logging hoặc làm rule bỏ lọt tình huống thật.

**Câu 19.** Zero Trust/VPN logs có đủ để biết dữ liệu nào đã bị export không?  
*Gợi ý:* Cần application/database/SaaS audit và authorization.

**Câu 20.** Một case triage hoàn chỉnh cần những nhóm thông tin nào?  
*Gợi ý:* Observed, inferred, unknown, confidence, priority, decision, evidence, owner/next action.

### 29.3. Bài tập kiến trúc và quy trình

Một tổ chức có **hai data centers, Kubernetes cluster production, một VPC cloud, người dùng VPN/ZTNA, một API public và hệ thống ERP/database**. SOC nhận đồng thời:

- Alert A: application Pod tăng HTTPS outbound gấp 8 lần.
- Alert B: một VPN client thử nhiều RDP/SMB connections tới subnet quản trị.
- Alert C: public API request rate tăng, latency và HTTP 503 cũng tăng.
- Alert D: CoreDNS queries tăng mạnh và NXDOMAIN nhiều.

Hãy thực hiện:

1. Xác định **asset owner, network paths và trust boundaries** của từng alert.
2. Tách **source identity, destination, protocol, timestamps, bytes direction, NAT**.
3. Liệt kê ít nhất **ba benign explanations** và **ba risk explanations** cho từng cảnh báo.
4. Vẽ sơ đồ sensor coverage: **EDR, IDS/IPS, flow, DNS, proxy, IAM, cloud audit, CNI, application**.
5. Chỉ rõ field nào **không quan sát được** do TLS/collector/identity limitations.
6. Thiết kế enrichment trong time window thích hợp, có clock drift handling.
7. Xếp confidence và priority riêng cho từng case; giải thích vì sao.
8. Xác định những bằng chứng cần trước khi gọi một luồng là **data exfiltration, lateral success hoặc DDoS**.
9. Viết pseudo SQL tổng hợp flows hoặc xác minh identity mapping theo nguồn có thẩm quyền.
10. Xác định lúc nào cần PCAP và phạm vi capture được phê duyệt.
11. Đề xuất ít nhất **hai containment options hẹp** cho mỗi tình huống rủi ro cao.
12. Nêu tác động/rollback của firewall rule, session revoke và rate-limit.
13. Tạo mẫu case record chứa **facts, inference, unknowns, owner, priority, evidence**.
14. Viết tối thiểu **10 positive/negative tests** với synthetic records.
15. Đề xuất các cải tiến telemetry/alert tuning cùng KPI trước-sau.

**Tiêu chí đạt:** các quyết định triage có dữ liệu nguồn đáng tin, có giải thích rõ, đủ bằng chứng để người tiếp nhận tiếp tục; không gán incident/exfil từ một tín hiệu đơn lẻ; những hành động tác động production phải đúng thẩm quyền và có đánh giá rủi ro.

## 30. Những điều cần ghi nhớ

- **Triage là giai đoạn ra quyết định có cấu trúc giữa detection và incident response.** Một alert chưa tự là incident.
- **Tách observed facts, inferred findings và unknowns**; không điền user, HTTP method hoặc data class từ những field chưa quan sát.
- **Confidence khác impact/severity/priority**. Một dấu hiệu chưa chắc trên critical asset vẫn có thể cần điều tra nhanh.
- **Đặt sensor đúng điểm và hiểu schema** quan trọng hơn nhìn dashboard đẹp: flow direction, NAT, sampling, packet loss và timezone có thể làm đổi kết luận.
- **Baseline phải theo vai trò, app, thời điểm, dữ liệu, đích nhận và change context**, không dùng một ngưỡng lưu lượng cho toàn doanh nghiệp.
- **NetFlow/firewall, DNS, TLS, proxy, IDS/IPS, EDR, IdP, cloud/Kubernetes và application logs** cung cấp các mảnh bằng chứng khác nhau; không nguồn nào đủ cho mọi câu hỏi.
- **TCP handshake, DNS query, IDS signature hoặc TLS connection không chứng minh truy cập dữ liệu hay khai thác thành công.**
- **TLS 1.3/ECH/HTTP/3 ảnh hưởng visibility**, nên không suy passive sensor luôn thấy certificate, true SNI hoặc HTTPS request body.
- **Định danh nguồn phải dựa NAT/DHCP/VPN/EDR/Pod UID theo event time**; một public IP/Pod IP dùng chung hoặc tái sử dụng không phải user identity.
- **Scan, beacon-like traffic, lateral movement, DoS và HTTPS exfil đều có benign explanations cần kiểm tra**, đồng thời vẫn phải xem xét rủi ro hoạt động.
- **PCAP là chứng cứ có giới hạn**, cần capture scope được phê duyệt, bảo vệ dữ liệu nhạy cảm, giữ nguyên bản và chain of custody khi cần.
- **Containment phải tương xứng với độ chắc và tác động**, có incident owner, thẩm quyền, kế hoạch rollback và kiểm tra các đường bypass.
- **Giảm số alert không đồng nghĩa tăng an toàn**; tuning phải giữ positive/negative tests và theo dõi visibility gaps, false positives và business impact.
- **Báo cáo triage tốt nói rõ điều đã biết, điều chưa biết, vì sao ưu tiên và bước tiếp theo**, giúp SOC/IR/SRE phối hợp mà không phải lặp lại điều tra.
- **Chỉ kiểm thử trên lab và dữ liệu synthetic hoặc hệ thống được cấp quyền**, không dùng scan, exploit, flood hay thu thập dữ liệu nhạy cảm ngoài phạm vi.
