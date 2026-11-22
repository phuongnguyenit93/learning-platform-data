# Restart partition

Trong Spring Batch, partitioning chia một Step lớn thành nhiều partition nhỏ. Mỗi partition được thực thi như một `StepExecution` riêng, có `ExecutionContext` và trạng thái riêng. Khi Job bị lỗi và được restart, Spring Batch có thể tiếp tục các partition chưa hoàn tất từ checkpoint đã lưu, đồng thời giữ lại kết quả của những partition đã hoàn thành.

Restart partition đặc biệt hữu ích với Job xử lý lượng dữ liệu lớn, vì một partition thất bại không nhất thiết buộc toàn bộ dữ liệu đã xử lý thành công phải chạy lại. Để cơ chế này hoạt động đúng, partition cần có tên ổn định, phạm vi dữ liệu có thể tái tạo, worker Step phải hỗ trợ restart và metadata phải được lưu trong `JobRepository`.

## 1. Partitioning tạo ra nhiều StepExecution

Một partitioned Step thường có hai vai trò:

- **Manager/master Step:** chia dữ liệu thành các partition và điều phối việc thực thi.
- **Worker Step:** thực hiện xử lý dữ liệu của một partition, thường dùng chunk-oriented processing hoặc Tasklet.

Ví dụ, Job nhập 1.000.000 đơn hàng có thể chia ID thành bốn khoảng. Mỗi khoảng trở thành một partition và được xử lý bởi một worker StepExecution riêng.

```text
JobExecution: importOrdersJob
       |
       v
Manager Step: partitionOrdersStep
       |
       +--> workerStep:partition0  (ID 1 - 250000)
       |
       +--> workerStep:partition1  (ID 250001 - 500000)
       |
       +--> workerStep:partition2  (ID 500001 - 750000)
       |
       +--> workerStep:partition3  (ID 750001 - 1000000)
```

Mỗi worker partition có `StepExecution` và `ExecutionContext` riêng. Do đó, checkpoint của partition 0 không ghi đè checkpoint của partition 1. Đây là nền tảng để Spring Batch theo dõi partition nào đã hoàn tất và partition nào cần tiếp tục khi restart.

## 2. Restart partition hoạt động như thế nào?

Giả sử Job có bốn partition. Hai partition đầu hoàn tất, partition thứ ba thất bại giữa quá trình xử lý, còn partition thứ tư chưa chạy do lỗi xảy ra trong lúc điều phối.

```text
Lần chạy đầu
  partition0 -> COMPLETED
  partition1 -> COMPLETED
  partition2 -> FAILED (đã commit một số chunk)
  partition3 -> chưa hoàn tất

Restart cùng JobInstance
  partition0 -> giữ kết quả COMPLETED
  partition1 -> giữ kết quả COMPLETED
  partition2 -> chạy lại từ checkpoint đã commit gần nhất
  partition3 -> được thực thi vì chưa hoàn tất
```

Spring Batch sử dụng metadata trong `JobRepository` để nhận diện các StepExecution của partition. Partition đã hoàn tất thường không được thực thi lại trong lần restart thông thường. Partition thất bại hoặc chưa hoàn tất được tạo/khôi phục execution phù hợp và chạy tiếp theo trạng thái đã lưu.

Với worker Step xử lý theo chunk, checkpoint thường nằm trong Step `ExecutionContext` của partition. Nếu partition đã commit bốn chunk rồi gặp lỗi ở chunk thứ năm, lần restart có thể tiếp tục từ checkpoint của chunk thứ tư, thay vì đọc lại toàn bộ partition.

Restart không có nghĩa là Spring Batch khởi chạy lại mọi partition từ đầu. Nó dựa trên trạng thái từng partition và metadata đã được lưu.

## 3. JobInstance phải được giữ nguyên khi restart

Spring Batch xác định `JobInstance` bằng tên Job cùng các JobParameters được đánh dấu identifying. Restart là một `JobExecution` mới của cùng JobInstance, do đó cần khởi chạy lại với cùng bộ identifying parameters.

Ví dụ, Job nhập đơn hàng được chạy với:

```text
jobName       = importOrdersJob
businessDate  = 2026-11-15  (identifying)
sourceSystem  = ERP         (identifying)
```

Khi Job thất bại, restart với cùng `businessDate` và `sourceSystem` để Spring Batch tìm đúng JobInstance và metadata partition trước đó.

Nếu thêm một identifying parameter mới như timestamp hoặc `run.id` thay đổi ở lần gọi lại, yêu cầu có thể tạo JobInstance mới. Khi đó, Spring Batch xem đây là công việc logic mới và các partition có thể được chạy lại từ đầu.

Không dùng một JobParametersIncrementer để restart công việc cũ. Incrementer thường tạo identifying parameter mới cho instance tiếp theo; restart cần giữ nguyên identity của JobInstance hiện tại.

## 4. Tên partition phải ổn định

Partition name là một phần quan trọng để framework liên kết metadata của partition giữa các lần thực thi. Nếu lần đầu tạo các tên `partition0`, `partition1`, `partition2`, `partition3`, lần restart cần tái tạo đúng tập tên tương ứng.

Ví dụ tên ổn định:

```text
orders-partition-000
orders-partition-001
orders-partition-002
orders-partition-003
```

Không nên đặt tên partition dựa trên UUID hoặc timestamp ngẫu nhiên ở mỗi lần gọi `Partitioner.partition()`. Khi tên thay đổi, framework có thể không liên kết partition mới với `StepExecution` và checkpoint cũ, khiến dữ liệu đã hoàn tất bị xử lý lại hoặc metadata không được sử dụng như mong muốn.

Tên partition nên dựa trên một định danh ổn định của phạm vi dữ liệu, chẳng hạn số thứ tự shard, tenant, ngày nghiệp vụ hoặc khoảng ID. Tên worker Step cũng cần giữ ổn định qua các phiên bản triển khai vì metadata StepExecution gắn với tên Step.

## 5. Partitioner phải tái tạo phạm vi dữ liệu nhất quán

`Partitioner` tạo một `ExecutionContext` cho mỗi partition. Context thường chứa giới hạn dữ liệu mà worker sẽ xử lý, ví dụ `minId` và `maxId`.

Interface cơ bản:

```java
public interface Partitioner {
    Map<String, ExecutionContext> partition(int gridSize);
}
```

Ví dụ partitioner chia một khoảng ID cố định thành các phần:

```java
public class OrderRangePartitioner implements Partitioner {

    private final long minId;
    private final long maxId;

    public OrderRangePartitioner(long minId, long maxId) {
        this.minId = minId;
        this.maxId = maxId;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        Map<String, ExecutionContext> partitions = new LinkedHashMap<>();

        if (gridSize <= 0 || minId > maxId) {
            return partitions;
        }

        long totalItems = maxId - minId + 1;
        long targetSize = (totalItems + gridSize - 1) / gridSize;
        long start = minId;
        int partitionNumber = 0;

        while (start <= maxId) {
            long end = Math.min(start + targetSize - 1, maxId);

            ExecutionContext context = new ExecutionContext();
            context.putLong("minId", start);
            context.putLong("maxId", end);

            String partitionName = String.format(
                    Locale.ROOT, "orders-partition-%03d", partitionNumber++
            );
            partitions.put(partitionName, context);

            start = end + 1;
        }

        return partitions;
    }
}
```

Với `minId=1`, `maxId=1000` và `gridSize=4`, partitioner tạo bốn context chứa các khoảng ID gần bằng nhau. Tên và giới hạn của từng partition được tái tạo giống nhau nếu đầu vào partitioner không thay đổi.

Ví dụ này dùng giới hạn cố định để làm rõ nguyên tắc. Trong hệ thống thực tế, không nên đọc `MAX(id)` từ bảng đang thay đổi ở mỗi lần restart rồi chia lại mà không có quy tắc snapshot. Nếu dữ liệu mới được thêm vào, số partition hoặc ranh giới có thể thay đổi. Hãy cố định phạm vi đầu vào bằng JobParameters, snapshot, manifest hoặc metadata nghiệp vụ được lưu bền vững.

## 6. Worker đọc giới hạn từ partition ExecutionContext

Mỗi worker Step nhận context của partition hiện tại. Có thể dùng `@StepScope` để inject các giới hạn đó vào reader:

```java
@Bean
@StepScope
public JdbcPagingItemReader<Order> partitionOrderReader(
        DataSource dataSource,
        PagingQueryProvider queryProvider,
        RowMapper<Order> rowMapper,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    return new JdbcPagingItemReaderBuilder<Order>()
            .name("partitionOrderReader")
            .dataSource(dataSource)
            .queryProvider(queryProvider)
            .parameterValues(Map.of("minId", minId, "maxId", maxId))
            .rowMapper(rowMapper)
            .pageSize(100)
            .saveState(true)
            .build();
}
```

Query của `PagingQueryProvider` cần lọc theo giới hạn partition và sắp xếp theo khóa ổn định, ví dụ:

```sql
SELECT order_id, customer_id, amount
FROM orders
WHERE order_id BETWEEN :minId AND :maxId
ORDER BY order_id
```

Mỗi partition chỉ đọc phạm vi của nó. `saveState(true)` cho phép reader lưu vị trí đọc trong Step ExecutionContext của partition để restart tiếp tục từ checkpoint đã commit.

Tên reader nên ổn định. Nếu reader có state, tránh đổi tên hoặc thay đổi key nội bộ mà không có kế hoạch tương thích với metadata của execution đang dở.

## 7. Cấu hình manager Step và worker Step

Worker Step thường là một chunk-oriented Step. Manager Step dùng partitioner để tạo partition và `PartitionHandler` để phân phối chúng.

Ví dụ worker Step:

```java
@Bean
public Step importOrderWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> partitionOrderReader,
        ItemProcessor<Order, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrderWorkerStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(partitionOrderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
```

Manager Step:

```java
@Bean
public Step partitionOrdersStep(
        JobRepository jobRepository,
        Step importOrderWorkerStep,
        Partitioner orderRangePartitioner,
        TaskExecutor partitionTaskExecutor) {

    return new StepBuilder("partitionOrdersStep", jobRepository)
            .partitioner("importOrderWorkerStep", orderRangePartitioner)
            .step(importOrderWorkerStep)
            .gridSize(4)
            .taskExecutor(partitionTaskExecutor)
            .build();
}
```

`gridSize(4)` là gợi ý số partition mong muốn cho partitioner/handler; số partition thực tế phụ thuộc map mà `Partitioner` trả về. `TaskExecutor` cho phép các worker partition chạy song song trong local partitioning. Nếu dùng remote partitioning, cơ chế gửi yêu cầu và môi trường worker sẽ khác, nhưng nguyên tắc metadata và checkpoint theo partition vẫn cần được duy trì.

Trong cấu hình thực tế, cần bảo đảm reader bean là step-scoped để nhận đúng ExecutionContext của từng partition. Nếu một reader mutable singleton bị chia sẻ giữa nhiều worker, các partition có thể ghi đè state và đọc sai phạm vi.

## 8. StepExecution và ExecutionContext của từng partition

Khi manager tạo partition, Spring Batch tạo các StepExecution cho worker. Mỗi StepExecution có metadata và ExecutionContext riêng:

```text
JobExecution
  |
  +-- Manager StepExecution: partitionOrdersStep
        |
        +-- Worker StepExecution: importOrderWorkerStep:orders-partition-000
        |      +-- ExecutionContext: minId, maxId, reader checkpoint
        |
        +-- Worker StepExecution: importOrderWorkerStep:orders-partition-001
        |      +-- ExecutionContext: minId, maxId, reader checkpoint
        |
        +-- Worker StepExecution: importOrderWorkerStep:orders-partition-002
        |      +-- ExecutionContext: minId, maxId, reader checkpoint
        |
        +-- Worker StepExecution: importOrderWorkerStep:orders-partition-003
               +-- ExecutionContext: minId, maxId, reader checkpoint
```

ExecutionContext của partition chứa cả dữ liệu phân vùng ban đầu và state do reader/writer cập nhật. Khi restart, framework cần xác định đúng partition name và khôi phục context tương ứng.

Không lưu checkpoint của mọi partition vào một singleton field dùng chung. Mỗi partition có phạm vi state riêng và nên dựa trên StepExecution/ExecutionContext của chính nó.

## 9. Điều gì xảy ra khi một partition thất bại?

Giả sử partition 2 xử lý dữ liệu theo chunk size 100. Nó đã commit 12 chunk, sau đó chunk thứ 13 gặp lỗi:

```text
orders-partition-002
  Chunk 1..12  -> COMPLETED / committed
  Chunk 13     -> FAILED / rolled back
  Chunk 14..   -> chưa chạy
```

Khi Job được restart với cùng JobInstance, Spring Batch sử dụng metadata đã lưu của partition 2. Worker có thể khôi phục reader checkpoint sau chunk 12 và tiếp tục từ phần dữ liệu chưa hoàn tất.

Các partition đã hoàn tất vẫn giữ kết quả. Những partition chưa hoàn tất hoặc thất bại được tiếp tục theo trạng thái đã lưu. Vì vậy, tổng dữ liệu không cần chạy lại từ đầu nếu metadata và reader được cấu hình restart đúng.

Nếu worker Step có cấu hình skip/retry, lỗi có thể được xử lý trong chính lần thực thi trước khi partition kết thúc. Nếu lỗi không thể phục hồi và worker Step thất bại, restart Job mới tạo cơ hội tiếp tục partition từ checkpoint gần nhất.

## 10. Restart partition cần dữ liệu đầu vào ổn định

Một partitioner có thể tạo cùng tên partition nhưng vẫn trả ra phạm vi dữ liệu khác. Khi đó, framework tìm thấy metadata cũ nhưng context mới không còn mô tả cùng dữ liệu.

Ví dụ lần đầu chia bảng có ID từ 1 đến 1.000 thành bốn khoảng. Trong lúc Job thất bại, dữ liệu được chèn/xóa hoặc `MAX(id)` thay đổi. Lần restart tính lại phạm vi có thể tạo khoảng khác với lần đầu.

Để tránh tình huống này:

- Dùng JobParameters identifying để cố định ngày, tenant, nguồn hoặc snapshot cần xử lý.
- Lưu tổng phạm vi hoặc manifest partition ở nơi bền vững nếu ranh giới được tính động.
- Dùng partition name ổn định, không dựa trên thứ tự không xác định của map hoặc UUID mới mỗi lần.
- Dùng sort key duy nhất và ổn định trong reader.
- Tránh thay đổi query filter hoặc cách chia partition giữa lần chạy đầu và lần restart nếu chưa có migration.
- Nếu nguồn dữ liệu thay đổi liên tục, cân nhắc snapshot hoặc watermark để xác định tập dữ liệu logic.

Partition name và ExecutionContext là một phần của metadata restart. Thay đổi thuật toán phân vùng giữa hai phiên bản ứng dụng có thể khiến execution cũ không còn tương thích.

## 11. PartitionNameProvider và việc khôi phục tên partition

Với partitioner có chi phí tính toán cao, Spring Batch hỗ trợ `PartitionNameProvider`. Interface này cho phép cung cấp danh sách tên partition mà không cần dựng toàn bộ `ExecutionContext` cho mọi partition.

Ví dụ:

```java
public class OrderRangePartitioner
        implements Partitioner, PartitionNameProvider {

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        // Tạo tên và ExecutionContext cho các partition cần tạo.
        return createPartitionContexts(gridSize);
    }

    @Override
    public Set<String> getPartitionNames(int gridSize) {
        // Trả lại đúng các tên partition ổn định.
        return createStablePartitionNames(gridSize);
    }
}
```

Trong quá trình restart, framework có thể dùng danh sách tên để đối chiếu partition trước đó và tránh tính lại context không cần thiết cho partition đã hoàn tất. Tên được trả về phải giống tên đã dùng ở lần chạy ban đầu.

`PartitionNameProvider` chỉ tối ưu cách lấy tên partition; nó không thay thế `Partitioner`, không lưu checkpoint thay reader và không tự bảo đảm phạm vi dữ liệu ổn định. Việc tạo lại context cho partition cần chạy vẫn phải dựa trên quy tắc phân vùng nhất quán.

## 12. Local partitioning và remote partitioning khi restart

Restart partition áp dụng cho cả local partitioning và remote partitioning, nhưng hạ tầng lưu metadata và cách worker được khởi chạy có khác biệt.

**Local partitioning:** manager Step phân phối worker StepExecution đến các thread trong cùng ứng dụng, thường thông qua `TaskExecutor`. Các worker dùng chung JobRepository và các resource cấu hình trong application context.

**Remote partitioning:** manager gửi yêu cầu thực thi partition đến worker process hoặc node khác thông qua middleware. Manager và worker cần phối hợp trên metadata repository phù hợp để trạng thái worker và checkpoint được lưu, truy xuất nhất quán. Worker cần có cấu hình Step tương ứng và đọc đúng ExecutionContext của partition được giao.

Trong cả hai trường hợp, cần giữ ổn định tên worker Step, partition name và key checkpoint. Nếu worker process bị dừng, JobRepository phải còn metadata của partition để lần restart có thể nhận diện phần đã hoàn tất và phần cần chạy lại.

Không nhầm remote partitioning với remote chunking. Remote partitioning phân phối các partition/StepExecution cho worker; remote chunking phân phối chunk từ một manager Step đến worker xử lý chunk. Cơ chế restart và đơn vị metadata theo dõi khác nhau.

## 13. Transaction và idempotency trong worker partition

Checkpoint của reader giúp khôi phục vị trí đọc, nhưng không tự bảo vệ mọi side effect. Worker có thể gọi API, gửi message hoặc ghi file ngoài transaction database. Nếu side effect đã xảy ra nhưng chunk chưa commit, partition có thể thực hiện lại thao tác khi restart.

Với dữ liệu database trong cùng transaction manager, rollback chunk có thể hoàn tác thay đổi chưa commit. Với resource ngoài transaction, hãy dùng business key ổn định, unique constraint, idempotency key, outbox hoặc quy trình staging.

Ví dụ, nếu mỗi partition ghi đơn hàng vào bảng đích, có thể dùng `order_id` làm khóa duy nhất và thao tác upsert phù hợp. Khi một chunk được xử lý lại sau rollback, cùng một order không tạo thêm bản ghi trùng.

Nếu mỗi partition tạo file riêng, hãy đặt tên file theo partition name hoặc business key ổn định, ghi file tạm rồi publish sau khi hoàn tất. Tránh nối thêm dữ liệu vào file cũ mà không xác định chính xác phần đã commit.

## 14. allowStartIfComplete và partition đã hoàn tất

Worker Step có thể được cấu hình `allowStartIfComplete(true)`. Tùy chọn này cho phép Step đã hoàn tất được chạy lại trong lần restart phù hợp. Với partitioning, điều đó có thể làm một partition đã hoàn tất được thực thi lại.

Chỉ bật tùy chọn này khi nghiệp vụ yêu cầu chạy lại partition đã hoàn tất và writer có khả năng idempotent. Nếu mục tiêu là restart thông thường, để các partition hoàn tất được giữ nguyên thường phù hợp hơn.

Không nên bật `allowStartIfComplete` chỉ để “chắc chắn dữ liệu được cập nhật”. Nếu dữ liệu đầu vào thay đổi, cần xác định đó là một JobInstance mới hay một lần chạy lại có chủ đích. Đừng biến restart thành một lượt xử lý mới ngoài ý muốn.

## 15. Lỗi thường gặp khi restart partition

### Partition name thay đổi giữa các lần chạy

Tên partition mới không khớp metadata cũ. Framework có thể không liên kết được checkpoint và tạo execution mới cho phạm vi đã hoàn tất. Hãy dùng tên ổn định theo business key hoặc shard index.

### Partitioner tính lại phạm vi từ dữ liệu đã thay đổi

Một partition có cùng tên nhưng giới hạn ID khác. Worker có thể đọc trùng hoặc bỏ sót dữ liệu. Hãy cố định snapshot hoặc lưu manifest phạm vi.

### Reader không lưu state

Reader không triển khai `ItemStream`, tắt `saveState` hoặc không được đăng ký stream. Khi restart, reader bắt đầu từ đầu partition. Hãy bật state và bảo đảm callback `open/update/close` được gọi.

### Đổi tên worker Step hoặc reader

Metadata cũ gắn với tên Step và key reader cũ. Đổi tên có thể khiến execution cũ không còn tương thích. Cần giữ tên hoặc có kế hoạch migration.

### Dùng identifying parameters mới khi restart

Job tạo JobInstance mới nên không sử dụng metadata partition cũ. Giữ nguyên identifying parameters của công việc cần tiếp tục.

### Side effect không idempotent

Một chunk hoặc partition có thể được xử lý lại sau rollback/restart. Dùng transaction hoặc idempotency để tránh ghi trùng.

### Dùng mutable singleton reader cho nhiều partition

Nhiều worker cùng thay đổi vị trí đọc trong một object, gây race condition. Reader có state cần được tạo theo Step scope hoặc theo partition execution.

## 16. Theo dõi partition khi vận hành

Khi điều tra một Job partitioned, không chỉ xem trạng thái manager Step. Hãy xem từng worker StepExecution:

- Partition name và tên worker Step.
- `BatchStatus` và `ExitStatus`.
- `startTime`, `endTime` và thời gian chạy.
- `readCount`, `writeCount`, filter/skip count.
- `commitCount` và `rollbackCount`.
- ExecutionContext chứa giới hạn partition và checkpoint reader.
- Exception của partition thất bại.

Các thông tin này giúp xác định partition nào đã hoàn tất, partition nào thất bại và checkpoint cuối cùng ở đâu. Khi restart, có thể so sánh StepExecution cũ và mới của cùng partition name để xác nhận framework tiếp tục đúng phạm vi.

Không sửa trực tiếp metadata trong JobRepository để đánh dấu partition hoàn tất hoặc ép checkpoint sang vị trí khác nếu chưa hiểu đầy đủ dữ liệu nghiệp vụ. Thay đổi metadata không đồng bộ với dữ liệu đích có thể khiến restart bỏ sót hoặc xử lý trùng.

## 17. Kiểm thử restart partition

Một bài kiểm thử restart có ý nghĩa nên mô phỏng lỗi ở một partition sau khi một số chunk đã commit:

1. Khởi chạy Job với một bộ identifying JobParameters cố định.
2. Tạo nhiều partition với tên và phạm vi ổn định.
3. Cho một số partition hoàn tất.
4. Làm một partition thất bại sau một vài chunk đã commit.
5. Kiểm tra metadata và checkpoint của từng partition.
6. Khởi chạy lại cùng JobInstance với cùng identifying parameters.
7. Xác nhận partition đã hoàn tất không chạy lại trong cấu hình mặc định.
8. Xác nhận partition thất bại tiếp tục từ checkpoint đã lưu.
9. Kiểm tra dữ liệu đầu ra không bị thiếu hoặc trùng.

Ngoài trường hợp lỗi, nên kiểm tra thêm:

- Restart khi partition chưa được worker nhận xử lý.
- Restart khi worker bị dừng giữa một chunk.
- Partitioner tạo lại đúng tên và giới hạn partition.
- Dữ liệu nguồn thay đổi giữa lần chạy đầu và restart.
- Nhiều worker chạy song song nhưng không chia sẻ mutable reader state.
- Side effect ngoài transaction không bị lặp ngoài ý muốn.

Integration test cần dùng repository có khả năng giữ metadata qua hai lần chạy. Nếu dùng repository in-memory bị tạo lại giữa hai lần test, test không thể chứng minh hành vi restart bền vững qua process restart.

## 18. Quy tắc thiết kế restart partition

Để restart partition đáng tin cậy, hãy giữ nguyên JobInstance bằng identifying JobParameters ổn định; dùng partition name và worker Step name ổn định; tái tạo cùng phạm vi dữ liệu; lưu reader checkpoint trong ExecutionContext của từng partition; và dùng JobRepository bền vững. Với writer, bảo đảm thay đổi database cùng transaction có thể rollback hoặc side effect bên ngoài có idempotency.

Khi một Job partitioned thất bại, hãy xem metadata của từng worker StepExecution để xác định partition đã hoàn tất và partition cần tiếp tục. Restart partition dựa trên trạng thái riêng của từng partition, nên một partition lỗi không buộc các partition đã hoàn tất phải chạy lại. Điều kiện là danh tính partition, checkpoint và nguồn dữ liệu vẫn nhất quán qua các lần thực thi.
