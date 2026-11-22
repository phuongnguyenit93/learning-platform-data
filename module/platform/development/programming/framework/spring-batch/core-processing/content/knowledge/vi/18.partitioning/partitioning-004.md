# PartitionHandler trong Spring Batch

Trong Spring Batch, partitioning chia một step lớn thành nhiều phần việc độc lập. Mỗi phần được biểu diễn bằng một `StepExecution` riêng và có thể chạy trên một thread hoặc worker khác. `PartitionHandler` là thành phần chịu trách nhiệm thực thi các phần việc đó và thu thập kết quả để step điều phối (manager step) biết chúng đã hoàn tất, thất bại hay còn đang chạy.

`Partitioner` xác định cách chia dữ liệu; `StepExecutionSplitter` tạo các execution tương ứng; còn `PartitionHandler` quyết định những execution đó được chạy ở đâu và bằng cách nào. Hiểu đúng vai trò của handler giúp chọn giữa chạy song song trong cùng JVM và remote partitioning trên nhiều tiến trình/máy, đồng thời kiểm soát concurrency, restart và lỗi của từng partition.

## 1. Partitioning và mô hình manager/worker

Partitioning phù hợp khi một step có thể chia thành các phần dữ liệu độc lập. Ví dụ, job cần xử lý một triệu khách hàng. Thay vì một worker xử lý toàn bộ dữ liệu, ứng dụng có thể chia thành các dải ID và giao mỗi dải cho một worker step.

```text
Parent Job
    |
    v
Manager Step
    |
    +-- Partitioner xác định các vùng dữ liệu
    |
    +-- StepExecutionSplitter tạo các StepExecution
    |
    v
PartitionHandler
    |
    +---- Partition 0 -> Worker Step (ID 1..250000)
    +---- Partition 1 -> Worker Step (ID 250001..500000)
    +---- Partition 2 -> Worker Step (ID 500001..750000)
    +---- Partition 3 -> Worker Step (ID 750001..1000000)
    |
    v
Manager tổng hợp kết quả các worker
    |
    v
Manager Step hoàn tất hoặc thất bại
```

Manager step điều phối. Worker step thực hiện logic đọc, xử lý và ghi dữ liệu. Mỗi partition có `StepExecution` và `ExecutionContext` riêng, nhờ đó worker có thể nhận tham số phạm vi dữ liệu riêng.

Partitioning thường giúp tăng throughput khi các phần dữ liệu độc lập, có thể xử lý đồng thời và không tranh chấp tài nguyên quá nhiều. Nó không tự động làm cho một thuật toán tuần tự trở nên song song; dữ liệu và thao tác nghiệp vụ phải có thể chia tách an toàn.

## 2. PartitionHandler là gì?

`PartitionHandler` là abstraction chịu trách nhiệm thực thi các `StepExecution` đã được tách ra. Nó nhận `StepExecutionSplitter` cùng `StepExecution` của manager, yêu cầu splitter tạo các execution con, điều phối chúng và trả về collection các kết quả.

Hợp đồng API ở mức khái niệm:

```java
public interface PartitionHandler {

    Collection<StepExecution> handle(
        StepExecutionSplitter stepExecutionSplitter,
        StepExecution stepExecution
    ) throws Exception;
}
```

Hai tham số có vai trò khác nhau:

- `StepExecutionSplitter` tạo các `StepExecution` cho từng partition dựa trên manager execution, partitioner và metadata repository.
- `StepExecution` được truyền vào là execution của manager step, làm ngữ cảnh để tạo các worker execution.

Handler không quyết định dữ liệu nào thuộc partition nào; việc đó thuộc `Partitioner`. Handler tập trung vào cách dispatch và thu thập kết quả. Với handler chạy local, các worker có thể chạy bằng `TaskExecutor`. Với remote partitioning, handler gửi yêu cầu đến worker qua middleware và chờ kết quả theo cơ chế tích hợp.

## 3. Phân biệt các thành phần trong partitioning

| Thành phần | Trách nhiệm |
| --- | --- |
| `Partitioner` | Tạo map tên partition sang `ExecutionContext` chứa dữ liệu/phạm vi dành cho worker. |
| `StepExecutionSplitter` | Tạo hoặc khôi phục các worker `StepExecution` dựa trên partition metadata và trạng thái restart. |
| `PartitionHandler` | Điều phối việc thực thi worker execution và thu thập kết quả. |
| Manager step | Điều phối toàn bộ partitioning trong flow của job. |
| Worker step | Thực hiện logic nghiệp vụ cho một partition cụ thể. |
| `JobRepository` | Lưu trạng thái manager execution, worker execution và context liên quan. |

Ví dụ, `Partitioner` tạo `partition0` với `minId=1`, `maxId=1000`; handler nhận execution tương ứng và chạy worker step; worker reader lấy hai giá trị đó từ step execution context để chỉ đọc phần dữ liệu của partition.

## 4. PartitionHandler được sử dụng ở đâu?

Trong cấu hình job, handler được gắn với manager step. Với API builder của Spring Batch 5, có thể cấu hình như sau:

```java
@Bean
Step managerStep(JobRepository jobRepository,
                 Partitioner customerPartitioner,
                 PartitionHandler customerPartitionHandler) {
    return new StepBuilder("managerStep", jobRepository)
        .partitioner("customerWorkerStep", customerPartitioner)
        .partitionHandler(customerPartitionHandler)
        .build();
}
```

`partitioner("customerWorkerStep", ...)` chỉ định tên step worker và thành phần chia partition. `.partitionHandler(...)` cung cấp cơ chế thực thi các worker execution.

Một cách cấu hình khác là dùng builder convenience methods như `.step(workerStep).gridSize(...).taskExecutor(...)` khi muốn Spring Batch tạo handler local dựa trên `TaskExecutor`. Dùng handler tường minh hữu ích khi cần tùy chỉnh cách dispatch hoặc chọn implementation khác.

## 5. TaskExecutorPartitionHandler: chạy partition trong cùng JVM

`TaskExecutorPartitionHandler` là implementation phổ biến để chạy các partition bằng `TaskExecutor`. Các worker step chạy trong cùng tiến trình ứng dụng, thường trên các thread khác nhau.

```java
@Bean
TaskExecutor partitionTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(0);
    executor.setThreadNamePrefix("batch-partition-");
    return executor;
}

@Bean
TaskExecutorPartitionHandler customerPartitionHandler(
        Step customerWorkerStep,
        TaskExecutor partitionTaskExecutor) {

    TaskExecutorPartitionHandler handler =
        new TaskExecutorPartitionHandler();
    handler.setStep(customerWorkerStep);
    handler.setTaskExecutor(partitionTaskExecutor);
    handler.setGridSize(4);
    return handler;
}
```

Sau đó manager step dùng `customerPartitionHandler` như ví dụ trước. `TaskExecutorPartitionHandler` sẽ thực thi worker step theo các partition execution được splitter tạo.

Ưu điểm của cách chạy local:

- Cấu hình đơn giản, không cần broker hoặc messaging middleware.
- Dễ debug trong một tiến trình và thuận tiện cho integration test.
- Có thể dùng chung bean infrastructure, datasource và metadata repository.
- Phù hợp khi tải có thể xử lý trên một máy và tài nguyên máy đủ đáp ứng.

Giới hạn là tất cả worker vẫn dùng CPU, heap, connection pool và tài nguyên của cùng JVM/host. Nếu cần mở rộng qua nhiều máy hoặc cô lập worker theo tiến trình, remote partitioning phù hợp hơn.

## 6. MessageChannelPartitionHandler: remote partitioning

Khi cần chạy worker trên các tiến trình hoặc máy khác nhau, có thể dùng remote partitioning. Manager gửi thông tin yêu cầu thực thi partition qua messaging middleware; worker nhận yêu cầu, thực hiện step và cập nhật kết quả.

Trong hệ sinh thái Spring Batch, `MessageChannelPartitionHandler` là một implementation phục vụ mô hình này, thường được sử dụng cùng Spring Integration và message channel. Worker side có thành phần xử lý `StepExecutionRequest` để chạy step được chỉ định.

```text
Manager application
  Manager Step
      |
      v
  Partitioner + StepExecutionSplitter
      |
      v
  MessageChannelPartitionHandler
      |
      v
  Queue / Message Broker
      |
      +-----------------------------+
      |              |              |
      v              v              v
 Worker node 1   Worker node 2   Worker node 3
      |              |              |
      v              v              v
  Worker Step    Worker Step    Worker Step
      |              |              |
      +--------------+--------------+
                     |
                     v
          Metadata/result coordination
                     |
                     v
                Manager tiếp tục
```

Remote partitioning phù hợp khi cần mở rộng số worker độc lập, dùng nhiều máy hoặc triển khai worker theo năng lực riêng. Đổi lại, hệ thống cần quản lý broker, serialization message, lỗi mạng, timeout, worker availability và tính nhất quán của metadata.

Trong mô hình remote phổ biến, manager và worker cần truy cập được metadata repository dùng chung hoặc cơ chế repository được thiết kế tương thích để worker execution được ghi nhận và manager có thể theo dõi kết quả. Cần bảo đảm cấu hình schema, table prefix và phiên bản Spring Batch tương thích giữa các node.

Remote partitioning khác remote chunking. Trong remote partitioning, mỗi worker chạy một step độc lập trên một partition dữ liệu. Trong remote chunking, manager thường đọc và phân phối chunk cho worker xử lý; ranh giới phân chia công việc và trách nhiệm đọc/ghi khác nhau.

## 7. Tạo các partition bằng Partitioner

`Partitioner` trả về một `Map<String, ExecutionContext>`. Mỗi key là tên partition; mỗi value chứa dữ liệu mà worker cần để xử lý phần tương ứng.

Ví dụ chia một dải ID từ 1 đến 10.000:

```java
public class CustomerRangePartitioner implements Partitioner {

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize < 1) {
            throw new IllegalArgumentException("gridSize must be positive");
        }

        long minId = 1L;
        long maxId = 10_000L;
        long total = maxId - minId + 1;
        long targetSize = (total + gridSize - 1) / gridSize;

        Map<String, ExecutionContext> partitions = new LinkedHashMap<>();
        long start = minId;
        int partitionNumber = 0;

        while (start <= maxId) {
            long end = Math.min(start + targetSize - 1, maxId);

            ExecutionContext context = new ExecutionContext();
            context.putLong("minId", start);
            context.putLong("maxId", end);

            partitions.put("partition" + partitionNumber, context);
            start = end + 1;
            partitionNumber++;
        }

        return partitions;
    }
}
```

Với `gridSize=4`, partitioner tạo bốn vùng có kích thước gần bằng nhau. Ví dụ dùng khoảng bao gồm cả hai đầu mút (`minId` và `maxId`), nên worker query cần dùng điều kiện `BETWEEN` hoặc điều kiện tương đương.

Trong production, `minId` và `maxId` nên được lấy từ dữ liệu hoặc snapshot nghiệp vụ thực tế, không hard-code. Nếu dữ liệu rỗng, partitioner cần có hành vi rõ ràng, chẳng hạn trả về map rỗng hoặc tạo một partition no-op tùy yêu cầu vận hành và cách ứng dụng muốn biểu diễn step không có dữ liệu.

## 8. Worker đọc phạm vi từ StepExecutionContext

Mỗi worker cần nhận đúng phạm vi mà partitioner đã gán. `@StepScope` cho phép tạo reader theo từng `StepExecution` và lấy giá trị từ step execution context bằng SpEL.

```java
@Bean
@StepScope
JdbcCursorItemReader<Customer> customerReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    return new JdbcCursorItemReaderBuilder<Customer>()
        .name("customerReader")
        .dataSource(dataSource)
        .sql("""
            select id, name
            from customer
            where id between ? and ?
            order by id
            """)
        .preparedStatementSetter(ps -> {
            ps.setLong(1, minId);
            ps.setLong(2, maxId);
        })
        .rowMapper(new BeanPropertyRowMapper<>(Customer.class))
        .saveState(true)
        .build();
}
```

Reader được khởi tạo theo từng worker execution nên mỗi partition nhận `minId` và `maxId` riêng. Không nên dùng một singleton reader có mutable cursor chung cho tất cả partition, vì các worker có thể ghi đè trạng thái đọc của nhau.

Worker step có thể được khai báo như step chunk thông thường:

```java
@Bean
Step customerWorkerStep(JobRepository jobRepository,
                        PlatformTransactionManager transactionManager,
                        ItemReader<Customer> customerReader,
                        ItemProcessor<Customer, CustomerSummary> processor,
                        ItemWriter<CustomerSummary> writer) {
    return new StepBuilder("customerWorkerStep", jobRepository)
        .<Customer, CustomerSummary>chunk(200, transactionManager)
        .reader(customerReader)
        .processor(processor)
        .writer(writer)
        .build();
}
```

Mỗi partition chạy cùng định nghĩa worker step nhưng có `StepExecution` và step context riêng. Các bean không step-scoped vẫn có thể được chia sẻ giữa các worker; nếu chúng chứa state mutable, cần bảo đảm thread safety hoặc chuyển chúng thành scope phù hợp.

## 9. Cấu hình manager step hoàn chỉnh

Kết hợp partitioner, worker step và handler:

```java
@Bean
Partitioner customerPartitioner() {
    return new CustomerRangePartitioner();
}

@Bean
Step customerManagerStep(JobRepository jobRepository,
                          Partitioner customerPartitioner,
                          PartitionHandler customerPartitionHandler) {
    return new StepBuilder("customerManagerStep", jobRepository)
        .partitioner("customerWorkerStep", customerPartitioner)
        .partitionHandler(customerPartitionHandler)
        .build();
}

@Bean
Job customerImportJob(JobRepository jobRepository,
                       Step customerManagerStep) {
    return new JobBuilder("customerImportJob", jobRepository)
        .start(customerManagerStep)
        .build();
}
```

Tên `"customerWorkerStep"` trong `.partitioner(...)` phải khớp với tên worker step được handler sử dụng. Giữ tên partition ổn định để metadata và restart có thể nhận diện các execution tương ứng.

Với cấu hình đơn giản, có thể dùng builder API để khai báo worker step, grid size và task executor trực tiếp:

```java
@Bean
Step customerManagerStep(JobRepository jobRepository,
                         Step customerWorkerStep,
                         Partitioner customerPartitioner,
                         TaskExecutor partitionTaskExecutor) {
    return new StepBuilder("customerManagerStep", jobRepository)
        .partitioner(customerWorkerStep.getName(), customerPartitioner)
        .step(customerWorkerStep)
        .gridSize(4)
        .taskExecutor(partitionTaskExecutor)
        .build();
}
```

Cách này để builder tạo cấu hình partition handler local từ worker step và task executor. Chọn một cách cấu hình rõ ràng; không cần đồng thời gắn một handler tường minh và các convenience settings cho cùng manager step.

## 10. Grid size và số thread không phải một khái niệm

`gridSize` là gợi ý số lượng partition mà manager yêu cầu partitioner tạo. Số worker chạy đồng thời còn phụ thuộc `TaskExecutor`, số thread khả dụng, giới hạn tài nguyên và implementation của handler.

Ví dụ:

| Grid size | Thread pool size | Hành vi có thể xảy ra |
| ---: | ---: | --- |
| 4 | 4 | Có thể chạy tối đa bốn partition cùng lúc. |
| 8 | 4 | Tạo tám partition; bốn partition chạy trước, các partition còn lại chờ lượt. |
| 4 | 8 | Chỉ có bốn partition được tạo; thread dư không có partition để chạy. |
| 20 | 4 | Nhiều partition hơn, có thể giảm kích thước mỗi phần nhưng tạo thêm overhead và metadata. |

Grid size không đảm bảo số thread thực tế. Một `TaskExecutor` có thể dùng queue, giới hạn concurrency hoặc executor policy riêng. Với remote handler, concurrency phụ thuộc số worker đang hoạt động, khả năng tiêu thụ message và giới hạn của broker.

Nên chọn số partition dựa trên kích thước dữ liệu, số CPU, database connection pool, tốc độ I/O và thời gian khởi tạo worker. Quá nhiều partition nhỏ có thể làm tăng overhead điều phối và metadata mà không tăng throughput.

## 11. Local partitioning và remote partitioning

| Tiêu chí | Local với `TaskExecutorPartitionHandler` | Remote với message handler |
| --- | --- | --- |
| Vị trí worker | Cùng JVM/host với manager | Có thể ở JVM hoặc máy khác |
| Cơ chế dispatch | Task executor/thread pool | Message channel/broker |
| Hạ tầng | Spring Batch và executor | Thường cần Spring Integration và middleware |
| Khả năng mở rộng | Giới hạn tài nguyên một host | Có thể thêm worker node |
| Lỗi thường gặp | Thread contention, heap, connection pool | Network, broker, timeout, worker availability |
| Vận hành | Đơn giản hơn | Cần quan sát và vận hành manager, broker, worker |

Chọn local partitioning khi một máy có đủ tài nguyên và muốn tăng concurrency với cấu hình gọn. Chọn remote partitioning khi cần mở rộng worker qua nhiều máy, tách biệt tài nguyên hoặc triển khai worker theo nhóm riêng.

Remote partitioning không tự động làm cho worker an toàn hơn. Vẫn cần chia dữ liệu không trùng, quản lý transaction, idempotency và restart. Việc truyền message cũng tạo thêm failure mode cần được xử lý.

## 12. PartitionHandler và remote chunking khác nhau

Hai mô hình đều có thể dùng middleware để phân phối công việc, nhưng cách chia trách nhiệm khác nhau:

- **Remote partitioning:** manager chia dữ liệu thành các partition và gửi yêu cầu chạy worker step. Mỗi worker tự đọc/xử lý/ghi phần dữ liệu được giao.
- **Remote chunking:** manager thường giữ vai trò đọc dữ liệu và gửi chunk đến worker để xử lý/ghi. Worker nhận chunk thay vì tự chạy một step đọc phạm vi riêng.

Remote partitioning phù hợp khi mỗi worker có thể tự đọc phần dữ liệu độc lập từ nguồn chung hoặc nguồn được định danh. Remote chunking phù hợp khi việc đọc nên tập trung ở manager, còn xử lý/ghi có thể phân tán.

Đừng chọn remote partitioning chỉ vì thấy có `PartitionHandler`. Hãy xác định bottleneck nằm ở đọc, xử lý hay ghi và chọn mô hình phù hợp với quyền sở hữu nguồn dữ liệu.

## 13. Restart và tên partition ổn định

Spring Batch lưu `StepExecution` cho từng partition. Khi manager step restart, `StepExecutionSplitter` sử dụng metadata đã lưu để xác định partition nào cần thực thi lại và partition nào đã hoàn thành theo restart semantics.

Tên partition và dữ liệu phạm vi phải ổn định giữa các lần chạy lại cùng một `JobInstance`. Ví dụ, nếu `partition0` trước đây xử lý ID 1..1000 nhưng sau khi restart lại được gán ID 500..1500, metadata cũ có thể bị áp dụng cho một vùng dữ liệu khác.

Các nguyên tắc quan trọng:

- Dùng tên partition có tính ổn định và duy nhất trong một worker step.
- Tạo phạm vi dựa trên snapshot hoặc định danh dữ liệu nhất quán.
- Không thay đổi cách chia dữ liệu tùy tiện giữa lần chạy đầu và restart.
- Reader của worker cần lưu checkpoint trong step execution context nếu cần restart bên trong partition.
- Writer phải chịu được việc xử lý lại dữ liệu chưa commit.
- Xác minh partition execution cũ không còn chạy trước khi khởi chạy lại.

Nếu dữ liệu nguồn thay đổi liên tục, cần xác định snapshot, watermark hoặc batch ID để mọi partition trong cùng job instance xử lý cùng một tập dữ liệu logic.

## 14. Khi một partition thất bại

Giả sử manager tạo bốn partition và partition 2 thất bại:

```text
partition0 -> COMPLETED
partition1 -> COMPLETED
partition2 -> FAILED
partition3 -> COMPLETED
                    |
                    v
          Manager partition step FAILED
```

Manager step thường không thể coi toàn bộ partition step là hoàn tất nếu một worker execution thất bại. Metadata của từng worker giúp xác định phần nào đã hoàn thành và phần nào cần điều tra.

Khi restart, các partition đã hoàn tất thường được nhận diện qua repository và không cần chạy lại theo restart behavior mặc định; partition thất bại hoặc chưa hoàn tất có thể được thực thi lại. Điều này phụ thuộc `allowStartIfComplete`, cấu hình step và logic splitter. Không nên dựa vào giả định này nếu partitioner tạo tên/phạm vi không ổn định.

Transaction của các partition độc lập. Nếu partition 0 đã commit dữ liệu và partition 2 thất bại, dữ liệu đã commit của partition 0 vẫn còn. Partitioning không cung cấp một transaction nguyên tử bao trùm tất cả worker. Nếu nghiệp vụ cần hoàn tác toàn bộ kết quả khi một partition thất bại, cần thiết kế staging/commit cuối, trạng thái batch hoặc quy trình bù trừ.

## 15. Quản lý dữ liệu không trùng và không bỏ sót

Partitioner cần tạo các vùng dữ liệu bao phủ đúng tập input và không giao nhau nếu mỗi item chỉ được xử lý một lần. Với phân vùng theo ID, cần xác định rõ khoảng inclusive/exclusive.

Ví dụ dùng khoảng nửa mở:

```sql
select id, name
from customer
where id >= :minId
  and id < :maxIdExclusive
order by id
```

Hoặc dùng khoảng hai đầu mút bao gồm:

```sql
select id, name
from customer
where id between :minId and :maxId
order by id
```

Không được trộn hai quy ước. Nếu partition trước kết thúc tại 1000 và partition tiếp theo bắt đầu tại 1000 trong truy vấn `BETWEEN`, item 1000 sẽ bị xử lý hai lần. Nếu partition trước dùng `< 1000` còn partition tiếp theo dùng `>= 1000`, ranh giới sẽ không trùng.

Ngoài ID range, có thể partition theo ngày, tenant, region, hash bucket hoặc danh sách file. Dù dùng chiến lược nào, cần bảo đảm tất cả partition dùng cùng quy tắc lọc và cùng snapshot dữ liệu.

## 16. Transaction và tài nguyên dùng chung

Mỗi worker step có transaction của riêng nó. Với chunk worker, từng chunk của partition có transaction riêng; không có transaction toàn cục bao trùm tất cả partition trừ khi ứng dụng chủ động xây dựng cơ chế phân tán phù hợp.

Khi chạy nhiều worker đồng thời, hãy kiểm tra:

- Database connection pool đủ cho số worker và các hoạt động khác của ứng dụng.
- Các partition không cập nhật cùng hàng theo cách gây lock contention hoặc deadlock.
- Reader dùng phạm vi riêng, không chia sẻ cursor mutable.
- Writer dùng transaction manager phù hợp và có idempotency khi cần retry.
- Processor/service singleton không giữ state theo item nếu không thread-safe.
- File output có tên riêng cho từng partition hoặc cơ chế ghi đồng bộ rõ ràng.
- Các API bên ngoài có rate limit phù hợp với tổng concurrency.

Ví dụ, nếu pool database chỉ có 8 connection nhưng chạy 20 worker, các worker có thể phải chờ connection và throughput giảm. Tăng grid size không giải quyết được giới hạn connection; nó có thể làm tình trạng chờ và timeout nặng hơn.

## 17. StepScope và state riêng cho từng partition

Các giá trị trong `ExecutionContext` là riêng cho từng partition. Dùng `@StepScope` cho reader, writer hoặc processor cần nhận giá trị partition lúc khởi tạo:

```java
@Bean
@StepScope
ItemProcessor<Customer, CustomerSummary> customerProcessor(
        @Value("#{stepExecutionContext['region']}") String region) {

    return customer -> new CustomerSummary(
        customer.getId(),
        region,
        customer.getName()
    );
}
```

Không nên inject `stepExecutionContext` vào một singleton bean rồi lưu giá trị vào field mutable dùng chung giữa các worker. `@StepScope` giúp Spring tạo target theo từng step execution, từ đó mỗi partition có dependency được khởi tạo với context tương ứng.

Nếu một service được chia sẻ giữa worker, service đó nên stateless hoặc được thiết kế thread-safe. Step scope không tự biến mọi dependency được inject vào nó thành thread-safe; các bean singleton bên dưới vẫn có thể được dùng chung.

## 18. Giới hạn và điều phối concurrency

Concurrency nên được giới hạn theo bottleneck thực tế, không chỉ theo số CPU. Một job đọc và ghi database có thể bị giới hạn bởi connection pool, I/O hoặc lock; một job xử lý ảnh có thể bị giới hạn bởi CPU và heap.

Các cách kiểm soát:

- Đặt core/max pool size cho `ThreadPoolTaskExecutor`.
- Chọn `gridSize` vừa đủ để tạo các partition có kích thước hợp lý.
- Giới hạn số worker remote đang tiêu thụ message.
- Cấu hình timeout và queue phù hợp với thời gian xử lý.
- Theo dõi active partition, queue depth, worker latency và connection wait.
- Tránh chạy nhiều job partitioned cùng lúc vượt khả năng database.

Nếu các partition có kích thước không đều, một số worker có thể hoàn tất sớm trong khi worker chậm nhất giữ manager step ở trạng thái chạy. Cân nhắc chiến lược chia theo số lượng bản ghi ước lượng hoặc theo chi phí xử lý, thay vì chỉ chia đều số ID nếu độ nặng mỗi record khác nhau.

## 19. Kiểm thử Partitioner và PartitionHandler

Nên tách kiểm thử cách chia dữ liệu khỏi kiểm thử cách thực thi.

### Unit test cho Partitioner

Kiểm tra:

- Số partition được tạo theo grid size và dữ liệu đầu vào.
- Các khoảng không bị giao nhau.
- Không có khoảng trống giữa các partition.
- Tổng số item được bao phủ bằng tập input.
- Trường hợp dữ liệu rỗng, một item và số item nhỏ hơn grid size.
- Grid size không hợp lệ được xử lý rõ ràng.

Ví dụ, với ID 1..10 và grid size 3, có thể xác nhận các range bao phủ đủ 10 ID mà không trùng. Không nên chỉ kiểm tra số phần tử của map.

### Integration test cho local handler

Dùng `TaskExecutorPartitionHandler` với worker step ghi nhận ID đã xử lý. Chạy manager job bằng `JobLauncherTestUtils`, sau đó xác nhận:

- Tất cả partition execution được tạo.
- Mỗi item thuộc đúng một partition.
- Các worker execution có trạng thái mong đợi.
- Tổng `readCount`/`writeCount` phù hợp với tập dữ liệu.
- Job/manager step hoàn tất khi tất cả worker thành công.

### Kiểm thử lỗi và restart

Cho một partition thất bại có kiểm soát, xác nhận manager step/job thất bại và metadata ghi nhận partition tương ứng. Sau đó restart cùng `JobInstance`, kiểm tra partition đã hoàn tất không bị chạy lại ngoài ý muốn và partition lỗi tiếp tục từ checkpoint phù hợp.

Với remote partitioning, cần kiểm thử thêm message serialization, worker không sẵn sàng, timeout, message retry/redelivery và trường hợp worker hoàn tất nhưng phản hồi bị mất. Consumer/worker phải xử lý message lặp an toàn.

## 20. Theo dõi và chẩn đoán PartitionHandler

Khi manager step chậm hoặc thất bại, hãy kiểm tra cả manager execution và từng worker `StepExecution`:

- Số partition được tạo và số partition đang hoạt động.
- Thời gian bắt đầu/kết thúc của từng worker.
- `BatchStatus`, `ExitStatus` và failure exception.
- `readCount`, `writeCount`, skip count, commit count và rollback count.
- Grid size, executor pool size và số thread/worker thực tế.
- Connection pool wait, database lock, CPU, heap và queue depth.
- Partition nào xử lý lâu bất thường hoặc có khối lượng lệch.

Với remote handler, bổ sung message ID, queue/topic, thời điểm gửi/nhận, số lần redelivery và worker ID. Ghi nhận parent job execution ID, manager step execution ID và worker step execution ID để truy vết quan hệ.

Không chỉ xem trạng thái manager step. Manager có thể thất bại do một worker cụ thể; cần tìm execution con để biết partition nào gặp lỗi và checkpoint cuối cùng ở đâu.

## 21. Các lỗi thường gặp khi dùng PartitionHandler

**Nhầm Partitioner với PartitionHandler:** partitioner chia dữ liệu và tạo context; handler điều phối việc chạy các execution. Thay đổi concurrency không nhất thiết cần viết lại partitioner.

**Cho rằng grid size bằng số thread:** grid size là số partition được yêu cầu; concurrency thực tế do executor hoặc worker pool quyết định.

**Dùng singleton reader có state chung:** các partition có thể đọc đè cursor của nhau. Dùng reader step-scoped và phạm vi riêng trong context.

**Partition range bị trùng hoặc bỏ sót:** quy ước inclusive/exclusive không nhất quán. Test coverage và overlap của partitioner.

**Tên partition thay đổi giữa các lần restart:** metadata cũ có thể gắn với vùng dữ liệu khác. Giữ tên và phạm vi ổn định cho cùng một job instance.

**Tăng worker vượt connection pool:** nhiều thread cùng chờ database, khiến throughput giảm và timeout tăng. Điều chỉnh concurrency theo tài nguyên.

**Cho rằng toàn bộ partition commit nguyên tử:** mỗi worker/chunk có transaction riêng. Partition thành công vẫn có dữ liệu đã commit nếu partition khác thất bại.

**Không xử lý message lặp trong remote mode:** broker có thể redeliver. Worker và thao tác ghi cần idempotency.

**Không phân biệt remote partitioning và remote chunking:** hai mô hình chia trách nhiệm đọc/dispatch khác nhau. Chọn theo nơi nên thực hiện việc đọc dữ liệu.

## 22. Cách lựa chọn PartitionHandler trong production

Trước tiên, xác định liệu dữ liệu có thể chia thành các phần độc lập và có cách phân vùng ổn định hay không. Thiết kế `Partitioner` sao cho các vùng bao phủ input, không giao nhau và có thể tái tạo khi restart. Đưa ranh giới và định danh cần thiết vào `ExecutionContext` của từng partition.

Nếu worker chạy trên cùng một máy, bắt đầu với `TaskExecutorPartitionHandler` và thread pool có giới hạn. Đo throughput, database connection usage, lock wait, heap và thời gian của từng partition trước khi tăng grid size. Nếu cần mở rộng qua nhiều tiến trình/máy, đánh giá remote partitioning với message channel, broker, metadata repository dùng chung và cơ chế theo dõi worker.

Giữ worker step stateless ở cấp singleton hoặc dùng `@StepScope` cho thành phần cần dữ liệu riêng của partition. Bảo đảm writer có transaction/idempotency, checkpoint reader được lưu đúng và partition names ổn định. Kiểm thử lỗi một worker, restart và message redelivery trước khi triển khai production.

`PartitionHandler` là điểm thực thi của mô hình partitioning: nó nhận các worker execution đã được splitter tạo và chạy chúng theo chiến lược local hoặc remote. Khi kết hợp đúng với partitioner, worker step, grid size và metadata repository, ứng dụng có thể phân phối công việc batch rõ ràng, mở rộng concurrency có kiểm soát và phục hồi từng partition sau sự cố.
