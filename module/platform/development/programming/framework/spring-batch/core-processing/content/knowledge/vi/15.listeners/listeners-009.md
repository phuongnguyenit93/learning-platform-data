# Listener order

Trong Spring Batch, listener cho phép ứng dụng quan sát hoặc bổ sung hành vi tại những thời điểm cụ thể trong vòng đời job, step, chunk và từng item. Một job có thể đăng ký nhiều listener cùng loại hoặc một listener triển khai nhiều interface. Khi đó, thứ tự callback quyết định listener nào chạy trước, listener nào chạy sau và dữ liệu mà listener sau nhìn thấy.

Để hiểu listener order, cần phân biệt hai lớp thứ tự:

- **Thứ tự theo vòng đời xử lý:** job bao quanh các step; step bao quanh các chunk hoặc lần thực thi tasklet; chunk điều phối các callback đọc, xử lý và ghi item.
- **Thứ tự giữa nhiều listener cùng loại:** khi nhiều listener cùng nhận một callback, framework gọi chúng theo thứ tự trong composite listener. Với các callback dạng trước/sau, thứ tự thường có tính chất stack: callback mở đầu chạy theo thứ tự đăng ký, callback kết thúc chạy theo thứ tự ngược lại.

Không nên xem tất cả listener là một danh sách callback toàn cục. Mỗi loại listener gắn với một ranh giới khác nhau, và vị trí callback trong transaction cũng quan trọng như thứ tự gọi.

## 1. Các nhóm listener trong Spring Batch

Spring Batch cung cấp listener ở nhiều cấp:

| Listener | Phạm vi | Callback tiêu biểu | Mục đích |
|---|---|---|---|
| `JobExecutionListener` | Toàn bộ job execution | `beforeJob`, `afterJob` | Chuẩn bị hoặc tổng kết một lần chạy job |
| `StepExecutionListener` | Một step execution | `beforeStep`, `afterStep` | Ghi nhận trạng thái và kết quả step |
| `ChunkListener` | Một chunk/lần thực thi tasklet | `beforeChunk`, `afterChunk`, `afterChunkError` | Quan sát ranh giới chunk và transaction |
| `ItemReadListener` | Một lần đọc item | `beforeRead`, `afterRead`, `onReadError` | Theo dõi reader |
| `ItemProcessListener` | Một item được xử lý | `beforeProcess`, `afterProcess`, `onProcessError` | Theo dõi processor |
| `ItemWriteListener` | Một lần ghi chunk | `beforeWrite`, `afterWrite`, `onWriteError` | Theo dõi writer |
| `SkipListener` | Một item bị skip | `onSkipInRead`, `onSkipInProcess`, `onSkipInWrite` | Ghi nhận item bị bỏ qua theo giai đoạn |
| `RetryListener` | Một lần retry operation | `open`, `onError`, `close` | Quan sát vòng đời retry |

Tên và chữ ký một số interface có thể khác giữa các phiên bản Spring Batch. Ví dụ, writer ở Spring Batch 5 nhận `Chunk`, trong khi các phiên bản cũ dùng `List`. Khi triển khai, hãy theo API của phiên bản dự án.

## 2. Thứ tự callback theo vòng đời job

Ở cấp cao nhất, `JobExecutionListener` bao quanh toàn bộ job execution. `beforeJob` chạy khi job chuẩn bị thực thi; các step sau đó được điều phối; `afterJob` chạy khi job execution kết thúc.

Với job gồm hai step, có thể hình dung thứ tự tổng quát:

```text
JobExecutionListener.beforeJob
  StepExecutionListener.beforeStep (step 1)
    Các callback chunk/item của step 1
  StepExecutionListener.afterStep (step 1)

  StepExecutionListener.beforeStep (step 2)
    Các callback chunk/item của step 2
  StepExecutionListener.afterStep (step 2)
JobExecutionListener.afterJob
```

Nếu flow có điều kiện, nhánh rẽ hoặc step song song, thứ tự các step phụ thuộc flow và cơ chế điều phối. Tuy nhiên, listener ở cấp job vẫn bao quanh vòng đời của job execution tương ứng.

`beforeJob` phù hợp để chuẩn bị tài nguyên ở phạm vi job hoặc ghi log bắt đầu. `afterJob` phù hợp để tổng kết trạng thái cuối cùng, gửi thông tin vận hành hoặc giải phóng tài nguyên thuộc job. Không nên dùng listener để thực hiện công việc nghiệp vụ lớn vốn nên được mô hình hóa thành step riêng.

## 3. Thứ tự callback trong một step

`StepExecutionListener` bao quanh một lần thực thi step:

1. `beforeStep(stepExecution)` được gọi trước phần xử lý chính của step.
2. Step chạy tasklet hoặc chunk-oriented processing.
3. `afterStep(stepExecution)` được gọi khi step kết thúc và có thể trả về `ExitStatus` bổ sung hoặc tùy chỉnh.

Ví dụ:

```java
public class StepAuditListener implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution stepExecution) {
        log.info("Starting step {}", stepExecution.getStepName());
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        log.info("Step {} ended with {}",
                stepExecution.getStepName(), stepExecution.getStatus());
        return stepExecution.getExitStatus();
    }
}
```

`afterStep` có thể trả `ExitStatus` để kết hợp với exit status hiện tại. Vì vậy, listener này không chỉ quan sát mà còn có thể ảnh hưởng đến flow nếu thay đổi exit code. Cần giữ hành vi đó có chủ đích và kiểm thử các nhánh chuyển step.

## 4. Thứ tự callback trong một chunk

Với chunk-oriented step, `ChunkListener` bao quanh một chunk. Thứ tự tổng quát:

```text
Transaction của chunk bắt đầu
ChunkListener.beforeChunk
  ItemReadListener callbacks
  ItemProcessListener callbacks
  ItemWriteListener callbacks
Chunk transaction commit thành công
ChunkListener.afterChunk
```

Nếu chunk thất bại và transaction rollback, framework có thể gọi `afterChunkError` theo lifecycle tương ứng. Một số chi tiết về thời điểm callback phụ thuộc loại step và phiên bản framework; điều quan trọng là phân biệt callback trước/sau thao tác writer với callback sau khi chunk transaction hoàn tất.

`beforeChunk` thường chạy sau khi transaction chunk đã bắt đầu và trước khi reader được gọi. `afterChunk` chạy sau khi chunk hoàn tất thành công và transaction đã commit. `afterChunkError` được dùng khi chunk gặp lỗi và transaction bị rollback.

Ví dụ:

```java
public class ChunkAuditListener implements ChunkListener {

    @Override
    public void beforeChunk(ChunkContext context) {
        log.debug("Chunk started");
    }

    @Override
    public void afterChunk(ChunkContext context) {
        log.debug("Chunk committed");
    }

    @Override
    public void afterChunkError(ChunkContext context) {
        log.warn("Chunk failed and was rolled back");
    }
}
```

Không nên đặt tác dụng phụ không thể lặp lại trong callback có thể được gọi khi retry. Nếu cần gửi thông báo sau commit, hãy dùng cơ chế đảm bảo idempotency hoặc phát sự kiện qua outbox; chỉ dựa vào log callback không tạo ra bảo đảm exactly-once.

## 5. Thứ tự callback quanh từng item

Trong chunk, mỗi item đi qua reader và processor; sau đó các kết quả được gom để writer xử lý. Các listener theo item có thứ tự riêng.

### Reader

```text
ItemReadListener.beforeRead
ItemReader.read
  ├─ thành công có item -> ItemReadListener.afterRead(item)
  ├─ hết dữ liệu (null) -> không có afterRead cho item
  └─ exception -> ItemReadListener.onReadError(exception)
```

`afterRead` chỉ chạy khi reader trả về một item. `null` là tín hiệu hết dữ liệu, không phải item. Nếu reader ném exception, callback lỗi được gọi theo cơ chế listener của step.

### Processor

```text
ItemProcessListener.beforeProcess(item)
ItemProcessor.process(item)
  ├─ trả output -> ItemProcessListener.afterProcess(item, output)
  ├─ trả null -> item bị filter; afterProcess được gọi với output null
  └─ exception -> ItemProcessListener.onProcessError(item, exception)
```

Processor trả về `null` là filter bình thường, không phải skip. Callback `afterProcess` có thể nhận output `null`; listener cần xử lý trường hợp đó.

### Writer

```text
ItemWriteListener.beforeWrite(chunk)
ItemWriter.write(chunk)
  ├─ thành công -> ItemWriteListener.afterWrite(chunk)
  └─ exception -> ItemWriteListener.onWriteError(exception, chunk)
```

Writer nhận một nhóm item. Một lần gọi writer có thể ghi nhiều bản ghi, và khi retry hoặc xử lý skip, writer có thể được gọi lại. Vì vậy, không nên xem mỗi `beforeWrite` là một lần ghi đã được commit.

## 6. Bảng thứ tự tổng hợp cho một chunk thành công

Với một chunk đơn giản gồm hai item, không có filter, retry hoặc skip, thứ tự có thể mô tả như sau:

| Thứ tự | Callback/hoạt động | Phạm vi |
|---:|---|---|
| 1 | `ChunkListener.beforeChunk` | Bắt đầu chunk |
| 2 | `ItemReadListener.beforeRead` | Đọc item 1 |
| 3 | `ItemReader.read` trả item 1 | Reader |
| 4 | `ItemReadListener.afterRead(item1)` | Reader |
| 5 | `ItemProcessListener.beforeProcess(item1)` | Processor |
| 6 | `ItemProcessor.process(item1)` | Processor |
| 7 | `ItemProcessListener.afterProcess(item1, output1)` | Processor |
| 8–13 | Các callback đọc/xử lý tương tự cho item 2 | Reader/processor |
| 14 | `ItemWriteListener.beforeWrite(chunk)` | Writer |
| 15 | `ItemWriter.write(chunk)` | Writer |
| 16 | `ItemWriteListener.afterWrite(chunk)` | Writer |
| 17 | Commit transaction của chunk | Transaction |
| 18 | `ChunkListener.afterChunk` | Kết thúc chunk |

Đây là thứ tự minh họa của một luồng chunk thành công đơn giản. Trong thực tế, reader có thể được gọi thêm một lần để nhận `null` khi hết dữ liệu; processor có thể filter item; retry/skip có thể khiến một số callback lặp lại; và framework có thể có các callback bổ sung cho stream/checkpoint.

## 7. Thứ tự khi có nhiều listener cùng loại

Một step có thể đăng ký nhiều listener cùng interface, ví dụ hai `ItemWriteListener` để ghi metric và audit. Spring Batch kết hợp chúng thông qua composite listener.

Với các callback có cặp trước/sau, quy tắc thông thường của composite listener là:

- Callback bắt đầu như `beforeWrite` hoặc `beforeStep` chạy theo thứ tự listener được sắp xếp/đăng ký.
- Callback kết thúc như `afterWrite` hoặc `afterStep` chạy theo thứ tự ngược lại, tương tự tháo stack đã mở.
- Callback lỗi thường được dispatch theo quy tắc của composite listener tương ứng; không nên suy đoán thứ tự nếu ứng dụng phụ thuộc vào nó mà chưa xác nhận theo phiên bản đang dùng.

Ví dụ với hai listener A và B được đăng ký theo thứ tự A rồi B:

```text
beforeWrite: A -> B
ItemWriter.write(...)
afterWrite:  B -> A
```

Cách gọi dạng stack giúp listener B có thể hoàn tất trước listener A, tương tự cách một lớp wrapper bên ngoài mở trước và đóng sau.

Nếu callback có logic phụ thuộc thứ tự, hãy khai báo thứ tự rõ ràng theo cơ chế mà phiên bản Spring Batch và cách cấu hình của dự án hỗ trợ, sau đó viết test ghi nhận sequence thực tế. Không dựa vào thứ tự scan bean hoặc thứ tự khởi tạo ngẫu nhiên của application context.

## 8. Listener triển khai nhiều interface

Một class có thể triển khai nhiều listener interface:

```java
public class BatchAuditListener implements
        JobExecutionListener,
        StepExecutionListener,
        ChunkListener {

    // beforeJob / afterJob
    // beforeStep / afterStep
    // beforeChunk / afterChunk / afterChunkError
}
```

Điều này gom logic audit có liên quan vào một class, nhưng không có nghĩa tất cả callback chạy liền nhau. Mỗi phương thức vẫn được gọi ở ranh giới lifecycle tương ứng.

Nếu cùng một object được đăng ký ở nhiều cấp, cần hiểu nó có thể nhận callback ở nhiều phạm vi. Ví dụ, `beforeStep` sẽ chạy cho mỗi step mà listener được đăng ký, còn `beforeJob` chạy một lần cho job execution. Tránh đăng ký cùng một listener trùng lặp ở cả cấp job, step và qua annotation nếu không chủ đích; nếu không, cùng callback có thể bị gọi nhiều lần.

## 9. Đăng ký listener và thứ tự khai báo

Với Java configuration, listener thường được gắn vào job hoặc step bằng `.listener(...)`:

```java
@Bean
public Step importStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemWriter<Order> writer,
        StepAuditListener stepAuditListener,
        ChunkAuditListener chunkAuditListener,
        OrderReadListener orderReadListener,
        OrderWriteListener orderWriteListener) {

    return new StepBuilder("importStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .writer(writer)
            .listener(stepAuditListener)
            .listener(chunkAuditListener)
            .listener(orderReadListener)
            .listener(orderWriteListener)
            .build();
}
```

Đoạn cấu hình cho thấy các listener được gắn vào step. Không phải mọi listener interface đều có thể được đăng ký ở mọi vị trí; builder thường nhận listener tương thích và tự nhận diện các interface mà object triển khai. Với API hoặc phiên bản khác, hãy dùng đúng overload và vị trí đăng ký.

Đối với thứ tự nhiều listener cùng loại, hãy dùng cơ chế sắp xếp được hỗ trợ như thứ tự đăng ký hoặc `Ordered`/`@Order` nếu composite listener trong phiên bản đó áp dụng ordering. Tránh dựa vào thứ tự inject các bean nếu nó không được quy định rõ.

## 10. Annotation listener và thứ tự thực thi

Spring Batch hỗ trợ annotation listener trên các phương thức, chẳng hạn:

- `@BeforeJob`, `@AfterJob`.
- `@BeforeStep`, `@AfterStep`.
- `@BeforeChunk`, `@AfterChunk`, `@AfterChunkError`.
- `@BeforeRead`, `@AfterRead`, `@OnReadError`.
- `@BeforeProcess`, `@AfterProcess`, `@OnProcessError`.
- `@BeforeWrite`, `@AfterWrite`, `@OnWriteError`.
- `@OnSkipInRead`, `@OnSkipInProcess`, `@OnSkipInWrite`.

Ví dụ:

```java
public class OrderListener {

    @BeforeWrite
    public void beforeWrite(Chunk<? extends Order> items) {
        log.debug("About to write {} orders", items.size());
    }

    @AfterWrite
    public void afterWrite(Chunk<? extends Order> items) {
        log.debug("Writer returned successfully for {} orders", items.size());
    }

    @OnWriteError
    public void onWriteError(
            Exception exception,
            Chunk<? extends Order> items) {
        log.warn("Write failed for {} orders", items.size(), exception);
    }
}
```

Annotation thay đổi cách khai báo phương thức, không thay đổi vị trí lifecycle của callback. Nếu cùng class được đăng ký nhiều lần hoặc vừa được đăng ký như interface listener vừa được phát hiện qua annotation, có nguy cơ callback được thực thi lặp. Hãy chọn một cách đăng ký nhất quán cho từng listener.

## 11. SkipListener có vị trí đặc biệt

`SkipListener` khác các listener quan sát read/process/write thông thường. Nó được gọi khi framework quyết định thực sự skip một item theo skip policy.

Các callback chính:

```java
public interface SkipListener<I, O> {
    void onSkipInRead(Throwable t);
    void onSkipInProcess(I item, Throwable t);
    void onSkipInWrite(O item, Throwable t);
}
```

`onSkipInRead` không nhận item vì reader đã ném lỗi trước khi tạo được item. `onSkipInProcess` nhận item đầu vào bị skip. `onSkipInWrite` nhận item đầu ra không ghi được.

Một điểm quan trọng là Spring Batch thiết kế `SkipListener` để callback skip được gọi một lần cho item bị skip và ở thời điểm gần commit chunk, nhằm cho phép ghi nhận skip bằng tài nguyên transaction. Điều này khác `onWriteError`, vốn có thể được gọi nhiều lần trong quá trình retry hoặc xác định item lỗi.

Ví dụ:

```java
public class OrderSkipListener implements SkipListener<Order, OrderRecord> {

    @Override
    public void onSkipInRead(Throwable t) {
        log.warn("An input record could not be read", t);
    }

    @Override
    public void onSkipInProcess(Order item, Throwable t) {
        log.warn("Order {} was skipped during processing", item.getId(), t);
    }

    @Override
    public void onSkipInWrite(OrderRecord item, Throwable t) {
        log.warn("Order {} was skipped during writing", item.getId(), t);
    }
}
```

Nếu listener ghi bản ghi lỗi vào database, nên dùng transaction resource phù hợp để audit được commit cùng chunk theo thiết kế. Nếu audit phải được giữ ngay cả khi transaction rollback, cần một cơ chế riêng và hiểu rõ khả năng ghi lặp khi retry.

## 12. RetryListener và callback lặp lại

Khi step có retry policy, `RetryListener` có thể quan sát vòng đời retry. Callback thường gồm `open`, `onError` và `close`, gắn với một lần thực hiện retry operation.

Điểm cần nhớ:

- `onError` có thể được gọi nhiều lần nếu operation thất bại nhiều lần.
- Một retry thành công không đồng nghĩa item đã bị skip.
- Listener item có thể nhận callback nhiều lần khi chunk hoặc operation được thử lại.
- Không nên đặt tác dụng phụ không idempotent trong callback retry.

Ví dụ, nếu `onError` gửi email mỗi lần gặp lỗi, một item retry ba lần có thể tạo ba email. Callback này phù hợp để ghi metric hoặc log có định danh attempt; thông báo vận hành nên có cơ chế gom nhóm hoặc idempotency.

## 13. Thời điểm callback và transaction boundary

Thứ tự listener không chỉ là vấn đề trước hay sau. Cần biết callback được gọi trước commit, sau commit hay trong quá trình rollback.

| Callback | Vị trí tương đối | Hệ quả khi thiết kế |
|---|---|---|
| `beforeChunk` | Sau khi transaction chunk bắt đầu, trước xử lý item | Có thể quan sát bắt đầu chunk; không nên làm việc chậm kéo dài transaction |
| `beforeRead` / `afterRead` | Bao quanh một lần đọc | Phù hợp quan sát reader; không phải checkpoint |
| `beforeProcess` / `afterProcess` | Bao quanh một lần xử lý item | Phù hợp metric/trace; callback có thể lặp khi retry |
| `beforeWrite` / `afterWrite` | Bao quanh lần gọi writer | `afterWrite` chỉ cho biết writer trả về thành công, chưa tự chứng minh transaction đã commit |
| `onWriteError` | Khi writer ném exception | Có thể được gọi lại trong retry/skip scan |
| `SkipListener` | Khi item được quyết định skip, gần thời điểm commit | Phù hợp ghi nhận item skip; cần hiểu transaction của resource audit |
| `afterChunk` | Sau khi chunk hoàn tất và commit thành công | Phù hợp ghi nhận chunk đã commit |
| `afterChunkError` | Khi chunk thất bại và rollback | Phù hợp metric lỗi; không giả định mọi resource ngoài transaction đã được hoàn tác |
| `afterStep` | Khi step kết thúc | Có thể điều chỉnh `ExitStatus`; không phải callback sau mỗi chunk |
| `afterJob` | Khi job execution kết thúc | Phù hợp tổng kết trạng thái cuối cùng |

Ví dụ, `ItemWriteListener.afterWrite` được gọi sau khi phương thức writer trả về, nhưng transaction chunk vẫn có thể thất bại ở bước sau, chẳng hạn khi cập nhật metadata hoặc commit database. Nếu cần hành động chỉ xảy ra sau commit thành công, `ChunkListener.afterChunk` gần với ranh giới đó hơn. Với tác dụng phụ cần bảo đảm bền vững, outbox vẫn là lựa chọn đáng tin cậy hơn việc gửi trực tiếp trong listener.

## 14. Thứ tự callback khi có lỗi

Khi một item hoặc chunk gặp lỗi, chuỗi callback khác với luồng thành công.

Ví dụ processor ném exception và exception được skip:

```text
ItemProcessListener.beforeProcess(item)
ItemProcessor.process(item) -> exception
ItemProcessListener.onProcessError(item, exception)
Framework áp dụng retry/skip policy
SkipListener.onSkipInProcess(item, exception)  (nếu item thực sự bị skip)
Các item còn lại tiếp tục theo flow của chunk
Chunk transaction commit nếu toàn bộ chunk cuối cùng hợp lệ
ChunkListener.afterChunk
```

Nếu retry thành công, `onProcessError` có thể đã được gọi nhưng `SkipListener.onSkipInProcess` không được gọi cho item đó vì item không bị skip. Nếu lỗi không thể xử lý, chunk có thể rollback và step thất bại; khi đó không có `afterChunk` cho chunk commit thành công.

Ví dụ writer ném lỗi:

```text
ItemWriteListener.beforeWrite(chunk)
ItemWriter.write(chunk) -> exception
ItemWriteListener.onWriteError(exception, chunk)
Transaction rollback
Framework retry hoặc scan để tìm item lỗi nếu cấu hình skip
  - writer có thể được gọi lại
  - onWriteError có thể được gọi lại
Nếu một item bị skip:
  SkipListener.onSkipInWrite(item, exception)
Nếu chunk hoàn tất sau xử lý lỗi:
  transaction commit
  ChunkListener.afterChunk
Nếu không xử lý được:
  step kết thúc FAILED
```

Sơ đồ này mô tả hành vi khái quát; số lần callback và thứ tự chi tiết phụ thuộc retry/skip policy, loại writer và phiên bản Spring Batch. Khi cần dựa vào một trình tự cụ thể, hãy kiểm tra bằng test trên phiên bản dự án.

## 15. Thứ tự nhiều listener: ví dụ với audit và metrics

Giả sử có hai listener cùng loại:

- `MetricsWriteListener` đo thời gian ghi.
- `AuditWriteListener` ghi thông tin nghiệp vụ của chunk.

Nếu đăng ký theo thứ tự metrics rồi audit, callback mở đầu có thể chạy:

```text
MetricsWriteListener.beforeWrite
AuditWriteListener.beforeWrite
ItemWriter.write
AuditWriteListener.afterWrite
MetricsWriteListener.afterWrite
```

Thứ tự đóng ngược lại có ích khi listener đầu tiên mở một tài nguyên hoặc bắt đầu đo, listener thứ hai bổ sung xử lý; khi kết thúc, listener thứ hai hoàn tất trước rồi listener đầu tiên dừng timer.

Nếu metrics cần đo riêng thời gian writer, có thể bắt đầu timer trong `beforeWrite` và kết thúc trong `afterWrite`. Nếu muốn đo cả thời gian transaction commit, `afterWrite` chưa đủ; cần đo ở `afterChunk` hoặc dùng instrumentation transaction phù hợp.

Không nên để `AuditWriteListener.afterWrite` gửi thông báo thành công ra ngoài trước khi transaction commit. Nếu commit sau đó thất bại, thông báo sẽ không khớp dữ liệu. Hãy ghi audit trong transaction hoặc phát sự kiện sau commit bằng outbox.

## 16. Xử lý exception trong listener

Listener là một phần của luồng thực thi. Nếu callback ném exception, tác động phụ thuộc listener type và thời điểm callback:

- Exception trong callback trước thao tác như `beforeRead` hoặc `beforeWrite` có thể ngăn thao tác chính tiếp tục và làm step thất bại.
- Exception trong callback sau thao tác có thể làm chunk/step thất bại tùy callback và lifecycle.
- Exception trong listener lỗi hoặc skip có thể làm hỏng chính quá trình xử lý lỗi.
- Exception trong `afterStep` hoặc `afterJob` có quy tắc xử lý riêng của framework; không nên giả định chúng luôn được xử lý như exception từ processor/writer.

Vì vậy, listener chỉ nên thực hiện công việc ngắn, có kiểm soát lỗi và tránh gọi dịch vụ ngoài chậm. Nếu listener là thành phần audit bắt buộc, cần xác định rõ lỗi audit có được phép làm job thất bại hay không.

Không nên bắt mọi exception rồi bỏ qua. Nếu audit là yêu cầu bắt buộc, nuốt lỗi có thể làm mất khả năng kiểm toán. Ngược lại, nếu metrics chỉ mang tính quan sát, có thể xử lý lỗi ghi metrics để tránh làm gián đoạn job, miễn là quyết định đó được quy định rõ.

## 17. Kiểm thử thứ tự listener

Khi thứ tự listener quan trọng, hãy kiểm thử thứ tự thực tế thay vì chỉ kiểm tra từng listener được gọi.

Một cách đơn giản là dùng một danh sách sự kiện dùng chung trong test:

```java
class RecordingListener implements ItemWriteListener<Order> {

    private final String name;
    private final List<String> events;

    RecordingListener(String name, List<String> events) {
        this.name = name;
        this.events = events;
    }

    @Override
    public void beforeWrite(Chunk<? extends Order> items) {
        events.add(name + ".beforeWrite");
    }

    @Override
    public void afterWrite(Chunk<? extends Order> items) {
        events.add(name + ".afterWrite");
    }

    @Override
    public void onWriteError(Exception ex, Chunk<? extends Order> items) {
        events.add(name + ".onWriteError");
    }
}
```

Trong test, tạo hai listener, đăng ký vào step theo thứ tự xác định, chạy một chunk và so sánh danh sách sự kiện thực tế với trình tự mong đợi.

Ví dụ kỳ vọng khi writer thành công:

```java
assertEquals(List.of(
        "metrics.beforeWrite",
        "audit.beforeWrite",
        "audit.afterWrite",
        "metrics.afterWrite"
), events);
```

Đây là minh họa cho quy tắc callback mở đầu/đóng kết thúc của composite listener. Hãy xác nhận thứ tự trong phiên bản và cơ chế đăng ký thực tế của ứng dụng. Nếu dùng `@Order` hoặc `Ordered`, test cần kiểm tra rằng composite listener thực sự tôn trọng thứ tự đó.

### Kiểm thử trường hợp lỗi

Nên bổ sung test khi writer ném exception để xác nhận:

- `beforeWrite` được gọi trước khi writer chạy.
- `onWriteError` nhận đúng exception.
- `afterWrite` không được xem là callback thành công cho lần ghi thất bại.
- Retry có thể làm các callback tương ứng xuất hiện nhiều lần.
- `SkipListener` chỉ được gọi nếu item thực sự bị skip.
- `afterChunk` chỉ phản ánh chunk hoàn tất thành công; chunk rollback đi theo callback lỗi phù hợp.

Nếu test cần xác nhận transaction commit/rollback, hãy chạy integration test với transaction manager và resource thực thay vì chỉ mock writer.

## 18. Tránh phụ thuộc vào thứ tự khởi tạo bean

Trong Spring application context, thứ tự tạo bean không phải một hợp đồng phù hợp để điều khiển listener order. Bean có thể được khởi tạo sớm hoặc muộn tùy dependency graph, lazy initialization và cấu hình context.

Nếu listener order ảnh hưởng đến kết quả:

- Đăng ký listener ở vị trí rõ ràng trong cấu hình job/step.
- Dùng `Ordered` hoặc `@Order` nếu composite listener của phiên bản đó hỗ trợ.
- Không dựa vào thứ tự component scan.
- Không đăng ký cùng listener qua nhiều cơ chế.
- Viết test xác nhận callback sequence.

Nếu hai listener không cần phụ thuộc nhau, tốt nhất giữ chúng độc lập. Listener metrics không nên cần audit listener chạy trước; listener audit cũng không nên dựa vào side effect chưa commit của listener khác.

## 19. Listener order trong step chạy song song

Khi step dùng multi-threading, partitioning hoặc remote chunking, callback vẫn tuân theo lifecycle của từng execution/chunk, nhưng không có một thứ tự toàn cục ổn định giữa các worker.

Ví dụ, partition A có thể gọi `beforeChunk` trước partition B, nhưng B có thể commit trước A. Log từ nhiều thread có thể xen kẽ. Không nên suy luận thứ tự nghiệp vụ toàn cục chỉ từ thứ tự timestamp của listener log.

Trong môi trường song song:

- Gắn execution ID, step name, partition ID hoặc correlation ID vào log.
- Dùng metric thread-safe và tránh biến đếm mutable không đồng bộ.
- Không dùng listener làm cơ chế khóa hoặc đồng bộ dữ liệu giữa worker.
- Không giả định `afterChunk` của partition này chạy trước/sau partition khác.
- Nếu cần thứ tự publish toàn cục, tạo bước tổng hợp sau khi các partition hoàn tất.

Listener order trong một composite của cùng execution khác với thứ tự hoàn thành giữa nhiều execution song song.

## 20. Những nguyên tắc cần nhớ

- Listener có phạm vi riêng: job, step, chunk, item, skip và retry.
- `JobExecutionListener` bao quanh job; `StepExecutionListener` bao quanh step; `ChunkListener` bao quanh chunk.
- Item listener bao quanh từng lần đọc, xử lý hoặc ghi; writer listener làm việc với cả chunk.
- Callback mở đầu thường chạy theo thứ tự đăng ký/sắp xếp; callback kết thúc thường chạy theo thứ tự ngược trong composite listener.
- Không xem `afterWrite` là bằng chứng transaction đã commit; `afterChunk` gắn với kết thúc chunk thành công.
- `onWriteError` có thể được gọi nhiều lần khi retry hoặc scan skip; `SkipListener` chỉ phản ánh item thực sự bị skip.
- Processor trả `null` là filter, không phải skip.
- Listener exception có thể ảnh hưởng step; giữ callback ngắn và xác định rõ chính sách lỗi.
- Khi nhiều listener cùng loại, khai báo thứ tự rõ ràng theo API phiên bản và kiểm thử sequence thực tế.
- Không dựa vào thứ tự khởi tạo bean hoặc component scan.
- Trong xử lý song song, thứ tự giữa các worker không có tính toàn cục; dùng correlation ID và bước tổng hợp khi cần.
- Tác dụng phụ sau ghi cần transaction phù hợp, idempotency hoặc outbox để tránh thông báo sai khi rollback/retry.

Hiểu listener order giúp đặt đúng logic audit, metrics, xử lý lỗi và điều phối theo vòng đời Spring Batch. Khi phân biệt rõ callback theo cấp job/step/chunk/item, thứ tự mở đầu và kết thúc của nhiều listener, cùng vị trí transaction commit/rollback, ứng dụng sẽ tránh được việc ghi nhận sai trạng thái hoặc thực hiện tác dụng phụ nhiều lần.
