# Alert theo ngưỡng và theo hành vi: thiết kế phát hiện bất thường trong giám sát mạng

## 1. Vì sao giám sát mạng cần cả alert theo ngưỡng lẫn theo hành vi?

Trong một hạ tầng hiện đại, lưu lượng có thể đi qua firewall, VPN, load balancer, Kubernetes CNI, cloud VPC/VNet, DNS resolver, proxy, IDS/IPS và nhiều dịch vụ mã hóa TLS. Hệ thống giám sát thu về **metrics, flow records, event logs và traces**, nhưng **có dữ liệu không đồng nghĩa biết khi nào cần hành động**. Một hệ thống alert tốt phải chuyển quan sát thành **tín hiệu có ngữ cảnh, đủ đáng tin và gắn với một quy trình phản ứng**.

Ví dụ: một đường Internet 1 Gbit/s thường dùng 200 Mbit/s, hôm nay tăng lên 900 Mbit/s. **Alert theo ngưỡng** có thể phát khi băng thông vượt 80% capacity trong 5 phút. Trong một tình huống khác, máy quản trị bình thường chỉ kết nối hai server nội bộ, đêm nay bắt đầu thử hàng chục cổng trên nhiều địa chỉ. Tổng băng thông vẫn rất thấp nên threshold băng thông sẽ không phát hiện, nhưng **alert theo hành vi** có thể nhận ra thay đổi so với baseline của **chính workload** ấy.

Ngược lại, trong dịp phát hành sản phẩm, gateway nhận số request cao gấp 10 lần baseline nhưng vẫn đáp ứng SLO. Chỉ dựa vào behavioral deviation có thể gây hàng nghìn cảnh báo; chỉ dựa vào threshold cố định cũng có thể bỏ sót một API nhạy cảm bị quét chậm. **Hai cách tiếp cận bổ sung cho nhau**, nhưng cả hai phải xử lý sampling, seasonality, sự kiện bảo trì, các tài nguyên mới, thiếu dữ liệu và rủi ro tự động phản ứng sai.

Thuộc chương **Giám sát mạng và telemetry**, module **SECURITY_NETWORK_SECURITY**, bài này liên hệ trực tiếp với **network segmentation, firewall, VPN, IDS/IPS, DNS protection, phân tích lưu lượng, threat modeling, cloud security và giám sát xâm nhập**. Mục tiêu không phải biến mọi bất thường thành incident, mà là **phát hiện đúng dấu hiệu cần xử lý, giảm thời gian nhận biết và giới hạn báo động giả**.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **threshold alerts** (ngưỡng tĩnh/có điều kiện), **baseline/adaptive threshold**, **behavioral/anomaly alerts** và **signature/rule detection**.
2. Chọn **nguồn telemetry**, đơn vị đo, nhóm tài nguyên, cửa sổ thời gian và cách tổng hợp phù hợp.
3. Thiết kế **high/low threshold, rate of change, ratio, duration, hysteresis và multi-signal alerts**.
4. Giải thích **baseline theo workload, giờ/ngày, mùa vụ, peer group**, và giới hạn của z-score, MAD, EWMA.
5. Phát hiện các mẫu **port scan, lateral movement, DNS tunneling, data exfiltration, VPN brute-force symptoms, DDoS và telemetry outage** mà không kết luận quá mức.
6. Đánh giá **false positive/false negative, precision, recall, detection latency, alert fatigue và business impact**.
7. Thiết kế pipeline **normalize → enrich → detect → deduplicate/correlate → triage → respond → learn**.
8. Thực hiện **lab Python offline** với dữ liệu giả lập, lập ma trận kiểm thử và runbook vận hành SOC.

## 2. Các khái niệm: signal, event, alert, incident và baseline

| Thuật ngữ | Ý nghĩa thực tế | Không được nhầm với |
| --- | --- | --- |
| **Metric** | Giá trị số theo timestamp và nhãn, ví dụ bps hoặc dropped packets/s | Một sự kiện bảo mật đã được chứng minh |
| **Event/log** | Bản ghi tại một thời điểm hoặc khoảng thời gian: firewall DENY, login failed | Tất cả packets hoặc mọi kết nối thực |
| **Flow record** | Metadata một nhóm packets/flow ở điểm quan sát; có thể sampled/aggregated | Một phiên TCP hoàn chỉnh hoặc HTTP request |
| **Signal** | Quan sát hoặc đặc trưng dùng ra quyết định, như distinct ports/minute | Kết luận actor có ý định xấu |
| **Detection rule** | Điều kiện, thống kê hoặc mô hình phát hiện event đáng xem | Chính sách cho phép tự block mọi trường hợp |
| **Alert** | Kết quả phát hiện có đủ thông tin để người hoặc automation xử lý | Incident được xác minh |
| **Finding** | Kết quả kiểm tra/risk hypothesis, có thể chứa nhiều alerts | Một hành động trái phép chắc chắn đã xảy ra |
| **Incident** | Sự kiện được phân loại theo quy trình ứng phó tổ chức | Mỗi lần metric vượt ngưỡng |
| **Baseline** | Mẫu hoạt động mong đợi từ lịch sử hoặc peer group có điều kiện | Trạng thái luôn an toàn |
| **Threshold** | Giá trị/điều kiện dùng quyết định kích hoạt | Ngưỡng nào cũng có tính pháp lý hoặc universal |
| **SLO/SLI** | Mục tiêu/chỉ số chất lượng dịch vụ | Ngưỡng IDS/IPS cho tấn công |
| **False positive (FP)** | Alert báo vấn đề khi tình huống thực là hợp lệ | Thiếu bằng chứng nên chắc là benign |
| **False negative (FN)** | Vấn đề đáng phát hiện nhưng detector bỏ sót | Không có logs nên chắc không có vấn đề |

### 2.1. Luồng từ telemetry đến hành động

~~~mermaid
flowchart LR
    A["Firewall / DNS / VPN / IDS / VPC / App"] --> B["Collect + normalize"]
    B --> C["Validate health, timestamps, schema"]
    C --> D["Enrich asset/identity + baseline"]
    D --> E["Threshold and behavior detectors"]
    E --> F["Group, dedupe, correlate, score"]
    F --> G["SOC triage / alert routing"]
    G --> H["Validate incident / respond"]
    H -. "Feedback / detection tuning" .-> D
~~~

**Đừng đặt mô hình ML hoặc rule đắt tiền trước khi kiểm tra dữ liệu đầu vào.** Nếu pipeline thiếu flow logs một nửa các subnet, thuật toán tốt cũng không thể chứng minh nửa mạng còn lại an toàn.

### 2.2. Bốn chiều quyết định alert

Một alert chất lượng trả lời:

- **Điều gì?** Metric/event, rule ID/version, giá trị quan sát, ngưỡng hay baseline.
- **Ở đâu/ai?** Account/project, VPC/VNet, interface, source/destination, workload/owner và environment, gắn theo thời điểm.
- **Khi nào?** Event time UTC, evaluation window, ingestion time, duration và data freshness.
- **Làm gì tiếp?** Severity, confidence, ảnh hưởng, evidence liên quan, runbook, người phụ trách và phương án kiểm tra.

Chỉ gửi thông báo “CPU HIGH” hoặc “Network anomaly” mà không có **resource, window, owner và evidence** sẽ tạo alert fatigue dù detector đúng về mặt tính toán.

## 3. Ba lớp phát hiện thường dùng

### 3.1. Ngưỡng tuyệt đối (static threshold)

Điều kiện như:

~~~text
IF interface_utilization_percent > 85
FOR 5 consecutive valid minutes
THEN raise WARNING
~~~

Dễ giải thích, phù hợp **capacity, SLO, queue depth, packet loss, sensor health, interface down**. Nhưng giá trị “bình thường” của một đường 100 Mbit/s và 100 Gbit/s khác nhau; 1.000 requests/s có thể bình thường ở API lớn và bất thường ở bastion.

### 3.2. Ngưỡng thích nghi (dynamic/seasonal threshold)

~~~text
IF current_dns_queries_per_minute >
   expected_range_for_this_resolver_and_time
FOR 3 valid windows
THEN investigate
~~~

Giá trị expected range có thể đến từ **rolling median, percentile, EWMA, time-of-week hoặc learned model**, nhưng phải có **history đáng tin, sample size tối thiểu và cơ chế kiểm soát learning drift**.

### 3.3. Phát hiện hành vi (behavioral detection)

Đặt câu hỏi về **quan hệ, chuỗi sự kiện, đối tượng mới hoặc thay đổi mẫu giao tiếp**:

~~~text
An application workload that normally talks to 3 known internal
services starts contacting 45 distinct internal hosts on 14 ports,
with repeated rejects outside its deployment window.
~~~

Behavioral detection không nhất thiết dùng AI: **SQL distinct counts, graph changes, rare destination rules, time-of-day modeling, sequence correlations** đã là phát hiện hành vi. AI/ML có thể bổ sung nhưng cần giải thích, đánh giá accuracy, cost và khả năng chống data poisoning.

### 3.4. So sánh theo tiêu chí thực hành

| Tiêu chí | Static threshold | Adaptive threshold | Behavioral/sequence |
| --- | --- | --- | --- |
| Dễ giải thích | Cao | Trung bình nếu biết baseline | Tùy rule/model |
| Cần lịch sử | Ít hoặc không | Có, cần đủ chu kỳ | Thường cần context/historical profile |
| Bắt sự cố capacity | Rất phù hợp | Phù hợp | Có thể nhưng không ưu tiên |
| Bắt scan chậm/hiếm | Kém nếu chỉ đo băng thông | Một phần | Có lợi thế khi xét hành vi/đích |
| Ảnh hưởng seasonality | Dễ sai | Có thể xử lý | Phải đưa vào mô hình/baseline |
| Nhu cầu tuning | Cần chọn threshold | Chọn model/window và thresholds | Cần hiểu use case, ground truth |
| Rủi ro drift/poison | Thấp ở threshold cố định | Có | Có nếu mô hình học từ traffic bất thường |
| Độ phức tạp vận hành | Thấp | Trung bình | Có thể cao |

**Không có loại nào luôn tốt nhất.** Thiết kế giám sát tốt có thể dùng **static safety guardrail** cho capacity/telemetry outage và **behavioral rules** cho anomalous traffic, cùng một pipeline triage.

## 4. Đơn vị đo và phương pháp tổng hợp phải đúng

Alert sai nhiều khi do **đơn vị và phép tổng hợp sai**, không phải do ngưỡng thiếu thông minh.

### 4.1. Counter khác gauge

- **Counter:** số tăng tích lũy, ví dụ network bytes_total, packets_dropped_total, requests_total; có thể reset khi process/network agent restart.
- **Gauge:** giá trị tức thời có thể tăng/giảm, ví dụ active_connections, interface_utilization_percent, queue_depth.
- **Histogram:** quan sát phân phối latency/size, thường có bucket counters cần dùng **rate** và cách tính quantile theo hệ thống.
- **Event/flow record:** không thể tự xử lý như counter liên tục; mỗi dòng có timestamp/interval và dữ liệu đầy đủ/thiếu theo nguồn.

Đối với counter băng thông:

\[
\mathrm{bps} =
8 \times \frac{\Delta(\mathrm{bytes\_total})}{\Delta t}
\]

Nếu counter reset trong cửa sổ, phép trừ thô có thể ra số âm; cần **counter-reset-aware rate function** hoặc loại segment lỗi theo telemetry semantics.

### 4.2. Băng thông và utilization

Giả sử interface danh định **1 Gbit/s**, quan sát egress **825 Mbit/s**:

\[
\mathrm{utilization} = \frac{825}{1000} \times 100\% = 82.5\%
\]

Nhưng capacity danh định không phải luôn **effective throughput**: shaping/QoS, full/half duplex, tunnel encryption overhead, cloud limits, burst quotas và path bottleneck cần xét. Trong mạng hai chiều, **ingress/egress** có thể có giới hạn riêng; đừng cộng hai chiều rồi chia cho capacity một chiều không đúng.

### 4.3. COUNT, SUM, AVG, MAX, DISTINCT có nghĩa khác

| Aggregate | Câu hỏi | Rủi ro khi dùng sai |
| --- | --- | --- |
| COUNT(records) | Có bao nhiêu bản ghi được thu? | Một flow record không bằng một connection |
| SUM(bytes) | Tổng số bytes quan sát trong các records | Sampling, double-count đa NIC, retransmission |
| AVG(rate) | Tốc độ trung bình trong cửa sổ | Che burst ngắn gây packet loss |
| MAX(gauge) | Đỉnh đo được | Một outlier đơn lẻ có thể tạo false alert |
| P95/P99(latency) | Phần đuôi phân phối | Ít mẫu hoặc histogram config sai làm không ổn định |
| COUNT(DISTINCT dst_ip) | Số đích khác nhau nhìn thấy | NAT/CDN/shared IP và ephemeral IP gây nhầm |
| RATIO(deny, all) | Tỷ lệ bị từ chối | Denominator quá nhỏ khiến tỷ lệ 100% dễ gây ảo giác |
| Rate of change | Tăng/giảm nhanh thế nào | Counter reset, sampling gaps, rolling-window effects |

### 4.4. Ratio phải có mẫu tối thiểu

Một bastion có **1 kết nối bị REJECT trên 1 attempt** → tỷ lệ deny 100%. Một WAF có **10.000 requests bị DENY trên 100.000 attempts** → 10%. Tỷ lệ đầu có thể kém đáng tin vì chỉ một mẫu; tỷ lệ sau có ngữ cảnh khối lượng. Detector theo ratio nên có điều kiện **minimum denominator/volume**, đồng thời giám sát **count** để không bỏ sót các tài nguyên ít traffic nhưng nhạy cảm.

## 5. Cửa sổ thời gian: event time, ingestion time và xử lý trễ

Hệ thống giám sát mạng có thể ingest logs muộn do **aggregation interval, sampling, network/backpressure, collector outage hoặc regional delivery**. Một alert streaming dùng sai timestamps dễ gán sự cố cho sai thời điểm.

| Thời gian | Giải thích |
| --- | --- |
| **Event time** | Lúc giao tiếp/packet/log event được quan sát tại nguồn |
| **Window start/end** | Khoảng thời gian detector nhóm events hoặc tính rate |
| **Ingestion time** | Lúc collector/SIEM nhận bản ghi |
| **Evaluation time** | Lúc rule được chạy hoặc model đánh giá |
| **Alert emission time** | Lúc hệ thống tạo alert |
| **Acknowledgement time** | Lúc SOC nhận/thừa nhận alert |
| **Containment time** | Lúc hành động giảm rủi ro thực sự có hiệu lực |

### 5.1. Tumbling, sliding và session windows

~~~text
Tumbling windows 5 phút:
  [10:00,10:05), [10:05,10:10), [10:10,10:15)

Sliding windows 5 phút, bước 1 phút:
  [10:00,10:05), [10:01,10:06), [10:02,10:07), ...

Session windows:
  Nhóm events theo khoảng cách thời gian không hoạt động;
  cần rule cụ thể và cẩn trọng đối với long-lived flows.
~~~

**Sliding windows** cho phép phản ứng nhanh hơn tại nhiều mốc nhưng dễ tạo **alerts trùng lặp từ cùng traffic**; phải dedupe/cooldown. **Tumbling windows** đơn giản nhưng một burst nằm ngay ranh giới có thể bị chia thành hai phần và không vượt ngưỡng ở cửa sổ nào.

### 5.2. Event-time watermark và late arrivals

Trong pipeline stream analytics, **watermark** là một chiến lược ước lượng tiến độ của event time và độ trễ cho phép; events đến quá muộn có thể bị **drop, side output hoặc cập nhật result** tùy engine. Nếu rule phát alert dựa trên window chưa đủ dữ liệu, cần ghi **provisional vs final**, nguồn và revision; không tự sửa timeline âm thầm khiến investigator không biết alert vì sao đổi.

### 5.3. Sampling và gaps

Nếu VPC flow logs được lấy mẫu **10%** theo semantics của nguồn, một detector “nhiều nhất 50 unique destinations” quan sát từ mẫu **không chứng minh** chỉ có 50 destinations thật. Một số hệ thống cung cấp sampling weights/estimated counts nhưng phải hiểu cơ chế lấy mẫu và sai số. Đừng đơn giản nhân mọi distinct cardinality lên 10 rồi gọi đó là sự thật.

**Missing data phải là một trạng thái riêng**: NORMAL, ALERTING và NO_DATA/STALE không thể đánh đồng. Một pipeline đột ngột giảm toàn bộ firewall DENY về 0 cùng lúc app throughput vẫn cao có thể là **lỗi thu thập**, không phải mạng an toàn hơn.

## 6. Thiết kế alert theo ngưỡng cố định

### 6.1. Ngưỡng cao, thấp, kéo dài và tốc độ thay đổi

| Rule | Tình huống | Ví dụ có điều kiện |
| --- | --- | --- |
| **High threshold** | Saturation | Egress utilization >85% trong 5 phút hợp lệ |
| **Low threshold** | Dịch vụ bị mất hoặc kiểm tra health | VPN tunnels_up < số tunnel tối thiểu trong 2 windows |
| **Rate of change** | Tăng đột ngột | Reject rate tăng >4 lần so với cửa sổ trước, đủ sample size |
| **Threshold ratio** | Error/deny proportion | SYN failed ratio >20% khi tổng connections >=500 |
| **Multiple conditions** | DDoS symptoms | PPS cao AND drops cao AND latency tăng |
| **SLO burn rate** | Tiêu thụ error budget quá nhanh | Error budget burn vượt quy tắc đa cửa sổ có phê duyệt |
| **No-data threshold** | Collector mất tín hiệu | Không có heartbeat/records quá freshness SLA trong khi resource đang active |

**Các số chỉ là minh họa**, không phải tiêu chuẩn cho mạng 1 Gbit/s, hệ thống VPN hay IDS cụ thể. Phải derive theo **business SLO, capacity, baseline, risk và cost of false positives**.

### 6.2. Duration: tránh báo chỉ vì một spike

Một burst 1 giây có thể vô hại nhưng một số loại tấn công cũng rất ngắn. Do đó phải chọn **measurement resolution và minimum duration** theo threat model:

~~~text
Metric: firewall_dropped_packets_per_second
Evaluation: mỗi 1 phút
Open condition: rate > 5000 pps in 3 of last 5 valid windows
Clear condition: rate < 2000 pps in 5 valid windows
No-data: separate DATA_QUALITY alert after 2 missed windows
~~~

Đây là dạng **M-of-N detection** kết hợp **hysteresis**. Nó giảm nhấp nháy nhưng có thể làm tăng **detection delay**; với security hard stops như **unauthorized admin login success** đôi khi cần alert ngay từ một event có độ tin cậy cao.

### 6.3. Hysteresis: hai ngưỡng bật/tắt

~~~mermaid
stateDiagram-v2
    [*] --> NORMAL
    NORMAL --> PENDING: Value > high threshold
    PENDING --> ALERTING: Condition persists M-of-N
    PENDING --> NORMAL: Condition cleared before trigger
    ALERTING --> RECOVERING: Value < low threshold
    RECOVERING --> NORMAL: Stable low for clear window
    RECOVERING --> ALERTING: Value rises again
    NORMAL --> NO_DATA: Missing required measurements
    ALERTING --> NO_DATA: Missing data, preserve incident state
    NO_DATA --> PENDING: Measurements resume, re-evaluate
~~~

Không để **NO_DATA** tự chuyển thành **NORMAL** và auto-close một incident nghiêm trọng. Khi khôi phục telemetry, rule phải làm rõ **tình trạng alert cũ, last known severity và cần bằng chứng gì để resolve**.

### 6.4. Ngưỡng theo vai trò tài sản

| Resource | Cùng một metric nhưng ngữ cảnh khác | Baseline/threshold nên xét |
| --- | --- | --- |
| Public API ingress | RPS/conn cao là bình thường | Capacity, latency, 5xx, WAF/edge metrics |
| Database subnet | Inbound từ clients rất hẹp | Allowed peers, new source identity, query owner |
| Bastion/jump host | Lưu lượng ít, quản trị hiếm | Unusual target, MFA/session events |
| DNS resolver | QPS cao, nhiều query types | Per-client profile, NXDOMAIN rate, entropy/suspicious names |
| VPN concentrator | Logins theo ca làm việc | Fail/success ratio, geo/ASN, user baselines |
| Backup host | Egress burst định kỳ | Job schedule/approved destinations, deviations |
| Service mesh | RPS/mTLS handshakes giữa services | Service graph, authZ denies, retries, cert expiry |

**Một ngưỡng global duy nhất** dễ làm bastion không phát hiện bất thường và public API báo giả liên tục. Tối thiểu phải phân biệt **environment, service role, network interface capacity và thời gian**.

## 7. Chất lượng telemetry và tín hiệu giám sát chính hệ thống cảnh báo

Trước khi tính threshold hoặc baseline, phải biết **sensor có hoạt động, dữ liệu có đầy đủ và parser có hiểu đúng schema không**.

### 7.1. Tám nguồn lỗi dữ liệu

1. **Missing source:** Pod/VM/NIC mới chưa bật collection; một region không xuất log.
2. **Partial scope:** Chỉ thu ACCEPT mà rule lại dùng DENY; thiếu IPv6/VPN/DR.
3. **Sampling/aggregation:** Event hiếm biến mất, bytes/counts không chính xác như raw packets.
4. **Clock/timezone skew:** Event bị gán vào window sai.
5. **Schema drift:** Vendor đổi field action/protocol; parser đẩy thành UNKNOWN hoặc âm thầm bỏ record.
6. **Duplicate delivery:** Retry từ log shipper gây tăng giả counts.
7. **High cardinality:** Nhãn IP/port/request_id tạo quá nhiều time series, collector bị quá tải.
8. **Delayed delivery:** Alert chỉ phát sau khi hành động đã kết thúc, dẫn đến sai thứ tự điều tra.

### 7.2. Health alerts cho pipeline

| Health signal | Alert hữu ích | Đừng kết luận |
| --- | --- | --- |
| Collector heartbeat thiếu | Sensor unavailable/stale | Không có traffic hay attack |
| Ingestion lag p95 tăng | Detections có thể bị trễ | Endpoint chắc không an toàn |
| Per-source event volume giảm mạnh | Data quality incident, kiểm tra scope/IAM | Mọi lưu lượng đã giảm |
| Parsing/schema error rate tăng | Sai mapping/version, fallback | Bản ghi còn lại đại diện đầy đủ |
| Duplicate ID rate tăng | Replay/retry, risk inflated count | Attacker chắc tạo nhiều packet |
| Flow log SKIP/unknown action | Coverage incomplete | Action là ACCEPT |
| NTP/clock offset lớn | Timeline unreliable | User cố tình giả mạo timestamp |
| SIEM rule execution failures | Detector không đánh giá đúng | Metric dưới ngưỡng |

### 7.3. Tách an ninh và tính sẵn sàng của detection

Tạo một **data-quality alert** độc lập khi nguồn bắt buộc thiếu, thay vì để dashboard security hiển thị “0 incidents”. Nếu **collector đã mất**, các detector phụ thuộc nó nên có trạng thái **DEGRADED/NO_DATA** và các báo cáo phải ghi giới hạn kết luận.

## 8. Thiết kế baseline theo hành vi: “bình thường” phải có điều kiện

Baseline là **mẫu hoạt động tham chiếu** dùng để so với sự kiện mới. Nếu coi toàn bộ mạng có chung “normal”, detector sẽ bỏ qua sự khác nhau giữa **bastion, database, CDN gateway, backup worker, DNS resolver và VPN access**.

### 8.1. Baseline theo những chiều nào?

| Chiều | Ví dụ | Tại sao quan trọng? |
| --- | --- | --- |
| **Resource identity** | VM/Pod/ServiceAccount/ENI tại thời điểm | IP/Pod có thể bị tái sử dụng; workload mới không mang lịch sử cũ |
| **Service role** | Database, ingress API, bastion, backup | Mức traffic “thường” khác nhau nhiều |
| **Environment** | Prod, Dev, DR | Dev có thể scan/test; Prod có chính sách chặt hơn |
| **Time-of-day/week** | Giờ làm việc, ca trực, weekend | VPN/SSO hoặc batch có chu kỳ |
| **Business calendar** | Release, cuối tháng, sale campaign | Spike hợp lệ không nên thành attack |
| **Protocol/operation** | DNS, TCP/443, SSH, gRPC, HTTP POST | Bytes cùng mức nhưng risk khác |
| **Network direction** | Internet ingress, east-west, egress | Chuyển dữ liệu ra ngoài nhạy cảm hơn giữa peers được phép |
| **Peer group** | Cùng nhóm application replicas | Một instance khác hẳn peers cần kiểm tra |
| **Asset criticality** | Prod database vs demo app | Mức độ ưu tiên và ngưỡng điều tra khác |
| **Data quality** | Complete, sampled, stale, missing | Không học baseline từ số đo lỗi |

### 8.2. Cold start và tài sản mới

Một Pod mới chưa có lịch sử traffic đủ dài. Nếu hệ thống đặt baseline là **0** rồi báo khi có request đầu tiên, sẽ tạo false positives. Nếu tự coi bất kỳ lưu lượng nào của Pod mới là bình thường sau 5 phút học, attacker có thể **poison baseline**.

Giải pháp:

1. Bắt đầu với **service-role baseline hoặc peer-group baseline** được kiểm chứng.
2. Gắn trạng thái **COLD_START / insufficient evidence** và vẫn áp **static security guardrails**.
3. Kiểm soát **training period, minimum sample count và biến thiên hợp lệ**.
4. Không tự học những windows có **incident, rollout lỗi, stress test hoặc telemetry outage**.
5. Chuyển sang baseline riêng khi đã có dữ liệu đủ tin và người sở hữu xác nhận.

### 8.3. Baseline có thể trở nên sai

Ứng dụng đổi mô hình kết nối sau release, chuyển region, scale gấp 5 hoặc nhận thêm nhóm khách hàng mới. Khi đó baseline cũ có thể báo giả; baseline cập nhật tự động quá nhanh lại **hấp thụ tấn công kéo dài**. Nên giữ **versioned baselines**, lưu **baseline provenance**, xem drift theo change tickets và kiểm soát thời điểm retrain.

## 9. Những kỹ thuật thống kê dùng cho behavioral alert

Các kỹ thuật sau **không tự chứng minh bất thường là malicious**. Chúng chỉ giúp mô tả **độ lệch khỏi một mô hình**. Lựa chọn phụ thuộc phân phối dữ liệu, chu kỳ thời gian, mức sampling và nhu cầu giải thích.

### 9.1. Mean và standard deviation / z-score

Với các mẫu baseline \(x_1,\ldots,x_n\):

\[
\mu = \frac{1}{n}\sum_{i=1}^{n}x_i,\qquad
\sigma=\sqrt{\frac{1}{n}\sum_{i=1}^{n}(x_i-\mu)^2}
\]

Z-score cho mẫu mới:

\[
z=\frac{x-\mu}{\sigma}
\]

Nếu baseline là số DNS queries/s trong các giờ cùng loại, z-score lớn có thể báo **cao hơn kỳ vọng**. Nhưng **\(\sigma=0\)** cần xử lý riêng, và **heavy-tailed traffic, bursty events, low counts, correlated samples** khiến giả định gần chuẩn không phù hợp. Đừng gọi “z>3” là xác suất bị tấn công 99,7%.

### 9.2. Median, MAD và robust deviation

Nếu vài outlier làm mean/sigma bị kéo lệch, dùng:

\[
m=\mathrm{median}(x),\qquad
\mathrm{MAD}=\mathrm{median}(|x_i-m|)
\]

Một dạng robust score khi MAD dương:

\[
z_{\mathrm{robust}}=0.6745\cdot\frac{x-m}{\mathrm{MAD}}
\]

Hệ số 0,6745 là hiệu chỉnh thông dụng cho ước lượng tương ứng phân phối chuẩn, **không làm dữ liệu mạng thành phân phối chuẩn**. Nếu **MAD=0** do phần lớn mẫu bằng nhau, cần policy thay thế: **minimum absolute delta, percentile, count threshold hoặc explicit unknown**, không chia cho 0.

### 9.3. Exponentially Weighted Moving Average (EWMA)

\[
E_t = \alpha x_t + (1-\alpha)E_{t-1},\qquad 0<\alpha\le1
\]

EWMA phản ứng với thay đổi gần đây, trong đó **alpha lớn** làm baseline nhạy nhanh hơn, **alpha nhỏ** làm mượt hơn. Nếu cập nhật EWMA bằng chính traffic tấn công mỗi phút, baseline có thể **đuổi theo tấn công** và alert biến mất. Nên tách **detection window** khỏi **baseline training/update**, chặn retrain trong incident và giữ static hard stops.

### 9.4. Quantiles và time-of-week bands

Với throughput hoặc QPS theo các chu kỳ ổn định, có thể lấy **p95/p99** của cùng giờ/ngày trong nhiều tuần. Ví dụ:

~~~text
Baseline cohort:
  Resolver prod-dns-1, weekday 09:00-10:00,
  non-incident windows, data quality OK.

Expected DNS QPS band:
  median = 240, p95 = 420, p99 = 650 (minh họa)

Candidate detector:
  QPS > 650 for 3 valid windows
  AND NXDOMAIN ratio rising
  AND no approved rollout / DNS migration.
~~~

Một p99 từ chỉ 10 mẫu **không có độ tin cậy tương tự p99 từ hàng nghìn mẫu độc lập**. Lịch sử chứa ngày lễ/campaign có thể không đại diện tuần mới; cần **sample-size guard, missingness check, seasonality segmentation và review baseline**.

### 9.5. Robustness với chuỗi nhiều mùa vụ

Một hệ thống có thể có chu kỳ **theo ngày, tuần, kỳ lương, release và backup**. Cần baseline có điều kiện, phát hiện **change points** và loại windows có deploy/maintenance đã phê duyệt. Không để “ngày cuối tháng lưu lượng cao” trở thành exception miễn mọi cảnh báo: **hard security guardrails và peer/auth failures** vẫn hoạt động.

### 9.6. Những đặc trưng hành vi ngoài volume

| Feature | Cách hiểu | Cần kiểm tra |
| --- | --- | --- |
| Distinct destinations per source per window | Fan-out/lateral movement khả nghi | Service discovery, scanner được phê duyệt |
| Distinct destination ports | Port sweep/connection anomalies | Monitoring, active health probes, IDS context |
| New peer compared with service graph | Service-to-service drift | Deployment, Pod rotation, mesh routing |
| Repeated small flows at regular cadence | Beacon-like behavior | Metrics agents, NTP, scheduled jobs |
| DNS labels unusually long/rare | Có thể đáng triage về DNS tunneling | CDN, DNSSEC, legitimate encoded labels |
| NXDOMAIN ratio spike | Misconfiguration, DGA-like suspicion | Bad deployment, random subdomains cho tracing |
| Egress bytes to rare destinations | Potential data movement | Backup, artifact repository, NAT mapping |
| Failed auth then success | Possible credential abuse | User typo, expired tokens, SSO refresh |
| Source/destination graph connectivity change | Lateral movement or new topology | Service rollout, DR/failover, IP reuse |
| Repeated security policy DENY | Scan/misconfiguration | Allowed scanner, rule updates, connectivity test |

**Một “rare destination” có thể là legitimate CDN edge hoặc một server mới**. Behavioral features cần **resource criticality, authenticated identity và business context**, không phải auto-block dựa trên rarity.

## 10. Mùa vụ, concept drift và poisoning baseline

### 10.1. Seasonality và business change

Một job backup chạy **02:00 mỗi Chủ nhật** có thể truyền 500 GB tới storage đã phê duyệt. Baseline “lưu lượng rạng sáng thấp” không có lịch job sẽ báo exfil mỗi tuần. Giải pháp không chỉ là tắt detector Chủ nhật, mà:

- Baseline **riêng job/service identity**, destination class, data volume và scheduled window.
- Đối chiếu **change calendar và approved backup plan**.
- Vẫn alert nếu **đích lạ, service identity khác, job ngoài schedule hoặc bytes bất thường hơn peer history**.
- Theo dõi **SLO và DLP/object access logs** để không nhầm bytes mạng với tài liệu nhạy cảm đã rời tổ chức.

### 10.2. Concept drift

Một API vốn dùng một database nay chuyển sang gọi hàng chục shards. Detector fan-out có thể báo “lateral movement” dù migration hợp lệ. Cần:

1. Theo dõi **drift signal** và rollout event.
2. Đối chiếu **service dependency graph và policy-as-code**.
3. Tái huấn luyện baseline từ **vùng dữ liệu đã được đánh giá hợp lệ**.
4. Giữ lại **old baseline và lý do đổi** để audit.
5. Test detector không bỏ sót **unauthorized new destinations** sau khi số peer hợp lệ tăng.

### 10.3. Baseline poisoning

Nếu attacker tăng exfil từ từ mỗi ngày, mô hình học theo traffic gần nhất có thể coi mức mới là bình thường. Biện pháp:

- **Không retrain khi có open incidents hoặc unexplained deviations**.
- Dùng **slow/frozen reference baseline** cho các luồng nhạy cảm.
- Đặt **hard policy checks**: unapproved destination, restricted protocol, unauthorized source vẫn DENY/alert.
- So sánh với **trusted peer group** và **business-approved communication graph**.
- Có **human review/reproducible model version** trước khi đẩy adaptive rule lên Production.

### 10.4. Peer-group anomaly cần so sánh đúng nhóm

So VM database với toàn bộ VM trong cùng VPC có thể vô nghĩa. Peer group nên có **cùng ứng dụng, role, tier, region, instance size và time window** ở mức hợp lý. Một Pod xử lý nhiều customer requests có thể có traffic cao hơn replicas khác do **sticky sessions/sharding**, không nhất thiết compromised.

## 11. State machine alert: duration, cooldown, suppression và recovery

Một detector lý tưởng không phát lại mỗi phút khi cùng incident kéo dài. Nó nên có trạng thái **NORMAL, PENDING, FIRING, ACKNOWLEDGED, SUPPRESSED, RECOVERING, RESOLVED và NO_DATA** tùy hệ thống.

~~~mermaid
flowchart TD
    N["NORMAL"] -->|"Condition first true"| P["PENDING"]
    P -->|"M of N valid windows"| F["FIRING"]
    P -->|"Condition false"| N
    F -->|"SOC acknowledged"| A["ACKNOWLEDGED"]
    F -->|"Matched approved maintenance"| S["SUPPRESSED"]
    A -->|"Clear threshold for required duration"| R["RECOVERING"]
    S -->|"Maintenance expires / alert still true"| F
    F -->|"Clear threshold"| R
    R -->|"Stable clear"| Z["RESOLVED"]
    R -->|"Condition returns"| F
    Z --> N
    N -->|"Telemetry stale"| D["NO_DATA"]
    F -->|"Telemetry stale"| D
    D -->|"Data restored"| P
~~~

### 11.1. M-of-N evaluation

Một rule “3 trong 5 phút” phải định nghĩa rõ **3 distinct valid 1-minute buckets** hay **3 evaluations of sliding 5-minute windows**. Hai cách khác nhau. Nếu 2/5 buckets **NO_DATA**, có nên coi 3/3 còn lại là “3-of-5”? Quy tắc phải xử lý missingness rõ, không âm thầm xem missing là 0 hay true.

### 11.2. Cooldown và dedup key

Một alert thường nên có fingerprint dựa trên:

~~~text
detector_id + detector_version + environment
+ source asset/workload identity + destination class
+ relevant protocol/service + incident scope
~~~

**Không dùng timestamp mỗi event trong fingerprint** nếu muốn group cùng một episode; cũng không dùng fingerprint quá rộng như “network-anomaly-prod” khiến port scan trên bastion và DDoS trên ingress bị trộn. Dedupe phải giữ **first_seen, last_seen, max observed, count và sample evidence**.

### 11.3. Silence và maintenance là ngoại lệ có hạn

Trong một đợt load test, có thể **suppress alert về throughput capacity** cho đúng service/time/owner, nhưng không tự im lặng **unauthorized management access, malware hit hoặc logging outage**. Một suppression cần có **ticket, approver, expiry, affected rule/resource và audit**; không đặt blanket silence mọi alert của Production.

### 11.4. Escalation và auto-close

Alert chưa được ACK trong một thời gian phù hợp có thể nâng mức tới **on-call khác**. Tuy nhiên auto-close chỉ vì metric thấp trở lại sau khi collector mất không phải recovery. Với incident an ninh, cần **confirmed remediation, no-data status và owner sign-off** trước khi đóng.

## 12. Dữ liệu từ từng thiết bị mạng và ứng dụng

| Nguồn telemetry | Các chỉ số/event thường hữu ích | Lỗi suy diễn cần tránh |
| --- | --- | --- |
| **Router/switch SNMP/streaming telemetry** | Interface octets, errors, drops, link state, utilization, BGP adjacency | Link up không chứng minh app reachable |
| **Firewall/NGFW** | Rule action, connection/session counts, drops, threat signatures, NAT state | ACCEPT ở firewall không đồng nghĩa HTTP success |
| **IDS/IPS** | Signature/severity, detection action, drops, sensor health | Signature hit không tự là compromise confirmed |
| **NetFlow/IPFIX/sFlow** | Source/dst/protocol/ports, bytes/packets, sampled traffic | Sampled flow không là số TCP sessions chính xác |
| **Cloud VPC/VNet flow logs** | Per-source/ENI/network flow metadata, ACCEPT/REJECT theo provider | Không phải PCAP, source/dst pre/post NAT có thể khác |
| **DNS resolver** | QPS, NXDOMAIN, query classes/names, per-client baseline | Một IP CDN không ánh xạ duy nhất tới domain |
| **VPN/ZTNA/SSO** | Login success/fail, session duration, posture, auth method, revoke | Có tunnel không nghĩa mọi API action hợp lệ |
| **TLS/PKI/service mesh** | Handshake failures, cert expiry, mTLS principal, peer denies | Valid mTLS không cấp object/tenant authorization |
| **Load balancer/API gateway/WAF** | RPS, latency, 4xx/5xx, blocked rules, upstream errors | 503 có thể được gateway sinh trước backend |
| **Kubernetes CNI/eBPF** | Pod flow, policy denies, socket/process metadata theo agent | Pod IP có thể đổi và bị tái sử dụng |
| **Endpoint/EDR** | Process, security alerts, device health, network connections | Process detection khác với mọi packet thực đi |
| **Application/cloud audit** | User/action/resource, IAM/config changes, business outcome | App logs không bao phủ packets bị chặn trước app |

### 12.1. Đừng trộn action semantics của các nguồn

**Firewall DROP, IDS DETECT, IPS BLOCK, WAF CHALLENGE, DNS NXDOMAIN, VPN AUTH_DENY và VPC Flow Logs REJECT** không có nghĩa giống nhau. Một pipeline chuẩn hóa có thể dùng field chung **outcome_category**, nhưng vẫn phải giữ **source_action, source_product, rule_id, observation_point và evidence_version**. Nếu ép mọi thứ thành “deny=1”, rule tổng hợp có thể kết luận sai về tác động.

### 12.2. Hãy lưu resource identity theo thời điểm

NAT gateway dùng một public IP cho nhiều Pods; VM/Pod IP bị tái sử dụng. Muốn alert “workload Orders liên hệ IP lạ”, cần **historical IP assignment/Pod UID, interface/resource ID, account/VPC/time window và NAT mapping**, không chỉ join vào inventory hiện tại.

### 12.3. Multi-hop và double-count

Một connection đi qua source NIC, gateway và destination NIC có thể được ghi **ba lần**. Nếu cộng bytes trên mọi điểm mà không chọn **accounting boundary** sẽ thổi phồng lưu lượng. Nếu muốn xác minh đường đi, ghi các observations riêng; nếu muốn tính usage tổng, chọn **một nguồn/điểm đo xác định** và ghi phương pháp.

## 13. Thiết kế phát hiện quét cổng và lateral movement

**Port scan/host sweep** có thể tạo nhiều connection attempts tới nhiều ports/hosts với tỷ lệ bị chặn cao; **lateral movement** có thể xuất hiện như service mới truy cập nhiều endpoints nội bộ, dùng giao thức quản trị không thuộc graph hợp lệ. Nhưng monitoring, vulnerability scans, deploy và service discovery cũng có thể tạo mẫu tương tự.

### 13.1. Detector nhiều đặc trưng

~~~text
Entity:
  Source workload identity/Pod UID + network scope + time window

Window:
  10 minutes of valid, sufficiently complete flow records

Candidate signals:
  distinct_destination_ips >= 20
  AND distinct_destination_ports >= 8
  AND rejected_attempts >= 50
  AND new_destination_ratio > 0.8

Context:
  Not an approved scanner, not an expected deployment/maintenance
  Source is not a service discovery/health-check infrastructure host

Result:
  "Suspected network reconnaissance" with evidence and confidence
  Do not automatically label "compromised" or block a broad CIDR.
~~~

Tất cả số là **giá trị minh họa để thiết kế**, phải tune với mạng và sampling của tổ chức. Một attacker quét rất chậm có thể **không vượt threshold trong 10 phút**, nên có thể thêm **longer horizon/day-level unique target count** với yêu cầu storage/cost phù hợp.

### 13.2. Mẫu “scan chậm”

Một tài khoản chỉ thử **một port lạ mỗi giờ** trên 20 servers trong 20 giờ. Rate/volume threshold 10 phút bỏ sót; detector behavior có thể nhận **dịch vụ/peer mới**, **sequence over 24h** và **không nằm trong allowlisted service graph**. Nhưng phải xem account/identity có phải **vulnerability scanner hoặc SRE được phê duyệt** không.

### 13.3. Khi nào nên nâng severity?

Severity cao hơn khi đồng thời có **unauthorized admin protocol to critical subnet, successful authentication after repeated failures, EDR suspicious process và previously unseen peer relationships**. Một cuộc quét đã bị firewall DENY hoàn toàn vẫn cần quan sát nhưng **không cùng mức tác động** với kết nối quản trị trái phép đã thành công.

### 13.4. Không tự lấy port làm chứng cứ nghiệp vụ

Traffic TCP/443 có thể là HTTPS, gRPC hoặc protocol tùy ứng dụng; TCP/22 có thể được port-forward một cách hợp pháp; connection tới port database không chứng minh đã đọc database. Cần **app/auth logs, endpoint identity và network ownership**.

## 14. DDoS và saturation: phân biệt tải lớn với tấn công

DDoS detection thường cần **đa nguồn telemetry**: PPS/BPS, new connections/s, SYN state, L4 drops, upstream latency, CDN/WAF challenge, application error rate và user-facing SLI. Một metric traffic cao riêng lẻ không đủ để kết luận tấn công.

### 14.1. Ví dụ logic multi-signal

~~~text
IF inbound_pps > threshold_for_edge
AND SYN_incomplete_ratio > 0.6 with sample_count >= 1000
AND upstream_connection_failures rising
FOR 3 valid windows
THEN "Possible L4 resource exhaustion"

Escalate if:
  application SLO breached or edge mitigation confirms attack.
~~~

Đây là **pseudocode**; các giá trị không là cấu hình production. SYN ratio còn phụ thuộc **protocol, SYN cookies, sensor visibility, asymmetric routing, NAT và client mix**. Với UDP floods không dùng SYN ratio; cần feature tương ứng.

### 14.2. Baseline có business context

Một product launch có thể làm requests/s tăng nhiều lần nhưng **latency, error rate và firewall drops vẫn ổn**. Một flood nhắm port hiếm có thể làm **link saturation** mà application RPS không tăng. Bởi vậy kết hợp **ingress edge/network capacity + app/service metrics + mitigation telemetry**.

### 14.3. Ứng phó tự động cần guardrails

Các hành động như **rate limit, bot challenge, traffic scrubbing, route change hoặc IP block** có thể gây gián đoạn khách hàng. Chỉ tự động hóa khi detector có đủ **confidence, giới hạn action scope, approval policy, rollback và monitoring false positives**. Không dùng một IP shared CDN làm mục tiêu block toàn diện chỉ vì có requests lạ.

## 15. DNS tunneling, DGA-like symptoms và phân tích hành vi DNS

DNS được dùng cho name resolution nhưng cũng có thể bị lạm dụng để truyền metadata/dữ liệu theo truy vấn hoặc beacon. **Chỉ từ QPS/NXDOMAIN/độ dài hostname, không thể khẳng định DNS tunneling** vì nhiều hệ thống dùng encoded labels hợp lệ.

### 15.1. Đặc trưng hữu ích

| Feature | Có thể gợi ý | False positives phổ biến |
| --- | --- | --- |
| Truy vấn tới nhiều subdomain chưa thấy | DGA-like patterns hoặc exfil through labels | Tracking, service discovery, telemetry IDs |
| Label dài/entropy cao | Encoded data trong QNAME | CDN/cache key, cryptographic identifiers hợp lệ |
| NXDOMAIN ratio cao | DGA, misconfigured app hoặc typo | Deployment bug, search domains, resolver outage |
| TXT queries tăng | Kênh dữ liệu ngoài thông thường | SPF/DKIM/verification/service config |
| Query rate đều với khoảng cách nhỏ | Beacon-like | Monitoring, health checks, SDK polling |
| Truy vấn tới resolver lạ | DNS egress policy bypass, DoH/DoT | New approved resolver, VPN split DNS |
| DNS answers bất thường | Fast flux/hạ tầng chuyển đổi | CDN, active failover, geo balancing |

### 15.2. Detector có điều kiện

~~~text
Source: DNS resolver logs that preserve authenticated client or host
Entity: client_workload + queried_domain_suffix
Window: 15 min, good-quality records
Signals:
  many unique subdomains under a newly seen suffix
  AND long labels/high estimated entropy versus workload baseline
  AND unusual DNS query types or NXDOMAIN ratio
Risk context:
  source is sensitive asset, destination unknown,
  no approved vendor/monitoring purpose
Follow-up:
  Correlate DNS responses, egress flows, endpoint process,
  proxy logs and actual data classification.
~~~

**Đừng tự phát truy vấn DNS có nội dung thật nhạy cảm để test detector.** Dùng dữ liệu tổng hợp hoặc lab domain được cấp phép. Với **DNS over HTTPS/TLS**, resolver log ở doanh nghiệp có thể không thấy nội dung truy vấn; cần endpoint/approved proxy/egress visibility và tuân thủ privacy.

### 15.3. Vai trò của entropy

Shannon entropy \(H(X)=-\sum_i p_i\log_2 p_i\) có thể giúp mô tả phân bố ký tự trong một tập label, nhưng **entropy cao không chứng minh mã hóa hay ý đồ xấu**. Độ dài chuỗi, bảng chữ cái, tên domain sinh động, punycode, random IDs hợp lệ và số lượng mẫu ảnh hưởng mạnh; cần calibrated baseline và evidence bổ sung.

## 16. Data exfiltration hypotheses: byte volume không đủ

Exfiltration là nghi vấn **dữ liệu vượt trust boundary trái phép**. Flow logs ghi metadata/IP/port/bytes ở một điểm, còn **DLP, object storage logs, proxy/application audit và EDR** mới giúp xác định dữ liệu/quyền/đích và kết quả thực.

### 16.1. Các mẫu bất thường đáng xét

- Workload Production bình thường chỉ gọi một cloud storage endpoint được phê duyệt nay **egress tới external IP mới**.
- **Outbound bytes** tăng nhiều lần ngoài lịch backup, không tương quan với workload RPS.
- Các phiên TCP/443 hoặc QUIC kéo dài tới **ASN/region mới** so với allowlisted service graph.
- Tạo nhiều DNS queries tới domain hiếm, cùng **outbound HTTPS** tăng từ process lạ.
- IAM/object storage audit cho thấy **read/list/download trên dữ liệu nhạy cảm** trước spike egress.
- DLP/endpoint telemetry báo có **archive/compression process, unusual bulk reads** trên máy nguồn.

### 16.2. Rule minh họa kết hợp

~~~text
Candidate:
  outbound_observed_bytes > workload_time_of_week_p99
  AND destination_not_in_approved_peer_graph
  AND unique_external_destinations > typical_workload_baseline

Corroboration:
  cloud storage object reads / DB exports,
  endpoint process/command, DNS/proxy identity,
  remote ownership and data classification

Alert title:
  "Unusual outbound data movement - investigate"

NOT:
  "Confirmed data theft"
~~~

Trong môi trường NAT dùng chung public IP, phải **map pre/post NAT tuples theo timestamp và port** trước khi quy trách nhiệm một workload. Nếu logs sampled, báo **observed/estimated bytes** theo semantics nguồn; không lấy tổng ở nhiều NIC làm số dữ liệu thực bị lấy.

### 16.3. Slow exfil và baseline drift

Một transfer vài MB/phút từ tài sản nhạy cảm tới đích lạ kéo dài nhiều ngày có thể nằm dưới high-byte threshold. Behavioral alerts nên theo **new destination, unusual data-access sequence, cumulative bytes per destination over longer horizon và departure from approved data flow**. Không được vì baseline tăng dần mà tự hợp pháp hóa đường gửi data chưa được chấp thuận.

### 16.4. Trong môi trường TLS/IPsec

TLS và VPN che nội dung payload ở những điểm quan sát nhất định. **ESP outer flow** chỉ biểu diễn gateway/tunnel, không cho biết inner API URLs. Nếu proxy terminate TLS hợp pháp, application access logs có thể cung cấp context. Cần định rõ **privacy, legal basis, data minimization và where plaintext is available**, không thu thập bí mật hoặc cố giải mã traffic ngoài quyền.

## 17. VPN, ZTNA, TLS và xác thực: phát hiện chuỗi bất thường

### 17.1. Repeated failures và credential stuffing symptoms

~~~text
Entity: account + app + source-device/session context
Window: 10 minutes
Signals:
  failed_login_count high relative to that account/app baseline
  AND distinct user accounts targeted by same origin may be high
  AND successful login to sensitive resource later (optional)
Correlate:
  IdP risk, MFA method, device posture, known VPN proxies,
  app authorization and approved load test.
~~~

**Một IP NAT shared** có thể đại diện nhiều users, nên “100 failed logins cùng IP” không tự là một actor. Ngược lại attacker phân tán trên nhiều IP có thể **low-rate per-IP** nhưng high-rate **per target account**. Detector nên theo **user/device/session/ASN/network risk** và kiểm soát user privacy.

### 17.2. VPN tunnel flap và routing anomalies

Alert theo ngưỡng có thể dùng **tunnel_up=0**, **SA rekey failures**, **BGP adjacency down** hoặc **packet loss**. Behavioral detection có thể thấy **frequent tunnel reset, unusual route churn hoặc traffic switching between regions**. Điều tra cần **IKE/IPsec logs, BGP/control-plane, tunnel counters, MTU/PMTU và app latency**, không kết luận attacker vì một lần rekey thất bại.

### 17.3. Certificate/handshake anomalies

Một đợt mTLS cert rotation có thể gây **handshake failures tăng** khi trust bundle chưa hội tụ. Một số lỗi auth cũng có thể do **unknown peer identity**. Detector cần phân biệt:

- **Expired certificate**, **unknown CA**, **hostname/SPIFFE ID mismatch**.
- **TLS protocol/cipher incompatibility** khi upgrade.
- **Clock skew** với notBefore/notAfter.
- **Peer authorization DENY** sau handshake hợp lệ.
- **Network timeout** trước khi TLS handshake.

Không biến tất cả thành “TLS attack”. Nếu cert chưa được refresh, hành động đúng là **sửa issuance/SDS/app reload theo kế hoạch**, không tắt peer verification.

### 17.4. Lateral movement qua allowed channels

Kẻ tấn công dùng credential hợp lệ có thể gọi API qua TCP/443/mTLS, nên **low-level firewall ACCEPT** không chứng minh request hợp lệ. Phát hiện hành vi nên xét **workload identity, new service edges, unusual methods, privileged operation sequence, resource access và auth/session anomalies** kết hợp network telemetry.

## 18. Alert pipeline: chuẩn hóa, enrichment, detection và routing

~~~mermaid
flowchart TB
    N["Network / cloud / app sources"] --> IN["Ingest with source ID, event time"]
    IN --> QA{"Schema, sampling, coverage OK?"}
    QA -->|"Không"| DQ["Data quality alert + mark degraded"]
    QA -->|"Có"| E["Enrich asset, identity, owner, topology"]
    E --> R["Threshold + behavior detectors"]
    R --> C["Correlation, dedupe, confidence"]
    C --> S["Severity + ticket/pager routing"]
    S --> T["SOC triage, evidence, response"]
    T --> F["Feedback: label + tune + canary"]
    F -. "Rule/model version changes" .-> R
~~~

### 18.1. Chuẩn hóa mà không mất thông tin gốc

Một record normalized nên giữ:

~~~json
{
  "event_start_utc": "2026-11-28T04:00:00Z",
  "event_end_utc": "2026-11-28T04:01:00Z",
  "ingested_at_utc": "2026-11-28T04:01:20Z",
  "source_system": "example-firewall",
  "schema_version": "example-v2",
  "account": "acct-example",
  "environment": "prod",
  "resource_id": "fw-ingress-01",
  "observation_point": "edge-firewall",
  "source_ip": "192.0.2.25",
  "destination_ip": "10.20.0.15",
  "destination_port": 443,
  "protocol": 6,
  "source_action": "DENY_BY_RULE",
  "normalized_outcome": "DENIED",
  "rule_id": "policy-allowlist-17",
  "packets_observed": 5,
  "quality": "COMPLETE_FOR_SOURCE_SCOPE",
  "sampled": false
}
~~~

Đây là **schema giả lập**, không phải cấu trúc chính thức của bất kỳ vendor nào. Trường **quality** không nên tự nhận “COMPLETE” nếu nguồn logging không chứng minh được coverage; và source IP thuộc **TEST-NET** chỉ dùng minh họa.

### 18.2. Enrichment là join theo thời gian

Khi một Pod IP 10.20.0.15 được tái sử dụng, join với **current inventory** có thể gán traffic quá khứ cho Pod khác. Dùng **Pod UID, ServiceAccount, ENI/interface ID, account/VPC, historical IP allocation và validity interval**. NAT/proxy cần **translation/request ID**; DNS IP→domain chỉ là giả thuyết nếu CDN/shared hosts.

### 18.3. Route theo ownership và severity

| Alert class | Người xử lý đầu | Hành động ban đầu |
| --- | --- | --- |
| Edge saturation / packet drops | NOC/Network SRE | Kiểm tra link/QoS/scrubbing, app SLO |
| Repeated privileged access from unknown identity | SOC + IAM | Xác thực principal/session, account protection |
| Suspected internal scanning | SOC + Platform | Asset/service discovery, approved scanner check |
| Unexpected egress / sensitive data movement | SOC + Data owner | Tương quan DLP/app/EDR, đánh giá risk |
| DNS query anomalies | DNS/network + SOC | Xem resolver/client/process và baseline |
| Certificate expiry / handshake failures | PKI/Platform | Verify cert/CA rotation, avoid insecure bypass |
| Flow log collector outage | Observability Platform + SOC | Khôi phục telemetry, ghi blind spots |

### 18.4. Một alert không nên bắt đầu bằng dữ liệu bí mật

Không gửi **raw JWT, cookies, PII, private IP map toàn tổ chức, full DNS query payload có thể chứa thông tin nhạy cảm hoặc decrypted packet body** tới pager/Slack/ticket công khai. Alert nên có **metadata đủ triage, evidence link được RBAC, redaction và retention**.

## 19. Correlation và giảm alert fatigue

Một tấn công hoặc sự cố có thể tạo 300 alerts: WAF blocks, IDS signatures, firewall DENY, egress anomaly, TCP resets, application 5xx. Nếu SOC phải mở từng thông báo độc lập, **signal-to-noise ratio** giảm nghiêm trọng.

### 19.1. Alert grouping không phải bỏ bằng chứng

Nhóm theo **incident hypothesis**:

~~~text
CASE: Suspected credential abuse from source cohort
Timeline:
  04:01 failed SSO logins rising
  04:03 VPN authentication success for one identity
  04:05 new admin connections to 3 internal servers
  04:07 EDR suspicious process alert

Evidence:
  source event refs, principal, device,
  src/dest traffic observations, policy decisions,
  confidence and remaining unknowns.
~~~

Không kết luận chuỗi này là cùng actor nếu chỉ có **shared IP/NAT**; cần identity/session/connection mapping và event-time correlation.

### 19.2. Dedupe, correlation, suppression, inhibition

| Cơ chế | Ví dụ | Rủi ro khi lạm dụng |
| --- | --- | --- |
| **Dedupe** | Một rule firing lặp lại từ same asset/window → một ongoing alert | Group rộng làm mất alert khác cần xử lý |
| **Correlation** | Firewall DENY + EDR + auth success → một hypothesis | Ghép sai actors do IP reuse/shared NAT |
| **Suppression/silence** | Approved load test 30 phút → giảm capacity warning | Che threat alert khác không thuộc scope |
| **Inhibition** | Link down parent alert → suppress downstream no-traffic noise | Parent alert sai làm che outage độc lập |
| **Cooldown** | Sau một firing, giới hạn thời gian phát lại | Bỏ sót episode mới trong cùng cooldown |
| **Escalation** | Một alert critical chưa ACK → pager cấp cao hơn | Escalate sai nhóm/ngoài ca trực |
| **Auto-resolution** | Metric dưới clear threshold ổn định | Data loss bị nhầm recovery |

### 19.3. Alert budget và priority queue

Tổ chức nên đo **alerts per engineer shift, actionable proportion, median time to triage và repeated noise sources**. Không nên đặt mục tiêu “0 alerts” bằng cách tắt tất cả rules. **Rare high-severity events** như unauthorized privileged action có thể cần alert ngay dù chỉ một event; **high-volume low-confidence anomalies** có thể triage theo batch/case.

### 19.4. Parent-child topology

Khi upstream provider link down, hàng trăm services sẽ lỗi DNS/HTTP. Correlation theo **dependency graph** có thể tạo một **parent incident**; nhưng vẫn phải giữ **child evidence** nếu có một security alert độc lập. Không để “network outage” im lặng những dấu hiệu **active compromise** chỉ vì cùng timestamp.

## 20. Severity, confidence, impact và thứ tự ưu tiên

**Severity** không nên chỉ bằng **giá trị metric vượt ngưỡng bao nhiêu**. Ví dụ 1.000 blocked scans tới cổng public không nhất thiết nghiêm trọng hơn một **successful privileged login trái quyền**.

### 20.1. Ba trục đánh giá

1. **Detection confidence:** Rule/model có bao nhiêu bằng chứng và chất lượng dữ liệu ra sao?
2. **Business/security impact:** Resource criticality, dữ liệu, blast radius, thành công thất bại.
3. **Urgency:** Ongoing/confirmed exploitation, SLO breach, time-sensitive containment.

| Tình huống | Confidence / impact | Hướng xử lý |
| --- | --- | --- |
| Một TCP/22 REJECT tới bastion | Thấp đến vừa / chưa có impact | Group, ghi nhận, triage khi pattern tăng |
| 50.000 DENY cùng nguồn do approved scan | High observation / benign context | Tuning theo scope, vẫn giữ evidence |
| Verified identity compromise + successful admin action | Cao / có thể cao | Incident response ưu tiên, containment |
| Egress bytes lớn tới approved backup | High observation / có thể hợp lệ | Check job ticket, no auto compromise label |
| DNS entropy cao nhưng không có process context | Thấp / chưa biết | Enrich/process and domain investigation |
| VPC flow ingestion mất toàn region | Cao về thiếu dữ liệu / visibility nghiêm trọng | Data-quality incident, giảm confidence các detections |

### 20.2. Rule risk scoring là công cụ xếp hàng, không phải quyền block

Một score có thể dùng **asset sensitivity × confidence × observed impact**, nhưng công thức nhân đơn giản có thể gặp các tình huống phi tuyến hoặc missing data. Cần **explainable category, rule owner, override review, audit**; tránh cho model được quyền **block một tenant/CIDR rộng** chỉ vì tổng score vượt một số.

### 20.3. Phân biệt triage và incident declaration

Alert “possible port sweep” bắt đầu ở **hypothesis**. Sau khi kiểm tra source có phải authorized vulnerability scanner, policy match, EDR và user/owner, SOC mới kết luận **benign, misconfiguration, policy violation, suspicious unresolved hoặc confirmed incident** theo tiêu chí nội bộ. Không tô nhãn “attack confirmed” chỉ để làm dashboard đẹp.

## 21. Ví dụ truy vấn: metric alerts và hành vi từ flow records

Các truy vấn bên dưới là **minh họa có điều kiện**, không chạy trong bài STEP 4. Tên metrics/table do ví dụ tự đặt; khi triển khai cần đối chiếu exporter, schema và query engine thực tế.

### 21.1. PromQL — rate counter và capacity alert

Giả định:

- **network_interface_transmit_bytes_total** là counter mỗi interface, đã được exporter định nghĩa rõ.
- **interface_capacity_bits_per_second** là gauge đúng với interface và hướng đang xét.
- Labels **instance/interface** xác định duy nhất interface trong môi trường đã chọn.

~~~promql
# Minh họa ý tưởng cho bộ lọc interface đã biết capacity.
(
  rate(network_interface_transmit_bytes_total[5m]) * 8
  /
  interface_capacity_bits_per_second
) > 0.85
~~~

Trong rule engine có thể đặt **for: 5m** nếu metric sampling và SLO phù hợp. Phải xử lý **missing capacity, zero capacity, counter resets, interface rename, link changes và label matching**. Nếu exporter có multiple labels hoặc metrics không cùng cardinality, cần xác minh vector matching thay vì copy nguyên.

### 21.2. PromQL — DNS error ratio với sample guard

~~~promql
(
  sum by (resolver) (rate(dns_responses_total{rcode="NXDOMAIN"}[5m]))
  /
  sum by (resolver) (rate(dns_responses_total[5m]))
) > 0.4
and on (resolver)
sum by (resolver) (increase(dns_responses_total[5m])) >= 100
~~~

Đây là **cú pháp ví dụ nếu exporter cấp chính xác các metric/labels giả định**. Phải kiểm tra denominator bằng 0, sampling, duplicate, label alignment, response codes và error handling. Một deployment mới với domain search suffix sai có thể gây NXDOMAIN spike hợp lệ nhưng cần khắc phục, không tự gọi DNS tunneling.

### 21.3. Pseudocode SQL — fan-out/internal scan

~~~sql
-- PSEUDOCODE: normalized_flows là bảng minh họa.
-- Dùng event time, asset identity tại thời điểm và quality.
SELECT
  source_workload_id,
  COUNT(DISTINCT destination_ip) AS distinct_hosts,
  COUNT(DISTINCT destination_port) AS distinct_ports,
  SUM(CASE WHEN normalized_action = 'DENIED' THEN 1 ELSE 0 END)
    AS denied_records
FROM normalized_flows
WHERE event_start_utc >= TIMESTAMP '2026-11-28 03:00:00'
  AND event_start_utc <  TIMESTAMP '2026-11-28 03:10:00'
  AND environment = 'prod'
  AND destination_zone = 'internal'
  AND log_quality = 'VALID'
GROUP BY source_workload_id
HAVING COUNT(DISTINCT destination_ip) >= 20
   AND COUNT(DISTINCT destination_port) >= 8;
~~~

**Số denied_records không phải số packets bị drop hoặc attempts chính xác** nếu log là aggregated/sample flow records. Nếu dùng SQL thông thường, những flow bắt đầu trước cửa sổ nhưng overlap vào cửa sổ có thể cần **event_end_utc >= window_start** thay vì chỉ lọc start; tùy semantics record.

### 21.4. Pseudocode SQL — new peer trong service graph

~~~sql
-- Conceptual join, không phải mã trực tiếp cho mọi SQL engine.
SELECT
  f.source_workload_id,
  f.destination_workload_id,
  SUM(f.bytes_observed) AS bytes_observed
FROM normalized_flows f
LEFT JOIN approved_service_edges e
  ON f.source_workload_id = e.source_workload_id
 AND f.destination_workload_id = e.destination_workload_id
 AND f.event_start_utc >= e.valid_from_utc
 AND f.event_start_utc <  e.valid_until_utc
WHERE f.environment = 'prod'
  AND e.source_workload_id IS NULL
GROUP BY f.source_workload_id, f.destination_workload_id;
~~~

**Không mặc định new peer = malicious**. Kiểm tra rollout, temporary job, DR routing, CNI identity mapping và asset ownership; với network NAT/proxy cần mapping đúng trước khi join.

### 21.5. Query results phải kèm điều kiện nguồn

Mỗi dashboard hoặc query dùng cho incident nên hiển thị: **time window/timezone, source coverage, filters, record quality, sampling mode, ingestion lag, schema/parser version và số lượng samples**. Một bảng “Top 10 suspicious IPs” thiếu context có thể dẫn tới chặn nhầm CDN/provider IP.

## 22. Đánh giá detector bằng bằng chứng, không chỉ số lượng alerts

Một rule phát hiện nhiều alerts **chưa chắc tốt**. Nếu tất cả đều false positive, nó làm SOC mất thời gian và có thể khiến người vận hành bỏ qua alert thật. Nếu quá ít alerts vì threshold quá cao, có thể detector **bỏ sót các tình huống quan trọng**.

### 22.1. Ma trận confusion

| | Sự kiện đáng phát hiện thực sự | Sự kiện không đáng phát hiện |
| --- | --- | --- |
| **Detector báo** | **TP** — true positive | **FP** — false positive |
| **Detector không báo** | **FN** — false negative | **TN** — true negative |

Những định nghĩa này chỉ có ý nghĩa khi có **ground truth/label policy**. Trong an ninh mạng, ground truth thường thiếu; nhiều alerts chỉ được triage chứ không thể xác nhận an toàn/tấn công tuyệt đối. Phải ghi rõ **unknown/unreviewed** thay vì tự gán toàn bộ alerts chưa xử lý là FP.

Các chỉ số:

\[
\mathrm{Precision}=\frac{TP}{TP+FP},\qquad
\mathrm{Recall}=\frac{TP}{TP+FN}
\]

\[
\mathrm{FPR}=\frac{FP}{FP+TN},\qquad
\mathrm{F1} = 2\cdot\frac{\mathrm{Precision}\cdot\mathrm{Recall}}{\mathrm{Precision}+\mathrm{Recall}}
\]

Giả sử trong một tập kiểm thử được **gán nhãn đáng tin** detector có **TP=24, FP=6, FN=8**. Khi đó precision = **24/30 = 80%**, recall = **24/32 = 75%**. Con số chỉ minh họa cho tập đó, **không cam kết production accuracy**. Trên telemetry mạng nhiều triệu events/ngày, một FPR nhỏ vẫn tạo số alerts rất lớn nếu base rate của attack thấp.

### 22.2. Đánh giá event vs incident

Rule tạo 200 alerts cho một đợt DDoS có thể có **event-level recall cao** nhưng không giúp incident triage nếu đều trùng lặp. Cần đo:

- **Incident-level recall:** Có nhận ra những incidents quan trọng trong tập đánh giá không?
- **Actionability/precision:** Bao nhiêu alerts dẫn tới điều tra hữu ích, remediation hoặc kiến thức mới?
- **Time to detect (TTD):** Độ trễ từ sự kiện đến alert đầu tiên đáng tin.
- **Mean time to acknowledge/triage/resolve:** Khả năng vận hành SOC.
- **Duplicate alerts per incident:** Mức nhiễu sau correlation.
- **Missed critical controls:** Những trường hợp unexpected admin success, network bypass hoặc collector outage bị bỏ sót.
- **Availability impact:** False blocks, unnecessary rate limits, repeated MFA challenge nếu có automation.

### 22.3. Test với dữ liệu có nhãn rõ

Nguồn test hữu ích gồm:

1. **Synthetic traffic và log events** trong lab, biết chính xác expected outcome.
2. **Historical incidents** có timeline, labels và chain of evidence.
3. **Approved load tests / scanner schedules** để đo false positives.
4. **Replay offline** dữ liệu đã redaction, có schema/source fidelity.
5. **Negative controls:** Telemetry mất/clock skew/duplicate/late arrivals/IP reuse.
6. **Canary shadow evaluation:** Detector mới đánh giá nhưng không paging/auto-block; so với rule đang chạy.

**Không chạy port scan thật vào hệ thống không được cấp quyền** chỉ để tạo TP. Dữ liệu mô phỏng đủ để kiểm tra logic; lab có quyền mới phù hợp test end-to-end.

### 22.4. Tuning và overfitting

Nếu điều chỉnh threshold sau khi nhìn một tập incident rồi đo accuracy trên **chính tập đó**, kết quả có thể quá lạc quan. Tách **training/tuning windows** khỏi **holdout validation**, đánh giá các ngày/đợt traffic khác, theo environment/region/asset role và kiểm tra drift. Không giả định một “p99 threshold” có độ chính xác tương tự tại tất cả sites.

### 22.5. Cần biết cái gì chưa đo được

Không thể tính FN thực nếu **không có cơ chế biết về các trường hợp bị bỏ sót**. Một dashboard “Detection recall 100%” chỉ vì mọi alert được SOC xác nhận là TP là sai phương pháp; nó chưa có mẫu của **không được cảnh báo**. Sử dụng tabletop/synthetic tests/approved detection validation để ước lượng coverage và ghi bất định.

## 23. Quản trị detector: policy-as-code, ownership và rollout an toàn

Alert rule là **mã/chính sách vận hành**. Một sửa đổi có thể làm ngừng gọi on-call hoặc tạo hàng triệu alerts; cần **owner, review, version, test, canary, change record và rollback**.

### 23.1. Đặc tả rule tối thiểu

~~~yaml
# Schema minh họa, KHÔNG phải manifest của Prometheus/Elastic/Splunk.
detector_id: network-bastion-new-peer
version: 3
owner: soc-detection-engineering
description: New admin target outside allowed service graph
data_sources:
  - normalized_network_flow
  - asset_inventory_history
  - approved_admin_target_registry
scope:
  environment: production
  resource_role: bastion
  protocol: TCP
window:
  duration: 15m
  evaluation_interval: 1m
  event_time_based: true
quality_requirements:
  source_coverage: required
  late_event_grace: 2m
  sampled_data_handling: mark_uncertain
condition:
  new_destination_count: 3
  admin_port_profile: matching_approved_list
baseline:
  profile: bastion-identity-time-of-week
  min_history_days: 21
action:
  emit: suspected_unapproved_admin_connectivity
  auto_block: false
  dedupe_scope: workload_and_destination_class
  triage_runbook: soc-network-new-peer
security:
  evidence_access: restricted
  redact_auth_material: true
~~~

**Đây là một bản đặc tả ý tưởng**, không thể nạp trực tiếp vào một SIEM bất kỳ. Một rule engine thực có cấu trúc, permissions, query language và evaluation behavior riêng. Các giá trị threshold/history cũng là ví dụ cần hiệu chỉnh theo tập dữ liệu hợp lệ.

### 23.2. Thứ tự thay đổi

1. Mô tả **detection objective** và threat hypothesis, không chỉ tên rule.
2. Rà soát **schema/data quality** và nơi collection hoạt động.
3. Xác định **asset scope, sensitivity, business calendar và allowed scanning**.
4. Viết rule có **unit tests/replay tests** trên TP, FP, missing, late và reset cases.
5. Chạy **shadow mode** để đo kết quả mà không phát pager hoặc chặn traffic.
6. Canary một **environment/cohort/region** với ngưỡng có review.
7. Đo **precision/actionability, alert volume, TTD và SLO impact**.
8. Đưa vào production có **owner/runbook/pager routing, version pinning và rollback**.
9. Kiểm tra **post-deploy effective rule + data source coverage**, không chỉ CI PASS.
10. Đánh giá định kỳ **concept drift, new techniques và sensor migrations**.

### 23.3. Detector lifecycle

| Trạng thái | Ý nghĩa |
| --- | --- |
| DRAFT | Có giả thuyết, chưa có bằng chứng hoạt động |
| VALIDATING | Đang test dữ liệu có nhãn và quality |
| SHADOW | Chạy real traffic nhưng không tự paging/block |
| CANARY | Phát alerts cho scope giới hạn |
| ACTIVE | Có owner, runbook, SLO, triage route |
| DEGRADED | Source missing/sampling bất thường hoặc parser lỗi |
| SUSPENDED | Tạm tắt có approval, scope và expiry |
| RETIRED | Không còn use case hoặc được thay thế; phải lưu audit lý do |

**Đừng để những rules đã lỗi thời chạy mãi chỉ vì chưa có người sở hữu**. Một detector có owner đã rời đội, nguồn logs bị đổi nhưng vẫn báo “0 alerts” cần được xem là **coverage gap**, không phải production-ready.

### 23.4. Đo lợi ích thay vì tối ưu số đẹp

Hạ threshold từ 100 xuống 10 có thể tăng **recall trong lab** nhưng tạo quá nhiều false positives trong Prod. Tăng threshold chỉ để có ít alerts có thể làm bỏ sót reconnaissance. Quyết định tuning nên dựa trên **cost of missed detection, analyst capacity, data quality, available controls và approved risk appetite**.

## 24. Security và privacy của pipeline alert

Telemetry mạng có thể chứa **địa chỉ nội bộ, port quản trị, domain truy vấn, traffic volume, user identity, device metadata, IP public đối tác**. Thêm enrichment từ IAM/EDR/DLP làm dữ liệu có thể nhạy cảm hơn bản flow log gốc.

### 24.1. Quy tắc bảo vệ

| Kiểm soát | Mục tiêu |
| --- | --- |
| **Least-privilege ingest** | Collector chỉ nhận/ghi đúng telemetry được phép, không cần quyền sửa firewall |
| **RBAC cho query/evidence** | SOC chỉ truy cập môi trường/case cần; developer không đọc mọi user events |
| **Encryption** | Bảo vệ in transit và at rest, quản lý keys theo hệ thống |
| **Tamper detection** | Audit thay rule, parser, suppression, retention, collector config |
| **Log redaction** | Loại Authorization/Cookie/API keys và dữ liệu khách hàng không cần thiết |
| **Retention/minimization** | Quy định hot/search/archive và xóa theo phân loại dữ liệu |
| **Data residency** | Không chuyển logs qua region/quốc gia trái policy |
| **Export controls** | Chia sẻ evidence qua liên kết truy cập có kiểm soát, không dán thẳng raw logs vào chat |
| **Source integrity** | Authenticate collectors, verify schema/version, monitor replay/duplicates |
| **Secure automation** | Quyền hành động nhỏ nhất, limit/safe rollback, human approval cho phạm vi lớn |

### 24.2. Bảo vệ chính hệ thống alert trước tấn công

Attacker có thể cố **vô hiệu hóa flow logging, thay suppression, tạo nhiễu che alert, poison baseline hoặc dùng compromised account để chỉnh rule**. Cần giám sát độc lập:

- **Rule/alertmanager policy changes**, người thay và thời điểm.
- **Sensor coverage drift, IAM/KMS failures, dropped events và ingestion lag**.
- **Suppression/silence duration**, owner và phạm vi.
- **Baseline retrain/model version**, dataset provenance và approval.
- **Pager routing/receiver changes** khiến alert không đến người trực.
- **Automated block changes** và tác động tới khách hàng.

Một “alert disabled” phải tạo **configuration/audit finding** nếu không có change ticket hợp lệ. Không để cùng một quyền có thể vừa **gây tấn công vừa xóa bằng chứng** mà không có tách trách nhiệm phù hợp.

### 24.3. Hạn chế auto-remediation

Tự động block một IP có thể:

- Chặn **shared proxy/CDN/NAT IP** của nhiều khách hàng.
- Gây outage cho **monitoring, service mesh control plane, DNS, VPN**.
- Làm hệ thống khác tự retry và gây **cascading failure**.
- Phá chain of evidence hoặc làm attacker đổi kỹ thuật, bỏ mất cơ hội xác minh.

Nếu auto-remediation được phê duyệt, cần **scope nhỏ, confidence thresholds, allowlist critical dependencies, TTL, audit, rollback và kill switch**. Với high-stakes như **firewall prod ANY/ANY, cloud routing hoặc tài khoản admin**, yêu cầu người có thẩm quyền theo quy trình.

## 25. Case study A: static threshold bỏ sót scan chậm trên bastion

**Bối cảnh giả định:** Tài sản bastion Production bình thường chỉ SSH tới hai máy quản trị được phê duyệt. Một process lạ mỗi 30 phút thử TCP/22 hoặc 3389 tới một host khác trong subnet. Trong 8 giờ chỉ có 16 flow records; tổng egress <1 MB và nhiều SYN bị REJECT.

### 25.1. Vì sao alert bandwidth không phát?

Threshold edge băng thông 800 Mbit/s và SYN failure ratio window 1 phút **không vượt** vì lưu lượng quá nhỏ/chậm. Tuy nhiên **hành vi giao tiếp** của bastion đã thay đổi:

- **New destination count = 16** so với baseline chỉ 2 approved hosts.
- Giao thức quản trị xuất hiện ở **unauthorized targets**.
- Event sequence trải nhiều giờ, nhiều DENY trên nội mạng.
- Có thể có process/EDR evidence nếu sensor được bật.

### 25.2. Tìm nguồn và tính hợp lệ

| Evidence | Câu hỏi |
| --- | --- |
| CNI/VPC flow logs | Source đúng bastion interface/Pod và time window? |
| Approved admin target inventory | Destination có thuộc planned maintenance không? |
| OS/EDR process events | Process/job nào tạo sockets, chủ thể nào thực thi? |
| IAM/bastion session | Có người dùng/automation được phê duyệt vào thời điểm đó không? |
| Firewall policy | Traffic đã bị chặn hay có accepted admin connection? |
| Change/scan schedule | Có test/scanner được tổ chức cho phép? |

### 25.3. Rule phù hợp hơn

Alert theo **distinct new admin destinations over 24h** và **known service graph**, cộng condition **unapproved source identity**. Không nên auto-block chỉ dựa trên port scan; cần điều tra có thể là **SRE test/monitoring**.

**Bài học:** Behavioral detection có thể phát hiện hoạt động **low-and-slow** mà traffic volume threshold bỏ sót, nhưng cần **asset-specific baseline** và context.

## 26. Case study B: API traffic tăng gấp 8 trong đợt mở bán

**Bối cảnh giả định:** API gateway có baseline 2.000 requests/s vào ngày thường, khi mở bán tăng tới 16.000 requests/s trong 15 phút. Adaptive detector xem đây là anomalous, gửi page security critical mỗi phút. Application SLI vẫn tốt: p95 latency ổn, 5xx thấp, CDN/WAF mitigations không có signal tấn công đáng tin.

### 26.1. Điều cần phân biệt

| Quan sát | Ý nghĩa có thể có |
| --- | --- |
| Request rate tăng 8 lần | Đúng là lệch baseline, chưa phải attack |
| User/session count tăng phù hợp campaign | Có thể giải thích bởi legitimate demand |
| Error/latency và drops vẫn thấp | Chưa có dấu saturation rõ |
| WAF/edge threat score không tăng | Hỗ trợ giả thuyết traffic hợp lệ; không tự chứng minh |
| CDN traffic/geography đa dạng | Có thể phù hợp chiến dịch marketing |
| Backend autoscale đúng plan | Mức load được dự kiến và có khả năng phục vụ |

### 26.2. Cách cải thiện detector

1. Dùng **campaign calendar và business owner**, baseline có điều kiện nhưng không auto-disable mọi security alerts.
2. Tách **capacity alert** (latency, drops, CPU, queue) khỏi **security DDoS hypothesis** (edge signatures, SYN failure, suspicious client patterns).
3. Có **M-of-N, dedupe/cooldown** để tránh page lặp từng phút.
4. Giữ **hard security signals** cho unauthorized admin, TLS failures, malicious WAF signatures hoặc egress anomalies.
5. Sau chiến dịch, đánh giá **false positive, alert volume, missed indicators và threshold changes**.

**Bài học:** **Anomaly so với lịch sử không đồng nghĩa malicious**. Detector nên gắn business context và **thành công/thất bại của ứng dụng**, không chỉ traffic tăng.

## 27. Case study C: DNS anomalies và nguy cơ exfil chưa được xác minh

**Bối cảnh giả định:** DNS resolver logs cho thấy một Pod Production gửi nhiều truy vấn TXT với hostname labels dài tới domain chưa từng thấy. Đồng thời flow logs cho thấy outbound TLS/443 tới một cloud IP mới. SOC tạo alert “suspected data movement”.

### 27.1. Những câu hỏi cần trả lời

1. Pod nào tạo DNS queries? **Pod UID/ServiceAccount/IP historical mapping** có đúng?
2. Domain thuộc **vendor/monitoring agent hợp lệ** hay đích chưa rõ?
3. **DNS queries per minute, query type, NXDOMAIN ratio, label lengths và entropy** khác baseline bao nhiêu?
4. Network flow là **same process/session** hay chỉ cùng Pod NAT/IP? Có proxy/sidecar mapping không?
5. **EDR/process logs, app job, cloud audit, DLP/object storage logs** cho biết có data read/export thực không?
6. Log sources có sampling/ingestion lag hay một event batch hợp lệ?

### 27.2. Phân loại kết luận

**Observation:** Queries TXT và outbound HTTPS bất thường được ghi từ một workload. **Hypothesis:** Có thể DNS abuse hoặc data exfil. **Unverified:** Chưa biết payload, người thực hiện hay dữ liệu đã rời môi trường.

Nếu phát hiện process bất thường, domain không được phê duyệt và sensitive object reads tương quan, nâng severity và điều tra theo incident plan. Nếu là telemetry provider vừa triển khai có ticket/ownership hợp lệ, cập nhật baseline/service graph theo review, không tắt hoàn toàn DNS anomaly rule.

**Bài học:** Một chuỗi nhiều signals đáng điều tra hơn một chỉ số riêng lẻ, nhưng **correlation không tự chứng minh causal link hoặc exfiltration thành công**.

## 28. Case study D: luồng DENY về 0 vì collector mất quyền ghi

**Bối cảnh giả định:** SOC thấy mọi firewall DENY alerts biến mất sau một thay đổi IAM role/KMS key đối với central log sink. Dashboard gọi đây là “thành công của segmentation”. Nhưng application requests/s và interface traffic vẫn bình thường.

### 28.1. Chứng cứ đối chiếu

| Metric | Trước | Sau | Cách hiểu |
| --- | --- | --- | --- |
| Firewall records/s | 2.000 (giả định) | 0 | Bất thường về visibility |
| App requests/s | 4.000 | 4.100 | Traffic còn chạy |
| Network throughput | Bình thường | Bình thường | Không có bằng chứng mạng ngừng |
| Log sink permission errors | 0 | Tăng | Pipeline delivery bị lỗi |
| Cloud audit | Không đổi | IAM/KMS change | Có nguyên nhân khả dĩ cần xác minh |
| NO_DATA alert | Chưa có | Đáng lẽ phải FIRING | Thiếu health rule |

### 28.2. Xử lý phù hợp

1. Khai báo **data-quality incident**, đặt affected detectors thành **DEGRADED/UNKNOWN**.
2. Kiểm tra **collector enabled/coverage, IAM writer permissions, KMS grants, sink quotas và parser errors**.
3. Khôi phục quyền theo **least privilege**, có change ID/approval; không cấp admin toàn bộ.
4. Ghi **blind spot start/end**, rà soát firewall/EDR/app logs còn lại; không cam kết backfill nếu events đã mất.
5. Thêm **synthetic heartbeats, per-source event volume threshold, ingestion lag và alert-routing health**.
6. Sau khi có dữ liệu mới, xác nhận detector hoạt động bằng **authorized synthetic event/replay**.

**Bài học:** **Không có alert không có nghĩa là không có đe dọa**. Một trong các alert quan trọng nhất là cảnh báo **hệ thống phát hiện đã mất khả năng quan sát**.

## 29. Lab Python offline: alert theo ngưỡng, hành vi và trạng thái NO_DATA

Lab này dùng **Python 3.10+**, dữ liệu tổng hợp tự khai báo trong source code, **không đọc file, không mở socket, không quét cổng, không gọi SIEM/cloud API, không thay đổi firewall và không xử lý secrets thật**. Mục tiêu là minh họa cách **đánh giá ngưỡng liên tiếp có hysteresis**, **phát hiện peer mới** và giữ trạng thái **NO_DATA** khi thiếu chất lượng.

### 29.1. Thiết kế

Có hai detector độc lập:

1. **Interface utilization:** cảnh báo khi vượt **85% trong ba bucket hợp lệ liên tiếp**, clear khi xuống dưới **65% trong ba bucket liên tiếp**. Bucket không hợp lệ → **NO_DATA**, không được coi như 0% utilization.
2. **Bastion new peers:** so sánh destinations trong flow records với allowlisted peers của một bastion theo một window; khi có **ít nhất ba destination mới ở ports quản trị** và đủ record chất lượng OK → phát **SUSPECTED_NEW_ADMIN_PEERS** để SOC điều tra. Không kết luận port scan xác định.

**Các ngưỡng chỉ dùng cho lab**, không phải khuyến nghị triển khai nguyên xi trên mạng Production.

### 29.2. Mô phỏng ngưỡng có trạng thái

~~~python
from dataclasses import dataclass
from ipaddress import ip_address


@dataclass(frozen=True)
class UtilBucket:
    event_time: str
    percent: float | None
    quality: str


def threshold_states(
    buckets: list[UtilBucket],
    high: float = 85.0,
    clear: float = 65.0,
    consecutive: int = 3,
) -> list[tuple[str, str]]:
    """Minh họa duration/hysteresis, không có scheduler/network calls."""
    if high <= clear or consecutive < 1:
        raise ValueError("Invalid thresholds")

    state = "NORMAL"
    above_count = 0
    below_count = 0
    output: list[tuple[str, str]] = []

    for bucket in buckets:
        if (
            bucket.quality != "OK"
            or bucket.percent is None
            or not 0 <= bucket.percent <= 100
        ):
            state = "NO_DATA"
            above_count = 0
            below_count = 0
            output.append((bucket.event_time, state))
            continue

        if state == "NO_DATA":
            # Recover visibility, but do NOT claim the previous
            # incident was resolved by its missing data.
            state = "NORMAL"
            above_count = 0
            below_count = 0

        if state == "NORMAL":
            if bucket.percent > high:
                above_count += 1
            else:
                above_count = 0
            if above_count >= consecutive:
                state = "FIRING"
                below_count = 0

        elif state == "FIRING":
            if bucket.percent < clear:
                below_count += 1
            else:
                below_count = 0
            if below_count >= consecutive:
                state = "NORMAL"
                above_count = 0
                below_count = 0

        output.append((bucket.event_time, state))

    return output


utilization = [
    UtilBucket("10:00", 90.0, "OK"),
    UtilBucket("10:01", 91.0, "OK"),
    UtilBucket("10:02", 92.0, "OK"),
    UtilBucket("10:03", 58.0, "OK"),
    UtilBucket("10:04", 61.0, "OK"),
    UtilBucket("10:05", 60.0, "OK"),
    UtilBucket("10:06", None, "COLLECTOR_MISSING"),
    UtilBucket("10:07", 90.0, "OK"),
    UtilBucket("10:08", 92.0, "OK"),
    UtilBucket("10:09", 93.0, "OK"),
]

states = threshold_states(utilization)
for time, state in states:
    print(time, state)

assert states[2][1] == "FIRING"
assert states[5][1] == "NORMAL"
assert states[6][1] == "NO_DATA"
assert states[9][1] == "FIRING"
~~~

Kết quả dự kiến:

~~~text
10:00 NORMAL
10:01 NORMAL
10:02 FIRING
10:03 FIRING
10:04 FIRING
10:05 NORMAL
10:06 NO_DATA
10:07 NORMAL
10:08 NORMAL
10:09 FIRING
~~~

**Giới hạn quan trọng:** Trong ví dụ, sau NO_DATA detector bắt đầu lại từ NORMAL cho chuỗi mới; **đó không phải là cách xử lý production incident state đúng trong mọi tình huống**. Trong hệ thống thực nên có **alert episode ID**, một **data-quality incident riêng** và quy trình quyết định **khi nào close alert cũ** sau khi dữ liệu trở lại.

### 29.3. Detector hành vi dùng service graph và record quality

~~~python
@dataclass(frozen=True)
class ObservedFlow:
    src_asset: str
    dst_ip: str
    dst_port: int
    action: str
    quality: str
    event_time: str


APPROVED_BASTION_PEERS = frozenset(
    {"10.20.0.10", "10.20.0.11"}
)
ADMIN_PORTS = frozenset({22, 3389, 5985, 5986})


def detect_new_admin_peers(
    flows: list[ObservedFlow],
    source_asset: str,
    approved_peers: frozenset[str],
    min_new_peers: int = 3,
) -> dict:
    """Không chứng minh scan/compromise; chỉ gắn cờ peer drift."""
    owned = [f for f in flows if f.src_asset == source_asset]
    if not owned:
        return {
            "result": "INSUFFICIENT_DATA",
            "new_peers": [],
            "observed_records": 0,
        }

    if any(f.quality != "OK" for f in owned):
        return {
            "result": "DEGRADED_DATA_QUALITY",
            "new_peers": [],
            "observed_records": len(owned),
        }

    candidates = set()
    for f in owned:
        # Validation detects malformed IPs rather than silently treating
        # arbitrary strings as destination assets.
        ip_address(f.dst_ip)
        if (
            f.dst_port in ADMIN_PORTS
            and f.dst_ip not in approved_peers
        ):
            candidates.add(f.dst_ip)

    result = (
        "SUSPECTED_NEW_ADMIN_PEERS"
        if len(candidates) >= min_new_peers
        else "NO_BEHAVIOR_ALERT"
    )
    return {
        "result": result,
        "new_peers": sorted(candidates),
        "observed_records": len(owned),
    }


flows = [
    ObservedFlow("bastion-prod", "10.20.0.10", 22, "ACCEPT", "OK", "10:00"),
    ObservedFlow("bastion-prod", "10.20.0.21", 22, "REJECT", "OK", "10:02"),
    ObservedFlow("bastion-prod", "10.20.0.22", 3389, "REJECT", "OK", "10:05"),
    ObservedFlow("bastion-prod", "10.20.0.23", 22, "REJECT", "OK", "10:07"),
    ObservedFlow("orders-api", "10.20.0.31", 443, "ACCEPT", "OK", "10:08"),
]

finding = detect_new_admin_peers(
    flows, "bastion-prod", APPROVED_BASTION_PEERS
)
print(finding)
assert finding["result"] == "SUSPECTED_NEW_ADMIN_PEERS"
assert len(finding["new_peers"]) == 3

degraded_flows = flows + [
    ObservedFlow("bastion-prod", "10.20.0.24", 22,
                 "UNKNOWN", "SKIPPED", "10:09")
]
degraded = detect_new_admin_peers(
    degraded_flows, "bastion-prod", APPROVED_BASTION_PEERS
)
print(degraded["result"])
assert degraded["result"] == "DEGRADED_DATA_QUALITY"
~~~

Kết quả dự kiến:

~~~text
{'result': 'SUSPECTED_NEW_ADMIN_PEERS', 'new_peers': ['10.20.0.21', '10.20.0.22', '10.20.0.23'], 'observed_records': 4}
DEGRADED_DATA_QUALITY
~~~

### 29.4. Vì sao detector hành vi này chỉ là một phần nhỏ?

- **Approved peers hardcoded:** Production cần versioned **service graph** và join theo **workload identity, timestamp, account/VPC**, không so IP đơn lẻ.
- **Window giả định:** Code không tự group timestamps thành 10 phút; cần upstream event-time windowing và late-event policy.
- **Mọi record phải OK:** Đưa detector sang DEGRADED khi chỉ một record có SKIPPED là cách bảo thủ để minh họa, không phải quy tắc duy nhất của mọi nguồn.
- **Distinct new peers:** Một source có thể được phép quét vì approved maintenance; cần **scanner identity, ticket và context**.
- **Port-only assumptions:** Port 22/3389 không tự xác định protocol hoặc hành động xấu.
- **No volume/sampling adjustment:** Flow logs có thể sampled; distinct peers bị undercount và kết quả không phải connection count.
- **No network attribution:** NAT, shared IP, Pod IP reuse và overlay có thể làm src_asset gán sai.
- **No automatic action:** Lab **không** thực hiện firewall changes, account disable hay network scan.

### 29.5. Bài tập mở rộng

1. Thêm **tumbling/sliding windows**, event time, allowed lateness và late-event counters.
2. Tách **alert state** và **data-quality state**; khi mất dữ liệu không được auto-close alert đang FIRING.
3. Hỗ trợ **3-of-5 valid buckets** với quy tắc tối thiểu cho missing data.
4. Dùng rolling **median/MAD** để so throughput, xử lý MAD=0 và minimum sample count.
5. Thêm **time-of-week baseline** cho VPN logins/backup egress.
6. Thêm **historical asset metadata** và approved scan schedule để giảm false positives.
7. Gắn **new peer detector** với auth/EDR signals và phân biệt **suspected vs confirmed**.
8. Thêm **dedupe fingerprint**, first_seen, last_seen, count và cooldown.
9. Tạo synthetic case **source IP thuộc NAT chung** và chứng minh cần NAT translation/time mapping.
10. Thêm **false-positive review labels và holdout window**, so precision/recall nếu có ground truth.

**Bài thực hành là tư duy thiết kế và kiểm tra logic, không phải hệ thống IDS/IPS hoàn chỉnh.** Không đưa thẳng các threshold/allowlist ví dụ vào Production.

## 30. Ma trận kiểm thử detector và alert pipeline

Những test dưới đây dành cho **lab/staging, synthetic telemetry hoặc các tài sản được cấp quyền**. Không tạo port scan, flood, exfiltration thật hay tấn công credential lên tài sản không được ủy quyền. Những ca liên quan firewall/routing/rate limiting có thể gây ngừng dịch vụ phải có **change owner, approval, canary và rollback**.

| Test ID | Tình huống | Kết quả/bằng chứng mong đợi |
| --- | --- | --- |
| AL-01 | Interface 1 Gbit/s có egress 900 Mbit/s bền vững | Alert high utilization sau đúng duration/window |
| AL-02 | Burst 1 giây trong cửa sổ 5 phút | Kết quả đúng granularity; không mặc định FIRING |
| AL-03 | Counter bytes reset khi exporter restart | Rate reset-aware, không âm hoặc spike giả |
| AL-04 | Interface capacity gauge bằng 0 hoặc missing | Data quality finding; không chia 0 hoặc coi 100% |
| AL-05 | 3-of-5 windows vượt ngưỡng | Phân biệt 3 valid buckets và 3 overlapping evaluations |
| AL-06 | Chỉ 2/5 windows có data, cả hai vượt ngưỡng | Không suy 3-of-5 PASS từ missing |
| AL-07 | Giá trị dao động 84–86% | Hysteresis/duration giảm flapping |
| AL-08 | FIRING rồi metric xuống dưới clear threshold đủ lâu | RESOLVED theo rule, có recovery evidence |
| AL-09 | FIRING rồi collector biến mất | NO_DATA/DEGRADED, không auto-close như bình thường |
| AL-10 | Collector được khôi phục | Episode cũ/new data được xử lý và audit đúng |
| AL-11 | DNS NXDOMAIN 1/1 queries | Ratio guard/min count, không page critical từ một mẫu |
| AL-12 | DNS NXDOMAIN 500/1000 queries | Alert theo ratio+volume nếu baseline/policy cho phép |
| AL-13 | DNS high QPS khi maintenance | Context và suppression có hạn, không tắt security checks khác |
| AL-14 | DNS labels entropy cao thuộc vendor hợp lệ | False-positive triage, không gọi tunneling confirmed |
| AL-15 | DNS DoH/DoT bypass resolver logs | Coverage gap hoặc endpoint/egress evidence, không kết luận không có DNS |
| AL-16 | One-to-many internal ports trong 10 phút | Suspected reconnaissance + distinct features và source identity |
| AL-17 | Low-and-slow scan synthetic kéo 24 giờ | Behavioral long horizon phát nếu theo threat model |
| AL-18 | Approved vulnerability scanner thực hiện job hợp lệ | Context/ticket giảm noise nhưng evidence vẫn giữ |
| AL-19 | New Pod IP được tái sử dụng | Historical workload identity tránh attribution sai |
| AL-20 | VPC flow sampled và một số destination vắng | Quality flag, không khẳng định đầy đủ unique peers |
| AL-21 | NAT public IP chung cho nhiều workloads | Không gán alert actor chỉ từ public source IP |
| AL-22 | Same connection ghi tại hai ENIs | Không cộng bytes thành double throughput |
| AL-23 | Cloud flow action ACCEPT nhưng backend lỗi | Không báo HTTP success từ ACCEPT |
| AL-24 | Firewall REJECT tăng do lỗi allowlist deployment | Phân biệt misconfiguration với malicious scan |
| AL-25 | IDS signature DETECT nhưng IPS không block | Giữ semantics của action nguồn |
| AL-26 | VPN fail count tăng sau client release lỗi | Correlate app/device/IdP context, tránh kết luận stuffing |
| AL-27 | Stolen-credential-like synthetic sequence | Nâng priority nếu verified account/session evidence |
| AL-28 | Public API traffic tăng vì campaign | Behavioral anomaly nhưng business/SLO context tránh DDoS false positive |
| AL-29 | L4 UDP flood synthetic symptoms | Không dùng TCP SYN metric làm điều kiện bắt buộc |
| AL-30 | Egress bytes lớn tới approved backup target | Triage hợp lệ, không báo data theft chắc chắn |
| AL-31 | Slow cumulative outbound tới unapproved peer | Long-horizon feature, không chỉ high-byte threshold |
| AL-32 | New HTTPS to shared CDN IP | Không suy một hostname hoặc attacker từ IP đơn lẻ |
| AL-33 | gRPC/HTTP2 nhiều requests trên một TCP flow | Không đếm connections = application requests |
| AL-34 | mTLS handshake failures do CA rotation | Giữ nguyên error category, không tắt certificate verification |
| AL-35 | TLS peer valid nhưng backend authZ DENY | Phân biệt authentication vs application authorization |
| AL-36 | Data source event timestamps lệch UTC | Timeline normalization và clock quality alert |
| AL-37 | Events đến trễ vượt watermark | Late-data policy rõ, không âm thầm drop làm “0 traffic” |
| AL-38 | Log shipper retry gửi duplicate event | Dedupe delivery IDs, giữ independent observations |
| AL-39 | Parser schema drift sau nâng cấp provider | Không ép UNKNOWN action thành ACCEPT/DENY |
| AL-40 | Cloud log sink mất IAM/KMS writer rights | Telemetry outage alert, coverage degraded |
| AL-41 | PEP/IDS/data collector health ở DR region | Failover giữ coverage và routing alerts đúng |
| AL-42 | Alert lặp lại mỗi evaluation minute | Một incident group với first/last seen, max/count |
| AL-43 | Hai sự cố độc lập cùng detector nhưng khác assets | Không gộp thành một alert vô dụng |
| AL-44 | Maintenance suppression chỉ cho băng thông gateway A | Những security alerts ngoài scope vẫn paging |
| AL-45 | Suppression hết hạn trong lúc condition vẫn true | Alert quay lại theo policy và audit |
| AL-46 | Link parent outage gây downstream errors | Correlation/inhibition giữ child evidence, không che compromise |
| AL-47 | Missing baseline cho workload mới | COLD_START/peer baseline + static guardrails |
| AL-48 | Baseline đã học từ incident | Retrain bị chặn, baseline provenance và review |
| AL-49 | Gradual drift của unapproved destination | Hard guardrails vẫn alert dù EWMA thích nghi |
| AL-50 | MAD=0 trong baseline | Không chia 0, có fallback/insufficient_data |
| AL-51 | Alert threshold chỉ vượt khi label bị nhầm instance | Asset identity/label join được kiểm tra |
| AL-52 | Deny rate tăng tại firewall rule mới | Cross-check change ID/policy action/bypass |
| AL-53 | API request error nhưng network flows bình thường | Correlate app/gateway, không đổ lỗi mạng vô căn cứ |
| AL-54 | Rule change gây 1000x alert volume | Shadow/canary/rollback không phá on-call |
| AL-55 | Pager receiver/route bị đổi | Audit và synthetic notification test, người trực nhận đúng |
| AL-56 | Log xuất chứa fake Authorization marker | Redaction qua SIEM/ticket/pager, không lộ credential |
| AL-57 | Auto-rate-limit làm khách hàng hợp lệ bị chặn | Safe scope/action TTL, rollback và false-block SLO |
| AL-58 | Chính sách nghiêm cấm block target shared NAT | Detector không vượt guardrail dù score cao |
| AL-59 | Offline historical incident replay | Phân biệt TP, FP, FN, unknown với labels hợp lệ |
| AL-60 | Holdout datasets từ region/tuần khác | Tuning không overfit một tuần baseline |
| AL-61 | Webhook feedback SOC gửi label trái quyền | Review nguồn quyền, audit và tránh poisoning model |
| AL-62 | SIEM ngừng nhận logs nhưng dashboard báo zero alerts | Data-quality incident, security confidence degraded |

### 30.1. Mẫu hồ sơ kiểm thử

~~~text
TEST / CHANGE ID:
Rule ID/version, owner and environment:
Asset/workload identity, VPC/account/region, observation point:
Event time UTC, ingestion time, evaluation window:
Source log schema, quality, sampling, duplicate/late handling:
Metric/counter/gauge unit and aggregation:
Threshold/baseline version + expected feature values:
Expected state NORMAL/PENDING/FIRING/NO_DATA/RESOLVED:
Actual alert, severity, confidence and dedupe fingerprint:
Correlated IDS/firewall/DNS/EDR/app/change evidence:
Authorized maintenance/scan context:
False-positive / false-negative evaluation:
Pager and on-call delivery, required action:
Safe rollback / approver / remaining gaps:
~~~

### 30.2. Ba tầng xác minh

1. **Logic:** Unit tests cho threshold/window/baseline/state, schema mapping và non-divide-by-zero.
2. **Pipeline:** Event ingestion, late/sampled/no-data behavior, correlation, dedupe, pager routing.
3. **End-to-end:** Trong môi trường được phép, một dấu hiệu nguy hiểm phù hợp policy tạo alert đến đúng owner; traffic hợp lệ không bị block nhầm; dữ liệu bị mất tạo **quality alert** chứ không im lặng.

**Không coi một ma trận toàn PASS ở mức unit test là đã hoàn tất bảo mật**. Cần xác minh **coverage/collector health, production routing, owner/runbook readiness và false-positive costs**.

## 31. Runbook vận hành khi detector phát cảnh báo

Runbook giúp analyst trả lời **alert có đáng tin không, tài sản có bị ảnh hưởng không, cần lấy gì và có nên phản ứng ngay không**. Với high-confidence compromise có thể phải containment trước khi hoàn tất mọi bằng chứng, theo incident policy; với low-confidence anomaly phải **triage**, không tự phong tỏa.

### 31.1. Quy trình triage

~~~mermaid
flowchart TD
    A["Alert FIRING"] --> B["Check quality, source scope, time and rule version"]
    B --> C{"Telemetry complete enough?"}
    C -- "Không" --> D["Data-quality incident + alternate sources"]
    C -- "Có" --> E["Enrich asset, service owner, identity, approved changes"]
    E --> F["Cross-check independent evidence / baseline"]
    F --> G{"Credible threat or availability impact?"}
    G -- "Chưa rõ" --> H["Investigate / track hypothesis and gaps"]
    G -- "Có" --> I["Contain or mitigate per approval/runbook"]
    I --> J["Verify impact, recovery, ALLOW/DENY and SLO"]
    H --> K["Label finding, update baseline/rule feedback"]
    D --> K
    J --> K
~~~

### 31.2. Bước 1 — xác minh nguồn và phạm vi

1. Rule ID/version, threshold/model, exact **event-time window**, timestamp UTC.
2. Source platform, sensor health, sampling/aggregation, skipped records, ingestion lag.
3. Account/project, region, subnet/ENI, Pod UID/VM resource ID, IP family.
4. Nhận diện **source/peer ownership tại thời điểm**, NAT/LB/sidecar attribution nếu cần.
5. Có **approved maintenance, scan, product launch, backup hoặc DR failover** không?

### 31.3. Bước 2 — xác định detector đang nói gì

| Alert | Câu hỏi đúng | Không nên kết luận |
| --- | --- | --- |
| High utilization | Interface nào gần capacity? Có drops/latency tăng không? | DDoS chắc chắn |
| New peer | Peer nào mới, service có deploy/backup mới không? | Lateral movement confirmed |
| Many firewall REJECT | Rule/source/target nào, đã chặn hay được phép? | Attacker đã chiếm server |
| DNS anomaly | Client/process, domain, volume/entropy và resolver identity? | DNS tunnel đã truyền secrets |
| Unexpected egress | Data owner, expected destination, process và object reads? | Data theft confirmed |
| VPN failures | User/device/MFA, client release, NAT/geo context? | Credential stuffing confirmed |
| TLS handshake failures | Expiry/CA/trust, reload, protocol mismatch, peer identity? | Network intrusion chắc chắn |
| Zero events | Collector active? Source volume/pipeline healthy không? | Không có traffic hoặc sự cố |

### 31.4. Bước 3 — correlation tối thiểu

Tùy use case:

- **Network:** Flow logs, packet/drop counters, firewall rule actions, NAT mappings, VPC routes.
- **Identity:** IdP login/MFA, VPN/ZTNA sessions, ServiceAccount/mTLS principal.
- **Endpoint:** EDR process, host firewall, application startup/deploy.
- **Business data:** DLP, cloud object access, app audit, tenant/resource owner.
- **Control plane:** IAM, security group/route/NAT changes, DNS and mesh config rollouts.

Giữ **observation → hypothesis → verification needed → finding** thành các trường riêng. Không suy một cuộc tấn công đã thành công từ network ACCEPT, một IP mới hoặc port 443.

### 31.5. Bước 4 — hành động theo mức độ tin cậy

**High-confidence ongoing unauthorized activity:** SOC/incident commander có thể **revoke identity, quarantine workload, rate limit, chặn đúng đường mạng** sau khi xác định scope và có quyền. **Low-confidence anomaly:** ưu tiên **giữ evidence, xác minh business context và phát ticket**. Với false positive hợp lệ, tune **rule scope/baseline**; không xóa raw evidence hoặc tắt detector toàn công ty.

### 31.6. Bước 5 — xác minh recovery

- Dịch vụ hợp lệ trở về **SLO/latency/success rate** phù hợp.
- Đường trái quyền **vẫn DENY** sau sửa network policy.
- Collector/data sources **đang hoạt động**, không còn NO_DATA gaps không giải thích.
- Pager/correlation groups không còn alert flood; các finding mở có owner.
- Nếu credential hay workload bị compromise, **revoke/reissue** tại verifier và xác nhận phạm vi hiệu lực.
- Record **timeline, change ID, policy version, root cause confidence, remaining blind spots**.

### 31.7. Mẫu incident report

~~~text
INCIDENT ID / DETECTOR ID/VERSION:
UTC start / first signal / alert / ack / containment / recovery:
Affected accounts/VPCs/regions/resources/workloads:
Telemetry sources, sampling/aggregation, coverage and gaps:
Observed feature values and baseline/threshold:
Rule fingerprint, suppression, correlated alerts:
Context: deployment/maintenance/approved scans:
Evidence: firewall, flow, DNS, VPN, IDS, EDR, app, audit:
Confirmed impact vs suspected hypotheses:
Actions, approvals, blast radius, rollback:
ALLOW functionality and DENY security regression:
Detection quality (TP/FP/FN/UNKNOWN), false positives:
Postmortem owners, deadlines, retention and follow-up:
~~~

### 31.8. Kiểm tra sau khi tune detector

Khi đổi threshold hoặc allowlist, phải chạy lại **các positive/negative cases** và kiểm tra **những tình huống bị bỏ sót**. Ví dụ allowlist một domain do vendor dùng không nên cho phép mọi outbound từ bastion tới **toàn bộ shared CDN ASN**. Rule version phải có **before/after impact** và người sở hữu phê duyệt.

## 32. Những hiểu nhầm thường gặp khi thiết kế alert

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Alert vượt ngưỡng là đã xảy ra tấn công.” | Chỉ chứng minh điều kiện đo được vượt ngưỡng trong scope; cần điều tra nguyên nhân. |
| “AI/ML anomaly detection luôn tốt hơn threshold.” | Mỗi phương pháp có trường hợp mạnh/yếu; data quality và evaluation quan trọng hơn nhãn ML. |
| “Một static threshold dùng chung cho mọi router/VM/Pod.” | Capacity, service role và seasonality khác nhau. |
| “Một bản ghi NetFlow/VPC flow log bằng một TCP connection.” | Flow records có thể aggregated/sampled hoặc cùng session chia nhiều record. |
| “Traffic cao nhất luôn là sự cố nghiêm trọng nhất.” | Unauthorized privileged action nhỏ có thể đáng ưu tiên hơn traffic hợp lệ lớn. |
| “Không có alerts nghĩa là không có incident.” | Rule, sensor, log sink hoặc pipeline có thể mất khả năng quan sát. |
| “COUNT(flow records) là số packets.” | Record counts, packets và sessions là các đơn vị khác nhau. |
| “Cộng bytes của mọi sensor là tổng dữ liệu đã truyền.” | Multi-hop logs có thể đếm trùng; sampling/headers/retransmissions ảnh hưởng. |
| “Firewall ACCEPT chứng minh backend HTTP 200.” | Chỉ nói về action ở điểm firewall, cần app logs để xác minh. |
| “IDS signature HIT là xâm nhập thành công.” | Có thể là attempt đã bị chặn, false positive hoặc test hợp lệ. |
| “Một IP public NAT là một người dùng.” | Nhiều users/Pods có thể chia sẻ IP và port mappings. |
| “Pod IP hiện tại đủ quy traffic tuần trước.” | Pod/VM IP có thể tái sử dụng, cần historical identity. |
| “Z-score >3 nghĩa là xác suất tấn công gần 100%.” | Z-score đo độ lệch trong mô hình, không trực tiếp xác suất malicious. |
| “MAD=0 thì chia cho 0 hoặc coi không có anomaly.” | Cần fallback hoặc insufficient evidence rõ ràng. |
| “P99 từ vài mẫu có ý nghĩa như p99 từ dữ liệu lớn.” | Sample size và dependence quyết định độ tin cậy. |
| “Adaptive baseline luôn tự cải thiện khi có traffic mới.” | Có nguy cơ poisoning, incident contamination và concept drift. |
| “EWMA tăng theo spike nghĩa là tấn công đã hết.” | Baseline có thể đang học theo attack và làm rule im lặng. |
| “Baseline theo tuần không cần business calendar.” | Product launch/backup/DR/maintenance tạo seasonality đặc biệt. |
| “Một tỷ lệ lỗi 100% luôn nghiêm trọng.” | 1/1 và 1000/1000 có độ tin cậy/impact khác nhau. |
| “Thiếu data bucket có thể coi bằng 0 cho tiện.” | Missing != zero, cần NO_DATA/DEGRADED. |
| “Ingestion time là lúc packet xảy ra.” | Event time, aggregation và delivery time khác nhau. |
| “Sliding window 5 phút luôn có một alert duy nhất.” | Các evaluations overlap có thể báo trùng nếu không dedupe. |
| “Mỗi phút FIRING lại phải paging.” | Incident/group có thể cập nhật last_seen/count mà không spam. |
| “Silence trong maintenance an toàn để áp cho mọi rule.” | Silence phải có scope, owner, expiry, giữ hard security guards. |
| “Một scanner được allowlist thì mọi activity của nó hợp lệ.” | Phải kiểm scope, identity, thời gian, targets và hành động được phê duyệt. |
| “Nhiều port REJECT là port scan có chủ ý xấu.” | Monitoring và misconfiguration có thể tạo cùng pattern. |
| “DNS entropy cao chứng minh DNS tunneling.” | IDs/CDN và DNS hợp lệ cũng sinh labels entropy cao. |
| “NXDOMAIN cao luôn là DGA.” | Lỗi deploy, search domain hoặc client config cũng gây ra. |
| “Bps cao chứng minh DDoS.” | Marketing campaign, backups và data imports cũng có thể tăng traffic. |
| “Egress bytes tăng nghĩa là dữ liệu bí mật đã bị đánh cắp.” | Cần DLP/object audit/process/identity và remote confirmation phù hợp. |
| “Đích IP mới chắc là adversary infrastructure.” | Shared CDN, cloud failover và legitimate services có IP mới. |
| “HTTPS/VPN ngăn mọi network monitoring.” | Metadata IP/port/bytes còn quan sát được ở các điểm; payload vẫn cần bảo vệ. |
| “Một PEP/mesh allow là ứng dụng cho phép mọi object.” | Workload auth và app resource authorization khác nhau. |
| “Tự động block IP nguy hiểm luôn tốt hơn để analyst xử lý.” | Shared IP/false positives có thể gây outage lớn, cần guardrails. |
| “Alert precision 100% vì tất cả alerts đều được đánh giá là TP.” | Cần ground truth, tính FN và review tập không alert. |
| “Chỉ tune một lần sau khi deploy.” | Data drift, new workload, source schema và threat model thay đổi. |
| “CI rule PASS nghĩa là Prod detector hoạt động.” | Cần readback effective rule, data source health, routing và paging. |
| “Auto-close khi dữ liệu về 0 là bình thường.” | Collector outage có thể khiến 0 events, không chứng minh recovery. |
| “Đưa raw Authorization vào alert giúp điều tra dễ hơn.” | Gây lộ bearer token; nên dùng evidence metadata đã redact. |

## 33. Câu hỏi tự kiểm tra và bài tập kiến trúc

1. **Ngưỡng tĩnh là gì?** Điều kiện so metric/event với giá trị hoặc luật cố định trong cửa sổ.
2. **Ngưỡng động khác ở đâu?** Tham chiếu biến thiên từ baseline theo điều kiện/time, có yêu cầu lịch sử và quality.
3. **Behavioral detection chỉ có thể làm bằng AI?** Không; service graph, distinct peers và event sequence đủ tạo rule hành vi.
4. **Vì sao port scan chậm có thể thoát alert PPS?** Volume mỗi cửa sổ thấp dù số đích/cổng mới tăng dài hạn.
5. **Counter và gauge cần xử lý khác nhau thế nào?** Counter dùng reset-aware rate/increase, gauge có thể đo trực tiếp theo thời gian.
6. **Tại sao không chia capacity khi capacity metric bằng 0?** Không có denominator đáng tin; đánh dấu quality lỗi.
7. **Một SYN failed ratio 100% với một attempt đáng báo gì?** Cần sample-size guard và context, không xem tương đương flood.
8. **Sliding window tạo nguy cơ gì?** Nhiều windows chồng lấp dẫn tới duplicate alerts, cần dedupe.
9. **Tumbling window có thể bỏ burst thế nào?** Burst nằm sát ranh giới bị chia nhỏ dưới threshold.
10. **Event time khác ingestion time ở đâu?** Event xảy ra tại nguồn, ingestion là khi hệ thống nhận; có aggregation/delay.
11. **Sampling ảnh hưởng distinct destination count thế nào?** Có thể undercount targets; không tự suy số đích thực.
12. **Khi collector mất thì metric=0 đúng không?** Không; dữ liệu không có, phải NO_DATA/DEGRADED.
13. **Vì sao cần historical identity mapping?** NAT/Pod IP reuse làm actor attribution sai nếu tra inventory hiện tại.
14. **EWMA có rủi ro gì khi học từ traffic tấn công?** Baseline tự nâng lên và làm mất alert.
15. **Khi MAD=0 cần làm gì?** Chọn fallback/minimum delta/unknown, không chia 0.
16. **P99 baseline từ 8 mẫu có đáng tin như 8.000 mẫu không?** Không; sample size và dependence khác.
17. **Hysteresis và duration giải quyết gì?** Giảm flapping và single-sample noise, đánh đổi tăng detection delay.
18. **Dedupe khác correlation?** Dedupe gộp cùng alert episode; correlation liên kết signals thành giả thuyết chung.
19. **Suppression cần gì để an toàn?** Scope, owner, approval, expiry và audit, không che security-critical khác.
20. **Nhiều firewall DENY cho biết điều gì?** Policy chặn các attempts ở observation point; chưa chứng minh attacker thành công.
21. **DNS tunneling có thể phát hiện chỉ bằng entropy không?** Không, cần client/process/domain context và corroboration.
22. **HTTP/2 có thể có bao nhiêu requests trên một TCP flow?** Nhiều requests/streams, không thể đếm từ flow record đơn thuần.
23. **DDoS detector nên kết hợp các tín hiệu nào?** PPS/BPS, connection state, drops, WAF/CDN, app SLI và mitigation.
24. **Egress bytes cao có xác nhận exfil không?** Không, cần data ownership, object/app/EDR/DLP evidence.
25. **Precision và recall khác nhau?** Precision đo phần alerts đúng trong alerts, recall đo phần incidents/events cần phát hiện được bắt.
26. **Vì sao detection holdout quan trọng?** Giảm overfitting trên lịch sử đã dùng tune.
27. **Tại sao auto-block shared CDN IP nguy hiểm?** Ảnh hưởng nhiều clients/services hợp lệ, khó quy một actor.
28. **Một alert tốt nên có metadata nào?** Rule/version, scope, UTC window, feature/baseline, quality, evidence, owner/runbook.
29. **Ngưỡng nào phù hợp cho bastion so với public ingress?** Bastion ưu tiên peer/admin identity, ingress ưu tiên capacity/RPS/error/SLO và các security signals khác.
30. **Vì sao app latency tốt chưa loại trừ tấn công?** Một số hoạt động trái quyền low-volume vẫn xảy ra khi hệ thống khỏe.
31. **Làm sao biết detector đã hoạt động trên Prod?** Effective rule, sensor coverage/quality, synthetic permitted event, pager routing và triage.
32. **Một detector không báo gì sau schema migration phải kiểm tra gì?** Parser/version, source action mapping, filter scope, health và backfill.

### Bài tập tổng hợp

Một tổ chức có **Internet-facing API** qua CDN/WAF/load balancer, **VPN/ZTNA** cho nhân viên, **Kubernetes microservices**, Production database ở private subnet, DNS resolvers và cloud VPC flow logging. SOC nhận cùng lúc ba báo cáo: API traffic tăng mạnh, bastion kết nối những servers chưa từng thấy và một collector ngừng gửi dữ liệu.

Hãy xây dựng bản thiết kế detection engineering gồm:

1. **Sơ đồ telemetry pipeline** từ sensors tới SIEM, PDP/PEP/firewall/application audit và on-call.
2. **Inventory nguồn, metric type/unit** (counter/gauge/events/flows) và điểm quan sát tương ứng.
3. **Static threshold rules** cho utilization/drops, link/VPN health, collector NO_DATA.
4. **Adaptive baseline** cho API QPS, DNS NXDOMAIN, user VPN login và backup egress theo time-of-week.
5. **Behavior rules** cho bastion new peers, DNS queries hiếm, east-west graph drift và unauthorized admin.
6. **Cửa sổ thời gian**: event time, aggregation, sampling, allowed late arrivals, M-of-N và hysteresis.
7. **Risk/severity routing** theo asset criticality, confirmed impact và confidence/quality.
8. **Correlation** giữa firewall/IDS/flow, WAF, IdP/EDR, Kubernetes và business changes.
9. **Suppression** cho load test được phê duyệt nhưng vẫn giữ critical security và data-quality alerts.
10. **Kiểm thử** TP/FP/FN/unknown bằng lab replay, không dùng attack traffic ngoài quyền.
11. **Safe response** cho DDoS, credential abuse và suspected exfil với action scope, rollback, SLO.
12. **Dashboard** precision/actionability, TTD, duplicate ratio, stale sensors, event delivery lag, false-positive cost.
13. **Runbook** từ alert tới incident conclusion, rõ owner, evidence và remaining unknowns.

**Tiêu chí đánh giá:** Một thiết kế tốt phải giải thích được **tại sao detector phát hoặc không phát, dữ liệu có đáng tin không, hoạt động ấy có hợp lệ theo service/workload context không, và phản ứng nào an toàn**. Với mạng có nhiều điểm quan sát, cũng phải chứng minh **không đếm trùng traffic và không bỏ sót những vùng chưa thu telemetry**.

## 34. Checklist triển khai alert theo ngưỡng và hành vi

- [ ] Có **inventory network sensors/log sources** theo account/VPC/VNet/interface/Pod, IPv4/IPv6 và DR?
- [ ] Mỗi detector có **use case, owner, resource scope, severity và runbook** rõ?
- [ ] Đã phân biệt **network capacity/SLO alert** với security threat hypothesis?
- [ ] Chọn đúng **counter/gauge/histogram/event/flow schema** và đơn vị đo?
- [ ] Counter có **reset-aware rate**, gauge/capacity không chia cho 0?
- [ ] Các truy vấn **COUNT/SUM/AVG/MAX/P95/DISTINCT/RATIO** có semantics được kiểm chứng?
- [ ] Ratio thresholds có **minimum denominator/sample size** và negative cases?
- [ ] Time windows có **event time UTC, ingestion lag, aggregation, late events** rõ?
- [ ] Đã xác định **tumbling/sliding, M-of-N, duration, high/clear hysteresis**?
- [ ] **NO_DATA/STALE** là trạng thái riêng, không ép thành metric=0 hay healthy?
- [ ] Có alert cho **collector heartbeat, source coverage, parser errors, skip/sampling, ingestion lag**?
- [ ] Biết flow records có thể **sampled, aggregated, duplicate hoặc đa observation points**?
- [ ] Tính toán volume có một **accounting boundary** rõ, không double-count?
- [ ] Các nguồn action **ACCEPT/REJECT/DROP/DETECT/CHALLENGE** giữ nguyên semantics ban đầu?
- [ ] Enrichment IP/asset/Pod/ServiceAccount có **time-aware mapping** và NAT/proxy context?
- [ ] Baseline theo **workload/service role, environment, time-of-week và business calendar**?
- [ ] Có cơ chế **cold start/peer-group baseline**, không học 5 phút đầu rồi coi là bình thường?
- [ ] Baseline có **minimum samples, version/provenance, exclusions cho incidents**?
- [ ] Có xử lý **seasonality, concept drift và baseline poisoning**?
- [ ] Các phép tính **z-score, MAD, EWMA, percentiles** có giới hạn/điều kiện rõ?
- [ ] Detectors low-and-slow có **long-horizon features** cho new peers/ports?
- [ ] Có coverage cho **DNS anomalies, lateral movement, unusual egress, authentication, TLS/VPN, DDoS** tùy threat model?
- [ ] Không kết luận **attack/exfiltration confirmed** chỉ bằng high bytes, entropy hoặc nhiều REJECT?
- [ ] Các cảnh báo có **identity, resource, UTC window, baseline/threshold, confidence và quality**?
- [ ] Có **dedup/correlation**, không paging mỗi evaluation cho cùng incident?
- [ ] Suppressions có **scope, owner, expiry, approval/audit**, không che alerts critical ngoài scope?
- [ ] Hệ thống biết **parent-child dependency incidents** mà không đánh mất independent evidence?
- [ ] Severity phản ánh **criticality, confidence, actual impact và urgency**, không chỉ số vượt threshold?
- [ ] Đã đánh giá **precision/recall/TTD/actionability** trên tập có nhãn thích hợp và holdout?
- [ ] Có ghi **unknown/unreviewed**, không tự gán mọi alert chưa triage thành FP?
- [ ] Có **policy-as-code, peer review, shadow, canary, rollback và detector version**?
- [ ] Sau rollout đã xác minh **effective rule, source health, pager receiver và owner ACK**?
- [ ] **Auto-block/rate limit** được giới hạn theo resource, có safe rollback và false-block SLO?
- [ ] Bảo vệ **IAM, encryption, privacy, redaction, retention và evidence access**?
- [ ] Monitor **detector disables, changed suppressions, log sink IAM/KMS và model retrain**?
- [ ] Khi kiểm tra đã có **authorized synthetic positive/negative tests** và edge cases missing/late?
- [ ] Có runbook triage **observation → hypothesis → corroboration → response → feedback**?
- [ ] Sau mitigation đã kiểm tra **service hợp lệ phục hồi và unauthorized path vẫn DENY**?
- [ ] Các blind spots/quality gaps và remaining risk được ghi nhận rõ trong incident report?

**Kết luận:** **Alert theo ngưỡng** rất hiệu quả để phát hiện một chỉ số vượt giới hạn vận hành hoặc chính sách; **alert theo hành vi** bổ sung khả năng nhận ra mẫu kết nối, thời gian, danh tính và quan hệ dịch vụ bất thường ngay cả khi traffic thấp. Cả hai chỉ đáng tin nếu **telemetry đầy đủ và có nhãn chất lượng, aggregation đúng, baseline có điều kiện, cửa sổ thời gian rõ, rule được kiểm thử và alerts được tương quan với bằng chứng độc lập**. Một hệ thống giám sát mạng tốt cần **phát hiện sớm, giảm báo động giả, không im lặng khi mất sensor, định tuyến đúng người xử lý và chỉ phản ứng mạnh khi có đủ điều kiện an toàn**. Mục tiêu cuối cùng không phải nhiều alerts mà là **nhận biết và xử lý đúng rủi ro trong khi duy trì kết nối hợp lệ, giữ phân đoạn mạng và bảo vệ dữ liệu**.
