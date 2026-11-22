# Distributed tracing và xác định phụ thuộc gây chậm

Một REST API trả `200 OK` sau 1,4 giây. Trong log của controller, đoạn xử lý nghiệp vụ chỉ mất 35 ms. Chậm ở đâu: load balancer, pool kết nối, một HTTP service khác, câu truy vấn SQL, retry hay thời gian chờ hàng đợi? Nếu chỉ nhìn log tại một instance Java/Spring, ta có thể tối ưu sai chỗ. **Distributed tracing (truy vết phân tán)** cung cấp cách nối các thao tác thuộc **cùng một yêu cầu xuyên qua nhiều dịch vụ**, từ đó xác định **đường thực thi quyết định độ trễ** và phụ thuộc cần điều tra.

Bài này thuộc chương **Quan sát hệ thống** của module `INTEGRATION_API_REST`: học thiết kế, vận hành và kiểm thử REST API dựa trên resource, HTTP, Java/Spring và các hợp đồng dữ liệu rõ ràng. Trọng tâm không phải cài một giao diện đẹp, mà là dùng dấu vết có ý nghĩa để trả lời: *Yêu cầu nào chậm? Chậm trong đoạn nào? Vì sao? Có thể chứng minh bằng những tín hiệu nào?*

**Kết quả học tập:** người học phân biệt trace/span/log/metric; truyền context qua HTTP và xử lý bất đồng bộ; instrument ứng dụng Spring bằng OpenTelemetry; đọc waterfall để tìm critical path; kết hợp latency, lỗi và tải; thiết kế sampling, bảo mật dữ liệu và bài test cho distributed tracing.

## 1. Ba trụ cột quan sát giải quyết ba câu hỏi khác nhau

| Tín hiệu | Câu hỏi chính | Ví dụ | Giới hạn |
| --- | --- | --- | --- |
| **Metrics** | *Có vấn đề bao nhiêu, trong thời gian nào?* | p95 latency của `POST /v1/orders` tăng từ 250 ms lên 1,2 s; tỷ lệ 5xx | Không chỉ ra chính xác một request đã đi qua đâu |
| **Logs** | *Một thành phần đã ghi nhận sự kiện gì?* | `inventory reservation timed out`, `connection pool exhausted` | Khó nối log ở nhiều dịch vụ nếu thiếu trace context |
| **Traces** | *Một yêu cầu đi qua những bước/phụ thuộc nào?* | Gateway → Orders → Inventory → PostgreSQL; span inventory chiếm 800 ms | Một trace đơn lẻ không đại diện toàn bộ traffic, có thể bị sampling hoặc thiếu span |

Trong vận hành, thường bắt đầu từ **metric cảnh báo SLO** (ví dụ tỷ lệ request trên 1 giây), mở một **trace đại diện**, sau đó truy log của những span/phụ thuộc bất thường để xác minh nguyên nhân. Không thay hệ thống metric bằng việc tự tính p95 từ vài trace được sampling: tập trace có thể bị thiên lệch.

Ví dụ symptom:

~~~text
http.server.request.duration (route=/v1/orders, p95): 1.4 s
http.server.request.duration (route=/v1/orders, p50): 0.18 s
error rate (5xx): 0.2%
~~~

Phần lớn request vẫn nhanh nhưng nhóm đuôi chậm rất rõ. Trước khi đọc trace, hãy phân nhóm theo **route template**, HTTP method, status, vùng triển khai, phiên bản release và dependency. Không dùng path có ID động như `/v1/orders/ord-123` làm metric label; nó làm bùng nổ cardinality.

## 2. Trace, span, parent-child và context

Một **trace** biểu diễn một hành trình logic của request/operation. Trace có **trace ID** (thường biểu diễn bằng 32 ký tự hex cho 16 byte). Mỗi **span** là một đơn vị công việc có thời điểm bắt đầu/kết thúc, một **span ID** riêng (thường 16 ký tự hex cho 8 byte), tên operation, attributes, events, status và quan hệ tới span khác.

~~~mermaid
flowchart TD
    T["Trace: request POST /v1/orders"] --> G["Span: gateway HTTP inbound"]
    G --> O["Span: orders-api HTTP server"]
    O --> V["Span: validate-order"]
    O --> I["Span: HTTP client inventory-api"]
    I --> IS["Span: inventory-api HTTP server"]
    IS --> DB["Span: SELECT/UPDATE inventory"]
    O --> P["Span: HTTP client payment-api"]
    P --> PS["Span: payment-api HTTP server"]
    O --> W["Span: INSERT orders (JDBC)"]
~~~

Trong ví dụ trên:

- Mọi span của **cùng một trace** chia sẻ trace ID, nhưng có span ID khác nhau.
- Span `orders-api HTTP server` là parent của những span do quá trình xử lý request tạo ra tại service Orders.
- Một outbound HTTP client span và inbound server span ở Inventory mô tả hai phía của **cùng lần gọi**. Việc nối parent-child phụ thuộc context được truyền qua network.
- Span cha có thể bao trùm nhiều span con; các span con có thể **chồng thời gian** do chạy song song. **Không cộng đơn giản duration của mọi span con** để suy ra request mất bao lâu.
- Một span có thể chứa attributes như `http.request.method=POST` hoặc `http.route=/v1/orders`, events đánh dấu retry, exception; attribute/event nào thực tế xuất hiện phụ thuộc instrumentation và phiên bản semantic conventions.

### Span khác log như thế nào?

Đây là ví dụ dữ liệu **minh họa**, không phải một chuẩn JSON bắt buộc của exporter:

~~~json
{
  "traceId": "8c1f8e4e312f4cc3be553e2511c6db25",
  "spanId": "d71dbd6c211a1c08",
  "parentSpanId": "c9b9f154dc206a33",
  "name": "POST /v1/orders",
  "service": "orders-api",
  "startTime": "2026-11-18T09:00:00.000Z",
  "durationMs": 835,
  "attributes": {
    "http.request.method": "POST",
    "http.route": "/v1/orders",
    "http.response.status_code": 201
  }
}
~~~

Một log cùng ngữ cảnh có thể là:

~~~json
{
  "timestamp": "2026-11-18T09:00:00.760Z",
  "level": "WARN",
  "service": "orders-api",
  "trace_id": "8c1f8e4e312f4cc3be553e2511c6db25",
  "span_id": "d71dbd6c211a1c08",
  "message": "Inventory call required a retry",
  "dependency": "inventory-api",
  "retry_attempt": 1
}
~~~

Traces cho ta **cấu trúc và thời gian**; logs cung cấp bối cảnh chi tiết không nhất thiết phù hợp làm span attribute; metrics cho thấy quy mô và xu hướng. Hãy đảm bảo correlation bằng trace ID/span ID, nhưng **không dùng trace ID làm bằng chứng xác thực hoặc quyền truy cập**.

## 3. W3C Trace Context: nối hành trình qua HTTP

Khi `orders-api` gọi `inventory-api`, trace context phải đi qua HTTP request. Chuẩn W3C Trace Context định nghĩa:

- `traceparent` chứa version, trace ID, parent span ID và trace flags.
- `tracestate` cho phép lưu thông tin vendor-specific có cấu trúc, có giới hạn kích thước/số entry.
- `baggage` là một chuẩn khác dùng để truyền các key-value metadata theo ngữ cảnh; **không** dùng để gửi bí mật, token hay thông tin cá nhân.

Ví dụ một request đã được instrument:

~~~http
GET /v1/inventory/BOOK-42 HTTP/1.1
Host: inventory.internal
traceparent: 00-8c1f8e4e312f4cc3be553e2511c6db25-d71dbd6c211a1c08-01
tracestate: vendor=sample-state
~~~

Giải mã phần `traceparent`:

~~~text
00   - 8c1f8e4e312f4cc3be553e2511c6db25 - d71dbd6c211a1c08 - 01
│      │                                  │                   │
version│                                  parent span ID      trace flags
       trace ID
~~~

`01` ở ví dụ biểu thị cờ sampled trong trace flags. **Cờ sampled không phải cam kết toàn bộ span chắc chắn được lưu ở backend**: collector/exporter vẫn có thể lọc hoặc làm rơi dữ liệu khi quá tải. Một header tự sinh bằng tay trong Postman có thể mang trace ID tùy chọn, nhưng không chứng minh hệ thống đã xuất trace.

### Điều cần đúng tại ranh giới service

1. **Inbound:** framework/extractor lấy parent context từ request, tạo server span. Nếu không có parent hợp lệ, service bắt đầu trace mới theo sampling policy.
2. **Outbound:** instrumentation lấy context hiện hành, tạo client span, chèn `traceparent` (và những header truyền ngữ cảnh đã bật) vào HTTP request.
3. **Receiver:** service đích extract context và tạo server span liên kết.
4. **Async boundary:** khi đưa việc sang thread pool hoặc message broker, phải truyền context có chủ đích. `ThreadLocal` không tự đi cùng task sang thread khác.
5. **Trust boundary:** headers từ client Internet là dữ liệu không đáng tin; validator/propagator phải xử lý giá trị sai và giới hạn metadata. Không ghi raw `baggage` vào log, không cho client quyết định tenant, vai trò hoặc cấp độ quyền bằng baggage.

Nếu gateway không truyền header, nếu một client HTTP được tạo ngoài cơ chế instrument, hoặc nếu context bị mất ở `CompletableFuture`/executor, trace có thể bị **tách thành hai trace độc lập**. Đây là lỗi khả năng quan sát, không nhất thiết là lỗi nghiệp vụ; nhưng nó khiến chẩn đoán sai.

## 4. Đặt span đúng chỗ và đặt tên sao cho truy vấn được

Với `POST /v1/orders`, có ba cấp span có ích:

| Cấp | Ví dụ tên / thông tin | Lý do |
| --- | --- | --- |
| Entry HTTP server | `POST /v1/orders`, `http.route=/v1/orders`, status, duration | Theo dõi latency endpoint và SLO |
| Client/DB tự động | `GET inventory-api`, câu lệnh SQL được chuẩn hóa, host dịch vụ | Tìm dependency và xác định chỗ chờ network/DB |
| Business span thủ công | `orders.reserve-stock`, `orders.validate-policy` | Phân biệt thời gian nghiệp vụ với framework |

**Tên span và attributes phải có cardinality thấp**. Tên nên là operation ổn định: `orders.reserve-stock`, không phải `orders.reserve-stock-BUYER-98123`. Lưu route template `/v1/orders/{id}` thay vì path cụ thể có UUID. Hạn chế attributes theo API/sensitivity budget; không gắn email, bearer token, địa chỉ, thẻ thanh toán, raw SQL parameter, session cookie hay full JSON body.

Những span có ích phải thể hiện **thời gian chờ**, không chỉ thời gian CPU:

- HTTP client call (bao gồm chờ pool/connection nếu instrumentation đo được), server xử lý request, retries và backoff.
- JDBC transaction/query, chờ lấy connection từ pool, lock contention và số lần query.
- Queue publish, queue consumer, **queue age** (enqueue → start processing) và thời gian thực thi job.
- Cache lookup, cache miss rồi fallback DB, semaphore/concurrency admission.

Không tự tạo hàng trăm span cho mỗi vòng lặp nhỏ nếu chúng không giúp ra quyết định. Khi cần xem từng dòng hàng, aggregate số lượng và thời gian thành một span/event có giới hạn; tránh chi phí instrumentation lớn hơn lợi ích.

### 4.1. Khi nào đánh dấu span lỗi?

**HTTP status và span status không phải một thứ.** Một request 404 hợp lệ do resource không tồn tại có thể là kết quả nghiệp vụ được dự kiến, không nhất thiết lỗi hệ thống. Các instrumentation thường áp quy tắc semantic conventions cho server/client span; khi tạo span thủ công hãy chọn `StatusCode.ERROR` khi thao tác **thực sự thất bại theo mục đích** của span, kèm exception đã được lọc.

Ví dụ client nhận 429 rate limit: ghi `http.response.status_code=429`; để metric phân biệt từ chối chủ động với 5xx. Với timeout đến DB hoặc downstream, ghi timeout type, dependency và trạng thái lỗi; không ghi connection string có mật khẩu hay nội dung nhạy cảm.

## 5. Đọc waterfall: xác định dependency nằm trên critical path

Hãy xem một trace của `POST /v1/orders` có thời lượng end-to-end **740 ms**. Các mốc dưới đây là giả lập và lấy cùng một trục thời gian để dễ tính:

| Span/hoạt động | Bắt đầu (ms) | Kết thúc (ms) | Duration |
| --- | ---: | ---: | ---: |
| Gateway HTTP inbound | 0 | 740 | **740 ms** |
| Orders API server | 20 | 726 | 706 ms |
| Load customer (JDBC) | 50 | 100 | 50 ms |
| Inventory HTTP client | 120 | 540 | **420 ms** |
| Pricing HTTP client (song song) | 125 | 200 | 75 ms |
| Payment HTTP client (sau inventory) | 550 | 680 | **130 ms** |
| Save order (JDBC) | 687 | 710 | 23 ms |

Hình dung dưới dạng thanh thời gian:

~~~text
Thời gian (ms)     0      100      200      300      400      500      600      700 740
Gateway            [===================================================================]
Orders API           [================================================================]
DB customer              [====]
Inventory HTTP                  [=========================================]
Pricing HTTP                     [=======]
Payment HTTP                                                               [============]
DB save                                                                                    [==]
~~~

**Sai lầm phổ biến:** cộng `50 + 420 + 75 + 130 + 23 = 698 ms` rồi tuyên bố “đó là toàn bộ thời gian xử lý”. Pricing chạy **song song** với inventory, nên 75 ms pricing có thể **không làm tăng thời gian end-to-end** ở lần chạy này. Ngoài ra còn có thời gian giữa spans, việc ở gateway và logic chưa instrument. Duration của span cha cũng bao gồm khoảng thời gian của span con.

**Critical path** là chuỗi công việc/ràng buộc phụ thuộc quyết định thời điểm hoàn tất. Trong ví dụ: đọc khách hàng → đợi Inventory → gọi Payment → ghi Order là đường tuần tự chính. Nếu giảm Pricing từ 75 ms còn 10 ms nhưng Pricing đã hoàn tất trước Inventory, tổng latency có thể **gần như không đổi**. Nếu giảm Inventory 420 ms xuống 150 ms mà không xuất hiện nghẽn khác, request có tiềm năng giảm đáng kể.

Tuy nhiên, không được kết luận *Inventory server xử lý 420 ms* chỉ từ **HTTP client span 420 ms**. Client span có thể bao gồm:

~~~text
Inventory HTTP client: 120 .. 540 = 420 ms
    Chờ connection pool:           120 .. 420 = 300 ms
    DNS/connect/TLS hoặc network:  420 .. 455 =  35 ms
    Inventory server span:         455 .. 535 =  80 ms
    Đọc response / overhead:       535 .. 540 =   5 ms
~~~

**Chẩn đoán đúng:** Server Inventory chỉ dùng 80 ms; điểm nghẽn chính là **chờ lấy connection trong Orders** (300 ms). Tăng tài nguyên Inventory có thể không cải thiện gì. Cần kiểm tra pool metrics (active/idle/pending), reuse kết nối, concurrency, timeout, số kết nối bị giữ lâu và retry. Đây là tình huống minh họa; trên hệ thống thực, các pha DNS/network/pool chỉ hiện riêng nếu có instrumentation hỗ trợ.

**Đồng hồ giữa các máy:** So sánh absolute start/end giữa các service cần lưu ý clock skew, network timing và sai số instrumentation. Duration đo bằng đồng hồ phù hợp trong cùng process thường đáng tin hơn việc trừ hai timestamp từ hai host không đồng bộ. Nếu UI vẽ span con bắt đầu trước span cha, trước tiên kiểm tra context/clock sync thay vì suy ra “du hành thời gian”.

### 5.1. Checklist đọc trace khi API chậm

1. Chọn endpoint, môi trường, release và cohort có latency p95/p99 cao từ metrics; lấy một số trace **chậm và nhanh** để so sánh.
2. Xác định root/server span, tổng duration, các span con có thời điểm và cấu trúc parent-child.
3. Tìm **những span nằm trên đường tới thời điểm hoàn tất**, không chỉ span có duration lớn nhất.
4. Tách client-side latency khỏi server-side latency của cùng dependency; tìm khoảng trống do pool, queue, backoff, connection, TLS hoặc thiếu instrumentation.
5. Đọc attributes/status/events: retry count, timeout, database system, route group, cache hit, sampling và deployment version.
6. Đối chiếu với histogram, pool/queue metrics, log có cùng trace ID; loại trừ hot shard/tenant hoặc một release cụ thể.
7. Thử thay đổi có kiểm soát rồi đo lại **p95/p99, tỷ lệ lỗi và throughput**; đừng chỉ nhìn một waterfall đẹp hơn.

## 6. Một trường hợp điều tra thực tế: N+1, retry và độ trễ đuôi

Giả sử `GET /v1/orders?page=0&size=50` có p50 = 120 ms, p95 = 1.100 ms. Trace chậm cho thấy:

~~~text
GET /v1/orders              1,100 ms
  authorization                12 ms
  SELECT orders                32 ms
  load order details          840 ms
    SELECT detail WHERE id=1   14 ms
    SELECT detail WHERE id=2   16 ms
    ... (50 lần gần nối tiếp)
  serialize response           28 ms
~~~

Ở đây lỗi thiết kế có thể là **N+1 query**: service đọc 50 đơn, sau đó truy vấn detail của từng đơn, tạo 51 query thay vì lấy dữ liệu theo lô. Trace cho thấy nhiều span JDBC lặp lại; xác minh bằng số câu SQL, request scope và DB metrics. Cải tiến có thể là batch query, `JOIN` có kiểm soát, projection phù hợp, hoặc thay đổi DTO để không tải quan hệ không cần thiết.

Một kiểu chậm khác là retry:

~~~text
orders → inventory (client) 900 ms
    attempt 1: 200 ms → timeout
    backoff:   100 ms
    attempt 2: 200 ms → timeout
    backoff:   200 ms
    attempt 3: 180 ms → 200 OK
    overhead:   20 ms
~~~

Traces cần hiển thị số attempt hoặc events có giới hạn. Nếu chỉ instrument wrapper của retry thành một span 900 ms mà bỏ chi tiết, ta có thể đổ lỗi nhầm cho “Inventory xử lý chậm” dù nhiều lần lỗi và backoff mới là nguyên nhân. Sửa bằng deadline end-to-end, timeout phù hợp, retry budget, exponential backoff có jitter và circuit breaker; **không** retry POST không idempotent một cách mù quáng.

**Phân biệt lỗi và tốc độ:** rate limit 429 hoặc admission control 503 có thể **giảm** thời gian phục vụ số request bị từ chối trong khi trải nghiệm người dùng vẫn xấu. Khi điều tra, xem cả tỷ lệ accepted/rejected và số request thành công hoàn tất trong SLO, không chỉ p95 latency của 2xx.

## 7. Instrument Spring Boot/Java bằng OpenTelemetry

**OpenTelemetry (OTel)** cung cấp API, SDK, instrumentation và chuẩn xuất dữ liệu qua OTLP. Có hai hướng triển khai phổ biến với Spring:

- **OpenTelemetry Java agent**: gắn agent ở JVM startup để tự instrument nhiều thư viện Spring MVC, HTTP client, JDBC, messaging được hỗ trợ. Phù hợp để thấy trace xuyên service nhanh mà không sửa nhiều code.
- **Micrometer Tracing trong Spring Boot Actuator**: Spring tích hợp observation/tracing và có thể bridge sang OTel/OTLP. Phù hợp khi muốn quản lý instrumentation trong ứng dụng theo cấu hình Spring.

**Không bật hai cơ chế instrument cùng một HTTP request một cách thiếu kiểm soát**: Java agent và Micrometer bridge có thể tạo span trùng hoặc làm phức tạp propagation nếu cấu hình chồng chéo. Chọn kiến trúc rõ ràng, kiểm tra span thực tế và tài liệu tương ứng với phiên bản Spring Boot/agent.

### 7.1. Ví dụ tự động với Java agent và OTLP

Ví dụ môi trường staging, container có `opentelemetry-javaagent.jar` và OpenTelemetry Collector nội bộ. Đây là lệnh **minh họa trên shell Linux**, không phải nội dung cần chạy trong thư mục bài học:

~~~bash
export OTEL_SERVICE_NAME=orders-api
export OTEL_RESOURCE_ATTRIBUTES="service.namespace=commerce,deployment.environment.name=staging"
export OTEL_TRACES_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
export OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
export OTEL_TRACES_SAMPLER=parentbased_traceidratio
export OTEL_TRACES_SAMPLER_ARG=0.10

java -javaagent:/opt/opentelemetry-javaagent.jar -jar orders-api.jar
~~~

Với OTLP qua HTTP/protobuf, `OTEL_EXPORTER_OTLP_ENDPOINT` trong ví dụ là **base endpoint**; exporter ghép đường dẫn tín hiệu như `/v1/traces`. Nếu dùng biến endpoint riêng cho traces thì kiểm tra cú pháp đường dẫn theo exporter đang chạy. Với OTLP/gRPC thường dùng port 4317 thay vì 4318. Không nhầm hai giao thức, đồng thời cấu hình TLS và xác thực giữa ứng dụng–collector trong production.

Chạy tương tự cho `inventory-api`, `payment-api` và các worker. Dùng tên `service.name` ổn định, phân biệt bằng thuộc tính môi trường/phiên bản thay vì tạo tên mới cho mỗi pod. Gắn `service.version` hoặc metadata deploy để so sánh trước và sau release.

Hành trình điển hình:

~~~mermaid
flowchart LR
    C[Browser/mobile] --> G[API gateway]
    G --> O[orders-api + OTel]
    O --> I[inventory-api + OTel]
    O --> P[payment-api + OTel]
    O --> DB[(PostgreSQL)]
    G -. OTLP .-> COL[OTel Collector]
    O -. OTLP .-> COL
    I -. OTLP .-> COL
    P -. OTLP .-> COL
    COL --> B[(Trace backend)]
~~~

**Collector** thường nhận, lọc, batch, giới hạn và xuất trace tới backend truy vấn; nó không tự sửa lỗi nghiệp vụ hoặc đảm bảo không mất span trong mọi sự cố. Dùng queue/retry/bộ nhớ có giới hạn và theo dõi tình trạng export. Không xuất thẳng dữ liệu có PII ra dịch vụ không được phê duyệt.

### 7.2. Nếu dùng Spring Boot Actuator + Micrometer Tracing

Ví dụ cấu hình tổng quát cho những phiên bản Boot 3.x hỗ trợ Micrometer Tracing/OTLP (xác nhận tên property theo phiên bản thực tế):

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.10
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
~~~

Ứng dụng cần dependencies tương ứng, ví dụ Actuator, Micrometer Tracing bridge OTel và OTLP exporter; YAML **không tự cài dependency**. Khác với base endpoint ở Java agent phía trên, cấu hình `management.otlp.tracing.endpoint` của Spring thường là **URL đầy đủ cho traces**. Chỉ dùng một chiến lược export/propagation thống nhất, kiểm tra backend nhận đúng trace của ứng dụng trước khi tăng sampling.

### 7.3. Thêm business span thủ công bằng OTel API

Auto-instrumentation không biết đoạn nghiệp vụ “giữ tồn kho” bắt đầu/kết thúc ở đâu. Với OpenTelemetry API, có thể tạo span có tên cố định:

~~~java
import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;

public final class InventoryReservation {
    private final Tracer tracer =
        GlobalOpenTelemetry.getTracer("app.orders");
    private final InventoryClient inventoryClient;

    public InventoryReservation(InventoryClient inventoryClient) {
        this.inventoryClient = inventoryClient;
    }

    public void reserve(String sku, int quantity) {
        Span span = tracer.spanBuilder("orders.reserve-stock").startSpan();
        try (Scope scope = span.makeCurrent()) {
            span.setAttribute("orders.item_count", 1L);
            inventoryClient.reserve(sku, quantity);
            span.addEvent("inventory.reservation.confirmed");
        } catch (RuntimeException ex) {
            span.recordException(ex);
            span.setStatus(StatusCode.ERROR, "Inventory reservation failed");
            throw ex;
        } finally {
            span.end();
        }
    }
}

interface InventoryClient {
    void reserve(String sku, int quantity);
}
~~~

`Tracer` phải được nối với một OTel SDK/provider đã cấu hình (ví dụ agent hoặc dependency injection phù hợp); nếu chỉ thêm API mà không cài SDK/exporter thì không tự xuất trace. `Scope` giúp span thành current context cho lời gọi con trên cùng thread; `finally` bảo đảm end span ngay cả khi lỗi. Giữ **exception recording** có kiểm soát: exception message có thể chứa dữ liệu người dùng, nên scrub bằng processor/filter hoặc tránh gắn thông tin nhạy cảm.

Không đưa giá trị `sku`, email, access token hay JSON body vào span name. Nếu cần phân tích theo loại hàng, dùng nhóm đã được duyệt và cardinality thấp, không dùng ID sản phẩm có hàng triệu giá trị làm metric label.

## 8. Truyền trace qua thread pool, message broker và background job

### 8.1. Thread pool và `CompletableFuture`

Trong xử lý request bất đồng bộ, context không tự truyền qua mọi executor. Ví dụ chuyển đúng context đã capture sang task:

~~~java
import io.opentelemetry.context.Context;
import io.opentelemetry.context.Scope;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;

public CompletableFuture<Void> runAsyncWithTrace(
        Executor executor, Runnable task) {
    Context parent = Context.current();
    return CompletableFuture.runAsync(() -> {
        try (Scope ignored = parent.makeCurrent()) {
            task.run();
        }
    }, executor);
}
~~~

Nếu không có context propagation, span tạo bên trong `task` có thể thành trace mới. Nếu task kéo dài sau khi HTTP request kết thúc, cần chọn quan hệ phù hợp (parent-child hoặc span **link**) và lifecycle độc lập; đừng giữ span server request mở chỉ để đợi một job hàng phút.

### 8.2. Message broker

Với Kafka/RabbitMQ hoặc queue tương đương, publisher cần inject propagation context vào **message headers**; consumer extract context khi xử lý. Instrumentation tự động của thư viện có thể làm việc này. Nếu tự triển khai adapter:

~~~java
import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.propagation.TextMapPropagator;
import java.util.HashMap;
import java.util.Map;

TextMapPropagator propagator =
    GlobalOpenTelemetry.getPropagators().getTextMapPropagator();
Map<String, String> messageHeaders = new HashMap<>();

propagator.inject(
    Context.current(),
    messageHeaders,
    (carrier, key, value) -> carrier.put(key, value)
);

// Chuyển messageHeaders vào broker headers bằng adapter phù hợp.
~~~

Ở consumer, dùng extractor theo định dạng message header và khôi phục context trước khi tạo consumer/business span. Không mặc định mọi broker dùng key-value String thuần: Kafka headers là byte arrays, một số broker có nhiều giá trị cho cùng key; adapter phải chuyển đổi đúng và bảo vệ trước kích thước header bất thường.

**Parent-child không phải lúc nào cũng đúng.** Một HTTP request nhận job rồi trả `202 Accepted`; worker có thể chạy sau nhiều phút. Worker có thể ghi parent context đã được truyền, hoặc dùng **span links** tới producer/operation khi có nhiều message/batch hoặc execution độc lập; chọn cách trình bày phản ánh quan hệ nhân quả mà không giả tạo một request HTTP kéo dài hàng phút.

Với queue, cần thêm metric `enqueue timestamp → consumer start` để đo **queue latency**. Span duration của consumer thường chỉ đo lúc worker thực sự chạy, nên một job chờ 20 phút trong queue có thể trông “chỉ mất 50 ms” nếu không đo thời gian chờ.

## 9. Sampling, chi phí và giới hạn của trace

Ở 10.000 request/giây, nếu mỗi request tạo 15 spans, hệ thống có thể tạo **150.000 spans/giây** trước sampling. Xuất tất cả có thể tốn network, CPU, lưu trữ và chi phí truy vấn. Cần chính sách lấy mẫu:

| Cách | Cách quyết định | Ưu điểm | Điểm cần thận trọng |
| --- | --- | --- | --- |
| **Head sampling** | Quyết định khi trace bắt đầu, trước khi biết độ trễ/lỗi cuối | Giảm overhead sớm, triển khai đơn giản | Có thể bỏ qua trace hiếm mà quan trọng |
| **Parent-based sampling** | Tôn trọng quyết định sampling của parent trong phạm vi được chọn | Giúp trace xuyên dịch vụ nhất quán hơn | Context ngoại lai không đáng tin, tail backend vẫn có thể drop |
| **Tail sampling** | Collector đợi đủ thông tin trong một khoảng rồi chọn theo lỗi/latency/thuộc tính | Ưu tiên trace chậm, lỗi hiếm | Phải tiếp nhận/buffer dữ liệu trước khi quyết định; tốn memory và state |
| **Always-on cho môi trường nhỏ** | Thu tất cả | Dễ debug | Không phù hợp traffic lớn/PII nếu chưa quản trị |

Một hệ thống có thể chọn sampling 10% cho traffic bình thường, ưu tiên trace 5xx hoặc chậm theo rule ở collector. Nhưng **tail sampling không thể khôi phục span đã bị head sampler loại bỏ từ ứng dụng**. Muốn collector quyết định từ dấu vết đầy đủ, upstream phải gửi đủ dữ liệu theo thiết kế đã được kiểm soát; còn head sampling sẽ giảm dữ liệu ngay từ nguồn.

**Cảnh báo dữ liệu sai lệch:** Nếu giữ lại phần lớn trace chậm/lỗi và ít trace nhanh, histogram tính từ số trace lưu sẽ bị thiên lệch. Dùng metrics ở source để tính SLO, p95/p99 và error budget; traces giúp tìm nguyên nhân, không phải tự động là tập mẫu thống kê ngẫu nhiên.

### Bảo vệ thông tin và độ tin cậy

- Mặc định không log body, header `Authorization`, cookie, OTP, địa chỉ, email, token, SQL parameters hoặc mật khẩu trong spans. Áp chính sách lọc tại instrumenter và collector, kiểm thử đường lỗi cũng không rò dữ liệu.
- `traceparent` do người dùng gửi có thể giả mạo. Trace ID chỉ dùng correlation; không làm session ID, audit identity, access control hay idempotency key.
- Không tin `baggage` do external caller cung cấp để định danh tenant/role; xác thực mọi quyết định nghiệp vụ bằng principal hoặc dữ liệu server.
- Giới hạn attribute/value length, số events, baggage size và số span theo request. Hạn chế high-cardinality trong metrics và backend truy vấn trace.
- Bật TLS/authentication cho đường xuất OTLP, phân quyền người xem traces, retention và masking theo dữ liệu cần bảo vệ.
- Theo dõi số spans bị drop, collector queue, exporter error, ingestion latency, tỷ lệ trace thiếu service và chênh lệch sampled/exported. “Không thấy span” không đồng nghĩa “service không được gọi”.

## 10. Kết hợp tracing với HTTP semantics và REST API

Traces hữu dụng hơn khi REST API có **route/resource và status rõ ràng**:

| Dạng triệu chứng | Thông tin cần xem trong trace | Hướng hành động |
| --- | --- | --- |
| `GET /v1/orders/{id}` p99 cao | DB lookup, cache miss, N+1, lock wait | Index, query plan, cache/projection |
| `POST /v1/orders` 5xx do inventory | HTTP dependency, timeout, retry, downstream status | Timeout budget, circuit breaker, resilience |
| 429 tăng sau release | Rate limiter span, route, policy, tenant tier *đã chuẩn hóa* | Điều chỉnh admission, client retry/backoff; không chỉ tăng quota |
| 503/504 tại gateway | Gateway span, request có tới service không, pool/tài nguyên | Phân biệt queue tại ingress với worker timeout |
| `202 Accepted` nhưng job xong chậm | Publish latency, queue age, consumer span, job state | Điều tra backlog và concurrency worker |
| GET sau POST thấy dữ liệu cũ | Write span, outbox, projection lag, cache | Kiểm tra eventual consistency và read-your-writes |
| API chậm chỉ khi request lớn | Parser/validation, payload bytes/depth, DB cost | Giới hạn request, hiệu chỉnh schema/batch |

**Có thể không có trace đầy đủ ngay khi người dùng báo sự cố.** Hỏi thời gian UTC, route template, request ID/trace ID (nếu đã công bố an toàn), status, deployment version. Dùng log correlation và metrics để khoanh vùng; không yêu cầu người dùng gửi access token hoặc nội dung bí mật chỉ để tìm trace.

### Liên kết trace với log trong Spring

Spring Boot khi cấu hình Micrometer Tracing có thể thêm trace/span IDs vào logging correlation; với OTel agent, cấu hình log correlation tùy logging framework và agent/instrumentation. Có thể chuẩn hóa JSON log:

~~~json
{
  "level": "ERROR",
  "service": "orders-api",
  "trace_id": "8c1f8e4e312f4cc3be553e2511c6db25",
  "span_id": "d71dbd6c211a1c08",
  "http_route": "/v1/orders",
  "event": "dependency_timeout",
  "dependency": "inventory-api",
  "retry_count": 2
}
~~~

Trace và log phải cùng ID dưới cùng context; nếu log của thread pool bị thiếu trace ID, xem lại context propagation hoặc MDC. Đừng giả định một task bất đồng bộ luôn thừa kế thread-local logging context. Với metrics, ví dụ histogram `http.server.request.duration` theo route/status và exemplar liên kết tới trace tương ứng sẽ giúp đi từ cảnh báo tail-latency sang waterfall cụ thể; khả năng exemplar tùy exporter và backend.

## 11. Kiểm thử distributed tracing: không chỉ xem dashboard

Để kiểm thử, sử dụng một ứng dụng có ít nhất **Orders → Inventory** qua HTTP và một đường async/queue; gửi cả request thành công, 4xx, 5xx, timeout và retry. Dữ liệu quan sát được có thể được export vào một collector/backend trong môi trường test, hoặc dùng in-memory exporter của OTel SDK cho unit/integration test nơi phù hợp.

### 11.1. Test HTTP propagation

Gửi request với traceparent hợp lệ:

~~~bash
curl -i -X POST "http://localhost:8080/v1/orders" \
  -H "Content-Type: application/json" \
  -H "traceparent: 00-8c1f8e4e312f4cc3be553e2511c6db25-d71dbd6c211a1c08-01" \
  -d '{"items":[{"sku":"BOOK-42","quantity":1}]}'
~~~

`curl` chỉ gửi header; để thấy trace, ứng dụng và backend **phải được instrument và cấu hình exporter**. API cần schema/auth phù hợp; ví dụ body ở trên có thể không đạt hợp đồng thực tế. Quan sát inbound server span của Orders và outbound Inventory: cùng trace ID, span ID riêng, parent-child hợp lý; kiểm tra response status mà không phụ thuộc việc API có trả trace ID cho client.

Kiểm thử thêm:

1. **Không có `traceparent`:** server tạo trace theo policy; không báo lỗi nghiệp vụ chỉ vì thiếu tracing.
2. **Header sai định dạng:** propagator bỏ qua/tạo context mới an toàn, không trả 500 vì parsing trace header.
3. **Đường nhiều nút:** load balancer chuyển giữa instance A/B; trace context không bị đổi trong cùng hành trình.
4. **Thread pool:** span trong async task có parent/link phù hợp; logs trong task có trace ID tương ứng khi cần.
5. **HTTP outbound:** client instrumentation có truyền `traceparent` đúng tới dependency; không tự phản chiếu header bất kỳ sang domain không đáng tin.
6. **Message queue:** producer–consumer có quan hệ trace/link; queue age được đo riêng; delivery lặp không bị nhầm với một request duy nhất.
7. **Lỗi và retries:** có client span/attempt hoặc event đủ để thấy retry budget, timeout, backoff; không lộ message của exception nhạy cảm.
8. **Sampling và exporter down:** API vẫn trả nghiệp vụ đúng; instrumentation/exporter không giữ request mãi khi collector chậm.

### 11.2. Ví dụ unit test bằng in-memory span exporter

Trích đoạn JUnit với OTel SDK test utilities; giả sử đã có dependency `opentelemetry-sdk-testing` cùng phiên bản với SDK dùng trong dự án. Mục tiêu là kiểm tra một business span **được tạo, có tên và không chứa PII**, không chứng minh HTTP propagation (cần integration test riêng).

~~~java
import static org.junit.jupiter.api.Assertions.*;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;
import io.opentelemetry.sdk.testing.exporter.InMemorySpanExporter;
import io.opentelemetry.sdk.trace.SdkTracerProvider;
import io.opentelemetry.sdk.trace.data.SpanData;
import io.opentelemetry.sdk.trace.export.SimpleSpanProcessor;
import java.util.List;
import org.junit.jupiter.api.Test;

@Test
void businessSpanContainsNoCustomerEmail() {
    InMemorySpanExporter exporter = InMemorySpanExporter.create();
    SdkTracerProvider provider = SdkTracerProvider.builder()
        .addSpanProcessor(SimpleSpanProcessor.create(exporter))
        .build();
    try {
        Tracer tracer = provider.get("test.orders");
        Span span = tracer.spanBuilder("orders.reserve-stock").startSpan();
        try (Scope ignored = span.makeCurrent()) {
            span.setAttribute("orders.item_count", 2L);
        } finally {
            span.end();
        }

        List<SpanData> spans = exporter.getFinishedSpanItems();
        assertEquals(1, spans.size());
        assertEquals("orders.reserve-stock", spans.get(0).getName());
        assertFalse(spans.get(0).getAttributes().toString()
            .contains("linh@example.com"));
    } finally {
        provider.close();
    }
}
~~~

Test trên chỉ chứng minh một mẫu span không chứa chuỗi email; production cần kiểm tra nhiều đường exception, header, payload, queue message và các processor/exporter khác nhau. Không viết test cứng rằng mọi span đều phải có mặt khi sampling < 100%; trong môi trường test có thể dùng sampler `always_on` hoặc provider test riêng để có kết quả ổn định.

### 11.3. Test bằng fault injection

| Sự cố đưa vào | Trace nên cho thấy | Metric/log đối chứng |
| --- | --- | --- |
| Delay Inventory 800 ms | Client span và server span liên quan, đường critical path dài ra | p95 orders tăng; Inventory latency tăng |
| Pool HTTP có 1 connection và 20 request song song | Client span chờ lâu trước server span | Pending-acquire, active pool, timeout |
| 50 query N+1 | Nhiều JDBC span trong cùng request | DB query count, connection metrics |
| Inventory trả 503 hai lần rồi 200 | Retry attempts, backoff/deadline | 503 upstream, retry counter |
| Worker queue bị dừng 60 giây | Consumer start trễ so với enqueue | Queue age/depth tăng |
| Collector/exporter không khả dụng | Có metric dropped/export failed; API không treo lâu | Exporter errors, memory/queue |

Giữ fault injection trong môi trường kiểm soát, có deadline/giới hạn tải; không gây gián đoạn production để chỉ thu một trace.

## 12. Quy trình điều tra và quyết định tối ưu

Một playbook ngắn khi nghe “REST API chậm”:

~~~text
1. Xác định triệu chứng: route/method, thời gian, môi trường, release,
   p50/p95/p99, error rate, request rate, 429/503.
2. Lấy trace chậm + trace bình thường cùng cohort.
3. Tìm critical path, HTTP client/server spans và các khoảng trống.
4. Đối chiếu pool/queue/DB/cache/retry metrics và log theo trace_id.
5. Lập giả thuyết nguyên nhân (ví dụ acquire connection mất 300 ms).
6. Chỉnh một biến có kiểm soát; tránh che triệu chứng bằng timeout dài hơn.
7. So lại SLO, p95/p99, throughput, errors và chi phí; rollback nếu xấu hơn.
~~~

**Một trace không xác nhận quan hệ nhân quả.** Ví dụ span SQL mất 300 ms có thể là hậu quả của hệ thống quá tải do retry storm chứ không phải nguyên nhân đầu tiên. Dùng xu hướng metric, sự thay đổi deploy, pool state, tải vào và test có kiểm soát để xác nhận. Nếu tất cả spans đều có vẻ nhanh nhưng request end-to-end chậm, phải tìm phần **không instrument**: ingress queue, TLS, app thread queue, proxy buffering, trình duyệt/network phía client hoặc gap do mất context.

## 13. Bài tập thực hành

**Bài 1 — Tính critical path.** Một API có chuỗi: auth 20 ms → gọi Inventory 250 ms **song song** với Pricing 80 ms → đợi cả hai → gọi Payment 140 ms → lưu DB 30 ms. Bỏ qua overhead. (a) Tổng latency gần đúng là bao nhiêu? (b) Nếu tối ưu Pricing còn 10 ms, latency giảm bao nhiêu? (c) Nếu tối ưu Inventory còn 90 ms, latency còn bao nhiêu? (d) Nếu Pricing tăng lên 310 ms, đường critical path đổi như thế nào?

**Bài 2 — Tìm đúng phụ thuộc.** Trace `POST /v1/orders` mất 900 ms. Span HTTP client gọi Inventory dài 600 ms, nhưng server Inventory chỉ dài 90 ms, và metric `pendingAcquire` của HTTP pool tăng cao. Hãy nêu ít nhất ba giả thuyết cần đo bổ sung và đề xuất giải pháp **không đơn giản là tăng CPU cho Inventory**.

**Bài 3 — Thiết kế instrumentation.** Vẽ trace cho Gateway → Orders → Inventory → PostgreSQL, có thêm task `CompletableFuture` và event `OrderCreated` sang worker. Chỉ ra nơi inject/extract `traceparent`, cách chọn parent/link cho job async, tên span ổn định và attributes được phép dùng. Chọn 5 dữ liệu nhạy cảm cần tuyệt đối tránh đưa vào trace.

**Bài 4 — SLO và sampling.** Một service chạy 5.000 request/s, mỗi request 12 spans. (a) Tính số spans/s khi thu 100%. (b) Ước lượng nếu head sampling độc lập 10% theo trace (giả sử các service cùng theo quyết định parent) thì còn bao nhiêu spans/s? (c) Vì sao không tính p99 từ tập trace được tail-sample ưu tiên lỗi/chậm?

**Bài 5 — Kiểm thử sự cố.** Tạo integration test có HTTP client gọi một stub Inventory, cho stub trả 503 hai lần rồi 200. Kiểm tra response API, timeout/retry budget và trace gồm các attempt hoặc events tương ứng. Lặp lại khi collector tắt: API vẫn hoạt động trong giới hạn tài nguyên, trace export có metric lỗi, và không có access token trong attributes.

**Gợi ý đáp án:** Bài 1: (a) `20 + max(250,80) + 140 + 30 = 440 ms`; (b) khoảng `0 ms` do Inventory vẫn lâu hơn; (c) `20 + max(90,80) + 140 + 30 = 280 ms`; (d) Pricing trở thành nhánh chặn, tổng `20 + 310 + 140 + 30 = 500 ms`. Bài 2: xem pool acquisition, DNS/TLS/network và số lần retry, so với server span và pending metrics. Bài 3: HTTP client inject, HTTP server extract; queue producer/consumer mang context/link; tên span không chứa user ID, payload hoặc token. Bài 4: (a) `60.000 spans/s`, (b) khoảng `6.000 spans/s` nếu sampling đồng nhất và bỏ qua overhead, (c) tập mẫu thiên lệch. Bài 5: xác minh cả chức năng lẫn khả năng quan sát và tình huống telemetry backend bị lỗi, không đánh đồng “traces không thấy” với “request không xảy ra”.
