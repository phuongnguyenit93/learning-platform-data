# CompositeItemWriter trong Spring Batch

CompositeItemWriter là một writer tổng hợp của Spring Batch. Nó nhận một chunk từ step rồi chuyển cùng chunk đó lần lượt đến nhiều ItemWriter delegate. Cách này phù hợp khi một item sau khi xử lý cần được ghi ra nhiều đích, chẳng hạn lưu dữ liệu nghiệp vụ vào database, xuất file báo cáo và ghi thêm một bản ghi audit.

Điểm quan trọng của CompositeItemWriter là fan-out: mọi delegate đều nhận toàn bộ chunk theo thứ tự đã cấu hình. Nó không tự chia item theo điều kiện, không biến đổi item và không tạo một transaction phân tán giữa các hệ thống. Việc ghi có nguyên tử hay không phụ thuộc transaction manager và khả năng tham gia transaction của từng delegate.

## 1. CompositeItemWriter giải quyết vấn đề gì?

Một chunk-oriented step thường có một ItemWriter. Nhưng trong thực tế, một lần xử lý có thể cần nhiều đầu ra:

- Ghi order đã chuẩn hóa vào bảng nghiệp vụ.
- Ghi bản sao dữ liệu vào bảng audit.
- Xuất một file CSV cho hệ thống downstream.
- Cập nhật bảng thống kê hoặc trạng thái import.
- Gửi dữ liệu đến một hệ thống phụ trợ.

Nếu để processor thực hiện các thao tác ghi này, processor sẽ tạo side effect trước khi step đi đến transaction commit. Điều đó làm retry, rollback và skip khó dự đoán hơn. Một cách tổ chức rõ hơn là để processor tạo item đầu ra, rồi writer chịu trách nhiệm ghi item đó.

CompositeItemWriter cho phép ghép nhiều writer thành một writer duy nhất để đăng ký vào step:

~~~text
Reader
  |
  v
Processor
  |
  v
Chunk<Order>
  |
  v
CompositeItemWriter
  |
  +----> DatabaseWriter
  |
  +----> AuditWriter
  |
  +----> FileWriter
~~~

Mỗi delegate nhận cùng chunk. Nếu chunk chứa 100 order, cả DatabaseWriter, AuditWriter và FileWriter đều được gọi với 100 order đó.

## 2. CompositeItemWriter khác với writer định tuyến

Không nên nhầm composite writer với writer chọn một delegate cho mỗi item:

| Thành phần | Cách hoạt động | Khi nào dùng |
| --- | --- | --- |
| CompositeItemWriter | Gửi toàn bộ chunk đến mọi delegate theo thứ tự | Một item cần được ghi ra nhiều đích |
| ClassifierCompositeItemWriter | Dùng classifier để chọn writer cho từng item | Mỗi item chỉ cần đi đến một đích được xác định bởi loại/điều kiện |
| ItemWriter đơn | Ghi chunk vào một đích | Chỉ có một đầu ra |

Ví dụ, một order cần vừa lưu database vừa xuất file thì CompositeItemWriter phù hợp. Nếu order loại DOMESTIC phải vào writer A còn INTERNATIONAL phải vào writer B, thường dùng ClassifierCompositeItemWriter.

CompositeItemWriter không lọc item. Nếu chunk có các order thuộc nhiều loại khác nhau, tất cả delegate vẫn nhận toàn bộ chunk đó.

## 3. Cách CompositeItemWriter chuyển giao chunk

Về mặt khái niệm, hoạt động của writer tổng hợp tương tự:

~~~java
for (ItemWriter<? super T> delegate : delegates) {
    delegate.write(chunk);
}
~~~

Các delegate được gọi tuần tự theo thứ tự khai báo. Delegate thứ nhất hoàn thành trước khi delegate thứ hai bắt đầu. Nếu một delegate ném exception, lời gọi ghi dừng tại delegate đó và exception được truyền về step; những delegate đứng sau chưa được gọi trong lần gọi đó.

Ví dụ thứ tự:

~~~text
Delegates:
  1. databaseWriter
  2. auditWriter
  3. fileWriter

Lần gọi write(chunk):
  databaseWriter.write(chunk) -> thành công
  auditWriter.write(chunk)    -> thành công
  fileWriter.write(chunk)     -> exception

Kết quả:
  Step nhận exception từ writer
  Transaction chunk được xử lý theo rollback policy
  fileWriter chưa hoàn tất
~~~

Thứ tự delegate vì thế có ý nghĩa. Hãy cấu hình theo thứ tự dễ hiểu và phù hợp với dependencies giữa các đầu ra. Tuy nhiên, thứ tự gọi không tự bảo đảm thứ tự commit giữa các hệ thống độc lập.

## 4. Cấu hình bằng CompositeItemWriterBuilder

Trong Spring Batch 5, có thể tạo writer tổng hợp bằng CompositeItemWriterBuilder:

~~~java
@Bean
CompositeItemWriter<Order> orderCompositeWriter(
        ItemWriter<Order> databaseOrderWriter,
        ItemWriter<Order> auditOrderWriter) {

    return new CompositeItemWriterBuilder<Order>()
        .delegates(List.of(
            databaseOrderWriter,
            auditOrderWriter
        ))
        .build();
}
~~~

Sau đó đăng ký composite writer vào step:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        CompositeItemWriter<Order> orderCompositeWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderCompositeWriter)
        .build();
}
~~~

Step chỉ cần biết một ItemWriter, trong khi bean đó điều phối các writer delegate. Mỗi delegate vẫn có thể được khai báo thành bean riêng để tái sử dụng hoặc kiểm thử độc lập.

Các ví dụ trong bài dùng API chunk-based của Spring Batch 5, trong đó ItemWriter.write nhận Chunk. Dự án Spring Batch 4 cũ có thể dùng chữ ký write(List<? extends T>); cần dùng API tương ứng với phiên bản đang chạy.

## 5. Ví dụ database writer và audit writer

Một delegate có thể ghi dữ liệu order bằng JdbcBatchItemWriter:

~~~java
@Bean
JdbcBatchItemWriter<Order> databaseOrderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
        .dataSource(dataSource)
        .sql("""
            insert into imported_order
                (source_order_id, customer_id, total, status)
            values
                (:sourceOrderId, :customerId, :total, :status)
            """)
        .beanMapped()
        .assertUpdates(true)
        .build();
}
~~~

Delegate thứ hai ghi audit:

~~~java
@Bean
JdbcBatchItemWriter<Order> auditOrderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
        .dataSource(dataSource)
        .sql("""
            insert into order_import_audit
                (source_order_id, event_type, imported_at)
            values
                (:sourceOrderId, 'IMPORTED', :importedAt)
            """)
        .beanMapped()
        .assertUpdates(true)
        .build();
}
~~~

Composite writer:

~~~java
@Bean
CompositeItemWriter<Order> orderCompositeWriter(
        JdbcBatchItemWriter<Order> databaseOrderWriter,
        JdbcBatchItemWriter<Order> auditOrderWriter) {

    return new CompositeItemWriterBuilder<Order>()
        .delegates(List.of(databaseOrderWriter, auditOrderWriter))
        .build();
}
~~~

Hai delegate nhận cùng các order đã được processor tạo ra. Nếu cả hai writer sử dụng cùng datasource và cùng transaction manager của step, các câu lệnh ghi có thể tham gia cùng transaction chunk. Khi một delegate thất bại trước commit, transaction có thể rollback các thay đổi database đã thực hiện trong chunk.

Điều này không có nghĩa mọi database writer trong mọi cấu hình đều tự động nguyên tử. Hãy xác nhận chúng dùng đúng datasource, transaction manager và connection transaction-bound.

## 6. Kết hợp database writer với file writer

Một trường hợp phổ biến là ghi dữ liệu vào database đồng thời tạo file cho hệ thống downstream:

~~~java
@Bean
FlatFileItemWriter<Order> orderFileWriter(
        @Value("#{jobParameters['outputFile']}") Resource outputFile) {

    return new FlatFileItemWriterBuilder<Order>()
        .name("orderFileWriter")
        .resource(outputFile)
        .lineAggregator(order ->
            order.sourceOrderId() + "," +
            order.customerId() + "," +
            order.total()
        )
        .headerCallback(writer ->
            writer.write("sourceOrderId,customerId,total"))
        .shouldDeleteIfExists(true)
        .build();
}
~~~

Ghép file writer với database writer:

~~~java
@Bean
CompositeItemWriter<Order> orderCompositeWriter(
        ItemWriter<Order> databaseOrderWriter,
        ItemWriter<Order> orderFileWriter) {

    return new CompositeItemWriterBuilder<Order>()
        .delegates(List.of(databaseOrderWriter, orderFileWriter))
        .build();
}
~~~

Đây là ví dụ cấu hình; trong production cần xác định rõ file là artifact tạm, file kết quả cuối hay file staging chờ publish. File system thường không tham gia cùng transaction database. FlatFileItemWriter có cơ chế hỗ trợ transaction/lifecycle riêng, nhưng không nên suy ra rằng ghi database và file trên mọi filesystem đều có thể rollback nguyên tử như một transaction database.

Một thiết kế an toàn hơn có thể ghi file staging theo execution, hoàn tất step rồi mới publish/rename file ở bước cuối. Nếu job thất bại, file staging có thể được giữ để restart hoặc được cleanup theo retention policy.

## 7. Delegate nào nhận được item?

Mỗi delegate nhận toàn bộ chunk đầu vào của composite writer. Composite writer không tạo bản sao riêng cho từng delegate và không tự chuyển đổi item.

Ví dụ:

~~~java
List<Order> orders = List.of(orderA, orderB, orderC);
compositeWriter.write(new Chunk<>(orders));
~~~

Kết quả:

- databaseWriter nhận orderA, orderB và orderC.
- auditWriter nhận orderA, orderB và orderC.
- fileWriter nhận orderA, orderB và orderC.

Nếu một delegate chỉ cần một phần item, cần một writer lọc/định tuyến phù hợp hoặc thay đổi pipeline trước khi tới composite writer. Không nên kỳ vọng composite writer tự lọc theo thuộc tính.

Vì các delegate có thể nhận cùng object instance, tránh sửa mutable item trong write. Nếu delegate đầu tiên sửa order rồi delegate thứ hai nhận order đã bị sửa, kết quả sẽ phụ thuộc thứ tự gọi. Hãy dùng immutable item, hoặc tạo representation riêng ở processor/writer chuyên biệt.

## 8. Thứ tự delegate và dependency giữa các đầu ra

Danh sách delegate được cấu hình theo thứ tự thực thi. Ví dụ:

~~~java
.delegates(List.of(
    databaseOrderWriter,
    auditOrderWriter,
    orderFileWriter
))
~~~

Thứ tự này có thể hữu ích nếu audit cần tham chiếu tới dữ liệu đã được ghi trong database hoặc file cần được tạo sau khi dữ liệu được chuẩn hóa. Tuy nhiên, nếu delegate sau cần ID do database sinh ra, hãy nhớ rằng composite writer truyền cùng item hiện tại; nó không tự nạp lại item sau khi delegate đầu tiên ghi.

Nếu cần lấy generated key hoặc kết quả của delegate trước để tạo input cho delegate sau, hãy thực hiện việc đó trong processor/service trước writer, hoặc dùng một writer điều phối tùy chỉnh có hợp đồng rõ ràng. Không phụ thuộc vào việc delegate đầu tiên sửa object để truyền dữ liệu ngầm cho delegate tiếp theo.

Nếu đầu ra thứ hai chỉ được tạo sau khi đầu ra đầu tiên đã commit, hai thao tác không còn là một lần gọi composite writer trong cùng transaction đơn giản. Cân nhắc một step tiếp theo, event/outbox hoặc workflow có trạng thái rõ ràng.

## 9. CompositeItemWriter và transaction của chunk

CompositeItemWriter gọi các delegate trong lúc step đang ghi chunk. Nó không tự mở một transaction mới cho mỗi delegate. Transaction thường được điều khiển bởi step và PlatformTransactionManager được truyền vào cấu hình chunk.

Với các delegate cùng tham gia một transaction:

~~~text
BEGIN CHUNK TRANSACTION
  databaseWriter.write(chunk)
  auditWriter.write(chunk)
  fileWriter.write(chunk)
COMMIT
~~~

Nếu một delegate ném exception trước commit, step xử lý transaction theo rollback policy. Những thao tác đã tham gia transaction có thể được rollback.

Nhưng rollback chỉ tác động tới resource tham gia transaction đó. Ví dụ:

- Hai JDBC writer cùng datasource/transaction manager có thể rollback cùng nhau.
- Gọi HTTP API từ writer không tự rollback được request đã được remote service xử lý.
- Ghi vào filesystem không mặc nhiên được database transaction hoàn tác.
- Ghi vào một datasource khác không tự động atomic với datasource của step.

Vì vậy, composite writer giúp tổ chức nhiều đầu ra, nhưng không phải distributed transaction coordinator.

## 10. Điều gì xảy ra nếu delegate thứ hai thất bại?

Giả sử composite có hai delegate:

1. databaseWriter ghi thành công.
2. externalWriter gửi dữ liệu tới hệ thống bên ngoài nhưng timeout.

Step nhận exception từ externalWriter. Nếu database write còn nằm trong transaction chưa commit, database có thể rollback. Nhưng hệ thống ngoài có thể đã nhận và xử lý request dù client không nhận được response.

Khi chunk được retry hoặc job restart, cùng item có thể được gửi lại. Hệ thống ngoài cần idempotency key hoặc cơ chế deduplication.

Một timeout không chứng minh remote operation chưa xảy ra. Nó có thể đã thành công ở server và chỉ response bị mất. Nếu gửi lại mà không có idempotency, dữ liệu hoặc side effect có thể bị nhân đôi.

## 11. Retry, rollback và idempotency

Writer có thể được gọi nhiều lần cho cùng một chunk do retry, rollback hoặc restart. Composite writer không lưu dấu rằng một delegate đã hoàn tất trước khi delegate khác thất bại.

Ví dụ:

~~~text
Attempt 1:
  databaseWriter -> thành công trong transaction
  externalWriter -> timeout
  transaction rollback

Attempt 2:
  databaseWriter -> được gọi lại
  externalWriter -> được gọi lại
~~~

Nếu database transaction rollback đúng, lần ghi database đầu không còn hiệu lực. Nhưng external operation có thể đã xảy ra và cần chống trùng.

Các biện pháp:

- Dùng business key hoặc operation ID ổn định cho mỗi item/event.
- Thiết kế database writer theo upsert hoặc insert có unique constraint khi phù hợp.
- Yêu cầu API downstream hỗ trợ idempotency key.
- Ghi outbox event trong cùng transaction database với dữ liệu nghiệp vụ.
- Để publisher riêng gửi outbox event và đánh dấu trạng thái sau khi nhận xác nhận.
- Ghi nhận trạng thái gửi để có thể retry có kiểm soát.

Idempotency phải được thiết kế ở từng đích. Việc một writer trong composite chạy trước không bảo đảm delegate tiếp theo chỉ chạy một lần.

## 12. Dùng transactional outbox thay cho gọi remote trực tiếp

Nếu một chunk cần vừa lưu database vừa phát event, pattern transactional outbox thường đáng tin cậy hơn việc gọi HTTP trực tiếp trong composite writer:

~~~text
Chunk transaction
  |
  +--> insert business rows
  |
  +--> insert outbox events
  |
  +--> COMMIT

Separate publisher
  |
  +--> read pending outbox rows
  +--> send event with stable event ID
  +--> mark event published
~~~

Business row và outbox row được ghi trong cùng database transaction. Nếu chunk rollback, cả hai đều rollback. Publisher xử lý gửi event theo cơ chế retry/idempotency riêng.

Có thể đặt database writer và outbox writer trong CompositeItemWriter nếu cả hai dùng cùng transaction manager và cùng transaction-bound datasource. Cũng có thể dùng một writer tùy chỉnh để ghi cả hai theo một hợp đồng nghiệp vụ. Điều cần bảo đảm là cả hai thao tác thực sự tham gia cùng transaction.

Outbox không bảo đảm remote consumer chỉ nhận đúng một lần. Consumer vẫn nên deduplicate theo event ID vì message broker thường cung cấp semantics at-least-once.

## 13. ItemStream lifecycle của các delegate

Một số writer cần lifecycle:

- open(ExecutionContext): mở file, cursor hoặc resource.
- update(ExecutionContext): lưu state/checkpoint.
- close(): flush và giải phóng resource.

CompositeItemWriter triển khai ItemStream và có thể chuyển tiếp lifecycle tới các delegate triển khai ItemStream. Theo mặc định, nó quản lý các delegate stream; tùy chọn ignoreItemStream có thể thay đổi hành vi này.

Ví dụ:

~~~java
CompositeItemWriter<Order> writer =
    new CompositeItemWriterBuilder<Order>()
        .delegates(List.of(databaseWriter, flatFileWriter))
        .build();
~~~

Khi composite writer được đăng ký trong step, Spring Batch gọi lifecycle của composite và composite chuyển tiếp đến delegate stream theo cấu hình. Vì vậy, FlatFileItemWriter có thể mở file trước khi ghi và đóng/flush khi step kết thúc.

Không nên đặt ignoreItemStream(true) nếu các delegate cần open/update/close mà không có nơi nào khác quản lý lifecycle của chúng.

## 14. Khi nào dùng ignoreItemStream?

Builder có tùy chọn ignoreItemStream(boolean). Khi bật, composite writer bỏ qua việc tự chuyển tiếp lifecycle ItemStream tới delegate.

~~~java
CompositeItemWriter<Order> writer =
    new CompositeItemWriterBuilder<Order>()
        .delegates(List.of(databaseWriter, flatFileWriter))
        .ignoreItemStream(true)
        .build();
~~~

Chỉ dùng khi lifecycle của delegate được quản lý riêng và rõ ràng, chẳng hạn delegate stream đã được đăng ký trực tiếp với step bằng .stream(delegate), hoặc delegate không cần lifecycle.

Nếu delegate cần open() để mở file nhưng composite bỏ qua stream và step cũng không đăng ký delegate riêng, writer có thể thất bại khi ghi hoặc không flush/đóng resource đúng cách.

Một cách khác là để wrapper/custom writer triển khai ItemStreamWriter và forward các callback. Khi tự quản lý lifecycle, bảo đảm mỗi delegate chỉ được mở/đóng đúng phạm vi và cleanup xảy ra cả khi step thất bại.

## 15. Đăng ký stream khi delegate nằm trong wrapper

Không phải wrapper nào cũng expose ItemStream. Ví dụ một adapter chỉ implement ItemWriter nhưng giữ FlatFileItemWriter trong field. Spring Batch có thể chỉ nhìn thấy adapter, không thấy stream delegate bên trong.

Nếu composite được cấu hình để bỏ qua stream, hoặc delegate nằm sâu trong wrapper không được composite nhận diện, đăng ký delegate stream với step:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
    .<Order, Order>chunk(100, transactionManager)
    .reader(reader)
    .writer(compositeWriter)
    .stream(flatFileWriter)
    .build();
~~~

Tránh đăng ký cùng một stream theo nhiều đường nếu điều đó khiến lifecycle callback bị gọi trùng. Hãy chọn một owner rõ ràng: composite chuyển tiếp lifecycle, hoặc step đăng ký delegate độc lập, hoặc wrapper tự forward.

## 16. Xử lý lỗi trong delegate và skip policy

Nếu một delegate ném exception, exception được truyền về step. Step áp dụng rollback, retry hoặc skip theo fault-tolerance configuration.

Ví dụ:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
    .<OrderInput, Order>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(orderCompositeWriter)
    .faultTolerant()
    .retry(TransientDataAccessException.class)
    .retryLimit(3)
    .skip(InvalidOrderException.class)
    .skipLimit(10)
    .build();
~~~

Chỉ cấu hình retry cho lỗi có khả năng tự hết, chẳng hạn một số lỗi database/network tạm thời. Không retry lỗi mapping cố định hoặc lỗi validation. Cũng cần xem exception phát sinh từ delegate nào; nếu cùng một exception type được dùng cho cả lỗi tạm thời và lỗi nghiệp vụ, policy có thể áp dụng quá rộng.

Nếu một delegate đã tạo side effect bên ngoài trước khi delegate sau thất bại, skip hoặc retry ở cấp chunk có thể làm side effect đó lặp. Dùng idempotency hoặc tách external operation thành bước riêng có trạng thái bền vững.

## 17. CompositeItemWriter không biến mọi đầu ra thành atomic

Một lỗi thiết kế là giả định rằng gọi nhiều delegate trong một CompositeItemWriter đồng nghĩa mọi đích sẽ commit hoặc rollback cùng nhau. Điều đó chỉ đúng nếu các resource thực sự tham gia cùng transaction coordinator.

Ví dụ:

| Delegate | Resource | Có thể rollback cùng transaction JDBC? |
| --- | --- | --- |
| JdbcBatchItemWriter cùng datasource | Database transaction-bound | Thường có |
| JdbcBatchItemWriter dùng datasource khác | Transaction riêng | Không tự động |
| FlatFileItemWriter | Filesystem | Không mặc nhiên atomic với DB |
| HTTP writer | Remote service | Không |
| Message producer | Broker | Chỉ khi có transaction integration được cấu hình phù hợp; không tự động |

Nếu cần đảm bảo nhiều resource cùng commit, phải chọn distributed transaction phù hợp hoặc thiết kế workflow/outbox/saga. Đừng suy ra guarantee chỉ từ thứ tự delegate.

## 18. Delegate writer nên có cùng kiểu item

CompositeItemWriter<T> nhận một danh sách delegate tương thích với kiểu item T. Các delegate có thể nhận ItemWriter<? super T>, cho phép writer nhận một supertype của item.

Ví dụ:

~~~java
ItemWriter<Auditable> auditWriter = ...;
ItemWriter<Order> orderWriter = ...;

CompositeItemWriter<Order> composite =
    new CompositeItemWriterBuilder<Order>()
        .delegates(List.of(orderWriter, auditWriter))
        .build();
~~~

Order có thể triển khai Auditable, vì vậy audit writer nhận được order. Nhưng nếu một delegate cần một kiểu output khác hẳn, hãy chuyển đổi trước trong processor hoặc viết adapter có kiểu rõ ràng. Không ép kiểu raw để vượt qua compiler; điều đó có thể dẫn đến ClassCastException khi job chạy.

## 19. Dùng adapter khi một đích cần representation khác

Một database writer có thể cần Order, còn file writer cần OrderCsvRow. Không thể đưa hai writer với input type khác nhau vào cùng CompositeItemWriter<Order> nếu file writer chỉ nhận OrderCsvRow.

Có thể tạo adapter:

~~~java
public class OrderCsvWriter implements ItemWriter<Order> {

    private final ItemWriter<OrderCsvRow> delegate;

    public OrderCsvWriter(ItemWriter<OrderCsvRow> delegate) {
        this.delegate = delegate;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) throws Exception {
        List<OrderCsvRow> rows = chunk.getItems().stream()
            .map(OrderCsvRow::from)
            .toList();
        delegate.write(new Chunk<>(rows));
    }
}
~~~

Composite writer vẫn nhận Order; adapter chuyển mỗi order thành representation phù hợp rồi gọi delegate file writer. Nếu delegate bên trong triển khai ItemStream, adapter cũng cần forward lifecycle hoặc đăng ký delegate stream riêng với step.

Một lựa chọn khác là processor tạo một output envelope chứa các representation cần thiết:

~~~java
public record OrderWriteModel(
    Order order,
    OrderCsvRow csvRow
) {}
~~~

Các writer adapter nhận cùng OrderWriteModel rồi chọn phần dữ liệu cần ghi. Cách này giữ việc chuyển đổi ở processor và làm rõ output contract.

## 20. Composite writer và thứ tự side effect

Composite writer gọi delegate tuần tự, nhưng không bảo đảm side effect của delegate trước đã bền vững trước khi delegate sau chạy. Nếu database writer tham gia transaction, lệnh SQL có thể chưa commit khi file writer được gọi.

Ví dụ:

~~~text
BEGIN DB TRANSACTION
  databaseWriter -> INSERT order (chưa commit)
  fileWriter     -> ghi dòng CSV
COMMIT DB
~~~

Nếu commit DB thất bại sau khi file đã được ghi, file có thể chứa order chưa được lưu trong database. Đảo thứ tự delegate không giải quyết bản chất vấn đề; chỉ thay đổi side effect nào có thể xảy ra trước.

Với yêu cầu nhất quán giữa DB và file, cân nhắc:

- Ghi file staging rồi publish sau khi database step thành công.
- Tạo file từ dữ liệu database đã commit trong một step tiếp theo.
- Ghi manifest/trạng thái publish để có thể retry an toàn.
- Định danh artifact theo JobExecution hoặc batch ID.
- Dùng cleanup/reconciliation cho file tạm còn lại sau failure.

## 21. Multi-threaded step và thread safety của delegate

CompositeItemWriter gọi delegate tuần tự trong một lần gọi write(), nhưng điều đó không có nghĩa writer an toàn khi nhiều thread gọi composite đồng thời.

Trong multi-threaded step, partitioning hoặc cấu hình executor, cần xác định có nhiều thread cùng sử dụng một writer instance hay mỗi worker có instance riêng. Nếu dùng chung instance, mọi delegate cũng có thể bị gọi đồng thời từ các thread khác nhau.

Kiểm tra các delegate:

- Có mutable field theo chunk/item không?
- Có ghi vào cùng file hoặc cùng output stream không?
- Có JDBC resource riêng theo invocation hay giữ connection/cursor trong field?
- Có hỗ trợ concurrent writes không?
- Có cần đồng bộ thứ tự ghi không?

CompositeItemWriter không tự tạo lock, clone delegate hoặc serialize các lần gọi đồng thời. Nếu một delegate không thread-safe, dùng partition-specific writer, writer được đồng bộ phù hợp hoặc thay đổi mô hình step. SynchronizedItemStreamWriter có thể giúp tuần tự hóa write của một số writer, nhưng cần xem cả open/update/close và semantics của delegate.

Không dùng một FlatFileItemWriter chung cho nhiều worker ghi song song nếu chưa có thiết kế đảm bảo thứ tự và an toàn. Có thể dùng file riêng theo partition rồi hợp nhất ở step sau.

## 22. Không dùng CompositeItemWriter để thay thế flow nhiều step

Composite writer phù hợp khi các đầu ra thuộc cùng một chunk và cần được gọi trong cùng phase ghi. Nếu một đầu ra cần chạy sau khi đầu ra khác đã hoàn tất/commit, nên dùng nhiều step trong job flow.

Ví dụ:

~~~text
ImportStep
  Reader -> Processor -> DatabaseWriter
       |
       v
ExportStep
  DatabaseReader -> FileWriter
       |
       v
PublishStep
  Publish artifact / notify downstream
~~~

Tách step cho phép:

- Mỗi đầu ra có transaction boundary rõ ràng.
- Restart từng bước độc lập.
- Retry hoặc skip theo chính sách riêng.
- Có thể chạy export lại mà không import lại nguồn.
- Theo dõi status và metrics riêng.

Đổi lại, cần quản lý dependency giữa step và dữ liệu đã commit. Đừng ghép tất cả writer vào một composite chỉ vì muốn job có ít step hơn.

## 23. Kiểm thử thứ tự và số lần gọi delegate

Unit test có thể dùng mock writer để xác nhận tất cả delegate nhận chunk và được gọi theo thứ tự:

~~~java
@Test
void writesChunkToEveryDelegateInConfiguredOrder() throws Exception {
    ItemWriter<Order> first = mock(ItemWriter.class);
    ItemWriter<Order> second = mock(ItemWriter.class);

    CompositeItemWriter<Order> writer =
        new CompositeItemWriterBuilder<Order>()
            .delegates(List.of(first, second))
            .build();

    Chunk<Order> chunk = new Chunk<>(List.of(orderA, orderB));
    writer.write(chunk);

    InOrder inOrder = inOrder(first, second);
    inOrder.verify(first).write(chunk);
    inOrder.verify(second).write(chunk);
}
~~~

Test này kiểm tra contract fan-out. Có thể bổ sung:

- Delegate đầu tiên được gọi trước delegate thứ hai.
- Mọi delegate nhận đúng item trong chunk.
- Delegate sau không được gọi nếu delegate trước ném exception.
- Exception được truyền về caller.
- Danh sách delegate rỗng hoặc cấu hình sai được phát hiện lúc khởi tạo theo behavior builder/version đang dùng.

Không nên chỉ test composite writer bằng mock rồi kết luận transaction/rollback hoạt động. Transaction cần integration test với resource thực.

## 24. Kiểm thử rollback khi delegate thất bại

Với các delegate database dùng cùng datasource và transaction manager, integration test nên xác nhận rollback:

1. Delegate A ghi vào bảng thứ nhất.
2. Delegate B cố ý ném exception.
3. Step kết thúc FAILED hoặc retry theo cấu hình.
4. Kiểm tra bảng thứ nhất không có dữ liệu của chunk chưa commit.

Ví dụ writer thất bại:

~~~java
public class FailingAuditWriter implements ItemWriter<Order> {

    @Override
    public void write(Chunk<? extends Order> chunk) {
        throw new IllegalStateException("Audit write failed");
    }
}
~~~

Nếu database writer trước đó tham gia đúng transaction của step, insert của chunk có thể rollback. Test cần dùng transaction manager và datasource thật như production. Mock writer không chứng minh transaction participation.

Nếu hai delegate dùng hai datasource khác nhau, viết test cho failure window để xác định dữ liệu nào có thể đã commit. Đừng mong rollback tự động khi không có transaction coordinator chung.

## 25. Kiểm thử ItemStream lifecycle của delegate

Với file writer hoặc writer tự quản lý resource, cần xác nhận open, update và close được gọi qua composite:

~~~java
class TrackingStreamWriter implements ItemWriter<Order>, ItemStream {

    private int opens;
    private int updates;
    private int closes;

    @Override
    public void open(ExecutionContext context) {
        opens++;
    }

    @Override
    public void update(ExecutionContext context) {
        updates++;
    }

    @Override
    public void close() {
        closes++;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) {
        // Test writer chỉ ghi nhận lifecycle.
    }
}
~~~

Sau khi dựng composite với delegate trên, test gọi lifecycle của composite hoặc chạy một step thật rồi kiểm tra các callback đã được chuyển tiếp. Test unit có thể xác nhận việc ủy quyền; integration test xác nhận lifecycle diễn ra đúng thời điểm trong step.

Nếu composite được cấu hình ignoreItemStream(true), test phải xác nhận delegate stream đã được đăng ký trực tiếp hoặc có owner khác quản lý. Không để writer chạy được trong test unit nhưng thất bại khi step mở file trong production.

## 26. Kiểm thử retry và side effect lặp

Nếu delegate đầu tiên ghi database còn delegate thứ hai gửi HTTP/message, hãy test trường hợp delegate thứ hai timeout sau khi remote đã nhận request. Mock server có thể nhận request nhưng không trả response; retry sau đó sẽ gửi request lần nữa.

Test cần xác nhận:

- Idempotency key giữ nguyên qua các lần retry.
- Remote service chỉ áp dụng một lần cho cùng key.
- Database transaction rollback/commit đúng theo cấu hình.
- Job restart không tạo operation ID mới cho cùng item operation.
- Log và audit có thể truy vết số lần thử và kết quả cuối.

Không chỉ assert số lần write() của composite. Điều quan trọng là side effect ở từng hệ thống có kết quả đúng sau retry.

## 27. Skip và write skip trong composite

Nếu exception từ một delegate thuộc skip policy, Spring Batch có thể xử lý nó như lỗi write và áp dụng skip theo cấu hình. Tuy nhiên, khi nhiều delegate đã được gọi trước lúc exception xảy ra, các delegate trước có thể đã tạo side effect.

Ví dụ:

~~~text
databaseWriter -> hoàn tất write
auditWriter    -> ném InvalidOrderException
fileWriter     -> chưa được gọi
Step           -> xử lý write skip theo policy
~~~

Nếu transaction rollback chunk, database write có thể được hoàn tác. Nhưng nếu audit writer ghi sang resource không transactional, dữ liệu có thể vẫn tồn tại. Item bị skip không tự xóa side effect đã phát sinh ở hệ thống ngoài.

Với composite nhiều đích, skip policy cần được thiết kế cùng semantics của từng delegate. Nếu một lỗi ở đích phụ không được phép làm mất dữ liệu ở đích chính, cân nhắc tách đích phụ thành step/outbox riêng thay vì skip toàn item.

## 28. Giám sát và vận hành composite writer

Khi job chạy production, log và metric nên cho biết delegate nào đang chậm hoặc lỗi. Có thể bọc writer bằng decorator đo thời gian:

~~~java
public class TimedOrderWriter implements ItemWriter<Order> {

    private final String name;
    private final ItemWriter<Order> delegate;
    private final MeterRegistry meterRegistry;

    public TimedOrderWriter(
            String name,
            ItemWriter<Order> delegate,
            MeterRegistry meterRegistry) {
        this.name = name;
        this.delegate = delegate;
        this.meterRegistry = meterRegistry;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) throws Exception {
        Timer.Sample sample = Timer.start(meterRegistry);
        try {
            delegate.write(chunk);
        } finally {
            sample.stop(meterRegistry.timer(
                "batch.writer.duration",
                "writer", name
            ));
        }
    }
}
~~~

Decorator trên đo thời gian gọi writer, kể cả khi exception xảy ra. Nếu delegate triển khai ItemStream, decorator cũng cần forward lifecycle để không làm mất open/update/close.

Metrics có thể bao gồm:

- Số chunk và item đã ghi theo delegate.
- Thời gian write của từng delegate.
- Số lần exception/retry.
- Số item skip ở write phase.
- Số file staging được tạo/publish.
- Số outbox event pending/failed.

Không log toàn bộ payload nhạy cảm chỉ để debug writer. Dùng job execution ID, step execution ID và business key phù hợp để truy vết.

## 29. Các lỗi thường gặp khi dùng CompositeItemWriter

**Tưởng mỗi delegate nhận một phần chunk:** mọi delegate nhận toàn bộ chunk. Dùng classifier writer nếu cần định tuyến.

**Cho rằng thứ tự delegate đồng nghĩa thứ tự commit:** thứ tự gọi không bảo đảm resource độc lập commit cùng nhau. Xác định transaction participation.

**Cho rằng composite tự tạo distributed transaction:** nó chỉ điều phối lời gọi writer. Dùng transaction coordinator/outbox/workflow nếu cần consistency nhiều resource.

**Gọi HTTP trực tiếp rồi retry:** remote side effect có thể đã thành công dù client timeout. Dùng idempotency key hoặc outbox.

**Delegate sau cần generated ID từ delegate trước:** composite không tự nạp lại item đã cập nhật từ database. Tạo dữ liệu cần thiết trước writer hoặc dùng coordinator có hợp đồng rõ.

**Quên ItemStream lifecycle:** delegate file/cursor không được open/update/close. Để composite forward stream hoặc đăng ký delegate riêng.

**Bật ignoreItemStream không có owner khác:** resource có thể không được mở/đóng. Chỉ bỏ qua lifecycle khi đã quản lý riêng.

**Dùng delegate không cùng kiểu item:** ép kiểu raw có thể gây lỗi runtime. Dùng adapter hoặc output model chung.

**Giả định thread-safe:** composite gọi delegate tuần tự trong một lần write, nhưng nhiều thread có thể gọi cùng instance đồng thời. Kiểm tra concurrency của từng delegate.

**Dùng composite thay cho flow nhiều step:** các đầu ra có dependency/commit riêng thường cần step riêng để restart và vận hành rõ ràng.

**Chỉ test mock invocation:** test mock không chứng minh rollback, stream lifecycle hoặc idempotency. Bổ sung integration test cho resource thực.

## 30. Quy trình thiết kế CompositeItemWriter trong production

Trước tiên, xác định các đầu ra có thực sự cần nhận cùng một item/chunk hay không. Nếu tất cả đích cần cùng dữ liệu, dùng CompositeItemWriter; nếu item cần được phân tuyến theo loại, dùng classifier writer. Giữ danh sách delegate theo thứ tự rõ ràng và bảo đảm kiểu item tương thích.

Tiếp theo, cấu hình từng delegate độc lập rồi ghép bằng CompositeItemWriterBuilder. Xác định transaction manager, datasource và resource nào tham gia transaction chunk. Với delegate triển khai ItemStream, bảo đảm lifecycle được composite chuyển tiếp hoặc được step quản lý riêng. Đừng bật ignoreItemStream khi chưa có owner thay thế.

Cuối cùng, thiết kế retry/skip dựa trên side effect thật của từng đích. Dùng idempotency key cho thao tác có thể được gọi lại, outbox cho event cần phát sau commit, và step riêng cho đầu ra có transaction/lifecycle khác biệt. Test thứ tự delegate, rollback, stream lifecycle, retry, restart và concurrency bằng cả unit test lẫn integration test.

CompositeItemWriter là cách đơn giản để gửi cùng một chunk tới nhiều writer theo thứ tự cấu hình. Nó giúp step có một điểm ghi thống nhất và tái sử dụng các delegate chuyên trách. Nhưng transaction, restart, idempotency, thread safety và resource lifecycle vẫn do cấu hình cùng từng delegate quyết định. Khi hiểu rõ fan-out semantics và giới hạn transaction, composite writer có thể hỗ trợ nhiều đầu ra mà vẫn giữ được khả năng vận hành và phục hồi của batch job.
