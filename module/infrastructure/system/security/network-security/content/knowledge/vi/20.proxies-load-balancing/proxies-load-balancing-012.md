# Log correlation giữa proxy và backend

> **Chương:** Proxy reverse proxy và cân bằng tải  
> **Mô-đun:** SECURITY_NETWORK_SECURITY  
> **Bối cảnh:** Giám sát và bảo vệ lưu lượng xuyên CDN, WAF, reverse proxy, load balancer, API gateway, service mesh, backend và các mạng phân đoạn/on-prem/cloud.  
> **Trọng tâm:** Dùng định danh tương quan, dữ liệu log có cấu trúc, dấu thời gian và ngữ cảnh đáng tin để tái dựng một request từ điểm vào đến dịch vụ cuối; phục vụ phân tích sự cố, phát hiện xâm nhập, SRE và ứng phó bảo mật.

## 1. Log correlation giữa proxy và backend là gì?

Trong một hệ thống web hiện đại, request của người dùng hiếm khi đi thẳng từ trình duyệt tới ứng dụng. Nó có thể đi qua **CDN → WAF → reverse proxy → load balancer → API gateway → service A → service B**. Mỗi lớp có thể ghi một bản log riêng với địa chỉ IP, mã trạng thái, thời gian xử lý và định danh khác nhau.

**Log correlation** là quá trình **liên kết các bản ghi thuộc cùng một yêu cầu, giao dịch hoặc chuỗi xử lý** để trả lời:

- Request bắt đầu ở đâu, đi qua những thành phần nào, tới backend nào?
- Lớp nào quyết định **ALLOW, BLOCK, CHALLENGE hoặc RATE LIMIT**?
- Vì sao client thấy **403, 429, 499, 502 hoặc 504**, trong khi backend ghi kết quả khác?
- Request có bị **retry**, chuyển backend, fan-out sang nhiều service, hoặc rơi vào queue không?
- Tổng độ trễ đến từ client, proxy, kết nối upstream, ứng dụng hay dependency?
- Có dấu hiệu giả mạo header, bypass WAF, truy cập ngoài quyền hoặc request đáng ngờ không?

Để tương quan đáng tin, cần kết hợp **request ID, trace ID/span ID, hop/attempt ID, route, timestamp, trusted client identity, upstream và policy decision**. Không nên chỉ so sánh thời điểm hoặc địa chỉ IP: NAT, proxy, HTTP/2 multiplexing và concurrent requests khiến nhiều request có thể trông giống nhau.

**Ví dụ ngắn:** người dùng nhận HTTP 504; Nginx báo upstream timeout; ứng dụng lại ghi HTTP 200 sau đó. Hai log **không nhất thiết mâu thuẫn**: proxy đã hết thời gian chờ và trả 504 trước khi backend hoàn tất. Chỉ khi ghép **cùng request ID + upstream attempt + timeline** mới diễn giải đúng.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **request ID**, **correlation ID**, **trace ID**, **span ID**, **WAF event/rule ID** và **session/user ID**.
2. Thiết kế sơ đồ truyền ID qua **trusted ingress, CDN/WAF, reverse proxy, load balancer và backend**.
3. Xây dựng log JSON có schema ổn định, tránh lộ token, cookie và nội dung nhạy cảm.
4. Phân tích **X-Forwarded-For, Forwarded, X-Request-ID, traceparent, tracestate** trong ranh giới tin cậy.
5. Tương quan **status code, retries, upstream attempts, fan-out, bất đồng bộ, WebSocket/gRPC và lỗi kết nối**.
6. Dùng công cụ và truy vấn log/SIEM có phép để điều tra latency, lỗi 5xx và sự cố bảo mật.
7. Thiết kế observability, kiểm thử, kiểm soát truy cập log và runbook khắc phục/ứng phó.

## 2. Kiến trúc dữ liệu: request đi qua những lớp nào?

Ví dụ một nền tảng API có nhiều lớp bảo vệ mạng:

~~~mermaid
flowchart LR
    U[Browser / Mobile Client] --> C[CDN / Edge TLS]
    C --> W[WAF]
    W --> P[Reverse Proxy / Ingress]
    P --> L[Load Balancer / API Gateway]
    L --> A[Orders Service]
    A --> B[Inventory Service]
    A --> Q[Message Broker]
    C -. Edge log .-> S[Central Logs / SIEM]
    W -. WAF events .-> S
    P -. Access / Error log .-> S
    L -. Routing / Upstream log .-> S
    A -. App log / Trace .-> S
    B -. App log / Trace .-> S
    Q -. Async events .-> S
~~~

Mỗi hop có **một vùng trách nhiệm riêng**:

| Lớp | Quan sát chủ yếu | Câu hỏi |
|---|---|---|
| **CDN/Edge** | Host, protocol, edge request ID, TLS, cache, edge status | Request có đến edge? Cache hit/miss? |
| **WAF** | WAF event ID, matched rules, action, policy version | Có bị block/challenge/rate limit? |
| **Reverse proxy** | Request ID, route, response status, total time, upstream | Proxy nào xử lý? Có kết nối backend không? |
| **Load balancer/API gateway** | Chọn pool/target, attempts, retry/timeout, per-route policy | Request vào instance nào và lần thử nào? |
| **Backend** | Request ID, trace/span, ứng dụng, DB/dependency, app status | Ứng dụng làm gì, lỗi ở đâu? |
| **Service mesh** | mTLS peer identity, upstream/downstream spans, retry policy | Service nào gọi service nào và có đúng quyền? |
| **Queue/worker** | Message ID, causation ID, attempt, job state | Xử lý có chuyển sang bất đồng bộ không? |
| **SIEM/APM** | Chuỗi sự kiện đã chuẩn hóa, truy vấn và cảnh báo | Bức tranh end-to-end có nhất quán không? |

**Log correlation không tự chứng minh mọi hop đã được bảo vệ.** Phải xác minh TLS/mTLS từng đoạn, phân đoạn VLAN/VRF, firewall/WAF và chính sách truy cập. Một request có cùng ID trên hai hệ thống vẫn có thể đi qua một đường không an toàn.

## 3. Request ID, correlation ID, trace ID và các ID khác

| ID | Mục đích | Phạm vi thường dùng | Điều không nên nhầm |
|---|---|---|---|
| **Request ID** | Nhận diện một HTTP request trong phạm vi được thiết kế | Một request qua nhiều proxy/backend | Không phải user ID hoặc chứng cứ quyền truy cập |
| **Correlation ID** | Liên kết các sự kiện thuộc một giao dịch/nghiệp vụ | Có thể bao trùm nhiều request, job, retry | Không có một format bắt buộc toàn ngành |
| **Trace ID** | Nhận diện một distributed trace | Nhiều span của cùng trace | Không đồng nghĩa một HTTP request duy nhất |
| **Span ID** | Nhận diện một bước/công việc trong trace | Một RPC/HTTP hop/DB operation | Thường thay đổi giữa các service/hop |
| **Parent span ID** | Chỉ quan hệ cha–con giữa các span | Trace tree | Không phải parent request ID của queue |
| **Edge/CDN request ID** | Nhận diện request trong hệ thống CDN | Tùy provider/region | Có thể khác request ID của proxy |
| **WAF event ID** | Nhận diện một event quyết định/phát hiện của WAF | Một hoặc nhiều rule evaluation | Không phải trace ID hoặc request ID |
| **WAF rule ID** | Chỉ rule/policy được match | Nhiều request cùng rule | Không được dùng làm khóa duy nhất của request |
| **Upstream attempt ID** | Phân biệt lần thử đến backend khi có retry | Một lần kết nối/forwarding cụ thể | Một request có thể có nhiều attempts |
| **Message/job ID** | Nhận diện bản tin hoặc công việc async | Queue/worker | Không chắc trùng với incoming request ID |
| **Session/user/device ID** | Liên kết actor đã xác thực | Nhiều request từ cùng actor | Có thể là dữ liệu cá nhân; không tạo quyền chỉ vì có ID |

**Không áp đặt một ID cho mọi khái niệm.** Một khách hàng có thể thực hiện ba request HTTP trong một thao tác checkout; mỗi request có request ID riêng, còn **correlation/transaction ID** có thể liên kết cả ba. Trong một request checkout, service có thể tạo hàng chục **span ID** cùng **trace ID**.

### 3.1. Sơ đồ quan hệ ID

~~~mermaid
flowchart TD
    T[Correlation ID: checkout-42] --> R1[HTTP Request ID: req-a]
    T --> R2[HTTP Request ID: req-b]
    R1 --> X[Trace ID: trace-1]
    X --> S1[Span: edge]
    X --> S2[Span: orders]
    X --> S3[Span: inventory]
    R1 --> U1[Upstream attempt 1]
    R1 --> U2[Upstream attempt 2]
    R2 --> M[Async message ID: message-9]
~~~

Đây là cách mô hình hóa để học. Tùy hệ thống, một HTTP request có thể **không có trace** do sampling hoặc service chưa được instrument. Có thể tái dựng bằng logs và request ID ngay cả khi trace không tồn tại.

## 4. Những thuộc tính cần có để tương quan đúng

Một record log tối thiểu nên có:

- **Thời điểm có timezone:** event timestamp chuẩn hóa, không chỉ tên giờ địa phương.
- **Service và environment:** edge, WAF, gateway, app, instance, cluster, region.
- **Request ID/correlation ID** theo chính sách và **trace_id/span_id** nếu có.
- **HTTP method, host, route template** hoặc endpoint định danh theo cách an toàn.
- **HTTP status** do chính lớp đó trả và **upstream status** nếu lớp đó đã gọi upstream.
- **Latency** có định nghĩa rõ: total proxy time, upstream response time, application processing time.
- **Upstream target/attempt count**, retry reason hoặc cache status khi có.
- **Action/decision source:** WAF BLOCK, proxy TIMEOUT, app 403, rate limit 429, v.v.
- **Trusted identity/client context** khi có thể xác minh; không tin header do client tự khai.

### 4.1. Mẫu schema JSON thống nhất

~~~json
{
  "event_time": "2026-11-28T08:20:14.238Z",
  "event_type": "http_request_completed",
  "environment": "production",
  "layer": "reverse_proxy",
  "service": "api-ingress",
  "instance": "ingress-2",
  "region": "region-a",
  "request_id": "e7a4dd1c5b3b4a3d8e9e7cc142aa0b57",
  "correlation_id": "checkout-opaque-42",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "method": "POST",
  "host": "api.example.com",
  "route": "/v1/orders",
  "status": 504,
  "status_source": "proxy_timeout",
  "upstream_cluster": "orders-v1",
  "upstream_target": "orders-2",
  "upstream_status": null,
  "attempt_count": 1,
  "duration_ms": 30002,
  "upstream_duration_ms": 30000,
  "client_ip": "192.0.2.44",
  "client_ip_source": "trusted_edge",
  "decision": "GATEWAY_TIMEOUT",
  "policy_version": "ingress-v17"
}
~~~

Địa chỉ IP, định danh và timestamp trong ví dụ đều **giả định phục vụ học tập**. Tên trường là schema tham chiếu, **không phải output mặc định của Nginx, Envoy hay OpenTelemetry**.

**Tách null khỏi 0.** Nếu upstream không được gọi, **upstream_duration_ms: null** có nghĩa hơn là 0. Nếu request được phục vụ từ cache, status 200 không đồng nghĩa backend có một bản log 200 tương ứng.

## 5. Phân biệt ID từ client và ID tại điểm vào tin cậy

Một client bên ngoài có thể tự gửi:

~~~http
GET /v1/orders HTTP/1.1
Host: api.example.com
X-Request-ID: admin-request-123
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
X-Forwarded-For: 10.0.0.1
~~~

Không có gì ngăn client **tự đặt tên X-Request-ID, traceparent hoặc X-Forwarded-For**. Vì vậy:

1. **Không dùng các header này để xác thực, gán quyền, miễn rate limit hoặc quyết định nguồn đáng tin.**
2. Tại **trusted ingress**, tạo ID riêng hoặc kiểm tra/chuẩn hóa ID theo chính sách đã duyệt. Với nguồn Internet không tin cậy, cách đơn giản là **ghi đè X-Request-ID bằng giá trị mới**.
3. Chặn ID quá dài, ký tự điều khiển, newline, chuỗi chứa markup hoặc định dạng không hợp lệ để tránh **log injection**, tăng cardinality hoặc gây lỗi parser.
4. Chỉ cho backend nhận traffic từ **proxy/gateway được phép**; không để backend public bypass ingress khiến header tự khai được tin là của proxy.
5. Các proxy tiếp theo phải **giữ nguyên request ID của trusted ingress** nếu mô hình correlation yêu cầu, không tạo lại vô cớ ở mỗi hop.

### 5.1. Tại sao cần ID đủ khó đoán?

Một chuỗi ID ngắn hoặc tuần tự có thể bị đoán và tạo trùng, đặc biệt khi nhiều edge sinh ID song song. Nên dùng **UUID ngẫu nhiên được sinh đúng cách** hoặc một định dạng định danh có **độ duy nhất đủ mạnh**, có kiểm soát độ dài và không nhúng password, số tài khoản hay dữ liệu cá nhân.

ID **không phải secret**, nhưng cũng **không được coi là bằng chứng người gọi được phép tra cứu log**. API hỗ trợ tìm log theo request ID phải xác thực và giới hạn dữ liệu trả về theo tenant/role.

### 5.2. Giữ cả ID cục bộ và ID bên ngoài khi có nhiều CDN

Một số CDN tạo request ID riêng không theo định dạng của ứng dụng. Có thể duy trì:

~~~text
edge_request_id      = id do CDN sinh
request_id           = id do trusted ingress sinh và forward
trace_id             = id của distributed trace (nếu có)
upstream_attempt_id  = id cho từng lần proxy retry
~~~

Nếu có **mapping edge_request_id ↔ request_id** trong log tại điểm nối, người vận hành có thể bắt đầu từ ticket CDN và truy đến application backend. Không yêu cầu mọi nhà cung cấp dùng chung một header do khách hàng tự gửi.

## 6. Ranh giới tin cậy: X-Forwarded-For và Forwarded

Khi traffic qua nhiều proxy, IP nguồn socket mà backend nhìn thấy thường là **IP của proxy gần nhất**, không phải client gốc. Các header như **X-Forwarded-For (XFF)** hoặc **Forwarded** theo RFC 7239 hỗ trợ truyền thông tin về hop trước.

~~~text
Client 192.0.2.44
  -> CDN 198.51.100.10
  -> Ingress 198.51.100.20
  -> Backend 10.20.30.8

Socket peer ở Backend: Ingress 198.51.100.20
Các giá trị forwarded có thể mô tả chuỗi client/CDN/Ingress,
nhưng chỉ đáng tin theo chính sách danh sách proxy được xác thực.
~~~

**Sai lầm nghiêm trọng:** backend lấy địa chỉ đầu tiên của một chuỗi **X-Forwarded-For** rồi xem đó là client thật, trong khi một client Internet có thể tự điền giá trị đầu tiên.

### 6.1. Cách xác minh nguồn

- Định nghĩa **những proxy/CDN nào được phép nối đến ingress/backend** qua network ACL, mTLS, security group hoặc cơ chế tương ứng.
- Tại **trusted edge**, bỏ qua/ghi đè những header forwarded không đáng tin hoặc xử lý dựa trên hợp đồng proxy tin cậy.
- Ở các hop downstream, sử dụng **danh sách trusted proxies + địa chỉ socket peer**, xử lý chuỗi theo cấu hình nền tảng; không cắt chuỗi bằng quy tắc đơn giản “lấy IP bên trái” trong mọi tình huống.
- Ghi **client_ip_source** và **trusted_hops** nếu đủ bằng chứng, nhưng tránh sao chép dữ liệu XFF nguyên bản chưa xác minh sang trường nhận diện actor.
- Chú ý **IPv6, IPv4-mapped addresses, port, NAT, proxy protocol** và cấu hình của load balancer.

**Không tin X-Forwarded-Proto từ Internet** để quyết định request đã qua HTTPS hoặc chọn redirect. Proxy được phép phải thiết lập header này theo kết nối thực tế; nếu không, client có thể đánh lừa scheme detection hoặc policy.

### 6.2. IP không phải user ID

NAT/CGNAT, reverse proxy, VPN, CDN và IP tái cấp khiến cùng một IP đại diện cho nhiều user. Muốn quy trách nhiệm trong SIEM, cần **session identity đã xác thực, device identity, request ID, timestamp, user/tenant scope và nguồn dữ liệu đáng tin**. Đừng chỉ nhóm log theo IP.

## 7. Thiết kế vòng đời request ID qua các hop

Một mô hình thực tế:

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant E as Trusted Edge
    participant W as WAF
    participant P as Reverse Proxy
    participant A as Orders Backend
    C->>E: HTTP request (header có thể tự khai)
    E->>E: Generate/validate request_id = R
    E->>W: Forward R với context đã chuẩn hóa
    W->>W: Log WAF event_id + R
    W->>P: ALLOW + R
    P->>A: X-Request-ID: R
    A->>A: Bind R vào log context, trace nếu có
    A-->>P: HTTP response + R (optional)
    P-->>E: Status + R
    E-->>C: Status + opaque R (optional)
~~~

### 7.1. Quy tắc nhất quán

1. **Sinh ID ở sớm nhất có thể trong trusted ingress**, trước WAF/rate limit nếu kiến trúc cho phép, để log được cả request bị chặn.
2. **Ghi log mapping** khi ID của CDN và ID của hệ thống backend không giống nhau.
3. **Truyền ID đến service** qua HTTP header được kiểm soát và cho vào structured logger.
4. **Giữ ID trên đường trả kết quả** khi hữu ích cho hỗ trợ khách hàng; không dùng ID như token truy cập log.
5. Với **fan-out và retries**, giữ request ID gốc làm khóa nhóm nhưng tạo **span/attempt ID riêng** cho mỗi bước.
6. Với **async job**, giữ liên kết bằng causation/correlation ID và message/job ID, không tự giả định một trace kéo dài vô hạn.

### 7.2. Có cần tất cả proxy dùng cùng ID không?

Không bắt buộc mọi nền tảng hỗ trợ một request ID duy nhất. Hệ thống vẫn có thể tương quan qua **mapping liên kết**:

~~~json
{
  "event_time": "2026-11-28T08:20:12.008Z",
  "layer": "edge",
  "edge_request_id": "edge-req-8ab9",
  "request_id": "e7a4dd1c5b3b4a3d8e9e7cc142aa0b57",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "action": "FORWARD",
  "upstream_service": "waf"
}
~~~

Khuyến nghị nhất quán về **tên trường**, chuẩn encoding và chính sách sinh ID, hơn là buộc mọi log chỉ có một khóa duy nhất.

## 8. W3C Trace Context: traceparent và tracestate

**W3C Trace Context** quy định cách truyền ngữ cảnh distributed tracing qua HTTP, phổ biến là:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Trong format phiên bản 00:

| Thành phần | Ví dụ | Ý nghĩa |
|---|---|---|
| **version** | 00 | Phiên bản định dạng |
| **trace-id** | 4bf92f3577b34da6a3ce929d0e0e4736 | 16 byte ở dạng 32 ký tự hex, khác toàn số 0 |
| **parent-id** | 00f067aa0ba902b7 | 8 byte ở dạng 16 ký tự hex, khác toàn số 0 |
| **trace-flags** | 01 | Các bit cờ, trong đó có sampled theo đặc tả |

**Trace ID** thường được giữ xuyên nhiều service, còn **span ID thay đổi theo từng span**. Khi service B nhận traceparent, nó có thể tạo **span mới** với parent tham chiếu span từ service A; không ghi đè mọi span bằng cùng một span ID.

### 8.1. tracestate và baggage

- **tracestate** mang thông tin trạng thái trace theo nhà cung cấp/triển khai; cần kiểm soát kích thước, số lượng và độ tin cậy.
- **baggage** (khi sử dụng) truyền metadata có ngữ cảnh qua service boundaries; rất dễ trở thành kênh lộ **PII, tokens hoặc dữ liệu tenant** nếu không có allowlist.
- Không chấp nhận **traceparent** như chứng minh client đã được xác thực. Một client ngoài Internet có thể tạo chuỗi trace hợp cú pháp.

### 8.2. Xử lý trace context ở trust boundary

Tùy threat model, trusted ingress có thể **bắt đầu trace mới** hoặc tiếp tục trace đã nhận sau kiểm tra định dạng và policy. Cần tránh:

- Header quá dài hoặc sai cú pháp gây overhead/log injection.
- Dùng metadata tracing do client gửi để bật chế độ debug nhạy cảm.
- Trộn trace từ nhiều tenant vào cùng một chuỗi hiển thị không giới hạn quyền.
- Ghi raw baggage/tracestate mà không kiểm soát secret/PII.

**Tracing và logging bổ sung cho nhau.** Tracing có sampling; request quan trọng cho điều tra WAF hoặc sự cố bảo mật vẫn cần log metadata tối thiểu có retention phù hợp ngay cả khi trace chưa được thu thập.

## 9. OpenTelemetry: kết hợp logs, traces, metrics

OpenTelemetry hỗ trợ telemetry theo ba dạng phổ biến:

| Tín hiệu | Phù hợp để trả lời | Định danh trọng tâm |
|---|---|---|
| **Logs** | Sự kiện, lỗi, quyết định policy, trạng thái cụ thể | event time, service, request ID, trace/span khi có |
| **Traces** | Quan hệ nhân quả và độ trễ giữa các bước | trace ID, span ID, parent span |
| **Metrics** | Số lượng, tỷ lệ lỗi, p95/p99 latency theo thời gian | label có cardinality được kiểm soát |

Một log ứng dụng có thể chứa:

~~~json
{
  "timestamp": "2026-11-28T08:20:13.411Z",
  "severity": "ERROR",
  "service.name": "orders-api",
  "service.instance.id": "orders-2",
  "deployment.environment": "production",
  "request_id": "e7a4dd1c5b3b4a3d8e9e7cc142aa0b57",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "5b8aa5a3a711a631",
  "event_name": "inventory_dependency_timeout",
  "dependency": "inventory",
  "timeout_ms": 28000
}
~~~

Các trường tên dấu chấm ở đây minh họa cách gắn resource/attributes; **không cam kết đúng tên mọi semantic convention của mỗi phiên bản SDK**. Khi triển khai, dùng convention phù hợp phiên bản OpenTelemetry/collector/agent đang chạy và chuẩn hóa dữ liệu đầu vào của các nguồn không tương thích.

### 9.1. Vì sao không đưa request ID vào metric label?

Mỗi request ID gần như duy nhất. Nếu đặt **request_id, trace_id, raw URL, IP client hay user ID** làm label metrics, số chuỗi thời gian có thể tăng cực lớn (**high cardinality**), gây tốn bộ nhớ/chi phí và mất ổn định backend giám sát.

Metrics nên dùng **route template, service, region, response class, upstream cluster, policy action**, còn ID chi tiết được tìm trong logs/traces.

## 10. Log JSON có cấu trúc tốt hơn log văn bản ghép tay

Một dòng log dạng:

~~~text
2026-11-28 15:20 error user request failed from 10.0.0.1 504
~~~

khó phân biệt **thời gian theo timezone, IP thật, status nguồn nào, request ID** và nguyên nhân. JSON tạo điều kiện chuẩn hóa và truy vấn:

~~~json
{
  "event_time": "2026-11-28T08:20:14.238Z",
  "layer": "proxy",
  "service": "ingress",
  "request_id": "e7a4dd1c5b3b4a3d8e9e7cc142aa0b57",
  "method": "GET",
  "route": "/v1/items/{id}",
  "http_status": 502,
  "upstream_status": 502,
  "status_source": "upstream_connection_failure",
  "upstream_target": "items-3",
  "duration_ms": 18
}
~~~

### 10.1. Quy ước schema

- **Tên field nhất quán**: chọn request_id thay vì nơi thì reqId, nơi thì rid mà không mapping.
- **Kiểu dữ liệu rõ**: status, attempts và duration là number; missing là null/absent.
- **Một trường một nghĩa**: http_status là status lớp ghi log đã trả; upstream_status là kết quả từ upstream nếu có.
- **Timestamp có timezone**: chuẩn hóa UTC ở pipeline; giữ source timestamp và ingest timestamp khi cần.
- **Route thay vì URL thô**: không mặc định ghi query string chứa token, email, ID nhạy cảm.
- **Action source rõ**: blocked_by_waf, rate_limited_by_gateway, denied_by_app không gộp thành “403”.
- **Version schema** để nâng cấp không phá pipeline.

### 10.2. Ví dụ schema versioning

~~~json
{
  "schema_version": "1.0",
  "event_time": "2026-11-28T08:20:14.238Z",
  "ingest_time": "2026-11-28T08:20:14.605Z",
  "service": "ingress",
  "request_id": "e7a4dd1c5b3b4a3d8e9e7cc142aa0b57",
  "route": "/v1/orders",
  "http_status": 504,
  "upstream_status": null,
  "status_source": "gateway_timeout",
  "duration_ms": 30002
}
~~~

**Tách event_time và ingest_time:** pipeline có thể đến chậm, retry hoặc bị tắc. Thứ tự theo ingest_time không phải thứ tự request xảy ra trên mạng.

## 11. Nginx: tạo request ID và ghi access log JSON

Một reverse proxy Nginx có thể sinh **$request_id**, dùng nó trong access log và chuyển tiếp vào header **X-Request-ID** cho backend. Ví dụ:

~~~nginx
# PSEUDOCONFIG để học: cần đặt đúng context http/server/location
# và hoàn thiện TLS, upstream, timeout, real IP, security controls.

http {
    log_format correlation escape=json
      '{"time":"$time_iso8601",'
      '"layer":"reverse_proxy",'
      '"request_id":"$request_id",'
      '"method":"$request_method",'
      '"host":"$host",'
      '"path":"$uri",'
      '"status":$status,'
      '"request_time_s":"$request_time",'
      '"upstream_addr":"$upstream_addr",'
      '"upstream_status":"$upstream_status",'
      '"upstream_response_time_s":"$upstream_response_time"}';

    upstream orders_pool {
        server 10.20.30.11:8080;
        server 10.20.30.12:8080;
    }

    server {
        listen 443 ssl;
        server_name api.example.com;
        # ssl_certificate /...; ssl_certificate_key /...;
        access_log /var/log/nginx/requests.json correlation;

        location /v1/orders {
            proxy_set_header X-Request-ID $request_id;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_pass http://orders_pool;
            add_header X-Request-ID $request_id always;
        }
    }
}
~~~

**Giới hạn và lưu ý bắt buộc:**

1. Đây là **ví dụ rút gọn, không phải cấu hình production hoàn chỉnh**; thiếu nhiều thông số TLS, upstream health, proxy headers, server defaults và log security.
2. **$request_id** được sinh tại Nginx đang xử lý request. Nếu trước Nginx đã có **trusted ingress request ID** thì ghi đè ở hop này **sẽ cắt chuỗi correlation**. Chỉ tạo tại nơi đã xác định làm **điểm sinh ID**; ở hop sau phải bảo tồn ID đáng tin.
3. **$uri** là path hiện tại theo trạng thái xử lý Nginx và có thể bị rewrite; nó không phải route template lý tưởng. Cần chuẩn hóa để tránh cardinality cao hoặc path chứa dữ liệu cá nhân.
4. **$upstream_status, $upstream_addr và $upstream_response_time** có thể là **danh sách nhiều giá trị** khi retry hoặc đi nhiều nhóm upstream; không ép thành số nguyên đơn.
5. Ví dụ log các field upstream dạng **string** vì trong Nginx có thể là chuỗi rỗng, dấu nối hoặc giá trị phức hợp. Pipeline phải parse theo kiểu dữ liệu phù hợp.
6. **Không ghi trực tiếp $request_uri, Cookie, Authorization hoặc query string** vào log sản xuất nếu chưa có đánh giá/redaction dữ liệu.
7. Cần **allowlist truy cập backend và chuẩn hóa forwarded headers** ở đúng trust boundary. Cấu hình này không tự bảo đảm không có direct-to-origin bypass.

### 11.1. Nginx phía sau một ingress đã tin cậy

Khi ID đến từ một proxy trước đó, không dùng lại tùy tiện **$http_x_request_id** nếu client Internet có thể chạm thẳng Nginx. Thiết kế cần:

- Chỉ chấp nhận kết nối từ **trusted ingress** được firewall/mTLS bảo vệ.
- Tin header ID **chỉ từ nguồn được xác minh**.
- Kiểm tra ID có một giá trị, format và chiều dài hợp lệ.
- Nếu không có ID hợp lệ, sinh ID mới và log **correlation_discontinuity** khi cần.
- Ghi mapping tới edge ID riêng nếu platform trước dùng ID khác.

Trên Nginx, việc triển khai logic chọn ID có thể dùng **map**, gateway scripting hoặc bộ phận ở upstream; **đừng chỉ viết map tin mọi X-Request-ID** mà không kiểm tra đường vào.

## 12. Backend Java/Spring Boot: đưa request ID vào MDC

Trong ứng dụng Java, có thể dùng **Mapped Diagnostic Context (MDC)** để gắn request ID vào log của request thread. Ví dụ Spring Boot sử dụng **OncePerRequestFilter**:

~~~java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.Enumeration;
import java.util.UUID;
import java.util.regex.Pattern;

@Component
public final class RequestCorrelationFilter extends OncePerRequestFilter {
    private static final Pattern VALID_ID =
        Pattern.compile("[A-Za-z0-9_-]{16,64}");

    @Override
    protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain chain
    ) throws ServletException, IOException {
        // Chỉ tin X-Request-ID nếu backend CHỈ nhận request
        // từ trusted ingress có nhiệm vụ ghi đè/kiểm tra header.
        Enumeration<String> values = request.getHeaders("X-Request-ID");
        String candidate = null;
        if (values != null && values.hasMoreElements()) {
            String first = values.nextElement();
            if (!values.hasMoreElements()
                    && VALID_ID.matcher(first).matches()) {
                candidate = first;
            }
        }

        String requestId = (candidate != null)
            ? candidate
            : UUID.randomUUID().toString();

        MDC.put("request_id", requestId);
        response.setHeader("X-Request-ID", requestId);
        try {
            chain.doFilter(request, response);
        } finally {
            MDC.remove("request_id");
        }
    }
}
~~~

**Đây là ví dụ minh họa**, cần điều chỉnh theo framework/version và pipeline logging thực tế. Cấu hình log app phải in trường **MDC request_id** dưới dạng JSON, ví dụ với encoder/layout có hỗ trợ. Không giả định chỉ có filter là log JSON sẽ tự xuất.

### 12.1. Cảnh báo security cho filter

- Nếu backend public hoặc có đường bypass proxy, **X-Request-ID vẫn là dữ liệu khách tự khai**. Không dùng ID đó để xác thực hoặc truy cập dữ liệu của request khác.
- **UUID.randomUUID()** tạo ID dự phòng và có thể làm **mất liên kết** với log edge nếu upstream không truyền được; theo dõi số lần thiếu ID để sửa data path.
- MDC truyền theo thread trong nhiều implementation; **CompletableFuture, executor, Reactor/WebFlux và async callbacks** có thể chạy thread khác. Cần cơ chế **context propagation** tương ứng, không tin ThreadLocal tự được sao chép.
- Tránh rò MDC giữa các request nếu thread được tái sử dụng: luôn **remove/restore trong finally**.
- Không thêm request ID vào bất kỳ trường database/authorization nào như "proof" cho actor.

### 12.2. Log cấu trúc từ ứng dụng

~~~json
{
  "event_time": "2026-11-28T08:20:14.300Z",
  "layer": "backend",
  "service": "orders",
  "instance": "orders-2",
  "request_id": "e7a4dd1c5b3b4a3d8e9e7cc142aa0b57",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "5b8aa5a3a711a631",
  "route": "/v1/orders",
  "application_status": "dependency_timeout",
  "processing_duration_ms": 28000
}
~~~

## 13. Envoy, HAProxy, API gateway và service mesh

Mỗi proxy có cơ chế riêng cho **request identifier, dynamic metadata, access log format, retries và tracing**. Khi hệ thống gồm Envoy ở ingress, HAProxy ở load balancer và một gateway API khác, không mặc định tất cả dùng cùng tên/giá trị ID.

| Nền tảng | Khả năng cần xác minh | Nguy cơ vận hành |
|---|---|---|
| **Nginx** | $request_id, access/error logs, proxy headers, upstream timing | Retry tạo nhiều upstream statuses; ID không được giữ giữa nhiều ingress |
| **Envoy** | x-request-id, tracing headers, response flags, access log/stream info | X-request-id có semantics riêng theo cấu hình; route retry và upstream reset |
| **HAProxy** | unique ID, log format, timers, termination state và selected backend | Log termination code và retry cần parse đúng version |
| **API gateway** | Gateway request ID, auth/rate-limit decision, upstream metadata | 401/403/429 có thể được tạo ngay tại gateway, không có backend log |
| **Service mesh proxy** | mTLS peer identities, spans, retries, destination service | Trace ID hiện diện không chứng minh request được authorized |
| **Cloud load balancer** | Provider request ID, target status, latency, trace integration | Format/fields phụ thuộc dịch vụ và kiểu LB |

**Khi ghi tài liệu triển khai:** chỉ rõ vendor/version, điểm TLS termination, luồng local/central, field log thật, phạm vi retry và giá trị mặc định. **Không lấy ví dụ tên header từ một vendor áp cho mọi thiết bị**.

### 13.1. Một request nhiều proxy: ai sinh ID?

Nên chọn **một điểm vào có thẩm quyền** với cơ chế sinh ID và một chính sách bảo tồn, hoặc lưu mapping ID giữa các lớp. Ví dụ CDN có **edge_id**, Envoy tạo **x-request-id** riêng, Spring ghi **request_id**: để tương quan được cần ít nhất log mapping **edge_id ↔ x-request-id ↔ app request_id** tại các điểm tiếp giáp.

## 14. Load balancing và retries: một request có nhiều lần thử

Khi backend bị timeout hoặc connection reset, load balancer có thể thử lại ở instance khác nếu chính sách cho phép. Điều đó khiến:

- **Một client request ID** có thể gắn với **nhiều upstream attempts**.
- Proxy có thể ghi các trạng thái và thời gian upstream theo **chuỗi**, không phải một số duy nhất.
- Backend A có thể đã nhận một phần hoặc toàn bộ request, trong khi proxy retry sang backend B.
- Client có thể thấy **một status cuối** khác status/lỗi ở attempt trước.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant G as Load Balancer
    participant A as Backend A
    participant B as Backend B
    C->>G: Request R
    G->>A: Attempt 1 / R
    A--xG: Connection reset / no valid response
    G->>B: Attempt 2 / R
    B-->>G: 200 OK
    G-->>C: 200 OK / R
    Note over G: Một client request, hai upstream attempts
~~~

### 14.1. Log attempt riêng

~~~json
{
  "event_time": "2026-11-28T08:20:14.000Z",
  "layer": "load_balancer",
  "request_id": "e7a4dd1c5b3b4a3d8e9e7cc142aa0b57",
  "attempts": [
    {
      "attempt": 1,
      "target": "orders-1",
      "result": "connection_reset",
      "duration_ms": 120
    },
    {
      "attempt": 2,
      "target": "orders-2",
      "result": "http_200",
      "duration_ms": 80
    }
  ],
  "final_http_status": 200,
  "total_duration_ms": 206
}
~~~

Các số và dữ kiện chỉ minh họa. Nếu hệ thống không hỗ trợ một object log attempts, có thể sinh **event riêng theo attempt** và liên kết bằng request_id + attempt_index.

### 14.2. Retry có thể gây side effect

Một **POST tạo đơn hàng** có thể đã được backend A xử lý thành công nhưng proxy chưa kịp nhận response. Retry sang B có thể tạo **đơn hàng trùng** nếu ứng dụng không có **idempotency key/transaction semantics** phù hợp.

**Request ID không mặc định là idempotency key.** Chúng có mục đích khác nhau; idempotency phải được thiết kế theo API/đơn hàng và scope của operation. Không bật retry không kiểm soát cho các thao tác có side effect chỉ để giảm lỗi 502.

### 14.3. Route, retry và status phải được đọc cùng nhau

Một bản ghi proxy chứa **upstream_status: "502, 200"** có thể có hai attempts. Không kết luận client đã nhận 502 vì backend đầu tiên lỗi; phải xem **final_http_status**. Ngược lại, một client cuối cùng thấy 502 không nhất thiết mọi attempt đều trả 502.

## 15. Fan-out: một request gọi nhiều service

Một API tổng hợp có thể gọi **inventory**, **pricing** và **recommendation** song song. Mỗi service có span và trạng thái riêng nhưng thường cùng trace ID.

~~~mermaid
flowchart TD
    R[Request ID R / Trace ID T] --> O[Orders API]
    O -->|Span A| I[Inventory]
    O -->|Span B| P[Pricing]
    O -->|Span C| S[Shipping]
    I --> D[Database]
    P --> C[Cache]
    S --> E[Carrier API]
~~~

**Nếu chỉ có request ID**, có thể nhóm toàn bộ log nhưng khó xác định **nhánh nào chậm hoặc nhánh nào là nguyên nhân**. Distributed tracing bổ sung **span/parent-child relationship** và thời lượng mỗi dependency.

### 15.1. Không nhầm causal chain với thứ tự thời gian

Hai dependency có thể chạy song song. Một bản log xuất hiện trước không phải lúc nào cũng là nguyên nhân của bản log sau, nhất là khi clock lệch và logs gửi qua pipeline khác nhau. Dùng **span links, parent span, message causation ID và event semantics** để xác định quan hệ nhân quả.

## 16. Asynchronous processing: queue và job không còn cùng một HTTP request

Một API có thể trả **202 Accepted** ngay rồi đưa công việc vào queue. Worker xử lý sau hàng giây hoặc hàng phút, khi HTTP connection đã kết thúc.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as API
    participant Q as Queue
    participant W as Worker
    C->>A: POST /exports [request_id=R]
    A->>Q: Publish job J, causation_id=R
    A-->>C: 202 Accepted [job_id=J]
    Q->>W: Deliver job J
    W->>W: Process, log job_id=J + correlation_id
    W-->>Q: Ack / retry according to queue policy
~~~

### 16.1. Nên truyền gì qua message?

- **message_id/job_id** cho bản tin cụ thể.
- **correlation_id** cho nghiệp vụ lớn, nếu được phép truyền.
- **causation_id** hoặc span link để nối bản tin với request sinh ra nó.
- **trace context đã được kiểm tra**, nếu hệ thống hỗ trợ trace qua messaging.
- **attempt_count, enqueue_time, dequeue_time** để phân biệt queue delay và processing time.

**Không truyền Authorization header, session cookie hoặc toàn bộ HTTP header** vào queue chỉ để giữ correlation. Nếu cần quyền xử lý nền, phải có **service identity, delegation/authorization rõ ràng, thời hạn và audit**.

### 16.2. Re-delivery và duplicate

Nhiều queue có cơ chế **at-least-once delivery** hoặc cho phép retry. Một **message_id/job_id** có thể xuất hiện trong nhiều lần xử lý; ghi thêm **delivery_attempt**, worker instance và idempotency/business key để điều tra. Không dùng request ID làm bằng chứng chỉ xử lý đúng một lần.

## 17. Đồng bộ thời gian: event time, receive time và ingest time

Request có thể đi qua nhiều máy, region và log pipeline; nếu clock lệch vài giây, thứ tự bản ghi sẽ đảo ngược.

| Timestamp | Nó mô tả gì? | Lưu ý |
|---|---|---|
| **Client send time** | Client bắt đầu gửi request theo đồng hồ client | Không hoàn toàn tin cậy; clock client có thể sai |
| **Proxy received time** | Proxy nhận request | Cần hiểu timestamp được ghi lúc đầu hay lúc hoàn thành |
| **Event time** | Thời điểm sự kiện xảy ra theo logger | Có thể xảy ra clock skew |
| **Proxy completion time** | Kết thúc xử lý và ghi access log | Thường đến sau backend events |
| **Ingest time** | Collector/SIEM nhận record | Có thể trễ do buffering, retry hoặc outage |
| **Monotonic duration** | Thời lượng đo tại một process/hop | Thường đáng tin hơn phép trừ timestamp giữa máy |

### 17.1. Thực hành tốt

1. Đồng bộ thời gian qua nguồn **NTP/chrony/PTP phù hợp** với môi trường.
2. Log timestamp ở **UTC ISO 8601** hoặc offset rõ ràng; tránh chuỗi giờ không có timezone.
3. Giữ **event_time và ingest_time** riêng để phân biệt thời điểm xảy ra và thời điểm được lưu.
4. Khi tương quan nhiều máy, chấp nhận **khoảng sai lệch có kiểm soát**, không ép order tuyệt đối khi dữ liệu không đủ.
5. Dùng **duration** do từng hop đo để phân tích latency; đừng lấy hai clock khác nhau trừ trực tiếp mà không hiệu chỉnh.

### 17.2. Request completion log đến sau app log là bình thường

Proxy access log thường ghi **sau khi request đã kết thúc**. Backend có thể log "bắt đầu xử lý" hoặc "truy vấn DB" trước đó. Vì vậy sắp xếp theo event_time rồi mong proxy luôn đứng đầu là không chính xác nếu không phân biệt **log-on-receive** và **log-on-completion**.

## 18. Latency: đo đúng request_time và upstream time

Một response đi qua nhiều lớp có thể chịu:

- Client upload và mạng tới edge.
- TLS handshake/connection reuse.
- WAF, auth và rate-limit processing.
- Proxy queue, upstream connection establishment.
- Thời gian chờ backend, DB/cache/third-party.
- Backend serialization và response streaming.
- Thời gian chuyển response về client.

### 18.1. Nginx timing fields thường gặp

| Trường | Khái niệm tham chiếu | Lưu ý |
|---|---|---|
| **$request_time** | Tổng thời gian xử lý request theo định nghĩa Nginx | Có thể gồm client upload/response send; không phải chỉ app latency |
| **$upstream_connect_time** | Thời gian thiết lập upstream connection | Có thể thay đổi với keepalive, TLS tới upstream và retries |
| **$upstream_header_time** | Thời gian tới khi nhận upstream response headers | Không phải thời gian đọc hết response body |
| **$upstream_response_time** | Thời gian nhận upstream response theo Nginx | Có thể nhiều giá trị khi nhiều attempts |

**Không mặc định duration_ms = request_time - upstream_response_time** là thời gian WAF hoặc network. Hai khoảng có thể chứa các thành phần khác nhau, việc làm tròn, streaming và retries khiến phép trừ không đủ tin cậy để gán nguyên nhân.

### 18.2. P95/P99 và phân nhóm

Để đánh giá hiệu năng, tạo **histogram theo route template, service, region, upstream cluster và response class**. Nếu chỉ nhìn average, vài request timeout rất chậm có thể bị che. Với incident, hãy kết hợp p95/p99 với **request ID mẫu** được lấy từ log/trace có phép.

### 18.3. Timeout budget phải nhất quán

Một hệ thống có proxy timeout 30s, backend timeout 60s có thể gây tình huống proxy trả **504** nhưng backend tiếp tục chạy. Nên thiết kế **deadline propagation/cancellation** phù hợp, nhất là request có side effects; log cả **deadline, timeout source và cancellation signal** nếu có.

## 19. Mã HTTP 4xx/5xx: mã nào do lớp nào tạo?

**Một status code không tự cho biết lỗi sinh ở đâu.** Cùng 403 có thể do WAF hoặc ứng dụng, cùng 429 có thể do CDN/API gateway/backend, 500 có thể do app hoặc proxy khi xử lý nội bộ.

| Mã / dấu hiệu | Nguyên nhân thường gặp | Backend có log không? |
|---|---|---|
| **200/201/204** | Thành công theo semantics HTTP | Có nếu request thực sự tới backend; không có nếu cache/edge tự trả |
| **301/302/307/308** | Redirect ở CDN/proxy/app | Không nhất thiết |
| **401** | Chưa xác thực / challenge auth phù hợp | Tùy auth ở gateway hay backend |
| **403** | WAF block, gateway deny hoặc app authorization deny | Có thể **không có** nếu chặn tại edge |
| **404** | Không có route ở proxy hoặc resource không tồn tại ở app | Tùy lớp tạo |
| **429** | Rate limit/quota tại CDN/WAF/gateway/app | Không có backend log nếu chặn trước upstream |
| **499 (Nginx)** | Client đã đóng kết nối theo cách Nginx ghi nhận | Backend vẫn có thể đang xử lý hoặc không nhận request |
| **502** | Bad Gateway: upstream trả phản hồi không hợp lệ/lỗi kết nối hoặc một số lỗi gateway | Có thể không có backend log cho connection failure |
| **503** | Service unavailable: proxy no healthy upstream/overload hoặc app 503 | Tùy nơi phát |
| **504** | Gateway timeout khi chờ upstream hoặc xử lý gateway | Backend có thể xử lý hoàn tất muộn |

**499 không phải HTTP status chuẩn gửi tới client**; đó là mã **Nginx-specific** để mô tả tình huống client đóng kết nối. Khi SIEM chuẩn hóa nên giữ **vendor_status** và diễn giải, không trộn 499 với response 4xx chuẩn theo giả định.

### 19.1. Dùng status_source

~~~json
{
  "request_id": "e7a4dd1c5b3b4a3d8e9e7cc142aa0b57",
  "proxy_status": 403,
  "backend_status": null,
  "status_source": "waf_block",
  "waf_rule_id": "rule-901",
  "waf_event_id": "waf-evt-761"
}
~~~

Không được suy diễn "backend trả 403" chỉ từ **proxy_status=403**. Cần trường **status_source, upstream_attempt_count và WAF decision**.

## 20. WAF và request ID: tương quan request đã bị chặn

Một request có thể bị WAF chặn **trước khi bất kỳ backend nào nhận được traffic**. Nếu pipeline chỉ ghi request ID khi backend xử lý, các request bị chặn sẽ **không có cách nối tới log ứng dụng**, khiến NOC/SOC khó giải thích ticket.

### 20.1. Thiết kế cho request bị chặn

~~~mermaid
flowchart TD
    U[Client request] --> E[Edge sinh R]
    E --> W{WAF policy evaluation}
    W -- Block --> X[Edge trả 403 / WAF event E1]
    W -- Allow --> P[Proxy / Load Balancer]
    P --> A[Backend có log R]
    E -. R .-> L[Central log]
    X -. R + event_id + rule_id .-> L
    P -. R .-> L
    A -. R + trace/span .-> L
~~~

Nếu request bị chặn, **không có backend log là đúng hành vi**, không phải ingestion failure. Bản ghi WAF cần cho biết **ID, action, matched rules, policy version, thời điểm và response status** mà không ghi payload nhạy cảm.

### 20.2. Rule ID không phải event ID

Một WAF rule có thể match hàng triệu request; **rule_id** dùng để nhóm policy, **event_id** nhận diện một lần đánh giá hoặc sự kiện, còn **request_id** nối với các lớp proxy. Nếu WAF có nhiều rule evaluations cho một request, có thể có **nhiều rule ID/event ID** liên kết cùng request ID.

### 20.3. Count/Challenge/RateLimit

Không đánh đồng:

- **Count/Log:** rule match nhưng chưa chắc chặn.
- **Block:** WAF quyết định không chuyển request upstream.
- **Challenge:** client phải thực hiện một bước xác minh; có thể phát nhiều request liên quan.
- **Rate limit:** một số request bị 429 trước backend, các request khác vẫn được forward.

Phân biệt **matched_rule, action, final_disposition và HTTP response status** để giảm false positive khi điều tra.

## 21. CDN cache: request không đến backend vẫn có thể thành công

Nếu CDN phục vụ nội dung từ cache, backend có thể **không có log tương ứng với từng client request**. Đây là behavior bình thường.

~~~text
Request R1 -> CDN cache HIT  -> 200 response, không gọi origin
Request R2 -> CDN cache MISS -> Origin / Backend, có upstream log
Request R3 -> CDN cache STALE + refresh async -> Client 200,
              có thể có refresh job riêng ở hậu trường
~~~

### 21.1. Trường log cần thiết

- **cache_status**: HIT, MISS, BYPASS, STALE hoặc giá trị vendor tương ứng.
- **cache_key_hash/route** nếu an toàn và có nhu cầu điều tra, không log token.
- **origin_request_id** khi CDN thực sự gọi origin.
- **response source**: cache/edge/upstream.
- **TTL/Age**, response status, cache invalidation event khi phù hợp.

**Không dùng số backend requests làm số lượng người dùng đã gửi request** nếu CDN cache hoạt động; phải tổng hợp ở ingress/edge theo định nghĩa metric.

### 21.2. Cache và nội dung nhạy cảm

Correlation logs có thể giúp điều tra cache nhầm giữa tenant/user, nhưng **không được log cache key chứa token, cookie hoặc thông tin cá nhân**. Cache policy phải được kiểm tra về Authorization, Vary, Cache-Control, tenant boundaries và routing ngoài việc có request ID.

## 22. gRPC, HTTP/2, WebSocket và streaming

### 22.1. HTTP/2 multiplexing

Nhiều request chạy trên **một TCP/TLS connection**. Không dùng connection ID hoặc 5-tuple làm khóa duy nhất của request. Mỗi request/stream cần **request ID/trace context** riêng theo giao thức và khả năng instrumentation.

### 22.2. gRPC

Với gRPC, HTTP/2 response có thể mang **HTTP status 200** nhưng gRPC operation thất bại thông qua **grpc-status trong trailers**. Nếu chỉ ghi **http_status**, dashboard có thể báo thành công dù ứng dụng trả gRPC **DEADLINE_EXCEEDED, UNAVAILABLE hoặc PERMISSION_DENIED**.

~~~json
{
  "layer": "api_gateway",
  "protocol": "grpc",
  "request_id": "e7a4dd1c5b3b4a3d8e9e7cc142aa0b57",
  "service": "inventory-api",
  "rpc_method": "GetItem",
  "http_status": 200,
  "grpc_status": "DEADLINE_EXCEEDED",
  "duration_ms": 30000
}
~~~

Đây là schema minh họa; cần lấy **trailer/status đúng** tại gateway hoặc gRPC instrumentation. Không tự quy đổi toàn bộ lỗi gRPC về HTTP 5xx mà thiếu ngữ cảnh.

### 22.3. WebSocket

Một request upgrade WebSocket có thể nhận **101 Switching Protocols**, sau đó tạo phiên dài. Access log tại proxy thường ghi khi kết nối **kết thúc**, không ghi cho mỗi message. Cần **connection/session ID**, handshake request ID, close code, time, direction và event correlation thích hợp, tránh log payload nhạy cảm.

### 22.4. Server-Sent Events và streaming

Một response streaming có thể mở lâu dù backend đã tạo headers sớm. Phân tích **header time, response time và time-to-first-byte** theo semantics của proxy; đừng quy một request_time dài là backend xử lý CPU chậm.

## 23. Dữ liệu riêng tư, log injection và bảo vệ audit trail

Log của proxy có thể vô tình chứa dữ liệu rất nhạy cảm:

| Dữ liệu | Rủi ro | Khuyến nghị |
|---|---|---|
| **Authorization header/cookie** | Lộ bearer token/session | Không log nội dung; nếu cần dùng cờ/loại đã redacted |
| **URL query string** | Token, email, mã xác minh, từ khóa cá nhân | Log route template và tập tham số được duyệt |
| **Request/response body** | Mật khẩu, PII, dữ liệu khách hàng, dữ liệu kinh doanh | Không ghi mặc định; exception có phê duyệt và redaction |
| **X-Forwarded-For/raw headers** | Spoofed identifiers, PII và injection | Chỉ dùng trusted values; giới hạn độ dài/charset |
| **Client IP/user/device** | Dữ liệu cá nhân, giám sát vị trí truy cập | RBAC, retention, audit và privacy policy |
| **TLS certificate subject/SAN** | Có thể chứa identity nội bộ hoặc thiết bị | Ghi thông tin tối thiểu đủ điều tra |
| **Trace baggage/tracestate** | Metadata do client gửi, có thể chứa PII | Allowlist, giới hạn kích thước, không ghi raw bừa bãi |
| **Upstream error messages** | Có thể chứa SQL, path nội bộ hoặc secret | Chuẩn hóa error code; giữ raw message ở nơi hạn chế |

### 23.1. Log injection

Header request ID chứa newline hoặc ký tự điều khiển có thể làm **giả mạo thêm log line** nếu ứng dụng ghép string không escaping. Cần:

1. **Validate length/charset** ở ingress.
2. **Structured encoding** đúng (ví dụ JSON escaping).
3. Giới hạn log field size và số header có thể ghi.
4. Không ghi dữ liệu khách trực tiếp thành tên trường, tên index hoặc câu truy vấn.
5. Tách sự kiện **parse failure** với dữ liệu nguồn gây lỗi, tránh lặp lại payload.

### 23.2. Integrity và access control

- Chỉ service/collector được phép đẩy logs vào pipeline; dùng **mTLS/IAM/RBAC** theo thiết kế.
- Áp **append-only hoặc immutable retention** khi yêu cầu điều tra, kèm chống sửa/xóa trái phép.
- Giới hạn ai được đọc log có IP/user/customer; audit truy vấn nhạy cảm.
- Dùng policy retention/region phù hợp; **không giữ logs vô hạn** chỉ vì thuận tiện.
- Tránh đặt access token trong URL dashboard hoặc chia sẻ link tra request ID mà không xác thực.

**Một request ID không phải bằng chứng xác thực**. Nếu kẻ khác biết ID, họ không được phép xem toàn bộ nhật ký của user/tenant đó.

## 24. Điều tra mẫu: 504 tại proxy, backend 200

### 24.1. Tình huống

Người dùng gửi **POST /v1/orders** và thấy **504 Gateway Timeout** sau khoảng 30 giây. Phía backend có log xử lý hoàn tất và trả HTTP 200 sau 33 giây.

### 24.2. Dữ liệu minh họa

~~~text
2026-11-28T08:20:00.000Z  EDGE    R  FORWARD request /v1/orders
2026-11-28T08:20:00.010Z  WAF     R  ALLOW
2026-11-28T08:20:00.015Z  PROXY   R  upstream=orders-2  timeout=30000ms
2026-11-28T08:20:00.028Z  APP     R  start order processing
2026-11-28T08:20:29.990Z  APP     R  inventory dependency still pending
2026-11-28T08:20:30.018Z  PROXY   R  final_status=504
2026-11-28T08:20:33.110Z  APP     R  order committed, app_status=200
2026-11-28T08:20:33.111Z  APP     R  response write failed/client gone (possible)
~~~

**Giải thích:** proxy có thể đã ngừng chờ và trả 504 trong khi application vẫn tiếp tục. Log **app_status=200** có thể chỉ phản ánh ứng dụng muốn trả 200, không chứng minh client nhận được 200.

### 24.3. Câu hỏi điều tra

1. ID **R** có thực sự được truyền qua tất cả hop?
2. Proxy phát 504 do **connect timeout, read timeout hay overall deadline**?
3. Backend có nhận request đầy đủ không, đã commit transaction chưa?
4. Có retry tại proxy, SDK, client hoặc queue không?
5. **POST có idempotency key** phù hợp và giới hạn side effect không?
6. Có body lớn, DB lock, dependency timeout hoặc thread pool saturation không?
7. Client có thấy response nào khác qua retry hoặc người dùng bấm gửi lại không?

### 24.4. Hành động phù hợp

Không sửa bằng cách **tăng timeout vô hạn**. Cần phân tích latency/dependency, deadline, cancellation, idempotency và thông báo trạng thái nghiệp vụ. Dùng **log và distributed trace** để xác định upstream attempt, thời điểm proxy timeout, thời điểm backend commit và trạng thái client; chỉ điều tra routing/firewall sâu hơn nếu có bằng chứng về sự cố đường mạng.

## 25. Điều tra mẫu: 403 WAF nhưng không có backend log

### 25.1. Tình huống

Một client báo API trả 403. NOC tìm request ID ở backend nhưng không thấy gì. WAF event có ID cùng request nhưng action **BLOCK** trước khi forward.

~~~json
{
  "layer": "waf",
  "request_id": "e7a4dd1c5b3b4a3d8e9e7cc142aa0b57",
  "waf_event_id": "waf-evt-761",
  "matched_rules": ["rule-901", "rule-903"],
  "final_disposition": "BLOCK",
  "http_status": 403,
  "upstream_attempts": 0
}
~~~

**Kết luận:** không có backend log **là kết quả đúng**. Việc cần kiểm tra là **rule/policy, request metadata đã redacted, false positive, change timeline và khả năng client thuộc nhóm cần truy cập**.

### 25.2. Không mở WAF rule toàn bộ để hết 403

Nếu rule tạo false positive, xem **scope, endpoint, managed vs custom rules, mode Count/Challenge và exception theo đặc điểm request**. Mọi ngoại lệ cần owner, expiry, log và kiểm thử regression; không tắt WAF trên toàn ứng dụng khi chưa đánh giá rủi ro.

## 26. Điều tra mẫu: 502, retry và client ngắt kết nối

### 26.1. Nhóm lỗi không được đồng nhất

- **502 do connection refused:** backend không lắng nghe hoặc network policy/target sai; có thể không có application log.
- **502 do invalid upstream response:** upstream có kết nối nhưng trả phản hồi không hợp lệ theo gateway.
- **499 ở Nginx:** client đóng kết nối trước khi proxy hoàn thành; backend có thể vẫn xử lý.
- **503 no healthy targets:** load balancer có thể không chọn được backend để gửi.
- **Retry success:** client cuối cùng nhận 200 dù một upstream attempt trước lỗi.

### 26.2. Ví dụ timeline hai attempts

~~~text
Request R
  Edge: received 14:00:00.000Z
  Gateway: attempt 1 to orders-1 at 14:00:00.010Z
  Gateway: reset/502 at 14:00:00.130Z
  Gateway: attempt 2 to orders-2 at 14:00:00.140Z
  orders-2: HTTP 200 at 14:00:00.230Z
  Gateway: final_status=200 at 14:00:00.235Z

Nếu chỉ chọn event 502 và bỏ qua attempt 2, báo cáo sẽ sai.
~~~

### 26.3. Điều kiện cần giữ

Ghi **attempt_count, upstream_addr, per-attempt status/reason, final status và timings**. Với request **không idempotent**, cần biết retry đã được cho phép theo chính sách gì và backend có xử lý lần 1 hay không.

## 27. Tìm sự cố bằng truy vấn SIEM hoặc kho log

Các ví dụ sau dùng **schema normalized_http_logs giả định**, không phải cú pháp sẵn cho mọi SIEM. Chỉ truy vấn logs trong phạm vi quyền của người điều tra.

### 27.1. Tìm chuỗi request theo ID

~~~sql
SELECT event_time, ingest_time, layer, service, instance,
       request_id, trace_id, span_id,
       route, http_status, upstream_status, status_source,
       upstream_target, duration_ms
FROM normalized_http_logs
WHERE request_id = 'e7a4dd1c5b3b4a3d8e9e7cc142aa0b57'
ORDER BY event_time, layer;
~~~

Nếu không thấy đủ hop, cần kiểm tra **log sampling, CDN cache, WAF BLOCK, pipeline ingestion delay, clock skew, ID lost ở proxy và backend crash** trước khi kết luận dữ liệu bị xóa.

### 27.2. Phân tích 5xx theo lớp gây lỗi

~~~sql
SELECT layer, service, status_source, http_status,
       COUNT(*) AS request_count
FROM normalized_http_logs
WHERE event_time >= TIMESTAMP '2026-11-28 08:00:00'
  AND event_time <  TIMESTAMP '2026-11-28 09:00:00'
  AND http_status BETWEEN 500 AND 599
GROUP BY layer, service, status_source, http_status
ORDER BY request_count DESC;
~~~

Lưu ý **một request có nhiều log ở nhiều layer**, nên tổng count qua tất cả layers **không bằng số client requests**. Nếu muốn đếm client requests duy nhất, lọc **layer=trusted_ingress** hoặc dùng **COUNT DISTINCT(request_id)** theo định nghĩa và khả năng dedup.

### 27.3. Phát hiện chênh lệch proxy vs backend

~~~sql
WITH proxy AS (
  SELECT request_id, MAX(http_status) AS proxy_status
  FROM normalized_http_logs
  WHERE layer = 'reverse_proxy'
    AND event_time >= TIMESTAMP '2026-11-28 08:00:00'
  GROUP BY request_id
),
app AS (
  SELECT request_id, MAX(http_status) AS app_status
  FROM normalized_http_logs
  WHERE layer = 'backend'
    AND event_time >= TIMESTAMP '2026-11-28 08:00:00'
  GROUP BY request_id
)
SELECT p.request_id, p.proxy_status, a.app_status
FROM proxy p LEFT JOIN app a ON p.request_id = a.request_id
WHERE a.request_id IS NULL OR p.proxy_status <> a.app_status;
~~~

**Cảnh báo:** MAX(status) ở ví dụ chỉ giúp tạo shortlist; **không xác định final attempt** nếu một request có nhiều backend responses/retries. Muốn kết luận phải join theo **attempt_id, response_source, event_type và timestamps**. Với cache/WAF BLOCK, app log thiếu là bình thường.

### 27.4. Dùng trace ID để tìm các service liên quan

~~~sql
SELECT event_time, service, span_id, parent_span_id,
       event_name, duration_ms
FROM trace_enriched_logs
WHERE trace_id = '4bf92f3577b34da6a3ce929d0e0e4736'
ORDER BY event_time;
~~~

Với trace sampling, có thể chỉ có một phần hoặc không có spans. Dùng request ID/event logs bổ sung và ghi **telemetry coverage** để tránh suy diễn một hop không tồn tại.

## 28. Runbook triển khai log correlation

### Bước 1 — Inventory toàn bộ data path

Liệt kê **CDN/WAF, API gateway, reverse proxy, LB, ingress, service mesh, backend, queue, cloud/on-prem, VPN và DNS**. Vẽ sơ đồ các điểm TLS termination, địa chỉ upstream, route, cache, WAF block, failover và nơi có thể đi vòng.

### Bước 2 — Chuẩn hóa ranh giới tin cậy

Chọn **trusted ingress** sinh request ID; chính sách ghi đè/kiểm tra các header bên ngoài. Xác minh các hop downstream chỉ nhận traffic từ proxy được phép, với **ACL/mTLS/firewall** tương ứng. Xác định cách xác minh client IP và trusted forwarded headers.

### Bước 3 — Định nghĩa schema

Chọn các field bắt buộc: **event_time, layer, service, request_id, trace/span, route, source, status, status_source, upstream/attempt, duration, policy_version, identity mapping** khi có. Chuẩn hóa data types, null semantics và trường thông tin riêng tư phải redacted.

### Bước 4 — Instrument từng lớp

- **Edge/WAF:** log event/mapping, decision, request ID và edge ID.
- **Proxy/LB:** access log JSON, upstream attempts, final status, timeouts.
- **Backend:** MDC/context propagation, app status và dependency logs.
- **Queue/worker:** correlation/causation/message IDs, processing attempt.
- **OpenTelemetry:** traceparent propagation và mapping logs-traces khi phù hợp.

### Bước 5 — Tạo test trong môi trường được phép

Thử **request allow, WAF block, cache hit/miss, timeout, retry, fan-out, async, gRPC/WebSocket, IPv4/IPv6, direct-to-origin bypass**, và header do client giả mạo. Không thử xâm nhập hay tạo lưu lượng gây hại vào hệ thống ngoài phạm vi.

### Bước 6 — Kết nối pipeline giám sát

Thiết lập collector/forwarder, JSON parsing, mapping field, retention, RBAC, dashboards, alert và **event-time/ingest-time**. Kiểm tra quyền truy cập log theo tenant/role, tránh lưu Authorization/body/PII.

### Bước 7 — Rollout và regression

Canary theo region/route, đối chiếu log coverage và error budget. Sau đổi **WAF rules, load balancer, proxy firmware/config, service mesh, TLS, retry, cloud networking hoặc API app**, kiểm thử lại chuỗi correlation.

~~~mermaid
flowchart TD
    A[Inventory các hop và trust boundaries] --> B[Chọn ID strategy + trusted ingress]
    B --> C[Chuẩn hóa JSON schema và privacy policy]
    C --> D[Instrument edge/WAF/proxy/backend/queue]
    D --> E[Kiểm thử allow/block/cache/retry/timeout/async]
    E --> F{IDs, statuses, timings và mappings đúng?}
    F -- Không --> G[Sửa header/log mapping/ingestion]
    G --> D
    F -- Có --> H[Deploy canary và giám sát coverage]
    H --> I[Regression sau thay đổi kiến trúc]
~~~

## 29. Runbook điều tra lỗi hoặc sự cố bảo mật

### Giai đoạn 1 — Ghi nhận yêu cầu

Lấy **request ID do hệ thống cấp**, thời điểm kèm timezone, hostname, route, phản hồi client, user/tenant identity khi được phép, địa chỉ nguồn đã xác minh hoặc edge request ID. Không hỏi khách hàng gửi token, cookie hay password.

### Giai đoạn 2 — Xác định entrypoint

Tìm **edge/WAF log**, xác nhận request có tới hệ thống hay không, TLS/HTTP protocol, cache_status, action và policy version. Nếu thấy WAF BLOCK, không tìm backend log bằng mọi giá.

### Giai đoạn 3 — Lần theo từng hop

Theo **request_id**, kết hợp **edge_id, trace_id, attempt_id** để nối tới proxy/LB/backend/queue. So sánh event_time, trạng thái, upstream target và retries. Với service-to-service, kiểm tra **mTLS identities và API authorization**.

### Giai đoạn 4 — Phân loại nguyên nhân

| Nhóm | Bằng chứng cần thiết |
|---|---|
| **WAF/Policy deny** | final_disposition, rule/action, request ID, upstream_attempt_count |
| **Load balancer health/retry** | target selection, health, attempt status, reset/timeouts |
| **Network/firewall** | route, security group, VPN/ACL, flow deny, upstream reachability |
| **TLS/mTLS** | handshake errors, peer certificate/identity, SNI, trust policy |
| **Backend/app** | app log, trace/span, DB/dependency, timeout/budget, error code |
| **Queue/async** | job/message IDs, retry/delivery count, worker errors |
| **Observability gap** | ID lost, wrong parsing, sampling, collector outage, clock skew |

### Giai đoạn 5 — Khắc phục và kiểm chứng

Sửa tại **đúng thành phần gây lỗi**, tránh tắt WAF, mở firewall any/any hoặc tăng timeout vô hạn. Kiểm tra cả **luồng ALLOW hợp lệ, luồng DENY bảo mật, status cuối, trace coverage và user-facing SLI**.

### Giai đoạn 6 — Hậu kiểm

Tổng kết **timeline, ID mapping, căn nguyên, phạm vi người dùng/tenant, tác động bảo mật, policy/config changes, điểm mù telemetry và bài học**. Đặt owner và lịch regression; sửa schema/alert để lần sau điều tra nhanh hơn.

## 30. Kiểm thử toàn tuyến cho log correlation

Sử dụng **test client và endpoint do tổ chức sở hữu**, không quét mạng hoặc tạo traffic phá hoại. Thiết kế cả ca thành công, lỗi và các trường hợp thiếu log có chủ đích.

| ID | Kịch bản | Kết quả mong đợi | Bằng chứng |
|---|---|---|---|
| **T-01** | Một GET hợp lệ qua CDN/WAF/proxy/backend | Cùng request ID hoặc mapping rõ | Log từng hop |
| **T-02** | Client tự gửi X-Request-ID bất kỳ | Trusted ingress ghi đè/validate theo policy | Edge/app request ID |
| **T-03** | Client tự gửi X-Forwarded-For | Không thể giả client_ip_authoritative | Peer IP/trusted proxy logs |
| **T-04** | Header ID chứa newline/ký tự điều khiển | Reject/sanitize, không làm sai JSON parser | Ingress validation/log |
| **T-05** | WAF BLOCK | Có edge/WAF log, không buộc có backend log | final_disposition, attempts=0 |
| **T-06** | WAF Count/Challenge | Log match khác final action | Rule events và client flow |
| **T-07** | Rate limit 429 | Xác định lớp phát 429, không nhầm backend | action_source |
| **T-08** | CDN HIT | Client 200, origin request không bắt buộc | cache_status |
| **T-09** | CDN MISS | Có origin mapping/attempt phù hợp | cache/origin logs |
| **T-10** | LB retry sau connection reset | Một request nhiều attempts, final status đúng | attempt list |
| **T-11** | POST side effect với retry được mô phỏng | Không duplicate nghiệp vụ nhờ idempotency policy | Business log + attempts |
| **T-12** | Upstream timeout 504 | Proxy 504 và app có thể hoàn tất muộn | Correlated timeline |
| **T-13** | Client disconnect 499 trên Nginx | Không báo 499 là HTTP response client thật nhận | vendor_status, app state |
| **T-14** | 502 do upstream connection failed | Không ép cần có app log | Proxy error/flow logs |
| **T-15** | Fan-out ba backend | Trace ID chung, spans riêng | Trace graph, app logs |
| **T-16** | Async queue job 202 | Correlation/causation links giữa request và job | Queue/worker logs |
| **T-17** | Worker retry/re-delivery | Phân biệt message ID và delivery attempts | Job telemetry |
| **T-18** | HTTP/2 multiplexing | Phân biệt requests cùng connection | Request/stream IDs |
| **T-19** | gRPC HTTP 200 + grpc-status lỗi | Dashboard không báo false success | grpc_status |
| **T-20** | WebSocket 101 + close | Có connection lifecycle log đúng | Handshake/close |
| **T-21** | IPv4 và IPv6 ingress | Client IP handling/trusted hops đúng | Edge/backend logs |
| **T-22** | Nhiều CDN POP/region | Schema/ID mapping không lệch | Multi-region logs |
| **T-23** | Clock skew mô phỏng trong lab | Điều tra không dựa vào thứ tự log tuyệt đối | event/ingest time |
| **T-24** | Async execution Java | MDC/trace context không biến mất khi chuyển thread | Async service logs |
| **T-25** | TLS termination giữa nhiều proxy | Đúng nguồn forwarded protocol/client identity | Edge/ingress logs |
| **T-26** | Direct-to-backend path attempt trong lab | Bị chặn theo ACL hoặc log nguồn không tin | Firewall/mTLS |
| **T-27** | Request có sensitive query/cookie | Log không chứa secret/PII ngoài policy | Redaction test |
| **T-28** | SIEM ingestion delay/outage | Có khả năng phân biệt event_time và ingest_time | Pipeline metrics |
| **T-29** | Sampling mất trace | Request metadata vẫn tra được qua logs | Logs + trace presence |
| **T-30** | HA/failover chuyển proxy/backend | ID bảo tồn và schema đồng nhất | Canaries, config diff |
| **T-31** | Mỗi tenant truy vấn log theo request ID | RBAC không lộ log tenant khác | AuthZ tests |
| **T-32** | Metric labels với ID ngẫu nhiên | Không tạo high-cardinality label | Metrics review |

### 30.1. Kiểm thử cả nội dung đúng và an ninh log

Một hệ thống có correlation ID truyền xuyên hop nhưng vẫn log **password/token**, hoặc cho **khách Internet tự khai client IP**, chưa đạt yêu cầu bảo mật. Tương quan cần đi cùng **trust boundary, log integrity, privacy và quyền tra cứu**.

## 31. Những lỗi thiết kế thường gặp

| Ngộ nhận hoặc sai sót | Hậu quả | Hướng khắc phục |
|---|---|---|
| **Mỗi proxy tự sinh ID mới không mapping** | Mất chuỗi end-to-end | Sinh ở trusted ingress, preserve hoặc log mapping |
| **Tin X-Request-ID từ client như danh tính** | Spoofing, log poisoning, điều tra sai | Validate/overwrite và không dùng ID để cấp quyền |
| **Lấy IP đầu tiên trong XFF làm client thật** | Dễ nhận nhầm actor | Trusted proxy chain + peer source policy |
| **Chỉ log 200 request** | Mất 403/429/5xx/WAF block | Ghi completion/decision events đúng lớp |
| **Chỉ log ở backend** | Không thấy cache HIT, WAF BLOCK, proxy connect failure | Instrument edge/WAF/proxy |
| **Gộp upstream_status thành một số** | Mất thông tin retries | Per-attempt logs/array |
| **Coi HTTP status = gRPC status** | Bỏ sót gRPC lỗi trong HTTP 200 | Ghi grpc-status/trailers |
| **Đếm số log thay số client requests** | Double count qua nhiều lớp | Count tại trusted ingress hoặc dedup theo định nghĩa |
| **So thứ tự logs bằng ingest_time** | Timeline bị đảo bởi queue/collector delay | Event time + clock-skew tolerance |
| **Không đồng bộ clock** | Dễ đổ lỗi sai hop | NTP/chrony và monotonic duration |
| **Nhầm request_time với backend CPU time** | Chẩn đoán latency sai | Phân biệt queue/connect/upstream/streaming |
| **Đặt request_id làm metric label** | Cardinality/cost quá cao | Dùng route/service/status class |
| **Log query/cookie/body mặc định** | Lộ PII/token và tăng rủi ro | Redaction, route template, RBAC/retention |
| **Giữ raw trace baggage từ client** | Lộ dữ liệu, log injection hoặc sai context | Allowlist, giới hạn kích thước |
| **Không truyền MDC qua async thread** | Request ID mất khi có executor/Reactor | Context propagation theo framework |
| **Coi app trả 200 là client nhận 200** | Đọc sai sự cố 504 hoặc disconnect | So proxy final status và timeline |
| **Retry POST không idempotency** | Giao dịch nghiệp vụ bị nhân đôi | Retry policy và idempotency key riêng |
| **Tra request ID là được xem mọi log** | Lộ dữ liệu tenant khác | IAM/RBAC và tenant-scoped queries |
| **Một collector không thấy log nghĩa là request không xảy ra** | False negative | Kiểm tra sampling, ingest, cache, WAF, region |
| **Backend public nhưng tin header từ proxy** | Bypass identity/source protections | Network isolation, mTLS và overwrite tại ingress |

## 32. Checklist thiết kế và vận hành

- [ ] Có sơ đồ data path cho CDN, WAF, proxy, LB, ingress, service mesh, backend, queue và cloud/VPN.
- [ ] Đã chọn **trusted ingress** sinh/chuẩn hóa request ID trước WAF block khi có thể.
- [ ] Các proxy kế tiếp **preserve ID** hoặc có mapping edge_id ↔ request_id.
- [ ] Có quy định format, độ dài, charset và xử lý duplicate headers.
- [ ] Không dùng request ID, trace ID, XFF hoặc client-supplied headers như bằng chứng auth/authorization.
- [ ] Xác thực danh sách trusted proxies và bảo vệ direct-to-origin bằng ACL/mTLS/segmentation.
- [ ] Header forwarded client IP/protocol được tạo hoặc ghi đè tại trust boundary phù hợp.
- [ ] Log dùng schema JSON nhất quán và có **schema version**.
- [ ] Có **event_time kèm timezone**, ingest_time riêng và đồng bộ clock.
- [ ] Ghi **final_http_status, upstream_status, status_source** với semantics rõ.
- [ ] Ghi upstream target, attempt index/retry reason và timeout/deadline nếu có.
- [ ] Phân biệt WAF action/matched rule/final disposition/rule ID/event ID.
- [ ] Xử lý cache HIT/BYPASS/MISS; không đòi backend log khi không có origin call.
- [ ] Có trace_id/span_id theo W3C Trace Context và quyền truyền context an toàn.
- [ ] Traces có thể sampling nhưng logs an ninh trọng yếu có coverage phù hợp.
- [ ] Không đặt request ID/user ID/raw URL vào metric labels cardinality cao.
- [ ] Backend Java có MDC/context propagation đúng sync/async và cleanup trong finally.
- [ ] Với gRPC/WebSocket/streaming, log đúng status/lifecycle, không chỉ HTTP code.
- [ ] Với queue, ghi message/job/causation IDs và delivery attempt.
- [ ] Mỗi tầng log dùng route/service/instance/region và policy version đúng.
- [ ] Tránh ghi Authorization, Cookie, token, body và query thô; redact PII.
- [ ] Log escaping, field-size limits và validator chống log injection.
- [ ] Có access control, audit tra cứu log, retention và chính sách cross-tenant.
- [ ] Có dashboards lỗi 4xx/5xx, WAF decisions, retry rate, p95/p99, missing IDs và log ingestion lag.
- [ ] Có test allow, WAF block, cache, 502, 504, 499, retry, fan-out, async, IPv4/IPv6, multi-region.
- [ ] Có runbook giữ bằng chứng, tra theo ID, xác định lỗi tại đúng hop và phục hồi an toàn.
- [ ] Sau đổi proxy/mesh/WAF/LB/TLS, chạy regression correlation và data-path tests.

## 33. Câu hỏi tự kiểm tra

**1. Vì sao chỉ dựa vào client IP để ghép log không đáng tin?**  
NAT/CDN/VPN, IP tái cấp và nhiều request song song có thể dùng chung IP. Cần request ID, thời điểm, hop và identity đã xác thực.

**2. Request ID và trace ID giống nhau không?**  
Không. Request ID thường đại diện một HTTP request; trace ID nối nhiều spans trong distributed trace và có thể bao trùm nhiều hoạt động.

**3. Một request có thể có hai upstream statuses không?**  
Có. Proxy retry sang backend khác hoặc thử nhiều lần; cần biết từng attempt và final status client thấy.

**4. Tại sao client gửi X-Request-ID không được xem là nguồn tin cậy?**  
Vì client tự sửa header được; trusted ingress phải tạo/kiểm tra ID và backend không được dùng nó để cấp quyền.

**5. Backend ghi HTTP 200 nhưng proxy ghi 504 có mâu thuẫn không?**  
Không nhất thiết. Backend có thể hoàn tất sau khi proxy hết timeout và đã trả 504 cho client.

**6. WAF ghi BLOCK/403 nhưng backend không có log là lỗi pipeline?**  
Chưa chắc. Nếu WAF chặn trước upstream, không có request nào tới backend nên không có backend log là đúng.

**7. Vì sao HTTP 200 ở gRPC chưa chắc request thành công?**  
gRPC có trạng thái riêng trong trailers, có thể trả DEADLINE_EXCEEDED hoặc lỗi khác dù HTTP transport status là 200.

**8. Khi CDN cache HIT, có nhất thiết tồn tại backend request tương ứng không?**  
Không. Cache có thể phục vụ response mà không gọi origin.

**9. X-Forwarded-For đầu tiên có luôn là IP khách thật không?**  
Không. Cần xác minh trusted proxies và socket peer, vì client có thể giả header ban đầu.

**10. Vì sao không nên đưa request ID vào metric label?**  
ID gần như duy nhất, gây high cardinality và chi phí/tải hệ thống metrics rất lớn.

**11. Vì sao cần event_time và ingest_time riêng?**  
Collector có thể gửi log chậm hoặc retry; ingest order không chắc phản ánh thứ tự sự kiện.

**12. MDC có tự theo request sang executor hoặc Reactor thread không?**  
Không mặc định. Phải dùng context propagation tương ứng và cleanup để tránh mất/lẫn ID.

**13. Traceparent có thể dùng như user authentication header không?**  
Không. Nó là metadata tracing, client bên ngoài có thể tự tạo và cần validation/limits.

**14. Chuyển một POST có side effect sang backend khác có thể gây vấn đề gì?**  
Retry khi lần đầu đã commit có thể tạo nghiệp vụ trùng. Cần idempotency/transaction semantics riêng.

**15. Cần gì để điều tra được một request bị WAF rate-limit tại edge?**  
Edge/WAF request ID, action, rule/event ID, final status 429, thời điểm và policy version; không bắt buộc có backend log.

**16. Một request ID cho phép bất kỳ ai xem nhật ký request đó không?**  
Không. Log phải được bảo vệ theo IAM/RBAC, tenant scope và chính sách riêng tư.

## 34. Tài liệu tham khảo

- [W3C Trace Context — Recommendation](https://www.w3.org/TR/trace-context/): traceparent, tracestate, trace ID và các quy tắc truyền trace context.
- [W3C Baggage — Specification](https://www.w3.org/TR/baggage/): ngữ cảnh truyền metadata và các giới hạn bảo mật.
- [OpenTelemetry — Documentation](https://opentelemetry.io/docs/): logs, traces, metrics và context propagation.
- [OpenTelemetry — Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/): cấu trúc log và tương quan với trace/span.
- [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239): header Forwarded và ngữ nghĩa proxy.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): HTTP status, metadata và semantics request/response.
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): multiplexed streams và các đặc tính HTTP/2.
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446): bảo vệ kết nối TLS qua các hop theo thiết kế.
- [Nginx — Log Module](https://nginx.org/en/docs/http/ngx_http_log_module.html): log_format, access_log, escape=json.
- [Nginx — HTTP Proxy Module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html): proxy_set_header và xử lý upstream.
- [Nginx — Embedded Variables](https://nginx.org/en/docs/http/ngx_http_core_module.html#variables): request, upstream và các biến HTTP liên quan.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): log security, dữ liệu cần/không nên log, log injection và audit.
- [OWASP — REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html): xác thực, giới hạn request, kiểm soát API.
- [NIST SP 800-92 — Guide to Computer Security Log Management](https://csrc.nist.gov/pubs/sp/800/92/final): nguyên tắc thu thập, phân tích, bảo vệ và quản trị log.
- [CNCF — OpenTelemetry Project](https://www.cncf.io/projects/opentelemetry/): hệ sinh thái quan sát dịch vụ phân tán.

**Ghi nhớ:** Log correlation giữa proxy và backend hiệu quả khi **request được gắn định danh đáng tin từ ingress**, những hop tiếp theo **giữ ID hoặc log mapping**, và dữ liệu được ghi với **timestamp, status source, upstream attempt, trace/span cùng đúng schema**. Không nhầm **ID do client tự gửi với danh tính được xác thực**, không nhầm **status proxy với status backend**, và không mặc định một request đi thẳng tới một service. Kết hợp **WAF, load balancing, TLS/mTLS, firewall segmentation, OpenTelemetry, SIEM và quản trị log** để tái dựng đường đi, chẩn đoán lỗi chính xác và bảo vệ dữ liệu khi vận hành.
