# Test multi-threaded step

## 1. Mục tiêu của bài kiểm thử

Trong module **SPRING_BATCH_SCALING_OPERATIONS**, chúng ta mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và các kiến trúc phân tán phù hợp. Việc thêm `TaskExecutor` vào Step chỉ có ý nghĩa nếu chứng minh được **xử lý đồng thời thật, kết quả nghiệp vụ chính xác, có thể retry/restart an toàn và thông lượng cải thiện trong giới hạn tài nguyên**.

Bài thuộc chương **Testing concurrency**, tập trung vào **Test multi-threaded step**: thiết kế phép kiểm thử cho một chunk-oriented Step được cấu hình thực thi song song.

Giả sử job xử lý 100.000 hóa đơn:

1. `ItemReader` đọc hóa đơn theo ID.
2. `ItemProcessor` tính phí và kiểm tra quy tắc nghiệp vụ.
3. `ItemWriter` cập nhật bảng `invoice_result` với khóa duy nhất `invoice_id`.
4. Step sử dụng executor có tối đa bốn worker.

Câu hỏi kiểm thử không dừng ở “job trả về `COMPLETED` chưa?”. Cần trả lời:

- Có **ít nhất hai lời gọi chạy chồng lấp về thời gian** hay chỉ có nhiều tên thread khác nhau?
- Mỗi khóa hóa đơn đầu vào có đúng một kết quả hợp lệ ở đầu ra khi không có skip/filter?
- Khi reader, processor hoặc writer gặp lỗi, số lượng commit/rollback, retry và checkpoint có hợp lý?
- Cùng một `JobInstance` restart sau lỗi có bỏ sót hoặc nhân đôi dữ liệu không?
- Khi tăng độ song song, hệ thống có chạm trần CPU, connection pool, khóa DB, timeout hay hàng đợi executor không?

Chúng ta sẽ tách kiểm tra **tính đúng đắn** và **hiệu năng**. Một benchmark throughput không thể thay thế kiểm thử race condition; một test có latches cũng không chứng minh cấu hình tối ưu ở production.

## 2. Xác định đúng phiên bản Spring Batch trước khi kiểm tra

Cùng phương thức `.taskExecutor(...)` nhưng đơn vị thực thi đồng thời khác nhau giữa các thế hệ Spring Batch. Đây là nguồn gốc của nhiều test đưa ra kết luận sai.

| Đặc điểm | Spring Batch 5.2 | Spring Batch 6.0 trở lên, chunk-oriented Step |
| --- | --- | --- |
| Công việc được đưa sang worker | **Toàn bộ chunk**: đọc → xử lý → ghi → commit | Các lời gọi **`ItemProcessor.process(...)`** được chạy đồng thời |
| Reader | Có thể được gọi từ nhiều worker | Đọc tuần tự trên thread điều phối Step |
| Processor | Có thể được gọi đồng thời | Có thể được gọi đồng thời |
| Writer | Có thể được gọi từ nhiều worker | Ghi tuần tự trên thread điều phối Step |
| Transaction | Chunk transaction chạy trong worker của chunk | Chunk transaction ở thread điều phối; transaction không tự truyền vào worker processor |
| Kiểu cấu hình chunk | `.chunk(size, transactionManager)` | `.chunk(size).transactionManager(transactionManager)` |
| Test concurrency đặt probe ở đâu? | Có thể đo tại chu trình chunk hoặc processor, đồng thời kiểm tra reader/writer | Đặt probe **bên trong processor**; không đòi writer có nhiều thread |

**Hệ quả:** Trong Spring Batch 6.x, một test thất bại vì writer không chạy đồng thời là **test sai kỳ vọng**. Ngược lại, trong Spring Batch 5.x, nếu reader dùng shared mutable cursor không thread-safe, test chỉ kiểm tra processor sẽ chưa phát hiện hết rủi ro.

Spring Batch 6.x cung cấp `ChunkOrientedStepBuilder.taskExecutor(AsyncTaskExecutor)` cho xử lý item đồng thời. Cách chạy tasklet/chunk cũ qua `AbstractTaskletStepBuilder.taskExecutor(TaskExecutor)` đã deprecated từ 6.0. Khi nâng cấp, phải sửa **cả giả định kiểm thử** lẫn cấu hình Step.

## 3. Bộ tiêu chí PASS của một multi-threaded Step

Trước khi viết test, chuyển yêu cầu thành **invariants** có thể kiểm chứng.

| Nhóm | Điều kiện PASS | Bằng chứng tốt |
| --- | --- | --- |
| Có concurrency | Ít nhất hai tác vụ thực hiện `process` cùng lúc (6.x), hoặc hai chunk thực hiện đồng thời (5.x) | `maxActive >= 2`; latch/phaser có timeout; trace theo thời gian |
| Đủ dữ liệu | Với N item, không filter/skip: N khóa đầu vào xuất hiện ở bảng đích | Đối soát tập khóa và count từ **DB đã commit** |
| Không trùng | Mỗi khóa nghiệp vụ có đúng một bản ghi đầu ra | `UNIQUE(invoice_id)` và truy vấn `GROUP BY ... HAVING COUNT(*) > 1` |
| Không lệ thuộc order | Các kết quả logic giống baseline tuần tự, dù thứ tự hoàn thành khác | So sánh `Map<BusinessKey, Result>` hoặc set; không so sánh thứ tự ghi |
| Retry đúng | Lỗi tạm thời được retry đúng chính sách, lỗi cố định được skip/fail | Fault injection, audit số lần thử, status của Step |
| Restart an toàn | Job thất bại rồi restart cùng identifying parameters không bỏ sót/trùng | Lịch sử `JobExecution`, checkpoint, kết quả cuối ở DB |
| Cô lập dữ liệu | Hai test chạy độc lập không tranh cùng JobInstance, metadata và input | Fixture riêng, tên schema/job params riêng hoặc dọn đúng phạm vi |
| Tài nguyên ổn định | Không từ chối task bất ngờ, leak thread/connection hoặc deadlock | Queue/active thread, Hikari, database locks, timeout |
| Hiệu năng | Throughput cải thiện mà kết quả vẫn chính xác | Đo cùng tập dữ liệu và tải nền; nhiều lần chạy |

**Không đánh đồng:** `BatchStatus.COMPLETED` chỉ nói rằng framework hoàn thành luồng xử lý theo cấu hình. Nó không chứng minh dữ liệu không bị duplicate, không mất bản ghi hoặc không xuất hiện side effect bên ngoài transaction.

## 4. Chiến lược kiểm thử ba tầng

**Tầng A — Kiểm thử đồng thời của component.** Gọi processor nhiều lần từ hai hay nhiều thread, dựng tình huống interleaving có chủ đích. Phù hợp tìm shared mutable state, tài nguyên dùng chung và race condition; nhanh hơn chạy cả job.

**Tầng B — Kiểm thử tích hợp Step/Job.** Khởi tạo Spring Batch với `JobRepository` thực, truyền `TaskExecutor`, chạy một Step từ fixture có giới hạn. Kiểm tra actual concurrency và dữ liệu đã ghi. Đây là trọng tâm bài.

**Tầng C — Kiểm thử lỗi và hiệu năng gần production.** Sử dụng database/container, dữ liệu lớn hơn, pool/timeout gần hệ thống thật; fault injection, restart, concurrent launches, stop/shutdown và benchmark. Chỉ tầng này mới quan sát được lock contention, connection pool và isolation level trên DB dùng trong production.

Với các test cần checkpoint/restart hoặc đồng thời nhiều execution, dùng **JDBC JobRepository** có schema metadata phù hợp. Ở Spring Batch 6.x, cấu hình mặc định `@EnableBatchProcessing` có thể dùng `ResourcelessJobRepository`, implementation **không thread-safe, không lưu bền vững và không phù hợp cho test restart đa luồng**. Trong test mẫu dưới đây, chúng ta bật tường minh `@EnableJdbcJobRepository` và dùng H2.

## 5. Dùng latch để chứng minh hai processor chạy đồng thời

### 5.1 Vì sao đếm tên thread hoặc dùng sleep là chưa đủ?

Đoạn mã sau không đủ mạnh:

```java
Set<String> threadNames = ConcurrentHashMap.newKeySet();

public ScoredInvoice process(Invoice invoice) {
    threadNames.add(Thread.currentThread().getName());
    return calculate(invoice);
}
```

Kết quả có hai tên thread không chứng minh chúng đã chạy **chồng lấp**. Một executor có thể dùng luân phiên nhiều worker nhưng chỉ làm một việc mỗi thời điểm. Ngược lại, một test `Thread.sleep(100)` rồi so tổng thời gian dễ bị flaky vì CPU, GC, CI và tốc độ đĩa khác nhau.

Cách đáng tin cậy hơn là dùng **`CountDownLatch`** để cho hai lời gọi processor cùng đi tới một điểm trước khi được phép kết thúc. Đồng thời đo số lời gọi đang hoạt động:

```text
worker-1: process(1) -> active=1 -> arrived ----┐
                                                 ├── cả hai arrived -> cùng đi tiếp
worker-2: process(2) -> active=2 -> arrived ----┘

maxActive == 2    => đã có ít nhất hai process(...) chồng lấp
maxActive == 1    => chưa chứng minh được song song
```

**Điều kiện để test hợp lệ:** pool phải có ít nhất hai worker, Step có ít nhất hai item độc lập, và `chunkSize >= 2` trong ví dụ Spring Batch 6.x. Latch phải **có timeout** để khi cấu hình sai test trả về lỗi rõ ràng, tránh treo vô hạn.

### 5.2 Ví dụ tích hợp JUnit Jupiter + Spring Batch 6.x

Mẫu dưới đây dựng một job hai item, processor dùng latch, writer lưu kết quả vào bộ nhớ để minh họa kiểm chứng overlap. Đây là **test concurrency thành công**, chưa phải test transaction/restart của dữ liệu nghiệp vụ: để kiểm tra rollback thực sự, thay writer bằng JDBC và đối soát database như phần sau.

Yêu cầu trong test classpath: Spring Batch 6.x (`spring-batch-core`, `spring-batch-test`), Spring Test/JUnit Jupiter, Spring JDBC và H2. Các import sử dụng **package của Spring Batch 6.x**.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.job.Job;
import org.springframework.batch.core.job.JobExecution;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.Step;
import org.springframework.batch.core.step.StepExecution;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.configuration.annotation.EnableBatchProcessing;
import org.springframework.batch.core.configuration.annotation.EnableJdbcJobRepository;
import org.springframework.batch.infrastructure.item.ItemProcessor;
import org.springframework.batch.infrastructure.item.ItemReader;
import org.springframework.batch.infrastructure.item.ItemWriter;
import org.springframework.batch.test.JobOperatorTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseBuilder;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseType;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBatchTest
@SpringJUnitConfig(MultiThreadedStepTest.Config.class)
class MultiThreadedStepTest {

    @Autowired
    private JobOperatorTestUtils batchTests;

    @Autowired
    private OverlapProbe probe;

    @Autowired
    private Results results;

    @Test
    void processorsReallyOverlapAndAllItemsAreWritten() throws Exception {
        // JobOperatorTestUtils tự tạo JobParameters duy nhất cho lần chạy này.
        JobExecution execution = batchTests.startJob();

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        assertTrue(probe.maxActive() >= 2,
                "Expected two overlapping process(...) calls");

        List<Long> actual = results.snapshot();
        assertEquals(2, actual.size(), "No missing/duplicate output");
        assertEquals(Set.of(10L, 20L), Set.copyOf(actual));

        StepExecution step = execution.getStepExecutions()
                .iterator().next();
        assertEquals(2L, step.getReadCount());
        assertEquals(2L, step.getWriteCount());
    }

    static final class OverlapProbe implements ItemProcessor<Long, Long> {
        private final CountDownLatch bothArrived = new CountDownLatch(2);
        private final AtomicInteger active = new AtomicInteger();
        private final AtomicInteger peak = new AtomicInteger();

        @Override
        public Long process(Long id) throws Exception {
            int inFlight = active.incrementAndGet();
            peak.accumulateAndGet(inFlight, Math::max);
            try {
                bothArrived.countDown();
                if (!bothArrived.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "No overlap: check executor, chunk size and input");
                }
                return id * 10L;
            } finally {
                active.decrementAndGet();
            }
        }

        int maxActive() {
            return peak.get();
        }
    }

    static final class Results {
        private final List<Long> committed =
                new CopyOnWriteArrayList<>();

        void addAll(List<? extends Long> items) {
            committed.addAll(items);
        }

        List<Long> snapshot() {
            return List.copyOf(committed);
        }
    }

    @Configuration
    @EnableBatchProcessing
    @EnableJdbcJobRepository
    static class Config {

        @Bean
        DataSource dataSource() {
            return new EmbeddedDatabaseBuilder()
                    .setType(EmbeddedDatabaseType.H2)
                    .addScript(
                        "org/springframework/batch/core/schema-h2.sql")
                    .build();
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource dataSource) {
            return new JdbcTransactionManager(dataSource);
        }

        @Bean
        ThreadPoolTaskExecutor processorExecutor() {
            ThreadPoolTaskExecutor executor =
                    new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(2);
            executor.setMaxPoolSize(2);
            executor.setQueueCapacity(2);
            executor.setThreadNamePrefix("test-process-");
            // Spring quản lý việc initialize/destroy bean này.
            return executor;
        }

        @Bean
        OverlapProbe overlapProbe() {
            return new OverlapProbe();
        }

        @Bean
        Results results() {
            return new Results();
        }

        @Bean
        ItemReader<Long> reader() {
            AtomicInteger nextId = new AtomicInteger();
            return () -> {
                int id = nextId.incrementAndGet();
                return id <= 2 ? (long) id : null;
            };
        }

        @Bean
        ItemWriter<Long> writer(Results results) {
            return chunk -> results.addAll(
                    new ArrayList<>(chunk.getItems()));
        }

        @Bean
        Step concurrentStep(
                JobRepository repository,
                PlatformTransactionManager transactionManager,
                ItemReader<Long> reader,
                OverlapProbe processor,
                ItemWriter<Long> writer,
                ThreadPoolTaskExecutor processorExecutor) {

            return new StepBuilder("concurrentStep", repository)
                    .<Long, Long>chunk(2)
                    .transactionManager(transactionManager)
                    .reader(reader)
                    .processor(processor)
                    .writer(writer)
                    .taskExecutor(processorExecutor)
                    .build();
        }

        @Bean
        Job testJob(JobRepository repository, Step concurrentStep) {
            return new JobBuilder("testConcurrencyJob", repository)
                    .start(concurrentStep)
                    .build();
        }
    }
}
```

**Cách kết luận từ ví dụ:**

- `bothArrived` chỉ về 0 khi **hai lần gọi processor đều đã bắt đầu**; nếu step xử lý tuần tự hoặc pool chỉ một thread, worker thứ nhất đợi tối đa năm giây rồi thất bại.
- `active` được tăng trước khi đợi latch, giảm trong `finally`; `peak` ghi lại số processor cùng hoạt động. Test khẳng định `peak >= 2` thay vì ép chính xác mọi lần đều chỉ có hai worker.
- Hai item đầu vào `1L, 2L` tạo ra `10L, 20L`. Test kiểm tra **vừa kích thước vừa tập giá trị** để không bỏ lọt kết quả trùng.
- `@EnableJdbcJobRepository` tạo repository JDBC với metadata H2 qua schema, tránh kiểm thử concurrency trên `ResourcelessJobRepository`.
- `JobOperatorTestUtils.startJob()` là API thử nghiệm khuyến nghị ở Spring Batch 6.x; test có một bean `Job`. Nếu context có nhiều job, cần chỉ rõ job mục tiêu bằng `setJob(...)`.
- Trong cấu hình minh họa, job được launch đồng bộ. Nếu ứng dụng thay `JobOperator` bằng cơ chế launch bất đồng bộ, cần chờ execution chuyển tới trạng thái kết thúc qua repository/explorer **có timeout** rồi mới assert.

**Giới hạn có chủ đích:** reader dùng `AtomicInteger` chỉ sinh dữ liệu tại một lần chạy, writer dùng danh sách trong RAM và không rollback. Chúng **không có checkpoint bền vững** và không kiểm chứng tính atomic của ghi dữ liệu. Không sử dụng fixture này để kết luận restart, transactional writer hoặc exactly-once đã an toàn.

### 5.3 Điều khiển race một cách chủ động

Để thử một processor có state, dùng `CyclicBarrier` hoặc `Phaser` ép hai worker vào cùng điểm cập nhật shared state, ví dụ gần thao tác `read-modify-write`. Viết một phiên bản intentionally unsafe để **chứng minh test có thể phát hiện lỗi**, sau đó thay bằng thiết kế stateless/atomic và chạy lại. Mỗi barrier phải có timeout hoặc cơ chế cancel, và số participants không vượt số worker thực sự có thể chạy.

Ví dụ sai:

```java
class UnsafeCounterProcessor
        implements ItemProcessor<Long, Long> {
    private long count;  // shared mutable state

    @Override
    public Long process(Long id) {
        count++;         // read-modify-write không atomic
        return id * 10L;
    }

    long count() {
        return count;
    }
}
```

`volatile long count` cũng **không** làm `count++` atomic. Cách tốt nhất nếu processor không cần giữ state là bỏ `count` và tính đầu ra thuần túy theo input. Nếu cần đo số lượt gọi, dùng `AtomicLong` hoặc metric phù hợp; đừng lấy một counter runtime làm checkpoint của job.

## 6. Điều chỉnh cho Spring Batch 5.2

Spring Batch 5.2 thường được cấu hình theo dạng:

```java
// Spring Batch 5.2: mỗi chunk được thực thi trên worker.
new StepBuilder("invoiceStep", jobRepository)
        .<Invoice, InvoiceResult>chunk(100, transactionManager)
        .reader(invoiceReader)
        .processor(invoiceProcessor)
        .writer(invoiceWriter)
        .taskExecutor(taskExecutor)
        .build();
```

Các interface item ở Spring Batch 5.x dùng package `org.springframework.batch.item.*`; các interface của Spring Batch 6.x dùng `org.springframework.batch.infrastructure.item.*`. Trong 5.x, công việc **read/process/write** của nhiều chunk có thể xen kẽ trên nhiều worker, nên kiểm thử thread safety của reader và writer là bắt buộc nếu chúng chia sẻ trạng thái.

Một kế hoạch test bổ sung cho 5.x:

1. Chạy reader với input có ID cố định và writer ghi vào bảng có `UNIQUE(invoice_id)`.
2. Tăng số item đủ tạo nhiều chunk, dùng latch trong processor để xác nhận overlap giữa ít nhất hai worker.
3. Thu thập ID thực sự được đọc/ghi, đối soát không thiếu/trùng trên DB; không chỉ so `readCount`.
4. Kiểm tra các implementation như `FlatFileItemReader` hoặc cursor reader có bảo đảm thread safety hay không. Có thể dùng `SynchronizedItemStreamReader` để đồng bộ `read()` nhưng **không mặc nhiên bảo đảm restart an toàn** khi retry/rollback làm item được đọc lại.
5. Tiêm lỗi giữa hai chunk đồng thời và xác nhận checkpoint nhất quán, kể cả lúc chunk hoàn thành không đúng thứ tự.
6. Chạy benchmark với giới hạn concurrency thực. Ở cơ chế cũ, `throttleLimit` đã deprecated từ 5.0; kích thước thread pool không luôn phản ánh số chunk được phép chạy đồng thời.

**Không dùng `@SpringBatchTest` như một dấu hiệu phân biệt phiên bản:** cả 5.x và 6.x đều có annotation này. Điểm khác ở test utility: Spring Batch 5.2 dùng `JobLauncherTestUtils.launchStep(...)` / `launchJob(...)`; từ 6.0 khuyến nghị `JobOperatorTestUtils.startStep(...)` / `startJob(...)`.

## 7. Kiểm tra tính đúng đắn với DB đã commit

Fixture trong RAM phù hợp để đo overlap, nhưng kiểm thử nghiệp vụ phải quan sát kết quả ở database hoặc hệ thống đích.

Giả sử bảng đầu vào `invoice_input` chứa các ID từ 1 đến 10.000 và bảng kết quả có cấu trúc:

```sql
CREATE TABLE invoice_result (
    invoice_id BIGINT PRIMARY KEY,
    fee_cents BIGINT NOT NULL
);
```

Bảng này nên thuộc test schema riêng; test cần quyết định cách setup/cleanup để không ảnh hưởng dữ liệu khác. Với output có một hàng/khóa, các truy vấn dưới đây kiểm tra ba loại lỗi:

**Thiếu dữ liệu** — không có kết quả tương ứng với input:

```sql
SELECT i.invoice_id
FROM invoice_input i
LEFT JOIN invoice_result r
    ON r.invoice_id = i.invoice_id
WHERE r.invoice_id IS NULL;
```

**Có kết quả ngoài tập input** — writer ghi nhầm dữ liệu:

```sql
SELECT r.invoice_id
FROM invoice_result r
LEFT JOIN invoice_input i
    ON i.invoice_id = r.invoice_id
WHERE i.invoice_id IS NULL;
```

**Lỗi nghiệp vụ** — so kết quả với oracle tính độc lập:

```sql
SELECT r.invoice_id, r.fee_cents, e.expected_fee_cents
FROM invoice_result r
JOIN expected_fee e ON e.invoice_id = r.invoice_id
WHERE r.fee_cents <> e.expected_fee_cents;
```

Khóa chính `invoice_id` sẽ từ chối hai hàng trùng. Nếu bảng đích chưa có unique key, bổ sung:

```sql
SELECT invoice_id, COUNT(*) AS copies
FROM invoice_result
GROUP BY invoice_id
HAVING COUNT(*) > 1;
```

**Định nghĩa oracle rõ ràng:** nếu có filter/skip, bộ khóa mong đợi phải phản ánh chính sách nghiệp vụ. Khi tổng hợp từ nhiều record vào một record, không dùng công thức ngây thơ `readCount = writeCount`. Có thể dùng snapshot của các kết quả baseline tuần tự như oracle, nhưng cần xác nhận baseline thực sự đúng và không phụ thuộc thứ tự.

### Không assert thứ tự hoàn thành

Đừng viết:

```java
assertEquals(List.of(1L, 2L, 3L, 4L), writtenIds);
```

nếu contract nghiệp vụ không yêu cầu output có thứ tự. Các worker có thể hoàn tất khác thứ tự. Hãy so theo khóa:

```java
assertEquals(expectedById, actualById);
assertEquals(expectedById.size(), writtenRows.size());
```

Nếu thứ tự là yêu cầu thật (ví dụ xuất file theo timestamp), phải thiết kế stage sắp xếp ổn định hoặc cơ chế writer có thứ tự, rồi **kiểm thử cả ordering contract**.

## 8. Tiêm lỗi để kiểm tra retry, rollback và restart

Một Step chạy tốt khi mọi thứ thành công là chưa đủ. Đối với workload lớn, giá trị của JobRepository và `ExecutionContext` thể hiện rõ nhất khi job dừng giữa chừng.

### Kịch bản tái hiện có kiểm soát

Giả sử input có **40 item**, `chunkSize=10`, output được ghi vào bảng có khóa duy nhất. Dùng reader hỗ trợ `ItemStream` và checkpoint, ví dụ `JdbcPagingItemReader` hoặc `FlatFileItemReader` được cấu hình phù hợp. Tạo lỗi một lần ở item 25 hoặc một lần ngay trước commit của một chunk. Với lỗi không retry, lần chạy đầu tiên kết thúc `FAILED`.

Các bước test:

1. **Setup:** nạp 40 khóa nghiệp vụ cố định, metadata repository riêng và database đầu ra sạch.
2. **Run #1:** chạy cùng bộ `JobParameters` identifying; kích hoạt lỗi có kiểm soát. Xác nhận `BatchStatus.FAILED`, các checkpoint/context tồn tại và bảng đầu ra chỉ chứa dữ liệu **đã commit**.
3. **Fix lỗi:** tắt fault injector, giữ nguyên dữ liệu và metadata đã lưu; không tạo `run.id` identifying mới.
4. **Restart:** thực hiện restart theo API `JobOperator` của phiên bản, sử dụng execution đã lỗi. Xác nhận execution mới thuộc **cùng JobInstance**.
5. **Đối soát:** status cuối `COMPLETED`, bảng đầu ra có đúng 40 khóa với giá trị đúng, không trùng; tổng số item được xử lý lại có thể lớn hơn 40 vì rollback/retry.
6. **Điều tra metadata:** xem `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION` và `BATCH_STEP_EXECUTION_CONTEXT` để xác nhận vị trí restart và số rollback/skip.

Không đặt assert cứng rằng lỗi ở item 25 đồng nghĩa **chính xác 20 item** phải commit trước đó: fault-tolerance, chunk rollback, buffer, thứ tự xử lý và thời điểm phát lỗi có thể khiến cách đếm khác. Hãy assert dữ liệu đã commit và semantics nghiệp vụ thay vì đoán thứ tự worker.

### Một fault injector có thể bật/tắt

```java
import java.util.concurrent.atomic.AtomicBoolean;

final class FailOnce {
    private final AtomicBoolean enabled = new AtomicBoolean(true);

    void maybeFail(long invoiceId) {
        if (invoiceId == 25L
                && enabled.compareAndSet(true, false)) {
            throw new IllegalStateException("Injected failure");
        }
    }

    void disable() {
        enabled.set(false);
    }
}
```

Trong processor/writer test, gọi `maybeFail(...)` ở vị trí chủ đích. Nếu đã cấu hình retry cho lỗi đó, lần fail đầu có thể được xử lý ngay **trong cùng một lần chạy**, nên phải chọn rõ test muốn đo **retry thành công** hay **restart sau FAILED**. Với mục tiêu restart, tắt retry hoặc dùng lỗi vượt `retryLimit`; giữ điều kiện lỗi ổn định đến khi run đầu thật sự thất bại.

**Quan trọng với processor song song 6.x:** đừng để processor thực hiện side effect bên ngoài rồi hy vọng rollback chunk ở thread chính hoàn tác được. Spring transaction gắn với thread; các processor worker **không tự thừa hưởng transaction** của chunk. Test nên đưa trường hợp gọi DB/API trong processor vào matrix riêng và xác minh có transaction riêng phù hợp hoặc cơ chế idempotency.

### Thử nghiệm lost update, duplicate và idempotency

- **Lost update:** cho hai worker cập nhật cùng một bản ghi/counter nghiệp vụ; dùng optimistic locking/atomic update và assert phiên bản hoặc giá trị cuối.
- **Duplicate:** cố ý retry một tác vụ đã gửi request API hoặc đã ghi output ở transaction riêng; assert idempotency key hoặc unique constraint chặn hành động lặp.
- **Poison item:** đưa dữ liệu vi phạm validation, xác định item bị skip/fail đúng chính sách và không biến thành retry vô hạn.
- **Timeout:** làm chậm DB/API; xác nhận timeout/bounded retry, không treo pool mãi.
- **Stop/shutdown:** yêu cầu dừng job khi nhiều tác vụ đang chạy; xác nhận trạng thái thực thi, cleanup và chính sách khôi phục.

Không bao giờ gắn nhãn `exactly-once` chỉ vì `JobRepository` báo completed. Metadata có thể giúp khôi phục trạng thái framework, nhưng side effect bên ngoài cần hợp đồng idempotency riêng.

## 9. Kiểm tra transaction, thread context và resource sharing

### 9.1 Transaction propagation

Trong Spring Batch 6.x, nếu processor **không chủ động mở transaction riêng**, callback trên worker không tham gia transaction chunk của thread chính. Có thể đặt probe trong processor:

```java
boolean transactionActive =
    TransactionSynchronizationManager.isActualTransactionActive();

String thread = Thread.currentThread().getName();

// Chỉ assert !transactionActive nếu test bảo đảm rằng
// processor không được bao bởi một transaction khác.
assertFalse(transactionActive);
```

Import `TransactionSynchronizationManager` từ `org.springframework.transaction.support`.

Nếu code production yêu cầu transaction trong processor, cần test **đúng** proxy `@Transactional` và propagation. `@Transactional(MANDATORY)` có thể thất bại trên worker vì không tồn tại transaction thừa hưởng từ chunk. `@Transactional(REQUIRED)` trên một Spring bean được gọi qua proxy có thể tạo transaction mới, nhưng transaction đó **độc lập với commit/rollback của chunk**. Tự gọi phương thức annotated trong cùng object thường không kích hoạt Spring proxy.

### 9.2 Các trạng thái dễ gây race

| Thành phần | Race cần mô phỏng | Phép xác nhận |
| --- | --- | --- |
| Processor singleton | `HashMap`, `ArrayList`, counter mutable chia sẻ | Không lost update/`ConcurrentModificationException`; ưu tiên stateless |
| Reader 5.x | Cursor và bộ đếm vị trí bị đọc song song | Mỗi ID được đọc theo contract, không bỏ sót/trùng sau rollback |
| Writer 5.x | Buffer mutable và tài nguyên I/O dùng chung | Kết quả DB đúng, không ghi lẫn record giữa chunk |
| Database | Hai worker cập nhật cùng row | Optimistic lock hoặc SQL atomic update đúng; không deadlock kéo dài |
| HTTP client | Pool/request limit bị bão hòa | Không vượt concurrency limit, retry có backoff |
| `ExecutionContext` | Nhiều luồng ghi cùng key/checkpoint | Restart không bỏ sót; mỗi partition có state riêng khi phù hợp |
| `ThreadLocal`/MDC/security | Context luồng chính không xuất hiện ở worker | Truyền context có chủ đích, không rò rỉ giữa job |
| Thread pool | Hàng đợi đầy khi submit task | Hành vi từ chối tác vụ rõ ràng, job fail/retry theo chính sách |
| JobRepository | Hai launcher bắt đầu cùng identifying params | Không tạo hai execution đang chạy trái chính sách |

`StepScope` hoặc `@Bean` **không đồng nghĩa với thread safety**. Một object step-scoped vẫn có thể được chia sẻ bởi các worker trong cùng StepExecution tùy kiến trúc.

## 10. Stress test và benchmark không làm test trở nên flaky

**Kiểm thử xác định (deterministic concurrency test)** và **stress/benchmark** có mục đích khác nhau:

- Test có latch/phaser giúp ép vào tình huống đồng thời cụ thể, ưu tiên chạy thường xuyên trong CI.
- Stress test chạy trên tập dữ liệu lớn, nhiều mức pool/chunk và nhiều lần, nhằm phát hiện tranh chấp tài nguyên và race xác suất thấp. Nó không thể bảo đảm đã duyệt hết mọi lịch lập thread.
- Benchmark throughput cần dùng cùng dataset, phần cứng, cấu hình DB, JDK, warm-up và tải nền. Đừng dùng ngưỡng “phải chạy dưới 50 ms” như một unit test logic cứng.

Bảng thử nghiệm ví dụ:

| Lần chạy | Pool worker | Chunk size | Input | Chỉ số chính |
| --- | ---: | ---: | ---: | --- |
| Baseline | 1 | 100 | 100.000 | Thời gian, số hàng, lỗi |
| A | 2 | 100 | 100.000 | `maxActive`, throughput, CPU |
| B | 4 | 100 | 100.000 | Queue wait, DB connection, GC |
| C | 8 | 100 | 100.000 | Deadlocks, timeout, retry, throughput |
| D | 4 | 500 | 100.000 | Commit count, heap, latency chunk |
| E | 4 | 100 | 100.000 | Fault injection + restart + đối soát DB |

Lưu ý:

- Với Spring Batch 6.x, số processor đang chạy đồng thời còn bị giới hạn bởi **số item sẵn sàng trong chunk**, số worker thực và scheduler. Chỉ tăng worker mà vẫn `chunkSize=1` không cho test được mức overlap 2.
- Nếu processor chiếm rất ít thời gian và reader/writer mới là bottleneck, thêm thread không tạo tăng tốc đáng kể. Cần đo từng giai đoạn thay vì đổ lỗi cho executor.
- Khi processor chủ yếu gọi HTTP/DB, pool cỡ lớn có thể khiến connection pool, rate limit hoặc database trở thành nút thắt mới.
- `ThreadPoolTaskExecutor` có `corePoolSize`, `maxPoolSize` và `queueCapacity`: `maxPoolSize` không đồng nghĩa luôn có bấy nhiêu worker. Test phải quan sát **active threads và queue** thực tế.
- So sánh throughput **cùng với dữ liệu và error rate**; throughput cao nhưng có record trùng hoặc nhiều retry thì không phải cải thiện hợp lệ.

Thu thập: `items/s`, Step/Job duration, read/process/write time, active/queued tasks, `commitCount`, `rollbackCount`, retry/skip, CPU, GC, Hikari active/pending, DB lock wait, API latency. Một dashboard chỉ có CPU và thời gian tổng thường không đủ để định vị bottleneck.

### Chạy nhiều lần với seed có thể tái hiện

Dữ liệu stress nên có phân bố độ khó:

- ID ngẫu nhiên nhưng **seed cố định** để tái hiện lần lỗi;
- Một phần item rất chậm để tạo chênh lệch thời gian worker;
- Item có cùng khóa logical để thử contention;
- Item gây exception tại pha read/process/write;
- Số item không chia hết chunk size để kiểm tra chunk cuối;
- Input rỗng, input một item, số item nhỏ hơn và lớn hơn pool size.

Khi stress thất bại, lưu seed, bộ job params, phiên bản Spring Batch/JDK, schema DB, thread dump, log lỗi và trạng thái metadata. Không dựa vào một lần không lỗi để kết luận race đã được loại bỏ.

## 11. Những lỗi thường gặp trong test concurrency

| Hiện tượng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| Test pass dù Step chạy tuần tự | Chỉ assert `COMPLETED` hoặc có hai thread name | Dùng latch/barrier và `maxActive >= 2` |
| Test treo vĩnh viễn | Latch thiếu timeout; pool 1 thread nhưng barrier cần 2 | Timeout cho `await`, chunk và pool đủ lớn, fail rõ ràng |
| Test chạy flaky khi CI tải cao | So wall-clock duration với ngưỡng nhỏ; dùng sleep để hy vọng overlap | Bỏ điều kiện timing mong manh; dùng phối hợp xác định |
| Test Spring Batch 6.x đòi reader/writer song song | Hiểu nhầm khác biệt phiên bản | Đặt overlap probe trong processor |
| Test 5.x bỏ sót mất item | Reader/writer dùng shared mutable state không thread-safe | Kiểm tra các khóa đầu/cuối, retry/restart và DB |
| `startJob()` không chạy job mong muốn | ApplicationContext có nhiều bean `Job` | Chỉ rõ job mục tiêu trong test utility |
| Lặp test bị `JobInstanceAlreadyCompleteException` | Dùng lại identifying params của instance đã completed | Dùng params duy nhất cho test mới; giữ nguyên params khi muốn test restart |
| Test restart luôn đọc lại từ đầu | Dùng reader không hỗ trợ checkpoint hoặc tạo instance mới | Dùng reader `ItemStream`, JDBC repository và params đúng |
| Test thấy dữ liệu xuất hiện dù transaction fail | Writer RAM/file/HTTP nằm ngoài rollback của DB | Kiểm tra bằng transactional JDBC writer; kiểm tra side effect riêng |
| Test lọc/skip nhưng assert `readCount == writeCount` | Không xây oracle theo nghiệp vụ | Tính expected keys đã loại filtered/skipped |
| Thử tải lớn trên H2 nhưng production dùng PostgreSQL/Oracle | H2 có isolation/locks/index khác DB thật | Thêm integration suite trên DB cùng vendor, ví dụ Testcontainers |
| Shutdown CI còn thread chạy | Executor hoặc client async chưa cleanup | Giao lifecycle cho Spring; close pools, timeout và dọn tài nguyên |

## 12. Ma trận test tối thiểu trước khi đưa vào production

| Mã | Trường hợp | Kết quả phải kiểm tra |
| --- | --- | --- |
| MT-01 | 2 item, pool=2, chunk=2, latch | Hai `process` chồng lấp và Step completed (6.x) |
| MT-02 | Pool=1 (negative control) | Bằng chứng overlap không đạt, test phát hiện cấu hình sai |
| MT-03 | N item duy nhất, concurrency=1/2/4 | Output theo khóa giống baseline; không thiếu/trùng |
| MT-04 | Input rỗng, một item, chunk cuối thiếu item | Hoàn thành hợp lệ, không giả định luôn có concurrency |
| MT-05 | Processor dùng shared state nguy hiểm | Tái hiện lỗi, sau đó xác nhận bản stateless/atomic sửa được |
| MT-06 | Tiêm lỗi process/writer và retry | Số lần thử và DB sau commit theo chính sách |
| MT-07 | Fail sau một số chunk, restart cùng JobInstance | Không bỏ sót/duplicate, checkpoint và lịch sử execution đúng |
| MT-08 | Bão hòa DB pool/HTTP pool/queue | Timeout/reject hợp lý, job không treo |
| MT-09 | Stop/shutdown giữa lúc đang xử lý | Không còn tác vụ mồ côi gây side effect ngoài dự kiến |
| MT-10 | Tăng pool và chunk trên dataset lớn | Throughput/latency và resource metrics được ghi lại |
| MT-11 | Hai launcher gửi cùng identifying params | JobRepository giữ tính nhất quán về instance/execution |
| MT-12 | Cùng bộ test trên DB gần production | Xác nhận lock/isolation và restart tương ứng thực tế |

Ma trận này không buộc chạy toàn bộ stress suite trên mọi commit. Test nhỏ có latch và đối soát dữ liệu nên chạy thường xuyên; các kịch bản DB nặng, fault injection, shutdown và benchmark có thể chạy ở pipeline kiểm thử tích hợp định kỳ hoặc trước release.

## 13. Câu hỏi tự kiểm tra

1. Vì sao **hai tên thread khác nhau** không đủ để chứng minh processor chạy đồng thời?
2. Trong Spring Batch 5.2 và 6.x, probe trong reader/writer mang ý nghĩa khác nhau thế nào?
3. Tại sao một latch có hai participants có thể khiến test treo khi pool chỉ có một worker? Cách phòng tránh?
4. Vì sao vừa kiểm tra `actual.size()` vừa kiểm tra `Set.copyOf(actual)` trong ví dụ hai item?
5. Tại sao output từ writer trong RAM không thể dùng làm chứng cứ cho rollback/restart chính xác?
6. Khi test restart, đổi `run.id` identifying sẽ ảnh hưởng gì tới `JobInstance`?
7. Vì sao processor trong worker Spring Batch 6.x không tự tham gia transaction chunk? Test trường hợp này bằng cách nào?
8. Khi job có filter/skip, vì sao `READ_COUNT == WRITE_COUNT` không còn là điều kiện bắt buộc?
9. Nếu throughput tăng nhưng duplicate tăng, nên coi benchmark là PASS hay FAIL?
10. Trong hệ thống dùng PostgreSQL production, tại sao H2 test có thể pass nhưng vẫn cần suite trên PostgreSQL?

## 14. Tài liệu tham khảo

- [Spring Batch 6.0 — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/6.0/scalability.html): multi-threaded Step, executor chạy processor, transaction theo thread, local chunking và partitioning.
- [Spring Batch 6.0 — Unit Testing](https://docs.spring.io/spring-batch/reference/6.0/testing.html): `@SpringBatchTest`, `@SpringJUnitConfig`, `JobOperatorTestUtils` và kiểm thử step.
- [Spring Batch 6.0 — JobOperatorTestUtils API](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/test/JobOperatorTestUtils.html): `startJob(...)` và `startStep(...)`.
- [Spring Batch 6.0 — Configuring a JobRepository](https://docs.spring.io/spring-batch/reference/6.0/job/configuring-repository.html): repository JDBC, resourceless và yêu cầu thread safety.
- [Spring Batch 6.0 — ChunkOrientedStepBuilder API](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/step/builder/ChunkOrientedStepBuilder.html): `taskExecutor(AsyncTaskExecutor)`.
- [Spring Batch 5.2 — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/5.2/scalability.html): mô hình multi-threaded chunk cũ, thread safety và đồng bộ reader.
- [Spring Batch 5.2 — Unit Testing](https://docs.spring.io/spring-batch/reference/5.2/testing.html): `JobLauncherTestUtils` và kiểm thử tích hợp với JUnit.
- [Spring Batch 6.0 Migration Guide](https://github.com/spring-projects/spring-batch/wiki/Spring-Batch-6.0-Migration-Guide): chuyển cấu hình hạ tầng, JDBC JobRepository và API phù hợp.

**Nguyên tắc kết thúc:** Một multi-threaded Step chỉ được xem là triển khai tốt khi test chứng minh **concurrency có thật**, đồng thời giữ **đầy đủ dữ liệu, chống trùng, retry/restart chính xác và vận hành ổn định** ở cấu hình tài nguyên thực tế. Đo các thuộc tính này độc lập, rồi kết hợp chúng trong integration suite.
