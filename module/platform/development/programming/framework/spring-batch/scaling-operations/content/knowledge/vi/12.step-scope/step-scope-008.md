# Tránh dùng singleton mutable state khi mở rộng Spring Batch

## 1. Vấn đề xuất hiện khi một job có nhiều worker

Một job Spring Batch chạy tuần tự trên một thread thường che giấu được nhiều lỗi thiết kế. Ví dụ, một `ItemProcessor` singleton có field `currentCustomerId` và `processedCount` có thể hoạt động “có vẻ đúng” khi mỗi lần chỉ xử lý một item. Nhưng khi bật multi-threaded step, chạy parallel steps hoặc chia thành nhiều partition, **cùng một object có thể được nhiều execution hoặc nhiều thread sử dụng đồng thời**.

Lúc đó, các field có thể bị ghi đè giữa chừng, gây:

- Gán nhầm dữ liệu của tenant/partition này sang item của tenant/partition khác.
- Đếm thiếu hoặc đếm trùng do thao tác `count++` không nguyên tử.
- Làm hỏng cursor, buffer hoặc trạng thái reader/writer.
- Đọc lại sai vị trí sau retry/restart, ngay cả khi job kết thúc với trạng thái `COMPLETED`.
- Phát sinh lỗi không ổn định: chạy một worker thì đúng, tăng số worker thì sai.

Đây là bài **“Tránh dùng singleton mutable state”**, thuộc chương **Step scope** của module `SPRING_BATCH_SCALING_OPERATIONS`. Module tập trung mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và xử lý phân tán, đồng thời đo bottleneck, bảo đảm thread safety, retry/restart và chọn kiến trúc dựa trên tài nguyên thực tế.

Sau bài này, bạn sẽ có thể:

1. Phân biệt **singleton**, **stateless**, **immutable** và **thread-safe** — bốn khái niệm không đồng nghĩa.
2. Nhận biết mutable state nguy hiểm trong reader, processor, writer, listener và client dùng chung.
3. Chọn giữa **singleton stateless**, **`@StepScope`** và cơ chế đồng bộ khi thực sự cần.
4. Giải thích giới hạn của `@StepScope` trong một **multi-threaded step** có nhiều chunk đồng thời.
5. Thiết kế partition có state tách biệt và checkpoint/restart đáng tin cậy.
6. Đo độ đúng và hiệu năng trước/sau khi tăng concurrency.

Ví dụ sử dụng **Java 17+, Spring Batch 5.x và Spring Boot 3.x**. Không phải mọi client hoặc reader đều thread-safe; phải xem hợp đồng của từng class và kiểm thử đúng mô hình concurrency của ứng dụng.

## 2. Bean singleton được chia sẻ như thế nào?

Spring quản lý bean dạng **singleton theo `ApplicationContext`** nếu không chỉ định scope khác. Khi hai `StepExecution` cùng tham chiếu một bean singleton, chúng có thể cùng gọi method của **một object**. Nếu object giữ state thay đổi theo item hoặc partition, state đó dễ bị xen kẽ.

~~~mermaid
flowchart TB
    C[Spring ApplicationContext] --> P[Singleton OrderProcessor]
    S[Batch Job] --> M[Manager]
    M --> A[StepExecution partition-0]
    M --> B[StepExecution partition-1]
    A -->|Thread A: process| P
    B -->|Thread B: process| P
    P --> F[Mutable field: currentTenant / count]
    F --> X[Race condition / cross-partition contamination]
~~~

Nếu chuyển một bean có trạng thái **theo partition** sang `@StepScope`, mỗi `StepExecution` nhận một **target instance riêng**:

~~~mermaid
flowchart TB
    SP[Step-scoped proxy] --> A[StepExecution partition-0]
    SP --> B[StepExecution partition-1]
    A --> PA[Reader target A: cursor/checkpoint A]
    B --> PB[Reader target B: cursor/checkpoint B]
    PA --> DA[ExecutionContext A]
    PB --> DB[ExecutionContext B]
~~~

Sơ đồ thứ hai mô tả cách ly **giữa các `StepExecution`**. Nếu **một `StepExecution` dùng nhiều thread**, tất cả thread của execution đó vẫn có thể dùng cùng target scoped bean. Vì vậy, `@StepScope` **không tự bảo đảm** an toàn cho một reader có cursor khi chạy multi-threaded step.

### Bốn khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Singleton** | Một bean instance trong một Spring container (thường là scope mặc định) | `@Component` hoặc `@Bean` không khai scope |
| **Mutable** | Object có field hoặc dữ liệu nội bộ thay đổi trong vòng đời | `counter++`, `HashMap.put`, `ArrayList.add`, cursor position |
| **Stateless** | Kết quả method không phụ thuộc trạng thái mutable giữa các lời gọi | Processor chuyển `Order` thành DTO mới bằng tham số đầu vào |
| **Thread-safe** | Đúng khi nhiều thread truy cập đồng thời theo contract | Một client đã được tài liệu xác nhận an toàn, hoặc object được đồng bộ đúng |

**Singleton không đồng nghĩa nguy hiểm.** Một `ItemProcessor` singleton **stateless**, một service immutable hoặc connection pool được thiết kế thread-safe thường hoàn toàn phù hợp. Điều cần tránh là **đưa trạng thái thay đổi theo item, step hoặc partition vào một singleton không có cơ chế cô lập/đồng bộ phù hợp**.

## 3. Anti-pattern: processor giữ trạng thái của item trước

Xem code sau. Nó có hai field mutable được chia sẻ trên mọi lời gọi `process`:

~~~java
import org.springframework.batch.item.ItemProcessor;
import org.springframework.stereotype.Component;

record Order(long id, String tenantId, long amount) {}
record Receipt(long orderId, String tenantId, long amount) {}

@Component // Singleton theo mặc định
public class UnsafeOrderProcessor implements ItemProcessor<Order, Receipt> {
    private String currentTenant;
    private long processedCount;

    @Override
    public Receipt process(Order item) {
        currentTenant = item.tenantId();
        processedCount++; // Không nguyên tử
        return new Receipt(item.id(), currentTenant, item.amount());
    }

    public long processedCount() {
        return processedCount;
    }
}
~~~

Với thread A xử lý đơn hàng tenant `ALPHA` và thread B xử lý đơn hàng tenant `BETA`:

~~~text
Thread A                          Thread B
-------------------------------   -------------------------------
currentTenant = "ALPHA"
                                  currentTenant = "BETA"
return Receipt(..., currentTenant)
=> Có thể ghi nhầm "BETA" cho item của A
~~~

Ngay cả khi `Receipt` là record immutable, **giá trị đã được lấy từ shared mutable field có thể sai**. `processedCount++` cũng có thể mất lượt tăng vì phép đọc–cộng–ghi không được đồng bộ.

Lỗi có thể hiếm trong unit test tuần tự và xuất hiện nhiều hơn khi CPU tải cao, thread scheduling thay đổi hoặc worker được scale. Không được dựa vào `volatile` để sửa `count++`: `volatile` hỗ trợ visibility, **không biến thao tác increment thành atomic**.

### Những vị trí dễ có mutable singleton khác

| Component | Mutable state đáng ngờ | Hậu quả khi chia sẻ không đúng |
|---|---|---|
| `ItemReader` | Cursor, current index, iterator, buffer, open file handle | Trùng/thiếu item, checkpoint không khớp |
| `ItemProcessor` | `currentItem`, `currentTenant`, cache `HashMap` mutable | Sai dữ liệu, rò rỉ ngữ cảnh giữa partition |
| `ItemWriter` | `List` đệm, `StringBuilder`, transaction/session lưu ở field | Ghi thiếu/trùng hoặc ghi sang đích sai |
| `StepExecutionListener` | Field `currentStepExecution`, tổng đếm toàn job | Trộn thông tin của nhiều execution |
| `Tasklet` | Field `lastProcessedId`, trạng thái vòng lặp | Restart sai hoặc race |
| Custom service | `SimpleDateFormat`, random generator dùng sai, mutable credentials/context | Sai format, lỗi cạnh tranh hoặc rò dữ liệu |
| `ExecutionContext` cache tự tạo | Static `Map` gắn execution ID vào state | Leak, mất state khi restart JVM, lỗi giữa process |

Đừng đánh giá an toàn chỉ dựa trên annotation `@Component`, `@Service` hoặc chữ “service”. Hãy nhìn **field thực tế** và cách object được gọi đồng thời.

## 4. Thiết kế an toàn nhất: singleton stateless, dữ liệu đi qua tham số

Cách sửa anti-pattern là bỏ những field không cần thiết và tạo kết quả chỉ từ item đầu vào:

~~~java
import org.springframework.batch.item.ItemProcessor;
import org.springframework.stereotype.Component;

@Component
public final class StatelessOrderProcessor
        implements ItemProcessor<Order, Receipt> {

    @Override
    public Receipt process(Order order) {
        // Không gán currentTenant hoặc currentItem vào instance field.
        return new Receipt(
                order.id(),
                order.tenantId(),
                order.amount()
        );
    }
}
~~~

`Order` và `Receipt` ở đây là record của ví dụ trước, có các field final. Một processor như vậy có thể được dùng chung an toàn **nếu các dependency mà nó gọi cũng an toàn và method không tạo side effect cạnh tranh**.

**Quy tắc:** dữ liệu của item nên nằm trong **local variable, method parameter hoặc DTO immutable**. Trạng thái riêng của partition nằm trong `ExecutionContext`/bean scope đúng phạm vi. Cấu hình tĩnh nằm trong immutable field, ví dụ:

~~~java
public final class VatProcessor implements ItemProcessor<Order, Receipt> {
    private final long vatRateBasisPoints;

    public VatProcessor(long vatRateBasisPoints) {
        this.vatRateBasisPoints = vatRateBasisPoints;
    }

    @Override
    public Receipt process(Order order) {
        long fee = Math.multiplyExact(
                order.amount(), vatRateBasisPoints) / 10_000L;
        return new Receipt(
                order.id(),
                order.tenantId(),
                Math.addExact(order.amount(), fee)
        );
    }
}
~~~

`vatRateBasisPoints` là **immutable configuration**, không phải mutable per-item state. Mã dùng số nguyên để tránh nhập nhằng floating point trong ví dụ tính phí; ứng dụng thực tế cần quy tắc làm tròn và kiểu tiền tệ phù hợp.

### Vậy đếm số item thế nào?

Không cần tự đếm bằng singleton `processedCount` chỉ để theo dõi throughput. Spring Batch đã có metric của `StepExecution`:

- `readCount`: số item được đọc theo quy ước của step.
- `writeCount`: số item đã ghi theo quy ước của step.
- `filterCount`, `readSkipCount`, `processSkipCount`, `writeSkipCount`: hỗ trợ phân tích lọc/skip.
- `commitCount`, `rollbackCount`: gợi ý chi phí giao dịch và retry.

Với partitioning, số đếm thuộc **mỗi `StepExecution`**; dùng hệ thống quan sát/tổng hợp để báo cáo toàn job. Nếu cần chỉ số tùy chỉnh, sử dụng Micrometer counter/timer với cardinality được kiểm soát và xác định rõ semantic khi retry/rollback.

## 5. Khi bean cần state: dùng @StepScope với đúng ranh giới

Một reader thường phải giữ cursor, vị trí đọc và tài nguyên I/O. Điều này hợp lý **nếu state ấy thuộc đúng một `StepExecution`**. Với partitioning, Spring Batch hỗ trợ `@StepScope` để tạo target reader riêng cho từng partition.

### 5.1. Partitioner ghi miền dữ liệu vào ExecutionContext

Giả sử bảng `orders` dùng khóa `id` ổn định. Manager lập các vùng ID đóng, không giao nhau:

~~~text
partition0 -> minId=1,   maxId=250
partition1 -> minId=251, maxId=500
partition2 -> minId=501, maxId=750
partition3 -> minId=751, maxId=1000
~~~

Mỗi dòng trên tương ứng với một `StepExecutionContext` riêng. Giá trị range cần được chốt cho cùng job instance và giữ ổn định khi restart.

Ví dụ `Partitioner` đơn giản:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;

public final class OrderRangePartitioner implements Partitioner {
    private final long firstId;
    private final long lastId;

    public OrderRangePartitioner(long firstId, long lastId) {
        if (firstId > lastId) {
            throw new IllegalArgumentException("Empty ID range");
        }
        this.firstId = firstId;
        this.lastId = lastId;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize <= 0) {
            throw new IllegalArgumentException("gridSize must be positive");
        }
        long total = Math.addExact(
                Math.subtractExact(lastId, firstId), 1L);
        int partitions = (int) Math.min((long) gridSize, total);
        long base = total / partitions;
        long remainder = total % partitions;
        long start = firstId;

        Map<String, ExecutionContext> result = new LinkedHashMap<>();
        for (int i = 0; i < partitions; i++) {
            long width = base + (i < remainder ? 1L : 0L);
            long end = Math.addExact(start, width - 1);
            ExecutionContext context = new ExecutionContext();
            context.putLong("minId", start);
            context.putLong("maxId", end);
            result.put("partition" + i, context);
            if (i + 1 < partitions) {
                start = Math.addExact(end, 1L);
            }
        }
        return result;
    }
}
~~~

`OrderRangePartitioner` trong ví dụ **không có state thay đổi trong lúc partition(...) chạy**: `firstId` và `lastId` là final, `start` và `result` là biến local. Đây là thiết kế an toàn hơn một singleton chứa field mutable `currentRange` được ghi khi mọi lần gọi tạo partition.

### 5.2. Reader theo StepExecution, không chia sẻ cursor

Ví dụ reader Spring Batch 5.x lấy range qua SpEL:

~~~java
import javax.sql.DataSource;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class WorkerReaderConfiguration {

    @Bean
    @StepScope
    public JdbcCursorItemReader<Order> ordersReader(
            DataSource dataSource,
            @Value("#{stepExecutionContext['minId']}") Long minId,
            @Value("#{stepExecutionContext['maxId']}") Long maxId) {

        if (minId == null || maxId == null || minId > maxId) {
            throw new IllegalArgumentException(
                    "Missing or invalid partition range");
        }

        return new JdbcCursorItemReaderBuilder<Order>()
                .name("ordersRangeReader")
                .dataSource(dataSource)
                .sql("""
                    SELECT id, tenant_id, amount
                    FROM orders
                    WHERE id >= ? AND id <= ?
                    ORDER BY id
                    """)
                .preparedStatementSetter(ps -> {
                    ps.setLong(1, minId);
                    ps.setLong(2, maxId);
                })
                .rowMapper((rs, rowNum) -> new Order(
                        rs.getLong("id"),
                        rs.getString("tenant_id"),
                        rs.getLong("amount")
                ))
                .saveState(true)
                .build();
    }
}
~~~

Giả định bảng nguồn có các cột `id BIGINT`, `tenant_id` và `amount BIGINT`. `Order` là record immutable từ ví dụ processor trước.

Các điểm cần lưu ý:

1. `@StepScope` trì hoãn tạo target reader đến khi có `StepExecution`. Khi cấu hình step, Spring inject một **proxy**.
2. Mỗi partition late bind hai giá trị `minId`/`maxId` từ **`stepExecutionContext` riêng**.
3. Cursor và trạng thái `ItemStream` của mỗi target reader được cô lập theo `StepExecution`.
4. Method `@Bean` trả về **kiểu concrete `JdbcCursorItemReader`**, để lifecycle `open/update/close` được expose qua proxy.
5. `.name("ordersRangeReader")` tạo tên ổn định cho key checkpoint. Nhiều partition dùng cùng tên reader vẫn an toàn nếu context của chúng tách riêng.
6. `ORDER BY id` giúp thứ tự đọc ổn định. Không được tự thay cutoff/range của một partition khi restart.

**Đừng dùng `@StepScope` làm cái cớ bỏ qua giới hạn JDBC pool.** Nếu một pod chạy 16 partition đồng thời, có thể xuất hiện nhiều cursor và transaction connection cùng lúc. Cần tính giới hạn trên mỗi pod và toàn cụm dựa trên hoạt động thực tế.

### 5.3. Writer stateless và thao tác idempotent

Một writer thường có thể là singleton **nếu thư viện bảo đảm cách dùng đồng thời và cấu hình đã cố định sau khi khởi tạo**. `JdbcBatchItemWriter` không cần lưu `currentItem` hoặc một `List` mutable ở bean ứng dụng.

Ví dụ ghi kết quả bằng PostgreSQL:

~~~sql
CREATE TABLE order_receipts (
    order_id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    total_amount BIGINT NOT NULL
);
~~~

~~~java
import javax.sql.DataSource;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

@Bean
public JdbcBatchItemWriter<Receipt> receiptWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<Receipt>()
            .dataSource(dataSource)
            .sql("""
                INSERT INTO order_receipts
                    (order_id, tenant_id, total_amount)
                VALUES (:orderId, :tenantId, :totalAmount)
                ON CONFLICT (order_id)
                DO UPDATE SET
                    tenant_id = EXCLUDED.tenant_id,
                    total_amount = EXCLUDED.total_amount
                """)
            .itemSqlParameterSourceProvider(receipt ->
                    new MapSqlParameterSource()
                            .addValue("orderId", receipt.orderId())
                            .addValue("tenantId", receipt.tenantId())
                            .addValue("totalAmount", receipt.amount()))
            .build();
}
~~~

Ở ví dụ, `Receipt` là record immutable ở phần 3. Upsert theo `order_id` cho kết quả lặp lại nhất quán với cùng đầu vào; cần cân nhắc **last-write-wins**, versioning và thứ tự sự kiện nếu nghiệp vụ cho phép cập nhật kết quả theo nhiều phiên bản.

Nếu writer còn gửi message hoặc gọi API bên ngoài transaction database, thao tác SQL idempotent **không làm** side effect đó tự động idempotent; cần message ID ổn định, outbox hoặc cơ chế deduplication.

## 6. Cấu hình Step không buộc processor phải stateful

Khi reader giữ state theo step, processor vẫn có thể là một singleton stateless và writer là bean được chia sẻ đúng contract:

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
public Step ordersWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        JdbcCursorItemReader<Order> ordersReader,
        StatelessOrderProcessor processor,
        JdbcBatchItemWriter<Receipt> receiptWriter) {

    return new StepBuilder("ordersWorkerStep", jobRepository)
            .<Order, Receipt>chunk(250, transactionManager)
            .reader(ordersReader)
            .processor(processor)
            .writer(receiptWriter)
            .build();
}
~~~

Trong một class `@Configuration` có các dependency trên, `ordersReader` là scoped proxy được inject vào step; target reader thực được tạo cho mỗi `StepExecution`. `StatelessOrderProcessor` không giữ trạng thái giữa các lời gọi, vì vậy không cần `@StepScope` chỉ vì step chạy song song.

Nếu cần một processor với immutable configuration theo partition, có thể khai báo `@StepScope` và late bind:

~~~java
@Bean
@StepScope
public ItemProcessor<Order, Receipt> tenantProcessor(
        @Value("#{stepExecutionContext['tenantId']}") String tenantId) {

    if (tenantId == null || tenantId.isBlank()) {
        throw new IllegalArgumentException("Missing tenantId");
    }
    return order -> {
        if (!tenantId.equals(order.tenantId())) {
            throw new IllegalArgumentException("Unexpected tenant");
        }
        return new Receipt(
                order.id(), tenantId, order.amount());
    };
}
~~~

Lambda có capture `tenantId` bất biến và target bean theo step. Nó an toàn hơn một singleton liên tục gọi `setTenantId(...)` trước khi xử lý partition. Ví dụ giả định mỗi partition đã có `tenantId` trong context; khi dùng range partition không có key đó, phải cung cấp từ partitioner hoặc dùng processor stateless trước đó.

## 7. @StepScope chưa đủ cho multi-threaded step

Đây là điểm thường bị hiểu sai nhất.

| Mô hình | Số `StepExecution` | Bean `@StepScope` có thể được dùng bởi ai? |
|---|---|---|
| **Step tuần tự** | Một | Một thread tuần tự trong lần thực thi thông thường |
| **Multi-threaded step** | Thường là **một** | Nhiều thread/chunk của **cùng** `StepExecution` có thể cùng gọi **một target** |
| **Local partitioning** | Nhiều, mỗi partition một execution | Mỗi execution có **target riêng**; thread safety vẫn cần xét dependency |
| **Remote partitioning** | Nhiều, trên các process khác nhau | Target riêng theo execution tại worker; metadata và dữ liệu dùng chung vẫn cần nhất quán |
| **Parallel flows/steps** | Mỗi step/flow có execution riêng | Bean singleton vẫn có thể bị các execution gọi chung nếu tham chiếu cùng bean |

Giả sử `FlatFileItemReader` được dùng với `@StepScope` trong một multi-threaded step có `TaskExecutor`. Chỉ có một `StepExecution` nên chỉ có một target reader, không phải mỗi thread một reader riêng. Các thread có thể tranh cursor và làm checkpoint không đúng.

Các hướng xử lý đáng cân nhắc:

1. **Ưu tiên partitioning**, mỗi partition có `StepExecution`/reader riêng, khi dữ liệu chia độc lập được.
2. Với reader không thread-safe buộc phải chia sẻ, có thể dùng một decorator như `SynchronizedItemStreamReader` hoặc đồng bộ theo contract thư viện **sau khi hiểu giới hạn**.
3. Thiết kế reader dựa trên hàng đợi hoặc nguồn vốn hỗ trợ cạnh tranh và bảo đảm item được cấp độc lập cho mỗi worker.
4. Nếu checkpoint và ordering phức tạp, giảm concurrency hoặc dùng từng step tuần tự thay vì đánh đổi tính đúng.

**Cảnh báo về `SynchronizedItemStreamReader`:** khóa `read()` có thể bảo vệ việc đọc, nhưng không tự giải quyết an toàn của toàn chu trình `read/process/write`, ordering và restart. Khi các chunk được xử lý không theo thứ tự đọc, khả năng restart của một reader đọc tuần tự có thể bị ảnh hưởng. Đừng hiểu wrapper đồng bộ là “bật thread safety và exactly-once”.

### Vì sao @JobScope không thay thế được?

`@JobScope` tạo bean theo `JobExecution`, tức một target có thể được sử dụng bởi nhiều step/partition trong một job. Với state mutable theo item hoặc partition, đây là phạm vi **quá rộng**. Ngoài ra, context của job không được thiết lập tự động trên mọi thread tạo thủ công trong môi trường multi-threaded/partitioned step. Với reader có state theo partition, `@StepScope` thường là lựa chọn đúng hơn.

`@StepScope` và `@JobScope` là công cụ quản lý lifecycle, **không phải distributed lock hoặc transaction manager**.

## 8. Vì sao các cách sửa nhanh thường không đủ?

### `volatile` chỉ xử lý một phần visibility

~~~java
private volatile long processedCount;

void increment() {
    processedCount++; // Vẫn không atomic!
}
~~~

`processedCount++` gồm nhiều bước logic, hai thread vẫn có thể đọc cùng giá trị rồi ghi chồng nhau. `AtomicLong.incrementAndGet()` xử lý đếm nguyên tử **trong một JVM**, nhưng không tự biến toàn bộ processor thành thread-safe và không giải quyết semantics khi chunk rollback/retry. Một counter trong RAM cũng mất sau khi process chết, không thể thay checkpoint của `JobRepository`.

### `synchronized` đánh đổi thông lượng

Đánh dấu `synchronized` trên toàn bộ method `process` có thể ngăn race trong JVM, nhưng:

- Tất cả thread phải đợi một khóa, mất lợi ích scale.
- Không đồng bộ với worker service ở JVM khác.
- Không tự làm commit/rollback của DB và side effect bên ngoài thành nguyên tử.
- Không tự bảo đảm checkpoint và thứ tự xử lý được khôi phục đúng.

Dùng đồng bộ **chỉ khi** phạm vi tài nguyên phải độc quyền thật sự, đã đo chi phí và không thể cô lập state.

### `ThreadLocal` không đại diện cho StepExecution

Một `ThreadLocal` gắn state theo **thread**, không phải theo step/partition. Trong executor pool, thread có thể được tái sử dụng cho nhiều execution; nếu quên `remove()`, state có thể rò sang tác vụ sau. Một execution cũng có thể không luôn gắn với cùng một thread ở mọi mô hình xử lý. `ThreadLocal` không tồn tại qua restart JVM hoặc đi theo remote worker.

Vì vậy, đừng dùng `ThreadLocal` để lưu checkpoint, business context hay tenant của partition thay cho `ExecutionContext` và scope đúng vòng đời.

### ConcurrentHashMap không phải thuốc chữa tổng quát

`ConcurrentHashMap` giúp một số thao tác map an toàn đồng thời; nó không tự biến cả chuỗi “đọc–kiểm tra–ghi” thành một transaction, cũng không bảo vệ state của object mutable nằm bên trong map. Đưa toàn bộ state partition vào static map theo `stepExecutionId` còn tạo nguy cơ leak, quên cleanup và mất state khi worker restart.

Nếu phải cache dữ liệu chung, hãy xác định cache immutable hay mutable, eviction, key isolation, concurrency semantics và cách tái tạo khi restart; ưu tiên hạ tầng cache được thiết kế cho việc đó.

## 9. ExecutionContext dùng để lưu checkpoint, không phải shared concurrent map

`StepExecutionContext` thuộc **một `StepExecution`** và được Spring Batch lưu qua `JobRepository` theo lifecycle. Đối với `ItemStream`, framework có thể gọi:

~~~text
open(executionContext)
    -> khôi phục vị trí reader

read/process/write theo chunk

update(executionContext)
    -> lưu vị trí hiện tại trước commit phù hợp

JobRepository lưu metadata/checkpoint

close()
    -> giải phóng tài nguyên
~~~

Phân biệt hai nhóm key:

| Key | Ví dụ | Ai quản lý? |
|---|---|---|
| **Thông tin phân vùng** | `minId`, `maxId`, `tenantId`, `fileKey` | Partitioner/manager hoặc code điều phối |
| **Vị trí checkpoint** | `ordersRangeReader.read.count` và các key nội bộ khác | `ItemStream`/framework |

Đừng tự cập nhật các key checkpoint nội bộ của reader. Đừng dùng `ExecutionContext` làm bảng trạng thái có nhiều thread cùng `put` không kiểm soát: `ExecutionContext` được thiết kế cho metadata thực thi, **không phải một concurrent map tùy ý**.

Với nhiều partition, mỗi context cần giữ dữ liệu nhỏ và tuần tự hóa được, chẳng hạn ID range, tên file, cutoff hoặc manifest key. Không nhét toàn bộ list triệu record, `DataSource`, open connection, bean Spring hoặc đối tượng mutable lớn vào context. Cũng không lưu secret/credential trong metadata nếu không có biện pháp bảo vệ thích hợp.

### Restart không làm state trong singleton sống lại

Nếu một reader/processor singleton giữ `lastProcessedId` trong RAM mà không lưu qua cơ chế `ItemStream`, worker bị kill sẽ mất vị trí ấy. Một process mới không thể đoán chính xác item đã commit chỉ từ field mutable trong process cũ.

Muốn restart an toàn:

- Dùng **cùng identifying `JobParameters`** cho job instance bị lỗi.
- Giữ `stepName`/partition names, cutoff và phạm vi đầu vào ổn định.
- Bảo đảm reader là `ItemStream` được đăng ký lifecycle đúng và có `saveState` phù hợp.
- Dùng query có thứ tự ổn định, file snapshot hoặc manifest bất biến.
- Bảo đảm writer idempotent; với side effect ngoài DB, dùng outbox, deduplication hoặc idempotency key.
- Đối soát `readCount`, `writeCount`, commit và dữ liệu nghiệp vụ sau khi recover.

## 10. Khi scale ngang, singleton còn nghĩa gì?

Một singleton của Spring chỉ là singleton **trong một application context**, không phải một object duy nhất cho toàn bộ cụm.

~~~mermaid
flowchart LR
    M[Manager] --> Q[(Request queue)]
    Q --> A[Worker pod A]
    Q --> B[Worker pod B]
    A --> S1[Singleton bean A]
    B --> S2[Singleton bean B]
    A --> DB[(Shared database)]
    B --> DB
    M --> JR[(JobRepository)]
    A --> JR
    B --> JR
~~~

Hai pod có thể cùng một class `@Component` nhưng **hai singleton instance khác nhau**. Vì vậy một counter trong singleton A **không** phản ánh toàn bộ cluster. Ngược lại, hai instance có thể cùng sửa một row DB, một cache key hoặc một file shared; dù không chia sẻ Java object, ứng dụng vẫn có **concurrency ở cấp dữ liệu**.

Để bảo đảm an toàn khi nhiều máy xử lý, cần các lớp:

1. Partition plan không giao nhau hoặc có khóa/lease rõ ràng.
2. Transaction và unique constraint ở database.
3. Idempotency khi retry, broker redelivery hoặc worker chết sau commit.
4. Giới hạn concurrency/connection pool và giám sát toàn cụm.
5. Schema message/context tương thích khi manager và worker nâng cấp độc lập.

**Không dùng một Java `synchronized` hay static map để bảo vệ tài nguyên chung của nhiều pod.** Những cơ chế đó chỉ có hiệu lực trong một JVM.

## 11. Concurrency nên được quyết định bởi tài nguyên, không chỉ annotation

Giả sử manager tạo 40 partition, hệ thống có 5 worker pod và mỗi pod có thể thực thi 2 `StepExecution` cùng lúc. Trần lý thuyết là:

\[
C_{\mathrm{active}} \le \min(40, 5 \times 2) = 10
\]

Con số này là **trần scheduling**, không phải lời hứa xử lý nhanh gấp 10. Nếu mỗi execution giữ JDBC cursor, nhiều transaction DB và các thao tác ghi, database hoặc pool của từng pod có thể bị nghẽn trước khi CPU xử lý đạt mức tối đa.

### Tính ngân sách kết nối

Nếu `N` pod, mỗi pod có pool tối đa `P` connection, `M` connection dành cho manager/metadata hoặc các client khác, thì một ước lượng về **sức chứa tối đa có thể mở** là:

\[
C_{\mathrm{cluster,max}} \approx N \times P + M
\]

Phải so sánh với `max_connections` của database và các hệ thống khác, đồng thời nhớ rằng DB metadata, reader cursor và writer transaction có thể dùng các connection khác nhau tùy cấu hình. Không đồng nhất `pool max` với số connection đang active; hãy đo active/idle/pending và thời gian chờ.

| Số đo | Ý nghĩa thường gặp | Hướng xử lý |
|---|---|---|
| CPU worker thấp, DB pool pending cao | Thread đang chờ connection thay vì tính toán | Giảm concurrency hoặc tăng pool có kiểm soát nếu DB còn capacity |
| CPU worker cao, DB/broker nhàn | Workload có thể bị giới hạn CPU | Xem phân phối worker và CPU throttling |
| Partition duration lệch lớn | Dữ liệu chia không đều hoặc một nguồn bị chậm | Cải thiện partition plan/manifest |
| Retry/rollback tăng theo số worker | Tranh chấp lock hoặc downstream quá tải | Giảm worker, tối ưu transaction và retry |
| Throughput không tăng nhưng GC/heap tăng | Overhead đồng thời, buffer hoặc object allocation tăng | Giảm in-flight workload, đo profiler/GC |

Hãy chạy benchmark với số worker 1, 2, 4, 8 trên cùng snapshot. So sánh wall-clock time, throughput, latency p95/p99, DB pool wait, rollback, và **tính đúng của kết quả**; không chỉ nhìn trạng thái `COMPLETED`.

## 12. Kiểm thử để phát hiện shared mutable state

### 12.1. Unit test phải thử concurrent invocation

Đầu tiên, test tuần tự xác nhận business logic. Sau đó cố tình gọi processor cùng một instance từ nhiều thread và so sánh `tenantId` đầu ra với đầu vào tương ứng.

Ví dụ pseudo-test kiểm tra bất biến nghiệp vụ:

~~~java
// Thiết lập một tập Order gồm nhiều tenant khác nhau.
// Dùng ExecutorService chạy process(order) đồng thời.
// Assert cho mọi i: result[i].tenantId().equals(order[i].tenantId()).
// Lặp phép thử nhiều lần, thay đổi interleaving để phát hiện race.
// Đừng chỉ assert count; cần so sánh từng item / tenant.
~~~

Đây là **kịch bản test**, không phải assertion rằng test này luôn bắt được race. Concurrency bugs có thể phụ thuộc lịch thread; để tăng độ chắc chắn, có thể dùng barrier/latch trong test hoặc stress test nhiều vòng, nhưng luôn kết hợp **thiết kế loại bỏ shared state** thay vì chỉ dựa vào may rủi của test.

### 12.2. Test partition, checkpoint và restart

Một integration test có giá trị nên thực hiện:

1. Tạo snapshot đầu vào xác định, lập nhiều `ExecutionContext` với range không overlap.
2. Chạy các worker step đồng thời, thu `readCount`/`writeCount` theo từng `StepExecution`.
3. Kiểm tra **tập ID đầu ra** đúng bằng tập ID đầu vào, không trùng và không thiếu.
4. Chủ động tạo lỗi giữa chunk (sau khi đã có commit), sau đó restart cùng job instance.
5. Xác minh partition hoàn tất không bị xử lý ngoài chủ đích và checkpoint khôi phục đúng.
6. Với remote worker, thử crash trước ACK/reply và bảo đảm tác động nghiệp vụ vẫn an toàn khi request bị phát lại.

Một test chỉ xác nhận tổng count có thể bỏ sót trường hợp **một ID bị xử lý hai lần và một ID khác bị thiếu**; nên so sánh tập khóa, checksum hoặc kết quả business.

### 12.3. Kiểm tra bean scope thực tế

Trong test Spring Batch có thể dùng `StepScopeTestUtils` (từ `spring-batch-test`) để tạo một `StepExecution` giả lập và resolve bean scoped trong context:

~~~java
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.MetaDataInstanceFactory;
import org.springframework.batch.test.scope.StepScopeTestUtils;

StepExecution se = MetaDataInstanceFactory.createStepExecution();
se.getExecutionContext().putLong("minId", 1L);
se.getExecutionContext().putLong("maxId", 100L);

StepScopeTestUtils.doInStepScope(se, () -> {
    // Resolve bean scoped từ ApplicationContext.
    // Xác minh target reader nhận đúng 1..100, không giữ range trước.
    return null;
});
~~~

Đây là **khung test**, chưa phải test độc lập hoàn chỉnh. Test thực tế cần chuẩn bị `ApplicationContext`, nguồn dữ liệu và assertions. Tạo `StepExecution` thứ hai với range khác để xác minh state không bị chia sẻ giữa executions.

## 13. Runbook khi dữ liệu sai sau khi tăng thread

Khi tăng concurrency rồi xuất hiện record trùng, thiếu hoặc sai tenant, hãy kiểm tra có hệ thống:

1. Từ `jobExecutionId` và `stepExecutionId`, đối chiếu danh sách partition, ranh giới dữ liệu, worker instance và các key trong `ExecutionContext`.
2. Xem cấu hình thực tế đang dùng **multi-threaded step** hay **partitioning**. Với multi-threaded step, có bao nhiêu thread cùng dùng một reader target?
3. Kiểm tra các bean `ItemReader`, `ItemProcessor`, `ItemWriter`, listener và custom service: có instance field `current...`, `count`, `Map`/`List` mutable hoặc client non-thread-safe không?
4. Tìm state bị đưa vào singleton/shared static `Map`, field `ThreadLocal` hoặc bean `@JobScope` quá rộng.
5. Xem `JobRepository`: checkpoint có được lưu đúng và có partition nào rollback/retry nhiều bất thường?
6. Kiểm tra DB và broker: lock contention, constraint violation, redelivery, file overlap, timeout; không quy mọi lỗi dữ liệu cho Java race.
7. Giảm concurrency để khoanh vùng, sau đó sửa thiết kế bằng stateless operation hoặc cô lập theo `StepExecution`. Không dùng `synchronized` trên toàn pipeline như giải pháp mặc định.
8. Chạy lại với snapshot cố định, đối soát **từng khóa nghiệp vụ** và thử restart/crash trước khi phát hành.

## 14. Checklist dùng trước production

- [ ] Các bean singleton được rà soát: không giữ mutable per-item/per-partition state không cần thiết.
- [ ] Processor stateless dùng DTO immutable và local variables; dependency được kiểm tra thread safety.
- [ ] Reader có cursor/state được cô lập theo `StepExecution` bằng `@StepScope` khi partitioning.
- [ ] Đã phân biệt `@StepScope` giữa nhiều `StepExecution` với nhiều thread trong **một** `StepExecution`.
- [ ] Không dùng `@JobScope` hoặc `ThreadLocal` làm nơi giữ checkpoint của partition.
- [ ] `ExecutionContext` chỉ chứa state nhỏ, serializable và đúng lifecycle; không ghi đè key nội bộ của reader.
- [ ] Partition plan, names, cutoff và input ổn định khi restart.
- [ ] `ItemStream` được đăng ký lifecycle và writer/side effects idempotent.
- [ ] Đã tính DB/middleware pool cho cả pod và cluster, đo waiting/rollback khi scale.
- [ ] Test concurrent processing kiểm tra từng item, không chỉ tổng số count.
- [ ] Đã test fail/restart và worker redelivery nếu chạy phân tán.
- [ ] Có log/metric theo `jobExecutionId`, `stepExecutionId`, partition và worker, không lộ dữ liệu nhạy cảm.

## 15. Bài tập thực hành và câu hỏi tự kiểm tra

### Bài tập 1 — Tìm race condition

Với `UnsafeOrderProcessor` ở phần 3, viết stress test với nhiều tenant và 8 thread. Liệt kê những field nào bị chia sẻ và lỗi nào có thể xuất hiện. Sau đó thay bằng `StatelessOrderProcessor` và so sánh đầu ra theo từng ID.

### Bài tập 2 — Chuyển từ singleton reader sang StepScope

Giả sử có một `JdbcCursorItemReader` singleton và bốn partition với range 1..250, 251..500, 501..750, 751..1000. Hãy chuyển reader thành `@StepScope`, late bind `minId/maxId` và kiểm tra mỗi partition có checkpoint độc lập. Giải thích vì sao không tạo bốn reader thủ công trong một static map.

### Bài tập 3 — Multi-threaded step khác partitioning

Chạy một step với `TaskExecutor` có 4 thread dùng chung reader `@StepScope`. Phân tích vì sao vẫn có thể sai. Đổi sang local partitioning với 4 `StepExecution` và reader target riêng; so sánh độ đúng, tài nguyên DB và hiệu năng.

### Bài tập 4 — Retry/restart không đánh đổi tính đúng

Làm một partition lỗi sau vài chunk đã commit. Restart bằng cùng identifying `JobParameters` và input bất biến. Kiểm tra `ExecutionContext`, record đầu ra và idempotency của writer. Thêm thao tác publish event và thiết kế outbox/deduplication.

### Bài tập 5 — Scale theo ngân sách

Manager tạo 40 partition. Bắt đầu với 4 pod, mỗi pod một worker; sau đó thử 8 pod. Đo wall-clock time, JDBC pool pending, SQL lock wait, CPU, số retry và partition chậm nhất. Kết luận khi nào tăng worker có ích và khi nào cần tối ưu DB/partition plan.

**Câu hỏi tự kiểm tra:** Vì sao singleton không mặc nhiên sai? Vì sao `@StepScope` không sửa được mọi lỗi multi-threaded step? `AtomicLong` giải quyết vấn đề gì và không giải quyết vấn đề gì? Vì sao mutable state trong singleton không thể dùng làm checkpoint restart? Tại sao hai singleton ở hai worker pod không chia sẻ Java field nhưng vẫn có thể tranh chấp dữ liệu?

## 16. Kết luận

Để scale Spring Batch an toàn, hãy **đặt mutable state ở phạm vi nhỏ nhất tương ứng với vòng đời của nó**. Một singleton **stateless** có thể rất phù hợp cho processor hoặc service dùng chung; state của reader, cursor và checkpoint thường thuộc một `StepExecution` và nên được cô lập bằng `@StepScope` trong partitioning. Ngược lại, một multi-threaded step có thể cho nhiều thread dùng cùng target scoped bean, nên vẫn cần đánh giá thread safety theo đúng mô hình thực thi.

Khi chuyển từ một thread sang nhiều thread, partition hoặc worker process, chỉ tăng concurrency sau khi đã kiểm chứng **ranh giới dữ liệu, restart/idempotency, connection pool, metrics và tính đúng trên từng item**. Loại bỏ shared mutable state nguy hiểm không chỉ tránh race condition, mà còn làm hệ thống dễ đo lường, khôi phục và vận hành bền vững ở workload dữ liệu lớn.
