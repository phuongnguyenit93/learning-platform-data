# Cloud Trace và distributed tracing

Trong một hệ thống gồm nhiều dịch vụ, một request của người dùng có thể đi qua load balancer, API gateway, Cloud Run hoặc GKE, rồi gọi database, cache và các dịch vụ bên ngoài. Khi request chậm hoặc thất bại, log của từng thành phần thường chỉ cho thấy một phần câu chuyện. Distributed tracing liên kết các thao tác đó thành một trace để người vận hành nhìn được đường đi của request, thời gian xử lý ở từng bước và nơi phát sinh độ trễ.

Cloud Trace là dịch vụ của Google Cloud dùng để nhận, lưu và khám phá trace. OpenTelemetry cung cấp API, SDK và cơ chế truyền ngữ cảnh để ứng dụng tạo trace theo một chuẩn có thể dùng trên nhiều nền tảng. Kết hợp hai công cụ này giúp nhóm phát triển theo dõi ứng dụng chạy trên Compute Engine, GKE, Cloud Run và các dịch vụ GCP khác.

Trong phạm vi **CLOUD_PROVIDERS_GCP**, distributed tracing bổ sung góc nhìn theo request cho việc vận hành project, mạng, workload, lưu trữ và cơ sở dữ liệu. Nó hỗ trợ xác định dịch vụ phụ thuộc gây chậm, kiểm tra ảnh hưởng sau khi phát hành, đối chiếu log và metric, đồng thời giúp đánh giá độ tin cậy và chi phí của hệ thống.

Sau bài học, người học có thể:

- Giải thích trace, span, parent-child relationship và trace context.
- Mô tả cách trace context được truyền qua HTTP, RPC, hàng đợi và các tác vụ bất đồng bộ.
- Instrument ứng dụng bằng OpenTelemetry SDK hoặc agent.
- Gửi trace từ workload tới Cloud Trace bằng exporter hoặc OpenTelemetry Collector.
- Đọc waterfall, nhận diện span chậm và liên kết trace với log.
- Chọn chiến lược sampling, thuộc tính span và cách bảo vệ dữ liệu trace phù hợp.

## 1. Distributed tracing giải quyết vấn đề gì?

Log thường mô tả một sự kiện tại một thành phần: request được nhận, câu lệnh database thất bại hoặc container ghi một exception. Metric tổng hợp số liệu theo thời gian: request rate, error rate, CPU hoặc latency percentile. Trace trả lời một câu hỏi khác: **một request cụ thể đã đi qua những thành phần nào và thời gian được tiêu tốn ở đâu?**

Ví dụ, API đặt hàng có thể gọi dịch vụ kiểm tra tồn kho, dịch vụ thanh toán và database. Người dùng thấy request mất 2,4 giây. Nếu chỉ xem log của API, ta có thể biết request bắt đầu và kết thúc, nhưng chưa chắc biết dịch vụ nào làm chậm. Trace cho thấy các span con và thời lượng tương ứng.

~~~mermaid
flowchart LR
    U[Client] --> G[HTTPS Load Balancer]
    G --> A[orders-api]
    A --> B[inventory-service]
    A --> C[payment-service]
    A --> D[Cloud SQL]
    B --> E[Inventory database]
    C --> F[Payment provider]
~~~

Mỗi thành phần có thể tạo một hoặc nhiều span. Nếu các span mang cùng trace ID và được nối bằng quan hệ cha-con hoặc link, Cloud Trace có thể hiển thị chúng trong một dòng thời gian thống nhất.

Distributed tracing hữu ích khi:

- Một request đi qua nhiều microservice hoặc nhiều vùng triển khai.
- Độ trễ tăng nhưng CPU và bộ nhớ của service đầu vào vẫn bình thường.
- Một dependency như database, API bên thứ ba hoặc message broker phản hồi chậm.
- Lỗi chỉ xuất hiện trên một số request, tenant, revision hoặc đường xử lý.
- Nhóm cần so sánh hành vi trước và sau một lần triển khai.

Tracing không thay thế log và metric. Trace giúp giải thích đường đi của request; log lưu chi tiết sự kiện; metric cho biết xu hướng và mức độ ảnh hưởng trên toàn hệ thống.

## 2. Mô hình trace và span

### 2.1. Trace

Một **trace** biểu diễn hành trình của một operation xuyên qua một hoặc nhiều thành phần. Trace có một định danh duy nhất gọi là trace ID. Các span thuộc cùng trace có thể được ghép lại để tạo thành bức tranh tổng thể.

Một trace thường có:

- Trace ID: định danh trace, được truyền giữa các thành phần.
- Root span: span gốc đại diện cho operation đầu tiên được đo.
- Child spans: các thao tác con như gọi HTTP, truy vấn database hoặc xử lý nghiệp vụ.
- Trace context: dữ liệu cần thiết để thành phần tiếp theo tiếp tục đúng trace.

Không phải mọi trace đều đầy đủ. Một service có thể chưa được instrument, một request có thể mất context khi đi qua hàng đợi, hoặc sampling có thể loại bỏ một phần trace. Vì vậy, cần xem xét mức độ bao phủ instrumentation trước khi kết luận một dependency không được gọi.

### 2.2. Span

**Span** là một đơn vị công việc có thời điểm bắt đầu và kết thúc. Một span thường có các thành phần:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Name | Tên operation | `POST /orders`, `inventory.lookup` |
| Start/end time | Khoảng thời gian thực hiện | 10:15:03.120–10:15:03.185 |
| Trace ID | Trace mà span thuộc về | Một ID chung cho request |
| Span ID | Định danh riêng của span | ID của thao tác lookup |
| Parent span ID | Span cha nếu có | Span của `orders-api` |
| Attributes | Thuộc tính mô tả operation | HTTP method, route, DB system |
| Events | Sự kiện xảy ra trong span | Retry, cache miss, exception |
| Status | Kết quả của span | OK hoặc ERROR |
| Links | Liên kết tới span context khác | Một consumer xử lý batch nhiều message |

Span cha thường bao trùm khoảng thời gian của các span con. Các span con có thể chạy tuần tự hoặc song song, vì vậy không cộng máy móc thời lượng của tất cả span để suy ra thời lượng request. Khi các lời gọi chạy song song, thời gian tổng thể phụ thuộc vào đường găng và thời điểm hoàn tất của operation.

Ví dụ một trace:

~~~text
Trace: create-order
└── HTTP POST /orders                 2,400 ms
    ├── inventory.lookup                180 ms
    │   └── SQL SELECT inventory         95 ms
    ├── payment.authorize              1,850 ms
    │   └── HTTP POST payment-provider 1,720 ms
    └── SQL INSERT order                 70 ms
~~~

Trong ví dụ này, lời gọi payment provider chiếm phần lớn thời gian. Tối ưu truy vấn INSERT có thể không cải thiện đáng kể latency của request; cần điều tra dependency thanh toán trước.

### 2.3. Attributes, events, status và links

- **Attributes** mô tả ngữ cảnh của span. Nên ưu tiên thuộc tính có ý nghĩa vận hành như tên service, route chuẩn hóa, loại database, trạng thái HTTP và phiên bản triển khai.
- **Events** ghi lại một mốc xảy ra bên trong span, chẳng hạn bắt đầu retry hoặc nhận được phản hồi từ dependency.
- **Status** cho biết span có lỗi hay không. Khi bắt exception, nên ghi nhận lỗi và đặt status phù hợp nếu thư viện instrumentation chưa tự làm điều đó.
- **Links** kết nối span với một hoặc nhiều span context khác mà không ép chúng thành quan hệ cha-con. Links hữu ích cho xử lý batch hoặc tác vụ được kích hoạt từ nhiều message.

Không đưa password, token, nội dung request nhạy cảm hoặc dữ liệu cá nhân vào attributes, events hay baggage. Tránh dùng giá trị có cardinality rất cao như user ID, email, session ID hoặc raw URL chứa ID làm nhãn phổ biến. Chúng làm trace khó phân tích và có thể làm tăng chi phí hoặc rủi ro lộ dữ liệu.

## 3. Trace context và truyền ngữ cảnh giữa dịch vụ

Để các service tạo span trong cùng một trace, chúng phải truyền trace context qua ranh giới giao tiếp. Nếu mỗi service tự tạo một trace mới, giao diện sẽ hiển thị nhiều trace rời rạc và khó nối được request ban đầu.

### 3.1. W3C Trace Context

OpenTelemetry hỗ trợ chuẩn W3C Trace Context. Header HTTP quan trọng nhất là `traceparent`, có cấu trúc:

~~~text
traceparent: 00-<trace-id>-<parent-id>-<trace-flags>
~~~

Trong đó:

- `trace-id` có 32 ký tự hex và nhận diện trace.
- `parent-id` có 16 ký tự hex và nhận diện span đã gửi request.
- `trace-flags` chứa cờ như trạng thái sampled.
- `tracestate` là header tùy chọn để truyền thông tin vendor-specific theo chuẩn.

Ví dụ minh họa:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
tracestate: vendor=value
~~~

Khi service A gọi service B, instrumentation của A inject context vào header. Instrumentation của B extract context, tạo span mới với trace ID tương ứng và parent là span của A. Cách này duy trì quan hệ xuyên suốt qua nhiều service mà không cần tự truyền trace ID trong từng hàm nghiệp vụ.

### 3.2. Header tương thích Google Cloud cũ

Một số thành phần hoặc hệ thống cũ có thể sử dụng header `X-Cloud-Trace-Context`. Dạng thường gặp:

~~~text
X-Cloud-Trace-Context: TRACE_ID/SPAN_ID;o=TRACE_TRUE
~~~

Đây là định dạng tương thích của Google Cloud. Khi tích hợp hệ thống hỗn hợp, hãy xác nhận các proxy, gateway và thư viện tracing có cùng cấu hình propagator hoặc có chuyển đổi header phù hợp. Không giả định rằng mọi framework đều tự động chuyển đổi giữa W3C Trace Context và header cũ.

### 3.3. HTTP, RPC và message queue

Với HTTP hoặc RPC, context thường được inject vào metadata/header của request. Với message queue, producer có thể ghi trace context vào message attributes hoặc headers; consumer extract context khi xử lý message.

Các trường hợp cần lưu ý:

- **HTTP đồng bộ:** span client của service gọi và span server của service nhận cần được nối bằng context.
- **Tác vụ bất đồng bộ:** context phải được giữ khi đưa công việc vào executor, scheduler hoặc background worker.
- **Message queue:** context cần đi cùng message qua broker; thời gian chờ trong queue có thể cần được thể hiện riêng để phân biệt với thời gian xử lý.
- **Batch processing:** một batch có thể gồm nhiều message với nhiều trace context. Cân nhắc tạo span consumer mới và dùng links tới các context nguồn thay vì chọn tùy tiện một message làm parent.
- **Ranh giới tin cậy:** nếu nhận context từ client không đáng tin cậy, cần cân nhắc chính sách tiếp nhận hoặc tạo trace mới. Không dùng trace context làm cơ chế xác thực hay phân quyền.

OpenTelemetry cung cấp propagator để inject và extract context. Dùng instrumentation có sẵn của framework khi có thể; tự viết logic header chỉ khi hệ thống có giao thức riêng và đã kiểm thử tương thích.

## 4. Cloud Trace trong kiến trúc observability của GCP

Cloud Trace nhận trace từ ứng dụng hoặc collector và cung cấp giao diện để xem chi tiết trace, span và phân bố độ trễ. Ứng dụng cần được instrument và cấu hình exporter; Cloud Trace không tự suy ra mọi span từ một ứng dụng chưa phát trace.

~~~mermaid
flowchart LR
    A[Ứng dụng và thư viện] --> B[OpenTelemetry API / SDK / Agent]
    B --> C[OTLP]
    C --> D[OpenTelemetry Collector]
    D --> E[Cloud Trace]
    A --> F[Cloud Logging]
    E --> G[Trace waterfall và latency analysis]
    F --> H[Log Explorer]
    G --> I[Đối chiếu trace, log và metric]
    H --> I
    J[Cloud Monitoring] --> I
~~~

Các thành phần:

1. **Instrumentation:** thư viện hoặc agent tạo span khi ứng dụng nhận request, gọi dependency hoặc thực hiện thao tác nghiệp vụ.
2. **OpenTelemetry SDK:** quản lý tracer provider, resource, processor, sampler và exporter trong tiến trình ứng dụng.
3. **OTLP:** giao thức chuẩn để gửi telemetry từ SDK tới collector hoặc backend hỗ trợ.
4. **OpenTelemetry Collector:** nhận, xử lý theo batch, lọc hoặc lấy mẫu rồi xuất trace tới backend. Collector cũng có thể gom telemetry từ nhiều workload.
5. **Cloud Trace:** lưu và hiển thị trace để người vận hành tìm kiếm và phân tích.

Collector không bắt buộc cho mọi kiến trúc nhỏ. Ứng dụng có thể xuất trực tiếp bằng exporter tương thích. Tuy nhiên, collector giúp tách cấu hình backend khỏi ứng dụng, tập trung xác thực, batch, retry, sampling và quản lý nhiều nguồn telemetry.

### 4.1. Chuẩn bị project và quyền

Trước khi gửi trace lên Google Cloud:

1. Chọn project đích sẽ lưu trace và xác định project chứa workload nếu khác project.
2. Bật Cloud Trace API cho project nhận trace.
3. Cấp cho danh tính chạy exporter hoặc collector quyền ghi trace phù hợp, thường là role `roles/cloudtrace.agent` trong phạm vi project đích.
4. Dùng Application Default Credentials (ADC), service account gắn với workload hoặc Workload Identity; tránh lưu khóa JSON lâu dài trong image hay source.
5. Xác minh network egress và DNS cho đường gửi telemetry nếu workload chạy trong mạng bị giới hạn.

Nếu collector chạy với service account riêng, quyền ghi trace cần được cấp cho danh tính của collector. Không nhầm quyền của ứng dụng gọi API nghiệp vụ với quyền của tiến trình xuất trace.

### 4.2. Resource attributes

Resource attributes mô tả nguồn tạo telemetry. Nên thiết lập tối thiểu:

| Attribute | Ví dụ | Mục đích |
|---|---|---|
| `service.name` | `orders-api` | Phân biệt service |
| `service.version` | `2026.11.19` | So sánh các bản phát hành |
| `deployment.environment.name` | `production` | Phân biệt môi trường |
| `service.namespace` | `commerce` | Nhóm service theo miền nghiệp vụ |
| `cloud.region` | `asia-southeast1` | Xác định vùng chạy |
| `cloud.platform` | `gcp_cloud_run` hoặc giá trị phù hợp | Mô tả nền tảng |

Giá trị phải phản ánh môi trường thật và tuân theo semantic conventions mà phiên bản OpenTelemetry đang dùng hỗ trợ. Tránh đặt tên service khác nhau giữa log, trace và metric nếu chúng cùng nói về một workload.

## 5. Instrument ứng dụng bằng OpenTelemetry

Có hai cách chính để tạo span:

- **Automatic instrumentation:** agent hoặc thư viện tự instrument framework HTTP, client database, RPC và một số dependency. Cách này giúp có trace nhanh với ít thay đổi source.
- **Manual instrumentation:** lập trình viên tạo span quanh thao tác nghiệp vụ riêng để đo phần logic mà instrumentation tự động không hiểu.

Nên bắt đầu bằng automatic instrumentation cho framework phổ biến, sau đó bổ sung manual span ở các ranh giới nghiệp vụ có giá trị. Tạo quá nhiều span nhỏ cho từng hàm nội bộ có thể làm trace rối và tăng volume.

### 5.1. Ví dụ Java dùng OpenTelemetry API

Đoạn mã sau minh họa cách tạo span cho thao tác tra cứu tồn kho. Biến `tracer` được lấy từ OpenTelemetry SDK đã được khởi tạo trong ứng dụng:

~~~java
Span span = tracer.spanBuilder("inventory.lookup").startSpan();

try (Scope scope = span.makeCurrent()) {
    span.setAttribute("inventory.region", region);
    span.setAttribute("inventory.source", "primary");

    return inventoryRepository.findBySku(sku);
} catch (RuntimeException exception) {
    span.recordException(exception);
    span.setStatus(StatusCode.ERROR, "inventory lookup failed");
    throw exception;
} finally {
    span.end();
}
~~~

Các điểm quan trọng:

- `startSpan()` bắt đầu đo operation.
- `makeCurrent()` đặt span vào context hiện tại để các lời gọi con được instrument có thể kế thừa parent context.
- `setAttribute()` bổ sung ngữ cảnh có ích cho điều tra.
- `recordException()` và `setStatus()` ghi nhận lỗi khi exception đi qua đoạn mã.
- `end()` phải được gọi kể cả khi operation thành công hay thất bại.

Đây là ví dụ rút gọn; cần có các import, tracer initialization và dependency OpenTelemetry phù hợp với ứng dụng. Không đặt SKU nhạy cảm, thông tin khách hàng hoặc dữ liệu bí mật vào span attributes nếu không có lý do và kiểm soát phù hợp.

### 5.2. Ví dụ bật Java agent

Với ứng dụng Java dùng framework phổ biến, có thể bắt đầu bằng OpenTelemetry Java agent để tự động instrument một số thư viện:

~~~bash
java \
  -javaagent:/opt/opentelemetry-javaagent.jar \
  -Dotel.service.name=orders-api \
  -Dotel.resource.attributes=service.version=2026.11,deployment.environment.name=production \
  -Dotel.exporter.otlp.endpoint=http://otel-collector:4317 \
  -Dotel.exporter.otlp.protocol=grpc \
  -jar app.jar
~~~

Ví dụ giả định collector có thể truy cập tại `otel-collector:4317` và nhận OTLP qua gRPC. Tên host, port, giao thức, cách khởi chạy agent và thuộc tính resource cần điều chỉnh theo môi trường. Ứng dụng gửi OTLP tới collector; collector được cấu hình exporter Google Cloud để chuyển trace vào Cloud Trace.

### 5.3. Cấu hình OpenTelemetry Collector tối thiểu

Ví dụ cấu hình minh họa cho collector distribution có hỗ trợ receiver OTLP và exporter Google Cloud:

~~~yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:

exporters:
  googlecloud:

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [googlecloud]
~~~

Collector cần chạy bằng danh tính có quyền ghi trace và có ADC hợp lệ. Một số bản phân phối Collector không đóng gói exporter `googlecloud`; hãy chọn distribution phù hợp, kiểm tra danh sách component của phiên bản đang triển khai và xác thực cấu hình trước khi phát hành. Trong production, cân nhắc thêm memory limiter, retry/queue, TLS hoặc xác thực OTLP, health check và giám sát chính collector.

## 6. Triển khai tracing trên các dịch vụ GCP

### 6.1. Cloud Run

- Instrument ứng dụng bằng OpenTelemetry SDK hoặc agent.
- Đặt `service.name` ổn định và thêm service version/revision để phân biệt bản phát hành.
- Cấu hình exporter trực tiếp hoặc gửi OTLP tới collector sidecar/endpoint phù hợp với kiến trúc.
- Cấp quyền Cloud Trace cho danh tính thực sự gửi trace.
- Giữ trace context qua các lời gọi HTTP đi ra và các tác vụ nền.
- Kết hợp trace với request log của Cloud Run để điều tra cùng một request.

Cloud Run có thể tự cung cấp một số thông tin request và log nền tảng, nhưng mức độ chi tiết của span ứng dụng phụ thuộc instrumentation. Đừng mặc định mọi lời gọi database hoặc HTTP client đã được đo nếu chưa kiểm tra thư viện tương ứng.

### 6.2. Google Kubernetes Engine

- Chọn mô hình triển khai collector: sidecar, DaemonSet hoặc gateway tập trung tùy mật độ workload và ranh giới mạng.
- Gắn danh tính collector bằng Workload Identity for GKE hoặc cơ chế danh tính được tổ chức phê duyệt.
- Đặt resource attributes để nhận diện cluster, namespace, workload và service.
- Bảo đảm pod có thể gửi OTLP tới collector và collector có thể gửi trace tới Google Cloud.
- Kiểm tra context propagation qua service mesh, ingress, egress và message broker.
- Tránh instrument trùng lặp cùng một lớp giao tiếp ở cả agent và library nếu tạo ra span lặp không có ý nghĩa.

Với collector dùng chung, giới hạn ai được gửi telemetry vào endpoint và bảo vệ endpoint khỏi truy cập không mong muốn. Cấu hình batch, memory và retry để collector không trở thành điểm nghẽn khi tải tăng.

### 6.3. Compute Engine

- Cài đặt OpenTelemetry Collector hoặc chạy exporter trong ứng dụng.
- Dùng service account gắn với VM hoặc danh tính workload có quyền ghi trace.
- Mở egress tới collector hoặc endpoint telemetry cần thiết theo chính sách mạng.
- Thiết lập service name, version, environment và region nhất quán.
- Theo dõi tiến trình collector, hàng đợi export và lỗi gửi telemetry.

Không cần cấp quyền quản trị VM cho ứng dụng chỉ để ghi trace. Quyền Cloud Trace nên được giới hạn ở danh tính thực hiện export.

## 7. Sampling và quản lý lượng trace

Một hệ thống có hàng nghìn request mỗi giây có thể tạo ra lượng span rất lớn. Sampling quyết định trace nào được giữ và gửi tới backend, từ đó cân bằng khả năng quan sát, tải hệ thống và chi phí.

### 7.1. Head-based sampling

Head-based sampling đưa ra quyết định sớm, thường khi root span bắt đầu. Ví dụ sampler chọn một tỷ lệ request dựa trên trace ID. Các service downstream cần kế thừa sampling decision để trace không bị đứt đoạn.

Ưu điểm:

- Dễ triển khai và giảm volume trước khi span được gửi đi.
- Có thể áp dụng nhất quán trên nhiều service khi dùng parent-based sampler.

Hạn chế:

- Quyết định được đưa ra trước khi biết request có chậm hoặc thất bại hay không.
- Một trace lỗi vẫn có thể bị loại nếu không được chọn mẫu.

### 7.2. Tail-based sampling

Tail-based sampling trì hoãn quyết định cho đến khi collector đã nhận đủ một phần hoặc toàn bộ trace. Collector có thể ưu tiên giữ trace có lỗi, latency cao hoặc thuộc nhóm cần kiểm tra.

Ưu điểm là có thể chọn mẫu dựa trên kết quả cuối cùng. Đổi lại, collector phải giữ trace trong bộ nhớ hoặc hàng đợi một khoảng thời gian; cấu hình không đủ tài nguyên có thể làm mất dữ liệu hoặc tăng độ trễ.

Tail sampling cần được thiết kế ở collector hoặc pipeline hỗ trợ, không nên giả định Cloud Trace tự giữ mọi span rồi mới chọn mẫu theo tiêu chí tùy ý.

### 7.3. Chọn chính sách sampling

- Bắt đầu với tỷ lệ đủ để kiểm tra instrumentation trong môi trường dev/test.
- Production có tải lớn nên chọn tỷ lệ theo lưu lượng, mục tiêu điều tra và ngân sách.
- Cân nhắc ưu tiên trace có lỗi hoặc vượt ngưỡng latency nếu dùng tail sampling.
- Duy trì một tỷ lệ trace thành công để có đường cơ sở so sánh.
- Đảm bảo các service cùng kế thừa quyết định sampling khi dùng head-based sampling.
- Theo dõi số span được tạo, số span export thành công và lỗi exporter.

Sampling làm giảm khả năng quan sát các request hiếm. Không dùng một trace đơn lẻ làm bằng chứng rằng mọi request khác đều hoạt động giống vậy; kết hợp trace với metric tổng hợp và log theo yêu cầu.

## 8. Đọc trace trong Cloud Trace

Khi mở một trace trong Cloud Trace, hãy đọc theo thứ tự từ operation gốc tới các span con.

1. **Xác định root span:** kiểm tra tên operation, service, thời điểm và tổng thời lượng.
2. **Quan sát waterfall:** xem span nào bắt đầu, kết thúc và chạy song song; xác định đoạn nằm trên đường găng.
3. **Tìm span dài bất thường:** so sánh thời lượng của HTTP client, RPC, database và các thao tác nội bộ.
4. **Kiểm tra status và events:** xem exception, retry, timeout hoặc thuộc tính thể hiện trạng thái lỗi.
5. **So sánh các trace:** chọn request thành công và request chậm có điều kiện tương tự để tìm điểm khác biệt.
6. **Đối chiếu log và metric:** dùng trace ID, span ID, timestamp và service name để mở log liên quan; xem metric để đánh giá mức độ phổ biến.

Một số dấu hiệu thường gặp:

| Dấu hiệu trên trace | Khả năng cần kiểm tra |
|---|---|
| Root span dài, không có child span tương ứng | Instrumentation thiếu, công việc đồng bộ chưa được đo hoặc code chờ nội bộ |
| Một HTTP client span chiếm phần lớn thời gian | Dependency từ xa, DNS, TLS, retry hoặc timeout |
| Nhiều span database chậm | Query plan, connection pool, lock, I/O hoặc tải database |
| Span con bắt đầu muộn | Queueing, thread pool, scheduler hoặc chờ tài nguyên |
| Trace bị tách thành nhiều trace ID | Context propagation bị mất hoặc propagator không tương thích |
| Span lỗi nhưng request ngoài cùng thành công | Ứng dụng đã retry/fallback; cần xem kết quả cuối và chi phí retry |
| Không thấy trace của request | Sampling, quyền, exporter, cấu hình API hoặc thiếu instrumentation |

Thời lượng span có thể bao gồm thời gian chờ network, queue hoặc dependency. Một span dài không tự chứng minh CPU của service đó bận; cần đối chiếu metric và loại operation.

## 9. Liên kết Cloud Trace với Cloud Logging

Khi log chứa trace ID và span ID, người vận hành có thể chuyển từ một log entry sang trace tương ứng. Với structured logging, ứng dụng có thể ghi các trường đặc biệt của Cloud Logging:

~~~json
{
  "severity": "ERROR",
  "message": "payment authorization failed",
  "logging.googleapis.com/trace": "projects/PROJECT_ID/traces/TRACE_ID",
  "logging.googleapis.com/spanId": "SPAN_ID",
  "logging.googleapis.com/trace_sampled": true
}
~~~

Các giá trị trace và span phải là ID thực của context hiện tại. Trường trace nên có định dạng đầy đủ gắn với project như ví dụ. Khi dùng logging library hoặc agent, ưu tiên tích hợp tự động để tránh tự tạo trace ID không khớp với span đang hoạt động.

Trong quá trình điều tra:

- Từ log, lấy trace ID để mở trace.
- Từ span, đối chiếu span ID với log phát ra trong cùng operation.
- Dùng timestamp và request ID để xác nhận hai bản ghi cùng một request.
- Nếu log không có trace ID, kiểm tra logger có đọc context hiện tại và có cấu hình structured logging phù hợp không.

Trace context giúp liên kết dữ liệu quan sát; nó không nên chứa thông tin xác thực hoặc được dùng thay cho audit identity. Danh tính thực hiện thao tác vẫn cần được ghi bằng trường principal hoặc audit log tương ứng.

## 10. Phân biệt logs, metrics và traces

| Tín hiệu | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Logs | Sự kiện cụ thể nào đã xảy ra? | Exception, policy change, request bị từ chối |
| Metrics | Hệ thống đang hoạt động ở mức nào theo thời gian? | Request rate, error rate, p95 latency, CPU |
| Traces | Một request đi qua những bước nào và chậm ở đâu? | API gọi payment provider mất 1,8 giây |

Một quy trình điều tra hiệu quả thường bắt đầu từ metric báo động, dùng trace để xác định đường xử lý chậm, rồi dùng log để đọc chi tiết lỗi hoặc thay đổi đã xảy ra. Ba tín hiệu bổ trợ nhau; không nên cố biến mọi log thành metric hoặc tạo trace cho từng sự kiện không có quan hệ với request.

## 11. Lỗi thường gặp và cách xử lý

**Mỗi service tạo một trace riêng.** Kiểm tra propagator, header forwarding và instrumentation ở client/server. Đảm bảo context được inject trước khi gửi và extract khi nhận.

**Trace thiếu một service trung gian.** Xác minh service đó đã được instrument, có gửi span và không bị sampling loại. Kiểm tra đường đi qua proxy hoặc service mesh.

**Trace có span nhưng không có attributes hữu ích.** Bổ sung resource attributes và span attributes có kiểm soát. Dùng route chuẩn hóa thay cho URL chứa ID động.

**Không thấy trace trong Cloud Trace.** Kiểm tra Cloud Trace API, quyền của exporter/collector, ADC, endpoint, egress, lỗi exporter và sampling decision.

**Trace bị trùng hoặc span lặp.** Kiểm tra agent và SDK có cùng instrument một thư viện hay không; tránh tạo manual span bao quanh operation đã có auto instrumentation nếu không cần thiết.

**Trace dừng ở ranh giới bất đồng bộ.** Truyền context trong message metadata hoặc task context; kiểm tra executor và callback có giữ context hay không.

**Không tìm thấy log từ trace.** Bảo đảm logger nhận context hiện tại và ghi trace/span fields; xác minh log bucket và quyền truy cập.

**Trace chứa dữ liệu nhạy cảm.** Điều chỉnh instrumentation để loại bỏ hoặc mask attributes/events, rà soát baggage và quyền xem trace.

**Collector bị quá tải.** Theo dõi memory, queue, retry và export errors; điều chỉnh batch, sampling và số collector theo tải. Không tăng sampling hoặc queue vô hạn mà không đánh giá tài nguyên.

## 12. Thực hành: tìm dependency làm chậm API

Giả sử API `orders-api` trên Cloud Run có p95 latency tăng sau khi phát hành revision mới. Mục tiêu là tìm dependency gây chậm.

1. Mở dashboard Cloud Monitoring và xác nhận thời điểm p95 latency tăng.
2. Trong Cloud Trace, tìm trace thuộc service `orders-api` ở khoảng thời gian đó.
3. Chọn một trace chậm và một trace thành công có điều kiện gần giống nhau.
4. So sánh root span và các span con; chú ý HTTP client, database và thời gian chờ.
5. Nếu span payment dài, mở attributes/events để kiểm tra endpoint, status và retry count nếu đã instrument.
6. Lấy trace ID và tìm log liên quan trong Logs Explorer.
7. Đối chiếu audit log và revision để xác định thay đổi cấu hình hoặc phát hành có liên quan.
8. Thử biện pháp khắc phục ở môi trường phù hợp, rồi theo dõi p95, error rate và trace sau thay đổi.

Sơ đồ một trace có thể trông như sau:

~~~text
orders-api / POST /orders              2.4 s
├── inventory-service / lookup         180 ms
│   └── Cloud SQL / SELECT               95 ms
├── payment-service / authorize      1,850 ms
│   └── payment-provider / POST       1,720 ms
└── orders-db / INSERT                  70 ms
~~~

Nếu payment provider là đoạn chậm nhất, nhóm có thể xem xét timeout, retry policy, circuit breaker hoặc xử lý bất đồng bộ. Không tăng timeout một cách máy móc: việc đó có thể làm request giữ tài nguyên lâu hơn và tăng số request đồng thời khi dependency đang suy giảm.

## 13. Nguyên tắc thiết kế tracing an toàn và hữu ích

- Đặt tên span theo operation ổn định, không gắn ID động vào tên.
- Dùng resource attributes để nhận diện service, version, environment và region.
- Instrument các ranh giới giao tiếp và thao tác nghiệp vụ quan trọng.
- Bảo đảm context propagation xuyên HTTP, RPC, queue và tác vụ nền.
- Giữ attributes có ý nghĩa vận hành, tránh PII, token và dữ liệu bí mật.
- Chọn sampling theo tải và mục tiêu điều tra; đo tỷ lệ export thành công.
- Giám sát chính collector và pipeline telemetry như một workload production.
- Cấp quyền ghi trace cho danh tính exporter; cấp quyền đọc trace cho nhóm cần điều tra.
- Đặt retention, quyền truy cập và chi phí telemetry theo yêu cầu vận hành.
- Kiểm thử trace end-to-end sau mỗi thay đổi lớn ở gateway, framework, service mesh hoặc message broker.

## 14. Checklist triển khai Cloud Trace

### Instrumentation và context

- [ ] Mỗi service có `service.name` ổn định và version/environment phù hợp.
- [ ] HTTP/RPC client và server đã được instrument.
- [ ] Các thao tác database hoặc dependency quan trọng có span hữu ích.
- [ ] Trace context được truyền qua HTTP, queue và tác vụ bất đồng bộ.
- [ ] Có kiểm thử để xác nhận các span nằm trong cùng một trace.

### Gửi trace tới Google Cloud

- [ ] Cloud Trace API đã bật ở project đích.
- [ ] Exporter/collector dùng ADC hoặc workload identity.
- [ ] Danh tính gửi trace có quyền `roles/cloudtrace.agent` phù hợp.
- [ ] Endpoint, DNS, egress và giao thức OTLP hoạt động.
- [ ] Collector có batch, retry và giới hạn bộ nhớ phù hợp.
- [ ] Export errors và dropped spans được theo dõi.

### Vận hành và bảo vệ

- [ ] Có thể mở trace từ log hoặc request ID.
- [ ] Span có status, attributes và events đủ để điều tra.
- [ ] Sampling vẫn giữ đủ trace thành công và trace lỗi cho mục tiêu quan sát.
- [ ] Không ghi secret hoặc dữ liệu cá nhân vào trace.
- [ ] Quyền đọc trace và thời hạn lưu giữ được giới hạn phù hợp.
- [ ] Metric latency/error rate được đối chiếu với trace khi có sự cố.

## 15. Tài liệu tham khảo chính thức

- [Cloud Trace documentation](https://cloud.google.com/trace/docs)
- [Set up Cloud Trace](https://cloud.google.com/trace/docs/setup)
- [Trace context and propagation](https://cloud.google.com/trace/docs/trace-context)
- [OpenTelemetry traces concepts](https://opentelemetry.io/docs/concepts/signals/traces/)
- [OpenTelemetry context propagation](https://opentelemetry.io/docs/concepts/context-propagation/)
- [OpenTelemetry Java documentation](https://opentelemetry.io/docs/languages/java/)
- [OpenTelemetry Collector](https://opentelemetry.io/docs/collector/)
- [Google Cloud exporter for OpenTelemetry Collector](https://github.com/GoogleCloudPlatform/opentelemetry-operations-collector)

Khi đưa tracing vào production, hãy kiểm thử một request xuyên suốt từ điểm vào đến dependency cuối cùng. Một trace hữu ích cần có context liên tục, span mang ý nghĩa nghiệp vụ, log liên kết được và sampling phù hợp với tải thực tế. Khi các yếu tố này hoạt động cùng nhau, Cloud Trace giúp nhóm tìm đúng đoạn gây chậm và xác định hướng khắc phục dựa trên bằng chứng.
