# Parent-based sampler

Một request đi qua API Gateway, Order Service, Inventory Service và Payment Service. Nếu mỗi service tự chọn sampling độc lập, có thể gateway giữ trace nhưng một service ở giữa lại bỏ span, khiến trace bị đứt. **Parent-based sampler** giải quyết vấn đề nhất quán đó: khi một span đã có parent, sampler tiếp tục theo quyết định sampled/not-sampled của parent; chỉ khi tạo root span mới, root sampler mới quyết định có lấy mẫu hay không.

Bài **Parent-based sampler** thuộc chương **Sampling** của module **SPRING_BOOT_OBSERVABILITY**. Module hướng đến thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; học context propagation, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ, hành vi ứng dụng trong môi trường thực.

> **Ý chính:** Parent-based sampler không phải “mỗi span tung đồng xu theo tỷ lệ”. Nó là sampler kết hợp: **root span dùng root sampler**, còn span có parent được quyết định bởi nhánh tương ứng trạng thái sampled của parent (remote/local). Với cấu hình mặc định của OpenTelemetry ParentBased, parent sampled dẫn đến child sampled; parent not-sampled dẫn đến child not-sampled. Điều này giúp toàn trace nhất quán, nhưng cũng khiến quyết định loại trace ở root lan truyền đến downstream spans.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích parent-based sampler và vai trò riêng của root sampler.
2. Phân biệt root span, local parent và remote parent.
3. Đọc sampled flag trong trace context và hiểu ảnh hưởng tới child span.
4. Mô tả bốn nhánh mặc định của OpenTelemetry ParentBased sampler.
5. Cấu hình sampling trong Spring Boot, hiểu vai trò của probability và sampler type khi dùng OpenTelemetry.
6. Phân biệt hành vi OTel với các tracing bridge/tracer khác.
7. Đánh giá tác động của root sampling lên trace completeness và chi phí exporter.
8. Phân biệt parent-based/head-based sampling với tail sampling ở Collector.
9. Kiểm thử sampling decision qua nhiều service và điều tra trace bị thiếu.
10. Hiểu rủi ro khi tin sampled flag từ remote caller.

## 2. Vì sao cần Parent-based sampler?

Một distributed trace thường gồm nhiều spans qua nhiều service. Nếu các service tự áp dụng ratio sampling độc lập, một trace có thể bị cắt đoạn. Gateway có thể giữ span, Order bỏ span, còn Inventory lại giữ span riêng. Backend sẽ hiển thị khoảng trống hoặc spans không có quan hệ cha-con như mong đợi.

Parent-based sampler đưa ra quy tắc: **child spans kế thừa quyết định sampling từ parent**. Root sampler chọn trace ban đầu; từ đó quyết định thường được duy trì qua ranh giới process khi trace context truyền đúng.

~~~mermaid
flowchart TD
    A["Không có parent context"] --> B["Root sampler"]
    B -->|Sampled| C["Root span được record/sample"]
    B -->|Not sampled| D["Root span không được export"]
    C --> E["Child span"]
    D --> F["Child span"]
    E --> G["ParentBased: follow sampled parent"]
    F --> H["ParentBased: follow not-sampled parent"]
    G --> I["Child sampled"]
    H --> J["Child not sampled"]
~~~

Parent-based sampling không tự bảo đảm backend có mọi span. Span vẫn có thể thiếu vì instrumentation không tạo span, context propagation bị đứt, process crash, exporter/collector drop hoặc retention/query. Nó chỉ nhất quán hóa sampling decision tại thời điểm sampler được gọi.

## 3. Root span, child span và hai loại parent

**Root span** là span không có parent context hợp lệ trong trace hiện hành. Nó thường xuất hiện ở inbound boundary của request mới, message mới hoặc công việc độc lập.

**Child span** được tạo trong context có parent. Nó có Trace ID chung với parent, Span ID mới và parentSpanId trỏ đến Span ID của parent.

~~~text
Trace T
  API Gateway server span       (root, sampled)
    Order Service server span   (child, sampled)
      Inventory client span     (child, sampled)
        Inventory server span   (child, sampled)
      Payment client span       (child, sampled)
        Payment server span     (child, sampled)
~~~

OpenTelemetry ParentBased phân biệt:

- **Local parent:** parent span được tạo trong cùng process/SDK context, ví dụ span nghiệp vụ gọi span DB.
- **Remote parent:** context được extract từ process khác, thường qua W3C traceparent hoặc propagation format khác.
- **Không có parent:** sampler dùng root policy.

Sự phân biệt này cho phép cấu hình nhánh riêng cho parent remote sampled/not-sampled và local sampled/not-sampled. Mặc định ParentBased của OpenTelemetry xử lý sampled parent bằng AlwaysOn và not-sampled parent bằng AlwaysOff, cho cả local lẫn remote.

## 4. Bốn nhánh mặc định của OpenTelemetry ParentBased

ParentBased là sampler decorator có root sampler bắt buộc và bốn nhánh parent tùy chọn. Các nhánh mặc định của OpenTelemetry SDK:

| Parent tồn tại? | Parent remote? | Parent sampled? | Nhánh mặc định | Quyết định |
|---|---|---|---|---|
| Không | Không áp dụng | Không áp dụng | root(root sampler) | Root sampler quyết định |
| Có | Có | Có | remoteParentSampled = AlwaysOn | Sample child |
| Có | Có | Không | remoteParentNotSampled = AlwaysOff | Không sample child |
| Có | Không | Có | localParentSampled = AlwaysOn | Sample child |
| Có | Không | Không | localParentNotSampled = AlwaysOff | Không sample child |

**Root sampler** có thể là AlwaysOn, AlwaysOff hoặc TraceIdRatioBased. ParentBased dùng nó chỉ khi không có parent.

### 4.1 Root ratio 10% nghĩa là gì?

Giả sử root sampler dùng TraceIdRatioBased với tỷ lệ 0.10:

- Mỗi root trace có cơ hội khoảng 10% được chọn theo thuật toán deterministic dựa trên Trace ID.
- Nếu root sampled, các child span theo nhánh parent sampled và được sample.
- Nếu root not-sampled, các child span theo nhánh parent not-sampled và không được sample.
- Các service không tung tỷ lệ 10% độc lập cho từng child của cùng trace.

Tỷ lệ 10% là xác suất cho root traces, không phải giới hạn cứng “đúng 10 trace mỗi 100 request”. Trong cửa sổ nhỏ hoặc traffic ít, tỷ lệ quan sát được có thể khác đáng kể.

### 4.2 Parent sampled không có nghĩa mọi telemetry đều được lưu

ParentBased sampler quyết định span có được recording/sampling theo SDK hay không. Nó không cam kết exporter thành công, collector không drop hoặc backend giữ span vô thời hạn. Cần phân biệt:

1. Sampling decision ở SDK.
2. Span được ghi trong process và kết thúc đúng lifecycle.
3. Processor/exporter gửi span.
4. Collector nhận và xử lý span.
5. Backend lưu và cho phép truy vấn.

Child có decision sampled nhưng không có trong UI vẫn có thể do export, collector hoặc backend. Kiểm tra từng chặng thay vì đổi root ratio ngay.

## 5. Quyết định sampling được truyền qua HTTP

W3C Trace Context truyền Trace ID, parent span ID và trace flags trong header traceparent. Sampled bit trong trace flags là một phần context mà downstream dùng để áp dụng parent-based sampling.

Ví dụ root span được sample và Order Service gọi Inventory:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

- Trace ID: 4bf92f3577b34da6a3ce929d0e0e4736.
- Parent ID: 00f067aa0ba902b7, định danh span phía gửi.
- Trace flags 01: sampled bit được bật.
- Inventory extract remote parent context; ParentBased chọn remoteParentSampled và sample server span mới.

Nếu sampled bit tắt, với mặc định ParentBased, remoteParentNotSampled sẽ không sample child.

### 5.1 Sampled flag không phải xác nhận từ backend

Bit sampled có thể được truyền xuyên process, nhưng không phải receipt từ backend. Nó không chứng minh exporter đã gửi span hoặc collector đã lưu. Một trace có sampled flag bật vẫn có thể vắng ở backend nếu app crash, export thất bại, collector drop hoặc query sai thời gian.

### 5.2 Remote sampled flag là trust boundary

Nếu service public tin mọi remote sampled flag, caller có thể cố ý gửi request với sampled bit bật để khiến downstream ghi nhiều spans hơn và tăng chi phí. Mặc định ParentBased theo parent decision giúp trace consistency, nhưng ranh giới internet cần policy rõ ràng:

- Đặt gateway/trusted ingress quản lý hoặc chuẩn hóa tracing context.
- Chọn sampler/branch policy phù hợp nếu SDK cho phép.
- Giới hạn tài nguyên exporter/collector, queue và ingestion.
- Không dùng Trace ID hoặc sampled flag để cấp quyền.
- Giám sát tỷ lệ sampled, span volume và dropped spans.

Đừng tự sửa sampled bit thủ công trong từng service mà không có kế hoạch; có thể tạo trace bị phân mảnh.

## 6. Cấu hình Parent-based sampler trong Spring Boot

Spring Boot Actuator auto-configure Micrometer Tracing khi dependencies và tracer bridge phù hợp. Theo tài liệu Spring Boot hiện hành, khi dùng **OpenTelemetry**, property **management.opentelemetry.tracing.sampler** hỗ trợ các lựa chọn:

| Sampler | Root decision / parent behavior |
|---|---|
| always-on | Sample mọi trace |
| always-off | Không sample trace |
| trace-id-ratio | Chọn tỷ lệ dựa trên management.tracing.sampling.probability; không parent-based |
| parent-based-always-on | Parent sampled thì sample child; root luôn sample |
| parent-based-always-off | Parent sampled thì sample child; root không sample |
| parent-based-trace-id-ratio | Parent decision được kế thừa; root dùng tỷ lệ cấu hình |

Với OpenTelemetry, Spring Boot hiện hành dùng **parent-based-trace-id-ratio** làm mặc định. Spring Boot đặt sampling probability mặc định 10% để hạn chế làm quá tải trace backend. Các hành vi/property phụ thuộc phiên bản Spring Boot và tracer implementation. Tham khảo [Spring Boot Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html).

### 6.1 Cấu hình root ratio 10%

~~~yaml
spring:
  application:
    name: order-service

management:
  tracing:
    sampling:
      probability: 0.10
  opentelemetry:
    tracing:
      sampler: parent-based-trace-id-ratio
~~~

Diễn giải:

- Root traces được chọn theo tỷ lệ 10%.
- Child spans thông thường tuân theo quyết định sampled/not-sampled của parent.
- Downstream services cần truyền và extract trace context đúng để giữ quyết định.
- Exporter/collector là cấu hình riêng; YAML sampling không tự cung cấp backend.

Với Spring Boot dùng auto-default phù hợp, đặt probability có thể đã sử dụng sampler parent-based mặc định của OpenTelemetry. Khai báo sampler type tường minh giúp tránh nhầm ratio sampler độc lập với parent-based ratio sampler.

### 6.2 Thu thập 100% traces trong local test

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
  opentelemetry:
    tracing:
      sampler: parent-based-trace-id-ratio
~~~

Với root ratio 1.0, tất cả root traces được chọn; ParentBased tiếp tục quyết định đó cho child spans. Chỉ dùng ở local/staging hoặc cửa sổ production được đánh giá kỹ vì span volume có thể tăng đáng kể. Cần exporter/collector hoạt động để xem kết quả.

### 6.3 Không sample root traces

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.0
  opentelemetry:
    tracing:
      sampler: parent-based-trace-id-ratio
~~~

Root sampler không chọn root trace; ParentBased mặc định cũng không chọn child của parent not-sampled. Đây không phải cách tắt toàn bộ instrumentation: Observation và metrics vẫn có thể hoạt động, nhưng trace spans không được sample theo policy này. Nếu có remote parent sampled, nhánh remote-parent-sampled cần được hiểu riêng; root probability chỉ quyết định trace không có parent.

### 6.4 Spring Boot dùng Brave hay OpenTelemetry?

Spring Boot hỗ trợ các tracer khác nhau, ví dụ OpenTelemetry và OpenZipkin Brave. Property **management.opentelemetry.tracing.sampler** dành cho OpenTelemetry sampler; không mặc định điều khiển Brave sampler. **management.tracing.sampling.probability** là property sampling abstraction của Spring Boot, nhưng chi tiết parent-based và bridge integration có thể khác. Kiểm tra dependencies, auto-configuration và tài liệu phiên bản dự án thay vì giả định tên sampler OTel áp dụng cho mọi bridge.

## 7. Parent-based sampling và head-based sampling

ParentBased thường được dùng như một **head-based sampling strategy** khi root decision được thực hiện ngay lúc bắt đầu trace. Quyết định sớm tiết kiệm recording/export chi phí cho traces không được chọn.

| Khía cạnh | Ratio sampler độc lập mỗi span | Parent-based ratio |
|---|---|---|
| Root span | Tự quyết định theo ratio | Dùng root sampler |
| Child span | Có thể tự chọn lại | Mặc định theo quyết định parent |
| Tính nhất quán xuyên service | Có thể đứt nếu mỗi service quyết định khác | Nhất quán khi context được propagate |
| Giữ trace đầy đủ | Không đảm bảo | Tăng khả năng giữ spans của trace đã chọn |
| Chọn trace lỗi theo dữ liệu cuối | Không | Không, nếu root head decision đã bỏ trace |

ParentBased không phải tail sampler. Nó không đợi trace hoàn tất để xem có lỗi, latency cao hay attribute đặc biệt rồi mới quyết định lưu cả trace.

## 8. Parent-based sampling khác tail sampling thế nào?

Tail sampling thường được thực hiện ở Collector/backend sau khi spans được gửi về một điểm tập trung. Collector giữ dữ liệu trong buffer/cache và quyết định theo policy sau khi quan sát các spans đến.

| Câu hỏi | Parent-based/head-based | Tail sampling |
|---|---|---|
| Khi nào quyết định? | Lúc span được tạo, dựa trên parent/root | Sau khi spans tới collector và đủ điều kiện policy |
| Thông tin nhìn thấy | Context và sampling attributes lúc tạo | Có thể xem status, duration, attributes đã nhận |
| Ưu điểm | Quyết định nhanh, giảm tải từ đầu | Có thể giữ trace lỗi/chậm theo điều kiện cuối |
| Nhược điểm | Root đã bỏ thì thường không thể khôi phục đủ spans | Cần memory/buffering, capacity và điều phối trace |
| Phù hợp | Giảm volume đồng đều, giữ quyết định xuyên service | Giữ lỗi, latency cao, route đặc biệt |

Một kiến trúc có thể dùng root ParentBased ở SDK và tail sampling ở Collector, nhưng nếu SDK đã loại root trace và không gửi spans, Collector không có đủ dữ liệu để giữ trace ấy. Muốn tail sampling chọn traces lỗi, cần gửi đủ spans đến điểm tail sampler hoặc thiết kế chiến lược head/tail phù hợp với chi phí.

### 8.1 Vì sao Collector không thể khôi phục span chưa được gửi?

Tail sampler chỉ quyết định trên dữ liệu nó nhận được. Nếu head sampler trong SDK đã loại tất cả spans của trace, Collector không thể tái tạo duration, exception hoặc attributes bị mất. Đây là lý do quyết định head sampling và tail policy phải được thiết kế như một pipeline chung.

## 9. Local parent, remote parent và service boundary

Một trace có thể gồm spans tạo trong cùng process và spans được extract qua network. ParentBased phân biệt hai loại parent, nhưng mặc định OpenTelemetry xử lý cùng nguyên tắc: sampled parent thì sample child; not-sampled parent thì không sample child.

~~~mermaid
sequenceDiagram
    participant C as External client
    participant G as API Gateway
    participant O as Order Service
    participant I as Inventory Service
    C->>G: HTTP request (no parent)
    Note over G: Root sampler chọn Trace T
    G->>O: HTTP + traceparent
    Note over O: Remote parent sampled/not-sampled
    O->>O: Local child span
    O->>I: HTTP + updated traceparent
    Note over I: Remote parent decision được kế thừa
~~~

Ví dụ root sampler đã sample:

1. Gateway tạo root span sampled.
2. Gateway gọi Order; Order extract remote parent sampled và sample server child.
3. Order tạo local child cho business operation; localParentSampled chọn sample.
4. Order gọi Inventory; Inventory extract remote parent sampled và sample server child.
5. Cả chuỗi trace có quyết định nhất quán.

Nếu Gateway không sample root, mặc định ParentBased truyền quyết định not-sampled xuống child. Trace context vẫn có thể được propagate để downstream biết cùng Trace ID và không tự khởi tạo trace mới.

## 10. Mất parent context: child trở thành root ngoài ý muốn

Nếu context không được inject/extract, downstream có thể nhìn request như một trace mới không có parent. Root sampler lại được gọi, và xác suất sampling được áp dụng lần nữa. Hậu quả:

- Một phần downstream spans có Trace ID khác request ban đầu.
- Một service tạo root sampled trong khi upstream trace không sampled.
- Trace UI hiển thị nhiều traces cho một hành trình nghiệp vụ.
- Tỷ lệ traces nhìn thấy khác sampling ratio dự kiến.
- Log correlation cho thấy IDs không nhất quán.

Kiểm tra instrumented HTTP client builder, inbound server instrumentation, W3C/B3 propagation formats, gateway header policy và async context propagation. Đừng sửa ParentBased thành ratio sampler độc lập để che lỗi context.

## 11. Parent-based sampler và metrics/logs

Tracing sampling không đồng nghĩa sampling mọi tín hiệu:

| Signal | Tác động thông thường của tracing sampler |
|---|---|
| Traces/spans | Quyết định span có recording/sample theo policy |
| Metrics | Không tự giảm Counter/Timer/Gauge theo cùng sampling ratio |
| Logs | Không tự giảm log events; logging level/filters/collector policy riêng |
| Baggage/trace context | Có thể tiếp tục propagate dù span không được export, tùy implementation |

Ví dụ root sampling 10% không có nghĩa chỉ 10% HTTP requests được đếm trong http.server.requests. Spring instrumentation có thể ghi metrics cho toàn bộ requests trong khi tracing chỉ export một phần traces. Metrics cho thống kê tổng thể; traces cho điều tra chi tiết một phần request.

Logs có thể có traceId/spanId ở những request không được export hoặc không tìm thấy trace backend. Không kết luận log correlation sai chỉ vì trace bị sampling loại.

## 12. Tác động vận hành và chi phí

ParentBased giúp giảm chi phí vì khi root not-sampled, các child spans thông thường cũng không được gửi. Khi root sampled, cả trace có thể tạo nhiều spans vì mỗi service, client call, database operation hoặc custom Observation có thể tạo span.

Các yếu tố tác động volume:

- Request rate và tỷ lệ root sampling.
- Số services/hops mỗi trace.
- Số spans được tạo trong mỗi service.
- Attributes, events và links mỗi span.
- Batch span processor queue/batch/flush cadence.
- Retry, timeout, exporter failure và collector backpressure.
- Sampling ở collector/backend và retention.

Giảm sampling ratio không phải cách duy nhất để giảm chi phí. Có thể giảm instrumentation dư thừa, bỏ attributes không cần, hạn chế events, giảm duplicate spans và tối ưu collector. Đảm bảo vẫn giữ đủ trace để điều tra và đáp ứng SLO.

### 12.1 Tỷ lệ root không phải tỷ lệ span

Nếu 10% root requests được sample và mỗi trace có trung bình 15 spans, tổng spans có thể xấp xỉ 10% số root traces nhân số span trung bình, chứ không phải 10% tổng số span độc lập. Traces có kích thước không đồng đều, nên root sampling ratio 10% không nhất thiết làm span volume giảm đúng 90% trong mọi workload.

## 13. Kiểm thử ParentBased sampler

Kiểm thử nên kiểm tra decision matrix và toàn chuỗi context, không chỉ xác nhận property tồn tại.

### 13.1 Decision matrix

Với OTel ParentBased mặc định và root ratio được cấu hình:

| Input context | Kết quả mong đợi |
|---|---|
| Không có parent; root ratio chọn | Kết quả theo root sampler |
| Không có parent; root ratio loại | Root not-sampled |
| Parent local sampled | Child sampled |
| Parent local not-sampled | Child not-sampled |
| Parent remote sampled | Child sampled |
| Parent remote not-sampled | Child not-sampled |

Nếu custom sampler thay các nhánh mặc định, test phải theo policy thực tế. Đừng giả định mọi SDK wrapper dùng cùng default branch nếu đã custom config.

### 13.2 Kiểm thử nhiều service

1. Chọn root request và cấu hình sampling dễ quan sát trong test (ví dụ tạm 100%).
2. Gọi Gateway → Order → Inventory.
3. Xác nhận cùng Trace ID, mỗi span có Span ID riêng và quan hệ parent phù hợp.
4. Lặp lại với root không được sample hoặc parent context not-sampled.
5. Xác nhận downstream không tự sample child theo root ratio độc lập.
6. Tạo trường hợp context propagation bị tắt để thấy downstream bắt đầu root ngoài ý muốn.
7. Đối chiếu SDK sampling decision với exporter/collector: trace không có trong UI có thể do pipeline, không nhất thiết do sampler.

Dùng test exporter/in-memory span exporter nếu SDK version hỗ trợ; không phụ thuộc backend Zipkin/OTLP bên ngoài cho mọi unit test.

### 13.3 Không dùng tập mẫu ngắn để đòi đúng 10%

Với root ratio 10%, 50 request có thể tạo ít hoặc nhiều hơn 5 traces được sample. Đây là quyết định theo Trace ID chứ không phải bộ đếm bảo đảm đúng 10 trên mỗi 100. Unit test logic nên test deterministic inputs hoặc ratio extremes 0/1; integration statistics cần nhiều mẫu và tolerance.

## 14. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
|---|---|---|
| Gateway có trace, downstream thiếu spans | Remote parent not-sampled hoặc export/propagation lỗi | Xem sampled flag, sampler branch, exporter |
| Downstream tạo Trace ID mới | Parent context không được extract | Kiểm tra traceparent, client builder, proxy |
| Child span sampled dù parent not-sampled | Custom branch AlwaysOn hoặc context bị mất, tạo root mới | Xem sampler config và parent context |
| Một trace có spans rời rạc | Sampling không thống nhất, context đứt, collector drop | Đối chiếu trace IDs, parent IDs, collector |
| Trace volume cao bất ngờ | Root ratio tăng, remote sampled flag được tin, span duplication | Kiểm tra config, ingress, instrumentation |
| Probability 10% nhưng thấy ít hơn nhiều | Collector/exporter drop, traffic nhỏ hoặc policy khác | Kiểm tra SDK decision và exporter diagnostics |
| Probability 10% nhưng thấy nhiều trace hơn dự kiến | Nhiều root traces độc lập hoặc propagation đứt | Xác nhận Trace ID và root spans |
| Metrics vẫn đủ trong khi traces chỉ 10% | Hành vi bình thường | Sampling metrics/tracing độc lập |
| Log có traceId nhưng UI không có trace | Span not-sampled, chưa export, retention/query | Kiểm tra sampled flag và pipeline |
| OTel sampler property không tác dụng với Brave | Property dành cho OTel | Kiểm tra tracer bridge/property tương ứng |
| Parent remote sampled tạo nhiều spans | Theo parent decision mặc định | Kiểm soát ingress/trust boundary/collector |
| Tail sampler không giữ trace lỗi | Head sampler đã loại spans trước collector | Thiết kế lại pipeline sampling |

## 15. Playbook: điều tra trace bị đứt giữa các service

**Tình huống:** Order Service có trace, nhưng Payment Service không có span trong cùng Trace ID.

1. **So sánh Trace ID:** nếu khác nhau, xác định context bị đứt hoặc Payment bắt đầu root trace mới.
2. **Kiểm tra outbound traceparent:** parent ID và sampled flag có hợp lệ không?
3. **Kiểm tra remote parent extraction:** Payment có nhận đúng header và dùng đúng propagation format không?
4. **Xem sampler type ở Payment:** nếu dùng OTel ParentBased, remote parent sampled/not-sampled quyết định nhánh nào.
5. **Kiểm tra SDK/export:** child được sample nhưng exporter/collector vẫn có thể drop.
6. **Kiểm tra instrumentation:** client/server spans có thực sự được tạo không?
7. **So sánh log/metrics:** metrics HTTP hoặc business operations có tăng dù trace không có?
8. **Kiểm chứng sau sửa:** trace đi qua cả chuỗi; root/child decisions nhất quán.

Không thay probability thành 1.0 trong production chỉ để tìm trace bị mất trước khi biết lỗi nằm ở root sampling, propagation hay export.

## 16. Bài tập tự kiểm tra

**Bài 1 — Root và child.** Root sampler chọn 10% trace. Một root được chọn, tạo ba child local và hai child remote. Với ParentBased defaults, những spans nào được sample? Vì sao child không tung tỷ lệ 10% riêng?

**Bài 2 — Root bị loại.** Một root không được sample, gọi Order và Inventory. Mặc định ParentBased quyết định child thế nào? Trace context còn có thể được propagate không?

**Bài 3 — Parent local và remote.** Giải thích khác biệt hai nhánh. Trong mặc định OTel, quyết định của chúng khác nhau ra sao khi parent sampled/not-sampled?

**Bài 4 — Spring Boot.** Bạn dùng Spring Boot với OpenTelemetry, đặt sampling probability 0.25 và sampler type parent-based-trace-id-ratio. Con số 0.25 áp dụng ở đâu? Nó có áp dụng lại cho từng child span không?

**Bài 5 — Tail sampling.** Collector muốn giữ mọi trace có ERROR. Nếu SDK head sampler đã loại trace root và không gửi spans, Collector có thể phục hồi trace đó không? Vì sao?

**Bài 6 — Metrics.** Tracing sampling là 10%, nhưng Counter HTTP request vẫn tăng cho mọi request. Đây là sai cấu hình hay hành vi bình thường?

**Bài 7 — Trust boundary.** Caller bên ngoài gửi traceparent có sampled bit bật. Tại sao có thể làm tăng chi phí? Ingress/SDK/collector có thể áp dụng policy nào?

**Bài 8 — Probability thực tế.** Test gửi 50 requests với ratio 10%, nhưng thấy 8 traces. Điều này có chứng minh sampler sai không? Cần test theo cách nào?

### Gợi ý trả lời

1. Root được sample nên tất cả child theo nhánh sampled mặc định cũng sample.
2. Child theo not-sampled parent nên không sample; context vẫn có thể được truyền để duy trì trace identity/decision.
3. Local parent nằm trong cùng process, remote parent được extract từ process khác; mặc định cả hai AlwaysOn khi sampled và AlwaysOff khi not-sampled.
4. 0.25 áp dụng cho root traces; child tuân theo parent decision, không tự áp ratio lần nữa.
5. Không; collector không thể tail-sample spans chưa từng được gửi.
6. Bình thường; metrics và traces có cơ chế sampling/export riêng.
7. Caller có thể gây span volume lớn; cần ingress policy, sampler branch/trust, giới hạn tài nguyên và monitoring.
8. Không; tập mẫu nhỏ dao động. Test decision logic hoặc ratio 0/1 deterministic, integration statistics cần nhiều mẫu và tolerance.

## 17. Tài liệu tham khảo chính thức

- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): sampling probability, supported OpenTelemetry sampler types và default Spring Boot behavior.
- [Spring Boot 4.1 — Tracing](https://docs.spring.io/spring-boot/4.1/reference/actuator/tracing.html): OpenTelemetry parent-based sampler property và lựa chọn sampler.
- [OpenTelemetry Specification — Trace SDK](https://opentelemetry.io/docs/specs/otel/trace/sdk/): ParentBased sampler, root/local/remote parent branches và default behavior.
- [OpenTelemetry Java SDK](https://opentelemetry.io/docs/languages/java/sdk/): sampler Java SDK, ParentBased và root sampler configuration.
- [OpenTelemetry Java Configuration](https://opentelemetry.io/docs/languages/java/configuration/): sampler configuration và ratio properties.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/): traceparent, trace flags và sampled bit.
- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/): tracer abstraction và tích hợp tracing.
- [OpenTelemetry — Sampling](https://opentelemetry.io/docs/concepts/sampling/): sampling strategies và trade-offs.
- [OpenTelemetry Collector — Tail Sampling Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/tailsamplingprocessor): policy tail sampling tại collector.

**Ghi nhớ:** Parent-based sampler dùng **root sampler để quyết định trace mới**, rồi giữ quyết định của parent cho các spans con qua local và remote boundaries. Với OpenTelemetry/Spring Boot, parent-based-trace-id-ratio kết hợp tỷ lệ root được cấu hình qua management.tracing.sampling.probability; child không tự áp lại tỷ lệ đó. Điều này giúp trace đã chọn ít bị đứt, nhưng root bị loại sẽ không thể được tail sampler ở Collector khôi phục nếu spans không được gửi. Hãy kiểm tra parent context, sampled flag, exporter và collector theo từng chặng; giữ metrics/logs như tín hiệu độc lập và bảo vệ trust boundary khi nhận trace context từ bên ngoài.

