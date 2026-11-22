# Ghi cùng item đến nhiều writer

Trong Spring Batch, một Step đôi khi cần ghi cùng một tập item đến nhiều đích. Ví dụ, mỗi đơn hàng đã xử lý cần được lưu vào database đồng thời xuất ra file CSV để hệ thống khác nhận, hoặc một bản ghi cần được ghi vào bảng nghiệp vụ và bảng audit. `CompositeItemWriter<T>` hỗ trợ cách làm này bằng cách gọi nhiều `ItemWriter` delegate theo thứ tự cấu hình.

Mỗi delegate nhận cùng chunk item mà composite nhận được. Composite không tự biến đổi item và cũng không tự tạo transaction phân tán giữa các đích. Vì vậy, khi dùng nhiều writer, cần hiểu thứ tự gọi, lifecycle của delegate, transaction boundary, khả năng rollback và tính idempotent của từng đích ghi.

## 1. CompositeItemWriter là gì?

`CompositeItemWriter<T>` là một `ItemWriter<T>` đóng vai trò điều phối. Nó giữ một danh sách writer delegate và chuyển cùng chunk đến từng writer theo thứ tự đã cấu hình.

Ví dụ một Step xử lý `Order` cần ghi vào hai nơi:

- `JdbcBatchItemWriter<Order>` lưu đơn hàng vào database.
- `FlatFileItemWriter<Order>` xuất cùng đơn hàng ra file CSV.

```text
ItemReader<Order>
       |
       v
ItemProcessor<Order, Order>
       |
       v
Chunk<Order>
       |
       v
CompositeItemWriter<Order>
       |
       +------> JdbcBatchItemWriter ------> Database
       |
       +------> FlatFileItemWriter -------> CSV file
```

Nếu chunk có 100 `Order`, mỗi delegate được gọi với chunk đó. Composite không chia 100 item thành hai nhóm và cũng không chọn một writer duy nhất cho từng item.

## 2. CompositeItemWriter khác với writer định tuyến

Có hai nhu cầu thường bị nhầm lẫn:

- Ghi mọi item đến tất cả writer: dùng `CompositeItemWriter`.
- Chọn một writer phù hợp cho mỗi item: dùng `ClassifierCompositeItemWriter` hoặc một cơ chế routing tương đương.

| Tiêu chí | `CompositeItemWriter` | `ClassifierCompositeItemWriter` |
|---|---|---|
| Quy tắc | Gọi mọi delegate cho cùng chunk | Chọn delegate theo classifier cho từng item |
| Một item được ghi ở đâu? | Tất cả writer trong danh sách | Writer được chọn cho item đó |
| Ví dụ | Lưu DB và xuất audit file cùng lúc | Đơn hàng nội địa vào writer A, quốc tế vào writer B |
| Số lần ghi | Một lần trên mỗi delegate | Một lần trên writer được phân loại |

Nếu yêu cầu là “mỗi đơn hàng vừa lưu database vừa ghi file”, `CompositeItemWriter` phù hợp. Nếu yêu cầu là “đơn hàng loại A ghi database A, loại B ghi database B”, cần routing writer.

## 3. Cấu hình CompositeItemWriter bằng builder

Spring Batch cung cấp `CompositeItemWriterBuilder<T>` để khai báo danh sách delegate:

```java
@Bean
public CompositeItemWriter<Order> orderCompositeWriter(
        JdbcBatchItemWriter<Order> databaseOrderWriter,
        FlatFileItemWriter<Order> orderFileWriter) {

    return new CompositeItemWriterBuilder<Order>()
            .delegates(List.of(databaseOrderWriter, orderFileWriter))
            .build();
}
```

Danh sách delegate xác định thứ tự gọi. Trong ví dụ, database writer được gọi trước, sau đó file writer. Thứ tự cần được chọn có chủ đích vì một delegate có thể hoàn tất trước khi delegate tiếp theo gặp lỗi.

Composite nên được cấu hình một lần trong application context. Các writer delegate được Spring inject và quản lý lifecycle. Không tạo lại delegate bên trong mỗi lần `write()` vì việc đó làm mất state, checkpoint và tài nguyên đã được cấu hình.

## 4. Ví dụ hai writer: database và CSV file

Giả sử một `Order` cần được lưu vào bảng `processed_order` và đồng thời xuất ra file `processed-orders.csv`.

Database writer:

```java
@Bean
public JdbcBatchItemWriter<Order> databaseOrderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("""
                    INSERT INTO processed_order (order_id, customer_name, amount)
                    VALUES (:orderId, :customerName, :amount)
                    """)
            .beanMapped()
            .build();
}
```

File writer:

```java
@Bean
@StepScope
public FlatFileItemWriter<Order> orderFileWriter(
        @Value("#{jobParameters['outputFile']}") String outputFile) {

    return new FlatFileItemWriterBuilder<Order>()
            .name("orderFileWriter")
            .resource(new FileSystemResource(outputFile))
            .delimited()
            .delimiter(",")
            .names("orderId", "customerName", "amount")
            .saveState(true)
            .build();
}
```

Composite writer:

```java
@Bean
public CompositeItemWriter<Order> orderCompositeWriter(
        JdbcBatchItemWriter<Order> databaseOrderWriter,
        FlatFileItemWriter<Order> orderFileWriter) {

    return new CompositeItemWriterBuilder<Order>()
            .delegates(List.of(databaseOrderWriter, orderFileWriter))
            .build();
}
```

Ở đây file path được lấy từ JobParameters qua `@StepScope`, còn database writer dùng `DataSource` do Spring quản lý. File writer có tên ổn định và bật `saveState(true)` để hỗ trợ checkpoint/restart.

## 5. Đăng ký CompositeItemWriter trong Step

Composite writer được truyền vào Step như một writer bình thường:

```java
@Bean
public Step exportProcessedOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, Order> orderProcessor,
        CompositeItemWriter<Order> orderCompositeWriter) {

    return new StepBuilder("exportProcessedOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderCompositeWriter)
            .build();
}
```

Với chunk size 100, Spring Batch gọi `orderCompositeWriter.write(...)` cho chunk hiện tại. Composite lần lượt gọi database writer và file writer với cùng các `Order`.

Trong các phiên bản Spring Batch hiện đại, `CompositeItemWriter` triển khai `ItemStreamWriter` và có thể chuyển tiếp lifecycle đến các delegate triển khai `ItemStream`. Nếu dùng phiên bản cũ hoặc delegate bị ẩn trong wrapper/proxy mà framework không nhận diện được, cần kiểm tra việc đăng ký stream và có thể đăng ký delegate tường minh bằng `.stream(...)` trên Step. Không đăng ký trùng lifecycle cho cùng delegate.

## 6. Thứ tự gọi các delegate

Composite gọi delegate theo thứ tự trong danh sách cấu hình. Ví dụ:

```java
.delegates(List.of(databaseWriter, fileWriter, auditWriter))
```

Thứ tự là:

1. `databaseWriter.write(chunk)`.
2. `fileWriter.write(chunk)`.
3. `auditWriter.write(chunk)`.

Nếu một delegate ném exception, lời gọi composite không thể tiếp tục hoàn tất bình thường. Các delegate sau có thể chưa được gọi. Các delegate đã chạy trước đó có thể đã tạo side effect.

Hãy sắp xếp thứ tự dựa trên đặc tính transaction và độ tin cậy của từng đích. Thứ tự không tạo ra atomicity giữa các hệ thống. Nó chỉ xác định thứ tự gọi method.

Nếu một delegate cần dữ liệu do delegate khác tạo ra, hãy cân nhắc chuyển phần tạo dữ liệu đó vào processor hoặc một service có contract rõ ràng. Không nên dựa vào việc writer trước sửa trực tiếp item để writer sau nhận giá trị mới.

## 7. Mọi delegate nhận cùng chunk

`CompositeItemWriter` gửi cùng chunk cho mỗi delegate. Vì vậy, writer delegate phải chấp nhận cùng kiểu item và hiểu cùng ý nghĩa dữ liệu.

Ví dụ:

```text
Chunk<Order> = [orderA, orderB, orderC]

databaseWriter.write([orderA, orderB, orderC])
fileWriter.write([orderA, orderB, orderC])
auditWriter.write([orderA, orderB, orderC])
```

Nếu các đích cần biểu diễn dữ liệu khác nhau, có thể:

- Dùng các extractor/mapper riêng trong từng writer.
- Dùng một model chung chứa đủ dữ liệu cho các đích.
- Chuẩn hóa hoặc enrich item trong processor trước khi đến composite.
- Viết adapter `ItemWriter` cho một đích để chuyển model sang schema đích.

Tránh để một delegate thay đổi object nhận được theo cách ảnh hưởng đến delegate tiếp theo. Item nên được xem là dữ liệu đầu vào bất biến trong quá trình fan-out. Nếu cần biến đổi riêng, hãy tạo DTO/representation riêng bên trong delegate.

## 8. CompositeItemWriter không tự tạo transaction

Composite chỉ điều phối lời gọi writer. Transaction của chunk do Step và `PlatformTransactionManager` quản lý.

Nếu tất cả delegate ghi vào cùng database và cùng transaction manager, các câu lệnh ghi có thể tham gia cùng transaction. Khi một delegate thất bại, rollback có thể hoàn tác các thay đổi database chưa commit của delegate trước đó.

Nhưng nếu các delegate ghi đến nhiều loại resource khác nhau, ví dụ database, file, HTTP API và message broker, transaction của database không tự động hoàn tác mọi side effect bên ngoài.

| Đích ghi | Rollback của transaction DB có tự hoàn tác không? |
|---|---|
| Bảng trong cùng database/transaction | Thường có, nếu cùng transaction manager/resource |
| Database khác với transaction manager riêng | Không, trừ khi có cơ chế phối hợp transaction phù hợp |
| File thông thường | Không có distributed atomicity; writer có thể có transactional buffering riêng |
| HTTP API | Không |
| Email hoặc hệ thống notification | Không |
| Message broker | Chỉ khi broker tham gia transaction được phối hợp phù hợp |

Vì vậy, không nên diễn giải việc `CompositeItemWriter` gọi nhiều writer trong cùng một Step là tất cả đích sẽ commit hoặc rollback nguyên tử cùng nhau.

## 9. Điều gì xảy ra nếu writer thứ hai thất bại?

Giả sử composite gọi database writer trước rồi file writer:

```text
CompositeItemWriter.write(chunk)
       |
       +--> databaseWriter.write(chunk)  thành công
       |
       +--> fileWriter.write(chunk)      ném exception
       |
       v
Chunk transaction rollback (nếu exception làm rollback)
```

Nếu database writer tham gia transaction của Step, các thay đổi database chưa commit có thể được rollback. Với file writer, hành vi phụ thuộc implementation và cách file writer quản lý transaction buffer/checkpoint. Một file output hoặc side effect ngoài transaction có thể đã thay đổi và không được database rollback thu hồi.

Khi retry, composite có thể gọi lại các delegate. Database writer có thể ghi lại cùng item; file writer có thể ghi lại hoặc khôi phục vị trí theo state của nó. Những đích không hỗ trợ rollback cần idempotency hoặc cơ chế phục hồi riêng.

Nếu delegate đầu tiên đã gửi HTTP request thành công và delegate thứ hai lỗi, retry có thể gửi lại HTTP request. Dùng idempotency key theo business item hoặc chunk để tránh tạo side effect trùng.

## 10. Transactional buffering của FlatFileItemWriter

`FlatFileItemWriter` hỗ trợ lưu state và có cơ chế transactional buffering để phối hợp ghi file với chunk processing. Điều này giúp xử lý rollback trong các tình huống thông thường của Step tốt hơn so với một writer tự ghi byte trực tiếp vào file mà không có state.

Tuy nhiên, transactional buffering không biến filesystem thành một resource tham gia XA transaction với database. Sự cố process hoặc máy chủ đúng vào thời điểm publish/flush có thể vẫn cần đối soát. Nếu yêu cầu nhất quán cao giữa database và file, cân nhắc ghi file tạm theo chunk hoặc theo Job, chỉ publish file sau khi database transaction/Step hoàn tất, và dùng manifest/trạng thái để quản lý việc publish.

Một mô hình an toàn thường là:

1. Ghi dữ liệu nghiệp vụ vào database trong transaction.
2. Ghi sự kiện cần xuất vào outbox cùng transaction đó.
3. Một Step/Job riêng đọc outbox và tạo file hoặc gửi message.
4. Đánh dấu sự kiện đã publish bằng idempotency key.

Outbox giúp database commit cùng dữ liệu nghiệp vụ và ý định phát đi. Việc gửi file/message vẫn có thể retry, nhưng có thể nhận diện và xử lý duplicate.

## 11. Lifecycle của delegate ItemStream

Một số delegate như `FlatFileItemWriter` triển khai `ItemStreamWriter` vì cần mở file, lưu vị trí và đóng resource. Composite writer phải chuyển tiếp lifecycle để delegate được quản lý đúng.

Trong các phiên bản Spring Batch hiện đại, `CompositeItemWriter` mặc định có thể gọi `open()`, `update()` và `close()` cho các delegate là `ItemStream`. Builder có tùy chọn `ignoreItemStream(...)`; không bật bỏ qua lifecycle nếu delegate cần checkpoint hoặc đóng resource.

Ví dụ:

```java
return new CompositeItemWriterBuilder<Order>()
        .delegates(List.of(databaseWriter, fileWriter))
        .ignoreItemStream(false)
        .build();
```

Nếu dùng phiên bản API cũ hoặc composite tùy chỉnh không chuyển tiếp lifecycle, đăng ký stream delegate trực tiếp trong Step:

```java
return new StepBuilder("exportOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .writer(compositeWriter)
        .stream(fileWriter)
        .build();
```

Chọn một cơ chế lifecycle rõ ràng. Nếu composite đã quản lý delegate, không đăng ký cùng delegate lần thứ hai nếu điều đó khiến `open/update/close` bị gọi lặp. Hãy đối chiếu version Spring Batch của dự án và kiểm thử lifecycle thực tế.

## 12. Checkpoint và restart của nhiều writer

Mỗi delegate có thể có state riêng. Ví dụ file writer lưu vị trí file, còn writer khác lưu metadata của riêng nó. Composite cần đảm bảo state của các delegate được cập nhật tại checkpoint.

Khi restart:

1. Spring Batch mở composite writer.
2. Composite chuyển `open()` đến các delegate stream đã đăng ký.
3. Mỗi delegate khôi phục state từ Step `ExecutionContext`.
4. Khi chunk commit, composite chuyển `update()` đến delegate.
5. Khi Step kết thúc, composite chuyển `close()` để giải phóng resource.

Tên writer và key trong ExecutionContext cần ổn định. Nếu hai delegate dùng cùng key state, chúng có thể ghi đè nhau. Dùng tên riêng cho từng writer và giữ tên đó qua các lần deploy khi Job cũ còn có thể restart.

Checkpoint chỉ mô tả tiến độ được Spring Batch lưu. Nó không tự bảo đảm mọi external side effect đã hoàn tất đúng một lần. Ví dụ, HTTP API đã nhận dữ liệu nhưng process crash trước khi metadata commit; lần restart có thể gửi lại request. Đích ghi cần idempotency hoặc một cơ chế reconciliation.

## 13. Cấu hình ignoreItemStream

`ignoreItemStream` điều khiển việc composite có chuyển tiếp lifecycle ItemStream đến các delegate hay không trong các phiên bản có tùy chọn này.

- `false`: composite quản lý lifecycle cho delegate triển khai `ItemStream`.
- `true`: composite bỏ qua lifecycle delegate; ứng dụng phải có cách đăng ký/quản lý stream khác nếu delegate cần lifecycle.

Thông thường nên giữ `false` khi có delegate stateful. Chỉ bật `true` khi lifecycle được quản lý tường minh ở nơi khác và đã tránh đăng ký trùng.

Không dùng `ignoreItemStream(true)` chỉ để làm Step hết lỗi open/close. Nếu file writer không được mở hoặc không lưu checkpoint, restart có thể ghi sai vị trí hoặc không giải phóng file handle.

## 14. Khi nào cần adapter writer?

Composite yêu cầu các delegate nhận kiểu item tương thích với `T`. Nếu một đích cần schema khác, có thể tạo adapter:

```java
public class OrderAuditWriter implements ItemWriter<Order> {

    private final ItemWriter<OrderAuditRecord> delegate;

    public OrderAuditWriter(ItemWriter<OrderAuditRecord> delegate) {
        this.delegate = delegate;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) throws Exception {
        List<OrderAuditRecord> auditRecords = chunk.getItems().stream()
                .map(order -> new OrderAuditRecord(
                        order.getOrderId(),
                        "ORDER_PROCESSED",
                        order.getAmount()))
                .toList();

        delegate.write(new Chunk<>(auditRecords));
    }
}
```

Composite có thể nhận `OrderAuditWriter` cùng với database writer. Adapter chuyển `Order` thành `OrderAuditRecord` rồi gọi delegate tương ứng.

Nếu adapter chứa một delegate `ItemStream`, adapter cũng cần chuyển tiếp lifecycle hoặc Step cần đăng ký delegate stream tường minh. Không được chỉ chuyển tiếp `write()` mà quên `open/update/close()` khi delegate có state.

## 15. CompositeItemWriter và processor

Processor chạy trước writer và thường là nơi phù hợp để chuẩn hóa item một lần trước khi fan-out. Ví dụ processor bổ sung `processedAt`, tính trạng thái hoặc tạo ID audit; mọi delegate sau đó nhận cùng kết quả.

```java
@Bean
public ItemProcessor<Order, ProcessedOrder> orderProcessor(Clock clock) {
    return order -> new ProcessedOrder(
            order.getOrderId(),
            order.getCustomerName(),
            order.getAmount(),
            Instant.now(clock)
    );
}
```

Khi đó composite có kiểu `CompositeItemWriter<ProcessedOrder>` và các delegate nhận `ProcessedOrder`.

Tránh để mỗi writer tự sửa cùng object đầu vào. Thứ tự gọi delegate không nên làm thay đổi dữ liệu mà delegate tiếp theo nhìn thấy. Nếu một đích cần một dạng dữ liệu khác, adapter tạo representation riêng sẽ rõ ràng hơn.

## 16. Xử lý exception và retry

Khi một delegate ném exception, composite không thể coi chunk đã được ghi thành công đến mọi đích. Exception được đưa về Step để transaction và fault-tolerance policy xử lý.

Ví dụ:

```java
return new StepBuilder("exportOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .writer(compositeWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
```

Chỉ retry lỗi có khả năng phục hồi. Nếu database đã ghi nhưng file writer thất bại, retry có thể gọi database writer lại. Cần bảo đảm database write idempotent, ví dụ dùng unique key/upsert phù hợp hoặc transaction rollback thực sự bao phủ thao tác ghi.

Không nên retry một HTTP writer nếu API không hỗ trợ idempotency và mỗi lần gọi tạo một giao dịch mới. Trong trường hợp đó, retry có thể tạo duplicate dù Step cuối cùng chỉ commit một lần.

Skip cũng cần cẩn trọng. Nếu một delegate không thể ghi item nhưng các delegate khác đã ghi item đó, bỏ qua toàn bộ item có thể tạo ra trạng thái không nhất quán giữa các đích. Hãy xác định rõ skip policy có phù hợp với fan-out hay không và có cơ chế đối soát hay không.

## 17. Idempotency khi ghi đến nhiều đích

Idempotency nghĩa là lặp lại cùng một thao tác không tạo ra kết quả nghiệp vụ trùng hoặc sai. Với composite writer, idempotency đặc biệt quan trọng vì delegate có thể được gọi lại sau rollback/retry/restart.

Các cách thường dùng:

- Dùng business key/unique constraint cho database insert.
- Dùng upsert hoặc ghi theo phiên bản nếu phù hợp nghiệp vụ.
- Gửi idempotency key đến HTTP API.
- Đặt event ID duy nhất trong message và để consumer deduplicate.
- Ghi file vào path theo JobInstance/batch ID, sau đó publish một lần.
- Dùng outbox/inbox để quản lý việc phát và nhận sự kiện.
- Lưu trạng thái publish riêng để có thể retry và reconciliation.

Không dùng số lần gọi `write()` hoặc thứ tự delegate làm định danh nghiệp vụ. Key phải ổn định theo item hoặc event trong suốt các lần retry.

## 18. CompositeItemWriter và nhiều database

Nếu tất cả writer dùng cùng một database transaction và cùng `DataSource` được quản lý bởi transaction manager của Step, các thao tác có thể tham gia cùng transaction. Khi dùng nhiều database độc lập, một `PlatformTransactionManager` thông thường không tự điều phối atomic commit giữa tất cả database.

Các lựa chọn:

- Dùng transaction coordinator/XA nếu yêu cầu atomicity phân tán thực sự và hạ tầng hỗ trợ.
- Dùng outbox để ghi ý định cập nhật database phụ trong transaction chính, sau đó xử lý bất đồng bộ.
- Dùng idempotent upsert và reconciliation nếu chấp nhận eventual consistency.
- Chia thành các Step riêng để mỗi đích có retry/restart độc lập, lưu trạng thái hoàn tất theo batch ID.

CompositeItemWriter phù hợp để fan-out đồng bộ trong một Step khi các delegate có transaction semantics tương thích. Nó không thay thế transaction coordinator.

## 19. Khi nào nên tách thành nhiều Step?

Không phải mọi trường hợp ghi nhiều đích đều nên dùng CompositeItemWriter. Nếu các đích có SLA, retry policy hoặc cách phục hồi khác nhau, tách thành nhiều Step có thể dễ vận hành hơn.

Ví dụ:

```text
read + validate + write database
              |
              v
       commit main data
              |
              v
     export file from database
              |
              v
      publish to external API
```

Ưu điểm của nhiều Step:

- Mỗi đích có checkpoint và retry riêng.
- Lỗi publish không cần đọc lại nguồn ban đầu.
- Có thể chạy lại Step export/publish mà không ghi lại dữ liệu nghiệp vụ.
- Dễ theo dõi trạng thái từng giai đoạn.

Đổi lại, cần lưu batch ID hoặc điều kiện truy vấn để Step sau lấy đúng tập dữ liệu mà Step trước đã commit. Nếu cần ghi mọi đích trong cùng một chunk và chúng có transaction semantics phù hợp, CompositeItemWriter có thể đơn giản hơn.

## 20. Những nhầm lẫn thường gặp

**Cho rằng CompositeItemWriter chia item cho các delegate.** Nó gửi cùng chunk đến tất cả delegate. Muốn định tuyến theo item, dùng classifier writer.

**Cho rằng composite tự tạo transaction chung.** Transaction do Step/transaction manager quản lý; composite chỉ gọi writer.

**Cho rằng mọi đích sẽ rollback cùng nhau.** Chỉ resource tham gia transaction tương ứng mới được rollback. File, HTTP, email và broker có thể giữ side effect.

**Không quan tâm thứ tự delegate.** Writer được gọi theo thứ tự cấu hình. Delegate sau có thể không chạy nếu delegate trước lỗi.

**Để writer trước sửa item cho writer sau.** Các delegate nhận cùng object/chunk; mutation tạo phụ thuộc vào thứ tự và có thể gây lỗi khó đoán.

**Quên lifecycle của delegate ItemStream.** File writer cần open/update/close. Kiểm tra composite có chuyển tiếp lifecycle hay Step đã đăng ký stream riêng.

**Đăng ký delegate stream hai lần.** Lifecycle có thể bị gọi lặp. Chọn một cơ chế quản lý rõ ràng.

**Retry writer không idempotent.** Delegate đã tạo side effect có thể bị gọi lại sau lỗi ở delegate khác. Dùng idempotency key hoặc outbox.

**Dùng composite dù các đích cần vận hành độc lập.** Tách thành Step riêng khi cần checkpoint, retry và phục hồi độc lập.

## 21. Kiểm thử CompositeItemWriter

Nên kiểm thử cả việc fan-out và hành vi khi delegate thất bại:

1. Cấu hình hai delegate và xác nhận cả hai nhận cùng các item trong chunk.
2. Cấu hình ba delegate và xác nhận thứ tự gọi theo danh sách.
3. Làm delegate đầu tiên ném exception; xác nhận các delegate sau không được coi là đã ghi thành công.
4. Làm delegate thứ hai ném exception sau khi delegate đầu đã chạy; xác nhận transaction rollback với resource tham gia transaction.
5. Kiểm tra file writer khôi phục state sau rollback/restart theo cấu hình thực tế.
6. Xác nhận `open()`, `update()` và `close()` được chuyển tiếp đúng số lần cho delegate ItemStream.
7. Kiểm tra delegate stream ẩn trong wrapper được đăng ký tường minh.
8. Chạy retry và xác nhận database/API/file không tạo duplicate.
9. Kiểm tra skip policy không làm các đích lệch dữ liệu.
10. Chạy Job restart sau khi một chunk đã commit và một chunk chưa commit.

Unit test với mock writer giúp xác nhận thứ tự và chunk được truyền. Integration test với database, file system và transaction manager thật mới xác nhận rollback, buffering và restart. Nếu có HTTP hoặc broker, kiểm tra side effect ở hệ thống đích bằng idempotency key.

## 22. Cách lựa chọn chiến lược ghi nhiều đích

Hãy dùng `CompositeItemWriter` khi cùng một item/chunk cần được ghi đồng bộ đến mọi writer delegate. Cấu hình delegate theo thứ tự có chủ đích, bảo đảm tất cả nhận cùng kiểu item và không mutate object đầu vào. Nếu delegate có state, quản lý lifecycle `ItemStream` và checkpoint đúng cách.

Trước khi dùng, xác định transaction boundary của từng đích. Các writer trong cùng transaction database có thể rollback cùng nhau; file và hệ thống ngoài cần cơ chế buffering, idempotency, outbox hoặc reconciliation. Nếu mỗi đích cần retry/restart độc lập, cân nhắc tách thành các Step riêng. Nếu mỗi item chỉ nên đi đến một đích, dùng writer định tuyến.

CompositeItemWriter giúp fan-out dữ liệu trong chunk Step một cách đơn giản. Tính nhất quán thực sự vẫn phụ thuộc transaction manager, lifecycle của delegate, khả năng rollback và cách mỗi đích xử lý việc ghi lặp sau retry hoặc restart.
