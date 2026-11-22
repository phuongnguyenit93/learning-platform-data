# Partitioning chia dữ liệu thành nhiều step execution

Partitioning trong Spring Batch chia dữ liệu đầu vào thành nhiều phần độc lập, sau đó chạy cùng một định nghĩa worker step cho từng phần. Mỗi phần tạo một `StepExecution` riêng với `ExecutionContext` riêng, nhờ đó các phần có thể được xử lý đồng thời hoặc phân phối sang nhiều tiến trình.

Thay vì một step duy nhất đọc toàn bộ dữ liệu, partitioning tạo ra một step điều phối (manager/master) và nhiều lần thực thi worker step. Manager xác định các partition; mỗi worker nhận phạm vi dữ liệu của mình, xử lý và lưu trạng thái riêng trong `JobRepository`.

## 1. Partitioning là gì?

Partitioning là cách chia workload thành các phần không chồng lấn để nhiều worker step execution có thể xử lý độc lập. Ví dụ, một job nhập một triệu đơn hàng có thể chia theo khoảng ID thành tám partition. Mỗi worker chỉ đọc và ghi dữ liệu thuộc khoảng được giao.

```text
Job: importOrders
       |
       v
Manager step
       |
       +-- tạo partition0: orderId 1..125000
       +-- tạo partition1: orderId 125001..250000
       +-- tạo partition2: orderId 250001..375000
       +-- ...
       +-- tạo partition7: orderId 875001..1000000
       |
       v
Các worker StepExecution
       |
       +-- worker partition0
       +-- worker partition1
       +-- worker partition2
       +-- ...
       +-- worker partition7
```

Mỗi partition là một đơn vị dữ liệu được mô tả bằng một tên và một `ExecutionContext`. Worker step dùng context đó để biết cần xử lý phạm vi nào. Các worker có thể chạy song song nếu cấu hình `PartitionHandler` và executor cho phép.

## 2. Manager step và worker step

Một cấu hình partitioning thường có hai vai trò:

| Thành phần | Trách nhiệm |
|---|---|
| Manager/master step | Gọi `Partitioner`, tạo các partition và điều phối việc thực thi worker |
| Worker step | Xử lý dữ liệu của một partition bằng tasklet hoặc chunk-oriented processing |
| `PartitionHandler` | Khởi chạy worker execution, cục bộ hoặc qua cơ chế phân phối |
| `JobRepository` | Lưu metadata của manager, từng worker `StepExecution` và context tương ứng |

Worker step là một định nghĩa step được tái sử dụng cho từng partition. Spring Batch tạo một `StepExecution` riêng cho mỗi partition, vì vậy mỗi worker có trạng thái, bộ đếm và `ExecutionContext` độc lập.

Manager không cần tự xử lý từng item. Nó chịu trách nhiệm chia việc và theo dõi kết quả của các worker. Worker thực hiện logic đọc, xử lý và ghi dữ liệu.

## 3. Partitioner tạo các phần dữ liệu

`Partitioner` là interface mô tả cách chia dữ liệu. Phương thức `partition(int gridSize)` trả về một map, trong đó key là tên partition và value là `ExecutionContext` chứa dữ liệu cần thiết cho worker.

```java
public interface Partitioner {
    Map<String, ExecutionContext> partition(int gridSize);
}
```

Ví dụ, job xử lý các đơn hàng có ID liên tục từ 1 đến 1.000.000. Partitioner chia khoảng ID thành số phần dựa trên `gridSize`:

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
        if (gridSize <= 0) {
            throw new IllegalArgumentException("gridSize must be positive");
        }

        Map<String, ExecutionContext> result = new LinkedHashMap<>();
        if (maxId < minId) {
            return result;
        }

        long total = maxId - minId + 1;
        int partitionCount = (int) Math.min((long) gridSize, total);
        long baseSize = total / partitionCount;
        long remainder = total % partitionCount;
        long nextStart = minId;

        for (int i = 0; i < partitionCount; i++) {
            long size = baseSize + (i < remainder ? 1 : 0);
            long end = nextStart + size - 1;

            ExecutionContext context = new ExecutionContext();
            context.putLong("minId", nextStart);
            context.putLong("maxId", end);

            result.put("partition" + i, context);
            nextStart = end + 1;
        }

        return result;
    }
}
```

Với khoảng 1 đến 1.000 và `gridSize = 4`, kết quả là bốn phạm vi gần bằng nhau. Nếu tổng số ID không chia hết cho số partition, phần dư được phân phối thêm một ID cho các partition đầu.

| Partition | minId | maxId |
|---|---:|---:|
| `partition0` | 1 | 250 |
| `partition1` | 251 | 500 |
| `partition2` | 501 | 750 |
| `partition3` | 751 | 1000 |

Ví dụ giả định miền ID hợp lệ, không tràn số khi tính độ dài khoảng. Với dữ liệu thực tế, cần xác thực `minId`, `maxId`, số lượng bản ghi và trường hợp nguồn rỗng trước khi tạo partition.

## 4. Đảm bảo các partition đầy đủ và không chồng lấn

Chất lượng của partitioning phụ thuộc trực tiếp vào thuật toán chia dữ liệu. Các partition nên thỏa mãn ba thuộc tính:

1. **Không chồng lấn:** một item không được thuộc đồng thời hai partition nếu không có chủ đích xử lý trùng.
2. **Bao phủ đầy đủ:** mọi item trong phạm vi cần xử lý phải thuộc một partition nào đó.
3. **Cân bằng tương đối:** mỗi partition nên có workload tương đương để tránh một worker kéo dài toàn bộ job.

Với khoảng số liên tục, có thể chia theo min/max ID. Nhưng ID trong database thường có thể bị khuyết; chia đều khoảng số không đồng nghĩa chia đều số bản ghi. Một partition có thể chứa ít dữ liệu hơn partition khác nếu phân bố ID không đồng đều.

Các cách chia khác có thể phù hợp hơn tùy dữ liệu:

- Chia theo range của khóa chính hoặc khóa nghiệp vụ.
- Chia theo ngày/tháng hoặc khoảng thời gian.
- Chia theo tenant, vùng hoặc nhóm khách hàng.
- Chia theo hash/modulo của khóa nếu các nhóm có thể được truy vấn độc lập.
- Chia theo danh sách shard hoặc work item đã được chuẩn bị trước.

Điều kiện query của worker phải khớp chính xác với quy tắc partitioner. Nếu partitioner tạo khoảng inclusive `[minId, maxId]`, reader cần dùng điều kiện tương ứng như `id >= ? AND id <= ?`. Tránh dùng biên inclusive ở cả hai partition liền kề vì sẽ xử lý trùng bản ghi.

## 5. Truyền dữ liệu partition qua ExecutionContext

`Partitioner` không truyền trực tiếp các tham số Java vào worker method. Nó đặt dữ liệu cần thiết vào `ExecutionContext` của từng partition. Spring Batch lưu context cùng metadata và cung cấp nó cho worker `StepExecution` tương ứng.

Ví dụ mỗi context có thể chứa:

```java
ExecutionContext context = new ExecutionContext();
context.putLong("minId", 1L);
context.putLong("maxId", 250L);
context.putString("region", "north");
```

Worker có thể đọc giá trị từ step execution context bằng `@StepScope` và SpEL. Các giá trị cần lưu nên nhỏ, có thể serialize và đủ để xác định phạm vi xử lý. Không lưu connection, reader đang mở, service bean hoặc resource runtime vào context.

## 6. Cấu hình worker step trong Spring Batch 5

Worker step có thể là chunk-oriented step. Reader được tạo theo từng `StepExecution` để mỗi partition có query range riêng.

```java
@Bean
@StepScope
JdbcCursorItemReader<Order> partitionedOrderReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    return new JdbcCursorItemReaderBuilder<Order>()
        .name("partitionedOrderReader")
        .dataSource(dataSource)
        .sql("""
            SELECT ORDER_ID, CUSTOMER_ID, TOTAL
            FROM ORDERS
            WHERE ORDER_ID >= ? AND ORDER_ID <= ?
            ORDER BY ORDER_ID
            """)
        .preparedStatementSetter(ps -> {
            ps.setLong(1, minId);
            ps.setLong(2, maxId);
        })
        .rowMapper(new OrderRowMapper())
        .saveState(true)
        .build();
}
```

`@StepScope` làm cho reader được tạo theo từng step execution. Nhờ đó mỗi partition nhận `minId` và `maxId` riêng, thay vì chia sẻ một reader có trạng thái mutable giữa các worker. Reader có thể lưu trạng thái đọc để hỗ trợ restart; tên reader phải ổn định và context của từng worker được quản lý riêng.

Khai báo worker step:

```java
@Bean
Step orderWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> partitionedOrderReader,
        ItemProcessor<Order, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("orderWorker", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(partitionedOrderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .build();
}
```

Worker dùng cùng một định nghĩa step cho mọi partition. Sự khác biệt về dữ liệu đến từ step execution context, chứ không cần tạo một bean step riêng cho từng range.

## 7. Cấu hình manager step và chạy song song

Manager step gắn partitioner với worker step. Với local partitioning, có thể dùng `TaskExecutor` để chạy các worker trên nhiều thread trong cùng ứng dụng.

```java
@Bean
Step orderManagerStep(
        JobRepository jobRepository,
        Step orderWorkerStep,
        Partitioner orderRangePartitioner,
        TaskExecutor partitionTaskExecutor) {

    return new StepBuilder("orderManager", jobRepository)
        .partitioner(orderWorkerStep.getName(), orderRangePartitioner)
        .step(orderWorkerStep)
        .gridSize(4)
        .taskExecutor(partitionTaskExecutor)
        .build();
}
```

Job có thể bắt đầu bằng manager step:

```java
@Bean
Job partitionedOrderImportJob(
        JobRepository jobRepository,
        Step orderManagerStep) {

    return new JobBuilder("partitionedOrderImportJob", jobRepository)
        .start(orderManagerStep)
        .build();
}
```

Trong cấu hình trên, `gridSize(4)` yêu cầu tạo khoảng bốn partition khi dữ liệu đủ lớn. Executor quyết định có bao nhiêu worker thực sự chạy đồng thời. Nếu có tám partition nhưng thread pool chỉ có bốn thread, các worker sẽ được thực thi theo nhiều lượt.

Có thể cấu hình executor riêng với giới hạn thread:

```java
@Bean
TaskExecutor partitionTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setThreadNamePrefix("order-partition-");
    executor.initialize();
    return executor;
}
```

Không nên đặt số thread lớn hơn khả năng chịu tải của database hoặc hệ thống đích. Tăng số partition không tự động làm job nhanh hơn nếu các worker tranh chấp cùng bảng, connection pool hoặc dịch vụ bên ngoài.

## 8. Grid size không đồng nghĩa với số thread

`gridSize` là gợi ý cho partitioner về số phần cần tạo. Số worker chạy đồng thời phụ thuộc `PartitionHandler`, executor, tài nguyên hệ thống và cấu hình triển khai.

Ví dụ:

| Grid size | Thread pool size | Hành vi thường thấy |
|---:|---:|---|
| 4 | 4 | Tối đa bốn worker chạy đồng thời |
| 8 | 4 | Tạo tám partition, thực thi theo các đợt |
| 4 | 8 | Chỉ có tối đa bốn partition để chạy; thread dư không tạo thêm việc |
| 8 | 8 | Có thể chạy đồng thời tám worker nếu tài nguyên cho phép |

Giá trị thực tế còn phụ thuộc `PartitionHandler` và executor cụ thể. Hãy phân biệt số partition được tạo với số thread có thể xử lý cùng lúc.

## 9. Partitioning và StepExecution

Mỗi partition tạo một worker `StepExecution` riêng. Trong metadata, các execution có tên được tạo từ tên worker step và tên partition, ví dụ `orderWorker:partition0`.

```text
JobExecution #42
  +-- orderManager
        +-- orderWorker:partition0  -> COMPLETED
        +-- orderWorker:partition1  -> COMPLETED
        +-- orderWorker:partition2  -> FAILED
        +-- orderWorker:partition3  -> COMPLETED
```

Mỗi worker execution có các bộ đếm read/write/skip, trạng thái và `ExecutionContext` riêng. Nhờ vậy có thể theo dõi partition nào hoàn tất, partition nào thất bại và checkpoint của từng worker.

Manager step tổng hợp kết quả worker. Nếu có worker thất bại, manager/job có thể kết thúc thất bại theo hành vi partition handler và flow. Các worker khác có thể đã hoàn thành và commit dữ liệu của họ; partitioning không tạo một transaction duy nhất bao trùm mọi partition.

## 10. Restart partitioned step

Khi job được restart, Spring Batch dùng metadata trong `JobRepository` để nhận diện các worker execution trước đó. Những partition đã hoàn thành thường không cần chạy lại; partition thất bại hoặc chưa hoàn tất có thể được khởi chạy lại theo quy tắc restart.

Ví dụ:

```text
Execution #1
  partition0 -> COMPLETED
  partition1 -> COMPLETED
  partition2 -> FAILED
  partition3 -> COMPLETED

Restart cùng JobInstance
  partition0 -> bỏ qua vì đã hoàn thành
  partition1 -> bỏ qua vì đã hoàn thành
  partition2 -> chạy lại từ checkpoint của worker
  partition3 -> bỏ qua vì đã hoàn thành
```

Để restart đúng, partitioner cần tạo lại partition có tên và phạm vi tương ứng với lần chạy trước. Không nên sinh tên partition ngẫu nhiên hoặc thay đổi range tùy ý giữa các lần restart của cùng JobInstance.

Ví dụ, nếu lần đầu `partition2` xử lý ID 501–750 nhưng lần restart cùng JobInstance lại gán ID 600–850 cho tên đó, metadata cũ có thể được áp dụng sai phạm vi dữ liệu. Hãy giữ quy tắc phân chia ổn định theo JobParameters và snapshot dữ liệu của lần chạy.

## 11. Dữ liệu thay đổi trong lúc partitioning

Chia dữ liệu theo min/max ID hoặc theo thời gian cần xét đến dữ liệu mới được thêm hoặc thay đổi khi job đang chạy.

Giả sử partitioner truy vấn `MAX(ORDER_ID)` là 1.000 rồi tạo các range đến ID 1.000. Trong lúc worker đang chạy, ứng dụng online thêm ID 1.001. Bản ghi mới không thuộc partition nào của job hiện tại. Đây có thể là hành vi đúng nếu job xử lý snapshot đến thời điểm bắt đầu; nếu cần xử lý cả dữ liệu mới, phải có watermark hoặc lượt chạy tiếp theo.

Các cách kiểm soát:

- Chụp mốc `maxId` hoặc watermark tại thời điểm bắt đầu và dùng nhất quán cho mọi partition.
- Dùng snapshot isolation hoặc cơ chế snapshot phù hợp nếu cần dữ liệu nhất quán tại cùng thời điểm.
- Truyền watermark trong JobParameters hoặc JobExecutionContext để restart vẫn dùng cùng giới hạn.
- Đảm bảo dữ liệu trong range không bị xóa hoặc thay đổi làm sai ý nghĩa xử lý trong lúc job chạy.
- Lập lịch một lượt tiếp theo để xử lý dữ liệu phát sinh sau watermark.

Partitioning chỉ chia phạm vi thực thi; nó không tự tạo snapshot nhất quán cho dữ liệu nguồn.

## 12. Cân bằng tải và chọn chiến lược chia

Chia đều số lượng ID không nhất thiết chia đều thời gian xử lý. Một range có thể chứa nhiều bản ghi lớn, nhiều quan hệ hoặc nhiều thao tác ngoài hơn các range khác.

Khi workload lệch, worker nhanh có thể hoàn tất sớm và chờ partition chậm nhất. Tổng thời gian job bị chi phối bởi partition nặng nhất.

Các chiến lược cân bằng:

1. Chia theo số lượng bản ghi ước tính thay vì chỉ theo độ rộng ID.
2. Dùng histogram hoặc thống kê phân bố để chọn ranh giới range.
3. Chia theo nhóm nghiệp vụ có chi phí xử lý tương đương.
4. Tăng số partition so với số thread để executor có nhiều phần việc nhỏ hơn, nếu overhead tạo worker chấp nhận được.
5. Theo dõi thời gian từng `StepExecution` và điều chỉnh thuật toán ở lần chạy sau.

Không nên tạo quá nhiều partition nhỏ nếu mỗi worker tạo overhead đáng kể về metadata, connection và khởi tạo tài nguyên.

## 13. Partitioning cục bộ và remote partitioning

Partitioning có thể chạy các worker trên cùng JVM hoặc phân phối worker sang các tiến trình/nút khác.

| Mô hình | Cách hoạt động | Khi phù hợp |
|---|---|---|
| Local partitioning | Manager dùng `TaskExecutor` để chạy worker step trên thread trong cùng ứng dụng | Muốn tận dụng nhiều core trên một node và chia sẻ tài nguyên ứng dụng |
| Remote partitioning | Manager gửi yêu cầu worker qua middleware/message channel; worker chạy ở process hoặc node khác | Cần mở rộng ngang và phân phối workload trên nhiều máy |

Với remote partitioning, `ExecutionContext` của partition được chuyển cùng yêu cầu thực thi qua cơ chế messaging. Worker cần có cấu hình job/step tương ứng và truy cập được các tài nguyên cần thiết. `JobRepository` phải được cấu hình để manager và worker phối hợp metadata theo mô hình triển khai.

Remote partitioning khác remote chunking. Trong remote partitioning, manager phân chia dữ liệu và worker thực hiện toàn bộ worker step cho partition được giao. Trong remote chunking, manager thường đọc và gửi chunk tới worker để xử lý/ghi theo mô hình khác.

## 14. Phân biệt partitioning với multi-threaded step và split flow

Ba cơ chế đều có thể chạy song song nhưng chia việc ở các cấp khác nhau:

| Cơ chế | Đơn vị song song | Đặc điểm |
|---|---|---|
| Partitioning | Một phần dữ liệu được gán cho một worker `StepExecution` | Mỗi worker có context và trạng thái riêng |
| Multi-threaded step | Các lần xử lý item/chunk trong một step | Có thể chia sẻ một số thành phần step; cần xem xét thread safety |
| `split()` flow | Các flow hoặc step độc lập | Song song các nhánh quy trình khác nhau |

Partitioning phù hợp khi có thể xác định các lát dữ liệu độc lập, ví dụ theo ID range hoặc tenant. Multi-threaded step phù hợp khi một step có thể xử lý các item song song theo cấu hình và component hỗ trợ. `split()` phù hợp khi các nhánh nghiệp vụ khác nhau có thể chạy độc lập.

## 15. Thread safety và tài nguyên trong worker

Mỗi partition có `StepExecution` riêng, nhưng điều đó không tự bảo đảm mọi bean được worker sử dụng đều có instance riêng. Bean Spring singleton vẫn có thể được chia sẻ giữa các worker.

Các lưu ý quan trọng:

- Dùng `@StepScope` cho reader/writer có state hoặc cần nhận partition-specific values.
- Không chia sẻ reader giữ cursor hoặc mutable state giữa các partition.
- Processor dùng chung phải thread-safe hoặc stateless.
- Writer phải chịu được ghi đồng thời, bao gồm unique constraint và thứ tự cập nhật.
- Connection pool cần đủ capacity cho số worker đồng thời cùng các kết nối khác của ứng dụng.
- Giới hạn executor để không làm quá tải database, file system hoặc API bên ngoài.

Nếu hai partition ghi cùng một bản ghi, có thể xảy ra race condition hoặc deadlock. Thiết kế partitioner sao cho dữ liệu ghi không xung đột, hoặc dùng khóa/transaction/unique constraint phù hợp.

## 16. Transaction và lỗi giữa các partition

Mỗi worker step xử lý chunk bằng transaction riêng theo transaction manager của worker. Chunk đã commit ở một partition không tự rollback chỉ vì partition khác thất bại.

```text
partition0: chunk A -> COMMIT -> chunk B -> COMMIT
partition1: chunk A -> COMMIT -> chunk B -> FAILED
partition2: chunk A -> COMMIT -> chunk B -> COMMIT

Kết quả: partition1 thất bại; các commit đã hoàn thành ở partition0 và partition2 vẫn tồn tại.
```

Vì các worker độc lập, job có thể ở trạng thái thất bại dù một phần dữ liệu đã được ghi thành công. Restart cần dựa vào metadata và checkpoint từng worker; writer cũng cần idempotency nếu có thao tác ngoài transaction.

Không giả định partitioning cung cấp atomic commit trên toàn bộ dữ liệu. Nếu nghiệp vụ yêu cầu tất cả hoặc không có gì trên nhiều partition, cần một thiết kế transaction hoặc staging/publish riêng, ví dụ ghi vào bảng staging rồi thực hiện bước publish nguyên tử sau khi tất cả partition hoàn tất.

## 17. Xử lý partition rỗng và dữ liệu không đều

Khi nguồn không có dữ liệu, partitioner có thể không tạo partition. Ứng dụng nên xác định rõ hành vi mong muốn: job hoàn tất với kết quả rỗng, ghi nhận trạng thái không có dữ liệu hay báo lỗi nghiệp vụ.

Với các range không có bản ghi do ID khuyết, worker vẫn có thể chạy và hoàn tất với read count bằng 0. Nếu tạo quá nhiều range rỗng, metadata và chi phí khởi tạo worker tăng mà không mang lại lợi ích.

Có thể kiểm tra số bản ghi trước khi tạo partition, giới hạn partition count không vượt quá workload ước tính và tránh tạo partition rỗng nếu thuật toán chia cho phép. Hãy kiểm thử riêng trường hợp nguồn rỗng vì cách manager xử lý map partition rỗng cần phù hợp với phiên bản/cấu hình cụ thể.

## 18. Những lỗi thường gặp khi partitioning

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Các range bị chồng lấn | Một item được xử lý nhiều lần | Kiểm thử biên inclusive/exclusive và query predicate |
| Có khoảng dữ liệu không được gán | Một số item bị bỏ sót | Bảo đảm các partition bao phủ toàn bộ phạm vi cần xử lý |
| Dùng range ID nhưng phân bố dữ liệu lệch | Một worker chạy lâu hơn hẳn các worker khác | Chia theo thống kê hoặc số bản ghi ước tính |
| Dùng reader singleton có cursor | Worker có thể chia sẻ state và đọc sai dữ liệu | Tạo reader `@StepScope` cho mỗi execution |
| `gridSize` lớn nhưng executor quá nhỏ | Nhiều partition chờ, hoặc hệ thống chịu overhead không cần thiết | Điều chỉnh grid size và pool theo tài nguyên |
| Tên/range partition thay đổi khi restart | Metadata/checkpoint cũ có thể gắn sai phạm vi | Giữ tên và cách chia ổn định cho cùng JobInstance |
| Giả định mọi partition rollback cùng nhau | Dữ liệu partition đã commit vẫn tồn tại khi partition khác lỗi | Thiết kế restart, idempotency hoặc staging/publish |
| Không giới hạn connection pool và worker count | Cạn connection hoặc database quá tải | Đặt concurrency theo capacity của hệ thống |
| Dùng `ExecutionContext` chứa object runtime | Không serialize được metadata | Chỉ lưu key, range và dữ liệu checkpoint nhỏ |

## 19. Kiểm thử partitioner và worker

Partitioning nên được kiểm thử ở cả mức thuật toán chia và tích hợp step.

Các kiểm tra cho `Partitioner`:

1. Tổng số partition không vượt `gridSize` theo quy tắc thiết kế.
2. Các range không chồng lấn.
3. Hợp của các range bao phủ đúng toàn bộ phạm vi dữ liệu.
4. Không có khoảng trống ở ranh giới giữa hai partition.
5. Phần dư được phân phối đúng khi tổng số item không chia hết.
6. Xử lý đúng `gridSize` không hợp lệ, phạm vi rỗng và một item duy nhất.

Các kiểm tra tích hợp:

- Mỗi worker chỉ đọc dữ liệu thuộc partition context của nó.
- Tổng số item được ghi bằng số item hợp lệ trong phạm vi, không bị trùng hoặc thiếu.
- Các worker thực sự chạy đồng thời trong giới hạn executor nếu yêu cầu song song.
- Khi một partition thất bại, metadata ghi đúng trạng thái từng worker.
- Restart cùng JobInstance bỏ qua partition đã hoàn thành và tiếp tục partition cần chạy lại.
- Reader state và checkpoint được khôi phục đúng sau restart.

## 20. Quy trình thiết kế một job partitioned

Có thể triển khai theo trình tự:

1. Xác định tập dữ liệu cần xử lý và khóa có thể chia thành các phần độc lập.
2. Chọn chiến lược partition, bảo đảm không chồng lấn và bao phủ đầy đủ.
3. Xác định snapshot/watermark để dữ liệu nguồn ổn định trong suốt lần chạy.
4. Viết `Partitioner` tạo tên ổn định và `ExecutionContext` nhỏ cho từng phần.
5. Viết worker step dùng `@StepScope` để đọc phạm vi riêng.
6. Cấu hình manager step, `PartitionHandler`, `gridSize` và executor.
7. Đảm bảo worker reader/writer an toàn với concurrency và transaction.
8. Kiểm thử phân chia, hiệu năng, lỗi một partition và restart.
9. Theo dõi thời gian, read/write count và trạng thái từng `StepExecution` trong production.

## Kết luận

Partitioning chia một workload thành nhiều phần độc lập và tạo một worker `StepExecution` cho mỗi partition. `Partitioner` mô tả phạm vi bằng `ExecutionContext`; manager step điều phối worker step; `JobRepository` lưu trạng thái và checkpoint riêng để theo dõi hoặc restart từng phần.

Để partitioning đúng và hiệu quả, các phần phải không chồng lấn, bao phủ dữ liệu cần xử lý, có workload tương đối cân bằng và giữ tên/range ổn định khi restart. Dùng `@StepScope` cho component phụ thuộc context của partition, điều chỉnh executor theo capacity và nhớ rằng transaction của các worker độc lập: partition đã commit không tự rollback khi partition khác thất bại.
