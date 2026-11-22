# Restart với writer state

Trong Spring Batch, restart không chỉ cần biết reader đã đọc tới đâu. Writer cũng có thể cần khôi phục trạng thái để tiếp tục ghi đúng vị trí sau khi step bị lỗi hoặc tiến trình dừng đột ngột. Ví dụ, writer xuất file cần biết đã ghi bao nhiêu dòng; writer ghi một định dạng tuần tự có thể cần khôi phục offset; writer tùy chỉnh có thể cần biết sequence cuối cùng đã commit.

Spring Batch hỗ trợ việc này thông qua `ItemStream` và `ExecutionContext`. Writer có state có thể mở lại từ checkpoint đã lưu, cập nhật state tại các điểm commit và đóng resource khi step kết thúc. Nhiều writer dựng sẵn, tiêu biểu là `FlatFileItemWriter`, đã hỗ trợ lưu state. Với writer tự triển khai, ứng dụng cần thiết kế rõ lifecycle, transaction boundary và cách khôi phục state.

Điều quan trọng là writer state phải mô tả **phần output đã được xác nhận bền vững**. Nếu state tiến lên trước khi output được commit, restart có thể bỏ qua dữ liệu chưa ghi. Nếu output đã được ghi nhưng state chưa được lưu, restart có thể ghi trùng. Writer state vì vậy phải được phối hợp với transaction và checkpoint của step.

## Reader checkpoint và writer state

Trong chunk-oriented step, reader và writer có thể đều cần lưu state, nhưng chúng trả lời hai câu hỏi khác nhau:

| Thành phần | Câu hỏi mà state trả lời | Ví dụ |
| --- | --- | --- |
| Reader | Lần tiếp theo cần đọc item nào? | Dòng file, page number, khóa cuối đã đọc |
| Writer | Output đã được ghi tới đâu? | Số dòng đã ghi, byte offset, sequence cuối đã commit |

Reader state giúp tránh bỏ sót input; writer state giúp tiếp tục output đúng vị trí. Một job restart an toàn cần hai phía phối hợp. Nếu reader tiếp tục từ item 501 nhưng writer lại ghi từ dòng đầu file, output có thể bị trùng. Ngược lại, nếu writer tiếp tục ở dòng 501 trong khi reader đọc lại từ item đầu, có thể mất hoặc ghi sai dữ liệu.

Trong chunk step, flow khái quát như sau:

```text
                Step bắt đầu / restart
                         |
                         v
        Reader.open(step ExecutionContext)
        Writer.open(step ExecutionContext)
                         |
                         v
                 Đọc và xử lý chunk
                         |
                         v
                    Writer.write
                         |
                         v
            Reader/Writer.update(context)
                         |
                         v
           Lưu StepExecution và ExecutionContext
                         |
                         v
                      COMMIT
                         |
                         v
              Checkpoint mới đã bền vững
```

Đây là mô hình khái niệm. Spring Batch điều phối lifecycle `ItemStream` và lưu metadata theo transaction/repository configuration của step. Chi tiết nội bộ có thể khác theo loại writer và phiên bản framework.

## ItemStream: hợp đồng lưu và khôi phục writer state

`ItemStream` cung cấp ba callback chính:

```java
public interface ItemStream {
    void open(ExecutionContext executionContext);
    void update(ExecutionContext executionContext);
    void close();
}
```

Trong Spring Batch, các method thực tế có thể khai báo `ItemStreamException`; ví dụ rút gọn ở trên tập trung vào vai trò của từng callback.

| Callback | Thời điểm và mục đích |
| --- | --- |
| `open(context)` | Khôi phục state đã lưu khi step bắt đầu hoặc được restart; mở resource cần ghi |
| `write(chunk)` | Ghi output của chunk hiện tại |
| `update(context)` | Đưa state hiện tại vào `ExecutionContext` tại checkpoint |
| `close()` | Đóng file, stream, connection hoặc resource do writer sở hữu |

`ItemWriter` tự nó không bắt buộc phải lưu state. Writer cần state có thể triển khai `ItemStreamWriter<T>` hoặc interface kết hợp `ItemWriter<T>` và `ItemStream`. Các writer dựng sẵn thường đã triển khai đúng contract.

Trong chunk-oriented step, Spring Batch quản lý các stream được đăng ký với step. Reader và writer trực tiếp thường được đăng ký tự động khi chúng triển khai `ItemStream`. Nếu writer được bọc trong một delegate/composite hoặc được tạo qua adapter, cần xác nhận stream của delegate được đăng ký và lifecycle `open/update/close` được gọi. Có thể đăng ký thêm stream bằng cấu hình `.stream(...)` của step khi cần.

## ExecutionContext và writer checkpoint

Writer state thường được lưu trong step `ExecutionContext`, được quản lý bởi `JobRepository`. Với JDBC repository, step context được lưu trong metadata, thường là bảng `BATCH_STEP_EXECUTION_CONTEXT`.

Các giá trị phù hợp để lưu gồm:

- Số dòng đã ghi thành công.
- Byte offset hoặc record sequence đã commit.
- ID của output segment hiện tại.
- Tên resource hoặc object key của output.
- Version/checksum nhỏ để xác nhận output đang được tiếp tục là đúng phiên bản.

Ví dụ key state do writer quản lý:

```java
private static final String WRITTEN_COUNT_KEY =
        "orderFileWriter.current.count";
```

Tên key cần ổn định qua các lần triển khai nếu execution cũ còn có thể restart. Nên dùng namespace theo tên writer để tránh xung đột với reader hoặc writer khác.

Không lưu toàn bộ output, payload hoặc danh sách item trong context. Chỉ lưu vị trí hoặc tham chiếu cần để tiếp tục. Context lớn làm tăng chi phí serialize, database IO và thời gian restart.

## FlatFileItemWriter hỗ trợ restart

`FlatFileItemWriter` là ví dụ phổ biến về writer có state. Nó ghi item thành các dòng thông qua `LineAggregator` và có thể lưu số dòng đã ghi vào `ExecutionContext` để tiếp tục file sau restart.

Ví dụ cấu hình Spring Batch 5:

```java
@Bean
@StepScope
FlatFileItemWriter<Order> orderFileWriter(
        @Value("#{jobParameters['outputFile']}") String outputFile) {

    return new FlatFileItemWriterBuilder<Order>()
            .name("orderFileWriter")
            .resource(new FileSystemResource(outputFile))
            .encoding("UTF-8")
            .lineAggregator(order -> String.join(
                    ",",
                    order.orderId(),
                    order.customerId(),
                    order.amount().toPlainString()))
            .saveState(true)
            .headerCallback(writer ->
                    writer.write("orderId,customerId,amount"))
            .build();
}
```

Trong ví dụ:

- `.name("orderFileWriter")` đặt tên ổn định để writer xác định key state trong context.
- `.resource(...)` chỉ định file đích.
- `.lineAggregator(...)` chuyển mỗi `Order` thành một dòng.
- `.saveState(true)` bật lưu state để hỗ trợ restart.
- Header được ghi theo lifecycle của writer; khi restart, writer cần nhận ra file đã được tạo và tiếp tục đúng trạng thái.

`outputFile` phải ổn định cho cùng một logical job execution. Nếu mỗi lần restart lại tạo đường dẫn mới có timestamp hoặc UUID khác, writer có thể tạo một file mới thay vì tiếp tục file của execution trước.

Trong production, cần xử lý quoting/escaping đúng định dạng CSV. Ví dụ `String.join` ở trên chỉ minh họa ánh xạ trường; nó không tự escape dấu phẩy, dấu nháy hoặc newline bên trong dữ liệu.

### Vì sao tên writer phải ổn định?

Writer dùng tên để lưu và tìm state trong `ExecutionContext`. Nếu đổi tên `orderFileWriter` thành `orderExportWriter` trong khi execution cũ còn cần restart, writer mới có thể tìm một key khác và không khôi phục được vị trí trước đó.

Giữ tên ổn định giữa các lần triển khai trong thời gian còn execution cần restart. Nếu phải thay đổi tên hoặc format state, cần có kế hoạch chuyển đổi hoặc hoàn tất các execution cũ trước khi triển khai.

### SaveState

`saveState(true)` cho phép writer lưu state vào execution context. Với writer có hỗ trợ restart, nên cấu hình rõ tùy chọn này để thể hiện ý định và tránh vô tình tắt state.

Nếu đặt `saveState(false)`, writer không lưu checkpoint nội bộ theo cơ chế của nó. Khi step restart, writer có thể không biết vị trí cần tiếp tục. Tùy cấu hình file và output, điều này có thể dẫn tới ghi lại từ đầu, append sai vị trí hoặc không thể phục hồi đúng. Chỉ tắt state khi ứng dụng có cơ chế phục hồi khác và đã kiểm thử hành vi đó.

### File phải còn tồn tại khi restart

Execution context chỉ lưu trạng thái, không lưu nội dung file. Nếu file đã bị xóa, di chuyển hoặc thay thế sau khi step thất bại, writer không thể tự tái tạo phần output đã commit chỉ từ số dòng checkpoint.

Hãy giữ file output của execution thất bại trong thời gian cho phép restart. Nếu cần dùng tên file cuối cùng cho consumer, có thể ghi vào file tạm gắn với logical execution rồi chỉ publish/rename sau khi job hoàn thành. Thao tác rename và tính nguyên tử phụ thuộc filesystem hoặc object storage.

## Restart writer diễn ra như thế nào?

Giả sử writer đã ghi và commit hai chunk vào file:

```text
orders-output.csv
  Header
  O-001
  O-002
  O-003
  O-004

Writer checkpoint: 4 data lines committed
```

Sau đó chunk tiếp theo thất bại. Khi restart cùng `JobInstance`, Spring Batch khôi phục step context đã lưu. `FlatFileItemWriter.open(context)` đọc state của writer, nhận biết số dòng đã ghi và mở lại resource theo cơ chế restart của nó. Writer tiếp tục với output mới thay vì ghi lại toàn bộ phần đã commit.

```text
Lần chạy đầu:
  Chunk 1 -> ghi O-001, O-002 -> COMMIT
  Chunk 2 -> ghi O-003, O-004 -> COMMIT
  Chunk 3 -> lỗi -> ROLLBACK

Restart:
  Reader khôi phục input checkpoint
  Writer khôi phục output checkpoint = 4 dòng
  Xử lý lại phần chưa commit
  Ghi tiếp các dòng còn thiếu
```

Kết quả mong muốn là file cuối có đúng header và mỗi output item xuất hiện đúng số lần theo nghiệp vụ. Writer state giúp định vị phần output đã ghi; reader checkpoint xác định phần input cần xử lý lại.

## Writer state và transaction boundary

Writer state phải được cập nhật cùng checkpoint của chunk. Trong chunk thành công, writer ghi output, `ItemStream.update` cập nhật state vào context, repository lưu metadata và transaction commit. Khi rollback, state metadata của chunk chưa commit không được trở thành checkpoint bền vững mới.

Tuy nhiên, cần phân biệt **state trong database** với **side effect thực tế của output resource**. Với JDBC writer dùng cùng datasource/transaction manager với step, business data và checkpoint có thể commit/rollback cùng transaction. Với file hoặc message broker, transaction JDBC không tự động bao phủ mọi thao tác I/O; writer tích hợp phải có cơ chế phù hợp hoặc ứng dụng phải bổ sung idempotency/đối soát.

| Đích writer | State/checkpoint | Điều cần lưu ý khi rollback/restart |
| --- | --- | --- |
| `FlatFileItemWriter` | Số dòng/state file trong context | Dùng writer hỗ trợ transaction/restart, giữ file và đường dẫn ổn định |
| JDBC cùng transaction resource | Thường dựa vào database commit và step checkpoint | Business rows và metadata có thể rollback/commit cùng nhau |
| JDBC datasource khác | Có thể có transaction độc lập | Dùng unique key, upsert hoặc ledger để xử lý ghi lặp |
| Message broker | Offset/sequence/event ID tùy writer | Message có thể đã được broker nhận dù chunk rollback |
| Writer tùy chỉnh | Do ứng dụng định nghĩa trong `ExecutionContext` | Phải đồng bộ state với output commit và xử lý rollback rõ ràng |

## JDBC writer thường không cần writer state riêng

`JdbcBatchItemWriter` thường không cần lưu vị trí dòng hoặc offset như file writer. Nó ghi dữ liệu vào database bằng SQL batch. Khả năng restart an toàn chủ yếu dựa vào transaction của step, checkpoint reader và thiết kế SQL/business key.

Ví dụ:

```java
@Bean
JdbcBatchItemWriter<Order> orderDatabaseWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("""
                    INSERT INTO orders(order_id, customer_id, amount)
                    VALUES (:orderId, :customerId, :amount)
                    """)
            .beanMapped()
            .build();
}
```

Nếu writer và `JobRepository` dùng cùng transaction resource cùng transaction manager, insert chưa commit của chunk sẽ rollback cùng checkpoint. Khi restart, reader đọc lại item thuộc chunk chưa commit và writer thực hiện lại insert.

Nếu database đã commit nhưng metadata/checkpoint ở resource khác chưa commit, cùng item có thể được ghi lại. Hãy dùng unique constraint trên business key, upsert hoặc bảng ledger để chống duplicate. Không nên thêm một bộ đếm writer vào context nếu database đã có cơ chế transaction/idempotency phù hợp.

## Writer tùy chỉnh cần triển khai ItemStream

Nếu writer tự quản lý file position, sequence hoặc trạng thái output, có thể triển khai `ItemStreamWriter<T>`. Writer cần:

1. Khôi phục state trong `open(context)`.
2. Ghi chunk trong `write(chunk)`.
3. Cập nhật checkpoint vào context trong `update(context)`.
4. Đóng resource trong `close()`.

Ví dụ skeleton cho một writer tuần tự:

```java
public class SequenceItemWriter<T> implements ItemStreamWriter<T> {

    private static final String LAST_SEQUENCE_KEY =
            "sequenceWriter.lastCommittedSequence";

    private long lastCommittedSequence;

    @Override
    public void open(ExecutionContext context) {
        lastCommittedSequence = context.getLong(LAST_SEQUENCE_KEY, 0L);
        openOutputAt(lastCommittedSequence);
    }

    @Override
    public void write(Chunk<? extends T> chunk) {
        // Ghi các item vào output theo sequence tiếp theo.
        // Sink phải có semantics transaction/rollback hoặc idempotency phù hợp.
        writeChunkToSink(chunk);
    }

    @Override
    public void update(ExecutionContext context) {
        // Lưu sequence đã được sink xác nhận commit theo contract của sink.
        context.putLong(LAST_SEQUENCE_KEY, lastCommittedSequence);
    }

    @Override
    public void close() {
        closeOutput();
    }
}
```

`openOutputAt`, `writeChunkToSink` và `closeOutput` là các phương thức minh họa do ứng dụng triển khai. Đây là skeleton về lifecycle, không phải một writer hoàn chỉnh có thể sao chép nguyên trạng. Đặc biệt, `lastCommittedSequence` chỉ được cập nhật sau khi output thực sự được xác nhận theo transaction contract. Nếu `write` làm thay đổi field trước commit rồi chunk rollback, writer phải khôi phục state trong memory hoặc dùng sink transaction-aware; chỉ lưu giá trị vào `ExecutionContext` là chưa đủ để làm side effect bên ngoài rollback.

### Tránh state trong memory tiến trước checkpoint

Một lỗi phổ biến là tăng counter trong `write()` rồi giữ counter đó ngay cả khi transaction rollback. Khi chunk được retry trong cùng process, counter trong memory có thể đã tiến lên dù output chưa commit. Writer có thể bỏ qua sequence hoặc ghi lệch vị trí.

Các lựa chọn thiết kế:

- Dùng writer dựng sẵn đã quản lý transaction/state như `FlatFileItemWriter` khi phù hợp.
- Dùng sink có transaction và chỉ xác nhận state sau commit.
- Giữ riêng `committedState` và `pendingState`, khôi phục pending khi rollback qua transaction synchronization phù hợp.
- Thiết kế thao tác ghi idempotent theo sequence/business key để có thể replay an toàn.
- Nếu output không hỗ trợ rollback, ghi staging output rồi publish sau khi step/job hoàn tất.

Không nên triển khai writer stateful chỉ bằng một counter mutable mà không định nghĩa hành vi rollback.

## Đăng ký writer stream trong step

Khi writer trực tiếp được truyền vào `.writer(...)` và triển khai `ItemStream`, Spring Batch thường có thể quản lý lifecycle stream đó. Nhưng với delegate lồng trong `CompositeItemWriter`, adapter hoặc wrapper tùy chỉnh, cần bảo đảm stream bên trong được gọi.

Ví dụ với composite writer:

```java
@Bean
CompositeItemWriter<Order> compositeOrderWriter(
        JdbcBatchItemWriter<Order> databaseWriter,
        FlatFileItemWriter<Order> fileWriter) throws Exception {

    return new CompositeItemWriterBuilder<Order>()
            .delegates(databaseWriter, fileWriter)
            .build();
}
```

Khi dùng composite, kiểm tra implementation/phiên bản Spring Batch có delegate `ItemStream` được forward lifecycle hay không. Nếu wrapper không tự đăng ký delegate stream, đăng ký rõ trong step:

```java
return new StepBuilder("exportOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .writer(compositeOrderWriter)
        .stream(fileWriter)
        .build();
```

Việc đăng ký stream bảo đảm writer delegate nhận `open`, `update` và `close` để lưu/khôi phục state. Không đăng ký stream cần thiết có thể khiến file writer hoạt động trong lần chạy đầu nhưng không có checkpoint hợp lệ cho restart.

## Nhiều writer và nhiều đích output

Một chunk có thể được ghi tới database và file thông qua `CompositeItemWriter`. Khi restart, mỗi delegate có thể có yêu cầu state khác nhau:

- Database writer dựa vào transaction và idempotency.
- File writer cần lưu số dòng/vị trí ghi.
- Message writer cần event ID/sequence và acknowledgement.

Các writer cần được khởi tạo, cập nhật state và đóng đúng lifecycle. Một delegate thất bại có thể khiến chunk rollback theo transaction của step, nhưng side effect ở delegate khác đã ghi ra resource ngoài có thể vẫn tồn tại.

Ví dụ database commit và file output không có atomic transaction chung có thể tạo trạng thái lệch. Khi đó cần staging file, outbox hoặc quy trình đối soát. Composite writer không tự tạo một distributed transaction bao trùm mọi đích.

## File path và JobParameters khi restart

Writer thường nhận resource từ `JobParameters`. Nếu output path thay đổi mỗi lần execution, restart có thể ghi vào một file mới thay vì tiếp tục file cũ.

Ví dụ tham số ổn định:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("outputFile", "/batch/output/orders-2026-11-15.csv", true)
        .toJobParameters();
```

Khi restart cùng `JobInstance`, dùng lại identifying parameters và cùng output path. Nếu mỗi lần chạy nghiệp vụ phải tạo một file mới, hãy tạo logical run mới có chủ đích với identifying parameter mang ý nghĩa nghiệp vụ, đồng thời định nghĩa rõ cách xử lý file cũ.

Không dùng timestamp mới hoặc UUID mới ở lần restart chỉ để tạo file khác. Việc đó có thể tạo `JobInstance` mới và làm mất liên kết với writer checkpoint đã lưu.

Nếu output path là non-identifying parameter, cần bảo đảm lần restart vẫn truyền đúng giá trị ban đầu. Cùng một identifying parameter nhưng output path khác có thể khiến job tiếp tục với checkpoint cũ nhưng ghi sang resource khác, dẫn đến file không đầy đủ. Có thể dùng path như identifying parameter hoặc lưu/kiểm tra path ổn định trong context.

## Writer state và restart với file đã tồn tại

Khi restart, writer cần phân biệt:

- Lần chạy mới chưa có state: áp dụng chính sách tạo file mới hoặc xử lý file tồn tại theo cấu hình.
- Lần restart có state: mở lại file đã tạo và tiếp tục theo checkpoint.
- File bị xóa hoặc thay thế: state không còn khớp resource; cần báo lỗi hoặc phục hồi theo quy trình rõ ràng.

Không nên bật append một cách máy móc. Append có thể phù hợp cho một số luồng ghi, nhưng nếu checkpoint đã lưu số dòng và file đã chứa output trước đó, append không đúng cách có thể tạo duplicate. Dùng cơ chế restart state của writer và kiểm thử trên filesystem thực tế.

Nếu file output cần được consumer sử dụng, tránh để consumer đọc file chưa hoàn tất. Có thể tạo file tạm theo execution, sau đó đổi tên hoặc publish manifest sau khi step/job thành công. Nếu job thất bại, giữ file tạm đủ lâu để restart hoặc cleanup theo retention.

## Restart của writer và exactly-once

Writer state giúp khôi phục vị trí output, nhưng không tự bảo đảm exactly-once trên mọi hệ thống. Exactly-once phụ thuộc khả năng phối hợp transaction giữa business data, metadata và đích output.

Một số tình huống:

| Tình huống | Rủi ro | Cách giảm rủi ro |
| --- | --- | --- |
| File ghi thành công nhưng checkpoint chưa commit | Restart có thể ghi lại output | Writer transaction-aware, state file nhất quán hoặc staging/publish |
| Database commit cùng checkpoint | Hai thay đổi có thể commit/rollback cùng nhau | Dùng chung datasource/transaction manager phù hợp |
| Database khác repository | Một bên commit, bên kia rollback | Unique key, upsert, ledger và đối soát |
| Message đã được broker nhận rồi chunk rollback | Message có thể được gửi lại | Event ID ổn định và idempotent consumer; cân nhắc outbox |
| Writer gọi API trước khi commit | API đã xử lý dù chunk rollback | Idempotency key hoặc tách side effect sang bước sau |

Đừng mô tả một writer là exactly-once chỉ vì nó triển khai `ItemStream`. `ItemStream` cung cấp cơ chế lưu/khôi phục state; tính đúng đắn của side effect còn phụ thuộc resource và transaction semantics.

## Writer state trong partitioned hoặc parallel step

Khi step chạy song song theo partition hoặc nhiều flow, mỗi execution có thể cần writer state riêng. Không nên để nhiều worker cùng ghi và cập nhật một key state hoặc một file mà không có cơ chế đồng bộ.

Các nguyên tắc:

- Dùng step-scoped writer hoặc writer instance riêng cho từng partition khi phù hợp.
- Đặt tên/key state duy nhất theo partition nếu component tự quản lý context key.
- Mỗi partition nên có output resource riêng, sau đó hợp nhất ở step sau nếu cần.
- Nếu nhiều partition ghi cùng database table, dùng business key và transaction isolation phù hợp.
- Không chia sẻ mutable counter giữa các writer trên nhiều thread nếu không thread-safe.
- Khi tổng hợp output, chỉ publish sau khi tất cả partition cần thiết hoàn tất.

Nếu nhiều partition cùng ghi một file, cần một thiết kế đồng bộ riêng; `FlatFileItemWriter` không nên được giả định là một writer thread-safe dùng chung cho mọi worker. Tách file theo partition thường dễ restart và đối soát hơn.

## Những lỗi thường gặp

### Chỉ checkpoint reader mà bỏ qua writer state

Reader tiếp tục đúng vị trí nhưng file writer có thể ghi lại từ đầu hoặc không biết vị trí output. Dùng writer hỗ trợ `ItemStream` hoặc thiết kế output idempotent.

### Đổi tên writer giữa các lần triển khai

Key trong `ExecutionContext` có thể thay đổi và writer không tìm thấy state cũ. Giữ tên ổn định khi execution còn có thể restart.

### Đặt `saveState(false)` nhưng vẫn mong writer resume

Writer không lưu state nội bộ; restart có thể không tiếp tục đúng vị trí. Chỉ tắt khi có cơ chế khác đã được kiểm thử.

### Thay output path ở lần restart

Writer có thể tạo file mới nhưng dùng checkpoint cũ hoặc không tìm thấy file cần tiếp tục. Dùng path ổn định cho cùng logical execution.

### Quên đăng ký delegate ItemStream

Writer bọc trong composite/wrapper có thể không nhận lifecycle nếu stream delegate không được forward hoặc đăng ký. Xác nhận `open/update/close` thực sự được gọi.

### Tăng counter trong write rồi không phục hồi khi rollback

State trong memory có thể tiến trước checkpoint bền vững. Dùng transaction-aware sink, committed/pending state hoặc idempotency.

### Cho rằng database writer luôn cần state riêng

`JdbcBatchItemWriter` thường dựa vào transaction và business key. Thêm state không cần thiết có thể làm thiết kế phức tạp mà không giải quyết được duplicate giữa hai resource.

### Giả định ItemStream bảo đảm exactly-once

ItemStream chỉ quản lý state lifecycle. File, message và API vẫn có thể có side effect ngoài transaction; cần idempotency hoặc outbox.

### Xóa file output sau khi job thất bại

Writer state còn tham chiếu tới output đã mất. Giữ resource trong thời gian restart hoặc chủ động reset job/output theo quy trình nghiệp vụ.

## Kiểm thử restart với writer state

Kiểm thử quan trọng nhất là mô phỏng một lần chạy đã commit một phần output, sau đó thất bại và restart cùng logical job. Test phải xác nhận cả output lẫn metadata.

### Kiểm thử FlatFileItemWriter

Một integration test có thể thực hiện:

1. Tạo input có nhiều chunk.
2. Dùng `FlatFileItemWriter` ghi vào file tạm với `.saveState(true)` và tên ổn định.
3. Cho một số chunk đầu commit.
4. Làm step thất bại ở chunk tiếp theo bằng lỗi có kiểm soát.
5. Xác nhận file có output của các chunk đã commit.
6. Restart cùng identifying `JobParameters` và cùng output path.
7. Xác nhận writer khôi phục state và ghi phần output còn thiếu.
8. Đọc file cuối, xác nhận header, số dòng, thứ tự và không có duplicate/missing record.

Test cần dùng một failure fixture xác định, không dựa vào timing ngẫu nhiên. Có thể dùng processor test double ném exception ở business key cụ thể trong lần chạy đầu, sau đó cho phép xử lý thành công ở lần restart.

### Kiểm thử writer state qua ItemStream

Với writer tự triển khai, kiểm tra:

- `open` đọc được key state đã lưu.
- `update` ghi đúng committed position vào context.
- Key state không bị trùng với component khác.
- Rollback không làm state trong memory tiến vượt checkpoint.
- Restart dùng cùng writer name/key và khôi phục đúng vị trí.
- Resource đích tồn tại và đúng version.

Không chỉ unit test `open` và `update`; cần integration test để xác nhận repository thực sự lưu context và transaction rollback không lưu checkpoint của chunk thất bại.

### Kiểm thử JDBC writer

Với JDBC writer, test cần xác nhận transaction và idempotency:

- Chunk lỗi rollback các insert chưa commit khi cùng transaction resource.
- Chunk trước đã commit vẫn tồn tại.
- Restart không tạo duplicate theo business key.
- Khi metadata và business database tách biệt, mô phỏng lỗi một phía commit để xác nhận ledger/upsert xử lý replay.

### Kiểm thử delegate/composite

Nếu dùng composite writer, xác nhận tất cả delegate cần state đều được mở, cập nhật và đóng. Làm một lần chạy rồi restart để bảo đảm writer delegate không bắt đầu lại từ đầu hoặc append sai vị trí.

## Ví dụ kiểm tra metadata và output

`JobExplorer` có thể truy vấn `JobExecution` và `StepExecution` đã lưu; `JdbcTemplate` hoặc API file có thể kiểm tra output thực tế.

```java
JobExecution persisted = jobExplorer.getJobExecution(executionId);
assertNotNull(persisted);

StepExecution stepExecution = persisted.getStepExecutions()
        .stream()
        .filter(step -> step.getStepName().equals("exportOrdersStep"))
        .findFirst()
        .orElseThrow();

assertEquals(BatchStatus.COMPLETED, stepExecution.getStatus());
assertEquals(expectedWriteCount, stepExecution.getWriteCount());
```

Sau đó đọc file và so sánh danh sách order ID với expected output. `writeCount` chỉ là metadata counter; nó không thay thế kiểm tra nội dung file. Nếu writer ghi database, query bảng đích và xác nhận business key/values.

Trong test restart, giữ nguyên identifying parameters giữa lần chạy đầu và lần restart. Với test độc lập khác, tạo `testRunId` riêng để tránh `JobInstanceAlreadyCompleteException`. Dọn file và business data riêng; cleanup batch metadata bằng tiện ích phù hợp nhưng không xóa execution mà test restart cần dùng.

## Các bước chẩn đoán khi writer không resume đúng

Nếu restart tạo file trùng, thiếu dòng hoặc writer bắt đầu sai vị trí, kiểm tra theo thứ tự:

1. Writer có triển khai `ItemStream` hoặc implementation dựng sẵn có hỗ trợ state không?
2. `saveState` có được bật không?
3. Writer name có giữ nguyên qua lần chạy và restart không?
4. Stream delegate có được đăng ký trong step không?
5. Job restart có dùng cùng identifying parameters không?
6. Output resource path có giống lần chạy đầu không?
7. File/output resource có còn tồn tại và đúng version không?
8. Checkpoint được lưu cùng transaction commit hay ở resource độc lập?
9. Có side effect ngoài transaction đã xảy ra trước khi rollback không?
10. Writer state trong memory có được phục hồi đúng sau rollback trong cùng process không?

Không nên sửa trực tiếp serialized `ExecutionContext` trong bảng `BATCH_*` để ép writer tiếp tục. Hãy xác định nguyên nhân, dùng API/metadata để quan sát và áp dụng quy trình restart hoặc reset output được kiểm soát.

## Nguyên tắc thiết kế writer state

Khi thiết kế writer có restart, hãy thống nhất:

1. Writer có thực sự cần state riêng hay transaction/idempotency của đích đã đủ?
2. State mô tả output đã commit tới đâu?
3. Writer triển khai `ItemStream` và được step quản lý lifecycle đầy đủ chưa?
4. Writer name và context key có ổn định qua các lần triển khai không?
5. `saveState` có bật khi cần restart không?
6. Output path/resource có ổn định và tồn tại trong thời gian restart không?
7. State update có nhất quán với transaction của output không?
8. Rollback có khôi phục cả state trong memory và output resource không?
9. Writer có thể được gọi lại an toàn sau retry/restart không?
10. Composite/delegate/partition có đăng ký stream và cô lập state đúng không?
11. Integration test đã xác nhận output cuối không thiếu hoặc trùng chưa?

Ưu tiên writer dựng sẵn có hỗ trợ restart khi phù hợp. Với writer tùy chỉnh, thiết kế committed state, pending state và transaction semantics trước khi triển khai. Nếu output không hỗ trợ rollback, hãy dùng staging, idempotency hoặc quy trình publish riêng để phục hồi an toàn.

## Ghi nhớ

Restart với writer state cho phép writer khôi phục vị trí output đã commit thông qua `ItemStream` và step `ExecutionContext`. `open` đọc state, `write` ghi chunk, `update` lưu checkpoint và `close` giải phóng resource. `FlatFileItemWriter` hỗ trợ state với tên writer ổn định và `saveState(true)`; giữ nguyên output path và file trong thời gian restart. JDBC writer thường dựa vào transaction cùng business key/idempotency thay vì một offset riêng. Với writer tùy chỉnh hoặc composite, phải đăng ký stream đầy đủ và bảo đảm state trong memory không tiến trước output commit. Writer state không tự bảo đảm exactly-once cho file, message hay API; cần transaction-aware sink, idempotency, outbox hoặc staging/publish. Kiểm thử bằng cách commit một phần output, làm step thất bại, restart cùng identifying parameters rồi xác nhận output cuối không thiếu hoặc trùng.
