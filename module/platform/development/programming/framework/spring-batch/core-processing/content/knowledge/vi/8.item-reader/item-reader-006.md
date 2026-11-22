# Reader từ file, database và resource

Trong Spring Batch, `ItemReader<T>` là thành phần cung cấp từng item đầu vào cho một chunk-oriented step. Dữ liệu có thể đến từ file văn bản, cơ sở dữ liệu, XML, hoặc một tài nguyên được Spring biểu diễn qua abstraction `Resource`. Việc chọn reader phù hợp ảnh hưởng trực tiếp đến hiệu năng, cách quản lý tài nguyên, khả năng restart và độ ổn định của job.

Spring Batch cung cấp nhiều reader triển khai sẵn. Thay vì tự viết vòng lặp đọc file hoặc truy vấn database trong một tasklet, ứng dụng có thể chọn reader phù hợp rồi ghép nó với `ItemProcessor` và `ItemWriter`. Framework sẽ điều phối việc đọc theo chunk, quản lý giao dịch và lưu trạng thái thực thi.

## 1. Vai trò và hợp đồng của ItemReader

Interface cốt lõi có dạng:

```java
public interface ItemReader<T> {
    T read() throws Exception;
}
```

Mỗi lần Spring Batch gọi `read()`, reader trả về một item tiếp theo. Khi không còn dữ liệu, reader trả về `null` để báo kết thúc input. `null` là tín hiệu điều khiển của hợp đồng reader; không dùng nó để biểu diễn một bản ghi có trường dữ liệu rỗng.

Ví dụ, reader đơn hàng có thể trả về lần lượt:

```text
read() -> OrderInput("O-001", "C-101", 250000)
read() -> OrderInput("O-002", "C-102", 180000)
read() -> OrderInput("O-003", "C-103", 99000)
read() -> null
```

Reader thường tập trung vào việc lấy dữ liệu và ánh xạ cấu trúc nguồn thành item. Các quy tắc nghiệp vụ như kiểm tra số tiền, phân loại đơn hàng hoặc tính thuế thường thuộc `ItemProcessor`.

Một số reader còn triển khai `ItemStream` để quản lý vòng đời tài nguyên và trạng thái restart. Các callback quan trọng gồm `open`, `update` và `close`: mở tài nguyên/khôi phục trạng thái, ghi checkpoint vào `ExecutionContext`, và giải phóng tài nguyên.

## 2. Resource là gì trong Spring?

`Resource` là abstraction của Spring dùng để mô tả một tài nguyên đầu vào. Nó giúp code không phải phụ thuộc cứng vào một kiểu vị trí cụ thể như đường dẫn file trên máy. Một `Resource` có thể đại diện cho file trong filesystem, file trên classpath, URL hoặc dữ liệu nằm trong bộ nhớ.

Các implementation thường gặp:

| Resource | Cách xác định tài nguyên | Trường hợp sử dụng |
|---|---|---|
| `FileSystemResource` | Đường dẫn file trên filesystem | File đầu vào được tải lên hoặc đặt trong thư mục dữ liệu. |
| `ClassPathResource` | Tài nguyên nằm trong classpath của ứng dụng | File cấu hình hoặc dữ liệu mẫu được đóng gói cùng ứng dụng. |
| `UrlResource` | URL như HTTP hoặc một giao thức được hỗ trợ | Tài nguyên có địa chỉ URL; cần cân nhắc tính ổn định và khả năng truy cập lại. |
| `ByteArrayResource` | Mảng byte trong bộ nhớ | Dữ liệu nhỏ đã có sẵn trong bộ nhớ. |
| `InputStreamResource` | Một InputStream đã được cung cấp | Luồng dữ liệu do thành phần khác tạo; thường chỉ đọc được một lần. |

`Resource` mô tả nơi lấy dữ liệu; bản thân nó không phải là một `ItemReader`. Ví dụ, `FlatFileItemReader` sử dụng một `Resource` để mở file và đọc từng dòng.

Ví dụ tạo resource:

```java
Resource fileResource = new FileSystemResource("data/orders.csv");
Resource classpathResource = new ClassPathResource("samples/orders.csv");
```

Với tài nguyên classpath, ứng dụng thường chỉ đọc được; không nên giả định có thể ghi đè tài nguyên đã đóng gói trong JAR. Với file đầu vào do người dùng tải lên, `FileSystemResource` hoặc một resource tương ứng với vùng lưu trữ bền vững thường phù hợp hơn.

### Resource và khả năng mở lại stream

Reader có thể cần mở lại tài nguyên khi restart hoặc khi framework khởi tạo lại step. Vì vậy, loại Resource cần hỗ trợ việc mở stream theo cách phù hợp. `InputStreamResource` thường đại diện cho một stream đã có sẵn và không thể mở lại nhiều lần. Nếu cần restart, nên dùng một resource có thể mở lại như `FileSystemResource`, hoặc tự thiết kế cơ chế lưu và khôi phục nguồn dữ liệu.

Với `UrlResource`, cần cân nhắc URL có thể thay đổi nội dung hoặc tạm thời không truy cập được hay không. Một job đọc trực tiếp từ URL có thể gặp nội dung khác khi restart. Đối với dữ liệu quan trọng, cách an toàn hơn thường là tải về vùng lưu trữ bất biến, xác định batch/file ID rồi xử lý từ bản lưu đó.

## 3. Đọc file văn bản bằng FlatFileItemReader

`FlatFileItemReader<T>` là reader phổ biến để đọc file văn bản theo từng dòng. Nó có thể dùng line mapper để chuyển một dòng thành object Java. Với CSV hoặc file có ký tự phân cách, builder hỗ trợ khai báo tên cột và ánh xạ `FieldSet`.

Giả sử file `orders.csv` có nội dung:

```csv
order_id,customer_id,amount
O-001,C-101,250000
O-002,C-102,180000
O-003,C-103,99000
```

Đối tượng nhận dữ liệu:

```java
public record OrderInput(
        String orderId,
        String customerId,
        BigDecimal amount) {
}
```

Reader có thể được khai báo như sau theo API Spring Batch 5:

```java
@Bean
@StepScope
FlatFileItemReader<OrderInput> orderFileReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderFileReader")
            .resource(new FileSystemResource(inputFile))
            .encoding("UTF-8")
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

Giải thích cấu hình:

- `name`: tên reader ổn định, được dùng để nhận diện trạng thái của stream trong metadata.
- `resource`: tài nguyên chứa file cần đọc.
- `encoding`: bộ mã ký tự dùng để giải mã nội dung file.
- `linesToSkip(1)`: bỏ qua dòng tiêu đề CSV.
- `delimited()`: khai báo dữ liệu có các trường phân cách.
- `names(...)`: tên các cột theo thứ tự xuất hiện.
- `fieldSetMapper(...)`: chuyển từng dòng đã phân tích thành `OrderInput`.
- `saveState(true)`: cho phép lưu trạng thái đọc để hỗ trợ restart.

`@StepScope` cho phép tạo reader khi step execution bắt đầu và lấy giá trị `inputFile` từ JobParameters bằng late binding. Nếu đường dẫn file thay đổi theo từng lần chạy, không nên tạo một singleton reader cố định với giá trị chỉ biết tại runtime.

### Các tùy chọn hữu ích của FlatFileItemReader

| Tùy chọn | Ý nghĩa |
|---|---|
| `encoding` | Chọn encoding, ví dụ UTF-8. |
| `linesToSkip` | Bỏ qua một số dòng đầu, thường là header. |
| `comments` | Khai báo tiền tố của các dòng comment cần bỏ qua. |
| `strict` | Quy định cách xử lý khi resource không tồn tại hoặc không thể mở theo cấu hình. |
| `saveState` | Bật hoặc tắt lưu trạng thái để restart. |
| `recordSeparatorPolicy` | Điều khiển cách nhận diện ranh giới record, hữu ích với record nhiều dòng. |
| `lineMapper` | Ánh xạ một dòng thành object, có thể kết hợp tokenizer và field set mapper. |

Khi dữ liệu có dấu phẩy bên trong chuỗi được đặt trong dấu ngoặc kép, cần cấu hình tokenizer phù hợp với định dạng CSV thực tế. Không nên tách chuỗi bằng `String.split(",")` vì cách đơn giản đó không xử lý đầy đủ dấu ngoặc kép, ký tự escape và trường rỗng.

### Xử lý lỗi file và dòng dữ liệu

File có thể không tồn tại, sai encoding, thiếu cột hoặc có giá trị không chuyển đổi được. `FlatFileItemReader` có thể phát sinh exception liên quan đến mở resource hoặc phân tích dòng, ví dụ `FlatFileParseException`.

Nên phân biệt lỗi nguồn và lỗi nghiệp vụ:

- File không tồn tại hoặc không thể mở thường là lỗi đầu vào/hạ tầng cần làm job thất bại.
- Dòng không đúng cấu trúc có thể được skip nếu nghiệp vụ cho phép và có cơ chế lưu lỗi.
- Dòng có cấu trúc hợp lệ nhưng vi phạm quy tắc nghiệp vụ thường được kiểm tra ở processor.

Không nên skip mọi lỗi đọc file. Nếu file bị cắt cụt hoặc encoding sai, tiếp tục xử lý có thể tạo kết quả thiếu dữ liệu mà không được phát hiện.

## 4. Đọc nhiều file bằng MultiResourceItemReader

Khi một job cần đọc nhiều file cùng định dạng, `MultiResourceItemReader<T>` có thể lần lượt cấp từng resource cho một reader delegate. Ví dụ, thư mục chứa các file đơn hàng theo ngày hoặc theo phân vùng.

```text
orders-001.csv --+
orders-002.csv --+--> MultiResourceItemReader
orders-003.csv --+           |
                             v
                     FlatFileItemReader
                             |
                             v
                       từng OrderInput
```

Ví dụ cấu hình với một tập resource đã được phân giải:

```java
@Bean
MultiResourceItemReader<OrderInput> multiOrderReader(
        Resource[] orderFiles,
        FlatFileItemReader<OrderInput> orderFileDelegate) {

    return new MultiResourceItemReaderBuilder<OrderInput>()
            .name("multiOrderReader")
            .resources(orderFiles)
            .delegate(orderFileDelegate)
            .build();
}
```

`orderFiles` có thể được tạo từ `PathMatchingResourcePatternResolver`, cấu hình ứng dụng hoặc một thành phần chuẩn bị input. `FlatFileItemReader` delegate chịu trách nhiệm đọc nội dung từng file. `MultiResourceItemReader` quản lý thứ tự các resource và trạng thái chuyển từ file này sang file khác.

Thứ tự resource cần ổn định giữa lần chạy đầu và lần restart. Nếu danh sách file thay đổi hoặc thứ tự bị thay đổi trong lúc job đang xử lý, checkpoint có thể không còn trỏ đến cùng một tập dữ liệu. Nên chốt danh sách file cho một batch, sắp xếp theo quy tắc xác định và giữ nguyên các file đó cho đến khi job kết thúc.

Nếu mỗi file có header, delegate cần được cấu hình bỏ qua header cho từng resource. Đồng thời, cần bảo đảm reader delegate hỗ trợ resource-aware lifecycle để nhận đúng resource hiện tại.

## 5. Đọc XML từ resource bằng StaxEventItemReader

Khi nguồn là XML, `StaxEventItemReader<T>` có thể đọc các phần tử XML theo kiểu streaming. Reader dùng StAX để xử lý từng fragment thay vì tải toàn bộ tài liệu XML vào bộ nhớ.

Ví dụ XML:

```xml
<orders>
    <order>
        <orderId>O-001</orderId>
        <customerId>C-101</customerId>
        <amount>250000</amount>
    </order>
    <order>
        <orderId>O-002</orderId>
        <customerId>C-102</customerId>
        <amount>180000</amount>
    </order>
</orders>
```

Reader có thể được cấu hình để lấy từng phần tử `order` làm fragment và dùng `Unmarshaller` chuyển fragment thành object:

```java
@Bean
@StepScope
StaxEventItemReader<OrderXml> orderXmlReader(
        @Value("#{jobParameters['inputFile']}") String inputFile,
        Unmarshaller orderUnmarshaller) {

    return new StaxEventItemReaderBuilder<OrderXml>()
            .name("orderXmlReader")
            .resource(new FileSystemResource(inputFile))
            .addFragmentRootElements("order")
            .unmarshaller(orderUnmarshaller)
            .saveState(true)
            .build();
}
```

`Unmarshaller` cần được cấu hình để ánh xạ fragment XML thành kiểu `OrderXml`. Với XML lớn, streaming giúp giảm nhu cầu giữ toàn bộ document trong bộ nhớ. Cần kiểm tra cấu trúc namespace, tên fragment, encoding và cách xử lý XML không hợp lệ.

## 6. Đọc database bằng JdbcCursorItemReader

`JdbcCursorItemReader<T>` dùng JDBC cursor để đọc kết quả truy vấn theo hướng tiến. Reader mở một `ResultSet`, mỗi lần `read()` lấy hàng tiếp theo rồi ánh xạ thành object Java.

Ví dụ bảng `orders` có các cột `order_id`, `customer_id`, `amount` và `status`. Reader có thể lấy các đơn hàng đang chờ xử lý:

```java
@Bean
JdbcCursorItemReader<OrderInput> orderCursorReader(DataSource dataSource) {
    return new JdbcCursorItemReaderBuilder<OrderInput>()
            .name("orderCursorReader")
            .dataSource(dataSource)
            .sql("""
                    SELECT order_id, customer_id, amount
                    FROM orders
                    WHERE status = ?
                    ORDER BY order_id
                    """)
            .preparedStatementSetter(
                    ps -> ps.setString(1, "READY"))
            .rowMapper((rs, rowNum) -> new OrderInput(
                    rs.getString("order_id"),
                    rs.getString("customer_id"),
                    rs.getBigDecimal("amount")))
            .fetchSize(500)
            .saveState(true)
            .build();
}
```

Các thành phần chính:

- `dataSource`: datasource dùng để tạo kết nối JDBC.
- `sql`: câu truy vấn lấy dữ liệu.
- `preparedStatementSetter`: gán giá trị cho các tham số SQL.
- `rowMapper`: ánh xạ mỗi hàng ResultSet thành object.
- `fetchSize`: gợi ý cho JDBC driver về số hàng lấy theo từng đợt; hành vi cụ thể phụ thuộc driver và database.
- `saveState`: cho phép lưu vị trí đọc để hỗ trợ restart.

### Ưu điểm và giới hạn của cursor reader

Cursor reader có thể đọc tập kết quả lớn mà không cần tải tất cả hàng vào một collection trong ứng dụng. Nó phù hợp với truy vấn có thứ tự ổn định và khi database/driver hỗ trợ cursor hiệu quả.

Tuy nhiên, cursor thường giữ ResultSet và kết nối trong suốt thời gian đọc. Với job chạy lâu, điều này có thể giữ một connection trong thời gian dài và ảnh hưởng đến pool hoặc giới hạn tài nguyên của database. Cần hiểu cách driver xử lý fetch size, transaction và cursor; một số driver yêu cầu cấu hình transaction hoặc fetch size đặc thù để streaming thực sự có hiệu quả.

`ORDER BY` nên có thứ tự ổn định. Nếu nhiều hàng có cùng giá trị sắp xếp, nên bổ sung khóa duy nhất làm tiêu chí phụ để kết quả có thứ tự xác định. Điều này đặc biệt quan trọng khi cần checkpoint và restart.

## 7. Đọc database theo trang bằng JdbcPagingItemReader

`JdbcPagingItemReader<T>` chia truy vấn thành nhiều trang (page). Mỗi lần lấy một trang, reader thực hiện truy vấn phân trang và ánh xạ các hàng thành item. Cách này tránh phải giữ một cursor mở trong suốt toàn bộ thời gian đọc.

Ví dụ:

```java
@Bean
JdbcPagingItemReader<OrderInput> orderPagingReader(DataSource dataSource) {
    return new JdbcPagingItemReaderBuilder<OrderInput>()
            .name("orderPagingReader")
            .dataSource(dataSource)
            .selectClause("select order_id, customer_id, amount")
            .fromClause("from orders")
            .whereClause("where status = :status")
            .parameterValues(Map.of("status", "READY"))
            .sortKeys(Map.of("order_id", Order.ASCENDING))
            .rowMapper((rs, rowNum) -> new OrderInput(
                    rs.getString("order_id"),
                    rs.getString("customer_id"),
                    rs.getBigDecimal("amount")))
            .pageSize(500)
            .saveState(true)
            .build();
}
```

Paging reader cần biết cách phân trang phù hợp với database. Spring Batch sử dụng `PagingQueryProvider` để tạo truy vấn tương ứng với hệ quản trị cơ sở dữ liệu được cấu hình. Các phần select, from, where và sort key xác định tập dữ liệu cũng như thứ tự trang.

### Sort key phải ổn định

Sort key là yếu tố quan trọng của paging. Nên chọn một khóa duy nhất hoặc một tổ hợp khóa tạo ra thứ tự duy nhất. Nếu sort key không duy nhất, các hàng có cùng giá trị có thể bị lặp hoặc bỏ sót ở ranh giới trang, tùy cách database phân trang.

Ngoài ra, nếu dữ liệu nguồn thay đổi trong lúc job đang chạy, một hàng có thể chuyển vào hoặc ra khỏi điều kiện truy vấn, làm thay đổi vị trí phân trang. Với job cần kết quả nhất quán, nên xử lý trên một snapshot hoặc giới hạn dữ liệu bằng mốc thời gian/batch ID cố định, và tránh để tập dữ liệu nguồn biến động ngoài dự kiến trong quá trình chạy.

### Page size và fetch size

`pageSize` là số item reader lấy trong một trang. `fetchSize` là gợi ý ở tầng JDBC về số hàng driver lấy mỗi lần fetch. Hai khái niệm có liên quan đến hiệu năng nhưng không đồng nghĩa. Page size ảnh hưởng số item mỗi truy vấn phân trang trả về; fetch size phụ thuộc cách driver truyền hàng từ database về ứng dụng.

## 8. Các reader database khác

Ngoài JDBC cursor và paging, Spring Batch còn có reader cho JPA và Spring Data.

| Reader | Cách hoạt động | Khi cân nhắc sử dụng |
|---|---|---|
| `JpaPagingItemReader` | Dùng EntityManager và truy vấn JPQL để đọc entity theo trang. | Khi ứng dụng đã dùng JPA và cần xử lý entity theo trang. |
| `RepositoryItemReader` | Gọi phương thức repository có hỗ trợ paging/sorting. | Khi muốn tái sử dụng Spring Data repository và truy vấn được biểu diễn phù hợp qua repository method. |
| `JdbcCursorItemReader` | Đọc tuần tự từ JDBC ResultSet cursor. | Khi cần streaming theo cursor và có thể quản lý connection/cursor lâu dài. |
| `JdbcPagingItemReader` | Chạy truy vấn phân trang theo sort key. | Khi muốn đọc theo trang và tránh giữ cursor mở lâu. |

Ví dụ `RepositoryItemReader`:

```java
@Bean
RepositoryItemReader<OrderEntity> repositoryOrderReader(
        OrderRepository orderRepository) {

    return new RepositoryItemReaderBuilder<OrderEntity>()
            .name("repositoryOrderReader")
            .repository(orderRepository)
            .methodName("findByStatus")
            .arguments(List.of(OrderStatus.READY))
            .sorts(Map.of("id", Sort.Direction.ASC))
            .pageSize(500)
            .saveState(true)
            .build();
}
```

Repository cần có phương thức tương thích với paging, ví dụ `Page<OrderEntity> findByStatus(OrderStatus status, Pageable pageable)`. Tên property dùng trong `sorts` phải là property hợp lệ của entity. Thứ tự nên ổn định và có khóa duy nhất.

Ví dụ `JpaPagingItemReader`:

```java
@Bean
JpaPagingItemReader<OrderEntity> jpaOrderReader(
        EntityManagerFactory entityManagerFactory) {

    return new JpaPagingItemReaderBuilder<OrderEntity>()
            .name("jpaOrderReader")
            .entityManagerFactory(entityManagerFactory)
            .queryString("select o from OrderEntity o " +
                    "where o.status = 'READY' order by o.id")
            .pageSize(500)
            .saveState(true)
            .build();
}
```

JPA paging reader quản lý EntityManager theo vòng đời reader và lấy entity theo từng trang. Cần cân nhắc kích thước trang, persistence context và việc entity được detach/clear theo hành vi reader. Nếu job chỉ cần dữ liệu dạng projection hoặc cần hiệu năng JDBC trực tiếp, JDBC reader có thể phù hợp hơn.

## 9. Đọc từ Resource theo JobParameters

Trong nhiều ứng dụng, vị trí file đầu vào chỉ được biết khi job được yêu cầu chạy. Có thể truyền đường dẫn trong JobParameters và tạo reader theo `@StepScope`.

Ví dụ JobParameters:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "data/inbound/orders.csv", true)
        .addString("businessDate", "2026-11-15", true)
        .toJobParameters();
```

Reader lấy tham số lúc step bắt đầu:

```java
@Bean
@StepScope
FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    Resource resource = new FileSystemResource(inputFile);

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(resource)
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

Ở ví dụ này, tham số `inputFile` vừa được dùng để tạo `Resource`, vừa có thể tham gia xác định JobInstance. Nếu cùng một JobInstance được restart, file phải giữ nội dung tương ứng với lần chạy ban đầu. Đường dẫn giống nhau nhưng nội dung bị thay thế có thể làm checkpoint không còn chính xác.

Nếu cần dùng `ClassPathResource`, có thể tạo resource tương ứng thay cho `FileSystemResource`. Nếu resource được chọn dựa trên loại nguồn đầu vào, có thể đặt logic tạo Resource trong một factory hoặc service nhỏ để reader không phải chứa nhiều nhánh chọn nguồn.

## 10. So sánh file reader và database reader

| Tiêu chí | File reader | Database reader |
|---|---|---|
| Nguồn | CSV, text, XML hoặc file khác | Bảng, view hoặc kết quả truy vấn |
| Ánh xạ | LineMapper, FieldSetMapper, Unmarshaller | RowMapper, JPA mapping hoặc repository method |
| Tài nguyên | File stream, file handle | Connection, ResultSet, EntityManager |
| Phân trang | Thường đọc tuần tự theo dòng/record | Có cursor hoặc paging tùy reader |
| Restart | Dựa vào vị trí đọc và trạng thái resource | Dựa vào số item/trang, query và sort key theo reader |
| Rủi ro thay đổi nguồn | File bị ghi đè hoặc thay đổi giữa các lần chạy | Bảng thay đổi khi job đang phân trang hoặc truy vấn |
| Lỗi thường gặp | Encoding, cấu trúc dòng, thiếu file, sai delimiter | SQL, connection, timeout, lock, sort key không ổn định |

Không có reader nào tốt nhất cho mọi trường hợp. Hãy chọn dựa trên nguồn dữ liệu thực tế, kích thước tập dữ liệu, yêu cầu transaction, restart và cách dữ liệu thay đổi trong thời gian job chạy.

## 11. Restart và checkpoint của reader

Một reader có thể restart khi trạng thái cần thiết để tiếp tục đọc được lưu và khôi phục đúng. Nhiều reader tích hợp triển khai `ItemStream`, do đó Spring Batch có thể lưu checkpoint vào `ExecutionContext` tại ranh giới commit.

Với file reader, checkpoint có thể là vị trí đọc trong file. Với cursor hoặc paging reader, checkpoint có thể liên quan đến số item đã đọc hoặc trạng thái truy vấn. Cách lưu cụ thể tùy implementation.

Để restart đáng tin cậy:

- Dùng tên reader ổn định giữa các lần chạy.
- Bật lưu trạng thái nếu reader hỗ trợ và job cần restart.
- Giữ nguyên file, resource hoặc tập dữ liệu nguồn trong suốt vòng đời JobInstance.
- Với paging, dùng sort key duy nhất và ổn định.
- Với query database, giữ điều kiện lọc và tham số nhất quán giữa lần chạy đầu và restart.
- Không dùng `InputStreamResource` một lần nếu cần mở lại stream.
- Với reader tự viết, triển khai ItemStream để lưu và khôi phục checkpoint.

Restart không có nghĩa là tiếp tục tại đúng câu lệnh Java cuối cùng. Framework tiếp tục từ trạng thái đã lưu. Item trong chunk chưa commit có thể được đọc lại; vì vậy processor và writer cần chịu được việc xử lý lặp.

## 12. Quản lý tài nguyên và transaction

Reader thường mở tài nguyên trong `open` và đóng trong `close`. Khi đọc file, cần giải phóng stream để tránh rò rỉ file handle. Khi đọc database bằng cursor, cần giải phóng ResultSet và connection đúng vòng đời.

Với cursor reader, kết nối có thể được giữ trong thời gian dài. Cần xem xét pool size, transaction manager, isolation level và cách JDBC driver thực hiện fetch. Nếu job chạy lâu, paging reader có thể giảm thời gian giữ cursor, nhưng sẽ phát sinh nhiều truy vấn phân trang.

Reader không nhất thiết ghi dữ liệu, nhưng transaction vẫn có thể ảnh hưởng đến cách reader tương tác với database, ví dụ snapshot dữ liệu, lock hoặc cursor visibility. Hãy chọn transaction manager và isolation level dựa trên yêu cầu nhất quán của batch.

Đối với file, việc đọc file không tự động tham gia giao dịch database. Nếu chunk rollback, Spring Batch có thể khôi phục trạng thái reader có hỗ trợ checkpoint, nhưng nội dung file không được transaction manager database rollback. Với file đầu ra hoặc nhiều tài nguyên, cần dùng cơ chế quản lý riêng để tránh file trung gian ở trạng thái không hoàn chỉnh.

## 13. Hiệu năng và kích thước dữ liệu

Hiệu năng reader phụ thuộc cách lấy dữ liệu và đặc tính của nguồn:

- Với file, dùng streaming reader thay vì đọc toàn bộ file vào một `List`.
- Với JDBC cursor, cấu hình fetch size phù hợp và kiểm tra hành vi của driver.
- Với paging, chọn page size hợp lý và bảo đảm sort key có index nếu truy vấn cần.
- Với JPA, tránh giữ persistence context quá lớn; cân nhắc cách reader quản lý entity theo trang.
- Với repository, kiểm tra SQL thực tế và kế hoạch truy vấn; abstraction repository không tự bảo đảm truy vấn hiệu quả.
- Với nhiều file, dùng `MultiResourceItemReader` và cố định danh sách resource cho batch.

Đừng nhầm lẫn `chunk size`, `pageSize` và JDBC `fetchSize`:

| Giá trị | Điều khiển điều gì? |
|---|---|
| `chunk size` | Số item đầu vào được xử lý trong một chu kỳ ghi/commit của step. |
| `pageSize` | Số item reader phân trang lấy trong một lần truy vấn page. |
| JDBC `fetchSize` | Gợi ý cho driver số hàng lấy từ database mỗi lần fetch. |

Các giá trị này có thể được đặt bằng nhau trong một số trường hợp, nhưng chúng phục vụ những tầng khác nhau. Cần đo thông lượng, thời gian truy vấn, số lần commit và mức sử dụng bộ nhớ để chọn cấu hình phù hợp.

## 14. Các lỗi thường gặp khi dùng reader

| Vấn đề | Nguyên nhân có thể gặp | Hướng xử lý |
|---|---|---|
| Reader không tìm thấy file | Đường dẫn sai, working directory khác hoặc file chưa được chuyển đến. | Kiểm tra JobParameters, resource và thời điểm job được gọi. |
| Đọc sai ký tự tiếng Việt | Encoding của file không khớp cấu hình. | Xác định encoding nguồn và cấu hình `encoding` rõ ràng. |
| CSV bị lệch cột | Tokenizer không xử lý delimiter, quote hoặc escape đúng định dạng. | Dùng tokenizer phù hợp và kiểm tra cấu trúc file thực tế. |
| Restart đọc lại từ đầu | Reader không lưu trạng thái, tên reader thay đổi hoặc trạng thái không được khôi phục. | Dùng reader hỗ trợ ItemStream, tên ổn định và `saveState(true)` khi cần. |
| Restart đọc nhầm nội dung | File cùng đường dẫn bị thay đổi giữa hai lần chạy. | Lưu file bất biến và định danh theo batch/file version. |
| Paging bỏ sót hoặc lặp hàng | Sort key không duy nhất hoặc dữ liệu nguồn thay đổi trong lúc phân trang. | Dùng thứ tự ổn định, khóa duy nhất và tập dữ liệu/snapshot cố định. |
| Cursor giữ connection quá lâu | Cursor mở trong suốt thời gian đọc. | Cân nhắc paging, fetch size, pool và thời gian chạy. |
| InputStream không thể mở lại | Resource chỉ đại diện cho một stream dùng một lần. | Dùng resource có thể mở lại hoặc thiết kế lại cách cung cấp input. |
| Reader tự viết không restart được | Không lưu trạng thái cần thiết vào ExecutionContext. | Triển khai ItemStream và kiểm thử khôi phục checkpoint. |
| Job chạy song song gây lỗi reader | Reader giữ state nội bộ và không thread-safe. | Dùng reader riêng theo partition hoặc cơ chế đồng bộ phù hợp. |

## 15. Chọn reader nào cho từng tình huống?

| Tình huống | Reader thường phù hợp | Lý do |
|---|---|---|
| Đọc một file CSV lớn | `FlatFileItemReader` | Đọc tuần tự, ánh xạ dòng và hỗ trợ checkpoint. |
| Đọc nhiều file cùng định dạng | `MultiResourceItemReader` kết hợp reader delegate | Điều phối nhiều resource theo thứ tự. |
| Đọc XML theo từng phần tử | `StaxEventItemReader` | Streaming theo fragment, tránh tải toàn bộ XML. |
| Truy vấn database theo cursor | `JdbcCursorItemReader` | Đọc tuần tự trên ResultSet. |
| Đọc database theo trang | `JdbcPagingItemReader` | Truy vấn từng trang, không giữ cursor mở xuyên suốt. |
| Đọc entity qua JPA | `JpaPagingItemReader` | Tận dụng JPQL và EntityManager. |
| Đọc qua Spring Data repository | `RepositoryItemReader` | Tái sử dụng repository method có paging/sorting. |
| Đọc file được đóng gói trong ứng dụng | `FlatFileItemReader` với `ClassPathResource` | Dùng classpath resource làm nguồn file. |

Khi chọn, hãy trả lời các câu hỏi: dữ liệu nằm ở đâu, tập dữ liệu lớn đến mức nào, có cần phân trang không, nguồn có thay đổi trong lúc job chạy không, reader có thể restart không, và tài nguyên nào sẽ được giữ trong thời gian dài?

## 16. Cách đọc code reader trong một ứng dụng Spring Batch

Khi gặp một bean reader, hãy lần theo các chi tiết sau:

1. **Kiểu reader:** file, JDBC cursor, JDBC paging, JPA, repository hay XML.
2. **Nguồn dữ liệu:** `Resource`, `DataSource`, `EntityManagerFactory` hoặc repository nào được sử dụng.
3. **Kiểu item:** reader trả về DTO, entity hay object trung gian nào.
4. **Cách ánh xạ:** `FieldSetMapper`, `LineMapper`, `RowMapper`, `Unmarshaller` hoặc repository method.
5. **Tham số runtime:** đường dẫn file, ngày nghiệp vụ, điều kiện SQL hoặc page size có lấy từ JobParameters không.
6. **Trạng thái restart:** tên reader, `saveState`, ItemStream và ExecutionContext.
7. **Tài nguyên:** stream, cursor, connection hoặc EntityManager được mở và đóng như thế nào.
8. **Thứ tự và tính nhất quán:** file có bất biến không, SQL có `ORDER BY` ổn định không, paging có sort key duy nhất không.

Sau khi hiểu reader, tiếp tục xem processor và writer để biết item được biến đổi và lưu ở đâu. Từ đó có thể hiểu đầy đủ luồng chunk processing của step.

## 17. Những điểm cần ghi nhớ

- `ItemReader<T>` trả về một item mỗi lần gọi `read()` và trả `null` khi hết dữ liệu.
- `Resource` là abstraction mô tả vị trí tài nguyên; reader như `FlatFileItemReader` mới là thành phần đọc item.
- `FlatFileItemReader` phù hợp với file văn bản và có thể ánh xạ dòng thành object bằng tokenizer, FieldSetMapper hoặc LineMapper.
- `MultiResourceItemReader` điều phối một reader delegate qua nhiều resource; danh sách và thứ tự file cần ổn định khi restart.
- `StaxEventItemReader` đọc XML theo fragment bằng streaming.
- `JdbcCursorItemReader` đọc tuần tự bằng cursor; cần cân nhắc connection và ResultSet được giữ trong thời gian dài.
- `JdbcPagingItemReader` đọc theo trang; cần sort key ổn định, tốt nhất là duy nhất.
- `JpaPagingItemReader` và `RepositoryItemReader` phù hợp khi ứng dụng dùng JPA hoặc Spring Data.
- `ItemStream`, `ExecutionContext` và `saveState` hỗ trợ lưu checkpoint để restart.
- Resource và tập dữ liệu đầu vào phải ổn định giữa lần chạy đầu và restart.
- Phân biệt chunk size, page size và JDBC fetch size vì chúng điều khiển các tầng khác nhau.

Khi xây dựng reader, hãy chọn implementation dựa trên loại nguồn, kích thước dữ liệu, yêu cầu nhất quán và khả năng restart. Một reader được cấu hình đúng giúp luồng batch đọc dữ liệu ổn định, sử dụng tài nguyên hợp lý và tiếp tục an toàn sau khi execution gặp lỗi.
