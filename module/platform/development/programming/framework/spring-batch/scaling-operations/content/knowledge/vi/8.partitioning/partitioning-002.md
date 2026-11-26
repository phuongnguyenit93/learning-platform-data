# Worker step giống nhau theo partition trong Spring Batch

## 1. Vấn đề: tại sao nhiều partition có thể dùng cùng một worker Step?

Một Job Spring Batch cần xử lý 8 triệu đơn hàng. Để rút ngắn thời gian xử lý, nhóm phát triển chia đầu vào thành tám miền khóa, cho nhiều worker xử lý đồng thời. Có cần viết tám class hoặc tám bean Step khác nhau, mỗi Step phụ trách một miền dữ liệu?

**Không.** Với mô hình partitioning của Spring Batch, ta thường định nghĩa **một worker Step có logic chung**, rồi tạo nhiều **StepExecution** của Step đó, mỗi StepExecution nhận một **ExecutionContext của partition riêng**. Nhờ vậy, tất cả worker áp dụng cùng thuật toán read–process–write, nhưng xử lý những phần dữ liệu khác nhau.

Đây là một nguyên tắc nền tảng trong module **SPRING_BATCH_SCALING_OPERATIONS**: mở rộng Spring Batch cho workload lớn bằng multi-threaded step, parallel steps, partitioning hoặc phân tán theo năng lực tài nguyên thực tế. Việc dùng cùng worker Step giúp tránh lặp code và đơn giản hóa vận hành; nhưng để scale đúng còn phải kiểm soát **phạm vi dữ liệu, thread safety, trạng thái checkpoint, retry/restart và tác dụng phụ khi xử lý lại**.

Sau bài học, bạn có thể:

- Phân biệt **Step definition**, **StepExecution** và **partition context**; giải thích tại sao một Step xử lý được nhiều partition.
- Tạo Partitioner phát các miền dữ liệu không giao nhau, cấp tham số cho worker qua ExecutionContext.
- Cấu hình một worker Step với reader **@StepScope**, processor phù hợp và writer an toàn khi retry.
- Nối worker Step với manager Step qua TaskExecutorPartitionHandler và phân biệt khi chuyển sang remote partitioning.
- Đo throughput, kiểm tra dữ liệu, xử lý restart và tránh nhầm việc dùng chung một Step với việc dùng chung một reader stateful.

## 2. Mô hình: một định nghĩa Step, nhiều lần thực thi

### 2.1. Ba khái niệm cần tách

| Khái niệm | Nó là gì? | Ví dụ |
|---|---|---|
| **Worker Step definition** | Cấu hình logic của một Step: reader, processor, writer, chunk size, transaction | Worker Step mang tên processOrdersStep |
| **Partition** | Một đơn vị công việc logic với tên và đầu vào riêng | range-0002 xử lý ID [200001, 300001) |
| **Worker StepExecution** | Một lần thực thi Step cho một partition, được JobRepository theo dõi | processOrdersStep:range-0002, với readCount, writeCount, status, ExecutionContext riêng |

Cùng một Step definition có thể được framework dùng để tạo nhiều StepExecution. **Các StepExecution không dùng chung một ExecutionContext**, dù xuất phát từ một định nghĩa Step. Vì vậy mỗi worker phải lấy dữ liệu của mình từ ngữ cảnh thực thi, không gắn cứng mã partition vào class.

Ví dụ:

~~~text
Step definition: processOrdersStep
    reader  = đọc đơn hàng trong [minId, maxIdExclusive)
    processor = chuẩn hóa đơn hàng
    writer = ghi dữ liệu đích theo business key

StepExecution processOrdersStep:range-0000
    minId = 1         maxIdExclusive = 100001

StepExecution processOrdersStep:range-0001
    minId = 100001    maxIdExclusive = 200001

StepExecution processOrdersStep:range-0002
    minId = 200001    maxIdExclusive = 300001
~~~

Ba StepExecution sử dụng cùng logic. Điểm khác biệt duy nhất có chủ đích là **giá trị partition context** và tiến độ thực thi của từng phần. Reader và các thành phần có trạng thái phải có vòng đời phù hợp để không rò trạng thái giữa các lần thực thi.

### 2.2. Luồng điều phối

~~~mermaid
flowchart TB
    J[Job] --> M[Manager Step]
    M --> P[Partitioner]
    P --> C1[ExecutionContext range-0000]
    P --> C2[ExecutionContext range-0001]
    P --> C3[ExecutionContext range-0002]
    C1 --> H[PartitionHandler]
    C2 --> H
    C3 --> H
    H --> W1[Worker StepExecution 0000]
    H --> W2[Worker StepExecution 0001]
    H --> W3[Worker StepExecution 0002]
    W1 --> L[Cùng định nghĩa processOrdersStep]
    W2 --> L
    W3 --> L
    W1 --> D[(Dữ liệu đích)]
    W2 --> D
    W3 --> D
    W1 -. trạng thái .-> R[(JobRepository)]
    W2 -. trạng thái .-> R
    W3 -. trạng thái .-> R
~~~

Luồng khái niệm gồm:

1. **Manager Step** yêu cầu phân chia công việc.
2. **Partitioner** tạo map tên partition → ExecutionContext, chẳng hạn minId và maxIdExclusive.
3. **PartitionHandler** sắp xếp thực thi các worker StepExecution bằng TaskExecutor (local) hoặc một cơ chế remote.
4. Mỗi worker dùng **cùng cấu hình Step** nhưng bind giá trị partition của mình khi mở reader/writer và thực hiện các chunk.
5. **JobRepository** lưu trạng thái của từng StepExecution để manager biết phần nào hoàn tất, lỗi hoặc cần restart.

Đừng nhầm rằng manager nhân bản nguyên một đối tượng Java Step thành N đối tượng và gửi qua mạng. **Step là định nghĩa công việc**; với remote partitioning, tiến trình worker cần có cấu hình worker Step tương thích và thực thi một StepExecution được giao theo hợp đồng của Spring Batch Integration.

## 3. Điều gì được dùng chung, điều gì bắt buộc tách riêng?

| Thành phần | Có thể dùng chung? | Lý do và giới hạn |
|---|---|---|
| Định nghĩa worker Step | **Có** | Cùng logic nghiệp vụ, cùng tên worker Step, cùng quy tắc transaction |
| Stateless ItemProcessor | **Thường có** | Nếu không có mutable state và dependency không gây data race |
| DataSource/pool | **Có, có giới hạn** | Pool được thiết kế dùng chung nhưng có max connections của cả Job |
| Cấu hình SQL và mapper bất biến | **Có** | Không bị thay đổi theo partition |
| Partition ExecutionContext | **Không** | Mỗi StepExecution có range/checkpoint riêng |
| JdbcCursorItemReader có cursor/position | **Không dùng chung instance stateful** | Cursor và read position thuộc một lượt xử lý |
| ItemWriter có buffer trạng thái | **Không mặc định** | Phải tách instance, đồng bộ hoặc chứng minh thread safety |
| Transaction/connection đang dùng | **Không chia sẻ tùy tiện** | Thuộc phạm vi transaction/thread phù hợp |
| Biến đếm tiến độ, checkpoint | **Tách riêng** | Không thể dùng một biến static để lưu tiến độ của nhiều partition |
| Output file tạm | **Tách riêng hoặc có phối hợp** | Tránh nhiều worker ghi lẫn dữ liệu và ghi đè khi retry |

**Quy tắc quan trọng:** “Một worker Step giống nhau” là **tái sử dụng cấu hình và thuật toán**. Nó không có nghĩa “mọi StepExecution cùng sửa một object stateful”.

Một cấu hình an toàn thường dùng singleton **Step bean**, singleton **stateless processor**, và reader/writer **Step-scoped** nếu chúng giữ state theo StepExecution. Ngay cả khi đã dùng @StepScope, nếu bản thân một worker Step lại dùng TaskExecutor để xử lý nhiều chunk đồng thời thì các instance reader/writer vẫn phải được kiểm tra về thread safety trong phạm vi StepExecution đó.

## 4. Thiết kế phân vùng để worker Step có thể dùng lại

### 4.1. Chọn contract đầu vào cố định

Với bảng đơn hàng có khóa long, ví dụ chia miền khóa thành các đoạn nửa mở:

~~~text
Partition A: [1,      100001)
Partition B: [100001, 200001)
Partition C: [200001, 300001)
~~~

Truy vấn chung của mọi worker:

~~~sql
SELECT id, amount_cents, source_version
FROM orders
WHERE id >= :minId
  AND id < :maxIdExclusive
ORDER BY id ASC;
~~~

Điều kiện nửa mở **[minId, maxIdExclusive)** giúp tránh giao nhau tại ranh giới. Một bản ghi ID 100001 chỉ nằm ở B, không thuộc A. Cần có index/partitioning database phù hợp để range scan không trở thành nút thắt.

Cấu hình chung không có nghĩa mọi nguồn đều dùng range ID. Với file, contract có thể là file URI; với tenant, có thể là tenantId; với bảng phân tán, có thể là shardKey hoặc bucket. Điều quan trọng là **mọi partition cung cấp dữ liệu theo cùng schema tham số**, ví dụ:

~~~text
range-0000 -> {minId=1, maxIdExclusive=100001, snapshot=...}
range-0001 -> {minId=100001, maxIdExclusive=200001, snapshot=...}
range-0002 -> {minId=200001, maxIdExclusive=300001, snapshot=...}
~~~

### 4.2. Ví dụ Partitioner tạo context đồng nhất

Mã minh họa dưới đây phù hợp phong cách Spring Batch 5. Nó nhận miền dữ liệu **[fromInclusive, toExclusive)** đã được chốt cho JobInstance và chia thành những đoạn có kích thước gần nhau. Mỗi partition có **cùng hai key** và một tên ổn định.

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;

public final class OrderRangePartitioner implements Partitioner {
    private final long fromInclusive;
    private final long toExclusive;

    public OrderRangePartitioner(long fromInclusive, long toExclusive) {
        if (fromInclusive >= toExclusive) {
            throw new IllegalArgumentException("Invalid or empty range");
        }
        this.fromInclusive = fromInclusive;
        this.toExclusive = toExclusive;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize <= 0) {
            throw new IllegalArgumentException("gridSize must be positive");
        }

        long total = Math.subtractExact(toExclusive, fromInclusive);
        int partitions = (int) Math.min(total, (long) gridSize);
        long basicSize = total / partitions;
        long remainder = total % partitions;

        Map<String, ExecutionContext> result = new LinkedHashMap<>();
        long start = fromInclusive;

        for (int index = 0; index < partitions; index++) {
            long size = basicSize + (index < remainder ? 1 : 0);
            long end = Math.addExact(start, size);

            ExecutionContext context = new ExecutionContext();
            context.putLong("minId", start);
            context.putLong("maxIdExclusive", end);
            result.put(String.format("range-%04d", index), context);

            start = end;
        }
        return result;
    }
}
~~~

Giả sử fromInclusive=1, toExclusive=1_000_001 và gridSize=4, kết quả là bốn đoạn, mỗi đoạn 250.000 giá trị ID. Tập giá trị ID có thể có lỗ hổng, nên **số ID không đồng nghĩa số hàng hoặc khối lượng công việc**; cần xem phân bố thực tế để tránh partition lệch tải.

**Giới hạn và điều kiện sử dụng:**

- Hai biên phải được xác định từ JobParameter/snapshot hoặc cấu hình bền vững liên kết với JobInstance. Nếu mỗi lần restart lại truy vấn MAX(id) rồi chia lại, các StepExecution đã hoàn tất có thể không còn khớp tập dữ liệu.
- Partition name và cách tính range phải ổn định trong những lần restart của cùng JobInstance.
- Math.subtractExact và Math.addExact chủ động báo lỗi khi số long tràn; hệ thống cần chọn miền khóa thích hợp.
- Nếu tập rỗng, ví dụ cần thiết kế rõ không tạo partition hoặc kết thúc Step không có dữ liệu; mã trên chủ động từ chối vì mục tiêu là minh họa partition của miền không rỗng.
- gridSize là **định hướng số partition** cho Partitioner, không phải lời hứa số worker đang chạy đồng thời.

### 4.3. Ngữ cảnh mỗi partition không chứa toàn bộ dữ liệu

Một ExecutionContext tốt thường chỉ chứa metadata nhỏ và có thể tuần tự hóa: minId/maxId, tenantId, file name, snapshot watermark hoặc key để tra cứu cấu hình. Không nhét hàng triệu item hoặc object không serialize được vào ExecutionContext. Kích thước context lớn làm metadata database nặng, chậm checkpoint và khó restart.

Thay vì:

~~~text
context.put("allOrders", List<OrderRow> gồm 250.000 phần tử)  // Không phù hợp
~~~

Hãy lưu ranh giới:

~~~text
context.putLong("minId", 1)
context.putLong("maxIdExclusive", 250001)
~~~

Worker tự đọc dữ liệu từ nguồn dựa trên ranh giới được giao.

## 5. Reader giống logic, dữ liệu khác nhờ @StepScope

### 5.1. Vấn đề của reader singleton có trạng thái

Giả sử toàn bộ worker dùng một singleton JdbcCursorItemReader rồi thay SQL/range bằng biến instance mutable mỗi khi partition mới bắt đầu. Trong local partitioning, nhiều StepExecution có thể cùng thao tác trên một cursor, khiến chúng đọc sai range, bỏ sót, đọc trùng hoặc gây lỗi do reader không thread-safe.

Thay thế bằng một bean reader **@StepScope**: Spring tạo một đối tượng reader theo mỗi StepExecution, còn cùng một định nghĩa factory method được tái sử dụng.

### 5.2. Ví dụ reader theo ExecutionContext

Đoạn Java sau giả định dữ liệu orders có các cột id, amount_cents, source_version; ví dụ sử dụng API quen thuộc của Spring Batch 5:

~~~java
import javax.sql.DataSource;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

public record OrderRow(long id, long amountCents, long sourceVersion) {}

@Bean
@StepScope
public JdbcCursorItemReader<OrderRow> orderReader(
        DataSource sourceDataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxIdExclusive']}") Long maxIdExclusive) {

    return new JdbcCursorItemReaderBuilder<OrderRow>()
        .name("partitionOrderReader")
        .dataSource(sourceDataSource)
        .sql("""
            SELECT id, amount_cents, source_version
            FROM orders
            WHERE id >= ? AND id < ?
            ORDER BY id ASC
            """)
        .preparedStatementSetter(ps -> {
            ps.setLong(1, minId);
            ps.setLong(2, maxIdExclusive);
        })
        .rowMapper((rs, rowNum) -> new OrderRow(
            rs.getLong("id"),
            rs.getLong("amount_cents"),
            rs.getLong("source_version")))
        .fetchSize(500)
        .saveState(true)
        .build();
}
~~~

Hai StepExecution dùng **cùng method orderReader** nhưng sẽ thấy các giá trị khác nhau:

| Worker StepExecution | minId | maxIdExclusive | Câu SQL thực thi |
|---|---:|---:|---|
| processOrdersStep:range-0000 | 1 | 250001 | id >= 1 AND id < 250001 |
| processOrdersStep:range-0001 | 250001 | 500001 | id >= 250001 AND id < 500001 |

Ở đây các điều kiện sử dụng PreparedStatement được bind, không phải nối giá trị bằng chuỗi. **@StepScope** cho phép late binding expression tới stepExecutionContext khi StepExecution bắt đầu. Bean factory trả kiểu cụ thể JdbcCursorItemReader để framework có thể nhận diện các hợp đồng ItemStream cần thiết trong cấu hình.

**saveState(true)** cho phép reader dùng cơ chế ItemStream lưu và khôi phục read position; đó không phải cơ chế tự tạo snapshot dữ liệu. Nếu nguồn orders thay đổi thứ tự hoặc bị thêm/xóa bản ghi trong range sau restart, reader có thể quan sát tập dữ liệu khác. Cần chốt snapshot, immutable workset, watermark và tính ổn định của ORDER BY theo yêu cầu nghiệp vụ.

### 5.3. Khi nào @StepScope chưa đủ?

- Reader stateful được dùng trong **một worker Step đa luồng**: một bean StepScope vẫn có thể bị nhiều thread của cùng StepExecution truy cập; phải xác minh thread safety hoặc tránh cấu hình đó.
- Reader mở connection/cursor lâu và nhiều partition chạy đồng thời: có thể nghẽn connection pool.
- SQL có ORDER BY nhưng khóa sắp xếp không duy nhất: nếu dùng paging/restart, cần khóa tie-breaker ổn định.
- Reader dựa vào mutable cache của Job khác: ngữ cảnh partition đúng nhưng tập nguồn có thể sai.

Với reader kiểu cursor thông thường, thiết kế khởi điểm đơn giản là **một luồng trên mỗi partition**, nhiều partition chạy song song.

## 6. Processor và writer: cùng thuật toán nhưng tách trạng thái đúng cách

### 6.1. Processor thuần có thể dùng chung

Ví dụ một processor xác định output chỉ từ input:

~~~java
import org.springframework.batch.item.ItemProcessor;

public record PreparedOrder(
        long orderId,
        long amountCents,
        long sourceVersion) {}

public final class OrderProcessor
        implements ItemProcessor<OrderRow, PreparedOrder> {

    @Override
    public PreparedOrder process(OrderRow input) {
        if (input.amountCents() < 0) {
            throw new IllegalArgumentException(
                "Negative amount for order " + input.id());
        }
        return new PreparedOrder(
            input.id(),
            input.amountCents(),
            input.sourceVersion());
    }
}
~~~

Nếu không giữ mutable state và các dependency cũng phù hợp, một bean OrderProcessor có thể được dùng chung. **Không** đưa biến currentPartitionTotal, lastId hay các bộ đếm không đồng bộ vào instance singleton để cập nhật trong mỗi lần process.

Nếu logic cần tham số partition, ví dụ tenantId ảnh hưởng phép chuyển đổi, tạo processor @StepScope hoặc truyền metadata bất biến qua ngữ cảnh thích hợp. Không sửa field singleton khi có StepExecution mới.

### 6.2. Writer dùng chung logic, xử lý retry bằng idempotency

Ví dụ writer ghi sang PostgreSQL đích theo business key order_id:

~~~java
import javax.sql.DataSource;

import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

@Bean
public JdbcBatchItemWriter<PreparedOrder> orderWriter(
        DataSource targetDataSource) {

    return new JdbcBatchItemWriterBuilder<PreparedOrder>()
        .dataSource(targetDataSource)
        .sql("""
            INSERT INTO target_orders (order_id, amount_cents, source_version)
            VALUES (:orderId, :amountCents, :sourceVersion)
            ON CONFLICT (order_id)
            DO UPDATE SET
                amount_cents = EXCLUDED.amount_cents,
                source_version = EXCLUDED.source_version
            WHERE target_orders.source_version <= EXCLUDED.source_version
            """)
        .itemSqlParameterSourceProvider(item ->
            new MapSqlParameterSource()
                .addValue("orderId", item.orderId())
                .addValue("amountCents", item.amountCents())
                .addValue("sourceVersion", item.sourceVersion()))
        .assertUpdates(false)
        .build();
}
~~~

**Đây là ví dụ minh họa, không phải thiết kế exactly-once hoàn chỉnh.** Bảng đích phải có unique constraint trên order_id. Cần làm rõ quy tắc xử lý hai payload khác nhau nhưng có cùng source_version; nếu cần chống dữ liệu sai, nên kiểm tra checksum hoặc version/sequence và báo xung đột. assertUpdates(false) chấp nhận row không cập nhật theo điều kiện WHERE; điều này có thể phù hợp khi bỏ qua dữ liệu nguồn cũ, nhưng phải có đối soát để không che giấu lỗi.

Nếu source, target và JobRepository không nằm trong một transaction chung, có thể xảy ra tình huống **target đã commit nhưng checkpoint chưa lưu**. Worker có thể đọc lại cùng item khi restart. Tính idempotent ở đích và phép đối soát là điều kiện thực tế để kết quả không nhân đôi.

Nếu ItemWriter chứa buffer, stream state hoặc file handle riêng, hãy tạo writer StepScope hoặc đảm bảo vòng đời riêng theo StepExecution. Không cho nhiều partition ghi cùng file tạm hoặc cùng vùng dữ liệu không có cơ chế đồng bộ.

## 7. Cấu hình một worker Step dùng cho mọi partition

Một Step với pipeline chung có thể cấu hình như sau:

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
public Step processOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        JdbcCursorItemReader<OrderRow> orderReader,
        ItemProcessor<OrderRow, PreparedOrder> orderProcessor,
        ItemWriter<PreparedOrder> orderWriter) {

    return new StepBuilder("processOrdersStep", jobRepository)
        .<OrderRow, PreparedOrder>chunk(500, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .build();
}
~~~

Đây là **một** định nghĩa Step trong cấu hình Spring. Khi chạy, framework tạo một StepExecution cho từng partition được gán. Ở ví dụ này:

- Reader là **@StepScope**, mỗi StepExecution dùng cursor/position riêng.
- Processor thuần có thể là singleton.
- Writer JDBC mẫu không giữ vị trí partition trong field; ranh giới partition do reader quyết định. Nếu writer có trạng thái mutable, phải xác minh thread safety hoặc đổi vòng đời.
- Transaction manager nên quản lý đúng resource được writer sử dụng; với nhiều datasource, cần thiết kế và kiểm chứng transaction boundaries cụ thể.
- Chunk size 500 là mốc thử nghiệm, phải benchmark và xem chi phí rollback/memory/connection.

**Không gắn TaskExecutor trực tiếp vào processOrdersStep trong ví dụ này.** Concurrency nằm ở cấp **các partition**, khiến một StepExecution có thể dùng reader stateful theo luồng tuần tự. Nếu vừa chạy nhiều partition vừa thêm multi-threaded step bên trong mỗi partition, số tác vụ đồng thời và yêu cầu thread safety thay đổi đáng kể.

### 7.1. Những thứ không được gắn vào worker Step theo cách chung

Phản ví dụ:

~~~java
public class BadReader {
    private static long currentMinId;
    private static long currentMaxId;
    private static long currentCursorPosition;
}
~~~

Đổi ba biến static trên khi partition khác bắt đầu sẽ làm vùng dữ liệu bị lẫn. Không dùng ThreadLocal để thay thế checkpoint bền vững vì thread pool có thể tái sử dụng thread và worker có thể khởi động lại ở tiến trình khác.

Tương tự, không tạo tám bean Step với SQL hard-code mỗi vùng chỉ để chạy tám partition. Khi dữ liệu phân bố lệch và cần thay đổi số partition, mô hình đó tốn chi phí duy trì và dễ có khác biệt logic không mong muốn.

## 8. Nối manager Step với worker Step bằng TaskExecutorPartitionHandler

Ở **local partitioning**, các worker StepExecution chạy trên các thread của cùng JVM. Một cấu hình tham khảo Spring Batch 5:

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.partition.PartitionHandler;
import org.springframework.batch.core.partition.support.TaskExecutorPartitionHandler;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.core.task.TaskExecutor;

@Bean("partitionExecutor")
public ThreadPoolTaskExecutor partitionExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(16);
    executor.setThreadNamePrefix("order-partition-");
    executor.initialize();
    return executor;
}

@Bean
public TaskExecutorPartitionHandler partitionHandler(
        @Qualifier("processOrdersStep") Step workerStep,
        @Qualifier("partitionExecutor") TaskExecutor executor) {

    TaskExecutorPartitionHandler handler = new TaskExecutorPartitionHandler();
    handler.setStep(workerStep);
    handler.setTaskExecutor(executor);
    handler.setGridSize(8);
    return handler;
}

@Bean
public Step managerStep(
        JobRepository jobRepository,
        Partitioner orderRangePartitioner,
        PartitionHandler partitionHandler) {

    return new StepBuilder("managerStep", jobRepository)
        .partitioner("processOrdersStep", orderRangePartitioner)
        .partitionHandler(partitionHandler)
        .build();
}
~~~

Đây là các đoạn cấu hình để minh họa **mối quan hệ giữa các bean**, chưa gồm toàn bộ Job, datasource, partitioner bean và chính sách exception. Ở ứng dụng có nhiều bean cùng kiểu, cần chỉ rõ qualifier hoặc tên bean. API và import phải được kiểm tra theo phiên bản Spring Batch/JDK/Spring Boot dự án.

**Lưu ý về khả năng thực thi và giới hạn:**

- Partitioner được yêu cầu tạo 8 partition trong ví dụ. Executor có 4 thread hoạt động đồng thời, nên số StepExecution chạy cùng lúc thường thấp hơn hoặc bằng 4, tùy trạng thái pool và workload khác.
- TaskExecutorPartitionHandler sử dụng cùng định nghĩa worker Step để chạy các StepExecution trên nhiều thread.
- Queue capacity 16 là giới hạn queue nội bộ của executor, không phải kích thước partition, commit interval hoặc connection pool.
- Một worker có thể mở reader connection và writer connection; số connection thực tế còn phụ thuộc datasource, transaction và hành vi reader/writer.
- Nếu Partitioner tạo rất nhiều partition nhỏ, JobRepository và scheduling overhead có thể tăng. Tăng gridSize không bảo đảm tăng throughput.

### 8.1. Khi chuyển sang remote partitioning

**Logic worker Step vẫn giống nhau**, nhưng nơi thực thi thay đổi:

~~~text
Local:
  Manager JVM -> TaskExecutorPartitionHandler
                 -> processOrdersStep ở nhiều thread

Remote:
  Manager JVM -> remote PartitionHandler / middleware
                 -> Worker JVM A -> processOrdersStep
                 -> Worker JVM B -> processOrdersStep
                 -> Worker JVM C -> processOrdersStep
~~~

Trong remote partitioning, phía manager cần cơ chế gửi yêu cầu xử lý partition; các tiến trình worker phải cung cấp Step cùng tên/contract và được cấu hình để lấy StepExecution/ExecutionContext theo cơ chế Spring Batch Integration áp dụng. **Không thể chỉ đổi TaskExecutorPartitionHandler thành broker rồi coi cấu hình remote đã hoàn chỉnh.** Cần hợp đồng message, request/response, JobRepository, ack/redelivery, timeout, security, correlation, tương thích version và quy trình phát hiện worker mất kết nối.

Việc logic giống nhau giúp triển khai và mở rộng đồng nhất, nhưng phải đánh giá **JobRepository dùng chung**, khả năng truy cập nguồn/đích, khả năng network partition và hành vi khi cùng yêu cầu bị gửi lại.

## 9. Phân biệt thiết kế worker Step và thiết kế partition

| Câu hỏi | Thuộc về Partitioner/manager | Thuộc về worker Step |
|---|---|---|
| Chia dữ liệu theo khóa nào? | Chọn key, phạm vi và tên partition | Nhận range/key và dùng để lọc |
| Có bao nhiêu partition? | Đặt gridSize và chiến lược phân chia | Không tự ý đổi số partition |
| Tác vụ nào chạy trước? | Điều phối, phụ thuộc giữa Step hoặc partition | Tuân thủ thứ tự xử lý trong Step khi nghiệp vụ yêu cầu |
| Mỗi item biến đổi thế nào? | Không nên chứa logic biến đổi chính | Reader, processor, writer |
| Tiến độ một partition tới đâu? | Theo dõi StepExecution/status tổng hợp | Checkpoint và bộ đếm của StepExecution đó |
| Khi worker lỗi thì sao? | Xác định chính sách restart/relaunch và trạng thái | Rollback/chịu retry, có thể phục hồi và ghi đích an toàn |
| Tăng tốc bằng cách nào? | Tăng partition/concurrency khi có headroom | Tối ưu SQL, chunk, processor, writer và giới hạn tài nguyên |

Phân chia công việc thuộc trách nhiệm manager/Partitioner; xử lý phần việc thuộc worker Step. Nếu worker tự đi quét toàn bộ bảng rồi chia ngẫu nhiên theo số thread của mình, thiết kế partition có thể bị vô hiệu: mỗi worker đọc trùng toàn bộ dữ liệu hoặc tranh cùng khóa ghi.

## 10. Thread safety và tính nhất quán khi nhiều StepExecution cùng chạy

### 10.1. Một Step definition không bảo đảm bean an toàn

Trong local partitioning, cùng một Step bean có thể được dùng để điều phối nhiều StepExecution. Những dependency singleton không có state thay đổi thường an toàn; các dependency có cursor, buffer, shared counter hoặc file handle cần tách instance hoặc đồng bộ thích hợp.

Ví dụ lỗi:

~~~java
@Component
class SharedCounterProcessor implements ItemProcessor<OrderRow, OrderRow> {
    private long processed;

    @Override
    public OrderRow process(OrderRow row) {
        processed++; // Data race và chứa tiến độ không thể restart.
        return row;
    }
}
~~~

Nếu muốn thống kê, dùng bộ đếm qua StepExecution/metric có thiết kế concurrency, hoặc gom kết quả bền vững sau khi các partition hoàn tất. Không coi một AtomicLong toàn JVM là checkpoint vì nó không phân biệt partition và mất đi khi JVM chết.

### 10.2. Chỉ một miền dữ liệu cho mỗi partition

Điều kiện cần:

~~~text
P0: [1, 250001)
P1: [250001, 500001)
P2: [500001, 750001)
P3: [750001, 1000001)
~~~

Chứng minh không giao nhau:

~~~text
P0.maxIdExclusive == P1.minId
P1.maxIdExclusive == P2.minId
P2.maxIdExclusive == P3.minId

Mỗi ID hợp lệ xuất hiện trong đúng một khoảng.
~~~

Nhưng nếu bảng có bản ghi được thêm hoặc sửa trong lúc xử lý, một khóa ID có thể nằm trong khoảng xác định mà nội dung thay đổi giữa các lần đọc. Khi nghiệp vụ đòi hỏi tập đầu vào nhất quán, cần snapshot, batch watermark, dữ liệu immutable hoặc cơ chế tương đương. Không suy ra tính nhất quán của dữ liệu chỉ từ các khoảng ID không chồng lấn.

### 10.3. Những tài nguyên dùng chung vẫn có bottleneck

Một worker Step giống nhau chạy 16 lần có thể tạo 16 reader cursor, 16 writer transaction và nhiều hoạt động log/metadata cùng lúc. Nếu database chỉ đáp ứng 8 transaction ghi hiệu quả đồng thời, tăng số worker có thể làm:

- Active connection chạm max, pending requests tăng.
- Lock wait và deadlock tăng, đặc biệt khi các partition ghi cùng bảng/index nóng.
- p95 commit tăng dù CPU ứng dụng chưa bão hòa.
- Retry storm khi nhiều partition cùng gặp timeout.
- JobRepository quá tải vì quá nhiều partition hoặc checkpoint.

Đo **throughput toàn Job** và **độ trễ/tỷ lệ lỗi theo partition**. Không chọn số worker chỉ vì máy có nhiều CPU core.

## 11. Retry và restart: mỗi partition có trạng thái riêng

### 11.1. Tại sao StepExecution riêng là bắt buộc?

Giả sử bốn partition đã chạy:

| Partition | Status | Read | Write | Giả định |
|---|---|---:|---:|---|
| range-0000 | COMPLETED | 250.000 | 250.000 | Hoàn tất |
| range-0001 | COMPLETED | 250.000 | 250.000 | Hoàn tất |
| range-0002 | FAILED | 142.500 | 142.000 | Lỗi khi đang ghi |
| range-0003 | COMPLETED | 250.000 | 250.000 | Hoàn tất |

*Bảng là dữ liệu minh họa; read/write count có thể khác vì filter/skip, và các bộ đếm phải được hiểu cùng commit/rollback.*

Nếu Job restart với cùng cấu hình và cùng tập partition ổn định, mục tiêu là **không làm lại phần đã hoàn tất một cách không cần thiết**, đồng thời phục hồi phần chưa xong theo trạng thái lưu ở JobRepository. Cách xử lý chính xác phụ thuộc status, bước không restartable, checkpoint của reader/writer, commit và cơ chế manager. Một worker khác có thể thực thi lại partition range-0002 mà không cần cache/cursor cũ trong RAM.

### 11.2. Chỉ lưu trạng thái bền vững ở đúng nơi

| Trạng thái | Vị trí thích hợp | Sai lầm cần tránh |
|---|---|---|
| minId/maxIdExclusive, snapshot token | Partition ExecutionContext, được JobRepository lưu | Đọc lại min/max mới khi restart |
| Reader position, ItemStream checkpoint | Step ExecutionContext theo policy checkpoint | Chỉ giữ biến currentIndex trong singleton |
| Step status và số commit/rollback | StepExecution/JobRepository | Dùng log cuối cùng làm nguồn sự thật |
| Dữ liệu đã ghi | Database/file/object store bền vững | Để kết quả chưa publish ở local temp không thể phục hồi |
| Tác dụng phụ đã thực thi | Unique key/idempotency record/outbox hoặc cơ chế đối soát | Cho phép API bị gọi lại mà không có nhận diện |

Cần phân biệt **retry một item/chunk** bên trong Step với **restart Job/Step** sau lỗi. Cả hai đều có thể dẫn tới việc một item được gọi xử lý nhiều lần. Trong trường hợp database đích và JobRepository nằm ở hai transaction resource, **không có bảo đảm tự động rằng đã ghi output và checkpoint được commit cùng lúc**. Idempotency và đối soát giúp giữ kết quả đúng khi lặp.

### 11.3. Cửa sổ lỗi cần thiết kế

~~~text
Tình huống A:
  worker đọc chunk -> xử lý -> lỗi trước commit
  -> transaction rollback -> chạy lại chunk theo checkpoint.

Tình huống B:
  worker ghi thành công vào database đích
  -> tiến trình chết trước khi JobRepository lưu checkpoint
  -> partition được restart và đọc lại một số bản ghi
  -> writer phải nhận biết bản ghi đã áp dụng, tránh duplicate.

Tình huống C:
  broker giao lại partition khi worker cũ vẫn đang thực thi
  -> hai attempt có thể cùng đụng dữ liệu
  -> cần cơ chế ownership/fencing và idempotency phù hợp.
~~~

B không được giải quyết chỉ bằng @StepScope; C không được giải quyết chỉ bằng cùng worker Step name. Vấn đề nằm ở **hợp đồng end-to-end** giữa điều phối, transaction, broker và hệ thống đích.

### 11.4. Thay đổi gridSize khi restart

Việc tăng worker từ 4 lên 8 không đồng nghĩa bắt buộc tạo lại tám partition khác. Nếu thay đổi **cách sinh tên và biên partition** giữa chừng, các StepExecution đã COMPLETED có thể không còn ánh xạ đúng dữ liệu mới; rủi ro đọc trùng hoặc bỏ sót sẽ tăng.

Tách hai quyết định:

- **Partition layout:** tập phần việc logic có định danh ổn định cho JobInstance.
- **Executor concurrency:** số partition được phép chạy đồng thời tại một thời điểm.

Có thể cân chỉnh concurrency trong giới hạn hỗ trợ của cơ chế điều phối mà không tự ý làm lại ranh giới partition của JobInstance đang cần restart. Trường hợp bắt buộc repartition cần quy trình migration/checkpoint/reconciliation rõ ràng.

## 12. Vì sao cùng worker Step không phải multi-threaded step?

Hai mô hình dễ nhầm nhưng có ý nghĩa khác nhau:

~~~text
A. Partitioning:
    StepExecution P0 -> reader P0 -> processor -> writer
    StepExecution P1 -> reader P1 -> processor -> writer
    StepExecution P2 -> reader P2 -> processor -> writer

B. Multi-threaded step:
    Một StepExecution
       Thread T1 -> xử lý chunk X
       Thread T2 -> xử lý chunk Y
       Thread T3 -> xử lý chunk Z
~~~

Trong A, mỗi partition có ExecutionContext và StepExecution riêng, đồng thời chạy trên nhiều worker/luồng. Trong B, các luồng có thể cùng làm việc trong **một StepExecution**; mọi thành phần stateful được chia sẻ bên trong Step phải được đánh giá thread safety đặc biệt cẩn thận, và ordering giữa chunk có thể thay đổi.

Bản thân partitioning không cần sử dụng TaskExecutor trong từng worker Step. Nếu kết hợp cả hai, hệ thống có hai tầng concurrency: **số partition đang chạy × mức concurrency bên trong mỗi worker**. Đây là quyết định kiến trúc riêng, cần benchmark và kiểm chứng restart/ordering.

## 13. Ví dụ kiểm chứng: 1 triệu đơn hàng, 4 partition, 2 worker thread

### 13.1. Thiết lập

- Snapshot dữ liệu có ID từ 1 tới 1.000.000.
- Partitioner sinh bốn đoạn [1,250001), [250001,500001), [500001,750001), [750001,1000001).
- Reader có ORDER BY id và @StepScope; chunk size 500.
- Writer sử dụng khóa order_id duy nhất và ghi idempotent theo rule nghiệp vụ.
- ThreadPoolTaskExecutor cho phép tối đa 2 partition chạy đồng thời.

Dự kiến:

~~~text
Time ----->

Thread 1: range-0000 ======= DONE    range-0002 ===== DONE
Thread 2: range-0001 ========== DONE range-0003 ======= DONE

processOrdersStep:range-0000 -> đọc và ghi ID 1..250000
processOrdersStep:range-0001 -> đọc và ghi ID 250001..500000
processOrdersStep:range-0002 -> đọc và ghi ID 500001..750000
processOrdersStep:range-0003 -> đọc và ghi ID 750001..1000000
~~~

Hình biểu thị một lịch có thể xảy ra, **không phải lời hứa về thứ tự scheduling thực tế**. range-0002 có thể chạy trước range-0003 hoặc ngược lại; kết quả phải độc lập với lịch chạy nếu dữ liệu và writer được thiết kế đúng.

### 13.2. Đo kết quả

Giả sử cùng workload được đo nhiều lần và cho kết quả minh họa:

| Concurrency | Thời gian Job | Throughput ghi | CPU app | p95 write | Ghi chú |
|---:|---:|---:|---:|---:|---|
| 1 | 40 phút | ~417 item/s | 40% | 180 ms | Baseline |
| 2 | 24 phút | ~694 item/s | 65% | 210 ms | Có lợi |
| 4 | 18 phút | ~926 item/s | 80% | 350 ms | Bắt đầu nghẽn đích |
| 8 | 19 phút | ~877 item/s | 82% | 590 ms | Scale quá mức |

*Các số trên chỉ để diễn giải cách đo, không phải benchmark hiệu năng của Spring Batch.*

Tăng concurrency từ 4 lên 8 khiến wall-clock **tệ hơn** và write latency tăng. Hãy xem connection pool, SQL batch, lock wait, commit latency và I/O của database trước khi tăng tiếp số worker.

### 13.3. Đối soát dữ liệu

Sau khi Job hoàn tất, không chỉ kiểm tra status COMPLETED:

~~~sql
-- Ví dụ kiểm tra số bản ghi thuộc tập input đã chốt.
SELECT COUNT(*) AS written
FROM target_orders
WHERE order_id BETWEEN 1 AND 1000000;

-- Kiểm tra số khóa trùng nếu hệ thống đích chưa có unique key:
SELECT order_id, COUNT(*) AS copies
FROM target_orders
WHERE order_id BETWEEN 1 AND 1000000
GROUP BY order_id
HAVING COUNT(*) > 1;
~~~

Trong production cần đối chiếu **tập source đã chốt**, không mặc định mọi ID trong miền đều hiện diện hoặc đều đủ điều kiện ghi. Kiểm tra thêm checksum, tổng amount, version và quy tắc filter/skip để phát hiện mất dữ liệu dù count bằng nhau.

## 14. Những lỗi thường gặp khi tái sử dụng worker Step

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Viết một worker Step riêng cho mỗi range | Trùng mã, khó đổi số partition, logic lệch | Một Step template + ExecutionContext |
| Singleton cursor reader dùng chung cho nhiều StepExecution | Lẫn cursor, mất hoặc lặp item | Reader @StepScope theo StepExecution |
| Chuyển min/max qua biến static | Tranh chấp state và sai partition | Late binding từ stepExecutionContext |
| Không có ORDER BY với reader dùng checkpoint theo vị trí | Restart có thể đọc tập phần tử khác | Sort key ổn định, snapshot/cutoff |
| Dùng JobScope cho state chỉ thuộc một partition | Bean có thể chia sẻ trong cùng Job | StepScope cho state của StepExecution |
| Quên filter dữ liệu theo partition | Nhiều worker cùng đọc toàn bộ nguồn | Cố định predicate/contract của reader |
| Nhiều worker ghi cùng file tạm | Ghi lẫn/ghi đè khi retry | File riêng theo partition, merge sau |
| Tăng gridSize nhưng pool/database không đủ | Queue, lock wait, timeout tăng | Đo cả Job và pool/DB |
| Thay partition name/range khi restart | Bỏ sót/lặp công việc | Giữ layout ổn định và đối soát |
| Giả định StepScope tự xử lý mọi retry | Duplicate sau commit ở hệ đích | Writer idempotent, transaction và dedupe |
| Coi remote partitioning là gửi một Step bean qua message | Worker không có định nghĩa Step tương thích | Triển khai worker Step ở worker JVM theo hợp đồng Integration |
| Bỏ qua lỗi một partition vì phần khác COMPLETED | Job kết quả thiếu dữ liệu | Theo dõi trạng thái từng partition, restart phần lỗi |

## 15. Bài thực hành: xây dựng cùng một worker Step cho nhiều partition

**Bối cảnh:** Hệ thống nhập các đơn hàng theo ID từ database nguồn sang PostgreSQL đích. Một Job cần xử lý dữ liệu trong cửa sổ đã chốt, có thể chạy đồng thời tối đa 4 partition và phải khôi phục đúng nếu worker chết giữa chừng.

**Các bước triển khai:**

1. Chốt input: fromId, toExclusive, snapshot/record version phù hợp. Không lấy giới hạn mới khi restart.
2. Viết OrderRangePartitioner trả về map tên partition và hai key minId/maxIdExclusive.
3. Viết một bean orderReader @StepScope, bind từ stepExecutionContext và truy vấn range có ORDER BY.
4. Viết OrderProcessor không chứa mutable state; nêu rõ trường hợp filter hoặc lỗi dữ liệu.
5. Viết writer có unique key và chiến lược idempotency; xác định transaction boundary của target và JobRepository.
6. Ghép một processOrdersStep với chunk size ban đầu 500; tránh thêm TaskExecutor vào worker Step.
7. Tạo managerStep và TaskExecutorPartitionHandler; bắt đầu với concurrency=2, so sánh 1/2/4 worker.
8. Đo duration, throughput, read/write/filter/skip/rollback, p95 chunk, DB wait, pool pending và skew theo partition.
9. Dừng tiến trình sau khi một phần dữ liệu đã commit, chạy restart và đối soát bản ghi.
10. Thay số worker nhưng giữ nguyên layout partition của JobInstance; kiểm tra kết quả độc lập lịch scheduling.

### 15.1. Các ca kiểm thử bắt buộc

| Ca thử | Kích thích | Tiêu chí PASS |
|---|---|---|
| Phạm vi không giao nhau | Bốn khoảng liên tiếp | Mọi ID input thuộc tối đa một partition; không có khoảng chồng lấn |
| Dùng chung Step | Bốn partition cùng tạo StepExecution | Cùng cấu hình worker Step, mỗi partition nhận context riêng |
| Đọc độc lập | Làm chậm một reader | Reader khác không bị thay đổi cursor/range |
| Ghi lặp an toàn | Chạy lại chunk đã commit | Không tạo duplicate hoặc thay đổi kết quả sai |
| Restart | Kill một worker giữa Job | Phần chưa xong được phục hồi, phần đã hoàn tất không bị xử lý sai |
| Lệch tải | Một range chứa phần lớn bản ghi | Metric cho thấy straggler; có kế hoạch chia lại ở lượt chạy phù hợp |
| Giới hạn database | Tăng concurrency 2 → 4 → 8 | Phát hiện nấc throughput bão hòa, không mặc định càng nhiều càng nhanh |
| Đổi số worker | Tăng executor thread trên một layout ổn định | Kết quả nghiệp vụ không đổi |
| Đầu vào thay đổi | Chèn đơn hàng giữa hai lần chạy | Chính sách snapshot/watermark nhận diện hoặc ngăn sai lệch |
| Version mismatch ở remote | Worker code khác manager | Từ chối/kiểm soát theo chính sách triển khai, không ghi dữ liệu sai |

### 15.2. Mẫu báo cáo kết quả

~~~text
Job            : ordersImport
Worker Step    : processOrdersStep
Partitioning   : 8 range, tên ổn định, [minId, maxIdExclusive)
Concurrency    : 4 StepExecution đang chạy tối đa
Input snapshot : snapshot-2026-11-26
Duration       : 21m30s
Read / Write   : 1.000.000 / 1.000.000
Filter / Skip  : 0 / 0
Failed parts   : 0
DB write p95   : 230ms
Restart test   : PASS (kill sau commit, replay không duplicate)
Reconciliation : COUNT + checksum + version = PASS
Bottleneck     : writer/transaction log khi concurrency > 4
~~~

Đây là số liệu mẫu minh họa, cần thay bằng kết quả đo thực tế và định nghĩa cụ thể về snapshot, throughput, checksum.

## 16. Checklist vận hành và kiến thức cần nhớ

- [ ] Mọi partition sử dụng **cùng định nghĩa worker Step**, khác biệt đầu vào nằm trong ExecutionContext.
- [ ] Có quy tắc đặt tên partition ổn định và phạm vi dữ liệu không giao nhau.
- [ ] Reader/writer có state được tạo theo **StepExecution**, thường bằng @StepScope hoặc cơ chế tương đương.
- [ ] Singleton processor không chứa mutable state ảnh hưởng kết quả của partition khác.
- [ ] Query có predicate partition, sort key và chính sách snapshot phù hợp.
- [ ] Mỗi StepExecution có checkpoint/status độc lập trong JobRepository.
- [ ] Đã kiểm tra idempotency khi side effect và checkpoint không cùng transaction.
- [ ] Đã xác định rõ concurrency ở cấp partition và ở cấp worker Step.
- [ ] Đã tính hạn mức database, connection pool, CPU, heap và broker trước khi tăng worker.
- [ ] Có metric theo partition, log tương quan StepExecution và quy trình restart/failover.
- [ ] Đã đối soát dữ liệu và thử crash trước/sau commit.
- [ ] Khi dùng remote partitioning, worker có cấu hình worker Step và version tương thích.

**Kết luận:** Worker Step “giống nhau” theo partition là **cùng thuật toán và cấu hình Step được tái sử dụng qua nhiều StepExecution**, chứ không phải một instance reader/writer stateful được chia sẻ tùy tiện. Partitioner quyết định phần việc, ExecutionContext mang đầu vào, StepScope cung cấp dependency có trạng thái riêng, còn JobRepository theo dõi tiến độ độc lập. Thiết kế này giúp mở rộng local hoặc remote partitioning linh hoạt mà vẫn giữ được điều kiện thread safety, retry/restart và tính đúng đắn khi các worker thực thi song song.

**Nguồn nên đối chiếu khi triển khai:** Spring Batch Reference Documentation về Scaling and Parallel Processing, Partitioning, JobRepository, StepExecution, ExecutionContext, StepScope và ItemStream; Spring Batch Integration documentation về remote partitioning; Spring Boot/Spring Framework documentation về bean scope, TaskExecutor và transaction; tài liệu database về isolation, SQL batching, UPSERT và unique constraint. Kiểm tra tên API, import và hành vi với phiên bản Spring Batch thực tế của dự án.
