# Load test khi bật instrumentation trong Spring Boot

**Load test khi bật instrumentation** là phép thử tải có kiểm soát để đo tác động của metrics, distributed tracing và logging lên hiệu năng ứng dụng. Mục tiêu là định lượng overhead mà instrumentation tạo ra, xác định giới hạn throughput/latency, quan sát mức tiêu thụ CPU/heap/network và kiểm tra khả năng export telemetry khi tải tăng. Kết quả giúp chọn cấu hình đủ khả năng điều tra sự cố mà vẫn đáp ứng SLO của service.

Trong module **SPRING_BOOT_OBSERVABILITY**, bài này kết nối Micrometer Observation với phương pháp performance testing. Nội dung thuộc chương **Hiệu năng observability**, tập trung vào baseline và các biến thể instrumentation, thiết kế workload, open/closed load model, phép đo ở application/Collector/backend, phân tích thống kê, failure injection, tiêu chí nghiệm thu và quy trình benchmark có thể lặp lại.

## 1. Vì sao phải load test instrumentation?

Instrumentation tạo thêm công việc trong request path và telemetry pipeline:
- Tạo Observation, Span, event và key-value metadata.
- Đọc/ghi context, inject/extract trace headers.
- Cập nhật meters và histogram buckets.
- Serialize, batch, compress và export telemetry.
- Ghi logs, format structured fields và truyền tới log collector.
- Duy trì queues/buffers khi exporter hoặc backend chậm.

Chi phí nhỏ trên một request có thể trở nên đáng kể khi request rate tăng cao. Ngược lại, tắt instrumentation để đạt throughput tối đa có thể làm mất tín hiệu cần thiết khi điều tra incident. Load test giúp đo trade-off trên workload thực tế.

### 1.1. Những câu hỏi cần trả lời

1. Instrumentation làm p95/p99 latency tăng bao nhiêu?
2. Throughput tối đa trước và sau khi bật telemetry thay đổi thế nào?
3. CPU, allocation rate, heap và GC thay đổi ra sao?
4. Exporter có theo kịp tốc độ tạo spans/logs không?
5. Queue có tăng liên tục hoặc drop telemetry khi peak load không?
6. Collector/backend có trở thành bottleneck không?
7. Sampling và cardinality có giữ trong budget khi traffic thay đổi không?
8. Business request có tiếp tục hoạt động khi telemetry backend chậm hoặc unavailable không?

## 2. Thiết lập baseline và các biến thể thử nghiệm

Baseline là kết quả đo với cùng ứng dụng và workload nhưng instrumentation được giảm về mức tối thiểu cần thiết để làm mốc so sánh. Không nên thay đổi business logic, JVM options, database dataset hoặc infrastructure giữa baseline và instrumented runs.

Một ma trận thử nghiệm có thể gồm:

| Run | Cấu hình | Mục đích |
| --- | --- | --- |
| A | Instrumentation tối thiểu, logs ở mức chuẩn | Baseline |
| B | Metrics bật, chưa export traces | Đo metrics overhead |
| C | Metrics + tracing, sampling 100% trong lab | Đo upper-bound trace volume |
| D | Metrics + tracing với sampling mục tiêu | Đánh giá production-like policy |
| E | Metrics + tracing + structured logs | Đo combined signal cost |
| F | Instrumented, Collector chậm hoặc unavailable | Kiểm tra queue/backpressure/failure behavior |

Sampling 100% chỉ nên dùng trong môi trường lab và tải phù hợp; nó giúp quan sát volume tối đa nhưng có thể làm backend quá tải. Không dùng kết quả đó như production recommendation.

### 2.1. Giữ biến thử nghiệm độc lập

Thay đổi từng nhóm cấu hình trong mỗi lần chạy. Nếu cùng lúc đổi sampling, batch size, compression và log level, không thể xác định yếu tố nào tạo ra chênh lệch.

Giữ cố định:
- Application build và dependency versions.
- JVM version, heap settings và container limits.
- CPU/memory quota và node type.
- Dataset, database state và cache warmness.
- Load generator location/network.
- Request mix và payload distribution.
- Collector/backend capacity khi đang đo application overhead.

## 3. Thiết kế workload đại diện

Workload cần phản ánh request mix thực tế, không chỉ gọi một endpoint đơn giản. Một ứng dụng Spring Boot có thể có các đường xử lý khác nhau:
- HTTP request chỉ đọc cache.
- HTTP request truy vấn database.
- Request ghi dữ liệu và publish message.
- Request gọi downstream HTTP service.
- Request lỗi validation hoặc business rule.
- Request có response payload lớn.
- Background job hoặc scheduled task.

Mỗi nhóm có số spans, logs và database calls khác nhau. Ghi lại tỷ trọng từng loại để kết quả có thể giải thích.

### 3.1. Arrival rate và concurrency

Có hai cách mô hình hóa tải phổ biến:

- **Open model:** tạo request theo arrival rate đã định, bất kể response trước đó hoàn tất hay chưa. Phù hợp hệ thống nhận traffic từ bên ngoài và giúp phát hiện queue buildup.
- **Closed model:** duy trì số virtual users/concurrent clients cố định; client gửi request tiếp theo sau khi request trước hoàn tất. Phù hợp một số workload user-driven nhưng có thể che khuất saturation khi latency tăng.

Chọn mô hình theo traffic thực tế. Ghi rõ arrival rate, concurrency, think time và request timeout.

### 3.2. Tránh coordinated omission

Nếu load generator chỉ gửi request mới sau khi request cũ hoàn tất, latency spike có thể khiến generator giảm tốc độ phát request và không ghi nhận đầy đủ thời gian chờ mà hệ thống thực tế sẽ trải qua. Dùng load model và histogram correction phù hợp để tránh đánh giá thấp tail latency.

## 4. Warm-up và thời gian chạy

JVM cần warm-up để JIT compilation, class loading, connection pools và caches ổn định. Đo ngay sau startup thường không phản ánh steady state.

Một kịch bản thử nghiệm nên có:
1. Startup và readiness.
2. Warm-up ở tải thấp.
3. Ramp-up theo các mức đã chọn.
4. Steady-state window đủ dài để thu số liệu.
5. Peak/burst phase nếu cần.
6. Ramp-down và shutdown/flush.
7. Cool-down trước run tiếp theo.

Thời lượng cụ thể phụ thuộc ứng dụng. Chọn steady-state đủ dài để quan sát GC cycles, periodic export và backend ingestion lag.

## 5. Các chỉ số ở application layer

Không chỉ nhìn average latency. Ghi nhận tối thiểu:

| Metric | Ý nghĩa |
| --- | --- |
| Throughput (requests/s) | Số request hoàn tất mỗi giây |
| p50 latency | Trải nghiệm điển hình |
| p95 latency | Tail latency của nhóm request chậm |
| p99 latency | Tail latency nghiêm trọng hơn |
| Error rate | Tỷ lệ request lỗi/timeout |
| CPU utilization | Chi phí xử lý tổng thể |
| Heap used/committed | Áp lực memory |
| Allocation rate | Tốc độ tạo object |
| GC count/pause | Chi phí garbage collection |
| Thread/event-loop saturation | Khả năng xử lý concurrent work |
| Connection pool wait | Tắc nghẽn dependency |

Phân tích theo endpoint/request class nếu dimensions được chuẩn hóa. Không tạo metric tags từ user ID, raw URL hoặc request-specific values.

### 5.1. Tách application latency và dependency latency

Nếu database hoặc downstream service chậm, tổng request latency tăng dù instrumentation không phải nguyên nhân. Kết hợp server metrics với database/pool metrics, client spans và downstream measurements để xác định phần thời gian thuộc ứng dụng hay dependency.

## 6. Đo overhead của metrics

Metrics thường có overhead từ meter lookup, tag evaluation, histogram recording và export. Với Micrometer, meter state được cập nhật trong application process; registry/exporter có thể scrape hoặc push theo cấu hình.

Kiểm tra:
- Số lượng meter names và time series.
- Tag combinations/cardinality.
- Histogram bucket count.
- Scrape interval hoặc push step.
- CPU/allocation khi record timer/counter.
- Export latency và registry contention nếu có.

### 6.1. Histogram và percentile

Histogram buckets hữu ích cho percentile aggregation ở backend nhưng mỗi bucket có thể làm tăng số series. Chỉ bật buckets phù hợp với SLO và latency range cần phân tích.

Client-side percentile có thể tốn memory và không aggregate giống histogram buckets giữa instances. Chọn loại percentile theo mục tiêu dashboard/alerting.

### 6.2. Cardinality stress test

Trong lab, tạo traffic với nhiều route IDs hoặc query parameters nhưng route template vẫn được chuẩn hóa. Xác minh số series không tăng theo số lượng IDs. Kiểm tra top tag values và series count trước/sau khi bật custom dimensions.

## 7. Đo overhead của tracing

Tracing có thể tạo nhiều spans trên một request: server, client, database, messaging và custom operation. Chi phí phụ thuộc spans/request, attributes/span, events/span, sampling ratio và exporter batch settings.

Ghi nhận:
- Spans created/sec và spans exported/sec.
- Bytes exported/sec.
- Span attributes/events count.
- Sampling ratio thực tế.
- Export success/failure/drop count.
- Batch queue occupancy.
- Export latency.
- CPU/allocation do context propagation và serialization.

### 7.1. Sampling matrix

Thử sampling ratios theo mục tiêu, ví dụ 0%, 1%, 10% và 100% trong lab. Không chỉ so sánh volume; kiểm tra trace continuity, error visibility và khả năng giữ trace có latency cao.

Với parent-based sampling, xác nhận downstream services tuân theo sampled decision. Với tail sampling, nhớ rằng spans phải được chuyển tới Collector trước khi Collector quyết định giữ trace.

### 7.2. Span density

Một request tạo 2 spans và một request khác tạo 30 spans không có cùng tracing cost. Theo dõi spans/request theo route hoặc operation category với dimension có cardinality thấp. Tìm instrumentation trùng lặp nếu span density tăng bất thường.

## 8. Đo overhead của logging

Logs có thể tạo allocation/string formatting và I/O. Async logging giảm blocking ở caller path nhưng thường dùng queue; queue đầy có thể drop hoặc block tùy implementation.

Thử các cấu hình:
- INFO baseline.
- DEBUG ở một package có kiểm soát.
- Structured logging với Trace ID/Span ID.
- Exception logs ở error path.
- Async appender và queue behavior nếu dùng.

Đo log events/sec, bytes/sec, CPU, queue utilization, dropped events và backend ingestion. Không bật DEBUG toàn ứng dụng trong tải production-like nếu chưa giới hạn dữ liệu và dung lượng.

### 8.1. Duplicate logging

Một exception có thể được log ở repository, service, controller advice và global handler. Duplicate logs làm tăng chi phí và che khuất sự kiện gốc. Chọn một boundary sở hữu log event, các tầng khác bổ sung context hoặc propagate exception.

## 9. Exporter, Collector và backend metrics

Khi bật telemetry export, cần đo riêng từng hop:
- Application tạo records.
- Exporter gửi records.
- Collector receiver chấp nhận records.
- Collector processor batch/filter/sample.
- Collector exporter chuyển tiếp.
- Backend ingest/index hoàn tất.

So sánh rates giữa các tầng. Nếu app export 10.000 spans nhưng backend chỉ ingest 7.000, cần xác định 3.000 records còn lại đang queue, bị drop, retry hoặc bị filter.

### 9.1. Queue và backpressure

Theo dõi queue occupancy theo thời gian, không chỉ snapshot cuối run. Queue tăng liên tục nghĩa là downstream throughput thấp hơn producer rate. Khi queue đầy, processor có thể drop records hoặc áp dụng hành vi khác tùy implementation.

Không để exporter đồng bộ chặn request thread vô hạn. Cấu hình queue hữu hạn, timeout, retry bounded và shutdown flush budget.

### 9.2. Collector saturation

Collector CPU/memory cao, receiver refused records hoặc export queue tăng có thể là bottleneck. Thử scale Collector hoặc tăng capacity có kiểm soát, nhưng không thay đổi capacity giữa các run dùng để so sánh application overhead.

## 10. Kiểm tra behavior khi telemetry backend chậm

Instrumentation phải chịu được sự cố của telemetry pipeline theo policy đã chọn. Trong lab, mô phỏng:
- Collector response chậm.
- Collector tạm unavailable.
- Network latency/loss.
- Backend ingest throttling.
- DNS/connectivity failure.
- Export timeout.

Quan sát business request latency, queue growth, dropped telemetry và recovery time. Business path không nên block vô hạn vì telemetry backend chậm.

### 10.1. Failure isolation

Nếu tracing exporter và metrics exporter dùng pipeline riêng, một signal failure không nhất thiết làm signal khác dừng. Kiểm tra từng pipeline và custom handlers. Tránh custom ObservationHandler thực hiện synchronous network call trên request thread.

## 11. Thiết kế load test script và dữ liệu

Load script cần version-control cùng benchmark configuration. Mô tả endpoint, payload, headers, authentication setup, arrival rate, duration, ramp-up và assertion.

Dữ liệu test:
- Có phân phối kích thước payload tương tự thực tế.
- Có cache hit/miss ratio hợp lý.
- Có key distribution tránh một hot key ngoài ý muốn.
- Có database dataset đủ lớn để không chỉ đo cache.
- Không chứa PII hoặc production secrets.
- Có reset/seed procedure để run có thể lặp lại.

Đặt load generator trên máy riêng hoặc node tách biệt để CPU của generator không cạnh tranh với ứng dụng. Đo network path tương tự production nếu có thể.

## 12. Phân tích kết quả và độ tin cậy

Một run đơn lẻ có thể bị ảnh hưởng bởi GC, noisy neighbor, network jitter hoặc backend compaction. Chạy nhiều lần, so sánh median/percentiles giữa runs và ghi nhận môi trường.

Các bước phân tích:
1. Kiểm tra workload thực tế có đạt target arrival rate không.
2. Loại startup/warm-up window khỏi steady-state analysis.
3. So sánh throughput và latency distribution.
4. So sánh CPU, heap, allocation và GC.
5. So sánh telemetry volume/queue/drop.
6. Kiểm tra application error rate và dependency health.
7. Xác định thay đổi vượt ngưỡng nhiễu bình thường.
8. Lặp lại run khi kết quả bất thường.

Không kết luận instrumentation gây latency chỉ vì run B chậm hơn run A nếu database hoặc node contention cũng khác nhau.

### 12.1. Relative overhead

Có thể tính overhead tương đối:

```text
overhead_percent = ((instrumented - baseline) / baseline) * 100
```

Tính riêng cho p95 latency, CPU/request hoặc allocation/request. Với throughput, chiều diễn giải ngược: giảm throughput là suy giảm. Luôn ghi đơn vị và workload cùng phép tính.

### 12.2. Confidence và noise

Dùng nhiều runs và khoảng phân phối thay vì chỉ một số trung bình. Nếu khác biệt nhỏ hơn biến thiên giữa các lần chạy, chưa đủ bằng chứng để quy kết cho instrumentation. Ghi lại commit, image digest, JVM flags, node type và telemetry backend configuration.

## 13. Tiêu chí nghiệm thu theo SLO và budget

Đặt tiêu chí trước khi chạy, tránh chọn ngưỡng sau khi xem kết quả. Ví dụ tiêu chí cần được điều chỉnh theo service:
- p95/p99 không vượt SLO.
- Error rate không tăng đáng kể.
- Throughput đạt target arrival rate.
- CPU/memory còn headroom cho traffic burst.
- GC pauses không gây tail latency bất thường.
- Telemetry queue không tăng liên tục.
- Export/drop rate nằm trong budget.
- Cardinality và storage growth nằm trong giới hạn.
- Collector/backend không bị saturation.
- Khi backend telemetry lỗi, business request vẫn hoạt động theo policy.

Một cấu hình có overhead CPU thấp nhưng drop hầu hết traces không thể được xem là đạt nếu mục tiêu là điều tra distributed failures.

## 14. Troubleshooting load test khi bật instrumentation

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| p95 tăng mạnh khi bật tracing | Span density/attributes/serialization cao | So sánh spans/request và CPU profile |
| Throughput giảm nhưng CPU không tăng | Blocking export, network wait hoặc dependency | Kiểm tra request threads và network |
| Heap/GC tăng | Allocation, batch queue hoặc payload lớn | Xem allocation profile và queue |
| Metrics series tăng nhanh | Dynamic tags/raw URI | Kiểm tra cardinality theo meter |
| Export queue tăng liên tục | Collector/backend throughput thấp | So sánh rates từng pipeline hop |
| Dropped spans tăng | Queue full, timeout hoặc retry failure | Kiểm tra processor/exporter diagnostics |
| Logs volume tăng đột biến | DEBUG/duplicate exception logs | Kiểm tra log levels và event duplication |
| p99 tăng khi Collector chậm | Handler/export đồng bộ hoặc queue contention | Kiểm tra thread dump và export path |
| CPU tăng khi compression bật | Compression cost cao | Benchmark compressed/uncompressed |
| Trace coverage thấp | Sampling/filter quá chặt hoặc export loss | Đối chiếu request count và spans |
| Kết quả run dao động lớn | Noisy node, warm-up hoặc workload không ổn định | Lặp lại với environment cố định |
| Load generator không đạt target | Generator bottleneck | Theo dõi CPU/network generator |
| Backend lag nhưng app export ổn | Collector downstream/backend saturation | So sánh accepted/exported/ingested |
| Shutdown mất records | Flush timeout/grace period ngắn | Kiểm tra provider close lifecycle |

### Quy trình điều tra

1. Xác minh load generator đạt arrival rate dự kiến.
2. Kiểm tra workload mix và warm-up.
3. So sánh baseline với từng instrumentation variant.
4. Xem p50/p95/p99, throughput và error rate.
5. Kiểm tra CPU, allocation, heap, GC và threads.
6. Kiểm tra metric series/cardinality.
7. Kiểm tra spans/request, sampling và payload size.
8. Theo dõi exporter/Collector queues, failures và drops.
9. Kiểm tra backend ingest/index lag.
10. Lặp lại run sau khi thay đúng một yếu tố.

## 15. Bài thực hành: benchmark instrumentation

Mục tiêu là định lượng overhead của metrics, tracing và logging trong một Spring Boot service.

### Chuẩn bị

- Spring Boot service có HTTP, database và một downstream call hoặc message publish.
- Load generator có open/closed model.
- Actuator/Micrometer registry.
- Tracing bridge/exporter và Collector lab.
- Metrics/JVM monitoring cho application và Collector.
- Dataset không chứa dữ liệu production.

### Bước 1 — Xác định workload

Chọn request mix gồm read, write, downstream call và error path. Ghi target arrival rate, payload sizes và concurrency.

### Bước 2 — Chạy baseline

Giữ instrumentation bổ sung ở mức tối thiểu. Warm-up, chạy steady state và ghi throughput, p95/p99, CPU, heap, GC và error rate.

### Bước 3 — Bật metrics

Bật meter handlers/export. Chạy lại workload giống hệt. Ghi series count, sample rate, CPU và latency.

### Bước 4 — Bật tracing

Bật producer/server/client/database instrumentation. Chạy sampling 100% trong một run lab có giới hạn, sau đó thử sampling ratios thấp hơn.

### Bước 5 — Bật structured logs

Giữ log level và event set rõ ràng. Đo log bytes/sec, CPU, allocation và queue behavior.

### Bước 6 — Kiểm tra combined signals

Bật đồng thời metrics, traces và logs. Xác nhận combined overhead không vượt budget.

### Bước 7 — Mô phỏng Collector chậm

Giới hạn receiver hoặc gây network delay. Quan sát business latency, exporter queues và dropped telemetry.

### Bước 8 — Kiểm tra cardinality

Tạo nhiều IDs trên cùng route template. Xác nhận metric series không tăng theo số IDs.

### Bước 9 — Lặp lại benchmark

Chạy lại mỗi variant nhiều lần trong môi trường ổn định. Tính relative overhead và ghi nhận độ biến thiên.

### Bước 10 — Chốt cấu hình

Chọn sampling, batch, queue, log level và Collector capacity theo SLO, telemetry coverage và cost budget.

### Checklist nghiệm thu

| Điều cần chứng minh | Kết quả mong đợi |
| --- | --- |
| Baseline | Có run đối chứng với workload cố định |
| Workload | Request mix và arrival model đại diện |
| Warm-up | Không trộn startup với steady state |
| Latency | Có p50/p95/p99 |
| Throughput | Đạt target arrival rate |
| Resources | Đo CPU, heap, allocation và GC |
| Metrics | Đo series count và export rate |
| Tracing | Đo spans/request, sampling và drops |
| Logging | Đo events/sec và bytes/sec |
| Pipeline | Đo exporter/Collector/backend throughput |
| Failure | Business path chịu được telemetry outage |
| Repeatability | Nhiều runs, environment/config được ghi lại |

## 16. Những nguyên tắc cần ghi nhớ

1. **Luôn có baseline đối chứng.** Giữ workload, build, JVM và infrastructure cố định.
2. **Đo tail latency và throughput, không chỉ average.** p95/p99 cho thấy tác động tới request chậm.
3. **Tách metrics, tracing và logging.** Bật từng signal rồi mới đo combined configuration.
4. **Thiết kế workload đại diện.** Request mix, dependency calls và payload size quyết định telemetry volume.
5. **Theo dõi toàn pipeline.** Application export thành công chưa chứng minh Collector/backend ingest đầy đủ.
6. **Kiểm soát cardinality và span density.** Dynamic tags và duplicate instrumentation có thể tăng cost mạnh.
7. **Queue phải hữu hạn.** Telemetry backend chậm không được block business path vô hạn.
8. **Sampling cần đánh giá cả cost lẫn coverage.** Giảm spans nhưng vẫn phải giữ khả năng điều tra errors/slow traces.
9. **Lặp lại và ghi nhận môi trường.** Kết quả cần đủ tin cậy để so sánh release.
10. **Đặt acceptance criteria theo SLO và budget trước khi chạy.** Không chọn ngưỡng chỉ để hợp thức hóa kết quả.

Load test khi bật instrumentation biến nhận định “telemetry có overhead nhỏ” thành số liệu có thể kiểm chứng. Với baseline rõ ràng, workload đại diện, phép đo ở application và telemetry pipeline, cùng thử nghiệm khi Collector/backend chậm, nhóm phát triển có thể chọn cấu hình Micrometer Observation, metrics, tracing và logging đáp ứng SLO mà vẫn giữ đủ dữ liệu để vận hành và điều tra sự cố.
