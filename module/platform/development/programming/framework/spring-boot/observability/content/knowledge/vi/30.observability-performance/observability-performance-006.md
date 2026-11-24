# Drop telemetry khi quá tải

Một Spring Boot service nhận lượng request tăng đột biến. Ứng dụng vẫn xử lý nghiệp vụ, nhưng trace exporter gửi dữ liệu chậm vì Collector hoặc backend đang quá tải. Hàng đợi telemetry dần đầy; nếu ứng dụng tiếp tục giữ mọi span, log và metric trong bộ nhớ, heap có thể tăng, thread export bị nghẽn và cuối cùng ảnh hưởng cả request production. Drop telemetry có kiểm soát là một cơ chế bảo vệ: chấp nhận mất một phần dữ liệu quan sát trong điều kiện quá tải để giữ ổn định ứng dụng và bảo toàn tín hiệu quan trọng nhất.

Bài **Drop telemetry khi quá tải** thuộc chương **Hiệu năng observability** của module **SPRING_BOOT_OBSERVABILITY**. Module học cách thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; hiểu context propagation, tag/cardinality, exporter, sampling và liên kết các tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trong môi trường thực.

> **Nguyên tắc:** Telemetry là dữ liệu phụ trợ cho vận hành; việc export telemetry không được trở thành dependency đồng bộ bắt buộc của request nghiệp vụ. Khi quá tải, dùng bounded queues, timeout, sampling, filtering và ưu tiên có chủ đích. Theo dõi queue occupancy, export failures và dropped records để biết hệ thống đang mất dữ liệu ở đâu. Không được để cơ chế drop che giấu sự cố bằng cách bỏ luôn metrics báo mất telemetry.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao telemetry pipeline cần backpressure và cơ chế drop.
2. Nhận diện các điểm nghẽn từ instrumentation đến backend exporter.
3. Phân biệt sampling, filtering, rate limiting và dropping.
4. Thiết kế queue có giới hạn và timeout để bảo vệ heap/thread.
5. Hiểu cách batch span processor và Collector xử lý queue đầy/export chậm.
6. Ưu tiên telemetry theo giá trị vận hành và chi phí.
7. Tránh để exporter hoặc Collector gây latency cho request nghiệp vụ.
8. Theo dõi dropped spans, logs, metrics và export failures.
9. Thiết kế graceful degradation và recovery sau overload.
10. Kiểm thử pipeline khi backend chậm, unreachable hoặc trả lỗi.

## 2. Vì sao telemetry có thể làm ứng dụng quá tải?

Mỗi request có thể tạo nhiều spans, log records và measurements. Khi traffic tăng, số telemetry records tăng theo. Nếu tốc độ tạo dữ liệu lớn hơn tốc độ export trong một khoảng đủ dài, backlog sẽ tích tụ.

~~~mermaid
flowchart LR
    A["Application instrumentation"] --> B["SDK / Micrometer buffers"]
    B --> C["Exporter workers"]
    C --> D["Collector receivers / processors"]
    D --> E["Backend"]
    B -. "queue full" .-> X["Drop / reject"]
    C -. "export timeout" .-> X
    D -. "memory pressure" .-> X
~~~

Ví dụ:
- 5.000 requests/second.
- Mỗi request tạo 4 spans.
- SDK tạo khoảng 20.000 spans/second.
- Exporter/backend chỉ xử lý được 12.000 spans/second.

Backlog tăng khoảng 8.000 spans mỗi giây cho đến khi queue đầy. Tăng queue size chỉ trì hoãn thời điểm đầy; nó không sửa throughput deficit lâu dài.

### 2.1 Các điểm nghẽn thường gặp

| Vị trí | Triệu chứng | Hậu quả |
|---|---|---|
| Instrumentation | Quá nhiều spans/attributes/events | CPU và allocation tăng |
| SDK queue | Queue occupancy tăng liên tục | Queue đầy và drop |
| Export worker | Export latency/timeout cao | Backlog không được drain |
| Network | Packet loss, TLS/DNS/connect issue | Export retry/failure |
| Collector receiver | Ingest rate vượt capacity | Refusal hoặc backpressure |
| Collector processor | Batch/memory limiter chạm ngưỡng | Queueing, refusal hoặc drop |
| Backend | Ingest throttling, storage/index chậm | Collector retry hoặc reject |

Điều tra từ source tới backend; chỉ nhìn backend ingest rate có thể bỏ sót việc SDK đã drop spans trước khi chúng tới Collector.

## 3. Backpressure và bounded queues

Backpressure là cách hệ thống phản ứng khi downstream không theo kịp upstream. Với telemetry, các lựa chọn gồm:
- Chặn producer để chờ capacity.
- Từ chối hoặc drop record khi queue đầy.
- Giảm tốc độ tạo telemetry bằng sampling/filtering.
- Tăng consumer/export capacity nếu có tài nguyên.
- Buffer tạm thời ngoài process nếu kiến trúc và durability cho phép.

Với request-serving application, chặn thread nghiệp vụ chờ telemetry exporter thường là lựa chọn nguy hiểm. Bounded queue giới hạn bộ nhớ; khi đầy, policy phải quyết định record nào bị từ chối hoặc drop.

~~~mermaid
flowchart TD
    A["New telemetry record"] --> B{"Queue has capacity?"}
    B -->|Yes| C["Enqueue"]
    C --> D["Export worker"]
    D --> E{"Export succeeds?"}
    E -->|Yes| F["Release record"]
    E -->|No| G["Retry within bounded policy"]
    G --> D
    B -->|No| H["Drop / reject / shed load"]
    G -->|Retry budget exhausted| H
~~~

Queue bounded giúp memory usage có giới hạn. Tuy nhiên, queue lớn hơn cũng tăng memory footprint và thời gian chờ trước khi export. Chọn capacity dựa trên record size, burst duration và tốc độ drain có thể đạt được.

## 4. Sampling, filtering và dropping khác nhau

| Cơ chế | Khi nào quyết định? | Ý nghĩa |
|---|---|---|
| Sampling | Khi tạo/đánh giá trace | Chọn trace nào được ghi/export |
| Filtering | Theo rule về nội dung/loại signal | Loại telemetry không cần thiết |
| Rate limiting | Giới hạn số record trong một khoảng thời gian | Kiểm soát tốc độ ingest |
| Queue overflow drop | Khi buffer đầy | Bỏ record vì không còn capacity |
| Export failure drop | Sau khi retry/timeout policy kết thúc | Bỏ record không gửi được |
| Tail sampling | Sau khi Collector đã nhận trace | Giữ/bỏ trace dựa trên dữ liệu đã quan sát |

Sampling là cách chủ động giảm volume trước khi quá tải. Queue overflow drop là phản ứng cuối khi producer vẫn nhanh hơn consumer. Filtering loại bỏ dữ liệu theo policy; rate limiting kiểm soát tốc độ. Tail sampling có thể giữ trace lỗi/chậm tốt hơn head sampling, nhưng Collector phải nhận và xử lý spans trước khi ra quyết định, nên vẫn cần capacity và memory phù hợp.

Không xem mọi dropped span là sampling. Phân biệt chủ đích sampling với loss do queue full/export failure để dashboard phản ánh đúng chất lượng telemetry.

## 5. OpenTelemetry BatchSpanProcessor

OpenTelemetry SDK thường dùng BatchSpanProcessor để gom ended spans và export theo batch thay vì gọi exporter đồng bộ trên mỗi span.

Các cấu hình quan trọng thường gồm:
- max queue size: số spans tối đa được giữ trong queue.
- max export batch size: số spans tối đa trong một batch.
- schedule delay: khoảng thời gian chờ trước khi export batch.
- exporter timeout: thời gian tối đa cho một export operation.

Tên property/environment variables và defaults phụ thuộc ngôn ngữ SDK/version. Với Java agent hoặc OpenTelemetry Java SDK, kiểm tra cấu hình chính thức của đúng distribution.

Khi queue đầy, BatchSpanProcessor không giữ vô hạn spans mới; spans có thể bị drop và SDK thường expose metric/log về dropped spans tùy version. Đây là lý do cần theo dõi SDK telemetry nội bộ và kiểm tra cấu hình queue.

### 5.1 Chọn queue size

Queue size phải cân bằng burst absorption và memory:
- Queue quá nhỏ: burst ngắn đã gây drop.
- Queue quá lớn: heap usage tăng và export latency có thể kéo dài.
- Batch size quá nhỏ: overhead export/network cao.
- Batch size quá lớn: payload/CPU/memory spike, exporter có thể timeout.
- Schedule delay quá dài: telemetry chậm xuất hiện trong backend.
- Timeout quá dài: worker bị chiếm lâu khi backend không phản hồi.

Không có một con số đúng cho mọi service. Đo span size, traffic burst, export throughput và heap headroom trước khi đặt capacity.

## 6. Collector queue, retry và memory limiter

OpenTelemetry Collector có thể dùng sending queue và retry policy trong exporter helper. Queue giúp hấp thụ burst và tách receiver khỏi exporter trong giới hạn capacity. Retry giúp xử lý lỗi tạm thời, nhưng retry vô hạn hoặc queue không giới hạn có thể làm tăng memory pressure.

Memory limiter processor có thể từ chối dữ liệu khi Collector gần ngưỡng memory để bảo vệ process. Batch processor gom records thành batch nhằm tăng hiệu quả export. Cần cấu hình thứ tự processor và pipeline đúng với Collector distribution/version.

Ví dụ cấu hình khái niệm:

~~~yaml
processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 512
    spike_limit_mib: 128
  batch:
    send_batch_size: 1024
    timeout: 5s

exporters:
  otlp:
    endpoint: telemetry-backend:4317
    sending_queue:
      enabled: true
      queue_size: 5000
    retry_on_failure:
      enabled: true
      max_elapsed_time: 120s

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlp]
~~~

Đây là cấu hình minh họa, không phải cấu hình production hoàn chỉnh. Cần kiểm tra exporter helper schema, queue storage, retry defaults, processor order và memory unit của phiên bản Collector đang chạy. Queue in-memory có thể mất dữ liệu khi Collector restart; persistent queue cần storage extension và đánh giá durability/disk pressure.

### 6.1 Retry không tạo durability tuyệt đối

Retry chỉ có ích khi lỗi tạm thời và còn capacity. Nếu backend từ chối liên tục hoặc queue đầy, record cuối cùng vẫn có thể bị drop. Persistent queue có thể giúp vượt qua restart, nhưng không bảo đảm exactly-once delivery; duplicate hoặc replay cần được chấp nhận theo semantics của backend.

## 7. Ưu tiên telemetry khi quá tải

Không phải mọi record đều có giá trị như nhau trong incident. Có thể định nghĩa policy:
- Giữ error traces và slow traces với sampling phù hợp.
- Giữ metrics tổng hợp về availability, latency, saturation và dropped telemetry.
- Giữ log cảnh báo/lỗi đã scrub.
- Giảm debug/info logs có volume cao.
- Bỏ spans cho health checks/noisy operations nếu policy cho phép.
- Loại bỏ attributes/events không phục vụ điều tra.
- Hạn chế payload capture và stacktrace duplication.

Ưu tiên phải được thực hiện trước điểm nghẽn. Khi queue SDK đã đầy, Collector tail sampling không thể cứu spans chưa rời khỏi process. Head sampling tại SDK có thể giảm tải sớm; tail sampling cần Collector đủ năng lực nhận trace.

### 7.1 Không bỏ metrics báo mất telemetry

Nếu overload policy drop spans, vẫn cần metrics cho:
- Dropped spans/records.
- Export failures và timeouts.
- Queue size/occupancy.
- Collector refused records.
- Export batch duration.
- Backend throttling/rejection.

Nếu metrics telemetry cũng bị drop cùng lúc, dùng out-of-band signals như process logs, Collector self-telemetry, health endpoint, host metrics hoặc alert từ queue/backend.

## 8. Giữ request nghiệp vụ độc lập với exporter

Exporter nên hoạt động trên worker/background path với queue bounded. Request thread chỉ nên tạo/đóng Observation hoặc enqueue record theo chi phí nhỏ, không chờ network export đồng bộ.

Các nguyên tắc:
1. Dùng asynchronous/batch exporter integration phù hợp.
2. Giới hạn queue và export timeout.
3. Không retry trên request thread.
4. Không gọi remote telemetry backend từ Observation handler theo cách blocking.
5. Không để exporter exception làm thất bại business transaction.
6. Giữ thread pool telemetry tách khỏi pool xử lý request nếu integration cho phép.
7. Có shutdown flush với timeout hữu hạn, không chặn shutdown vô hạn.

Một số instrumentation có chi phí CPU/allocation ngay trong application thread; cần profile và giảm số attributes/events nếu overhead lớn. “Async export” không có nghĩa instrumentation hoàn toàn miễn phí.

## 9. Drop policy và signal-specific behavior

Metrics, traces và logs có semantics khác nhau:
- Metrics thường là aggregation; mất một số measurements có thể làm counter/rate sai nếu không biết loss. Một số registry/exporter dùng temporality và cumulative/delta behavior khác nhau.
- Traces là records theo request; drop một span có thể làm trace thiếu một đoạn hoặc mất cả trace nếu sampling/queue drop.
- Logs là event records; drop có thể làm mất bằng chứng incident cụ thể.

Vì vậy không dùng một policy duy nhất cho mọi signal. Ví dụ:
- Giữ service-level RED metrics (rate, errors, duration) ở pipeline có capacity ưu tiên.
- Sampling traces theo error/latency và traffic budget.
- Rate-limit repetitive logs, giữ error logs với deduplication.
- Không capture mọi request body hoặc debug payload.
- Đo dropped counts riêng cho từng signal.

Nếu backend hoặc Collector có per-signal queues, đặt budgets và alert riêng. Một trace overload không nhất thiết có nghĩa metrics pipeline cũng đã quá tải.

## 10. Adaptive sampling và overload controls

Adaptive sampling thay đổi sampling probability theo traffic/throughput budget. Ví dụ khi traffic tăng, giảm tỷ lệ trace bình thường nhưng giữ nhiều trace lỗi/chậm nếu có thể dùng tail sampling.

Cần cẩn trọng:
- Sampling policy phải nhất quán để không làm trace bị đứt context giữa services.
- Parent-based sampling giúp downstream tôn trọng quyết định trace upstream trong một số propagation setups.
- Tail sampling cần memory/decision wait window và routing đúng trace ID.
- Khi Collector quá tải, tail sampling processor có thể trở thành bottleneck.
- Đảm bảo policy không vô tình bỏ toàn bộ traces của một tenant/route quan trọng.
- Không dùng PII làm sampling key hoặc attribute để ưu tiên.

Adaptive control cần giới hạn min/max sampling và quan sát sampling rate. Đừng phản ứng quá nhanh gây oscillation hoặc làm thay đổi phân phối dữ liệu khó diễn giải.

## 11. Cardinality và payload size cũng gây overload

Không chỉ số spans gây áp lực. Mỗi record có thể lớn do:
- Nhiều span attributes/events/links.
- Exception stack traces dài.
- HTTP headers/body capture.
- SQL statements và bind values.
- Log message chứa object serialization.
- Resource attributes lặp lại không cần thiết.

Giảm payload:
- Chỉ ghi attributes có giá trị điều tra.
- Dùng route templates và bounded tags.
- Không capture request/response body mặc định.
- Cắt bớt hoặc scrub exception details.
- Giới hạn log message size.
- Không serialize object graph lớn vào span/log.
- Dùng event/metric tổng hợp thay nhiều spans cho mỗi internal step khi phù hợp.

Payload size lớn làm tăng memory, network bandwidth, Collector CPU và backend indexing cost. Đồng thời kiểm soát PII và cardinality để tránh một vấn đề vận hành biến thành privacy incident.

## 12. Graceful degradation và recovery

Khi telemetry backend unavailable:
- Application tiếp tục phục vụ nghiệp vụ nếu dependency nghiệp vụ còn khỏe.
- Exporter queue tăng tới giới hạn rồi áp dụng drop policy.
- Exporter timeout/retry trong budget.
- Alert về dropped telemetry và backend availability.
- Khi backend phục hồi, queue được drain theo capacity đã giới hạn.
- Không để recovery burst làm backend quá tải lần nữa.

Nếu dùng persistent queue, theo dõi disk usage, queue age và replay throughput. Khi replay, backend có thể nhận dữ liệu cũ với tốc độ cao; cần giới hạn drain rate.

Shutdown:
- Gọi flush/shutdown theo lifecycle integration.
- Đặt timeout hữu hạn.
- Không block process shutdown vô hạn để export toàn bộ backlog.
- Ghi nhận số record còn lại/dropped nếu SDK hỗ trợ.

## 13. Metrics để quan sát telemetry pipeline

Một số tín hiệu nên theo dõi:

| Metric/Signal | Câu hỏi |
|---|---|
| SDK queue size/capacity | Buffer đang đầy đến đâu? |
| SDK dropped spans | Bao nhiêu spans bị bỏ trước export? |
| Exporter failures | Bao nhiêu lần export thất bại? |
| Export duration | Export latency có tăng không? |
| Collector refused records | Receiver/processor có từ chối telemetry không? |
| Collector queue size | Backlog đang tích tụ ở Collector? |
| Collector memory usage | Memory limiter gần ngưỡng chưa? |
| Backend throttling | Backend có rate-limit/reject ingest? |
| Application latency | Telemetry overload có ảnh hưởng request không? |
| Signal volume | Records/second theo traces, metrics và logs? |

Tên metric chính xác tùy SDK, Collector version và exporter. Không hardcode tên từ ví dụ nếu chưa xác nhận metric thực tế. Dùng self-telemetry của Collector và SDK instrumentation phù hợp.

## 14. Kiểm thử overload và drop behavior

Không chờ production outage mới biết queue policy. Tạo test/staging experiment:
1. Dùng fake exporter hoặc Collector backend giả lập response chậm.
2. Tăng telemetry production rate có kiểm soát.
3. Làm export latency lớn hơn ingest rate.
4. Xác nhận queue occupancy tăng nhưng không vượt capacity.
5. Xác nhận dropped counter tăng khi queue đầy.
6. Xác nhận request latency/error rate nghiệp vụ không tăng bất thường.
7. Xác nhận exporter timeout/retry kết thúc trong budget.
8. Khôi phục backend và kiểm tra queue drain ổn định.
9. Kiểm tra shutdown flush không block vô hạn.
10. Lặp lại riêng cho traces, metrics và logs.

### 14.1 Fault injection

Có thể mô phỏng:
- Network latency/loss tới Collector.
- Collector process restart.
- Backend trả 429/503.
- Export endpoint không resolve được.
- Disk đầy với persistent queue.
- Memory limiter kích hoạt.
- Traffic burst và span payload lớn.

Thực hiện ở môi trường kiểm thử có giới hạn, đặt rollback/stop condition và không tạo tải không kiểm soát trên production.

## 15. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| SDK dropped spans tăng | Batch queue đầy hoặc exporter chậm | Kiểm tra queue/export duration, giảm sampling/volume hoặc tăng drain capacity |
| App latency tăng cùng exporter errors | Export blocking hoặc thread contention | Kiểm tra exporter sync path và tách worker |
| Collector memory tăng liên tục | Ingest > export, queue lớn hoặc payload lớn | Bounded queue, memory limiter, giảm payload/rate |
| Collector refused records tăng | Memory limiter hoặc receiver overload | Kiểm tra self-telemetry, capacity và pipeline |
| Backend nhận ít spans hơn SDK tạo | Drop ở SDK/network/Collector/backend | So sánh counters tại từng boundary |
| Retry queue không drain | Backend vẫn throttling hoặc drain rate quá cao | Giới hạn retry/backoff và replay rate |
| Trace thiếu child spans | Head/tail sampling, SDK queue drop hoặc propagation issue | Kiểm tra sampling decisions và dropped counters |
| Metrics vẫn ổn nhưng logs mất | Per-signal pipeline khác nhau | Kiểm tra logs queue/exporter riêng |
| Shutdown kéo dài | Flush đợi backend hoặc backlog quá lớn | Giới hạn flush timeout |
| Queue tăng sau deploy | Instrumentation volume/attribute size tăng | So sánh spans per request, events và payload size |
| Cardinality tăng bất thường | Tag values động tạo series/records lớn | Allowlist và normalize dimensions |
| Drop không có alert | Chưa export self-telemetry hoặc dashboard thiếu | Tạo alert từ SDK/Collector drop metrics và out-of-band signals |

## 16. Playbook: backend telemetry chậm trong giờ cao điểm

**Tình huống:** Collector export timeout tăng, SDK dropped spans xuất hiện và request latency bắt đầu nhích lên.

1. So sánh application request rate với spans/log records generated per second.
2. Kiểm tra SDK queue occupancy, dropped spans và export duration.
3. Kiểm tra Collector receiver rate, refused records, memory và exporter queue.
4. Xác định bottleneck là application SDK, network, Collector processor hay backend ingest.
5. Giảm telemetry volume có chủ đích: sampling traces bình thường, filter noisy health checks và giảm verbose logs.
6. Giữ error/slow traces và metrics availability/latency/dropped telemetry theo policy.
7. Xác nhận exporter chạy background và không block request threads.
8. Điều chỉnh queue/batch/timeout theo memory headroom và measured throughput.
9. Khi backend phục hồi, drain backlog với rate giới hạn.
10. Theo dõi dropped rate, queue age và application SLO sau recovery.

Không chỉ tăng queue size khi backend xử lý chậm kéo dài. Tìm cách tăng capacity hoặc giảm input rate; queue lớn hơn chỉ giữ nhiều dữ liệu hơn trong bộ nhớ.

## 17. Bài tập tự kiểm tra

**Bài 1 — Queue math.** SDK tạo 20.000 spans/s, exporter gửi 12.000 spans/s. Queue tăng bao nhiêu spans mỗi giây? Vì sao tăng queue chỉ trì hoãn drop?

**Bài 2 — Sampling vs drop.** Phân biệt trace bị head-sampled out với span bị drop vì BatchSpanProcessor queue đầy. Cần metric nào để biết?

**Bài 3 — Backpressure.** Vì sao không nên block request thread để chờ telemetry exporter trong hệ thống synchronous API?

**Bài 4 — Collector.** Memory limiter, batch processor và exporter sending queue có vai trò gì? Vì sao cần cấu hình theo version?

**Bài 5 — Tail sampling.** Vì sao tail sampling không cứu được span đã bị drop trong SDK trước khi tới Collector?

**Bài 6 — Signal policy.** Vì sao traces, metrics và logs nên có drop/retention policies khác nhau?

**Bài 7 — Recovery.** Persistent queue drain quá nhanh sau backend recovery có thể gây vấn đề gì?

**Bài 8 — Self-observability.** Nếu chính metrics telemetry cũng bị drop, làm thế nào phát hiện pipeline đang mất dữ liệu?

### Gợi ý trả lời

1. Tăng 8.000 spans/s. Queue đầy sau một khoảng thời gian hữu hạn; tăng capacity chỉ kéo dài thời gian trước overflow.
2. Head sampling là quyết định policy trước khi export; queue drop là loss do capacity. Theo dõi sampling decision/rate và SDK dropped spans.
3. Exporter/network chậm sẽ giữ thread nghiệp vụ, tăng latency và gây cascading failure.
4. Memory limiter bảo vệ Collector, batch tăng hiệu quả export, sending queue hấp thụ burst/retry. Schema/defaults thay đổi theo Collector distribution/version.
5. Collector chưa nhận span nên không có dữ liệu để tail sampling giữ lại.
6. Metrics tổng hợp cho SLO, traces theo request và logs là event records; giá trị và chi phí mất dữ liệu khác nhau.
7. Backend lại bị ingest burst/throttling; giới hạn replay/drain rate.
8. Dùng Collector self-telemetry, process logs, health, host metrics hoặc external monitoring độc lập.

## 18. Tài liệu tham khảo chính thức

- [OpenTelemetry — Batch Span Processor](https://opentelemetry.io/docs/specs/otel/trace/sdk/#batching-processor): batching, queue và export behavior.
- [OpenTelemetry Java — Configuration](https://opentelemetry.io/docs/zero-code/java/agent/configuration/): Java agent properties, batch processor và exporter settings.
- [OpenTelemetry Collector — Resiliency](https://opentelemetry.io/docs/collector/resiliency/): queues, retries và memory management.
- [OpenTelemetry Collector — Memory Limiter](https://github.com/open-telemetry/opentelemetry-collector/tree/main/processor/memorylimiterprocessor): memory pressure và refusal behavior.
- [OpenTelemetry Collector — Batch Processor](https://github.com/open-telemetry/opentelemetry-collector/tree/main/processor/batchprocessor): batching records.
- [OpenTelemetry Collector — Exporter Helper](https://github.com/open-telemetry/opentelemetry-collector/tree/main/exporter/exporterhelper): sending queues, retry và timeout configuration.
- [OpenTelemetry — Sampling](https://opentelemetry.io/docs/concepts/sampling/): head/tail sampling concepts.
- [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): Observation handlers và instrumentation lifecycle.
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): tracing configuration, sampling và exporter integration.

**Ghi nhớ:** Telemetry pipeline phải có capacity hữu hạn và được tách khỏi request path. Khi input vượt throughput export, queue sẽ đầy; sampling/filtering giảm input có chủ đích, còn drop là loss do capacity hoặc export failure. Theo dõi dropped records, queue occupancy, export latency và Collector self-telemetry. Ưu tiên tín hiệu theo giá trị điều tra, giới hạn payload và retry, rồi kiểm thử overload/recovery để chứng minh telemetry backend chậm không làm gián đoạn nghiệp vụ.

