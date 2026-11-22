# AWS X-Ray, service map và phân tích distributed trace

Một request đặt hàng trong hệ thống Java Spring Boot có thể đi qua API Gateway, Application Load Balancer, orders-api, DynamoDB, SQS và một Lambda worker gửi email. Người dùng chỉ thấy request mất 4 giây hoặc trả HTTP 500; log của từng service có thể đều ghi “request failed” nhưng chưa chỉ ra chặng nào gây lỗi.

**Distributed tracing** ghi lại đường đi của một request qua nhiều thành phần. AWS X-Ray nhận trace data, ghép các phần có cùng trace ID và tạo service graph để thể hiện service, dependency, latency và lỗi. Trong CloudWatch, bạn có thể mở Trace Map, xem một trace cụ thể, đọc timeline của segment/span và lọc các request có lỗi hoặc thời gian xử lý cao.

Đối với Java, cần lưu ý thay đổi quan trọng: từ **25/02/2026**, AWS X-Ray SDK và X-Ray Daemon đã chuyển sang maintenance mode, chỉ nhận các bản cập nhật để xử lý vấn đề bảo mật. AWS khuyến nghị dùng **OpenTelemetry (OTel) hoặc AWS Distro for OpenTelemetry (ADOT)** để instrument ứng dụng mới và gửi trace tới X-Ray. X-Ray vẫn là nơi xem trace, trace map và dùng X-Ray APIs; thay đổi chính nằm ở cách tạo và chuyển trace data.

Bài học thuộc chương **Quan sát với CloudWatch** của module **CLOUD_PROVIDERS_AWS**. Nội dung tập trung vào mô hình trace, Java/Spring Boot instrumentation, sampling, propagation, service map/trace map, filter expressions và quy trình tìm root cause trong hệ thống phân tán.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích distributed tracing giải quyết vấn đề gì trong hệ thống nhiều service.
2. Phân biệt trace, trace ID, segment, subsegment, span và span context.
3. Mô tả cách X-Ray tạo service graph từ các segment có cùng trace ID.
4. Giải thích inferred segment và quan hệ giữa upstream edge với downstream node.
5. Phân biệt X-Ray Trace Map với CloudWatch Application Map của Application Signals.
6. Instrument Java/Spring Boot bằng ADOT hoặc OpenTelemetry Java agent.
7. Tạo custom span và attributes cho nghiệp vụ cần phân tích.
8. Truyền trace context qua HTTP và các service AWS.
9. Chọn sampling strategy và đánh giá tác động tới chi phí/độ bao phủ.
10. Phân biệt X-Ray annotations với metadata.
11. Đọc node, edge, timeline, response time distribution và error flags.
12. Dùng X-Ray filter expressions để tìm fault, throttle, latency và root cause.
13. Phân tích trace qua SQS, Lambda và các dependency AWS.
14. Tích hợp trace với metrics, logs và Application Signals.
15. Nhận diện trace thiếu segment, context propagation lỗi và instrumentation gaps.
16. Lập kế hoạch chuyển từ X-Ray SDK/Daemon sang OpenTelemetry.

## 2. Distributed tracing là gì?

Trong ứng dụng đơn khối, một request thường đi qua một process nên log và stack trace có thể đủ để tìm lỗi. Trong kiến trúc microservices, request có thể đi qua nhiều process, container, AWS service và queue. Mỗi thành phần có log riêng, đồng hồ và cách đặt request ID khác nhau.

Distributed tracing tạo một định danh xuyên suốt để liên kết hoạt động của các thành phần trong cùng một request logic.

Ví dụ:

    Browser
       |
       v
    API Gateway
       |
       v
    orders-api (Spring Boot)
       |                 \
       v                  v
    DynamoDB              SQS
                             |
                             v
                       invoice-worker (Lambda)
                             |
                             v
                         S3 / SES

Một trace cho request đặt hàng có thể gồm thời gian API Gateway chuyển request, thời gian orders-api kiểm tra dữ liệu, thời gian gọi DynamoDB, thời gian gửi message tới SQS và trace liên kết tới Lambda consumer nếu propagation được hỗ trợ và cấu hình đúng.

Trace giúp trả lời: request chậm ở service nào, dependency nào đang lỗi, thời gian chờ nằm ở đâu và lỗi bắt đầu từ đâu.

### 2.1. Log, metric và trace bổ sung cho nhau

| Tín hiệu | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Logs | Điều gì đã xảy ra? | Exception, business event, request data đã mask |
| Metrics | Xu hướng và mức độ ảnh hưởng? | Error rate, request count, p95 latency |
| Traces | Một request đã đi qua đâu và mất thời gian ở đâu? | orders-api chờ DynamoDB 1,8 giây |
| Events | Có thay đổi nào xảy ra cùng thời điểm? | Deployment, scaling, configuration change |

Metric/Alarm phát hiện vấn đề; trace chỉ ra đường đi của request; log cung cấp chi tiết để hiểu nguyên nhân. Không tín hiệu nào thay thế hoàn toàn tín hiệu còn lại.

## 3. Mô hình dữ liệu của AWS X-Ray

X-Ray dùng các khái niệm chính sau:

| Khái niệm | Ý nghĩa |
|---|---|
| Trace | Tập hợp dữ liệu về một request logic, được liên kết bằng trace ID |
| Trace ID | Định danh chung của request qua nhiều service |
| Segment | Dữ liệu một service gửi về phần công việc mà service đó thực hiện |
| Subsegment | Phần chi tiết của segment, thường mô tả lời gọi downstream hoặc một đoạn xử lý |
| Service graph | Đồ thị các service/resource và kết nối được suy ra từ traces |
| Trace Map | Giao diện trực quan hóa service graph và thông tin vận hành |
| Annotation | Key-value được index để lọc trace |
| Metadata | Dữ liệu bổ sung không được index để tìm kiếm |

Một segment thường chứa tên service/resource, thông tin request/response, thời điểm bắt đầu/kết thúc, subsegments và thông tin lỗi/exception. Một subsegment có thể ghi lại lời gọi tới AWS service, HTTP API bên ngoài, SQL database hoặc một đoạn code do ứng dụng tự instrument.

### 3.1. Trace ID và parent-child relationship

Trace ID liên kết các segment/span của cùng một request. Mỗi segment hoặc span có ID riêng và có thể tham chiếu parent để biểu diễn quan hệ gọi nhau.

    Trace: request-123
       |
       +-- API Gateway segment
       |
       +-- orders-api segment
              |
              +-- validate-order span
              |
              +-- DynamoDB subsegment/span
              |
              +-- SQS SendMessage subsegment/span

Nếu context propagation bị mất, service phía sau có thể tạo trace mới hoặc span không có parent đúng. Khi đó trace map không còn thể hiện đầy đủ một luồng nghiệp vụ.

## 4. Segment, subsegment và inferred segment

**Segment** đại diện cho công việc mà một service thực hiện khi xử lý request. Với HTTP server, segment có thể ghi method, URL, response status, thời gian xử lý và exception.

**Subsegment** cung cấp góc nhìn của service gọi downstream. Ví dụ orders-api gọi DynamoDB bằng AWS SDK, instrumentation ghi subsegment cho lời gọi đó. Subsegment có thể chứa AWS service/operation, round-trip time, kết quả, throttling hoặc exception.

**Inferred segment** xuất hiện khi downstream service/resource không gửi segment riêng. X-Ray có thể tạo inferred segment dựa trên subsegment của service gọi để thể hiện dependency đó trên trace map.

Nếu downstream service được instrument và gửi segment riêng, node service graph dùng dữ liệu segment của downstream; edge giữa hai node vẫn dùng thông tin subsegment từ phía caller. Hai góc nhìn bổ sung cho nhau:

- Downstream segment cho biết thời gian service thực sự xử lý.
- Upstream subsegment cho biết thời gian round-trip mà caller phải chờ, gồm network và thời gian chờ khác.

Không nhầm inferred segment với bằng chứng rằng bạn đã instrument được code bên trong AWS service.

## 5. Service graph và Trace Map

X-Ray nhóm các segment có cùng trace ID để tạo service graph. Mỗi node biểu diễn một service/resource; edge biểu diễn quan hệ gọi giữa chúng.

Trace Map giúp operator nhìn thấy topology và dependency, xác định service có error/fault/throttle, phát hiện edge có latency cao, lọc trace đi qua node/edge cụ thể và mở timeline của một request.

Tên service nên ổn định và có ý nghĩa. Nếu mỗi instance tự tạo một tên khác nhau, map sẽ có quá nhiều node và khó phân tích. Dùng logical service name như orders-api, payment-service, invoice-worker; thông tin instance, pod, task hoặc version nên thể hiện bằng resource attributes phù hợp.

### 5.1. Màu sắc và trạng thái

Trong CloudWatch X-Ray Trace Map, viền node thể hiện loại vấn đề:

| Màu | Ý nghĩa |
|---|---|
| Đỏ | Server fault, HTTP 5xx |
| Vàng | Client error, HTTP 4xx |
| Tím | Throttling, HTTP 429 |

Service map cũ trong X-Ray console có thể hiển thị màu xanh cho request thành công. Khi thao tác trên CloudWatch Trace Map, hãy dùng legend của giao diện hiện tại để diễn giải màu. Màu node là tín hiệu định hướng; hãy mở node/edge, xem metrics và trace cụ thể để xác định nguyên nhân.

## 6. Trace Map và Application Map khác nhau thế nào?

CloudWatch có hai trải nghiệm map liên quan nhưng phục vụ các góc nhìn khác nhau:

| Giao diện | Mục đích |
|---|---|
| **X-Ray Trace Map** | Service graph được tạo từ trace data; drill down từ node/edge tới trace và segment timeline |
| **Application Signals Application Map** | Bản đồ ứng dụng theo service, client, canary và dependency; hiển thị SLI/SLO health và operational metrics |

Trace Map tập trung vào dữ liệu trace và đường đi của request. Application Map thuộc Application Signals, phù hợp theo dõi sức khỏe dịch vụ, SLO và topology theo góc nhìn ứng dụng.

Application Signals có thể liên kết service operation metrics với X-Ray traces, CloudWatch logs và Container Insights. Từ một điểm metric bất thường, operator có thể mở trace liên quan để tìm root cause.

Không giả định mọi node trong Application Map đều có trace chi tiết. Một service chưa được instrument có thể xuất hiện với dữ liệu telemetry hạn chế.

## 7. Tình trạng AWS X-Ray SDK và Daemon trong năm 2026

AWS thông báo X-Ray SDKs và X-Ray Daemon chuyển sang **maintenance mode từ 25/02/2026**. Trong chế độ này, AWS giới hạn release chủ yếu cho các vấn đề bảo mật; các SDK/Daemon không còn là hướng phát triển instrumentation mới được khuyến nghị.

AWS khuyến nghị:

- Dùng OpenTelemetry SDKs hoặc ADOT instrumentation để tạo trace.
- Dùng OpenTelemetry Collector hoặc CloudWatch Agent để nhận, xử lý và chuyển trace.
- Tiếp tục dùng X-Ray làm trace backend và xem dữ liệu trên CloudWatch Trace Map/Traces.
- Dùng Application Signals nếu cần góc nhìn service health, metrics và SLO.

Điều này không có nghĩa X-Ray service ngừng hoạt động. Trace data từ OpenTelemetry vẫn có thể được chuyển thành X-Ray segments/subsegments và hiển thị trong CloudWatch.

### 7.1. Ánh xạ khái niệm X-Ray sang OpenTelemetry

| X-Ray | OpenTelemetry |
|---|---|
| Recorder | Tracer Provider và Tracer |
| Segment | Server span |
| Subsegment | Non-server span |
| Annotation/Metadata | Span attributes |
| Sampling rules | Sampler |
| Emitter | Span exporter |
| Trace context | Span context |
| X-Ray Daemon | OpenTelemetry Collector hoặc CloudWatch Agent |
| Service plugin | Resource detector |

Khi xuất trace tới X-Ray, server spans được chuyển thành segments; các span khác được chuyển thành subsegments. OpenTelemetry attributes mặc định được chuyển thành metadata trong raw X-Ray data. Có thể đánh dấu một số attribute thành annotation theo cấu hình X-Ray exporter.

## 8. Kiến trúc tracing hiện đại cho Java trên AWS

Một mô hình triển khai phổ biến:

    Spring Boot application
       |
       | OpenTelemetry Java agent / SDK
       | HTTP + OTLP
       v
    ADOT Collector hoặc CloudWatch Agent
       |
       | Batch / process / export
       v
    AWS X-Ray
       |
       +--> CloudWatch X-Ray Trace Map
       +--> CloudWatch Traces
       +--> Application Signals (nếu bật)

Ứng dụng tạo spans và gắn context. Collector nhận OTLP, batch và gửi trace tới X-Ray. Collector có thể đặt cạnh application hoặc chạy tập trung tùy compute platform, network và vận hành.

### 8.1. Chọn auto-instrumentation hay manual instrumentation

| Cách | Ưu điểm | Khi phù hợp |
|---|---|---|
| ADOT/OpenTelemetry Java agent | Instrument HTTP server, client, JDBC và framework được hỗ trợ với ít thay đổi code | Bắt đầu tracing Spring Boot nhanh |
| OpenTelemetry Spring Boot starter | Tích hợp theo dependency và cấu hình ứng dụng | Muốn kiểm soát instrumentation trong application |
| OpenTelemetry SDK API | Tạo span cho logic nghiệp vụ riêng | Cần đo đoạn code hoặc business workflow đặc thù |
| X-Ray SDK cũ | Tương thích ứng dụng đang dùng | Duy trì trong thời gian migration có kiểm soát |

Với dự án mới, ưu tiên ADOT/OpenTelemetry. Chỉ thêm manual spans cho phần nghiệp vụ chưa được auto-instrumentation bao phủ; tránh tạo span trùng lặp cho cùng một HTTP/DB call.

## 9. Auto-instrumentation Java với ADOT

ADOT cung cấp Java auto-instrumentation agent dựa trên OpenTelemetry. Agent có thể tự động instrument các framework/library được hỗ trợ bằng bytecode instrumentation.

Ví dụ chạy một Spring Boot JAR với agent:

    java \
      -javaagent:/opt/aws-opentelemetry-agent.jar \
      -Dotel.service.name=orders-api \
      -Dotel.resource.attributes=deployment.environment.name=prod,service.version=1.4.2 \
      -Dotel.exporter.otlp.endpoint=http://127.0.0.1:4317 \
      -Dotel.exporter.otlp.protocol=grpc \
      -jar orders-api.jar

Đây là ví dụ khi Collector/CloudWatch Agent đang nhận OTLP gRPC ở localhost:4317. Nếu collector chạy ở host/task khác, thay endpoint bằng địa chỉ reachable trong network.

Các thuộc tính quan trọng:

- service.name: tên logic của service.
- deployment.environment.name: môi trường triển khai.
- service.version: phiên bản ứng dụng.
- OTLP endpoint/protocol: nơi agent gửi spans.
- Propagators: định dạng context được inject/extract giữa các service.

Tên file agent, version và cấu hình thực tế phụ thuộc bản ADOT Java agent bạn đóng gói. Pin version agent và kiểm tra compatibility với JDK, Spring Boot và instrumentation libraries.

### 9.1. Propagators

OpenTelemetry thường dùng W3C Trace Context với header `traceparent` và `tracestate`. X-Ray dùng header `X-Amzn-Trace-Id`.

Nếu cần tương tác với AWS services hoặc hệ thống đã dùng X-Ray header, cấu hình X-Ray propagator phù hợp trong ADOT/OpenTelemetry setup. Một cấu hình có thể cần các propagators như `tracecontext,baggage,xray`; xác nhận agent/distribution đang dùng có extension tương ứng.

Không tự tạo trace ID mới ở mỗi service. Hãy extract parent context từ request đến, tạo child span và inject context vào request đi.

## 10. Collector nhận và gửi trace tới X-Ray

ADOT Collector hoặc OpenTelemetry Collector có thể nhận OTLP rồi dùng AWS X-Ray exporter.

Ví dụ cấu hình collector rút gọn:

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
      awsxray:

    service:
      pipelines:
        traces:
          receivers: [otlp]
          processors: [batch]
          exporters: [awsxray]

Đây là cấu hình khung. Các component có trong distribution, endpoint, region, TLS và authentication phụ thuộc bản Collector/ADOT đang triển khai. Kiểm tra cấu hình với schema của phiên bản thực tế trước khi deploy.

Collector có thể thực hiện thêm resource detection để thêm metadata ECS/EC2/EKS, batch processing để giảm overhead export, filtering để loại health check hoặc dữ liệu không cần thiết, retry/queue để xử lý lỗi export có kiểm soát và tail sampling nếu cần quyết định giữ trace sau khi thấy toàn bộ trace.

### 10.1. IAM cho trace exporter

Role của Collector/CloudWatch Agent cần quyền gửi trace tới X-Ray, thường gồm:

- `xray:PutTraceSegments`
- `xray:PutTelemetryRecords`

Nếu cấu hình remote sampling bằng X-Ray sampling rules, cần thêm quyền đọc sampling rules/targets/statistics tương ứng. Chỉ cấp quyền thực sự được exporter/sampler sử dụng.

Ưu tiên IAM role của EC2, ECS task, EKS workload identity hoặc Lambda execution role thay access key dài hạn. Không đưa credential vào collector config.

## 11. Manual instrumentation trong Java

Auto-instrumentation không hiểu mọi business step. Bạn có thể tạo span cho nghiệp vụ quan trọng như reserve inventory, calculate shipping hoặc validate payment.

Ví dụ với OpenTelemetry API:

    import io.opentelemetry.api.GlobalOpenTelemetry;
    import io.opentelemetry.api.trace.Span;
    import io.opentelemetry.api.trace.StatusCode;
    import io.opentelemetry.context.Scope;

    public class OrderService {
        private final Tracer tracer =
            GlobalOpenTelemetry.getTracer("orders-api");

        public void reserveInventory(String orderType) {
            Span span = tracer.spanBuilder("inventory.reserve").startSpan();

            try (Scope scope = span.makeCurrent()) {
                span.setAttribute("order.type", orderType);
                inventoryClient.reserve();
            } catch (RuntimeException ex) {
                span.recordException(ex);
                span.setStatus(StatusCode.ERROR, "Inventory reservation failed");
                throw ex;
            } finally {
                span.end();
            }
        }
    }

Đoạn code minh họa tạo child span trong context hiện hành. Trong ứng dụng thật, inject Tracer qua cấu hình/bean nếu phù hợp và không khởi tạo một TracerProvider riêng nếu Java agent đã quản lý global provider.

### 11.1. Đặt tên span có ý nghĩa

Tên span nên mô tả operation, không chứa dữ liệu biến thiên:

- Tốt: `orders.reserve`, `payment.authorize`, `inventory.lookup`.
- Không tốt: `orders/12345`, `GET /users/987654` nếu path chứa ID động, `query-customer-email@example.com`.

Tên ổn định giúp aggregate latency/error theo operation và tránh cardinality bùng nổ.

### 11.2. Attributes, annotations và metadata

OpenTelemetry span attributes là key-value metadata. Khi chuyển sang X-Ray:

- Attribute mặc định được ghi thành metadata.
- Attribute được liệt kê trong `aws.xray.annotations` có thể trở thành annotation để lọc.
- Chọn annotation cho các field có giá trị tìm kiếm, như order tier hoặc region group.
- Dùng metadata cho thông tin chi tiết không cần index.

Ví dụ đánh dấu attribute thành X-Ray annotation:

    import io.opentelemetry.api.common.AttributeKey;
    import java.util.List;

    span.setAttribute("order.tier", "premium");
    span.setAttribute(
        AttributeKey.stringArrayKey("aws.xray.annotations"),
        List.of("order.tier")
    );

X-Ray index tối đa 50 annotations trên một trace. Chọn key có ích cho điều tra và giữ cardinality hợp lý. Không đưa password, access token, email, số thẻ hoặc payload nhạy cảm vào annotation/metadata.

## 12. Propagate trace context qua HTTP

Một trace chỉ hữu ích khi các service liên kết được spans của chúng. Với HTTP, instrumentation thường tự inject/extract context.

    orders-api
       |
       | traceparent / X-Amzn-Trace-Id
       v
    payment-service
       |
       | trace context
       v
    fraud-check-service

Cần chú ý:

- Cả hai service phải dùng propagator tương thích.
- Proxy/load balancer phải giữ header cần thiết.
- HTTP client phải được instrument hoặc inject context.
- Không tạo root trace mới khi đã có valid parent context.
- Không ghi đè context giữa chừng nếu không có lý do rõ ràng.
- Với async execution, context phải được propagate qua executor/reactive boundary.

Trace context không phải cơ chế xác thực. Không dùng trace ID để cấp quyền hoặc định danh người dùng.

### 12.1. Tin cậy header từ client bên ngoài

X-Ray tracing header có thể đến từ SDK, AWS service hoặc client request. Một client không tin cậy có thể tự gửi trace ID/sampling decision. Với request public, thiết kế ingress cần kiểm soát việc nhận hoặc loại bỏ header do client tự cung cấp theo hướng dẫn AWS và yêu cầu tracing của hệ thống.

Không cho phép client quyết định tùy ý sampling hoặc tạo trace context giả để làm sai lệch telemetry. Giữ trace context nội bộ nhất quán sau khi ingress đã xác định parent/root context.

## 13. Trace context trong SQS và xử lý bất đồng bộ

HTTP request và message queue có vòng đời khác nhau. Một message có thể được tạo ở service A và xử lý nhiều giây/phút sau bởi Lambda hoặc worker B.

Khi service gửi message:

1. Instrumentation tạo span cho thao tác publish.
2. Trace context được truyền bằng cơ chế propagation mà integration hỗ trợ.
3. Consumer extract context khi nhận message.
4. Consumer tạo span xử lý message liên kết với trace cha hoặc span link theo mô hình phù hợp.
5. Trace map có thể thể hiện quan hệ producer/consumer nếu các integration và trace data hỗ trợ.

CloudWatch X-Ray Trace Map có thể hiển thị connected view cho event-driven flow dùng SQS và Lambda; quan hệ producer/consumer có thể được thể hiện bằng dashed edge.

Nếu consumer không nhận context, trace có thể bị tách. Kiểm tra message attributes/system attributes và khả năng propagation của SDK/runtime đang dùng; đừng tự giả định mọi queue/client version đều truyền context giống nhau.

## 14. Sampling: chọn request nào được trace

Trace mọi request có thể tăng chi phí, lưu lượng export và dung lượng telemetry. Sampling chọn một phần request đại diện.

Hai cách phổ biến:

- **Head sampling:** quyết định ở đầu trace, trước khi biết toàn bộ kết quả. Nhanh và ít tốn bộ nhớ.
- **Tail sampling:** collector đợi đủ trace rồi quyết định giữ/bỏ dựa trên lỗi, latency hoặc thuộc tính. Có thể ưu tiên giữ trace lỗi/chậm nhưng cần state, memory và routing phù hợp.

### 14.1. X-Ray SDK default sampling

Tài liệu X-Ray SDK mô tả default sampling rule cũ là:

- Giữ request đầu tiên mỗi giây.
- Giữ thêm 5% các request còn lại.

Đây là default của X-Ray SDK, không phải default chung cho mọi OpenTelemetry SDK/ADOT agent. Khi dùng OTel, sampling phụ thuộc sampler và cấu hình bạn triển khai.

### 14.2. Parent-based sampling

Sampling thường phải tôn trọng quyết định của root/parent span. Nếu service đầu tiên đã quyết định sampled=false, downstream services thường kế thừa quyết định đó.

Một rule chỉ đặt ở service downstream có thể không có tác dụng nếu request luôn đến từ parent đã quyết định sampling. Hãy đặt sampling policy ở điểm bắt đầu trace hoặc cấu hình parent-based sampler đúng ý định.

### 14.3. Thiết kế sampling policy

| Traffic | Cách cân nhắc |
|---|---|
| Transaction thay đổi trạng thái | Tỷ lệ cao hơn hoặc ưu tiên theo business risk |
| Read API traffic rất lớn | Sample thấp hơn nhưng đủ đại diện |
| Health check/heartbeat | Sample rất thấp hoặc loại bỏ |
| Error/latency bất thường | Tail sampling có thể giữ trace lỗi/chậm |
| Internal background jobs | Sampling theo volume và giá trị điều tra |

Sampling không nên thay metrics. Dù trace bị sample, hãy giữ request/error/latency metrics đủ đầy để đo SLO.

## 15. Đọc Trace Map trong CloudWatch

Trong AWS Console:

1. Chọn đúng account và Region.
2. Mở CloudWatch.
3. Trong phần X-Ray traces, chọn **Trace Map**.
4. Chọn time range bao phủ sự cố.
5. Chọn node service hoặc edge cần điều tra.
6. Xem metrics, alerts và response time distribution.
7. Chọn View traces hoặc View filtered traces để mở danh sách trace.
8. Chọn một trace ID để mở Trace details.
9. Dùng View logs nếu node hỗ trợ để chuyển sang log liên quan.

Node cho biết service/resource. Edge cho biết lời gọi giữa hai node. Nếu node đỏ nhưng edge bình thường, lỗi có thể nằm trong xử lý nội bộ của service. Nếu edge tới dependency có latency cao hoặc throttle, kiểm tra dependency đó.

Trace Map có thể hỗ trợ cross-account tracing nếu cấu hình CloudWatch/X-Ray và quyền truy cập phù hợp.

### 15.1. Chọn node hay edge?

- Chọn **node** khi muốn xem các request đi qua service cụ thể.
- Chọn **edge** khi nghi ngờ một dependency call có vấn đề.
- Lọc theo lỗi để tìm request thất bại.
- Lọc theo response time distribution để tìm nhóm request chậm.
- Chuyển từ map sang trace details để xác định segment/subsegment cụ thể.

Một service map lớn có thể khó đọc. Zoom, filter theo group và thu hẹp time range để tập trung vào phần topology liên quan.

## 16. Đọc Trace details và timeline

Trace details thường gồm Trace Map của các node liên quan tới request, trace summary với URL/operation, response code, duration và thời điểm, segments timeline thể hiện thời lượng từng segment/subsegment, cùng details chứa metadata, annotations, exception và downstream call.

Ví dụ timeline:

    0 ms       orders-api server span bắt đầu
    12 ms      validate-order hoàn tất
    20 ms      DynamoDB GetItem bắt đầu
    1,420 ms   DynamoDB GetItem kết thúc
    1,440 ms   SQS SendMessage bắt đầu
    1,470 ms   SQS SendMessage kết thúc
    1,510 ms   orders-api trả HTTP 201

Nếu DynamoDB chiếm gần toàn bộ thời gian, kiểm tra latency, throttling, retries, hot partition, connection pool và network. Nếu span nội bộ chiếm thời gian lớn nhưng không có child spans, bổ sung instrumentation vào đoạn code đó.

Không cộng duration của các span lồng nhau để suy ra request duration. Parent span thường bao phủ thời gian của child span; cộng tất cả sẽ đếm trùng thời gian.

## 17. X-Ray filter expressions

X-Ray có filter expression language để lọc traces theo lỗi, thời gian, service, edge, annotation và thuộc tính request.

### 17.1. Lọc lỗi

Tìm trace có server fault:

    fault

Tìm client error:

    error

Tìm throttling:

    throttle

Tìm trace không thành công:

    !ok

Các keyword này mô tả trạng thái trace ở mức request. Một downstream error đã được ứng dụng xử lý và không làm request gốc thất bại có thể không xuất hiện khi chỉ tìm error. Khi đó hãy lọc service/edge cụ thể.

### 17.2. Lọc theo thời gian và status

Tìm request có response time lớn hơn 2 giây:

    responsetime > 2

Tìm request có tổng duration từ 3 tới 8 giây:

    duration >= 3 AND duration <= 8

Tìm status code khác 200:

    http.status != 200

Tìm URL path:

    http.url CONTAINS "/orders/"

X-Ray filter expression dùng giây cho responsetime/duration. Đọc tài liệu cú pháp trước khi copy các toán tử vào query thực tế.

### 17.3. Lọc theo service và edge

Tìm trace có fault tại orders-api:

    service("orders-api") { fault }

Tìm trace có throttling trên edge giữa caller và dependency:

    edge("orders-api", "DynamoDB") { throttle }

Tên service/destination phải khớp tên node trong trace graph của môi trường. Nếu node có tên AWS service type hoặc ARN, chọn đúng tên hiển thị và kiểm tra filter expression syntax.

### 17.4. Lọc theo annotation

Nếu ứng dụng ghi annotation `tenantTier`, có thể tìm trace thuộc nhóm premium:

    annotation.tenantTier = "premium"

Với annotation key chứa dấu chấm, dùng cú pháp bracket theo tài liệu filter expressions.

Chỉ những field được ghi thành annotation mới có thể được filter như annotation. Metadata không được index nên không dùng thay annotation để tìm kiếm.

### 17.5. Root cause filter

Có thể lọc theo root cause service/exception. Ví dụ tìm trace fault có root cause liên quan một service cụ thể:

    rootcause.fault.service { name = "payment-service" }

Root cause analysis hỗ trợ thu hẹp node hoặc exception có đóng góp vào fault/latency. Kết quả vẫn cần được xác nhận bằng timeline và log.

## 18. X-Ray groups

Groups là tập trace được xác định bằng filter expression. Mỗi group có thể tạo service graph, trace summaries và CloudWatch metrics riêng.

Ví dụ nhóm request có lỗi thanh toán:

    service("payment-service") { fault OR error }

Groups phù hợp để theo dõi một luồng nghiệp vụ hoặc nhóm dependency cụ thể mà đội vận hành thường xuyên quan tâm.

Lưu ý:

- Group áp dụng cho trace mới khi X-Ray tiếp nhận dữ liệu.
- Thay filter expression không sửa lại dữ liệu đã được lưu trước đó.
- Thay đổi filter có thể làm graph gộp dữ liệu theo tiêu chí cũ/mới.
- Group có thể phát sinh chi phí theo số trace được truy xuất phù hợp.

Không tạo quá nhiều group trùng lặp. Chỉ duy trì nhóm có owner và mục đích điều tra rõ ràng.

## 19. Phân tích latency: tìm critical path

Khi request chậm, hãy bắt đầu từ tổng duration rồi lần theo các span/subsegment dài nhất.

1. Chọn trace có duration cao hoặc vượt SLO.
2. Xem root/server span và tổng request duration.
3. Tìm child span chiếm phần lớn thời gian.
4. Xác định thời gian là xử lý CPU, chờ network, chờ connection pool hay downstream service.
5. Mở subsegment/edge để xem AWS operation và resource.
6. Đối chiếu metric/log cùng thời điểm.
7. So sánh trace nhanh và trace chậm của cùng operation.

Một số pattern thường gặp:

| Dấu hiệu trong trace | Hướng điều tra |
|---|---|
| Một DynamoDB subsegment rất dài | Throttling, hot key, retry, network hoặc capacity |
| Nhiều lần gọi cùng một API | N+1 calls, retry lồng nhau hoặc loop |
| HTTP client span dài nhưng server span ngắn | Network, queueing hoặc chờ phía client |
| JDBC span dài | Query plan, lock, connection pool, DB load |
| Lambda span có phần init lớn | Cold start, runtime initialization, package size |
| Parent span dài nhưng thiếu child spans | Instrumentation gap hoặc đoạn code chưa được instrument |
| Nhiều service cùng chậm | Shared dependency, network path hoặc tải hệ thống |

Đừng mặc định span dài nhất luôn là root cause. Span có thể bao gồm chờ queue/network hoặc bao phủ child spans. Đối chiếu các khoảng thời gian và góc nhìn caller/callee.

## 20. Phân tích lỗi: fault, error và throttle

X-Ray phân loại trạng thái lỗi:

| Trạng thái | Ý nghĩa |
|---|---|
| Error | Client error, thường là HTTP 4xx |
| Fault | Server fault, thường là HTTP 5xx |
| Throttle | Throttling, thường là HTTP 429 |

Một lỗi ở downstream có thể được xử lý và retry thành công trước khi trả response. Trace root có thể không mang fault dù subsegment vẫn cho thấy dependency call thất bại. Vì vậy:

- Kiểm tra cả root segment và subsegments.
- Tìm service/edge có error/throttle.
- Xem exception và AWS error code.
- Đối chiếu retry metrics và logs.
- Kiểm tra request có bị retry nhiều lần trước khi thành công không.

Nếu chỉ lọc root fault, bạn có thể bỏ sót dependency failure đã được xử lý bên trong request.

## 21. Phân tích AWS SDK calls

Với Java service gọi AWS SDK for Java 2.x, instrumentation có thể tạo spans/subsegments cho các lời gọi DynamoDB, S3, SQS, Secrets Manager và các AWS service được hỗ trợ.

Khi dependency span bất thường, kiểm tra service/operation name, AWS Region/endpoint, resource ARN/table/bucket/queue nếu được ghi, error code/HTTP status/request ID nếu instrumentation có, retry attempts/total latency, throttling/service-side errors, credentials refresh, DNS, VPC endpoint và connection pool.

Không ghi request/response body hoặc credentials chỉ để có thêm thông tin trace. Attributes cần vừa đủ để phân loại lỗi và truy vết.

## 22. Kết hợp traces với CloudWatch Application Signals

Application Signals cung cấp góc nhìn service-centric cho application health:

- Services page cho biết service có latency/fault cao.
- Service detail hiển thị volume, availability, latency, faults/errors và dependencies.
- Application Map cho thấy client, service và dependency topology.
- SLO/SLI cho biết service có đáp ứng mục tiêu độ tin cậy không.
- Correlated traces cho phép mở X-Ray trace details từ metric point bất thường.
- Correlated logs giúp xem log liên quan tới service operation.

Workflow điều tra:

    Application Signals Services
          |
          v
    Service operation có latency/error bất thường
          |
          v
    Chọn metric data point
          |
          v
    Correlated traces + logs
          |
          v
    Mở X-Ray Trace details
          |
          v
    Phân tích segment timeline và dependency edge

Application Signals hỗ trợ Java và một số runtime khác trên các compute platforms được AWS tài liệu hóa. Kiểm tra platform, Region và yêu cầu cấu hình trước khi bật. Application Signals có chi phí riêng và có thể cần agent/permissions bổ sung.

## 23. CLI và X-Ray APIs

Có thể tìm trace bằng AWS CLI hoặc gọi X-Ray APIs trong automation.

Lấy trace summaries theo thời gian và filter expression:

    aws xray get-trace-summaries \
      --start-time <START_EPOCH_SECONDS> \
      --end-time <END_EPOCH_SECONDS> \
      --filter-expression 'fault'

Kết quả chứa trace IDs và summary fields. Dùng các trace IDs để lấy đầy đủ trace:

    aws xray batch-get-traces \
      --trace-ids <TRACE_ID_1> <TRACE_ID_2>

Các API quan trọng:

| API | Mục đích |
|---|---|
| GetTraceSummaries | Tìm trace IDs và summaries theo time range/filter |
| BatchGetTraces | Lấy segment documents của một hoặc nhiều traces |
| GetServiceGraph | Lấy service graph theo time range/group |
| GetTraceGraph | Lấy graph của một trace cụ thể |
| GetGroups | Liệt kê X-Ray groups |
| GetSamplingRules | Đọc sampling rules |

Thời gian start/end của X-Ray APIs được truyền dưới dạng Unix epoch seconds. Kiểm tra pagination token và giới hạn kết quả; không giả định một API response luôn chứa mọi trace trong time range.

IAM role cần quyền read-only tương ứng như xray:GetTraceSummaries, xray:BatchGetTraces, xray:GetServiceGraph hoặc xray:GetTraceGraph theo workflow. Chỉ cấp API thực sự được automation sử dụng.

## 24. Trace ID formats và tương thích W3C

X-Ray trace ID thường có định dạng:

    1-<8-hex-timestamp>-<24-hex-unique-id>

W3C Trace Context dùng trace ID 32 ký tự hex, cùng traceparent header. OpenTelemetry có thể tạo trace ID theo W3C format và X-Ray console có thể hiển thị trace ID W3C dưới dạng X-Ray tương ứng khi truy vấn.

Ví dụ W3C trace ID:

    4efaaf4d1e8720b39541901950019ee5

X-Ray equivalent:

    1-4efaaf4d-1e8720b39541901950019ee5

Khi correlate log, trace và support ticket, ghi nhận đúng định dạng mà hệ thống trả về. Không cắt trace ID thành một chuỗi ngắn có thể gây collision.

## 25. Cross-account và event-driven tracing

Trace có thể đi qua nhiều AWS accounts nếu cấu hình cross-account observability và quyền truy cập phù hợp. Trace Map/Traces hỗ trợ hiển thị dữ liệu từ nhiều account trong cùng một góc nhìn.

Với hệ thống event-driven:

- Producer tạo message và trace context.
- SQS nhận message.
- Lambda hoặc worker xử lý message.
- Consumer tạo spans cho processing và downstream calls.
- Trace map có thể liên kết producer/consumer khi instrumentation và propagation hỗ trợ.

Nếu trace dừng tại SQS, kiểm tra consumer instrumentation, message context, quyền gửi trace và thời điểm export. Không kết luận queue làm mất trace chỉ vì trace map không hiện edge; có thể sampling hoặc integration chưa tạo dữ liệu tương ứng.

## 26. Những lý do trace không đầy đủ

Một trace có thể thiếu segment/span vì:

1. Một service chưa được instrument.
2. Một thư viện hoặc protocol chưa được auto-instrumentation hỗ trợ.
3. Trace context không được inject/extract đúng.
4. Sampling quyết định bỏ trace ở root.
5. Async task không truyền context.
6. Collector không nhận hoặc không export được spans.
7. Application/collector kết thúc trước khi flush.
8. IAM hoặc network chặn export.
9. Resource/service name không nhất quán.
10. Query time range hoặc filter expression không bao phủ trace.

### 26.1. Kiểm tra theo thứ tự

- Xác nhận ứng dụng tạo span ở local/test environment.
- Kiểm tra agent startup log và version compatibility.
- Kiểm tra OTLP receiver endpoint/protocol.
- Kiểm tra Collector pipeline có traces receiver, processor và exporter.
- Kiểm tra IAM permissions của collector role.
- Kiểm tra network/security group/VPC endpoint tới collector hoặc AWS.
- Kiểm tra sampling decision ở root.
- Kiểm tra traceparent/X-Amzn-Trace-Id giữa các service.
- Kiểm tra time range và Region trong CloudWatch.

Không bật debug log toàn bộ trong production lâu dài; telemetry exporter có thể ghi thông tin nội bộ và làm tăng log volume.

## 27. Bảo mật và chất lượng dữ liệu trace

Trace data có thể chứa URL, user ID, resource ARN, exception message và custom attributes. Vì vậy:

- Không ghi password, token, cookie, authorization header hoặc private key.
- Không đưa email, số điện thoại hoặc dữ liệu thanh toán vào annotation.
- Mask hoặc pseudonymize identifier nếu cần liên kết nghiệp vụ.
- Dùng service role least privilege cho PutTraceSegments/telemetry và read APIs.
- Hạn chế ai được xem traces/logs có dữ liệu nhạy cảm.
- Kiểm soát X-Ray groups/filter để tránh truy xuất không cần thiết.
- Chọn retention và sampling theo yêu cầu audit/incident.
- Không dùng trace context như cơ chế xác thực hoặc authorization.

X-Ray có thể ghi client IP từ X-Forwarded-For khi request đi qua proxy/load balancer. Header này có thể bị giả mạo nếu trust boundary không được cấu hình đúng; không dùng nó làm bằng chứng danh tính.

## 28. Chi phí, retention và sampling

Trace có chi phí ingest/retrieval và có thể làm tăng chi phí của collector, CloudWatch và X-Ray. Trước khi bật tracing 100%, hãy xác định volume request, span count mỗi request, sampling, retention và nhóm người dùng cần truy cập.

Các nguyên tắc:

- Bắt đầu với sampling có kiểm soát.
- Giữ tỷ lệ trace cao hơn cho luồng nghiệp vụ rủi ro nếu ngân sách cho phép.
- Giảm tracing cho health checks và traffic lặp lại có giá trị thấp.
- Dùng tail sampling khi cần ưu tiên lỗi/chậm và collector đủ tài nguyên.
- Tránh tạo quá nhiều custom spans cho từng dòng code.
- Giới hạn attributes và metadata.
- Theo dõi dropped spans, exporter errors và collector queue.
- Dùng metrics để theo dõi toàn bộ traffic; trace chỉ là mẫu nếu sampling bật.

Theo tài liệu X-Ray, trace data được giữ 30 ngày. Nếu cần lưu trữ dài hạn hoặc audit, thiết kế giải pháp archive/analytics riêng phù hợp chính sách dữ liệu và chi phí.

## 29. Kế hoạch migration từ X-Ray SDK/Daemon sang OpenTelemetry

Với ứng dụng Java đang dùng X-Ray SDK, nên chuyển theo từng bước:

1. Inventory các service đang dùng X-Ray SDK, Java agent và Daemon.
2. Ghi lại instrumentation đang có: HTTP, Spring, AWS SDK v2, JDBC và custom subsegments.
3. Chọn ADOT Java agent hoặc OpenTelemetry Java agent/SDK.
4. Chọn Collector hoặc CloudWatch Agent làm trace receiver/exporter.
5. Cấu hình resource attributes, propagators, sampling và exporter.
6. Kiểm tra quyền IAM và network.
7. Chạy staging, so sánh trace coverage, latency và service graph.
8. Chuyển từng service theo rollout.
9. Kiểm tra trace propagation xuyên các service cũ/mới.
10. Loại bỏ X-Ray SDK/Daemon sau khi không còn dependency và xác nhận không còn port conflict.

### 29.1. Tránh dual instrumentation

Nếu đồng thời bật X-Ray Java agent cũ và OTel Java agent cho cùng HTTP/JDBC/AWS SDK calls, có thể tạo span trùng hoặc parent-child relationships sai. Trong giai đoạn migration, chọn rõ instrumentation owner cho từng thư viện.

Nếu thay X-Ray Daemon bằng CloudWatch Agent hoặc OTel Collector, dừng Daemon cũ theo quy trình để tránh xung đột port/receiver. Không chạy hai collector nhận cùng một trace stream nếu chưa có mục tiêu rõ ràng.

### 29.2. Tương thích trong thời gian chuyển đổi

X-Ray và OpenTelemetry có thể cùng xuất hiện trong một hệ thống phân tán. Quan trọng là các service hiểu context format tương ứng và không tạo root trace ngoài ý muốn. Cấu hình W3C/X-Ray propagators theo từng boundary và kiểm tra trace ID trên end-to-end test.

## 30. Runbook khi latency hoặc fault tăng

Khi dashboard báo p95 tăng hoặc 5xx tăng:

1. Xác định service và time range có vấn đề.
2. Mở Application Signals/CloudWatch metrics để biết phạm vi ảnh hưởng.
3. Mở X-Ray Trace Map và chọn node/edge có dấu hiệu bất thường.
4. Lọc trace theo fault, throttle hoặc response time.
5. Chọn một số trace đại diện và mở Trace details.
6. Xác định span/subsegment chiếm nhiều thời gian hoặc mang exception.
7. Đối chiếu CloudWatch Logs theo trace ID.
8. Kiểm tra dependency metrics, AWS service errors và deployment events.
9. Kiểm tra retry, timeout, connection pool và sampling.
10. Sau khi khắc phục, so sánh trace/metrics với baseline.

Nếu Trace Map không có dữ liệu, kiểm tra instrumentation/export/permissions/sampling trước khi kết luận ứng dụng không có request.

## 31. Tình huống thực tế

### Tình huống A — orders-api chậm do DynamoDB

Trace summary cho thấy request mất 2,8 giây. Timeline cho thấy DynamoDB subsegment chiếm 2,3 giây.

**Cách xử lý:** kiểm tra throttle/retry, hot partition, table/index capacity, SDK attempt latency, VPC endpoint và connection pool. Đối chiếu CloudWatch DynamoDB metrics và application logs.

### Tình huống B — payment-service trả 500

Trace Map node payment-service đỏ. Trace details có exception ở span gọi payment provider.

**Cách xử lý:** lọc fault, mở span lỗi, kiểm tra HTTP status, error message đã mask, downstream latency và deployment version. Phân biệt lỗi nội bộ với lỗi từ external provider.

### Tình huống C — trace chỉ có orders-api

Orders-api gọi invoice-worker qua SQS nhưng trace map không nối hai service.

**Cách xử lý:** kiểm tra message trace context propagation, Lambda instrumentation, sampling decision, exporter và IAM. Kiểm tra integration có hỗ trợ liên kết producer/consumer trong kiến trúc đang dùng.

### Tình huống D — service có fault nhưng root trace vẫn thành công

Một downstream call lỗi nhưng application retry và thành công.

**Cách xử lý:** xem subsegment/edge có throttle hoặc error; không chỉ lọc root fault. Đánh giá retry count và dependency health.

### Tình huống E — nhiều node trùng tên

Nhiều deployment/service instance xuất hiện thành các node khó phân biệt hoặc graph quá lớn.

**Cách xử lý:** chuẩn hóa logical service name, dùng resource attributes cho instance/task/version và tránh đặt service name theo request ID hoặc pod ID.

### Tình huống F — trace bị chia thành hai trace ID

Service A gọi service B nhưng B tạo trace root mới.

**Cách xử lý:** kiểm tra propagator, HTTP instrumentation, proxy headers và async context propagation. Đảm bảo B extract parent context trước khi tạo server span.

### Tình huống G — lỗi chỉ xuất hiện trong production

Staging không tái hiện latency, production trace cho thấy JDBC span dài.

**Cách xử lý:** so sánh DB connection pool, query plan, lock contention, network, data volume và traffic shape. Dùng trace để chọn thời điểm/log liên quan thay vì thu thập payload nhạy cảm.

## 32. Bài tập tình huống

### Bài A — Trace, segment và subsegment

Một request đi qua orders-api rồi gọi DynamoDB.

**Đáp án:** trace đại diện request; orders-api có server segment/span; lời gọi DynamoDB được ghi trong subsegment/client span.

### Bài B — Inferred segment

DynamoDB không gửi segment riêng trong trace.

**Đáp án:** X-Ray có thể dựng inferred segment/node từ subsegment của caller để thể hiện dependency.

### Bài C — Edge latency cao

Node orders-api khỏe nhưng edge tới payment-service có latency cao.

**Đáp án:** mở edge và trace, kiểm tra round-trip time, network, retry, downstream processing và connection pool.

### Bài D — Trace Map đỏ

Node payment-service có viền đỏ.

**Đáp án:** red biểu thị server fault/5xx trong Trace Map; mở trace để xem segment/exception và downstream dependencies.

### Bài E — Throttle tăng

Edge tới DynamoDB có nhiều trace throttle.

**Đáp án:** kiểm tra throttling, capacity, hot key, retry policy và workload burst; không chỉ tăng sampling.

### Bài F — Annotation không filter được

Ứng dụng ghi order.tier dưới metadata nhưng filter annotation không tìm thấy.

**Đáp án:** cấu hình attribute thành X-Ray annotation theo exporter; metadata không được index.

### Bài G — Sampling rule ở downstream

Service B có sampling rule 100% nhưng trace vẫn không được sample vì service A quyết định sampled=false.

**Đáp án:** sampling thường parent-based; quyết định của root/parent được downstream tôn trọng. Điều chỉnh ở root hoặc thiết kế sampler phù hợp.

### Bài H — X-Ray SDK đang dùng trong Java

Một ứng dụng mới bắt đầu phát triển dựa trên X-Ray SDK/Daemon vào cuối năm 2026.

**Đáp án:** ưu tiên OpenTelemetry/ADOT vì X-Ray SDK/Daemon đã vào maintenance mode từ 25/02/2026.

### Bài I — Trace context qua SQS bị mất

Producer có trace nhưng Lambda consumer không liên kết.

**Đáp án:** kiểm tra propagation trong message, Lambda instrumentation, consumer context extraction và sampling/export.

### Bài J — Parent span dài hơn nhiều child spans

Tổng request 3 giây nhưng tổng duration các child span chỉ 1 giây.

**Đáp án:** có đoạn xử lý/chờ chưa được instrument hoặc parent bao gồm thời gian không nằm trong child spans. Bổ sung span và xem thread/queue/network wait.

### Bài K — Service Map và Application Map

Operator muốn theo dõi SLO health, nhưng đang xem X-Ray Trace Map.

**Đáp án:** dùng Application Signals Application Map/Services cho SLO và operational health; dùng X-Ray Trace Map để drill down trace/service graph.

### Bài L — Một request có nhiều lỗi downstream nhưng trả 200

Filter fault không tìm thấy trace.

**Đáp án:** xem subsegments/edges và filter service-specific; lỗi đã được retry/handle có thể không làm root trace thành fault.

### Bài M — Query theo annotation

Muốn tìm trace của nhóm khách hàng premium.

**Đáp án:** thêm annotation có cardinality thấp, không chứa PII, rồi filter theo annotation.tenantTier = "premium".

### Bài N — X-Ray Daemon và CloudWatch Agent cùng chạy

Sau migration, collector không nhận trace ổn định.

**Đáp án:** kiểm tra receiver/port conflict, dừng Daemon cũ khi chuyển hẳn sang CloudWatch Agent/Collector và xác nhận exporter chỉ gửi một luồng trace.

### Bài O — Trace có dữ liệu email

Trace attributes chứa email khách hàng.

**Đáp án:** loại bỏ hoặc pseudonymize PII, kiểm soát quyền truy cập và review processor/filter trước khi export.

## 33. Câu hỏi ôn tập

1. Distributed tracing giải quyết vấn đề gì trong microservices?
2. Trace ID có vai trò gì?
3. Segment đại diện cho điều gì?
4. Subsegment thường ghi lại loại hoạt động nào?
5. Inferred segment được tạo trong trường hợp nào?
6. Service graph được xây dựng từ dữ liệu nào?
7. Edge thể hiện điều gì?
8. Vì sao caller và callee có thể có thời gian khác nhau?
9. X-Ray Trace Map dùng để làm gì?
10. Application Signals Application Map khác Trace Map ở đâu?
11. Từ ngày nào X-Ray SDK/Daemon chuyển sang maintenance mode?
12. AWS khuyến nghị gì cho instrumentation mới?
13. OpenTelemetry span tương ứng khái niệm X-Ray nào?
14. OTel attributes mặc định được chuyển thành gì trong X-Ray?
15. Annotation khác metadata như thế nào?
16. X-Ray index tối đa bao nhiêu annotations mỗi trace?
17. X-Ray tracing header có tên gì?
18. W3C Trace Context thường dùng header nào?
19. Vì sao cần propagator tương thích giữa service?
20. ADOT Java agent có vai trò gì?
21. Collector nhận OTLP thường dùng protocol nào?
22. Exporter gửi trace tới X-Ray cần quyền nào?
23. Sampling giải quyết bài toán gì?
24. Default 1 request/second và 5% thuộc cơ chế nào?
25. Parent-based sampling ảnh hưởng downstream thế nào?
26. Tail sampling cần thực hiện ở đâu?
27. Trace Map màu đỏ/vàng/tím biểu thị gì?
28. fault, error và throttle khác nhau thế nào?
29. responsetime và duration dùng đơn vị gì trong filter expression?
30. Khi nào cần filter theo service/edge thay vì root fault?
31. Vì sao span duration lồng nhau không được cộng trực tiếp?
32. Trace Map và Application Map hỗ trợ những mục tiêu khác nhau nào?
33. Vì sao trace có thể thiếu segment?
34. X-Ray trace data được giữ bao lâu theo tài liệu hiện hành?
35. Khi migration, vì sao không nên bật đồng thời hai auto-instrumentation agent cho cùng thư viện?

**Đáp án nhanh:** (1) nối đường đi request giữa nhiều process; (2) liên kết spans/segments cùng request; (3) công việc của service; (4) downstream calls/đoạn xử lý; (5) downstream không gửi segment riêng; (6) các segments có cùng trace ID; (7) quan hệ gọi và round-trip; (8) caller đo round-trip, callee đo thời gian xử lý; (9) xem topology và traces; (10) SLO/service health so với trace graph; (11) 25/02/2026; (12) OTel/ADOT; (13) server span và non-server span; (14) metadata; (15) annotation được index, metadata không; (16) 50; (17) X-Amzn-Trace-Id; (18) traceparent/tracestate; (19) giữ parent-child context; (20) tự động instrument Java; (21) OTLP gRPC/HTTP; (22) PutTraceSegments và PutTelemetryRecords; (23) kiểm soát volume/chi phí; (24) X-Ray SDK default; (25) downstream kế thừa quyết định parent; (26) Collector; (27) 5xx/4xx/429; (28) server fault/client error/throttling; (29) giây; (30) khi lỗi downstream được xử lý và root vẫn thành công; (31) parent đã bao gồm child; (32) Trace Map phân tích trace, Application Map theo dõi SLO/topology; (33) sampling, instrumentation hoặc propagation/export gap; (34) 30 ngày; (35) tránh span trùng và parent-child sai.

## 34. Checklist production

- [ ] Service name ổn định và có ý nghĩa theo logical service.
- [ ] Java application dùng ADOT/OpenTelemetry instrumentation có version được pin.
- [ ] HTTP server/client, AWS SDK và JDBC instrumentation được kiểm tra.
- [ ] Custom spans chỉ bao phủ business operation cần thiết.
- [ ] Resource attributes có service name, environment và version.
- [ ] Trace context được propagate xuyên HTTP và async boundary.
- [ ] X-Ray/W3C propagators tương thích ở các boundary.
- [ ] Sampling policy được đặt tại root và phù hợp traffic.
- [ ] Metrics vẫn phản ánh toàn bộ request nếu trace sampling dưới 100%.
- [ ] Annotation chỉ chứa field cần filter, cardinality thấp và không có PII.
- [ ] Metadata không chứa secret hoặc payload nhạy cảm.
- [ ] Collector/CloudWatch Agent có pipeline traces và exporter hợp lệ.
- [ ] IAM role có quyền PutTraceSegments/PutTelemetryRecords tối thiểu.
- [ ] Collector có batch, retry/queue và theo dõi dropped spans.
- [ ] X-Ray Trace Map có thể drill down tới trace details.
- [ ] Application Signals được bật nếu cần service health/SLO map.
- [ ] CloudWatch logs có trace ID để correlate.
- [ ] Có query/filter expressions cho fault, throttle, latency và dependency.
- [ ] Có dashboard/alarms metrics cho SLO; không phụ thuộc trace sampling để cảnh báo.
- [ ] Có kiểm thử trace qua SQS/Lambda hoặc async worker nếu kiến trúc dùng queue.
- [ ] Có quy trình migration khỏi X-Ray SDK/Daemon maintenance mode.
- [ ] Không chạy hai instrumentation agent trùng lặp sau migration.
- [ ] Có quyền truy cập trace/log phù hợp và retention/cost policy rõ ràng.
- [ ] Runbook phân biệt instrumentation gap, sampling, propagation, exporter và dependency failure.

## 35. Tổng kết

AWS X-Ray giúp quan sát đường đi của request trong hệ thống phân tán bằng trace, segment, subsegment và service graph:

- Trace ID liên kết dữ liệu của cùng request; segment mô tả công việc của service; subsegment ghi lại downstream call hoặc đoạn xử lý chi tiết.
- Inferred segment giúp hiển thị dependency không gửi segment riêng; edge cung cấp góc nhìn round-trip từ caller.
- X-Ray Trace Map trực quan hóa service graph, lỗi và latency; Application Signals Application Map tập trung vào topology, service health và SLO.
- Từ 25/02/2026, X-Ray SDK/Daemon ở maintenance mode. Với Java mới, ưu tiên OpenTelemetry/ADOT và Collector/CloudWatch Agent để gửi trace tới X-Ray.
- Auto-instrumentation giúp thu thập spans cho framework/library; manual spans bổ sung ngữ cảnh nghiệp vụ.
- Sampling kiểm soát volume/chi phí; parent-based sampling cần được cấu hình tại root; tail sampling có thể ưu tiên trace lỗi/chậm.
- Annotation được index để filter; metadata lưu thông tin không cần tìm kiếm.
- Filter expressions giúp tìm fault, error, throttle, latency, service, edge và root cause.
- Trace details/timeline giúp tìm critical path; logs và metrics cung cấp bằng chứng bổ sung.
- Migration cần kiểm tra context propagation, collector, IAM, sampling và tránh instrumentation trùng.

Distributed tracing hiệu quả khi mỗi service tạo telemetry có cấu trúc, giữ được parent-child context và cung cấp đủ dữ liệu để nối topology với một request cụ thể. Trace không tự giải thích mọi sự cố; nó cho bạn đường dẫn để tìm đúng log, metric, dependency và đoạn code cần điều tra.

### Tài liệu AWS và OpenTelemetry chính thức

1. AWS X-Ray concepts: https://docs.aws.amazon.com/xray/latest/devguide/xray-concepts.html
2. Using the X-Ray trace map: https://docs.aws.amazon.com/xray/latest/devguide/xray-console-servicemap.html
3. Viewing traces and trace details: https://docs.aws.amazon.com/xray/latest/devguide/xray-console-traces.html
4. Using filter expressions: https://docs.aws.amazon.com/xray/latest/devguide/xray-console-filters.html
5. Configuring sampling rules: https://docs.aws.amazon.com/xray/latest/devguide/xray-console-sampling.html
6. Migrating from X-Ray instrumentation to OpenTelemetry: https://docs.aws.amazon.com/xray/latest/devguide/xray-sdk-migration.html
7. Migrating to OpenTelemetry Java: https://docs.aws.amazon.com/xray/latest/devguide/xray-migration-opentelemetry.html
8. AWS X-Ray SDK and Daemon: https://docs.aws.amazon.com/xray/latest/devguide/xray-sdk-java.html
9. AWS X-Ray daemon: https://docs.aws.amazon.com/xray/latest/devguide/xray-daemon.html
10. CloudWatch Application Signals: https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Services.html
11. CloudWatch Application Map: https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/ServiceMap.html
12. CloudWatch Agent and Application Signals: https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Agent-Application_Signals.html
13. CloudWatch integration with X-Ray: https://docs.aws.amazon.com/xray/latest/devguide/xray-services-cloudwatch.html
14. AWS X-Ray GetTraceSummaries API: https://docs.aws.amazon.com/xray/latest/api/API_GetTraceSummaries.html
15. AWS X-Ray BatchGetTraces API: https://docs.aws.amazon.com/xray/latest/api/API_BatchGetTraces.html
16. AWS Distro for OpenTelemetry: https://aws-otel.github.io/
17. OpenTelemetry Java instrumentation: https://opentelemetry.io/docs/zero-code/java/agent/
18. OpenTelemetry traces: https://opentelemetry.io/docs/concepts/signals/traces/
19. OpenTelemetry context propagation: https://opentelemetry.io/docs/concepts/context-propagation/
20. AWS Well-Architected Reliability Pillar: https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/welcome.html
