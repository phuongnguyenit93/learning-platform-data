# Không để exporter làm chậm nghiệp vụ

> **Chương:** Export traces  
> **Bối cảnh:** Spring Modulith Documentation & Observability — xuất module entry spans và các trace của ứng dụng Spring Boot đến hệ thống quan sát mà vẫn giữ độ trễ nghiệp vụ ổn định khi collector hoặc backend gặp sự cố.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt việc kết thúc span, xếp span vào hàng đợi, batch export và collector tiếp nhận dữ liệu.
2. Giải thích vì sao **BatchSpanProcessor** giúp tách network I/O khỏi request path và vì sao **SimpleSpanProcessor** có thể làm tăng latency.
3. Cấu hình queue size, batch size, schedule delay, export timeout và OTLP timeout trong Spring Boot.
4. Ước lượng queue theo tốc độ sinh span và thời gian gián đoạn có thể chịu được.
5. Hiểu backpressure, queue đầy, retry, timeout và dữ liệu bị drop; không xem queue lớn là giải pháp cho tình trạng backend quá tải kéo dài.
6. Dùng sampling, OpenTelemetry Collector và graceful shutdown để cân bằng latency, độ đầy đủ của trace và chi phí vận hành.
7. Kiểm tra exporter bằng metrics, log, test tải và tình huống collector chậm hoặc mất kết nối.

## 2. Vì sao export trace có thể ảnh hưởng request?

Một module entry span thường được tạo khi lời gọi đi vào Spring component thuộc API của application module. Khi span kết thúc, hệ thống cần chuyển dữ liệu span tới backend như Tempo, Jaeger, Zipkin hoặc một dịch vụ nhận OTLP.

Nếu thao tác gửi dữ liệu mạng diễn ra ngay trên thread đang xử lý request, request có thể phải chờ:

- Kết nối đến collector hoặc backend.
- DNS, TLS handshake và xác thực.
- Gửi payload và chờ phản hồi.
- Retry khi endpoint tạm thời lỗi.

Khi backend chậm, các khoảng chờ này có thể làm tăng thời gian phản hồi, giữ thread lâu hơn và tạo áp lực dây chuyền lên thread pool.

Mục tiêu của kiến trúc export là **ghi nhận span nhanh tại ứng dụng, sau đó gửi theo lô trên worker riêng**. Việc này tách phần lớn network I/O khỏi đường xử lý nghiệp vụ.

~~~mermaid
flowchart LR
    Request["Request thread<br/>orders / payments"] --> Span["Kết thúc module span"]
    Span --> Queue["BatchSpanProcessor<br/>bounded queue"]
    Queue --> Worker["Export worker thread"]
    Worker --> Exporter["OTLP SpanExporter"]
    Exporter --> Collector["OpenTelemetry Collector"]
    Collector --> Backend["Tempo / Jaeger / backend"]
~~~

Sơ đồ mô tả pipeline thường dùng với OpenTelemetry **BatchSpanProcessor**. Thread nghiệp vụ vẫn chịu chi phí tạo span, ghi attributes và đưa span vào queue; nó không phải chờ toàn bộ network round-trip của exporter trong mô hình batch.

## 3. Phân biệt SpanProcessor và SpanExporter

Hai thành phần này có trách nhiệm khác nhau:

| Thành phần | Vai trò | Câu hỏi chính |
| --- | --- | --- |
| **SpanProcessor** | Nhận span khi span kết thúc, quyết định xử lý ngay hay xếp hàng/batch | Khi nào và trên thread nào span được chuyển đi? |
| **SpanExporter** | Chuyển batch span ra ngoài tiến trình qua OTLP, Zipkin hoặc giao thức khác | Gửi dữ liệu đến đâu và bằng cách nào? |
| **OpenTelemetry Collector** | Nhận, xử lý, lọc, batch, retry hoặc chuyển tiếp telemetry | Có thể gom và định tuyến dữ liệu ở tầng hạ tầng ra sao? |
| **Trace backend** | Lưu trữ và truy vấn traces | Người vận hành xem trace ở đâu? |

**SpanExporter không tự đảm bảo việc gửi bất đồng bộ. SpanProcessor quyết định cách exporter được gọi.** Với OpenTelemetry Java SDK:

- **BatchSpanProcessor** gom các sampled spans vào queue hữu hạn, rồi gửi theo batch bằng worker.
- **SimpleSpanProcessor** gửi từng sampled span khi span kết thúc. Vì lời gọi exporter có thể được kích hoạt từ thread kết thúc span, không dùng kiểu này cho network exporter trên request path nếu chưa đánh giá tác động.

Một BatchSpanProcessor vẫn gọi SpanExporter ở worker của nó; batching không làm exporter biến mất và cũng không đảm bảo không có chi phí CPU/memory trong request thread.

## 4. Batch export bảo vệ đường nghiệp vụ như thế nào?

Với BatchSpanProcessor, khi span kết thúc:

1. Processor nhận span đã được ghi nhận và sampled.
2. Span được đưa vào queue nội bộ có giới hạn.
3. Worker export gom nhiều spans thành một batch khi batch đạt ngưỡng hoặc đến lịch export.
4. Exporter gửi batch tới collector.
5. Sau khi xử lý xong, processor tiếp tục lấy dữ liệu trong queue.

~~~mermaid
sequenceDiagram
    participant App as Request / module thread
    participant BSP as BatchSpanProcessor
    participant Q as Queue
    participant W as Export worker
    participant OTLP as OTLP exporter
    participant C as Collector
    App->>BSP: onEnd(span)
    BSP->>Q: enqueue span
    Note over App,Q: Request tiếp tục sau khi ghi span vào queue
    W->>Q: lấy batch
    Q-->>W: tối đa maxBatchSize spans
    W->>OTLP: export(batch)
    OTLP->>C: OTLP request
    C-->>OTLP: ACK / lỗi
    OTLP-->>W: kết quả export
~~~

Batching giúp giảm số lần gọi mạng, tận dụng kết nối và tránh buộc từng request chờ backend. Tuy vậy, nếu queue đầy hoặc custom processor/exporter làm việc đồng bộ, ứng dụng vẫn có thể chịu ảnh hưởng.

### 4.1. Không nhầm export delay với request latency

**schedule-delay** là khoảng thời gian theo lịch giữa các lần export batch khi chưa đạt ngưỡng batch; nó không phải thời gian request phải đợi. Vì vậy trace có thể xuất hiện ở backend trễ hơn thời điểm request hoàn tất.

Nếu giảm delay:

- Trace đến backend sớm hơn.
- Batch có thể nhỏ hơn, dẫn tới nhiều lần gửi hơn.

Nếu tăng delay:

- Có cơ hội gom batch lớn hơn.
- Dữ liệu chờ lâu hơn trước khi được export.

Chọn delay dựa trên nhu cầu tra cứu gần thời gian thực và năng lực collector; không đặt quá thấp chỉ vì muốn thấy trace ngay sau khi refresh.

## 5. Cấu hình Spring Boot với OpenTelemetry OTLP

Ví dụ dưới đây dùng **Spring Boot 4.2** với OpenTelemetry/OTLP. Spring Boot cung cấp starter và auto-configuration để tích hợp Micrometer Tracing với OpenTelemetry.

Dependency:

~~~xml
<!-- pom.xml: version do Spring Boot dependency management quản lý -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-opentelemetry</artifactId>
</dependency>
~~~

Trong ứng dụng Spring Modulith, vẫn cần dependency observability phù hợp để tạo module entry observations/spans, ví dụ Insight starter của Spring Modulith theo BOM tương thích:

~~~xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-starter-insight</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

### 5.1. Ví dụ cấu hình queue, batch và timeout

~~~yaml
# application.yml — ví dụ khởi đầu cho Spring Boot 4.2
management:
  tracing:
    sampling:
      probability: 0.10

  opentelemetry:
    tracing:
      export:
        schedule-delay: 2s
        max-queue-size: 4096
        max-batch-size: 512
        timeout: 20s
        otlp:
          endpoint: "http://otel-collector:4318/v1/traces"
          transport: http
          connect-timeout: 2s
          timeout: 8s
          compression: gzip
~~~

Các thuộc tính quan trọng:

| Thuộc tính | Ý nghĩa | Giá trị mặc định trong Boot 4.2 |
| --- | --- | ---: |
| **management.opentelemetry.tracing.export.schedule-delay** | Khoảng cách giữa các lần export theo lịch | **5s** |
| **management.opentelemetry.tracing.export.max-queue-size** | Số span tối đa được giữ trong queue trước khi span mới có thể bị drop | **2048** |
| **management.opentelemetry.tracing.export.max-batch-size** | Số span tối đa trong một batch export; không vượt quá queue size | **512** |
| **management.opentelemetry.tracing.export.timeout** | Thời gian tối đa cho một lần export của processor trước khi bị hủy | **30s** |
| **management.opentelemetry.tracing.export.otlp.connect-timeout** | Giới hạn thời gian thiết lập kết nối tới collector | **10s** |
| **management.opentelemetry.tracing.export.otlp.timeout** | Thời gian tối đa cho lời gọi export OTLP, gồm DNS/kết nối/gửi/nhận phản hồi và retry trong budget | **10s** |

Các giá trị trong YAML là **ví dụ để bắt đầu thử nghiệm**, không phải khuyến nghị cố định cho mọi tải. Ở ví dụ này, queue tăng lên 4096 để hấp thụ burst ngắn; processor timeout là 20 giây, còn mỗi lần gọi OTLP có timeout 8 giây.

Endpoint theo signal được khai báo đầy đủ **/v1/traces**. Nếu dùng thuộc tính chung **management.opentelemetry.otlp.endpoint** thay cho endpoint riêng, Spring Boot sẽ thêm path signal tương ứng khi áp dụng HTTP fallback. Không thêm path lần thứ hai khi đã cấu hình endpoint riêng đầy đủ.

### 5.2. Sampling cũng ảnh hưởng tải export

Spring Boot mặc định sample một tỷ lệ nhỏ request để hạn chế lượng trace gửi đến backend. Thuộc tính **management.tracing.sampling.probability** điều khiển tỷ lệ này; giá trị **0.10** tương ứng khoảng 10% traces được chọn ở root theo sampler ratio, tùy chính sách parent-based.

- Giảm tỷ lệ sampling làm giảm số span phải xếp queue và export.
- Tăng tỷ lệ sampling giúp điều tra nhiều request hơn, nhưng tăng CPU, bộ nhớ, băng thông và dung lượng lưu trữ.
- Không đặt sampling 100% trên production chỉ để làm dashboard có nhiều dữ liệu hơn.

Sampling diễn ra trước khi span được export. Nếu ứng dụng head-sample và loại bỏ trace ngay tại nguồn, collector không thể khôi phục các span đã không được gửi.

## 6. Chọn queue size dựa trên tải thực tế

Queue hữu hạn là bộ đệm hấp thụ burst hoặc một khoảng gián đoạn ngắn của collector. Một ước lượng ban đầu:

~~~text
queue cần thiết ≈ số span sinh ra mỗi giây
                 × thời gian gián đoạn muốn hấp thụ
                 + phần dự phòng
~~~

Ví dụ:

- Ứng dụng tạo trung bình 250 sampled spans/giây.
- Muốn hấp thụ một đợt gián đoạn khoảng 8 giây.
- Số span cần giữ tạm thời: **250 × 8 = 2.000**.
- Có thể thử queue 3.000–4.096 rồi đo lại dưới tải thật.

Đây chỉ là **ước lượng số lượng span**, chưa tính dung lượng bộ nhớ của từng span, số attributes/events, tốc độ export sau khi collector hồi phục và số instance. Span chứa nhiều metadata có thể tốn bộ nhớ lớn hơn đáng kể.

### 6.1. Queue không giải quyết được quá tải kéo dài

Gọi:

- **Rin:** tốc độ span được sinh và đưa vào queue.
- **Rout:** tốc độ worker export thành công.

Nếu Rout lớn hơn Rin trong thời gian đủ dài, queue có thể được làm rỗng. Nếu Rout thấp hơn Rin liên tục, queue sẽ tăng cho đến khi đầy, dù dung lượng ban đầu lớn đến đâu.

~~~mermaid
flowchart TD
    A["Span rate Rin"] --> Q["Bounded queue"]
    Q --> W["Export throughput Rout"]
    W --> B["Collector / backend"]
    Q --> C{"Queue đầy?"}
    C -->|"Không"| D["Tiếp tục nhận spans"]
    C -->|"Có"| E["Span mới bị drop<br/>theo chính sách processor"]
    E --> F["Theo dõi queue/drop metrics<br/>giảm tải hoặc tăng năng lực"]
~~~

Khi queue đầy, OpenTelemetry BatchSpanProcessor không nên biến request thành một lần chờ vô hạn để cứu telemetry. Queue có giới hạn và span có thể bị drop. Đây là trade-off có chủ đích: bảo vệ ứng dụng khỏi việc giữ dữ liệu không giới hạn, nhưng phải giám sát để biết trace đang mất.

## 7. Điều chỉnh batch size và schedule delay

| Điều chỉnh | Tác động tích cực | Rủi ro/đánh đổi |
| --- | --- | --- |
| Tăng **max-batch-size** | Ít request mạng hơn, tận dụng thông lượng tốt hơn | Payload lớn, tăng memory và thời gian xử lý một batch |
| Giảm **max-batch-size** | Batch nhỏ, phản hồi export nhanh hơn trong một số tình huống | Nhiều request hơn, tăng overhead mạng |
| Tăng **schedule-delay** | Có thời gian gom thêm spans | Trace đến backend muộn hơn |
| Giảm **schedule-delay** | Trace hiển thị sớm hơn | Nhiều batch nhỏ, tăng overhead |
| Tăng **max-queue-size** | Hấp thụ burst hoặc outage ngắn lâu hơn | Tốn heap hơn; không sửa được throughput thiếu kéo dài |

Nguyên tắc:

1. Bắt đầu với batch size vừa phải (ví dụ 512) và schedule delay vài giây.
2. Đo queue occupancy, dropped spans, batch size thực tế và export duration.
3. Tăng batch size nếu worker đang gửi nhiều batch nhỏ và collector có khả năng nhận batch lớn.
4. Chỉ tăng queue nếu có bằng chứng workload là burst ngắn và heap còn đủ dư địa.
5. Đánh giá lại bằng tải production-like; không chọn tham số chỉ từ một lần chạy local.

## 8. Timeout: tách kết nối, export request và processor

Ba timeout có ý nghĩa khác nhau:

| Timeout | Giới hạn | Khi vượt ngưỡng |
| --- | --- | --- |
| Connect timeout | Thời gian thiết lập kết nối tới collector | Không thiết lập được kết nối trong giới hạn |
| OTLP exporter timeout | Toàn bộ lời gọi export batch, gồm kết nối, gửi payload, chờ phản hồi và retry theo budget | Exporter trả kết quả thất bại/hết hạn |
| Batch processor export timeout | Thời gian processor cho phép một lần export chạy trước khi hủy | Processor kết thúc lần export theo timeout của nó |

Ví dụ cấu hình ở phần 5:

- Kết nối tối đa 2 giây.
- Lời gọi OTLP tối đa 8 giây.
- Processor cho phép export tối đa 20 giây.

Processor timeout nên được hiểu như giới hạn ngoài cho một lượt xử lý batch; exporter timeout là giới hạn của lời gọi OTLP. Đặt các timeout không hợp lý có thể khiến worker bị giữ lâu, queue tăng và span bị drop khi queue đầy.

**Timeout quá dài:** worker có thể mắc kẹt lâu khi collector không phản hồi.  
**Timeout quá ngắn:** mạng chậm bình thường cũng có thể làm batch thất bại.  
**Không có timeout:** worker có thể bị treo quá lâu và làm queue tích tụ.

## 9. Retry và backoff khi collector tạm thời lỗi

OTLP quy định exporter cần xử lý transient errors bằng **exponential backoff và jitter**. Mỗi lần thử và thời gian chờ retry đều bị giới hạn bởi export timeout còn lại; exporter không được kéo dài vô hạn chỉ vì lỗi mạng.

Luồng khái niệm:

~~~mermaid
flowchart TD
    A["Export batch"] --> B["Gửi OTLP request"]
    B --> C{"Kết quả"}
    C -->|"Thành công"| D["Đánh dấu batch export xong"]
    C -->|"Transient error"| E["Backoff tăng dần + jitter"]
    E --> F{"Còn timeout budget?"}
    F -->|"Có"| B
    F -->|"Không"| G["Kết thúc thất bại<br/>ghi nhận lỗi"]
    C -->|"Non-retryable error"| G
~~~

Retry có ích khi collector restart ngắn hoặc có lỗi mạng thoáng qua. Tuy nhiên:

- Retry giữ worker bận và làm queue phía ứng dụng tăng.
- Retry không thể bảo đảm gửi thành công nếu backend ngừng hoạt động lâu.
- Khi hết timeout budget, batch có thể thất bại và span có thể mất khỏi pipeline in-memory.
- Không thêm một vòng retry vô hạn bên ngoài exporter; nhiều tầng retry có thể nhân thời gian chờ và tạo retry storm.

## 10. Đưa OpenTelemetry Collector vào giữa ứng dụng và backend

Một kiến trúc phổ biến:

~~~mermaid
flowchart LR
    subgraph App["Application pods"]
        A["orders / payments<br/>BatchSpanProcessor"]
    end
    A -->|"OTLP HTTP/gRPC"| Agent["Collector agent<br/>gần application"]
    Agent -->|"batch / retry / routing"| Gateway["Collector gateway"]
    Gateway --> Tempo["Tempo / Jaeger"]
    Gateway --> Other["Backend khác"]
~~~

Collector giúp tách cấu hình backend khỏi từng service, chuẩn hóa resource attributes, lọc dữ liệu, gom batch và định tuyến đến nhiều đích. Collector agent gần ứng dụng có thể giảm độ trễ mạng và tránh mỗi application phải tự quản lý nhiều kết nối backend.

### 10.1. Pipeline collector minh họa

Một cấu hình rút gọn để hình dung receiver, processor và exporter:

~~~yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 512
  batch:
    timeout: 5s
    send_batch_size: 512

exporters:
  otlp:
    endpoint: tempo-gateway:4317
    # Cấu hình TLS/auth theo môi trường triển khai.

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlp]
~~~

Đây là **ví dụ cấu trúc**; tên exporter, TLS và các tùy chọn queue/retry cần được đối chiếu phiên bản OpenTelemetry Collector đang dùng. Trong production, cấu hình bảo mật, memory limiter, sending queue, retry và resource limits phải được đánh giá riêng.

Collector không tự biến queue trong application thành durable storage. Nếu Collector cũng giữ queue trong RAM và bị kill đột ngột, dữ liệu chưa gửi có thể mất. Nếu yêu cầu giữ telemetry qua restart/mất mạng dài, cần một tầng đệm bền vững được thiết kế riêng (ví dụ message broker hoặc persistent queue phù hợp), kèm giới hạn dung lượng và chính sách đầy.

## 11. Sampling và Tail Sampling

Sampling là cách giảm số trace cần ghi nhận và export:

- **Head sampling:** quyết định sớm ở đầu trace; spans không được sample sẽ không đi vào pipeline export thông thường.
- **Tail sampling:** collector quyết định sau khi đã quan sát đủ dữ liệu của trace, ví dụ giữ trace có lỗi hoặc latency cao.

Với tail sampling, collector phải nhận đủ các spans của một trace trước khi ra quyết định. Nếu ứng dụng đã head-sample loại bỏ một phần trace, collector không thể tail-sample trên dữ liệu chưa từng nhận. Trong môi trường nhiều collector, cần đảm bảo các spans cùng trace được định tuyến đến cùng tail-sampling decision point hoặc một kiến trúc hỗ trợ quyết định phân tán.

Sampling giúp giảm áp lực queue và backend, nhưng có thể làm mất khả năng điều tra các request bình thường. Hãy chọn chính sách dựa trên câu hỏi vận hành: giữ lỗi, latency cao, một số route/module quan trọng hoặc một tỷ lệ nền cho các trace còn lại.

## 12. Graceful shutdown và nguy cơ mất span

Batch queue thường nằm trong bộ nhớ tiến trình. Khi ứng dụng dừng:

1. Không nhận thêm request mới theo quy trình shutdown của ứng dụng.
2. Các spans đã kết thúc còn trong queue cần được processor/exporter flush.
3. SDK đóng exporter và các tài nguyên liên quan.
4. Tiến trình kết thúc sau khi quá trình shutdown hoàn tất hoặc hết thời gian cho phép.

Nếu container bị kill ngay lập tức, máy bị mất điện hoặc process crash, dữ liệu còn trong queue RAM có thể mất. Vì vậy:

- Cho phép Spring ApplicationContext đóng bình thường để SDK được shutdown theo lifecycle.
- Đặt thời gian termination grace của nền tảng đủ cho ứng dụng hoàn tất shutdown, nhưng vẫn có giới hạn rõ.
- Với SDK tự tạo, gọi **forceFlush()** và **shutdown()** theo API, chờ kết quả trong thời gian hữu hạn.
- Không tự tạo thêm **SdkTracerProvider** nếu Spring Boot đã auto-configure một provider; hai pipeline dễ gây trùng spans và khó quản lý shutdown.
- Nếu yêu cầu không mất trace là bắt buộc, dùng tầng buffer bền vững; BatchSpanProcessor in-memory không phải durable queue.

## 13. Theo dõi chính exporter và queue

Không chỉ kiểm tra trace có xuất hiện trong UI hay không. Cần theo dõi cả pipeline export:

| Chỉ số | Ý nghĩa | Dấu hiệu cần chú ý |
| --- | --- | --- |
| Queue size / capacity | Số spans đang chờ so với giới hạn | Queue liên tục gần đầy |
| Spans processed/dropped | Số span đã xử lý, export hoặc bị drop | Tăng lỗi **queue_full** |
| Export duration | Thời gian xử lý mỗi batch | Tăng đồng thời với queue size |
| Export failures | Số lần export thất bại | Lỗi OTLP, timeout, HTTP/gRPC status |
| Batch size | Số span trong mỗi lần gửi | Batch quá nhỏ hoặc liên tục đạt ngưỡng tối đa |
| Collector accepted/refused | Số spans collector nhận hoặc từ chối | Receiver quá tải hoặc memory limiter kích hoạt |

OpenTelemetry SDK Java có thể cung cấp self-observability cho BatchSpanProcessor và exporter, với các metric như:

- **otel.sdk.processor.span.queue.capacity**
- **otel.sdk.processor.span.queue.size**
- **otel.sdk.processor.span.processed**
- **otel.sdk.exporter.span.inflight**
- **otel.sdk.exporter.span.exported**

Tên và mức độ sẵn có phụ thuộc phiên bản SDK và việc bật SDK internal telemetry. Hãy xác minh meter thực tế thay vì mặc định mọi phiên bản Spring Boot đều expose sẵn các tên trên.

Nếu chỉ nhìn backend UI và thấy trace ít, bạn chưa biết nguyên nhân là sampling, queue drop, export timeout, collector reject hay query sai. Self-metrics và log exporter giúp tách các khả năng này.

## 14. Cách kiểm chứng exporter không làm chậm nghiệp vụ

Thực hiện một bài kiểm tra có đối chứng:

1. Chạy ứng dụng Spring Modulith với module entry spans và OTLP exporter hoạt động bình thường.
2. Gửi workload ổn định, đo p50/p95/p99 latency và throughput của endpoint nghiệp vụ.
3. Ghi lại queue size, export duration, lỗi và số spans bị drop.
4. Làm collector phản hồi chậm hoặc tạm ngắt kết nối trong một khoảng thời gian được kiểm soát.
5. Tiếp tục gửi workload và đo lại latency nghiệp vụ; xác nhận request không phải chờ OTLP network round-trip trong mô hình batch.
6. Quan sát queue tăng; khi vượt capacity, kiểm tra số spans drop và log/metrics báo lỗi.
7. Khôi phục collector, quan sát queue được drain và export throughput có vượt tốc độ sinh span để trở về bình thường không.
8. Restart ứng dụng theo graceful shutdown, kiểm tra batch còn trong queue có được flush trong thời gian cho phép không.
9. So sánh kết quả khi sampling thấp hơn và khi sampling cao hơn để xác định trade-off giữa trace coverage và overhead.

### 14.1. Tiêu chí đánh giá

| Kết quả | Đạt yêu cầu? | Diễn giải |
| --- | --- | --- |
| Backend chậm nhưng p95/p99 nghiệp vụ gần baseline | Có | Batch export tách network I/O khỏi request path |
| Queue tăng trong outage rồi giảm sau khi collector hồi phục | Có | Queue hấp thụ được gián đoạn ngắn |
| Queue đầy và span bị drop có cảnh báo | Có về mặt bảo vệ ứng dụng; cần đánh giá mất trace | Bounded queue tránh tăng memory vô hạn |
| Queue đầy nhưng không có metric/log cảnh báo | Chưa đạt | Không thể phát hiện trace bị mất |
| Request latency tăng mạnh khi collector chậm | Chưa đạt | Có thể đang dùng processor/exporter đồng bộ hoặc custom code block |
| Queue không giảm sau khi collector phục hồi | Chưa đạt | Export throughput không theo kịp, retry/timeout hoặc collector vẫn quá tải |

Không đặt mục tiêu “không bao giờ mất trace” bằng cách cho queue tăng vô hạn. Hãy đặt SLO cho telemetry pipeline và xác định rõ ứng dụng ưu tiên tính sẵn sàng nghiệp vụ hay giữ đầy đủ telemetry khi hệ thống quá tải.

## 15. Những lỗi cấu hình thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng **SimpleSpanProcessor** với exporter mạng | Export có thể chạy trên thread kết thúc span | Dùng batch processor qua auto-configuration hoặc cấu hình tương đương |
| Queue không đủ lớn cho burst ngắn | Span bị drop sớm | Ước lượng từ span rate × outage window, đo heap |
| Queue quá lớn để che quá tải lâu dài | Tăng memory, trace vẫn không kịp export | Tăng throughput collector/backend, giảm sample rate, giới hạn queue |
| **max-batch-size** lớn hơn queue size | Cấu hình không hợp lệ hoặc không được chấp nhận | Đảm bảo batch size ≤ queue size |
| Schedule delay quá thấp | Nhiều batch nhỏ, nhiều request mạng | Điều chỉnh theo độ trễ hiển thị cần thiết |
| OTLP timeout quá dài | Worker giữ batch lâu, queue tích tụ | Đặt connect/export timeout hữu hạn và quan sát retry |
| Retry ở nhiều tầng không giới hạn | Retry storm, tải tăng khi backend vừa hồi phục | Giữ retry có backoff/jitter và deadline rõ |
| Sampling 100% trên production | Volume, chi phí và queue pressure tăng | Dùng sampling policy phù hợp |
| Chỉ có app queue, không giám sát collector | Không biết dữ liệu bị từ chối ở downstream | Theo dõi receiver, processor và exporter metrics của Collector |
| Tự tạo OTel SDK song song với Boot | Hai tracer provider, trùng spans hoặc shutdown khó kiểm soát | Dùng một pipeline quản lý rõ ràng |
| Process bị kill trước khi flush | Span còn trong RAM bị mất | Graceful shutdown hoặc buffer bền vững nếu yêu cầu |
| Custom exporter chặn thread kết thúc span | Tăng latency nghiệp vụ | Đặt custom exporter sau batch processor, kiểm tra không thực hiện I/O trong callback đồng bộ |

## 16. Khác biệt cấu hình giữa Spring Boot 3.5 và 4.2

Các namespace cấu hình OpenTelemetry đã thay đổi giữa các dòng Spring Boot. Không copy nguyên YAML Boot 4.2 vào dự án Boot 3.5.

| Nội dung | Spring Boot 3.5 | Spring Boot 4.2 |
| --- | --- | --- |
| Batch queue | **management.tracing.opentelemetry.export.max-queue-size** | **management.opentelemetry.tracing.export.max-queue-size** |
| Batch size | **management.tracing.opentelemetry.export.max-batch-size** | **management.opentelemetry.tracing.export.max-batch-size** |
| Schedule delay | **management.tracing.opentelemetry.export.schedule-delay** | **management.opentelemetry.tracing.export.schedule-delay** |
| Processor timeout | **management.tracing.opentelemetry.export.timeout** | **management.opentelemetry.tracing.export.timeout** |
| OTLP endpoint/timeout | Nhóm **management.otlp.tracing.*** | Nhóm **management.opentelemetry.tracing.export.otlp.*** |

Bảng trên nêu các namespace chính của tài liệu Spring Boot tương ứng; các starter, exporter và cấu hình khác cũng có thể thay đổi. Luôn kiểm tra Appendix Application Properties của **đúng minor/major version** đang dùng.

## 17. Bài thực hành: mô phỏng exporter chậm

**Bối cảnh:** ứng dụng Spring Boot có hai application module **orders** và **payments**. Một request tạo đơn hàng tạo HTTP span và module entry spans. OTLP collector nằm ngoài tiến trình ứng dụng.

Thực hiện:

1. Thêm OpenTelemetry starter phù hợp và Spring Modulith Insight/observability theo BOM dự án.
2. Cấu hình OTLP endpoint, BatchSpanProcessor queue 4096, batch 512 và timeout hữu hạn.
3. Đặt sampling 10% cho profile thử nghiệm; xác nhận trace bình thường xuất hiện trong backend.
4. Ghi baseline p50/p95/p99 latency và throughput với collector khỏe mạnh.
5. Giả lập collector chậm hoặc không truy cập được trong 10 giây; tiếp tục gửi request.
6. Kiểm tra latency nghiệp vụ, queue size, export duration và số span drop.
7. Khôi phục collector; xác nhận queue được drain nếu export throughput lớn hơn span arrival rate.
8. Thử giảm queue để quan sát hành vi khi queue đầy; ghi nhận cảnh báo và số span bị mất.
9. Thử tăng queue rồi so sánh mức dùng heap; không coi queue lớn hơn là giải pháp nếu tốc độ export vẫn thấp hơn tốc độ sinh span.
10. Dừng ứng dụng theo graceful shutdown và kiểm tra spans đã hoàn tất có được flush trước khi process kết thúc hay không.

Mẫu bảng kết quả:

| Chỉ số | Collector bình thường | Collector chậm | Sau khi hồi phục |
| --- | --- | --- | --- |
| p95 latency nghiệp vụ | Ghi baseline | So với baseline | Trở về gần baseline |
| Queue occupancy | Thấp/ổn định | Tăng | Giảm |
| Export failures | Thấp | Có thể tăng | Giảm |
| Dropped spans | Không đáng kể | Có thể tăng nếu queue đầy | Không tăng thêm khi ổn định |
| Export throughput | Đủ xử lý tải | Giảm | Phải vượt span arrival rate để drain queue |

**Tiêu chí đạt:** giải thích được vì sao batch export không chờ network trong request path; cấu hình được queue/batch/timeout; nhận diện được khi queue đầy; chứng minh được tác động bằng latency và export metrics; nêu được giới hạn dữ liệu trong RAM khi shutdown/crash.

## 18. Ghi nhớ

Để exporter không làm chậm nghiệp vụ, hãy thiết kế pipeline theo chuỗi:

~~~text
Module span kết thúc
       ↓
BatchSpanProcessor nhận span
       ↓
Queue hữu hạn trong ứng dụng
       ↓
Worker gửi batch qua OTLP
       ↓
Collector xử lý và chuyển tiếp
       ↓
Trace backend
~~~

Batch export giúp tách network I/O khỏi request thread, nhưng **không phải bảo đảm không mất telemetry**. Queue cần hữu hạn; timeout và retry cần có giới hạn; sampling cần phù hợp; collector cần được giám sát; shutdown phải có thời gian flush. Khi queue đầy, ưu tiên giữ ứng dụng hoạt động và phát hiện span drop thay vì để telemetry làm cạn bộ nhớ hoặc kéo dài request vô hạn.

Với Spring Modulith, module entry spans cung cấp bằng chứng về các operation đi qua ranh giới module. Để kiểm chứng kiến trúc khi vận hành, hãy kết hợp chúng với module graph, Actuator module metadata, event publication metrics và context propagation. Exporter là một phần của pipeline quan sát; độ tin cậy của nó phải được đo và vận hành như một thành phần hạ tầng.

### Tài liệu tham khảo

- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html) — Micrometer Tracing, OTLP starter, sampling và trace export.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html) — OpenTelemetry integration và cấu hình context/observability.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/) — queue, batch, schedule delay, timeout và OTLP exporter properties.
- [OpenTelemetry Java — Manage Telemetry with SDK](https://opentelemetry.io/docs/languages/java/sdk/) — BatchSpanProcessor, SimpleSpanProcessor, SpanExporter, queue và self-observability.
- [OpenTelemetry — OTLP Exporter Specification](https://opentelemetry.io/docs/specs/otel/protocol/exporter/) — timeout, transient error và retry backoff/jitter.
- [OpenTelemetry — Configuration Types Reference](https://opentelemetry.io/docs/specs/otel/configuration/types/) — queue size, batch size, schedule delay và export timeout.
- [OpenTelemetry — Collector Documentation](https://opentelemetry.io/docs/collector/) — receiver, processor, exporter và pipeline collector.
- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html) — module entry spans và observability cho application modules.

> **Lưu ý phiên bản:** ví dụ cấu hình chính trong bài dùng Spring Boot 4.2 và OpenTelemetry OTLP. Spring Boot 3.5 dùng namespace exporter khác; cần đối chiếu tài liệu đúng version và BOM của dự án. Giá trị queue/batch/timeout trong ví dụ là điểm khởi đầu để thử tải, không phải cấu hình tối ưu chung. Bài hoàn thành STEP 4 về mặt nội dung; Content QA chuyên môn thuộc bước riêng.
