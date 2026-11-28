# Metrics, logs và traces của network path

Một người dùng báo ứng dụng đặt hàng “thỉnh thoảng rất chậm”. Dashboard HTTP của dịch vụ Orders cho thấy thời gian xử lý trung bình vẫn thấp. Đội mạng lại thấy interface không bão hòa, trong khi gateway ghi nhận một số request kết thúc bằng 504. Liệu lỗi xảy ra khi phân giải DNS, thiết lập TCP/TLS, qua load balancer, trong service mesh, ở API backend hay trong một lần gọi database?

Để trả lời, không thể chỉ nhìn **một chỉ số CPU** hoặc **một dòng HTTP access log**. Cần quan sát **network path** bằng ba loại tín hiệu bổ sung nhau: **metrics** cho xu hướng và mức độ; **logs/events** cho quyết định và sự kiện cụ thể; **traces** cho quan hệ nhân quả và thời gian của các thao tác có ngữ cảnh. Trong nhiều trường hợp còn cần **flow records, packet/transport diagnostics và topology** để xác định chặng mạng.

Bài thuộc chương **Giám sát mạng và telemetry** của module **SECURITY_NETWORK_SECURITY**. Kiến thức gắn với phân đoạn mạng, firewall, VPN, IDS/IPS, xác thực kết nối, DNS, mạng không dây, Kubernetes/cloud networking, mô hình hóa mối đe dọa và giám sát xâm nhập.

> **Nguyên tắc:** **Metrics chỉ ra điều gì thay đổi; logs cho biết sự kiện/quyết định nào đã xảy ra; traces giúp biết một tác vụ đã đi qua những thành phần nào và tốn thời gian ở đâu.** Không một loại tín hiệu đơn lẻ luôn nhìn thấy toàn bộ đường đi của một packet hoặc chứng minh chính xác nguyên nhân.

## 1. Mục tiêu học tập

Sau bài này, bạn cần:

1. Định nghĩa **network path** của một request qua DNS, routing, firewall, proxy, TLS, Kubernetes Service/CNI và các hop tới backend.
2. Phân biệt **metric, log, event, distributed trace, network flow record và packet capture**; biết dùng mỗi tín hiệu cho câu hỏi nào.
3. Chọn network metrics phù hợp: **throughput, packets/bytes, drops, errors, RTT, TCP retransmissions, connection failures, DNS latency, TLS handshake, HTTP latency** và saturation.
4. Thiết kế labels/tags có cardinality an toàn, phân biệt counter/gauge/histogram và hiểu histogram quantile.
5. Đọc **access logs, DNS logs, firewall/CNI flow logs, IDS/IPS alerts và cloud flow logs** đúng ngữ cảnh, tránh nhầm “no log” với “no traffic”.
6. Hiểu trace/span, trace context, client/server spans, sampling và lý do **TCP hop hoặc network device có thể không xuất hiện trong distributed trace**.
7. Liên kết ba tín hiệu theo **time window, resource/service identity, request/trace ID, 5-tuple và NAT mapping**, với độ tin cậy và giới hạn được nêu rõ.
8. Xây dashboard/SLO/alerting và quy trình điều tra một lỗi network path bằng chứng cứ đối chứng.
9. Kiểm soát dữ liệu nhạy cảm, chi phí telemetry, retention và quyền truy cập quan sát.
10. Lập ma trận positive/negative tests để xác minh pipeline telemetry hoạt động trước khi có incident thật.

## 2. Network path là gì?

**Network path** là chuỗi bước, thành phần và ranh giới mà lưu lượng trải qua từ client tới đích. Một ứng dụng có thể phát sinh **nhiều network paths**: client→gateway, gateway→API, API→service khác, API→database, cùng các đường DNS, identity provider, telemetry và OCSP/PKI tùy kiến trúc.

Ví dụ minh họa:

~~~mermaid
flowchart LR
    B["Browser / client"]
    DNS["DNS resolver"]
    EDGE["CDN / WAF / LB"]
    GW["Ingress / API gateway"]
    NET["CNI / Service routing"]
    API["Orders API"]
    MESH["Mesh proxy"]
    DB[("Database")]
    B -.->|"DNS query"| DNS
    B -->|"TCP/TLS or QUIC"| EDGE
    EDGE -->|"TLS hop / proxy routing"| GW
    GW -->|"Ingress rules / service VIP"| NET
    NET -->|"To selected Pod"| API
    API -->|"Service-to-service flow"| MESH
    MESH --> DB
~~~

Sơ đồ không ngụ ý mọi deployment phải có CDN, WAF, gateway, sidecar hay database, cũng không khẳng định mỗi mũi tên là một kết nối TCP duy nhất. **Proxy thường chấm dứt một kết nối và tạo kết nối mới**; mỗi đoạn có source/destination, thời gian, TLS peer và failure mode riêng.

### 2.1. Ba cách nhìn đường đi

| Góc nhìn | Câu hỏi | Đơn vị quan sát |
|---|---|---|
| **Packet/flow** | Một luồng IP đi từ interface/source nào tới đâu, được allow hay drop? | L3/L4, 5-tuple, bytes/packets, flow verdict |
| **Connection** | DNS, TCP/TLS/QUIC handshake và session diễn ra thế nào? | Endpoint, handshake, RTT, retransmission, connection state |
| **Request/transaction** | Một lời gọi API, gRPC hoặc truy vấn nghiệp vụ mất thời gian ở đâu? | HTTP/gRPC request, span, trace, business operation |

Một **HTTP request** không đồng nhất với một **TCP connection**: HTTP/2 có thể multiplex nhiều request trên một kết nối; keep-alive tái sử dụng connection; một lời gọi nghiệp vụ có thể phát sinh retries và các request con. Ngược lại, một TCP flow chưa chắc chứa HTTP hoặc có tracing.

### 2.2. Ranh giới và câu hỏi đo lường

| Chặng | Điểm bắt đầu/kết thúc | Có thể xảy ra |
|---|---|---|
| Client → DNS resolver | OS/browser → resolver | NXDOMAIN, SERVFAIL, timeout, cache miss, DNS poisoning |
| Client → edge | Client IP → public VIP/CDN | Packet loss, network congestion, TLS handshake failure |
| Edge/WAF → gateway | Reverse proxy → upstream | Block rule, origin selection sai, 502/504, TLS mismatch |
| Gateway → Service/Pod | Ingress → CNI/LB/Pod | NetworkPolicy deny, endpoint stale, NAT/route vấn đề |
| Pod → service khác | Mesh/tunnel → upstream | Service AuthZ deny, mTLS failure, retry storm |
| Service → DB | App connection pool → DB | Pool exhaustion, DB auth/lock/query delay |
| App → telemetry | SDK/agent → collector/backend | Dropped spans/logs, exporter queue full |

**Lỗi của ứng dụng có thể biểu hiện giống lỗi mạng.** Một 504 từ gateway có thể do mạng tới backend không tới được, nhưng cũng có thể do backend đang treo vì database chậm. Phải xác định **thành phần nào sinh 504 và timeout đang xảy ra ở chặng nào**.

## 3. So sánh metrics, logs và traces

| Tín hiệu | Bản chất | Trả lời tốt | Không tự trả lời |
|---|---|---|---|
| **Metrics** | Chuỗi giá trị theo thời gian; aggregate hoặc gauges/counters/histograms | Khi nào lỗi tăng, p95 latency đổi ra sao, cổng có bão hòa không? | Request cụ thể của user nào lỗi vì sao? |
| **Logs** | Bản ghi sự kiện có timestamp, thuộc tính và nội dung | Ai bị firewall deny, TLS alert nào, upstream nào trả 503? | Mọi log có cùng request thuộc chuỗi nhân quả nào? |
| **Distributed traces** | Tập spans có quan hệ parent/child hoặc liên kết, đại diện thao tác trong workflow | Request A qua gateway→orders→payment mất bao lâu? | Mọi packet/router hop, packet loss trên một link không instrumented? |
| **Flow records** | Metadata kết nối như source/destination IP/port, protocol, bytes, decision | Cặp endpoint nào trao đổi traffic, có bị network policy deny? | Nội dung API và danh tính user nếu không có enrichment |
| **Packet capture** | Mẫu packet/headers/payload tùy điểm capture | TCP handshake/retransmit, DNS query, vấn đề giao thức cụ thể | Ý nghĩa nghiệp vụ, nội dung khi mã hóa, toàn bộ mạng từ một điểm đo |
| **Topology/config events** | Thay đổi route, DNS, policy, deployment, endpoint | Sự cố bắt đầu cùng thay đổi nào? | Quan hệ nhân quả nếu không có flow/request evidence |

Một **flow log** có thể được đưa vào kho log, nhưng về mặt ý nghĩa nó là **flow-level telemetry**, không phải trace. Một **span event** nằm trong trace có thuộc tính gần giống log, nhưng vẫn mang trace context. Một **metric exemplar** có thể liên kết một điểm dữ liệu histogram với trace ID (khi hệ thống hỗ trợ); exemplar không có nghĩa mọi điểm metric được trace.

### 3.1. Ba câu hỏi cho cùng một lỗi

Giả sử lỗi 5xx tăng vào 14:05:

1. **Metric:** tỷ lệ gateway 5xx tăng từ baseline lên mức nào và kéo dài bao lâu?
2. **Log:** 5xx do gateway tự phát vì upstream timeout, do WAF policy hay do backend trả về?
3. **Trace:** ở những request có context và được sample, chặng nào chiếm phần lớn wall time?

Sau đó đối chiếu **CNI/network flow verdict, TCP RTT/retransmissions, DNS failure và change events** để phân biệt chậm do transport với chậm do app/DB.

## 4. Chọn tín hiệu tại đúng measurement point

Trong network observability, vị trí đo quyết định ý nghĩa của số liệu:

~~~mermaid
flowchart TB
    subgraph SOURCE["Client / endpoint"]
      D["DNS timing, connect timing, TLS timing"]
    end
    subgraph MIDDLE["Network / gateways"]
      F["Interface counters / flow verdicts / RTT samples"]
      P["WAF, LB, proxy access logs and latency metrics"]
    end
    subgraph APP["Workload / application"]
      S["Client and server spans"]
      L["App logs / response outcome"]
      X["DB call spans and metrics"]
    end
    D --> F --> P --> S --> L --> X
    D -.-> COL["Telemetry collector / correlation"]
    F -.-> COL
    P -.-> COL
    S -.-> COL
    L -.-> COL
    X -.-> COL
~~~

| Measurement point | Có thể đo | Điểm dễ suy diễn sai |
|---|---|---|
| **Client/browser** | DNS, connection setup, TLS, TTFB, request duration tùy API công cụ | Client connection reuse/cache làm DNS/TLS timing bằng 0 ở request sau |
| **OS/network interface** | Bytes, packets, errors/drops, link state | Interface drops không chứng minh drop của request cụ thể |
| **Firewall/CNI** | Verdict allow/deny theo interface/identity/policy | Log có thể sample; host traffic có thể ngoài scope |
| **Load balancer/proxy** | Request count, 4xx/5xx, upstream connect/response time | Proxy-generated 502/504 khác backend-generated 5xx |
| **Service mesh** | TLS/peer identity, per-service connection/request stats | Không nhìn thấy các luồng bypass proxy hoặc bị loại khỏi capture |
| **Application instrumentation** | Request/operation spans, error semantics, dependencies | Không tự thấy routing trong switch/router không instrumented |
| **Database** | Connections, query latency, locks, rejected auth | DB nhanh không đồng nghĩa network tới DB nhanh |
| **Collector/backend** | Export lag, ingest drops, gaps | Không biết nguyên nhân tại source nếu thiếu self-telemetry |

### 4.1. Time reference và đồng hồ

Để ghép dữ liệu nhiều host, cần **clock synchronization** và hiểu timestamp:

- Timestamp lúc **sự kiện xảy ra** khác **thời điểm collector nhận**.
- Thiết bị có clock skew có thể khiến các log đến “sớm hơn” request.
- Trace spans thường ghi start/end dựa trên clock của process; phép trừ cross-host timestamp có thể sai nếu skew lớn.
- **Monotonic duration measurement** ở từng tiến trình/SDK thích hợp để đo elapsed time; wall-clock timestamps cần đồng bộ để correlation.
- DNS caching, rate aggregation và flow log delivery có thể thêm độ trễ quan sát.

Không suy thứ tự nhân quả hoàn toàn từ timestamp logs ở hai host nếu **đồng hồ chưa được xác minh**.

## 5. Network metrics: định nghĩa và chọn đúng kiểu

### 5.1. Counter

**Counter** là đại lượng tích lũy thường chỉ tăng, trừ khi process restart/reset; ví dụ packets transmitted, TCP retransmission events, HTTP requests, failed TLS handshakes.

Đánh giá tốc độ bằng **rate/increase trong một cửa sổ** thay vì so trực tiếp tổng counter giữa các host uptime khác nhau.

~~~text
net_tx_bytes_total{node="worker-a",interface="eth0"}
net_rx_packets_total{node="worker-a",interface="eth0"}
tcp_retransmissions_total{node="worker-a"}
http_requests_total{service="orders",status_code="503"}

Đây là tên metric GIẢ ĐỊNH để diễn giải,
không phải tên mặc định của node_exporter/Prometheus/OTel.
~~~

Ví dụ logic:

~~~text
Bytes gửi trong 60 giây = counter(t1) - counter(t0)
Bytes/giây = delta_bytes / 60
Bits/giây = (delta_bytes * 8) / 60

Chỉ dùng trực tiếp phép trừ khi KHÔNG có counter reset.
Trong hệ thống metrics cần dùng hàm xử lý counter resets phù hợp.
~~~

Để so utilization với line rate, cần biết **interface tốc độ nào, duplex, overhead, đường bonding, tunnel**, và metric đo bytes ở lớp nào. 100 Mbps theo một metric ứng dụng không đồng nghĩa NIC 100 Mbps đã bão hòa.

### 5.2. Gauge

**Gauge** có thể tăng hoặc giảm: current active connections, queue length, số sessions, link operational state, số healthy upstreams.

~~~text
active_connections{service="orders"}
proxy_pending_requests{gateway="edge-gw"}
available_upstreams{service="payments"}
collector_export_queue_length{pipeline="traces"}

Tên ví dụ, cần map sang telemetry thực tế của sản phẩm.
~~~

Gauge tức thời có thể bỏ lỡ **spikes ngắn** nếu scrape interval lớn. Tránh suy không có congestion chỉ vì sample lúc kiểm tra thấy queue bằng 0.

### 5.3. Histogram

**Histogram** phân phối quan sát vào các buckets; thường dùng cho DNS query duration, TCP connect duration, TLS handshake, HTTP request duration, proxy upstream latency.

~~~text
network_path_request_duration_seconds_bucket{service="orders",le="0.1"} ...
network_path_request_duration_seconds_bucket{service="orders",le="0.5"} ...
network_path_request_duration_seconds_bucket{service="orders",le="+Inf"} ...
network_path_request_duration_seconds_sum{service="orders"} ...
network_path_request_duration_seconds_count{service="orders"} ...

Tên minh họa theo classic Prometheus histogram;
bucket là cumulative, không phải đếm riêng từng khoảng.
~~~

Không tính “p95 trung bình” bằng cách lấy trung bình p95 của từng replica. Với classic histogram, cần **hợp buckets trước khi ước tính quantile** nếu muốn p95 tổng.

### 5.4. Ví dụ PromQL trên metric giả định

Các biểu thức chỉ dùng khi đã có metric/labels tương ứng; không sao chép như thể đây là metric mặc định.

~~~promql
# Tốc độ HTTP requests/giây theo service:
sum by (service) (
  rate(http_requests_total[5m])
)

# Tỷ lệ responses 5xx (phần trăm) theo service:
100 *
sum by (service) (
  rate(http_requests_total{status_code=~"5.."}[5m])
)
/
clamp_min(
  sum by (service) (rate(http_requests_total[5m])),
  1e-9
)

# Ước tính p95 qua classic histogram buckets:
histogram_quantile(
  0.95,
  sum by (le, service) (
    rate(network_path_request_duration_seconds_bucket[5m])
  )
)

# TCP retransmission events mỗi giây theo node:
sum by (node) (
  rate(tcp_retransmissions_total[5m])
)
~~~

**Cẩn trọng:** PromQL chỉ có ý nghĩa khi exporter có labels đúng, histogram buckets đủ phân giải, time series không bị mất dữ liệu và hệ thống không double-count traffic. Đặc biệt, **tốc độ retransmission** không phải “tỷ lệ packet loss” theo một phép chia mặc định: một packet có thể retransmit nhiều lần, đường chồng lấn với loss/congestion/reordering và cần đối chiếu counters khác.

### 5.5. Tổ chức metric theo RED và USE

| Khung | Thành phần | Ví dụ network path |
|---|---|---|
| **RED (service request)** | Rate | Request/giây ở API gateway hoặc service |
| | Errors | 5xx, timeout, TLS handshake failures, rejected upstream requests |
| | Duration | p50/p95/p99 end-to-end hoặc per-upstream |
| **USE (resource)** | Utilization | NIC bandwidth utilization, CPU proxy, connection pool |
| | Saturation | Backlog, queue occupancy, pending connections, drops |
| | Errors | NIC errors, interface drops, socket resource errors |

RED phù hợp **request-oriented services**; USE phù hợp **resource/interface capacity**. Không mọi network path đều có HTTP request count. Với DNS, chọn query rate/error/latency; với VPN, chọn tunnel up/down, session count, packet loss và throughput theo tầng thích hợp.

## 6. Metrics theo từng chặng của network path

Một biểu đồ **"network latency"** chung thường không đủ. Cần xác định latency được đo **ở đâu**, có gồm thời gian xử lý ứng dụng/DB hay không và đo bằng loại kết nối nào.

### 6.1. DNS resolution

| Tín hiệu | Cách diễn giải | Cẩn trọng |
|---|---|---|
| DNS queries/giây | Tải trên resolver | Cache giảm queries nhưng không giảm số request ứng dụng |
| Query duration p95/p99 | Thời gian xử lý/trả lời theo vị trí đo | Client timeout khác server response latency |
| NXDOMAIN rate | Tên miền không tồn tại | Có thể do app config/typo, không mặc định là tấn công |
| SERVFAIL rate | Resolver không xử lý được | Có thể do upstream, DNSSEC, timeout hoặc cấu hình |
| Timeouts/retries | Thiếu phản hồi kịp thời | Không tự cho biết packet bị drop ở đâu |
| Cache hit rate | Hiệu quả cache tại resolver | Cache hit cao không chứng minh record đúng |
| DNS answer changes | Endpoint IP/CDN/policy thay đổi | Có thể bình thường do scaling/GSLB |

**Ví dụ:** DNS p95 tăng nhưng HTTP latency của những request tái sử dụng kết nối vẫn thấp. Điều này có thể do chỉ **new connections** cần resolve; không được kết luận DNS “không ảnh hưởng người dùng” từ một biểu đồ HTTP trung bình.

### 6.2. TCP connection và transport

| Tín hiệu | Ý nghĩa gợi ý | Không được suy trực tiếp |
|---|---|---|
| SYN attempts/connection failures | Khả năng tạo kết nối | Timeout có thể do firewall, route, server down hoặc backlog |
| SYN retransmits | Không hoàn thành bắt tay trong lần thử | Không chỉ rõ link nào mất packet |
| Smoothed RTT / RTT samples | Ước tính round-trip ở một socket/điểm đo | Không bằng total HTTP request latency |
| TCP retransmissions | Segment phải truyền lại | Không đồng nghĩa packet loss ratio chính xác |
| Receive/send queue | Buffering/congestion ở endpoint | Không xác định nguyên nhân nếu thiếu CPU/app/network context |
| Reset (RST) events | Kết nối bị reset | RST có thể do app/proxy/client chính đáng |
| Connections in TIME_WAIT/ESTABLISHED | Socket state và churn | TIME_WAIT cao không tự là lỗi |
| Interface drops/errors | Drop/error tại NIC/queue/driver theo metric | Không tự chỉ ra request hoặc user nào bị ảnh hưởng |

TCP retransmissions tăng cùng **RTT p99, SYN timeout và interface queue drops** gợi ý vấn đề transport, nhưng vẫn cần phân tích route, tải backend, proxy retries và vị trí đo. Nếu mạng mất gói ở hop không instrumented, network metrics ở endpoint có thể chỉ phản ánh **hậu quả**, không xác định vị trí gốc.

### 6.3. TLS và mTLS

| Tín hiệu | Nguyên nhân cần khảo sát | Bằng chứng bổ sung |
|---|---|---|
| TLS handshake failures | Cert expired, SAN mismatch, trust root sai, protocol/cipher mismatch, client cert thiếu | TLS alert, peer config, cert metadata |
| Handshake duration | New connection latency, CA/key operation, CPU load | Connection reuse, CPU/proxy metrics |
| mTLS authorization rejects | Peer identity không được policy cho phép | Service principal, policy ID, AuthZ verdict |
| Certificate expiry horizon | Nguy cơ outage khi hết hạn | Inventory issuer, cert age, rotation status |
| Proxy connection resets | Failed upstream TLS/transport hoặc proxy policy | Phân biệt upstream/downstream và reset reason |

**Không bao giờ** dùng `verify=false` hoặc bỏ hostname validation để làm telemetry “xanh”. TLS success phải là kết nối **được xác minh đúng peer và trust chain** trong phạm vi policy.

### 6.4. Gateway, WAF, load balancer và service mesh

- **Request rate, status code distribution:** phân biệt status do **gateway tạo** và do **upstream trả** nếu sản phẩm cung cấp.
- **Upstream connect time:** thời gian thiết lập kết nối tới backend, thường khác upstream response time.
- **Request duration / time to first byte:** cần biết tính cả queue/TLS và response streaming không.
- **Active/pending connections:** nhận diện backlog, pool pressure, fail-open/fail-closed behavior.
- **Retry count và attempts per request:** retry có thể tạo nhiều upstream requests cho một client request.
- **Routing decisions:** matched route, cluster/backend, endpoint, canary version, gateway policy.
- **WAF/IPS deny events:** rule ID, action, source context, false positive baseline.
- **Mesh peer identity/mTLS:** service/workload principals và policy decisions, chỉ trên đường thực qua mesh dataplane.

**Một downstream 504 có thể do upstream không phản hồi trước deadline**, không có nghĩa upstream trả HTTP 504. Nếu **gateway 502** là do TLS handshake tới origin thất bại, chỉ nhìn app logs có thể không thấy request nào đến backend.

### 6.5. Kubernetes CNI / NetworkPolicy / Service

Các vấn đề đặc trưng:

- Pod IP và endpoint thay đổi theo rollout/scale.
- Service **ClusterIP** được datapath chuyển tiếp tới Pod endpoint.
- CNI enforcement của NetworkPolicy phụ thuộc plugin và traffic path.
- HostNetwork, node-local DNS, egress gateway và secondary interfaces có phạm vi policy khác thường.
- SNAT/DNAT có thể thay source/destination IP quan sát tại các chặng.

Một CNI flow record có thể bao gồm **source/destination Pod identity, namespace, policy verdict và TCP port** theo triển khai; nhưng không mặc định mọi CNI có cùng fields. Luôn xem **capabilities thật**, CNI configuration và nơi nó đo packet **trước hay sau NAT**.

### 6.6. Database và downstream dependencies

Khi request Orders → DB chậm, những metric có ích gồm:

- Database **connection pool wait duration**, available/in-use connections.
- TCP connection establishment tới DB, TLS errors khi có.
- DB query duration, lock waits và concurrent active queries.
- Credentials/authentication failures, connection limits và resource saturation.
- Retries ở client/proxy nếu có, cả số lần gọi thực tới DB.

Nếu trace báo `db.query` mất 450 ms, **chưa đủ kết luận network có 450 ms latency**; khoảng đó có thể gồm pool wait, SQL execution, locks hoặc data transfer. Cần span breakdown và DB/transport metrics riêng.

## 7. Logs và events: câu trả lời ở mức sự kiện

Đối với một sự cố, log có giá trị khi biết **nó được tạo ở đâu**, **có đúng timestamp**, **nó mô tả hành động hay chỉ mô tả kết quả**, và **nó có được thu thập đầy đủ không**.

### 7.1. Nguồn logs theo network path

| Nguồn | Dữ liệu thường có thể thu | Rủi ro diễn giải |
|---|---|---|
| DNS resolver | qname, qtype, response code, latency, resolver identity | Cache/client DoH có thể khiến query không đến resolver đó |
| Host OS/kernels | Link state changes, routes, socket errors, kernel counters | Log kernel không luôn tạo cho từng packet |
| Firewall | Allow/deny, rule ID, source/destination/protocol/port | Policy log có thể disabled hoặc sampled |
| VPC/VNet flow logs | Flow metadata, action, bytes/packets theo interval | Aggregated flow không phải packet-by-packet |
| Kubernetes CNI | Flow verdict, source/destination Pod identity/policy | Không luôn bao phủ node/host traffic |
| L4/L7 LB | Backend selection, connect failures, resets, status | Một request qua proxy có thể phát sinh hai flows |
| API gateway/WAF | HTTP route, status, upstream time, block rule | L7 log không xuất hiện khi TCP/TLS fail trước HTTP |
| Service mesh | mTLS principal, policy reject, retry, route | Miss các paths không được capture |
| Application | Business error, auth decision, request IDs | Không phản ánh packet drop trước app |
| IDS/IPS | Detection signature, alert confidence, drop action | Alert không đồng nghĩa attack thành công |

### 7.2. Log mẫu đã lược bỏ thông tin nhạy cảm

~~~json
{
  "timestamp": "2026-11-28T07:05:12.340Z",
  "observed_at": "2026-11-28T07:05:12.410Z",
  "source": "api-gateway",
  "environment": "lab",
  "event_type": "http_upstream_timeout",
  "service": "orders",
  "route": "GET /orders/{orderId}",
  "status_code": 504,
  "status_origin": "gateway",
  "upstream_service": "orders-api",
  "upstream_connect_ms": 12,
  "upstream_response_ms": 800,
  "request_id": "req-lab-7f21",
  "trace_id": "a3a3a3a3a3a3a3a3b4b4b4b4b4b4b4b4",
  "policy_decision": "allow",
  "diagnostic_note": "synthetic-example"
}
~~~

**Giả định:** dữ liệu này là ví dụ tự tạo; không phải log thu thập từ hạ tầng thật. `trace_id` chỉ có ích nếu gateway và các service phát/nhận cùng trace context đúng. Log từ gateway có thể cho biết **gateway timeout**, nhưng chưa đủ để kết luận 800 ms là thời gian truyền mạng.

### 7.3. Các trường nên có

| Trường | Lý do | Cẩn trọng |
|---|---|---|
| Event timestamp, ingest timestamp | Time correlation, nhận diện delivery lag | UTC, clock skew |
| Service, environment, region/zone | Chọn failure domain | Không gắn địa chỉ nhạy cảm công khai |
| Request ID / trace ID / span ID | Liên kết với request workflow | IDs không thay identity; kiểm tra format |
| Source/destination logical identity | Hiểu service-to-service flow | Pod UID/namespace thường tốt hơn Pod IP ngắn hạn |
| Source/destination IP:port + protocol | So flow và firewall decision | NAT/reuse cần context |
| Direction/measurement point | Biết đây là ingress/egress ở đâu | Không đồng nhất upstream/downstream |
| Outcome/reason | Allow/deny/reset/timeout; HTTP status origin | “Deny” ở WAF khác deny ở firewall |
| Policy/rule ID và version | Chứng minh quyết định ở thời điểm đó | Policy drift giữa controllers/regions |
| Sampling/drop indicators | Biết dữ liệu là mẫu hay tổng | Không suy số tuyệt đối từ sampled events |
| Sanitized error class | Phân loại sự cố | Không log raw credential/secret |

### 7.4. Không ghi raw credential để dễ debug

Không log access tokens, cookies, Authorization header, API keys, TLS private keys, user passwords hoặc full request bodies nhạy cảm. **IP, hostname, user ID và DNS query name cũng có thể là dữ liệu nhạy cảm hoặc nhận dạng cá nhân** theo bối cảnh.

Thiết kế:

- **Schema chuẩn** cho network events và application events.
- **Redaction/tokenization** trước khi lưu và giới hạn nguồn log có thể chứa secrets.
- **Role-based access**, retention, encryption và audit người truy cập.
- **Allowlist fields** thay vì dump toàn bộ HTTP headers/body.
- Phân biệt hệ thống chính thức từ **test/synthetic events** để không làm hỏng metrics sự cố.

### 7.5. Flow log aggregation và sampling

Một cloud flow record thường tổng hợp traffic trong khoảng thời gian, không ghi từng packet. Một số nền tảng ghi ACCEPT/REJECT theo policy ở nơi thu khác với application outcome. Những hệ thống network telemetry có thể sample flows hoặc chỉ ghi flows khớp điều kiện.

**Không có flow log** có nhiều khả năng: traffic không đi qua interface đó, logging chưa bật, sampling không bắt trúng, pipeline mất dữ liệu, filter sai, hoặc traffic bypass measurement point. Cần **pipeline health metric** và positive controls trước khi khẳng định “không có traffic”.

## 8. Distributed tracing: từ một request tới nhiều spans

Một **trace** biểu diễn các thao tác liên quan của một workflow, thường mang một **trace ID** chung. Mỗi **span** ghi một operation có thời điểm bắt đầu/kết thúc, parent/links, attributes, status và tùy SDK có events. Trong hệ thống HTTP/gRPC, trace context thường được truyền qua các headers/protocol metadata phù hợp.

### 8.1. Ví dụ request đi qua nhiều services

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant G as Gateway
    participant O as Orders API
    participant P as Payments API
    participant D as Database
    B->>G: GET /checkout (request context)
    G->>O: Upstream HTTP/gRPC + trace context
    O->>P: Charge/order verification
    P->>D: Query/update
    D-->>P: Result
    P-->>O: Payment result
    O-->>G: HTTP response
    G-->>B: HTTP response
~~~

Một trace mẫu:

~~~text
Trace: 8c8c... (minh họa)
  gateway.handle_request            920 ms
    orders.http_server              875 ms
      orders.authz                   18 ms
      payments.http_client          810 ms
        payments.http_server         790 ms
          payments.db_pool_wait      500 ms
          payments.db_query         245 ms
~~~

Thời lượng các child spans có thể **chồng lấn**, không nên mặc định tổng thời lượng con bằng thời lượng cha. Nếu network latency là nghi vấn, cần phân biệt **client span duration**, **server span duration**, thời điểm gửi/nhận theo clock, retries và queue. Những “khoảng trống” giữa spans có thể do network, proxy, queue hoặc **độ trễ instrumentation**; không nên gán tất cả cho packet transit.

### 8.2. W3C Trace Context và sự lan truyền

Một số hệ thống HTTP truyền trace context bằng các header như `traceparent` và `tracestate`. Ví dụ cấu trúc `traceparent`:

~~~text
traceparent: 00-a3a3a3a3a3a3a3a3b4b4b4b4b4b4b4b4-1111111111111111-01

version-trace_id(16-byte)-parent_span_id(8-byte)-flags
~~~

**Quan trọng:**

- Header nhận được từ client là **dữ liệu đầu vào không tin cậy**; không được dùng nó làm chứng cứ authentication/authorization.
- Trace ID phải không đoán được nếu hệ thống dùng cho correlation có yêu cầu chống trùng; **không chứa user ID, token hoặc dữ liệu bí mật**.
- Khi qua trust boundary, gateway có thể chuẩn hóa/khởi tạo context theo policy và quy tắc sampling riêng; tránh cho client ép sampling 100% không kiểm soát.
- `tracestate` và `baggage` (nếu dùng) phải được quản trị vì có thể tạo leak hoặc cardinality; không đưa PII/bearer token vào baggage.
- Không phải giao thức TCP/UDP tùy ý có cơ chế propagate trace context; cần instrumentation/proxy hỗ trợ.

### 8.3. Client span và server span trả lời gì?

| Span | Thời gian thường đo | Giới hạn |
|---|---|---|
| HTTP client span tại Orders | Thời gian client đợi Payments, có thể gồm retries/connection waiting | Không tách tự động RTT, network queuing, server processing |
| HTTP server span tại Payments | Thời gian handler/server thấy request | Có thể không gồm queue trước server/gateway |
| DB client span | Tổng thời gian SDK/driver call | Có thể gồm pool wait, connection establishment, query, transfer |
| Ingress proxy span | Thời gian gateway xử lý downstream request | Có thể gồm client read/write, upstream retry và buffering |
| Mesh proxy span | Span ở đoạn L7 nếu được instrumented | L4-only traffic có thể không có spans HTTP |

**Distributed tracing không phải traceroute.** Nó theo dõi **các thao tác ứng dụng được instrumented**, không tự phát hiện từng router/switch, link vật lý hoặc packet mất trên đường.

### 8.4. Traces thất lạc và chuyện sampling

Một request có thể không có trace vì:

- Sampling policy loại nó trước hoặc sau khi capture.
- Một client/service không truyền `traceparent`.
- Gateway loại bỏ/khởi tạo context mới theo security policy.
- Span exporter/collector queue đầy, backend ingest lag hoặc storage retention hết.
- Service không được instrumented, giao thức là opaque L4.
- Propagation sử dụng protocol chưa được hỗ trợ hoặc có version mismatch.

Không diễn giải “không có trace của request thất bại” thành “request không đi qua service”. Khi incident, đối chiếu **request IDs, access logs, flow metadata, collector health**.

### 8.5. Tracing và retries

Một request tại gateway có thể tạo **nhiều upstream attempts**. Một trace được instrumented tốt cần phân biệt:

- Original downstream request.
- Each upstream attempt/retry.
- Chọn backend instance/region.
- Timeout hay reset giữa các attempts.
- Ghi nhận network/request latency cho đúng attempts.

Nếu count retry attempts như client requests, dashboard traffic có thể tăng sai và error budget không phản ánh trải nghiệm người dùng.

## 9. Ghép metrics, logs và traces vào một câu chuyện

### 9.1. Các khóa correlation

| Khóa | Hữu ích cho | Giới hạn |
|---|---|---|
| **Trace ID / Span ID** | Ghép spans và application/proxy logs | Không có ở raw packets hoặc service không propagate context |
| **Request ID** | Gắn gateway và backend logs | Proxy có thể cấp ID khác; cần propagation |
| **Workload identity** | Cặp service/namespace/SA theo topology | Labels/identity thay đổi theo rollout; không đồng nghĩa user |
| **5-tuple** | Protocol, source IP:port, dest IP:port | NAT và port reuse tạo ambiguity |
| **Connection ID** | Proxy/network connection events | Một connection có nhiều HTTP requests |
| **Timestamp + observation point** | Thu hẹp cùng thời gian và đường | Clock skew, log delivery lag, aggregation |
| **Deployment/policy version** | Tương quan với thay đổi | Temporal correlation không tự chứng minh causation |
| **Metric exemplar** | Từ latency histogram tới trace mẫu | Exemplar là mẫu, không đại diện mọi request |

### 9.2. 5-tuple và NAT: tránh ghép sai

Một **5-tuple** gồm protocol, source IP, source port, destination IP, destination port. Ví dụ:

~~~text
Trước SNAT:
  TCP 10.1.4.25:51042 -> 198.51.100.20:443

Sau SNAT (minh họa):
  TCP 203.0.113.9:62001 -> 198.51.100.20:443

Sau reverse proxy:
  TCP 10.2.3.10:42881 -> 10.2.5.17:8080
~~~

Các địa chỉ IPv4 trong ví dụ thuộc dải riêng hoặc **dải tài liệu**. Đây có thể là **hai/từ ba connection segments khác nhau**; không được ghép chỉ bằng IP đích và port. Cần **NAT translation records hoặc connection IDs, thời gian, proxy request ID, host/interface và topology** khi có.

### 9.3. Điều kiện tương quan mạnh và yếu

~~~text
MẠNH (trong phạm vi cùng workflow):
  Trace ID được propagate đúng
  + gateway request ID tương ứng
  + backend span / access log
  + proxy upstream target & time window hợp lệ

TRUNG BÌNH:
  service identity + source/destination port
  + close timestamp + route/policy version

YẾU:
  "Hai log xảy ra cùng phút"
  hoặc "cùng IP public sau NAT"
~~~

**Chỉ rõ độ tin cậy trong báo cáo sự cố**: “bằng chứng chỉ ra” khác “nghi ngờ do cùng thời điểm”. Đừng ép flow sample ghép với trace mẫu để suy rằng đó là request giống nhau khi thiếu khóa định danh.

## 10. Telemetry pipeline: từ instrumentation tới phân tích

Một pipeline điển hình có thể kết hợp:

~~~mermaid
flowchart TB
    subgraph SOURCES["Instrumentation / sources"]
      NET["Host / CNI / firewall / cloud flow"]
      HTTP["Gateway / service / proxy"]
      DNS["DNS / PKI / TLS logs"]
      APP["Application traces / logs"]
    end
    NET --> AGENT["Local agents / exporters"]
    HTTP --> AGENT
    DNS --> AGENT
    APP --> AGENT
    AGENT --> COL["Collectors: receive, batch, enrich, filter, sample"]
    COL --> MET["Metric backend + dashboards"]
    COL --> LOG["Log store / search"]
    COL --> TRACE["Trace backend / service graph"]
    COL --> HEALTH["Pipeline self-telemetry / alerts"]
    MET --> SOC["SRE / SOC triage"]
    LOG --> SOC
    TRACE --> SOC
~~~

**OpenTelemetry** có khái niệm **metrics, logs, traces, resource attributes và Collector** để tổ chức instrumentation/pipeline. Nhưng **network interfaces, firewall flow records và CNI policy verdicts không tự xuất hiện dưới dạng spans**: cần exporter/receiver/agent/adapter phù hợp và ánh xạ fields theo source.

### 10.1. Nên enrich bằng gì?

- Cluster, environment, region/zone, node, namespace, workload/ServiceAccount identity.
- Service name/version, deployment revision, gateway route/policy ID.
- Network segment/subnet, interface, direction và observation point.
- Trace/request IDs khi thật sự có propagation.
- Sampling metadata và collector version.

Không nên thêm raw user ID, full URL paths có object ID, dynamic IP:port hoặc trace ID thành **metric label** cho mọi request vì **cardinality bùng nổ**. Những fields high-cardinality thích hợp hơn ở **logs/traces** có sampling/retention có kiểm soát.

### 10.2. Collector có thể trở thành điểm lỗi

Nếu queue đầy, exporter bị timeout hoặc backend quá tải:

- **Metrics bị trễ hoặc gap**.
- Logs/spans bị drop hoặc chỉ còn một phần.
- Sampling policy có thể thiên lệch về loại request được giữ.
- Tài nguyên node/collector tăng, có thể ảnh hưởng ứng dụng nếu chia sẻ CPU/memory.

Các chỉ số tự giám sát nên gồm **accepted/refused records, dropped items, queue utilization, export failures, retries, ingest lag và collector memory/CPU** theo tên chính xác của hệ thống đang dùng.

### 10.3. Tránh telemetry tự gây sự cố

Không bật full payload logging, 100% tracing hoặc packet capture trên mọi production interface mà chưa có đánh giá:

- Lưu lượng/thông lượng backend telemetry.
- CPU/RAM của agent và proxy.
- Data retention, encryption, privacy.
- Thông tin nhạy cảm có thể xuất hiện trong packet/body.
- Giới hạn sample, filter và backpressure.
- Quy trình tắt hoặc thu hẹp khi collector/agent gây ảnh hưởng SLO.

## 11. Sampling, cardinality và các khoảng trống quan sát

### 11.1. Vì sao sampling cần nhưng cũng nguy hiểm?

Với hàng triệu requests/ngày, thu **100% spans, access logs, flows** có thể vượt chi phí/throughput và lộ nhiều dữ liệu không cần thiết. Sampling chọn một phần sự kiện.

| Cơ chế | Ý tưởng | Rủi ro phân tích |
|---|---|---|
| **Head-based trace sampling** | Quyết định giữ/bỏ trace gần lúc khởi tạo | Có thể bỏ sót các lỗi hiếm xảy ra sau đó |
| **Tail-based trace sampling** | Quan sát các spans rồi chọn traces theo kết quả | Cần buffer/ownership/latency; nếu thiếu spans có thể quyết định sai |
| **Probabilistic flow sampling** | Chọn một tỷ lệ flows/packets | Rare attack/short connections có thể không xuất hiện |
| **Log filtering** | Chỉ giữ event classes hoặc severity nhất định | Có thể mất context của lỗi cấp thấp |
| **Metric aggregation** | Tổng hợp thay vì lưu từng request | Không thể khôi phục sự kiện cụ thể từ aggregate |

Với tail sampling, việc ghép đủ spans của một trace trên nhiều collector instances cần chiến lược routing/consistent decisions phù hợp. Nếu bỏ một nửa spans, trace graph có thể tạo **kết luận sai về chặng mất thời gian**.

### 11.2. Sampling bias trong điều tra

Giả sử tỷ lệ lỗi thật là **0,1%**. Head sampling 1% có thể giữ rất ít trace lỗi trong một khoảng ngắn, nhất là khi tổng request thấp. Tránh kết luận “không có lỗi” từ việc không thấy error trace. So với **metrics tổng số lỗi, gateway logs và CNI flow counters**.

Ngược lại, một trace backend toàn lỗi do tail sampling **không đại diện cho phân bố latency của toàn traffic**. Đừng tính global p95 bằng trung bình spans trong một tập trace cố ý thiên về lỗi.

### 11.3. High cardinality từ network identifiers

Một metric có labels:

~~~text
request_duration_seconds{
  user_id="random-user",
  source_ip="dynamic-ip",
  source_port="ephemeral",
  request_id="unique",
  path="/orders/123456"
}
~~~

có thể sinh một time series mới cho hầu hết requests, tăng chi phí index, CPU/memory và làm dashboards/alerts chậm. **Không dùng request ID/trace ID/token/full URL với dynamic object ID làm metric labels**.

Thay vào đó:

~~~text
request_duration_seconds{
  service="orders",
  route="GET /orders/{orderId}",
  environment="production",
  status_class="5xx"
}
~~~

Những identifiers chi tiết chỉ xuất hiện ở **logs/traces** khi cần, với retention và access controls riêng. Cũng cần kiểm tra **host/pod UID** khi autoscale mạnh, vì dù ít nhạy cảm hơn user ID chúng vẫn có cardinality đáng kể.

### 11.4. Biết “lỗ hổng telemetry” là gì

Một collector sống khỏe không chứng minh **mọi source vẫn gửi dữ liệu**. Cần quan sát:

- **Source heartbeat** và ingestion delay theo loại dữ liệu.
- Expected vs observed event volume theo service/namespace/region.
- Collector receiver/exporter drop/retry errors.
- Sampling configuration và bản ghi decision.
- Time synchronization và timestamp anomalies.
- Gaps do rotation/log agent restart, throttling hoặc network policy chặn exporter.
- Đường truyền telemetry có TLS/auth, tránh giả mạo hoặc gửi giả events.

**Nếu log mất đúng lúc incident, không được mặc định “không có traffic đáng ngờ”.**

## 12. SLI, SLO và alerting cho network path

Đừng cố đặt một ngưỡng chung cho mọi mạng. Một ứng dụng realtime, một batch backup qua VPN và một API checkout có ngân sách latency/loss khác nhau.

### 12.1. Phân biệt outcome của người dùng và health hạ tầng

| Chỉ số | Tầng | Câu hỏi |
|---|---|---|
| Successful HTTP requests / total eligible requests | End-user/request SLI | Người dùng có thực hiện được thao tác? |
| p95 latency của request ở ingress | End-user/request SLI | Tốc độ người dùng cảm nhận ra sao? |
| DNS query success/duration | Dependency SLI | Service discovery có đang hoạt động? |
| TCP connect success/RTT | Transport SLI | Tạo connection có ổn không? |
| Gateway upstream timeout rate | Proxy SLI | Gateway có đạt upstream trong deadline không? |
| CNI policy deny count | Security/flow metric | Policy có chặn luồng nào? |
| TLS/mTLS handshake failure rate | Security/connectivity | Peer validation/trust đang gặp lỗi? |
| NIC drops/retransmissions | Infrastructure symptom | Có dấu hiệu mất gói/buffer pressure? |
| Collector export success/delay | Observability SLI | Dữ liệu có đáng tin để điều tra không? |

**Không định nghĩa p95 HTTP request latency là “network-only latency”**: nó có thể gồm queue, computation, API auth, DB, retries và response transfer.

### 12.2. Ví dụ SLO minh họa

~~~text
SLO lab mẫu (KHÔNG phải tiêu chuẩn chung):
  Trong cửa sổ đánh giá 28 ngày,
  ít nhất 99,9% requests "eligible" tới Checkout API
  phải trả kết quả thành công theo định nghĩa nghiệp vụ
  và phần lớn requests đạt thời gian phản hồi đã thỏa thuận.

Định nghĩa "eligible" phải ghi rõ:
  - Loại request và route.
  - Có loại 4xx do user invalid input không?
  - Gateway timeout được tính ra sao?
  - Có loại bỏ synthetic probes không?
  - Endpoint health/probes có tách khỏi business traffic không?
~~~

Các con số chỉ là bài tập; mỗi tổ chức đặt SLO theo mục tiêu sản phẩm và phương pháp đo. Nếu tính **HTTP 403 của user không đủ quyền** là “availability outage”, SLI có thể sai; nếu bỏ toàn bộ 5xx của gateway khỏi mẫu, cũng làm tỷ lệ thành công đẹp giả.

### 12.3. Cảnh báo theo triệu chứng + tác động

Một alert tốt gắn:

1. **Người dùng bị ảnh hưởng:** error rate/latency vượt ngưỡng đủ lâu.
2. **Failure domain:** cluster, region, gateway route, Service, node pool.
3. **Tín hiệu gợi ý nguyên nhân:** DNS failures, TLS errors, TCP retransmissions, CNI denies, backend pool pressure.
4. **Độ tin cậy telemetry:** pipeline gaps/counter reset/sampling changes.
5. **Runbook:** nơi tra logs/traces, đối chứng và owner liên quan.

Không nên pager chỉ vì một metric `CNI denied flows > 0`: default-deny có thể cố ý chặn các kết nối không được phép. Cần so với baseline, source workload identity, policy change và service impact.

### 12.4. Triển khai dashboard theo góc nhìn

**Dashboard A — End-user/edge:** request rate, 4xx/5xx (phân nguồn), p95/p99, TLS errors, origin connect time, upstream retries.

**Dashboard B — Network path:** DNS p95/RCODE, TCP connect/RTT/retransmissions, interface utilization/drops, firewall/CNI verdicts, VPN tunnel state, NAT gateway errors.

**Dashboard C — Dependencies:** service version, DB pool wait, backend queue, mesh mTLS/authz, EndpointSlice changes, retries, database errors.

**Dashboard D — Telemetry health:** collector queue/drop/export lag, source heartbeats, sampling change, clock sync and pipeline availability.

Phân chia giúp không trộn **user impact** với **underlying symptoms**. Tất cả dashboards cần cùng timezone/time range, và có đường drill-down tới log/trace khi hệ thống có correlation.

## 13. Case study: gateway 504 nhưng API CPU vẫn bình thường

### 13.1. Mô tả tình huống

Giả sử vào 14:00, một cluster lab có luồng:

~~~text
Browser → DNS → Edge LB → Ingress gateway
  → Orders API (Kubernetes)
  → Payments service (mesh)
  → Payments DB
~~~

Triệu chứng:

- Gateway HTTP 504 tăng khi người dùng checkout.
- CPU Orders API chỉ khoảng mức bình thường.
- Network interface throughput của node không cao.
- Dashboard latency trung bình trông vẫn tốt nhưng p99 tăng.
- Lúc 13:58 có một thay đổi cấu hình connection pool ở Payments.

**Không kết luận pool change là nguyên nhân chỉ vì cùng thời điểm**. Đây mới là giả thuyết cần xác minh.

### 13.2. Thu ba tín hiệu

**Metrics:** Gateway `5xx_rate` tăng; `upstream_connect_duration` không tăng nhiều; `upstream_response_duration` và `payments_db_pool_wait_p99` tăng; node `tcp_retransmission_rate` không đổi nhiều trong failure domain tương ứng.

**Logs:** Gateway ghi `upstream_response_timeout`, route `POST /checkout`, upstream `orders-api` và request ID. Orders application ghi Payments call timeout. Payments logs cho thấy DB pool acquisition timeout và pool saturation events; DB server vẫn healthy.

**Traces:** Traces được sample cho thấy Orders server chờ Payments client span; Payments spans có `db_pool_wait` lớn trước `db_query`. Không có dấu hiệu bất thường về TCP connect/TLS handshake trong những paths được đo.

### 13.3. Diễn giải có bằng chứng

~~~mermaid
flowchart TD
    A["Gateway 504 tăng"] --> B["Gateway upstream connect time có tăng?"]
    B -->|"Không đáng kể"| C["Gateway upstream response time tăng"]
    C --> D["Trace Orders → Payments chậm"]
    D --> E["Payments DB pool wait p99 tăng"]
    E --> F["Pool capacity / leak / DB availability là giả thuyết"]
    F --> G["Kiểm tra DB pool metrics, logs, load và change"]
    G --> H["Fix có canary; đối chiếu 5xx/p99/queue sau thay đổi"]
~~~

**Kết luận có điều kiện:** bằng chứng **nghiêng về nghẽn connection pool** tại Payments hơn là packet loss ở node. Tuy nhiên cần xác minh source metrics, samples và control test, không phủ nhận hoàn toàn network issue nếu telemetry coverage thiếu.

### 13.4. Những cách làm sai

- Chỉ xem gateway 504 rồi yêu cầu mở rộng timeout lên vài phút.
- Thấy Orders CPU bình thường rồi loại mọi dependency khỏi nghi vấn.
- Xem một trace lỗi rồi suy toàn bộ 5xx đều do pool.
- Thấy retransmissions không tăng trên **một node** rồi kết luận toàn bộ network path không mất gói.
- Nhìn một event thay đổi lúc 13:58 rồi rollback ngay không có đối chứng tác động.
- Bật mọi access logs, trace payloads và packet capture vô hạn trong production để “có dữ liệu”.

### 13.5. Sau remediation nên đo gì?

- Request success/error và p95/p99 end-to-end theo route.
- Payments DB pool wait histogram, in-use/available connections.
- Gateway retry attempts và upstream timeouts.
- Queue saturation, DB query/lock time nếu liên quan.
- Collector ingestion completeness; xác minh spans/logs chưa bị drop.
- Regression trên workload canary và xác nhận service identity/authorization vẫn đúng.

## 14. Quy trình triage theo symptom, không theo công cụ

### Bước 1 — Xác nhận tác động thật

Xác định request route, user segment (không lưu PII không cần), failure window, tỷ lệ affected, status/error source và SLO. Một synthetic probe fail có thể báo môi trường test chứ chưa ảnh hưởng người dùng; một API trả `200` có thể vẫn sai dữ liệu nghiệp vụ.

### Bước 2 — Xác định chặng đầu tiên có bằng chứng lỗi

Từ client tới backend: DNS → TCP/TLS → edge/gateway → CNI/service → application → dependencies. Chọn **điểm trước và sau chặng nghi ngờ**, không gom mọi lỗi vào “mạng”.

### Bước 3 — Kiểm tra health của chính telemetry

So time range, clocks, pipeline delay, labels, sampling and dropped records. Một chỗ không có log chưa chứng minh packet không đến.

### Bước 4 — Tách transport và application

| Dấu hiệu | Điều nên điều tra |
|---|---|
| DNS failure tăng; TCP chưa được thử | Resolver, record, NodeLocal DNS, policy Egress |
| SYN timeout, TCP connect error | Firewall, route, backend listener, capacity, packet loss |
| TLS handshake failure | Certificate/hostname/trust/mTLS policy/protocol |
| Gateway upstream connect ổn, response time tăng | Backend queue, app, DB, retries |
| CNI deny đúng lúc lỗi | Policy, Pod labels, namespace, route/port, dual-sided isolation |
| App HTTP 403 nhưng network flow allow | Application AuthZ/service mesh L7 policy |
| DB pool wait cao | Pool settings, leak, DB capacity hoặc backend behavior |
| Traces thiếu nhưng logs/metrics có | Sampling/context propagation/collector |

### Bước 5 — Đối chiếu thay đổi

Kiểm tra deployments, NetworkPolicies, firewall, DNS/PKI rotation, gateway configs, service mesh rules, autoscaling và cloud routing changes trong failure window. **Tương quan thời gian là gợi ý, không tự chứng minh nguyên nhân**.

### Bước 6 — Thử giả thuyết an toàn

Dùng traffic lab/canary/approved probes; yêu cầu một **positive control** (dịch vụ healthy) và một **negative/control condition**. Nếu muốn thử NetworkPolicy deny, cần có **flow verdict deny** chứ không chỉ lỗi kết nối.

### Bước 7 — Remediate nhỏ nhất, theo dõi và rollback

Ưu tiên sửa endpoint/route/policy/cert/pool đúng nguyên nhân. Có người phê duyệt, version, canary, SLO và rollback. Không tắt TLS verification, xóa default-deny hoặc mở all ports/egress chỉ để dashboard xanh.

### Bước 8 — Hậu kiểm và cải thiện observability

Bổ sung những spans, fields, metrics hoặc health signals **thiếu để phân biệt sự cố lần sau**, tránh thu quá mức. Ghi nguyên nhân, evidence quality, timeline và owner.

## 15. Giám sát an ninh trên network path

Metrics, logs và traces còn giúp phát hiện rủi ro, nhưng **bảo mật mạng cần ngữ cảnh chính sách và hành vi**, không chỉ spike.

| Tín hiệu | Câu hỏi an ninh | Giới hạn |
|---|---|---|
| Firewall/CNI denies tăng theo source workload | Có workload thử lateral movement? | Có thể do discovery/probe hợp lệ |
| NXDOMAIN tăng từ một host | Có typo/config drift hoặc DNS abuse? | Không tự chứng minh tunneling/exfiltration |
| TLS invalid peer/certificate error | Có misconfiguration, rotation fail hoặc impersonation? | Không tự là tấn công thành công |
| Unexpected egress dest/port | Ứng dụng gọi ngoài dependency inventory? | CDN/shared IP và NAT có thể gây nhầm |
| Login/authz rejects cùng trace/request | Source service/user bị từ chối ở lớp nào? | Network allow khác user permission |
| Flow volume tăng ra vùng khác | Backup hợp lệ hay exfiltration? | Cần dữ liệu, owner, thời gian, approval |
| Policy config version khác giữa nodes | Có drift làm thay đổi access không? | Cần effective rule/flow tests |
| Trace từ service hợp lệ tới admin API lạ | Có khả năng misuse service identity? | Trace chỉ có khi instrumented |

### 15.1. Khi “không có dấu vết” là phát hiện quan trọng

Ví dụ một database nhận kết nối từ network lạ, nhưng CNI flow logs không có bản ghi tương ứng. Có nhiều khả năng: database nằm ngoài CNI coverage, traffic đến qua hostNetwork, flow sampling, thiếu logs, hoặc một đường khác. **Khoảng trống quan sát là điều cần kiểm tra**, không phải bằng chứng khẳng định “kết nối đã bypass chính sách” nếu chưa đối chiếu topology/measurement point.

### 15.2. Telemetry không thay enforcement

Log một request trái quyền nhưng không chặn nó không phải prevention. Trong kiến trúc Zero Trust/service mesh:

- **NetworkPolicy/firewall** giới hạn network reachability.
- **TLS/mTLS** xác minh peer và bảo vệ transport theo hop.
- **Service/application AuthZ** hạn chế operation và object.
- **Telemetry** xác định hoạt động, hậu kiểm và cảnh báo.

Các lớp này cần phối hợp; dùng một dashboard có alert không thể thay ACL, certificate verification hoặc authorization đúng.

## 16. Lệnh quan sát an toàn trên host và Kubernetes

Các lệnh sau dành cho **máy/cluster mà người học có quyền quan sát**. Chúng không thay firewall, thêm quyền, mở cổng hay tạo packet capture. Một số kết quả chứa IP, route, tên service/namespaces nhạy cảm; **không đăng nguyên output lên kênh công khai**.

### 16.1. Linux: interface và TCP sockets

~~~bash
# Xem danh sách interface và địa chỉ.
ip -br address

# Xem thống kê packet/byte/drop/error trên interfaces.
ip -s link

# Đọc route IPv4/IPv6 để biết hướng đi mặc định/đường riêng.
ip -4 route show
ip -6 route show

# Đếm sockets theo trạng thái; không thay socket.
ss -s

# Xem TCP sockets và trạng thái; có thể hiện IP nội bộ.
ss -tan

# Kernel TCP counters (tên field phụ thuộc OS/version).
cat /proc/net/snmp
cat /proc/net/netstat
~~~

**Cách đọc:** `ip -s link` là counter ở network interface, không phải p95 HTTP latency. `ss -tan` phản ánh socket trên host nơi chạy lệnh; network flow đi qua router/kube-proxy/Pod khác có thể không xuất hiện ở đó. `/proc/net/snmp` và `/proc/net/netstat` là counters tổng hợp của kernel, có thể reset sau reboot và cần biết semantics field trước khi tính tỷ lệ.

### 16.2. Linux: quan sát chi tiết TCP socket đã có

~~~bash
# Chỉ đọc thông tin TCP sockets; có thể gồm rtt, rto, retrans
# cho các kết nối mà kernel có thông tin, tùy phiên bản.
ss -ti
~~~

Lệnh **không tự tạo một phép đo ping tới đích**; nó đọc TCP diagnostic state trên host hiện tại. RTT của một socket không phải latency từ mọi client tới backend; dữ liệu phụ thuộc TCP implementation và connection health.

### 16.3. Windows PowerShell: network counters và sessions

~~~powershell
# Chỉ đọc network interfaces và counters.
Get-NetAdapter
Get-NetAdapterStatistics
Get-NetIPConfiguration

# Đọc TCP connections hiện tại; cần cân nhắc thông tin IP nhạy cảm.
Get-NetTCPConnection | Select-Object LocalAddress, LocalPort, RemoteAddress, RemotePort, State

# Chỉ đọc bảng định tuyến.
Get-NetRoute | Select-Object DestinationPrefix, NextHop, InterfaceAlias, RouteMetric
~~~

Trên một số thiết bị, lệnh có thể cần quyền OS hoặc module tương ứng. Nếu thiếu quyền, **không tự nâng tài khoản chỉ để làm bài**; nhờ người quản trị cung cấp dữ liệu đã làm sạch.

### 16.4. Kubernetes: resource/topology trạng thái

~~~bash
# Tránh nhầm cluster test với production.
kubectl config current-context

# Danh sách Pod/Service/Endpoints theo quyền RBAC hiện có.
kubectl get pods -A -o wide
kubectl get services -A
kubectl get endpointslices -A

# Xem NetworkPolicy objects; chưa chứng minh CNI enforce đúng.
kubectl get networkpolicies -A

# Chỉ đọc events được phép nhìn thấy.
kubectl get events -A --sort-by='.lastTimestamp'
~~~

**Kubernetes events không phải audit log đầy đủ**; chúng có giới hạn retention, có thể gộp sự kiện và không ghi mọi quyết định CNI/firewall. Pod `Pending`, `CrashLoopBackOff` hoặc EndpointSlice thay đổi là tín hiệu cần đối chiếu với metric/log/trace tương ứng.

### 16.5. Probe tạo traffic chỉ trong lab được cấp phép

Thử một **HTTP endpoint lab** đang lắng nghe trên loopback, không đọc body:

~~~bash
# Chỉ chạy nếu service lab tại localhost:8080 đã được thiết lập.
# Probe tạo HTTP request thực, không phải lệnh thuần read-only.
curl --silent --show-error --output /dev/null \
  --write-out 'http_code=%{http_code} total=%{time_total}s connect=%{time_connect}s tls=%{time_appconnect}s\n' \
  http://127.0.0.1:8080/health
~~~

Vì URL là **HTTP**, `time_appconnect` thường bằng 0; không suy “TLS handshake rất nhanh” từ chỉ số đó. Thời gian đo bởi `curl` là **từ vị trí client thực hiện probe**, không tương đương browser ở vùng mạng xa. Với HTTPS lab, dùng TLS certificate hợp lệ, **không thêm `-k`** để bỏ xác minh.

**Không bật `tcpdump`/pcap để thu full packets trên production như bước mặc định**: packet data có thể chứa thông tin nhận dạng, credentials hoặc dữ liệu nhạy cảm, đồng thời capture ở interface sai dễ gây hiểu nhầm. Nếu packet capture thực sự cần, phải có phạm vi/approval, filter, giới hạn thời lượng và lưu trữ mã hóa an toàn.

## 17. Quyền riêng tư và bảo vệ telemetry pipeline

Telemetry không phải dữ liệu vô hại chỉ vì gọi là “technical logs”. IP, DNS query, URL paths, service topology, principal, HTTP headers và traces có thể tiết lộ người dùng, hệ thống nội bộ, tenant, phương thức vận hành và dữ liệu kinh doanh.

### 17.1. Threat model của chính hệ thống giám sát

- **Confidentiality:** ai đọc được logs/traces/flow records chứa mạng nội bộ và user metadata?
- **Integrity:** attacker có thể ghi log giả, sửa metrics, xóa dấu vết hoặc thao túng alerts không?
- **Availability:** collector/backend bị quá tải có ảnh hưởng production không?
- **Privilege:** một network agent/DaemonSet được cấp host networking hoặc runtime socket có quyền gì?
- **Data lifecycle:** retention, privacy policies, encryption và legal requirements ra sao?
- **Cross-tenant isolation:** nhóm vận hành tenant A có thể đọc traces của tenant B không?

### 17.2. Kiểm soát tương ứng

| Rủi ro | Kiểm soát |
|---|---|
| Lộ user tokens/Secrets | Field allowlist, redaction, secret detection, hạn chế payload |
| Giả mạo telemetry | Agent identity, mTLS/AuthN đến collector, access control |
| Xóa/sửa logs | Storage IAM, append-only/immutable retention khi yêu cầu, audit |
| Data exfiltration từ collector | Egress allowlist, private endpoints, network segmentation |
| Collector quá đặc quyền | Least privilege, tránh Docker/CRI socket nếu không thật cần |
| Cardinality/volume explosion | Label hygiene, rate limiting, sampling, cost alerts |
| Lộ IP/topology multi-tenant | Data partitioning, RBAC/ABAC, pseudonymization khi phù hợp |
| Incident mất dữ liệu | Queue/backpressure strategy, source health, local buffer có giới hạn |

**Không để telemetry backend trở thành đường quản trị host thứ hai.** Nếu một agent cần quyền eBPF, host PID/network hoặc runtime socket, phải threat-model và hạn chế quyền tương ứng. Thu logs từ ứng dụng không mặc định yêu cầu Docker daemon access.

### 17.3. Tích hợp SOC và SRE

SRE tập trung availability/latency/capacity, SOC tập trung identity, policy drift, lateral movement và data misuse. Hai nhóm cần chia sẻ **cùng định nghĩa topology, timestamps, request/policy identifiers và incident timeline** nhưng quyền xem thông tin chi tiết phải phù hợp.

Không yêu cầu SOC được xem mọi user request body, hoặc mọi developer có quyền truy cập security investigations chỉ để giải quyết latency.

## 18. Threat modeling: 22 lỗi giám sát network path thường gặp

| ID | Rủi ro | Triệu chứng/thiếu sót | Cách kiểm chứng và giảm thiểu |
|---|---|---|---|
| T01 | **Chỉ nhìn CPU và băng thông** | Network path lỗi nhưng dashboard resource bình thường | RED + DNS/TCP/TLS/proxy/dependency metrics |
| T02 | **Một HTTP 504 bị gọi là network loss** | Gateway timeout do backend pool | Trace + upstream timings + DB metrics |
| T03 | **Traces được coi là packet route** | Không thấy hop router nên suy không có | Tách application spans và L3/L4 telemetry |
| T04 | **Mất trace context** | Client/server spans không nối | Kiểm tra W3C propagation và trusted boundary |
| T05 | **Sampling bỏ lỗi hiếm** | Không thấy error traces nhưng 5xx metrics tăng | Tail sampling/metric cross-check và error logs |
| T06 | **Trace samples thiên lệch** | Dùng error traces để ước lượng global p95 | Histogram SLI tổng traffic, không lấy từ biased trace |
| T07 | **Metric labels bùng nổ** | TSDB overload vì user_id/request_id | Low-cardinality labels, log/trace cho ID |
| T08 | **Counter reset bị hiểu là traffic âm** | Delta bytes âm sau process restart | Counter-aware rate và reset handling |
| T09 | **Gộp p95 của replicas sai** | Lấy trung bình percentiles | Aggregate histogram buckets trước quantile |
| T10 | **NAT che nguồn** | Ghép sai 5-tuples giữa hops | Translation logs, proxy request IDs, time/location |
| T11 | **Clock skew làm timeline sai** | Trace/log events ngược thời gian | NTP/clock sync, event vs ingestion timestamps |
| T12 | **Không có logs bị hiểu là không có traffic** | Flow sampling/collector outage | Synthetic controls, source heartbeat, queue health |
| T13 | **HTTP status không rõ nơi sinh** | 502/504 do gateway hay app? | Log status origin, upstream connect/response |
| T14 | **CNI policy không bao phủ hostNetwork** | Security flow blind spot | Host-level controls và topology-specific tests |
| T15 | **DNS cache che lỗi resolver** | Probe dùng cached resolution | Client DNS/cache-aware tests |
| T16 | **IPv6 bị bỏ sót** | IPv4 healthy, IPv6 path lỗi | Dual-stack DNS/route/flows |
| T17 | **Retry double counting** | Một user request thành nhiều upstream attempts | Gateway/downstream counts, retry metadata |
| T18 | **Metrics telemetry pipeline mất dữ liệu** | Dashboard trống khi collector overload | Self-telemetry, queue/drop/lag alerts |
| T19 | **Logs chứa token/PII** | Raw headers/body trong access logs | Redaction, field allowlist, RBAC/retention |
| T20 | **Trace headers không tin cậy** | Client ép sampling/lưu baggage độc hại | Gateway normalization, bounded sampling, sanitation |
| T21 | **Observability agent quá đặc quyền** | Agent có runtime socket/root privileges | Least privilege, host agent hardening, access review |
| T22 | **Tương quan bị nhận là nguyên nhân** | Đổ lỗi deployment lúc 14:00 không có test | Hypothesis+counterfactual/positive control, change correlation |

### 18.1. Mức ưu tiên theo failure domain

Đặt ưu tiên dựa trên **user impact, breadth, dữ liệu nhạy cảm, tính sẵn sàng của bằng chứng và khả năng rollback**. Một sự cố khiến mọi flow records mất trong thời điểm firewall đổi rule có giá trị an ninh khác với một route ít người dùng bị trễ 5 ms.

### 18.2. Phân biệt visibility gap và security bypass

Không có log ở CNI không tự là CNI bị bypass. Cần xét:

1. Traffic đi qua interface/Pod datapath mà CNI thực thi không?
2. Logging có bật cho allow/deny của loại flow đó không?
3. Flow sampling/filter/delivery có đang mất dữ liệu không?
4. Có đường khác qua hostNetwork, node, VPN, LB hoặc cloud service không?
5. Firewall/endpoint/app logs có bằng chứng độc lập không?

Chỉ khi xác minh đường đi và enforcement mới có thể kết luận một bypass cụ thể.

## 19. Ma trận kiểm thử chất lượng metrics, logs và traces

Chỉ thực hiện trên **môi trường lab hoặc hệ thống đã được cho phép**. Với negative tests, dùng **đường đối chứng khỏe mạnh**; một probe thất bại do Service không tồn tại không chứng minh firewall đã deny.

| ID | Kiểm thử | Kết quả kỳ vọng | Bằng chứng |
|---|---|---|---|
| P01 | HTTP request hợp lệ tới Orders lab | Request metrics tăng, gateway/app logs cùng request | Counter rate, request ID |
| P02 | Request có trace context qua gateway→Orders | Client/server spans nối cùng trace | Trace graph, propagation |
| P03 | DNS query hợp lệ tới resolver được quản lý | DNS duration/rcode được quan sát | Resolver metric/log |
| P04 | TLS handshake hợp lệ tới endpoint lab | Success và peer được verify | Client certificate validation result |
| P05 | TCP connection healthy | Connect success và socket state phù hợp | Client+OS observations |
| N01 | Request tạo 504 từ timeout có kiểm soát trong lab | Gateway log nêu timeout source, không nhầm app 504 | Gateway upstream event |
| N02 | DNS NXDOMAIN từ tên thử nghiệm | Có NXDOMAIN event theo nơi đo | Resolver logs, không lộ qname nhạy cảm |
| N03 | Policy deny flow thử nghiệm trong lab | CNI/firewall verdict deny, app healthy với source khác | Rule ID + positive control |
| N04 | TLS certificate hostname sai trong lab | TLS reject, không bỏ verification | TLS alert, error class |
| N05 | mTLS identity không được cấp quyền | Mesh/service AuthZ reject đúng nơi | Peer principal + policy verdict |
| N06 | Một service ngừng propagate trace context | Detect broken trace chain | Trace IDs, app/proxy logs |
| N07 | Collector queue gần full hoặc exporter lỗi mô phỏng | Pipeline alerts hiện hữu, không làm app sập | Queue/drop/export metrics |
| N08 | Metric counter reset trong lab | Rate không báo giá trị âm giả | Counter reset-aware query |
| N09 | Synthetic events sample bị thiếu | Dashboard thể hiện sampling/coverage | Sample settings, source event count |
| N10 | Thêm label request_id vào metric test | Linter/review từ chối high-cardinality | Metric schema/cardinality check |
| N11 | Request dùng user-supplied traceparent | Không thể trở thành trusted identity hoặc ép logging không giới hạn | Gateway security config |
| P06 | Histogram có đủ buckets/số mẫu | p95 được tính từ aggregated histogram | Bucket counts, query result |
| N12 | Log message chứa chuỗi giả lập secret | Redaction hoạt động trước storage | Sanitized log record |
| N13 | Một source agent dừng gửi telemetry | Heartbeat/gap alert kích hoạt | Agent health, ingest lag |
| P07 | CNI flow khớp workload labels | Có source/destination identity ở nơi hỗ trợ | CNI observer fields |
| N14 | NAT làm thay source port/IP | Correlation ghi rõ translation/ambiguity | Pre/post NAT evidence |
| N15 | IPv6 flow trong lab | Được nhìn thấy bởi sources có hỗ trợ | IPv6 logs/counters |
| P08 | Canary config change được gắn version | Timeline metric/log/trace đối chiếu version | Deploy/policy version |
| N16 | Retry tạo nhiều upstream attempts | Request count không nhầm attempts | Proxy attempt metadata |
| P09 | Application DB call có spans phân chia pool wait/query | Phân biệt app waiting và transport | Trace attributes, DB metrics |
| N17 | Thử đọc logs/trace trái role trong lab | Bị RBAC/ABAC từ chối | Audit access decision |
| N18 | HostNetwork path không được CNI ghi | Tài liệu/kiểm thử chỉ rõ coverage gap và host signal khác | Host firewall/flow observation |
| P10 | Dashboard cùng time window cho các nguồn | Timestamps nhất quán trong sai số cho phép | Event vs ingest time |
| N19 | Đóng telemetry backend tạm trong lab | Collection/backpressure xử lý theo runbook | Export retries/loss metrics |
| N20 | Backend bị deny bởi app AuthZ nhưng network allow | Log thể hiện đúng layer, không gọi firewall deny | Flow allow + HTTP 403 app |
| P11 | So SLO user-facing với backend spans | Hai loại latency có phân biệt | Ingress histogram + trace |
| N21 | Route/cert/policy changes sai vùng | Giám sát phát hiện drift hoặc health failure | Config event + regional telemetry |

### 19.1. Kỳ vọng đối với phép kiểm chứng

- **Metrics tests:** biết exporter, label schema, counter reset và aggregation interval.
- **Logs tests:** biết source, event time, policy/action origin, sampling và redaction.
- **Traces tests:** biết client/server spans, propagation, trace sampling và service coverage.
- **Network tests:** biết đúng enforcement point và bằng chứng flow verdict.
- **Security tests:** thông tin nhạy cảm không được ghi vào telemetry; chủ thể thiếu quyền không đọc được.

**Không coi “có chart trên dashboard” là kiểm chứng** nếu chart có thể lấy từ dữ liệu cache, demo hoặc không có positive signal. Nên dùng một **synthetic event có ID riêng** trong lab để xác minh đường ingest end-to-end.

## 20. Rollout telemetry theo giai đoạn

### Bước 1 — Tạo dependency map

Vẽ client → DNS → gateway → service → DB, node/cluster/region, trust boundaries, NAT/Service VIP, CNI và tuyến telemetry. Gắn owner cho từng hop và mức nhạy cảm dữ liệu.

### Bước 2 — Chọn user-facing SLI và nguồn đo

Bắt đầu từ **availability và latency end-to-end** ở ingress/client, rồi chọn metric DNS/TCP/TLS/proxy/DB giải thích các nguyên nhân có khả năng. Tránh thu mọi metric chưa có mục tiêu.

### Bước 3 — Chuẩn hóa resource attributes và log schema

Thống nhất service, environment, region, policy version, request ID/trace ID, timestamp và measurement point. Phân biệt source/destination logical identities với IP sau NAT.

### Bước 4 — Instrument traces ở luồng đại diện

Chọn một luồng HTTP/gRPC có thể truyền trace context end-to-end. Kiểm tra sampling, proxy trust boundary, long-lived connections, retries và tính đúng của child spans.

### Bước 5 — Thêm flow/DNS/TLS telemetry và pipeline health

Bảo đảm firewall/CNI/host/cloud logs phản ánh những đường có thật. Giám sát exporter queue, sampling drops, clock drift và backend ingest latency.

### Bước 6 — Bảo vệ dữ liệu, quyền và chi phí

Rà soát PII/tokens, permissions, retention, labels cardinality, CPU/RAM overhead và cost. Thu hẹp nếu agent/collector làm giảm SLO.

### Bước 7 — Canary và negative tests

Thực hiện DNS failure/TLS failure/policy deny/trace break/collector outage **trên lab**, so với positive controls. Không tiêm lỗi trên production nếu chưa có quy trình change/approval.

### Bước 8 — Alerting, on-call và postmortem

Alert phải có user impact, rule owner, dashboard links, logs/traces/flows và runbook. Hậu kiểm đánh giá **evidence quality**, không chỉ thời gian khôi phục ứng dụng.

## 21. Bài tập tình huống: từ “network chậm” đến bằng chứng nguyên nhân

**Bối cảnh giả định:** hệ thống nhận request qua CDN và API gateway, backend trên Kubernetes, CNI có network policy, service Orders gọi Payments qua mesh và Payments dùng DB.

Trong 10 phút:

- API gateway p95 tăng, một số request trả 504.
- DNS query latency ở resolver không tăng đáng kể.
- CNI flow denies tăng từ một Pod `debug-agent` không thuộc luồng nghiệp vụ.
- TLS handshake failure ở mesh tăng trên một tập nhỏ Pod sau rollout.
- Traces được giữ theo head sampling 1%; nhiều request lỗi không có trace.
- DB pool wait của Payments tăng ở một node pool.
- Collector báo dropped spans tăng do queue đầy.

### 21.1. Câu hỏi

1. Những tín hiệu nào **cho thấy user impact** và tín hiệu nào chỉ là **security/infra symptoms**?
2. Có thể suy CNI denies của `debug-agent` là nguyên nhân 504 không? Cần bằng chứng gì?
3. Vì sao DNS latency bình thường chưa đủ loại mọi DNS-related failure trong các clients khác?
4. TLS failures ở một tập Pod có ảnh hưởng tới mọi requests hay chỉ subset? Cần dùng nhãn/version/route nào?
5. Head sampling 1% và collector drops làm thay đổi độ tin cậy trace evidence thế nào?
6. Nếu trace cho thấy `db_pool_wait` lớn, bằng chứng nào giúp loại giả thuyết loss trên đường DB?
7. Làm sao phân biệt gateway sinh 504 với backend tự trả 504?
8. Tên nào là metric labels nên dùng: `service`, `region`, `request_id`, `source_port`, `route_template`?
9. Đề xuất 3 positive và 5 negative tests cho pipeline và enforcement.
10. Nên ưu tiên remediation nào trước, theo user impact và rủi ro?

### 21.2. Gợi ý đối chiếu

- Gateway p95/504 là **user-impact indicators**. CNI denies từ debug agent chưa có chứng cứ thuộc đường checkout; có thể là policy đang chặn đúng.
- TLS failure subset cần phân theo **service version, Pod/namespace, CA/identity, route, gateway/mesh mode**. Không gán toàn bộ p95 tăng cho TLS nếu phần lớn requests tái sử dụng connection đã được thiết lập.
- DNS resolver bình thường không chứng minh client DNS cache/mạng/NodeLocal DNSCache ở mọi vùng đều tốt.
- Head sampling 1% cộng queue dropped spans có thể khiến **missing traces thiên lệch nghiêm trọng**; metric tổng và gateway logs là đối chứng.
- `db_pool_wait` tăng gợi ý **resource saturation tại DB client pool**; cần DB metrics, client connection states, network RTT và thay đổi cấu hình để kiểm chứng.
- Không đưa `request_id` và `source_port` vào metric labels vì cardinality; `service`, `region` và `route_template` có thể phù hợp sau khi kiểm soát số giá trị.
- Remediation nên dựa trên **bằng chứng được đối chiếu**: sửa/rollback rollout TLS nếu nó gây lỗi xác thực, điều chỉnh pool nếu chứng minh nghẽn, tăng capacity collector/sampling strategy nếu làm mù observability — không mở firewall hay tắt TLS theo cảm tính.

## 22. Checklist metrics, logs và traces của network path

- [ ] Có sơ đồ network path theo client → DNS → TLS/transport → gateway → Service/CNI → app → dependencies.
- [ ] Phân biệt network flow, TCP connection, HTTP/gRPC request và business transaction.
- [ ] Biết measurement point của mỗi metric/log/trace, gồm vị trí trước/sau NAT/proxy.
- [ ] Chọn user-facing SLI riêng với network/resource metrics, không gọi mọi latency là “network latency”.
- [ ] Chọn đúng counter/gauge/histogram, biết counter resets và histogram bucket aggregation.
- [ ] Không tính p95 toàn fleet bằng trung bình p95 của từng Pod.
- [ ] Có RED/USE, DNS latency/RCODE, TCP RTT/retransmissions, TLS failures và gateway upstream timings phù hợp.
- [ ] Không coi TCP retransmission count là packet loss ratio tuyệt đối.
- [ ] Proxy/gateway logs phân biệt downstream/upstream, status origin, retries và connection attempts.
- [ ] Firewall/CNI flow logs có policy verdict/measurement point; đã kiểm tra sampling và coverage.
- [ ] Có thông tin Service/EndpointSlice, Pod labels, namespace, policy/deployment version và node/region.
- [ ] Hiểu 5-tuple, NAT translation, dynamic ports, connection reuse và nguồn gốc IP.
- [ ] Có trace ID/request ID propagation ở đường được instrumented và không dùng chúng làm authentication.
- [ ] Phân biệt distributed tracing với packet traceroute; không suy các network hops chưa được instrumented.
- [ ] Trace sampling strategy, collection gaps và missing spans được mô tả minh bạch.
- [ ] Không dùng sampled error traces làm phân bố latency của toàn bộ request population.
- [ ] Metric labels không chứa user_id, request_id, dynamic source port hoặc raw object IDs.
- [ ] Có collector/agent self-telemetry: queue, drops, export failures, ingest lag và heartbeat.
- [ ] Đã đồng bộ thời gian hoặc biết clock skew, event time khác observed/ingest time.
- [ ] Có cross-layer correlation: gateway access log ↔ trace ↔ app log ↔ flow/DB metrics khi dữ liệu cho phép.
- [ ] Bằng chứng negative test có positive control chứng minh backend khỏe và enforcement thực sự deny.
- [ ] Đã kiểm thử IPv4/IPv6, node-local/hostNetwork, cloud/mesh routes phù hợp topology.
- [ ] Log/trace không thu raw Authorization headers, cookies, passwords, private keys hoặc data payloads không cần thiết.
- [ ] Telemetry pipeline được mã hóa/xác thực, phân quyền truy cập, hạn chế retention và audit.
- [ ] Host/cluster agents không nhận quyền Docker/CRI/socket vượt nhu cầu quan sát.
- [ ] Alert phân biệt failure symptoms, security denies cố ý và telemetry pipeline outage.
- [ ] Đã đo performance/cost overhead của agents, proxies, sampling và storage.
- [ ] Có runbook điều tra DNS→TCP/TLS→proxy→app→dependency, không gán lỗi theo trực giác.
- [ ] Có canary rollout, config/version tracking, change review và rollback nếu telemetry gây ảnh hưởng.
- [ ] Incident reports nêu **bằng chứng, measurement point, độ tin cậy, các khả năng khác và kết quả xác minh**.

**Ghi nhớ:** **Metrics, logs và traces là ba góc nhìn bổ sung của network path, không phải ba bản sao cùng một dữ liệu.** Metrics cho thấy **xu hướng và tác động**, logs ghi **sự kiện/quyết định**, traces liên kết **các thao tác và thời gian**; flow records và transport diagnostics giúp giải thích **đường đi và kết nối ở L3/L4**. Chỉ khi hiểu **vị trí đo, NAT/proxy boundaries, sampling, clock, identity và telemetry coverage**, ta mới có thể phân biệt **mất gói, timeout proxy, DNS/TLS failure, NetworkPolicy deny và lỗi ứng dụng/DB** một cách có bằng chứng. Observability tốt cần **đủ tín hiệu, bảo vệ dữ liệu, đo cả pipeline và kiểm thử kiểm soát thực tế**, không chỉ thêm dashboard.
