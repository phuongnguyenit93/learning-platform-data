# Async exporter trong Spring Boot observability

Ứng dụng tạo metrics, logs và spans nhanh hơn tốc độ một backend telemetry có thể nhận dữ liệu trong một số thời điểm. Nếu mỗi request phải chờ gửi telemetry qua mạng, exporter có thể làm tăng latency của business request hoặc khiến ứng dụng phụ thuộc trực tiếp vào tình trạng của monitoring backend. **Async exporter** tách việc ghi nhận telemetry khỏi việc truyền dữ liệu: ứng dụng ghi vào một hàng đợi/buffer, một worker gom batch và gửi dữ liệu ở nền.

Bài **Async exporter** thuộc chương **Hiệu năng observability** của module **SPRING_BOOT_OBSERVABILITY**. Module hướng dẫn thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; học context propagation, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

Sau bài học, bạn có thể mô tả pipeline export bất đồng bộ, hiểu queue/batch/backpressure/drop/retry, phân biệt Micrometer registry với OpenTelemetry BatchSpanProcessor, chọn timeout và batch limits, xử lý shutdown an toàn, và theo dõi chính pipeline telemetry để phát hiện mất dữ liệu hoặc exporter backlog.

## 1. Vì sao cần export bất đồng bộ?

Exporter gửi telemetry từ process tới backend hoặc collector. Nếu gửi đồng bộ trên đường đi của request, latency của exporter có thể cộng trực tiếp vào latency của ứng dụng. Nếu backend tạm unavailable, business thread có thể bị chặn hoặc phát sinh lỗi ngoài ý muốn.

Async export thường có các bước:

1. Instrumentation tạo observations/spans/log records hoặc cập nhật meters.
2. SDK/registry ghi dữ liệu vào buffer hoặc queue.
3. Worker lấy dữ liệu theo batch.
4. Exporter serialize và gửi qua OTLP/HTTP, OTLP/gRPC hoặc protocol của registry.
5. Collector/backend nhận và lưu dữ liệu.

```mermaid
flowchart LR
    A["Application threads"]
    B["Telemetry SDK / registry"]
    C["Bounded queue"]
    D["Batch worker"]
    E["Exporter"]
    F["Collector"]
    G["Observability backend"]
    A --> B --> C --> D --> E --> F --> G
```

Queue tạo vùng đệm giữa tốc độ sinh telemetry và tốc độ export. Nó giúp hấp thụ burst ngắn, nhưng không thể giữ dữ liệu vô hạn nếu backend ngừng nhận trong thời gian dài.

## 2. Async không có nghĩa là miễn phí

Async export chuyển chi phí từ request thread sang bộ nhớ, worker threads và network I/O. Những chi phí này vẫn thuộc process:

- Buffer dùng heap/direct memory.
- Worker cần CPU để serialize, compress và gửi.
- Queue tạo độ trễ giữa lúc span kết thúc và lúc backend nhận span.
- Khi queue đầy, SDK phải block, drop hoặc áp dụng policy khác.
- Khi process crash trước khi flush, dữ liệu trong memory queue có thể mất.

Vì vậy, cần thiết kế async export như một pipeline có capacity, latency budget và failure policy. Không chỉ bật async rồi mặc định telemetry sẽ luôn được giao.

## 3. Phân biệt các thành phần trong pipeline

| Thành phần | Trách nhiệm |
| --- | --- |
| Instrumentation | Tạo observations/spans/log records hoặc cập nhật meters |
| SDK/registry | Quản lý lifecycle, processors, aggregation và export |
| Queue/buffer | Giữ telemetry chờ xử lý |
| Batch processor | Gom nhiều records để giảm số lần gửi |
| Exporter | Chuyển dữ liệu sang protocol/transport |
| Collector | Nhận, xử lý, batch, filter, retry và route telemetry |
| Backend | Lưu trữ, truy vấn, dashboard và alert |

Một ứng dụng Spring Boot có thể dùng Micrometer cho metrics và Micrometer Tracing/OTel bridge cho traces. Cách export của từng signal không nhất thiết giống nhau: Prometheus thường scrape metrics từ endpoint; OTLP traces thường được push qua exporter; logs có thể đi qua logging appender/agent hoặc OTLP pipeline.

Không gọi tất cả các đường đi đó là một async exporter duy nhất. Xác định signal và owner cụ thể trước khi cấu hình.

## 4. Micrometer registry và OpenTelemetry batch processor

Micrometer cung cấp facade cho metrics và Observation. Registry quản lý meter state/aggregation và export theo semantics của từng registry. Ví dụ Prometheus registry thường expose scrape endpoint; backend scrape định kỳ, không nhất thiết dùng queue push bất đồng bộ như span exporter.

Với OpenTelemetry tracing, BatchSpanProcessor nhận ended spans, đưa chúng vào queue, gom batch rồi gọi SpanExporter ở worker. Cơ chế này giảm công việc export trên application thread.

Các khái niệm cấu hình thường gặp của batch processor:

- maxQueueSize: giới hạn số spans chờ.
- maxExportBatchSize: số spans tối đa trong một lần export.
- scheduleDelay: khoảng chờ trước khi worker export batch.
- exportTimeout: thời gian tối đa cho một lần export.

Tên property/env vars và default values phụ thuộc OTel SDK/version và cách Spring Boot cấu hình SDK. Hãy kiểm tra version đang được dependency management chọn; không copy defaults từ một SDK release khác.

## 5. Cấu hình OTLP exporter trong Spring Boot

Spring Boot có thể cấu hình tracing export qua OTLP khi dependencies và auto-configuration tương ứng có mặt. Ví dụ minh họa:

```yaml
management:
  tracing:
    sampling:
      probability: 0.1
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
```

Endpoint, protocol và property prefix cần xác minh theo Spring Boot version. Một số setup dùng OTLP/gRPC với endpoint/port khác; không trộn HTTP path /v1/traces với gRPC endpoint. Nếu dùng OTel SDK tự cấu hình, cấu hình batch processor và exporter theo đúng SDK properties hoặc bean wiring của ứng dụng.

Giữ endpoint/credentials ngoài source code. Dùng environment/configuration management và secret manager theo deployment platform. Không bật exporter thứ hai nếu agent hoặc Spring Boot đã sở hữu provider và export pipeline.

## 6. Queue size và batch size

Queue size giới hạn lượng telemetry có thể chờ export. Batch size quyết định số records được gửi trong một request export.

| Tham số | Quá nhỏ | Quá lớn |
| --- | --- | --- |
| Queue size | Dễ drop khi burst ngắn | Tốn memory, giữ nhiều dữ liệu cũ |
| Batch size | Nhiều request nhỏ, overhead cao | Payload lớn, serialize/transport tốn CPU và dễ timeout |
| Schedule delay | Export thường xuyên, batch ít đầy | Telemetry tới backend trễ hơn |
| Export timeout | Dễ fail khi backend chậm | Worker có thể bị chiếm lâu |

Không có một giá trị tối ưu cho mọi service. Đo spans/second, kích thước trung bình của span, network throughput, backend ingest capacity và memory budget trước khi chọn.

Một ước lượng sơ bộ cho queue memory:

\[
\text{Queue memory} \approx
\text{queued items} \times \text{average in-memory item size}
\]

Đây chỉ là ước lượng. Object overhead, attributes, events, links, string storage và batch copies có thể làm footprint lớn hơn serialized payload.

## 7. Backpressure và queue đầy

Backpressure là cách pipeline phản ứng khi producer tạo telemetry nhanh hơn consumer/exporter xử lý. Các policy thường gặp:

- **Drop newest:** bỏ records mới khi queue đầy; dữ liệu cũ có cơ hội được export.
- **Drop oldest:** loại records cũ để giữ dữ liệu mới hơn, nếu implementation hỗ trợ.
- **Block producer:** chặn thread tạo telemetry cho tới khi queue có chỗ; có thể làm tăng business latency.
- **Bounded wait/reject:** chờ trong giới hạn rồi bỏ dữ liệu.

Policy cụ thể phụ thuộc SDK/processor. Không giả định mọi exporter đều cho phép chọn mọi policy. OTel BatchSpanProcessor có behavior được định nghĩa bởi implementation; kiểm tra docs/version trước khi dựa vào một policy.

Với tracing, drop spans có thể làm trace thiếu một số đoạn nhưng không nên làm request nghiệp vụ thất bại. Tránh để telemetry export failure truyền exception về business path trừ khi đó là yêu cầu rất đặc biệt và đã được thiết kế.

## 8. Retry, timeout và duplicate delivery

Exporter có thể retry khi gặp lỗi transient như timeout, connection reset hoặc HTTP 5xx. Retry cần có giới hạn:

- Dùng timeout cho mỗi export attempt.
- Dùng exponential backoff và jitter nếu exporter/collector hỗ trợ.
- Giới hạn retry duration và số lần thử.
- Tránh retry vô hạn khiến queue không bao giờ drain.
- Quan sát retry count và export failure.

Một lần timeout không chứng minh collector chưa nhận payload. Nếu exporter retry, có thể xảy ra duplicate delivery tùy protocol và backend. Trace/span IDs giúp nhận diện cùng telemetry item, nhưng không nên giả định mọi backend deduplicate hoàn toàn.

Không tự viết retry loop quanh một exporter đã có retry policy nếu không hiểu tương tác; có thể nhân số lần gửi và làm backlog lớn hơn.

## 9. Shutdown và flush dữ liệu

Khi Spring Boot nhận SIGTERM, process cần có thời gian để hoàn tất requests, đóng resources và flush telemetry queue. Nếu container bị kill ngay, dữ liệu còn trong buffer có thể mất.

Một shutdown strategy cần:

1. Ngừng nhận traffic mới và bắt đầu graceful shutdown.
2. Cho business work đang chạy hoàn tất trong termination grace period.
3. Gọi shutdown/close của SDK/provider/exporter để flush dữ liệu theo lifecycle được hỗ trợ.
4. Đặt timeout flush nhỏ hơn tổng shutdown budget.
5. Kết thúc process trước khi orchestrator gửi SIGKILL.

Spring Boot hoặc OTel integration có thể tự quản lý lifecycle. Không tự gọi shutdown nhiều lần hoặc đóng provider khi application context vẫn cần dùng. Xác minh lifecycle owner trong cấu hình thực tế.

Ví dụ Kubernetes terminationGracePeriodSeconds phải đủ cho cả application drain và telemetry flush, nhưng không nên đặt quá dài chỉ để cố gửi hết dữ liệu khi collector đang down.

## 10. Export metrics, traces và logs có semantics khác nhau

| Signal | Cách export thường gặp | Điều cần quan sát |
| --- | --- | --- |
| Metrics | Pull/scrape hoặc push registry exporter | Scrape failures, scrape duration, series count, export errors |
| Traces | Batch processor push exporter | Queue occupancy, dropped spans, export latency/failures |
| Logs | Appender/agent/OTLP pipeline | Appender queue, blocked appenders, dropped log events |

Ví dụ Prometheus scrape không cần queue trong ứng dụng theo cùng cách BatchSpanProcessor dùng queue. Nếu metrics registry dùng step aggregation hoặc push exporter, semantics lại khác. Kiểm tra registry cụ thể trước khi áp dụng khái niệm queue/batch.

Logs thường có yêu cầu retention/audit khác traces. Nếu log appender block khi backend chậm, logging có thể trở thành điểm nghẽn; nếu appender drop logs, cần có counters/alerts để biết dữ liệu đã mất.

## 11. Đo chính exporter pipeline

Exporter cũng cần được quan sát. Các tín hiệu hữu ích:

- Queue size/current occupancy và utilization ratio.
- Queue capacity/max.
- Dropped spans/records.
- Export batch size.
- Export duration/latency.
- Export request failures/timeouts.
- Retry count/backoff.
- Shutdown flush duration và records flushed.
- Collector receiver refused/failed records.

Tên metrics phụ thuộc SDK/exporter/collector. Không hardcode meter names trước khi xác minh endpoint metrics hoặc exporter instrumentation đang cung cấp.

Alert nên phản ánh ảnh hưởng:

- Queue utilization cao liên tục.
- Drop counter tăng.
- Export failure rate vượt baseline.
- Export duration tiến sát timeout.
- Collector refused data hoặc unavailable kéo dài.

Một queue utilization spike ngắn trong burst có thể bình thường nếu queue drain lại nhanh và không có drop.

## 12. Sampling và async export là hai quyết định khác nhau

Sampling quyết định spans nào được giữ để export. Async processor quyết định spans đã được giữ sẽ được gửi như thế nào. Tăng queue size không phục hồi spans đã bị sampler loại bỏ; tăng sampling rate không sửa exporter đang nghẽn.

Phân tích theo thứ tự:

1. Xác minh span có được tạo và được sampling giữ lại không.
2. Xác minh ended span có vào batch processor không.
3. Kiểm tra queue có đầy hoặc drop không.
4. Kiểm tra exporter request và collector response.
5. Kiểm tra backend ingest/query.

Không suy ra trace không xuất hiện đồng nghĩa sampling đã drop. Vấn đề có thể nằm ở instrumentation, queue, exporter, network, collector hoặc backend.

## 13. Bảo mật và dữ liệu trong queue/export

Async queue thường nằm trong memory process. Nếu exporter dùng disk spool hoặc collector queue persistent, telemetry có thể tồn tại lâu hơn và có yêu cầu bảo vệ tương tự dữ liệu logs.

- Không export credentials, access tokens hoặc raw authorization headers.
- Dùng TLS cho transport qua network không tin cậy.
- Xác thực exporter-to-collector theo workload identity/secret management.
- Giới hạn attributes và payload size.
- Đặt retention và access policy cho collector/backend.
- Cẩn thận với disk buffering vì dữ liệu telemetry có thể chứa PII.

Queue không phải kho lưu trữ bền vững. Nếu cần delivery guarantee qua process crash, phải chọn một pipeline có persistence/durability phù hợp và chấp nhận thêm latency, disk I/O, operational complexity.

## 14. Kiểm thử async exporter

| Test | Điều cần chứng minh |
| --- | --- |
| Batch test | Nhiều spans được gom thành batch đúng giới hạn |
| Queue full test | Policy khi đầy đúng behavior và không làm hỏng business request |
| Slow exporter test | Backpressure/drop được kiểm soát |
| Timeout/retry test | Lỗi transient không gây retry vô hạn |
| Shutdown flush test | Provider flush trong budget khi close |
| Export failure test | Failure metrics/logs được phát ra |
| Duplicate test | Retry behavior không làm dashboard đếm trùng ngoài semantics |
| Security test | Token/PII không xuất hiện trong exported payload |

Ví dụ test strategy với in-memory exporter:

```java
// Pseudocode:
// 1. Configure a test SpanExporter that stores exported spans in memory.
// 2. Create a BatchSpanProcessor with a small queue and batch size.
// 3. End several spans.
// 4. Force/await a flush using the processor lifecycle API.
// 5. Assert exported span count and attributes.
// 6. Simulate exporter failure and verify the documented drop/retry behavior.
```

Đây là pseudocode; API cụ thể phụ thuộc OpenTelemetry SDK version. Test nên tránh sleep cố định nếu processor cung cấp flush/shutdown synchronization. Không cần kết nối backend production để kiểm thử batch semantics.

## 15. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Trace xuất hiện trễ | Schedule delay lớn hoặc queue backlog | Queue occupancy, batch schedule và export duration |
| Mất spans khi traffic burst | Queue capacity nhỏ hoặc exporter chậm | Dropped counter, batch size và collector throughput |
| Request latency tăng khi collector down | Export path block producer hoặc retry đồng bộ | Kiểm tra processor, queue policy và exporter timeout |
| Memory tăng theo thời gian | Queue backlog không drain hoặc queue quá lớn | Occupancy trend, average item size, heap |
| Shutdown mất telemetry cuối | Không flush hoặc grace period quá ngắn | SDK lifecycle, flush timeout và termination budget |
| Export timeout liên tục | Payload lớn, network/backend chậm | Batch size, timeout, collector health |
| Duplicate telemetry | Retry hoặc nhiều pipeline/provider cùng export | Provider ownership, retry semantics và IDs |
| Queue luôn gần đầy | Sustained producer rate cao hơn export capacity | Sampling, collector capacity và exporter throughput |
| Logs làm chậm request | Synchronous/blocking appender | Appender queue, disk/network latency |
| Metrics không có queue stats | Signal/registry không dùng async queue đó | Kiểm tra đúng exporter/processor và metric source |

## 16. Tình huống thực tế: collector chậm làm trace queue đầy

**Bối cảnh giả định:** orders-service phát sinh khoảng 4.000 spans/giây trong một đợt traffic. OTLP collector xử lý chậm do backend storage đang gặp sự cố. Trace queue trong application tăng dần, exporter timeout xuất hiện và dropped spans bắt đầu tăng.

Quy trình điều tra:

1. **Xác nhận phạm vi:** kiểm tra queue occupancy, export latency/failure và dropped spans theo từng pod.
2. **Kiểm tra collector:** receiver refused, exporter queue, backend ingest latency và network errors.
3. **Giữ business path ổn định:** xác minh application threads không bị block bởi telemetry export; kiểm tra request latency và thread dumps nếu cần.
4. **Giảm telemetry volume có kiểm soát:** điều chỉnh sampling hoặc loại spans ít giá trị theo policy; không tắt toàn bộ instrumentation khi chưa đánh giá.
5. **Khôi phục capacity:** tăng collector/backend throughput hoặc giảm payload/batch theo số liệu; không chỉ tăng queue vô hạn.
6. **Kiểm tra shutdown:** đảm bảo pod termination có flush budget hợp lý.
7. **Xác minh:** queue drain về baseline, export failures/drops ngừng tăng và business latency không bị ảnh hưởng.

Async queue hấp thụ burst ngắn, không giải quyết được mất cân bằng capacity kéo dài. Nếu producer rate luôn cao hơn consumer rate, cuối cùng queue sẽ đầy.

## 17. Bài tập tự kiểm tra

**Bài 1.** Async exporter giải quyết vấn đề gì?

*Gợi ý:* Tách network export khỏi request path bằng buffer/worker, giảm khả năng exporter latency chặn business threads.

**Bài 2.** Vì sao queue không thể tăng vô hạn?

*Gợi ý:* Bộ nhớ process hữu hạn; queue lớn làm tăng heap usage và giữ telemetry cũ lâu hơn.

**Bài 3.** Queue đầy có thể xử lý theo những cách nào?

*Gợi ý:* Drop, block hoặc bounded wait tùy implementation; cần hiểu policy thật của processor.

**Bài 4.** Batch size quá lớn có trade-off gì?

*Gợi ý:* Payload lớn, serialize tốn CPU, network request dễ timeout và memory peak tăng.

**Bài 5.** Vì sao phải flush khi shutdown?

*Gợi ý:* Dữ liệu còn trong memory queue có thể mất khi process kết thúc; flush giúp gửi phần còn lại trong shutdown budget.

**Bài 6.** Sampling và async export khác nhau thế nào?

*Gợi ý:* Sampling quyết định span nào được giữ; async export quyết định cách gửi span đã được giữ.

**Bài 7.** Queue occupancy cao nhưng chưa drop có cần alert không?

*Gợi ý:* Theo dõi trend và thời gian kéo dài; spike ngắn có thể bình thường, sustained backlog báo capacity issue.

**Bài 8.** Vì sao Prometheus scrape không nhất thiết dùng cùng queue model với BatchSpanProcessor?

*Gợi ý:* Prometheus thường pull metrics từ registry; OTel batch processor push spans qua exporter. Mỗi signal có lifecycle khác nhau.

## 18. Ghi nhớ

- Async exporter tách telemetry creation khỏi network export bằng queue, worker và batch; nó giảm blocking nhưng vẫn tiêu thụ memory, CPU và network.
- Queue phải bounded. Khi producer rate vượt export capacity kéo dài, queue cuối cùng sẽ đầy.
- Hiểu rõ batch size, queue size, schedule delay, timeout và backpressure policy của SDK/exporter version đang dùng.
- Retry cần bounded timeout/backoff; timeout không chứng minh collector chưa nhận dữ liệu và retry có thể tạo duplicate delivery.
- Shutdown cần lifecycle owner và flush budget phù hợp với graceful termination; không flush vô hạn khi collector unavailable.
- Metrics, traces và logs có export semantics khác nhau; Prometheus scrape không đồng nghĩa OTel BatchSpanProcessor.
- Theo dõi queue occupancy, dropped records, export duration/failures, retries và collector health để quan sát pipeline telemetry.
- Sampling quyết định spans được giữ; async export quyết định spans đã giữ được gửi đi thế nào. Không nhầm hai nguyên nhân khi điều tra trace bị thiếu.
