# Retry trong read, process và write

Trong Spring Batch, retry cho phép một chunk Step thử lại thao tác khi reader, processor hoặc writer gặp lỗi có khả năng phục hồi. Ví dụ, một truy vấn database tạm thời bị deadlock, một dịch vụ tham chiếu bị timeout trong lúc xử lý item, hoặc writer gặp lỗi kết nối ngắn hạn. Nếu lỗi được phân loại là retryable, framework có thể thực hiện lại thao tác theo giới hạn và chính sách backoff đã cấu hình.

Retry đặc biệt hữu ích với lỗi tạm thời. Nó không sửa được dữ liệu đầu vào sai cố định, lỗi lập trình hoặc cấu hình sai. Những lỗi đó cần được skip theo quy tắc nghiệp vụ hoặc làm Step thất bại. Để dùng retry an toàn, phải hiểu thành phần nào được gọi lại, transaction nào rollback và tác dụng phụ nào có thể bị lặp.

## 1. Retry nằm ở đâu trong chunk processing?

Một chunk Step thực hiện chu trình đọc, xử lý và ghi nhiều item. Exception có thể xảy ra ở từng giai đoạn:

```text
ItemReader
    |
    +-- Lỗi tạm thời --> Retry read
    |
    v
ItemProcessor
    |
    +-- Lỗi tạm thời --> Retry process
    |
    v
ItemWriter
    |
    +-- Lỗi tạm thời --> Retry write
    |
    v
Commit chunk
```

Retry là cơ chế fault tolerance ở cấp thao tác/item trong chunk Step. Nó không có nghĩa Spring Batch khởi chạy lại toàn bộ Job. Nếu retry thành công, Step tiếp tục xử lý chunk theo luồng bình thường. Nếu retry hết giới hạn, exception có thể được chuyển sang skip policy nếu được phép skip; nếu không, Step có thể thất bại.

| Giai đoạn | Ví dụ lỗi tạm thời | Thao tác có thể được thử lại |
|---|---|---|
| Read | Timeout khi lấy dữ liệu từ database hoặc API | `ItemReader.read()` |
| Process | Timeout khi gọi dịch vụ tra cứu dữ liệu tham chiếu | `ItemProcessor.process(item)` |
| Write | Deadlock hoặc lỗi kết nối database khi ghi | `ItemWriter.write(chunk)` hoặc phần ghi được framework xử lý lại |

Mỗi giai đoạn có đặc điểm khác nhau. Read retry cần reader có thể tiếp tục an toàn; process retry có thể gọi lại processor với cùng item; write retry có thể gọi lại writer với chunk hoặc nhóm item liên quan. Vì vậy, không nên giả định một lần retry luôn tương ứng với một item giống nhau ở cả ba giai đoạn.

## 2. Cấu hình retry cơ bản cho Step

Với Spring Batch 5, retry được cấu hình trên fault-tolerant chunk Step bằng `.retry(...)` và `.retryLimit(...)`:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(200, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .faultTolerant()
            .retry(TransientDataAccessException.class)
            .retryLimit(3)
            .build();
}
```

Trong ví dụ, `TransientDataAccessException` là nhóm lỗi được phép retry. `retryLimit` giới hạn số lần retry theo chính sách của builder. Khi chọn giá trị, hãy xác nhận semantics của phiên bản Spring Batch/Spring Retry đang dùng và tính cả thời gian backoff vào SLA của Job.

Không phải mọi exception đều được retry. Những exception không thuộc cấu hình retry sẽ đi theo chính sách lỗi tương ứng, thường làm Step thất bại nếu không được skip hoặc xử lý theo một policy khác.

### Loại trừ exception khỏi retry

Có thể cấu hình exception không được retry bằng `.noRetry(...)`:

```java
.faultTolerant()
.retry(TransientDataAccessException.class)
.retryLimit(3)
.noRetry(InvalidOrderException.class)
```

Trong ví dụ, lỗi truy cập dữ liệu tạm thời có thể được retry, còn lỗi dữ liệu đơn hàng không được thử lại. Nếu item thiếu mã đơn hàng, chờ thêm không làm dữ liệu tự hợp lệ; lỗi đó cần được skip hoặc làm Step thất bại theo quy tắc nghiệp vụ.

### Dùng RetryPolicy tùy chỉnh

Khi các loại exception có giới hạn retry khác nhau, có thể cung cấp `RetryPolicy` tùy chỉnh thay vì chỉ dùng một `.retryLimit(...)` chung. Spring Retry có các policy như `SimpleRetryPolicy`, `NeverRetryPolicy`, `TimeoutRetryPolicy` và `ExceptionClassifierRetryPolicy`.

Policy tùy chỉnh cần có default an toàn: exception chưa biết không tự động được retry. Nếu dùng `.retryPolicy(...)`, hãy để policy đó là nơi quyết định hành vi retry và tránh kết hợp nhiều rule `.retry(...)`/`.retryLimit(...)` mà không hiểu cách builder áp dụng cấu hình.

## 3. Retry trong ItemReader

`ItemReader.read()` lấy item tiếp theo từ nguồn dữ liệu. Read retry phù hợp khi thao tác đọc thất bại do lỗi tạm thời, ví dụ timeout kết nối hoặc deadlock trong truy vấn.

Ví dụ một reader truy vấn dịch vụ dữ liệu:

```java
public class RemoteOrderReader implements ItemReader<OrderInput> {

    private final OrderSourceClient client;
    private Iterator<OrderInput> currentPage;

    public RemoteOrderReader(OrderSourceClient client) {
        this.client = client;
    }

    @Override
    public OrderInput read() {
        if (currentPage == null || !currentPage.hasNext()) {
            List<OrderInput> nextPage = client.fetchNextPage();
            if (nextPage.isEmpty()) {
                return null;
            }
            currentPage = nextPage.iterator();
        }

        return currentPage.next();
    }
}
```

Nếu `fetchNextPage()` ném một exception timeout được cấu hình retry, Spring Batch có thể gọi lại thao tác đọc. Reader cần bảo đảm một lần gọi thất bại không làm mất vị trí hoặc bỏ qua trang dữ liệu.

### Các điểm cần chú ý khi retry read

- Nếu request đọc đã được server xử lý nhưng response bị timeout, lần gọi lại có thể lấy trang khác nếu API dùng cursor không ổn định.
- Nếu reader tăng offset hoặc cursor trước khi xác nhận dữ liệu nhận được, exception có thể làm reader bỏ qua dữ liệu.
- Reader có thể giữ state trong bộ nhớ; cần xác định state có được cập nhật trước hay sau khi đọc thành công.
- Với nguồn không transactional, rollback database không tự đưa nguồn đọc trở lại vị trí trước đó.
- Với reader hỗ trợ `ItemStream`, checkpoint cần được lưu qua `ExecutionContext` để restart từ vị trí đã commit.

### Read retry và buffering

Trong chunk processing, Spring Batch thường buffer item đã đọc để hỗ trợ rollback và xử lý lại chunk. Điều này giúp framework không nhất thiết phải đọc lại toàn bộ nguồn mỗi khi transaction writer rollback. Tuy nhiên, lỗi xảy ra ngay trong `read()` trước khi item được tạo có đặc điểm khác: reader phải có khả năng gọi lại thao tác đọc mà không làm mất dữ liệu.

Với nguồn transactional queue, có thể cấu hình `readerIsTransactionalQueue()` khi reader dùng queue mà việc rollback transaction có thể trả message về nguồn. Chỉ bật khi nguồn và reader thực sự có semantics transactional queue; không dùng tùy chọn này cho file hoặc API thông thường.

## 4. Retry trong ItemProcessor

`ItemProcessor.process(item)` nhận một item đã đọc và trả về item đầu ra. Process retry phù hợp khi processor phụ thuộc vào một dịch vụ hoặc tài nguyên có thể tạm thời không sẵn sàng.

Ví dụ, processor cần tra cứu thông tin thuế từ dịch vụ ngoài:

```java
public class TaxProcessor implements ItemProcessor<OrderInput, Order> {

    private final TaxRateClient taxRateClient;

    public TaxProcessor(TaxRateClient taxRateClient) {
        this.taxRateClient = taxRateClient;
    }

    @Override
    public Order process(OrderInput input) {
        BigDecimal rate = taxRateClient.getRate(input.region());
        BigDecimal tax = input.amount().multiply(rate);

        return new Order(
                input.orderId(),
                input.amount(),
                tax);
    }
}
```

Nếu `getRate()` ném exception timeout tạm thời và exception đó được cấu hình retry, processor có thể được gọi lại với item đang xử lý. Khi dịch vụ hoạt động trở lại, processor có thể trả kết quả và item tiếp tục đến writer.

### Process retry và tính lặp an toàn

Processor có thể được gọi nhiều lần cho cùng một item khi retry hoặc rollback. Vì vậy, nên giữ processor càng ít tác dụng phụ càng tốt:

- Tránh gửi email trong `process`.
- Tránh ghi trực tiếp dữ liệu nghiệp vụ vào một hệ thống khác transaction của Step.
- Tránh tăng counter nghiệp vụ bên ngoài theo mỗi lần gọi processor.
- Không tạo ID nghiệp vụ mới ngẫu nhiên ở mỗi lần retry nếu ID cần ổn định.
- Nếu gọi API có tác dụng phụ, dùng idempotency key hoặc chuyển tác vụ sang outbox/Step riêng.

Nếu processor chỉ kiểm tra, tính toán và tạo object đầu ra, việc gọi lại thường an toàn hơn. Nếu processor có side effect, cần định nghĩa rõ cách phát hiện request đã được thực hiện trước đó.

### Phân biệt lỗi dữ liệu với lỗi tạm thời

Một item có số tiền âm là lỗi dữ liệu cố định; retry không làm số tiền trở thành hợp lệ. Ngược lại, một request tra cứu tỷ giá bị timeout có thể thành công ở lần sau. Hãy dùng exception type riêng để phân biệt hai trường hợp:

```java
if (input.amount().signum() <= 0) {
    throw new InvalidOrderException("Amount must be positive");
}

BigDecimal rate = taxRateClient.getRate(input.region());
```

`InvalidOrderException` có thể được cấu hình skip hoặc fail; exception timeout từ client có thể được retry.

## 5. Retry trong ItemWriter

`ItemWriter` nhận các item đầu ra của chunk và ghi chúng đến hệ thống đích. Write retry phù hợp khi lỗi ghi có thể phục hồi, ví dụ deadlock, lock timeout hoặc lỗi kết nối database tạm thời.

Ví dụ writer ghi theo batch:

```java
@Bean
JdbcBatchItemWriter<Order> orderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("""
                    INSERT INTO orders (order_id, amount, tax)
                    VALUES (:orderId, :amount, :tax)
                    """)
            .beanMapped()
            .build();
}
```

Nếu database gặp deadlock trong lúc ghi và exception được cấu hình retry, Spring Batch có thể rollback transaction chunk và thử lại thao tác ghi theo cơ chế fault tolerance.

### Writer nhận một chunk, không phải một item đơn lẻ

Trong Spring Batch 5, `ItemWriter` nhận `Chunk` các item đầu ra. Vì vậy, một lần ghi lỗi có thể liên quan đến bất kỳ item nào trong chunk hoặc đến chính tài nguyên đích.

```java
public class AuditWriter implements ItemWriter<Order> {

    @Override
    public void write(Chunk<? extends Order> chunk) {
        for (Order order : chunk) {
            // Ghi các đơn hàng trong chunk.
        }
    }
}
```

Khi write retry hoặc write skip, framework có thể rollback và gọi lại writer. Với một số tình huống write skip, Spring Batch có thể phân tích chunk bằng cách thử ghi các nhóm nhỏ hơn hoặc từng item để tìm item gây lỗi. Do đó, không nên giả định writer chỉ được gọi một lần cho mỗi chunk.

### Write retry và transaction

Nếu writer ghi qua cùng datasource và transaction manager của Step, các thay đổi chưa commit có thể được rollback khi writer ném exception. Khi retry, writer có thể thực hiện lại thao tác trong transaction mới hoặc trong đường xử lý retry do framework điều phối.

Điều này không tự bảo đảm cho tài nguyên ngoài transaction:

- Gửi HTTP request có thể đã được server xử lý dù client timeout.
- Email đã gửi không thể được thu hồi bằng rollback database.
- File đã ghi hoặc đổi tên không tự quay lại trạng thái cũ.
- Message đã publish có thể vẫn tồn tại sau rollback JDBC.

Nếu writer thực hiện tác dụng phụ ngoài transaction, cần idempotency key, outbox/inbox hoặc quy trình đối soát để tránh lặp tác dụng phụ.

## 6. Cấu hình retry với backoff

Nếu retry ngay lập tức, ứng dụng có thể gửi nhiều request liên tiếp đến hệ thống đang quá tải. Backoff tạo khoảng chờ giữa các lần thử để tài nguyên có thời gian phục hồi.

Ví dụ dùng exponential backoff:

```java
@Bean
BackOffPolicy retryBackOffPolicy() {
    ExponentialBackOffPolicy policy = new ExponentialBackOffPolicy();
    policy.setInitialInterval(500L);
    policy.setMultiplier(2.0);
    policy.setMaxInterval(5_000L);
    return policy;
}

@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        ItemWriter<Order> orderWriter,
        BackOffPolicy retryBackOffPolicy) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(200, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .faultTolerant()
            .retry(TransientDataAccessException.class)
            .retryLimit(4)
            .backOffPolicy(retryBackOffPolicy)
            .build();
}
```

Trong ví dụ, khoảng chờ bắt đầu ở 500 ms, tăng theo hệ số 2 và bị giới hạn ở 5 giây. Các giá trị cần được chọn theo timeout của dịch vụ, SLA của Job và mức độ quá tải có thể xảy ra.

Backoff không thay thế timeout. Nếu một request bị treo 10 phút, backoff chỉ bắt đầu sau khi request kết thúc bằng lỗi. Hãy cấu hình connect/read/query timeout ở HTTP client, JDBC driver hoặc dịch vụ tương ứng.

## 7. RetryLimit và số lần thực thi

`retryLimit` giới hạn retry cho exception được cấu hình. Khi chọn giới hạn, cần phân biệt:

- Lần gọi ban đầu.
- Các lần thử lại sau khi lần gọi trước thất bại.
- Tổng thời gian chờ backoff.
- Thời gian bản thân reader/processor/writer thực hiện mỗi lần.

Semantics chính xác của giới hạn cần được hiểu theo API Spring Batch/Spring Retry đang dùng. Một số policy biểu diễn `maxAttempts` bao gồm lần gọi đầu tiên, trong khi builder Spring Batch có thể mô tả retry limit theo số lần retry. Không nên tự tính tổng thời gian hoặc số request chỉ từ một con số nếu chưa xác nhận cách builder tạo policy.

Ví dụ, nếu một thao tác mất 2 giây mỗi lần và có nhiều lần backoff, thời gian tổng có thể vượt xa 2 giây. Hãy tính thời gian tối đa cho một item/chunk và bảo đảm Job timeout/SLA cho phép.

## 8. Kết hợp retry và skip

Retry và skip có thể được cấu hình cùng nhau:

- Retry lỗi có khả năng tự phục hồi.
- Nếu retry không thành công, skip item nếu exception đó cũng được phép skip và skip limit chưa bị vượt.
- Nếu exception không được skip hoặc vượt skip limit, Step thất bại.

Ví dụ:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(200, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .skip(InvalidOrderException.class)
        .skip(FlatFileParseException.class)
        .skipLimit(50)
        .build();
```

Trong ví dụ, lỗi truy cập dữ liệu tạm thời được retry. Lỗi dữ liệu đơn hàng và lỗi parse dòng CSV được skip theo giới hạn. Nếu lỗi database không thuộc skip policy, retry exhaustion làm Step thất bại.

Không nên cấu hình cùng một exception vừa retry vừa skip nếu chưa xác định rõ ý nghĩa cuối cùng. Trong một số trường hợp, muốn thử lại lỗi transient trước rồi mới skip khi hết retry; trong trường hợp khác, lỗi đó phải làm Step thất bại. Hãy kiểm thử với exception thực tế và policy của phiên bản đang dùng.

## 9. Retry và skip không giống filter

Filter là quyết định nghiệp vụ của processor: trả về `null` để loại item hợp lệ khỏi writer. Retry là thử lại thao tác bị exception. Skip là bỏ qua item do exception được phép bỏ qua.

| Cơ chế | Cách kích hoạt | Mục đích | Bộ đếm/quan sát |
|---|---|---|---|
| Retry | Exception thuộc retry policy | Thử lại lỗi có khả năng phục hồi | RetryContext/RetryListener và log/metric. |
| Skip | Exception thuộc skip policy và trong giới hạn | Bỏ qua item lỗi đã được cho phép | Read/process/write skip count và SkipListener. |
| Filter | Processor trả `null` | Loại item hợp lệ nhưng ngoài phạm vi output | `filterCount`. |

Không retry một item chỉ vì nó không cần ghi; dùng filter. Không skip lỗi tạm thời nếu có khả năng phục hồi và dữ liệu bắt buộc phải xử lý; cân nhắc retry. Không dùng retry để xử lý lỗi dữ liệu cố định.

## 10. Retry, rollback và chunk transaction

Chunk thường được thực hiện trong transaction. Khi exception xảy ra, transaction hiện tại có thể rollback theo rollback rules và cấu hình của Step. Sau đó framework thực hiện retry hoặc skip theo policy.

Các điểm cần hiểu:

- Những chunk đã commit trước đó vẫn được giữ lại.
- Chunk hiện tại có thể rollback trước khi thao tác được thử lại.
- Processor có thể được gọi lại cho cùng item.
- Writer có thể được gọi lại với chunk hoặc nhóm item liên quan.
- Reader có thể được gọi lại nếu lỗi xảy ra trong read; item đã đọc trước đó thường được buffer để hỗ trợ rollback.
- Tác dụng phụ ngoài transaction không tự rollback.

Không nên xem retry là rollback toàn bộ Job. Retry chỉ xử lý thao tác/chunk theo cơ chế fault tolerance. Nếu Step thất bại sau khi hết retry, Job có thể được restart theo metadata và checkpoint đã commit.

### noRollback không phải retry

Cấu hình `.noRollback(SomeException.class)` chỉ thay đổi hành vi rollback cho exception được chỉ định. Nó không tự động retry và cũng không tự động skip item.

Chỉ dùng `noRollback` khi transaction có thể tiếp tục nhất quán sau exception. Nếu writer đã ghi một phần dữ liệu và exception cho thấy transaction không còn an toàn, bỏ rollback có thể để lại trạng thái dở dang.

## 11. Stateful retry, reader buffering và checkpoint

Retry operation trong một chunk và restart sau khi process dừng là hai cơ chế khác nhau:

- **Retry trong execution hiện tại:** framework thử lại thao tác sau exception theo retry policy.
- **Restart Job/Step:** Spring Batch tạo JobExecution mới cho cùng JobInstance và khôi phục checkpoint đã lưu trong ExecutionContext nếu reader/writer hỗ trợ.

`RetryContext` lưu trạng thái tạm thời của retry operation. `ExecutionContext` lưu checkpoint bền vững của Job/Step. Không dùng retry count làm checkpoint và không dùng ExecutionContext để thay retry policy.

Reader/writer triển khai `ItemStream` có thể dùng `open`, `update` và `close` để khôi phục/lưu state. Với reader phân trang, nên lưu cursor hoặc khóa cuối cùng đã commit; với file reader, dùng vị trí đọc ổn định. Nếu nguồn thay đổi thứ tự giữa lần chạy và restart, checkpoint theo offset có thể dẫn đến trùng hoặc bỏ sót item.

## 12. RetryListener để quan sát các lần thử

`RetryListener` của Spring Retry có thể ghi nhận vòng đời retry operation thông qua các callback `open`, `onError` và `close`.

Ví dụ listener log exception và retry count:

```java
public class BatchRetryListener implements RetryListener {

    private static final Logger log =
            LoggerFactory.getLogger(BatchRetryListener.class);

    @Override
    public <T, E extends Throwable> boolean open(
            RetryContext context,
            RetryCallback<T, E> callback) {
        return true;
    }

    @Override
    public <T, E extends Throwable> void onError(
            RetryContext context,
            RetryCallback<T, E> callback,
            Throwable throwable) {
        log.warn("Retry count={}, exceptionType={}",
                context.getRetryCount(),
                throwable.getClass().getSimpleName());
    }

    @Override
    public <T, E extends Throwable> void close(
            RetryContext context,
            RetryCallback<T, E> callback,
            Throwable throwable) {
        if (throwable != null) {
            log.error("Retry operation ended with failure", throwable);
        }
    }
}
```

Đăng ký listener trên fault-tolerant Step builder bằng `.listener(retryListener)` theo API của phiên bản Spring Batch/Spring Retry đang dùng. Listener quan sát retry, không quyết định exception có retry hay không.

Với Job chạy đồng thời, listener singleton cần thread-safe. Không lưu retry count của từng item trong field mutable dùng chung; dùng `RetryContext` và metric thread-safe. Không ghi payload nhạy cảm vào log.

## 13. Chọn exception retryable

Một exception phù hợp để retry thường có các đặc điểm:

- Có khả năng tự phục hồi sau một khoảng thời gian.
- Thao tác có thể được thực hiện lại mà không làm hỏng dữ liệu.
- Có timeout và backoff rõ ràng.
- Có giới hạn retry để tránh vòng lặp vô hạn.
- Có thể quan sát và điều tra nếu retry thất bại.

Ví dụ thường cân nhắc:

- Deadlock database.
- Lock acquisition timeout.
- Lỗi kết nối ngắn hạn.
- HTTP 429 hoặc 5xx theo chính sách dịch vụ.
- Timeout của dịch vụ tra cứu có tính idempotent.

Ví dụ thường không nên retry mặc định:

- Dữ liệu thiếu trường bắt buộc.
- Ngày tháng hoặc số tiền không parse được.
- Không tìm thấy file đầu vào bắt buộc.
- Lỗi cấu hình hoặc quyền truy cập bị từ chối cố định.
- Lỗi lập trình như `NullPointerException` không được dự kiến.

Phân loại cần dựa trên nguyên nhân thực tế. Ví dụ HTTP 429 thường cần backoff và tôn trọng `Retry-After`; HTTP 400 do payload sai thường không nên retry. Một HTTP 500 có thể tạm thời nhưng cũng có thể phản ánh lỗi nghiệp vụ ở server.

## 14. Idempotency khi retry read, process và write

Retry có thể gọi lại thao tác. Tính idempotent đặc biệt quan trọng khi thao tác có side effect.

### Reader

Reader cần đọc lại đúng item sau lỗi. Với API phân trang, dùng cursor ổn định hoặc request ID; tránh tăng page/offset trước khi nhận và xác nhận dữ liệu thành công.

### Processor

Processor nên ưu tiên tính toán thuần. Nếu cần gọi API có tác dụng phụ, dùng idempotency key gắn với business key và operation để request lặp không tạo kết quả mới.

### Writer

Writer có thể được gọi lại. Với database, dùng unique business key, upsert hoặc kiểm tra trạng thái phù hợp. Với message/API, dùng outbox/inbox hoặc idempotency key. Không dựa vào transaction JDBC để rollback một request ngoài hệ thống.

Ví dụ API nhận idempotency key:

```java
paymentClient.charge(
        order.orderId(),
        order.amount(),
        "charge-order-" + order.orderId());
```

Đây là ví dụ minh họa; hệ thống đích phải thực sự hỗ trợ idempotency key và lưu kết quả theo key đó. Chỉ gửi một header/key mà API không xử lý thì không tạo ra bảo đảm chống trùng.

## 15. Retry và concurrency

Khi partitioning hoặc multi-threaded Step chạy đồng thời, nhiều item có thể retry cùng lúc. Cần cân nhắc:

- Tổng số retry request có thể tăng đột biến khi dịch vụ gặp sự cố.
- Backoff giúp phân tán tải nhưng không thay thế circuit breaker hoặc rate limiter.
- Reader/processor/writer cần thread safety theo cách Step sử dụng.
- RetryListener và metric cần hỗ trợ truy cập đồng thời.
- Connection pool phải đủ cho số worker nhưng không vượt năng lực database.
- Không giữ lock hoặc transaction lâu trong thời gian backoff nếu cấu hình/đường retry khiến transaction còn mở.

Trong một số cấu hình, transaction của chunk được rollback và retry thực hiện theo một transaction mới; ở các đường xử lý khác, chi tiết transaction phụ thuộc retry policy và transaction attribute. Hãy đo transaction duration và kiểm thử deadlock/timeout trong môi trường tương tự production.

## 16. Kiểm thử retry cho từng giai đoạn

Unit test riêng reader, processor và writer giúp xác nhận hành vi khi gặp exception. Integration test ở cấp Step cần xác nhận Spring Batch thực sự áp dụng retry policy, transaction và skip đúng cách.

### Read retry

- Reader ném transient exception ở lần đầu và trả item ở lần sau.
- Reader không bỏ qua cursor/page sau lần đọc lỗi.
- Khi hết retry, Step có trạng thái đúng theo policy.
- Restart dùng checkpoint đã commit.

### Process retry

- Processor ném transient exception rồi thành công ở lần sau.
- Processor nhận lại đúng item.
- Exception dữ liệu cố định không bị retry ngoài ý muốn.
- Side effect không bị nhân đôi.

### Write retry

- Writer ném deadlock/timeout rồi thành công ở lần sau.
- Transaction rollback dữ liệu ghi dở trước retry.
- Writer không tạo duplicate khi được gọi lại.
- Khi hết retry, skip hoặc fail theo policy.

### Kiểm tra backoff và listener

- Backoff được áp dụng giữa các lần thử theo cấu hình.
- RetryListener nhận callback đúng vòng đời.
- Retry count và exception được ghi nhận chính xác.
- Listener thread-safe khi có nhiều worker.

## 17. Những lỗi thường gặp

### Retry lỗi dữ liệu cố định

Một item thiếu mã hoặc sai định dạng sẽ tiếp tục lỗi ở lần thử sau. Hãy dùng skip hoặc fail theo nghiệp vụ thay vì retry.

### Retry mọi exception

Retry `Exception.class` có thể lặp lỗi lập trình, cấu hình hoặc lỗi không thể phục hồi. Chỉ chọn exception type đã xác định là transient.

### Không đặt retry limit

Retry vô hạn có thể khiến Job không kết thúc và giữ tài nguyên lâu. Luôn có giới hạn và theo dõi retry exhaustion.

### Retry ngay liên tục

Không có backoff có thể làm hệ thống đích quá tải hơn. Dùng fixed hoặc exponential backoff theo đặc tính dịch vụ.

### Giả định writer chỉ được gọi một lần

Write retry hoặc write skip có thể khiến writer được gọi lại. Writer cần transaction hoặc idempotency phù hợp.

### Processor tạo side effect

Processor có thể chạy lại cùng item. Tránh gửi email, publish message hoặc ghi hệ thống ngoài nếu không có chống trùng.

### Nhầm retry với restart Job

Retry xử lý exception trong execution hiện tại. Restart tạo JobExecution mới và khôi phục checkpoint đã lưu. Hai cơ chế có vòng đời và metadata khác nhau.

### Cấu hình retry và skip chồng lấn mà không kiểm thử

Sau khi retry hết giới hạn, exception có thể được skip nếu thuộc skip policy; nếu không, Step thất bại. Xác định rõ hành vi mong muốn và kiểm thử ở giá trị biên.

### Nghĩ backoff là timeout

Backoff chỉ chờ giữa các lần thử. Nó không hủy một lời gọi I/O đang bị treo. Cần timeout riêng cho JDBC, HTTP client và các nguồn dữ liệu.

## 18. Quy trình triển khai retry trong read, process và write

Khi xây dựng fault-tolerant chunk Step, có thể thực hiện theo trình tự:

1. Liệt kê lỗi có thể xảy ra ở reader, processor và writer.
2. Phân loại lỗi dữ liệu cố định, lỗi tạm thời và lỗi nghiêm trọng.
3. Chọn exception type cụ thể cho `.retry(...)`.
4. Đặt retry limit theo SLA và khả năng phục hồi của dịch vụ.
5. Cấu hình backoff nếu retry ngay có thể tạo tải lớn.
6. Xác nhận reader không mất item khi read retry và hỗ trợ checkpoint khi restart.
7. Giữ processor ít side effect và an toàn khi gọi lại.
8. Bảo đảm writer tham gia transaction hoặc có idempotency cho tác dụng phụ ngoài transaction.
9. Xác định retry exhaustion sẽ skip hay fail; đặt skip policy riêng nếu nghiệp vụ cho phép.
10. Thêm RetryListener/metrics để quan sát nhưng không dùng listener thay policy.
11. Kiểm thử lỗi ở cả ba giai đoạn, rollback, backoff, restart và concurrency.

| Giai đoạn | Thiết kế retry an toàn |
|---|---|
| Read | Reader có thể gọi lại mà không bỏ sót item; cursor/checkpoint ổn định. |
| Process | Processor tập trung vào tính toán; external call có idempotency và timeout. |
| Write | Writer chịu được gọi lại; database dùng transaction/unique key, external output dùng outbox hoặc idempotency key. |

## Kết luận

Spring Batch có thể retry lỗi ở cả `ItemReader`, `ItemProcessor` và `ItemWriter` trong fault-tolerant chunk Step. Read retry cần reader không làm mất vị trí khi lần đọc thất bại; process retry có thể gọi lại processor với cùng item; write retry có thể gọi lại writer với chunk hoặc nhóm item liên quan và cần transaction/idempotency phù hợp. Dùng `.retry(...)`, `.retryLimit(...)`, `.noRetry(...)` và `BackOffPolicy` để kiểm soát lỗi tạm thời; dùng skip cho lỗi item đã được phép bỏ qua và fail Step khi không thể tiếp tục an toàn. Hãy phân biệt retry trong execution với restart Job, kiểm thử từng giai đoạn và thiết kế mọi tác dụng phụ có thể lặp theo hướng idempotent.
