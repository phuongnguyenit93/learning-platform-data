# Map tên partition sang ExecutionContext trong Spring Batch

## 1. Vì sao `Partitioner` trả về một `Map`?

Khi xử lý vài triệu bản ghi bằng Spring Batch, chạy nhiều thread chưa đủ: framework cần biết **mỗi worker chịu trách nhiệm cho phần dữ liệu nào**. Trong chương **Partitioner** của module **SPRING_BATCH_SCALING_OPERATIONS**, kỹ thuật then chốt là ánh xạ **tên partition** sang **`ExecutionContext` chứa tham số công việc**.

Đây là hợp đồng chính của interface `org.springframework.batch.core.partition.support.Partitioner`:

```java
public interface Partitioner {
    Map<String, ExecutionContext> partition(int gridSize);
}
```

Một implementation có thể trả về:

```text
Map<String, ExecutionContext>
├── "partition0" → { "minId": 1,      "maxId": 250000,  "batchId": "B20261126" }
├── "partition1" → { "minId": 250001, "maxId": 500000,  "batchId": "B20261126" }
├── "partition2" → { "minId": 500001, "maxId": 750000,  "batchId": "B20261126" }
└── "partition3" → { "minId": 750001, "maxId": 1000000, "batchId": "B20261126" }
```

Ý nghĩa thực tế:

- **Key** của map là một tên partition ổn định, ví dụ `partition0`. Nó giúp Spring Batch nhận diện phần việc khi tạo và khôi phục `StepExecution`.
- **Value** là một đối tượng `ExecutionContext` **riêng** của partition, chứa những tham số worker cần: khoảng ID, mã tenant, đường dẫn file, ngày xử lý, phiên bản snapshot...
- Manager step đưa các context này vào các worker step. Các worker có thể dùng cùng một **định nghĩa step**, nhưng nhận dữ liệu đầu vào khác nhau.
- Một context không phải một thread, cũng không phải toàn bộ tập record. Nó là **mô tả phần việc** và nơi framework có thể duy trì trạng thái cần thiết cho restart.

Đây là điểm nối giữa phân chia dữ liệu, thực thi song song và quản lý lỗi. Với workload lớn, thiết kế map chính xác giúp tránh các lỗi phổ biến: xử lý trùng dữ liệu, bỏ sót vùng, ghi đè checkpoint, hoặc restart trên một vùng khác với lần chạy đầu.

Sau bài học, bạn sẽ biết cách tạo map, đặt tên key, chọn dữ liệu cho context, binding context vào reader bằng `@StepScope`, kiểm tra kết quả, và thiết kế an toàn khi retry/restart trong local hoặc remote partitioning.

## 2. Bốn đối tượng cần phân biệt

| Khái niệm | Đại diện cho | Không đồng nghĩa với |
| --- | --- | --- |
| `Partitioner` | Bộ tạo kế hoạch chia công việc: tên partition → context. | Một worker đang chạy, một thread, hoặc query reader. |
| `ExecutionContext` | Bản đồ key-value lưu tham số/trạng thái thực thi cho một scope. | `ApplicationContext`, bean scope, transaction hay cấu hình executor. |
| `StepExecution` | Một lần thực thi step cụ thể, mang trạng thái, số liệu và context. | Tên partition thuần túy, hoặc một JobInstance. |
| `TaskExecutor` / `PartitionHandler` | Cơ chế điều phối và thực thi các worker partition. | Bộ tạo range hoặc cơ chế bảo đảm exactly-once. |

Trong partitioning, **manager step** nắm kế hoạch, còn **worker step** thực thi một vùng dữ liệu. Spring Batch dùng tên do partitioner tạo để sinh định danh worker execution, thường thấy dạng `workerStep:partition0`. Mỗi worker execution gắn với context tương ứng.

Ví dụ minh họa:

```text
                  Job
                   |
          Manager step "ordersManager"
                   |
          Partitioner.partition(3)
                   |
      +------------+------------+
      |            |            |
"partition0"  "partition1"  "partition2"
      |            |            |
EC {1..100}  EC {101..200} EC {201..300}
      |            |            |
     workerStep:partition0
             workerStep:partition1
                          workerStep:partition2
      |            |            |
      +------------+------------+
                   |
           Tổng hợp kết quả
```

`EC` viết tắt của `ExecutionContext`; sơ đồ nhấn mạnh quan hệ **một tên → một context → một worker step execution**. Cách bố trí dọc trong hình không biểu thị thứ tự thực thi.

### `ExecutionContext` là gì?

`ExecutionContext` của Spring Batch là nơi lưu các cặp khóa–giá trị liên quan đến thực thi. Nó hỗ trợ phương thức theo kiểu:

```java
ExecutionContext context = new ExecutionContext();
context.putString("batchId", "B20261126");
context.putLong("minId", 1L);
context.putLong("maxId", 250_000L);
context.putInt("attemptBudget", 3);

String batchId = context.getString("batchId");
long minId = context.getLong("minId");
long maxId = context.getLong("maxId");
```

`ExecutionContext` còn được dùng bởi reader/writer để lưu checkpoint. Vì thế **tham số partition** và **state xử lý** có thể cùng nằm trong step execution context, nhưng không nên tùy tiện ghi đè các key do component khác sở hữu.

## 3. Hợp đồng `Map<String, ExecutionContext>`

`partition(int gridSize)` nhận một số `gridSize`. Đây là **gợi ý số vùng** do manager cung cấp, không phải số luồng bắt buộc và không ép implementation phải tạo đúng từng ấy entry.

Một map hợp lệ cần các tính chất:

1. **Key không trùng:** map chỉ chứa một value cho mỗi tên. Hai vùng cùng key sẽ ghi đè nhau nếu dùng `put` không kiểm tra.
2. **Tên xác định và ổn định:** với cùng input và cùng kế hoạch partition, tên không nên thay đổi khi retry/restart.
3. **Value không null:** mỗi tên có một `ExecutionContext` hợp lệ.
4. **Context riêng:** tạo một instance `ExecutionContext` cho **mỗi partition**; không tái sử dụng cùng object rồi thay giá trị trong vòng lặp.
5. **Đủ dữ liệu định tuyến:** worker phải phân biệt rõ vùng mình sở hữu, ví dụ `minId/maxId` và `batchId`.
6. **Có phạm vi không chồng lấn:** nếu mỗi record chỉ nên được xử lý một lần, các điều kiện đọc của worker phải loại trừ nhau.
7. **Có cơ chế bao phủ:** tổng các vùng phải phủ toàn bộ đầu vào được chốt và dự định xử lý.
8. **Dữ liệu context có thể lưu/đọc lại:** ưu tiên `String`, số, boolean và các kiểu đơn giản được serializer của JobRepository hỗ trợ.

**`gridSize` không phải số worker đồng thời.** Ví dụ partitioner trả 16 entry nhưng executor chỉ có 4 thread thì thường tối đa 4 worker partition cùng chạy tại một thời điểm trong local partitioning. Số worker đang chạy còn bị ảnh hưởng bởi các tài nguyên như JDBC connection, giới hạn downstream và các job khác.

### Tên partition có vai trò vận hành

Chọn tên dễ truy vết và ổn định, ví dụ `partition0000`, `partition0001` hoặc `tenant-acme`. Không chọn `UUID.randomUUID()` hay timestamp mới mỗi lần gọi `partition()`, vì hệ thống có thể không khớp phần việc khi restart.

Nếu tên có chứa dấu phân cách hay ký tự đặc biệt, hãy dùng quy ước dễ log và không mơ hồ; nên tránh đưa thông tin bí mật hoặc thông tin định danh cá nhân vào tên. Một chuỗi tên ngắn, nhất quán giúp tra cứu log, metric, metadata và lỗi của từng worker.

### Không trả cùng object cho tất cả tên

Đây là lỗi logic nguy hiểm:

```java
// SAI: cùng một instance bị sửa và gán cho mọi partition.
ExecutionContext shared = new ExecutionContext();

for (int i = 0; i < 4; i++) {
    shared.putLong("minId", ...);
    shared.putLong("maxId", ...);
    partitions.put("partition" + i, shared);
}
```

Mọi key cuối cùng có thể trỏ đến context với **giá trị của lần lặp cuối**. Worker sẽ đọc cùng một vùng, dẫn tới trùng lặp dữ liệu hoặc bỏ sót hàng loạt.

Cách đúng là khởi tạo **`new ExecutionContext()` bên trong mỗi vòng lặp**.

## 4. Thiết kế nội dung của mỗi ExecutionContext

Các thông tin nên đưa vào context là **tham số nhận diện phần việc**, thay vì toàn bộ dữ liệu cần xử lý.

| Key gợi ý | Kiểu | Vai trò |
| --- | --- | --- |
| `batchId` | String | Xác định dataset/snapshot bất biến được xử lý. |
| `minId` | long | Khóa ID bắt đầu, dùng cận dưới bao gồm. |
| `maxId` | long | Khóa ID kết thúc, dùng cận trên bao gồm. |
| `tenantId` | String | Giới hạn dữ liệu theo tenant, nếu kiến trúc cần. |
| `inputResource` | String | Định danh/path tệp đầu vào của một vùng. |
| `partitionVersion` | int | Phiên bản sơ đồ chia vùng, nếu cần migration/kiểm chứng. |

Không nhồi hàng triệu item, JSON lớn, JDBC connection, `DataSource`, service bean, lambda hoặc thread object vào `ExecutionContext`. Context được lưu qua JobRepository ở các thời điểm thích hợp; giữ nó nhỏ giúp metadata gọn, tránh serializer không hỗ trợ object và giảm chi phí I/O.

Không lưu password, token, connection secret hay dữ liệu nhạy cảm vào context. Thay vào đó đưa **định danh** nguồn dữ liệu hoặc credential reference; worker lấy cấu hình từ cơ chế quản lý bí mật phù hợp.

### Namespace key để tránh đụng nhau

Nếu ứng dụng dùng nhiều component và reader tự ghi checkpoint, có thể đặt tên tham số như:

```java
context.putLong("range.minId", minId);
context.putLong("range.maxId", maxId);
context.putString("input.batchId", batchId);
```

Worker sẽ truy cập bằng đúng key, ví dụ `stepExecutionContext['range.minId']`. Đặt prefix không phải yêu cầu bắt buộc của Spring Batch, nhưng giúp người đọc metadata biết key nào thuộc về kế hoạch partition và key nào thuộc về reader/writer.

Để đơn giản, các ví dụ code tiếp theo dùng ba key `batchId`, `minId` và `maxId`.

## 5. Ví dụ đầy đủ: tạo map theo range ID

Giả sử một batch đã chốt có ID từ 101 đến 125 và muốn chia thành 4 partition. Quy ước dùng **cận bao gồm cả hai đầu**: `[minId,maxId]`.

```text
partition0 → {batchId="B42", minId=101, maxId=107}
partition1 → {batchId="B42", minId=108, maxId=113}
partition2 → {batchId="B42", minId=114, maxId=119}
partition3 → {batchId="B42", minId=120, maxId=125}
```

Mỗi ID trong miền xuất hiện ở đúng một khoảng. Nếu bảng có lỗ hổng ID thì vài vị trí trong khoảng không có record thật; điều đó không làm range sai.

### Triển khai Java

Ví dụ sau theo Spring Batch 5.x và Java 17+. `BigInteger` được dùng ở phần **tính toán biên**, tránh tràn số khi miền ID `BIGINT` quá lớn. Import cần thiết gồm `Partitioner`, `ExecutionContext`, `BigInteger`, `Map`, `LinkedHashMap`, `Collections` và `Objects`.

```java
public final class IdRangePartitioner implements Partitioner {

    private final long minId;
    private final long maxId;
    private final String batchId;

    public IdRangePartitioner(long minId, long maxId, String batchId) {
        this.minId = minId;
        this.maxId = maxId;
        this.batchId = Objects.requireNonNull(batchId, "batchId");
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize < 1) {
            throw new IllegalArgumentException("gridSize must be positive");
        }

        // Tập đã chốt nhưng không có bản ghi.
        if (minId > maxId) {
            return Collections.emptyMap();
        }

        BigInteger one = BigInteger.ONE;
        BigInteger total = BigInteger.valueOf(maxId)
            .subtract(BigInteger.valueOf(minId))
            .add(one);

        // Không tạo nhiều range hơn số giá trị ID trong miền.
        int count = total.compareTo(BigInteger.valueOf(gridSize)) < 0
            ? total.intValueExact()
            : gridSize;

        BigInteger[] qr = total.divideAndRemainder(
            BigInteger.valueOf(count)
        );

        BigInteger normalWidth = qr[0];
        int extra = qr[1].intValueExact();

        Map<String, ExecutionContext> result = new LinkedHashMap<>();
        BigInteger cursor = BigInteger.valueOf(minId);

        for (int i = 0; i < count; i++) {
            BigInteger width = normalWidth.add(
                i < extra ? one : BigInteger.ZERO
            );
            BigInteger upper = cursor.add(width).subtract(one);

            ExecutionContext context = new ExecutionContext();
            context.putString("batchId", batchId);
            context.putLong("minId", cursor.longValueExact());
            context.putLong("maxId", upper.longValueExact());

            String partitionName = "partition" + i;
            result.put(partitionName, context);

            cursor = upper.add(one);
        }

        return result;
    }
}
```

Điểm quan trọng trong code:

- `result` là `Map<String,ExecutionContext>`; mỗi vòng lặp tạo **context riêng** và key riêng.
- `minId` và `maxId` được đặt vào context, chứ không truyền trực tiếp qua biến thread-local hoặc singleton mutable field.
- Số partition tạo ra là `min(gridSize, số giá trị trong miền)`. Đó là lựa chọn cụ thể của implementation này; interface không bắt buộc mọi partitioner phải làm vậy.
- Các range liên tiếp và không trùng nhau. Nếu tổng miền có `L` giá trị, mỗi range có độ rộng `q` hoặc `q+1`, trong đó `q = floor(L/count)`.
- `BigInteger` không làm thay đổi schema ID: các biên thực tế vẫn được lưu dưới dạng `long`, vì chúng bắt đầu/kết thúc trong phạm vi `long` của nguồn.
- Trả map rỗng với tập đầu vào rỗng phải được kiểm chứng theo quy tắc hoàn thành job thực tế. Không gán range giả `[0,0]` để tránh truy vấn sai dữ liệu.

### Vì sao lại dùng LinkedHashMap?

`LinkedHashMap` cho thứ tự lặp xác định theo thứ tự thêm key; nó giúp đọc log hoặc debug dễ hơn. Tuy nhiên, Spring Batch không bảo đảm worker chạy/commit theo thứ tự key. Nếu nghiệp vụ yêu cầu *thứ tự toàn cục*, nhiều partition đồng thời thường không phù hợp.

### Kiểm tra kết quả map

```java
Map<String, ExecutionContext> parts =
    new IdRangePartitioner(101L, 125L, "B42").partition(4);

parts.forEach((name, ctx) -> System.out.printf(
    "%s: batch=%s, range=[%d,%d]%n",
    name,
    ctx.getString("batchId"),
    ctx.getLong("minId"),
    ctx.getLong("maxId")
));
```

Kết quả dự kiến:

```text
partition0: batch=B42, range=[101,107]
partition1: batch=B42, range=[108,113]
partition2: batch=B42, range=[114,119]
partition3: batch=B42, range=[120,125]
```

Đây là kiểm tra về **cấu trúc map và tính liên tục của range**, chưa phải bằng chứng đã đọc đúng từng record từ database.

## 6. Tạo partition theo dữ liệu thực tế

Trong production, `minId` và `maxId` thường lấy từ database **sau khi tập dữ liệu đầu vào đã chốt**. Ví dụ bảng `orders_staging` có khóa `id` kiểu `BIGINT` và `batch_id`:

```sql
SELECT MIN(id) AS min_id, MAX(id) AS max_id
FROM orders_staging
WHERE batch_id = :batchId;
```

Một adapter có thể lấy biên và ủy quyền cho `IdRangePartitioner`. Đây là ví dụ Java tập trung vào cách tạo `Map`, không bao gồm toàn bộ cấu hình datasource:

```java
public final class DatabaseOrdersPartitioner implements Partitioner {

    private final JdbcTemplate jdbcTemplate;
    private final String batchId;

    public DatabaseOrdersPartitioner(
            JdbcTemplate jdbcTemplate,
            String batchId) {
        this.jdbcTemplate = jdbcTemplate;
        this.batchId = batchId;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        Map<String, Object> bounds = jdbcTemplate.queryForMap(
            """
            SELECT MIN(id) AS min_id, MAX(id) AS max_id
            FROM orders_staging WHERE batch_id = ?
            """,
            batchId
        );

        if (bounds.get("min_id") == null) {
            return Collections.emptyMap();
        }

        long minId = ((Number) bounds.get("min_id")).longValue();
        long maxId = ((Number) bounds.get("max_id")).longValue();

        return new IdRangePartitioner(
            minId, maxId, batchId
        ).partition(gridSize);
    }
}
```

`batchId` phải đại diện cho một tập dữ liệu đã chốt, và **cùng điều kiện lọc** phải xuất hiện trong query worker. Nếu adapter chỉ lấy min/max theo `batch_id` nhưng worker quên filter batch, range có thể lẫn dữ liệu của nhiều batch khác nhau.

**Giới hạn khi restart:** nếu upstream thêm/xóa/chuyển batch trong lúc chạy, MIN/MAX có thể thay đổi. Dù tên vẫn là `partition0`, nội dung khoảng có thể khác lần đầu. Khi hệ thống cần restart chính xác, phải giữ dataset và **kế hoạch phân chia** ổn định; có thể dùng staging bất biến, snapshot theo phiên bản, bảng lưu kế hoạch partition hoặc cơ chế metadata phù hợp. Không coi việc query lại MIN/MAX là luôn an toàn.

## 7. Gắn map với manager step và worker step

Trong Spring Batch 5.x, có thể cấu hình local partitioning bằng builder DSL như sau. Các bean `JobRepository`, `PlatformTransactionManager`, `ItemReader<OrderRow>` và `ItemWriter<OrderRow>` do ứng dụng cung cấp; example chỉ minh họa wiring.

```java
@Bean
public ThreadPoolTaskExecutor partitionExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(8);
    executor.setThreadNamePrefix("partition-worker-");
    executor.initialize();
    return executor;
}

@Bean
public Step ordersWorker(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderRow> ordersReader,
        ItemWriter<OrderRow> ordersWriter) {

    return new StepBuilder("ordersWorker", jobRepository)
        .<OrderRow, OrderRow>chunk(200, transactionManager)
        .reader(ordersReader)
        .writer(ordersWriter)
        .build();
}

@Bean
public Step ordersManager(
        JobRepository jobRepository,
        Step ordersWorker,
        Partitioner ordersPartitioner,
        @Qualifier("partitionExecutor") TaskExecutor executor) {

    return new StepBuilder("ordersManager", jobRepository)
        .partitioner("ordersWorker", ordersPartitioner)
        .step(ordersWorker)
        .gridSize(8)
        .taskExecutor(executor)
        .build();
}
```

`ordersPartitioner` là bean của `IdRangePartitioner` hoặc `DatabaseOrdersPartitioner`. Khi cần nhận `batchId` từ `JobParameters`, ứng dụng có thể dùng cấu hình scoped thích hợp; ví dụ:

```java
@Bean
@StepScope
public Partitioner ordersPartitioner(
        JdbcTemplate jdbcTemplate,
        @Value("#{jobParameters['batchId']}") String batchId) {
    return new DatabaseOrdersPartitioner(jdbcTemplate, batchId);
}
```

Ở đây, bean partitioner thuộc **manager step scope**; binding parameter diễn ra khi manager step thực thi. Cần kiểm tra cấu hình Spring Batch/Spring Boot cụ thể và bảo đảm định nghĩa step thực sự sử dụng scoped proxy tại runtime.

**Một partitioner tạo ra nhiều `StepExecution`, nhưng không tạo nhiều `JobInstance`.** Tất cả worker thuộc cùng một job execution, nhận kế hoạch riêng. Trong local partitioning, executor quản lý mức song song; các worker step nằm trong cùng JVM. Khi dùng remote partitioning, cần `PartitionHandler` tương ứng với broker/worker từ xa, nhưng hợp đồng `Map<String,ExecutionContext>` của partitioner vẫn giữ nguyên vai trò.

## 8. Worker đọc context bằng StepScope

Phần tử map không tự đi vào SQL. Worker cần đọc cận từ `stepExecutionContext` để tạo query, phân trang và checkpoint đúng vùng.

Ví dụ dùng `JdbcPagingItemReader` cho PostgreSQL:

```java
@Bean
@StepScope
public JdbcPagingItemReader<OrderRow> ordersReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['batchId']}") String batchId,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    PostgresPagingQueryProvider queryProvider =
        new PostgresPagingQueryProvider();

    queryProvider.setSelectClause("id, customer_id, total_amount");
    queryProvider.setFromClause("orders_staging");
    queryProvider.setWhereClause(
        "batch_id = :batchId AND id >= :minId AND id <= :maxId"
    );
    queryProvider.setSortKey("id");

    return new JdbcPagingItemReaderBuilder<OrderRow>()
        .name("ordersReader")
        .dataSource(dataSource)
        .queryProvider(queryProvider)
        .parameterValues(Map.of(
            "batchId", batchId,
            "minId", minId,
            "maxId", maxId
        ))
        .pageSize(200)
        .rowMapper((rs, index) -> new OrderRow(
            rs.getLong("id"),
            rs.getLong("customer_id"),
            rs.getBigDecimal("total_amount")
        ))
        .saveState(true)
        .build();
}
```

Với domain minh họa:

```java
public record OrderRow(
    long id,
    long customerId,
    BigDecimal totalAmount
) {}
```

Cơ chế binding:

```text
Partitioner:
    partition1 -> ExecutionContext{minId=250001, maxId=500000, batchId=B42}

Worker StepExecution "ordersWorker:partition1":
    stepExecutionContext['minId'] = 250001
    stepExecutionContext['maxId'] = 500000

@StepScope reader:
    SQL WHERE batch_id='B42'
          AND id >= 250001
          AND id <= 500000
```

Nếu thiếu `@StepScope`, bean reader singleton có thể được tạo trước khi có step context hoặc chia sẻ state không phù hợp. `@StepScope` chỉ bảo đảm scope theo **StepExecution**, không mặc định an toàn nếu bên trong cùng một partition lại dùng multi-threaded chunk processing. Với local partitioning, thường để mỗi worker step xử lý chunk tuần tự, cấp concurrency ở **manager step**.

`JdbcPagingItemReader` yêu cầu thứ tự phân trang ổn định; `id` làm sort key là hợp lý khi nó là khóa duy nhất, bất biến. Nếu reader có `saveState(true)`, checkpoint cần gắn với đúng worker step/context và tập dữ liệu cố định để restart đáng tin cậy.

## 9. Khi nào dùng JobParameters, JobExecutionContext, StepExecutionContext?

Ba nơi lưu thông tin này dễ bị nhầm:

| Nguồn | Phạm vi | Ví dụ | Cách binding thông dụng |
| --- | --- | --- | --- |
| `jobParameters` | Đầu vào của lần chạy logic; identifying fields quyết định JobInstance. | `batchId`, ngày xử lý, source ID. | `@Value("#{jobParameters['batchId']}")` |
| `jobExecutionContext` | Context gắn với JobExecution. | Metadata/snapshot chung cho job do bước trước tạo. | `@Value("#{jobExecutionContext['snapshotId']}")` |
| `stepExecutionContext` | Context gắn với một StepExecution; trong partitioning chứa thông số range riêng. | `minId`, `maxId`, reader checkpoint. | `@Value("#{stepExecutionContext['minId']}")` |

Nếu `batchId` xác định dataset, nó thường nên là **identifying job parameter**. Partitioner có thể đọc parameter này rồi chép vào từng partition context như một thông số đơn giản để worker đọc nhất quán. Đừng cố biến `minId`/`maxId` thành **job parameters chung cho toàn job** khi mỗi partition cần giá trị khác nhau.

Một `ExecutionContext` của worker không tự lan truyền sang context của job hay context của partition khác. Nếu cần tổng hợp kết quả sau khi các worker hoàn tất, dùng cơ chế aggregation/listener phù hợp, đọc `StepExecution` qua framework hoặc lưu kết quả trong kho dữ liệu được thiết kế cho mục đích đó. Không coi context như một shared-memory map cho nhiều thread cùng cập nhật.

## 10. Các lỗi thường gặp khi thiết kế Map

### 10.1. Hai partition có cùng tên

```java
partitions.put("partition", firstContext);
partitions.put("partition", secondContext);
```

`Map.put` lần thứ hai thay value lần đầu. Kết quả thực tế chỉ còn **một** partition; một vùng dữ liệu bị mất khỏi kế hoạch.

Cách phòng tránh: đặt tên dựa trên index hoặc khóa vùng duy nhất, kiểm tra `partitions.put(name, value) == null` nếu muốn fail fast khi trùng tên.

### 10.2. Hai partition có cùng range

Tên khác nhau nhưng `ExecutionContext` chứa `[1,100]` cho cả hai worker. Map vẫn hợp lệ về key nhưng sai dữ liệu: cả hai cùng đọc một vùng.

Cách phòng tránh: kiểm tra tính không giao nhau và độ bao phủ của các khoảng bằng unit test/property test và đối soát dữ liệu.

### 10.3. Context dùng sai kiểu

Partioner ghi `context.putString("minId", "100")` nhưng worker khai báo `Long minId` với binding không có chuyển đổi chắc chắn, hoặc code gọi `getLong("minId")` trực tiếp. Có thể gây lỗi binding/cast khi chạy.

Cách phòng tránh: thống nhất schema context: `putLong/getLong`, `putString/getString`, tên key và ý nghĩa biên. Kiểm thử cả serialization/readback.

### 10.4. Không lưu batchId hoặc bỏ mất điều kiện tenant

Range ID được tính từ `batchId=B42` nhưng worker truy vấn tất cả bản ghi trong khoảng, làm lẫn dữ liệu của batch khác.

Cách phòng tránh: mọi predicate lựa chọn nguồn phải nhất quán giữa truy vấn lập kế hoạch và truy vấn worker; kiểm tra cùng `batchId`/`tenantId`/snapshot.

### 10.5. Dùng context như vùng lưu kết quả khổng lồ

Đưa cả danh sách hàng trăm nghìn bản ghi vào context tạo metadata rất lớn, serializer có thể thất bại và restart khó quản lý.

Cách phòng tránh: lưu **locator** (ID range, object key, shard ID, filter) trong context; đọc dữ liệu thật từ nguồn phù hợp.

### 10.6. Thay đổi gridSize khi restart mà không giữ kế hoạch

Lần đầu tên `partition1` tương ứng `[101,200]`, lần sau vì chia lại mà tên này đại diện `[251,375]`. Metadata và checkpoint có nguy cơ bị ghép với vùng khác.

Cách phòng tránh: giữ kế hoạch ổn định cho cùng JobInstance, định nghĩa rõ version và kiểm tra cách framework sử dụng các StepExecution cũ trên restart. Chỉ tái cân bằng khi tạo instance mới hoặc có quy trình migration được kiểm chứng.

### 10.7. Dùng key ngẫu nhiên để “cân bằng tải”

Tên `random-...` không giúp chia công việc tốt hơn; nó chỉ làm mất tính ổn định và khó quan sát khi restart.

Cách phòng tránh: dùng tên xác định, tăng số vùng nhỏ hoặc áp dụng thuật toán cân bằng dữ liệu dựa trên số record/chi phí dự đoán.

## 11. Kết quả Map ảnh hưởng thế nào tới retry và restart?

Spring Batch lưu trạng thái job và step trong `JobRepository`. Khi worker nhận partition, `ExecutionContext` ban đầu mang ranh giới và các tham số; trong khi worker chạy, reader/writer có thể cập nhật checkpoint vào context step. Các trạng thái và context được lưu theo cơ chế transaction/checkpoint của framework.

Ví dụ:

```text
JobInstance: importOrders(batchId=B42)

Lần chạy #1:
  ordersWorker:partition0  [1..100]     COMPLETED
  ordersWorker:partition1  [101..200]   FAILED sau vài chunk
  ordersWorker:partition2  [201..300]   COMPLETED

Lần restart:
  partition0 / partition2: thường được bỏ qua vì đã COMPLETED
  partition1: tiếp tục theo checkpoint đã lưu nếu đủ điều kiện
```

**Mấu chốt:** “tên partition” có vai trò nhận diện phần việc. Khi một tên cũ được tái sử dụng, nó phải tiếp tục có **cùng ý nghĩa nghiệp vụ** và ranh giới dữ liệu với lần chạy trước. Nếu dataset thay đổi hoặc partitioner tính lại biên khác, việc khôi phục có thể không tương ứng với checkpoint cũ.

Những yêu cầu cần kiểm tra:

1. **Tập dữ liệu bất biến trong vòng đời instance.** Nếu upstream có thể thêm ID thấp vào cùng batch, hoặc xóa/chuyển record khỏi filter, lần đọc mới có thể không giống lần đầu.
2. **Map và tên ổn định.** Không đổi ngẫu nhiên số/tên/định nghĩa partition trong một lần restart.
3. **Reader lưu state đúng.** `saveState(true)` hoặc cơ chế tương đương phải tương thích với scope, dữ liệu và paging.
4. **Writer idempotent.** Side effect ngoài transaction có thể đã xảy ra trước khi chunk lỗi; retry có thể gọi lại.
5. **Step completed handling đúng.** Các step/partition đã `COMPLETED` thường không chạy lại trừ khi cấu hình cho phép. Đừng giả định restart luôn chạy toàn bộ dữ liệu từ đầu hoặc luôn tiếp tục đúng item kế tiếp.
6. **PartitionNameProvider nếu dùng phải nhất quán.** Khi dùng cơ chế chỉ liệt kê tên partition để tối ưu restart, danh sách tên phải phù hợp với tên do `partition(gridSize)` trả về.

### Ví dụ writer chống ghi trùng

Với PostgreSQL, một cách ghi dữ liệu đích theo khóa duy nhất:

```sql
INSERT INTO orders_result(id, batch_id, normalized_amount)
VALUES (:id, :batchId, :amount)
ON CONFLICT (id)
DO UPDATE SET
    batch_id = EXCLUDED.batch_id,
    normalized_amount = EXCLUDED.normalized_amount;
```

Upsert giúp các thao tác lặp theo ID ít nguy cơ sinh duplicate, nhưng không giải quyết mọi tình huống: kết quả phải xác định với cùng input; nếu bản ghi có version/độ ưu tiên khác nhau, cần quy tắc cập nhật và khóa nghiệp vụ tương ứng.

### Stop không rollback toàn bộ partition khác

Nếu một worker lỗi trong khi worker khác đã commit, các transaction đã commit **không tự rollback**. Khi restart, framework dùng metadata và checkpoint của từng phần; phép đối soát sau cùng mới xác nhận mọi bản ghi trong batch đều được xử lý theo yêu cầu.

## 12. Quan hệ với parallel steps, multi-threaded step và remote partitioning

Từ cùng một `Map<String, ExecutionContext>`, có thể hình dung bốn cách cấp mức đồng thời:

| Mô hình | Đơn vị song song | Có dùng `Partitioner` map không? | Lưu ý |
| --- | --- | --- | --- |
| Multi-threaded step | Các chunk của cùng một step. | Không bắt buộc. | Dễ chia sẻ reader/state; cần thread safety. |
| Parallel flows/steps | Các flow hoặc step độc lập. | Không bắt buộc. | Quan hệ phụ thuộc và tài nguyên giữa flow. |
| Local partitioning | Các `StepExecution` partition trong cùng JVM. | **Có.** | `TaskExecutor` giới hạn số worker đồng thời. |
| Remote partitioning | Các `StepExecution` trên process/JVM khác. | **Có.** | Cần transport, worker deployment, retry/dedup và giám sát từ xa. |

Trong local partitioning, cùng một worker step definition được thực thi nhiều lần với context khác nhau; với `@StepScope`, mỗi StepExecution có thể có reader riêng. Đây thường là lựa chọn dễ quản lý state hơn việc gắn executor vào một step dùng chung một mutable reader.

Với remote partitioning, manager vẫn tạo các partition theo map nhưng phải đưa phần việc tới worker qua middleware hoặc handler tương ứng. Context cần **serialize được trong hệ thống thực tế**; đừng đặt object gắn với process, local file handle hay resource chỉ tồn tại tại manager vào đó. Nếu path file được gửi tới remote worker, worker phải có quyền truy cập path hoặc object storage tương ứng.

`gridSize` là gợi ý partition count, còn **executor pool/worker capacity** quyết định mức thực thi. Tăng gridSize có thể giảm mất cân bằng khi nhiều vùng nhỏ, nhưng cũng làm tăng số StepExecution, metadata và scheduling overhead.

## 13. Đánh giá cân bằng tải của Map

Một map đúng về mặt biên **chưa chắc cân bằng về workload**. Ví dụ ID thật gồm `10,11,50,51,52,1000,1001,1002`. Chia đều miền `[10,1002]` thành ba khoảng độ rộng 331:

| Partition | Range | Số record thực |
| --- | --- | ---: |
| partition0 | 10–340 | 5 |
| partition1 | 341–671 | 0 |
| partition2 | 672–1002 | 3 |

`partition1` rỗng, một worker có thể hoàn tất ngay, còn worker khác kéo dài. Nếu record có chi phí xử lý khác nhau (ví dụ gọi HTTP), lệch runtime càng lớn.

Các chiến lược thay thế:

- Chia theo **phân vị ID** hoặc ước lượng count để mỗi range có số record gần nhau.
- Tạo nhiều range nhỏ hơn số worker, để worker lấy các partition còn lại khi hoàn thành vùng trước.
- Chia theo **ngày, tenant, shard hoặc nhóm nghiệp vụ** nếu dữ liệu có locality và tránh xung đột ghi tốt hơn.
- Dựa trên telemetry lịch sử để ước lượng chi phí từng vùng, rồi tạo map theo ngân sách xử lý.

Ví dụ muốn 16 partition trên pool 4 thread là hợp lý khi mỗi partition có chi phí quản lý thấp và giúp giảm skew. Nhưng nếu 10.000 partition chỉ có vài record, việc tạo StepExecution/metadata nhiều lần có thể khiến throughput giảm.

**Đừng tối ưu bằng số thread trước khi đo.** Thu thập thời gian mỗi partition, số record, thời gian đọc/ghi, DB connection wait, lock wait, CPU, heap, queue depth, retry và tiến độ thực.

## 14. Kiểm thử Map trước khi chạy production

### Kiểm thử cấu trúc và bất biến

Với `IdRangePartitioner(101,125,"B42")` và `gridSize=4`, dự kiến:

```text
partition0: [101,107]
partition1: [108,113]
partition2: [114,119]
partition3: [120,125]
```

Các assertion nên có:

1. Map có 4 key, mỗi key không null và mỗi value là một instance context riêng.
2. Mỗi context chứa `batchId` đúng và hai cận có kiểu `long`.
3. Mỗi `minId <= maxId`, các range liền nhau, tổng độ rộng bằng 25.
4. Gọi lại `partition(4)` với input không đổi phải cho **tên và giá trị tương đương**.
5. Dữ liệu đã đọc bằng toàn bộ reader partition không thiếu/trùng ID thực tế.

Pseudo-test JUnit:

```java
@Test
void splitsRangesWithoutOverlap() {
    Map<String, ExecutionContext> parts =
        new IdRangePartitioner(101L, 125L, "B42").partition(4);

    assertEquals(4, parts.size());
    assertEquals(
        101L, parts.get("partition0").getLong("minId")
    );
    assertEquals(
        107L, parts.get("partition0").getLong("maxId")
    );
    assertEquals(
        108L, parts.get("partition1").getLong("minId")
    );
    assertEquals(
        125L, parts.get("partition3").getLong("maxId")
    );
    assertEquals(
        "B42", parts.get("partition2").getString("batchId")
    );
    assertNotSame(parts.get("partition0"), parts.get("partition1"));
}
```

### Trường hợp biên cần kiểm tra

| Input | Kỳ vọng |
| --- | --- |
| `minId=7, maxId=7, gridSize=8` | Một partition duy nhất chứa `[7,7]`. |
| `minId=10, maxId=9, gridSize=4` | Map rỗng theo quy ước của ví dụ. |
| `minId=1, maxId=2, gridSize=10` | Hai partition, không tạo tám range không hợp lệ. |
| `gridSize=0` | Báo lỗi đầu vào. |
| `minId=Long.MIN_VALUE, maxId=Long.MAX_VALUE` | Không overflow lúc tính biên trung gian. |
| Nguồn có ID thưa, record đã xóa | Range bao phủ miền ID; reader chỉ trả record thực có trong DB. |
| Batch có tenant và batchId khác nhau | Reader không đọc lẫn dữ liệu giữa các nhóm. |
| Restart sau một số worker `COMPLETED` | Không mất/trùng record, tên và context dùng cho resume ổn định. |

### Đối soát dữ liệu bằng tập khóa

`COUNT(*)` của đầu vào và đầu ra bằng nhau **chưa đủ**: vẫn có thể hai tập ID khác nhau nhưng cùng số lượng. Với yêu cầu đúng một lần theo business key, hãy so sánh hai tập ID và kiểm tra unique constraint, kiểm tra lỗi retry/restart:

```sql
-- ID đầu vào đã chốt nhưng chưa có ở đích
SELECT id FROM orders_staging WHERE batch_id = :batchId
EXCEPT
SELECT id FROM orders_result WHERE batch_id = :batchId;

-- ID đích thuộc batch nhưng không có trong đầu vào
SELECT id FROM orders_result WHERE batch_id = :batchId
EXCEPT
SELECT id FROM orders_staging WHERE batch_id = :batchId;
```

Hai tập chênh lệch phải rỗng nếu nghiệp vụ yêu cầu mỗi ID đầu vào có một bản ghi kết quả tương ứng. Khi có filter hoặc skip hợp lệ, cần xác định tập kỳ vọng theo chính sách nghiệp vụ trước khi đối soát.

## 15. Vận hành và giám sát Map partition

Một dashboard hữu ích cần hiển thị **tên partition** cùng context định tuyến (nếu không chứa thông tin nhạy cảm), trạng thái và tiến độ:

| Trường/metric | Công dụng |
| --- | --- |
| `jobInstanceId`, `jobExecutionId` | Phân biệt restart và job instance mới. |
| `partitionName`, `workerStepExecutionId` | Liên hệ metadata, log và worker cụ thể. |
| `batchId`, `minId`, `maxId` | Điều tra vùng dữ liệu đang hoặc đã xử lý. |
| `readCount`, `writeCount`, `skipCount` | Kiểm tra tiến độ và số liệu theo từng vùng. |
| `BatchStatus`, `ExitStatus`, lỗi chi tiết | Nhận diện partition bị stop/failed/completed. |
| Thời gian xử lý partition | Phát hiện skew và worker bị kẹt. |
| Active thread, DB connection wait, lock wait | Xác định giới hạn tài nguyên thực tế. |
| Retry, restart count, checkpoint | Đánh giá tính ổn định và khả năng phục hồi. |

Không giả định một partition `COMPLETED` đồng nghĩa job hoàn tất. Manager có thể còn worker khác đang chạy hoặc gặp lỗi. Với workload lớn, phân biệt **status tổng thể** và **status từng worker** rất quan trọng để không restart/stop sai phần việc.

Khi một partition bị treo, dùng tên `ordersWorker:partitionN` để tìm log, range ID, những transaction đã commit, query đang chạy và trạng thái reader. Đừng tự thay `ExecutionContext` trong bảng metadata để “đẩy” partition qua một range mới nếu chưa có quy trình migration và đối soát dữ liệu chặt chẽ.

## 16. Bài thực hành tổng hợp

**Bài 1 — Thiết kế map.** Một tập đơn hàng có ID `[100,112]`; `gridSize=4`. Hãy viết map với tên `partition0...partition3` và range đúng. Đáp án: `[100,103]`, `[104,106]`, `[107,109]`, `[110,112]`.

**Bài 2 — Phát hiện bug.** Một vòng lặp tạo đúng tên nhưng tái sử dụng cùng một `ExecutionContext`. Dự đoán giá trị worker đọc được và giải thích vì sao có thể xảy ra duplicate hoặc mất record.

**Bài 3 — Phân biệt nguồn dữ liệu.** `batchId` đến từ `JobParameters`, còn `minId/maxId` đến từ `stepExecutionContext`. Viết SpEL phù hợp cho reader và giải thích vì sao không lưu tất cả cận dưới dạng job parameters.

**Bài 4 — Lệch tải.** Bốn partition có thời gian `[12, 10, 11, 65]` phút, pool 4 thread. Nêu cách điều chỉnh kế hoạch map để tránh một vùng đơn lẻ quyết định runtime toàn job. Xem xét chi phí tạo thêm partition.

**Bài 5 — Restart.** `partition0` và `partition2` hoàn tất, `partition1` thất bại sau khi commit vài chunk. Viết quy trình kiểm tra tên, context, checkpoint, writer idempotency và đối soát ID khi chạy lại cùng `JobInstance`.

**Bài 6 — Remote.** Một context chứa path `C:\local\orders.csv` của manager. Giải thích vì sao remote worker chạy trên host khác có thể không đọc được, và đề xuất sử dụng URI object storage hoặc shared storage với quyền truy cập được kiểm soát.

## 17. Checklist triển khai

- [ ] `Partitioner` trả về `Map<String,ExecutionContext>` có tên duy nhất và context không null.
- [ ] Mỗi partition có context riêng; không tái sử dụng cùng mutable object.
- [ ] Schema key/value rõ ràng, dùng kiểu đơn giản có thể serialize và readback.
- [ ] Map bao phủ tập dữ liệu đã chọn, không overlap, không bỏ sót; điều kiện filter trong worker khớp nguồn.
- [ ] Tên partition và ý nghĩa của chúng ổn định giữa các lần restart của cùng JobInstance.
- [ ] `gridSize` và concurrency của executor được xem là hai tham số riêng.
- [ ] Reader dùng `@StepScope` để nhận `stepExecutionContext`; không chia sẻ state đọc thiếu an toàn.
- [ ] Writer và side effect có idempotency/dedup khi retry hoặc restart.
- [ ] Dữ liệu đầu vào và kế hoạch phân vùng có snapshot/version ổn định cho restart.
- [ ] Đã thử batch rỗng, một ID, ID thưa, biên kiểu `BIGINT` và lỗi giữa chừng.
- [ ] Đã đo thời gian mỗi partition, skew, CPU, DB connection, lock, retry và tổng throughput.
- [ ] Đã đối soát tập khóa nghiệp vụ sau chạy thường và restart.

## 18. Ghi nhớ

Trong Spring Batch, `Partitioner.partition(gridSize)` tạo **bản đồ tên partition → ExecutionContext**. Tên giúp framework và người vận hành nhận diện phần việc; context mang ranh giới và tham số để worker chỉ xử lý vùng được giao. Manager step chuyển chúng thành các worker `StepExecution` độc lập, sau đó handler/executor quyết định cách thực thi.

Một map đúng không chỉ có đủ số entry. Nó cần **tên ổn định, context tách biệt, phạm vi dữ liệu không giao nhau, khả năng lưu/khôi phục và sự phù hợp với tài nguyên thực tế**. Khi kết hợp những yêu cầu đó với reader theo step scope, writer idempotent, kiểm thử lỗi và metric theo partition, cơ chế này mới phát huy lợi ích khi mở rộng workload dữ liệu lớn.
