# ItemReader, ItemProcessor và ItemWriter

Trong Spring Batch, **chunk processing** là mô hình xử lý dữ liệu theo từng nhóm item. Một step theo mô hình này thường đọc dữ liệu từ nguồn, tùy chọn chuyển đổi hoặc lọc từng item, sau đó ghi kết quả thành một chunk đến đích. Ba abstraction đảm nhiệm các phần việc đó là `ItemReader`, `ItemProcessor` và `ItemWriter`.

Ba thành phần này giúp tách rõ trách nhiệm của một luồng xử lý batch. Reader tập trung lấy dữ liệu, processor tập trung áp dụng quy tắc xử lý cho từng item, còn writer tập trung ghi kết quả. Spring Batch điều phối chúng theo kích thước chunk, quản lý giao dịch và lưu metadata để hỗ trợ theo dõi cũng như restart.

## 1. Luồng read-process-write trong một chunk

Một chunk-oriented step thường được cấu hình với ba thành phần:

```text
Nguồn dữ liệu
     |
     v
 ItemReader
     |
     | từng item
     v
ItemProcessor (tùy chọn)
     |
     | item đã chuyển đổi hoặc bị lọc
     v
  ItemWriter
     |
     v
Đích dữ liệu

Spring Batch gom item thành chunk, quản lý transaction,
checkpoint và trạng thái StepExecution.
```

Giả sử chunk size bằng 100. Spring Batch gọi reader nhiều lần để lấy tối đa 100 item. Mỗi item được chuyển qua processor nếu step có cấu hình processor. Các kết quả được gom lại rồi chuyển cho writer trong một lần ghi chunk. Khi giao dịch commit thành công, framework tiếp tục đọc chunk tiếp theo.

```text
Chunk 1: đọc tối đa 100 item
         -> xử lý từng item
         -> ghi nhóm kết quả
         -> commit

Chunk 2: đọc tối đa 100 item tiếp theo
         -> xử lý từng item
         -> ghi nhóm kết quả
         -> commit

Chunk cuối: có thể ít hơn 100 item
            -> ghi phần còn lại
            -> commit
            -> kết thúc step khi reader báo hết dữ liệu
```

Chunk size là số item đầu vào mà step gom cho một chu kỳ xử lý, không nhất thiết bằng số item writer nhận được. Nếu processor lọc bỏ một số item bằng cách trả về `null`, chunk đầu ra sẽ ít item hơn chunk đầu vào.

## 2. Hợp đồng của ba interface

Các interface cốt lõi có thể hiểu qua những chữ ký phương thức sau:

```java
public interface ItemReader<T> {
    T read() throws Exception;
}

public interface ItemProcessor<I, O> {
    O process(I item) throws Exception;
}

public interface ItemWriter<T> {
    void write(Chunk<? extends T> chunk) throws Exception;
}
```

Đây là API theo Spring Batch 5 trở lên. Trong Spring Batch 4 và các phiên bản cũ hơn, chữ ký `ItemWriter.write` sử dụng `List` thay vì `Chunk`, vì vậy code writer cũ có thể khác code hiện tại.

| Thành phần | Đầu vào | Đầu ra | Trách nhiệm |
|---|---|---|---|
| `ItemReader<T>` | Nguồn dữ liệu hoặc trạng thái đọc | Một item kiểu `T` ở mỗi lần gọi | Lấy item kế tiếp; trả về `null` khi hết dữ liệu. |
| `ItemProcessor<I, O>` | Một item kiểu `I` | Item kiểu `O`, hoặc `null` để lọc | Kiểm tra, biến đổi, làm giàu hoặc loại item. |
| `ItemWriter<T>` | Một `Chunk` gồm các item kiểu `T` | Không trả về giá trị | Ghi một nhóm item đến đích. |

Processor là thành phần tùy chọn. Nếu không cần biến đổi hoặc lọc dữ liệu, step có thể nối reader trực tiếp với writer. Khi có processor, kiểu đầu ra `O` của processor phải phù hợp với kiểu item mà writer nhận.

## 3. ItemReader: đọc từng item từ nguồn dữ liệu

`ItemReader<T>` chịu trách nhiệm cung cấp dữ liệu đầu vào cho step. Mỗi lần framework gọi `read()`, reader trả về một item tiếp theo. Khi không còn dữ liệu, reader trả về `null` để báo kết thúc.

Ví dụ, một reader có thể lần lượt trả về các đơn hàng đọc từ file CSV:

```text
read() lần 1 -> OrderInput(orderId="O-001", ...)
read() lần 2 -> OrderInput(orderId="O-002", ...)
read() lần 3 -> OrderInput(orderId="O-003", ...)
read() lần 4 -> null
```

Giá trị `null` có ý nghĩa đặc biệt: nó báo không còn item để đọc. Nếu dữ liệu nghiệp vụ có một trường nullable, hãy biểu diễn trường đó bên trong đối tượng item; không dùng một item `null` để biểu thị bản ghi có trường rỗng.

### Các nguồn dữ liệu thường gặp

Spring Batch có nhiều reader triển khai sẵn cho các nguồn dữ liệu khác nhau:

| Reader | Nguồn dữ liệu và cách hoạt động |
|---|---|
| `FlatFileItemReader` | Đọc file văn bản, CSV hoặc dữ liệu phân cách theo dòng. |
| `JdbcCursorItemReader` | Đọc kết quả truy vấn JDBC bằng cursor. |
| `JdbcPagingItemReader` | Đọc dữ liệu theo từng trang thông qua truy vấn phân trang. |
| `JpaPagingItemReader` | Đọc entity từ JPA theo từng trang. |
| `RepositoryItemReader` | Đọc dữ liệu thông qua Spring Data repository có hỗ trợ phân trang. |
| `StaxEventItemReader` | Đọc các phần tử XML theo cơ chế streaming. |

Chọn reader dựa trên kích thước dữ liệu, khả năng phân trang, cách quản lý tài nguyên, yêu cầu restart và đặc tính của nguồn. Với file lớn, nên đọc theo luồng thay vì tải toàn bộ file vào bộ nhớ. Với bảng dữ liệu lớn, cursor hoặc paging có thể phù hợp tùy database, transaction và kế hoạch truy vấn.

### Reader không nên làm thay công việc của processor

Reader nên tập trung lấy dữ liệu và ánh xạ dữ liệu nguồn thành item. Ví dụ, `FlatFileItemReader` có thể phân tích một dòng CSV thành `OrderInput`. Các quy tắc như đơn hàng có số tiền hợp lệ hay khách hàng có được phép mua hay không thường thuộc processor hoặc một service nghiệp vụ mà processor gọi.

Việc tách trách nhiệm giúp thay nguồn dữ liệu mà không phải viết lại quy tắc nghiệp vụ. Cùng một processor có thể được dùng với reader từ file, database hoặc API nếu kiểu item đầu vào tương thích.

### Reader và trạng thái đọc

Nhiều reader tích hợp của Spring Batch hỗ trợ restart bằng cách lưu trạng thái đọc trong `ExecutionContext`. Các thành phần triển khai `ItemStream` có vòng đời gồm `open`, `update` và `close`:

- `open`: mở tài nguyên và khôi phục trạng thái đã lưu nếu có.
- `update`: ghi trạng thái hiện tại vào `ExecutionContext` để checkpoint.
- `close`: giải phóng tài nguyên như stream hoặc cursor.

Ví dụ, reader file có thể lưu vị trí dòng đã đọc. Sau khi một chunk commit, Spring Batch lưu checkpoint. Nếu step thất bại, lần restart có thể mở lại file và tiếp tục từ vị trí phù hợp.

Không phải reader nào cũng có thể restart. Reader tự viết muốn hỗ trợ khả năng này thường cần triển khai `ItemStream` hoặc `ItemStreamReader`, lưu trạng thái cần thiết trong `update` và khôi phục trạng thái trong `open`. Với reader không hỗ trợ lưu trạng thái, lần restart có thể phải đọc lại từ đầu hoặc cần cơ chế phục hồi do ứng dụng tự xây dựng.

### Reader cần xử lý việc đọc lại

Trong trường hợp chunk rollback, framework có thể đọc lại các item chưa được commit. Vì vậy, không nên giả định mỗi item chỉ được gọi `read()` đúng một lần trong toàn bộ vòng đời job. Reader cần có hành vi nhất quán khi transaction rollback và khi restart.

Nếu reader lấy dữ liệu từ một nguồn có trạng thái tiêu thụ không thể hoàn tác, chẳng hạn một hàng đợi mà việc nhận message đã xác nhận ngay lập tức, cần thiết kế cơ chế acknowledge và transaction phù hợp. Nếu không, job có thể mất dữ liệu khi rollback hoặc nhận lại item ngoài dự kiến.

## 4. ItemProcessor: biến đổi hoặc lọc từng item

`ItemProcessor<I, O>` nhận một item kiểu `I` và trả về một item kiểu `O`. Kiểu đầu vào và đầu ra có thể giống hoặc khác nhau.

Processor thường đảm nhiệm các công việc:

- Kiểm tra quy tắc nghiệp vụ.
- Chuẩn hóa dữ liệu như mã, chuỗi, ngày hoặc số tiền.
- Chuyển đổi DTO đầu vào thành đối tượng miền nghiệp vụ.
- Bổ sung dữ liệu cần thiết trước khi ghi.
- Lọc những item không cần đưa đến writer.

Ví dụ chuyển đổi dữ liệu nhập từ file thành đối tượng đơn hàng:

```java
@Bean
ItemProcessor<OrderInput, Order> orderProcessor() {
    return input -> {
        if (input.amount().signum() <= 0) {
            throw new InvalidOrderException(
                    "Order amount must be greater than zero");
        }

        return new Order(
                input.orderId(),
                input.customerId(),
                input.amount());
    };
}
```

Ở đây, processor nhận `OrderInput`, kiểm tra số tiền rồi tạo `Order`. Reader và writer không cần biết quy tắc chuyển đổi cụ thể.

### Trả về null để filter item

Một đặc điểm quan trọng của `ItemProcessor` là có thể trả về `null`. Spring Batch hiểu đây là yêu cầu lọc bỏ item: item đó không được chuyển tiếp đến writer.

```java
@Bean
ItemProcessor<OrderInput, Order> orderFilter() {
    return input -> {
        if (input.amount().signum() <= 0) {
            return null;
        }

        return new Order(
                input.orderId(),
                input.customerId(),
                input.amount());
    };
}
```

Trong ví dụ, các đơn hàng có số tiền không dương bị loại khỏi đầu ra của processor. Đây là filter, không phải skip do exception.

### Phân biệt filter và skip

Hai cơ chế này có mục đích khác nhau:

| Cơ chế | Cách thực hiện | Ý nghĩa |
|---|---|---|
| Filter | Processor trả về `null` | Item được chủ động loại khỏi kết quả, không chuyển đến writer. |
| Skip | Một exception được ném ra và được skip policy cho phép | Item hoặc thao tác lỗi được bỏ qua theo chính sách lỗi của step. |

Nếu item không đáp ứng điều kiện để xử lý nhưng đó là trường hợp nghiệp vụ bình thường, filter có thể phù hợp. Nếu item có dữ liệu sai định dạng, lỗi mapping hoặc vi phạm cần ghi nhận như một lỗi xử lý, có thể ném exception và cấu hình skip cùng listener hoặc cơ chế ghi nhận lỗi.

Không nên trả `null` cho mọi loại lỗi chỉ để job tiếp tục. Cách đó làm mất thông tin nguyên nhân và có thể khiến dữ liệu không hợp lệ bị loại âm thầm.

### Processor nên tập trung vào xử lý item

Processor thường được gọi một lần cho mỗi item trong chunk. Nên giữ logic xử lý có thể kiểm soát và dễ kiểm thử. Tránh thực hiện tác dụng phụ không thể hoàn tác như gửi email, trừ khi đã có thiết kế idempotency phù hợp. Nếu chunk rollback hoặc step restart, processor có thể được gọi lại cho cùng item.

Với quy tắc nghiệp vụ phức tạp, processor có thể gọi một service riêng. Cách này giúp tái sử dụng logic và giữ lớp batch tập trung vào việc điều phối item.

### Ghép nhiều processor

Khi cần nhiều phép biến đổi tuần tự, có thể dùng `CompositeItemProcessor` để nối các processor nhỏ. Ví dụ:

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
CalculateTaxProcessor
    |
    v
Order
```

Mỗi processor có một trách nhiệm rõ ràng. Kiểu đầu ra của processor trước phải tương thích với kiểu đầu vào của processor kế tiếp. Nếu một processor trả về `null`, item bị lọc và không tiếp tục qua các processor còn lại.

## 5. ItemWriter: ghi một chunk đến đích

`ItemWriter<T>` nhận một nhóm item đã được xử lý và ghi chúng đến đích. Khác với reader và processor làm việc từng item, writer nhận toàn bộ chunk trong một lần gọi.

Một số writer thường gặp:

- `JdbcBatchItemWriter`: ghi nhiều bản ghi vào cơ sở dữ liệu bằng JDBC batch.
- `FlatFileItemWriter`: ghi dữ liệu ra file theo định dạng được cấu hình.
- `RepositoryItemWriter`: ghi thông qua Spring Data repository.
- `JsonFileItemWriter`: ghi các item ra file JSON theo cấu hình tương ứng của phiên bản.

Writer nên tập trung vào việc lưu kết quả. Việc tính toán hoặc kiểm tra quy tắc nghiệp vụ chính thường thuộc processor. Phân chia như vậy giúp writer có thể thay đổi đích lưu trữ mà không phải thay đổi logic chuyển đổi dữ liệu.

### Writer nhận Chunk thay vì một item

Trong Spring Batch 5 trở lên, phương thức `write` nhận một `Chunk`:

```java
public void write(Chunk<? extends Order> chunk) throws Exception {
    for (Order order : chunk) {
        // Ghi order đến đích.
    }
}
```

Framework gom các kết quả từ processor rồi gọi writer. Với chunk size 100 và không có item nào bị filter, writer thường nhận một chunk gồm 100 item. Nếu có item bị filter, số item thực tế trong chunk đầu ra có thể nhỏ hơn.

Writer có thể dùng batch insert/update để giảm số lần round trip đến database. Ví dụ, `JdbcBatchItemWriter` hỗ trợ thực thi một câu SQL cho nhiều item bằng tham số của từng đối tượng.

### Ghi dữ liệu và transaction

Trong chunk-oriented step, thao tác ghi thường diễn ra trong transaction của chunk. Nếu writer phát sinh exception trước khi commit, transaction manager có thể rollback các thay đổi thuộc cùng giao dịch. Spring Batch sau đó áp dụng retry, skip hoặc đánh dấu step thất bại tùy cấu hình.

Tuy nhiên, rollback chỉ áp dụng cho tài nguyên tham gia giao dịch tương ứng. Nếu writer gọi HTTP API, gửi email hoặc ghi sang hệ thống không tham gia transaction, thao tác bên ngoài có thể đã thành công dù chunk sau đó rollback. Khi đó retry có thể gửi lại cùng yêu cầu.

Với writer tích hợp hệ thống ngoài, cần xem xét:

- Idempotency key hoặc mã nghiệp vụ duy nhất để hệ thống nhận biết yêu cầu lặp.
- Cơ chế tra cứu trạng thái đã ghi nhận trước khi gửi lại.
- Outbox pattern hoặc một quy trình phát sự kiện riêng khi cần đồng bộ database với hệ thống khác.
- Cách xử lý timeout khi không biết chắc hệ thống đích đã nhận yêu cầu hay chưa.

Writer không nên giả định một lần gọi `write` luôn chỉ xảy ra đúng một lần trong toàn bộ vòng đời job. Retry hoặc restart có thể khiến cùng dữ liệu được ghi lại.

## 6. Ghép reader, processor và writer trong một Step

Trong Spring Batch 5 trở lên, chunk-oriented step thường được cấu hình bằng `StepBuilder` và `JobRepository`. Phương thức `chunk` nhận kích thước chunk cùng `PlatformTransactionManager`.

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
```

Khai báo generic `.<OrderInput, Order>` cho biết:

- Reader cung cấp `OrderInput`.
- Processor nhận `OrderInput` và trả về `Order`.
- Writer nhận chunk các đối tượng `Order`.

Nếu không cần processor, có thể cấu hình reader và writer với cùng kiểu item:

```java
return new StepBuilder("copyOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .writer(orderWriter)
        .build();
```

Trong trường hợp này, item từ reader được chuyển thẳng đến writer. Không cần tạo một processor chỉ để trả lại nguyên item.

## 7. Ví dụ: đọc CSV, chuyển đổi và ghi vào database

Giả sử file đầu vào có nội dung:

```csv
order_id,customer_id,amount
O-001,C-101,250000
O-002,C-102,180000
O-003,C-103,99000
```

Ứng dụng cần đọc từng dòng thành `OrderInput`, kiểm tra số tiền và chuyển thành `Order`, sau đó ghi vào bảng `orders`.

Để minh họa kiểu dữ liệu, có thể dùng hai record:

```java
public record OrderInput(
        String orderId,
        String customerId,
        BigDecimal amount) {
}

public record Order(
        String orderId,
        String customerId,
        BigDecimal amount) {
}
```

### Cấu hình reader

`FlatFileItemReader` đọc file theo dòng và ánh xạ các cột thành `OrderInput`:

```java
@Bean
@StepScope
FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .linesToSkip(1)
            .delimited()
            .names("orderId", "customerId", "amount")
            .fieldSetMapper(fieldSet -> new OrderInput(
                    fieldSet.readString("orderId"),
                    fieldSet.readString("customerId"),
                    fieldSet.readBigDecimal("amount")))
            .saveState(true)
            .build();
}
```

`@StepScope` cho phép reader nhận đường dẫn file từ JobParameters khi step execution được tạo. `saveState(true)` cho phép reader lưu trạng thái đọc để hỗ trợ restart. File đầu vào nên bất biến trong suốt vòng đời xử lý và restart.

### Cấu hình processor

Processor kiểm tra số tiền và chuyển đối tượng đầu vào thành đối tượng dùng để ghi:

```java
@Bean
ItemProcessor<OrderInput, Order> orderProcessor() {
    return input -> {
        if (input.amount() == null || input.amount().signum() <= 0) {
            throw new InvalidOrderException(
                    "Invalid amount for order " + input.orderId());
        }

        return new Order(
                input.orderId(),
                input.customerId(),
                input.amount());
    };
}
```

Ví dụ này ném exception khi dữ liệu không hợp lệ. Step có thể được cấu hình skip policy nếu nghiệp vụ cho phép bỏ qua những bản ghi thuộc loại lỗi đó. Nếu nghiệp vụ coi bản ghi đó là trường hợp cần lọc bình thường, processor có thể trả về `null` thay vì ném exception.

### Cấu hình writer

Writer dùng `JdbcBatchItemWriter` để ghi từng chunk vào bảng database:

```java
@Bean
JdbcBatchItemWriter<Order> orderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("""
                    INSERT INTO orders (order_id, customer_id, amount)
                    VALUES (:orderId, :customerId, :amount)
                    """)
            .itemSqlParameterSourceProvider(order ->
                    new MapSqlParameterSource()
                            .addValue("orderId", order.orderId())
                            .addValue("customerId", order.customerId())
                            .addValue("amount", order.amount()))
            .build();
}
```

Writer nhận các `Order` đã được processor chuyển đổi và thực hiện batch insert. Trong ví dụ, `order_id` cần có ràng buộc duy nhất phù hợp với nghiệp vụ hoặc writer cần được thiết kế theo cách ghi idempotent nếu có khả năng chạy lại cùng dữ liệu.

### Ghép các thành phần

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

Đây là cấu hình minh họa theo API Spring Batch 5 trở lên. Các class exception, import, schema database và bean hạ tầng như JobRepository, transaction manager, DataSource cần được khai báo phù hợp trong ứng dụng.

## 8. Xử lý lỗi bằng skip và retry

Reader, processor hoặc writer đều có thể phát sinh exception. Spring Batch cho phép cấu hình chính sách lỗi ở step để quyết định khi nào retry, khi nào skip và khi nào kết thúc step với trạng thái thất bại.

Ví dụ, nếu một số đơn hàng có dữ liệu không hợp lệ và nghiệp vụ cho phép bỏ qua tối đa 20 bản ghi loại đó:

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

Khi exception thuộc loại được cấu hình skip, Spring Batch ghi nhận item bị bỏ qua và tiếp tục theo chính sách của step. Khi vượt giới hạn skip, step thất bại. Trong ứng dụng thực tế, nên đăng ký listener hoặc cơ chế ghi nhận lỗi để lưu mã đơn hàng, nguyên nhân và dữ liệu cần điều tra.

Retry phù hợp với một số lỗi tạm thời, chẳng hạn lỗi kết nối có thể phục hồi. Ví dụ cấu hình có thể dùng `.retry(TransientDataAccessException.class).retryLimit(3)`. Tuy nhiên, retry sẽ khiến thao tác có thể được thực hiện lại, vì vậy writer và các tích hợp bên ngoài cần an toàn khi lặp.

Không nên skip mọi exception. Lỗi hệ thống như mất kết nối database thường cần retry hoặc làm step thất bại để xử lý sau, còn lỗi dữ liệu nghiệp vụ có thể được skip nếu có quy trình ghi nhận và đối soát.

## 9. Chunk size ảnh hưởng đến reader, processor và writer

Chunk size được cấu hình trong step, ví dụ `.chunk(100, transactionManager)`. Giá trị này ảnh hưởng đến số item gom vào một chu kỳ ghi và commit.

| Chunk size | Đặc điểm thường gặp |
|---:|---|
| Nhỏ | Giao dịch ngắn và ít item trong bộ nhớ, nhưng có thể tăng số lần commit và chi phí gọi writer. |
| Vừa phải | Cân bằng giữa chi phí commit, bộ nhớ và thông lượng trong nhiều trường hợp. |
| Lớn | Có thể giảm số lần commit, nhưng tăng lượng dữ liệu trong một giao dịch, bộ nhớ sử dụng và thời gian rollback. |

Không có chunk size tối ưu cho mọi ứng dụng. Cần cân nhắc kích thước item, tốc độ nguồn, khả năng batch của đích, giới hạn bộ nhớ, thời gian transaction và yêu cầu phục hồi.

Ví dụ, nếu processor lọc 10 trong 100 item, writer chỉ nhận các item còn lại. Chunk size vẫn điều khiển chu kỳ xử lý dựa trên item đầu vào, không phải cam kết writer luôn nhận đúng 100 item.

## 10. Restart và ExecutionContext

Khả năng restart phụ thuộc vào việc Spring Batch và các thành phần đọc/ghi có thể lưu và khôi phục trạng thái phù hợp hay không.

Một số reader và writer triển khai `ItemStream`, cho phép lưu trạng thái vào `ExecutionContext`. Với reader file, trạng thái có thể bao gồm vị trí đọc. Với writer file, trạng thái có thể bao gồm vị trí ghi hoặc thông tin cần thiết để tiếp tục file.

Trong chunk processing, trạng thái thường được cập nhật tại ranh giới commit. Nếu chunk chưa commit bị rollback, các item thuộc chunk đó có thể được đọc và xử lý lại. Nếu reader không lưu trạng thái hoặc nguồn dữ liệu không thể khôi phục, ứng dụng cần một chiến lược khác.

Một số điểm cần lưu ý:

- Dùng tên reader ổn định để metadata checkpoint được liên kết nhất quán.
- Không thay nội dung file đầu vào giữa lần chạy đầu và lần restart nếu identity vẫn chỉ ra cùng một file logic.
- Với reader tự viết, triển khai `ItemStream` nếu cần lưu trạng thái restart.
- `saveState(false)` có thể vô hiệu hóa lưu trạng thái của reader hỗ trợ tùy chọn này; chỉ dùng khi hiểu rõ hệ quả.
- Không lưu toàn bộ dữ liệu lớn vào ExecutionContext; chỉ lưu metadata nhỏ cần khôi phục.
- Thiết kế writer có thể chịu được việc ghi lại dữ liệu nếu có tình huống retry hoặc tác dụng phụ ngoài transaction.

## 11. Thread safety và xử lý song song

Một số reader hoặc writer giữ trạng thái nội bộ như cursor, vị trí file, bộ đếm hoặc buffer. Không phải implementation nào cũng an toàn khi nhiều thread gọi đồng thời.

Khi dùng multi-threaded step hoặc chia partition, cần kiểm tra tài liệu của reader/writer đang dùng:

- Reader có hỗ trợ nhiều thread hay cần được đồng bộ hóa?
- Mỗi partition có được cấp một reader riêng và phạm vi dữ liệu riêng không?
- Writer có thể nhận nhiều chunk đồng thời mà không làm sai dữ liệu không?
- ExecutionContext và tài nguyên file/database có được tách theo step execution không?
- Thứ tự item có cần được bảo toàn không?

`SynchronizedItemStreamReader` có thể hỗ trợ đồng bộ lời gọi đọc với một reader không thread-safe trong một số cấu hình. Tuy nhiên, đồng bộ hóa không tự giải quyết mọi vấn đề về thứ tự, checkpoint hoặc restart khi xử lý song song. Partitioning với tài nguyên và phạm vi dữ liệu riêng thường là cách rõ ràng hơn khi cần chia công việc.

## 12. Kiểm thử riêng từng thành phần

Việc tách reader, processor và writer giúp có thể kiểm thử chúng độc lập trước khi kiểm thử toàn step.

### Kiểm thử reader

- Cung cấp nguồn dữ liệu nhỏ có nội dung xác định.
- Gọi `read()` nhiều lần và kiểm tra item theo đúng thứ tự mong đợi.
- Kiểm tra lần gọi sau item cuối trả về `null`.
- Kiểm tra cách xử lý file rỗng, dòng sai định dạng và tài nguyên không tồn tại.
- Nếu hỗ trợ restart, kiểm tra trạng thái được lưu và khôi phục đúng.

### Kiểm thử processor

- Kiểm tra đầu vào hợp lệ được chuyển đổi đúng.
- Kiểm tra dữ liệu biên và quy tắc nghiệp vụ.
- Kiểm tra trường hợp trả về `null` để filter.
- Kiểm tra exception được ném ra với loại dữ liệu lỗi cần xử lý.
- Nếu processor gọi service, kiểm tra cách xử lý kết quả và lỗi từ service.

### Kiểm thử writer

- Truyền một chunk nhỏ và xác nhận dữ liệu được ghi đúng đích.
- Kiểm tra chunk rỗng nếu implementation có thể nhận trường hợp đó.
- Kiểm tra lỗi khi ghi và hành vi transaction/rollback ở integration test.
- Kiểm tra writer có xử lý an toàn khi nhận lại dữ liệu đã ghi hay không.

Spring Batch Test có thể hỗ trợ chạy toàn step hoặc job với dữ liệu test. Unit test từng thành phần giúp xác định lỗi nằm ở ánh xạ dữ liệu, quy tắc xử lý hay thao tác ghi; integration test xác nhận các thành phần hoạt động đúng khi được Spring Batch điều phối.

## 13. Các lỗi thường gặp khi triển khai ba thành phần

| Vấn đề | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Step dừng ngay khi reader trả về `null` | `null` là tín hiệu hết dữ liệu theo hợp đồng ItemReader. | Không trả `null` để biểu diễn một bản ghi có trường rỗng. |
| Item không đến writer | Processor trả về `null` và Spring Batch filter item đó. | Kiểm tra điều kiện filter; nếu cần ghi nhận lỗi, dùng exception và skip policy phù hợp. |
| Writer nhận ít item hơn chunk size | Một số item bị filter hoặc chunk cuối không đủ kích thước. | Đây là hành vi bình thường; không giả định writer luôn nhận đúng chunk size. |
| Dữ liệu bị ghi trùng sau restart | Writer có tác dụng phụ không idempotent hoặc thao tác ngoài transaction. | Dùng khóa nghiệp vụ, idempotency key hoặc cơ chế đối soát. |
| Reader đọc lại item sau lỗi | Chunk rollback hoặc step restart làm item chưa commit được xử lý lại. | Thiết kế reader có trạng thái phù hợp và xử lý lại an toàn. |
| Restart đọc sai vị trí | Reader không lưu checkpoint hoặc nguồn đầu vào đã thay đổi. | Dùng reader hỗ trợ ItemStream và giữ nguồn dữ liệu bất biến. |
| Bộ nhớ tăng cao | Reader tải toàn bộ dữ liệu hoặc chunk quá lớn. | Dùng streaming/paging và chọn chunk size phù hợp. |
| Thứ tự dữ liệu thay đổi khi chạy song song | Nhiều thread xử lý item đồng thời. | Xác định yêu cầu thứ tự; cân nhắc partitioning hoặc xử lý tuần tự khi cần. |
| Writer chậm | Ghi từng item bằng nhiều round trip hoặc thiếu batch operation. | Dùng batch writer, tối ưu SQL và kiểm tra index/transaction. |

## 14. Cách đọc code một chunk-oriented step

Khi gặp một step trong dự án, hãy lần theo ba thành phần theo thứ tự:

1. **Tìm reader:** xác định nguồn dữ liệu, cách phân trang/streaming, kiểu item và tham số đầu vào.
2. **Tìm processor:** xác định quy tắc kiểm tra, chuyển đổi, làm giàu hoặc filter dữ liệu.
3. **Tìm writer:** xác định đích ghi, cách ghi theo chunk và tài nguyên transaction được sử dụng.
4. **Đọc chunk size:** hiểu số item được gom trong một chu kỳ xử lý và commit.
5. **Kiểm tra fault tolerance:** xem skip, retry, rollback và listener liên quan.
6. **Kiểm tra restart:** xác định reader/writer có hỗ trợ ItemStream, trạng thái nào được lưu trong ExecutionContext và dữ liệu đầu vào có ổn định không.
7. **Kiểm tra concurrency:** nếu step chạy song song, xác định các thành phần có thread-safe và tài nguyên có được phân vùng phù hợp không.

Khi đã hiểu luồng read-process-write, có thể lần ngược lên Job để xem step được chạy ở đâu, JobParameters cung cấp đầu vào nào và JobRepository lưu trạng thái ra sao.

## 15. Những điểm cần ghi nhớ

- `ItemReader` đọc và trả về từng item; trả `null` khi hết dữ liệu.
- `ItemProcessor` nhận một item, có thể chuyển đổi kiểu dữ liệu và trả `null` để filter.
- `ItemWriter` nhận một chunk các item đã xử lý và ghi chúng đến đích.
- Processor là tùy chọn; reader có thể nối trực tiếp với writer nếu không cần xử lý trung gian.
- Chunk size điều khiển số item đầu vào trong một chu kỳ xử lý, không bảo đảm writer luôn nhận đúng số item đó.
- Trong Spring Batch 5, `ItemWriter.write` nhận `Chunk`; code Spring Batch 4 có thể dùng `List`.
- Filter bằng `null` khác với skip do exception; hãy chọn cơ chế phù hợp với ý nghĩa nghiệp vụ.
- Reader/writer hỗ trợ `ItemStream` có thể lưu checkpoint trong `ExecutionContext` để hỗ trợ restart.
- Rollback và restart có thể khiến item được xử lý lại; writer và tích hợp bên ngoài cần tính idempotent phù hợp.
- Kiểm tra thread safety khi dùng multi-threaded step hoặc partitioning.

Khi thiết kế chunk-oriented step, hãy giữ reader tập trung vào việc lấy dữ liệu, processor tập trung vào quy tắc xử lý từng item và writer tập trung vào việc ghi chunk. Sự phân chia này giúp ứng dụng dễ thay đổi nguồn hoặc đích dữ liệu, dễ kiểm thử, kiểm soát lỗi và phục hồi sau khi execution thất bại.
