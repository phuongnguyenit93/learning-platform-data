# Scope bean khi nhiều thread cùng chạy trong Spring Batch

## Mục tiêu bài học

Một ứng dụng Spring Batch có thể chạy đúng ở chế độ tuần tự nhưng đọc trùng dữ liệu, ghi nhầm partition hoặc hỏng checkpoint sau khi bật `TaskExecutor`. Nguyên nhân thường không nằm ở thuật toán nghiệp vụ mà ở cách các bean **được tạo, chia sẻ và sử dụng đồng thời**. Đặt `@StepScope` lên một `ItemReader` có thể giúp mỗi partition nhận vùng dữ liệu riêng, nhưng **không** có nghĩa mỗi thread xử lý chunk sẽ tự động được cấp một reader riêng.

Bài thuộc chương **An toàn luồng** của module **SPRING_BATCH_SCALING_OPERATIONS**. Trọng tâm là **scope bean khi nhiều thread cùng chạy**, gắn với lựa chọn multi-threaded step, parallel steps, local/remote partitioning và remote chunking. Mục tiêu cuối không chỉ là tăng throughput, mà còn bảo đảm thread safety, tính đúng dữ liệu, retry/restart và chi phí vận hành theo khả năng thực tế của hệ thống.

Sau bài học, bạn có thể:

- Phân biệt `singleton`, `prototype`, `@JobScope`, `@StepScope` và phạm vi của thread.
- Xác định bean nào thực sự được chia sẻ theo **JobExecution**, **StepExecution**, chunk thread, partition hoặc JVM.
- Giải thích tại sao scoped proxy không biến một bean mutable thành thread-safe.
- Dùng late binding từ `JobParameters` và `StepExecutionContext` đúng phạm vi.
- Thiết kế reader/processor/writer theo mô hình local partitioning với state được cô lập.
- Tránh dùng `@JobScope` và context thread-bound sai cách trong các step song song.
- Kiểm thử concurrency, fault tolerance, checkpoint và restart thay vì chỉ kiểm tra job hoàn thành.
- Ước lượng trade-off giữa tạo nhiều instance, đồng bộ hóa và throughput.

## 1. Scope là ranh giới vòng đời, không phải chứng chỉ thread safety

Trong Spring, **scope** trả lời câu hỏi: *một bean target được tạo bao nhiêu lần, sống trong phạm vi nào và khi nào được truy xuất?* **Thread safety** trả lời câu hỏi khác: *nếu nhiều thread đồng thời gọi cùng một object, các bất biến dữ liệu có được giữ hay không?*

Hai câu hỏi liên quan nhưng không thể thay thế nhau.

Ví dụ:

~~~java
public final class CountingProcessor
        implements ItemProcessor<InputRow, OutputRow> {

    private long processed;

    @Override
    public OutputRow process(InputRow row) {
        processed++; // thao tác read-modify-write không nguyên tử
        return new OutputRow(row.id(), row.amountCents());
    }

    public long processedCount() {
        return processed;
    }
}
~~~

Nếu một instance `CountingProcessor` chỉ chạy trên một thread, biến `processed` ít có nguy cơ race. Nhưng nếu cùng instance được dùng bởi bốn chunk threads, các lượt `processed++` có thể ghi đè lên nhau. Thêm `@StepScope` **không giải quyết** vấn đề nếu bốn thread vẫn thuộc **cùng StepExecution**.

Ngược lại, một processor immutable và stateless có thể dùng an toàn như bean singleton:

~~~java
@Component
public final class AmountProcessor
        implements ItemProcessor<InputRow, OutputRow> {

    @Override
    public OutputRow process(InputRow row) {
        return new OutputRow(row.id(), row.amountCents());
    }
}
~~~

Các kiểu `InputRow` và `OutputRow` trong ví dụ là DTO/record giả định của ứng dụng. Tính an toàn của processor thứ hai còn phụ thuộc việc nó không tham chiếu SDK hoặc singleton mutable không an toàn.

**Nguyên tắc nền:** phải xét **scope + state thực tế + số thread/StepExecution cùng truy cập + giao dịch và side effect bên ngoài**.

## 2. Bản đồ phạm vi thực thi Spring Batch

Trước khi chọn annotation, cần hình dung cấu trúc execution:

~~~mermaid
flowchart TB
    J["JobExecution 501"]
    J --> S1["StepExecution A"]
    J --> S2["StepExecution B"]
    S1 --> C1["Chunk thread 1"]
    S1 --> C2["Chunk thread 2"]
    S2 --> C3["Chunk thread 3"]
    S2 --> C4["Chunk thread 4"]
    C1 --> R1["Reader/Processor/Writer được truy cập"]
    C2 --> R1
    C3 --> R2["Bean target khác nếu @StepScope"]
    C4 --> R2
~~~

Hình minh họa hai StepExecution và mỗi step có hai chunk threads. Trong thực tế cấu hình có thể không bật multi-threading bên trong worker step; hình chủ ý tách hai cấp concurrency để thấy sự khác biệt.

- **JobInstance:** danh tính logic của một batch job với các JobParameters phân biệt.
- **JobExecution:** một lần cố gắng thực thi JobInstance; khi restart có thể xuất hiện JobExecution khác.
- **StepExecution:** một lần thực thi step thuộc một JobExecution; trong partitioning, mỗi partition thường có StepExecution riêng.
- **Chunk thread:** thread đang xử lý một chunk; có thể có nhiều thread trong cùng một StepExecution nếu step dùng TaskExecutor.
- **JVM/process:** ranh giới heap. Các JVM khác nhau không chia sẻ cùng object Java, dù có thể dùng chung database, broker hay API.

Các khái niệm này tạo nên câu hỏi thực dụng: **một instance mutable bị chia sẻ bởi những execution/thread nào?**

## 3. Các scope Spring hay gặp

| Scope | Ranh giới target bean | Có mặc nhiên thread-safe không? | Lưu ý trong Spring Batch |
| --- | --- | --- | --- |
| **Singleton** (mặc định) | Một target bean trên mỗi Spring application context | **Không** | Có thể phục vụ nhiều step, thread hoặc partition trong cùng JVM |
| **Prototype** | Một target mới mỗi lần container được yêu cầu tạo bean | **Không** | Inject trực tiếp vào singleton thường chỉ tạo một instance tại lúc inject |
| **Step scope** (`@StepScope`) | Một target cho mỗi StepExecution đang truy cập | **Không** | Có thể dùng chung giữa các chunk threads của cùng StepExecution |
| **Job scope** (`@JobScope`) | Một target cho mỗi JobExecution | **Không** | Không nên dùng tùy tiện với multi-threaded/partitioned steps; context thread-bound |
| **Thread scope** (`SimpleThreadScope`) | Theo Java thread khi được đăng ký và sử dụng | **Không** | Không phải cấu hình mặc định; thread pool tái sử dụng thread và dễ rò state |
| **Request/session scope** | Theo request/session web | **Không** | Thường không phù hợp cho batch job chạy nền |

**Lưu ý quan trọng về @JobScope:** tài liệu Spring Batch nêu các giới hạn thực tế khi dùng job-scoped bean trong multi-threaded hoặc partitioned steps do framework không kiểm soát toàn bộ các thread được sinh ra để thiết lập job context đúng cách. Vì vậy không nên dựa vào `@JobScope` làm cách chia sẻ state trên nhiều worker thread.

**Lưu ý về @StepScope:** phạm vi gắn với **StepExecution**, không phải một thread. Nó hữu ích cho reader lấy `stepExecutionContext` của partition, nhưng không thay thế thiết kế thread-safe khi chính StepExecution đó xử lý nhiều chunk đồng thời.

## 4. Singleton: đơn giản, nhưng chia sẻ trên toàn ApplicationContext

Mặc định các bean do `@Component`, `@Service` hoặc `@Bean` tạo trong Spring có scope singleton. Đây là một bean **trên mỗi Spring ApplicationContext**, không phải một instance duy nhất trên mọi JVM.

Ví dụ không an toàn:

~~~java
@Service
public class UnsafeNormalizationService {
    private final StringBuilder buffer = new StringBuilder();

    public String normalize(String input) {
        buffer.setLength(0);
        buffer.append(input.trim().toLowerCase());
        return buffer.toString();
    }
}
~~~

Nếu một singleton `ItemProcessor` hoặc nhiều scoped processor cùng inject service này, tất cả dùng **cùng một `StringBuilder` trong JVM**. Tạo processor `@StepScope` không đủ nếu `UnsafeNormalizationService` vẫn là singleton mutable.

Cách cải thiện đơn giản hơn:

~~~java
@Service
public class StatelessNormalizationService {
    public String normalize(String input) {
        return input.trim().toLowerCase(java.util.Locale.ROOT);
    }
}
~~~

Không lưu mutable buffer giữa các lời gọi. Với code có nhiều thư viện ngoài, cần kiểm tra **toàn bộ dependency graph**, kể cả cache, formatter, parser, callback, SDK client và request builder.

### Singleton nào có thể chia sẻ?

Một bean stateless/immutable hoặc một client có **hợp đồng thread-safe rõ ràng** thường phù hợp làm singleton. Nhưng điều kiện cần kiểm tra:

1. Mọi field mutable có cơ chế concurrency đúng hoặc không bị sửa sau cấu hình.
2. Các tham số và đối tượng trả về có thể là request-specific, không được dùng chung sai phạm vi.
3. `close()`, `reset()`, `refreshToken()` hoặc thay cấu hình không chạy đồng thời ngoài hợp đồng.
4. Side effect trên DB/API vẫn có quy tắc atomicity và idempotency phù hợp.

**Singleton không có nghĩa là sai**; nó chỉ làm trách nhiệm đánh giá concurrent access trở nên rõ ràng hơn.

## 5. Prototype: một target mới theo lượt lấy bean, không phải theo thread

`@Scope("prototype")` thường bị hiểu nhầm là “mỗi worker thread sẽ có một instance”. Thực tế, bean prototype được tạo mỗi khi container **thực hiện một lượt resolve/get bean**, không phải mỗi khi một method được gọi.

Ví dụ:

~~~java
@Configuration
class ParserConfiguration {

    @Bean
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    LegacyParser legacyParser() {
        return new LegacyParser();
    }
}

@Service
class UnsafeAdapter {
    private final LegacyParser parser;

    UnsafeAdapter(LegacyParser parser) {
        this.parser = parser;
    }

    // Adapter singleton giữ cùng một parser được inject ban đầu.
    String parse(String line) {
        return parser.parse(line);
    }
}
~~~

`LegacyParser` là dependency giả định không thread-safe. Dù bean parser được khai báo prototype, khi **inject vào singleton `UnsafeAdapter` một lần**, cùng một instance được giữ và chia sẻ giữa các lượt gọi. Annotation scope không tự tái tạo parser theo từng lần `parse()`.

### Lấy prototype theo mỗi lượt sử dụng

Dùng `ObjectProvider` khi việc tạo mới mỗi lần là hợp đồng thiết kế:

~~~java
@Service
class PerCallAdapter {
    private final ObjectProvider<LegacyParser> parsers;

    PerCallAdapter(ObjectProvider<LegacyParser> parsers) {
        this.parsers = parsers;
    }

    String parse(String line) {
        LegacyParser parser = parsers.getObject();
        return parser.parse(line);
    }
}
~~~

Ở ví dụ này, `getObject()` yêu cầu container resolve một prototype mới **mỗi lần parse**. Điều đó giúp cô lập mutable state của parser nếu parser không chia sẻ thêm singleton unsafe bên trong.

**Đánh đổi:** khởi tạo parser cho từng item có thể đắt về CPU và allocation/GC. Nếu một item là một dòng nhẹ, hàng triệu lượt tạo parser có thể làm throughput giảm. Đo trước khi dùng trong đường xử lý nóng (*hot path*).

**Lifecycle:** Spring không tự quản lý đầy đủ việc hủy từng prototype sau khi giao cho caller; nếu parser giữ file handle, session, native buffer hoặc connection, ứng dụng phải có kế hoạch đóng/trả resource theo hợp đồng thư viện.

## 6. @StepScope và scoped proxy thực sự hoạt động như thế nào?

`@StepScope` cung cấp một bean gắn với execution context của **StepExecution đang hoạt động**. Spring Batch thường tạo proxy để một bean singleton cấp cao có thể inject tham chiếu đến scoped bean trước khi step thực sự chạy.

~~~mermaid
flowchart LR
    A["Step configuration singleton"] --> P["Scoped proxy"]
    P --> S["StepExecution hiện tại"]
    S --> T["Target reader/processor của step"]
~~~

Điểm dễ nhầm:

- **Proxy có thể được inject một lần** và được chia sẻ như một object tham chiếu.
- **Target phía sau proxy** được truy xuất theo StepExecution đang hoạt động.
- **Trong cùng StepExecution**, các chunk threads có thể đến **cùng target**.
- **Giữa các StepExecution**, chẳng hạn hai partition, target theo StepScope thường khác nhau.
- Proxy **không khóa**, không sao chép object theo item và không tự chuyển object không an toàn thành thread-safe.

### Late binding

Một scoped reader chỉ biết phạm vi dữ liệu khi job thực thi. Có thể inject:

~~~java
@Value("#{stepExecutionContext['minIdInclusive']}")
Long minId;

@Value("#{stepExecutionContext['maxIdExclusive']}")
Long maxExclusive;

@Value("#{jobParameters['businessDate']}")
String businessDate;
~~~

Đây là cách lấy dữ liệu theo ngữ cảnh step, không phải giá trị được đọc khi ứng dụng khởi tạo. Với `JobParameters`, lựa chọn kiểu dữ liệu và cách parse phải phù hợp phiên bản Spring Batch.

Các key input phải được manager/partitioner thiết lập và ổn định qua restart. Nếu key thiếu, bean cần **fail sớm với thông báo rõ ràng**, không âm thầm dùng một khoảng mặc định dễ gây ghi trùng dữ liệu.

## 7. @StepScope trong multi-threaded step: bẫy phổ biến nhất

Xét một multi-threaded step có `TaskExecutor`, bốn chunk đang chạy đồng thời trên các thread khác nhau, nhưng **chỉ có một StepExecution**.

~~~mermaid
flowchart TB
    S["StepExecution: importStep #204"]
    S --> P["Một scoped proxy"]
    P --> T["Một target @StepScope ItemReader"]
    A["Thread 1"] --> P
    B["Thread 2"] --> P
    C["Thread 3"] --> P
    D["Thread 4"] --> P
~~~

Nếu target `ItemReader` có cursor, vị trí file hoặc buffer mutable, bốn thread vẫn có thể tranh chấp state.

Ví dụ dễ gây hiểu nhầm:

~~~java
@Bean
@StepScope
public ItemReader<Order> statefulReader(...) {
    return new SomeStatefulReader(...);
}
~~~

Chỉ thêm `@StepScope` không có nghĩa bốn thread được chia bốn `SomeStatefulReader`. Tương tự, `@StepScope` trên processor có SDK mutable cũng không loại bỏ race giữa chunk threads của cùng step.

### Thứ tự và checkpoint

Multi-threaded step có thể xử lý và commit các chunk không theo thứ tự ban đầu. Một reader được bảo vệ bằng `synchronized read()` có thể tránh đồng thời thay đổi cursor, nhưng điều đó **chưa chứng minh** checkpoint đúng khi chunk sau hoàn tất trước chunk trước.

Nếu reader chỉ hỗ trợ khôi phục theo vị trí tuần tự, cần xác minh theo tài liệu và thử restart thực tế; có lúc phải chọn kiến trúc khác hoặc cấu hình reader không lưu state theo sự đánh đổi có chủ đích. Không tắt checkpoint chỉ để xóa lỗi concurrency mà chưa thiết kế cơ chế đọc lặp an toàn.

**Kết luận:** nếu reader giữ vị trí đọc mutable và cần restart chặt chẽ, **partitioning với các reader độc lập theo phạm vi** thường dễ suy luận hơn việc dùng chung một reader giữa các chunk threads.

## 8. @StepScope trong local partitioning: một target theo partition

Local partitioning có manager chia dữ liệu thành nhiều partition, mỗi partition thông thường được biểu diễn bằng một StepExecution riêng. Khi worker step khai báo reader `@StepScope`, các partition có thể nhận các target reader khác nhau với input riêng.

~~~mermaid
flowchart TB
    M["Manager Step"]
    M --> A["Partition A: StepExecution A"]
    M --> B["Partition B: StepExecution B"]
    M --> C["Partition C: StepExecution C"]
    A --> RA["Reader @StepScope A"]
    B --> RB["Reader @StepScope B"]
    C --> RC["Reader @StepScope C"]
    RA --> DB[("Nguồn dữ liệu")]
    RB --> DB
    RC --> DB
~~~

Đây là một lợi ích lớn: reader có cursor riêng, SQL range riêng và checkpoint riêng. Nhưng một số điều kiện vẫn bắt buộc:

- `Partitioner` giao **miền dữ liệu không chồng lấn**.
- Tên partition và high-watermark ổn định qua restart cùng JobInstance.
- Worker step không âm thầm bật đa luồng bên trong mỗi partition nếu reader không an toàn.
- Các singleton mà reader/processor/writer inject vẫn phải thread-safe.
- DataSource/DB hỗ trợ được tổng connection và query song song.
- Không hai partition ghi cùng business key nếu nghiệp vụ chưa có cơ chế atomicity/idempotency.

**Grid size không phải số thread thực tế.** Có thể tạo 16 partition nhưng TaskExecutor chỉ có bốn thread. Điều này giúp cân bằng tải, đồng thời làm tăng số StepExecution và chi phí metadata cần quản lý.

## 9. Ví dụ hoàn chỉnh: local partitioning với reader @StepScope

Bài toán: đọc bảng `orders` theo ID và ghi tóm tắt vào `order_summary`. Mỗi partition có reader riêng, xử lý theo chunk **tuần tự bên trong worker step**; chỉ các **partition** chạy song song. Ví dụ minh họa Java 17, Spring Batch 5.x, PostgreSQL và một `JobRepository`/transaction manager được cấu hình sẵn.

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import javax.sql.DataSource;

import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class PartitionedOrdersConfiguration {

    public record Order(long id, long amountCents) {}

    @Bean
    public Partitioner ordersPartitioner() {
        return gridSize -> {
            long firstId = 1L;
            long maxExclusive = 1_000_001L;
            int count = Math.max(1, gridSize);
            long width = (maxExclusive - firstId + count - 1L) / count;

            Map<String, ExecutionContext> partitions =
                    new LinkedHashMap<>();

            for (int index = 0; index < count; index++) {
                long from = firstId + index * width;
                if (from >= maxExclusive) {
                    break;
                }
                long to = Math.min(from + width, maxExclusive);

                ExecutionContext input = new ExecutionContext();
                input.putLong("minIdInclusive", from);
                input.putLong("maxIdExclusive", to);

                partitions.put("orders-part-" + index, input);
            }
            return partitions;
        };
    }

    @Bean
    @StepScope
    public JdbcCursorItemReader<Order> partitionOrderReader(
            DataSource dataSource,
            @Value("#{stepExecutionContext['minIdInclusive']}")
                    Long minId,
            @Value("#{stepExecutionContext['maxIdExclusive']}")
                    Long maxExclusive) {

        if (minId == null || maxExclusive == null
                || minId >= maxExclusive) {
            throw new IllegalArgumentException(
                    "Partition ID range must be valid");
        }

        return new JdbcCursorItemReaderBuilder<Order>()
                .name("partitionOrderReader")
                .dataSource(dataSource)
                .sql("""
                     SELECT id, amount_cents
                     FROM orders
                     WHERE id >= ? AND id < ?
                     ORDER BY id
                     """)
                .preparedStatementSetter(ps -> {
                    ps.setLong(1, minId);
                    ps.setLong(2, maxExclusive);
                })
                .rowMapper((rs, rowNum) -> new Order(
                        rs.getLong("id"),
                        rs.getLong("amount_cents")))
                .saveState(true)
                .build();
    }

    @Bean
    public JdbcBatchItemWriter<Order> orderWriter(
            DataSource dataSource) {

        return new JdbcBatchItemWriterBuilder<Order>()
                .dataSource(dataSource)
                .sql("""
                     INSERT INTO order_summary (order_id, amount_cents)
                     VALUES (?, ?)
                     ON CONFLICT (order_id)
                     DO UPDATE SET
                         amount_cents = EXCLUDED.amount_cents
                     """)
                .itemPreparedStatementSetter((item, ps) -> {
                    ps.setLong(1, item.id());
                    ps.setLong(2, item.amountCents());
                })
                .build();
    }

    @Bean
    public Step partitionWorkerStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            JdbcCursorItemReader<Order> partitionOrderReader,
            JdbcBatchItemWriter<Order> orderWriter) {

        return new StepBuilder("partitionWorkerStep", jobRepository)
                .<Order, Order>chunk(250, transactionManager)
                .reader(partitionOrderReader)
                .writer(orderWriter)
                .build();
    }

    @Bean
    public TaskExecutor partitionExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("partition-");
        executor.initialize();
        return executor;
    }

    @Bean
    public Step ordersManagerStep(
            JobRepository jobRepository,
            Partitioner ordersPartitioner,
            @Qualifier("partitionWorkerStep")
                    Step partitionWorkerStep,
            @Qualifier("partitionExecutor")
                    TaskExecutor partitionExecutor) {

        return new StepBuilder("ordersManagerStep", jobRepository)
                .partitioner("partitionWorkerStep", ordersPartitioner)
                .step(partitionWorkerStep)
                .gridSize(8)
                .taskExecutor(partitionExecutor)
                .build();
    }
}
~~~

### Đọc mã theo scope

1. `ordersManagerStep` điều phối tối đa tám partition do `gridSize(8)` gợi ý cho Partitioner, trong khi executor có bốn worker threads.
2. `ordersPartitioner` tạo tám khoảng ID và đặt cặp key trong `ExecutionContext`.
3. Mỗi partition có `StepExecution` riêng và sử dụng `partitionWorkerStep` làm định nghĩa step chung.
4. `partitionOrderReader` là **target `@StepScope` riêng cho mỗi StepExecution**, nhận khoảng ID ở thời điểm thực thi.
5. `orderWriter` được cấu hình dạng singleton; cần xác nhận writer và hạ tầng được dùng đồng thời đúng hợp đồng. Với kiểu writer JDBC hỗ trợ batch và không lưu mutable per-partition state ngoài hợp đồng, có thể chia sẻ khi cấu hình phù hợp; trong trường hợp khác phải dùng instance/step scope riêng hoặc adapter an toàn.
6. Worker step không gọi `.taskExecutor(...)`, tức ví dụ không bật xử lý nhiều chunk thread trong **cùng** StepExecution.

**Giới hạn của ví dụ:** mã không định nghĩa `Job` hoặc hạ tầng DataSource/JobRepository và không bao gồm migration schema; `ON CONFLICT` là cú pháp PostgreSQL, cần khóa `UNIQUE`/primary key trên `order_id`. Đầu vào `1..1.000.000` được cố định để giải thích; trong production, cần chốt cutoff/snapshot hợp lệ theo nghiệp vụ và giữ ổn định khi restart. Cơ chế reader mở cursor, tài nguyên transaction và hành vi của driver phải được kiểm chứng trong môi trường thực tế.

### Vì sao method @Bean trả về JdbcCursorItemReader?

Khi dùng Java configuration cho step-scoped ItemStream, **nên khai báo kiểu trả về đủ cụ thể hoặc ít nhất là một kiểu có hợp đồng ItemStream** để Spring Batch nhận ra các callback `open/update/close`. Khai báo return type quá rộng, không thể hiện `ItemStream`, có thể làm framework không đăng ký lifecycle đúng cách.

Bài toán không kết thúc tại `@StepScope`: vẫn phải thử crash/restart và kiểm tra writer có idempotent để không nhân đôi dữ liệu.

## 10. Bean scope khi dùng parallel steps

Trong một job có nhiều flow chạy đồng thời, mỗi flow thường có các StepExecution riêng. Những **singleton Spring bean** mà các flow dùng chung vẫn chỉ có một target trên mỗi ApplicationContext.

Ví dụ:

~~~mermaid
flowchart TB
    J["JobExecution chung"]
    J --> S["Split flow"]
    S --> A["Flow A: StepExecution A"]
    S --> B["Flow B: StepExecution B"]
    A --> P1["Processor @StepScope A"]
    B --> P2["Processor @StepScope B"]
    P1 --> SDK["Singleton external SDK"]
    P2 --> SDK
~~~

`@StepScope` tách hai processor target, nhưng **singleton SDK bên dưới vẫn là một instance**. Nếu SDK giữ mutable request builder hay parser, Flow A và B có thể đua nhau thay đổi state.

Nếu hai flow phải ghi cùng một hàng tổng hợp, scope cũng không giải quyết atomicity ở database. Cần transaction phù hợp, ranh giới sở hữu dữ liệu, optimistic locking hoặc hợp nhất có kiểm soát.

**Khi dùng @JobScope:** cả hai step cùng thuộc một JobExecution có thể cùng trỏ đến job-scoped target. Vì vấn đề context thread-bound và hạn chế của multi-threaded/partitioned steps, **không dùng @JobScope như một chỗ chứa state mutable dùng chung cho các flow song song**.

## 11. Remote partitioning: mỗi JVM có scope container riêng

Trong remote partitioning, manager và worker là các JVM/process khác nhau. Scope của Spring sống trong **ApplicationContext của từng JVM**; một singleton manager không phải cùng Java object với singleton worker.

~~~mermaid
flowchart TB
    M["Manager JVM"]
    M --> Q[["Yêu cầu partition qua message"]]
    Q --> W1["Worker JVM 1"]
    Q --> W2["Worker JVM 2"]
    W1 --> A["Singleton SDK trong JVM 1"]
    W2 --> B["Singleton SDK trong JVM 2"]
    W1 --> S1["StepExecution A → Reader A"]
    W2 --> S2["StepExecution B → Reader B"]
    S1 --> DB[("DB chung")]
    S2 --> DB
~~~

Tuy không chia sẻ heap qua JVM, các worker vẫn có thể:

- Cùng ghi một bảng/index hoặc business key.
- Cạnh tranh connection của database và quota API.
- Chia sẻ filesystem/network mount với trạng thái ngoài JVM.
- Chạy nhiều partition đồng thời **trong cùng worker JVM**, khiến singleton của worker đó được dùng chung giữa các StepExecution.

Vì vậy **không đồng nhất “multi-process” với “không có concurrency issue”**.

### Scope và input phân tán

Trong remote partitioning, manager tạo `StepExecution` và `ExecutionContext` cho từng partition. Worker dùng `JobExplorer`/`JobRepository` và handler phù hợp để tìm phần việc, rồi bean `@StepScope` resolve input tại worker.

Để restart đúng, tên partition, key context và snapshot/high-watermark phải ổn định. Không dựa vào tên pod, thứ tự nhận message hoặc số replica để tự đoán miền dữ liệu.

## 12. Remote chunking: scope được tính ở manager hay worker?

Remote chunking khác remote partitioning: manager thường đọc và tạo chunk, worker nhận chunk qua message để process/write. Scope vẫn được xác định theo lifecycle Spring Batch thực tế ở **từng phía**.

Điểm cần kiểm tra:

- Reader của manager có thể được gọi trong một StepExecution; concurrency đọc thuộc mô hình manager.
- Worker xử lý nhiều message có thể tái dùng cùng singleton processor/writer.
- Một worker JVM có thể nhận nhiều chunk/requests đồng thời theo listener/container concurrency.
- Các object nhận từ message là dữ liệu đã deserialize; không vì chúng đến từ broker mà có thread safety cho mọi object được tạo lại.
- Message reply/ack, commit DB, retry và checkpoint không mặc nhiên nằm trong cùng một transaction.

**@StepScope của bean worker chỉ có ý nghĩa khi framework thực sự thiết lập StepExecution context cho luồng gọi đó.** Không nên suy đoán rằng remote chunking cũng có worker StepExecution và input theo partition giống hệt remote partitioning.

## 13. @JobScope: đúng cho state theo job, không phải khóa an toàn giữa threads

Một job-scoped bean thường phục vụ trường hợp một target theo JobExecution, chẳng hạn cấu hình, tham số hoặc resource được tạo cho toàn lần chạy.

~~~java
@Bean
@JobScope
public JobInputDescriptor jobInputDescriptor(
        @Value("#{jobParameters['businessDate']}")
        String businessDate) {

    return new JobInputDescriptor(businessDate);
}
~~~

Ví dụ giả định `JobInputDescriptor` là kiểu bất biến và framework hỗ trợ job scope theo cấu hình. Nhưng trong multi-threaded/partitioned steps:

- Job context thường được gắn với thread thực thi theo cơ chế framework.
- Framework không thể luôn chuẩn bị context đúng cho các thread do ứng dụng/partitioning sinh ra.
- Truy cập job-scoped target từ thread không có active job context có thể gây lỗi hoặc hành vi không như mong đợi.
- Ngay cả khi truy cập thành công, một target cho cả JobExecution **không** làm state mutable thread-safe.

**Khuyến nghị:** không dùng `@JobScope` để truyền trạng thái mutable qua các worker threads/partitions. Đưa input cần thiết vào `JobParameters`, chuyển tiếp những tham số cụ thể vào `StepExecutionContext` ở manager hoặc cấu hình reader `@StepScope` theo execution phù hợp. Nếu cần trạng thái chia sẻ bền vững, thiết kế store/transaction riêng có tính đúng và có khả năng restart.

## 14. Scope thread và ThreadLocal: vì sao không phải giải pháp mặc định?

Spring có `SimpleThreadScope` nhưng đây **không phải** scope tự động được đăng ký cho mọi ứng dụng Spring Batch. Việc đăng ký tùy biến và dùng một bean cho mỗi Java thread thường nghe có vẻ hợp lý, nhưng cần hiểu thread pool.

~~~mermaid
flowchart LR
    P["Executor thread #7"] --> A["Partition A / Job hôm nay"]
    A --> B["Thread-local SDK state còn lại"]
    P --> C["Partition B / Job ngày mai"]
    B --> C
~~~

Executor thường **tái sử dụng thread**. Vì vậy:

- Thread của partition sau có thể giữ state từ partition trước.
- `ThreadLocal` không tự bị hủy khi chunk, StepExecution hoặc JobExecution kết thúc.
- Resource giữ trong ThreadLocal có thể kéo dài vòng đời và tiêu tốn heap/connection.
- Callback/async có thể chuyển việc sang thread khác, khiến ThreadLocal không còn sẵn hoặc mang state sai.
- Không có checkpoint/restart tự động cho state gắn với thread.

Nếu buộc phải dùng ThreadLocal, cần lifecycle `try/finally` để `remove()`, tài liệu về owner và test thread reuse. Tuy nhiên nếu resource mang thông tin nghiệp vụ theo partition, **StepExecutionContext + @StepScope** thường là diễn đạt đúng hơn.

`SimpleThreadScope` cũng không quản lý destruction callbacks tự động như một số scope khác; không nên xem nó là cơ chế lifecycle hoàn chỉnh cho connection/session cần close.

## 15. Tự tạo thread và asynchronous callbacks có thể mất step context

Cơ chế của `@StepScope` dựa vào ngữ cảnh StepExecution đang hoạt động. Việc Spring Batch thực thi step theo lối hỗ trợ chính thức khác với tự mở thread tùy ý trong processor.

Ví dụ không nên mặc định an toàn:

~~~java
public OutputRow process(InputRow item) {
    CompletableFuture.supplyAsync(() -> {
        // Không mặc định có StepExecution context trong thread mới.
        // Không truy cập bừa một @StepScope proxy ở đây.
        return scopedService.enrich(item);
    });
    return new OutputRow(item.id(), item.amountCents());
}
~~~

Ngoài context, đoạn mã còn có lỗi thiết kế **không đợi CompletableFuture hoàn tất trước khi trả output**; chunk có thể commit trước khi tác vụ phụ kết thúc. Nếu tác vụ phụ gọi API bên ngoài, retry/restart và idempotency càng khó kiểm soát.

### Cách xử lý

- Ưu tiên mô hình parallelism do Spring Batch quản lý khi phù hợp.
- Không gọi scoped proxy từ arbitrary thread mà không kiểm tra context được truyền hợp lệ.
- Không tự gắn StepExecution context thủ công chỉ để né lỗi scope nếu chưa hiểu hoàn toàn vòng đời, transaction và cleanup.
- Nếu phải dùng async, hãy truyền **dữ liệu bất biến tối thiểu** vào task, xác định quy tắc chờ/kết thúc trước commit, xử lý lỗi và side effect rõ ràng.
- Để công việc có checkpoint độc lập, có thể mô hình hóa thành step/partition khác thay vì luồng phụ khó quản lý.

**Một context được truyền sang thread không tự truyền transaction DB, JDBC Connection, MDC, security context hoặc mọi ThreadLocal tương ứng.** Mỗi loại context có cơ chế riêng; không suy luận rằng một wrapper giải quyết được toàn bộ.

## 16. Chọn scope cho reader, processor và writer

Một cấu hình tốt thường **khác nhau theo loại component**, không phải cứ batch bean nào cũng gắn `@StepScope`.

| Component | Khi nào singleton hợp lý? | Khi nào StepScope/per-call hợp lý? |
| --- | --- | --- |
| **ItemReader** | Chỉ nếu implementation stateless hoặc chia sẻ an toàn theo thiết kế và yêu cầu restart | Reader có cursor/range theo partition thường cần StepScope |
| **ItemProcessor** | Mapping stateless, input/output immutable, dependency thread-safe | State/cấu hình riêng theo StepExecution; SDK mutable phải cô lập theo concurrency thật |
| **ItemWriter** | Writer có hợp đồng sử dụng đồng thời phù hợp, không có shared mutable buffer nguy hiểm | Writer lưu state theo partition, file output riêng, session riêng hoặc cần bind context |
| **StepExecutionListener** | Logic stateless, không lưu mốc thời gian chung giữa nhiều execution | Nếu có state theo StepExecution, dùng thiết kế lưu state riêng/đúng scope |
| **SDK client** | API chính thức cho phép reuse concurrent, lifecycle quản lý tập trung | Client không an toàn, request/session mutable hoặc cần credential/context riêng |
| **Configuration descriptor** | Immutable và không phụ thuộc execution | Dữ liệu phụ thuộc JobParameters/StepExecutionContext có thể được late-bind đúng scope |

**Với reader restartable**, dù scoped target đã tách đúng, phải bảo đảm framework nhận ra `ItemStream` để gọi `open/update/close` và trạng thái checkpoint. Nếu khai báo bean trả về kiểu quá chung, có thể gây vấn đề với việc nhận diện callback. Sử dụng return type cụ thể hoặc interface có `ItemStream` như trong ví dụ JDBC ở trên.

**Với writer singleton**, kiểm tra thread safety của cả writer lẫn resource nó gọi. Có một số writer không có state riêng nhưng dùng chung mutable request builder hoặc formatter bên trong; scope của writer không nói hết vấn đề.

## 17. Đừng thay đổi scope để chữa sai ranh giới giao dịch

Có những lỗi trông giống thread safety nhưng gốc là tính nguyên tử của nghiệp vụ.

Giả sử hai partition đọc các order khác nhau nhưng cùng tăng một dòng `daily_total` theo cách read–modify–write:

~~~mermaid
sequenceDiagram
    participant A as Partition A
    participant DB as Database
    participant B as Partition B
    A->>DB: SELECT total = 1000
    B->>DB: SELECT total = 1000
    A->>DB: UPDATE total = 1100
    B->>DB: UPDATE total = 1100
    Note over A,B: Kết quả mong muốn là 1200
~~~

Tạo reader và writer `@StepScope` khác nhau không sửa được **lost update** trên DB. Cần:

- Atomic SQL update có ngữ nghĩa đúng.
- Isolation/optimistic hoặc pessimistic locking khi cần.
- Partition ownership theo business key để tránh chồng lấn.
- Ghi kết quả trung gian theo partition rồi tổng hợp ở step cuối.
- Writer idempotent và ranh giới transaction rõ ràng.

Scope bảo vệ vòng đời **object Java**; tính đúng dữ liệu giữa nhiều JVM phải được bảo đảm bằng **mô hình nghiệp vụ và cơ chế của resource dùng chung**.

## 18. Checklist lifecycle: tạo, open, update, close và restart

Một bean stateful dùng cho reader/writer không chỉ có lúc khởi tạo. Cần kiểm tra chuỗi:

~~~mermaid
flowchart LR
    A["Bean target được resolve"] --> B["ItemStream.open"]
    B --> C["read/process/write chunk"]
    C --> D["ItemStream.update / checkpoint"]
    D --> E["commit"]
    E -. "các chunk tiếp" .-> C
    E --> F["ItemStream.close"]
~~~

Sơ đồ mô tả logic; thứ tự callback/transaction cụ thể phụ thuộc Spring Batch và cấu hình. `ItemStream.update` là callback để đồng bộ state checkpoint theo cơ chế framework, không nên mặc định callback chỉ chạy sau khi DB commit.

### Những câu hỏi cần kiểm tra

1. Bean stateful được tạo **một lần theo ranh giới nào**?
2. Ai gọi `open()`, và nó được gọi bao nhiêu lần trên cùng target?
3. Nếu hai chunk threads dùng chung reader, các lời gọi `read/update` có tương thích không?
4. Khi rollback, state reader có khớp phần đã commit không?
5. Khi restart, `ExecutionContext` có được restore cho đúng StepExecution không?
6. `close()` có thể làm hỏng thread đang dùng target không?
7. Resource bên ngoài có cần close/cleanup độc lập với scoped bean không?
8. Nếu bean là prototype, ai chịu trách nhiệm destruction callback?

**Không tắt `saveState` chỉ để hết một exception về checkpoint** nếu chưa chấp nhận rõ hệ quả mất khả năng restart dựa trên state; tùy reader và pipeline, điều này có thể dẫn đến đọc lại hoặc bỏ sót dữ liệu sau sự cố.

## 19. Kiểm thử scope bằng bằng chứng, không dựa vào annotation

Một unit test chạy một processor trên một thread **không** kiểm chứng scope của Spring container. Để kiểm tra thực tế, cần chạy đúng topology.

### 19.1. Kiểm tra số target tạo ra theo StepExecution

Có thể dùng một class giả định lưu `instanceId` khi khởi tạo:

~~~java
public final class TaggedProcessor
        implements ItemProcessor<InputRow, OutputRow> {

    private final String instanceId =
            java.util.UUID.randomUUID().toString();

    @Override
    public OutputRow process(InputRow input) {
        // Trong thử nghiệm: log stepExecutionId, thread name, instanceId.
        return new OutputRow(input.id(), input.amountCents());
    }

    public String instanceId() {
        return instanceId;
    }
}
~~~

Đăng ký `TaggedProcessor` với `@StepScope` và quan sát:

- **Multi-threaded step:** nhiều chunk threads trong một StepExecution có thể thấy **cùng target instanceId**.
- **Local partitioning:** các StepExecution partition độc lập nên có thể thấy **instanceId khác nhau**.
- **Remote partitioning:** target thuộc JVM của worker, vẫn cần kiểm tra số concurrent StepExecution trong JVM ấy.

Đừng chỉ log `System.identityHashCode` của **scoped proxy** rồi suy ra số target: proxy có thể là một object tham chiếu được chia sẻ, trong khi target khác nhau theo context.

### 19.2. Stress test trên object thật được chia sẻ

Nếu target có mutable state, dùng `ExecutorService`/JUnit hoặc một integration test Spring Batch để tạo truy cập đồng thời và đối soát từng business key.

Ví dụ kiểm tra một mapper stateless:

~~~java
@Test
void parallelMappingKeepsEveryBusinessKey() throws Exception {
    int tasks = 2_000;
    ExecutorService executor = Executors.newFixedThreadPool(8);
    StatelessOrderMapper mapper = new StatelessOrderMapper();

    try {
        List<Future<OutputRow>> results = new ArrayList<>();
        for (int i = 0; i < tasks; i++) {
            final long id = i;
            results.add(executor.submit(() ->
                    mapper.map(new InputRow(id, id * 100L))));
        }

        for (int i = 0; i < tasks; i++) {
            OutputRow row = results.get(i).get(20, TimeUnit.SECONDS);
            assertEquals(i, row.id());
            assertEquals(i * 100L, row.amountCents());
        }
    } finally {
        executor.shutdownNow();
    }
}
~~~

Giả định test có JUnit 5, các import tương ứng và mapper/DTO được khai báo; mã dùng một instance mapper để cố ý thử **concurrent use**. Test này không kiểm tra scope proxy, DB transaction hay restart; phải bổ sung integration test chạy job/partition thật.

### 19.3. Kiểm thử phạm vi trong container

Một bài integration test có giá trị nên:

1. Khởi chạy hai StepExecution với hai ExecutionContext khác nhau.
2. Ghi lại instance ID ở **target** reader/processor theo từng StepExecution.
3. Xác nhận các target không chia sẻ cursor/range ngoài ý muốn.
4. Chạy multi-threaded step riêng để chứng minh StepScope **không** tạo target theo thread.
5. Tạo lỗi giữa chunk và restart, kiểm tra không thiếu/trùng business key.
6. Theo dõi resource close và connection pool, không có leak sau hoàn thành/thất bại.

Nếu một test pass, đó là bằng chứng cho cấu hình được thử, **không phải chứng minh thread safety cho mọi interleaving hay mọi phiên bản dependency**.

## 20. Chọn mô hình thay vì cố chữa state bằng scope

Mỗi mô hình scaling mang một trade-off về chia sẻ state:

| Nhu cầu | Mô hình nên xét | Scope/khả năng thread safety cần chứng minh |
| --- | --- | --- |
| CPU còn dư, processor stateless, reader đồng thời an toàn | Multi-threaded step | Singleton stateless có thể hợp lý; StepScope không tách theo chunk thread |
| Các flow độc lập, riêng input/output | Parallel steps | StepScope riêng theo StepExecution; singleton dependency có thể dùng chung |
| Reader stateful, dữ liệu chia được theo ID/file/tenant | Local partitioning | Reader @StepScope theo partition, StepExecution riêng |
| Một JVM thiếu CPU/RAM, partition có input ổn định | Remote partitioning | Scope theo StepExecution ở worker JVM; input/context và restart bền vững |
| Manager đọc nhanh, process/write nặng | Remote chunking | Worker có thể nhận nhiều message; kiểm tra concurrency của component trong JVM |
| SDK không an toàn, không thể tạo riêng rẻ | Adapter/pool hoặc đổi thư viện | Lock/pool có giới hạn, đo throughput |
| Tài nguyên đích đã bão hòa | Tối ưu SQL/writer/quota trước | Scope không loại bỏ DB lock/rate limit |

**Nguyên tắc đơn giản:** nếu có thể dùng **bean stateless/immutable**, hãy ưu tiên cách đó. Nếu buộc có state riêng theo một partition, dùng scope tương ứng. Nếu cần một instance riêng cho từng lời gọi, dùng factory/prototype đúng lifecycle. Không dùng scope như một lớp che đậy concurrency contract chưa được hiểu.

## 21. Đo throughput sau khi thay scope

Chuyển từ một singleton SDK sang nhiều instance per-call/per-StepExecution có thể sửa được race, nhưng cũng có chi phí:

- **CPU:** khởi tạo parser/SDK/connection mới.
- **Heap và GC:** nhiều object hoặc buffer lớn.
- **Connection pool:** mỗi instance có thể mở resource riêng.
- **Metadata:** nhiều partition tạo nhiều StepExecution/ExecutionContext.
- **Lock contention:** synchronized wrapper có thể khiến nhiều thread chờ một object.
- **Startup latency:** scoped target thường khởi tạo lúc StepExecution chạy, không phải lúc ứng dụng start.

Một mô hình throughput trực quan:

\[
R_{\mathrm{end-to-end}}
\leq \min(R_{\mathrm{read}},R_{\mathrm{process}},R_{\mathrm{write}})
\]

Các thông lượng phải được quy về cùng đơn vị input/output tương đương; nếu processor lọc item, cần tính tỷ lệ chuyển đổi trước khi so. Tăng số instance processor chỉ giúp khi processor là nút thắt và DB nguồn/đích còn năng lực.

### Ví dụ benchmark giả định

| Cấu hình | Throughput | Kết quả dữ liệu | Ghi chú |
| --- | ---: | --- | --- |
| Step tuần tự, singleton stateful | 3.500 item/s | PASS | Baseline |
| 8 chunk threads, singleton stateful | 10.800 item/s | **FAIL** | Race, nhầm output |
| 8 chunk threads, adapter synchronized | 4.200 item/s | PASS | Lock bottleneck |
| 4 local partitions, reader @StepScope, processor stateless | 8.100 item/s | PASS | Tách StepExecution |
| 8 local partitions, processor per-partition SDK | 9.000 item/s | PASS | Bắt đầu gần trần DB |

Tất cả số liệu **giả định để thực hành nhận xét**, không phải số đo Spring Batch. Không chọn phương án 10.800 item/s nếu đầu ra sai. Khi mức throughput đủ đáp ứng SLA, có thể chọn mô hình ít tài nguyên hoặc dễ vận hành hơn thay vì luôn tăng số worker.

### Quan sát cần có

Ghi JobExecution ID, StepExecution ID, partition name, thread name, target instance ID trong log thử nghiệm; tránh đưa mọi ID này thành label metric với cardinality cao. Theo dõi `readCount`, `writeCount`, `rollbackCount`, latency chunk, heap/GC, connection wait, DB lock và số business key đúng.

## 22. Tình huống thực tế: 6 triệu hóa đơn, hai cấp concurrency

Một hệ thống cần xử lý **6 triệu hóa đơn** và ghi trạng thái chuẩn hóa trong **20 phút**. SLA đầu vào tối thiểu theo phép chia lý tưởng:

\[
R_{\mathrm{required}}=
\frac{6.000.000}{20\times60}
=5.000\ \mathrm{item/s}
\]

Processor chuẩn hóa mã sản phẩm bằng một legacy SDK chứa mutable buffer, reader dùng JDBC cursor có checkpoint. Ban đầu job chạy tuần tự chính xác nhưng không kịp SLA.

### Thử nghiệm A — Thêm TaskExecutor

Nhóm chuyển step sang tám chunk threads mà vẫn inject một singleton reader và legacy SDK. Throughput tăng, nhưng đôi lúc đọc trùng ID và giá trị chuẩn hóa từ item khác; job có thể vẫn báo COMPLETED. Việc gắn `@StepScope` lên reader **không giải quyết triệt để** vì tất cả chunk threads thuộc cùng StepExecution.

### Thử nghiệm B — Dùng synchronized

Nhóm bảo vệ tất cả lời gọi tới SDK và reader bằng lock. Kết quả đúng hơn trong test, nhưng nhiều thread phải chờ các hot lock; throughput vẫn thấp và checkpoint lệch thứ tự chưa được chứng minh an toàn cho restart.

### Thử nghiệm C — Local partitioning

Dữ liệu được chốt snapshot, chia thành 16 partition theo ID và chạy bốn worker threads. Mỗi worker StepExecution có:

- `JdbcCursorItemReader` `@StepScope` lấy ID range riêng.
- Processor `@StepScope` tạo một SDK mutable riêng theo partition.
- Worker step xử lý chunk tuần tự trong mỗi StepExecution.
- Writer idempotent theo business key, mỗi transaction commit theo chunk.

Cấu hình đáp ứng khoảng 6.800 item/s trong phép đo **giả định**, đủ vượt mức 5.000 item/s tối thiểu. Sau đó tăng lên tám worker chỉ đạt 7.100 item/s nhưng DB lock wait tăng; nhóm giữ bốn worker để có dư địa vận hành.

### Thử nghiệm D — Lỗi/restart

Nhóm dừng một worker giữa chunk và restart cùng JobInstance. Cần đối soát:

1. 6 triệu input hợp lệ được bao phủ đúng một lần theo khóa nghiệp vụ.
2. Các partition không chồng lấn; snapshot và tên partition giữ nguyên.
3. Những chunk chưa commit được xử lý lại an toàn.
4. Không ghi trùng hoặc sai mã chuẩn hóa sau restart.
5. Không rò SDK resource, cursor hoặc connection khi StepExecution kết thúc.

**Bài học:** thay đổi scope chỉ có ý nghĩa khi tương ứng đúng **ranh giới thực thi**. Chọn local partitioning không chỉ tăng throughput, mà còn làm reader/SDK state có owner rõ hơn.

## 23. Những hiểu nhầm thường gặp

| Nhận định | Thực tế |
| --- | --- |
| “@StepScope nghĩa là mỗi thread một bean.” | **Sai**: target gắn với StepExecution; nhiều chunk threads có thể cùng target. |
| “Prototype nghĩa là mỗi lần gọi method một instance.” | Chỉ khi code yêu cầu resolve bean lại; inject trực tiếp vào singleton thường giữ một instance. |
| “Bean singleton của Spring luôn thread-safe.” | Singleton chỉ là vòng đời, không phải concurrency contract. |
| “Gắn @StepScope lên processor sẽ sửa singleton SDK bên dưới.” | SDK singleton vẫn có thể được chia sẻ giữa các scoped targets. |
| “@JobScope phù hợp để giữ state mutable cho các worker partition.” | Dễ gặp vấn đề thread-bound context và chia sẻ state; không khuyến nghị cho multi-threaded/partitioned steps. |
| “ThreadLocal bảo đảm state đúng theo partition.” | Thread pool tái sử dụng thread; ThreadLocal không đồng nghĩa StepExecution. |
| “Remote partitioning không thể có race.” | Không chia sẻ heap giữa JVM nhưng có thể nhiều thread trong một JVM và DB/API chung. |
| “Tạo reader riêng là đủ để tránh trùng dữ liệu.” | Còn phải chia input không chồng lấn, checkpoint đúng và writer idempotent. |
| “Scoped proxy là một bản sao riêng của object trên mỗi lời gọi.” | Proxy định tuyến đến target theo active scope; nó không tự nhân bản theo method call. |
| “Thread safety của Java object bảo đảm DB đúng.” | Lost update, lock, transaction và idempotency là vấn đề ở resource chung. |
| “Test pass nghĩa là chắc chắn restart đúng.” | Phải thử crash/rollback và đối soát dữ liệu đầu ra. |
| “Càng nhiều scoped bean càng nhanh.” | Khởi tạo, heap/GC và connection có thể khiến throughput giảm. |

## 24. Checklist thiết kế scope trước khi scaling

- [ ] Biết chính xác một JobExecution có bao nhiêu StepExecution và chunk threads.
- [ ] Xác định `singleton`, `prototype`, `@JobScope`, `@StepScope` trên tất cả component nóng.
- [ ] Hiểu scoped proxy khác target và phân biệt StepExecution với Java thread.
- [ ] Liệt kê bean mutable và dependency được reader/processor/writer gọi.
- [ ] Không giả định singleton/prototype/StepScope tự bảo đảm thread safety.
- [ ] Không dùng `@JobScope` tùy tiện trong multi-threaded hoặc partitioned steps.
- [ ] Reader có cursor/range được cô lập theo StepExecution nếu dùng partitioning.
- [ ] Processor có SDK mutable dùng riêng theo đúng phạm vi concurrency hoặc có cơ chế bảo vệ an toàn.
- [ ] Writer có contract concurrency và transaction/idempotency phù hợp.
- [ ] `@StepScope` nhận input từ `StepExecutionContext` và validate key/range.
- [ ] Bean `ItemStream` được đăng ký `open/update/close` đúng cách.
- [ ] Không truy cập scoped proxy từ arbitrary async thread mà chưa có context hợp lệ.
- [ ] Nếu dùng prototype/ThreadLocal, có quản lý cleanup và lifecycle rõ.
- [ ] Ranh giới partition không trùng/thiếu, stable qua restart cùng JobInstance.
- [ ] Có integration test với nhiều StepExecution, và một test multi-threaded step riêng.
- [ ] Đã thử kill worker giữa chunk, retry/restart, đối soát business key và nội dung đầu ra.
- [ ] Đo throughput, rollback, heap/GC, connection wait và lock sau khi đổi scope.
- [ ] Chọn số thread/partition theo năng lực DB/API thực tế, không chỉ số CPU core.

## 25. Câu hỏi tự kiểm tra

**1. Một ItemReader có @StepScope trong multi-threaded step với tám chunk threads. Có tám reader target không?**

Không mặc định. Nếu tám chunk threads cùng thuộc **một StepExecution**, chúng có thể truy cập **cùng một target** theo StepScope. Cần kiểm tra implementation reader có cho phép concurrent use và cơ chế checkpoint đúng hay không.

**2. Vì sao một prototype parser inject trực tiếp vào singleton service vẫn có thể không thread-safe?**

Vì prototype chỉ tạo instance mới khi container resolve bean. Singleton service thường được inject **một lần**, rồi giữ tham chiếu đến cùng parser qua mọi lời gọi. Dùng factory/ObjectProvider hoặc thay cách thiết kế nếu cần instance mới theo mỗi lượt xử lý.

**3. Local partitioning có 10 partition và bốn worker threads: có bao nhiêu reader @StepScope?**

Thông thường có tối đa **một scoped target reader cho mỗi StepExecution partition đã truy cập bean**, tổng có thể là 10 target qua vòng đời job, nhưng chỉ khoảng bốn partition cùng thực thi theo cấu hình executor. Số instance thực tế còn phụ thuộc lazy creation và restart; không phải luôn bốn hoặc luôn 10 ở mọi thời điểm.

**4. Có nên dùng @JobScope để chia sẻ một Map mutable giữa các partition không?**

Không nên. Các partition/threads có thể gặp giới hạn job context và tranh chấp Map; hơn nữa chia sẻ state mutable không tạo checkpoint bền vững. Hãy dùng StepExecutionContext cho input từng partition hoặc một store có giao dịch rõ ràng nếu cần tổng hợp liên partition.

**5. Tại sao hai scoped processor khác nhau vẫn có thể race?**

Vì cả hai có thể inject cùng một singleton SDK hoặc cache mutable. Phải kiểm tra object graph, không chỉ annotation trên processor.

**6. ThreadLocal có phải cách truyền ExecutionContext giữa worker threads không?**

Không. ThreadLocal gắn với thread và có thể tồn tại qua nhiều partition do thread pool tái sử dụng. ExecutionContext gắn với JobExecution/StepExecution và được framework quản lý cho checkpoint/restart.

**7. Có thể dùng CompletableFuture gọi StepScope proxy trên thread mới rồi lập tức trả kết quả của processor không?**

Không nên. Thread mới có thể không có active step context, và tác vụ bất đồng bộ có thể chưa xong khi chunk commit. Cần thiết kế lifecycle/transaction/await đúng hoặc chuyển công việc sang step/partition có quản lý.

**8. Reader per-partition đã cô lập. Vì sao vẫn có thể ghi trùng khi restart?**

Vì ranh giới partition có thể thay đổi, snapshot không ổn định hoặc writer không idempotent khi một chunk đã commit trước sự cố. Scope chỉ quản lý Java object, không bảo đảm exactly-once side effect.

**9. Khi nào singleton processor là lựa chọn tốt?**

Khi processor stateless/immutable, dependency có hợp đồng dùng đồng thời an toàn và không lưu state theo item/step. Điều này giảm chi phí tạo instance mà vẫn có thể hỗ trợ concurrency.

**10. Tăng từ bốn lên tám partition làm throughput tăng 2% nhưng heap/DB lock tăng nhiều. Có nên tiếp tục?**

Không nên tăng chỉ dựa vào số worker. Cần so SLA, correctness, rollback, thời gian restart và chi phí tài nguyên; giữ cấu hình ít phức tạp hơn nếu đã đáp ứng mục tiêu.

---

**Ghi nhớ:** Trong Spring Batch, **scope bean phải khớp với ranh giới sở hữu state**. `singleton` là một target trên mỗi ApplicationContext; `prototype` tạo mới theo lượt resolve; `@JobScope` theo JobExecution; `@StepScope` theo StepExecution — **không theo chunk thread**. Multi-threaded step có thể chia sẻ một target giữa nhiều thread, trong khi partitioning thường cho phép reader có target riêng theo partition. Chỉ chọn scope sau khi hiểu topology concurrency, lifecycle `ItemStream`, dependency dùng chung, transaction, restart và tải tài nguyên thực tế.
