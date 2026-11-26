# StepExecutionSplitter trong kiến trúc Spring Batch

> **Chương:** Partitioning
>
> **Module:** SPRING_BATCH_SCALING_OPERATIONS — Mở rộng Spring Batch cho workload dữ liệu lớn qua multi-threaded step, parallel steps, partitioning và các mô hình xử lý phân tán phù hợp. Bài học tập trung vào cách `StepExecutionSplitter` tạo và lựa chọn worker execution, giữ tính nhất quán khi retry/restart, đồng thời hỗ trợ đo nút thắt và vận hành job trên tài nguyên thực tế.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Xác định vị trí và trách nhiệm của `StepExecutionSplitter` trong kiến trúc manager–worker của Spring Batch.
2. Phân biệt `Partitioner`, `StepExecutionSplitter` và `PartitionHandler` bằng **dữ liệu đầu vào, kết quả đầu ra và thời điểm thực thi**.
3. Hiểu vì sao splitter phải kết hợp tên partition, `ExecutionContext` và lịch sử trong `JobRepository` thay vì chỉ tạo một danh sách công việc mới mỗi lần.
4. Cấu hình partitioned step sử dụng `SimpleStepExecutionSplitter` thông qua Spring Batch builder và biết khi nào cần tùy biến.
5. Chẩn đoán partition bị bỏ sót, chạy lại sai phạm vi, worker bị lỗi và vấn đề hiệu năng khi dùng local hoặc remote partitioning.

## 1. StepExecutionSplitter là thành phần nào?

Một job xử lý 20 triệu bản ghi có thể chia thành nhiều phần việc độc lập, ví dụ các dải ID hoặc các file. Trong Spring Batch, **partitioning** tạo các worker step execution để mỗi worker đọc, xử lý và ghi một phần dữ liệu.

`StepExecutionSplitter` là thành phần **chuyển kế hoạch phân vùng thành tập `StepExecution` có thể thực thi**, có xét lịch sử và quy tắc restart. Nó không tự chạy `ItemReader` hay `ItemWriter`, không chọn máy chủ để thực thi và không thay thế `Partitioner`.

~~~mermaid
flowchart TB
    J["JobExecution"] --> M["Manager PartitionStep"]
    M --> H["PartitionHandler.handle(splitter, managerExecution)"]
    H --> S["StepExecutionSplitter.split(managerExecution, gridSize)"]
    S --> P["Partitioner: Map<key, ExecutionContext>"]
    S <--> R[("JobRepository: lịch sử StepExecution<br/>và ExecutionContext")]
    S --> E["Tập worker StepExecution cần chạy"]
    E --> H
    H --> W1["Worker StepExecution: range-0000"]
    H --> W2["Worker StepExecution: range-0001"]
    H --> W3["Worker StepExecution: range-0002"]
    W1 --> R
    W2 --> R
    W3 --> R
    H --> M
~~~

Sơ đồ mô tả **luồng trách nhiệm**. Trong triển khai phổ biến, `PartitionStep` gọi `PartitionHandler.handle(...)`, handler gọi splitter để lấy worker executions, rồi phân phối những execution đó theo cách cục bộ hoặc từ xa. Không nên suy rằng manager luôn gọi `split()` trực tiếp ở ngoài handler.

### Ba thành phần có tên dễ nhầm

| Thành phần | Đầu vào | Đầu ra | Câu hỏi được giải quyết |
| --- | --- | --- | --- |
| `Partitioner` | `gridSize` và kế hoạch chia dữ liệu | `Map<String, ExecutionContext>` | **Chia việc gì?** Mỗi partition đọc tập dữ liệu nào? |
| `StepExecutionSplitter` | `manager StepExecution`, `gridSize`, lịch sử metadata và partitioner | `Set<StepExecution>` | **Worker execution nào cần chạy trong lượt này?** |
| `PartitionHandler` | Splitter và manager execution | Các worker `StepExecution` đã được xử lý/thu thập kết quả | **Chạy ở đâu, bằng cách nào và lấy kết quả ra sao?** |

Nếu partitioner tạo sai ranh giới, splitter không thể tự sửa các khoảng chồng nhau. Nếu handler có 8 thread nhưng splitter chỉ trả 3 worker executions, handler chỉ có 3 phần việc logic để chạy trong lượt đó. Nếu một partition hoàn tất trước khi job lỗi, splitter có thể nhận diện việc đó qua metadata để tránh chạy lại phần đã hoàn tất theo chính sách restart thông thường.

## 2. Hợp đồng API của StepExecutionSplitter

Giao diện `StepExecutionSplitter` thuộc Spring Batch và có hai ý chính: tên step được chia và thao tác tạo/chọn worker executions.

~~~java
// Rút gọn chữ ký API để tập trung vào hợp đồng.
public interface StepExecutionSplitter {
    String getStepName();

    Set<StepExecution> split(
            StepExecution managerStepExecution,
            int gridSize) throws JobExecutionException;
}
~~~

Trong đó:

- `managerStepExecution` là execution của **manager partition step** trong lần chạy hiện tại, qua đó xác định `JobExecution`/`JobInstance` và lịch sử cần đối chiếu.
- `gridSize` là kích thước lưới do handler cung cấp để định hướng số phần việc. Nó không bảo đảm có đúng bấy nhiêu partition và **không đồng nghĩa** số thread hoặc container chạy đồng thời.
- `Set<StepExecution>` chứa **worker step executions được chọn để thực thi**. Đây không phải `Set` các business record, cũng không phải map dữ liệu thô của partitioner.
- `getStepName()` nhận diện tên step worker mà splitter quản lý.

`StepExecution` chứa tên step, ID metadata, trạng thái, counters, `ExecutionContext` và liên kết tới `JobExecution`. Mỗi worker có checkpoint riêng trong context; reader `@StepScope` có thể truy cập các giá trị được gán như khoảng ID hoặc tên file.

### Ví dụ dữ liệu đi qua các thành phần

Partitioner tạo:

~~~text
range-0000 -> {minId: 1,     maxIdExclusive: 25001}
range-0001 -> {minId: 25001, maxIdExclusive: 50001}
range-0002 -> {minId: 50001, maxIdExclusive: 75001}
range-0003 -> {minId: 75001, maxIdExclusive: 100001}
~~~

Splitter sử dụng các key trên để xác định những worker step execution có tên logic kiểu:

~~~text
ordersWorkerStep:range-0000
ordersWorkerStep:range-0001
ordersWorkerStep:range-0002
ordersWorkerStep:range-0003
~~~

Mỗi worker execution nhận context tương ứng. Trên lần chạy đầu, nếu chưa có lịch sử và mọi partition cần thực thi, tập trả về gồm cả bốn worker. Trên lần restart, **tập cần chạy có thể ít hơn bốn** vì splitter xét lịch sử các partition đã hoàn tất. ID thực thi mới được repository cấp có thể khác lần trước, nhưng **partition key và phạm vi dữ liệu logic** phải giữ ổn định.

## 3. SimpleStepExecutionSplitter làm gì?

`SimpleStepExecutionSplitter` là implementation thường dùng trong partitioned step của Spring Batch. Nó kết hợp `Partitioner` với `JobRepository` để quản lý các `StepExecution` tương ứng với từng partition.

Có thể hiểu công việc của splitter theo các pha sau:

1. **Xác định identity của các partition.** Tên partition do `Partitioner` cung cấp; ở một số đường đi restart, `PartitionNameProvider` có thể chỉ cung cấp danh sách tên để tránh dựng lại toàn bộ context.
2. **Đối chiếu metadata.** Dựa trên `JobInstance` hiện tại và tên worker step/partition để tìm lịch sử thực thi liên quan trong `JobRepository`.
3. **Chọn các partition cần thực thi.** Partition chưa từng chạy, bị lỗi hoặc chưa hoàn tất có thể được chọn theo chính sách restart. Partition hoàn tất thường không cần chạy lại, trừ khi chính sách như `allowStartIfComplete` cho phép.
4. **Tạo worker StepExecution thích hợp.** Execution mới thuộc `JobExecution` hiện tại, mang identity partition và context đúng với phần việc. Với partition chạy lại, trạng thái checkpoint đã lưu cần được kế thừa phù hợp.
5. **Trả tập execution cho handler.** `PartitionHandler` quyết định thực thi local hay remote và thu trạng thái từ worker.

Chi tiết nội bộ của các bước trên phụ thuộc phiên bản Spring Batch và cấu hình restart. Đây là **mô hình tư duy vận hành**, không phải mã nguồn giả định chạy nguyên xi trong mọi phiên bản.

### Sơ đồ một lần chạy và lần restart

~~~mermaid
sequenceDiagram
    participant P as PartitionStep
    participant H as PartitionHandler
    participant S as StepExecutionSplitter
    participant R as JobRepository
    participant W as Worker step
    P->>H: handle(splitter, managerExecution)
    H->>S: split(managerExecution, gridSize)
    S->>R: Kiểm tra lịch sử theo tên partition
    R-->>S: StepExecution trước đó + status/context
    S-->>H: Worker executions cần chạy
    H->>W: Thực thi các worker được chọn
    W->>R: Commit/checkpoint/cập nhật status
    W-->>H: Trạng thái worker
    H-->>P: Kết quả đã thu thập
~~~

Nếu `Partitioner` liên tục đổi key hoặc cùng một key lại chỉ tới dữ liệu khác trên restart, splitter không thể tự nhận biết đúng ý nghĩa nghiệp vụ. Nó thấy **tên và metadata**, nên **kế hoạch chia dữ liệu phải ổn định** trong cùng tập công việc cần khôi phục.

## 4. Tên partition và ExecutionContext quyết định khả năng restart

Tên partition là key của `Map<String, ExecutionContext>`. Key này cần **duy nhất trong kết quả một lần partition** và **ổn định theo cùng công việc logic** qua restart.

| Yếu tố | Điều cần giữ | Lỗi nếu thay đổi tùy tiện |
| --- | --- | --- |
| Tên partition | Ví dụ `range-0002` luôn đại diện cùng phần việc trong một kế hoạch | Splitter khó ghép lịch sử worker execution chính xác |
| Ranh giới dữ liệu | `[minIdInclusive, maxIdExclusive)` cố định theo partition | Trùng hoặc mất item khi resume/checkpoint |
| Nguồn dữ liệu | Snapshot, file manifest, watermark hoặc phiên bản input xác định | Restart đọc tập dữ liệu khác lượt trước |
| Trạng thái checkpoint | `ExecutionContext` của worker gắn với partition đúng | Reader tiếp tục từ vị trí không thuộc phần việc hiện tại |
| Điều kiện ghi | Business key và quy tắc idempotency ổn định | Retry có thể nhân đôi tác dụng phụ |

Hai partition có tên **khác nhau** vẫn có thể đọc cùng ID nếu câu SQL lọc sai. Ngược lại, hai lần `put("range-0000", ...)` vào cùng `Map` chỉ để lại **một** entry, vì `Map` ghi đè key cũ. Unique partition key giúp splitter định danh phần việc nhưng **không tự bảo đảm dữ liệu được phân vùng đúng**.

Nên dùng khoảng nửa mở:

~~~sql
SELECT id, order_code
FROM orders
WHERE id >= :minId
  AND id < :maxIdExclusive
ORDER BY id;
~~~

Ví dụ `[1, 25_001)` và `[25_001, 50_001)` không giao nhau. `ORDER BY id` phải dựa vào khóa sắp xếp **duy nhất và ổn định** nếu dùng reader paging và cần restart. Còn nếu dữ liệu nguồn thay đổi giữa các thời điểm worker đọc, việc chia range không thay thế snapshot hoặc watermark.

### Vì sao UUID ngẫu nhiên là lựa chọn sai trong trường hợp phổ biến?

Nếu mỗi lần `partition()` được gọi, code tạo `UUID.randomUUID()` mới làm partition key, các tên của lần restart có thể **không khớp lịch sử**. Splitter sẽ không có identity ổn định để nhận diện đúng phần đã hoàn tất. Có thể dùng UUID **đã được tạo một lần và lưu bền vững trong manifest**; vấn đề là sinh lại tên trong mỗi lần retry/restart, không phải bản thân kiểu UUID.

`PartitionNameProvider` hữu ích khi việc dựng đầy đủ các context partition tốn kém. Trong trường hợp có hỗ trợ này, tập tên cung cấp khi restart **phải khớp** tên đã tạo ban đầu. Nó giúp tối ưu bước xác định identity nhưng không sửa partition overlap hoặc thay thế lưu checkpoint.

## 5. Ví dụ Java: cấu hình splitter thông qua manager builder

Ở ứng dụng Spring Batch 5.x, cách cấu hình phổ biến là cung cấp `Partitioner` và worker `Step` cho `StepBuilder`. Framework thiết lập splitter và handler phù hợp theo builder.

Ví dụ minh họa dưới đây cố định bốn range để tập trung vào quan hệ **partitioner → splitter → handler**. Trong production, các ranh giới cần lấy từ kế hoạch dữ liệu/snapshot được lưu bền vững cho `JobInstance`.

~~~java
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

import org.springframework.batch.core.Step;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class OrdersPartitionConfig {

    @Bean
    Partitioner ordersPartitioner() {
        return gridSize -> {
            Map<String, ExecutionContext> result = new LinkedHashMap<>();

            for (int i = 0; i < 4; i++) {
                long minId = 1L + i * 25_000L;
                long maxIdExclusive = minId + 25_000L;
                String key = String.format(Locale.ROOT, "range-%04d", i);

                ExecutionContext context = new ExecutionContext();
                context.putLong("minId", minId);
                context.putLong("maxIdExclusive", maxIdExclusive);

                if (result.putIfAbsent(key, context) != null) {
                    throw new IllegalStateException("Trùng partition key: " + key);
                }
            }

            return result;
        };
    }

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
}
~~~

**Ở cấu hình này:**

- `ordersPartitioner` trả về `Map` có key duy nhất và context chứa khoảng ID.
- Partitioned step builder thiết lập logic chia worker execution, thường sử dụng `SimpleStepExecutionSplitter`; không cần tự gọi `split()` trong service của ứng dụng.
- Handler cục bộ đưa worker executions tới `TaskExecutor`. Bốn partition không có nghĩa sẽ chạy nhanh gấp bốn lần: CPU, bộ nhớ, database pool và chi phí I/O quyết định thông lượng.
- `ordersWorkerStep` là bean step được định nghĩa riêng, ví dụ chunk step đọc theo `ExecutionContext`, có transaction, processor và writer phù hợp.
- `gridSize(4)` chỉ là một gợi ý; ví dụ dùng kế hoạch cố định bốn range để giữ identity khi restart. Trong bài toán thực tế cần giải thích quy tắc tạo partition khi số lượng worker hoặc dữ liệu thay đổi.

### Reader dùng đúng phạm vi được splitter gắn vào worker

Mỗi worker `StepExecution` cần reader riêng theo phạm vi mà partitioner đã khai báo:

~~~java
@Bean
@StepScope
JdbcPagingItemReader<OrderRow> ordersByRangeReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxIdExclusive']}") Long maxId) {

    return new JdbcPagingItemReaderBuilder<OrderRow>()
            .name("ordersByRangeReader")
            .dataSource(dataSource)
            .selectClause("SELECT id, order_code")
            .fromClause("FROM orders")
            .whereClause("WHERE id >= :minId AND id < :maxId")
            .parameterValues(
                    Map.of("minId", minId, "maxId", maxId))
            .sortKeys(Map.of("id", Order.ASCENDING))
            .rowMapper((rs, rowNum) -> new OrderRow(
                    rs.getLong("id"),
                    rs.getString("order_code")))
            .pageSize(500)
            .saveState(true)
            .build();
}
~~~

Ví dụ này giả định `OrderRow` là kiểu dữ liệu nghiệp vụ, `orders.id` duy nhất và reader được import từ `org.springframework.batch.item.database` / `...builder`; `Order` là enum thứ tự sắp xếp từ Spring Batch JDBC. `@StepScope` và `@Value` do Spring Framework cung cấp. Cấu hình worker step/transaction manager/writer được lược bớt để tập trung vào việc tiêu thụ partition context.

`@StepScope` tạo bean theo **worker StepExecution**, giúp mỗi partition có reader và checkpoint riêng. Nếu chính worker step lại dùng **multi-threaded chunk step**, các thread bên trong worker có thể chia sẻ một reader step-scoped; vẫn cần kiểm tra thread safety riêng.

### Trường hợp cần cấu hình SimpleStepExecutionSplitter tường minh

Khi tự dựng `PartitionStep` hoặc viết `PartitionHandler` đặc thù, có thể làm việc trực tiếp với `SimpleStepExecutionSplitter`. Đây là mẫu định hướng cho nhánh tích hợp nâng cao:

~~~java
StepExecutionSplitter splitter = new SimpleStepExecutionSplitter(
        jobRepository,
        false,                 // allowStartIfComplete
        "ordersWorkerStep",
        ordersPartitioner);

// Handler được manager gọi và sẽ dùng splitter để chọn worker executions.
Collection<StepExecution> results =
        partitionHandler.handle(splitter, managerStepExecution);
~~~

Đoạn trên biểu diễn **một phần trong framework/tầng cấu hình nâng cao**, không phải lệnh cần đặt vào mọi `@Bean`/business service hoặc gọi lại tùy ý. Các biến `managerStepExecution` và `partitionHandler` là ngữ cảnh do cơ chế chạy step cung cấp. Nếu dùng builder chuẩn ở ví dụ trước, tránh tạo thêm splitter riêng làm trùng luồng điều phối.

## 6. Restart: splitter phải xét lịch sử thay vì chia lại mù quáng

Xét job nhập bốn dải dữ liệu với cùng một `JobInstance`:

| Partition key | Phạm vi | Lần chạy đầu | Trong lần restart thông thường |
| --- | --- | --- | --- |
| `range-0000` | `[1, 25001)` | `COMPLETED` | Không chọn chạy lại nếu chính sách không yêu cầu |
| `range-0001` | `[25001, 50001)` | `FAILED` | Tạo/chọn execution phù hợp để chạy lại |
| `range-0002` | `[50001, 75001)` | `COMPLETED` | Không chọn chạy lại nếu chính sách không yêu cầu |
| `range-0003` | `[75001, 100001)` | `STOPPED` | Được xét tiếp tục theo chính sách restart |

Trong trường hợp giả định này, splitter có thể trả về các worker executions cần chạy cho `range-0001` và `range-0003`. Kết quả cụ thể tùy trạng thái đã lưu, cấu hình restart và các ngoại lệ như `allowStartIfComplete`. Điểm mấu chốt: **không tự động chạy lại cả bốn chỉ vì manager được khởi động lại**.

### Những tình huống cần phân biệt

**Chunk rollback rồi retry:** Worker `StepExecution` có thể thử lại một chunk theo chính sách retry/skip của step. Đây là cơ chế xử lý lỗi *bên trong worker*, không có nghĩa splitter được gọi cho mỗi lần retry item.

**Worker bị lỗi, job restart:** Tạo `JobExecution` mới cho cùng `JobInstance` (nếu job cho phép restart). Splitter dựa vào metadata để xác định worker cần tiếp tục/chạy lại. `StepExecutionId` của lần chạy mới có thể khác nhưng partition name phải ổn định.

**Một partition đã hoàn tất:** Có thể được bỏ qua khi restart theo mặc định; cấu hình `allowStartIfComplete` ảnh hưởng đến quyết định này. Không nên bật chạy lại partition hoàn tất chỉ để “an toàn hơn” khi writer không idempotent.

**Manager không nhận được phản hồi từ worker:** Có thể có tình huống worker đã commit một số chunk nhưng manager vẫn chờ hoặc mất kết nối. Trước khi phát lại công việc từ xa, cần kiểm tra metadata và cơ chế chống chạy chồng/ghi trùng.

**Chạy lại cùng dữ liệu dưới JobInstance mới:** Các execution cũ không tự đóng vai trò dedupe cho một `JobInstance` khác. Nếu nghiệp vụ cho phép chạy lại nguồn, writer vẫn cần khóa idempotency để kiểm soát bản ghi đã xử lý.

### Lỗi restart do đổi kế hoạch phân vùng

Giả sử ban đầu `range-0001` đại diện `[25_001, 50_001)`, checkpoint tại ID 39.000. Sau sự cố, ai đó sửa code để cùng key `range-0001` đại diện `[40_001, 80_001)`. Dù splitter nhận đúng tên từ repository, **checkpoint cũ và miền dữ liệu mới không còn khớp nhau**; có thể bỏ sót hoặc xử lý trùng.

Do đó phải lưu kế hoạch partition theo phiên bản input, danh sách file hoặc watermark ổn định. Nếu nhất thiết phải chia lại, đó là **kế hoạch xử lý mới** với chiến lược replay/idempotency được xác định rõ.

## 7. StepExecutionSplitter trong remote partitioning

Khi manager và worker ở các JVM khác nhau, **splitter thường vẫn chạy ở phía manager**. Handler có thể sử dụng `MessageChannelPartitionHandler` để gửi yêu cầu cho worker qua Spring Integration/message broker.

~~~mermaid
flowchart LR
    M["Manager JVM"] --> S["StepExecutionSplitter"]
    S <--> R[("JobRepository dùng chung")]
    S --> H["MessageChannelPartitionHandler"]
    H --> Q["Broker / request channel"]
    Q --> A["Worker JVM A"]
    Q --> B["Worker JVM B"]
    A --> R
    B --> R
    A --> D[("Database / đích")]
    B --> D
~~~

Ở mô hình này, splitter vẫn trả tập `StepExecution` cần chạy. Handler quyết định cách gửi yêu cầu; worker cần nhận diện `StepExecution`/context tương ứng và thực thi worker step có tên thích hợp. Có thể dùng kênh phản hồi hoặc cơ chế theo dõi repository tùy cấu hình tích hợp.

**Không nhầm với remote chunking:** Remote partitioning gửi **yêu cầu chạy partition/worker step**; remote chunking gửi **các chunk item** do manager đọc. Splitter gắn với luồng *partition execution*, không phải một bộ chia dữ liệu chunk ở cấp item.

Khi nhiều JVM cùng làm việc, vấn đề vận hành không chỉ là chia đúng key:

- Broker có thể phát lại request hoặc mất acknowledgement; phải thiết kế dedupe/claim và cách xử lý kết quả chưa rõ ràng.
- Nhiều worker ghi chung database; unique constraint, transaction và idempotency giúp giảm nguy cơ ghi trùng.
- `JobRepository` phải đủ nhất quán để manager/worker quan sát trạng thái execution; thiết kế remote thường yêu cầu backend repository dùng chung.
- Retry/restart cần giới hạn khả năng **hai worker cùng xử lý một partition** tại một thời điểm, nhất là khi có timeout và mạng chập chờn.
- `gridSize`, broker queue và số worker slot là những đại lượng khác nhau; tăng số partition không tự tăng năng lực của database đích.

## 8. Tìm bottleneck và đo kết quả của splitter

Splitter chủ yếu tạo/chọn **metadata execution**, nên chi phí của nó thường nhỏ hơn thời gian đọc/xử lý/ghi dữ liệu. Tuy nhiên, với số partition rất lớn hoặc repository chậm, chi phí lập kế hoạch và điều phối có thể đáng kể.

| Triệu chứng | Khả năng cần kiểm tra | Hướng quan sát |
| --- | --- | --- |
| Job lâu mới bắt đầu chạy worker | Tạo nhiều partition, truy vấn metadata chậm, kết nối repository thiếu | Thời gian partition/split, latency JobRepository |
| Manager chờ nhưng ít worker hoạt động | Handler/executor/broker thiếu slot hoặc worker bị lỗi | Thread active, queue depth, status worker |
| Restart chạy lại cả vùng đã xử lý | Partition key thay đổi, metadata không khớp, `allowStartIfComplete` | So sánh key/context/status theo JobInstance |
| Có vùng dữ liệu không được đọc | Key trùng làm ghi đè, range hở, partitioner sinh thiếu | Kiểm tra map key và đối soát input |
| Các worker ghi trùng item | Range giao nhau, shared reader hoặc replay không idempotent | Kiểm tra predicate/unique business key |
| Một số partition chạy quá lâu | Phân phối dữ liệu lệch, query plan, lock contention | Duration, read/write count và DB wait theo partition |
| Tăng grid size nhưng job không nhanh hơn | Nút thắt ở CPU/IO/connection pool hoặc overhead tăng | Benchmark concurrency với dataset cố định |

Nên đo ít nhất:

1. **Thời gian chuẩn bị:** Từ manager bắt đầu đến khi worker đầu tiên được thực thi; khi cần thì tách thời gian partition/split và dispatch.
2. **Tiến độ worker:** `readCount`, `writeCount`, `filterCount`, skip và `rollbackCount` theo từng `StepExecution`, kèm thời gian và trạng thái.
3. **Tính đúng:** Số business ID duy nhất đầu vào/đầu ra, duplicate/no-op, checksum hoặc các bất biến nghiệp vụ.
4. **Hạ tầng:** CPU, heap/GC, thread pool, connection pool, disk/network, broker lag và thời gian chờ DB.
5. **Khả năng phục hồi:** Có bao nhiêu partition `COMPLETED`, `FAILED`, `STOPPED` và cần retry sau restart.

`readCount` và `writeCount` là **counter theo StepExecution**, không chứng minh số hàng database thực sự thay đổi. Manager step có thể có counters rất khác các worker; khi tổng hợp qua restart phải phân biệt khối lượng công việc đã thử với kết quả nghiệp vụ **duy nhất**.

## 9. Kiểm thử tính đúng đắn của splitter

Một bộ kiểm thử hữu ích nên bao gồm cả kế hoạch phân vùng, repository và việc chạy worker:

| Tình huống | Kiểm tra mong đợi |
| --- | --- |
| Tạo partition lần đầu | Mỗi key duy nhất, context đúng, đủ input, không overlap |
| `gridSize` là 8 nhưng partitioner có 4 range cố định | Chỉ có 4 phần việc logic; không tự phát sinh thêm 4 vùng |
| Partition hoàn tất trước sự cố | Không chạy lại trái chính sách trong cùng JobInstance |
| Partition bị lỗi rồi restart | Worker mới đúng partition key, có checkpoint/context phù hợp |
| Key hoặc range vô tình đổi khi restart | Phát hiện và ngăn kế hoạch không nhất quán |
| Hai partition dùng chung business ID | Đối soát phát hiện overlap dù key khác nhau |
| Reader dùng `@StepScope` | Mỗi worker nhận đúng phạm vi của context và không chia sẻ cursor ngoài ý muốn |
| Local handler chỉ có 2 thread cho 8 partition | Handler xếp lịch hữu hạn; các worker vẫn hoàn tất |
| Broker gửi lại yêu cầu partition | Hệ thống chống chạy chồng/ghi trùng và báo trạng thái chính xác |
| Source thay đổi giữa lần chạy và restart | Snapshot/cutoff/manifest theo JobInstance duy trì tập input nhất quán |

### Một tình huống thực hành

Job nhập đơn hàng theo bốn range. Lần đầu:

~~~text
ordersWorkerStep:range-0000  COMPLETED
ordersWorkerStep:range-0001  COMPLETED
ordersWorkerStep:range-0002  FAILED
ordersWorkerStep:range-0003  STOPPED
~~~

Sau đó nhóm vận hành khởi động lại job. Hãy trả lời:

1. Thành phần nào quyết định `range-0002` và `range-0003` có cần thực thi lại?
2. Thành phần nào thực sự cấp thread hoặc gửi request tới worker?
3. Điều gì xảy ra nếu lần restart đổi tên `range-0002` thành một UUID mới?
4. Có thể suy ra job không ghi trùng chỉ vì splitter bỏ qua những partition đã `COMPLETED` không?

**Định hướng đáp án:** `StepExecutionSplitter` phối hợp với metadata/restart policy để chọn worker executions; `PartitionHandler` chịu trách nhiệm thực thi/phân phối. Key mới làm mất liên kết identity với partition cũ; nguy cơ xử lý lại sai hoặc thừa. Dù metadata đúng, writer vẫn cần idempotency cho replay, overlap hoặc side effect ngoài transaction.

## 10. Checklist chọn cách triển khai

Trước khi tăng số partition hoặc chuyển từ local sang remote, hãy kiểm tra:

- **Kế hoạch chia dữ liệu:** Tên partition ổn định, phạm vi không trùng/không hở, dữ liệu nguồn được chốt theo snapshot hoặc watermark khi cần.
- **Metadata và restart:** `JobRepository` hoạt động ổn định, context được lưu đúng, những partition đã hoàn thành được nhận diện theo chính sách.
- **Handler:** Local `TaskExecutorPartitionHandler` hay remote `MessageChannelPartitionHandler` phù hợp CPU/I/O, số worker, network và khả năng vận hành.
- **Worker:** Reader/processor/writer chịu được concurrency; `@StepScope` được dùng đúng nơi cần tạo state riêng theo worker.
- **Dữ liệu đích:** Dedupe/idempotency, transaction và business key bảo vệ trước retry hoặc replay.
- **Hiệu năng:** Có benchmark cùng dataset với 1, 2, 4, 8 worker và chỉ số về CPU, DB pool, I/O, rollback, thời gian hoàn thành.
- **Đối soát:** Dashboard thể hiện tiến độ theo partition, nhưng kết luận đủ/đúng phải dựa trên business ID ở nguồn và đích.

## Tài liệu tham khảo

- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): partitioning, manager/worker và cơ chế scale.
- [Spring Batch API — StepExecutionSplitter](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/core/partition/StepExecutionSplitter.html): hợp đồng `split()` và `getStepName()`.
- [Spring Batch API — SimpleStepExecutionSplitter](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/core/partition/support/SimpleStepExecutionSplitter.html): implementation dựa vào partitioner và repository.
- [Spring Batch API — PartitionHandler](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/core/partition/PartitionHandler.html): hợp đồng điều phối worker executions.
- [Spring Batch Reference — Step Scope and Late Binding](https://docs.spring.io/spring-batch/reference/step/late-binding.html): truy cập `stepExecutionContext` trong worker.
- [Spring Batch Integration — Remote Partitioning](https://docs.spring.io/spring-batch/reference/spring-batch-integration/remote-partitioning.html): cơ chế phân phối worker qua message.

> **Ghi nhớ:** `Partitioner` định nghĩa **những phần việc tồn tại**, `StepExecutionSplitter` xác định **execution nào cần chạy trong lượt hiện tại dựa trên metadata và chính sách restart**, còn `PartitionHandler` tổ chức **việc thực thi và thu kết quả**. Muốn scale an toàn, giữ identity và input của partition ổn định, kiểm tra concurrency và đối soát dữ liệu sau retry/restart.
