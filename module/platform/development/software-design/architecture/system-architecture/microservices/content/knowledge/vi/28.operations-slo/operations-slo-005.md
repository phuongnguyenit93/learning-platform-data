# Chẩn đoán sự cố theo đồ thị phụ thuộc trong Microservices

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices → Vận hành và SLO.
>
> **Bài học:** Khi người dùng gặp lỗi, hệ thống có thể có hàng chục hoặc hàng trăm microservice. **Đồ thị phụ thuộc (dependency graph)** cho biết service nào gọi service nào, dữ liệu và tài nguyên quan trọng đi qua đâu, lỗi ở một node/edge có thể lan đến những hành trình nghiệp vụ nào. Kết hợp đồ thị với **SLI/SLO, Four Golden Signals, distributed traces, logs, event triển khai và tri thức vận hành** giúp chuyển từ “cái gì đang hỏng?” sang “phần nào khởi phát sự cố, vì sao lan rộng, cách giảm tác động và bằng chứng phục hồi là gì?”.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Biểu diễn microservice, database, broker, cache, external provider và API Gateway thành các node và edge có **hướng phụ thuộc** rõ ràng.
2. Phân biệt **upstream/downstream**, phụ thuộc bắt buộc/tùy chọn, đồng bộ/bất đồng bộ, runtime dependency và deployment/config dependency.
3. Đọc đồ thị cùng với SLO, traffic, error rate, p95/p99 latency và saturation để khoanh vùng sự cố từ user journey đến dependency có khả năng liên quan.
4. Phân biệt **nơi lỗi được quan sát** với **nguyên nhân gốc**; tránh khẳng định nguyên nhân chỉ vì hai biểu đồ biến động cùng lúc.
5. Dùng trace ID, span hierarchy, status/outcome, logs và deployment events để kiểm chứng chuỗi nhân quả của một request hoặc asynchronous workflow.
6. Dựng, cập nhật và đặt độ tin cậy cho dependency graph từ tracing, service discovery, cấu hình triển khai và telemetry hạ tầng.
7. Phân tích các mẫu lỗi như downstream timeout, retry amplification, connection pool exhaustion, queue lag, split-brain và shared infrastructure failure.
8. Thiết kế dashboard, alert routing, runbook và diễn tập incident response theo đồ thị phụ thuộc, với kết luận dựa trên bằng chứng.
9. Biết giới hạn của service map tự sinh: trace sampling, missing instrumentation, edge ẩn, async causality, version/config drift và dữ liệu không đầy đủ.

Các tên service, truy vấn, dữ liệu và cấu hình bên dưới chỉ mang tính minh họa. Với hệ thống thật, cần căn cứ vào hạ tầng quan sát, phiên bản thư viện, chính sách SLO và phương thức giao tiếp đang dùng.

## 2. Vấn đề: một lỗi ở cuối chuỗi hiện ra ở đầu chuỗi

Xét hệ thống đặt hàng:

~~~text
Web / Mobile
    │
    ▼
API Gateway
    │
    ▼
Order Service
    ├──► Inventory Service ──► Inventory Database
    │
    ├──► Payment Service ────► Payment Provider
    │
    ├──► Order Database
    │
    └──► Event Broker ──► Notification Worker ──► Email Provider
~~~

Người dùng báo: “Thanh toán mãi không xong”. Dashboard Gateway cho thấy `POST /checkout` p99 tăng lên 12 giây. Log của Order nói request bị timeout. Nhưng điều đó **không chứng minh Order là nguyên nhân gốc**:

- Payment Provider có thể phản hồi chậm, khiến Payment Service giữ HTTP connections.
- Payment Service có thể sử dụng connection pool quá nhỏ.
- Inventory Database có thể đang bị khóa, khiến giữ hàng chậm.
- Gateway có thể retry vào Order, làm tải tăng gấp nhiều lần.
- Một triển khai cấu hình timeout mới có thể khiến mọi lời gọi chờ quá lâu.
- IDP/JWKS hoặc DNS có thể lỗi ở nhiều service cùng lúc.

Nếu chỉ “restart Order” theo triệu chứng thấy được, có thể làm mất thêm in-flight requests, khuếch đại retry và kéo dài sự cố.

**Cách chẩn đoán theo đồ thị:** bắt đầu từ hành trình nghiệp vụ bị ảnh hưởng, lần theo các dependency thực sự nằm trên đường đi của request hoặc event, tìm điểm sớm nhất nơi hành vi bắt đầu lệch chuẩn, rồi kiểm chứng bằng dữ liệu độc lập trước khi xử lý.

## 3. Định nghĩa dependency graph

Một dependency graph có thể ký hiệu:

\[
G=(V,E)
\]

Trong đó:

- **V (vertices/nodes):** các thành phần, ví dụ Gateway, Order, Payment, Postgres, Kafka, Redis, IAM, third-party API.
- **E (edges):** quan hệ phụ thuộc hoặc lời gọi, ví dụ Order gọi Payment qua HTTP, Payment ghi DB, Notification consume Kafka.
- **Hướng cạnh:** trong bài này quy ước `A → B` nghĩa là **A phụ thuộc hoặc gọi B**. Vì vậy B là **downstream** của A và A là **upstream** của B.
- **Thuộc tính cạnh:** giao thức, operation, criticality, timeout, retry policy, failure semantics, region/AZ, traffic/error/latency và độ tin cậy của bằng chứng.
- **Thuộc tính node:** owner, môi trường, phiên bản, SLO, saturation, deploy/config, tình trạng health, dữ liệu phụ thuộc.

Ví dụ:

~~~text
Checkout Journey
        │
        ▼
Gateway ──HTTP──► Order ──HTTP──► Payment ──HTTP──► Provider
                      │
                      ├─SQL────► Order DB
                      │
                      └─HTTP───► Inventory ──SQL──► Inventory DB
~~~

Một câu hỏi quan trọng:

> Nếu Payment Provider lỗi, **những node upstream nào có thể bị ảnh hưởng**, và những user journeys nào thực sự phụ thuộc vào Provider ở nhánh bắt buộc?

Tìm các node có đường đi từ chúng đến Provider (reverse reachability), nhưng sau đó còn phải xét fallback, caching, feature flags, routing và mức độ criticality. **Có cạnh phụ thuộc không đồng nghĩa mọi request đều bị lỗi khi downstream hỏng**.

### 3.1. Dependency graph khác call graph và architecture diagram

| Biểu diễn | Đối tượng | Mục đích |
| --- | --- | --- |
| Architecture diagram | Ranh giới module/service, thành phần hạ tầng theo thiết kế | Hiểu cấu trúc dự định |
| Runtime service map | Service/endpoint gọi nhau dựa trên quan sát | Thấy quan hệ thực đã chạy trong cửa sổ dữ liệu |
| Distributed trace graph | Span và quan hệ parent/child/link của từng execution | Tìm đường đi, thời gian và lỗi của request cụ thể |
| Static call graph | Function/class/module gọi nhau trong code | Phân tích luồng code |
| Dependency graph vận hành | Node/edge có criticality, SLO, topology và evidence | Phân tích blast radius, nguyên nhân và ưu tiên xử lý |
| CMDB/service catalog | Ownership, tài nguyên, version, contact, docs | Tra cứu trách nhiệm và runbook |

Sơ đồ kiến trúc có thể chứa cạnh “theo thiết kế” nhưng không có traffic trong ngày hôm nay. Runtime map có thể bỏ sót một dependency chỉ được gọi lúc đêm hoặc lúc fallback. Để vận hành đáng tin, cần **phối hợp nhiều nguồn** và ghi độ tươi của thông tin.

### 3.2. Phân biệt các loại cạnh

- **Synchronous request:** Order gọi Payment và đợi response. Lỗi downstream có thể tác động trực tiếp request latency/availability.
- **Asynchronous message:** Order phát event, Notification xử lý sau. HTTP request ban đầu có thể trả 202 thành công trong khi notification bị trễ.
- **Data dependency:** service đọc/ghi DB, object storage hoặc cache. Lỗi không nhất thiết là HTTP 5xx.
- **Control/config dependency:** DNS, secrets manager, IAM, certificate, service discovery. Có thể chỉ ảnh hưởng lúc khởi động, token refresh hoặc rotate key.
- **Scheduled/batch dependency:** job chạy mỗi đêm; quan hệ không hiển thị trong trace giờ cao điểm.
- **Fallback dependency:** cache/alternate provider chỉ được gọi khi đường chính lỗi.
- **Deployment/build dependency:** service dùng chung một release, image base hoặc feature flag; một lỗi cấu hình có thể ảnh hưởng đồng thời nhiều node mà không có lời gọi runtime giữa chúng.

## 4. Hướng cạnh và phân tích upstream/downstream

Quy ước `A → B` là “A gọi/phụ thuộc B”:

~~~text
Gateway → Order → Payment → External Provider
                ↘ Inventory → Inventory DB
~~~

Khi **Payment** hỏng:

- **Downstream từ Payment:** External Provider; đây là những thành phần Payment cần để hoàn tất thao tác.
- **Upstream tới Payment:** Order, Gateway và user journey checkout; chúng có thể bị ảnh hưởng gián tiếp.
- **Sibling dependency:** Inventory; nó không bắt buộc hỏng nhưng có thể nhận thêm tải vì Order retry toàn bộ request.

Tìm nguồn gây lỗi khác với tìm phạm vi ảnh hưởng:

- **Root-cause candidates:** lần theo hướng phụ thuộc từ node có triệu chứng tới những dependency/edges bất thường.
- **Blast radius:** từ node nghi lỗi, lần theo **cạnh ngược** để tìm upstream consumers và user journeys phụ thuộc.
- **Recovery verification:** kiểm tra cả node nguồn lẫn upstream journeys, không chỉ nhìn node vừa sửa có `up=1`.

Một nhầm lẫn phổ biến: thấy tất cả upstream nodes báo 5xx rồi kết luận “mọi service đều hỏng độc lập”. Một database hoặc Provider chung có thể tạo lỗi lan rộng.

## 5. Đồ thị không chỉ có service: phải chứa tài nguyên chia sẻ

Ví dụ:

~~~text
                ┌──► Catalog Service ──┐
Gateway ────────┤                      ├──► Shared Redis
                └──► Order Service ────┘
                           │
                           └────────────► Shared PostgreSQL
~~~

Khi Redis lỗi, Catalog và Order cùng tăng latency. Nếu service map chỉ chứa HTTP edges, không thể thấy nguyên nhân chung vì Redis không được instrument như một service HTTP.

Nên biểu diễn thêm node loại:

- Database cluster / writer / replica.
- Cache cluster và keyspace/tenant nếu có ý nghĩa vận hành.
- Broker/topic/queue/consumer group.
- External provider/API/quota.
- DNS, IdP, Secrets Manager, certificate authority.
- Network zone, region, node group hoặc ingress.
- Object storage, blob/container và CDN.
- Shared library/config release/feature flags khi phân tích sự cố thay đổi đồng thời.

Không cần mô hình hóa mọi file và function. Mức hạt nên đủ cho quyết định vận hành và không vượt năng lực duy trì metadata.

## 6. Phụ thuộc bắt buộc, tùy chọn và có thể suy giảm

Một cạnh nên có criticality theo từng **operation** chứ không chỉ theo service:

| Quan hệ | Operation | Vai trò | Nếu downstream hỏng |
| --- | --- | --- | --- |
| Checkout → Payment | authorize payment | Bắt buộc | Checkout không thể xác nhận thanh toán |
| Checkout → Inventory | reserve items | Bắt buộc | Không thể xác nhận giữ hàng |
| Checkout → Recommendation | related items | Tùy chọn | Bỏ recommendation nếu hợp đồng cho phép |
| Catalog → Redis | load cached product | Cache/fallback | Có thể đọc DB nhưng latency tăng |
| Order → Notification Broker | publish OrderCreated | Phụ thuộc độ bền event | Có thể dùng outbox để publish sau |
| Profile → Avatar CDN | load image | Tùy chọn | Ảnh dự phòng khi CDN lỗi |

**Không đánh đồng “bắt buộc” và “không có fallback”.** Một business workflow có thể trả trạng thái PENDING thay cho SUCCESS khi dependency chưa trả lời; điều này bảo vệ tính đúng đắn nhưng thay đổi SLI của người dùng.

Trong graph metadata có thể ghi:

~~~yaml
edge:
  caller: order-service
  callee: payment-service
  operation: authorize
  protocol: HTTP
  criticality: required
  timeoutBudgetMs: 1200
  retryPolicy: bounded-idempotent
  fallback: none
  owner: payments-team
  confidence: observed-and-declared
~~~

Thông tin này cần được cập nhật khi policy thực thay đổi; nếu chỉ là tài liệu tĩnh, dễ gây kết luận sai.

## 7. Bắt đầu từ user journey và SLO

Một incident thường được phát hiện qua triệu chứng:

- Khách hàng không checkout được.
- Đơn hàng bị tạo trùng.
- Trang catalog chậm.
- Email xác nhận tới muộn.
- Hệ thống trả 200 nhưng dữ liệu sai.
- Hệ thống trả 429 do capacity thiếu.

SLO phải mô tả điều khách hàng coi là tốt, không chỉ health của một process.

Ví dụ:

> Trong 30 ngày, ít nhất 99,9% checkout requests hợp lệ kết thúc thành công theo business contract trong 2 giây.

Một SLI minh họa:

\[
SLI_{checkout}=\frac{\#\{eligible\ checkout\ requests\ completed\ correctly\ in\ 2s\}}{\#\{eligible\ checkout\ requests\}}
\]

Nếu SLI giảm, bắt đầu điều tra tại boundary đo checkout (Gateway hoặc business operation), sau đó tìm span/edge trong graph gây chậm hoặc lỗi. Nếu chỉ có `Payment 5xx` mà checkout đã fallback hợp lệ và SLI vẫn tốt, mức ưu tiên điều tra có thể khác.

### 7.1. Không dùng health endpoint thay business SLI

`/health` trả 200 chỉ cho biết endpoint của một thành phần sẵn sàng theo kiểm tra cục bộ. Nó không chứng minh Payment được gọi thành công hay khách hàng nhận kết quả đúng.

### 7.2. Phân tích error budget

Với SLO 99,9%, phần ngân sách bad requests là 0,1%. Nếu trong cửa sổ 5 phút, bad ratio là 2% thì **burn rate minh họa**:

\[
BurnRate = \frac{2\%}{0.1\%}=20
\]

Burn rate giúp quyết định mức khẩn cấp. Không tự chuyển tỷ lệ lỗi theo request thành phút downtime; đơn vị phụ thuộc định nghĩa SLO. Khi traffic thấp, tỷ lệ cần kết hợp số request thực, thời gian và sự đầy đủ của telemetry.

## 8. Bốn tín hiệu trên từng node và edge

Đồ thị sẽ trở thành công cụ chẩn đoán khi đi kèm telemetry:

| Tín hiệu | Ở node | Ở edge A → B | Câu hỏi |
| --- | --- | --- | --- |
| **Traffic** | Inbound RPS/messages/s | Outbound attempt rate, operation mix | Có burst hoặc retry amplification? |
| **Errors** | 5xx/business bad events | Timeout, 429, response status, transport error | Lỗi phát sinh ở đâu, chỗ nào chỉ truyền lỗi? |
| **Latency** | p50/p95/p99 server duration | Client duration, queueing, connection acquire | Thời gian bị chậm trên đường nào? |
| **Saturation** | CPU, memory, in-flight, thread pool | Client pool, DB pool, queue depth/age | Tài nguyên nào đã gần cạn? |

Thêm **change events**: deployment, config, feature flags, secret rotation, network policy, database migration, autoscaling.

### 8.1. Node latency và edge latency khác nhau

Order xử lý trong 2 giây, trong đó 1,8 giây chờ Payment. CPU Order có thể thấp. Chỉ xem latency server Order sẽ gắn triệu chứng vào Order; chỉ xem CPU sẽ tưởng Order rảnh. Edge client duration và trace mới cho biết phần chờ Payment chiếm phần lớn.

### 8.2. Đếm request người dùng khác downstream attempts

Một checkout có thể tạo một request Gateway→Order nhưng ba lần Order→Payment vì retry. Nếu dựa vào outbound RPS, đồ thị có thể cho thấy Payment traffic gấp 3 lần client traffic. Đó là dấu hiệu amplification cần điều tra, không nhất thiết Payment bị bot tấn công.

### 8.3. Percentile phải đo ở boundary đúng

Không cộng p95 của Order, Payment, Inventory để ra p95 checkout. Percentile là đặc trưng phân phối và không cộng tuyến tính. Đo checkout p95 ở Gateway/business boundary; dùng trace của những request chậm để thấy thành phần đóng góp.

## 9. Distributed tracing: bằng chứng theo từng request

Một trace thể hiện đường đi và thời gian của một execution:

~~~text
traceId=abc123
Gateway POST /checkout                 2200 ms
└── Order POST /checkout               2150 ms
    ├── Inventory POST /reserve          85 ms
    ├── Payment POST /authorize        1800 ms
    │   └── PaymentProvider HTTP       1750 ms
    └── OrderDB INSERT                   30 ms
~~~

Từ trace này, **PaymentProvider HTTP** là một ứng viên chẩn đoán vì chiếm phần lớn thời gian. Chưa thể kết luận Provider là root cause nếu đoạn chờ thực tế là connection pool của Payment hoặc DNS lookup. Cần các span con/metrics của client pool, network và status để tách.

### 9.1. Những thuộc tính trace hữu ích

- Trace ID, span ID, parent span ID.
- Service name, operation/route template, span kind CLIENT/SERVER/PRODUCER/CONSUMER.
- Start/end timestamp, duration, error/status category.
- Target peer/service, protocol, status code, timeout/retry attempt khi được instrument.
- Deployment version, environment, region/AZ trong resource attributes.
- ID nghiệp vụ hoặc idempotency reference ở hệ thống log có phân quyền nếu thực sự cần.

Không gắn raw Authorization header, access token, password, full payload chứa PII vào span attributes. Không đưa request ID hoặc user ID thành metric label cardinality cao.

### 9.2. Context propagation

Để nối spans giữa Gateway, Order, Payment và Provider, các lời gọi cần truyền context qua HTTP/gRPC headers hoặc message metadata với cơ chế được kiểm soát (ví dụ W3C Trace Context).

Nếu một service không propagate trace context, graph có thể bị đứt:

~~~text
Trace A: Gateway → Order
Trace B: Payment → Provider   (mất quan hệ)
~~~

Lúc đó không được suy ra Payment không liên quan; có thể do instrumentation thiếu. Dùng HTTP client metrics, service discovery, log correlation hoặc config để bổ sung bằng chứng.

### 9.3. Sampling là một nguồn mù

Trace sampling giúp giảm lưu trữ nhưng có thể bỏ các request lỗi hiếm hoặc chỉ lưu một phần span. Runtime dependency graph tự sinh từ trace có thể thiếu cạnh ít xuất hiện.

Không suy ra RPS/error ratio trực tiếp từ một tập traces lấy mẫu nếu không có cách hiệu chỉnh sampling phù hợp. Counters và histograms tổng hợp từ toàn lưu lượng thường đáng tin hơn để tính SLI.

### 9.4. Asynchronous span links

Với message broker, producer và consumer có thể không nằm trong một parent/child tree trực tiếp. Một event được xử lý sau nhiều phút, fan-out tới nhiều consumer hoặc được retry.

Cần:

- Operation/event ID ổn định.
- Producer/consumer spans hoặc span links theo khả năng stack.
- Enqueue timestamp, dequeue timestamp, processing duration.
- Delivery count, retry/ack/DLQ.
- Correlation giữa user request và business operation.

Không coi HTTP request ban đầu thành công 202 là toàn workflow đã hoàn thành.

## 10. Thu thập và duy trì dependency graph

Không có nguồn duy nhất hoàn hảo. Một graph tốt thường ghép nhiều nguồn:

### 10.1. Từ OpenTelemetry traces

Instrument inbound/outbound calls để trích ra các cặp (caller, callee, operation) cùng latency, status và tần suất. Đây là nguồn hữu ích cho **quan hệ đã hoạt động** trong thời gian quan sát.

**Giới hạn:** chỉ thấy request được trace, có thể thiếu async, DB, source ngoài hoặc các đường cold/fallback.

### 10.2. Từ service discovery và orchestrator

Kubernetes Services, EndpointSlices, ingress routes, mesh config, DNS names và deployment manifests cho biết **đường định tuyến có thể xảy ra**.

**Giới hạn:** việc có route không chứng minh app thực đã sử dụng; một Service có thể không có traffic hoặc endpoint không Ready.

### 10.3. Từ code/config

HTTP client base URLs, gRPC stubs, environment variables, topic subscriptions, DB connection strings, scheduled jobs và declared dependency files.

**Giới hạn:** có thể là cấu hình chưa bật, feature flag tắt hoặc dependency chỉ sử dụng ở một phiên bản.

### 10.4. Từ service catalog và owner

CMDB/service catalog ghi team ownership, criticality, contact, runbook, SLO và environment. Dùng để liên hệ đúng đội và gắn mức ảnh hưởng.

**Giới hạn:** dữ liệu quản trị có thể cũ; cần quy trình cập nhật theo deploy hoặc owner xác nhận.

### 10.5. Gắn thời gian và độ tin cậy

Một cạnh có thể có metadata:

~~~json
{
  "caller": "order-service",
  "callee": "payment-service",
  "operation": "authorize",
  "protocol": "http",
  "evidence": ["trace", "http-client-metric", "config"],
  "firstSeen": "2026-11-10T10:00:00Z",
  "lastSeen": "2026-11-12T02:00:00Z",
  "environment": "production",
  "confidence": "high"
}
~~~

Một cạnh được thấy lần cuối hai tháng trước không nên được đối xử giống cạnh được quan sát ngay trong incident. Nhưng cũng không xóa cạnh ít gọi chỉ vì 24 giờ không có trace; có thể là đường chỉ chạy lúc lỗi hoặc theo lịch.

### 10.6. Phiên bản và môi trường

Graph cần được lọc theo production/staging, region, service version hoặc feature flag khi dữ liệu cho phép. Nếu Order V1 gọi Inventory trực tiếp còn V2 đi qua Aggregator, một graph trộn version dễ tạo kết luận không đúng cho incident đang xảy ra.

## 11. Mô hình một node/edge cho vận hành

Một node nên có:

~~~yaml
node:
  id: payment-service
  kind: application
  environment: production
  owner: payments-team
  region: region-a
  runbook: payments-incident-playbook
  criticalJourneys:
    - checkout
  metrics:
    - inbound_rps
    - failure_ratio
    - p95_latency
    - active_connections
  recentChange:
    version: "2.4.1"
    deployedAt: "2026-11-12T01:40:00Z"
~~~

Một edge nên có:

~~~yaml
edge:
  from: payment-service
  to: external-provider
  operation: authorize
  criticality: required
  protocol: HTTPS
  timeoutMs: 1500
  maxRetries: 1
  requestRate: "observed-at-runtime"
  errorRatio: "observed-at-runtime"
  latencyP95: "observed-at-runtime"
  upstreamImpact:
    - checkout
~~~

Các trường telemetry động phải lấy từ hệ thống metrics/traces theo cùng thời điểm điều tra, không cố lưu số liệu runtime cố định trong YAML.

## 12. Quy trình chẩn đoán từ SLO đến giả thuyết

Một quy trình thực dụng gồm các pha:

### Pha 1 — Xác nhận symptom và phạm vi

Trả lời:

- Hành trình nào lỗi? `POST /checkout`, catalog hay notifications?
- Khi nào bắt đầu? Ảnh hưởng toàn region hay chỉ tenant/zone/version?
- Có bao nhiêu request lỗi, p95/p99 tăng bao nhiêu?
- Error-budget burn rate và business impact ở mức nào?
- Telemetry có bị thiếu? Có mất scrape/traces/logs không?

Không mở graph trước rồi tìm node đang màu đỏ một cách tùy ý; hãy dùng **user impact** làm điểm khởi đầu.

### Pha 2 — Đặt symptom tại node/edge tương ứng

Bắt đầu từ boundary như Gateway→Order, chọn những tuyến request hoặc business operations bị ảnh hưởng. Đưa chúng lên graph và tách:

- Tăng traffic?
- Tăng error?
- Tăng latency?
- Tăng saturation?
- Có recent deployment/config change?

Đối chiếu với những journey đang bình thường để thu hẹp phạm vi.

### Pha 3 — Đi xuống graph có định hướng

Theo cạnh **từ caller đến callee**, ưu tiên những cạnh:

1. Nằm trong critical path của user journey.
2. Có error/latency thay đổi trước hoặc đồng thời với triệu chứng.
3. Có in-flight, queue, pool hoặc dependency bottleneck.
4. Có tần suất request đủ để giải thích tác động.
5. Có evidence từ trace hoặc log và gần thời điểm incident.

Nếu Order p99 tăng nhưng Payment edge bình thường còn Inventory p99 tăng rõ, chuyển điều tra sang Inventory và DB. Không kiểm tra tất cả 100 services với ưu tiên ngang nhau.

### Pha 4 — Phân biệt nguồn và điểm truyền lỗi

Một node upstream có thể chỉ truyền lỗi từ downstream:

~~~text
Provider trả 503
    ↓
Payment trả 503
    ↓
Order trả 502
    ↓
Gateway trả 502
~~~

Trong đồ thị, tất cả các node có lỗi. Nhưng **Provider** là một ứng viên nguồn phát chuỗi lỗi; Payment, Order và Gateway đang phản ứng theo contract (có thể còn có lỗi retry policy khiến tác động nặng hơn).

Nếu Payment đổi cấu hình timeout sai ngay trước incident, nguyên nhân gốc có thể ở Payment dù Provider còn khỏe. Đọc deployment/config change để phân biệt.

### Pha 5 — Kiểm chứng giả thuyết

Với mỗi ứng viên, tìm bằng chứng:

- Metrics per edge: timeout/5xx/client duration.
- Trace từ request lỗi và request thành công cùng thời điểm.
- Log có correlation IDs, error class và dependency metadata.
- Database/broker/infra events hoặc provider status.
- Recent deployment, feature flag, secret rotation.
- Synthetic request có kiểm soát hoặc test an toàn.

Chỉ hành động dựa trên mối liên hệ đã đủ tin cậy; trong tình huống nghiêm trọng có thể triển khai biện pháp giảm tác động trước khi có root cause cuối cùng.

### Pha 6 — Giảm tác động và phục hồi

Có thể:

- Rollback canary/config mới.
- Chuyển traffic khỏi vùng/replica lỗi.
- Giới hạn retry và concurrency.
- Rate limit/load shed để bảo vệ downstream.
- Dùng fallback/degraded mode hợp lệ.
- Khôi phục DB/broker/identity dependency.
- Tăng capacity nếu bottleneck thực là capacity và dependency chịu được.

Sau can thiệp, **xác nhận user-facing SLI**, không chỉ một metric của node nguồn.

### Pha 7 — Ghi nhận và cập nhật graph

Đưa vào incident timeline, bằng chứng, giả thuyết đã loại, root cause cuối cùng, propagation path, blast radius, khuyến nghị phòng ngừa và owner.

Graph cũng cần cập nhật nếu phát hiện dependency ẩn hoặc chính sách fallback khác tài liệu.

## 13. Một cách xếp hạng các ứng viên gây lỗi

Khi graph lớn, cần cách ưu tiên node. Một phương pháp có thể dùng **score để hỗ trợ triage**, không tự khẳng định root cause:

~~~text
candidate_score(v) =
    w1 × anomaly_strength(v)
  + w2 × temporal_precedence(v)
  + w3 × critical_path_relevance(v)
  + w4 × downstream_to_upstream_consistency(v)
  + w5 × recent_change_relevance(v)
  − w6 × telemetry_uncertainty(v)
~~~

Ý nghĩa:

- **Anomaly strength:** error/latency/saturation của node hoặc edge lệch baseline bao nhiêu.
- **Temporal precedence:** biến động có xuất hiện trước triệu chứng upstream, trong giới hạn clock skew/metric delay.
- **Critical path relevance:** node có thực sự phục vụ journey đang lỗi không.
- **Propagation consistency:** lỗi downstream có khả năng giải thích lỗi upstream theo contract không.
- **Recent change:** deployment, config hoặc hạ tầng biến động sát incident.
- **Uncertainty:** data bị sampling, thiếu instrumentation, metric không có đủ request hoặc graph stale.

Trọng số cần hiệu chỉnh theo dữ liệu vận hành và đánh giá của con người. Một score cao không chứng minh quan hệ nhân quả. Đừng coi một sự kiện deploy gần thời điểm outage là nguyên nhân nếu không có bằng chứng hỗ trợ.

### 13.1. Điểm đỏ sâu nhất không nhất thiết là root cause

Có thể DB bị bão hòa vì Gateway tạo retry storm sau một cấu hình timeout sai. DB là điểm có saturation cao nhất, nhưng **điều chỉnh timeout/retry tại Gateway** mới có thể là thay đổi khởi phát.

Cần phân biệt:

- **Trigger:** thay đổi hoặc sự kiện bắt đầu chuỗi.
- **Root cause:** nguyên nhân hệ thống cốt lõi khiến sự cố xảy ra hoặc lan rộng.
- **Contributing factors:** retry vô hạn, pool chung, thiếu backpressure, headroom thấp.
- **Symptom:** biểu hiện tại service/user journey.
- **Mitigation:** hành động giảm tác động ngay, có thể không sửa triệt để root cause.

## 14. Mẫu lỗi A: Payment Provider chậm làm checkout tăng latency

### 14.1. Đồ thị

~~~text
Gateway → Order ──► Inventory ──► Inventory DB
               └──► Payment ───► External Provider
~~~

### 14.2. Tín hiệu

| Vị trí | Quan sát |
| --- | --- |
| Gateway checkout | p95 từ 500 ms lên 2,4 giây |
| Order inbound | RPS ổn, in-flight tăng |
| Order→Inventory | p95 vẫn 80 ms, lỗi thấp |
| Order→Payment | p95 từ 250 ms lên 1,9 giây |
| Payment→Provider | p95 1,8 giây, timeout tăng |
| Payment CPU | Thấp hoặc bình thường |
| Payment client pool | Pending connections tăng |

### 14.3. Giả thuyết

Provider có thể phản hồi chậm; cũng có thể Payment đang thiếu connection và thời gian chờ nằm **trước** khi request đi ra provider. Cần trace có các span như connection acquisition, DNS, TLS và HTTP wait nếu instrumentation hỗ trợ.

### 14.4. Hành động

- Kiểm tra provider status/edge errors.
- Xem latency theo upstream/downstream và connection pool pending.
- Giảm retry amplification, áp dụng timeout và circuit/bulkhead đúng policy.
- Nếu provider chậm, có thể chuyển sang provider dự phòng hoặc trả trạng thái pending/fallback **chỉ nếu contract hỗ trợ**.
- Theo dõi checkout SLI, không chỉ Payment p95.

**Sai lầm:** scale Order 5 lần chỉ vì Order latency cao; Payment/Provider mới là nơi tạo thời gian chờ.

## 15. Mẫu lỗi B: Database chậm làm nhiều service đồng thời lỗi

### 15.1. Đồ thị

~~~text
Catalog Service ──► Shared PostgreSQL
Order Service ─────► Shared PostgreSQL
Profile Service ───► Shared PostgreSQL
~~~

Đồng thời Catalog, Order và Profile tăng p99. Nếu chỉ xem application graph, chúng không có edge giữa nhau. Node DB chung giải thích tương quan.

### 15.2. Dấu hiệu

- DB active/pending connections tăng.
- Slow queries hoặc lock waits tăng.
- Transaction duration tăng.
- CPU ở các app có thể vẫn thấp vì thread đang chờ.
- Số kết nối tăng sau HPA scale-up hoặc deploy.
- Query mới hoặc migration tạo lock.

### 15.3. Kiểm chứng

- Xem DB server metrics, query/lock/connection pools.
- Đối chiếu timeline deployment, traffic, HPA và migration.
- Xác định truy vấn/top transaction là bottleneck, không mặc định “DB quá yếu”.
- Dùng trace spans SQL để map journey nào chịu tác động.

### 15.4. Giảm tác động

Tùy nguyên nhân: rollback query/config, hạn concurrency, giảm pool connections, cải thiện index/lock strategy, cache hợp lệ, scale database hoặc phân tách workload. **Tăng app replicas có thể làm DB nặng hơn.**

## 16. Mẫu lỗi C: Retry storm lan từ Gateway tới downstream

### 16.1. Kịch bản

Gateway có 1.000 RPS từ client. Một thay đổi cấu hình khiến nó retry request vào Order hai lần khi chậm. Order cũng retry Payment. Các request downstream có thể tăng gấp nhiều lần dù user traffic không đổi.

~~~text
Client 1000 RPS
    │
    ▼
Gateway retries
    │  up to 3000 Order attempts
    ▼
Order retries Payment
    │  potentially > 3000 Payment attempts
    ▼
Payment / Provider
~~~

Không lấy các con số này làm prediction chắc chắn: số attempt thực phụ thuộc tỷ lệ lỗi, deadline, circuit state và policy tại mỗi tầng.

### 16.2. Tín hiệu quan trọng

- Offered RPS tại Gateway **không tăng**.
- Outbound attempts Gateway→Order tăng.
- Payment attempt rate tăng nhanh hơn Order business operation rate.
- CPU/DB pool, in-flight và timeout tăng.
- Nhiều request cùng operation ID hoặc idempotency key tạo nhiều attempts.

### 16.3. Root cause và contributing factors

Một dependency chậm ban đầu có thể là trigger; retry không có budget là yếu tố khuếch đại. Cần phân biệt “Provider hỏng” với “Gateway và Order biến lỗi nhỏ thành tải cực lớn”.

### 16.4. Hành động

Giới hạn retries theo deadline và idempotency, tăng backoff/jitter, dùng circuit breakers/bulkheads, rate limit và load shedding. Với operation ghi, không retry mù sau timeout vì kết quả có thể chưa biết; dùng idempotency và reconciliation.

## 17. Mẫu lỗi D: Hàng đợi chậm nhưng API vẫn trả 202

### 17.1. Đồ thị bất đồng bộ

~~~text
Order API → Order DB
         └→ Event Broker → Billing Worker → Payment Provider
                         └→ Email Worker → Mail Provider
~~~

Gateway trả 202 nhanh, 5xx gần 0. Nhưng hóa đơn không được gửi hoặc thanh toán đối soát muộn.

### 17.2. Tín hiệu

- Producer publish rate và broker acceptance.
- Consumer processed success rate.
- Consumer lag, queue depth, oldest message age.
- Retry/DLQ rate.
- Processing duration, external provider latency.
- Event ID/operation ID để nối đầu request với completion.

### 17.3. Phân tích graph

Từ journey “nhận hóa đơn trong 60 giây”, đi qua Order→Broker→Billing Worker. SLI phải đo **enqueue-to-completion**, không chỉ thời gian HTTP trả 202.

Nếu queue depth tăng khi consumer count không đổi, có thể cần scale worker. Nhưng nếu Payment Provider liên tục 429, scale worker có thể gây thêm overload. Xem downstream dependency trước khi tăng concurrency.

### 17.4. Bẫy eventual consistency

Request vừa ghi DB đã trả 202, consumer xử lý sau. Một read-after-write test có thể thấy trạng thái cũ trong một khoảng hợp lệ. Phải dùng trạng thái PENDING/COMPLETED rõ ràng, deadline và SLI riêng; không gọi mọi chậm trễ là lỗi ngay tức thì.

## 18. Mẫu lỗi E: Identity/JWKS gặp sự cố

### 18.1. Đồ thị ẩn

~~~text
Gateway ──► Identity Provider / JWKS
Order ─────► Identity Provider / JWKS (ở một số đường xác minh)
Admin ─────► Identity Provider / JWKS
~~~

Nếu key rotation hoặc config audience sai, nhiều service trả 401/403 cùng lúc, trong khi CPU và DB đều bình thường.

### 18.2. Điều tra

- Token issuer, audience, key ID đã được xác minh.
- JWKS endpoint reachability, cache expiry, key rollover.
- Deployment/config/secret change.
- Error classes authn/authz theo version/region.
- Có sự khác biệt giữa token mới và session/token cũ không?

Đừng vô hiệu hóa kiểm tra chữ ký hoặc mở authn fail-open để “khôi phục availability”. Giảm tác động phải giữ an toàn danh tính; có thể rollback trust config lỗi hoặc khôi phục IdP/JWKS theo runbook.

### 18.3. Tại sao graph từ tracing có thể bỏ sót?

JWT có thể được xác minh **offline** với JWKS cache; một request bình thường không gọi IdP. Khi cache hết hạn, dependency mới hoạt động và gây outage. Nếu graph chỉ học từ 5 phút trace lúc khỏe, cạnh này có thể không tồn tại. Cần thêm declared/config dependencies và test failure path.

## 19. Mẫu lỗi F: Deployment gây correlated failure

### 19.1. Tình huống

Cùng một base library được nâng version cho ba service. Các service bắt đầu lỗi sau deploy vài phút. Trên runtime graph, chúng không có quan hệ gọi nhau, nhưng có **dependency dùng chung về code/config**.

### 19.2. Đưa change graph vào điều tra

~~~text
Shared library version X
    ├──► Gateway version 4
    ├──► Order version 9
    └──► Payment version 3
~~~

Hoặc:

~~~text
Feature flag checkout-strict-mode
    ├──► Order
    └──► Payment
~~~

Khi nhiều node biến động gần cùng thời điểm, kiểm tra release manifest, config repo, flag rollout và secrets rotation. Đừng mặc định database là nguồn chỉ vì nhiều service có DB metrics thay đổi cùng lúc.

### 19.3. Cảnh giác post hoc

“Sự cố xảy ra sau deploy” là tín hiệu ưu tiên, không là bằng chứng tuyệt đối. Xác nhận bằng canary versus control, rollback có kiểm soát, traces/error types và reproducible scenario.

## 20. Mẫu lỗi G: Sự cố theo Availability Zone

### 20.1. Đồ thị topology

~~~text
Region
├── AZ-A ── Order A, Payment A, DB writer
├── AZ-B ── Order B, Payment B, DB standby
└── AZ-C ── Order C, Payment C, DB standby
~~~

Mất AZ-A làm nhiều service NotReady và database cần failover. Nếu graph chỉ có service-level node, tổng RPS có thể giảm nhưng không biết nơi xảy ra lỗi. Cần overlays về zone/node/region.

### 20.2. Phân tích

- Nodes/Pods Ready theo AZ.
- Endpoint health và load balancer route weights.
- Cross-zone traffic và capacity còn lại.
- DB writer election/failover, replication lag.
- Retry/connection resets khi chuyển zone.
- SLI theo region/AZ/tenant, nếu dữ liệu đủ tin cậy.

Không kết luận đã phục hồi chỉ vì LB chuyển request: DB writer và queue có thể chưa khôi phục, và các AZ còn lại có thể không đủ headroom.

## 21. Mẫu lỗi H: Cache lỗi tạo tải dây chuyền vào DB

### 21.1. Đồ thị

~~~text
Catalog → Redis Cache
        ↘ Product Database
~~~

Khi Redis lỗi hoặc cache hit rate giảm mạnh, Catalog fallback DB. Traffic client không đổi nhưng DB QPS tăng gấp nhiều lần.

### 21.2. Kiểm chứng

- Redis error, hit/miss, eviction, response time.
- Catalog→DB RPS và query latency.
- DB pool pending, CPU/I/O.
- Trạng thái warm-up sau rollout.
- TTL và các key hot bị invalidation.

### 21.3. Hành động

Chống cache stampede, giới hạn concurrency/rate, phục hồi Redis, preload dữ liệu nóng có kiểm soát và tối ưu DB. Không mặc định tăng Catalog replicas sẽ giải quyết latency.

## 22. Mẫu lỗi I: Partial failure và fallback che triệu chứng

Order trả HTTP 200 nhờ cache/fallback nhưng dữ liệu về tồn kho đã cũ. Dashboard 5xx không tăng, SLO availability kỹ thuật nhìn vẫn tốt, trong khi đơn đặt hàng bị hủy sau đó.

Cần model hóa:

- **Primary dependency:** Inventory service.
- **Fallback dependency:** Cache hoặc read replica.
- **Outcome:** SUCCESS, DEGRADED, PENDING, UNKNOWN, FAILURE.
- **Data freshness:** thời gian dữ liệu được tạo, lag và deadline hợp lệ.

Một dependency graph có thể hiển thị primary edge đỏ, fallback edge xanh; user journey vẫn có thể bị coi là bad nếu fallback không đáp ứng nghiệp vụ. **Hệ thống observability phải đo điều khách hàng cần, không chỉ HTTP status.**

## 23. Cách xây dashboard từ graph

### 23.1. Lớp 1 — user journey/SLO

- Checkout availability và latency SLI.
- Error budget burn.
- RPS, 5xx/429, business failures.
- Phân đoạn theo operation/region/tenant class khi có ý nghĩa.

### 23.2. Lớp 2 — dependency graph có trọng số

- Nodes hiển thị health và SLO status.
- Edges hiển thị RPS/error ratio/p95 hoặc một biến nổi bật.
- Phân biệt required/optional và sync/async edges.
- Đánh dấu deployed version hoặc config change.
- Lọc theo incident time window và environment.

### 23.3. Lớp 3 — chi tiết node/edge

- Client/server latency tách biệt.
- HTTP error types, retry counts, timeout rate.
- Connection pool, thread pool, queue and DB metrics.
- Representative traces: success, slow, error.
- Logs có correlation IDs và runbook liên quan.

### 23.4. Lớp 4 — owner và hành động

- Service/team owner.
- On-call và escalation path.
- Known failure modes.
- Last deploy/config change.
- Biện pháp mitigation được phê duyệt.
- Incident timeline và evidence link.

Nếu dashboard chỉ tô màu đỏ một node vì CPU cao mà không cho biết user journey và dependency relation, nó là sơ đồ trạng thái chứ chưa phải công cụ chẩn đoán.

## 24. Một số query PromQL minh họa

Tên metric/label phải kiểm tra theo exporter thực tế. Những ví dụ dưới đây giả sử HTTP server/client metrics kiểu Micrometer/Prometheus và labels đã được hệ thống xác nhận.

### 24.1. RPS cho từng service

~~~promql
sum by (job) (
  rate(http_server_requests_seconds_count{
    namespace="production"
  }[5m])
)
~~~

Không cộng Gateway RPS và service RPS rồi gọi đó là số request người dùng: cùng một request được đếm ở nhiều ranh giới.

### 24.2. Server 5xx ratio

~~~promql
sum by (job) (
  rate(http_server_requests_seconds_count{
    namespace="production",
    status=~"5.."
  }[5m])
)
/
clamp_min(
  sum by (job) (
    rate(http_server_requests_seconds_count{
      namespace="production"
    }[5m])
  ),
  1e-9
)
~~~

Đây chỉ là **HTTP 5xx ratio** chứ chưa bao hàm business failure, deadline miss hoặc partial success. Tử/mẫu phải cùng tập request đủ điều kiện.

### 24.3. Client p95 theo dependency

~~~promql
histogram_quantile(
  0.95,
  sum by (le, client_name) (
    rate(http_client_requests_seconds_bucket{
      job="order-service"
    }[5m])
  )
)
~~~

Tên `http_client_requests_seconds_bucket` và label `client_name` minh họa, không bảo đảm tồn tại trong mọi phiên bản. Histogram phải được instrument, có bucket phù hợp, và aggregation giữ `le`.

### 24.4. Retry amplification

Giả sử đã instrument counters:

~~~promql
sum(rate(dependency_attempts_total{
  caller="order-service",
  callee="payment-service"
}[5m]))
/
clamp_min(
  sum(rate(business_operations_total{
    operation="checkout"
  }[5m])),
  1e-9
)
~~~

Tỷ lệ lớn hơn baseline có thể do retries hoặc số lời gọi downstream trên một operation tăng. Cần xét cả đường logic hợp lệ, batch và fallback; không kết luận nguyên nhân chỉ bằng một tỷ lệ.

### 24.5. Saturation DB pool

~~~promql
sum by (pool, instance) (
  hikaricp_connections_pending{
    job="order-service"
  }
)
~~~

Metric HikariCP có thể khác tùy registry. Khi connection pending tăng, cần xem acquisition latency, active/max, DB locks và traffic, không tự kết luận “tăng DB pool là đủ”.

### 24.6. Missing telemetry

Exporter `up=0` hoặc metric biến mất cần được coi là **độ không chắc chắn của điều tra**. Không thể nói service không có lỗi nếu logs/traces/metrics không nhận được từ service đó.

## 25. Phác thảo thuật toán lần theo graph

Giả sử graph có adjacency list theo hướng caller→callee:

~~~text
deps["gateway"] = ["order"]
deps["order"] = ["inventory", "payment", "order-db"]
deps["payment"] = ["external-provider"]
deps["inventory"] = ["inventory-db"]
~~~

### 25.1. Tìm downstream của một symptom

Pseudocode:

~~~text
function traverseDownstream(start, deps):
    seen = Set()
    queue = [start]
    while queue not empty:
        node = queue.popFront()
        if node in seen:
            continue
        seen.add(node)
        for child in deps[node]:
            queue.pushBack(child)
    return seen
~~~

Đây là tập node cần cân nhắc chẩn đoán, không phải kết quả root cause. Phải lọc theo **operation, thời gian và runtime evidence**, nếu không sẽ mở rộng quá mức.

### 25.2. Tìm upstream blast radius

Đảo cạnh:

~~~text
reverse["payment"] = ["order"]
reverse["order"] = ["gateway"]
reverse["external-provider"] = ["payment"]
~~~

Đi từ node nghi lỗi theo reverse edges đến những caller/user journeys có thể bị ảnh hưởng. Khi có cycle, dùng `seen` để tránh lặp vô hạn.

### 25.3. Lọc theo critical path

Với checkout, chọn only required operations:

~~~text
checkout → gateway → order → inventory → inventory-db
                            → payment → external-provider
                            → order-db
~~~

Recommendation và email có thể ở nhánh tùy chọn; không cần ưu tiên ngang Payment nếu symptom là “không thể hoàn tất checkout”.

### 25.4. Tính criticality và blast radius

Không chỉ đếm số upstream services. Một node dùng bởi 2 services phục vụ thanh toán có thể quan trọng hơn node dùng bởi 30 services ít dùng. Có thể cân theo:

- User journeys có SLO nghiêm ngặt.
- Request volume và doanh thu/giá trị nghiệp vụ.
- Thời gian phục hồi và fallback.
- Mức ảnh hưởng dữ liệu/consistency.
- Tính đa tenant/region.
- Độ tin cậy của edge.

Không lấy sơ đồ có nhiều mũi tên làm bằng chứng định lượng rủi ro nếu chưa gắn traffic và criticality.

## 26. Tương quan thời gian và độ trễ telemetry

Một vấn đề khó: mọi metric đều được tổng hợp theo cửa sổ, không ghi cùng thời điểm chính xác. Ví dụ:

~~~text
10:00:00  Payment Provider bắt đầu timeout.
10:00:15  Payment HTTP client errors tăng.
10:00:25  Order in-flight tăng.
10:00:35  Gateway p99 tăng.
10:01:00  Dashboard refresh nhận dữ liệu và vẽ đường đỏ.
~~~

Nếu latency/metrics ingestion khác nhau, biểu đồ có thể vẽ Order lỗi “sớm hơn” Provider dù thực tế ngược lại.

Cần:

- Time synchronization/clock skew awareness.
- Event occurredAt khác collector ingest time.
- Scrape interval, metric window và query step.
- Trace span timestamps và logs có correlation.
- Change annotations đúng timezone và version.
- Khả năng gián đoạn metrics pipeline khi incident.

**Temporal precedence là bằng chứng hỗ trợ**, không tự động là causality. Một network outage chung có thể làm Provider và Order lỗi gần cùng lúc mà không có cái nào gây ra cái kia.

## 27. Chẩn đoán đồ thị có cycle và fan-out

Microservices không phải lúc nào cũng tạo DAG thuần:

~~~text
A → B → C → A
~~~

Cycle có thể do callbacks, service delegation hoặc event feedback loops; nó gây khó cho retry, circuit behavior và root-cause navigation.

### 27.1. Strongly connected components

Có thể gom các node trong vòng phụ thuộc mạnh thành một nhóm khi phân tích reachability, nhưng không bỏ thông tin hướng operation thực tế. Khi sự cố trong nhóm, cần trace/edge-level metrics để phân biệt điểm khởi phát.

### 27.2. Fan-out

Một request Aggregator gọi đồng thời 10 downstream services. Một downstream chậm có thể quyết định latency toàn request nếu Aggregator chờ tất cả. Nếu chỉ yêu cầu “ít nhất 8/10” kết quả, blast radius khác.

Graph metadata nên ghi **fan-out/fan-in semantics**, parallelism, quorum, deadline và result aggregation policy. Không cộng tổng p95 từng edge để dự đoán p95 tại Aggregator.

### 27.3. Fan-in và shared node

Nhiều services cùng dùng Shared DB hoặc IdP. Khi node chung lỗi, những upstream symptoms có thể xuất hiện đồng thời. Đây là lý do graph có giá trị hơn việc xem từng dashboard service riêng lẻ.

## 28. Health propagation và chính sách sẵn sàng

Một service có nhiều dependencies:

~~~text
Order
  ├── Payment (required)
  ├── Inventory (required)
  └── Recommendations (optional)
~~~

Nếu Recommendations chết, Order có thể vẫn Ready nếu degrade hợp lệ. Nếu Payment chết, việc Order NotReady có thể khiến tất cả requests — kể cả `GET /orders` vốn không cần Payment — bị cắt. Phải xác định health theo **khả năng phục vụ và operation**, không chỉ AND tất cả dependencies.

**Liveness** nên kiểm tra process có kẹt tới mức phải restart không, không nên kiểm remote DB theo cách khiến toàn cluster restart loop. **Readiness** điều khiển endpoint eligibility nhưng cũng phải được thiết kế tránh cascading failure.

Graph có thể chỉ ra nơi dùng dependency bắt buộc theo từng route để chọn health policy phù hợp.

## 29. Kết hợp deployment events, feature flags và graph

Khi sự cố bắt đầu sau một thay đổi, cần xem:

- Service version đang phục vụ từng AZ.
- Canary weight và traffic split.
- Config diff, timeout/retry/pool settings.
- DB migration, schema version.
- Feature flag bật cho nhóm người dùng nào.
- Secret/certificate rotation.
- Node/ingress/mesh/network policy changes.

Trên graph, có thể tô dấu **node/edge bị thay đổi** trong khung thời gian incident. Nếu chỉ 10% request qua Payment V2 bị lỗi, Graph theo version giúp tránh đưa toàn bộ Payment V1 vào cùng một nhóm.

### 29.1. Phân biệt version và identity

Một service có nhiều replicas, các Pod cũ/mới chạy cùng lúc. Nếu graph gộp tất cả vào một node và p95 tăng, cần drill-down theo version/Pod/AZ để xem lỗi chỉ thuộc một release hay toàn service.

### 29.2. Change annotation không phải nguyên nhân đã chứng minh

Một deploy có thể trùng giờ với Provider outage. Sau khi rollback nếu lỗi vẫn tồn tại, phải tiếp tục điều tra. Dựa trên user impact và edge telemetry mới xác định mối liên hệ.

## 30. Triển khai instrumentation trong Java/Spring Boot

Một service Java thường có:

- Inbound HTTP server instrumentation.
- HTTP client instrumentation cho RestClient, WebClient hoặc các client khác.
- JDBC/DB instrumentation ở mức phù hợp.
- Broker producer/consumer instrumentation.
- OpenTelemetry trace propagation và exporters.
- Micrometer counters/timers/gauges cho errors, latency, pool/queue.
- Structured logs chứa trace ID nhưng không chứa secrets.

### 30.1. Định danh rõ operation

Trong metrics, route nên ở dạng template như `/orders/{id}` thay vì `/orders/123456`. Với HTTP client dependency, gắn service hoặc logical peer name có **cardinality hữu hạn**.

Không đưa per-request IDs, email, token, raw URLs hoặc SQL với dữ liệu nhạy cảm vào metric labels.

### 30.2. Một service client adapter có metric duration và outcome

Ví dụ Java minh họa:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public final class PaymentGateway {
    private final PaymentClient client;
    private final MeterRegistry registry;

    public PaymentGateway(
            PaymentClient client,
            MeterRegistry registry) {
        this.client = client;
        this.registry = registry;
    }

    public AuthorizationResult authorize(AuthorizationCommand cmd) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";
        try {
            return client.authorize(cmd);
        } catch (RuntimeException ex) {
            outcome = "error";
            throw ex;
        } finally {
            Timer timer = Timer.builder("dependency.client.duration")
                    .tag("callee", "payment-provider")
                    .tag("operation", "authorize")
                    .tag("outcome", outcome)
                    .publishPercentileHistogram()
                    .register(registry);
            sample.stop(timer);
        }
    }
}
~~~

`PaymentClient`, `AuthorizationCommand` và `AuthorizationResult` là kiểu minh họa. Trong implementation thực, cần phân loại outcomes rõ hơn: success, timeout, rejected, 4xx hợp lệ, 5xx, unknown result; đưa policy retry/idempotency ra đúng boundary.

**Điều đoạn mã chưa chứng minh:** metric này không thay thế tracing, không đo server/provider status nếu client che exception và không xác định được khoảng chờ connection nếu không có thêm instrument.

### 30.3. Log có correlation

Ví dụ log đã làm sạch:

~~~json
{
  "timestamp": "2026-11-12T02:05:12Z",
  "service": "order-service",
  "operation": "checkout",
  "traceId": "trace-example-123",
  "dependency": "payment-service",
  "errorType": "TIMEOUT",
  "requestId": "request-example-42",
  "durationMs": 1500
}
~~~

Không ghi Authorization header, API key, session cookie, payment card details hoặc full request payload. Với môi trường multi-tenant, quyền truy cập logs và retention cũng là yêu cầu thiết kế.

## 31. Trace có điểm kết nối khi service mesh hoặc proxy ở giữa

Một hệ thống có Envoy/service mesh có thể tạo spans của proxy:

~~~text
Order App → Order Sidecar → Payment Sidecar → Payment App
~~~

Cần hiểu span nào đo network, connection queue, retry và application execution. Nếu đếm `Order→Payment` ở cả app instrumentation và sidecar, service map có thể có **cạnh trùng** hoặc lượng calls bị nhân đôi.

Đề xuất:

- Xác định canonical identity cho service, workload và proxy.
- Gộp các hop kỹ thuật khi trình bày đồ thị nghiệp vụ, nhưng giữ drill-down để chẩn đoán network.
- So sánh app-level client/server duration và proxy-level latency.
- Không gộp request attempts với logical business operations.
- Xác định sampling và retry của proxy trước khi suy ra traffic.

## 32. Độ tin cậy của bằng chứng

Không phải mọi node đỏ đều đáng tin ngang nhau. Một sự kiện cần được đặt trong bảng:

| Bằng chứng | Có thể hỗ trợ | Hạn chế |
| --- | --- | --- |
| Edge timeout ratio tăng | Đường gọi tới dependency đang gặp vấn đề | Có thể do client pool, network hoặc callee |
| Callee server latency tăng | Callee xử lý chậm | Có thể không thấy network time trước ingress |
| Trace chậm có span provider dài | Provider path chiếm latency trong mẫu đó | Sampling và một trace chưa đại diện toàn lưu lượng |
| DB lock wait tăng | Có contention ở DB | Cần biết tác nhân tạo lock |
| Deployment gần thời điểm lỗi | Có thay đổi đáng điều tra | Correlation không phải causation |
| Một AZ mất Node Ready | Fault domain hạ tầng có vấn đề | Cần xem traffic routing và data plane |
| Provider public status báo outage | Nguồn ngoài có thể hỏng | Status page có thể trễ/không bao phủ tenant |
| Không có logs lỗi | Không phát hiện bằng log hiện có | Pipeline có thể thiếu hoặc log level không phù hợp |

Một kết luận có thể ghi:

> “Có xác suất cao Payment Provider latency là nguồn làm checkout chậm: 85% trace lỗi có provider span chiếm phần lớn thời gian, edge timeout tăng trước SLO burn, provider-side dashboard cũng báo degraded. Chưa loại trừ vấn đề connection pool ở một AZ.”

Cách diễn đạt này minh bạch hơn “Provider chắc chắn là nguyên nhân” khi bằng chứng còn hạn chế.

## 33. Cách xử lý thiếu telemetry

Một số trường hợp:

- Trace context không được propagate qua asynchronous queue.
- Agent tracing bị tắt ở một service.
- Network outage khiến collector không nhận logs/metrics.
- Service map chỉ dùng spans lấy mẫu nên thiếu route hiếm.
- Node bị crash trước khi flush telemetry.
- Metrics chỉ gắn service name không có version/AZ.
- Third-party provider không cung cấp server-side metrics.

**Cách bổ sung:**

1. Dùng server metrics, outbound client metrics và audit log hiện có.
2. Kiểm tra service discovery/config/declared dependencies.
3. Đối chiếu LB/proxy access logs đã làm sạch.
4. Xem infra telemetry từ node, DB, broker, network.
5. Ghi chú blind spot trong incident timeline.
6. Sau sự cố, bổ sung instrumentation ở critical edges.

Không khẳng định “không có đường gọi A→B” chỉ vì graph không vẽ cạnh.

## 34. Chẩn đoán database/broker bằng đồ thị nhiều lớp

Service graph chỉ có ứng dụng có thể bỏ sót các trạng thái đặc thù:

### 34.1. PostgreSQL/MySQL

- Writer/read replica và replica lag.
- Connection pools theo caller.
- Query latency và lock waits.
- Transaction commit/rollback.
- Schema migration.
- Failover và endpoint update.

Một writer mất có thể làm mọi service ghi dữ liệu lỗi, trong khi read-only journeys vẫn có thể bình thường; đồ thị cần phân biệt **read edge** và **write edge**.

### 34.2. Kafka/RabbitMQ

- Topic/queue và partitions.
- Consumer group subscription.
- Producer publish/ack latency.
- Consumer lag và oldest message age.
- DLQ, retries và poison messages.
- Quorum, leader/fencing và availability.

Một consumer chậm không nhất thiết làm producer HTTP 5xx, nhưng có thể làm workflow end-to-end vượt deadline. Vì vậy graph vận hành cần có business event edges, không chỉ network calls.

### 34.3. External provider

Theo dõi provider latency, HTTP status, quota/rate limits, error class, contractual timeout và status notifications. Nếu provider trả 429, việc tăng worker hoặc app replicas dễ làm xấu hơn. Cần rate limiting/backoff hoặc queue trước provider theo chính sách.

## 35. Tư duy chẩn đoán: tổng latency không luôn là tổng span durations

Trong trace có lời gọi song song:

~~~text
Order request 700 ms
├── Inventory 500 ms  ┐
└── Payment 600 ms    ┘ chạy song song
~~~

End-to-end latency có thể khoảng 700 ms, không là 1.100 ms. Hai span chồng lấn; cộng duration dẫn đến double counting.

Ngược lại, nếu Order gửi hai attempts tuần tự do timeout:

~~~text
Payment attempt #1: 600 ms timeout
Payment attempt #2: 600 ms success
~~~

Lời gọi logic có thể tốn 1.200 ms cộng backoff. Graph cần gắn attempts và retry policy.

**Critical path analysis** phải xét thời gian bắt đầu/kết thúc, dependency order và parallelism, không chỉ chọn span dài nhất hoặc cộng tất cả span lengths.

## 36. Chẩn đoán theo vùng ảnh hưởng, không theo màu đỏ toàn cụm

Giả sử:

- Checkout lỗi tại region-a.
- Catalog vẫn bình thường ở region-a.
- Checkout bình thường ở region-b.
- Payment client errors chỉ tăng trên Pod ở AZ-a.

Thay vì rollback tất cả regions, phân vùng graph theo **journey → region → AZ → service version → operation**. Điều này giúp tìm sự cố network/secret ở một AZ hoặc canary version lỗi.

Nếu chỉ có tổng service-wide error ratio, 5% request lỗi ở một AZ có thể bị che trong số lượng request của toàn cluster. Cần giữ khả năng drill-down nhưng tránh metric label cardinality bùng nổ.

## 37. Alert routing theo phụ thuộc và ownership

Một sự cố Provider có thể tạo cảnh báo Gateway, Order, Payment và Billing Worker cùng lúc. Nếu mỗi đội được page độc lập mà không có correlation, incident trở nên nhiễu.

Gợi ý:

- Alert từ user-facing SLO xác định **mức độ ưu tiên**.
- Edge anomaly và graph xác định **nhóm có khả năng cần điều tra**.
- Dedup/group theo incident, dependency, timeframe và environment.
- Gắn owner, escalation path và runbook.
- Mở incident bridge nếu nhiều teams/dependencies cần phối hợp.
- Đảm bảo on-call nhận bằng chứng và impact, không chỉ thông báo “CPU high”.

**Không tự động câm tất cả upstream alerts** khi có một downstream alert nếu chưa kiểm tra user impact; upstream vẫn có thể có lỗi độc lập hoặc khuếch đại.

## 38. Runbook điều tra incident theo đồ thị

### Bước 1 — Tạo ảnh chụp tình huống

Ghi:

- Incident ID, thời gian bắt đầu/khung giờ.
- User journeys, regions, tenants bị ảnh hưởng.
- SLI/SLO: bad requests, p95/p99, error-budget burn.
- Dashboard/graph snapshot ở cùng time window.
- Những nơi telemetry thiếu, không đầy đủ hoặc bị chậm.

### Bước 2 — Chọn đường đi trọng yếu

Từ `checkout` xác định các edges bắt buộc, operation được gọi và version đang phục vụ. Không cần mở các service không nằm trên đường nghiệp vụ trừ khi chúng là shared control/data dependencies.

### Bước 3 — Tìm điểm đổi trạng thái đầu tiên

So sánh trước/sau incident: traffic, errors, latency, saturation. Ưu tiên edge có thay đổi sớm, mức bất thường cao và có thể giải thích upstream SLI.

### Bước 4 — Thu bằng chứng độc lập

Trace lỗi và trace thành công, request IDs, logs có cấu trúc, DB/broker/provider metrics, recent deployments, network events.

### Bước 5 — Đặt giả thuyết và ghi điều chưa chắc

Ví dụ:

- H1: Provider chậm.
- H2: Payment client connection pool cạn.
- H3: DNS resolution trong AZ-a chậm.
- H4: Retry policy vừa thay đổi làm request amplification.

Chọn test/quan sát phân biệt các giả thuyết, không chỉ tìm dữ liệu ủng hộ H1.

### Bước 6 — Giảm tác động

Có thể route traffic khỏi vùng lỗi, giảm retry, hạn concurrency, rollback thay đổi hoặc áp dụng fallback hợp lệ. Cần ưu tiên an toàn dữ liệu và idempotency cho giao dịch đang không rõ kết quả.

### Bước 7 — Xác nhận phục hồi

- Edge errors/latency trở về baseline.
- User SLI đạt mức chấp nhận trong khoảng quan sát.
- Queue backlog xử lý xong hoặc giảm theo kế hoạch.
- Database/broker/state consistency được kiểm tra.
- Không phát sinh duplicate side effects từ retry.
- Alert và telemetry hoạt động.

### Bước 8 — Postmortem và graph maintenance

Lưu nguyên nhân, yếu tố góp phần, timeline, evidence, thay đổi kiến trúc/instrumentation/runbook, owner và deadline. Cập nhật những dependency ẩn đã phát hiện.

## 39. Thực hành tạo graph từ dữ liệu telemetry

Một bài lab có thể dùng:

- API Gateway.
- Order Service.
- Inventory Service.
- Payment Service.
- PostgreSQL.
- Một message broker và Notification Worker.
- OpenTelemetry Collector + tracing backend.
- Prometheus hoặc time-series backend.
- Dashboard đồ thị service/dependency.

### 39.1. Kịch bản baseline

Gửi tải đều vào checkout, ghi:

- Edge list quan sát được.
- Traffic/error/latency per edge.
- Trace coverage ở HTTP và broker.
- User-facing checkout SLI.
- Độ trễ và health của DB/broker.

### 39.2. Fault injection

Inject:

1. Payment 503 ở 20% calls.
2. Payment delay 1 giây ở 10% requests.
3. DB pool giới hạn nhỏ để tạo pending.
4. Broker consumer tạm dừng khiến queue age tăng.
5. Một canary Order V2 đổi timeout sai.
6. Một AZ có network latency tăng.

Mỗi scenario cần giới hạn, trong môi trường thử nghiệm được phép, không tác động production ngoài phạm vi.

### 39.3. Những gì phải quan sát

- User journey nào bị ảnh hưởng?
- Node/edge nào đầu tiên lệch baseline?
- Trace và metric có đồng ý không?
- Có retry amplification, fallback hoặc queueing không?
- Graph có vẽ đủ DB/broker/control-plane dependencies không?
- Có tìm đúng root cause mà không cần xem mọi service không?
- Khi khôi phục fault, SLI có trở lại bình thường không?

## 40. Bài tập tình huống

### Bài A — Xác định upstream blast radius

Đồ thị:

~~~text
Gateway → Order → Payment → Provider
                → Inventory → Inventory DB
Admin   → Payment
~~~

Provider hỏng. Hãy xác định các node có thể bị ảnh hưởng ngược và những node không có quan hệ phụ thuộc trực tiếp.

**Gợi ý:** Payment, Order, Gateway và Admin có đường đi phụ thuộc tới Provider; Inventory và Inventory DB không nhất thiết hỏng, dù retry/load có thể tác động gián tiếp. Cần xét operation và fallback.

### Bài B — CPU thấp nhưng latency cao

Order CPU 15%, p99 checkout 8 giây. Payment client p99 7,5 giây, connection pool pending tăng. Provider server latency bình thường.

**Câu hỏi:** nên kiểm tra gì trước?  
**Gợi ý:** Payment HTTP client connection acquisition, pool size, long-lived requests, leak, retry và network. Không mặc định Provider là nguyên nhân khi chính server latency của Provider bình thường và pending tại client cao.

### Bài C — Shared dependency

Catalog và Profile cùng tăng 5xx, không gọi nhau. Cả hai đều dùng Redis.

**Câu hỏi:** graph hỗ trợ điều tra thế nào?  
**Gợi ý:** thêm node Redis và edges dữ liệu; xem Redis error, cache misses, network, failover, recent config. Không vội rollback cả hai ứng dụng.

### Bài D — Event-driven SLO

Order API trả 202 nhanh, nhưng email xác nhận thường đến sau 20 phút. Broker lag tăng; Email Provider phản hồi 429.

**Câu hỏi:** tăng Notification Worker lên 50 replica có chắc cải thiện không?  
**Gợi ý:** không. Provider đang rate limit; tăng worker có thể làm 429 nhiều hơn. Cần throughput hợp lệ, backoff, queue deadline và SLI enqueue-to-email.

### Bài E — Retry amplification

Gateway inbound 1.000 RPS, Gateway→Order attempts 2.400 RPS và Order→Payment attempts 4.500 RPS.

**Câu hỏi:** có thể kết luận traffic người dùng tăng 4,5 lần không?  
**Gợi ý:** không. Đây có thể là retries ở nhiều tầng hoặc logic fan-out; cần đếm logical operations, idempotency keys, policy và status.

### Bài F — Graph thiếu cạnh

Service map không có edge Order→JWKS nhưng sau key rotation, Order trả 401 hàng loạt.

**Câu hỏi:** vì sao graph thiếu?  
**Gợi ý:** JWKS có thể được cache và chỉ fetch lúc cache expiry; trace sampling/thiếu instrumentation cũng gây thiếu. Bổ sung declared dependency và control-plane events.

### Bài G — Deploy trùng giờ outage

Order V2 được deploy lúc 10:00, Provider 503 cũng tăng lúc 10:00. Rollback Order không giảm errors.

**Câu hỏi:** nên kết luận gì?  
**Gợi ý:** thời điểm trùng nhau không chứng minh deploy là nguyên nhân. Kiểm tra Provider evidence, Payment client errors, retry configuration và những thứ cùng thay đổi.

### Bài H — Zone failure

AZ-a mất node Ready; Order vẫn có Pod ở b/c nhưng database writer ở a failover mất 30 giây.

**Câu hỏi:** graph layer nào cần để giải thích sự cố?  
**Gợi ý:** dependency graph kết hợp topology node/AZ và DB writer role; user-facing SLI phản ánh gián đoạn ghi dù app Pods vẫn chạy.

### Bài I — Fallback che bad event

Inventory offline, Order trả 200 với tồn kho cache cũ và chấp nhận bán vượt lượng tồn.

**Câu hỏi:** dashboard 5xx=0 có chứng minh khỏe không?  
**Gợi ý:** không. Cần business correctness SLI, degraded/partial outcome, cache freshness và data consistency.

### Bài J — Phân tích trace song song

Order gọi Inventory 400 ms và Payment 500 ms **song song**, tổng checkout 600 ms.

**Câu hỏi:** vì sao không phải 900 ms?  
**Gợi ý:** span overlap. Phân tích critical path theo timestamps và concurrency, không cộng tất cả duration.

## 41. Checklist sử dụng đồ thị khi vận hành

### Chất lượng graph

- [ ] Quy ước hướng cạnh A→B được áp dụng thống nhất.
- [ ] Có node ứng dụng, database, broker, cache, provider và control dependencies quan trọng.
- [ ] Biết edge required/optional, sync/async, operation và fallback.
- [ ] Graph có environment, region/AZ, version, owner, thời điểm quan sát.
- [ ] Kết hợp runtime traces với service discovery và declared/config dependencies.
- [ ] Có đánh dấu độ tin cậy, sampling và edge ẩn hoặc stale.

### Quan sát

- [ ] Có SLI/SLO cho user journeys thực sự quan trọng.
- [ ] Traffic, errors, latency, saturation đo ở node và edge phù hợp.
- [ ] Inbound requests tách khỏi outbound attempts và retries.
- [ ] Traces có context propagation xuyên HTTP/gRPC và event flows khi khả thi.
- [ ] Logs có correlation IDs, error type và không chứa secrets.
- [ ] Database/broker/infra metrics cho những dependency không dùng HTTP.
- [ ] Recent deploy/config/feature flag events được gắn lên timeline.
- [ ] Có alert riêng khi telemetry pipeline thiếu dữ liệu.

### Incident process

- [ ] Bắt đầu từ user impact và SLO, không bắt đầu bằng node bất kỳ có CPU cao.
- [ ] Lần theo required critical path trước, không kiểm tra mọi service ngang nhau.
- [ ] Phân biệt trigger, root cause, contributing factors và symptom.
- [ ] Ưu tiên ứng viên bằng anomaly, timeline, relevance và evidence quality.
- [ ] Kiểm chứng bằng trace/log/metrics và dữ liệu dependency độc lập.
- [ ] Không tuyên bố causality chỉ vì metric cùng biến động hoặc deploy gần thời điểm lỗi.
- [ ] Có biện pháp giảm tác động an toàn cho timeout, retries và data consistency.
- [ ] Xác nhận phục hồi ở user SLI, queue age, business outcomes và dependencies.
- [ ] Cập nhật runbook/owner/graph sau incident.

## 42. Tổng kết

**Đồ thị phụ thuộc** biến một tập hợp các microservice thành mô hình có thể lần theo: từ **user journey** tới **service**, từ service tới **database/broker/provider**, và từ một dependency lỗi ngược lên **những thành phần có thể chịu ảnh hưởng**.

Quy trình có hiệu quả là: **xác nhận SLO bị ảnh hưởng → chọn critical path → lần theo node/edge bất thường → so sánh timeline và thay đổi → kiểm chứng bằng metric, trace, log và hạ tầng → giảm blast radius → kiểm tra user-facing recovery → cập nhật tri thức vận hành**.

Không nên nhầm “nhiều node đỏ” với nhiều root causes độc lập, và cũng không tin một service map hoàn toàn nếu telemetry bị sampling/thiếu edge. Graph là **bản đồ giả thuyết**; kết luận sự cố phải dựa trên bằng chứng, hiểu đúng hợp đồng nghiệp vụ và đo được hệ thống đã phục hồi.
