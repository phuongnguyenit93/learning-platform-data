# Writer ghi file, database hoặc message

Trong Spring Batch, `ItemWriter<T>` chịu trách nhiệm ghi các item đã được đọc và xử lý tới đích đầu ra. Trong chunk-oriented step, writer nhận một nhóm item của chunk trong một lần gọi `write`, nhờ đó có thể ghi theo lô thay vì mở một thao tác riêng cho từng item.

Đích ghi có thể là file, cơ sở dữ liệu hoặc hệ thống messaging như Kafka hay JMS. Mỗi loại đích có đặc điểm khác nhau về transaction, restart, hiệu năng và cách xử lý lỗi. Spring Batch cung cấp nhiều writer dựng sẵn cho các trường hợp phổ biến; khi cần tích hợp hệ thống riêng, có thể triển khai `ItemWriter` tùy chỉnh.

## Hợp đồng của ItemWriter

Trong Spring Batch 5, `ItemWriter<T>` nhận `Chunk` chứa các item output:

```java
public interface ItemWriter<T> {
    void write(Chunk<? extends T> chunk) throws Exception;
}
```

Ở các phiên bản Spring Batch cũ hơn, chữ ký `write` có thể nhận `List<? extends T>`. Hãy dùng đúng API của phiên bản framework mà dự án đang sử dụng.

Writer được gọi sau khi reader đã cung cấp các item và processor đã chuyển đổi chúng. Các item mà processor filter bằng cách trả về `null` không có trong chunk chuyển tới writer.

```text
ItemReader
    |
    v
  Input items
    |
    v
ItemProcessor
    |
    v
 Output items
    |
    v
ItemWriter.write(chunk)
    |
    +----> File
    +----> Database
    +----> Message broker
```

Một số nguyên tắc của writer:

- Nhận toàn bộ output của chunk hiện tại và ghi chúng theo thứ tự hoặc quy tắc được thiết kế.
- Ném exception nếu không thể hoàn tất thao tác ghi; Spring Batch có thể rollback, retry, skip hoặc đánh dấu step thất bại theo cấu hình.
- Không tự quyết định kết thúc input; việc đó thuộc `ItemReader`.
- Không nên phụ thuộc vào định dạng nguồn; writer chỉ nên hiểu mô hình output đã được chuẩn hóa.
- Cần có chiến lược transaction và idempotency phù hợp với đích ghi.

## Chọn writer theo loại đích

| Đích đầu ra | Writer thường dùng | Đặc điểm chính |
| --- | --- | --- |
| File văn bản, CSV hoặc fixed-width | `FlatFileItemWriter` | Ghi tuần tự, hỗ trợ header/footer và lưu state để restart |
| Database quan hệ qua JDBC | `JdbcBatchItemWriter` | Thực thi batch SQL theo chunk và tham gia transaction JDBC của step |
| Database qua JPA | `JpaItemWriter` | Ghi entity qua `EntityManager` và transaction manager JPA |
| Message broker | Writer tùy chỉnh dùng Kafka/JMS client hoặc adapter tích hợp | Cần xác định xác nhận gửi, transaction và xử lý gửi lặp |
| Nhiều đích | `CompositeItemWriter` hoặc writer định tuyến | Một chunk được chuyển tới nhiều writer hoặc writer phù hợp theo điều kiện |

Không có một writer phù hợp cho mọi đích. Hãy chọn dựa trên kiểu dữ liệu đầu ra, transaction mà đích hỗ trợ, yêu cầu restart và cách hệ thống tiêu thụ kết quả.

## Ghi file với FlatFileItemWriter

`FlatFileItemWriter<T>` là writer phổ biến để xuất dữ liệu thành file văn bản. Nó có thể ghi mỗi item thành một dòng thông qua `LineAggregator`, đồng thời hỗ trợ các tùy chọn như encoding, header, footer và lưu trạng thái để restart.

### Ví dụ ghi CSV

Giả sử processor tạo ra các đối tượng `Order`:

```java
public record Order(
        String orderId,
        String customerId,
        BigDecimal amount,
        String status) {
}
```

Có thể cấu hình writer bằng builder:

```java
@Bean
FlatFileItemWriter<Order> orderFileWriter(
        @Value("${batch.output.orders}") Resource outputFile) {

    return new FlatFileItemWriterBuilder<Order>()
            .name("orderFileWriter")
            .resource(outputFile)
            .encoding("UTF-8")
            .delimited()
            .delimiter(",")
            .names("orderId", "customerId", "amount", "status")
            .headerCallback(writer ->
                    writer.write("orderId,customerId,amount,status"))
            .build();
}
```

`delimited()` tạo cách ánh xạ các property thành các trường được phân cách. `names(...)` chỉ định những property cần xuất. Với dữ liệu CSV thực tế có thể chứa dấu phẩy, dấu nháy hoặc ký tự xuống dòng, cần cấu hình escaping/quoting phù hợp hoặc cung cấp `LineAggregator` chuyên dụng; việc chỉ nối các trường bằng dấu phẩy không tự bảo đảm file tuân thủ mọi quy tắc CSV.

Kết quả minh họa:

```csv
orderId,customerId,amount,status
O-1001,C-01,125.50,NEW
O-1003,C-03,240.00,NEW
```

### LineAggregator

`LineAggregator<T>` chuyển một item thành một dòng `String`. Với định dạng đơn giản, builder có thể tạo aggregator từ danh sách property. Với định dạng phức tạp, có thể tự triển khai aggregator để kiểm soát cách định dạng ngày, số thập phân, dấu phân cách, padding hoặc escaping.

```java
LineAggregator<Order> orderLineAggregator = order -> String.join(
        ",",
        csvEscape(order.orderId()),
        csvEscape(order.customerId()),
        order.amount().toPlainString(),
        csvEscape(order.status()));
```

Trong ví dụ, `csvEscape` là hàm do ứng dụng định nghĩa để quote và escape đúng quy tắc CSV. Nếu dữ liệu có thể chứa dấu phân cách hoặc dấu nháy, không nên dùng `String.join` đơn giản mà không xử lý escaping.

### Header và footer

`headerCallback` có thể ghi tên cột hoặc thông tin mô tả file. `footerCallback` có thể ghi tổng số bản ghi hoặc checksum nếu ứng dụng đã tính toán được giá trị cần thiết.

```java
new FlatFileItemWriterBuilder<Order>()
        .name("orderFileWriter")
        .resource(outputFile)
        .lineAggregator(orderLineAggregator)
        .headerCallback(writer -> writer.write("orderId,customerId,amount,status"))
        .footerCallback(writer -> writer.write("# end-of-file"))
        .build();
```

Header và footer phải tuân theo định dạng mà hệ thống tiêu thụ mong đợi. Ví dụ, nếu file là CSV thuần để nạp vào một hệ thống khác, một dòng footer tùy ý có thể bị hiểu nhầm là dữ liệu; chỉ thêm footer khi giao ước file cho phép.

### Restart và ghi file

`FlatFileItemWriter` có thể lưu trạng thái ghi vào `ExecutionContext` để hỗ trợ restart. Cần đặt `.name(...)` ổn định và bật state management theo cấu hình phù hợp. Khi restart, writer dựa vào metadata để tiếp tục file đã tạo thay vì coi đó là một lần xuất hoàn toàn mới.

Một số lưu ý:

- Dùng đường dẫn output ổn định cho cùng một logical job khi cần restart.
- Không xóa file cũ ở mỗi lần mở nếu mục tiêu là tiếp tục một execution bị lỗi.
- Nếu mỗi lần chạy nghiệp vụ phải tạo file mới, đưa định danh đầu ra vào đường dẫn hoặc cấu hình resource theo `JobParameters`.
- Đảm bảo thư mục tồn tại và tiến trình có quyền ghi.
- Chọn encoding rõ ràng, thường là UTF-8, và quy định newline/format với hệ thống nhận.
- Không để consumer đọc file cuối cùng khi job vẫn đang ghi dở.

Một mẫu triển khai an toàn là ghi vào file tạm theo execution, chỉ công bố hoặc đổi tên sang tên file chính thức sau khi job hoàn thành thành công. Việc đổi tên cần được thiết kế theo filesystem/object storage thực tế; không phải mọi hệ thống lưu trữ đều hỗ trợ thao tác rename nguyên tử.

## Ghi database với JdbcBatchItemWriter

`JdbcBatchItemWriter<T>` phù hợp khi output cần được ghi vào database quan hệ bằng JDBC. Writer nhận một chunk và sử dụng batch update để giảm số round trip tới database.

### Ví dụ insert theo batch

```java
@Bean
JdbcBatchItemWriter<Order> orderDatabaseWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("""
                    INSERT INTO orders
                        (order_id, customer_id, amount, status)
                    VALUES
                        (:orderId, :customerId, :amount, :status)
                    """)
            .beanMapped()
            .build();
}
```

`beanMapped()` ánh xạ named parameter trong SQL tới property tương ứng của object. Có thể dùng `columnMapped()` khi item là `Map`, hoặc cung cấp `ItemSqlParameterSourceProvider` tùy chỉnh khi cần cách ánh xạ khác.

Với chunk 100 item, writer có thể gửi một batch gồm các câu lệnh tương ứng cho 100 output. Kích thước batch thực tế và hiệu năng còn phụ thuộc driver JDBC, database, SQL và cấu hình transaction.

### Update hoặc upsert

Nếu job đồng bộ dữ liệu đã tồn tại, có thể dùng câu `UPDATE`, `MERGE` hoặc cú pháp upsert theo database. Ví dụ với PostgreSQL:

```sql
INSERT INTO orders (order_id, customer_id, amount, status)
VALUES (:orderId, :customerId, :amount, :status)
ON CONFLICT (order_id)
DO UPDATE SET
    customer_id = EXCLUDED.customer_id,
    amount = EXCLUDED.amount,
    status = EXCLUDED.status;
```

Upsert giúp thao tác ghi có thể được thực hiện lại với cùng business key mà không tạo thêm bản ghi trùng. Tuy nhiên, cần xác định rõ khi nào dữ liệu được phép cập nhật, có ghi đè trạng thái mới hơn hay không và cách xử lý xung đột theo nghiệp vụ.

### Transaction của database writer

Trong chunk-oriented step, writer thường tham gia transaction do `PlatformTransactionManager` của step quản lý. Nếu writer và `JobRepository` cùng sử dụng một database resource cùng transaction manager phù hợp, dữ liệu nghiệp vụ và checkpoint có thể commit hoặc rollback cùng nhau.

Nếu writer dùng một datasource hoặc transaction manager khác, không có bảo đảm atomic commit mặc định giữa dữ liệu nghiệp vụ và batch metadata. Khi đó cần thiết kế idempotency, unique key, upsert hoặc quy trình đối soát để xử lý tình huống một phía commit còn phía kia thất bại.

Không nên tự mở transaction mới trong writer nếu không có yêu cầu cụ thể. Một transaction `REQUIRES_NEW` có thể commit dữ liệu writer độc lập với chunk; nếu chunk rollback, dữ liệu đã commit vẫn tồn tại và có thể được ghi lại khi restart.

### JpaItemWriter

Nếu ứng dụng làm việc với entity qua JPA, có thể dùng `JpaItemWriter` để ghi chunk entity thông qua `EntityManager`. Cần cấu hình `EntityManagerFactory` và transaction manager JPA phù hợp với step. Việc chọn `persist` hay `merge` phụ thuộc entity mới hay đã tồn tại và semantics mà ứng dụng mong muốn.

Với chunk lớn, cần cân nhắc persistence context và flush/clear để tránh giữ quá nhiều entity trong bộ nhớ. Hãy đo hiệu năng và xác định rõ hành vi khi một entity vi phạm constraint hoặc lỗi trong lúc flush.

## Ghi message tới Kafka, JMS hoặc broker khác

Một số job không ghi trực tiếp vào database hoặc file mà phát sự kiện để hệ thống khác xử lý. Ví dụ, sau khi chuẩn hóa đơn hàng, batch job phát `OrderImported` tới Kafka hoặc gửi message tới JMS queue.

Spring Batch không áp đặt một message broker cụ thể. Có thể triển khai `ItemWriter` tùy chỉnh dùng client như `KafkaTemplate`, `JmsTemplate` hoặc adapter messaging của ứng dụng.

### Ví dụ writer phát message

Định nghĩa một abstraction nhỏ để tách writer khỏi thư viện broker:

```java
public interface OrderEventPublisher {
    void publish(OrderImported event) throws Exception;
}

public class OrderMessageWriter implements ItemWriter<OrderImported> {

    private final OrderEventPublisher publisher;

    public OrderMessageWriter(OrderEventPublisher publisher) {
        this.publisher = publisher;
    }

    @Override
    public void write(Chunk<? extends OrderImported> chunk) throws Exception {
        for (OrderImported event : chunk) {
            publisher.publish(event);
        }
    }
}
```

Adapter `OrderEventPublisher` sẽ sử dụng Kafka, JMS hoặc broker khác theo cấu hình ứng dụng. Việc tách adapter giúp kiểm thử writer bằng fake publisher và thay broker mà không sửa logic chunk step.

### Gửi message đồng bộ hay bất đồng bộ?

Nhiều client messaging cung cấp API gửi bất đồng bộ. Nếu writer trả về ngay sau khi tạo future mà không chờ kết quả, step có thể commit trước khi broker xác nhận message. Lỗi gửi xảy ra sau đó có thể không được phản ánh trong transaction chunk.

Khi yêu cầu job chỉ tiếp tục sau khi broker xác nhận, writer cần chờ kết quả gửi hoặc sử dụng cơ chế transaction/acknowledgement phù hợp. Cách chờ future và API cụ thể khác nhau giữa các phiên bản client. Tránh nuốt exception hoặc chỉ ghi log rồi coi chunk đã thành công.

Gửi message đồng bộ có thể làm giảm throughput. Có thể tối ưu bằng batch send, producer async có quản lý completion, hoặc cấu hình transaction broker phù hợp, nhưng cần giữ một quy tắc rõ ràng: khi nào writer được phép trả về thành công và khi nào chunk được phép commit.

### Transaction với message broker

Transaction của database không tự động rollback message đã gửi tới broker. Nếu writer publish message rồi một thao tác khác trong chunk thất bại, message có thể vẫn tồn tại dù database rollback.

Một số broker hỗ trợ transaction riêng. Một số nền tảng có thể phối hợp transaction database và messaging thông qua distributed transaction/XA, nhưng cách triển khai có chi phí và giới hạn vận hành. Không nên giả định chỉ vì producer được cấu hình transaction là transaction đó đã nguyên tử với transaction JDBC của Spring Batch.

Các lựa chọn thiết kế thường gặp:

- **Transactional outbox:** ghi sự kiện vào bảng outbox cùng transaction với dữ liệu nghiệp vụ; một publisher riêng đọc outbox và gửi tới broker. Có thể đánh dấu đã gửi sau khi broker xác nhận, đồng thời dùng event ID để chống trùng.
- **Idempotent consumer:** chấp nhận message có thể được gửi lại và để consumer loại trùng bằng event ID hoặc business key.
- **Broker transaction:** dùng transaction của broker khi yêu cầu và cấu hình thực sự chỉ liên quan tới resource đó.
- **Distributed transaction:** cân nhắc XA khi yêu cầu atomicity qua nhiều resource đủ mạnh để chấp nhận độ phức tạp vận hành.

Với nhiều hệ thống nghiệp vụ, outbox kết hợp consumer idempotent là cách dễ phục hồi hơn so với cố gắng giả định database và broker luôn commit cùng nhau.

### Thiết kế message để retry an toàn

Một event nên có định danh ổn định, loại event, thời điểm phát sinh, business key và payload cần thiết. Ví dụ:

```json
{
  "eventId": "order-import:O-1001:v1",
  "eventType": "OrderImported",
  "orderId": "O-1001",
  "businessDate": "2026-11-15",
  "amount": 125.50
}
```

`eventId` ổn định giúp consumer nhận biết message lặp. Không nên tạo UUID mới cho cùng một sự kiện mỗi lần retry nếu consumer cần phát hiện duplicate; ID phải gắn với sự kiện nghiệp vụ hoặc lần xử lý logic phù hợp.

Partition key, message key, ordering và delivery guarantee cần được xác định theo broker. Ví dụ, nếu các event của cùng một order phải giữ thứ tự, có thể dùng `orderId` làm key trong hệ thống partitioned log hỗ trợ key-based partitioning.

## Kết hợp nhiều writer

Có trường hợp một chunk cần được ghi tới nhiều đích, ví dụ vừa lưu đơn hàng vào database vừa xuất file báo cáo. Spring Batch cung cấp `CompositeItemWriter` để gọi nhiều writer delegate trên cùng chunk.

```java
@Bean
CompositeItemWriter<Order> compositeOrderWriter(
        JdbcBatchItemWriter<Order> orderDatabaseWriter,
        FlatFileItemWriter<Order> orderFileWriter) throws Exception {

    return new CompositeItemWriterBuilder<Order>()
            .delegates(orderDatabaseWriter, orderFileWriter)
            .build();
}
```

Composite writer gọi các delegate theo thứ tự được cấu hình. Nếu một delegate thất bại, exception được đưa về step và transaction xử lý theo cấu hình. Tuy nhiên, điều này không tự làm cho nhiều loại resource có atomic transaction chung. Database có thể rollback trong khi file đã ghi, hoặc ngược lại, tùy cơ chế transaction và resource.

Khi một chunk cần nhiều đích:

- Xác định thứ tự ghi và hành vi khi một delegate lỗi.
- Xác định các writer có dùng chung transaction resource hay không.
- Thiết kế cách khôi phục file/message nếu database đã commit hoặc ngược lại.
- Bảo đảm mỗi delegate an toàn khi được gọi lại sau retry/restart.
- Cân nhắc outbox hoặc tách thành step riêng nếu cần điều phối giữa các hệ thống.

Nếu cần chọn một writer dựa trên từng item, có thể dùng `ClassifierCompositeItemWriter` hoặc tự triển khai writer định tuyến. Khi định tuyến, cần hiểu rằng một item chỉ được gửi tới delegate được chọn; số lượng ghi ở từng đích nên được theo dõi riêng nếu cần báo cáo.

## Transaction, rollback và restart của writer

Writer là nơi thường tạo side effect, vì vậy cần xem xét transaction kỹ lưỡng.

### Database writer

Nếu ghi vào cùng database resource với transaction manager của step, thao tác ghi thường rollback khi chunk thất bại. Khi restart, item của chunk chưa commit có thể được xử lý lại và writer được gọi lại.

### File writer

`FlatFileItemWriter` hỗ trợ lưu state và phối hợp với transaction của step để khôi phục vị trí ghi theo cơ chế của framework. Tuy nhiên file không phải một database transaction tổng quát. Consumer bên ngoài vẫn có thể nhìn thấy file đang được tạo nếu đọc trực tiếp đường dẫn đó. Nên dùng file tạm và chỉ công bố file sau khi job hoàn tất nếu yêu cầu không cho phép đọc output dở dang.

### Message writer

Message đã được broker nhận có thể không bị thu hồi khi chunk rollback. Retry có thể gửi lại message. Hãy dùng event ID ổn định, idempotent consumer hoặc outbox để xử lý delivery lặp và khôi phục trạng thái.

### Writer tự triển khai có state

Nếu writer giữ trạng thái nội bộ như số dòng, checksum hoặc vị trí ghi, có thể cần triển khai `ItemStream` để lưu/khôi phục state qua `ExecutionContext`. Tên stream phải ổn định và state phải đủ để tiếp tục chính xác sau restart. Không lưu toàn bộ payload lớn trong execution context; chỉ lưu checkpoint hoặc metadata nhỏ.

## Lỗi thường gặp khi ghi output

### Không có quyền ghi file hoặc thư mục không tồn tại

Kiểm tra resource path, quyền truy cập của process, dung lượng đĩa và việc tạo thư mục trước khi chạy. Với job chạy trong container, cần xác định volume được mount và đường dẫn có tồn tại ở node thực thi.

### File bị ghi đè khi restart

Kiểm tra tên writer, `ExecutionContext`, cấu hình append/delete và resource path. Nếu muốn restart cùng logical job, giữ ổn định resource và state. Nếu muốn tạo file mới, dùng định danh lần xuất mới có chủ đích.

### Lỗi constraint hoặc duplicate key trong database

Kiểm tra business key, dữ liệu đầu vào, chính sách insert/update và hành vi khi writer được gọi lại. Dùng upsert hoặc unique key theo quy tắc nghiệp vụ nếu retry/restart có thể gửi cùng item nhiều lần.

### Message được gửi nhưng step vẫn thất bại

Broker có thể đã nhận message trước khi một thao tác sau đó trong chunk lỗi. Kiểm tra transaction broker, transaction manager, acknowledgement và event ID. Thiết kế consumer idempotent để xử lý trường hợp message được gửi lại.

### Writer bất đồng bộ nhưng không chờ lỗi

Nếu writer trả về trước khi thao tác gửi hoàn tất, step có thể commit trong khi tác vụ gửi vẫn đang thất bại. Quản lý future/acknowledgement và chỉ trả về thành công khi điều kiện hoàn tất mà nghiệp vụ yêu cầu đã được đáp ứng.

### Chunk quá lớn hoặc writer quá chậm

Chunk lớn có thể tạo batch SQL lớn, giữ transaction lâu hoặc tạo nhiều message trong một lần. Đo thời gian đọc/ghi, throughput, memory, connection pool và broker latency; điều chỉnh commit interval và batch size phù hợp.

### Nuốt exception trong writer

Nếu writer chỉ log lỗi rồi tiếp tục, Spring Batch có thể đánh dấu chunk thành công dù dữ liệu không được ghi đầy đủ. Hãy ném exception khi không đạt điều kiện thành công và để step áp dụng transaction/retry/skip policy đã thiết kế.

## Kiểm thử writer

Writer cần được kiểm thử theo đặc điểm của đích ghi.

### Kiểm thử file writer

- Dùng thư mục tạm và file nhỏ để xác nhận encoding, header, delimiter, quoting và thứ tự dòng.
- Kiểm tra dữ liệu có dấu phẩy, dấu nháy, newline và ký tự Unicode.
- Kiểm tra file sau khi step hoàn thành và sau một lần restart mô phỏng.
- Xác nhận file tạm không bị công bố khi job thất bại nếu hệ thống yêu cầu output hoàn chỉnh.

### Kiểm thử database writer

- Dùng database test để xác nhận batch insert/update đúng.
- Kiểm tra rollback khi một câu lệnh trong chunk thất bại.
- Kiểm tra unique constraint, upsert và khả năng ghi lặp an toàn.
- Xác nhận transaction manager và datasource của writer đúng với cấu hình step.

### Kiểm thử message writer

- Dùng fake publisher hoặc broker test để xác nhận key, payload, headers và số message.
- Mô phỏng lỗi gửi trước và sau khi broker xác nhận.
- Kiểm tra writer chờ acknowledgement đúng yêu cầu.
- Gửi lại cùng event ID và xác nhận consumer có thể loại duplicate.
- Kiểm tra trường hợp database rollback sau khi message đã được publish.

### Kiểm thử composite writer

Kiểm tra thứ tự delegate, lỗi tại từng delegate và kết quả khi một đích đã ghi thành công còn đích khác thất bại. Đừng chỉ kiểm tra trường hợp mọi writer đều thành công; các tình huống lỗi mới cho thấy rõ chiến lược phục hồi.

## Nguyên tắc thiết kế writer trong production

1. Chọn writer theo đích và giao thức thực tế: file, JDBC, JPA hoặc broker.
2. Ghi theo chunk/batch để tận dụng hiệu năng của đích.
3. Xác định transaction manager và resource mà writer sử dụng.
4. Thiết kế idempotency cho retry, rollback và restart.
5. Với file, dùng đường dẫn và quy tắc công bố output rõ ràng.
6. Với message, xác định acknowledgement, key, event ID và delivery semantics.
7. Không nuốt exception hoặc báo thành công trước khi thao tác ghi đáp ứng điều kiện hoàn tất.
8. Dùng `ItemStream` khi writer tùy chỉnh cần lưu state cho restart.
9. Đo throughput, thời gian ghi, lỗi, retry và tài nguyên tiêu thụ.
10. Kiểm thử tình huống partial failure khi ghi nhiều resource.

## Ghi nhớ

`ItemWriter` nhận một chunk output và ghi tới đích. Dùng `FlatFileItemWriter` cho file, `JdbcBatchItemWriter` hoặc `JpaItemWriter` cho database, và writer tùy chỉnh dựa trên Kafka/JMS client hoặc adapter cho message broker. Writer cần phối hợp với transaction của step, xử lý exception đúng cách và có chiến lược restart/idempotency. Database có thể rollback trong transaction phù hợp; file cần quản lý state và công bố output hoàn chỉnh; message có thể đã được broker nhận dù chunk rollback nên cần event ID, outbox hoặc consumer idempotent. Khi ghi nhiều đích, phải thiết kế rõ hành vi nếu một đích thành công còn đích khác thất bại.
