# Tự viết ItemWriter

Trong Spring Batch, `ItemWriter<T>` là thành phần nhận các item đầu ra của một chunk và ghi chúng đến đích. Spring Batch có sẵn nhiều writer cho database, file và các định dạng phổ biến. Khi đích ghi hoặc quy tắc ghi không phù hợp với writer tích hợp, ứng dụng có thể tự triển khai `ItemWriter<T>`.

Một custom writer thường cần làm rõ bốn việc: nhận đúng các item trong chunk, ghi theo hợp đồng của hệ thống đích, để exception được truyền về framework khi ghi thất bại và bảo đảm hành vi phù hợp với transaction/restart. Writer không nên tự điều khiển vòng lặp Job, tự commit transaction hoặc âm thầm bỏ item lỗi.

Các ví dụ trong bài dùng API Spring Batch 5, trong đó `ItemWriter` nhận `Chunk<? extends T>`. Với Spring Batch 4 trở về trước, chữ ký writer cũ thường nhận `List<? extends T>`; cần dùng API khớp với phiên bản của dự án.

## 1. Khi nào cần tự viết ItemWriter?

Custom writer phù hợp khi ứng dụng cần:

- Ghi vào một hệ thống nội bộ không có writer tích hợp.
- Gọi API của đối tác để gửi một nhóm bản ghi.
- Áp dụng quy tắc batch-specific trước khi lưu.
- Ghi đồng thời vào nhiều đích theo một chính sách rõ ràng.
- Tích hợp với thư viện hoặc giao thức riêng.
- Bọc một writer có sẵn để bổ sung validation, metrics hoặc audit.

Nếu writer tích hợp đã đáp ứng nhu cầu, nên ưu tiên dùng writer đó. Ví dụ, `JdbcBatchItemWriter` phù hợp cho insert/update JDBC, `FlatFileItemWriter` cho text file và `JsonFileItemWriter` cho JSON array. Custom writer có thể làm tăng trách nhiệm về transaction, resource lifecycle, retry và restart mà framework đã xử lý trong các implementation có sẵn.

## 2. ItemWriter trong chunk-oriented processing

Một chunk Step thực hiện luồng đọc, xử lý và ghi:

```text
ItemReader
    |
    v
ItemProcessor
    |
    v
Chunk<T>
    |
    v
ItemWriter.write(chunk)
    |
    v
Transaction commit
```

Reader tạo item. Processor có thể biến đổi item hoặc trả `null` để filter item. Các item còn lại được gom thành chunk và truyền cho writer. Writer nhận cả chunk trong một lần gọi; nó không được giả định mỗi lần gọi chỉ có một item.

Ví dụ Step có chunk size 100:

```java
return new StepBuilder("exportOrdersStep", jobRepository)
        .<Order, OrderExport>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .build();
```

Nếu có 235 item đầu ra, writer thường được gọi với ba chunk có kích thước 100, 100 và 35. Chunk size quyết định nhóm item được ghi trong một transaction của Step; nó không phải số thread hoặc số lần Job chạy.

## 3. Hợp đồng ItemWriter trong Spring Batch 5

Interface `ItemWriter<T>` có phương thức `write` nhận một `Chunk`:

```java
package org.springframework.batch.item;

public interface ItemWriter<T> {
    void write(Chunk<? extends T> chunk) throws Exception;
}
```

Các điểm quan trọng:

- `T` là kiểu item writer nhận.
- `Chunk<? extends T>` chứa các item của lần ghi hiện tại.
- Phương thức có thể ném exception để báo cho framework rằng thao tác ghi thất bại.
- Writer không trả về danh sách item đã ghi; kết quả được biểu diễn qua việc hoàn tất bình thường hoặc ném exception.
- Framework điều phối transaction, retry, skip và commit theo cấu hình Step.

Trong Spring Batch 5, có thể duyệt item bằng `chunk.getItems()`:

```java
@Override
public void write(Chunk<? extends Order> chunk) {
    for (Order order : chunk.getItems()) {
        // Ghi từng order.
    }
}
```

Không tự gọi `reader.read()` bên trong writer. Reader, processor và writer là các vai trò riêng trong pipeline; việc đọc thêm ở writer làm mất khả năng kiểm soát chunk và checkpoint của framework.

## 4. Custom writer đơn giản ghi vào database

Ví dụ writer dùng `JdbcTemplate` để ghi các đơn hàng vào bảng đích:

```java
public class JdbcOrderWriter implements ItemWriter<OrderExport> {

    private static final String INSERT_SQL = """
            INSERT INTO exported_orders
                (order_id, customer_id, amount, currency)
            VALUES (?, ?, ?, ?)
            """;

    private final JdbcTemplate jdbcTemplate;

    public JdbcOrderWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public void write(Chunk<? extends OrderExport> chunk) {
        for (OrderExport order : chunk.getItems()) {
            jdbcTemplate.update(
                    INSERT_SQL,
                    order.orderId(),
                    order.customerId(),
                    order.amount(),
                    order.currency());
        }
    }
}
```

Writer nhận cả chunk và ghi lần lượt từng item. `JdbcTemplate` bind giá trị vào prepared statement, tránh nối trực tiếp input vào SQL. Nếu một lệnh ghi ném `DataAccessException`, exception được truyền lên Spring Batch để transaction chunk được xử lý theo policy.

Trong production, nếu cần hiệu năng cao, có thể dùng `JdbcTemplate.batchUpdate` hoặc `NamedParameterJdbcTemplate` để gửi batch SQL. Cách triển khai cần giữ nguyên semantics: lỗi ghi phải được truyền ra và không được báo thành công khi chỉ một phần thao tác đã thất bại.

## 5. Đăng ký custom writer thành Spring bean

Có thể tạo writer bằng `@Bean`:

```java
@Bean
ItemWriter<OrderExport> orderExportWriter(JdbcTemplate jdbcTemplate) {
    return new JdbcOrderWriter(jdbcTemplate);
}
```

Sau đó inject vào Step:

```java
@Bean
Step exportOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, OrderExport> orderProcessor,
        ItemWriter<OrderExport> orderExportWriter) {

    return new StepBuilder("exportOrdersStep", jobRepository)
            .<Order, OrderExport>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderExportWriter)
            .build();
}
```

Nếu application có nhiều bean `ItemWriter` cùng kiểu, dùng `@Qualifier` để chỉ định đúng writer. Tên bean nên mô tả đích hoặc mục đích, ví dụ `orderExportWriter`, `customerArchiveWriter`.

Không cần `@StepScope` cho mọi custom writer. Một writer stateless, không phụ thuộc JobParameters và an toàn khi dùng chung có thể là singleton. Chỉ dùng `@StepScope` khi cần resource hoặc tham số theo execution, hoặc khi writer giữ state riêng cho Step.

## 6. Transaction khi custom writer ghi JDBC

Custom writer dùng `JdbcTemplate` có thể tham gia transaction chunk nếu `JdbcTemplate` dùng cùng `DataSource` và transaction manager của Step. Khi đó, các câu lệnh JDBC được thực hiện trên connection gắn với transaction hiện tại của Spring.

```text
Chunk transaction
    |
    +--> Writer: INSERT order 1
    +--> Writer: INSERT order 2
    +--> Writer: INSERT order 3
    +--> Exception khi ghi order 3
    |
    v
Rollback transaction
    |
    +--> Các thay đổi trong transaction chưa commit được hoàn tác
```

Điều này chỉ đúng khi resource thực sự tham gia cùng transaction. Nếu writer dùng một `DataSource` khác với transaction manager, tự mở connection độc lập hoặc gọi hệ thống ngoài, rollback của chunk không tự hoàn tác resource đó.

Không gọi `connection.commit()` hoặc `transactionManager.commit()` thủ công trong `write`. Framework quản lý ranh giới transaction. Tự commit có thể khiến dữ liệu được ghi bền vững trước khi chunk hoàn tất, làm mất khả năng rollback đúng khi processor/writer gặp lỗi.

## 7. Không nuốt exception trong write

Writer phải báo thất bại bằng cách ném exception. Không bắt exception rồi chỉ log:

```java
// Không nên
@Override
public void write(Chunk<? extends OrderExport> chunk) {
    try {
        persist(chunk);
    } catch (DataAccessException exception) {
        log.error("Could not write orders", exception);
        // Framework sẽ nghĩ write đã thành công.
    }
}
```

Nếu writer không ném exception, Spring Batch có thể coi chunk đã ghi thành công và tiếp tục commit. Các item bị lỗi khi đó có thể bị mất khỏi luồng xử lý mà Job vẫn báo `COMPLETED`.

Hãy truyền exception lên framework hoặc wrap bằng exception có ngữ cảnh nhưng giữ nguyên cause:

```java
try {
    persist(order);
} catch (DataAccessException exception) {
    throw new OrderWriteException(
            "Could not persist order " + order.orderId(),
            exception);
}
```

Không wrap mọi exception thành cùng một loại nếu điều đó làm mất khả năng phân loại lỗi transient, dữ liệu hoặc lỗi cấu hình. Giữ cause chain để retry/skip policy và người vận hành có thể xác định nguyên nhân.

## 8. Ghi theo batch thay vì từng item

Vòng lặp `jdbcTemplate.update` dễ hiểu nhưng tạo một lần gọi JDBC cho mỗi item. Với chunk lớn, có thể dùng batch update để giảm round trip:

```java
public class JdbcOrderWriter implements ItemWriter<OrderExport> {

    private final JdbcTemplate jdbcTemplate;

    public JdbcOrderWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public void write(Chunk<? extends OrderExport> chunk) {
        jdbcTemplate.batchUpdate(
                """
                INSERT INTO exported_orders
                    (order_id, customer_id, amount, currency)
                VALUES (?, ?, ?, ?)
                """,
                chunk.getItems(),
                chunk.size(),
                (statement, order) -> {
                    statement.setLong(1, order.orderId());
                    statement.setString(2, order.customerId());
                    statement.setBigDecimal(3, order.amount());
                    statement.setString(4, order.currency());
                });
    }
}
```

Batch update có thể tăng throughput, nhưng cách driver/database báo lỗi theo batch khác nhau. Hãy kiểm thử khi một row vi phạm constraint, khi batch bị timeout và khi transaction rollback. Không giả định mọi driver luôn xác định chính xác item lỗi theo cùng một cách.

## 9. Custom writer ghi vào API bên ngoài

Một custom writer có thể gửi các item đến service ngoài:

```java
public class PartnerOrderWriter implements ItemWriter<OrderExport> {

    private final PartnerClient partnerClient;

    public PartnerOrderWriter(PartnerClient partnerClient) {
        this.partnerClient = partnerClient;
    }

    @Override
    public void write(Chunk<? extends OrderExport> chunk) {
        for (OrderExport order : chunk.getItems()) {
            partnerClient.upsertOrder(
                    order.orderId(),
                    order,
                    "order-export-" + order.orderId());
        }
    }
}
```

Ví dụ giả định API đối tác hỗ trợ operation idempotent hoặc idempotency key. Nếu gọi HTTP thành công ở server nhưng client timeout trước khi nhận response, Spring Batch có thể retry writer. Lần gọi lại phải dùng cùng key để hệ thống đích không tạo side effect trùng.

Transaction JDBC của chunk không rollback được request HTTP đã được đối tác xử lý. Với tích hợp quan trọng, cân nhắc ghi outbox trong transaction của chunk rồi để relay riêng gửi request. Writer gọi API trực tiếp chỉ phù hợp khi semantics retry, timeout và deduplication đã được xác định rõ.

## 10. Writer nhận chunk nhưng không nên tự quản lý transaction

Một custom writer có thể ghi nhiều item trong một lần gọi, nhưng không nên tự tạo transaction mới cho từng item nếu muốn các thay đổi thuộc cùng chunk được commit/rollback cùng nhau.

Ví dụ không phù hợp:

```java
for (OrderExport order : chunk.getItems()) {
    transactionTemplate.execute(status -> {
        repository.save(order);
        return null;
    });
}
```

Nếu mỗi item được commit độc lập, một lỗi ở item cuối có thể để lại các item trước đã commit dù chunk thất bại. Điều này phá vỡ atomicity mà người đọc thường kỳ vọng từ chunk transaction.

Nếu nghiệp vụ thực sự yêu cầu transaction riêng từng item, hãy thiết kế Step/flow phù hợp và ghi rõ semantics. Đừng vô tình tạo transaction riêng chỉ vì custom writer muốn kiểm soát thao tác ghi.

## 11. Custom writer có state: ItemStreamWriter

`ItemWriter` đơn giản đủ cho writer stateless. Nếu writer quản lý resource hoặc cần lưu state để restart, hãy triển khai `ItemStreamWriter<T>`, interface kết hợp `ItemWriter<T>` và `ItemStream`.

`ItemStream` định nghĩa ba callback:

```java
public interface ItemStream {
    void open(ExecutionContext executionContext)
            throws ItemStreamException;

    void update(ExecutionContext executionContext)
            throws ItemStreamException;

    void close() throws ItemStreamException;
}
```

Vai trò:

- `open`: mở resource và khôi phục state từ ExecutionContext.
- `update`: lưu state hiện tại để checkpoint cùng chunk.
- `close`: giải phóng handle/resource khi vòng đời Step kết thúc bình thường.

Ví dụ custom writer bọc một writer khác và bổ sung validation:

```java
public class ValidatingOrderWriter
        implements ItemStreamWriter<OrderExport> {

    private final ItemStreamWriter<OrderExport> delegate;

    public ValidatingOrderWriter(
            ItemStreamWriter<OrderExport> delegate) {
        this.delegate = delegate;
    }

    @Override
    public void write(Chunk<? extends OrderExport> chunk)
            throws Exception {

        for (OrderExport order : chunk.getItems()) {
            if (order.orderId() == null || order.amount() == null) {
                throw new IllegalArgumentException(
                        "Order id and amount are required");
            }
        }

        delegate.write(chunk);
    }

    @Override
    public void open(ExecutionContext executionContext)
            throws ItemStreamException {
        delegate.open(executionContext);
    }

    @Override
    public void update(ExecutionContext executionContext)
            throws ItemStreamException {
        delegate.update(executionContext);
    }

    @Override
    public void close() throws ItemStreamException {
        delegate.close();
    }
}
```

Ví dụ cho thấy một decorator phải chuyển tiếp cả ba callback lifecycle đến delegate. Nếu chỉ gọi `delegate.write` mà quên `open`, `update` và `close`, writer bên trong có thể không mở resource, không lưu checkpoint hoặc không đóng file đúng cách.

Khi đăng ký decorator, hãy bảo đảm Spring Batch nhận diện bean là `ItemStreamWriter` hoặc đăng ký stream delegate theo cơ chế phù hợp. Đừng che mất interface `ItemStream` khi bọc một writer có state.

## 12. Lưu state riêng trong ExecutionContext

Nếu writer tự quản lý state, `update` ghi state vào `ExecutionContext` và `open` khôi phục state đó. Key nên có prefix riêng, ổn định và không xung đột với component khác.

Ví dụ về nguyên tắc:

```java
private static final String LAST_WRITTEN_ID =
        "customOrderWriter.lastWrittenId";

@Override
public void open(ExecutionContext context) {
    if (context.containsKey(LAST_WRITTEN_ID)) {
        lastWrittenId = context.getLong(LAST_WRITTEN_ID);
    } else {
        lastWrittenId = 0L;
    }
}

@Override
public void update(ExecutionContext context) {
    context.putLong(LAST_WRITTEN_ID, lastWrittenId);
}
```

Đây chỉ là minh họa lưu state. Trong writer thực tế, chỉ cập nhật `lastWrittenId` sau khi thao tác ghi của item/chunk thành công theo semantics transaction đã chọn. Nếu resource ngoài transaction, state trong ExecutionContext có thể commit khác thời điểm với side effect; cần idempotency hoặc reconciliation.

Không lưu object lớn, connection, stream hoặc credential vào ExecutionContext. Nên lưu giá trị nhỏ, có thể serialize và dùng để khôi phục resource.

## 13. Resource lifecycle và đóng tài nguyên

Writer quản lý file, socket hoặc cursor cần đóng resource đúng vòng đời. Hãy xác định ai sở hữu resource:

- Nếu writer tự tạo resource, writer thường chịu trách nhiệm đóng nó.
- Nếu resource được inject từ bên ngoài, hợp đồng sở hữu cần được xác định để tránh đóng resource dùng chung.
- Nếu writer delegate quản lý resource, decorator phải chuyển tiếp lifecycle.
- Không đóng connection do Spring transaction manager quản lý bằng cách tự lấy và đóng connection từ transaction-bound context.

`close()` giải phóng resource khi framework kết thúc stream lifecycle bình thường. Process bị kill đột ngột có thể không gọi `close()`. Với file tạm hoặc resource ngoài, cần cơ chế cleanup/recovery riêng cho trường hợp crash.

## 14. Retry và write failure

Nếu `write` ném exception thuộc retry policy, Spring Batch có thể thử lại thao tác ghi theo cấu hình fault tolerance. Vì vậy, custom writer phải chịu được việc được gọi lại.

Các nguyên tắc:

- Chỉ retry lỗi có khả năng phục hồi, ví dụ deadlock hoặc lỗi kết nối tạm thời.
- Đặt retry limit và backoff phù hợp.
- Không retry lỗi dữ liệu cố định như thiếu field bắt buộc.
- Không nuốt exception rồi trả về bình thường.
- Nếu writer có side effect ngoài transaction, dùng idempotency key hoặc deduplication.
- Không lưu state mutable dùng chung làm sai lệch giữa các lần retry.

Ví dụ cấu hình:

```java
return new StepBuilder("exportOrdersStep", jobRepository)
        .<Order, OrderExport>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
```

`retryLimit` và cách đếm attempt cần được hiểu theo API/phiên bản Spring Batch đang dùng. Nếu retry exhaustion phải chuyển sang skip, cần cấu hình skip policy rõ ràng và kiểm thử tương tác giữa retry và skip.

## 15. Skip và write failure

Spring Batch có thể skip một item nếu exception từ writer được phép bởi skip policy và skip limit chưa bị vượt. Trong một số tình huống, framework cần cô lập item gây lỗi bằng cách thử lại các nhóm nhỏ hơn hoặc từng item; do đó writer có thể được gọi nhiều lần với các chunk khác nhau khi write skip được bật.

Điều này có nghĩa custom writer không nên:

- Giả định chunk luôn có đúng một kích thước cố định.
- Tạo side effect không thể lặp trong lần ghi đầu rồi mong framework không gọi lại.
- Thay đổi nội dung chunk hoặc loại item ra khỏi danh sách mà không có hợp đồng rõ.
- Dựa vào vị trí item trong chunk như một ID bền vững.

Ví dụ cấu hình skip lỗi dữ liệu:

```java
.faultTolerant()
.skip(InvalidOrderException.class)
.skipLimit(20)
```

Với lỗi dữ liệu, thường tốt hơn nếu validate trong processor để xác định item lỗi trước khi writer thực hiện side effect. Writer nên tập trung ghi các item đã hợp lệ.

## 16. Writer và filter không giống nhau

Processor trả `null` để filter item hợp lệ nhưng không cần ghi. Writer nhận các item còn lại. Nếu writer tự bỏ qua item mà không báo framework, các counter và audit có thể không phản ánh đúng.

| Nhu cầu | Thành phần phù hợp |
|---|---|
| Loại item theo điều kiện nghiệp vụ | `ItemProcessor` trả `null` |
| Biến đổi item sang output model | `ItemProcessor` |
| Ghi item đến đích | `ItemWriter` |
| Bỏ qua item do exception được cho phép | Skip policy và `SkipListener` |
| Ghi log trước/sau thao tác write | `ItemWriteListener` |

Không dùng writer để thay thế processor cho các quy tắc lọc phức tạp. Việc đó làm khó kiểm thử và khó phân biệt số item được filter với số item thực sự được ghi.

## 17. ItemWriteListener và trách nhiệm của writer

`ItemWriteListener` cho phép quan sát vòng đời write:

- `beforeWrite`: trước khi writer được gọi.
- `afterWrite`: sau khi writer hoàn tất bình thường.
- `onWriteError`: khi thao tác writer ném exception.

Listener thích hợp cho logging, metrics và audit. Nó không thay thế writer và không nên tự ghi lại cùng output.

Ví dụ:

```java
public class OrderWriteListener implements ItemWriteListener<OrderExport> {

    @Override
    public void beforeWrite(Chunk<? extends OrderExport> items) {
        log.debug("Writing {} orders", items.size());
    }

    @Override
    public void afterWrite(Chunk<? extends OrderExport> items) {
        log.info("Wrote {} orders", items.size());
    }

    @Override
    public void onWriteError(
            Exception exception,
            Chunk<? extends OrderExport> items) {
        log.error("Could not write {} orders", items.size(), exception);
    }
}
```

Đăng ký listener trên Step bằng `.listener(orderWriteListener)`. Khi retry, callback có thể được gọi nhiều lần; log/metric nên phản ánh attempt và không được hiểu nhầm mỗi `afterWrite` là một commit nghiệp vụ cuối cùng nếu transaction còn có thể rollback.

## 18. Composite và routing writer

Nếu nhu cầu chỉ là gửi cùng item đến nhiều writer, Spring Batch có `CompositeItemWriter`. Nếu cần chọn writer theo loại item, có thể cân nhắc `ClassifierCompositeItemWriter` hoặc một routing pattern phù hợp phiên bản.

Không nên tự viết một writer điều phối phức tạp nếu component có sẵn đáp ứng. Tuy nhiên, custom composite có thể cần thiết khi phải áp dụng quy tắc thứ tự, xử lý lỗi hoặc phối hợp nhiều đích đặc thù.

Khi ghi nhiều đích, phải xác định transaction boundary. Nếu một writer ghi database và writer khác gọi API, transaction database không thể rollback API. Nếu writer thứ nhất thành công và writer thứ hai thất bại, retry có thể gọi lại writer thứ nhất. Mỗi đích cần transaction chung hoặc idempotency/deduplication phù hợp.

## 19. Thread safety và scope

Một writer singleton có thể được gọi từ nhiều execution hoặc thread nếu ứng dụng chạy partitioning/multi-threaded Step hoặc nhiều Job đồng thời. Hãy quyết định rõ writer có được chia sẻ hay không.

Writer stateless dùng `JdbcTemplate` thường có thể là singleton vì `JdbcTemplate` được thiết kế để dùng chung. Tuy nhiên, writer tự giữ các field mutable như current file, counter, buffer hoặc current tenant cần scope riêng hoặc đồng bộ phù hợp.

Các nguyên tắc:

- Không lưu item hiện tại vào field singleton.
- Không dùng một `BufferedWriter` chung cho nhiều Job nếu không có cơ chế ownership/locking.
- Dùng `@StepScope` khi resource/path/state thuộc một StepExecution.
- Không tạo static mutable state cho retry count hoặc item list.
- Nếu writer có thể được gọi đồng thời, bảo đảm collaborator và resource thread-safe.
- Kiểm thử hai Job chạy song song với output khác nhau.

## 20. Idempotency khi writer được gọi lại

Một chunk có thể được ghi lại sau rollback/retry hoặc khi restart từ checkpoint. Nếu writer tạo side effect ngoài transaction, phải tránh trùng lặp.

Ví dụ các biện pháp:

- Database: unique business key, upsert hoặc operation ID.
- HTTP API: idempotency key ổn định theo business operation.
- Message broker: event ID ổn định và deduplication ở consumer.
- File: staging path theo JobInstance, checksum và publish idempotent.
- Nhiều resource: outbox/inbox hoặc reconciliation.

Không tạo idempotency key ngẫu nhiên mới trong mỗi lần gọi `write`. Key phải đại diện cho operation nghiệp vụ và giữ nguyên qua retry/restart.

Nếu writer chỉ ghi vào database cùng transaction của chunk, rollback có thể hoàn tác các thay đổi chưa commit. Dù vậy, vẫn cần xem xét unique key khi có nhiều Job cùng xử lý business record hoặc trạng thái commit không rõ ràng sau lỗi kết nối.

## 21. Validation trong custom writer

Writer có thể kiểm tra điều kiện kỹ thuật trước khi ghi, ví dụ object không null, ID bắt buộc tồn tại hoặc chunk không vượt giới hạn API. Nhưng các quy tắc nghiệp vụ phức tạp thường nên đặt trong processor hoặc validator riêng.

Ví dụ kiểm tra đơn giản:

```java
private void validate(OrderExport order) {
    if (order.orderId() == null) {
        throw new InvalidOrderException("orderId is required");
    }
    if (order.amount() == null || order.amount().signum() < 0) {
        throw new InvalidOrderException("amount must be non-negative");
    }
}
```

Nếu writer validate toàn bộ chunk trước khi ghi, một item không hợp lệ sẽ làm cả lần write thất bại. Nếu skip policy bật, framework có thể cần cô lập item gây lỗi. Với dữ liệu cần reject từng item, validate trong processor thường giúp xác định và ghi nhận lỗi rõ hơn trước khi writer nhận chunk.

Không mutate item hoặc loại item khỏi chunk bên trong writer. Nếu cần chuyển đổi dữ liệu, thực hiện trong processor để output type và counters nhất quán.

## 22. Logging và metrics

Writer là vị trí phù hợp để ghi nhận thông tin thao tác ghi ở mức chunk:

- Tên Job/Step hoặc operation category.
- Số item trong chunk.
- Thời gian thực hiện write.
- Đích ghi hoặc loại đích.
- Kết quả thành công/thất bại.
- Exception category và retry attempt nếu có context.

Tránh log toàn bộ item hoặc payload nhạy cảm. Không dùng order ID/customer ID làm metric tag có cardinality cao. Nếu cần truy vết một item, dùng structured log với quyền truy cập phù hợp.

`afterWrite` chỉ cho biết writer trả về bình thường; transaction của chunk vẫn có thể rollback sau đó. Khi báo cáo metric “đã commit”, hãy dùng điểm quan sát thực sự sau commit hoặc metadata/counter phù hợp, không nhầm write success với transaction commit.

## 23. Kiểm thử custom ItemWriter

Nên có unit test cho logic writer và integration test cho transaction/Step behavior.

### Unit test với mock collaborator

Ví dụ test writer JDBC:

```java
@Test
void writesEveryItemInChunk() {
    JdbcTemplate jdbcTemplate = mock(JdbcTemplate.class);
    JdbcOrderWriter writer = new JdbcOrderWriter(jdbcTemplate);

    OrderExport first = new OrderExport(
            1001L, "C001", new BigDecimal("250000.00"), "VND");
    OrderExport second = new OrderExport(
            1002L, "C002", new BigDecimal("175000.00"), "VND");

    Chunk<OrderExport> chunk = new Chunk<>();
    chunk.add(first);
    chunk.add(second);

    writer.write(chunk);

    verify(jdbcTemplate, times(2)).update(
            anyString(), any(), any(), any(), any());
}
```

Test xác nhận writer gửi đủ item đến collaborator. Có thể kiểm tra chính xác tham số từng lệnh bằng `ArgumentCaptor` nếu mapping field quan trọng.

### Kiểm thử exception được truyền ra

```java
@Test
void propagatesDatabaseFailure() {
    JdbcTemplate jdbcTemplate = mock(JdbcTemplate.class);
    when(jdbcTemplate.update(
            anyString(), any(), any(), any(), any()))
            .thenThrow(new DataAccessResourceFailureException("database down"));

    JdbcOrderWriter writer = new JdbcOrderWriter(jdbcTemplate);
    Chunk<OrderExport> chunk = new Chunk<>();
    chunk.add(new OrderExport(
            1001L, "C001", new BigDecimal("250000.00"), "VND"));

    assertThatThrownBy(() -> writer.write(chunk))
            .isInstanceOf(DataAccessResourceFailureException.class);
}
```

Điểm cần xác nhận là writer không nuốt exception. Test thực tế cần dùng signature mock khớp overload `JdbcTemplate` của phiên bản Spring Framework đang dùng.

### Integration test transaction

Với database test, tạo một chunk có nhiều item và làm một lệnh ghi thất bại. Sau khi Step rollback, xác nhận không có bản ghi nào của chunk chưa commit nếu tất cả thao tác tham gia cùng transaction. Đồng thời xác nhận các chunk đã commit trước đó vẫn tồn tại.

### Test retry, skip và restart

- Writer gặp lỗi transient rồi thành công: số lần gọi và dữ liệu cuối đúng.
- Writer gặp lỗi dữ liệu: skip/fail theo policy.
- Retry exhaustion: Step có trạng thái và failure exception đúng.
- Restart: writer mở lại đúng resource và state.
- External sink: cùng idempotency key không tạo side effect trùng.
- Concurrent execution: state và output của các Job không bị lẫn.

## 24. Những lỗi thường gặp

### Coi chunk như một item

Trong Spring Batch 5, `write` nhận `Chunk`, không phải một object đơn lẻ. Hãy duyệt toàn bộ item trong chunk và hiểu chunk size do Step cấu hình.

### Dùng chữ ký List của phiên bản cũ

Code `write(List<? extends T>)` không khớp interface Spring Batch 5. Dùng đúng signature `write(Chunk<? extends T>)` cho phiên bản hiện tại.

### Nuốt exception và chỉ log

Framework sẽ coi write thành công và có thể commit chunk. Truyền exception ra để retry/skip/fail được áp dụng.

### Tự commit transaction

Commit bên trong writer phá vỡ transaction boundary của chunk. Để Spring Batch điều phối transaction.

### Gọi API không idempotent trong writer

Retry có thể gửi side effect lần nữa sau timeout. Dùng idempotency key, outbox hoặc reconciliation.

### Quên ItemStream lifecycle khi bọc writer

Delegate có thể không được mở, cập nhật checkpoint hoặc đóng. Chuyển tiếp `open`, `update` và `close`.

### Giữ mutable state trong singleton

Các execution có thể ghi đè state của nhau. Dùng writer stateless, StepScope hoặc cơ chế đồng bộ/ownership phù hợp.

### Đặt validation nghiệp vụ quá sâu trong writer

Khó xác định item lỗi và áp dụng skip. Validate dữ liệu trước writer, thường ở processor.

### Giả định write success nghĩa là đã commit

Transaction có thể rollback sau callback write. Phân biệt writer hoàn tất với chunk commit.

### Tự triển khai lại writer tích hợp

Custom code có thể bỏ sót checkpoint, encoding, rollback và restart. Ưu tiên writer có sẵn nếu đáp ứng yêu cầu.

## 25. Quy trình thiết kế custom ItemWriter

Khi cần tự viết writer, có thể thực hiện theo trình tự:

1. Xác định output type và đích ghi.
2. Kiểm tra writer tích hợp có đáp ứng được yêu cầu không.
3. Chọn `ItemWriter<T>` stateless hay `ItemStreamWriter<T>` có resource/state.
4. Triển khai `write(Chunk<? extends T>)` và xử lý toàn bộ item trong chunk.
5. Để exception truyền ra; wrap có cause nếu cần thêm ngữ cảnh.
6. Xác định transaction manager và resource có tham gia transaction chunk không.
7. Không tự commit/rollback bên trong writer.
8. Nếu có external side effect, thiết kế idempotency key, outbox hoặc deduplication.
9. Nếu writer có state, triển khai `open`, `update`, `close` và lưu state nhỏ trong ExecutionContext.
10. Bảo đảm writer thread-safe hoặc có scope riêng theo StepExecution.
11. Đăng ký writer thành bean và inject vào Step.
12. Thêm ItemWriteListener cho metrics/audit nếu cần, không thay logic writer bằng listener.
13. Unit test chunk mapping và exception propagation.
14. Integration test transaction, retry, skip, restart và concurrency.

| Nhu cầu | Lựa chọn |
|---|---|
| Writer stateless, ghi database cùng transaction | `ItemWriter<T>` + `JdbcTemplate` dùng cùng DataSource/transaction manager |
| Writer quản lý file/cursor và checkpoint | `ItemStreamWriter<T>` |
| Bọc writer có sẵn để validation | Decorator chuyển tiếp `write`, `open`, `update`, `close` |
| Ghi API bên ngoài | Custom writer với timeout, retry policy và idempotency |
| Ghi cùng item đến nhiều đích | `CompositeItemWriter` nếu phù hợp; xác định transaction từng đích |
| Chỉ cần logging/metrics quanh write | `ItemWriteListener` |

## Kết luận

Tự viết `ItemWriter<T>` trong Spring Batch 5 bằng cách triển khai `write(Chunk<? extends T>)` và xử lý toàn bộ item của chunk theo hợp đồng đích ghi. Writer nên tập trung vào thao tác ghi, truyền exception ra framework và để Step quản lý transaction, retry, skip và commit. Nếu writer quản lý resource hoặc cần checkpoint, triển khai `ItemStreamWriter<T>` và chuyển tiếp `open`, `update`, `close`; nếu gọi hệ thống ngoài, bảo đảm idempotency vì retry có thể lặp side effect. Giữ writer stateless/thread-safe khi có thể, dùng DTO phù hợp, kiểm thử exception propagation, transaction, restart và concurrency, đồng thời ưu tiên writer tích hợp khi chúng đã đáp ứng yêu cầu.
