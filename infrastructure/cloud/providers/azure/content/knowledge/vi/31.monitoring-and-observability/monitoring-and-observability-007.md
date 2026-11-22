# OpenTelemetry và distributed tracing trên Azure

Một khách hàng đặt hàng trên ứng dụng thương mại điện tử. API Gateway chuyển request tới dịch vụ Orders trên Azure App Service, Orders gọi Pricing chạy trên Azure Kubernetes Service (AKS), đọc Azure SQL Database rồi gửi message tới Azure Service Bus. Worker xử lý message, lưu hóa đơn trên Azure Blob Storage và thông báo trạng thái. Người dùng chỉ thấy một thông báo “Request timeout” sau 8 giây. Dịch vụ nào chậm? Kết nối nào thất bại? Có phải database, mạng, queue, hay chính sách retry làm tăng độ trễ?

**Distributed tracing** giúp theo dõi **một hoạt động logic xuyên qua nhiều tiến trình/dịch vụ** dưới cùng một trace ID. **OpenTelemetry (OTel)** cung cấp các API, SDK, semantic conventions, cơ chế instrumentation và giao thức xuất dữ liệu theo tiêu chuẩn mở. Trên Azure, có thể sử dụng **Azure Monitor Application Insights**, **Azure Monitor OpenTelemetry Distro**, Java agent, OpenTelemetry Collector và các công cụ quan sát khác để thu thập, lưu, truy vấn và phân tích các dấu vết.

Bài học thuộc chương **Giám sát và quan sát hệ thống** trong mô-đun **CLOUD_PROVIDERS_AZURE**: nối kiến thức về subscription, resource group, Entra ID, networking, App Service, AKS, Functions, dữ liệu và chi phí thành một quy trình truy vết và vận hành kiến trúc Azure có thể kiểm chứng.

**Phạm vi:** nền tảng tracing độc lập ngôn ngữ, triển khai thực hành ưu tiên Spring Boot/Java chạy trên Azure App Service hoặc AKS. Dùng thông số, tên dịch vụ và connection strings giả định. Không tạo tài nguyên Azure production, không đẩy dữ liệu cá nhân vào telemetry. Phiên bản agent, cấu hình và defaults có thể thay đổi; kiểm tra tài liệu Microsoft Learn/OpenTelemetry tương ứng trước khi phát hành production.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **metrics, logs, traces** và biết khi nào cần mỗi tín hiệu.
2. Mô tả **trace**, **span**, **trace ID**, **span ID**, **parent**, **attributes**, **events**, **status**, **links**.
3. Giải thích distributed trace là quan hệ nhân quả, không chỉ một chuỗi log có timestamp.
4. Hiểu propagation qua HTTP headers **traceparent**, **tracestate** và **baggage** theo W3C.
5. Phân biệt span kinds **SERVER, CLIENT, PRODUCER, CONSUMER, INTERNAL**.
6. Thiết kế **service.name**, **service.namespace**, **deployment.environment.name**, **service.version** và attribute cardinality.
7. Hiểu auto-instrumentation, manual instrumentation và OpenTelemetry Java API/SDK.
8. Instrument ứng dụng Spring Boot bằng **Azure Monitor Application Insights Java agent** mà không chèn secret trong image.
9. Tạo custom span, attributes, events, exception và status bằng Java OpenTelemetry API.
10. Truyền context qua HTTP, async executors, message queues và retry có kiểm soát.
11. Phân biệt **Azure Monitor exporter/agent** với **OTLP Collector**, hiểu không thể gửi OTLP thẳng tới mọi URL Azure Monitor.
12. Dùng Application Insights Application Map, End-to-end transaction details và KQL bảng **AppRequests, AppDependencies, AppTraces, AppExceptions**.
13. Giải thích head sampling, parent-based sampling, tail sampling, rate-limited sampling và tác động tới chi phí.
14. Bảo vệ PII, secrets, SAS, access tokens và thông tin đa tenant khi thu thập traces.
15. Chẩn đoán missing spans, duplicate telemetry, propagation sai, exporter errors, clock skew và sampling.
16. Lập SLO, alerting, retention, capacity và runbook tracing trong production.

## 2. Tại sao một correlation ID đơn giản chưa đủ?

### 2.1. Hệ thống phân tán có nhiều đồng hồ và ranh giới

~~~mermaid
flowchart LR
    U["Client"] --> GW["API Gateway"]
    GW --> OR["Orders API - App Service"]
    OR --> PR["Pricing - AKS"]
    OR --> DB["Azure SQL"]
    OR --> SB["Azure Service Bus"]
    SB --> WK["Invoice Worker - Container Apps"]
    WK --> BL["Azure Blob Storage"]
    OR --> AM["Azure Monitor / Application Insights"]
    PR --> AM
    WK --> AM
~~~

Nếu mỗi dịch vụ ghi logs riêng, người vận hành phải tìm:
- Request nào thuộc cùng một đơn hàng?
- Service nào bắt đầu child operation nào?
- Các thao tác nào chạy song song?
- Delay 2 giây nằm ở Pricing, SQL hay Service Bus?
- Retry của SDK có tạo nhiều network attempts?
- Message worker xử lý sau bao lâu?
- Lỗi xảy ra trong request hay sau khi HTTP response đã trả?

Một request ID tự tạo giúp lọc logs, nhưng thường **không mô tả cây parent-child, thời lượng span, trạng thái và các quan hệ không đồng bộ**. Distributed tracing bổ sung mô hình dữ liệu để ghép những sự kiện đó thành một trace.

### 2.2. Traces, metrics và logs hỗ trợ nhau

| Tín hiệu | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| **Metrics** | Có sự cố không, quy mô ra sao? | p95 latency = 1,8 s; error rate 4% |
| **Logs** | Chuyện gì xảy ra chi tiết? | Exception SQLException hoặc thông báo validation |
| **Traces** | Một request cụ thể đi qua đâu, phần nào chậm? | Orders → Pricing 900 ms → SQL 30 ms |
| **Profiles** (nếu dùng) | CPU/memory được sử dụng ở đâu? | Java allocation hoặc hot method |

Không dùng traces thay thế mọi metrics; **sampling** có thể khiến phần lớn requests không có trace trong kho phân tích. Không dùng logs toàn bộ raw payload để “thay tracing”, vì nguy cơ PII, độ lớn và thiếu cấu trúc causality.

### 2.3. Trường hợp cần distributed tracing

- Microservices giao tiếp qua HTTP/gRPC.
- Azure SDK clients gọi Storage, Cosmos DB, Service Bus, Event Hubs hoặc Azure SQL.
- Async workers và serverless Functions.
- Những request có nhiều child dependencies.
- Incident với latency p99 hoặc timeout rời rạc.
- Nhiều retries, circuit breakers, queue backlogs.
- Deploy canary cần so behavior theo version.
- Multi-region routing hoặc hybrid network.

Nếu ứng dụng chỉ có một process và một câu SQL đơn giản, structured logs + metrics có thể đã đáp ứng bước đầu; không nhất thiết thêm Collector phức tạp.

## 3. Mô hình dữ liệu OpenTelemetry Tracing

### 3.1. Trace là hoạt động logic

Một **trace** biểu diễn chuỗi hoặc đồ thị các operations liên quan. Trace có **trace ID 128-bit** thường được hiển thị bằng 32 chữ số hex, ví dụ:

~~~text
traceId = 4bf92f3577b34da6a3ce929d0e0e4736
~~~

Trace ID **không phải ID của khách hàng hoặc số đơn hàng**. Tránh dùng một business ID có ý nghĩa cá nhân làm trace ID; trace ID nên được tạo ngẫu nhiên theo quy tắc SDK.

### 3.2. Span là một đơn vị công việc

**Span** chứa:
- Name: orders.checkout, HTTP GET, db.query ...
- Span ID (64-bit, thường 16 chữ số hex).
- Parent Span ID hoặc context quan hệ.
- Start/end timestamps và duration.
- Span kind: SERVER, CLIENT, PRODUCER, CONSUMER, INTERNAL.
- Attributes: các key-value phục vụ phân tích.
- Events: những mốc diễn ra bên trong span.
- Status: thường UNSET hoặc ERROR.
- Links: liên kết với spans khác không theo cây parent-child đơn giản.

Span có thể tồn tại rất ngắn, và **span kết thúc bằng span.end()**. Nếu quên end, telemetry có thể không được xuất hoặc trở thành trace khó hiểu.

### 3.3. Parent-child tạo cây gọi dịch vụ

~~~mermaid
flowchart TD
    A["SERVER: POST /orders | 1200 ms"]
    A --> B["CLIENT: Pricing HTTP | 780 ms"]
    A --> C["CLIENT: SQL INSERT | 180 ms"]
    A --> D["PRODUCER: Service Bus send | 65 ms"]
    B --> E["SERVER: Pricing GET /quotes | 700 ms"]
    E --> F["CLIENT: Redis GET | 15 ms"]
    D -. "async link / propagated context" .-> G["CONSUMER: invoice-worker process | 350 ms"]
~~~

Nếu cùng trace context được propagated, **span của downstream** có thể có cùng trace ID và parent ID tương ứng. Tuy nhiên các hệ thống bất đồng bộ có thể dùng **span links** thay cho quan hệ parent-child trực tiếp; việc vẽ nét nối không tự chứng minh chính xác semantics của broker hoặc instrumentation.

### 3.4. Các span kinds

| Kind | Ngữ cảnh | Ví dụ |
|---|---|---|
| SERVER | Tiếp nhận request từ remote client | Spring MVC nhận POST /orders |
| CLIENT | Gọi một remote service | Orders gọi Pricing qua HTTP |
| PRODUCER | Tạo/gửi message | Đưa command lên Service Bus |
| CONSUMER | Nhận/xử lý message | Worker xử lý event |
| INTERNAL | Công việc bên trong process | Validate order, calculate tax |

**INTERNAL span không phải dependency network**. Một số backend có thể map spans sang requests/dependencies theo kind, integration và instrumentation. Không tự giả định một INTERNAL span luôn tạo một HTTP request trong Application Insights.

### 3.5. Span attributes và events

Ví dụ:

~~~text
Span name: orders.validate
Span kind: INTERNAL
Attributes:
  order.channel = "mobile"
  order.line_count = 3
  deployment.environment.name = "staging"
Events:
  validation.started
  validation.completed
Status:
  UNSET (không có lỗi)
~~~

Attributes nên là các giá trị có phạm vi hạn chế, **không chứa full payment token, customer email, credit card, raw SQL tham số nhạy cảm hoặc body của request**.

### 3.6. Status và exception

- Một span thành công thường để status **UNSET** thay vì ghi OK cho tất cả.
- Khi xảy ra lỗi nghiệp vụ hoặc technical exception cần diagnostic: record exception event và set status ERROR khi phù hợp.
- Một HTTP 4xx không nhất thiết là lỗi hệ thống: 400 validation có thể là kết quả dự kiến; đánh dấu ERROR theo semantic conventions và mục tiêu SLO được thống nhất.
- Có exception được bắt và xử lý thành công thì không nhất thiết biến toàn trace thành error.

Không dùng span exception để thay exception handling hoặc trả thông báo lỗi chi tiết cho user.

## 4. W3C Trace Context và context propagation

### 4.1. traceparent header

Một HTTP request có thể mang header:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Cấu trúc:

~~~text
version-trace-id-parent-id-trace-flags
00 - 32 hex characters - 16 hex characters - 2 hex chars
~~~

Trong ví dụ:
- **00:** traceparent version.
- **4bf9...4736:** trace ID.
- **00f0...02b7:** span ID của caller được gửi cho callee.
- **01:** sampled bit được bật.

Header không chứa lời cam kết security. Kẻ tấn công có thể tự đặt traceparent; không sử dụng header này như **xác thực, phân quyền hoặc bằng chứng caller đã được tin cậy**.

### 4.2. tracestate và baggage

- **tracestate:** bổ sung ngữ cảnh dành cho tracing vendors/implementations, theo W3C và giới hạn kích thước.
- **baggage:** key-value đi qua ranh giới dịch vụ; có thể giúp contextual propagation, nhưng dễ bị gửi sang đối tác thứ ba.
- **Attributes:** nằm trên span, không mặc định tự được truyền qua mọi request như baggage.
- **Log correlation:** thường dùng trace_id và span_id trong logs, không cần sao chép toàn bộ baggage.

Không đặt tên người dùng, email, Authorization, địa chỉ nhà, JWT hoặc tenant data nhạy cảm trong baggage. Coi baggage/traceparent **untrusted input** ở inbound boundary.

### 4.3. Inject và extract

- **Inject:** trước khi gửi HTTP/message, instrumentation chèn traceparent/tracestate và context metadata được phép vào carrier.
- **Extract:** phía nhận đọc headers, tạo context của parent rồi tạo span mới.
- **Propagate:** nếu cùng trace được phép, child giữ trace ID và có quan hệ tới caller.
- **Trust boundary:** incoming baggage cần allowlist/size checks, không copy vô điều kiện vào internal logs.
- **Fallback:** nếu không có valid traceparent, server tạo root span mới.

~~~mermaid
sequenceDiagram
    participant A as Orders API
    participant P as OTel Propagator
    participant H as HTTP Headers
    participant B as Pricing API
    A->>P: Inject current context
    P->>H: traceparent / tracestate
    H->>B: GET /price
    B->>B: Extract remote context
    B->>B: Start SERVER child span
    B-->>A: Response
~~~

### 4.4. Một trace với nhiều root hoặc traces bị chia

Nếu caller không inject header hoặc downstream không extract, Pricing tạo trace ID mới. Trong Application Map có thể vẫn thấy dependency HTTP nhưng **không ghép được full end-to-end trace**.

Các nguyên nhân khác:
- HTTP gateway/proxy loại traceparent.
- Async worker mất thread-local context.
- Message broker custom code không truyền context trong application properties.
- Runtime có hai instrumentations cùng cài.
- Sampling không nhất quán ở các services.
- Thư viện dùng propagation format không tương thích.

## 5. Resource attributes và tên dịch vụ

### 5.1. Resource mô tả nguồn telemetry

OpenTelemetry **Resource** gắn metadata về service/process/cloud environment cho spans, metrics và logs.

Các thuộc tính cần hoạch định:

| Thuộc tính | Ví dụ | Mục đích |
|---|---|---|
| service.name | orders-api | Nhận diện service ổn định |
| service.namespace | commerce | Phân nhóm services |
| service.version | 2.4.1 | So regression theo release |
| deployment.environment.name | production | Phân biệt môi trường |
| cloud.provider | azure | Cloud provider |
| cloud.region | southeastasia | Azure region khi detector phù hợp |
| service.instance.id | instance-id được hệ thống tạo | Phân biệt replicas khi cần |
| k8s.namespace.name | commerce-prod | AKS context khi detector hỗ trợ |

Không gắn từng **user ID/order ID** vào service.name hoặc các giá trị resource có cardinality lớn. Service name thay theo mỗi Pod/instance sẽ làm Application Map thành hàng nghìn nodes khó sử dụng.

### 5.2. Cloud Role Name trong Application Insights

Azure Monitor/Application Insights sử dụng mô hình **Cloud Role Name** để phân nhóm services trên Application Map. Với các Java services xuất vào cùng một resource, cần tên role **khác nhau, ổn định** như orders-api, pricing-api, invoice-worker.

Nếu mọi service cùng tên “application”, Application Map khó phân biệt và phân tích dependency dễ bị sai. Trong Application Insights Java agent, có thể cấu hình role name bằng cấu hình agent; đồng thời quản trị service.name/OTel Resource theo SDK/agent integration được hỗ trợ.

### 5.3. Tên span nên có cardinality thấp

Không nên:

~~~text
GET /orders/8d3f5ac9-...    (mỗi order một tên span)
payment to customer@example.com
query invoices for tenant-391028
~~~

Nên:

~~~text
GET /orders/{orderId}
orders.checkout
payment.authorize
invoice.persist
~~~

ID cụ thể (nếu được phép) có thể dùng correlation ở logs/attributes theo chính sách PII và cardinality; không làm span name/metric label thay đổi cho mỗi request.



## 6. Kiến trúc OpenTelemetry: API, SDK, instrumentation và exporter

### 6.1. Các thành phần

~~~mermaid
flowchart TD
    APP["Application code"] --> API["OTel API: Tracer / Span / Context"]
    LIB["HTTP/JDBC/Messaging libraries"] --> INST["Auto instrumentation"]
    API --> SDK["OTel SDK: processors / sampler / resources"]
    INST --> SDK
    SDK --> EXP["Exporter"]
    EXP --> COL["OTLP Collector - optional"]
    EXP --> AZ["Azure Monitor exporter / Java agent path"]
    COL --> BACK["Supported observability backend"]
    AZ --> AI["Application Insights / Azure Monitor"]
~~~

**Các khái niệm:**

- **OpenTelemetry API:** các interfaces để tạo spans, thêm attributes, quản lý context. Chỉ có API **chưa chắc đã gửi dữ liệu**.
- **OpenTelemetry SDK:** hiện thực providers, processors, samplers, exporters.
- **Instrumentation:** thư viện hoặc Java agent tự tạo spans cho HTTP server/client, JDBC, messaging và các thành phần hỗ trợ.
- **Exporter:** đưa dữ liệu sang một đích, ví dụ OTLP endpoint hoặc Azure Monitor.
- **Collector:** dịch vụ nhận, xử lý, gom batch, lọc và xuất telemetry; là tùy chọn, không bắt buộc trong mọi mô hình.
- **Backend:** nơi lưu, truy vấn, hiển thị traces, ví dụ Azure Monitor Application Insights.

### 6.2. Auto instrumentation và manual instrumentation

| Cách | Phát hiện | Khi nên dùng |
|---|---|---|
| Auto instrumentation | HTTP request, JDBC calls, nhiều SDK/network clients | Bắt đầu nhanh, giảm code |
| Manual API spans | Những bước nghiệp vụ khó thấy: validate, pricing, fraud rules | Cần diễn giải business operation |
| Instrumentation library | Một số framework riêng | Nếu agent/SDK hỗ trợ đúng |
| Collector processing | Lọc/redact/routing telemetry sau nguồn | Chính sách quan sát đa dịch vụ |

Auto instrumentation không hiểu hết business domain. Một HTTP child span “POST /payments” biết dependency chậm 3 giây nhưng không tự giải thích “tại sao đơn bị từ chối” hoặc “đã xếp job gửi hóa đơn hay chưa”. Manual spans giúp bổ sung.

### 6.3. Semantic conventions

OpenTelemetry có **semantic conventions** cho HTTP, RPC, database, messaging và cloud. Ví dụ nhiều thư viện hiện đại dùng tên thuộc tính:

~~~text
http.request.method
http.response.status_code
server.address
url.scheme
db.system.name
messaging.system
messaging.operation.name
error.type
~~~

Tên trường thực có thể khác theo phiên bản OpenTelemetry Semantic Conventions và instrumentation đang chạy. Khi nâng Java agent, dữ liệu trước và sau có thể khác key. Không viết KQL production phụ thuộc một field duy nhất mà không có backward-compatible plan.

### 6.4. Không tạo hai TracerProvider/exporters vô chủ đích

Một lỗi phổ biến:

1. Bật Application Insights Java agent qua JVM.
2. Đồng thời import một bộ OpenTelemetry SDK khác khởi tạo GlobalOpenTelemetry.
3. Đồng thời bật Spring/Micrometer tracing exporter.
4. Tất cả cùng tự instrument Spring MVC.

Hậu quả có thể là **duplicate spans, parent relationships sai, telemetry tăng gấp đôi và chi phí cao**. Chọn **một pipeline tracing chính** và phối hợp các instrumentation bổ sung theo mô hình hỗ trợ. Nếu sử dụng Java agent, thường chỉ cần **OpenTelemetry API** trong application code cho custom spans thay vì tự tạo thêm một SDK/exporter độc lập.

## 7. Azure Monitor, Application Insights và Log Analytics

### 7.1. Ba khái niệm dễ nhầm

- **Azure Monitor:** dịch vụ giám sát và quan sát tổng thể trên Azure, bao gồm metrics, logs, alerts.
- **Application Insights:** thành phần application performance monitoring (APM) giúp phân tích requests, dependencies, exceptions, Application Map và giao dịch.
- **Log Analytics workspace:** nơi lưu/truy vấn Log Analytics dữ liệu có cấu trúc bằng **Kusto Query Language (KQL)** trong mô hình workspace-based Application Insights.

Sơ đồ:

~~~mermaid
flowchart LR
    O["OTel instrumented app"] --> AG["Azure Monitor OpenTelemetry Distro / Java agent"]
    AG --> AI["Application Insights resource"]
    AI --> LA["Log Analytics workspace"]
    LA --> KQL["KQL / Alerts / Workbooks"]
    AI --> MAP["Application Map / Transaction details"]
~~~

**Traces** là mô hình OpenTelemetry; **Application Insights** là một backend/visualization. Không phải mọi loại trace từ mọi nhà cung cấp đều có mapping giống nhau sang Application Insights schema.

### 7.2. Workspace-based Application Insights

Trong mô hình hiện hành, những dữ liệu ứng dụng có thể xuất hiện ở các bảng:

| Bảng | Loại telemetry thường gặp |
|---|---|
| **AppRequests** | Server/inbound request telemetry |
| **AppDependencies** | HTTP/JDBC/remote dependency calls, nhiều custom internal spans theo mapping |
| **AppTraces** | Log/tracing messages được thu thập |
| **AppExceptions** | Exception details |
| **AppEvents** | Custom events khi exporter/integration hỗ trợ |
| **AppMetrics** | Một số custom/application metrics theo ingestion mode |
| **AzureDiagnostics/Resource-specific tables** | Resource diagnostic logs, không tự đồng nhất với OTel traces |

Danh sách bảng thực tế phụ thuộc exporter, workspace/resource configuration và thời điểm. **Không nhầm AppTraces (log messages) với toàn bộ span tree**: span requests/dependencies thường nằm ở AppRequests và AppDependencies.

### 7.3. OperationId và quan hệ dữ liệu

Trong Application Insights, **OperationId** thường là khóa tương quan của một distributed operation và tương thích với trace ID của W3C theo pipeline instrumentation phù hợp. Các bảng thường có **Id, ParentId, OperationId, TimeGenerated** cùng những cột khác.

- **OperationId:** tìm các telemetry records trong một transaction.
- **Id:** ID của request/dependency item.
- **ParentId:** liên kết với item/span cha.
- **AppRoleName:** service logic phát telemetry.
- **DurationMs:** thời gian đo theo item.
- **Success, ResultCode:** kết quả mà instrumentation nhận diện.

Một OperationId trùng **không tự chứng minh service đã xử lý đúng**; cần xem parent relationships, time window và errors.

### 7.4. Application Map và End-to-end transaction details

Trong portal, dùng:

1. **Application Insights → Application Map** để thấy services/dependencies và health/performance theo dữ liệu đã có.
2. **Transaction search** hoặc truy vấn logs để tìm request cụ thể.
3. **End-to-end transaction details** xem request và các dependency con.
4. **Failures** kiểm tra HTTP 5xx/exception patterns.
5. **Performance** tìm requests chậm và breakdown.
6. **Live Metrics** quan sát nhanh xu hướng theo khả năng cấu hình.
7. **Logs (KQL)** để phân tích sâu và đối chiếu.

Nếu ba services xuất vào cùng Application Insights resource, cấu hình **Cloud Role Name** riêng để Application Map không gộp tất cả làm một node. Nếu dữ liệu xuất nhiều resources/workspaces, cross-resource querying và visualization còn phụ thuộc quyền/khả năng của công cụ.

## 8. Chọn một trong các đường gửi telemetry

### 8.1. Phương án A: Java agent → Azure Monitor Application Insights

~~~mermaid
flowchart LR
    J["Spring Boot JVM"] --> AG["Azure Monitor / Application Insights Java agent"]
    AG --> ING["Azure Monitor ingestion endpoint"]
    ING --> AI["Application Insights"]
~~~

Ưu điểm:
- Ít hoặc không phải sửa business code để có server/dependency telemetry.
- Tích hợp Java auto instrumentation và Azure Monitor backend.
- Có cấu hình agent cho role, sampling, logs, self-diagnostics.
- Phù hợp Azure App Service, AKS/Container Apps và JVM workload theo điều kiện hỗ trợ.

Nhược điểm:
- Phụ thuộc version của Java agent và danh sách libraries được instrument.
- Cần cấu hình security/egress/connection string.
- Có overhead CPU, memory, network và chi phí ingestion.
- Nếu đã bật auto-instrumentation platform, không nên attach thêm agent trùng.

### 8.2. Phương án B: OpenTelemetry Java agent → OTLP Collector → Backend

~~~mermaid
flowchart LR
    J["Spring Boot JVM"] --> OT["OpenTelemetry Java agent + OTLP exporter"]
    OT --> C["OTel Collector"]
    C --> DBG["Debug exporter trong lab"]
    C --> B["Backend/exporter được hỗ trợ"]
~~~

Ưu điểm:
- Có thể route OTLP tới nhiều observability backends khi được hỗ trợ.
- Tập trung policies về batching, filtering, redaction và networking.
- Phù hợp tổ chức nhiều ngôn ngữ, services, vendors.

Nhược điểm:
- Cần vận hành Collector: capacity, TLS, authentication, queue, retries và upgrades.
- Không phải exporter nào cũng hỗ trợ mọi signal, sampling semantics và Azure features.
- **Azure Monitor Application Insights ingestion endpoint không phải một OTLP receiver tùy ý.** Không thay OTEL_EXPORTER_OTLP_ENDPOINT bằng URL App Insights ingestion rồi kỳ vọng gửi OTLP trực tiếp thành công.

### 8.3. Lựa chọn phù hợp

| Bối cảnh | Cách bắt đầu |
|---|---|
| Spring Boot trên App Service muốn Application Map nhanh | Azure Monitor Application Insights Java agent |
| AKS với nhiều JVM services muốn Azure Monitor | Java agent/auto-instrumentation hoặc Azure-supported approach |
| Nhiều ngôn ngữ, nhiều backends | OTLP → Collector → exporters phù hợp |
| Có OpenTelemetry SDK đã cấu hình | Tích hợp exporter/distro mà không tạo providers trùng |
| Native image Java | Xem hướng dẫn riêng cho Spring Boot native / OTel Java SDK |
| Ứng dụng nhiều agent/SDK cũ | Lập migration plan tránh duplicate telemetry |

**Một JVM nên có một chiến lược instrument/export chính được kiểm thử.** Không bật đồng thời Azure Monitor Java agent và upstream OTel Java agent chỉ để “đầy đủ hơn”.

## 9. Thực hành A: Spring Boot với Azure Monitor Java agent

### 9.1. Kiến trúc bài lab

~~~text
Spring Boot orders-api
    ├─ GET /health (framework endpoint)
    ├─ POST /orders/{id}/confirm
    ├─ HTTP client call
    └─ Manual span "orders.validate"
           ↓
Application Insights Java agent (auto + manual spans)
           ↓
Azure Monitor / Application Insights
           ↓
Application Map + KQL
~~~

Trong lab, endpoint và Application Insights resource thuộc subscription đã được phép dùng. Không phát sinh request tới payment/DB production; các bước manual spans có thể dùng mock business operation.

### 9.2. Chuẩn bị tài nguyên an toàn

Cần:
- Một **workspace-based Application Insights resource** được cho phép.
- **Connection string** của resource, không dùng một instrumentation key đơn lẻ thay thế cơ chế hiện hành.
- Azure App Service hoặc máy dev có JVM/Spring Boot và agent phù hợp.
- Quyền truy cập Application Insights/Log Analytics để xem data.
- HTTPS egress tới ingestion endpoints, DNS/TLS hợp lệ.
- Không lưu connection string trong repository hoặc Docker image public.

Connection string xác định ingestion destination; nó **không phải bearer token cấp quyền đọc toàn bộ Log Analytics**, nhưng vẫn nên xử lý như cấu hình nhạy cảm, không đưa vào code/log không cần thiết.

### 9.3. Dùng Azure Monitor Java agent

Theo hướng dẫn Microsoft Learn được kiểm tra khi soạn bài, ví dụ Java agent release trong tài liệu là **applicationinsights-agent-3.7.9.jar**. Đây là version minh họa tại thời điểm tài liệu được tra cứu; **xác minh release/JDK compatibility, provenance và checksum** trước khi dùng thực tế.

Ví dụ Bash:

~~~bash
export APPLICATIONINSIGHTS_CONNECTION_STRING="<APP_INSIGHTS_CONNECTION_STRING>"

java \
  -javaagent:"/opt/agents/applicationinsights-agent-3.7.9.jar" \
  -jar "orders-api.jar"
~~~

Lưu ý:
- **-javaagent** phải nằm trước **-jar**.
- Đường dẫn JAR phải tồn tại và được cung cấp qua artifact repository tin cậy.
- Không tự tải JAR từ URL ngẫu nhiên hoặc bỏ qua integrity validation.
- Không gắn connection string thật vào lệnh java -D trong CI log nếu policy không cho phép.
- Không attach thêm một OpenTelemetry agent khác lên JVM.
- Với Azure App Service auto-instrumentation qua portal, kiểm tra **nền tảng đã tự gắn Java agent hay chưa** trước khi tự thêm -javaagent.

### 9.4. Định danh service bằng role name

Trong lab, tệp cấu hình agent có thể được đặt cạnh JAR agent, ví dụ **applicationinsights.json**:

~~~json
{
  "role": {
    "name": "orders-api"
  },
  "sampling": {
    "requestsPerSecond": 5
  }
}
~~~

Tên role dùng cho Application Map. **requestsPerSecond** là sampling target, không phải traffic rate limit của API và cũng không đảm bảo thu đúng năm request mỗi giây theo mọi thời điểm/instance.

Với deployment nhiều services, Pricing và Invoice Worker nên dùng role names riêng.

Nếu App Service tự quản lý auto-instrumentation, platform có những cấu hình JSON/environment settings riêng; không thay file agent trong App Service portal khi chưa biết agent được tải và cấu hình từ đâu.

### 9.5. Sampling mặc định của Java agent

Theo Microsoft Learn hiện hành, từ **Java agent 3.4.0**, rate-limited sampling là mặc định, thường hướng đến khoảng **5 requests/second** và các dependency/logs liên quan đến requests được chọn. Điều này thay đổi so với các phiên bản cũ từng thu 100% requests.

Hệ quả:
- Một request cụ thể có thể không xuất hiện trong transaction search.
- Không coi thiếu trace là bằng chứng request không chạy.
- Khi test trace một lần, sampling có thể khiến kết quả không thấy ngay.
- Nếu cần test toàn vẹn, dùng cấu hình sampling phù hợp **chỉ trong lab**, không thay production sampling bừa bãi.
- Logs không gắn với request có thể có chính sách sampling khác; startup logs thường không bị request sampler làm mất mặc định.
- **Live Metrics** có sampling/telemetry behavior riêng; không phải bản sao hoàn hảo của kho Logs.

### 9.6. Chạy smoke test

Sau khi app khởi động, gửi một vài requests tới **lab endpoint** được phép:

~~~bash
curl -i "http://localhost:8080/health"
curl -i -X POST "http://localhost:8080/orders/demo-123/confirm"
~~~

Các URL trên là minh họa, không phải routes mặc định Spring Boot có sẵn. Nếu ứng dụng chưa định nghĩa endpoint, xem controller thực hành ở phần sau hoặc thay bằng endpoint lab có thật.

Trong Application Insights:
1. Kiểm tra resource/connection string đang trỏ đúng.
2. Tạo traffic từ môi trường lab.
3. Kiểm tra Requests/Dependencies và Application Map.
4. Query Logs trong khoảng thời gian UTC phù hợp.
5. Nếu chưa thấy data, chờ ingestion delay hợp lý và kiểm tra agent diagnostics/network/sampling.
6. Không kết luận thất bại ngay sau 1–2 giây.



## 10. Thực hành B: viết custom spans trong Spring Boot Java

### 10.1. Khi nào cần manual instrumentation?

Java agent thường tự tạo SERVER span khi HTTP controller nhận request và CLIENT span khi app gọi HTTP/JDBC được hỗ trợ. Nhưng những công đoạn như **định giá, kiểm tra hạn mức, xác thực business rule** có thể không có span riêng.

Thêm **manual INTERNAL span** để thấy rõ phần ứng dụng tự xử lý. Không tạo một SERVER span mới trùng với server span do Spring MVC agent đã tạo.

### 10.2. Dependencies

Trong pom.xml của ứng dụng Spring Boot, thêm **OpenTelemetry API**, quản lý phiên bản nhất quán với Java agent và dependency policy:

~~~xml
<dependency>
    <groupId>io.opentelemetry</groupId>
    <artifactId>opentelemetry-api</artifactId>
    <version>${opentelemetry.version}</version>
</dependency>
~~~

Biến opentelemetry.version là property do **BOM/dependency management** của dự án cung cấp; không phải Spring Boot nào cũng định nghĩa sẵn property này. Trước khi build, chọn một API version tương thích agent/runtime theo tài liệu OpenTelemetry. Thông thường **không cần tự thêm opentelemetry-sdk** nếu Java agent đã cấu hình provider/exporter và ứng dụng chỉ cần API.

### 10.3. Spring Boot controller minh họa

~~~java
package com.example.orders;

import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public final class OrdersController {
    private static final Tracer TRACER =
        GlobalOpenTelemetry.getTracer("com.example.orders.manual");

    @PostMapping("/{orderId}/confirm")
    public ResponseEntity<String> confirm(
            @PathVariable String orderId) {
        // SERVER span cho HTTP thường do Java agent tạo sẵn.
        Span span = TRACER.spanBuilder("orders.confirm")
            .setSpanKind(SpanKind.INTERNAL)
            .startSpan();

        try (Scope ignored = span.makeCurrent()) {
            // Đừng gắn orderId thẳng vào span nếu policy coi là PII
            // hoặc giá trị cardinality quá cao.
            span.setAttribute("orders.action", "confirm");
            span.setAttribute("orders.validation.mode", "standard");
            span.addEvent("orders.validation.started");

            if (orderId.isBlank()) {
                throw new IllegalArgumentException("Invalid order ID");
            }

            // Lab: giả lập bước xác nhận, không chạm DB/partner thật.
            span.addEvent("orders.validation.passed");

            return ResponseEntity.accepted()
                .body("Order accepted in lab");
        } catch (RuntimeException ex) {
            span.recordException(ex);
            span.setStatus(StatusCode.ERROR, "orders confirmation failed");
            throw ex;
        } finally {
            span.end();
        }
    }
}
~~~

Điểm quan trọng:

- **GlobalOpenTelemetry** được Java agent/SDK cung cấp khi cấu hình đúng; chỉ import API không tự tạo exporter.
- **SpanKind.INTERNAL** biểu diễn business step trong request.
- **makeCurrent()** thiết lập context cho lời gọi con trên cùng execution context.
- **recordException()** thêm exception event, nhưng không thay lỗi HTTP handler.
- **setStatus(ERROR)** mô tả span thất bại; không phải mã HTTP response.
- **span.end()** ở finally để đóng span dù request thất bại.
- **orderId** có thể là định danh cá nhân/kinh doanh; không đưa raw vào span name hoặc thuộc tính trước khi xác định policy.

Khi auto instrumentation được bật, nên thấy SERVER span “POST /orders/{orderId}” cùng child INTERNAL span “orders.confirm”. Nếu không bật agent/SDK, API có thể hoạt động như no-op; việc request trả 202 **không chứng minh telemetry đã được xuất**.

### 10.4. Thêm event thay vì quá nhiều spans

Nếu một bước nội bộ rất nhanh và không cần breakdown độc lập, thêm events vào span hiện có:

~~~java
Span current = Span.current();
current.addEvent("orders.price.checked");
current.setAttribute("orders.items.count", 3);
~~~

Đừng tạo hàng trăm child spans cho từng thao tác đơn giản trong một loop có hàng nghìn items. Mỗi span thêm payload, CPU, memory và chi phí ingestion. Chọn mức độ quan sát phục vụ điều tra và đo lường.

### 10.5. @WithSpan annotation

Một số instrumentation hỗ trợ annotation:

~~~java
import io.opentelemetry.instrumentation.annotations.WithSpan;

@WithSpan("orders.fraud-check")
public boolean fraudCheck() {
    return true;  // lab stub
}
~~~

Cần dependency annotations và Java agent/instrumentation hỗ trợ annotation đó. **Chỉ thêm annotation library không nhất thiết tạo telemetry**. Với Spring AOP/self-invocation/proxies, hãy kiểm tra annotation thực sự hoạt động trong cấu hình đang dùng.

### 10.6. Kiểm thử span hierarchy

Mục tiêu cho một POST hợp lệ:

~~~text
SERVER  POST /orders/{orderId}     50 ms
  INTERNAL orders.confirm          5 ms
    EVENT orders.validation.started
    EVENT orders.validation.passed
~~~

Nếu gọi HTTP outbound hoặc JDBC thật qua instrumentation được hỗ trợ, thêm CLIENT child spans. Không gắn business event “payment succeeded” nếu lab chưa thực hiện thanh toán: telemetry phải phản ánh sự kiện thật, không được dựng kết quả giả ở production.

## 11. Truyền context qua async executors và reactive code

### 11.1. Vì sao context bị mất?

OTel Context thường dùng **thread-local scope** trong Java. Một HTTP request bắt đầu trên thread A, nhưng ứng dụng chuyển xử lý sang executor thread B:

~~~text
Thread A: SERVER span đang active
    |
    | submit task
    v
Thread B: không có context nếu không propagate
    |
    v
Tạo span mới thành root khác hoặc mất parent
~~~

Một số Java auto instrumentation tự xử lý common executors/frameworks. Tuy nhiên không phải mọi custom queue/thread pool/reactive operator đều được hỗ trợ; cần kiểm tra trace thực thay vì giả định.

### 11.2. Capture rồi khôi phục context

Ví dụ Java thuần với một Executor đã được quản lý:

~~~java
import io.opentelemetry.context.Context;
import io.opentelemetry.context.Scope;
import java.util.concurrent.Executor;

public final class AsyncTaskExample {
    private final Executor executor;

    public AsyncTaskExample(Executor executor) {
        this.executor = executor;
    }

    public void scheduleInvoiceTask() {
        Context captured = Context.current();

        executor.execute(() -> {
            try (Scope ignored = captured.makeCurrent()) {
                // Mọi span mới ở đây có thể dùng captured parent.
                doBusinessWork();
            }
        });
    }

    private void doBusinessWork() {
        // Nội dung minh họa; implementation riêng của ứng dụng.
    }
}
~~~

Thời gian sống của Context và task phải được quản lý. Không giữ một Context chứa baggage không đáng tin cậy vô hạn trong shared singleton. Khi task bắt đầu nhiều giờ sau, tốt hơn dùng **explicit message context propagation** thay vì phụ thuộc thread-local của HTTP request cũ.

### 11.3. Reactor/CompletableFuture

Trong Spring WebFlux, Reactor dùng một execution model khác imperative thread-per-request:

- Thread có thể thay đổi sau publishOn/subscribeOn.
- Context.current() trên thread hiện tại không phải lúc nào cũng chứa parent nếu context bridge chưa được bật.
- Instrumentation/OTel–Reactor context propagation có các lựa chọn theo phiên bản agent/Reactor/Micrometer.
- Không gọi block() hoặc Thread.sleep trong Netty event loop để “giữ cùng thread”.
- Kiểm tra traces bằng integration tests khi dùng CompletableFuture, Reactor, coroutines hoặc custom scheduler.

Đừng bọc thủ công tất cả callbacks bằng một Context giả nếu framework instrumentation đã propagate; có thể tạo parent sai hoặc leak context giữa requests.

### 11.4. Thread-local không phải message context

Nếu một worker nhận message sau 20 phút, HTTP thread tạo message đã kết thúc. **Không thể dựa vào cùng một thread** để giữ trace context. Phải inject context vào **message attributes/properties**, sau đó receiver extract. Với nhiều event trong một batch, thường dùng **span links** đến từng producer context thay vì ép tất cả events có cùng một parent.

## 12. Distributed tracing qua Azure Service Bus

### 12.1. Các bên tham gia

~~~mermaid
flowchart LR
    API["Orders API"] --> SEND["PRODUCER: Service Bus send"]
    SEND --> Q["Azure Service Bus queue"]
    Q --> RECV["CONSUMER: invoice-worker process"]
    RECV --> BLOB["CLIENT: Blob upload"]
~~~

Bên gửi và nhận thường khác tiến trình/thời điểm. Trace context cần nằm trong message metadata mà cả producer lẫn consumer hiểu. Một số phiên bản **Azure Service Bus Java SDK** và instrumentation có thể tự propagation; kiểm tra thật trước khi viết logic thủ công.

### 12.2. Inject bằng OpenTelemetry propagator

Ví dụ transport-neutral, chuẩn bị **Map<String,String>** làm carrier. Sau đó adapter của SDK đưa các cặp key-value vào application properties của message:

~~~java
import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.context.Context;
import java.util.HashMap;
import java.util.Map;

Map<String, String> headers = new HashMap<>();

GlobalOpenTelemetry.getPropagators()
    .getTextMapPropagator()
    .inject(
        Context.current(),
        headers,
        (carrier, key, value) -> carrier.put(key, value)
    );

// Đối với một ServiceBusMessage cụ thể, khi SDK không tự
// propagate, copy các giá trị vào application properties:
// headers.forEach((k, v) ->
//     serviceBusMessage.getApplicationProperties().put(k, v)
// );
~~~

Chỉ thực hiện thủ công **khi SDK/instrumentation chưa inject**. Nếu đã có headers traceparent/tracestate, không ghi đè bằng một context mới. Message application properties phải tuân thủ giới hạn kích thước/type của Azure Service Bus và không chứa secret trong baggage.

### 12.3. Extract tại consumer

~~~java
import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.Scope;
import io.opentelemetry.context.propagation.TextMapGetter;

import java.util.Map;

// Trong ứng dụng thật, lấy map từ message SDK:
// receivedMessage.getApplicationProperties()
Map<String, Object> messageProperties = Map.of(); // placeholder lab
Map<String, String> headers = new java.util.HashMap<>();
messageProperties.forEach((key, value) -> {
    if (value instanceof String) {
        headers.put(key, (String) value);
    }
});

TextMapGetter<Map<String, String>> getter = new TextMapGetter<>() {
    @Override
    public Iterable<String> keys(Map<String, String> carrier) {
        return carrier.keySet();
    }

    @Override
    public String get(Map<String, String> carrier, String key) {
        return carrier.get(key);
    }
};

Context remote = GlobalOpenTelemetry.getPropagators()
    .getTextMapPropagator()
    .extract(Context.root(), headers, getter);

Tracer tracer = GlobalOpenTelemetry.getTracer("com.example.invoice");

Span consumer = tracer.spanBuilder("invoice.process")
    .setParent(remote)
    .setSpanKind(SpanKind.CONSUMER)
    .startSpan();

try (Scope ignored = consumer.makeCurrent()) {
    // Xử lý message với giới hạn concurrency và idempotency.
} finally {
    consumer.end();
}
~~~

**Quan trọng:** đây là **khung minh họa API**, không copy nguyên văn chạy: headers phải được đọc từ message thật, xử lý null, giới hạn kích thước và chuẩn hóa giá trị string theo Azure Service Bus SDK. Một số thư viện nhận message đã tạo CONSUMER span; tạo thêm thủ công lúc đó có thể gây duplicate spans. Chỉ tự instrument thiếu sót được xác nhận.

### 12.4. Tracing không giải quyết exactly-once

Trong queue:
- Producer có thể gửi lại cùng message nếu ACK mất.
- Consumer có thể bị retry sau khi xử lý phần lớn công việc.
- Dead-letter queue và lock renewal có semantics riêng.
- Một message có thể được xử lý ở worker khác sau vài phút.
- Traces có thể ghi **nhiều consumer spans** cho các attempts khác nhau.

Trace giúp thấy **retry/deliveryCount/queue lag**, không ngăn tạo invoice trùng. Cần **stable message ID, idempotency key, database unique constraints hoặc transactional outbox** theo nghiệp vụ.

### 12.5. Parent hoặc link?

Khi consumer xử lý đúng một message, có thể dùng extracted remote context làm parent nếu pattern/framework hỗ trợ. Với:
- Batch nhiều messages,
- Fan-in từ nhiều producers,
- Long-running workflows,
- Reprocessing/backfill,

**span links** thường diễn đạt tốt hơn nhiều parent contexts. Một span chỉ có một parent, nhưng có thể link tới nhiều contexts. Chọn theo OpenTelemetry messaging semantic conventions và kiến trúc của bạn.

## 13. Thực hành C: OTLP Collector trong môi trường phát triển

### 13.1. Vì sao làm lab Collector?

Để hiểu **OpenTelemetry chuẩn** tách biệt Azure Monitor exporter. Một Collector có thể nhận OTLP của ứng dụng, batch dữ liệu và đưa ra debug logs trước khi chọn observability backend. Lab này **không dùng Application Insights connection string** và không gửi đến Azure production.

### 13.2. Pipeline tối thiểu

~~~mermaid
flowchart LR
    APP["OpenTelemetry Java agent"] -->|OTLP HTTP/gRPC| C["Collector OTLP receiver"]
    C --> ML["memory_limiter"]
    ML --> BA["batch processor"]
    BA --> DE["debug exporter - lab only"]
~~~

Một ví dụ cấu hình Collector trên localhost:

~~~yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 127.0.0.1:4317
      http:
        endpoint: 127.0.0.1:4318

processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 256
  batch: {}

exporters:
  debug:
    verbosity: basic

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [debug]
~~~

**Đây là cấu hình Collector demo**. Trong container/Kubernetes cần bind/network address khác và bảo vệ receiver bằng TLS/auth/network policies nếu không chỉ chạy trên localhost. Không expose 0.0.0.0:4317 công khai lên Internet. Các Collector releases có thể thay đổi component availability; kiểm tra distribution đang dùng hỗ trợ memory_limiter, batch, debug.

### 13.3. Khởi chạy một OTel Java agent riêng

Một tuyến OTLP thuần có thể dùng **upstream OpenTelemetry Java agent** thay vì Azure Monitor Java agent:

~~~bash
export OTEL_SERVICE_NAME="orders-api"
export OTEL_TRACES_EXPORTER="otlp"
export OTEL_EXPORTER_OTLP_PROTOCOL="http/protobuf"
export OTEL_EXPORTER_OTLP_ENDPOINT="http://127.0.0.1:4318"

java -javaagent:"/opt/agents/opentelemetry-javaagent.jar" \
  -jar "orders-api.jar"
~~~

Agent JAR phải được lấy từ nguồn chính thức, pin version/verify checksum và tương thích JDK. Chỉ chạy phương án này **thay cho** Application Insights Java agent ở phần 9 khi mục đích là hiểu OTLP pipeline. Không attach cả hai agents cùng lúc.

### 13.4. OTLP protocol và endpoints

| Transport | Port thường dùng | Ghi chú |
|---|---|---|
| OTLP/gRPC | 4317 | Cần gRPC-compatible receiver |
| OTLP/HTTP protobuf | 4318 | HTTP/protobuf; endpoint base thường được SDK mở rộng theo signal |
| Application Insights ingestion | Theo Azure Monitor connection string | **Không phải generic OTLP endpoint** |

Kiểm tra OTEL_EXPORTER_OTLP_PROTOCOL và OTEL_EXPORTER_OTLP_ENDPOINT có tương thích. Một Collector nhận trên 4318 không nhất thiết nhận gRPC trên cùng cổng.

### 13.5. Những thành phần Collector production

Một Collector khi production thường cần:
- Authentication/TLS giữa app và Collector.
- NetworkPolicy/Private Endpoint hoặc private network path.
- Memory limiter, bounded queues, batch processor.
- Exporter retries và backpressure.
- Health, self-metrics và logs.
- High availability/replica strategy.
- Data loss/restart semantics và optional persistent queue nếu supported.
- Attr filtering/redaction trước export.
- Ownership, version pinning, security patching.

Collector **không bảo đảm mọi telemetry được lưu bền vững** chỉ vì bạn bật batch. Nếu process crash trước khi batch xuất, có thể mất dữ liệu đang nằm trong memory. Thiết kế reliability theo khả năng exporter/queue/storage thực.



## 14. Sampling: chọn dữ liệu có chủ đích

### 14.1. Vì sao không giữ mọi span?

Một hệ thống nhận 10.000 requests/giây, mỗi request sinh trung bình 15 spans:

~~~text
10,000 requests/s × 15 spans/request
    = 150,000 spans/s

Trong 1 ngày:
    150,000 × 86,400
    = 12,960,000,000 spans/day
~~~

Đây chỉ là tính toán minh họa trước khi tính logs, metrics, request payload sizes, compression và ingest retries. Việc thu toàn bộ có thể tăng CPU/memory, egress, ingestion và retention costs đáng kể.

### 14.2. Head sampling

**Head sampling** đưa quyết định lấy mẫu khi trace/request bắt đầu, ví dụ giữ khoảng 10% traces. Ưu điểm đơn giản, ít overhead; nhược điểm **không biết trước request có chậm hoặc lỗi ở cuối hay không**.

Ví dụ:

~~~text
Root request enters API
Sampler decides: retain (sampled=1)
    → downstream spans inherit decision where supported

Root request enters API
Sampler decides: drop (sampled=0)
    → có thể không lưu span tree vào backend
~~~

**Parent-based sampling** thường giúp một trace có kết quả nhất quán giữa các services. Nếu một service drop spans độc lập dựa random sampling, có thể tạo những traces đứt đoạn. Ngược lại, nếu một downstream service không tôn trọng sampled flag hoặc sampling strategy của backend, vẫn có nguy cơ missing/partial traces.

### 14.3. Rate-limited sampling trong Azure Monitor Java

Trong Azure Monitor Application Insights Java agent (theo tài liệu tại thời điểm soạn), rate-limited sampling đã là mặc định từ agent 3.4.0 với mục tiêu khoảng **5 requests mỗi giây** cùng telemetry phụ thuộc phù hợp.

Một cấu hình minh họa:

~~~json
{
  "sampling": {
    "requestsPerSecond": 5
  }
}
~~~

Đây là cấu hình **per-agent process**, không phải giới hạn traffic của toàn cluster và không bảo đảm giữ chính xác 5 traces/giây trong mọi giây. Nếu 20 replicas có traffic, tổng số sampled requests không phải ngưỡng 5 toàn hệ thống. Cần tính số replicas/regions và dynamic scaling.

Nếu cần tìm một test request cụ thể:
- Không dùng việc “không thấy trace” để kết luận request không đi qua service.
- Lấy logs/metrics corroboration và kiểm tra sampling.
- Có thể cấu hình sampling phù hợp trong **staging** để thuận lợi cho smoke tests.
- Không tắt sampling toàn fleet production mà chưa đánh giá ingestion costs.

### 14.4. Fixed-percentage sampling

Khi muốn giữ một tỷ lệ tương đối ổn định, có thể cấu hình percentage sampling theo khả năng Java agent đang dùng. Chẳng hạn 10% của 10.000 requests/s về mặt thống kê khoảng 1.000 requests/s **trước khi xét semantic/replica effects**.

Ưu điểm: dễ ước lượng theo tỷ lệ. Hạn chế: số traces vẫn tăng tuyến tính khi traffic tăng, và các lỗi hiếm có thể không được lấy mẫu.

**Không tính error rate production đơn giản bằng số failed spans / số successful spans trong dữ liệu đã sampling** nếu sampling policy khác theo status/route; metric-based SLI hoặc weighted estimators phù hợp hơn.

### 14.5. Tail sampling

**Tail sampling** đợi thu thập phần lớn hoặc toàn bộ spans của một trace trước khi quyết định giữ, ví dụ ưu tiên traces có lỗi hoặc latency cao.

~~~mermaid
flowchart LR
    S["Spans from many services"] --> C["Collector tail sampler"]
    C --> Q{"Slow / Error / Selected?"}
    Q -->|Yes| B["Keep trace"]
    Q -->|No| D["Drop trace"]
~~~

Những rủi ro:
- Collector phải **buffer spans** trong một khoảng, tăng memory.
- Cần routing nhất quán để spans của cùng trace tới sampling decision point.
- Traces rất dài/async có thể đến sau decision window.
- Collector crash có thể làm mất buffered traces.
- Không phải backend/exporter nào tương thích mọi sampling strategy.
- Với Application Insights, cần tôn trọng **Azure Monitor sampler** và yêu cầu trace completeness; không mặc định gắn arbitrary tail sampling trước exporter mà sẽ luôn cho kết quả đúng.

Tail sampling là quyết định kiến trúc có kiểm thử, không phải toggle đơn giản cho Azure Monitor Java agent.

### 14.6. Sampling logs và metrics

- **Traces:** thường được sample để giảm khối lượng.
- **Metrics:** thường aggregate, không giống cách sample từng trace; có cardinality limits riêng.
- **Logs:** có thể sample/filter, nhưng critical security/audit logs cần retention/collection policy khác.
- **Logs gắn với request:** một số integration giữ cùng trace sampling decision nhằm bảo vệ correlation.
- **Logs startup/background:** có thể có sampling behavior khác request logs.

Trước khi thay policy, đo **chi phí + khả năng điều tra + compliance**. Không hy sinh toàn bộ exception evidence để tiết kiệm ingestion mà không có giải pháp bổ sung.

### 14.7. Bảng lựa chọn ban đầu

| Mục tiêu | Chiến lược cân nhắc | Điều kiện |
|---|---|---|
| Lab 20 requests | Sampling cao trong staging | Không gửi PII/prod |
| Production nhiều RPS | Rate-limit/percentage | Cần SLO/cost budget |
| Sự cố lỗi hiếm | Override theo route/error khi khả năng hỗ trợ | Không phá trace correlation |
| Truy vết dài qua queue | Propagation + retention/collector evaluation | Async traces có late spans |
| Compliance audit | Logs/audit pipeline riêng | Không chỉ dựa sampled traces |

## 15. KQL: truy vấn distributed traces trên Application Insights

### 15.1. Không nhầm tên bảng

Trong **workspace-based Application Insights**:
- **AppRequests:** inbound/server request telemetry.
- **AppDependencies:** outbound dependency calls và nhiều internal operations.
- **AppTraces:** logs/tracing messages.
- **AppExceptions:** exception records.

Trong những trải nghiệm/query legacy hoặc phạm vi resource khác có thể gặp bảng **requests, dependencies, traces, exceptions** với tên cột khác. Hãy xác định Log Analytics context trước khi copy KQL.

### 15.2. Request latency và lỗi theo service

~~~kusto
AppRequests
| where TimeGenerated > ago(1h)
| summarize
    Requests = sum(ItemCount),
    Failures = sumif(ItemCount, Success == false),
    P95Ms = percentile(DurationMs, 95)
  by bin(TimeGenerated, 5m), AppRoleName
| order by TimeGenerated asc
~~~

**ItemCount** có thể biểu diễn trọng số sampling, nên tổng Requests thường dùng sum(ItemCount) thay vì count() khi ước lượng volume. Percentile ở truy vấn trên không tự áp trọng số sampling; coi đây là quan sát sơ bộ trên dữ liệu được giữ, không nhất thiết là percentile population chính xác.

### 15.3. Tìm top dependencies chậm

~~~kusto
AppDependencies
| where TimeGenerated > ago(1h)
| summarize
    Calls = sum(ItemCount),
    Failed = sumif(ItemCount, Success == false),
    P95Ms = percentile(DurationMs, 95)
  by AppRoleName, Type, Target, Name
| top 20 by P95Ms desc
~~~

Kết quả cho biết dependency nào có latency cao trong dữ liệu được thu thập. Không kết luận Azure Storage luôn chậm nếu chỉ có 2 samples và 1 sample 2 giây; kiểm tra volume, distribution và sampling.

### 15.4. Tìm một trace bằng OperationId

Giả sử đã có trace ID từ một response/log có quyền:

~~~kusto
let targetTraceId = "4bf92f3577b34da6a3ce929d0e0e4736";
union
    (
      AppRequests
      | where OperationId == targetTraceId
      | project TimeGenerated, Signal="request",
          AppRoleName, Name, Id, ParentId,
          OperationId, DurationMs, Success, ResultCode
    ),
    (
      AppDependencies
      | where OperationId == targetTraceId
      | project TimeGenerated, Signal="dependency",
          AppRoleName, Name, Id, ParentId,
          OperationId, DurationMs, Success, ResultCode
    )
| order by TimeGenerated asc
~~~

Nếu trace nằm ở nhiều Application Insights resources/workspaces, một query chỉ trên một workspace có thể không thấy toàn bộ services. Cần cross-resource/union đúng và người truy vấn có RBAC phù hợp.

### 15.5. Xem exceptions của cùng trace

~~~kusto
let targetTraceId = "4bf92f3577b34da6a3ce929d0e0e4736";
AppExceptions
| where TimeGenerated > ago(24h)
| where OperationId == targetTraceId
| project TimeGenerated, AppRoleName,
    Type, Method, Message, ProblemId, OperationId
| order by TimeGenerated asc
~~~

Trong môi trường sản xuất, exception messages có thể chứa nội dung đầu vào nhạy cảm. Không copy toàn bộ KQL result ra bug tracker công khai; redact và giới hạn người xem.

### 15.6. Liên kết request và dependency

~~~kusto
let errors =
    AppRequests
    | where TimeGenerated > ago(1h)
    | where Success == false
    | project OperationId, RequestName=Name,
        RequestRole=AppRoleName, RequestMs=DurationMs;
errors
| join kind=leftouter (
    AppDependencies
    | where TimeGenerated > ago(1h)
    | project OperationId, DependencyName=Name,
        DependencyTarget=Target, DependencyMs=DurationMs,
        DependencySuccess=Success
) on OperationId
| order by RequestMs desc, DependencyMs desc
~~~

Một request có nhiều dependencies nên **join có thể nhân nhiều rows**. Query là công cụ điều tra, không phải phép cộng duration của mọi dependency để ra tổng request duration; các child operations có thể chạy song song hoặc lồng nhau.

### 15.7. Nhận diện log correlation

~~~kusto
AppTraces
| where TimeGenerated > ago(30m)
| where OperationId == "4bf92f3577b34da6a3ce929d0e0e4736"
| project TimeGenerated, AppRoleName,
    SeverityLevel, Message, OperationId, ParentId
| order by TimeGenerated asc
~~~

Nếu AppTraces không có OperationId cho log, có thể là log được ghi ngoài span context hoặc instrumentation/log correlation chưa bật. Đừng ép mọi background log vào trace ID của request gần nhất theo timestamp.

### 15.8. Đừng dựa duy nhất vào KQL cho mọi SLO

KQL trên sampled traces hữu ích để **điều tra**. Availability/latency SLO cần nguồn đo phù hợp:
- Azure Monitor metrics hoặc app-level counters/histograms.
- Application Insights request data có sampling weights/limitations được hiểu rõ.
- Synthetic availability tests nếu đã cấu hình.
- Load balancer/gateway metrics nếu là nguồn sự thật của total traffic.
- Service Bus queue age/lag nếu đánh giá background processing.

Nếu 100% error traces được giữ nhưng chỉ 5% successful traces, tỷ lệ failed/successful trong bảng không còn phản ánh error rate thật nếu không điều chỉnh phương pháp.

## 16. Log correlation và truy vết lỗi thực tế

### 16.1. Trace ID trong structured logs

Một log hữu ích có thể như:

~~~json
{
  "timestampUtc": "2026-11-20T10:05:10Z",
  "level": "WARN",
  "service": "orders-api",
  "event": "pricing_timeout",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "error_type": "TimeoutException",
  "dependency": "pricing-api",
  "duration_ms": 2000
}
~~~

Đây là JSON minh họa, không phải logging format mặc định của mọi Java agent. Các trường cần được lấy từ **active OTel context** hoặc log correlation instrumentation; không tự đặt trace ID ngẫu nhiên cho mỗi log line.

### 16.2. Trace ID không thay request ID của nghiệp vụ

- **Trace ID:** correlation cho execution path.
- **Span ID:** operations trong một trace.
- **Business order ID:** đối tượng nghiệp vụ, có thể nằm trong datastore và logs được bảo vệ.
- **Message ID:** nhận diện message/retry, hỗ trợ idempotency.
- **Idempotency key:** ngăn side effects trùng.
- **Request ID:** ID cấp gateway/service cho một HTTP request cụ thể.

Một order có thể có **nhiều traces** (create, retry, status poll, refund). Một trace cũng có thể xử lý nhiều objects trong batch. Không dùng trace ID làm unique key của database transaction.

### 16.3. Phát hiện lỗi do retry

Ví dụ một user request có:
- SERVER span tổng 6 giây.
- CLIENT Pricing span 2 giây thất bại.
- CLIENT Pricing retry span 2 giây.
- CLIENT Pricing cuối 1 giây thành công.
- SQL insert 50 ms.

Lúc này tăng Azure SQL DTUs không cải thiện p99: vấn đề nằm ở HTTP timeout/retry với Pricing. Tuy nhiên **có thể không thấy mỗi attempt** nếu thư viện instrumentation chỉ ghi logical dependency span; kiểm tra SDK/agent settings khi cần attempt-level detail.

### 16.4. Clock skew trong spans

Các dịch vụ khác nhau có thể có đồng hồ lệch vài giây. Bản trace vẫn liên kết bởi IDs nhưng waterfall có thể cho impression span child bắt đầu trước parent.

Hãy kiểm tra:
- NTP/clock synchronization của VMs/edge devices.
- Thời gian UTC và time zone.
- Agent/SDK clock source.
- Message enqueue time vs process time.
- Query ingestion delay khác event timestamp.

Không dùng **một timestamp của downstream** để chứng minh thứ tự tuyệt đối khi clocks không đồng bộ.

### 16.5. Thứ tự event và asynchronous work

HTTP request hoàn thành lúc 10:00, invoice worker xử lý 10:05. Nếu worker giữ cùng trace ID, timeline kéo dài 5 phút. Một số tracing backend hiển thị theo kiểu có gaps hoặc chia trace; quan hệ producer-consumer/span links có thể khác tùy instrumentation.

Trace này không đồng nghĩa request HTTP đã chờ worker 5 phút. SLO HTTP và background queue processing phải đo riêng.

## 17. Azure hosting: App Service, AKS, Container Apps, Functions

### 17.1. Azure App Service

Có thể bật Application Insights auto-instrumentation/Java agent bằng cấu hình App Service được hỗ trợ, hoặc chủ động attach agent JVM trong deployment. **Không dùng cả hai cùng lúc** nếu chúng instrument cùng workload.

Kiểm tra:
- App Service runtime/JDK.
- Connection string và role name.
- VNet integration/egress đến ingestion endpoint.
- Startup parameters/JAVA_TOOL_OPTIONS khi áp dụng.
- Agent log và app logs.
- Auto-instrumentation đã được portal bật hay chưa.
- Slot staging/production có trỏ đúng App Insights resource hay không.

Nếu triển khai slot swap, đừng vô tình gửi telemetry staging sang production resource hoặc ngược lại; phân biệt cloud role/environment.

### 17.2. AKS

Một hướng triển khai Java agent:
- Pin agent JAR trong image hoặc mount qua cơ chế tin cậy.
- Cấu hình JVM argument trong container entrypoint/JAVA_TOOL_OPTIONS.
- Đưa Application Insights connection string qua configuration/secret mechanism được duyệt.
- Gắn role/service name ổn định (không phải Pod UID).
- Giới hạn CPU/memory của agent.
- Kiểm tra NetworkPolicy, outbound TLS, DNS.
- Rollout/canary với HPA, rate-limited sampling và cost budgets.
- Không expose OTLP Collector receiver công khai khi dùng private pipeline.

Nếu dùng Collector trong AKS, quyết định **sidecar, daemonset hoặc gateway deployment** theo topology, cardinality và ownership. Không mặc định DaemonSet có thể thu spans của mọi Pod nếu ứng dụng chưa xuất OTLP/agent chưa có config.

### 17.3. Azure Container Apps

Container Apps có revision-based deployment, managed identities, egress và scaling riêng. Java app có thể attach agent hoặc gửi OTLP tới Collector khi được hỗ trợ. Cần kiểm tra:
- Revision và service.version.
- Scale-to-zero/cold start telemetry.
- Container memory overhead.
- Private networking/ingestion endpoint.
- Khả năng propagate context giữa app và worker revisions.
- Logs có bị thu hai lần qua platform logger + agent hay không.

### 17.4. Azure Functions

Functions có trigger/context propagation phụ thuộc ngôn ngữ, hosting model và integration hỗ trợ. Với HTTP trigger, auto-instrumentation có thể tạo server span; với Service Bus/Event Hubs trigger cần kiểm tra producer/consumer context. Không chỉ thêm library rồi giả định end-to-end traces xuất hiện đầy đủ.

Phải phân biệt:
- Function invocation ID.
- OTel trace ID/span ID.
- Message ID/sequence.
- Trigger retries và dead-letter/poison semantics.

### 17.5. Networking và Microsoft Entra ID

Đường xuất telemetry tới Azure Monitor ingestion khác đường ứng dụng truy cập Key Vault/Storage/SQL. Để dữ liệu tới Application Insights:
- DNS/TLS tới ingestion endpoints đúng sovereign cloud/region.
- Egress firewall/proxy cho phép traffic cần thiết.
- Connection string cấu hình đúng resource.
- Managed identity cho **truy cập dữ liệu của app** không tự làm thay đổi telemetry exporter authentication.
- Azure RBAC để xem Log Analytics khác quyền gửi telemetry.

Không mở wildcard outbound không cần thiết hoặc tắt TLS validation để chữa exporter timeout. Kiểm tra network docs của Azure Monitor/Application Insights và deployment thực tế.

## 18. Bảo mật, quyền riêng tư và multi-tenant observability

### 18.1. Threat model cho tracing

Dữ liệu tracing có thể vô tình chứa:
- Authorization bearer tokens, JWT, SAS query strings.
- Request/response bodies chứa PII.
- SQL statements với literal values.
- Customer name/email/phone/address.
- Payment or medical details.
- Baggage do client tự đặt.
- Internal service endpoints/topology.
- Stack traces chứa user input hoặc secrets.
- Resource labels có customer IDs.

Traces không phải nơi lưu log/audit mọi dữ liệu. Cần **data minimization** theo luật và policy của tổ chức.

### 18.2. Không đưa secrets vào attributes/baggage

Sai:

~~~text
http.request.header.authorization = "Bearer ..."
user.email = "customer@example.com"
db.statement = "SELECT ... WHERE password='secret'"
baggage = "tenantPrivateKey=..."
~~~

Nên:

~~~text
http.route = "/orders/{orderId}"
http.request.method = "POST"
http.response.status_code = 503
dependency.type = "database"
error.type = "timeout"
orders.channel = "mobile"
~~~

Nếu cần tenant attribution, dùng một ID đã được đánh giá theo data classification và tránh labels không giới hạn/đa tenant isolation leaks. Không gửi tenant secrets qua baggage.

### 18.3. Traceparent là untrusted

Một malicious caller có thể gửi traceparent/tracestate/baggage tùy ý. Proxy/agent nên:
- Validate header format/size.
- Giới hạn baggage keys/values.
- Không dùng sampled bit như quyền bảo mật.
- Tạo trace context mới khi header invalid và phù hợp trust boundary.
- Không tin user role/tenant authorization trong baggage.
- Không dùng trace ID làm permission token.

### 18.4. Authorization xem telemetry

Người xem Application Insights/Log Analytics có thể học về:
- Endpoint names, exception patterns, internal topology.
- Request metadata và các values nếu collector để lọt.
- Release versions và resource identifiers.

Cần Azure RBAC least privilege, audit truy vấn khi được hỗ trợ, retention, workspace separation hoặc data access model phù hợp. Một connection string xuất telemetry **không cấp quyền đọc mọi traces**, nhưng cũng không nên phát tán vô hạn.

### 18.5. Redaction theo nhiều lớp

1. Ở ứng dụng, đừng tạo attributes nhạy cảm.
2. Ở instrumentation library/agent, cấu hình capture headers/body/SQL phù hợp.
3. Ở Collector, redact/filter khi có pipeline và capability hỗ trợ.
4. Ở ingestion backend, thiết kế data governance/retention.
5. Ở KQL export/incident sharing, loại PII trước khi chia sẻ.

Một regex redaction ở Collector **không đảm bảo loại mọi secret** nếu telemetry đã được xuất sang destination khác trước đó. Data minimization từ nguồn vẫn là ưu tiên.

### 18.6. Bảo vệ môi trường test

Lab có thể dùng orderId “demo-123”, fake email và fake token. Không dùng live API keys, customer records hoặc production SQL snapshots để kiểm thử tracing. Nếu cần tái hiện lỗi production, sử dụng dữ liệu đã khử định danh hoặc controlled access/retention được phê duyệt.



## 19. Hiệu năng, chi phí và quản trị telemetry

### 19.1. Instrumentation có chi phí

OpenTelemetry hữu ích nhưng không miễn phí. Các chi phí cần tính:

~~~text
Total observability cost =
    Application instrumentation CPU + memory
  + Telemetry serialization/network egress
  + Agent / Collector compute and storage queues
  + Azure Monitor ingestion and data retention
  + Log Analytics querying/workspaces
  + Alerts, Workbooks and incident analysis
  + Operations, upgrades and security governance
~~~

Giá cụ thể thay đổi theo region, pricing plan, retention, data tiers và chính sách Azure Monitor. Không lấy ví dụ trong tài liệu làm báo giá hiện hành.

### 19.2. Ước tính volume

Giả sử ứng dụng có:
- 2 triệu requests mỗi ngày.
- Trung bình 8 spans cho một request.
- Kích thước serialized span trung bình giả định là 500 bytes.

~~~text
Raw spans per day:
  2,000,000 × 8 = 16,000,000 spans

Approx telemetry payload:
  16,000,000 × 500 bytes
  = 8,000,000,000 bytes
  ≈ 8 GB/ngày (decimal units)

30 days at same level:
  ≈ 240 GB raw estimated
~~~

Đây chỉ là **ước lượng thô**; thật tế có attributes, events, stack traces, logs, wire compression, sampling, ingestion format và overhead khác. Một agent default ~5 requests/s có thể giảm volume so với 100% tracing, nhưng không đảm bảo dung lượng bằng công thức đơn giản trên.

### 19.3. Kiểm soát cardinality

Sai:
- span name = “GET /orders/12345”.
- Metric label = mỗi user ID.
- Resource service.name = tên Pod UUID.
- Attribute chứa raw query SQL với literal values.
- Log field chứa từng requestId được dùng làm aggregate group.

Tốt hơn:
- span name dùng route template.
- service.name ổn định theo application.
- service.version có số release được kiểm soát.
- Exception type/statusClass/cardinality nhỏ.
- Trace IDs nằm trong trace/log records, không là nhãn của time-series metrics.

### 19.4. Tối ưu số lượng spans

Trước khi tạo custom spans cho từng dòng dữ liệu:
1. Dùng auto instrumentation đã có.
2. Xác định business steps có ích cho troubleshooting.
3. Chỉ tạo spans cho operations có độ trễ hay lỗi đáng quan tâm.
4. Dùng span events cho các mốc nhỏ.
5. Giảm hoặc loại attrs không hữu ích.
6. Xem overhead dưới load test.
7. So p95/p99 ứng dụng có/không instrumentation.
8. Giữ khả năng debug và audit theo policy.

Không giảm sampling quá thấp khiến mọi incident đều không thể điều tra; phối hợp traces với metrics/logs.

### 19.5. Daily cap và retention

Azure Monitor/Application Insights có các chính sách capacity, daily cap hoặc retention theo cấu hình/plan. Chúng giúp kiểm soát chi phí nhưng cần hiểu:

- Khi chạm cap, một phần telemetry có thể không được lưu như dự kiến.
- Log Analytics retention có thể ảnh hưởng thời gian điều tra incidents.
- App metrics và logs/traces có retention/ingestion paths khác nhau.
- Privacy/legal hold có thể yêu cầu thời gian giữ riêng.
- Cần alert khi volume tăng đột biến thay vì chỉ chờ cap cắt dữ liệu.
- Bật duplicate instrumentation có thể khiến chi phí tăng đột ngột.

**Daily cap không phải chiến lược sampling và không bảo đảm trace completeness.**

### 19.6. Budgets, tags và quyền sở hữu

Mỗi Application Insights/Collector/Log Analytics workspace nên có:
- Owner/team.
- Environment và region.
- Cost center/tag theo governance.
- Data retention và data classification.
- Sampling policy có version.
- Agent/Collector version và update schedule.
- Incident responder/on-call.
- Query/dashboard runbooks.
- Budget/alert thresholds.
- RPO/RTO đối với observability pipeline khi cần.

Observability phải có người vận hành; không chỉ là một checkbox “Enable Application Insights” trong portal.

## 20. Kế hoạch kiểm thử tracing có thể lặp lại

### 20.1. Ba lớp kiểm thử

| Loại | Mục tiêu | Không thay thế |
|---|---|---|
| Unit test | Manual span creation, attrs, error status, no PII | Network propagation |
| Integration test | HTTP/service messaging trace context end-to-end | Full production load |
| Load/fault injection | Sampling, exporter outage, p95 overhead, scalability | Semantic correctness của business |

Dùng staging/subscription lab và dữ liệu giả. Không phát request sai tới payment production hoặc cố tình flood Application Insights để thử quotas.

### 20.2. HTTP propagation test

Một integration test có thể tạo:
- Orders HTTP endpoint nhận request có traceparent hợp lệ.
- Orders gọi Pricing bằng HttpClient đã instrument.
- Pricing nhận traceparent và tạo SERVER span.
- Azure Monitor/Collector nhận ít nhất một trace giữ chung trace ID.
- Parent-child relation hợp lý.
- Test không đưa user email/Authorization vào attributes.

Mẫu expected:

~~~text
Trace ID: 4bf92f3577b34da6a3ce929d0e0e4736

orders-api  SERVER  POST /orders/{orderId}
   orders-api CLIENT GET /price
      pricing-api SERVER GET /price
         pricing-api INTERNAL calculate-price
~~~

Đừng khẳng định số spans phải luôn đúng bốn; agent có thể bổ sung DNS/network/SDK spans, hoặc sampling làm mất một số.

### 20.3. Async message test

1. HTTP handler tạo message có stable message ID.
2. Producer inject OTel context vào message metadata.
3. Worker nhận và extract; có CONSUMER span hoặc link phù hợp.
4. Worker gọi Blob Storage và quan sát dependency.
5. Worker retry message một lần theo lab setup.
6. Không tạo hai invoices (đây là kiểm thử idempotency riêng).
7. Đảm bảo trace logs có message ID/correlation hợp lệ.
8. Xem queue delay, delivery count và child spans.
9. Không lưu baggage nhạy cảm.
10. Nếu Service Bus SDK tự instrument, không chèn duplicate manual consumer span.

### 20.4. Sampling tests

- Chạy 10–20 requests trong lab, cho sampling phù hợp.
- Kiểm tra sampled/unsampled behavior.
- Test parent sampled flag đi qua HTTP boundaries.
- Với rate-limit sampling, tạo nhiều requests hơn threshold và xác minh volume giảm.
- Kiểm tra logs không gắn request có thể vẫn được thu theo agent policy.
- Xem traces được giữ có đầy đủ chain trong giới hạn instrumentation.
- So metrics volume với traces volume.
- Test regression sau khi thay agent configuration/release.

### 20.5. Exporter/Collector failure tests

~~~text
Condition A: Collector unavailable
Condition B: DNS failure to Azure Monitor ingestion
Condition C: Proxy/TLS failure
Condition D: Exporter receives throttling/5xx
Condition E: Collector memory limit reached
Condition F: App exits before batch flush
~~~

Mục tiêu:
- **Ứng dụng business không bị block vô hạn** chỉ vì telemetry backend down.
- Agent/Collector có bounded buffering/retry.
- Logs/metrics báo telemetry drops/export errors.
- Không log connection string hoặc secrets trong diagnostic error.
- Khi backend hồi phục, kết quả đúng theo loss/replay guarantees thực tế.
- SLO của ứng dụng vẫn được bảo vệ.

Không mô tả tracing là **transactional audit log** hoặc nguồn duy nhất để chứng minh một giao dịch tài chính đã xảy ra; observability telemetry có thể bị sample/drop.

### 20.6. Security tests

- Gửi request header Authorization giả, kiểm tra nó **không hiện** trong spans.
- Gửi query string có marker giả nhạy cảm, kiểm tra redaction.
- Thử baggage quá lớn hoặc key không có trong allowlist.
- Đảm bảo tenant A không đọc telemetry của tenant B nếu yêu cầu isolation.
- Kiểm tra IAM của Application Insights/Log Analytics.
- Xem raw stack traces/SQL text không chứa customer data.
- Kiểm tra Service Bus application properties không bị log tràn.
- Kiểm tra dashboard exports được redact trước khi chia sẻ.

### 20.7. Kiểm thử performance

Đo trong điều kiện có và không bật tracing:
- p50/p95/p99 request latency.
- CPU/memory/GC pressure.
- Network bytes.
- Span volume và exporter queue.
- Collector memory/CPU.
- Ingestion delay.
- Sampling rate thực.
- Cost per million legitimate requests.
- Error rate và retry amplification.

Không tối ưu chi phí bằng cách cắt hết traces trước khi đã biết nguyên nhân sự cố; nên chọn spans, attrs và sampling cân bằng dựa trên dữ liệu.

## 21. Bảng troubleshooting những lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Bước kiểm tra |
|---|---|---|
| App chạy nhưng không có spans | Agent không attach/exporter chưa bật | JVM args, agent self-diagnostics |
| Spring server span không xuất hiện | Library/version không được instrument | Agent compatibility/support matrix |
| App Map chỉ có một node | Cloud Role Name chung hoặc không có | Agent role.name mỗi service |
| Orders có trace, Pricing không | Header không propagate hoặc sampling | W3C traceparent trên outbound/inbound |
| Worker tạo trace ID mới | Message context không inject/extract | Application properties và instrumentation |
| Spans không có parent | Async thread-local lost | Executor/Reactor context propagation |
| Duplicate requests/dependencies | Hai agents/exporters cùng instrument | JVM args, platform autoinstrumentation |
| Missing traces ngẫu nhiên | Sampling rate/daily cap/export errors | Agent config và ingestion metrics |
| Trace duration rất dài | Async queue lag hoặc clock skew | Queue timestamps và span parent/links |
| Dependency “SQL” không có | JDBC library không được instrument | Driver, agent support, manual span |
| 401/403 khi xem Logs | Thiếu Azure RBAC của người truy vấn | Workspace/resource roles |
| Telemetry gửi sai resource | Sai connection string | Environment/slot/revision settings |
| Java agent không start | Sai path/JDK/agent release | Startup log và manifest/provenance |
| OTLP Collector không nhận | Sai port/protocol/bind | 4317 gRPC vs 4318 HTTP |
| Collector debug có spans, Azure không | Exporter/backend route không hỗ trợ | Exporter config và compatibility |
| DNS/TLS errors tới ingestion | Egress/firewall/proxy/private route | Runtime DNS/TLS và service endpoints |
| KQL query trống | Sai workspace/table/timezone/sampling | TimeGenerated/time range/RBAC |
| OperationId khác nhau giữa services | Tracestate/traceparent bị strip/đổi | Inbound/outbound headers |
| Baggage chứa dữ liệu lạ | Client tự chèn headers | Allowlist và trust boundary |
| Logs có token/PII | Body/header capture hoặc custom attrs | Redaction and security incident |
| Ingestion chi phí tăng đột biến | Sampling giảm/duplicate spans/high-cardinality | Usage/cost, deploy diff |
| Exporter queue đầy | Backend chậm, agent/Collector capacity | Queue metrics/retries/drops |
| Trace missing sau rollout | Agent/bom/instrumentation incompatibility | Version diff và canary rollback |

## 22. Runbook xử lý distributed tracing incidents

### 22.1. Runbook A: một request timeout nhưng không thấy trace

1. Ghi **UTC timestamp, HTTP route, service, release version** và correlation ID nếu có.
2. Kiểm tra có metric/log chứng minh request đã được xử lý không.
3. Xác định Application Insights resource/workspace/region đúng.
4. Xem Java agent có attach không, có self-diagnostic lỗi không.
5. Kiểm tra sampling rate/overrides; request có thể không được chọn.
6. Kiểm tra Connection String và Azure Monitor ingestion egress.
7. Kiểm tra KQL time range/TimeGenerated và ingestion delay.
8. Tìm theo OperationId nếu có, không dùng Order ID như trace ID.
9. Nếu test ở staging, chỉnh sampling theo approval và tạo test request mới.
10. Ghi kết quả và cập nhật observability runbook; không tắt production sampling vô hạn chỉ để tìm một request.

### 22.2. Runbook B: trace bị đứt giữa Orders và Pricing

1. Chọn một trace đã được sample và có Orders CLIENT dependency.
2. Kiểm tra Pricing có SERVER request logs/counter tương ứng không.
3. Xác minh HTTP client đã được Java agent/instrumentation hỗ trợ.
4. Kiểm tra outbound traceparent/tracestate **không chứa secrets**.
5. Kiểm tra API gateway/proxy có strip hoặc rewrite headers không.
6. Kiểm tra Pricing extract và active context.
7. Xác minh Cloud Role Name/resource selection và sampling strategy.
8. Nếu có async processing, kiểm tra executor/reactive propagation.
9. Chạy integration test Orders → Pricing trong staging.
10. Kiểm tra parent IDs/correlation sau thay đổi; không tự copy trace ID bằng String field.

### 22.3. Runbook C: trùng telemetry sau deploy

1. So telemetry volume trước/sau deployment.
2. Kiểm tra App Service portal auto instrumentation.
3. Kiểm tra JVM args/JAVA_TOOL_OPTIONS có -javaagent không.
4. Kiểm tra có đồng thời Application Insights Java agent và upstream OTel agent không.
5. Kiểm tra Spring/Micrometer exporter và custom SDK providers.
6. Kiểm tra Collector có gửi một span tới nhiều exporters về cùng backend không.
7. Tắt pipeline trùng ở staging và kiểm tra count/span hierarchy.
8. Canary production rồi quan sát ingestion cost/error rate.
9. Giữ lại một chủ sở hữu instrumentation chính.
10. Document kiến trúc và chặn double agent trong CI.

### 22.4. Runbook D: exporter đột ngột thất bại

1. Xem logs/self-diagnostic của Java agent/Collector.
2. Phân loại DNS, connect, TLS, 401/403, 429, 5xx.
3. Kiểm tra Application Insights connection string/OTLP protocol.
4. Đo queue length, dropped spans, retries và CPU/memory.
5. Kiểm tra VNet/NSG/proxy/Azure Firewall/ingestion hostname.
6. Không mở outbound wildcard hoặc disable certificate validation không kiểm soát.
7. Nếu Collector bị memory pressure, tăng capacity hoặc giảm telemetry theo chính sách.
8. Kiểm tra hệ thống business vẫn đạt SLO.
9. Phục hồi/rollout có kiểm soát và xem data gaps.
10. Báo cáo data loss assumptions minh bạch; không khẳng định mọi spans sẽ tự replay.

### 22.5. Runbook E: telemetry chứa thông tin nhạy cảm

1. Chặn tiếp tục phát tán; disable offending attribute/header capture.
2. Thu hồi credentials nếu raw token/SAS bị lộ.
3. Xác định nguồn: app code, agent, Collector, HTTP logs hoặc query export.
4. Áp data classification/incident policy, ghi scope/time range.
5. Rà soát quyền xem workspace và exports.
6. Thực hiện xóa/retention/backup handling theo governance/legal requirements.
7. Sửa instrumentation và thêm redaction tests.
8. Cập nhật CI policy ngăn attrs nhạy cảm.
9. Verify bằng staging marker dữ liệu giả.
10. Ghi postmortem; đừng đưa raw token vào ticket/log khi điều tra.



## 23. Case study: truy vết đơn hàng xuyên App Service, AKS và Service Bus

### 23.1. Bài toán

Một nền tảng bán hàng chạy trên Azure:

- **API Gateway** nhận request từ frontend.
- **Orders API** chạy Spring Boot trên App Service.
- **Pricing API** chạy trên AKS.
- **Azure SQL Database** giữ đơn hàng.
- **Azure Service Bus** chứa job tạo hóa đơn.
- **Invoice Worker** chạy trên Azure Container Apps.
- **Blob Storage** lưu PDF hóa đơn.
- **Azure Monitor Application Insights** và Log Analytics giúp quan sát.

Mục tiêu:
- HTTP API đạt latency p95 nhỏ hơn 800 ms trong điều kiện tải bình thường.
- Invoice worker tạo hóa đơn trong 2 phút với queue backlog hợp lý.
- Có đủ evidence để biết dependency nào gây timeout.
- Không log payment token, JWT hoặc order/customer identifiers nhạy cảm.
- Có thể so trước/sau deployment và rollback khi p99 xấu đi.
- Có định nghĩa sampling/retention/cost không phụ thuộc một người thao tác portal.

### 23.2. Kiến trúc observability

~~~mermaid
flowchart TD
    GW["Gateway"] --> API["Orders API - App Service"]
    API --> PR["Pricing API - AKS"]
    API --> SQL["Azure SQL"]
    API --> SB["Service Bus"]
    SB --> WK["Invoice Worker - Container Apps"]
    WK --> BL["Blob Storage"]
    API -. "Java agent spans" .-> AI["Application Insights"]
    PR -. "Java agent spans" .-> AI
    WK -. "Java agent spans" .-> AI
    AI --> LA["Log Analytics / KQL / Alerts"]
    SB -. "Queue metrics" .-> MON["Azure Monitor Metrics"]
    SQL -. "DB metrics" .-> MON
    MON --> ALERT["On-call notifications"]
    LA --> ALERT
~~~

Các services có Cloud Role Names **orders-api**, **pricing-api**, **invoice-worker**, mỗi service có release version/environment. Java agent hoặc instrumentation tương thích được triển khai một lần trên mỗi JVM. Có thể chọn Application Insights resources riêng theo môi trường và dùng querying phù hợp khi cần phân tích cross-resource.

### 23.3. Một trace bình thường

Ví dụ thời gian (minh họa, không phải SLA):

~~~text
TraceId 4bf92f3577b34da6a3ce929d0e0e4736

Orders API: POST /orders/{orderId}             420 ms
 ├─ INTERNAL orders.validate                    12 ms
 ├─ CLIENT Pricing GET /quote                    210 ms
 │   └─ SERVER Pricing GET /quote                190 ms
 │       └─ INTERNAL pricing.calculate           35 ms
 ├─ CLIENT Azure SQL INSERT                     70 ms
 └─ PRODUCER Service Bus send                   45 ms

Invoice Worker: CONSUMER invoice.process         310 ms
 └─ CLIENT Blob Storage upload                  240 ms
~~~

Một queue consumer có thể xử lý **sau** khi Orders API trả response; duration 310 ms của Invoice Worker không phải thời gian nằm trong 420 ms HTTP request. Parent/link relationships và timestamp phải được đọc theo semantics của message instrumentation.

### 23.4. Một trace lỗi

Trong giờ cao điểm:
- Orders API p99 từ 700 ms tăng lên 6 giây.
- Pricing API trả 503 thoáng qua.
- HttpClient SDK retry hai lần, mỗi lần timeout khoảng 2 giây.
- Orders gateway trả 504.
- SQL latency không đổi.

Quy trình:
1. Azure Monitor Metrics alert p99 và 5xx rate.
2. Application Insights Performance/Failures tìm request chậm.
3. KQL join AppRequests/AppDependencies theo OperationId.
4. Trace waterfall cho thấy Pricing CLIENT span dài/lặp, SQL chỉ 30 ms.
5. Kiểm tra Pricing logs, AKS HPA, dependency health và network.
6. Xem retry amplification/Retry-After/circuit breaker.
7. Giới hạn retries theo total business deadline và điều chỉnh capacity nếu cần.
8. Canary release, so p95/p99, error rate, attempts và cost.
9. Viết postmortem và cập nhật runbook.

Nếu chỉ nhìn một log “SQL connection failed” xuất hiện gần cùng thời điểm, có thể tốn công tăng SQL DTUs dù lỗi chính nằm ở Pricing. Tracing giúp giữ **quan hệ nhân quả theo OperationId**, không chỉ so timestamp gần nhau.

### 23.5. Không đánh đồng trace với chứng cứ ghi nhận đơn

Sau HTTP timeout, Orders API có thể đã gửi Service Bus message thành công nhưng không nhận ACK. Người dùng retry và hệ thống tạo invoice hai lần. Trace có thể hiển thị hai sends, nhưng cách sửa **không phải xóa một span**.

Cần:
- Stable order ID và idempotency key.
- Database unique constraint/conditional write.
- Outbox hoặc transactional strategy cho DB + message dispatch.
- Message ID ổn định, worker dedup.
- Durable business audit log riêng với OTel traces.
- Reconciliation khi queue/Blob processing xảy ra chậm.

**Tracing giúp phát hiện và giải thích lỗi; nó không biến workflow thành exactly-once.**

### 23.6. Phân tách SLO

| SLO/SLI | Nguồn đo gợi ý | Điều không nên làm |
|---|---|---|
| HTTP latency p95 | Request metrics / gateway counters | Chỉ đo sampled traces |
| HTTP availability | Gateway/service metrics | Đếm không weighted failed spans |
| Background invoice lag | Service Bus age/worker processing metrics | Coi HTTP request duration bao gồm queue wait |
| Trace coverage | Sampled trace counts, propagation checks | Coi 100% trace coverage là traffic SLO |
| Dependency diagnostics | AppDependencies + spans | Cộng tất cả child durations |
| Privacy | Redaction tests/audit | Chỉ hy vọng mặc định ẩn mọi token |
| Observability cost | Azure Monitor usage/cost metrics | Giả định số spans ≈ số requests |

### 23.7. Rollout từng bước

1. Bật instrumentation cho **orders-api** ở dev.
2. Thêm role, version, environment attributes.
3. Bật **pricing-api** ở staging, test W3C HTTP context.
4. Bật **invoice-worker**, test messaging context/links.
5. Đo export drops và overhead.
6. Chuẩn hóa KQL/Workbooks/alerts và access permissions.
7. Thiết kế sampling rate/retention budgets.
8. Canary production một số instances.
9. Xem p95/p99/CPU/memory/ingestion cost.
10. Mở rộng toàn fleet và lưu runbook, owner, rollback plan.

## 24. Checklist production

### Data model và propagation

- [ ] Hiểu trace/span, trace ID, parent ID, span kinds, events và links.
- [ ] Đã xác định service.name/Cloud Role Name ổn định cho từng service.
- [ ] service.version và deployment environment có metadata.
- [ ] HTTP/gRPC outbound/inbound truyền W3C traceparent đúng.
- [ ] Reverse proxy/API gateway không loại context ngoài ý muốn.
- [ ] Service Bus/Event Hubs messages có propagation strategy.
- [ ] Async executors/Reactor context được test.
- [ ] Batches/fan-in dùng span links khi phù hợp.
- [ ] Không dùng trace ID thay business ID hoặc idempotency key.
- [ ] Root, client, producer và consumer spans có quan hệ hợp lý.

### Instrumentation và exporter

- [ ] Chọn một chiến lược instrumentation/export chính cho mỗi JVM.
- [ ] Không bật hai Java agents tự instrument cùng service.
- [ ] Java agent/SDK/OTel API versions được pin/verify.
- [ ] Agent JAR lấy từ nguồn tin cậy, kiểm tra checksum.
- [ ] Auto instrumentation HTTP/JDBC/SDK được xác minh theo version.
- [ ] Manual spans chỉ thêm cho business steps có ích.
- [ ] Mọi manual span đều được end trong finally.
- [ ] Exceptions/status được ghi có chủ đích, không làm sai business flow.
- [ ] App Service platform auto-instrumentation được kiểm tra trước khi attach agent.
- [ ] Azure Monitor ingestion và OTLP Collector pipeline không bị nhầm lẫn.
- [ ] Collector receiver có TLS/auth/private access khi dùng ngoài localhost.
- [ ] Có telemetry export drops/retries/queue metrics và runbook.

### Sampling và data protection

- [ ] Sampling mode/rate được xác định và test.
- [ ] Parent-based consistency và downstream behavior được kiểm tra.
- [ ] Hiểu missing trace có thể do sampling, không nhất thiết lỗi request.
- [ ] Không dùng sampled traces duy nhất để ước lượng error rate.
- [ ] Logs/metrics/traces retention theo chính sách.
- [ ] Không ghi Authorization, SAS, secrets, raw request body vào spans.
- [ ] W3C baggage được allowlist và giới hạn kích thước.
- [ ] Không tin traceparent/baggage làm authentication.
- [ ] Không dùng raw user/order IDs làm span names/metric labels.
- [ ] Có negative tests chứng minh PII không rò rỉ.
- [ ] Log Analytics/Application Insights access theo least privilege.
- [ ] Có policy xử lý telemetry incident chứa secret.

### Reliability, cost và operations

- [ ] Có SLI/SLO rõ cho HTTP và background workflows.
- [ ] Monitoring p95/p99/error rate có nguồn đo phù hợp.
- [ ] Có dashboards Application Map, Failures, Performance, KQL.
- [ ] KQL truy vấn được OperationId qua AppRequests/AppDependencies.
- [ ] Có alerts cho exporter failures và Collector saturation.
- [ ] App business vẫn chạy khi telemetry backend tạm mất, theo thiết kế.
- [ ] Đo CPU/memory/network overhead của agent/Collector.
- [ ] Đặt budget, retention, sampling và daily cap policy.
- [ ] Không có duplicate telemetry sau rollout.
- [ ] Có owner/on-call và runbooks missing traces, 429, DNS/TLS, privacy.
- [ ] Có fault-injection tests và canary.
- [ ] Có rollback plan khi agent upgrade tăng latency/cost.
- [ ] Có evidence version/metrics trước-sau release.

## 25. Câu hỏi tự kiểm tra

1. **Distributed tracing giải quyết vấn đề gì?** Theo dõi quan hệ nhân quả của một hoạt động xuyên nhiều services.
2. **Metrics khác traces ở đâu?** Metrics đo xu hướng/tổng hợp, traces diễn giải đường đi một hoạt động.
3. **Logs có thay thế traces hoàn toàn được không?** Không, nếu thiếu span/parent context và timing.
4. **Trace ID dài bao nhiêu?** Thường 128-bit theo W3C, biểu diễn 32 hex.
5. **Span ID dài bao nhiêu?** Thường 64-bit, biểu diễn 16 hex.
6. **Span chứa những gì?** Name, IDs, kind, start/end, attributes, events, status và links.
7. **SERVER span nghĩa gì?** Nhận request từ remote caller.
8. **CLIENT span nghĩa gì?** Gọi remote dependency.
9. **PRODUCER/CONSUMER dùng khi nào?** Gửi/nhận message.
10. **INTERNAL span dùng cho gì?** Công việc bên trong một tiến trình.
11. **Span link khác parent như thế nào?** Có thể tham chiếu nhiều contexts mà không tạo quan hệ cha-con duy nhất.
12. **W3C traceparent chứa gì?** Version, trace ID, parent span ID và trace flags.
13. **Header sampled=1 có là bằng chứng request đã xác thực không?** Không.
14. **tracestate dùng làm gì?** Thông tin bổ sung của tracing implementations.
15. **Baggage có nên chứa token/user email không?** Không.
16. **Inject context nghĩa là gì?** Gắn trace context vào outbound carrier.
17. **Extract context nghĩa là gì?** Đọc remote context trước khi tạo span ở receiver.
18. **Nếu gateway bỏ traceparent thì sao?** Downstream có thể tạo trace root mới.
19. **service.name nên đặt thế nào?** Ổn định theo logic service, không theo mỗi request/Pod.
20. **Cloud Role Name cần gì?** Phân biệt services trên Application Map.
21. **OpenTelemetry API có tự xuất dữ liệu không?** Không nếu chưa có SDK/exporter/agent.
22. **Auto instrumentation khác manual?** Auto instrument framework calls; manual bổ sung business spans.
23. **Vì sao không chạy hai Java agents cùng lúc?** Có thể tạo duplicate spans và hỏng context.
24. **Java agent dùng cờ JVM nào?** -javaagent trước -jar.
25. **Connection string Application Insights dùng làm gì?** Xác định đích export telemetry.
26. **Connection string có cấp quyền đọc mọi Log Analytics data không?** Không.
27. **Java Azure Monitor agent sampling mặc định trong dòng mới?** Rate-limited, khoảng 5 requests/s theo tài liệu.
28. **Không thấy một request trong traces chứng minh nó không chạy không?** Không, có thể sampling/export/drop.
29. **Head sampling quyết định khi nào?** Khi bắt đầu trace/request.
30. **Tail sampling quyết định khi nào?** Sau khi quan sát thêm spans/đặc điểm cuối trace.
31. **Tail sampling có hạn chế gì?** Memory buffering, routing, trace lateness và data loss.
32. **Parent-based sampling có lợi gì?** Giữ quyết định sampled nhất quán trong trace.
33. **AppRequests chứa loại dữ liệu gì?** Server/request telemetry.
34. **AppDependencies chứa gì?** Remote dependencies và nhiều custom spans theo mapping.
35. **AppTraces có phải bảng chứa mọi span không?** Không, thường chứa log/tracing messages.
36. **OperationId dùng để làm gì?** Tương quan các telemetry items trong một distributed operation.
37. **ItemCount giúp gì với sampling?** Ước lượng volume represented trong Application Insights khi áp dụng.
38. **KQL join theo OperationId có thể tạo nhiều rows không?** Có, vì một request có nhiều dependencies.
39. **Vì sao không cộng mọi child durations?** Các operations có thể song song hoặc lồng nhau.
40. **Trace ID và order ID có giống nhau không?** Không.
41. **Context mất qua async executor vì sao?** Thread-local không tự truyền sang thread khác nếu thiếu instrumentation.
42. **Muốn propagate qua Service Bus cần gì?** Context injection/extraction trong message metadata hoặc SDK hỗ trợ.
43. **Một message retry có thể sinh nhiều consumer spans không?** Có.
44. **Collector debug exporter có gửi Application Insights không?** Không.
45. **OTLP HTTP thường dùng cổng nào?** 4318, cần endpoint/protocol phù hợp.
46. **OTLP gRPC thường dùng cổng nào?** 4317.
47. **App Insights ingestion URL có tự là OTLP receiver không?** Không.
48. **Java agent auto instrumentation có hỗ trợ mọi library không?** Không, cần kiểm tra support/version.
49. **Không nên ghi gì vào span attributes?** Token, PII, raw SQL params, secrets.
50. **Khi production thiếu spans, kiểm tra gì?** Agent, configuration, sampling, network, exporter, role/workspace, propagation.
51. **Khi trace bị chia thành hai, kiểm tra gì?** traceparent, gateway, async/message context và sampling.
52. **Khi telemetry tăng gấp đôi sau deploy, kiểm tra gì?** Double agents/exporters/instrumentation.
53. **Tracing có bảo đảm exactly-once cho Service Bus không?** Không.
54. **Điều gì quyết định tracing production an toàn?** Sampling, propagation, privacy, least privilege, monitoring, fault tests, budgets và runbooks.
55. **Traces có thể làm nguồn duy nhất cho audit giao dịch không?** Không, vì sampling/exporter loss và retention.
56. **SLO HTTP và SLO queue worker giống nhau không?** Không, cần tách latency và queue processing.
57. **Latency overhead của OTel cần đo ở đâu?** p95/p99/CPU/memory trước-sau instrument.
58. **Vì sao không lấy trace ID làm metric label?** Cardinality quá cao và tăng chi phí.
59. **Nếu App Map gộp nhiều services thành một node, kiểm tra gì?** Cloud Role Name/resource settings.
60. **Khi exporter lỗi, ứng dụng phải làm gì?** Theo thiết kế giữ business SLO, bounded buffering/retry và báo telemetry drops.

## 26. Tài liệu tham khảo

Tra cứu các nguồn chính thức sau theo **phiên bản Azure Monitor Java agent, OpenTelemetry SDK và service client thực tế** trước khi áp dụng production:

- [OpenTelemetry specification](https://opentelemetry.io/docs/specs/otel/) — data model, context, API/SDK, semantic conventions.
- [OpenTelemetry concepts: traces](https://opentelemetry.io/docs/concepts/signals/traces/) — trace/span relationships, events/status.
- [OpenTelemetry context propagation](https://opentelemetry.io/docs/concepts/context-propagation/) — inject/extract context.
- [OpenTelemetry Java documentation](https://opentelemetry.io/docs/languages/java/) — instrumentation, SDK, Java agent.
- [OpenTelemetry Java agent](https://opentelemetry.io/docs/zero-code/java/agent/) — zero-code instrumentation và cấu hình.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/) — traceparent/tracestate wire format.
- [W3C Baggage](https://www.w3.org/TR/baggage/) — baggage propagation, limits và privacy.
- [OpenTelemetry Collector](https://opentelemetry.io/docs/collector/) — receivers, processors, exporters, vận hành.
- [OTLP specification](https://opentelemetry.io/docs/specs/otlp/) — gRPC/HTTP telemetry protocol.
- [Azure Monitor Application Insights overview](https://learn.microsoft.com/en-us/azure/azure-monitor/app/app-insights-overview) — APM và quan sát ứng dụng trên Azure.
- [Enable OpenTelemetry in Application Insights](https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-enable?tabs=java) — Java agent và connection string.
- [Using Application Insights with Spring Boot](https://learn.microsoft.com/en-us/azure/azure-monitor/app/java-spring-boot) — JVM agent và Spring Boot.
- [Azure Monitor OpenTelemetry configuration](https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-configuration?tabs=java) — sampling, role, Java defaults.
- [Azure Monitor OpenTelemetry sampling](https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-sampling) — sampler và trace completeness.
- [Azure Monitor Java agent configuration](https://learn.microsoft.com/en-us/azure/azure-monitor/app/java-standalone-config) — role.name, configuration file, sampling và diagnostics.
- [Add custom OpenTelemetry spans in Application Insights](https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-add-modify?tabs=java) — OpenTelemetry API, @WithSpan, attributes, logs.
- [Application Insights dependencies](https://learn.microsoft.com/en-us/azure/azure-monitor/app/dependencies) — dependency tracking.
- [Application Insights Java on Azure App Service](https://learn.microsoft.com/en-us/azure/azure-monitor/app/azure-web-apps?tabs=java) — platform auto-instrumentation.
- [AppRequests table schema](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/apprequests) — OperationId, DurationMs, sampling fields.
- [AppDependencies table schema](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/appdependencies) — dependency query columns.
- [AppRequests example KQL queries](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/queries/apprequests) — latency, failures, requests count.
- [Azure Monitor Logs KQL](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/log-query-overview) — truy vấn, permissions.
- [Azure Monitor costs and usage](https://learn.microsoft.com/en-us/azure/azure-monitor/cost-usage) — ingestion, retention và chi phí.
- [Azure Well-Architected operational excellence](https://learn.microsoft.com/en-us/azure/well-architected/operational-excellence/) — monitoring, observability, incident response.
- [Azure Service Bus messaging documentation](https://learn.microsoft.com/en-us/azure/service-bus-messaging/) — async delivery và ứng dụng messaging.
- [Azure Cost Management](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/) — budgets và cost allocation.

**Kết luận:** OpenTelemetry cung cấp **mô hình tiêu chuẩn cho traces, spans, context propagation và exporters**; distributed tracing giúp liên kết một business operation qua App Service, AKS, Functions, Azure SDK, SQL và Service Bus. Trên Azure, **Application Insights Java agent** là con đường thực tế để instrument nhanh JVM workloads và truy vấn bằng **Application Map, End-to-end transaction details, AppRequests/AppDependencies/KQL**. Một kiến trúc đáng tin còn phải xử lý **W3C propagation, async messages, span parents/links, sampling và data completeness, authorization, redaction, exporter failures, overhead, retention, chi phí và SLO**. Tracing giúp tìm nguyên nhân sự cố, nhưng không thay business idempotency, metrics hay audit logs; hãy thử nghiệm end-to-end trên staging, triển khai canary và có runbook trước khi phụ thuộc vào nó trong production.

