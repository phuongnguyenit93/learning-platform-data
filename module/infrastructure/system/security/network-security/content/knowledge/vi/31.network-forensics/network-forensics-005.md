# Nhận diện beaconing và periodic connection trong network forensics

## 1. Beaconing và kết nối định kỳ là gì?

**Beaconing** là hiện tượng một thiết bị, ứng dụng hoặc tiến trình liên lạc lặp lại với một điểm đích theo các khoảng thời gian có quy luật hoặc gần có quy luật. Trong điều tra an ninh mạng, hành vi này thường được xem xét khi nghi ngờ một thành phần liên lạc định kỳ với hệ thống điều khiển từ xa (**command-and-control, C2**). Nhưng **nhịp kết nối đều không đồng nghĩa có mã độc**: agent giám sát, health check, cập nhật phần mềm, đồng bộ thời gian, VPN keepalive và application polling cũng tạo những mẫu như vậy.

Trong chương **Điều tra số trên mạng** của mô-đun **SECURITY_NETWORK_SECURITY**, phát hiện beaconing sử dụng dữ liệu từ phân đoạn mạng, firewall, VPN, IDS/IPS, DNS, mạng không dây, packet capture, proxy và hạ tầng đám mây để trả lời:

- **Nguồn:** thiết bị, workload, tiến trình và tài khoản nào tạo lưu lượng?
- **Đích:** IP, hostname, port, protocol và dịch vụ nào được liên hệ?
- **Thời gian:** hoạt động bắt đầu khi nào, lặp theo nhịp nào, tồn tại trong bao lâu?
- **Hành vi:** mở connection mới, gửi request, DNS query, retry hay application heartbeat?
- **Ngữ cảnh:** có lịch tác vụ hoặc nhiệm vụ hợp lệ giải thích nhịp này không?
- **Đối chiếu:** flow, DNS, proxy, firewall, endpoint và IDS cùng cho thấy điều gì?

Mục tiêu là **tìm các ứng viên để điều tra**, phân biệt giao tiếp có chủ đích và traffic nền hợp lệ, rồi kết luận theo chứng cứ. Chỉ riêng sự định kỳ chưa chứng minh C2 thành công, malware hay rò rỉ dữ liệu.

## 2. Các hiện tượng cần phân biệt

| Hiện tượng | Mẫu thường thấy | Ý nghĩa |
| --- | --- | --- |
| **Periodic connection** | Mở nhiều phiên tới cùng đích theo lịch | Có thể hợp lệ hoặc đáng nghi |
| **Beaconing nghi C2** | Liên lạc lặp kèm dấu hiệu khác về tiến trình/đích | Cần xác minh bằng nguồn độc lập |
| **Health check** | Gọi endpoint theo phút/giây | Kiểm tra owner và cấu hình monitoring |
| **Scheduled job/updater** | Hoạt động mỗi giờ/ngày hoặc theo phiên | Kiểm tra scheduler, job và update logs |
| **Retry/backoff** | Kết nối lại sau lỗi hoặc timeout | Có thể giống nhịp tuần hoàn trong cửa sổ ngắn |
| **Application polling** | Nhiều request trên một kết nối | Cần request-level log để thấy tần suất |
| **Keepalive** | Message nhỏ lặp trong connection dài | Không nhất thiết có TCP connection mới |
| **DNS refresh** | Query lặp theo cache/TTL/lỗi | Không chứng minh có kết nối ứng dụng |

**Một connection khác một request.** HTTP/2 multiplex nhiều stream, WebSocket/gRPC/QUIC cho phép lưu lượng định kỳ trên connection kéo dài. Một request cũng có thể làm phát sinh nhiều phiên TCP do retry hoặc proxy. Do đó phải xác định **loại sự kiện** trước khi tính chu kỳ.

## 3. Nguồn telemetry để tìm mẫu lặp

| Nguồn | Bằng chứng hữu ích | Hạn chế |
| --- | --- | --- |
| **Firewall/NAT session logs** | 5-tuple, action, session start/end, byte, NAT mapping | Một số thiết bị chỉ log lúc session đóng |
| **NetFlow/IPFIX** | Flow start/end, packet, byte, IP/port/protocol | Exporter có active timeout làm một connection thành nhiều record |
| **sFlow** | Sampled packets và counters | Có thể bỏ sót connection ngắn |
| **DNS resolver logs** | Client, QNAME, QTYPE, RCODE, answer, TTL | Query có thể không đi cùng connection vì cache |
| **Proxy/CDN/API gateway** | Request time, route, host, status, request ID | TLS termination, cache và connection reuse |
| **IDS/IPS/NDR/Zeek** | Alert, session metadata, TLS/DNS/HTTP khi có thể phân tích | Sensor có thể thiếu một chiều; false positives |
| **PCAP/PCAPNG** | Packet timing, TCP flags, sizes, plaintext còn hiển thị | Mã hóa, offloading, capture loss, dung lượng lớn |
| **Endpoint/EDR** | Process lineage, executable, signer, task, identity | Agent có thể bị ngắt hoặc thiếu event |
| **VPN/NAC/DHCP** | Host mapping, tunnel, user, IP lease, access session | Mapping chỉ đúng trong cửa sổ lịch sử |
| **Cloud/Kubernetes** | VPC flow, instance/pod UID, CNI policy, egress | IP thay đổi, NAT/overlay, log aggregation |

Một dashboard SIEM có thể tổng hợp từ nhiều hệ thống nhưng **hai biểu đồ dùng chung nguồn gốc không tạo thành hai chứng cứ độc lập**. Cần ghi sensor, phiên bản/cấu hình exporter, mức sampling và điểm quan sát.

### 3.1. Những nguồn trả lời câu hỏi nào?

**Flow/firewall** trả lời các cặp endpoint nào trao đổi, bao nhiêu lần và bao nhiêu byte tại điểm thu. **DNS** giúp tìm tên dịch vụ được truy vấn, nhưng DNS query không xác nhận đã có TCP connection. **Proxy logs** cung cấp request ở mức HTTP khi đã có khả năng đọc request tại proxy. **EDR** giúp xác định tiến trình và lịch tác vụ. **PCAP** kiểm chứng thứ tự packet/TCP handshake tại một interface, nhưng không tự giải mã TLS/QUIC hay xác định payload có dữ liệu mật.

## 4. Định nghĩa một sự kiện quan sát

Khi phân tích một asset gọi TCP/443, cần phân biệt:

1. **Connection attempt:** lần đầu thử mở connection, không đếm SYN retransmission thành phiên mới.
2. **Established session:** một phiên đã thiết lập TCP hoặc được firewall xác nhận trạng thái established.
3. **HTTP request:** một request logic, có thể có nhiều request trên cùng TCP/TLS connection.
4. **DNS query:** một lần hỏi resolver, không bảo đảm sẽ có HTTP connection.
5. **Application heartbeat:** message trong một connection có sẵn; flow logs có thể không có record riêng.
6. **Flow export record:** record định kỳ của collector/exporter; có thể thuộc **một** connection kéo dài.

Một khóa nhóm ứng viên hợp lý:

~~~text
asset_id + destination_identity + protocol + destination_port + event_type
~~~

Trong đó **asset_id** xác định thiết bị/workload theo thời gian, **destination_identity** là endpoint đã kiểm chứng (IP:port hoặc service logic) và **event_type** quy định đang đo sự kiện nào. Không gộp bừa tất cả IP của một CDN hoặc mọi người dùng sau cùng NAT public IP.

### 4.1. Chuẩn hóa dữ liệu trước khi đo

| Trường | Ý nghĩa |
| --- | --- |
| event_time_utc | Timestamp thực của sự kiện theo nguồn |
| ingest_time_utc | Timestamp khi collector nhận record |
| source_asset_id | Asset/workload ID tại thời điểm sự kiện |
| src_ip, src_port, dst_ip, dst_port | 5-tuple cùng protocol, trước/sau NAT tùy điểm bắt |
| destination_domain | Domain có bằng chứng liên hệ với flow |
| protocol, event_type | Giao thức và loại sự kiện được đếm |
| action, result | Allow/deny, success/fail, HTTP status nếu có |
| bytes_out, bytes_in, duration_ms | Kích thước, hướng và thời lượng theo semantics nguồn |
| sensor_id, source_system | Thiết bị/cảm biến và phương pháp tạo log |
| connection_id, request_id | Khóa tham chiếu nếu nguồn cung cấp |

Trước khi phân tích phải: chuẩn hóa timezone về UTC nhưng giữ raw timestamp; kiểm tra clock skew; tách event time khỏi ingest time; loại record ingest trùng mà không gộp nhầm các connection thật; đối chiếu NAT/DHCP/cloud mapping theo thời điểm; xác nhận sampling, packet drop, exporter timeout, độ phân giải timestamps và khoảng thiếu log.

**Ví dụ sai lệch:** IPFIX xuất record mỗi 60 giây theo active timeout. Một kết nối duy nhất kéo dài 10 phút có thể tạo nhiều record cách nhau 60 giây. Đây là **chu kỳ xuất log**, chưa phải client mở kết nối mỗi phút.

## 5. Tính khoảng cách thời gian giữa các sự kiện

Với nhóm sự kiện có mốc tăng dần:

\[
t_1 < t_2 < \cdots < t_n
\]

Khoảng giữa hai sự kiện liên tiếp:

\[
\Delta_i=t_{i+1}-t_i,\qquad i=1,\ldots,n-1
\]

Các thống kê:

| Chỉ số | Ý nghĩa | Cẩn trọng |
| --- | --- | --- |
| Mean inter-arrival | Khoảng trung bình | Dễ bị kéo lệch do mất record hoặc outage |
| Median inter-arrival | Khoảng điển hình | Có thể che nhiều chu kỳ khác nhau |
| Standard deviation | Độ phân tán tuyệt đối | Phụ thuộc đơn vị và chu kỳ |
| Coefficient of variation (CV) | Độ phân tán tương đối | CV nhỏ không đồng nghĩa độc hại |
| Median absolute deviation (MAD) | Độ lệch trung vị ít nhạy outlier | Cần đủ mẫu |
| Inter-arrival histogram | Nhận diện một hoặc nhiều cụm khoảng | Binning ảnh hưởng kết quả |
| Time-of-day pattern | Lặp theo giờ, ngày, phiên hoạt động | Cron/monitoring thường đều |
| Autocorrelation/periodogram | Tìm tín hiệu lặp trong chuỗi đủ dài | Peak không thay thế phân tích nguyên nhân |

Khi mean interval lớn hơn 0, hệ số biến thiên:

\[
CV=\frac{\sigma_\Delta}{\overline{\Delta}}
\]

trong đó \(\sigma_\Delta\) là độ lệch chuẩn của dãy khoảng. Đây là chỉ số **mô tả dữ liệu tại cửa sổ quan sát**; không phải xác suất malware và không có ngưỡng phổ quát cho mọi endpoint.

### 5.1. Ví dụ định lượng

| Lần | Thời điểm UTC | Khoảng từ lần trước |
| --- | --- | --- |
| 1 | 10:00:00 | — |
| 2 | 10:01:00 | 60 giây |
| 3 | 10:02:01 | 61 giây |
| 4 | 10:03:00 | 59 giây |
| 5 | 10:04:00 | 60 giây |
| 6 | 10:05:00 | 60 giây |

Với dãy **[60,61,59,60,60]** giây, mean = 60 giây, median = 60 giây, population standard deviation ≈ 0,63 giây, **CV ≈ 1,1%**. Đây là bằng chứng có **nhịp gần đều trong năm khoảng**, nhưng cùng mẫu cũng có thể do updater hoặc monitoring agent. Muốn phân loại cần xác định đích, tiến trình và lịch hợp lệ.

Nếu thiếu một event, khoảng 120 giây có thể xuất hiện. Nếu có retry, một khoảng 2 giây có thể chen vào. Tránh coi những dao động này là đặc tính phần mềm khi chưa kiểm tra tình trạng nguồn log và lỗi mạng.

## 6. Không chỉ tìm chu kỳ hoàn toàn đều

Các lịch thực tế có thể bị ảnh hưởng bởi scheduler, network latency, timeout, máy ngủ/thức và CPU load. Nhiều traffic lặp có thể:

- Gần một chu kỳ điển hình nhưng thay đổi vài giây giữa các lần.
- Gồm cụm nhiều request ngắn và khoảng nghỉ dài.
- Chỉ xuất hiện trong ca làm việc, phiên VPN hoặc khi service hoạt động.
- Chạy mỗi giờ/ngày thay vì theo phút.
- Liên hệ nhiều IP của một dịch vụ do CDN/load balancing.
- Phát message trên HTTP/2, WebSocket, gRPC hoặc QUIC connection dài.

Hãy so phân phối interval trên nhiều cửa sổ, sự thay đổi sau deploy/config, baseline theo nhóm host cùng vai trò và các sự kiện bảo trì. Không nên gán nhãn bằng một con số cố định.

## 7. Luồng phát hiện và xác minh

~~~mermaid
flowchart TD
    A[Chọn nguồn log và cửa sổ UTC] --> B[Ánh xạ asset, NAT và endpoint]
    B --> C[Kiểm tra event type, duplicate, sampling, clock]
    C --> D[Nhóm asset + đích + protocol + event type]
    D --> E[Tính inter-arrival, duration và volume]
    E --> F{Có mẫu lặp cần xem xét?}
    F -->|Chưa rõ| G[Mở rộng cửa sổ hoặc dữ liệu]
    G --> C
    F -->|Có| H[So baseline và lịch tác vụ hợp lệ]
    H --> I[Đối chiếu DNS, proxy, EDR, IDS, firewall]
    I --> J[Ghi kết luận có giới hạn và bảo toàn chứng cứ]
~~~

Các bước này tạo **ứng viên điều tra**, không tạo phán quyết tự động rằng host đã bị xâm nhập. Có thể xác định ưu tiên theo độ nhạy tài sản, điểm bất thường so baseline, chất lượng bằng chứng và các chỉ báo bổ sung.

## 8. Ví dụ SQL nhận diện kết nối gần định kỳ

Giả sử pipeline có bảng **network_events** với event_time_utc (timestamp có timezone), asset_id, destination_id và event_type. Mỗi hàng được chuẩn hóa thành một **connection attempt mới**, sau khi loại các bản ghi xuất lại của flow exporter và SYN retransmission. Truy vấn PostgreSQL sau tính khoảng cách trong từng cặp host–đích:

~~~sql
WITH ordered AS (
    SELECT
        asset_id,
        destination_id,
        event_time_utc,
        LAG(event_time_utc) OVER (
            PARTITION BY asset_id, destination_id
            ORDER BY event_time_utc
        ) AS previous_time
    FROM network_events
    WHERE event_type = 'connection_attempt'
      AND event_time_utc >= TIMESTAMPTZ '2026-11-28 00:00:00+00'
      AND event_time_utc <  TIMESTAMPTZ '2026-11-29 00:00:00+00'
),
intervals AS (
    SELECT
        asset_id,
        destination_id,
        EXTRACT(EPOCH FROM (event_time_utc - previous_time))
            AS interval_seconds
    FROM ordered
    WHERE previous_time IS NOT NULL
),
summary AS (
    SELECT
        asset_id,
        destination_id,
        COUNT(*) AS interval_count,
        AVG(interval_seconds) AS mean_interval_seconds,
        STDDEV_POP(interval_seconds) AS stddev_interval_seconds
    FROM intervals
    WHERE interval_seconds > 0
    GROUP BY asset_id, destination_id
)
SELECT
    asset_id,
    destination_id,
    interval_count,
    ROUND(mean_interval_seconds, 2) AS mean_seconds,
    ROUND(stddev_interval_seconds, 2) AS stddev_seconds,
    ROUND(
        stddev_interval_seconds / NULLIF(mean_interval_seconds, 0), 3
    ) AS coefficient_of_variation
FROM summary
WHERE interval_count >= 5
ORDER BY coefficient_of_variation ASC;
~~~

**Cách đọc:** mỗi hàng kết quả là một nhóm có ít nhất năm khoảng giữa các connection attempts. CV thấp xếp một ứng viên lên đầu bảng, **không phải rule xác nhận C2**. Số khoảng tối thiểu, cửa sổ thời gian và phân nhóm theo service/destination cần hiệu chỉnh theo nguồn log và môi trường. Nhóm cả ngày có thể che mất một nhịp chỉ diễn ra trong một giờ; khi cần có thể tính theo cửa sổ trượt. Nếu timestamps chỉ có độ phân giải phút, không thể phân tích chu kỳ ngắn với độ chính xác giây.

Ví dụ bản tóm tắt phân tích:

~~~json
{
  "asset_id": "WS-042",
  "destination": "203.0.113.70:443",
  "event_type": "connection_attempt",
  "event_count": 6,
  "interval_count": 5,
  "mean_interval_seconds": 60,
  "median_interval_seconds": 60,
  "cv": 0.011,
  "classification": "candidate_needs_review",
  "limitations": "Only five intervals; process identity unverified"
}
~~~

Đây là dữ liệu minh họa. Báo cáo thực tế cần giữ **raw event IDs**, filter, query, phiên bản detection và nguồn timestamp để kiểm chứng lại từng sự kiện.

## 9. Những tín hiệu bổ trợ cần kiểm tra

### 9.1. Kích thước, thời lượng và kết quả connection

Ngoài khoảng thời gian, hãy xem session duration, bytes_out, bytes_in, packet counts, tỷ lệ hai chiều, TCP reset, connection success/failure và HTTP status. Ví dụ, một loạt kết nối nhỏ gửi/nhận ít byte có thể là heartbeat hoặc health check. Các đợt outbound bytes lớn ngay sau chuỗi lặp cần điều tra thêm, nhưng **bytes trên flow không tự chứng minh dữ liệu nhạy cảm đã bị lấy đi**. Cần file access audit, DLP, proxy hoặc application logs để xác minh nội dung.

Một số ứng dụng giữ TCP connection và gửi request nhỏ định kỳ; flow-level detection có thể không thấy nhịp ứng dụng. Ngược lại, lỗi kết nối có thể tạo nhiều SYN/retry trông giống beacon nếu không phân biệt session mới.

### 9.2. Bối cảnh destination

Đánh giá endpoint có thuộc phần mềm cập nhật, dịch vụ giám sát, SaaS hoặc đối tác được phê duyệt không. Đối chiếu DNS answers, TLS metadata còn nhìn thấy, proxy host/route, asset role và các host cùng nhóm. Threat intelligence có thể giúp ưu tiên, nhưng cần xem **nguồn, thời điểm công bố và độ tin cậy**.

IP nằm trong cloud/CDN, tên miền hiếm gặp hoặc vị trí địa lý lạ **không tự chứng minh độc hại**. Một IP có thể phục vụ nhiều khách hàng hoặc được tái sử dụng theo thời gian.

### 9.3. Bối cảnh tiến trình và danh tính

Từ EDR/host audit, tìm process lineage, executable path, signer, scheduler/systemd timer/cron, account context, thời điểm khởi chạy, lần update/deployment gần nhất và các sự kiện khác. Lịch tác vụ được quản lý và process có owner rõ ràng giúp giải thích một chu kỳ.

Đáng ưu tiên hơn là chuỗi phát sinh sau một hành vi endpoint bất thường, không tìm được chủ sở hữu hợp lệ, hoặc có thêm dấu hiệu credential misuse và data-access anomaly. Kết luận vẫn phải dựa trên **nhiều bằng chứng độc lập**, không đơn thuần so chu kỳ.

## 10. False positive và baseline hoạt động bình thường

| Hoạt động hợp lệ | Vì sao có thể lặp đều? | Nguồn kiểm chứng |
| --- | --- | --- |
| NTP/time sync | Client đồng bộ giờ theo lịch | Time service, server được phép, policy |
| Monitoring/EDR agent | Heartbeat về hệ thống quản lý | Agent inventory, config, log |
| API health check | Gọi endpoint kiểm tra sức khỏe | Route, scheduler, monitoring owner |
| Backup/replication | Truyền dữ liệu theo giờ/ngày | Backup job logs, storage destination |
| Software updater | Poll version hoặc download theo lịch | Signed binary, updater log, vendor endpoint |
| VPN keepalive | Duy trì trạng thái tunnel | Peer, SA/tunnel logs và protocol |
| Cloud/Kubernetes/mesh | Service probe và control-plane traffic | Pod/service identity, config, mesh logs |
| DNS cache refresh | Query gần TTL hoặc sau lỗi | Resolver log, answer, TTL, client cache |
| Broker reconnect | Client kết nối lại khi upstream lỗi | Broker log, timeout/retry policy |
| IoT/OT telemetry | Thiết bị gửi thông số theo lịch | Asset inventory, vendor protocol, owner |

Nên so một host với **baseline lịch sử và nhóm peer có cùng vai trò**. Agent trên laptop có thể gửi heartbeat khác agent trên server; lịch theo ca làm việc khác dịch vụ 24/7. Khi thay đổi phiên bản phần mềm hoặc cập nhật chính sách, baseline cũng cần được rà soát.

Không tạo allowlist vĩnh viễn chỉ từ hostname hay user agent có thể bị giả mạo. Bằng chứng loại trừ tốt hơn là **asset + process đã xác minh + endpoint có owner + lịch được quản lý**, kết hợp kiểm tra lại khi điều kiện thay đổi.

## 11. Các yếu tố làm méo chu kỳ và phân loại sai

| Vấn đề | Hệ quả | Cách xác minh |
| --- | --- | --- |
| Active timeout flow exporter | Nhiều record đều nhau từ một kết nối dài | Connection/session ID và config exporter |
| NAT/shared public IP | Nhiều host bị gộp thành một nguồn | NAT mapping, DHCP, thời gian |
| Proxy connection pooling | Nhiều request trong một upstream session | Proxy request logs và trace |
| HTTP/2, WebSocket, gRPC, QUIC | Có message lặp mà không có TCP SYN mới | Protocol-aware/app telemetry |
| Sampling hoặc capture loss | Missing events, interval tăng bội số | Counters, sampling rate, sensor logs |
| Retry/backoff do lỗi | Cụm các attempt gần nhau | App/TCP error, upstream status |
| Clock skew / ingestion delay | Thời điểm bị đảo hoặc tụ nhóm | Event time, ingest time, NTP |
| Sleep/wake, login/session | Chu kỳ chỉ tồn tại khi máy hoạt động | Endpoint power/auth logs |
| Pod restart/autoscaling | IP đổi nhưng cùng workload logic | Pod UID, deployment/instance history |
| DNS cache/DoH/DoT | Thiếu truy vấn rõ tên miền | Resolver/endpoint telemetry có quyền |
| TLS/SSH/IPsec encryption | Không đọc được application payload | Metadata và logs từ điểm giải mã hợp lệ |

Không thấy kết nối trong PCAP tại một sensor không chứng minh host không liên lạc: có thể sai interface, filter, phân đoạn, chiều traffic, packet drop hoặc tuyến mạng thay đổi. Khi log chỉ ở mức aggregate, kết luận nên giới hạn thành **mẫu lặp trong dữ liệu quan sát** thay vì nói chắc tiến trình phát heartbeat.

## 12. Kiểm chứng ứng viên với packet capture và log

### 12.1. Thu packet có giới hạn

Ở điểm quan sát được phép và với các địa chỉ minh họa:

~~~bash
sudo tcpdump -i eth0 -nn -s 160 -c 3000 \
  -w beacon-candidate.pcap \
  'host 10.10.4.22 and host 203.0.113.70'
~~~

Chọn interface và filter theo **địa chỉ thực tế tại điểm thu**: sau NAT, source có thể đổi; sau proxy, destination có thể là proxy thay vì origin. Tham số -s 160 giới hạn packet được ghi và có thể cắt trường cần xem; -c 3000 giới hạn số packet, không bảo đảm bao phủ đủ một chu kỳ dài. Cần ghi filter, thời gian, snaplen, counters và packet drops.

### 12.2. Kiểm tra SYN và thời điểm

~~~bash
tshark -r beacon-candidate.pcap \
  -Y 'tcp.flags.syn == 1 && tcp.flags.ack == 0' \
  -T fields \
  -e frame.time_epoch -e ip.src -e ip.dst \
  -e tcp.srcport -e tcp.dstport -e tcp.stream
~~~

**Cẩn trọng:** SYN retransmissions có thể bị đếm nhầm là connection mới. Đối chiếu TCP sequence/ACK, 5-tuple và session state. **UDP/QUIC không có TCP SYN**; heartbeat trong connection HTTP/2, gRPC hay WebSocket kéo dài cũng không tạo SYN mới. Với TLS, PCAP thông thường không đọc được URL/path hoặc body; nếu cần xem HTTP thì ưu tiên proxy/access logs được quản trị theo quy định.

### 12.3. Lập bảng ghép chứng cứ

1. **DNS:** QNAME, answers, TTL, resolver và mốc thời gian nếu có.
2. **Firewall/NAT:** original/translated 5-tuple, action, session start/end.
3. **Proxy/LB:** request time, host/route, status, upstream, request ID và connection pooling.
4. **EDR/host:** process identity, parent, signer, lịch chạy và sự kiện phát sinh.
5. **IDS/NDR:** sensor location, alert, rule version và packet/flow reference.

Những nguồn này chỉ cung cấp điều mà chúng thực sự quan sát. Ví dụ, DNS query không chứng minh HTTP request; WAF 403 không chứng minh backend nhận request; flow ACCEPT không bảo đảm ứng dụng xử lý thành công.

## 13. Tình huống minh họa: sáu kết nối cách nhau một phút

Hệ thống NDR đánh dấu máy **WS-042** có sáu connection TCP/443 tới **203.0.113.70** trong năm phút. Đây là địa chỉ thuộc dải dùng cho tài liệu, không phải IOC thật.

~~~text
10:00:00  WS-042 -> 203.0.113.70:443  attempt #1
10:01:00  WS-042 -> 203.0.113.70:443  attempt #2
10:02:01  WS-042 -> 203.0.113.70:443  attempt #3
10:03:00  WS-042 -> 203.0.113.70:443  attempt #4
10:04:00  WS-042 -> 203.0.113.70:443  attempt #5
10:05:00  WS-042 -> 203.0.113.70:443  attempt #6
~~~

**Xác nhận ban đầu:** hoạt động gần định kỳ tại sensor. **Chưa xác nhận:** malware, C2, domain gốc hay nội dung truyền trong TLS.

### 13.1. Đối chiếu với nguồn độc lập

| Nguồn | Kết quả giả định | Có thể kết luận |
| --- | --- | --- |
| DHCP/inventory | IP thuộc WS-042 trong thời gian đó | Ánh xạ host nguồn |
| Firewall/session | Sáu connection được cho phép | Firewall ghi nhận các phiên |
| DNS resolver | Truy vấn updates.example.test trước kết nối | Có query; cần kiểm tra answer trùng đích |
| Egress PCAP | Có TCP/TLS handshake | Packet đi qua điểm thu |
| EDR | Updater của một phần mềm doanh nghiệp tạo socket | Ngữ cảnh tiến trình |
| Scheduler/update log | Lịch kiểm tra phiên bản mỗi phút khi chạy test | Có giải thích hợp lệ |
| Software inventory | Executable và owner đã xác minh | Hỗ trợ phân loại bình thường |

Trường hợp trên có thể được hạ ưu tiên khi process, lịch, endpoint và asset role **đều phù hợp với cấu hình đã được kiểm chứng**. Chữ ký số hoặc tên domain quen thuộc một mình chưa đủ loại trừ mọi rủi ro.

### 13.2. Ví dụ cần ưu tiên cao hơn

Nếu chuỗi lặp xuất hiện sau alert thực thi file không rõ nguồn gốc, đi kèm hoạt động xác thực bất thường và endpoint không có owner, có cơ sở **mở rộng điều tra**: bảo toàn logs/PCAP, kiểm tra process lineage, account activity, dữ liệu được truy cập và những host có hành vi tương tự. Dù vậy, khẳng định "**C2 đã xác nhận**" vẫn cần bằng chứng về hành vi/đích phù hợp, không thể suy từ chu kỳ.

## 14. Khung đánh giá ưu tiên và chất lượng detection

| Nhóm đánh giá | Câu hỏi |
| --- | --- |
| Nhịp | Có đủ số interval và đủ thời gian để nhận biết quy luật? |
| Baseline | Khác với host cùng vai trò hoặc lịch sử chính nó? |
| Destination | Endpoint có owner và mục đích được giải thích? |
| Process/identity | Tiến trình và lịch có hợp lệ, có bất thường đồng thời? |
| Network/security | Firewall, IDS, DNS, WAF, VPN và EDR có chứng cứ hỗ trợ? |
| Data quality | Đã kiểm tra clock skew, NAT, sampling, flow timeout? |
| Tác động | Tài sản có quyền cao, zone nhạy cảm hoặc dữ liệu quan trọng? |

Một ứng viên CV thấp nhưng thuộc monitoring agent hợp lệ có thể ưu tiên thấp; một chuỗi ít đều hơn nhưng có nhiều bằng chứng endpoint/identity đáng nghi có thể cần xem ngay. Khi đưa detection vào SOC, cần đánh giá **coverage, false-positive rate, alert latency, số mẫu tối thiểu và drift theo loại tài sản** bằng dữ liệu có nhãn và review của người phân tích. Thay đổi nguồn log hoặc phiên bản exporter có thể làm rule phát hiện sai.

## 15. Bảo toàn chứng cứ và giới hạn kết luận

Trong hồ sơ vụ việc, lưu: raw event IDs, nguồn và sensor, cửa sổ UTC, mapping host/NAT, query và phiên bản rule, dữ liệu về sampling/dropped packets, phân tích đã thực hiện, kết quả EDR, các khoảng thiếu và đánh giá mức tin cậy. Luôn phân biệt **sự kiện gốc**, **bản sao phân tích** và **suy luận**.

Ví dụ manifest:

~~~yaml
case_id: INC-EXAMPLE-BEACON-042
asset_id: WS-042
window_utc:
  start: "2026-11-28T10:00:00Z"
  end: "2026-11-28T10:05:00Z"
candidate:
  destination: "203.0.113.70:443"
  event_type: connection_attempt
  event_count: 6
  mean_interval_seconds: 60
  classification: investigate
evidence:
  - firewall-session-export
  - endpoint-process-telemetry
  - pcap-egress
limitations:
  - "Không có HTTP payload do TLS mã hóa"
  - "Cần xác minh mapping DNS và process identity"
~~~

Có thể tính hash sau khi lưu bản gốc:

~~~bash
sha256sum beacon-candidate.pcap
~~~

Ghi hash với thời gian, người thu, thiết bị, filter, nơi lưu và lịch sử truy cập/chuyển giao (**chain of custody**). Hash chỉ hỗ trợ kiểm tra các byte có giống nhau khi đối chiếu, **không tự chứng minh dữ liệu gốc chính xác hoặc hoàn chỉnh**. PCAP có thể chứa token, payload và metadata nhạy cảm; cần giới hạn thu thập, phân quyền và retention phù hợp.

**Không suy diễn:** flow bytes không chứng minh dữ liệu mật đã bị đánh cắp; DNS query không chứng minh có session ứng dụng; IP public không định danh một người; TLS handshake không bảo đảm request thành công; không thấy gói tại sensor không chứng minh packet không tồn tại; CV thấp không bằng malware.

## 16. Checklist điều tra beaconing và periodic connection

- [ ] Đã xác định câu hỏi, cửa sổ UTC và nguồn phát hiện ứng viên.
- [ ] Đã định nghĩa event type: connection attempt, session, request, DNS query hoặc heartbeat.
- [ ] Đã ánh xạ asset đúng thời gian, bao gồm NAT/DHCP/pod UID/VPN nếu cần.
- [ ] Đã nhóm đích, protocol, port và sự kiện một cách nhất quán.
- [ ] Đã kiểm tra active flow timeout, deduplication, missing events, sampling và clock skew.
- [ ] Đã tính interval, median/mean, độ phân tán và volume trên số mẫu đủ dùng.
- [ ] Đã so nhiều cửa sổ thời gian, baseline và nhóm peer có vai trò tương đương.
- [ ] Đã phân biệt request/heartbeat trên kết nối giữ lâu với connection mới.
- [ ] Đã đối chiếu DNS, firewall, proxy, IDS/NDR, VPN và EDR phù hợp.
- [ ] Đã kiểm tra lịch job, monitoring, updater, backup, retry và dịch vụ hợp lệ.
- [ ] Đã đánh giá endpoint, process identity và các tín hiệu an ninh độc lập.
- [ ] Đã ghi rõ dữ kiện, giả thuyết, mức tin cậy, giới hạn và bước điều tra tiếp.
- [ ] Đã bảo toàn raw log/PCAP, hash, metadata và quyền truy cập theo chính sách.

Nhận diện **beaconing và periodic connection** bắt đầu từ các sự kiện theo thời gian, nhưng chỉ có giá trị pháp chứng khi hiểu rõ **ngữ nghĩa sự kiện**, kiểm tra độ đều trong bối cảnh lịch hoạt động và đối chiếu network telemetry với endpoint/identity. Phương pháp này giúp phát hiện luồng cần chú ý mà không biến mọi tác vụ định kỳ thành cảnh báo C2, đồng thời giữ đủ căn cứ để người khác kiểm chứng kết quả.
