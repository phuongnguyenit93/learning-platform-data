# Throughput theo chunk trong Spring Batch

## 1. Throughput theo chunk là gì?

Trong Spring Batch Core Processing, các Step dạng **chunk-oriented** xử lý dữ liệu theo từng nhóm item: đọc, xử lý, ghi và commit transaction. Khi tối ưu hiệu năng, một câu hỏi thường gặp là: **Mỗi chunk mất bao lâu, và toàn bộ Step xử lý được bao nhiêu item trong một giây?**

**Throughput** là tốc độ hoàn thành một lượng công việc trong một khoảng thời gian. Đối với Spring Batch, có thể quan sát throughput ở nhiều mức:

- **Input throughput:** số item được đọc thành công trên một giây.
- **Output throughput:** số item được Step ghi nhận là đã ghi trên một giây.
- **Chunk throughput:** số vòng xử lý chunk hoàn thành trên một giây.
- **Commit throughput:** số transaction commit được Step ghi nhận trên một giây.
- **End-to-end throughput:** tổng số item nghiệp vụ hoàn tất chia cho thời gian chạy từ đầu đến cuối của Job hoặc Step.

Các chỉ số này liên quan nhưng **không đồng nhất**. Một chunk có thể đọc 500 item, lọc 30 item và ghi 470 item. Một chunk khác có thể retry, rollback, hoặc không có item để ghi. Đo riêng số chunk không cho biết tổng sản lượng đầu ra; đo riêng số item cũng không cho biết chi phí transaction.

Ví dụ một Step hoàn thành việc nhập 120.000 item trong 40 giây:

~~~text
Job: importOrdersJob
Step: importOrdersStep
Chunk size: 500

Read:  120.000 item
Write: 117.000 item
Filter:  3.000 item
Wall-clock duration: 40 giây

Input throughput : 120.000 / 40 = 3.000 item/giây
Output throughput: 117.000 / 40 = 2.925 item/giây
~~~

Đây là throughput trung bình của toàn bộ lần thực thi Step. Để biết vì sao tốc độ thấp hoặc biến động, cần đo thêm **thời lượng từng chunk**, **số transaction commit**, **rollback**, **thời gian đọc/ghi** và **mức sử dụng tài nguyên**.

Bài này hướng dẫn cách định nghĩa, đo, phân tích và cải thiện throughput theo chunk bằng những công cụ có sẵn trong Spring Batch 5.x, Spring Boot 3.x và Micrometer, đồng thời giải thích những sai lầm dễ gặp trong benchmark.

## 2. Vòng đời chunk và những điểm có thể đo

Xét Step:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, OrderOutput> processor,
        ItemWriter<OrderOutput> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, OrderOutput>chunk(500, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

Với **chunk size = 500**, Spring Batch cố gắng thu thập một nhóm tối đa 500 item đầu vào cho mỗi vòng chunk, xử lý chúng rồi ghi kết quả trong ranh giới transaction do Step quản lý. Chunk cuối có thể nhỏ hơn nếu reader hết dữ liệu.

~~~text
            Bắt đầu chunk
                  |
             Mở transaction
                  |
       +----------v----------+
       | ItemReader          |  Chi phí đọc file / database / API
       +----------+----------+
                  |
       +----------v----------+
       | ItemProcessor       |  Chi phí tính toán / validate / map
       +----------+----------+
                  |
       +----------v----------+
       | ItemWriter          |  Chi phí SQL batch / ghi file / mạng
       +----------+----------+
                  |
       +----------v----------+
       | Checkpoint, metadata|  Lưu ExecutionContext / StepExecution
       +----------+----------+
                  |
                Commit
                  |
             Kết thúc chunk
                  |
             Chunk kế tiếp
~~~

Có ít nhất ba lớp thời gian:

1. **Thời gian từng thao tác:** reader, processor, writer và các lời gọi I/O cụ thể.
2. **Thời gian chunk:** thời gian từ trước khi xử lý chunk đến khi chunk hoàn tất. Với callback **ChunkListener**, có thể đo từ **beforeChunk** đến **afterChunk** cho trường hợp thành công.
3. **Thời gian Step/Job:** thời gian thực tế từ bắt đầu đến kết thúc, bao gồm khởi tạo, mở/đóng tài nguyên, transaction, chunk, listener và overhead khác.

Một Step xử lý rất nhanh ở processor nhưng commit chậm vẫn có throughput thấp. Ngược lại, tăng chunk size có thể giảm tần suất commit nhưng làm chunk giữ transaction và bộ nhớ lâu hơn.

### Vì sao commit count không thể thay thế số chunk?

**StepExecution.getCommitCount()** ghi nhận số transaction commit mà Step quản lý. Trong cấu hình đơn giản nó thường có liên hệ chặt với chunk processing, nhưng có thể bao gồm vòng xử lý kết thúc dữ liệu hoặc hành vi riêng của Step. Ngoài ra, rollback, retry, Tasklet và restart làm cho cách suy diễn đơn giản trở nên không chắc chắn.

Khi cần **số chunk thành công**, hãy đếm callback **afterChunk** của những chunk thuộc phạm vi quan tâm. Khi cần **số commit theo framework**, dùng **getCommitCount()**. Không đặt hai tên chỉ số này như thể chúng luôn bằng nhau.

## 3. Công thức throughput và cách chọn mẫu số

### 3.1. Throughput theo item

Với một khoảng quan sát có độ dài **Δt** giây:

~~~text
readThroughput  = ΔreadCount  / Δt   (item/giây)
writeThroughput = ΔwriteCount / Δt   (item/giây)
~~~

Dấu **Δ** nghĩa là hiệu giữa giá trị ở cuối và đầu khoảng quan sát của **cùng StepExecution**.

Ví dụ:

| Thời gian | readCount | writeCount | commitCount |
| --- | ---: | ---: | ---: |
| 10:00:00 | 2.000 | 1.900 | 10 |
| 10:00:20 | 6.000 | 5.700 | 30 |

Trong 20 giây:

~~~text
readThroughput  = (6.000 - 2.000) / 20 = 200 item/giây
writeThroughput = (5.700 - 1.900) / 20 = 190 item/giây
commitRate      = (30 - 10) / 20 = 1 commit/giây
~~~

**Read throughput** cho biết tốc độ đọc thành công. **Write throughput** cho biết số item writer được framework ghi nhận. Khác biệt có thể đến từ filter, skip, hoặc cách Step được cấu hình. Không kết luận mất dữ liệu chỉ vì read throughput lớn hơn write throughput.

### 3.2. Throughput theo chunk

Nếu quan sát được **C** chunk hoàn thành thành công trong **Δt** giây:

~~~text
chunkThroughput = C / Δt                   (chunk/giây)
averageChunkRate = Δt / C                (giây/chunk)
~~~

Ví dụ: 40 chunk hoàn tất trong 20 giây tương đương **2 chunk/giây**.

Cần lưu ý **đơn vị chunk khác đơn vị item**. Khi một chunk chứa 100 item còn chunk khác chỉ chứa 20 item, mỗi chunk đều đóng góp một đơn vị vào chunk throughput, nhưng khối lượng công việc khác nhau.

### 3.3. Thời lượng từng chunk

Với mỗi chunk hoàn tất, đo thời lượng thực hiện:

~~~text
chunkDuration = timeAfterChunk - timeBeforeChunk
~~~

Sau khi thu thập nhiều mẫu, xem:

- **p50:** trung vị thời lượng chunk.
- **p95:** mức thời lượng mà khoảng 95% chunk không vượt quá trong mẫu quan sát.
- **p99:** nhận biết nhóm chunk chậm nhất.
- **max:** chunk chậm nhất từng ghi nhận trong khoảng đo.
- **count:** số mẫu chunk đã thu thập.

Một Step có throughput trung bình tốt nhưng p99 tăng mạnh có thể gặp database lock, GC pause hoặc độ trễ I/O thất thường.

### 3.4. Throughput end-to-end

Nếu Step hoàn tất **W** item đầu ra hợp lệ trong **T** giây từ lúc bắt đầu đến khi kết thúc:

~~~text
endToEndWriteThroughput = W / T
~~~

Dùng thời gian **wall-clock**, không phải tổng thời gian CPU. Chỉ số này phản ánh mức năng suất người dùng thực sự nhận được, bao gồm đọc, xử lý, ghi, commit và các overhead trong quá trình chạy.

Trong Job nhiều Step, phải xác định phạm vi: thời gian riêng của một Step khác với thời gian toàn bộ Job. Với Job có nhiều Step chạy song song, **cộng thời lượng từng Step** không bằng thời gian thực đã trôi qua; các Step có thể overlap.

### 3.5. So sánh các thước đo

| Metric | Công thức hoặc nguồn | Phù hợp khi |
| --- | --- | --- |
| **Read items/s** | ΔreadCount / Δt | Chẩn đoán khả năng lấy dữ liệu |
| **Written items/s** | ΔwriteCount / Δt | Đo năng suất ghi của Step |
| **Completed chunks/s** | Số afterChunk thành công / Δt | Quan sát nhịp hoàn tất chunk |
| **Commits/s** | ΔcommitCount / Δt | Quan sát nhịp transaction |
| **Chunk duration** | afterChunk - beforeChunk | Tìm chunk chậm, độ trễ p95/p99 |
| **End-to-end items/s** | Tổng item đầu ra / wall-clock Job hoặc Step | So sánh các lần benchmark |
| **Rollback count** | StepExecution.getRollbackCount() | Giải thích giảm throughput do lỗi giao dịch |

Không sử dụng một thước đo duy nhất để quyết định chunk size tối ưu.

## 4. Chi phí cố định mỗi chunk và chi phí theo item

Một mô hình đơn giản giúp hiểu trade-off:

~~~text
T_total ≈ N × t_item + ceil(N / K) × t_chunk_fixed
~~~

Trong đó:

- **N:** số item đầu vào.
- **K:** chunk size.
- **t_item:** chi phí trung bình để đọc, xử lý và ghi một item.
- **t_chunk_fixed:** chi phí trung bình cố định của mỗi chunk, chẳng hạn bắt đầu transaction, ghi metadata và commit.

Theo mô hình này, **K lớn hơn** làm giảm số lần trả chi phí cố định. Ví dụ với N = 1.000.000 và overhead giả định 10 ms mỗi chunk:

~~~text
K = 100:
  ~10.000 chunk × 10 ms = ~100 giây overhead cố định

K = 500:
  ~2.000 chunk × 10 ms = ~20 giây overhead cố định

Tiết kiệm mô hình: khoảng 80 giây overhead
~~~

Tuy nhiên, đây chỉ là **mô hình tư duy**. Thời gian thực tế không tuyến tính vì:

- Batch insert/update có thể hiệu quả hơn khi writer nhận nhiều item.
- Chunk lớn sử dụng bộ nhớ nhiều hơn và kéo dài transaction.
- Lock tại database có thể bị giữ lâu hơn.
- Khi rollback/retry, chunk lớn có thể phải làm lại nhiều công việc.
- Garbage collection có thể tăng khi nhiều object sống lâu.
- Query paging/cursor, cache và network round-trip có đặc tính riêng.
- Phần chi phí đọc/ghi có thể thay đổi khi database đạt ngưỡng tải.

Vì vậy, không chọn K chỉ từ công thức. Hãy **đo trên workload đại diện**, so sánh nhiều chunk size và kiểm tra khả năng khôi phục sau lỗi.

## 5. Dùng ChunkListener để đo thời lượng thực tế

**ChunkListener** cung cấp các callback hữu ích:

- **beforeChunk:** trước khi bắt đầu xử lý một chunk trong phạm vi transaction của Step.
- **afterChunk:** sau khi chunk hoàn thành thành công và transaction liên quan hoàn tất theo lifecycle của Spring Batch.
- **afterChunkError:** khi chunk gặp lỗi; callback phục vụ đo và chẩn đoán lần thử thất bại.

Mã dưới đây dùng **System.nanoTime()** để đo khoảng thời gian trôi qua. Đồng hồ monotonic này phù hợp cho duration hơn **System.currentTimeMillis()**, vốn có thể thay đổi do đồng bộ đồng hồ hệ thống.

### 5.1. Listener ghi nhận Timer và Counter với Micrometer

Ví dụ Spring Batch 5.x, Spring Boot 3.x, Micrometer:

~~~java
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.batch.core.ChunkListener;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.scope.context.ChunkContext;
import org.springframework.stereotype.Component;

@Component
public class ChunkThroughputListener implements ChunkListener {

    private final MeterRegistry registry;

    // Mỗi thread xử lý chunk giữ mốc thời gian của chính nó.
    private final ThreadLocal<Long> startedAt = new ThreadLocal<>();

    public ChunkThroughputListener(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public void beforeChunk(ChunkContext context) {
        startedAt.set(System.nanoTime());
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
        Long start = startedAt.get();
        startedAt.remove();

        if (start == null) {
            return;
        }

        StepExecution step =
                context.getStepContext().getStepExecution();

        String jobName = step.getJobExecution()
                .getJobInstance()
                .getJobName();

        long elapsedNanos = System.nanoTime() - start;

        Timer.builder("app.batch.chunk.duration")
                .description("Elapsed time of chunk attempts")
                .tags(
                        "job", jobName,
                        "step", step.getStepName(),
                        "outcome", outcome)
                .publishPercentileHistogram()
                .register(registry)
                .record(elapsedNanos, TimeUnit.NANOSECONDS);

        registry.counter(
                "app.batch.chunk.events",
                "job", jobName,
                "step", step.getStepName(),
                "outcome", outcome
        ).increment();
    }
}
~~~

Đăng ký listener:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, OrderOutput> processor,
        ItemWriter<OrderOutput> writer,
        ChunkThroughputListener throughputListener) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, OrderOutput>chunk(500, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .listener(throughputListener)
            .build();
}
~~~

Mỗi callback thành công ghi một mẫu **app.batch.chunk.duration** có **outcome=success**. Một callback lỗi ghi mẫu **outcome=error**. Counter **app.batch.chunk.events** giúp đếm số callback theo kết quả; đối với throughput chunk thành công, chỉ lấy **outcome=success**.

Những điều cần hiểu về listener:

1. **Timer đo thời gian bao quanh chunk**, gồm các thành phần trong khoảng callback. Nó không phải timer riêng của reader, processor hoặc writer.
2. **Mẫu error là thời gian của lần thử chunk gặp lỗi**, không phải một chunk dữ liệu đã commit thành công.
3. **ThreadLocal** giúp tách mốc thời gian trên các thread xử lý chunk khác nhau trong cách chạy callback đồng bộ thông thường; gọi **remove()** để tránh giữ dữ liệu khi thread được tái sử dụng.
4. Với một kiến trúc mà callback bắt đầu/kết thúc không ở cùng thread, cần thay ThreadLocal bằng cơ chế liên kết với **chunk attempt ID** phù hợp. Không mặc định listener này áp dụng nguyên xi cho mọi hệ thống điều phối từ xa.
5. Nếu process bị kill giữa chunk, callback kết thúc có thể không chạy, nên mẫu timing cho chunk đó có thể bị thiếu.
6. **publishPercentileHistogram()** tăng số series và bộ nhớ metrics. Chỉ bật histogram cho các metric cần p95/p99 thực sự.
7. Không gắn **jobExecutionId**, UUID, tên file đầu vào hoặc customer ID thành metric tags dài hạn, vì chúng khiến cardinality tăng rất nhanh.

### 5.2. Tại sao không đo bằng thời gian của ItemWriter riêng?

Nếu writer mất 30 ms nhưng reader + processor mất 400 ms, một phép đo chỉ ở writer sẽ cho cảm giác chunk rất nhanh trong khi tổng thời gian là khoảng 430 ms hoặc hơn. **Chunk duration** giúp định vị mức độ chậm tổng thể. Khi cần đi sâu, thêm timer cho reader/processor/writer để phân tích thành phần nào chiếm nhiều thời gian.

**ItemReadListener**, **ItemProcessListener** và **ItemWriteListener** có thể giúp instrument từng phase. Tuy nhiên, trong trường hợp retry/rollback, một item có thể được gọi nhiều lần. Metrics phase thường phản ánh **lượt gọi và thời lượng xử lý**, không tự động bằng số item cuối cùng đã commit.

## 6. Đo số item trên mỗi chunk

Một chunk được thiết kế với size 500 không nhất thiết ghi 500 item:

- Chunk cuối có thể chỉ còn 80 item.
- Processor có thể loại item bằng cách trả về **null**.
- Step có thể skip item lỗi.
- Retry/rollback có thể làm thay đổi các lượt xử lý thực tế.
- Writer có thể cập nhật bản ghi đã tồn tại thay vì insert mới.

Với **Step tuần tự**, có thể lấy chênh lệch **writeCount** trước và sau chunk để ước lượng số item được Step ghi nhận là đã viết trong chunk đó. Nhưng phải hiểu giới hạn của cách đo này: ở một Step **đa luồng**, các chunk có thể cùng cập nhật count toàn Step, nên hiệu count toàn cục giữa hai callback có thể chứa công việc của thread khác.

Vì vậy:

- **Chunk duration** có thể đo theo callback của từng chunk.
- **Written items/s** nên lấy từ snapshot **StepExecution.writeCount** trên cửa sổ thời gian, hoặc từ một instrumentation riêng đã được thiết kế đúng transaction/concurrency.
- Đừng mặc định rằng **getWriteCount() hiện tại - getWriteCount() trước đó** luôn là số item của đúng một chunk khi có xử lý song song.
- Đừng lấy **số lần ItemWriter.write(...)** làm số item ghi; mỗi lần writer có thể nhận một **Chunk** chứa nhiều item.

Để tính throughput nghiệp vụ thực tế, nên ưu tiên **writeCount theo StepExecution cùng một khoảng thời gian** và đối soát dữ liệu đã tồn tại ở đích. Nếu writer là API ngoài transaction, cũng cần thêm metric acknowledgment hoặc kết quả thực ở hệ thống nhận.

## 7. Xem tiến độ qua StepExecution và JobExplorer

Spring Batch lưu các count và trạng thái trong **StepExecution**. Ví dụ:

~~~java
StepExecution step = ...;

long reads = step.getReadCount();
long writes = step.getWriteCount();
int commits = step.getCommitCount();
int rollbacks = step.getRollbackCount();
int filters = step.getFilterCount();
int skips = step.getSkipCount();
~~~

Để giám sát từ một service khác, **JobExplorer** có thể truy vấn JobExecution và StepExecution đã được lưu:

~~~java
import java.util.List;

import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.stereotype.Service;

@Service
public class BatchThroughputQueryService {

    private final JobExplorer jobExplorer;

    public BatchThroughputQueryService(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public List<StepSnapshot> getSteps(long jobExecutionId) {
        JobExecution execution =
                jobExplorer.getJobExecution(jobExecutionId);

        if (execution == null) {
            throw new IllegalArgumentException(
                    "Unknown jobExecutionId=" + jobExecutionId);
        }

        return execution.getStepExecutions().stream()
                .map(step -> new StepSnapshot(
                        step.getId(),
                        step.getStepName(),
                        step.getStatus().name(),
                        step.getReadCount(),
                        step.getWriteCount(),
                        step.getCommitCount(),
                        step.getRollbackCount()))
                .toList();
    }

    public record StepSnapshot(
            Long stepExecutionId,
            String stepName,
            String status,
            long reads,
            long writes,
            int commits,
            int rollbacks) {}
}
~~~

Một dashboard có thể query lại mỗi 15 hoặc 30 giây, lưu snapshot trước và tính tốc độ bằng **delta counts / delta time**.

Cần chú ý:

- **JobExplorer trả về trạng thái đã lưu trong JobRepository**. Trong khi một chunk chưa commit, snapshot có thể không thay đổi.
- Đối tượng StepExecution lấy ở lần query trước không tự động cập nhật. Dashboard cần truy vấn lại.
- Chỉ tính delta trong **cùng StepExecution ID**. Nếu Job restart và xuất hiện StepExecution mới, không lấy count mới trừ count cũ của một execution khác.
- Khi Job đã **COMPLETED**, throughput end-to-end có thể tính từ tổng item và thời lượng thực thi; lúc này không còn độ trễ do chunk chưa commit.
- Nếu JobLauncher bất đồng bộ, lời gọi **run(...)** trả về chưa chắc Job đã hoàn tất; phải đợi trạng thái kết thúc trước khi tính thời lượng tổng.

### SQL từ bảng metadata

Trong một schema Spring Batch 5.x điển hình, có thể truy vấn:

~~~sql
SELECT
    STEP_EXECUTION_ID,
    JOB_EXECUTION_ID,
    STEP_NAME,
    STATUS,
    READ_COUNT,
    WRITE_COUNT,
    FILTER_COUNT,
    COMMIT_COUNT,
    ROLLBACK_COUNT,
    LAST_UPDATED
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = ?
ORDER BY STEP_EXECUTION_ID;
~~~

Thông tin này hữu ích cho snapshot theo StepExecution. Cần dùng quyền đọc phù hợp, chọn database JobRepository chính xác và không sửa metadata để “điều chỉnh” throughput.

**LAST_UPDATED** là mốc metadata được cập nhật; không phải đồng hồ đo chính xác thời gian xử lý từng chunk. Để có phân bố duration p50/p95, nên dùng timer ở ChunkListener.

## 8. Dùng Prometheus và Grafana để quan sát

Với Micrometer và Prometheus registry, tên metric có thể được ánh xạ từ dấu chấm sang dấu gạch dưới và bổ sung hậu tố đơn vị. Giả sử Counter thành công ở phần 5 được export thành series **app_batch_chunk_events_total** với label **outcome=success**.

### Chunks hoàn thành mỗi giây

~~~promql
sum by (job, step) (
  rate(app_batch_chunk_events_total{outcome="success"}[5m])
)
~~~

Biểu thức này biểu diễn số sự kiện **afterChunk thành công mỗi giây** trung bình trong năm phút. Nó không tự cho biết có bao nhiêu item trong mỗi chunk.

### Thời lượng chunk trung bình

Giả sử Timer **app.batch.chunk.duration** được export thành **app_batch_chunk_duration_seconds_sum** và **app_batch_chunk_duration_seconds_count**:

~~~promql
sum by (job, step) (
  rate(app_batch_chunk_duration_seconds_sum{outcome="success"}[5m])
)
/
sum by (job, step) (
  rate(app_batch_chunk_duration_seconds_count{outcome="success"}[5m])
)
~~~

Đơn vị kết quả là **giây/chunk**, vì tổng thời gian được chia cho số sự kiện chunk.

### p95 duration

Nếu histogram đã được bật và backend có các bucket phù hợp:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, job, step) (
    rate(app_batch_chunk_duration_seconds_bucket{outcome="success"}[5m])
  )
)
~~~

Kết quả giúp tìm tail latency. Tên series chính xác có thể khác tùy cấu hình registry và version; hãy xem endpoint metrics đang thực sự expose trước khi dùng biểu thức.

### Các panel nên có

| Panel | Nguồn | Vai trò |
| --- | --- | --- |
| **Written items/s** | Delta writeCount theo StepExecution hoặc metric item phù hợp | Năng suất đầu ra |
| **Successful chunks/s** | ChunkListener Counter | Nhịp hoàn thành chunk |
| **Chunk duration p50/p95/p99** | ChunkListener Timer histogram | Tìm đuôi độ trễ và biến động |
| **Read/write/filter/skip** | StepExecution hoặc instrumentation | Giải thích dữ liệu đi qua pipeline |
| **Commit/rollback trend** | StepExecution | Tìm lỗi transaction và chậm commit |
| **CPU, memory, GC** | JVM metrics | Nhận biết giới hạn xử lý/memory |
| **JDBC pool, query latency, locks** | DataSource/database metrics | Nhận biết bottleneck writer/reader |
| **Job completion time** | Job metadata | Đo hiệu năng end-to-end |

Không nên so sánh đơn độc **chunk duration p95** giữa hai Job có chunk size khác nhau rồi kết luận Job nào nhanh hơn. Chunk size lớn thường làm duration một chunk dài hơn, nhưng có thể nâng **item/giây** do giảm overhead. Hãy xem cả hai.

## 9. Benchmark chunk size như thế nào?

Để chọn chunk size, dùng cùng dataset, cùng logic nghiệp vụ và môi trường đo đủ ổn định. Một thí nghiệm có thể thay K qua các giá trị: **50, 200, 500, 2.000**.

Ví dụ kết quả **giả lập** với một triệu item đầu vào và không filter/skip:

| Chunk size | Thời gian toàn Step | Output throughput | Quan sát |
| ---: | ---: | ---: | --- |
| 50 | 240 giây | ~4.167 item/giây | Nhiều transaction, overhead lớn |
| 200 | 155 giây | ~6.452 item/giây | Giảm overhead đáng kể |
| 500 | 148 giây | ~6.757 item/giây | Tốc độ cao nhất trong thí nghiệm |
| 2.000 | 182 giây | ~5.495 item/giây | Chunk lớn, memory/lock/rollback cost có thể cao |

Đây là dữ liệu minh họa để học cách so sánh, không phải kết quả đo Spring Batch mặc định. Chunk size **500** chỉ là lựa chọn tốt nhất **trong bảng giả định này**. Với nguồn dữ liệu và database khác, chunk size phù hợp có thể hoàn toàn khác.

### Quy trình benchmark có thể lặp lại

1. **Cố định dataset:** số item, kích thước item, tỷ lệ filter/skip, độ phức tạp processor, phân bố giá trị và kích thước output phải đại diện production.
2. **Chọn môi trường:** cùng database engine, cùng hardware/CPU quota, cùng pool connection và cấu hình JDBC writer. Tránh để một benchmark bị tác vụ nền chi phối.
3. **Cố định các biến khác:** chỉ thay chunk size ở một nhóm thí nghiệm; giữ nguyên reader query, processor logic, writer, retry policy và số thread.
4. **Warm up hợp lý:** nếu JVM/JIT, cache hoặc connection pool ảnh hưởng đáng kể, chạy thử trước khi ghi nhận số liệu. Tài liệu hóa cách warm up.
5. **Chạy nhiều lần:** lấy median và các phân vị của thời gian toàn Step; một lần chạy có thể bị GC, lock hoặc network jitter.
6. **Ghi đủ chỉ số:** wall time, output item/s, chunk duration p95, CPU, heap, GC pause, JDBC latency, rollback và error rate.
7. **Xác minh kết quả nghiệp vụ:** output đúng số lượng và nội dung, không có item mất hoặc ghi trùng.
8. **Kiểm tra trường hợp lỗi:** benchmark hoạt động bình thường chưa đủ; chunk quá lớn có thể làm thời gian phục hồi sau rollback/restart rất tốn kém.

Không nên đặt một ngưỡng thời gian quá chặt cho integration test chạy trên CI chia sẻ tài nguyên. Kiểm thử correctness nên được tách khỏi **performance benchmark** ở môi trường kiểm soát tốt hơn.

## 10. Các nguyên nhân khiến throughput theo chunk thấp

### 10.1. Reader chậm

Dấu hiệu: reader có độ trễ cao, CPU processor không bận, writer thường nhàn rỗi.

Nguồn nguyên nhân:

- Query không có index thích hợp hoặc kế hoạch SQL không hiệu quả.
- Paging truy vấn nhiều lần với offset lớn.
- Network latency lớn khi mỗi lần đọc thực hiện I/O.
- Dữ liệu đầu vào cần parse phức tạp hoặc file nằm trên remote storage.
- Cursor/paging reader bị cạnh tranh tài nguyên.

Hướng cải thiện:

- Kiểm tra query plan và index.
- Chọn reader phù hợp giữa cursor, paging, file hoặc streaming.
- Tune fetch size/paging hợp lý, đồng thời giữ thứ tự đọc ổn định để hỗ trợ restart.
- Hạn chế round-trip không cần thiết và tách biến đổi dữ liệu nặng khỏi đường đọc khi phù hợp.

**Fetch size của JDBC không phải chunk size.** Fetch size gợi ý số bản ghi driver lấy từ database trong một lượt, trong khi chunk size quyết định ranh giới transaction xử lý item tại Spring Batch. Hai tham số có thể được điều chỉnh độc lập.

### 10.2. Processor chậm

Dấu hiệu: CPU cao, processor chiếm nhiều thời gian; tăng chunk size ít cải thiện item/s.

Nguyên nhân có thể gồm:

- Regex, mapping, validation hoặc tính toán tốn CPU.
- Gọi API hoặc query database cho từng item.
- Tạo nhiều object/JSON làm tăng garbage collection.
- N + 1 query khi xử lý từng item.

Hướng cải thiện:

- Profile CPU và allocation.
- Cache dữ liệu tham chiếu phù hợp, có giới hạn bộ nhớ.
- Gom truy vấn hoặc tiền tải dữ liệu tham chiếu khi nghiệp vụ cho phép.
- Tránh side effect không cần thiết trong processor.
- Chỉ xem xét multi-thread hoặc partition sau khi bảo đảm reader/processor/writer có thể phối hợp an toàn và output idempotent.

Nếu processor chiếm 95% thời lượng mỗi item, chỉ tăng chunk size thường không tạo khác biệt đáng kể vì chi phí transaction chỉ chiếm tỷ trọng nhỏ.

### 10.3. Writer chậm

Dấu hiệu: thời lượng chunk tăng chủ yếu ở writer, database CPU/lock cao hoặc network throughput đạt trần.

Nguyên nhân:

- Ghi từng item với nhiều SQL round-trip.
- Thiếu JDBC batching hoặc cấu hình driver chưa hỗ trợ tối ưu batch.
- Insert/update cần index hoặc constraint kiểm tra tốn kém.
- Database lock contention hoặc nhiều transaction tranh cùng bảng.
- Writer gọi API từ xa với độ trễ cao.
- File writer flush hoặc đồng bộ ổ đĩa quá thường xuyên.

Hướng cải thiện:

- Dùng **JdbcBatchItemWriter** hoặc cơ chế batch writing phù hợp để giảm round-trip.
- Kiểm tra index, execution plan, lock waits và transaction duration.
- Tách tải dữ liệu và thao tác transform nếu kiến trúc cho phép.
- Với API writer, xem xét batch endpoint và giới hạn concurrency.
- Thiết kế idempotency/retry vì tăng tốc ghi không được đánh đổi tính nhất quán.

Không nên tăng chunk size vô hạn để bù một writer thực hiện thao tác riêng lẻ quá chậm. Hãy xác định nguồn latency thực sự.

### 10.4. Commit hoặc checkpoint chậm

Dấu hiệu: reader/processor/writer đều tương đối nhanh, nhưng thời lượng chunk vẫn lớn; database log/transaction commit hoặc metadata update tốn thời gian.

Nguyên nhân có thể gồm:

- Chi phí fsync hoặc transaction log.
- Transaction giữ lock lâu.
- JobRepository đặt trên database chậm hoặc bị quá tải.
- ExecutionContext chứa quá nhiều dữ liệu phải serialize.
- Dùng nhiều listener có truy vấn trong mỗi chunk.

Hướng cải thiện:

- Đo riêng thời gian writer và tổng chunk để thấy phần overhead còn lại.
- Giữ **ExecutionContext** gọn, chỉ lưu trạng thái cần cho restart.
- Kiểm tra hạ tầng database, log, lock và số lượng kết nối.
- Thử chunk size cao hơn trong benchmark có kiểm soát.
- Tránh đặt logic nặng trong listener đồng bộ.

## 11. Tác dụng phụ khi tăng chunk size quá lớn

Tăng chunk size thường giảm số lượt transaction cho cùng lượng dữ liệu, nhưng có các chi phí:

| Rủi ro | Vì sao chunk lớn làm tăng rủi ro? |
| --- | --- |
| **Memory pressure** | Nhiều input/output object nằm trong chunk cùng lúc |
| **GC pause** | Nhiều allocation và object sống lâu hơn |
| **Lock contention** | Transaction giữ lock trong khoảng dài hơn |
| **Rollback cost** | Nhiều item trong chunk chưa commit có thể phải xử lý lại |
| **Restart granularity** | Checkpoint thưa hơn; sau crash có thể lặp lại nhiều xử lý |
| **Slow chunk p99** | Một item chậm có thể kéo dài toàn transaction |
| **Large SQL batch** | Driver hoặc database có giới hạn về kích thước câu lệnh/batch |
| **Timeout** | Transaction hoặc API có thể vượt giới hạn thời gian cho phép |

Ví dụ:

~~~text
Chunk size = 100
  Commit sau mỗi nhóm nhỏ.
  Crash sau 9.950 item -> tối đa khoảng một chunk chưa checkpoint.

Chunk size = 10.000
  Commit thưa hơn.
  Crash sau 9.950 item -> có thể phải xử lý lại phần lớn chunk đầu.
~~~

Ví dụ chỉ minh họa checkpoint trong hệ thống tuần tự; số item thực tế cần xử lý lại phụ thuộc ItemStream, reader, transaction và vị trí crash. Với writer gửi side effect ngoài transaction, xử lý lại còn có thể dẫn đến gửi trùng nếu thiếu idempotency.

Kích thước chunk phù hợp cần cân bằng **throughput**, **latency**, **memory**, **thời gian rollback** và **độ an toàn restart**.

## 12. Multi-threaded Step, partitioning và throughput

### 12.1. Step chạy nhiều thread

Khi Step thực thi nhiều chunk đồng thời, throughput end-to-end có thể tăng nếu bottleneck được giải quyết bằng song song. Tuy nhiên:

- **Tổng thời lượng các chunk** có thể lớn hơn thời gian wall-clock vì nhiều chunk overlap.
- **writeCount/readCount** trên StepExecution là count của toàn Step; không dùng hiệu count tại hai callback để suy ra số item duy nhất của một chunk đang chạy song song.
- Reader, writer và processor phải được thiết kế tương thích với concurrency; nhiều ItemReader mang trạng thái không tự thread-safe.
- Thứ tự commit và thứ tự output có thể không giống input.
- Mỗi thread có thể cần kết nối database; pool nhỏ sẽ thành bottleneck.

Ví dụ, bốn chunk chạy đồng thời, mỗi chunk mất một giây:

~~~text
Thread 1: [ chunk A 1s ]
Thread 2: [ chunk B 1s ]
Thread 3: [ chunk C 1s ]
Thread 4: [ chunk D 1s ]

Tổng chunk durations: 4 giây
Wall-clock elapsed  : khoảng 1 giây (chưa tính overhead)
~~~

Không tính **chunk throughput = 4 / tổng durations 4s = 1 chunk/s** trong trường hợp này. Throughput thực theo wall-clock là khoảng **4 chunk/s**, còn duration trung bình mỗi chunk vẫn gần 1 giây.

### 12.2. Partitioned Step

Với partitioning, nhiều **worker StepExecution** xử lý các vùng dữ liệu khác nhau. Có thể đo:

- Throughput tổng theo Job bằng output hợp lệ chia wall-clock.
- Throughput từng partition để tìm worker chậm.
- p95 chunk duration từng partition.
- Độ lệch số item giữa các partition.

Cần tránh **đếm trùng**: manager StepExecution có thể chứa các count đã được aggregator tổng hợp. Không cộng cả manager và worker nếu manager đã tổng hợp số liệu worker.

### 12.3. Remote chunking

Khi reader/processor/writer nằm ở các tiến trình khác nhau, throughput phụ thuộc message broker, network, serialization, acknowledgment và số lượng worker. **Chunk duration phía manager** có thể bao gồm chờ remote worker; cần thêm metric độ trễ queue và worker xử lý để phân biệt bottleneck.

Không coi việc thêm nhiều worker là chắc chắn làm throughput tăng tuyến tính. Database đích, pool connection hoặc băng thông mạng có thể trở thành điểm nghẽn mới.

## 13. Retry, rollback và cách diễn giải throughput

Một benchmark “happy path” với dữ liệu sạch thường cho tốc độ cao hơn workload thực tế. Khi Step được cấu hình **faultTolerant()**, lỗi tạm thời có thể gây rollback và retry.

Ví dụ:

~~~text
Chunk 1: 500 item -> commit
Chunk 2: 500 item -> writer lỗi -> rollback
Chunk 2: retry -> commit
Chunk 3: 500 item -> commit
~~~

Những công việc của lần thử chunk 2 thất bại vẫn tiêu tốn CPU, I/O và thời gian, nhưng không tạo ra thêm 500 item nghiệp vụ thành công. Nếu chỉ đo **số lần đọc hay số lần gọi writer**, throughput có thể bị thổi phồng. **Output throughput trên wall-clock** và **dữ liệu đích cuối cùng** phản ánh kết quả thực tế tốt hơn.

Nên tách rõ:

- **Attempt throughput:** số lần xử lý/ghi được thử, gồm cả retry.
- **Successful chunk throughput:** số chunk hoàn thành thành công.
- **Committed output throughput:** số item được Step ghi nhận là đã viết thành công theo semantics của Step trên thời gian thực.
- **Business throughput:** số bản ghi/đơn hàng độc nhất ở hệ thống đích trong thời gian thực.

Khi hệ thống có retry nhiều, chỉ báo successful chunks/s có thể giảm mạnh trong khi attempt count tăng. Theo dõi **rollbackCount**, skip count và exception để giải thích nguyên nhân.

## 14. Restart ảnh hưởng phép đo như thế nào?

Một JobInstance thất bại rồi restart có nhiều JobExecution và StepExecution:

~~~text
JobInstance importOrdersJob(businessDate=2026-11-15)
  |
  +-- JobExecution #1: FAILED
  |     StepExecution #10
  |       writeCount = 8.000
  |
  +-- JobExecution #2: COMPLETED
        StepExecution #11
          writeCount = 4.000
~~~

Đây là ví dụ minh họa. Khi tính throughput:

- **Trong lần chạy đầu**, lấy count và thời gian của StepExecution #10.
- **Trong lần restart**, lấy count và thời gian của StepExecution #11.
- **End-to-end của toàn kỳ nghiệp vụ**, phải xác định có tính thời gian gián đoạn chờ restart hay không; thường cần tách cả thời gian xử lý và elapsed time tới khi dữ liệu cuối cùng hoàn chỉnh.
- **Số item cuối cùng** nên kiểm tra từ dữ liệu đích hoặc khóa nghiệp vụ; không lấy commitCount làm số item.

Không tính delta giữa writeCount của StepExecution #10 và #11 như thể chúng thuộc cùng một counter liên tục.

Một chunk được xử lý lại sau rollback có thể khiến CPU và I/O sử dụng nhiều hơn mà không tăng số item đầu ra cuối. Đây là lý do nên theo dõi cả **throughput thành công**, **retry/rollback overhead** và **khả năng checkpoint**.

## 15. Kiểm thử đo throughput

Kiểm thử có hai mục tiêu khác nhau:

1. **Correctness test:** xác nhận Step đọc/ghi đúng item, trạng thái và counters; không phụ thuộc sức mạnh CPU của máy CI.
2. **Performance benchmark:** đo thời gian và throughput trong môi trường ổn định, lặp nhiều lần rồi so sánh phiên bản/cấu hình.

### 15.1. Integration test correctness

Ví dụ dùng **spring-batch-test**, **JUnit 5** và **AssertJ**:

~~~java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class ImportOrdersThroughputTest {

    @Autowired
    private JobLauncherTestUtils testUtils;

    @Test
    void shouldProcessAllItemsAndRecordCommits() throws Exception {
        // Fixture của test chứa đúng 1.000 item hợp lệ.
        JobParameters parameters = new JobParametersBuilder()
                .addString("caseId", UUID.randomUUID().toString(), true)
                .toJobParameters();

        long startNanos = System.nanoTime();
        JobExecution jobExecution =
                testUtils.launchStep("importOrdersStep", parameters);
        double elapsedSeconds =
                (System.nanoTime() - startNanos) / 1_000_000_000.0;

        StepExecution step = jobExecution.getStepExecutions().stream()
                .filter(s -> "importOrdersStep".equals(s.getStepName()))
                .findFirst()
                .orElseThrow();

        assertThat(jobExecution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
        assertThat(step.getReadCount()).isEqualTo(1_000);
        assertThat(step.getWriteCount()).isEqualTo(1_000);
        assertThat(step.getRollbackCount()).isZero();

        // Ví dụ chỉ in metric để quan sát, không đặt pass/fail
        // dựa trên một ngưỡng throughput biến động theo máy CI.
        double throughput = step.getWriteCount() / elapsedSeconds;
        System.out.printf("write throughput = %.1f item/s%n", throughput);
    }
}
~~~

Giả định **JobLauncher đồng bộ** và fixture không bị test khác sửa. Nếu launcher bất đồng bộ, phải đợi Job hoàn tất rồi mới lấy elapsed time.

Dữ liệu test cần có đầu ra xác định; ngoài read/write count, bài test nên kiểm tra bảng/file đích theo đúng business key, nhất là khi writer có side effect bên ngoài transaction.

### 15.2. Benchmark nhiều chunk size

Không nên chỉnh chung Step đã triển khai production chỉ để benchmark. Có thể truyền **chunk size** vào cấu hình benchmark riêng khi xây Step, hoặc tạo các Step tương ứng với những giá trị K cố định trong test environment.

Một bảng ghi nhận kết quả nên gồm:

~~~text
datasetVersion, chunkSize, threads, readCount, writeCount,
durationSeconds, itemsPerSecond, chunkP95Ms,
rollbackCount, peakHeapMb, gcPauseMs, dbLockWaitMs
~~~

Khi so sánh lần chạy, phải giữ version dataset và các thiết lập liên quan. Nên chạy nhiều vòng để có median/p95 đáng tin cậy. Với máy CI dùng chung, coi các phép đo hiệu năng chỉ mang tính tham khảo, không đặt assertion cứng như “phải trên 20.000 item/s” nếu hạ tầng không được kiểm soát.

### 15.3. Kiểm thử listener đo thời gian

Có thể kiểm thử **ChunkThroughputListener** với MeterRegistry test và một ChunkContext giả lập có StepExecution. Mục tiêu của unit test là chứng minh listener phát ra Timer/Counter có tên và tags đúng, không phải kiểm tra tốc độ vật lý chính xác của CPU.

Không nên tự sleep để cố định một duration rồi assert bằng đúng số millisecond. Các độ trễ runtime, scheduler và CI có thể làm kết quả không ổn định. Với logic tính toán throughput từ snapshot, nên tách hàm thuần nhận **deltaCount** và **elapsedSeconds** để kiểm tra công thức bằng input xác định.

## 16. Những lỗi đo throughput thường gặp

| Sai lầm | Vì sao sai? | Cách xử lý |
| --- | --- | --- |
| Dùng **chunk size × commitCount** làm số item ghi chính xác | Commit có thể liên quan EOF, filter, skip hoặc Step đặc biệt | Dùng writeCount và output thực tế |
| Lấy **tổng thời lượng chunk** làm wall-clock khi chạy song song | Chunk overlap giữa các thread | Đo thời gian thực từ đầu đến cuối |
| Chỉ xem throughput trong 1 giây | Chunk lớn làm metric cập nhật theo đợt | Dùng cửa sổ dài hơn và so sánh p50/p95 |
| Chỉ đo writer | Bỏ qua reader, processor và commit overhead | Đo whole-chunk và instrument từng phase |
| Gắn UUID/jobExecutionId vào metric tags | Cardinality tăng vô hạn theo mỗi lần chạy | Chỉ tag job, step và nhóm kết quả ít biến động |
| Đặt pass/fail theo tốc độ trên CI chia sẻ | CPU, database và mạng thay đổi | Benchmark trong môi trường ổn định |
| So sánh dataset khác nhau | Item phức tạp/nhỏ/lớn có chi phí khác | Cố định fixture và phiên bản dữ liệu |
| Cho rằng rollback/retry không ảnh hưởng tốc độ | Xử lý lại vẫn tốn tài nguyên | Theo dõi attempt, rollback, output |
| Tăng chunk size vô hạn | Memory, transaction duration và retry cost tăng | Đo nhiều giá trị K và kiểm tra giới hạn |
| Chỉ nhìn item/s, bỏ qua correctness | Có thể ghi nhanh nhưng mất/trùng dữ liệu | Assert kết quả nghiệp vụ cuối |
| Không tách restart executions | Đếm nhầm giữa các StepExecution | Dùng ID đúng hoặc tổng hợp có chủ đích |
| Cộng manager và worker partition | Count bị aggregate trùng | Chọn đúng nguồn số liệu |

## 17. Quy trình tối ưu throughput theo chunk trong thực tế

Có thể áp dụng một chu trình lặp như sau:

**Bước 1 — Đặt mục tiêu.** Ví dụ phải xử lý 10 triệu item trước 06:00, với error rate và memory dưới ngưỡng cho phép. Xác định rõ input throughput hay output throughput mới là KPI chính.

**Bước 2 — Lấy baseline.** Đo elapsed time, read/write items/s, chunk duration p50/p95, commit/rollback, CPU, heap, GC, database latency và count ở đích.

**Bước 3 — Xác định bottleneck.** Nếu writer chiếm phần lớn thời gian, tối ưu batch SQL hoặc database; nếu processor chiếm phần lớn, profile CPU; nếu commit overhead lớn, thử tăng chunk size có kiểm soát.

**Bước 4 — Thay một biến.** Thử một dải chunk size thay vì vừa đổi K vừa đổi reader, writer và số thread.

**Bước 5 — Đo nhiều vòng.** Ghi median và tail latency. Một lần chạy có thể bị nhiễu bởi warm up, cache hoặc GC.

**Bước 6 — Xem trade-off.** Chunk size mới phải đạt throughput tốt hơn mà không tăng rollback cost, memory, lock time hoặc rủi ro mất tính đúng đắn khi restart.

**Bước 7 — Kiểm tra failure path.** Tạo lỗi có kiểm soát tại giữa chunk, xác nhận rollback và restart tạo output đúng, không mất/trùng item.

**Bước 8 — Theo dõi sau triển khai.** Lưu baseline, dựng dashboard và cảnh báo nếu throughput giảm, chunk p95 tăng hoặc rollback tăng bất thường.

### Ví dụ báo cáo giám sát Step

~~~text
Job: importOrdersJob                  Status: STARTED
Step: importOrdersStep                Chunk size: 500
JobExecution: 1824                    StepExecution: 2941

Read count                120.000
Write count               117.000
Filter count                3.000
Commit count                  240
Rollback count                  0

Read throughput            3.000 item/s
Write throughput           2.925 item/s
Successful chunks/sec      6,0 chunk/s
Chunk duration p50         145 ms
Chunk duration p95         230 ms
Heap usage                 52%
Database lock waits        thấp
~~~

Các giá trị trên là ví dụ minh họa; chunk duration và chunks/s có thể chịu ảnh hưởng của song song và phương pháp đo. Phải ghi rõ cửa sổ thời gian của tốc độ cùng nguồn dữ liệu đo.

**Throughput theo chunk** có ý nghĩa nhất khi được nhìn như một tập hợp gồm **sản lượng item**, **nhịp hoàn thành chunk**, **thời lượng chunk**, **chi phí transaction** và **tính đúng đắn của kết quả**. Chunk size tốt nhất là giá trị giúp Job đáp ứng mục tiêu throughput và SLA trong khi vẫn giữ được khả năng rollback, restart và vận hành ổn định trên dữ liệu thực tế.

