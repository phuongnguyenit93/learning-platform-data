# Baseline lưu lượng bình thường

**Baseline lưu lượng mạng** là một mô hình mô tả những đặc điểm **thường gặp trong điều kiện vận hành đã xác định**: ai/ứng dụng nào trao đổi với dịch vụ nào, vào thời điểm nào, qua giao thức gì, với thông lượng, số kết nối, độ trễ và tỷ lệ lỗi ra sao. Baseline giúp đội vận hành và an ninh nhận ra **độ lệch khỏi hành vi kỳ vọng**, đánh giá sự cố mạng, phát hiện hoạt động đáng ngờ và đo tác động của thay đổi cấu hình.

Ví dụ, trong một hệ thống thương mại điện tử, lưu lượng HTTPS tới API đặt hàng có thể tăng đều vào giờ mua sắm, các job sao lưu tạo luồng lớn lúc rạng sáng, còn truy vấn DNS và kết nối cơ sở dữ liệu thay đổi theo số Pod hoạt động. Nếu đặt một ngưỡng cố định như **“trên 100 Mbps là bất thường”** cho mọi subnet, hệ thống sẽ vừa báo động sai với backup vừa bỏ sót những truy cập trái quyền có lưu lượng nhỏ.

**“Bình thường” không đồng nghĩa “an toàn” hoặc “được phép”.** Một lưu lượng quét nội bộ tồn tại nhiều tuần có thể trở thành một phần của baseline thống kê. Một lần triển khai phần mềm mới được phê duyệt có thể tạo khác biệt rất lớn nhưng hoàn toàn hợp lệ. Vì vậy baseline phải kết hợp **telemetry định lượng, danh mục ứng dụng, chính sách quyền truy cập, lịch thay đổi và threat model**, không chỉ dùng thuật toán phát hiện ngoại lệ.

Trong chương **Giám sát mạng và telemetry** của module **SECURITY_NETWORK_SECURITY**, bài học này liên kết với phân đoạn mạng, firewall, VPN, IDS/IPS, DNS, Wi-Fi, cloud/Kubernetes và phân tích lưu lượng. Trọng tâm là phương pháp đo, chuẩn hóa, học đặc điểm lưu lượng, xác minh độ tin cậy của baseline và biến độ lệch thành **cảnh báo có bằng chứng, có thể giải thích và có hành động phù hợp**.

> **Nguyên tắc:** Đo đúng **điểm quan sát**, đúng **chiều traffic**, đúng **đơn vị**, đúng **nhóm đối tượng** và đúng **khung thời gian** trước khi so với baseline. Một đồ thị đẹp nhưng mất nguồn dữ liệu, nhầm NAT hoặc trộn giờ backup với giờ kinh doanh có thể dẫn đến quyết định sai.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Định nghĩa baseline lưu lượng và phân biệt **normal, expected, authorized, secure, anomalous**.
2. Chọn đúng nguồn quan sát: **interface counters/SNMP, NetFlow/IPFIX, sFlow, PCAP, eBPF/CNI, firewall, DNS, TLS, cloud flow logs và application telemetry**.
3. Chuẩn hóa **bits/s, bytes/s, packets/s, flows/s, connections/s, latency, error/drop/retransmission metrics** mà không trộn các đại lượng.
4. Xây baseline theo **network zone, app/service, role, workload, endpoint, giờ/ngày/tuần và sự kiện nghiệp vụ**.
5. Xử lý **sampling, counter resets, clock skew, NAT, asymmetric routing, IP churn, missing logs và exporter drift**.
6. Áp dụng **median, percentile, interquartile range (IQR), median absolute deviation (MAD), rolling windows, ratios và seasonality** đúng điều kiện.
7. Thiết kế baseline cho **DNS, TCP/UDP, HTTPS/TLS, Internet egress, East–West traffic, VPN và cloud/Kubernetes**.
8. Xây detector đa tín hiệu, phân biệt **traffic spike do tải, cấu hình sai, outage hoặc hành vi đáng ngờ**.
9. Quản lý **cold start, change point, concept drift, model versioning, false positives và negative tests**.
10. Viết quy trình quan sát, truy vấn tổng hợp, mô hình chính sách, log giả lập, runbook và bài lab an toàn có thể kiểm chứng.

## 2. Baseline là gì và không phải là gì?

### 2.1. Định nghĩa theo phạm vi

Một baseline có thể được phát biểu thành:

> Với **dịch vụ Orders API** trong **môi trường production**, vào **thứ Hai–thứ Sáu, 09:00–17:00 giờ địa phương**, các Pods thuộc nhóm **frontend** thường phát sinh một phân phối **requests/s, bytes/s, active connections, p95 latency và 5xx rate** nằm trong khoảng được đo từ những kỳ vận hành được xác nhận hợp lệ.

Phát biểu này cụ thể hơn “mạng thông thường có 200 Mbps” vì nó chỉ rõ **đối tượng, điều kiện, metric và nguồn dữ liệu**.

### 2.2. Ba kiểu đường chuẩn

| Kiểu | Câu hỏi | Nguồn dữ liệu chính |
| --- | --- | --- |
| **Statistical baseline** | Những giá trị nào thường xảy ra? | Chuỗi thời gian, flow records, telemetry |
| **Operational expected baseline** | Hành vi nào được mong đợi theo kiến trúc và lịch vận hành? | Service inventory, SLO, deployment/backup schedules |
| **Security/authorization baseline** | Chủ thể nào được phép nói chuyện với đích/port nào? | Firewall policy, identity, NetworkPolicy, app authorization |

**Chỉ dùng statistical baseline có thể “học thuộc” hoạt động trái quyền.** Chỉ dùng security baseline dạng allowlist mà không đo thực tế có thể bỏ sót degradation hoặc spike trong những kết nối vốn được phép.

### 2.3. Độ lệch không phải bản án

| Quan sát | Cách diễn giải đúng |
| --- | --- |
| Lưu lượng tăng 4 lần sau campaign | Có thể hợp lệ; kiểm tra thay đổi và SLO |
| Một Pod mới kết nối dịch vụ lạ | Cần xác minh deployment, namespace và policy |
| DNS NXDOMAIN tăng | Có thể là misconfiguration, retry hoặc hành vi bất thường |
| Bytes outbound thấp nhưng kết nối tới host không được phép | Có thể là security policy violation dù không vượt throughput baseline |
| Lưu lượng giảm về 0 | Có thể sensor mất dữ liệu, service down hoặc thực sự không có traffic |
| Một flow lớn tới backup destination | Có thể theo lịch; cần owner và destination đúng |

### 2.4. Baseline là mô hình có thời hạn

Mạng thay đổi khi tăng số người dùng, phát hành phiên bản mới, đổi region, đổi CNI, chuyển HTTP/2 sang HTTP/3, bật IPv6 hoặc chuyển CDN. Baseline cần **chủ sở hữu, thời gian huấn luyện, điều kiện áp dụng, phiên bản và lịch rà soát**. Không tự coi một đường chuẩn học từ năm trước là vẫn phù hợp.

## 3. Vì sao cần baseline trong vận hành và bảo mật?

### 3.1. Vận hành

- Phát hiện đường truyền sắp bão hòa trước khi user thấy lỗi.
- Xác định thay đổi bất thường về retry, latency, packet loss, DNS errors.
- Kiểm chứng thay đổi route, firewall, VPN hoặc load balancing.
- Lập kế hoạch capacity, QoS và traffic engineering.
- So sánh trước/sau migration, deploy hoặc điều chỉnh kiến trúc.

### 3.2. An ninh

- Phát hiện kết nối **East–West** không đi theo service dependency.
- Ưu tiên điều tra những đích Internet mới/ngoài danh mục.
- Nhận diện tăng đột ngột các connection attempts, port diversity hoặc DNS errors.
- Tìm bất thường quanh VPN access, privileged workload hoặc service account.
- Đánh giá egress data volume cùng endpoint/data access telemetry để phát hiện **nghi vấn** thất thoát dữ liệu.
- Xác nhận một rule firewall/NetworkPolicy mới có làm traffic đi theo đường khác hay không.

### 3.3. Một spike có thể do nhiều nguyên nhân

~~~mermaid
flowchart TD
    OBS["Bất thường: outbound traffic tăng"] --> QUALITY{"Telemetry đầy đủ và đúng chiều?"}
    QUALITY -->|Không| Q["Kiểm tra exporter/NAT/counter/sampling"]
    QUALITY -->|Có| CHG{"Có campaign/deploy/backup được duyệt?"}
    CHG -->|Có| EXPECT["Đối chiếu SLO, scope và lịch"]
    CHG -->|Không hoặc chưa rõ| CORR["Liên kết process, identity, DNS, app, policy"]
    CORR --> ASSESS{"Có dấu hiệu vi phạm quyền/rủi ro?"}
    ASSESS -->|Chưa đủ bằng chứng| REVIEW["Theo dõi/triage có người phụ trách"]
    ASSESS -->|Có bằng chứng| IR["Containment phù hợp và điều tra"]
~~~

**Bất thường về lưu lượng là tín hiệu khởi đầu**, không tự xác định nguyên nhân.

## 4. Định nghĩa đơn vị và đối tượng đo

### 4.1. Các đại lượng mạng cốt lõi

| Metric | Đơn vị | Ý nghĩa và lưu ý |
| --- | --- | --- |
| **Throughput** | bit/s, Mbit/s, Gbit/s | Tốc độ truyền trong một cửa sổ; cần chiều và vị trí |
| **Byte rate** | B/s, KiB/s, MiB/s | Không đồng nhất với bit/s; phân biệt SI/binary prefixes |
| **Packet rate** | packets/s (pps) | Nhiều packet nhỏ có thể áp lực CPU dù bps thấp |
| **Flow rate** | flows/s | Phụ thuộc flow timeout/aggregation và định nghĩa exporter |
| **Connection attempts** | attempts/s | Không bằng established connections; cần TCP/SYN hoặc logs phù hợp |
| **Concurrent connections** | số lượng | Gauge tại thời điểm, không phải counter tích lũy |
| **Flow duration** | ms/s | Long-lived sessions làm kết quả khác short connections |
| **Connection/handshake failures** | count/rate | Cần nguồn quan sát có loại lỗi thích hợp |
| **RTT/latency** | ms | Network RTT, proxy latency và app response khác nhau |
| **Packet loss/retransmission** | % hoặc count | Phụ thuộc cách tính và điểm đo |
| **Drop/reject count** | count/rate | Thường do firewall/CNI/router; định nghĩa chính sách cụ thể |
| **DNS query/error rate** | queries/s, % NXDOMAIN/SERVFAIL | Phụ thuộc resolver/vị trí |

### 4.2. Chuyển đơn vị chính xác

Nếu đo **150 MiB trong 60 giây**, thông lượng quy đổi xấp xỉ:

\[
R_{\mathrm{bit/s}} = \frac{150\times 2^{20}\times 8}{60}\approx 20{,}971{,}520\ \mathrm{bit/s}\approx 20.97\ \mathrm{Mbit/s}.
\]

**MiB (2^20 bytes)** và **MB (10^6 bytes)** khác nhau. Một dashboard có đơn vị “Mbps” phải làm rõ là **megabits per second**, không phải megabytes per second.

### 4.3. Counter và rate

Một interface byte counter tăng từ \(C_{t-1}\) lên \(C_t\) trong \(\Delta t\) giây thì:

\[
\text{bitrate} = \frac{8(C_t-C_{t-1})}{\Delta t}.
\]

Chỉ dùng khi biết **counter monotonic và không bị reset/wrap**, đồng thời dữ liệu timestamp hợp lệ. Counter delta âm có thể do interface restart, exporter reset hoặc counter width overflow; không tự diễn giải thành traffic âm.

### 4.4. Chiều traffic

- **Ingress/egress tại một interface** phụ thuộc hướng nhìn của interface đó.
- **Client→server** và **server→client** phụ thuộc cách chuẩn hóa 5-tuple/session, khác khái niệm “in/out tại NAT gateway”.
- **Network egress bytes** không nhất thiết bằng số byte body HTTP upload do TLS overhead, retransmission, proxy và sampling.
- Với overlay tunnel, underlay thấy **packet outer** chứ không luôn thấy Pod-to-Pod inner flow.

Ghi cả **sensor_id, observation_point, source/destination before/after NAT, direction_basis, unit và sample interval** trong dữ liệu chuẩn hóa.

## 5. Nguồn telemetry: biết rõ công cụ đo được gì

| Nguồn | Những giá trị điển hình | Giới hạn cần hiểu |
| --- | --- | --- |
| **SNMP/interface counters** | Octets, packets, errors, discards, utilization | Tổng interface, không tự biết user/app; counter reset/wrap |
| **NetFlow/IPFIX** | 5-tuple, bytes, packets, start/end, direction hoặc NAT info khi exporter hỗ trợ | Aggregated/sampled, thiếu payload, schema khác |
| **sFlow** | Sampled packets và interface counters | Cần hiểu sampling rate, ước lượng và độ sai lệch |
| **PCAP/SPAN/TAP** | Packet-level network observations tại điểm đặt | Dung lượng lớn, privacy, packet loss; TLS payload mã hóa |
| **eBPF/host telemetry** | Kernel/socket/flow/process metadata tùy agent | Hook/permissions/coverage khác nhau |
| **CNI/NetworkPolicy telemetry** | Pod/namespace, policy verdict, flow identity | CNI-specific; hostNetwork/secondary paths có thể khác |
| **Firewall/IDS/IPS** | Allow/drop, rule, signature, traffic metrics | Không ghi mọi allow; signature ≠ proof of compromise |
| **DNS resolver** | Queries, NXDOMAIN/SERVFAIL, latency, RCODE | Không thấy cache/proxy-side DNS hoặc resolver ngoài |
| **SWG/TLS proxy** | User/host/URL/method nếu thấy HTTP; bytes và policy | CONNECT tunnel ≠ giải mã HTTPS; bypass vẫn tồn tại |
| **Cloud flow logs** | VPC/VNet flow tuple, actions, counters theo provider | Aggregation/capture gaps/NAT/field semantics |
| **Ingress/service mesh** | Service request rate, mTLS identity, status, latency | Không thấy traffic đi vòng gateway/mesh |
| **Application/APM** | HTTP/gRPC requests, errors, response times, business operations | Không thay kết nối L3/L4 ngoài app |
| **EDR/endpoint DLP** | Process, file/identity, connection ở endpoint | Endpoint coverage, OS support và privacy |

### 5.1. Không chỉ đếm những gì collector nhìn thấy

Một collector đặt tại **Internet firewall** có thể không thấy traffic giữa Pods trên cùng node; cloud NAT không nhất thiết thấy lưu lượng tới **private cloud endpoint**; SWG của nhân viên không thể tự quan sát mọi workload serverless.

### 5.2. Sampling và estimation

Một **1:1000 sample** không có nghĩa mọi flow được nhân đúng 1000 rồi chính xác tuyệt đối. Khả năng ước lượng phụ thuộc **sFlow packet sampling, exporter flow sampling, thời gian quan sát, packet sizes và thuật toán**. Với rare events, sampling có thể bỏ sót hoàn toàn; phải gắn **coverage, sample rate và confidence**.

### 5.3. Flow record khác packet

NetFlow/IPFIX thường xuất **records tổng hợp**, không phải mọi packet. Exporter có active/inactive timeouts: một kết nối dài có thể tạo nhiều records. Việc đếm **“flow count”** có thể thay khi cấu hình timeout đổi mà ứng dụng không thay. Cần ghi **exporter version, template ID, timeout và sampling**.

### 5.4. Không có log ≠ không có traffic

Thiếu record có thể do mất sensor, network path đổi, log quota, sampling, agent crash hoặc data pipeline lỗi. Nên có dashboard **telemetry freshness/coverage** và cảnh báo riêng cho **mất quan sát**, không gán giá trị 0 cho dữ liệu thiếu.

## 6. Kiến trúc thu thập và tính baseline

~~~mermaid
flowchart LR
    R["Router/Switch: SNMP/IPFIX"] --> ING["Telemetry ingestion"]
    FW["Firewall/IDS/SWG"] --> ING
    K["Cloud/K8s/CNI"] --> ING
    D["DNS + TLS + Endpoint"] --> ING
    A["App/APM/Change events"] --> ING
    ING --> NORM["Validate + normalize<br/>time/units/identity/NAT"]
    NORM --> STORE[("Time-series / flow storage")]
    STORE --> B["Baseline by service/zone/time"]
    CMDB["App ownership + policy inventory"] --> B
    B --> DET["Anomaly and policy checks"]
    DET --> CASE["Alert with evidence/limitations"]
    CASE --> SOC["SOC/SRE triage"]
    SOC -. "Verified labels, tuning, changes" .-> B
~~~

### 6.1. Tách pipeline quan sát khỏi baseline học

Một kiến trúc tốt phân biệt:

1. **Raw ingestion:** telemetry nhận được, với source và timestamp.
2. **Normalization:** đổi units, nhận diện NAT/identity, kiểm tra schema.
3. **Aggregation:** tính metric theo bucket thời gian hợp lệ.
4. **Baseline training:** học phân phối trên dữ liệu đã được kiểm chứng.
5. **Detection:** so với đường chuẩn và kiểm tra policy/known events.
6. **Triage/feedback:** quyết định alert nào thực sự sai lệch có ý nghĩa.

Nếu collector ngừng gửi dữ liệu, bước 3 phải tạo **missing-data state** thay vì coi service chỉ còn 0 Mbps.

### 6.2. Kiến trúc có thể mở rộng

- Giữ **các metric tính sẵn** theo 1 phút/5 phút cho high-volume traffic.
- Lưu raw/unsampled records theo nhu cầu điều tra và retention được phê duyệt.
- Đánh dấu **cardinality cao** như IP, Pod UID, ephemeral ports để quản lý chi phí.
- Tránh gộp tất cả endpoints vào một histogram không còn giải thích được.
- Giám sát ingestion lag, dropped records, schema drift và processing errors.

### 6.3. Bảo vệ dữ liệu và chính hệ thống giám sát

Telemetry có thể tiết lộ user, nội dung domain, topology, resource names và data movement. Cần **RBAC, encryption, retention, access audit, secrets management và separation of duties**. Một attacker kiểm soát pipeline log có thể làm baseline sai hoặc che alert; tính toàn vẹn và khả dụng của telemetry là một phần của thiết kế.

## 7. Preflight: danh mục tài sản, traffic và quyền

Trước khi huấn luyện, hãy xác định:

| Nhóm | Trường cần có | Câu hỏi |
| --- | --- | --- |
| **Network zones** | Corp, data, DMZ, cloud, Kubernetes, VPN, partner | Ranh giới tin cậy ở đâu? |
| **Resources** | App ID, Service, FQDN, CIDR, owner, environment | IP/hostname đại diện cho ứng dụng nào? |
| **Identities** | User, workload/service account, device, Pod/VM ID | Ai tạo traffic? |
| **Protocols** | TCP/UDP/QUIC, DNS, SSH, HTTPS, ports | Giao thức và cổng thực tế là gì? |
| **Normal schedules** | Backup, batch, payroll, campaign, deploy windows | Spike nào được phê duyệt? |
| **Security policies** | Firewall/NetworkPolicy/Zero Trust/CASB rules | Flow nào được phép? |
| **Data sources** | Sensor owners, ingestion interval, coverage | Metric nào đáng tin? |
| **Operations** | Change tickets, SLO, maintenance windows | Khi nào baseline phải loại trừ/đổi version? |

### 7.1. Từ IP đến danh tính ổn định

Pod, VM autoscaling và VPN users có thể thay IP liên tục. Baseline theo **IP đơn thuần** dễ bị lỗi khi IP được tái sử dụng. Ưu tiên **service ID, Pod UID/namespace, cloud instance ID, user+device session ID và app owner**, có correlation tới IP/NAT theo thời điểm.

### 7.2. Baseline theo vùng và vai trò

Một DNS resolver thường có hàng nghìn kết nối ngắn; một database có tương đối ít nguồn và port; một ingress gateway phục vụ nhiều clients. Không dùng cùng một baseline **flows/s** cho cả ba. Chia theo **peer group có cấu trúc và mục đích nghiệp vụ tương đồng**.

### 7.3. Mô tả phạm vi mà mô hình chưa hỗ trợ

Nếu collector chỉ thấy IPv4 và TCP, cần ghi **IPv6/UDP/cloud private endpoints not covered**, không gọi baseline là “toàn bộ egress”. Khi bổ sung nguồn telemetry mới, kết quả tăng đột ngột có thể chỉ do **coverage tăng**, không phải traffic thật tăng.

## 8. Chuẩn hóa telemetry trước khi học

### 8.1. Quy tắc timestamp

Nên lưu **event time** theo UTC cùng với **time zone/offset gốc và sensor time source** khi cần; thể hiện ngày/giờ địa phương ở bước hiển thị. Phân biệt:

- **Event time:** thời điểm traffic thực sự xảy ra/flow kết thúc.
- **Collection time:** thời điểm collector nhận record.
- **Processing/ingestion time:** thời điểm pipeline xử lý.

Một collector bị delay 10 phút không có nghĩa mạng vừa có đợt traffic spike. Khi so baseline, dùng đúng mốc thời gian và cho phép **late-arriving events**.

### 8.2. Đồng hồ lệch

Nếu firewall báo 09:00:00 còn EDR báo 09:03:00 cho cùng phiên, correlation có thể sai. Giám sát **NTP/time sync status, clock offset, clock drift và timestamp precision**. Cần có mức dung sai có căn cứ chứ không chọn một time window rất rộng làm ghép nhầm mọi sự kiện.

### 8.3. Chuẩn hóa schema

Một record logic có thể gồm:

~~~text
event_time_utc, observation_point, sensor_id, source_type
src_ip_original, src_port_original, src_ip_translated, src_port_translated
dst_ip_original, dst_port_original, dst_ip_translated, dst_port_translated
transport_protocol, ip_family, direction_basis
bytes_up, bytes_down, packets_up, packets_down
first_seen, last_seen, duration_ms, sampling_method, sampling_rate
network_zone, service_id, workload_id, identity_ref
action, rule_id, exporter_version, evidence_quality
~~~

**Chỉ điền những fields có trong nguồn có thẩm quyền**. Nếu firewall chỉ có tổng bytes, để bytes_up/bytes_down là **unknown**, không suy tỷ lệ hai chiều từ tổng bytes.

### 8.4. Deduplication

Cùng một gói/flow có thể được quan sát tại **host, switch, firewall, load balancer và cloud flow collector**. Cộng các byte counters từ nhiều điểm có thể nhân đôi traffic. Với multi-point telemetry:

1. Chọn **canonical observation point** cho từng metric.
2. Dùng connection/flow IDs và timestamps khi có.
3. So sánh **mỗi hop** riêng để đo loss/NAT thay vì sum tùy tiện.
4. Đánh dấu trường hợp không thể xác định trùng một cách đáng tin.

### 8.5. Cardinality và ephemeral identities

IP/port ephemeral, Pod UID và per-request IDs tạo số lượng time-series cực lớn. Nên phân tầng:

- **Aggregate baseline:** service + zone + 5-minute slot.
- **Drill-down:** top talkers, exact process/user, trace/request ID.
- **Incident data:** raw events được lưu có hạn và truy cập kiểm soát.

Không nên dùng mọi 5-tuple làm một time series dài hạn nếu chỉ cần capacity và traffic-shape detection ở service level.

### 8.6. Missing so với zero

| Giá trị | Ý nghĩa đúng |
| --- | --- |
| **0 bytes trong bucket có coverage xác minh** | Có bằng chứng sensor ghi nhận không có bytes theo phương pháp đó |
| **NULL/missing bucket** | Không có dữ liệu đủ để kết luận |
| **0 do exporter restart** | Cần nhận diện counter reset, không nối delta |
| **0 do ACL drop trước điểm sensor** | Không suy client không cố kết nối |
| **0 do dịch vụ down** | Có thể là sự cố, không phải baseline mới |

## 9. Phân nhóm baseline theo network zone, app và identity

### 9.1. Vì sao một baseline toàn cluster có ít giá trị?

Giả sử tổng traffic cluster là 3 Gbit/s. Một Pod gửi 50 Mbit/s bất thường tới một đích không được phép có thể bị che trong aggregate; ngược lại một đợt backup đẩy tổng lên 5 Gbit/s có thể bị cảnh báo dù an toàn. Cần tách **mục đích nghiệp vụ và ranh giới tin cậy**.

### 9.2. Baseline đa cấp

| Cấp | Key minh họa | Dùng cho |
| --- | --- | --- |
| **Organization/region** | region, environment | Capacity và network-level outages |
| **Zone-to-zone** | src_zone, dst_zone, protocol | East–West segmentation, policy drift |
| **Service-to-service** | src_service, dst_service, port | Application dependency và lateral movement |
| **Role/device group** | user_role, managed_device | Remote access/SaaS behavior |
| **Workload identity** | namespace, service account, workload label | Kubernetes và cloud workload egress |
| **Endpoint/process** | host_id, process_entity_id | Suspicious process behavior |
| **Data destination/account** | approved SaaS tenant, cloud account ID | Data transfer authorization context |

Một nhóm có **quá ít dữ liệu** sẽ khó ước lượng percentile hoặc MAD. Có thể dùng **fallback peer baseline** (tương tự role/app) và gắn confidence thấp, thay vì giả một mức “bình thường” chính xác.

### 9.3. Directional service pairs

Trong một cụm:

~~~text
frontend → orders-api:8443   = expected
orders-api → postgres:5432   = expected
postgres → public-internet   = normally prohibited
build-job → artifact-store   = expected in release window
hr-portal → dev-workstation  = not in approved dependency inventory
~~~

**Nhiều traffic “không xuất hiện trong baseline” nhưng đã có policy cấm** có thể cần cảnh báo dù volume nhỏ. Mục đích của statistical baseline không thay danh mục kết nối được duyệt.

### 9.4. Phân biệt chiều yêu cầu và phản hồi

Database trả nhiều dữ liệu về app là bình thường theo workload; dùng **outbound ở interface DB** không có nghĩa dữ liệu đang thoát Internet. Cần biết **zone/peer, connection initiator, direction và nơi NAT/proxy** để phân biệt service response hợp lệ với dữ liệu bị xuất ngoài.

### 9.5. Risk-weighted segmentation

Với payment/HR/identity infrastructure, nên dùng những baseline hẹp hơn:

- Approved peer set và port.
- Dung lượng dữ liệu/cường độ truy vấn đã được phê duyệt.
- Thời điểm quản trị/batch windows.
- Source/workload identity và device posture.
- Alert sensitivity theo asset/data classification.

Không nên đặt chế độ auto-block giống nhau cho môi trường lab và hệ thống production nhạy cảm; ảnh hưởng sai tích cực khác nhau.

## 10. Seasonality: giờ trong ngày, ngày trong tuần và sự kiện kinh doanh

Một hệ thống công ty có thể có:

- Giờ làm việc tăng web/app requests.
- Thứ Hai tăng SSO/VPN connections khi nhân viên trở lại.
- Cuối tháng có báo cáo tài chính.
- Rạng sáng có backup/batch.
- Thời điểm sale có peak requests và CDN egress.
- Ngày lễ có khác biệt traffic người dùng theo vùng.

### 10.1. Bucket theo thời gian

| Bucket | Phù hợp | Nhược điểm |
| --- | --- | --- |
| **30 giây–1 phút** | Burst/packet rate/short incident | Nhiều noise, ingestion cost |
| **5 phút** | Web traffic, network capacity và common anomaly | Có thể làm mượt burst rất ngắn |
| **15–60 phút** | User/activity baseline và trend | Che một số incident ngắn |
| **1 ngày/tuần** | Capacity planning, SaaS upload totals | Không phát hiện kịp sự kiện real-time |

Chọn theo **SLO và tốc độ phản ứng cần thiết**, không dùng một bucket cho tất cả. Với một metric 5xx rate, sự cố 30 giây có thể bị che nếu chỉ nhìn trung bình giờ.

### 10.2. Seasonality theo calendar

Một cách phân nhóm đơn giản:

~~~text
baseline_key = (
    environment,
    service,
    traffic_direction,
    day_type,           # weekday / weekend / holiday / special campaign
    hour_of_day,
    deployment_phase
)
~~~

Tính giờ địa phương ở bước trình bày hoặc nhóm theo lịch ứng dụng; nếu vận hành đa vùng, có thể dùng **calendar/timezone riêng của từng dịch vụ**. Với khu vực có đổi giờ mùa hè, tránh ghép nhầm hai giờ địa phương giống nhau; lưu UTC và timezone đầy đủ.

### 10.3. Chú ý ngày sự kiện

Một campaign hợp lệ có thể là **outlier được phê duyệt** chứ không nên đưa ngay vào baseline lâu dài. Đánh dấu event bằng **change/calendar record** để so theo **event-aware baseline**, thay vì tăng ngưỡng vĩnh viễn sau một lần sale.

### 10.4. Baseline trước và sau thay đổi

Khi triển khai HTTP/3, chuyển CDN hoặc bật cache, số TCP connections, UDP 443 flows và bytes ở network gateway có thể thay đổi dù requests/s không tăng. Ghi **change point** và tạo **model version mới** sau khi kiểm chứng trạng thái vận hành.

### 10.5. Tránh học từ maintenance windows

Trong thời gian cắt mạng, traffic có thể giảm về 0. Nếu đưa outage vào training như vận hành bình thường, ngưỡng thấp sẽ bị kéo xuống. Cần đánh dấu **maintenance, incident và telemetry-gap windows** trước khi tính thống kê.

## 11. Các thống kê thực dụng: median, quantile, IQR và MAD

### 11.1. Mean và standard deviation

Trung bình:

\[
\mu=\frac{1}{n}\sum_{i=1}^{n}x_i.
\]

Độ lệch chuẩn mô tả độ phân tán nhưng **nhạy với outliers và heavy-tailed traffic**. Một lần backup 120 GB có thể kéo mean rất xa hành vi thường ngày của một ứng dụng nhỏ.

### 11.2. Median và percentile

- **Median (p50):** 50% quan sát không vượt giá trị đó.
- **p95/p99:** các quantile dùng để mô tả phần đuôi phân phối theo cùng đối tượng/cửa sổ.
- **IQR:** \(Q_3-Q_1\), phản ánh 50% trung tâm của phân phối.

Ví dụ 5-minute throughput (Mbit/s):

~~~text
12, 13, 14, 14, 15, 15, 16, 16, 17, 90
Median ≈ 15
Mean   = 22.2
~~~

Giá trị 90 có thể là backup hoặc incident; median ổn định hơn mean. Đây là **tập số giả lập quá nhỏ để dùng làm baseline production**.

### 11.3. Median Absolute Deviation

\[
\mathrm{MAD}=\operatorname{median}_i(|x_i-\operatorname{median}(x)|).
\]

Với giả định phân phối gần chuẩn, đôi khi dùng **scaled MAD ≈ 1.4826 × MAD** để so sánh độ lệch dạng robust. Nhưng **không coi scaled MAD là độ lệch chuẩn thực** trong traffic có phân phối lệch mạnh, zero-inflated hoặc nhiều mùa.

### 11.4. Quy tắc IQR minh họa

Một detector có thể đánh dấu quan sát vượt \(Q_3+1.5\times\mathrm{IQR}\) để **xem xét**, không phải tự kết luận tấn công. Với traffic heavy-tail hoặc theo lịch backup, ngưỡng này có thể báo động nhiều.

### 11.5. Quantile có phụ thuộc định nghĩa

Các thư viện/hệ thống tính percentile có nhiều phương pháp nội suy, và **p95 của daily totals không bằng p95 của 5-minute samples**. Khi so baseline, phải giữ **cùng metric definition, bucket size, aggregation method và quantile algorithm**.

### 11.6. Ratio và relative deviation

Một tỷ lệ:

\[
r = \frac{x_{\mathrm{observed}}}{\max(x_{\mathrm{baseline}},\epsilon)}
\]

có thể hữu ích, nhưng nếu baseline gần 0 thì một flow nhỏ sẽ tạo ratio rất lớn. Dùng thêm **absolute minimum, count/volume constraints, asset risk** và thời gian quan sát. Với các kết nối **bị cấm**, không cần chờ bytes vượt ngưỡng.

### 11.7. Không tự mặc định traffic phân phối chuẩn

Traffic network có thể **bursty, heavy-tailed, nhiều số 0 và phụ thuộc lịch**. Chọn model sau khi xem histogram/seasonality, không gắn z-score từ normal distribution cho mọi service. Với samples ít và dữ liệu có missing, baseline nên thể hiện **uncertainty/low confidence** thay vì một ngưỡng “chắc chắn”.

## 12. Chất lượng dữ liệu và độ tin cậy của baseline

### 12.1. Dữ liệu tốt cần đo được

| Tiêu chí | Cách đánh giá |
| --- | --- |
| **Coverage** | Bao nhiêu nodes/interfaces/users/zones có sensor? |
| **Freshness** | Event cuối cùng đến khi nào, pipeline lag bao nhiêu? |
| **Completeness** | Có đủ expected buckets/records, fields? |
| **Accuracy** | Counter reset, sampling, units, direction được xử lý? |
| **Consistency** | Schema/exporter versions, timezone, IDs đồng nhất? |
| **Uniqueness** | Có duplicate records từ nhiều collectors? |
| **Identity fidelity** | NAT/Pod/workload/user attribution được liên kết đúng? |
| **Security** | Logs có bảo vệ integrity, access và retention? |

### 12.2. Training window

Không có quy tắc “mặc định đủ chính xác trong 7 ngày” cho mọi ứng dụng. **1–4 tuần** có thể dùng để khảo sát một số hệ thống ổn định, nhưng workload có **payroll cycle, month-end processing, seasonal sale, patch Tuesday hoặc DR drills** cần nhiều kỳ hoặc baseline theo sự kiện. Độ tin cậy phụ thuộc **số quan sát hữu ích, tính đại diện và changes**, không phải số ngày đơn thuần.

### 12.3. Holdout validation

Tách **training period** khỏi **validation/holdout period**. Đánh giá detector trên cả:

- Những ngày vận hành hợp lệ, có spike được phê duyệt.
- Sự cố đã được phân loại và có evidence.
- Synthetic abnormal events trong lab.
- Telemetry gaps/reset/sampling changes.

Một model quá khớp training data có thể phát ra nhiều false alarms khi deploy thực tế.

### 12.4. Data poisoning và contaminated baseline

Nếu attacker/ứng dụng lỗi đã tạo lưu lượng trái chính sách trong thời gian học, “normal” thống kê có thể chứa hoạt động đó. Vì vậy phải:

1. Rà **approved network reachability và dependency matrix**.
2. Loại những windows đã có incident/outage hoặc gắn nhãn rõ.
3. So các peer groups có tương đồng hợp lý.
4. Không auto-learn một đích mới có rủi ro cao chỉ vì lặp nhiều ngày.
5. Yêu cầu **owner review** khi baseline thay đổi lớn.

### 12.5. Đổi collector cũng là đổi phương pháp đo

Khi thay IPFIX exporter, CNI hoặc cloud flow log format, bytes/flow counts có thể nhảy do **sampling, active timeout, NAT observation point hoặc trường mới**. Baseline mới phải đánh dấu **telemetry version**, so sánh song song và xác minh trước khi nối chuỗi.

## 13. NAT, proxy, tunnel và đường quan sát

### 13.1. NAT làm sai attribution nếu không ghép session

Một firewall ở Internet edge thấy một **public NAT IP**, trong khi bên trong có hàng trăm devices/Pods. Attribution đáng tin cần **pre-NAT tuple, translated tuple, timestamp, user/workload ID và flow ID**.

~~~text
Endpoint:  10.12.5.77:53012   → HTTPS destination
NAT:       198.51.100.20:62120 → 203.0.113.40:443
Observed:  Internet firewall sees public NAT tuple
Identity:  endpoint-017 / workload-xyz via authorized NAT mapping
~~~

Các IP ví dụ thuộc dải **documentation-only**; không đại diện hệ thống vận hành thực tế.

### 13.2. Proxy aggregation

Nếu 1.000 người dùng đi qua SWG, network firewall có thể thấy **SWG IP→SaaS IP** thay vì từng endpoint. Baseline theo **SWG public IP** hữu ích cho capacity nhưng rất hạn chế để phát hiện người dùng riêng lẻ. Cần proxy auth logs và IdP/endpoint correlation.

### 13.3. Overlay và CNI

Traffic Pod-to-Pod qua VXLAN/Geneve có thể được gói vào node-to-node tunnels; underlay sensor thấy **node IP/tunnel bytes**, không thấy inner service ports. Với direct routing/VPC-native, Pod IP có thể hiển thị ở một số điểm. Cần chọn **eBPF/CNI/host sensor hoặc flow logs phù hợp** để có baseline theo workload.

### 13.4. Asymmetric routing

Yêu cầu và phản hồi có thể đi qua **khác firewall/sensor**. Một sensor chỉ thấy một chiều có thể báo upload/downlink bất thường hoặc suy kết nối lỗi. Phải đo **observation coverage** và sử dụng nguồn đa điểm/connection-tracking khi phù hợp, không tự bịa chiều bị thiếu.

### 13.5. VPN, IPsec và các tunnel

Sensor **ngoài VPN tunnel** có thể chỉ thấy tunnel endpoints và aggregate encrypted traffic, còn sensor phía sau VPN gateway thấy inner client/service flows. Baseline phải tách **tunnel capacity** với **người dùng/ứng dụng bên trong**; không đo packet size bên ngoài rồi quy trực tiếp cho từng user.

### 13.6. IPv4 và IPv6

Dual-stack có thể tạo hai đường tới cùng dịch vụ. Khi bật IPv6, baseline IPv4 có thể giảm vì clients chuyển sang IPv6, trong khi **tổng traffic application** không đổi. Xây dashboard **per address family** và **combined service view**, đồng thời xác minh IPv6 firewall và DNS AAAA.

## 14. Baseline theo giao thức: TCP, UDP, ICMP và QUIC

### 14.1. TCP

Các metric hữu ích:

- New/established connections, SYN attempts và failures **khi sensor đủ dữ liệu**.
- RTT, retransmissions và resets nếu TCP instrumentation hỗ trợ.
- Connection duration, bytes per flow và concurrent sessions.
- Destination ports, source/service pair diversity.

Một **SYN attempt spike** có thể là client retry, kiểm tra sức khỏe, deployment mới hoặc dấu hiệu quét/DoS; phân biệt bằng **response/handshake success, destination diversity, app logs và change events**.

### 14.2. UDP

UDP không có TCP handshake, nên không được gọi UDP packet sequence là **“established TCP connection”**. Baseline UDP theo **datagrams/s, bytes, flows defined by timeout, source/destination distribution và application-layer status** khi có.

Ví dụ DNS qua UDP có query-response ratio; QUIC/HTTP/3 có session semantics riêng. Không áp cùng ngưỡng **SYN failures** cho UDP.

### 14.3. ICMP

ICMP có thể phản ánh **network diagnostics, PMTU discovery, reachability** hoặc lưu lượng bất thường. Phân biệt **ICMP types/codes**, source/destination zones và expected network behaviors. Chặn tất cả ICMP chỉ vì volume tăng có thể làm hỏng **Path MTU Discovery** và chẩn đoán sự cố.

### 14.4. HTTP/3/QUIC

QUIC thường chạy trên UDP 443 và dùng cơ chế bảo mật tương ứng. Số “connections” ở sensor phụ thuộc cách đo; migration HTTP/2→HTTP/3 có thể làm TCP 443 giảm, UDP 443 tăng mà **request rate không đổi**. Baseline theo app/protocol version và dữ liệu proxy/APM khi có.

### 14.5. TLS metadata không tương đương payload

TLS 1.3 và ECH làm thay đổi handshake visibility. Passive sensor có thể không nhìn thấy HTTP Host/path/body hay server certificate như với các phiên TLS cũ. Dùng **connection metrics, endpoint/app/proxy telemetry và authorization data**; không khẳng định “đã thấy upload file” chỉ vì TCP/443 bytes tăng.

## 15. Baseline DNS: query mix, lỗi và hành vi resolver

DNS không chỉ là một bước phụ khi truy cập website: biến động DNS có thể phản ánh **service discovery, retry storm, lỗi CoreDNS/resolver, client misconfiguration hoặc hoạt động đáng ngờ**.

### 15.1. Các metric hữu ích

| Metric | Ý nghĩa |
| --- | --- |
| Queries/s theo resolver/client group | Tải và thay đổi use cases |
| RCODE distribution | NOERROR/NXDOMAIN/SERVFAIL/REFUSED và lỗi |
| p50/p95/p99 resolution latency | Chậm trễ DNS so với bình thường |
| Cache hit ratio khi resolver có hỗ trợ | Tác động của cache và TTL |
| A/AAAA/PTR/SRV/TXT query mix | DNS use cases, dual-stack, service discovery |
| Unique queried domain counts | Độ đa dạng, phụ thuộc normalization |
| New/rare FQDN theo workload/role | Thay đổi ứng dụng hoặc nghi vấn |
| Resolver/upstream error count | Trạng thái hệ thống phân giải |

### 15.2. NXDOMAIN spike không tự là tấn công

Nguyên nhân có thể gồm:

- Application loop hoặc lỗi hostname.
- Kubernetes DNS search domains/ndots tạo nhiều queries.
- DNS record bị xóa sau deployment.
- Thiết bị có captive portal hoặc domain validation workflow.
- Truy vấn tới những domain không hợp lệ trong môi trường test.

Phân biệt bằng **client/process, queried domain pattern, response time, rate theo baseline, change tickets**. Không kết luận malware hoặc DNS tunneling chỉ từ NXDOMAIN tăng.

### 15.3. DNS cache và tên miền mới

Không có DNS query trong 5 phút không có nghĩa không có kết nối: OS/browser cache, proxy-side lookup hoặc DNS over HTTPS/DoT có thể thay quan sát. Khi dùng DNS telemetry để liên kết flow, áp dụng **TTL, query timestamps và độ tin cậy của mapping**; không gán một IP CDN dùng chung cho một domain duy nhất.

### 15.4. Domain baseline và approval

Domain mới tới software update service được phê duyệt có thể hợp lệ; domain xuất hiện nhiều năm vẫn có thể trái chính sách. Cần song song hai câu hỏi:

1. **Có khác baseline không?**
2. **Có thuộc danh sách ứng dụng/dịch vụ được phép không?**

### 15.5. DNS và lưu lượng IPv6

Khi client bắt đầu ưu tiên AAAA/IPv6, A query rate hoặc IPv4 flows giảm mà tổng requests không giảm. Xây baseline **A vs AAAA, IPv4 vs IPv6** để tránh hiểu nhầm thay đổi routing là tấn công hoặc outage.

## 16. Baseline HTTPS/TLS và dịch vụ Internet

### 16.1. Những trường có thể đo

- TCP/443 và UDP/443 flows/s theo **app, user/device và region**.
- Client-to-server vs server-to-client bytes khi sensor có direction.
- TLS handshake success/failure nếu được gateway/proxy ghi nhận.
- TLS protocol version/cipher policy outcomes ở nơi có quan sát.
- Approved hostname/category/account/tenant theo dữ liệu proxy/CASB khi có.
- HTTP requests/s, 4xx/5xx, URI route classes và p95 latency tại terminating proxy/APM.
- Certificate expiry/rotation events ở **server/gateway management telemetry**.

### 16.2. Phân biệt flow, request và dữ liệu

| Quan sát | Kết luận có thể rút |
| --- | --- |
| Outbound TCP 443 bytes tăng | Lưu lượng mạng tăng ở điểm đó |
| Proxy thấy CONNECT tới hostname | Có request tạo tunnel tới đích được chỉ định |
| Proxy terminate TLS và log POST 201 | Có HTTP POST được ứng dụng/proxy quan sát; xem thêm body/upload evidence |
| Application audit ghi upload object | Có action nghiệp vụ theo log ứng dụng |
| SaaS audit xác nhận external share | Có thay đổi sharing permission trong SaaS |

**Không chuyển một tín hiệu yếu thành thông tin chưa được quan sát.** Flow 200 MB không được mô tả thành “đã đánh cắp file 200 MB”.

### 16.3. Loại trừ thay đổi protocol

Khi bật **HTTP/2 multiplexing**, một browser có thể gửi nhiều requests trên ít kết nối TCP hơn. Khi bật **HTTP/3**, UDP 443 có thể tăng. Vì vậy hãy baseline **application requests/latency** song song **transport flows/connections** để thấy thay đổi do network stack, không tưởng tượng ra tăng/giảm hoạt động người dùng.

### 16.4. Approved SaaS tenant khác approved domain

Một domain cloud storage có thể phục vụ hàng triệu accounts. Baseline lưu lượng tới provider theo domain hữu ích cho capacity, nhưng để phát hiện chuyển dữ liệu trái quyền cần **tenant/account identification, source data labels và policy** khi công nghệ cho phép.

### 16.5. SNI, ECH và TLS 1.3

SNI plaintext có thể giúp nhóm hostname, nhưng ECH làm thông tin true hostname có thể không thấy tại passive observer. Server certificates trong TLS 1.3 thường không được nhìn thấy bởi passive sensor thiếu keys. Không xây detector dựa trên giả định **“mọi HTTPS đều có SNI và cert nhìn được”**.

## 17. Baseline ứng dụng và mối liên hệ với SLO

Một mạng có throughput bình thường vẫn có thể đang gặp sự cố ứng dụng. Baseline nên ghép network telemetry với **golden signals** của dịch vụ: traffic, latency, errors và saturation khi có observability tương ứng.

### 17.1. Metrics cho một web/API service

| Metric | Ví dụ nguồn | Lý do theo dõi |
| --- | --- | --- |
| Requests/s | Ingress proxy/APM | Thể hiện nhu cầu ứng dụng |
| Concurrent requests | Service runtime/proxy | Hàng đợi và saturation |
| p50/p95/p99 response latency | APM/trace/ingress | User experience |
| 4xx/5xx rate | Proxy/application | Xác thực/validation và service errors |
| Connection pool utilization | DB/client metrics | Bottleneck, retry storms |
| Bytes sent/received per request | Proxy/APM | Traffic shape, compression |
| CPU/memory/sockets | Node/container metrics | Capacity context |
| Network retransmission/loss | Host/router telemetry | Phân biệt network vs app |
| Dependency call rate | Tracing/service mesh | Chuyển đổi của upstream/downstream |

### 17.2. Baseline kết hợp không phải chắp tất cả vào một số

Nếu request rate không đổi nhưng network throughput tăng gấp ba, giả thuyết có thể là **response payload lớn hơn, cache thay đổi, retries, compression disabled, telemetry khác**. Nếu network throughput ổn mà 5xx tăng, điều tra app/database/dependencies thay vì chỉ network capacity.

### 17.3. SLO không giống baseline

Một baseline p95 latency là 180 ms không có nghĩa SLO cho phép 180 ms hay dịch vụ đã đạt yêu cầu khách hàng. **SLO do nghiệp vụ/owner đặt**; baseline ghi lại những gì đã xảy ra. Nếu ứng dụng luôn chậm, không nên nâng SLO theo baseline kém.

### 17.4. Correlation với deployments

Ghi **version/release ID, rollout start/end, feature flags, CDN/cache configuration, traffic-shift/canary percentages**. Một spike connection rate sau deploy có thể do reconnect/retry behavior, không phải scan. Ngược lại, deploy được phê duyệt vẫn có thể tạo security policy violation nếu thay đổi trust boundary.

### 17.5. Từ service dependency đến traffic graph

~~~mermaid
flowchart LR
    C["External clients"] --> EDGE["Ingress Gateway"]
    EDGE --> API["Orders API"]
    API --> DB[("Orders DB")]
    API --> PAY["Payment service"]
    API -. "Unexpected connection" .-> MGMT["Node management port"]
    GRAPH["Approved dependency graph"] -. "Defines expected peer sets" .-> API
~~~

Những kết nối tới **node management port** có thể cần cảnh báo theo policy dù bytes rất ít. Đây là lý do kết hợp **traffic graph + policy inventory + statistical baseline**.

## 18. Baseline firewall, segmentation và IDS/IPS

### 18.1. Thống kê per-rule/per-zone

Firewall logs hữu ích cho:

- Allow/deny counts theo rule ID và source/destination zone.
- Deny rate trên mỗi 1.000 attempts (khi có denominator đáng tin).
- Top talkers, protocol/port diversity.
- Unexpected inter-zone traffic sau thay policy.
- Session creation failures và firewall resource saturation.

Một **allow traffic spike** sau nới firewall có thể là vấn đề policy review; ngược lại deny tăng sau tightening có thể chính là kết quả dự kiến.

### 18.2. Không đếm deny thành tấn công một cách máy móc

Health checks cấu hình sai hoặc DNS stale có thể tạo deny records rất nhiều. Cần xem **nguồn, đích, port, time, retry patterns, host logs** và change events.

### 18.3. Baseline IDS/IPS alerts

Một IDS phát hàng nghìn signatures không đồng nghĩa hàng nghìn incidents. Theo dõi:

- Số alerts theo signature/category, asset criticality và detection source.
- Số alerts sau deduplication/grouping.
- True-positive confirmation rate, false-positive trend và coverage.
- Signature/version changes và sensor traffic distribution.

Một signature mới hoặc thay engine version có thể làm alert count nhảy dù traffic không đổi. Ghi **detection-rule version** như một yếu tố của baseline.

### 18.4. Policy-level anomaly khác volume anomaly

Nếu mọi truy cập đến admin SSH port từ workload frontend **bị cấm**, một connect attempt dù chỉ vài packet có thể có ý nghĩa. Ngược lại backup 100 GB được duyệt tới storage account đúng không cần alert chỉ do băng thông.

### 18.5. Stateful firewalls

Nhiều firewall dùng **state tracking**. Traffic phản hồi được chấp nhận không nhất thiết có một allow rule riêng tương đương mở kết nối mới. Khi baseline deny/allow theo chiều, hiểu **connection state, NAT và rule lookup stage** của platform để tránh diễn giải sai.

## 19. Cloud và Kubernetes: baseline trong hệ thống biến động

### 19.1. Autoscaling làm IP và traffic thay đổi

Khi HPA/autoscaling tạo Pods hoặc cloud VMs mới:

- Flow sources/Pod IP thay đổi.
- Tổng kết nối có thể tăng do nhiều replicas.
- Requests/replica có thể giảm dù tổng requests ổn định.
- Lưu lượng node-to-node/overlay tăng hoặc giảm theo placement.

Baseline theo **deployment/service identity, namespace và replicas** thường ổn định hơn per-IP. Theo dõi **traffic/replica hoặc requests per resource unit** để tách scaling khỏi abnormal load.

### 19.2. CNI eBPF và service mesh

Một eBPF/CNI dataplane có thể cung cấp **Pod/namespace/service identity và policy verdict**; service mesh có thể ghi **mTLS principals, gRPC/HTTP request metrics** theo cấu hình. Nhưng:

- Không phải mọi CNI đều hỗ trợ cùng fields.
- CNI logs không mặc nhiên có HTTP payload.
- Mesh telemetry không bao phủ các Pods hoặc network interfaces không enrolled.
- NetworkPolicy API được chấp nhận không bảo đảm dataplane enforce nếu CNI không có policy engine.

### 19.3. HostNetwork và node traffic

Traffic từ **hostNetwork Pods, node agents, kubelet hoặc host services** có thể được quan sát/enforce ở điểm khác so với Pod-to-Pod networking. Cần baseline riêng **node-to-Pod, Pod-to-node, Pod-to-Internet**, tránh coi default-deny NetworkPolicy chuẩn kiểm soát mọi host traffic.

### 19.4. Service VIP, SNAT/DNAT

Một request tới **ClusterIP Service** có thể được chuyển đến Pod endpoint qua kube-proxy hoặc dataplane thay thế. Sensor trước NAT có thể thấy **Service VIP**, sensor sau translation thấy **Pod IP**. Khi dựng service-to-service graph cần correlation qua **Service, EndpointSlice, workload labels và NAT context** phù hợp triển khai.

### 19.5. Cloud private endpoints

Một workload ghi object sang cloud storage qua private endpoint có thể **không xuất hiện tại Internet egress firewall**. Baseline cần cloud storage/API audit, role identity, cloud flow hoặc service telemetry; “không có traffic Internet” không có nghĩa không có data movement.

### 19.6. Multi-region và disaster recovery

Một traffic shift do regional failover có thể làm baseline region A giảm và region B tăng. Ghi **failover drills, routing weights, region, AZ, load balancer events và topology changes** để phân biệt dự kiến với DDoS/lateral movement.

### 19.7. Service account và workload permission

Baseline theo service account hữu ích nhưng không thay **authorization**. Một workload hợp lệ có thể bị compromise và dùng quyền sẵn có để gọi đích được phép với dữ liệu ngoài phạm vi. Cần app/data audit cùng egress observations.

## 20. Xây detector: volume, novelty, topology và failure rate

Không có một detector “bất thường” phù hợp mọi metric. Nên chia tín hiệu:

| Detector | Quan sát | Khi nào hữu ích | Giới hạn |
| --- | --- | --- | --- |
| **Rate deviation** | bps/pps/flows vượt baseline | Burst, capacity, retry, transfer spike | Backup/campaign false positives |
| **Unexpected peer** | Service/zone kết nối đích ngoài approved graph | Segmentation và lateral movement | Inventory có thể chưa đầy đủ |
| **New destination** | External FQDN/IP/account mới | Egress review và SaaS risk | CDN/updates/false positives |
| **Connection failure spike** | TCP failures/resets, unavailable backends | Routing/firewall/outage | Sensor có thể không thấy full handshake |
| **DNS error spike** | NXDOMAIN/SERVFAIL/latency | Resolver/app misconfiguration | DNS cache/DoH coverage |
| **Protocol shift** | TCP→UDP443, A→AAAA, TLS version | Migration, policy drift | Thường hợp lệ sau deploy |
| **Directional anomaly** | Upload/download ratio thay đổi | Data movement/retry | NAT/sampling/streaming |
| **Privilege/source identity anomaly** | New admin workstation/service account peer | Abuse/credential misuse | Identity mapping cần đáng tin |
| **Data transfer correlation** | Sensitive data read + unusual egress | Exfil suspicion | Không chứng minh content từ flows |

### 20.1. Phân biệt volume anomaly và policy violation

**Volume anomaly:** lưu lượng thay đổi nhiều so với thống kê cùng loại.

**Policy violation:** flow/identity/port trái với quan hệ được phép. Một violation có thể có **0.5 KiB** nhưng quan trọng hơn một backup 100 GiB đúng đích.

### 20.2. Multi-signal correlation

Ví dụ khi thấy **Outbound HTTPS tăng**:

1. Kiểm tra ingestion/coverage không thay.
2. Xác định source user/workload, process, zone.
3. So baseline đúng giờ, ngày, service và lịch backup.
4. Kiểm tra destination domain/account và allowlist.
5. Liên kết DNS/endpoint/file/app logs nếu có.
6. Đối chiếu change ticket/deployment.
7. Đánh giá asset/data criticality trước khi mở case.

Một flow lớn sau thay CDN có thể không cần security incident; cùng flow lớn từ một privileged service tới unapproved account cùng thời điểm data export có thể đáng điều tra hơn.

### 20.3. Detector đa cửa sổ

Phát hiện ngắn hạn và dài hạn khác nhau:

- **1–5 phút:** burst, connection storm, DNS spike, sudden drop.
- **1–4 giờ:** bất thường user/device workload so với shift.
- **1–7 ngày:** slow drift, unusual daily egress, dormant access return.
- **Nhiều kỳ nghiệp vụ:** backup/quarter-end seasonality, cost/capacity trends.

Không đặt long-term aggregate làm nguồn duy nhất cho real-time incident; cũng không biến mọi 10-second spike thành pager alert.

### 20.4. Unknown confidence

Nếu chưa có sampling rate, destination account ID hoặc process identity, detector nên ghi **not observed/unknown** và giảm confidence, không điền giá trị mặc định để tạo câu chuyện hoàn chỉnh.

## 21. Alert thresholds và giảm báo động sai

### 21.1. Một alert tốt cần những gì?

| Trường | Ví dụ |
| --- | --- |
| **Who/what** | service=orders-api, namespace=payments |
| **Where** | src_zone=backend, dst_zone=Internet |
| **When** | UTC window + local business time |
| **Metric** | verified bytes_up/s trong 5 phút |
| **Expected** | role/service-specific baseline p95/p99, model version |
| **Observed** | 180 Mbit/s, từ đúng sensor |
| **Context** | no approved export job, new destination tenant |
| **Confidence** | High/Medium/Low với missing signals |
| **Action** | triage/runbook; không tự động block nếu chưa đủ bằng chứng |
| **Linkage** | Flow ID, policy ID, trace/change ticket khi có |

### 21.2. Static vs dynamic thresholds

- **Static:** phù hợp giới hạn vật lý/hợp đồng/SLO rõ, ví dụ link utilization theo capacity.
- **Dynamic/seasonal:** phù hợp traffic thay đổi theo giờ/ngày hoặc workload.
- **Policy-based:** không phụ thuộc volume, ví dụ backend→admin port bị cấm.

Kết hợp **absolute cap + relative baseline + policy context**, không dùng dynamic threshold để thay thế những quy định cấm rõ ràng.

### 21.3. Hysteresis và alert dwell time

Để tránh alert “chớp tắt”:

- Yêu cầu điều kiện vượt ngưỡng **N trong M buckets** cho metric phù hợp.
- Ngưỡng clear thấp hơn ngưỡng trigger khi cần.
- Có thời gian quiet/cooldown với owner và policy.
- Đừng debounce quá lâu các sự kiện bảo mật **high-confidence**.

Một sự cố dữ liệu nhạy cảm cần chính sách khác với network link utilization.

### 21.4. Baseline guardrails

Không tự tăng ngưỡng vì liên tục bị alert khi chưa biết **cảnh báo đó thực sự sai hay một sự cố kéo dài**. Mỗi thay đổi threshold cần:

1. Chứng cứ và source data health.
2. Impact analysis trên positive/negative cases.
3. Owner, ticket, version và expiry nếu là exception.
4. Có thể rollback.
5. Theo dõi false-negative risk.

### 21.5. Severity theo asset và bằng chứng

| Quan sát | Ưu tiên gợi ý |
| --- | --- |
| Bandwidth tăng có backup ticket đúng | Operational review hoặc no alert |
| DNS SERVFAIL tăng, app requests thất bại | SRE incident |
| New frontend→DB port ngoài allowed graph | Security triage |
| Privileged workload→unknown external account + export audit | High-priority investigation |
| Sensor stopped reporting | Telemetry coverage incident |

Mức ưu tiên phải theo **chính sách tổ chức và khả năng gián đoạn**, không có giá trị tuyệt đối chung.

## 22. Concept drift, change point và cập nhật baseline

**Concept drift** xảy ra khi đặc điểm hoạt động thực sự thay đổi: thêm dịch vụ, tăng người dùng, đổi giao thức, traffic shifting, cloud autoscaling hoặc hành vi khách hàng thay đổi lâu dài. **Data drift** cũng có thể xuất hiện do sensor/exporter đổi field, sampling hoặc coverage, dù hệ thống mạng không thay.

### 22.1. Ba loại thay đổi cần tách

| Loại | Ví dụ | Hành động |
| --- | --- | --- |
| **Business/workload drift** | API được dùng thường xuyên hơn sau mở thị trường | Owner xác nhận, huấn luyện baseline phiên bản mới |
| **Infrastructure/telemetry drift** | Đổi CNI hoặc NetFlow sampling 1:100 → 1:1000 | Hiệu chỉnh measurement, không gán mọi chênh lệch cho traffic |
| **Suspicious/unknown drift** | Một service dần gửi dữ liệu tới đích lạ | Tạm khóa auto-learning, triage và policy review |

### 22.2. Change point evidence

Giữ timeline gồm:

- Deployment/release, autoscaling và feature flags.
- Network route/firewall/ACL changes, certificate/TLS changes.
- DNS, load balancer, CDN, cloud region failover.
- New telemetry source/exporter template/version.
- Security incident windows và data policy exceptions.

Một change point model có thể phát hiện **step change** trong traffic, nhưng không tự phân loại nguyên nhân. Ghép **change tickets/telemetry version** trước khi chấp nhận đường chuẩn mới.

### 22.3. Shadow baseline

Trong giai đoạn chuyển mô hình:

1. Giữ **current production baseline** không thay.
2. Tính **candidate baseline** trên dữ liệu mới được xác minh.
3. Chạy candidate ở chế độ **shadow/report-only**.
4. So false positives/negatives với holdout tests.
5. Xác minh approved service dependencies không bị mở rộng trái quyền.
6. Phê duyệt/ghi version rồi mới chuyển baseline.
7. Có rollback nếu alert behavior xấu đi.

### 22.4. Auto-learning phải có guardrail

Không để hệ thống **tự whitelist domain mới chỉ vì truy cập lặp lại**, hoặc tự nâng ngưỡng egress cho một workload vừa bị compromise. Với tài nguyên nhạy cảm, new service peer hoặc destination account cần **owner review**, dù thống kê đã chuyển sang trạng thái “thường gặp”.

### 22.5. Cold start

Một service mới hoặc cluster mới có thể chưa đủ dữ liệu:

- Dùng **peer-group baseline** có confidence hạn chế.
- Sử dụng **policy-based allowlist, SLO và known capacity constraints**.
- Chạy observability trước, thu thập approved business cycles.
- Không tự tạo ngưỡng p99 từ vài requests.
- Lưu trạng thái **model not ready** rõ ràng để SOC không tin nhầm mức bảo vệ.

### 22.6. Retirement và retention

Khi app ngừng hoạt động, baseline cũ cần được đánh dấu retired cùng owner và thời điểm. Nếu IP bị cấp lại, không để đường chuẩn “tài sản cũ” tự áp cho workload mới. Retain models/logs theo nhu cầu điều tra và policy dữ liệu, không vô hạn.

## 23. Quản trị, quyền riêng tư và bằng chứng kiểm toán

Một baseline network có thể tiết lộ hành vi nhân viên, hệ thống nhạy cảm, nhóm khách hàng hoặc dữ liệu nghiệp vụ. Cần thiết kế **quản trị dữ liệu** ngay từ đầu.

### 23.1. Vai trò và trách nhiệm

| Vai trò | Trách nhiệm |
| --- | --- |
| **Network/SRE** | Chất lượng sensor, measurement, capacity và incident vận hành |
| **Security/SOC** | Threat model, detection policy, alert triage và bằng chứng |
| **Application owner** | App dependencies, approved schedules, release changes |
| **Data governance/privacy** | Data classification, retention, quyền dùng telemetry |
| **IAM/platform** | Identity attribution, workload labels, agent permissions |
| **Change manager** | Approval cho threshold/coverage/baseline versions |

### 23.2. Data minimization

Không phải mọi dashboard cần user-level browsing history hoặc raw PCAP. Với capacity có thể chỉ cần aggregate bytes; khi có incident hợp lệ mới drill down theo **user/device/process/flow**. Áp dụng:

- **Least-privilege access** tới flow, DNS và endpoint logs.
- Pseudonymization hoặc coarse aggregation khi có thể.
- Retention hạn chế theo use case.
- Audit quyền truy cập và exports của SIEM/data warehouse.
- Secret/token redaction; không thu TLS private keys để thuận tiện monitoring.
- Encryption và integrity controls cho telemetry.

### 23.3. Các nguy cơ đối với pipeline

- **Tampering:** sửa/xóa logs hoặc thay rule để che dấu flow.
- **Sensor outage:** mất coverage tạo false sense of normal.
- **Data poisoning:** đưa activity xấu vào giai đoạn training.
- **Exposure:** lộ topology và user/app mapping qua dashboard.
- **Privilege escalation:** tài khoản quản trị telemetry có thể thay suppression/threshold.

Cần **RBAC, approvals, audit, separated roles, resilient storage và coverage alarms** theo mức độ nhạy cảm. Không coi SIEM admin là người được tự ý thay các policy kinh doanh mà không review.

### 23.4. Explainability

Một alert nên giải thích:

~~~text
Source:      payments/orders-api (verified workload identity)
Metric:      outbound_bytes_per_5m (client-to-server)
Observed:    1.8 GiB
Expected:    0.2-0.4 GiB during this hour/day class
Change:      +new destination account (unapproved)
Context:     no release/backup ticket
Data quality: 98% buckets present; sampling unchanged
Limitations:  HTTP body not inspected; data classification unknown
Decision:    manual security triage, not confirmed exfiltration
~~~

**Các số liệu chỉ minh họa**, không phải bằng chứng của một sự cố thật.

### 23.5. Policy và kết luận

Một detector có thể cảnh báo rằng một user/device có hành vi khác thường. Chỉ **người/nhóm có thẩm quyền** mới có thể xác nhận hoạt động đó trái chính sách, và không nên suy đoán **động cơ, ý định hoặc hậu quả pháp lý** chỉ từ telemetry định lượng.

## 24. Mô hình chính sách baseline trung lập với sản phẩm

Tài liệu YAML dưới đây mô tả **yêu cầu thiết kế và kiểm chứng**. Nó **không phải file cấu hình** có thể áp trực tiếp vào SNMP server, NetFlow collector, SIEM, eBPF agent, CNI, firewall hoặc Kubernetes.

~~~yaml
networkTrafficBaselineRequirements:
  name: approved-network-telemetry-baseline
  environment: isolated-training
  ownership:
    telemetry: network-observability
    security: soc
    applications: approved-service-owners
    privacy: data-governance
  sources:
    expected:
      - interface-counters
      - ipfix-or-flow-export
      - firewall-policy-events
      - dns-resolver-events
      - cloud-and-kubernetes-flows
      - application-and-endpoint-context
    recordObservationPoint: true
    recordExporterVersionAndSampling: true
    monitorCollectionFreshnessAndGaps: true
    doNotTreatMissingAsZero: true
  normalization:
    storeEventTimeUtc: true
    retainRelevantTimezoneForSeasonality: true
    verifyBitByteAndCounterUnits: true
    distinguishRequestDirectionFromInterfaceDirection: true
    correlatePreNatPostNatWhenAvailable: true
    preserveUnknownFieldsAsUnknown: true
    deduplicateRepeatedSensorsBeforeSummation: true
    protectHighCardinalityRawData: true
  segmentation:
    useStableServiceOrWorkloadIdentity: true
    separateProductionFromStaging: true
    separateInternalExternalAndTrustZones: true
    separateIpv4AndIpv6: true
    classifyApprovedApplicationsAndDestinations: true
    documentLegacyVpnAndPrivateCloudPaths: true
  baseline:
    dimensions:
      - service-and-network-zone
      - traffic-direction
      - protocol-and-application
      - weekday-weekend-business-calendar
      - validated-release-or-backup-window
    compute:
      - median
      - p95-and-p99-when-sample-size-sufficient
      - iqr-or-mad-when-appropriate
      - sample-count-and-confidence
    excludeKnownTelemetryGaps: true
    labelIncidentsAndMaintenance: true
    reviewUnknownDependenciesBeforeAutoLearning: true
    validateOnHeldOutTimeWindows: true
  anomalyDetection:
    useRateAndTopologySignals: true
    includeSecurityPolicyViolationsRegardlessOfVolume: true
    correlateServiceIdentityWithDnsAndAppTelemetry: true
    includeSloAndChangeEvents: true
    useEvidenceConfidenceAndMissingDataTags: true
    avoidDuplicateAlertsFromSameFlow: true
  lifecycle:
    baselineVersioning: true
    shadowCandidateModelsBeforePromotion: true
    detectSensorAndDistributionDriftSeparately: true
    requireOwnerApprovalForRiskyBaselineExpansion: true
    maintainRollback: true
    retireBaselinesForDeletedResources: true
  response:
    lowConfidence: observe-or-review
    confirmedUnauthorizedFlow: security-triage
    outageIndicators: sre-triage
    irreversibleAction: human-approved-incident-process
  privacy:
    collectMinimumRequiredFields: true
    enforceRoleBasedAccess: true
    redactSecretsAndSensitiveIdentifiers: true
    retentionPerApprovedPolicy: true
  validation:
    testAuthorizedTrafficSpikes: true
    testUnauthorizedSmallFlows: true
    testClockSkewSamplingChangesAndMissingData: true
    verifyIpv6CloudAndHostNetworkCoverage: true
~~~

### 24.1. Từ ý định thành công cụ thật

Ví dụ **doNotTreatMissingAsZero: true** phải được thể hiện bằng pipeline có trạng thái data quality và dashboard query không tự fill NULL bằng 0. **recordExporterVersionAndSampling: true** cần collector fields có thực hoặc out-of-band inventory. Một string mô tả không tự tạo tính năng.

### 24.2. Tách anomaly với authorization

YAML yêu cầu **includeSecurityPolicyViolationsRegardlessOfVolume**, nghĩa là bất kỳ flow trái dependency/egress allowlist phù hợp nào cũng cần được đánh giá, dù baseline volume không đổi. Nhưng policy phải được xác minh từ **nguồn cấu hình có thẩm quyền**, không đoán quyền từ lịch sử flow.

### 24.3. SLO của pipeline

Thiết kế mục tiêu:

- Giới hạn **ingestion lag/freshness** theo SRE/SOC requirements.
- Alert khi node/sensor không gửi dữ liệu.
- Theo dõi sample rate/exporter template changes.
- Có data lineage từ dashboard metric tới sensor/event class.
- Hiển thị confidence hoặc trạng thái **insufficient data**.

Không có các yếu tố này, một baseline được vẽ đẹp vẫn có thể che outage.

## 25. Ví dụ truy vấn SQL và quy trình tính baseline

Đây là **SQL minh họa** trên bảng telemetry đã được chuẩn hóa, không phải truy vấn có thể chạy nguyên trạng trên mọi SIEM. Không dùng để quét mạng hoặc truy cập dữ liệu thật ngoài phạm vi được phép.

### 25.1. Schema giả định

~~~text
normalized_traffic_events(
    event_id,
    event_time_utc,
    source_type,
    sensor_id,
    service_id,
    source_zone,
    destination_zone,
    traffic_direction,
    ip_family,
    transport_protocol,
    bytes_observed,
    packets_observed,
    bytes_direction_verified,
    sample_rate,
    telemetry_quality,
    exporter_version,
    change_event_id
)
~~~

Một service có thể có các flow records đã được tách theo 5-minute bucket, hoặc các interface counter deltas đã được chuyển thành **byte increments**. Không trộn raw counter values với flow byte totals.

### 25.2. Tổng hợp theo service và bucket một phút

~~~sql
-- PSEUDO SQL trên telemetry lab đã chuẩn hóa:
-- Logic date_trunc/bucket cần đổi theo SQL engine thực tế.
SELECT
    service_id,
    source_zone,
    destination_zone,
    traffic_direction,
    transport_protocol,
    DATE_TRUNC('minute', event_time_utc) AS minute_bucket,
    SUM(bytes_observed) AS observed_bytes,
    SUM(packets_observed) AS observed_packets,
    COUNT(*) AS observed_records
FROM normalized_traffic_events
WHERE event_time_utc >= :period_start
  AND event_time_utc < :period_end
  AND telemetry_quality = 'valid'
  AND bytes_direction_verified = TRUE
GROUP BY
    service_id,
    source_zone,
    destination_zone,
    traffic_direction,
    transport_protocol,
    DATE_TRUNC('minute', event_time_utc);
~~~

Truy vấn trên tạo **minute buckets**, không phải 5-minute buckets; để tính 5 phút phải dùng bucket function tương ứng hoặc gộp 5 minute buckets có UTC alignment. Phân biệt rõ mục tiêu giúp tránh nhầm time-series width.

### 25.3. Ví dụ công thức bucket 5 phút

Với timestamp Unix theo giây \(t\), bucket 5 phút (300 giây) có thể là:

\[
b(t)=300\left\lfloor \frac{t}{300}\right\rfloor .
\]

Trong SQL thực tế, dùng hàm epoch/bucket được engine hỗ trợ và giữ timestamp UTC. **Một flow record bao trùm nhiều buckets không nên được phân bổ tùy tiện toàn bộ vào thời điểm kết thúc** nếu yêu cầu độ chính xác cao; cần method phân bổ theo thời gian hoặc dữ liệu có độ phân giải tốt hơn, và ghi uncertainty.

### 25.4. Baseline theo ngày/giờ

~~~text
Training input:
  validated 5-minute buckets
  service_id + zone_pair + protocol + direction
  day_type + hour_or_bucket_slot
  exclude data_gaps, confirmed incidents, maintenance

For each peer group + seasonal slot:
  n = count(usable observations)
  if n < required_minimum_for_model:
      baseline_status = "insufficient_data"
  else:
      baseline = {
          "median": median(samples),
          "p95": percentile(samples, 95),
          "iqr": percentile(samples, 75) - percentile(samples, 25),
          "sample_count": n,
          "training_window": [start, end],
          "data_quality": measured_quality
      }
~~~

### 25.5. Detection pseudocode

~~~text
function evaluateNetworkMetric(observation, baseline, policy, context):
    if not observation.sensorHealthy:
        return TELEMETRY_COVERAGE_ALERT

    if not observation.unitsAndDirectionVerified:
        return INSUFFICIENT_EVIDENCE

    if policy.explicitlyDenies(
          observation.sourceIdentity,
          observation.destinationService,
          observation.port
       ):
        return SECURITY_POLICY_REVIEW  # even if bytes are small

    if baseline.status != "ready":
        return BASELINE_NOT_READY_WITH_OBSERVATION

    if context.isConfirmedMaintenanceOrApprovedBackup:
        return EXPECTED_CHANGE_WITH_SLO_CHECKS

    deviation = compareToSeasonalDistribution(
        observation.value, baseline.median, baseline.p95, baseline.iqr
    )

    if deviation is strong:
        evidence = correlate(
            appTelemetry,
            identityAndWorkload,
            dnsAndDestination,
            policyAndDeploymentChanges
        )
        return EXPLAINABLE_TRIAGE_FINDING(evidence)

    return WITHIN_EXPECTED_STATISTICAL_RANGE
~~~

**Hàm là giả mã phòng vệ**, không định nghĩa ngưỡng production hay một hệ thống có thể tự động block. Real implementation cần rate-limits, missing data handling, deduplication, backtesting và quyền phê duyệt thay đổi.

### 25.6. Bẫy percentile khi sample ít

Nếu một service mới chỉ có vài 5-minute buckets, p95/p99 sẽ không ổn định; không dùng nó làm ngưỡng chắc chắn. Tính **sample_count/coverage**, so peer-group phù hợp hoặc dùng ngưỡng theo policy/SLO trước khi model ready.

### 25.7. Tránh aggregation của sampled flows như exact bytes

Nếu exporter lấy mẫu, dashboard phải ghi **estimated throughput, sampling method và confidence**, tránh nhãn “exact total bytes”. Việc nhân hệ số sampling trong những điều kiện không đáp ứng giả định có thể làm phát hiện lệch.

## 26. Log giả lập: ba tình huống baseline khác nhau

Các logs sau đều là **synthetic training data**, không đại diện schema của SIEM/cloud vendor. Mục đích là thể hiện evidence và limitations chứ không phải dựng thêm thông tin không quan sát được.

### 26.1. Tình huống A: backup tăng bandwidth nhưng đã được duyệt

~~~json
{
  "timestamp_utc": "2026-11-28T01:15:00Z",
  "dataset": "synthetic-training-event",
  "event_type": "network_baseline_deviation",
  "source_service": "nightly-backup-job",
  "destination_service": "approved-enterprise-backup",
  "observation_point": "lab-egress-proxy",
  "window_seconds": 300,
  "observed_megabits_per_second": 820,
  "baseline_median_megabits_per_second": 145,
  "approved_change_reference": "LAB-BACKUP-SCHEDULE-01",
  "identity_verified": true,
  "destination_account_approved": true,
  "sensor_quality": "healthy",
  "decision": "expected_scheduled_activity",
  "followup": "validate_backup_completion_and_capacity"
}
~~~

Một backup hợp lệ vẫn có thể gây **network saturation** cần SRE review. **Không tạo security incident chỉ vì vượt baseline** nếu business context/identity/account và data policy phù hợp.

### 26.2. Tình huống B: một flow nhỏ vi phạm quan hệ dịch vụ

~~~json
{
  "timestamp_utc": "2026-11-28T02:22:00Z",
  "dataset": "synthetic-training-event",
  "event_type": "unexpected_service_peer",
  "source": {
    "namespace": "shop",
    "service": "frontend",
    "pod_uid_ref": "synthetic-pod-017"
  },
  "destination": {
    "zone": "management",
    "service": "node-admin",
    "port": 22,
    "protocol": "TCP"
  },
  "observed_bytes": 512,
  "approved_dependency": false,
  "policy_verdict": "deny",
  "baseline_status": "rare_or_unobserved",
  "action": "review_unexpected_attempt",
  "impact": "connection_blocked",
  "confidence_limitation": "no_evidence_of_successful_login"
}
~~~

Đây là **policy violation candidate** có volume rất nhỏ. Deny ở firewall không chứng minh node đã bị truy cập; case cần kiểm tra source/process và lý do kết nối.

### 26.3. Tình huống C: mất sensor làm throughput về 0 giả

~~~json
{
  "timestamp_utc": "2026-11-28T03:00:00Z",
  "dataset": "synthetic-training-event",
  "event_type": "telemetry_quality_warning",
  "sensor_id": "ipfix-lab-node-05",
  "last_event_age_seconds": 780,
  "expected_reporting_interval_seconds": 60,
  "observed_records": null,
  "estimated_throughput": null,
  "baseline_comparison": "suspended",
  "decision": "telemetry_coverage_incident",
  "do_not_infer": "network_traffic_is_zero",
  "followup": "check_exporter_and_ingestion"
}
~~~

**NULL là chưa biết**, không phải traffic bằng 0. Đây là tình huống rất quan trọng trong network monitoring: hệ thống giám sát cần **tự giám sát sức khỏe của chính nó**.

## 27. Ma trận kiểm thử baseline trong lab được cấp quyền

Các ca sau dùng **lab traffic, log giả lập hoặc ứng dụng/thiết bị được phép giám sát**. Không quét subnet ngoài quyền, không làm DDoS, không sinh lưu lượng gây nghẽn production, không cố truy cập hệ thống quản trị thật và không sử dụng file dữ liệu nhạy cảm. Với kiểm thử policy-violation, nên dùng **synthetic event** hoặc tài nguyên lab nơi hành vi deny đã được phê duyệt.

### 27.1. Kiểm thử thu thập và chất lượng dữ liệu

| Mã | Tình huống | Kết quả kỳ vọng |
| --- | --- | --- |
| T-01 | Interface tăng counter đều trong lab | Bitrate tính đúng đơn vị và khoảng thời gian |
| T-02 | SNMP counter reset sau restart interface | Không tạo bitrate âm hoặc spike giả |
| T-03 | Counter 32-bit overflow trên thiết bị lab giả lập | Phát hiện wrap/đổi counter width theo khả năng |
| T-04 | Một sensor ngừng gửi dữ liệu | Alert coverage, bucket marked missing, không suy 0 |
| T-05 | Ingestion lag tăng 10 phút | Dữ liệu gán event time, không làm spike sai giờ |
| T-06 | Đồng hồ collector lệch so với endpoint 2 phút | Correlation phát hiện time skew/đánh dấu giới hạn |
| T-07 | Cùng flow được gửi bởi hai sensors | Không double-count trong tổng traffic cùng metric |
| T-08 | IPFIX template/exporter version thay đổi | Schema validation phát hiện thay đổi |
| T-09 | Sampling rate của exporter đổi | Model đánh dấu measurement drift |
| T-10 | Flow kéo dài qua nhiều 5-minute buckets | Không gán tất cả bytes vào một bucket nếu cần time allocation |
| T-11 | Record thiếu bytes direction | Không suy upload/download chính xác |
| T-12 | NAT mapping của nhiều users dùng chung public IP | Attribution theo mapping/time hoặc unknown |

### 27.2. Kiểm thử baseline thống kê và lịch nghiệp vụ

| Mã | Tình huống | Kết quả kỳ vọng |
| --- | --- | --- |
| T-13 | Backup 100 GB theo lịch được duyệt | Security anomaly không auto-escalate chỉ vì volume |
| T-14 | Campaign tăng HTTPS requests gấp nhiều lần | Event-aware baseline/owner context |
| T-15 | Ngoài giờ làm việc traffic giảm hợp lệ | Seasonal baseline không báo outage vô căn cứ |
| T-16 | Service mới chỉ có 4 buckets | Model báo insufficient data, không dùng p99 giả chắc chắn |
| T-17 | Training có một ngày outage | Window được label/exclude khỏi normal training |
| T-18 | Training có incident đã xác minh | Không tự học incident thành bình thường |
| T-19 | Application tăng số user đều vài tuần | Candidate baseline/shadow và owner review |
| T-20 | HTTP/2 thay HTTP/1.1 | Connection count đổi nhưng requests/s có context |
| T-21 | Bật HTTP/3/QUIC | TCP/443 giảm, UDP/443 tăng được giải thích theo release |
| T-22 | Autoscaling tăng replicas 3 lần | Per-service và per-replica views nhất quán |
| T-23 | Thay endpoint Pod IP sau reschedule | Baseline theo workload identity không reset sai |
| T-24 | Region failover được phê duyệt | Regional baselines và global view phân biệt traffic shift |
| T-25 | Một spike 1 phút nhưng baseline theo 1 giờ | Kiểm thử khả năng mất tín hiệu do aggregation |
| T-26 | Độ lệch ít bytes từ baseline gần 0 | Ratio không tạo critical alert vô căn cứ |

### 27.3. Kiểm thử theo giao thức và an ninh

| Mã | Tình huống | Kết quả kỳ vọng |
| --- | --- | --- |
| T-27 | Frontend lab gọi backend đúng port/zone | Allow + expected topology |
| T-28 | Frontend lab tạo event SSH tới management zone không được duyệt | Alert policy violation dù bytes rất nhỏ |
| T-29 | DNS NXDOMAIN tăng do hostname typo trong lab | Triage phân biệt misconfiguration với threat |
| T-30 | Managed resolver bị lỗi SERVFAIL | Detection và SRE triage phù hợp |
| T-31 | IPv4 flow giảm khi IPv6 được bật | Combined service usage không báo sai outage |
| T-32 | Một IPv6 egress path không có firewall logs | Coverage gap được ghi và escalated |
| T-33 | HTTP CONNECT tunnel có nhiều bytes | Không tự gán HTTP POST/path hoặc file |
| T-34 | TLS 1.3 passive capture không thấy certificate | Không bịa server certificate detail |
| T-35 | ECH được bật trong test hỗ trợ | Không yêu cầu true SNI ở passive sensor |
| T-36 | DNS query có nhưng không có network flow | Không kết luận có connection |
| T-37 | Firewall drop tăng sau policy rollout có ticket | So rollout, không tự gọi attack |
| T-38 | IDS signature updates làm alert count tăng | Detection-version-aware baseline |
| T-39 | Một TCP retry storm do backend timeout | Correlate 5xx/RTT/retransmissions, không mặc định DDoS |
| T-40 | ICMP type/code xuất hiện vì PMTU testing | Không chặn toàn ICMP, giải thích theo network |

### 27.4. Kiểm thử cloud, workload và phản ứng

| Mã | Tình huống | Kết quả kỳ vọng |
| --- | --- | --- |
| T-41 | Kubernetes Pod-to-Pod cùng node không qua Internet firewall | CNI/host telemetry bao phủ khi yêu cầu |
| T-42 | Cross-node overlay VXLAN trong lab | Phân biệt outer tunnel và inner service flow |
| T-43 | Pod hostNetwork gửi traffic | Có host-specific coverage/exception documented |
| T-44 | Cloud workload dùng private endpoint | Cloud API/flow audit, không dựa solely Internet SWG |
| T-45 | SaaS personal vs approved enterprise account | Baseline account-aware khi nguồn có trường đó |
| T-46 | Egress bytes cao nhưng không có data classification | Alert giới hạn bằng chứng, không khẳng định exfil |
| T-47 | Một log quality gap trùng traffic giảm | Ưu tiên telemetry incident trước khi suy outage |
| T-48 | Change request mở service peer mới ngoài app dependency | Owner review + policy approval trước baseline update |
| T-49 | Detector rule gây false positives trong lab | Canary, threshold versioning, rollback |
| T-50 | Nhiều signals trùng một root cause | Alert grouping không tạo incident storm |
| T-51 | User/service bị đổi quyền, traffic tới đích cũ vẫn xảy ra | Policy violation được phát hiện độc lập statistical baseline |
| T-52 | Dashboard p95 đổi do method tính percentile | Metric definition/version được giữ và so đúng |

### 27.5. Bằng chứng tối thiểu của một test

1. **Test case ID**, phạm vi được phép, environment và owner.
2. **Sensor ID, observation point, telemetry version**, sampling và freshness.
3. **Resource/service/zone identity** được xác minh theo thời điểm.
4. **Metric/unit/direction, bucket interval, timestamp**, IPv4/IPv6/protocol.
5. Baseline version, training/validation windows, seasonality và sample count.
6. **Expected/observed result** cùng confidence và missing-data notes.
7. Policy/SLO/change-ticket context nếu liên quan.
8. Loại detection, severity, suppression, action và rollback.
9. Privacy controls, không ghi token, private keys, file nhạy cảm hoặc PII không cần.

### 27.6. Positive và negative test phải đi đôi

**Positive:** business traffic hợp lệ, backup và scale event không tạo alert sai, SLO vẫn được theo dõi.

**Negative:** những peer/service connections ngoài policy, direct egress không được duyệt, mất sensor, IPv6 bypass hoặc Pod host path có evidence phù hợp. Một hệ thống “ít alert” không phải thành công nếu nó mất log hoặc bị suppress hết các sự kiện có giá trị.

## 28. Runbook: bất thường lưu lượng mạng vừa xuất hiện

**Tình huống:** SOC/SRE nhận được cảnh báo **egress traffic của Orders API tăng gấp 5 lần trong 5 phút** ở một region. Dashboard firewall vẫn ghi traffic allowed, nhưng chưa rõ do release, backup, lỗi retry hay hành vi trái quyền.

### Giai đoạn 1 – Xác minh tín hiệu có thật

1. Ghi alert ID, metric definition, **sensor, source zone, destination zone, protocol**.
2. Kiểm tra ingestion freshness, sampling rate, exporter version và missing buckets.
3. Xác nhận **bits vs bytes, interval length và counter delta**.
4. Kiểm tra direction: outbound của node hay **client-to-server** thực?
5. Xem NAT/proxy/tunnel mapping; có thay observation point không?
6. Kiểm tra flow duplication, delayed events và source attribution.

Nếu sensor vừa mất dữ liệu hoặc counter reset, xử lý **telemetry quality incident** trước khi khẳng định traffic spike.

### Giai đoạn 2 – So với baseline đúng điều kiện

| Câu hỏi | Nguồn cần đối chiếu |
| --- | --- |
| Baseline nào đang áp? | Service/zone/time bucket/model version |
| Có đủ training samples? | Sample count/coverage/holdout |
| Đây có phải giờ backup/campaign? | Business/change calendars |
| Có deploy, autoscaling, traffic shift không? | CI/CD/HPA/LB/cloud events |
| Thực tế tăng bps hay cả requests/s? | Flow + ingress/APM telemetry |
| Có latency/5xx/retries tăng theo? | SLO/APM/host/network metrics |
| Có destination/peer mới? | DNS, firewall, service graph |
| Có nguồn trái policy? | IAM/workload identity + firewall/CNI policies |

### Giai đoạn 3 – Khoanh vùng

1. Tách **source service/workload/users**, không gắn cả public NAT IP cho một user.
2. Xác định top destinations/ports và source processes nếu có.
3. So **IPv4/IPv6**, TCP/UDP, internal/external, same-node/cross-node.
4. Xem firewall/IPS drop/reject và policy change events.
5. Xem application request shapes, gRPC/HTTP status và database load.
6. Kiểm tra private cloud endpoints/SaaS transfers ngoài Internet SWG.
7. Liên kết với DNS answers và identity data khi nguồn đáng tin.

### Giai đoạn 4 – Phân loại nguyên nhân

| Kịch bản | Bằng chứng gợi ý | Hướng xử lý |
| --- | --- | --- |
| Backup/ETL đúng lịch | Owner/ticket/account, data source phù hợp | SRE capacity review nếu nghẽn |
| Campaign tăng tải | Requests/s tăng tương ứng, deploy/business event | Scaling/rate limits theo SLO |
| Retry storm | Error rate/retransmissions tăng, backend unhealthy | Xử lý timeout, circuit breaker, dependency |
| DNS misconfiguration | NXDOMAIN/SERVFAIL và client retries | DNS/application config fix |
| Policy change | Allowed/denied topology thay với ticket | Review ACL/NetworkPolicy, rollback nếu cần |
| New suspicious destination | Không có app owner, risky identity/context | SOC triage, xác minh quyền |
| Confirmed policy violation | Đích/cổng không được phép, effective flow evidence | Incident containment theo owner |
| Exporter/collector issue | Missing fields, sampling change, counter reset | Telemetry pipeline remediation |

### Giai đoạn 5 – Containment và khắc phục

**Không tự khóa cả subnet hoặc tắt Internet egress chỉ vì một rate spike.** Nếu có bằng chứng rủi ro cao, phối hợp người phụ trách để:

- Chặn **đúng destination/port/identity/session** theo điểm PEP được phê duyệt.
- Thu hồi quyền/token chỉ khi incident process có căn cứ.
- Bảo vệ hệ thống quan trọng bằng rate controls/capacity fixes khi là outage.
- Ghi change ticket, alert, ảnh hưởng và rollback.
- Không sửa raw logs hay xóa bằng chứng.

### Giai đoạn 6 – Xác minh phục hồi

1. Traffic/requests/latency/error rates trở về mức đáp ứng **SLO và nghiệp vụ**.
2. Sensor/flow pipeline lại gửi records đúng.
3. Chính sách allow/deny giữ nguyên các ranh giới được duyệt.
4. Negative test không có bypass mới.
5. Baseline không tự học cửa sổ incident thành normal.
6. Root cause và detector tuning được ghi với owner.

### 28.1. Khi mất telemetry thay vì mất dịch vụ

Nếu một dashboard đột ngột hiển thị **0 Mbit/s**, kiểm tra:

- Last event timestamp có mới không?
- SNMP target, exporter, eBPF agent hoặc cloud log integration có healthy không?
- Có reboot/counter reset hoặc thay credentials không?
- Collector queue/drop ratio và processing failures?
- Những nguồn độc lập như APM/ingress vẫn ghi requests không?

Nếu app vẫn phục vụ bình thường nhưng flow collector mất log, phải tạo **observability incident**, không gọi là service outage hoặc gán baseline 0.

### 28.2. Khi có incident thật nhưng baseline không cảnh báo

Đánh giá những nguyên nhân:

- Detector chỉ nhìn global throughput, bỏ qua service-peer change.
- Aggregation bucket quá dài.
- Sampling bỏ sót rare events.
- Model được huấn luyện trên incident/contaminated data.
- Alert bị suppress quá rộng hoặc rule owner thay đổi.
- CNI/host/cloud route đi ngoài sensor coverage.
- Identity/NAT association sai.

Cải thiện không chỉ bằng giảm threshold; nhiều trường hợp cần **nguồn dữ liệu mới, policy-based rule hoặc phân đoạn baseline phù hợp hơn**.

## 29. Case study tổng hợp: “egress tăng 400%” sau thay đổi hạ tầng

### 29.1. Bối cảnh

Một hệ thống học trực tuyến gồm:

- **Public ingress gateway** đưa traffic HTTPS tới frontend.
- **course-api** và **payment-api** chạy trong Kubernetes.
- **PostgreSQL** và object storage ở private cloud.
- **CI/CD release job** tải artifacts qua HTTPS.
- **Cloud NAT/egress firewall** và CNI telemetry theo Pods.
- **VPN/ZTNA** cho nhân viên và các ứng dụng quản trị.

Đội SRE có dashboard tổng outbound qua một Internet gateway. Sau một rollout vào thứ Ba, firewall report tăng **gần 400%** trong một cửa sổ 5 phút. Hệ thống IDS tạo thêm alert “high outgoing flow volume”. SOC nghi data exfiltration, SRE nghi lỗi network.

### 29.2. Những dữ liệu đầu tiên

| Tín hiệu | Quan sát ban đầu | Giới hạn |
| --- | --- | --- |
| Internet gateway bytes_out | 950 Mbit/s so baseline 190 Mbit/s | Chỉ thấy tổng interface |
| Service request rate | Gần như không đổi | APM chỉ bao phủ API được instrumented |
| Payment API errors | Không tăng đáng kể | Chưa kiểm tra mọi dependency |
| New UDP/443 flows | Tăng | Có thể HTTP/3 rollout, cần xác minh |
| CI job | Có release job được duyệt | Cần xác nhận destination/account và bytes |
| CNI telemetry | Một số Pod IDs đổi do rolling update | IP churn không tự là tấn công |
| Firewall rule logs | Mostly allowed | Allow không chứng minh dữ liệu hợp pháp |
| Data audit | Chưa thấy bất thường | Coverage có thể thiếu |

### 29.3. Kiểm tra số liệu

Trong lab giả định, phát hiện:

1. Cloud team vừa thay một **flow exporter**, đổi active timeout. Số **flow records/s tăng** nhưng không thể so trực tiếp với exporter cũ.
2. Một release job tải **container artifacts lớn** tới approved enterprise registry.
3. HTTP/3 được bật cho một phần clients, khiến **UDP/443 tăng**, TCP/443 giảm.
4. Một Pod backend mới có **unexpected destination** là một endpoint không thuộc danh mục, nhưng bytes rất nhỏ và bị NetworkPolicy chặn.

Do đó có **nhiều hiện tượng độc lập**:

- Spike băng thông thật từ release job hợp lệ.
- Flow count anomaly một phần do measurement change.
- Protocol mix shift do rollout HTTP/3.
- Một **policy-violation candidate** cần SOC triage, không được bỏ qua vì nhỏ.

### 29.4. Tại sao global baseline gây nhầm?

Baseline tổng outbound không phân biệt:

- Frontend customer traffic.
- CI artifacts/backup.
- Database egress.
- Public/approved destination accounts.
- Traffic bị deny ở management zone.

Nếu detector chỉ nhìn **tổng Mbit/s**, nó không phân loại được nghiệp vụ và có thể **bỏ sót flow trái quyền chỉ vài trăm bytes**.

### 29.5. Baseline được thiết kế lại

| Nhóm | Metrics chính | Ngữ cảnh và rule |
| --- | --- | --- |
| **CI/build release** | Bytes up, artifact count, failures | Approved registry + release windows |
| **Frontend/ingress** | Requests/s, p95 latency, 4xx/5xx, TLS mix | Campaign and traffic shift |
| **Course API** | Service peers, requests/s, DB latency | Approved dependency graph |
| **Payment API** | Allowlisted peers/ports, denied attempts | Strict security policy |
| **Database** | Query/export count, connections, egress | Data owner and backup schedule |
| **Internet edge** | Link utilization, bps/pps, drops | Capacity/SLO and sensor health |
| **CNI/Kubernetes** | Pod/workload identity, policy verdict, node path | HPA/deployment/hostNetwork coverage |
| **DNS** | Queries/s, RCODE, latency, A/AAAA mix | Resolver and app changes |

### 29.6. Sơ đồ phân loại

~~~mermaid
flowchart TD
    ALERT["Alert: Internet outbound tăng"] --> SENSOR["Check exporter/sampling/NAT"]
    SENSOR --> CHANGE["Release/HTTP3/CI job calendar"]
    CHANGE --> METRIC["Compare service + protocol + owner baselines"]
    METRIC --> A["Approved artifact upload"]
    METRIC --> B["Exporter flow-count drift"]
    METRIC --> C["New UDP443 traffic by HTTP3"]
    METRIC --> D["Unexpected small peer attempt"]
    A --> OPS["Operational capacity review"]
    B --> QA["Telemetry model revalidation"]
    C --> VALID["Protocol-shift acceptance tests"]
    D --> SEC["Security triage with policy verdict"]
~~~

### 29.7. Phân biệt kết luận có bằng chứng

**Được xác nhận trong kịch bản lab:** release job là nguồn chính của bandwidth tăng; exporter thay đổi cách đếm flows; một policy denied connection xuất hiện; HTTP/3 rollout thay protocol mix.

**Chưa thể kết luận chỉ từ số liệu hiện có:** có data exfiltration; policy-denied attempt là attack; HTTP/3 có làm bypass hay không; uploader đã chuyển tài liệu nhạy cảm. Các giả thuyết cần **destination account, data source, app logs, IAM và coverage** riêng.

### 29.8. Hành động sau điều tra

1. Cập nhật baseline cho **release job** theo lịch/owner và approved registry, không mở allow-all cho cả cloud.
2. Tách baseline **flow record rate trước/sau exporter version**.
3. Dùng **requests/s và UDP/TCP mix** làm context cho HTTP/3.
4. Giữ **alert theo approved peer graph**, độc lập bytes volume, cho denied connection.
5. Kiểm tra egress policy coverage trên IPv6, hostNetwork và private endpoints.
6. Lập canary/holdout validation trước promote model mới.
7. Giữ source data integrity, review thresholds và liên kết incident/change ticket.

### 29.9. Tiêu chí nghiệm thu

- Business upload hợp lệ không tạo security alert sai, nhưng SRE vẫn cảnh báo khi link utilization vượt SLO.
- Flow count change được giải thích theo exporter config, không trộn dữ liệu hai định nghĩa.
- Policy violation candidate được triage dù traffic nhỏ.
- Sensor outage vẫn tạo coverage alarm.
- Service-level/region-level baselines thể hiện đúng thay đổi workload và protocol.
- Toàn bộ decision có **data source, confidence, owner và version**.

## 30. Sai lầm thường gặp, câu hỏi tự đánh giá và tổng kết

### 30.1. Sai lầm thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| “Bình thường nghĩa là an toàn” | Baseline học cả hành vi trái quyền | Kết hợp policy/approved dependency graph |
| “Một ngưỡng Mbps dùng được mọi service” | Backup gây false positive, app nhỏ bị bỏ sót | Baseline theo service/role/time |
| “Mất log nghĩa là không có traffic” | Dashboard 0 tạo false negative | Freshness/coverage alerts, NULL khác zero |
| “SNMP counter là bitrate” | Nhầm counter tích lũy với tốc độ | Tính delta/time và xử lý reset |
| “Mbps là MB/s” | Sai hệ số 8 và prefix | Ghi rõ bit/s, bytes/s, SI/binary |
| “Mọi flow record là một kết nối mới” | Flow timeout tăng count | Ghi exporter timeout/template |
| “Sampling 1:1000 có thể nhân chính xác mọi flow” | Sai ước lượng/rare-event loss | Ghi sampling và uncertainty |
| “NAT public IP là một user” | Attribution sai người/thiết bị | Pre/post NAT, identity và time mapping |
| “Một flow outbound lớn là data exfiltration” | Gán kết luận vượt evidence | Data source, account, app authorization |
| “Một TCP 443 flow chắc chắn là HTTPS” | Sai protocol classification | TLS/proxy/app evidence |
| “Một UDP 443 flow chắc chắn là HTTP/3” | Nhầm protocol | Protocol-aware observation |
| “Passive TLS1.3 sensor nhìn đầy đủ cert và payload” | Dựng dữ liệu không có | Xác định TLS visibility/hook |
| “Không có DNS query nghĩa là không có HTTPS” | Bỏ cache, DoH/proxy DNS | DNS+flow+endpoint correlation |
| “Một lần spike là attack” | Chặn nhầm campaign/release | Business/event correlation |
| “p99 của 10 samples đủ chính xác” | Threshold thiếu tin cậy | Minimum sample counts và holdout |
| “Giá trị p95 của 1h bằng p95 5m” | Dùng nhầm phân phối | Giữ consistent bucket/algorithm |
| “MAD/normal z-score hợp với mọi traffic” | False alarms trên heavy tails | Robust/seasonal models có review |
| “Traffic always low là service khỏe” | Bỏ qua lỗi app hoặc cảm biến | APM/SLO và coverage |
| “Một policy hẹp override allow rộng” | Effective security policy khác mong muốn | Rà union/priority theo engine |
| “Đổi exporter không ảnh hưởng baseline” | Metric drift giả | Model/telemetry versioning |
| “Global bandwidth đủ để phát hiện lateral movement” | Peer nhỏ bị che trong aggregate | Zone/service graph và policy checks |
| “IP Pod ổn định để baseline” | Autoscaling/reschedule đổi IP | Workload/Pod UID + service identity |
| “Cloud Internet firewall thấy mọi traffic” | Bỏ private endpoints, SaaS-to-SaaS | Cloud resource/API audit và CNI |
| “NetworkPolicy tồn tại chắc chắn enforce” | CNI thiếu/không hỗ trợ engine | Effective policy tests |
| “IPv4 traffic giảm nghĩa là traffic biến mất” | IPv6 path được bỏ qua | Dual-stack combined/per-family views |
| “Có nhiều alert là có nhiều incidents” | Alert storm do cùng root cause | Dedup/grouping và evidence |
| “Cảnh báo nhiều thì tự tăng ngưỡng” | Che một incident kéo dài | Triage/owner review/shadow model |
| “Model auto-learning domain mới là an toàn” | Poisoned baseline và whitelist trái quyền | Owner approval và policy invariants |
| “Đã có baseline là không cần app authorization” | Không kiểm tra quyền business/data | IAM/mTLS/API object checks độc lập |
| “Triển khai đủ dashboard là xong” | Không có runbook/test/evidence | Positive+negative tests, ownership, rollback |

### 30.2. Câu hỏi ôn tập

**1.** Baseline thống kê khác security allowlist ở đâu?

*Gợi ý:* Baseline mô tả điều hay xảy ra; allowlist xác định điều được phép. Một hoạt động thường gặp vẫn có thể bị cấm.

**2.** Vì sao byte counter SNMP không thể dùng nguyên làm throughput?

*Gợi ý:* Đó là counter tích lũy. Cần delta/time, kiểm tra reset và units.

**3.** p95 của 5-minute samples có thể dùng thay p95 của daily totals không?

*Gợi ý:* Không; phân phối và mức tổng hợp khác nhau.

**4.** Khi thấy traffic về 0, vì sao phải kiểm tra sensor health?

*Gợi ý:* Missing telemetry không có nghĩa service không chuyển traffic.

**5.** NetFlow/IPFIX có những hạn chế gì khi dùng để phát hiện upload HTTPS?

*Gợi ý:* Không có HTTP payload, direction và sampling/aggregation có giới hạn; NAT attribution cần mapping.

**6.** Khi đổi từ HTTP/2 sang HTTP/3, những chỉ số nào có thể thay mà requests/s không đổi?

*Gợi ý:* TCP vs UDP443 flows, concurrent sessions, transport counters.

**7.** Vì sao một Pod IP không phù hợp làm identity baseline dài hạn?

*Gợi ý:* Pod reschedule và autoscaling làm IP thay; dùng workload/service identity.

**8.** Một firewall rule mới làm deny tăng gấp ba. Có nên lập security incident ngay không?

*Gợi ý:* Xem policy change, nguồn/đích, expected outcomes và impact; deny không tự chứng minh attack.

**9.** MAD giúp gì? Khi nào nó vẫn kém phù hợp?

*Gợi ý:* Robust hơn mean/std với outliers; vẫn cần seasonality, sample size và hiểu phân phối.

**10.** Vì sao baseline trên global egress bytes bỏ sót lateral movement?

*Gợi ý:* Một vài packet trái quan hệ service bị che trong aggregate lớn.

**11.** Khi không thấy true SNI trong ECH, nên dùng những nguồn nào?

*Gợi ý:* Endpoint/process, managed DNS/proxy và app/SaaS telemetry khi có quyền.

**12.** Làm sao phân biệt spike thật với thay exporter/sampling?

*Gợi ý:* Check exporter version, template/active timeout, independent sensors và APM.

**13.** Khi application có requests/s không đổi nhưng bytes/s tăng, có thể do gì?

*Gợi ý:* Payload size, compression, cache, retries hoặc measurement changes.

**14.** Tại sao baseline theo giờ làm việc có thể sai với backup/payroll?

*Gợi ý:* Batch/seasonality và event calendar khác hẳn user-facing traffic.

**15.** Khi data source thiếu user identity, có nên gắn người từ public NAT IP?

*Gợi ý:* Không; phải ghi unknown hoặc dùng pre/post NAT mapping cùng timestamp và các logs đáng tin.

**16.** Cách đo mô hình có khả năng bỏ sót incident ra sao?

*Gợi ý:* Holdout positive/negative tests, sensor coverage, sample rate và policy violation events.

**17.** Vì sao cloud private endpoint vẫn cần traffic/data baseline?

*Gợi ý:* Cross-account/object transfers có thể đi trong private routing, không qua Internet firewall.

**18.** Thế nào là baseline đã sẵn sàng?

*Gợi ý:* Có data quality, representative windows, owner, version, sufficient samples, holdout tests và scope.

### 30.3. Bài tập thiết kế hệ thống

Một tổ chức có **văn phòng, remote VPN/ZTNA, 2 regions cloud và Kubernetes cluster**, dùng ứng dụng sales/HR/payment, database, SaaS storage và CI/CD artifacts. Nhiệm vụ là thiết kế một nền tảng baseline lưu lượng bình thường và phát hiện bất thường mà không làm giảm hiệu quả vận hành.

Hãy:

1. Vẽ topology **interface/router → NetFlow/IPFIX/host/CNI/cloud flow → collector → normalization → time-series → baseline → detector → SOC/SRE**.
2. Lập bản đồ **network zones, service IDs, ingress/egress và approved dependency graph**.
3. Định nghĩa metric và unit cho bps, pps, flows/s, DNS error ratio, requests/s, p95 latency.
4. Quy định observation point, exporter template/version, sampling, direction và NAT correlation.
5. Lập baseline riêng cho **frontend, DB, backup, CI, HR, VPN và Kubernetes**; giải thích vì sao không gộp.
6. Chọn window/bucket và seasonality theo **weekday, weekend, nightly backup, month-end**.
7. Chỉ ra cách tính median, p95, IQR hoặc MAD và điều kiện mẫu đủ tin cậy.
8. Thiết kế **missing vs zero** và sensor freshness alarm.
9. Xây một rule **unexpected peer dù rất ít bytes** theo security policy.
10. Xây một rule **throughput anomaly** gắn với release/change events.
11. Thiết kế DNS, TLS/HTTP3 và IPv4/IPv6 baselines có coverage rõ.
12. Phân biệt app requests/s, network flow records/s và byte throughput khi chọn SLO.
13. Thiết kế **model versioning/shadow baseline/rollback**, không auto-learn incident.
14. Lập ít nhất 15 positive/negative lab tests với synthetic traffic/events.
15. Xây log schema bảo vệ user/privacy và evidence quality.
16. Viết runbook cho **spike băng thông** và **telemetry loss giả báo 0**.
17. Đặt KPI: sensor coverage, ingestion lag, false-positive rate, time to detect/triage, stale baseline ratio.
18. Giao owner cho network, SOC, app, platform, privacy và change approval.

**Tiêu chí đạt:** detector phân biệt được **outlier thống kê với policy violation**, có baseline đúng metric/nguồn/lịch, không suy traffic=0 khi mất sensor, nhận biết legitimate business spikes và vẫn phát hiện luồng trái phép có volume thấp.

### 30.4. Những điều cần ghi nhớ

- **Baseline là mô hình hành vi quan sát thường gặp theo điều kiện**, không phải định nghĩa điều được phép hay bảo đảm an toàn.
- **Định nghĩa metric, unit, chiều traffic, sensor và thời gian** trước khi dùng số liệu; tránh nhầm Mbps/MBps, counter/rate và records/connections.
- **Dữ liệu thiếu không phải giá trị 0**; telemetry pipeline phải có coverage/freshness alert độc lập với anomaly detector.
- **NAT, proxy, overlay, VPN và asymmetric routing** thay đổi những gì sensor nhìn thấy; cần correlation và attribution có bằng chứng.
- **Phân đoạn baseline theo service, zone, role, protocol và business calendar**; không dùng một ngưỡng duy nhất cho mọi workload.
- **Median, quantile, IQR và MAD hữu ích nhưng có điều kiện**; sample size, distribution, seasonality và sampling quyết định độ tin cậy.
- **DNS, TLS, TCP, UDP/QUIC, ứng dụng và cloud metrics** cung cấp những bức tranh khác nhau; TLS mã hóa không cho passive observer đọc payload HTTP.
- **Security policy violation không cần vượt ngưỡng lưu lượng**; một peer/cổng trái quyền với vài bytes vẫn đáng triage.
- **Anomaly không tự là attack**: campaign, backup, deploy, autoscaling, protocol shift và exporter change đều có thể tạo độ lệch hợp lệ.
- **Đổi model cần versioning, holdout, shadow tests, owner approval và rollback**; không tự huấn luyện bình thường mới từ incident.
- **Kubernetes/Cloud/IPv6/hostNetwork/private endpoints** tạo nhiều đường cần có coverage tương ứng, không dựa một Internet firewall làm nguồn tuyệt đối.
- **Cảnh báo tốt phải có bằng chứng, chất lượng dữ liệu, giới hạn suy luận và runbook**, bảo vệ quyền riêng tư và business availability.
