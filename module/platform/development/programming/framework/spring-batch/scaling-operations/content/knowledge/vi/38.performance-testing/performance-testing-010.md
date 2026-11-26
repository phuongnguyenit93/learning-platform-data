# Test soak dài giờ cho Spring Batch scaling

## Mục tiêu bài học

Một Spring Batch job xử lý 20 triệu records đầu tiên trong 45 phút, throughput tốt và p95 chunk latency thấp. Nhưng sau khi hệ thống chạy liên tục 18 giờ, RAM của worker tăng dần, queue tích lũy thêm hàng triệu items, connection pool không còn chỗ trống, JobRepository phình to và một lần worker restart khiến vài partitions bị xử lý trùng. **Benchmark ngắn đã chứng minh hệ thống nhanh ở thời điểm đầu; nó chưa chứng minh hệ thống ổn định khi chạy lâu.**

**Soak test** (endurance test, kiểm thử chịu tải dài giờ) chủ động vận hành pipeline **trong thời gian đủ dài và theo mô hình workload thực tế** để phát hiện suy thoái có tính tích lũy: memory/thread/connection leak, queue drift, database growth, lock contention, GC/latency degradation, thiếu ổ đĩa, broker lag, checkpoint/restart sai và sai lệch business data.

Bài thuộc chương **Performance testing** của module **SPRING_BATCH_SCALING_OPERATIONS**. Module học mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và các mô hình phân tán; đồng thời đo bottleneck, giữ thread safety, retry/restart, vận hành job và chọn kiến trúc phù hợp CPU, bộ nhớ, database, broker và worker thực tế.

Sau bài, bạn có thể:

- Phân biệt soak với load/stress/spike/capacity tests.
- Xây **workload model**, thời gian warm-up/steady-state, đầu vào và phân phối key/partition đại diện.
- Đặt ngưỡng PASS/FAIL cho throughput hữu ích, backlog, latency, GC, RAM, connection pool, metadata và data correctness.
- Theo dõi memory leak chậm bằng **xu hướng sau GC**, không chỉ giá trị heap tại một thời điểm.
- Kiểm tra thread safety, pool exhaustion, JobRepository growth, database WAL/bloat và queue drift sau nhiều giờ.
- Bố trí chạy thử với Spring Batch 5.x và Micrometer/Actuator mà không làm méo kết quả do đo đạc quá mức.
- Đưa fault injection, restart/rollback, redelivery và validation vào thử nghiệm mà vẫn phân biệt baseline với recovery.
- Thiết kế các kịch bản 8/24/48/72 giờ, so sánh trước/sau thay đổi concurrency và lập runbook phân tích.
- Đối soát business outcomes trước khi kết luận một hệ thống vừa **nhanh, vừa bền, vừa đúng**.

## 1. Soak test trả lời câu hỏi nào?

Một bài test chạy 15 phút có thể cho biết một cấu hình chạy được 12.000 items/s trong trạng thái tương đối lý tưởng. Soak test hỏi thêm:

- Sau 12 giờ, throughput có giữ được không hay giảm từng giờ?
- Với arrival rate ổn định, queue backlog có tăng không giới hạn?
- Heap sau **full/major GC thích hợp** có tăng dần không?
- Thread count, file descriptors, connections và direct memory có tích lũy?
- Database có tăng thời gian commit vì WAL, autovacuum, index/metadata growth?
- JobRepository có chịu được hàng nghìn StepExecutions, retries và restarts không?
- Remote workers có giữ được request/reply throughput khi broker redelivery và consumer lag tăng?
- Một partition nóng có tạo tail latency khiến JobExecution tổng bị kéo dài?
- Hệ thống có tự hồi phục sau worker kill, DB failover hoặc broker gián đoạn?
- Có thể chứng minh không missing/duplicate data sau 24 giờ và sau restart không?

**Mục tiêu không phải chạy thật lâu bằng mọi giá**, mà là chứng minh các **bất biến vận hành và nghiệp vụ** còn đúng trong những tình huống có khả năng xảy ra sau thời gian dài.

## 2. Phân biệt soak, load, stress, spike và chaos test

| Kiểu test | Tác nhân thay đổi chính | Câu hỏi |
| --- | --- | --- |
| **Load test** | Tải dự kiến trong khoảng tương đối ngắn | Có đáp ứng latency/throughput mục tiêu? |
| **Capacity test** | Tăng tải có kiểm soát | Tối đa bao nhiêu trước khi vi phạm SLA? |
| **Stress test** | Tải vượt ngưỡng/bão hòa | Hệ thống suy giảm và từ chối tải thế nào? |
| **Spike test** | Tải tăng/giảm đột ngột | Queue, pool và recovery có chịu được burst? |
| **Soak/endurance** | **Thời gian** ở workload đại diện | Có tích lũy rò rỉ, backlog hoặc tail degradation? |
| **Chaos/fault injection** | Chủ động phá dependency/worker | Có phục hồi đúng sau sự cố? |
| **Recovery test** | Restart từ checkpoint và đối soát | Có tiếp tục đúng và trong thời hạn? |

Các kiểu test có thể kết hợp, nhưng nên tách **soak baseline không lỗi** khỏi **soak có lỗi theo lịch** để không quy nhầm nguồn suy giảm.

Ví dụ broker down 5 phút trong bài soak sẽ tạo backlog chủ động. Một đường queue length tăng trong 5 phút đó **không phải bằng chứng memory leak**; cần xem queue có drain khi broker phục hồi và arrival rate quay về mức mục tiêu không.

## 3. Không phải job batch nào cũng chạy liên tục 24 giờ

Spring Batch thường xử lý **đầu vào hữu hạn**, kết thúc khi hết data. Muốn soak 24–72 giờ phải xây workload đại diện mà **không làm biến dạng semantics**.

Có ba kiểu thử nghiệm:

1. **Một JobExecution rất lớn:** workload đủ lớn để một job chạy trong thời gian dự kiến; thích hợp phát hiện drift trong reader/writer, memory, broker và partition tail. Không dùng vô hạn nếu production thực chạy 20–60 phút.
2. **Chuỗi JobInstances theo kỳ:** chạy nhiều jobs liên tiếp qua scheduler để quan sát JobRepository/history buildup, resource cleanup giữa jobs, cache leak và connection pools được tái sử dụng.
3. **Nhiều jobs song song theo lịch thực:** mô phỏng nhiều business periods/workloads dùng chung database, executor, broker và object storage; thích hợp phát hiện cross-job contention.

**Cấu hình soak phải mô phỏng vòng đời thực**. Một job thực tế chạy 30 phút mỗi giờ nên được test bằng nhiều runs, không mặc nhiên thay reader thành vòng `while(true)` trong cùng StepExecution. Cách đó có thể bỏ qua JobInstance creation, Step close/reopen, scheduler overlap và metadata growth.

### Soak time nên chọn thế nào?

Thời gian phụ thuộc chu kỳ lỗi nghi ngờ, retention/TTL, autoscaling, database checkpoint/vacuum cadence, traffic profile và ngân sách. Ví dụ 8 giờ để sàng lọc, 24 giờ để vượt một chu kỳ ngày, 48–72 giờ để phát hiện leak chậm hoặc hoạt động nền có tính chu kỳ. **Không có quy tắc chung “72 giờ luôn đủ”**; nếu lỗi chỉ xuất hiện sau weekly cleanup, bài test phải bao phủ chu kỳ đó hoặc dùng kỹ thuật gia tốc có kiểm soát.

## 4. Workload model: đầu vào nào là đại diện?

Một workload chỉ có 10 triệu hàng giống hệt nhau rất dễ cache và tránh hot keys, nên thường **không đại diện** cho production.

Định nghĩa trước:

| Chiều dữ liệu | Ví dụ |
| --- | --- |
| Dung lượng | 12–50 triệu events/JobInstance; nhiều instances theo lịch |
| Record size | p50 2 KiB, p99 128 KiB; có outliers |
| Key cardinality | Nhiều unique keys, một nhóm hot keys, version collisions |
| Partition skew | Một số partitions chiếm 2–4 lần dữ liệu trung bình |
| Business transform | CPU parsing, enrichment/DB lookup, validation, serialization |
| Read/write ratio | Số SELECT, UPDATE, INSERT trên mỗi record |
| Reject/skip | Tỷ lệ lỗi hợp lệ, duplicates, malformed rows có kiểm soát |
| Retry | Deadlock/network transient với tỷ lệ thật hoặc inject riêng |
| External I/O | Broker confirm latency, HTTP rate limits, file object storage |
| Schedule | Arrival rate, giờ cao điểm, overlap jobs, recovery windows |
| Data lifecycle | TTL, cleanup, JobRepository history, outbox/inbox retention |

Ví dụ cần cả records hợp lệ, rejected, duplicate deliveries và values bất thường. Nếu chỉ dùng `id = 1..N` với các payload rỗng, test có thể đo tốc độ ghi một workload không phản ánh serialization, index contention và GC allocation thật.

### Chốt source snapshot và phiên bản

Khi soak cần restart, input phải **bất biến** theo `sourceVersion`/cutoff. Không chạy worker 20 giờ trên một file path có thể bị upstream ghi đè rồi kết luận checkpoint an toàn.

## 5. Open workload và closed workload: phân biệt arrival và concurrency

Với hệ thống có queue/broker, hai cách tạo tải khác nhau:

- **Open model:** producer phát items/jobs với **arrival rate** được quy định, độc lập với hệ thống xử lý nhanh/chậm. Nếu service rate giảm, backlog tăng.
- **Closed model:** giữ số clients/requests/active jobs cố định, producer chỉ tiếp tục khi request trước hoàn tất. Khi service chậm, input rate tự giảm.

Một closed test dễ che giấu overload vì lượng việc được phát giảm theo latency. Với queue-backed remote chunking, cần ghi rõ producer có bị backpressure khi queue đầy hay không.

### Ba tốc độ phải đo riêng

\[
\lambda = \text{arrival rate (items/s)}
\]
\[
\mu = \text{sustainable committed processing rate (items/s)}
\]
\[
\Delta Q \approx (\lambda-\mu)\Delta t
\]

Công thức queue drift là **gần đúng khi không có drops, retries/duplicates được xử lý theo thống kê và đủ backlog để service bão hòa**. Nếu `\lambda > \mu` kéo dài, queue có xu hướng tăng dù CPU/heap các worker lúc đầu còn ổn.

**Không dùng “messages consumed/s” thay hoàn toàn cho useful business throughput**: retry/redelivery có thể khiến broker delivery rate rất cao nhưng unique records commit ít.

## 6. Chuỗi pha của một bài soak đáng tin

~~~mermaid
flowchart LR
    P["Preflight: môi trường + dataset"] --> W["Warm-up"]
    W --> B["Steady baseline"]
    B --> L["Long steady soak"]
    L --> F["Optional controlled faults"]
    F --> R["Recovery + drain"]
    R --> V["Data validation"]
    V --> A["Analysis & report"]
~~~

Có thể chia thời gian như:

| Pha | Thời lượng minh họa | Nội dung |
| --- | --- | --- |
| Preflight | Trước run | Kiểm tra version, resource quotas, dashboards |
| Warm-up | 15–45 phút | JIT, caches, connection pools, queries |
| Baseline | 30–60 phút | Ghi chuẩn throughput và resource envelope |
| Steady soak | 8–48 giờ | Đo drift dưới workload đại diện |
| Fault window | 15–60 phút | Worker kill/broker outage/DB failover có kế hoạch |
| Recovery | Tới khi backlog drain | Đo MTTR, checkpoint, duplicate handling |
| Validation | Theo data size | Full count/key/side-effect reconciliation |
| Report | Sau test | PASS/FAIL có evidence và giới hạn |

Số phút/giờ trên là **ví dụ kế hoạch**, không phải mặc định của Spring Batch. Không tính warm-up vào steady-state mean nếu mục tiêu là phân tích memory slope ở trạng thái nóng; đồng thời vẫn giữ đủ dữ liệu warm-up để phát hiện startup leak.

## 7. Môi trường test phải giữ được yếu tố gây lỗi dài hạn

Để kết quả có ý nghĩa, nên mô phỏng:

- Java runtime/JVM flags, Spring Batch/Spring Boot version và cấu hình thực.
- CPU cores, memory limits, container cgroups, GC algorithm.
- DB engine/version, schema, indexes, transaction isolation, pool sizes.
- Broker partition/queue count, durability/acks, consumer prefetch, quotas.
- Worker count, executor type, chunk size, grid size, retry/skip policies.
- Storage throughput/latency, IOPS, fsync/object-store semantics.
- Telemetry sampling/cardinality và overhead của exporters.
- Volume và phân phối business keys như production.
- JobRepository isolation và history growth.
- Upstream/downstream rate limits, schema version và backpressure.

### Isolation và dữ liệu an toàn

- Dùng test tenant/namespaces riêng; không để replay test gửi payment/email thật.
- Nếu dùng production-shaped data, phải mask/minimize PII và tuân quyền dữ liệu.
- Tắt/điều hướng external side effects sang sandbox đáng tin; vẫn đo latency gần production.
- Không dùng production database nếu workload hoặc fault injection có thể gây mất dữ liệu/ảnh hưởng người dùng.

**Một bài soak 48 giờ trên laptop hoặc DB schema trống thường không đo cùng bottleneck** với 24 worker JVM và production PostgreSQL nhiều index/WAL.

## 8. Tài nguyên phải có budget toàn cluster

Ví dụ cấu hình:

~~~text
Worker JVMs:                  8
TaskExecutor max threads/JVM: 12
Hikari max pool/JVM:          16
Manager pool:                 12
Publisher pool:               10
Database connection budget:  180 (sau khi trừ phần hệ thống khác)
~~~

Chỉ riêng worker JDBC pool trần là `8 × 16 = 128` connections, chưa tính manager, publisher, admin, monitoring và DB internal overhead. Tổng dự kiến `128 + 12 + 10 = 150`, còn headroom danh nghĩa 30 **nếu tất cả pools cùng hướng tới một DB và các số trên là max**. Thực tế cần rà connection pool riêng cho JobRepository, transaction managers và bên thứ ba.

### Tránh đánh giá một worker độc lập

Một worker chỉ dùng 60% heap và 20% CPU không có nghĩa scaling từ 8 lên 32 workers tuyến tính. DB locks, connection limits, broker quotas và I/O bandwidth là tài nguyên dùng chung.

**Budget quan trọng hơn một con số concurrency đẹp**. Đo sự thay đổi khi worker số 9, 10,... được bật, và rút lui khi useful throughput không còn tăng.

## 9. Các điều kiện PASS/FAIL phải đặt trước khi chạy

Một bài soak không được tuyên bố thành công chỉ vì “không crash” hoặc vì cuối cùng job COMPLETED.

Acceptance contract minh họa:

| Tiêu chí | Ví dụ ngưỡng có thể đo | Điều kiện |
| --- | --- | --- |
| Useful throughput | ≥ 8.000 unique commits/s trung bình steady | Theo contract và measurement method |
| Window drift | Không giảm quá 10% từ baseline tới last stable hours | Loại fault window riêng |
| Queue backlog | Không có xu hướng tăng khi `\lambda < \mu` | Đủ điều kiện steady |
| p99 chunk latency | `p99 < 3s` ở workload baseline | Cùng bucket/histogram config |
| Heap after GC | Không có positive drift vượt budget | Theo GC/heap class |
| Non-heap/direct | Không tăng không giới hạn | Theo process/container |
| JDBC active connections | Không stuck gần max pool liên tục | Trừ burst có giải thích |
| Threads/FDs | Plateau sau warm-up | Không leak monotonic |
| DB WAL/disk | Tốc độ tăng có retention/drain policy | Không hết disk |
| JobRepository | Query/commit latency nằm budget | Với lịch sử lớn |
| Business correctness | Missing/duplicate unintended = 0 | Reconciliation full scope |
| Recovery | Restart, drain, publish trong SLO | Với fault window định nghĩa |

**Mọi ngưỡng trên chỉ là ví dụ**. Chọn theo dữ liệu và SLAs thật; không dùng một SLA chung cho mọi batch service.

### Phải định nghĩa khoảng đo

Nếu mỗi 5 phút có một retry storm ngắn, mean throughput vẫn có thể cao. Hãy đo **windowed throughput** (ví dụ mỗi 1/5/15 phút), p95/p99, tail partition và tỷ lệ errors, không chỉ grand total toàn 24 giờ.

## 10. Baseline trước soak: đo đúng và có chứng cứ

Thực hiện một test ngắn ổn định trên **cùng phiên bản cấu hình** để chốt:

- Throughput hữu ích và latency distribution.
- CPU utilization theo JVM và toàn cluster.
- Allocation rate, GC time, post-GC heap occupancy.
- Direct/native memory, thread count, file descriptors.
- Connection pool active/idle/pending và wait times.
- DB query plans/latency/locks/WAL/checkpoint.
- Broker send/confirm latency, queue/consumer lag.
- Read/write IOPS, file output size/throughput.
- JobRepository StepExecution create/update/commit latency.
- Business input/output counts và reject/duplicate baseline.

Lưu **run manifest** gồm source commit, Java flags, Docker image digest, config values, test data identity, resource quotas, ngày giờ start/end, telemetry setup và dashboard links.

### Vì sao cần baseline cùng môi trường?

Soak chạy bản code mới trên DB nóng có metadata 6 tháng không thể so trực tiếp với baseline cũ trên DB sạch nếu không kiểm soát khác biệt. Cần **A/B hoặc trước–sau cùng profile**, lặp lại khi noise môi trường lớn.

## 11. Warm-up: JIT, caches và connection pool

Warm-up làm các yếu tố sau thay đổi:

- JVM JIT compilation và class loading.
- Entity/SQL/prepared statement/DB plan caches.
- HikariCP pool initialization và database connection establishment.
- OS page cache, filesystem caches, broker page cache.
- Spring bean initialization và Job/Step startup.
- Compression/serialization library initialization.

Nếu đo memory slope từ phút 0, quá trình load classes/caches ban đầu có thể bị hiểu nhầm là leak. Ngược lại, nếu bỏ qua warm-up hoàn toàn, bạn có thể bỏ lỡ **cache không có giới hạn** tăng theo mỗi JobInstance.

### Chọn thời điểm steady-state

Không chọn “phút thứ 30” bằng niềm tin. Hãy xem heap occupancy **sau những GC tương đương**, throughput window, connection count và cache hit rate đã tương đối ổn chưa. Ghi rõ thời điểm bắt đầu đo steady-state.

## 12. Hữu ích nhất: throughput không chỉ là số lần xử lý

Các hệ thống batch có thể báo:

- `readCount` tăng.
- `writeCount` tăng.
- Broker `messages_consumed_total` tăng.
- DB QPS cao.
- Retry attempts cao.

Nhưng **useful throughput** là số **business operations duy nhất đã commit thành công và qua reconciliation** trong đơn vị thời gian, theo contract.

Ví dụ:

~~~text
Raw broker deliveries:  15,000 messages/s
Duplicates/redelivery:  3,000 messages/s
Business records commit: 11,500 records/s
Business validation fail: 500 records/s
Useful throughput:      11,000 records/s
~~~

Không tự suy `useful = writeCount` nếu một item tạo nhiều DB operations, dedup làm no-op hoặc writer có side effects ngoài transaction.

### Công thức có điều kiện

\[
R_{\mathrm{useful}} =
\frac{N_{\mathrm{unique,\ validated\ committed}}}
{\Delta t_{\mathrm{steady}}}
\]

Dữ liệu tử số nên đến từ business ledger/reconciliation hoặc counters được thiết kế duplicate-safe. Nếu không có ledger, hãy ghi rõ **ước lượng** và giới hạn phương pháp.

## 13. Backlog drift là một dấu hiệu soak thất bại

Giả sử producer phát `\lambda = 10.000` events/s, consumer xử lý bền vững `\mu = 9.500` unique events/s.

\[
\Delta Q \approx (10.000 - 9.500)
\times 3.600 = 1.800.000\ \text{events/giờ}
\]

Sau 24 giờ, backlog lý thuyết tăng khoảng **43,2 triệu events**, nếu rates giữ nguyên và không có drops/capacity limits. Một job có thể không crash nhưng pipeline **không sustainable**.

### Ba hình dạng queue

~~~text
A. Plateau:
   backlog tăng trong warm-up rồi ổn định
   → Có thể đạt steady state.

B. Linear upward:
   backlog tăng đều nhiều giờ
   → Arrival > sustainable drain hoặc downstream chậm.

C. Sawtooth:
   backlog tăng trong peak rồi giảm ở off-peak
   → Cần xét complete cycle và peak storage/SLA.
~~~

Đừng chỉ chụp queue length vào cuối bài soak, vì nếu cuối giờ là off-peak, có thể đã che mất peak-age vi phạm SLA. Theo dõi **oldest message age**, queue depth theo thời gian, retry/DLQ và delay của business output.

**Một bài soak “không lỗi nhưng backlog tăng mãi” thường không đạt SLO vận hành**, trừ khi đây là thiết kế batch window có backlog được lập kế hoạch và drain đúng hạn.

## 14. Heap leak: nhìn đường đáy sau GC, không chỉ peak

Trong một JVM khỏe mạnh, heap used có thể dao động dạng răng cưa khi objects được cấp phát rồi GC. Heap tăng trước một GC **không tự chứng minh memory leak**.

~~~text
Heap used (minh họa)

Bình thường:      /|    /|    /|    /|
                 / |   / |   / |   / |
                /  |__/  |__/  |__/  |__

Nghi leak:       /|      /|       /|
                / |     / |      / |
               /  |____/  |_____/  |____
                 đáy tăng dần sau GC tương đương
~~~

### Cần đo gì?

- `jvm.memory.used` và `jvm.memory.committed` theo memory pool.
- Heap occupancy **sau những GC tương đương** trong nhiều thời điểm.
- `jvm.gc.pause` count/total/latency distribution nếu instrument đúng.
- Allocation rate và old-generation/live-set approximation.
- Container RSS/working set, limit và OOMKill count.
- Heap histogram/dump theo quy trình có quyền và an toàn dữ liệu.

Không ép `System.gc()` giữa benchmark rồi coi như môi trường thực. Heap dump có thể STW, lớn và chứa PII; phải có ngân sách disk và kiểm soát truy cập.

### Cache tăng có phải leak?

Cache nạp hot keys rồi đạt plateau không hẳn leak. Nhưng cache tăng theo unique keys không có giới hạn vẫn khiến OOM nếu không có max size, TTL và eviction policy. Soak phải xác minh **khả năng bounded** sau nhiều business periods, không chỉ tìm unreachable references.

## 15. Định lượng xu hướng memory leak

Một cách ước lượng là lấy các điểm **post-GC comparable** hoặc windowed lows trong steady state:

\[
s=\frac{H_2-H_1}{t_2-t_1}
\]

`H` là bytes giữ lại sau GC, `t` là thời gian. Đơn vị `s` thường MiB/giờ.

Ví dụ:

~~~text
T =  2 giờ: post-GC live heap ≈ 1.8 GiB
T =  8 giờ: post-GC live heap ≈ 2.1 GiB
T = 14 giờ: post-GC live heap ≈ 2.4 GiB

Slope ≈ 0.05 GiB/h = 51.2 MiB/h
~~~

Nếu headroom còn 1,5 GiB, ngoại suy thô:

\[
T_{\mathrm{headroom}}\approx
\frac{1.5\ \mathrm{GiB}}
{0.05\ \mathrm{GiB/hour}}=30\ \mathrm{hours}
\]

Đây là **ước tính minh họa, không phải dự báo chắc chắn**. GC algorithm, traffic mix, caches, batch cycle và native memory có thể làm slope thay đổi; kiểm tra nhiều windows và confidence/noise.

### So sánh đúng

- Dùng cùng workload mix/worker count giữa các cửa sổ.
- Không so heap trước GC với heap sau GC.
- Nếu có periodic cleanup mỗi 6 giờ, chạy qua đủ chu kỳ.
- Container có thể OOM trước Java heap max nếu không còn native headroom.

## 16. Non-heap, direct memory, metaspace và RSS

Soak có thể fail dù biểu đồ heap ổn định. Nguồn native/non-heap:

- Metaspace, dynamic class loading và proxies.
- Thread stacks khi thread count tăng.
- Direct `ByteBuffer`, Netty/network buffers.
- JNI, native compression/TLS và memory allocator.
- Mapped files, native cache và JIT code cache.
- OS/container accounting khác với Java heap.

| Resource | Nguồn quan sát |
| --- | --- |
| Heap | MemoryPool MXBeans, Micrometer JVM meters |
| Metaspace | JVM nonheap pools/class loading |
| Direct buffers | `BufferPoolMXBean`/library metrics |
| Native RSS | Process RSS/cgroup metrics |
| Thread stacks | Live/peak thread count |
| Container memory | Working set, memory limit, OOM events |
| GC | Pause, CPU overhead, allocation |

**`-Xmx=4GiB` trong container memory limit 4GiB có thể thiếu** chỗ cho native memory. Phải budget overhead, không kết luận “JVM leak” chỉ vì OOMKill trong khi heap used thấp.

Nếu nghi native leak, dùng `jcmd VM.native_memory` khi Native Memory Tracking đã bật, process-level RSS và profiler phù hợp; công cụ profiler có overhead cần được ghi nhận trong báo cáo soak.

## 17. GC và tail latency tăng dần

GC tạo áp lực:

- Allocation rate cao khiến GC liên tục.
- Live set lớn làm hoạt động GC nặng hơn.
- Old-gen pressure hoặc concurrent GC CPU tăng.
- Worker pause gây DB transaction latency, broker ack timeout hoặc queue backlog.
- Mean throughput vẫn ổn trong khi p99 chunk latency vi phạm SLO.

Ví dụ giả định:

~~~text
Giờ 1:  p99 chunk 1.5 s, GC overhead  2%
Giờ 8:  p99 chunk 2.0 s, GC overhead  4%
Giờ 16: p99 chunk 4.5 s, GC overhead 12%
Giờ 24: p99 chunk 9.0 s, GC overhead 21%
~~~

Đừng khẳng định GC là root cause chỉ vì hai đồ thị tăng cùng lúc; DB/IO latency tăng cũng có thể làm objects sống lâu và heap căng.

Chẩn đoán:

1. So chunk p99 với GC pause, DB query/commit latency, broker ACK và CPU throttling cùng timeline.
2. Xem allocation hotspots/caches.
3. So post-GC heap và native RSS.
4. Kiểm tra chunk size, reader/writer buffering và retry.
5. Thực hiện controlled A/B, chỉ đổi một trục cấu hình mỗi lần.

Tăng `-Xmx` đơn thuần không giải quyết leak tiếp tục tăng theo thời gian.

## 18. Thread leak và executor queues qua nhiều JobInstances

Nguồn threads: `ThreadPoolTaskExecutor`, partition manager/worker, broker listeners, JDBC pool, scheduler, HTTP clients, async callbacks và exporters.

Nếu mỗi JobInstance tạo một executor mới không đóng, soak chạy 500 JobInstances có thể phát hiện thread leak mà long-running Step đơn lẻ bỏ qua.

Theo dõi:

- Live threads, peak threads và states WAITING/BLOCKED/RUNNABLE.
- Executor `activeCount`, `poolSize`, `queueSize`, rejected tasks.
- Time-in-queue và thread dump có kiểm soát.
- Number of open thread locals/MDC cleanup theo lifecycle.
- Loại thread còn sống sau các JobInstances đã COMPLETED.

### Unbounded queue che overload

Một executor có 8 worker threads và queue không giới hạn dễ làm CPU nhìn ổn trong khi pending work tăng liên tục rồi heap cạn. Cần bounded queue/admission và theo dõi **queue age**, không chỉ active thread count.

Tăng max threads khi DB connection pool đã bão hòa có thể chỉ làm nhiều thread cùng **chờ connection** hơn.

## 19. JDBC connection pool: active, idle, pending và timeouts

Một leak chậm có thể chỉ lộ khi sau nhiều giờ pool hết chỗ.

| Metric gợi ý | Ý nghĩa |
| --- | --- |
| `hikaricp.connections.active` | Connections đang được mượn |
| `hikaricp.connections.idle` | Connections nhàn rỗi |
| `hikaricp.connections.pending` | Threads chờ borrow |
| `hikaricp.connections.timeout` | Connection acquisition timeouts |
| `hikaricp.connections.acquire` | Thời gian chờ lấy connection |
| `hikaricp.connections.usage` | Thời gian giữ connection |
| `hikaricp.connections.creation` | Latency tạo connection |

Tên metric/availability tùy HikariCP, Micrometer và exporter version; phải kiểm tra endpoint thực.

~~~text
00:00 active=4,  idle=12, pending=0
04:00 active=7,  idle=9,  pending=0
12:00 active=13, idle=3,  pending=1
18:00 active=16, idle=0,  pending=20
19:00 connection acquisition timeout tăng
~~~

`active` tăng có thể do **query chậm giữ connection lâu**, không phải code quên close. So `usage` duration, DB wait events, transaction age và query plans để tách leak khỏi saturation.

Nếu 12 worker JVM, mỗi pool max 20, trần riêng workers đã là **240 connections**, chưa tính manager/JobRepository/publisher/monitoring. Soak phải đo **tổng cluster**, không chỉ một worker “healthy”.

## 20. PostgreSQL: long transactions, locks, WAL và autovacuum

Database là bottleneck tích lũy rất phổ biến:

- Long-running transactions giữ MVCC snapshots, ngăn cleanup.
- Dead tuples/index bloat tăng sau hàng triệu UPDATE.
- WAL growth vượt khả năng archive/replica drain.
- Autovacuum không theo kịp.
- Checkpoints/IOPS pressure làm commit latency tăng.
- Hot-row locks tăng khi nhiều partitions cùng cập nhật.
- Pool saturation kéo theo retry storm.
- JobRepository metadata writes tranh DB I/O.

### SQL read-only kiểm tra transaction ages

~~~sql
SELECT
    state,
    wait_event_type,
    wait_event,
    COUNT(*) AS sessions,
    MAX(now() - xact_start) AS oldest_transaction_age
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY state, wait_event_type, wait_event
ORDER BY sessions DESC;
~~~

`xact_start` có thể NULL; query là snapshot, cần lấy thành time series. Với quyền DB phù hợp, kiểm tra `pg_stat_database`, locks, WAL/archive/replication lag, query latency và autovacuum.

### SQL xem thống kê dead tuples

~~~sql
SELECT
    relname,
    n_live_tup,
    n_dead_tup,
    last_autovacuum,
    autovacuum_count
FROM pg_stat_user_tables
WHERE relname IN (
    'orders', 'outbox_event',
    'batch_job_execution', 'batch_step_execution'
)
ORDER BY n_dead_tup DESC;
~~~

Tên tables chỉ minh họa, có thể không đúng schema/prefix. `n_dead_tup` là **ước lượng thống kê**, không phải số đếm chính xác. Không chạy VACUUM FULL hoặc thao tác nguy hiểm trên production chỉ từ một đồ thị; cần DBA đánh giá.

## 21. Chunk size và transaction boundaries trong soak

Chunk size tác động đồng thời lên overhead commit, ItemStream checkpoint, DB lock hold time, số items buffering, chi phí rollback/retry, latency và khả năng graceful stop.

~~~mermaid
flowchart LR
    R["Read N items"] --> P["Process N"]
    P --> W["Write N"]
    W --> C["Chunk transaction COMMIT"]
    C --> S["Checkpoint + next chunk"]
~~~

Sơ đồ là mô hình logic; commit metadata/business DB và writer buffering phụ thuộc JobRepository/transaction manager cùng cấu hình.

| Chunk size | Worker threads | Giả thuyết cần kiểm chứng |
| ---: | ---: | --- |
| 100 | 4 | Commit overhead có lớn? |
| 500 | 8 | Cân bằng throughput/heap? |
| 1.000 | 8 | Retry và pool wait phù hợp? |
| 2.000 | 16 | DB lock/p99 commit tăng? |
| 5.000 | 16 | Buffer/rollback cost quá lớn? |

Giá trị chỉ **minh họa**, không phải khuyến nghị chung. Với soak dài giờ, chunk lớn và UPDATE liên tục có thể trùng chu kỳ autovacuum/checkpoint của DB, làm latency drift khác benchmark 15 phút.

Không thay đồng thời chunk size, thread count, pool size và broker prefetch rồi kết luận nguyên nhân từ một số throughput.

## 22. JobRepository metadata growth qua hàng nghìn executions

Spring Batch lưu JobInstances, JobExecutions, StepExecutions và ExecutionContexts để quản lý restart/checkpoint. Với nhiều JobInstances nối tiếp:

- Partitioning tạo hàng chục/hàng trăm StepExecutions mỗi job.
- Large ExecutionContexts bị serialize/update thường xuyên.
- Queries liệt kê history và tạo executions chậm dần.
- Table/index bloat và WAL usage tăng.
- Metadata DB pool cạnh tranh với business DB.
- Retention chưa chốt có thể khiến disk đầy.

Nếu một ngày chạy 200 job instances, mỗi job có 40 worker partitions:

\[
200\times40=8.000\ \mathrm{StepExecutions/ngày}
\]

Chưa gồm manager steps, restarts và những lần tạo StepExecution bổ sung.

### Cần quan sát

- BATCH tables/index sizes trước/sau, growth per JobInstance.
- Checkpoint/metadata write p95/p99.
- Query latency khi JobRepository có lịch sử lớn.
- Restart từ snapshot/chunk checkpoint khi DB đã chứa nhiều metadata.
- Cleanup không xóa state còn phục vụ restart/audit.
- Number/size của serialized ExecutionContext entries.

**Không lưu hàng triệu business IDs trong ExecutionContext.** Nếu có state lớn, cân nhắc pointer tới immutable manifest/partition metadata và business ledger theo contract; đừng xóa BATCH metadata thô để tạo biểu đồ đẹp.

## 23. Remote partitioning: tail partition chi phối toàn job

Nếu 24 partitions được dispatch nhưng một partition có hot keys:

~~~text
P00–P20: 24–31 phút
P21    : 45 phút
P22    : 70 phút
P23    : 245 phút
~~~

Job hoàn thành theo **tail partition**, không theo median. Khi soak nhiều cycles, stragglers có thể chồng lên kỳ sau, giữ executor slots, DB locks hoặc correlation state.

Đo:

- Duration p50/p95/p99/max theo logical partition.
- Outstanding partitions và oldest in-progress age.
- Queue wait trước worker start.
- Per-partition read/write/retry/rollback counts.
- Hot-key range, SQL waits, transaction duration.
- Manager wait time sau worker cuối.

PartitionNames phải ổn định qua restart, không dùng hostname làm logical identity. Khi manager timeout, worker cũ vẫn có thể đang commit; không tự dispatch lại cùng partition khi ownership chưa rõ.

**Soak đúng phải kiểm tra source range và business correctness sau restart**, không chỉ tổng số StepExecutions COMPLETED.

## 24. Remote chunking: queue age, reply retention và prefetch

Remote chunking gửi chunk requests từ manager qua broker tới workers, sau đó nhận replies. Qua nhiều giờ có thể xảy ra:

- Manager gửi nhanh hơn workers commit, request backlog tăng.
- Prefetch lớn giữ nhiều chunks trong heap worker.
- Reply aggregator giữ state mãi nếu reply không về.
- Broker redelivery tăng vì timeout/GC pause.
- DLQ/retry queues không có retention/alert đúng.
- ACK trước DB commit làm mất effect, ACK sau commit có cửa sổ duplicate.
- Excessive correlation headers tăng message memory overhead.

Metrics gợi ý:

~~~text
manager.chunk_sent_rate
worker.unique_chunk_committed_rate
broker.request_depth
broker.request_oldest_age
broker.reply_depth
manager.outstanding_chunk_requests
worker.redelivery_count
worker.db_commit_latency
~~~

Các tên **không phải built-in**. Số chunk requests không bằng số business records; một chunk có thể chứa nhiều items.

Không tăng prefetch vô hạn để che broker queue vì backlog có thể chỉ chuyển từ broker sang JVM heap rồi gây OOM. Kiểm tra **total inflight chunks và memory per chunk**.

## 25. Retry, skip và duplicate accounting xuyên restart

Một pipeline one-to-one có thể có bốn nhóm rời nhau:

\[
N_\mathrm{input}
=N_\mathrm{accepted}
+N_\mathrm{filtered}
+N_\mathrm{rejected}
+N_\mathrm{duplicatesSuppressed}
\]

Và nếu mỗi accepted unique input tạo một output:

\[
N_\mathrm{outputExpected}=N_\mathrm{accepted}
\]

Các nhóm phải không giao nhau và bao phủ input; với one-to-many hoặc aggregation cần bất biến khác.

### Vì sao StepExecution counters chưa đủ?

Item có thể được read/process/write lại khi rollback, restart hoặc redelivery. `readCount` và `writeCount` của các executions không mặc nhiên là **số unique business effects**. Đo stable business IDs/source versions, full output diff và idempotent ledger.

Soak cần:

- Attempts/s, retries/s và unique committed records/s.
- Skip/reject/duplicate suppression theo phase.
- DLQ age/count và poison events.
- Missing/extra/mismatched business keys = 0 nếu contract bắt buộc.
- Kiểm tra không nhân đôi external API/event/file effects sau restart.
- Không bỏ data silently để đạt throughput mục tiêu.

## 26. File/object storage và temp disk fill-up

File workers sử dụng descriptors, buffers, compression state, temp files, multipart uploads, staging attempts, manifests và IOPS. Soak có thể hết disk vì logs, temp spill, failed attempts hoặc object requests bị throttled dù heap/CPU còn khỏe.

| Resource | Chỉ số theo dõi |
| --- | --- |
| Free disk/inodes | Còn chỗ cho temp/retry? |
| Open file descriptors | Có file/socket leak? |
| Temp directory bytes | External sort/merge spill tăng? |
| Orphan staging attempts | Cleanup có bỏ sót? |
| Object store latency/errors | Upload requests có bị throttle? |
| Output validated/published | Có partial dataset bị lộ? |
| Merge backlog/age | Publication trễ vì merge? |

**Không xóa staging theo tuổi mù quáng**: JobInstance có thể đang cần file để restart/đối soát, audit có thể giữ failed attempts. Cleanup phải dựa vào run state + retention policy.

## 27. Backlog trong heap khác memory reference leak

Nếu `arrival rate > processing rate`, objects ở executor/consumer queue sống lâu hơn và heap tăng theo backlog dù code không tạo reference leak.

Chẩn đoán:

1. So queue depth/age và post-GC heap trên cùng timeline.
2. Trong môi trường test, giảm/pause producer có kiểm soát.
3. Chờ queue drain; quan sát live heap có trở về plateau không.
4. Nếu queue rỗng nhưng heap tiếp tục tăng qua nhiều JobInstances, điều tra caches/ThreadLocal/listeners.
5. Dùng heap histogram/profiler được phê duyệt để tìm retention roots.
6. Không giảm queue bằng cách drop messages âm thầm rồi tuyên bố PASS.

Các nguyên nhân tích lũy phổ biến: `Future` callbacks giữ payload, reply correlation groups không expire, listener maps không cleanup, `ThreadLocal` chưa remove, ResultSet/HTTP response/file stream chưa close, exceptions chứa payload lớn hoặc retry queue vô hạn.

**Một phép thử “không còn queue” chỉ thành công nếu business counts và DLQ contract vẫn đúng**, không phải vì đã vứt bỏ work.

## 28. Micrometer/Actuator: thu thập dữ liệu đúng phạm vi

Spring Boot Actuator và Micrometer có thể cung cấp JVM memory/GC, process/system metrics, HikariCP, application metrics; Spring Batch có observations/metrics tùy version và integration.

Ví dụ cấu hình Spring Boot properties:

~~~properties
management.endpoints.web.exposure.include=health,info,metrics,prometheus
management.metrics.tags.application=spring-batch-soak
management.tracing.sampling.probability=0.1
~~~

Đây chỉ là **minh họa, chưa có security configuration**:

- Endpoint Prometheus cần registry phù hợp; không mở Actuator public.
- Sampling 0.1 là giả định, không phải mặc định an toàn/tối ưu.
- Đo overhead của logs/tracing/profiling và lưu telemetry configuration trong test manifest.
- Kiểm tra actual metric names/tag formats từ endpoint thay vì suy đoán theo ví dụ.
- Không đưa dynamic business IDs, `jobExecutionId` hay mọi `partitionName` vào metric labels high-cardinality.

**JVM metrics không chứng minh business correctness**. Cần metrics `unique_committed` cùng business ledger và output reconciliation.

## 29. Java: đo thời gian callback chunk bằng Micrometer

Ví dụ Java 17, Spring Batch 5.x; dùng `ThreadLocal` để không ghi đè thời điểm bắt đầu khi nhiều chunk threads chạy song song.

~~~java
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import org.springframework.batch.core.ChunkListener;
import org.springframework.batch.core.scope.context.ChunkContext;

public final class ChunkDurationMetrics
        implements ChunkListener {

    private final ThreadLocal<Long> startNanos =
            new ThreadLocal<>();

    private final Timer successTimer;
    private final Timer errorTimer;

    public ChunkDurationMetrics(MeterRegistry registry) {
        successTimer = Timer.builder("batch.chunk.duration")
                .tag("outcome", "success")
                .register(registry);
        errorTimer = Timer.builder("batch.chunk.duration")
                .tag("outcome", "error")
                .register(registry);
    }

    @Override
    public void beforeChunk(ChunkContext context) {
        startNanos.set(System.nanoTime());
    }

    @Override
    public void afterChunk(ChunkContext context) {
        recordAndClear(successTimer);
    }

    @Override
    public void afterChunkError(ChunkContext context) {
        recordAndClear(errorTimer);
    }

    private void recordAndClear(Timer timer) {
        Long start = startNanos.get();
        startNanos.remove();

        if (start != null) {
            long elapsed = System.nanoTime() - start;
            if (elapsed >= 0) {
                timer.record(elapsed, TimeUnit.NANOSECONDS);
            }
        }
    }
}
~~~

### Giới hạn của ví dụ

- Listener đo callback elapsed time, không tách cụ thể reader/processor/writer, queue wait, broker ACK.
- Process bị SIGKILL/OOMKill có thể không chạy callback lỗi; Timer không thể là business completion ledger.
- `ThreadLocal.remove()` giúp ngăn giữ reference trên executor threads được reuse.
- Khi Step bị stop, cần xác minh callback behavior trong integration test tương thích version.
- `System.nanoTime()` dùng đo duration, không thay `Instant` timestamp của audit event.
- Nếu framework đã expose meter tương tự, tránh đặt tên trùng/double counting.
- Metric tags ví dụ chỉ `outcome` low-cardinality; không gắn `businessKey` hoặc `JobExecutionId` mỗi lần.

## 30. Histogram và p99: không trung bình hóa percentiles

Mean chunk latency có thể tốt trong khi một số chunks bị DB lock 20 giây. Nên có p95/p99 từ histogram với buckets phù hợp.

- Histogram buckets xác định độ chính xác của estimated p99.
- Không lấy trung bình p99 của từng worker làm p99 toàn cluster.
- Tổng hợp histogram bucket counters đúng rồi mới tính quantile.
- Với ít mẫu trong một window, p99 không ổn định; phải kèm sample count.
- So run A/B bằng cùng latency buckets, sampling và workload profile.

PromQL minh họa nếu exporter thật có histogram metric tương ứng:

~~~promql
histogram_quantile(
  0.99,
  sum by (le) (
    rate(batch_chunk_duration_seconds_bucket[5m])
  )
)
~~~

`Timer` Micrometer cần distribution histogram configuration phù hợp mới có bucket series để query. **Tên metric này chỉ minh họa**, kiểm tra trực tiếp registry output thực tế.

## 31. Báo cáo soak phải có time series đồng bộ

Một dashboard cần:

- Useful throughput theo 1/5/15-minute windows.
- p50/p95/p99 chunk/step/partition durations.
- Post-GC heap, allocation rate, GC pauses và CPU overhead.
- Container RSS, memory limit, OOM/restarts, CPU throttling.
- Thread count, executor queue depth/age, rejected tasks.
- HikariCP active/pending/timeout/connection usage.
- DB transaction age, lock waits, query/commit latency, WAL và autovacuum.
- JobRepository metadata size và checkpoint/write latency.
- Broker request/reply queue age/depth, redelivery, DLQ.
- File descriptor count, staging/temp disk, object-store latency.
- Business reconciliation counts và publication state.
- Timeline markers cho autoscaling, deploy, backup và fault injections.

**Cùng timeline giúp tìm causal chain.** Ví dụ DB locks tăng 10:00, chunk p99 tăng 10:05, broker queue tăng 10:10 và heap tăng 10:20. Chỉ nhìn heap 10:20 có thể kết luận nhầm memory leak.

## 32. Load generator và instrumentation cũng tiêu tài nguyên

Generator chạy chung node worker có thể giành CPU/network và tạo bottleneck giả. Logs từng item, tracing 100% và profiler liên tục có thể làm hệ thống chậm hơn production.

Các biện pháp:

1. Tách generator khỏi worker nếu kiến trúc production tách.
2. Đo target arrival rate vs actual delivered rate.
3. Đo CPU/network/disk và lỗi của generator riêng.
4. Benchmark overhead của tracing/logs/profiling.
5. Dùng sampling low-overhead và low-cardinality labels.
6. Không log payload/PII từng record.
7. Profiling nặng chỉ bật ở windows có kế hoạch và quyền.
8. Lưu gaps/failed scrapes của metrics backend, không coi missing metrics là zero.

**Nếu generator phát được 7.000/s dù mục tiêu 10.000/s, kết quả PASS ở 7.000/s không chứng minh hệ thống xử lý nổi 10.000/s.**

## 33. Clean soak và recovery soak nên báo cáo riêng

**Clean soak:** workload đại diện, không cố ý làm chết dependency; tập trung phát hiện slow leak, backlog, GC/DB drift và throughput degradation.

**Recovery soak:** inject có kiểm soát (kill worker, broker disconnect, DB outage, pod restart) và kiểm tra MTTR, queue drain, checkpoint, duplicate prevention và state cleanup.

Ví dụ lịch:

~~~text
H+00:00   Warm-up begins
H+00:45   Enter steady state
H+08:00   Kill one worker JVM
H+08:10   Restore capacity
H+14:00   Broker unavailable 3 minutes
H+14:03   Broker reconnects
H+18:00   Add DB acquisition delay 60 seconds
H+18:01   Restore DB
H+22:00   Restart manager with ownership check
H+24:00   Stop arrivals, drain queues, reconcile
~~~

Đây là **kịch bản phòng thử nghiệm**, không áp dụng trực tiếp vào production.

Khi có fault windows, không chấm cùng ngưỡng steady throughput cho chính thời điểm dependency down; cần **recovery acceptance riêng**. Sau broker recovery, backlog phải drain theo deadline, resources về plateau và data reconciliation PASS.

## 34. Restart sau nhiều giờ: checkpoint và business idempotency

Một worker có thể chết **sau DB business commit nhưng trước khi JobRepository checkpoint được cập nhật**, nếu các resources không nằm trong cùng transaction atomic:

~~~text
Chunk C100 đã COMMIT business state
Worker JVM chết trước metadata checkpoint
Restart cùng JobInstance đọc lại C100
Writer có thể được gọi lại
~~~

Đối soát sau restart cần chứng minh:

- `JobInstance` và identifying JobParameters không bị đổi.
- Input source snapshot/version và partition ranges giữ nguyên.
- `ExecutionContext`/`ItemStream` checkpoint khôi phục đúng.
- Business event ID ổn định, unique constraint/version guard hoặc ledger ngăn duplicate.
- Remote worker cũ không còn xử lý cùng partition khi worker mới bắt đầu.
- File writer không append partial attempt vào final file.
- Outbox/consumer inbox bảo vệ các message redeliver.
- Không silent skip business records khi retry budget exhausted.

**JobExecution COMPLETED sau restart chưa chứng minh không missing/duplicate.** Phải kiểm tra business ledger, source inventory, output manifest và external effects.

## 35. Ma trận fault injection dài giờ

| Fault | Kỳ vọng framework/resource | Bằng chứng data correctness |
| --- | --- | --- |
| Kill worker trước chunk commit | Rollback/retry theo policy | Không mất/nhân business effect |
| Kill worker sau business commit | Metadata có thể stale | Replay idempotent |
| Manager timeout trước worker reply | Worker có thể còn chạy | Không dispatch trùng owner |
| Broker publish ACK unknown | Có thể redelivery | Consumer dedup |
| Broker down ngắn | Backlog tăng theo policy | Drain trong SLO |
| DB pool exhausted | Bounded backpressure | Không retry storm/silent skips |
| WAL/archive lag | Disk/replica lag tăng | Alert và resource policy |
| Object upload timeout | Partial staging object | Manifest gate chặn publish |
| JobRepository outage | Checkpoint/metadata fail | Reconcile DB vs metadata |
| Worker OOMKill | Pod/JVM restarted | State cleanup và idempotency |
| Pause producer | Queue drain | Post-GC heap về plateau |
| GC pause dài | Chunk p99/timeout tăng | Redelivery xử lý đúng |
| API downstream chậm | Pending work tăng có budget | Không unbounded queue |
| Cleanup chạy đồng thời | Old attempts được xử lý theo policy | Không xóa restart evidence |

**Không coi recovery PASS chỉ vì pods lại READY**. Kết quả phải bao gồm JobRepository, business effects, backlog drained và output publication/side effects đúng.

### Fault injection phải có điểm dừng rõ

Mỗi fault nên có `injectedAt`, `recoveredAt`, `expectedImpact`, `maxDrainTime` và `reconciliationScope`. Nếu fault làm mất khả năng quan sát, nên fail test và giữ artifacts để điều tra, không ghi success ước đoán.

## 36. Tính thời gian xả backlog sau outage

Giả sử broker phục hồi với backlog `B_0=3.600.000` events. Producer tiếp tục phát `\lambda=8.000` events/s, workers xử lý hữu ích `\mu=12.000` events/s.

\[
R_\mathrm{drain}=\mu-\lambda=4.000\ \mathrm{events/s}
\]

\[
T_\mathrm{drain}\approx\frac{B_0}{\mu-\lambda}
=\frac{3.600.000}{4.000}=900\ \mathrm{s}
=15\ \mathrm{phút}
\]

Đây là **ước lượng khi rates ổn định**, không có poison messages và capacity không suy giảm theo backlog. Nếu `\mu\leq\lambda` thì backlog không thể drain dưới rates đó; phải tăng sustainable throughput hoặc giảm arrival.

### Đo thực tế

Đo oldest message age, queue depth, unique committed/s và DLQ. Khi backlog lớn, DB hot rows hoặc container memory/GC có thể làm `\mu` giảm, khiến thời gian thực vượt dự báo.

Một soak hồi phục thành công cần **đạt ngưỡng drain time và business integrity**, không chỉ xử lý được vài triệu deliveries.

## 37. Chạy chuỗi nhiều JobInstances để tìm lifecycle leak

Một JobInstance 24 giờ có thể không phát hiện lỗi mỗi job tạo một executor/client/cache mới không đóng. Với công việc sản xuất chạy 30 phút mỗi giờ, nên mô phỏng chuỗi D1..D500:

~~~text
Cycle 001: launch D001 -> complete -> validate
Cycle 002: launch D002 -> complete -> validate
...
Cycle 500: launch D500 -> complete -> validate
~~~

Sau mỗi cycle, lấy metrics ở **điểm đồng dạng** (ví dụ sau khi Step close, checkpoint completed và cleanup đã chạy):

- Heap post-GC và native RSS.
- Thread/FD count.
- DB pool active/idle/pending.
- Broker consumers/producers, open channels.
- Temp disk/staging artifacts.
- JobRepository table/index size và query latency.
- Number of unique Micrometer time series.

Nếu thread count tăng 2 sau mỗi job, 500 cycles làm tăng khoảng 1.000 threads; dù mỗi JobExecution COMPLETED, system **không sustainable**.

### Tránh leak do telemetry

Nếu tạo meter tag `jobExecutionId` cho mỗi job, cardinality tăng theo 500 cycles. Đây là leak trong **observability design**, không nhất thiết do business code; phải giám sát cả metrics registry/exporter memory.

## 38. Stop/restart lặp lại: kiểm thử state cleanup

Một số lỗi chỉ xảy ra khi lifecycle bị ngắt:

- Worker stop/restart nhiều lần.
- Broker consumer reconnect/rebalance.
- ItemStream reader/writer open/close lại.
- Partition manager timeout và remote workers đổi owner.
- Scheduler job rollover khi kỳ trước chưa xong.
- JDBC connection invalidation/refresh.
- Cleanup task và checkpoint race.

Ví dụ kịch bản:

~~~text
Run D1: COMPLETE
Run D2: FAIL checkpoint K -> RESTART -> COMPLETE
Run D3: STOPPED checkpoint K2 -> RESTART -> COMPLETE
Run D4: broker reconnect + worker replacement -> COMPLETE
Run D5: overlapping period policy tested -> COMPLETE
~~~

Theo dõi old/new JobExecution IDs, cùng JobInstance identity, source snapshot và business key/version diff. **Không thêm identifying run.id ngẫu nhiên** để ép launch; đó là new JobInstance, không kiểm thử checkpoint recovery.

### Nhận biết residual state

Nếu sau mỗi restart số active threads/consumer subscriptions tăng thêm nhưng không giảm sau idle, có thể có leftover listeners/tasks. Soak phải có baseline **sau cleanup**, không chỉ resource peak trong RUNNING.

## 39. Autoscaling và thay đổi worker count giữa soak

Production có thể autoscale worker JVM/pods khi queue depth cao. Soak nên kiểm tra:

- Scale-out không vượt DB max_connections/broker quotas.
- Scale-in không kill worker giữa business commit và checkpoint mà không recovery.
- Partition ownership không bị cấp cho hai JVM cùng lúc.
- Inflight chunks/requests được drain hoặc redeliver duplicate-safe.
- Người quản lý job/reply aggregator không mất state khi worker count đổi.
- CPU throttling không tăng khiến p99 latency xấu đi.
- Batch metadata từ terminated workers được reconcile đúng.

### Scale-out không luôn tăng throughput

Nếu broker/DB IOPS đã đạt trần, thêm 20 workers sẽ làm queue pending ở connection pool thay vì xử lý nhiều unique events hơn. Đo throughput trước/sau scale cùng số **source input records**, không chỉ so CPU average.

### Test scale-in có backpressure

Khi hạ replicas, `\mu` giảm. Nếu open workload vẫn phát `\lambda` như cũ, `Q` có thể tăng. Đo thời gian tăng backlog và policy admission của manager, không chờ tới OOM rồi mới phát hiện.

## 40. Phân tích drift bằng windows thay vì cả run

Giả sử một run 24 giờ chia 24 windows, mỗi window một giờ. So sánh:

- Mean/median throughput của giờ 2–4 (sau warm-up).
- Mean/median throughput của giờ 20–22 (trước fault/final drain).
- p99 latency, queue age, post-GC heap và connection usage trong cùng windows.
- Độ dốc tăng/giảm và sự ổn định sau khi loại nhiễu có lý do.

Một phép tính đơn giản:

\[
\mathrm{throughputDriftPct}
=100\times
\frac{R_\mathrm{late}-R_\mathrm{early}}
{R_\mathrm{early}}
\]

Nếu `R_early=10.000/s`, `R_late=8.800/s`:

\[
\mathrm{drift}=-12\%
\]

Ngưỡng FAIL ví dụ `-10%` sẽ bị vi phạm, nếu workload/availability tương đương và metric sampling đáng tin.

### Không cherry-pick windows

Chọn early/late periods **trước test** hoặc có selection algorithm cố định. Nếu tự chọn hai giờ đẹp nhất, kết quả không đáng tin. Fault/recovery windows nên báo riêng nhưng vẫn ghi đầy đủ trong timeline.

### Confidence và chạy lặp

Run-to-run noise đến từ scheduler, CPU overcommit, DB background jobs, cloud noisy neighbors và cache state. Một regression đáng tin nên có các reruns/A-B có kiểm soát khi khác biệt gần ngưỡng; không dựa vào một chart duy nhất.

## 41. Quy trình root-cause khi một chỉ số xấu dần

Bảng phân biệt các dấu hiệu:

| Triệu chứng | Giả thuyết đầu tiên | Cách kiểm chứng |
| --- | --- | --- |
| Post-GC heap tăng, queue ổn | Cache/listener/reference retention | Heap histogram/dump, map sizes |
| Heap tăng cùng queue | Producer > consumer / backpressure | Pause producer, queue drain |
| RSS tăng, heap phẳng | Direct/native buffers, thread stacks | NMT/BufferPoolMXBean, threads |
| GC pause tăng, allocation cao | Object churn, chunk buffering | Allocation profiler |
| Hikari active tăng, usage duration tăng | DB queries/transactions chậm | pg_stat_activity, SQL latency |
| Hikari pending tăng mà DB idle | Pool sizing/leak/invalid connections | Borrow timeouts, lease stacks |
| DB locks tăng và p99 chunks tăng | Hot-key contention | Wait events, key/partition mapping |
| WAL/disk tăng không giới hạn | Archival/retention/replica lag | WAL metrics, archives, slots |
| JobRepository latency tăng qua runs | Metadata growth/index bloat | Table size, query plans |
| Broker oldest age tăng | Downstream slower than arrival | Arrival vs useful service rate |
| Reply groups tăng | Missing replies/aggregator retention | Correlation state, timeouts |
| FD count tăng | Streams/sockets not closed | Process FD table, resource lifecycle |
| Throughput giảm sau scale-out | Shared DB/broker contention | Load A/B with capped workers |

**Phương pháp:** xem timeline → xác định chỉ số biến xấu sớm nhất → kiểm tra bằng chứng độc lập → thay một cấu hình/điểm code → chạy lại workload tương đương. Không sửa đồng thời năm tham số rồi gán công lao cho một trong chúng.

## 42. Case study: 72 giờ, 80 triệu records/ngày

Một pipeline đơn hàng dùng Spring Batch để normalize events, ghi PostgreSQL và outbox, gửi tới downstream qua Kafka. Workload minh họa:

~~~text
Worker JVMs           : 8
Threads per JVM       : 12
Chunk size            : 500
DB pool per worker    : 16
Broker partitions     : 24
Source                 : immutable daily snapshots
Daily volume          : 80,000,000 logical records
Test duration         : 72 hours
Expected daily jobs   : 1 per business day
~~~

Để hoàn thành 80 triệu records trong 6 giờ, throughput lý tưởng tối thiểu:

\[
R_\mathrm{required}
=\frac{80.000.000}{6\times3.600}
\approx 3.704\ \mathrm{records/s}
\]

Đây là cận tối thiểu **trước overhead**. Nếu data validation/publish cần thêm thời gian và SLA chỉ tính end-to-end 6 giờ, processing phải nhanh hơn.

### Lần soak thứ nhất: regression có vẻ nhỏ

| Chỉ số | Giờ 2 | Giờ 30 | Giờ 70 |
| --- | ---: | ---: | ---: |
| Useful throughput | 7.900/s | 7.500/s | 6.100/s |
| Post-GC live heap/worker | 1,4 GiB | 1,9 GiB | 2,8 GiB |
| Broker oldest age | 8s | 40s | 370s |
| Hikari pending | 0 | 2 | 19 |
| Chunk p99 | 1,2s | 2,5s | 9,0s |
| Reconciled missing keys | 0 | 0 | 0 |

Các số **giả định**. Hệ thống chưa mất data, nhưng throughput giảm, queue lag tăng, memory/connection pressure xấu dần nên **soak FAIL về sustainability**.

### Phân tích nguyên nhân

Một `StepExecutionListener` giữ cached `JobExecution`/input payload trong singleton map theo run ID mà không dọn khi job kết thúc. Đồng thời DB UPDATE hot rows khiến Hikari usage duration tăng; broker queue tăng vì workers bị block.

Các biểu đồ có thể có nhiều root causes, không chỉ Java leak. Nhóm cần tách:

1. Heap retained objects: listener map size tăng theo số runs.
2. DB lock hotspots: query plan/row keys.
3. Queue age: arrival vs committed processing.
4. Correctness: vẫn PASS nhưng không đủ kết luận performance PASS.

### Lần soak thứ hai sau sửa

Thay map bằng bounded cache/lifecycle cleanup, tối ưu partition affinity cho hot keys và giới hạn queue inflight. Chạy lại **cùng source mix, 72 giờ, cùng worker/DB/broker budget** và so early/late windows. Chỉ PASS nếu cả memory/queue slopes, latency/throughput SLO, resource limits và business reconciliation đạt.

**Bài học case study:** một pipeline có thể xử lý đúng 80 triệu records mỗi ngày nhưng vẫn **không bền** nếu latency, backlog hoặc resource usage tăng không giới hạn. Soak test xác định khi nào scaling thực sự sustainable.

## 43. Runbook khi soak bắt đầu suy giảm

Một runbook ngắn nhưng có thứ tự giúp không làm biến dạng thí nghiệm giữa chừng.

**Bước 1 — Đánh dấu mốc sự cố.** Ghi runId, source snapshot, version/config, tUTC và loại chỉ số vi phạm. Đừng sửa config âm thầm trong run.

**Bước 2 — Phân loại drift.** Throughput giảm, queue tăng, heap tăng, native RSS tăng, Hikari pending, DB locks, broker lag, JobRepository hay file descriptor/temp disk?

**Bước 3 — So timeline.** Tìm tín hiệu xấu xuất hiện đầu tiên; đối chiếu fault events, background DB maintenance, autoscale và source mix.

**Bước 4 — Kiểm tra generator.** Actual arrival rate có giữ đúng target không? Một producer bị throttle có thể khiến mọi chỉ số phía consumer nhìn “ổn”.

**Bước 5 — Xem tài nguyên chung.** Worker CPU/memory, database connection/lock/WAL, broker quotas và storage I/O. Đừng chỉ dựa vào JVM heap.

**Bước 6 — Bảo đảm tính đúng dữ liệu.** Kiểm tra count ledger/accepted/rejected/duplicates, output checksum, JobRepository consistency và DLQ; không xoá backlog để giảm áp lực rồi coi là recovery.

**Bước 7 — Thu evidence đúng mức.** Ghi heap histogram/thread dump/DB query plan theo policy, giới hạn profiling overhead. Giữ timestamp và source identity.

**Bước 8 — Chọn hành động.** Khi cần khẩn cấp, dừng arrival có kiểm soát, rollback/recovery theo runbook; nếu đang làm baseline khoa học, ưu tiên giữ nguyên cấu hình cho tới khi thu đủ evidence và đạt stop criteria.

**Bước 9 — Tạo controlled experiment mới.** Chỉ thay một biến (chunk size, pool/queue cap, cache TTL, partition affinity), cùng workload và telemetry settings để so sánh.

**Bước 10 — Ghi verdict.** PASS/FAIL/INCONCLUSIVE theo ngưỡng đã chốt; report cả giới hạn test environment và các fault windows.

### Stop criteria có chủ đích

Dừng test sớm nếu container OOMKill lặp, disk/WAL gần đầy, ảnh hưởng môi trường dùng chung, dữ liệu an toàn bị đe dọa hoặc resource limits vượt guardrails. **Early abort là FAIL hoặc INCONCLUSIVE tùy nguyên nhân, không tự gọi là PASS vì chưa tới 24 giờ.**

## 44. Báo cáo nghiệm thu soak: bản khai có thể đối chiếu

Một báo cáo không nên chỉ có ảnh dashboard. Nó cần **đủ metadata để tái lập**:

~~~json
{
  "reportSchemaVersion": 1,
  "runId": "orders-soak-2026-11-26-r1",
  "module": "SPRING_BATCH_SCALING_OPERATIONS",
  "testType": "SOAK_WITH_CONTROLLED_FAULTS",
  "targetDurationHours": 72,
  "actualDurationHours": 72,
  "warmupMinutes": 45,
  "workload": {
    "sourceManifestId": "input-v17",
    "dailyLogicalRecords": 80000000,
    "maxArrivalPerSecond": 10000,
    "businessModel": "accepted-dedup-rejected-accounted"
  },
  "topology": {
    "workerJvmCount": 8,
    "threadsPerWorker": 12,
    "chunkSize": 500,
    "jdbcPoolPerWorker": 16
  },
  "observations": {
    "earlyUsefulThroughput": 7900,
    "lateUsefulThroughput": 7800,
    "oldestQueueAgeSecondsMax": 38,
    "unexplainedHeapSlopeMiBPerHour": 0,
    "businessKeyMissing": 0,
    "businessKeyUnexpected": 0,
    "businessValueMismatches": 0
  },
  "recovery": {
    "workerRestartObserved": true,
    "backlogDrainedWithinSlo": true
  },
  "verdict": "PASS",
  "evidence": {
    "dashboardRunRef": "observability-dash-run-r1",
    "jobRepositorySnapshotRef": "jobrepo-evidence-r1",
    "reconciliationReportRef": "reconcile-r1"
  }
}
~~~

Đây là **JSON minh họa**, không phải report của một run thực. Một field `PASS` chỉ hợp lệ khi tất cả acceptance checks được thực hiện; `unexplainedHeapSlope=0` cần measurement method và confidence, không phải đặt mặc định. Nếu clean soak, recovery fields có thể not-applicable thay vì giả định PASS.

### Nên đưa thêm

- Git commit/image digest, JDK, Spring Batch/Boot, GC configuration.
- Database version/isolation/indexes và JobRepository schema.
- Kafka/RabbitMQ topology, broker durability/quotas, consumers.
- Dataset cardinality, skew, record size distribution và rejection profile.
- Full observation time windows và sample counts.
- Errors/ooms/failed checkpoints/cancelled executions.
- Per-step/partition tail durations và delayed publication age.
- Specific fault injection times, observed MTTR, drain trajectories.
- QA/benchmark limitations, approvals và data retention.

**Một report có thông tin để kiểm tra lại** có giá trị hơn một con số throughput cao nhưng không biết nguồn/cấu hình và business effects.

## 45. Tự động hóa gate cho CI, nightly và pre-release

Soak 48–72 giờ có chi phí cao, không phù hợp chạy đầy đủ cho mọi commit. Có thể dùng tầng test:

| Tầng | Khi nào | Tìm gì |
| --- | --- | --- |
| Unit/performance microbench | Mỗi thay đổi quan trọng | Parser, mapper, allocation hotspots |
| Short integration load | CI/chạy định kỳ | Throughput regression, retry/rollback correctness |
| 2–4 hour mini-soak | Nightly hoặc trước merge lớn | Thread/connection/queue leak rõ |
| 8–24 hour soak | Định kỳ/pre-release | Daily cycle, metadata growth |
| 48–72 hour soak | Trước mở rộng lớn hoặc phiên bản quan trọng | Leak chậm, long recovery windows |
| Fault/recovery rehearsal | Định kỳ theo rủi ro | Restart, broker/DB outage, backpressure |

Đây là **mô hình tổ chức**, không phải lịch mặc định. Nếu workload phụ thuộc weekly cleanup/rotation, nên chạy test qua chu kỳ đó hoặc thiết kế phép gia tốc chứng minh được tương đương.

### Gate không nên quá đơn giản

Một tự động gate đáng tin không chỉ xét:

~~~text
exitCode = 0
AND averageThroughput >= target
~~~

Mà nên xét:

~~~text
runDuration >= requiredDuration
AND generatorTargetReached
AND steadyWindowCoverage >= threshold
AND usefulThroughputWithinSlo
AND p99LatencyWithinSlo
AND noUnboundedQueueOrResourceDrift
AND noUnresolvedOOMOrPoolExhaustion
AND recoveryScenariosPass
AND businessReconciliationPass
~~~

Tên trường là pseudo-code acceptance policy của ứng dụng, không phải API Spring Batch.

Nếu telemetry mất 8 giờ hoặc generator không đạt arrival target, kết luận có thể là **INCONCLUSIVE** chứ không phải PASS. Nếu test kết thúc sớm do OOM/disk full, đó là FAIL theo safety guardrail.

## 46. Những ngộ nhận nguy hiểm trong soak test

| Ngộ nhận | Thực tế |
| --- | --- |
| “Job chạy 24 giờ không crash là PASS.” | Có thể backlog, RAM, WAL hoặc p99 latency tăng không giới hạn. |
| “Một JobExecution 24 giờ giống 500 jobs ngắn.” | Không kiểm tra cleanup giữa JobInstances và metadata growth tương đương. |
| “Heap dùng tăng nghĩa chắc chắn memory leak.” | Có thể backlog/cache/warm-up; xét post-GC trend và roots. |
| “Heap ổn nghĩa không OOM.” | Native RSS, direct buffers, threads và cgroup limit vẫn có thể lỗi. |
| “Post-GC slope bằng 0 ở một cửa sổ là an toàn.” | Cần nhiều windows, chu kỳ tải và retention budget. |
| “Tăng worker luôn tăng throughput.” | DB locks/IO/broker quotas có thể là trần. |
| “Queue length thấp nghĩa consumer đủ capacity.” | Closed model có thể tự hạ arrival. |
| “Mean latency đủ để đánh giá.” | Tail p99, oldest age và partition skew có thể vi phạm SLA. |
| “p99 các workers cộng rồi chia là p99 cluster.” | Không phải phép tổng hợp quantile đúng. |
| “Hikari active cao luôn là leak.” | Query chậm và locks giữ connections lâu. |
| “JobRepository metadata không ảnh hưởng throughput.” | Nhiều StepExecutions/checkpoints có chi phí IO/index. |
| “Retry giúp tăng successful throughput.” | Retry attempts không phải unique committed work. |
| “Broker consumed count chính là business count.” | Redelivery/duplicates làm inflated counter. |
| “Tăng prefetch để broker queue rỗng là ổn.” | Backlog có thể chỉ chuyển vào JVM heap. |
| “Số partitions bằng số threads là tối ưu.” | Tail skew, I/O và connection budget quyết định. |
| “File staging có thể xoá ngay khi Step COMPLETED.” | Có thể cần validation/restart/forensics. |
| “Rollback chunk nghĩa external API/file cũng rollback.” | Các side effects ngoài transaction không tự undo. |
| “Job COMPLETED chứng minh không duplicate.” | Cần business ledger/key multiset diff. |
| “Đo ở production DB sẽ đáng tin nhất.” | Fault injection/load có thể gây ảnh hưởng người dùng; phải có môi trường/giới hạn an toàn. |
| “Load generator target 10k/s là actual 10k/s.” | Phải đo actual delivered rate/errors. |
| “Sampled trace có đủ audit mọi action.” | Tracing không thay durable audit/business proof. |
| “Mất metrics một giờ là hệ thống hoạt động tốt.” | Data gap cần coi là unknown/inconclusive. |
| “Sửa một lúc 6 tham số rồi chạy lại là tối ưu hóa.” | Không xác định được root cause. |
| “Một lần chạy tốt đủ chứng minh mọi điều kiện.” | Noise, DST, retention/cleanup và burst cycles có thể chưa được bao phủ. |

## 47. Checklist production-ready cho soak dài giờ

### Kế hoạch và workload

- [ ] Xác định rõ soak một long-running job, nhiều sequential jobs hay overlapping jobs.
- [ ] Chốt immutable input sources/versions và business data contract.
- [ ] Workload phản ánh key cardinality, payload sizes, skew, rejects và duplicates.
- [ ] Mô hình arrival open/closed được công bố.
- [ ] Target arrival đã được generator thực sự đáp ứng và đo.
- [ ] Có baseline cùng version/resource/topology.
- [ ] Warm-up và steady-state windows có tiêu chí định nghĩa trước.
- [ ] Chạy đủ thời gian/cycles để kiểm tra leak/cleanup/TTL nghi ngờ.
- [ ] Có acceptance thresholds cho useful throughput, p99 và queue age.
- [ ] Có stop conditions an toàn cho OOM, disk, DB và shared environments.

### JVM, thread và pool

- [ ] Post-GC live heap có xu hướng/budget rõ.
- [ ] Non-heap, direct buffers, process RSS/container limit được đo.
- [ ] GC overhead và p99 chunk durations được theo dõi đồng thời.
- [ ] Live thread count/FDs plateau sau job cleanup.
- [ ] Executor queues bounded, queue age/rejections có telemetry.
- [ ] Không có ThreadLocal/listener/aggregator state giữ vô hạn qua runs.
- [ ] HikariCP active/pending/timeouts/usage được đo cả theo cluster.
- [ ] Connection budget bao gồm manager/worker/publisher/JobRepository.
- [ ] Thêm worker không làm giảm useful throughput do DB contention.

### Database và middleware

- [ ] Long transactions, locks, commit p99, autovacuum và WAL/replication lag được quan sát.
- [ ] JobRepository metadata tables/index growth có retention và restart plan.
- [ ] ExecutionContext không chứa payload khổng lồ.
- [ ] Broker request/reply/DLQ queues có depth/oldest age/drain policy.
- [ ] Prefetch/inflight request count bounded và phù hợp worker memory.
- [ ] File/object storage disk/inodes/staging attempts có budget.
- [ ] Chunk/partition tail latency và hot-key skew được giám sát.
- [ ] Sản phẩm downstream có throughput/latency và idempotency contract.

### Correctness và recovery

- [ ] Phân biệt read/write attempts với unique committed business effects.
- [ ] Full accepted/filter/reject/dedup accounting theo contract.
- [ ] Output key/version diff, checksums và manifests đều PASS.
- [ ] Restart cùng JobInstance/identifying params, source snapshot không đổi.
- [ ] Worker kill sau business commit trước checkpoint có test.
- [ ] Remote worker ownership không chồng lấn khi manager timeout.
- [ ] Broker ACK unknown/redelivery không nhân đôi effect.
- [ ] Outbox/inbox/file staging an toàn qua retry.
- [ ] Sau outage, backlog drain trong recovery SLO.
- [ ] Audit old/new JobExecution và mọi fault timeline đã có.
- [ ] JobExecution COMPLETED không được dùng thay business validation.

### Đo đạc và báo cáo

- [ ] Metrics time series có 1/5/15-min windows và sample counts.
- [ ] p99 histogram được tổng hợp đúng, không mean p99 các workers.
- [ ] Metric tags không gây high-cardinality hoặc lộ PII.
- [ ] Telemetry/load-generator overhead được kiểm soát và ghi lại.
- [ ] Dashboard gắn markers deployment, autoscale, backup và injected faults.
- [ ] PASS/FAIL/INCONCLUSIVE dựa trên acceptance contract đã chốt.
- [ ] Có run manifest: code/image/JDK/GC/config/dataset/topology/version.
- [ ] Có evidence links cho JobRepository, business reconciliation, DB, broker.
- [ ] Một regression gần ngưỡng được rerun/A-B trước khi kết luận.
- [ ] Cleanup test data chỉ sau khi đã giữ evidence/retention cần thiết.

## 48. Câu hỏi tự kiểm tra

**1. Soak test khác load test ngắn ở điểm nào quan trọng nhất?**

Soak nhấn vào **tác động tích lũy theo thời gian** dưới workload đại diện: memory/resource drift, queue lag, metadata growth, restart/correctness; load test ngắn nhấn vào tốc độ/latency ở một mức tải.

**2. Vì sao 24 giờ một JobExecution không thay thế 500 JobInstances ngắn?**

Vì nó không tạo/đóng các lifecycle resources nhiều lần và không làm JobRepository metadata tích lũy theo chuỗi runs giống production.

**3. CPU thấp và queue tăng dần có thể là vấn đề gì?**

Có thể producer vượt sustainable throughput ở dependency khác như DB/broker, hoặc worker bị chặn bởi connection/locks. Cần đo arrival, useful processing và queue age.

**4. Vì sao heap used tăng chưa đủ chứng minh memory leak?**

Heap có warm-up, caches và dao động trước GC. So post-GC live set giữa các windows tương đương, queue depth và retained references.

**5. Heap ổn nhưng container OOMKill. Nên xem gì?**

Native RSS, direct buffers, metaspace, thread stacks, container memory limit, cgroup accounting và page cache.

**6. HikariCP active tăng có chắc là code không đóng connection không?**

Không. SQL/transactions chậm cũng giữ connection lâu; so connection usage duration, DB wait events, borrow times và code lifecycle.

**7. Vì sao JobRepository growth cần soak nhiều kỳ?**

Mỗi instance/partition/restart tạo metadata; query/checkpoint latency và disk/index bloat có thể chỉ lộ sau nhiều executions.

**8. Broker backlog tăng 500 events/s suốt 24 giờ nghĩa là gì?**

Backlog lý thuyết tăng `500 × 86.400 = 43.200.000` events nếu rates ổn định và không có drops/caps. Hệ thống có thể không sustainable.

**9. Khi nào queue sawtooth không phải FAIL?**

Khi burst tăng là chủ đích nhưng **drain đúng SLA** trong mỗi chu kỳ, oldest age/storage nằm budget và business data không mất.

**10. Mean chunk latency tốt nhưng p99 tăng mạnh. Có thể PASS không?**

Không nếu p99 vi phạm acceptance SLO. Cần tìm tail DB lock, GC, broker ACK hoặc hot partition skew.

**11. Có được cộng p99 của tám workers rồi chia tám để tính cluster p99 không?**

Không. Quantile phải được tính từ phân phối tổng hợp/histogram buckets phù hợp.

**12. Vì sao prefetch lớn có thể gây OOM dù broker queue giảm?**

Nó có thể chuyển backlog vào heap worker; phải đo tổng inflight bytes và backpressure.

**13. Khi processor retry cùng item ba lần, có nên đếm là ba business records đã hoàn thành?**

Không. Attempts khác unique validated committed records; cần idempotent ledger/correctness metric.

**14. Worker chết sau business commit trước JobRepository checkpoint tạo rủi ro gì?**

Restart có thể replay item/chunk đã commit. Cần stable business identity, idempotent writes và reconciliation.

**15. Nếu một partition chạy 245 phút trong khi 23 partitions chạy 30 phút, bottleneck là gì?**

Tail partition/straggler chi phối JobExecution completion. Phải điều tra skew/hot rows/worker ownership và partition strategy.

**16. Một test broker-down 3 phút có thể chấm FAIL ngay vì queue tăng không?**

Không nếu queue tăng là tác động kỳ vọng trong fault window. Chấm theo recovery SLO, drain time, stability và data correctness.

**17. Với backlog 3,6 triệu, arrival 8k/s và consumer 12k/s, mất bao lâu để drain?**

Khoảng 15 phút theo mô hình ổn định: `3.600.000 / (12.000-8.000) = 900 giây`. Thời gian thực còn phụ thuộc tail latency/capacity.

**18. Vì sao không dùng readCount/writeCount làm đối soát sau restart?**

Rollback/replay/skip/one-to-many có thể làm counters khác unique business records; cần stable key/version diff và business effects validation.

**19. Khi metric backend mất dữ liệu 8 giờ trong soak 24 giờ, có thể PASS không?**

Không nên tự PASS theo ngưỡng yêu cầu full coverage. Đánh INCONCLUSIVE hoặc rerun theo chính sách, trừ khi có bằng chứng thay thế được chấp nhận từ trước.

**20. Tại sao cần đánh dấu deploy, autoscaling và backup trên dashboard?**

Vì các hoạt động này tạo thay đổi throughput/latency/resource; thiếu timeline markers dễ quy sai thành memory leak hay regression.

**21. Một container RSS tăng nhưng heap post-GC phẳng. Chỉ cần tăng -Xmx không?**

Không. Phải tìm native/direct memory, stacks, JIT, fragmentation hoặc page cache; tăng heap max còn có thể giảm headroom native.

**22. Một bài soak không crash nhưng oldest message age tăng vô hạn và output key diff = 0 có đạt không?**

Không nếu violating backlog/latency/SLA contract. Correctness là cần thiết nhưng chưa đủ cho sustainability.

**23. Vì sao test không nên tạo mọi item giống nhau?**

Vì có thể giảm cache misses, serialization pressure, hot-key skew, reject/retry paths và DB lock contention so production.

**24. Tiêu chí tổng quát để công nhận soak PASS là gì?**

Đủ thời lượng/mẫu và actual arrival target; throughput/p99/backlog/resource slopes đạt SLO; restart/recovery/drain đúng; business reconciliation không thiếu/trùng; tất cả bằng chứng có thể truy lại và không có lỗi quan trọng bị che.

## 49. Bài tập thực hành có hướng dẫn

**Bài tập A — Kiểm tra throughput drift.** Chạy 4 JobInstances nối tiếp, mỗi instance xử lý cùng lượng records từ các immutable snapshots khác nhau. Thu useful throughput mỗi 5 phút, tính median early vs late windows và viết nhận định có điều kiện. Không đổi workload mix giữa các windows.

**Bài tập B — Phân biệt backlog và heap leak.** Dùng broker test queue với arrival rate cao hơn consumer 5% trong một giờ; sau đó pause producer và đo drain time, post-GC heap. Kết luận có reference leak hay chỉ backlog dựa trên dữ liệu, không nhìn đồ thị heap đơn lẻ.

**Bài tập C — Connection pool pressure.** Giữ worker threads cố định, thay đổi pool max nhỏ–vừa–lớn trong môi trường test. Đo Hikari pending/usage, DB active sessions, locks, useful throughput, p99. Xác định điểm tăng pool không còn tăng throughput.

**Bài tập D — Restart fault.** Kill worker giữa chunk, restart **cùng JobInstance**, lưu old/new JobExecution IDs, so input/output business keys, outbox deliveries và reject inventory. Chỉ PASS nếu không có unintended duplicate effect.

**Bài tập E — Long-cycle resource leak.** Chạy 100 sequential JobInstances; sau mỗi run đo threads, RSS, FDs, temp disk, JobRepository table size, metric time-series count. Tính slope và đề xuất retention/cleanup nếu không plateau.

**Bài tập F — Soak report.** Viết báo cáo 1 trang tóm tắt acceptance thresholds, actual load, evidence windows, drift, faults, recovery, correctness và verdict. Ghi rõ điều gì **chưa được chứng minh** khi môi trường test khác production.

## 50. Tổng kết: nhanh, bền và đúng là ba điều kiện riêng

Với Spring Batch scaling, một cấu hình thành công chỉ khi **cả ba** mục tiêu được kiểm chứng:

1. **Nhanh:** useful throughput và tail latency đáp ứng business SLA.
2. **Bền:** qua nhiều giờ/cycles, heap/native memory, queues, connections, DB/WAL/JobRepository và file resources vẫn bounded với headroom phù hợp.
3. **Đúng:** retry/restart/fault injection không làm mất hoặc nhân đôi business effects; output manifests, ledger và downstream publication được đối soát.

Soak test nên bắt đầu bằng **immutable workload + acceptance contract**, chạy đủ warm-up/steady/recovery phases, đo time-series theo cùng timeline, rồi thử lỗi có kiểm soát. Nếu chỉ nhìn `JobExecution COMPLETED` hoặc average items/s, bạn có thể bỏ qua queue drift, memory leak chậm, tail partition và khả năng restart sai.

**Ghi nhớ:** **Test soak dài giờ không phải cuộc thi “chạy lâu mà chưa crash”**. Đó là phép kiểm chứng liệu một kiến trúc Spring Batch đa luồng/phân vùng/phân tán có duy trì **sustainable useful throughput, resource limits và dữ liệu nghiệp vụ đúng** khi chạy đủ lâu, khi JobInstances tích lũy và khi dependencies gặp lỗi. Chỉ ghi PASS khi các chỉ số và kết quả đối soát đạt tiêu chí đã chốt **với bằng chứng có thể tái lập**.
