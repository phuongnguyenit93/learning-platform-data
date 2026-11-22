# Cloud Observability và thiết kế telemetry cho workload

Trong module `CLOUD_PROVIDERS_GCP`, bạn khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Các tình huống triển khai giúp bạn lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Chương **Cloud Observability** đưa những năng lực vận hành đó vào một quy trình thống nhất: tạo telemetry từ workload, thu thập và lưu trữ dữ liệu, phát hiện dấu hiệu suy giảm, rồi lần theo nguyên nhân ở đúng thành phần.

Bài học này hướng dẫn cách thiết kế telemetry cho ứng dụng chạy trên Google Cloud. Bạn sẽ phân biệt metrics, logs và traces; dùng OpenTelemetry để chuẩn hóa instrumentation; chọn cách thu thập phù hợp với Compute Engine, GKE và Cloud Run; sau đó xây dashboard, SLI/SLO và cảnh báo có thể hành động.

## 1. Observability là gì và giúp giải quyết vấn đề nào?

Observability (khả năng quan sát) là khả năng suy ra trạng thái bên trong của một hệ thống từ dữ liệu mà hệ thống phát ra. Monitoring thường tập trung theo dõi các chỉ số và điều kiện đã biết, chẳng hạn CPU vượt 90% hoặc tỷ lệ lỗi tăng. Observability còn giúp điều tra những tình huống chưa được dự đoán trước bằng cách kết hợp nhiều tín hiệu, theo dõi một request xuyên qua các dịch vụ và đặt câu hỏi mới trên dữ liệu đã thu thập.

Telemetry là dữ liệu được tạo ra trong quá trình ứng dụng và hạ tầng hoạt động. Ba nhóm tín hiệu phổ biến nhất là metrics, logs và traces:

| Tín hiệu | Mô tả | Trả lời câu hỏi |
| --- | --- | --- |
| **Metrics** | Dữ liệu số được tổng hợp theo thời gian, thường có tên metric, nhãn, timestamp và giá trị. | Hệ thống đang khỏe đến đâu? Xu hướng có thay đổi không? |
| **Logs** | Các bản ghi sự kiện có timestamp và nội dung chi tiết. | Điều gì đã xảy ra tại một thời điểm cụ thể? |
| **Traces** | Đường đi của một request qua các thành phần; mỗi trace gồm nhiều span đại diện cho một thao tác. | Request đã đi qua đâu và thời gian bị tiêu tốn ở thành phần nào? |

Ba tín hiệu bổ sung cho nhau. Metric cho thấy tỷ lệ lỗi của dịch vụ tăng từ 0,2% lên 8%; trace cho biết phần lớn thời gian chờ nằm ở lời gọi cơ sở dữ liệu; log của span tương ứng cung cấp mã lỗi hoặc thông tin nghiệp vụ để xác định nguyên nhân. Chỉ có một tín hiệu thường chưa đủ để kết luận.

Ngoài ba tín hiệu trên, **profiling** giúp đo mức tiêu thụ CPU và bộ nhớ theo hàm hoặc đoạn mã. Error Reporting gom nhóm lỗi ứng dụng để người vận hành theo dõi các lỗi lặp lại. Đây là những công cụ bổ trợ cho quá trình tìm nguyên nhân.

### 1.1. Những câu hỏi cần trả lời khi thiết kế

Bắt đầu từ cách người dùng trải nghiệm dịch vụ, sau đó mới chọn dữ liệu cần thu thập:

- Người dùng có gọi được chức năng quan trọng không?
- Request mất bao lâu ở mức trung vị và ở đuôi phân phối (p95, p99)?
- Tỷ lệ request lỗi, retry hoặc timeout đang thay đổi thế nào?
- Dịch vụ có đang cạn CPU, bộ nhớ, connection pool, worker hoặc dung lượng hàng đợi không?
- Khi một dịch vụ chậm, thành phần phụ thuộc nào đang gây ra độ trễ?
- Phiên bản mới có làm tăng lỗi, độ trễ hoặc chi phí trên mỗi request không?

Với dịch vụ HTTP, bốn tín hiệu vàng thường dùng là **latency, traffic, errors và saturation**. Với worker xử lý nền, cần bổ sung queue depth, tuổi của message lâu nhất, consumer lag, retry và dead-letter count. Với cơ sở dữ liệu, có thể theo dõi connection pool, transaction latency, lock wait, số kết nối và dung lượng lưu trữ.

## 2. Thiết kế telemetry cho workload

Một thiết kế tốt bắt đầu từ một hợp đồng telemetry thống nhất. Hợp đồng này quy định tên dịch vụ, môi trường, phiên bản, tài nguyên, định dạng log, tên metric, thuộc tính span và cách truyền trace context giữa các thành phần.

### 2.1. Xác định danh tính của dịch vụ

Mỗi tín hiệu cần mô tả rõ nó đến từ dịch vụ và phiên bản nào. Với OpenTelemetry, các resource attributes thường hữu ích gồm:

| Thuộc tính | Ví dụ | Mục đích |
| --- | --- | --- |
| `service.name` | `orders-api` | Tên ổn định của dịch vụ. |
| `service.namespace` | `commerce` | Nhóm hoặc miền nghiệp vụ chứa dịch vụ. |
| `service.version` | `2026.11.19-4f2a1c` | Phân biệt các bản phát hành. |
| `deployment.environment.name` | `production` | Phân biệt production, staging và development. |
| `cloud.region` | `asia-southeast1` | Xác định khu vực triển khai. |
| `k8s.namespace.name` | `commerce-prod` | Xác định namespace trên Kubernetes. |
| `k8s.deployment.name` | `orders-api` | Xác định workload Kubernetes. |
| `host.name` | `orders-vm-01` | Xác định máy chủ khi chạy trên VM. |

Hãy dùng cùng một cách viết cho tên service, environment và version ở metrics, logs và traces. Khi cần so sánh phiên bản cũ với phiên bản mới, bạn có thể lọc cùng một dashboard theo `service.version`.

Không đưa thông tin thay đổi theo từng request vào resource attributes. Resource mô tả nơi phát sinh telemetry; các giá trị như request ID hoặc trace ID thuộc về từng log entry hoặc span.

### 2.2. Chọn metric phản ánh sức khỏe dịch vụ

Metric nên đo điều người dùng hoặc hệ thống phụ thuộc thực sự quan tâm. Một bộ metric cơ bản cho API có thể gồm:

| Metric | Kiểu dữ liệu phù hợp | Cách sử dụng |
| --- | --- | --- |
| Tổng request | Counter | Đo lưu lượng và tính tỷ lệ lỗi. |
| Request thành công/thất bại | Counter hoặc phân loại theo mã kết quả | Theo dõi availability và lỗi theo endpoint hoặc nhóm nghiệp vụ. |
| Thời gian xử lý request | Histogram | Tính p50, p95, p99 và xây latency SLI. |
| Request đang xử lý | Gauge | Phát hiện tải đồng thời tăng bất thường. |
| CPU và memory | Gauge | Theo dõi mức sử dụng tài nguyên. |
| Queue depth và oldest message age | Gauge | Phát hiện worker không theo kịp tốc độ phát sinh công việc. |
| Retry và dead-letter count | Counter | Phát hiện lỗi phụ thuộc hoặc message không xử lý được. |
| Connection pool đang dùng/còn trống | Gauge | Phát hiện nguy cơ cạn kết nối. |

Với metric dạng counter, giá trị thường tăng dần; hệ thống truy vấn sẽ tính tốc độ tăng trong một khoảng thời gian. Histogram giữ phân phối quan sát, phù hợp hơn giá trị trung bình khi cần đánh giá độ trễ đuôi. Gauge biểu diễn giá trị tại thời điểm đo, chẳng hạn số message đang chờ.

Đừng chỉ theo dõi CPU và memory. Một dịch vụ có thể dùng CPU thấp nhưng vẫn không phục vụ được request vì chờ cơ sở dữ liệu, hết connection pool hoặc bị giới hạn concurrency. Hãy đặt metric ở các điểm mà người dùng cảm nhận được chất lượng dịch vụ và tại những tài nguyên có thể trở thành nút thắt.

### 2.3. Ghi log có cấu trúc

Dùng log có cấu trúc JSON thay cho chuỗi văn bản khó phân tích. Mỗi entry nên có timestamp, severity, message, tên dịch vụ, environment, version và các thuộc tính liên quan đến request. Ghi một sự kiện trên một entry để Cloud Logging có thể lọc theo field.

Ví dụ một log JSON có liên kết trace:

~~~json
{
  "severity": "ERROR",
  "message": "Payment authorization timed out",
  "service": "checkout-api",
  "environment": "production",
  "service_version": "2026.11.19",
  "request_id": "req-7f13",
  "logging.googleapis.com/trace": "projects/PROJECT_ID/traces/TRACE_ID",
  "logging.googleapis.com/spanId": "SPAN_ID",
  "logging.googleapis.com/trace_sampled": true,
  "http": {
    "request_method": "POST",
    "status_code": 504
  },
  "dependency": "payment-provider"
}
~~~

Các field đặc biệt `logging.googleapis.com/trace`, `logging.googleapis.com/spanId` và `logging.googleapis.com/trace_sampled` cho phép Cloud Logging liên kết log entry với trace và span tương ứng. Nếu dùng Logging client library hoặc OpenTelemetry context, thư viện có thể điền thông tin liên kết tự động.

Một log tốt mô tả sự kiện có ý nghĩa: request timeout, retry vượt ngưỡng, circuit breaker chuyển trạng thái, không kết nối được database hoặc một giao dịch bị từ chối. Tránh ghi toàn bộ request/response body chỉ để tiện debug. Không ghi access token, mật khẩu, khóa bí mật, cookie, thông tin thanh toán hoặc dữ liệu cá nhân không cần thiết. Nếu phải ghi một định danh nghiệp vụ, dùng ID đã được kiểm soát và giới hạn quyền đọc log.

### 2.4. Tạo trace xuyên suốt request

Một trace biểu diễn toàn bộ hành trình của một request. Span gốc đại diện cho request vào; các span con có thể đại diện cho truy vấn database, lời gọi HTTP đến dịch vụ khác, thao tác cache hoặc xử lý message.

Ví dụ một luồng checkout:

~~~text
checkout-api (root span)
  ├── validate-cart
  ├── inventory-api
  │     └── inventory-db-query
  ├── payment-api
  │     └── payment-provider-request
  └── publish-order-event
        └── orders-worker (consumer span)
~~~

Mỗi span nên có tên thao tác ngắn, thời gian bắt đầu/kết thúc, trạng thái và các thuộc tính cần thiết để phân tích. Không đặt tên span chứa ID duy nhất của người dùng hoặc request; tên span có cardinality cao làm dữ liệu khó nhóm và khó phân tích.

Để trace không bị đứt đoạn ở ranh giới dịch vụ, ứng dụng cần truyền trace context qua HTTP header hoặc metadata của message. OpenTelemetry hỗ trợ propagator theo chuẩn W3C Trace Context; header phổ biến là `traceparent`. Khi một dịch vụ gọi dịch vụ khác, span mới phải giữ cùng trace ID và tham chiếu parent span thích hợp. Với xử lý bất đồng bộ qua Pub/Sub hoặc hàng đợi, hãy đưa context vào metadata của message và khôi phục context ở consumer nếu thư viện hoặc nền tảng không tự thực hiện việc đó.

Không phải dịch vụ Google Cloud nào cũng khởi tạo hoặc truyền trace context theo cùng cách. Hãy xác minh khả năng của từng thành phần trên đường đi. Cloud Trace lưu và hiển thị trace; việc truyền context là trách nhiệm của ứng dụng, thư viện instrumentation hoặc dịch vụ trung gian.

## 3. OpenTelemetry và kiến trúc thu thập telemetry

OpenTelemetry (OTel) là bộ API, SDK, thư viện instrumentation và công cụ thu thập mã nguồn mở, trung lập với nhà cung cấp. Nó giúp ứng dụng phát ra metrics, logs và traces theo mô hình nhất quán. OTLP (OpenTelemetry Protocol) là giao thức truyền telemetry giữa ứng dụng, collector và backend.

### 3.1. Các thành phần trong pipeline

Một pipeline OTel thường có các thành phần:

- **Instrumentation:** thư viện hoặc agent tạo telemetry từ framework, HTTP client, database client và đoạn mã nghiệp vụ.
- **SDK:** quản lý provider, processor, sampler và exporter trong tiến trình ứng dụng.
- **Exporter:** chuyển tín hiệu từ SDK đến một đích nhận, thường qua OTLP.
- **Collector:** tiến trình nhận, xử lý và chuyển tiếp telemetry. Collector có thể nhận từ nhiều workload và xuất đến một hoặc nhiều backend.
- **Backend:** nơi lưu trữ, truy vấn, hiển thị và cảnh báo, ví dụ Cloud Logging, Cloud Monitoring và Cloud Trace.

Collector có thể thực hiện batching, thêm resource attributes, lọc dữ liệu, giới hạn bộ nhớ, chuyển đổi định dạng hoặc định tuyến đến nhiều backend. Cấu hình collector cần có receiver, processor, exporter và service pipeline tương ứng với từng tín hiệu.

Sơ đồ tổng quát của một pipeline telemetry:

~~~mermaid
flowchart LR
  subgraph W[Workload]
    APP[Application + OpenTelemetry SDK]
    LOG[Structured logs stdout/stderr]
  end
  APP -->|OTLP| COL[Collector / Agent / Sidecar]
  LOG --> CL[Cloud Logging]
  COL --> CL
  COL --> CM[Cloud Monitoring]
  COL --> CT[Cloud Trace]
  CL --> ER[Error Reporting]
  CL --> VIEW[Dashboards and alerting]
  CM --> VIEW
  CT --> VIEW
  CP[Cloud Profiler] --> VIEW
~~~

### 3.2. Hai cách gửi telemetry lên Google Cloud

| Cách gửi | Luồng dữ liệu | Khi nên dùng |
| --- | --- | --- |
| Collector-based export | Ứng dụng OTel SDK → OTLP → OTel Collector → Google Cloud | Môi trường có thể chạy collector; cần lọc, xử lý tập trung, quản lý retry và giữ mã ứng dụng trung lập với backend. |
| Direct export | Ứng dụng OTel SDK → Telemetry API | Môi trường không thuận tiện chạy tiến trình collector riêng hoặc workload nhỏ cần cấu hình đơn giản. |

Google khuyến nghị dùng collector khi môi trường triển khai hỗ trợ. Nếu collector không phù hợp, có thể export trực tiếp từ tiến trình ứng dụng. Dùng OTLP giúp ứng dụng giữ instrumentation trung lập hơn; khi đổi backend, bạn có thể thay cấu hình collector hoặc exporter mà không phải viết lại toàn bộ logic đo lường.

### 3.3. Cấu hình OpenTelemetry bằng biến môi trường

Các biến môi trường chuẩn của OpenTelemetry giúp triển khai cùng một cách cấu hình cho nhiều ngôn ngữ. Ví dụ minh họa:

~~~bash
OTEL_SERVICE_NAME=orders-api
OTEL_RESOURCE_ATTRIBUTES=service.namespace=commerce,deployment.environment.name=production,service.version=2026.11.19
OTEL_EXPORTER_OTLP_ENDPOINT=http://OTEL_COLLECTOR_HOST:4318
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_PROPAGATORS=tracecontext,baggage
~~~

Thay `OTEL_COLLECTOR_HOST` bằng endpoint thực tế của collector. SDK cần được khởi tạo và instrumentation của framework cần được bật; chỉ đặt biến môi trường không tự động tạo ra mọi span nghiệp vụ. Hãy xác minh exporter, giao thức và endpoint được hỗ trợ bởi SDK đang dùng. Nếu collector yêu cầu xác thực hoặc TLS, cấu hình thông tin xác thực theo hướng dẫn của môi trường.

Với ứng dụng Java, có thể bắt đầu bằng OpenTelemetry Java agent để tự động instrument các framework phổ biến, sau đó bổ sung span thủ công ở những bước nghiệp vụ quan trọng. Với các ngôn ngữ khác, chọn SDK/agent tương ứng và kiểm tra danh sách thư viện đã được instrument tự động. Tránh tạo span thủ công cho mọi hàm nhỏ; hãy tập trung vào ranh giới dịch vụ, lời gọi phụ thuộc và các bước nghiệp vụ có ý nghĩa.

## 4. Chọn cách thu thập theo nền tảng Google Cloud

Mỗi nền tảng có cách chạy agent, sidecar và tiến trình nền khác nhau. Hãy chọn pipeline dựa trên vòng đời workload, loại tín hiệu và mức độ kiểm soát cần có.

### 4.1. Compute Engine

Trên VM, **Ops Agent** là lựa chọn chính để thu thập log và metric hệ điều hành, cùng telemetry từ ứng dụng và phần mềm bên thứ ba theo receiver đã cấu hình. Với ứng dụng cần distributed tracing hoặc custom metrics, instrument bằng OpenTelemetry SDK và gửi OTLP đến receiver của Ops Agent hoặc collector phù hợp.

Một cách triển khai thường dùng:

1. Cài Ops Agent trên VM bằng chính sách quản lý hoặc công cụ tự động hóa.
2. Cấu hình ứng dụng ghi log JSON vào file mà agent có thể đọc.
3. Dùng OpenTelemetry SDK để tạo metric và trace cho các request và dependency.
4. Cấu hình OTLP receiver trên agent/collector và cấp quyền ghi telemetry vào project.
5. Kiểm tra metric VM trong Cloud Monitoring, log trong Logs Explorer và trace trong Cloud Trace.

Nếu chỉ cần Prometheus-format metrics, Ops Agent có Prometheus receiver để scrape endpoint của ứng dụng hoặc exporter. Tránh cài nhiều agent trùng chức năng trên cùng VM vì có thể thu thập lặp, tăng tài nguyên và khó xác định nguồn dữ liệu.

### 4.2. Google Kubernetes Engine (GKE)

GKE tự thu thập log ứng dụng ghi ra `stdout` và `stderr`; vì vậy, hãy ưu tiên log JSON theo từng dòng. Với metric Prometheus, Google Cloud Managed Service for Prometheus cung cấp nơi lưu trữ và truy vấn metric tương thích PromQL. Managed collection giúp giảm công việc vận hành Prometheus collector, bao gồm triển khai, mở rộng và cấu hình shard.

Nếu ứng dụng đã dùng OpenTelemetry, bạn có thể triển khai **Managed OpenTelemetry for GKE**. Tính năng này cung cấp collector trong cluster để nhận OTLP traces, metrics và logs; workload vẫn cần được instrument và cấu hình gửi telemetry đến endpoint. Endpoint OTLP HTTP và gRPC mặc định được tài liệu GKE mô tả như sau:

~~~text
OTLP/HTTP: http://opentelemetry-collector.gke-managed-otel.svc.cluster.local:4318
OTLP/gRPC: http://opentelemetry-collector.gke-managed-otel.svc.cluster.local:4317
~~~

Managed OpenTelemetry for GKE có thể dùng tài nguyên `Instrumentation` để cấu hình tự động cho workload tương thích. Nếu cần lọc, biến đổi hoặc định tuyến telemetry theo quy tắc riêng, cân nhắc Google-Built OpenTelemetry Collector. Với metrics Prometheus, chọn Managed Service for Prometheus và cách thu thập phù hợp với exporter hiện có.

Trong GKE, cần gắn resource attributes như cluster, namespace, workload và container để phân biệt dữ liệu giữa các môi trường. Khi một Pod bị thay thế, service identity và version vẫn phải giúp người vận hành nhận diện workload đang phát telemetry.

### 4.3. Cloud Run

Cloud Run tự thu thập log container ghi ra `stdout` và `stderr`. Dịch vụ cũng tạo trace cho độ trễ của request HTTP vào/ra. Nếu cần trace chi tiết bên trong ứng dụng, hãy instrument bằng OpenTelemetry để tạo custom span và truyền context đến dịch vụ downstream.

Đối với telemetry tùy chỉnh:

- Dùng OpenTelemetry SDK và OpenTelemetry sidecar để thu thập OTLP metrics và traces.
- Nếu ứng dụng phát metric theo định dạng Prometheus, dùng Prometheus sidecar dành cho Cloud Run.
- Nếu collector chạy nền để export telemetry, kiểm tra chế độ CPU allocation và cấu hình instance-based billing theo hướng dẫn Cloud Run; tiến trình nền cần CPU để tiếp tục xử lý sau khi request kết thúc.
- Kiểm tra chi phí ingest log, metric và trace khi tăng số instance hoặc sampling rate.

Với Cloud Run functions, cách thu thập có một số khác biệt: log `stdout`/`stderr` được thu thập tự động; có thể dùng log-based metrics khi cần metric tùy chỉnh vì ghi metric trực tiếp không được hỗ trợ theo hướng dẫn instrumentation hiện hành cho Cloud Run functions.

### 4.4. Bảng chọn nhanh

| Môi trường | Log | Metrics | Traces |
| --- | --- | --- | --- |
| Compute Engine | JSON file + Ops Agent | Ops Agent, Prometheus receiver hoặc OTel | OTel SDK → OTLP receiver của Ops Agent/collector |
| GKE | JSON `stdout`/`stderr` được nền tảng thu thập | Managed Service for Prometheus hoặc OTel Collector | Managed OpenTelemetry for GKE hoặc Google-Built OTel Collector |
| Cloud Run | JSON `stdout`/`stderr` được nền tảng thu thập | OTel sidecar hoặc Prometheus sidecar | Trace HTTP nền tảng và OTel custom spans/sidecar |

Đây là các hướng triển khai thường gặp, không phải danh sách giới hạn. Hãy kiểm tra khả năng của runtime, SDK, phiên bản agent và loại tín hiệu trước khi chốt kiến trúc.

## 5. Sử dụng các dịch vụ Google Cloud Observability

Google Cloud cung cấp các dịch vụ được tích hợp để lưu trữ, truy vấn, hiển thị và cảnh báo trên telemetry.

| Dịch vụ | Vai trò | Công cụ thường dùng |
| --- | --- | --- |
| **Cloud Logging** | Thu thập, lưu trữ, truy vấn và phân tích log; hỗ trợ log-based metrics, log-based alerts và log routing. | Logs Explorer, Log Analytics, log buckets, sinks. |
| **Cloud Monitoring** | Thu thập và truy vấn metric; theo dõi tài nguyên, tạo dashboard và alert. | Metrics Explorer, dashboards, alerting policies, uptime checks. |
| **Cloud Trace** | Hiển thị trace và phân tích độ trễ theo từng span trong request phân tán. | Trace Explorer, trace waterfall, trace scope. |
| **Error Reporting** | Phát hiện và gom nhóm lỗi từ log để theo dõi tần suất và lịch sử lỗi. | Error groups và danh sách lỗi trong Console. |
| **Cloud Profiler** | Thu thập profile CPU và phân bổ bộ nhớ với overhead thấp để tìm đoạn mã tiêu thụ tài nguyên. | Profile theo thời gian và flame graph. |
| **Managed Service for Prometheus** | Thu thập, lưu trữ và truy vấn metric theo mô hình Prometheus. | PromQL, exporters, managed collection. |

### 5.1. Cloud Logging

Cloud Logging tự động thu thập log từ nhiều tài nguyên Google Cloud; ứng dụng, hệ thống tại chỗ và môi trường cloud khác cũng có thể gửi log vào project. Dùng Logs Explorer để lọc theo resource, severity, service, timestamp và các field JSON.

Ví dụ truy vấn log lỗi của Cloud Run:

~~~text
resource.type="cloud_run_revision"
severity>=ERROR
resource.labels.service_name="checkout-api"
~~~

Ví dụ tìm log có thông tin một request:

~~~text
resource.type="cloud_run_revision"
jsonPayload.request_id="req-7f13"
~~~

Thay resource type và field theo nền tảng, schema log thực tế. Với log có cấu trúc, dùng field cụ thể để lọc thay vì tìm chuỗi tự do trong toàn bộ payload.

Log sink định tuyến log đến log bucket khác, project giám sát tập trung, BigQuery, Cloud Storage hoặc Pub/Sub tùy mục tiêu. Trước khi tạo sink, xác định log nào cần lưu dài hạn, ai được quyền đọc, retention bao lâu và đích nhận có quyền truy cập phù hợp không.

### 5.2. Cloud Monitoring

Cloud Monitoring lưu trữ time series và cung cấp Metrics Explorer, dashboard, alerting policy, uptime check và SLO monitoring. Dùng dashboard để đặt các chỉ số có liên quan cạnh nhau, chẳng hạn request rate, error rate, p95 latency, CPU, memory và queue depth.

Metric-based alert phù hợp với xu hướng số liệu và điều kiện kéo dài. Log-based alert phù hợp với một sự kiện quan trọng xuất hiện trong log, chẳng hạn circuit breaker mở hoặc một tác vụ khôi phục thất bại. SQL-based alert phù hợp với mẫu phức tạp cần tổng hợp nhiều log entry. Chọn loại alert theo câu hỏi vận hành; mỗi alert cần có chủ sở hữu, mức độ nghiêm trọng, hành động tiếp theo và liên kết runbook.

### 5.3. Cloud Trace và tương quan log-trace

Trace Explorer hiển thị trace theo dạng waterfall, giúp xác định span chậm và dependency gây độ trễ. Khi log entry có field trace và span ID tương ứng, bạn có thể mở log từ trace hoặc xem các log liên quan trong Logs Explorer.

Để log được liên kết, các entry cần cùng trace resource và có timestamp phù hợp. Nếu dùng OpenTelemetry, hãy đảm bảo log được tạo trong context của span để trace ID và span ID được gắn vào log record. Việc correlation giúp chuyển từ câu hỏi “request nào chậm?” sang “lệnh gọi database nào làm request chậm?” mà không phải tìm thủ công qua nhiều file log.

### 5.4. Error Reporting và Cloud Profiler

Error Reporting phân tích log để phát hiện và gom nhóm lỗi. Khi một nhóm lỗi tăng đột biến sau bản phát hành, hãy so sánh thời điểm bắt đầu lỗi, version và stack trace với sự kiện triển khai.

Cloud Profiler thu thập thông tin CPU và memory allocation để xác định hàm hoặc đoạn mã tiêu thụ tài nguyên. Dùng profiler sau khi metric hoặc trace cho thấy một vấn đề về hiệu năng cần điều tra ở cấp mã nguồn. Trace cho biết request chậm ở bước nào; profile giúp tìm phần code đang dùng tài nguyên trong bước đó.

## 6. Thiết kế SLI, SLO và cảnh báo

Telemetry có giá trị khi được chuyển thành quyết định vận hành. SLI là chỉ số đo chất lượng dịch vụ; SLO là mục tiêu mong muốn của SLI trong một khoảng thời gian; error budget là phần sai lỗi được phép trước khi vi phạm SLO.

### 6.1. Chọn SLI theo trải nghiệm người dùng

Hai SLI cơ bản cho API là availability và latency:

- **Availability SLI:** số request tốt chia cho tổng request hợp lệ.
- **Latency SLI:** số request hoàn thành dưới ngưỡng thời gian chia cho tổng request được đo.

Ví dụ một dịch vụ checkout đặt hai mục tiêu:

- Availability: ít nhất 99,9% request hợp lệ thành công trong cửa sổ 30 ngày.
- Latency: ít nhất 95% request hoàn thành dưới 300 ms trong cùng cửa sổ.

Đây là ví dụ để minh họa cách viết SLO; ngưỡng thực tế cần dựa trên nhu cầu người dùng, baseline và cam kết của dịch vụ. Không dùng CPU làm SLI trực tiếp cho trải nghiệm người dùng nếu có thể đo thành công và độ trễ của request.

### 6.2. Tính error budget

Với SLO availability 99,9%, tỷ lệ request không tốt được phép là:

\[
1 - 0.999 = 0.001 = 0.1\%
\]

Nếu có 1.000.000 request hợp lệ trong kỳ, error budget tương ứng là:

\[
1.000.000 \times 0.001 = 1.000 \text{ request}
\]

Error budget giúp đội phát triển và vận hành cân nhắc rủi ro khi phát hành. Nếu budget bị tiêu thụ nhanh, có thể tạm giảm tốc độ thay đổi và ưu tiên xử lý độ tin cậy. SLO 100% không để lại error budget và thường không phải mục tiêu vận hành thực tế.

### 6.3. Tạo cảnh báo có thể hành động

Cảnh báo nên tập trung vào triệu chứng ảnh hưởng đến người dùng và tốc độ tiêu thụ error budget. Ví dụ:

| Điều kiện | Mục tiêu cảnh báo | Hành động gợi ý |
| --- | --- | --- |
| Error budget burn tăng nhanh | Phát hiện dịch vụ có nguy cơ vi phạm SLO. | Kiểm tra error rate, version và dependency. |
| p95 latency vượt mục tiêu liên tục | Phát hiện suy giảm trải nghiệm. | Mở trace mẫu và tìm span chậm. |
| HTTP 5xx tăng đột biến | Phát hiện lỗi request. | Nhóm lỗi theo route, version và downstream. |
| Queue age hoặc consumer lag tăng | Phát hiện worker không xử lý kịp. | Kiểm tra worker count, retry và dependency. |
| Disk gần đầy hoặc memory tăng liên tục | Phát hiện nguy cơ cạn tài nguyên. | Xác định tốc độ tăng, dung lượng còn lại và kế hoạch mở rộng. |
| Không có telemetry trong thời gian dự kiến | Phát hiện agent hoặc pipeline thu thập bị hỏng. | Kiểm tra collector, quyền IAM, endpoint và exporter. |

Không gửi cảnh báo cho mọi lỗi đơn lẻ nếu chúng không cần hành động. Gom nhóm theo dịch vụ và nguyên nhân, đặt thời gian đánh giá đủ để tránh nhiễu, đồng thời dùng notification channel đúng nhóm trực ca. Alert không có hướng xử lý rõ ràng thường tạo ra mệt mỏi cảnh báo.

## 7. Kiểm soát chất lượng, chi phí và bảo mật telemetry

Telemetry có thể tăng nhanh theo lưu lượng, số service, số nhãn và thời gian lưu trữ. Thiết kế từ đầu giúp giữ dữ liệu hữu ích mà không tạo gánh nặng vận hành.

### 7.1. Kiểm soát cardinality

Cardinality là số lượng time series khác nhau được tạo ra bởi metric và tập nhãn. Nếu đưa `user_id`, `request_id`, email hoặc URL đầy đủ vào metric label, số time series có thể tăng rất lớn. Dùng metric labels có tập giá trị giới hạn, ví dụ method, route template, status class, region hoặc service version.

Với request ID, trace ID và user ID, hãy lưu trong log hoặc trace khi có lý do hợp lệ và kiểm soát quyền truy cập. Không biến những định danh duy nhất này thành nhãn metric.

### 7.2. Giảm chi phí mà vẫn giữ khả năng điều tra

- Dùng sampling cho trace ở workload có lưu lượng cao; bảo đảm các dịch vụ trong cùng request tôn trọng sampling context.
- Chỉ tạo span chi tiết ở ranh giới nghiệp vụ hoặc dependency cần phân tích.
- Dùng histogram phù hợp và giới hạn nhãn metric.
- Đặt retention cho log bucket theo nhu cầu vận hành và kiểm toán; định tuyến log dài hạn đến nơi lưu trữ phù hợp.
- Theo dõi volume ingest của log, số trace span và số time series metric.
- Loại bỏ log debug lặp lại hoặc telemetry không có giá trị điều tra sau khi đánh giá tác động.

Cloud Trace hỗ trợ sampling ở phía các thành phần gửi dữ liệu. Cloud Trace không tự thực hiện tail-based sampling; nếu cần quyết định sampling sau khi đã xem toàn bộ trace, phải dùng collector trung gian có Tail Sampling Processor và thiết kế để các span cùng trace ID đến cùng collector. Sampling và context propagation là hai việc khác nhau: sampling quyết định có ghi span hay không, còn propagation giúp liên kết span giữa các dịch vụ.

Không loại bỏ log bảo mật, audit hoặc bằng chứng bắt buộc chỉ để giảm chi phí. Hãy giữ chính sách retention và quyền truy cập phù hợp với yêu cầu tổ chức.

### 7.3. Bảo vệ dữ liệu telemetry

- Không ghi secret, token, mật khẩu, private key, cookie hoặc dữ liệu cá nhân nhạy cảm vào log/span.
- Redact hoặc mask field nhạy cảm trước khi export; không trông chờ người đọc log tự bỏ qua dữ liệu đó.
- Cấp quyền IAM tối thiểu cho người xem log, metric và trace; tách quyền quản trị pipeline khỏi quyền truy vấn.
- Bảo vệ collector endpoint bằng mạng, xác thực và TLS theo kiến trúc triển khai.
- Kiểm soát log sink, bucket, retention và project lưu trữ tập trung.
- Đưa cấu hình telemetry vào quy trình review và triển khai như các cấu hình ứng dụng khác.

### 7.4. Quan sát nhiều project

Với hệ thống chia thành nhiều project, hãy dùng observability scope để xem telemetry tập trung. Google Cloud Application Monitoring có thể hiển thị logs, metrics và traces của ứng dụng App Hub trên nhiều project thông qua log scope, metrics scope và trace scope. Cấu hình quyền IAM cho người vận hành và xác định rõ project nào là nơi truy vấn hoặc quản lý dữ liệu.

Tổ chức dữ liệu theo application/service giúp dashboard, alert và runbook phản ánh cấu trúc vận hành thực tế thay vì chỉ phản ánh ranh giới project.

## 8. Tình huống thực tế: điều tra checkout API chậm

Giả sử người dùng báo rằng thao tác checkout mất 4 giây, trong khi mục tiêu p95 là 300 ms. Hệ thống gồm Cloud Run `checkout-api`, GKE `inventory-api`, dịch vụ thanh toán bên ngoài và Cloud SQL.

Thực hiện điều tra theo trình tự:

1. **Xác nhận phạm vi ảnh hưởng:** Mở Cloud Monitoring dashboard, kiểm tra request rate, error rate, p50/p95/p99 latency và thời điểm bắt đầu suy giảm. So sánh theo `service.version` và environment để xem lỗi có xuất hiện sau bản phát hành không.
2. **Tìm trace đại diện:** Mở Cloud Trace, lọc theo service và khoảng thời gian, chọn trace có latency cao. Quan sát waterfall để xác định span chiếm nhiều thời gian.
3. **Kiểm tra dependency:** Nếu span gọi `inventory-api` chiếm 3 giây, kiểm tra các span con của inventory, database query và connection pool. Nếu span thanh toán chậm, xác định đó là thời gian chờ mạng, retry hay xử lý từ nhà cung cấp.
4. **Mở log liên quan:** Từ trace, mở log cùng trace ID/span ID. Kiểm tra timeout, mã trạng thái, retry count và thông tin lỗi đã được làm sạch.
5. **Kiểm tra tài nguyên:** Xem CPU, memory, số instance, concurrency, queue depth và connection pool. Nếu trace cho thấy bước xử lý nội bộ tốn CPU, dùng Cloud Profiler để tìm hàm tiêu thụ tài nguyên.
6. **Đánh giá thay đổi:** Đối chiếu thời điểm với bản phát hành, cấu hình autoscaling, thay đổi database, quota hoặc sự cố dependency.
7. **Khắc phục và xác minh:** Triển khai thay đổi có kiểm soát, sau đó xác minh p95, error rate và error budget trở lại mức mục tiêu. Cập nhật dashboard, alert và runbook nếu phát hiện khoảng trống trong telemetry.

Nếu trace không có span của dịch vụ downstream, hãy kiểm tra propagation qua HTTP hoặc message metadata. Nếu log không xuất hiện cùng trace, xác minh field trace/span trong log entry. Nếu metric ngừng cập nhật, kiểm tra collector, exporter, IAM permission, endpoint và quota trước khi kết luận workload không phát sinh hoạt động.

## 9. Quy trình triển khai observability cho một workload mới

Có thể dùng trình tự sau cho workload chạy trên Google Cloud:

1. Xác định chức năng quan trọng, dependency, người sở hữu dịch vụ và các SLI cần đo.
2. Chuẩn hóa resource attributes, tên metric, schema log và trace context.
3. Instrument ứng dụng bằng OpenTelemetry; bật instrumentation tự động cho framework phù hợp và thêm span cho nghiệp vụ quan trọng.
4. Chọn collector/agent theo môi trường: Ops Agent trên VM, Managed OpenTelemetry hoặc Google-Built OTel Collector trên GKE, sidecar hoặc direct export trên Cloud Run.
5. Gửi log có cấu trúc và kiểm tra correlation giữa log, metric và trace.
6. Tạo dashboard theo góc nhìn người dùng, dependency và hạ tầng.
7. Định nghĩa SLI/SLO, error budget và alerting policy; thêm uptime check hoặc synthetic monitor cho luồng quan trọng.
8. Cấp IAM tối thiểu, cấu hình retention, kiểm soát dữ liệu nhạy cảm và theo dõi chi phí ingest.
9. Thử nghiệm một tình huống lỗi có kiểm soát để xác nhận đội vận hành có thể phát hiện, điều tra và khôi phục bằng telemetry đã thiết kế.

## 10. Checklist thiết kế telemetry

- [ ] Mỗi workload có `service.name`, environment và version ổn định.
- [ ] Metrics đo traffic, latency, errors và saturation cùng các tín hiệu đặc thù của workload.
- [ ] Histogram được dùng cho phân phối latency; metric labels có cardinality được kiểm soát.
- [ ] Logs là JSON có severity, message, timestamp và thông tin service.
- [ ] Log và trace được liên kết bằng trace ID/span ID khi có context.
- [ ] Trace context được truyền qua HTTP và message metadata ở ranh giới dịch vụ.
- [ ] Sampling được chọn theo lưu lượng, chi phí và yêu cầu điều tra.
- [ ] Collector/agent phù hợp với vòng đời Compute Engine, GKE hoặc Cloud Run.
- [ ] Dashboard có thể trả lời câu hỏi về sức khỏe dịch vụ và dependency.
- [ ] SLI/SLO phản ánh trải nghiệm người dùng và có error budget.
- [ ] Alert có chủ sở hữu, ngưỡng phù hợp, notification channel và runbook.
- [ ] Telemetry không chứa secret hoặc dữ liệu cá nhân không cần thiết.
- [ ] Retention, IAM, log routing và chi phí ingest được kiểm soát.
- [ ] Đã thử nghiệm quy trình phát hiện, điều tra và xác minh sau khắc phục.

## Tài liệu tham khảo

- [Google Cloud Observability overview](https://docs.cloud.google.com/stackdriver/docs/observability) — vai trò của Cloud Logging, Cloud Monitoring, Cloud Trace và Error Reporting.
- [Observability in Google Cloud](https://docs.cloud.google.com/stackdriver/docs) — khái niệm metrics, logs, traces và cách kết hợp telemetry.
- [Choose an instrumentation approach](https://docs.cloud.google.com/stackdriver/docs/instrumentation/choose-approach) — khuyến nghị OpenTelemetry, collector và cách thu thập theo GKE, Compute Engine, Cloud Run.
- [Telemetry (OTLP) API overview](https://docs.cloud.google.com/stackdriver/docs/reference/telemetry/overview) — giao thức OTLP và API nhận telemetry.
- [Managed OpenTelemetry for GKE](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/managed-otel-gke) — managed collector và endpoint OTLP cho GKE.
- [Google Cloud Managed Service for Prometheus](https://docs.cloud.google.com/stackdriver/docs/managed-prometheus) — thu thập Prometheus metrics trong Kubernetes và các môi trường khác.
- [Cloud Trace overview](https://docs.cloud.google.com/trace/docs/overview) — trace explorer, instrumentation và phân tích độ trễ.
- [Trace context](https://docs.cloud.google.com/trace/docs/trace-context) — truyền trace context giữa các thành phần.
- [Link log entries with traces](https://docs.cloud.google.com/trace/docs/trace-log-integration) — liên kết log entry với trace và span.
- [Trace sampling](https://docs.cloud.google.com/trace/docs/trace-sampling) — sampling, quota và tail-based sampling.
- [Cloud Monitoring alerting overview](https://docs.cloud.google.com/monitoring/alerts) — metric-based, log-based và SQL-based alerting.
- [SLO monitoring concepts](https://docs.cloud.google.com/stackdriver/docs/solutions/slo-monitoring) — SLI, SLO và error budget.
- [Cloud Profiler documentation](https://docs.cloud.google.com/profiler/docs) — profiling CPU và memory allocation.
- [Cloud Logging overview](https://docs.cloud.google.com/logging/docs/overview) — thu thập, truy vấn, lưu trữ và định tuyến log.

