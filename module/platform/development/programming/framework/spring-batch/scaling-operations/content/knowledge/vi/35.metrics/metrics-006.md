# Worker throughput trong Spring Batch

## 1. Vì sao tăng worker từ 4 lên 16 mà job không nhanh hơn?

Một hệ thống xử lý 12 triệu giao dịch qua **remote partitioning**. Manager tạo 48 partition, gửi các `StepExecution` tới nhiều worker. Dashboard cho thấy mỗi worker có lúc đạt 15.000 items/giây; khi tăng từ 4 lên 16 worker, tổng các đường throughput nhìn có vẻ tăng mạnh. Tuy nhiên, thời gian hoàn tất job chỉ giảm từ 25 xuống 23 phút, PostgreSQL bắt đầu chờ row locks và một partition cuối cùng kéo dài thêm 7 phút.

Vấn đề nằm ở cách đo:

- Một worker đọc nhanh chưa chắc đã ghi nhanh.
- `writeCount` tăng không nhất thiết có bấy nhiêu **business records mới** ở database.
- Tổng tốc độ trong **cửa sổ 10 giây** không thể lấy bằng cách cộng những đỉnh throughput xuất hiện ở **các thời điểm khác nhau**.
- Throughput khi worker đang chạy không bao gồm thời gian đợi partition, startup, retry, queue hoặc kết thúc job.
- Worker nhanh nhất không quyết định kết quả; job thường phải đợi **partition chậm nhất** hoặc toàn bộ tập work units hoàn tất.

Đó là lý do cần một hệ metric vừa nhìn rõ **worker**, vừa đối chiếu được với **StepExecution**, **JobExecution** và **kết quả nghiệp vụ đã commit**.

Bài **“Worker throughput”** thuộc chương **Metrics** của module `SPRING_BATCH_SCALING_OPERATIONS`. Module hướng tới mở rộng Spring Batch cho workload dữ liệu lớn qua multi-threaded step, parallel steps, partitioning và mô hình xử lý phân tán; đồng thời học đo bottleneck, bảo đảm thread safety, retry/restart, vận hành job và lựa chọn kiến trúc theo tài nguyên thực tế.

Sau bài này, bạn có thể:

1. Định nghĩa chính xác throughput theo **read, process, writer item, database affected row, committed business key, byte** và thời gian quan sát.
2. Tách throughput của một worker process, một worker `StepExecution`, một partition logic và toàn bộ job.
3. Thu thập `StepExecution` counts/latency qua listener, đồng thời hiểu giới hạn của từng callback và metric.
4. Tạo metric Micrometer/Prometheus có cardinality hợp lý; đọc `rate`, `increase`, p95 latency và aggregation theo cùng thời điểm.
5. Phát hiện **partition skew, stragglers, worker idle**, retry storm, pool starvation và database contention.
6. Đánh giá scale-out bằng speedup, efficiency, saturation và **end-to-end job wall-clock** thay vì CPU/thread count.
7. Đo tác động của retry, redelivery, restart, lost ACK và writer idempotent đến độ tin cậy của số liệu.
8. Thiết kế benchmark, alert, runbook và bài tập kiểm chứng dữ liệu sau khi tăng concurrency.

**Bối cảnh ví dụ:** Java 17+, Spring Batch 5.2.x, Spring Boot 3.x, Micrometer, Prometheus/Grafana, HikariCP, PostgreSQL. Với Spring Batch 6.x/Boot 4.x, cần đối chiếu API và tên metric có sẵn của chính phiên bản triển khai. Các metric được định nghĩa trong bài là **metric ứng dụng minh họa**, không tuyên bố đều được Spring Batch xuất tự động.

## 2. Định nghĩa throughput phải có đơn vị và ranh giới

Một số đồ thị đều ghi “rows/sec” nhưng đo những việc khác nhau. Trước khi tối ưu, hãy thống nhất **tử số là gì**, **mẫu số là khoảng nào**, **đã commit chưa** và **đếm lại retry hay không**.

| Tên chỉ số | Tử số | Mẫu số | Giải thích |
|---|---|---|---|
| **Read item rate** | Item reader trả về | Giây quan sát | Nhanh ở nguồn không chứng minh đầu ra nhanh |
| **Processed item rate** | Item processor nhận/xử lý | Giây | Có thể có filtered items; processor không nhất thiết có side effect |
| **Writer input item rate** | Item đưa vào `ItemWriter.write` | Giây | Chưa tính commit; retries có thể làm số lần thử tăng |
| **Step write-count rate** | Delta `StepExecution.writeCount` | Giây | Theo lifecycle Batch, không phải số row mới thực ở database |
| **DB affected-row rate** | Row thực sự bị INSERT/UPDATE/DELETE theo SQL/driver | Giây | UPSERT/trigger/update counts đặc biệt cần diễn giải đúng |
| **Unique committed business-key rate** | Business keys hợp lệ mới được chấp nhận và commit | Giây | Thường gần nhất với throughput có ích của ETL idempotent |
| **Byte throughput** | Bytes đã đọc/ghi tại một tầng cụ thể | Giây | Payload bytes khác WAL bytes, disk bytes và network bytes |
| **Job end-to-end throughput** | Business records hợp lệ của toàn job | Từ request/job launch tới completed | Bao gồm startup, queue, tail, retry và finalization theo định nghĩa |

**Các khái niệm không hoán đổi cho nhau.** Một writer dùng PostgreSQL `INSERT ... ON CONFLICT DO NOTHING` có thể nhận 500 items nhưng chèn 480 row vì 20 key đã tồn tại. `writeCount` có thể tăng theo 500 writer items sau chunk, trong khi committed **new rows** chỉ có 480. Nếu đó là duplicate hợp lệ, job không sai; metric phải được đặt tên đúng.

### 2.1. Cửa sổ thời gian và công thức cơ bản

Với một counter tăng đơn điệu `N(t)` đo **đúng một loại event**:

\[
R_{\Delta t}=\frac{N(t_2)-N(t_1)}{t_2-t_1}
\]

Ví dụ trong 30 giây, một worker `StepExecution` tăng `writeCount` từ 8.000 lên 44.000:

\[
R_{\mathrm{step-write}}\approx\frac{44\,000-8\,000}{30}
=1\,200\ \mathrm{items/s}
\]

Đây là **step writer-item rate**, chưa chứng minh 1.200 business rows/s đã được insert mới. Nếu worker retry một chunk bị rollback, các lần `write()` có thể được gọi nhiều hơn số item được ghi nhận sau chunk commit. Nếu process bị kill, in-memory metrics có thể mất phần chưa được scrape.

### 2.2. Denominator: thời gian nào là quan trọng?

- **Worker active time:** thời gian worker thực sự xử lý assigned execution/partition. Dùng để đo hiệu suất worker khi bận.
- **Partition elapsed time:** từ partition được gán/bắt đầu tới khi có trạng thái cuối, có thể gồm đợi connection và retry.
- **Job wall-clock:** từ một mốc yêu cầu/launch được thống nhất tới job outcome, có thể gồm scheduling/dispatch/queue/final aggregation.
- **Cluster allocated time:** tổng pod/CPU-hours/worker-seconds trả tiền, kể cả idle nếu worker luôn chạy.

Một worker có thể đạt 25.000 items/s khi active nhưng chỉ active 10 giây trong job 2 phút. Không lấy 25.000 làm throughput trung bình của **cả job** nếu phần lớn thời gian worker chỉ chờ.

### 2.3. Độ lớn một item không đồng đều

100.000 records/s chứa bản ghi 100 byte khác hẳn 100.000 records/s chứa JSON 20 KiB. Với I/O-heavy pipelines, nên đo song song:

\[
R_{\mathrm{MiB/s}}=\frac{\Delta\mathrm{bytes}}
{\Delta t\times 1\,048\,576}
\]

Payload size lấy trước/ sau compression có thể khác nhau; kích thước WAL bao gồm write amplification, index/transaction overhead. Luôn ghi rõ tầng đo: **source payload**, **broker payload**, **JDBC row bytes ước lượng** hay **storage/WAL physical bytes**.

## 3. Các tầng worker và partition trong Spring Batch

~~~mermaid
flowchart TB
    M["Manager JobExecution"] --> P["Partitioner / PartitionHandler"]
    P --> R["Request broker (remote partitioning)"]
    R --> A["Worker Pod A"]
    R --> B["Worker Pod B"]
    R --> C["Worker Pod C"]
    A --> SA["Worker StepExecution P0 / P4 / ..."]
    B --> SB["Worker StepExecution P1 / P5 / ..."]
    C --> SC["Worker StepExecution P2 / P6 / ..."]
    SA --> D[(Business DB)]
    SB --> D
    SC --> D
    SA --> J[(Shared JobRepository)]
    SB --> J
    SC --> J
~~~

**Một worker không đồng nghĩa một partition.** Một pod có thể xử lý nhiều `StepExecution` lần lượt hoặc đồng thời, tùy consumer concurrency. Một partition có thể được **thử lại** ở execution khác sau restart, còn tên logical partition và business range vẫn giữ nguyên.

| Tầng | Danh tính | Metric phù hợp | Cảnh báo |
|---|---|---|---|
| Worker process/pod | `workerInstanceId`, pod/container | CPU, heap, GC, threads, pool, processed item rate | Pod ID thường thay đổi, không nên tạo metric label vô hạn |
| Worker `StepExecution` | `stepExecutionId`, step name, JobExecution | Counts, elapsed, skip/retry/rollback, status | ID là từng attempt, khác logical partition |
| Logical partition | `partitionName`, input range/bucket, job identity | Expected/actual keys, partition elapsed, skew | Tên partition có thể tạo high cardinality trên Prometheus |
| Manager `JobExecution` | `jobExecutionId`, JobInstance | End-to-end wall time, total unique output | Manager không tự đo toàn bộ business commits |
| Cluster/DB | Các pool, broker, database | Active worker count, queue age, DB waits, WAL/IO | Shared resource counters không thể mặc định quy toàn bộ cho một job |

### 3.1. So sánh mô hình concurrency

- **Step tuần tự:** một `StepExecution` xử lý chunks lần lượt; đơn giản nhất để gán delta count cho chunk.
- **Multi-threaded step:** nhiều threads có thể xử lý chunks trong **cùng `StepExecution`**. Step-scoped reader **không** tự thành per-thread; instrumentation phải tránh race và không giả định callback tuần tự.
- **Parallel steps:** nhiều `StepExecution` độc lập, có thể cùng tranh database.
- **Local partitioning:** mỗi partition có worker `StepExecution` riêng trong một JVM.
- **Remote partitioning:** worker đọc theo riêng `ExecutionContext`, cần shared `JobRepository` và message transport.
- **Remote chunking:** manager đọc, worker xử lý chunks; metric “worker read rate” khác vì reader ở **manager**.
- **Remote step trong Spring Batch 6.x:** đặt một step ở process khác không tự biến step thành nhiều partitions.

Với mô hình remote, **request published/ACK/reply** và **business commit** là những mốc khác nhau. Không lấy broker ACK rate làm worker business throughput.

## 4. Một ví dụ số: tổng rate, worker rate và tail

Giả sử một job có 1.000.000 unique valid records:

| Worker | Records hợp lệ do worker xử lý trong lượt chạy minh họa | Active time | Rate trong thời gian active |
|---|---:|---:|---:|
| A | 320.000 | 80 s | 4.000 items/s |
| B | 280.000 | 70 s | 4.000 items/s |
| C | 300.000 | 100 s | 3.000 items/s |
| D | 100.000 | 50 s | 2.000 items/s |

Tổng được đối soát là 1.000.000. Nhưng:

- **Không lấy trung bình cộng** bốn worker rates rồi nhân 4 nếu worker hoạt động ở những khoảng thời gian không trùng nhau.
- **Không cộng các peak không cùng thời điểm**. Muốn biết cluster throughput tại thời điểm `t`, cộng **rate của từng worker cùng cửa sổ**.
- Nếu job wall-clock 120 giây, throughput end-to-end là khoảng `1.000.000/120≈8.333` unique records/s, **không phải** `4.000+4.000+3.000+2.000=13.000` items/s.
- Tổng active worker-seconds = 300. Một metric hiệu quả theo active worker-second là `1.000.000/300≈3.333` items/s/active-worker-second. Nó khác cluster wall rate.

Ví dụ là **số giả định để học cách tính**, không phải benchmark đo Spring Batch. Với retry/duplicate rows, tổng output unique keys có thể **nhỏ hơn** tổng writer attempts; phải điều chỉnh tử số theo business contract.

### 4.1. Đường cong throughput theo thời gian

~~~text
throughput
 ^             _________
 |        ____/         \____
 |   ____/                    \___
 |__/                              \__
 +------------------------------------> time
    startup   steady   one slow partition
~~~

Ở đoạn cuối job, nhiều worker đã hoàn tất và chỉ còn một partition nặng; aggregate rate giảm. Đó có thể là **straggler/tail**, không nhất thiết là lỗi CPU hoặc database. Cần xem partition sizes, ownership, skew và thời gian thực tế trước khi autoscale.

## 5. StepExecution counts: nền tảng nhưng không phải nguồn sự thật duy nhất

`StepExecution` trong Spring Batch giữ các số đếm như:

- `getReadCount()`: item reader đọc theo lifecycle của step.
- `getWriteCount()`: item ghi theo writer contribution được framework ghi nhận.
- `getFilterCount()`: item bị processor filter (ví dụ trả `null`).
- `getReadSkipCount()`, `getProcessSkipCount()`, `getWriteSkipCount()`.
- `getCommitCount()` và `getRollbackCount()`.
- `getStatus()` (`BatchStatus`) và `getExitStatus()` (`ExitStatus`).

**Các count có phạm vi `StepExecution`.** Khi restart, một logical partition có thể xuất hiện thêm execution mới với counts riêng. Cộng counts của nhiều attempts để đo business records cuối cùng có thể đếm lại work đã được thử hoặc bỏ sót side effects không transaction. Cần nhìn JobRepository và unique business keys cùng nhau.

### 5.1. `writeCount` không phải committed new-row count

Trong một chunk:

~~~text
Reader:        500 items
Processor:     lọc 30 items
Writer:        nhận 470 items
SQL:           ON CONFLICT DO NOTHING bỏ qua 20 duplicate keys
Business DB:   tạo 450 rows mới

Expected:
  writeCount theo Spring Batch có thể phản ánh 470 writer items.
  New unique rows cho snapshot này = 450.
~~~

Với trigger, multi-table writer, JPA flush, update counts đặc biệt, stored procedures hoặc downstream API, sự khác biệt còn lớn hơn. Đối soát output/ledger hoặc dùng atomic affected-row instrumentation có contract rõ ràng, không gắn tên `business_rows_committed` lên `writeCount`.

### 5.2. Đọc qua API thay vì sửa repository

Trong code quản lý job, sử dụng `JobExplorer`/`JobRepository` theo version để tra cứu `JobExecution` và `StepExecution`. Truy vấn đọc metadata table trong staging có thể hữu ích cho điều tra, nhưng **không sửa trực tiếp `BATCH_STEP_EXECUTION` để ép state**.

Ví dụ read-only cho schema Spring Batch 5.x (kiểm tra bảng/cột theo version đang dùng):

~~~sql
SELECT STEP_EXECUTION_ID,
       JOB_EXECUTION_ID,
       STEP_NAME,
       STATUS,
       READ_COUNT, WRITE_COUNT,
       FILTER_COUNT,
       READ_SKIP_COUNT, PROCESS_SKIP_COUNT, WRITE_SKIP_COUNT,
       COMMIT_COUNT, ROLLBACK_COUNT
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = :jobExecutionId
ORDER BY STEP_EXECUTION_ID;
~~~

**Tính mới của số liệu:** metadata được cập nhật theo lifecycle/transaction/checkpoint; query tại một thời điểm không bảo đảm mọi worker đã commit xong. Độ trễ, clock lệch hoặc worker chết có thể khiến status `STARTED` tồn tại cho tới recovery. Đừng suy “throughput = 0” chỉ vì bảng chưa đổi trong một cửa sổ ngắn.

## 6. Ba loại số đo: counter, timer và gauge

| Loại | Dùng cho | Không nên dùng cho |
|---|---|---|
| **Counter** (đơn điệu trong process) | Số item được quan sát, retry, errors, completed attempts | Current queue depth, số worker đang active |
| **Timer/histogram** | Writer call/chunk/step duration, acquire latency, partition time | Số byte backlog hiện tại |
| **Gauge** | Active workers, pending tasks, Hikari active, queue depth/oldest age | Tổng số work đã xử lý từ đầu hệ thống |

### 6.1. Chọn tên metric không gây hiểu lầm

Một bộ metric ứng dụng có thể đặt:

~~~text
batch.worker.writer.calls
batch.worker.writer.items.attempted
batch.worker.chunk.writer.items.observed
batch.worker.step.duration
batch.worker.chunk.duration
batch.worker.step.errors
batch.worker.active.executions
batch.worker.partition.queue.age
batch.business.unique.keys.committed
~~~

Đây là **tên metric đề xuất**, không phải danh sách metric Spring Batch tự động cấp. Với Prometheus, Micrometer thường chuyển tên thành các dạng `batch_worker_writer_items_attempted_total`, `batch_worker_step_duration_seconds_count` hoặc histogram/summary tương ứng tùy registry và cấu hình distribution. **Quan sát endpoint `/actuator/prometheus` thực tế** thay vì đoán tên xuất ra từ code.

### 6.2. Counter không xóa được các lần thử lại

Nếu một writer đã gọi cho 100 items rồi transaction rollback và retry, counter `writer.items.attempted` có thể tăng 200 trước khi một kết quả commit. Counter ấy hữu ích để phát hiện **wasted work**, nhưng không phải business committed rate.

Nếu metrics chỉ nằm trong memory process, pod crash làm mất những increment chưa được Prometheus scrape. Vì thế business reconciliation/ledger là nguồn sự thật cho tính đúng, còn telemetry là quan sát **best-effort**.

## 7. Đo throughput sau chunk bằng Micrometer

Một thiết kế cơ bản cho **worker step xử lý chunks tuần tự trong mỗi `StepExecution`** có thể dùng `StepExecutionListener` và `ChunkListener`. Listener dưới đây đo:

- Delta `writeCount` sau mỗi **chunk hoàn tất thành công** theo Spring Batch lifecycle.
- Thời gian từ `beforeStep` đến `afterStep` cho mỗi attempt có callback cuối.
- Số chunk bị báo lỗi; không gọi chúng là “records đã mất”.

### 7.1. Worker listener

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.TimeUnit;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.ChunkListener;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;
import org.springframework.batch.core.scope.context.ChunkContext;
import org.springframework.stereotype.Component;

@Component
public class WorkerThroughputMetricsListener
        implements StepExecutionListener, ChunkListener {

    private final MeterRegistry registry;
    private final ConcurrentMap<Long, Long> startedNanos =
            new ConcurrentHashMap<>();
    private final ConcurrentMap<Long, Long> lastWriteCount =
            new ConcurrentHashMap<>();
    private final Counter observedWriterItems;
    private final Counter chunkErrors;

    public WorkerThroughputMetricsListener(MeterRegistry registry) {
        this.registry = registry;
        this.observedWriterItems = Counter.builder(
                "batch.worker.chunk.writer.items.observed")
                .tag("role", "event-worker")
                .register(registry);
        this.chunkErrors = Counter.builder(
                "batch.worker.chunk.errors")
                .tag("role", "event-worker")
                .register(registry);
    }

    @Override
    public void beforeStep(StepExecution execution) {
        Long id = execution.getId();
        if (id != null) {
            startedNanos.put(id, System.nanoTime());
            lastWriteCount.put(id, 0L);
        }
    }

    @Override
    public void afterChunk(ChunkContext context) {
        StepExecution execution =
                context.getStepContext().getStepExecution();
        Long id = execution.getId();
        if (id == null) {
            return;
        }
        long current = execution.getWriteCount();
        Long previous = lastWriteCount.put(id, current);
        if (previous != null && current > previous) {
            observedWriterItems.increment(current - previous);
        }
    }

    @Override
    public void afterChunkError(ChunkContext context) {
        chunkErrors.increment();
    }

    @Override
    public ExitStatus afterStep(StepExecution execution) {
        Long id = execution.getId();
        if (id != null) {
            Long started = startedNanos.remove(id);
            lastWriteCount.remove(id);
            if (started != null) {
                registry.timer(
                        "batch.worker.step.duration",
                        "role", "event-worker",
                        "result", statusTag(execution.getStatus()))
                        .record(System.nanoTime() - started,
                                TimeUnit.NANOSECONDS);
            }
        }
        return null; // Không ghi đè ExitStatus có sẵn.
    }

    private static String statusTag(BatchStatus status) {
        return status == BatchStatus.COMPLETED
                ? "completed" : "not_completed";
    }
}
~~~

Đây là **instrumentation minh họa cho chunk tuần tự theo `StepExecution`**. `afterChunk` được gọi khi chunk được xử lý thành công theo transaction lifecycle; delta `getWriteCount` đo **writer items được StepExecution ghi nhận**, không đếm row database mới. Nếu dùng **multi-threaded chunks trong cùng một `StepExecution`**, hai callbacks có thể chạy đồng thời và phép `getWriteCount()/put()` đơn giản không đảm bảo delta chính xác; phải dùng synchronization/snapshot atomic hoặc instrument **per chunk contribution** theo concurrency model, với kiểm thử race riêng.

**Giới hạn khác:** nếu worker process chết ngay trước `afterChunk` hoặc `afterStep`, metric trong JVM có thể thiếu; nếu tiến trình crash mà business DB đã commit, instrumentation không đủ xác nhận đúng dữ liệu. Nếu một `StepExecution` đã có counts từ checkpoint khi restart theo cách đặc thù, cần kiểm tra giá trị đầu của delta; thiết kế test phải xác minh không đếm lại progress.

### 7.2. Đăng ký listener vào worker step

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

// Trong class @Configuration, các bean phụ thuộc đã được cung cấp:
@Bean
public Step eventWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager businessTransactionManager,
        ItemReader<SourceEvent> reader,
        ItemWriter<SourceEvent> writer,
        WorkerThroughputMetricsListener metricsListener) {

    return new StepBuilder("eventWorkerStep", jobRepository)
            .<SourceEvent, SourceEvent>chunk(
                    500, businessTransactionManager)
            .reader(reader)
            .writer(writer)
            .listener((StepExecutionListener) metricsListener)
            .listener((ChunkListener) metricsListener)
            .build();
}
~~~

`SourceEvent` là DTO/record ứng dụng tự định nghĩa. Đoạn trên chỉ là **wiring snippet**, cần bean reader, writer, datasource và `Job`/manager/worker topology. Nếu reader cũng implement `ItemStream` để checkpoint, bảo đảm Spring Batch nhận đúng interface/lifecycle; đặc biệt với scoped proxy hãy đăng ký reader là loại `ItemStreamReader`/concrete type phù hợp thay vì che nó sau bean type quá chung. Với worker partitioning, reader nên late-bind `ExecutionContext` qua `@StepScope` và không chia sẻ cursor mutable giữa executions.

### 7.3. Đừng gắn partition ID làm metric label vô hạn

Một `StepExecution` remote có thể có tên `eventWorkerStep:partition-0042`; nếu lấy nguyên tên step làm tag cho Prometheus, mỗi job tạo hàng trăm time-series mới. Trong ví dụ, label `role=event-worker` có số giá trị cố định. Giữ `jobExecutionId`, `stepExecutionId`, `partitionName` và `workerInstanceId` trong **structured logs/traces**, hoặc dùng dashboard chi tiết theo event/metadata store riêng.

Nếu cần so throughput theo job/step, dùng tag **logical job/worker step name** có cardinality giới hạn, không dùng full partition-qualified step names một cách mù quáng.

## 8. Đo writer call latency mà không gọi nó là committed throughput

Trong job ghi JDBC, `ItemWriter.write(...)` có thể gọi `executeBatch()` và trả về **trước commit transaction**. Ở JPA, `EntityManager.flush()` có thể thực thi SQL nhưng transaction vẫn còn khả năng rollback. Với remote workers, message ACK và metadata update lại là các ranh giới khác.

Một decorator nhỏ đo thời gian writer method:

~~~java
import java.util.concurrent.TimeUnit;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.batch.item.ItemWriter;

public final class TimedItemWriter<T> implements ItemWriter<T> {

    private final ItemWriter<T> delegate;
    private final Counter attemptedItems;
    private final Timer callTimer;

    public TimedItemWriter(
            ItemWriter<T> delegate, MeterRegistry registry) {
        this.delegate = delegate;
        this.attemptedItems = Counter.builder(
                "batch.worker.writer.items.attempted")
                .tag("role", "event-worker")
                .register(registry);
        this.callTimer = Timer.builder(
                "batch.worker.writer.call.duration")
                .tag("role", "event-worker")
                .description("Latency of ItemWriter.write call")
                .register(registry);
    }

    @Override
    public void write(org.springframework.batch.item.Chunk<? extends T> chunk)
            throws Exception {
        attemptedItems.increment(chunk.size());

        long start = System.nanoTime();
        try {
            delegate.write(chunk);
        } finally {
            callTimer.record(System.nanoTime() - start,
                    TimeUnit.NANOSECONDS);
        }
    }
}
~~~

**Chú ý:**

- `items.attempted` có thể tăng nhiều lần với cùng item khi retry/rollback.
- Timer đo cả lần gọi writer **thành công và thất bại**; có thể thêm error counter/classification.
- Decorator này **chỉ implement `ItemWriter`**. Nếu delegate còn implement `ItemStream`, `ItemStream` lifecycle có thể bị che qua wrapper; cần forward `open/update/close` hoặc đăng ký delegate đúng interface với framework.
- Với worker dùng một writer singleton concurrent, phải kiểm tra thread safety của **delegate**, không mặc định wrapper giải quyết sự an toàn.
- Tên metric `writer.call.duration` **không phải** `business.commit.duration`. Để đo commit cần hook/transaction metrics phù hợp, và để đo business output phải xét **database đã commit**.

### 8.1. Những thời điểm có thể ghi nhận “thành công”

~~~mermaid
sequenceDiagram
    participant W as ItemWriter
    participant D as Business database
    participant J as JobRepository
    participant B as Broker
    W->>D: JDBC batch SQL
    D-->>W: executeBatch trả về
    Note over W,D: Writer-call timer dừng tại đây
    W->>D: COMMIT chunk transaction
    D-->>W: Commit acknowledged
    Note over W,D: Business output theo transaction policy
    W->>J: Metadata/checkpoint theo lifecycle
    W-->>B: Reply / ACK theo transport
~~~

Thứ tự giữa business commit, metadata persistence và ACK **phụ thuộc topology và transaction managers**; sơ đồ nêu các mốc cần phân biệt, không phải cam kết thứ tự áp dụng cho mọi cấu hình. Với business DB và `JobRepository` cùng local transaction, một phần mốc có thể nguyên tử; nếu là hai DB/broker tách biệt, không có atomicity mặc định.

## 9. Một business ledger để đo “đã commit đúng” thay cho writer attempts

Giả sử nguồn có một snapshot các event bất biến. Writer đưa kết quả vào bảng với **unique business key**:

~~~sql
CREATE TABLE source_events (
    snapshot_key VARCHAR(80) NOT NULL,
    event_id     BIGINT NOT NULL,
    tenant_id    VARCHAR(64) NOT NULL,
    amount_cents BIGINT NOT NULL,
    PRIMARY KEY (snapshot_key, event_id)
);

CREATE TABLE processed_events (
    snapshot_key VARCHAR(80) NOT NULL,
    event_id     BIGINT NOT NULL,
    tenant_id    VARCHAR(64) NOT NULL,
    amount_cents BIGINT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (snapshot_key, event_id)
);
~~~

Mỗi `(snapshot_key,event_id)` là một logical business record. Nếu item có thể bị replay:

~~~sql
INSERT INTO processed_events
    (snapshot_key, event_id, tenant_id, amount_cents)
VALUES (:snapshotKey, :eventId, :tenantId, :amountCents)
ON CONFLICT (snapshot_key, event_id) DO NOTHING;
~~~

Với PostgreSQL, `DO NOTHING` khiến duplicate insert có thể ảnh hưởng 0 row; DB không thêm một output key nữa. **Tuy nhiên**, nếu cùng key đến với amount khác, `DO NOTHING` sẽ che khác biệt payload. Trong production phải xác định snapshot bất biến, checksum/version policy và hành vi detect/quarantine khi key tái sử dụng không đúng.

### 9.1. Đối soát số unique business keys

~~~sql
SELECT count(*) AS committed_unique_keys,
       sum(amount_cents) AS committed_amount
FROM processed_events
WHERE snapshot_key = :snapshotKey;
~~~

Với primary key ở trên, `count(*)` tương đương số unique `event_id` trong snapshot. Nếu schema không có uniqueness, phải kiểm tra cả duplicates.

Sử dụng **snapshot đầu vào cố định** để tính expected:

~~~sql
-- Input có nhưng output thiếu:
SELECT event_id, tenant_id, amount_cents
FROM source_events
WHERE snapshot_key = :snapshotKey
EXCEPT
SELECT event_id, tenant_id, amount_cents
FROM processed_events
WHERE snapshot_key = :snapshotKey;
~~~

~~~sql
-- Output không khớp input:
SELECT event_id, tenant_id, amount_cents
FROM processed_events
WHERE snapshot_key = :snapshotKey
EXCEPT
SELECT event_id, tenant_id, amount_cents
FROM source_events
WHERE snapshot_key = :snapshotKey;
~~~

Hai tập đều rỗng là một kiểm tra tốt cho phép biến đổi **identity** minh họa. Với processor biến đổi/filter, phải so với **expected transformed dataset**, không đơn giản so output với raw input. `EXCEPT` so theo set; nếu không có unique constraint, cần kiểm tra multiplicity riêng.

### 9.2. Tính tốc độ hoàn tất có ích

Đối với một snapshot duy nhất, khi dashboard poll count ở `t_1` và `t_2`:

\[
R_{\mathrm{new\ keys}}\approx
\frac{C(t_2)-C(t_1)}{t_2-t_1}
\]

Đây là **ước tính bằng polling output table**, đúng khi tập output tăng đơn điệu, không có delete/overwrite làm thay đổi count và không có job khác dùng cùng snapshot. Không chạy `COUNT(*)` trên bảng khổng lồ mỗi vài giây trong production chỉ để tạo dashboard: dùng audit table/counter theo transaction, change stream hoặc scheduled aggregation với ngân sách rõ ràng.

### 9.3. Metrics sau commit vẫn có giới hạn

Có thể đăng ký transaction synchronization `afterCommit` để tăng counter **sau khi business DB transaction commit**, nhưng:

- Callback trong process có thể không chạy nếu process chết ngay sau database commit.
- Một chunk writer có thể chứa nhiều duplicate `DO NOTHING`, không biết số new rows nếu chỉ nhìn `Chunk.size()`.
- Callback không chứng minh broker/metadata/resource khác đã commit.
- Counter exporter/scraper có thể mất số liệu trong cửa sổ crash.

**Vì vậy, business ledger/output là nguồn xác thực tính đúng; metric sau commit chỉ giúp quan sát gần thời gian thực.** Với nghiệp vụ yêu cầu kế toán chính xác, dùng một ledger/event table được commit cùng business state rồi tổng hợp sau, thay vì lấy in-memory Micrometer counter làm sổ cái.

## 10. Prometheus: tính rate đúng với counters và pod restart

Prometheus là ví dụ phổ biến khi Spring Boot có Micrometer registry/Actuator. Nếu custom counter `batch.worker.chunk.writer.items.observed` được xuất ra thành `batch_worker_chunk_writer_items_observed_total`, query rate:

~~~promql
sum(
  rate(batch_worker_chunk_writer_items_observed_total[5m])
)
~~~

**Tên metric Prometheus phải được kiểm tra trên endpoint thực**, tùy registry naming conventions. Query trên đo **writer-item delta quan sát ở chunk callback**, không phải committed new business-key rate.

### 10.1. Aggregation đúng theo thời gian

Nếu có label `role` và `instance`:

~~~promql
sum by (role) (
  rate(batch_worker_chunk_writer_items_observed_total[5m])
)
~~~

`rate` tính biến thiên counter trong cùng cửa sổ, có xử lý các lần counter reset khi process restart theo thuật toán Prometheus. Sau đó `sum` cộng **cùng khoảng thời gian** giữa các instances. Không viết:

~~~promql
rate(
  sum(batch_worker_chunk_writer_items_observed_total)[5m]
)
~~~

như phép thay thế tương đương: cộng counters qua pods trước khi tính rate có thể làm counter reset, pod churn hoặc metric mất/xuất hiện gây sai lệch. Thực tế PromQL còn yêu cầu cú pháp subquery riêng khi dùng range trên biểu thức; **tính `rate` ở mức series trước, rồi mới aggregate**.

### 10.2. Counter theo lần hoàn tất step không vẽ mượt được

Nếu chỉ increment `batch.worker.step.items.written` **sau khi step hoàn tất**, đồ thị sẽ có spike ở lúc finish rồi bằng 0 khi step đang chạy. Nó không đại diện instantaneous throughput của một worker đang xử lý 60 phút.

Để thấy progress trong lúc chạy, dùng:

- Counter tăng sau mỗi successful chunk, với caveat counts ở phần 7.
- Instrumentation reader/writer per attempt để xem pipeline stage rate (phải gắn nhãn đúng).
- Business ledger/outbox metrics được cập nhật sau commit để theo dõi accepted outcomes.
- Periodic `StepExecution` snapshot kết hợp checkpoint, nhưng không dùng delta thiếu timestamp mà đoán tốc độ.

### 10.3. Counter, gauge và histogram trong PromQL

Một vài truy vấn minh họa (sau khi xác minh metric names):

~~~promql
# Số writer items được ghi nhận trong 15 phút:
sum(increase(batch_worker_chunk_writer_items_observed_total[15m]))

# Tốc độ writer attempts cho mỗi role:
sum by (role) (
  rate(batch_worker_writer_items_attempted_total[5m])
)

# Số worker executions đang hoạt động (nếu có gauge này):
sum(batch_worker_active_executions)
~~~

Histogram p95 writer-call:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, role) (
    rate(batch_worker_writer_call_duration_seconds_bucket[5m])
  )
)
~~~

**Điều kiện:** metric Timer phải được cấu hình xuất histogram buckets phù hợp; nếu chỉ có count/sum, `_bucket` có thể không tồn tại. Không lấy average latency để thay thế p95. Với Micrometer Timer, time unit và suffix `_seconds` phụ thuộc exporter; hãy kiểm tra bằng scrape thực tế.

### 10.4. Hiểu giới hạn dữ liệu bị mất khi pod chết

Giả sử worker commit 100.000 business events rồi chết trước lần scrape tiếp theo. Prometheus có thể không bao giờ nhận tất cả local counter increments. Sau restart, counter mới bắt đầu từ 0. `rate` xử lý reset **trên những mẫu nó nhìn thấy**, không thể phục hồi một increment chưa từng được gửi.

Do đó:

- Dùng counters phục vụ **quan sát xu hướng và cảnh báo**.
- Dùng bảng business output/ledger/JobRepository phục vụ **đối soát chính xác**.
- Với pod ngắn sống dưới scrape interval, cân nhắc push/OTLP/export chiến lược phù hợp, nhưng không coi bất kỳ exporter nào là nguồn sự thật tuyệt đối khi process crash.

### 10.5. Tránh high-cardinality tags

Không dùng:

~~~text
requestId, eventId, jobExecutionId,
stepExecutionId, partitionName có hàng nghìn giá trị,
fileName, raw SQL, input path tùy ý
~~~

làm tags Prometheus trên mỗi item/attempt. Các giá trị ấy phù hợp cho **structured logs/tracing hoặc bảng kiểm soát**, với retention/access controls. Tags nên ổn định: `jobName`/logical `stepRole`, environment, worker role, status category, pool name, retryable error class.

`workerInstanceId`/pod name có thể dùng trong dashboard ngắn hạn phục vụ debug, nhưng pod churn làm series tăng. Khi cần so worker process, dùng platform labels có retention/aggregation policy phù hợp và tránh kết hợp với cả execution/partition ID trên mọi metric.

## 11. Bảng thông số “worker throughput dashboard” nên có gì?

Một dashboard hữu ích không chỉ là một số lớn “records/s”. Nên bố trí theo đường đi của một job:

| Khu vực | Chart/metric | Mục đích |
|---|---|---|
| **Ingress & dispatch** | Job arrivals, partition requests, broker queue age | Có work chờ trước khi worker không? |
| **Worker active** | Active worker executions, active pods/threads | Thực tế dùng bao nhiêu worker slots? |
| **Read/processor** | Read rate, filter rate, process latency | Bottleneck ở input hoặc CPU? |
| **Writer/commit** | Writer attempts/s, successful-chunk item delta/s, writer-call p95, commit latency | Ghi vào DB có chậm không? |
| **Business result** | New unique committed business keys/s, reconciliation mismatch | Throughput **có ích** |
| **Retry/failures** | Rollbacks, retries, skips, deadlocks, failed partitions | Có đang làm lại cùng dữ liệu? |
| **Partition tail** | Active/completed partitions, p95/max partition elapsed | Có straggler không? |
| **Resources** | Hikari pending, DB lock/WAL/IO, GC/CPU, broker redelivery | Scale bị giới hạn bởi đâu? |
| **SLO** | Time-to-first-chunk, job wall-clock, deadline misses | Người dùng nhận kết quả kịp không? |

Một biểu đồ writer attempts/s tăng mạnh trong khi committed unique keys/s không đổi là **dấu hiệu điều tra**: duplicate delivery, retry, `DO NOTHING`, rollbacks hoặc logic thiếu tính idempotency có thể làm app bận mà output mới không tăng.

### 11.1. Quan hệ giữa các rates

Trong một pipeline đơn giản không retry:

~~~text
read items
   ├─ filtered / skipped
   └─ items to writer
          ├─ duplicate / unchanged result
          └─ new committed business output
~~~

Nếu người học thấy `read_rate > write_rate`, cần xem filter/skip và backpressure; không luôn kết luận writer bị nghẽn. Nếu `writer_attempt_rate > read_rate` theo một thời điểm, có thể các rates được tính trên **khác cửa sổ** hoặc writer retries làm phát sinh nhiều attempts.

### 11.2. Phân biệt instantaneous và cumulative views

- **Instantaneous (rolling window):** xem burst, stall, backpressure và recovery.
- **Cumulative per step:** xem tổng số read/write/skip/commit và tiến độ hoàn tất.
- **Cumulative per business snapshot:** biết bao nhiêu unique keys đã được chấp nhận.
- **Job-level wall-clock:** biết pipeline có đáp ứng SLA end-to-end không.

Không dùng cumulative counter dạng đường đi lên để suy throughput tăng nếu chưa lấy `rate`. Đường đếm luôn tăng **không** có nghĩa tốc độ đang tăng.

## 12. Partition skew: worker chậm không nhất thiết do CPU yếu

Trong remote partitioning, `Partitioner` tạo một tập work units. Hai partitions có số ID gần bằng nhau **không có nghĩa** có số row/tốn thời gian tương đương nếu dữ liệu có gaps, độ lớn payload khác nhau, hoặc một partition xử lý nhiều hot customers.

~~~mermaid
gantt
    title Worker execution durations - minh họa
    dateFormat  X
    axisFormat %s
    section Worker A
    P0 : 0, 40
    P4 : 40, 85
    section Worker B
    P1 : 0, 42
    P5 : 42, 90
    section Worker C
    P2 : 0, 120
    section Worker D
    P3 : 0, 35
    P6 : 35, 76
~~~

Biểu đồ Gantt là **timeline giả định**. Worker C giữ partition P2 lâu hơn; các worker khác đã rảnh sau 76–90 giây nhưng job phải đợi tới 120 giây. Trong trường hợp này, **job tail** là vấn đề phân tải, không chỉ rate trung bình.

### 12.1. Các dấu hiệu skew

- Partition p50 hoàn thành sau 30 giây nhưng p99/max mất 180 giây.
- Một worker có readCount thấp nhưng step duration cao: item khó, DB lock hoặc I/O.
- Các workers idle nhiều khi vẫn còn **một partition rất lớn**.
- Các partitions có cùng số row nhưng khác biệt rất lớn về bytes xử lý, SQL complexity hoặc external API latency.
- Một vài tenant/customer keys xuất hiện ở nhiều partitions làm lock contention.

### 12.2. Tính metrics skew

Với `k` partitions đã hoàn thành và các durations `T_i`:

\[
T_{\mathrm{mean}}=\frac{1}{k}\sum_{i=1}^{k}T_i,\qquad
\mathrm{skewRatio}=\frac{\max_i T_i}{\mathrm{median}(T_i)}
\]

`max/median` cho một tín hiệu về tail nhưng không phải chỉ số chuẩn bắt buộc của Spring Batch. Nếu một partition có 100 lần nhiều business rows hơn partition khác, so duration thô **không công bằng**; nên báo cả `duration/unique-record`, payload bytes, retry count và resource wait. Với số partition ít, p99 estimate không ổn định; báo **max** và phân bố thực.

### 12.3. Một đơn vị phân vùng cần giữ tính đúng qua restart

Để làm skew nhỏ hơn, có thể:

1. Chia partitions thành nhiều ranges nhỏ hơn, nhưng **không** tạo hàng triệu `StepExecution` làm metadata/broker quá tải.
2. Chia theo estimated weight (row count/bytes/tenant complexity) thay vì chỉ ID interval.
3. Dùng dynamic work claiming ở tầng thiết kế phù hợp, giữ logical work IDs/idempotency.
4. Tránh hai partitions cùng ghi hot aggregate key nếu có thể chia theo **write ownership**.
5. Đo cost trên **cùng immutable snapshot**, phân tích skew trước khi thay partition plan.

**Cực kỳ quan trọng:** một job đã fail và cần restart thường dựa trên **partition names, `ExecutionContext` và checkpoint đã lưu**. Không đổi `gridSize`/partition plan giữa chừng rồi giả định restart tiếp tục đúng. Tái phân vùng cần chính sách migration/reconciliation riêng.

### 12.4. Distinguish slow partition và slow worker

Nếu cùng partition P7 luôn chậm dù chạy trên pod khác, lỗi có thể do dữ liệu P7/hot key. Nếu mọi partition trên pod B chậm, có thể node throttling, GC, network, DB connection pool cấu hình khác hoặc consumer setup. Cần log/trace:

~~~text
jobExecutionId, stepExecutionId, partitionName,
workerInstanceId, inputRange, inputRows, inputBytes,
stepStartedAt, firstChunkAt, stepEndedAt,
readCount, writeCount, retryCount,
poolWaitMs, dbLockWaitMs, errorCategory
~~~

Không đưa tất cả các ID vào Prometheus labels; giữ correlation chi tiết trong logs/trace hoặc bảng audit của test/operations.

## 13. Worker utilization: bận xử lý hay chỉ đang đợi?

**Utilization** có ít nhất ba nghĩa:

1. **Allocated utilization:** pod/worker process được cấp tài nguyên và đang có assigned `StepExecution`.
2. **CPU utilization:** CPU thực đang tính toán so với quota/cores.
3. **Useful utilization:** thời gian làm việc tạo kết quả hữu ích thay vì idle/retry/wait.

Một pod có CPU 5%, có một worker `STARTED` và Hikari active connection = 1 có thể đang **chờ DB row lock**, không phải “rảnh để nhận thêm job”.

### 13.1. Worker active count

Gợi ý metric:

~~~text
batch.worker.active.executions{role="event-worker"} = 0..N
batch.worker.pending.assignments{role="event-worker"} = ...
batch.worker.idle.slots{role="event-worker"} = ...
~~~

Các gauge này phải được cập nhật khi StepExecution start/finish/fail và khi process restart; cần đối chiếu với broker consumer state/JobRepository vì pod có thể crash trước callback decrement. In-memory gauge ở pod đã chết biến mất, không tự báo sự thật của execution còn `STARTED` trong repository.

### 13.2. Công thức capacity-slot utilization

Nếu cluster có `C` worker slots và quan sát trong khoảng `T`:

\[
U_{\mathrm{slot}}=
\frac{\int_0^T A(t)\,dt}{C\,T}
\]

`A(t)` là số slots đang active tại thời điểm `t`; `0 \le U_{\mathrm{slot}}\le 1` nếu định nghĩa nhất quán. Đây là **slot occupancy**, không phải CPU utilization hoặc tỷ lệ hiệu ứng business đã commit.

Nếu auto-scaling thay đổi `C(t)` theo thời gian, thay mẫu số bằng `\int_0^T C(t)\,dt` để phản ánh allocated slot-seconds thực, không áp một số worker cố định cả run.

### 13.3. Worker có nhiều executions đồng thời

Ví dụ worker pod có 4 consumer threads nhưng JDBC pool max 2; nếu mỗi execution cần ít nhất một connection cho transaction và reader giữ thêm connection, 4 active StepExecutions có thể chỉ khiến nhiều threads **đợi pool**. Từ đó:

- Active executions tăng, CPU vẫn thấp.
- Hikari pending và acquire p95 tăng.
- Throughput không tăng hoặc giảm.
- Nếu xử lý nhiều tenant/key nóng, lock wait còn làm vấn đề tệ hơn.

Đừng suy “CPU thấp nên tăng consumer concurrency”. Kiểm tra **nút thắt thực** ở pool/DB/broker/downstream.

## 14. Phân biệt bottleneck bằng bộ metric song song

Chỉ một số `worker throughput` không trả lời được “tại sao chậm”. Nên đặt rate cùng latency và resource waits:

| Triệu chứng | Dữ liệu cần xem | Khả năng chính |
|---|---|---|
| Read rate thấp, writer rảnh | Source query p95, network/read I/O, reader connection | Source scan hoặc reader bottleneck |
| Process rate thấp, CPU cao | CPU profiles, allocation, GC, processor latency | CPU/serialization/validation |
| Writer-call p95 cao, DB `Lock` waits tăng | pg_blocking_pids, transaction age, hot keys | Row lock contention |
| Writer-call p95 cao, DB WAL/IO saturation | WAL write/sync, disk latency, commit count | DB storage/commit bottleneck |
| Hikari pending tăng, DB CPU thấp | Pool acquire time, cursor hold, REQUIRES_NEW | Pool starvation/long transactions |
| Broker queue age tăng, workers idle | Consumer count, routing, subscriptions, serialization | Worker readiness/transport |
| Retry/error rate tăng, committed unique rate đứng yên | Exceptions, rollback/skip, duplicate checks | Wasted work/retry storm |
| Mọi partitions nhanh trừ một | Partition bytes/rows, DB hotspots, max duration | Skew/straggler |
| CPU throttling tăng khi scale replicas | K8s CPU quotas/node pressure, GC | Pod scheduling/CPU resource |

### 14.1. HikariCP là một nguồn throughput quan trọng

Theo dõi ít nhất:

~~~text
hikaricp.connections.active
hikaricp.connections.idle
hikaricp.connections.pending
hikaricp.connections.acquire
hikaricp.connections.usage
~~~

Tên exporter có thể khác theo registry. Trong metric Prometheus, dấu chấm thường đổi thành dấu gạch dưới; Timer sẽ có suffix `_seconds` hoặc `_seconds_count/_sum` khi xuất Prometheus. Kiểm tra endpoint của môi trường đang chạy.

Nếu `pending > 0` lâu và `acquire p95` tăng:

- Connection có thể bị giữ bởi cursor readers hoặc transaction dài.
- Nhiều `REQUIRES_NEW` có thể mượn thêm connection.
- Một worker process mở nhiều pools (business + metadata) với ngân sách riêng.
- Database có lock wait; tăng pool làm nhiều transaction chờ cùng row.

**Connection pool size không tương đương “số worker tối ưu”.** Với remote partitioning, cộng pools trên toàn bộ replicas, kể cả rolling deployment surge.

### 14.2. PostgreSQL database signals

Một query read-only để xem wait events:

~~~sql
SELECT state,
       wait_event_type,
       wait_event,
       count(*) AS sessions
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY state, wait_event_type, wait_event
ORDER BY sessions DESC;
~~~

Khi nghi row lock blockers:

~~~sql
SELECT pid, application_name, wait_event_type, wait_event,
       pg_blocking_pids(pid) AS blockers,
       now() - xact_start AS transaction_age
FROM pg_stat_activity
WHERE datname = current_database()
  AND cardinality(pg_blocking_pids(pid)) > 0;
~~~

`transaction_age` không phải thời gian chờ lock chính xác. PostgreSQL có thể hiển thị chờ `transactionid` thay vì row lock dễ nhận diện; cần kết hợp SQL/trace/DBA logs để xác định hot key.

Để theo dõi WAL (trên PostgreSQL hỗ trợ `pg_stat_wal` và các field tương ứng):

~~~sql
SELECT wal_records, wal_fpi, wal_bytes,
       wal_write, wal_sync, wal_write_time, wal_sync_time,
       stats_reset
FROM pg_stat_wal;
~~~

Các counter này thuộc **toàn PostgreSQL instance**, không phải metric riêng của một worker. `wal_write_time/wal_sync_time` chỉ hữu ích nếu timing collection được bật theo version/config. Lấy delta giữa hai thời điểm, xác định workload khác cùng DB và không nhầm WAL bytes với payload bytes.

### 14.3. Ít worker hơn đôi khi có throughput cao hơn

Nếu 16 worker cùng update một row tổng hợp, PostgreSQL phải tuần tự hóa các transaction liên quan. Giảm xuống 4 worker có thể:

- Giảm lock queue.
- Rút ngắn transaction/connection hold.
- Giảm deadlocks/retry.
- Tăng tỷ lệ committed unique outcomes trên mỗi CPU-second.

Benchmark phải so **wall-clock và output correctness** của cùng workload; không chỉ chọn cấu hình có số executions active lớn nhất.

## 15. Broker và metadata cũng có thể giới hạn worker throughput

Một worker không thấy request hoặc chờ tải `StepExecution` từ repository có thể có read/write rate bằng 0 dù business DB vẫn khỏe.

### 15.1. Phân tích pipeline remote partitioning

~~~text
manager creates partitions
  -> JobRepository persists StepExecutions
  -> broker accepts request messages
  -> consumer receives request
  -> worker loads StepExecution
  -> reader starts reading business data
  -> writer/chunk transactions commit
  -> worker metadata/reply reaches manager
  -> manager aggregates final job status
~~~

Ghi thời điểm:

- `partitionCreatedAt`, `requestPublishedAt`.
- `requestReceivedAt`, `workerStepStartedAt`.
- `firstChunkAt`, `lastChunkAt`.
- `workerStepFinishedAt`, `replyReceivedAt`, `managerAggregatedAt`.

**Không trừ `System.nanoTime()` từ hai JVM khác nhau.** Để đo cross-process duration, dùng đồng bộ timestamp/trace hoặc hệ thống quan sát trung tâm; dùng `nanoTime` chỉ cho khoảng thời gian trong cùng process.

### 15.2. Queue age và prefetch

Một broker có 1000 messages tồn nhưng chỉ 10 workers active không mặc nhiên cho biết writer chậm: có thể consumer concurrency/prefetch thấp, routing sai hoặc worker chưa subscribe. Ngược lại, prefetch quá cao có thể **giấu backlog trong các consumers**, khiến queue depth trên broker trông thấp nhưng worker memory/in-flight lớn.

Đo ít nhất: **queue age, ready messages, unacked/in-flight, consumer count, redelivery rate, worker active executions**. Với RabbitMQ, Kafka hoặc JMS, mỗi broker có semantics khác nhau; không ghép thẳng `ACK` thành “DB committed” nếu không có contract tương ứng.

### 15.3. JobRepository throughput

Manager có thể tạo quá nhiều partitions rất nhỏ, khiến số `StepExecution` metadata updates/request/replies lớn hơn lợi ích parallelism. Một chiến lược chia 1 triệu rows thành **100.000 partitions** có thể tốn nhiều công tạo execution hơn xử lý dữ liệu. Cần benchmark trade-off giữa **partition granularity** và:

- Metadata database writes/locks/connection pool.
- Broker request/reply throughput.
- Worker startup/context initialization.
- Chí phí job/step restart/aggregation.
- Tail skew và load balancing.

Không chia partitions “càng nhỏ càng tốt” nếu mỗi work unit kéo theo nhiều round trips và transaction metadata.

## 16. Scale-out: speedup và efficiency có nghĩa khi dữ liệu giống nhau

Với cùng immutable input snapshot, output state đã reset hoặc chuẩn bị tương đương và yêu cầu correctness giống nhau:

\[
S(N)=\frac{T(1)}{T(N)},\qquad
E(N)=\frac{S(N)}{N}
\]

Trong đó `T(N)` là **job wall-clock** khi dùng `N` worker slots (hoặc một định nghĩa N nhất quán) và `T(1)` là baseline một slot. Có thể tính tương đương từ throughput nếu tử số là cùng số **unique committed records** và cửa sổ đo tương đương.

### 16.1. Ví dụ speedup giả định

| Worker slots | Job time | Speedup | Efficiency |
|---|---:|---:|---:|
| 1 | 80 phút | 1,00× | 100% |
| 2 | 42 phút | 1,90× | 95% |
| 4 | 23 phút | 3,48× | 87% |
| 8 | 15 phút | 5,33× | 67% |
| 16 | 13 phút | 6,15× | 38% |

Đây là **bảng số minh họa**, không phải benchmark thực. Tốc độ cải thiện giảm dần có thể do serial overhead, DB I/O/WAL, pool/lock, partition skew, metadata overhead hoặc startup/coordination.

**Đừng gọi 16 worker là nhanh hơn 16 lần** chỉ vì có 16 pod. Theo ví dụ, 16 worker giảm thời gian từ 80 xuống 13 phút, chỉ khoảng 6,15 lần; hiệu suất slot khoảng 38%.

### 16.2. Worker throughput vs job throughput

Nếu tổng throughput đang active tăng gần tuyến tính từ 1→8 workers nhưng **job wall-clock** không giảm tương ứng, kiểm tra:

- Startup/connection/broker dispatch overhead.
- Partition tail sau khi nhiều worker đã idle.
- Final aggregation, single-threaded report/merge step.
- Overlap và duplicate work trong các retries.
- Dữ liệu chỉ được xử lý trên một subset partition, các worker còn lại chưa có work.
- End-to-end downstream consumer chậm dù writer đã hoàn tất.

Với job ngắn, startup/warm-up có thể chiếm phần lớn; với job dài, DB resource saturation/tail thường quan trọng hơn. Đo cả **time-to-first-chunk** và **job-complete** nếu SLA yêu cầu.

### 16.3. Hiệu suất chi phí

Khi worker chạy trong Kubernetes hoặc cloud, có thể bổ sung:

\[
\mathrm{cost\ efficiency} =
\frac{\mathrm{unique\ business\ outcomes}}
{\mathrm{allocated\ CPU\!-\!hours\ or\ cost}}
\]

Một cấu hình nhanh hơn 8% nhưng dùng gấp đôi pods có thể kém hiệu quả về chi phí. Tuy nhiên, nếu deadline bắt buộc, chi phí cao hơn có thể là trade-off đúng. Luôn so **throughput, correctness, tail latency và cost** trên cùng workload.

## 17. Worker throughput liên quan trực tiếp đến backpressure

Nếu producer tạo 15.000 work units/giây nhưng cluster chỉ hoàn tất 10.000 business outcomes/giây, backlog có thể tăng gần 5.000/giây nếu không điều tiết (ước lượng với cùng đơn vị và không có drop/expiry). **Không thể giải quyết bằng một queue không giới hạn**.

~~~mermaid
flowchart LR
    A["Producer / manager"] --> Q["Durable bounded backlog"]
    Q --> W["Worker concurrency limit"]
    W --> DB[(DB / downstream)]
    DB -.-> M["Throughput + latency + pressure metrics"]
    M -.-> W
    M -.-> Q
    M -.-> A
~~~

### 17.1. Các hành động khi downstream bão hòa

- Giảm **consumer concurrency/prefetch** để broker giữ pending work thay vì tải vào memory.
- Giới hạn **manager partition dispatch/in-flight requests** theo capacity thật.
- Pause producer/poller hoặc reject/delay *new job requests* theo contract.
- Giữ active chunks được commit/rollback có kiểm soát, không kill cả cluster khi DB lock.
- Dùng bounded retries với backoff/jitter; không để retry storm làm tăng attempted throughput mà giảm useful throughput.
- Chọn active budget bằng số liệu DB/worker thực, không bằng `gridSize` hoặc `maximumPoolSize` đơn lẻ.

### 17.2. Metrics gợi ý điều chỉnh admission

Một policy minh họa có thể chuyển:

~~~text
NORMAL:
    queue age thấp
    committed rate tăng khi thêm worker
    DB pool pending thấp

DEGRADED:
    writer/commit p95 tăng
    DB lock/WAL/IO hoặc pool pending bão hòa
    committed rate không tăng dù active workers tăng

RAMP_UP:
    sau recovery, mở admission dần
    quan sát lại rate + p95 + queue age
~~~

Cần **hysteresis/cooldown** để tránh đóng/mở liên tục khi metric dao động sát ngưỡng. Nếu nhiều API/manager pods tự điều chỉnh độc lập, có thể cùng ramp-up gây thundering herd; muốn giới hạn toàn cụm cần phối hợp shared admission budget.

**Không cắt một `StepExecution` đang chạy để “tối ưu rate” nếu chưa thiết kế stop/restart/idempotency.** Backpressure chủ yếu điều tiết **work mới được nhận hoặc dispatch**, còn work đang chạy cần lifecycle recovery đúng.

## 18. Retry, rollback và restart làm throughput bị “ảo” như thế nào?

Trong hệ thống phân tán, một item có thể được **thử xử lý nhiều lần** nhưng chỉ được phép tạo một business effect. Các mốc:

~~~mermaid
sequenceDiagram
    participant M as Manager
    participant B as Broker
    participant W as Worker
    participant D as Business DB
    participant J as JobRepository
    M->>B: Gửi partition request
    B->>W: Giao request
    W->>D: Writer batch SQL
    D-->>W: COMMIT thành công
    Note over W,J: Worker mất kết nối/crash trước metadata hoặc reply
    W--xJ: Chưa cập nhật đủ tiến độ
    B->>W: Request redelivery / restart
    W->>D: Replay cùng business keys
    D-->>W: Idempotent conflict / no-op
    W->>J: Hoàn tất theo recovery contract
~~~

Ở lần đầu, business DB đã commit `500` rows. Lần hai, writer có thể được gọi lại với cùng `500` items; `writeCount`/attempted metrics có thể tăng, nhưng **new unique keys** không tăng. Ngược lại, nếu writer có side effect `account.balance = balance + delta` mà **không** có event ledger/idempotency guard, replay có thể làm business output tăng **hai lần** dù input không đổi.

### 18.1. Bốn dạng số đếm phải phân biệt

| Count | Ví dụ | Mục đích |
|---|---|---|
| **Attempts** | 1.000 item lần đầu + 500 item replay = 1.500 writer attempts | Đo retry overhead |
| **Step writeCount** | Theo chunk contributions của từng `StepExecution` | Theo dõi tiến độ Batch |
| **DB affected rows** | Lần đầu 1.000, lần replay no-op | Hiểu SQL side effects |
| **Unique business outcomes** | 1.000 keys chính xác | Chứng minh business correctness |

Không cộng `writeCount` qua tất cả `StepExecution` rồi gọi đó là total unique output nếu job đã restart nhiều lần. Một step execution mới là một **attempt/lần chạy**, không phải một business identity mới.

### 18.2. Metrics sau worker crash

Nếu pod chết, các timer/counters chưa scrape có thể biến mất. `StepExecution` metadata cũng có thể chưa phản ánh chunk cuối khi business DB khác transaction manager. Do vậy, một lỗi “metric rate thấp bất thường” không nhất thiết đồng nghĩa database mất data.

Khi chẩn đoán:

1. Kiểm tra pod lifecycle/metrics scrape gap.
2. Đọc JobRepository `JobExecution` và các worker `StepExecution`.
3. Đọc business ledger/output để biết kết quả đã commit.
4. Tìm broker redelivery/reply/ACK timeline.
5. Chỉ sau đó mới quyết định restart/redispatch và cách giải thích rate.

### 18.3. Giữ identifying JobParameters

`JobInstance` được định danh bởi job name và identifying `JobParameters`. Restart đúng một job đã fail cần sử dụng **cùng identifying parameters** và input snapshot/partition plan ổn định. Thêm `run.id` mới chỉ để chạy lại sẽ thường tạo **JobInstance khác**, khiến kết quả business có thể được thực hiện lần hai nếu writer không idempotent.

Ở remote partitioning, một logical partition có thể xuất hiện các `StepExecution` attempts khác nhau. Giữ logical partition name/range, checkpoint, serializer/worker version tương thích và ngăn worker cũ còn chạy gây side effect sau khi request đã được giao lại.

### 18.4. Missing reply không phải missing data

Worker có thể đã commit business DB và cập nhật metadata, nhưng manager không nhận được reply do broker outage. Nếu chỉ nhìn `reply_received_count`, dashboard có vẻ worker “throughput = 0”; kết luận thực tế cần xem **shared repository và business output**.

Đồng thời, một reply `COMPLETED` đến sớm hoặc trùng **không phải** bằng chứng để manager bỏ qua partition thiếu. Manager phải dùng execution identity/correlation, aggregation policy và trạng thái metadata đúng version.

## 19. Benchmark worker throughput có khả năng tái lập

Một benchmark đúng phải giữ **workload tương đương** trong các lần thử. Không dùng một lượt chạy insert mới rồi lượt sau chạy `ON CONFLICT DO NOTHING` và gọi đó là tăng throughput nhờ worker warming.

### 19.1. Cố định input/output và điều kiện

1. **Snapshot bất biến:** cùng tập business keys, payload sizes, distribution theo tenant/hot keys.
2. **Target state:** reset/reseed staging output trước mỗi thử nghiệm hoặc định nghĩa rõ bài toán UPSERT/replay.
3. **Schema:** giữ unique indexes, FK, triggers, business constraints giống nhau.
4. **Runtime:** ghi JDK, Spring Batch/Boot, JDBC driver, broker version, DB settings, CPU/heap.
5. **Resource:** ghi số worker pods, threads/consumer concurrency, Hikari pools, DB instance capacity.
6. **Partition plan:** ghi `gridSize`, actual partition count/ranges và strategy.
7. **Measurement windows:** báo cả cold startup, first successful chunk, steady period và job wall-clock.
8. **Correctness:** so expected unique keys, amount/checksum và trạng thái job.

Nếu dùng multi-threaded step, kiểm tra reader/writer thread safety trước khi benchmark; throughput cao do bỏ sót input là **lỗi**, không phải tăng tốc.

### 19.2. Ma trận thử nghiệm

| Lần | Worker concurrency | Chunk size | Partition count | Câu hỏi |
|---|---:|---:|---:|---|
| A | 1 | 200 | 8 | Baseline tuần tự |
| B | 2 | 200 | 8 | Speedup từ một lên hai worker |
| C | 4 | 200 | 8 | Pool/DB còn khả năng tăng rate? |
| D | 8 | 200 | 16 | Tác động granularity và tail |
| E | 8 | 500 | 16 | Commit/JDBC batching overhead |
| F | 16 | 500 | 32 | Điểm bão hòa, metadata/broker load |
| G | 8 | 500 | 64 | Partition quá nhỏ có tăng overhead không? |

Đây là **kế hoạch thử nghiệm**, không phải kết quả. Muốn xác định tác động của một biến, cần tách thử nghiệm để **chỉ đổi một yếu tố mỗi lần**. Ma trận ở đây gồm cả một số dòng thử granularity, cần so với baseline phù hợp chứ không quy mọi khác biệt cho concurrency.

### 19.3. Record đầy đủ một lần chạy

| Loại kết quả | Dữ liệu cần ghi |
|---|---|
| Identity | `jobName`, identifying params, snapshot, image/driver version |
| Workload | Expected unique IDs, total input bytes, distribution/tenant |
| Settings | Chunk size, worker slots, broker prefetch, pool max, partitions |
| Start/tail | Scheduler/launch, first chunk, last worker, manager complete |
| Worker counts | Per-StepExecution read/write/filter/skip/commit/rollback |
| Throughput | Rolling writer item rate, committed unique keys/s, job wall rate |
| Latency | Writer-call p50/p95, chunk/commit p95, partition p95/max |
| Resources | CPU/GC, Hikari pending/acquire, DB lock/WAL/IO, broker age |
| Correctness | Exact key set, checksum, duplicates/mismatch, restart result |
| Incidents | Retry/rollback counts, deadlocks, worker/pod churn |

### 19.4. Thử skew riêng với random load

Để kiểm tra partition skew, dùng ít nhất hai datasets:

- **Uniform:** các partitions có số rows/bytes tương tự.
- **Skewed:** 60% records thuộc một số tenant hoặc một set khóa có xử lý tốn kém/hot rows.

Nếu cả hai có cùng tổng row count nhưng kết quả khác nhau, hãy phân tích **cost distribution, DB contention và partition plan** trước khi sửa thread pool.

### 19.5. Thực nghiệm với đủ thời gian quan sát

Với job chỉ chạy 10 giây, một Prometheus `rate(...[5m])` có thể làm phẳng toàn bộ burst hoặc không có đủ samples. Sử dụng **event timestamps/trace/job metadata** cho job ngắn, scraper interval phù hợp và end-to-end wall-clock. Với job dài, rolling window rate hữu ích; báo nhiều percentile, không chỉ một lần đo tốt nhất.

**Không chọn throughput cao nhất của một phút bất kỳ làm đại diện toàn job.** Đo nhiều lần, báo median/variance và điều kiện cache/JIT/startup, đồng thời đảm bảo final output giống nhau.

## 20. Kiểm thử công cụ đo: metric đúng quan trọng ngang job đúng

Instrumentation có bug có thể khiến operator tăng worker không cần thiết. Nên kiểm thử cả **ngữ nghĩa số đếm** lẫn resilience:

### 20.1. Một class tính rate thuần Java

Tách phép toán đơn vị giây ra khỏi collector giúp unit test dễ:

~~~java
import java.time.Duration;

public final class WorkerRateCalculator {

    private WorkerRateCalculator() {}

    public static double perSecond(long deltaItems, Duration elapsed) {
        if (deltaItems < 0 || elapsed == null
                || elapsed.isZero() || elapsed.isNegative()) {
            throw new IllegalArgumentException("Invalid counter/window");
        }
        double seconds =
                elapsed.getSeconds() + elapsed.getNano() / 1_000_000_000.0;
        return deltaItems / seconds;
    }
}
~~~

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import java.time.Duration;
import org.junit.jupiter.api.Test;

class WorkerRateCalculatorTest {

    @Test
    void computesRateForKnownWindow() {
        assertThat(WorkerRateCalculator.perSecond(
                36_000, Duration.ofSeconds(30)))
                .isEqualTo(1_200.0);
    }

    @Test
    void refusesInvalidElapsedTimeOrCounter() {
        assertThatThrownBy(() -> WorkerRateCalculator.perSecond(
                100, Duration.ZERO))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> WorkerRateCalculator.perSecond(
                -1, Duration.ofSeconds(5)))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
~~~

Đây là unit test tính toán, **không chứng minh** số `deltaItems` đã được thu đúng từ JobRepository/Micrometer. Nếu counter reset do pod restart, collector phải xử lý reset/khởi tạo stream trước khi đưa delta vào hàm; không gửi số âm rồi lấy giá trị tuyệt đối.

### 20.2. Test listener trên worker step thật

Trong integration test dùng Spring Batch Test/`JobLauncherTestUtils` theo version:

1. Tạo 1.203 input rows, `chunk(500)`, một worker step tuần tự.
2. Cho processor filter một tập xác định, writer ghi output với unique key.
3. Xác nhận số chunk thành công, `StepExecution.readCount/writeCount` và metric `chunk.writer.items.observed` theo semantics đã chọn.
4. Cố tình lỗi giữa chunk để thấy `writer.items.attempted` tăng nhưng business output không tăng tương ứng.
5. Cho một replay `ON CONFLICT DO NOTHING` để xác minh writer item metric và new-row count khác nhau.
6. Dùng `SimpleMeterRegistry` ở test để đọc counter/timer **không cần Prometheus server**.

Ví dụ assert giả mã:

~~~text
expectedNewBusinessKeys = 1_100
writerItemsAfterCommittedChunks = 1_203 - filteredItems

assert output unique business keys == expectedNewBusinessKeys
assert StepExecution.writeCount == writerItemsAfterCommittedChunks
assert Micrometer observed writer items ~ StepExecution.writeCount
assert attempted writer items >= observed writer items
~~~

Đây là **một contract kiểm thử minh họa**, không phải assert chung cho mọi fault-tolerant step. Khi skip/retry/custom writer hoặc process crash, mối quan hệ có thể khác; cần đặt expected số dựa trên fixture và phương thức instrument thật. Trường hợp `StepExecution` không hoàn tất, metric ở `afterStep` có thể có duration nếu callback chạy, nhưng pod crash cứng thì không.

### 20.3. Test multi-threaded chunk instrument không được chạy “mù”

Listener `lastWriteCount.put` ở phần 7 **chỉ giả định một chunk callback tại một thời điểm cho mỗi StepExecution**. Nếu step dùng `TaskExecutor` để chạy concurrent chunks, cần:

- Mô phỏng 2+ chunks hoàn tất ở thứ tự khác nhau.
- Dùng một thiết kế delta atomic hoặc instrument **per-chunk committed contribution** không dựa vào một mutable snapshot.
- Kiểm tra race bằng barrier/latch, không chỉ `Thread.sleep`.
- So observed counter cuối với StepExecution committed writer-item counts trong điều kiện không crash.
- Phân biệt **worker thread** với **remote worker process**; cùng process có thể có nhiều executions.

Tương tự, các gauges active executions cần increment/decrement an toàn ở mọi trạng thái, nhưng không thể kỳ vọng callback decrement khi container bị `SIGKILL`. Monitoring phải phát hiện pod mất qua orchestrator và metadata stale executions.

### 20.4. Test Prometheus labels và reset

- Sau scrape, xác minh metric family và suffix thực tế.
- Giả lập pod restart/counter reset và kiểm tra dashboard `rate` không tạo spike vô lý.
- Xác minh không có `jobExecutionId`/`stepExecutionId`/raw partition ID trong high-cardinality labels.
- Xác minh histogram buckets đã bật trước khi dùng `histogram_quantile`.
- Xác minh rate query dùng **rate trước sum**.
- Giả lập pod sống ngắn hơn scrape interval và báo rõ phần metrics best effort, có business reconciliation.

## 21. Ma trận functional, performance và failure tests

| Test | Input/điều kiện | Điều kiện đạt |
|---|---|---|
| Đọc dữ liệu tuần tự | 1 worker, 1.003 records | Read/processor/write counts và output keys đúng |
| Filter items | Processor trả null có chủ đích | Read > write hợp lý, filterCount chính xác |
| Duplicate keys | `ON CONFLICT DO NOTHING` | Writer item count khác new committed rows đúng kỳ vọng |
| Retry chunk | Transient DB lỗi rồi rollback/retry | Attempts tăng, unique business result không trùng |
| Worker crash trước commit | Kill worker giữa transaction | Recovery đúng, metric may miss nhưng output đúng |
| Worker crash sau commit | Mất reply/metadata trong topology tách resource | Replay idempotent và đối soát |
| Multiple workers | 4 workers song song, range không overlap | Cluster rate cùng-window, không missing/duplicate |
| Partition skew | Một partition có nhiều hot rows | p95/max partition duration phản ánh tail |
| Worker CPU-bound | Processor nặng | CPU/GC metrics phù hợp, DB không bị kết luận sai |
| DB lock-bound | Nhiều partitions update một key | Lock waits cao, commit/business throughput thấp |
| Hikari saturated | Active executions vượt connection budget | Pending/acquire p95 tăng và được cảnh báo |
| Broker backlog | Pause consumer có kiểm soát | Queue age tăng, worker rate giảm, không coi business DB là lỗi |
| Manager metadata bottleneck | Nhiều partitions rất nhỏ | Dispatch/aggregation latency được quan sát |
| Multi-threaded chunks | Nhiều callback một StepExecution | Instrument không lost/double delta hoặc được thay thế |
| Pod churn/Prom reset | Restart pods khi job chạy | Query rate xử lý reset, business ledger vẫn đúng |
| Short job | Job ngắn hơn scrape interval | Dashboard cảnh báo thiếu samples, wall-clock đúng |
| Scale-out | 1/2/4/8/16 workers cùng workload | Speedup, efficiency, DB pressure và correctness |
| Backpressure | Arrival rate > committed rate | Bounded queue/reject/delay, không retry storm |
| Mixed versions | Rolling deploy workers khác version | Serialization/metadata semantics và metric contract tương thích |

**Một benchmark/test được coi đạt** khi có cả metric đủ giải thích và **business output correctness**. Không pass chỉ vì `JobExecution.COMPLETED` hoặc vì dòng throughput cao.

## 22. Cảnh báo và SLO: khi nào throughput thực sự là sự cố?

Một hệ thống có thể cố ý giảm worker rate khi không còn input. **Throughput thấp đơn lẻ không phải lỗi.** Cảnh báo cần dựa vào demand, backlog, tiến độ và deadline:

| Tình huống | Có cảnh báo? | Giải thích |
|---|---|---|
| Không có input/queue, worker throughput = 0 | Thường không | Worker idle đúng |
| Queue age tăng, active worker count = 0 dù có request hợp lệ | Có | Worker không được dispatch/consumer chưa sẵn sàng |
| Queue backlog lớn, active workers cao, committed rate thấp | Có | Downstream choke/retry/lock |
| Writer attempts tăng, unique business keys/s gần 0 | Có | Wasted work hoặc replay/duplicate storm |
| Một partition tail kéo dài quá SLO | Có | Straggler làm job trễ |
| Worker pod restart và counter reset | Có thể có alert lifecycle | Không nhầm reset với sụt business output |
| Job hoàn tất đúng hạn, p95 spike ngắn | Tùy error budget | Không alert quá nhạy từng dao động |
| Committed unique rate cao nhưng mismatch dữ liệu | **Báo lỗi dữ liệu ngay** | Correctness quan trọng hơn rate |

### 22.1. SLO theo job hay theo workers?

Ví dụ SLO **do ứng dụng định nghĩa**, không phải mặc định Spring Batch:

> 99% job thuộc nhóm `daily-ledger` được hoàn tất và đối soát trong 30 phút kể từ thời điểm scheduler accepted request, với zero missing/duplicate business keys theo snapshot.

Worker throughput là **leading indicator** cho SLO, không phải SLO cuối cùng. Một job nhỏ có thể hoàn tất nhanh dù workers đạt rate thấp; một job lớn có thể có rate cao nhưng vẫn trễ do startup/partition tail/aggregation.

Một hệ thống có thể có hai SLO:

- **Service-level:** queue wait p95, time to first chunk, end-to-end job completion và deadline misses.
- **Data correctness:** exact expected key set/checksum, skip policy, idempotency/restart consistency.

Nếu business cần dữ liệu đúng, **không** đặt mục tiêu throughput khiến team chấp nhận skip thầm lặng hay bỏ unique constraints.

### 22.2. Alert dựa vào thiếu tiến độ

Một cảnh báo kiểu “no progress” hợp lý hơn “rate < 100”:

~~~text
IF valid_pending_work > 0
AND active_workers > 0
AND committed_business_progress_delta == 0
FOR a configured observation window
THEN alert "Worker/DB pipeline stalled"
~~~

Ngưỡng cụ thể phải dựa vào job profile. Với một operation có transaction 10 phút, không có progress mỗi 30 giây có thể bình thường; cần theo dõi **in-flight** và latency. Với job 15 giây, cửa sổ 10 phút làm cảnh báo đến quá trễ.

### 22.3. Phân biệt báo động hiệu năng và dữ liệu

Một worker `writeCount` tăng đều nhưng checksum output sai phải được coi là **data-integrity incident**. Ngược lại, một worker chậm do input có record 20 MiB có thể là performance issue được chấp nhận nếu SLA vẫn đạt.

## 23. Runbook: Worker throughput giảm bất thường

### Bước 1 — Chốt metric đang được nhìn

Xác nhận dashboard là `writer.items.attempted/s`, `StepExecution.writeCount/s`, DB affected-row rate, unique committed business keys/s, hay bytes/s. Nếu chỉ có một số “records/sec”, **không ra quyết định scale ngay**.

### Bước 2 — Xác định demand và mốc thời gian

Kiểm tra nguồn có đang còn input, manager có phát partition requests hay không, broker queue age và `JobExecution` đang ở trạng thái nào. Với worker pod vừa khởi động, phân biệt **startup/warm-up** với sustained processing. Kiểm tra run window/cửa sổ PromQL có đủ mẫu không.

### Bước 3 — Xác định vấn đề local hay toàn cụm

So worker instances:

- Nếu chỉ một worker chậm với mọi partitions, xem CPU throttling, heap/GC, connection pool và node/network.
- Nếu một partition chậm trên nhiều workers, xem dữ liệu skew/hot keys.
- Nếu toàn cluster cùng chậm, xem shared DB/broker/JobRepository/resource contention.

Không dựa vào peak rate từng worker để kết luận cluster đã tăng throughput.

### Bước 4 — So sánh attempted, step và committed throughput

Nếu attempts cao nhưng business output thấp:

- Kiểm tra retry/rollback, duplicate delivery, `ON CONFLICT DO NOTHING`, skipped records.
- Đọc `StepExecution` counts/status và business ledger theo cùng snapshot.
- Kiểm tra mất ACK/reply và worker crash trước/sau commit.
- Nếu business commit có outcome không chắc chắn, **đối soát** trước khi dispatch lại.

### Bước 5 — Phân tích bottleneck theo stage

| Nơi có độ trễ | Kiểm tra đầu tiên |
|---|---|
| Reader/source | Query/read p95, I/O, snapshot selectivity |
| Processor | CPU, GC, JSON/regex/serialization |
| Writer | JDBC batch call p95, SQL plan, unique constraints |
| Transaction commit | WAL sync/IO, chunk size, rollback |
| DB locks | `pg_stat_activity`, `pg_blocking_pids`, hot keys |
| Pool | Hikari pending, acquire p95, connection hold |
| Broker | Consumer readiness, routing, prefetch, queue age |
| Metadata | JobRepository DB waits, partition count/granularity |
| Manager tail | Last partition, step aggregation, slowest worker |

### Bước 6 — Hạn chế retry storm và quá tải

Nếu DB đang bão hòa, **giảm worker concurrency/prefetch hoặc pause dispatch work mới**, giữ admission/queued work có durable state. Dùng bounded retry/backoff/jitter thay vì tạo thêm threads; không tăng Hikari pool vô hạn khi các transactions đang chờ cùng hot row.

### Bước 7 — Kiểm tra reader/writer thread safety và restart

Multi-threaded chunk step có thể chia sẻ mutable reader; remote partitioning cần reader `@StepScope` theo `StepExecution` và shared durable `JobRepository`. Không chỉnh partition plan/identifying parameters giữa restart; không dùng random `run.id` để che `FAILED` job.

### Bước 8 — Đối soát output

So exact business keys/checksum/totals với input snapshot. Nếu chỉ có count bằng nhau, vẫn có nguy cơ **một key bị lặp và key khác bị thiếu**. Kiểm tra các exceptions, skips và inconsistent duplicate payloads trước khi báo job hoàn tất.

### Bước 9 — Thử một thay đổi tại một thời điểm

Nếu bottleneck DB write, thử chunk/JDBC batch size/worker concurrency một cách có kiểm soát. Nếu bottleneck skew, thử partition weighting. Nếu bottleneck broker, thử consumer/dispatch settings. Ghi throughput *và* job wall-clock *và* correctness ở mỗi lượt.

### Bước 10 — Cập nhật capacity và alert

Lưu baseline `committed_unique_keys/s`, max partition duration, writer p95, pool pending, DB waits, broker age và resource cost theo loại job. Thêm regression test cho root cause và điều chỉnh SLO/alert theo workload thật.

## 24. Những sai lầm đo Worker throughput thường gặp

| Sai lầm | Vì sao sai | Cách thay thế |
|---|---|---|
| `writeCount` = số business rows mới | Duplicate/upsert/trigger/rollback làm lệch | Unique business key ledger và đối soát |
| Cộng các worker peak khác thời điểm | Không phải cluster throughput tại cùng một thời điểm | Cùng-window rate rồi `sum` |
| Cộng `writeCount` qua restart rồi coi là unique | Mỗi attempt có counts riêng | Logical partition + business reconciliation |
| Dùng `afterWrite` như commit confirmation | Callback trước chunk commit | Quan sát chunk/transaction lifecycle và DB output |
| Gọi `EntityManager.flush()` là COMMIT | SQL có thể flush rồi rollback | Commit/transaction metrics riêng |
| Gắn `stepExecutionId` vào mọi Prometheus labels | Cardinality tăng theo jobs/partitions | Low-cardinality tags, details trong logs |
| Dùng `rate(sum(counter))` | Pod resets/churn gây sai lệch; cú pháp cũng không tương đương | `sum(rate(counter[window]))` |
| Đọc counter tích lũy như rate | Đường luôn tăng dù tốc độ giảm | `rate`/`increase` theo window |
| Coi pod crash metric gap là mất data | Scrape best effort, business DB có thể commit | Repository/ledger reconciliation |
| Tăng worker vì CPU thấp | Worker có thể chờ DB/locks/pool | DB wait/Hikari/queue metrics |
| Tăng `gridSize` là tăng active workers | Partitioner plan ≠ consumer concurrency | Đo actual active executions |
| Dùng một worker nhanh nhất làm baseline | Skew và tail quyết định job completion | p95/max partition, job wall-clock |
| So lần INSERT mới với lần duplicate no-op | Không cùng workload | Reset/reseed staging target |
| Bỏ SQL uniqueness để benchmark nhanh | Mất idempotency/correctness | Giữ constraints business |
| Gọi ACK rate là throughput business | ACK khác transaction commit | Business outcome metrics |
| Đo histogram p95 khi chưa bật bucket | Query trả trống hoặc không chính xác | Kiểm tra `_bucket`, registry config |
| Coi metric name ví dụ là metric mặc định | Version/registry đặt tên khác | Inspect Actuator/Prometheus endpoint |
| Để một pod làm cả manager và worker trong test rồi gọi là remote E2E | Không test process/network boundaries | Multi-process test với shared metadata |
| Chỉ xem CPU/heap, bỏ metadata/broker | Nút thắt ở dispatch/JobRepository | Full-pipeline dashboard |

## 25. Checklist xây dựng dashboard Worker throughput

- [ ] Xác định tử số: read, processed, writer attempts, StepExecution writeCount, DB affected rows hay committed unique business keys.
- [ ] Ghi rõ mẫu số: worker active time, step elapsed, job wall-clock hay allocated worker-seconds.
- [ ] Đo đồng thời items/s và bytes/s nếu kích thước item thay đổi đáng kể.
- [ ] Không đặt tên `committed` cho counter ghi trong `ItemWriter.write` trước COMMIT.
- [ ] Mô tả chính xác semantics của `ChunkListener.afterChunk` và transaction manager.
- [ ] Có metric attempted writer calls và observed committed-step writer items riêng.
- [ ] Có business ledger/output để đối soát unique keys và checksum sau restart.
- [ ] Có `StepExecution` read/write/filter/skip/commit/rollback/status theo lifecycle.
- [ ] Có log/trace `jobExecutionId`, `stepExecutionId`, logical partition và worker identity.
- [ ] Không đưa execution/partition/request IDs có cardinality cao lên mọi Prometheus time series.
- [ ] Query PromQL dùng `rate` trước `sum` và đúng counter resets/scrape interval.
- [ ] Đã bật histogram buckets trước khi hiển thị p95 từ `histogram_quantile`.
- [ ] Đo worker active/idle slots và worker pod count khác nhau.
- [ ] So worker rates trên **cùng cửa sổ thời gian**, không cộng peaks khác thời điểm.
- [ ] Theo dõi p50/p95/max partition duration và slowest partition cho tail.
- [ ] Biết phân biệt data skew với worker/node chậm bằng workerInstanceId/partitionName logs.
- [ ] Có Hikari active/pending/acquire/usage, DB lock/WAL/IO và broker queue age.
- [ ] Phân biệt remote partitioning với remote chunking trong chỗ đặt reader metric.
- [ ] Có speedup/efficiency và job wall-clock trên cùng immutable snapshot.
- [ ] Dùng target output state tương đương khi benchmark, không so INSERT với duplicate no-op.
- [ ] Có retry/rollback/redelivery metrics, không lẫn attempts với unique business work.
- [ ] Worker crash không làm dashboard được coi là nguồn dữ liệu kế toán.
- [ ] Có backpressure khi backlog tăng và useful throughput không tăng.
- [ ] Đã test multi-threaded step callback races nếu instrument cùng `StepExecution`.
- [ ] Đã test pod churn/counter reset và job ngắn hơn scrape interval.
- [ ] Alert chỉ bật khi có pending demand/SLO risk, không báo lỗi vì worker idle hợp lệ.
- [ ] Có runbook phân biệt reader, processor, writer, DB, broker, metadata và partition tail.

## 26. Bài tập thực hành

### Bài tập 1 — Tính những rate khác nhau

Một worker thực hiện 40.000 writer attempts trong 20 giây. Có 4.000 attempts là retry, 2.000 rows bị `ON CONFLICT DO NOTHING` bỏ qua; cuối cùng tạo 34.000 unique new rows hợp lệ. Tính attempted writer rate và new committed business rate, giải thích khác nhau do những nhóm event nào. Cho biết vì sao **chỉ từ writeCount** có thể không suy được cả hai số.

### Bài tập 2 — Cộng rates đúng thời điểm

Worker A có 3.000 items/s trong `[0,10s)` nhưng sau đó idle. Worker B idle ở `[0,10s)` rồi chạy 4.000 items/s trong `[10,20s)`. Tính cluster rate trong hai cửa sổ và average 20 giây. Giải thích vì sao cộng đỉnh `3.000+4.000=7.000` không đại diện một thời điểm nào.

### Bài tập 3 — Instrument worker step

Thêm `WorkerThroughputMetricsListener` vào một worker step chunk-oriented tuần tự, dùng `SimpleMeterRegistry` trên test. Chạy 1.203 items với `chunk(500)`, processor filter 23 items và writer idempotent. Kiểm tra counter observed writer items, `StepExecution.writeCount`, số chunks và output unique keys. Thử duplicate replay và phân biệt business result với writer-item metric.

### Bài tập 4 — Thử multi-threaded step

Giữ một `StepExecution` nhưng cấu hình nhiều chunk threads (sau khi kiểm tra thread safety reader/writer). Dùng barrier/latch để buộc hai chunks hoàn tất gần nhau và quan sát giới hạn của listener `lastWriteCount.put`. Thiết kế cách instrument per-chunk contribution an toàn, so tổng cuối với committed-step writer items và ghi cảnh báo về concurrent callbacks.

### Bài tập 5 — Tạo dashboard PromQL

Từ metric `batch_worker_chunk_writer_items_observed_total`, viết PromQL cho: overall rate 5 phút, rate theo role, số item trong 15 phút, và p95 writer-call duration với histogram buckets. Kiểm tra metric names trên endpoint thực, giả lập pod restart và chứng minh `rate` được tính trước `sum`.

### Bài tập 6 — Partition skew

Tạo tám partitions, bảy partition mỗi cái 10.000 rows và một partition 100.000 rows. Chạy 4 workers, đo partition elapsed, worker active/idle slots, max/median ratio và total job time. Chọn chiến lược reweight/repartition cho **job instance mới** và giải thích vì sao không đổi partition plan tùy ý giữa restart.

### Bài tập 7 — Hot row và Hikari pool

Cho 80% events cập nhật một aggregate row trong PostgreSQL. So throughput/lock waits/Hikari pending khi worker concurrency là 1/2/4/8. Sau đó chuyển sang append-only events và aggregate theo write key riêng. Đánh giá **committed unique outcomes/s** và correctness, không chỉ attempted calls.

### Bài tập 8 — Remote partitioning end-to-end

Khởi chạy manager, shared JDBC JobRepository, broker thật và ít nhất hai worker processes. Ghi correlation `jobExecutionId/stepExecutionId/partitionName/workerInstanceId`. So `JobExplorer` step counts, broker ACKs, business output exact key set và worker active rates. Thử worker process crash giữa chunk và sau business commit, xác minh replay idempotent.

### Bài tập 9 — Scale-out efficiency

Với bảng `T(1)=80` phút, `T(2)=42`, `T(4)=23`, `T(8)=15`, `T(16)=13`, tính `S(N)` và `E(N)`. Đề xuất mức worker tối ưu khi có SLO 20 phút và chi phí tính theo CPU-hours; nêu giả định cần đo trước khi quyết định.

### Bài tập 10 — Ngắn vs dài

So một job có 10.000 items và một job có 10 triệu items, cùng worker startup 25 giây và steady processing capacity như nhau. Giải thích tại sao time-to-first-chunk là chỉ số quan trọng hơn với job ngắn và tại sao database saturation/tail quan trọng hơn với job dài.

### Bài tập 11 — Metrics bị mất sau SIGKILL

Worker commit 20.000 rows rồi bị `SIGKILL` trước lần Prometheus scrape. Hãy mô tả điều gì xảy ra với in-memory counters, `StepExecution` metadata, broker reply và business DB theo từng topology. Thiết kế cách reconcile để không báo thiếu dữ liệu hoặc phát lại tạo double effect.

### Bài tập 12 — Incident runbook

Một dashboard báo:

~~~text
active_worker_executions: 32 -> 64
writer_attempts/s:       40k -> 82k
business_unique_keys/s:  35k -> 31k
Hikari pending:           0 -> 70
PostgreSQL Lock waits:    tăng mạnh
oldest_queue_age:         1m -> 18m
rollback/retry:           tăng mạnh
~~~

Hãy xác định đây có phải scale-out thành công không. Viết runbook ưu tiên **giảm admission/worker pressure**, tìm hot rows, kiểm tra transaction/pool, xác nhận input snapshot/output unique keys và lựa chọn điểm rollback cấu hình. Nêu tại sao mở thêm 64 workers không phải phép khắc phục đáng tin.

### Câu hỏi tự kiểm tra

- Worker throughput khác job end-to-end throughput như thế nào?
- `StepExecution.writeCount` có phải số row mới commit không?
- Vì sao nên tính `sum(rate(counter[window]))` thay vì cộng các worker peaks?
- Một worker có CPU thấp và active StepExecution có thật sự idle không?
- Vì sao p95/max partition duration có ích hơn mean khi job bị straggler?
- Broker ACK có bảo đảm business DB commit không?
- Vì sao restart cùng logical partition có thể xuất hiện `StepExecution` mới?
- Counter reset khi pod restart có bảo đảm không mất telemetry chưa scrape không?
- Cần điều kiện gì trước khi dùng `histogram_quantile`?
- Vì sao tăng 16 workers thường không giúp đạt 16× speedup?
- Nếu output `COUNT(*)` bằng expected, đã đủ xác nhận exact business key set chưa?
- Khi nào throughput thấp **không nên** tạo alert?

## 27. Tổng kết

**Worker throughput** là một tập các phép đo cần gắn với **đơn vị công việc, thời gian và transaction boundary**. Trong Spring Batch, `StepExecution.readCount/writeCount` và callback listener giúp quan sát tiến độ mỗi worker/partition, nhưng không tự thay thế được số **business keys mới đã commit**. Khi job chạy phân tán, còn phải xét broker dispatch/reply, shared `JobRepository`, retries, duplicates, worker/pod churn và slowest partition.

Để đánh giá đúng khả năng mở rộng, hãy kết hợp **rolling worker rate, active worker slots, partition skew/tail, writer/commit p95, Hikari/DB/broker pressure, job wall-clock và business reconciliation**. Tính aggregate throughput bằng cùng-window rates, đo scale-out speedup/efficiency trên cùng snapshot, đừng dùng một đỉnh items/s hay số pod để quyết định kiến trúc.

**Mục tiêu cuối cùng là throughput hữu ích bền vững: nhiều kết quả nghiệp vụ hợp lệ hơn trong thời gian và ngân sách tài nguyên cho phép, không làm sai dữ liệu khi worker retry, crash hoặc restart.**
