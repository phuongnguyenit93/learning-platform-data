# Ảnh hưởng của sampling tới CPU và bộ nhớ

## 1. Vì sao tracing cần sampling?

Trong ứng dụng Spring Boot sử dụng **Spring Modulith**, một request có thể đi qua nhiều application module. Chẳng hạn, module **orders** gọi API của **inventory**, phát event để **notifications** xử lý và chuyển yêu cầu sang **payments**. Spring Modulith có thể tạo module entry spans tại các ranh giới API của module để quan sát các lời gọi đó trong distributed trace.

Tracing rất hữu ích khi điều tra latency, exception và luồng xử lý xuyên module. Tuy nhiên, nếu hệ thống có hàng trăm hoặc hàng nghìn request mỗi giây, mỗi request lại tạo nhiều span, lượng telemetry có thể tăng nhanh. Ứng dụng phải tạo và quản lý span; exporter phải xếp hàng, serialize và gửi dữ liệu; collector phải nhận, xử lý; backend phải lưu trữ và lập chỉ mục. Các bước này tiêu thụ CPU, heap, network và dung lượng lưu trữ.

**Sampling** là cơ chế chọn một phần trace để ghi nhận và export. Mục tiêu là giữ đủ dữ liệu đại diện cho việc điều tra, đồng thời kiểm soát chi phí observability. Sampling không làm cho tracing miễn phí: ngay cả trace không được chọn vẫn có thể cần instrumentation và truyền context để các service/module giữ được quan hệ trace.

Bài **“Ảnh hưởng của sampling tới CPU và bộ nhớ”** thuộc chương **Hiệu năng** của module **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Module này dùng Spring Modulith để sinh tài liệu ranh giới application module và quan sát tương tác giữa các phần trong ứng dụng Spring Boot. Bài học tập trung vào chi phí của span recording/export, cách head sampling và tail sampling hoạt động, cách ước lượng tài nguyên và quy trình đo hiệu năng trước khi chọn sampling ratio.

Sau bài học, bạn có thể:

- Giải thích sampling tác động tới CPU, heap, garbage collection, network và trace backend.
- Phân biệt head sampling, parent-based sampling và tail sampling.
- Hiểu phần overhead vẫn còn khi trace không được sample.
- Ước lượng số span và dung lượng telemetry từ request rate, span count và sampling ratio.
- Cấu hình sampling trong Spring Boot bằng property phù hợp.
- Phân biệt trace sampling với metrics collection và log volume.
- Đo hiệu năng ở các sampling ratio khác nhau và chọn cấu hình dựa trên số liệu.
- Nhận diện dấu hiệu exporter queue đầy, span bị drop và collector quá tải.

## 2. Sampling thay đổi điều gì trong pipeline tracing?

Một pipeline tracing điển hình gồm các bước:

1. Instrumentation quan sát HTTP request, database call, message handler hoặc lời gọi qua module boundary.
2. Tracer tạo span và gắn span vào tracing context.
3. Sampler quyết định trace/span có được ghi nhận hay không.
4. Span được kết thúc, xử lý bởi span processor và chuyển tới exporter nếu được chọn.
5. Exporter gửi span tới collector hoặc trace backend.
6. Collector có thể xử lý, lọc, tail-sample hoặc chuyển tiếp telemetry.
7. Backend lưu trữ và lập chỉ mục để người vận hành tìm kiếm.

~~~mermaid
flowchart TD
    A["HTTP request / module invocation"] --> B["Instrumentation tạo observation/span"]
    B --> C["Sampler quyết định"]
    C -->|Sampled| D["Record span và xử lý"]
    C -->|Not sampled| E["Không export span"]
    D --> F["Span processor / exporter queue"]
    F --> G["Collector / trace backend"]
    G --> H["Lưu trữ và truy vấn trace"]
    E --> I["Context propagation vẫn cần thiết"]
~~~

Sampling sớm ở SDK thường được gọi là **head sampling**. Sampler quyết định khi span được bắt đầu, trước khi biết toàn bộ kết quả của request. Với quyết định không sample, SDK thường không ghi và export span đó. Tuy nhiên, code instrumentation vẫn có thể chạy và tracing context vẫn cần tồn tại để truyền qua các ranh giới.

### 2.1. Những chi phí có thể giảm

Khi head sampler loại trace ngay tại ứng dụng, các chi phí sau thường giảm theo số trace không được ghi nhận:

- Tạo và lưu dữ liệu span có tính ghi nhận (recording).
- Thu thập attributes, events và exception details vào span được ghi.
- Gọi span processors và serialize span để export.
- Sử dụng exporter queue và băng thông gửi trace.
- Collector/backend phải xử lý, lập chỉ mục và lưu các span đã bị loại từ đầu.

Mức giảm thực tế phụ thuộc tracer bridge, instrumentation và cấu hình exporter. Không nên giả định CPU hoặc heap giảm đúng cùng tỷ lệ với sampling probability.

### 2.2. Những chi phí vẫn còn

Ngay cả khi một trace không được sample, ứng dụng vẫn có thể phải trả chi phí cho:

- Instrumentation hooks và kiểm tra context ở HTTP, database, messaging hoặc Spring component.
- Tạo/đọc tracing context và quyết định sampling.
- Inject/extract trace headers giữa các service.
- Context propagation qua executor hoặc Reactor.
- Log correlation hoặc thao tác liên quan tới MDC nếu logging integration vẫn bật.
- Metrics và các quan sát không phụ thuộc trace sampling.

Do đó, sampling 0% không tương đương tracing hoàn toàn tắt. Muốn đo overhead nền của ứng dụng, cần có thêm phép đo khi tracing instrumentation được tắt hoặc không được cài đặt.

## 3. Head sampling và parent-based sampling

**Head sampling** đưa ra quyết định khi trace bắt đầu. Với ratio sampling, sampler chọn một tỷ lệ trace dựa trên trace ID hoặc xác suất. Quyết định này được truyền qua context để các span con biết trace có được sample hay không.

Ví dụ Spring Boot:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.10
~~~

Property nhận giá trị từ 0.0 đến 1.0. Tài liệu Spring Boot hiện hành đặt mặc định 0.1, tức khoảng 10% request/trace được sample để tránh làm trace backend quá tải. Hãy xác minh default và sampler cụ thể theo Spring Boot version, tracer bridge và cấu hình ứng dụng đang dùng.

Một số mức tham khảo:

| Sampling probability | Số trace được chọn kỳ vọng trên 1.000 root trace | Cách dùng |
| ---: | ---: | --- |
| 0.0 | 0 | Kiểm tra behavior khi không export trace; instrumentation vẫn có thể hoạt động |
| 0.01 | 10 | Traffic lớn, cần giảm mạnh volume |
| 0.05 | 50 | Bắt đầu thăm dò chi phí |
| 0.10 | 100 | Mức mặc định thường gặp của Spring Boot |
| 0.25 | 250 | Cần quan sát nhiều hơn cho dịch vụ quan trọng |
| 1.0 | 1.000 | Test, staging có kiểm soát hoặc điều tra sự cố có thời hạn |

Đây là số lượng kỳ vọng, không phải cam kết chính xác cho từng khoảng ngắn. Sampling theo xác suất có dao động thống kê.

### 3.1. Vì sao parent-based quan trọng?

Một request có thể đi qua nhiều service. Nếu mỗi service tự quyết định sampling độc lập cho từng span, trace có thể bị đứt: service đầu ghi span nhưng service sau bỏ span, hoặc ngược lại. Parent-based sampler dùng quyết định của parent context cho span con.

Với W3C Trace Context, cờ sampled trong header traceparent giúp truyền quyết định này. Nếu trace cha đã được sample, các span con thường tiếp tục được sample; nếu trace cha không được sample, các span con tuân theo quyết định đó theo sampler parent-based.

Trong OpenTelemetry, Spring Boot hỗ trợ các lựa chọn sampler như ratio-based và parent-based ratio-based tùy phiên bản. Hãy dùng sampler parent-based phù hợp khi muốn giữ trace xuyên service. Không cấu hình các service độc lập với tỷ lệ không đồng nhất mà không hiểu cách chúng xử lý remote parent sampling flag.

### 3.2. Head sampling có giới hạn gì?

Sampler quyết định trước khi request hoàn tất, vì vậy thường không biết:
- Request cuối cùng có lỗi hay không.
- Latency cuối cùng có vượt ngưỡng hay không.
- Event listener có retry hoặc thất bại sau đó không.
- Trace có chứa một module invocation hiếm gặp nhưng quan trọng hay không.

Nếu một trace không được chọn ở đầu, lỗi xảy ra ở cuối hành trình có thể không có trace đầy đủ để điều tra. Tăng sampling ratio sẽ tăng xác suất giữ lại lỗi, nhưng cũng tăng chi phí.

## 4. Tail sampling và chi phí tại Collector

**Tail sampling** trì hoãn quyết định cho tới khi collector nhận được một phần hoặc toàn bộ spans của trace. Collector có thể chọn giữ trace dựa trên thuộc tính đã quan sát được, ví dụ:
- Trace có span status error.
- Latency tổng thể vượt một ngưỡng.
- Có span thuộc module hoặc operation quan trọng.
- Trace thuộc service/tenant được ưu tiên theo chính sách.
- Giữ một tỷ lệ nhỏ các trace bình thường để làm mẫu đại diện.

Tail sampling có ưu điểm là có thể giữ trace lỗi hoặc chậm dù chúng hiếm. Tuy nhiên, để quyết định sau khi trace đã chạy, collector cần **buffer các span trong một khoảng thời gian** và gom các span của cùng trace về cùng một nơi xử lý.

Chi phí và giới hạn:
- Collector cần heap để giữ span chờ quyết định.
- Cần CPU để đánh giá policy và xử lý buffer.
- Các span từ nhiều service phải được định tuyến nhất quán theo trace ID.
- Nếu trace đến trễ hoặc thiếu span, quyết định tail sampling có thể không dựa trên toàn bộ hành trình.
- Ứng dụng vẫn gửi span tới collector trước khi collector loại trace, vì vậy tail sampling không nhất thiết giảm CPU/network ở ứng dụng hoặc lượng dữ liệu collector phải nhận.
- Cấu hình wait/buffer quá lớn làm tăng memory; quá nhỏ có thể quyết định trước khi đủ span.

~~~mermaid
sequenceDiagram
    participant A as Service A
    participant B as Service B
    participant C as Tail-sampling Collector
    participant P as Trace Backend
    A->>C: Span A
    B->>C: Span B
    Note over C: Buffer spans theo traceId
    C->>C: Đánh giá status, duration, attributes
    C->>P: Export trace được giữ
    Note over C,P: Trace không đạt policy bị loại
~~~

Head sampling và tail sampling có thể được kết hợp theo kiến trúc, nhưng cần hiểu điểm quyết định. Nếu ứng dụng head-sample loại trace trước khi gửi, collector không thể khôi phục những span chưa bao giờ được gửi. Muốn tail sampler quyết định trên nhiều trace hơn, upstream phải gửi đủ dữ liệu tới collector; điều này làm giảm lợi ích tiết kiệm network/CPU ở phía ứng dụng.

## 5. Sampling ảnh hưởng CPU như thế nào?

CPU tracing thường đến từ nhiều phần:

| Thành phần | Công việc | Ảnh hưởng khi tăng sampling |
| --- | --- | --- |
| Instrumentation | Hook vào HTTP, database, messaging, module invocation | Phần lớn vẫn tồn tại; số span recording có thể làm tăng việc xử lý |
| Sampler | Đánh giá quyết định sample | Tăng theo số trace/span được bắt đầu, thường nhỏ so với export nhưng không bằng 0 |
| Span recording | Ghi name, attributes, events, status và timing | Tăng rõ khi nhiều trace được sample |
| Span processor | Xử lý span khi kết thúc, batch hoặc enrich | Tăng theo số span được ghi |
| Serialization | Chuyển span thành payload export | Gần tỷ lệ với số span export |
| Exporter | Batch, gửi HTTP/gRPC và retry | Tăng CPU theo volume và lỗi mạng |
| Collector | Parse, process, tail-sample, route | Tăng theo span ingest và policy |
| Backend | Index, compact, query và retention | Tăng theo ingest và thời gian lưu |

Tỷ lệ CPU không nhất thiết tăng tuyến tính theo sampling ratio. Một exporter có batch tốt có thể xử lý volume tăng mà chi phí mỗi span giảm; ngược lại, queue đầy và retry có thể làm CPU tăng mạnh. Các attributes lớn, exception stack trace và số span trên mỗi request cũng ảnh hưởng chi phí.

### 5.1. Module spans làm tăng số span trên một trace

Trong Spring Modulith, observability có thể tạo module entry spans cho các lời gọi đi qua component API của application module. Một request tạo đơn hàng có thể tạo:
- HTTP server span.
- Span tại module orders.
- Span tại module inventory.
- Span của HTTP client gọi payment service.
- Span tại module notifications khi listener được thực thi.
- Span database hoặc messaging do instrumentation khác tạo.

Số span trên mỗi trace vì thế phụ thuộc độ sâu và số module được gọi. Một hệ thống chia module rõ ràng có thể tạo nhiều span hơn một request chỉ có một tầng xử lý; đó là dữ liệu có giá trị cho việc hiểu kiến trúc, nhưng cũng làm tăng telemetry volume khi trace được sample.

Không nên xóa module instrumentation chỉ để giảm số span trước khi đo. Hãy kiểm tra span nào hữu ích, sampling ratio, attributes, export batch và nhu cầu điều tra trước khi quyết định.

## 6. Sampling ảnh hưởng bộ nhớ như thế nào?

Bộ nhớ được dùng ở nhiều nơi:

### 6.1. Trong ứng dụng

- Span recording giữ tên, context, attributes, events, links và trạng thái.
- Span processor có thể giữ span đã kết thúc trong queue trước khi export.
- Exporter batch gom span thành request.
- Retry hoặc exporter chậm có thể làm queue tích tụ.
- Context propagation giữ dữ liệu context trong phạm vi request/task.

Head sampling giảm số span được ghi và đưa vào exporter queue, nên thường giảm heap dành cho span data và queue. Tuy nhiên, nếu collector tail-sample thì ứng dụng có thể vẫn phải ghi/export tất cả span upstream.

### 6.2. Trong collector

Collector tail-sampling giữ span trong buffer cho tới khi quyết định. Số trace đồng thời, số span mỗi trace, kích thước attributes và thời gian chờ quyết định đều ảnh hưởng memory.

Một cách ước lượng thô:

\[
M_{\text{buffer}} \approx
R_{\text{traces}} \times W_{\text{wait}} \times S_{\text{trace}}
\]

Trong đó:
- \(R_{\text{traces}}\): số trace/giây collector nhận.
- \(W_{\text{wait}}\): thời gian buffer (giây).
- \(S_{\text{trace}}\): dung lượng trung bình của một trace trong buffer.

Công thức này chỉ là mô hình gần đúng; overhead object, map, indexes, batching và allocator có thể làm memory thực tế cao hơn đáng kể.

### 6.3. Trong trace backend

Backend cần memory cho ingest buffers, indexes, cache, compaction và query. Sampling ở application làm giảm số trace gửi tới backend. Tail sampling ở collector cũng giảm số trace được chuyển tiếp/lưu trữ, nhưng collector vẫn phải nhận và buffer dữ liệu trước quyết định.

## 7. Ước lượng telemetry volume bằng một ví dụ

Giả sử một ứng dụng có:
- 800 root request/giây.
- Trung bình 6 spans cho mỗi trace đã sample.
- Dung lượng serialized trung bình 1,5 KB/span trước khi nén.
- Sampling probability là 10%.

Số trace được chọn kỳ vọng:

\[
800 \times 0.10 = 80 \text{ traces/second}
\]

Số span được export:

\[
80 \times 6 = 480 \text{ spans/second}
\]

Dung lượng raw ước lượng:

\[
480 \times 1.5 = 720 \text{ KB/second}
\]

Nếu sample 100% với cùng workload và span count:

\[
800 \times 6 \times 1.5 = 7{,}200 \text{ KB/second}
\]

Tức khoảng 7,2 MB/giây trước khi nén và overhead transport. Trong một giờ, chênh lệch lý thuyết có thể lên tới hàng chục GB dữ liệu span thô.

| Sampling | Trace/giây kỳ vọng | Span/giây | Payload thô/giây |
| ---: | ---: | ---: | ---: |
| 1% | 8 | 48 | 72 KB |
| 5% | 40 | 240 | 360 KB |
| 10% | 80 | 480 | 720 KB |
| 25% | 200 | 1.200 | 1.800 KB |
| 100% | 800 | 4.800 | 7.200 KB |

Đây là ví dụ để ước lượng, không phải số đo thực tế. Kích thước span khác nhau tùy attributes, events, exception, resource metadata, encoding và compression. Một số request có nhiều span hơn mức trung bình; sampling xác suất cũng khiến số trace trong một cửa sổ ngắn dao động.

## 8. Cấu hình sampling trong Spring Boot

Với Spring Boot, property phổ biến để đặt xác suất sampling là:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.10
~~~

Các giá trị hợp lệ trong khoảng từ 0.0 đến 1.0. Ví dụ:
- 0.01: sample khoảng 1% trace.
- 0.10: sample khoảng 10% trace.
- 1.00: sample tất cả trace.
- 0.00: không chọn trace để export theo ratio sampler; instrumentation và propagation vẫn có thể còn overhead.

Spring Boot mặc định sample 10% request theo tài liệu hiện hành nhằm tránh làm trace backend quá tải. Cần xác minh cấu hình sampler đang hoạt động; nếu dùng OpenTelemetry, property sampler cụ thể có thể thay đổi cách áp dụng xác suất và parent decision.

### 8.1. Profile test và production

Trong test integration cần assert span export, có thể dùng sampling 100%:

~~~yaml
# application-test.yml
management:
  tracing:
    sampling:
      probability: 1.0
~~~

Trong production, chọn ratio dựa trên traffic và budget observability. Không để cấu hình test 100% bị đóng gói nhầm hoặc override profile production.

### 8.2. Không đồng nhất sampling với tắt tracing

Ba cấu hình sau có ý nghĩa khác nhau:

| Trạng thái | Ý nghĩa |
| --- | --- |
| Tracing instrumentation không được cài/không bật | Không tạo observation/span tracing từ các integration đó |
| Instrumentation bật, sampling 0% | Có thể vẫn có context propagation và chi phí instrumentation/sampler; span không được ghi/export theo sampler |
| Instrumentation bật, sampling 10% | Một phần trace được ghi và export; các trace còn lại vẫn có thể propagate context |
| Instrumentation bật, sampling 100% | Mọi trace đủ điều kiện được ghi/export, chi phí telemetry cao nhất trong các cấu hình này |

Nếu muốn biết riêng overhead của instrumentation, phải đo cả trường hợp tracing tắt và trường hợp tracing bật nhưng không export. Không dùng hai trường hợp đó thay thế cho nhau.

## 9. Trace sampling không phải metrics sampling

Một lỗi thiết kế là giảm trace sampling rồi cho rằng toàn bộ observability data cũng giảm cùng tỷ lệ.

| Dữ liệu | Bị ảnh hưởng trực tiếp bởi trace sampling? | Ghi chú |
| --- | --- | --- |
| Distributed traces | Có | Trace không được chọn thường không được export từ SDK head sampler |
| Module entry spans | Có | Span thuộc trace không được sample có thể không được export |
| HTTP metrics | Không | Counter/timer vẫn được ghi theo cấu hình metrics |
| module.events.published | Không | Event publication counter của Spring Modulith là meter riêng |
| JVM metrics | Không | CPU, heap, GC metrics không phụ thuộc trace sampler |
| Application logs | Không | Log volume do logging configuration quyết định |
| Log correlation ID | Không nhất thiết | MDC/context có thể còn ID dù trace không có trong backend; phụ thuộc bridge và logging integration |

Spring Modulith cung cấp counter tổng hợp module.events.published và counter cho từng event type. Các meter này không bị giảm chỉ vì trace sampling probability giảm. Nếu cần giảm metric volume, phải giải quyết metric cardinality, meter filtering hoặc scrape policy riêng; không dùng tracing sampler như một công tắc cho metrics.

Logs cũng không tự động giảm theo trace sampling. Nếu ứng dụng log mọi request ở INFO, log volume vẫn có thể cao ngay cả khi chỉ export 10% traces.

## 10. Chọn sampling strategy theo mục tiêu

| Chiến lược | Ưu điểm | Hạn chế | Phù hợp khi |
| --- | --- | --- | --- |
| Head ratio sampling | Quyết định sớm, giảm recording/export ở ứng dụng | Có thể bỏ lỡ lỗi/trace chậm hiếm gặp | Traffic lớn, cần mẫu đại diện và chi phí thấp |
| Parent-based ratio | Giữ quyết định nhất quán xuyên service | Root decision vẫn có thể bỏ lỡ trace quan trọng | Hệ thống distributed nhiều service |
| Tail sampling | Có thể giữ trace lỗi/chậm dựa trên kết quả cuối | Collector cần buffer, memory, CPU và routing nhất quán | Có hạ tầng collector và yêu cầu chọn trace theo kết quả |
| Always-on | Dữ liệu đầy đủ, dễ debug | Tốn tài nguyên và lưu trữ | Test, staging hoặc điều tra production ngắn hạn có kiểm soát |
| Always-off | Không export trace theo sampler | Không có trace để điều tra; instrumentation overhead có thể còn | Kiểm tra đối chứng, không phải cấu hình quan sát lâu dài |

Với hệ thống nhiều module, một điểm bắt đầu thường là parent-based head sampling ở application, sau đó đánh giá nhu cầu giữ trace lỗi/chậm. Nếu cần tail sampling, triển khai ở collector có đủ tài nguyên và bảo đảm tất cả spans cùng trace được route tới cùng decision point.

## 11. Đo CPU và memory thay vì đoán

Muốn chọn sampling ratio phù hợp, cần chạy benchmark với workload đại diện và so sánh nhiều cấu hình.

### 11.1. Ma trận benchmark

Giữ nguyên code, dataset, request mix, concurrency và thời gian chạy; thay đổi sampling:

| Run | Tracing | Sampling | Mục tiêu |
| --- | --- | ---: | --- |
| A | Tắt instrumentation | — | Baseline ứng dụng |
| B | Bật instrumentation | 0% | Đo chi phí instrumentation/context/sampler |
| C | Bật instrumentation | 1% | Đo mức sampling thấp |
| D | Bật instrumentation | 10% | Đo mức mặc định phổ biến |
| E | Bật instrumentation | 25% | Đo mức quan sát cao hơn |
| F | Bật instrumentation | 100% | Đo chi phí tối đa trong test |

Không thay đổi đồng thời exporter, backend và sampling ratio trong cùng một lượt nếu mục tiêu là cô lập tác động của sampling. Nếu cần đo tail sampling, chạy một ma trận riêng cho collector và backend.

### 11.2. Chỉ số cần thu thập

| Nhóm | Chỉ số |
| --- | --- |
| Application CPU | CPU cores/usage, process CPU time |
| Request performance | Throughput, p50/p95/p99 latency, error rate |
| Memory | Heap used/committed, allocation rate, live objects |
| Garbage collection | GC count, pause time, allocation pressure |
| Tracing | Spans created/recorded/exported, exporter queue occupancy, dropped/failed spans |
| Network | Bytes sent/received, exporter request rate |
| Collector | CPU, heap, queue/buffer size, refused/dropped spans |
| Backend | Ingest rate, storage growth, query latency, retention usage |

Dùng cùng warm-up và thời gian đo cho từng run. Lặp lại đủ lần để nhận ra biến động do JIT, GC và noise của môi trường. Ghi lại version Spring Boot, Spring Modulith, tracer bridge, exporter, collector và backend để có thể so sánh lại sau nâng cấp.

### 11.3. Cách diễn giải kết quả

- Nếu tracing off và sampling 0% có CPU gần nhau, phần overhead chủ yếu có thể nằm ở instrumentation/context; cần xem thêm allocation và latency.
- Nếu CPU/heap tăng mạnh từ 0% lên 10%, span recording/processor/export có thể là phần đáng kể.
- Nếu app ổn định nhưng collector memory tăng, xem tail-sampling buffer, batch size và arrival rate.
- Nếu exporter queue thường xuyên đầy hoặc dropped spans tăng, exporter/backend không theo kịp tốc độ gửi.
- Nếu p99 latency tăng nhưng CPU không cao, kiểm tra network exporter, blocking processor hoặc synchronous export.
- Nếu 100% tracing làm backend quá tải, giảm sample ratio chỉ giải quyết một phần; cần kiểm tra retention, ingest capacity, indexing và attributes.

Không kết luận sampling làm CPU giảm bao nhiêu phần trăm từ một benchmark duy nhất. Tác động phụ thuộc request mix, số span/trace, attributes, exporter, network và backend.

## 12. Tuning để giảm chi phí mà vẫn giữ dữ liệu hữu ích

### 12.1. Chọn ratio theo volume và mức quan trọng

- Dịch vụ traffic cao có thể bắt đầu ở tỷ lệ thấp hơn.
- Dịch vụ có traffic thấp hoặc luồng nghiệp vụ quan trọng có thể cần tỷ lệ cao hơn để có đủ trace.
- Các luồng thanh toán, đặt hàng hoặc xử lý lỗi nghiêm trọng cần chiến lược giữ trace phù hợp với yêu cầu điều tra.
- Không tăng sampling đồng loạt cho toàn bộ hệ thống nếu chỉ một service/module cần dữ liệu chi tiết.

### 12.2. Giảm số span và kích thước span có ý nghĩa

Sampling không phải cách duy nhất để giảm telemetry:
- Chỉ instrument những ranh giới đem lại thông tin chẩn đoán hữu ích.
- Tránh tạo span lồng nhau trùng lặp cho cùng một thao tác.
- Giữ attributes có giá trị vận hành; không đính kèm payload lớn hoặc object graph.
- Tránh ghi dữ liệu nhạy cảm vào span attributes/events.
- Dùng module entry spans để thấy ranh giới module, nhưng review các custom observations dư thừa.
- Không xóa module spans quan trọng chỉ vì số lượng span tăng mà chưa xem tác động chẩn đoán.

### 12.3. Tuning exporter và collector

- Ưu tiên batch export bất đồng bộ nếu integration hỗ trợ.
- Theo dõi queue capacity, batch size, export timeout và retry.
- Đảm bảo exporter không block request thread trong đường xử lý thông thường.
- Cấp đủ CPU/heap cho collector theo ingest rate.
- Với tail sampling, chọn buffer window và decision wait phù hợp với độ trễ span đến.
- Giám sát dropped spans, queue saturation và export failures.
- Kiểm tra backend retention và indexing để chi phí không tăng ngoài dự kiến.

Tên property và default cho batch processor/exporter phụ thuộc bridge và version. Không copy giá trị queue/batch từ một phiên bản OpenTelemetry hoặc collector sang hệ thống khác mà chưa xác minh.

## 13. Dấu hiệu sampling hoặc exporter đang gây vấn đề

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| CPU tăng khi bật tracing 100% | Span recording, processors, serialization và export tăng | So sánh tracing off, 0%, 10%, 100% |
| Heap tăng theo traffic | Nhiều span/attributes hoặc exporter queue tích tụ | Kiểm tra allocation, queue và exporter latency |
| GC pause tăng | Span object và attribute allocations tăng | Profile allocation và giảm attributes/span volume |
| Trace bị thiếu span ở service con | Sampler không parent-based hoặc propagation không đúng | Kiểm tra remote parent sampled flag và propagator |
| Trace backend chỉ có ít trace hơn mong đợi | Sampling ratio, exporter failure hoặc backend ingestion | Đối chiếu sampled/recorded/exported/dropped counts |
| Collector heap tăng mạnh | Tail sampling buffer hoặc decision wait quá lớn | Kiểm tra trace rate, buffer size, wait window |
| Collector nhận nhiều dữ liệu nhưng backend lưu ít | Tail sampling loại trace theo policy | Kiểm tra policy và số trace giữ/loại |
| Queue exporter đầy | Exporter/backend không theo kịp span rate | Kiểm tra batch, timeout, network và backend capacity |
| Log có trace ID nhưng không tìm thấy trace | Trace không được sample hoặc export/retention thất bại | Kiểm tra sampling, exporter và backend time range |
| Metrics vẫn nhiều dù giảm trace sampling | Metrics không dùng trace sampler | Kiểm tra meter cardinality và scrape/export metrics riêng |

## 14. Checklist triển khai sampling

| Hạng mục | Điều kiện đạt |
| --- | --- |
| Mục tiêu sampling | Xác định cần giảm application export, collector ingest hay backend storage |
| Sampling strategy | Head/parent-based/tail được chọn theo yêu cầu |
| Ratio | Có số liệu traffic và trace volume để biện minh |
| Context propagation | Quyết định sampling nhất quán qua service/module |
| Module spans | Số span trên mỗi trace được đo và có giá trị chẩn đoán |
| Metrics | Không nhầm trace sampling với metrics collection |
| Logs | Có chính sách log volume và correlation riêng |
| Memory | Theo dõi heap, exporter queue và collector buffer |
| CPU | Đo application và collector dưới cùng workload |
| Exporter | Không có queue saturation hoặc dropped spans ngoài ngưỡng |
| Tail sampler | Có đủ buffer, trace affinity và decision wait |
| Bảo mật | Attributes/events không chứa payload hoặc dữ liệu nhạy cảm |
| Test | Sampling 100% chỉ dùng trong test/staging có kiểm soát |
| Rollout | Thay đổi ratio có giám sát và khả năng rollback |

## 15. Ghi nhớ

**Sampling giảm lượng trace được ghi nhận và export, nhưng không loại bỏ toàn bộ overhead của tracing.** Head sampling quyết định sớm ở ứng dụng nên có thể giảm span recording, exporter queue, network và backend ingest. Instrumentation, sampler và context propagation vẫn có chi phí. Tail sampling chọn trace sau khi collector nhận spans, vì vậy có thể giữ trace lỗi/chậm nhưng cần buffer, CPU và memory tại collector; ứng dụng vẫn phải gửi dữ liệu upstream.

Trong Spring Modulith, số module entry spans trên mỗi request phụ thuộc số ranh giới module được đi qua. Đo span count cùng request rate để ước lượng volume; không nhầm trace sampling với metrics như module.events.published hoặc log volume. Chọn sampling ratio bằng benchmark cùng workload, theo dõi CPU, heap, GC, exporter queue, dropped spans và backend ingest. Mục tiêu là giữ đủ trace có ích để vận hành trong giới hạn tài nguyên thực tế.

## Tài liệu tham khảo

- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): sampling probability, sampler và trace export.
- [Spring Boot — Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html): cấu hình management.tracing.sampling.probability.
- [OpenTelemetry — Sampling](https://opentelemetry.io/docs/concepts/sampling/): head sampling, tail sampling, chi phí và trade-off.
- [OpenTelemetry Collector — Tail Sampling Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/tailsamplingprocessor): policy, buffer và tail sampling tại collector.
- [OpenTelemetry — Batch Span Processor](https://opentelemetry.io/docs/specs/otel/trace/sdk/#batching-processor): batch export và queue behavior.
- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): module entry spans và event publication metrics.
- [Micrometer Tracing — Sampling](https://docs.micrometer.io/tracing/reference/sampling.html): sampler abstraction và cấu hình tracing bridge.

> **Giới hạn:** Sampling behavior, sampler names, exporter queue và processor defaults phụ thuộc Spring Boot, Micrometer Tracing, tracer bridge và OpenTelemetry Collector version. Ví dụ volume chỉ là ước lượng với giả định đã nêu, không thay thế benchmark. Khi thay đổi cấu hình, xác minh trace completeness, metrics/logs và resource usage trên môi trường có tải đại diện.
