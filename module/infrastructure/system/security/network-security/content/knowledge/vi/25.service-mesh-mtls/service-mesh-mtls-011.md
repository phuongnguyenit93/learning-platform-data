# Quan sát request qua telemetry trong service mesh và mTLS

**Quan sát request qua telemetry** là quá trình thu thập, liên kết và giải thích các tín hiệu phát sinh khi một yêu cầu đi qua **client, ingress gateway, workload proxy, service-to-service hop, ứng dụng, egress gateway** và các phụ thuộc bên ngoài. Trong service mesh, telemetry giúp trả lời: request bắt đầu ở đâu, đi qua những dịch vụ nào, mất thời gian ở chặng nào, kết thúc bằng lỗi gì, có xác thực mTLS và phân quyền đúng không, lỗi do network, proxy hay mã ứng dụng, và cơ chế phòng vệ có hoạt động đúng trên mọi đường đi không?

Bài **Quan sát request qua telemetry** thuộc chương **Service mesh và mTLS**, học phần **SECURITY_NETWORK_SECURITY**. Đây là chủ đề gắn với phân đoạn, firewall, VPN, IDS/IPS, xác thực kết nối, DNS, cloud networking và kiến trúc mạng an toàn. Telemetry là **cơ chế quan sát và thu thập bằng chứng**, không tự là firewall hoặc authorization. Một dashboard xanh không chứng minh hệ thống an toàn; một trace thành công cũng không chứng minh mọi request được xử lý đúng.

Trọng tâm của bài là **vòng đời của một request** và ba loại tín hiệu bổ sung nhau: **metrics** (đếm, tỷ lệ lỗi, phân phối độ trễ), **logs** (sự kiện, quyết định và ngữ cảnh), **distributed traces** (chuỗi span xử lý request). Ví dụ dùng Istio/Envoy, OpenTelemetry, Prometheus và các backend quan sát. **Tên metric, field, cấu hình và khả năng L7 phụ thuộc mesh version, datapath, protocol và exporter**, nên không mặc định mọi ví dụ là cấu hình production có thể dùng nguyên xi. Tên miền .example và các định danh minh họa không phải tài sản thực.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **metrics, access logs, application logs, distributed traces, network flow logs và control-plane audit**.
2. Vẽ đường đi request qua **ingress, sidecar hoặc ambient datapath, application, gateway và dependency**.
3. Tính các tín hiệu **Rate, Errors, Duration (RED)**, đọc latency histogram và phân biệt HTTP, gRPC, TCP/TLS errors.
4. Giải thích **trace ID, span ID, traceparent, tracestate, baggage, sampling và W3C Trace Context**.
5. Correlate telemetry theo **service, namespace, workload, revision, trace ID, request ID và thời gian**.
6. Phân biệt **network reachability, mTLS peer authentication, mesh authorization và application authorization**.
7. Phân tích **retry amplification, timeout, circuit breaking, connection reset, TLS handshake failures** và policy denies.
8. Thiết kế pipeline **proxy/SDK → OpenTelemetry Collector → metrics/logs/traces backends**.
9. Giảm **high cardinality, sampling bias, telemetry loss, lộ dữ liệu nhạy cảm** và sai lệch khi đếm nhiều proxies.
10. Lập **SLI/SLO, dashboard, alerts, ma trận kiểm thử và incident runbook** cho request telemetry.

## 2. Quan sát request nghĩa là quan sát ở đâu?

Một request có thể phát sinh telemetry ở nhiều hop:

- **Client / edge / ingress gateway:** request đến, TLS termination, route và response trả client.
- **Source proxy:** outbound HTTP/TCP request từ workload nguồn nếu traffic đi qua mesh datapath.
- **Destination proxy:** inbound request, upstream handling, TLS peer metadata, authorization decision khi được cung cấp bởi engine đáng tin.
- **Application SDK:** logic nghiệp vụ, database calls, queues, authorization theo user/tenant và domain errors.
- **Egress gateway:** luồng rời mesh ra mạng khác qua đường được kiểm soát.
- **CNI/node/cloud firewall:** flow metadata L3/L4, packet drops hoặc routing information ở scope tương ứng.
- **Control plane / CA:** cấu hình, cấp/đổi certificates, proxy readiness, policy changes, không nhất thiết là per-request data.

~~~mermaid
flowchart LR
    C[Client] --> G[Ingress Gateway]
    G --> P1[Orders proxy]
    P1 --> A[Orders app]
    A --> P2[Inventory proxy]
    P2 --> B[Inventory app]
    B --> DB[(Database)]
    G -.Metrics / logs / spans.-> COL[Telemetry Collector]
    P1 -.Telemetry.-> COL
    P2 -.Telemetry.-> COL
    A -.App spans.-> COL
    B -.App spans.-> COL
    COL --> M[Metrics backend]
    COL --> L[Log backend]
    COL --> T[Trace backend]
~~~

Các đường telemetry là **logic**: Prometheus có thể *scrape* metrics còn traces/logs được *push* tới collector. Mỗi thành phần có thể dùng agent, collector tập trung hoặc backend khác.

### 2.1. Một request không phải một bản ghi

Một user request có thể tạo 1 gateway access log, 2 outbound logs, 2 inbound logs, vài application logs và nhiều spans. Nếu cộng mọi bản ghi thành số **user requests**, sẽ bị double counting. Chọn **điểm đo canonical** cho SLI rồi dùng trace/log correlation để hiểu những hop còn lại.

### 2.2. Coverage giới hạn theo đường đi

Service mesh thường không tự nhìn thấy mọi traffic:
- Workload không tham gia mesh, sidecar injection lỗi, waypoint không nằm trên route.
- hostNetwork/node-level traffic hoặc bypass qua gateway khác.
- TLS passthrough/opaque TCP làm mất L7 visibility.
- Database query, background job hoặc queue message không được app instrument.
- Connection trực tiếp tới private endpoint, VPC peering hoặc network path không qua proxy.
- Các request bị drop trước điểm thu telemetry.

**Không có trace không chứng minh request không xảy ra.** Phải đối chiếu proxy config, CNI/cloud flow logs, application logs và telemetry pipeline health.

## 3. Các loại telemetry hỗ trợ nhau

| Tín hiệu | Giải đáp tốt | Hạn chế |
|---|---|---|
| **Metrics** | Throughput, error rate, latency distribution, saturation | Không cho toàn bộ lịch sử một request |
| **Proxy access logs** | Request/connection, proxy route, status, duration, response flags | Không hiểu business logic nếu thiếu application logs |
| **Application logs** | Business action, domain validation, authorization decision | Có nguy cơ secret/PII, phụ thuộc instrumentation |
| **Distributed traces** | Chuỗi spans và thời gian mỗi chặng | Sampling, propagation và missing spans |
| **Network flow logs** | IP/port, allow/deny, bytes theo scope | Không tự hiểu HTTP body, user hay TLS payload |
| **Control-plane audit** | Ai đổi mesh policy, cert hoặc datapath config | Không chứng minh traffic đã đi qua policy |

**Metrics để phát hiện xu hướng; traces để khoanh vùng; logs/audit để xác minh quyết định; flow data để đối chiếu network path.**

### 3.1. Structured attributes

Các trường như service.name, k8s.namespace.name, deployment.environment.name, http.request.method và http.response.status_code hỗ trợ truy vấn nhất quán. Tên và semantics có thể đổi theo **OpenTelemetry Semantic Conventions version**, vì thế pipeline nên ghi schema/version và có kế hoạch migration.

Không đưa user email, bearer token, session cookie hoặc full query string vào mọi metric vì dễ tạo **rò dữ liệu và cardinality explosion**.

## 4. Service mesh tự thu những gì?

Một mesh proxy **có thể** tạo request metrics, access logs và tracing spans khi được bật. Nhưng:

1. Không phải mọi môi trường tự bật đủ ba loại tín hiệu.
2. Proxy chỉ giải mã L7 khi có protocol-aware processing và traffic phù hợp.
3. Opaque TCP, UDP hoặc TLS passthrough giảm khả năng nhìn HTTP route/status.
4. Proxy không tự biết database transaction hay business rule.
5. Proxy không tự propagate trace context xuyên mọi async job/queue.
6. Trong ambient architecture, **L4 component** có tín hiệu connection/workload identity; **L7 waypoint** chỉ có HTTP telemetry với traffic thật sự đi qua nó.
7. Control-plane cert renewal, config changes và proxy reconnect là những telemetry khác per-request data.

| Thành phần | Điểm quan sát | Không được suy diễn |
|---|---|---|
| **Sidecar proxy** | Lưu lượng inbound/outbound đi qua sidecar | Mọi traffic trong Pod chắc chắn qua sidecar |
| **Ambient L4 datapath** | Connection metadata và secure transport theo khả năng | Tự có HTTP paths hoặc L7 spans |
| **Waypoint/L7 proxy** | L7 routing, authz và request telemetry khi traffic đi qua | Mọi service đều có waypoint |
| **Ingress/egress gateway** | Traffic ở boundary tương ứng | Biết business spans bên trong ứng dụng |
| **OTel application SDK** | Methods, DB, queue, custom business spans | Thấy mọi hop mạng nếu không instrument proxy |

## 5. Một HTTP request đi qua những hop nào?

Giả sử Client gọi Orders API, Orders gọi Inventory API và database.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway
    participant O as Orders proxy/app
    participant I as Inventory proxy/app
    participant D as Database
    C->>G: POST /v1/orders + traceparent
    G->>O: Ingress to Orders
    O->>I: GET /v1/stock + trace context
    I->>D: Query stock
    D-->>I: Result
    I-->>O: HTTP 200
    O-->>G: HTTP 201
    G-->>C: HTTP 201
    Note over G,I: Metrics, logs và spans tại những hop được cấu hình
~~~

### 5.1. Góc nhìn từng thành phần

- Gateway đo 201 và latency tới client.
- Orders inbound proxy đo response application và peer connection.
- Orders outbound proxy đo request tới Inventory, kể cả retries nếu có.
- Inventory inbound đo requests thật sự tới Inventory.
- App SDK đo business spans, cache/DB, domain errors.
- DB có thể có logs/metrics riêng nhưng **không tự phát spans do mesh được bật**.

Nếu Orders retry gọi Inventory ba lần, **một user request** có thể tương ứng **ba upstream attempts**. Vì vậy rate tại gateway và rate tại downstream không nhất thiết bằng nhau.

### 5.2. Thành công theo góc nhìn

Gateway 201 chưa chứng minh async event xử lý xong; proxy 200 không đủ chứng minh gRPC status OK; application ghi “created” không chứng minh client đã nhận response. Hãy định nghĩa **SLI theo user intent** và tách nó khỏi chỉ số từng hop.

## 6. RED và các tín hiệu vàng

**RED (Rate, Errors, Duration)** hỗ trợ quan sát request workloads:

- **Rate:** requests/second hoặc upstream attempts/second trong khoảng đo.
- **Errors:** tỷ lệ request không đạt contract, có thể khác HTTP 5xx.
- **Duration:** latency distribution, thường có p50/p95/p99.

Bốn tín hiệu vàng còn gồm **saturation**, chẳng hạn active connections, request queues, CPU, worker threads, connection pool hoặc Envoy pending requests.

### 6.1. Ví dụ số học

Giả sử gateway ghi nhận 15.000 user-facing requests trong 5 phút; 120 thuộc lớp lỗi đã định nghĩa:

\[
R=\frac{15000}{300}=50\ \text{request/s}
\]

\[
\text{Error rate}=\frac{120}{15000}\times100\%=0.8\%
\]

Đây là phép tính minh họa. Khi làm SLO phải quy định cụ thể **numerator/denominator, loại trừ health checks, 4xx/429, gRPC và client cancellation**.

### 6.2. Source và destination reporters

Một số Istio standard metrics có nhãn **reporter** thể hiện góc nhìn source/destination. Nếu cộng cả hai, có thể đếm đôi cùng một request. Chọn reporter đúng SLI và so sánh với gateway/application counters.

## 7. Request metrics: tên và labels

Những họ metric thường gặp ở các triển khai Istio gồm:
- **istio_requests_total**: số request.
- **istio_request_duration_milliseconds** và histogram buckets (khi cấu hình/exporter hỗ trợ).
- **istio_request_bytes**, **istio_response_bytes**: phân phối bytes.
- **istio_tcp_sent_bytes_total**, **istio_tcp_received_bytes_total**: TCP throughput trong những datapaths hỗ trợ.

**Tên, đơn vị, labels, histogram type và sự xuất hiện của metrics thay đổi theo phiên bản và chế độ sidecar/ambient**, nên phải kiểm tra target scrape output thực tế.

| Label/attribute | Ý nghĩa | Lưu ý |
|---|---|---|
| source_workload / source_workload_namespace | Caller workload | Không phải end-user identity |
| destination_workload / destination_service | Service/upstream | Cần phân biệt app instance và service |
| response_code | HTTP status | Không đủ cho gRPC app status |
| response_flags | Proxy-local outcome | Phải đối chiếu Envoy semantics |
| request_protocol | HTTP/gRPC/TCP theo schema | Opaque TCP không có HTTP route |
| connection_security_policy | Loại transport security theo schema | Không tự chứng minh policy end-to-end |
| reporter | Source/destination | Tránh double counting |
| canonical_service / canonical_revision | Service và rollout version | Bảo đảm thống nhất label |
| request_operation | Normalized route nếu được hỗ trợ | Không dùng raw URL chứa object ID |

### 7.1. PromQL minh họa: destination rate

~~~promql
sum by (destination_service) (
  rate(istio_requests_total{reporter="destination"}[5m])
)
~~~

### 7.2. PromQL minh họa: HTTP 5xx ratio

~~~promql
sum(rate(istio_requests_total{
  reporter="destination",
  response_code=~"5.."
}[5m]))
/
clamp_min(
  sum(rate(istio_requests_total{reporter="destination"}[5m])),
  1e-9
)
~~~

Đây là **HTTP 5xx ratio**, chưa chắc là business failure rate hoặc gRPC failure rate. Muốn dùng cho SLO, lọc đúng environment/service, tính requests attempts vs user requests và kiểm tra timeseries có tồn tại.

### 7.3. PromQL minh họa: p95

~~~promql
histogram_quantile(
  0.95,
  sum by (le, destination_service) (
    rate(istio_request_duration_milliseconds_bucket{
      reporter="destination"
    }[5m])
  )
)
~~~

Đây là ví dụ với **classic histogram theo milliseconds** và metric name tương ứng. Nếu exporter dùng **native histogram** hoặc metric OTel theo seconds, query/đơn vị khác. Không tính p95 dịch vụ bằng **trung bình p95 của từng Pod**.

## 8. Histograms và SLI/SLO

**Counter** tích lũy request count, **gauge** thể hiện active connections/queue depth, còn **histogram** phân bố latency theo buckets. Với classic histograms, mỗi tổ hợp labels tạo nhiều series (buckets, count, sum).

### 8.1. Tail latency quan trọng

Nếu đa số requests mất 50–100 ms nhưng một nhóm nhỏ kéo dài 3 giây, latency trung bình có thể che hiện tượng. **p95/p99** cho biết hành vi phần đuôi nhưng vẫn cần sample count và confidence trong cửa sổ ít traffic.

### 8.2. Định nghĩa SLI cụ thể

Một ví dụ:
- **Availability SLI:** tỷ lệ user requests hợp lệ tới Orders API có outcome đúng hợp đồng, đo tại ingress.
- **Latency SLI:** tỷ lệ requests hoàn thành dưới 800 ms tại điểm ingress, sau khi đã quy định excluded classes.
- **Security signal:** tỷ lệ requests bị mTLS handshake reject/authorization deny, quan sát riêng thay vì nhập mọi 403 vào application availability errors.

Nếu SLO request success là **99,9%**, error budget tương ứng là **0,1% user requests hợp lệ** trong cửa sổ. Đây không mặc định là số phút downtime.

### 8.3. Histogram aggregation

Bỏ các nhãn làm rò thông tin và xem việc giữ **le** khi tổng hợp classic histogram. Những histogram tạo ở từng Pod có thể được aggregate theo buckets, nhưng **quantiles tính riêng tại từng Pod không thể trung bình để suy ra quantile toàn dịch vụ**.

## 9. High cardinality: telemetry trở thành nguồn quá tải

Cardinality là số lượng time series do các tổ hợp labels tạo ra. Ví dụ 40 services × 6 status classes × 8 revisions × 10 routes cho ra **19.200 tổ hợp** trước khi tính region, source workload, Pod, histogram buckets.

Không đặt những giá trị không giới hạn vào metrics labels:
- Raw URL với user IDs, order IDs và query strings.
- Trace ID, request ID, session ID, JWT token.
- Email, IP của từng end user hoặc device fingerprint.
- Exception message hoặc full stack trace.
- Tên miền do user cung cấp, nếu cardinality không kiểm soát.

Ưu tiên **route template, canonical service, bounded operation, response class, environment**. Trace/request ID nên được đặt trong **logs/traces có retention/permission**, không phải Prometheus label per request.

### 9.1. Histogram nhân số series

Nếu mỗi metric latency có nhiều buckets, một tổ hợp 8 nhãn có thể tạo lượng time series rất lớn. Chỉ bật chiều dữ liệu cần dùng, đặt **cardinality budget**, theo dõi scrape/storage costs và review Telemetry API custom dimensions.

### 9.2. Không đổi khả năng điều tra lấy dữ liệu quá rộng

Dùng metric để aggregate theo service và logs/traces có privacy controls để phân tích request cụ thể. Nếu cần thêm field tạm thời cho điều tra, áp **time-bound, approved instrumentation** và xóa sau khi hoàn tất.

## 10. Proxy access logs và structured events

Một access log hữu ích có thể chứa **timestamp, source/destination workload, route template, method, status, duration, upstream host, response flags, request ID, trace ID** và identity khi được xác minh bởi mTLS/proxy.

~~~json
{
  "event_time": "2026-11-28T06:00:00Z",
  "mesh_service": "orders-api",
  "namespace": "orders-prod",
  "revision": "v3",
  "direction": "inbound",
  "method": "POST",
  "route_template": "/v1/orders",
  "response_code": 201,
  "duration_ms": 134,
  "request_id": "example-request-id",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "peer_identity": "spiffe://example.test/ns/edge/sa/ingress",
  "peer_identity_verified": true,
  "authorization_decision": "allow"
}
~~~

**Đây là schema minh họa, không phải Envoy/Istio default log.** Peer identity/decision chỉ được xuất từ **verified proxy metadata/policy engine**, không từ header do client gửi. Nếu không có dữ liệu đáng tin, đánh dấu unknown/omit, không tự gán true.

### 10.1. Phân biệt lớp lỗi

HTTP 503 có thể do:
- Ứng dụng thật sự trả 503.
- Proxy không tìm thấy healthy upstream.
- Upstream connection reset/refused.
- TLS handshake hoặc certificate validation fail.
- Gateway route sai.
- Proxy timeout/circuit breaking/overload.

Cần xem **response_flags, transport_failure_reason, upstream cluster, logs và app telemetry**. Các mã Envoy flags và tên fields phải đối chiếu version thực tế.

### 10.2. Bảo vệ log

Không log mặc định Authorization/Cookie/Set-Cookie headers, access tokens, private keys, raw bodies, signed URLs, full query strings hoặc PII. Dùng **allowlist fields, redaction, encryption, role-based access và retention**. Một số headers/metadata cần được loại bỏ ngay từ nguồn, không chỉ dựa vào dashboard masking.

## 11. Distributed traces: trace, span, links và thời gian

**Trace** gồm các spans liên quan tới một request hoặc transaction. Một span có **trace ID, span ID, parent ID, name/kind, start, duration, attributes, events, status**, và có thể liên kết qua **links** trong trường hợp async/message workflows.

~~~text
Trace POST /v1/orders                        240 ms
  |-- gateway inbound                         240 ms
  |-- orders HTTP server                      210 ms
      |-- inventory HTTP client                35 ms
      |-- database query                       80 ms
      |-- publish order event                  12 ms
~~~

Trace trên **chỉ là minh họa**. Spans có thể chồng lấp hoặc thiếu do async execution, sampling, context loss hoặc collector outages. **Không cộng mọi span durations** để tính end-to-end latency.

### 11.1. Trace gãy không luôn là network bypass

Một span thiếu có thể do:
- Proxy/app không instrument.
- Client không forward trace context.
- Queue không propagate.
- Sampling ở một hop.
- Exporter/Collector drops.
- TLS passthrough/opaque TCP.
- Khác propagation format.
- App tạo request mới với trace ID khác.

Cần kiểm tra headers, sampling và pipeline trước khi suy rằng request không qua mesh.

## 12. W3C Trace Context và propagation

W3C định nghĩa **traceparent** và **tracestate** headers:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
tracestate: vendor=opaque-state
~~~

Trace ID thường là 16 bytes / 32 ký tự hex; parent span ID 8 bytes / 16 ký tự hex. Sampled flag là **gợi ý propagation**, không bảo đảm trace đã được lưu. Dạng header phải tuân chuẩn về độ dài và giá trị hợp lệ.

### 12.1. Chuỗi propagation

1. Edge nhận hoặc tạo trace context theo trust policy.
2. Gateway/proxy tạo span khi tracing được bật.
3. App server SDK extract context, tạo server/application span.
4. App HTTP client inject context khi gọi downstream.
5. Destination SDK/proxy nhận context và liên kết child spans.
6. Spans được export tới Collector theo sampling và retention.

**Sidecar không tự nối mọi span qua application không propagate context.** Nếu app không giữ header khi gọi downstream, mối quan hệ parent–child có thể đứt.

### 12.2. Formats và trust

Một số tổ chức dùng **B3/Jaeger proprietary propagation** bên cạnh W3C. Migration phải có chiến lược tránh trace fragmentation. **Traceparent không phải xác thực danh tính**: client bên ngoài có thể tự gửi nó. Edge cần kiểm soát correlation identifiers, giới hạn kích thước và tránh **trace poisoning**.

### 12.3. Baggage

Baggage có thể được truyền xuyên nhiều service và vùng, nên **không đặt JWT, user email, account secret hoặc raw PII** vào đó. Chỉ sử dụng approved bounded attributes và chính sách retention/privacy.

## 13. Sampling: sự đánh đổi giữa chi phí và độ phủ

Một hệ thống xử lý nhiều request không phải lúc nào cũng lưu được mọi span. **Sampling** giúp giảm chi phí collector/storage nhưng tạo **selection bias**: trace backend không còn là nguồn đếm số request chính xác.

### 13.1. Head sampling

Quyết định lấy mẫu khi request bắt đầu, có thể theo xác suất hoặc incoming sampled flag. Ưu điểm: giảm chi phí ngay từ nguồn. Hạn chế: không biết request sẽ lỗi hoặc chậm khi quyết định.

### 13.2. Tail sampling

Đợi thu thập spans trong một khoảng thời gian, sau đó ưu tiên traces có **error, high latency hoặc operation quan trọng**. Ưu điểm: dễ giữ failure traces. Hạn chế:
- Tốn memory/CPU/buffer và cần giới hạn thời gian quyết định.
- Collector phân tán cần cách route tất cả spans thuộc một trace tới cùng decision context.
- Một trace đến trễ hoặc thiếu spans có thể bị quyết định sai.
- Không nên đánh đồng tỷ lệ errors trong tail-sampled traces với tỷ lệ errors của toàn bộ requests.

### 13.3. Ví dụ

Giả sử 100.000 user requests/phút được head-sample **1%**, số traces kỳ vọng khoảng **1.000/phút** theo xác suất. Không đảm bảo luôn đúng 1.000; đặc biệt không đảm bảo giữ đúng 1% lỗi hiếm.

Khi cần tính SLO, sử dụng **counter/histogram đo toàn traffic trong phạm vi đã định**, không tính bằng cách đếm sampled traces. Nếu metrics cũng sampled hoặc mất scrape, ghi rõ sai lệch và theo dõi data completeness.

### 13.4. Quy tắc triển khai

1. Định nghĩa ngân sách spans/second, bytes/second và lưu trữ theo service.
2. Giữ cấu hình sampling của source SDK, gateway, sidecar và Collector nhất quán.
3. Theo dõi queue occupancy, exporter failures và spans dropped.
4. Ưu tiên slow/error traces trong điều kiện chi phí cho phép.
5. Ghi nhận sampling policy version và thời gian áp dụng.
6. Kiểm thử trace continuity khi workload scale hoặc collector failover.
7. Tránh dùng PII/secret làm điều kiện sampling.
8. Có emergency sampling increase **theo scope và thời hạn**, không bật 100% trên toàn mesh mặc định.

## 14. Quan sát mTLS: xác thực kết nối không đồng nghĩa quyền nghiệp vụ

**mTLS** xác thực cả hai đầu một kết nối TLS khi cấu hình đúng. Trong mesh, proxy thường dùng workload identity/chứng chỉ ngắn hạn; peer identity có thể dựa trên SPIFFE-format principal hoặc cách định danh tương đương do control plane cấp.

### 14.1. Mục tiêu quan sát

- Request đã dùng **plaintext, TLS một chiều hay mTLS** ở hop đang đo?
- Peer identity thật sự **được TLS stack xác minh** là gì?
- Chứng chỉ còn hạn, phù hợp trust bundle, SAN và security domain không?
- Có handshake failures hoặc identity mismatch tăng sau deploy không?
- Policy áp **STRICT/PERMISSIVE/DISABLE** hay chế độ tương đương theo mesh version/scope?
- Traffic có bị bypass qua một đường không tham gia mTLS không?
- Proxy destination nào đang dùng trust bundle/cert cũ?

### 14.2. Bốn câu hỏi khác nhau

| Câu hỏi | Tín hiệu | Điều chưa thể kết luận |
|---|---|---|
| Có kết nối TCP? | Flow logs, TCP connection counters | Có TLS, đúng peer |
| TLS handshake thành công? | Proxy TLS/transport logs và connection stats | Client có quyền gọi API |
| Peer mTLS identity được xác minh? | Verified peer principal/cert metadata | Được phép đọc object cụ thể |
| Request được authorization cho phép? | Mesh authz decision, app authz audit | Không có lỗ hổng logic sâu trong app |

**mTLS success không tự cấp quyền**. Peer identity có thể hợp lệ mà không có quyền gọi một route hoặc dữ liệu tenant khác. Đây là lý do phải kết hợp mesh AuthorizationPolicy và application-level authorization.

### 14.3. Nguồn telemetry đáng tin

Chỉ đánh dấu mTLS verified khi thông tin đến từ **TLS peer state/proxy metadata** hoặc telemetry đã được engine tạo sau xác minh. **Không** đọc header tùy ý như X-Peer-Identity từ request bên ngoài rồi coi là danh tính đã kiểm chứng.

Một số metric có nhãn loại transport security, nhưng:
- Nhãn có thể không tồn tại hoặc đổi theo version.
- Nhãn theo hop không nói gì về hop khác.
- Có thể chỉ phản ánh requests proxy thấy, không toàn traffic.
- Một kết nối inbound tới gateway và outbound từ gateway có các TLS contexts khác nhau.

## 15. Identity và policy: nhận diện nguồn/đích theo workload

Service mesh có thể gắn request với **service account, namespace, workload, principal/trust domain**, trong khi người dùng cuối thường được xác thực qua ứng dụng/API gateway.

### 15.1. Tách bốn danh tính

- **Network identity:** source IP/port, chịu NAT/overlay và IP reuse.
- **Transport identity:** mTLS certificate identity do peer verification xác nhận.
- **Workload identity:** Kubernetes service account/SPIFFE principal hoặc provider identity.
- **End-user identity:** user subject, session, organization/tenant, xác thực bằng IdP/JWT/cookie ở lớp phù hợp.

Một Pod có identity hợp lệ nhưng bị chiếm vẫn có thể gửi requests dưới identity đó. Identity cho phép **attribution và policy** nhưng không bảo đảm workload luôn lành mạnh; cần runtime/supply chain controls và least privilege.

### 15.2. Quan sát policy decision

Một policy engine có thể quyết định:
- **ALLOW:** peer phù hợp role/namespace/path/method.
- **DENY:** sai peer, thiếu quyền, explicit deny hoặc default deny.
- **UNKNOWN/NOT_EVALUATED:** traffic không đi qua điểm enforce hoặc telemetry không ghi được outcome.

Cần phân biệt **mesh L4/L7 deny** với **gateway 401/403** và **application 403**. Mỗi lớp quyết định dựa trên dữ liệu và trust boundary khác nhau.

### 15.3. Mẫu event quyết định an ninh

~~~json
{
  "time_utc": "2026-11-28T06:15:00Z",
  "event_type": "mesh_authorization",
  "enforcement_point": "inventory-waypoint",
  "source_principal_verified": "spiffe://example.test/ns/orders-prod/sa/orders",
  "destination_service": "inventory-api",
  "operation": "GET /v1/stock",
  "decision": "deny",
  "policy_revision": "authz-policy-v8",
  "reason_class": "not_authorized",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"
}
~~~

Đây là **schema khái niệm do nhóm vận hành tự thiết kế**; không phải JSON native mặc định của Istio AuthorizationPolicy/Envoy. Chỉ tạo fields có evidence từ engine. Không tự suy policy quyết định DENY vì thấy HTTP 403 trong app log.

## 16. TLS lỗi ở đâu: handshake, identity và proxy route?

Có những trường hợp request **không có HTTP span/status** vì kết nối thất bại trước L7. Tín hiệu cần thiết có thể nằm ở **proxy transport logs, TLS counters, SDS/cert state và network flow logs**.

| Dấu hiệu | Nguyên nhân có thể | Cần đối chiếu |
|---|---|---|
| TCP connection refused | Upstream listener/endpoint không mở | Route, Service endpoints, container port |
| TLS handshake failure | Cert/trust/ALPN/SNI/mTLS policy sai | Proxy TLS errors, cert validity, SAN |
| Peer cert expired | Rotation/clock/cert distribution lỗi | CA/SDS and node clock metrics |
| Certificate unknown CA | Trust bundle không đồng bộ | Control-plane rollout, roots |
| Identity mismatch | Client và server kỳ vọng principal khác | Verified SAN, trust domain, policy |
| Plaintext tới STRICT mTLS endpoint | Caller không có mesh mTLS phù hợp | PeerAuthentication/security config |
| 503 từ proxy | No healthy upstream, TLS/route/connect failure | Response flags + upstream failure reason |
| HTTP 403 sau TLS OK | Mesh/gateway/app authz | Policy/audit logs theo từng layer |

**Tránh chữa mTLS handshake fail bằng cách tắt certificate verification hoặc chuyển mesh thành PERMISSIVE toàn cụm**. Tìm đúng phiên bản cấu hình, issuer, trust roots, thời gian và identity mismatch.

### 16.1. Chứng chỉ và control plane

Theo dõi:
- Expiration window của workload certificates.
- Rotation successes/failures và SDS secret delivery.
- Control-plane xDS/SDS connection health.
- Trust bundle version đồng nhất giữa regions/clusters.
- Proxy version skew trong rollout.
- CA availability và renewal policy.

Không đưa **private keys hoặc nội dung certificates có dữ liệu nhạy cảm** lên dashboard công khai. Có thể hiển thị ngày hết hạn, issuer/trust domain đã tổng hợp và trạng thái rotation.

## 17. HTTP, HTTP/2, gRPC và opaque TCP

Mục tiêu quan sát khác nhau theo giao thức.

### 17.1. HTTP

HTTP proxy thường thấy method, normalized route, status code, bytes và duration nếu traffic được giải mã ở đúng hop. Tuy nhiên:
- POST không mặc định là mutation nguy hiểm, GET cũng có thể vi phạm semantics.
- HTTP 200 không chứng minh transaction business thành công.
- 4xx có thể là client lỗi hoặc authorization deny có chủ đích.
- HTTP 499 hoặc mã vendor-specific cho client disconnect phải được hiểu theo sản phẩm.

### 17.2. gRPC

Một gRPC request có thể dùng HTTP/2 và nhận **HTTP status 200** trong khi **grpc-status** biểu thị application error. Ví dụ:
- grpc-status=0: OK.
- grpc-status=14: UNAVAILABLE.
- grpc-status=4: DEADLINE_EXCEEDED.
- grpc-status=7: PERMISSION_DENIED.

Không định nghĩa gRPC error ratio bằng cách chỉ nhìn **HTTP 5xx**. Cần metric/trailer hoặc instrumentation ghi gRPC method/status trong phạm vi mà proxy/backend hỗ trợ.

### 17.3. TCP và TLS passthrough

Với opaque TCP hoặc TLS passthrough, proxy có thể chỉ thấy:
- Source/destination, connect attempts.
- Bytes, TCP resets, connection durations.
- Peer TLS metadata nếu proxy thực sự là endpoint của kết nối TLS tương ứng.
- Một số protocol stats nếu có filter cụ thể.

Không tự có **HTTP route, header, gRPC code hoặc request count L7** khi payload không được giải mã. Cần instrumentation của application, database hoặc một L7 gateway được phê duyệt.

### 17.4. HTTP/3, QUIC và UDP

Một số đường HTTP/3/QUIC dùng UDP và có telemetry khác HTTP/2/TCP sidecar. Nếu mesh/CNI/egress policy chỉ quan sát TCP, có nguy cơ điểm mù. Đối chiếu **protocol negotiation, gateway configuration và network path** trước khi kết luận coverage tương đương.

## 18. Retries, timeouts và circuit breaking gây sai lệch số liệu

Một user request thường không tương đương một upstream attempt.

### 18.1. Retry amplification

Giả định một gateway nhận 100 user requests tới Orders; mỗi request Orders gọi Inventory. Nếu 20 request cần retry hai lần trước khi hoàn tất, Inventory có thể nhận **140 attempts** dù gateway chỉ thấy 100 user requests (nếu "retry hai lần" nghĩa tối đa hai attempts bổ sung).

\[
100 + 20 \times 2 = 140 \text{ attempts}
\]

Điểm đo **gateway success** và **destination inbound attempts** phản ánh hai sự thật khác nhau. Có thể thấy Inventory 5xx tăng trong khi gateway vẫn trả 200 sau retry. Nếu chỉ nhìn gateway, rủi ro upstream overload bị che.

### 18.2. Các tín hiệu cần correlate

- **Retry count** và retry reasons theo source upstream cluster.
- **Per-attempt latency** và total request duration.
- **Connect timeout, per-try timeout và overall deadline**.
- **Circuit breaker overflow** và pending request queue.
- **Upstream reset/rejected connections**.
- **Outlier detection/ejection**, healthy endpoint count.
- **Client cancellation** sau khi upstream vẫn đang xử lý.
- **Idempotency**: một POST không idempotent có thể gây tác dụng lặp khi retry sai.

### 18.3. Hedging và race requests

Một số hệ thống gửi nhiều attempts song song để giảm latency; các spans có thể **overlap**. Không tổng các span durations để kết luận số giây user chờ. Theo dõi extra traffic/cost và bảo đảm nghiệp vụ idempotent hoặc có deduplication.

### 18.4. Timeouts không có HTTP response

Nếu kết nối bị reset trước khi có response, application metrics chỉ đếm completed requests có thể bỏ sót. Proxy transport telemetry và client-side failures cần được xem để có error SLI đúng.

## 19. Ingress, egress và ranh giới giữa các mesh

Một service mesh có thể gồm nhiều cluster, VM workloads và egress gateways. Cùng một request có thể đổi identity/route và đi qua TLS termination ở các boundaries.

~~~mermaid
flowchart LR
    C[Internet Client] --> W[WAF / Edge]
    W --> G[Ingress Gateway]
    G --> S[Mesh Service A]
    S --> E[Egress Gateway]
    E --> P[Partner API]
    G -.Edge telemetry.-> OBS[Observability]
    S -.Mesh telemetry.-> OBS
    E -.Egress decision.-> OBS
    P -.Không mặc định instrument.-> OBS
~~~

### 19.1. Identity và trace tại ingress

Client public có thể gửi traceparent/request ID do họ chọn. Ingress nên:
- Áp trust/validation rules để không nhầm externally supplied IDs với authenticated identity.
- Ghi trace ID được chuẩn hóa, correlation ID nội bộ.
- Không chấp nhận X-Forwarded-For/X-User do client tự gửi khi không có trusted proxy chain.
- Ghi TLS termination hop và upstream mTLS hop riêng.
- Giới hạn trace headers/baggage để tránh abuse.

### 19.2. Egress gateway

Egress telemetry hữu ích cho:
- Xác định service nào gọi đối tác nào.
- Phân tích HTTP/CONNECT/TLS outcomes.
- Nhận diện denied outbound attempts và destination drift.
- Quan sát latency và rate limits từ provider.
- Kiểm tra direct-egress bypass bằng flow logs ngoài gateway.

**Ghi traffic tại gateway không chứng minh mọi egress buộc phải đi gateway**. Cần NetworkPolicy/CNI/cloud firewall và negative tests.

### 19.3. Multi-cluster và trust domain

Trace có thể trải qua nhiều clusters với **service identities/trust domains, certificates và sampling policies** khác nhau. Theo dõi trace continuity, policy parity và cross-region data movement; không gửi PII xuyên vùng chỉ vì trace context tự propagate.

## 20. Ambient datapath: tránh suy diễn L7 từ L4

Một số kiến trúc mesh hỗ trợ **ambient** để giảm số sidecars. Các thành phần L4 và L7 có mục đích khác:

- **L4 secure datapath** có thể ghi connection/bytes, workload identity và transport-level outcomes theo feature.
- **Waypoint/L7 proxy** có thể ghi HTTP/gRPC request metrics, authz decisions và spans cho traffic thực sự đi qua.
- **Ingress/egress gateway** có telemetry riêng theo request/connection.

### 20.1. Lỗi phổ biến

Nếu một namespace chỉ dùng L4 datapath mà dashboard lại kỳ vọng **HTTP p95 latency theo route**, timeseries có thể vắng mặt. Không suy là lỗi exporter nếu kiến trúc **không có L7 processing point**.

### 20.2. Một policy L7 không đi qua waypoint

Trong những hệ thống dùng waypoint cho L7 authorization, phải xác minh traffic scope/routing thực sự đi qua waypoint. Một request đi một đường khác có thể không được L7 decision đó quan sát hay thực thi. **Telemetry coverage và policy enforcement placement cần được review cùng nhau.**

### 20.3. Sidecar vs ambient reporting khác nhau

Một dashboard được xây cho sidecar metrics có thể không tương thích ambient L4 metrics hoặc nhãn workloads mới. Khi chuyển chế độ:
1. Xác định canonical SLI point trước/sau.
2. So sánh request counts, HTTP vs TCP signals.
3. Tạo test set với trace/log expectations riêng.
4. Kiểm tra waypoint enrollment và service routing.
5. Chuẩn hóa labels/identity migration.
6. Theo dõi false telemetry gaps khi rollout từng namespace.

## 21. Kiến trúc OpenTelemetry pipeline

**OpenTelemetry (OTel)** cung cấp API/SDK, Collector và conventions giúp xử lý signals từ applications và một số proxy/exporter. Một pipeline thường có **receivers → processors → exporters**, có thể có agent Collector gần source và gateway Collector để tập trung governance.

~~~mermaid
flowchart LR
    P[Envoy access log / trace] --> AG[Agent Collector]
    A[Application OTel SDK] --> AG
    AG --> GC[Gateway Collector]
    GC --> MET[Prometheus-compatible metrics backend]
    GC --> TR[Trace backend]
    GC --> LOG[Log backend]
    GC -.Self metrics and alerts.-> SOC[Telemetry operations]
~~~

Đối với **metrics từ Envoy/Istio**, Prometheus có thể scrape trực tiếp targets thay vì OTel receive push. Vì vậy sơ đồ mô tả kiến trúc tùy chọn, không có một chuẩn routing áp cho tất cả deployments.

### 21.1. Những chức năng pipeline

| Thành phần | Nhiệm vụ | Rủi ro |
|---|---|---|
| **Receiver** | Nhận OTLP/Prometheus/log sources | Endpoint public/tráo danh nếu không auth |
| **Processor** | Batch, memory limit, filter, transform, sampling | Drop data hoặc làm sai semantic labels |
| **Exporter** | Gửi tới backend | Queue backlog, network/TLS failure |
| **Collector agent** | Thu cục bộ theo node/Pod | Node resource usage, privilege |
| **Collector gateway** | Central policy/cross-cluster ingest | Single bottleneck/failure domain |
| **Storage/query backend** | Lưu/truy vấn telemetry | Chi phí, retention và access control |

### 21.2. Một bản pseudopolicy cho pipeline

~~~yaml
# Pseudopolicy; KHÔNG phải cấu hình OpenTelemetry Collector hoàn chỉnh.
telemetry_pipeline:
  source: approved-mesh-proxies-and-application-sdks
  transport: authenticated-otlp-with-tls
  processors:
    - memory-limits
    - redact-secrets-and-sensitive-query-fields
    - normalize-service-environment-attributes
    - bounded-batching
  tracing:
    sampling: governed-head-or-tail
    trace_id_field: trace_id
  storage:
    metrics_retention: per-data-classification
    logs_retention: shorter-for-sensitive-data
    traces_retention: cost-and-privacy-controlled
  exporters:
    destination: approved-telemetry-backends
    egress_policy: least-privilege
  monitoring:
    alert_on: [received-vs-exported-gap, dropped-data, queue-overflow, auth-failure]
~~~

Một **Collector production config** phải tuân schema receivers/processors/exporters chính xác theo release và các components đã được build vào distribution. Không paste pseudopolicy để vận hành trực tiếp.

### 21.3. Không cho telemetry pipeline quyền quá rộng

Collector có thể nhận/request metadata và đôi khi thấy dữ liệu nhạy cảm. Bảo vệ:
- TLS/mTLS hoặc machine auth giữa agents/collectors/backends.
- NetworkPolicy chỉ cho đúng source/destination ports.
- Workload identities và read-only RBAC khi phù hợp.
- Không mount cluster-wide secrets nếu không cần.
- Encrypt in transit/at rest, audit access và retention.
- Hạn chế user truy vấn cross-tenant logs/traces.
- Giảm hoặc xóa dữ liệu nhạy cảm **trước khi export** nếu có thể.

## 22. Istio/Envoy Telemetry: cách cấu hình về mặt ý tưởng

Một mesh deployment có thể bật/tùy chỉnh **metrics, access logging, tracing** thông qua Istio Telemetry API, mesh config hoặc thành phần tương đương. Tùy version, cấu hình có selectors, provider, sampling, dimensions và inheritance.

### 22.1. Vì sao không dùng một setting toàn mesh tùy tiện?

Một thay đổi mesh-wide có thể:
- Bật access logs cho hàng triệu requests và gây cost spike.
- Ghi raw paths có PII nếu format chưa redacted.
- Tạo metric labels unbounded.
- Tăng CPU/latency proxy và collector.
- Thay sampling làm mất trace continuity.
- Tạo log volume bất ngờ khi service mesh retry nhiều lần.

### 22.2. Mẫu logic áp dụng theo scope

~~~yaml
# Pseudopolicy; chỉ mô tả ý định, không phải Istio Telemetry CRD hợp lệ.
telemetry_policy:
  namespace: orders-prod
  workload_selector:
    app: orders-api
  metrics:
    emit: [requests, errors, latency]
    dimensions: [service, operation_template, response_class, revision]
  tracing:
    provider: approved-otlp-collector
    propagation: w3c-tracecontext
    sampling_strategy: bounded-with-error-priority
  access_logs:
    format: structured-json
    fields: [timestamp, service, route_template, status, duration_ms, trace_id]
    sensitive_headers: redact
  controls:
    identity: workload-service-account
    retention: governed
    rollback: previous-tested-config
~~~

Phải chuyển schema ý tưởng thành **Istio Telemetry API hoặc Envoy config thật đúng version**, có canary và verify metrics/logs/traces output; không tự thêm labels hay bật mọi request headers.

### 22.3. Telemetry provider health

Cần theo dõi:
- Proxy config sync và telemetry provider resolution.
- Tracing exporter health và access log sink errors.
- Prometheus targets/up, sample age, scrape duration.
- Collector received/exported/dropped counts.
- Backend ingestion errors và storage/query availability.

Một dashboard thiếu metrics có thể do **scrape/collector/config vấn đề**, không chứng minh service không còn request.

## 23. Correlation: ghép metrics, logs, traces theo sự kiện

Ví dụ một cảnh báo p99 tăng ở Orders API:

1. **Metrics:** chọn window, service, revision và route template có latency tăng.
2. **Exemplars/trace links** nếu có: mở trace đại diện có thời gian đúng.
3. **Distributed trace:** xác định chặng Inventory hay DB lâu nhất.
4. **Proxy logs:** xác nhận retry, upstream reset, 503 local reply, mTLS/authz outcome.
5. **Application logs:** liên kết trace ID để tìm business error và DB query class.
6. **CNI/cloud flow logs:** kiểm tra network path/NAT/packet loss khi cần.
7. **Control-plane audit:** kiểm tra gần đó có deploy/policy/cert/route changes hay không.
8. **SLO:** xem ảnh hưởng tới user-facing request success/latency, không chỉ internal metric.

### 23.1. Timestamp và clock skew

- Dùng timestamp UTC, giữ event time và ingest time riêng.
- Đồng bộ clocks trên nodes/collectors.
- Một span có thời gian “âm” hoặc child bắt đầu trước parent có thể do clock skew/instrumentation.
- Khi SIEM ingest chậm, dùng time window phù hợp và cảnh báo telemetry lag.
- Không sửa timestamp bằng cách trừ một độ lệch tùy ý cho toàn cluster mà không xác minh.

### 23.2. Correlation ID không phải security identity

Request ID có thể do client, gateway hoặc SDK tạo; cần biết **bên nào tin được**. Không dùng một X-Request-ID/traceparent do client tự gửi để cấp quyền truy cập hoặc quy kết hành động nhạy cảm. Authentication identity phải đến từ verified token/TLS/app session và ghi provenance.

### 23.3. Exemplar

Exemplar có thể liên kết một histogram observation với trace ID, hỗ trợ đi từ biểu đồ latency tới trace cụ thể. Không đưa trace ID thành Prometheus label, và không suy exemplar bao phủ mọi request. Kiểm tra feature support/backend và privacy policy.

## 24. Đo độ phủ và chất lượng telemetry

Có telemetry **không đồng nghĩa telemetry đầy đủ hoặc chính xác**.

### 24.1. Những chỉ số độ phủ

| Chỉ số | Cách hiểu | Sai lệch thường gặp |
|---|---|---|
| Mesh enrollment | Workloads thực sự đi qua mesh datapath | Pod chưa inject/waypoint chưa gắn |
| Proxy metrics coverage | Service có metrics trong window | Scrape target missing, label drift |
| Request log coverage | Các hop được ghi access logs theo policy | Sampling, log sink outages |
| Trace continuity | Trace có spans qua những service kỳ vọng | App không propagate, sampling |
| Collector delivery | Spans/logs nhận so với export thành công | Queue drop, exporter timeout |
| Identity coverage | Bao nhiêu flows có verified peer identity | Opaque/external traffic, metadata thiếu |
| Policy audit coverage | Quyết định allow/deny có được ghi hay không | Engine chưa bật audit, log loss |
| Time freshness | Độ trễ từ event tới query available | Buffer, SIEM backlog, clock skew |

### 24.2. Tỷ lệ minh họa

Giả sử có 80 workloads trong scope, trong đó 72 workloads đã được xác nhận đi qua datapath cần thiết:

\[
\text{Enrollment coverage}=\frac{72}{80}\times100\%=90\%
\]

Đây **không phải 90% request coverage** nếu 8 workloads bị thiếu xử lý phần lớn traffic. Khi cần, đo coverage theo **request volume, criticality và enforcement path**, không chỉ số workload.

### 24.3. Freshness và lag

Một Collector có thể vẫn up nhưng exporter đang queue dữ liệu hàng chục phút. Dashboard nhìn một window gần hiện tại sẽ thấy “không có traffic”. Theo dõi **last event timestamp**, received/exported/dropped rates và ingestion lag; cần alert riêng cho telemetry loss để tránh đưa ra quyết định sai.

### 24.4. Thu đủ mà không làm mesh nghẽn

Telemetry không được biến thành nút cổ chai request path. Với phần lớn thiết kế, proxy cần có queue/backpressure và error-handling cho log/tracing exporters; cần kiểm tra mặc định của provider và quyết định **availability vs audit completeness** theo mức quan trọng dữ liệu. Không chấp nhận silent loss nếu dữ liệu bắt buộc cho pháp lý/bảo mật mà không có cơ chế thay thế và cảnh báo.

## 25. Security monitoring từ request telemetry

Quan sát request trong service mesh có thể cung cấp tín hiệu hỗ trợ phát hiện tấn công và lỗi policy, nhưng **không thay thế IDS/IPS, WAF, API authorization hay endpoint security**. Một kỹ thuật tấn công có thể xảy ra hoàn toàn trong business logic dù mọi kết nối mTLS hợp lệ.

### 25.1. Các nhóm tín hiệu đáng theo dõi

| Nhóm | Tín hiệu gợi ý | Cần phân biệt |
|---|---|---|
| **mTLS/identity** | Handshake fail, peer cert invalid, trust-domain mismatch, cert gần hết hạn | Config rollout với hành vi bất thường |
| **Authorization** | Tăng deny decisions, 401/403, caller/route ngoài baseline | Deny hợp lệ so với tấn công |
| **Egress bất thường** | Workload gọi hostname/IP mới, byte outbound tăng | New partner integration so với data exfil |
| **Lateral movement** | Dev→Prod attempts, Pod gọi management endpoint lạ | Positive security control chặn thành công |
| **Application-layer DoS** | RPS, concurrent requests, 429, pending requests, CPU/proxy overload | Legitimate campaign/flash sale |
| **Retry amplification** | Upstream attempts nhiều hơn user requests, queue tăng | Failover/temporary dependency outage |
| **Telemetry evasion** | Mất source/destination report, missing spans/logs | Exporter failure, route bypass, intentional tampering |
| **TLS downgrade** | Tăng plaintext connections trong boundary yêu cầu mTLS | Migration window hoặc cấu hình sai |
| **Policy drift** | Policy revision/sidecar version/route đổi không đúng change window | Platform rollout được phê duyệt |
| **Sensitive data exposure** | Raw tokens/PII xuất hiện trong logs/labels | Redaction regression, debug mode mở sai |

### 25.2. Không đồng nhất deny với sự cố

Một request **bị AuthorizationPolicy từ chối đúng** là dấu hiệu kiểm soát hoạt động. Alert nên tính **tần suất, nguồn, loại route, độ nhạy tài sản và thay đổi so baseline**, thay vì đánh dấu mọi HTTP 403 là outage.

Ngược lại, nếu policy dự định deny Dev→Prod nhưng telemetry thấy 200 từ Prod cho source Dev, đây có thể là **policy bypass hoặc alternate application path** và cần điều tra. Phải xác minh identity từ peer/auth token đáng tin, không quy kết từ một header dễ giả mạo.

### 25.3. Triangulation security events

Một cuộc gọi trái quyền tới production admin API có thể để lại:
- Gateway log: route request đến từ một client.
- Destination proxy: verified peer workload identity hoặc deny.
- Application audit: end-user/session authorization fail.
- CNI/cloud flows: source/destination IP/port và policy.
- Kubernetes/cloud audit: thay đổi policy/deployment gần thời điểm đó.

**Một event đơn lẻ không đủ** để suy actor, mức ảnh hưởng và quyền thực tế. Ghép theo **timestamp, trace/correlation ID, workload UID, verified identity và policy version**.

## 26. Threat model của chính telemetry

Telemetry là một hệ thống dữ liệu và quyền hạn. Nó có thể bị thao túng, lạm dụng, mất khả dụng hoặc tạo ra dữ liệu nhạy cảm ngoài dự kiến.

### 26.1. Tài sản cần bảo vệ

- Traces/metrics/logs chứa network topology, service URLs, endpoint mappings và workload identities.
- Application logs có user actions/tenant identifiers.
- Collector service accounts, exporter tokens, dashboard credentials.
- TLS credentials giữa proxies, collectors và backends.
- Storage, query API, alerting channels và incident tickets.
- Sampling/retention/redaction configurations và audit trail.
- Telemetry pipeline availability để SOC/SRE còn nhìn được sự cố.

### 26.2. Kịch bản đe dọa

| Rủi ro | Điều có thể xảy ra | Phòng vệ |
|---|---|---|
| **Trace context spoofing** | Client gắn traceparent có chủ đích để gây correlation sai | Validate/trust boundary, edge regeneration theo policy |
| **Log injection** | Input user chứa newline/format làm sai event parsing | Structured logging, escaping, input bounds |
| **High-cardinality attack** | URL/header tạo hàng triệu nhãn | Route templates, allowlist dimensions, quotas |
| **Telemetry exfiltration** | Logs/traces gửi tới backend không được cấp phép | Egress controls, TLS, IAM và approved destinations |
| **PII/token leakage** | Proxy log raw headers/URLs hoặc spans body | Redaction trước export, retention và data classification |
| **Misleading sampled traces** | Tail sampler chỉ giữ errors làm tỷ lệ lỗi tưởng rất cao | Metrics SLI toàn traffic, sampling metadata |
| **Audit gap** | Collector queue overflow, backend ingest lỗi | Alerts on drop/lag/absence, buffer/HA |
| **Credential compromise** | Người lạ truy vấn log của mọi tenant | RBAC/ABAC, scoped tokens, query audit |
| **Tampering/disabled telemetry** | Đổi Telemetry config để giảm logs | GitOps, cloud/K8s audit, independent monitoring |
| **Untrusted metadata** | Tin X-User, X-Peer-Identity từ request như verified data | Xây danh tính từ auth engine/proxy TLS state |

### 26.3. Tại sao trace ID không là bí mật?

Trace ID chủ yếu dùng để **tương quan**, không phải credential. Nó có thể được chia sẻ trong response headers/tickets nếu policy cho phép, nhưng không được dùng làm token để truy vấn logs/traces không có authorization. API tìm trace phải kiểm tra **RBAC, tenant scope và audit**, dù requester biết ID hợp lệ.

### 26.4. Telemetry tampering và independent monitoring

Nếu một attacker chiếm app có thể sửa application logs, proxy/collector logs tại điểm thực thi độc lập có thể hỗ trợ phát hiện; nhưng nếu attacker chiếm node/CNI hoặc control plane, cần thêm cloud flow logs, immutable/audit sinks hoặc nguồn khác. **“Có log” không tự đồng nghĩa tamper-proof**.

## 27. Privacy, retention và quyền truy cập dữ liệu telemetry

Telemetry phục vụ điều hành nhưng có thể tiết lộ:
- IP/hostnames private, cấu trúc service/namespace.
- Thời gian người dùng giao dịch, route nhạy cảm.
- Tên đối tác và kết nối nội bộ.
- User IDs, JWT claims, tài liệu nghiệp vụ nếu app instrument sai.
- Source principal và security policy decisions.
- Secrets trong URLs/headers hoặc exception messages.

### 27.1. Data minimization

1. **Metrics:** chỉ nhãn bounded, không chứa user IDs hay secrets.
2. **Access logs:** route template, status, duration, approved identity fields; không raw header/body.
3. **Traces:** span name và attributes đã sanitize; không đưa payment details hoặc object content.
4. **Security audit:** giữ verified identity/policy outcome nhưng giới hạn quyền xem và retention theo yêu cầu.
5. **Payload captures:** chỉ khi cần, được phê duyệt, phân vùng truy cập và xóa theo hạn.

### 27.2. Phân loại quyền

| Role | Quyền hợp lý | Không mặc định |
|---|---|---|
| Developer dịch vụ | Metrics/traces của service sở hữu, logs đã redacted | Traces/PII mọi tenant |
| SRE/on-call | Cross-service debugging trong phạm vi incident | Secret/raw body không giới hạn |
| SOC | Security alerts, policy decisions và correlation theo scope | Quyền mutate toàn mesh |
| Privacy/compliance reviewer | Audit metadata/retention theo nhu cầu | Root access vào production nodes |
| Telemetry operator | Pipeline health, aggregation, storage config | Business user identity tự do |
| Break-glass | Truy cập khẩn cấp có ticket/time limit/audit | Quyền thường trực cho mọi người |

### 27.3. Retention theo rủi ro, không chỉ chi phí

Không nên tuyên bố một con số ngày lưu giữ áp dụng cho mọi tổ chức. Hãy xác định retention dựa trên **phân loại dữ liệu, mục đích, pháp lý, điều tra, chi phí, vùng địa lý và khả năng xóa**. Nếu bắt buộc lưu lâu cho audit, tách và kiểm soát dữ liệu khác với debug traces chứa metadata phong phú.

### 27.4. Xử lý sự cố lộ token qua logs

Một quy trình an toàn:
- Chặn phát sinh log mới tại nguồn; chỉnh redaction hoặc rollback cấu hình.
- Giới hạn truy cập, xác định nơi đã replicate/index/cache.
- Đánh giá thời gian token còn hiệu lực và truy cập khả nghi.
- Thu hồi/rotate credentials khi cần.
- Xử lý xóa/hạn chế bản sao theo quy trình data incident.
- Test hồi quy ingestion/exports sau thay đổi.

**Không chỉ xóa một dòng dashboard** rồi cho rằng token đã không còn ở storage, SIEM hoặc backup.

## 28. Thiết kế observability cho môi trường nhiều cluster/region

Telemetry cần nhận diện chính xác **cluster, region, environment, mesh trust domain và service revision**. Nếu tất cả đều dùng service.name=orders, một dashboard có thể gộp traffic production với staging hoặc region khác.

### 28.1. Topology thường gặp

~~~mermaid
flowchart TB
    subgraph REGION_A[Region A]
      A[Mesh workloads A] --> CA[Collector A]
    end
    subgraph REGION_B[Region B]
      B[Mesh workloads B] --> CB[Collector B]
    end
    CA --> BACK[Approved central telemetry backend]
    CB --> BACK
    BACK --> DASH[Scoped dashboards / alerts]
    CTRL[Policy and schema governance] -.Applies.-> CA
    CTRL -.Applies.-> CB
~~~

### 28.2. Những quyết định cần rõ

- Telemetry có phải **ở lại region** theo data residency requirement?
- Backends có được cross-account/tenant visibility không?
- Trace IDs được propagate giữa regions qua trust boundary nào?
- Collector failover có thay exporter identity/cert và mất spans không?
- Metrics schema có đồng nhất giữa sidecar/ambient hoặc versions không?
- Có liên kết time series theo cluster/namespace để tránh gộp sai không?
- Nếu một region down, có còn **independent telemetry** để xác nhận DR hoạt động không?
- Có network egress restrictions cho telemetry exporters và private endpoints?

### 28.3. Không bắt mọi proxy gửi xuyên region nếu không cần

Tập trung tất cả logs/traces qua một Collector ở vùng xa có thể làm tăng latency, transfer costs, outage blast radius và nghĩa vụ privacy. Có thể dùng **regional collectors, local buffering và federated queries** theo nhu cầu.

### 28.4. Disaster recovery phải có observability parity

Failover thành công không chỉ là API HTTP 200; phải kiểm tra **mTLS peer identity, authorization denies, metrics/traces, log access, alerts và ingest freshness** ở region dự phòng.

## 29. Quy trình triển khai telemetry an toàn theo giai đoạn

### Giai đoạn 1 — Inventory và SLI

1. Xác định services, owners, trust boundaries, critical routes và data classification.
2. Vẽ flow chính: client→gateway→service→dependency.
3. Quy định **canonical reporter** cho user request rate/error/latency.
4. Xác định cần metrics, access logs, traces, app spans hay flow logs ở từng hop.
5. Kiểm tra sidecar/ambient/waypoint enrollment và protocol visibility.
6. Ghi số liệu traffic, SLO và cost/retention budgets trước thay đổi.

### Giai đoạn 2 — Thiết kế schema và privacy

1. Chọn semantic conventions/naming rules có version.
2. Chuẩn hóa service.name, namespace, cluster, environment, revision, route template.
3. Chỉ dùng bounded labels cho metrics.
4. Chọn trace propagation W3C/B3 migration policy.
5. Redact secrets ở source/collector, tránh raw payload.
6. Xác định role của SRE, SOC, developer và tenant separation.
7. Định nghĩa sampling, telemetry freshness và drop-rate SLO.
8. Quy định TLS/mTLS và IAM cho exporter/collector/backend.

### Giai đoạn 3 — Pilot trong lab/staging

1. Bật metrics trước và xác nhận Rate/Errors/Duration theo reporter.
2. Bật structured access logs với sampling/retention phù hợp.
3. Instrument application spans và verify trace propagation qua 2–3 services.
4. Kiểm tra HTTP/gRPC/TCP behavior, retry và timeout outcomes.
5. Kiểm tra mTLS identity và AuthorizationPolicy denies bằng test đã duyệt.
6. Kiểm tra logs không chứa Authorization/PII.
7. Đo overhead CPU/memory, collector traffic và storage cost.
8. Thử collector restart/exporter failures, xác nhận alerts on loss.
9. Tạo test evidence về config version và route/service map.

### Giai đoạn 4 — Rollout production có kiểm soát

1. Canary theo namespace/workload/region.
2. Theo dõi SLO của ứng dụng và sức khỏe proxy/collector.
3. So request counts với baseline gateway/app, giải thích chênh lệch.
4. Kiểm soát cardinality và sampling ratio.
5. Theo dõi exporter queue, dropped spans/logs và ingestion lag.
6. Kiểm thử data-access scopes trước khi mở dashboard cho nhiều đội.
7. Duy trì cấu hình rollback, không tắt mTLS hoặc authorization để giúp metrics xuất hiện.
8. Ghi lại quyết định và owner cho mọi ngoại lệ có thời hạn.

### Giai đoạn 5 — Vận hành liên tục

- Review critical service coverage và missing telemetry.
- Kiểm tra CNI/mesh/gateway/OTel upgrades làm đổi metric names/labels không.
- Diễn tập cert rotation, policy deny, upstream timeout, retry storm và collector failure.
- Tối ưu sampling/car​dinality dựa trên dữ liệu thực (không bỏ các tín hiệu bắt buộc).
- Lập báo cáo định kỳ **SLI, policy changes, telemetry quality và data retention**.

## 30. Thực hành đọc-only trong một Kubernetes lab được cấp quyền

Các lệnh sau chủ yếu là **đọc cấu hình, trạng thái và logs**. Không chạy trên cluster ngoài quyền; mọi output có thể chứa private topology, identifiers hoặc dữ liệu nhạy cảm nên phải redaction trước khi chia sẻ.

### 30.1. Xem workload và proxy enrollment

~~~bash
# Đọc Pod labels và containers của namespace lab
kubectl get pods -n orders-prod -o wide --show-labels

# Xem chi tiết một Pod bạn có quyền
kubectl describe pod orders-api-lab-0 -n orders-prod
~~~

Nếu dùng Istio sidecar, có thể quan sát container **istio-proxy** trong danh sách Pod; nếu dùng ambient, không thấy sidecar **không đồng nghĩa Pod không thuộc mesh**. Cần kiểm tra ambient enrollment và waypoint routing bằng công cụ đúng version.

### 30.2. Xem trạng thái mesh proxy khi có istioctl

~~~bash
# Chỉ đọc control-plane/proxy synchronization status
istioctl proxy-status

# Với đúng Pod lab thuộc quyền, xem routes được proxy biết
istioctl proxy-config routes orders-api-lab-0 -n orders-prod
~~~

Không mặc định hai lệnh hoạt động trong mọi mesh hoặc ambient-only deployment. Proxy-config output có thể bộc lộ internal hostnames/routes, nên chỉ sử dụng với RBAC/authorization phù hợp.

### 30.3. Xem cấu hình Telemetry và policy

~~~bash
# Chỉ đọc CRDs khi cluster đã cài Istio API tương ứng
kubectl get telemetry -A
kubectl get peerauthentications -A
kubectl get authorizationpolicies -A

# Xem service và deployments trong một namespace do bạn quản trị
kubectl get svc,deploy -n orders-prod
~~~

Nếu CRD không có hoặc người dùng không được phép xem, **không nâng quyền trái phép**. Một object Telemetry/AuthorizationPolicy hiện diện không tự chứng minh proxy đã nhận cấu hình hay traffic đang đi qua datapath.

### 30.4. Đọc logs trong một cửa sổ nhỏ

~~~bash
# Chỉ nếu có container proxy và bạn được phép xem logs
kubectl logs -n orders-prod orders-api-lab-0 \
  -c istio-proxy --since=10m --tail=100

# Application logs để đối chiếu trace/request ID
kubectl logs -n orders-prod orders-api-lab-0 \
  -c app --since=10m --tail=100
~~~

**Access logging có thể chưa bật**, Pod/container names chỉ là placeholder. Không copy logs chứa token/PII lên ticket công khai. Một log không có nghĩa proxy đã bỏ qua request nếu policy logging, sampling hoặc exporter không được bật.

### 30.5. Một phép thử HTTPS nhỏ trên tài sản lab

~~~bash
# Một request có giới hạn thời gian tới endpoint lab đã được cấp quyền
curl --silent --show-error --max-time 5 \
  -i https://api.lab.example/health
~~~

Lệnh chỉ cho thấy **một kết quả tại thời điểm gọi**. Không dùng --insecure để tắt TLS verification, không yêu cầu bắt packet người khác và không gọi hàng loạt endpoints không thuộc quyền.

### 30.6. Phân tích khi metrics rỗng

1. Workload có traffic trong window thật không?
2. Mesh enrollment/proxy config đã đồng bộ chưa?
3. Telemetry provider/exporter có bật loại tín hiệu tương ứng không?
4. HTTP có đi qua một L7 datapath hay chỉ L4/TLS passthrough?
5. Scrape target up và labels đúng không?
6. Collector receiving/exporting hoặc storage ingest có lỗi không?
7. Query có dùng metric tên/đơn vị/labels theo version hiện tại không?
8. Dashboard có lọc sai environment/cluster/namespace không?
9. Có sampling/logging policy khiến dữ liệu không được xuất không?
10. Có direct bypass traffic không, theo network flow evidence?

**Đừng mở toàn bộ access logging/100% tracing trên production để tìm lỗi query**; cần xác định nguồn thiếu và tác động tài nguyên trước.

## 31. Ma trận kiểm thử request telemetry và mTLS

Ma trận dưới đây là **kế hoạch nghiệm thu**, không phải tuyên bố các phép thử đã được chạy. Với mỗi case cần **owner, environment, cluster/version, source/destination workload, sampling policy, timestamp, expected result, actual result, trace/log/metric evidence và trạng thái PASS/FAIL/BLOCKED/NOT_RUN**. Những trường hợp có khả năng gây lỗi hoặc tải lớn chỉ chạy trong lab/staging hoặc change window đã được phê duyệt.

| ID | Tình huống | Kỳ vọng | Bằng chứng |
|---|---|---|---|
| T01 | Một request qua ingress gateway | Có gateway request metric/log đúng scope | Gateway access log + counter |
| T02 | Một request Orders → Inventory qua sidecars | Ghi tín hiệu ở source và destination | Proxy logs, workload IDs |
| T03 | Reporter source/destination cùng tồn tại | Dashboard không cộng đôi user requests | Metrics labels + query review |
| T04 | HTTP 201 tại gateway | User-facing success theo API contract | Gateway status + app audit |
| T05 | HTTP 503 do app tự trả | Phân biệt app error với proxy local reply | Proxy flags + app logs |
| T06 | Không có healthy upstream | Có proxy-local error evidence | Upstream stats/flags |
| T07 | TLS handshake fail trong lab | Có transport errors dù không có HTTP span | TLS/proxy error counters |
| T08 | mTLS peer identity hợp lệ | Verified principal được ghi từ TLS state | Proxy trust metadata |
| T09 | Peer cert invalid | Bị từ chối và có TLS failure evidence | CA/cert/proxy logs |
| T10 | Request plaintext tới STRICT boundary | Không được chấp nhận theo policy | Mesh policy + handshake metrics |
| T11 | Peer mTLS hợp lệ nhưng app authZ sai | App từ chối đúng dù transport OK | TLS success + app 403 |
| T12 | Mesh AuthorizationPolicy deny | Từ chối và ghi decision khi cấu hình audit | Authz/proxy evidence |
| T13 | 401 từ gateway do thiếu token | Không nhầm với mesh mTLS deny | Gateway auth logs |
| T14 | Traceparent W3C hợp lệ qua 3 hops | Trace ID nhất quán, parent-child hợp lệ | Trace graph |
| T15 | Service không propagate trace context | Phát hiện disconnected trace, không suy mất request | Headers + app SDK logs |
| T16 | Client tự gửi traceparent giả | Trust policy không dùng trace ID làm identity | Edge validation/audit |
| T17 | Baggage chứa dữ liệu không được phép trong lab | Field bị loại theo privacy policy | Collector sanitization test |
| T18 | Head sampling 1% | Trace volume theo budget, metrics vẫn đo toàn traffic | Sampler + counters |
| T19 | Tail sampling ưu tiên errors | Không dùng sampled errors làm SLO numerator | Sampler config + SLI query |
| T20 | Collector exporter down | Có alert drops/queue/lag | Collector self metrics |
| T21 | Collector restart | Ứng dụng vẫn theo availability design; mất dữ liệu được giám sát | App SLO + telemetry health |
| T22 | Metric label là raw URL | Policy phát hiện cardinality/PII risk | Config review |
| T23 | Route template thay raw path | Nhãn bounded, không có user ID | Scrape labels |
| T24 | Traces trong hai regions | Có region/cluster scoping và retention đúng | Trace attributes + backend RBAC |
| T25 | gRPC trả HTTP 200 nhưng grpc-status=14 | Ghi RPC error đúng contract | gRPC telemetry |
| T26 | Opaque TCP traffic | Chỉ kỳ vọng L4/TCP stats, không giả L7 spans | Proxy capabilities + flows |
| T27 | TLS passthrough | Không giả định proxy thấy plaintext HTTP | Gateway route + logs |
| T28 | QUIC/UDP egress ở scope được phép | Đo/chặn theo datapath thật | CNI/firewall telemetry |
| T29 | Orders gọi Inventory retry hai lần | Upstream attempts tăng hơn user requests | Retry counters + traces |
| T30 | Per-try timeout trong lab | Chẩn đoán timeout đúng hop | Proxy flags/trace timestamps |
| T31 | Circuit breaker overflow | Có saturation/errors và upstream queue evidence | Envoy stats |
| T32 | User hủy request sớm | Không tự coi là application 5xx | Client/proxy disconnect logs |
| T33 | Proxy metrics endpoint mất scrape | Alert telemetry absence | Prometheus target health |
| T34 | Metric name đổi khi upgrade | Dashboards phát hiện schema regression | Before/after schema diff |
| T35 | Ambient L4-only workload | Không kỳ vọng HTTP route metrics | Enrollment + L4 signals |
| T36 | Request qua waypoint | Có L7 request telemetry đúng waypoint | Waypoint logs/metrics |
| T37 | Direct bypass không qua egress gateway | Đường ngoài policy được CNI/firewall kiểm soát | Gateway vs flow evidence |
| T38 | IP được SNAT ở gateway | Attribution theo Pod UID/identity được giữ | NAT mapping + proxy logs |
| T39 | Logs chứa Authorization trong lab | Redaction chặn trước export | Ingestion test, không dùng secret thật |
| T40 | Trace lookup từ user không cùng tenant | Backend RBAC từ chối | Query audit |
| T41 | Policy change bị sửa trái phép | Cloud/K8s audit + alert | Control-plane events |
| T42 | Certificate rotation giữa nhiều clusters | Không gây mTLS failures kéo dài | SDS/CA health + app SLI |
| T43 | Failover region | SLI/identity/authz/telemetry parity | DR checklist + traces |
| T44 | Sampling bị tắt trong một workload | Có cảnh báo coverage/trace continuity | Config drift + telemetry tests |
| T45 | Hệ thống logging nghẽn | Không mất tín hiệu bắt buộc âm thầm | Queue/dropped logs alerts |
| T46 | HTTP errors tăng nhưng app logs không có | Phân biệt proxy-generated errors | Flags + app log correlation |
| T47 | Requests qua queue async | Dùng links/propagation phù hợp | Producer/consumer spans |
| T48 | Dashboard p95 lấy nhầm đơn vị | Dashboard cảnh báo/test ms vs s | Query/unit review |

Không chạy các test **mTLS downgrade, privileged debug, load/DoS hoặc policy deny cố ý** trên production ngoài quy trình change được phê duyệt. Positive tests **và negative tests** đều cần bằng chứng từ ít nhất hai lớp nếu đang kiểm tra security controls.

## 32. Chẩn đoán theo triệu chứng

### 32.1. Gateway trả 503 nhưng app không có log

**Khả năng:** proxy tự tạo local reply vì no healthy upstream, connect failure, upstream TLS error, circuit breaker hoặc timeout trước khi đến app.

**Kiểm tra:** gateway response flags, upstream cluster, endpoint health, mTLS handshake, route, proxy config sync và CNI/flow logs. Đừng mặc định ứng dụng đã trả 503.

### 32.2. Metrics bình thường nhưng người dùng báo lỗi

**Khả năng:** metric đo sai hop/reporter, excludes request class quan trọng, client cancellation không tính, gRPC status khác HTTP hoặc telemetry chỉ thấy healthy subset.

**Kiểm tra:** canonical SLI tại user-facing boundary, access logs, gRPC status, gateway vs destination counts, regions/versions và synthetic transaction. HTTP 200 không tự là business success.

### 32.3. Traces gãy sau Orders API

**Khả năng:** SDK không inject context, B3/W3C mismatch, message broker mất context, sampling khác nhau hoặc Collector không nhận spans.

**Kiểm tra:** trace headers ở boundary được phép, app instrumentation, exporter queue/drop, sampling policies và hop visibility. Không tăng sampling 100% trước khi hiểu lỗi propagation.

### 32.4. Dashboard RPS tăng gấp đôi sau bật mesh

**Khả năng:** cộng source và destination reporters hoặc cộng ingress gateway + destination services; upstream retries tạo nhiều attempts.

**Kiểm tra:** query labels, canonical reporter, request counts ở edge, service call graph và retry counters. Không dùng tổng mọi proxy inbound/outbound làm user RPS.

### 32.5. p95 latency tăng sau bật tracing

**Khả năng:** sampling 100%, synchronous exporters, CPU/IO overhead, trace attributes lớn hoặc Collector backpressure. Nhưng cũng có thể là vấn đề app độc lập.

**Kiểm tra:** before/after canary, app SLI, proxy CPU, queue sizes, bytes exported, dropped spans và load pattern. Tối ưu sampling/batching đúng scope; không bỏ các security audit events cần thiết.

### 32.6. mTLS handshake failures sau cert rotation

**Khả năng:** trust bundle lệch, clock skew, SDS stale, cert expired, peer identity thay đổi hoặc version skew.

**Kiểm tra:** CA/SDS metrics, cert expiration, trust domains, proxy xDS sync, service principal expectations và network TLS logs. Không chuyển toàn mesh về permissive chỉ để khôi phục nhanh.

### 32.7. Access log ghi 403 nhưng mesh AuthorizationPolicy không deny

**Khả năng:** gateway JWT auth, application authorization, WAF/filter, upstream service trả 403 hoặc policy engine khác.

**Kiểm tra:** enforcement point, response flags, verified peer, authz decision logs và app route audit. HTTP 403 không tự bằng mesh deny.

### 32.8. Có TCP metrics nhưng không có HTTP latency

**Khả năng:** ambient L4-only, TCP opaque, TLS passthrough, wrong protocol detection hoặc traffic không đi waypoint.

**Kiểm tra:** service port/protocol, L7 gateway/waypoint enrollment, datapath routing và exporter capability. Không tự thêm HTTP metrics ở nơi không xử lý HTTP.

### 32.9. Trace chứa user email trong span attribute

**Nguyên nhân:** SDK/automatic instrumentation hoặc custom span attributes ghi PII. Xử lý như rủi ro data leakage: dừng ghi mới, redaction trước export, xem dữ liệu đã lưu, quyền truy cập và retention, phối hợp privacy/incident owner.

### 32.10. Prometheus thấy target up nhưng metric trống

**Khả năng:** proxy không phát metric, telemetry disabled, metric name đổi, wrong scrape path, wrong labels, filter/drop trong Collector hoặc traffic L4 không khớp HTTP counter.

**Kiểm tra:** scrape payload trong môi trường được cấp quyền, proxy config, target labels, query và metric type. Target up không chứng minh schema telemetry đủ.

### 32.11. Trace latency không khớp gateway latency

**Khả năng:** sampling, missing spans, client/edge waiting time, network queue, connection setup, parallel work, clock skew hoặc khác SLI boundary.

**Kiểm tra:** start/end timestamps, span kind, trace completeness, ingress duration và retry attempts. Không cộng mọi span durations trực tiếp.

### 32.12. Sau failover chỉ một cluster không có telemetry

**Khả năng:** collector exporter TLS/IAM, network egress, mesh Telemetry config, policy/schema drift hoặc backend residency rule.

**Kiểm tra:** collector self metrics, regional endpoints/certs, data pipeline alert, service SLI độc lập và DR configuration diff. Không kết luận region down chỉ vì dashboard không có chuỗi.

## 33. Tình huống phân tích và đáp án gợi ý

### Tình huống A — Một user request, bốn access logs

Gateway, Orders source, Inventory destination và Inventory application đều ghi request; team cộng logs để ra traffic người dùng.

**Gợi ý:** log events là nhiều góc nhìn cùng một request. Chọn canonical SLI source, ví dụ ingress gateway; dùng trace ID để correlate, không cộng mọi logs làm user request count.

### Tình huống B — mTLS success nhưng truy cập tenant khác vẫn được

Orders API có peer identity hợp lệ và mTLS thành công nhưng cho phép đọc đơn hàng của tenant khác.

**Gợi ý:** mTLS xác thực workload/peer, không thay business object authorization. Cần app authZ theo tenant/resource, ghi audit outcome và kiểm thử negative cases.

### Tình huống C — Một service chỉ có TCP metrics

Một workload ambient chỉ đi qua L4 datapath, dashboard không tìm thấy HTTP response_code/p95.

**Gợi ý:** không mặc định có L7 proxy. Xác minh waypoint/L7 enrollment hoặc application instrumentation; dùng TCP metrics đúng khả năng khi không có HTTP visibility.

### Tình huống D — Gateway báo 503 nhưng backend khỏe

Tất cả Pods Ready; gateway logs có upstream connect failure và TLS transport reason.

**Gợi ý:** tập trung TLS/route/cert/proxy, không chỉ readiness. Phân biệt local reply, mTLS handshake, trust bundle và app-generated 503.

### Tình huống E — gRPC HTTP 200 nhưng giao dịch lỗi

Một RPC có HTTP 200 và grpc-status=14, dashboard chỉ đếm HTTP 5xx.

**Gợi ý:** gRPC application status khác HTTP transport status. Instrument gRPC status; xây SLI theo RPC contract.

### Tình huống F — Traces đứt tại message queue

Orders gửi message rồi worker xử lý sau, trace không có child span của worker.

**Gợi ý:** propagation qua message headers và producer/consumer spans hoặc span links, theo async semantics. Queue không tự propagate W3C context nếu app không cấu hình.

### Tình huống G — Trace ID trong metrics labels

Team đưa mỗi trace ID vào nhãn latency histogram để tiện click.

**Gợi ý:** cardinality rất cao. Dùng exemplars/trace links, giữ trace IDs trong logs/traces có controls, không dùng làm Prometheus labels.

### Tình huống H — Tracing tăng từ 1% lên 100%

Một incident được xử lý bằng cách bật 100% traces trên toàn cluster; proxies/Collector quá tải.

**Gợi ý:** sampling increase phải có scope, thời hạn, capacity/retention budget; ưu tiên tail/error sampling hoặc targeted services. Theo dõi drop rates và app SLO.

### Tình huống I — 403 tăng sau bật AuthorizationPolicy

Policy mới deny Dev→Prod đúng thiết kế, dashboard coi tất cả 403 là outage.

**Gợi ý:** tách security denies khỏi application availability errors; đánh giá xu hướng và xác minh caller/route/policy revision. Deny hợp lệ có thể là bằng chứng bảo vệ.

### Tình huống J — Access log chứa Authorization

Proxy dùng log format ghi toàn bộ headers để debug, khiến JWT xuất hiện ở backend chung.

**Gợi ý:** ngừng capture nhạy cảm, redact tại nguồn, đánh giá storage/replicas, quyền xem và rotate/revoke token theo sự cố. Không chỉ ẩn dữ liệu ở UI.

### Tình huống K — Đổi service revision làm dashboard mất data

Sau rollout, label canonical_service hoặc revision đổi, query chỉ lọc tên cũ.

**Gợi ý:** telemetry schema/version migration và config diff; kiểm tra scrape output, query filters và region/namespace, không suy service ngừng phục vụ.

### Tình huống L — Source reporter gấp đôi destination

Orders outbound gọi Inventory hai retries; Inventory logs có những attempts khác gateway requests.

**Gợi ý:** phân biệt user request count, upstream attempt count, retry count và logging coverage. Không ép mọi điểm quan sát phải có cùng số lượng.

### Tình huống M — Client giả traceparent hợp lệ

Một client public gửi traceparent với ID đã xuất hiện trong logs nội bộ.

**Gợi ý:** trace context không là identity hoặc authorization. Trusted edge phải áp validation/restart trace policy, query backend vẫn kiểm tra RBAC/tenant scope.

### Tình huống N — Root cert thay nhưng region dự phòng vẫn dùng bản cũ

Primary mTLS OK, DR region có nhiều handshake failures.

**Gợi ý:** kiểm tra trust bundle, SDS, CA rotation, proxy sync và time skew; DR phải có security/telemetry parity. Không tắt TLS verification.

### Tình huống O — NetworkPolicy deny mà access logs của mesh không thấy

CNI chặn packet trước proxy; logs proxy im lặng.

**Gợi ý:** điểm chặn nằm trước mesh. Dùng CNI/cloud flow logs/NetworkPolicy verdict; thiếu proxy access log không chứng minh không có attempted connection.

### Tình huống P — Egress gateway logs không thấy traffic tới SaaS

Ứng dụng vẫn gọi SaaS thành công, nhưng gateway logs không có event.

**Gợi ý:** có thể direct-egress bypass, PrivateLink/path khác, telemetry disabled hoặc log loss. Cần traffic path, CNI/firewall evidence và enforcement tests.

### Tình huống Q — p95 của ba Pods được tính trung bình

Một dashboard lấy p95 Pod A, B, C rồi tính trung bình thành service p95.

**Gợi ý:** percentiles không aggregate bằng trung bình. Dùng histogram buckets/appropriate backend aggregation và đúng units.

### Tình huống R — SIEM chậm ingest nhưng dashboard hiển thị traffic thấp

Exporter queue tăng, logs đến muộn 20 phút, SOC nghĩ traffic đã dừng.

**Gợi ý:** phân biệt event time/ingest time, scrape/collector freshness và log loss; alert telemetry lag. SLI application độc lập giúp kiểm chứng traffic còn chạy.

## 34. Runbook khi telemetry hoặc request security signal bất thường

### Giai đoạn A — Xác minh sự kiện và phạm vi

1. Xác định **incident time**, cluster/region, service, namespace, version và route.
2. Ghi triệu chứng: latency/error spike, policy deny, handshake fail, retry storm, missing traces hoặc data leakage.
3. Đọc metrics tại **canonical reporter**, không cộng chéo proxies.
4. Kiểm tra Collector/Prometheus ingestion health để tránh kết luận từ dữ liệu thiếu.
5. Tìm proxy access logs, tracing spans và app logs theo correlation ID.
6. Đối chiếu CNI/cloud flow logs khi nghi bypass hoặc L4 failure.
7. Kiểm tra mesh policy, cert, routing, Telemetry config và rollout gần đây.
8. Đánh giá verified peer identity và quyền thật của end-user, không dùng header tự khai.

### Giai đoạn B — Khoanh vùng

- **mTLS failure:** kiểm tra CA/trust bundle/SDS, cert expiry, peer principal, ALPN/SNI theo service; không chuyển toàn cluster thành plaintext.
- **Authorization deny bất thường:** xác định policy owner, caller, scope, timestamp, app route; giữ denial policy khi nó đúng.
- **Retry storm:** xem per-try timeout, retry budget, upstream health, circuit breakers; không mở retry vô hạn.
- **Metrics/traces missing:** kiểm tra exporter queue, sampling, L7 coverage, receiver auth, backend ingest.
- **Data leakage:** chặn log fields nhạy cảm, hạn chế truy vấn, xử lý retention/credentials/incident theo quy trình.
- **Egress bypass:** kiểm tra direct routes, CNI/SG, gateway logs, source workload và alternate endpoints.

### Giai đoạn C — Khôi phục có kiểm soát

1. Rollback cấu hình Telemetry/mesh gây sự cố nếu có baseline an toàn và approval.
2. Giữ mTLS và AuthorizationPolicy theo yêu cầu, chỉ mở ngoại lệ được phê duyệt, có hạn.
3. Đảm bảo application SLO không bị ảnh hưởng bởi collector overload hoặc tracing changes.
4. Kiểm tra metrics, access logs và traces xuất hiện đúng điểm quan sát.
5. Xác nhận pipeline self-metrics và telemetry freshness.
6. Chạy positive/negative tests cho mTLS, authorization và egress routes trong scope.
7. Đo lại sampling/cardinality, cost, dropped signals.
8. Kiểm tra DR/backup region và policy parity nếu sự cố liên vùng.

### Giai đoạn D — Hậu kiểm

Tài liệu hóa:
- Root cause, thời điểm phát hiện và ảnh hưởng tới end users/security.
- Sai lệch ở source telemetry, sampling hoặc schema.
- Trust boundary hoặc enforcement point bị hiểu sai.
- Quyền/hành động nào có thể làm tắt hoặc làm sai telemetry.
- Tác động PII/credential và cách khắc phục nếu có.
- Test coverage còn thiếu và owner/hạn hoàn thành.
- Các thay đổi dashboard, SLI, runbook và policy-as-code.

**Một dashboard xanh trở lại chưa đủ để đóng incident** nếu access logs/traces vẫn rò dữ liệu, SLO bị tính sai hoặc egress security boundary còn bypass.

## 35. Những sai lầm thường gặp

1. **Coi service mesh tự hiểu mọi business operation.** Proxy không tự biết DB/domain logic.
2. **Coi mọi request có một log.** Nhiều hops tạo nhiều events.
3. **Cộng source và destination request metrics.** Double counting.
4. **Lấy upstream attempts làm user requests.** Retries làm số liệu lệch.
5. **Chỉ xem HTTP 5xx cho gRPC.** grpc-status có thể lỗi dù HTTP 200.
6. **Coi HTTP 200 là transaction thành công.** Domain failure vẫn có thể tồn tại.
7. **Coi 403 đồng nghĩa outage.** Mesh deny đúng có thể là security success.
8. **Coi mTLS verified đồng nghĩa được quyền mọi API.** Còn AuthorizationPolicy/app authZ.
9. **Tin X-Peer-Identity do client gửi.** Không phải verified TLS metadata.
10. **Coi traceparent là credential.** Trace ID chỉ để correlation.
11. **Bỏ qua application propagation.** Traces có thể đứt qua client calls/queues.
12. **Dùng sampled traces để tính error SLO.** Sampling bias gây sai.
13. **Coi bật 100% tracing là không tốn tài nguyên.** Proxy/collector/storage có giới hạn.
14. **Coi không có trace là không có request.** Có sampling/exporter loss.
15. **Đặt user ID, URL đầy đủ hoặc trace ID trong metrics labels.** Cardinality/PII.
16. **Tính trung bình p95 của Pods.** Không tương đương service p95.
17. **Quên đơn vị histogram ms so với seconds.** Dashboard latency sai.
18. **Không tính client cancellations/transport resets.** Error SLI thiếu.
19. **Coi 503 luôn do app trả.** Proxy có thể tạo local reply.
20. **Không xem response_flags/TLS errors.** Bỏ qua lớp network/proxy.
21. **Chỉ instrument ingress rồi khẳng định thấy mọi internal requests.** Thiếu hop telemetry.
22. **Coi ambient L4 có đầy đủ HTTP telemetry.** Waypoint/L7 cần đi đúng path.
23. **Coi TLS passthrough giúp proxy đọc HTTP headers.** Không có plaintext L7 visibility.
24. **Tin egress gateway logs chứng minh không có bypass.** Cần CNI/firewall.
25. **Bỏ qua DNS, IPv6, QUIC và direct cloud endpoints.** Có thể có đường không được đo.
26. **Không đo Collector received/exported/dropped.** Im lặng mất tín hiệu.
27. **Không alert telemetry absence/freshness.** Dashboard rỗng bị hiểu nhầm.
28. **Không kiểm soát log retention và tenant access.** Rò dữ liệu gián tiếp.
29. **Ghi Authorization header vào proxy logs.** Lộ token.
30. **Dùng raw path/query làm span name.** Rò PII và tăng cardinality.
31. **Cho rằng TLS mTLS trên một hop bảo đảm toàn bộ path.** Mỗi boundary có policy riêng.
32. **Không tương quan policy revision với request outcome.** Khó điều tra change regressions.
33. **Không kiểm tra cert rotation và SDS health.** Handshake fail bất ngờ.
34. **Không phân biệt user identity với workload identity.** Audit attribution sai.
35. **Xem application logs thay thế network flow logs.** Lỗi trước app có thể không hiện.
36. **Dựa vào một client IP sau NAT để quy kết user.** Cần workload/time/identity.
37. **Mở cross-tenant trace lookup không authZ.** Trace ID bị biết không là permission.
38. **Bật debug/tracing toàn mesh để sửa lỗi một service.** Gây overhead và data risk.
39. **Không kiểm tra dashboard schema sau upgrade.** Metrics names/labels thay.
40. **Coi health của backend telemetry là health của app.** Hai hệ thống khác nhau.
41. **Không thử security parity khi failover.** Region dự phòng có thể thiếu audit.
42. **Chỉ thực hiện positive tests.** Không biết denied requests có bị chặn đúng.
43. **Đưa log chứa dữ liệu thật vào ticket công khai.** Mất kiểm soát bản sao.
44. **Không ghi uncertainty của sampling/coverage.** Kết luận dựa trên dữ liệu thiếu.
45. **Không có owner cho dashboards/alerts và policy.** Config drift tồn tại lâu.

## 36. Checklist triển khai telemetry cho service mesh

- [ ] Đã có sơ đồ request path: client, gateway, source/destination proxy, app, dependencies.
- [ ] Có inventory mesh enrollment, sidecar/ambient/waypoint và traffic ngoài mesh.
- [ ] Xác định canonical SLI reporter cho user-facing requests.
- [ ] Đã phân biệt user requests và upstream attempts/retries.
- [ ] Có RED metrics (rate/errors/duration) và saturation signals.
- [ ] Có thống nhất metric units, histogram types và label schema theo version.
- [ ] Có PromQL/dashboard được review tránh cộng source/destination.
- [ ] Có gRPC status telemetry và handling của HTTP/2/TCP opaque.
- [ ] Có access log fields tối thiểu, không raw Authorization/cookies/PII.
- [ ] Có traceparent propagation và application instrumentation khi cần.
- [ ] Có phương án cho queue/async spans/links.
- [ ] Có sampling strategy, budgets và alerts dropped spans.
- [ ] Có monitoring về high cardinality, scrape size và telemetry cost.
- [ ] Có mTLS identity được đọc từ verified TLS state.
- [ ] Có alerts cert expiration, SDS/CA health và handshake errors.
- [ ] Có mesh AuthorizationPolicy events/deny visibility theo scope phù hợp.
- [ ] Không dùng request ID/trace ID làm identity hoặc authorization.
- [ ] Phân biệt gateway, mesh và application authz outcomes.
- [ ] Có network flow evidence khi proxy không nhìn thấy packet.
- [ ] Có kiểm soát direct egress bypass và private endpoints.
- [ ] Có CNI/NetworkPolicy/SG và identity controls cho telemetry pipeline.
- [ ] Exporter/Collector/backend giao tiếp TLS và credential scope tối thiểu.
- [ ] Có receiver/processor/exporter health, buffer/queue/drop metrics.
- [ ] Có alert telemetry loss, ingestion lag và missing scrape targets.
- [ ] Có redaction trước export, privacy classification và retention.
- [ ] Quyền tìm kiếm logs/traces theo role/tenant có audit.
- [ ] Có schema version, config owner và rollback cho Telemetry API.
- [ ] Đã test sidecar/ambient/waypoint migration và L7 coverage.
- [ ] Đã test multi-cluster/multi-region tags và trust domain boundaries.
- [ ] Đã thử mTLS success/failure, authorization allow/deny trong lab.
- [ ] Đã thử retry/timeouts/connection reset và proxy-local 503 outcomes.
- [ ] Đã test trace continuity với application HTTP/async calls.
- [ ] Đã test gateway SLI với gRPC and HTTP errors.
- [ ] Đã test log sanitization bằng dữ liệu giả, không dùng credential thật.
- [ ] Có negative tests cho egress bypass và caller trái quyền.
- [ ] Có đảm bảo app không bị Collector/trace exporter overload.
- [ ] Có runbook khi metrics rỗng hoặc trace bị gãy.
- [ ] Có quy trình tăng sampling tạm thời được phê duyệt.
- [ ] Có DR/failover parity cho security telemetry và backend access.
- [ ] Không coi một biểu đồ xanh là bằng chứng đủ cho quyền mạng và dữ liệu.

## 37. Bảng thuật ngữ nhanh

| Thuật ngữ | Giải thích |
|---|---|
| **Telemetry** | Tín hiệu đo/ghi nhận để quan sát hệ thống |
| **RED** | Rate, Errors, Duration |
| **Four Golden Signals** | Latency, Traffic, Errors, Saturation |
| **Metric counter** | Số đo tích lũy, thường dùng rate/increase |
| **Histogram** | Phân phối mẫu theo buckets hoặc native representation |
| **Cardinality** | Số time series do các tổ hợp nhãn tạo ra |
| **Access log** | Event ghi tại proxy/application boundary |
| **Distributed trace** | Tập spans liên quan một transaction |
| **Span** | Một đơn vị xử lý trong trace |
| **Trace ID / Span ID** | Định danh tương quan trace/operation, không phải credential |
| **Trace Context** | Chuẩn truyền context qua HTTP, điển hình W3C traceparent |
| **Baggage** | Thuộc tính truyền qua nhiều hops, cần giới hạn dữ liệu |
| **Head sampling** | Chọn trace khi bắt đầu |
| **Tail sampling** | Chọn trace sau khi xem outcome/spans |
| **Exemplar** | Liên kết quan sát metric với trace/sample metadata |
| **mTLS** | TLS xác thực cả client và server |
| **Peer identity** | Danh tính đối tác kết nối do TLS/mesh xác minh theo cấu hình |
| **SDS / xDS** | Các cơ chế cung cấp secrets/cấu hình tới proxy trong nhiều mesh/Envoy deployments |
| **Sidecar** | Proxy chạy cùng Pod/app theo mô hình phù hợp |
| **Ambient / waypoint** | Datapath L4 và thành phần L7 của kiến trúc mesh phù hợp |
| **Collector** | Thành phần tiếp nhận, xử lý và export telemetry |
| **OTLP** | Giao thức truyền tín hiệu OpenTelemetry |
| **Reporter** | Góc nhìn source/destination của metric trong một số mesh |
| **SLI/SLO** | Chỉ số và mục tiêu về chất lượng dịch vụ |
| **Policy deny** | Quyết định từ chối tại enforcement point, không nhất thiết là app error |
| **Response flags** | Dấu hiệu nguyên nhân transport/proxy theo sản phẩm |
| **Telemetry freshness** | Độ mới dữ liệu so với thời điểm event |

## 38. Tổng kết

**Quan sát request qua telemetry** biến các cuộc gọi service-to-service thành dữ liệu có thể phân tích về **đường đi, độ trễ, lỗi, identity, policy decision và tác động của thay đổi mạng**. Trong service mesh, **metrics** cho thấy xu hướng và SLO, **logs** cung cấp bằng chứng per-hop hoặc quyết định an ninh, còn **distributed traces** liên kết các chặng được instrument/sampled. Cả ba đều có giới hạn về coverage, độ tin cậy, dữ liệu nhạy cảm và chi phí.

Để quan sát đúng trong **SECURITY_NETWORK_SECURITY**, cần tách **HTTP/gRPC/TCP outcomes**, **mTLS peer verification**, **mesh/application authorization**, **proxy-local errors**, **retry amplification**, **sidecar/ambient visibility** và **control-plane events**. Một hệ thống tốt không chỉ có dashboard đẹp mà còn biết **nó nhìn thấy gì, không nhìn thấy gì, dữ liệu có đến đúng thời điểm không, ai được quyền truy vấn và có bằng chứng nào cho luồng bị chặn**.

Điểm mấu chốt khi vận hành là **chọn một canonical SLI boundary, liên kết request bằng trace/log correlation đáng tin, bảo vệ privacy, kiểm soát cardinality/sampling, giám sát sức khỏe pipeline và chạy cả positive lẫn negative tests**. Khi đó, telemetry mới đủ hữu ích để phát hiện và khoanh vùng sự cố, điều tra hành vi mạng đáng ngờ, xác minh mTLS và phục hồi hệ thống mà không hy sinh ranh giới bảo mật.
