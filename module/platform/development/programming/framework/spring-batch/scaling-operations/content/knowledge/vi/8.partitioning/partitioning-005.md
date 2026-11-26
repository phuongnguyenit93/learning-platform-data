# PartitionHandler trong kiến trúc Spring Batch

> **Chương:** Partitioning
>
> **Module:** SPRING_BATCH_SCALING_OPERATIONS — Mở rộng Spring Batch cho workload dữ liệu lớn qua multi-threaded step, parallel steps, partitioning và các mô hình xử lý phân tán phù hợp. Bài này giải thích vai trò điều phối của `PartitionHandler`, cách chọn thực thi cục bộ hay từ xa và các yêu cầu về thread safety, retry/restart, đo nút thắt và vận hành job.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Đặt `PartitionHandler` vào đúng vị trí giữa **manager step**, **StepExecutionSplitter**, **Partitioner**, **worker step** và **JobRepository**.
2. Phân biệt nhiệm vụ **chia dữ liệu** với nhiệm vụ **phân phối và thực thi các partition**.
3. Cấu hình `TaskExecutorPartitionHandler` để chạy nhiều worker `StepExecution` trên một JVM bằng Spring Batch 5.x.
4. Giải thích cách thay đổi sang **remote partitioning** với `MessageChannelPartitionHandler` và những yêu cầu bổ sung khi có message broker.
5. Xác định giới hạn concurrency, nguy cơ chạy trùng, retry/restart, tình trạng partition và các metric quan trọng trước khi chọn kiến trúc.

## 1. Bức tranh tổng thể: PartitionHandler nằm ở đâu?

Trong mô hình partitioning, một step được chia thành nhiều **worker StepExecution**. Mỗi worker thực hiện một phần tập input, có `ExecutionContext` và trạng thái chạy riêng, giúp phân phối tải và checkpoint theo phần việc.

~~~mermaid
flowchart TB
    J["Job"] --> M["Manager / PartitionStep"]
    M --> S["StepExecutionSplitter"]
    S --> P["Partitioner<br/>Định nghĩa partition key + ExecutionContext"]
    P --> S
    S --> R[("JobRepository<br/>StepExecution + ExecutionContext")]
    M --> H["PartitionHandler<br/>Phân phối và thu kết quả worker"]
    S --> H
    H --> A["Worker StepExecution 0"]
    H --> B["Worker StepExecution 1"]
    H --> C["Worker StepExecution N"]
    A --> R
    B --> R
    C --> R
    H --> AG["Kết quả các worker"]
    AG --> M
~~~

Đây là sơ đồ **logic**, không ràng buộc tất cả thành phần phải ở cùng JVM. Phần worker có thể chạy bằng các thread nội bộ hoặc trên nhiều tiến trình/máy.

Trong chu trình này:

1. **Manager step** (thường là một `PartitionStep`) được job khởi chạy và cần tổ chức các worker.
2. **StepExecutionSplitter** sử dụng partitioner cùng metadata đã lưu để xác định các worker `StepExecution` cần chạy hoặc chạy lại.
3. **Partitioner** mô tả các phần việc dưới dạng `Map<String, ExecutionContext>`. Key đặt tên partition; value chứa thông tin nguồn của partition, ví dụ ID range hay tên file.
4. **PartitionHandler** nhận yêu cầu thực thi các worker từ manager/splitter. Nó quyết định **thực thi ở đâu, bằng cách nào và thu kết quả ra sao**.
5. **Worker step** thực hiện `read → process → write` trên phạm vi được gán. `JobRepository` lưu các lần thực thi, counters, context và trạng thái phục vụ restart.
6. Manager tổng hợp các trạng thái worker để xác định kết quả của bước partitioning.

Về giao diện, `PartitionHandler` có phương thức cốt lõi tương đương:

~~~java
Collection<StepExecution> handle(
        StepExecutionSplitter stepExecutionSplitter,
        StepExecution managerStepExecution) throws Exception;
~~~

Handler nhận **splitter** thay vì tự đoán phạm vi dữ liệu. Kết quả là tập worker `StepExecution` sau khi được thực thi/thu thập; manager dùng các kết quả này để quyết định trạng thái tổng thể.

### So sánh trách nhiệm

| Thành phần | Trả lời câu hỏi | Trách nhiệm chính |
| --- | --- | --- |
| `Partitioner` | “Dữ liệu được chia thành những phần nào?” | Tạo tên partition và `ExecutionContext` |
| `StepExecutionSplitter` | “Phần việc nào cần có worker execution, kể cả khi restart?” | Tạo/chọn các worker `StepExecution` dựa vào partition và metadata |
| `PartitionHandler` | “Worker được chạy ở đâu và kết quả về bằng cách nào?” | Điều phối thực thi cục bộ hoặc từ xa; trả tập kết quả |
| Worker `Step` | “Làm gì với dữ liệu của một partition?” | Reader, processor, writer, chunk transaction, checkpoint |
| `JobRepository` | “Đã chạy những gì và trạng thái ra sao?” | Lưu metadata `JobExecution`/`StepExecution` và context |
| `TaskExecutor` hoặc message broker | “Cơ chế thực thi/truyền tải cụ thể là gì?” | Cấp thread hoặc gửi message; không tự tạo logic partition |

**Điểm cần nhớ:** `PartitionHandler` không tự làm cho dữ liệu được chia chính xác. Nếu `Partitioner` tạo các khoảng ID chồng lấn, handler vẫn có thể điều phối hai worker cùng đọc một bản ghi.

## 2. Hai hướng thực thi chính

Spring Batch hỗ trợ nhiều cách chạy worker tùy nguồn lực. Khác biệt chủ yếu nằm ở implementation của handler.

| Tiêu chí | Local partitioning | Remote partitioning |
| --- | --- | --- |
| Handler thường dùng | `TaskExecutorPartitionHandler` | `MessageChannelPartitionHandler` trong Spring Batch Integration |
| Nơi chạy worker | Các thread trong cùng JVM | Các JVM/container/máy worker riêng |
| Cơ chế phân phối | `TaskExecutor` | Kênh message/broker và thành phần nhận request |
| Metadata | `JobRepository` của ứng dụng | Manager và worker cần truy cập metadata nhất quán, thường dùng chung `JobRepository` |
| Chi phí triển khai | Thấp hơn, ít hạ tầng | Cao hơn: broker, worker, kết nối, timeout, giám sát |
| Giới hạn thường gặp | CPU, heap, DB pool, I/O của một JVM | Năng lực broker, số worker, DB pool tổng, mạng, độ tin cậy message |
| Khi phù hợp | Một máy còn tài nguyên và dữ liệu chia được | Một máy đã thành nút thắt hoặc cần worker trên nhiều máy |

**Partitioning khác remote chunking:** Trong **remote partitioning**, mỗi worker chạy một **step** và tự đọc/xử lý/ghi phạm vi dữ liệu được phân. Trong **remote chunking**, manager thường đọc và gửi **các chunk item** cho worker xử lý/ghi. Việc chọn handler và topology phải đúng mô hình; hai cách này có chiến lược transaction, truyền tải và restart khác nhau.

## 3. Local: TaskExecutorPartitionHandler hoạt động thế nào?

`TaskExecutorPartitionHandler` là handler có sẵn để chạy các worker step bằng một `TaskExecutor` trong cùng JVM. Mỗi partition có một `StepExecution` riêng, ngay cả khi các worker dùng cùng định nghĩa `Step` trong Spring configuration.

~~~mermaid
flowchart LR
    M["PartitionStep<br/>manager"] --> H["TaskExecutorPartitionHandler"]
    H --> E["ThreadPoolTaskExecutor"]
    E --> W1["Thread A<br/>worker step: partition-0"]
    E --> W2["Thread B<br/>worker step: partition-1"]
    E --> W3["Thread C<br/>worker step: partition-2"]
    W1 --> D[("Database đích")]
    W2 --> D
    W3 --> D
~~~

Nếu cấu hình 12 partition nhưng thread pool chỉ có 4 worker đồng thời, những partition còn lại phải chờ được cấp thread. `gridSize` là gợi ý về mức chia công việc do handler/splitter truyền; **không nên đồng nhất** nó với số core CPU hay số thread được thực thi đồng thời.

### 3.1. Ví dụ cấu hình manager step

Ví dụ Spring Batch 5.x, giả định có `ordersWorkerStep` là chunk step riêng và việc phân chia ID đã được chốt từ trước theo một JobInstance.

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.batch.core.Step;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.core.partition.support.TaskExecutorPartitionHandler;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class OrdersPartitionConfiguration {

    @Bean
    Partitioner ordersPartitioner() {
        return gridSize -> {
            Map<String, ExecutionContext> partitions = new LinkedHashMap<>();

            // Ví dụ: tập ID 1..100000 chia thành 4 range cố định.
            // Trong production, lấy từ một kế hoạch phân vùng bền vững.
            for (int i = 0; i < 4; i++) {
                long min = 1L + 25_000L * i;
                long maxExclusive = min + 25_000L;

                ExecutionContext context = new ExecutionContext();
                context.putLong("minId", min);
                context.putLong("maxIdExclusive", maxExclusive);

                String partitionName = String.format("range-%04d", i);
                if (partitions.putIfAbsent(partitionName, context) != null) {
                    throw new IllegalStateException(
                            "Duplicate partition: " + partitionName);
                }
            }
            return partitions;
        };
    }

    @Bean
    ThreadPoolTaskExecutor ordersPartitionExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(8);
        executor.setThreadNamePrefix("orders-part-");
        executor.initialize();
        return executor;
    }

    @Bean
    TaskExecutorPartitionHandler ordersPartitionHandler(
            @Qualifier("ordersWorkerStep") Step workerStep,
            ThreadPoolTaskExecutor ordersPartitionExecutor) {

        TaskExecutorPartitionHandler handler = new TaskExecutorPartitionHandler();
        handler.setStep(workerStep);
        handler.setTaskExecutor(ordersPartitionExecutor);
        handler.setGridSize(4);
        return handler;
    }

    @Bean
    Step ordersManagerStep(
            JobRepository jobRepository,
            Partitioner ordersPartitioner,
            TaskExecutorPartitionHandler ordersPartitionHandler) {

        return new StepBuilder("ordersManagerStep", jobRepository)
                .partitioner("ordersWorkerStep", ordersPartitioner)
                .partitionHandler(ordersPartitionHandler)
                .build();
    }
}
~~~

**Điều cần hiểu về mã:**

- `ordersPartitioner` tạo bốn partition có tên cố định và các khoảng nửa mở `[minId, maxIdExclusive)`, **không giao nhau**.
- `ordersPartitionHandler` chịu trách nhiệm **chạy** worker bằng executor, không tạo lại các range.
- Worker được cấu hình và truyền vào qua `ordersWorkerStep`. Đây là định nghĩa step được tái sử dụng; mỗi worker execution vẫn có context riêng.
- `setGridSize(4)` và thread pool 4 thread là lựa chọn để minh họa; tăng `gridSize` không tự tăng giới hạn thread pool.
- Ví dụ giữ cứng biên partition để dễ học. Với dữ liệu thực tế, đọc/snapshot tập nguồn và cố định kế hoạch theo job parameters hoặc metadata bền vững để tránh thay đổi phạm vi khi restart.

### 3.2. Worker lấy phạm vi từ ExecutionContext

Reader trong worker chỉ nên chọn bản ghi thuộc partition mình sở hữu. Với nguồn JDBC theo ID, có thể cấu hình reader theo kiểu:

~~~java
@Bean
@StepScope
JdbcPagingItemReader<OrderRow> ordersWorkerReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxIdExclusive']}") Long maxId) {

    return new JdbcPagingItemReaderBuilder<OrderRow>()
            .name("ordersWorkerReader")
            .dataSource(dataSource)
            .selectClause("SELECT id, order_code")
            .fromClause("FROM orders")
            .whereClause("WHERE id >= :min AND id < :max")
            .parameterValues(Map.of("min", minId, "max", maxId))
            .sortKeys(Map.of("id", Order.ASCENDING))
            .rowMapper((rs, rowNum) ->
                    new OrderRow(
                        rs.getLong("id"),
                        rs.getString("order_code")))
            .pageSize(500)
            .saveState(true)
            .build();
}
~~~

Ở đây `OrderRow` là record/POJO nghiệp vụ, còn `DataSource`, `StepScope`, `Value`, `JdbcPagingItemReader`, `JdbcPagingItemReaderBuilder` và `Order` được import từ Java/Spring tương ứng. Ví dụ giả định `orders.id` là cột sắp xếp **duy nhất, ổn định** và kết nối database hỗ trợ câu SQL trên.

`@StepScope` giúp tạo một reader cho **mỗi worker StepExecution**, tránh chia sẻ cursor giữa các partition. Mỗi worker có checkpoint trong `ExecutionContext` riêng. Tuy nhiên, nó không thay thế kiểm tra thread safety của writer hoặc các singleton được chia sẻ. Nếu một worker step tự gắn thêm `TaskExecutor` để xử lý nhiều chunk song song, các thread trong cùng worker có thể vẫn chia sẻ reader step-scoped, nên phải xem xét riêng.

## 4. Remote: MessageChannelPartitionHandler trong kiến trúc

Khi một JVM không đủ CPU/RAM/I/O hoặc muốn mở rộng theo số lượng máy, có thể chạy **remote partitioning** qua Spring Batch Integration. `MessageChannelPartitionHandler` là handler phía manager để đưa yêu cầu thực thi worker lên một message channel và nhận/thu thập kết quả theo cơ chế tích hợp đang cấu hình.

~~~mermaid
sequenceDiagram
    participant M as Manager / PartitionStep
    participant H as MessageChannelPartitionHandler
    participant Q as Broker / request channel
    participant W as Remote worker
    participant R as JobRepository
    M->>H: handle(splitter, managerExecution)
    H->>R: Chuẩn bị/lấy worker StepExecutions
    H->>Q: StepExecutionRequest
    Q->>W: Giao request
    W->>R: Lấy metadata + ExecutionContext
    W->>W: Chạy worker Step (read/process/write)
    W->>R: Cập nhật status/counters/checkpoint
    W-->>H: Reply hoặc tín hiệu hoàn tất theo cấu hình
    H-->>M: Trả các worker StepExecution
~~~

Sơ đồ lược giản: chi tiết gửi reply, polling repository, timeout và mức độ bảo đảm truyền nhận phụ thuộc cấu hình Spring Batch Integration/message transport đang dùng.

### Các thành phần cần có

- **Manager** chứa `Partitioner`, splitter, `MessageChannelPartitionHandler` và kênh gửi yêu cầu.
- **Message transport** mang yêu cầu được định danh theo job/step execution. Có thể dùng broker qua Spring Integration adapter hoặc transport phù hợp.
- **Worker** có thành phần nhận yêu cầu (thường `StepExecutionRequestHandler`), định nghĩa worker `Step` giống tên mà manager yêu cầu và quyền truy cập metadata để tải `StepExecution` cùng `ExecutionContext`.
- **JobRepository/JobExplorer** nhất quán giữa manager và các worker; ở triển khai phân tán, thường cần backend metadata dùng chung.
- **Kênh/chiến lược phản hồi** để manager biết worker đã xong hoặc gặp lỗi. Phải cấu hình timeout, lỗi hạ tầng và giám sát request bị treo.

**PartitionHandler không phải message broker:** Handler tạo/phát yêu cầu và thu kết quả, còn độ bền message, retry delivery, visibility timeout, acknowledgement, ordering và dead-letter queue là trách nhiệm cấu hình transport/worker đi kèm.

### Ví dụ luồng thực tế

Giả sử có ba máy worker, mỗi máy xử lý tối đa hai partition đồng thời. Manager tạo 12 partition có ID cố định `range-0000` đến `range-0011`. Nó gửi yêu cầu tương ứng qua kênh request; các worker nhận và chạy theo năng lực của mình. Nếu một worker bị ngắt kết nối sau khi ghi thành công nhưng trước khi gửi phản hồi, request có thể được xử lý lại hoặc manager có thể coi lần chạy chưa rõ kết quả.

Vì vậy cần:

1. Worker có **partition identity** ổn định và trạng thái trong repository để phân biệt đã hoàn thành/chưa hoàn thành.
2. Writer có cơ chế **idempotency** tại đích, đặc biệt khi gọi HTTP, gửi event hoặc ghi sang hệ thống không cùng transaction.
3. Timeout/retry message được cấu hình cùng việc kiểm tra metadata, tránh tạo hai worker cùng sửa một tài nguyên mà không có biện pháp chống cạnh tranh.
4. Capacity planning theo **tổng số worker đang hoạt động**, không chỉ số thread ở manager.

Remote partitioning tăng khả năng mở rộng tài nguyên nhưng cũng tạo thêm điểm lỗi mạng, broker, container và lịch xử lý phân tán. Chỉ chuyển sang mô hình này khi số đo cho thấy lợi ích vượt chi phí vận hành.

## 5. PartitionHandler và retry/restart

Hệ thống có nhiều worker dễ gặp một số tình huống:

| Sự cố | Điều có thể xảy ra | Hướng xử lý |
| --- | --- | --- |
| Worker thất bại trước commit chunk | Chunk chưa commit rollback; StepExecution thất bại | Retry/restart theo chính sách step và checkpoint |
| Worker đã commit nhưng manager chưa nhận kết quả | Manager có thể tạm thấy trạng thái chưa rõ hoặc timeout | Đối chiếu metadata và trạng thái thực; tránh tự phát lại mù |
| Manager dừng giữa lúc worker vẫn chạy | Một số worker có thể hoàn tất, một số chưa | Dựa vào JobRepository để khôi phục và chọn phần việc còn thiếu |
| Broker giao lại request | Có nguy cơ cùng partition được yêu cầu thêm lần nữa | Dedup/claim phù hợp, ngăn chạy chồng, writer idempotent |
| Kế hoạch phân vùng đổi khi restart | Tên partition cũ chỉ đến dữ liệu khác | Giữ ánh xạ key → input ổn định theo JobInstance |
| Partition A xong, partition B lỗi | Các commit của A không tự rollback vì B lỗi | Restart B nếu thích hợp; đối soát kết quả toàn job |

Trong partitioning, **tên partition**, **ExecutionContext** và **trạng thái StepExecution** phải kết hợp nhất quán. `StepExecutionSplitter` sử dụng metadata để quyết định worker execution cần xử lý ở một lần thực thi; `PartitionHandler` điều phối phần việc đã được chọn. Việc restart có thể tạo các `StepExecution` mới cho phần việc cần chạy lại, nhưng **partition key và phạm vi dữ liệu** phải tiếp tục biểu diễn cùng công việc logic.

### Một ví dụ lỗi nghiêm trọng

Lần đầu, key `part-0` đại diện ID `[1, 1001)` và đã hoàn thành; `part-1` đại diện ID `[1001, 2001)` nhưng thất bại. Lần restart, partitioner thay cách chia, khiến `part-1` chuyển thành `[501, 1501)`. Khi worker được tái thực thi theo lịch sử `part-1`, nó có thể xử lý lại một phần công việc của `part-0` và bỏ thiếu dữ liệu cũ.

Do đó, **không tạo partition key bằng UUID/time mới ở mỗi lần chạy** và không đổi biên dữ liệu âm thầm dưới cùng key trong cùng JobInstance. Nếu muốn chia lại, cần thiết kế kế hoạch job mới và quy tắc replay/dedup rõ ràng.

### Idempotency phải nằm ở nơi có hiệu lực giữa các worker

Đặt `synchronized` trên một method trong manager hoặc một worker JVM chỉ khóa các thread trong tiến trình đó; nó không chống ghi lặp giữa nhiều máy. Với database, unique constraint hoặc bảng ledger dùng chung trong cùng transaction với thay đổi nghiệp vụ thường là biện pháp thích hợp. Với API, dùng idempotency key ổn định và xác nhận hỗ trợ từ server. Với message, cân nhắc outbox/inbox và dedupe theo event ID.

## 6. Grid size, thread pool và backpressure

Ba đại lượng hay bị nhầm lẫn:

1. **Số partition logic:** Tổng số phần việc được phân chia, ví dụ 40 range.
2. **Concurrency thực tế:** Số worker/chunk thực sự chạy đồng thời, ví dụ 8 thread hoặc 8 slot remote.
3. **Chunk size:** Số item tối đa được gom để ghi/commit mỗi chunk, ví dụ 500 item, không phải số partition.

~~~text
40 partitions
  ├─ local executor: tối đa 8 worker chạy cùng lúc
  │    └─ mỗi worker: chunk size 500
  └─ hoặc remote workers: 5 máy × 2 worker slots = 10 slot đồng thời
~~~

Đây là ví dụ về giới hạn thiết kế, không phải công thức Spring Batch áp đặt cứng. Trong thực tế, executor có queue, broker có prefetch, database có connection pool và một worker có thể đợi đọc/ghi nên concurrency thay đổi theo thời gian.

| Hiện tượng | Nguyên nhân thường gặp | Cách đo và điều chỉnh |
| --- | --- | --- |
| Tăng partition nhưng throughput đứng yên | DB/source I/O hoặc writer đã bão hòa | Đo CPU, I/O, DB lock/pool, thời gian read/write |
| Partition chạy xong không đều | Dữ liệu phân phối lệch hoặc query plan khác | Read/write count và duration theo từng partition |
| Nhiều rollback/deadlock | Nhiều worker tranh chấp khóa ghi | Giảm concurrency, chia vùng ghi, index/transaction |
| Thread pool có hàng đợi dài | Số partition vượt quá worker slots | Kiểm tra queue latency và capacity |
| Manager/worker chờ broker | Message backlog, timeout, broker hạn chế | Lag, ack, retry, DLQ, bandwidth, số consumer |
| Memory tăng mạnh | Quá nhiều chunk/partition có trạng thái đệm | Giới hạn queue, chunk size, vùng dữ liệu trong RAM |

**Đo bottleneck trước khi scale:** so sánh throughput theo item/giây, p95 latency của read/process/write, thời gian chờ connection, số rollback và thời gian kết thúc job. Tăng worker có thể làm giảm hiệu năng nếu DB pool nhỏ hoặc lock contention tăng.

## 7. Mối quan hệ với thread safety

Local partitioning có thể giúp tránh chia sẻ state của reader: mỗi worker `StepExecution` có `ExecutionContext` và reader `@StepScope` riêng. Nhưng không nên coi mọi bean trong worker tự an toàn:

- **Reader:** Nếu là `@StepScope`, thường có instance riêng cho mỗi worker StepExecution. Nếu bên trong worker còn đa luồng theo chunk thì vẫn phải xét chia sẻ reader trong phạm vi worker.
- **Processor:** Singleton stateful có field mutable được dùng giữa nhiều worker có thể gây race condition. Ưu tiên stateless hoặc state theo step.
- **Writer:** Dùng chung database không đồng nghĩa các thao tác ghi an toàn khi chạy cạnh tranh. Cần thread safety ở implementation và idempotency/transaction tại đích.
- **External client:** HTTP client, message producer và connection pool cần cấu hình concurrency, timeout và retry phù hợp.
- **StepExecution/ExecutionContext:** Không lấy shared mutable map trong singleton làm “trạng thái partition”; mỗi worker dùng context riêng của framework.

Một `TaskExecutorPartitionHandler` có thể chạy 8 worker đồng thời nhưng reader thực tế truy vấn cùng toàn bộ bảng nếu không dùng predicate theo partition; trong trường hợp này, tăng thread chỉ làm tăng xử lý trùng.

## 8. Quan sát PartitionHandler khi vận hành

Nên theo dõi theo **manager** và **worker**:

| Phạm vi | Metric/trường quan trọng | Câu hỏi cần trả lời |
| --- | --- | --- |
| Manager step | JobExecutionId, StepExecutionId, status, thời gian tổng | Công việc phân vùng đã kết thúc chưa? |
| Partition | Partition key, range/file ID, worker StepExecutionId, status | Partition nào đang chạy, xong, lỗi hay cần retry? |
| Thông lượng | `readCount`, `writeCount`, Δitem/s của từng partition | Có partition chậm hoặc bị kẹt không? |
| Lỗi | `readSkipCount`, `processSkipCount`, `writeSkipCount`, `rollbackCount` | Lỗi xuất hiện ở giai đoạn nào? |
| Local resource | Executor active threads, queue length, CPU, heap/GC | JVM đã hết khả năng xử lý chưa? |
| Remote resource | Message lag, số request pending, timeout, retry, worker health | Broker hoặc máy worker nào đang nghẽn? |
| Database | Connection pool, lock wait, deadlocks, query latency | Tăng partition có gây tranh chấp DB không? |
| Kết quả nghiệp vụ | Số business key duy nhất, duplicate/no-op, checksum/tổng tiền | Output có đủ và đúng sau retry/restart không? |

**Không dùng `writeCount` làm bằng chứng duy nhất về số hàng mới:** một writer dùng `INSERT ... ON CONFLICT DO NOTHING` có thể nhận item thành công nhưng không insert hàng mới. Ngoài ra, khi job restart, có thể có nhiều `StepExecution` cho cùng partition logic; dashboard cần phân biệt **công việc xử lý qua các lần chạy** với **kết quả nghiệp vụ duy nhất tại đích**.

Khi thu thập metric time-series, cân nhắc cardinality: partition ID/StepExecutionId hữu ích trong log hoặc truy vấn metadata, nhưng gắn vào mọi nhãn metric dài hạn có thể làm tăng số chuỗi dữ liệu rất lớn. Có thể tổng hợp metric theo job/worker pool và dùng trace/log để điều tra từng partition.

## 9. Chọn handler theo tài nguyên và yêu cầu

| Tiêu chí đánh giá | Hướng quyết định |
| --- | --- |
| Dữ liệu có thể chia thành các range/file/shard không giao nhau? | Nếu không, nên xử lý lại thiết kế nguồn trước khi chọn handler |
| Một JVM còn đủ CPU/RAM/IO và dễ truy cập nguồn/đích? | Ưu tiên thử `TaskExecutorPartitionHandler` vì vận hành đơn giản hơn |
| Nhu cầu worker vượt tài nguyên một máy, cần scale ngang? | Xem xét `MessageChannelPartitionHandler`/remote partitioning |
| Database đích đang bão hòa? | Tăng worker từ xa thường không giải quyết bottleneck; tối ưu DB và số kết nối |
| Restart sau lỗi một partition có bắt buộc chính xác? | Giữ partition key → input ổn định, checkpoint worker, writer idempotent |
| Input liên tục thay đổi? | Cố định watermark/snapshot/manifest trước khi chia việc |
| Side effect bên ngoài transaction? | Thiết kế idempotency key, outbox/inbox hoặc cơ chế xác nhận/dedup |
| Có khả năng vận hành broker, nhiều worker và cảnh báo lỗi? | Nếu chưa, triển khai local và đo hiệu quả trước |

**Ví dụ quyết định:** Hệ thống import 10 triệu bản ghi mỗi đêm. Baseline tuần tự mất 5 giờ; phần xử lý CPU chiếm 75% thời gian, DB còn dư công suất. Thử local partitioning với 4 worker có thể là bước hợp lý. Nếu CPU một JVM bão hòa nhưng DB còn dư, mới cân nhắc remote partitioning. Nếu DB write latency và lock wait mới là bottleneck, thêm worker/máy có thể làm job chậm hơn. Cần xác nhận qua benchmark với dataset tương đương.

## 10. Kiểm thử một thiết kế partitioning

### Các tình huống nên tái hiện

| Kiểm thử | Kỳ vọng |
| --- | --- |
| `Partitioner.partition(4)` gọi hai lần với cùng kế hoạch | Tập partition key và range giống nhau |
| Các range ở sát biên | Không có item trùng hoặc bỏ sót giữa các khoảng |
| 4 partition, executor tối đa 2 thread | Công việc được xếp lịch hữu hạn; kết quả đầy đủ |
| Một worker throw và rollback giữa chunk | StepExecution của worker báo lỗi đúng; chunk chưa commit không bị coi đã hoàn thành |
| Restart sau lỗi một partition | Partition đã thành công không bị xử lý lại trái chính sách; phần lỗi được khôi phục từ đúng context |
| Worker remote chết sau khi DB commit nhưng trước khi reply | Cơ chế timeout/reconciliation và writer idempotent không tạo double side effect |
| Cùng event được hai partition nhận | Unique business key/ledger ở đích chặn trùng, đồng thời ghi nhận lỗi overlap |
| Tăng 2 → 4 → 8 worker | Throughput tăng theo số đo; không tăng lock wait, rollback quá mức |
| Input thay đổi giữa chừng | Snapshot/cutoff/manifest nhất quán theo định nghĩa nghiệp vụ |

Đối soát kết quả bằng **tập business ID đầu vào và đầu ra**, không chỉ tổng `readCount`/`writeCount`. Với các sự kiện có hiệu ứng tiền tệ, còn phải kiểm tra tổng tiền, số event được xử lý đúng một lần và trạng thái giao dịch cuối cùng.

### Câu hỏi tự kiểm tra

Một job có manager step dùng `TaskExecutorPartitionHandler` và `gridSize = 8`. Tám partition có tên riêng, nhưng tất cả worker dùng chung reader singleton thực hiện `SELECT * FROM orders`. Job tạo ra bản ghi trùng tại đích. Nhóm kỹ thuật đề xuất đổi sang `MessageChannelPartitionHandler` để chạy trên bốn máy. Việc đổi handler có giải quyết lỗi dữ liệu không?

**Định hướng trả lời:** Không. Handler điều phối nơi thực thi, **không tự sửa predicate đọc**. Phải tạo reader theo worker `StepExecution` và sử dụng `ExecutionContext` để giới hạn mỗi partition tới tập input không giao nhau. Đồng thời, writer phải idempotent nếu retry/restart hoặc message phát lại có thể xảy ra. Chỉ sau khi tính đúng đắn được kiểm chứng mới đánh giá nên giữ local hay chuyển remote dựa trên throughput, CPU/I/O/DB và chi phí vận hành.

## Tài liệu tham khảo

- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): mô hình partitioning và các chiến lược scale.
- [Spring Batch API — PartitionHandler](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/core/partition/PartitionHandler.html): hợp đồng điều phối worker `StepExecution`.
- [Spring Batch API — TaskExecutorPartitionHandler](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/core/partition/support/TaskExecutorPartitionHandler.html): handler chạy worker bằng `TaskExecutor`.
- [Spring Batch Integration — Remote Partitioning](https://docs.spring.io/spring-batch/reference/spring-batch-integration/remote-partitioning.html): kiến trúc manager/worker với message.
- [Spring Batch Reference — Step Scope and Late Binding](https://docs.spring.io/spring-batch/reference/step/late-binding.html): bind `stepExecutionContext` cho reader theo partition.

> **Ghi nhớ:** `Partitioner` quyết định **chia việc gì**, `StepExecutionSplitter` xác định **worker execution nào cần chạy**, còn `PartitionHandler` chịu trách nhiệm **chạy ở đâu, phân phối thế nào và thu kết quả ra sao**. Muốn scale an toàn, luôn kiểm tra ranh giới dữ liệu, checkpoint/restart, thread safety, idempotency và giới hạn tài nguyên thực tế.
