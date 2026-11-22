# Fault-tolerant chunk và checkpoint

Trong Spring Batch, chunk-oriented processing chia dữ liệu thành các nhóm item. Mỗi chunk được xử lý trong một transaction và chỉ được xem là hoàn tất khi các thao tác cần thiết của chunk thành công, metadata/checkpoint được cập nhật và transaction commit. Khi reader, processor hoặc writer gặp lỗi, transaction hiện tại có thể rollback; Spring Batch áp dụng retry/skip policy nếu step được cấu hình, còn checkpoint đã commit trước đó là mốc an toàn để restart.

**Checkpoint** là trạng thái bền vững cho biết step đã xử lý tới đâu. Với reader và writer hỗ trợ `ItemStream`, Spring Batch lưu state vào step `ExecutionContext` tại các điểm commit. Nếu tiến trình dừng đột ngột, lần restart có thể khôi phục state từ checkpoint đã commit và tiếp tục phần công việc chưa hoàn tất.

Fault tolerance và checkpoint có quan hệ chặt chẽ: retry/skip quyết định cách xử lý lỗi trong lần chạy hiện tại; checkpoint quyết định phần tiến trình nào đã được xác nhận bền vững khi transaction commit. Thiết kế đúng cần bảo đảm dữ liệu nghiệp vụ, metadata, reader state và side effect bên ngoài có thể phục hồi nhất quán.

## Chunk transaction và checkpoint

Một chunk step thường thực hiện các công việc theo thứ tự khái quát:

1. Bắt đầu transaction cho chunk.
2. Reader lấy các item đầu vào cho chunk.
3. Processor chuyển đổi, kiểm tra hoặc filter từng item.
4. Writer ghi các output được chấp nhận.
5. Các thành phần `ItemStream` cập nhật state vào `ExecutionContext`.
6. Spring Batch cập nhật `StepExecution` và lưu execution context qua `JobRepository`.
7. Transaction commit.

```text
              Chunk transaction
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
           ItemStream.update(context)
                     |
                     v
       Save StepExecution / ExecutionContext
                     |
                     v
                   COMMIT
                     |
                     v
           Checkpoint bền vững mới
```

Sơ đồ mô tả lifecycle ở mức khái niệm. Chi tiết callback và thứ tự nội bộ có thể khác theo loại step và phiên bản, nhưng nguyên tắc quan trọng là checkpoint phải đại diện cho phần dữ liệu đã được commit.

Nếu chunk commit thành công, các thay đổi nghiệp vụ và checkpoint tham gia cùng transaction resource có thể được lưu cùng nhau. Nếu chunk rollback, các thay đổi chưa commit trong transaction đó không được giữ lại và checkpoint bền vững vẫn là checkpoint trước đó.

### Checkpoint không phải trạng thái trong memory

Một biến field trong reader như `currentLine` chỉ tồn tại trong object đang chạy. Nếu tiến trình JVM dừng, biến đó mất. Checkpoint trong `ExecutionContext` được lưu trong repository nên có thể được khôi phục sau khi ứng dụng khởi động lại.

Ví dụ reader có thể lưu số dòng tiếp theo cần đọc, page number hoặc khóa cuối đã xử lý. Không nên chỉ dựa vào một counter trong memory rồi giả định Spring Batch tự biết vị trí cần restart.

## Điều gì xảy ra khi chunk gặp exception?

Giả sử chunk size là 3. Reader cung cấp ba đơn hàng; processor xử lý hai item đầu và ném exception ở item thứ ba.

```text
Chunk hiện tại: [O-1, O-2, O-3]

Reader       Processor          Writer
  |              |                 |
  |-- O-1 ------>|-- O-1'           |
  |-- O-2 ------>|-- O-2'           |
  |-- O-3 ------>|                 |
  |              |-- exception     |
  |              X                 |
                 |
                 v
          ROLLBACK chunk
                 |
                 v
      Checkpoint đã commit trước đó
      vẫn là mốc phục hồi
```

Nếu exception không được xử lý bởi retry hoặc skip policy:

- Transaction của chunk hiện tại rollback theo rollback rule.
- Writer không nhận chunk hoàn chỉnh vì quá trình process dừng trước giai đoạn ghi.
- Các thay đổi database tham gia transaction hiện tại được rollback.
- Checkpoint đã commit trước đó vẫn còn.
- Step thường kết thúc `FAILED`.
- Các chunk trước đó đã commit vẫn được giữ lại.

Nếu exception được retry hoặc skip, framework có thể thực hiện thêm các lần xử lý theo fault-tolerance policy. Processor có thể được gọi lại cho cùng item; một chunk có thể rollback trước khi retry hoặc xác định item bị skip. Vì vậy processor cần an toàn khi được gọi lại.

## Rollback chunk hiện tại không rollback toàn bộ job

Mỗi chunk có transaction riêng. Ví dụ job xử lý 10.000 item với chunk size 100. Nếu 20 chunk đầu đã commit và chunk thứ 21 gặp lỗi không thể phục hồi, dữ liệu của 20 chunk đầu vẫn tồn tại.

| Phần xử lý | Trạng thái sau khi chunk 21 thất bại |
| --- | --- |
| Chunk 1–20 | Đã commit; business data và checkpoint tương ứng vẫn tồn tại |
| Chunk 21 | Transaction hiện tại rollback nếu lỗi kích hoạt rollback |
| Chunk 22 trở đi | Chưa được xử lý |

Đây là cơ sở để restart tiếp tục từ checkpoint cuối cùng đã commit. Nếu nghiệp vụ yêu cầu toàn bộ job chỉ được công bố kết quả khi tất cả item thành công, có thể ghi vào staging table hoặc file tạm rồi thực hiện bước publish sau khi các step xử lý hoàn tất.

Không nên coi một `JobExecution` là một transaction duy nhất. Trạng thái `FAILED` không có nghĩa mọi thay đổi nghiệp vụ của job đã rollback.

## Checkpoint được lưu trong ExecutionContext

`ExecutionContext` là map key-value gắn với `StepExecution` hoặc `JobExecution`. Reader và writer có thể dùng step context để lưu trạng thái cần thiết cho restart.

Với reader, các giá trị thường gặp gồm:

- Vị trí dòng hiện tại hoặc offset của file.
- Page number hoặc index tiếp theo.
- Khóa cuối đã đọc/đã xử lý trong một truy vấn có thứ tự ổn định.
- Tên file, version hoặc checksum của nguồn dữ liệu.
- Một số metadata nhỏ cần để tiếp tục đọc đúng nguồn.

Ví dụ cập nhật context:

```java
ExecutionContext context =
        stepExecution.getExecutionContext();

context.putLong("lastCommittedOrderId", lastCommittedOrderId);
context.putString("sourceVersion", sourceVersion);
```

Chỉ lưu những giá trị nhỏ cần để khôi phục tiến trình. Không lưu toàn bộ danh sách item, entity graph, file bytes hoặc payload lớn vào context; những dữ liệu đó nên nằm ở database, staging table hoặc object storage, còn context chỉ giữ ID/URI/version.

## ItemStream và lifecycle của reader/writer

`ItemStream` cung cấp lifecycle để thành phần lưu và khôi phục state:

```java
public interface ItemStream {
    void open(ExecutionContext executionContext);
    void update(ExecutionContext executionContext);
    void close();
}
```

Reader/writer cần lưu state có thể triển khai `ItemStream` hoặc dùng implementation dựng sẵn đã hỗ trợ stream. Ba phương thức có vai trò:

| Phương thức | Vai trò |
| --- | --- |
| `open(context)` | Khôi phục state từ execution context khi step bắt đầu hoặc restart |
| `update(context)` | Ghi state hiện tại vào context tại checkpoint |
| `close()` | Đóng resource và giải phóng tài nguyên |

Với chunk step, Spring Batch gọi `update` tại các điểm lưu state trong lifecycle chunk. State được lưu cùng metadata theo transaction/repository configuration. Khi rollback, checkpoint bền vững không nên tiến qua phần dữ liệu chưa commit.

### Ví dụ reader tự triển khai

Ví dụ sau minh họa ý tưởng lưu khóa tiếp tục. Phần truy vấn và cách cập nhật khóa cần được triển khai sao cho state phản ánh đúng item thuộc chunk đã commit.

```java
public class OrderReader implements ItemStreamReader<OrderInput> {

    private long lastCommittedOrderId;

    @Override
    public void open(ExecutionContext context) {
        lastCommittedOrderId =
                context.getLong("lastCommittedOrderId", 0L);
    }

    @Override
    public OrderInput read() {
        return readNextOrderAfter(lastCommittedOrderId);
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong("lastCommittedOrderId", lastCommittedOrderId);
    }

    @Override
    public void close() {
        // Đóng cursor/resource nếu reader đang giữ resource.
    }
}
```

`readNextOrderAfter(...)` là phần truy vấn do ứng dụng định nghĩa. Reader thực tế phải cập nhật state theo quy tắc xử lý/commit của chunk, không đơn thuần tăng khóa trong memory rồi giả định giá trị đó đã commit. Khi dùng reader dựng sẵn, ưu tiên cơ chế checkpoint tích hợp của nó thay vì tự viết lại state management.

## Reader buffering khi rollback

Một reader thông thường có thể đọc dữ liệu từ nguồn không tham gia transaction, chẳng hạn file hoặc API. Nếu chunk rollback, các item đã đọc không thể được trả ngược về file hoặc API một cách tự nhiên.

Để hỗ trợ xử lý lại, Spring Batch mặc định buffer các item đã đọc trong chunk. Khi rollback xảy ra, framework có thể sử dụng lại các item đã buffer thay vì yêu cầu reader đọc nguồn lần nữa ngay lập tức. Điều này giúp tránh việc bỏ mất item chỉ vì con trỏ nguồn đã tiến lên.

Ví dụ:

```text
Nguồn file: O-1, O-2, O-3, O-4, O-5, ...

Reader đọc O-1, O-2, O-3
          |
          v
     Processor lỗi
          |
          v
      ROLLBACK
          |
          v
Spring Batch dùng lại item đã buffer
trong quá trình xử lý lại/fault tolerance
```

Buffer này là cơ chế trong quá trình xử lý, không thay thế checkpoint bền vững. Khi JVM dừng, buffer trong memory mất; restart dựa vào state đã lưu trong `ExecutionContext` và khả năng restart của reader.

Không nên tự giả định mọi reader đều có cùng hành vi. Reader tự triển khai, reader transactional và reader không hỗ trợ `ItemStream` có thể có semantics khác. Hãy kiểm tra hợp đồng của reader đang sử dụng.

## Reader từ transactional queue

Một số reader đọc từ nguồn transactional như JMS queue. Khi transaction rollback, message đã nhận có thể được trả về queue theo semantics của resource. Trong trường hợp đó, buffer nội bộ của Spring Batch có thể không phù hợp vì queue đã có cơ chế rollback/receive lại riêng.

Spring Batch cung cấp cấu hình `readerIsTransactionalQueue()` trên fault-tolerant chunk builder để báo rằng reader lấy item từ transactional queue và không cần buffer item theo cách thông thường.

```java
@Bean
Step consumeMessagesStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderMessage> messageReader,
        ItemProcessor<OrderMessage, OrderEvent> processor,
        ItemWriter<OrderEvent> eventWriter) {

    return new StepBuilder("consumeMessagesStep", jobRepository)
            .<OrderMessage, OrderEvent>chunk(50, transactionManager)
            .reader(messageReader)
            .processor(processor)
            .writer(eventWriter)
            .faultTolerant()
            .readerIsTransactionalQueue()
            .build();
}
```

Tên API và cấu hình transaction cần phù hợp với phiên bản Spring Batch và middleware đang dùng. Chỉ bật `readerIsTransactionalQueue()` khi nguồn đọc thực sự có semantics transactional phù hợp; không dùng nó cho file reader hoặc API reader thông thường.

Với queue, cần xác nhận transaction manager có phối hợp đúng với session/connection của broker. Nếu broker transaction và database transaction là hai resource độc lập, rollback của database không tự động trả message hoặc ngược lại. Có thể cần XA, outbox/inbox hoặc idempotent consumer tùy yêu cầu.

## Reader và writer dựng sẵn hỗ trợ checkpoint

Nhiều reader/writer Spring Batch được cung cấp đã triển khai `ItemStream` và lưu state. Ví dụ:

- `FlatFileItemReader` lưu vị trí đọc trong file.
- `JdbcPagingItemReader` lưu thông tin paging cần thiết để tiếp tục.
- `JdbcCursorItemReader` có cơ chế state riêng tùy cấu hình và khả năng restart.
- `FlatFileItemWriter` lưu trạng thái ghi để hỗ trợ restart.

Khi cấu hình các component này, cần đặt tên ổn định và kiểm tra `saveState` theo yêu cầu restart.

```java
@Bean
@StepScope
FlatFileItemReader<OrderInput> orderReader(
        @Value("${batch.input.orders}") Resource inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(inputFile)
            .delimited()
            .names("orderId", "amount")
            .fieldSetMapper(fields -> new OrderInput(
                    fields.readString("orderId"),
                    fields.readBigDecimal("amount")))
            .saveState(true)
            .build();
}
```

`saveState(true)` bật lưu state của reader để hỗ trợ restart. Nếu tắt state hoặc dùng reader không có checkpoint phù hợp, step có thể không tiếp tục từ vị trí cũ sau khi JVM dừng. Cần hiểu semantics cụ thể của từng reader; không phải mọi reader có cùng cách xác định vị trí an toàn.

## Tên reader/writer và state ổn định

Các component lưu state thường dùng tên để tạo key trong `ExecutionContext`. Tên cần ổn định và duy nhất trong phạm vi phù hợp.

Ví dụ:

```java
.name("orderReader")
```

Không nên thay tên reader tùy tiện khi còn job execution cũ cần restart, vì key state có thể thay đổi và reader không tìm thấy checkpoint trước đó. Nếu hai reader cùng step dùng tên trùng, state có thể xung đột hoặc khó khôi phục.

Đối với custom `ItemStream`, dùng key có namespace rõ ràng, tránh trùng với key của component khác. Duy trì tương thích key và kiểu dữ liệu khi triển khai phiên bản mới trong lúc còn execution chờ restart.

## Fault tolerance: retry và skip ảnh hưởng checkpoint ra sao?

Fault-tolerant chunk step có thể xử lý exception bằng retry hoặc skip. Các policy này quyết định cách tiếp tục trong lần chạy hiện tại, còn checkpoint vẫn gắn với transaction commit.

### Retry

Retry phù hợp với lỗi tạm thời có thể phục hồi, chẳng hạn deadlock hoặc timeout của dịch vụ tra cứu.

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retry(TransientLookupException.class)
        .retryLimit(3)
        .build();
```

Nếu processor được gọi lại cho cùng item, mọi side effect không idempotent có thể lặp. Processor nên tập trung vào transformation; nếu cần gọi dịch vụ ngoài, dùng idempotency key hoặc cơ chế truy vấn trạng thái.

Retry không tạo checkpoint commit riêng cho từng attempt. Chunk chỉ tiến tới checkpoint mới khi transaction xử lý chunk cuối cùng hoàn tất theo lifecycle của step.

### Skip

Skip phù hợp với lỗi dữ liệu mà nghiệp vụ cho phép bỏ qua:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(50)
        .build();
```

Khi exception được phép skip và chưa vượt giới hạn, item lỗi có thể bị loại khỏi output và các item còn lại được ghi theo fault-tolerance processing. Framework có thể rollback và xử lý lại/scan item trong chunk để xác định item gây lỗi. Do đó reader/processor có thể được gọi lại; side effect phải an toàn khi lặp.

Skip không có nghĩa checkpoint được tiến lên ngay khi exception xuất hiện. Checkpoint của chunk vẫn được cập nhật tại commit point. Nếu vượt `skipLimit`, step thất bại; chunk hiện tại có thể rollback trong khi các chunk trước đã commit vẫn tồn tại.

### Filtering

Processor trả `null` để filter một item hợp lệ nhưng không cần output. Filtering không phải exception, không kích hoạt retry/skip và không tiêu thụ `skipLimit`. `filterCount` được ghi riêng trong `StepExecution`.

| Kết quả processor | Ý nghĩa | Ảnh hưởng checkpoint |
| --- | --- | --- |
| Trả object | Output hợp lệ | Được đưa vào writer của chunk |
| Trả `null` | Filter có chủ đích | Item không tới writer; chunk vẫn có thể commit |
| Ném exception được retry | Lỗi tạm thời | Thử lại theo policy; checkpoint chỉ tiến khi chunk hoàn tất |
| Ném exception được skip | Lỗi được phép bỏ qua | Item được bỏ qua theo policy; chunk hoàn tất thì checkpoint mới được lưu |
| Ném exception không được xử lý | Lỗi làm step dừng | Chunk rollback; checkpoint bền vững vẫn ở commit point trước |

## Commit interval và phạm vi công việc phải xử lý lại

Commit interval quyết định số item tối đa trong một chunk. Chunk lớn thường giảm số lần commit và có thể tăng hiệu quả batch write, nhưng transaction lâu hơn và phạm vi công việc có thể phải xử lý lại lớn hơn khi rollback.

Chunk nhỏ thường:

- Commit thường xuyên hơn.
- Tạo checkpoint thường xuyên hơn.
- Giảm số item trong transaction bị rollback.
- Tăng overhead transaction và repository metadata.

Chunk lớn thường:

- Giảm số lần commit.
- Có thể cải thiện batch write throughput.
- Giữ transaction và lock lâu hơn.
- Tăng lượng item cần đọc/process lại khi rollback hoặc restart từ checkpoint trước.

Ví dụ, nếu chunk size là 1.000 và processor lỗi ở item cuối, có thể phải xử lý lại phần lớn chunk đó tùy reader/fault-tolerance behavior. Nếu chunk size là 100, phạm vi transaction nhỏ hơn nhưng số lần commit nhiều hơn.

Chọn commit interval bằng đo lường thực tế: thời gian reader/processor/writer, lock duration, connection pool, throughput, memory và yêu cầu restart. Không có một con số tối ưu cho mọi job.

## Restart sau khi tiến trình dừng đột ngột

Rollback trong cùng process và restart sau khi process chết là hai tình huống liên quan nhưng khác nhau.

### Lỗi khi JVM vẫn đang chạy

Nếu processor ném exception và step xử lý lỗi, transaction hiện tại rollback. Framework có thể tiếp tục retry/skip hoặc đánh dấu step thất bại. Reader và processor có thể được gọi lại trong cùng execution theo policy.

### JVM hoặc máy chủ dừng đột ngột

Nếu process chết trước commit, transaction database chưa commit sẽ được database rollback khi connection/session được giải phóng. Metadata checkpoint của chunk chưa commit không được xem là mốc tiến trình mới. Khi restart, Spring Batch đọc checkpoint đã lưu ở commit point trước đó.

```text
Chunk 1 -> COMMIT -> checkpoint 100
Chunk 2 -> COMMIT -> checkpoint 200
Chunk 3 -> đang xử lý -> process bị kill

Restart:
  khôi phục checkpoint 200
  đọc/xử lý lại phần sau item 200
```

Nếu writer đã tạo side effect ở hệ thống ngoài trước khi process chết, side effect đó có thể tồn tại dù transaction database chưa commit. Khi restart, cùng item có thể được gửi lại. Dùng idempotency key, outbox hoặc đối soát theo business key.

## Identifying JobParameters khi restart

Để restart cùng logical job, cần giữ nguyên identifying parameters để Spring Batch tìm đúng `JobInstance`. Restart tạo `JobExecution` mới cho cùng instance khi trạng thái và cấu hình cho phép.

Ví dụ:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("sourceFile", "orders-2026-11-15.csv", true)
        .toJobParameters();
```

Khi restart, dùng lại cùng giá trị identifying. Không thêm timestamp hoặc UUID identifying mới nếu mục tiêu là tiếp tục execution đã thất bại; làm vậy sẽ tạo `JobInstance` mới và có thể đọc lại dữ liệu từ đầu.

Nếu nội dung file nguồn có thể thay đổi, nên kiểm tra version/checksum hoặc dùng resource immutable. Cùng đường dẫn nhưng nội dung khác có thể khiến restart xử lý một tập dữ liệu khác với lần chạy đầu.

## Business data và checkpoint phải nhất quán

`JobRepository` lưu batch metadata; writer lưu business data. Khi cả hai dùng cùng transaction resource và transaction manager phù hợp, business changes và checkpoint của chunk có thể commit/rollback cùng nhau.

Nếu writer ghi business data ở database khác với repository, hai local transaction không tự động atomic. Có thể xảy ra:

- Business data commit nhưng checkpoint rollback: restart có thể ghi lại cùng item.
- Checkpoint commit nhưng business data chưa commit: restart có thể bỏ qua item chưa được lưu.

Trong trường hợp tách resource, cần thiết kế writer idempotent theo business key, unique constraint, upsert hoặc business processing ledger. Nếu job phát message, transactional outbox giúp lưu event cùng business transaction rồi publisher gửi lại an toàn.

Không nên dựa vào checkpoint để chứng minh side effect ngoài database đã hoàn tất. Checkpoint chỉ phản ánh state được quản lý bởi repository/transaction; file, API và broker cần cơ chế riêng.

## Thiết kế writer idempotent

Khi retry hoặc restart, cùng một item có thể được gửi tới writer nhiều lần. Writer idempotent bảo đảm việc áp dụng lại cùng yêu cầu không tạo thêm tác động nghiệp vụ ngoài ý muốn.

Một số cách:

- Dùng unique business key và insert/upsert có điều kiện.
- Ghi processing ledger với khóa item ổn định.
- Dùng idempotency key cho API.
- Gắn event ID ổn định cho message và để consumer loại duplicate.
- Dùng outbox để tách việc commit business data khỏi publish message.

Ví dụ PostgreSQL upsert:

```sql
INSERT INTO processed_order (order_id, amount)
VALUES (:orderId, :amount)
ON CONFLICT (order_id)
DO UPDATE SET amount = EXCLUDED.amount;
```

Upsert chỉ phù hợp nếu ghi lại cùng `order_id` là hành vi nghiệp vụ hợp lệ. Nếu dữ liệu mới hơn không được ghi đè, cần thêm điều kiện version hoặc thời điểm cập nhật.

## Kiểm thử fault-tolerant chunk và checkpoint

Unit test processor chỉ chứng minh logic trả output hoặc ném exception. Để kiểm tra rollback/checkpoint, cần integration test với `JobRepository`, transaction manager và resource thực tế hoặc test database tương đương.

Các câu hỏi test nên trả lời:

1. Chunk thành công có ghi business data và checkpoint không?
2. Processor exception không được xử lý có rollback chunk hiện tại không?
3. Chunk trước đã commit có còn dữ liệu không?
4. Retry có gọi lại processor theo policy không?
5. Skip có tăng đúng counter và cho phép các item còn lại tiếp tục không?
6. Reader có khôi phục state từ checkpoint đã commit không?
7. Restart có dùng cùng identifying parameters không?
8. Writer có tạo duplicate khi item được xử lý lại không?

### Kiểm thử rollback chunk

Giả sử chunk size là 2, bốn input gồm hai item hợp lệ đầu tiên và item thứ ba không hợp lệ. Processor ném exception ở item thứ ba, không có skip/retry policy. Writer ghi vào bảng `processed_order` cùng transaction manager với step.

```text
Chunk 1: O-1, O-2 -> writer -> COMMIT
Chunk 2: O-3 lỗi -> ROLLBACK
Kết quả mong đợi: chỉ có O-1, O-2 trong bảng đích
```

Ví dụ assertion với `JobLauncherTestUtils`:

```java
@SpringBootTest
@SpringBatchTest
class FaultTolerantCheckpointTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    @Qualifier("processorFailureJob")
    private Job processorFailureJob;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @BeforeEach
    void setUp() {
        jobLauncherTestUtils.setJob(processorFailureJob);
        jdbcTemplate.update("DELETE FROM processed_order");
    }

    @Test
    void keepsEarlierCommittedChunkAndRollsBackFailingChunk() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("testRunId", UUID.randomUUID().toString(), true)
                .toJobParameters();

        JobExecution execution =
                jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.FAILED, execution.getStatus());

        List<String> ids = jdbcTemplate.queryForList(
                "SELECT order_id FROM processed_order ORDER BY order_id",
                String.class);

        assertEquals(List.of("O-1", "O-2"), ids);
    }
}
```

Đây là fixture minh họa. Job test cần reader, processor và writer được cấu hình đúng thứ tự dữ liệu/chunk size, đồng thời dùng cùng transaction resource nếu muốn assert rollback database như trên.

### Kiểm thử retry

Tạo processor hoặc service stub ném `TransientLookupException` một số lần rồi thành công. Xác nhận:

- Processor được gọi lại theo retry policy.
- Step hoàn tất nếu retry thành công.
- Item chỉ được ghi theo kết quả thành công.
- Không có side effect trùng từ các attempt thất bại.

### Kiểm thử skip

Tạo item gây `InvalidOrderException`, cấu hình `.skip(InvalidOrderException.class)` và `skipLimit`. Xác nhận item lỗi không được ghi, `processSkipCount` tăng và các item hợp lệ vẫn được ghi. Kiểm tra trường hợp skip limit bị vượt để xác nhận step thất bại.

### Kiểm thử restart từ checkpoint

Một test restart có thể:

1. Chạy job với identifying parameters cố định.
2. Cho một số chunk commit rồi làm step thất bại ở chunk tiếp theo.
3. Đọc `StepExecution` và `ExecutionContext` đã lưu bằng `JobExplorer`.
4. Khởi chạy lại cùng job với cùng identifying parameters.
5. Xác nhận reader tiếp tục từ checkpoint đã commit.
6. Đối chiếu business data để bảo đảm chunk đã commit không bị duplicate và chunk chưa commit được xử lý lại.

Không tạo UUID identifying mới giữa lần chạy đầu và restart. Nếu cần cô lập test độc lập, tạo UUID một lần cho test đó rồi tái sử dụng cùng giá trị trong toàn bộ kịch bản restart.

### Kiểm tra metadata bằng JobExplorer

`JobExplorer` cho phép đọc metadata và execution context đã lưu:

```java
JobExecution persisted = jobExplorer.getJobExecution(execution.getId());
assertNotNull(persisted);

StepExecution stepExecution = persisted.getStepExecutions()
        .stream()
        .filter(step -> step.getStepName().equals("importOrdersStep"))
        .findFirst()
        .orElseThrow();

assertEquals(BatchStatus.FAILED, stepExecution.getStatus());
assertTrue(stepExecution.getRollbackCount() > 0);
```

Tên step và giá trị counter phụ thuộc fixture. Không nên chỉ kiểm tra `rollbackCount`; hãy đối chiếu với dữ liệu business thực tế và checkpoint đã lưu. Có thể dùng `JobRepositoryTestUtils` để cleanup metadata test, nhưng phải cleanup business data/file/message riêng và tránh xóa execution của test chạy song song.

## Các lỗi thường gặp

### Nghĩ rollback chunk sẽ đưa mọi thứ về trạng thái ban đầu của job

Rollback chỉ áp dụng transaction hiện tại. Các chunk trước đã commit vẫn tồn tại. Thiết kế restart phải dựa trên checkpoint cuối cùng đã commit.

### Chỉ lưu checkpoint trong field của reader

Field trong memory mất khi JVM dừng. Dùng reader hỗ trợ `ItemStream` hoặc cơ chế lưu state bền vững trong `ExecutionContext`.

### Cập nhật checkpoint độc lập trước business data

Checkpoint có thể tiến lên dù dữ liệu chưa commit, khiến restart bỏ qua item. Cập nhật state tại checkpoint lifecycle và dùng transaction resource phù hợp.

### Giả định mọi reader đều cần buffer giống nhau

Reader từ file/API và transactional queue có semantics khác nhau. Dùng `readerIsTransactionalQueue()` chỉ khi nguồn thực sự transactional.

### Processor có side effect không idempotent

Retry, skip scan hoặc restart có thể gọi processor nhiều lần. Không gửi message hoặc gọi API tạo tác động lặp mà không có idempotency.

### Dùng `saveState(false)` nhưng vẫn mong restart tại vị trí cũ

Tắt lưu state làm reader không ghi checkpoint theo cơ chế tích hợp. Chỉ dùng khi có cơ chế restart khác hoặc nghiệp vụ chấp nhận đọc lại từ đầu.

### Đổi tên reader khi job cũ còn cần restart

Tên component có thể được dùng để tạo key state. Thay đổi tùy tiện có thể khiến reader không tìm thấy checkpoint cũ.

### Cho rằng Job FAILED nghĩa là business data đã rollback hết

Các chunk đã commit vẫn còn. Kiểm tra từng step execution, checkpoint và dữ liệu đích trước khi quyết định restart hoặc chạy lại từ đầu.

### Chỉ test trạng thái job mà không kiểm tra checkpoint

`FAILED` hoặc `COMPLETED` không chứng minh reader khôi phục đúng. Test cần xác nhận state đã lưu và vị trí tiếp tục thực tế.

## Nguyên tắc thiết kế

Khi thiết kế fault-tolerant chunk và checkpoint cho production, hãy xác định:

1. Transaction boundary của chunk và commit interval phù hợp.
2. Exception nào retry, exception nào skip và exception nào làm step thất bại.
3. Reader có buffer item khi rollback hay nguồn đọc có transaction riêng.
4. Reader/writer có triển khai `ItemStream` và lưu state cần thiết không.
5. `ExecutionContext` chứa checkpoint nhỏ, ổn định và serializer-compatible.
6. Tên reader/writer và key context có ổn định qua các lần triển khai không.
7. Checkpoint chỉ tiến cùng phần business data đã commit.
8. Writer và processor có an toàn khi retry/restart không.
9. Side effect ngoài transaction có idempotency, outbox hoặc cơ chế đối soát không.
10. Restart giữ nguyên identifying `JobParameters` và đọc đúng nguồn dữ liệu ban đầu.
11. Integration test bao phủ rollback, retry, skip, checkpoint và restart.

Với reader/writer dựng sẵn, ưu tiên dùng state management tích hợp và cấu hình `saveState` phù hợp. Với reader tự triển khai, thực hiện `ItemStream` đúng lifecycle và chỉ lưu vị trí có thể khôi phục. Giữ processor càng thuần càng tốt, writer idempotent và transaction resource được cấu hình rõ ràng.

## Ghi nhớ

Fault-tolerant chunk xử lý lỗi bằng retry/skip theo policy, còn checkpoint lưu mốc tiến trình đã commit để restart. Trong chunk thành công, Spring Batch ghi output, cập nhật state của `ItemStream`, lưu `ExecutionContext`/metadata rồi commit transaction. Nếu chunk rollback, checkpoint bền vững vẫn ở commit point trước; các chunk đã commit không bị rollback. Reader không transactional thường được framework buffer item để xử lý lại trong các đường rollback; transactional queue có thể dùng `readerIsTransactionalQueue()` để dựa vào rollback của queue. Hãy lưu state nhỏ và ổn định trong `ExecutionContext`, giữ identifying parameters khi restart, tránh side effect không idempotent trong processor và bảo đảm writer có thể xử lý replay. Kiểm thử cả transaction rollback, metadata checkpoint và business data thực tế.
