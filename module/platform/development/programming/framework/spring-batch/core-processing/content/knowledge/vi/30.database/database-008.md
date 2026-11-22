# ItemPreparedStatementSetter

Trong Spring Batch, `ItemPreparedStatementSetter<T>` là callback dùng để gán giá trị của một item vào các placeholder `?` của JDBC `PreparedStatement`. Nó thường được dùng cùng `JdbcBatchItemWriter` khi muốn kiểm soát tường minh cách từng thuộc tính của object được bind vào câu SQL.

Ví dụ, một `Order` có `orderId`, `customerId` và `amount`. Writer thực thi câu lệnh:

```sql
INSERT INTO orders (order_id, customer_id, amount)
VALUES (?, ?, ?)
```

`ItemPreparedStatementSetter` nhận một `Order` và một `PreparedStatement`, sau đó gọi `setString`, `setBigDecimal` hoặc các phương thức JDBC tương ứng để gán ba giá trị vào vị trí 1, 2 và 3. `JdbcBatchItemWriter` chịu trách nhiệm gom các item thành batch và thực thi batch; setter chỉ ánh xạ dữ liệu cho một item.

Đây là cách binding theo vị trí, phù hợp khi SQL dùng placeholder `?`, cần kiểm soát kiểu JDBC, xử lý `null` rõ ràng hoặc ánh xạ dữ liệu phức tạp. Nếu muốn binding theo tên như `:orderId`, có thể dùng `ItemSqlParameterSourceProvider` hoặc các lựa chọn `beanMapped()`/`columnMapped()` của builder thay vì `ItemPreparedStatementSetter`.

## ItemPreparedStatementSetter là gì?

Interface nằm trong package `org.springframework.batch.item.database` và có hợp đồng đơn giản:

```java
public interface ItemPreparedStatementSetter<T> {

    void setValues(T item, PreparedStatement ps) throws SQLException;
}
```

Hai tham số có ý nghĩa:

- `item`: item hiện tại do writer nhận được, thường là output của `ItemProcessor` hoặc item trực tiếp từ reader nếu không có processor.
- `ps`: `PreparedStatement` mà writer dùng để thực thi câu SQL đã cấu hình.

Method `setValues` được gọi cho từng item trong batch để gán các parameter của item đó. Setter không tự tạo connection, không tự chạy SQL và không commit transaction. Những công việc này thuộc `JdbcBatchItemWriter` cùng JDBC infrastructure của Spring.

### Vị trí trong chunk processing

```text
ItemReader<OrderInput>
        |
        v
ItemProcessor<OrderInput, Order>
        |
        v
Chunk<Order>
        |
        v
JdbcBatchItemWriter<Order>
        |
        +--> SQL: INSERT ... VALUES (?, ?, ?)
        |
        +--> ItemPreparedStatementSetter<Order>
                 |
                 +--> setString(1, orderId)
                 +--> setString(2, customerId)
                 +--> setBigDecimal(3, amount)
        |
        v
JdbcTemplate batchUpdate
        |
        v
Database
```

Reader/processor tạo ra item. Writer lấy từng item, gọi setter để bind parameter và sau đó thực thi batch. Khi step chạy theo chunk, writer thường hoạt động trong transaction của chunk nếu được cấu hình với datasource/transaction manager phù hợp.

## Cấu hình JdbcBatchItemWriter với setter

Ví dụ dưới đây dùng Spring Batch 5 và Java record:

```java
public record Order(
        String orderId,
        String customerId,
        BigDecimal amount) {
}
```

Khai báo writer:

```java
@Bean
JdbcBatchItemWriter<Order> orderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("""
                    INSERT INTO orders (order_id, customer_id, amount)
                    VALUES (?, ?, ?)
                    """)
            .itemPreparedStatementSetter((order, ps) -> {
                ps.setString(1, order.orderId());
                ps.setString(2, order.customerId());
                ps.setBigDecimal(3, order.amount());
            })
            .build();
}
```

Các phần chính:

1. `.dataSource(dataSource)` cung cấp datasource mà writer sử dụng.
2. `.sql(...)` khai báo câu SQL có placeholder JDBC `?`.
3. `.itemPreparedStatementSetter(...)` định nghĩa cách gán parameter cho từng item.
4. `.build()` tạo `JdbcBatchItemWriter` đã được cấu hình.

Builder cũng có thể nhận một instance setter đã được khai báo thành bean:

```java
@Bean
ItemPreparedStatementSetter<Order> orderParameterSetter() {
    return (order, ps) -> {
        ps.setString(1, order.orderId());
        ps.setString(2, order.customerId());
        ps.setBigDecimal(3, order.amount());
    };
}

@Bean
JdbcBatchItemWriter<Order> orderWriter(
        DataSource dataSource,
        ItemPreparedStatementSetter<Order> orderParameterSetter) {

    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("INSERT INTO orders(order_id, customer_id, amount) VALUES (?, ?, ?)")
            .itemPreparedStatementSetter(orderParameterSetter)
            .build();
}
```

Tách setter thành bean giúp tái sử dụng và unit test độc lập. Nếu application có nhiều setter cùng generic type, dùng `@Qualifier` để Spring inject đúng bean.

## Thứ tự placeholder và JDBC parameter index

JDBC đánh số parameter từ **1**, không phải 0. Vị trí trong setter phải khớp thứ tự placeholder trong câu SQL.

```sql
UPDATE orders
SET customer_id = ?, amount = ?, updated_at = ?
WHERE order_id = ?
```

Setter tương ứng:

```java
ItemPreparedStatementSetter<Order> setter = (order, ps) -> {
    ps.setString(1, order.customerId());
    ps.setBigDecimal(2, order.amount());
    ps.setTimestamp(3, Timestamp.valueOf(order.updatedAt()));
    ps.setString(4, order.orderId());
};
```

| Vị trí | Placeholder SQL | Giá trị được bind |
| ---: | --- | --- |
| 1 | `customer_id = ?` | `order.customerId()` |
| 2 | `amount = ?` | `order.amount()` |
| 3 | `updated_at = ?` | `order.updatedAt()` dưới dạng timestamp |
| 4 | `WHERE order_id = ?` | `order.orderId()` |

Nếu gán nhầm thứ tự, SQL vẫn có thể chạy thành công nhưng ghi sai cột. Đây là lỗi nguy hiểm vì không nhất thiết phát sinh exception. Nên giữ câu SQL và setter gần nhau, dùng tên biến rõ ràng và có test xác nhận từng vị trí.

### Mỗi placeholder phải được gán trong mỗi lần gọi

`JdbcBatchItemWriter` tái sử dụng prepared statement cho nhiều item trong batch. Setter cần gán tất cả parameter mà câu SQL yêu cầu mỗi lần được gọi. Không dựa vào giá trị của item trước đó còn nằm trong statement.

Ví dụ không đầy đủ:

```java
// Không nên: khi note null, parameter 3 có thể còn giá trị từ lần bind trước
if (order.note() != null) {
    ps.setString(3, order.note());
}
```

Hãy gán cả trường hợp null:

```java
if (order.note() == null) {
    ps.setNull(3, Types.VARCHAR);
} else {
    ps.setString(3, order.note());
}
```

Điều này bảo đảm mỗi item có một bộ parameter độc lập, đầy đủ và không bị rò giá trị từ item trước.

## Chọn phương thức setter theo kiểu dữ liệu

Ưu tiên phương thức JDBC phù hợp với kiểu SQL để driver nhận đúng kiểu dữ liệu.

| Kiểu Java | Phương thức JDBC thường dùng | Kiểu SQL thường gặp |
| --- | --- | --- |
| `String` | `setString(index, value)` | `VARCHAR`, `CHAR`, `TEXT` tùy driver |
| `Integer` / `int` | `setInt(index, value)` | `INTEGER` |
| `Long` / `long` | `setLong(index, value)` | `BIGINT` |
| `BigDecimal` | `setBigDecimal(index, value)` | `DECIMAL`, `NUMERIC` |
| `Boolean` / `boolean` | `setBoolean(index, value)` | `BOOLEAN` hoặc kiểu tương ứng của database |
| `LocalDate` | `setDate(index, Date.valueOf(value))` | `DATE` |
| `LocalDateTime` | `setTimestamp(index, Timestamp.valueOf(value))` | `TIMESTAMP` |
| `Instant` | `setTimestamp(index, Timestamp.from(value))` | `TIMESTAMP` theo quy ước timezone của ứng dụng |
| `byte[]` | `setBytes(index, value)` | `BINARY`, `VARBINARY`, `BLOB` tùy kích thước/driver |

Ví dụ với kiểu ngày giờ:

```java
ps.setDate(1, Date.valueOf(order.businessDate()));
ps.setTimestamp(2, Timestamp.valueOf(order.createdAt()));
ps.setTimestamp(3, Timestamp.from(order.createdInstant()));
```

`LocalDate` không chứa timezone. `LocalDateTime` cũng không chứa timezone/offset. `Instant` biểu diễn một thời điểm tuyệt đối; cần thống nhất quy ước lưu UTC hoặc timezone của database và driver. Đừng tự chuyển timezone ngầm giữa processor và setter.

### Xử lý null có kiểu

Khi giá trị có thể null, nên dùng `setNull(index, sqlType)` để chỉ rõ SQL type:

```java
if (order.discount() == null) {
    ps.setNull(4, Types.DECIMAL);
} else {
    ps.setBigDecimal(4, order.discount());
}
```

`setObject(index, null)` có thể khiến driver không xác định được SQL type, đặc biệt với database hoặc cột có kiểu đặc thù. `setNull` rõ ràng hơn và giúp code ít phụ thuộc driver.

Nếu cột có kiểu database đặc biệt, dùng `Types` phù hợp hoặc overload `setObject` có SQL type nếu driver hỗ trợ. Kiểm tra schema và driver production, không chỉ dựa trên H2 hoặc database test.

### Enum và kiểu miền nghiệp vụ

Enum thường được lưu dưới dạng chuỗi hoặc mã số. Quyết định mapping phải nhất quán với schema:

```java
ps.setString(1, order.status().name());
```

Nếu database lưu mã như `P`, `C`, `X`, hãy dùng mapper tường minh thay vì `name()`:

```java
ps.setString(1, statusCodeMapper.toCode(order.status()));
```

Không dựa vào `ordinal()` để lưu enum nếu thứ tự enum có thể thay đổi giữa các phiên bản; thêm enum mới ở giữa có thể làm dữ liệu cũ bị diễn giải sai.

## Setter cho INSERT

Với `INSERT`, số placeholder thường bằng số cột cần cung cấp:

```sql
INSERT INTO orders (
    order_id,
    customer_id,
    amount,
    status,
    created_at
)
VALUES (?, ?, ?, ?, ?)
```

Setter:

```java
ItemPreparedStatementSetter<Order> insertOrderSetter = (order, ps) -> {
    ps.setString(1, order.orderId());
    ps.setString(2, order.customerId());
    ps.setBigDecimal(3, order.amount());
    ps.setString(4, order.status().name());
    ps.setTimestamp(5, Timestamp.from(order.createdAt()));
};
```

Nếu database tự sinh primary key, không cần placeholder cho cột đó nếu SQL dùng identity/default. `ItemPreparedStatementSetter` không phải callback lấy generated key và ghi ngược vào item. Nếu cần generated key, hãy dùng cơ chế JDBC generated keys, sequence/returning phù hợp hoặc một bước/service chuyên biệt.

## Setter cho UPDATE

Với `UPDATE`, nhớ gán cả parameter ở phần `SET` lẫn phần `WHERE`:

```sql
UPDATE orders
SET status = ?, updated_at = ?
WHERE order_id = ?
```

```java
ItemPreparedStatementSetter<Order> updateOrderSetter = (order, ps) -> {
    ps.setString(1, order.status().name());
    ps.setTimestamp(2, Timestamp.from(order.updatedAt()));
    ps.setString(3, order.orderId());
};
```

Nếu `WHERE` không khớp bản ghi nào, update count có thể bằng 0. `JdbcBatchItemWriter` mặc định kiểm tra update count và có thể báo lỗi khi một item không cập nhật row nào. Điều này hữu ích khi ứng dụng mong đợi mỗi item phải ảnh hưởng tới ít nhất một row.

Nếu SQL hợp lệ có thể cập nhật 0 row, hãy cân nhắc `assertUpdates(false)` hoặc thay đổi hợp đồng nghiệp vụ. Không tắt kiểm tra chỉ để che lỗi khóa không tồn tại hoặc dữ liệu bị bỏ sót.

## Setter cho SQL có nhiều parameter

Một câu SQL có thể có nhiều parameter, ví dụ insert vào bảng giao dịch:

```sql
INSERT INTO payment_transaction (
    transaction_id,
    order_id,
    amount,
    currency,
    approved,
    processed_at,
    reference_code
)
VALUES (?, ?, ?, ?, ?, ?, ?)
```

```java
ItemPreparedStatementSetter<PaymentTransaction> paymentSetter =
        (payment, ps) -> {
            ps.setString(1, payment.transactionId());
            ps.setString(2, payment.orderId());
            ps.setBigDecimal(3, payment.amount());
            ps.setString(4, payment.currency());
            ps.setBoolean(5, payment.approved());
            ps.setTimestamp(6, Timestamp.from(payment.processedAt()));

            if (payment.referenceCode() == null) {
                ps.setNull(7, Types.VARCHAR);
            } else {
                ps.setString(7, payment.referenceCode());
            }
        };
```

Khi SQL dài, nên căn chỉnh danh sách cột, placeholder và setter theo cùng thứ tự. Có thể thêm comment trong setter để liên hệ vị trí với cột, nhưng tốt nhất vẫn là giữ code dễ đọc và có test.

## Dùng setter trong chunk-oriented step

Writer được gắn vào step như các `ItemWriter` khác:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
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

Với chunk size 100, writer nhận tối đa 100 output item trong một lần ghi (số thực tế có thể ít hơn do cuối input hoặc filtering). `JdbcBatchItemWriter` dùng setter cho từng item và thực thi batch update. Setter không quyết định chunk size và không tự quản lý transaction.

Nếu processor trả `null` để filter item, item đó không tới writer và setter không được gọi cho item đó. Nếu processor ném exception, step xử lý exception theo rollback/retry/skip policy đã cấu hình; setter chỉ chạy cho item được chuyển tới writer.

## ItemPreparedStatementSetter và ItemSqlParameterSourceProvider

Spring Batch cung cấp hai hướng binding phổ biến cho `JdbcBatchItemWriter`:

| Cách binding | SQL placeholder | Cơ chế |
| --- | --- | --- |
| `ItemPreparedStatementSetter<T>` | `?` theo vị trí | Gọi `PreparedStatement.setX(index, value)` |
| `ItemSqlParameterSourceProvider<T>` | Named parameter như `:orderId` | Tạo `SqlParameterSource` cho item |

### Named parameters với beanMapped

Nếu tên property của object khớp tên parameter trong SQL, có thể dùng `beanMapped()`:

```java
@Bean
JdbcBatchItemWriter<Order> namedOrderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("""
                    INSERT INTO orders(order_id, customer_id, amount)
                    VALUES (:orderId, :customerId, :amount)
                    """)
            .beanMapped()
            .build();
}
```

Builder sử dụng property của item để cung cấp named parameter. Cách này ngắn gọn khi object có bean property phù hợp và SQL không cần mapping đặc biệt.

### Named parameters với provider tùy chỉnh

Khi cần mapping theo tên nhưng không muốn dùng property mapping mặc định, có thể cung cấp `ItemSqlParameterSourceProvider` tùy chỉnh. Provider tạo `SqlParameterSource` cho mỗi item.

`ItemPreparedStatementSetter` phù hợp hơn khi:

- SQL đang dùng placeholder vị trí `?`.
- Cần gọi JDBC setter cụ thể cho từng kiểu.
- Mapping có logic đặc thù hoặc cần kiểm soát `Types` của null.
- Muốn code hiển thị chính xác thứ tự parameter.

Named parameter phù hợp hơn khi:

- SQL có nhiều cột và tên parameter giúp dễ đọc.
- Tên property của object khớp với SQL.
- Muốn giảm nguy cơ đảo nhầm vị trí placeholder.
- Team đã chuẩn hóa cách dùng `SqlParameterSource`.

Không trộn `ItemPreparedStatementSetter` và provider cho cùng một writer. Chọn một cơ chế binding nhất quán với SQL.

## ItemPreparedStatementSetter khác PreparedStatementSetter

Hai interface có tên gần giống nhau nhưng phạm vi sử dụng khác:

| Interface | Package | Dữ liệu được bind |
| --- | --- | --- |
| `ItemPreparedStatementSetter<T>` | `org.springframework.batch.item.database` | Một item Spring Batch cho mỗi lần callback |
| `PreparedStatementSetter` | `org.springframework.jdbc.core` | Parameter cho một lần thực thi câu JDBC trong Spring JDBC |

`ItemPreparedStatementSetter` nhận thêm `item`, vì vậy nó có thể được gọi lặp cho từng phần tử trong batch. Nó là adapter ở tầng Spring Batch giúp `JdbcBatchItemWriter` chuyển mỗi item thành parameter set.

Không thay interface này bằng `RowMapper`. `RowMapper` ánh xạ một row kết quả truy vấn thành object; `ItemPreparedStatementSetter` ánh xạ object thành parameter đầu vào cho SQL ghi.

## Setter nên làm gì và không nên làm gì?

Setter nên thực hiện công việc đơn giản, xác định và không có side effect:

- Đọc thuộc tính của item.
- Chuyển kiểu đơn giản nếu cần.
- Gán tất cả parameter vào statement.
- Dùng SQL type phù hợp cho giá trị null.
- Ném `SQLException` nếu JDBC binding thất bại.

Setter không nên:

- Tự gọi `executeUpdate()`, `executeBatch()` hoặc `commit()`.
- Đóng `PreparedStatement` hoặc connection do writer quản lý.
- Tạo connection mới cho từng item.
- Ghi log toàn bộ payload hoặc gọi API bên ngoài.
- Thực hiện truy vấn database khác trong mỗi callback nếu có thể xử lý trước đó.
- Giữ reference tới `PreparedStatement` để dùng sau callback.
- Dùng field mutable để nhớ item trước đó.

`JdbcBatchItemWriter` quản lý việc thực thi batch. Nếu setter tự execute hoặc commit, nó có thể phá vỡ batch lifecycle và transaction boundary của chunk.

## Validation nên nằm ở đâu?

`ItemPreparedStatementSetter` là tầng binding JDBC, không phải nơi lý tưởng để thực hiện validation nghiệp vụ phức tạp.

Ví dụ, nếu `amount` phải lớn hơn 0, nên kiểm tra trong processor hoặc validator:

```java
public Order process(OrderInput input) {
    if (input.amount() == null || input.amount().signum() <= 0) {
        throw new InvalidOrderException("Amount must be positive");
    }

    return new Order(input.orderId(), input.customerId(), input.amount());
}
```

Setter sau đó chỉ bind:

```java
ps.setBigDecimal(3, order.amount());
```

Phân chia trách nhiệm này giúp skip/retry policy phân loại lỗi nghiệp vụ ở tầng processor, còn lỗi JDBC binding được nhận diện là lỗi ghi. Nếu setter phát hiện giá trị null hoặc kiểu không hợp lệ, nó có thể ném exception, nhưng cần cân nhắc rằng lỗi này xảy ra trong giai đoạn writer và ảnh hưởng tới retry/skip semantics khác với validation ở processor.

## SQLException và exception handling

`setValues` khai báo `throws SQLException`. Nếu một lệnh `PreparedStatement.setX(...)` thất bại, exception được truyền về JDBC writer/JdbcTemplate và thường được chuyển thành `DataAccessException` theo exception translation của Spring JDBC.

Các lỗi có thể gặp:

- Kiểu parameter không tương thích với cột.
- Giá trị vượt precision/scale của `DECIMAL`.
- String vượt độ dài cột.
- SQL parameter index không hợp lệ.
- Driver không hỗ trợ kiểu được yêu cầu.
- Connection bị đóng hoặc lỗi JDBC trong lúc thực thi batch.

Không nên catch `SQLException` rồi bỏ qua trong setter. Nếu không thể bind đúng dữ liệu, hãy để lỗi đi lên để Spring Batch áp dụng rollback/retry/skip policy. Nếu muốn chuyển lỗi thành exception nghiệp vụ, cần giữ cause và phân loại rõ ràng.

### Retry và skip ở writer

Exception xảy ra trong setter thuộc quá trình writer binding. Nếu step cấu hình fault tolerance, cần chọn exception type phù hợp:

```java
.faultTolerant()
.skip(InvalidColumnValueException.class)
.skipLimit(20)
```

Tuy nhiên, không nên skip lỗi cấu hình SQL hoặc lỗi kết nối database một cách rộng rãi. Lỗi hạ tầng thường cần retry có giới hạn hoặc fail để operator xử lý. Lỗi dữ liệu có thể được validation ở processor trước khi tới writer.

Với batch writer, một item có thể nằm trong chunk cùng nhiều item khác. Khi writer thất bại, transaction chunk có thể rollback; fault-tolerant writer có thể phải xác định item gây lỗi theo cơ chế scan. Setter có thể được gọi lại cho item trong quá trình đó, vì vậy nó cần stateless và an toàn khi lặp.

## Batch update count và assertUpdates

`JdbcBatchItemWriter` thực thi batch và nhận update counts từ JDBC driver. Builder mặc định bật kiểm tra `assertUpdates`. Mục đích là phát hiện trường hợp một item không ảnh hưởng tới row nào khi writer mong đợi mỗi item phải cập nhật/insert ít nhất một row.

Với câu `UPDATE ... WHERE order_id = ?`, nếu order không tồn tại, update count có thể bằng 0. Khi `assertUpdates` bật, writer có thể ném exception thay vì âm thầm chấp nhận item không được cập nhật.

```java
new JdbcBatchItemWriterBuilder<Order>()
        .dataSource(dataSource)
        .sql("UPDATE orders SET status = ? WHERE order_id = ?")
        .itemPreparedStatementSetter((order, ps) -> {
            ps.setString(1, order.status().name());
            ps.setString(2, order.orderId());
        })
        .assertUpdates(true)
        .build();
```

Nếu update count bằng 0 là kết quả hợp lệ theo nghiệp vụ, có thể cấu hình `.assertUpdates(false)`, nhưng cần kiểm tra output/metrics riêng để phát hiện item không có tác động khi cần. JDBC driver có thể trả các giá trị đặc biệt như `SUCCESS_NO_INFO` cho batch update; không nên giả định mọi driver luôn trả đúng số row chính xác.

Đối với `INSERT`, unique constraint hoặc foreign key violation thường tạo exception. Không nên dùng `assertUpdates(false)` để che những lỗi đó; nó không thay thế việc xử lý constraint hoặc dữ liệu trùng.

## Transaction và datasource

`ItemPreparedStatementSetter` không quản lý transaction. `JdbcBatchItemWriter` thực thi trong transaction được điều phối bởi step nếu writer dùng cùng datasource/transaction manager phù hợp.

```java
@Bean
Step writeOrdersStep(
        JobRepository jobRepository,
        @Qualifier("ordersTransactionManager") PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        JdbcBatchItemWriter<Order> writer) {

    return new StepBuilder("writeOrdersStep", jobRepository)
            .<Order, Order>chunk(200, transactionManager)
            .reader(reader)
            .writer(writer)
            .build();
}
```

Trong cấu hình nhiều datasource, phải bảo đảm writer dùng datasource được quản lý bởi transaction manager của step nếu muốn rollback insert/update cùng chunk. Nếu writer dùng datasource khác, local transaction của step không tự động rollback resource đó.

| Cấu hình | Hệ quả |
| --- | --- |
| Writer và step dùng cùng datasource/transaction manager | Batch write tham gia transaction chunk; exception có thể rollback thay đổi chưa commit |
| Writer dùng datasource khác | Có thể có transaction độc lập; cần phối hợp hoặc idempotency |
| Setter tự mở connection riêng | Bỏ qua transaction do step quản lý; không nên làm vậy |
| Setter tự commit | Phá vỡ chunk atomicity; không nên làm vậy |

Với writer database cùng transaction resource, nếu một item trong batch gây lỗi và transaction rollback, các thay đổi của chunk hiện tại được rollback theo database semantics. Các chunk trước đã commit vẫn tồn tại.

## Thread safety và tái sử dụng setter

`JdbcBatchItemWriter` được thiết kế để dùng trong batch processing và có thể được chia sẻ sau khi cấu hình hoàn tất. Tuy nhiên, custom `ItemPreparedStatementSetter` cũng phải an toàn với cách writer được sử dụng.

Một setter stateless thường an toàn:

```java
ItemPreparedStatementSetter<Order> setter = (order, ps) -> {
    ps.setString(1, order.orderId());
    ps.setBigDecimal(2, order.amount());
};
```

Setter có mutable field lưu item hiện tại có thể gặp race condition nếu nhiều thread gọi đồng thời:

```java
// Không nên: state dùng chung giữa các lần gọi
private String currentOrderId;

public void setValues(Order order, PreparedStatement ps) throws SQLException {
    currentOrderId = order.orderId();
    ps.setString(1, currentOrderId);
}
```

Hãy dùng biến local và chỉ đọc item được truyền vào. Không lưu `PreparedStatement` trong field. Nếu setter cần một mapper phụ thuộc configuration, mapper đó nên immutable hoặc thread-safe.

Với multi-threaded step hoặc nhiều flow dùng chung writer, cần đánh giá cả JDBC connection/transaction model và khả năng thread safety của custom collaborators. Không mặc định một setter có mutable state sẽ an toàn chỉ vì writer được Spring quản lý singleton.

## Kiểm thử ItemPreparedStatementSetter

Nên có unit test xác nhận mapping từng parameter và integration test xác nhận batch write/transaction với database.

### Unit test bằng mock PreparedStatement

Test độc lập có thể xác nhận đúng vị trí và kiểu JDBC được gọi:

```java
@Test
void bindsOrderFieldsToExpectedPositions() throws SQLException {
    PreparedStatement ps = mock(PreparedStatement.class);
    ItemPreparedStatementSetter<Order> setter = (order, statement) -> {
        statement.setString(1, order.orderId());
        statement.setString(2, order.customerId());
        statement.setBigDecimal(3, order.amount());
    };

    Order order = new Order(
            "O-1001",
            "C-20",
            new BigDecimal("125.50"));

    setter.setValues(order, ps);

    verify(ps).setString(1, "O-1001");
    verify(ps).setString(2, "C-20");
    verify(ps).setBigDecimal(3, new BigDecimal("125.50"));
}
```

Unit test này chứng minh setter gọi đúng JDBC method và parameter index. Nó không chứng minh SQL schema, driver hoặc transaction hoạt động đúng.

### Unit test null binding

```java
@Test
void bindsNullWithExplicitSqlType() throws SQLException {
    PreparedStatement ps = mock(PreparedStatement.class);
    OrderWithNote order = new OrderWithNote("O-1", null);

    setter.setValues(order, ps);

    verify(ps).setNull(2, Types.VARCHAR);
}
```

Test nên bao gồm cả giá trị có và không có để bảo đảm mọi lần gọi đều gán parameter.

### Integration test với JdbcBatchItemWriter

Dùng database test có schema tương ứng. Khởi chạy step chứa writer và xác nhận:

- Số row được insert/update đúng.
- Giá trị từng cột khớp item đầu vào.
- Decimal scale, date/time và null được lưu đúng.
- Parameter order trong SQL không bị đảo.
- Batch nhiều item không rò giá trị từ item trước.
- Unique/foreign key violation được xử lý theo policy mong muốn.

Ví dụ test có thể launch job bằng `JobLauncherTestUtils`, sau đó truy vấn bằng `JdbcTemplate`:

```java
List<OrderRow> rows = jdbcTemplate.query(
        "SELECT order_id, customer_id, amount FROM orders ORDER BY order_id",
        (rs, rowNum) -> new OrderRow(
                rs.getString("order_id"),
                rs.getString("customer_id"),
                rs.getBigDecimal("amount")));

assertEquals(2, rows.size());
assertEquals("O-1001", rows.get(0).orderId());
assertEquals(new BigDecimal("125.50"), rows.get(0).amount());
```

`OrderRow` là record test do ứng dụng định nghĩa. Với test thực tế, dùng identifying `JobParameters` riêng để tránh execution metadata cũ làm ảnh hưởng lần chạy.

### Kiểm thử rollback của chunk

Tạo một batch có nhiều item, trong đó một item gây lỗi khi bind hoặc khi database thực thi. Xác nhận transaction của chunk rollback nếu writer và `JobRepository`/business datasource dùng transaction resource phù hợp. Kiểm tra các chunk trước đã commit vẫn còn.

Không chỉ assert job `FAILED`; query bảng đích để xác nhận dữ liệu thực tế. Nếu driver có batch update behavior khác nhau, chạy test trên database/driver tương đương production.

### Kiểm thử assertUpdates

Với SQL update không tìm thấy row, xác nhận hành vi khi `assertUpdates(true)` và khi `false`. Nếu zero update là hợp lệ, test phải chứng minh ứng dụng có metrics hoặc logic khác để nhận biết item không có tác động.

## Hiệu năng batch và setter

`ItemPreparedStatementSetter` được gọi cho từng item, nhưng SQL được thực thi theo batch do writer điều phối. Để giữ throughput:

- Tránh tạo object hoặc format string lớn trong setter nếu không cần thiết.
- Không truy vấn database hoặc gọi HTTP cho mỗi item trong setter.
- Dùng đúng JDBC setter để tránh conversion không cần thiết.
- Giữ logic binding ngắn và xác định.
- Chọn chunk size theo throughput, transaction duration và giới hạn database.
- Kiểm tra JDBC driver có hỗ trợ batch update hiệu quả và cấu hình phù hợp không.
- Đo hiệu năng với dữ liệu đại diện, gồm cả null và kiểu dữ liệu lớn.

Không nên dùng một chunk size cực lớn chỉ để giảm số lần gọi writer. Batch quá lớn có thể tăng memory, lock duration và thời gian rollback. Chọn kích thước bằng benchmark và metrics thực tế.

## Lỗi thường gặp

### Dùng index bắt đầu từ 0

JDBC parameter index bắt đầu từ 1. Index 0 gây `SQLException` hoặc lỗi binding.

### Thứ tự setter không khớp SQL

SQL có thể chạy nhưng giá trị vào nhầm cột. Đối chiếu placeholder và setter theo vị trí; có unit test cho mapping.

### Không gán parameter khi giá trị null

Prepared statement có thể giữ giá trị cũ hoặc driver báo lỗi. Gọi `setNull` với SQL type phù hợp.

### Dùng `setObject` cho mọi kiểu

Driver có thể suy luận type khác nhau. Ưu tiên `setString`, `setBigDecimal`, `setTimestamp` hoặc overload có SQL type phù hợp.

### Nối chuỗi item vào SQL

Nối dữ liệu trực tiếp vào SQL gây lỗi quoting và nguy cơ SQL injection. Dùng placeholder `?` và bind qua `PreparedStatement`.

### Tự execute hoặc commit trong setter

Setter chỉ gán parameter. `JdbcBatchItemWriter` quản lý batch execution; step transaction manager quản lý commit/rollback.

### Catch SQLException rồi bỏ qua

Writer có thể tiếp tục như thể parameter hợp lệ. Để exception đi lên để framework xử lý đúng.

### Thực hiện validation nghiệp vụ trong setter

Lỗi xuất hiện ở giai đoạn write và khó phân biệt với lỗi JDBC. Validate dữ liệu ở processor/domain layer; setter tập trung vào binding.

### Dùng setter mutable trong multi-threaded step

State dùng chung có thể bị ghi đè giữa các item. Giữ setter stateless và dùng biến local.

### Nhầm ItemPreparedStatementSetter với PreparedStatementSetter hoặc RowMapper

`ItemPreparedStatementSetter` bind một item Spring Batch; `PreparedStatementSetter` thuộc Spring JDBC; `RowMapper` ánh xạ row kết quả thành object.

### Không kiểm tra update count

Một `UPDATE` có thể ảnh hưởng zero row. Giữ `assertUpdates` phù hợp và kiểm thử kết quả zero update theo hợp đồng nghiệp vụ.

## Nguyên tắc triển khai

Khi sử dụng `ItemPreparedStatementSetter`, hãy xác định:

1. SQL dùng placeholder `?` và số lượng placeholder có khớp setter không?
2. Mỗi vị trí JDBC được gán đúng cột và đúng thứ tự chưa?
3. Mỗi lần callback có gán đầy đủ mọi parameter không?
4. Null được bind bằng SQL type phù hợp chưa?
5. Date/time, decimal, enum và binary có mapping nhất quán với schema không?
6. Setter có stateless, không giữ `PreparedStatement` và không có side effect không?
7. Writer và step có dùng datasource/transaction manager phù hợp không?
8. `assertUpdates` có phản ánh đúng kỳ vọng update count không?
9. Exception có được phân loại phù hợp cho retry/skip/fail không?
10. Test đã xác nhận parameter mapping, batch output, rollback và database driver chưa?

Với SQL positional, `ItemPreparedStatementSetter` cung cấp cách binding trực tiếp và rõ ràng. Giữ setter nhỏ, dùng JDBC method đúng kiểu, luôn gán mọi parameter và để `JdbcBatchItemWriter` thực thi batch trong transaction của step. Nếu SQL có nhiều cột và tên parameter giúp dễ đọc hơn, cân nhắc named parameter provider. Trong cả hai trường hợp, kiểm thử trên database/driver tương đương production và xác nhận business data thực tế sau commit/rollback.

## Ghi nhớ

`ItemPreparedStatementSetter<T>` ánh xạ một item vào các placeholder `?` của `PreparedStatement` thông qua `setValues(item, ps)`. JDBC parameter index bắt đầu từ 1 và phải khớp chính xác thứ tự placeholder trong SQL. Setter chỉ gán giá trị; `JdbcBatchItemWriter` thực thi batch còn transaction manager của step quản lý commit/rollback. Gán mọi parameter ở mỗi lần gọi, dùng phương thức JDBC đúng kiểu và `setNull(index, Types.X)` cho null. Giữ setter stateless, không tự execute/commit/đóng statement và không nối dữ liệu vào SQL. Dùng `ItemSqlParameterSourceProvider`/`beanMapped()` nếu muốn named parameter. Kiểm thử riêng mapping bằng mock `PreparedStatement`, rồi integration test với database để xác nhận batch output, update count, null/type mapping và rollback.
