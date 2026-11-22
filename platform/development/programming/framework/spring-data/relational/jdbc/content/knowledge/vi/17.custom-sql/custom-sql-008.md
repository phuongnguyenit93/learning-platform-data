# Phân biệt tham số giá trị với tên bảng, tên cột và cấu trúc SQL

Khi viết SQL tùy chỉnh trong Spring Data JDBC hoặc Spring JDBC, cần phân biệt **dữ liệu được truyền vào câu lệnh** với **cấu trúc tạo nên câu lệnh SQL**. Prepared statement có thể bind một giá trị như mã khách hàng, trạng thái, ngày tháng hoặc số lượng. Nó không thể dùng một placeholder để thay tên bảng, tên cột, từ khóa SQL, toán tử hay toàn bộ một đoạn câu lệnh.

Ranh giới này vừa là quy tắc kỹ thuật của JDBC, vừa là nền tảng để tránh SQL injection. Bài học dùng ví dụ đơn hàng để chỉ ra phần nào nên bind, phần nào phải được chọn từ cấu hình/allowlist, và cách tổ chức truy vấn động an toàn bằng `JdbcTemplate`, `NamedParameterJdbcTemplate` và `@Query` của Spring Data JDBC.

## 1. Hai loại thành phần trong một câu SQL

Xét truy vấn:

```sql
SELECT id, status, total_amount
FROM purchase_order
WHERE customer_id = ?
  AND status = ?
ORDER BY created_at DESC;
```

Có hai nhóm thành phần:

| Nhóm | Ví dụ trong câu SQL | Vai trò |
| --- | --- | --- |
| Cấu trúc SQL | `SELECT`, `FROM`, `WHERE`, `ORDER BY`, `AND`, `DESC` | Xác định database phải thực hiện thao tác nào. |
| Identifier | `purchase_order`, `customer_id`, `created_at`, `status` | Chỉ ra bảng, schema, cột hoặc đối tượng SQL cần truy cập. |
| Giá trị dữ liệu | `7`, `CREATED`, `2026-11-01` | Dữ liệu được so sánh, ghi hoặc xử lý trong câu lệnh. |
| Biểu thức/toán tử | `=`, `>`, `LIKE`, `COUNT(...)` | Xác định cách biểu thức được đánh giá. |

Trong câu lệnh trên, hai dấu `?` là vị trí cho **giá trị dữ liệu**. Khi chạy, JDBC bind ID khách hàng và trạng thái vào các vị trí đó.

Không thể thay `purchase_order` hoặc `created_at` bằng một giá trị bind. Tên bảng và tên cột phải được parser SQL nhận diện khi câu lệnh được phân tích; chúng thuộc cấu trúc câu lệnh.

Có thể nhớ theo câu hỏi:

- Người dùng đang chọn **dữ liệu nào** để tìm? Bind giá trị.
- Người dùng đang chọn **bảng/cột/toán tử/thứ tự nào** để SQL thực thi? Chọn từ tập cấu trúc được ứng dụng cho phép, không bind trực tiếp từ input.

## 2. Bind giá trị bằng PreparedStatement và JdbcTemplate

Ví dụ dùng `JdbcTemplate`:

```java
@Repository
public class OrderSearchRepository {

    private final JdbcTemplate jdbc;

    public OrderSearchRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<OrderSummary> findByCustomerAndStatus(
            long customerId,
            String status) {

        String sql = """
            SELECT id, customer_id, status, total_amount
            FROM purchase_order
            WHERE customer_id = ?
              AND status = ?
            ORDER BY created_at DESC
            """;

        return jdbc.query(
            sql,
            (rs, rowNum) -> new OrderSummary(
                rs.getLong("id"),
                rs.getLong("customer_id"),
                rs.getString("status"),
                rs.getBigDecimal("total_amount")
            ),
            customerId,
            status
        );
    }
}
```

Các giá trị `customerId` và `status` được bind thành tham số của câu lệnh. Nếu status chứa ký tự nháy đơn hoặc chuỗi trông giống SQL, driver vẫn truyền nó như dữ liệu; nó không biến thành một phần của cú pháp câu lệnh.

Ví dụ ghi dữ liệu:

```java
String sql = """
    UPDATE purchase_order
    SET status = ?
    WHERE id = ?
    """;

int updated = jdbc.update(sql, newStatus, orderId);
```

Không nối giá trị request vào SQL bằng toán tử cộng:

```java
// Không an toàn: dữ liệu đi vào cấu trúc SQL.
String sql = "SELECT * FROM purchase_order WHERE status = '"
    + status + "'";
```

Nếu `status` đến từ request, người dùng có thể cung cấp một chuỗi làm thay đổi cú pháp. Ngay cả khi đầu vào hiện tại chỉ đến từ dropdown, vẫn nên bind nó như giá trị. Việc kiểm tra trạng thái có hợp lệ theo domain là một bước khác; parameter binding bảo vệ ranh giới SQL.

## 3. NamedParameterJdbcTemplate: tên tham số không phải tên cột

`NamedParameterJdbcTemplate` cho phép đặt tên dễ đọc cho **giá trị**:

```java
String sql = """
    SELECT id, customer_id, status, total_amount
    FROM purchase_order
    WHERE customer_id = :customerId
      AND status = :status
    """;

MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("customerId", customerId)
    .addValue("status", status);

List<OrderSummary> result =
    namedParameterJdbcTemplate.query(sql, params, rowMapper);
```

Ở đây `:customerId` và `:status` là placeholder cho dữ liệu. Chúng không phải tham chiếu đến cột `customer_id` hay `status`. Tên tham số được đặt theo code; tên cột vẫn nằm trong SQL.

Ví dụ sau không có nghĩa là chọn cột theo giá trị truyền vào:

```sql
SELECT id
FROM purchase_order
WHERE :columnName = :value;
```

Database xem `:columnName` như một biểu thức giá trị. Nó không thay thế identifier `status` hoặc `customer_id`. Tùy database, biểu thức có thể được so sánh như một hằng số, dẫn đến kết quả vô nghĩa hoặc lỗi kiểu dữ liệu.

**Tên placeholder là tên của biến dữ liệu**, không phải cơ chế thay thế văn bản trong SQL.

## 4. Vì sao không thể bind tên bảng hoặc tên cột?

Prepared statement được database phân tích thành cấu trúc trước khi các giá trị bind được đưa vào. Placeholder đại diện cho một literal/expression value ở vị trí được phép, không phải một token identifier trong grammar SQL.

Ví dụ không hoạt động như mong đợi:

```java
String sql = "SELECT * FROM ? WHERE id = ?";
jdbc.query(sql, rowMapper, tableName, id);
```

Placeholder đầu tiên không trở thành tên bảng. Tương tự:

```java
String sql = "SELECT ? FROM purchase_order WHERE id = ?";
jdbc.query(sql, rowMapper, columnName, id);
```

Placeholder trong danh sách SELECT là một giá trị biểu thức, không phải cột được chọn. Kết quả thường là cùng một giá trị hằng được trả về cho mỗi hàng, chứ không phải nội dung của cột có tên được truyền vào.

Một số vị trí không thể thay bằng bind parameter:

| Thành phần muốn thay đổi | Có thể bind trực tiếp không? | Ví dụ |
| --- | --- | --- |
| Giá trị trong WHERE | Có | `WHERE id = ?` |
| Giá trị trong INSERT/UPDATE | Có | `SET status = ?` |
| Giá trị trong LIMIT/OFFSET | Thường có trên nhiều driver/database; cần kiểm tra dialect | `LIMIT ? OFFSET ?` |
| Tên bảng | Không | `FROM ?` |
| Tên schema | Không | `FROM ?.purchase_order` |
| Tên cột | Không | `ORDER BY ?` nếu muốn chọn cột động |
| ASC/DESC | Không | `ORDER BY created_at ?` |
| Toán tử | Không | `WHERE amount ? ?` |
| Từ khóa hoặc đoạn SQL | Không | Chèn `DISTINCT` bằng placeholder |
| Tên hàm/cú pháp JOIN | Không | Chọn fragment JOIN bằng placeholder |

Một lưu ý: một số database cho phép bind giá trị ở vị trí giới hạn/số dòng hoặc biểu thức cụ thể. Hãy kiểm tra driver và dialect. Điều đó không làm placeholder trở thành công cụ thay thế identifier hoặc cú pháp SQL.

## 5. ORDER BY ? không chọn cột theo tham số

Đây là lỗi thường gặp khi xây dựng màn hình sắp xếp động:

```java
String sql = """
    SELECT id, status, created_at
    FROM purchase_order
    ORDER BY ?
    """;

jdbc.query(sql, rowMapper, sortColumn);
```

Lập trình viên có thể nghĩ rằng truyền `created_at` sẽ tạo ra `ORDER BY created_at`. Nhưng database nhận một giá trị tham số trong biểu thức sắp xếp. Nó không phân tích nội dung chuỗi tham số thành tên cột. Các hàng có thể được sắp xếp theo cùng một hằng số, nên kết quả không được sắp xếp theo cột mong muốn.

Tương tự, `ORDER BY ? DESC` không cho phép người dùng chọn identifier. Bind parameter an toàn về mặt dữ liệu nhưng sai về ý nghĩa truy vấn.

Giải pháp là chọn tên cột từ danh sách cho phép, sau đó chỉ bind các giá trị còn lại.

## 6. Dynamic sorting an toàn bằng allowlist

Giả sử giao diện cho phép sắp xếp đơn hàng theo ngày tạo, tổng tiền hoặc trạng thái. Không nối trực tiếp `sortBy` từ request vào SQL. Hãy ánh xạ một khóa API cố định sang identifier SQL do ứng dụng kiểm soát.

```java
private static final Map<String, String> SORT_COLUMNS = Map.of(
    "createdAt", "created_at",
    "totalAmount", "total_amount",
    "status", "status"
);

public List<OrderSummary> search(
        long customerId,
        String requestedSort,
        String requestedDirection,
        int limit) {

    String column = SORT_COLUMNS.get(requestedSort);
    if (column == null) {
        throw new IllegalArgumentException("Unsupported sort field");
    }

    String direction = switch (
            requestedDirection.toUpperCase(Locale.ROOT)) {
        case "ASC" -> "ASC";
        case "DESC" -> "DESC";
        default -> throw new IllegalArgumentException(
            "Unsupported sort direction"
        );
    };

    String sql = """
        SELECT id, customer_id, status, total_amount, created_at
        FROM purchase_order
        WHERE customer_id = ?
        ORDER BY %s %s
        LIMIT ?
        """.formatted(column, direction);

    return jdbc.query(sql, rowMapper, customerId, limit);
}
```

Trong ví dụ:

- `requestedSort` không được chèn thẳng vào SQL. Nó chỉ là khóa tra cứu trong `SORT_COLUMNS`.
- Giá trị lấy từ map là identifier SQL viết sẵn trong source code.
- `requestedDirection` được chuyển thành một trong hai chuỗi cố định `ASC` hoặc `DESC`.
- `customerId` và `limit` vẫn được bind như dữ liệu.
- Nếu người dùng gửi một khóa không được hỗ trợ, ứng dụng từ chối yêu cầu.

Cấu trúc được nối vào SQL là **giá trị đã được allowlist**, không phải input tùy ý. Cách này giữ khả năng sắp xếp linh hoạt và bảo đảm câu SQL chỉ chứa identifier/keyword mà ứng dụng đã định nghĩa.

Nếu API không cần nhiều lựa chọn, dùng enum còn rõ ràng hơn:

```java
public enum OrderSort {
    CREATED_AT,
    TOTAL_AMOUNT,
    STATUS
}
```

Có thể dùng `switch` trên enum để lấy tên cột. Enum giúp tránh việc mọi tầng trong ứng dụng truyền đi các chuỗi tự do.

### Allowlist cả chiều sắp xếp

`ASC` và `DESC` là cú pháp SQL, không phải giá trị dữ liệu. Không làm như sau:

```java
String sql = "SELECT ... ORDER BY created_at " + request.direction();
```

Thay vào đó, chỉ chấp nhận các lựa chọn cụ thể. Với boolean như `descending`, có thể ánh xạ:

```java
String direction = descending ? "DESC" : "ASC";
```

Không nối một chuỗi tùy ý như `NULLS FIRST`, `COLLATE ...` hoặc phần SQL do client gửi nếu chưa có allowlist riêng và hiểu rõ semantics của database.

## 7. Dynamic table/schema: chỉ chọn từ cấu hình đáng tin cậy

Đôi khi ứng dụng phải truy vấn một trong vài bảng có cùng cấu trúc, ví dụ bảng dữ liệu hiện tại và bảng lưu trữ:

```java
public enum OrderStore {
    CURRENT,
    ARCHIVE
}
```

Ánh xạ lựa chọn thành tên bảng cố định:

```java
private static String tableFor(OrderStore store) {
    return switch (store) {
        case CURRENT -> "purchase_order";
        case ARCHIVE -> "purchase_order_archive";
    };
}

public List<OrderSummary> findById(OrderStore store, long id) {
    String table = tableFor(store);

    String sql = """
        SELECT id, customer_id, status, total_amount
        FROM %s
        WHERE id = ?
        """.formatted(table);

    return jdbc.query(sql, rowMapper, id);
}
```

Giá trị `store` nên được quyết định từ nghiệp vụ/authorization của ứng dụng. Không truyền trực tiếp tên bảng từ query string hoặc JSON vào `tableFor`.

Không an toàn:

```java
String sql = "SELECT * FROM " + request.tableName()
    + " WHERE id = ?";
```

Nếu người dùng điều khiển `tableName`, họ có thể thử chèn identifier khác, schema khác hoặc cú pháp ngoài dự kiến. Ngay cả khi tài khoản database không cho phép truy cập bảng nhạy cảm, ứng dụng vẫn không nên để request tự quyết định cấu trúc SQL.

### Schema theo tenant

Một số hệ thống có schema riêng cho từng tenant. Không nối chuỗi tenant ID chưa xác thực thành tên schema:

```java
// Không an toàn nếu tenantSchema lấy trực tiếp từ request.
String sql = "SELECT * FROM " + tenantSchema + ".purchase_order";
```

Hướng an toàn hơn là ánh xạ tenant đã được xác thực sang schema nằm trong registry/cấu hình do server quản lý. Nếu dùng datasource routing hoặc thiết lập schema/search path trên connection, cần bảo đảm tenant context được kiểm tra và không bị rò rỉ giữa các request/connection pool.

Allowlist có thể là map từ tenant key nội bộ sang schema identifier cố định. Không coi việc kiểm tra chuỗi bằng regex là đủ để chứng minh người dùng được phép truy cập schema đó.

## 8. Dynamic WHERE: ghép fragment cố định, bind mọi giá trị

Truy vấn tìm kiếm có thể có một số filter tùy chọn. Ví dụ người dùng lọc theo khách hàng, trạng thái và khoảng ngày.

Có thể xây dựng câu SQL từ những fragment do code định nghĩa:

```java
public List<OrderSummary> search(OrderFilter filter) {
    StringBuilder sql = new StringBuilder("""
        SELECT id, customer_id, status, total_amount, created_at
        FROM purchase_order
        WHERE 1 = 1
        """);

    MapSqlParameterSource params = new MapSqlParameterSource();

    if (filter.customerId() != null) {
        sql.append(" AND customer_id = :customerId");
        params.addValue("customerId", filter.customerId());
    }

    if (filter.status() != null) {
        sql.append(" AND status = :status");
        params.addValue("status", filter.status());
    }

    if (filter.createdFrom() != null) {
        sql.append(" AND created_at >= :createdFrom");
        params.addValue("createdFrom", filter.createdFrom());
    }

    if (filter.createdBefore() != null) {
        sql.append(" AND created_at < :createdBefore");
        params.addValue("createdBefore", filter.createdBefore());
    }

    return namedParameterJdbcTemplate.query(
        sql.toString(),
        params,
        rowMapper
    );
}
```

Các đoạn nối vào SQL là literal cố định do code viết. Dữ liệu thực tế được đưa vào `MapSqlParameterSource`. Cách này cho phép số lượng điều kiện thay đổi mà không phải nối giá trị người dùng vào câu lệnh.

Không làm:

```java
sql.append(" AND status = '" + filter.status() + "'");
```

Cũng không nhận nguyên một biểu thức WHERE do client gửi. Client nên gửi filter có cấu trúc (ví dụ `status`, `createdFrom`), còn server quyết định cách biến filter đó thành SQL.

### Dynamic operator

Nếu cần cho phép nhiều kiểu so sánh, ánh xạ operator thành một tập cố định:

```java
String operator = switch (filter.amountComparison()) {
    case EQUALS -> "=";
    case GREATER_THAN -> ">";
    case LESS_THAN -> "<";
};

sql.append(" AND total_amount ").append(operator)
   .append(" :amount");
params.addValue("amount", filter.amount());
```

Toán tử không thể bind như một giá trị. Chỉ nối operator sau khi đã chuyển từ enum/allowlist sang một trong các chuỗi cố định. Không nối trực tiếp chuỗi operator do request gửi vào SQL.

## 9. NamedParameterJdbcTemplate và danh sách IN

Một ưu điểm của `NamedParameterJdbcTemplate` là có thể mở rộng collection thành nhiều placeholder trong `IN`:

```java
String sql = """
    SELECT id, status
    FROM purchase_order
    WHERE status IN (:statuses)
    """;

MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("statuses", List.of("CREATED", "CONFIRMED"));

List<OrderHeader> result =
    namedParameterJdbcTemplate.query(sql, params, headerMapper);
```

Framework mở rộng collection thành danh sách bind parameter phù hợp, thay vì nối từng giá trị vào SQL. Từng status vẫn là dữ liệu được bind.

Cần xử lý danh sách rỗng trước khi chạy query. Không nên phụ thuộc vào việc database chấp nhận `IN ()`; nhiều database không hỗ trợ cú pháp đó. Quyết định thường gặp:

- Danh sách rỗng có nghĩa là không lọc theo trạng thái: bỏ điều kiện `IN`.
- Danh sách rỗng có nghĩa là không có kết quả nào được phép: trả danh sách rỗng ngay ở service.
- Danh sách rỗng không hợp lệ theo API: trả validation error.

Không chuyển list thành chuỗi rồi ghép vào SQL. Cách đó khó xử lý quoting và mở ra SQL injection.

## 10. @Query trong Spring Data JDBC cũng bind giá trị

Repository có thể khai báo SQL tùy chỉnh bằng `@Query`:

```java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    @Query("""
        SELECT id, customer_id, status, total_amount, created_at, note
        FROM purchase_order
        WHERE customer_id = :customerId
          AND status = :status
        ORDER BY created_at DESC
        """)
    List<PurchaseOrder> findRecentByCustomerAndStatus(
        Long customerId,
        String status
    );
}
```

Tên tham số như `:customerId` và `:status` là placeholder cho giá trị. `purchase_order`, `customer_id`, `status` và `created_at` vẫn là identifier được viết trong SQL.

Không thể viết một `@Query` kiểu:

```java
@Query("SELECT * FROM :tableName WHERE :columnName = :value")
List<PurchaseOrder> search(
    String tableName,
    String columnName,
    Object value
);
```

với kỳ vọng Spring Data thay `tableName` thành tên bảng và `columnName` thành tên cột. Các placeholder đó không phải cơ chế template cho identifier. Nếu cần chọn bảng/cột động, dùng custom repository để chọn fragment đã allowlist rồi bind các giá trị.

Khi dùng `@Query`, cũng cần bảo đảm câu SQL phù hợp với kiểu kết quả. Truy vấn aggregate phải trả đủ dữ liệu cần để ánh xạ theo hợp đồng mapping; truy vấn báo cáo nên dùng DTO/projection hoặc custom row mapper phù hợp. Parameter binding không tự giải quyết vấn đề projection hoặc aggregate loading.

## 11. LIKE: bind giá trị vẫn cần hiểu wildcard

Parameter binding ngăn chuỗi đầu vào trở thành cú pháp SQL, nhưng không thay đổi ý nghĩa wildcard của `LIKE`.

Ví dụ:

```java
String sql = """
    SELECT id, note
    FROM purchase_order
    WHERE note LIKE ?
    """;

jdbc.query(sql, rowMapper, "%" + searchText + "%");
```

`searchText` vẫn được bind an toàn. Tuy nhiên, nếu người dùng nhập `%` hoặc `_`, các ký tự đó có ý nghĩa wildcard trong `LIKE`; kết quả có thể rộng hơn mong muốn. Đây là vấn đề semantics tìm kiếm, không phải SQL injection.

Nếu muốn tìm literal substring, cần escape wildcard theo quy ước của câu SQL và chỉ định ký tự `ESCAPE`, ví dụ:

```sql
SELECT id, note
FROM purchase_order
WHERE note LIKE ? ESCAPE '!';
```

Ứng dụng có thể escape `!`, `%` và `_` trong input trước khi thêm wildcard ở hai đầu. Quy tắc escape cần nhất quán với database và ký tự escape đã chọn.

Đừng nhầm hai mục tiêu:

- Bind parameter bảo vệ ranh giới giữa giá trị và cú pháp SQL.
- Escape wildcard bảo vệ ý nghĩa tìm kiếm literal trong toán tử `LIKE`.

## 12. Identifier quoting không thay thế allowlist

Database có cú pháp quote identifier riêng. PostgreSQL dùng dấu nháy kép, MySQL thường dùng backtick (hoặc nháy kép khi bật chế độ phù hợp), SQL Server dùng ngoặc vuông hoặc quy tắc quote identifier. Quote giúp database hiểu một identifier có chữ hoa, khoảng trắng hoặc trùng từ khóa theo quy tắc của engine.

Nhưng **quote một chuỗi tùy ý không tự chứng minh người dùng được phép chọn identifier đó**. Cần tách hai việc:

1. Xác thực identifier có thuộc tập lựa chọn ứng dụng cho phép hay không.
2. Nếu cần, quote identifier theo đúng dialect và quy tắc escape của database.

Với các cột sort đã biết, allowlist ánh xạ trực tiếp sang identifier chuẩn thường đơn giản hơn tự tạo hàm quote. Tránh viết một hàm quote tự chế rồi xem đó là giải pháp duy nhất chống injection.

Không dùng cách thay dấu nháy hoặc xóa ký tự đặc biệt bằng regex để “làm sạch” identifier tùy ý. Regex có thể bỏ sót quy tắc escape, từ khóa, schema qualification hoặc quyền truy cập. Allowlist cụ thể thể hiện rõ cấu trúc nào ứng dụng cho phép.

## 13. Những ví dụ SQL injection cần tránh

### Nối giá trị trực tiếp vào điều kiện

```java
String sql = "SELECT * FROM purchase_order WHERE status = '"
    + request.status() + "'";
```

Nếu input chứa dấu nháy và phần SQL tiếp theo, nó có thể làm thay đổi logic câu lệnh.

Cách đúng:

```java
String sql = """
    SELECT * FROM purchase_order
    WHERE status = ?
    """;

jdbc.query(sql, rowMapper, request.status());
```

### Nối cột sort từ request

```java
String sql = "SELECT * FROM purchase_order ORDER BY "
    + request.sortBy();
```

Cách đúng: tra `sortBy` trong allowlist, từ chối khóa không hỗ trợ, rồi nối identifier cố định đã chọn. Các giá trị filter vẫn bind riêng.

### Nối nguyên đoạn điều kiện

```java
String sql = "SELECT * FROM purchase_order WHERE "
    + request.whereClause();
```

Không nhận `WHERE` fragment tự do từ client. Hãy nhận DTO filter có kiểu dữ liệu, xác thực từng field và tự xây dựng các điều kiện cố định ở server.

### Dữ liệu đã lưu cũng không tự động đáng tin

Một giá trị lấy từ database có thể ban đầu được nhập bởi người dùng hoặc hệ thống bên ngoài. Nếu sau đó lấy giá trị đó và nối vào SQL động, nó vẫn có thể tạo ra injection. Hãy bind mọi dữ liệu như value parameter; identifier động vẫn phải lấy từ cấu hình/allowlist, bất kể nguồn của chuỗi.

## 14. Thiết kế API tìm kiếm không để client gửi SQL

Một API nên nhận yêu cầu nghiệp vụ có cấu trúc:

```json
{
  "customerId": 7,
  "statuses": ["CREATED", "CONFIRMED"],
  "sortBy": "createdAt",
  "direction": "DESC",
  "limit": 20
}
```

Server thực hiện các bước:

1. Xác thực quyền truy cập customer 7.
2. Kiểm tra danh sách trạng thái thuộc các giá trị domain hợp lệ.
3. Tra `sortBy` trong allowlist.
4. Chuyển direction thành `ASC` hoặc `DESC` cố định.
5. Kiểm tra limit trong giới hạn được phép.
6. Xây dựng SQL từ cấu trúc đã kiểm soát.
7. Bind customer ID, từng status và limit như dữ liệu.

API không cần và không nên nhận:

```json
{
  "table": "purchase_order",
  "column": "created_at",
  "operator": ">",
  "where": "customer_id = 7",
  "orderBy": "created_at DESC"
}
```

Nếu sản phẩm thực sự cần query builder tổng quát, hãy định nghĩa một ngôn ngữ filter nhỏ với các field/operator được hỗ trợ, sau đó compile sang SQL từ allowlist. Đừng biến API thành cổng thực thi SQL tùy ý.

## 15. Kiểm thử parameter binding và cấu trúc động

Nên kiểm thử hai nhóm riêng.

### Kiểm thử giá trị

- Trạng thái có dấu nháy, dấu gạch ngang hoặc ký tự Unicode vẫn được coi là một giá trị.
- Chuỗi giống payload SQL không làm thay đổi cấu trúc query.
- Null được xử lý theo hợp đồng và kiểu SQL.
- Ngày, số thập phân và boolean được bind đúng kiểu.
- Danh sách `IN` có 1, nhiều và 0 phần tử được xử lý đúng.

### Kiểm thử cấu trúc

- Chỉ các khóa sort được allowlist mới được chấp nhận.
- `ASC` và `DESC` là hai lựa chọn hợp lệ; chuỗi khác bị từ chối.
- Tên bảng chỉ có thể được chọn từ enum/registry được phép.
- Không có API nào nối trực tiếp `whereClause`, `columnName` hoặc `tableName` do client cung cấp.
- Các filter tùy chọn chỉ thêm fragment cố định và bind giá trị tương ứng.
- Query được chạy với đúng database/driver production khi có cú pháp phụ thuộc dialect.

Ví dụ test sort field không hợp lệ:

```java
assertThatThrownBy(() ->
    repository.search(
        7L,
        "created_at DESC; DELETE FROM customer",
        "ASC",
        20
    )
).isInstanceOf(IllegalArgumentException.class);
```

Test này xác nhận khóa không nằm trong allowlist bị từ chối. Nên bổ sung integration test để xác nhận không có câu lệnh phụ được thực thi và dữ liệu vẫn nguyên vẹn.

Một test giá trị độc hại nên xác nhận nó được xem như dữ liệu:

```java
String input = "' OR 1=1 --";

List<OrderSummary> result =
    repository.findByStatus(input);
```

Kết quả đúng là truy vấn tìm trạng thái bằng chính chuỗi đó; nó không trả toàn bộ đơn như khi ghép chuỗi SQL không an toàn.

## 16. Bảng quyết định: bind hay allowlist?

| Thành phần đầu vào | Cách xử lý | Ví dụ |
| --- | --- | --- |
| ID khách hàng | Bind value | `WHERE customer_id = :id` |
| Trạng thái | Bind value và validate domain | `status = :status` |
| Ngày bắt đầu/kết thúc | Bind value | `created_at >= :from` |
| Từ khóa tìm kiếm | Bind value; escape wildcard nếu cần literal LIKE | `note LIKE :pattern` |
| Danh sách trạng thái | Bind collection qua named parameter | `status IN (:statuses)` |
| Tên cột sort | Allowlist/enum thành identifier cố định | `created_at`, `total_amount` |
| Hướng sort | Allowlist enum/boolean | `ASC`, `DESC` |
| Tên bảng | Allowlist/configuration phía server | `purchase_order`, `purchase_order_archive` |
| Tên schema/tenant | Registry được xác thực hoặc datasource/schema routing | tenant key → schema cố định |
| Toán tử | Allowlist enum | `=`, `>`, `<` |
| SQL fragment/WHERE/JOIN | Không nhận từ client; dựng từ fragment cố định trong code | `AND status = :status` |
| Tên hàm/cú pháp vendor-specific | Chọn từ code/configuration đã kiểm soát | hàm phù hợp dialect |

## 17. Nguyên tắc tổ chức custom repository

Khi truy vấn động có nhiều lựa chọn, nên gom logic dựng SQL vào một adapter/repository riêng. Tách ba bước:

- **Validate request:** kiểm tra filter, quyền truy cập, sort key, direction và giới hạn.
- **Build statement:** chọn fragment/identifier từ allowlist và ghép cấu trúc cố định.
- **Bind parameters:** truyền mọi giá trị bằng `JdbcTemplate` hoặc `NamedParameterJdbcTemplate`.

Ví dụ một thiết kế đơn giản:

```java
public record OrderSearch(
    Long customerId,
    String status,
    OrderSort sort,
    SortDirection direction,
    int limit
) {}

public enum OrderSort {
    CREATED_AT,
    TOTAL_AMOUNT,
    STATUS
}

public enum SortDirection {
    ASC,
    DESC
}
```

Enum sort có thể được ánh xạ bằng `switch`:

```java
private static String columnFor(OrderSort sort) {
    return switch (sort) {
        case CREATED_AT -> "created_at";
        case TOTAL_AMOUNT -> "total_amount";
        case STATUS -> "status";
    };
}
```

Enum direction có thể chuyển trực tiếp sang chuỗi SQL cố định:

```java
private static String directionFor(SortDirection direction) {
    return switch (direction) {
        case ASC -> "ASC";
        case DESC -> "DESC";
    };
}
```

Nhờ vậy, phần code tạo SQL không phải đoán xem chuỗi nào từ request có thể được nối. Nó chỉ nhận những lựa chọn đã được xác thực và chuyển chúng thành cấu trúc SQL hợp lệ.

Nếu dùng nhiều database, identifier và cú pháp có thể khác theo dialect. Giữ phần khác biệt đó trong adapter/implementation tương ứng, không rải các nhánh vendor-specific khắp service.

## 18. Câu hỏi tự kiểm tra

- PreparedStatement dùng placeholder cho loại thành phần nào trong câu SQL?
- Vì sao `FROM ?` không thay `?` bằng tên bảng?
- `ORDER BY ?` khác gì `ORDER BY created_at`?
- Tại sao tên tham số `:customerId` không phải tên cột?
- Khi nào có thể dùng `NamedParameterJdbcTemplate` để bind danh sách trong `IN`?
- Nếu người dùng chọn cột sắp xếp, ứng dụng cần làm gì trước khi đưa tên cột vào SQL?
- Vì sao phải allowlist cả `ASC`/`DESC` và toán tử?
- Có thể nhận nguyên `WHERE` fragment từ client rồi bind một phần giá trị không? Vì sao?
- Identifier quoting có thay thế allowlist không?
- Làm thế nào giữ an toàn khi lựa chọn schema theo tenant?
- Vì sao dữ liệu lấy từ database vẫn phải bind nếu dùng lại trong một câu SQL khác?
- `LIKE` parameter binding có tự biến `%` và `_` thành ký tự literal không?

Khi viết SQL tùy chỉnh, hãy **bind mọi giá trị dữ liệu** và **chọn mọi identifier/cấu trúc động từ tập lựa chọn do ứng dụng kiểm soát**. Prepared statement không phải bộ thay thế văn bản cho SQL; nó giữ phần dữ liệu tách khỏi cú pháp. Với tên bảng, tên cột, hướng sắp xếp và toán tử, hãy dùng enum/allowlist hoặc cấu hình server-side, sau đó kiểm thử cả dữ liệu đầu vào lẫn cấu trúc câu lệnh được tạo.
