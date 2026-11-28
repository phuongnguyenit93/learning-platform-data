# Availability, latency, throughput và error rate: Bốn tín hiệu cốt lõi trong giám sát mạng

## 1. Vì sao phải đo cùng lúc bốn tín hiệu?

Một dịch vụ có thể trả lời `200 OK` nhưng phải mất 12 giây; một đường truyền có thể đạt 1 Gbit/s trong một phép thử nhưng thường xuyên mất gói; một hệ thống giám sát có thể báo *up* trong khi người dùng ở một khu vực không phân giải được DNS. Đó là lý do **availability, latency, throughput và error rate** phải được đo cùng nhau, theo **đúng ranh giới trải nghiệm và mục tiêu vận hành**.

Trong chương **Giám sát mạng và telemetry** của module **SECURITY_NETWORK_SECURITY**, những tín hiệu này hỗ trợ cả vận hành và an ninh: nhận biết mạng phân đoạn hay firewall chặn nhầm, VPN/IDS/IPS gây độ trễ, DNS/TLS lỗi, cloud load balancer mất backend, hoặc một luồng lưu lượng bất thường làm suy giảm dịch vụ. Chúng cũng có thể là dấu hiệu của sự cố cấu hình, thay đổi tải, lỗi mạng, hoặc tấn công từ chối dịch vụ; **không thể kết luận nguyên nhân chỉ từ một biểu đồ**.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Định nghĩa bốn tín hiệu và nêu rõ **đơn vị đo, đối tượng đo, ranh giới đo và cửa sổ thời gian**.
2. Phân biệt **availability của endpoint**, *reachability* của đường mạng và *successful user journey*.
3. Phân tích latency **DNS, TCP/QUIC, TLS, request, server, network, queue** cùng sự khác biệt giữa trung bình và p95/p99.
4. Phân biệt **throughput**, **goodput**, packet rate, link utilization, bps/Bps và tác động của retransmission.
5. Thiết kế **error rate** với mẫu số phù hợp, phân loại transport/DNS/TLS/HTTP/app errors và không nhầm security deny với outage.
6. Tính **SLI, SLO, error budget**, xem burn rate và điều kiện cảnh báo theo mức tác động.
7. Chọn nguồn telemetry: **synthetic probes, passive metrics, logs, traces, NetFlow/IPFIX, packet captures và cloud flow logs**.
8. Xây metric dashboard/queries/alerts an toàn với **counters, gauges, histograms, PromQL**, có kiểm soát cardinality và missing data.
9. Thực hiện **positive/negative tests** cho cả dịch vụ hợp lệ và những luồng cố ý bị chặn do segmentation.
10. Viết runbook chẩn đoán vấn đề và case study theo bằng chứng thay vì suy đoán từ tương quan.

> **Phạm vi thực hành:** các địa chỉ như `192.0.2.10`, `198.51.100.20`, `203.0.113.10` và miền `*.example.test` dành cho ví dụ, không phải tài nguyên cần truy cập. Chỉ gửi probes hoặc lấy telemetry từ mạng, cluster và hệ thống được cấp phép. Không thử tải lưu lượng lớn, quét hàng loạt, tắt firewall hoặc thu packet chứa dữ liệu người khác để làm bài. Những công thức/query là ví dụ cần hiệu chỉnh theo nhãn, exporter và policy thực tế.

## 2. Mô hình đo lường: bốn tín hiệu không nói cùng một điều

| Tín hiệu | Câu hỏi chính | Biểu diễn thường gặp | Tình huống dễ đọc sai |
|---|---|---|---|
| **Availability** | Dịch vụ có thực hiện được chức năng cần thiết khi được yêu cầu không? | % thành công theo thời gian hoặc theo request | ICMP tới node vẫn OK nhưng API lỗi toàn bộ |
| **Latency** | Cần bao lâu để có kết quả, nhất là những request chậm nhất? | ms/s; p50, p95, p99; phân phối | Trung bình thấp nhưng 1% người dùng chờ rất lâu |
| **Throughput** | Mức dữ liệu hoặc công việc được hoàn thành mỗi đơn vị thời gian? | bit/s, B/s, packets/s, requests/s | 1 Gbit/s wire traffic nhưng goodput hữu ích thấp |
| **Error rate** | Bao nhiêu yêu cầu/phiên/packet thất bại theo định nghĩa đã chọn? | % hoặc lỗi/s, loss rate | HTTP 403 do policy đúng bị tính thành lỗi ứng dụng |

Một ví dụ giả định:

~~~text
System: api.example.test, đo từ client khu vực A trong 5 phút
Availability: 99.2% successful requests
p50 latency: 45 ms
p99 latency: 1,450 ms
HTTP 5xx error rate: 0.6%
Business throughput: 3,200 successful requests/s
Network egress: 720 Mbit/s
~~~

Những con số này **không thay thế lẫn nhau**. 99.2% request thành công có thể gồm nhiều request chậm không đáp ứng SLO; 720 Mbit/s không cho biết 3.200 RPS là nhiều hay ít nếu payload thay đổi. Phải biết **mẫu số, hướng traffic, thời gian, phân vùng, giao thức và phép đo từ đâu**.

### 2.1. Chọn ranh giới quan sát trước khi đặt metric

~~~mermaid
flowchart LR
    U["Client / user"] --> DNS["DNS resolver"]
    U --> LB["CDN / LB / WAF"]
    LB --> IN["Ingress / firewall"]
    IN --> API["Application Pod"]
    API --> DB["Database"]
    T["Telemetry"] -. "Probes, logs, metrics, traces và flows" .-> U
    T -. "Theo từng hop" .-> LB
    T -. "Theo từng hop" .-> API
    T -. "Theo từng hop" .-> DB
~~~

*Client-facing end-to-end availability* khác *backend availability*. Khi API trả `503` từ ingress vì không có endpoints, máy backend có thể vẫn chạy. Tương tự, người dùng có thể mất khả năng gọi service do DNS, VPN route, TLS hostname mismatch hoặc ZTNA policy, dù server process và Kubernetes Pod đều Ready.

### 2.2. Phân biệt quan sát và bằng chứng

- **Metric:** số liệu định lượng được lấy mẫu/tổng hợp, tốt cho xu hướng, SLO và alert.
- **Log:** sự kiện rời rạc như request status, DNS failure, firewall drop, authentication deny.
- **Trace:** đường đi qua nhiều services, duration của spans và propagation context.
- **Flow record:** thống kê kết nối/5-tuple, bytes/packets, source/destination và action tùy nguồn.
- **Packet capture:** gói thực tế tại một điểm, hữu ích khi cần chứng cứ protocol-level nhưng có chi phí, quyền riêng tư và độ nhạy cao.

**Không có một nguồn dữ liệu nào quan sát đầy đủ mọi hop.** Một reverse proxy có thể kết thúc TLS và tạo TCP connection mới, NAT làm thay IP/port, cùng một lỗi bị đếm ở client và gateway. Correlation phải dùng **UTC timestamps, request/trace ID, identities, policy revision và hướng đi**, không chỉ ghép theo IP.

## 3. Availability: tính sẵn sàng theo chức năng, không chỉ theo máy sống

Availability là tỷ lệ thời gian hoặc sự kiện mà **một chức năng được xem là phục vụ đúng yêu cầu**. Việc chọn định nghĩa này quan trọng hơn bản thân ký hiệu `%`.

### 3.1. Availability theo thời gian

Nếu ta xác định hệ thống có hai trạng thái *available* và *unavailable* theo từng khoảng:

\[
A_{\mathrm{time}}=\frac{T_{\mathrm{available}}}{T_{\mathrm{eligible}}}
=1-\frac{T_{\mathrm{unavailable}}}{T_{\mathrm{eligible}}}
\]

Trong đó, \(T_{\mathrm{eligible}}\) là tổng thời gian thuộc phạm vi đánh giá theo chính sách; không tự ý loại maintenance hoặc lỗi nhà cung cấp nếu SLO không cho loại. Nếu có khoảng **không quan sát được**, cần một quy tắc xử lý *unknown* và **coverage metric riêng** thay vì âm thầm tính là *up*.

### 3.2. Availability theo request

Khi có đủ request observations:

\[
A_{\mathrm{request}}=\frac{N_{\mathrm{eligible\ and\ successful}}}
{N_{\mathrm{eligible}}}
\]

Ví dụ: có 100.000 HTTP requests hợp lệ, 99.600 được xem là success theo tiêu chí nghiệp vụ, thì availability theo request là **99,6%**. Đây không nhất thiết trùng time availability: 5 phút outage trong thời kỳ cao điểm có thể gây nhiều request fail hơn 5 phút lúc không có traffic.

### 3.3. Thành công nghĩa là gì?

Một số mức kiểm tra:

| Phép đo | Khi nào hữu ích | Không thể chứng minh |
|---|---|---|
| ICMP echo tới node | Host/network path trả ICMP theo chính sách | HTTP API, TLS, database hay user login hoạt động |
| TCP connect tới port | Có listener hoặc endpoint chấp nhận kết nối | TLS certificate đúng, HTTP trả nội dung đúng |
| TLS handshake với hostname validation | Chứng minh peer TLS được xác minh trên đường test | App/business function thành công |
| HTTP `/health` hoặc `/ready` | Một endpoint health đáp ứng đúng status/body | Tính đúng của chức năng người dùng |
| Synthetic business transaction | User journey có thể hoàn thành từ location thử | Tất cả users/regions/roles đều thành công |
| Real-user/real-request SLI | Trải nghiệm của traffic được đo thực tế | Regions không có traffic hoặc failures trước instrumentation |

Với dịch vụ DNS, một check “UDP/53 reachable” không chứng minh **tên quan trọng được giải đúng và phản hồi hợp lệ**. Với VPN, tunnel daemon chạy không chứng minh **luồng user→service** vẫn được phép theo routing/firewall.

### 3.4. Phân biệt lệnh cấm hợp lệ với sự cố

Khi NetworkPolicy chặn Pod không có quyền hoặc ZTNA từ chối người dùng chưa xác thực, đó có thể là **thành công của chính sách bảo mật**, không phải service outage. SLI phải xác định **tập eligible clients/requests**:

~~~text
Eligible:
  authenticated business user với entitlement hợp lệ
  source network/identity được phép
  supported API/hostname/version

Excluded from application-availability denominator by policy:
  malicious scans, wrong credentials, unauthorized endpoint requests
  intentionally denied network paths

Still monitor separately:
  authentication failures, firewall denies, policy anomalies
~~~

Không loại bỏ 4xx/timeout chỉ vì muốn SLO đẹp. Nếu người dùng được phép lại bị `403` do policy regression, đó **là lỗi sẵn sàng trong customer journey**. Phân loại phải dựa danh tính, trường hợp nghiệp vụ và policy version chứ không chỉ HTTP code.

## 4. SLI, SLO, SLA và error budget

**Service Level Indicator (SLI)** là số đo như tỷ lệ successful requests, latency under threshold hoặc DNS lookup success. **Service Level Objective (SLO)** là mục tiêu định lượng của một SLI trong thời gian xác định. **Service Level Agreement (SLA)** là cam kết hợp đồng, có thể liên quan hậu quả vi phạm; không đồng nghĩa với SLO nội bộ.

### 4.1. Ví dụ availability SLO

~~~text
Service: api.example.test
SLI: eligible HTTPS GET requests thành công và trả kết quả hợp lệ
SLO: >= 99.9% trong rolling 30 ngày
Window: 30 ngày, theo UTC
Scope: production, những regions/clients được định nghĩa
Unknown-data handling: đo riêng + quy tắc đã công bố
~~~

Nếu xét thời gian 30 ngày (30 × 24 × 60 = 43.200 phút), budget downtime tương đương cho 99,9% là:

\[
B_{\mathrm{time}}=(1-0{,}999)\times43.200
=43{,}2\ \text{phút}.
\]

Với **99,95%**, ngân sách tương đương là **21,6 phút/30 ngày**. Đây là *time-based budget* khi các khoảng up/down được định nghĩa phù hợp, **không phải số phút outage chắc chắn hợp lệ với request-based SLO**.

### 4.2. Error budget theo requests

Với SLO 99,9% và 2.000.000 eligible requests trong 30 ngày:

\[
B_{\mathrm{requests}}=(1-0{,}999)\times 2.000.000=2.000
\]

Tức tối đa **2.000 failed eligible requests** trước khi dùng hết request-based budget, theo định nghĩa success đã chọn. Nếu chỉ có 10.000 eligible requests, budget là 10 thất bại. **Không đổi trực tiếp số request lỗi thành thời gian outage** khi traffic không đều.

### 4.3. Burn rate

Burn rate giúp diễn giải tốc độ dùng error budget:

\[
\mathrm{burn\ rate}=\frac{\mathrm{observed\ eligible\ error\ fraction}}
{1-\mathrm{SLO\ target}}
\]

Nếu SLO 99,9% cho phép error fraction 0,1%, nhưng 1 giờ gần nhất ghi nhận **1% eligible requests thất bại**, burn rate là **10×**. Với traffic request-weighted đều, rate này sẽ tiêu tốn budget nhanh gấp mười lần tốc độ trung bình cho phép. Burn rate **không tự chứng minh** số phút downtime.

Multi-window burn-rate alert thường kết hợp **cửa sổ ngắn** để phát hiện nhanh và **cửa sổ dài** để hạn chế nhiễu. Chọn thresholds theo SLO, tổn thất budget, traffic volume và khả năng phản ứng; tránh sao chép ngưỡng của dịch vụ khác khi chưa mô phỏng.

## 5. Latency: phải định nghĩa thời điểm bắt đầu và kết thúc

**Latency** là thời gian từ một mốc bắt đầu đến một mốc kết thúc. Một request web có thể bao gồm:

~~~text
DNS resolution
  + connection establishment (TCP hoặc QUIC)
  + TLS handshake (khi áp dụng)
  + request network transit
  + queueing tại gateway/backend
  + server processing + downstream dependencies
  + response transmission
  + browser/client processing (nếu thuộc SLI)
~~~

Khi dùng kết nối có sẵn, **DNS/TCP/TLS setup có thể không diễn ra trên mỗi request**; không cộng các thành phần trên thành một phương trình cứng cho mọi transaction. Các timer có thể overlap (HTTP/2 multiplexing, TLS handshake, redirects), và retries có thể tạo thêm requests trên đường.

### 5.1. Những mốc đo nên phân biệt

| Chỉ số latency | Phạm vi | Nguyên nhân có thể |
|---|---|---|
| **DNS lookup time** | Request tới resolver, chờ câu trả lời | DNS timeout, cache miss, upstream resolver |
| **TCP connect time** | SYN→kết nối thiết lập theo client | Loss, RTT, firewall drop, overloaded accept queue |
| **TLS handshake time** | Thiết lập session TLS, cert verification | RTT, TLS policy, CA/cert issue, load |
| **Time To First Byte (TTFB)** | Từ request mốc đo đến byte phản hồi đầu | Network, queue, backend processing |
| **Total request duration** | Mốc client request đến hoàn thành response | Payload size, server time, retries, congestion |
| **Proxy upstream response time** | Thời gian proxy tương tác với backend theo sản phẩm | Pod/service/network path, backend latency |
| **Application handler duration** | Vào handler đến khi xử lý theo metric | CPU, locks, DB, queue và dependencies |
| **TCP RTT** | Round-trip transport estimate | Path delay, queueing, measurement method |

**TTFB không luôn bằng server processing time.** Client có thể chịu DNS, TLS, TCP, network RTT hoặc proxy buffering trước khi nhận byte đầu.

### 5.2. End-to-end vs per-hop

~~~mermaid
flowchart LR
    C["Client probe"] --> L["Load balancer"]
    L --> W["WAF / Ingress"]
    W --> A["API Pod"]
    A --> D["DB"]
    C -. "End-to-end duration" .-> A
    L -. "LB latency metric" .-> W
    W -. "Upstream duration" .-> A
    A -. "DB span" .-> D
~~~

Không cộng thẳng mọi span duration trong distributed tracing: các spans có thể chạy **song song/nested**, và timer bắt đầu/kết thúc tại những điểm khác nhau. Với việc xác định bottleneck, so **critical path, wait/queue time và response size** trên cùng request ID.

## 6. Trung bình, percentiles và phân phối độ trễ

Với latency, **trung bình** có thể che giấu trải nghiệm rất chậm của một nhóm người dùng. Giả sử 990 request trả sau 30 ms và 10 request trả sau 3.000 ms. Trung bình xấp xỉ **59,7 ms**, nhưng nhóm 1% chịu độ trễ rất lớn.

### 6.1. Các chỉ số thống kê

- **p50 (median):** khoảng một nửa quan sát có latency không vượt giá trị này; cho biết trải nghiệm điển hình.
- **p95:** khoảng 95% quan sát không vượt ngưỡng p95; phản ánh tail rộng hơn.
- **p99:** khoảng 99% quan sát không vượt ngưỡng p99; hữu ích khi slow tail ảnh hưởng khách hàng, nhưng **khó ước lượng** ở lưu lượng rất thấp.
- **Max:** độ trễ lớn nhất quan sát được, có thể rất nhạy với outliers và lỗi đo.
- **Histogram:** số quan sát trong các buckets, hỗ trợ tỷ lệ dưới ngưỡng, phân phối và ước lượng quantile.
- **Average:** tổng duration chia số quan sát; tốt cho tải tổng hợp nhưng không thay thế tail.

Percentile luôn có ý nghĩa theo **mẫu và cửa sổ thời gian**. “p99 = 200 ms” mà không ghi đo ở client/ingress/backend, traffic nào, từ vùng nào và lúc nào là thông tin chưa đủ.

### 6.2. Cẩn thận khi tổng hợp percentiles

Không lấy **trung bình p99 của hai Pod** để suy p99 toàn dịch vụ. Một Pod có 10 requests và một Pod có 10.000 requests; trung bình hai p99 làm sai trọng số. Với Prometheus histogram buckets cùng ngữ nghĩa, có thể **cộng buckets** trước rồi ước lượng quantile cho toàn bộ traffic. Với client-side quantiles không có raw distribution/histogram compatible, việc tổng hợp phải theo cấu trúc metric và khả năng triển khai.

### 6.3. Tail amplification

Một user journey gọi **5 services nối tiếp** có thể bị chậm khi bất kỳ service nào có tail latency cao. Với lời gọi song song, latency của tổng request thường phụ thuộc **nhánh chậm nhất**, không phải tổng trung bình. Retries và hedging có thể giảm latency một số tình huống nhưng làm tăng traffic, cạnh tranh tài nguyên và gây tác dụng ngược khi hệ thống đã quá tải.

~~~mermaid
flowchart TD
    REQ["User request"] --> A["Service A"]
    A --> B["Service B"]
    A --> C["Service C"]
    B --> JOIN["Kết quả chờ nhánh chậm"]
    C --> JOIN
    JOIN --> RESP["Response"]
~~~

### 6.4. Coordinated omission và timeout

Một bộ đo chỉ phát request mới **sau khi response trước hoàn thành** có thể bỏ sót các khoảng thời gian bị đình trệ, khiến latency under load **trông đẹp hơn thực tế**. Cần chọn load/latency methodology có tính đến **arrival schedule**, concurrency, timeouts và những requests chưa hoàn tất. Các timeout phải được thống kê cả ở **latency SLI** (nếu định nghĩa cho phép) và **error/availability SLI**, tránh biến request chậm vô hạn thành quan sát bị bỏ qua.

## 7. Throughput: lưu lượng, công việc hoàn thành và giới hạn năng lực

**Throughput** mô tả khối lượng thông tin hoặc đơn vị công việc hoàn thành trong một khoảng thời gian. Nó có thể là:

- **Bits per second (bit/s, Kbit/s, Mbit/s, Gbit/s)** ở interface/link.
- **Bytes per second (B/s, MiB/s)** ở application, storage hoặc network.
- **Packets per second (pps)** ở interface, firewall hoặc packet-processing appliance.
- **Requests/transactions per second (RPS/TPS)** ở HTTP/API.
- **Successful business operations/s** như đơn hàng được xác nhận.

### 7.1. Throughput khác bandwidth/capacity

**Bandwidth hoặc link capacity** là năng lực danh định của đường truyền theo công nghệ/cấu hình. Throughput là **lưu lượng thực tế** đi qua hoặc được xử lý. Link có capacity 1 Gbit/s không có nghĩa ứng dụng luôn đạt 1 Gbit/s vì còn RTT, TCP congestion control, loss, CPU, crypto, queue, firewall throughput và payload size.

\[
\mathrm{Average\ throughput}_{bps}
=\frac{8\times\Delta \mathrm{bytes}}{\Delta t}
\]

Ví dụ một interface ghi nhận **600 MiB** được truyền trong 60 giây, với đơn vị MiB = \(2^{20}\) bytes:

\[
\frac{600\times2^{20}\times 8}{60}
\approx83{,}9\ \mathrm{Mbit/s}.
\]

Đổi đơn vị phải nói rõ: **Mb (megabit)** khác **MB (megabyte)**; trong hệ thập phân 1 MB/s tương đương 8 Mbit/s. Không trộn MiB với MB khi tính capacity/billing.

### 7.2. Throughput và goodput

**Throughput on-wire** có thể gồm Ethernet/IP/TCP headers, handshake, retransmission, keepalive và protocol overhead. **Goodput** thường là **payload hữu ích được ứng dụng nhận thành công mỗi đơn vị thời gian**, không gồm overhead/retransmitted data.

~~~text
Link-level observed throughput: 600 Mbit/s
TCP retransmissions + protocol overhead: significant
Successful payload goodput: 420 Mbit/s

Meaning:
  Không kết luận 600 Mbit/s đều là dữ liệu hữu ích.
  Cần xem retransmission, MTU, MSS, loss, cwnd và application bytes.
~~~

Hai con số giả định không phải một công thức có thể trừ tuyến tính mọi overhead. Với encrypted traffic, application goodput cần instrumentation ở application/proxy phù hợp; **flow logs** không tự tách data hữu ích khỏi overhead một cách chính xác.

### 7.3. Link utilization và saturation

\[
\mathrm{Utilization}(\%)=
\frac{\mathrm{Observed\ bps}}{\mathrm{Effective\ link\ capacity\ bps}}\times100.
\]

Với egress **900 Mbit/s** trên interface **1 Gbit/s**, trung bình utilization là 90%. Tuy vậy, một cửa sổ 5 phút trung bình 50% có thể che **microbursts** gần 100% trong vài mili giây gây queueing/drops. Capacity thực có thể bị giới hạn ở **virtual NIC, QoS policer, security appliance, cloud bandwidth tier hoặc CPU**, không chỉ tốc độ cổng vật lý.

### 7.4. Packet rate quan trọng với firewall/IDS/IPS

Hai nguồn traffic cùng 500 Mbit/s có thể có packet rate rất khác nếu kích cỡ gói khác nhau. Thiết bị firewall, IDS/IPS, DDoS protection và packet processors có giới hạn **pps, connections/s, concurrent sessions, TLS handshakes/s**. Một lượng lớn gói nhỏ có thể làm CPU/conntrack kiệt sức dù chỉ chiếm một phần capacity tính theo bit/s.

### 7.5. Tăng traffic chưa chắc là tấn công

Traffic tăng do backup, batch processing, software rollout, video, cache warming hoặc khách hàng hợp lệ. Tương tự, throughput giảm có thể do **tự động scale đúng, nhu cầu người dùng thấp, policy chặn nguồn độc hại, client congestion hoặc upstream bottleneck**. Cần so với baseline theo thời gian, inventory và các signals khác; không gắn nhãn DDoS từ một spike đơn lẻ.

## 8. Error rate: số lỗi phải có mẫu số và ngữ nghĩa đúng

Error rate là tỷ lệ **sự kiện không đạt tiêu chí** trên **tập sự kiện đủ điều kiện**:

\[
\mathrm{Error\ rate}=\frac{N_{\mathrm{errors}}}{N_{\mathrm{eligible\ events}}}\times100\%.
\]

Trong hệ thống mạng, “error” có nhiều lớp:

| Lớp | Ví dụ | Cách diễn giải |
|---|---|---|
| **DNS** | Lookup timeout, `SERVFAIL`, câu trả lời sai theo kỳ vọng | Resolver/service discovery có vấn đề; `NXDOMAIN` có thể hợp lệ với tên không tồn tại |
| **Transport** | TCP connection refused/reset, connect timeout, QUIC connection failure | Có thể do listener, ACL, route, loss hoặc quá tải |
| **TLS** | Handshake fail, invalid SAN/chain, trust/cipher mismatch | Tách khỏi TCP reachability; một số rejects là security policy đúng |
| **HTTP** | 5xx, timeout, proxy 502/503/504 | Thường gợi ý server/upstream failure, nhưng cần xác minh nguồn status |
| **HTTP 4xx** | 400, 401, 403, 404, 429 | Có thể là client mistake, unauthorized request hoặc rate limit hoạt động đúng |
| **Application** | Valid HTTP 200 nhưng payload hoặc giao dịch sai | Cần business correctness check |
| **Interface** | RX/TX errors, discards/drops, CRC, overruns theo driver | Không đồng nhất với số HTTP request fail |
| **Packet loss** | Gói không nhận được trong probe/methodology | Không phải mọi loss đều phá ứng dụng do transport recovery |
| **Security enforcement** | Firewall deny, IDS/IPS block, WAF reject | Có thể là **đúng chính sách** hoặc **false positive** gây outage |

### 8.1. 4xx có phải lỗi SLO?

Không có đáp án cố định. `401 Unauthorized` do user sai mật khẩu có thể **ngoài** availability SLI; `403` tới tài khoản đã có quyền nhưng bị policy cấu hình sai có thể **là lỗi nghiêm trọng**. `429 Too Many Requests` có thể là rate limiting hợp lệ theo hợp đồng, hoặc là dấu hiệu capacity không đủ cho khách hàng được phép.

**Định nghĩa success/error bằng contract của chức năng**; tài liệu SLI phải nêu rõ treatment của 401/403/404/429, client disconnect, timeout, retries và requests bị WAF/CNI deny.

### 8.2. Retries có thể làm metric khác nhau

Một business transaction có thể gửi 3 HTTP attempts: lần 1 timeout, lần 2 trả 503, lần 3 thành công. Khi đó:

- **Attempt-level error rate:** 2/3 attempts fail.
- **User transaction availability:** 1/1 transaction có kết quả thành công, có thể vượt latency SLO.
- **Network/load footprint:** 3 attempts tăng RPS/traffic tới backend.

Đừng trộn attempt metrics ở ingress/proxy với completed-user-journey metrics mà không đặt nhãn khác nhau.

### 8.3. Error rate và traffic volume

1 lỗi trong 2 requests là **50%**, nhưng chỉ có hai quan sát. 500 lỗi trong 100.000 requests là **0,5%** với tác động lớn hơn về số lượng. Alert nên xét cả **tỷ lệ, minimum samples/traffic, duration và ảnh hưởng SLO**, tránh pager storm khi traffic rất thấp.

### 8.4. Loss rate không phải HTTP error rate

Nếu ICMP probe mất 10/100 echo replies, loss trong **phép thử đó** là 10%, không suy mọi TCP flow đều mất 10% hoặc API error 10%. ICMP có thể bị rate-limit/filtered trong khi TCP hoạt động bình thường; ngược lại path TCP/443 có thể bị chặn khi ICMP tới host vẫn phản hồi.

## 9. Bốn tín hiệu liên quan nhau thế nào?

Một hệ thống thường biểu lộ nhiều tín hiệu đồng thời, nhưng **tương quan không chứng minh nhân quả**.

~~~mermaid
flowchart TD
    LOAD["Offered load / traffic pattern"] --> QUEUE["Queue/CPU/conntrack pressure"]
    QUEUE --> LAT["Tail latency tăng"]
    QUEUE --> DROP["Packet drops / timeouts"]
    DROP --> ERR["Error rate tăng"]
    ERR --> AV["Availability SLI giảm"]
    QUEUE --> THR["Throughput có thể đạt ngưỡng rồi giảm"]
    RETRY["Retries"] --> LOAD
    ERR --> RETRY
~~~

Các kiểu sự kiện:

| Quan sát kết hợp | Giả thuyết cần kiểm tra | Không được suy ngay |
|---|---|---|
| Throughput ↑, latency ↑, drops ↑ | Saturation/queueing hoặc traffic spike | Chắc chắn bị DDoS |
| Throughput ↓, error rate ↑, DNS errors ↑ | DNS outage hay resolver policy | Backend server chắc chắn chết |
| Interface bps thấp, RPS cao, p99 ↑ | Gói nhỏ/pps limit, backend CPU, lock contention | Link 1 Gbit/s dư nên không thể nghẽn |
| Availability ↓ chỉ tại một region | Regional LB/DNS/route/VPN issue | Toàn bộ global service down |
| 403 tăng sau firewall/mesh policy change | Authorization regression hoặc scanners bị chặn | Mọi 403 đều là lỗi |
| TLS handshake fail ↑, TCP connect OK | Certificate/CA/SNI/TLS config issue | Firewall chắc chắn là nguyên nhân |
| p99 ↑, avg latency ổn | Tail/queue hoặc subgroup bị ảnh hưởng | Dịch vụ vẫn tốt vì trung bình thấp |
| Business throughput ↑, network bps ↓ | Payload nhỏ, compression/cache hoặc đường xử lý thay | Mất dữ liệu chắc chắn |

### 9.1. Hãy đặt câu hỏi “điểm quan sát ở đâu?”

Nếu **firewall drops** tăng và **backend request error rate** không tăng, có thể firewall đang chặn traffic không hợp lệ **trước khi tới app**. Nếu **client availability** giảm nhưng ingress requests không đổi, có thể lỗi xảy ra **trước ingress**: DNS, ISP, TLS, CDN hoặc đường vào. Khi so logs cần phân biệt event bị chặn với request hợp lệ không tới được.

### 9.2. Quy trình cô lập nguyên nhân

1. Xác nhận **user-visible impact**, nguồn đo và thời gian.
2. So **số eligible requests** với throughput, RPS và request outcomes.
3. Tách **client region, protocol IPv4/IPv6, hostname, service, route, deployment revision**.
4. Tìm điểm đầu tiên mà success/error/latency thay đổi dọc request path.
5. Đối chiếu load, queue, CPU/memory, conntrack, drops, retransmission, DNS/TLS.
6. Xem thay đổi gần đó: firewall/IDS policy, rollout, BGP/route, DNS records, certificate, VPN và scaling.
7. Thử **positive control** và **negative control** có phép trên đường cụ thể.
8. Khắc phục có rollback, sau đó kiểm tra hồi quy bốn tín hiệu.

## 10. RED, USE và Golden Signals trong network operations

Các phương pháp quan sát thường gặp:

| Phương pháp | Chữ viết tắt | Phù hợp |
|---|---|---|
| **RED** | Rate, Errors, Duration | Request-serving services: ingress, API, DNS RPC, gateway |
| **USE** | Utilization, Saturation, Errors | Resources: NIC, CPU, disk, conntrack, VPN/firewall appliances |
| **Golden Signals** | Latency, Traffic, Errors, Saturation | Tổng quan service health và capacity |
| **SLI/SLO** | Số đo chất lượng và mục tiêu | Quyết định khi nào cần cảnh báo, ưu tiên sửa lỗi |

Tương quan với yêu cầu bài:

- **Availability:** outcome-based service success/uptime SLI.
- **Latency:** RED Duration/Golden Signal latency.
- **Throughput:** RED Rate, traffic và resource throughput.
- **Error rate:** RED Errors, network discard/loss, app failure theo ngữ nghĩa.
- **Saturation:** tín hiệu hỗ trợ chẩn đoán quan trọng dù không nằm trong bốn tên gọi của tiêu đề.

**Availability và error rate có thể là hai cách nhìn gần nhau** nếu SLI success định nghĩa hoàn toàn bằng lỗi HTTP; nhưng chúng có thể khác đáng kể khi có latency SLO, no-traffic windows, requests blocked before instrumentation, business validation hoặc request retries.

## 11. Thiết kế telemetry: active probes và passive observations

### 11.1. Active monitoring (synthetic)

Synthetic monitor chủ động tạo request hoặc probe từ **điểm đo được quản lý**, ví dụ:

- DNS lookup một record được kiểm soát và kiểm tra value/TTL hoặc response phù hợp.
- TCP connect/HTTPS handshake có hostname/SAN verification.
- HTTP GET tới endpoint lab, kiểm tra status, body marker hoặc business response.
- Gọi một **synthetic transaction không phá dữ liệu**, có tài khoản kiểm thử riêng.
- Kiểm tra VPN/Zero Trust path **từ identity được phép** tới đích chính xác.

Ưu điểm: hoạt động **ngay cả khi không có user traffic**, phát hiện vấn đề trước ingress hoặc ở một region. Giới hạn: probes có thể không đại diện mọi OS, ISP, thiết bị, tenant, tài khoản hoặc transaction; chính probe cũng có thể bị lỗi.

### 11.2. Passive monitoring

Passive monitoring quan sát traffic và hệ thống hoạt động thật:

- Reverse proxy/API counters, latency histograms và request logs.
- Host NIC byte/packet counters, link errors/discards.
- TCP retransmission, reset, RTT estimates, connection tracking utilization.
- DNS resolver query metrics, response codes và latency.
- Flow records của VPC/VNet, firewall, NetFlow/IPFIX, VPN gateway.
- Traces của application/service mesh và ingress/controller logs.

Ưu điểm: phản ánh tải thật và có khả năng phân rã theo service/user journey. Giới hạn: có **blind spots khi request không tới instrumented component**, sampling, rate limit, NAT/proxy và dữ liệu nhạy cảm.

### 11.3. Vì sao kết hợp hai loại?

~~~mermaid
flowchart LR
    SYN["Synthetic probes: client-side"] --> A["Availability + DNS/TLS/connect/total latency"]
    USER["Real users / clients"] --> R["Real-user / request observations"]
    R --> API["Ingress/API metrics + traces"]
    NET["NIC, firewall, flow logs"] --> FLOW["Throughput/loss/deny/route evidence"]
    A --> CORR["Correlation theo time, host, region, route"]
    API --> CORR
    FLOW --> CORR
~~~

**Dịch vụ không có request không chắc là healthy.** Passive API success rate có thể không có mẫu số khi tất cả clients không kết nối được do DNS/global outage. Synthetic probes từ nhiều network vantage points giúp phát hiện *absence of arrivals*.

### 11.4. Multi-vantage probes

Chọn điểm đo đại diện cho:

1. User Internet ở các regions/ISPs cần bảo đảm.
2. User mạng nội bộ qua proxy/VPN/Zero Trust.
3. Pod trong cluster gọi Service/Pod IP theo chính sách cho phép.
4. Service-to-service traffic qua mesh hoặc private endpoints.
5. Điểm OOB/management network nếu là tài nguyên quản trị.

Mỗi vantage có **identity và network path riêng**. Một máy giám sát trong VPC gọi thành công API qua private address không chứng minh Internet client gọi thành công public hostname.

### 11.5. Giám sát chính giám sát

Một collector bị down không phải bằng chứng service bị down hoặc service đang up. Theo dõi:

- Scrape success và freshness/timestamp của sample.
- Probe scheduler có chạy và có tạo đủ probes không?
- Exporter, agent, OTLP collector queue, dropped batches và backpressure.
- Time synchronization, clock skew, out-of-order data.
- Metrics backend ingestion rate, remote-write queue, dropped series.
- Traces/log collection coverage và sampling rate.

**Phân biệt `DOWN`, `UP` và `UNKNOWN/NO DATA`** theo contract, hiển thị coverage metric và alert riêng cho mất quan sát. Không tự động chuyển thiếu sample thành `0 lỗi`.

## 12. Các loại metric: counter, gauge, histogram, summary

Để xây dashboard/alerts chính xác, phải hiểu **kiểu dữ liệu và đơn vị đo**.

| Loại metric | Ví dụ | Cách dùng | Bẫy |
|---|---|---|---|
| **Counter** | `http_requests_total`, `node_network_transmit_bytes_total` | `rate()`/`increase()` theo window | Counter reset khi process restart, không lấy chênh lệch naïve |
| **Gauge** | Active connections, CPU usage, queue depth, link state | Giá trị hiện tại hoặc max/avg theo thời gian | Gauge có thể thiếu/stale; không luôn cộng được |
| **Classic histogram** | `..._bucket`, `..._sum`, `..._count` | Percentiles/tỷ lệ dưới threshold từ buckets | Buckets phải cùng schema/units, `le` phải được giữ |
| **Summary** | Client-calculated quantiles và sum/count | Quantile tại một instance theo window | Không cộng/average quantiles giữa instances |
| **Native histogram** | Histogram mẫu kiểu native nếu exporter/backend hỗ trợ | Quantile và aggregation theo semantics native | Yêu cầu version/support, không áp dụng trực tiếp công thức classic bucket |

### 12.1. Counter và `rate()`

Counter như `node_network_receive_bytes_total` tăng theo tổng bytes nhận từ khi process/device metric khởi tạo. Muốn biết **bytes/s trung bình** trong cửa sổ 5 phút, dùng `rate(counter[5m])`, không dùng raw counter làm throughput.

Nếu exporter restart, counter có thể về 0; `rate()` xử lý **counter resets** theo chuỗi mẫu trong cửa sổ một cách phù hợp. Tuy vậy, nếu scrape bị thiếu, counter bị đổi labels hoặc có quá ít samples, kết quả vẫn có thể không đáng tin.

### 12.2. Classic histogram tích lũy

Với HTTP duration metric, buckets:

~~~text
http_request_duration_seconds_bucket{le="0.05"}  350
http_request_duration_seconds_bucket{le="0.10"}  700
http_request_duration_seconds_bucket{le="0.25"}  940
http_request_duration_seconds_bucket{le="0.50"}  985
http_request_duration_seconds_bucket{le="+Inf"}  1000
~~~

Đây là **số đếm tích lũy** (các sample đã quan sát cho đến thời điểm hiện tại), không phải một histogram có chính xác 350 requests ở 0–50 ms và 700 requests ở 50–100 ms. Giá trị `le=0.10` bao gồm cả requests dưới 50 ms.

Trong ví dụ này 940/1000 requests có duration **≤250 ms**. Nếu tiêu chí latency SLO là `≤250 ms`, có thể dùng **bucket success fraction** thay vì chỉ xem p95 ước lượng.

### 12.3. Histogram quantile là ước lượng

`histogram_quantile(0.99, ...)` trên classic histograms trả **ước lượng dựa trên bucket boundaries và interpolation**, không nhất thiết chính là p99 raw samples. Nếu buckets quá thô, p99 có thể sai lệch đáng kể. Chọn buckets xung quanh **latency SLO threshold** và tail range quan trọng.

### 12.4. Cardinality và nhãn

Các labels an toàn tương đối:

~~~text
service, environment, cluster, region, route_template,
http_method, status_class, interface, protocol, zone
~~~

Các labels **không nên đưa trực tiếp vào metric series** nếu giá trị gần như duy nhất:

~~~text
raw_url_path với order-id, request_id, trace_id,
client_ip, user_id, session_id, JWT subject không bucket,
src_ip/dst_ip 5-tuple ở mọi flow
~~~

Các giá trị độc nhất làm **cardinality bùng nổ**, gây tốn bộ nhớ/ingestion và đôi khi làm hệ thống giám sát mất khả năng quan sát chính lúc sự cố. Lưu chi tiết nhiều chiều ở **logs/traces/flow storage có quota và quyền truy cập**, còn metrics nên tổng hợp theo route template hoặc số chiều vừa đủ.

## 13. Ví dụ PromQL cho availability, latency, throughput và error rate

Các ví dụ dưới đây giả định một Prometheus-compatible backend với metric names/labels **minh họa**. Trước khi áp dụng, phải xem exporter thật: có hệ dùng `code`, hệ khác `status`, `status_code` hoặc `response_code`. Không phải mọi cluster có `http_requests_total` hoặc classic histograms theo những tên này.

### 13.1. HTTP request rate (requests/s)

~~~promql
sum(rate(http_requests_total{job="api"}[5m]))
~~~

Tính **số HTTP attempts/s** mà API metric instrumented đã đếm trong 5 phút. Nếu client đã timeout trước khi request tới API thì request **không có mặt trong counter**; cần client/synthetic SLI.

### 13.2. HTTP 5xx error rate

~~~promql
sum(rate(http_requests_total{job="api",code=~"5.."}[5m]))
/
sum(rate(http_requests_total{job="api"}[5m]))
~~~

Cho tỷ lệ 5xx **trên requests do API đếm**, không phải tất cả business transaction failures hay firewall denies. Nếu trong 5 phút **không có request** hoặc metric 5xx chưa từng được phát hành, biểu thức có thể **không trả sample/NaN** thay vì 0; phải xử lý missing numerator/denominator theo rule rõ ràng và monitor traffic/coverage riêng.

Một cách xử lý số 5xx chưa xuất hiện với global aggregation là:

~~~promql
(
  sum(rate(http_requests_total{job="api",code=~"5.."}[5m]))
  or vector(0)
)
/
sum(rate(http_requests_total{job="api"}[5m]))
~~~

**Chỉ numerator được zero-fill** khi series chưa tồn tại; denominator vẫn phải có traffic thực. Không zero-fill cả denominator để biến no-traffic thành error rate 0 một cách giả tạo.

### 13.3. p99 latency từ classic histogram

~~~promql
histogram_quantile(
  0.99,
  sum by (le) (
    rate(http_request_duration_seconds_bucket{job="api"}[5m])
  )
)
~~~

Trả **p99 ước lượng bằng giây** cho tất cả API observations khớp selector. Phải chắc chắn buckets được thiết kế theo cùng observation/unit và `le` còn sau aggregation. Nếu muốn p99 theo `region` hoặc `route`, giữ thêm nhãn đó trong `sum by (le, region, route)` và kiểm soát cardinality.

### 13.4. Tỷ lệ HTTP requests đáp ứng latency objective

Giả sử histogram có bucket `le="0.25"`:

~~~promql
sum(rate(http_request_duration_seconds_bucket{job="api",le="0.25"}[5m]))
/
sum(rate(http_request_duration_seconds_count{job="api"}[5m]))
~~~

Đây là **fraction of observed requests with duration ≤250 ms**, rất hợp cho latency SLI. Nếu histogram chỉ đo server handler, nó không chứng minh end-to-end client latency. Định nghĩa success phải quyết định xem 5xx/timeout được xét ở latency objective hay error objective như thế nào.

### 13.5. Network throughput theo interface

~~~promql
8 * rate(node_network_receive_bytes_total{
  job="node",device="eth0"
}[5m])
~~~

Trả nhận vào interface `eth0` theo **bit/s** trong cửa sổ 5 phút. Với nhiều node/instances, có thể aggregate theo node/cluster nhưng không cộng lẫn những cổng **hai đầu cùng một đường** nếu mục tiêu là đo lưu lượng thực; làm vậy có thể **đếm đôi**.

~~~promql
8 * sum by (instance) (
  rate(node_network_transmit_bytes_total{
    job="node",device="eth0"
  }[5m])
)
~~~

Metric của NIC có thể có nhiều interfaces ảo/tunnel/loopback. Nếu cộng mọi interface, cùng một packet có thể được đếm nhiều lần khi qua bridge/VPN/tunnel. Định nghĩa **điểm đo và hướng RX/TX** trước khi tổng hợp.

### 13.6. Interface receive error/discard rate

~~~promql
rate(node_network_receive_errs_total{
  job="node",device="eth0"
}[5m])
~~~

~~~promql
rate(node_network_receive_drop_total{
  job="node",device="eth0"
}[5m])
~~~

Đơn vị là **events/s**, không phải “% HTTP requests”. Tên/ý nghĩa `errs`/`drop` phụ thuộc driver/exporter. Muốn ratio như dropped packets / received packets, phải xác minh packet counter cùng interface/direction, cách exporter tính, và mẫu số khác 0.

### 13.7. Synthetic availability

Với blackbox exporter có `probe_success` bằng 1/0 cho probes đã được thu:

~~~promql
avg_over_time(probe_success{
  job="https-probe",instance="https://api.example.test/health"
}[1h])
~~~

Giá trị minh họa này là **fraction of collected probe samples** thành công trong 1 giờ, **không tự là time-weighted uptime** nếu probes không đều/mất lịch. Phải theo dõi **probe count/scheduler coverage** riêng và không coi một series mất hoàn toàn là “all good”.

### 13.8. Mất exporter và mất telemetry

~~~promql
up{job="node"} == 0
~~~

`up` phản ánh scrape của Prometheus với target đó (0 khi scrape thất bại, 1 khi thành công), **không phản ánh trực tiếp service business up/down**. Khi một target/metric **biến mất khỏi service discovery**, có thể không còn series có `up=0`; dùng `absent()`/inventory-based expectations hoặc một availability rule phù hợp để phát hiện *missing targets*.

### 13.9. Query không thay định nghĩa SLO

Các biểu thức ở trên chỉ là **cách tính dữ liệu đo được**. Một SLO thực tế còn cần quy định cửa sổ thời gian, nguồn traffic, scope tenants, exclusions có lý do, data completeness, sample volume và ownership. Đừng dùng một query 5 phút chung cho mọi báo cáo availability 30 ngày mà không xác định aggregation và error-budget accounting.

## 14. Telemetry từ tầng mạng: interface, TCP/QUIC, firewall và flows

### 14.1. Thiết bị và interfaces

Một network dashboard nên tách **uplink, downlink, physical/virtual NICs, tunnels và service traffic**. Bộ tín hiệu thường hữu ích:

| Tín hiệu | Dữ liệu cần lấy | Có thể gợi ý |
|---|---|---|
| Link admin/oper state | Up/down, carrier transitions | Interface thật mất kết nối hoặc link flap |
| RX/TX bytes | Delta theo thời gian, theo hướng | Throughput bps và thay đổi tải |
| RX/TX packets | Packet counters | pps, packet size distribution khi kết hợp bytes |
| RX errors, CRC/FCS, overruns | Interface/driver diagnostics | Lỗi vật lý, buffer hoặc driver tùy loại |
| RX/TX drops/discards | Drop counters với vendor semantics | Congestion, buffer pressure, QoS hoặc policy |
| Queue depth/queue drops | Switch/router/NIC queues | Microbursts/saturation, tail latency |
| Port speed/duplex/autoneg | Effective link settings | Mismatch hoặc capacity limit |
| Link utilization | bps / effective capacity | Capacity planning nhưng không đủ tìm microbursts |
| CPU/memory/conntrack/session table | Firewall/VPN/load balancer appliances | Resource saturation trước khi throughput chạm line rate |

SNMP counters như **`ifHCInOctets`/`ifHCOutOctets`** có thể hữu ích cho high-capacity interfaces; phải dùng loại counter/wrap handling phù hợp, interface identity ổn định và poll interval. **Tên `ifIndex` có thể thay sau reboot/reconfigure** tùy thiết bị, nên map interface description/identity trong inventory thay vì coi ifIndex cố định mãi.

### 14.2. TCP transport

Tín hiệu TCP cần xem:

- **Estimated RTT/RTT variance** ở phía sender/receiver theo công cụ hỗ trợ.
- **Retransmitted segments** và timeout/recovery events.
- **Connection establishments, resets, refused/failed connects** theo điểm quan sát.
- **Congestion window / receive window**, advertised window và app stalls nếu có.
- **SYN backlog, accept queue, conntrack state count/exhaustion**.
- **MSS/MTU/Path MTU Discovery**, ECN khi được bật và hỗ trợ.

**Retransmission tăng không tự chứng minh packet loss ở một thiết bị cụ thể.** Nó có thể do loss, out-of-order delivery, path change hoặc đặc điểm sender/receiver; cần kết hợp per-hop queue/errors, packet traces được phép và topology.

### 14.3. UDP/QUIC

Với UDP, không có TCP retransmission counters để dùng nguyên. **QUIC** chạy trên UDP nhưng có loss recovery và RTT/congestion telemetry của chính implementation. Một UDP packet drop trên firewall chưa nói lên user transaction bị lỗi; cần protocol/client metrics. Khi CDN hoặc API dùng HTTP/3, so sánh **HTTP/2/TCP và HTTP/3/QUIC** để tránh một chỉ số chung che vấn đề theo protocol.

### 14.4. Firewall, IDS/IPS và VPN

| Nguồn | Metrics / events | Tình huống liên quan 4 tín hiệu |
|---|---|---|
| **Firewall** | Sessions active/new per sec, CPU, drops/denies, bytes, state table | Availability/latency sụt do conntrack hoặc policy |
| **IDS/IPS** | Inspect throughput, queue, signature hits, drops và mode inline/out-of-band | False positive có thể làm lỗi hợp lệ khi inline |
| **VPN gateway** | Tunnel up, authenticated peers, bytes, rekeys, SA expiry, RTT/loss | Tunnel up vẫn chưa chứng minh app path hoạt động |
| **ZTNA proxy** | Authorized sessions, decision latency, denies, connector health | Login success khác được phép tới target |
| **WAF/CDN** | Edge request rate, 4xx/5xx, challenges, cache hit, origin errors | Đường từ client có thể fail trước backend |
| **Load balancer** | Healthy targets, active connections, backend latency, 5xx by origin | 502/503 có thể phát sinh tại LB/ingress |

**Security-deny metric phải có chính sách nhãn rõ.** `drop` do deny đúng khác `drop` do congestion, malformed packets hay false positive. Với IDS chạy **out-of-band**, một cảnh báo detection không đồng nghĩa IDS đã chặn traffic.

### 14.5. Flow telemetry: NetFlow/IPFIX/VPC logs

Các records thường mô tả **source/destination IP, protocol/ports, bytes/packets, start/end time và đôi khi action**. Chúng tốt cho top talkers, east–west, unusual egress và điều tra tuyến, nhưng:

- Có thể **sample**, aggregate theo window hoặc delay ingest.
- NAT có thể làm source/destination thay đổi qua từng hop.
- Một flow record **không chứng minh HTTP request thành công**.
- Cloud flow logs không luôn ghi **mọi packet hoặc mọi deny**, tùy provider/filter/aggregation.
- Nếu chỉ nhìn post-NAT egress, nhiều Pods/users có thể cùng một public source IP.
- Flow records có thể chứa network metadata nhạy cảm, cần data governance.

Trong security monitoring, kết hợp **flow identity mapping** (Pod UID, VM ID, security group, workload identity) với **request/identity logs**, không coi mỗi IP là một user duy nhất.

## 15. DNS, TLS, VPN, segmentation và cloud: đo end-to-end đúng phạm vi

### 15.1. DNS có thể là single point of failure trước HTTP

Một domain có thể có nhiều tầng:

~~~text
Client resolver -> Recursive DNS -> Authoritative DNS -> answer
Client -> Returned CDN/LB IP -> TLS -> API
~~~

Theo dõi **resolution success, correctness, latency, SERVFAIL, timeout, cache effectiveness và phân vùng region**. `NXDOMAIN` cho tên không tồn tại là kết quả hợp lệ theo hợp đồng DNS, không phải lúc nào cũng lỗi. Với DNSSEC, một validation failure có thể dẫn tới SERVFAIL và ảnh hưởng availability dù DNS server vẫn trả lời.

### 15.2. TLS authentication failure cần hiển thị riêng

TLS có thể thất bại do certificate expired, SAN không đúng, chain/CA trust, client certificate trong mTLS, SNI, version/cipher mismatch hoặc clock skew. Monitoring nên phân biệt:

1. TCP/QUIC connection thiết lập được?
2. TLS handshake thành công theo **client validation**?
3. Certificate identity khớp **hostname dự kiến**?
4. HTTP/app request có hoàn thành và đúng nội dung?

**Không dùng `curl -k` hay tắt hostname verification trong synthetic availability production** chỉ để metric báo thành công. Làm vậy che hỏng trust boundary và khiến “up” không phản ánh trải nghiệm của client bảo mật đúng.

### 15.3. VPN up chưa có nghĩa dịch vụ reachable

Một tunnel báo connected có thể vẫn bị route/MTU/firewall/identity policy chặn đến ứng dụng. Nên đặt **probe hợp lệ từ đúng VPN/Zero Trust identity tới đúng private service**, không dùng `ping tunnel gateway` làm kết luận toàn bộ ứng dụng sẵn sàng. Network ACL deny đối với nguồn không có quyền là **kết quả mong muốn** và cần test riêng.

### 15.4. Cloud networking và đa vùng

Cloud network metrics có thể đến từ:

- VPC/VNet flow logs, cloud firewalls/security groups.
- Internal/public load balancers, NAT gateways, transit gateways.
- Kubernetes CNI, ingress, service mesh và egress gateways.
- Private endpoints, DNS resolvers và managed service metrics.

**Một AZ/region healthy không chứng minh toàn hệ thống healthy**. Phải đo failover route từ client, DNS TTL/cache effects, LB traffic weights, cross-zone bandwidth/egress, và sự nhất quán của policy cho IPv4/IPv6.

### 15.5. NetworkPolicy/ACL allow và deny là hai tests khác nhau

~~~mermaid
flowchart TD
    A["Approved app / user"] --> G["Gateway / CNI / Firewall"]
    B["Unapproved source"] --> G
    G -->| "ALLOW theo policy" | S["Backend Service"]
    G -->| "DENY đúng chính sách" | D["Policy decision logs"]
    S --> T["Availability + latency + errors"]
~~~

Trong kiểm tra segmentation, cần cả:

- **Positive:** nguồn có quyền → dịch vụ chạy đúng, đáp ứng SLO.
- **Negative:** nguồn không có quyền → bị chặn **bởi đúng enforcement point**.

Nếu backend tắt, cả hai sources đều fail: điều đó **không** chứng minh firewall đang enforce đúng. Nếu firewall đang chặn đúng 100 cuộc dò trái phép, không nên tính chúng thành 100 user-visible errors.

## 16. Sampling, aggregation, clock và dữ liệu thiếu

### 16.1. Sampling có thể gây hiểu sai

Giả sử packet flow collector lấy mẫu **1 trên 1.000 packets** hoặc tracing chỉ lưu 10% requests. Có thể xem xu hướng trên tập mẫu, nhưng không được tự coi sample count bằng **tổng số sự kiện thực** mà không hiểu sampling algorithm, weight và bias.

Với tail latency, sample ngẫu nhiên nhỏ có thể **bỏ lỡ những request rất chậm**. Với rare security denies, sampling có thể không thu đủ bằng chứng sự kiện cần forensic. Quyết định sampling phải phù hợp SLO measurement và data-retention policy.

### 16.2. Aggregation theo region, tenant và protocol

Ví dụ:

~~~text
Region A: 990/1000 successful requests = 99.0%
Region B: 99900/100000 successful requests = 99.9%

Request-weighted global success:
  (990 + 99900) / (1000 + 100000)
  = 100890 / 101000 ~= 99.891%
~~~

Trung bình số học **(99,0% + 99,9%)/2 = 99,45%** không phải request-weighted global availability. Nhưng global aggregate cũng có thể che region A đang dưới SLO. Nên hiển thị **từng slice quan trọng và global view**, không dùng một trung bình để xóa ảnh hưởng của nhóm nhỏ.

### 16.3. Thời gian và đồng bộ

Nguồn log/probe/metric có thể ghi UTC, timezone local hoặc clock drift. Một trace có các spans trên nhiều hosts với clock skew có thể trông như response xảy ra trước request. Quy trình tương quan cần:

- UTC normalized timestamps và data-source offset.
- NTP/clock synchronization theo hạ tầng cho phép.
- Ingest timestamp và event timestamp phân biệt rõ.
- Các cửa sổ `5m`, `1h`, `30d` ghi đúng semantics.
- Thận trọng với delays của flow logs, collector queues và eventual consistency.

### 16.4. Data completeness là một chỉ số riêng

Ví dụ đang có 10 probes dự kiến/phút nhưng chỉ có 2 samples/phút do scheduler lỗi. Nếu 2 probes đều thành công, `avg(probe_success)=100%` **không đủ bằng chứng** rằng service đạt availability. Dashboard nên có:

~~~text
Probe expected count per minute: 10
Probe collected count per minute: 2
Probe collection coverage: 20%
Probe success fraction of collected: 100%
Status of service SLI: INCONCLUSIVE / unknown per policy
Telemetry health: FAIL
~~~

Tách **service degradation** và **observability degradation** thành alert độc lập, vì cả hai đều ảnh hưởng khả năng vận hành.

## 17. Thiết kế dashboard theo người xem và quyết định vận hành

Một dashboard tốt phải trả lời **“có vấn đề không, ở đâu, tác động tới ai và nên làm gì tiếp?”**; không chỉ nhồi biểu đồ CPU, bytes và status codes.

### 17.1. Dashboard tổng quan service health

| Panel | Biểu diễn | Câu hỏi |
|---|---|---|
| **Availability SLI** | Success fraction 5m/1h/30d + coverage | User traffic và synthetic journeys có đang phục vụ? |
| **Latency** | p50, p95, p99 + share under SLO threshold | Tail latency ở region/route nào vượt mục tiêu? |
| **Throughput** | Eligible RPS, successful RPS, bps, pps | Tải đang tăng hay bị giảm do lỗi? |
| **Error rate** | 5xx fraction, transport/TLS/DNS failures | Lỗi phát sinh từ layer nào? |
| **Saturation** | NIC utilization, queue drops, CPU, connection tables | Có bottleneck tài nguyên không? |
| **Traffic slices** | Region, tenant, service, IPv4/IPv6, protocol | Nhóm nào chịu tác động? |
| **Recent changes** | Deploy, firewall/NetworkPolicy, DNS, cert, route | Sự cố có trùng thời điểm thay đổi nào? |
| **Telemetry health** | Probe coverage, scrape up, collector lag | Dữ liệu có đáng tin và đủ mới? |

### 17.2. Dashboard của network/security operator

Thêm:

- Interface utilization, pps và discards theo **device/interface/zone**.
- Firewall **allow/deny** tách theo rule/intent, session table pressure.
- IDS/IPS **detect vs block** phân biệt; signature alert rates và false-positive investigation.
- NAT gateway throughput/connections/port exhaustion indicators theo provider.
- VPN tunnels up, rekeys, bytes, RTT/loss tới **approved application endpoint**.
- CNI/NetworkPolicy denies theo **workload identity/namespace** khi hệ thống có khả năng thu.
- WAF/rate limiting và origin vs edge error rates.
- Top talkers/top destinations với **cardinality/PII limits**, không phơi raw user identifiers.

### 17.3. Dashboard cho service owner

Service owner cần success rate, p95/p99, retries/timeouts, dependency latency, error code classes và user-visible impact. Không bắt buộc mọi kỹ sư ứng dụng phải thấy **tất cả firewall logs chứa IP khách hàng**, TLS secrets metadata hoặc mạng quản trị. Chia sẻ dashboards theo **least-privilege data access**.

### 17.4. Không dùng màu xanh thay cho chính sách

Một dashboard có thể xanh vì:

- Probes chỉ đi qua một region khỏe mạnh.
- Requests bị chặn trước ingress nên API không thấy lỗi.
- Exporter bị mất dữ liệu và query tự zero-fill.
- WAF đã chặn bot đúng nhưng user hợp lệ ở một tenant bị ảnh hưởng.
- `status=200` nhưng response body sai.
- Latency trung bình OK nhưng p99 vượt threshold nghiêm trọng.

Mỗi panel chính nên có **liên kết hoặc mô tả SLI definition, nguồn dữ liệu, sample volume và data freshness**. Các màu/threshold là phương tiện trình bày, không phải bảo đảm chất lượng.

## 18. Alerts: cảnh báo theo tác động, không chỉ theo một ngưỡng thô

### 18.1. Một alert có khả năng hành động cần gì?

Một cảnh báo nên chỉ rõ:

1. **Dịch vụ hoặc vùng bị ảnh hưởng**, không chỉ host vô danh.
2. **Triệu chứng user-facing** hoặc rủi ro SLO/budget.
3. **Thời gian/window và severity**, có ngưỡng noise control.
4. **Evidence/links** tới dashboard, metrics, logs, traces và change history.
5. **Owner, escalation và runbook**, có rollback/mitigation khi được phê duyệt.
6. **Data completeness**, không gửi “service OK” khi giám sát mất mẫu.

### 18.2. Ví dụ cảnh báo 5xx ratio trong lab

~~~yaml
# MẪU PROMETHEUS ALERT RULE; chưa qua kiểm thử trong hạ tầng thật.
# Metric names/labels job, code và traffic threshold phải xác minh.
groups:
  - name: example-api-alerts
    rules:
      - alert: ApiHigh5xxRatio
        expr: |
          (
            (
              sum(rate(http_requests_total{job="api",code=~"5.."}[5m]))
              or vector(0)
            )
            /
            sum(rate(http_requests_total{job="api"}[5m]))
          ) > 0.02
          and
          sum(increase(http_requests_total{job="api"}[5m])) > 200
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "API 5xx ratio cao trong cửa sổ 5 phút"
          description: "Kiểm tra client impact, backend health, ingress, recent changes."
~~~

Điều kiện traffic **`>200 requests trong 5m`** chỉ là ví dụ. Nếu API cực ít traffic, muốn có cảnh báo chính xác có thể cần **synthetic checks hoặc per-transaction alerts** thay vì ngưỡng sample lớn. Rule này cũng **không thay thế burn-rate alerts** cho SLO dài hạn và không giám sát errors xảy ra trước API instrumentation.

### 18.3. Burn-rate alert cho error budget

Giả sử request-based SLO **99,9%**. Cho error fraction của một window là \(e\), burn rate \(e/0{,}001\). Có thể thiết kế một **multi-window strategy**:

~~~text
Example goal:
  Long window: 1h hoặc 6h phát hiện budget burn bền vững.
  Short window: 5m hoặc 30m xác nhận tình trạng còn tiếp diễn.

Trigger:
  Long-window burn > approved threshold
  AND short-window burn > matching threshold
  AND đủ sample/coverage

Owner:
  Service team / on-call with verified runbook
~~~

Không có một cặp ngưỡng chuẩn đúng mọi dịch vụ; policy phải dựa **SLO target, cửa sổ 30 ngày, urgency, traffic pattern và noise tolerance**. Một metric 5xx thấp có thể vẫn kích hoạt burn-rate nghiêm trọng nếu SLO rất cao.

### 18.4. Mất quan sát cũng cần cảnh báo

Nếu scrape target fail (`up=0`), synthetic probes không chạy hoặc OTLP collector bị mất batch, dashboard có thể đánh giá SLI không đủ bằng chứng. Cần alert **telemetry outage** riêng, không hạ mức `0 error rate` mặc định. Khi rule tính tỷ lệ trả no data, thể hiện **UNKNOWN** và kiểm tra health của collector/probe/scrape.

### 18.5. Alert tuning tránh gây incident fatigue

- `for` duration để tránh báo mỗi spike ngắn không đáng hành động.
- Có **minimum traffic/sample** hoặc synthetic evidence.
- Có de-duplication, grouping theo service/region, inhibition khi upstream root cause đã rõ.
- Tránh gửi 100 alerts khi cùng một DNS resolver lỗi làm nhiều services fail.
- Cảnh báo **user impact** ưu tiên hơn mọi CPU spike không ảnh hưởng.
- Có security-specific alert cho **IPS false positives** hoặc policy denies đối với nguồn hợp lệ.
- Phân biệt **information vs warning vs paging**, có owner và follow-up.

### 18.6. Khi nào không alert theo link utilization?

Một link 75% utilization trung bình có thể ổn; link 40% trung bình nhưng có microbursts/queue drops có thể gây p99 latency kém. Alert trên **utilization + queue/drop + latency + error/SLO impact** đáng tin hơn ngưỡng bandwidth đơn lẻ. Với capacity planning, có thể xem percentiles theo ngày/tuần, forecast và việc phân phối traffic giữa multiple links.

## 19. Lab an toàn: đo HTTP/TLS và liên hệ với telemetry mạng

Lab này **không tạo synthetic load mạnh**. Nó chỉ sử dụng một endpoint HTTPS thử nghiệm mà bạn quản lý (ví dụ `https://api.lab.example.test/health`) và các lệnh quan sát **chỉ đọc** trên host Linux lab. Nếu hostname/IP ví dụ không tồn tại, không chạy lệnh nguyên mẫu và không coi lỗi đó là một kết quả network test.

### 19.1. Mục tiêu

1. Đo DNS, TCP connect, TLS handshake, TTFB và total HTTP time.
2. Xác thực certificate hostname; không dùng `--insecure` hay bỏ CA verification.
3. Phân biệt HTTP status với transport error.
4. So metric client với ingress/API latency và NIC bytes/pps theo thời gian.
5. Phân tích một route được phép và một route bị cấm theo network policy **trong lab riêng có phê duyệt**, không quét port hay firewall.

### 19.2. Một request `curl` có giới hạn

~~~bash
# CHỈ chạy sau khi thay tên host bằng endpoint HTTPS lab được sở hữu.
# Lệnh gửi một request thật; không sửa network config.
curl --silent --show-error \
  --output /dev/null \
  --connect-timeout 3 \
  --max-time 10 \
  --write-out \
  'code=%{http_code} dns=%{time_namelookup}s tcp=%{time_connect}s tls=%{time_appconnect}s ttfb=%{time_starttransfer}s total=%{time_total}s remote=%{remote_ip}\n' \
  https://api.lab.example.test/health
~~~

**Những mốc này thường là elapsed time tính từ lúc request bắt đầu**, không phải các duration độc lập có thể cộng nguyên xi. Ví dụ `time_connect` là mốc hoàn thành connect tương ứng trong chuỗi của curl, `time_appconnect` là mốc hoàn thành SSL/TLS connection; trên đường có proxy, HTTP/2 multiplexing hoặc connection reuse, cách diễn giải cần xét chính request.

Để lấy thời gian **riêng của một chặng**, có thể xét hiệu số giữa các mốc khi chúng xảy ra tuần tự trong trường hợp test cụ thể, ví dụ `time_appconnect - time_connect`, nhưng không coi công thức đó là latency TLS đúng trong mọi protocol/connection context.

### 19.3. Kiểm tra certificate identity

~~~bash
# CHỈ trên endpoint lab. Lệnh mở một TLS kết nối và thoát.
openssl s_client \
  -connect api.lab.example.test:443 \
  -servername api.lab.example.test \
  -verify_hostname api.lab.example.test \
  -verify_return_error \
  -brief < /dev/null
~~~

`-verify_hostname` kiểm tra hostname được chỉ định so với certificate theo OpenSSL implementation; `-verify_return_error` giúp dừng/ghi thất bại khi validation không thành công. Với private PKI cần CA trust/bundle **được phê duyệt**, không bỏ TLS verification chỉ để lấy số latency thành công.

### 19.4. Quan sát host interface counters

~~~bash
# Chỉ đọc trên Linux VM lab có iproute2.
ip -s link show
ip -br address
ip route

# Chỉ đọc summary TCP sockets; không sửa network state.
ss -s
~~~

Ghi lại **timestamp trước/sau**, cùng device name, RX/TX bytes/packets/errors/drops. Vì counters bao gồm **tất cả traffic trên interface**, một lần curl ngắn khó làm thay đổi đáng kể nếu host đang tải. Muốn so exact flow phải dùng instrumentation/flow telemetry được phép, không suy từ NIC aggregate của host multi-tenant.

### 19.5. Kiểm tra protocol path, có điều kiện

~~~bash
# Chỉ khi được duyệt đo một hostname cụ thể trong lab.
# Một DNS query có thể đi tới resolver đã cấu hình trong máy lab.
dig +time=2 +tries=1 api.lab.example.test A
dig +time=2 +tries=1 api.lab.example.test AAAA
~~~

Đọc **rcode, answer, TTL, latency** theo resolver. Nếu `AAAA` không tồn tại trong thiết kế IPv4-only, đó có thể là kết quả hợp lệ. Không ép mọi record thiếu thành `DNS failure` mà bỏ DNS contract.

### 19.6. Ghi kết quả theo layer

~~~yaml
experiment_id: METRICS-HTTP-LAB-01
environment: controlled-test-endpoint
time_utc: pending
source:
  region: lab-region-a
  identity: authorized-test-client
  network_path: lab-internet-or-private
destination:
  hostname: api.lab.example.test
  protocol: HTTPS
  path: /health
observations:
  dns_seconds: pending
  tcp_connect_seconds: pending
  tls_handshake_milestone_seconds: pending
  ttfb_seconds: pending
  total_seconds: pending
  http_status: pending
  certificate_validation: pending
  nic_rx_tx_delta_bytes: pending
  backend_handler_duration: pending
  ingress_request_id: pending
conclusion: pending-correlation
~~~

**Không điền những dữ liệu chưa đo bằng giá trị suy đoán.** Xác minh request IDs, timestamps, source vantage và label mapping khi ghép client telemetry với server metrics.

### 19.7. Bài thử negative-path đúng cách

Nếu đã có một firewall/NetworkPolicy lab chặn `unapproved-client → internal-api`, tiến hành kiểm thử **có quyền**:

- Dùng **approved-client** gọi cùng endpoint: API health/response OK.
- Dùng **unapproved-client** gọi endpoint: bị deny.
- Thu **firewall/CNI deny log** cho source/target đó và timestamp.
- Không gọi kết quả timeout là PASS nếu không biết nó bị policy chặn hay vì service down.
- Không đưa unauthorized probes vào availability SLI của eligible application users.

### 19.8. Kết quả kỳ vọng từ lab

Lab giúp khẳng định **cách đo và phân biệt các lớp lỗi**, không tự tạo “baseline 20 ms” áp dụng production. Một DNS/TLS error là lỗi thực cho endpoint thử, nhưng chỉ đại diện **vantage, thời điểm và protocol** đã được test.

## 20. Ma trận 40 trường hợp kiểm thử bốn tín hiệu và telemetry

Các test sau là **thiết kế cho môi trường được cấp phép**, không phải kết quả đã chạy. Chúng giúp kiểm chứng **độ đúng của phép đo**, không chỉ service availability; mỗi test phải nêu rõ source vantage, đường đi, window, expected success/error và evidence.

| Test ID | Tình huống / mục tiêu | Dữ liệu và phép thử | Kỳ vọng |
|---|---|---|---|
| **AVL-01** | Probe tới service healthy | Synthetic HTTPS với hostname validation | Success đúng contract |
| **AVL-02** | Backend app down nhưng node ping OK | Lab app health và ICMP so sánh | App availability fail dù ICMP up |
| **AVL-03** | DNS lỗi trước ingress | DNS/probe client; ingress request counter | Client fail, ingress có thể không ghi request |
| **AVL-04** | Một region mất route | Multi-region synthetic probes | Region lỗi được thấy dù global traffic vẫn cao |
| **AVL-05** | Eligible user bị policy deny | Identity-aware test sau policy change | User-visible availability fail đúng ngữ nghĩa |
| **AVL-06** | Unauthorized source bị deny đúng | NetworkPolicy/firewall negative control | Không đưa deny hợp lệ vào eligible-user denominator |
| **AVL-07** | No traffic / no data | Tắt probe scheduler **chỉ trong lab** hoặc mô phỏng data | UNKNOWN/coverage alert, không tự UP |
| **LAT-01** | DNS latency tăng | Resolver metrics + client curl/dig | Xác định DNS timing rõ |
| **LAT-02** | TLS handshake chậm | TLS milestone + edge/server metrics | Tách TLS khỏi app processing |
| **LAT-03** | p50 bình thường nhưng p99 cao | Histogram và client timings | Tail latency được cảnh báo |
| **LAT-04** | p99 toàn service | Aggregate compatible buckets trước `histogram_quantile` | Không average p99 của Pods |
| **LAT-05** | App handler nhanh, response chậm | Client total vs ingress upstream vs payload | Phân biệt network/proxy/transfer |
| **LAT-06** | Thao tác timeout sau threshold | Synthetic request có max-time | Timeout được ghi trong error/availability |
| **LAT-07** | L7 route/region có tail riêng | Labels route template/region, tracing | Slice bị ảnh hưởng không bị aggregate che |
| **THR-01** | Interface RX throughput | `rate(bytes_total[window]) × 8` | bit/s đúng hướng và đơn vị |
| **THR-02** | Bytes counter reset | Exporter restart trong lab/trace mẫu | `rate` không tạo spike âm giả |
| **THR-03** | Throughput vs goodput | On-wire counters + app delivered bytes | Không coi retransmissions là payload hữu ích |
| **THR-04** | NIC bps và requests/s | Cùng window, response payload sizes | Không suy RPS từ bps thiếu payload distribution |
| **THR-05** | Packet-rate saturation | pps + conntrack/CPU/queue metrics | Thấy overload dù bandwidth chưa đầy |
| **THR-06** | Microbursts | Short-window queue drops vs 5m averages | Không bỏ qua drops do trung bình thấp |
| **THR-07** | Double counting tunnel/bridge | So per-interface topology và aggregate | Không cộng hai lần cùng flow ở nhiều interfaces |
| **ERR-01** | HTTP 5xx numerator/denominator | Request counter theo status/total | Ratio đúng và sample volume rõ |
| **ERR-02** | 401/403 do policy hợp lệ | Security logs + request eligibility | Không tự tính như app outage |
| **ERR-03** | User hợp lệ bị 403 do regression | Positive auth test + policy revision | Count vào user-facing failure SLI |
| **ERR-04** | Client retries | Attempts và logical transactions | Không trộn request errors với journey success |
| **ERR-05** | TCP reset vs TLS failure | Transport/TLS logs với đúng source | Xác định lớp phát sinh lỗi |
| **ERR-06** | DNS NXDOMAIN vs SERVFAIL | Query hợp lệ/không tồn tại trong lab | DNS contract xác định thành công |
| **ERR-07** | Error rate 50% từ hai requests | Traffic threshold/coverage | Không page dựa mẫu quá nhỏ không có bối cảnh |
| **SEC-01** | IDS alert nhưng không inline block | Sensor mode + packet/path logs | Detection khác enforcement |
| **SEC-02** | IPS chặn source hợp lệ | Positive control + rule log | False positive được phát hiện |
| **SEC-03** | VPN tunnel up nhưng API unreachable | App synthetic từ approved VPN identity | Không suy VPN up = service available |
| **SEC-04** | WAF block tăng theo scan | WAF actions + app eligible traffic | Không coi toàn bộ denied bots là service errors |
| **SEC-05** | Firewall conntrack exhaustion | Active sessions, new connections/s, drops | Phân biệt saturation và policy deny |
| **SEC-06** | IPv6 path bypass hoặc lỗi | IPv4/IPv6 reachability/policy tests | Hai stacks có cùng policy intent |
| **SEC-07** | Unauthorized Pod gọi DB | Positive/negative CNI policy test | Deny do đúng PEP, backend healthy |
| **OBS-01** | Prometheus scrape fail | `up`, expected-target inventory | Mất telemetry được phát hiện |
| **OBS-02** | Probe coverage thấp | Expected vs collected probes | UNKNOWN, không hiển thị giả 100% |
| **OBS-03** | Metric high cardinality | Label audit/test ingestion budget | Tránh raw user_id/trace_id metrics |
| **OBS-04** | Flow log sampling | Sample configuration và packet/flow evidence | Không coi sample là toàn bộ lưu lượng |
| **OBS-05** | Đồng bộ timestamps cross hops | UTC request ID/trace correlation | Không suy sai thứ tự do clock skew |

### 20.1. PASS / FAIL / INCONCLUSIVE

**PASS:** nguồn đo và định nghĩa hợp lệ, dữ liệu đủ, kết quả khớp kỳ vọng **có bằng chứng từ đúng enforcement/observation point**. Ví dụ một client hợp lệ truy cập API thành công, một Pod không có quyền bị NetworkPolicy từ chối và log cho biết chính rule đã deny.

**FAIL:** một sự kiện user-facing fail nhưng báo healthy; phân loại sai 403, mất dữ liệu đo mà dashboard tự hiện 0 lỗi, dùng bytes counter sai đơn vị; hoặc một đường unauthorized được phép mặc dù policy yêu cầu deny.

**INCONCLUSIVE:** endpoint không tồn tại, test dùng DNS sai, target down, không có đủ samples/coverage, thiếu trace/request mapping hoặc test từ nguồn không có quyền nhưng lại bị chặn ở một lớp khác với lớp đang cần chứng minh.

### 20.2. Mẫu test evidence

~~~yaml
test_id: LAT-03
environment: authorized-monitoring-lab
time_utc: pending
service: api.lab.example.test
vantage: client-region-a
observation_window: 5m
protocol: HTTPS
eligibility: authenticated-read-only-health-test
expected:
  latency_metric: end-to-end
  percentile: p99
  threshold_ms: 500
  sample_coverage: sufficient-for-policy
evidence_required:
  - synthetic-request-timings
  - certificate-validation-result
  - request-count-and-timeout-count
  - app-or-ingress-histogram-buckets
  - request-id-time-correlation
result: pending-execution
~~~

Không ghi password, token, session cookie hoặc nội dung người dùng vào evidence. **Tài liệu này không khẳng định đã chạy 40 tests**.

## 21. Case study 1 — Firewall/IPS cập nhật và người dùng hợp lệ bị chặn

### 21.1. Bối cảnh giả định

Một doanh nghiệp có API HTTPS public qua CDN/WAF, firewall inline IDS/IPS và ingress controller. Một bản cập nhật rule mới được triển khai để ngăn một loại lưu lượng xấu. Sau cập nhật:

~~~text
Synthetic from region A: success 100%
Synthetic from region B: success 85%
Backend pod health: ready
API application 5xx rate: gần như không đổi
Ingress request volume from region B: giảm
Firewall deny counters: tăng mạnh trên rule mới
User support tickets: login/API timeouts ở region B
~~~

Số liệu ở đây là **giả định để học**, không phải một incident thực tế. Nếu chỉ nhìn backend health và 5xx rate, dashboard có thể báo “dịch vụ tốt”. Nhưng traffic bị chặn **trước ingress**, nên API counter không chứa những failed attempts.

### 21.2. Sơ đồ và bốn tín hiệu

~~~mermaid
flowchart LR
    A["Users region A"] --> CDN["CDN"]
    B["Users region B"] --> CDN
    CDN --> FW["Firewall / inline IPS"]
    FW --> ING["Ingress"]
    ING --> API["API"]
    FW -. "Rule deny tăng" .-> DEN["Policy logs"]
    B -. "Client failures" .-> SYN["Regional synthetic monitoring"]
~~~

| Tín hiệu | Chỉ đo ở backend có thể thấy | Đo client/end-to-end cần thấy |
|---|---|---|
| Availability | Pod Ready, request success của phần traffic tới API | Region B có nhiều request không tới API |
| Latency | App handler không tăng đáng kể | Client connect timeout hoặc total duration tăng |
| Throughput | Ingress RPS giảm ở một region | Offered legitimate traffic vẫn tồn tại, firewall denies tăng |
| Error rate | 5xx app thấp | Client transport failures/timeout tăng; IPS deny riêng |

### 21.3. Điều tra theo bằng chứng

1. Xác nhận **đúng thời điểm** deploy rule và tỷ lệ lỗi ở region B.
2. So synthetic probes ở A/B, DNS/TLS và frontend LB health để khoanh lớp.
3. Quan sát **firewall allow/deny counters và rule IDs**; không suy mọi deny đều false positive.
4. Lấy mẫu **approved client identities/request IDs** ở B, so chúng với policy.
5. Chạy positive control từ approved client B tới **chính route**; nếu bị deny, xác minh policy match.
6. Kiểm thử negative control từ nguồn/traffic đáng bị chặn trong lab, không tái tạo payload độc hại ngoài môi trường.
7. Thực hiện sửa rule hẹp hoặc rollback có phê duyệt; không tắt toàn bộ IPS vì một false positive.
8. Xác minh **legitimate region B success** phục hồi và deny đúng đối tượng vẫn hoạt động.

### 21.4. Vì sao không dùng HTTP 5xx đơn độc?

Một firewall DROP trước TLS handshake khiến request **không trở thành HTTP 5xx ở API**. Một IPS có thể block TCP connection hoặc return block response riêng. Nếu SLI chỉ dựa `http_requests_total{job="api"}`, cả mẫu số và lỗi đều **thiếu những kết nối bị chặn trước ingress**.

### 21.5. Kết quả trước/sau kỳ vọng

~~~text
BEFORE (lab scenario):
  Region A eligible client success: normal
  Region B eligible client success: degraded
  Firewall rule deny on legitimate B traffic: present
  Backend 5xx: not necessarily elevated

AFTER (desired, pending validation):
  Eligible region B traffic: ALLOW + correct TLS/API result
  Unauthorized traffic matching intended security rule: DENY
  Regional synthetic coverage: sufficient
  Availability, latency, error rate and throughput: within defined SLO
  Evidence: changed rule ID, request/time correlation, approval, rollback
~~~

**Bài học:** một security control có thể chặn đúng kẻ xấu nhưng cũng gây **false positive làm gián đoạn người dùng hợp lệ**. Monitoring phải đo ở **hai phía của PEP**, kết hợp availability end-to-end và telemetry của firewall/IPS.

## 22. Case study 2 — Link trung bình còn trống nhưng p99 và error rate tăng

### 22.1. Bối cảnh giả định

Một cluster gửi traffic từ API qua shared egress firewall/NAT tới đối tác. Link báo capacity **1 Gbit/s**. Dashboard 5 phút cho thấy:

~~~text
Link TX average throughput: 430 Mbit/s
API average latency: 65 ms
API p99 latency: 2,800 ms
Transport timeouts: increased
Firewall session creation/sec: spikes
NIC/queue drops: short bursts
Packet rate: high, mostly small packets
TCP retransmissions: elevated on affected flows
Business goodput: lower than expected
~~~

Đội vận hành có thể nghĩ link mới dùng 43% nên **không thể nghẽn mạng**, hoặc throughput tăng do **DDoS**. Cả hai đều là kết luận thiếu bằng chứng. Một thiết bị có thể đạt ngưỡng **pps/conntrack, CPU inspection hoặc queue microburst**, dù trung bình bit/s dưới line rate.

### 22.2. Giải thích các tín hiệu

~~~mermaid
flowchart TD
    A["Burst of many small connections"] --> P["High pps / sessions per sec"]
    P --> F["Firewall processing + queue pressure"]
    F --> DROP["Microburst drops / transport retransmissions"]
    DROP --> TAIL["p99 latency increases"]
    DROP --> ERR["Timeout/error rate increases"]
    RETRY["Client retries"] --> P
    TAIL --> RETRY
    FLOW["5m average bps still below link capacity"] -. "Che microbursts" .-> F
~~~

| Tín hiệu | Điều đang quan sát | Ý nghĩa cần xác minh |
|---|---|---|
| Availability | Một số transactions không hoàn thành | User journeys fail hay chỉ HTTP attempts fail? |
| Latency | p99 rất cao, avg thấp | Queueing, retries hoặc subgroup/hop chậm |
| Throughput | Average 430 Mbit/s, goodput giảm | Bps thấp không loại trừ pps/CPU/queue saturation |
| Error rate | Transport timeouts tăng | Đo ở client và firewall, không chỉ HTTP 5xx |

### 22.3. Quy trình phân tích

1. Xác nhận **đúng interface** và capacity thật của firewall/NAT instance/cloud tier.
2. So **pps, new connections/s, active sessions, CPU, queue depth/drops, NAT port utilization**.
3. Chuyển từ 5-minute average sang **độ phân giải có thể phát hiện bursts**; tránh truy vấn quá nặng trên metrics backend.
4. Tách traffic theo **nguồn đã được cấp phép, destination, protocol và payload distribution**; kiểm tra backup/batch/rollout/retries.
5. So client p95/p99 với backend/egress timings, TCP retransmission và flow logs tại đúng thời điểm.
6. Kiểm tra security policies, rate limits, TLS inspection và IDS/IPS mode có tạo bottleneck/false positive không.
7. Xác định **traffic hợp lệ hay bất thường** từ inventory/change schedule và security evidence; không tự dán nhãn DDoS.
8. Giảm nguyên nhân qua capacity management, queue/connection control hoặc application backoff theo change control; không tự tắt inspection.
9. Sau sửa, kiểm tra **goodput, p99, error rate, retransmission, queue drops và user SLI**.

### 22.4. Một phản ví dụ quan trọng

Nếu traffic **chỉ có một công việc batch đẩy dữ liệu lớn** và pps thấp, hiệu ứng có thể do chính ứng dụng/database processing thay vì firewall pps. Cùng một biểu đồ bps **không xác nhận** nguyên nhân. Cần so packet sizes, service traces, queuing và dữ liệu host/cloud; ưu tiên kiểm chứng giả thuyết có thể bác bỏ.

### 22.5. Điều kiện hoàn thành

~~~text
Desired (not yet measured):
  p99 latency under service SLO
  Eligible request success rate meets availability objective
  Error rate and timeouts within defined tolerance
  Firewall queue drops and retransmissions explained/reduced
  Throughput and business goodput reported separately
  Security enforcement remains active and correct
  Capacity/action owner, monitoring and rollback documented
~~~

**Bài học:** throughput trung bình **không phản ánh đầy đủ saturation**. Phải kết hợp pps, queue drops, tail latency và real-user error rate để hiểu sự cố.

## 23. Troubleshooting bốn tín hiệu theo từng lớp

### 23.1. Bảng triệu chứng và nguồn bằng chứng

| Triệu chứng | Giả thuyết | Cần xem |
|---|---|---|
| Synthetic fail nhưng API request success đẹp | DNS/CDN/TLS/network trước API | Regional probes, DNS resolver, ingress requests |
| ICMP up nhưng HTTPS fail | Port 443/TLS/app/routing khác ICMP | TCP connect, TLS SAN/CA, HTTP health |
| TLS handshake fail đột ngột | Cert expiry/SAN, SNI, CA trust, clock | Client TLS error, cert inventory, rollout |
| p99 tăng nhưng p50 ổn | Slow tail, overloaded subgroup/queue/retry | Histogram buckets per route/region, traces |
| p99 không đổi sau app tối ưu | Bottleneck ngoài app hoặc histogram không đủ mịn | Client total, proxy upstream, buckets, payload |
| Error rate 0 nhưng khách hàng báo outage | Missing ingress arrivals, no data, wrong eligibility | Synthetic checks, traffic counters, probe coverage |
| 5xx tăng sau deployment | Application bug, endpoint/readiness, gateway upstream | Changes, Service/EndpointSlice, app logs |
| HTTP 403 tăng sau policy update | Firewall/WAF/mesh authz regression hoặc deny hợp lệ | Client identity, rule ID, positive control |
| HTTP 429 tăng khi high traffic | Rate limits hoạt động hoặc quá tải hợp lệ | Contract, eligible user RPS, rate-limit logs |
| DNS `SERVFAIL` tăng | Resolver/upstream/DNSSEC validation | Resolver rcode, latency, zone change |
| `NXDOMAIN` tăng | Client typo/scans hoặc legitimate missing record | Query names/contracts, DNS change |
| Link utilization cao | Capacity saturation hoặc legitimate batch | Interface capacity, bps/pps, queue drops |
| Link utilization thấp mà latency vẫn cao | CPU/pps/conntrack, microbursts, application queue | CPU, pps, drops, traces |
| Receive errors tăng | Physical link, driver/NIC issue | CRC/FCS, device logs, carrier state |
| Network retransmissions tăng | Loss/congestion/reorder/route change | RTT variance, queue, per-hop evidence |
| VPN tunnel up nhưng app không gọi được | Route, split tunneling, DNS, ACL, MTU | Approved synthetic app flow, tunnel and firewall logs |
| Cross-region HTTPS response lớn treo | PMTUD/MTU, overlay/VPN overhead, proxy body limit | Interface MTU, ICMP PTB, request size |
| IPv4 OK nhưng IPv6 fail | AAAA/IPv6 route/firewall khác | IPv4/IPv6 probes, DNS, LB listener |
| Cloud LB 503 trong khi Pod Ready | Service endpoints, unhealthy target, wrong port | LB health, EndpointSlice, Pod listeners |
| IDS alert tăng không thấy block | Passive sensor mode hoặc detection only | Sensor configuration, inline policy |
| WAF denies tăng trong khi backend errors giảm | Bot traffic được chặn đúng hoặc false positives | Verified client eligibility, WAF rule and user probes |
| NIC bytes tăng nhưng successful RPS giảm | Retries, larger payload, overhead, attack/batch | Business RPS, bytes, retrans, request size |
| Probe success luôn 100% dù ít mẫu | Scheduler/exporter down, query zero-fill | Expected count, scrape freshness, no-data alerts |
| Error rate ratio quá lớn/nhỏ kỳ lạ | Sai counter labels, missing numerator, tiny denominator | Raw series, rate window, sample counts |
| p99 toàn dịch vụ tính từ average Pod p99 | Sai phương pháp aggregate | Histograms/raw durations với weights |
| Logs ở các hops lệch thời gian | Clock skew, delayed ingestion, async records | UTC, clock sync, event vs ingest timestamp |
| CPU monitoring backend cao khi traffic spike | High-cardinality labels/log ingestion overload | Series cardinality, dropped batches, queue |

### 23.2. Runbook điều tra ngắn theo hướng người dùng

1. **Xác định sự kiện:** hostname, API/port, region, eligible client, loại lỗi và UTC window.
2. **Xác minh telemetry health:** probes/scrapes/logs/traces có đầy đủ hay không?
3. **Đo user-visible availability:** synthetic + real requests, không chỉ node health.
4. **Phân loại failure layer:** DNS → connect/TLS → ingress/WAF → service/network → app/dependency.
5. **Xác định p95/p99 và timeout:** có tail latency hoặc uncompleted requests không?
6. **So offered traffic với successful throughput:** RPS, bps, pps, goodput, queue/conntrack.
7. **Xem drops/denies/5xx:** mỗi loại từ đúng PEP/driver/proxy nào?
8. **Đối chiếu gần sự cố:** rollout, certificate, DNS, firewall/IDS/NetworkPolicy, cloud routes, scaling.
9. **Làm phép thử có đối chứng:** allowed client được phục vụ, unauthorized client bị deny đúng.
10. **Khắc phục có rollback:** xác nhận SLI phục hồi và policy bảo mật không bị mở rộng ngoài ý định.

### 23.3. Trường hợp báo cáo phải ghi INCONCLUSIVE

- Không có synthetic probes khi toàn bộ người dùng mất DNS.
- Không đủ request volume để ước lượng p99 đáng tin.
- Counter reset/metric labels changed làm tỷ lệ bị ngắt.
- Packet capture ghi sau sự cố, không còn traffic cần xem.
- CNI/firewall logs có sampling mà không biết tỉ lệ.
- Kết nối test thất bại nhưng backend đang down hoặc bị chặn ở điểm không phải PEP mục tiêu.

Trong những tình huống đó, **không tự đánh dấu PASS hay FAIL** cho một security control chỉ vì thiếu bằng chứng; ghi rõ mức chắc chắn, dữ liệu cần bổ sung và chủ trách nhiệm.

## 24. Runbook triển khai giám sát bốn tín hiệu theo SLO

### Bước 1 — Chọn dịch vụ và định nghĩa “được phục vụ”

Trước khi bật collector, viết rõ:

~~~yaml
# MẪU POLICY-AS-INTENT, không phải cấu hình có thể apply vào Kubernetes.
service: orders-api
owner: application-and-network-oncall
environment: production
frontend_hostname: api.example.test
eligible_clients: authenticated-users-with-approved-access
measurement_perspectives:
  - external-client-region-a
  - external-client-region-b
  - approved-private-network-client
  - ingress-proxy
  - application-handler
availability_sli:
  success: correct-http-and-business-outcome
  excludes:
    - unauthorized-probe-traffic
    - explicitly-rejected-security-policy-traffic
  no_data: unknown-with-coverage-alert
latency_sli:
  boundary: client-request-to-completed-response
  target_ms: 500
  target_fraction: 0.99
availability_slo:
  target_fraction: 0.999
  rolling_window: 30d
throughput:
  primary: successful-transactions-per-second
  supplemental: bytes-per-second-and-packets-per-second
error_rate:
  numerator: eligible-transaction-failures
  denominator: eligible-transactions
security_controls:
  - firewall-deny-observed-separately
  - tls-validity-required
  - networkpolicy-deny-tests-maintained
~~~

Đây là một **bản mô tả ý định**; những số mục tiêu chỉ là ví dụ để review. Mỗi service phải quy định rõ user segments, transaction types, timeout, retry semantics và các trường hợp cần tính là **business failure**.

### Bước 2 — Vẽ đường dữ liệu và chọn vị trí đo

~~~mermaid
flowchart TD
    U["Client / synthetic vantage"] --> DNS["DNS / TLS front door"]
    DNS --> LB["LB / WAF / firewall"]
    LB --> API["Ingress / API"]
    API --> DEP["Dependencies"]
    P1["Client-side probes"] -. "Availability + full latency" .-> U
    P2["Edge/network logs + counters"] -. "Throughput, policy denies, errors" .-> LB
    P3["Application histograms + tracing"] -. "Handler and dependency latency" .-> API
    P4["Collectors / metric backend"] -. "Completeness + retention" .-> DEP
~~~

Chọn ít nhất một phép đo **trước điểm có thể làm mất traffic** như DNS/CDN/firewall, và một phép đo **sau điểm đó** để xác định lỗi không tới backend. Với private services, chọn một allowed-vantage đại diện VPN/ZTNA/network segmentation.

### Bước 3 — Chọn metrics, labels và data ownership

| Tín hiệu | Metrics chính | Dimension tối thiểu |
|---|---|---|
| Availability | Successful eligible requests/total, synthetic probe_success | Service, region, environment, transaction class |
| Latency | Classic/native histogram durations, client timings | Service, route template, region/protocol |
| Throughput | RPS, business success/s, NIC bytes/s, packets/s | Service, workload/instance, device, direction |
| Error rate | 5xx/timeout/TLS/DNS/app error classes | Service, error layer, region, relevant route |
| Saturation/health | Queue, drops, CPU, conntrack, telemetry coverage | Network device, zone, collector/target |

Giới hạn **label cardinality**, loại trừ secrets và dữ liệu người dùng ở metrics. Traces/logs cần sampling/retention phù hợp, pseudonymization và role-based access.

### Bước 4 — Thiết lập tính toàn vẹn của số liệu

- Chuẩn hóa đơn vị **seconds vs milliseconds, bytes/s vs bit/s, decimal vs binary**.
- Chỉ dùng `rate()` cho counter hợp lệ với scrape interval đủ mẫu, theo dõi resets và target churn.
- Chọn histogram buckets quanh latency threshold thật; không average percentiles đã tính.
- Định nghĩa behavior **no traffic, missing data, partial region coverage và sampling**.
- Đảm bảo UTC timestamps và trace/request IDs có thể correlate.
- Tránh double count khi network traffic đi qua bridge, tunnels và LB.

### Bước 5 — Thiết lập SLO, cảnh báo và runbook

1. Chọn SLO cửa sổ rolling đủ ý nghĩa (ví dụ 30 ngày).
2. Định nghĩa time- vs request-based budget, không trộn công thức.
3. Triển khai **burn-rate alerts** cho user impact, kèm minimum volume hoặc synthetic evidence.
4. Thêm cảnh báo cho telemetry missing, certificate expiry, queue drops và policy false positives.
5. Chỉ paging khi có action, owner và runbook; còn long-term capacity nên dùng ticket/planning.
6. Kết nối alert với **change/release/firewall/DNS/cert timeline**.

### Bước 6 — Kiểm thử số liệu và đường đi

Trong lab hoặc canary có phê duyệt:

~~~text
Positive:
  Legitimate HTTPS request from region A : PASS
  Legitimate HTTPS request from region B : PASS
  Approved VPN/Pod identity -> private service : PASS
  Certificate verification by client: PASS

Negative:
  Wrong TLS hostname/cert: detected as TLS failure
  Unapproved source -> protected service: DENY by intended PEP
  Controlled backend failure: reflected in client availability
  Missing synthetic samples: coverage alert, not false green

Performance:
  Low-volume request timings tracked correctly
  Interface counter reset handled
  p99 histograms computed from compatible buckets
  RPS and bps treated as different metrics
~~~

Không tạo production load hoặc tắt hệ thống chỉ để minh họa lỗi; dùng controlled fault injection trong lab nếu cần và đã được phê duyệt. **Kết quả negative test chỉ PASS khi đúng lớp enforcement có evidence**, không chỉ vì curl timeout.

### Bước 7 — Canary, giám sát và rollback

~~~mermaid
flowchart TD
    D["Define SLI and traffic eligibility"] --> P["Select vantage/collectors/labels"]
    P --> I["Instrument clients, edges, API and network"]
    I --> V["Validate sample coverage + math + privacy"]
    V --> T["Lab positive/negative tests"]
    T --> G{"Metrics correct and actionable?"}
    G -- "Không" --> F["Fix definitions/instrumentation"]
    F --> V
    G -- "Có" --> C["Canary dashboards/alerts"]
    C --> O["Observe alert noise and SLO impact"]
    O --> R{"Blind spots or regression?"}
    R -- "Có" --> F
    R -- "Không" --> A["Roll out + periodic review"]
~~~

Monitor hạ tầng cũng có resource limits: collector CPU/memory, queue overflow, network egress charges, high cardinality và traces chứa secrets. Rollback có thể là **tắt một collector/exporter quá tải hoặc hạ sampling** mà vẫn giữ tối thiểu user-impact probes và security logs, theo change control.

### Bước 8 — Đánh giá định kỳ

Đối chiếu SLO trends, error budget burn, false-positive alerts, service ownership, telemetry costs, blind spots và các thay đổi trong topology. Một thay đổi CDN, service mesh, Kubernetes CNI, IPv6 route hoặc firewall rule có thể làm **điểm quan sát** và **mẫu số SLI** thay đổi dù ứng dụng không sửa code.

Mỗi review nên trả lời:

- Có người dùng/region/identity hợp lệ nào không nằm trong probes?
- Có requests nào bị chặn trước điểm đặt application metrics không?
- Có policies đang deny đúng nhưng dashboard đang xem là lỗi?
- Có một nguồn dữ liệu nào mất mà service vẫn hiển thị 100%?
- SLO/cảnh báo có khiến người trực xử lý được không?
- Có dữ liệu telemetry nhạy cảm nào đang được thu vượt nhu cầu?

## 25. Bài tập vận dụng và đáp án gợi ý

### Bài 1 — Phân biệt availability

Một máy chủ phản hồi ICMP 100%, nhưng API `/v1/orders` trả 503 trong một giờ. Có thể báo API availability 100% không?

**Gợi ý:** không. ICMP chứng minh host/network trả probe đó, không phải business endpoint hoạt động. Dùng eligible request/synthetic transaction SLI.

### Bài 2 — Availability request-based

Trong một cửa sổ, hệ thống nhận 50.000 eligible requests, 49.500 thành công. Tính availability và error fraction theo request.

**Đáp án:** availability \(49.500/50.000=99\%\); error fraction \(500/50.000=1\%\). Hai tỷ lệ chỉ cộng thành 100% nếu định nghĩa success/error phân hoạch toàn bộ eligible requests.

### Bài 3 — Time error budget

Một SLO 99,9% time-based trong 30 ngày (43.200 phút) cho budget downtime bao nhiêu?

**Đáp án:** \(0{,}1\%\times43.200=43{,}2\) phút. Không dùng con số này làm request-based budget nếu traffic thay đổi.

### Bài 4 — Request error budget

Một service có SLO 99,95% request-based và 200.000 eligible requests. Số request fail tối đa tương đương là bao nhiêu?

**Đáp án:** \(200.000\times0{,}0005=100\) requests.

### Bài 5 — Burn rate

SLO 99,9% cho error fraction 0,1%, nhưng quan sát 2% eligible transactions fail trong cửa sổ ngắn. Burn rate bằng bao nhiêu?

**Đáp án:** \(2\%/0{,}1\%=20\times\). Đánh giá volume/window/impact trước khi quyết định severity.

### Bài 6 — Trung bình và p99

API có average latency 50 ms nhưng p99 đạt 2.000 ms. Người dùng có thể vẫn gặp sự cố nghiêm trọng không?

**Gợi ý:** có. 1% request chậm có thể ảnh hưởng chức năng nhạy cảm, đặc biệt khi một transaction phụ thuộc nhiều services.

### Bài 7 — Tổng hợp p99

Hai Pods có p99 lần lượt là 100 ms và 900 ms, với traffic khác nhau. Có thể lấy trung bình 500 ms làm p99 toàn service không?

**Đáp án:** không. Cần raw observations hoặc aggregate histogram buckets tương thích rồi ước lượng percentile, không average per-Pod p99.

### Bài 8 — TTFB và server time

Client TTFB là 700 ms, backend handler duration 70 ms. Có thể kết luận backend xử lý 700 ms không?

**Gợi ý:** không. Phải xem DNS, connect/TLS, network, proxy queue, edge cache, upstream và measurement milestones.

### Bài 9 — Tính throughput

Một interface ghi nhận 30.000.000 bytes nhận trong 10 giây. Average receive throughput là bao nhiêu Mbit/s nếu dùng decimal units?

**Đáp án:** \(30.000.000\times8/10=24.000.000\) bit/s = **24 Mbit/s**.

### Bài 10 — Throughput và goodput

NIC TX có 500 Mbit/s nhưng ứng dụng chỉ hoàn thành 280 Mbit/s payload. Đây có tự động là packet loss 44% không?

**Đáp án:** không. Chênh lệch có thể gồm protocol headers, retransmission, encryption overhead, workload/measurement boundaries và app behavior. Cần xem cụ thể.

### Bài 11 — Packet rate

Firewall chưa chạm giới hạn Gbit/s nhưng CPU và connections/s rất cao, p99 tăng. Có thể là saturation không?

**Gợi ý:** có. Giới hạn pps, TLS handshakes/s, conntrack hoặc CPU inspection có thể đến trước giới hạn bit/s.

### Bài 12 — Error rate với mẫu nhỏ

Trong 5 phút chỉ có 2 requests, 1 request fail. Error rate 50% có nên lập tức gọi paging 24/7 không?

**Gợi ý:** không chỉ dựa tỷ lệ. Cần context, synthetic SLI, error budget, user impact, min sample và loại giao dịch; một giao dịch quan trọng vẫn có thể yêu cầu báo động riêng.

### Bài 13 — HTTP 403

WAF từ chối 2.000 requests từ các bot không có quyền. Có cần tính tất cả vào business availability failures không?

**Đáp án:** không mặc định. Đây có thể là enforcement thành công; theo dõi security-deny riêng. Nhưng phải phát hiện false positive khi legitimate user bị deny.

### Bài 14 — HTTP 200 sai dữ liệu

API trả HTTP 200 nhưng order payload có giá trị sai. Có nên tính request đó thành success chỉ vì HTTP code?

**Gợi ý:** không nếu SLI đã định nghĩa correctness; cần semantic/business validation chứ không chỉ HTTP status.

### Bài 15 — Counter rate

Vì sao không lấy trực tiếp `node_network_receive_bytes_total` làm bytes/s?

**Đáp án:** đó là cumulative counter. Dùng `rate(...[5m])` hoặc delta theo time window và xử lý reset/missing samples.

### Bài 16 — Histogram

Một histogram có 940/1.000 observations trong bucket `le="0.25"` và tổng count 1.000. Bao nhiêu % có duration ≤250 ms?

**Đáp án:** **94%**, giả định count/bucket cùng population/window.

### Bài 17 — Telemetry missing

Probes dự kiến 10 lần/phút nhưng chỉ thu được 2 lần, cả hai đều thành công. Có thể báo uptime 100% không?

**Gợi ý:** chỉ nói 100% **collected probes** thành công, coverage 20%. SLI đủ tin cậy hay UNKNOWN phụ thuộc policy; phải alert telemetry loss.

### Bài 18 — Retry accounting

Một transaction tạo ba HTTP attempts: timeout, 503 rồi 200. Attempt error fraction và transaction success là gì?

**Đáp án:** attempt-level failure 2/3 ≈66,7%; transaction-level success 1/1 nếu giao dịch thực sự thành công theo contract. Latency có thể không đạt SLO.

### Bài 19 — DNS và IPv6

Resolver trả A record đúng, `AAAA` không tồn tại trong hệ thống IPv4-only. Đây có luôn là DNS failure không?

**Gợi ý:** không. Phải xét DNS contract; nếu IPv6 được công bố là bắt buộc, mất AAAA/IPv6 reachability mới là vấn đề.

### Bài 20 — Active/passive

Backend request success = 100% nhưng synthetic từ region B fail toàn bộ. Những điểm nào cần kiểm tra?

**Gợi ý:** DNS, CDN/LB, firewall/IPS, TLS, IPv6, regional route và telemetry coverage. Requests fail trước backend không có trong application denominator.

### Bài 21 — NetworkPolicy

Pod ngoài allowlist không kết nối được DB; DB Pod lại đang Down. Có thể đánh dấu NetworkPolicy DENY PASS không?

**Đáp án:** không. Cần positive control từ nguồn được phép và CNI/firewall evidence chứng minh deny vì policy.

### Bài 22 — SNMP/flow logs

Một dashboard cộng bytes của physical NIC, bridge và overlay tunnel trên cùng host. Vì sao traffic total có thể bị thổi phồng?

**Gợi ý:** cùng packet đi qua nhiều interfaces/layers và được đếm nhiều lần; định nghĩa một điểm đo canonical.

### Bài 23 — Security alert

IDS signature hits tăng nhưng thiết bị chạy out-of-band. Có thể khẳng định IDS đã chặn 100% packet đáng ngờ?

**Đáp án:** không. Passive detection và inline enforcement khác nhau; cần xác minh sensor mode, network controls và log action.

### Bài 24 — Multi-region SLO

Region nhỏ có availability 90% nhưng region lớn đạt 99,99%; global weighted SLI vẫn vượt ngưỡng. Có nên bỏ qua sự cố region nhỏ?

**Gợi ý:** không. SLO global có thể che impact nghiêm trọng với một nhóm user. Dùng per-region SLO/alert và customer impact.

### Bài 25 — Thiết kế tổng hợp

Thiết kế dashboard cho hệ thống HTTPS gồm **DNS, CDN/WAF, VPN/private endpoint, Kubernetes ingress, API, DB**. Chọn ít nhất:

- 2 metrics availability,
- 3 latency distributions/milestones,
- 3 throughput/capacity metrics,
- 3 error/security-deny metrics,
- 1 telemetry coverage metric,
- 4 positive/negative tests.

**Gợi ý:** synthetic HTTPS success theo region, eligible transaction SLI; client total/p99, TLS handshake, API histogram; ingress RPS, link bps, pps; 5xx, DNS SERVFAIL/TLS failure, firewall/WAF denies tách; expected-vs-collected probes; approved HTTPS client success, unauthorized Pod blocked, wrong TLS cert detected và DNS failure reflected. Gắn mọi metric với **owner, unit, window, label dimensions và data source**.

## 26. Checklist triển khai Availability, Latency, Throughput và Error Rate

### 26.1. Định nghĩa và đo lường

- [ ] Đã chọn **tài nguyên, owner, users/clients đủ điều kiện, geography, protocols và measurement boundary**.
- [ ] Availability SLI phản ánh **chức năng thật**, không chỉ node ping/port up.
- [ ] Phân biệt **time-based availability** với **request-based success** và cách loại/ghi maintenance theo contract.
- [ ] Latency có mốc **client, proxy, application, dependency** rõ ràng; có p50/p95/p99 hoặc fraction dưới threshold.
- [ ] Có phương pháp xử lý **timeouts, unfinished requests, retries và coordinated omission**.
- [ ] Throughput phân biệt **bits/s, bytes/s, packets/s, requests/s và business goodput**.
- [ ] Không nhầm **link capacity, utilization, saturation và actual throughput**.
- [ ] Error rate có **mẫu số và eligible event definition**; 4xx, DNS errors, transport/TLS errors được phân loại.
- [ ] Policy denies hợp lệ được **theo dõi riêng** khỏi lỗi user-facing; false positives có test.
- [ ] Đã chọn **SLI/SLO/error budget/window**, có burn-rate/impact interpretation đúng.

### 26.2. Telemetry coverage và chất lượng dữ liệu

- [ ] Có **synthetic probes ở những vantage quan trọng** và passive request metrics cho traffic thật.
- [ ] Có điểm quan sát **trước và sau DNS/CDN/LB/firewall/ingress** theo yêu cầu điều tra.
- [ ] Những endpoints chỉ có private VPN/ZTNA access được kiểm thử từ **authorized identity** đúng.
- [ ] Đã bao phủ IPv4/IPv6 khi hỗ trợ, regions/AZs, ingress classes và important user journeys.
- [ ] DNS/TLS probes xác minh **response correctness và certificate hostname**, không tắt validation.
- [ ] Collectors/exporters, scheduler, probe coverage, scrape freshness và dropped telemetry được đo riêng.
- [ ] No data/unknown hiển thị chính xác; không biến **mất telemetry thành 0 lỗi hoặc uptime 100%**.
- [ ] Metrics counters dùng `rate()`/`increase()` với **reset semantics**, sampling và scrape window rõ.
- [ ] Classic histograms có buckets phù hợp ngưỡng SLO và **aggregate trước khi tính percentile**.
- [ ] Không average p99 của các instances hoặc regions khi thiếu distribution/weights phù hợp.
- [ ] Metric labels tránh **raw URL/user ID/IP/trace ID** gây high cardinality và tiết lộ dữ liệu.
- [ ] Logs/traces/flow telemetry có **retention, access controls, sampling, privacy redaction và cost limits**.
- [ ] Timestamps UTC, request/trace IDs và source/destination identities liên kết được qua các hops.

### 26.3. Network và security instrumentation

- [ ] Interface counters gắn với **đúng NIC/tunnel/link/hướng traffic**; tránh double counting.
- [ ] Đo **pps, queue drops, conntrack, CPU/crypto inspection và session creation rate**, không chỉ Mbps.
- [ ] Phân biệt packet errors/discards, loss, retransmission và HTTP request failures.
- [ ] Firewall/IDS/IPS events phân biệt **detection-only, intentional deny, unexpected drop và false positive**.
- [ ] NetworkPolicy/ACL được kiểm thử cả **approved allow** và **unapproved deny**.
- [ ] VPN tunnel health không thay thế **application synthetic từ tunnel identity**.
- [ ] DNS `SERVFAIL`, timeout, NXDOMAIN và DNSSEC validation được xử lý theo contract.
- [ ] TLS certificate expiry/SAN/chain/SNI/mTLS trust errors có metric/alert phù hợp.
- [ ] Cloud NAT/LB/flow logs được diễn giải theo **sampling, NAT và provider semantics**.
- [ ] Application metrics không được coi là đầy đủ khi traffic có thể fail **trước ingress**.
- [ ] Khi có egress restrictions hoặc zero trust, dashboard không tính **unauthorized probes** như sự cố ứng dụng.

### 26.4. Alerts và vận hành

- [ ] Có ít nhất một cảnh báo **user-impact/SLO burn** với owner, severity và runbook.
- [ ] Error rate alerts xét **số lượng requests, cửa sổ thời gian, noise control và impact**.
- [ ] Telemetry outage có alert riêng, không che bằng zero-fill bừa bãi.
- [ ] Dashboard hiển thị SLI, p95/p99, throughput, error layers, **saturation** và recent changes.
- [ ] Có breakdown theo **region, protocol, service, route template và network policy zone** khi có ích.
- [ ] Có logic tránh alert storm do một root cause DNS/CDN/LB hoặc collector outage.
- [ ] Changes về **firewall, IDS/IPS, VPN, DNS, cert, CNI/NetworkPolicy và ingress** được gắn với timeline.
- [ ] Mỗi sửa lỗi có **positive/negative regression tests** và không tự mở rộng quyền firewall/mesh để “làm xanh” dashboard.
- [ ] Có canary/rollback và periodic review cho instrumentations, collectors, SLO definitions và test coverage.

**Kết luận:** availability trả lời **dịch vụ có phục vụ được không**, latency trả lời **phục vụ nhanh đến mức nào**, throughput trả lời **hoàn thành bao nhiêu công việc/dữ liệu**, còn error rate trả lời **bao nhiêu sự kiện không đạt tiêu chí**. Để bốn tín hiệu trở thành bằng chứng hữu ích cho bảo mật và vận hành mạng, phải định nghĩa **đúng user/path, đúng lớp lỗi, đúng mẫu số và đúng nguồn đo**; kết hợp synthetic với passive telemetry, đo saturation, kiểm soát no-data/sampling và kiểm thử cả lưu lượng được phép lẫn bị chặn. Một dashboard xanh chỉ đáng tin khi **dữ liệu đủ đầy và security enforcement vẫn đúng**.

### Tài liệu tham khảo và đọc thêm

- [Google SRE Book — Monitoring Distributed Systems](https://sre.google/sre-book/monitoring-distributed-systems/): bốn Golden Signals, chất lượng cảnh báo và phương pháp giám sát.
- [Google SRE Book — Service Level Objectives](https://sre.google/sre-book/service-level-objectives/): SLI, SLO, lựa chọn indicators, interpretation.
- [Google SRE Workbook — Implementing SLOs](https://sre.google/workbook/implementing-slos/): metric definitions, windows và error-budget accounting.
- [Google SRE Workbook — Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/): burn-rate, nhiều cửa sổ và giảm alert noise.
- [Prometheus — Metric types](https://prometheus.io/docs/concepts/metric_types/): counter, gauge, histogram và summary.
- [Prometheus — Histograms and summaries](https://prometheus.io/docs/practices/histograms/): classic histograms, quantile aggregation và SLO thresholds.
- [Prometheus — Query functions](https://prometheus.io/docs/prometheus/latest/querying/functions/): `rate`, `increase`, `histogram_quantile`, `avg_over_time`, `absent`.
- [Prometheus — Alerting rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/): rule syntax, `for` và alert annotations.
- [Prometheus Blackbox Exporter](https://github.com/prometheus/blackbox_exporter): active HTTP, DNS, TCP và ICMP probes.
- [OpenTelemetry — Metrics](https://opentelemetry.io/docs/concepts/signals/metrics/): metrics instrumentation và aggregation concepts.
- [OpenTelemetry — Traces](https://opentelemetry.io/docs/concepts/signals/traces/): distributed tracing và request correlation.
- [OpenTelemetry — Collector](https://opentelemetry.io/docs/collector/): thu, xử lý và xuất telemetry.
- [RFC 7011 — IP Flow Information Export (IPFIX)](https://www.rfc-editor.org/rfc/rfc7011): giao thức export flow records.
- [RFC 9293 — Transmission Control Protocol (TCP)](https://www.rfc-editor.org/rfc/rfc9293): TCP semantics, recovery-related context.
- [RFC 9000 — QUIC](https://www.rfc-editor.org/rfc/rfc9000): transport over UDP, connection and path behavior.
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446): handshake và kênh TLS.
- [RFC 9525 — Service Identity in TLS](https://www.rfc-editor.org/rfc/rfc9525): xác minh hostname/danh tính của TLS endpoint.
- [NIST SP 800-137 — Information Security Continuous Monitoring](https://csrc.nist.gov/pubs/sp/800/137/final): quan sát liên tục theo rủi ro.
- [NIST SP 800-61 Rev. 3 — Incident Response Recommendations and Considerations for Cybersecurity Risk Management](https://csrc.nist.gov/pubs/sp/800/61/r3/final): hướng dẫn incident response trong quản trị rủi ro bảo mật.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): structured logs, privacy và bảo vệ audit events.









