# Đăng ký component trong step

Trong Spring Batch, một step không chỉ cần `ItemReader`, `ItemProcessor` và `ItemWriter` hoặc một `Tasklet`. Step còn có thể cần listener để quan sát lifecycle, `ItemStream` để quản lý resource và checkpoint, hoặc các component phụ trợ được bọc bên trong composite/delegate. Để những component này hoạt động đúng, chúng phải được đăng ký với step theo đúng vai trò.

Đăng ký component có nghĩa là để Spring Batch biết component nào tham gia xử lý và component nào cần nhận callback lifecycle. Một bean tồn tại trong Spring application context chưa đồng nghĩa step sẽ tự gọi mọi method của nó. Ví dụ, một `StepExecutionListener` cần được gắn vào step; một `ItemStream` ẩn bên trong wrapper có thể cần đăng ký tường minh để nhận `open`, `update` và `close`.

Ba cơ chế chính cần phân biệt:

- **Cấu hình component xử lý:** `.reader(...)`, `.processor(...)`, `.writer(...)` hoặc `.tasklet(...)` xác định thành phần thực hiện công việc.
- **Đăng ký stream:** `.stream(...)` đưa một `ItemStream` vào lifecycle quản lý resource và checkpoint của step.
- **Đăng ký listener:** `.listener(...)` đăng ký callback theo lifecycle của job, step, chunk hoặc item.

Một component có thể đảm nhiệm nhiều vai trò, ví dụ một reader vừa là `ItemReader` vừa là `ItemStream`. Khi đó cần hiểu vai trò nào đã được builder tự nhận diện và vai trò nào phải đăng ký bổ sung, tránh bỏ sót callback hoặc đăng ký trùng.

## Các loại component trong step

Một chunk-oriented step thường gồm các thành phần sau:

| Thành phần | Interface/vai trò | Cách đưa vào step |
| --- | --- | --- |
| Reader | `ItemReader<I>` | `.reader(reader)` |
| Processor | `ItemProcessor<I, O>` | `.processor(processor)` |
| Writer | `ItemWriter<O>` | `.writer(writer)` |
| Tasklet step | `Tasklet` | `.tasklet(tasklet, transactionManager)` |
| Stream resource | `ItemStream` | Tự nhận diện khi là component trực tiếp trong các trường hợp được builder hỗ trợ; nếu là delegate thì đăng ký `.stream(stream)` |
| Step listener | `StepExecutionListener` | `.listener(listener)` |
| Chunk listener | `ChunkListener` | `.listener(listener)` |
| Item listener | `ItemReadListener`, `ItemProcessListener`, `ItemWriteListener` | `.listener(listener)` |
| Skip listener | `SkipListener` | `.listener(listener)` |

`ItemReader`, `ItemProcessor`, `ItemWriter` và `Tasklet` mô tả công việc. `ItemStream` mô tả lifecycle của resource/state. Listener nhận sự kiện để logging, metrics, audit hoặc điều phối logic theo lifecycle. Một component không tự động có mọi vai trò chỉ vì nó được khai báo thành bean.

## Đăng ký Reader, Processor và Writer

Với Java configuration, các component chính được gắn trực tiếp vào `StepBuilder`:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
```

Các method `.reader`, `.processor` và `.writer` xác định pipeline của chunk. Step gọi reader để lấy input, processor để chuyển đổi/filter và writer để ghi output. Nếu không cần processor, có thể bỏ `.processor(...)`; khi đó kiểu input/output của chunk phải phù hợp với reader và writer.

Đây là đăng ký vai trò xử lý. Không cần gọi `.stream(reader)` thêm một cách máy móc chỉ vì reader là `ItemStream`. Các reader/writer triển khai `ItemStream` được đưa trực tiếp vào step thường được Spring Batch tự đăng ký để quản lý lifecycle. Phần cần đăng ký tường minh thường là stream bị ẩn sau một delegate hoặc wrapper mà step không nhìn thấy trực tiếp.

### Bean phải được Spring quản lý khi cần dependency injection

Khai báo component bằng `@Bean` giúp Spring inject dependency và quản lý scope:

```java
@Bean
ItemProcessor<OrderInput, Order> orderProcessor(OrderValidator validator) {
    return input -> {
        validator.validate(input);
        return new Order(input.orderId(), input.amount());
    };
}
```

Tránh tạo component bằng `new` bên trong method cấu hình step nếu component cần dependency injection, scope hoặc proxy của Spring:

```java
// Không nên tạo thủ công nếu component cần Spring quản lý
.processor(new OrderProcessor())
```

Tạo object thủ công có thể bỏ qua bean post-processor, `@StepScope`, proxy transaction, dependency injection và các cơ chế lifecycle khác. Với component thuần, stateless và không cần Spring, tạo trực tiếp có thể hợp lệ; tuy nhiên, bean được quản lý thường dễ kiểm thử và cấu hình hơn.

## Đăng ký ItemStream

`ItemStream` là hợp đồng lifecycle dành cho component cần mở/đóng resource hoặc lưu state để restart:

```java
public interface ItemStream {
    void open(ExecutionContext executionContext);
    void update(ExecutionContext executionContext);
    void close();
}
```

Trong API thực tế, các method có thể khai báo `ItemStreamException`; ví dụ trên rút gọn phần chữ ký để làm rõ vai trò.

| Callback | Vai trò |
| --- | --- |
| `open(context)` | Mở resource và khôi phục state đã lưu |
| `update(context)` | Ghi state hiện tại vào `ExecutionContext` tại checkpoint |
| `close()` | Đóng resource và giải phóng tài nguyên |

Ví dụ custom reader giữ vị trí đọc:

```java
public class OrderFileReader
        implements ItemReader<Order>, ItemStream {

    private static final String LINE_KEY = "orderReader.line";
    private BufferedReader reader;
    private int currentLine;

    @Override
    public void open(ExecutionContext context) {
        currentLine = context.getInt(LINE_KEY, 0);
        openFileAndSkipLines(currentLine);
    }

    @Override
    public Order read() {
        Order order = readNextOrder();
        if (order != null) {
            currentLine++;
        }
        return order;
    }

    @Override
    public void update(ExecutionContext context) {
        context.putInt(LINE_KEY, currentLine);
    }

    @Override
    public void close() {
        closeReaderQuietly();
    }
}
```

`openFileAndSkipLines`, `readNextOrder` và `closeReaderQuietly` là logic ứng dụng minh họa. Reader thực tế cần xử lý đúng rollback và chỉ lưu checkpoint đại diện cho dữ liệu đã commit. Không dùng ví dụ counter đơn giản này như một implementation production cho mọi file format.

Nếu reader được truyền trực tiếp vào `.reader(orderReader)` và triển khai `ItemStream`, Spring Batch thường nhận diện và đăng ký stream. Khi reader nằm bên trong một wrapper mà step chỉ nhìn thấy wrapper, cần kiểm tra wrapper có forward `ItemStream` lifecycle hay không.

## Khi nào cần `.stream(...)`?

Giả sử step dùng một writer tổng hợp để ghi vào database và file:

```text
Step
  |
  v
Composite writer
  |
  +--> JdbcBatchItemWriter
  |
  +--> FlatFileItemWriter
```

Step nhìn thấy `CompositeItemWriter` ở vị trí `.writer(...)`. Nếu writer file là một delegate ẩn bên trong composite và lifecycle stream của nó không được forward/đăng ký tự động, step sẽ không gọi `open`, `update` và `close` cho delegate đó. File writer có thể ghi trong lần chạy đầu nhưng không lưu checkpoint hoặc không restart đúng.

Đăng ký delegate `ItemStream` tường minh:

```java
@Bean
Step exportOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        CompositeItemWriter<Order> compositeWriter,
        FlatFileItemWriter<Order> fileDelegate) {

    return new StepBuilder("exportOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(orderReader)
            .writer(compositeWriter)
            .stream(fileDelegate)
            .build();
}
```

Ví dụ thể hiện trường hợp delegate cần đăng ký riêng. Nếu wrapper/composite đang dùng đã forward đầy đủ lifecycle hoặc đã đăng ký delegate, không đăng ký lặp một cách tùy tiện. Kiểm tra contract của wrapper và phiên bản Spring Batch để xác định stream nào step đã quản lý.

### Custom wrapper phải forward lifecycle hoặc đăng ký delegate

Một wrapper có thể implement `ItemWriter<T>` nhưng không implement `ItemStream`, trong khi delegate bên trong cần lifecycle:

```java
public class AuditingWriter<T> implements ItemWriter<T> {

    private final ItemWriter<T> delegate;

    public AuditingWriter(ItemWriter<T> delegate) {
        this.delegate = delegate;
    }

    @Override
    public void write(Chunk<? extends T> chunk) throws Exception {
        delegate.write(chunk);
    }
}
```

Nếu `delegate` là `FlatFileItemWriter`, step chỉ nhìn thấy `AuditingWriter`; stream của file writer bị ẩn. Có hai lựa chọn:

1. Đăng ký `delegate` bằng `.stream(fileWriter)` ở step.
2. Thiết kế wrapper implement `ItemStreamWriter<T>` và forward `open`, `update`, `close` tới delegate.

Ví dụ wrapper forward lifecycle:

```java
public class StreamingAuditingWriter<T>
        implements ItemStreamWriter<T> {

    private final ItemStreamWriter<T> delegate;

    public StreamingAuditingWriter(ItemStreamWriter<T> delegate) {
        this.delegate = delegate;
    }

    @Override
    public void open(ExecutionContext context) {
        delegate.open(context);
    }

    @Override
    public void update(ExecutionContext context) {
        delegate.update(context);
    }

    @Override
    public void close() {
        delegate.close();
    }

    @Override
    public void write(Chunk<? extends T> chunk) throws Exception {
        delegate.write(chunk);
        // Thực hiện audit phù hợp sau khi delegate write.
    }
}
```

Đây là skeleton minh họa. Nếu wrapper forward lifecycle, đăng ký wrapper làm writer trực tiếp thường đủ để step quản lý stream. Nếu wrapper không forward, đăng ký delegate riêng. Tránh vừa forward vừa đăng ký cùng delegate nếu điều đó làm callback được gọi hai lần.

### Đăng ký nhiều stream

Một step có thể có nhiều stream phụ trợ:

```java
return new StepBuilder("exportStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .writer(compositeWriter)
        .stream(fileWriter)
        .stream(checkpointStore)
        .build();
```

Mỗi stream cần có trách nhiệm rõ ràng và key `ExecutionContext` riêng. Nếu nhiều stream ghi cùng một key, một component có thể ghi đè state của component khác.

Không đăng ký một instance stream nhiều lần qua nhiều đường khác nhau. Callback `open`, `update` hoặc `close` có thể bị gọi lặp, gây mở file hai lần, ghi checkpoint trùng hoặc đóng resource đã đóng.

## Đăng ký listener trong step

Listener nhận callback ở các mốc lifecycle. Để Spring Batch gọi listener, gắn nó vào step bằng `.listener(...)` hoặc khai báo listener trong XML namespace tương ứng.

Ví dụ `StepExecutionListener`:

```java
public class ImportStepListener implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution stepExecution) {
        log.info("Starting step {}", stepExecution.getStepName());
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        log.info("Finished step {} with status {}",
                stepExecution.getStepName(), stepExecution.getStatus());
        return null; // Giữ ExitStatus hiện có
    }
}
```

Đăng ký:

```java
return new StepBuilder("importStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .listener(importStepListener)
        .build();
```

`beforeStep` được gọi khi step bắt đầu; `afterStep` được gọi khi step kết thúc. `afterStep` có thể trả `ExitStatus` để đóng góp vào kết quả flow. Trả `null` thường có nghĩa giữ exit status hiện tại. Không tự ghi đè status chỉ để che một lỗi thực thi.

## Các loại listener phổ biến

Spring Batch có listener theo nhiều cấp:

| Listener | Callback tiêu biểu | Phạm vi |
| --- | --- | --- |
| `StepExecutionListener` | `beforeStep`, `afterStep` | Một lần thực thi step |
| `ChunkListener` | `beforeChunk`, `afterChunk`, `afterChunkError` | Một chunk |
| `ItemReadListener<T>` | `beforeRead`, `afterRead`, `onReadError` | Một lần đọc item |
| `ItemProcessListener<I, O>` | `beforeProcess`, `afterProcess`, `onProcessError` | Một lần process item |
| `ItemWriteListener<T>` | `beforeWrite`, `afterWrite`, `onWriteError` | Một lần ghi chunk |
| `SkipListener<I, O>` | `onSkipInRead`, `onSkipInProcess`, `onSkipInWrite` | Item bị skip |
| `RetryListener` | Callback theo retry lifecycle | Một lần retry operation, khi retry được cấu hình |

Listener phù hợp cho logging, metrics, audit và phản ứng với sự kiện. Tránh đặt logic nghiệp vụ chính vào listener nếu logic đó nên nằm trong reader/processor/writer hoặc service riêng.

### ChunkListener

```java
public class ImportChunkListener implements ChunkListener {

    @Override
    public void beforeChunk(ChunkContext context) {
        log.debug("Starting a chunk");
    }

    @Override
    public void afterChunk(ChunkContext context) {
        log.debug("Chunk completed");
    }

    @Override
    public void afterChunkError(ChunkContext context) {
        log.warn("Chunk ended with an error");
    }
}
```

Gắn listener:

```java
.listener(importChunkListener)
```

`ChunkListener` không thay thế `ItemWriteListener`: một listener quan sát ranh giới chunk, listener kia quan sát callback writer. Nếu cần biết item nào được skip, dùng `SkipListener`.

### ItemReadListener, ItemProcessListener và ItemWriteListener

Ví dụ listener cho process:

```java
public class OrderProcessListener
        implements ItemProcessListener<OrderInput, Order> {

    @Override
    public void beforeProcess(OrderInput item) {
        log.debug("Processing order {}", item.orderId());
    }

    @Override
    public void afterProcess(OrderInput item, Order result) {
        log.debug("Processed order {}", item.orderId());
    }

    @Override
    public void onProcessError(OrderInput item, Exception exception) {
        log.error("Cannot process order {}", item.orderId(), exception);
    }
}
```

Đăng ký bằng `.listener(orderProcessListener)`. Có thể đăng ký nhiều listener khác nhau trên cùng step, mỗi listener phụ trách một concern như metrics, tracing hoặc audit.

### SkipListener

```java
public class OrderSkipListener implements SkipListener<OrderInput, Order> {

    @Override
    public void onSkipInRead(Throwable exception) {
        log.warn("Input record was skipped", exception);
    }

    @Override
    public void onSkipInProcess(OrderInput item, Throwable exception) {
        log.warn("Order {} was skipped during processing",
                item.orderId(), exception);
    }

    @Override
    public void onSkipInWrite(Order item, Throwable exception) {
        log.warn("Order {} was skipped during writing",
                item.orderId(), exception);
    }
}
```

Listener được gọi khi fault-tolerant step thực sự skip item. Nó hữu ích để ghi reject record hoặc audit. Nếu listener ghi ra file/database khác transaction, cần xem xét idempotency vì callback có thể được gọi trong một luồng xử lý có rollback/retry.

## Đăng ký nhiều listener và stream cùng lúc

Builder cho phép gọi `.listener(...)` nhiều lần:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .listener(stepExecutionListener)
        .listener(chunkListener)
        .listener(readListener)
        .listener(processListener)
        .listener(writeListener)
        .listener(skipListener)
        .stream(rejectFileWriter)
        .build();
```

Ví dụ này có nhiều listener theo các interface khác nhau và một stream phụ trợ để ghi reject file. `rejectFileWriter` cần được mở, cập nhật checkpoint và đóng cùng step. Nếu listener và stream cùng là một object, hãy xác định rõ cách đăng ký để không gọi lifecycle hai lần.

Khi có nhiều listener cùng một interface, kiểm tra thứ tự đăng ký mà builder/framework áp dụng trong version đang dùng. Không nên phụ thuộc vào thứ tự ngầm nếu nghiệp vụ yêu cầu listener A phải chạy trước listener B. Nếu thứ tự là điều kiện quan trọng, gom logic vào một listener điều phối hoặc service có thứ tự tường minh.

## Đăng ký component trong Tasklet step

Tasklet step dùng một `Tasklet` thay cho pipeline reader/processor/writer:

```java
@Bean
Step cleanupStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        CleanupTasklet cleanupTasklet,
        StepExecutionListener stepListener) {

    return new StepBuilder("cleanupStep", jobRepository)
            .tasklet(cleanupTasklet, transactionManager)
            .listener(stepListener)
            .build();
}
```

Tasklet là component thực thi chính. Listener vẫn cần đăng ký với step nếu muốn nhận callback. Nếu tasklet giữ resource/state và implement `ItemStream`, bảo đảm stream lifecycle của nó được step quản lý. Với tasklet hoặc component phụ trợ không được builder tự nhận diện, đăng ký `.stream(...)` tường minh.

Ví dụ tasklet có state:

```java
public class CleanupTasklet implements Tasklet, ItemStream {

    private static final String CURSOR_KEY = "cleanup.cursor";
    private long cursor;

    @Override
    public void open(ExecutionContext context) {
        cursor = context.getLong(CURSOR_KEY, 0L);
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong(CURSOR_KEY, cursor);
    }

    @Override
    public void close() {
        closeResources();
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {
        processNextPartition(cursor);
        cursor++;
        return hasMoreWork(cursor)
                ? RepeatStatus.CONTINUABLE
                : RepeatStatus.FINISHED;
    }
}
```

Nếu cần bảo đảm rõ ràng, có thể đăng ký stream:

```java
return new StepBuilder("cleanupStep", jobRepository)
        .tasklet(cleanupTasklet, transactionManager)
        .stream(cleanupTasklet)
        .build();
```

Chỉ làm như vậy khi tasklet chưa được tự động đăng ký như stream trong đường cấu hình/version đang dùng; tránh đăng ký cùng một stream hai lần. Một cách khác là tách state/resource management sang một `ItemStream` riêng và đăng ký stream đó.

## Đăng ký component trong XML namespace

XML namespace có các phần tử để tham chiếu listener và stream. Với chunk step, reader/processor/writer được tham chiếu qua bean ID; listener và stream phụ trợ có thể khai báo trong các phần tử con tương ứng.

Ví dụ:

```xml
<batch:step id="importOrdersStep">
    <batch:tasklet>
        <batch:chunk reader="orderReader"
                     processor="orderProcessor"
                     writer="compositeWriter"
                     commit-interval="100">

            <batch:streams>
                <batch:stream ref="fileWriterDelegate"/>
                <batch:stream ref="rejectFileWriter"/>
            </batch:streams>

            <batch:listeners>
                <batch:listener ref="readListener"/>
                <batch:listener ref="processListener"/>
                <batch:listener ref="writeListener"/>
                <batch:listener ref="skipListener"/>
            </batch:listeners>
        </batch:chunk>
    </batch:tasklet>

    <batch:listeners>
        <batch:listener ref="stepExecutionListener"/>
        <batch:listener ref="chunkListener"/>
    </batch:listeners>
</batch:step>
```

Các bean được tham chiếu phải tồn tại trong application context. `batch:streams` dùng để đăng ký các stream phụ trợ không được step nhìn thấy trực tiếp qua reader/writer; `batch:listeners` đăng ký callback ở cấp chunk/step tương ứng với vị trí phần tử theo XSD. Cú pháp XML cụ thể cần khớp schema Spring Batch version đang sử dụng.

Khai báo bean:

```xml
<bean id="stepExecutionListener"
      class="com.example.batch.ImportStepListener"/>

<bean id="fileWriterDelegate"
      class="org.springframework.batch.item.file.FlatFileItemWriter">
    <!-- Resource, line aggregator và các property cần thiết -->
</bean>
```

Nếu dùng namespace XML, nên dùng IDE schema completion và validate file theo XSD đi kèm dependency để xác nhận vị trí `streams` và `listeners` hợp lệ. Đừng đặt `batch:listeners` ở một vị trí bất kỳ chỉ vì XML vẫn well-formed; XSD quy định cấu trúc hợp lệ.

## Annotation-based listener

Spring Batch hỗ trợ listener callback bằng interface hoặc annotation trên method. Ví dụ:

```java
public class OrderAuditListener {

    @BeforeStep
    public void beforeStep(StepExecution stepExecution) {
        log.info("Step started: {}", stepExecution.getStepName());
    }

    @AfterStep
    public ExitStatus afterStep(StepExecution stepExecution) {
        log.info("Read {}, wrote {}",
                stepExecution.getReadCount(),
                stepExecution.getWriteCount());
        return null;
    }
}
```

Đăng ký object làm listener:

```java
.listener(orderAuditListener)
```

Spring Batch phát hiện các annotation listener được hỗ trợ khi object được đăng ký. Annotation trên một class không tự làm class trở thành listener của mọi step; vẫn phải gắn object vào step/job phù hợp.

Có thể dùng interface khi muốn compiler xác nhận hợp đồng và annotation khi muốn tập trung callback trong một class. Tránh trộn nhiều cơ chế cho cùng callback nếu không có lý do rõ ràng.

## Phân biệt listener cấp Job và cấp Step

`JobExecutionListener` thuộc vòng đời job, còn `StepExecutionListener` thuộc vòng đời step.

| Listener | Đăng ký ở đâu | Phạm vi |
| --- | --- | --- |
| `JobExecutionListener` | `.listener(...)` trên `JobBuilder` hoặc cấu hình job | Trước/sau toàn bộ job execution |
| `StepExecutionListener` | `.listener(...)` trên `StepBuilder` | Trước/sau một step execution |
| `ChunkListener` | `.listener(...)` trên chunk step | Trước/sau mỗi chunk |
| Item listeners | `.listener(...)` trên step | Từng read/process/write |

Ví dụ job listener:

```java
@Bean
Job importJob(
        JobRepository jobRepository,
        Step importStep,
        JobExecutionListener jobListener) {

    return new JobBuilder("importJob", jobRepository)
            .listener(jobListener)
            .start(importStep)
            .build();
}
```

Không gắn `JobExecutionListener` vào step với kỳ vọng callback sẽ bao trùm toàn bộ job. Hãy chọn scope đúng với sự kiện cần quan sát.

## StepScope và late binding cho component

Reader, processor, writer hoặc tasklet có thể phụ thuộc vào `JobParameters` hay `ExecutionContext` của execution hiện tại. Dùng `@StepScope` để target bean được tạo khi step chạy:

```java
@Bean
@StepScope
FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("orderId", "amount")
            .fieldSetMapper(fields -> new OrderInput(
                    fields.readString("orderId"),
                    fields.readBigDecimal("amount")))
            .saveState(true)
            .build();
}
```

Bean scoped được inject vào cấu hình step qua proxy. Step vẫn đăng ký proxy làm reader; Spring Batch quản lý target tương ứng với execution hiện tại. Không gọi method trên target bằng cách tự tạo object ngoài scope.

Trong XML, có thể dùng `scope="step"` cho bean phụ thuộc job/step context. Đảm bảo scope infrastructure được kích hoạt bởi cấu hình Spring Batch phù hợp.

## Listener và ItemStream là hai cơ chế khác nhau

Một listener quan sát sự kiện; một stream quản lý resource/state. Không thay thế hai cơ chế này cho nhau.

Ví dụ:

- `ItemWriteListener.afterWrite` nhận thông báo writer đã xử lý chunk.
- `ItemStream.update` lưu state để restart.
- `StepExecutionListener.afterStep` quan sát kết quả cuối step.
- `ItemStream.close` đóng file hoặc cursor.

Nếu một component cần cả audit callback lẫn checkpoint, nó có thể implement cả listener interface và `ItemStream`, sau đó được đăng ký theo các vai trò phù hợp. Builder có thể tự nhận diện interface trên component trực tiếp; với component bị bọc, cần đăng ký từng vai trò mà wrapper không forward.

Không dùng `afterStep` thay cho `close()` để đóng resource cần được giải phóng dù step kết thúc theo nhiều đường. Lifecycle stream là nơi thích hợp cho mở/đóng resource.

## Thứ tự lifecycle ở mức khái niệm

Với chunk step, lifecycle khái quát gồm:

```text
Step bắt đầu
  |
  +--> StepExecutionListener.beforeStep
  |
  +--> ItemStream.open
  |
  +--> Lặp các chunk
  |       |
  |       +--> ChunkListener.beforeChunk
  |       +--> Reader / Processor / Writer
  |       +--> Item listeners trong từng thao tác
  |       +--> ItemStream.update tại checkpoint
  |       +--> ChunkListener.afterChunk hoặc afterChunkError
  |
  +--> ItemStream.close
  |
  +--> StepExecutionListener.afterStep
  |
Step kết thúc
```

Đây là sơ đồ khái niệm, không phải cam kết thứ tự chi tiết giữa mọi callback nội bộ hoặc transaction synchronization. Thứ tự chính xác có thể phụ thuộc loại step và phiên bản. Nếu logic nghiệp vụ phụ thuộc vào một callback xảy ra trước/sau commit, cần kiểm tra contract API và kiểm thử bằng transaction thực tế.

## Stream registration và restart

Một `ItemStream` được đăng ký đúng sẽ được mở với `ExecutionContext` của step và cập nhật state tại các điểm checkpoint. Khi restart, component có thể khôi phục state đã lưu.

Các nguyên tắc:

- Đặt tên reader/writer ổn định để key state không đổi.
- Dùng key `ExecutionContext` có namespace riêng cho từng component.
- Chỉ lưu giá trị nhỏ, có thể serialize và tương thích qua restart.
- Giữ input/output resource ổn định trong thời gian job có thể restart.
- Không lưu `FileChannel`, JDBC connection, stream hoặc object runtime vào context.
- Đăng ký mọi delegate cần lifecycle nếu wrapper không forward.
- Không đăng ký cùng stream nhiều lần.

Nếu delegate không được đăng ký, `open` có thể không chạy nên resource chưa mở đúng; `update` không lưu checkpoint; `close` không giải phóng resource theo lifecycle. Điều này thường chỉ lộ ra khi restart hoặc khi step chạy lâu.

## Đăng ký component có side effect

Listener và stream có thể thực hiện side effect, ví dụ ghi audit, gửi notification hoặc publish event. Cần đặt chúng ở lifecycle phù hợp:

- Ghi metrics/logging có thể nằm trong listener.
- Ghi reject item có thể nằm trong `SkipListener` hoặc writer riêng.
- Lưu checkpoint thuộc `ItemStream.update`.
- Đóng resource thuộc `ItemStream.close`.
- Công bố kết quả cuối cùng có thể thuộc step finalize sau khi output hoàn chỉnh.

Listener không tự động làm side effect tham gia transaction của chunk. Nếu listener ghi vào resource khác, rollback database không nhất thiết hoàn tác side effect đó. Dùng idempotency key, outbox hoặc cơ chế đối soát khi callback có thể chạy lại.

Tránh gửi email hoặc gọi API không idempotent trong `afterChunk`/`afterStep` nếu job có thể restart và callback có thể được thực thi lại theo quy trình vận hành. Nếu cần publish sự kiện sau commit, thiết kế outbox hoặc event publication có thể deduplicate.

## Thread safety của component được đăng ký

Một bean singleton có thể được dùng bởi nhiều job execution hoặc nhiều thread nếu ứng dụng chạy song song. Đăng ký component vào step không tự làm component thread-safe.

Các nguyên tắc:

- Reader có mutable cursor nên thường cần instance theo step execution hoặc cơ chế đồng bộ phù hợp.
- Writer giữ state file/resource nên không chia sẻ cùng một instance cho các step chạy đồng thời nếu không được thiết kế cho việc đó.
- Listener dùng field mutable phải cô lập state theo execution; tránh lưu `StepExecution` hiện tại vào singleton field.
- `ItemStream` dùng key context riêng và không giữ state runtime dùng chung giữa các execution.
- Dùng `@StepScope` khi component phụ thuộc dữ liệu của một step execution.
- Với partitioning, mỗi partition nên có resource/state riêng hoặc cơ chế chia sẻ được thiết kế rõ ràng.

Ví dụ listener không nên lưu step execution vào field singleton:

```java
// Không nên nếu bean được dùng đồng thời bởi nhiều step execution
private StepExecution currentExecution;

@Override
public void beforeStep(StepExecution stepExecution) {
    this.currentExecution = stepExecution;
}
```

Thay vào đó, lấy execution từ callback parameter và truyền vào method xử lý ngay tại thời điểm cần thiết. Nếu cần state theo execution, dùng step scope hoặc context phù hợp.

## Kiểm thử component registration

Unit test component riêng lẻ chỉ chứng minh logic của nó. Để xác nhận đăng ký step đúng, cần test step/job để chứng minh callback thực sự được gọi và stream state được lưu.

### Kiểm thử listener được gọi

Tạo listener test double đếm callback hoặc dùng mock:

```java
@Test
void registersStepExecutionListener() throws Exception {
    StepExecutionListener listener = mock(StepExecutionListener.class);
    Step step = new StepBuilder("testStep", jobRepository)
            .tasklet((contribution, chunkContext) -> RepeatStatus.FINISHED,
                    transactionManager)
            .listener(listener)
            .build();

    JobExecution execution = launchSingleStep(step);

    verify(listener).beforeStep(any(StepExecution.class));
    verify(listener).afterStep(any(StepExecution.class));
}
```

`launchSingleStep` là helper test do ứng dụng định nghĩa hoặc có thể thay bằng `JobLauncherTestUtils`/`StepRunner` theo test setup. Test cần chạy step thật để xác nhận builder đã đăng ký listener.

### Kiểm thử ItemStream lifecycle

Tạo stream test double ghi nhận `open`, `update` và `close`. Đăng ký bằng `.stream(stream)` rồi chạy step:

```java
ItemStream stream = new ItemStream() {
    @Override
    public void open(ExecutionContext context) {
        opened = true;
    }

    @Override
    public void update(ExecutionContext context) {
        updateCount++;
        context.putInt("testStream.counter", updateCount);
    }

    @Override
    public void close() {
        closed = true;
    }
};
```

Xác nhận stream được mở, cập nhật và đóng theo lifecycle của step. Với chunk step, có thể xác nhận `update` được gọi tại checkpoint. Đừng chỉ gọi trực tiếp callback trong unit test vì điều đó không chứng minh step đã đăng ký stream.

### Kiểm thử delegate trong composite

Tạo writer wrapper/composite chứa delegate implement `ItemStream`. Chạy step với và không có `.stream(delegate)` trong fixture riêng; xác nhận delegate nhận lifecycle khi được đăng ký đúng. Kiểm tra không bị gọi `open`/`close` hai lần khi wrapper cũng forward lifecycle.

### Kiểm thử restart

Chạy step qua một số chunk rồi làm step thất bại. Restart cùng identifying `JobParameters`; xác nhận stream `open` nhận context đã lưu, reader/writer tiếp tục đúng checkpoint và output không thiếu/trùng. Giữ nguyên component name và resource path trong cả hai lần chạy.

### Kiểm thử listener exception

Nếu listener có thể ném exception, xác nhận step/job phản ứng theo lifecycle và transaction boundary thực tế. Không để listener âm thầm nuốt lỗi nếu callback là điều kiện bắt buộc cho audit hoặc business invariant.

## Các lỗi thường gặp

### Nghĩ bean tồn tại trong context là step tự gọi nó

Bean phải được gắn vào step ở đúng vai trò. Đăng ký listener bằng `.listener(...)`, stream bằng `.stream(...)`, reader/writer bằng builder method tương ứng.

### Quên đăng ký delegate ItemStream

Step chỉ nhìn thấy wrapper/composite và không biết delegate cần `open/update/close`. Đăng ký delegate bằng `.stream(...)` hoặc để wrapper forward lifecycle.

### Đăng ký stream hai lần

Một component có thể được auto-register do là reader/writer trực tiếp rồi lại thêm `.stream(...)`. Callback bị gọi lặp có thể mở/đóng resource sai. Chỉ đăng ký bổ sung những stream chưa được quản lý.

### Nhầm listener với stream

Listener nhận event; stream quản lý resource/checkpoint. Một component có thể cần cả hai, nhưng callback khác nhau.

### Gắn JobExecutionListener vào step

Listener job cần đăng ký ở `JobBuilder`; listener step đăng ký ở `StepBuilder`. Chọn đúng lifecycle scope.

### Tạo component bằng new

Có thể bỏ qua DI, proxy, scope và lifecycle của Spring. Khai báo bean nếu component cần dependency hoặc execution-specific state.

### Dùng singleton có mutable state

Nhiều execution có thể ghi đè field của nhau. Dùng component stateless, `@StepScope` hoặc state tách biệt theo execution.

### Không giữ resource qua toàn bộ step

Release lock/connection/file handle quá sớm làm component khác truy cập resource khi step vẫn đang dùng. Dùng lifecycle stream phù hợp.

### Ghi side effect không idempotent trong listener

Retry/restart có thể làm callback được thực thi lại hoặc business operation lặp. Dùng idempotency/outbox và đặt side effect đúng transaction boundary.

### Chỉ test component, không test registration

Component chạy đúng khi gọi trực tiếp chưa chứng minh step đã đăng ký callback. Test step/job thật và kiểm tra lifecycle.

## Nguyên tắc thiết kế

Khi đăng ký custom component trong step, hãy xác định:

1. Component là reader, processor, writer, tasklet, listener hay stream?
2. Component được step nhìn thấy trực tiếp hay bị ẩn trong wrapper/delegate?
3. Nếu implement `ItemStream`, ai gọi `open`, `update` và `close`?
4. Nếu là listener, cần gắn ở job, step, chunk hay item scope?
5. Component có được Spring quản lý và có scope phù hợp không?
6. Có cần `.stream(...)` hoặc `.listener(...)` tường minh không?
7. Có nguy cơ đăng ký trùng hoặc bỏ sót callback không?
8. State/checkpoint có key riêng và tương thích khi restart không?
9. Component có an toàn khi nhiều execution/thread/partition dùng đồng thời không?
10. Side effect trong callback có idempotent và phù hợp transaction boundary không?
11. Integration test đã xác nhận callback/lifecycle thực sự được gọi chưa?

Hãy cấu hình reader/processor/writer/tasklet bằng builder, đăng ký listener theo đúng lifecycle và đăng ký tường minh các `ItemStream` bị ẩn sau wrapper/delegate. Giữ component stateless hoặc cô lập state theo step execution; dùng `ItemStream` cho resource/checkpoint và listener cho event. Test step/job thực tế để xác nhận component được gọi đúng một lần theo contract, stream được phục hồi khi restart và side effect không tạo dữ liệu trùng.

## Ghi nhớ

Đăng ký component trong step gồm ba việc khác nhau: gắn reader/processor/writer hoặc tasklet làm thành phần xử lý, đăng ký `ItemStream` để quản lý `open/update/close` và checkpoint, và đăng ký listener để nhận callback lifecycle. Component trực tiếp được cấu hình trên step thường được Spring Batch nhận diện; stream hoặc listener nằm ẩn trong wrapper/delegate có thể cần `.stream(...)` hoặc `.listener(...)` tường minh. Với XML, dùng `batch:streams` và `batch:listeners` ở vị trí được XSD quy định. Không đăng ký cùng stream hai lần, không nhầm listener với stream, giữ component an toàn khi chạy song song và bảo đảm state được lưu đúng để restart. Kiểm thử bằng cách chạy step/job thật, xác nhận callback, stream lifecycle, delegate registration và output sau restart.
