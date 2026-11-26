# Xác định bottleneck của Job trong Spring Batch

## 1. Vì sao phải tìm bottleneck trước khi mở rộng?

Trong Spring Batch, một **Job** có thể gồm nhiều **Step**; mỗi Step có thể đọc dữ liệu, xử lý, ghi kết quả, giao tiếp với dịch vụ ngoài và quản lý transaction. Với workload lớn, thời gian chạy Job thường bị chi phối bởi một vài tài nguyên hoặc công đoạn có năng lực phục vụ thấp nhất, gọi là **bottleneck (nút thắt cổ chai)**.

Ví dụ, Job nhập 10 triệu giao dịch chạy 4 giờ. Tăng số luồng từ 2 lên 8 không bảo đảm rút thời gian xuống còn 1 giờ: nếu tất cả luồng cùng chờ database ghi dữ liệu, việc tăng concurrency có thể làm tranh chấp khóa và thời gian chờ connection cao hơn. Mục tiêu của phân tích nhu cầu là **xác định giới hạn thực tế bằng phép đo**, rồi mới chọn cách mở rộng: multi-threaded step, parallel steps, partitioning hay xử lý phân tán.

Sau bài học, người học có thể:

- Phân biệt Job chậm với nguyên nhân khiến Job chậm; phân tích bottleneck ở cấp Job, Step, chunk và hạ tầng.
- Đo thời gian chạy, throughput, độ trễ, độ chờ, lỗi và mức sử dụng tài nguyên bằng số liệu có thể đối chiếu.
- Tìm dấu hiệu nghẽn tại reader, processor, writer, transaction, connection pool, database, JVM và hệ thống ngoài.
- Thiết kế thí nghiệm thay đổi một biến, xác nhận giả thuyết và ước lượng khả năng scale an toàn.
- Lập báo cáo kết luận có bằng chứng, lưu ý thread safety, restart và tính đúng đắn dữ liệu.

## 2. Hiểu đúng bottleneck và phạm vi đo

**Bottleneck** là công đoạn hoặc tài nguyên đang hạn chế tốc độ hoàn thành công việc trong điều kiện tải hiện tại. Bottleneck có thể dịch chuyển: tối ưu SQL đọc xong, CPU xử lý có thể trở thành giới hạn mới; tăng số worker xong, connection pool hoặc tốc độ commit có thể thành giới hạn.

Không thể kết luận chỉ từ triệu chứng “CPU thấp”, “Step lâu”, hoặc “có nhiều thread”. Cần trả lời đồng thời ba câu hỏi:

1. **Job đang chậm ở đâu?** Ví dụ: Step đọc nguồn chiếm 70% thời gian Job, hoặc 95% chunk tốn trên 2 giây.
2. **Tại sao công đoạn đó chậm?** Ví dụ: truy vấn phải quét toàn bảng, chờ connection, tranh chấp khóa hoặc gọi API có độ trễ cao.
3. **Thay đổi gì làm số liệu tốt hơn?** Ví dụ: thêm chỉ mục làm p95 truy vấn giảm, và throughput toàn Job tăng khi cùng lượng dữ liệu.

### 2.1. Bốn lớp quan sát

| Lớp | Câu hỏi cần trả lời | Dữ liệu đáng đo |
|---|---|---|
| Job | Toàn Job mất bao lâu; có chờ scheduler hay khởi tạo không? | Job start/end, trạng thái, tổng bản ghi hợp lệ, SLA |
| Step | Step nào quyết định thời gian kết thúc Job? | Step start/end, read/write/filter/skip/commit/rollback count |
| Chunk và thao tác | Thời gian nằm ở đọc, xử lý, ghi hay commit? | p50/p95/p99 thời gian read/process/write/chunk, kích thước batch, transaction latency |
| Tài nguyên | Công đoạn chậm vì CPU, I/O, database, mạng hay contention? | CPU, GC, heap, disk, network, query plan, lock waits, connection pool, thread pool |

Ở Step dạng chunk, luồng logic thường là:

~~~text
Nguồn dữ liệu -> ItemReader -> ItemProcessor -> ItemWriter -> Commit
                      |              |              |
                 Query / file     CPU / API        SQL / I/O
                             [Lặp theo từng chunk]
~~~

Reader, processor và writer không nhất thiết tốn cùng một lượng thời gian. Ngoài các bước nghiệp vụ, còn có thời gian tạo bean, mở reader, lấy transaction, checkpoint, cập nhật JobRepository, flush và commit. Nếu một Step dùng nhiều luồng, thời gian của các thành phần có thể **chồng lấp**; vì vậy không tự cộng mọi bộ đếm thời gian của từng luồng để suy ra wall-clock duration.

### 2.2. Wall-clock, thời gian phục vụ và thời gian chờ

- **Wall-clock duration**: thời gian từ bắt đầu tới kết thúc thực tế; chỉ số chính khi so với SLA.
- **Service time**: thời gian tài nguyên trực tiếp xử lý một yêu cầu, ví dụ CPU chạy processor hoặc database thực thi câu SQL.
- **Wait time**: thời gian chờ tài nguyên, connection, lock, queue, phản hồi API hoặc I/O.
- **Throughput**: số bản ghi xử lý thành công trên một giây (hoặc số byte/giây, số chunk/giây); phải nêu rõ định nghĩa bản ghi.
- **Latency**: thời gian hoàn thành một item/chunk/request; nên xem phân vị p95/p99 cùng mức trung bình vì đuôi chậm có thể quyết định SLA.

Giả sử một chunk có 500 bản ghi, mất 800 ms chủ yếu để ghi và commit. Năng lực gần đúng của **một đường ghi tuần tự** là 500 / 0,8 = **625 bản ghi/giây**, chưa tính thời gian đọc và xử lý. Tăng CPU không giải quyết được giới hạn này nếu database vẫn chỉ hoàn thành chừng ấy công việc.

## 3. Các chỉ số để định vị bottleneck

### 3.1. Công thức nền tảng

Với cùng một tập dữ liệu và điều kiện đo:

~~~text
job_duration_s   = job_end - job_start
throughput_read  = read_count / step_duration_s
throughput_write = write_count / step_duration_s
speedup(p)       = T(1 worker) / T(p workers)
efficiency(p)    = speedup(p) / p
~~~

Ở đây, **read_count** không bắt buộc bằng **write_count** vì processor có thể lọc bản ghi (trả về null) hoặc cơ chế skip bỏ qua item lỗi. Cần ghi nhận thêm **filter_count**, **read_skip_count**, **process_skip_count**, **write_skip_count**. Dùng số bản ghi ghi thành công hoặc số bản ghi nghiệp vụ hoàn tất để đánh giá throughput đầu ra; không gọi một Job “nhanh hơn” nếu Job chỉ ghi ít dữ liệu hơn vì bị filter/skip ngoài dự kiến.

Với các Step tuần tự, thời gian Job gần bằng tổng thời gian các Step cộng overhead. Với các Step chạy song song, **đường găng (critical path)** mới quyết định thời điểm Job kết thúc:

~~~mermaid
flowchart LR
  A[Job bắt đầu] --> B[Step chuẩn bị]
  B --> C[Step kiểm tra nguồn: 4 phút]
  B --> D[Step chuyển đổi: 12 phút]
  C --> E[Step kết sổ: 2 phút]
  D --> E
  E --> F[Job kết thúc]
~~~

Ở hình trên, hai Step giữa chạy song song. Nếu thời gian Step chuẩn bị có thể bỏ qua thì thời gian Job gần đúng là **max(4, 12) + 2 = 14 phút**, không phải 4 + 12 + 2 = 18 phút. Nếu Step chuẩn bị mất thêm t phút thì cộng t vào kết quả. Khi báo cáo, nên dùng timestamp thực tế từ JobRepository để dựng timeline, tránh cộng trùng thời gian.

Nếu tỷ lệ công việc buộc phải tuần tự là **s**, còn phần có thể song song chạy trên **p** worker, giới hạn lý tưởng theo định luật Amdahl:

~~~text
speedup_tối_đa(p) = 1 / (s + (1 - s) / p)
~~~

Nếu s = 20%, dù có vô hạn worker thì speedup lý tưởng tối đa là 5 lần. Trong thực tế, chi phí đồng bộ, phân phối dữ liệu, kết nối, database và mất cân bằng partition còn làm giới hạn thấp hơn.

### 3.2. Nhóm dấu hiệu thực tế

| Dấu hiệu quan sát | Giả thuyết ưu tiên | Kiểm chứng trực tiếp |
|---|---|---|
| CPU của tiến trình cao liên tục, nhiều thread RUNNABLE | Processor, chuyển đổi dữ liệu hoặc serialization nặng CPU | Java Flight Recorder (JFR), CPU profiler, thời gian process/item |
| CPU ứng dụng thấp nhưng Step chậm, SQL đọc lâu | Reader/DB đọc/I/O là giới hạn | Slow query, EXPLAIN ANALYZE trên môi trường kiểm thử, scan và I/O database |
| p95 của write/chunk tăng mạnh khi thêm worker | Writer/commit, khóa hoặc transaction log đang nghẽn | DB lock waits, thời gian commit, batch size, throughput ghi |
| Active connections đạt max, pending requests tăng | Connection pool giới hạn | HikariCP active/idle/pending/timeout và cấu hình max pool |
| Thời gian chạy tăng kèm GC pause, heap tiến sát giới hạn | Phân bổ đối tượng, chunk quá lớn hoặc giữ dữ liệu lâu | GC logs/JFR, allocation profile, heap, live set |
| Nhiều thread WAITING/BLOCKED hoặc queue ngày càng dài | Lock, mutex, rate limit, executor hoặc downstream nghẽn | Thread dump, executor active/queue, lock contention |
| Nhiều lần retry/rollback, throughput đầu ra thấp | Lỗi dữ liệu, API, timeout hoặc transaction conflict | Retry count, rollback count, exception, p95 dependency |
| Một partition chạy lâu hơn nhiều partition còn lại | Data skew, hot key hoặc phân phối không cân | Throughput, thời gian, số bản ghi theo partition |
| Ghi JobRepository tăng chậm khi có rất nhiều Step | Metadata DB/JobRepository thành điểm tranh chấp | SQL và lock waits của bảng metadata, commit count, tần suất cập nhật |

Mỗi dấu hiệu mới chỉ là **giả thuyết**. Ví dụ CPU JVM thấp có thể do đang chờ database, nhưng cũng có thể do scheduler chưa cấp tài nguyên hoặc số thread cấu hình quá ít; phải kiểm chứng bằng chỉ số chờ và mức sử dụng của thành phần liên quan.

## 4. Thu thập baseline có thể so sánh

Không tối ưu khi chưa có **baseline**. Baseline tối thiểu cần:

1. **Mô tả workload**: số bản ghi, kích thước trung bình, phân bố dữ liệu, tỷ lệ filter/skip, số bản ghi trùng, đích ghi, thứ tự xử lý và số partition.
2. **Chụp cấu hình**: phiên bản Spring Batch/JDK, reader/writer, chunk size, fetch size, số worker, connection pool, giới hạn API, số CPU và dung lượng heap.
3. **Giữ điều kiện tải nhất quán**: cùng snapshot hoặc bộ dữ liệu tương đương, cùng index, cùng cạnh tranh từ workload khác; đánh dấu lần chạy đầu khi cache/JIT còn lạnh.
4. **Chạy một mốc đối chứng**, đo wall-clock Job/Step, throughput đầu ra, tỉ lệ lỗi, số lần commit/rollback, p50/p95/p99 và CPU/GC/DB.
5. **Lặp nhiều lần khi khả thi**; so sánh median và độ phân tán, ghi lại run ID, thời điểm và điều kiện để giải thích ngoại lệ.

Chỉ số đọc sau khi Job hoàn thành giúp biết Step nào chậm; để hiểu **vì sao** chậm cần quan sát khi Job đang chạy. Có thể lấy mẫu mỗi 5–15 giây ở môi trường kiểm thử, hoặc dùng sampling phù hợp trên production để hạn chế overhead. Đánh dấu thời điểm database maintenance, backup, network event, GC pause và thay đổi tải bên ngoài.

**Định nghĩa phép đo trước khi chạy:** một giao dịch được coi là hoàn thành khi dữ liệu đã được ghi và commit thành công; tránh trộn “số bản ghi đọc” với “số bản ghi ghi”. Khi xử lý remote hoặc retry, còn cần tách số lần thử khỏi số nghiệp vụ hoàn thành.

## 5. Dùng Spring Batch để tìm Step chậm

### 5.1. JobRepository và StepExecution

Spring Batch ghi metadata thực thi vào JobRepository. **JobExecution** ghi nhận trạng thái và thời gian của Job; **StepExecution** cung cấp các trường phù hợp để phân tích như:

- start/end time, status, exit status;
- read count, write count, filter count;
- read/process/write skip count;
- commit count và rollback count.

Ví dụ truy vấn **PostgreSQL**, với schema metadata mặc định Spring Batch và một JobExecution đã kết thúc:

~~~sql
SELECT
    s.STEP_NAME,
    s.STATUS,
    s.READ_COUNT,
    s.WRITE_COUNT,
    s.FILTER_COUNT,
    s.READ_SKIP_COUNT,
    s.PROCESS_SKIP_COUNT,
    s.WRITE_SKIP_COUNT,
    s.COMMIT_COUNT,
    s.ROLLBACK_COUNT,
    ROUND(
        EXTRACT(EPOCH FROM (s.END_TIME - s.START_TIME)),
        2
    ) AS duration_seconds,
    ROUND(
        s.WRITE_COUNT /
        NULLIF(EXTRACT(EPOCH FROM (s.END_TIME - s.START_TIME)), 0),
        2
    ) AS write_items_per_second
FROM BATCH_STEP_EXECUTION s
WHERE s.JOB_EXECUTION_ID = :job_execution_id
  AND s.START_TIME IS NOT NULL
  AND s.END_TIME IS NOT NULL
ORDER BY s.START_TIME, s.STEP_EXECUTION_ID;
~~~

Thay tham số **:job_execution_id** bằng execution cần điều tra. Schema/prefix bảng hoặc kiểu dữ liệu timestamp có thể khác tùy cấu hình và database; cần điều chỉnh cú pháp tương ứng. Nếu Step chưa kết thúc, **END_TIME** có thể rỗng; dùng timestamp lấy mẫu hiện tại để tính tốc độ tạm thời, đồng thời ghi rõ đó là ước lượng.

**Cách diễn giải:**

- Step có wall-clock lớn trên **đường găng** là ứng viên điều tra đầu tiên.
- **READ_COUNT** lớn nhưng **WRITE_COUNT** nhỏ cần phân tích FILTER/SKIP trước khi kết luận writer chậm.
- **ROLLBACK_COUNT** bất thường có thể phản ánh retry/transaction conflict; đọc log nguyên nhân lỗi.
- **COMMIT_COUNT** quá cao so với khối lượng ghi có thể cho thấy chunk quá nhỏ, nhưng không tự động chứng minh việc tăng chunk sẽ cải thiện.
- Nếu sử dụng partitioning, tổng thời gian của các worker Step không phải tổng wall-clock của manager Step; cần đối chiếu từng partition và thời điểm bắt đầu/kết thúc.

Lưu ý: StepExecution cho biết **kết quả tổng hợp của Step**, không tự cung cấp thời gian tách riêng reader, processor, writer hoặc SQL. Muốn kết luận nguyên nhân phải kết hợp instrumentation và metric bên dưới.

### 5.2. Micrometer, Actuator và log có ngữ cảnh

Trong các phiên bản Spring Batch hiện đại có tích hợp Micrometer, có thể theo dõi timer/counter thực thi Job, Step, đọc item, xử lý item và ghi chunk. Khi dùng Spring Boot, Actuator và hệ thống quan sát như Prometheus/Grafana giúp kiểm tra phân vị, xu hướng và tương quan theo thời gian. Tên metric, tag và cách xuất metric cần kiểm tra theo **phiên bản Spring Batch/Spring Boot** của dự án; không mặc định một dashboard mẫu luôn trùng khớp.

Khi các chỉ số mặc định chưa thể tách thời gian chunk, bổ sung **ChunkListener**. Ví dụ dưới đây đo wall-clock của chunk giữa callback trước chunk và callback sau chunk, dùng thời gian đơn điệu để tránh ảnh hưởng của thay đổi đồng hồ hệ thống:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.batch.core.ChunkListener;
import org.springframework.batch.core.scope.context.ChunkContext;
import org.springframework.stereotype.Component;

import java.util.concurrent.TimeUnit;

@Component
public class ChunkTimingListener implements ChunkListener {

    private final MeterRegistry registry;
    private final ThreadLocal<Long> startNanos = new ThreadLocal<>();

    public ChunkTimingListener(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public void beforeChunk(ChunkContext context) {
        startNanos.set(System.nanoTime());
    }

    @Override
    public void afterChunk(ChunkContext context) {
        record(context, "success");
    }

    @Override
    public void afterChunkError(ChunkContext context) {
        record(context, "error");
    }

    private void record(ChunkContext context, String outcome) {
        Long start = startNanos.get();
        try {
            if (start != null) {
                long elapsed = System.nanoTime() - start;
                Timer.builder("custom.batch.chunk.duration")
                    .tag("step", context.getStepContext().getStepName())
                    .tag("outcome", outcome)
                    .register(registry)
                    .record(elapsed, TimeUnit.NANOSECONDS);
            }
        } finally {
            startNanos.remove();
        }
    }
}
~~~

Đăng ký listener vào Step bằng **.listener(chunkTimingListener)** trong cấu hình Step hiện có. **ThreadLocal** giữ mốc thời gian riêng cho từng thread; **remove()** sau mỗi chunk tránh giữ dữ liệu trong thread pool. Timer trên đo thời gian ở ranh giới callback chunk, có thể bao gồm đọc/xử lý/ghi và transaction; nó **không phân tách** các thành phần này. Để tách chi tiết, đo thêm quanh reader, processor, writer hoặc JDBC instrumentation. Với listener dùng chung giữa nhiều Step, chỉ dùng tag có số lượng giá trị hữu hạn như tên Step và outcome; không dùng transaction ID, item ID hoặc jobExecutionId làm tag metric vì gây bùng nổ cardinality.

Nếu cần xem p95/p99, phải cấu hình phân phối histogram hoặc percentile phù hợp trong Micrometer/Prometheus; timer đơn lẻ không mặc nhiên cung cấp mọi phân vị ở backend quan sát.

### 5.3. Đối chiếu với hệ thống bên dưới

- **Ứng dụng/JVM**: CPU theo core, phân bố CPU theo thread, JFR, allocation rate, heap, GC pause và thread dump. Thread RUNNABLE không mặc nhiên là đang chiếm CPU, cần đối chiếu sampling/profiler.
- **Database**: số query/giây, p95 duration, index scan/seq scan, buffer/cache hit, I/O, lock wait, deadlock, thời gian commit và transaction log. Quan sát cả nguồn đọc lẫn đích ghi.
- **Connection pool**: active, idle, pending, max size, timeout; lượng pending tăng cùng việc active chạm max gợi ý chờ connection.
- **Executor/worker**: active thread, queue depth, wait time, số task hoàn thành và phần trăm thời gian nhàn rỗi.
- **Mạng/API/queue**: request rate, timeout, retry, latency, rate limiting, message lag, throughput và độ trễ acknowledge.
- **Host/container**: CPU throttling, memory pressure, disk IOPS/throughput, network bandwidth; container đạt quota CPU dù host còn tài nguyên vẫn có thể nghẽn.

Tương quan là mấu chốt: nếu p95 chunk tăng đúng lúc connection-pending tăng, kiểm tra pool và thời gian query; nếu pending vẫn bằng 0 nhưng write p95 tăng, chuyển sang khóa, I/O và commit trong database.

## 6. Quy trình điều tra bottleneck theo từng bước

### Bước 1 — Chọn một JobExecution và dựng timeline

Xác định SLA (ví dụ hoàn thành nhập dữ liệu trước 06:00), volume đã xử lý và thời điểm Job bị chậm. Ghi thời gian Job, từng Step, các nhánh song song, retry và thời gian cuối cùng. Đánh dấu đường găng. Đừng tập trung vào Step dùng 90% CPU nhưng chạy song song và hoàn tất sớm hơn nhánh khác.

### Bước 2 — Khoanh vùng Step và pha chậm

Đối chiếu write throughput, read throughput, chunk p95, thời gian read/process/write, commit count và rollback count. Với chunk-based Step, đặt các câu hỏi cụ thể:

- Reader đang chờ SQL, file, object store hay chưa cấp dữ liệu đủ nhanh?
- Processor tiêu tốn CPU, tạo quá nhiều object hay phải gọi API đồng bộ?
- Writer dùng JDBC batch thực sự hay đang ghi từng row? Có chờ khóa, flush, transaction log hay mạng không?
- Chunk quá nhỏ gây nhiều commit, hay chunk quá lớn kéo dài lock/rollback và tăng bộ nhớ?

Nếu một Step chủ yếu chạy tasklet, truy vấn tổng hợp hoặc lệnh gọi hệ thống ngoài, hãy đặt instrumentation đúng quanh hoạt động đó; không áp đặt mô hình reader–processor–writer cho mọi Step.

### Bước 3 — Tìm giới hạn tài nguyên có thể kiểm chứng

Đặt chỉ số ứng dụng cạnh metric hạ tầng trên cùng cửa sổ thời gian. Ví dụ:

- CPU app 95% trên số core được cấp, processor p95 cao, database vẫn nhàn → ưu tiên profile processor.
- CPU app 20%, worker chờ SQL, database disk I/O bão hòa → ưu tiên dữ liệu đọc, plan/index hoặc I/O.
- Active pool 20/20, pending 50, DB CPU 40% → có khả năng pool nhỏ hoặc connection bị giữ quá lâu; đo thời gian giữ connection trước khi tăng pool.
- DB CPU 95%, transaction/lock wait tăng mạnh khi thêm worker → database là giới hạn đang hoạt động; tăng pool/worker có thể làm tệ hơn.

Không dùng một ngưỡng CPU duy nhất cho mọi hệ thống: 80% CPU có thể bình thường, nhưng 80% CPU đi kèm latency p99 tăng và queue dài là tín hiệu cần điều tra.

### Bước 4 — Thử một thay đổi và đo lại

Xây dựng giả thuyết có thể bác bỏ, ví dụ: “Thời gian ghi tăng vì từng item phát một INSERT; gom 500 bản ghi/batch sẽ giảm round-trip và tăng throughput mà không đổi số bản ghi đúng”. Chạy A/B với cùng tập dữ liệu, cùng cấu hình khác, đo ít nhất wall-clock, throughput, p95, lỗi, commit/rollback, CPU/DB/GC và độ đúng dữ liệu.

Một thứ tự thử thường hữu ích:

1. Sửa truy vấn thiếu index, N+1 query, xử lý dư thừa, gọi API không cần thiết.
2. Cân chỉnh fetch size, JDBC batching và chunk size theo dữ liệu thực, đánh giá bộ nhớ và thời gian giữ transaction.
3. Xử lý lock contention, cơ chế kết nối và hạn mức downstream.
4. Sau khi một luồng/partition đã hiệu quả, tăng concurrency hoặc phân vùng từng nấc có kiểm soát.

### Bước 5 — Xác nhận nút thắt thực sự đã dịch chuyển

Một thay đổi chỉ được xem là có ích nếu **thời gian Job giảm hoặc throughput đầu ra tăng** trên workload tương đương, độ đúng dữ liệu và đặc tính restart vẫn giữ nguyên. Nếu throughput ổn định mà thêm worker làm DB wait tăng, bạn đã chạm giới hạn chia sẻ; cần thay đổi kiến trúc/nguồn lực thay vì tiếp tục tăng worker.

## 7. Ví dụ: tăng worker nhưng Job không nhanh hơn

Giả sử Job nhập 500.000 đơn hàng từ database nguồn sang database đích. Reader đã được phân vùng theo khóa chính, mỗi partition đọc phạm vi không trùng nhau, writer dùng JDBC batch và mỗi worker xử lý chunk riêng. Nhóm đo cùng snapshot dữ liệu qua các cấu hình:

| Số worker | Throughput đầu ra | CPU database đích | p95 chờ connection | Nhận xét |
|---:|---:|---:|---:|---|
| 1 | 520 đơn/s | 35% | 0 ms | Mốc đối chứng |
| 2 | 890 đơn/s | 60% | 10 ms | Tăng tốt |
| 4 | 1.030 đơn/s | 88% | 65 ms | Bắt đầu bão hòa |
| 8 | 1.010 đơn/s | 95% | 240 ms | Không còn hiệu quả |

*Các số liệu trên là ví dụ minh họa, không phải benchmark chung của Spring Batch.*

Với 1 worker, speedup là 1. Với 4 worker, speedup khoảng 1.030 / 520 = **1,98**, efficiency chỉ khoảng 1,98 / 4 = **49,5%**. Với 8 worker, throughput còn giảm nhẹ; thời gian chờ connection tăng cùng CPU database.

**Giả thuyết:** database đích hoặc đường ghi của nó là giới hạn hiện tại. Cần kiểm tra thêm p95 INSERT/batch, lock waits, commit latency, pool utilization và transaction log để phân biệt database thực sự quá tải với pool quá nhỏ hoặc query ghi kém hiệu quả. Không đủ bằng chứng để kết luận chỉ từ CPU database 95%.

**Thí nghiệm tiếp theo:** giữ 4 worker, so sánh batch insert hiện tại với cách ghi tối ưu (nếu writer chưa batching), hoặc kiểm tra index/trigger/khóa tại bảng đích. Nếu throughput tăng và p95 write giảm với cùng độ đúng dữ liệu, giả thuyết được củng cố. Nếu database vẫn bão hòa, đánh giá lại cách phân vùng theo bảng, cửa sổ xử lý, giới hạn write capacity hoặc kiến trúc ingest.

Lưu ý trong ví dụ, việc chia phạm vi khóa chính là điều kiện để các worker không đọc trùng. Không áp dụng ngay 8 thread vào reader kiểu cursor có trạng thái dùng chung khi chưa xác nhận thread safety.

## 8. Từ kết quả đo sang lựa chọn phương án scaling

| Điều kiện đã chứng minh | Hướng xử lý phù hợp | Điểm cần đánh giá |
|---|---|---|
| Processor nặng CPU, có thể xử lý item độc lập, nguồn/đích còn dư năng lực | Multi-threaded step hoặc partitioning | Thread safety của reader/writer, số core thực, thứ tự, restart |
| Nhiều Step độc lập cùng nằm trên đường găng | Parallel steps | Phụ thuộc dữ liệu, transaction và tài nguyên dùng chung |
| Tập dữ liệu chia được thành các miền khóa không giao nhau, có data skew | Partitioning, thiết kế partitioner cân bằng | Idempotency, checkpoint, phân bố tải, xử lý straggler |
| Một máy hết CPU/RAM nhưng database và mạng còn sức chứa | Remote partitioning hoặc remote chunking | Messaging, phân phối/khôi phục task, failure mode, JobRepository |
| Database hay API là điểm nghẽn dùng chung | Tối ưu SQL/batch, nâng năng lực downstream hoặc giới hạn tốc độ | Lock, connection pool, quota, retry storm, consistency |
| Thời gian bị chi phối bởi retry/rollback/GC | Sửa lỗi, memory profile, chiến lược retry/skip và transaction | Tính đúng đắn, timeout, giới hạn lần thử, restart |

Spring Batch có thể tăng throughput bằng multi-threaded step, parallel steps, partitioning và mô hình phân tán; nhưng **scaling chỉ có giá trị nếu tài nguyên thực tế còn headroom**. Khi cân nhắc phương án, phải tính cả:

- **Thread safety**: không mặc định ItemReader/ItemWriter có trạng thái dùng chung an toàn; dùng thiết kế thread-safe hoặc reader riêng theo partition, kiểm thử đồng thời.
- **Restart/checkpoint**: sau khi process chết giữa chunk, Job có thể tiếp tục mà không bỏ sót hoặc xử lý trùng sai nghiệp vụ không? Kiểm tra ExecutionContext và ranh giới commit.
- **Idempotency và phân vùng không chồng lấp**: xử lý lại cùng đơn hàng không tạo duplicate hay ghi đè sai; mỗi partition có khóa phạm vi rõ ràng.
- **Đường đi của dữ liệu và tài nguyên dùng chung**: các worker có thể vẫn tranh cùng một DB, connection pool, hàng đợi, file hoặc API quota.
- **Thứ tự**: tăng concurrency có thể thay đổi thứ tự đọc và ghi; nếu nghiệp vụ yêu cầu ordering, xác định phạm vi bảo đảm trước khi triển khai.
- **Failure/retry**: retry đồng loạt có thể khuếch đại tải; thiết lập giới hạn, backoff và quan sát retry rate.

Một phương án mở rộng tốt là phương án tối ưu **toàn Job** trong giới hạn CPU, RAM, I/O, connection, độ đúng dữ liệu và điều kiện vận hành thực tế, không phải phương án có nhiều thread nhất.

## 9. Những sai lầm chẩn đoán thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Chỉ nhìn tổng thời gian Job | Bỏ lỡ Step, chunk hoặc nhánh trên đường găng | Dựng timeline Job/Step và phân tích wall-clock |
| Gọi read count là số record hoàn tất | Throughput bị thổi phồng khi filter/skip/retry | Dùng write count cùng bộ đếm filter/skip và invariant nghiệp vụ |
| Cộng tổng thời gian các partition song song | Báo cáo thời gian lớn hơn thời gian thực | So timestamp, tìm đường găng và straggler |
| Chỉ tăng task executor/worker | Tăng queue, connection wait, lock hoặc CPU throttling | Đo headroom hạ tầng, thử nấc concurrency |
| Tăng chunk size vô hạn | Giữ transaction lâu, tăng heap, chi phí rollback cao | Thử nhiều chunk size và đo p95/GC/rollback |
| Chỉ xem trung bình | Bỏ qua các chunk/query rất chậm | Xem phân vị và phân bố dữ liệu |
| Benchmark trên dữ liệu quá nhỏ hoặc cache nóng | Kết quả không đại diện production | Dùng workload gần thực tế, nhiều lần chạy và ghi điều kiện |
| Chỉ nhìn CPU của ứng dụng | Bỏ qua database, network, I/O và connection pool | Ghép metric toàn bộ đường xử lý |
| Tối ưu từng Step mà không kiểm tra Job | Step nhanh hơn nhưng đường găng không đổi | Kiểm chứng thời gian kết thúc Job và SLA |
| Không kiểm tra kết quả sau scaling | Nguy cơ mất, lặp hoặc sai thứ tự dữ liệu | So count, checksum/invariant, restart và failover test |

## 10. Bài thực hành: lập hồ sơ và xác minh bottleneck

**Bối cảnh:** Job đồng bộ 2 triệu bản ghi mỗi đêm qua một Step chunk-oriented đang vượt SLA 45 phút. Có quyền đọc metadata Spring Batch và metric ứng dụng/database.

**Nhiệm vụ:**

1. Trích xuất JobExecution gần nhất cùng StepExecution; lập bảng thời gian chạy, read/write/filter/skip, commit/rollback và throughput đầu ra.
2. Instrument chunk p50/p95/p99, tách thời gian đọc, xử lý, ghi khi có thể; đối chiếu CPU, memory/GC, database query/lock và HikariCP.
3. Viết một giả thuyết chỉ rõ **công đoạn**, **tài nguyên**, **bằng chứng**, **kết quả mong đợi** và **điều kiện bác bỏ**.
4. Giữ nguyên workload, thay một cấu hình hoặc tối ưu một truy vấn; chạy lại, so sánh wall-clock, throughput, p95, lỗi và tính đúng đắn.
5. Nếu kết quả tốt, thử 1 → 2 → 4 worker hoặc số partition phù hợp; dừng tăng khi throughput không còn tăng tương xứng hoặc tài nguyên chia sẻ quá tải.
6. Đánh giá restart khi một chunk/worker thất bại; bảo đảm dữ liệu được commit đúng và không có bản ghi nghiệp vụ bị xử lý sai.

Mẫu kết luận ngắn có thể dùng trong báo cáo:

~~~text
Workload           : 2.000.000 bản ghi; snapshot dữ liệu ngày ...
Baseline           : 52 phút; 641 bản ghi hoàn tất/giây; 0 skip bất thường
Step đường găng    : loadOrders (47 phút)
Giả thuyết         : writer chờ commit vì tranh chấp khóa bảng đích
Bằng chứng         : p95 chunk 2,1 giây; p95 commit 1,8 giây;
                     DB lock wait tăng cùng write latency
Can thiệp          : đổi chiến lược ghi / phân vùng khóa trên cùng workload
Sau can thiệp      : 37 phút; 901 bản ghi hoàn tất/giây;
                     p95 chunk 0,9 giây; count/checksum khớp
Giới hạn còn lại   : database I/O khi > 4 worker; cần theo dõi khi volume tăng
Restart validation : chạy lỗi giữa chunk và tiếp tục thành công, không duplicate
~~~

Các giá trị trong mẫu là minh họa. Khi thực hành, cần thay toàn bộ bằng số liệu đo thực tế và nêu phạm vi thử nghiệm.

### Tiêu chí hoàn thành

Chỉ xem là đã **xác định được bottleneck** khi có đủ: (1) chỉ số mô tả tác động lên Job/SLA, (2) vị trí Step/pha, (3) bằng chứng tài nguyên giới hạn, (4) thí nghiệm thay đổi có đối chứng, và (5) dữ liệu đầu ra cùng hành vi restart vẫn chính xác. Nếu mới biết Step nào chậm mà chưa giải thích và kiểm chứng được nguyên nhân, kết luận vẫn đang ở mức **khoanh vùng**, chưa phải root cause.

## 11. Tóm tắt kiến thức cần ghi nhớ

- Bottleneck của Job là giới hạn tốc độ **tại điều kiện tải cụ thể** và có thể dịch chuyển sau mỗi tối ưu.
- Dùng JobExecution/StepExecution để tìm đường găng, đo thời gian và xác minh số bản ghi; dùng Micrometer, listener, profiler và database metrics để tìm nguyên nhân sâu hơn.
- Phân biệt wall-clock, service time, wait time, throughput và p95/p99; dữ liệu chạy song song không được cộng thời gian tùy tiện.
- Tăng concurrency chỉ hợp lý khi reader/processor/writer, database và tài nguyên chia sẻ có đủ headroom; luôn kiểm chứng thread safety và restartability.
- Quy trình chuẩn là **đo baseline → dựng timeline → nêu giả thuyết → thử một thay đổi → đo lại toàn Job → xác minh tính đúng đắn**.

**Tài liệu nên tham khảo khi triển khai:** Spring Batch Reference Documentation (JobRepository, StepExecution, monitoring/metrics, scaling and parallel processing), Spring Boot Actuator/Micrometer documentation, hướng dẫn tối ưu truy vấn và connection pool của hệ quản trị database đang sử dụng. Đối chiếu API, metric và metadata schema với đúng phiên bản Spring Batch trong dự án.
