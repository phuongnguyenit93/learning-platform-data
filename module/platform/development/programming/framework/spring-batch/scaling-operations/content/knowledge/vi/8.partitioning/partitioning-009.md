# Chỉ chạy lại partition thất bại trong Spring Batch

> **Chương:** Partitioning
>
> **Module:** SPRING_BATCH_SCALING_OPERATIONS — Mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và các mô hình xử lý phân tán. Bài học tập trung vào cách **khôi phục có chọn lọc các worker partition chưa hoàn tất**, tránh làm lại phần đã thành công, đồng thời bảo vệ thread safety, checkpoint, idempotency và hiệu năng vận hành.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích cơ chế **restart cùng JobInstance** và vì sao những partition đã `COMPLETED` thường không cần thực thi lại.
2. Phân biệt trạng thái `FAILED`, `STOPPED`, `COMPLETED` và những trường hợp kết quả chưa rõ; không đánh đồng “chỉ chạy lại phần thất bại” với việc lọc đúng một mã trạng thái.
3. Mô tả vai trò của `SimpleStepExecutionSplitter`, `JobRepository`, `ExecutionContext` và worker `StepExecution` khi chọn partition cần restart.
4. Cấu hình một partitioned step có khả năng restart bằng Java/Spring Batch 5.x và đối chiếu các lần chạy bằng metadata.
5. Xây dựng checklist khôi phục an toàn cho local/remote partitioning, kể cả khi worker đã commit một phần hoặc bị mất phản hồi.

## 1. “Chỉ chạy lại partition thất bại” nghĩa là gì?

Giả sử job nhập một triệu đơn hàng chia thành bốn partition. Mỗi partition là một phần việc độc lập, có **worker `StepExecution` riêng**, `ExecutionContext` riêng và nhiều chunk transaction riêng.

| Partition logic | Phạm vi đầu vào | Trạng thái lượt đầu |
| --- | --- | --- |
| `range-0000` | `[1, 250001)` | `COMPLETED` |
| `range-0001` | `[250001, 500001)` | `FAILED` |
| `range-0002` | `[500001, 750001)` | `COMPLETED` |
| `range-0003` | `[750001, 1000001)` | `COMPLETED` |

Khi lỗi của `range-0001` được khắc phục, mục tiêu của restart là:

- **Không chạy lại vô ích** ba partition đã hoàn tất.
- **Chạy tiếp/chạy lại** `range-0001` theo trạng thái/checkpoint hợp lệ.
- **Không xóa** dữ liệu đã commit của `range-0001` chỉ vì worker này chưa `COMPLETED`.
- **Đối soát** kết quả cuối cùng theo business key thay vì chỉ nhìn status.

~~~mermaid
flowchart TD
    A["JobExecution #1: thất bại"] --> B["range-0000: COMPLETED"]
    A --> C["range-0001: FAILED"]
    A --> D["range-0002: COMPLETED"]
    A --> E["range-0003: COMPLETED"]
    A --> R["Restart cùng JobInstance"]
    R --> S["StepExecutionSplitter<br/>đối chiếu JobRepository"]
    S --> F["range-0001: thực thi lại<br/>từ checkpoint hợp lệ"]
    B -. "Bỏ qua nếu đã hoàn tất" .-> S
    D -. "Bỏ qua nếu đã hoàn tất" .-> S
    E -. "Bỏ qua nếu đã hoàn tất" .-> S
    F --> G["JobExecution #2: có thể COMPLETED<br/>sau khi các bước đều đạt"]
~~~

**Diễn giải chính xác:** Spring Batch thường hướng đến **restart những partition cần được thực thi**, trong đó có partition `FAILED` và có thể cả `STOPPED` hoặc trạng thái chưa hoàn tất khác theo chính sách. Mục tiêu là **bỏ qua partition đã `COMPLETED`**, trừ khi chủ động cấu hình chạy lại. Không tự động suy rằng chỉ những partition có chuỗi trạng thái đúng bằng `FAILED` mới được phép chạy.

## 2. Những định danh cần hiểu trước khi restart

| Khái niệm | Ý nghĩa | Tác động đến restart |
| --- | --- | --- |
| `JobInstance` | Job name cùng **identifying JobParameters** | Restart đúng công việc tạo `JobExecution` mới của cùng instance |
| `JobExecution` | Một lần thực thi/thử chạy job | Có ID mới khi restart |
| Manager `StepExecution` | Bước điều phối worker của lượt chạy hiện tại | Có thể tạo mới khi job được restart |
| Worker `StepExecution` | Một lần thực thi step của **một partition** | Khi partition chạy lại có thể có ID mới |
| Partition key | Ví dụ `range-0001` | Phải duy trì **cùng ý nghĩa phần việc** qua các lượt của cùng kế hoạch |
| `ExecutionContext` | Range/file ID và checkpoint theo worker | Cần được khôi phục đúng cho partition đang chạy lại |
| Business key | Ví dụ `order_id` | Giúp chống side effect trùng khi retry/replay |

Một `JobInstance` có thể có nhiều `JobExecution`. **Tránh gọi job với một identifying parameter mới chỉ để “restart”**: đó thường là một công việc logic mới, không tự nhận diện những partition cũ đã hoàn thành để bỏ qua.

Với các job đã `COMPLETED`, việc gọi lại chính `JobInstance` thường không phải một restart hợp lệ. Nếu cần xử lý lại toàn bộ dữ liệu theo kế hoạch mới, hãy xác định rõ **re-run** và chiến lược idempotency, thay vì giả vờ job vừa hoàn tất là một lần retry.

## 3. Ai quyết định partition nào phải chạy lại?

Trong partitioning:

1. **`Partitioner`** định nghĩa tập partition logic bằng `Map<String, ExecutionContext>`; key ví dụ `range-0001`, value là dải ID/file.
2. **`StepExecutionSplitter`**, thường là `SimpleStepExecutionSplitter`, dùng kế hoạch phân vùng và metadata của `JobRepository` để xác định những worker `StepExecution` cần chạy ở lượt này.
3. **`PartitionHandler`** chạy các worker được splitter lựa chọn, cục bộ qua `TaskExecutor` hoặc từ xa qua message.
4. **`JobRepository`** lưu lịch sử các execution, kết quả, counters và context phục vụ restart.

~~~mermaid
sequenceDiagram
    participant O as JobOperator / JobLauncher
    participant M as Manager PartitionStep
    participant H as PartitionHandler
    participant S as StepExecutionSplitter
    participant R as JobRepository
    participant W as Worker Step
    O->>M: Restart cùng JobInstance
    M->>H: handle(splitter, managerExecution)
    H->>S: split(managerExecution, gridSize)
    S->>R: Tra lịch sử worker theo tên partition
    R-->>S: COMPLETED / FAILED / STOPPED + context
    S-->>H: Tập worker executions cần thực thi
    H->>W: Chỉ chạy tập đã chọn
    W->>R: Ghi checkpoint/counters/status
    W-->>H: Kết quả
    H-->>M: Tổng hợp worker executions
~~~

Các bước ở đây là **luồng kiến trúc điển hình**, không phải cam kết chính xác thứ tự mọi thao tác metadata nội bộ ở từng phiên bản. Đặc biệt, handler thường là thành phần gọi splitter; không nên thêm lệnh gọi `partition()` hoặc `split()` thủ công mỗi lần muốn thử lại một worker.

### Vì sao không chỉ duyệt một Map và gọi lại những entry “FAILED”?

Nếu bỏ qua `JobRepository` và tự viết vòng lặp trên những key đã lỗi:

- Không biết checkpoint nào đã được commit và phải dùng cho lần thực thi mới.
- Không bảo đảm các worker đó vẫn thuộc **đúng JobInstance, step name và input snapshot**.
- Có thể bỏ sót worker `STOPPED` hoặc worker có trạng thái chưa rõ.
- Có nguy cơ cùng lúc hai tiến trình khởi động lại một partition.
- Dễ khiến lịch sử Batch và kết quả nghiệp vụ không nhất quán.

Thông thường, nên ưu tiên **cơ chế restart của Spring Batch** và để splitter quyết định tập worker cần chạy theo metadata.

## 4. Đọc trạng thái như thế nào?

| Trạng thái worker trước restart | Diễn giải | Hành động mặc định thường mong đợi |
| --- | --- | --- |
| `COMPLETED` | Worker đã kết thúc thành công theo Batch | **Bỏ qua** khi restart nếu không cho phép chạy lại step hoàn tất |
| `FAILED` | Worker không hoàn tất vì lỗi | **Có thể chạy lại/tiếp tục** theo chính sách restart |
| `STOPPED` | Worker bị dừng có kiểm soát hoặc chưa hoàn tất | **Có thể tiếp tục** khi job được restart |
| `STARTING` / `STARTED` còn sót sau sự cố | Kết quả cuối chưa rõ hoặc execution có thể còn chạy | **Điều tra và hòa giải trạng thái**; tránh phát lại mù |
| `UNKNOWN` | Trạng thái chưa xác định đáng tin cậy | **Không giả định an toàn để retry**; cần xử lý vận hành |

**Lưu ý:** `BatchStatus` khác `ExitStatus`. Một worker có `BatchStatus` thể hiện vòng đời và `ExitStatus` mô tả kết quả kết thúc. Khi quyết định restart, cần dựa trên trạng thái thực tế và cách Spring Batch xử lý execution trong repository, thay vì chỉ tìm một chuỗi trong log.

### Cấu hình `allowStartIfComplete`

Một step có thể được cấu hình `allowStartIfComplete(true)` để cho phép chạy lại cả khi lần trước `COMPLETED`. Với bài toán **chỉ khôi phục phần chưa hoàn tất**, cần tránh bật tùy tiện thiết lập này trên **worker step**:

~~~java
new StepBuilder("ordersWorkerStep", jobRepository)
        .<OrderInput, OrderOutput>chunk(200, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .allowStartIfComplete(false)
        .build();
~~~

`false` là chủ đích minh họa; nó phù hợp với việc không chạy lại step đã hoàn tất. `OrderInput`, `OrderOutput` cùng reader/processor/writer là các kiểu và bean nghiệp vụ do ứng dụng định nghĩa. Ngoài chính sách worker, việc manager có được chạy khi restart hay không còn phụ thuộc kết quả step và cấu hình toàn job.

Đừng dùng `allowStartIfComplete(true)` như giải pháp “bảo đảm không mất dữ liệu”: nó có thể làm tăng replay, side effect trùng hoặc tải không cần thiết.

## 5. Ví dụ cấu hình partitioned job có thể restart

Ví dụ dùng API kiểu Spring Batch 5.x, một manager step chia bảng đơn hàng thành bốn dải nửa mở, worker xử lý từng dải qua reader `@StepScope`.

### 5.1. Partitioner tạo key và phạm vi ổn định

~~~java
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.context.annotation.Bean;

@Bean
Partitioner ordersPartitioner() {
    return gridSize -> {
        // Kế hoạch ví dụ được cố định cho JobInstance:
        // ID từ 1 đến 100000, chia bốn khoảng nửa mở.
        Map<String, ExecutionContext> partitions = new LinkedHashMap<>();

        for (int i = 0; i < 4; i++) {
            long min = 1L + i * 25_000L;
            long maxExclusive = min + 25_000L;

            String key = String.format(Locale.ROOT, "range-%04d", i);
            ExecutionContext context = new ExecutionContext();
            context.putLong("minIdInclusive", min);
            context.putLong("maxIdExclusive", maxExclusive);

            if (partitions.putIfAbsent(key, context) != null) {
                throw new IllegalStateException("Trùng partition key: " + key);
            }
        }
        return partitions;
    };
}
~~~

**Vì sao không dùng `UUID.randomUUID()` làm key mỗi lần chạy?** Splitter cần nhận diện các worker đã tồn tại trong metadata. Key mới sẽ không khớp identity cũ. Tương tự, nếu vẫn dùng tên `range-0001` nhưng đổi ranh giới sau khi job đã xử lý một phần, checkpoint cũ có thể không còn tương ứng với công việc mới.

### 5.2. Manager và executor

~~~java
@Bean
ThreadPoolTaskExecutor ordersPartitionExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(8);
    executor.setThreadNamePrefix("orders-partition-");
    executor.initialize();
    return executor;
}

@Bean
Step ordersManagerStep(
        JobRepository jobRepository,
        @Qualifier("ordersWorkerStep") Step workerStep,
        @Qualifier("ordersPartitioner") Partitioner partitioner,
        ThreadPoolTaskExecutor ordersPartitionExecutor) {

    return new StepBuilder("ordersManagerStep", jobRepository)
            .partitioner(workerStep.getName(), partitioner)
            .step(workerStep)
            .gridSize(4)
            .taskExecutor(ordersPartitionExecutor)
            .build();
}
~~~

Kiểu `Step`, `JobRepository`, `StepBuilder`, `ThreadPoolTaskExecutor`, `Qualifier` là API Spring tương ứng. `ordersWorkerStep` phải là một bean chunk step riêng. `gridSize(4)` mô tả gợi ý số partition; trong ví dụ partitioner tạo **chính xác bốn phần việc** theo kế hoạch cố định. Số thread executor không quyết định partition nào được restart; **splitter và metadata** mới là phần liên quan đến lựa chọn worker.

### 5.3. Worker reader lấy range từ ExecutionContext

~~~java
@Bean
@StepScope
JdbcPagingItemReader<OrderRow> ordersByRange(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minIdInclusive']}") Long minId,
        @Value("#{stepExecutionContext['maxIdExclusive']}") Long maxId) {

    return new JdbcPagingItemReaderBuilder<OrderRow>()
            .name("ordersByRange")
            .dataSource(dataSource)
            .selectClause("SELECT id, order_code")
            .fromClause("FROM orders")
            .whereClause("WHERE id >= :minId AND id < :maxId")
            .parameterValues(Map.of("minId", minId, "maxId", maxId))
            .sortKeys(Map.of("id", Order.ASCENDING))
            .rowMapper((rs, rowNum) ->
                    new OrderRow(rs.getLong("id"),
                                 rs.getString("order_code")))
            .pageSize(500)
            .saveState(true)
            .build();
}
~~~

Đây là ví dụ minh họa; `OrderRow` là record/POJO nghiệp vụ, còn `JdbcPagingItemReader`, builder và `Order` là kiểu từ Spring Batch JDBC. `@StepScope` tạo reader theo từng **worker `StepExecution`**; mỗi worker có `ExecutionContext` riêng. `saveState(true)` hỗ trợ reader lưu checkpoint theo cơ chế `ItemStream`, nhưng tính đúng khi restart còn tùy loại reader, transaction, dữ liệu nguồn bất biến và cách đặt tên state.

Sắp xếp paging theo `id` phải dựa trên một khóa **duy nhất, ổn định**. Không để reader dùng `SELECT * FROM orders` không lọc range: các partition khác nhau sẽ đọc trùng dữ liệu dù cơ chế restart hoạt động đúng.

### 5.4. Khởi động lại bằng cơ chế Batch

Khi job đã `FAILED` hoặc `STOPPED` và đủ điều kiện restart, có thể sử dụng `JobOperator` do ứng dụng cấu hình:

~~~java
// failedJobExecutionId là ID lần chạy lỗi đã được xác nhận.
// Giả định JobOperator đã được cấu hình cùng JobRepository/JobRegistry.
Long newJobExecutionId = jobOperator.restart(failedJobExecutionId);
~~~

Lệnh restart ở đây chỉ minh họa **đường đi API**; caller vẫn phải xử lý ngoại lệ, xác thực quyền vận hành, kiểm tra job không đang chạy và quan sát kết quả `JobExecution` mới. `JobOperator.restart(...)` nhằm restart công việc hiện có theo metadata, không giống việc tự gọi `JobLauncher.run(...)` với một tập identifying parameters khác.

**Không** gọi restart chỉ vì thấy một worker fail khi toàn bộ job còn đang chạy các worker khác; cần xác nhận trạng thái cuối của lần thực thi và chính sách dừng/khôi phục.

## 6. Checkpoint: partition thất bại không nhất thiết phải đọc lại từ đầu

Giả sử `range-0001` phụ trách 25.000 đơn hàng, commit theo chunk 200 item. Sau khi 60 chunk commit thành công, worker lỗi trong chunk tiếp theo.

~~~text
range-0001: 25.000 item

12.000 item đã commit thành công  ← 60 chunk × 200
200 item của chunk đang lỗi       ← có thể rollback
phần còn lại chưa xử lý

Restart cần dùng checkpoint hợp lệ và chính sách của reader/writer,
không mặc định xóa 12.000 kết quả đã commit.
~~~

Nếu reader hỗ trợ `ItemStream`, `saveState` đúng và checkpoint được lưu phù hợp tại ranh giới commit, worker mới **có thể tiếp tục từ trạng thái đã commit**. Những item của chunk rollback có thể được đọc/ghi lại khi retry/restart. Nếu reader không restartable, nguồn thay đổi hoặc state không nhất quán, cách khôi phục thực tế có thể phải replay phạm vi, đi cùng writer idempotent.

### Transaction và trạng thái đã commit

- **Dữ liệu ghi cùng transaction phù hợp với chunk:** Lỗi dẫn tới rollback có thể hủy phần ghi chưa commit, còn các chunk đã commit trước đó được giữ.
- **Đích ở một hệ thống transaction khác:** Checkpoint và side effect có thể không atomic; mất kết nối sau khi ghi bên ngoài là trường hợp có kết quả chưa rõ.
- **Lệnh HTTP, gửi message, email:** `JobRepository` không tự rollback tác dụng phụ đã được dịch vụ khác nhận.

Vì vậy, không thể khẳng định “chỉ retry partition FAILED” tự tạo ra bảo đảm **exactly-once effect**. Cần business key, ràng buộc unique, transactional outbox/inbox hoặc idempotency key ở đích tùy loại tác dụng phụ.

## 7. Phân biệt failed partition và stopped partition

Một hiểu lầm thường gặp là viết mã **chỉ lấy `STATUS = 'FAILED'`** rồi chạy lại thủ công. Cách đó có thể bỏ sót các partition dừng chưa hoàn tất, hoặc không xử lý được execution có trạng thái không rõ sau sự cố.

| Tình huống | Thao tác phù hợp |
| --- | --- |
| Một partition `FAILED`, phần còn lại `COMPLETED` | Khắc phục nguyên nhân, restart job để splitter chọn phần cần chạy |
| Một partition `STOPPED` sau yêu cầu dừng hợp lệ | Kiểm tra khả năng restart và checkpoint, tiếp tục theo cơ chế Batch |
| Worker báo `STARTED` nhưng máy chủ đã mất | Xác nhận tiến trình thật, trạng thái metadata/lock; xử lý khôi phục trước khi phát lại |
| `UNKNOWN` hoặc metadata không nhất quán | Điều tra sự cố, không ép `COMPLETED`/`FAILED` bằng SQL tùy ý |
| Muốn chạy lại partition đã `COMPLETED` do nghiệp vụ đổi | Cần một kế hoạch replay/reprocess riêng, không giả định restart mặc định sẽ chạy lại |

“Chỉ chạy lại partition thất bại” nên được hiểu là **khôi phục phần việc chưa hoàn tất và tránh chạy lại phần đã thành công**. Trên hệ thống thật, trạng thái `STOPPED` và các edge case cũng phải được định nghĩa trong quy trình vận hành.

## 8. Kiểm chứng bằng JobRepository

Các worker execution có thể được truy vấn qua metadata. Bảng thường dùng gồm:

| Bảng | Mục đích |
| --- | --- |
| `BATCH_JOB_INSTANCE` | Xác định JobInstance và identity job |
| `BATCH_JOB_EXECUTION` | Mỗi lần chạy/restart của job |
| `BATCH_STEP_EXECUTION` | Status, counters, thời gian, tên các manager/worker execution |
| `BATCH_STEP_EXECUTION_CONTEXT` | `ExecutionContext` của worker: range/file và checkpoint |

### 8.1. Liệt kê worker của một JobExecution

~~~sql
SELECT
    STEP_EXECUTION_ID,
    JOB_EXECUTION_ID,
    STEP_NAME,
    STATUS,
    EXIT_CODE,
    READ_COUNT,
    WRITE_COUNT,
    COMMIT_COUNT,
    ROLLBACK_COUNT,
    START_TIME,
    END_TIME
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = :jobExecutionId
ORDER BY STEP_EXECUTION_ID;
~~~

Truy vấn sẽ trả cả manager step nếu nó thuộc execution này; cần lọc đúng worker theo `STEP_NAME` của ứng dụng. Tên worker partition thường có dạng `ordersWorkerStep:range-0001`.

### 8.2. So sánh lịch sử partition qua nhiều lần restart

~~~sql
SELECT
    je.JOB_EXECUTION_ID,
    se.STEP_EXECUTION_ID,
    se.STEP_NAME,
    se.STATUS,
    se.READ_COUNT,
    se.WRITE_COUNT,
    se.COMMIT_COUNT,
    se.ROLLBACK_COUNT
FROM BATCH_JOB_EXECUTION je
JOIN BATCH_STEP_EXECUTION se
  ON se.JOB_EXECUTION_ID = je.JOB_EXECUTION_ID
WHERE je.JOB_INSTANCE_ID = :jobInstanceId
  AND se.STEP_NAME LIKE 'ordersWorkerStep:%'
ORDER BY je.JOB_EXECUTION_ID, se.STEP_EXECUTION_ID;
~~~

Đây là cú pháp minh họa cho schema metadata mặc định; tên bảng có thể thay đổi do cấu hình prefix. `LIKE` là cách lọc tên worker dựa vào **quy ước của ví dụ**, không phải quy tắc chung cho mọi job.

Kết quả mong đợi ở ví dụ bốn partition:

| JobExecution | Worker step name | Status |
| --- | --- | --- |
| #1 | `ordersWorkerStep:range-0000` | COMPLETED |
| #1 | `ordersWorkerStep:range-0001` | FAILED |
| #1 | `ordersWorkerStep:range-0002` | COMPLETED |
| #1 | `ordersWorkerStep:range-0003` | COMPLETED |
| #2 | `ordersWorkerStep:range-0001` | COMPLETED |

Nếu lần restart chỉ có `range-0001`, điều đó có thể là dấu hiệu cơ chế tránh chạy lại partition đã hoàn tất đang hoạt động đúng. `STEP_EXECUTION_ID` của `range-0001` trong lượt #2 khác lượt #1 là bình thường.

**Đừng cộng tất cả `readCount` hoặc `writeCount` của mọi attempt rồi kết luận số item duy nhất đã ghi.** Một worker có thể xử lý một phần trước lỗi, sau đó tiếp tục/replay. Số lượng nghiệp vụ duy nhất phải được đối soát ở đích theo business key.

### 8.3. Dùng JobExplorer để quan sát

~~~java
JobExecution execution = jobExplorer.getJobExecution(jobExecutionId);
if (execution == null) {
    throw new IllegalArgumentException("Không tồn tại JobExecution");
}

execution.getStepExecutions().stream()
        .filter(step -> step.getStepName()
                .startsWith("ordersWorkerStep:"))
        .forEach(step -> System.out.printf(
                "%s: %s, read=%d, write=%d, rollback=%d%n",
                step.getStepName(),
                step.getStatus(),
                step.getReadCount(),
                step.getWriteCount(),
                step.getRollbackCount()));
~~~

`JobExplorer` là API đọc metadata phù hợp khi xây dashboard hoặc công cụ điều tra; ví dụ giả định các biến `jobExplorer` và `jobExecutionId` đã được cung cấp. Khi cần lịch sử toàn `JobInstance`, phải tìm **nhiều JobExecution**, không chỉ một lần chạy. Không chỉnh trực tiếp `STATUS`, `VERSION` hoặc serialized context trong bảng Batch để ép framework coi một worker đã hoàn tất.

## 9. Local và remote partitioning có gì khác khi restart?

### Local: TaskExecutorPartitionHandler

Các worker được chạy bằng `TaskExecutor` trong cùng JVM. Sau lỗi và restart, handler nhận **tập worker executions do splitter lựa chọn**, không nhất thiết chạy đủ mọi partition. Executor giới hạn concurrency; ví dụ bốn partition nhưng chỉ một cần restart thì chỉ có một phần việc logic cần đưa vào xử lý, dù pool có tám thread.

### Remote: MessageChannelPartitionHandler

Manager gửi yêu cầu worker qua message transport. Trên restart, cần quan sát thêm:

- Request đã được broker **ack** hay có thể giao lại?
- Worker cũ **thật sự dừng chưa** hay chỉ mất liên lạc với manager?
- Metadata `StepExecution` có được cập nhật sau commit không?
- Hai worker có khả năng cùng xử lý một partition không? Có cần cơ chế claim/dedup?
- Writer có chịu được replay khi message được chuyển lại sau timeout không?

~~~mermaid
flowchart LR
    M["Manager: restart JobInstance"] --> S["Splitter: chọn partition chưa hoàn tất"]
    S --> H["MessageChannelPartitionHandler"]
    H --> Q["Broker / request channel"]
    Q --> W["Remote worker"]
    W <--> R[("JobRepository dùng chung")]
    W --> D[("Business database/API")]
    M <--> R
~~~

Một message có thể được gửi lại do lỗi hạ tầng. Do vậy, dù splitter đã chọn đúng `range-0001`, điều đó **không** có nghĩa transport chỉ gửi request đúng một lần hoặc side effect chỉ diễn ra một lần. Metadata và idempotency tại đích phải phối hợp để đảm bảo kết quả.

## 10. Runbook: khôi phục chỉ phần việc chưa hoàn tất

Khi nhận cảnh báo job partitioning lỗi, người vận hành có thể làm theo:

1. **Xác nhận trạng thái toàn job:** JobExecution hiện tại phải ở trạng thái phù hợp để restart; xác minh không còn worker/process cũ đang xử lý âm thầm.
2. **Xác định đúng JobInstance:** Ghi nhận job name, identifying `JobParameters`, phiên bản input, snapshot/watermark, `JobExecutionId` cũ.
3. **Liệt kê worker executions:** Đọc `BATCH_STEP_EXECUTION` hoặc `JobExplorer`, xác định partition `COMPLETED`, `FAILED`, `STOPPED` và các trạng thái không rõ.
4. **Phân tích nguyên nhân gốc:** DB deadlock, network timeout, thiếu tài nguyên, lỗi dữ liệu, reader/processor/writer stateful hay mất message.
5. **Kiểm tra checkpoint và partition plan:** Key → range/file phải giống lượt đầu. Không đổi `gridSize` nếu điều đó làm thay đổi mapping cho cùng JobInstance.
6. **Xác nhận tính an toàn của writer:** Transaction, unique constraint, idempotency key và side effect bên ngoài có được kiểm soát khi replay không?
7. **Restart đúng API:** Sử dụng cơ chế restart Batch (ví dụ `JobOperator.restart`) sau khi khắc phục blocker; không tự tạo JobInstance mới một cách ngẫu nhiên.
8. **Quan sát worker được chọn:** Xác nhận splitter không chạy lại partition `COMPLETED` trái chính sách, theo dõi counters/rollback/lock wait của worker còn lại.
9. **Đối soát kết quả cuối:** Dựa trên tập business key nguồn và đích, hàng mới/duplicate/no-op, quy tắc nghiệp vụ và trạng thái các partition.
10. **Ghi nhận sự cố:** Lưu cause, partitions bị ảnh hưởng, thay đổi hạ tầng, thời gian restart và hành động phòng ngừa.

### Chỉ số vận hành cần ghi lại

| Chỉ số | Vì sao cần |
| --- | --- |
| Số partition ở `COMPLETED`, `FAILED`, `STOPPED` | Xác định phạm vi khôi phục |
| Số worker executions mới ở lượt restart | Kiểm tra tính chọn lọc, không chạy lại vô ích |
| `readCount` / `writeCount` và tỷ lệ lỗi từng partition | Theo dõi tiến độ và khả năng xử lý |
| `commitCount` / `rollbackCount` | Nhận diện retry, deadlock, transaction bất ổn |
| Thời gian đọc/ghi, DB pool, CPU, I/O | Xác định bottleneck khiến partition thất bại |
| Số business keys duy nhất, conflict/dedup/no-op | Xác minh không bỏ sót hoặc nhân đôi dữ liệu |
| Thời gian restart và thời gian hoàn tất | Đo hiệu quả khôi phục |

Tối ưu mục tiêu “chỉ chạy lại phần lỗi” giúp giảm chi phí, nhưng **độ đúng của dữ liệu** luôn quan trọng hơn số worker được chạy lại. Một partition `COMPLETED` mà writer có side effect không nhất quán có thể cần kế hoạch đối soát/khắc phục riêng, không thể sửa chỉ bằng cách lọc status.

## 11. Kiểm thử bắt buộc

| Kịch bản | Điều phải kiểm chứng |
| --- | --- |
| Bốn partition, chỉ một `FAILED` | Sau restart, partition `COMPLETED` được bỏ qua theo cấu hình |
| Một worker commit 60 chunk rồi lỗi | Checkpoint/retry xử lý đúng phần chưa commit, không làm mất dữ liệu cũ |
| Worker `STOPPED` do lệnh dừng hợp lệ | Quy trình có thể tiếp tục nếu hỗ trợ; không bỏ quên vì chỉ lọc `FAILED` |
| Restart cùng JobInstance | Có `JobExecution` mới nhưng partition key/range vẫn ổn định |
| Khởi chạy với identifying parameters khác | Nhận ra đây là JobInstance mới, không lầm là restart |
| Đổi `gridSize` làm đổi key → range | Phát hiện rủi ro và ngăn áp dụng kế hoạch mới cho restart cũ |
| Hai partition đọc overlap | Business key/đối soát phát hiện lỗi, dù statuses đều `COMPLETED` |
| Worker remote commit nhưng mất reply | Reconciliation và idempotent writer chống double side effect |
| Writer gọi API không idempotent | Thử timeout rồi retry để phát hiện tạo tác dụng phụ trùng |
| Metadata còn `STARTED` sau crash | Runbook kiểm tra trạng thái thực, không phát lại vô điều kiện |

### Bài tập tình huống

Job chia 8 partition. Sau lần chạy đầu có 5 partition `COMPLETED`, 2 `FAILED`, 1 `STOPPED`. Nhóm kỹ thuật viết một script chỉ lấy dòng `STATUS='FAILED'` từ `BATCH_STEP_EXECUTION` rồi tự gọi worker cho hai partition đó.

**Câu hỏi:**

1. Vì sao script trên có thể chưa khôi phục đủ dữ liệu?
2. Thành phần Spring Batch nào nên quyết định các worker execution cần chạy khi restart?
3. Nếu một worker `FAILED` đã ghi thành công 10.000 item trước lỗi, có cần xóa toàn bộ output không?
4. Vì sao đổi identifying `JobParameters` để tạo instance mới có thể làm chạy lại cả tám partition?

**Định hướng trả lời:** Partition `STOPPED` cũng có thể cần tiếp tục; lọc đúng `FAILED` là chưa đủ trong nhiều tình huống. `StepExecutionSplitter` phối hợp `JobRepository` lựa chọn worker, `PartitionHandler` thực thi. Chunk đã commit thường được giữ; retry dựa trên checkpoint và idempotency, không tự xóa dữ liệu. Instance mới không mặc nhiên thừa hưởng lịch sử đã hoàn tất của instance cũ.

## Tài liệu tham khảo

- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): partitioning, worker/manager và restart.
- [Spring Batch Reference — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html): checkpoint và chính sách restart của step.
- [Spring Batch API — SimpleStepExecutionSplitter](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/core/partition/support/SimpleStepExecutionSplitter.html): lựa chọn worker executions dựa trên partition và metadata.
- [Spring Batch API — StepExecutionSplitter](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/core/partition/StepExecutionSplitter.html): hợp đồng `split()`.
- [Spring Batch API — JobOperator](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/core/launch/JobOperator.html): API vận hành job, trong đó có restart.
- [Spring Batch Reference — Metadata Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): metadata của `JobInstance`, `JobExecution` và `StepExecution`.

> **Ghi nhớ:** Mục tiêu của “chỉ chạy lại partition thất bại” là **không xử lý lại partition đã hoàn tất và khôi phục đúng phần việc chưa hoàn tất**. Hãy dùng restart cùng `JobInstance`, để `StepExecutionSplitter` dựa vào `JobRepository`, giữ partition key/input/checkpoint ổn định và bảo đảm writer idempotent khi có replay.
