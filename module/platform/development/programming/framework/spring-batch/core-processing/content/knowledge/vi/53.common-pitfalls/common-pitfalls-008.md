# Chunk quá lớn gây thiếu bộ nhớ trong Spring Batch

## 1. Bài toán và dấu hiệu nhận biết

**Chunk quá lớn gây thiếu bộ nhớ** là một lỗi thường gặp khi triển khai **Spring Batch Core Processing** trên dữ liệu lớn. Trong chunk-oriented processing, Spring Batch gom nhiều item thành một đơn vị xử lý và commit transaction. Nếu mỗi item chiếm nhiều bộ nhớ hoặc có quá nhiều item còn sống tại cùng thời điểm, JVM có thể bị tăng áp lực garbage collection (GC), giảm throughput, hết heap hoặc bị hệ điều hành kết thúc do vượt memory limit.

Ví dụ job nhập một triệu đơn hàng:

~~~text
orders.csv (1.000.000 records)
            |
            v
       ItemReader
            |
            v
       ItemProcessor
            |
            v
        ItemWriter
            |
            v
         Database
~~~

Khi dùng **chunk size = 100**, mỗi chunk chỉ xử lý khoảng 100 item trước khi ghi và commit. Nếu chuyển thành **chunk size = 100.000** nhằm giảm số lần commit, Step có thể phải giữ hàng trăm nghìn kết quả, dữ liệu phụ trợ và transaction state trước khi hoàn tất một chunk. Với object lớn, heap vài gigabyte cũng có thể không đủ.

Những triệu chứng thường gặp:

- Heap used tăng mạnh trong một chunk, giảm sau commit và GC hoặc tăng dần qua nhiều chunk.
- GC pause dài, CPU dành nhiều thời gian cho thu gom rác hơn là xử lý nghiệp vụ.
- Chunk sau xử lý chậm hơn dù số item giống các chunk trước.
- JVM báo **OutOfMemoryError: Java heap space** hoặc **GC overhead limit exceeded**.
- Container báo **OOMKilled**, đôi khi process thoát với code 137 và không có Java stack trace.
- Retry hoặc rollback trở nên chậm vì phải xử lý lại nhiều item trong một transaction lớn.
- Job bị kill trước khi kịp cập nhật metadata, để lại JobExecution có trạng thái STARTED.

Không phải mọi OOM đều do chunk size. Reader có thể tải hết file vào RAM; processor có thể giữ cache không giới hạn; JPA persistence context có thể giữ quá nhiều entity; writer có thể serialize toàn chunk thành một chuỗi JSON lớn; hoặc nhiều chunk chạy song song. Bài này tập trung vào cách **nhận diện và xử lý lỗi chunk quá lớn** nhưng cũng chỉ rõ cách phân biệt với các nguyên nhân liên quan.

## 2. Cơ chế chunk-oriented processing

Một chunk-oriented Step thường thực hiện:

1. Reader trả một item.
2. Processor biến đổi hoặc filter item theo quy tắc.
3. Spring Batch tích lũy kết quả của một nhóm item.
4. Writer nhận nhóm item để ghi.
5. ItemStream/ExecutionContext và metadata được cập nhật tại ranh giới checkpoint theo cơ chế framework.
6. Transaction được commit; Step tiếp tục chunk tiếp theo.

~~~text
Chunk #1: items 1..100
  read -> process -> write -> commit/checkpoint

Chunk #2: items 101..200
  read -> process -> write -> commit/checkpoint

Chunk #3: items 201..300
  read -> process -> write -> commit/checkpoint
~~~

Trong cấu hình Spring Batch 5+:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<RawOrder, ProcessedOrder>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .build();
~~~

Con số **100** là commit interval. Nó không có nghĩa job chỉ xử lý 100 record, cũng không bảo đảm mọi lần gọi writer luôn chứa đúng 100 kết quả: processor có thể filter, lỗi có thể dẫn đến skip hoặc retry, và chunk cuối có thể ngắn hơn.

### Vì sao chunk size làm tăng footprint?

Trước khi writer hoàn tất, Spring Batch thường phải giữ các output item của chunk; với fault-tolerant processing có thể còn các tham chiếu phục vụ retry/skip. Những object khác có thể cùng tồn tại:

- Dữ liệu đầu vào và output object graph.
- Collections lưu item, DTO trung gian và tham chiếu.
- Persistence context của JPA/Hibernate cùng snapshots phục vụ dirty checking.
- JDBC parameter buffers và batching structures.
- JSON/XML serializer buffers hoặc request bodies.
- Cache tra cứu từ processor.
- Retry context, exception và trạng thái của transaction.
- Nhiều chunk đang hoạt động trên các thread khác nhau.

Không phải implementation nào cũng giữ đồng thời tất cả những thành phần này, nhưng **commit interval lớn làm tăng lượng dữ liệu tối đa cần xử lý trong một đơn vị công việc**.

## 3. Mô hình tính bộ nhớ gần đúng

Có thể ước lượng:

\[
M_{\text{peak}} \approx M_{\text{baseline}}
+ C \times (M_{\text{input}} + M_{\text{output}} + M_{\text{overhead}})
+ M_{\text{buffers}} + M_{\text{parallel}}
\]

Trong đó:

- **C**: số item mục tiêu của chunk.
- **M_input**: bộ nhớ của item đầu vào còn được giữ.
- **M_output**: bộ nhớ của kết quả processor.
- **M_overhead**: tham chiếu, collection và state của framework.
- **M_buffers**: driver, writer, ORM, serialization và I/O.
- **M_parallel**: các chunk/task khác hoạt động đồng thời.
- **M_baseline**: Spring context, JVM, thread stacks, cache nền và object không liên quan chunk.

Đây là mô hình capacity, **không phải công thức đo heap chính xác**. Input và output đôi khi chia sẻ object, GC có thể chạy giữa các lần cấp phát và một số buffer nằm ngoài heap.

Giả sử một output object giữ payload khoảng **200 KiB**, chưa tính overhead:

| Chunk size | Chỉ riêng output payload |
|---:|---:|
| 10 | khoảng 2 MiB |
| 100 | khoảng 19,5 MiB |
| 500 | khoảng 97,7 MiB |
| 1.000 | khoảng 195,3 MiB |
| 5.000 | khoảng 976,6 MiB |

Với chunk size 5.000, gần 1 GiB chỉ dành cho payload đầu ra. Khi cộng object graph, input, ORM, serializer, thread và native memory, container 2 GiB rất dễ gặp sự cố.

**Không đo kích thước object Java chỉ bằng số byte của dòng CSV trên đĩa.** Một dòng ngắn có thể sinh nhiều String, collection và entity sau parse; JSON lớn có thể được copy thêm khi serialize.

Các công cụ như **Java Flight Recorder (JFR)**, heap dump hoặc profiler giúp đo allocation và retained size để thay thế phỏng đoán bằng số liệu.

## 4. Phân biệt các nguyên nhân sử dụng bộ nhớ lớn

| Vị trí | Vấn đề | Triệu chứng đặc trưng |
|---|---|---|
| Chunk buffer | Quá nhiều kết quả đang chờ writer | Peak tăng theo chunk size |
| ItemReader | Nạp hết file/query result vào List | Heap cao trước khi xử lý chunk đầu |
| ItemProcessor | Tạo payload lớn, nested objects, cache vô hạn | Allocation cao hoặc heap tăng xuyên chunk |
| ItemWriter | Copy toàn chunk sang JSON, byte array, batch buffer | Peak ở thời điểm ghi/serialize |
| JPA/Hibernate | Managed entities, relationships và snapshots | Old-gen và thời gian flush/commit tăng |
| JDBC driver | Fetch/batch buffer lớn | Heap/native memory tăng theo driver settings |
| Retry/skip | Nhiều item được giữ hoặc xử lý lại | Peak lúc lỗi/rollback |
| Async processor | Queue Future và pending results | Heap tăng cùng queue depth |
| Multi-threaded Step | Nhiều chunk đồng thời | Peak tăng cùng số worker |
| Logging | Payload, stack trace, async appender queue | Memory tăng cùng lượng sự kiện |

Nếu giảm chunk size nhưng heap vẫn tăng liên tục qua hàng nghìn chunk, cần tìm **tham chiếu sống lâu** thay vì chỉ tiếp tục giảm commit interval.

## 5. GC và các loại OutOfMemoryError

### Java heap space

~~~text
java.lang.OutOfMemoryError: Java heap space
~~~

Heap không đủ để cấp phát object mới. Chunk giữ nhiều DTO hoặc entity là một nguyên nhân thường gặp.

### GC overhead limit exceeded

~~~text
java.lang.OutOfMemoryError: GC overhead limit exceeded
~~~

JVM dành nhiều thời gian GC mà thu hồi rất ít. Nhiều object còn reachable, cache không được giải phóng hoặc heap quá nhỏ đều có thể góp phần.

### Direct buffer memory

~~~text
java.lang.OutOfMemoryError: Direct buffer memory
~~~

Liên quan off-heap direct buffers. Chỉ nhìn heap used có thể bỏ sót nguyên nhân. HTTP client, NIO và một số driver có thể dùng direct memory.

### OOMKilled trong container

~~~text
Reason: OOMKilled
Exit code: 137
~~~

Container vượt giới hạn bộ nhớ tính cả heap và native allocations; JVM có thể chưa kịp ghi một Java OOM exception. Cần xem memory working set/RSS và container limit, không chỉ Xmx.

### Hai mẫu đồ thị cần phân biệt

~~~text
Mẫu A: peak tăng theo chunk, có hồi phục

heap ^
     |       /\         /\         /\
     |      /  \       /  \       /  \
     |_____/    \_____/    \_____/    \____> time
            commit     commit     commit

Mẫu B: bộ nhớ giữ lại tăng xuyên chunk

heap ^
     |                           ______
     |                   _______/
     |           _______/
     |__________/______________________> time
~~~

Mẫu A gợi ý chunk/buffer; mẫu B gợi ý cache, JPA context hoặc reference sống lâu. Tuy nhiên heap có thể không giảm ngay ở commit vì GC không nhất thiết chạy tức thì; cần quan sát nhiều chu kỳ và retained objects.

## 6. Giảm chunk size: giải pháp trực tiếp

Khi peak memory chủ yếu tỷ lệ với commit interval, thử giảm từ 10.000 xuống 500 hoặc 100 item:

~~~java
.chunk(100, transactionManager)
~~~

Lợi ích:

- Ít item phải cùng tồn tại trong một chunk.
- Transaction nhỏ hơn, giảm số record phải xử lý lại sau rollback.
- Checkpoint thường xuyên hơn, giảm lượng công việc có thể phải replay khi restart.
- Writer ít có nguy cơ tạo buffer quá lớn.

Đánh đổi:

- Nhiều commit và cập nhật JobRepository hơn.
- Có thể tăng JDBC/database round-trips.
- Throughput giảm nếu commit latency là bottleneck.
- Chunk quá nhỏ có thể làm chi phí per-transaction chiếm ưu thế.

Với một triệu record, số chunk xấp xỉ:

| Chunk size | Số chunk |
|---:|---:|
| 10 | 100.000 |
| 100 | 10.000 |
| 500 | 2.000 |
| 1.000 | 1.000 |
| 10.000 | 100 |

Không có chunk size “chuẩn” cho mọi hệ thống. Nên tìm điểm cân bằng giữa **peak heap, throughput, commit latency, rollback cost và headroom** bằng benchmark.

## 7. Ví dụ Step xử lý đơn hàng với chunk có giới hạn

Ví dụ sau sử dụng Spring Batch 5+, đọc file CSV theo dòng, biến đổi sang DTO nhỏ và ghi database. Nó minh họa việc không nạp toàn bộ input vào một collection.

### 7.1. Định nghĩa dữ liệu

~~~java
import java.math.BigDecimal;

public record RawOrder(
        String orderId,
        String customerId,
        BigDecimal amount) {
}

public record ProcessedOrder(
        String orderId,
        String customerId,
        BigDecimal netAmount) {
}
~~~

DTO không giữ raw line, binary attachment hoặc toàn bộ API response khi không cần. Nếu record có payload hàng megabyte, nên cân nhắc truyền object-storage reference và chỉ tải nội dung ở phần thực sự cần xử lý.

### 7.2. FlatFileItemReader có checkpoint

~~~java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;

@Bean
@StepScope
public FlatFileItemReader<RawOrder> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<RawOrder>()
            .name("importOrderReader")
            .resource(new FileSystemResource(inputFile))
            .linesToSkip(1)
            .delimited()
            .names("orderId", "customerId", "amount")
            .fieldSetMapper(fields -> new RawOrder(
                    fields.readString("orderId"),
                    fields.readString("customerId"),
                    fields.readBigDecimal("amount")))
            .saveState(true)
            .build();
}
~~~

Reader trả từng record thay vì đọc toàn file. Cấu hình **saveState(true)** giúp reader lưu trạng thái khi Step checkpoint. **@StepScope** giải quyết inputFile khi Step thực thi và tránh dùng chung instance reader stateful giữa các execution.

### 7.3. Processor không giữ toàn bộ item

~~~java
import java.math.BigDecimal;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.context.annotation.Bean;

@Bean
public ItemProcessor<RawOrder, ProcessedOrder> orderProcessor() {
    return order -> {
        BigDecimal netAmount = order.amount()
                .multiply(new BigDecimal("0.95"));

        return new ProcessedOrder(
                order.orderId(),
                order.customerId(),
                netAmount);
    };
}
~~~

Processor không thêm mỗi item vào một List hoặc Map sống đến cuối job. Nếu cần lookup cache, phải có chính sách giới hạn kích thước và eviction.

### 7.4. JDBC batch writer

~~~java
import javax.sql.DataSource;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.context.annotation.Bean;

@Bean
public JdbcBatchItemWriter<ProcessedOrder> orderWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<ProcessedOrder>()
            .dataSource(dataSource)
            .sql("""
                 INSERT INTO processed_order
                     (order_id, customer_id, net_amount)
                 VALUES (:orderId, :customerId, :netAmount)
                 """)
            .itemSqlParameterSourceProvider(item -> {
                var params = new org.springframework.jdbc.core
                        .namedparam.MapSqlParameterSource();
                params.addValue("orderId", item.orderId());
                params.addValue("customerId", item.customerId());
                params.addValue("netAmount", item.netAmount());
                return params;
            })
            .build();
}
~~~

Đoạn này dùng MapSqlParameterSource để ánh xạ rõ accessor của Java record. Với các domain JavaBean thông thường, có thể dùng **beanMapped()** nếu tương thích. Writer JDBC cần cùng DataSource/transaction manager thích hợp để tham gia transaction của Step.

Schema minh họa:

~~~sql
CREATE TABLE processed_order (
    order_id    VARCHAR(64) PRIMARY KEY,
    customer_id VARCHAR(64) NOT NULL,
    net_amount  DECIMAL(18, 2) NOT NULL
);
~~~

Lệnh INSERT thuần chỉ minh họa cách ghi theo chunk. Với job có restart/retry và khả năng replay, cần chiến lược idempotent hoặc upsert được kiểm soát theo business key.

### 7.5. Cấu hình Step và Job

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        FlatFileItemReader<RawOrder> orderReader,
        ItemProcessor<RawOrder, ProcessedOrder> orderProcessor,
        JdbcBatchItemWriter<ProcessedOrder> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<RawOrder, ProcessedOrder>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}

@Bean
public Job importOrdersJob(
        JobRepository jobRepository,
        Step importOrdersStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .start(importOrdersStep)
            .build();
}
~~~

Những @Bean method cần đặt trong class @Configuration với Batch infrastructure đã được cấu hình. Đây là ví dụ về **giới hạn số item/chunk**, không phải lời hứa rằng chunk size 100 luôn phù hợp với mọi payload.

## 8. Reader phải thực sự streaming

Một lỗi phổ biến là dùng chunk nhỏ nhưng Reader đã nạp toàn bộ input vào bộ nhớ:

~~~java
// Phản mẫu cho file lớn:
List<RawOrder> allOrders;
try (var lines = Files.lines(path)) {
    allOrders = lines.skip(1)
            .map(this::parse)
            .toList();
}

return new ListItemReader<>(allOrders);
~~~

Khi trả item đầu tiên, List chứa mọi record đã tồn tại trên heap. Với vài triệu record, **chunk(10)** vẫn không giúp vì source collection tiếp tục giữ toàn bộ input.

Các hướng phù hợp:

| Nguồn | Reader/chiến lược |
|---|---|
| CSV/text | FlatFileItemReader theo dòng |
| Database | JdbcCursorItemReader hoặc JdbcPagingItemReader |
| JPA | JpaPagingItemReader và cấu hình page size |
| XML lớn | StAX/streaming item reader |
| JSON lớn | Streaming parser theo record, tránh readTree toàn file |
| Object storage | Streaming download/range hoặc artifact staging có kiểm soát |
| Message/queue | Tiêu thụ có backpressure, checkpoint theo contract |

### Chunk size khác page size và fetch size

**Chunk size** điều khiển commit interval. **Page size** điều khiển số item reader lấy ở mỗi page. **Fetch size** thường là gợi ý với JDBC driver về số row fetch. Ba tham số tác động các tầng bộ nhớ khác nhau.

Ví dụ paging reader (queryProvider được cấu hình cho database):

~~~java
JdbcPagingItemReader<RawOrder> reader =
        new JdbcPagingItemReaderBuilder<RawOrder>()
            .name("pagedOrdersReader")
            .dataSource(dataSource)
            .pageSize(200)
            .queryProvider(queryProvider)
            .rowMapper((rs, rowNum) -> new RawOrder(
                    rs.getString("order_id"),
                    rs.getString("customer_id"),
                    rs.getBigDecimal("amount")))
            .saveState(true)
            .build();
~~~

Đây là snippet cấu hình, cần bổ sung imports và queryProvider có sort key phù hợp. Khi dữ liệu nguồn có thể thay đổi trong lúc job chạy, cần snapshot hoặc watermark; page size nhỏ **không tự bảo đảm** không thiếu/trùng record.

## 9. JPA/Hibernate persistence context

JPA giữ entity được quản lý trong **persistence context** để hỗ trợ dirty checking, relationship tracking và flush. Một entity có thể kéo theo nhiều related entities hoặc snapshots, khiến memory footprint lớn hơn DTO thuần.

~~~text
JpaPagingItemReader
       |
       v
Order entity
  + Customer
  + List<OrderLine>
  + Address
       |
       v
Processor/Writer
       |
       v
Persistence context và flush/commit
~~~

Các biện pháp:

- Truy vấn projection/DTO chỉ có field cần thiết.
- Không eager-load quan hệ lớn khi Step không dùng.
- Chọn page size và chunk size theo record size thật.
- Hiểu cách JpaPagingItemReader/JpaItemWriter phiên bản đang dùng quản lý EntityManager và việc clear persistence context.
- Với custom JPA writer, dùng flush/clear ở thời điểm phù hợp trong transaction.
- Không giữ EntityManager hoặc entity graph sống qua mọi chunk nếu không cần.
- Không dùng cùng EntityManager không thread-safe cho nhiều worker thread.

Ví dụ minh họa với một EntityManager hợp lệ trong transaction:

~~~java
for (ProcessedEntity entity : batch) {
    entityManager.persist(entity);
}

entityManager.flush();
entityManager.clear();
~~~

Đây là ý tưởng cho **custom JPA writer**, không phải chỉ dẫn đặt clear trong mọi processor. Clear sẽ detach managed entities và có thể ảnh hưởng thay đổi chưa flush hoặc logic cần entity managed; cần thiết kế theo transaction của ứng dụng và kiểm tra semantics của JpaItemWriter trước khi thêm logic tương tự.

## 10. Writer tạo bản sao của chunk

Một writer có thể vô tình nhân đôi/nhân ba footprint:

~~~java
// Phản mẫu khi chunk lớn:
String body = objectMapper.writeValueAsString(
        chunk.getItems());
httpClient.send(body);
~~~

Tại thời điểm này có thể tồn tại:

1. Chunk chứa các Java objects.
2. String JSON của toàn bộ chunk.
3. Byte buffer cho request HTTP.
4. Temporary buffers do serializer/client tạo.

Nếu đối tác chỉ cho phép tối đa 100 items/request, có thể tách request:

~~~java
List<? extends ProcessedOrder> items = chunk.getItems();
int maxItemsPerRequest = 100;

for (int start = 0; start < items.size();
        start += maxItemsPerRequest) {
    int end = Math.min(start + maxItemsPerRequest, items.size());
    externalApi.sendBatch(items.subList(start, end));
}
~~~

Tách request **chỉ giới hạn kích thước từng request**, không làm Spring Batch giữ ít item trong chunk hơn. Để giảm memory peak của Step, vẫn cần giảm chunk size hoặc đổi cách xử lý dữ liệu. Nếu các HTTP request tạo side effect, phải thiết kế idempotency/reconciliation vì chúng không tự rollback cùng transaction DB.

Với JdbcBatchItemWriter, driver cũng có thể giữ parameter buffers. Cần xem các cấu hình driver cụ thể thay vì áp dụng một option batching giống nhau cho mọi database.

## 11. Retry, skip và rollback làm đỉnh bộ nhớ tăng

Fault-tolerant Step có thể retry item hoặc xử lý lại dữ liệu sau rollback:

~~~java
.faultTolerant()
.retry(TransientDataAccessException.class)
.retryLimit(3)
.skip(InvalidOrderException.class)
.skipLimit(20)
~~~

Đây là đoạn cấu hình minh họa, với các exception được định nghĩa/import ở ứng dụng. Nếu writer lỗi gần cuối chunk gồm 10.000 item, việc rollback và xử lý lại có thể tốn đáng kể CPU, memory, DB I/O. Chunk nhỏ có thể giảm phạm vi công việc phải xử lý lại, dù số commit tăng.

**OutOfMemoryError không phải lỗi nghiệp vụ có thể skip như parse error.** Khi JVM đã thiếu bộ nhớ, ngay cả logger và transaction manager có thể không còn đủ tài nguyên để hoàn tất. Không cấu hình skip/retry OOM như một item hỏng; cần sửa nguyên nhân bộ nhớ và thực hiện recovery sau sự cố.

Không dùng skip(Exception.class) hoặc retry mọi exception chỉ để job báo COMPLETED: điều đó che giấu lỗi hệ thống và có thể làm output thiếu.

## 12. Multi-threaded Step và số chunk đang hoạt động

Khi chạy nhiều chunk song song, memory peak phụ thuộc cả commit interval và concurrency:

\[
M_{\text{active chunks}} \approx
\text{concurrent chunks} \times M_{\text{per chunk}}
\]

Nếu mỗi chunk tiêu tốn khoảng 50 MiB và có tám worker active, riêng dữ liệu của các chunk đã có thể gần 400 MiB. Nếu task queue hoặc AsyncItemProcessor chứa nhiều Future, tổng footprint còn lớn hơn.

Ví dụ cấu hình executor:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Bean
public ThreadPoolTaskExecutor batchExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(16);
    executor.setThreadNamePrefix("batch-worker-");
    executor.initialize();
    return executor;
}
~~~

Step tương ứng có thể sử dụng:

~~~java
return new StepBuilder("parallelImportStep", jobRepository)
        .<RawOrder, ProcessedOrder>chunk(100, transactionManager)
        .reader(threadSafeReader)
        .processor(orderProcessor)
        .writer(threadSafeWriter)
        .taskExecutor(batchExecutor)
        .build();
~~~

Các biến threadSafeReader và threadSafeWriter đại diện cho thành phần đã được thiết kế/kiểm tra hỗ trợ concurrency. Không phải ItemReader/ItemWriter nào cũng thread-safe; cấu hình đa luồng có thể ảnh hưởng checkpoint và restart, cần xử lý riêng.

### Backpressure

Nếu reader/processor tạo object nhanh hơn writer/DB, queue có thể tăng. Cần kiểm soát:

- Số worker active và số task pending.
- Kích thước executor queue.
- Số item và **tổng bytes** in-flight.
- JDBC/HTTP batch size.
- Số partition chạy đồng thời.
- Tần suất retry và thời gian backoff.

Giới hạn chỉ theo số item có thể chưa đủ khi một vài payload lớn gấp hàng trăm lần bình thường.

## 13. Metrics và log để đo bộ nhớ

Các số đo quan trọng:

| Chỉ số | Tác dụng |
|---|---|
| JVM heap used/committed/max | Quan sát heap còn dự phòng |
| Old-gen used | Phát hiện object sống lâu |
| Allocation rate | Nhìn lượng object được tạo |
| GC pause duration/count | Đo chi phí thu gom rác |
| Direct buffer memory | Phát hiện off-heap pressure |
| Process RSS | Tổng bộ nhớ thực của process |
| Container working set/limit | Nguy cơ bị OOMKilled |
| Step/chunk duration | Biết commit interval ảnh hưởng latency thế nào |
| Read/write/skip/rollback counts | Đánh giá tiến độ và lỗi |
| DB commit latency/lock waits | Kiểm tra tác động transaction dài |

Spring Boot Actuator/Micrometer có thể xuất metrics JVM tới Prometheus, ví dụ những tên thường gặp:

~~~promql
jvm_memory_used_bytes{area="heap"}
jvm_memory_max_bytes{area="heap"}
jvm_gc_pause_seconds_count
jvm_gc_pause_seconds_sum
~~~

Tên và nhãn thực tế phụ thuộc version và registry, cần kiểm tra endpoint metrics của ứng dụng. Heap metrics chưa đủ để biết container memory usage, vì process còn có native allocations.

### Listener lấy snapshot heap sau chunk

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ChunkListener;
import org.springframework.batch.core.scope.context.ChunkContext;

public class ChunkMemoryListener implements ChunkListener {

    private static final Logger log =
            LoggerFactory.getLogger(ChunkMemoryListener.class);
    private final MemoryMXBean memory =
            ManagementFactory.getMemoryMXBean();

    @Override
    public void afterChunk(ChunkContext context) {
        MemoryUsage heap = memory.getHeapMemoryUsage();
        long usedMiB = heap.getUsed() / (1024L * 1024);
        long maxMiB = heap.getMax() / (1024L * 1024);

        log.debug(
                "event=chunk.committed stepName={} commitCount={} "
                + "heapUsedMiB={} heapMaxMiB={}",
                context.getStepContext().getStepName(),
                context.getStepContext().getStepExecution()
                        .getCommitCount(),
                usedMiB,
                maxMiB);
    }
}
~~~

Đăng ký listener với Step:

~~~java
.listener(new ChunkMemoryListener())
~~~

Snapshot **sau chunk** không chắc ghi được peak lúc writer serialize hoặc lúc nhiều task chạy đồng thời. Với benchmark, kết hợp JFR/heap profiler hoặc sampling metrics đủ mịn. Không ghi INFO cho mọi chunk trong job có hàng trăm nghìn chunk vì logging cũng tạo CPU, I/O và memory pressure.

## 14. Benchmark chọn chunk size phù hợp

Một thí nghiệm có giá trị cần giữ nguyên dataset, cấu hình DB, memory limit, JVM version và concurrency khi thay đổi chunk size.

Ví dụ kế hoạch:

| Test | Chunk size | Số worker | Mục tiêu |
|---|---:|---:|---|
| A | 50 | 1 | Baseline |
| B | 100 | 1 | Giảm overhead commit |
| C | 250 | 1 | Quan sát GC và heap |
| D | 500 | 1 | Tìm điểm throughput bão hòa |
| E | 100 | 4 | Tác động concurrency |
| F | 250 | 4 | Giới hạn in-flight |

Mỗi test cần đo:

- Thời gian job và throughput records/giây.
- Peak heap, old-gen occupancy, GC pause, allocation rate.
- RSS và container memory peak.
- Chunk p50/p95 duration, commit latency, rollback/retry.
- Độ đầy đủ/duy nhất của output sau job.

Số liệu minh họa, **không phải benchmark đã chạy**:

| Chunk | Throughput | Peak heap | GC pause |
|---:|---:|---:|---:|
| 50 | 6.000 item/s | 450 MiB | 12 s |
| 100 | 8.200 item/s | 510 MiB | 13 s |
| 250 | 9.300 item/s | 720 MiB | 17 s |
| 500 | 9.400 item/s | 1.250 MiB | 55 s |
| 1.000 | 7.100 item/s | 1.850 MiB | 110 s |

Trong kịch bản giả định này, chunk 250 có thể phù hợp hơn chunk 500 vì throughput gần tương đương nhưng headroom lớn hơn. Production cần đo trên dữ liệu đại diện, bao gồm record lớn, lỗi, retry và tải đồng thời.

**Không cần chạy tới OOM để tìm giới hạn**. Nên dừng tăng chunk khi peak heap hoặc GC pause không còn đạt mục tiêu vận hành.

## 15. JVM heap và giới hạn container

Container memory limit phải đủ cho **heap + non-heap/native memory**:

- Metaspace và code cache.
- Thread stacks.
- Direct buffers.
- JVM/GC internal memory.
- JNI hoặc thư viện nén/mã hóa.
- Memory-mapped files và các native allocations khác tùy môi trường.

Ví dụ cấu hình JVM mang tính minh họa:

~~~text
-Xms512m
-Xmx1536m
-XX:+HeapDumpOnOutOfMemoryError
-XX:HeapDumpPath=/secure-diagnostics
~~~

Nếu container chỉ được cấp 2 GiB, Xmx sát 2 GiB có thể không để đủ native headroom. Cần đo peak RSS, kiểm tra cgroup limit và cân chỉnh theo runtime thực tế. Các JVM mới còn hỗ trợ điều chỉnh heap theo tỷ lệ RAM container; behavior phụ thuộc JVM version và options.

**Heap dump có thể chứa PII, secret và toàn bộ record đang xử lý.** Chỉ ghi vào storage được bảo vệ, có dung lượng, phân quyền và retention thích hợp. Không upload tự động heap dump production lên nơi công khai để tìm lỗi.

## 16. Phân biệt chunk lớn và memory leak xuyên chunk

Một phản mẫu:

~~~java
public class LeakyProcessor
        implements ItemProcessor<RawOrder, ProcessedOrder> {

    private final List<RawOrder> seen = new ArrayList<>();

    @Override
    public ProcessedOrder process(RawOrder item) {
        seen.add(item);
        return convert(item);
    }
}
~~~

Nếu processor là singleton, List **seen** giữ mọi item trong suốt job/JVM. Dù giảm chunk từ 1.000 xuống 10, bộ nhớ vẫn tăng theo tổng số record.

Những tình huống tương tự:

- Cache Map không giới hạn và không eviction.
- Static collection để debug.
- Listener lưu toàn bộ event vào RAM.
- ThreadLocal giữ object/payload và không clear.
- Executor queue giữ nhiều Future chưa hoàn tất.
- Session/EntityManager sống quá lâu.
- Writer xây một danh sách tổng tất cả output rồi chỉ ghi cuối job.

Với leak, cần dùng heap dump/dominator tree để tìm GC root và retained size. Nếu object không còn reachable nhưng heap chưa giảm ngay, điều đó không nhất thiết là leak; hãy quan sát sau nhiều chu kỳ GC.

## 17. Phục hồi sau OOM: checkpoint và dữ liệu đã commit

Giả sử:

~~~text
Chunk 1: COMMITTED
Chunk 2: COMMITTED
Chunk 3: đang xử lý/commit
         -> OOM hoặc OOMKilled
~~~

Sau sự cố, không thể chỉ dựa vào dòng log cuối để kết luận chunk 3 đã rollback. Có thể tồn tại:

- Các chunk trước đã commit và checkpoint được lưu.
- Chunk đang chạy đã rollback trong DB.
- COMMIT đã thành công nhưng app mất phản hồi.
- Một API/Kafka/file đã có side effect ngoài transaction DB.
- Metadata JobRepository chưa kịp chuyển từ STARTED sang FAILED.

Quy trình recovery:

1. Dừng scheduler tự động chạy lại batch nếu trạng thái chưa rõ.
2. Xác định jobExecutionId, Step, resource đang ghi, memory limit và loại lỗi.
3. Xem JobRepository, checkpoint và output đã commit; xác minh worker/lock không còn hoạt động.
4. Sửa nguyên nhân gây OOM: chunk size, cache, JPA, buffer hoặc concurrency.
5. Đảm bảo input snapshot bất biến và writer có cơ chế idempotent.
6. Restart đúng JobInstance theo Spring Batch khi đủ điều kiện.
7. Đối soát output theo business keys, không chỉ count.
8. Chỉ đánh dấu output READY sau khi job và kiểm tra dữ liệu hoàn tất.

Không thêm identifying JobParameter ngẫu nhiên rồi gọi đó là restart; việc này tạo JobInstance mới, có thể đọc lại từ đầu và ghi trùng. Không tự UPDATE metadata Spring Batch trong DB production nếu chưa có runbook phục hồi được kiểm soát.

### Vì sao không catch OutOfMemoryError rồi tiếp tục?

OOM cho biết process đã thiếu tài nguyên ở mức nghiêm trọng. Transaction manager, logging, serialization và JobRepository có thể không đủ bộ nhớ để tiếp tục an toàn. Việc bắt Error rồi skip item như lỗi validation có thể dẫn tới trạng thái dữ liệu không nhất quán. Nên xử lý nguyên nhân, khởi động lại process phù hợp và phục hồi dựa trên dữ liệu bền vững.

## 18. Kiểm thử hành vi bộ nhớ và khả năng restart

Nên tách hai loại test:

**Functional integration test:** Chạy job nhỏ với Spring Batch Test, dữ liệu fixture cố định, xác nhận Job COMPLETED và số record output chính xác. Nếu có lỗi trước commit ở một chunk, restart cùng JobInstance và assert không thiếu/trùng.

**Capacity/performance test:** Chạy process hoặc container riêng với memory limit đại diện, dữ liệu lớn và record có nhiều kích thước, đo peak heap/RSS, GC, throughput và commit latency.

Ví dụ skeleton integration test:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.beans.factory.annotation.Autowired;

class ImportOrdersIT {

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void processesAllRowsWithBoundedChunks() throws Exception {
        // Context test có job, DB riêng, input fixture 1.001 record
        // và JobParameters được tạo bởi helper của test.
        JobExecution execution =
                jobLauncherTestUtils.launchJob(testParameters());

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        // Assert output chứa đúng 1.001 key riêng biệt
        // và không có missing/unexpected record.
    }
}
~~~

Đây là skeleton cần bổ sung **testParameters()**, @SpringBatchTest/@SpringBootTest, bean và fixture để chạy thực tế. Không nên đặt assertion kiểu “heap used phải đúng 123 MiB” trong unit test thông thường: GC/JIT và tải của CI làm phép đo này không ổn định.

### Kịch bản kiểm thử nên có

| Kịch bản | Điều cần chứng minh |
|---|---|
| Chunk nhỏ, input lớn | Memory ổn định và output đủ |
| Chunk tăng dần | Có đường cong throughput/peak heap |
| Item đặc biệt lớn | Không OOM hoặc có limit xử lý rõ ràng |
| Reader tải toàn bộ file | Benchmark bộc lộ retained input |
| Processor có cache | Cache không tăng vô hạn |
| JPA with relationships | Không giữ entity graph vượt khả năng |
| Writer serialize | Peak trong lúc ghi được đo |
| Retry/rollback | Không tạo replay sai hoặc memory spike kéo dài |
| Bốn worker đồng thời | Peak memory nằm trong budget |
| Failure giữa chunk | Checkpoint và idempotent restart đúng |
| OOMKilled giả lập riêng | Recovery dựa trên repository và actual output |

Không cần cố gây OOM thật trong pipeline CI hằng ngày. Nếu cần fault injection process kill hoặc ambiguous commit, thực hiện trong môi trường test riêng có kiểm soát và không dùng dữ liệu thật.

## 19. Runbook khi production bị thiếu bộ nhớ

~~~text
Spring Batch OOM / OOMKilled
             |
             v
Xác định heap hay native/container pressure
             |
             +--> Heap peak tăng theo chunk
             |      -> Giảm chunk và writer buffer
             |
             +--> Heap tăng qua nhiều chunk
             |      -> Tìm cache/retained references/JPA
             |
             +--> Heap ổn, container vượt limit
                    -> Xem direct buffers, threads, native memory
             |
             v
Kiểm tra JobRepository + checkpoint + output
             |
             v
Sửa nguyên nhân và benchmark có memory headroom
             |
             v
Restart có kiểm soát -> đối soát -> READY
~~~

Thông tin vận hành nên giữ:

~~~text
event=batch.memory.failure
jobName=importOrdersJob
jobExecutionId=8301
stepName=importOrdersStep
configuredChunkSize=10000
activeWorkers=4
jvmHeapMaxMiB=2048
containerMemoryLimitMiB=3072
failureClass=OutOfMemoryError
recoveryStatus=INVESTIGATING
~~~

Các giá trị chỉ minh họa. Không log toàn bộ payload của item hoặc raw JobParameters nhằm điều tra memory vì log/traces cũng có nguy cơ rò dữ liệu và tăng memory pressure.

### Câu hỏi chẩn đoán nhanh

| Câu hỏi | Hướng ưu tiên |
|---|---|
| Heap peak tăng tỷ lệ với chunk size? | Giảm commit interval |
| OOM trước lần writer đầu? | Xem reader và processor |
| Reader có List của toàn input? | Đổi sang streaming/paging |
| Processor có cache không giới hạn? | Giới hạn hoặc bỏ retention |
| JPA context chứa nhiều entity? | Projection, paging, quản lý flush/clear |
| Writer tạo JSON/buffer cả chunk? | Giới hạn request/batch, tránh bản sao |
| Có nhiều worker/pending Future? | Backpressure và giảm concurrency |
| Heap chưa hết nhưng pod OOMKilled? | Kiểm tra native/direct memory và cgroup |
| JobRepository còn STARTED? | Xác minh liveness, lock và recovery |
| Output có thể đã commit? | Reconcile, idempotent writer |

## 20. Những sai lầm phổ biến

**Coi chunk size là tổng số record job có thể xử lý.** Job vẫn có thể xử lý hàng triệu item qua nhiều chunk nhỏ.

**Tăng chunk để giảm commit mà không đo GC.** Chunk quá lớn có thể làm throughput giảm do GC pause, lock và rollback.

**Chỉ tăng Xmx.** Nếu code giữ toàn bộ input, tăng heap chỉ trì hoãn lỗi và có thể làm container OOMKilled.

**Giảm chunk rồi cho rằng mọi memory leak đã sửa.** Reference trong static List, cache hoặc thread pool vẫn còn.

**Lấy kích thước CSV làm kích thước Java object.** DTO, String, entity graph và serializer buffers có overhead lớn.

**Bỏ qua JPA persistence context.** Managed entities và snapshots có thể làm heap tăng qua nhiều chunk.

**Đồng nhất fetch size, page size với chunk size.** Chúng thuộc các tầng I/O và transaction khác nhau.

**Tăng số worker khi heap đã sát ngưỡng.** Nhiều chunk active làm lượng object in-flight tăng.

**Đặt retry/skip cho OOM.** Đây không phải một lỗi item thông thường; JVM có thể không đủ tài nguyên để tiếp tục an toàn.

**Dùng System.gc() ở cuối mỗi chunk.** Forced GC không thu hồi object còn reachable và có thể gây pause lớn.

**Chỉ xem JVM heap trong container.** Native/direct memory và thread stacks cũng tính vào memory limit.

**Chạy lại job bằng instance mới mà không đối soát.** Có nguy cơ duplicate, mất record hoặc lặp side effect ngoài.

**Không bảo vệ heap dump.** Dump có thể chứa dữ liệu nhạy cảm từ mọi item đang xử lý.

**Benchmark chỉ trên record nhỏ.** Một số payload rất lớn hoặc nhiều retry có thể tạo peak cao hơn happy path.

## 21. Nguyên tắc thiết kế batch có bộ nhớ ổn định

Để tránh **chunk quá lớn gây thiếu bộ nhớ** trong Spring Batch:

1. **Chọn commit interval theo kích thước item và memory budget**, không theo số dòng đơn thuần.
2. **Reader theo streaming/paging**, tránh materialize toàn bộ nguồn.
3. **Processor stateless khi có thể**, không giữ mọi item trong cache hoặc collection.
4. **Tối giản object graph**, tránh giữ raw payload, relationship hoặc DTO không cần thiết.
5. **Quản lý JPA/JDBC/HTTP buffers** ở ranh giới transaction thích hợp.
6. **Giới hạn concurrency, queue và tổng dữ liệu in-flight**.
7. **Theo dõi heap, GC, native memory, container RSS và chunk duration**.
8. **Benchmark nhiều chunk size trên workload đại diện**, chọn cấu hình còn headroom.
9. **Thiết kế checkpoint và idempotent replay** để phục hồi sau OOM/kill.
10. **Bảo vệ log và heap dump**, không dùng dữ liệu nhạy cảm làm công cụ debug tùy tiện.

Chunk size tốt không phải giá trị lớn nhất JVM chịu được trong một lần chạy may mắn. Đó là cấu hình giúp job có **throughput ổn định, transaction latency chấp nhận được, bộ nhớ dự phòng và khả năng phục hồi đúng dữ liệu** khi volume tăng hoặc xuất hiện lỗi. Khi reader, processor và writer đều giới hạn lượng dữ liệu được giữ đồng thời, Spring Batch có thể xử lý tập dữ liệu rất lớn mà không cần giữ toàn bộ dữ liệu trong heap.
