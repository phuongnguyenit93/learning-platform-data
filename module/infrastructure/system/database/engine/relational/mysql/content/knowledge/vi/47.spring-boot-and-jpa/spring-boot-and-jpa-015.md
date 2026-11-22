# Spring Boot và JPA

## Stored procedure, nhiều result set và OUT parameter

Stored procedure của MySQL có thể trả về nhiều tập kết quả (result set), số hàng bị ảnh hưởng và các tham số OUT/INOUT trong cùng một lần gọi. Một procedure báo cáo có thể trả danh sách đơn hàng ở result set thứ nhất, thống kê theo trạng thái ở result set thứ hai, rồi trả tổng số đơn và tổng tiền qua OUT parameter. Ứng dụng Spring Boot phải đọc hết chuỗi kết quả theo đúng thứ tự trước khi lấy output parameter và trả connection về pool.

Trong module **DATABASE_MYSQL**, bạn học cách làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction và kiểm soát đồng thời. Bạn cũng thực hành đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Bài này kết nối stored procedure với tầng Java: cách khai báo procedure, lựa chọn Spring Data JPA, `StoredProcedureQuery` hoặc JDBC qua `JdbcTemplate`, map nhiều result set, đọc OUT parameter và giữ transaction/persistence context nhất quán.

Ví dụ sử dụng MySQL 8.x, Spring Boot 3.x, Jakarta Persistence và MySQL Connector/J. Với Spring Boot 2.x, package JPA thường dùng `javax.persistence` thay cho `jakarta.persistence`; kiểm tra phiên bản dependency trước khi sao chép import.

### 1. Hiểu hợp đồng của stored procedure

Một lời gọi procedure có thể tạo ra nhiều loại kết quả:

- **Result set:** hàng/cột được trả về từ một câu `SELECT` trong procedure.
- **Update count:** số hàng được thay đổi bởi một câu DML.
- **OUT parameter:** giá trị procedure gán để trả lại caller.
- **INOUT parameter:** giá trị đầu vào được procedure đọc và có thể thay đổi.
- **Return status:** MySQL procedure không có `RETURN` scalar như stored function; nếu cần giá trị tổng hợp, dùng OUT parameter hoặc result set.

Ví dụ, procedure báo cáo khách hàng có hợp đồng:

1. `IN p_customer_id`: xác định khách hàng cần báo cáo.
2. Result set thứ nhất: danh sách đơn hàng.
3. Result set thứ hai: tổng hợp số đơn theo trạng thái.
4. `OUT p_order_count`: tổng số đơn.
5. `OUT p_total_amount`: tổng tiền.

Hợp đồng phải quy định thứ tự result set, tên/case cột, kiểu dữ liệu, nullability và ý nghĩa OUT parameter. Đổi thứ tự một câu SELECT trong procedure có thể phá vỡ mapper của ứng dụng dù chữ ký procedure không đổi.

### 2. Tạo procedure MySQL có nhiều result set và OUT parameter

Ví dụ dưới đây giả định bảng `orders` có các cột `order_id`, `customer_id`, `created_at`, `status` và `total_amount`:

~~~sql
DELIMITER //

CREATE PROCEDURE customer_order_report(
    IN p_customer_id BIGINT,
    OUT p_order_count INT,
    OUT p_total_amount DECIMAL(15, 2)
)
BEGIN
    -- Result set 1: chi tiết đơn hàng.
    SELECT
        order_id,
        created_at,
        status,
        total_amount
    FROM orders
    WHERE customer_id = p_customer_id
    ORDER BY created_at DESC, order_id DESC;

    -- Result set 2: tổng hợp theo trạng thái.
    SELECT
        status,
        COUNT(*) AS order_count,
        COALESCE(SUM(total_amount), 0) AS amount_by_status
    FROM orders
    WHERE customer_id = p_customer_id
    GROUP BY status
    ORDER BY status;

    -- OUT parameters: một giá trị cho toàn bộ báo cáo.
    SELECT
        COUNT(*),
        COALESCE(SUM(total_amount), 0)
    INTO p_order_count, p_total_amount
    FROM orders
    WHERE customer_id = p_customer_id;
END//

DELIMITER ;
~~~

Procedure trên tạo đúng hai result set. Câu `SELECT ... INTO` cuối gán OUT parameter và không tạo result set thứ ba. Nếu không có đơn hàng, `COUNT(*)` trả 0 và `COALESCE(SUM(...), 0)` bảo đảm tổng tiền là 0 thay vì NULL.

`DELIMITER` là lệnh của client dòng lệnh để đổi ký tự kết thúc câu lệnh khi nhập procedure body; nó không phải câu SQL gửi đến MySQL Server. Khi gọi qua JDBC, migration runner hoặc công cụ triển khai, gửi câu `CREATE PROCEDURE ... BEGIN ... END` theo cú pháp mà công cụ đó hỗ trợ, không gửi dòng `DELIMITER` như một statement SQL.

Gọi từ SQL client:

~~~sql
SET @order_count = NULL;
SET @total_amount = NULL;

CALL customer_order_report(42, @order_count, @total_amount);

SELECT
    @order_count AS order_count,
    @total_amount AS total_amount;
~~~

Client SQL hiển thị hai result set từ `CALL`, sau đó câu `SELECT` riêng đọc session variables. Qua JDBC `CallableStatement`, driver cung cấp OUT parameter qua `getInt()`/`getBigDecimal()` sau khi caller đã xử lý các kết quả của procedure.

### 3. Chọn API phù hợp trong Spring

Không phải API gọi procedure nào cũng phù hợp với nhiều result set:

| Cách gọi | Phù hợp | Giới hạn cần lưu ý |
|---|---|---|
| Spring Data JPA `@Procedure` | Procedure đơn giản, trả một OUT/scalar hoặc một tập OUT parameter | Không phải API thuận tiện để duyệt tùy ý nhiều result set theo thứ tự |
| JPA `StoredProcedureQuery` | Muốn giữ cách gọi trong EntityManager, dùng mapping JPA và quản lý transaction JPA | Nhiều result set phụ thuộc mapping/provider; kiểm tra với Hibernate và phiên bản đang dùng |
| Spring JDBC `JdbcTemplate` / `SimpleJdbcCall` | Procedure có nhiều result set, update count và OUT parameter cần kiểm soát rõ | Mapping được khai báo tường minh; làm việc ở tầng JDBC thay vì entity lifecycle |
| JDBC `CallableStatement` trực tiếp | Cần kiểm soát protocol và vòng lặp kết quả chi tiết | Phải quản lý tài nguyên và transaction đúng; nên dùng qua `JdbcTemplate` hoặc Spring-managed connection |

Quy tắc thực tế:

- Procedure chỉ trả một OUT parameter: `@Procedure` thường là lựa chọn gọn.
- Procedure trả nhiều result set cần map tuần tự: dùng `JdbcTemplate` với `CallableStatementCallback` để kiểm soát chính xác.
- Procedure cần JPA result mapping: dùng `StoredProcedureQuery`, nhưng phải test trên provider thực tế.

### 4. Gọi procedure đơn giản bằng Spring Data JPA `@Procedure`

Với procedure chỉ trả một OUT parameter, khai báo repository method:

~~~sql
DELIMITER //

CREATE PROCEDURE count_customer_orders(
    IN p_customer_id BIGINT,
    OUT p_order_count INT
)
BEGIN
    SELECT COUNT(*)
    INTO p_order_count
    FROM orders
    WHERE customer_id = p_customer_id;
END//

DELIMITER ;
~~~

~~~java
public interface OrderProcedureRepository
        extends Repository<Order, Long> {

    @Procedure(procedureName = "count_customer_orders")
    Integer countCustomerOrders(
            @Param("p_customer_id") Long customerId);
}
~~~

Gọi từ service:

~~~java
@Service
public class OrderReportService {

    private final OrderProcedureRepository procedures;

    public OrderReportService(OrderProcedureRepository procedures) {
        this.procedures = procedures;
    }

    public int countOrders(long customerId) {
        Integer count = procedures.countCustomerOrders(customerId);
        return count == null ? 0 : count;
    }
}
~~~

Tên procedure phải khớp với database. Tên parameter phải khớp với cách Spring Data JPA/provider bind parameter; nếu môi trường có khác biệt, kiểm tra SQL log và metadata của procedure. Không nối tên procedure hoặc tên schema từ input người dùng.

Khi procedure có nhiều OUT parameter, Spring Data JPA có thể trả một `Map<String, Object>` theo cách khai báo `@Procedure`/`@NamedStoredProcedureQuery` phù hợp. Tuy nhiên, nếu procedure đồng thời trả nhiều result set, hãy dùng `StoredProcedureQuery` hoặc JDBC để quản lý luồng kết quả tường minh.

### 5. Gọi procedure bằng JPA `StoredProcedureQuery`

JPA cung cấp `StoredProcedureQuery` qua `EntityManager`. API này hỗ trợ đăng ký tham số IN, OUT, INOUT, thực thi procedure và duyệt các kết quả tiếp theo.

Ví dụ dùng result set dạng `Object[]` để không phụ thuộc entity mapping:

Trong ví dụ này, `created_at` được giả định là `DATETIME` và được ánh xạ thành `LocalDateTime`. Nếu cột là `TIMESTAMP`, hãy dùng `Instant` hoặc một quy ước timezone rõ ràng; đừng chuyển đổi ngầm sang giờ JVM.

~~~java
@Service
public class JpaOrderReportService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional(readOnly = true)
    public OrderReport loadReport(long customerId) {
        StoredProcedureQuery query =
                entityManager.createStoredProcedureQuery(
                        "customer_order_report");

        query.registerStoredProcedureParameter(
                "p_customer_id", Long.class, ParameterMode.IN);
        query.registerStoredProcedureParameter(
                "p_order_count", Integer.class, ParameterMode.OUT);
        query.registerStoredProcedureParameter(
                "p_total_amount", BigDecimal.class, ParameterMode.OUT);

        query.setParameter("p_customer_id", customerId);

        List<OrderRow> orders = new ArrayList<>();
        List<StatusSummary> summaries = new ArrayList<>();
        int resultSetIndex = 0;
        boolean hasResultSet = query.execute();

        while (true) {
            if (hasResultSet) {
                List<?> rows = query.getResultList();

                if (resultSetIndex == 0) {
                    for (Object row : rows) {
                        Object[] columns = (Object[]) row;
                        orders.add(new OrderRow(
                                ((Number) columns[0]).longValue(),
                                toLocalDateTime(columns[1]),
                                (String) columns[2],
                                (BigDecimal) columns[3]));
                    }
                } else if (resultSetIndex == 1) {
                    for (Object row : rows) {
                        Object[] columns = (Object[]) row;
                        summaries.add(new StatusSummary(
                                (String) columns[0],
                                ((Number) columns[1]).longValue(),
                                (BigDecimal) columns[2]));
                    }
                } else {
                    throw new IllegalStateException(
                            "Unexpected result set index: " + resultSetIndex);
                }

                resultSetIndex++;
            } else if (query.getUpdateCount() == -1) {
                break;
            }

            hasResultSet = query.hasMoreResults();
        }

        if (resultSetIndex != 2) {
            throw new IllegalStateException(
                    "Expected 2 result sets but received " + resultSetIndex);
        }

        // Đọc OUT parameter sau khi đã tiêu thụ mọi result set/update count.
        Integer orderCount = (Integer)
                query.getOutputParameterValue("p_order_count");
        BigDecimal totalAmount = (BigDecimal)
                query.getOutputParameterValue("p_total_amount");

        return new OrderReport(
                orders,
                summaries,
                orderCount == null ? 0 : orderCount,
                totalAmount == null ? BigDecimal.ZERO : totalAmount);
    }

    private LocalDateTime toLocalDateTime(Object value) {
        if (value instanceof LocalDateTime dateTime) {
            return dateTime;
        }
        throw new IllegalArgumentException(
                "Unexpected created_at type: " + value);
    }
}
~~~

Đoạn code minh họa cách duyệt kết quả JPA. Kiểu Java thực tế của từng cột phụ thuộc JDBC driver, dialect và provider; kiểm tra kiểu trả về trong integration test. Ví dụ dùng `Number.longValue()` cho các kiểu số nguyên để tránh giả định provider luôn trả `Long`.

Các record DTO:

~~~java
public record OrderRow(
        long orderId,
        LocalDateTime createdAt,
        String status,
        BigDecimal totalAmount) {}

public record StatusSummary(
        String status,
        long orderCount,
        BigDecimal amountByStatus) {}

public record OrderReport(
        List<OrderRow> orders,
        List<StatusSummary> summaries,
        int orderCount,
        BigDecimal totalAmount) {}
~~~

`createStoredProcedureQuery("customer_order_report")` không chỉ rõ result mapping nên ví dụ xử lý từng hàng dưới dạng `Object[]`. Nếu muốn map vào entity/DTO bằng `@SqlResultSetMapping`, khai báo mapping phù hợp với thứ tự result set và kiểm tra hành vi của Hibernate version đang triển khai. JPA provider có thể khác nhau về cách xử lý procedure trả nhiều kết quả; nếu cần điều khiển protocol ổn định, JDBC thường dễ kiểm soát hơn.

### 6. Duyệt nhiều result set bằng JDBC qua `JdbcTemplate`

Đối với procedure trả nhiều result set và OUT parameter, `CallableStatement` cung cấp vòng lặp rõ ràng:

1. Gọi `execute()`.
2. Nếu kết quả hiện tại là ResultSet, đọc và đóng nó.
3. Nếu không phải ResultSet, kiểm tra update count.
4. Gọi `getMoreResults()` để chuyển sang kết quả kế tiếp.
5. Dừng khi không còn ResultSet và `getUpdateCount()` trả `-1`.
6. Đọc OUT parameter sau khi đã tiêu thụ toàn bộ kết quả.

Đây là mẫu Spring JDBC hoàn chỉnh:

~~~java
@Service
public class JdbcOrderReportService {

    private final JdbcTemplate jdbcTemplate;

    public JdbcOrderReportService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional(readOnly = true)
    public OrderReport loadReport(long customerId) {
        return jdbcTemplate.execute(
                connection -> {
                    CallableStatement statement =
                            connection.prepareCall(
                                    "{call customer_order_report(?, ?, ?)}");
                    statement.setLong(1, customerId);
                    statement.registerOutParameter(2, Types.INTEGER);
                    statement.registerOutParameter(3, Types.DECIMAL);
                    return statement;
                },
                (CallableStatementCallback<OrderReport>) statement -> {
                    List<OrderRow> orders = new ArrayList<>();
                    List<StatusSummary> summaries = new ArrayList<>();
                    int resultSetIndex = 0;
                    boolean hasResultSet = statement.execute();

                    while (true) {
                        if (hasResultSet) {
                            try (ResultSet rs = statement.getResultSet()) {
                                if (resultSetIndex == 0) {
                                    while (rs.next()) {
                                        orders.add(new OrderRow(
                                                rs.getLong("order_id"),
                                                rs.getObject(
                                                        "created_at",
                                                        LocalDateTime.class),
                                                rs.getString("status"),
                                                rs.getBigDecimal("total_amount")));
                                    }
                                } else if (resultSetIndex == 1) {
                                    while (rs.next()) {
                                        summaries.add(new StatusSummary(
                                                rs.getString("status"),
                                                rs.getLong("order_count"),
                                                rs.getBigDecimal("amount_by_status")));
                                    }
                                } else {
                                    throw new SQLException(
                                            "Unexpected result set index: "
                                                    + resultSetIndex);
                                }
                            }
                            resultSetIndex++;
                        } else {
                            int updateCount = statement.getUpdateCount();
                            if (updateCount == -1) {
                                break;
                            }
                        }

                        hasResultSet = statement.getMoreResults(
                                Statement.CLOSE_CURRENT_RESULT);
                    }

                    if (resultSetIndex != 2) {
                        throw new SQLException(
                                "Expected 2 result sets but received "
                                        + resultSetIndex);
                    }

                    // OUT values chỉ được lấy sau khi đã đọc hết kết quả CALL.
                    int orderCount = statement.getInt(2);
                    if (statement.wasNull()) {
                        orderCount = 0;
                    }
                    BigDecimal totalAmount = statement.getBigDecimal(3);
                    if (totalAmount == null) {
                        totalAmount = BigDecimal.ZERO;
                    }

                    return new OrderReport(
                            orders, summaries, orderCount, totalAmount);
                });
    }
}
~~~

`JdbcTemplate.execute(CallableStatementCreator, CallableStatementCallback)` quản lý việc lấy/trả connection theo Spring JDBC và đóng statement sau callback. ResultSet được đóng ngay trong vòng lặp. Nếu dùng `CallableStatement` trực tiếp ngoài `JdbcTemplate`, phải tự đóng `ResultSet`, `CallableStatement` và connection đúng thứ tự.

Ví dụ trên giả định result set thứ nhất và thứ hai luôn được trả theo hợp đồng. Nếu procedure thay đổi thứ tự hoặc thêm SELECT mới, kiểm tra `resultSetIndex` sẽ phát hiện thay đổi thay vì âm thầm map nhầm dữ liệu.

### 7. Vì sao phải đọc hết kết quả trước khi lấy OUT parameter?

Một lần gọi procedure có thể trả về chuỗi kết quả trên cùng JDBC protocol. Khi còn result set chưa đọc, driver vẫn đang xử lý response của `CALL`. Việc lấy OUT parameter quá sớm có thể khiến driver phải tự tiêu thụ kết quả còn lại, gây hành vi khác nhau giữa driver/provider hoặc làm mất cơ hội xử lý update count.

Quy tắc an toàn:

- Đọc hết từng ResultSet theo đúng thứ tự.
- Đóng ResultSet trước khi gọi `getMoreResults()`.
- Xử lý update count nếu procedure có DML.
- Dừng khi `getUpdateCount()` là `-1` và không còn result set.
- Sau đó mới gọi `getInt()`, `getBigDecimal()` hoặc `getObject()` cho OUT parameter.

Đừng chỉ gọi `executeQuery()` cho procedure có nhiều result set. `executeQuery()` phù hợp với statement trả một ResultSet; với procedure có kết quả hỗn hợp, dùng `execute()` và vòng lặp `getMoreResults()`.

### 8. Xử lý IN, OUT và INOUT

JDBC dùng `registerOutParameter()` để đăng ký tham số đầu ra:

~~~java
try (Connection connection = dataSource.getConnection();
     CallableStatement statement =
             connection.prepareCall("{call adjust_credit(?, ?, ?)}")) {

    statement.setLong(1, customerId);                 // IN
    statement.registerOutParameter(2, Types.DECIMAL); // OUT
    statement.setBigDecimal(3, adjustment);           // INOUT input
    statement.registerOutParameter(3, Types.DECIMAL); // INOUT output

    statement.execute();

    BigDecimal newCredit = statement.getBigDecimal(2);
    BigDecimal adjustedValue = statement.getBigDecimal(3);
}
~~~

Trong MySQL, khai báo procedure tương ứng:

~~~sql
CREATE PROCEDURE adjust_credit(
    IN p_customer_id BIGINT,
    OUT p_new_credit DECIMAL(15, 2),
    INOUT p_adjustment DECIMAL(15, 2)
)
BEGIN
    UPDATE customers
    SET credit_limit = credit_limit + p_adjustment
    WHERE customer_id = p_customer_id;

    SELECT credit_limit
    INTO p_new_credit
    FROM customers
    WHERE customer_id = p_customer_id;

    SET p_adjustment = p_new_credit;
END;
~~~

Ví dụ chỉ minh họa mode tham số. Trong production, kiểm tra hàng khách hàng có tồn tại, xử lý update không có hàng, khóa dòng khi cần và xác định ý nghĩa của INOUT. Không giả định procedure luôn trả một giá trị hợp lệ nếu câu SELECT INTO không tìm thấy dòng.

### 9. Dùng `SimpleJdbcCall` khi muốn khai báo mapping

`SimpleJdbcCall` là abstraction của Spring JDBC cho stored procedure. Nó có thể khai báo `SqlOutParameter` và `returningResultSet()` để ánh xạ các result set theo tên:

~~~java
@Repository
public class OrderReportDao {

    private final SimpleJdbcCall reportCall;

    public OrderReportDao(JdbcTemplate jdbcTemplate) {
        this.reportCall = new SimpleJdbcCall(jdbcTemplate)
                .withProcedureName("customer_order_report")
                .withoutProcedureColumnMetaDataAccess()
                .declareParameters(
                        new SqlParameter("p_customer_id", Types.BIGINT),
                        new SqlOutParameter("p_order_count", Types.INTEGER),
                        new SqlOutParameter("p_total_amount", Types.DECIMAL))
                .returningResultSet(
                        "orders",
                        (rs, rowNum) -> new OrderRow(
                                rs.getLong("order_id"),
                                rs.getObject("created_at", LocalDateTime.class),
                                rs.getString("status"),
                                rs.getBigDecimal("total_amount")))
                .returningResultSet(
                        "summaries",
                        (rs, rowNum) -> new StatusSummary(
                                rs.getString("status"),
                                rs.getLong("order_count"),
                                rs.getBigDecimal("amount_by_status")));
    }

    @SuppressWarnings("unchecked")
    public OrderReport load(long customerId) {
        Map<String, Object> result =
                reportCall.execute(Map.of("p_customer_id", customerId));

        List<OrderRow> orders =
                (List<OrderRow>) result.get("orders");
        List<StatusSummary> summaries =
                (List<StatusSummary>) result.get("summaries");
        Number count = (Number) result.get("p_order_count");
        BigDecimal total = (BigDecimal) result.get("p_total_amount");

        return new OrderReport(
                orders == null ? List.of() : orders,
                summaries == null ? List.of() : summaries,
                count == null ? 0 : count.intValue(),
                total == null ? BigDecimal.ZERO : total);
    }
}
~~~

Khi tắt metadata lookup bằng `withoutProcedureColumnMetaDataAccess()`, phải khai báo chính xác tất cả tham số theo tên, thứ tự và SQL type. `returningResultSet()` cần được khai báo theo thứ tự result set mà procedure trả về. Kiểm tra map key và kiểu giá trị với phiên bản Spring JDBC thực tế; nếu cần xử lý update count hoặc luồng kết quả phức tạp, callback `CallableStatement` ở phần trước dễ kiểm soát hơn.

### 10. Tích hợp transaction với JPA

Nếu procedure chỉ đọc, có thể dùng `@Transactional(readOnly = true)` như các ví dụ. Nếu procedure ghi dữ liệu, dùng transaction ghi thông thường:

~~~java
@Transactional
public void closeOrder(long orderId) {
    // Gọi procedure có cập nhật trạng thái đơn hàng.
}
~~~

`JdbcTemplate` có thể tham gia transaction Spring đang quản lý nếu nó dùng cùng `DataSource` với `JpaTransactionManager` và cấu hình transaction phù hợp. Không tạo một DataSource khác cho JdbcTemplate rồi kỳ vọng transaction JPA tự động bao trùm connection đó.

Một số nguyên tắc:

- Không gọi `COMMIT` hoặc `ROLLBACK` thủ công trong procedure nếu transaction được quản lý bởi Spring, trừ khi thiết kế transaction đã chủ đích cho việc đó.
- MySQL DDL có thể gây implicit commit; tránh trộn DDL với transaction nghiệp vụ.
- Không đánh dấu transaction read-only nếu procedure thực hiện DML.
- Giữ procedure ngắn và giới hạn lock; không giữ transaction trong khi ứng dụng gọi HTTP hoặc chờ bên ngoài.
- Khi có deadlock, retry toàn bộ đơn vị transaction ở tầng service với giới hạn và idempotency phù hợp.

`@Transactional(readOnly = true)` là metadata/hint cho transaction manager và provider, không phải cơ chế cấp quyền bảo mật thay thế GRANT trên MySQL.

### 11. Persistence context và dữ liệu do procedure thay đổi

JPA persistence context có thể đang giữ entity đã được load trước khi stored procedure cập nhật cùng hàng. Nếu procedure chạy qua JDBC hoặc native procedure call, Hibernate có thể không biết những entity trong bộ nhớ đã bị thay đổi.

Ví dụ:

1. Entity `Order` được load vào persistence context.
2. Stored procedure cập nhật `orders.status` thành `SHIPPED`.
3. Code đọc lại cùng entity từ EntityManager.
4. Hibernate có thể trả entity đang được quản lý với trạng thái cũ vì identity map không tự đọc lại hàng.

Biện pháp:

- Gọi `entityManager.flush()` trước procedure nếu procedure phải nhìn thấy các thay đổi JPA đang chờ ghi.
- Gọi `entityManager.refresh(entity)` cho entity cụ thể cần đồng bộ lại.
- Gọi `entityManager.clear()` sau procedure nếu nhiều entity bị ảnh hưởng và có thể bỏ toàn bộ persistence context.
- Nếu dùng second-level cache hoặc query cache, evict vùng/entity liên quan theo API của provider; `clear()` chỉ xóa first-level persistence context.

Không gọi `clear()` tùy tiện khi còn entity chưa flush vì các thay đổi chưa ghi có thể bị mất khỏi persistence context. Thứ tự flush, gọi procedure và refresh/clear phải được xác định theo transaction.

### 12. Mapping result set vào DTO hoặc entity

Có ba cách mapping phổ biến:

**JDBC RowMapper:** phù hợp cho DTO, dễ kiểm soát kiểu và tên cột.

~~~java
RowMapper<OrderRow> orderMapper = (rs, rowNum) ->
        new OrderRow(
                rs.getLong("order_id"),
                rs.getObject("created_at", LocalDateTime.class),
                rs.getString("status"),
                rs.getBigDecimal("total_amount"));
~~~

**JPA `@SqlResultSetMapping`:** phù hợp khi muốn dùng mapping được khai báo trong persistence metadata. Khai báo constructor result cho DTO hoặc entity result cho entity; đảm bảo alias cột khớp mapping.

**`Object[]`:** hữu ích cho thử nghiệm nhanh nhưng dễ lỗi khi procedure đổi thứ tự cột. Nếu dùng, ghi rõ index và kiểu của từng cột, kiểm thử hợp đồng và chuyển ngay sang DTO.

Không map một result set vào entity JPA chỉ vì các cột trùng tên. Entity có thể cần primary key, discriminator, version column hoặc quan hệ mà result set không trả. Với dữ liệu báo cáo chỉ đọc, DTO thường đơn giản và an toàn hơn.

### 13. Kiểu dữ liệu và NULL trong OUT parameter

OUT parameter có thể là NULL. Với JDBC primitive getter như `getInt()`, giá trị NULL được biểu diễn thành 0; phải gọi `wasNull()` ngay sau getter để phân biệt NULL với số 0 thật:

~~~java
int rawCount = statement.getInt("p_order_count");
Integer count = statement.wasNull() ? null : rawCount;
~~~

Với `getBigDecimal()` và `getString()`, NULL thường được trả về dưới dạng `null`. Không tự thay NULL thành 0 nếu NULL mang ý nghĩa nghiệp vụ khác.

Kiểu Java và SQL cần tương thích:

| MySQL | JDBC type | Java type thường dùng |
|---|---|---|
| BIGINT | Types.BIGINT | Long |
| INT | Types.INTEGER | Integer |
| DECIMAL(p,s) | Types.DECIMAL | BigDecimal |
| VARCHAR | Types.VARCHAR | String |
| DATE | Types.DATE | LocalDate hoặc java.sql.Date |
| DATETIME | Types.TIMESTAMP/JDBC mapping theo driver | LocalDateTime hoặc Timestamp |
| TIMESTAMP | Types.TIMESTAMP | Instant/Timestamp theo timezone policy |

Với DECIMAL, luôn dùng `BigDecimal`, không chuyển qua `double` vì có thể mất độ chính xác tiền tệ.

### 14. Xử lý lỗi và đóng tài nguyên

Các lỗi phổ biến:

- Procedure name sai hoặc procedure chưa được deploy.
- Thiếu quyền EXECUTE.
- Tên hoặc thứ tự parameter không khớp.
- SQL type OUT parameter không tương thích.
- Result set thứ hai bị map nhầm thành result set thứ nhất.
- Không đọc hết kết quả khiến connection không thể dùng cho statement kế tiếp.
- OUT parameter được đọc trước khi driver hoàn tất chuỗi kết quả.
- Procedure phát sinh SQL exception giữa các result set.
- Connection mất trong lúc procedure đang chạy hoặc lúc commit.

Với JDBC, dùng try-with-resources cho ResultSet/Statement/Connection. Với JdbcTemplate, để Spring quản lý connection/statement và đóng ResultSet trong callback. Khi có exception, không cố tiếp tục dùng một CallableStatement hoặc connection đang ở trạng thái protocol không rõ; để Spring/pool thu hồi hoặc loại connection theo cơ chế của nó.

Không retry mọi lỗi procedure. Lỗi thiếu quyền, parameter mismatch hoặc SQL syntax cần sửa cấu hình/code. Deadlock có thể retry toàn transaction nếu nghiệp vụ cho phép. Mất kết nối lúc commit có thể tạo kết quả không xác định; cần idempotency key hoặc truy vấn trạng thái nghiệp vụ trước khi thử lại.

### 15. Bảo mật procedure

Procedure thường được cấp quyền EXECUTE để ứng dụng không cần quyền trực tiếp trên mọi bảng. Tuy nhiên, quyền thực tế phụ thuộc `SQL SECURITY DEFINER` hoặc `SQL SECURITY INVOKER`.

- `DEFINER`: procedure thực thi với quyền của tài khoản definer trong phạm vi quy tắc MySQL.
- `INVOKER`: procedure thực thi với quyền của tài khoản gọi.

Chọn rõ mô hình least privilege, quản lý tài khoản definer và tránh definer là tài khoản cá nhân. Không đưa input người dùng vào dynamic SQL bằng nối chuỗi. Nếu cần tên bảng/cột động, dùng allowlist và quote identifier; parameter marker chỉ bind giá trị, không bind identifier.

Ứng dụng chỉ nên được cấp `EXECUTE` cho procedure cần thiết cùng quyền truy cập tối thiểu khác. Không cấp quyền `CREATE ROUTINE`, `ALTER ROUTINE` hoặc quyền quản trị cho tài khoản runtime nếu không cần.

### 16. Kiểm thử procedure trong Spring Boot

Integration test nên chạy trên MySQL thật hoặc container MySQL tương thích, vì H2 không mô phỏng đầy đủ cú pháp CALL, OUT parameter, result set và hành vi Connector/J.

Ví dụ kiểm thử service:

~~~java
@SpringBootTest
@Transactional
class JdbcOrderReportServiceIT {

    @Autowired
    private JdbcOrderReportService service;

    @Test
    void returnsTwoResultSetsAndOutParameters() {
        OrderReport report = service.loadReport(42L);

        assertEquals(3, report.orders().size());
        assertEquals(2, report.summaries().size());
        assertEquals(3, report.orderCount());
        assertEquals(new BigDecimal("125.50"), report.totalAmount());
    }
}
~~~

Fixture phải tạo dữ liệu có tổng và số hàng biết trước. Nếu test chạy với `@Transactional`, xác minh cách test framework rollback và cách procedure tham gia cùng connection/transaction. Không dùng dữ liệu tồn tại ngẫu nhiên từ database dùng chung.

Các ca cần kiểm thử:

1. Khách hàng có nhiều đơn, nhiều trạng thái.
2. Khách hàng không có đơn: result set rỗng, count 0, tổng tiền 0.
3. OUT parameter có NULL nếu hợp đồng cho phép.
4. Procedure trả update count xen giữa các result set.
5. Procedure ném lỗi ở result set thứ hai.
6. Cột DECIMAL có số lẻ và giá trị lớn.
7. Procedure thêm/bớt/reorder SELECT để test phát hiện contract drift.
8. Connector/J reconnect hoặc connection pool thu hồi connection sau lỗi.
9. Procedure ghi dữ liệu và rollback khi service ném exception.
10. Entity đã load trước procedure được refresh/clear đúng cách.

### 17. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `PROCEDURE ... does not exist` | Sai schema/name hoặc migration chưa deploy | Kiểm tra database hiện tại, `SHOW PROCEDURE STATUS` và deployment |
| `executeQuery()` không trả hết kết quả | Procedure trả nhiều result set hoặc update count | Dùng `execute()` và `getMoreResults()` |
| `getMoreResults()` bỏ qua dữ liệu | Đóng/di chuyển result set sai thứ tự | Đọc và đóng result set hiện tại trước khi chuyển tiếp |
| OUT parameter thành 0 dù database trả NULL | Dùng `getInt()` nhưng không gọi `wasNull()` | Kiểm tra `wasNull()` ngay sau getter |
| OUT parameter chưa sẵn sàng | Chưa tiêu thụ hết result set/update count | Duyệt hết kết quả rồi mới đọc OUT |
| Result set thứ hai map sai DTO | Mapper dựa vào thứ tự cột hoặc result set không đúng contract | Kiểm tra index result set, alias và kiểu dữ liệu |
| JPA trả entity với dữ liệu cũ | Persistence context/cache không biết procedure đã cập nhật | Flush trước, refresh/clear sau; evict second-level cache nếu cần |
| `EXECUTE command denied` | Tài khoản ứng dụng thiếu quyền | Cấp EXECUTE đúng procedure và kiểm tra DEFINER/INVOKER |
| Procedure chạy ngoài transaction dự kiến | JdbcTemplate dùng DataSource/transaction manager khác hoặc procedure tự commit | Dùng cùng DataSource, kiểm tra transaction manager và code procedure |
| Connection lỗi sau procedure | Result set chưa đọc hết, protocol error hoặc connection đã hỏng | Đóng hết kết quả, kiểm tra driver log và để pool loại connection lỗi |
| Giá trị DECIMAL sai | Dùng float/double hoặc scale không đúng | Dùng BigDecimal và kiểm tra precision/scale |

### 18. Checklist thiết kế và vận hành

- [ ] Procedure có hợp đồng rõ về IN, OUT, INOUT và thứ tự result set.
- [ ] Tên cột, alias, kiểu dữ liệu và nullability được ghi nhận.
- [ ] Procedure có số lượng result set ổn định; thay đổi được xem như thay đổi API.
- [ ] API gọi phù hợp: `@Procedure` cho trường hợp đơn giản; JPA/JDBC cho kết quả phức tạp.
- [ ] Với JDBC, dùng `execute()` và duyệt `getMoreResults()` đến khi hết kết quả.
- [ ] Đóng từng ResultSet trước khi chuyển sang kết quả kế tiếp.
- [ ] Đọc OUT parameter sau khi tiêu thụ mọi result set/update count.
- [ ] Kiểm tra `wasNull()` sau primitive getter.
- [ ] Mapping DTO không phụ thuộc cast số nguyên hoặc thứ tự cột không được kiểm thử.
- [ ] JPA persistence context được flush/refresh/clear phù hợp khi procedure ghi dữ liệu.
- [ ] JdbcTemplate dùng cùng DataSource/transaction manager nếu cần tham gia transaction JPA.
- [ ] Procedure không tự commit/rollback ngoài thiết kế transaction.
- [ ] Tài khoản runtime chỉ có EXECUTE và quyền cần thiết; DEFINER/INVOKER được xem xét.
- [ ] Integration test chạy trên MySQL và đúng Connector/J version.
- [ ] Retry có giới hạn; thao tác ghi có cách xử lý kết quả commit không xác định.
- [ ] Logs ghi procedure name, thời gian, SQLState và correlation ID mà không lộ dữ liệu nhạy cảm.

### 19. Bài tập thực hành

Một service Spring Boot gọi procedure `customer_order_report`. Procedure trả danh sách đơn hàng, thống kê theo trạng thái và hai OUT parameter. Ứng dụng chỉ đọc được result set đầu tiên; sau đó lần gọi query tiếp theo trên cùng connection báo lỗi. Một endpoint khác trả `orderCount = 0` dù khách hàng có đơn hàng.

1. Vì sao `executeQuery()` không phù hợp với procedure có nhiều result set?
2. Viết vòng lặp JDBC xử lý ResultSet và update count cho đến khi hết kết quả.
3. Vì sao phải đóng ResultSet hiện tại trước khi gọi `getMoreResults()`?
4. Khi nào có thể đọc OUT parameter an toàn?
5. Làm thế nào phân biệt OUT parameter NULL với giá trị số 0?
6. Khi nào nên chọn Spring Data `@Procedure`, JPA `StoredProcedureQuery` hay `JdbcTemplate`?
7. Nếu procedure cập nhật một entity đang được quản lý bởi EntityManager, cần làm gì với persistence context?
8. Thiết kế integration test cho khách hàng không có đơn và procedure phát sinh lỗi giữa các result set.

### 20. Nguyên tắc vận hành

Hãy xem stored procedure như một API có hợp đồng: xác định rõ tham số, thứ tự result set, alias, kiểu dữ liệu và OUT parameter. Với một OUT/scalar đơn giản, Spring Data `@Procedure` thường đủ; với nhiều result set và update count, dùng `StoredProcedureQuery` hoặc `JdbcTemplate` để duyệt kết quả có kiểm soát. Đọc và đóng hết kết quả trước khi lấy OUT parameter, giữ transaction đồng nhất với Spring, đồng bộ persistence context sau khi procedure ghi dữ liệu và kiểm thử trên MySQL cùng Connector/J thực tế.
