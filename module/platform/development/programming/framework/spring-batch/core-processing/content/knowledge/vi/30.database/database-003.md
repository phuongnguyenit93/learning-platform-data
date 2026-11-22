# RowMapper và mapper domain trong Spring Batch

Trong Spring Batch, reader thường lấy dữ liệu từ database rồi chuyển từng dòng kết quả thành một object để processor và writer xử lý. Với các reader dựa trên Spring JDBC, RowMapper đảm nhiệm bước chuyển một hàng trong ResultSet thành object Java. Sau bước đọc dữ liệu, ứng dụng đôi khi còn cần chuyển object persistence đó thành domain model có ý nghĩa nghiệp vụ. Công việc thứ hai thường được gọi là domain mapping.

Hai loại mapper này có liên quan nhưng có trách nhiệm khác nhau. RowMapper hiểu cấu trúc hàng dữ liệu JDBC; domain mapper hiểu mô hình và quy tắc của nghiệp vụ. Tách đúng trách nhiệm giúp reader dễ kiểm thử, processor không phụ thuộc cấu trúc cột database và batch job có thể thay đổi schema hoặc domain model với ít ảnh hưởng hơn.

## 1. RowMapper là gì?

RowMapper là interface của Spring JDBC dùng để ánh xạ một hàng trong ResultSet thành một object Java. Interface có một phương thức:

~~~java
public interface RowMapper<T> {
    T mapRow(ResultSet rs, int rowNum) throws SQLException;
}
~~~

Spring gọi mapRow cho từng hàng mà query trả về. Tham số:

- rs là ResultSet đang trỏ đến hàng hiện tại.
- rowNum là số thứ tự hàng trong kết quả, bắt đầu từ 0.
- Giá trị trả về là object đại diện cho hàng đó.

RowMapper không gọi rs.next(). Vòng lặp ResultSet do JdbcTemplate hoặc reader quản lý. Mapper chỉ đọc các cột của hàng hiện tại và tạo object. Nó cũng không có trách nhiệm đóng ResultSet, Statement hoặc Connection; resource lifecycle thuộc về thành phần thực hiện query.

Ví dụ, một hàng trong bảng orders có thể được ánh xạ thành OrderRow:

~~~java
public record OrderRow(
    long id,
    String customerId,
    BigDecimal total,
    LocalDate businessDate
) {}
~~~

RowMapper tương ứng:

~~~java
public class OrderRowMapper implements RowMapper<OrderRow> {

    @Override
    public OrderRow mapRow(ResultSet rs, int rowNum) throws SQLException {
        return new OrderRow(
            rs.getLong("id"),
            rs.getString("customer_id"),
            rs.getBigDecimal("total"),
            rs.getObject("business_date", LocalDate.class)
        );
    }
}
~~~

Mỗi hàng tạo một object mới. Reader có thể đưa object đó cho processor để validation, enrich hoặc chuyển đổi tiếp.

## 2. RowMapper được dùng ở đâu trong Spring Batch?

Các reader dựa trên Spring JDBC thường nhận một RowMapper để chuyển dữ liệu query thành item:

- JdbcCursorItemReader đọc qua một cursor JDBC.
- JdbcPagingItemReader đọc theo từng trang bằng các truy vấn phân trang.
- JdbcTemplate cũng dùng RowMapper khi truy vấn dữ liệu ngoài reader của Spring Batch.

Ví dụ cấu hình JdbcCursorItemReader:

~~~java
@Bean
@StepScope
JdbcCursorItemReader<OrderRow> orderReader(DataSource dataSource) {
    return new JdbcCursorItemReaderBuilder<OrderRow>()
        .name("orderReader")
        .dataSource(dataSource)
        .sql("""
            select id, customer_id, total, business_date
            from orders
            where status = ?
            order by id
            """)
        .preparedStatementSetter(ps -> ps.setString(1, "READY"))
        .rowMapper(new OrderRowMapper())
        .fetchSize(500)
        .saveState(true)
        .build();
}
~~~

Trong cấu hình này, reader quản lý việc thực thi query và lấy từng hàng; OrderRowMapper chỉ chuyển hàng hiện tại thành OrderRow. Reader không cần biết cách domain model được xây dựng sau đó.

Với JdbcPagingItemReader, RowMapper có cùng vai trò. Khác biệt nằm ở cách reader lấy dữ liệu theo trang, không phải cách ánh xạ một hàng:

~~~java
@Bean
@StepScope
JdbcPagingItemReader<OrderRow> pagingOrderReader(
        DataSource dataSource,
        PagingQueryProvider queryProvider) {

    return new JdbcPagingItemReaderBuilder<OrderRow>()
        .name("pagingOrderReader")
        .dataSource(dataSource)
        .queryProvider(queryProvider)
        .pageSize(500)
        .rowMapper(new OrderRowMapper())
        .saveState(true)
        .build();
}
~~~

RowMapper không quyết định page size, sort key hoặc checkpoint. Những phần đó thuộc cấu hình và lifecycle của paging reader.

## 3. Viết RowMapper tùy chỉnh

Custom RowMapper phù hợp khi mapping có quy tắc rõ ràng, cần xử lý kiểu dữ liệu đặc biệt hoặc tên cột không khớp với tên thuộc tính Java.

Ví dụ bảng orders lưu cột snake_case, trong khi Java model dùng camelCase:

~~~sql
select
    order_id,
    customer_code,
    gross_amount,
    created_at
from orders
~~~

Mapper:

~~~java
public class OrderRowMapper implements RowMapper<OrderRow> {

    @Override
    public OrderRow mapRow(ResultSet rs, int rowNum) throws SQLException {
        return new OrderRow(
            rs.getLong("order_id"),
            rs.getString("customer_code"),
            rs.getBigDecimal("gross_amount"),
            rs.getTimestamp("created_at").toInstant()
        );
    }
}
~~~

Việc đọc cột theo tên làm mapping dễ hiểu và ít phụ thuộc thứ tự cột trong SELECT. Nếu query thay đổi alias, mapper và query cần được cập nhật đồng bộ.

Có thể dùng column alias để làm rõ ý nghĩa dữ liệu:

~~~sql
select
    o.id as order_id,
    o.customer_code as customer_id,
    o.gross_amount as total_amount
from orders o
~~~

Sau đó mapper đọc đúng alias:

~~~java
return new OrderRow(
    rs.getLong("order_id"),
    rs.getString("customer_id"),
    rs.getBigDecimal("total_amount")
);
~~~

Alias đặc biệt hữu ích khi join nhiều bảng có cột trùng tên như id, status hoặc created_at.

## 4. BeanPropertyRowMapper và giới hạn của mapping tự động

Spring JDBC cung cấp BeanPropertyRowMapper để ánh xạ cột theo tên sang property Java. Theo mặc định, mapper có thể chuyển tên cột dạng underscore thành camelCase, ví dụ customer_id sang customerId.

~~~java
RowMapper<OrderBean> mapper =
    new BeanPropertyRowMapper<>(OrderBean.class);
~~~

Model Java cần có các property tương thích và cách khởi tạo mà mapper hỗ trợ:

~~~java
public class OrderBean {

    private long id;
    private String customerId;
    private BigDecimal total;

    public OrderBean() {
    }

    public long getId() {
        return id;
    }

    public void setId(long id) {
        this.id = id;
    }

    public String getCustomerId() {
        return customerId;
    }

    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public void setTotal(BigDecimal total) {
        this.total = total;
    }
}
~~~

Mapping tự động giảm code lặp nhưng không thay thế việc thiết kế schema/model. Những hạn chế cần cân nhắc:

- Tên cột và property phải khớp theo quy tắc mapping.
- Model cần hỗ trợ cách khởi tạo mà mapper yêu cầu.
- Mapping tự động không diễn đạt tốt các quy tắc nghiệp vụ.
- Query join có thể trả về cột trùng tên hoặc alias không rõ ràng.
- Kiểu dữ liệu đặc biệt và null có thể cần xử lý tường minh.
- Lỗi sai tên cột/property có thể chỉ xuất hiện khi query chạy.

Với immutable object, constructor-based mapping hoặc record, có thể cân nhắc DataClassRowMapper ở phiên bản Spring Framework hỗ trợ. Khi mapping có nhiều quy tắc hoặc cần độ rõ ràng cao, custom RowMapper thường dễ đọc và dễ kiểm soát hơn.

## 5. Xử lý SQL NULL đúng cách

Một lỗi thường gặp là dùng getter kiểu primitive rồi không kiểm tra SQL NULL. Ví dụ ResultSet.getLong() trả về 0 nếu cột là SQL NULL. Nếu 0 cũng là một giá trị hợp lệ, ứng dụng không thể phân biệt hai trường hợp nếu không gọi wasNull().

Ví dụ:

~~~java
long customerNumber = rs.getLong("customer_number");
Long nullableCustomerNumber =
    rs.wasNull() ? null : customerNumber;
~~~

Với JDBC driver hỗ trợ JDBC 4.1 trở lên, có thể dùng getObject với kiểu wrapper:

~~~java
Long customerNumber = rs.getObject("customer_number", Long.class);
Integer retryCount = rs.getObject("retry_count", Integer.class);
~~~

Với kiểu tham chiếu như String, BigDecimal và Timestamp, getter thường trả null nếu SQL column là NULL. Tuy nhiên, hãy xác định rõ domain model cho phép null hay không. Nếu trường bắt buộc bị null, có thể tạo một persistence row chứa giá trị nullable rồi để domain mapper phát hiện và ném lỗi validation có ý nghĩa.

Không tự thay mọi null bằng 0, chuỗi rỗng hoặc ngày mặc định nếu điều đó làm thay đổi ý nghĩa nghiệp vụ. Một số trường có thể cần default, nhưng default nên được thể hiện trong quy tắc domain rõ ràng.

## 6. Chuyển đổi kiểu dữ liệu ngày giờ và số

JDBC hỗ trợ nhiều kiểu SQL và Java. Nên dùng kiểu Java phản ánh đúng ý nghĩa dữ liệu:

| SQL type | Java type thường dùng | Lưu ý |
| --- | --- | --- |
| DATE | LocalDate | Chỉ có ngày, không có giờ/múi giờ |
| TIME | LocalTime | Chỉ có giờ trong ngày |
| TIMESTAMP | LocalDateTime hoặc Instant | Cần xác định quy ước múi giờ của dữ liệu |
| DECIMAL/NUMERIC | BigDecimal | Tránh chuyển qua double cho số tiền |
| BIGINT | Long hoặc long | Chọn nullable hay non-null theo schema |
| BOOLEAN | Boolean hoặc boolean | Kiểm tra null nếu cột cho phép |

Ví dụ:

~~~java
LocalDate businessDate =
    rs.getObject("business_date", LocalDate.class);

LocalDateTime createdAt =
    rs.getObject("created_at", LocalDateTime.class);

BigDecimal amount = rs.getBigDecimal("amount");
~~~

Không giả định mọi driver xử lý TIMESTAMP, timezone hoặc kiểu vendor-specific giống nhau. Với Oracle, PostgreSQL hoặc SQL Server, kiểm tra JDBC driver và mapping thực tế trong integration test.

Đối với tiền tệ, dùng BigDecimal và xác định scale/rounding ở domain layer. RowMapper nên giữ chính xác giá trị JDBC; đừng tự làm tròn chỉ vì cột đang hiển thị với số chữ số thập phân cố định.

## 7. Ánh xạ enum và trạng thái

Database thường lưu enum dưới dạng VARCHAR hoặc mã số. Không nên dùng Enum.valueOf trực tiếp nếu dữ liệu có thể chứa giá trị cũ, alias hoặc mã nghiệp vụ khác tên enum.

Nếu DB lưu đúng tên enum:

~~~java
OrderStatus status =
    OrderStatus.valueOf(rs.getString("status"));
~~~

Nếu DB lưu mã riêng:

~~~java
public enum OrderStatus {
    READY("R"),
    PROCESSING("P"),
    COMPLETED("C");

    private final String databaseCode;

    OrderStatus(String databaseCode) {
        this.databaseCode = databaseCode;
    }

    public static OrderStatus fromDatabaseCode(String code) {
        return Arrays.stream(values())
            .filter(value -> value.databaseCode.equals(code))
            .findFirst()
            .orElseThrow(() ->
                new IllegalArgumentException("Unknown order status: " + code)
            );
    }
}
~~~

RowMapper gọi hàm chuyển mã:

~~~java
OrderStatus status =
    OrderStatus.fromDatabaseCode(rs.getString("status"));
~~~

Lỗi mã không biết cần được phân loại có chủ đích. Nếu dữ liệu sai thuộc một record và nghiệp vụ cho phép loại bỏ, domain mapping có thể ném một exception validation riêng để step xử lý bằng skip policy. Nếu mã lạ cho thấy schema hoặc deployment không tương thích, step có thể cần fail để tránh bỏ qua hàng loạt.

## 8. Mapping dữ liệu join và quan hệ

Một query join có thể trả về các cột từ nhiều bảng. Hãy alias cột để phân biệt rõ nguồn:

~~~sql
select
    o.id as order_id,
    o.total as order_total,
    c.id as customer_id,
    c.name as customer_name
from orders o
join customers c on c.id = o.customer_id
~~~

RowMapper có thể tạo một read model phẳng:

~~~java
public record OrderWithCustomerRow(
    long orderId,
    BigDecimal orderTotal,
    String customerId,
    String customerName
) {}
~~~

~~~java
public class OrderWithCustomerRowMapper
        implements RowMapper<OrderWithCustomerRow> {

    @Override
    public OrderWithCustomerRow mapRow(ResultSet rs, int rowNum)
            throws SQLException {
        return new OrderWithCustomerRow(
            rs.getLong("order_id"),
            rs.getBigDecimal("order_total"),
            rs.getString("customer_id"),
            rs.getString("customer_name")
        );
    }
}
~~~

Không nên chạy thêm một query cho từng hàng ngay trong mapRow để lấy customer hoặc các collection liên quan. Cách đó tạo N+1 queries: một query đọc orders rồi một query bổ sung cho mỗi order. Hãy cân nhắc join, batch lookup hoặc một bước enrich riêng có kiểm soát.

Nếu join tạo nhiều hàng cho cùng một aggregate cha, một RowMapper đơn giản không tự nhóm các hàng đó thành một aggregate có collection con. Có thể dùng ResultSetExtractor cho phép xử lý toàn bộ ResultSet, hoặc để query trả read model phẳng rồi nhóm ở một bước riêng. Chọn công cụ theo hình dạng dữ liệu.

## 9. RowMapper và ResultSetExtractor khác nhau

RowMapper phù hợp khi mỗi hàng tương ứng với một item độc lập. ResultSetExtractor phù hợp khi cần xem toàn bộ ResultSet để tạo một object hoặc cấu trúc tổng hợp:

| Thành phần | Đơn vị xử lý | Ví dụ |
| --- | --- | --- |
| RowMapper | Một hàng | Một OrderRow |
| ResultSetExtractor | Toàn bộ ResultSet | Một Order kèm danh sách nhiều dòng order item |
| RowCallbackHandler | Một hàng, không cần trả object | Đọc và ghi trực tiếp từng hàng vào một sink |

Trong Spring Batch, reader thường muốn trả một item cho mỗi lần read(), vì vậy RowMapper tự nhiên với cursor/paging reader. Nếu mỗi item cần tổng hợp nhiều hàng, hãy xác định ranh giới aggregate trong query hoặc dùng reader/custom component có khả năng nhóm dữ liệu rõ ràng.

Không dùng RowMapper để tự gọi rs.next() nhằm gom nhiều hàng. Việc đó phá vỡ hợp đồng vì reader/JdbcTemplate đang quản lý vị trí ResultSet.

## 10. Domain mapper là gì?

Domain mapper chuyển đổi dữ liệu từ một representation kỹ thuật hoặc persistence model sang domain model mà nghiệp vụ sử dụng. Nó thường không phải interface của Spring JDBC; đây là thành phần do ứng dụng định nghĩa theo kiến trúc.

Ví dụ RowMapper tạo một DTO phản ánh dữ liệu database:

~~~java
public record OrderRow(
    long id,
    String customerCode,
    BigDecimal total,
    String statusCode
) {}
~~~

Domain mapper chuyển DTO đó thành domain object:

~~~java
public class OrderDomainMapper {

    public Order toDomain(OrderRow row) {
        CustomerId customerId = CustomerId.of(row.customerCode());
        Money total = Money.of(row.total(), Currency.getInstance("VND"));
        OrderStatus status = OrderStatus.fromDatabaseCode(row.statusCode());

        return Order.rehydrate(
            OrderId.of(row.id()),
            customerId,
            total,
            status
        );
    }
}
~~~

Trong ví dụ:

- RowMapper hiểu tên cột và kiểu JDBC.
- OrderRow phản ánh dữ liệu đã đọc.
- Domain mapper chuyển mã và giá trị thành value object.
- Domain model bảo vệ invariant và thể hiện ý nghĩa nghiệp vụ.

Tách domain mapper giúp domain model không phải biết tên cột SQL hoặc ResultSet.

## 11. Có nên ánh xạ ResultSet trực tiếp thành domain object?

Không có một quy tắc bắt buộc rằng RowMapper luôn phải tạo DTO trung gian. Nếu query đơn giản và domain object có constructor/factory phù hợp, RowMapper có thể tạo trực tiếp domain object:

~~~java
public class OrderDomainRowMapper implements RowMapper<Order> {

    @Override
    public Order mapRow(ResultSet rs, int rowNum) throws SQLException {
        return Order.rehydrate(
            OrderId.of(rs.getLong("id")),
            CustomerId.of(rs.getString("customer_id")),
            Money.of(
                rs.getBigDecimal("total"),
                Currency.getInstance("VND")
            ),
            OrderStatus.fromDatabaseCode(rs.getString("status"))
        );
    }
}
~~~

Cách này giảm một lớp mapping và phù hợp khi domain object chính là item mà batch cần xử lý. Tuy nhiên, RowMapper khi đó phụ thuộc vào domain API và phải xử lý cả chuyển đổi JDBC lẫn khởi tạo domain.

Nên tách DTO persistence và domain mapper khi:

- Một query/read model có thể được dùng bởi nhiều use case.
- Database schema và domain model có nhịp thay đổi khác nhau.
- Domain model có invariant hoặc factory phức tạp.
- Cần kiểm thử mapping dữ liệu và quy tắc nghiệp vụ riêng.
- Có nhiều nguồn dữ liệu cùng tạo ra một domain object.

Có thể map trực tiếp khi dữ liệu đơn giản, mapping rõ ràng và không tạo coupling khó kiểm soát. Mục tiêu là phân định trách nhiệm dễ hiểu, không phải tạo thêm lớp cho mọi trường hợp.

## 12. Đặt RowMapper và domain mapper ở đâu trong batch pipeline?

Một pipeline phổ biến:

~~~text
Database
   |
   v
JdbcCursorItemReader / JdbcPagingItemReader
   |
   v
RowMapper
   |
   v
Persistence row / read DTO
   |
   v
Domain mapper
   |
   v
Domain object
   |
   v
ItemProcessor
   |
   v
ItemWriter
~~~

Có thể đặt domain mapper bên trong processor nếu việc chuyển đổi là một phần của bước xử lý item:

~~~java
public class OrderProcessor
        implements ItemProcessor<OrderRow, EnrichedOrder> {

    private final OrderDomainMapper domainMapper;
    private final OrderEnrichmentService enrichmentService;

    public OrderProcessor(
            OrderDomainMapper domainMapper,
            OrderEnrichmentService enrichmentService) {
        this.domainMapper = domainMapper;
        this.enrichmentService = enrichmentService;
    }

    @Override
    public EnrichedOrder process(OrderRow row) {
        Order order = domainMapper.toDomain(row);
        return enrichmentService.enrich(order);
    }
}
~~~

Nếu reader có thể trả trực tiếp domain object, processor chỉ cần xử lý phần enrich. Nếu mapping có thể thất bại do dữ liệu record không hợp lệ, hãy phân loại exception rõ ràng để retry, skip hoặc fail theo nghiệp vụ.

## 13. Không đặt logic nghiệp vụ nặng trong RowMapper

RowMapper được gọi trong quá trình đọc từng hàng. Nó nên tập trung vào việc đọc cột và chuyển đổi dữ liệu cơ bản. Tránh thực hiện các công việc sau trong mapRow:

- Gọi HTTP service hoặc message broker.
- Gọi thêm query cho từng row để tải quan hệ.
- Ghi database hoặc tạo side effect.
- Thực hiện workflow nghiệp vụ nhiều bước.
- Giữ ResultSet, Connection hoặc Statement trong field để dùng sau.
- Tích lũy tất cả item trong một collection toàn cục.

Nếu mapper gọi API cho mỗi row, reader sẽ trở thành nơi điều phối integration và có thể tạo N+1 network calls. Việc retry/read lại cũng có thể lặp side effect. Chuyển phần enrich sang processor hoặc service riêng, nơi retry và transaction behavior có thể được cấu hình có chủ đích.

RowMapper nên đủ nhanh và stateless. Tạo object mới cho hàng hiện tại, trả về và để reader tiếp tục.

## 14. RowMapper cần stateless và thread-safe

RowMapper thường được cấu hình như một object dùng lại trong reader hoặc JdbcTemplate. Nếu có nhiều thread cùng gọi mapper, field mutable có thể bị chia sẻ và làm dữ liệu hàng này lẫn sang hàng khác.

Không nên:

~~~java
public class UnsafeOrderRowMapper implements RowMapper<OrderRow> {

    private String currentCustomer;

    @Override
    public OrderRow mapRow(ResultSet rs, int rowNum) throws SQLException {
        currentCustomer = rs.getString("customer_id");
        return new OrderRow(
            rs.getLong("id"),
            currentCustomer,
            rs.getBigDecimal("total"),
            rs.getObject("business_date", LocalDate.class)
        );
    }
}
~~~

Nên dùng biến local:

~~~java
public class SafeOrderRowMapper implements RowMapper<OrderRow> {

    @Override
    public OrderRow mapRow(ResultSet rs, int rowNum) throws SQLException {
        String customerId = rs.getString("customer_id");
        BigDecimal total = rs.getBigDecimal("total");
        LocalDate date = rs.getObject("business_date", LocalDate.class);

        return new OrderRow(
            rs.getLong("id"),
            customerId,
            total,
            date
        );
    }
}
~~~

Mapper stateless cũng dễ test hơn vì kết quả chỉ phụ thuộc vào hàng đầu vào. Nếu cần cache reference data, đưa cache vào một service riêng có concurrency control và lifecycle rõ ràng; đừng dùng field của RowMapper để giữ item hiện tại.

## 15. Xử lý lỗi mapping và phân loại exception

Lỗi mapping có thể xuất phát từ nhiều nguyên nhân:

- Query không trả về cột mà mapper yêu cầu.
- Cột có SQL NULL nhưng domain bắt buộc non-null.
- Giá trị enum/mã trạng thái không được nhận diện.
- Driver không hỗ trợ chuyển kiểu theo cách được giả định.
- Dữ liệu bị sai format hoặc vượt giới hạn.
- Schema và ứng dụng không tương thích sau một lần deploy.

Không nên bắt tất cả SQLException rồi trả về object rỗng. Làm vậy biến dữ liệu lỗi thành dữ liệu có vẻ hợp lệ và khiến processor/writer khó phát hiện vấn đề.

Có thể bọc lỗi validation record bằng exception có ý nghĩa:

~~~java
public class InvalidOrderRowException extends RuntimeException {
    public InvalidOrderRowException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Tuy nhiên, lỗi thiếu cột do query sai thường là lỗi lập trình/schema và nên làm step fail. Lỗi một giá trị record không hợp lệ có thể được skip nếu nghiệp vụ cho phép. Hãy phân biệt hai nhóm thay vì cấu hình skip rộng cho mọi exception mapping.

Với exception checked như SQLException, Spring JDBC thường truyền qua cơ chế exception translation hoặc reader bọc thành exception phù hợp. Kiểm tra loại exception thực tế mà step nhận được khi cấu hình retry/skip.

## 16. Mapping trong JdbcCursorItemReader và restart

RowMapper không lưu checkpoint. JdbcCursorItemReader quản lý cursor và trạng thái đọc theo lifecycle của reader. Nếu bật saveState, reader có thể lưu trạng thái cần thiết để restart theo cấu hình.

Ví dụ:

~~~java
new JdbcCursorItemReaderBuilder<OrderRow>()
    .name("orderReader")
    .dataSource(dataSource)
    .sql("select id, customer_id, total from orders order by id")
    .rowMapper(orderRowMapper)
    .saveState(true)
    .build();
~~~

Một mapper tốt không phụ thuộc vào rowNum như business identity. rowNum chỉ là vị trí trong kết quả hiện tại; query thay đổi, thứ tự thay đổi hoặc reader restart có thể khiến vị trí không còn là định danh ổn định của record.

Nếu processor hoặc writer cần nhận diện record để idempotency, dùng primary key/business key từ hàng dữ liệu. Không lưu object ResultSet hoặc phụ thuộc vào rowNum để khôi phục nghiệp vụ.

Đối với reader cursor, resource database được giữ trong vòng đời step. RowMapper không được đóng connection hoặc ResultSet; làm vậy có thể khiến reader không thể đọc hàng tiếp theo.

## 17. Mapping trong JdbcPagingItemReader và sort key

JdbcPagingItemReader thực hiện nhiều query theo trang. RowMapper vẫn chỉ map từng hàng, nhưng paging reader cần sort key ổn định để phân trang và restart chính xác.

Ví dụ query có sort key là id:

~~~sql
select id, customer_id, total
from orders
where status = :status
order by id
~~~

Sort key nên duy nhất hoặc kết hợp nhiều cột để tạo thứ tự ổn định. Nếu sort theo created_at mà nhiều hàng có cùng timestamp, cần thêm id làm tie-breaker. Nếu dữ liệu nguồn thay đổi trong lúc job chạy, cần hiểu ảnh hưởng của insert/update đến các trang.

RowMapper không giải quyết vấn đề paging order. Nó chỉ map cột id, customer_id và total. Reader/query provider quản lý sort key, page boundary và checkpoint.

Không dùng rowNum làm khóa paging vì rowNum có thể bắt đầu lại ở mỗi trang và không ổn định qua restart.

## 18. Domain mapper và invariant của domain model

Domain mapper là nơi chuyển dữ liệu kỹ thuật thành khái niệm nghiệp vụ. Nó có thể tạo value object, kiểm tra invariant hoặc gọi factory để tái tạo aggregate từ trạng thái đã lưu.

Ví dụ Money:

~~~java
public record Money(BigDecimal amount, Currency currency) {

    public Money {
        Objects.requireNonNull(amount);
        Objects.requireNonNull(currency);
        if (amount.signum() < 0) {
            throw new IllegalArgumentException("Amount cannot be negative");
        }
    }
}
~~~

Domain mapper:

~~~java
public class PaymentRowMapper {

    public Payment toDomain(PaymentRow row) {
        Money amount = new Money(
            row.amount(),
            Currency.getInstance(row.currencyCode())
        );

        return Payment.rehydrate(
            PaymentId.of(row.paymentId()),
            amount,
            PaymentStatus.fromCode(row.statusCode())
        );
    }
}
~~~

Nếu domain constructor/factory từ chối dữ liệu, mapper cần để exception thể hiện rõ record không hợp lệ. Đừng bỏ qua invariant để tạo object không nhất quán chỉ nhằm tránh lỗi batch.

Một số domain model phân biệt factory tạo entity mới với phương thức rehydrate khôi phục trạng thái đã lưu. Domain mapper nên dùng API đúng mục đích thay vì gọi setter để sửa từng field rồi bỏ qua invariant.

## 19. Mapping quan hệ một-nhiều

Một order có thể có nhiều order line. Query join trả một hàng cho mỗi line, nên cùng order ID xuất hiện nhiều lần:

~~~sql
select
    o.id as order_id,
    o.customer_id,
    l.id as line_id,
    l.product_id,
    l.quantity
from orders o
join order_line l on l.order_id = o.id
order by o.id, l.id
~~~

RowMapper có thể tạo một OrderLineRow cho mỗi hàng. Nhưng nếu item cần là cả Order với danh sách lines, cần nhóm các hàng theo order ID.

Có thể dùng ResultSetExtractor khi query trả toàn bộ nhóm cần thiết:

~~~java
Map<Long, OrderAggregateRow> orders =
    jdbcTemplate.query(sql, rs -> {
        Map<Long, OrderAggregateRow> result = new LinkedHashMap<>();
        while (rs.next()) {
            long orderId = rs.getLong("order_id");
            OrderAggregateRow order = result.computeIfAbsent(
                orderId,
                id -> new OrderAggregateRow(
                    id,
                    rsString(rs, "customer_id")
                )
            );
            order.addLine(
                rs.getLong("line_id"),
                rs.getString("product_id"),
                rs.getInt("quantity")
            );
        }
        return result;
    });
~~~

Đây là ví dụ khái niệm; helper rsString cần xử lý SQLException phù hợp trong code thực tế. Với batch lớn, không nên tải toàn bộ bảng vào Map trong một lần. Có thể query theo nhóm order, dùng custom reader gom một aggregate tại một thời điểm hoặc dùng một bước staging phù hợp.

Ranh giới item của batch nên được xác định trước: một row, một order hay một nhóm record. Ranh giới đó ảnh hưởng commit interval, retry, skip và memory usage.

## 20. Kiểm thử RowMapper độc lập

RowMapper có thể được unit test mà không cần khởi chạy toàn bộ job. Có thể dùng Mock ResultSet hoặc ResultSet thực từ database test. Test với database thật thường hữu ích hơn khi cần xác nhận kiểu dữ liệu và hành vi của JDBC driver.

Các trường hợp nên kiểm tra:

- Cột bắt buộc được ánh xạ đúng.
- SQL NULL được giữ thành null hoặc được xử lý theo quy tắc đã định.
- Decimal không bị mất độ chính xác.
- Date/time chuyển sang Java type đúng.
- Enum/code hợp lệ được ánh xạ đúng.
- Enum/code lạ tạo exception có ý nghĩa.
- Alias của query khớp tên cột mapper đọc.
- Mỗi lần gọi trả object mới, không tái sử dụng mutable object của hàng trước.

Ví dụ test logic mapping:

~~~java
@Test
void mapsOrderColumns() throws SQLException {
    ResultSet rs = mock(ResultSet.class);
    when(rs.getLong("id")).thenReturn(42L);
    when(rs.getString("customer_id")).thenReturn("C-100");
    when(rs.getBigDecimal("total"))
        .thenReturn(new BigDecimal("125.50"));
    when(rs.getObject("business_date", LocalDate.class))
        .thenReturn(LocalDate.of(2026, 11, 15));

    OrderRow row = new OrderRowMapper().mapRow(rs, 0);

    assertThat(row.id()).isEqualTo(42L);
    assertThat(row.customerId()).isEqualTo("C-100");
    assertThat(row.total()).isEqualByComparingTo("125.50");
    assertThat(row.businessDate())
        .isEqualTo(LocalDate.of(2026, 11, 15));
}
~~~

Mock test xác nhận mapper gọi đúng cột và chuyển đổi đúng theo giả định. Nó không xác nhận driver thật trả kiểu dữ liệu như mong muốn; bổ sung integration test cho query và schema quan trọng.

## 21. Kiểm thử domain mapper

Domain mapper nên được test độc lập với JDBC. Đầu vào là persistence DTO hoặc row object; đầu ra là domain object. Nhờ vậy có thể xác nhận invariant và quy tắc chuyển đổi mà không cần mock ResultSet.

Ví dụ:

~~~java
@Test
void mapsPersistenceRowToOrderDomain() {
    OrderRow row = new OrderRow(
        42L,
        "C-100",
        new BigDecimal("125.50"),
        "READY"
    );

    Order order = new OrderDomainMapper().toDomain(row);

    assertThat(order.id()).isEqualTo(OrderId.of(42L));
    assertThat(order.customerId()).isEqualTo(CustomerId.of("C-100"));
    assertThat(order.total().amount())
        .isEqualByComparingTo("125.50");
    assertThat(order.status()).isEqualTo(OrderStatus.READY);
}
~~~

Các test bổ sung nên xác nhận:

- Currency code không hợp lệ bị từ chối.
- Status code không được hỗ trợ tạo lỗi rõ ràng.
- Giá trị bắt buộc bị null được xử lý theo domain rule.
- Domain factory không cho phép tạo aggregate vi phạm invariant.
- Mapping không thay đổi object persistence đầu vào.

## 22. Integration test reader cùng RowMapper

Unit test RowMapper không xác nhận reader query đúng dữ liệu. Một integration test với database test có thể tạo bảng và dữ liệu fixture, chạy step rồi kiểm tra item được đọc và ghi.

Ví dụ test:

1. Insert hai order hợp lệ và một order có status không được chọn.
2. Cấu hình JdbcPagingItemReader hoặc JdbcCursorItemReader với query.
3. Dùng custom RowMapper.
4. Chạy step với writer test thu thập item hoặc ghi sang bảng đích.
5. Xác nhận đúng hai order được đọc và giá trị được map chính xác.
6. Xác nhận reader đóng resource sau step.

Với JdbcPagingItemReader, nên kiểm tra nhiều hơn một page để xác nhận query provider và sort key. Dùng dữ liệu có ID liên tiếp và cả trường hợp sort key trùng nếu query dùng composite sort.

Với JdbcCursorItemReader, kiểm tra behavior của cursor và transaction configuration theo database/driver đang dùng. Không dựa hoàn toàn vào mock ResultSet để kết luận reader restart được.

## 23. Mapping và hiệu năng trong batch lớn

RowMapper được gọi cho từng hàng, vì vậy chi phí nhỏ trong mapper có thể nhân lên hàng triệu lần. Hãy:

- Tránh reflection hoặc introspection lặp không cần thiết trong custom mapper.
- Tránh query bổ sung trong mapRow.
- Không parse payload lớn nhiều lần nếu có thể chuyển đổi một lần.
- Chỉ select các cột cần dùng.
- Dùng fetch size/page size theo khả năng database và memory.
- Không giữ mọi row object trong collection toàn cục.
- Dùng BigDecimal/Date conversion có chủ đích, tránh format/parse chuỗi không cần thiết.

BeanPropertyRowMapper tiện lợi nhưng có thể có overhead so với custom mapper đơn giản. Đừng tối ưu trước khi đo; với bottleneck thực tế, benchmark query và mapping riêng để xác định chi phí nằm ở database, network, conversion hay processor.

Domain mapper cũng có thể tạo nhiều value object. Điều đó thường đáng giá để giữ invariant và type safety. Nếu mapping trở thành điểm nghẽn, đo allocation và thời gian trước khi giảm abstraction.

## 24. Những lỗi thường gặp khi dùng RowMapper và domain mapper

**Gọi rs.next() trong mapRow:** JdbcTemplate/reader đã điều khiển con trỏ ResultSet. Gọi thêm sẽ bỏ qua hàng hoặc phá luồng đọc.

**Đóng ResultSet/Connection trong mapper:** mapper không sở hữu resource. Việc đóng có thể làm reader không đọc được hàng tiếp theo.

**Dùng rowNum làm business ID:** rowNum chỉ là vị trí trong kết quả hiện tại, không phải định danh ổn định của record.

**Bỏ qua SQL NULL:** getter primitive có thể trả 0/false. Dùng getObject wrapper hoặc wasNull() để phân biệt null.

**Dùng double cho tiền:** có thể mất độ chính xác. Giữ BigDecimal và áp dụng rounding trong domain rule.

**Dùng Enum.valueOf cho mã DB tùy chỉnh:** tên enum có thể khác mã lưu trong database. Dùng hàm chuyển mã rõ ràng.

**Đặt query phụ trong RowMapper:** tạo N+1 query và kéo dài thời gian đọc. Dùng join hoặc batch enrichment riêng.

**Giữ mutable field trong mapper:** nhiều hàng/thread có thể làm dữ liệu lẫn nhau. Dùng mapper stateless và biến local.

**Để domain model phụ thuộc ResultSet:** làm domain layer phụ thuộc JDBC. Dùng row DTO và domain mapper nếu cần tách lớp.

**Map mọi lỗi thành object mặc định:** che giấu dữ liệu lỗi và có thể ghi dữ liệu sai. Phân loại exception theo record validation hay lỗi schema/code.

**Dùng RowMapper để gom nhiều hàng thành aggregate:** RowMapper chỉ ánh xạ một hàng. Dùng ResultSetExtractor hoặc reader có ranh giới aggregate rõ.

**Cho rằng mapper xử lý checkpoint:** RowMapper không lưu reader state. Reader và ExecutionContext chịu trách nhiệm restart.

## 25. Quy trình thiết kế mapping cho production batch

Trước tiên, xác định item mà batch cần xử lý là một database row, một read DTO hay một domain aggregate. Thiết kế SELECT với alias rõ ràng và chỉ lấy các cột cần thiết. Viết custom RowMapper khi cần kiểm soát null, kiểu dữ liệu, enum hoặc mapping join; dùng BeanPropertyRowMapper cho model đơn giản có naming convention phù hợp.

Tiếp theo, quyết định có cần domain mapper hay không. Nếu batch chỉ chuyển dữ liệu đơn giản, RowMapper có thể tạo domain object trực tiếp. Nếu persistence shape khác domain model hoặc domain có invariant/value object, tạo DTO trung gian rồi dùng domain mapper. Giữ RowMapper stateless, không query phụ và không thực hiện side effect.

Cuối cùng, kiểm thử riêng hai lớp mapping và kiểm thử integration reader với database/driver thực tế. Bao phủ SQL NULL, kiểu ngày giờ, decimal, enum, alias, join, paging và restart. Đo hiệu năng trên dữ liệu đại diện trước khi tối ưu mapper.

RowMapper chuyển một hàng JDBC thành object; domain mapper chuyển object dữ liệu thành khái niệm nghiệp vụ. Trong Spring Batch, hai bước này giúp reader tập trung vào việc lấy dữ liệu, processor tập trung vào xử lý nghiệp vụ và writer tập trung vào đầu ra. Khi ranh giới rõ ràng, mapping dễ kiểm thử, query dễ thay đổi và batch job ít bị phụ thuộc vào chi tiết schema database.
