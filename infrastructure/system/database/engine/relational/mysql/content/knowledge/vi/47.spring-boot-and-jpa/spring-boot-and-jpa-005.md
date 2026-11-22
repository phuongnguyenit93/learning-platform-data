# JdbcTemplate, named parameter và ánh xạ kết quả

Spring Boot cung cấp `JdbcTemplate` để thực thi SQL trực tiếp trên MySQL mà không phải tự quản lý `Connection`, `PreparedStatement` và `ResultSet`. Khi câu SQL có nhiều tham số, `NamedParameterJdbcTemplate` cho phép đặt tên tham số như `:customerId` hoặc `:status`, giúp câu lệnh dễ đọc và tránh ghép dữ liệu đầu vào vào chuỗi SQL. Kết quả truy vấn được chuyển thành object Java bằng `RowMapper`, `ResultSetExtractor` hoặc các callback phù hợp.

Những công cụ này đặc biệt hữu ích khi cần kiểm soát SQL, dùng tính năng riêng của MySQL, tối ưu truy vấn hoặc đọc dữ liệu tổng hợp. Chúng vẫn dùng JDBC và transaction manager của Spring, vì vậy cần hiểu cách bind giá trị, xử lý `NULL`, ánh xạ kiểu số/ngày giờ và quản lý connection đúng cách.

## 1. Cấu hình JdbcTemplate trong Spring Boot

Nếu ứng dụng dùng `spring-boot-starter-jdbc` hoặc `spring-boot-starter-data-jpa`, Spring Boot thường tự cấu hình `DataSource`, `JdbcTemplate` và `NamedParameterJdbcTemplate` khi có driver JDBC trên classpath.

Ví dụ dependency Maven cho ứng dụng Spring Boot dùng JDBC trực tiếp:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jdbc</artifactId>
</dependency>

<dependency>
    <groupId>com.mysql</groupId>
    <artifactId>mysql-connector-j</artifactId>
    <scope>runtime</scope>
</dependency>
```

Khai báo kết nối trong `application.yml`:

```yaml
spring:
  datasource:
    url: jdbc:mysql://localhost:3306/appdb
    username: app_runtime
    password: ${DB_PASSWORD}
    driver-class-name: com.mysql.cj.jdbc.Driver
    hikari:
      maximum-pool-size: 15
      minimum-idle: 3
      connection-timeout: 30000
```

Các giá trị pool chỉ là ví dụ; cần điều chỉnh theo số instance ứng dụng, giới hạn connection của MySQL và tải thực tế. Không commit password vào repository. Trong ứng dụng mới, hãy kiểm tra thuộc tính charset/timezone của Connector/J theo chuẩn dữ liệu của hệ thống và dùng TLS khi kết nối qua mạng không tin cậy.

Inject template qua constructor:

```java
@Repository
public class CustomerJdbcRepository {
    private final JdbcTemplate jdbcTemplate;
    private final NamedParameterJdbcTemplate namedJdbc;

    public CustomerJdbcRepository(
            JdbcTemplate jdbcTemplate,
            NamedParameterJdbcTemplate namedJdbc) {
        this.jdbcTemplate = jdbcTemplate;
        this.namedJdbc = namedJdbc;
    }
}
```

`JdbcTemplate` và `NamedParameterJdbcTemplate` an toàn khi dùng đồng thời sau khi cấu hình xong. Không tạo một template mới cho từng request; hãy dùng bean được Spring quản lý để chia sẻ `DataSource` và connection pool.

## 2. JdbcTemplate xử lý JDBC boilerplate

Khi dùng JDBC thuần, ứng dụng phải lấy connection, tạo statement, bind tham số, đọc result set và đóng tài nguyên trong mọi nhánh. `JdbcTemplate` thực hiện phần quản lý vòng đời đó, đồng thời chuyển `SQLException` thành hệ thống exception không checked của Spring (`DataAccessException`).

Ví dụ truy vấn đơn giản:

```java
String sql = "SELECT COUNT(*) FROM customers WHERE status = ?";

Long count = jdbcTemplate.queryForObject(
        sql,
        Long.class,
        "ACTIVE"
);
```

Các phương thức thường dùng:

| Phương thức | Mục đích | Kết quả |
|---|---|---|
| `query(...)` | Truy vấn nhiều hàng | `List<T>` hoặc callback xử lý từng hàng. |
| `queryForObject(...)` | Truy vấn một giá trị hoặc một hàng | Một object; lỗi nếu số hàng không đúng một theo overload được dùng. |
| `queryForList(...)` | Truy vấn nhiều hàng dạng map | `List<Map<String, Object>>`. |
| `queryForMap(...)` | Một hàng dạng map | `Map<String, Object>`. |
| `update(...)` | `INSERT`, `UPDATE`, `DELETE` | Số hàng bị ảnh hưởng. |
| `batchUpdate(...)` | Thực hiện nhiều lần DML theo batch | Mảng số hàng hoặc kết quả batch. |
| `execute(...)` | Thực thi SQL/callback mức thấp | Tùy overload. |

`queryForObject()` phù hợp với truy vấn có đúng một kết quả, chẳng hạn count hoặc tìm theo khóa duy nhất. Nếu không có hàng, Spring thường ném `EmptyResultDataAccessException`; nếu có nhiều hơn một hàng trong overload yêu cầu một hàng, sẽ có `IncorrectResultSizeDataAccessException`. Với kết quả có thể không tồn tại, dùng `query()` trả list rồi chuyển thành `Optional` theo quy tắc của repository.

Ví dụ:

```java
public Optional<CustomerSummary> findById(long customerId) {
    String sql = """
        SELECT customer_id, email, status, credit_limit
        FROM customers
        WHERE customer_id = ?
        """;

    List<CustomerSummary> rows = jdbcTemplate.query(
            sql,
            CUSTOMER_ROW_MAPPER,
            customerId
    );

    return rows.stream().findFirst();
}
```

Nếu `customer_id` là primary key, truy vấn trả tối đa một hàng. Với truy vấn không có tính duy nhất, `findFirst()` chỉ lấy phần tử đầu theo thứ tự mà SQL trả về; hãy thêm `ORDER BY` nếu thứ tự có ý nghĩa.

## 3. NamedParameterJdbcTemplate và tham số có tên

Trong `JdbcTemplate`, tham số positional dùng dấu `?`; thứ tự `setXxx()` phải khớp vị trí trong SQL. Khi câu lệnh có nhiều điều kiện, named parameter làm rõ giá trị nào được bind vào điều kiện nào:

```java
String sql = """
    SELECT customer_id, email, status
    FROM customers
    WHERE status = :status
      AND created_at >= :fromTime
      AND created_at < :toTime
    ORDER BY created_at DESC
    """;

MapSqlParameterSource params = new MapSqlParameterSource()
        .addValue("status", "ACTIVE", Types.VARCHAR)
        .addValue("fromTime", fromTime, Types.TIMESTAMP)
        .addValue("toTime", toTime, Types.TIMESTAMP);

List<CustomerRow> customers = namedJdbc.query(
        sql,
        params,
        CUSTOMER_ROW_MAPPER
);
```

Named parameter được Spring chuyển thành JDBC placeholder `?` trước khi gửi đến driver. Giá trị vẫn được bind bằng prepared statement; nó không phải phép thay chuỗi trực tiếp.

Có thể dùng `Map` khi tham số đơn giản:

```java
Map<String, Object> params = Map.of(
        "status", "ACTIVE",
        "minTotal", new BigDecimal("100.00")
);

List<CustomerRow> rows = namedJdbc.query(
        "SELECT customer_id, email, status, credit_limit " +
        "FROM customers " +
        "WHERE status = :status AND credit_limit >= :minTotal",
        params,
        CUSTOMER_ROW_MAPPER
);
```

`Map.of()` không chấp nhận key hoặc value `null`. Khi tham số có thể null hoặc cần khai báo JDBC type rõ ràng, dùng `MapSqlParameterSource`:

```java
MapSqlParameterSource params = new MapSqlParameterSource()
        .addValue("email", nullableEmail, Types.VARCHAR)
        .addValue("status", status, Types.VARCHAR);
```

Khi bind `null`, khai báo SQL type giúp driver xử lý nhất quán, đặc biệt với kiểu `DECIMAL`, ngày giờ, binary và kiểu đặc thù.

### Named parameter với IN clause

`NamedParameterJdbcTemplate` có thể mở rộng collection thành nhiều placeholder:

```java
String sql = """
    SELECT customer_id, email, status
    FROM customers
    WHERE customer_id IN (:ids)
    """;

MapSqlParameterSource params = new MapSqlParameterSource()
        .addValue("ids", List.of(10L, 20L, 30L));

List<CustomerRow> rows = namedJdbc.query(sql, params, CUSTOMER_ROW_MAPPER);
```

Khi collection rỗng, không gửi nguyên `IN (:ids)` với danh sách rỗng vì SQL sinh ra có thể không hợp lệ hoặc khác nhau giữa driver/database. Hãy xử lý rõ ở tầng ứng dụng: trả danh sách rỗng ngay nếu nghiệp vụ yêu cầu không khớp hàng nào, hoặc bỏ điều kiện nếu ý nghĩa nghiệp vụ là không lọc theo danh sách.

### Giá trị có thể bind, identifier thì không

Prepared statement chỉ bind được giá trị. Không thể dùng `:columnName`, `:tableName` hoặc `:sortDirection` để bind tên cột, tên bảng hay từ khóa SQL. Nếu cần sắp xếp động, ánh xạ input qua allowlist:

```java
String orderColumn = switch (sortBy) {
    case "email" -> "email";
    case "createdAt" -> "created_at";
    case "status" -> "status";
    default -> throw new IllegalArgumentException("Unsupported sort field");
};

String direction = descending ? "DESC" : "ASC";
String sql = "SELECT customer_id, email, status FROM customers "
        + "ORDER BY " + orderColumn + " " + direction;
```

`orderColumn` và `direction` ở đây chỉ được chọn từ các giá trị cố định do server kiểm soát. Không nối trực tiếp chuỗi sort/table/column do client gửi lên. Mọi giá trị dữ liệu như email, status, thời gian và ID vẫn phải dùng bind parameter.

## 4. Ánh xạ hàng bằng RowMapper

`RowMapper<T>` chuyển một hàng hiện tại của `ResultSet` thành một object Java. Spring gọi `mapRow()` cho từng hàng; implementation không tự gọi `rs.next()` và không đóng `ResultSet`.

Định nghĩa DTO/record:

```java
public record CustomerRow(
        long customerId,
        String email,
        String status,
        BigDecimal creditLimit,
        LocalDateTime createdAt) {
}
```

Tạo mapper tường minh:

```java
private static final RowMapper<CustomerRow> CUSTOMER_ROW_MAPPER =
        (rs, rowNum) -> new CustomerRow(
                rs.getLong("customer_id"),
                rs.getString("email"),
                rs.getString("status"),
                rs.getBigDecimal("credit_limit"),
                rs.getObject("created_at", LocalDateTime.class)
        );
```

SQL nên chọn cột rõ ràng và dùng alias ổn định. Mapper dựa vào label (`customer_id`) thay vì phụ thuộc thứ tự cột, vì vậy có thể đổi thứ tự projection mà không làm sai mapping.

Nếu cột `created_at` là MySQL `DATETIME`, `LocalDateTime` phù hợp vì `DATETIME` không chứa timezone. Nếu cột là `TIMESTAMP`, hãy thống nhất timezone session và quy tắc chuyển đổi; có thể đọc bằng `Timestamp` rồi chuyển `toInstant()` nếu domain cần một instant tuyệt đối. Đừng tự gắn timezone vào `DATETIME` nếu dữ liệu chỉ là local date-time.

### BeanPropertyRowMapper

Spring có `BeanPropertyRowMapper` để map tên cột sang JavaBean property, thường hỗ trợ chuyển `customer_id` thành `customerId`:

```java
RowMapper<CustomerBean> mapper =
        new BeanPropertyRowMapper<>(CustomerBean.class);
```

Mapper này tiện cho DTO có constructor không tham số và setter, nhưng dựa vào reflection và quy tắc khớp tên. Nó có thể che khuất sai lệch kiểu hoặc nullability nếu dùng với domain object phức tạp. Với truy vấn quan trọng, kiểu unsigned, bitmask hoặc phép chuyển đổi tùy chỉnh, mapper tường minh thường dễ review và kiểm thử hơn.

## 5. Ánh xạ kiểu MySQL cần chú ý

Một số kiểu MySQL không nên đọc bằng primitive Java một cách tùy tiện:

| Kiểu MySQL | Java nên dùng | Gợi ý trong RowMapper |
|---|---|---|
| `DECIMAL(p,s)` | `BigDecimal` | `rs.getBigDecimal("amount")` |
| `BIGINT` signed | `long`/`Long` | `rs.getLong(...)`; dùng `wasNull()` nếu nullable hoặc `getObject(..., Long.class)`. |
| `BIGINT UNSIGNED` | `BigInteger` khi cần toàn miền | `rs.getBigDecimal(...).toBigIntegerExact()` hoặc `getObject()` rồi kiểm tra class. |
| `BIT(1)` / boolean | `Boolean` | `getBoolean()` rồi `wasNull()` nếu nullable. |
| `BIT(M)` với M lớn hơn 1 | `byte[]` | `rs.getBytes(...)`, giải mã bit theo quy ước ứng dụng. |
| `DATE` | `LocalDate` | `rs.getObject("birth_date", LocalDate.class)`. |
| `DATETIME` | `LocalDateTime` | `rs.getObject("created_at", LocalDateTime.class)`. |
| `TIMESTAMP` | `Instant` hoặc `Timestamp` theo domain | Thống nhất timezone session; đọc `Timestamp` rồi chuyển `toInstant()` khi cần instant. |

Ví dụ mapper xử lý unsigned, decimal, nullable boolean:

```java
public record PaymentRow(
        BigInteger paymentId,
        BigDecimal amount,
        Boolean confirmed) {
}

private static final RowMapper<PaymentRow> PAYMENT_ROW_MAPPER = (rs, rowNum) -> {
    BigDecimal rawId = rs.getBigDecimal("payment_id");
    BigInteger paymentId = rawId == null ? null : rawId.toBigIntegerExact();

    boolean confirmedValue = rs.getBoolean("confirmed");
    Boolean confirmed = rs.wasNull() ? null : confirmedValue;

    return new PaymentRow(
            paymentId,
            rs.getBigDecimal("amount"),
            confirmed
    );
};
```

`getLong()`, `getInt()` và `getBoolean()` trả giá trị primitive mặc định khi SQL value là `NULL`. Gọi `rs.wasNull()` ngay sau getter primitive cần kiểm tra; bất kỳ getter nào khác ở giữa đều làm thay đổi kết quả kiểm tra. Với cột nullable, có thể dùng `getObject(column, Long.class)` hoặc wrapper tương ứng nếu driver hỗ trợ đúng kiểu.

Với `BIGINT UNSIGNED`, không gọi `getLong()` cho toàn bộ miền vì giá trị vượt `Long.MAX_VALUE` có thể không biểu diễn được. Nếu ứng dụng chủ động giới hạn ID dưới `Long.MAX_VALUE`, hãy bảo đảm giới hạn đó bằng constraint/quy tắc dữ liệu và kiểm tra khi ghi.

## 6. Ánh xạ truy vấn JOIN một-nhiều

Một truy vấn join giữa parent và child trả nhiều hàng cho cùng một parent. Nếu dùng `RowMapper<OrderRow>`, mỗi hàng sẽ thành một object order lặp lại. Khi cần gom nhiều child vào một parent, dùng `ResultSetExtractor` để đọc toàn bộ kết quả và nhóm theo khóa.

Ví dụ DTO:

```java
public record OrderLine(long lineId, String productCode, int quantity) {}

public record OrderWithLines(long orderId, String orderNumber, List<OrderLine> lines) {}
```

SQL nên dùng `LEFT JOIN` nếu vẫn cần trả về order chưa có line:

```sql
SELECT
    o.order_id,
    o.order_number,
    l.line_id,
    l.product_code,
    l.quantity
FROM orders AS o
LEFT JOIN order_lines AS l ON l.order_id = o.order_id
WHERE o.order_id IN (:orderIds)
ORDER BY o.order_id, l.line_id;
```

Extractor:

```java
private static final ResultSetExtractor<List<OrderWithLines>> ORDER_EXTRACTOR = rs -> {
    Map<Long, OrderAccumulator> orders = new LinkedHashMap<>();

    while (rs.next()) {
        long orderId = rs.getLong("order_id");

        OrderAccumulator order = orders.computeIfAbsent(
                orderId,
                id -> new OrderAccumulator(
                        id,
                        getString(rs, "order_number"))
        );

        long lineId = rs.getLong("line_id");
        if (!rs.wasNull()) {
            order.lines.add(new OrderLine(
                    lineId,
                    rs.getString("product_code"),
                    rs.getInt("quantity")
            ));
        }
    }

    return orders.values().stream()
            .map(OrderAccumulator::toResult)
            .toList();
};
```

Trong ví dụ trên, `getString(rs, "order_number")` là helper đọc cột và được định nghĩa như sau:

```java
private static String getString(ResultSet rs, String column) {
    try {
        return rs.getString(column);
    } catch (SQLException ex) {
        throw new DataRetrievalFailureException("Cannot read " + column, ex);
    }
}

private static final class OrderAccumulator {
    final long orderId;
    final String orderNumber;
    final List<OrderLine> lines = new ArrayList<>();

    OrderAccumulator(long orderId, String orderNumber) {
        this.orderId = orderId;
        this.orderNumber = orderNumber;
    }

    OrderWithLines toResult() {
        return new OrderWithLines(orderId, orderNumber, List.copyOf(lines));
    }
}
```

Trong một implementation thực tế, có thể viết mapper helper để tránh bắt `SQLException` trong lambda `computeIfAbsent`, hoặc dùng vòng lặp `get`/`put` tường minh. Ý quan trọng là `ResultSetExtractor` sở hữu vòng lặp `rs.next()` và gom các hàng theo khóa parent. Dùng `LinkedHashMap` nếu muốn giữ thứ tự parent theo thứ tự truy vấn; SQL vẫn cần `ORDER BY` để bảo đảm thứ tự xác định.

## 7. Chọn đúng callback: RowMapper, ResultSetExtractor hay RowCallbackHandler

| Callback | Khi dùng | Đặc điểm |
|---|---|---|
| `RowMapper<T>` | Mỗi hàng độc lập trở thành một object. | Spring quản lý vòng lặp; mapper chỉ đọc hàng hiện tại. |
| `ResultSetExtractor<T>` | Cần nhìn toàn bộ kết quả để gom nhóm, tạo cấu trúc lồng nhau hoặc tính toán. | Ứng dụng tự duyệt `ResultSet`. |
| `RowCallbackHandler` | Xử lý từng hàng mà không cần giữ toàn bộ kết quả trong list. | Phù hợp tác vụ duyệt/ghi ra sink theo hàng. |

Ví dụ `RowCallbackHandler`:

```java
jdbcTemplate.query(
        "SELECT customer_id, email FROM customers ORDER BY customer_id",
        (RowCallbackHandler) rs -> {
            long id = rs.getLong("customer_id");
            String email = rs.getString("email");
            exportCustomer(id, email);
        }
);
```

Callback không làm cho truy vấn tự động streaming ở mọi driver. Với tập dữ liệu lớn, cần xem fetch size, cursor fetching, transaction và khả năng của Connector/J; nếu không, driver có thể buffer nhiều hàng trong bộ nhớ.

## 8. Pagination, lọc và sort an toàn

Với danh sách có thể lớn, phân trang ở SQL thay vì lấy toàn bộ rồi cắt trong Java:

```java
String sql = """
    SELECT customer_id, email, status, created_at
    FROM customers
    WHERE status = :status
    ORDER BY created_at DESC, customer_id DESC
    LIMIT :limit OFFSET :offset
    """;

MapSqlParameterSource params = new MapSqlParameterSource()
        .addValue("status", status, Types.VARCHAR)
        .addValue("limit", pageSize, Types.INTEGER)
        .addValue("offset", offset, Types.INTEGER);

List<CustomerRow> page = namedJdbc.query(sql, params, CUSTOMER_ROW_MAPPER);
```

`ORDER BY` cần có cột phân xử ổn định, chẳng hạn primary key, để các hàng có cùng `created_at` không đổi thứ tự tùy ý giữa các trang. Kiểm tra `pageSize` và `offset` ở tầng ứng dụng; không để client yêu cầu kích thước trang không giới hạn.

Với bảng lớn, `OFFSET` cao có thể khiến MySQL phải đọc và bỏ qua nhiều hàng. Keyset pagination thường hiệu quả hơn:

```sql
SELECT customer_id, email, created_at
FROM customers
WHERE status = :status
  AND (created_at, customer_id) < (:lastCreatedAt, :lastCustomerId)
ORDER BY created_at DESC, customer_id DESC
LIMIT :limit;
```

Điều kiện tuple ở trên minh họa cho thứ tự giảm dần; cần bảo đảm index phù hợp, ví dụ `(status, created_at, customer_id)`, và token trang cuối được lấy từ hàng cuối của trang trước. Nếu sort direction hoặc cột lọc thay đổi, phải thiết kế điều kiện keyset và index tương ứng.

## 9. Batch update và generated keys

Khi cần ghi nhiều hàng, `batchUpdate()` giảm số lần round-trip so với gọi `update()` trong vòng lặp:

```java
String sql = """
    UPDATE inventory
    SET reserved_quantity = reserved_quantity + :quantity
    WHERE product_id = :productId
    """;

SqlParameterSource[] batch = reservations.stream()
        .map(item -> new MapSqlParameterSource()
                .addValue("quantity", item.quantity(), Types.INTEGER)
                .addValue("productId", item.productId(), Types.BIGINT))
        .toArray(SqlParameterSource[]::new);

int[] results = namedJdbc.batchUpdate(sql, batch);
```

Chọn batch size theo tải và giới hạn packet/driver. Nếu batch phải nguyên tử, chạy trong transaction và xác định cách xử lý khi một phần batch lỗi. Không giả định mọi JDBC driver trả số hàng chính xác cho từng lệnh; JDBC có thể dùng `SUCCESS_NO_INFO` hoặc `EXECUTE_FAILED` trong kết quả batch.

Để lấy khóa tự tăng:

```java
String sql = "INSERT INTO customers (email, status) VALUES (?, ?)";
KeyHolder keyHolder = new GeneratedKeyHolder();

jdbcTemplate.update(connection -> {
    PreparedStatement ps = connection.prepareStatement(
            sql,
            Statement.RETURN_GENERATED_KEYS
    );
    ps.setString(1, email);
    ps.setString(2, "ACTIVE");
    return ps;
}, keyHolder);

Number generatedId = keyHolder.getKey();
if (generatedId == null) {
    throw new DataRetrievalFailureException("MySQL did not return a generated key");
}
long customerId = generatedId.longValue();
```

Đối với khóa unsigned có thể vượt `Long.MAX_VALUE`, không ép `Number` về `long`; hãy chọn kiểu khóa domain phù hợp và kiểm thử khả năng driver trả key. Trong phần lớn ứng dụng, ID tự tăng signed `BIGINT` được giữ trong miền `long` để tương thích Java.

## 10. Transaction với JdbcTemplate

Trong Spring Boot, `@Transactional` có thể quản lý transaction cho các lời gọi `JdbcTemplate` nếu template dùng cùng `DataSource` với transaction manager:

```java
@Service
public class TransferService {
    private final JdbcTemplate jdbc;

    public TransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void transfer(long fromAccount, long toAccount, BigDecimal amount) {
        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("Transfer amount must be positive");
        }

        int debited = jdbc.update("""
            UPDATE accounts
            SET balance = balance - ?
            WHERE account_id = ? AND balance >= ?
            """, amount, fromAccount, amount);

        if (debited != 1) {
            throw new IllegalStateException("Insufficient balance or account missing");
        }

        int credited = jdbc.update("""
            UPDATE accounts
            SET balance = balance + ?
            WHERE account_id = ?
            """, amount, toAccount);

        if (credited != 1) {
            throw new IllegalStateException("Destination account missing");
        }
    }
}
```

Nếu một bước ném runtime exception, Spring rollback transaction theo mặc định. Checked exception không tự động rollback theo mặc định; dùng `@Transactional(rollbackFor = ...)` nếu nghiệp vụ yêu cầu. Cả hai câu update phải chạy trên cùng transaction-bound connection. `JdbcTemplate` sử dụng cơ chế quản lý connection của Spring nên tự tham gia transaction hiện hành khi cấu hình đúng.

Không tự gọi `dataSource.getConnection()` rồi đóng connection trong một phương thức đã dùng `@Transactional` nếu không biết cách lấy connection gắn với transaction. Dùng `JdbcTemplate` hoặc `DataSourceUtils` để bảo đảm cùng connection được sử dụng.

### Kết hợp JdbcTemplate và JPA

Một ứng dụng có thể dùng JPA cho CRUD entity và `JdbcTemplate` cho truy vấn đặc thù. Hai công nghệ chỉ tham gia cùng transaction khi được cấu hình dùng cùng `DataSource` và transaction manager tương thích, thường là `JpaTransactionManager` được cấu hình cho persistence unit đó.

Nếu JPA đã thay đổi entity nhưng chưa flush, truy vấn `JdbcTemplate` có thể chưa nhìn thấy thay đổi vì SQL chưa được gửi đến database. Gọi `entityManager.flush()` khi cần đọc kết quả đã được JPA thay đổi trong cùng transaction. Ngược lại, nếu `JdbcTemplate` cập nhật trực tiếp hàng đang được quản lý bởi persistence context, entity đã nạp trong `EntityManager` có thể bị stale; cân nhắc `refresh()` hoặc `clear()` phù hợp. Tránh hai tầng cùng ghi một dữ liệu mà không xác định rõ nguồn quản lý trạng thái.

## 11. Đọc tập dữ liệu lớn và quản lý bộ nhớ

`query()` trả về `List<T>`, nên toàn bộ object kết quả được giữ trong bộ nhớ. Với báo cáo lớn hoặc export, cân nhắc `RowCallbackHandler`, phân trang theo keyset hoặc `queryForStream()`.

Ví dụ `queryForStream()`:

```java
try (Stream<CustomerRow> stream = jdbcTemplate.queryForStream(
        "SELECT customer_id, email, status, credit_limit FROM customers",
        CUSTOMER_ROW_MAPPER)) {
    stream.forEach(this::writeToExport);
}
```

Phải đóng stream bằng try-with-resources vì stream giữ tài nguyên JDBC cho đến khi đóng. Không trả stream ra ngoài tầng repository rồi để caller sử dụng tùy ý sau khi transaction/connection đã đóng.

Với MySQL Connector/J, cursor-based fetching cần cấu hình phù hợp, thường gồm `useCursorFetch=true` và fetch size dương trên statement. Chỉ gọi `setFetchSize()` không bảo đảm mọi driver sẽ stream dữ liệu theo cursor. Kiểm thử với đúng Connector/J version, transaction mode và cấu hình pool; theo dõi memory, thời gian giữ connection và tác động đến server.

Không giữ một connection trong thời gian dài nếu tác vụ export có thể chạy nhiều phút mà pool nhỏ. Chia batch, ghi ra sink theo từng phần và bảo đảm có giới hạn thời gian/khả năng hủy tác vụ.

## 12. Xử lý lỗi và logging

`JdbcTemplate` chuyển `SQLException` thành các subclass của `DataAccessException`, ví dụ `DuplicateKeyException`, `DataIntegrityViolationException`, `CannotAcquireLockException`, `PessimisticLockingFailureException` hoặc `DataAccessResourceFailureException`. Tên exception cụ thể phụ thuộc SQLState/vendor code và translator được cấu hình. Bắt exception theo ngữ nghĩa nghiệp vụ khi có thể, không bắt mọi `Exception` rồi bỏ qua.

Ví dụ xử lý unique conflict:

```java
try {
    jdbcTemplate.update(
            "INSERT INTO customers (email, status) VALUES (?, ?)",
            email,
            "ACTIVE"
    );
} catch (DuplicateKeyException ex) {
    throw new CustomerAlreadyExistsException(email, ex);
}
```

Không ghi password, token, thông tin cá nhân hoặc toàn bộ dữ liệu nhạy cảm của tham số vào log. Với lỗi SQL, lưu query identifier, tên repository method, SQLState/vendor code và correlation ID; chỉ log giá trị đã được làm sạch khi thật sự cần.

Đối với deadlock hoặc lock timeout, chỉ retry transaction nếu thao tác có thể chạy lại an toàn và retry toàn bộ transaction theo một ranh giới nhất quán. Không retry riêng một câu lệnh ở giữa transaction sau khi MySQL đã rollback transaction do deadlock.

## 13. Kiểm thử repository dùng MySQL

Spring Boot có `@JdbcTest` để tạo slice test cho JDBC components, cấu hình `JdbcTemplate` và transaction test. Nếu test dùng H2, một số cú pháp, collation, kiểu unsigned, `BIT(M)`, JSON, SQL mode hoặc hành vi locking của MySQL sẽ khác. Với repository phụ thuộc tính năng MySQL, nên chạy integration test trên MySQL thật bằng Testcontainers hoặc một database test riêng.

Các trường hợp cần kiểm thử:

- Truy vấn có kết quả, không có kết quả và nhiều kết quả ngoài mong đợi.
- Named parameter nullable, collection rỗng và `IN` với danh sách lớn.
- `DECIMAL` có scale, `BIGINT UNSIGNED` ở biên, `BIT(M)` và boolean nullable.
- JOIN một-nhiều không tạo parent trùng hoặc làm mất child.
- Batch có một hàng vi phạm constraint.
- Transaction rollback khi câu lệnh thứ hai thất bại.
- Pagination ổn định khi nhiều hàng có cùng timestamp.
- SQL động chỉ nhận identifier từ allowlist.

Kiểm thử mapper bằng `ResultSet` mock có thể xác nhận logic nhỏ, nhưng không thay thế integration test vì kiểu Java và metadata phụ thuộc Connector/J.

## 14. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `queryForObject()` ném lỗi khi không có hàng | API được gọi với kỳ vọng đúng một kết quả | Dùng `query()` và trả `Optional`, hoặc xử lý `EmptyResultDataAccessException`. |
| Kết quả JOIN có parent lặp lại | Mỗi hàng JOIN được map thành một parent object | Dùng `ResultSetExtractor` gom theo khóa hoặc trả DTO phẳng có chủ đích. |
| Cột nullable thành `0`/`false` | Getter primitive không phân biệt SQL `NULL` | Dùng wrapper hoặc gọi `wasNull()` ngay sau getter. |
| SQL injection trong ORDER BY | Ghép input người dùng vào identifier/direction | Dùng allowlist cho identifier; bind mọi giá trị dữ liệu. |
| `IN` clause lỗi với danh sách rỗng | Named parameter collection mở rộng thành không có placeholder | Xử lý collection rỗng trước khi chạy SQL. |
| Đọc `BIGINT UNSIGNED` bị tràn | Dùng `getLong()` cho toàn miền unsigned | Dùng `BigInteger`/`BigDecimal` và kiểm tra biên. |
| Export làm đầy heap | `query()` giữ toàn bộ kết quả thành list hoặc driver buffer hết dữ liệu | Dùng phân trang/callback/cursor fetching đã kiểm chứng. |
| Update JPA rồi query JDBC không thấy dữ liệu | EntityManager chưa flush | Gọi `flush()` khi cần SQL JPA được gửi trước truy vấn JDBC. |
| JDBC update nhưng entity JPA vẫn giá trị cũ | Persistence context đang giữ entity stale | Refresh/clear phù hợp hoặc tránh trộn hai cách ghi trên cùng entity. |
| Transaction không rollback như kỳ vọng | Khác DataSource/transaction manager hoặc checked exception không thuộc rollback rule | Dùng cùng transaction manager và cấu hình `rollbackFor` khi cần. |
| Retry tạo dữ liệu trùng | Thao tác không idempotent hoặc retry giữa transaction | Dùng idempotency key và retry toàn transaction theo chính sách rõ. |

## 15. Checklist thiết kế repository

- [ ] Dùng `JdbcTemplate`/`NamedParameterJdbcTemplate` được Spring Boot quản lý qua constructor injection.
- [ ] SQL dùng bind parameter cho mọi giá trị dữ liệu.
- [ ] Identifier động chỉ được chọn từ allowlist server-side.
- [ ] `MapSqlParameterSource` khai báo SQL type khi cần bind null hoặc kiểu đặc thù.
- [ ] `RowMapper` chỉ map hàng hiện tại; dùng `ResultSetExtractor` khi cần gom nhóm.
- [ ] Mapping `DECIMAL`, unsigned integer, BIT, boolean và date/time giữ đúng miền dữ liệu.
- [ ] SQL `NULL` không bị nhầm với giá trị mặc định của primitive.
- [ ] Pagination có thứ tự ổn định và giới hạn kích thước trang.
- [ ] Batch có giới hạn và chính sách transaction/error rõ ràng.
- [ ] `@Transactional` dùng đúng `DataSource`/transaction manager; kiểm tra tương tác với JPA.
- [ ] Tập kết quả lớn không bị nạp toàn bộ vào heap ngoài ý muốn.
- [ ] Exception được chuyển thành lỗi nghiệp vụ phù hợp; log không chứa secret/dữ liệu nhạy cảm.
- [ ] Repository được kiểm thử trên MySQL và đúng phiên bản Connector/J khi phụ thuộc hành vi riêng của MySQL.

`JdbcTemplate` giúp kiểm soát SQL mà vẫn giữ vòng đời JDBC và exception handling nhất quán với Spring. `NamedParameterJdbcTemplate` làm câu truy vấn nhiều điều kiện dễ đọc hơn, còn `RowMapper` và `ResultSetExtractor` chuyển kết quả thành cấu trúc Java theo đúng hình dạng dữ liệu. Khi kết hợp bind parameter, mapping kiểu chính xác, transaction cùng DataSource và kiểm thử trên MySQL thật, repository JDBC có thể hoạt động rõ ràng và tin cậy bên cạnh Spring Data JPA.
