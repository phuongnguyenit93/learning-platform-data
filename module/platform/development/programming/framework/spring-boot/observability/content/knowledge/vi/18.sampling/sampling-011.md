# Đánh đổi chi phí và độ quan sát

Trong chương **Sampling** của mô-đun **SPRING_BOOT_OBSERVABILITY**, sampling là quyết định chọn trace nào được ghi nhận và gửi tới hệ thống quan sát. Sampling giúp kiểm soát lưu lượng telemetry, dung lượng lưu trữ và chi phí backend, nhưng mỗi trace bị loại cũng đồng nghĩa mất một phần chi tiết có thể cần khi điều tra. Mục tiêu không phải giảm số trace xuống thấp nhất, mà là giữ đủ bằng chứng để hiểu lỗi, độ trễ và hành vi ứng dụng trong môi trường thực.

Với Spring Boot, chính sách sampling cần được xem cùng **Micrometer Observation, Micrometer Tracing, exporter, Collector, metrics và logs**. Tỷ lệ cố định có thể phù hợp với traffic thông thường nhưng bỏ sót lỗi hiếm; sampling quá cao có thể làm Collector và backend quá tải; head sampling thiếu nhất quán giữa các service có thể làm trace bị đứt. Bài này trình bày cách đánh giá các đánh đổi và xây dựng chính sách có thể kiểm chứng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích sampling ảnh hưởng thế nào tới số trace được giữ, chi phí ingest và khả năng điều tra.
2. Phân biệt head sampling, parent-based sampling và tail sampling.
3. Ước lượng volume spans, bytes và chi phí lưu trữ theo traffic, sampling ratio và retention.
4. Chọn sampling policy theo workload, SLO, giao dịch quan trọng và yêu cầu điều tra.
5. Hiểu vì sao head sampling cần quyết định nhất quán xuyên dịch vụ.
6. Giải thích giới hạn của tail sampling khi trace có nhiều service, nhiều Collector hoặc spans đến trễ.
7. Dùng metrics và logs để bù phần thống kê và sự kiện mà trace sampling không giữ.
8. Kiểm soát cardinality, baggage, attributes và dữ liệu nhạy cảm.
9. Triển khai thay đổi sampling theo giai đoạn và đo coverage, dropped spans, tác động backend.

## 2. Sampling giải quyết vấn đề gì?

Một trace thường gồm nhiều spans. Nếu API xử lý 2.000 request/giây và mỗi request tạo trung bình 8 spans, hệ thống có thể tạo khoảng 16.000 spans/giây trước sampling. Khi có nhiều service, retry, batch job hoặc fan-out, volume tăng nhanh.

Sampling quyết định phần trace được ghi nhận:

- **Sampling quá cao:** tăng ingest, serialization, network, Collector memory/queue và chi phí lưu trữ/index.
- **Sampling quá thấp:** giảm bằng chứng cho lỗi hiếm, tail latency, giao dịch quan trọng và hành vi bất thường.
- **Sampling thiếu nhất quán:** một service giữ span trong khi service khác bỏ, làm waterfall không đầy đủ.
- **Sampling thiếu quan sát:** không biết dữ liệu mất ở sampler, exporter, Collector hay backend.

**Trace sampling không phải request sampling cho metrics.** Counter, timer và histogram của Micrometer có thể tiếp tục tổng hợp mọi request được instrument, trong khi chỉ một phần traces được lưu. Không lấy số trace backend làm request count hoặc mẫu số SLO.

## 3. Ba lớp quyết định sampling

### Head sampling

Head sampling quyết định có ghi trace ngay khi trace bắt đầu, thường trước khi biết request cuối cùng thành công hay thất bại và mất bao lâu.

Ví dụ giữ 10% trace trong Spring Boot/Micrometer Tracing ở phiên bản hỗ trợ:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
~~~

Ưu điểm là quyết định sớm, giảm số spans phải serialize và gửi khỏi ứng dụng, hạn chế network và Collector load. Đây là cách đơn giản khi chỉ cần một mẫu đại diện của traffic thông thường.

Giới hạn là sampler chưa biết request sẽ lỗi hay chậm tại thời điểm quyết định. Một lỗi hiếm có thể rơi vào trace bị loại. Nếu các service quyết định độc lập, trace phân tán có thể không đầy đủ.

### Parent-based sampling

Parent-based sampling cho phép service con tuân theo sampling decision đã có trong parent context. Nếu service A quyết định sample trace, service B tiếp tục ghi spans thuộc trace đó; nếu parent được đánh dấu không sample, service con thường tuân theo quyết định tương ứng.

Điều này quan trọng với distributed tracing: các service cần giữ cùng trace context và tôn trọng sampling decision được propagate. Nếu một service tự tạo root trace hoặc ghi đè policy không chủ đích, dữ liệu có thể bị tách hoặc không nhất quán.

### Tail sampling

Tail sampling quyết định sau khi Collector nhận được một phần hoặc đủ spans của trace. Policy có thể chọn trace dựa trên thông tin chỉ biết khi request kết thúc, ví dụ:

- Trace có span status lỗi.
- Duration vượt ngưỡng.
- Có operation hoặc service quan trọng.
- Trace thuộc nhóm traffic được ưu tiên.

Ưu điểm là có thể giữ trace lỗi/chậm mà không cần giữ mọi request bình thường. Nhưng Collector phải nhận spans trước khi quyết định, giữ trạng thái tạm thời, chờ các span liên quan và có đủ năng lực để gom spans của cùng trace.

**Tail sampling không thể phục hồi span đã bị head sampler loại trước khi export.** Nếu ứng dụng không gửi trace tới Collector, Collector không có dữ liệu để phân loại và giữ lại.

| Tiêu chí | Head sampling | Parent-based | Tail sampling |
| --- | --- | --- | --- |
| Thời điểm quyết định | Khi trace bắt đầu | Theo quyết định parent | Sau khi Collector nhận spans |
| Biết kết quả cuối request | Không | Không, trừ thông tin đã có ở parent | Có thể, nếu đủ spans tới trước timeout |
| Giảm network từ ứng dụng | Có | Có khi parent quyết định bỏ | Thường không; spans phải tới Collector |
| Ưu điểm | Đơn giản, chi phí upstream thấp | Giữ quyết định nhất quán | Ưu tiên lỗi/chậm theo dữ liệu cuối |
| Giới hạn | Có thể bỏ lỗi hiếm | Phụ thuộc propagation và parent decision | Tốn memory/CPU, cần gom spans đúng trace |

Các chiến lược có thể được kết hợp. Cần hiểu rõ head sampling ở SDK và tail sampling tại Collector để không vô tình loại trace quan trọng trước khi tail policy có cơ hội xử lý.

## 4. Ước lượng chi phí trước khi chọn tỷ lệ

Một mô hình đơn giản:

- Request rate: số request mỗi giây.
- Average spans per request: số span trung bình trên một trace.
- Sampling ratio: tỷ lệ trace được giữ.
- Average span size: kích thước span sau serialization/encoding.
- Retention: thời gian backend lưu dữ liệu.

~~~text
spans_per_second =
    requests_per_second
    * average_spans_per_request
    * sampling_ratio

bytes_per_second =
    spans_per_second
    * average_serialized_span_bytes

daily_ingest_bytes =
    bytes_per_second * 86400
~~~

Ví dụ giả định:

| Thông số | Giá trị |
| --- | ---: |
| Request rate | 2.000 request/giây |
| Trung bình | 8 spans/request |
| Sampling ratio | 10% |
| Dung lượng span trung bình | 1,5 KB |

Ước lượng: 200 trace/giây được giữ; 1.600 spans/giây; payload thô khoảng 2,4 MB/giây; tương đương khoảng 207 GB/ngày theo đơn vị thập phân.

Đây là phép tính payload thô, không phải hóa đơn backend. Kích thước thực tế còn phụ thuộc attributes, events, resource metadata, compression, batching, protocol overhead, indexing, replication và retention.

### Sampling ratio không phải phần trăm tiết kiệm chính xác

Giảm từ 100% xuống 10% có thể giảm mạnh lượng trace được gửi, nhưng không có nghĩa chi phí toàn hệ thống giảm đúng 90%. Instrumentation vẫn chạy; Collector, metrics, logs, indexing overhead và baseline cost vẫn tồn tại.

Để dự toán, hãy đo spans/second trước và sau sampling, exported bytes, exporter queue/retry, Collector received/sent/refused/dropped spans, backend ingest/index growth, query latency, retention, replication và CPU/memory.

## 5. Chọn sampling theo giá trị trace

Không phải request nào cũng có cùng giá trị điều tra.

| Loại traffic | Mục tiêu quan sát | Cách cân nhắc |
| --- | --- | --- |
| Request đọc thông thường, tải lớn | Hiểu đường đi phổ biến và latency baseline | Head sampling tỷ lệ vừa phải có thể đủ. |
| Thanh toán/đặt hàng quan trọng | Có bằng chứng cho luồng tác động lớn | Cân nhắc policy giữ nhóm giao dịch đã xác minh. |
| Request lỗi | Điều tra lỗi hiếm và exception | Tail sampling có thể ưu tiên error status nếu nhận đủ spans. |
| Request rất chậm | Hiểu tail latency và dependency | Tail sampling theo duration có thể hữu ích. |
| Health checks/noise traffic | Tránh ingest cho request ít giá trị | Cân nhắc bỏ hoặc giữ tỷ lệ rất thấp theo policy. |
| Batch job | Theo dõi bước quan trọng hoặc job failure | Dùng operation naming và policy riêng, tránh trace quá lớn. |

Không đưa raw customer ID, email, order ID hoặc token vào sampling attributes. Dùng thuộc tính phân nhóm có số giá trị hữu hạn như operation name hoặc transaction class. Giá trị dùng cho policy ưu tiên phải đến từ nguồn đáng tin cậy, không thể bị caller giả mạo để chiếm tài nguyên ingest.

### Xác định rõ thế nào là lỗi

Một server span có status lỗi là tín hiệu hữu ích, nhưng business rejection có thể là response 4xx không phải exception. Ngược lại, lỗi ở client span có thể không được phản ánh trên server span downstream. Policy cần xác định rõ muốn giữ trace theo status của bất kỳ span nào, status của entry server span, exception/error event, duration toàn trace hay attribute nghiệp vụ đã kiểm soát.

Đừng mặc định mọi HTTP 4xx là lỗi hệ thống; xác định semantics nghiệp vụ và SLO.

## 6. Spring Boot: cấu hình xác suất sampling

Ví dụ Spring Boot 3.x với Micrometer Tracing và OpenTelemetry bridge:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    implementation 'io.opentelemetry:opentelemetry-exporter-otlp'
}
~~~

Ví dụ giữ toàn bộ trace ở lab:

~~~yaml
spring:
  application:
    name: order-api

management:
  tracing:
    sampling:
      probability: 1.0
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
~~~

Sampling 100% giúp quan sát spans khi xác minh instrumentation và exporter trên môi trường thử nghiệm. Không mang cấu hình này thẳng lên production với traffic lớn nếu chưa đánh giá capacity và retention.

Ví dụ production thử nghiệm với sampling 5%:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.05
~~~

Đây chỉ là giá trị minh họa. Tỷ lệ phù hợp phải được đo theo traffic, spans mỗi trace, kích thước attributes, backend capacity và yêu cầu điều tra. Nếu dùng Brave bridge hoặc custom sampler bean, cách cấu hình/độ ưu tiên có thể khác; kiểm tra cấu hình thực tế của Spring Boot và tracer implementation.

### Cẩn trọng với custom sampler

Khi khai báo sampler riêng, hãy xác minh sampler đó được dùng bởi tracer/SDK mà Micrometer Tracing bridge đang kết nối. Tự tạo một OpenTelemetry SDK độc lập có thể khiến spans từ Micrometer và code OTel trực tiếp đi theo hai pipeline khác nhau, context không chia sẻ, resource attributes hoặc exporter khác nhau.

Chỉ thêm custom bean khi có nhu cầu cụ thể và hiểu rõ auto-configuration đang bị thay thế hay mở rộng ở đâu.

## 7. Parent-based sampling và trace completeness

Trong request đi qua nhiều dịch vụ, service đầu vào thường tạo root/server span. Khi gọi downstream, client instrumentation inject trace context và sampling flags. Service con extract context rồi đưa ra quyết định phù hợp với parent-based policy.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as order-api
    participant B as inventory-api
    participant X as Trace backend

    C->>A: HTTP request
    Note over A: Root decision: sample / drop
    A->>B: RPC + trace context + sampling flags
    Note over B: Theo parent decision
    B-->>A: Response
    A-->>C: Response
    A->>X: Export spans nếu được sample
    B->>X: Export spans nếu được sample
~~~

Nếu order-api quyết định sample trace nhưng inventory-api tự dùng root sampler độc lập và quyết định drop, backend có thể thấy root và client span mà thiếu server span của inventory. Các lỗi thường gây trace không đầy đủ:

- Một service không extract đúng W3C Trace Context hoặc B3.
- Client instrumentation không inject headers.
- Context mất qua async/thread boundary.
- Một service dùng custom sampler không parent-based.
- Các service dùng tracer/version khác nhau nhưng propagation không liên thông.
- Exporter/backend drop một phần dữ liệu hoặc spans tới muộn.

Khi thấy trace thiếu service, kiểm tra **trace ID, parent span ID, propagation và sampler ở từng hop** trước khi tăng sampling ratio toàn hệ thống.

## 8. Tail sampling tại OpenTelemetry Collector

Tail sampling hữu ích khi muốn giữ traces dựa trên thông tin chỉ biết sau khi request hoàn thành. Ví dụ cấu hình minh họa:

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
    limit_mib: 1024
  tail_sampling:
    decision_wait: 10s
    num_traces: 50000
    policies:
      - name: keep-errors
        type: status_code
        status_code:
          status_codes: [ERROR]
      - name: sample-normal
        type: probabilistic
        probabilistic:
          sampling_percentage: 5
  batch: {}

exporters:
  debug:
    verbosity: basic

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, tail_sampling, batch]
      exporters: [debug]
~~~

Đây là cấu hình minh họa, không phải production config dùng nguyên trạng. Cần kiểm tra phiên bản và distribution Collector: tail sampling processor phải có trong bản triển khai; thứ tự processor ảnh hưởng dữ liệu; debug exporter chỉ nên dùng để kiểm thử. Production cần exporter tới backend, TLS/auth, queue/retry và giới hạn resource phù hợp.

Các tham số:

- **decision_wait:** thời gian Collector chờ nhận thêm spans trước khi quyết định.
- **num_traces:** giới hạn số trace giữ trong trạng thái tail sampling; cần căn cứ traffic.
- **status_code:** policy minh họa giữ trace có status ERROR.
- **probabilistic:** policy minh họa giữ một tỷ lệ trace bình thường.
- **memory_limiter:** bảo vệ Collector trước áp lực bộ nhớ; ngưỡng cần tính theo giới hạn process/container.

Không có cam kết rằng mọi lỗi sẽ được giữ. Span lỗi có thể tới sau thời gian chờ, không tới do exporter drop, hoặc spans của một trace được chuyển tới nhiều Collector khác nhau.

### Tail sampling cần đủ spans

Nếu một trace phân tán có spans đi đến nhiều Collector độc lập, mỗi Collector chỉ nhìn thấy một phần. Tail sampler có thể quyết định từ dữ liệu không đầy đủ hoặc tạo quyết định khác nhau. Kiến trúc thường cần routing/trace affinity để các spans của cùng trace tới đúng nơi xử lý.

Điều này tạo đánh đổi: tail sampling giữ trace quan trọng tốt hơn, nhưng tăng yêu cầu stateful routing, memory, network và độ phức tạp vận hành.

## 9. Kết hợp head và tail sampling

Một chiến lược kết hợp có thể là:

1. Ứng dụng dùng parent-based sampler để giữ decision nhất quán trong toàn trace.
2. Ứng dụng không gửi một số trace rõ ràng là noise/low-value nếu điều đó không phá mục tiêu điều tra.
3. Trace được gửi tới Collector được tail sampler phân loại theo error, duration và policy.
4. Collector export trace đã chọn tới backend.
5. Metrics và logs tiếp tục thu thập theo pipeline riêng.

Tuy nhiên, **head sampling 5% rồi tail sampling không thể giữ lỗi nằm trong 95% đã bị bỏ tại ứng dụng**. Nếu muốn Collector quyết định giữ lỗi sau khi nhìn thấy, ứng dụng phải gửi dữ liệu liên quan tới tầng tail sampler, hoặc head policy phải bảo đảm nhóm giao dịch đó được gửi.

## 10. Sampling và metrics: bù phần tổng hợp

Metrics cung cấp thống kê tổng hợp trên traffic, phù hợp với request rate, error rate, latency histogram và saturation. Metrics không mặc định bị giảm theo trace sampling ratio.

| Nhu cầu điều tra | Nguồn phù hợp |
| --- | --- |
| Request rate và error rate toàn dịch vụ | Counter/rate và HTTP server metrics. |
| P95/P99 theo route | Timer histogram và truy vấn backend metrics. |
| Một request đã đi qua đâu | Trace nếu được sample và lưu; correlation ID trong logs. |
| Exception message, business event | Logs có cấu trúc. |
| Dependency nào kéo latency lên | Client/server spans kết hợp dependency metrics. |
| Áp lực JVM/GC/connection pool | Runtime và application metrics. |

Ví dụ PromQL cho error ratio:

~~~promql
sum(rate(http_server_requests_seconds_count{
  job="order-api",status=~"5.."
}[5m]))
/
sum(rate(http_server_requests_seconds_count{
  job="order-api"
}[5m]))
~~~

Tên series và labels phụ thuộc exporter/instrumentation. Xác minh payload thực tế, xử lý mẫu số bằng 0 và lọc đúng service/route. Query này dùng metrics, không phải traces.

Khi tỷ lệ trace thấp, hãy giữ metrics histogram đủ cho SLO và logs có correlation phù hợp. Metrics cho biết vấn đề xảy ra ở đâu và thường xuyên đến mức nào; traces được sample giúp hiểu một đường thực thi cụ thể.

## 11. Sampling không thay thế kiểm soát cardinality

Một trace có thể chứa nhiều attributes và events. Giảm số trace nhưng giữ hàng trăm attributes dài trên mỗi span vẫn tạo payload lớn và chi phí index.

- Dùng span names ổn định, tránh gắn order ID hoặc user ID vào tên.
- Dùng low-cardinality tags cho metrics như operation, outcome, method và route template.
- Chỉ thêm high-cardinality trace attributes khi có mục đích điều tra cụ thể.
- Không đưa token, cookie, email, số thẻ hoặc request body vào trace/baggage.
- Giới hạn events lặp lại hoặc stack traces quá lớn.
- Đánh giá resource attributes để tránh tạo quá nhiều nhóm service instance không cần thiết.

Sampling giảm số trace/record được giữ; cardinality/attribute policy giảm độ lớn và số index dimensions của từng record. Nên đo cả hai.

## 12. Baggage và sampling

Baggage được propagate cùng context có thể giúp policy phân loại trace theo metadata nhỏ, nhưng phải kiểm soát giá trị đến từ bên ngoài. Ví dụ field có thể hữu ích nếu được xác minh và allowlist: request class, tenant tier hoặc region.

Không dùng customer ID, email, session ID hoặc token để quyết định ưu tiên sampling. Caller không được quyền tự gắn nhãn “premium” nhằm buộc hệ thống giữ trace hoặc ảnh hưởng tài nguyên. Giá trị quyết định chính sách cần được xác minh ở trust boundary hoặc do service tin cậy tạo ra.

Tail-sampling policy có thể dùng attributes như transaction class, nhưng phải xác minh Collector nhìn thấy attribute đó trên đúng span. Baggage có trong context không có nghĩa nó tự động trở thành span attribute; instrumentation/processor phải chủ động ghi hoặc chuyển đổi nếu cần.

## 13. Logs và correlation khi trace bị sample out

Khi trace bị head sampler bỏ, backend có thể không có trace dù ứng dụng vẫn tạo logs. Vì vậy:

- Giữ logging cho exception và business events có ý nghĩa.
- Dùng correlation/request ID có kiểm soát; trace ID chỉ liên kết được với trace nếu trace được lưu.
- Không log toàn bộ baggage hoặc gRPC metadata.
- Không coi việc không tìm thấy trace là bằng chứng request không chạy.
- Giữ metrics đủ coverage để phát hiện error rate và latency drift.

Có thể có trace ID trong log nhưng backend không tìm thấy trace vì sampling. Đây là kết quả có thể xảy ra, không nhất thiết là lỗi exporter. Khi điều tra, dùng timestamp, service, route, request ID đã được quản lý và metrics để khôi phục bối cảnh.

## 14. Sampling và distributed trace completeness

| Tình huống | Dấu hiệu | Rủi ro |
| --- | --- | --- |
| Root sample, child drop | Có span entry nhưng thiếu downstream server span | Waterfall không đầy đủ. |
| Root drop, child tự sample | Trace con không có parent span | Span rời không thể liên kết đầy đủ. |
| Một service không propagate context | Trace ID thay đổi giữa các service | Phân tích sai quan hệ dependency. |
| Tail sampling phân tán nhiều Collector | Backend có các phần trace khác nhau | Policy quyết định trên dữ liệu không đầy đủ. |
| Span tới sau decision_wait | Một số span mất khỏi trace đã giữ | Trace thiếu phần hoàn tất. |

Khi chọn sampler cho OpenTelemetry hoặc Brave, xác minh parent-based behavior và propagation format mà các service hỗ trợ. Nếu hệ thống hỗn hợp, test W3C/B3 tại gateway và mọi ranh giới HTTP/gRPC/message.

## 15. Runbook: điều chỉnh sampling khi chi phí tăng

Giả sử backend tracing tăng ingest gấp ba sau triển khai. Không nên giảm sampling ngay toàn hệ thống mà chưa tìm nguyên nhân volume.

1. **Xác định nơi tăng:** service nào tăng spans/giây, attributes bytes hoặc events? Do traffic, retry loop hay instrumentation trùng?
2. **Kiểm tra sampling decision:** tỷ lệ ở từng service, parent-based behavior và custom sampler có ghi đè không.
3. **Đo kích thước span:** attributes, events, exception stack trace, baggage và resource metadata có tăng không.
4. **Kiểm tra Collector:** received/sent/refused/dropped spans, exporter queue/retries, tail sampler state, memory và CPU.
5. **Kiểm tra backend:** ingest bytes, index growth, retention và query cost.
6. **Xác định nhóm trace có giá trị:** lỗi, slow requests, giao dịch quan trọng, batch job hoặc noise traffic.
7. **Thử policy trong staging/canary:** so sánh coverage lỗi, p95/p99, complete traces và chi phí.
8. **Rollout có kiểm soát:** áp dụng theo service/traffic cohort, theo dõi dropped spans và backend health.
9. **Xác nhận SLO evidence:** metrics histogram/error rate và logs vẫn có coverage.
10. **Ghi lại policy:** owner, lý do, ngưỡng review và cách rollback.

Không giảm sampling để che lỗi Collector hoặc backend. Nếu exporter queue đầy vì backend timeout, giảm lượng trace có thể giảm áp lực tạm thời nhưng nguyên nhân ingest failure vẫn phải được xử lý.

## 16. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Ít trace hơn tỷ lệ dự kiến | Parent decision, custom sampler, traffic mix hoặc exporter drop. | Kiểm tra sampled flags, sampler config và pipeline counters. |
| Không tìm thấy trace lỗi | Head sampler đã drop; error không được ghi status; Collector/backend drop. | So sánh error metrics/logs với sampling decision và Collector stats. |
| Có root span nhưng thiếu service con | Propagation/sampler không nhất quán hoặc downstream không instrument. | Kiểm tra traceparent/B3 và parent-based sampler. |
| Tail sampler không giữ trace chậm | Attribute/duration không nằm trên span policy xét, span đến muộn hoặc trace bị phân tán. | Kiểm tra policy input, thời gian chờ và trace routing. |
| Collector tăng memory mạnh | Tail sampling giữ quá nhiều state hoặc trace duration dài. | Kiểm tra số trace, thời gian chờ, traffic và memory limiter. |
| Trace count giảm nhưng ingest bytes không giảm tương ứng | Span size/attributes lớn hoặc metrics/logs cùng backend chiếm volume. | Đo bytes/span và tách tín hiệu. |
| Traces nhiều hơn request count dự kiến | Nhiều spans mỗi request, retry hoặc duplicate instrumentation. | Phân tích spans/trace và client/server instrumentation. |
| Logs có trace ID nhưng backend không có trace | Trace bị sample out hoặc exporter/backend drop. | Kiểm tra sampler và trace pipeline. |
| Metrics cũng giảm theo sampling | Instrumentation/handler hoặc query bị ảnh hưởng ngoài dự kiến. | Kiểm tra MeterRegistry và metrics scrape riêng. |
| Backend quá tải dù sampling thấp | High cardinality, retention/indexing, số service hoặc payload lớn. | Đo dimensions, bytes, index, queries và storage policy. |

## 17. Bài tập tự kiểm tra

### Bài 1 — Ước lượng volume

Một service nhận 500 request/giây, mỗi request tạo trung bình 10 spans, sampling 20%. Ước lượng spans/giây được giữ.

**Đáp án:** 500 × 10 × 0,2 = **1.000 spans/giây**. Đây là ước lượng trước exporter drops, instrumentation khác hoặc trace fan-out.

### Bài 2 — Head sampling bỏ lỗi hiếm

Một API dùng head sampling 1%. Một request lỗi đã bị sampler loại lúc bắt đầu. Tail sampler tại Collector có giữ được trace đó không?

**Đáp án:** Không. Collector không nhận được spans đã bị head sampler bỏ. Muốn tail sampling phân loại trace, ứng dụng phải gửi dữ liệu liên quan tới Collector.

### Bài 3 — Metrics nhiều hơn traces

Metrics ghi nhận 100.000 requests trong một giờ nhưng backend chỉ có khoảng 5.000 traces. Có nghĩa 95.000 requests bị mất khỏi ứng dụng không?

**Đáp án:** Không thể kết luận. Tỷ lệ này có thể phản ánh sampling 5%. Metrics và tracing là pipeline riêng; kiểm tra sampler, exporter và Collector để biết traces được loại theo chủ đích hay bị drop.

### Bài 4 — Tail sampling có lỗi nhưng không giữ

Một trace có lỗi ở service C nhưng backend chỉ lưu spans của A và B. Nêu hai nguyên nhân có thể.

**Đáp án:** Span lỗi của C đến sau thời gian chờ hoặc không được export; hoặc spans cùng trace được định tuyến tới Collector khác nhau nên tail sampler không nhìn đủ trace. Cũng cần kiểm tra status/error attribute có được gắn đúng.

### Bài 5 — Có nên tăng sampling để sửa trace đứt?

Service A và B có trace IDs khác nhau. Có nên tăng probability từ 10% lên 100%?

**Đáp án:** Không giải quyết nguyên nhân. Cần kiểm tra context propagation, W3C/B3 compatibility, client/server instrumentation và async boundaries. Sampling ratio thay đổi số trace được chọn, không nối hai context khác nhau.

### Bài 6 — Vì sao chi phí không giảm 90%?

Sampling giảm từ 100% xuống 10% nhưng hóa đơn backend giảm ít hơn 90%. Nêu ba yếu tố có thể giải thích.

**Đáp án:** Chi phí nền tảng/index/replication vẫn tồn tại; kích thước span tăng do attributes/events; metrics/logs hoặc pipeline khác vẫn chiếm ingest; retention/query và storage overhead không giảm cùng tỷ lệ.

## 18. Checklist xây dựng sampling policy

- [ ] Đã xác định mục tiêu điều tra và các nhóm request có giá trị khác nhau.
- [ ] Đã đo traffic, spans/request, span size và ingest trước khi đặt tỷ lệ.
- [ ] Hiểu rõ head sampling và parent-based sampling ở từng service.
- [ ] Nếu dùng tail sampling, Collector nhận đủ spans và routing phù hợp theo trace.
- [ ] decision wait, số trace tối đa, memory limit và traffic peak đã được capacity planning.
- [ ] Có policy cho error, slow traces, business-critical operations và noise traffic.
- [ ] Không dùng dữ liệu nhạy cảm hoặc giá trị caller có thể giả mạo làm điều kiện ưu tiên.
- [ ] Trace context propagation và sampled flags nhất quán giữa HTTP, gRPC và messaging.
- [ ] Metrics vẫn giữ coverage cho request count, error rate, latency histogram và SLO.
- [ ] Logs giữ exception/business events và correlation theo policy ngay cả khi trace bị sample out.
- [ ] Có dashboard cho received/sampled/exported/dropped spans, exporter queue và backend ingest.
- [ ] Đo cả số spans và bytes; kiểm soát attributes/events/cardinality.
- [ ] Thay đổi sampling được thử trên staging/canary, có tiêu chí rollback.
- [ ] Có owner, lý do và thời điểm review policy khi traffic hoặc SLO thay đổi.

**Ghi nhớ:** Sampling là quyết định phân bổ ngân sách quan sát. Head sampling giảm chi phí sớm nhưng không biết kết quả request; parent-based sampling giúp trace nhất quán; tail sampling có thể ưu tiên lỗi/chậm nhưng đòi hỏi Collector nhận đủ spans và có năng lực giữ state. Hãy dùng metrics để giữ thống kê tổng thể, logs để lưu sự kiện cần thiết và traces được chọn để hiểu đường thực thi. Chính sách tốt giữ được bằng chứng quan trọng trong giới hạn chi phí, không phải chính sách có tỷ lệ thấp nhất.
