# Đánh đổi latency với throughput

Trong Spring Batch, tăng số worker, tăng kích thước chunk hoặc gom nhiều bản ghi trước khi ghi xuống database thường giúp **thông lượng (throughput)** cao hơn. Nhưng những thay đổi ấy cũng có thể làm một bản ghi phải **chờ lâu hơn** mới được commit, khiến request nằm trong hàng đợi lâu hơn, kéo dài thời gian rollback/retry và làm p95/p99 latency tăng mạnh khi tài nguyên đạt ngưỡng bão hòa. Ngược lại, giảm chunk size và xử lý ít request đồng thời có thể giảm thời gian chờ của từng công việc nhưng không khai thác hết năng lực I/O và CPU.

Bài học **“Đánh đổi latency với throughput”**, thuộc chương **Thông lượng** của module **SPRING_BATCH_SCALING_OPERATIONS**, trình bày cách chọn điểm cân bằng cho workload lớn. Phạm vi module là mở rộng Spring Batch qua multi-threaded step, parallel steps, partitioning và mô hình xử lý phân tán, đồng thời đo bottleneck, bảo đảm thread safety, retry/restart và vận hành trên tài nguyên thực. Vì vậy, mục tiêu ở đây **không phải tối đa hóa một con số records/second bằng mọi giá**, mà là đạt throughput yêu cầu **trong giới hạn latency, độ đúng dữ liệu, khả năng phục hồi và ngân sách tài nguyên**.

> **Nguyên tắc:** tốc độ *nhận việc*, tốc độ *xử lý*, tốc độ *commit thành công* và tốc độ *công bố kết quả* là bốn mốc khác nhau. Đánh đổi latency–throughput chỉ có ý nghĩa khi mọi phép đo dùng cùng ranh giới, cùng workload và cùng tiêu chí correctness.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt latency theo **record, chunk, partition, JobExecution và end-to-end publication** với throughput theo items/chunks/jobs trên giây.
2. Đọc các số p50, p95, p99, queue wait, service time và thời gian commit mà không nhầm trung bình với tail latency.
3. Áp dụng **Little's Law** đúng điều kiện để liên hệ lượng công việc in-flight, arrival/completion rate và thời gian trong hệ thống.
4. Giải thích tại sao khi mức sử dụng tài nguyên tiến sát 100%, **queueing latency** có thể tăng vọt trước khi throughput tăng đáng kể.
5. Phân tích đánh đổi của **chunk size, JDBC batch size, commit interval, reader buffering và prefetch**.
6. Chọn concurrency budget cho `TaskExecutor`, partitioning và connection pool dựa trên bottleneck thực thay vì chỉ số CPU.
7. Phân biệt tính chất latency của **local partitioning**, **remote partitioning**, **remote chunking** và **parallel steps**.
8. Xác định vai trò của retry, rollback, idempotency, restart, broker ACK và backlog trong p99 latency.
9. Thiết kế benchmark lặp lại được với baseline, load profile, metrics, tracing, correctness checks và failure injection.
10. Ra quyết định tuning theo SLO và khả năng vận hành, không chỉ theo records/second cao nhất trong một lần chạy.

**Tình huống xuyên suốt:** mỗi giờ, hệ thống nhận khoảng 3 triệu giao dịch cần đối soát. Job `settlementImport` dùng Spring Batch 5.x/Java 17+, đọc staging PostgreSQL, chuyển đổi và ghi một database downstream. SLA yêu cầu hoàn tất batch trong 15 phút; đồng thời một số sự kiện rủi ro cao cần được hiển thị trong vòng 10 giây. Nếu chỉ tối ưu throughput của toàn job, hệ thống có thể hoàn tất đủ 3 triệu records nhưng các sự kiện rủi ro vẫn chờ đến cuối chunk hoặc đến cuối batch mới visible. Ta cần phân loại workload, định nghĩa SLO rồi chọn kiến trúc.

## 2. Throughput là gì và nên tính ở mốc nào?

**Throughput** là số lượng đơn vị công việc **hoàn tất theo định nghĩa đã chọn** trong một đơn vị thời gian. Với batch import:

\[
\text{Committed throughput} =
\frac{\text{Số records nghiệp vụ commit hợp lệ}}
     {\text{Khoảng thời gian đo (giây)}}
\]

Những con số sau không tương đương:

| Chỉ số | Ý nghĩa | Vì sao dễ đánh lừa |
| --- | --- | --- |
| `read/s` | Reader đọc bao nhiêu input records? | Có thể đọc trước nhưng chưa commit |
| `processed/s` | Processor thực thi bao nhiêu items? | Retry có thể gọi processor nhiều lần |
| `writer calls/s` | Writer được gọi bao nhiêu lần? | Writer call chưa chắc commit |
| `committed records/s` | Bao nhiêu logical results đã commit? | Cần biết filter/skip và duplicate key |
| `published results/s` | Bao nhiêu kết quả đã sẵn sàng cho consumer? | Publication gate có thể chậm hơn DB commit |
| `completed jobs/hour` | Bao nhiêu JobExecutions hoàn tất? | Kích thước mỗi job khác nhau |
| `messages/s` | Broker deliver/ACK bao nhiêu messages? | Một message có nhiều items, có redelivery |

**Mẫu số cũng phải cố định.** Throughput `3.000.000 / 900 = 3.333,3 records/s` là mức trung bình yêu cầu cho 15 phút **nếu tất cả 3 triệu records đều cần ghi và 900 giây dành trọn cho pipeline**. Nếu cần thêm 2 phút validation, archive và publication, thời gian dành cho import chỉ còn 780 giây: yêu cầu tương ứng khoảng `3.846,2 records/s`. Nếu 10% được filter hợp lệ, phải ghi rõ KPI tính **input covered** hay **business output committed**, không gộp hai định nghĩa.

## 3. Latency là gì? Chọn ranh giới trước khi đo

**Latency** là khoảng thời gian một đơn vị công việc trải qua từ **mốc bắt đầu** tới **mốc kết thúc** cụ thể.

~~~text
Input xuất hiện
    -> chờ được nhận (ingress wait)
    -> reader lấy record
    -> chờ gom chunk/buffer
    -> processor chạy
    -> chờ connection/lock
    -> writer SQL
    -> database COMMIT
    -> chờ reply/validation/publication
    -> downstream thấy kết quả
~~~

Các loại latency cần phân biệt:

- **Record end-to-end latency**: từ lúc input đủ điều kiện xử lý đến khi kết quả record được công bố. Với batch hàng giờ, một record có thể chờ lịch chạy lâu hơn thời gian process thực.
- **Chunk latency**: từ lúc chunk được hình thành/submit đến khi transaction chunk có outcome commit/rollback; có thể bao gồm queue wait.
- **Worker service time**: thời gian worker đang làm việc trên request/chunk/partition, không tính mọi khoảng chờ trước khi worker nhận.
- **Partition makespan**: từ lúc partition bắt đầu đến lúc worker StepExecution hoàn tất.
- **Job wall time**: JobExecution start → end, gồm điều phối/validation theo flow đã định nghĩa.
- **Time-to-first-result**: bao lâu có kết quả đầu tiên an toàn cho downstream; có thể khác hoàn toàn time-to-last-result.
- **Recovery latency**: từ khi lỗi xảy ra tới khi workload đạt trạng thái cuối đúng sau retry/restart.

**Không so p99 của từng-record latency với job makespan như thể chúng có cùng phân phối**. Một job có 3 triệu records có một makespan nhưng hàng triệu giá trị record latency.

## 4. Throughput, latency và concurrency không phải một núm điều chỉnh

~~~mermaid
flowchart LR
    A["Arrival rate λ"] --> Q["Queue / buffered work"]
    Q --> W["N concurrent workers"]
    W --> D["CPU / DB / disk / broker"]
    D --> C["Committed outcome rate X"]
    C --> P["Publication / downstream visibility"]
    Q -. "Queue wait tăng" .-> L["End-to-end latency"]
    D -. "Service/lock wait" .-> L
    P -. "Publication wait" .-> L
~~~

**Concurrency** là số công việc có thể hoạt động/in-flight cùng lúc. Tăng từ 2 lên 8 workers có thể tăng throughput nếu tài nguyên còn dư; nhưng khi DB pool hoặc disk đã đạt giới hạn, thêm workers chủ yếu tạo **nhiều công việc chờ hơn**.

**Quy tắc:** tốc độ gửi job/message vào hệ thống (`arrival rate`) không phải throughput đã commit (`completion rate`). Nếu arrival rate duy trì cao hơn năng lực hoàn tất, hàng đợi tăng; latency end-to-end có thể không còn giới hạn dù CPU của manager chưa cao.

## 5. Little's Law: quan hệ giữa WIP và thời gian chờ

Ở hệ thống ổn định, có ranh giới đo thống nhất và trung bình dài hạn đủ đại diện, **Little's Law**:

\[
L = \lambda W
\]

Trong đó:

- `L`: số lượng công việc trung bình **đang ở trong ranh giới hệ thống** (*work in progress*, gồm queue và service).
- `λ`: tốc độ đi qua hệ thống trung bình trong trạng thái ổn định, tính theo cùng đơn vị items/s hoặc chunks/s.
- `W`: thời gian trung bình một đơn vị ở trong hệ thống, tính bằng giây.

Ví dụ: hoàn tất ổn định **400 chunks/s** và có trung bình **80 chunks** từ lúc vào queue tới khi nhận outcome, ta ước lượng:

\[
W = \frac{80}{400} = 0{,}2\ \text{giây/chunk}
\]

Nếu tăng số work in-flight lên 400 chunks trong khi completion rate vẫn 400 chunks/s, thời gian trong hệ thống có thể tiến gần **1 giây/chunk**, không có ích gì cho throughput.

**Các bẫy khi dùng công thức:**

1. `L` phải bao gồm đúng những công việc trong **cùng ranh giới** đã dùng để đo `W`; không lấy chỉ active CPU threads rồi dùng latency bao gồm broker queue.
2. `λ` phải biểu diễn **flow trung bình ổn định**; khi backlog tăng liên tục, không tùy tiện áp dụng số đo ổn định.
3. Đơn vị phải nhất quán: chunk/s và chunk latency; không lấy items/s chia số partitions.
4. Công thức áp dụng cho **giá trị trung bình**, không trực tiếp suy ra p95/p99.
5. Không dùng Little's Law để kết luận nguyên nhân bottleneck; nó giúp thấy hệ quả **tăng WIP khi capacity không tăng**.

## 6. Queueing: vì sao p99 tăng mạnh gần saturation?

Xét mô hình lý tưởng M/M/1 (arrival Poisson, thời gian phục vụ exponential, một server, hàng đợi ổn định). Đây **chỉ là mô hình trực giác**, không mặc định đúng với Spring Batch/DB:

\[
\rho=\frac{\lambda}{\mu},\qquad
W_{\text{system}}=\frac{1}{\mu-\lambda},\qquad
W_{\text{service}}=\frac{1}{\mu}
\]

Với năng lực phục vụ `μ=100 chunks/s`, service time trung bình khoảng **10 ms/chunk**:

| Arrival rate | Utilization `ρ` | Mean time in system `W` | Nghĩa thực dụng |
| ---: | ---: | ---: | --- |
| 50 chunks/s | 50% | 20 ms | Còn dư năng lực |
| 80 chunks/s | 80% | 50 ms | Queue wait đã đáng kể |
| 90 chunks/s | 90% | 100 ms | Latency gấp 10 service time |
| 95 chunks/s | 95% | 200 ms | Rất nhạy với burst |
| 99 chunks/s | 99% | 1.000 ms | Queueing áp đảo |

Tất cả số trên là **minh họa toán học**, không phải benchmark đo từ Spring Batch. Hệ thực có nhiều workers, batch arrivals, retry, thời gian phục vụ biến thiên, pool và network delays; p99 có thể xấu hơn hoặc khác hẳn. Nhưng bài học vẫn hữu ích: **chạy ở 99% năng lực xử lý không đồng nghĩa đạt latency tốt**.

**Nếu arrival rate ≥ service capacity** lâu dài, mô hình không còn trạng thái ổn định với hàng đợi không giới hạn. Khi đó tăng timeout chỉ che triệu chứng; cần giảm ingress, tăng capacity thực hoặc thay đổi workload.

## 7. Đặt SLO cho cả throughput và latency

Một SLO tốt có **đơn vị, ranh giới, percentile và kỳ đo** rõ ràng.

Ví dụ (giả định cho tình huống học):

| Nhóm workload | Throughput/mốc hoàn tất | Latency SLO | Ghi chú |
| --- | --- | --- | --- |
| Import giao dịch đêm | ≥3 triệu input covered/15 phút | Job p95 ≤15 phút theo kỳ đo | Không phải từng record đều visible ngay |
| Kiểm tra giao dịch rủi ro | ≥500 events/s ổn định | Event p99 ≤10 giây, từ READY tới visible | Có thể cần luồng ưu tiên/tách job |
| Archive báo cáo | ≥200 files/phút | File p95 ≤2 phút từ processed tới archived | Filesystem/network khác business DB |
| Recovery sau worker crash | Không có data loss/duplicate effect | Hoàn tất reconciliation ≤30 phút | Không tính retry attempts là output mới |

**Không lấy p99 của records trong một batch rồi tuyên bố job p99 latency**. Job p95 cần đo trên nhiều JobExecutions; record p99 đo trên nhiều records với event-time/visibility semantics riêng.

Khi hai SLO xung đột, có thể **tách workload/priority queue** hoặc giữ capacity riêng cho record cần latency thấp. Cố dùng một queue FIFO khổng lồ cho cả nightly backfill và cảnh báo giao dịch có thể gây **head-of-line blocking**.

## 8. Cần tìm bottleneck trước khi tăng worker

~~~mermaid
flowchart TD
    A["Đo throughput, queue age và p95/p99"] --> B{"Bottleneck nằm ở đâu?"}
    B -->|Reader| C["Index/paging/source I/O/parallel read"]
    B -->|CPU processor| D["Profile, thuật toán, concurrency CPU"]
    B -->|DB writer| E["Batch SQL, index, locks, pool"]
    B -->|Broker| F["Consumers, prefetch, serialization, routing"]
    B -->|Publication| G["Validation/outbox/manifest/receiver"]
    C --> H["Benchmark lại + reconciliation"]
    D --> H
    E --> H
    F --> H
    G --> H
~~~

**Dấu hiệu thường gặp:**

- Reader chậm và workers rảnh: tăng worker writer không giúp, vì dữ liệu không được cấp đủ nhanh.
- Processor CPU-bound: tăng worker tới giới hạn core hiệu quả; vượt quá có thể tăng context switching/GC.
- Writer DB-bound: tăng worker có thể khiến pool/row locks bão hòa; phải tối ưu SQL/index/transaction và rate.
- Broker backlog cao nhưng worker service ngắn: xem consumer concurrency/prefetch, broker routing và network.
- Business DB commit nhanh nhưng downstream thấy kết quả muộn: bottleneck ở publication barrier, outbox hoặc validation.

Đánh đổi latency–throughput chỉ tối ưu được khi **đúng tầng** đang bị giới hạn. Một global `chunk(1000)` không tự giải quyết index scan chậm của reader hay broker reply queue bị nghẽn.

## 9. Chunk size tạo đánh đổi cố định–biến đổi

Trong chunk-oriented processing, giả sử thời gian lý tưởng của một chunk gồm:

\[
T_{\text{chunk}}(B) \approx T_{\text{fixed}} + B \cdot T_{\text{per-item}}
\]

Với `B` là số items/chunk, `T_fixed` gồm commit/round-trip/setup, `T_per-item` gồm phần CPU/SQL biến đổi trên mỗi item. Throughput một worker **khi không chờ việc, không lỗi, không contention**:

\[
X(B) \approx \frac{B}{T_{\text{fixed}} + B T_{\text{per-item}}}
\]

Nếu `T_fixed` đáng kể, tăng chunk size giúp giảm overhead per item. Nhưng `T_chunk` dài hơn cũng kéo dài **thời gian giữ transaction**, lock, memory và thời gian chờ kết quả durable của item đầu trong chunk.

**Công thức này chỉ là mô hình sơ bộ**, không phản ánh JDBC driver batching, query plan, transaction log, bulk APIs, worker overlap, network, skip/retry và database constraints. Luôn benchmark trên hệ tương đương production.

## 10. Ví dụ định lượng: chunk 100, 500 hay 1.000?

Giả sử một worker xử lý tuần tự; chi phí cố định per chunk **8 ms**, chi phí biến đổi mỗi item **0,12 ms**, và tất cả items đều hợp lệ:

| Chunk `B` | `T_chunk` theo mô hình | Throughput một worker lý tưởng | Chi phí fixed mỗi item |
| ---: | ---: | ---: | ---: |
| 1 | 8,12 ms | ~123 items/s | 8 ms |
| 50 | 14 ms | ~3.571 items/s | 0,16 ms |
| 100 | 20 ms | 5.000 items/s | 0,08 ms |
| 500 | 68 ms | ~7.353 items/s | 0,016 ms |
| 1.000 | 128 ms | ~7.813 items/s | 0,008 ms |
| 2.000 | 248 ms | ~8.065 items/s | 0,004 ms |

Lợi ích tăng chunk size **giảm dần**. Từ 100 → 500, thông lượng lý tưởng tăng ~47%; từ 1.000 → 2.000 chỉ tăng ~3%. Trong khi đó một transaction 2.000 items có thể có **gấp đôi dữ liệu cần rollback/replay**, memory và thời gian giữ lock so với 1.000.

**Không suy ra cấu hình tốt nhất là 2.000** từ bảng. Nếu DB lock wait tăng theo kích thước transaction hoặc một item lỗi khiến cả chunk retry, throughput hữu ích thực tế có thể giảm dù mô hình đơn giản dự báo tăng.

## 11. Chunk batching gây thời gian chờ ngay cả khi worker nhanh

Một tác động thường bị bỏ sót là **batch fill wait**: item đến trước phải chờ đủ item trong batch/chunk, hoặc chờ timeout flush. Nếu records đến liên tục với tốc độ gần như cố định `λ` items/s và hệ thống **chỉ gửi khi đủ B items**, thời gian chờ để lấp đầy batch của item đầu gần `(B-1)/λ`, còn chờ trung bình của mỗi item xấp xỉ:

\[
W_{\text{fill, avg}} \approx \frac{B-1}{2\lambda}
\]

**Ví dụ chỉ có ý nghĩa cho arrival liên tục và chế độ gom batch chờ đủ B items:**

~~~text
Arrival rate = 100 items/s
Chunk fill target B = 500

Item đầu có thể chờ ~4,99 giây mới gom đủ chunk.
Thời gian chờ trung bình do fill ~2,495 giây.
Worker xử lý+commit chunk có thể chỉ mất 68 ms.
~~~

Nếu một người chỉ xem `worker.chunk.duration=68ms` sẽ không thấy **2,5 giây fill wait**. Trường hợp Spring Batch đọc nhanh từ file/staging có sẵn, reader có thể lấp chunk gần như tức thì nên công thức trên **không phù hợp**; ngược lại với nguồn records đến lẻ tẻ/streaming-like thì rất quan trọng.

**Giải pháp tùy mục tiêu:** giảm B, dùng **flush-by-time/partial batch** khi abstraction hỗ trợ, hoặc tách luồng latency thấp ra khỏi batch lớn. Đừng tự gắn `chunk(500)` với một “timeout 100ms” không có trong cấu hình rồi mong framework tự flush khi reader đang chặn; Spring Batch chunk boundary/reader semantics phải được hiểu đúng.

## 12. Latency phân phối không chỉ có mean

Khi người dùng nói “job chậm”, cần tách:

| Percentile/metric | Ý nghĩa | Dễ bị che bởi |
| --- | --- | --- |
| Mean chunk latency | Trung bình chung | Vài chunk rất chậm có thể nhỏ so với tổng |
| p50 | Nửa requests xử lý nhanh hơn mức này | Không cho biết tail |
| p95/p99 | 5%/1% chậm nhất vượt ngưỡng này | Timeout, DB waits, long queues |
| Max | Request/chunk chậm nhất trong tập đo | Outlier có thể do test setup |
| Job makespan | Thời gian hoàn tất toàn bộ workload | Một partition skewed duy nhất |
| Queue oldest age | Công việc còn chờ lâu nhất | Backlog không được đo bằng processing timer |
| Time-to-first/last output | Tốc độ thấy dữ liệu đầu/cuối | Publication gate, slowest worker |

**p99 không bằng max**, và không được lấy trung bình cộng các giá trị p99 ở manager, broker và worker để ra end-to-end p99. Các request chậm nhất ở từng tầng **có thể không phải cùng request**; cần trace/request identity end-to-end và histogram đủ mẫu.

Lưu ý cách tổng hợp: p95 của từng worker không thể lấy trung bình rồi gọi là p95 toàn job; nên **merge histogram/distribution dữ liệu gốc** bằng công cụ có semantics phù hợp.

## 13. Transaction dài hơn: lock, redo log và rollback

Một chunk lớn thường giữ một database transaction lâu hơn. Điều này ảnh hưởng đến:

- **Lock lifetime:** các rows/index pages giữ lock lâu, worker khác chờ nhiều hơn.
- **Rollback cost:** item lỗi muộn có thể khiến một chunk lớn phải rollback và thử lại/cô lập item.
- **Transaction log/WAL:** nhiều thay đổi phải được ghi durable; spikes có thể làm commit chậm.
- **Connection occupancy:** connection được giữ qua nhiều item, giảm capacity cho các workers khác.
- **Memory buffer:** framework/driver giữ items, JDBC batch values hoặc result objects lâu hơn.
- **Failure blast radius:** một worker crash giữa chunk có thể khiến nhiều item phải replay, dù chunks trước đã commit.

**Nhưng không có quy tắc “chunk nhỏ luôn tốt”**: chunk nhỏ tạo nhiều commits và round-trips, tăng overhead, khiến throughput thấp dù lock time ngắn. Cần đo **chunk commit duration, row lock wait, rollback count, WAL pressure, connection pending và bytes/items per chunk**.

### Trường hợp có lỗi dữ liệu

~~~text
Chunk 1000 items; item cuối vi phạm business rule.
Nếu step rollback/retry để cô lập lỗi,
framework có thể phải thực hiện lại một phần work.

Chunk 100 items tạo blast radius nhỏ hơn,
nhưng tăng số transactions/round-trips khi tất cả đều hợp lệ.
~~~

Đây là mô tả xu hướng, **không khẳng định Spring Batch luôn replay toàn bộ 1.000 items ở mọi loại skip/write failure**. Hành vi thực phụ thuộc reader, processor, writer, skip/retry policy, buffering và transaction rollback classifier. Phải đo test có fault injection cho cấu hình đang chạy.

## 14. Chunk size khác với JDBC driver batch size

Trong Spring Batch, `.chunk(B, transactionManager)` xác định khoảng commit logic của một worker step. JDBC driver có thể gom nhiều statements hoặc parameter sets trong **một lần network round-trip** tùy writer và cấu hình.

| Cấp độ | Ví dụ | Mục đích |
| --- | --- | --- |
| Spring Batch chunk | `chunk(200)` | Boundary transaction, checkpoint, listener/retry semantics |
| JDBC batch | `JdbcBatchItemWriter` gọi batch update | Giảm round-trips/overhead SQL |
| Database multi-row insert/bulk API | SQL/COPY/provider-specific | Tăng tốc ingest khi hợp đồng cho phép |
| Broker message batch/chunk | 200 items/`ChunkRequest` | Giảm serialization/message overhead |
| Partition | 10.000 rows/range | Chia work cho worker StepExecution |

**Đừng đồng nhất các cấp:** một chunk 200 không bảo đảm driver gửi đúng một network packet; một bulk load API có thể có transaction/restart semantics khác `JdbcBatchItemWriter`. Chọn chúng theo **bottleneck thật** và kiểm cả data correctness.

### Mẫu worker step Spring Batch 5.x

~~~java
@Bean
Step importWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<InputRecord> reader,
        ItemProcessor<InputRecord, OutputRecord> processor,
        ItemWriter<OutputRecord> writer) {
    return new StepBuilder("importWorkerStep", jobRepository)
            .<InputRecord, OutputRecord>chunk(200, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

Đây là **bộ khung Spring Batch 5.x/Java 17+**, chưa bao gồm model types, reader/writer beans, imports, JobRepository, datasource và fault-tolerance. Thử `chunk(50), chunk(200), chunk(1000)` trên **cùng workload/snapshot**; đừng hardcode một giá trị từ benchmark sang production mà không nhìn p99, rollback và resource contention.

## 15. JDBC writer: tối ưu theo batch nhưng vẫn cần idempotency

Một writer SQL cho phép retry/restart theo business key:

~~~java
@Bean
JdbcBatchItemWriter<OutputRecord> outputWriter(DataSource ds) {
    return new JdbcBatchItemWriterBuilder<OutputRecord>()
            .dataSource(ds)
            .sql("""
                INSERT INTO normalized_record
                    (batch_key, record_id, net_amount)
                VALUES (:batchKey, :recordId, :netAmount)
                ON CONFLICT (batch_key, record_id) DO NOTHING
                """)
            .itemSqlParameterSourceProvider(item ->
                    new MapSqlParameterSource()
                            .addValue("batchKey", item.batchKey())
                            .addValue("recordId", item.recordId())
                            .addValue("netAmount", item.netAmount()))
            .assertUpdates(false)
            .build();
}
~~~

**Giới hạn:** `ON CONFLICT DO NOTHING` chỉ chặn duplicate row theo khóa unique. Nếu bản ghi cùng key nhưng `netAmount` khác do source/rule version thay đổi, SQL này có thể **che giấu lỗi dữ liệu**. Production phải verify existing payload/value hoặc dùng ledger/hash với chính sách conflict rõ. Với nghiệp vụ cộng dồn số dư, phải dùng idempotency key cho **logical operation**, không dùng một SQL increment rồi mặc định an toàn khi replay.

### Thử nghiệm writer

1. Chạy batch bình thường, ghi latency per commit và total committed logical records.
2. Chạy cùng snapshot khi restart hợp lệ; không có business effects trùng.
3. Tiêm lỗi sau business commit nhưng trước StepExecution metadata checkpoint.
4. Đo `duplicate_conflict` và phát hiện **conflict khác nội dung**, không chỉ `COUNT(*)`.
5. So với non-batched JDBC writer và database bulk loader **chỉ nếu transaction/recovery semantics được giải trình**.

**Throughput cao mà sai giao dịch không đạt mục tiêu tối ưu.** Khi tăng commit interval, hãy chắc chắn rollback/replay vẫn giữ đúng outcome sau crash.

## 16. Reader, prefetch và paging cũng tác động latency

Nguồn input là file, database hay API có đặc tính khác nhau:

- **FlatFileItemReader:** đọc tuần tự file; lớn chunk có thể làm DB commit hiệu quả hơn nhưng không thể bắt một file đọc tuần tự tự động chia cho nhiều threads.
- **JdbcCursorItemReader:** giữ cursor/connection trong lifecycle; nhiều workers có thể giữ nhiều connections lâu, khiến pool căng.
- **JdbcPagingItemReader:** truy vấn nhiều pages, cần unique sort key và stable source snapshot để không skip/duplicate khi dữ liệu thay đổi.
- **MultiResourceItemReader:** xử lý nhiều files; cần thống nhất resource ordering và checkpoint qua restart.
- **Reader qua API:** prefetch giúp che network latency nhưng có thể vượt rate limit/tạo queue lớn; phải có bounded buffer/timeout.

**Tối ưu throughput reader** không luôn làm giảm record end-to-end latency. Prefetch quá xa tạo thêm WIP/heap; reader có thể đã lấy dữ liệu vào memory nhưng phải chờ worker/DB, kéo dài time-to-commit và recovery complexity.

### Stable source snapshot

Nếu JobExecution restart với `ExecutionContext` checkpoint cũ nhưng input database bị append/modify hoặc file bị thay bytes, cùng offset/page có thể chỉ sang record khác. Đừng “cải thiện latency” bằng cache/prefetch làm mất **source identity/version**. Snapshot bất biến và idempotent sink là điều kiện trước khi benchmark restart.

## 17. Tăng số worker: từ hữu ích đến bão hòa

Giả sử worker service time trung bình một request là 100 ms (không tính queue), mỗi worker xử lý **tuần tự** và workload có đủ requests. Năng lực lý tưởng:

| Số workers | Năng lực lý tưởng nếu độc lập | Điều kiện |
| ---: | ---: | --- |
| 1 | 10 requests/s | Không shared bottleneck |
| 2 | 20 requests/s | Source/DB đủ capacity |
| 4 | 40 requests/s | CPU/network/pool không nghẽn |
| 8 | 80 requests/s | Có đủ 8 effective workers |
| 16 | 160 requests/s | Vẫn chưa gặp giới hạn nguồn/tài nguyên |

Trong hệ thật, tăng từ 8 lên 16 workers có thể chỉ đạt 82 requests/s nếu DB đã giới hạn ở ~80 requests/s. Lượng request in-flight và queueing có thể tăng gấp đôi, khiến latency cao hơn mà throughput gần như đứng yên.

**Vì thế cần tìm “knee point”**: vùng mà tăng concurrency cho thêm throughput ít nhưng tail latency/resource cost tăng nhiều. Điểm ấy phải đo theo **cùng dataset, cùng DB state và cùng rate input**, không suy từ số cores.

## 18. Executor gridSize, queue capacity và database pool

Spring Batch local partitioning dùng nhiều worker `StepExecution` qua `TaskExecutorPartitionHandler`. Số partitions, executor active threads và số DB connections khả dụng không nhất thiết bằng nhau.

~~~java
@Bean
ThreadPoolTaskExecutor partitionExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(8);
    executor.setThreadNamePrefix("batch-partition-");
    executor.initialize();
    return executor;
}

@Bean
TaskExecutorPartitionHandler partitionHandler(
        @Qualifier("workerStep") Step worker,
        @Qualifier("partitionExecutor") TaskExecutor executor) {
    TaskExecutorPartitionHandler handler =
            new TaskExecutorPartitionHandler();
    handler.setStep(worker);
    handler.setTaskExecutor(executor);
    handler.setGridSize(8);
    return handler;
}
~~~

`gridSize=8` là mức chia/điều phối, **không có nghĩa 8 workers chạy đồng thời**: pool ở ví dụ chỉ có tối đa 4 active threads. Nếu partitioner trả 8 partitions, một số work chờ trong executor queue. Nếu task submissions vượt pool+queue, chúng có thể bị **rejected** theo policy.

### Đừng đặt Hikari pool bằng gridSize theo công thức máy móc

Một worker có thể dùng connection cho JDBC cursor, writer transaction và metadata. JobRepository/manager, các tác vụ validator và thread pool khác cũng có thể dùng DB. Nếu `maxPoolSize=4` trong khi 4 JDBC cursor readers giữ connection suốt step và writers cần connection khác, rất dễ tạo waiting/timeouts tùy datasource và transaction configuration.

Hãy đo `active/pending/idle connection`, thời gian giữ connection, SQL locks và DB max connections. Giảm concurrency hoặc chọn reader/paging để giảm resource occupancy khi cần. **Vấn đề không tự hết bằng cách tăng timeout connection**.

## 19. CPU-bound, I/O-bound và workload hỗn hợp

**CPU-bound:** parser/crypto/validation tính toán nặng. Nếu hiệu năng chủ yếu do CPU, concurrency hiệu quả thường liên quan đến số cores khả dụng, GC, memory bandwidth và thread overhead; nhiều hơn core có thể chỉ gây scheduling overhead.

**I/O-bound:** phần lớn thời gian chờ DB/network/remote API. Vài workers có thể che I/O wait và nâng throughput, nhưng cuối cùng nghẽn ở DB pool, rate limit, broker hoặc remote service.

**Mixed pipeline:** reader I/O-bound, processor CPU-bound, writer DB-bound. Một worker end-to-end có thể chờ lẫn lộn; tăng workers giúp chồng lấp công đoạn nhưng cũng có thể tạo **pipeline bottleneck migration** từ processor sang writer.

### Ước lượng ban đầu, không phải đáp án cố định

Ví dụ mỗi worker chỉ dùng CPU khoảng 25% thời gian, còn 75% chờ I/O: bốn workers có thể sử dụng một core nhiều hơn một worker. Nhưng phép tính `workers = cores/(1-blocking ratio)` chỉ nên xem là **ước lượng mở đầu**; DB contention, đồng bộ lock, network variance và JVM GC khiến mức tối ưu khác. **Load test và latency SLO** mới quyết định concurrency cuối.

## 20. Amdahl's Law và giới hạn tốc độ hoàn tất job

Một job có phần tuần tự như khởi tạo, snapshot scan, validation hoặc publication barrier. **Amdahl's Law** mô tả speedup lý tưởng khi tỷ lệ `s` không song song:

\[
S(N)=\frac{1}{s+\frac{1-s}{N}}
\]

Ví dụ phần tuần tự chiếm `s=0,2` của baseline, dùng 8 workers:

\[
S(8)=\frac{1}{0,2+\frac{0,8}{8}}
=\frac{1}{0,3}\approx3,33
\]

Ngay cả 8 workers cũng chỉ cho ~3,33× speedup lý tưởng, chưa tính broker/DB contention. Khi `N→∞`, giới hạn lý tưởng là `1/s=5×`.

**Điều quan trọng:** giảm thời gian worker per chunk không nhất thiết giảm job wall time nếu 20% thời gian vẫn nằm ở phần tuần tự; cần **đo manager reader, setup, join/aggregate, validation và publish**, không chỉ processor time.

## 21. Local partitioning: speedup và tail của slowest partition

Trong local partitioning, manager chia work theo range/file rồi dùng executor chạy nhiều worker StepExecutions. Nếu có bốn partitions với thời gian:

~~~text
partition0: 10 s
partition1: 11 s
partition2: 12 s
partition3: 80 s
~~~

Job không thể hoàn tất trước partition chậm nhất (còn overhead manager/validation), dù ba partitions đã idle sớm. **Average partition latency** 28,25 s che mất **job makespan ~80 s+**.

**Cách xử lý:**

1. Tạo partition theo **số lượng record/ước lượng cost**, không chỉ numeric ID range width.
2. Với file có kích thước rất lệch, chia logical shards nếu record boundaries an toàn.
3. Đừng tạo quá nhiều partitions nhỏ nếu JobRepository metadata/executor overhead tăng mạnh.
4. Tách những partitions cực nặng sang pool/queue riêng nếu có SLO/priority khác.
5. Theo dõi `max partition duration`, idle worker time và work skew, không chỉ tổng records/s.

**Local partitioning không tự scale ngang qua nhiều nodes.** Khi một JVM/host đã chạm memory/CPU hoặc nguồn chung, remote partitioning có thể phân tải sang nhiều machines nhưng phải tính thêm network, consistency và failover cost.

## 22. Remote partitioning: thêm node không loại bỏ bottleneck chung

Trong remote partitioning, manager gửi `StepExecutionRequest` qua middleware, worker trên các JVM/nodes khác nhau đọc phạm vi input và cập nhật `StepExecution`/JobRepository theo topology đã triển khai.

**Lợi ích:** scale CPU/memory/connection xử lý ra nhiều nodes, có thể chạy partitions độc lập và tận dụng tài nguyên riêng.

**Chi phí bổ sung:**

- Serialization/dispatch, queue wait và reply/status propagation.
- Shared JobRepository/database contention khi quá nhiều worker steps cùng update metadata.
- Worker warm-up, network latency, broker availability và request timeout.
- Crash/restart semantics, duplicate delivery, late reply và stale worker.
- Source access locality: worker ở xa file system có thể tăng I/O latency.

Đối với partitions lớn chạy vài phút, chi phí dispatch vài milliseconds có thể nhỏ. Với partitions chỉ có vài chục items, overhead mạng/metadata có thể **lấn át thời gian tính toán**, khiến nhiều nodes đạt **throughput kém hơn** và tail latency cao hơn.

**Tuning:** chọn **partition granularity** đủ lớn để amortize dispatch overhead, nhưng không quá lớn gây stragglers/retry blast radius; benchmark các giá trị bằng JobExecution makespan và p95/p99 per-partition cùng số request pending.

## 23. Remote chunking: manager đọc nhanh chưa phải worker commit nhanh

Trong remote chunking, manager thường giữ `ItemReader`, đóng các items vào `ChunkRequest` gửi qua middleware; worker process/write rồi gửi `ChunkResponse` về manager.

~~~mermaid
flowchart LR
    R["Manager ItemReader"] --> C["ChunkRequest B items"]
    C --> MQ[("Request broker queue")]
    MQ --> W["Worker processor/writer"]
    W --> DB[("Business DB commit")]
    W --> RQ[("Reply queue")]
    RQ --> M["Manager correlation"]
~~~

**Đo ít nhất bốn tốc độ:**

1. `manager.items.read/s`: tốc độ reader tạo items.
2. `manager.chunks.dispatched/s`: tốc độ broker nhận request theo semantics publisher confirm.
3. `worker.items.committed/s`: logical effects commit thành công; phân biệt filter/skip và duplicate.
4. `manager.chunks.correlated/s`: response được match tới pending request có hiệu lực.

Nếu manager gửi 10.000 items/s nhưng worker chỉ commit 5.000 items/s, **backlog tăng trung bình khoảng 5.000 items/s** trong điều kiện không có cancellation/drop và cùng units. Manager throughput báo đẹp nhưng **end-to-end latency** sẽ tăng vì queue wait.

**Cần tính message sizes:** một ChunkRequest 1.000 records có thể nặng vài kilobytes hoặc hàng chục megabytes tùy payload; serialization, broker frame/message limit, network, memory và worker deserialization ảnh hưởng throughput/latency. Không chọn B chỉ dựa SQL commit optimization.

## 24. Broker prefetch, queue depth và head-of-line blocking

Consumer prefetch giới hạn số messages broker cho một consumer nhận nhưng chưa ACK, tùy transport/container semantics. Prefetch lớn có thể giảm round-trip và tăng throughput, nhưng cũng:

- Giữ nhiều work ở một worker đang chậm, làm những worker khác rảnh.
- Tăng memory và thời gian chờ của message đã deliver nhưng chưa process.
- Tăng số message phải redeliver khi một worker JVM bị kill.
- Làm fairness kém giữa workers có processing time khác nhau.
- Dễ gây burst database transactions khi consumer concurrency được tăng đột ngột.

**Ví dụ:** một worker có 10 messages prefetch, mỗi message cần 2 giây xử lý. Message cuối có thể chờ nhiều giây **trong worker buffer** trước khi bắt đầu; broker queue có thể nhìn thấp hơn nhưng record latency không giảm.

**Không có “prefetch=10 luôn đúng”**. Phải đo transport-specific unacked/in-flight count, consumer utilization, redelivery, queue age và business commit latency. Với Kafka, khái niệm consumer fetch/poll/partition assignment khác AMQP prefetch; không dùng cùng thuật ngữ/config như thể tương đương một-một.

## 25. Backpressure: kiểm soát WIP thay vì cho backlog vô hạn

**Backpressure** làm upstream giảm hoặc tạm dừng phát work khi downstream chưa có capacity. Trong Spring Batch/distributed messaging, một số cơ chế có thể là:

- Giới hạn số `ChunkRequest` in-flight chưa có valid response.
- Dùng bounded executor queue với rejection/timeout policy được xử lý rõ.
- Dùng broker capacity/prefetch và consumer concurrency được sizing theo DB throughput.
- Tạm dừng dispatch khi queue age hoặc oldest pending request vượt ngưỡng.
- Chia rate limit theo tenant/priority để một nguồn lớn không chiếm toàn bộ capacity.
- Giảm kích thước batch hoặc chuyển sang flush sớm cho luồng cần p99 thấp.

~~~mermaid
flowchart TD
    A["Manager muốn dispatch"] --> B{"Pending requests < budget?"}
    B -- "Có" --> C["Dispatch và tăng in-flight"]
    C --> D["Worker outcome / correlated reply"]
    D --> E["Giảm in-flight theo protocol"]
    E --> A
    B -- "Không" --> F["Chờ / throttle / chuyển lịch"]
    F --> A
~~~

**Lưu ý:** bộ đếm pending phải bền vững hoặc có recovery/correlation policy đúng khi manager restart; một biến `AtomicInteger` trong JVM không đủ để giải thích messages vẫn đang bay khi process chết. Giảm in-flight lúc `send()` trả về là sai; thường phải đợi **outcome hợp lệ** hoặc trạng thái timeout/recovery riêng.

**Backpressure là công cụ kiểm soát latency, không tự tạo thêm service capacity.** Khi arrival rate dài hạn > capacity, phải xử lý nguyên nhân, giảm ingress hoặc thay SLA. Hàng đợi hữu hạn giúp **tránh quá tải không kiểm soát**, nhưng nếu reject work, phải có durable retry/feedback để không mất dữ liệu.

## 26. Batch size trong remote chunking còn ảnh hưởng reply latency

Gửi chunks lớn:

**Lợi ích:**

- Giảm số broker messages/serializer invocations/response correlations trên cùng số items.
- Amortize network overhead và transaction setup.
- Có thể tăng throughput nếu worker/DB đang bị giới hạn bởi overhead cố định.

**Chi phí:**

- Manager phải gom nhiều items trước khi phát request.
- Worker giữ nhiều items trong RAM và transaction lâu hơn.
- Chunk lớn là đơn vị retry/redelivery lớn hơn khi worker crash hoặc reply mất.
- Một item chậm có thể giữ kết quả **cả chunk** lại (*head-of-line blocking*).
- P99 response latency tăng dù `records/s` được nâng.

**Mô hình ví dụ:** 100.000 items, mỗi request có network/serialization overhead 3 ms. B=100 → 1.000 requests, overhead lý tưởng khoảng 3 giây; B=1.000 → 100 requests, khoảng 0,3 giây. Nhưng nếu mỗi request 1.000 items kéo dài transaction/serialization và gặp broker message limits, tổng latency có thể lại xấu.

Thực tế còn có overlap giữa gửi/nhận, nhiều workers và broker queues; **không cộng thẳng 3 giây overhead như thể mọi request chạy tuần tự** khi hệ thống đang pipeline concurrency.

## 27. Retry và restart tạo throughput thô khác throughput hữu ích

Giả sử worker xử lý 12.000 item invocations/s, trong đó 2.000 là retry cùng logical items do DB deadlock hoặc duplicate request. Nếu sau cùng chỉ có 10.000 unique logical effects được commit, throughput nghiệp vụ là **10.000 effects/s**, không phải 12.000.

Các chỉ số phải phân biệt:

| Chỉ số | Dùng cho | Không nên suy ra |
| --- | --- | --- |
| `processor.calls_total` | CPU work thực tế | Committed logical records |
| `writer.batch.attempts_total` | Số lần thử ghi | Successes |
| `db.transactions.committed_total` | Commit events | Mỗi transaction đều chứa records mới |
| `logical.effects.applied_total` | Business outputs mới | Tất cả expected inputs đã covered |
| `dedup.noop_total` | Replay được idempotency chặn | Lỗi nghiệp vụ luôn luôn |
| `retry.total` | Overhead/failure pressure | Retry làm dữ liệu đúng hay sai |
| `job.restart.total` | Khả năng phục hồi | Không bị data loss |

**Latency cũng phải theo logical operation**, không chỉ attempt: một record mất 80 ms trong attempt cuối nhưng đã chờ retry/backoff 30 giây sẽ có **end-to-end latency >30 giây**. Nếu dashboard chỉ đo `worker.process.duration` ở attempt thành công, p99 latency thực bị che.

### Rollback blast radius

Một chunk đã process 900 items thì DB deadlock, transaction rollback; khi retry, không được đếm 900 processor calls trước đó thành **committed throughput**. Tăng chunk size có thể làm overhead cố định giảm, nhưng khi lỗi tăng sẽ tạo **retry amplification**; vì vậy benchmark có lỗi hữu hạn quan trọng như benchmark happy-path.

## 28. Chọn retry/backoff theo SLO, không retry vô hạn

Một retry policy nên định nghĩa:

1. **Lỗi nào transient** (deadlock, timeout cụ thể) và đủ điều kiện retry.
2. **Giới hạn số lần thử/elapsed budget** theo operation.
3. **Backoff/jitter** để tránh mọi worker retry cùng lúc lên DB đang quá tải.
4. **Side-effect idempotency** khi outcome commit không rõ.
5. **Điều kiện fail/quarantine** và recovery khi hết budget.

~~~java
// Bộ khung minh họa Spring Batch 5.x.
return new StepBuilder("workerStep", jobRepository)
        .<InputRecord, OutputRecord>chunk(200, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
~~~

**Không coi `retryLimit(3)` là toàn bộ SLO latency.** Thời gian mỗi attempt, backoff, broker redelivery và queue wait có thể cộng thành nhiều giây/phút. Với distributed middleware, worker retry và broker redelivery là **hai cơ chế khác nhau**, có thể nhân số lần work nếu không kiểm soát.

**Cảnh báo:** không `skip(Exception.class)` chỉ để throughput báo cao hơn. Skip records không có quarantine/quality gate có thể khiến job `COMPLETED` nhưng thiếu giao dịch.

## 29. Priority, fairness và hai SLA khác nhau

Giả sử 99% records là nightly reconciliation không cần kết quả tức thời; 1% là giao dịch rủi ro cần hiện trong 10 giây. Nếu cùng vào một FIFO queue với throughput cao nhưng backlog 30 phút, nhóm rủi ro không thể đạt SLA dù worker code chỉ tốn 5 ms/item.

Các lựa chọn:

- **Tách luồng/queue/pool** cho critical events và batch backfill.
- Dành một phần capacity riêng (reservation), tránh backfill chiếm hết DB connections.
- Dùng weighted fair scheduling hoặc giới hạn concurrent work theo tenant.
- Thiết kế chunk nhỏ hơn cho latency-sensitive workload, chunk lớn cho bulk ingestion.
- Chỉ publish kết quả được xác minh; không hạ chuẩn correctness để đổi latency thấp.

**Tradeoff rõ ràng:** dành resources cho event critical có thể làm bulk-job throughput thấp hơn một chút, nhưng đạt **mục tiêu hệ thống tổng thể** tốt hơn. Một benchmark chỉ đo toàn bộ records/s sẽ không phản ánh giá trị này.

## 30. Memory, GC và data size distribution

Nhiều chunks in-flight, nhiều partitions và prefetch lớn làm số item objects đang giữ trong heap tăng. Gần memory limit, JVM có thể có long GC pauses, allocation stalls hoặc OOM; p99 latency tăng mạnh.

**Cần đo:**

- Heap used/max, allocation rate, GC pause p95/p99 và full GC.
- Số items/chunks buffered và bytes/request; không chỉ record count.
- Object size distribution, các record ngoại lệ có payload lớn.
- Số `ExecutionContext`/reader state và cached metadata.
- Broker in-memory bytes/unacked payload.
- Tốc độ spill-to-disk/temp file và áp lực OS page cache nếu có.

Ví dụ: 1.000 records/chunk × 8 chunks in-flight × trung bình 20 KiB/object = **~156,25 MiB** payload thô trong JVM, **chưa tính** Java object overhead, copies khi serialization, driver buffers và output objects. Nếu 1% items nặng 2 MiB, tail memory có thể lớn hơn dự đoán từ kích thước trung bình.

Không dùng một `chunkSize` chung cho CSV records vài trăm bytes và JSON documents vài megabytes. **Memory budget phải tính theo bytes và concurrency**, không chỉ items.

## 31. Thêm metrics có mốc commit rõ ràng

Micrometer có thể đo time/counters cho các đoạn khác nhau. Ví dụ dưới đây chỉ đo **thời gian xử lý worker step**, **không phải thời gian DB commit của từng chunk**:

~~~java
@Bean
StepExecutionListener workerStepTimingListener(MeterRegistry registry) {
    // Test/telemetry state chỉ sống trong JVM này; không phải checkpoint.
    ConcurrentMap<Long, Long> startedAt = new ConcurrentHashMap<>();
    return new StepExecutionListener() {
        @Override
        public void beforeStep(StepExecution stepExecution) {
            Long id = stepExecution.getId();
            if (id != null) {
                startedAt.put(id, System.nanoTime());
            }
        }

        @Override
        public ExitStatus afterStep(StepExecution stepExecution) {
            Long id = stepExecution.getId();
            Long start = id == null ? null : startedAt.remove(id);
            if (start != null) {
                long elapsed = Math.max(0L, System.nanoTime() - start);
                Timer.builder("batch.worker.step.duration")
                        .tag("status", stepExecution.getStatus().name())
                        .tag("step", "workerStep")
                        .register(registry)
                        .record(elapsed, TimeUnit.NANOSECONDS);
            }
            return stepExecution.getExitStatus();
        }
    };
}
~~~

**Đây là ví dụ đo minh họa với các giới hạn:**

- `System.nanoTime()` được dùng để đo elapsed **trong cùng JVM**, không đem giá trị này làm timestamp liên process hay dùng làm checkpoint có ý nghĩa sau crash.
- `startedAt` là map tạm theo StepExecution ID trong một JVM; hoàn toàn **không lưu monotonic timestamp vào ExecutionContext/JobRepository**. Production có thể dùng Observation lifecycle phù hợp thay vì duy trì map thủ công.
- `afterStep` phản ánh execution lifecycle, không nhất thiết đã persist xong mọi metadata hoặc business publication.
- Nếu worker JVM bị kill trước `afterStep`, timer này có thể **không ghi nhận** duration; cần heartbeat/JobRepository và monitor timeouts.
- Không gắn `jobExecutionId`, `recordId` hoặc `chunkSequence` làm metric tags high-cardinality. Đưa chúng vào logs/traces có retention/permission.
- Để đo **chunk commit outcome**, instrument transaction manager/`TransactionSynchronization.afterCommit` đúng chỗ thay vì lấy `ItemWriteListener.afterWrite` làm bằng chứng.

**Nếu application có sẵn Spring Batch Micrometer/Observation metrics**, ưu tiên tận dụng instrumentation hiện có, không đếm trùng metric cùng ý nghĩa chỉ vì viết listener mới.

## 32. Tracing end-to-end: tìm chỗ chậm thật

Ở remote chunking:

~~~text
manager: source read → chunk formed
manager: broker publish
broker: queue wait
worker: consume/deserialize
worker: processor
worker: DB write + transaction commit outcome
worker: reply publish
manager: reply receive/correlation
downstream: visibility/publication
~~~

**Correlation ID của protocol** khác `traceId`; một trace có thể gồm nhiều chunk messages, còn một logical chunk có thể redeliver thành nhiều attempts/spans. Dùng cả hai khi điều tra.

Phân tích:

- Broker queue wait 15 s, worker process 30 ms: tăng timeout không giải quyết; cần capacity/backpressure/consumer diagnosis.
- Worker process 5 s, CPU cao: profile processor, cân nhắc parallelism và data skew.
- DB commit 3 s, connection pending cao: tối ưu DB/pool, giảm concurrency hoặc chunk size.
- Worker publish reply xong nhưng manager chờ 60 s: xem reply routing, wrong correlation, stale/duplicate responses.
- Tất cả chunks committed nhưng batch report chỉ xuất hiện sau 20 phút: publication/validation barrier mới là bottleneck của end-to-end SLA.

**Không cộng các p99 từng tầng thành p99 tổng**. Để xác định critical path, dùng spans của **cùng logical request**, metrics hỗ trợ và chú ý clock skew giữa manager/worker hosts.

## 33. Benchmark phải tái hiện workload thật, không chỉ chạy “happy path”

Một benchmark có giá trị cần mô tả **ít nhất sáu biến**:

1. **Input snapshot:** số records, size distribution, tenant mix, sparse IDs/files và tỷ lệ valid/invalid.
2. **Arrival profile:** dữ liệu có sẵn một lần, theo từng burst hay đến đều? Có yêu cầu time-to-first-result không?
3. **Environment:** Java/Spring Batch/DB version, CPU/memory, worker nodes, mạng, storage, broker, pool sizes.
4. **Configuration:** chunk size, partition count, executor threads/queue, prefetch, consumer concurrency, DB connection pool.
5. **Failure profile:** xác suất transient DB errors, broker retries, worker crash, slow partitions và recovery path.
6. **Outcome definition:** input covered, logical records committed, skipped/quarantined, job completion, publication, p95/p99.

**Chạy từng cấu hình nhiều lần** và giữ cách tạo dữ liệu giống nhau; ghi median cùng variability/CI nếu đủ mẫu. Dùng warm-up hoặc loại trừ ảnh hưởng khởi động classloader/connection/cache theo thiết kế benchmark, nhưng **đừng xóa chi phí warm-up** nếu chính startup latency là phần SLA của job ngắn.

### Không so database có trạng thái khác nhau

Nếu test A chèn 3 triệu records vào bảng trống còn test B thử `ON CONFLICT DO NOTHING` trên 3 triệu key **đã tồn tại**, throughput không cùng ý nghĩa. Reset snapshot/target chính xác trước mỗi run hoặc dùng một set key/version mới nhưng giữ workload/DB statistics tương đương. Cũng cần đo index bloat, WAL/checkpoint và cache warmth.

## 34. Ma trận benchmark có kiểm soát

Một thử nghiệm ba pha, mỗi pha chỉ thay đổi nhóm tham số liên quan:

| Pha | Tham số thử | Giữ cố định | Đọc kết quả |
| --- | --- | --- | --- |
| A. Chunk | `B=50,200,500,1000` | Worker=1, input/DB như nhau | Commit overhead, rollback, p99 |
| B. Concurrency | `workers=1,2,4,8` | Chọn 1–2 chunk sizes tốt từ A | Speedup, pool wait, queue age |
| C. Transport | Prefetch/in-flight budget & worker count | Source snapshot, business logic | Broker wait, throughput, redelivery |
| D. Failure | Inject retry/crash/slow partition | Cấu hình ứng viên | Recovery latency, duplicate effects |
| E. Burst | Arrival 0,5×/0,8×/1,0×/1,2× capacity | Các candidate configs | Backlog growth, p99 SLO |

**Không đổi `chunkSize`, `gridSize`, pool size và DB index cùng một lúc**, vì sẽ khó biết thay đổi nào cải thiện hoặc làm xấu latency. Sau khi tìm được từng hiệu ứng, có thể test tương tác giữa các tham số bằng thiết kế thí nghiệm có kiểm soát.

### Bảng kết quả minh họa, không phải số liệu sản phẩm

| Config | Committed throughput | Record p99 latency | DB pool pending | Rollback/retry | Đạt SLO? |
| --- | ---: | ---: | ---: | ---: | --- |
| B=100, W=2 | 3.200 items/s | 0,35 s | Thấp | Thấp | Chưa đủ throughput |
| B=500, W=4 | 4.600 items/s | 0,80 s | Thấp | Thấp | Có thể đạt |
| B=1000, W=8 | 4.800 items/s | 4,5 s | Cao | Tăng | Không nếu p99 ≤2s |
| B=2000, W=16 | 4.650 items/s | 12 s | Rất cao | Tăng mạnh | Không |

Các giá trị **chỉ giả lập một hình dạng kết quả thường gặp**. Thực tế có thể khác hẳn theo DB, I/O, workload và measurement boundary. Mẫu này cho thấy ứng viên **B=500, W=4** có thể tốt hơn việc đẩy tối đa worker/chunk khi đặt ràng buộc p99.

## 35. Chọn điểm trên Pareto frontier

Hai cấu hình có thể:

- A: throughput 5.000 items/s, p99 5 giây.
- B: throughput 4.800 items/s, p99 0,8 giây.

Không thể gọi A “tốt hơn tuyệt đối”: A chỉ cao hơn ~4,2% throughput nhưng p99 tệ hơn hơn 6 lần. Nếu SLO throughput ≥4.000 items/s và p99 ≤2 giây, B hợp lệ còn A không.

**Pareto frontier** là tập cấu hình không có cấu hình khác vừa throughput cao hơn hoặc bằng, vừa latency thấp hơn hoặc bằng (và ít nhất một chiều tốt hơn), với các điều kiện correctness/chi phí được giữ. Khi thêm tiêu chí **memory, DB cost, rollback risk, carbon/compute budget**, frontier là đa chiều.

### Một quy tắc ra quyết định thực dụng

1. Loại mọi cấu hình không đạt **correctness, data coverage, crash recovery**.
2. Loại cấu hình vi phạm hard SLO về **p99 latency, batch deadline, memory, pool, backlog**.
3. Trong phần còn lại, chọn throughput/cost phù hợp và có **headroom** cho bursts/worker loss.
4. Benchmark lại khi thay schema, data distribution, DB version, broker topology hoặc business rules.

**Không chọn cấu hình nằm sát saturation chỉ vì benchmark ngày hôm đó vừa đủ SLA.** Một burst nhỏ, GC pause hoặc slow query có thể đẩy p99 vượt ngưỡng.

## 36. Failure injection: thông lượng có còn hữu ích khi lỗi xảy ra?

| Trường hợp | Injection | Điều phải đo và chứng minh |
| --- | --- | --- |
| F01. DB deadlock | Hai workers lock rows ngược thứ tự | Bounded retry/fail; committed throughput, p99, không lost updates |
| F02. Connection pool cạn | Giảm pool/giữ connections có chủ đích | Pending tăng được thấy; không treo vô hạn, không loss |
| F03. Processor chậm bất thường | Sleep/CPU load ở một partition kiểm soát | Straggler/makespan, fairness, không timeout giả |
| F04. Worker crash giữa chunk | Kill JVM trước commit | Chunks rollback/replay đúng, latency recovery |
| F05. Crash sau commit trước reply | Kill worker giữa DB commit và broker ACK/reply | Idempotency, multiple attempts vs unique effects |
| F06. Broker backlog | Giảm consumers hoặc inject network latency | Queue age, backpressure, manager in-flight bound |
| F07. Reply routing sai | Cho reply vào wrong consumer/queue | Manager timeout rõ, protocol correlation, không fake success |
| F08. Source snapshot đổi | Sửa file/staging sau checkpoint | Fail/reconcile, không chạy nhanh nhưng sai dữ liệu |
| F09. Large payload outlier | Trộn 1% records kích thước lớn | Memory p99/GC, broker limits |
| F10. Skip nhiều | Dữ liệu malformed có policy | Quarantine durable; quality gate chặn publish nếu vượt |
| F11. Partition skew | Một partition có 80–90% work | Tail makespan và idle workers |
| F12. Downstream chậm | Tăng DB commit latency 10× | Backpressure hoạt động, retry không storm |
| F13. Queue full/rejection | Giảm capacity của executor | Bộc lộ failure, không rơi mất StepExecution |
| F14. Whole-job restart | FAILED JobInstance với partial commits | Same snapshot, đúng kết quả, đo recovery SLA |

**Không coi test worker throw exception là thay thế cho kill JVM**: trong local partitioning, kill JVM làm cả manager và workers trong process chết; trong distributed messaging còn có ACK/reply/multiple attempts. Test với broker/DB thật khi hành vi transport và transaction là trọng tâm.

## 37. Correctness luôn đi cùng chỉ số hiệu năng

Một benchmark Spring Batch cần kiểm **sau mỗi run**:

1. `JobExecution/StepExecution` trạng thái theo chính sách; không còn work pending/UNKNOWN bị coi thành công.
2. Expected source keys thuộc đúng **output, filtered hoặc quarantined** theo contract.
3. Không có source key vừa bị xử lý tốt vừa bị tính skip sai.
4. Business values, tenant scope, rule version và reconciliation totals khớp expected.
5. Không có duplicate logical effects khi retry, broker redelivery hoặc restart.
6. Chunks đã commit có metadata/outcome phù hợp; nếu chưa chắc chắn, đo `unknown` riêng.
7. Nếu whole-batch publication cần atomic logical view, chỉ `PUBLISHED` sau khi tất cả worker outcomes đã được verify.

Ví dụ SQL PostgreSQL cho một bài toán **mỗi input hợp lệ sinh đúng một output**:

~~~sql
-- Missing business output:
SELECT i.record_id
FROM staged_record i
LEFT JOIN normalized_record o
  ON o.batch_key = i.batch_key
 AND o.record_id = i.record_id
WHERE i.batch_key = :batchKey
  AND o.record_id IS NULL;

-- Unexpected business output:
SELECT o.record_id
FROM normalized_record o
LEFT JOIN staged_record i
  ON i.batch_key = o.batch_key
 AND i.record_id = o.record_id
WHERE o.batch_key = :batchKey
  AND i.record_id IS NULL;
~~~

Hai truy vấn giả định fixture có `staged_record`, `normalized_record` và business key tương ứng; nếu filter/skip hợp lệ hoặc một record tạo nhiều output, phải mở rộng phép đối soát đúng cardinality. **COUNT(*) bằng nhau vẫn có thể che một record thiếu cộng với một record thừa**.

**Chỉ đưa committed logical outputs vào throughput KPI** sau khi pass data correctness policy; `retry attempts/s`, `read/s` và `message ACK/s` là các metric riêng.

## 38. Runbook: throughput thấp, latency p99 cao

1. **Xác nhận SLO và ranh giới:** đang nói `records/s`, `chunks/s`, job makespan hay record-to-visible latency? Input có burst không?
2. **Xác nhận correctness:** JobRepository, durable output, missing/duplicate keys, failed/unknown chunks và publication lag.
3. **Đo arrival vs completion:** queue depth/oldest age và pending requests có tăng liên tục không?
4. **Xác định bottleneck:** manager reader/serialization, CPU processor, JDBC writer/commit, broker send/receive, reply routing hay validation?
5. **Kiểm resource:** CPU, heap/GC, DB active/pending connections, row locks/deadlocks, broker unacked/prefetch, disk/network IOPS.
6. **Đo concurrency hiệu dụng:** active workers khác `gridSize`/number of pods; executor queue có tasks chờ hay bị rejected không?
7. **So chunk size:** commit overhead/item, transaction duration, rollback cost và p99 theo B.
8. **Xem skew:** một partition/file lớn có làm job tail kéo dài trong khi workers khác rảnh không?
9. **Xem retry/backoff:** logical success rate khác invocation/message rate ra sao?
10. **Kiểm backpressure:** manager có tiếp tục dispatch khi worker/DB đã bão hòa không? Có bị head-of-line blocking không?
11. **Thử thay một tham số:** chunk, concurrency, prefetch, pool hoặc partition strategy; ghi baseline và kết quả.
12. **Kiểm lại sau tuning:** output đúng, p95/p99 đạt, recovery giữ nguyên, có headroom và runbook rollback.

### Dấu hiệu A — tăng workers nhưng throughput đứng yên

~~~text
W=4:   4.500 logical records/s, p99=0,8s
W=8:   4.600 logical records/s, p99=3,5s
DB CPU=95%, connection pending cao, locks tăng

=> DB đã bão hòa; giảm W hoặc tối ưu SQL/indices,
   chunk transaction/locking, pool và workload mix.
   Không tăng W lên 16 chỉ để thử vận may.
~~~

### Dấu hiệu B — manager báo gửi rất nhanh nhưng output đến chậm

~~~text
Manager dispatch = 10.000 items/s
Worker commit = 4.000 items/s
Broker backlog tăng, oldest age liên tục cao

=> Đo capacity thật của worker/DB và bật backpressure
   theo pending outcomes; không gọi dispatch rate là throughput.
~~~

### Dấu hiệu C — trung bình tốt nhưng p99 rất tệ

~~~text
Mean chunk service=40ms, p99 request end-to-end=20s.
Broker oldest age=18s.

=> Tập trung queueing và fairness/prefetch,
   không tối ưu CPU processor chỉ tiết kiệm vài ms.
~~~

**Không “chữa” latency bằng cách tăng timeout vô hạn, tắt dead-letter, bỏ checksum/validation hoặc sửa metadata JobRepository thành COMPLETED**. Những thao tác đó có thể làm dashboard đẹp nhưng không cải thiện hệ thống và có nguy cơ mất dữ liệu.

## 39. Những sai lầm thường gặp khi tối ưu throughput

| Sai lầm | Vì sao sai | Thay bằng |
| --- | --- | --- |
| Đo `readCount/duration` rồi gọi committed throughput | Có retry, filter, rollback | Logical commit/output coverage metrics |
| Chỉ tối đa hóa records/s | Có thể vi phạm p99 latency/quality | Tối ưu có SLO constraints |
| Tăng chunk size không giới hạn | Transaction/lock/memory/retry cost tăng | Sweep chunk sizes và đo tail |
| Tăng `gridSize` dù pool chỉ 4 threads | Không tạo thêm concurrency thực | Đo active workers và executor queue |
| Tăng pool threads khi DB 100% | Thêm contention và WIP | Tìm bottleneck, giảm overload |
| Tin `prefetch` lớn luôn tốt | Uneven work, redelivery burst | Bounded prefetch theo workload |
| Dispatch rate bằng processing rate | Queue có thể tăng vô hạn | Queue age + correlated completion |
| Tin DB connection count = worker count | Cursor, writer, metadata có nhu cầu khác | Đo pool active/pending và lifecycle |
| Đo p99 ở từng tầng rồi cộng | Percentiles không cộng tuyến tính | End-to-end trace cùng request |
| Chỉ đo mean | Tail bị che | p95/p99 và oldest age |
| Dùng buffer vô hạn | RAM/GC/latency tăng | Backpressure và bounded queues |
| Không test restart khi thay chunk size | Checkpoint/transaction behavior thay đổi | Failure injection + idempotent writer |
| Đếm redelivery thành work mới | Inflated throughput | Logical business operation IDs |
| Dùng `skip(Exception.class)` để job xong nhanh | Thiếu business records | Classify retry/skip/fail + quarantine |
| Benchmark source/DB ở trạng thái khác nhau | So sánh không công bằng | Immutable snapshot/controlled reset |
| Chia partition đều theo ID width | Có thể rất lệch record volume | Skew-aware partitioning |
| Không đo validation/publication | Chỉ thấy speedup worker | Record-to-visible, job makespan |
| Chọn 99% utilization cho SLO p99 | Queueing cực nhạy với bursts | Duy trì capacity headroom |

## 40. Bài thực hành: tìm điểm cân bằng tối ưu

Xây một job Java 17+/Spring Batch 5.x nhập 1 triệu records từ snapshot PostgreSQL hoặc file CSV immutable, chia theo những khoảng source keys không giao nhau. Output database có unique business key và idempotent writer; mỗi lần benchmark có `batchKey`/source version rõ.

**Phần A — xác lập baseline**

1. Chạy một worker, chunk 100, đo **committed logical records/s**, job wall time, record p50/p95/p99 latency và DB connection wait.
2. Đo thêm time-to-first-result và time-to-publication nếu downstream không đọc trực tiếp DB.
3. Đối soát exact keys/values, không chỉ COUNT(*).

**Phần B — chunk và concurrency**

4. Thử chunk 50/200/500/1.000, giữ worker=1; ghi commit latency, WAL/lock wait, memory.
5. Giữ 1–2 chunk candidates, thử workers=1/2/4/8 qua local partitioning; đo active threads, pool pending, skew.
6. Nếu input/DB đủ lớn, thử remote partitioning và so network/manager overhead; đừng so hai snapshot khác nhau.
7. Với remote chunking, thử pending request budgets và broker prefetch; đo queue oldest age, redelivery và correlated completion.

**Phần C — failure và SLO**

8. Kill worker trước DB commit; kiểm rollback và restart.
9. Kill sau DB commit trước reply; kiểm idempotency và recovered outcome.
10. Tiêm 1% transient failures với bounded retry và một slow partition.
11. Tạo burst input trên mức capacity ngắn hạn; backpressure phải giới hạn WIP và không làm mất work.
12. Chọn cấu hình đạt cả `throughput ≥ target`, `p99 latency ≤ SLO`, bounded memory và đúng business outcomes.

**Phần D — báo cáo**

13. Trình bày đồ thị `committed throughput vs p99 latency` cho từng cấu hình.
14. Đánh dấu knee point/Pareto candidates và giải thích resource bottleneck thay đổi ra sao.
15. Ghi đề xuất cấu hình, capacity headroom, ngưỡng alert và điều kiện rollback khi production drift.

**Điều kiện đạt:** một cấu hình tối ưu được **xác nhận bằng dữ liệu**, không phải suy từ công thức cố định; không có missing/duplicate logical effects và restart/cancellation đều tuân theo protocol.

## 41. Checklist trước production

- [ ] Định nghĩa throughput là **completed/committed logical outcome**, không phải dispatch/read/attempt rate.
- [ ] Xác định latency boundaries: queue wait, worker time, chunk commit, record-to-visible và job wall time.
- [ ] Có SLO p95/p99/oldest age và whole-batch deadline, không chỉ mean.
- [ ] Phân loại workload bulk với latency-sensitive; bảo vệ fairness/capacity khi cần.
- [ ] Input source bất biến, snapshot/version và partition mapping ổn định qua restart.
- [ ] Có baseline và benchmark chunk size với lock/commit/memory/retry metrics.
- [ ] JDBC batch/SQL optimization được kiểm cùng business idempotency.
- [ ] Reader không chia mutable cursor sai giữa threads; dùng `@StepScope` khi partitioning cần.
- [ ] Executor active workers, gridSize, queue capacity và DB connection pool được sizing bằng đo đạc.
- [ ] Có test DB pool exhaustion, executor rejection và hot row contention.
- [ ] Có đo skew/slowest partition, không chỉ average partition latency.
- [ ] Remote chunking đo manager dispatch, broker queue age, worker commit và reply correlation riêng.
- [ ] Pending requests/prefetch/backpressure có giới hạn rõ, không queue vô hạn.
- [ ] Không nhầm broker ACK, writer call, DB commit và JobRepository COMPLETED.
- [ ] Retry/skip/fail phân loại rõ, có bounded backoff và quality gate.
- [ ] Writer idempotent, kiểm duplicate conflict khác content, chịu được crash sau commit trước reply.
- [ ] Benchmark nhiều lần trên cùng snapshot, tương đương môi trường production và có run log.
- [ ] Correctness reconciliation theo key/value/filter/quarantine được chạy sau mọi benchmark.
- [ ] Có test slow partition, queue burst, long GC, source mutation và whole-JVM crash.
- [ ] Metrics low-cardinality, trace/logs cho các request chậm và outcome chưa rõ.
- [ ] Có capacity headroom cho traffic burst, worker loss và maintenance.
- [ ] Có runbook xác định bottleneck trước khi tăng threads, chunk size hoặc timeout.
- [ ] Chỉ publish batch khi worker outcomes và business reconciliation đúng.

**Ghi nhớ:** trong Spring Batch scaling, **latency thấp** và **throughput cao** không đối lập tuyệt đối, nhưng có những điểm đánh đổi rõ tại **chunk boundaries, queueing, concurrency, transaction locks, prefetch, retry và publication**. Tăng batch size giúp giảm fixed overhead, tăng workers giúp tận dụng tài nguyên rảnh; cả hai có thể phản tác dụng khi vượt capacity hoặc làm tail latency tăng. Hãy đo **committed throughput, end-to-end p95/p99, backlog, resource saturation và recovery correctness** trên cùng snapshot, rồi chọn cấu hình đạt **SLO có headroom** — không chạy đua theo một con số records/s tối đa.
