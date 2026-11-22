# JdbcCursorItemReader

Trong Spring Batch, `JdbcCursorItemReader<T>` đọc dữ liệu từ database bằng JDBC cursor. Reader mở một câu SQL, thực thi query và giữ `ResultSet` để lấy từng dòng theo thứ tự. Mỗi lần framework gọi `read()`, reader lấy dòng tiếp theo và dùng `RowMapper<T>` chuyển dòng đó thành object Java.

`JdbcCursorItemReader` phù hợp khi cần đọc tuần tự một tập kết quả SQL lớn mà không tải toàn bộ dữ liệu vào bộ nhớ. Nó thường được dùng trong chunk-oriented Step để đọc từng bản ghi, xử lý qua `ItemProcessor` rồi ghi bằng `ItemWriter`.

Đặc điểm quan trọng của cursor reader là nó giữ cursor và kết nối JDBC trong thời gian Step đọc dữ liệu. Điều này khác với `JdbcPagingItemReader`, vốn chia truy vấn thành nhiều page. Lựa chọn giữa hai loại cần cân nhắc thời gian giữ connection, hành vi transaction của database, yêu cầu restart và khả năng dữ liệu nguồn thay đổi trong lúc Job chạy.

## 1. Cursor reader hoạt động như thế nào?

JDBC cursor là một `ResultSet` cho phép ứng dụng duyệt kết quả query. Với `JdbcCursorItemReader`, Spring Batch quản lý vòng đời cursor và cung cấp một item cho mỗi lần gọi `read()`.

Luồng cơ bản:

1. Step bắt đầu và gọi `open()` trên reader.
2. Reader lấy connection, tạo statement và thực thi SQL.
3. JDBC trả về `ResultSet`.
4. Mỗi lần `read()`, reader di chuyển đến dòng tiếp theo.
5. `RowMapper` chuyển dòng hiện tại thành object.
6. Spring Batch gom item vào chunk, gọi processor/writer và commit transaction theo commit interval.
7. Reader cập nhật checkpoint qua `update()` khi framework lưu state.
8. Khi Step kết thúc, reader đóng `ResultSet`, statement và connection qua `close()`.

```text
Job / Step bắt đầu
       |
       v
reader.open(ExecutionContext)
       |
       v
Mở JDBC connection + PreparedStatement
       |
       v
Execute SQL -> ResultSet cursor
       |
       v
reader.read()
       |
       +--> ResultSet.next()
       |       |
       |       +--> RowMapper.mapRow(...)
       |       |
       |       +--> trả về một item
       |
       +--> lặp cho đến EOF (trả null)
       |
       v
reader.update(ExecutionContext)
       |
       v
reader.close()
```

`JdbcCursorItemReader` triển khai các contract cần thiết để hoạt động như một `ItemStreamReader`. Ứng dụng không cần tự mở và đóng cursor trong từng lần `read()`.

## 2. Cấu hình JdbcCursorItemReader cơ bản

Một cursor reader cần tối thiểu `DataSource`, SQL, tên reader và `RowMapper`:

```java
@Bean
public JdbcCursorItemReader<Order> orderCursorReader(DataSource dataSource) {
    JdbcCursorItemReader<Order> reader = new JdbcCursorItemReader<>();
    reader.setName("orderCursorReader");
    reader.setDataSource(dataSource);
    reader.setSql("""
            SELECT order_id, customer_id, amount, order_date
            FROM orders
            ORDER BY order_id
            """);
    reader.setRowMapper((rs, rowNum) -> {
        Order order = new Order();
        order.setOrderId(rs.getLong("order_id"));
        order.setCustomerId(rs.getLong("customer_id"));
        order.setAmount(rs.getBigDecimal("amount"));
        order.setOrderDate(rs.getDate("order_date").toLocalDate());
        return order;
    });
    reader.setFetchSize(500);
    reader.setSaveState(true);
    return reader;
}
```

Trong ví dụ:

- `setName(...)` đặt tên ổn định cho reader, được dùng khi lưu state.
- `setDataSource(...)` cung cấp JDBC connection.
- `setSql(...)` định nghĩa query trả về các cột cần đọc.
- `setRowMapper(...)` ánh xạ mỗi dòng `ResultSet` thành `Order`.
- `setFetchSize(500)` gợi ý JDBC driver lấy dữ liệu theo các nhóm phù hợp.
- `setSaveState(true)` bật lưu checkpoint để hỗ trợ restart.

SQL nên chỉ lấy các cột cần thiết. Tránh `SELECT *` nếu bảng có nhiều cột hoặc schema có thể thay đổi, vì reader chỉ nên phụ thuộc vào dữ liệu mà model cần.

## 3. Tích hợp reader vào chunk-oriented Step

Reader có thể được đăng ký như một thành phần đọc bình thường của chunk Step:

```java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        JdbcCursorItemReader<Order> orderCursorReader,
        ItemProcessor<Order, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(orderCursorReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
```

Với `chunk(100, transactionManager)`, Step xử lý tối đa 100 item trong một chunk trước khi commit theo luồng thông thường. Cursor không bị mở lại cho mỗi chunk; reader giữ ResultSet và tiếp tục đọc dòng tiếp theo trong suốt vòng đời Step.

Chunk size và JDBC fetch size là hai cấu hình khác nhau:

| Cấu hình | Điều khiển điều gì? |
|---|---|
| `chunk(100, transactionManager)` | Số item được xử lý trong một transaction chunk |
| `fetchSize(500)` | Gợi ý cho JDBC driver về số dòng lấy trước từ database mỗi lần fetch |

Không cần đặt hai giá trị bằng nhau. Chunk size ảnh hưởng transaction và commit; fetch size ảnh hưởng việc driver truyền dữ liệu từ database đến ứng dụng.

## 4. RowMapper chuyển ResultSet thành object

`RowMapper<T>` nhận `ResultSet` đang đứng tại dòng hiện tại và trả về object tương ứng:

```java
public interface RowMapper<T> {
    T mapRow(ResultSet rs, int rowNum) throws SQLException;
}
```

Ví dụ:

```java
public class OrderRowMapper implements RowMapper<Order> {

    @Override
    public Order mapRow(ResultSet rs, int rowNum) throws SQLException {
        Order order = new Order();
        order.setOrderId(rs.getLong("order_id"));
        order.setCustomerId(rs.getLong("customer_id"));
        order.setAmount(rs.getBigDecimal("amount"));

        Date orderDate = rs.getDate("order_date");
        order.setOrderDate(orderDate == null ? null : orderDate.toLocalDate());

        return order;
    }
}
```

`rowNum` là số thứ tự dòng theo ngữ cảnh mapper. Nếu cần lưu ID nghiệp vụ, hãy lấy từ cột khóa như `order_id`, không dùng `rowNum` làm định danh bản ghi.

Một `RowMapper` nên ánh xạ một dòng và không tự di chuyển cursor bằng `next()`, `previous()` hoặc `absolute()`. Reader quản lý vị trí ResultSet. Nếu mapper di chuyển cursor, reader có thể bỏ sót dòng hoặc phát hiện vị trí cursor không hợp lệ khi bật kiểm tra cursor position.

## 5. SQL có tham số và PreparedStatementSetter

Job thường cần đọc dữ liệu theo ngày nghiệp vụ, trạng thái hoặc tenant. Không nên nối trực tiếp tham số vào chuỗi SQL. Dùng placeholder `?` và `PreparedStatementSetter` để bind giá trị.

```java
@Bean
@StepScope
public JdbcCursorItemReader<Order> orderCursorReader(
        DataSource dataSource,
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    JdbcCursorItemReader<Order> reader = new JdbcCursorItemReader<>();
    reader.setName("orderCursorReader");
    reader.setDataSource(dataSource);
    reader.setSql("""
            SELECT order_id, customer_id, amount, order_date
            FROM orders
            WHERE business_date = ?
            ORDER BY order_id
            """);
    reader.setPreparedStatementSetter(ps ->
            ps.setDate(1, Date.valueOf(LocalDate.parse(businessDate)))
    );
    reader.setRowMapper(new OrderRowMapper());
    reader.setFetchSize(500);
    reader.setSaveState(true);
    return reader;
}
```

`@StepScope` cho phép đọc `businessDate` tại thời điểm StepExecution chạy. Prepared statement bind giá trị riêng biệt với câu SQL, giúp tránh SQL injection và xử lý kiểu dữ liệu đúng hơn so với nối chuỗi.

Nếu có nhiều tham số, bind theo đúng thứ tự placeholder:

```java
reader.setSql("""
        SELECT order_id, customer_id, amount
        FROM orders
        WHERE tenant_id = ?
          AND business_date >= ?
        ORDER BY order_id
        """);

reader.setPreparedStatementSetter(ps -> {
    ps.setLong(1, tenantId);
    ps.setDate(2, Date.valueOf(businessDate));
});
```

Tên cột, table hoặc `ORDER BY` direction không thể bind bằng `?` như value. Nếu cần chọn cấu trúc SQL động, hãy dùng whitelist cho các lựa chọn được phép và kiểm tra đầu vào trước khi tạo query.

## 6. Dùng JdbcCursorItemReaderBuilder

Spring Batch cung cấp builder để cấu hình reader theo cách gọn hơn:

```java
@Bean
public JdbcCursorItemReader<Order> orderCursorReader(DataSource dataSource) {
    return new JdbcCursorItemReaderBuilder<Order>()
            .name("orderCursorReader")
            .dataSource(dataSource)
            .sql("""
                    SELECT order_id, customer_id, amount
                    FROM orders
                    ORDER BY order_id
                    """)
            .rowMapper(new OrderRowMapper())
            .fetchSize(500)
            .saveState(true)
            .verifyCursorPosition(true)
            .build();
}
```

Builder thường giúp cấu hình các thuộc tính chính như name, data source, SQL, row mapper, fetch size và save state. Các tùy chọn nâng cao có thể được cấu hình qua builder hoặc setter của reader tùy phiên bản Spring Batch.

Nếu dự án dùng phiên bản API khác, hãy đối chiếu các method sẵn có trong dependency. Cách dùng trực tiếp setter như ví dụ trước thể hiện rõ các thuộc tính cốt lõi và dễ điều chỉnh khi builder thay đổi.

## 7. Fetch size và hiệu năng đọc

`fetchSize` là gợi ý cho JDBC driver về số dòng nên lấy trước từ database trong một lượt fetch. Nó có thể giảm số round trip giữa ứng dụng và database, đặc biệt khi đọc nhiều dòng.

Ví dụ:

```java
reader.setFetchSize(1000);
```

Fetch size không phải chunk size và không đảm bảo driver luôn lấy đúng số dòng đó. Một số driver xem nó là hint; một số driver có cách xử lý riêng hoặc cần cấu hình thêm để stream kết quả thay vì tải toàn bộ result set.

Khi chọn fetch size, cân nhắc:

- Số cột và kích thước trung bình mỗi dòng.
- Dung lượng heap có thể dành cho buffer của driver.
- Độ trễ mạng giữa ứng dụng và database.
- Hành vi fetch của JDBC driver.
- Số reader/partition chạy đồng thời.
- Thời gian giữ connection và cursor.

Fetch size quá nhỏ có thể tăng round trip; quá lớn có thể tăng bộ nhớ dùng cho buffer. Hãy đo với driver và database thực tế thay vì chọn giá trị chỉ dựa trên số item mỗi chunk.

## 8. Query timeout, max rows và các tùy chọn cursor

`JdbcCursorItemReader` hỗ trợ các thuộc tính JDBC hữu ích để kiểm soát query và cursor. Tên setter có thể thay đổi theo phiên bản, nhưng các khái niệm thường gặp gồm:

| Thuộc tính | Tác dụng |
|---|---|
| `fetchSize` | Hint về số dòng fetch mỗi lượt |
| `queryTimeout` | Giới hạn thời gian thực thi statement theo giây nếu driver hỗ trợ |
| `maxRows` | Giới hạn số dòng tối đa mà statement trả về khi được cấu hình |
| `verifyCursorPosition` | Kiểm tra mapper không tự thay đổi vị trí cursor |
| `driverSupportsAbsolute` | Cho reader biết driver hỗ trợ `ResultSet.absolute()` để định vị lại cursor |
| `saveState` | Bật/tắt lưu checkpoint trong ExecutionContext |

Ví dụ cấu hình reader trực tiếp:

```java
reader.setFetchSize(500);
reader.setQueryTimeout(60);
reader.setVerifyCursorPosition(true);
reader.setDriverSupportsAbsolute(false);
reader.setSaveState(true);
```

`queryTimeout` là timeout của câu lệnh JDBC, không nhất thiết là timeout tổng của toàn Step. Một query có thể thực thi nhanh nhưng cursor vẫn mở lâu vì Step đọc và xử lý từng chunk trong thời gian dài.

`maxRows` phù hợp cho giới hạn có chủ đích như test hoặc xử lý một tập con. Không dùng nó thay cho điều kiện nghiệp vụ trong SQL nếu cần xác định chính xác tập dữ liệu.

## 9. verifyCursorPosition

`verifyCursorPosition` giúp phát hiện `RowMapper` hoặc code liên quan đã tự di chuyển cursor. Khi bật, reader kiểm tra vị trí cursor trước/sau khi gọi mapper theo cơ chế của implementation.

Ví dụ:

```java
reader.setVerifyCursorPosition(true);
```

Đây thường là lựa chọn an toàn trong quá trình phát triển vì `RowMapper` chỉ nên đọc các cột của dòng hiện tại và trả object. Nếu mapper gọi `rs.next()` để tìm dòng khác, reader có thể bỏ qua item hoặc ném lỗi kiểm tra vị trí.

Không tắt kiểm tra để che lỗi mapper di chuyển cursor. Nếu cần đọc dữ liệu liên quan, hãy dùng query/join riêng, truy vấn repository phù hợp hoặc xử lý trong processor; không điều khiển ResultSet của cursor reader từ mapper.

## 10. driverSupportsAbsolute

Khi restart, cursor reader cần mở lại query và định vị đến vị trí đã lưu. Nếu JDBC driver hỗ trợ `ResultSet.absolute(row)`, reader có thể dùng thao tác này để nhảy đến vị trí cần thiết. Nếu không, reader phải di chuyển qua các dòng trước đó để đến checkpoint.

`driverSupportsAbsolute` cho reader biết driver có hỗ trợ cách định vị này hay không:

```java
reader.setDriverSupportsAbsolute(true);
```

Chỉ đặt `true` khi driver và ResultSet mode thực tế hỗ trợ `absolute()` cho cursor đang dùng. Nếu không chắc, giữ cấu hình an toàn theo default của phiên bản hoặc kiểm tra tài liệu JDBC driver.

Khả năng nhảy nhanh đến một row không thay thế yêu cầu dữ liệu có thứ tự ổn định. Khi restart, vị trí row chỉ có ý nghĩa nếu query trả lại cùng thứ tự và tập dữ liệu tương thích với lần chạy trước.

## 11. Connection và transaction behavior

Một điểm cần hiểu khi dùng `JdbcCursorItemReader` là cursor phải tồn tại trong khi Step đọc nhiều chunk. Trong cấu hình mặc định, reader thường mở connection riêng cho cursor thay vì dùng connection transaction của từng chunk. Điều này giúp cursor không bị đóng khi transaction chunk commit hoặc rollback.

Hệ quả:

- Connection cursor có thể được giữ trong suốt thời gian Step chạy.
- Mỗi chunk vẫn dùng transaction manager của Step để commit dữ liệu ghi.
- Cursor connection và chunk transaction có thể là hai connection/transaction khác nhau.
- Rollback transaction ghi không nhất thiết tua ngược cursor JDBC.
- Tính nhất quán dữ liệu đọc phụ thuộc isolation level và hành vi database/driver.

Không nên mặc định rằng reader và writer đang dùng cùng một transaction chỉ vì chúng dùng cùng một `DataSource`. Cần hiểu cách reader mở connection và cách transaction manager quản lý connection.

## 12. useSharedExtendedConnection

Trong một số trường hợp, muốn cursor dùng chung connection mở rộng với transaction của Step. `JdbcCursorItemReader` có tùy chọn `useSharedExtendedConnection`. Cách này yêu cầu `DataSource` được bọc bằng `ExtendedConnectionDataSourceProxy` và JDBC driver/database hỗ trợ giữ cursor qua commit (hold cursors over commit).

Ví dụ cấu hình khái niệm:

```java
@Bean
public DataSource extendedDataSource(DataSource targetDataSource) {
    return new ExtendedConnectionDataSourceProxy(targetDataSource);
}

@Bean
public JdbcCursorItemReader<Order> orderCursorReader(
        @Qualifier("extendedDataSource") DataSource dataSource) {

    JdbcCursorItemReader<Order> reader = new JdbcCursorItemReader<>();
    reader.setName("orderCursorReader");
    reader.setDataSource(dataSource);
    reader.setSql("SELECT order_id, amount FROM orders ORDER BY order_id");
    reader.setRowMapper(new OrderRowMapper());
    reader.setUseSharedExtendedConnection(true);
    reader.setSaveState(true);
    return reader;
}
```

Đây là cấu hình nâng cao. Không phải mọi database hoặc JDBC driver đều hỗ trợ cursor tồn tại qua commit. Nếu driver đóng ResultSet sau commit, shared extended connection có thể không hoạt động đúng.

Chỉ bật tùy chọn này sau khi xác nhận hỗ trợ của database/driver và kiểm thử transaction thực tế. Với phần lớn trường hợp, cấu hình mặc định dùng connection cursor riêng là điểm khởi đầu dễ vận hành hơn.

## 13. Checkpoint và restart

`JdbcCursorItemReader` hỗ trợ lưu state để Step có thể restart. Reader lưu tiến độ đọc trong Step `ExecutionContext`, thường thông qua item count hiện tại và key gắn với tên reader.

Ví dụ bật state:

```java
reader.setName("orderCursorReader");
reader.setSaveState(true);
```

Khi Job restart cùng JobInstance:

1. Spring Batch tạo StepExecution mới cho lần chạy lại.
2. Reader mở lại SQL và tạo cursor mới.
3. Reader đọc checkpoint đã lưu trong ExecutionContext.
4. Reader định vị lại cursor đến item tiếp theo cần xử lý.
5. Step tiếp tục từ phần chưa commit theo metadata đã lưu.

Reader không thể giữ nguyên JDBC `ResultSet` cũ qua process restart. Nó thực thi lại query và định vị lại dựa trên state đã lưu. Vì vậy, `saveState` chỉ giải quyết vị trí đọc; tính đúng đắn còn phụ thuộc query trả về cùng tập dữ liệu và cùng thứ tự.

Giữ tên reader ổn định qua các lần deploy nếu cần restart execution cũ. Đổi tên có thể làm thay đổi key lưu state và reader không tìm thấy checkpoint trước đó.

## 14. ORDER BY ổn định là yêu cầu quan trọng

Nếu query không có `ORDER BY`, database không bảo đảm thứ tự dòng trả về. Reader có thể đọc các item theo một thứ tự ở lần chạy đầu và một thứ tự khác khi restart.

Ví dụ không nên dùng:

```sql
SELECT order_id, amount
FROM orders
WHERE business_date = ?
```

Nên xác định thứ tự rõ ràng bằng một khóa ổn định:

```sql
SELECT order_id, amount
FROM orders
WHERE business_date = ?
ORDER BY order_id
```

Nếu `order_id` không duy nhất trong tập kết quả, thêm khóa phụ để thứ tự xác định:

```sql
ORDER BY customer_id, order_date, order_id
```

Thứ tự phải ổn định và duy nhất đối với các dòng cần đọc. Khi query có join một-nhiều, cần chú ý khóa sắp xếp phải phân biệt được từng dòng kết quả, không chỉ từng entity cha.

## 15. Dữ liệu thay đổi giữa lần chạy và restart

Cursor reader lưu vị trí theo thứ tự item, không phải một snapshot dữ liệu độc lập. Nếu dữ liệu nguồn thay đổi giữa lần chạy đầu và restart, vị trí row cũ có thể trỏ đến dữ liệu khác.

Ví dụ, lần đầu query trả 1.000 dòng theo `order_id`. Reader đã commit đến dòng thứ 500 rồi Job thất bại. Trước khi restart, một số dòng cũ bị xóa hoặc dòng mới được chèn vào đầu thứ tự. Khi query chạy lại, vị trí thứ 501 có thể không còn tương ứng với item tiếp theo của lần đầu.

Các biện pháp giúp ổn định nguồn dữ liệu:

- Chọn tập dữ liệu bằng `businessDate`, batch ID hoặc trạng thái nguồn cố định.
- Dùng snapshot hoặc isolation phù hợp nếu nghiệp vụ yêu cầu một ảnh chụp nhất quán.
- Dùng watermark/high-water mark để cố định phạm vi ID.
- Không cập nhật/xóa dữ liệu nguồn trong lúc Job đang xử lý nếu restart phụ thuộc row position.
- Lưu manifest hoặc danh sách khóa nếu tập dữ liệu cần được tái tạo chính xác.
- Với dữ liệu biến động lớn, cân nhắc paging theo khóa hoặc partitioning theo phạm vi nghiệp vụ.

`ORDER BY` là cần thiết nhưng chưa đủ nếu tập dữ liệu có thể thay đổi. Cần ổn định cả tập kết quả và thứ tự.

## 16. Cursor reader và connection pool

Vì cursor reader giữ connection trong thời gian Step chạy, nó có thể chiếm một connection từ pool trong nhiều phút hoặc lâu hơn. Nếu nhiều Job/Step chạy đồng thời, pool có thể cạn connection.

Ví dụ:

- 8 Step cursor đang chạy đồng thời.
- Mỗi Step giữ một connection cho cursor.
- Writer và các service khác cũng cần connection từ cùng pool.
- Nếu pool chỉ có 8 connection, các thao tác ghi hoặc service khác có thể phải chờ.

Khi triển khai, cần tính số connection cần cho reader cursor, writer transaction và các ứng dụng khác. Đừng chỉ tăng pool size mà không xem giới hạn connection của database.

Các điểm cần quan sát:

- Số connection active/idle trong pool.
- Thời gian một cursor giữ connection.
- Số cursor đang mở.
- Thời gian query mở cursor.
- Wait time khi lấy connection.
- Lock hoặc transaction lâu trên database.

Nếu Step chạy rất lâu, có thể cân nhắc `JdbcPagingItemReader` hoặc chia nhỏ phạm vi bằng partitioning để giới hạn thời gian giữ cursor và phân phối tải.

## 17. Khi nào nên dùng JdbcCursorItemReader?

Cursor reader phù hợp khi:

- Cần đọc tuần tự một result set theo một query.
- Database/driver hỗ trợ cursor ổn định với khối lượng dữ liệu cần xử lý.
- Có thể giữ connection/cursor trong thời gian Step chạy.
- Thứ tự và tập dữ liệu được kiểm soát để hỗ trợ restart.
- Muốn giảm số query lặp lại so với việc chạy query cho từng page.

Nên cân nhắc lựa chọn khác khi:

- Step kéo dài và không muốn giữ connection lâu.
- Database/driver không stream cursor như mong đợi.
- Nguồn dữ liệu thay đổi thường xuyên khiến row-position restart không an toàn.
- Cần chia dữ liệu thành nhiều partition theo khóa/range.
- Cần query lại theo từng page để quản lý tải và checkpoint rõ hơn.

## 18. So sánh JdbcCursorItemReader và JdbcPagingItemReader

| Tiêu chí | `JdbcCursorItemReader` | `JdbcPagingItemReader` |
|---|---|---|
| Cách đọc | Mở một query và duyệt ResultSet cursor | Chạy nhiều query theo page |
| Connection | Thường giữ cursor connection trong suốt Step | Thực thi query theo từng page; connection không cần giữ một cursor duy nhất suốt Step |
| Vị trí đọc | Dựa trên vị trí cursor/item count | Dựa trên sort key và page state |
| ORDER BY | Cần thứ tự xác định để restart an toàn | Cần sort key ổn định, thường là khóa duy nhất |
| Tải database | Một query dài có thể giữ cursor/transaction/resource | Nhiều query nhỏ hơn, có overhead query lặp |
| Phù hợp | Đọc tuần tự result set ổn định | Tập dữ liệu lớn, cần page và có thể muốn tránh cursor lâu dài |
| Restart | Mở lại query rồi định vị theo item count | Mở lại page dựa trên state và sort key |

Không có lựa chọn luôn nhanh hơn. Hiệu năng phụ thuộc database, driver, query plan, fetch size, page size, số connection và kích thước dữ liệu. Hãy đo trên workload gần production.

## 19. Kết hợp cursor reader với partitioning

Có thể dùng cursor reader trong worker Step của partitioned Job. Mỗi partition nhận phạm vi dữ liệu riêng và tạo cursor query riêng.

Ví dụ SQL của worker:

```sql
SELECT order_id, customer_id, amount
FROM orders
WHERE order_id BETWEEN ? AND ?
ORDER BY order_id
```

Reader step-scoped nhận `minId` và `maxId` từ `StepExecutionContext`, bind vào PreparedStatement. Mỗi worker có cursor và connection riêng.

Điều này có thể tăng throughput nhưng cũng làm tăng số cursor và connection đồng thời. Grid size cần phù hợp với connection pool và giới hạn database. Tên partition, phạm vi ID và JobParameters cần ổn định để restart đúng partition.

Không dùng một instance `JdbcCursorItemReader` singleton chia sẻ giữa nhiều worker StepExecution. Reader có mutable cursor state và không được thiết kế để nhiều partition cùng điều khiển một ResultSet.

## 20. Lỗi thường gặp khi dùng JdbcCursorItemReader

### Không có ORDER BY

Database trả kết quả theo thứ tự không xác định. Khi restart, reader có thể định vị sai item. Hãy dùng thứ tự ổn định, duy nhất.

### Giữ cursor quá lâu

Step chạy lâu giữ connection và cursor, gây áp lực lên connection pool hoặc database. Xem xét fetch size, query plan, page reader hoặc partitioning.

### RowMapper tự gọi ResultSet.next()

Mapper di chuyển cursor và làm reader bỏ qua dòng hoặc vi phạm kiểm tra cursor position. Mapper chỉ nên đọc cột của dòng hiện tại.

### Dùng sai fetch size

Fetch size quá nhỏ tăng round trip; quá lớn có thể tăng bộ nhớ. Kiểm tra hành vi thực tế của JDBC driver.

### Nghĩ rằng chunk commit sẽ commit cursor position

Cursor connection mặc định có thể tách khỏi transaction connection của chunk. Rollback transaction ghi không tự rewind cursor. Spring Batch quản lý replay/checkpoint theo reader state.

### Dữ liệu nguồn thay đổi giữa restart

Checkpoint theo item count có thể trỏ sang dòng khác nếu tập kết quả thay đổi. Dùng snapshot, batch ID, watermark hoặc nguồn bất biến.

### Tắt saveState nhưng kỳ vọng restart

Nếu `saveState(false)`, reader không lưu checkpoint theo cơ chế thông thường. Khi restart, nó có thể đọc lại từ đầu hoặc không khôi phục được tiến độ mong muốn.

### Dùng shared extended connection khi driver không hỗ trợ

Cursor có thể bị đóng sau commit. Chỉ bật tùy chọn này khi database/driver hỗ trợ hold cursor over commit và cấu hình proxy đúng.

## 21. Xử lý lỗi và fault tolerance

Exception có thể phát sinh khi mở connection, thực thi SQL, đọc ResultSet hoặc map dòng. Lỗi hạ tầng tạm thời có thể được retry nếu reader và database có thể thực hiện lại an toàn. Lỗi dữ liệu cụ thể có thể được skip nếu nghiệp vụ cho phép.

Ví dụ cấu hình retry cho lỗi truy cập dữ liệu tạm thời:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderCursorReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
```

Không nên retry mọi `Exception`. Lỗi SQL sai cú pháp, thiếu cột hoặc sai schema không tự khắc phục khi thử lại. Tương tự, không skip lỗi database outage vì có thể làm mất dữ liệu.

Khi lỗi xảy ra, cần xem exception gốc, transaction rollback, trạng thái cursor và checkpoint. Reader có thể được mở lại hoặc định vị lại theo cơ chế retry/restart; không tự giữ `ResultSet` trong code ngoài reader.

## 22. Kiểm thử JdbcCursorItemReader

Nên dùng database test phù hợp để xác nhận hành vi JDBC thực tế, đặc biệt nếu production dùng driver cụ thể. Một số trường hợp cần kiểm tra:

1. Đọc result set rỗng và xác nhận `read()` trả `null`.
2. Đọc nhiều dòng và xác nhận `RowMapper` ánh xạ đúng kiểu dữ liệu.
3. Bind tham số ngày/tenant và xác nhận query chỉ trả tập dữ liệu mong muốn.
4. Xác nhận `ORDER BY` cho thứ tự ổn định.
5. Kiểm tra fetch size và query timeout với driver thực tế.
6. Làm writer thất bại một lần rồi retry thành công; xác nhận item không bị mất hoặc ghi trùng.
7. Dừng Job sau một số chunk đã commit và restart cùng JobInstance; xác nhận reader tiếp tục đúng checkpoint.
8. Thay đổi dữ liệu nguồn giữa hai lần chạy để kiểm tra rủi ro của item-count restart.
9. Đo connection được giữ trong suốt Step và ảnh hưởng lên pool.
10. Nếu dùng `useSharedExtendedConnection`, xác nhận cursor vẫn mở qua commit với driver/database production.

Unit test `RowMapper` riêng giúp kiểm tra chuyển đổi một dòng, nhưng không chứng minh reader mở/đóng cursor, restart hay transaction hoạt động đúng. Integration test với `JobRepository`, transaction manager và database thực tế cần thiết cho các hành vi đó.

## 23. Quy tắc thiết kế JdbcCursorItemReader

Chọn `JdbcCursorItemReader` khi cần duyệt tuần tự một result set và có thể giữ cursor/connection trong thời gian Step chạy. Cấu hình SQL rõ ràng, chỉ lấy cột cần thiết, dùng `PreparedStatementSetter` cho giá trị runtime và `RowMapper` chỉ ánh xạ dòng hiện tại. Đặt fetch size dựa trên phép đo với JDBC driver thực tế.

Để restart đáng tin cậy, đặt tên reader ổn định, bật `saveState`, giữ nguyên JobParameters và bảo đảm query có `ORDER BY` xác định trên khóa duy nhất. Tập dữ liệu cũng cần ổn định giữa lần chạy đầu và restart. Hiểu rõ connection cursor mặc định tách khỏi transaction chunk; chỉ dùng shared extended connection khi database/driver hỗ trợ và đã kiểm thử.

Nếu không muốn giữ cursor lâu, cần phân trang hoặc cần phân chia tải theo khóa, cân nhắc `JdbcPagingItemReader` hoặc partitioning. Khi kiểm tra sự cố, xem cả checkpoint, transaction, trạng thái Step và dữ liệu đã commit. Thiết kế đúng các yếu tố đó giúp cursor reader xử lý dữ liệu database tuần tự, hiệu quả và có thể restart một cách có kiểm soát.
