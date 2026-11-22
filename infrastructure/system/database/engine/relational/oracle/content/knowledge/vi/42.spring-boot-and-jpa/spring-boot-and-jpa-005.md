# JdbcTemplate, named parameter và xử lý kiểu dữ liệu Oracle

Spring JDBC cung cấp một lớp truy cập database gọn hơn JDBC thuần nhưng vẫn giữ quyền kiểm soát SQL trong tay ứng dụng. Với Oracle Database, hai thành phần được dùng thường xuyên là `JdbcTemplate` và `NamedParameterJdbcTemplate`. `JdbcTemplate` giúp quản lý vòng đời JDBC resource, bind tham số, lặp qua kết quả và chuyển lỗi JDBC sang hệ thống exception của Spring. `NamedParameterJdbcTemplate` bổ sung khả năng dùng tên tham số như `:customerId` thay cho dấu `?`, giúp câu SQL dễ đọc và ít nhầm thứ tự tham số hơn.

Khi làm việc với Oracle, chất lượng lớp JDBC phụ thuộc nhiều vào cách ánh xạ kiểu dữ liệu. Oracle có các kiểu như `NUMBER`, `DATE`, `TIMESTAMP`, `TIMESTAMP WITH TIME ZONE`, `VARCHAR2`, `CHAR`, `CLOB`, `BLOB`, `RAW` và các kiểu đặc thù khác. Nếu bind hoặc đọc dữ liệu không đúng kiểu, ứng dụng có thể gặp lỗi chuyển đổi, mất phần thời gian, sai precision, lỗi NULL hoặc hiệu năng kém.

Tài liệu này trình bày cách cấu hình Spring JDBC trong Spring Boot, viết truy vấn với `JdbcTemplate` và named parameter, ánh xạ kết quả, xử lý transaction và batch, cùng các lưu ý thực tế khi làm việc với kiểu dữ liệu Oracle.

## 1. Vai trò của Spring JDBC

JDBC là API chuẩn của Java để kết nối và làm việc với database. Ở mức thấp, một thao tác truy vấn thường phải thực hiện các bước:

1. Lấy `Connection` từ `DataSource`.
2. Tạo `PreparedStatement` hoặc `CallableStatement`.
3. Bind các tham số.
4. Thực thi SQL.
5. Đọc `ResultSet`.
6. Đóng `ResultSet`, statement và connection trong mọi nhánh thành công/lỗi.
7. Chuyển đổi `SQLException` và xử lý transaction.

Nếu viết lặp lại các bước này ở mọi repository, code sẽ dài và dễ quên đóng resource. Spring JDBC đóng gói phần lặp lại đó trong template classes, còn ứng dụng cung cấp SQL, tham số và logic ánh xạ dữ liệu.

### 1.1. JdbcTemplate làm gì?

`JdbcTemplate` là lớp trung tâm của Spring JDBC. Nó cung cấp các thao tác phổ biến:

- `query(...)`: chạy SELECT và ánh xạ từng dòng.
- `queryForObject(...)`: truy vấn một giá trị hoặc một dòng.
- `queryForList(...)`: trả về danh sách kết quả dạng map hoặc kiểu đơn giản.
- `update(...)`: thực hiện INSERT, UPDATE, DELETE hoặc DML khác.
- `batchUpdate(...)`: thực hiện một nhóm DML với nhiều bộ tham số.
- `execute(...)`: thực hiện callback hoặc SQL cần kiểm soát thấp hơn.
- `call(...)`: gọi stored procedure/function trong các trường hợp cần khai báo parameter rõ ràng.

Template quản lý việc lấy và giải phóng JDBC resources. Khi có transaction do Spring quản lý, template tham gia transaction hiện tại thông qua `DataSourceUtils`.

### 1.2. NamedParameterJdbcTemplate làm gì?

JDBC `PreparedStatement` dùng placeholder vị trí `?`:

```sql
SELECT order_id, total_amount
FROM orders
WHERE customer_id = ?
  AND order_status = ?
```

Ứng dụng phải truyền giá trị đúng thứ tự. Với câu SQL dài, nhiều placeholder hoặc cùng một giá trị xuất hiện nhiều lần, việc đếm vị trí dễ gây nhầm lẫn.

`NamedParameterJdbcTemplate` cho phép đặt tên:

```sql
SELECT order_id, total_amount
FROM orders
WHERE customer_id = :customerId
  AND order_status = :status
```

Giá trị được truyền bằng tên tương ứng. Spring chuyển named parameter thành placeholder JDBC khi thực thi. Đây vẫn là bind variable, không phải nối chuỗi SQL.

### 1.3. Khi nào nên dùng JDBC thay vì JPA?

Spring JDBC phù hợp khi:

- SQL cần được kiểm soát chính xác, đặc biệt với truy vấn Oracle phức tạp.
- Ứng dụng dùng analytic function, CTE, hint hoặc tính năng SQL riêng của Oracle.
- Cần truy vấn báo cáo, bulk DML hoặc batch với lượng dữ liệu lớn.
- Muốn tránh overhead của ORM cho một số luồng truy cập dữ liệu.
- Cần làm việc trực tiếp với stored procedure hoặc kiểu dữ liệu đặc thù.

JPA phù hợp khi mô hình object và quan hệ entity là trọng tâm, còn JDBC phù hợp khi SQL và cách database thực thi là trọng tâm. Một ứng dụng Spring Boot có thể dùng JPA cho phần CRUD thông thường và Spring JDBC cho báo cáo hoặc truy vấn chuyên biệt; cần thống nhất transaction manager và `DataSource` khi phối hợp hai cách.

## 2. Cấu hình Spring Boot với Oracle JDBC

### 2.1. Dependency

Với Maven, dependency Spring JDBC thường được cung cấp qua starter:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jdbc</artifactId>
</dependency>

<dependency>
    <groupId>com.oracle.database.jdbc</groupId>
    <artifactId>ojdbc11</artifactId>
    <scope>runtime</scope>
</dependency>
```

Chọn artifact JDBC phù hợp với Java runtime và Oracle Database version. Ví dụ `ojdbc11` dành cho các Java version được driver hỗ trợ tương ứng; không nên tự chọn driver mới nhất mà bỏ qua ma trận tương thích của database, JDK và Spring Boot. Trong dự án thực tế, nên quản lý version qua Spring Boot dependency management hoặc dependency management nội bộ để tránh xung đột.

Nếu dự án đã dùng `spring-boot-starter-data-jpa`, starter JPA thường kéo theo Spring JDBC infrastructure cần thiết. Tuy nhiên, khai báo starter JDBC riêng có thể làm ý định dùng `JdbcTemplate` rõ ràng hơn.

### 2.2. Cấu hình DataSource

Ví dụ `application.yml`:

```yaml
spring:
  datasource:
    url: jdbc:oracle:thin:@//db-host.example.com:1521/SALES_PDB
    username: app_user
    password: ${DB_PASSWORD}
    driver-class-name: oracle.jdbc.OracleDriver
    hikari:
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 30000
      validation-timeout: 5000
```

`url` ở trên dùng service name theo dạng Easy Connect. Với RAC, ứng dụng thường kết nối bằng SCAN/service name đã được DBA công bố, thay vì hard-code một instance cụ thể. Password nên lấy từ secret manager hoặc biến môi trường, không commit vào Git.

Spring Boot thường tự cấu hình `DataSource` và `JdbcTemplate` khi có JDBC starter và driver phù hợp. HikariCP là connection pool mặc định phổ biến trong Spring Boot. Không nên đặt `maximum-pool-size` quá lớn theo cảm tính; tổng số connection từ mọi instance ứng dụng cần nằm trong giới hạn database và workload.

### 2.3. Inject JdbcTemplate

Khi auto-configuration hoạt động, có thể inject trực tiếp:

```java
@Repository
public class OrderRepository {

    private final JdbcTemplate jdbcTemplate;

    public OrderRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }
}
```

Spring Boot cũng có thể tạo `NamedParameterJdbcTemplate` dựa trên `JdbcTemplate`/`DataSource`:

```java
@Repository
public class OrderSearchRepository {

    private final NamedParameterJdbcTemplate namedJdbc;

    public OrderSearchRepository(NamedParameterJdbcTemplate namedJdbc) {
        this.namedJdbc = namedJdbc;
    }
}
```

Nếu ứng dụng có nhiều `DataSource`, cần khai báo rõ bean nào là `@Primary`, bean `JdbcTemplate` nào gắn với DataSource nào và transaction manager nào quản lý từng database. Không nên inject một template mặc định rồi giả định nó đang trỏ đúng database.

### 2.4. Cấu hình tường minh khi có nhiều DataSource

Ví dụ cấu hình một DataSource Oracle riêng:

```java
@Configuration
public class OracleJdbcConfig {

    @Bean
    @ConfigurationProperties("app.oracle.datasource")
    public DataSource oracleDataSource() {
        return DataSourceBuilder.create().build();
    }

    @Bean
    public JdbcTemplate oracleJdbcTemplate(
            @Qualifier("oracleDataSource") DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    @Bean
    public NamedParameterJdbcTemplate oracleNamedJdbcTemplate(
            @Qualifier("oracleDataSource") DataSource dataSource) {
        return new NamedParameterJdbcTemplate(dataSource);
    }
}
```

Trong cấu hình production, nên cấu hình pool implementation và các thuộc tính pool rõ ràng thay vì chỉ dựa vào `DataSourceBuilder` mặc định. Nếu có transaction riêng cho Oracle DataSource, khai báo `DataSourceTransactionManager` hoặc `JdbcTransactionManager` phù hợp và dùng đúng bean qualifier ở repository/service.

## 3. Truy vấn cơ bản với JdbcTemplate

### 3.1. Query trả về danh sách object

`RowMapper<T>` ánh xạ một dòng `ResultSet` thành một object Java. Ví dụ DTO:

```java
public record OrderSummary(
        long orderId,
        long customerId,
        BigDecimal totalAmount,
        String status) {
}
```

Repository:

```java
@Repository
public class OrderRepository {

    private final JdbcTemplate jdbcTemplate;

    public OrderRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public List<OrderSummary> findPaidOrders(long customerId) {
        String sql = """
            SELECT order_id,
                   customer_id,
                   total_amount,
                   order_status
            FROM app.orders
            WHERE customer_id = ?
              AND order_status = 'PAID'
            ORDER BY order_date DESC, order_id DESC
            """;

        return jdbcTemplate.query(sql, (rs, rowNum) ->
                new OrderSummary(
                        rs.getLong("ORDER_ID"),
                        rs.getLong("CUSTOMER_ID"),
                        rs.getBigDecimal("TOTAL_AMOUNT"),
                        rs.getString("ORDER_STATUS")
                ), customerId);
    }
}
```

`JdbcTemplate` nhận SQL, `RowMapper` và tham số bind. Template thực hiện prepare statement, bind giá trị, lặp qua `ResultSet` và đóng resources.

Nếu cột số có thể NULL, `ResultSet.getLong()` trả về 0 cho SQL NULL. Cần gọi `rs.wasNull()` ngay sau khi đọc cột hoặc dùng `getObject(..., Long.class)` khi driver hỗ trợ để phân biệt NULL với giá trị 0. Với DTO có nullable field, không nên âm thầm biến NULL thành zero.

### 3.2. Query một giá trị

Ví dụ đếm số đơn hàng:

```java
public long countOrders(long customerId) {
    String sql = """
        SELECT COUNT(*)
        FROM app.orders
        WHERE customer_id = ?
        """;

    Long count = jdbcTemplate.queryForObject(sql, Long.class, customerId);
    return count == null ? 0L : count;
}
```

`COUNT(*)` trả một dòng. `queryForObject` phù hợp khi SQL được kỳ vọng trả đúng một dòng. Nếu truy vấn không trả dòng hoặc trả nhiều dòng trong ngữ cảnh yêu cầu một kết quả, Spring ném exception tương ứng. Với aggregate như `COUNT`, database thường luôn trả một dòng, nhưng các aggregate khác có thể trả NULL khi không có input.

### 3.3. Query một dòng thành object

```java
public OrderSummary findById(long orderId) {
    String sql = """
        SELECT order_id,
               customer_id,
               total_amount,
               order_status
        FROM app.orders
        WHERE order_id = ?
        """;

    return jdbcTemplate.queryForObject(sql, (rs, rowNum) ->
            new OrderSummary(
                    rs.getLong("ORDER_ID"),
                    rs.getLong("CUSTOMER_ID"),
                    rs.getBigDecimal("TOTAL_AMOUNT"),
                    rs.getString("ORDER_STATUS")
            ), orderId);
}
```

Nếu `ORDER_ID` không tồn tại, `queryForObject` sẽ ném `EmptyResultDataAccessException`. Nếu muốn biểu diễn không tìm thấy bằng `Optional`, có thể bắt riêng exception đó hoặc dùng `query(...)` rồi lấy phần tử đầu nếu có. Không nên bắt `DataAccessException` chung rồi trả `null`, vì như vậy có thể che cả lỗi kết nối hoặc lỗi SQL.

### 3.4. Insert, update và delete

`update(...)` trả về số dòng bị ảnh hưởng:

```java
public int updateOrderStatus(long orderId, String status) {
    String sql = """
        UPDATE app.orders
        SET order_status = ?,
            updated_at = SYSTIMESTAMP
        WHERE order_id = ?
        """;

    return jdbcTemplate.update(sql, status, orderId);
}
```

Với `INSERT`, có thể dùng `update` nếu không cần lấy generated key. Nếu cần lấy sequence hoặc key do database sinh, có thể dùng `GeneratedKeyHolder` với cấu hình phù hợp, hoặc truy vấn sequence/`RETURNING` theo hỗ trợ của Oracle JDBC và phiên bản. Với Oracle, sequence `NEXTVAL` là cách phổ biến:

```java
public long nextOrderId() {
    Long value = jdbcTemplate.queryForObject(
            "SELECT app.order_id_seq.NEXTVAL FROM dual",
            Long.class);
    return value;
}
```

Sequence có thể tạo gap và không bảo đảm thứ tự commit. Không dùng sequence như bộ đếm liên tục không có khoảng trống.

## 4. NamedParameterJdbcTemplate

### 4.1. Dùng MapSqlParameterSource

Ví dụ truy vấn với named parameters:

```java
public List<OrderSummary> searchOrders(
        long customerId,
        String status,
        LocalDateTime fromTime) {

    String sql = """
        SELECT order_id,
               customer_id,
               total_amount,
               order_status
        FROM app.orders
        WHERE customer_id = :customerId
          AND order_status = :status
          AND order_date >= :fromTime
        ORDER BY order_date DESC, order_id DESC
        """;

    MapSqlParameterSource params = new MapSqlParameterSource()
            .addValue("customerId", customerId, Types.NUMERIC)
            .addValue("status", status, Types.VARCHAR)
            .addValue("fromTime", Timestamp.valueOf(fromTime), Types.TIMESTAMP);

    return namedJdbc.query(sql, params, (rs, rowNum) ->
            new OrderSummary(
                    rs.getLong("ORDER_ID"),
                    rs.getLong("CUSTOMER_ID"),
                    rs.getBigDecimal("TOTAL_AMOUNT"),
                    rs.getString("ORDER_STATUS")
            ));
}
```

`MapSqlParameterSource` cho phép khai báo tên, giá trị và JDBC type. Việc khai báo type đặc biệt hữu ích với NULL hoặc các kiểu Oracle mà driver không suy luận đúng từ Java value.

### 4.2. Dùng Map.of khi tham số đơn giản

```java
String sql = """
    SELECT order_id, order_status
    FROM app.orders
    WHERE customer_id = :customerId
    """;

List<Map<String, Object>> rows = namedJdbc.queryForList(
        sql,
        Map.of("customerId", 501L));
```

`Map.of` không chấp nhận key hoặc value là `null`. Nếu tham số có thể NULL, dùng `MapSqlParameterSource` hoặc `Map` mutable phù hợp.

### 4.3. Tái sử dụng cùng một named parameter

```sql
SELECT order_id,
       customer_id
FROM app.orders
WHERE customer_id = :customerId
   OR referred_by_customer_id = :customerId
```

Named parameter có thể được dùng nhiều lần; ứng dụng chỉ cần cung cấp một giá trị `customerId`. Spring mở rộng tên tham số thành placeholder JDBC tương ứng.

### 4.4. Named parameter với IN list

Một lợi ích đáng chú ý của `NamedParameterJdbcTemplate` là hỗ trợ collection:

```java
String sql = """
    SELECT order_id,
           customer_id,
           order_status
    FROM app.orders
    WHERE order_id IN (:orderIds)
    """;

MapSqlParameterSource params = new MapSqlParameterSource()
        .addValue("orderIds", List.of(1001L, 1002L, 1003L));

List<OrderSummary> orders = namedJdbc.query(sql, params, orderRowMapper);
```

Spring mở rộng collection thành số lượng placeholder phù hợp. Không cần nối chuỗi danh sách ID vào SQL.

Tuy nhiên, cần xử lý danh sách rỗng trước khi chạy. `IN ()` không phải cú pháp hợp lệ trong Oracle. Tùy semantics, có thể trả danh sách rỗng ngay trong Java, hoặc thêm điều kiện luôn sai. Ví dụ:

```java
public List<OrderSummary> findByIds(Collection<Long> ids) {
    if (ids == null || ids.isEmpty()) {
        return List.of();
    }

    String sql = """
        SELECT order_id, customer_id, total_amount, order_status
        FROM app.orders
        WHERE order_id IN (:ids)
        """;

    return namedJdbc.query(
            sql,
            new MapSqlParameterSource("ids", ids),
            orderRowMapper);
}
```

Oracle có giới hạn số expression trong một danh sách `IN` ở nhiều phiên bản (thường gặp giới hạn 1.000 expression trước Oracle Database 23ai; cần xác nhận theo version cụ thể). Với tập ID lớn, chia batch, nạp ID vào staging/global temporary table hoặc dùng collection/table type phù hợp thay vì tạo một `IN` list cực dài.

### 4.5. Named parameter không thay thế identifier

Bind parameter chỉ dùng cho giá trị dữ liệu. Không thể bind tên bảng, tên cột, từ khóa `ASC`/`DESC` hoặc một đoạn SQL:

```sql
-- Không hoạt động như cách bind giá trị:
SELECT * FROM :tableName
```

Nếu tên bảng hoặc cột cần thay đổi theo lựa chọn người dùng, dùng allowlist ở Java:

```java
private static final Map<String, String> SORT_COLUMNS = Map.of(
        "date", "ORDER_DATE",
        "amount", "TOTAL_AMOUNT",
        "id", "ORDER_ID"
);

String sortColumn = SORT_COLUMNS.get(requestedSort);
if (sortColumn == null) {
    throw new IllegalArgumentException("Unsupported sort field");
}

String direction = descending ? "DESC" : "ASC";
String sql = "SELECT order_id, order_date, total_amount " +
        "FROM app.orders ORDER BY " + sortColumn + " " + direction;
```

Chỉ identifier và token đã được chọn từ allowlist mới được ghép vào SQL. Các giá trị như customer ID, status hoặc ngày vẫn phải bind. Không nối input tùy ý từ HTTP request vào SQL.

## 5. RowMapper, ResultSetExtractor và mapping kết quả

### 5.1. RowMapper

`RowMapper<T>` ánh xạ một dòng thành một object. Spring gọi mapper cho từng dòng và quản lý vòng lặp `ResultSet`.

```java
private final RowMapper<OrderSummary> orderRowMapper = (rs, rowNum) ->
        new OrderSummary(
                rs.getLong("ORDER_ID"),
                rs.getLong("CUSTOMER_ID"),
                rs.getBigDecimal("TOTAL_AMOUNT"),
                rs.getString("ORDER_STATUS")
        );
```

Nên tái sử dụng mapper khi cùng một projection xuất hiện ở nhiều truy vấn. Không nên để mapper gọi thêm query cho mỗi dòng vì sẽ tạo N+1 query. Nếu cần dữ liệu liên quan, hãy join hoặc tải theo batch.

### 5.2. BeanPropertyRowMapper

Spring cung cấp `BeanPropertyRowMapper` để ánh xạ cột theo tên sang property Java theo quy tắc chuyển đổi phổ biến:

```java
public class CustomerRow {
    private Long customerId;
    private String customerName;
    private BigDecimal creditLimit;

    // getters/setters
}
```

```java
List<CustomerRow> customers = jdbcTemplate.query(
        "SELECT customer_id, customer_name, credit_limit FROM app.customers",
        new BeanPropertyRowMapper<>(CustomerRow.class));
```

`CUSTOMER_ID` thường được ánh xạ thành `customerId`. Tuy nhiên, mapping tự động có thể không phù hợp với tên cột phức tạp, nullable primitive, conversion đặc thù hoặc DTO immutable. Với truy vấn quan trọng, `RowMapper` tường minh thường dễ kiểm soát hơn.

### 5.3. ResultSetExtractor

`ResultSetExtractor<T>` nhận toàn bộ `ResultSet` và tự quyết định cách tổng hợp kết quả. Nó hữu ích khi một query trả các dòng lặp theo quan hệ cha-con và muốn dựng object graph trong một lần đọc.

Ví dụ một khách hàng có nhiều đơn hàng:

```java
Map<Long, CustomerWithOrders> result = jdbcTemplate.query(sql, rs -> {
    Map<Long, CustomerWithOrders> customers = new LinkedHashMap<>();

    while (rs.next()) {
        long customerId = rs.getLong("CUSTOMER_ID");
        CustomerWithOrders customer = customers.computeIfAbsent(
                customerId,
                id -> new CustomerWithOrders(
                        id,
                        rsString(rs, "CUSTOMER_NAME")));

        long orderId = rs.getLong("ORDER_ID");
        if (!rs.wasNull()) {
            customer.addOrder(new OrderItem(
                    orderId,
                    rs.getBigDecimal("TOTAL_AMOUNT")));
        }
    }

    return customers;
});
```

Đoạn trên minh họa ý tưởng; trong code thực tế cần tránh gọi `ResultSet` bên trong lambda `computeIfAbsent` nếu việc capture biến làm code khó đọc hoặc xử lý checked exception phức tạp. Có thể đọc tên khách hàng trước, kiểm tra map rồi tạo object tường minh.

### 5.4. Column alias để mapping ổn định

Với biểu thức hoặc tên cột phức tạp, dùng alias rõ ràng:

```sql
SELECT o.order_id AS order_id,
       o.total_amount * :taxRate AS amount_with_tax
FROM app.orders o
```

Sau đó đọc theo alias:

```java
rs.getBigDecimal("AMOUNT_WITH_TAX");
```

Oracle thường trả tên column label viết hoa nếu alias không đặt trong dấu nháy kép. Tránh quoted alias với kiểu chữ hỗn hợp nếu không có lý do, vì khi đó tên label có thể phân biệt chữ hoa/thường.

## 6. Ánh xạ NUMBER của Oracle sang Java

`NUMBER` là kiểu số chính của Oracle, hỗ trợ precision và scale. Trong Java, `BigDecimal` thường là lựa chọn an toàn nhất cho dữ liệu tiền tệ hoặc giá trị cần giữ precision.

| Oracle | Java thường dùng | Lưu ý |
|---|---|---|
| `NUMBER(p, s)` | `BigDecimal` | Giữ precision/scale; phù hợp tiền tệ |
| `NUMBER(10,0)` | `Long` hoặc `BigDecimal` | Chỉ dùng `Long` nếu miền giá trị chắc chắn nằm trong giới hạn |
| `NUMBER(1)` | `Integer`, `Short` hoặc quy ước boolean | Không tự động coi mọi NUMBER(1) là boolean |
| `BINARY_FLOAT` | `Float` | Số dấu phẩy động nhị phân |
| `BINARY_DOUBLE` | `Double` | Số dấu phẩy động nhị phân |

### 6.1. Dùng BigDecimal cho tiền

```java
BigDecimal amount = rs.getBigDecimal("TOTAL_AMOUNT");
```

Không nên dùng `double` cho tiền nếu yêu cầu nghiệp vụ cần độ chính xác thập phân. `double` biểu diễn số nhị phân nên nhiều số thập phân không thể lưu chính xác.

Khi bind:

```java
jdbcTemplate.update(
        "UPDATE app.orders SET total_amount = ? WHERE order_id = ?",
        new BigDecimal("1250.50"),
        1001L);
```

Tạo `BigDecimal` từ chuỗi thập phân giúp tránh sai số phát sinh khi tạo từ `double`:

```java
new BigDecimal("0.10");
```

Tránh:

```java
new BigDecimal(0.10);
```

### 6.2. Precision và scale

Với `NUMBER(12,2)`, tổng precision là 12 chữ số, scale là 2 chữ số sau dấu thập phân. Ứng dụng nên validate trước khi bind để tránh giá trị vượt precision hoặc có scale không phù hợp.

```java
BigDecimal normalized = amount.setScale(2, RoundingMode.HALF_UP);
```

Chọn rounding mode theo quy tắc nghiệp vụ. Không nên để database âm thầm làm tròn nếu ứng dụng cần kiểm soát chính sách làm tròn.

### 6.3. NUMBER có thể NULL

`getBigDecimal()` trả `null` nếu SQL NULL, nên phù hợp với cột nullable. Với primitive numeric getters như `getLong()` hoặc `getInt()`, cần kiểm tra `wasNull()`:

```java
long value = rs.getLong("OPTIONAL_COUNT");
Long optionalCount = rs.wasNull() ? null : value;
```

`wasNull()` phải được gọi ngay sau getter tương ứng vì nó phản ánh lần đọc cột gần nhất.

## 7. Ánh xạ DATE, TIMESTAMP và múi giờ

Oracle có một điểm dễ gây nhầm: kiểu `DATE` của Oracle lưu cả ngày và thời gian đến giây, không giống `java.sql.Date` chỉ biểu diễn ngày theo JDBC semantics. Nếu ứng dụng chỉ dùng `LocalDate` cho Oracle `DATE`, phần giờ/phút/giây có thể bị mất.

### 7.1. Oracle DATE

Oracle `DATE` lưu năm, tháng, ngày, giờ, phút và giây; không lưu fractional seconds và không lưu time zone.

Java mapping thường dùng:

- `LocalDateTime` nếu cần giữ cả phần ngày và giờ.
- `java.sql.Timestamp` làm kiểu JDBC trung gian.
- `LocalDate` chỉ khi cột được quy ước luôn chứa thời điểm nửa đêm hoặc ứng dụng chủ động bỏ phần thời gian.

Đọc Oracle DATE:

```java
LocalDateTime orderTime = rs.getTimestamp("ORDER_DATE").toLocalDateTime();
```

Bind:

```java
Timestamp timestamp = Timestamp.valueOf(orderTime);
jdbcTemplate.update(
        "INSERT INTO app.orders(order_id, order_date) VALUES (?, ?)",
        orderId,
        timestamp);
```

Với JDBC driver hỗ trợ JDBC 4.2 và kiểu tương ứng, có thể dùng `getObject`/`setObject` với `LocalDateTime`, nhưng nên xác nhận hành vi trên đúng phiên bản Oracle JDBC đang triển khai.

### 7.2. Oracle TIMESTAMP

`TIMESTAMP(p)` lưu ngày giờ và fractional seconds với precision `p` (tối đa theo giới hạn Oracle). Java `LocalDateTime` phù hợp khi cột không lưu time zone.

```java
LocalDateTime createdAt = rs.getTimestamp("CREATED_AT").toLocalDateTime();
```

Nếu dùng `Timestamp`, hãy nhớ `Timestamp` không chứa timezone. Không tự gắn timezone vào giá trị này nếu schema không quy định timezone semantics.

### 7.3. TIMESTAMP WITH TIME ZONE

`TIMESTAMP WITH TIME ZONE` lưu thời điểm cùng thông tin time zone/offset theo semantics của Oracle. Java `OffsetDateTime` thường là kiểu biểu diễn phù hợp hơn `LocalDateTime` khi cần giữ offset.

Với Oracle JDBC hỗ trợ JDBC 4.2:

```java
OffsetDateTime eventTime = rs.getObject("EVENT_TIME", OffsetDateTime.class);
```

Bind:

```java
namedJdbc.update(
        "INSERT INTO app.events(event_id, event_time) " +
        "VALUES (:eventId, :eventTime)",
        new MapSqlParameterSource()
                .addValue("eventId", eventId)
                .addValue("eventTime", eventTime));
```

Khả năng map chính xác còn phụ thuộc Oracle JDBC driver version và kiểu dữ liệu thực tế. Nên có integration test với database/driver production-like, đặc biệt khi cần bảo toàn region ID như `Europe/Paris` thay vì chỉ offset `+01:00`.

### 7.4. TIMESTAMP WITH LOCAL TIME ZONE

`TIMESTAMP WITH LOCAL TIME ZONE` được chuẩn hóa theo database time zone khi lưu và hiển thị theo session time zone khi đọc. Kiểu này không lưu nguyên time zone gốc của client theo cách `TIMESTAMP WITH TIME ZONE` làm.

Khi map sang Java, cần xác định session time zone và quy ước ứng dụng. Có thể đọc thành `Timestamp`/`LocalDateTime` theo session time zone, nhưng nếu nghiệp vụ cần biết timezone gốc của người dùng, phải lưu timezone/region riêng hoặc dùng kiểu dữ liệu phù hợp.

### 7.5. Tránh implicit conversion và NLS phụ thuộc session

Không truyền ngày giờ dưới dạng chuỗi phụ thuộc `NLS_DATE_FORMAT`:

```java
// Tránh: kết quả phụ thuộc format của session/database.
jdbcTemplate.query(sql, rowMapper, "14/11/2026");
```

Bind `Timestamp`, `LocalDateTime` hoặc `java.sql.Date` phù hợp thay vì để Oracle parse chuỗi. Nếu buộc phải parse chuỗi trong SQL, dùng format mask tường minh:

```sql
TO_DATE(:orderDateText, 'YYYY-MM-DD')
```

Tuy nhiên, cách tốt hơn thường là chuyển đổi sang kiểu Java trước và bind kiểu JDBC tương ứng.

## 8. VARCHAR2, CHAR, NVARCHAR2 và chuỗi Unicode

### 8.1. VARCHAR2

`VARCHAR2` lưu chuỗi độ dài biến đổi. Trong Java, dùng `String`:

```java
String customerName = rs.getString("CUSTOMER_NAME");
```

Bind bằng `String` và `Types.VARCHAR` khi cần khai báo type rõ ràng:

```java
params.addValue("customerName", customerName, Types.VARCHAR);
```

Độ dài tối đa của `VARCHAR2` phụ thuộc cấu hình `MAX_STRING_SIZE`, byte/char semantics và phiên bản. Không nên giả định giới hạn luôn là một con số duy nhất cho mọi database.

### 8.2. CHAR có padding

`CHAR(n)` là kiểu độ dài cố định và có thể được padding bằng khoảng trắng. Khi đọc bằng `getString`, ứng dụng có thể nhận chuỗi có trailing spaces tùy driver/kiểu mapping. Nếu dữ liệu là mã trạng thái fixed-width, cần cân nhắc `trim()` ở ranh giới mapping hoặc chuẩn hóa dữ liệu theo hợp đồng.

Không nên trim mọi chuỗi một cách tự động. Khoảng trắng có thể có ý nghĩa trong dữ liệu tự do; chỉ trim các cột có quy ước rõ ràng.

### 8.3. NVARCHAR2 và national character set

`NVARCHAR2` dùng national character set của Oracle. Java `String` có thể biểu diễn Unicode, nhưng JDBC type và driver mapping cần được chọn đúng khi bind. Có thể dùng `Types.NVARCHAR` hoặc `setNString` qua `PreparedStatement` nếu cần.

Ví dụ với `SqlParameterValue`:

```java
MapSqlParameterSource params = new MapSqlParameterSource()
        .addValue("displayName",
                new SqlParameterValue(Types.NVARCHAR, displayName));
```

Phần lớn ứng dụng mới dùng database character set Unicode như AL32UTF8 cho `VARCHAR2`; chỉ dùng `NCHAR`/`NVARCHAR2` khi schema có chủ đích rõ ràng. Cần kiểm tra character set của database và cột để tránh conversion hoặc ký tự bị thay thế.

### 8.4. Empty string và NULL

Trong Oracle SQL, chuỗi rỗng `''` đối với kiểu character thông thường được xử lý như `NULL`. Điều này khác với một số database coi empty string là giá trị riêng biệt.

Vì vậy:

- Java `""` khi bind vào `VARCHAR2` có thể được lưu/nhìn nhận như NULL.
- `IS NULL` là cách kiểm tra giá trị không có nội dung theo semantics Oracle.
- Không dùng `= ''` để tìm chuỗi rỗng trong Oracle.
- Nếu nghiệp vụ cần phân biệt “không cung cấp” với “cố ý để trống”, cần mô hình hóa riêng, ví dụ cờ trạng thái hoặc giá trị sentinel được quy ước.

## 9. CLOB, NCLOB, BLOB và dữ liệu lớn

### 9.1. CLOB và NCLOB

`CLOB` lưu dữ liệu ký tự lớn; `NCLOB` lưu dữ liệu ký tự lớn theo national character set. Java có thể đọc bằng `getString()` cho nội dung nhỏ, nhưng với LOB lớn nên dùng stream để tránh nạp toàn bộ vào heap.

Ví dụ đọc CLOB dạng stream:

```java
String sql = "SELECT document_body FROM app.documents WHERE document_id = ?";

String document = jdbcTemplate.queryForObject(sql, (rs, rowNum) -> {
    try (Reader reader = rs.getCharacterStream("DOCUMENT_BODY")) {
        if (reader == null) {
            return null;
        }
        StringBuilder content = new StringBuilder();
        char[] buffer = new char[8192];
        int count;
        while ((count = reader.read(buffer)) != -1) {
            content.append(buffer, 0, count);
        }
        return content.toString();
    }
}, documentId);
```

Ví dụ trên vẫn đưa toàn bộ nội dung vào `String` cuối cùng; lợi ích là kiểm soát cách đọc. Nếu document rất lớn, nên xử lý streaming trực tiếp tới file hoặc output consumer thay vì tạo `String` lớn.

### 9.2. BLOB

`BLOB` lưu dữ liệu nhị phân. Java có thể dùng `byte[]` cho nội dung nhỏ hoặc `InputStream` cho nội dung lớn.

```java
byte[] payload = rs.getBytes("FILE_CONTENT");
```

Với file lớn, `getBinaryStream()` giúp xử lý theo chunk. Lưu ý `ResultSet`, statement và connection phải còn mở trong khi stream được đọc. Không trả một `InputStream` gắn với `ResultSet` ra khỏi callback của `JdbcTemplate` rồi để template đóng connection trước khi caller đọc xong.

Nếu cần trả stream cho tầng web, hãy thiết kế callback/streaming response sao cho transaction và connection vẫn được giữ hợp lệ trong suốt quá trình đọc, đồng thời giới hạn thời gian giữ connection. Một lựa chọn khác là copy LOB sang file/temp storage trong callback rồi trả file stream độc lập.

### 9.3. Bind LOB

Với CLOB nhỏ, `String` thường đủ. Với nội dung lớn, có thể dùng `SqlLobValue` và `LobHandler` trong `PreparedStatementCreator`/`SqlParameterSource` theo API Spring tương ứng. Với BLOB, dùng `InputStream` và độ dài khi API yêu cầu.

Ví dụ khái niệm dùng `PreparedStatement` trực tiếp trong callback:

```java
jdbcTemplate.update(connection -> {
    PreparedStatement ps = connection.prepareStatement(
            "INSERT INTO app.documents(document_id, document_body) VALUES (?, ?)");
    ps.setLong(1, documentId);
    ps.setCharacterStream(2, new StringReader(documentText), documentText.length());
    return ps;
});
```

Template quản lý statement/connection. Với stream do ứng dụng tạo, cần bảo đảm stream được đóng theo ownership của ứng dụng và phù hợp với cách driver consume dữ liệu.

## 10. RAW, UUID và kiểu nhị phân

Oracle `RAW(n)` lưu dữ liệu byte. JDBC thường map sang `byte[]`:

```java
byte[] token = rs.getBytes("TOKEN_RAW");
```

Khi bind:

```java
jdbcTemplate.update(
        "INSERT INTO app.api_tokens(token_id, token_raw) VALUES (?, ?)",
        tokenId,
        token);
```

Nếu lưu UUID, cần thống nhất encoding. Có thể lưu UUID dưới dạng `RAW(16)` để tiết kiệm hơn chuỗi 36 ký tự, nhưng Java cần chuyển đổi hai chiều nhất quán giữa `UUID` và 16 byte. Không dùng `UUID.toString()` rồi parse như thể đó là byte representation của RAW.

Một hàm chuyển đổi:

```java
public static byte[] uuidToBytes(UUID uuid) {
    ByteBuffer buffer = ByteBuffer.allocate(16);
    buffer.putLong(uuid.getMostSignificantBits());
    buffer.putLong(uuid.getLeastSignificantBits());
    return buffer.array();
}

public static UUID bytesToUuid(byte[] bytes) {
    if (bytes == null || bytes.length != 16) {
        throw new IllegalArgumentException("UUID RAW value must contain 16 bytes");
    }
    ByteBuffer buffer = ByteBuffer.wrap(bytes);
    return new UUID(buffer.getLong(), buffer.getLong());
}
```

Nếu database đã có quy ước byte order khác, phải tuân theo quy ước đó thay vì áp dụng hàm mẫu một cách máy móc.

## 11. Boolean và các kiểu đặc thù Oracle

### 11.1. Boolean trong Oracle SQL phụ thuộc phiên bản

Ở các phiên bản Oracle Database trước khi có SQL `BOOLEAN` trong bảng (ví dụ nhiều hệ thống 19c/21c), không thể khai báo cột table SQL kiểu `BOOLEAN` như trong Java. Ứng dụng thường dùng quy ước:

- `NUMBER(1)` với `0`/`1`.
- `CHAR(1)` với `Y`/`N`.
- Một mã trạng thái rõ ràng nếu có nhiều trạng thái hơn true/false.

Ví dụ mapping `NUMBER(1)`:

```java
Boolean active = rs.getObject("IS_ACTIVE") == null
        ? null
        : rs.getInt("IS_ACTIVE") == 1;
```

Khi bind, chuyển đổi rõ ràng:

```java
Integer activeValue = active == null ? null : (active ? 1 : 0);
```

Oracle Database 23ai/23c bổ sung kiểu SQL `BOOLEAN` cho SQL table/column. Hỗ trợ mapping JDBC phụ thuộc driver và phiên bản; hãy kiểm tra driver cụ thể trước khi dùng `Boolean` trực tiếp với SQL BOOLEAN trong schema. PL/SQL `BOOLEAN` và SQL BOOLEAN là hai bối cảnh cần phân biệt theo phiên bản.

### 11.2. ROWID và UROWID

`ROWID` định danh vị trí dòng trong database. JDBC có kiểu `java.sql.RowId` và Oracle driver có hỗ trợ riêng. Không nên dùng ROWID làm khóa nghiệp vụ lâu dài vì row movement, table reorganize hoặc thay đổi cấu trúc có thể làm vị trí vật lý thay đổi. Dùng primary key cho tham chiếu nghiệp vụ.

### 11.3. XMLTYPE, JSON và object types

Oracle có các kiểu/khả năng như `XMLTYPE`, JSON và user-defined object types. Cách mapping JDBC phụ thuộc Oracle JDBC driver và API cụ thể. Với JSON, ứng dụng có thể lưu trong `CLOB`, `BLOB` hoặc kiểu JSON native tùy database version. Nếu cần thao tác JSON bằng SQL, hãy kiểm tra khả năng và giới hạn của version; không giả định mọi driver map native JSON thành `String` mà không có conversion.

Với Oracle object type hoặc collection type, có thể cần `Struct`, `Array` hoặc Oracle-specific JDBC classes. Nên cô lập mapping trong repository/adapter riêng để phần service không phụ thuộc API đặc thù của driver.

## 12. Bind NULL và khai báo JDBC type

NULL là trường hợp dễ phát sinh lỗi vì Java `null` không cho biết kiểu SQL cần bind. Với cột `NUMBER`, `DATE`, `TIMESTAMP`, `CLOB` hoặc `NVARCHAR2`, driver có thể cần JDBC type rõ ràng.

### 12.1. Named parameter với type rõ ràng

```java
MapSqlParameterSource params = new MapSqlParameterSource()
        .addValue("customerId", customerId, Types.NUMERIC)
        .addValue("comment", comment, Types.VARCHAR)
        .addValue("cancelledAt", cancelledAt, Types.TIMESTAMP);
```

Nếu `comment` hoặc `cancelledAt` là null, Spring vẫn biết JDBC type cần dùng.

### 12.2. SqlParameterValue

Với `JdbcTemplate`, có thể bọc giá trị và type:

```java
jdbcTemplate.update(
        "UPDATE app.orders SET cancelled_at = ? WHERE order_id = ?",
        new SqlParameterValue(Types.TIMESTAMP, cancelledAt),
        orderId);
```

### 12.3. setNull trong PreparedStatement

Khi cần kiểm soát JDBC trực tiếp:

```java
jdbcTemplate.update(connection -> {
    PreparedStatement ps = connection.prepareStatement(
            "UPDATE app.orders SET cancelled_at = ? WHERE order_id = ?");
    if (cancelledAt == null) {
        ps.setNull(1, Types.TIMESTAMP);
    } else {
        ps.setTimestamp(1, Timestamp.valueOf(cancelledAt));
    }
    ps.setLong(2, orderId);
    return ps;
});
```

Không dùng chuỗi `'NULL'` để đại diện SQL NULL. `'NULL'` là bốn ký tự văn bản; SQL NULL là giá trị không xác định.

## 13. Oracle REF CURSOR và stored procedure

Oracle stored procedure có thể trả dữ liệu qua `SYS_REFCURSOR`. Spring JDBC hỗ trợ gọi procedure thông qua `SimpleJdbcCall` hoặc `CallableStatement` tùy nhu cầu.

Ví dụ procedure:

```sql
CREATE OR REPLACE PROCEDURE app.get_orders_by_customer (
    p_customer_id IN NUMBER,
    p_result      OUT SYS_REFCURSOR
)
AS
BEGIN
    OPEN p_result FOR
        SELECT order_id,
               order_date,
               total_amount
        FROM app.orders
        WHERE customer_id = p_customer_id;
END;
/
```

Ví dụ dùng `SimpleJdbcCall`:

```java
SimpleJdbcCall getOrdersCall = new SimpleJdbcCall(jdbcTemplate)
        .withSchemaName("APP")
        .withProcedureName("GET_ORDERS_BY_CUSTOMER")
        .declareParameters(
                new SqlParameter("P_CUSTOMER_ID", Types.NUMERIC),
                new SqlOutParameter(
                        "P_RESULT",
                        OracleTypes.CURSOR,
                        orderRowMapper));

Map<String, Object> out = getOrdersCall.execute(
        new MapSqlParameterSource("P_CUSTOMER_ID", customerId));

@SuppressWarnings("unchecked")
List<OrderSummary> orders = (List<OrderSummary>) out.get("P_RESULT");
```

`OracleTypes.CURSOR` thuộc Oracle JDBC driver. Cần import từ package driver phù hợp với version đang dùng. Có thể cần cấu hình metadata lookup hoặc khai báo parameter tường minh để tránh khác biệt tên/metadata giữa phiên bản.

Với procedure/function phức tạp, cần kiểm thử tên parameter, direction, type, schema và cách mapping cursor. Không nên dựa vào thứ tự parameter nếu API cho phép khai báo tên rõ ràng.

## 14. Batch update với JdbcTemplate

Khi cần ghi nhiều dòng, gọi `update` trong vòng lặp Java sẽ tạo nhiều lần round-trip. `batchUpdate` cho phép gom nhiều bộ tham số thành batch JDBC.

```java
public int[][] insertOrders(List<OrderSummary> orders) {
    String sql = """
        INSERT INTO app.orders (
            order_id,
            customer_id,
            total_amount,
            order_status
        ) VALUES (?, ?, ?, ?)
        """;

    return jdbcTemplate.batchUpdate(sql, orders, 500,
            (ps, order) -> {
                ps.setLong(1, order.orderId());
                ps.setLong(2, order.customerId());
                ps.setBigDecimal(3, order.totalAmount());
                ps.setString(4, order.status());
            });
}
```

Batch size `500` chỉ là ví dụ. Cần chọn dựa trên kích thước dữ liệu, driver, memory, redo/undo, transaction duration và giới hạn ứng dụng. Batch không tự động commit mỗi batch; transaction boundary vẫn do transaction manager hoặc connection quản lý.

### 14.1. Batch với named parameter

```java
SqlParameterSource[] batch = orders.stream()
        .map(order -> new MapSqlParameterSource()
                .addValue("orderId", order.orderId(), Types.NUMERIC)
                .addValue("customerId", order.customerId(), Types.NUMERIC)
                .addValue("amount", order.totalAmount(), Types.NUMERIC)
                .addValue("status", order.status(), Types.VARCHAR))
        .toArray(SqlParameterSource[]::new);

int[] counts = namedJdbc.batchUpdate("""
        INSERT INTO app.orders (
            order_id, customer_id, total_amount, order_status
        ) VALUES (
            :orderId, :customerId, :amount, :status
        )
        """, batch);
```

Với lượng dữ liệu rất lớn, cân nhắc batch commit theo chunk nếu nghiệp vụ cho phép. Nếu toàn bộ import phải atomic, giữ một transaction cho toàn bộ batch có thể tạo undo lớn và transaction dài; cần đánh giá yêu cầu consistency trước khi chia commit.

### 14.2. Generated key và sequence trong batch

Với Oracle, cách đơn giản là sinh ID qua sequence hoặc để database xử lý theo identity column tùy version. Nếu cần lấy generated key của từng dòng trong batch, phải kiểm tra khả năng của Oracle JDBC driver và Spring version. Không nên giả định `GeneratedKeyHolder` hoạt động giống nhau trên mọi database/driver.

## 15. Transaction với Spring JDBC

`JdbcTemplate` tham gia transaction do Spring quản lý nếu nó sử dụng cùng `DataSource` với transaction manager.

### 15.1. Dùng @Transactional

```java
@Service
public class OrderService {

    private final JdbcTemplate jdbcTemplate;

    public OrderService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public void cancelOrder(long orderId) {
        int updated = jdbcTemplate.update("""
            UPDATE app.orders
            SET order_status = 'CANCELLED'
            WHERE order_id = ?
            """, orderId);

        if (updated != 1) {
            throw new IllegalStateException("Order was not found or not unique");
        }

        jdbcTemplate.update("""
            INSERT INTO app.order_audit(order_id, action, created_at)
            VALUES (?, 'CANCEL', SYSTIMESTAMP)
            """, orderId);
    }
}
```

Nếu bước audit lỗi và exception làm transaction rollback theo policy, thay đổi trạng thái đơn hàng cũng rollback. Mặc định Spring rollback với unchecked exception và `Error`; checked exception không tự động rollback trừ khi cấu hình `rollbackFor` hoặc policy khác.

### 15.2. Không tự quản lý commit trong repository

Không gọi `connection.commit()` trong repository khi Spring đang quản lý transaction. Làm vậy có thể phá vỡ transaction boundary và khiến các thao tác khác không thể rollback như mong đợi.

Để transaction manager quản lý commit/rollback. Repository chỉ thực hiện SQL và ném exception khi thất bại.

### 15.3. Nhiều DataSource

Nếu một service dùng hai database, `@Transactional` mặc định chỉ quản lý một transaction manager. Hai database không tự động trở thành một distributed transaction chỉ vì cùng được gọi trong một method. Cần JTA/XA hoặc thiết kế saga/outbox tùy yêu cầu; không nên giả định hai DataSource commit nguyên tử cùng nhau.

## 16. Exception translation và xử lý lỗi Oracle

Spring JDBC chuyển `SQLException` thành hệ thống `DataAccessException`. Điều này giúp tầng service ít phụ thuộc vào mã lỗi JDBC cụ thể.

Một số exception thường gặp:

| Spring exception | Ý nghĩa thường gặp |
|---|---|
| `DuplicateKeyException` | Vi phạm unique/primary key |
| `DataIntegrityViolationException` | Vi phạm constraint hoặc integrity |
| `BadSqlGrammarException` | SQL sai cú pháp hoặc object không hợp lệ |
| `EmptyResultDataAccessException` | Không có dòng trong thao tác kỳ vọng một kết quả |
| `IncorrectResultSizeDataAccessException` | Số dòng khác kỳ vọng |
| `CannotGetJdbcConnectionException` | Không lấy được connection |
| `QueryTimeoutException` | Truy vấn vượt query timeout được cấu hình |

Oracle error code vẫn có thể được xem qua root cause `SQLException` khi cần phân loại chi tiết. Ví dụ `ORA-00001` thường liên quan unique constraint, `ORA-02291` liên quan parent key không tồn tại và `ORA-00060` là deadlock detected.

Không nên bắt mọi `DataAccessException` rồi trả kết quả thành công hoặc `null`. Hãy phân loại lỗi có thể phục hồi, lỗi dữ liệu và lỗi hệ thống; ghi log có ngữ cảnh như SQL operation, batch ID và khóa nghiệp vụ nhưng không ghi password hoặc dữ liệu nhạy cảm.

## 17. Query timeout, fetch size và xử lý tập dữ liệu lớn

### 17.1. Query timeout

Có thể cấu hình timeout cho `JdbcTemplate`:

```java
@Bean
JdbcTemplate jdbcTemplate(DataSource dataSource) {
    JdbcTemplate template = new JdbcTemplate(dataSource);
    template.setQueryTimeout(30);
    return template;
}
```

Timeout tính bằng giây và phụ thuộc JDBC driver/database hỗ trợ. Timeout không thay thế việc tối ưu SQL. Với một số thao tác, timeout có thể làm statement bị cancel nhưng transaction vẫn cần được xử lý/rollback đúng.

### 17.2. Fetch size

Fetch size gợi ý số dòng driver lấy mỗi lần round-trip khi đọc `ResultSet`:

```java
JdbcTemplate template = new JdbcTemplate(dataSource);
template.setFetchSize(500);
```

Giá trị phù hợp phụ thuộc độ rộng dòng, network latency, heap và driver. Fetch size lớn giảm round-trip nhưng tăng memory/buffer; fetch size nhỏ có thể tăng số lần trao đổi với database.

### 17.3. Streaming và connection lifetime

`JdbcTemplate.query(...)` với `RowCallbackHandler` có thể xử lý từng dòng mà không cần giữ toàn bộ kết quả trong một `List`:

```java
jdbcTemplate.query(
        "SELECT order_id, total_amount FROM app.orders",
        (RowCallbackHandler) rs -> {
            long orderId = rs.getLong("ORDER_ID");
            BigDecimal amount = rs.getBigDecimal("TOTAL_AMOUNT");
            processOrder(orderId, amount);
        });
```

Template vẫn giữ connection và ResultSet trong thời gian callback chạy. Không nên thực hiện công việc chậm như gọi HTTP hoặc chờ người dùng trong callback, vì connection bị giữ lâu. Với export lớn, cân nhắc stream dữ liệu ra file/object storage theo chunk và kiểm soát transaction/timeout.

### 17.4. Oracle cursor và fetch behavior

Oracle JDBC driver sử dụng cursor và fetch round-trip để đọc kết quả. `fetchSize` ảnh hưởng số dòng lấy mỗi lượt. Với truy vấn lớn, cần đo kết hợp fetch size, row width, network và heap. Không tăng fetch size vô hạn vì các dòng chứa CLOB/BLOB hoặc object lớn có thể làm memory tăng nhanh.

## 18. SQL injection và an toàn khi bind parameter

Luôn dùng bind parameter cho giá trị dữ liệu:

```java
String sql = "SELECT order_id FROM app.orders WHERE customer_id = ?";
jdbcTemplate.query(sql, rowMapper, customerId);
```

Không nối chuỗi:

```java
// Không an toàn nếu customerId đến từ input bên ngoài.
String sql = "SELECT order_id FROM app.orders WHERE customer_id = " + customerId;
```

Named parameter cũng bind giá trị và có cùng lợi ích chống SQL injection:

```java
namedJdbc.query(
        "SELECT order_id FROM app.orders WHERE customer_id = :id",
        Map.of("id", customerId),
        rowMapper);
```

Bind parameter không thể thay thế identifier. Với sort column, table name hoặc SQL fragment, dùng allowlist cố định. Không dùng `String.format` hoặc nối input người dùng vào `ORDER BY`.

## 19. Oracle pagination và giới hạn SQL

Oracle Database 12c trở lên hỗ trợ `OFFSET ... FETCH`:

```sql
SELECT order_id,
       order_date,
       total_amount
FROM app.orders
WHERE customer_id = :customerId
ORDER BY order_date DESC, order_id DESC
OFFSET :offset ROWS FETCH NEXT :pageSize ROWS ONLY
```

Có thể bind giá trị offset/page size, nhưng phải validate không âm và giới hạn tối đa. Cần có `ORDER BY` xác định để kết quả phân trang ổn định.

Với trang rất sâu, OFFSET có thể khiến database phải đi qua nhiều dòng rồi mới trả trang. Có thể dùng keyset pagination dựa trên khóa cuối trang trước:

```sql
SELECT order_id,
       order_date,
       total_amount
FROM app.orders
WHERE customer_id = :customerId
  AND (order_date, order_id) < (:lastOrderDate, :lastOrderId)
ORDER BY order_date DESC, order_id DESC
FETCH FIRST :pageSize ROWS ONLY
```

Row-value comparison cần kiểm tra semantics và kiểu dữ liệu Oracle trong phiên bản sử dụng; có thể viết điều kiện tương đương bằng `OR` rõ ràng. Keyset pagination cần index phù hợp và xử lý NULL/duplicate order key theo hợp đồng.

## 20. Kiểu dữ liệu Oracle và JDBC: bảng tham chiếu

| Oracle SQL type | JDBC type thường gặp | Java type thường dùng | Lưu ý |
|---|---|---|---|
| `NUMBER` | `NUMERIC` / `DECIMAL` | `BigDecimal` | Dùng cho precision chính xác |
| `NUMBER(p,0)` | `NUMERIC` | `Long`/`Integer` nếu miền phù hợp | Kiểm tra overflow và NULL |
| `FLOAT` | `FLOAT`/`NUMERIC` tùy mapping | `BigDecimal` hoặc `Double` theo yêu cầu | Oracle FLOAT là kiểu số có precision nhị phân theo định nghĩa Oracle |
| `BINARY_FLOAT` | `REAL` | `Float` | IEEE floating point |
| `BINARY_DOUBLE` | `DOUBLE` | `Double` | IEEE floating point |
| `VARCHAR2` | `VARCHAR` | `String` | Character set database |
| `CHAR` | `CHAR` | `String` | Có padding |
| `NVARCHAR2` | `NVARCHAR` | `String` | National character set |
| `NCHAR` | `NCHAR` | `String` | Fixed-width national character |
| `DATE` | `DATE`/`TIMESTAMP` theo driver | `Timestamp`/`LocalDateTime` | Oracle DATE có cả giờ đến giây |
| `TIMESTAMP` | `TIMESTAMP` | `LocalDateTime`/`Timestamp` | Có fractional seconds |
| `TIMESTAMP WITH TIME ZONE` | `TIMESTAMP_WITH_TIMEZONE` hoặc Oracle-specific mapping | `OffsetDateTime` | Kiểm tra driver/version |
| `TIMESTAMP WITH LOCAL TIME ZONE` | Mapping phụ thuộc driver/session | `Timestamp`/`LocalDateTime` | Hiển thị theo session time zone |
| `CLOB` | `CLOB` | `Clob`, `Reader`, `String` | Stream nếu lớn |
| `NCLOB` | `NCLOB` | `NClob`, `Reader`, `String` | National character data |
| `BLOB` | `BLOB` | `Blob`, `InputStream`, `byte[]` | Stream nếu lớn |
| `RAW` | `VARBINARY`/Oracle-specific | `byte[]` | Binary data |
| `LONG` | `LONGVARCHAR` | `String`/stream | Kiểu legacy; nên cân nhắc chuyển sang CLOB |
| `LONG RAW` | `LONGVARBINARY` | `byte[]`/stream | Kiểu legacy; cân nhắc BLOB |
| `ROWID` | `ROWID` | `RowId`/Oracle-specific | Không dùng làm business key |
| SQL `BOOLEAN` (23ai/23c+) | Driver/version dependent | `Boolean` | Không áp dụng cho database cũ không có SQL BOOLEAN |

Mapping cụ thể có thể thay đổi theo Oracle JDBC driver version, `ResultSetMetaData`, kiểu cột và cách gọi API. Bảng này là hướng dẫn chọn kiểu, không thay thế integration test trên driver production.

## 21. Ví dụ repository tổng hợp

Một repository dùng named parameters, `BigDecimal`, `LocalDateTime` và `RowMapper`:

```java
@Repository
public class OrderSearchRepository {

    private static final RowMapper<OrderSummary> ROW_MAPPER = (rs, rowNum) ->
            new OrderSummary(
                    rs.getLong("ORDER_ID"),
                    rs.getLong("CUSTOMER_ID"),
                    rs.getBigDecimal("TOTAL_AMOUNT"),
                    rs.getString("ORDER_STATUS")
            );

    private final NamedParameterJdbcTemplate jdbc;

    public OrderSearchRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<OrderSummary> search(
            Long customerId,
            String status,
            LocalDateTime from,
            LocalDateTime to) {

        String sql = """
            SELECT order_id,
                   customer_id,
                   total_amount,
                   order_status
            FROM app.orders
            WHERE (:customerId IS NULL OR customer_id = :customerId)
              AND (:status IS NULL OR order_status = :status)
              AND order_date >= :fromTime
              AND order_date < :toTime
            ORDER BY order_date DESC, order_id DESC
            """;

        MapSqlParameterSource params = new MapSqlParameterSource()
                .addValue("customerId", customerId, Types.NUMERIC)
                .addValue("status", status, Types.VARCHAR)
                .addValue("fromTime", Timestamp.valueOf(from), Types.TIMESTAMP)
                .addValue("toTime", Timestamp.valueOf(to), Types.TIMESTAMP);

        return jdbc.query(sql, params, ROW_MAPPER);
    }
}
```

Mẫu `(:param IS NULL OR column = :param)` tiện cho optional filter, nhưng không phải lúc nào cũng tạo execution plan tối ưu, đặc biệt khi bind peeking và selectivity thay đổi mạnh. Với truy vấn quan trọng, có thể xây dựng các nhánh SQL theo filter thực sự có mặt (chỉ ghép các fragment cố định từ code) để optimizer nhìn thấy predicate rõ hơn. Không ghép giá trị input vào SQL.

## 22. Kiểm thử repository với Oracle

### 22.1. Unit test và integration test khác nhau

Unit test có thể kiểm tra logic service hoặc mapper bằng mock, nhưng mock JDBC không chứng minh Oracle chuyển đổi kiểu đúng. Với các kiểu như `DATE`, `TIMESTAMP WITH TIME ZONE`, `NUMBER`, `CLOB`, `RAW`, cần integration test với Oracle database/driver tương thích.

### 22.2. Test kiểu dữ liệu quan trọng

Nên có test cho:

- `NUMBER` lớn gần precision tối đa và giá trị scale.
- Giá trị tiền có phần thập phân và rounding rule.
- SQL NULL trong cột nullable.
- Oracle `DATE` có giờ/phút/giây khác 00:00:00.
- `TIMESTAMP` có fractional seconds.
- `TIMESTAMP WITH TIME ZONE` qua các offset khác nhau.
- `CHAR` có trailing spaces.
- `NVARCHAR2` có ký tự tiếng Việt và ký tự ngoài BMP nếu cần.
- Empty string so với NULL.
- CLOB/BLOB lớn và streaming lifecycle.
- Collection parameter rỗng và danh sách lớn.

### 22.3. Kiểm tra transaction rollback

Test một service method có nhiều DML và xác nhận khi bước sau thất bại, bước trước được rollback theo policy. Test cần chạy qua Spring transaction manager thực tế, không chỉ gọi repository trực tiếp ngoài transaction.

### 22.4. Kiểm tra performance

Với truy vấn lớn, đo:

- Số round-trip và fetch size.
- Số dòng và row width.
- Heap usage khi map kết quả.
- Thời gian giữ connection.
- Execution plan và logical/physical reads.
- Batch size, redo/undo và transaction duration.

Không dùng H2 làm bằng chứng cho tương thích Oracle SQL. H2 có thể hữu ích cho test logic đơn giản, nhưng khác biệt về kiểu dữ liệu, function, sequence, locking và SQL semantics khiến test Oracle-specific phải dùng Oracle.

## 23. Các lỗi thường gặp khi dùng JdbcTemplate với Oracle

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `ORA-01722: invalid number` | Chuỗi không chuyển được sang NUMBER hoặc implicit conversion | Bind `BigDecimal`/numeric type, kiểm tra dữ liệu và tránh conversion ngầm |
| `ORA-01861: literal does not match format string` | Chuỗi ngày không khớp format mask/NLS | Bind kiểu ngày giờ hoặc dùng format mask rõ ràng |
| `ORA-00932: inconsistent datatypes` | JDBC type không phù hợp với cột/biểu thức | Khai báo type rõ, kiểm tra Oracle type và driver mapping |
| `ORA-01008: not all variables bound` | Thiếu bind value hoặc tên parameter sai | Đối chiếu placeholder với parameter source |
| `ORA-01036: illegal variable name/number` | Bind sai tên/vị trí hoặc cố bind identifier | Chỉ bind giá trị, kiểm tra named parameter |
| `ORA-00001: unique constraint violated` | Dữ liệu trùng khóa | Kiểm tra key, idempotency và xử lý duplicate theo nghiệp vụ |
| `ORA-02291: integrity constraint violated - parent key not found` | Foreign key tham chiếu parent không tồn tại | Nạp parent trước hoặc kiểm tra khóa ngoại |
| `EmptyResultDataAccessException` | `queryForObject` không có dòng | Dùng Optional pattern hoặc query list nếu kết quả có thể rỗng |
| Giá trị Oracle DATE mất giờ | Mapping qua `java.sql.Date`/`LocalDate` | Dùng `Timestamp`/`LocalDateTime` khi cần giữ time |
| Tiền bị sai số | Dùng `double` thay vì `BigDecimal` | Dùng `BigDecimal` và rounding rule rõ ràng |
| NULL thành 0 | Dùng primitive getter mà không gọi `wasNull()` | Dùng wrapper/object mapping hoặc kiểm tra `wasNull()` |
| Lỗi với IN list rỗng | SQL thành `IN ()` | Xử lý list rỗng trước khi gọi query |
| Lỗi khi list quá lớn | Quá nhiều placeholder/expression | Chunk, staging table hoặc SQL collection phù hợp |
| Out of memory khi đọc LOB | Đọc toàn bộ CLOB/BLOB vào heap | Stream và giới hạn kích thước |
| Connection pool cạn | Giữ ResultSet/LOB stream lâu hoặc query chậm | Đóng resource đúng lúc, timeout và tối ưu SQL |

## 24. Quy trình xây dựng lớp JDBC ổn định

Khi thêm một repository Spring JDBC cho Oracle, có thể đi theo trình tự:

1. **Xác định SQL contract:** bảng, cột, predicate, join, ordering và cardinality mong muốn.
2. **Chọn template:** `JdbcTemplate` cho placeholder vị trí; `NamedParameterJdbcTemplate` cho SQL có nhiều tham số hoặc collection.
3. **Chọn kiểu Java:** `BigDecimal` cho số chính xác, `LocalDateTime` cho Oracle DATE/TIMESTAMP có giờ, `OffsetDateTime` cho timestamp có timezone khi driver hỗ trợ.
4. **Bind rõ ràng:** dùng `MapSqlParameterSource`/`SqlParameterValue` với JDBC type cho NULL và kiểu đặc thù.
5. **Mapping rõ ràng:** dùng `RowMapper` cho DTO; tránh N+1 query và mapping ngầm không kiểm soát.
6. **Xử lý LOB:** stream dữ liệu lớn và giữ connection/resource đúng vòng đời.
7. **Xác định transaction:** đặt `@Transactional` ở service boundary, không commit thủ công trong repository.
8. **Kiểm soát batch:** chọn batch size và transaction chunk theo workload.
9. **Bảo vệ SQL:** bind giá trị, allowlist identifier và không nối input tùy ý.
10. **Kiểm thử trên Oracle:** xác nhận kiểu dữ liệu, NULL, timezone, precision, transaction và execution plan.

## 25. Checklist trước khi đưa repository vào production

| Hạng mục | Câu hỏi cần xác nhận |
|---|---|
| Driver | Oracle JDBC driver có tương thích JDK, database và Spring Boot version không? |
| DataSource | URL dùng service name phù hợp; pool size nằm trong capacity database? |
| SQL | Tất cả giá trị bên ngoài đã được bind chưa? Identifier động có allowlist không? |
| Named parameter | Tên parameter khớp và collection rỗng/collection lớn đã được xử lý chưa? |
| NUMBER | Tiền và số precision cao có dùng `BigDecimal` không? |
| DATE | Có giữ phần thời gian của Oracle DATE khi nghiệp vụ cần không? |
| TIME ZONE | Session time zone và Java time type có đúng semantics không? |
| Character | CHAR padding, Unicode và empty string/NULL đã được hiểu rõ chưa? |
| LOB | Có stream dữ liệu lớn và quản lý connection lifetime không? |
| NULL | JDBC type được khai báo rõ khi bind null; primitive getter có kiểm tra `wasNull()`? |
| Transaction | Repository dùng cùng DataSource/transaction manager; rollback policy đã rõ? |
| Batch | Batch size, transaction duration, redo/undo và retry đã được kiểm soát? |
| Error handling | Exception được phân loại; lỗi không bị nuốt? |
| Performance | Fetch size, execution plan, round-trip và heap usage đã được đo? |
| Integration test | Các kiểu Oracle-specific đã được test với Oracle JDBC thật? |

`JdbcTemplate` và `NamedParameterJdbcTemplate` giúp viết lớp truy cập Oracle ngắn gọn mà vẫn giữ quyền kiểm soát SQL. Phần quan trọng nhất là bind giá trị bằng kiểu phù hợp, ánh xạ kết quả có chủ đích và hiểu semantics riêng của Oracle: `DATE` có cả thời gian, `NUMBER` cần precision đúng, `CHAR` có padding, chuỗi rỗng được xử lý như NULL, LOB cần quản lý stream và timestamp có timezone phụ thuộc driver/session. Khi kết hợp các nguyên tắc này với transaction boundary, batch size, timeout, fetch size và integration test trên Oracle, lớp JDBC sẽ ổn định hơn và dễ vận hành trong Spring Boot.
