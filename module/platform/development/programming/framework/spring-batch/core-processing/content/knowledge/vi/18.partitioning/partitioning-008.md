# Key partitioning

Trong Spring Batch, key partitioning là cách chia một tập dữ liệu thành nhiều phần dựa trên một khóa ổn định, thường là khóa chính hoặc một business key. Mỗi phần được giao cho một worker Step riêng để xử lý độc lập. Ví dụ, bảng `orders` có thể được chia theo `order_id` thành các khoảng khóa; mỗi partition chỉ đọc những đơn hàng thuộc khoảng của nó.

Key partitioning thường được triển khai bằng `Partitioner`. Partitioner tạo một `ExecutionContext` cho từng partition, trong đó lưu các giá trị như khóa bắt đầu và khóa kết thúc. Spring Batch tạo một `StepExecution` cho mỗi partition và chạy cùng một worker Step với context tương ứng. Nhờ vậy, mỗi worker có thể dùng reader `@StepScope` để lấy phạm vi khóa của chính nó.

## 1. Key partitioning giải quyết vấn đề gì?

Một chunk Step thông thường đọc toàn bộ tập dữ liệu theo một luồng xử lý. Với tập dữ liệu lớn, thời gian chạy có thể dài và khó tận dụng nhiều worker độc lập. Partitioning chia công việc thành nhiều StepExecution nhỏ hơn, mỗi execution xử lý một phần dữ liệu.

Ví dụ, một bảng có 1.000.000 đơn hàng. Có thể chia theo `order_id` thành bốn vùng:

```text
Tập dữ liệu orders
      |
      +-- Partition 0: order_id [1, 250001)
      |
      +-- Partition 1: order_id [250001, 500001)
      |
      +-- Partition 2: order_id [500001, 750001)
      |
      +-- Partition 3: order_id [750001, 1000001)
```

Mỗi worker chỉ đọc các dòng thuộc khoảng của mình. Các worker có thể chạy tuần tự hoặc song song tùy cấu hình TaskExecutor và hạ tầng.

Key partitioning hữu ích khi:

- Dữ liệu có khóa ổn định và có thể chia thành các phạm vi không chồng lấn.
- Mỗi item có thể được xử lý độc lập với item ở partition khác.
- Nguồn dữ liệu hỗ trợ truy vấn theo khóa hiệu quả, đặc biệt khi khóa có index.
- Muốn tăng throughput bằng cách xử lý nhiều partition đồng thời.
- Cần theo dõi và restart tiến độ của từng partition riêng.

Partitioning không tự làm một truy vấn chậm trở nên nhanh hơn nếu database không đủ năng lực. Nó phân chia công việc và cho phép concurrency; hiệu quả thực tế phụ thuộc index, query plan, tải database, transaction, writer và số worker.

## 2. Key partitioning khác chunk processing như thế nào?

Chunk processing và partitioning giải quyết hai cấp độ khác nhau:

- **Chunk processing** chia công việc của một Step thành các chunk, mỗi chunk có transaction và commit boundary riêng.
- **Partitioning** chia toàn bộ input thành nhiều phạm vi công việc; mỗi phạm vi được chạy bởi một StepExecution riêng. Bên trong mỗi worker Step, vẫn có thể dùng chunk processing.

```text
Manager Step
   |
   +-- Partition A --> Worker Step A --> Chunk 1, Chunk 2, ...
   |
   +-- Partition B --> Worker Step B --> Chunk 1, Chunk 2, ...
   |
   +-- Partition C --> Worker Step C --> Chunk 1, Chunk 2, ...
```

Mỗi worker thường dùng cùng định nghĩa Step nhưng nhận `ExecutionContext` khác nhau. Mỗi worker có `StepExecution`, bộ đếm, transaction và checkpoint riêng. Như vậy, partition xác định worker xử lý *phần dữ liệu nào*, còn chunk xác định worker commit *theo nhóm item nào*.

## 3. Partitioner và ExecutionContext

Interface `Partitioner` có nhiệm vụ tạo các partition:

```java
public interface Partitioner {
    Map<String, ExecutionContext> partition(int gridSize);
}
```

Mỗi entry trong map gồm:

- Key của map: tên partition, ví dụ `orders-partition-0`.
- Value: `ExecutionContext` chứa tham số riêng của partition.

Với key range partitioning, context thường chứa:

| Key trong ExecutionContext | Ý nghĩa |
|---|---|
| `minIdInclusive` | Khóa bắt đầu, được bao gồm trong partition. |
| `maxIdExclusive` | Khóa kết thúc, không bao gồm trong partition. |
| `partitionNumber` | Số thứ tự partition để log hoặc quan sát. |

Dùng khoảng nửa mở `[minIdInclusive, maxIdExclusive)` giúp hai partition liền kề không trùng nhau: partition trước kết thúc tại `x` nhưng không lấy `x`, partition sau bắt đầu từ `x` và có lấy `x`.

Ví dụ:

```text
Partition 0: id >= 1   AND id < 101
Partition 1: id >= 101 AND id < 201
Partition 2: id >= 201 AND id < 301
```

Các khoảng trên không chồng lấn và không có khoảng trống giữa chúng. Dù khóa trong bảng có thể bị khuyết, một dòng có khóa hợp lệ vẫn chỉ thuộc tối đa một partition.

## 4. Tạo key range partitioner

Ví dụ sau chia bảng `orders` theo khóa số nguyên `order_id`. Partitioner truy vấn khóa nhỏ nhất và lớn nhất, sau đó chia miền khóa thành các khoảng có độ rộng gần bằng nhau.

```java
public class OrderIdRangePartitioner implements Partitioner {

    private final JdbcTemplate jdbcTemplate;

    public OrderIdRangePartitioner(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize < 1) {
            throw new IllegalArgumentException("gridSize must be positive");
        }

        Long minId = jdbcTemplate.queryForObject(
                "select min(order_id) from orders", Long.class);
        Long maxId = jdbcTemplate.queryForObject(
                "select max(order_id) from orders", Long.class);

        Map<String, ExecutionContext> result = new LinkedHashMap<>();

        if (minId == null || maxId == null) {
            ExecutionContext emptyContext = new ExecutionContext();
            emptyContext.putLong("minIdInclusive", 0L);
            emptyContext.putLong("maxIdExclusive", 0L);
            emptyContext.putInt("partitionNumber", 0);
            result.put("orders-partition-0", emptyContext);
            return result;
        }

        long maxIdExclusive = Math.addExact(maxId, 1L);
        long keyRange = Math.subtractExact(maxIdExclusive, minId);
        int partitionCount = (int) Math.min((long) gridSize, keyRange);

        long baseSize = keyRange / partitionCount;
        long remainder = keyRange % partitionCount;
        long nextStart = minId;

        for (int i = 0; i < partitionCount; i++) {
            long size = baseSize + (i < remainder ? 1 : 0);
            long endExclusive = Math.addExact(nextStart, size);

            ExecutionContext context = new ExecutionContext();
            context.putLong("minIdInclusive", nextStart);
            context.putLong("maxIdExclusive", endExclusive);
            context.putInt("partitionNumber", i);

            result.put("orders-partition-" + i, context);
            nextStart = endExclusive;
        }

        return result;
    }
}
```

Ví dụ giả định `order_id` là khóa số nguyên có miền giá trị phù hợp với `long`, `maxId + 1` không vượt giới hạn kiểu và toàn bộ khoảng khóa không tràn số. `Math.addExact`/`subtractExact` giúp phát hiện tràn số thay vì âm thầm tạo ranh giới sai. Với khóa có miền rộng hơn hoặc kiểu khác, cần dùng chiến lược tính range tương ứng.

Nếu bảng rỗng, ví dụ tạo một partition rỗng với khoảng `[0, 0)` để worker chạy và không đọc được item nào. Ứng dụng cũng có thể chọn một cách xử lý riêng cho Job không có dữ liệu, nhưng cần định nghĩa rõ flow và kết quả mong muốn.

## 5. Vì sao nên dùng khoảng nửa mở?

Giả sử chia dữ liệu thành ba khoảng:

| Partition | Điều kiện SQL | Thuộc tính |
|---|---|---|
| A | `id >= 1 AND id < 101` | Lấy 1 đến 100. |
| B | `id >= 101 AND id < 201` | Lấy 101 đến 200. |
| C | `id >= 201 AND id < 301` | Lấy 201 đến 300. |

Nếu dùng cả hai đầu inclusive (`BETWEEN 1 AND 100`, `BETWEEN 100 AND 200`), khóa 100 có thể xuất hiện trong hai partition. Nếu dùng hai đầu exclusive, một số khóa biên có thể bị bỏ sót.

Khoảng nửa mở có quy tắc đơn giản:

```sql
WHERE order_id >= :minIdInclusive
  AND order_id <  :maxIdExclusive
```

Điều kiện này dễ nối tiếp và kiểm thử. Với khóa kiểu ngày/giờ hoặc chuỗi, cũng có thể dùng khoảng nửa mở nếu phép so sánh và collation được xác định ổn định.

## 6. Đưa Partitioner vào manager Step

Partitioning Step có hai vai trò:

- **Manager Step:** tạo partition, điều phối worker và tổng hợp kết quả.
- **Worker Step:** thực hiện công việc thực tế trên dữ liệu thuộc partition được giao.

Ví dụ cấu hình manager Step trong Spring Batch 5:

```java
@Bean
Partitioner orderIdPartitioner(JdbcTemplate jdbcTemplate) {
    return new OrderIdRangePartitioner(jdbcTemplate);
}

@Bean
Step partitionedOrderManagerStep(
        JobRepository jobRepository,
        Step orderWorkerStep,
        Partitioner orderIdPartitioner,
        TaskExecutor partitionTaskExecutor) {

    return new StepBuilder("partitionedOrderManagerStep", jobRepository)
            .partitioner("orderWorkerStep", orderIdPartitioner)
            .step(orderWorkerStep)
            .gridSize(4)
            .taskExecutor(partitionTaskExecutor)
            .build();
}
```

`.partitioner("orderWorkerStep", orderIdPartitioner)` chỉ định tên worker Step và Partitioner. `.step(orderWorkerStep)` cung cấp định nghĩa worker. `.gridSize(4)` yêu cầu tạo khoảng bốn partition trong ví dụ này; số partition thực tế có thể ít hơn nếu Partitioner trả về ít entry hơn.

`gridSize` là gợi ý/kích thước lưới cho việc phân chia, không tự đảm bảo có bốn thread chạy cùng lúc. Concurrency phụ thuộc TaskExecutor và giới hạn tài nguyên.

## 7. Chạy partition song song bằng TaskExecutor

Để các partition chạy đồng thời trong cùng JVM, manager Step có thể sử dụng `TaskExecutor`:

```java
@Bean
TaskExecutor partitionTaskExecutor() {
    SimpleAsyncTaskExecutor executor =
            new SimpleAsyncTaskExecutor("orders-partition-");
    executor.setConcurrencyLimit(4);
    return executor;
}
```

Trong ví dụ, giới hạn concurrency là bốn tác vụ. Có thể dùng `ThreadPoolTaskExecutor` để kiểm soát core/max pool size, queue capacity và thread naming theo chính sách vận hành.

Cần phân biệt:

- Số partition được tạo: do Partitioner trả về, có liên quan `gridSize`.
- Số partition chạy đồng thời: do TaskExecutor và giới hạn tài nguyên.
- Số chunk trong mỗi partition: do chunk size hoặc CompletionPolicy của worker Step.

Nếu có 16 partition nhưng executor chỉ cho phép 4 thread, các partition sẽ được xử lý theo nhiều đợt. Tăng số thread không phải lúc nào cũng tăng throughput; database có thể trở thành nút thắt do quá nhiều truy vấn và transaction đồng thời.

## 8. Worker Step nhận khóa của partition

Worker Step dùng `ExecutionContext` riêng của partition. Các giá trị trong context có thể được inject vào bean `@StepScope` bằng SpEL:

```java
@Bean
@StepScope
JdbcCursorItemReader<Order> partitionOrderReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minIdInclusive']}") Long minId,
        @Value("#{stepExecutionContext['maxIdExclusive']}") Long maxId) {

    return new JdbcCursorItemReaderBuilder<Order>()
            .name("partitionOrderReader")
            .dataSource(dataSource)
            .sql("""
                    SELECT order_id, customer_id, amount
                    FROM orders
                    WHERE order_id >= ? AND order_id < ?
                    ORDER BY order_id
                    """)
            .preparedStatementSetter(statement -> {
                statement.setLong(1, minId);
                statement.setLong(2, maxId);
            })
            .rowMapper((rs, rowNum) -> new Order(
                    rs.getLong("order_id"),
                    rs.getString("customer_id"),
                    rs.getBigDecimal("amount")))
            .fetchSize(500)
            .saveState(true)
            .build();
}
```

`@StepScope` rất quan trọng ở đây. Worker Step được dùng cho nhiều partition; mỗi StepExecution phải nhận đúng hai giới hạn khóa của chính partition đó. Nếu reader là singleton giữ `minId`/`maxId` trong field, các worker có thể dùng nhầm phạm vi của nhau.

Reader dùng câu SQL có tham số bind thay vì ghép giá trị vào chuỗi SQL. Điều này tránh lỗi quoting và giúp database tái sử dụng prepared statement. Cột `order_id` nên có index phù hợp để range scan hiệu quả.

## 9. Khai báo worker Step và Job

Worker Step có thể là chunk-oriented Step bình thường. Nó chỉ khác ở chỗ reader được giới hạn theo partition context:

```java
@Bean
Step orderWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> partitionOrderReader,
        ItemProcessor<Order, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("orderWorkerStep", jobRepository)
            .<Order, Order>chunk(200, transactionManager)
            .reader(partitionOrderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}

@Bean
Job partitionedOrderJob(
        JobRepository jobRepository,
        Step partitionedOrderManagerStep) {

    return new JobBuilder("partitionedOrderJob", jobRepository)
            .start(partitionedOrderManagerStep)
            .build();
}
```

Trong ví dụ, mỗi partition có một worker StepExecution và bên trong worker đó xử lý chunk 200 item. Cần bảo đảm các bean stateful được tạo theo `@StepScope` hoặc có thread safety phù hợp. Các writer dùng chung giữa worker phải hỗ trợ sử dụng đồng thời hoặc được tạo riêng theo scope.

## 10. Các kiểu key partitioning

Range partitioning theo khóa số là một cách phổ biến, nhưng không phải cách duy nhất.

### Range partitioning

Mỗi worker nhận một khoảng khóa:

```sql
WHERE id >= :lowerBound AND id < :upperBound
```

Phù hợp khi khóa có thứ tự và database có index. Cần kiểm soát phân bố dữ liệu vì khoảng khóa bằng nhau không nhất thiết có số dòng bằng nhau.

### Hash/modulo partitioning

Có thể chia theo phần dư của khóa:

```sql
WHERE MOD(order_id, :partitionCount) = :partitionNumber
```

Các bucket thường không chồng lấn và có thể phân phối khá đều nếu khóa phân bố tốt. Tuy nhiên, hàm trên cột có thể làm database khó dùng index range thông thường; cú pháp modulo và quy tắc với số âm phụ thuộc database. Cần kiểm tra execution plan và đảm bảo cùng một thuật toán hash được dùng ổn định qua restart.

### Partition theo danh sách key hoặc business group

Nếu dữ liệu được chia theo tenant, region, customer group hoặc business unit, mỗi partition có thể nhận một giá trị key:

```sql
WHERE tenant_id = :tenantId
```

Phù hợp khi business key tạo ra các nhóm tự nhiên và mỗi nhóm có thể xử lý độc lập. Nếu số key rất lớn, không nên đưa toàn bộ danh sách key vào một ExecutionContext; hãy lưu một tham chiếu đến danh sách phân vùng hoặc dùng một chiến lược bucket.

## 11. Chọn partition key phù hợp

Một key tốt cần đáp ứng các đặc điểm:

- **Ổn định:** giá trị không thay đổi trong thời gian Job chạy và khi restart.
- **Phân biệt được dữ liệu:** mỗi dòng được gán vào một partition duy nhất.
- **Có thể truy vấn hiệu quả:** database có thể lọc theo key, tốt nhất có index phù hợp.
- **Phân bố hợp lý:** tránh một partition chứa gần như toàn bộ dữ liệu.
- **Có ý nghĩa vận hành:** có thể ghi log, theo dõi và điều tra theo key/range.

Khóa chính tăng dần thường thuận tiện cho range partitioning, nhưng không phải lúc nào cũng cân bằng. Nếu một số khoảng khóa chứa nhiều dòng hơn đáng kể, worker tương ứng sẽ chạy lâu hơn và làm các worker khác phải chờ manager Step hoàn tất.

Không nên partition theo một cột có thể thay đổi trong lúc Job đang chạy, chẳng hạn trạng thái đơn hàng, nếu thay đổi đó có thể làm một dòng chuyển từ partition này sang partition khác. Nên chọn key bất biến hoặc làm việc trên một snapshot nhất quán.

## 12. Cân bằng tải và dữ liệu lệch (skew)

Chia miền khóa thành các khoảng có độ rộng bằng nhau không đồng nghĩa số dòng bằng nhau. Ví dụ, `order_id` từ 1 đến 1.000.000 nhưng chỉ 10% ID cũ có dữ liệu, còn 90% dữ liệu tập trung ở khoảng mới. Chia theo range đều có thể tạo worker chạy rất lâu và các worker khác kết thúc sớm.

Các cách xử lý:

- Dùng thống kê phân bố khóa hoặc histogram để xác định boundary gần số dòng thực tế.
- Chia theo số lượng bản ghi bằng truy vấn có window function nếu database hỗ trợ và execution plan phù hợp.
- Chọn business key hoặc hash bucket có phân bố tốt hơn.
- Tạo nhiều partition nhỏ hơn số worker để scheduler phân phối tải linh hoạt.
- Theo dõi thời gian xử lý mỗi partition và điều chỉnh ranh giới cho lần chạy sau.

Partition nhỏ hơn không tự khắc phục skew nếu mọi partition đều có kích thước dữ liệu rất khác nhau. Cần đo số dòng, thời gian reader/writer và thời gian commit của từng worker.

## 13. Đảm bảo không trùng và không bỏ sót dữ liệu

Tính đúng đắn của key partitioning phụ thuộc vào việc các partition tạo thành một phép chia hợp lệ của tập dữ liệu mục tiêu.

Với range partitioning, cần bảo đảm:

1. Các khoảng không chồng lấn.
2. Các khoảng phủ hết miền khóa được chọn.
3. Mọi dòng thuộc phạm vi nghiệp vụ nằm trong đúng một khoảng.
4. Điều kiện query của worker dùng đúng inclusive/exclusive boundary.
5. Ranh giới không thay đổi ngoài ý muốn giữa lúc tạo partition và lúc worker đọc dữ liệu.

Ví dụ kiểm tra điều kiện SQL cho hai partition liền kề:

```sql
-- Partition A
SELECT COUNT(*)
FROM orders
WHERE order_id >= 1 AND order_id < 101;

-- Partition B
SELECT COUNT(*)
FROM orders
WHERE order_id >= 101 AND order_id < 201;
```

Không dùng `BETWEEN` nếu muốn giữ semantics nửa mở vì `BETWEEN` thường bao gồm cả hai đầu. Khi cần tổng hợp kết quả, có thể so sánh tổng số dòng các partition với số dòng trong phạm vi nguồn tại cùng một snapshot.

## 14. Dữ liệu thay đổi trong khi partition chạy

Một rủi ro quan trọng là dữ liệu nguồn có thể thay đổi sau khi Partitioner truy vấn `min(id)` và `max(id)` nhưng trước khi các worker đọc xong.

Ví dụ:

- Một dòng mới có khóa lớn hơn `maxId` được thêm sau khi partition đã được tạo; dòng đó không thuộc bất kỳ partition nào của lần chạy hiện tại.
- Một dòng bị xóa trước khi worker đọc; worker sẽ không thấy dòng đó.
- Một thuộc tính dùng để lọc dữ liệu thay đổi giữa các worker, làm kết quả không còn cùng một snapshot logic.
- Nếu partition theo cột có thể thay đổi, một dòng có thể di chuyển phạm vi trong lúc Job chạy.

Các lựa chọn:

- Chụp high-watermark (ví dụ max key) tại thời điểm bắt đầu và xác định rõ dữ liệu mới hơn sẽ được xử lý ở lần chạy sau.
- Dùng transaction isolation hoặc snapshot phù hợp với database nếu cần một tập dữ liệu nhất quán.
- Partition theo khóa bất biến và điều kiện nghiệp vụ ổn định.
- Dùng bảng staging hoặc batch membership table để cố định tập item thuộc một lần chạy.
- Ghi nhận business key và trạng thái xử lý để đối soát dữ liệu thêm/xóa trong lúc Job chạy.

Không có một mức isolation mặc định phù hợp cho mọi database. Hãy xác định yêu cầu snapshot, thời gian chạy và tác động lên khóa/undo/version store trước khi chọn.

## 15. Restart của partitioned Step

Partitioning tạo metadata riêng cho từng partition. Manager Step điều phối các worker và JobRepository lưu StepExecution cho các partition. Khi Job thất bại, những partition đã hoàn tất thường có thể được giữ lại; các partition chưa hoàn tất hoặc thất bại có thể được xử lý lại theo chính sách restart.

Để restart đáng tin cậy:

- Dùng tên partition ổn định và có thể tái tạo.
- Giữ cách tính ranh giới nhất quán giữa lần chạy đầu và lần restart.
- Lưu `minIdInclusive`/`maxIdExclusive` trong partition ExecutionContext.
- Đảm bảo reader có `saveState`/`ItemStream` nếu cần checkpoint bên trong partition.
- Thiết kế writer idempotent hoặc có khóa duy nhất để tránh ghi trùng khi một chunk phải chạy lại.
- Không thay đổi identifying JobParameters khiến lần restart thành JobInstance mới.

Một partition có thể chứa nhiều chunk. Checkpoint của reader trong worker giúp tiếp tục bên trong partition; metadata partition giúp manager biết trạng thái worker. Đây là hai cấp độ trạng thái khác nhau.

Nếu nguồn dữ liệu hoặc quy tắc phân vùng thay đổi giữa hai lần chạy, không nên âm thầm tạo boundary mới cho cùng JobInstance. Hãy lưu thông tin snapshot/high-watermark cần thiết trong JobParameters hoặc ExecutionContext để lần restart tái tạo đúng phạm vi dữ liệu ban đầu.

## 16. Partitioning và concurrency an toàn

Khi nhiều worker chạy song song, mỗi worker có StepExecution riêng nhưng có thể dùng chung một số bean singleton. Cần chú ý:

- Reader giữ state nên thường cần `@StepScope`.
- Processor có state mutable cần được tạo riêng hoặc bảo đảm thread safety.
- Writer dùng chung phải an toàn khi nhiều thread gọi đồng thời.
- Không lưu `minId`, `maxId` của partition trong field của singleton reader.
- Giới hạn số worker theo connection pool, CPU, I/O và năng lực database.
- Tránh nhiều partition cùng cập nhật một dòng tổng hợp hoặc cùng ghi vào tài nguyên không hỗ trợ concurrency.

`gridSize` và số thread không nên vượt xa khả năng datasource. Ví dụ, nếu pool chỉ có 5 connection cho cả ứng dụng, cấu hình 32 worker có thể làm phần lớn thread chờ connection và tăng contention thay vì tăng tốc.

## 17. Local partitioning và remote partitioning

Key partitioning mô tả cách chia dữ liệu; cách thực thi partition có thể là local hoặc remote.

- **Local partitioning:** manager và worker Step chạy trong cùng JVM, thường dùng `TaskExecutor` để chạy song song trên các thread.
- **Remote partitioning:** manager gửi thông tin partition đến các worker process khác thông qua middleware hoặc kênh truyền thông được cấu hình. Mỗi worker thực hiện Step trên process riêng.

Trong cả hai trường hợp, partition context cần chứa đủ thông tin để worker biết phạm vi khóa của nó. Remote worker cần nhận và khôi phục context qua cơ chế truyền message; cần xử lý retry, duplicate message và lỗi worker theo hạ tầng triển khai.

Nếu chỉ cần tận dụng nhiều thread trên một ứng dụng, local partitioning thường đơn giản hơn. Nếu cần phân tán tải trên nhiều process hoặc máy chủ, remote partitioning có thể phù hợp, nhưng cần thiết kế thêm vận chuyển dữ liệu, tính sẵn sàng và quan sát.

## 18. Theo dõi từng partition

Mỗi partition có tên và StepExecution riêng, vì vậy có thể theo dõi:

- Tên partition.
- Khóa bắt đầu và kết thúc.
- Trạng thái `BatchStatus` và `ExitStatus`.
- Thời gian bắt đầu/kết thúc.
- Read/write/filter/skip count.
- Commit/rollback count.
- Exception cuối cùng nếu partition thất bại.

Thông tin range trong ExecutionContext rất hữu ích khi điều tra. Ví dụ, nếu partition `orders-partition-2` thất bại, có thể truy vấn đúng phạm vi `order_id` của worker đó thay vì điều tra toàn bộ bảng.

Nên ghi log `partitionName`, `minIdInclusive`, `maxIdExclusive` và JobExecution/StepExecution ID. Không nên log toàn bộ dữ liệu item nếu có thông tin nhạy cảm.

## 19. Những lỗi thường gặp

### Partition range bị chồng lấn

Nếu hai worker cùng lấy khóa biên, một số dòng có thể được xử lý hai lần. Dùng khoảng nửa mở `[start, end)` và kiểm tra predicate SQL.

### Có khoảng trống giữa các range

Nếu ranh giới không được nối tiếp chính xác, một số key có thể không thuộc partition nào. Dùng một biến cursor, đặt `nextStart = previousEndExclusive` và kiểm thử toàn bộ miền.

### Dùng gridSize như giới hạn concurrency

`gridSize` liên quan đến việc tạo partition; TaskExecutor quyết định cách thực thi và số tác vụ đồng thời. Cấu hình cả hai theo mục tiêu rõ ràng.

### Reader không có StepScope

Nếu reader không nhận context riêng của StepExecution, nhiều worker có thể dùng cùng phạm vi khóa. Dùng `@StepScope` cho reader nhận partition context.

### Chia đều miền key nhưng dữ liệu lệch

Range có độ rộng bằng nhau không đồng nghĩa số dòng bằng nhau. Dùng histogram, business bucket hoặc ranh giới dựa trên số lượng dòng khi cần cân bằng.

### Partition key thay đổi khi Job chạy

Một dòng có thể di chuyển phạm vi hoặc bị bỏ sót giữa các worker. Chọn key bất biến và snapshot/high-watermark rõ ràng.

### Tăng worker quá nhiều

Database connection pool, lock contention và I/O có thể trở thành nút thắt. Đo throughput rồi tăng concurrency từng bước.

### Restart tạo boundary khác lần đầu

Nếu dữ liệu nguồn thay đổi hoặc thuật toán partition không ổn định, cùng JobInstance có thể xử lý phạm vi khác. Lưu snapshot và bảo đảm partition name/boundary có thể tái tạo.

### Writer không an toàn khi chạy lại

Partition hoặc chunk có thể được chạy lại sau lỗi. Dùng unique key, upsert hoặc cơ chế idempotency phù hợp.

## 20. Quy trình triển khai key partitioning

Khi xây dựng partitioned Job theo key, có thể đi theo trình tự:

1. Chọn key ổn định, có thể phân biệt dữ liệu và được index.
2. Xác định phạm vi dữ liệu của lần chạy, ví dụ business date hoặc high-watermark.
3. Chọn chiến lược range, hash/modulo hoặc business key.
4. Viết Partitioner tạo map tên partition → ExecutionContext.
5. Định nghĩa ranh giới không chồng lấn và phủ hết tập dữ liệu mục tiêu.
6. Tạo worker Step với reader `@StepScope` lấy key từ `stepExecutionContext`.
7. Cấu hình manager Step bằng `.partitioner(...).step(...).gridSize(...)`.
8. Chọn TaskExecutor và concurrency phù hợp với connection pool, database và CPU.
9. Bảo đảm reader/writer có state và thread safety phù hợp.
10. Kiểm thử partition rỗng, dữ liệu thưa, key biên, dữ liệu mới phát sinh và restart.
11. Theo dõi số dòng, thời gian và trạng thái từng partition để phát hiện skew.

| Yêu cầu | Thiết kế nên dùng |
|---|---|
| Chia bảng theo khóa chính tăng dần | Range partitioning với `[min, max)` |
| Chia dữ liệu theo tenant/region | Partition theo business key |
| Khóa phân bố đều, muốn tạo bucket cố định | Hash/modulo partitioning |
| Cần worker chạy song song trong một JVM | Local partitioning với TaskExecutor |
| Cần xử lý trên nhiều process/máy | Remote partitioning |
| Cần restart từng vùng dữ liệu | Partition context ổn định và worker Step có checkpoint |

## Kết luận

Key partitioning chia tập dữ liệu thành các phần không chồng lấn dựa trên một khóa ổn định. `Partitioner` tạo tên partition và `ExecutionContext` chứa phạm vi khóa; manager Step giao từng phần cho worker Step, nơi reader `@StepScope` dùng các giới hạn đó để truy vấn đúng dữ liệu. Range partitioning với khoảng nửa mở `[minIdInclusive, maxIdExclusive)` giúp tránh trùng hoặc bỏ sót ở ranh giới. Để đạt hiệu quả và restart an toàn, cần chọn key có index và phân bố hợp lý, giữ boundary ổn định, giới hạn concurrency theo năng lực database, và thiết kế reader/writer hỗ trợ checkpoint cùng idempotency.
