# Memory của chunk trong Spring Batch

## 1. Mục tiêu và phạm vi

Trong Spring Batch, chunk-oriented processing cho phép xử lý hàng triệu bản ghi mà không cần giữ toàn bộ dữ liệu trong bộ nhớ. Reader lấy từng item, processor biến đổi, writer ghi theo từng nhóm và transaction commit ở các ranh giới chunk. Tuy nhiên, cấu hình `chunk(500, transactionManager)` không đồng nghĩa Java heap chỉ chứa 500 object: một item có thể là cả object graph; reader, writer, JDBC driver, Hibernate, cache, retry và các chunk xử lý đồng thời còn có bộ nhớ riêng.

Bài **Memory của chunk** thuộc chương *Performance* trong *Spring Batch Core Processing*. Mục tiêu là hiểu **đối tượng nào còn được giữ trong heap, trong bao lâu và tăng thế nào khi thay đổi chunk size**. Sau bài này, bạn có thể:

- Giải thích vòng đời item và bộ nhớ sử dụng trong một chunk.
- Ước lượng working set theo kích thước item, chunk size và concurrency.
- Nhận diện sự khác nhau giữa allocation, retention, GC pressure và memory leak.
- Tránh giữ tất cả dữ liệu trong reader, processor, writer, `ExecutionContext` hoặc persistence context.
- Chọn chunk/page/fetch size dựa trên throughput, heap, GC, transaction và restart.
- Thu thập dữ liệu với Micrometer, JFR và heap dump; xây benchmark có tải đại diện.
- Xử lý các trường hợp memory tăng do chunk lớn, nhiều worker, record bất thường hoặc native memory.

Ví dụ Java chính sử dụng **Java 17, Spring Boot 3.x và Spring Batch 5.2.x**. Spring Batch 6.x có một số thay đổi package/API, nên cần đối chiếu tài liệu đúng phiên bản khi sao chép code.

---

## 2. Chunk giữ những gì trong bộ nhớ?

Một step điển hình:

```text
Bắt đầu transaction
        │
        ▼
 ItemReader.read() ───→ Input item / object graph
        │
        ▼
ItemProcessor.process() → Output item / object graph
        │                       │
        └───────────┬───────────┘
                    ▼
          Chunk chứa các item
         cho tới ngưỡng commit
                    │
                    ▼
       ItemWriter.write(Chunk)
                    │
                    ▼
        Checkpoint / commit
                    │
                    ▼
 Các object không còn tham chiếu
   trở thành đối tượng có thể GC
                    │
                    ▼
               Chunk mới
```

Framework có chi tiết phức tạp hơn quanh retry, skip, transaction và checkpoint. Sơ đồ mô tả **vòng đời khái niệm** của dữ liệu, không phải tất cả lệnh nội bộ theo đúng thứ tự của mọi cấu hình.

### 2.1. Các nguồn tiêu thụ memory

| Nơi giữ dữ liệu | Ví dụ | Phụ thuộc chunk size? |
|---|---|---|
| Input chunk | Danh sách item được reader đọc | Thường có |
| Output chunk | Những item do processor tạo | Thường có |
| Reader buffer | Dòng CSV, JDBC fetch, trang SQL, parser XML/JSON | Có thể độc lập |
| Writer buffer | Line aggregation, JDBC batch, serialization | Thường có |
| Transaction/retry | Metadata, retry state, callback và object liên quan | Tùy cơ chế |
| JPA persistence context | Entity được quản lý, proxy và quan hệ | Tùy page/transaction |
| `ExecutionContext` | Checkpoint và dữ liệu tùy biến | Không giới hạn bởi chunk |
| Cache trong bean | `List`, `Map`, static state, listener | Không tự giới hạn |
| Concurrency | Nhiều chunk, partition, future, thread | Nhân số phần việc |

Một `Order` tham chiếu đến `Customer`, `List<OrderLine>` và nhiều chuỗi/`BigDecimal` có thể chiếm hàng chục KiB, dù ID và amount trên CSV chỉ vài chục byte. **Object graph còn reachable** quan trọng hơn shallow size của một object.

### 2.2. Vì sao memory không giảm ngay sau commit?

Kết thúc chunk chỉ khiến các object không còn được tham chiếu **đủ điều kiện** để garbage collector thu hồi. JVM có thể giữ heap đã commit để tái sử dụng; số `heapUsed` có thể giảm khi GC chạy chứ không nhất thiết ngay ở ranh giới chunk.

Nếu heap sau GC tăng liên tục qua hàng nghìn chunk, cần tìm tham chiếu giữ dữ liệu. Một số nguyên nhân:

- Reader nạp cả file thành `List<String>`.
- Processor singleton lưu item vào một collection không giới hạn.
- Writer gom bản ghi và chỉ flush ở cuối job.
- Bean `@StepScope` giữ cache qua tất cả chunk của một `StepExecution`.
- `ExecutionContext` lưu danh sách item thay vì checkpoint nhỏ.
- Hibernate/JPA giữ entity hoặc lazy-loaded graph.
- Async task/Future chưa hoàn thành giữ tham chiếu đến item.
- Queue trong executor phình to khi producer nhanh hơn consumer.

`@StepScope` có vòng đời **step**, không phải **mỗi chunk**. Chuyển một processor tích lũy dữ liệu từ singleton sang step scope chỉ rút ngắn thời gian sống của cache đến cuối step, không làm nó tự giảm giữa các commit.

---

## 3. Chunk size, commit interval và transaction

Trong Spring Batch 5.2, cấu hình chunk thường viết:

```java
@Bean
Step importStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Input> reader,
        ItemProcessor<Input, Output> processor,
        ItemWriter<Output> writer) {

    return new StepBuilder("importStep", jobRepository)
            .<Input, Output>chunk(500, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

`chunk(500, ...)` thường có nghĩa step thu thập đến 500 **input item** cho mỗi đơn vị xử lý/transaction trong cấu hình cơ bản. Không được suy luận heap sẽ bị giới hạn ở đúng 500 object. Khi processor tạo output mới, input và output có thể cùng còn sống; khi processor trả `null`, item bị filter và không gửi đến writer.

### 3.1. Ước lượng footprint

Mô hình để bắt đầu phân tích:

```text
Peak heap ≈
    heap nền của JVM/Spring
  + tổng working set của các chunk đang chạy
  + reader page/fetch buffer
  + writer batch/serialization buffer
  + ORM caches và transaction/retry state
  + các collection sống ngoài chunk
  + khoảng trống cho allocation và GC
```

Một chunk đơn giản:

```text
chunkWorkingSet ≈
    chunkSize × (retainedInputGraph + retainedOutputGraph)
  + dữ liệu trung gian còn giữ
  + buffer phụ thuộc chunk
```

Đây là **công thức ước lượng**, không phải hợp đồng nội bộ Spring Batch. Một số input/output chia sẻ object; một số buffer không thuộc riêng một chunk; peak heap còn phụ thuộc thời điểm lấy mẫu và GC.

Giả sử graph input ~8 KiB/item và output ~6 KiB/item, cùng tồn tại trước khi writer hoàn tất:

| Chunk size | Phần input + output ước lượng |
|---:|---:|
| 100 | ~1,37 MiB |
| 500 | ~6,84 MiB |
| 2.000 | ~27,34 MiB |
| 5.000 | ~68,36 MiB |

Nếu bốn chunk tương tự cùng hoạt động, chỉ riêng phần dữ liệu của chunk size 2.000 có thể gần 109 MiB, chưa tính reader, writer, JVM, cache và thread.

Với item chứa hai bản copy `byte[]` khoảng 250 KiB, chunk size 2.000 có thể giữ gần một GiB chỉ cho payload. Đây là tình huống nên stream/giảm copy hoặc chia nhỏ payload, thay vì tin rằng nâng heap là đủ.

### 3.2. Chunk nhỏ: ưu và nhược

Ưu điểm:

- Ít item được giữ đồng thời hơn.
- Transaction và lock có thể ngắn hơn.
- Checkpoint thường xuyên hơn, thuận lợi cho restart khi lỗi.
- Rollback thường liên quan ít item hơn.
- Heap spike/GC pressure có thể giảm khi item lớn.

Chi phí:

- Nhiều lần commit và cập nhật metadata hơn.
- Overhead JDBC/network/transaction tăng.
- Writer có thể không tận dụng tốt batch insert hoặc ghi theo khối.
- Throughput có thể giảm nếu khâu commit có chi phí cố định lớn.

### 3.3. Chunk lớn: ưu và nhược

Ưu điểm:

- Giảm số lần commit.
- Có thể tận dụng batch write và giảm round trip DB.
- Với item nhỏ và memory đủ, đôi khi throughput cao hơn.

Rủi ro:

- Giữ item/intermediate object lâu hơn.
- Transaction lớn, lock/undo/rollback tăng.
- Mỗi lần lỗi có thể làm phải xử lý lại nhiều dữ liệu.
- Với concurrency, peak memory tăng mạnh.
- GC pause kéo dài khi số lượng live object lớn.

**Chunk size tốt nhất là kết quả đo trên workload cụ thể.** Không có hằng số 100, 500 hoặc 1000 luôn tốt với mọi job.

---

## 4. Vị trí giữ bộ nhớ ngoài chunk: ItemReader

### 4.1. Đọc toàn bộ tệp trước khi xử lý

Ví dụ gây rủi ro với file lớn:

```java
List<String> allLines = Files.readAllLines(
        Path.of("/data/orders.csv"),
        StandardCharsets.UTF_8);

// read() lấy lần lượt phần tử từ allLines.
```

Dù step dùng `chunk(100)`, cả `allLines` vẫn được giữ trong bộ nhớ cho đến khi reference được giải phóng. File 10 triệu dòng không trở thành streaming chỉ nhờ cấu hình commit interval.

Với input CSV, ưu tiên reader theo dòng:

```java
@Bean
@StepScope
FlatFileItemReader<Order> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<Order>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .encoding(StandardCharsets.UTF_8.name())
            .strict(true)
            .linesToSkip(1)
            .delimited()
            .names("id", "amount")
            .fieldSetMapper(fs -> new Order(
                    fs.readLong("id"),
                    fs.readBigDecimal("amount")))
            .build();
}
```

Reader đọc từng dòng khi step cần; không tạo một danh sách toàn bộ file. Tuy nhiên, mỗi dòng quá lớn vẫn có thể tạo `String`/array tạm thời lớn. Một dòng JSON payload 100 MiB có thể gây spike ngay cả với chunk size 1.

### 4.2. JDBC cursor

`JdbcCursorItemReader` sử dụng `ResultSet` để đọc tuần tự. Ví dụ:

```java
@Bean
JdbcCursorItemReader<Order> jdbcReader(DataSource dataSource) {
    return new JdbcCursorItemReaderBuilder<Order>()
            .name("jdbcReader")
            .dataSource(dataSource)
            .sql("select id, amount from orders order by id")
            .rowMapper((rs, rowNum) -> new Order(
                    rs.getLong("id"),
                    rs.getBigDecimal("amount")))
            .fetchSize(500)
            .build();
}
```

`fetchSize(500)` là **hint cho JDBC driver**, không phải memory cap cứng. Một số driver cần cấu hình autocommit, transaction hoặc streaming mode riêng; nếu không, driver có thể buffer nhiều row hơn mong đợi. Quan sát heap và tài liệu JDBC driver thực tế.

Cursor có thể giữ connection lâu. Cần cân nhắc timeout, transaction, restart và thay đổi dữ liệu trong lúc đọc.

### 4.3. JDBC paging

`JdbcPagingItemReader` lấy từng trang, thường tiêu thụ memory theo kích thước page cùng object chunk:

```java
@Bean
JdbcPagingItemReader<Order> pagingReader(
        DataSource dataSource,
        PagingQueryProvider queryProvider) {
    return new JdbcPagingItemReaderBuilder<Order>()
            .name("pagingReader")
            .dataSource(dataSource)
            .queryProvider(queryProvider)
            .rowMapper((rs, n) -> new Order(
                    rs.getLong("id"),
                    rs.getBigDecimal("amount")))
            .pageSize(500)
            .build();
}
```

`PagingQueryProvider` phải có sort key ổn định để paging/restart không thiếu hoặc trùng dữ liệu ngoài dự kiến. `pageSize` và `chunkSize` là hai thiết lập riêng:

| pageSize | chunkSize | Điều nên quan sát |
|---:|---:|---|
| 100 | 100 | Trang và commit cùng kích thước |
| 1.000 | 100 | Reader giữ bao nhiêu item page sau commit? |
| 100 | 1.000 | Số lần query trong một chunk |
| 1.000 | 1.000 | Throughput và peak heap cùng thay đổi ra sao? |

Đặt pageSize lớn giảm số truy vấn nhưng làm working set lớn hơn. Không có quy tắc bắt buộc pageSize phải bằng chunkSize.

### 4.4. JPA và Hibernate

Entity JPA có thể bị giữ trong persistence context. Một trang 500 entity root với các quan hệ eager/lazy được truy cập sâu có thể kéo theo hàng nghìn hoặc hàng chục nghìn entity con.

Các hướng xử lý:

- Dùng `JpaPagingItemReader` và cấu hình page size phù hợp; đọc tài liệu về persistence context và cách reader tách entity theo page.
- Ưu tiên projection/DTO nếu chỉ cần ID, amount và vài trường.
- Tránh nạp cả collection quan hệ không dùng.
- Kiểm soát batch flush/clear theo transaction boundary của writer.
- Rà soát first-level cache và second-level cache.
- Đo object graph thực, không chỉ đếm root entities.

**Không tự gọi `entityManager.clear()` tùy tiện trong processor**: điều đó có thể detach entity mà writer cần hoặc ảnh hưởng thay đổi pending. Chỉ flush/clear theo cấu hình và transaction đã được hiểu rõ.

### 4.5. JSON, XML và dữ liệu nén

Đọc toàn bộ JSON thành `List<Map<String,Object>>` hoặc dựng DOM XML của file rất lớn có thể phá vỡ lợi ích chunk. Xem xét streaming parser, StAX/event-based reader hoặc chia file thành resource nhỏ hơn. Với GZIP, chú ý input đã giải nén có thể lớn hơn nhiều so với kích thước file nén; đừng ước lượng heap chỉ từ byte trên đĩa.

---

## 5. ItemProcessor, writer và memory retention

### 5.1. Processor tích lũy object

Một anti-pattern:

```java
@Component
public class CollectingProcessor
        implements ItemProcessor<Order, Order> {

    private final List<Order> allOrders = new ArrayList<>();

    @Override
    public Order process(Order item) {
        allOrders.add(item);
        return item;
    }
}
```

`allOrders` tăng theo tổng số record, không phụ thuộc chunk size. Nếu processor là singleton, collection còn có thể tồn tại qua nhiều JobExecution. Nếu `@StepScope`, collection vẫn được giữ tới cuối step.

Phiên bản stateless:

```java
@Bean
ItemProcessor<Order, Invoice> invoiceProcessor() {
    return order -> new Invoice(
            order.id(),
            order.amount().multiply(new BigDecimal("1.10")));
}
```

Nếu cần thống kê, giữ counter hoặc cấu trúc aggregate nhỏ. Nếu cần sort hoặc group toàn bộ dữ liệu, cân nhắc database aggregate, partition, disk-backed intermediate store hoặc external sort.

### 5.2. Writer gom output đến cuối job

Anti-pattern:

```java
public class AccumulatingWriter implements ItemWriter<Invoice> {
    private final List<Invoice> buffered = new ArrayList<>();

    @Override
    public void write(Chunk<? extends Invoice> chunk) {
        buffered.addAll(chunk.getItems());
    }

    public void finishJob() {
        // Chỉ flush toàn bộ buffered vào cuối job.
    }
}
```

Writer này khiến memory tăng theo tổng số record, dù chunk size rất nhỏ. Với `FlatFileItemWriter` hoặc `JdbcBatchItemWriter`, ưu tiên ghi theo từng chunk và kiểm tra cách flush/batch/buffer của writer thực tế.

Với file xuất lớn, có thể ghi tuần tự vào file tạm, rồi publish sau khi job hoàn tất. Với remote API, cần kiểm soát số request in-flight và retry. Không nên giữ toàn bộ output trong `StringBuilder` hoặc `ByteArrayOutputStream` tới cuối job.

### 5.3. Allocation pressure khác memory leak

Một processor tạo hàng triệu object ngắn hạn có thể làm CPU dành nhiều thời gian cho GC, dù sau mỗi GC live heap vẫn ổn định. Đó là **allocation pressure**.

Ngược lại, nếu một `List` giữ mọi item, live heap sau GC cứ tăng theo tổng item đã đọc. Đó là **retention** hoặc memory leak theo nghĩa ứng dụng giữ dữ liệu quá lâu.

| Hiện tượng | Dấu hiệu | Hướng tối ưu |
|---|---|---|
| Allocation rate cao | GC thường xuyên, object chết nhanh | Giảm copy, tránh serialize/deserialize vòng, dùng DTO gọn |
| Retention cao | Baseline sau GC tăng liên tục | Tìm GC root, cache/listener/ORM/future giữ reference |
| Spike tạm thời | Peak rất cao nhưng quay về baseline | Chọn chunk/batch nhỏ hơn, giới hạn record hoặc buffer |
| Off-heap tăng | RSS tăng nhưng Java heap không tăng tương ứng | Xem direct buffers, native libraries, stacks, driver |

Không dùng `System.gc()` sau mỗi chunk như một giải pháp chung: nó không loại bỏ những reference còn sống và có thể gây pause.

---

## 6. ExecutionContext và checkpoint

`ExecutionContext` của Spring Batch phục vụ lưu trạng thái restart: vị trí reader, khóa phân trang, offset, một số cờ hoặc tổng số nhỏ. Nó có thể được serialize và persist qua `JobRepository` khi checkpoint.

Không nên viết:

```java
// Lưu hàng trăm nghìn object vào metadata: rất tốn RAM và I/O.
executionContext.put("processedRows", allRows);
```

Nên giữ checkpoint nhỏ:

```java
executionContext.putLong("lastProcessedOrderId", lastId);
executionContext.putString("businessDate", "2026-11-15");
```

Một context lớn có thể:

- Làm tăng live heap.
- Tăng thời gian serialize/deserialize.
- Tăng kích thước bảng metadata.
- Khi commit thường xuyên, chi phí ghi lại state lặp đi lặp lại.
- Tạo lỗi khi kiểu dữ liệu không còn tương thích sau deploy.

`saveState(false)` **không** phải mẹo giảm memory mặc định: tùy reader/writer, tắt lưu state có thể khiến restart không thể tiếp tục chính xác. Sửa nguyên nhân memory retention và thiết kế checkpoint nhỏ trong khi vẫn giữ semantics restart.

---

## 7. Ví dụ batch đọc và ghi theo chunk có bộ nhớ kiểm soát

Bài toán: đọc CSV đơn hàng, tạo tổng tiền mới và ghi CSV, không tích lũy tất cả record. Các bean dưới đây dùng Spring Batch 5.2.

**Input:**

```csv
id,amount
101,100.00
102,200.50
103,20.00
```

**Output:** do `BigDecimal.multiply(new BigDecimal("1.10"))` tạo:

```csv
id,total
101,110.0000
102,220.5500
103,22.0000
```

Nếu yêu cầu output chỉ có hai chữ số thập phân, hãy thêm `setScale(2, RoundingMode...)` theo hợp đồng; không giả định scale tự được chuẩn hóa.

### 7.1. Dependency

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}
```

Trong production, dùng datasource/schema metadata phù hợp; H2 chỉ là ví dụ môi trường thử nghiệm.

### 7.2. Cấu hình hoàn chỉnh

```java
package com.example.batch;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.FlatFileItemWriter;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.batch.item.file.builder.FlatFileItemWriterBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration(proxyBeanMethods = false)
public class InvoiceBatchConfig {

    public record Order(long id, BigDecimal amount) {}
    public record Invoice(long id, BigDecimal total) {}

    @Bean
    @StepScope
    public FlatFileItemReader<Order> orderReader(
            @Value("#{jobParameters['inputFile']}") String file) {
        return new FlatFileItemReaderBuilder<Order>()
                .name("orderReader")
                .resource(new FileSystemResource(file))
                .encoding(StandardCharsets.UTF_8.name())
                .strict(true)
                .linesToSkip(1)
                .delimited()
                .names("id", "amount")
                .fieldSetMapper(fs -> new Order(
                        fs.readLong("id"),
                        fs.readBigDecimal("amount")))
                .build();
    }

    @Bean
    @StepScope
    public FlatFileItemWriter<Invoice> invoiceWriter(
            @Value("#{jobParameters['outputFile']}") String file) {
        return new FlatFileItemWriterBuilder<Invoice>()
                .name("invoiceWriter")
                .resource(new FileSystemResource(file))
                .encoding(StandardCharsets.UTF_8.name())
                .headerCallback(w -> w.write("id,total"))
                .lineAggregator(invoice ->
                        invoice.id() + ","
                        + invoice.total().toPlainString())
                .shouldDeleteIfExists(true)
                .build();
    }

    @Bean
    public Step invoiceStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager,
            FlatFileItemReader<Order> orderReader,
            FlatFileItemWriter<Invoice> invoiceWriter,
            @Value("${app.batch.chunk-size:500}") int chunkSize) {

        if (chunkSize <= 0) {
            throw new IllegalArgumentException("chunkSize must be > 0");
        }

        return new StepBuilder("invoiceStep", repository)
                .<Order, Invoice>chunk(chunkSize, transactionManager)
                .reader(orderReader)
                .processor(order -> new Invoice(
                        order.id(),
                        order.amount().multiply(new BigDecimal("1.10"))))
                .writer(invoiceWriter)
                .build();
    }

    @Bean
    public Job invoiceJob(
            JobRepository repository, Step invoiceStep) {
        return new JobBuilder("invoiceJob", repository)
                .start(invoiceStep)
                .build();
    }
}
```

Trong `application.yml`:

```yaml
app:
  batch:
    chunk-size: 500

spring:
  batch:
    job:
      enabled: false
```

Giải thích về bộ nhớ:

- Reader đọc từng dòng CSV; không giữ toàn bộ file.
- Processor tạo một `Invoice` cho mỗi `Order` mà không lưu chúng vào list sống dài hạn.
- Writer ghi chunk ra file, thay vì gom tất cả item tới cuối job.
- `chunk-size` được cấu hình để benchmark mà không sửa logic.
- `@StepScope` chọn resource theo `JobParameters` lúc step chạy.
- Mỗi object đầu vào/đầu ra nhỏ và không có graph quan hệ không cần thiết.

`shouldDeleteIfExists(true)` phù hợp minh họa output của một lượt chạy mới; cần thiết kế riêng khi job restart, append hoặc phát hành file cuối cùng. Nó không tự bảo đảm tính nguyên tử giữa file và database transaction.

### 7.3. Chạy job

```java
JobParameters params = new JobParametersBuilder()
        .addString("inputFile", "/data/orders.csv")
        .addString("outputFile", "/data/invoices.csv")
        .addString("runId", UUID.randomUUID().toString())
        .toJobParameters();

JobExecution execution = jobLauncher.run(invoiceJob, params);
```

`runId` ngẫu nhiên trong đoạn minh họa giúp tạo các JobInstance khác nhau cho benchmark. Với production, các identifying parameters nên được thiết kế theo business key như `businessDate` để tránh chạy trùng dữ liệu.

---

## 8. Concurrency nhân working set

Một chunk đơn luồng với 500 item có thể phù hợp heap 512 MiB, nhưng 16 chunk đồng thời có thể vượt giới hạn. Phải quan sát:

- Số task/worker đang chạy cùng thời điểm.
- Số chunk in-flight.
- Reader page, transaction và persistence context của từng worker.
- Writer/driver buffers và connection pool.
- Executor queue giữ task hoặc `Future`.
- Các job khác chạy cùng JVM.

### 8.1. Ước lượng

Giả sử mỗi item pair giữ 12 KiB:

```text
chunkSize = 2000

1 chunk  ≈ 2000 × 12 KiB = 23,4 MiB
4 chunks ≈ 93,8 MiB
8 chunks ≈ 187,5 MiB
16 chunks ≈ 375 MiB
```

Số liệu chỉ tính item graph theo giả định. Nếu JVM đã dùng 400 MiB ở baseline và còn reader/ORM buffer, 16 chunk cùng lúc có thể khiến một heap 1 GiB không đủ headroom.

### 8.2. Multi-threaded step

Ví dụ cấu hình task executor với Spring Batch 5.2:

```java
@Bean
TaskExecutor batchTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(0);
    executor.setThreadNamePrefix("batch-");
    executor.initialize();
    return executor;
}

@Bean
Step parallelStep(
        JobRepository repository,
        PlatformTransactionManager manager,
        ItemReader<Input> reader,
        ItemProcessor<Input, Output> processor,
        ItemWriter<Output> writer,
        TaskExecutor batchTaskExecutor) {

    return new StepBuilder("parallelStep", repository)
            .<Input, Output>chunk(500, manager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .taskExecutor(batchTaskExecutor)
            .build();
}
```

Đây là ví dụ cấu hình, chưa phải một step hoàn chỉnh để chạy vì các kiểu `Input`, `Output` và bean liên quan cần được định nghĩa. **Cần xác nhận reader/writer thread-safe.** Không phải mọi reader Spring Batch an toàn khi nhiều worker cùng dùng một instance. Wrapper đồng bộ hoặc partition với reader riêng có thể cần thiết, tùy yêu cầu.

Một executor không có queue lớn có thể giảm backlog nhưng còn cần cấu hình rejection policy, độ song song hiệu dụng và chính sách điều phối. Số thread cũng dùng stack và có thể tạo kết nối DB riêng.

### 8.3. Partition và remote worker

Partitioning thường tạo `StepExecution`/reader state độc lập theo partition. Khi tám partition chạy cùng JVM, phải tính tổng footprint của cả tám; khi chạy trên nhiều JVM, áp memory limit riêng trên từng worker, nhưng tổng áp lực DB/storage/network vẫn cộng dồn.

### 8.4. Async processor

Trong thiết kế async, các `Future`/task chưa hoàn thành có thể giữ input graph. Nếu producer nhanh hơn writer, queue/future backlog tăng không giới hạn dù chunk nhỏ. Cần giới hạn in-flight tasks, queue capacity, timeout, backpressure và số kết quả đợi theo thứ tự.

---

## 9. JVM heap và container memory

Không phải mọi bộ nhớ đều nằm trong Java heap.

| Loại bộ nhớ | Ví dụ | Thuộc Java heap? |
|---|---|---|
| Heap | Item, chunk, DTO, cache, persistence context | Có |
| Metaspace | Class metadata | Không |
| Thread stacks | Stack của worker/GC threads | Không |
| Direct/off-heap | NIO buffers, một số driver/client | Không |
| JVM native/JIT | Code cache, GC internals, native library | Không |
| OS/file cache | Cache filesystem, mapping | Không thuộc heap; có thể ảnh hưởng memory của container |

Với container limit 2 GiB, đặt `-Xmx2g` có thể khiến container bị OOMKilled vì native memory vẫn cần chỗ. Một ví dụ chính sách heap:

```text
JAVA_TOOL_OPTIONS="-Xms256m -Xmx1024m"
```

Hoặc theo tỷ lệ memory được JVM nhận diện:

```text
JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=60.0"
```

Các giá trị là ví dụ; cần đo phần ngoài heap, số thread, direct buffer và workload trước khi quyết định.

Phân biệt triệu chứng:

- `OutOfMemoryError: Java heap space`: thiếu Java heap.
- `OutOfMemoryError: Direct buffer memory`: cạn giới hạn direct buffer.
- `GC overhead limit exceeded`: GC làm quá nhiều việc mà thu hồi ít, phụ thuộc JDK/GC.
- Kubernetes `OOMKilled`/exit code thường là 137: kernel/container kill do vượt giới hạn, có thể không có stack trace Java.

Nếu RSS tăng nhưng heap used ổn định, cần điều tra direct/native/thread memory chứ không chỉ giảm chunk size.

---

## 10. Đo lường thay vì đoán

### 10.1. Metric cần thu thập

| Chỉ số | Mục đích |
|---|---|
| Heap used, committed, max | Mức heap đang sử dụng và giới hạn |
| Live heap sau GC | Phát hiện dữ liệu được giữ lâu |
| Allocation rate | Phát hiện tạo object quá nhanh |
| GC count, pause, CPU | Hiểu độ trễ do collector |
| Container RSS / working set | Theo dõi giới hạn memory thực |
| Chunk duration | Phát hiện chunk lớn/chậm bất thường |
| Read/write/filter/skip count | Kiểm tra tiến triển xử lý |
| Throughput items/s | Đánh giá hiệu quả tổng thể |
| JDBC batch/query time | Tách chi phí DB khỏi Java |
| Object retained graph | Tìm reference gây leak |

### 10.2. Logging heap sau mỗi chunk

Ví dụ listener cho Spring Batch 5.x:

```java
package com.example.batch.monitoring;

import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ChunkListener;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.scope.context.ChunkContext;

public class ChunkHeapLogger implements ChunkListener {

    private static final Logger log =
            LoggerFactory.getLogger(ChunkHeapLogger.class);

    private static final long MIB = 1024L * 1024L;

    private final MemoryMXBean memoryBean =
            ManagementFactory.getMemoryMXBean();

    @Override
    public void afterChunk(ChunkContext context) {
        StepExecution step =
                context.getStepContext().getStepExecution();

        MemoryUsage heap = memoryBean.getHeapMemoryUsage();

        log.info(
                "step={} read={} write={} heapUsedMiB={} "
                + "heapCommittedMiB={} heapMaxMiB={}",
                step.getStepName(),
                step.getReadCount(),
                step.getWriteCount(),
                heap.getUsed() / MIB,
                heap.getCommitted() / MIB,
                heap.getMax() < 0 ? "unknown"
                        : String.valueOf(heap.getMax() / MIB));
    }
}
```

Đăng ký listener trong builder:

```java
return new StepBuilder("invoiceStep", repository)
        .<Order, Invoice>chunk(chunkSize, transactionManager)
        .reader(orderReader)
        .processor(invoiceProcessor)
        .writer(invoiceWriter)
        .listener(new ChunkHeapLogger())
        .build();
```

Snapshot sau chunk **không phải** phép đo chính xác peak memory của chunk: object tạm thời có thể đã được thu hồi, heap used còn chứa object đã chết nhưng chưa GC, và off-heap không được đo. Khi có hàng triệu chunk, tránh log mọi chunk vì logging tạo overhead; lấy mẫu định kỳ hoặc metric aggregate.

### 10.3. Micrometer/Actuator

Dependency minh họa:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

Một số Prometheus series JVM thường gặp:

```promql
jvm_memory_used_bytes{area="heap"}
jvm_memory_committed_bytes{area="heap"}
jvm_memory_max_bytes{area="heap"}
rate(jvm_gc_pause_seconds_sum[5m])
process_resident_memory_bytes
```

Tên và label cụ thể thay đổi theo registry/phiên bản; cần quan sát endpoint metrics thực sự. Spring Batch metrics cung cấp thời gian job/step/item/chunk, nhưng không tự đo retained bytes chính xác cho mỗi chunk.

Không dùng `jobExecutionId` hoặc ID từng item làm tag cho mọi metric vì cardinality có thể tăng rất lớn; dùng tên job/step, environment và các tag ổn định.

### 10.4. Java Flight Recorder

JFR giúp phân tích allocation hotspot, GC, thread, lock và I/O:

```text
java -XX:StartFlightRecording=filename=/tmp/batch-memory.jfr,settings=profile,duration=300s -jar app.jar
```

Hoặc trên JVM đang chạy:

```text
jcmd <pid> JFR.start name=batch-memory settings=profile duration=300s filename=/tmp/batch-memory.jfr
```

Mở recording bằng JDK Mission Control. Việc thu JFR có overhead và dùng disk; cần chọn thời gian/tải phù hợp.

### 10.5. Heap dump

```text
jcmd <pid> GC.heap_dump /tmp/batch-heap.hprof
```

Phân tích dump bằng Eclipse MAT hoặc công cụ tương đương, tìm:

- `List`/`Map` tích lũy hàng triệu item.
- Class và collection có retained size lớn.
- Paths to GC roots giữ object.
- Entity/persistence context, thread-local hoặc `Future` không được giải phóng.
- Tỷ lệ số object sau 100 chunk so với sau 10.000 chunk.

Heap dump có thể lớn, chứa dữ liệu nghiệp vụ nhạy cảm, làm JVM pause và tiêu tốn storage. Chỉ thực hiện theo quy trình vận hành phù hợp.

### 10.6. Nhận diện hình răng cưa và leak

Heap bình thường có thể tăng trong khi tạo object rồi giảm sau GC:

```text
Heap
 ▲       /|        /|        /|
 │      / |       / |       / |
 │_____/  |______/  |______/  |____
 └───────────────────────────────► time
        GC         GC         GC
```

Nếu baseline sau GC tương đối ổn định, đó có thể là allocation bình thường. Nếu baseline sau mỗi GC tăng liên tục theo số record và heap dump chỉ ra object còn được giữ, nghi ngờ retention/leak. Hãy phân biệt trường hợp warm-up/cache có giới hạn rồi ổn định với tăng không giới hạn.

---

## 11. Benchmark chunk size một cách có hệ thống

Một quy trình đo thực tế:

1. Chuẩn bị input đủ lớn và đại diện: record trung bình, record lớn, dữ liệu lỗi, quan hệ JPA, độ trễ DB.
2. Cố định heap, số thread, JVM/GC, database, index, logic processor/writer và workload khác.
3. Thử các chunk size như 50, 250, 500, 1000, 2000, tùy kích thước item.
4. Đo tổng thời gian, items/s, peak heap, live heap sau GC, GC pause và p95 chunk duration.
5. Chạy lặp để giảm ảnh hưởng cache, JIT, cold start và tải nền.
6. Thử lại với concurrency thực tế, lỗi writer/retry và input có item lớn.
7. Chọn giá trị đạt SLA, throughput chấp nhận được và còn đủ headroom.

Bảng kết quả mẫu để điền số đo thật:

| Chunk | Workers | Items/s | Peak heap | GC pause/ phút | p95 chunk duration | Total time |
|---:|---:|---:|---:|---:|---:|---:|
| 50 | 1 | Đo | Đo | Đo | Đo | Đo |
| 250 | 1 | Đo | Đo | Đo | Đo | Đo |
| 500 | 1 | Đo | Đo | Đo | Đo | Đo |
| 1000 | 1 | Đo | Đo | Đo | Đo | Đo |
| 2000 | 1 | Đo | Đo | Đo | Đo | Đo |
| 500 | 4 | Đo | Đo | Đo | Đo | Đo |

Không suy luận từ file vài trăm dòng ra workload hàng triệu bản ghi. Một lỗi giữ reference có thể chỉ rõ khi chạy đủ số chunk.

### 11.1. Phân tích trade-off

Nếu tăng chunk từ 250 lên 1000 giúp throughput tăng 8% nhưng peak heap tăng gấp ba và pause GC vượt SLA, cấu hình lớn hơn chưa chắc tối ưu. Nếu giảm chunk xuống 50 khiến commit/DB roundtrip tăng mạnh, cũng không nên dùng chỉ vì heap thấp nhất.

### 11.2. Test đường đi lỗi

Cần bổ sung tình huống:

- Reader đọc record cực lớn.
- Processor throw exception ở cuối chunk.
- Writer fail, rollback và retry.
- Source I/O hoặc DB chậm.
- Input chỉ gồm item bị filter.
- Job restart sau checkpoint.
- Nhiều partition/job chạy đồng thời.
- Container memory limit tương đương production.

Đường đi lỗi có thể tạo object/stack trace, retry buffer và thời gian giữ dữ liệu khác với đường đi thành công.

---

## 12. Restart và fault tolerance tác động memory

### 12.1. Checkpoint

Chunk size ảnh hưởng khoảng cách giữa các checkpoint. Chunk lớn hơn có thể khiến nhiều item phải được xử lý lại sau crash; chunk nhỏ hơn tạo nhiều commit và metadata update.

Restart chính xác phụ thuộc `ItemStream`, `ExecutionContext`, transaction và output idempotency. Không thể kết luận giảm chunk size luôn đủ bảo đảm restart.

### 12.2. Retry và skip

Fault-tolerant step có thể giữ hoặc đọc lại item khi retry/skip. Nếu lỗi xuất hiện gần cuối chunk lớn, áp lực memory và rollback có thể cao hơn bình thường. Giới hạn retry/skip phù hợp, tránh retry vô hạn dữ liệu format sai.

Nếu skip listener lưu mọi item lỗi:

```java
public class RetainingSkipListener
        implements SkipListener<Order, Invoice> {

    private final List<Order> skipped = new ArrayList<>();

    @Override
    public void onSkipInProcess(Order item, Throwable error) {
        skipped.add(item); // Có thể tăng không giới hạn.
    }
}
```

Thay vào đó, lưu thống kê hoặc ghi record lỗi vào storage bên ngoài với chính sách transaction/idempotency rõ. Không giữ toàn bộ error payload/stack trace trong một collection tới cuối job.

### 12.3. Không tối ưu memory bằng cách bỏ restart tùy tiện

`saveState(false)` có thể giảm một phần overhead nhưng thường không giải quyết nguyên nhân OOM do item giữ trong heap và có thể làm mất khả năng restart theo checkpoint. Chỉ thay đổi khi job được thiết kế restart từ đầu hoặc có cơ chế checkpoint khác được kiểm chứng.

---

## 13. Chẩn đoán theo triệu chứng

| Dấu hiệu | Giả thuyết | Điều cần xem |
|---|---|---|
| Peak heap tăng khi chunk tăng | Item input/output giữ theo chunk | Đo peak, giảm chunk và so throughput |
| Heap tăng ngay sau open reader | Reader load toàn bộ dữ liệu | `readAllLines`, `queryForList`, JSON DOM, driver buffering |
| Baseline sau GC tăng theo số record | List/cache/ORM giữ object | Heap dump, GC roots |
| Memory spike ở writer | JDBC batch hoặc serialization buffer | Writer duration, driver buffer, output graph |
| GC cao nhưng baseline ổn định | Allocation rate cao | JFR allocation profile, copy chuỗi/JSON |
| Heap ổn nhưng container OOM | Native/direct memory, stacks | RSS, container memory, direct buffers |
| Chỉ OOM khi tăng threads | Concurrency × working set | In-flight chunk, queue, thread/connection counts |
| Chỉ OOM với một file nhất định | Record bất thường lớn | Max line/object size, parser, decompression |
| Retry lâu tạo memory tăng | Retry/log/listener giữ object | Fault tolerance config và error handling |
| Step scope kết thúc mới giảm memory | Bean giữ state xuyên step | Bean fields, caches, `ExecutionContext` |
| Partition tổng thể chậm khi tăng workers | DB/IO saturated hoặc GC | CPU, DB locks, latency, GC, throughput |

Một quy trình điều tra thực tế:

```text
Job memory cao
     │
     ├─ Heap hay RSS/native?
     │      ├─ Heap → GC/JFR/heap dump
     │      └─ Native → direct/stacks/driver/container
     │
     ├─ Heap tăng theo chunk hay theo tổng record?
     │      ├─ Theo chunk → chunk/item graph/buffer
     │      └─ Theo tổng record → cache/list/ORM retention
     │
     ├─ Có nhiều chunk đồng thời?
     │      └─ Giới hạn threads/partitions/queues
     │
     └─ Đo lại throughput, pause GC và headroom
```

---

## 14. Những sai lầm thường gặp

| Nhận định sai | Cách hiểu đúng |
|---|---|
| “Chunk 100 giữ tối đa 100 object” | Mỗi item là một graph; nhiều buffer và output cùng tồn tại |
| “Chunk lớn hơn chắc chắn nhanh hơn” | Throughput phải cân với GC, lock, rollback và memory |
| “Giảm chunk sửa mọi OOM” | Reader/processor/ORM có thể giữ cả tập dữ liệu |
| “`@StepScope` giải phóng state mỗi chunk” | Scope theo step execution |
| “`fetchSize` luôn là giới hạn memory” | JDBC driver có quyền quyết định cách fetch |
| “`pageSize` luôn phải bằng `chunkSize`” | Hai cơ chế độc lập cần được tune bằng số đo |
| “`ExecutionContext` dùng để lưu mọi record” | Nên chứa checkpoint nhỏ để restart |
| “Gọi `System.gc()` sẽ sửa memory leak” | GC không thu được object còn tham chiếu |
| “Heap used sau commit là peak của chunk” | Đây chỉ là snapshot ở một thời điểm |
| “Đặt `-Xmx` bằng memory limit container” | Native, direct buffers, stack vẫn cần memory |
| “Chỉ cần test job `COMPLETED`” | Cần quan sát throughput, heap, GC, output và restart |
| “Có 8 workers thì memory như một worker” | Tổng in-flight working set thường tăng theo concurrency |

---

## 15. Bài tập thực hành

### Bài 1 — Ước lượng

Một input graph trung bình 4 KiB, output graph 6 KiB, chunk size 1000 và 8 chunks đồng thời. Ước lượng memory dùng bởi input/output graph, rồi liệt kê những thành phần chưa có trong kết quả.

### Bài 2 — Benchmark chunk

Tạo input một triệu record. Chạy step với chunk size 50, 250, 500, 1000 và 2000. Thu tổng thời gian, throughput, peak heap, GC pause và p95 chunk duration. Chọn kích thước phù hợp theo số liệu.

### Bài 3 — Reader giữ toàn bộ input

So sánh reader dùng `Files.readAllLines()` với `FlatFileItemReader` trên file ngày càng lớn. Quan sát live heap trước khi bắt đầu xử lý và sau mỗi 100 chunk.

### Bài 4 — Processor leak

Viết processor cố ý lưu mọi item vào `ArrayList`. Dùng JFR/heap dump tìm đường tham chiếu giữ list; chuyển thành stateless và đo lại.

### Bài 5 — JDBC paging

Thử `pageSize=100, 500, 1000` phối hợp chunk size khác nhau. Theo dõi số SQL query, memory, DB wait và throughput. Giải thích vì sao page size và chunk size không bắt buộc bằng nhau.

### Bài 6 — Concurrency

Chạy cùng job với 1, 4, 8 workers; đo in-flight chunks, heap, RSS, throughput và connection pool. Xác định điểm tăng concurrency không còn mang lại lợi ích.

### Bài 7 — Retry và checkpoint

Cho writer lỗi cuối chunk; thử retry/rollback ở chunk size 100 và 1000. Kiểm tra output sau restart, tần suất checkpoint và chi phí bộ nhớ.

### Bài 8 — ExecutionContext

So sánh lưu 50.000 object vào `ExecutionContext` với chỉ lưu `lastProcessedId`. Quan sát kích thước context, thời gian ghi metadata và khả năng restart đúng.

### Bài 9 — Heap và container

Giới hạn heap 512 MiB, container 768 MiB; theo dõi RSS và `jvm_memory_used_bytes` khi tăng thread/driver buffer. Phân biệt Java heap OOM và process bị OOMKilled.

---

## 16. Tài liệu tham khảo

- [Spring Batch — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): vòng đời đọc/xử lý/ghi và commit.
- [Spring Batch — Commit Interval](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/commit-interval.html): cấu hình commit interval.
- [Spring Batch — Readers and Writers](https://docs.spring.io/spring-batch/reference/readers-and-writers.html): lựa chọn reader/writer.
- [Spring Batch — Database Readers and Writers](https://docs.spring.io/spring-batch/reference/readers-and-writers/database.html): JDBC cursor/paging và JPA.
- [Spring Batch — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): open/update/close và checkpoint.
- [Spring Batch — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): concurrency và partitioning.
- [Spring Batch — Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html): giám sát job/step/chunk.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer và JVM metrics.
- [Java 17 — MemoryMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html): heap usage từ JVM.
- [JDK Mission Control](https://openjdk.org/projects/jmc/): phân tích JFR.
- [Java 17 — jcmd](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): JFR và heap dump.

Memory của chunk phụ thuộc vào **tổng object graph còn được giữ trong reader, processor, writer, transaction và cache**, kết hợp với số chunk chạy đồng thời. Tối ưu hiệu quả đòi hỏi đọc theo luồng/trang, tránh tích lũy vô hạn, dùng checkpoint nhỏ và đo peak heap, GC, throughput, rollback trên dữ liệu đại diện. Chunk size là một công cụ điều chỉnh quan trọng, nhưng phải được lựa chọn cùng kiến trúc I/O và giới hạn bộ nhớ JVM/container.
