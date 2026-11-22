# Quan sát API và theo dõi lỗi qua nhiều dịch vụ

Một người dùng gửi yêu cầu thanh toán tới API và nhận lỗi HTTP 502 sau vài giây. Phía trước là Azure Front Door hoặc Application Gateway, tiếp theo Azure API Management (APIM), một API Java trên Azure Container Apps/AKS, Azure Functions nhận tác vụ, Service Bus, và cuối cùng là Azure SQL Database. Mỗi thành phần đều có log riêng. Nếu chỉ đọc log của API gateway, nhóm vận hành có thể biết request thất bại nhưng không biết **ở chặng nào**, có phải do database, network, timeout, retry hay một deployment mới.

**API observability (quan sát API)** là khả năng suy luận trạng thái của hệ thống từ telemetry: **metrics, logs và distributed traces**, kết hợp ngữ cảnh release, topology, identity và yêu cầu nghiệp vụ. Mục tiêu không chỉ là tạo dashboard đẹp, mà là trả lời nhanh các câu hỏi:

- API nào đang ảnh hưởng người dùng, trong thời gian và khu vực nào?
- Request bắt đầu ở đâu, đi qua những dịch vụ nào và mắc lỗi ở bước nào?
- Lỗi thuộc client, gateway, backend, dependency hay network?
- Có thể tìm lại một yêu cầu theo trace ID/correlation ID mà không lộ dữ liệu nhạy cảm?
- Cần cảnh báo, rollback, giới hạn retry hay tăng tài nguyên?
- Phần giám sát có đáp ứng ngân sách và chính sách dữ liệu không?

Bài học thuộc chương **API và tích hợp quy trình** trong module **CLOUD_PROVIDERS_AZURE**. Nó kết nối từ subscription/resource group, Microsoft Entra ID, mạng ảo, API Management, Java services, Functions, Service Bus, Azure Monitor, Application Insights và Log Analytics đến bảo mật, triển khai và kiểm soát chi phí.

> **Phạm vi:** tên bảng KQL, trường log, loại metric và tích hợp telemetry phụ thuộc Azure resource, chế độ workspace-based Application Insights, SDK/agent và phiên bản. Các ví dụ bên dưới sử dụng schema thông dụng để học cách điều tra; trước khi dùng production, đối chiếu dữ liệu thực và metric definitions của tài nguyên trong subscription.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt monitoring và observability; hiểu ba tín hiệu metrics, logs và traces.
2. Chọn SLI/SLO thực tế cho API: availability, latency, error rate, throughput và độ chính xác nghiệp vụ.
3. Giải thích W3C Trace Context, **trace ID**, **span ID**, parent/child spans, **traceparent**, **tracestate**, và correlation ID.
4. Thiết kế propagation qua APIM, HTTP services, Azure Functions và message broker.
5. Cấu hình quy trình thu thập telemetry bằng **Azure Monitor**, **Application Insights**, **Log Analytics** và **OpenTelemetry**.
6. Viết truy vấn **KQL** để tìm request lỗi, dependency chậm, tương quan bằng OperationId/trace ID và nhận diện phát sinh sau deployment.
7. Phân biệt 4xx, 5xx, 429, 502/503/504, timeout, dependency failures và các lỗi business không hiện thành HTTP 5xx.
8. Thiết lập alerts có hành động và quy trình xử lý sự cố/rollback có thể thực hiện được.
9. Thiết kế sampling, retention, redaction, RBAC và kiểm soát chi phí telemetry.
10. Triển khai bài lab API nhiều dịch vụ và chứng minh được đường đi của một request lỗi.

## 2. Monitoring khác observability như thế nào?

**Monitoring** là việc thu thập tín hiệu đã biết và cảnh báo khi vượt ngưỡng: số lỗi mỗi phút, CPU sử dụng, tỷ lệ request thành công.

**Observability** rộng hơn: từ dữ liệu đã thu, nhóm kỹ thuật có thể đặt câu hỏi mới để suy ra nguyên nhân sự cố mà không nhất thiết phải biết trước mọi kiểu lỗi.

Ví dụ:

| Câu hỏi | Monitoring truyền thống | Observability |
|---|---|---|
| API có lỗi không? | Biểu đồ HTTP 5xx | Biểu đồ lỗi + đường đi từng request |
| Lỗi bắt đầu khi nào? | Alert và biểu đồ theo phút | Correlation với release, scale, dependency |
| Lỗi ở đâu? | Kiểm tra thủ công từng service | Trace cho biết span nào kéo dài/thất bại |
| Ai bị ảnh hưởng? | Tổng lỗi toàn hệ thống | Theo API route, region, environment, tenant nhóm an toàn |
| Cần hành động gì? | Tăng instance nếu CPU cao | Khắc phục đúng dependency/policy, tránh thay đổi sai chỗ |

Không có một công cụ duy nhất tự biến toàn hệ thống thành observable. Bạn cần **instrumentation nhất quán, context propagation, naming, quyền truy cập, thời gian đồng bộ và quy trình incident response**.

## 3. Ba trụ cột telemetry và bối cảnh chung

### Metrics

Metrics là các số đo tổng hợp theo thời gian: request count, response time, CPU, connection failures, queue backlog. Chúng phù hợp với dashboard và alert vì chi phí lưu/đọc thường dễ kiểm soát hơn log chi tiết cho mọi request.

Các loại thường gặp:

- **Counter:** số request, lỗi, timeout, retry.
- **Histogram:** phân phối latency và kích thước payload; phục vụ p50/p95/p99.
- **Gauge:** queue depth, số connection đang mở, instance khỏe, memory.
- **Up/down counter:** số request đang xử lý theo thời điểm.

Không nên chọn metric có quá nhiều nhãn giá trị độc nhất như **userId**, **orderId**, **raw URL**, **traceId**. Cardinality quá cao gây tăng chi phí và khó tổng hợp.

### Logs

Logs ghi lại sự kiện/chi tiết có cấu trúc: bắt đầu một workflow, mã lỗi database, request bị từ chối, kết quả retry. Log hữu ích khi phải xem **giá trị cụ thể** hoặc chuỗi hành động bên trong một thành phần.

Ví dụ structured log an toàn:

~~~json
{
  "timestamp": "2026-11-20T08:16:32Z",
  "level": "ERROR",
  "service": "payment-api",
  "environment": "production",
  "operation": "capturePayment",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "errorCode": "PAYMENT_PROVIDER_TIMEOUT",
  "attempt": 2,
  "durationMs": 2800
}
~~~

Không log card number, bearer token, session cookie, password, đầy đủ request/response body hoặc dữ liệu cá nhân không cần thiết.

### Distributed traces

Trace mô tả một hành trình logic qua nhiều dịch vụ. Mỗi bước là **span**, có thời gian, trạng thái, attributes và quan hệ parent/child hoặc links.

~~~mermaid
flowchart LR
  C["Client"] --> F["Front Door / App Gateway"]
  F --> A["API Management"]
  A --> J["Java Orders API"]
  J --> P["Payments API"]
  P --> SQL["Azure SQL"]
  J --> SB["Service Bus"]
  SB --> FN["Azure Function worker"]
~~~

Mỗi mũi tên **không tự động tạo span**; instrumentation và propagation phải hoạt động ở từng hop. Trace có thể có **khoảng trống** nếu một gateway không export spans, agent chưa bật hoặc sampling làm mất dữ liệu.

### Context bổ sung

Để xác định nguyên nhân, kết hợp telemetry với:

- Release/commit hash và thời gian triển khai.
- Region/zone và loại hosting plan.
- API name, route template, môi trường.
- Request path và dependency type đã được chuẩn hóa.
- Health/restart events, node pool upgrades.
- Incident, change record, maintenance window.
- Business outcome: đơn hàng thành công hay thất bại.

## 4. Thiết kế SLI/SLO trước khi chọn dashboard

**SLI (Service Level Indicator)** là đại lượng đo trải nghiệm; **SLO (Service Level Objective)** là mục tiêu về đại lượng đó trong một cửa sổ thời gian.

Ví dụ minh họa cho một API đặt hàng:

| SLI | Định nghĩa đề xuất | SLO minh họa |
|---|---|---|
| Availability | Yêu cầu hợp lệ thành công / yêu cầu hợp lệ | 99,9% trong 30 ngày |
| Latency | p95 duration tại điểm gần trải nghiệm client | Dưới 800 ms cho GET phù hợp |
| Error rate | 5xx và lỗi hệ thống xác định / yêu cầu đủ điều kiện | Dưới ngưỡng đã công bố |
| Async completion | Job hoàn tất đúng hạn / job được nhận | 99% trong 10 phút |
| Data correctness | Giao dịch không tạo hiệu ứng trùng/mất | Theo ràng buộc nghiệp vụ |

Các con số trên **chỉ để học cách đặt mục tiêu**, không phải SLA của dịch vụ Azure hay khuyến nghị dùng nguyên xi cho mọi ứng dụng.

### Chọn mẫu số đúng

Nếu endpoint đăng nhập trả 401 vì mật khẩu sai, đó có thể là kết quả mong đợi, không phải lỗi hệ thống. Nhưng nếu API trả 403 do RBAC bị triển khai sai và chặn mọi người dùng hợp lệ, đó là sự cố.

Do đó:

- **Không đếm mọi 4xx là lỗi availability** một cách máy móc.
- **Không coi mọi 200/202 là giao dịch thành công** nếu bên dưới job thất bại.
- Cân nhắc request hợp lệ, business outcome và API route quan trọng.
- Tách SLO cho GET nhanh, checkout và background job có đặc điểm khác nhau.

### Percentile và trung bình

Latency trung bình có thể ổn trong khi 5% người dùng chịu request chậm bất thường. Theo dõi **p50, p95, p99** khi lưu lượng đủ lớn và có nghĩa thống kê.

Chú ý percentile được tính trên tập request nào: theo region/route, sampled hay full, chỉ thành công hay gồm lỗi? Trộn các endpoint không cùng thời lượng có thể che giấu lỗi nghiêm trọng.

## 5. Chuẩn hóa tên endpoint, lỗi và dịch vụ

Một mô hình telemetry cần thống nhất:

| Thành phần | Nên ghi | Tránh |
|---|---|---|
| Service name | payment-api, orders-api | Pod/VM hostname thay đổi sau mỗi deploy |
| Environment | dev/staging/production | Bí danh mơ hồ như test2 |
| HTTP route | GET /orders/{orderId} | GET /orders/1024, GET /orders/1025 thành series khác nhau |
| Region | Azure region được chuẩn hóa | Tên tự đặt không có mapping |
| Release | Commit SHA hoặc version | Chỉ latest |
| Error code | DB_TIMEOUT, UPSTREAM_503 | Log raw exception không phân loại |
| Trace context | traceId, spanId, parent span | Tạo correlation ID mới tại mọi hop |
| Business ID | orderId dạng an toàn trong log theo chính sách | ID dùng làm metric label có cardinality quá lớn |

Một HTTP status 502 tại APIM không đủ phân biệt lỗi. Cần hiểu **backend status**, policy/gateway error, backend timeout hoặc APIM không kết nối được upstream. Vì vậy telemetry nên có **nơi quan sát và error classification** rõ ràng.

### Trace ID khác correlation ID nghiệp vụ

- **Trace ID:** một trace của một hành trình request.
- **Span ID:** một bước cụ thể trong trace.
- **Correlation ID:** ID do ứng dụng/đội vận hành thống nhất để nối các bước nghiệp vụ hoặc request; có thể tồn tại qua nhiều traces.
- **Order ID/job ID:** ID của đối tượng nghiệp vụ, có thể xuất hiện trong nhiều requests và traces.

Không thay thế hết các khái niệm này bằng một ID duy nhất. Khi retry một job bất đồng bộ, **job ID ổn định** nhưng trace/span IDs có thể khác; nên lưu liên kết phù hợp thay vì cưỡng ép mọi invocation dùng một trace ID cũ.

## 6. W3C Trace Context và header traceparent

**W3C Trace Context** là chuẩn được dùng rộng rãi để truyền ngữ cảnh trace qua HTTP. Header quan trọng:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Cấu trúc:

~~~text
version - trace-id (32 hex) - parent-id (16 hex) - trace-flags (2 hex)
00      - 4bf92f3577b34da6a3ce929d0e0e4736 - 00f067aa0ba902b7 - 01
~~~

- **trace-id:** cố gắng giữ ổn định trong các hop cùng hành trình.
- **parent-id:** ID span của phía gọi, giúp tạo quan hệ nhân quả; nó **thay đổi qua từng hop**.
- **trace-flags:** chứa thông tin như cờ sampled; không phải quyền truy cập hay cam kết mọi service đã ghi trace.
- **tracestate:** tùy chọn; dùng cho thông tin tracing vendor-specific theo quy tắc chuẩn.

Nếu dịch vụ tự tạo trace mới mà không đọc incoming traceparent, trace bị **đứt mạch**. Nếu hai service ghi cùng một trace ID nhưng thiếu parent/child quan hệ, điều tra vẫn khó hơn.

### Propagation đúng

1. Gateway nhận request, giữ/chuẩn hóa trace context theo chính sách.
2. Backend Java tiếp nhận context để tạo server span.
3. Khi gọi dependency HTTP, client instrumentation **inject** context vào outgoing request.
4. Dịch vụ downstream **extract** context và tạo span con.
5. Nếu gửi message, ghi trace context vào **message application properties/headers** phù hợp.
6. Consumer lấy context và tạo span/links tương ứng với quan hệ nhân quả.

Không tự viết chuỗi traceparent cố định cho mọi request. **Không dùng traceparent làm token chứng thực**; client bên ngoài có thể gửi header tùy ý, vì vậy gateway/receiver cần quyết định trust boundary và chính sách xử lý.

### Tracestate và baggage

**Baggage** có thể truyền thêm key/value giữa các dịch vụ; nó khác span attributes và có thể lan qua network. Không đưa email, số thẻ, secret, bearer token hoặc thông tin nhạy cảm vào baggage. Không phải mọi header metadata cần được copy từ Internet vào hệ thống private.

## 7. Distributed tracing qua HTTP và hàng đợi

Một luồng API không đồng bộ có thể diễn ra như sau:

~~~mermaid
sequenceDiagram
  participant C as Client
  participant G as API Management
  participant A as Orders API
  participant Q as Service Bus
  participant W as Function Worker
  participant D as Database
  C->>G: POST /orders (traceparent)
  G->>A: Forward request + trace context
  A->>D: Save order + outbox
  D-->>A: Commit
  A->>Q: Publish message + trace context
  A-->>G: 202 Accepted + jobId
  G-->>C: Response
  Q-->>W: Deliver message
  W->>D: Apply work idempotently
  D-->>W: Result
~~~

Trace propagation qua HTTP tương đối trực tiếp bằng W3C headers. **Qua queue/broker**, ngữ cảnh không tự trở thành HTTP headers: thư viện SDK/instrumentation phải truyền qua metadata message, hoặc ứng dụng phải inject/extract một cách có kiểm soát.

Ví dụ message chứa:

~~~json
{
  "jobId": "job-1024",
  "orderId": "order-1024",
  "schemaVersion": 1
}
~~~

Và **application properties** riêng như traceparent, tracestate nếu cần. Không nhất thiết đưa context vào JSON body; body nên giữ contract nghiệp vụ, trong khi tracing metadata có thể dùng broker headers/properties.

### Span links và async boundaries

Một consumer nhận nhiều message cùng lúc, hoặc một message được retry sau vài giờ, có thể cần **Span Links** thay vì luôn cố tạo quan hệ parent-child kéo dài. Lựa chọn phụ thuộc semantics và convention OpenTelemetry của messaging SDK/instrumentation. Quan trọng là có đường truy vết về producer/job ID và hiểu retry là invocation khác.

### At-least-once delivery

Trace giúp tìm ra hai lần chạy nhưng **không ngăn duplicate business effect**. Với Queue Storage, Service Bus, Event Grid và nhiều hệ thống event-driven, cần idempotency key, retry policy và DLQ/poison runbook. Telemetry phải phân biệt:

- Message ID/event ID từ producer.
- Delivery attempt hoặc dequeue/delivery count.
- Job ID/business key ổn định.
- Trace ID của lần xử lý tương ứng.
- Kết quả complete/abandon/dead-letter và outcome nghiệp vụ.

## 8. Azure observability stack: thành phần nào làm gì?

| Thành phần Azure | Trách nhiệm | Lưu ý |
|---|---|---|
| **Azure Monitor** | Nền tảng thu thập/đánh giá metrics, logs, alerts | Cần xác định đúng data source và retention |
| **Application Insights** | Application telemetry: requests, dependencies, exceptions, traces, availability | Workspace-based resource thường lưu dữ liệu vào Log Analytics |
| **Log Analytics workspace** | Truy vấn KQL và lưu logs theo bảng/workspace | RBAC, retention và ingestion có chi phí |
| **API Management diagnostics** | Theo dõi gateway traffic và lỗi từ APIM | Không đồng nghĩa tự có trace backend đầy đủ |
| **Azure resource diagnostic settings** | Gửi resource logs/metrics được hỗ trợ tới destination | Mỗi resource/category có schema và chi phí khác nhau |
| **Azure Monitor alerts** | Cảnh báo theo metrics/log queries hoặc các nguồn hỗ trợ | Thiết kế action groups, noise control và người nhận |
| **OpenTelemetry** | Chuẩn instrumentation/semantic conventions/exporters | Cần chọn pipeline/exporter/agent phù hợp |
| **Azure Service Health/Resource Health** | Tín hiệu trạng thái dịch vụ/tài nguyên nền tảng | Không thay thế application tracing |
| **Cost Management** | Theo dõi chi phí nền tảng/telemetry | Không chứng minh SLO của ứng dụng |

### Application Insights không phải Log Analytics workspace

Application Insights là resource/trải nghiệm application monitoring; Log Analytics workspace cung cấp nơi lưu/truy vấn dữ liệu log theo chế độ tích hợp. **Azure Monitor Metrics** còn có metric store riêng. Một dashboard có thể tổng hợp cả metrics và logs nhưng chúng **không có cùng retention, schema, chi phí hoặc tính năng**.

### Nguồn platform và nguồn application

- APIM/gateway logs giúp tìm gateway response, backend response và policy errors.
- Application Insights trong Java/Functions giúp tìm server request, dependency call, exception.
- AKS Container Insights/managed Prometheus giúp xem pod/node/container health.
- Service Bus metrics/logs giúp xem backlog, dead-letter và lỗi broker.
- SQL/Storage diagnostics giúp phân biệt backend throttle/timeout.
- Deployment change records giúp phát hiện regression theo phiên bản.

**Không chỉ bật APIM diagnostics rồi mong có full distributed tracing xuyên Java/SQL/Service Bus.** Cần instrumentation tại những thành phần có giá trị, kiểm tra propagation và sampling xuyên pipeline.

## 9. Điểm quan sát tại API Management

Azure API Management thường đứng ở giữa client và backend. Những câu hỏi quan trọng:

1. Client có gọi đúng API/operation không?
2. Gateway nhận request hay thất bại trước khi vào backend?
3. Authentication, rate limit, quota hoặc policy có từ chối request không?
4. Gateway đã forward backend URL nào (đã giảm/ẩn thông tin nhạy cảm)?
5. Backend có trả status hay gateway timeout khi gọi?
6. Tổng thời gian của gateway khác thời gian backend bao nhiêu?
7. Lỗi có chỉ xảy ra với một region, revision, subscription hoặc route?

### Gateway status khác backend status

Ví dụ APIM trả HTTP 504 tới client vì **upstream timeout**. Backend có thể vẫn đang xử lý. Nếu client retry ngay, nghiệp vụ có thể bị thực hiện hai lần. Trace phải giúp phân biệt:

~~~text
Client HTTP 504
  -> APIM gateway timeout at 30s
  -> Backend /orders vẫn chạy, hoàn tất sau đó
  -> Client retry với cùng job/order ID
~~~

Đây là ví dụ cơ chế lỗi, không phải cấu hình timeout mặc định cố định của APIM.

### APIM diagnostics và Application Insights

APIM có các khả năng diagnostics/integration để gửi dữ liệu gateway vào telemetry destinations được hỗ trợ. Cần cấu hình ở scope phù hợp và kiểm soát:

- Logger/diagnostics settings phù hợp resource và API.
- Tỷ lệ sampling và chọn dữ liệu request/response.
- Các header nào được phép ghi log; tránh Authorization, Cookie, Set-Cookie.
- Body logging phải cực kỳ hạn chế hoặc tắt theo chính sách.
- Client IP, tenant/user ID và query parameters phải được đánh giá bảo vệ dữ liệu.
- Quyền và kết nối tới Application Insights/Log Analytics.

### Không dùng debug trace không được phép trên production

Các chức năng tracing/debug APIM có cơ chế quyền và cách sử dụng thay đổi theo phiên bản/tier. Không mặc định mọi client có thể bật verbose APIM trace bằng một header cũ. Với production, ưu tiên diagnostics có kiểm soát, redaction, least privilege và quy trình điều tra được phê duyệt.

## 10. Azure Application Insights: request, dependency, exception

Khi ứng dụng Java được instrument, thường có các nhóm telemetry:

| Nhóm | Nội dung | Câu hỏi |
|---|---|---|
| Requests | Endpoint, thời gian, status, success, operation context | API nào chậm hoặc lỗi? |
| Dependencies | HTTP/SQL/Storage/messaging calls đã được hỗ trợ | Dependency nào gây latency/failure? |
| Exceptions | Loại lỗi, stack và ngữ cảnh | Tại sao request fail? |
| Traces (logs) | Log ứng dụng có mức độ và context | Handler thực hiện những bước nào? |
| Custom events/metrics | Business milestones hoặc số đo riêng | Order hoàn tất đúng hạn không? |
| Availability | Synthetic tests nếu được cấu hình | Endpoint có thể truy cập từ outside? |

**Đừng nhầm bảng AppTraces với distributed trace tree**: AppTraces thường lưu log message có correlation; tree cần các request/dependency spans liên hệ.

### Instrumentation tự động có giới hạn

Agent Java có thể tự ghi một số HTTP, JDBC, messaging calls và exceptions tùy agent/library version. Nhưng nó không biết **nghiệp vụ “reserve inventory”** nếu bạn không tạo span/metric hoặc log thích hợp. Muốn biết bước reserve inventory tốn 1,8s hay DB query 1,2s, thêm **custom spans** ở vị trí có ý nghĩa.

## 11. OpenTelemetry và Java: cách bắt đầu

**OpenTelemetry (OTel)** cung cấp API/SDK/auto-instrumentation/semantic conventions cho metrics, traces và logs. Đối với Java service, thường chọn một trong các phương án:

1. **Azure Monitor OpenTelemetry Java distribution/agent** theo phiên bản được hỗ trợ, export telemetry tới Azure Monitor/Application Insights.
2. **OpenTelemetry Java agent** với exporter/pipeline (OTLP collector hoặc exporter tương thích) đã được cấu hình và bảo vệ.
3. Instrumentation thủ công bằng OTel API/SDK cho business spans, kết hợp auto-instrumentation khi cần.

Đừng chạy đồng thời nhiều Java tracing agents cùng instrument HTTP/JDBC trong một JVM nếu chưa thử; dễ sinh **duplicate spans, context conflict và overhead**.

### Ví dụ cấu hình hướng đi

~~~text
Java API on Container Apps / AKS / App Service
  -> OTel instrumentation/agent
  -> (option A) Azure Monitor exporter / supported distribution
  -> Application Insights + Log Analytics workspace

Java API
  -> OTel Java agent (OTLP)
  -> OTLP collector được quản trị
  -> exporter/ingestion endpoint được hỗ trợ
  -> Azure Monitor / storage tương ứng
~~~

Hai phương án không phải **lệnh thay thế tương đương 1:1**. Cần kiểm tra agent, exporter, environment variables, auth và các giới hạn được Azure hỗ trợ tại thời điểm triển khai.

### Java agent injection — ví dụ dạng khái niệm

Nếu đã tải và kiểm tra **một Java agent được tổ chức phê duyệt**, có thể khởi động app với:

~~~bash
java -javaagent:/opt/telemetry/approved-agent.jar -jar orders-api.jar
~~~

Đường dẫn là placeholder; cấu hình exporter, service name, version, environment, connection string/credentials và sampling phải được khai báo riêng theo loại agent. Không tải agent từ URL ngẫu nhiên ở mỗi lần khởi động production hoặc gắn bí mật vào command line.

### Resource attributes có ích

- service.name = orders-api
- service.version = 2.3.7 hoặc commit hash
- deployment.environment.name = production (theo semantic conventions/SDK đang sử dụng)
- cloud.region = southeastasia khi có nguồn dữ liệu chính xác
- k8s.namespace.name / k8s.pod.name nếu workload chạy trên AKS

Không dùng resource attributes chứa identity khách hàng cụ thể hoặc token. Tên attribute theo semantic conventions có thể thay đổi theo phiên bản; thống nhất trong hệ thống và xác minh bằng dữ liệu xuất ra.

## 12. Java: thêm custom span cho bước nghiệp vụ

Ví dụ với **OpenTelemetry API** trong một Java service đã có tracing provider do agent/SDK cấu hình. Đoạn code minh họa span cho một thao tác nghiệp vụ:

~~~java
import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;

public final class InventoryTracing {

    private static final Tracer tracer =
        GlobalOpenTelemetry.getTracer("commerce.orders", "1.0");

    public void reserve(String orderId) {
        Span span = tracer.spanBuilder("inventory.reserve").startSpan();
        try (Scope scope = span.makeCurrent()) {
            span.setAttribute("business.operation", "reserveInventory");

            // Call the real inventory service using an instrumented client.
            reserveInInventoryService(orderId);

        } catch (RuntimeException ex) {
            span.recordException(ex);
            span.setStatus(StatusCode.ERROR);
            throw ex;
        } finally {
            span.end();
        }
    }

    private void reserveInInventoryService(String orderId) {
        // Replace with actual idempotent business logic and HTTP/SDK call.
        throw new UnsupportedOperationException("Example only");
    }
}
~~~

**Đây là ví dụ minh họa cách instrument, không phải class nghiệp vụ chạy ngay**: method thực chưa được triển khai; phải thay placeholder trước khi chạy. Cần dependency OpenTelemetry API có version tương thích; cung cấp tracer provider/exporter từ agent/SDK trước khi gọi.

Lưu ý:

- **Span name** có cardinality thấp và ý nghĩa, không dùng tên chứa orderId.
- **Attributes** không chứa PII hoặc secret; nếu cần ID nghiệp vụ cho điều tra, áp dụng policy về nhạy cảm, retention và sampling.
- **recordException + setStatus(ERROR)** giúp trace biểu thị lỗi trong các SDK hỗ trợ.
- **finally span.end()** bảo đảm span kết thúc cả khi exception.
- `Scope` giúp span là current context trong block, thuận lợi cho client instrumentation tạo child spans.
- Xử lý lỗi phải giữ đúng exception propagation, không silently swallow failure vì muốn metric đẹp.

## 13. Propagate context từ Java HTTP client

Với Java HttpClient, nếu auto-instrumentation phù hợp đã hoạt động, context có thể được inject tự động. Nếu viết client tùy biến hoặc SDK chưa được hỗ trợ, có thể inject W3C context qua OTel propagator.

Ví dụ **đoạn rút gọn** trong một request handler có active span:

~~~java
import java.net.URI;
import java.net.http.HttpRequest;

import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.context.Context;

HttpRequest.Builder builder = HttpRequest.newBuilder()
    .uri(URI.create("https://inventory.internal.example/api/reserve"))
    .POST(HttpRequest.BodyPublishers.noBody());

GlobalOpenTelemetry.getPropagators()
    .getTextMapPropagator()
    .inject(Context.current(), builder,
        (carrier, key, value) -> carrier.header(key, value));

HttpRequest outgoing = builder.build();
// Send using an appropriately configured HttpClient and policy.
~~~

Đây là **snippet**, không phải chương trình hoàn chỉnh. Tracer provider phải được cấu hình W3C propagation và request phải được gửi từ scope đúng. Không vừa auto inject vừa tự inject trùng lặp mà chưa xác nhận hành vi client.

**Không copy toàn bộ incoming headers** từ client ngoài Internet sang downstream. Chỉ truyền các header cần thiết được cho phép; Authorization/cookie không được lan qua trust boundaries một cách tự động.

### Các ca kiểm tra

- Incoming traceparent hợp lệ → server span được gắn đúng trace.
- Outgoing HTTP call → downstream span có cùng trace ID và parent hợp lý.
- HTTP call timeout/retry → mỗi attempt có span/attribute đủ để phân biệt.
- Client ngắt kết nối → backend có thể vẫn xử lý; cần business idempotency.
- Gateway đổi route hoặc proxy → trace context không bị drop ngoài ý muốn.

## 14. Propagation qua Service Bus và Azure Functions

Một request có thể nhận đơn, phát message, rồi worker xử lý sau vài giây hoặc vài phút. HTTP trace cần được liên hệ với lần xử lý background nhưng các mốc đó có tính không đồng bộ.

### Producer

- Tạo message chứa **jobId/orderId ổn định**.
- Lưu hoặc inject **traceparent/tracestate** vào application properties của message theo SDK/instrumentation hỗ trợ.
- Ghi event “enqueued” trong log/span phù hợp với producer.
- Trả HTTP **202 Accepted** khi job đã được nhận và lưu bền vững theo cam kết API.

### Consumer

- Đọc message và trace context.
- Dùng SDK instrumentation hoặc explicit extract để xây consumer span / span link.
- Ghi attempt number, queue/topic, worker service, status xử lý theo conventions.
- Nếu lỗi, log exception không chứa message body nhạy cảm.
- Hoàn tất/abandon/dead-letter theo semantics của broker và nghiệp vụ.
- Chỉ đánh dấu job thành công khi output đã được lưu bền vững.

### Không coi connection giữa spans là tự động

Azure Functions và Service Bus có instrumentation riêng theo runtime/extension/SDK; một số phiên bản có khả năng liên kết trace tự động, một số không. Hãy kiểm tra **traces thực tế sau một message thử**. Nếu consumer không được liên kết, dùng application properties hoặc link theo chuẩn được agent hỗ trợ.

### Tách retry invocation

Nếu message được giao lại 3 lần, có thể có **3 processing spans**, mỗi span kèm attempt info và cùng job ID. Đó là điều mong muốn: sự lặp lại có ý nghĩa. Đừng gộp chúng thành một span kéo dài vô hạn hoặc tạo một **business success** giả vì lần thử đầu thất bại.

## 15. Workspace-based Application Insights và KQL

Khi Application Insights liên kết Log Analytics workspace, dữ liệu ứng dụng thường có các bảng như:

| Loại telemetry | Bảng workspace-based thường gặp |
|---|---|
| Server requests | **AppRequests** |
| Outbound dependencies | **AppDependencies** |
| Application exceptions | **AppExceptions** |
| Application log/trace messages | **AppTraces** |
| Custom events | **AppEvents** |

Ở schema/Application Insights environment khác, có thể gặp các tên **requests**, **dependencies**, **exceptions**, **traces** trong trải nghiệm classic. Query KQL dưới đây giả định **workspace-based App*** tables và các trường tương ứng; nếu dữ liệu trong workspace của bạn khác, xem schema thực rồi điều chỉnh.

### Truy vấn 1 — Request lỗi 5xx trong giờ gần nhất

~~~kusto
AppRequests
| where TimeGenerated >= ago(1h)
| where toint(ResultCode) >= 500 and toint(ResultCode) < 600
| project TimeGenerated, OperationId, Name, ResultCode,
          DurationMs, Success, Url
| order by TimeGenerated desc
| take 100
~~~

Dùng để tìm **OperationId** của request lỗi cụ thể và đối chiếu thời gian. Cần bảo vệ quyền truy cập vì cột Url có thể chứa query parameters nhạy cảm; trên dashboard chia sẻ rộng nên chỉ chọn route template hoặc xử lý masking.

### Truy vấn 2 — Tỷ lệ lỗi và p95 theo route

~~~kusto
AppRequests
| where TimeGenerated >= ago(6h)
| summarize
    Requests = count(),
    Failed = countif(Success == false),
    P95Ms = percentile(DurationMs, 95)
  by bin(TimeGenerated, 5m), Name
| extend ErrorRatePct =
    iff(Requests == 0, 0.0, 100.0 * todouble(Failed) / Requests)
| order by TimeGenerated asc
~~~

**Lưu ý:** `Success` có thể được SDK xác định khác business outcome. Query đo lỗi theo telemetry đang thu, không tự đồng nghĩa SLI availability đã chuẩn hóa. Nếu sampling/ingestion transform có hiệu lực, phải xác định cách trọng số/sampling ảnh hưởng các phép đếm; không kết luận số request tuyệt đối là chính xác khi telemetry không đầy đủ.

### Truy vấn 3 — Dependency failures

~~~kusto
AppDependencies
| where TimeGenerated >= ago(2h)
| where Success == false
| summarize Failures = count()
  by Name, Target, ResultCode
| top 20 by Failures desc
~~~

Nếu dependency SQL hoặc HTTP không xuất hiện dù request lỗi, có thể do instrumentation thiếu, sampling, thư viện chưa được hỗ trợ hoặc truy cập không tạo telemetry. Không suy rằng dependency đã thành công chỉ vì không có log.

### Truy vấn 4 — Toàn bộ dữ liệu cùng OperationId

~~~kusto
let chosenTrace = "4bf92f3577b34da6a3ce929d0e0e4736";
union withsource=SourceTable
    AppRequests, AppDependencies, AppTraces, AppExceptions
| where TimeGenerated >= ago(24h)
| where OperationId == chosenTrace
| project
    TimeGenerated,
    SourceTable,
    OperationId,
    SpanOrParentId = tostring(column_ifexists("ParentId", "")),
    ItemName = tostring(column_ifexists("Name", "")),
    MessageText = tostring(column_ifexists("Message", "")),
    ResultCode = tostring(column_ifexists("ResultCode", ""))
| order by TimeGenerated asc
~~~

OperationId trong Application Insights thường được dùng cho correlation và có thể tương ứng với W3C trace ID khi pipeline tích hợp đúng. **Đừng mặc định tất cả resource diagnostic logs của APIM/Service Bus cũng có cùng OperationId**: mỗi nguồn có schema/context khác nhau. Cần kiểm chứng mapping, cách export trace, và có thể dùng correlation ID/traceparent ở từng hệ thống.

### Truy vấn 5 — Exception tăng sau một release

~~~kusto
AppExceptions
| where TimeGenerated >= ago(4h)
| summarize Errors = count()
  by bin(TimeGenerated, 10m),
     ExceptionType = tostring(column_ifexists("ExceptionType", "unknown"))
| order by TimeGenerated asc
~~~

Gắn thêm release/version khi telemetry thật có attribute này. Không tự viết tên cột `deploymentVersion` trong KQL nếu schema của bạn chưa có; custom attributes thường được lưu trong một trường dynamic hoặc resource metadata theo pipeline.

## 16. Điều tra lỗi tại nhiều tầng: ví dụ HTTP 502

Giả sử client nhận HTTP 502 khi gọi **POST /orders**.

### Bước 1 — Bắt đầu từ triệu chứng

Thu thập:

- Thời điểm chính xác theo UTC và region.
- Route template, HTTP method và client result.
- Trace ID/correlation ID nếu response cung cấp an toàn.
- Tỷ lệ 502 theo 5 phút và trend trước/sau.
- Release/incident/change gần thời điểm xảy ra.

Không cần xin payload chứa thẻ thanh toán hoặc token để bắt đầu điều tra.

### Bước 2 — Nhìn lớp gateway

Tại Front Door/Application Gateway/APIM, tìm request tương ứng bằng timestamp/ID trong log được cấu hình. Phân biệt:

- Backend đã trả 502?
- Gateway nhận 503 từ backend rồi map thành 502?
- Gateway tự trả 502 vì kết nối upstream bị reset?
- Policy authentication/transformation/timeout gây thất bại?
- Có WAF block/rate limit hay health probe fail?

### Bước 3 — Truy trace ở backend

Trong Application Insights, tìm **AppRequests** bằng OperationId/correlation và kiểm tra dependency spans:

~~~text
Client: 502 in 3.2s
  APIM: upstream call failed
    Orders API: duration 2.9s, status 500
      Inventory API: 200 in 60ms
      Payment API: 503 in 2.4s
        Third-party gateway: timeout/retry
~~~

Đây là **trace giả định minh họa**, không phải kết quả thu từ một môi trường đang chạy. Nếu API/backend không có span tương ứng, điều tra instrumentation và context propagation trước khi suy rằng request không đi tới đó.

### Bước 4 — Kiểm tra dependency và nền tảng

- Payment API có bị restart, hết connection pool, DNS lỗi hoặc SSL handshake fail?
- Azure SQL/Storage có throttling, timeout hoặc quota?
- Service Bus có backlog tăng, DLQ tăng hoặc consumer lỗi?
- Có deployment thay config endpoint/secret/cert gần thời điểm đó?
- Node pool, HPA, CPU/memory, connection saturation có bất thường?
- Có Azure Service Health incident hay resource health degradation?

### Bước 5 — Khắc phục và chứng minh

Nếu lỗi do release mới, rollback hoặc tắt feature theo quy trình. Nếu do dependency chậm, giới hạn retry, timeout budgets, circuit breaker hoặc capacity, nhưng phải cân nhắc tác động nghiệp vụ. Sau khắc phục:

1. Test lại endpoint chính.
2. Theo dõi rate 5xx/p95 ít nhất qua khoảng phù hợp traffic.
3. Đo business success, không chỉ HTTP 200.
4. Xác nhận backlog/poison messages được xử lý.
5. Ghi root cause, blast radius và hành động phòng ngừa.

## 17. Phân loại mã lỗi và tránh cảnh báo sai

| Mã/tín hiệu | Ý nghĩa thường gặp | Cần điều tra |
|---|---|---|
| **400** | Client gửi dữ liệu không hợp lệ | Validation, version/schema mismatch |
| **401** | Chưa xác thực | Token/credential, clock skew, auth gateway |
| **403** | Không đủ quyền hoặc policy chặn | Entra RBAC, app authorization, Storage firewall |
| **404** | Resource không tồn tại hoặc route sai | URL/template, deployment routing |
| **409** | Xung đột trạng thái hoặc duplicate operation | Idempotency/business lock |
| **429** | Rate limit/throttling | APIM policy, downstream quota, retry-after |
| **500** | Lỗi server chưa được xử lý | Exception, dependency, code regression |
| **502** | Gateway không nhận upstream response hợp lệ | Backend reset, policy/mapping, TLS |
| **503** | Service tạm không khả dụng | Capacity, backend unhealthy, throttling |
| **504** | Gateway timeout | Deadline, network, service latency |
| **Timeout client** | Caller ngừng đợi trước khi có response | Không suy rằng backend đã dừng |
| **Job DLQ** | Message không hoàn tất theo chính sách | Retry, poison, schema, business failures |

**Mã HTTP là tín hiệu, không phải nguyên nhân gốc.** Một 403 từ Storage có thể là data-plane RBAC, SAS không hợp lệ, public network bị khóa hoặc policy; cần xem error code/message và log thích hợp.

### Business errors không hiện 5xx

Một API trả HTTP 202 sau khi ghi queue. Sau đó worker không xử lý được và message vào DLQ. Nếu chỉ đo request 5xx, hệ thống có thể trông hoàn hảo dù đơn hàng không hoàn tất. Cần metric **end-to-end completion**: accepted → started → completed/failed, gắn job ID ổn định và deadline.

## 18. Retry, timeout, circuit breaker và telemetry

Trong hệ thống phân tán, retry có thể giúp xử lý lỗi tạm nhưng cũng có thể làm sự cố nặng hơn.

### Timeout budget xuyên dịch vụ

Nếu client chỉ chờ tối đa 5 giây nhưng API gọi hai downstream liên tiếp, mỗi nơi timeout 5 giây, tổng thời gian có thể vượt ngưỡng client. Cần phân bổ **end-to-end deadline** và timeout tại mỗi hop.

~~~text
Client deadline: 5s
  API handling & validation: < 0.5s
  Inventory dependency: < 1s
  Payment dependency: < 2s
  DB/serialization/margin: phần còn lại
~~~

Các số chỉ để minh họa cách phân bổ, không phải chuẩn timeout cho mọi giao dịch.

### Retry với backoff/jitter

- Retry lỗi tạm thời như một số HTTP 429/503/timeouts khi operation an toàn để thử lại.
- Tôn trọng `Retry-After` khi áp dụng.
- Dùng exponential backoff + jitter để tránh đồng loạt gọi lại.
- Giới hạn số attempt và tổng deadline.
- Ghi attempt count và outcome để biết request "thành công sau 4 lần" vẫn có chi phí.
- Đừng retry mọi 400/401/403 hoặc lỗi nghiệp vụ vĩnh viễn.

### Idempotency

Timeout của `POST /payments` **không chứng minh giao dịch chưa xảy ra**. Nếu retry, cần idempotency key và hệ thống đối tác cho phép truy vấn kết quả/đối soát. Trace cho biết hai HTTP attempts, nhưng **không thay thế transaction hoặc idempotency logic**.

### Circuit breaker

Khi một dependency thất bại kéo dài, circuit breaker có thể từ chối sớm để tránh làm cạn connection/thread pool. Telemetry cần phân biệt "short-circuited" với "downstream timeout", nếu không vận hành có thể hiểu sai rằng dependency đã hồi phục.

## 19. Logging có cấu trúc cho Java API

Log nên là cấu trúc máy đọc được, dễ filter theo service, route, error code và trace context. Ví dụ concept:

~~~json
{
  "time": "2026-11-20T09:12:30Z",
  "severity": "WARN",
  "service": "orders-api",
  "route": "POST /orders",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "f36b6d1935c1a055",
  "operation": "reserveInventory",
  "errorCode": "UPSTREAM_429",
  "retryAttempt": 1,
  "durationMs": 1150,
  "release": "2.3.7"
}
~~~

### Tương quan logs và traces

Trong Java, nhiều logging frameworks hỗ trợ **MDC (Mapped Diagnostic Context)**; instrumentation có thể tự chèn trace/span IDs vào MDC hoặc log attributes theo cấu hình. Đừng mặc định chỉ cài OpenTelemetry dependency là mọi log đã mang trace ID.

Kiểm thử bằng cách:

1. Gọi API với request thử.
2. Lấy trace ID từ log/spans.
3. Tìm tất cả log của cùng trace ID.
4. Xác minh khi gọi downstream context không mất.
5. Kiểm tra async thread pool/reactive pipeline vẫn propagation context; những chuyển luồng có thể cần instrumentation riêng.
6. Xác nhận secrets/PII không nằm trong log.

### Không dùng stack trace cho mọi lỗi hợp lệ

Validation 400 thường không cần stack trace dày đặc. Lỗi hạ tầng/bug 500 mới cần exception detail đầy đủ trong nơi có quyền hạn chế. Phân loại lỗi giúp giảm alert fatigue và chi phí lưu log.

## 20. Observability trong Azure Functions, Container Apps và AKS

### Azure Functions

- Application Insights/agent/extension theo runtime hỗ trợ.
- Theo dõi invocation, duration, exception và dependency.
- Với Queue/Service Bus trigger, liên hệ **message ID, delivery attempt, trace context và business outcome**.
- Không chỉ đo function success: nếu handler swallow exception rồi trả bình thường, broker có thể complete message dù nghiệp vụ thất bại.
- Cold start và runtime scaling có thể ảnh hưởng latency.

### Azure Container Apps

- Theo dõi revision, replica count, ingress requests, container logs và metrics theo khả năng dịch vụ.
- Kết nối application instrumentation Java tới Azure Monitor/OTel pipeline được hỗ trợ.
- So sánh lỗi theo **revision** để phát hiện regression.
- Cấu hình health probes phù hợp; một container đang Running nhưng NotReady chưa phục vụ được request.

### Azure Kubernetes Service

- Application tracing chạy bên trong pod; cluster/node metrics bổ sung ngữ cảnh hạ tầng.
- Gắn service.name, namespace, pod, node, version qua resource attributes theo policy.
- Liên hệ request failures với HPA, node restart, pod OOMKilled, ingress controller và rollout.
- Phân biệt service-level 503 do **không có ready endpoints** với 503 do dependency upstream.
- Kiểm tra network policy, DNS/private endpoint và cross-node latency khi có lỗi.

### APIM/Frontend với backend

Nhìn hai hướng:

1. **Gateway telemetry**: client-facing status, throttle, policy, backend call.
2. **Application telemetry**: handler/dependency/DB and business result.

Chỉ khi nối được hai bên bằng trace/correlation và timestamp, hệ thống mới cho khả năng tìm root cause xuyên lớp đủ tin cậy.

## 21. Azure CLI: quan sát cấu hình mà không tiết lộ secret

Ví dụ lệnh đọc trên **Azure Cloud Shell Bash** hoặc Azure CLI cài đặt phù hợp. Dùng đúng subscription và quyền được phê duyệt; không in connection strings/API keys.

~~~bash
az account show \
  --query "{subscription:name,id:id,tenant:tenantId}" \
  --output table
~~~

Lấy thông tin Application Insights resource đã tồn tại:

~~~bash
RG="rg-observability-lab"
APPINSIGHTS="appi-orders-lab"

az monitor app-insights component show \
  --resource-group "$RG" \
  --app "$APPINSIGHTS" \
  --query "{name:name,location:location,workspaceId:workspaceResourceId}" \
  --output json
~~~

Cần Azure CLI/extension phù hợp và resource đã tồn tại; availability của lệnh và query fields tùy phiên bản API. Nếu phần `workspaceResourceId` không được trả về, kiểm tra resource configuration bằng cách đọc các property **không nhạy cảm** thay vì suy đoán.

### Kiểm tra diagnostic settings của một resource

~~~bash
RESOURCE_ID="<EXISTING_RESOURCE_ID>"

az monitor diagnostic-settings list \
  --resource "$RESOURCE_ID" \
  --output json
~~~

Diagnostic settings **không giống auto-instrumentation ứng dụng**: resource có thể gửi platform logs nhưng không có spans Java.

### Kiểm tra alert rules

~~~bash
az monitor metrics alert list \
  --resource-group "$RG" \
  --output table
~~~

Một môi trường còn có alert log search, activity log hoặc alert rules thế hệ khác. Không chỉ dựa vào một lệnh list metrics alerts rồi kết luận không có cảnh báo.

### Cảnh giác với Application Insights connection string

Connection string cấu hình ingestion/routing telemetry, **không phải chứng chỉ chứng minh người gọi có quyền truy cập dữ liệu**. Hạn chế phân tán trong source và logs, quản lý theo quy trình cấu hình; bảo vệ resource bằng RBAC/ingestion access controls được hỗ trợ. Không nhầm nó với API Management subscription keys hoặc Storage account keys.

## 22. Thiết kế alert gắn với SLO và hành động

Một alert tốt phải giúp đội trực biết **cần làm gì**. Ví dụ:

| Alert | Điều kiện tham khảo | Hành động |
|---|---|---|
| Error rate tăng | 5xx/error SLI vượt baseline đủ thời gian | Xem route, trace, release |
| P95 latency xấu | p95 vượt SLO với lưu lượng đáng kể | Tìm slow dependency, saturation |
| Dependency 503/429 | Tỷ lệ lỗi/throttle tăng | Kiểm tra quota, backoff, downstream |
| Queue backlog/age | Oldest job vượt deadline | Scale worker, DLQ/poison investigation |
| API thành công nhưng business fail | Job completed ratio giảm | Kiểm tra async workflow và idempotency |
| Missing telemetry | Một service mất heartbeats/telemetry | Kiểm tra exporter, ingestion, network |
| Cost spike | Log ingestion/retention tăng bất thường | Điều chỉnh debug/sampling, tìm loop |

### Đừng chỉ đặt ngưỡng tĩnh

Một route chỉ có vài request mỗi đêm: một lỗi đơn lẻ tạo tỷ lệ thất bại 100%, nhưng có thể không cần gọi toàn bộ đội trực. Ngược lại, một route thanh toán có 100.000 request/giờ chỉ cần tăng 1% lỗi cũng ảnh hưởng lớn.

Kết hợp:

- Tỷ lệ và **số lượng lỗi tuyệt đối**.
- Cửa sổ thời gian và mức traffic.
- Mức độ quan trọng của endpoint.
- SLO/error budget, burn rate nếu đội sử dụng SRE.
- Region/service/version.
- Phân biệt synthetic tests và user requests.
- Khả năng thực hiện hành động cụ thể.

### Action groups và incident response

Đặt người nhận/nhóm trực, severity, escalation, link dashboard, runbook, thời gian maintenance và thông tin điều tra cơ bản. Không gửi payload nhạy cảm qua email/SMS của alert. Khi alert được xử lý, lưu incident timeline và kết quả để cải tiến định nghĩa alert.

## 23. Sampling, cardinality và chi phí telemetry

Ghi toàn bộ request và dependency spans có thể rất tốn ingestion, storage, query và làm giảm tín hiệu quan trọng trong khối dữ liệu lớn.

### Sampling là gì?

**Sampling** chọn một phần traces/telemetry để lưu lại. Nó giúp giảm chi phí nhưng làm mất một số yêu cầu trong dữ liệu chi tiết.

- **Head sampling:** quyết định sớm dựa trên context, service/route/rule.
- **Tail sampling:** quyết định sau khi thu thập đủ spans để xét lỗi/latency; đòi pipeline/collector phù hợp và có overhead.
- **Adaptive sampling:** thay đổi tỷ lệ theo tải theo khả năng của SDK/agent/pipeline.

**Không trộn sampling thiếu kiểm soát ở gateway, app và collector**: có thể chỉ giữ một số spans, tạo trace không hoàn chỉnh.

### Đếm request khi sampled

Nếu chỉ thu 10% requests, `count()` từ bảng telemetry không nhất thiết là traffic thật. Cần hiểu **sampling weight** (ví dụ ItemCount trong một số schema) hoặc dùng **platform metrics** phù hợp để tính SLI/count. Đối với tỷ lệ lỗi, head sampling có thể thiên lệch nếu các nhóm/route được sample khác nhau.

### Cardinality

Metric tag chứa `orderId`, `userId`, full URL có ID hoặc traceId tạo hàng triệu chuỗi riêng. Nên sử dụng:

- Route template thay full path.
- Service name cố định thay hostname ephemeral khi aggregate.
- Error code từ taxonomy hạn chế.
- Environment, region, method và result status đã chuẩn hóa.

ID cụ thể thích hợp hơn trong **logs/traces có quyền hạn chế** chứ không phải metric dimensions ở mọi request.

### Retention

Chọn thời gian giữ logs/traces theo nhu cầu điều tra, tuân thủ và ngân sách. Giữ dữ liệu thô vô hạn không phải yêu cầu của observability. Có thể tổng hợp metrics lâu hơn và giữ traces chi tiết trong thời gian ngắn hơn theo policy. Với security/audit logs có yêu cầu pháp lý, cần retention riêng, không tùy tiện giảm.

## 24. Privacy và bảo mật của hệ thống quan sát

Telemetry có thể tiết lộ route, tenant, tên bảng, lỗi database, hostname và thậm chí dữ liệu cá nhân. Khi triển khai tracing tự động, phải kiểm tra **những trường được agent thu thập mặc định**, không chỉ code log do đội tự viết.

### Những thứ thường không nên thu thập

- Authorization headers, access/refresh tokens, API keys.
- Cookie/session identifiers hoặc password.
- Raw credit card/payment information.
- Body HTTP request/response và payload message chứa PII trừ khi được phê duyệt rất cụ thể.
- Full URL với query string có email/token hoặc ID nhạy cảm.
- SQL query có literal dữ liệu nhạy cảm.
- Baggage chứa thông tin khách hàng, tenant secret.

### Biện pháp

1. **Redaction trước ingestion** khi có thể; không dựa hoàn toàn vào query masking.
2. Dùng route templates và error-code taxonomy.
3. Least-privilege Azure RBAC trên workspace/App Insights/APIM.
4. Tách production telemetry khỏi dev/staging theo nhu cầu và quyền.
5. Quản lý network/Private Link, ingestion endpoints và export destinations theo tính năng hỗ trợ.
6. Rà soát data residency, cross-region replication và retention.
7. Kiểm tra sampling/collection policy với nhóm security/compliance.
8. Audit việc bật verbose tracing hoặc truy vấn dữ liệu nhạy cảm.

### Trace context không xác thực người gọi

Kẻ ngoài có thể tự tạo traceparent hoặc correlation ID để cố gắng gây nhiễu dữ liệu. AuthN/AuthZ dùng Entra ID, tokens/managed identity hoặc cơ chế được phê duyệt. Tracing metadata là **dữ liệu không đáng tin** từ client tại ranh giới vào; xác thực format, giới hạn kích thước và không dùng nó làm quyền truy cập.

## 25. Sơ đồ chẩn đoán incident xuyên dịch vụ

~~~mermaid
flowchart TD
  A["Alert: 5xx / p95 / job deadline"] --> B["Xác định route, region, thời gian, release"]
  B --> C["Tìm request ở APIM/gateway"]
  C --> D{"Có trace/correlation backend?"}
  D -->|Có| E["Mở server spans + dependencies"]
  D -->|Không| F["Kiểm tra propagation, sampling, instrumentation"]
  E --> G{"Lỗi ở dependency nào?"}
  G -->|HTTP/DB| H["Kiểm tra timeout, 429/503, health, network"]
  G -->|Queue/worker| I["Kiểm tra backlog, DLQ, attempt, business status"]
  G -->|Ứng dụng| J["Exception, config, resource saturation, release"]
  H --> K["Khắc phục / rollback / failover theo runbook"]
  I --> K
  J --> K
  F --> K
  K --> L["Xác minh SLO + business outcomes"]
  L --> M["Post-incident: action items, telemetry gaps, cost"]
~~~

Một nguyên tắc quan trọng: **thất bại trong tracing pipeline không được làm API chính thất bại**, trừ khi tổ chức có yêu cầu audit bắt buộc đặc biệt. Exporter thường nên hoạt động bất đồng bộ/bounded buffers; mất telemetry cần alert nhưng không gây thắt nghẽn nghiệp vụ.

## 26. Case study: payment API lỗi sau khi triển khai

### Bối cảnh

Một ứng dụng đặt hàng có:

- Azure Front Door ở biên.
- APIM xử lý auth/quota/route.
- Orders API Java trên Azure Container Apps.
- Payments API Java trên AKS.
- Service Bus phát job `PaymentConfirmed`.
- Azure Functions cập nhật trạng thái đơn.
- Azure SQL Database và Storage.
- Application Insights workspace-based để tập hợp application telemetry.

Sau release `payments-api v2.3.7`, khách hàng thấy HTTP 503/504 tăng. Dashboard tổng thể cho thấy CPU không cao, nên giả thuyết “thiếu CPU” chưa có bằng chứng.

### Điều tra

1. Xem request error rate theo route/region/5m; xác định chỉ `POST /payments` bị ảnh hưởng.
2. Từ gateway logs xác nhận phần lớn lỗi do backend timeout, không phải APIM throttle.
3. Tìm một request bằng OperationId/trace ID.
4. Trong distributed trace, thấy 70ms tại APIM, 120ms tại Orders API, 2,7s tại Payments API và 2,5s tại SQL dependency.
5. So sánh release: Payments API v2.3.7 tăng một SQL query thiếu index hoặc tạo N+1 queries (giả thuyết cần xác minh bằng query telemetry/plan), trong khi v2.3.6 không có.
6. Kiểm tra SQL metrics: duration/throttling/connection pool; kiểm tra logs và app version.
7. Nếu xác nhận regression, rollback/feature flag theo runbook, đồng thời lập fix/index/migration có thử nghiệm.
8. Xác nhận 5xx và p95 giảm, business payment completion trở lại bình thường.
9. Rà soát message đã bị retry/DLQ, tránh tạo charge trùng khi replay.

### Kết quả cần có trong incident report

| Trường | Ví dụ cần ghi |
|---|---|
| Incident start/end | Mốc UTC và cách xác định |
| Impact | Số yêu cầu hợp lệ thất bại, region và khách hàng bị ảnh hưởng |
| Trace evidence | Trace ID được kiểm soát quyền, dependency/span lỗi |
| Root cause | Thay đổi code/config/query đã được chứng minh |
| Mitigation | Rollback, giới hạn retry, capacity/circuit breaker theo phê duyệt |
| Recovery validation | SLO, business completion, backlog/DLQ, data reconciliation |
| Prevention | Regression tests, tracing gaps, alerts, load tests |
| Cost impact | Retry compute, Log Analytics ingestion, downstream operations |

Đây là **kịch bản học tập**, không phải một sự cố Azure thực tế được truy xuất từ hệ thống người dùng.

## 27. Thiết kế dashboard cho nhóm vận hành

Một dashboard hữu ích có thể chia thành ba cấp:

### Lớp 1 — Executive/SLO overview

- Request volume theo API quan trọng.
- Availability SLI và error budget.
- p95/p99 latency và 5xx.
- Business completion của async workflows.
- Active incidents và trạng thái deployment.

### Lớp 2 — Service ownership

- Service name/version/region.
- Top routes by latency/failures.
- Dependency map, target latency/exception.
- Pod/revision health, CPU/memory/GC, throughput.
- Queue backlog, retry count và DLQ.
- Links tới traces/log queries.

### Lớp 3 — Incident drill-down

- Lọc theo khoảng UTC/region/route.
- Trace ID, service, version, span tree/timeline.
- Gateway vs backend status.
- Exception stack đã redacted.
- Dependency errors, retry attempts.
- Timeline deploy/change.
- SLO recovery và quyết định xử lý.

Dashboard không nên hiển thị raw request body hay token. Đảm bảo link/drill-down tuân thủ quyền truy cập workspace và môi trường.

## 28. Bài thực hành: tìm lỗi API qua ba dịch vụ

### Mục tiêu

Một lab gồm:

- Gateway hoặc entry API (có thể dùng APIM lab nếu có quyền).
- Orders API Java.
- Inventory API Java.
- Queue/Function worker hoặc mock downstream.
- Application Insights/Log Analytics hoặc OTel collector/viewer được cho phép.

Chạy trên **tài nguyên lab riêng**; các bước tạo resource Azure có thể phát sinh chi phí.

### Phần A — Thiết kế telemetry

1. Vẽ sơ đồ call chain từ client qua gateway tới hai Java services.
2. Chọn `service.name`, environment, version và route template cho từng service.
3. Định nghĩa SLI availability và p95 cho `POST /orders`.
4. Thiết lập error code taxonomy như `INVENTORY_TIMEOUT`, `PAYMENT_UNAVAILABLE`.
5. Chọn cách truyền W3C `traceparent` qua HTTP; giải thích trace ID và span ID.
6. Chọn job ID cho bước bất đồng bộ nếu có.
7. Quy định rõ những headers/body fields cần redaction.
8. Chọn sampling và retention phù hợp quy mô lab.

### Phần B — Instrumentation

1. Bật Application Insights hoặc OpenTelemetry exporter được hỗ trợ cho Java services.
2. Đảm bảo mỗi incoming HTTP request có server span.
3. Thêm custom span cho bước `inventory.reserve`.
4. Kích hoạt dependency instrumentation cho HTTP/SQL có trong lab.
5. Ghi structured logs kèm traceId/spanId và errorCode.
6. Nếu có queue, truyền context trong message properties và liên hệ consumer.
7. Kiểm tra version/resource attributes khi deploy một revision mới.
8. Thử một HTTP request thành công, quan sát end-to-end trace.

### Phần C — Cố tình tạo lỗi có kiểm soát

Trong **môi trường test không chứa dữ liệu thật**:

1. Cho Inventory API trả HTTP 503 với một số request thử.
2. Cho dependency phản hồi chậm để quan sát timeout.
3. Tạo một lỗi validation 400 để so với lỗi server 500.
4. Gọi request qua gateway, ghi lại thời điểm UTC và trace ID.
5. Tìm request trong AppRequests hoặc nguồn tracing đang dùng.
6. Xem AppDependencies và AppExceptions tương ứng.
7. Dùng một KQL query tổng hợp failure rate/p95 trong 30–60 phút.
8. Xác minh logs của hai dịch vụ có chung trace ID.
9. Kiểm tra một lần retry có attempt info và không tạo side effect trùng.
10. Nếu có queue, theo dõi backlog/DLQ và xác nhận business result.

### Phần D — Alert và phục hồi

1. Đặt alert thử cho failure rate hoặc latency đủ ngưỡng tối thiểu.
2. Liên kết alert tới dashboard/query/runbook.
3. Tạo lỗi trong lab và kiểm tra alert fire/resolution.
4. Khắc phục service/mocking dependency rồi đo recovery.
5. Rà soát incomplete traces do sampling hoặc propagation.
6. Ghi incident summary: triệu chứng, root cause, mitigation, bài học.
7. Kiểm tra telemetry cost và dọn resource lab theo quy trình được phép.

### Câu hỏi tự kiểm tra

**Câu 1.** Metrics, logs và distributed traces trả lời các loại câu hỏi khác nhau như thế nào?

**Câu 2.** Trace ID và span ID khác nhau ra sao? Header W3C nào truyền parent context qua HTTP?

**Câu 3.** Nếu request qua APIM thành công nhưng Azure Function xử lý queue thất bại sau 10 phút, HTTP SLI có đo được lỗi nghiệp vụ không?

**Câu 4.** Khi thấy APIM HTTP 502, vì sao phải kiểm tra backend status và policy/gateway logs?

**Câu 5.** Thêm Java agent vào Orders API có tự tạo spans trong Payments API không? Cần làm gì ở downstream?

**Câu 6.** Khi message được giao lại, trace ID mới có hợp lệ không và ID nào nên ổn định để chống xử lý trùng?

**Câu 7.** Vì sao tên metric không nên chứa orderId hoặc full URL có ID?

**Câu 8.** Sampling 10% có cho phép dùng thẳng `count()` làm chính xác toàn bộ số request production không?

**Câu 9.** Application Insights và Log Analytics workspace khác nhau thế nào?

**Câu 10.** Nếu người dùng nhận 504 nhưng backend sau đó commit thành công, điều gì cần làm trước khi retry payment?

**Câu 11.** Một HTTP 401 do nhập sai mật khẩu có nhất thiết là lỗi availability SLO không?

**Câu 12.** Làm thế nào để biết lỗi tăng sau một deployment chứ không chỉ tăng do traffic?

**Câu 13.** Những dữ liệu nào không được đưa vào tracing headers, baggage và application logs?

**Câu 14.** Tại sao dashboard CPU thấp không đủ để loại trừ vấn đề dependency/database?

**Câu 15.** Một alert chỉ dựa vào p95 latency không phân biệt route/region có thể gây hiểu lầm thế nào?

**Tiêu chí hoàn thành:** người học định nghĩa được SLI/SLO, mô tả context propagation, thiết kế instrumentation Java xuyên gateway/services/queue, truy vấn KQL tìm lỗi, lập runbook điều tra incident và đánh giá sampling, bảo mật, chi phí telemetry.

## Kết luận

**Quan sát API và theo dõi lỗi qua nhiều dịch vụ** đòi hỏi khả năng nối dữ liệu của gateway, ứng dụng, dependency, queue và nền tảng thành một bức tranh nhân quả. **Metrics** cho thấy xu hướng và SLO; **logs** cho chi tiết sự kiện; **distributed traces** với W3C Trace Context cho biết request đã đi qua đâu và chặng nào chậm hoặc lỗi.

Trên Azure, **Azure Monitor, Application Insights, Log Analytics, API Management diagnostics và OpenTelemetry** cung cấp các mảnh ghép quan trọng, nhưng cần được cấu hình đồng bộ theo service name, route, trace ID, release và policy dữ liệu. Khi kết hợp **KQL, cảnh báo có hành động, idempotency/retry budgets, bảo mật telemetry, sampling/retention và incident runbooks**, đội vận hành có thể tìm nguyên nhân chính xác hơn, giảm thời gian khắc phục và bảo vệ cả trải nghiệm người dùng lẫn chi phí hạ tầng Azure.

