# Trace sampling budget trong Spring Boot

Distributed tracing tạo telemetry tỷ lệ với request traffic, số spans trên mỗi trace và kích thước attributes. Nếu giữ mọi trace, hệ thống có thể vượt ingest capacity, tăng chi phí network/storage/indexing và làm truy vấn chậm. Nếu sampling quá thấp hoặc đặt sai vị trí, trace quan trọng như request lỗi, latency cao hoặc dependency failure có thể bị bỏ mất. **Trace sampling budget** là ngân sách có thể đo lường cho việc ghi nhận, xử lý, truyền và lưu traces, nhằm cân bằng khả năng điều tra với tài nguyên.

Trong module SPRING_BOOT_OBSERVABILITY, sampling budget liên kết Micrometer Tracing, OpenTelemetry, Collector, exporters và backend. Bài tập trung vào ước lượng trace volume, lựa chọn head/tail sampling, ưu tiên lỗi và slow traces, phân bổ capacity cho Collector/backend, kiểm soát attribute size/cardinality, kiểm thử policy và vận hành sampling an toàn.

## Mục tiêu học tập

1. Giải thích sampling và sampling budget trong distributed tracing.
2. Ước lượng trace/span volume từ request rate và spans per trace.
3. Phân biệt head sampling, tail sampling và probabilistic sampling.
4. Thiết kế policy ưu tiên lỗi, latency cao và traffic quan trọng.
5. Hiểu propagation của sampling decision qua distributed services.
6. Tính toán Collector memory, throughput, queue và backend ingest.
7. Phân biệt trace sampling với metrics aggregation và retention.
8. Kiểm soát attribute size, cardinality và dữ liệu nhạy cảm.
9. Kiểm thử sampling policy, dropped spans và trace completeness.

## 1. Trace sampling budget là gì?

Sampling quyết định trace nào được ghi nhận và chuyển tiếp. Sampling budget đặt giới hạn cho lượng traces/spans mà hệ thống có thể xử lý trong một khoảng thời gian hoặc chi phí xác định.

Budget cần bao gồm:
- số request/second đi qua hệ thống;
- tỷ lệ request tạo trace;
- số spans trung bình và phân phối spans/request;
- kích thước span attributes, events và links;
- bytes/second qua ứng dụng và Collector;
- Collector memory/CPU/queue capacity;
- backend ingest/indexing/storage capacity;
- retention và query workload.

Không thể chỉ chọn một sampling probability mà không đo các yếu tố trên.

### 1.1. Từ request tới trace volume

Một trace thường chứa server span, client spans, database spans và business spans. Một request có thể tạo vài spans hoặc hàng trăm spans nếu có fan-out, ORM N+1 hoặc nhiều async tasks.

~~~text
Request
  ├─ HTTP server span
  ├─ Business span
  ├─ HTTP client span
  ├─ JDBC span
  └─ Additional child spans
          |
          v
      Trace payload
          |
          v
    Collector / Backend
~~~

Số spans trên mỗi trace và kích thước span có thể biến động lớn. Dùng p50/p95/p99 và workload profile thay vì chỉ dùng trung bình.

## 2. Ước lượng ngân sách trace

Một mô hình ban đầu:
- R: incoming requests per second;
- S: average spans per request/trace;
- P: head sampling probability;
- B: average serialized bytes per span.

Khi mỗi request tạo một trace và sampling độc lập ở head:

\[
\text{sampled traces/sec} \approx R \times P
\]

\[
\text{sampled spans/sec} \approx R \times S \times P
\]

\[
\text{ingest bytes/sec} \approx R \times S \times P \times B
\]

Ví dụ service nhận 2.000 requests/second, trung bình 12 spans/trace, sampling 5%, mỗi span trung bình 1,2 KB:

- Sampled traces: 2.000 × 0,05 = 100 traces/second.
- Sampled spans: 2.000 × 12 × 0,05 = 1.200 spans/second.
- Payload thô: 1.200 × 1,2 KB = 1,44 MB/second.

Đây là ước lượng payload thô. Protocol framing, compression, retries, replication, indexing và backend overhead có thể làm tài nguyên thực tế khác đáng kể.

### 2.1. Tính theo peak traffic

Không chỉ tính theo average RPS. Nếu traffic tăng gấp ba trong peak, spans/second và bytes/second cũng có thể tăng tương ứng. Dùng peak sustained traffic và burst profile để chọn headroom.

### 2.2. Phân phối spans không đồng đều

Request đơn giản có thể có 4 spans; request fan-out có thể có 80. Dùng histogram spans/trace và p95/p99 để phát hiện outliers. Một ít trace cực lớn có thể chiếm tỷ lệ đáng kể memory/bytes dù trace count thấp.

### 2.3. Kích thước attributes

Span có nhiều attributes, events, stack traces hoặc baggage có thể lớn hơn nhiều so với span đơn giản. Giới hạn attribute count, string length, event count, stack trace size, baggage keys/values, captured headers và SQL text. Giảm span size thường hiệu quả hơn chỉ tăng sampling khi attributes không cần thiết được ghi vào mọi trace.

## 3. Head sampling

Head sampler quyết định ghi trace khi trace bắt đầu, thường ở root span. Quyết định được đưa ra trước khi biết toàn bộ kết quả request.

Ưu điểm:
- giảm spans và CPU sớm;
- dễ dự đoán ingest rate;
- không cần giữ toàn bộ trace trong Collector;
- hỗ trợ distributed decision khi trace context truyền sampling flags.

Hạn chế:
- không biết request có lỗi hoặc chậm ở cuối;
- trace bị drop ở đầu có thể không được ghi đầy đủ ở downstream;
- sampling probability tĩnh có thể không phù hợp khi traffic thay đổi.

### 3.1. Parent-based sampling

Parent-based sampler thường tôn trọng sampling decision của parent. Nếu root trace được sampled, downstream spans tiếp tục sampled; nếu parent không sampled, child spans thường không được ghi/export theo decision đó. Cách này giúp trace nhất quán xuyên service.

### 3.2. Probability sampler

Ví dụ cấu hình Spring Boot sampling probability:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.05
~~~

Giá trị minh họa 5%. Property và tracing bridge cần khớp Spring Boot version. Sampling probability không phải tỷ lệ chính xác trong từng phút; với traffic nhỏ, số trace thực tế dao động thống kê.

### 3.3. Head sampling không thể ưu tiên lỗi chưa xảy ra

Nếu trace bị drop tại root vì sampling decision, lỗi xảy ra sau đó không thể làm sampler quay ngược thời gian để giữ trace. Muốn ưu tiên errors/slow traces, cần tail sampling hoặc chiến lược giữ đủ dữ liệu tới nơi ra quyết định.

## 4. Tail sampling

Tail sampling trì hoãn quyết định cho tới khi Collector nhận đủ spans của trace hoặc hết decision wait window. Collector có thể giữ trace nếu có span error, latency vượt ngưỡng, operation/service quan trọng, traffic class được ưu tiên hoặc trace được chọn ngẫu nhiên để đại diện traffic bình thường.

Ưu điểm là quyết định dựa trên outcome cuối. Hạn chế là Collector phải giữ state/buffers cho traces đang chờ, cần nhận spans từ nhiều services và xử lý trace arrival trễ.

### 4.1. Trace affinity

Các spans của cùng Trace ID cần tới cùng tail-sampling decision point. Nếu spans bị chia tới nhiều Collector độc lập, mỗi Collector chỉ thấy một phần trace và có thể quyết định sai hoặc export trace không đầy đủ. Cần routing theo Trace ID tới đúng Collector/decision tier hoặc kiến trúc có state coordination.

### 4.2. Decision wait và late spans

Collector chờ một khoảng decision wait để nhận thêm spans. Wait quá ngắn có thể bỏ sót spans đến trễ; quá dài làm tăng memory và thời gian export. Chọn dựa trên end-to-end span arrival distribution và trace duration, không chỉ thời gian request trung bình.

### 4.3. Tail sampling không miễn phí

Tail sampling giảm dữ liệu lưu ở backend nhưng vẫn phải ingest và giữ candidate spans trước khi ra quyết định. Nó chuyển một phần chi phí từ backend storage sang Collector memory/CPU/network. Budget phải tính cả unsampled candidate traffic.

## 5. Kết hợp head và tail sampling

Một kiến trúc có thể dùng head sampling để giới hạn traffic trước Collector, rồi tail sampling chọn trace quan trọng trong phần traffic còn lại. Nhưng nếu head sampler drop trace, tail sampler không thể khôi phục trace đó.

Ví dụ:
- head sampling giữ 20% traffic;
- tail sampling giữ errors trong 20% đó;
- tail sampling giữ 10% successful traces còn lại.

Policy này chỉ bảo đảm errors trong tập đã được head sampler chuyển tiếp. Nếu yêu cầu giữ gần như mọi lỗi, head sampling phải cho phép đủ traffic tới tail tier hoặc dùng adaptive/consistent sampling phù hợp.

### 5.1. Quy tắc ưu tiên

Một policy tail sampling có thể ưu tiên:
1. traces có error status;
2. traces vượt latency threshold;
3. traces có operation critical;
4. một tỷ lệ successful traces để baseline;
5. bỏ các trace còn lại khi budget đầy.

Không nên chỉ giữ errors: cần baseline successful traces để so sánh latency và hiểu behavior bình thường.

### 5.2. Adaptive sampling

Adaptive sampling điều chỉnh sampling rate theo traffic hoặc budget. Khi RPS tăng, rate có thể giảm để giữ spans/second trong giới hạn; khi traffic thấp, rate có thể tăng. Distributed services cần decision propagation/consistency để không tạo partial traces. Thay đổi rate cần smoothing và guardrails để tránh dao động.

## 6. Distributed sampling và propagation

Sampling decision được mang theo trace context. Với W3C Trace Context, traceparent chứa trace ID, parent span ID và trace flags; sampled flag cho downstream biết trace có được recording theo decision hiện tại hay không.

~~~text
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
                                                                 ^^
                                                           sampled flag
~~~

Các service cần thống nhất sampling strategy. Nếu service A sampled nhưng service B tự drop, trace có thể thiếu database/client spans. Nếu service B tạo root trace mới thay vì tiếp tục context, liên kết phân tán bị mất.

### 6.1. Parent-based consistency

Dùng parent-based strategy khi muốn downstream tôn trọng sampling decision của upstream. Với message queues, trace context cần được inject vào message headers và extract ở consumer; consumer spans tiếp tục đúng trace hoặc dùng links tùy messaging semantics.

### 6.2. Trust boundary

Không nhất thiết tin sampling flag từ mọi external caller. Public ingress có thể áp dụng sampler/normalization riêng trước khi truyền decision vào nội bộ. Nếu external caller có thể ép sampled=true cho mọi request, backend có thể bị flood. Thiết kế trust boundary tại gateway/ingress.

## 7. Ngân sách cho OpenTelemetry Collector

Collector nhận telemetry, xử lý processors và export tới backend. Với tail sampling, nó còn giữ trace state. Cần budget cho receiver throughput, processor CPU, memory limiter, batch queues, tail sampling cache, exporter queue/retry và network egress.

### 7.1. Memory limiter

Memory limiter processor giúp Collector từ chối/backpressure dữ liệu khi memory tiến gần giới hạn. Đặt limit theo container memory và để headroom cho runtime/components khác. Nếu limiter liên tục từ chối, cần giảm input, tăng capacity hoặc sửa backend bottleneck; không tăng memory vô hạn.

### 7.2. Batch processor và exporter queue

Batch processor gom telemetry để giảm overhead network. Exporter sending queue hấp thụ backend chậm trong thời gian ngắn. Queue quá lớn có thể giữ nhiều dữ liệu trong memory/disk và tăng delay; queue quá nhỏ có thể drop khi burst.

### 7.3. Tail sampling capacity

Tail sampling cần memory tỷ lệ với số traces đang chờ, số spans/trace và payload size. Ước lượng:

\[
\text{buffer memory} \approx
\text{in-flight traces} \times
\text{avg spans/trace} \times
\text{avg bytes/span} \times
\text{overhead factor}
\]

Overhead factor phụ thuộc implementation và data structures; cần benchmark/load test thay vì giả định bằng 1.

### 7.4. Collector scaling

Tail sampling state cần trace-aware routing. Scale Collector bằng random load balancing có thể chia spans cùng trace sang nhiều replicas. Dùng routing theo Trace ID trước tail-sampling tier hoặc architecture có decision coordination. Test trace completeness khi scale và khi một Collector restart.

## 8. Backend ingest, storage và retention budget

Sampling chỉ là một phần chi phí. Backend cần xử lý ingest, indexing, query, replication và retention.

Một mô hình daily storage thô:

\[
\text{GB/day} \approx
\frac{\text{bytes/sec} \times 86.400}{1.000.000.000}
\]

Với 1,44 MB/second, payload thô khoảng 124 GB/day trước compression/replication/index overhead. Compression có thể giảm storage; indexing và replication có thể làm tổng chi phí tăng. Dùng số đo backend thực tế để lập ngân sách.

### 8.1. Retention theo trace class

Có thể áp dụng retention khác nhau cho error traces, slow traces, normal sampled traces, critical workflow traces và synthetic test traces. Backend phải hỗ trợ phân loại và policy tương ứng. Không giả định mọi trace backend có retention theo attribute; đôi khi cần routing sang tenants/datasets khác nhau.

### 8.2. Storage budget và query budget

Giữ trace lâu hơn làm tăng khả năng điều tra incident cũ nhưng cũng tăng storage/indexing cost. Traces nhiều attributes làm query/indexing nặng hơn. Theo dõi ingest bytes, stored bytes, query latency, dropped spans và retention expiry.

## 9. Sampling không thay thế metrics

Metrics thường được aggregate và giữ tỷ lệ đầy đủ theo meter recording; tracing sampling chỉ chọn một phần traces. Nếu muốn request rate/error ratio/latency SLI chính xác, không tính trực tiếp từ sampled traces khi sampling không đồng đều hoặc adaptive.

| Nhu cầu | Nguồn phù hợp |
| --- | --- |
| Request rate | Metrics |
| Error ratio/SLO | Metrics |
| p95/p99 latency theo endpoint | Metrics histogram |
| Một request cụ thể qua nhiều service | Trace |
| Dependency call sequence | Trace |
| Pool saturation | Metrics |
| Error detail và stack context | Logs/traces theo policy |

Nếu dùng trace-derived metrics, phải hiểu sampling bias và cách backend tính extrapolation. Metrics instrumentation nên hoạt động độc lập với trace sampling decision.

## 10. Cardinality, privacy và payload budget

Trace sampling giảm số traces nhưng không tự loại bỏ dữ liệu nhạy cảm hoặc attribute cardinality. Mỗi sampled span vẫn có thể chứa payload quá lớn.

Giảm payload bằng cách allowlist HTTP headers, không capture request/response bodies mặc định, redact tokens/cookies/query secrets, normalize SQL và bỏ bind values, giới hạn baggage, event count và string length, tránh exception message chứa user data, và bỏ attributes không có mục đích điều tra.

### 10.1. Span count budget

Đặt budget cho spans/trace theo operation class. Nếu một endpoint bất ngờ tạo 500 spans do N+1 queries hoặc fan-out, sampling 5% vẫn có thể tạo payload lớn. Theo dõi p95/p99 spans per trace và cảnh báo bất thường.

### 10.2. Trace size budget

Đặt giới hạn span attribute count, event count và payload bytes nếu SDK/backend hỗ trợ. Khi truncate/drop attributes, giữ metadata cần thiết như operation, status, service identity và timing. Ghi nhận telemetry bị dropped/truncated để biết budget có đang làm giảm khả năng điều tra hay không.

## 11. Kiểm thử sampling budget

| Test | Mục tiêu |
| --- | --- |
| Sampler unit test | Decision theo parent/status/attributes |
| Statistical test | Tỷ lệ sampled gần kỳ vọng trên số lượng đủ lớn |
| Distributed propagation test | Các service giữ cùng trace decision |
| Tail sampling test | Error/slow traces được giữ |
| Late span test | Decision wait xử lý spans đến trễ |
| Collector load test | Memory/queue/throughput dưới peak |
| Backend ingest test | Không vượt ingest budget |
| Privacy test | Attributes nhạy cảm không được export |
| Failure test | Collector/backend outage có queue/drop behavior dự kiến |

### 11.1. Test head sampling

Tạo số lượng trace đủ lớn với deterministic trace IDs hoặc sampler test hooks. Xác minh parent sampled decision được giữ qua child spans. Với probability sampler, tỷ lệ thực tế dao động; dùng khoảng tin cậy phù hợp thay vì assert con số chính xác trên mẫu nhỏ.

### 11.2. Test tail sampling

Gửi trace có error status, duration trên threshold, success bình thường và operation critical. Xác minh policy giữ đúng class và drop class còn lại. Kiểm tra toàn bộ spans của Trace ID được export cùng nhau, kể cả spans đến chậm trong decision window.

### 11.3. Load test Collector

Tạo peak traffic mô phỏng với spans/trace và attribute sizes gần production. Theo dõi memory, CPU, queue length, refused spans, exporter failures và tail decision latency. Thử Collector restart để hiểu traces đang buffered có mất hay không.

## 12. Troubleshooting sampling budget

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Backend ingest vượt budget | RPS/spans/trace/size tăng | Recalculate volume, adaptive/head sampling và payload limits |
| Không thấy error traces | Head sampler drop trước khi biết outcome | Tail sampling hoặc error-aware strategy |
| Trace chỉ có một phần services | Sampling decision không nhất quán hoặc propagation mất | Parent-based sampling và context tests |
| Tail sampler bỏ sót spans | Decision wait ngắn hoặc routing sai | Tăng wait có căn cứ, trace-ID routing |
| Collector OOM | Tail buffers/queues quá lớn | Memory limiter, capacity và queue budget |
| Exporter queue đầy | Backend chậm hoặc outage | Scale/repair backend, bounded queue và alert |
| Trace size bất thường | N+1/fan-out/events/attributes lớn | Span count/size budget và instrumentation review |
| Sampling rate dao động | Adaptive policy thiếu smoothing | Rate limits, hysteresis và observability |
| Metrics SLI lệch | Dùng sampled traces làm nguồn đếm | Dùng metrics recording độc lập |
| Trace storage tăng dù sample rate ổn định | Attribute size hoặc spans/trace tăng | Theo dõi bytes/span và spans/trace |
| Collector replicas có partial traces | Trace affinity không đúng | Route theo Trace ID tới tail-sampling tier |
| Không thể tìm trace cũ | Retention ngắn hoặc sai tenant | Kiểm tra retention, routing và policy |

### 12.1. Quy trình điều tra

1. Đo RPS và số trace được tạo.
2. Đo spans/trace p50/p95/p99 và serialized bytes/span.
3. So sánh sampling decisions ở ingress, service và Collector.
4. Kiểm tra propagation headers và parent-based behavior.
5. Xem Collector memory, queue, refused/dropped spans và exporter errors.
6. Kiểm tra backend ingest/storage/query capacity.
7. Xác minh retention policy và trace routing.
8. Đối chiếu metrics SLI độc lập với trace sampling.

## 13. Production checklist

| Tiêu chí | Bằng chứng |
| --- | --- |
| Volume model có dữ liệu thật | RPS, spans/trace, bytes/span |
| Peak budget được tính | Peak sustained và burst |
| Sampling strategy được ghi rõ | Head/tail/parent/adaptive |
| Error/slow trace policy | Test case chứng minh giữ trace |
| Distributed decision nhất quán | Parent context propagation |
| Tail sampling trace affinity | Routing theo Trace ID |
| Collector memory/queue budget | Load test và alert |
| Backend ingest/storage budget | Bytes/day, retention, replication |
| Metrics độc lập sampling | SLI không tính từ sampled traces |
| Payload/cardinality giới hạn | Attributes/events/baggage allowlist |
| Privacy trước export | Redaction test |
| Dropped spans được quan sát | Collector/exporter metrics |
| Policy thay đổi có kiểm soát | Versioned config và rollout |
| Failure behavior rõ | Backend outage/Collector restart tests |

## 14. Bài thực hành: lập trace sampling budget cho order-service

**Bối cảnh:** order-service nhận 1.500 requests/second ở peak, mỗi trace trung bình 15 spans, p95 35 spans và serialized span size trung bình 1 KB. Backend có ingest budget giới hạn; đội vận hành muốn giữ error traces và slow traces trong khi vẫn có baseline successful traces.

**Nhiệm vụ:**
1. Tính spans/second và bytes/second nếu head sampling 10%.
2. Ước lượng daily payload trước compression/replication.
3. Đo spans/trace p50/p95/p99 bằng workload test.
4. Chọn parent-based head sampling hoặc tail sampling và giải thích trade-off.
5. Thiết kế policy ưu tiên error, latency cao và critical operations.
6. Nếu dùng tail sampling, cấu hình trace-ID routing và decision wait.
7. Tính Collector in-flight trace memory và exporter queue budget.
8. Đặt limits cho span attributes, events, baggage và SQL/HTTP capture.
9. Xác minh metrics SLI vẫn đầy đủ khi trace sampling thay đổi.
10. Load test peak/burst và theo dõi refused/dropped spans.
11. Mô phỏng Collector/backend outage và xác minh queue/backpressure.
12. Viết runbook điều chỉnh sampling khi traffic hoặc backend capacity thay đổi.

**Kết quả mong đợi:** volume model, sampling policy có lý do, Collector/backend budget, test evidence, privacy limits và runbook.

## 15. Ghi nhớ

Trace sampling budget cần tính từ request rate, spans per trace và bytes per span, rồi cộng overhead của Collector, network, backend indexing, replication và retention. Head sampling giảm tải sớm nhưng không thể ưu tiên lỗi phát sinh sau quyết định; tail sampling có thể giữ errors/slow traces nhưng cần buffer, memory, decision wait và routing theo Trace ID. Kết hợp head và tail cần hiểu tail sampler chỉ quyết định trên spans đã tới được nó.

Sampling không thay thế metrics: request rate, error ratio và SLO nên được đo bằng metrics recording độc lập. Theo dõi dropped/refused spans, Collector queues, bytes/span và spans/trace để biết budget có bị vượt. Giảm payload bằng allowlist/redaction trước export, giới hạn baggage và tránh dynamic identifiers. Kiểm thử policy xuyên service và dưới peak load; điều chỉnh sampling có versioning, guardrails và runbook.

**Tài liệu tham khảo:**
- [OpenTelemetry — Sampling](https://opentelemetry.io/docs/concepts/sampling/)
- [OpenTelemetry — Trace SDK Sampling](https://opentelemetry.io/docs/specs/otel/trace/sdk/#sampling)
- [OpenTelemetry Collector — Tail Sampling Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/tailsamplingprocessor)
- [OpenTelemetry Collector — Memory Limiter Processor](https://github.com/open-telemetry/opentelemetry-collector/tree/main/processor/memorylimiterprocessor)
- [OpenTelemetry Collector — Load Balancing Exporter](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/exporter/loadbalancingexporter)
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Micrometer Tracing — Reference](https://docs.micrometer.io/tracing/reference/)

