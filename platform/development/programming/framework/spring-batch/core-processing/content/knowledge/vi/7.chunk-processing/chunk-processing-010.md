# Tách input, transformation và output

Trong Spring Batch, chunk-oriented processing chia một luồng xử lý thành ba trách nhiệm chính: đọc dữ liệu đầu vào, chuyển đổi từng item và ghi kết quả đầu ra. Ba trách nhiệm này tương ứng với `ItemReader`, `ItemProcessor` và `ItemWriter`.

`ItemReader` lấy dữ liệu từ nguồn như file CSV, database, message queue hoặc API. `ItemProcessor` kiểm tra, chuẩn hóa, lọc hoặc biến đổi một item sang mô hình mà bước tiếp theo cần. `ItemWriter` nhận một nhóm item đã xử lý và ghi chúng tới đích như database, file hoặc hệ thống khác. Spring Batch kết hợp ba thành phần trong một chunk transaction để quản lý commit, rollback, retry, skip và restart.

Việc tách input, transformation và output giúp mỗi thành phần tập trung vào một nhiệm vụ. Có thể thay nguồn dữ liệu mà giữ nguyên logic nghiệp vụ, thay cách ghi mà không phải sửa reader, hoặc kiểm thử transformation độc lập với database và file hệ thống.

## Mô hình Reader – Processor – Writer

Một chunk-oriented step thường có luồng dữ liệu:

```text
Nguồn dữ liệu
     |
     v
 ItemReader<I>
     |
     | đọc từng item I
     v
ItemProcessor<I, O>
     |
     | chuyển I thành O, hoặc trả null để lọc
     v
 ItemWriter<O>
     |
     | ghi một Chunk<O>
     v
Đích dữ liệu
```

Ký hiệu `I` là kiểu dữ liệu đầu vào và `O` là kiểu dữ liệu đầu ra sau transformation. Hai kiểu có thể giống nhau nếu processor chỉ kiểm tra hoặc chuẩn hóa tại chỗ, nhưng thường nên dùng các kiểu riêng để thể hiện ranh giới giữa dữ liệu nguồn và mô hình nghiệp vụ.

| Thành phần | Interface | Trách nhiệm | Đơn vị làm việc |
| --- | --- | --- | --- |
| Input | `ItemReader<I>` | Đọc item từ nguồn và xác định khi nào hết dữ liệu | Một item mỗi lần gọi `read()` |
| Transformation | `ItemProcessor<I, O>` | Kiểm tra, chuyển đổi, làm giàu hoặc lọc item | Một item mỗi lần gọi `process()` |
| Output | `ItemWriter<O>` | Ghi các item đã xử lý tới đích | Một chunk gồm nhiều item |

Reader và processor làm việc theo từng item. Writer nhận các item đã được processor xử lý trong một chunk, nên có thể ghi theo lô để giảm số lần gọi database hoặc hệ thống đích.

## Input: ItemReader

`ItemReader<T>` là abstraction đọc dữ liệu. Phương thức `read()` trả về một item mỗi lần được gọi. Khi không còn item nào, reader trả về `null` để báo kết thúc input.

```java
public interface ItemReader<T> {
    T read() throws Exception;
}
```

Một reader có thể đọc từ:

- File CSV, fixed-width, XML hoặc JSON.
- Bảng database qua JDBC hoặc JPA.
- Message queue hoặc một nguồn sự kiện.
- API, object storage hoặc một hệ thống bên ngoài.
- Một collection hoặc nguồn dữ liệu tự xây dựng.

Reader chịu trách nhiệm chuyển dữ liệu nguồn thành kiểu input mà processor hiểu. Ví dụ, `FlatFileItemReader` đọc từng dòng CSV và ánh xạ thành `OrderInput`; `JdbcCursorItemReader` đọc từng dòng kết quả truy vấn và ánh xạ thành một đối tượng Java.

### Hợp đồng của read()

Một số quy tắc quan trọng:

- Mỗi lần gọi `read()` trả về một item hoặc `null` khi hết dữ liệu.
- `null` mang ý nghĩa kết thúc input, không phải một item rỗng để processor xử lý.
- Lỗi đọc hoặc parse dữ liệu có thể làm step thất bại, trừ khi được cấu hình skip/retry phù hợp.
- Reader có state cần lưu trạng thái để hỗ trợ restart, ví dụ vị trí dòng, offset hoặc khóa bản ghi cuối.
- Reader cần tuân theo lifecycle và quy tắc thread-safety của loại step đang sử dụng.

### Ví dụ reader đọc CSV

Giả sử file `orders.csv` có nội dung:

```csv
orderId,customerId,amount,status
O-1001,C-01,125.50,NEW
O-1002,C-02,89.00,CANCELLED
O-1003,C-03,240.00,NEW
```

Định nghĩa mô hình input:

```java
public record OrderInput(
        String orderId,
        String customerId,
        BigDecimal amount,
        String status) {
}
```

Reader dùng `FlatFileItemReader` để đọc file, tách cột và ánh xạ mỗi dòng thành `OrderInput`:

```java
@Bean
FlatFileItemReader<OrderInput> orderReader(
        @Value("${batch.input.orders}") Resource inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(inputFile)
            .delimited()
            .names("orderId", "customerId", "amount", "status")
            .fieldSetMapper(fields -> new OrderInput(
                    fields.readString("orderId"),
                    fields.readString("customerId"),
                    fields.readBigDecimal("amount"),
                    fields.readString("status")))
            .build();
}
```

Reader xử lý việc truy cập file, phân tách cột và chuyển dữ liệu thô thành kiểu Java. Quy tắc nghiệp vụ như đơn hàng có được phép ghi hay không sẽ được đặt ở processor hoặc validator thích hợp.

### Reader có state và restart

Nhiều reader được Spring Batch cung cấp có khả năng lưu state vào `ExecutionContext`. Với file reader, state có thể bao gồm vị trí đọc hoặc số dòng đã xử lý. Khi step được restart, reader khôi phục state để tiếp tục từ vị trí phù hợp.

Reader tự viết muốn hỗ trợ restart thường cần triển khai cơ chế lưu và khôi phục state thông qua lifecycle của Spring Batch, chẳng hạn `ItemStream` với các phương thức `open`, `update` và `close`. Nếu reader không lưu state, cần hiểu rõ rằng restart có thể đọc lại từ đầu hoặc không thể tiếp tục đúng vị trí mong muốn.

Đối với reader đọc từ database, nên có thứ tự ổn định và cách phân trang/cursor phù hợp. Nếu dữ liệu nguồn thay đổi trong khi job chạy, cần xác định snapshot hoặc điều kiện truy vấn để tránh bỏ sót hay đọc trùng bản ghi.

## Transformation: ItemProcessor

`ItemProcessor<I, O>` nhận một item input kiểu `I` và trả về item output kiểu `O`. Đây là nơi phù hợp để thực hiện logic chuyển đổi cho từng bản ghi trước khi ghi.

```java
public interface ItemProcessor<I, O> {
    O process(I item) throws Exception;
}
```

Processor thường thực hiện:

- Kiểm tra dữ liệu theo quy tắc nghiệp vụ.
- Chuẩn hóa chuỗi, mã, ngày tháng hoặc đơn vị đo.
- Chuyển DTO nguồn thành domain object hoặc output DTO.
- Tính toán, ánh xạ trạng thái hoặc làm giàu dữ liệu.
- Lọc item không cần ghi bằng cách trả về `null`.

Processor nên tập trung vào transformation của item. Truy cập database hoặc gọi hệ thống ngoài trong processor có thể làm tăng thời gian xử lý, gây side effect khi retry và khiến logic khó kiểm thử. Nếu cần dữ liệu tham chiếu, hãy cân nhắc nạp trước, cache có kiểm soát hoặc thiết kế một service phù hợp với transaction và retry.

### Ví dụ chuyển OrderInput thành Order

Định nghĩa mô hình output riêng:

```java
public class Order {
    private final String orderId;
    private final String customerId;
    private final BigDecimal amount;
    private final String status;

    public Order(
            String orderId,
            String customerId,
            BigDecimal amount,
            String status) {
        this.orderId = orderId;
        this.customerId = customerId;
        this.amount = amount;
        this.status = status;
    }

    public String getOrderId() { return orderId; }
    public String getCustomerId() { return customerId; }
    public BigDecimal getAmount() { return amount; }
    public String getStatus() { return status; }
}
```

Processor chuyển đổi input, kiểm tra dữ liệu và lọc đơn hàng đã hủy:

```java
@Bean
ItemProcessor<OrderInput, Order> orderProcessor() {
    return new OrderProcessor();
}

public class OrderProcessor implements ItemProcessor<OrderInput, Order> {

    @Override
    public Order process(OrderInput input) {
        if (input.orderId() == null || input.orderId().isBlank()) {
            throw new InvalidOrderException("orderId is required");
        }

        if (input.amount() == null || input.amount().signum() <= 0) {
            throw new InvalidOrderException("amount must be positive");
        }

        if ("CANCELLED".equalsIgnoreCase(input.status())) {
            return null;
        }

        return new Order(
                input.orderId().trim(),
                input.customerId().trim(),
                input.amount(),
                input.status().trim().toUpperCase(Locale.ROOT));
    }
}
```

Ví dụ giả định `customerId` và `status` đã có giá trị hợp lệ sau khi đọc; trong ứng dụng thực tế cần kiểm tra null và quy tắc nghiệp vụ cho các trường này. `InvalidOrderException` là exception nghiệp vụ do ứng dụng định nghĩa.

### Lọc item bằng cách trả về null

Nếu `process()` trả về `null`, Spring Batch loại item đó khỏi luồng output. Item bị lọc không được chuyển tới writer. Đây là cách thể hiện một bản ghi hợp lệ về mặt cấu trúc nhưng không cần xuất ra đích, ví dụ đơn hàng đã hủy hoặc giao dịch nằm ngoài phạm vi báo cáo.

Phân biệt hai trường hợp:

| Kết quả processor | Ý nghĩa | Writer nhận item? |
| --- | --- | --- |
| Trả về object | Item được chuyển đổi thành công | Có |
| Trả về `null` | Item được lọc có chủ đích | Không |
| Ném exception | Xử lý item gặp lỗi | Phụ thuộc cấu hình retry/skip; nếu không xử lý được thì step thất bại |

Không dùng `null` để che giấu dữ liệu lỗi. Nếu item không hợp lệ và cần ghi nhận hoặc xử lý theo chính sách lỗi, hãy ném exception phù hợp và cấu hình skip, retry hoặc xử lý lỗi riêng.

### Processor chain

Khi transformation có nhiều bước độc lập, có thể kết hợp các processor theo chuỗi. Ví dụ:

```text
OrderInput
    |
    v
NormalizeOrderProcessor
    |
    v
ValidateOrderProcessor
    |
    v
EnrichOrderProcessor
    |
    v
Order
```

Spring Batch cung cấp `CompositeItemProcessor` để ghép các processor. Kiểu output của processor trước phải tương thích với kiểu input của processor tiếp theo.

```java
@Bean
CompositeItemProcessor<OrderInput, Order> orderProcessorChain(
        ItemProcessor<OrderInput, NormalizedOrder> normalizeProcessor,
        ItemProcessor<NormalizedOrder, ValidatedOrder> validateProcessor,
        ItemProcessor<ValidatedOrder, Order> mapProcessor) throws Exception {

    return new CompositeItemProcessorBuilder<OrderInput, Order>()
            .delegates(
                    normalizeProcessor,
                    validateProcessor,
                    mapProcessor)
            .build();
}
```

Các kiểu `NormalizedOrder` và `ValidatedOrder` biểu diễn kết quả trung gian. Cách chia này hữu ích khi mỗi bước có logic rõ ràng và có thể tái sử dụng hoặc kiểm thử riêng. Với transformation đơn giản, một processor duy nhất thường dễ đọc hơn.

## Output: ItemWriter

`ItemWriter<T>` nhận một nhóm item đã được processor xử lý và ghi chúng tới đích. Trong Spring Batch 5, phương thức `write` nhận một `Chunk`:

```java
public interface ItemWriter<T> {
    void write(Chunk<? extends T> chunk) throws Exception;
}
```

Ở các phiên bản cũ, chữ ký của `ItemWriter` có thể dùng `List<? extends T>`; hãy dùng API tương ứng với phiên bản framework của dự án. Về mặt xử lý, writer luôn nhận tập item của chunk hiện tại thay vì được gọi riêng cho từng item.

Writer có thể ghi tới:

- Database qua `JdbcBatchItemWriter`, `JpaItemWriter` hoặc writer tự triển khai.
- File qua `FlatFileItemWriter` hoặc writer chuyên dụng.
- Message broker hoặc hệ thống bên ngoài.
- Một dịch vụ lưu trữ hay API đích.

### Ví dụ ghi vào database

Với `JdbcBatchItemWriter`, có thể ghi một nhóm `Order` bằng batch SQL:

```java
@Bean
JdbcBatchItemWriter<Order> orderWriter(DataSource dataSource) {
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

`beanMapped()` ánh xạ named parameter trong SQL tới property của đối tượng output. Writer không cần biết dữ liệu ban đầu đến từ CSV hay database; nó chỉ cần nhận đúng kiểu `Order`.

Nếu cần cập nhật thay vì insert, có thể dùng câu SQL update/upsert phù hợp với hệ quản trị cơ sở dữ liệu. Cần xác định khóa nghiệp vụ và hành vi khi writer được gọi lại do retry hoặc restart.

### Ví dụ writer tự triển khai

Trong Spring Batch 5, một writer tùy chỉnh có thể nhận `Chunk`:

```java
public class AuditItemWriter implements ItemWriter<Order> {

    @Override
    public void write(Chunk<? extends Order> chunk) {
        for (Order order : chunk) {
            System.out.printf(
                    "Writing order %s for customer %s%n",
                    order.getOrderId(),
                    order.getCustomerId());
        }
    }
}
```

Ví dụ chỉ minh họa hợp đồng writer; `System.out` không phải nơi lưu dữ liệu production. Writer thực tế nên dùng repository, file writer hoặc client tới hệ thống đích và xử lý lỗi theo chính sách transaction của step.

## Kết nối ba thành phần trong một chunk step

Khi khai báo step, Spring Batch nhận reader, processor và writer rồi điều phối chúng theo commit interval. Ví dụ dưới đây dùng API builder của Spring Batch 5:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        FlatFileItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        JdbcBatchItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
```

Generic type trong `.<OrderInput, Order>chunk(...)` cho biết reader tạo `OrderInput`, processor chuyển sang `Order`, writer nhận `Order`. `chunk(100, transactionManager)` cấu hình tối đa 100 item đầu vào cho một chunk trước khi commit theo luồng xử lý thông thường.

Trong ứng dụng thực tế, cần khai báo các bean reader, processor và writer với tên phù hợp, cấu hình resource đầu vào, datasource và schema đích. Đoạn code tập trung vào cách ghép ba thành phần trong step.

## Một chunk được xử lý như thế nào?

Giả sử `commit-interval` là 3 và nguồn có năm item. Luồng xử lý khái quát:

```text
Chunk 1
  Reader: I1, I2, I3
  Processor: O1, null, O3
  Writer: [O1, O3]
  COMMIT

Chunk 2
  Reader: I4, I5, EOF
  Processor: O4, O5
  Writer: [O4, O5]
  COMMIT
```

Item `I2` bị processor lọc bằng cách trả về `null`, nên writer chỉ nhận `O1` và `O3`. Số item được đọc và số item được ghi có thể khác nhau vì processor có thể lọc item.

Các bước ở mức khái niệm:

1. Mở transaction cho chunk.
2. Reader được gọi nhiều lần để lấy các item đầu vào cho chunk.
3. Với mỗi item, processor được gọi để tạo output hoặc lọc item.
4. Writer nhận các output còn lại trong chunk và ghi chúng.
5. Spring Batch cập nhật metadata và execution context theo cấu hình của step.
6. Transaction commit; nếu lỗi làm transaction rollback, các thay đổi tham gia transaction được rollback.
7. Tiếp tục chunk tiếp theo cho tới khi reader báo hết dữ liệu.

Chi tiết lifecycle và thời điểm gọi listener có thể khác theo loại step và phiên bản, nhưng ranh giới chunk transaction là nền tảng để hiểu commit, rollback và restart.

## Transaction và tính nhất quán

Trong chunk-oriented step, reader, processor, writer và cập nhật metadata được điều phối quanh transaction của chunk. Khi writer ghi vào cùng database resource và sử dụng transaction manager phù hợp, dữ liệu nghiệp vụ và checkpoint có thể cùng commit hoặc rollback.

Nếu writer ghi ra một hệ thống ngoài transaction của database, chẳng hạn gọi HTTP hoặc publish message, side effect đó không tự động rollback khi chunk thất bại. Một lần retry có thể gửi message hoặc gọi API lần nữa. Khi đó cần idempotency key, outbox pattern, hoặc cơ chế đối soát phù hợp.

Reader cũng cần được xem xét theo nguồn dữ liệu. Với database cursor hoặc paging reader, transaction và snapshot isolation có thể ảnh hưởng dữ liệu đọc. Với file reader, vị trí đọc được lưu trong execution context để restart. Không phải mọi reader đều rollback được tác động đọc bên ngoài; cần dựa vào state management của reader cụ thể.

### Vì sao writer nên có tính idempotent?

Giả sử writer ghi một chunk thành công tới hệ thống đích, nhưng tiến trình dừng trước khi checkpoint được lưu. Khi restart, cùng các item có thể được gửi tới writer lần nữa. Nếu writer insert không kiểm soát trùng, kết quả có thể tạo duplicate.

Các cách giảm rủi ro:

- Dùng business key ổn định và unique constraint.
- Dùng upsert hoặc thao tác ghi có điều kiện theo quy tắc nghiệp vụ.
- Gắn idempotency key khi gọi API hoặc publish message.
- Lưu trạng thái xử lý tại hệ thống đích để nhận biết yêu cầu đã được áp dụng.
- Đối soát các trường hợp transaction giữa batch metadata và dữ liệu đích không commit đồng thời.

## Skip, retry và lỗi ở từng tầng

Lỗi có thể xuất hiện khi đọc, chuyển đổi hoặc ghi. Cần phân biệt nguồn lỗi để cấu hình chính sách phù hợp.

| Tầng | Ví dụ lỗi | Cách xử lý có thể cân nhắc |
| --- | --- | --- |
| Reader | Dòng CSV sai định dạng, lỗi kết nối nguồn | Skip lỗi parse có thể phục hồi; retry lỗi tạm thời nếu thao tác đọc an toàn |
| Processor | Dữ liệu không hợp lệ, dịch vụ tham chiếu tạm thời lỗi | Skip lỗi dữ liệu theo quy tắc; retry lỗi tạm thời nếu processor không tạo side effect |
| Writer | Deadlock, timeout database, lỗi hệ thống đích | Retry lỗi tạm thời; skip chỉ khi nghiệp vụ cho phép bỏ bản ghi |

Ví dụ cấu hình skip cho một loại lỗi dữ liệu cụ thể:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(20)
        .build();
```

Với cấu hình này, tối đa 20 lỗi thuộc loại `InvalidOrderException` được skip theo quy tắc fault tolerance của step. Lỗi vượt giới hạn hoặc lỗi không thuộc loại được khai báo có thể làm step thất bại. Không nên skip mọi exception một cách rộng rãi vì có thể che giấu lỗi hạ tầng hoặc làm mất dữ liệu.

Retry phù hợp với lỗi tạm thời như deadlock hoặc timeout nếu thao tác có thể thực hiện lại an toàn. Processor và writer cần tránh side effect không thể lặp an toàn. Với lỗi nghiệp vụ cố định như mã khách hàng không tồn tại, retry thường không giúp khắc phục vấn đề.

## Restart và ExecutionContext

Khi job bị dừng hoặc thất bại, Spring Batch có thể restart `JobInstance` nếu cấu hình và trạng thái cho phép. Reader có khả năng restart lưu tiến trình đọc vào `ExecutionContext`, còn repository lưu metadata để lần chạy mới biết cần tiếp tục từ đâu.

Trong mô hình tách input, transformation và output:

- Reader cần khôi phục đúng vị trí hoặc khóa tiếp tục.
- Processor nên có kết quả xác định từ input và trạng thái tham chiếu ổn định trong phạm vi lần chạy.
- Writer cần xử lý an toàn nếu item được gửi lại do retry hoặc restart.
- Các tham số identifying cần giữ nguyên khi restart cùng logical job.

Nếu processor phụ thuộc vào thời điểm hiện tại, dữ liệu tham chiếu thay đổi hoặc một API ngoài có side effect, kết quả restart có thể khác lần chạy đầu. Hãy cân nhắc truyền giá trị nghiệp vụ qua `JobParameters`, lưu snapshot tham chiếu cần thiết hoặc thiết kế processor có tính lặp an toàn.

Không nên tự tăng timestamp identifying mỗi lần restart. Làm vậy sẽ tạo `JobInstance` mới và tách lịch sử khỏi execution trước đó.

## Tách thành phần để kiểm thử độc lập

Một lợi ích lớn của mô hình Reader–Processor–Writer là có thể kiểm thử từng tầng với dữ liệu nhỏ mà không cần chạy toàn bộ job.

### Kiểm thử processor

Processor thường là phần dễ kiểm thử nhất vì đầu vào và đầu ra là object Java:

```java
@Test
void filtersCancelledOrders() throws Exception {
    OrderProcessor processor = new OrderProcessor();

    OrderInput input = new OrderInput(
            "O-1002", "C-02", new BigDecimal("89.00"), "CANCELLED");

    assertNull(processor.process(input));
}
```

Các test khác có thể kiểm tra chuẩn hóa chuỗi, tính toán, chuyển đổi trạng thái và exception cho dữ liệu không hợp lệ.

### Kiểm thử reader

Với reader file, dùng file mẫu nhỏ và kiểm tra từng item trả về cùng thứ tự. Kiểm tra thêm header, dòng rỗng, encoding, dấu phân cách, giá trị thiếu và hành vi EOF. Với reader có state, cần kiểm tra khả năng lưu state rồi mở lại để tiếp tục.

### Kiểm thử writer

Với writer database, có thể dùng database test hoặc test slice phù hợp để xác nhận nhiều item trong một chunk được ghi đúng. Kiểm tra constraint, rollback khi có lỗi, hành vi upsert và khả năng xử lý lặp.

### Kiểm thử tích hợp step

Cuối cùng, kiểm thử step với reader, processor và writer thật hoặc test double. Xác nhận số item đọc, số item ghi, item bị filter/skip, trạng thái step và kết quả sau restart. Kiểm thử tích hợp giúp xác nhận ba thành phần phối hợp đúng qua ranh giới transaction.

## Thay đổi nguồn hoặc đích mà không đổi logic nghiệp vụ

Khi ba trách nhiệm được tách rõ, có thể tái sử dụng processor cho nhiều nguồn và writer cho nhiều job.

Ví dụ:

```text
CSV Reader --------+
                   |
Database Reader ---+----> Order Processor ----> Database Writer
                   |                    |
API Reader --------+                    +------> File Writer
```

`OrderProcessor` có thể dùng chung nếu các reader tạo cùng kiểu `OrderInput`. Nếu nguồn khác có schema khác, chỉ cần viết adapter reader để ánh xạ về cùng mô hình input. Tương tự, nhiều writer có thể nhận cùng kiểu output nếu ứng dụng cần ghi ra nhiều đích, nhưng phải xác định rõ transaction và hành vi khi một đích thành công còn đích khác thất bại.

Không phải lúc nào cũng nên tái sử dụng một processor cho mọi luồng. Nếu quy tắc nghiệp vụ khác nhau, hãy dùng processor riêng hoặc cấu hình chain rõ ràng để tránh một lớp chứa quá nhiều nhánh theo nguồn dữ liệu.

## Những điểm cần cân nhắc khi thiết kế từng tầng

### Thiết kế input

- Chọn kiểu input phản ánh cấu trúc dữ liệu nguồn và không phụ thuộc quá nhiều vào database đích.
- Xác định thứ tự đọc ổn định, điều kiện lọc nguồn và cách xử lý dữ liệu thay đổi trong khi job chạy.
- Dùng reader có state nếu cần restart; cấu hình tên reader duy nhất và ổn định.
- Quyết định lỗi parse nào được skip, lỗi nào phải dừng job.
- Tránh tải toàn bộ dữ liệu lớn vào memory; ưu tiên cursor, paging hoặc streaming phù hợp.

### Thiết kế transformation

- Giữ processor tập trung vào một nhiệm vụ rõ ràng.
- Phân biệt dữ liệu sai định dạng, dữ liệu vi phạm nghiệp vụ và dữ liệu hợp lệ nhưng không cần output.
- Trả về `null` chỉ khi muốn filter item có chủ đích.
- Tránh side effect không idempotent trong processor.
- Giữ transformation xác định và dễ kiểm thử; truyền cấu hình cần thiết qua constructor hoặc job parameters.
- Tách processor thành chain khi từng bước đủ độc lập và có lợi ích tái sử dụng.

### Thiết kế output

- Ghi theo lô để tận dụng batch insert/update nếu hệ thống đích hỗ trợ.
- Xác định transaction manager và cách writer tham gia transaction chunk.
- Thiết kế idempotency để retry/restart không tạo dữ liệu trùng.
- Quy định rõ cách xử lý lỗi từng item và lỗi toàn chunk.
- Tránh thực hiện side effect không thể rollback mà không có cơ chế bù trừ hoặc đối soát.
- Theo dõi throughput, thời gian ghi, số lần retry và lỗi từ hệ thống đích.

## Các lỗi thiết kế thường gặp

### Đặt toàn bộ logic vào reader

Reader vừa truy vấn, vừa áp dụng quy tắc nghiệp vụ, vừa ghi dữ liệu phụ khiến nó khó tái sử dụng và kiểm thử. Reader nên tập trung lấy dữ liệu và ánh xạ sang kiểu input. Transformation thuộc processor; ghi dữ liệu thuộc writer.

### Processor gọi API hoặc ghi database cho từng item

Điều này có thể tạo rất nhiều request nhỏ, làm chậm job và gây side effect khi retry. Nếu cần làm giàu dữ liệu, hãy xem xét batch lookup, cache có giới hạn hoặc thiết kế dịch vụ có transaction/idempotency phù hợp.

### Writer xử lý lại việc parse dữ liệu nguồn

Nếu writer phải hiểu định dạng CSV hoặc tên cột của hệ thống nguồn, ranh giới input và output chưa rõ. Writer nên nhận mô hình output ổn định, độc lập với định dạng đầu vào.

### Dùng null cho mọi loại lỗi

Trả về `null` là filter item có chủ đích. Dùng nó cho dữ liệu sai hoặc lỗi hệ thống khiến bản ghi biến mất mà không có thống kê hay thông tin giải thích. Dùng exception và skip policy khi cần ghi nhận lỗi.

### Không tính đến transaction của hệ thống đích

Writer gọi API hoặc publish message có thể đã tạo side effect dù chunk rollback. Hãy thiết kế idempotency, outbox hoặc cơ chế xác nhận để xử lý retry an toàn.

### Chọn chunk size mà không đo tải

Chunk quá nhỏ làm tăng số lần commit và gọi writer; chunk quá lớn giữ transaction lâu, tăng lock và phạm vi rollback. Đo hiệu năng với dữ liệu gần thực tế rồi chọn giá trị phù hợp.

## Khi nào mô hình này phù hợp?

Mô hình Reader–Processor–Writer phù hợp khi job cần xử lý một tập item theo luồng, có thể chia thành các chunk và mỗi item có thể được đọc, biến đổi rồi ghi độc lập. Nó đặc biệt hữu ích khi input và output khác định dạng hoặc khác hệ thống.

Ví dụ:

| Bài toán | Reader | Processor | Writer |
| --- | --- | --- | --- |
| Nhập đơn hàng CSV | Đọc dòng CSV | Parse, validate, chuẩn hóa đơn hàng | Insert/upsert database |
| Đồng bộ khách hàng | Đọc khách hàng từ database nguồn | Chuẩn hóa địa chỉ, ánh xạ trạng thái | Ghi database đích hoặc API |
| Tạo báo cáo | Đọc giao dịch theo kỳ | Tính toán và nhóm dữ liệu | Ghi CSV hoặc file báo cáo |
| Chuyển đổi dữ liệu legacy | Đọc bản ghi cũ | Ánh xạ sang mô hình mới | Ghi schema mới |

Nếu công việc chỉ gồm một thao tác đơn giản, không cần xử lý từng item, `Tasklet` có thể phù hợp hơn. Nếu cần xử lý nhiều nguồn/đích với logic phức tạp, có thể chia thành nhiều step hoặc dùng flow riêng. Chunk processing phát huy tác dụng khi cần quản lý commit, restart, skip/retry và throughput cho một tập item.

## Ghi nhớ

Trong chunk processing, `ItemReader` chịu trách nhiệm lấy từng item đầu vào, `ItemProcessor` chuyển đổi hoặc lọc từng item, và `ItemWriter` ghi một nhóm output của chunk. Tách ba tầng giúp thay nguồn và đích độc lập, kiểm thử logic rõ ràng và quản lý transaction theo chunk. Reader cần state phù hợp cho restart; processor nên tập trung vào transformation có thể kiểm thử; writer cần batch write và idempotency khi retry hoặc restart. Trả về `null` từ processor có nghĩa là filter item, còn lỗi cần xử lý phải được biểu diễn bằng exception cùng chính sách skip/retry thích hợp.
