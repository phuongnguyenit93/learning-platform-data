# RowMapper bất biến trong Spring Batch

Trong Spring Batch, các reader JDBC thường dùng Spring JDBC để biến từng dòng của ResultSet thành một object Java. Thành phần thực hiện việc ánh xạ này là **RowMapper**. Một RowMapper tốt thường không giữ trạng thái giữa các lần gọi, không thay đổi cấu trúc dữ liệu đọc được và tạo ra object có giá trị ổn định sau khi rời khỏi ResultSet.

Khi xử lý batch, những đặc điểm đó đặc biệt quan trọng. Một RowMapper có state mutable có thể giữ nhầm dữ liệu từ dòng trước, gây lỗi khi dùng lại hoặc khi nhiều Step chạy đồng thời. Một object đầu ra mutable có thể bị thay đổi sau khi đọc, khiến processor, writer hoặc retry nhìn thấy những giá trị khác nhau. Thiết kế RowMapper bất biến giúp việc đọc dữ liệu dễ dự đoán, dễ kiểm thử và an toàn hơn khi tái sử dụng.

Cần phân biệt hai khái niệm:

- **RowMapper bất biến/stateless:** bản thân mapper không thay đổi state trong quá trình ánh xạ và không giữ ResultSet hoặc dữ liệu của dòng hiện tại trong field.
- **Object đầu ra bất biến:** object được tạo từ một dòng dữ liệu không cho phép thay đổi state sau khi khởi tạo, hoặc bảo vệ dữ liệu mutable bằng defensive copy.

Hai điều này bổ trợ cho nhau. Mapper có thể stateless nhưng trả về object mutable; ngược lại, object có thể immutable nhưng mapper vẫn không an toàn nếu giữ một biến field dùng chung. Trong batch processing, nên thiết kế cả hai phía một cách rõ ràng.

Bài học này tập trung vào RowMapper trong Spring JDBC và cách dùng nó với JdbcCursorItemReader, JdbcPagingItemReader. Nội dung bao gồm mapping bằng Java record hoặc class final, xử lý SQL NULL và kiểu dữ liệu, mapping JOIN, restart, concurrency, cùng cách kiểm thử mapper.

## 1. RowMapper làm gì?

Spring JDBC định nghĩa RowMapper để ánh xạ dòng hiện tại của ResultSet thành một object:

~~~java
public interface RowMapper<T> {
    T mapRow(ResultSet rs, int rowNum) throws SQLException;
}
~~~

Hai tham số:

- rs là ResultSet đang đứng tại dòng cần ánh xạ.
- rowNum là chỉ số dòng do framework cung cấp cho lần ánh xạ hiện tại.
- Giá trị trả về là object đại diện cho dòng đó.
- SQLException được phép truyền ra để framework xử lý theo cơ chế JDBC/Spring.

Ví dụ đơn giản:

~~~java
public class CustomerRowMapper implements RowMapper<Customer> {

    @Override
    public Customer mapRow(ResultSet rs, int rowNum)
            throws SQLException {

        return new Customer(
            rs.getLong("customer_id"),
            rs.getString("full_name"),
            rs.getString("email")
        );
    }
}
~~~

Với mỗi dòng ResultSet, mapper tạo một Customer mới. Mapper không gọi rs.next(); việc di chuyển cursor do JdbcTemplate hoặc reader quản lý.

### Một lần gọi mapRow tương ứng với một dòng

RowMapper không phải nơi điều khiển vòng lặp ResultSet. Không viết:

~~~java
@Override
public Customer mapRow(ResultSet rs, int rowNum)
        throws SQLException {

    while (rs.next()) {
        // Không làm như vậy trong RowMapper.
    }

    return null;
}
~~~

Nếu tự gọi rs.next(), mapper sẽ làm cursor tiến thêm một dòng và khiến framework bỏ qua dữ liệu hoặc gặp lỗi trạng thái cursor.

Cũng không giữ ResultSet trong field để dùng sau khi mapRow kết thúc. ResultSet có vòng đời gắn với statement/connection; sau khi query hoàn tất, nó có thể đã đóng.

## 2. Vì sao RowMapper nên stateless?

RowMapper thường được đăng ký thành Spring bean singleton và có thể được dùng lại qua nhiều lần query. Một implementation stateless có thể xử lý nhiều ResultSet mà không mang dữ liệu từ lần gọi trước sang lần gọi sau.

Ví dụ không an toàn:

~~~java
public class UnsafeCustomerRowMapper
        implements RowMapper<Customer> {

    private long currentCustomerId;
    private String currentName;

    @Override
    public Customer mapRow(ResultSet rs, int rowNum)
            throws SQLException {

        currentCustomerId = rs.getLong("customer_id");
        currentName = rs.getString("full_name");

        return new Customer(currentCustomerId, currentName);
    }
}
~~~

Các field currentCustomerId và currentName không cần tồn tại. Chúng tạo mutable state dùng chung và có thể gây race condition nếu mapper được gọi đồng thời.

Cách an toàn:

~~~java
public final class CustomerRowMapper
        implements RowMapper<Customer> {

    @Override
    public Customer mapRow(ResultSet rs, int rowNum)
            throws SQLException {

        long customerId = rs.getLong("customer_id");
        String name = rs.getString("full_name");

        return new Customer(customerId, name);
    }
}
~~~

Các biến local chỉ tồn tại trong một lần gọi mapRow. Mỗi dòng tạo một object mới, không ghi dữ liệu vào field dùng chung.

### Stateless giúp tái sử dụng

Một mapper stateless có thể:

- Được khai báo thành singleton bean.
- Được dùng bởi nhiều query có cùng projection.
- Được chia sẻ giữa các Step nếu mapping contract giống nhau.
- Được gọi đồng thời mà không có race condition do state nội bộ.
- Được unit test độc lập với Spring context.

Stateless không tự bảo đảm mọi dependency đều thread-safe. Nếu mapper dùng một formatter hoặc converter có mutable state, dependency đó cũng phải được thiết kế an toàn.

## 3. Object đầu ra bất biến là gì?

Object bất biến là object có trạng thái không thay đổi sau khi được tạo. Thay vì tạo object rỗng rồi gọi setter, constructor nhận toàn bộ giá trị cần thiết.

Ví dụ mutable:

~~~java
public class Customer {
    private long id;
    private String name;
    private String email;

    public void setId(long id) {
        this.id = id;
    }

    public void setName(String name) {
        this.name = name;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
~~~

Object này có thể được tạo ở trạng thái chưa đầy đủ rồi mới được gán từng field. Một component khác có thể thay đổi name hoặc email sau khi reader đã trả object.

Một model bất biến dùng Java record:

~~~java
public record Customer(
    long id,
    String name,
    String email
) {
}
~~~

Record tạo constructor, accessor và các method value-based. Các field của record là final. Nếu các thành phần bên trong cũng bất biến, Customer là một value object phù hợp cho pipeline.

Một lựa chọn khác là class final với field final:

~~~java
public final class Customer {

    private final long id;
    private final String name;
    private final String email;

    public Customer(long id, String name, String email) {
        this.id = id;
        this.name = name;
        this.email = email;
    }

    public long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }
}
~~~

Không cung cấp setter hoặc phương thức thay đổi field. Constructor kiểm tra invariant và khởi tạo object hoàn chỉnh.

## 4. Record là lựa chọn phù hợp cho JDBC projection

Với Java 16 trở lên, record thường phù hợp cho các object chỉ chứa dữ liệu được query từ database.

Ví dụ:

~~~java
public record OrderRow(
    long orderId,
    String orderNumber,
    String status,
    BigDecimal total,
    LocalDate createdDate
) {
}
~~~

RowMapper:

~~~java
public final class OrderRowMapper
        implements RowMapper<OrderRow> {

    @Override
    public OrderRow mapRow(ResultSet rs, int rowNum)
            throws SQLException {

        Date createdDate = rs.getDate("created_date");

        return new OrderRow(
            rs.getLong("order_id"),
            rs.getString("order_number"),
            rs.getString("status"),
            rs.getBigDecimal("total"),
            createdDate == null ? null : createdDate.toLocalDate()
        );
    }
}
~~~

Mapper không giữ field, còn OrderRow không có setter. Mỗi lần gọi mapRow tạo một snapshot giá trị của dòng hiện tại.

Record có thể dùng trực tiếp với ItemProcessor:

~~~java
@Bean
ItemProcessor<OrderRow, OrderSummary> orderProcessor() {
    return row -> new OrderSummary(
        row.orderId(),
        row.orderNumber(),
        row.total()
    );
}
~~~

Không bắt buộc mọi object trong pipeline đều phải là record. Nếu dự án dùng Java version cũ hoặc cần framework binding cụ thể, class final với constructor vẫn là lựa chọn tốt.

## 5. Bất biến sâu và defensive copy

Field final không có nghĩa object tự động immutable sâu. Nếu record chứa List, Map, array hoặc Date mutable, dữ liệu bên trong vẫn có thể bị thay đổi.

Ví dụ chưa đủ an toàn:

~~~java
public record CustomerWithTags(
    long id,
    List<String> tags
) {
}
~~~

Tham chiếu tags là final, nhưng người gọi vẫn có thể sửa list nếu list mutable.

Dùng defensive copy:

~~~java
public record CustomerWithTags(
    long id,
    List<String> tags
) {
    public CustomerWithTags {
        tags = List.copyOf(tags);
    }
}
~~~

List.copyOf tạo danh sách không thể sửa thông qua reference được trả ra. Nếu input có thể null, cần quy định rõ: từ chối null, thay bằng List.of() hoặc giữ null theo contract.

Với Map:

~~~java
public record CustomerAttributes(
    long id,
    Map<String, String> attributes
) {
    public CustomerAttributes {
        attributes = Map.copyOf(attributes);
    }
}
~~~

Với array, cần clone khi nhận và khi trả:

~~~java
public final class BinaryPayload {

    private final byte[] content;

    public BinaryPayload(byte[] content) {
        this.content = content.clone();
    }

    public byte[] content() {
        return content.clone();
    }
}
~~~

Nếu các phần tử trong collection cũng mutable, copy collection chưa đủ. Cần tạo bản sao bất biến cho từng phần tử hoặc dùng kiểu value immutable.

## 6. Mapping SQL NULL đúng cách

JDBC có một điểm dễ gây lỗi: các getter primitive như getLong(), getInt() và getBoolean() không trả null. Khi cột SQL là NULL, chúng trả giá trị mặc định; phải gọi wasNull() ngay sau getter để biết giá trị vừa đọc có null hay không.

Ví dụ:

~~~java
long parentIdValue = rs.getLong("parent_id");
Long parentId = rs.wasNull() ? null : parentIdValue;
~~~

Phải gọi wasNull() ngay sau getter tương ứng. Nếu gọi thêm getter khác rồi mới gọi wasNull(), kết quả sẽ phản ánh getter gần nhất chứ không phải cột parent_id.

Nếu driver hỗ trợ JDBC 4.1 và kiểu dữ liệu tương thích, có thể lấy wrapper trực tiếp:

~~~java
Long parentId = rs.getObject("parent_id", Long.class);
Integer retryCount = rs.getObject("retry_count", Integer.class);
Boolean enabled = rs.getObject("enabled", Boolean.class);
~~~

Cách này thể hiện null rõ ràng và tránh phải ghép getter primitive với wasNull. Tuy nhiên, cần kiểm tra driver và kiểu cột thực tế.

### Phân biệt zero với NULL

Hai trạng thái này có thể mang ý nghĩa nghiệp vụ khác nhau:

| SQL value | getLong() | Giá trị có ý nghĩa |
|---|---:|---|
| 0 | 0 | Số 0 thực sự |
| NULL | 0 | Không có giá trị |

Nếu bỏ qua wasNull(), mapper sẽ biến NULL thành 0 và làm mất thông tin. Điều này có thể khiến processor tính toán hoặc phân loại sai.

Với trường bắt buộc, có thể fail rõ ràng nếu database trả NULL:

~~~java
Long quantity = rs.getObject("quantity", Long.class);

if (quantity == null) {
    throw new SQLException(
        "Cột quantity không được NULL"
    );
}
~~~

Nếu null là trạng thái hợp lệ, giữ kiểu wrapper trong DTO thay vì ép thành primitive.

## 7. Kiểu dữ liệu số và BigDecimal

Đối với tiền, tỷ lệ hoặc số thập phân cần độ chính xác, dùng BigDecimal:

~~~java
BigDecimal amount = rs.getBigDecimal("amount");
~~~

Không chuyển DECIMAL sang double rồi tạo lại BigDecimal:

~~~java
// Tránh cách chuyển đổi qua double:
BigDecimal amount = BigDecimal.valueOf(
    rs.getDouble("amount")
);
~~~

Chuyển qua double có thể làm mất độ chính xác thập phân. Đọc trực tiếp bằng getBigDecimal giữ kiểu số decimal từ JDBC driver.

Nếu cột có thể NULL, getBigDecimal trả null. Hãy giữ null hoặc áp dụng default theo quy tắc nghiệp vụ được xác định rõ.

### Scale và rounding

Database có thể lưu DECIMAL(18, 2), nhưng object hoặc business rule có thể yêu cầu scale khác. Không tự ý gọi setScale trong RowMapper nếu đó là quy tắc tính toán nghiệp vụ.

Mapper nên phản ánh giá trị đã lưu. Việc rounding, quy đổi tiền tệ hoặc áp dụng precision nên nằm ở processor hoặc domain service.

## 8. Mapping enum và giá trị trạng thái

Nếu database lưu trạng thái dạng VARCHAR:

~~~text
status
------
ACTIVE
SUSPENDED
CLOSED
~~~

Có thể ánh xạ thành enum:

~~~java
public enum CustomerStatus {
    ACTIVE,
    SUSPENDED,
    CLOSED
}
~~~

Mapper:

~~~java
private CustomerStatus mapStatus(String value) {
    if (value == null) {
        return null;
    }

    try {
        return CustomerStatus.valueOf(
            value.trim().toUpperCase(Locale.ROOT)
        );
    } catch (IllegalArgumentException ex) {
        throw new IllegalArgumentException(
            "Customer status không được hỗ trợ: " + value,
            ex
        );
    }
}
~~~

Trong mapRow:

~~~java
CustomerStatus status = mapStatus(
    rs.getString("status")
);
~~~

Nếu database có giá trị legacy như ENABLED, DISABLED hoặc các code viết tắt, dùng mapping tường minh:

~~~java
private CustomerStatus mapStatus(String value) {
    if (value == null) {
        return null;
    }

    return switch (value) {
        case "A", "ACTIVE" -> CustomerStatus.ACTIVE;
        case "S", "SUSPENDED" -> CustomerStatus.SUSPENDED;
        case "C", "CLOSED" -> CustomerStatus.CLOSED;
        default -> throw new IllegalArgumentException(
            "Unknown status code: " + value
        );
    };
}
~~~

Không tự chuyển giá trị không nhận diện thành ACTIVE hoặc một trạng thái mặc định có thể làm thay đổi ý nghĩa dữ liệu. Nếu cần tương thích dữ liệu cũ, ghi rõ mapping và kiểm thử từng code.

## 9. Mapping ngày và thời gian

JDBC có các kiểu SQL DATE, TIME và TIMESTAMP. Nên chuyển sang java.time thay vì đưa java.sql.Date hoặc java.sql.Timestamp mutable vào domain object.

Ví dụ SQL DATE:

~~~java
Date sqlDate = rs.getDate("business_date");
LocalDate businessDate =
    sqlDate == null ? null : sqlDate.toLocalDate();
~~~

Ví dụ TIMESTAMP thành LocalDateTime:

~~~java
Timestamp timestamp = rs.getTimestamp("created_at");
LocalDateTime createdAt =
    timestamp == null ? null : timestamp.toLocalDateTime();
~~~

Nếu cột đại diện một thời điểm tuyệt đối:

~~~java
Timestamp timestamp = rs.getTimestamp("created_at");
Instant createdAt =
    timestamp == null ? null : timestamp.toInstant();
~~~

Cần hiểu kiểu cột, timezone của database, JDBC driver và cấu hình session. TIMESTAMP không timezone có thể được diễn giải theo timezone của session/driver; không tự coi mọi timestamp đều là UTC.

Với kiểu SQL có timezone, có thể dùng JDBC 4.2 getObject với OffsetDateTime nếu driver hỗ trợ:

~~~java
OffsetDateTime createdAt =
    rs.getObject("created_at", OffsetDateTime.class);
~~~

Hãy kiểm thử với database và driver thực tế. Không dùng java.util.Date làm field bất biến nếu object có thể bị thay đổi thông qua các method setTime.

## 10. Mapping cột bằng alias rõ ràng

Query JOIN có thể chứa nhiều cột trùng tên như id, status hoặc created_at. Nếu mapper đọc bằng label không rõ ràng, driver có thể trả cột không mong muốn hoặc phát sinh lỗi.

Dùng alias mô tả rõ projection:

~~~sql
SELECT
    c.customer_id AS customer_id,
    c.status AS customer_status,
    a.account_id AS account_id,
    a.status AS account_status
FROM customer c
LEFT JOIN account a
    ON a.customer_id = c.customer_id
~~~

Mapper đọc đúng label:

~~~java
return new CustomerAccountRow(
    rs.getLong("customer_id"),
    rs.getString("customer_status"),
    rs.getObject("account_id", Long.class),
    rs.getString("account_status")
);
~~~

Tên alias là một phần của contract giữa SQL và RowMapper. Khi thay đổi alias, query và mapper cần được cập nhật cùng nhau.

Tránh SELECT * trong query có JOIN. SELECT * làm projection phụ thuộc schema và có thể tạo tên cột trùng, khiến mapping khó hiểu khi bảng thay đổi.

## 11. Mapping một hàng JOIN thành projection bất biến

Một JOIN một-một hoặc nhiều-một có thể ánh xạ thành object kết hợp:

~~~java
public record CustomerAccountRow(
    long customerId,
    String customerName,
    Long accountId,
    String accountStatus
) {
}
~~~

RowMapper:

~~~java
public final class CustomerAccountRowMapper
        implements RowMapper<CustomerAccountRow> {

    @Override
    public CustomerAccountRow mapRow(
            ResultSet rs,
            int rowNum) throws SQLException {

        return new CustomerAccountRow(
            rs.getLong("customer_id"),
            rs.getString("customer_name"),
            rs.getObject("account_id", Long.class),
            rs.getString("account_status")
        );
    }
}
~~~

LEFT JOIN có thể không tìm thấy account. Khi đó account_id và account_status là null. Mapper cần giữ đúng ngữ nghĩa đó thay vì biến thành ID 0 hoặc chuỗi rỗng.

Đây là projection của một dòng JOIN. Nó phù hợp khi mỗi dòng SQL tương ứng với một object đầu ra.

## 12. JOIN một-nhiều cần xử lý khác

Giả sử một customer có nhiều address. Query JOIN có thể trả:

~~~text
customer_id | customer_name | address_id | city
------------+---------------+------------+----------
10          | An            | 101        | Hanoi
10          | An            | 102        | Da Nang
11          | Binh          | 103        | HCMC
~~~

Một RowMapper thông thường sẽ tạo một object cho mỗi dòng. Nếu ánh xạ thành CustomerWithAddresses, hai dòng đầu sẽ tạo hai Customer riêng cùng ID 10, mỗi object có một address.

Không nên dùng field Map trong singleton RowMapper để tích lũy address giữa các lần mapRow. Cách đó giữ state qua query, không biết khi nào một customer đã hoàn tất và không an toàn khi chạy đồng thời.

Có các lựa chọn phù hợp hơn:

- Dùng ResultSetExtractor để duyệt toàn bộ ResultSet và nhóm parent-child.
- Query parent riêng rồi load collection bằng query khác.
- Trả về flat projection theo từng dòng rồi group trong processor/service có phạm vi rõ.
- Dùng SQL aggregation như JSON aggregation nếu database và contract phù hợp.

### Khi nào dùng ResultSetExtractor?

RowMapper phù hợp với ánh xạ một dòng thành một object. ResultSetExtractor phù hợp khi cần đọc nhiều dòng để tạo một kết quả tổng hợp.

Ví dụ khái niệm:

~~~java
Map<Long, CustomerBuilder> customers = new LinkedHashMap<>();

while (rs.next()) {
    long customerId = rs.getLong("customer_id");

    CustomerBuilder customer = customers.computeIfAbsent(
        customerId,
        id -> new CustomerBuilder(
            id,
            readCustomerName(rs)
        )
    );

    Long addressId = rs.getObject("address_id", Long.class);

    if (addressId != null) {
        customer.addAddress(readAddress(rs));
    }
}

return customers.values().stream()
    .map(CustomerBuilder::build)
    .toList();
~~~

Đoạn code chỉ minh họa grouping. ResultSetExtractor có quyền điều khiển việc duyệt ResultSet; RowMapper thì không. Builder mutable có thể được dùng nội bộ trong một lần extract, sau đó chuyển thành object bất biến khi trả kết quả.

## 13. RowMapper trong JdbcTemplate

JdbcTemplate query nhận SQL và RowMapper:

~~~java
List<CustomerRow> customers = jdbcTemplate.query(
    """
    SELECT customer_id, full_name, email
    FROM customer
    WHERE status = ?
    ORDER BY customer_id
    """,
    customerRowMapper,
    "ACTIVE"
);
~~~

Spring JDBC quản lý việc tạo statement, thực thi query, duyệt ResultSet và gọi mapRow cho từng dòng.

Mapper không được:

- Gọi rs.next().
- Đóng ResultSet hoặc Statement.
- Đóng Connection do JdbcTemplate quản lý.
- Giữ ResultSet trong field.
- Gọi query khác bằng cùng ResultSet đang được ánh xạ.
- Thay đổi cursor hoặc transaction boundary.

Nếu cần truy vấn thêm dữ liệu cho mỗi dòng, đó là một thiết kế N+1 có thể gây hiệu năng kém. Nên cân nhắc JOIN, batch query hoặc enrichment sau khi lấy projection.

## 14. Dùng RowMapper với JdbcCursorItemReader

Trong Spring Batch, JdbcCursorItemReader dùng RowMapper để chuyển từng dòng cursor thành item:

~~~java
@Bean
@StepScope
JdbcCursorItemReader<CustomerRow> customerReader(
        DataSource dataSource,
        CustomerRowMapper customerRowMapper,
        @Value("#{jobParameters['status']}") String status) {

    return new JdbcCursorItemReaderBuilder<CustomerRow>()
        .name("customerReader")
        .dataSource(dataSource)
        .sql("""
            SELECT customer_id, full_name, email, status
            FROM customer
            WHERE status = ?
            ORDER BY customer_id
            """)
        .preparedStatementSetter(ps ->
            ps.setString(1, status)
        )
        .rowMapper(customerRowMapper)
        .fetchSize(500)
        .saveState(true)
        .build();
}
~~~

Reader mở cursor và điều khiển việc di chuyển qua ResultSet. RowMapper chỉ chuyển dòng hiện tại thành CustomerRow.

Với cursor reader:

- Không gọi rs.next() trong mapRow.
- Không đóng cursor hoặc connection trong mapper.
- Không lưu state vào field của mapper.
- Reader quản lý resource và checkpoint.
- Mapper nên trả object độc lập với ResultSet để item vẫn dùng được sau khi cursor tiến tiếp.

### Vì sao object phải độc lập với ResultSet?

ResultSet chỉ có hiệu lực trong vòng đời query. Nếu DTO giữ Blob, Clob, SQLXML hoặc stream phụ thuộc connection, dữ liệu có thể không còn đọc được sau khi reader chuyển dòng hoặc đóng cursor.

Nếu cần dữ liệu LOB, hãy đọc thành byte[], String hoặc một representation độc lập trong thời điểm mapRow, đồng thời cân nhắc giới hạn bộ nhớ và kích thước payload.

## 15. Dùng RowMapper với JdbcPagingItemReader

JdbcPagingItemReader cũng dùng RowMapper để chuyển từng dòng của từng page thành item:

~~~java
@Bean
@StepScope
JdbcPagingItemReader<CustomerRow> customerPagingReader(
        DataSource dataSource,
        PagingQueryProvider queryProvider,
        CustomerRowMapper customerRowMapper) {

    return new JdbcPagingItemReaderBuilder<CustomerRow>()
        .name("customerPagingReader")
        .dataSource(dataSource)
        .queryProvider(queryProvider)
        .pageSize(500)
        .rowMapper(customerRowMapper)
        .saveState(true)
        .build();
}
~~~

RowMapper không cần biết dữ liệu đang ở page nào. Nó chỉ nhận dòng hiện tại và ánh xạ.

Paging reader yêu cầu sort key ổn định để phân trang và restart. Nếu sort key không duy nhất, các dòng có cùng giá trị có thể bị lặp hoặc bỏ sót tùy query provider và database. Thường nên dùng khóa chính hoặc kết hợp khóa phụ để tạo thứ tự toàn phần.

### Mapper không lưu page state

Không đưa page number, current offset hoặc last ID vào field của singleton RowMapper. Những state đó thuộc reader hoặc ExecutionContext.

Tách trách nhiệm:

| Thành phần | State sở hữu |
|---|---|
| RowMapper | Không có state theo dòng hoặc page |
| JdbcPagingItemReader | Page, sort key và checkpoint |
| ItemProcessor | State nghiệp vụ nếu có, theo scope rõ |
| JobRepository | Metadata và ExecutionContext bền vững |

## 16. RowMapper và restart

RowMapper không phải thành phần lưu checkpoint. Nó không cần triển khai ItemStream chỉ vì được dùng bởi reader restartable.

Spring Batch reader chịu trách nhiệm:

- Xác định vị trí hiện tại.
- Cập nhật ExecutionContext.
- Khôi phục trạng thái khi restart.
- Quản lý cursor hoặc page.
- Mở và đóng resource.

RowMapper chịu trách nhiệm:

- Đọc các cột của dòng hiện tại.
- Chuyển kiểu dữ liệu.
- Tạo object đầu ra.
- Không giữ state giữa các dòng.

Vì mapper phải deterministic, cùng một dòng dữ liệu và cùng mapping contract nên tạo ra cùng một object value. Nếu mapping phụ thuộc thời gian hiện tại hoặc service mutable, restart có thể tạo ra object khác cho cùng dòng. Nếu cần snapshot, hãy lấy dữ liệu đó thành JobParameters hoặc dữ liệu được lưu rõ ràng trước khi xử lý.

### Tránh side effect trong mapRow

Không gửi email, cập nhật bảng, ghi file hoặc gọi API có side effect trong mapRow. Reader có thể đọc lại item sau rollback/restart hoặc retry; side effect trong mapper sẽ khó kiểm soát và có thể lặp.

Mapping nên là phép chuyển đổi dữ liệu thuần.

## 17. Mapping kiểu dữ liệu phức tạp

Một RowMapper có thể chuyển đổi nhiều kiểu:

~~~java
public record InvoiceRow(
    long id,
    String invoiceNumber,
    BigDecimal amount,
    LocalDate invoiceDate,
    Instant createdAt,
    InvoiceStatus status,
    Boolean approved
) {
}
~~~

Mapper:

~~~java
public final class InvoiceRowMapper
        implements RowMapper<InvoiceRow> {

    @Override
    public InvoiceRow mapRow(ResultSet rs, int rowNum)
            throws SQLException {

        Date invoiceDate = rs.getDate("invoice_date");
        Timestamp createdAt = rs.getTimestamp("created_at");
        String statusValue = rs.getString("status");

        return new InvoiceRow(
            rs.getLong("invoice_id"),
            rs.getString("invoice_number"),
            rs.getBigDecimal("amount"),
            invoiceDate == null
                ? null
                : invoiceDate.toLocalDate(),
            createdAt == null
                ? null
                : createdAt.toInstant(),
            statusValue == null
                ? null
                : InvoiceStatus.valueOf(statusValue),
            rs.getObject("approved", Boolean.class)
        );
    }
}
~~~

Trong production, việc parse enum cần xử lý giá trị legacy hoặc không hợp lệ theo contract. Nếu dữ liệu không hợp lệ, ném exception có ngữ nghĩa thay vì âm thầm chọn một enum mặc định.

### UUID

Nếu database lưu UUID và JDBC driver hỗ trợ kiểu tương ứng, có thể dùng getObject với UUID.class. Nếu driver hoặc database lưu UUID dưới dạng VARCHAR/BINARY, mapping phải phù hợp schema:

~~~java
String rawId = rs.getString("external_id");
UUID externalId =
    rawId == null ? null : UUID.fromString(rawId);
~~~

Không giả định mọi database lưu UUID giống nhau.

### JSON column

Nếu một cột chứa JSON, RowMapper có thể lấy String rồi parse bằng ObjectMapper:

~~~java
String rawMetadata = rs.getString("metadata_json");

Metadata metadata = rawMetadata == null
    ? null
    : objectMapper.readValue(rawMetadata, Metadata.class);
~~~

ObjectMapper được cấu hình xong có thể được chia sẻ nếu sử dụng theo cách thread-safe. Không tạo mapper JSON mới cho từng dòng nếu không cần, và không thay đổi cấu hình ObjectMapper dùng chung trong lúc batch chạy.

## 18. Mapping dữ liệu null và invariant của domain

Không phải mọi SQL NULL đều nên được giữ nguyên. Quyết định phụ thuộc ý nghĩa domain:

- Trường optional: giữ null bằng wrapper hoặc Optional ở tầng phù hợp.
- Trường bắt buộc: fail nếu database vi phạm invariant.
- Trường có default nghiệp vụ: áp dụng default có chủ đích, có test và có thể audit.
- Trường legacy: chuyển đổi theo mapping rõ ràng.

Ví dụ constructor kiểm tra invariant:

~~~java
public record ProductRow(
    long id,
    String sku,
    String name,
    BigDecimal price
) {
    public ProductRow {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException(
                "sku không được để trống"
            );
        }

        if (price == null || price.signum() < 0) {
            throw new IllegalArgumentException(
                "price không hợp lệ"
            );
        }
    }
}
~~~

Nếu constructor ném exception, lỗi xảy ra ngay khi mapRow tạo object. Điều này giúp dữ liệu không hợp lệ không đi sâu vào processor/writer.

Tuy nhiên, cần phân biệt lỗi dữ liệu có thể skip với lỗi schema/hạ tầng. Nếu cả một cột bắt buộc bị NULL do migration sai, skip từng dòng có thể che giấu lỗi toàn hệ thống.

## 19. Không trả object phụ thuộc tài nguyên JDBC

Một object đầu ra nên tồn tại độc lập sau khi mapRow hoàn tất. Tránh trả trực tiếp:

- ResultSet.
- Blob hoặc Clob còn phụ thuộc connection.
- SQLXML chưa được đọc.
- InputStream lấy từ LOB mà chưa materialize.
- JDBC Array chưa được chuyển đổi.
- Proxy hoặc wrapper gắn với transaction đã kết thúc.

Ví dụ đọc Clob thành String:

~~~java
Clob clob = rs.getClob("description");

String description = null;

if (clob != null) {
    long length = clob.length();

    if (length > MAX_DESCRIPTION_LENGTH) {
        throw new SQLException(
            "Description vượt giới hạn cho phép"
        );
    }

    description = clob.getSubString(1, (int) length);
}
~~~

Đoạn code cần giới hạn kích thước để không nạp payload không kiểm soát vào heap. Với LOB rất lớn, nên thiết kế một quy trình streaming riêng thay vì đưa stream gắn với ResultSet vào item rồi dùng sau khi cursor đóng.

## 20. RowMapper có nên dùng dependency?

Một RowMapper có thể nhận dependency như ObjectMapper, converter hoặc cấu hình mapping. Để giữ tính bất biến:

- Khai báo dependency bằng constructor.
- Dùng field final.
- Không thay đổi dependency sau khi tạo.
- Dependency dùng chung phải thread-safe.
- Không giữ dữ liệu của dòng hiện tại trong field.

Ví dụ:

~~~java
public final class EventRowMapper
        implements RowMapper<EventRow> {

    private final ObjectMapper objectMapper;

    public EventRowMapper(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public EventRow mapRow(ResultSet rs, int rowNum)
            throws SQLException {

        String payload = rs.getString("payload");

        try {
            EventPayload parsed =
                objectMapper.readValue(payload, EventPayload.class);

            return new EventRow(
                rs.getLong("event_id"),
                rs.getString("event_type"),
                parsed
            );
        } catch (JsonProcessingException ex) {
            throw new SQLException(
                "Không thể parse event payload",
                ex
            );
        }
    }
}
~~~

ObjectMapper sau khi cấu hình thường được tái sử dụng. Không gọi registerModule hoặc thay đổi cấu hình trên ObjectMapper dùng chung trong lúc batch đang chạy.

### Constructor injection trong Spring

Có thể khai báo mapper:

~~~java
@Bean
EventRowMapper eventRowMapper(ObjectMapper objectMapper) {
    return new EventRowMapper(objectMapper);
}
~~~

Spring bean mặc định là singleton. Điều này an toàn khi mapper không có mutable state theo request/dòng và dependency dùng chung an toàn.

## 21. RowMapper bất biến không có nghĩa SQL bất biến

Mapper có thể stateless nhưng kết quả vẫn thay đổi nếu query đọc dữ liệu database thay đổi giữa các lần chạy. Cần tách hai vấn đề:

- Mapper deterministic đối với một ResultSet row.
- Query và nguồn dữ liệu có snapshot/ordering phù hợp cho batch hay không.

Nếu batch cần xử lý đúng tập dữ liệu tại một thời điểm, hãy dùng business date, cutoff timestamp, batch ID, snapshot isolation hoặc một tập ID đã materialize. Không dựa vào mapper để giải quyết tính nhất quán nguồn.

Với JdbcPagingItemReader, sort key ổn định và filter theo cutoff giúp tránh dữ liệu mới chen vào tập đang đọc.

## 22. Xử lý exception trong RowMapper

RowMapper khai báo throws SQLException. Khi đọc cột hoặc chuyển đổi dữ liệu, có thể xảy ra:

- SQLException do cột không tồn tại hoặc driver lỗi.
- IllegalArgumentException khi parse enum hoặc UUID.
- JsonProcessingException khi parse JSON.
- Domain validation exception khi constructor từ chối dữ liệu.

Không bắt mọi Exception rồi trả object rỗng. Điều đó biến dữ liệu lỗi thành item có vẻ hợp lệ và làm lỗi xuất hiện muộn hơn.

Ví dụ chuyển đổi exception:

~~~java
try {
    return mapDomainObject(rs);
} catch (IllegalArgumentException ex) {
    throw new SQLException(
        "Dữ liệu database không phù hợp với projection",
        ex
    );
}
~~~

Tùy ứng dụng, có thể định nghĩa một exception mapping riêng. Khi dùng trong Spring Batch, kiểm tra cause chain và cấu hình retry/skip theo exception thực tế được reader phát ra ở version đang sử dụng.

### Không log toàn bộ row một cách mặc định

Row có thể chứa email, số tài khoản, token hoặc dữ liệu cá nhân. Nếu mapping lỗi, log primary key, query context hoặc correlation ID cần thiết thay vì dump toàn bộ giá trị.

## 23. Dùng ColumnMapRowMapper hay custom RowMapper?

Spring JDBC có thể trả map theo tên cột thông qua ColumnMapRowMapper. Điều này thuận tiện cho query động hoặc công cụ tổng quát, nhưng object map không có kiểu dữ liệu domain mạnh như DTO.

| Cách | Phù hợp khi |
|---|---|
| Custom RowMapper | Projection ổn định, kiểu rõ, logic chuyển đổi riêng |
| BeanPropertyRowMapper | Tên cột có thể map theo property convention và object phù hợp |
| DataClassRowMapper | Mapping constructor/record phù hợp với phiên bản Spring |
| ColumnMapRowMapper | Query động hoặc dữ liệu cần dạng Map |
| ResultSetExtractor | Cần tổng hợp nhiều dòng thành một kết quả |

BeanPropertyRowMapper hoặc DataClassRowMapper có thể giảm boilerplate, nhưng vẫn cần kiểm tra cách xử lý null, constructor, tên alias và kiểu dữ liệu. Không chọn mapper tự động chỉ vì code ngắn hơn nếu projection có quy tắc chuyển đổi quan trọng.

Một custom RowMapper là lựa chọn rõ ràng khi cần enum mapping, SQL NULL semantics, JSON, time zone hoặc domain invariant.

## 24. Kiểm thử RowMapper độc lập

Unit test nên kiểm tra mapping từ một dòng ResultSet sang object.

Có thể dùng Mockito mock ResultSet:

~~~java
@Test
void mapsCustomerColumns() throws SQLException {
    ResultSet rs = mock(ResultSet.class);

    when(rs.getLong("customer_id")).thenReturn(42L);
    when(rs.getString("full_name")).thenReturn("An Nguyen");
    when(rs.getString("email")).thenReturn("an@example.test");

    CustomerRowMapper mapper = new CustomerRowMapper();

    Customer customer = mapper.mapRow(rs, 0);

    assertEquals(42L, customer.id());
    assertEquals("An Nguyen", customer.name());
    assertEquals("an@example.test", customer.email());
}
~~~

Test này tập trung vào hợp đồng mapper mà không cần mở database. Nó phù hợp để kiểm tra từng field, alias, chuyển đổi kiểu và xử lý null.

Nếu dùng Mockito, cần khai báo dependency test tương ứng trong dự án. Không bắt buộc dùng mock; có thể dùng ResultSet thực từ embedded database cho test tích hợp.

## 25. Kiểm thử SQL NULL

Với getter primitive, test cần mô phỏng cả giá trị primitive mặc định và wasNull:

~~~java
@Test
void preservesNullForNullableLong() throws SQLException {
    ResultSet rs = mock(ResultSet.class);

    when(rs.getLong("parent_id")).thenReturn(0L);
    when(rs.wasNull()).thenReturn(true);

    NullableCustomerRowMapper mapper =
        new NullableCustomerRowMapper();

    CustomerRelation relation = mapper.mapRow(rs, 0);

    assertNull(relation.parentId());
}
~~~

Nếu mapper dùng getObject("parent_id", Long.class), test đơn giản hơn:

~~~java
when(rs.getObject("parent_id", Long.class)).thenReturn(null);
~~~

Cần có test riêng cho giá trị 0 thực sự để chắc chắn mapper không nhầm zero với NULL.

## 26. Kiểm thử object bất biến

Nếu output là record chỉ chứa String, Long và BigDecimal, các field đó vốn bất biến. Nếu có collection hoặc array, test defensive copy.

~~~java
@Test
void copiesTagsAndPreventsMutation() {
    List<String> source = new ArrayList<>();
    source.add("vip");

    CustomerWithTags customer =
        new CustomerWithTags(10L, source);

    source.add("internal");

    assertEquals(List.of("vip"), customer.tags());

    assertThrows(
        UnsupportedOperationException.class,
        () -> customer.tags().add("new-tag")
    );
}
~~~

Test này xác nhận object không bị thay đổi khi caller sửa list đầu vào và list trả ra không thể sửa.

Nếu model chứa object mutable khác, test cần kiểm tra cả object lồng bên trong. Immutability phải được đánh giá theo toàn bộ object graph, không chỉ modifier final của field ngoài cùng.

## 27. Kiểm thử RowMapper với database thật

Mock ResultSet không kiểm tra:

- SQL có trả đúng alias không.
- Database driver chuyển kiểu ra sao.
- Cột NULL được biểu diễn thế nào.
- Timestamp và timezone được diễn giải ra sao.
- Query JOIN có tạo dòng trùng không.
- Mapping có tương thích với schema thực tế không.

Dùng embedded database hoặc Testcontainers để kiểm thử query và mapper cùng nhau.

Ví dụ quy trình:

1. Tạo schema test với cột có kiểu dữ liệu tương ứng.
2. Insert record hợp lệ, NULL, zero và boundary values.
3. Chạy JdbcTemplate query với RowMapper.
4. Assert từng field và kiểu dữ liệu.
5. Chạy query JOIN để kiểm tra alias.
6. Xác nhận thứ tự và số dòng.
7. Kiểm tra behavior với driver/database giống production khi có khác biệt kiểu.

H2 hữu ích cho test nhanh, nhưng không thay thế hoàn toàn database production nếu SQL, JSON, UUID, timestamp hoặc numeric semantics khác nhau. Với mapping phụ thuộc driver, Testcontainers giúp chạy test gần môi trường thật hơn.

## 28. Kiểm thử RowMapper trong Spring Batch

Khi mapper được dùng bởi JdbcCursorItemReader, cần kiểm tra cả reader:

~~~java
@Bean
JdbcCursorItemReader<CustomerRow> customerReader(
        DataSource dataSource,
        CustomerRowMapper customerRowMapper) {

    return new JdbcCursorItemReaderBuilder<CustomerRow>()
        .name("customerReader")
        .dataSource(dataSource)
        .sql("""
            SELECT customer_id, full_name, email
            FROM customer
            ORDER BY customer_id
            """)
        .rowMapper(customerRowMapper)
        .saveState(true)
        .build();
}
~~~

Một Step integration test có thể xác nhận:

- Reader mở query.
- RowMapper tạo đúng item.
- Processor nhận object đã ánh xạ.
- Writer ghi đúng dữ liệu.
- StepExecution readCount và writeCount phù hợp.
- Cursor được đóng khi Step kết thúc.

Dùng spring-batch-test và JobLauncherTestUtils để chạy Step thật khi cần xác nhận JobRepository, transaction và lifecycle.

### Kiểm tra cả restart

RowMapper không giữ checkpoint, nhưng mapping vẫn phải ổn định khi reader restart. Test nên chạy Step một phần, tạo failure sau một chunk đã commit, restart cùng JobInstance và xác nhận item đọc tiếp có giá trị đúng.

Nếu query hoặc schema thay đổi giữa hai lần chạy, cùng một row có thể được ánh xạ khác. Cần quản lý version query/schema và dữ liệu nguồn phù hợp với khả năng restart.

## 29. RowMapper trong partitioning và chạy song song

Trong partitioning, nhiều worker có thể dùng cùng một RowMapper singleton nếu mapper stateless và dependency thread-safe. Mỗi worker có reader và ExecutionContext riêng.

Một mapper có field currentRow hoặc buffer dùng chung có thể tạo race condition:

~~~java
public class UnsafeMapper implements RowMapper<Customer> {
    private Customer lastCustomer;

    @Override
    public Customer mapRow(ResultSet rs, int rowNum)
            throws SQLException {
        lastCustomer = new Customer(
            rs.getLong("id"),
            rs.getString("name")
        );
        return lastCustomer;
    }
}
~~~

Không cần field lastCustomer. Trả trực tiếp object mới:

~~~java
@Override
public Customer mapRow(ResultSet rs, int rowNum)
        throws SQLException {
    return new Customer(
        rs.getLong("id"),
        rs.getString("name")
    );
}
~~~

Nếu mapper dùng DateTimeFormatter, ObjectMapper hoặc converter, hãy dùng instance immutable/thread-safe hoặc tạo state local theo lần gọi. Không chia sẻ SimpleDateFormat mutable giữa thread.

### Mapper singleton và reader StepScope

Một mẫu phổ biến:

- RowMapper là singleton stateless.
- JdbcCursorItemReader là StepScope nếu cần JobParameters.
- Mỗi partition có reader riêng.
- DataSource và connection pool được quản lý ở application scope.
- DTO bất biến được tạo riêng cho từng dòng.

Cách phân chia này giảm state mutable trong pipeline và làm rõ ownership.

## 30. Không dùng RowMapper để tích lũy dữ liệu

Một lỗi thường gặp là lưu danh sách item trong field của RowMapper để gom dữ liệu nhiều dòng:

~~~java
public class BadOrderMapper implements RowMapper<Order> {

    private final List<OrderLine> lines = new ArrayList<>();

    @Override
    public Order mapRow(ResultSet rs, int rowNum)
            throws SQLException {
        // Thêm line vào field và trả Order khi thấy dòng cuối.
        return null;
    }
}
~~~

Thiết kế này không phù hợp với hợp đồng RowMapper. Mapper được gọi một lần cho mỗi dòng và phải trả object của dòng hiện tại. Nó không biết một nhóm JOIN đã kết thúc ở đâu, trừ khi tự điều khiển cursor hoặc giữ state ngoài contract.

Nếu cần gom nhiều dòng:

- Dùng ResultSetExtractor trong Spring JDBC.
- Dùng SQL aggregation.
- Dùng flat row DTO rồi group trong một component có phạm vi query.
- Dùng processor hoặc service tổng hợp nếu dữ liệu được chia theo chunk và có quy tắc nhóm rõ.

Không giữ group state trong singleton RowMapper.

## 31. Mapping projection và domain entity

RowMapper thường phù hợp với DTO/projection đọc dữ liệu. Không nhất thiết phải tạo JPA entity cho mọi query.

Projection có thể chỉ chứa các cột cần cho batch:

~~~java
public record PaymentExportRow(
    long paymentId,
    String accountNumberMasked,
    BigDecimal amount,
    LocalDate settlementDate
) {
}
~~~

Ưu điểm:

- Không kéo theo lazy-loading behavior.
- Không cần persistence context.
- Có thể chỉ query cột cần thiết.
- Object có thể immutable.
- Mapping dễ kiểm thử và ổn định theo SQL contract.

Nếu cần cập nhật entity, có thể chuyển projection thành command/domain object trong processor hoặc service. Đừng dùng RowMapper để tự quản lý entity lifecycle như một ORM.

## 32. Version hóa mapping contract

Job có thể restart sau khi ứng dụng được deploy phiên bản mới. Nếu SQL alias, enum mapping hoặc kiểu dữ liệu thay đổi, cùng một JobInstance có thể đọc dữ liệu theo quy tắc khác nhau giữa lần đầu và lần restart.

Cần xem xét:

- Query version.
- Schema version.
- Enum code compatibility.
- Timezone conversion.
- Decimal scale.
- Nullability.
- Sort key và paging order.
- Thay đổi projection.

Nếu thay đổi ảnh hưởng kết quả nghiệp vụ, có thể lưu mapping version hoặc batch version trong JobParameters/ExecutionContext. Khi restart, xác nhận version phù hợp hoặc fail với thông báo rõ ràng.

Không âm thầm thay đổi cách diễn giải một cột trong khi Job cũ còn khả năng restart.

## 33. Hiệu năng của RowMapper

RowMapper được gọi một lần cho mỗi dòng, vì vậy thao tác bên trong cần gọn và có chi phí dự đoán được.

Nên:

- Chỉ đọc các cột cần thiết.
- Dùng SQL projection thay vì SELECT *.
- Dùng alias ổn định.
- Tái sử dụng converter immutable.
- Tránh tạo formatter hoặc parser nặng cho mỗi dòng nếu có thể tái sử dụng an toàn.
- Tránh query bổ sung cho từng row.
- Giới hạn kích thước LOB và JSON.
- Dùng fetch size/page size phù hợp.
- Đo hiệu năng trên dữ liệu đại diện.

Không nên tối ưu bằng cách giữ object mutable dùng chung để tránh allocation. Object mới cho mỗi row là semantics tự nhiên của mapper; JVM có thể tối ưu nhiều allocation ngắn hạn. Ưu tiên tính đúng và dễ hiểu, sau đó đo bottleneck thực tế.

### Tránh N+1 query trong mapper

Nếu mỗi mapRow gọi repository để lấy thêm thông tin, một query 100.000 dòng có thể tạo thêm 100.000 query. Điều này thường chậm và khó điều khiển transaction.

Thay vào đó, dùng JOIN, query theo nhóm key hoặc một bước enrichment theo batch. Nếu dữ liệu bổ sung có thể thay đổi, hãy snapshot hoặc xác định consistency policy.

## 34. Checklist thiết kế RowMapper bất biến

Trước khi dùng mapper trong batch, xác định:

1. **Projection:** query trả những cột nào và alias nào?
2. **Một row:** một dòng SQL tương ứng với một object nào?
3. **State:** mapper có field mutable không? Nếu có, có thực sự cần không?
4. **Output:** object có immutable sâu hay cần defensive copy?
5. **SQL NULL:** wrapper, wasNull hoặc invariant nào được dùng?
6. **Types:** BigDecimal, enum, date/time, UUID, JSON và LOB được chuyển đổi ra sao?
7. **JOIN:** một dòng ánh xạ một object hay cần gom nhiều dòng?
8. **Resource:** object trả về có phụ thuộc ResultSet/Connection không?
9. **Errors:** dữ liệu không hợp lệ được fail, skip hay chuyển thành reject?
10. **Concurrency:** mapper và dependency có an toàn khi dùng đồng thời không?
11. **Restart:** mapping contract có ổn định giữa lần chạy và restart không?
12. **Tests:** có unit test, SQL integration test và Step test cần thiết chưa?

## 35. Những lỗi thường gặp

### Giữ dữ liệu dòng hiện tại trong field

Mapper singleton có thể mang dữ liệu từ lần gọi trước hoặc race giữa thread. Dùng biến local và trả object mới.

### Trả object mutable rồi để nhiều component sửa

Processor có thể sửa item và ảnh hưởng component khác. Dùng record/class immutable hoặc tạo bản sao rõ ràng.

### Chỉ dùng final cho collection

Field final chỉ cố định reference. Dùng List.copyOf, Map.copyOf hoặc defensive copy cho array và object lồng.

### Quên wasNull khi dùng primitive getter

SQL NULL bị biến thành 0 hoặc false. Dùng wrapper qua getObject hoặc gọi wasNull ngay sau getter.

### Chuyển tiền qua double

Có thể mất độ chính xác. Dùng getBigDecimal.

### Dùng tên cột trùng trong JOIN

Mapper có thể đọc nhầm label. Dùng alias riêng và SELECT projection rõ ràng.

### Gọi rs.next trong mapRow

Framework quản lý cursor. Mapper không được di chuyển ResultSet.

### Đóng ResultSet hoặc Connection trong mapper

Resource thuộc JdbcTemplate hoặc reader. Để framework quản lý lifecycle.

### Giữ Blob/Clob/stream trong item

Object có thể phụ thuộc connection đã đóng. Materialize dữ liệu phù hợp hoặc dùng quy trình streaming riêng.

### Gom parent-child bằng field trong RowMapper

Mapper không biết ranh giới group và không thread-safe. Dùng ResultSetExtractor hoặc aggregation component.

### Gọi database/API trong mapRow

Tạo N+1 và side effect có thể lặp khi retry. Enrich ở query hoặc processor theo batch.

### Dùng mapper tự động mà không test null/type

Tên property khớp không bảo đảm semantics SQL NULL, enum và timestamp đúng. Kiểm thử với driver/database thực tế.

## 36. Quy trình triển khai RowMapper bất biến

Có thể triển khai theo trình tự:

1. **Thiết kế SQL projection:** liệt kê cột cần thiết, alias rõ và thứ tự ổn định.
2. **Tạo DTO bất biến:** dùng record hoặc class final với constructor đầy đủ.
3. **Viết mapper stateless:** không giữ row state, ResultSet hoặc cursor trong field.
4. **Ánh xạ null có chủ đích:** dùng wrapper/getObject hoặc wasNull đúng thời điểm.
5. **Chuyển kiểu rõ ràng:** BigDecimal, java.time, enum, UUID, JSON và LOB theo schema.
6. **Xử lý JOIN đúng abstraction:** RowMapper cho một row; ResultSetExtractor cho nhiều row thành một kết quả.
7. **Đăng ký mapper:** có thể dùng singleton nếu mapper và dependency thread-safe.
8. **Kết nối với Batch reader:** reader sở hữu checkpoint và resource; mapper chỉ ánh xạ.
9. **Kiểm thử:** mock ResultSet cho mapping, database test cho driver/SQL và Step test cho lifecycle.
10. **Giữ contract ổn định:** quản lý thay đổi schema/query trong khi Job cũ có thể restart.

## 37. Những điểm cần nhớ

- RowMapper.mapRow nhận dòng ResultSet hiện tại và trả về một object.
- RowMapper không gọi rs.next(), không đóng ResultSet và không giữ cursor.
- Mapper nên stateless, không lưu dữ liệu của dòng hiện tại trong field.
- Object đầu ra nên immutable bằng record hoặc class final với field final.
- Collection và array cần defensive copy để đạt immutability sâu.
- SQL NULL cần được phân biệt với zero/false bằng wrapper hoặc wasNull.
- Dùng BigDecimal cho DECIMAL và kiểu java.time cho ngày giờ.
- Enum, UUID và JSON cần mapping rõ ràng; không tự chọn giá trị mặc định cho code không hợp lệ.
- JOIN một dòng thành một projection phù hợp với RowMapper; gom parent-child nhiều dòng nên dùng ResultSetExtractor hoặc aggregation.
- JdbcCursorItemReader và JdbcPagingItemReader quản lý cursor/page/checkpoint; RowMapper không sở hữu state restart.
- Mapper stateless có thể là singleton dùng chung nếu dependency thread-safe.
- Không gọi API/database, ghi file hoặc tạo side effect trong mapRow.
- Không trả object phụ thuộc ResultSet hoặc connection đã đóng.
- Kiểm thử cả mapper riêng, SQL/driver thực tế và Step integration khi cần.
- Giữ mapping contract ổn định trong suốt JobInstance có thể restart.

RowMapper bất biến giúp mỗi dòng database được chuyển thành một snapshot dữ liệu độc lập, dễ dự đoán và an toàn khi tái sử dụng. Khi mapper không giữ state, object đầu ra bảo vệ được dữ liệu và reader chịu trách nhiệm checkpoint/resource, JDBC processing trong Spring Batch trở nên dễ kiểm thử, dễ mở rộng và đáng tin cậy hơn.

