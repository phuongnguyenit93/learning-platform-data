# ChunkListener trước và sau chunk

Trong Spring Batch, một Step xử lý theo chunk đọc và xử lý một nhóm item rồi ghi nhóm đó trong một transaction. `ChunkListener` cho phép ứng dụng quan sát các mốc quan trọng của vòng đời chunk: trước khi bắt đầu xử lý, sau khi chunk commit thành công và sau khi chunk rollback do lỗi.

Listener này hữu ích cho logging, metrics, audit kỹ thuật và theo dõi thời gian xử lý. Nó giúp biết một chunk bắt đầu khi nào, đã commit hay rollback và Step đang xử lý đến đâu. `ChunkListener` không thay thế `ItemReader`, `ItemProcessor` hoặc `ItemWriter`; nó quan sát vòng đời chunk, còn các thành phần kia chịu trách nhiệm xử lý dữ liệu.

## 1. Chunk là gì trong Spring Batch?

Trong chunk-oriented processing, Spring Batch gọi reader nhiều lần để lấy item, chuyển từng item qua processor nếu có, rồi chuyển nhóm item đã xử lý cho writer. Khi đạt commit interval hoặc reader báo hết input, writer ghi chunk và transaction được commit.

Ví dụ Step có chunk size 3 và reader cung cấp 7 item:

```text
Nguồn: A B C D E F G

Chunk 1: [A, B, C] -> Processor -> Writer -> Commit
Chunk 2: [D, E, F] -> Processor -> Writer -> Commit
Chunk 3: [G]       -> Processor -> Writer -> Commit
```

Chunk cuối có thể ít item hơn commit interval. Khi reader trả `null`, Spring Batch vẫn hoàn tất việc xử lý và ghi các item còn lại trong chunk cuối trước khi kết thúc Step.

Mỗi chunk là một đơn vị transaction theo cấu hình của Step. Nếu writer thành công và transaction commit, các thay đổi tham gia transaction được lưu. Nếu một lỗi làm chunk rollback, những thay đổi thuộc transaction đó được hoàn tác theo khả năng của transaction manager và resource tham gia.

## 2. ChunkListener cung cấp những callback nào?

`ChunkListener` định nghĩa ba callback chính:

```java
public interface ChunkListener extends StepListener {

    void beforeChunk(ChunkContext context);

    void afterChunk(ChunkContext context);

    void afterChunkError(ChunkContext context);
}
```

Ý nghĩa của từng callback:

| Callback | Thời điểm | Mục đích thường dùng |
|---|---|---|
| `beforeChunk()` | Sau khi transaction của chunk bắt đầu và trước khi đọc/xử lý/ghi chunk | Ghi nhận thời điểm bắt đầu, tạo correlation data hoặc log ngữ cảnh |
| `afterChunk()` | Sau khi chunk đã commit thành công | Ghi nhận chunk hoàn tất, cập nhật metrics hoặc log bộ đếm |
| `afterChunkError()` | Sau khi chunk rollback do lỗi | Ghi nhận lỗi, thời điểm rollback và thông tin phục vụ điều tra |

Các callback này thuộc vòng đời của chunk. Chúng không được gọi một lần cho mỗi item; một chunk có thể chứa nhiều item nhưng chỉ có một chu kỳ callback tương ứng.

## 3. Thứ tự callback so với transaction

Với một chunk xử lý thành công, luồng khái quát như sau:

```text
Bắt đầu transaction
        |
        v
beforeChunk(context)
        |
        v
ItemReader đọc item
        |
        v
ItemProcessor xử lý item (nếu có)
        |
        v
ItemWriter ghi chunk
        |
        v
Commit transaction
        |
        v
afterChunk(context)
```

Nếu có lỗi làm transaction rollback:

```text
Bắt đầu transaction
        |
        v
beforeChunk(context)
        |
        v
Đọc / xử lý / ghi
        |
        v
       Lỗi
        |
        v
Rollback transaction
        |
        v
afterChunkError(context)
```

`beforeChunk()` được gọi sau khi transaction đã bắt đầu. Vì vậy, thao tác database trong callback có thể tham gia transaction của chunk nếu dùng cùng transaction manager và cùng resource. Nếu chunk rollback, các thay đổi đó cũng có thể rollback.

`afterChunk()` được gọi sau khi chunk commit. Do đó, một thao tác database thực hiện trong callback này không còn nằm trong transaction vừa commit của chunk; nếu cần transaction riêng, ứng dụng phải cấu hình phù hợp. Không nên giả định thao tác trong `afterChunk()` có thể rollback cùng dữ liệu writer vừa ghi.

`afterChunkError()` được gọi sau khi chunk rollback. Callback này phù hợp để ghi nhận thông tin lỗi hoặc metrics. Nếu cần lưu audit lỗi vào database, phải cân nhắc transaction riêng vì transaction của chunk đã rollback.

## 4. Cài đặt ChunkListener bằng interface

Có thể tạo một bean triển khai `ChunkListener`:

```java
@Component
public class ImportChunkListener implements ChunkListener {

    private static final Logger log =
            LoggerFactory.getLogger(ImportChunkListener.class);

    @Override
    public void beforeChunk(ChunkContext context) {
        StepExecution stepExecution = context.getStepContext()
                .getStepExecution();

        log.info("Starting chunk: jobExecutionId={}, step={}, readCount={}",
                stepExecution.getJobExecutionId(),
                stepExecution.getStepName(),
                stepExecution.getReadCount());
    }

    @Override
    public void afterChunk(ChunkContext context) {
        StepExecution stepExecution = context.getStepContext()
                .getStepExecution();

        log.info("Chunk committed: step={}, readCount={}, writeCount={}",
                stepExecution.getStepName(),
                stepExecution.getReadCount(),
                stepExecution.getWriteCount());
    }

    @Override
    public void afterChunkError(ChunkContext context) {
        StepExecution stepExecution = context.getStepContext()
                .getStepExecution();

        log.warn("Chunk rolled back: jobExecutionId={}, step={}",
                stepExecution.getJobExecutionId(),
                stepExecution.getStepName());
    }
}
```

Listener lấy `StepExecution` từ `ChunkContext` để ghi tên Step, JobExecution ID và các bộ đếm. Trong ứng dụng thực tế, nên dùng logger thay vì `System.out.println`, đồng thời tránh ghi toàn bộ payload hoặc dữ liệu nhạy cảm.

Các bộ đếm như `readCount` và `writeCount` hữu ích để quan sát tiến độ, nhưng không phải lúc nào cũng tương đương chính xác với số tác dụng phụ nghiệp vụ đã xảy ra. Retry, skip, filter và rollback có thể làm cách diễn giải bộ đếm phức tạp hơn. Khi cần số liệu nghiệp vụ chính xác, hãy lưu chúng theo quy tắc domain riêng.

## 5. Đăng ký ChunkListener vào Step

Trong Spring Batch 5, có thể đăng ký listener bằng `StepBuilder.listener()`:

```java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerInput> reader,
        ItemProcessor<CustomerInput, Customer> processor,
        ItemWriter<Customer> writer,
        ImportChunkListener chunkListener) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<CustomerInput, Customer>chunk(500, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .listener(chunkListener)
            .build();
}
```

Khi Step chạy, Spring Batch gọi callback tương ứng quanh mỗi chunk. Một listener có thể được đăng ký trên nhiều Step nếu logic quan sát dùng chung, nhưng cần phân biệt tên Step trong log và không lưu trạng thái mutable của từng chunk trong field dùng chung.

## 6. Truy cập dữ liệu qua ChunkContext

Mỗi callback nhận một `ChunkContext`. Context này cung cấp `StepContext` và các thuộc tính liên quan đến lần xử lý chunk hiện tại.

Ví dụ lấy thông tin StepExecution:

```java
@Override
public void beforeChunk(ChunkContext context) {
    StepExecution stepExecution = context.getStepContext()
            .getStepExecution();

    Long jobExecutionId = stepExecution.getJobExecutionId();
    Long stepExecutionId = stepExecution.getId();
    String stepName = stepExecution.getStepName();
}
```

Có thể đọc JobParameters và các context map thông qua `StepContext`:

```java
StepContext stepContext = context.getStepContext();
Map<String, Object> jobParameters = stepContext.getJobParameters();
Map<String, Object> stepValues = stepContext.getStepExecutionContext();
Map<String, Object> jobValues = stepContext.getJobExecutionContext();
```

`ChunkContext` là context phục vụ lần xử lý chunk hiện tại. Không nên nhầm nó với `ExecutionContext` được Spring Batch lưu trong `JobRepository`. Nếu cần lưu checkpoint bền vững để restart, hãy cập nhật `StepExecution.getExecutionContext()` hoặc để reader triển khai `ItemStream` quản lý trạng thái của nó. Thuộc tính tạm trong `ChunkContext` không phải cơ chế lưu trữ durable thay thế ExecutionContext.

## 7. Dùng ChunkListener để đo thời gian xử lý

Một ứng dụng có thể dùng listener để ghi nhận thời gian bắt đầu và thời gian hoàn thành chunk. Nếu lưu timestamp vào `ChunkContext`, callback sau có thể lấy lại trong cùng context:

```java
@Component
public class ChunkTimingListener implements ChunkListener {

    private static final String START_NANOS = "chunk.startNanos";

    private static final Logger log =
            LoggerFactory.getLogger(ChunkTimingListener.class);

    @Override
    public void beforeChunk(ChunkContext context) {
        context.setAttribute(START_NANOS, System.nanoTime());
    }

    @Override
    public void afterChunk(ChunkContext context) {
        logDuration(context, "committed");
    }

    @Override
    public void afterChunkError(ChunkContext context) {
        logDuration(context, "rolled-back");
    }

    private void logDuration(ChunkContext context, String outcome) {
        Object start = context.getAttribute(START_NANOS);
        if (start instanceof Long startNanos) {
            long elapsedMillis =
                    (System.nanoTime() - startNanos) / 1_000_000;
            log.info("Chunk {} after {} ms", outcome, elapsedMillis);
        }
    }
}
```

Ví dụ dùng `System.nanoTime()` để đo khoảng thời gian trong cùng tiến trình; không dùng nó làm timestamp lịch sử hoặc checkpoint. Thuộc tính `ChunkContext` chỉ phục vụ context của chunk hiện tại.

Với retry, cùng một chunk logic có thể có nhiều lần thử và callback có thể được gọi lại theo từng attempt. Vì vậy, phép đo nên được hiểu là thời gian của attempt tương ứng, không phải lúc nào cũng là tổng thời gian nghiệp vụ của một nhóm item.

## 8. ChunkListener khi có retry, skip và rollback

Trong fault-tolerant Step, lỗi có thể làm chunk rollback rồi được retry. Khi đó, listener có thể quan sát nhiều lần bắt đầu và lỗi trước khi một lần thử thành công.

Ví dụ:

```text
Attempt 1:
  beforeChunk
  read / process / write
  deadlock
  rollback
  afterChunkError

Attempt 2:
  beforeChunk
  read / process / write
  commit
  afterChunk
```

Luồng thực tế có thể phức tạp hơn tùy loại lỗi, retry policy, buffering và cấu hình fault tolerance. Không nên giả định một lần `beforeChunk()` luôn có đúng một lần `afterChunk()`; một chunk có thể trải qua rollback và nhiều attempt.

`afterChunkError()` hữu ích để ghi nhận một attempt rollback. Nó không có nghĩa toàn bộ Step đã thất bại vĩnh viễn: Spring Batch có thể retry và chunk sau đó commit thành công. Để biết kết quả cuối cùng của Step, dùng `StepExecutionListener` hoặc `JobExecutionListener`.

Skip cũng có thể xảy ra trong một chunk mà chunk cuối cùng vẫn commit. Khi đó, `afterChunk()` được gọi cho chunk đã commit; số lượng item skip cần được xem qua các bộ đếm hoặc listener cấp item phù hợp.

## 9. Phân biệt ChunkListener với các listener khác

Spring Batch có nhiều listener vì mỗi listener quan sát một phạm vi khác nhau:

| Listener | Phạm vi | Callback tiêu biểu |
|---|---|---|
| `ChunkListener` | Một chunk | `beforeChunk`, `afterChunk`, `afterChunkError` |
| `ItemReadListener` | Một lần đọc item | `beforeRead`, `afterRead`, `onReadError` |
| `ItemProcessListener` | Một item được xử lý | `beforeProcess`, `afterProcess`, `onProcessError` |
| `ItemWriteListener` | Một lần ghi nhóm item | `beforeWrite`, `afterWrite`, `onWriteError` |
| `StepExecutionListener` | Toàn bộ một lần thực thi Step | `beforeStep`, `afterStep` |
| `JobExecutionListener` | Toàn bộ một lần thực thi Job | `beforeJob`, `afterJob` |

Chọn listener theo câu hỏi cần trả lời:

- Muốn đo thời gian của một chunk hoặc ghi nhận commit/rollback: dùng `ChunkListener`.
- Muốn biết item nào đọc lỗi: dùng `ItemReadListener`.
- Muốn quan sát một item bị processor từ chối hoặc lọc: dùng `ItemProcessListener`.
- Muốn biết writer ghi nhóm item nào hoặc gặp lỗi gì: dùng `ItemWriteListener`.
- Muốn ghi nhận trạng thái đầu/cuối của Step: dùng `StepExecutionListener`.
- Muốn ghi nhận trạng thái đầu/cuối của Job: dùng `JobExecutionListener`.

Không nên dùng `ChunkListener` để thay đổi nội dung item. Việc chuyển đổi hoặc lọc item thuộc `ItemProcessor`; ghi dữ liệu thuộc `ItemWriter`.

## 10. Có thể dùng annotation thay cho interface

Ngoài việc triển khai `ChunkListener`, Spring Batch hỗ trợ các annotation listener cho những callback tương ứng, như `@BeforeChunk`, `@AfterChunk` và `@AfterChunkError`.

Ví dụ:

```java
public class AnnotatedChunkAudit {

    @BeforeChunk
    public void before(ChunkContext context) {
        log.info("Chunk is starting");
    }

    @AfterChunk
    public void after(ChunkContext context) {
        log.info("Chunk has committed");
    }

    @AfterChunkError
    public void afterError(ChunkContext context) {
        log.warn("Chunk was rolled back");
    }
}
```

Đăng ký object chứa annotation với Step bằng `.listener(annotatedChunkAudit)`. Cách annotation phù hợp khi muốn gom nhiều callback vào một class mà không cần `implements ChunkListener`. Interface thường rõ ràng hơn nếu cần khai báo đầy đủ ba callback hoặc tái sử dụng listener theo kiểu Java thông thường.

## 11. Lưu ý khi callback thực hiện thao tác nghiệp vụ

`ChunkListener` thường nên tập trung vào quan sát. Nếu callback ghi audit, gửi thông báo hoặc gọi API, cần hiểu rõ transaction boundary.

### Không gửi thông báo quan trọng chỉ dựa vào afterChunk

`afterChunk()` chạy sau khi chunk đã commit. Nếu ứng dụng dừng sau commit nhưng trước khi callback hoàn tất, chunk đã được ghi nhưng thông báo có thể chưa được gửi. Nếu callback gửi thông báo rồi lỗi trước khi ghi nhận trạng thái gửi, một lần retry hoặc restart có thể gửi trùng.

Với thông báo hoặc sự kiện phải được phát cùng dữ liệu đã commit, cân nhắc transactional outbox: ghi bản ghi outbox trong cùng transaction chunk, rồi một publisher riêng gửi sự kiện và đánh dấu đã phát bằng cơ chế idempotent.

### Không dùng afterChunkError để thay thế xử lý lỗi

`afterChunkError()` được gọi để quan sát rollback. Nó không nên nuốt exception gốc hoặc đánh dấu Step thành công. Retry, skip và quyết định thất bại thuộc cơ chế fault tolerance của Step; kết quả cuối cùng cần được phản ánh trong metadata.

### Không giả định callback có thể rollback chunk đã commit

Khi `afterChunk()` được gọi, transaction của chunk đã commit. Nếu callback ném exception, dữ liệu chunk đã commit không tự động được rollback lại. Step có thể kết thúc lỗi trong khi chunk vẫn tồn tại trong database. Khi restart, chunk đã commit có thể không được xử lý lại, vì vậy các tác vụ sau commit cần có khả năng phục hồi riêng.

## 12. Thread safety khi Step chạy song song

Nếu Step được cấu hình chạy nhiều thread hoặc các partition thực thi đồng thời, callback của listener có thể được gọi đồng thời trên cùng bean listener tùy cách đăng ký và mô hình thực thi.

Không nên lưu trạng thái của chunk hiện tại trong mutable field dùng chung:

```java
// Không an toàn nếu nhiều chunk chạy đồng thời
private long currentChunkStart;
```

Một thread có thể ghi đè giá trị của thread khác. Hãy lưu timestamp hoặc dữ liệu tạm trong `ChunkContext`, hoặc dùng cơ chế metrics thread-safe. Nếu cần bộ đếm dùng chung, dùng loại dữ liệu đồng bộ phù hợp và hiểu rằng thứ tự callback giữa các worker không phản ánh thứ tự toàn cục của item.

Listener và service được inject cũng cần an toàn khi gọi đồng thời. Tránh giữ connection, cursor hoặc object theo từng chunk trong field của singleton bean. Dùng context của callback để lấy thông tin execution tương ứng.

## 13. Theo dõi chunk và các metrics hữu ích

ChunkListener có thể bổ sung thông tin cho observability của Job. Những số liệu thường hữu ích:

- Số chunk bắt đầu, commit và rollback.
- Thời gian xử lý mỗi chunk và phân bố p50/p95/p99.
- Số item đọc, ghi, lọc và skip.
- Số lần retry và số chunk hết retry.
- Tỷ lệ rollback theo Step hoặc Job.
- Throughput item/giây.
- JobExecution ID, StepExecution ID và business key liên quan.

Khi ghi log, nên gắn correlation ID để liên kết log ứng dụng với log database hoặc service ngoài. Không log password, access token hoặc toàn bộ dữ liệu cá nhân của item.

Nếu số chunk rất lớn, tránh ghi một log `INFO` cho mọi callback khiến log volume tăng nhanh. Có thể dùng `DEBUG` cho sự kiện từng chunk, metrics tổng hợp cho dashboard và `WARN` cho rollback hoặc lỗi cần điều tra.

## 14. Các lỗi thường gặp

**Nhầm afterChunk là callback trước commit:** `afterChunk()` được gọi sau khi chunk commit thành công. Nếu cần quan sát trước khi xử lý, dùng `beforeChunk()`.

**Cho rằng afterChunkError có nghĩa Job đã FAILED:** callback chỉ phản ánh chunk đã rollback. Chunk có thể được retry và Step vẫn hoàn tất thành công.

**Dùng listener để xử lý từng item:** `ChunkListener` không được gọi một lần cho mỗi item. Dùng `ItemReadListener`, `ItemProcessListener` hoặc `ItemWriteListener` theo nhu cầu.

**Ghi dữ liệu trong afterChunk rồi kỳ vọng rollback cùng writer:** transaction chunk đã commit trước callback. Dùng transaction riêng hoặc outbox nếu cần bảo đảm phù hợp.

**Giữ timestamp hoặc item trong field dùng chung:** có thể gây race condition khi chạy song song. Lưu dữ liệu tạm trong `ChunkContext` hoặc dùng cơ chế thread-safe.

**Dùng ChunkContext làm checkpoint bền vững:** thuộc tính tạm của ChunkContext không thay thế ExecutionContext. Dùng StepExecutionContext hoặc ItemStream cho trạng thái restart.

**Đếm callback như số chunk nghiệp vụ duy nhất:** retry có thể tạo nhiều attempt và nhiều callback cho cùng đơn vị công việc. Phân biệt số attempt, số rollback và số chunk commit.

## Kết luận

`ChunkListener` cung cấp ba callback để quan sát vòng đời chunk: `beforeChunk()` chạy sau khi transaction bắt đầu, `afterChunk()` chạy sau khi chunk commit và `afterChunkError()` chạy sau khi chunk rollback. Listener phù hợp để ghi log, đo thời gian và thu thập metrics ở cấp chunk. Hãy dùng `ChunkContext` cho dữ liệu tạm của callback, `ExecutionContext` cho checkpoint bền vững và các listener cấp item hoặc Step khi cần phạm vi quan sát khác. Khi có retry hoặc chạy song song, callback có thể xuất hiện nhiều lần hoặc đồng thời; vì vậy listener cần thread-safe và không nên chứa tác dụng phụ nghiệp vụ không có cơ chế phục hồi.
