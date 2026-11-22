# Rollback chunk khi processor ném exception

Trong Spring Batch, chunk-oriented step xử lý dữ liệu theo từng nhóm item. Một chunk thường gồm các thao tác đọc, chuyển đổi và ghi; các thay đổi thuộc transaction của chunk được commit khi chunk hoàn tất. Nếu `ItemProcessor` ném exception trong lúc xử lý một item, exception được truyền ra khỏi pipeline và transaction của chunk hiện tại thường bị rollback.

Rollback bảo vệ tính nhất quán của chunk: các thay đổi database chưa commit trong transaction đó không được giữ lại. Writer thường chưa được gọi cho chunk này vì quá trình xử lý item đã dừng trước giai đoạn ghi. Những chunk trước đó đã commit vẫn tồn tại; transaction của chunk hiện tại không bao trùm toàn bộ job.

Hành vi tiếp theo phụ thuộc vào cấu hình fault tolerance. Nếu exception không được retry hoặc skip, step thất bại. Nếu exception được cấu hình retry, Spring Batch có thể thử lại thao tác xử lý. Nếu exception được phép skip và chưa vượt `skipLimit`, item lỗi có thể bị loại khỏi output để các item hợp lệ tiếp tục được ghi. Dù theo nhánh nào, cần hiểu transaction boundary, side effect của processor và checkpoint của reader để tránh ghi trùng hoặc mất dữ liệu.

## Chunk transaction hoạt động như thế nào?

Với chunk-oriented processing, Spring Batch điều phối `ItemReader`, `ItemProcessor` và `ItemWriter` trong một transaction cho mỗi chunk. Ví dụ `chunk(3, transactionManager)` gom tối đa ba item đầu vào cho một lần xử lý/commit.

```text
Bắt đầu transaction của chunk
             |
             v
       ItemReader.read()
             |
             v
    ItemProcessor.process()
       |       |       |
       v       v       v
      O1      O2      O3
             |
             v
       ItemWriter.write()
             |
             v
    Cập nhật checkpoint/metadata
             |
             v
           COMMIT
```

Trong trường hợp thành công, output được writer ghi và transaction commit. Nếu một thao tác trong chunk ném exception trước commit, transaction được xử lý theo rollback rule của step và transaction manager.

`ItemProcessor<I, O>` xử lý từng item. Processor có thể trả về output, trả `null` để filter item hoặc ném exception nếu không thể xử lý. Trả `null` không phải lỗi và không tự gây rollback; exception mới đi vào đường xử lý lỗi.

## Điều gì xảy ra khi processor ném exception?

Giả sử chunk size là 3 và reader cung cấp ba đơn hàng. Processor xử lý hai item đầu thành công nhưng ném `InvalidOrderException` ở item thứ ba.

```text
Chunk hiện tại: [Order-1, Order-2, Order-3]

Reader       Processor                 Writer
  |              |                       |
  |-- Order-1 -->|-- Order-1'             |
  |-- Order-2 -->|-- Order-2'             |
  |-- Order-3 -->|                        |
  |              |-- throw exception     |
  |              |                       |
  |              X  pipeline dừng        |
                 |
                 v
        Rollback transaction
```

Với cấu hình mặc định không skip/retry exception đó:

1. Processor ném exception khi xử lý item lỗi.
2. Exception thoát khỏi quá trình xử lý chunk.
3. Spring Batch kết thúc lần xử lý chunk theo đường lỗi.
4. Transaction hiện tại rollback theo rollback rule.
5. Writer không nhận các output của chunk này vì giai đoạn xử lý chưa hoàn tất.
6. Step chuyển sang trạng thái thất bại nếu exception không được xử lý bởi fault-tolerance policy.

Các object output đã được tạo trong memory trước khi exception xảy ra không tự được ghi xuống database. Nếu processor đã thực hiện side effect bên ngoài transaction, ví dụ gửi HTTP request hoặc publish message, rollback database không thể tự thu hồi side effect đó.

### Writer có được gọi không?

Trong luồng chunk thông thường, Spring Batch chỉ gọi writer sau khi các item trong chunk đã được đọc và xử lý thành công theo policy. Nếu processor ném exception không được xử lý, pipeline dừng trước writer; chunk hiện tại không được ghi như một chunk hoàn chỉnh.

Với cấu hình fault-tolerant, framework có thể rollback và xử lý lại/scan các item để xác định item gây lỗi, hoặc thực hiện retry theo policy. Trong quá trình đó processor có thể được gọi nhiều lần. Vì vậy, không nên khẳng định writer tuyệt đối không bao giờ được gọi trong mọi tình huống fault-tolerant; điều cần kiểm tra là writer chỉ ghi những output được policy chấp nhận và transaction rollback không để lại dữ liệu dở dang.

## Phạm vi rollback: chunk hiện tại và các chunk trước

Rollback chỉ tác động tới thay đổi chưa commit trong transaction hiện tại. Những chunk đã commit trước đó không bị tự động rollback khi chunk sau thất bại.

Ví dụ step xử lý 7 item với `chunk(3, transactionManager)`:

```text
Chunk 1: Item 1, 2, 3  -> writer thành công -> COMMIT
Chunk 2: Item 4, 5, 6  -> processor lỗi ở Item 6 -> ROLLBACK
Chunk 3: Item 7        -> chưa được xử lý
```

Kết quả thường thấy:

| Phần xử lý | Trạng thái dữ liệu |
| --- | --- |
| Chunk 1 | Dữ liệu đã commit vẫn tồn tại |
| Chunk 2 | Thay đổi tham gia transaction bị rollback |
| Chunk 3 | Chưa được xử lý do step đã thất bại |

Đây là lý do không nên xem toàn bộ job là một transaction duy nhất. Một job dài có thể commit hàng trăm hoặc hàng nghìn chunk. Khi một chunk thất bại, các chunk đã commit trước đó vẫn được giữ lại và restart thường tiếp tục từ checkpoint phù hợp.

Nếu nghiệp vụ yêu cầu toàn bộ job phải nguyên tử, chunk processing mặc định không cung cấp transaction bao trùm mọi chunk. Cần cân nhắc staging/publish, transaction bù trừ hoặc một quy trình nghiệp vụ khác.

## Ví dụ cấu hình step có processor ném exception

Giả sử job nhập đơn hàng. Một đơn hàng có số tiền không hợp lệ sẽ làm processor ném `InvalidOrderException`.

```java
public record OrderInput(String orderId, BigDecimal amount) {
}

public record Order(String orderId, BigDecimal amount) {
}

public class InvalidOrderException extends RuntimeException {
    public InvalidOrderException(String message) {
        super(message);
    }
}
```

Processor kiểm tra và chuyển đổi:

```java
public class OrderProcessor
        implements ItemProcessor<OrderInput, Order> {

    @Override
    public Order process(OrderInput input) {
        if (input.amount() == null || input.amount().signum() <= 0) {
            throw new InvalidOrderException(
                    "Amount must be positive for order " + input.orderId());
        }

        return new Order(input.orderId(), input.amount());
    }
}
```

Khai báo chunk step trong Spring Batch 5:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(3, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
```

Trong cấu hình này không có `.faultTolerant().skip(...)` hoặc `.retry(...)`. Vì vậy, `InvalidOrderException` không được policy xử lý; step thất bại và transaction chunk đang chạy rollback. Nếu writer dùng cùng datasource/transaction manager với step, các thao tác ghi của chunk được bảo vệ bởi transaction đó.

## Transaction manager quyết định dữ liệu nào được rollback

Rollback chỉ áp dụng cho resource thực sự tham gia transaction. Nếu processor gọi service dùng cùng transaction manager và cùng database resource với step, các câu lệnh JDBC/JPA của service thường tham gia transaction chunk.

Ví dụ service:

```java
@Service
public class OrderEnrichmentService {

    private final JdbcTemplate jdbcTemplate;

    public OrderEnrichmentService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public void recordEnrichment(String orderId) {
        jdbcTemplate.update(
                "INSERT INTO order_enrichment(order_id, status) VALUES (?, ?)",
                orderId,
                "CHECKED");
    }
}
```

Nếu service dùng propagation `REQUIRED`, cùng transaction manager và resource, nó tham gia transaction đang hoạt động của chunk. Nếu processor sau đó ném exception, insert trong `recordEnrichment` có thể rollback cùng chunk.

Nếu service dùng `REQUIRES_NEW`, nó mở transaction độc lập. Service có thể commit thành công trước khi processor ném exception; transaction chunk rollback không thể hoàn tác transaction đã commit đó. Cần cân nhắc kỹ propagation khi gọi service từ processor.

| Loại thao tác trong processor | Có rollback cùng chunk không? |
| --- | --- |
| JDBC/JPA dùng cùng transaction resource và manager | Thông thường có |
| Service `@Transactional(REQUIRED)` dùng đúng manager | Tham gia transaction hiện tại; thường có |
| Service `@Transactional(REQUIRES_NEW)` | Transaction độc lập có thể đã commit; không rollback cùng chunk |
| Ghi file trực tiếp | Không tự rollback cùng JDBC transaction |
| Gửi HTTP request | Không tự rollback |
| Publish message tới broker không tham gia transaction chung | Không tự rollback |
| Ghi vào datasource khác với local transaction manager khác | Không có atomic rollback mặc định |

Không nên kết luận mọi thao tác được gọi từ processor đều rollback chỉ vì processor nằm trong chunk transaction. Hãy kiểm tra transaction manager, datasource, propagation và giao thức của hệ thống ngoài.

## Exception type và rollback rule

`ItemProcessor.process` khai báo `throws Exception`, nên processor có thể ném checked exception hoặc unchecked exception. Spring Batch cấu hình transaction của step để xử lý exception theo rollback rule của step; mặc định chunk transaction được rollback khi quá trình xử lý chunk thất bại. Nếu ứng dụng tùy chỉnh transaction attributes hoặc cấu hình ngoại lệ không rollback, cần kiểm tra lại hành vi thực tế.

Trong fault-tolerant step, các cấu hình như `skip`, `retry` và `noRollback` ảnh hưởng cách framework xử lý exception. Không nên suy luận chỉ từ việc exception là checked hay runtime mà bỏ qua cấu hình của step.

Ví dụ cấu hình không rollback cho một exception được chọn:

```java
.faultTolerant()
.skip(AlreadyProcessedException.class)
.noRollback(AlreadyProcessedException.class)
.skipLimit(20)
```

`noRollback` là cấu hình chuyên biệt, chỉ nên dùng khi semantics của exception và trạng thái xử lý cho phép tiếp tục mà không rollback chunk. Nó không có nghĩa mọi exception processor đều có thể bỏ qua rollback. Hãy kiểm thử transaction và output thực tế trước khi dùng, đặc biệt khi writer hoặc processor có side effect.

## Rollback khi không cấu hình skip hoặc retry

Đây là trường hợp cơ bản nhất. Nếu processor ném exception không được policy xử lý:

- Chunk hiện tại không được commit.
- Các thao tác database tham gia transaction chunk rollback.
- Step thường kết thúc `FAILED`.
- Job thường kết thúc `FAILED` nếu flow không có nhánh xử lý lỗi riêng.
- Các chunk trước đã commit vẫn tồn tại.
- Có thể restart cùng `JobInstance` nếu job và step cho phép restart.

Ví dụ test có thể xác nhận step thất bại và dữ liệu của chunk chưa commit không xuất hiện trong bảng đích. Nếu test dùng chunk size lớn hơn toàn bộ input, có thể không có business row nào được ghi. Nếu test có nhiều chunk, các row từ chunk trước vẫn tồn tại.

## Rollback khi processor exception được retry

Retry phù hợp với lỗi tạm thời có khả năng tự hết, chẳng hạn deadlock hoặc timeout của một dịch vụ. Khi processor ném exception thuộc retry policy, Spring Batch có thể thử lại thao tác theo cấu hình.

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

Với cấu hình này, `TransientLookupException` được thử lại theo retry policy. Số lần thử và cách diễn giải `retryLimit` cần được xác nhận theo API/version của dự án; trong cấu hình Spring Batch thông dụng, giới hạn retry chỉ định số lần retry tối đa sau lần thử ban đầu.

Khi retry xảy ra, processor có thể được gọi lại cho cùng item. Một chunk có thể bị rollback trước khi framework thực hiện lần thử tiếp theo tùy loại retry và transaction boundary. Vì vậy:

- Processor nên có tính xác định với cùng input và cùng dữ liệu tham chiếu.
- Tránh ghi file, gửi message hoặc gọi API có side effect không idempotent trong processor.
- Nếu phải gọi dịch vụ ngoài, dùng idempotency key hoặc API có khả năng truy vấn trạng thái.
- Chỉ retry lỗi có khả năng phục hồi; lỗi dữ liệu cố định thường không nên retry.

Nếu lần retry thành công, item được xử lý và chunk có thể tiếp tục tới writer/commit. Nếu retry hết giới hạn, exception tiếp tục đi theo chính sách còn lại: có thể được skip nếu được cấu hình và phân loại phù hợp, hoặc làm step thất bại.

## Rollback khi processor exception được skip

Skip phù hợp với lỗi dữ liệu mà nghiệp vụ cho phép bỏ qua. Nếu exception của processor được khai báo trong skip policy và tổng skip chưa vượt giới hạn, item lỗi có thể bị loại khỏi output để các item còn lại được ghi.

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

Với fault-tolerant processing, Spring Batch có thể rollback chunk rồi xử lý lại/scan các item để xác định item gây lỗi. Khi item lỗi được skip, các item hợp lệ có thể được ghi trong transaction thích hợp. Do đó, kết quả cuối cùng không giống trường hợp không có skip policy: chunk không nhất thiết bị bỏ toàn bộ chỉ vì một item lỗi.

Nếu số skip vượt `skipLimit`, step thất bại. Chunk hiện tại có thể rollback, trong khi các chunk trước đã commit vẫn được giữ. Hãy kiểm tra `readSkipCount`, `processSkipCount`, `writeSkipCount` và `skipCount` để biết lỗi phát sinh ở đâu.

### Filtering khác với skip

Processor trả `null` để filter một item hợp lệ nhưng không cần output. Đây không phải exception và không kích hoạt rollback chỉ vì kết quả `null`.

| Kết quả processor | Ý nghĩa | Tác động |
| --- | --- | --- |
| Trả về object | Xử lý thành công | Output được đưa vào chunk |
| Trả về `null` | Filter item có chủ đích | Item không tới writer; tăng `filterCount` |
| Ném exception được retry | Lỗi có thể phục hồi | Framework thử lại theo retry policy |
| Ném exception được skip | Lỗi được phép bỏ qua | Item được skip nếu chưa vượt limit |
| Ném exception không được xử lý | Lỗi không thể tiếp tục | Chunk rollback và step thất bại |

Không dùng `null` để che lỗi dữ liệu. Nếu item sai và cần ghi nhận reject, hãy ném exception phù hợp và dùng skip policy/`SkipListener`.

## Reader state sau rollback

Reader thường có state như vị trí file, offset hoặc page. Các reader tích hợp với `ItemStream` có thể lưu state vào step `ExecutionContext` tại checkpoint. Khi chunk rollback, checkpoint đã commit trước đó vẫn là mốc an toàn để restart.

Không nên tự giả định mọi reader đều tua ngược con trỏ trong memory ngay khi transaction rollback. Cách xử lý item đã đọc phụ thuộc reader và nguồn dữ liệu:

- Với reader không transactional, framework thường buffer item đã đọc để có thể xử lý lại mà không gọi nguồn đọc lần nữa trong một số đường rollback/fault-tolerant.
- Với nguồn transactional như message queue, rollback có thể trả message về nguồn theo semantics của resource.
- Với file/database reader có state, checkpoint được lưu tại commit point; restart sử dụng state đã lưu.
- Với reader tự triển khai, cần tuân theo `ItemStream` và thiết kế state để khôi phục đúng sau rollback/restart.

Nếu reader tự cập nhật một biến field khi đọc item, biến đó có thể đã tiến lên dù chunk chưa commit. Cần bảo đảm framework/reader có cách khôi phục hoặc đọc lại item chưa commit. Không tự ghi checkpoint vào một transaction độc lập trước khi dữ liệu tương ứng được commit.

## ExecutionContext và restart sau processor failure

`ExecutionContext` lưu checkpoint của step. Khi chunk commit thành công, reader/writer có thể cập nhật state và Spring Batch lưu context cùng metadata theo transaction/lifecycle đã cấu hình.

Ví dụ reader lưu khóa cuối đã xử lý:

```java
public class OrderReader implements ItemStreamReader<OrderInput> {

    private long lastProcessedId;

    @Override
    public void open(ExecutionContext context) {
        lastProcessedId = context.getLong("lastProcessedId", 0L);
    }

    @Override
    public OrderInput read() {
        return readNextAfter(lastProcessedId);
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong("lastProcessedId", lastProcessedId);
    }

    @Override
    public void close() {
    }
}
```

`readNextAfter(...)` là phần truy vấn do ứng dụng triển khai. Ví dụ chỉ minh họa state nhỏ cần lưu. Reader thực tế phải cập nhật `lastProcessedId` theo quy tắc phù hợp với item đã được xử lý/commit, không đơn thuần theo item vừa được đọc nếu rollback có thể xảy ra.

Khi processor ném exception và chunk rollback:

1. Dữ liệu trong chunk chưa commit được rollback nếu cùng transaction resource.
2. Checkpoint đã commit trước đó vẫn còn.
3. Step thất bại nếu exception không được retry/skip.
4. Khi restart cùng identifying parameters, reader khôi phục checkpoint hợp lệ.
5. Item thuộc chunk chưa commit có thể được đọc/xử lý lại theo semantics của reader.

Giữ nguyên identifying parameters khi restart cùng `JobInstance`. Thêm timestamp identifying mới sẽ tạo instance khác và có thể khiến job chạy lại từ đầu.

## Side effect trong processor không tự rollback

`ItemProcessor` nên tập trung vào kiểm tra và chuyển đổi dữ liệu. Nếu processor thực hiện side effect trước khi ném exception, side effect đó có thể tồn tại sau khi chunk rollback.

Ví dụ rủi ro:

```java
public Order process(OrderInput input) {
    notificationClient.send("Processing " + input.orderId());

    if (input.amount().signum() <= 0) {
        throw new InvalidOrderException("Invalid amount");
    }

    return map(input);
}
```

Nếu notification đã được gửi rồi processor ném exception, rollback database không thu hồi thông báo. Khi retry hoặc restart, thông báo có thể được gửi lần nữa.

Các lựa chọn an toàn hơn:

- Giữ processor thuần, chỉ tạo output hoặc ném exception.
- Đưa side effect vào writer để nó nằm trong transaction phù hợp nếu đích hỗ trợ.
- Ghi event vào transactional outbox cùng business data rồi publisher riêng gửi message.
- Dùng idempotency key cho API hoặc message để xử lý gửi lặp.
- Lưu kết quả tra cứu có thể tái sử dụng nếu cần tránh gọi dịch vụ ngoài nhiều lần.

Không dựa vào rollback chunk để hoàn tác file, HTTP request, email hoặc message đã được hệ thống ngoài tiếp nhận.

## Kiểm thử rollback khi processor ném exception

Kiểm thử cần chứng minh ba điều:

1. Exception của processor làm chunk hiện tại rollback khi không có policy xử lý.
2. Dữ liệu từ chunk trước đã commit vẫn còn.
3. Dữ liệu chưa commit của chunk lỗi không xuất hiện ở đích nếu writer cùng transaction resource.

Nên dùng integration test với `JobRepository`, transaction manager và database test thực sự. Unit test processor chỉ chứng minh processor ném exception; nó không chứng minh transaction của Spring Batch rollback đúng.

### Ví dụ fixture

```java
public record OrderInput(String orderId, boolean invalid) {
}

public record Order(String orderId) {
}

public class FailingOrderProcessor
        implements ItemProcessor<OrderInput, Order> {

    @Override
    public Order process(OrderInput input) {
        if (input.invalid()) {
            throw new InvalidOrderException(input.orderId());
        }
        return new Order(input.orderId());
    }
}
```

Với chunk size 2, cung cấp bốn item: hai item hợp lệ đầu tiên và item thứ ba gây lỗi. Writer ghi vào bảng `processed_order` bằng JDBC và dùng cùng transaction manager với step.

```text
Input: [O-1 valid, O-2 valid] [O-3 invalid, O-4 valid]
Chunk 1: ghi O-1, O-2 -> COMMIT
Chunk 2: processor lỗi ở O-3 -> ROLLBACK
Expected rows: O-1, O-2
```

Test có thể dùng `JobLauncherTestUtils` để chạy job và `JdbcTemplate` để kiểm tra bảng đích:

```java
@SpringBootTest
@SpringBatchTest
class ProcessorRollbackIntegrationTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    @Qualifier("processorRollbackJob")
    private Job processorRollbackJob;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @BeforeEach
    void configureJob() {
        jobLauncherTestUtils.setJob(processorRollbackJob);
        jdbcTemplate.update("DELETE FROM processed_order");
    }

    @Test
    void rollsBackChunkWhereProcessorThrows() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("testRunId", UUID.randomUUID().toString(), true)
                .toJobParameters();

        JobExecution execution =
                jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.FAILED, execution.getStatus());

        List<String> orderIds = jdbcTemplate.queryForList(
                "SELECT order_id FROM processed_order ORDER BY order_id",
                String.class);

        assertEquals(List.of("O-1", "O-2"), orderIds);
    }
}
```

Test minh họa giả định job fixture có reader trả đúng bốn item, chunk size bằng 2, writer insert vào `processed_order`, và tất cả dùng cùng datasource/transaction manager. Nếu chunk size hoặc thứ tự input khác, kết quả mong đợi cần thay đổi theo transaction boundary thực tế.

### Xác nhận failure exception

Ngoài `BatchStatus.FAILED`, có thể kiểm tra `StepExecution.getFailureExceptions()` để xác nhận nguyên nhân là `InvalidOrderException` hoặc exception được bọc có cause tương ứng. Tránh chỉ so sánh thông điệp lỗi vì thông điệp có thể thay đổi hoặc được framework bổ sung.

```java
StepExecution stepExecution = execution.getStepExecutions()
        .stream()
        .filter(step -> step.getStepName().equals("importOrdersStep"))
        .findFirst()
        .orElseThrow();

assertEquals(BatchStatus.FAILED, stepExecution.getStatus());
assertFalse(stepExecution.getFailureExceptions().isEmpty());
```

Nếu cần tìm exception gốc trong cause chain, viết helper duyệt `Throwable.getCause()` và kiểm tra loại exception thay vì phụ thuộc vào vị trí cố định trong danh sách.

## Kiểm thử rollback và skip/retry

Nên có các test riêng để xác nhận cấu hình thay đổi hành vi như thế nào.

| Cấu hình | Processor exception | Kết quả cần kiểm tra |
| --- | --- | --- |
| Không skip/retry | Exception không được xử lý | Chunk rollback, step `FAILED` |
| Retry | Exception tạm thời rồi thành công | Retry theo policy; chunk có thể hoàn tất và commit |
| Skip | Exception được phép bỏ qua, chưa vượt limit | Item lỗi bị skip; output hợp lệ được ghi theo policy |
| Skip limit exceeded | Tổng skip vượt giới hạn | Step `FAILED`; chunk hiện tại rollback theo fault-tolerance semantics |
| `noRollback` được cấu hình | Exception thuộc loại không rollback | Hành vi theo cấu hình; cần kiểm tra dữ liệu và counters cụ thể |

Không dùng một test duy nhất để chứng minh mọi nhánh. Mỗi policy có semantics khác nhau và cần fixture riêng, nhất là khi processor có side effect hoặc writer ghi vào nhiều resource.

## Kiểm thử processor được gọi lại

Với retry hoặc skip scan, processor có thể được gọi nhiều lần cho cùng item. Test nên đếm số lần gọi hoặc dùng mock để xác nhận hành vi khi cấu hình yêu cầu retry.

Ví dụ processor thất bại tạm thời một lần rồi thành công:

```java
public class RetryOnceProcessor
        implements ItemProcessor<OrderInput, Order> {

    private final AtomicInteger attempts = new AtomicInteger();

    @Override
    public Order process(OrderInput input) {
        if (attempts.getAndIncrement() == 0) {
            throw new TransientLookupException("Temporary lookup failure");
        }
        return new Order(input.orderId());
    }
}
```

Test integration với `.retry(TransientLookupException.class).retryLimit(1)` có thể xác nhận processor được gọi lại và step hoàn tất nếu lần sau thành công. Trong ứng dụng production, không nên dùng field counter như cơ chế retry; ví dụ chỉ tạo lỗi có kiểm soát cho test. Processor thực tế nên stateless và không phụ thuộc số lần được gọi.

Nếu processor phụ thuộc vào một service ngoài, dùng mock hoặc stub có hành vi xác định. Đừng dùng `Thread.sleep` để giả lập lỗi; hãy trả exception có kiểm soát để test ổn định.

## Kiểm tra dữ liệu khi rollback một phần

Rollback chunk không đồng nghĩa mọi dữ liệu của step đều biến mất. Với nhiều chunk, test cần kiểm tra:

- Các row từ chunk đã commit trước lỗi vẫn còn.
- Các row thuộc chunk rollback không còn nếu writer dùng cùng transaction.
- Các row chưa tới chunk không xuất hiện.
- Metadata phản ánh step thất bại và checkpoint cuối cùng đã commit.
- Các side effect ngoài transaction được kiểm tra riêng.

Nếu writer ghi file hoặc message, hãy kiểm thử riêng vì transaction JDBC không thể chứng minh các resource đó đã rollback. Với file, có thể dùng output tạm và xác nhận quy trình cleanup/rename. Với message, dùng event ID và xác nhận consumer xử lý duplicate an toàn.

## Lỗi thường gặp

### Nghĩ processor exception chỉ làm hỏng một item

Nếu không cấu hình skip/retry, exception có thể làm rollback cả chunk hiện tại và làm step thất bại. Muốn bỏ riêng item lỗi, cần skip policy rõ ràng.

### Nghĩ toàn bộ job bị rollback

Các chunk đã commit trước đó vẫn tồn tại. Transaction boundary là mỗi chunk, không phải toàn bộ job.

### Giả định writer đã ghi một phần chunk

Trong pipeline thông thường, processor exception xảy ra trước khi writer được gọi cho chunk đó. Nếu writer hoặc listener có side effect khác, phải phân tích theo callback và transaction riêng.

### Gọi API hoặc ghi file trong processor

Side effect bên ngoài database không tự rollback. Retry có thể lặp side effect. Giữ processor thuần hoặc dùng idempotency/outbox.

### Dùng REQUIRES_NEW không chủ ý

Service có thể commit độc lập rồi processor ném exception. Chunk rollback không xóa dữ liệu service đã commit. Kiểm tra transaction propagation.

### Không lưu checkpoint đúng cách

Reader có thể đã đọc item nhưng chunk chưa commit. Dùng reader hỗ trợ `ItemStream` hoặc cơ chế buffer/restart phù hợp; không tự lưu checkpoint độc lập trước dữ liệu.

### Catch exception rồi trả output bình thường

Nếu processor nuốt lỗi và trả object giả hoặc `null`, framework có thể không biết chunk đã gặp lỗi. Chỉ chuyển lỗi thành filter/default khi đó là quyết định nghiệp vụ rõ ràng; nếu không thể xử lý, hãy ném exception.

### Test chỉ kiểm tra trạng thái FAILED

`FAILED` không chứng minh business data rollback đúng. Kiểm tra bảng đích, chunk đã commit, checkpoint và exception gốc.

## Nguyên tắc thiết kế processor để rollback an toàn

Khi viết processor cho job production, hãy cân nhắc:

1. Giữ processor tập trung vào validation, transformation và enrichment có thể lặp an toàn.
2. Ném exception có loại rõ ràng để skip/retry policy phân loại đúng.
3. Không dùng `null` để che lỗi; chỉ trả `null` khi muốn filter item hợp lệ.
4. Tránh side effect không idempotent trong processor.
5. Nếu gọi service transactional, xác nhận propagation và transaction manager.
6. Đảm bảo database write cần rollback dùng cùng transaction resource với step.
7. Thiết kế reader state và `ExecutionContext` để restart từ checkpoint đã commit.
8. Xác định rõ exception nào retry, exception nào skip và exception nào làm step thất bại.
9. Kiểm tra chunk trước đã commit vẫn được giữ khi chunk sau lỗi.
10. Kiểm thử cả rollback database lẫn side effect ở hệ thống ngoài.

## Ghi nhớ

Khi `ItemProcessor` ném exception không được xử lý, quá trình chunk hiện tại dừng và transaction của chunk thường rollback; writer không ghi output của chunk chưa hoàn tất. Các chunk đã commit trước đó vẫn tồn tại. Nếu exception được cấu hình retry, processor có thể được gọi lại; nếu được skip và chưa vượt `skipLimit`, item lỗi có thể bị loại để các output hợp lệ tiếp tục được ghi. Rollback chỉ bao phủ resource tham gia cùng transaction manager: JDBC/JPA cùng resource có thể rollback, còn file, HTTP request, message hoặc transaction `REQUIRES_NEW` không tự được hoàn tác. Hãy giữ processor an toàn khi gọi lại, lưu checkpoint đúng trong `ExecutionContext` và kiểm thử cả trạng thái step lẫn dữ liệu thực tế sau rollback/restart.
