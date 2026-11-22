# ResultSetExtractor và gom nhiều hàng thành một kết quả

Trong **Spring Data Relational JDBC**, một câu SQL có thể trả về nhiều hàng nhưng ứng dụng lại cần một kết quả Java có cấu trúc khác với từng hàng riêng lẻ. Trường hợp phổ biến là truy vấn JOIN một bảng cha với bảng con: một đơn hàng có nhiều dòng sản phẩm, nên SQL trả về một hàng cho mỗi dòng sản phẩm, trong khi màn hình cần một object đơn hàng chứa danh sách sản phẩm.

**`ResultSetExtractor<T>`** của Spring JDBC giải quyết kiểu bài toán này. Thay vì ánh xạ độc lập từng hàng, callback nhận toàn bộ `ResultSet` và tự quyết định cách duyệt, nhóm và kết hợp các hàng thành một kết quả `T`. Kết quả có thể là một DTO lồng nhau, một danh sách DTO, một map hoặc một cấu trúc đọc khác.

Bài học này tập trung vào cách dùng `ResultSetExtractor` để gom nhiều hàng SQL thành kết quả Java, cách phân biệt nó với `RowMapper` và `RowCallbackHandler`, cách xử lý JOIN một-nhiều, giá trị NULL, hàng trùng lặp và phân trang.

## 1. Vì sao cần gom nhiều hàng thành một kết quả?

Giả sử database có hai bảng:

```sql
CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL,
    status VARCHAR(20) NOT NULL
);

CREATE TABLE order_items (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES purchase_orders(id),
    product_code VARCHAR(40) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(19, 2) NOT NULL
);
```

Một đơn hàng có thể có nhiều dòng sản phẩm:

```text
purchase_orders
+----+-------------+--------+
| id | order_number| status |
+----+-------------+--------+
| 42 | ORD-0042    | PAID   |
+----+-------------+--------+

order_items
+----+----------+--------------+----------+
| id | order_id | product_code | quantity |
+----+----------+--------------+----------+
| 1  | 42       | KB-01        | 2        |
| 2  | 42       | MS-02        | 1        |
| 3  | 42       | USB-03       | 3        |
+----+----------+--------------+----------+
```

Truy vấn JOIN:

```sql
SELECT
    o.id AS order_id,
    o.order_number,
    o.status,
    i.id AS item_id,
    i.product_code,
    i.quantity,
    i.unit_price
FROM purchase_orders o
LEFT JOIN order_items i ON i.order_id = o.id
WHERE o.id = :orderId
ORDER BY i.id;
```

Kết quả SQL có ba hàng:

| order_id | order_number | status | item_id | product_code | quantity |
|---:|---|---|---:|---|---:|
| 42 | ORD-0042 | PAID | 1 | KB-01 | 2 |
| 42 | ORD-0042 | PAID | 2 | MS-02 | 1 |
| 42 | ORD-0042 | PAID | 3 | USB-03 | 3 |

Nhưng object Java mà ứng dụng muốn trả về có thể là:

```text
OrderDetails
  id: 42
  orderNumber: ORD-0042
  status: PAID
  items:
    - OrderItem(id=1, productCode=KB-01, quantity=2)
    - OrderItem(id=2, productCode=MS-02, quantity=1)
    - OrderItem(id=3, productCode=USB-03, quantity=3)
```

Đây là phép biến đổi **nhiều hàng kết quả → một object cha có collection con**. Nếu dùng một `RowMapper` đơn giản, mỗi hàng sẽ được map riêng thành một object. `ResultSetExtractor` cho phép đọc hết các hàng và gom chúng lại.

## 2. Phân biệt ResultSetExtractor, RowMapper và RowCallbackHandler

Ba callback đều thuộc Spring JDBC, nhưng mục đích khác nhau.

| API | Đơn vị xử lý | Giá trị trả về | Trường hợp phù hợp |
|---|---|---|---|
| `RowMapper<T>` | Một hàng | Một object cho mỗi hàng | Mỗi hàng tương ứng một DTO/entity độc lập |
| `ResultSetExtractor<T>` | Toàn bộ ResultSet | Một kết quả `T` do callback quyết định | Gom nhiều hàng, tạo object lồng nhau, tổng hợp kết quả |
| `RowCallbackHandler` | Một hàng | Không trả kết quả từ callback | Xử lý từng hàng bằng side effect, ghi file hoặc đẩy dữ liệu sang nơi khác |

### 2.1. RowMapper: một hàng thành một object

```java
List<OrderItemView> items = jdbc.query(
    """
    SELECT id, product_code, quantity, unit_price
    FROM order_items
    WHERE order_id = :orderId
    ORDER BY id
    """,
    Map.of("orderId", 42L),
    (rs, rowNum) -> new OrderItemView(
        rs.getLong("id"),
        rs.getString("product_code"),
        rs.getInt("quantity"),
        rs.getBigDecimal("unit_price")
    )
);
```

Mỗi hàng được ánh xạ độc lập thành một `OrderItemView`. Kết quả của `query` là danh sách các object. Đây là lựa chọn đơn giản khi kết quả SQL đã có đúng một hàng cho mỗi object mà ứng dụng muốn tạo.

### 2.2. ResultSetExtractor: toàn bộ hàng thành một kết quả

`ResultSetExtractor<T>` có dạng khái quát:

```java
@FunctionalInterface
public interface ResultSetExtractor<T> {
    T extractData(ResultSet rs) throws SQLException, DataAccessException;
}
```

Callback nhận `ResultSet` đã được thực thi và có thể tự gọi `rs.next()` để duyệt toàn bộ hàng. Nó quyết định trả về một `T` duy nhất.

```java
OrderDetails result = jdbc.query(
    sql,
    parameters,
    rs -> {
        // Tự duyệt ResultSet, nhóm các hàng
        // và trả về một OrderDetails.
    }
);
```

`NamedParameterJdbcTemplate.query(...)` quản lý tài nguyên JDBC xung quanh callback. Không tự đóng `ResultSet` hoặc `Statement` do template cung cấp bên trong extractor.

### 2.3. RowCallbackHandler: xử lý từng hàng mà không tạo kết quả trả về

```java
jdbc.query(
    sql,
    parameters,
    rs -> {
        String code = rs.getString("product_code");
        auditBuffer.add(code);
    }
);
```

`RowCallbackHandler` hữu ích khi cần xử lý từng hàng mà không cần trả về một object tổng hợp. Nếu muốn trả một object cha có danh sách con, `ResultSetExtractor` thường diễn đạt ý định rõ hơn.

## 3. Cấu trúc DTO cho kết quả lồng nhau

Tạo hai record để biểu diễn dữ liệu đọc:

```java
import java.math.BigDecimal;
import java.util.List;

public record OrderItemView(
    Long id,
    String productCode,
    int quantity,
    BigDecimal unitPrice
) {}

public record OrderDetails(
    Long id,
    String orderNumber,
    String status,
    List<OrderItemView> items
) {}
```

`OrderDetails` là DTO/read model cho truy vấn đọc. Nó không nhất thiết phải là aggregate class được Spring Data JDBC dùng để ghi. DTO này chỉ thể hiện hình dạng kết quả mà màn hình hoặc API cần.

Tách DTO giúp chỉ lấy các cột cần thiết, chủ động tạo cấu trúc cha/con từ JOIN, không phụ thuộc vào constructor hoặc lifecycle của aggregate domain và trả kết quả đọc thuận tiện cho API.

## 4. Dùng ResultSetExtractor gom các dòng sản phẩm của một đơn hàng

Vì query chỉ tìm một đơn theo ID, ta có thể giữ một accumulator cho đơn đó và thêm từng dòng sản phẩm khi duyệt ResultSet.

### 4.1. SQL

```sql
SELECT
    o.id AS order_id,
    o.order_number,
    o.status,
    i.id AS item_id,
    i.product_code,
    i.quantity,
    i.unit_price
FROM purchase_orders o
LEFT JOIN order_items i ON i.order_id = o.id
WHERE o.id = :orderId
ORDER BY i.id;
```

Dùng `LEFT JOIN` để đơn hàng vẫn xuất hiện ngay cả khi chưa có dòng sản phẩm. Trong trường hợp đó, các cột phía `order_items` sẽ là SQL NULL.

### 4.2. Accumulator nội bộ

Accumulator là object mutable chỉ tồn tại trong lúc đọc ResultSet. Sau khi đã gom đủ dữ liệu, ta chuyển nó thành DTO immutable.

```java
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

final class OrderAccumulator {

    private final Long id;
    private final String orderNumber;
    private final String status;
    private final List<OrderItemView> items = new ArrayList<>();

    OrderAccumulator(Long id, String orderNumber, String status) {
        this.id = id;
        this.orderNumber = orderNumber;
        this.status = status;
    }

    void addItem(ResultSet rs) throws SQLException {
        Long itemId = rs.getObject("item_id", Long.class);

        // LEFT JOIN không tìm thấy dòng con:
        // item_id sẽ là NULL.
        if (itemId == null) {
            return;
        }

        items.add(new OrderItemView(
            itemId,
            rs.getString("product_code"),
            rs.getInt("quantity"),
            rs.getBigDecimal("unit_price")
        ));
    }

    OrderDetails toResult() {
        return new OrderDetails(
            id,
            orderNumber,
            status,
            List.copyOf(items)
        );
    }
}
```

`OrderAccumulator` giữ dữ liệu cha và danh sách con. Phương thức `addItem` kiểm tra ID dòng con trước khi tạo object. Khi `item_id` là NULL, đơn hàng không có dòng con; ta không tạo một `OrderItemView` giả với ID bằng 0.

### 4.3. Repository dùng ResultSetExtractor

```java
import java.util.Map;
import java.util.Optional;

import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderDetailsReadRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public OrderDetailsReadRepository(
            NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Optional<OrderDetails> findById(long orderId) {
        String sql = """
            SELECT
                o.id AS order_id,
                o.order_number,
                o.status,
                i.id AS item_id,
                i.product_code,
                i.quantity,
                i.unit_price
            FROM purchase_orders o
            LEFT JOIN order_items i ON i.order_id = o.id
            WHERE o.id = :orderId
            ORDER BY i.id
            """;

        OrderDetails result = jdbc.query(
            sql,
            Map.of("orderId", orderId),
            rs -> {
                OrderAccumulator order = null;

                while (rs.next()) {
                    if (order == null) {
                        order = new OrderAccumulator(
                            rs.getLong("order_id"),
                            rs.getString("order_number"),
                            rs.getString("status")
                        );
                    }

                    order.addItem(rs);
                }

                return order == null ? null : order.toResult();
            }
        );

        return Optional.ofNullable(result);
    }
}
```

Giải thích:

1. `jdbc.query` thực thi SQL và chuyển ResultSet vào extractor.
2. `order` ban đầu là `null` vì chưa đọc hàng nào.
3. Hàng đầu tiên khởi tạo thông tin cha `OrderAccumulator`.
4. Mỗi hàng được chuyển thành một dòng con nếu `item_id` không NULL.
5. Khi hết ResultSet, `toResult()` tạo một `OrderDetails` chứa toàn bộ danh sách.
6. Nếu không có hàng nào, extractor trả `null`; repository chuyển thành `Optional.empty()`.

`LEFT JOIN` đảm bảo đơn tồn tại nhưng chưa có item vẫn tạo một hàng với các cột item NULL. Nếu đơn không tồn tại, query không trả hàng nào và kết quả là `Optional.empty()`.

**Lưu ý:** ví dụ dùng `ResultSet.getObject(column, Long.class)` để đọc nullable ID. Nếu driver cũ không hỗ trợ kiểu overload này, có thể dùng `getLong` rồi gọi `wasNull()` ngay sau đó:

```java
long rawId = rs.getLong("item_id");
Long itemId = rs.wasNull() ? null : rawId;
```

Không dùng riêng `getLong` để nhận biết NULL, vì JDBC trả 0 cho SQL NULL khi đọc bằng primitive và cần `wasNull()` để phân biệt.

## 5. Gom nhiều đơn hàng thành một danh sách kết quả

Nếu query trả về nhiều đơn hàng, mỗi đơn có nhiều dòng sản phẩm, cần một accumulator cho từng ID đơn. Cấu trúc `Map` giữ liên hệ giữa hàng SQL và object cha.

### 5.1. SQL cho nhiều đơn

```sql
SELECT
    o.id AS order_id,
    o.order_number,
    o.status,
    i.id AS item_id,
    i.product_code,
    i.quantity,
    i.unit_price
FROM purchase_orders o
LEFT JOIN order_items i ON i.order_id = o.id
WHERE o.status = :status
ORDER BY o.id, i.id;
```

### 5.2. ResultSetExtractor trả về List<OrderDetails>

```java
public List<OrderDetails> findByStatus(String status) {
    String sql = """
        SELECT
            o.id AS order_id,
            o.order_number,
            o.status,
            i.id AS item_id,
            i.product_code,
            i.quantity,
            i.unit_price
        FROM purchase_orders o
        LEFT JOIN order_items i ON i.order_id = o.id
        WHERE o.status = :status
        ORDER BY o.id, i.id
        """;

    return jdbc.query(
        sql,
        Map.of("status", status),
        rs -> {
            Map<Long, OrderAccumulator> orders = new LinkedHashMap<>();

            while (rs.next()) {
                Long orderId = rs.getObject("order_id", Long.class);

                OrderAccumulator order = orders.get(orderId);
                if (order == null) {
                    order = new OrderAccumulator(
                        orderId,
                        rs.getString("order_number"),
                        rs.getString("status")
                    );
                    orders.put(orderId, order);
                }

                order.addItem(rs);
            }

            return orders.values().stream()
                .map(OrderAccumulator::toResult)
                .toList();
        }
    );
}
```

`LinkedHashMap` được dùng để giữ thứ tự lần đầu các đơn xuất hiện trong ResultSet. Với `ORDER BY o.id, i.id`, danh sách kết quả sẽ giữ thứ tự đơn theo ID và các item theo ID.

Đây là ví dụ tổng quát hơn: một ResultSet chứa nhiều nhóm cha, mỗi nhóm có nhiều hàng con, và extractor trả về một `List<OrderDetails>`.

### 5.3. Vì sao không dùng List rồi tìm kiếm cha mỗi lần?

Nếu với mỗi hàng lại tìm object cha bằng cách duyệt toàn bộ danh sách, chi phí có thể tăng theo số hàng nhân số nhóm. Dùng `Map<Id, Accumulator>` cho phép tìm accumulator theo khóa, thường có chi phí trung bình gần O(1) cho mỗi hàng.

Map cũng giúp tránh tạo object cha mới mỗi lần đọc một dòng con của cùng đơn hàng.

## 6. Xử lý LEFT JOIN và giá trị NULL đúng cách

`LEFT JOIN` là lựa chọn thường gặp khi muốn giữ object cha kể cả khi không có object con.

Ví dụ đơn hàng không có dòng sản phẩm:

```text
order_id = 42
order_number = ORD-0042
status = NEW
item_id = NULL
product_code = NULL
quantity = NULL
unit_price = NULL
```

Extractor phải kiểm tra cột khóa của bảng con:

```java
Long itemId = rs.getObject("item_id", Long.class);

if (itemId != null) {
    // Có dòng con thật, tiến hành mapping.
}
```

Không nên kiểm tra `product_code != null` để quyết định item tồn tại, vì một cột nghiệp vụ có thể nullable trong schema. Primary key của bảng con là dấu hiệu đáng tin cậy hơn.

### 6.1. SQL NULL và primitive Java

Các phương thức đọc primitive như `getInt` và `getLong` trả giá trị mặc định khi cột SQL là NULL. Ví dụ `getInt` có thể trả 0. Nếu 0 là giá trị hợp lệ, phải gọi `wasNull()` để phân biệt:

```java
int quantityValue = rs.getInt("quantity");
Integer quantity = rs.wasNull() ? null : quantityValue;
```

Hoặc dùng `getObject` với kiểu wrapper nếu driver hỗ trợ:

```java
Integer quantity = rs.getObject("quantity", Integer.class);
```

Đối với `BigDecimal`, `getBigDecimal` trả `null` khi cột là SQL NULL. Không tự chuyển NULL thành 0 nếu domain cần phân biệt hai trạng thái.

### 6.2. Không tạo child giả từ hàng LEFT JOIN

Một lỗi phổ biến:

```java
// Sai nếu item_id có thể NULL:
items.add(new OrderItemView(
    rs.getLong("item_id"),
    rs.getString("product_code"),
    rs.getInt("quantity"),
    rs.getBigDecimal("unit_price")
));
```

Khi không có item, đoạn code có thể tạo object với ID 0, quantity 0 và các trường null. Kết quả sẽ thể hiện một dòng sản phẩm giả.

Hãy kiểm tra khóa chính child trước khi mapping như ví dụ accumulator.

## 7. Tránh tạo child trùng khi JOIN nhiều bảng

Một ResultSet có thể chứa nhiều hàng lặp lại cùng một child nếu query JOIN thêm một bảng con khác.

Ví dụ một đơn có 2 dòng sản phẩm và 3 ghi chú. Nếu JOIN đồng thời `order_items` và `order_notes`, kết quả có thể có 2 × 3 = 6 hàng cho đơn. Mỗi dòng sản phẩm xuất hiện lặp lại theo số ghi chú.

```sql
SELECT
    o.id AS order_id,
    i.id AS item_id,
    i.product_code,
    n.id AS note_id,
    n.note_text
FROM purchase_orders o
LEFT JOIN order_items i ON i.order_id = o.id
LEFT JOIN order_notes n ON n.order_id = o.id
WHERE o.id = :orderId;
```

Nếu chỉ gọi `items.add(...)` ở mỗi hàng, danh sách item sẽ chứa bản sao.

### 7.1. Dùng Map theo ID child

Có thể thay danh sách accumulator bằng map:

```java
private final Map<Long, OrderItemView> items = new LinkedHashMap<>();

void addItem(ResultSet rs) throws SQLException {
    Long itemId = rs.getObject("item_id", Long.class);

    if (itemId == null) {
        return;
    }

    items.putIfAbsent(
        itemId,
        new OrderItemView(
            itemId,
            rs.getString("product_code"),
            rs.getInt("quantity"),
            rs.getBigDecimal("unit_price")
        )
    );
}
```

`putIfAbsent` đảm bảo cùng một item ID chỉ được thêm một lần.

Tương tự, nếu gom notes, dùng map theo `note_id`. Khi hoàn thiện DTO, chuyển `items.values()` và `notes.values()` thành immutable lists.

### 7.2. Tổng hợp bảng con trước khi JOIN

Nếu mục tiêu chỉ cần tổng tiền và số ghi chú, thường tốt hơn khi tổng hợp từng bảng con trong subquery/CTE trước khi JOIN:

```sql
WITH item_summary AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS total_amount,
        COUNT(*) AS item_count
    FROM order_items
    GROUP BY order_id
),
note_summary AS (
    SELECT
        order_id,
        COUNT(*) AS note_count
    FROM order_notes
    GROUP BY order_id
)
SELECT
    o.id,
    o.order_number,
    COALESCE(i.total_amount, 0) AS total_amount,
    COALESCE(i.item_count, 0) AS item_count,
    COALESCE(n.note_count, 0) AS note_count
FROM purchase_orders o
LEFT JOIN item_summary i ON i.order_id = o.id
LEFT JOIN note_summary n ON n.order_id = o.id;
```

Mỗi subquery trả một hàng cho mỗi đơn, nên phép JOIN không nhân bản các item hoặc note. Cách này thường dễ đọc và tránh lỗi cộng trùng.

## 8. Mapping ResultSet thành DTO lồng nhau theo từng bước

Một extractor tốt thường tách rõ ba việc:

1. Xác định object cha tương ứng với hàng hiện tại.
2. Xác định hàng có chứa object con thật hay không.
3. Thêm hoặc cập nhật object con trong accumulator.

Mẫu logic:

```java
ResultSetExtractor<List<OrderDetails>> extractor = rs -> {
    Map<Long, OrderAccumulator> groups = new LinkedHashMap<>();

    while (rs.next()) {
        Long orderId = rs.getObject("order_id", Long.class);

        OrderAccumulator parent = groups.get(orderId);
        if (parent == null) {
            parent = new OrderAccumulator(
                orderId,
                rs.getString("order_number"),
                rs.getString("status")
            );
            groups.put(orderId, parent);
        }

        parent.addItem(rs);
    }

    return groups.values().stream()
        .map(OrderAccumulator::toResult)
        .toList();
};
```

Cách viết tường minh giúp xử lý checked exception từ ResultSet dễ dàng và làm rõ thời điểm khởi tạo object cha.

### 8.1. Giữ thứ tự dữ liệu

Nếu thứ tự item có ý nghĩa, SQL cần `ORDER BY` phù hợp:

```sql
ORDER BY o.id, i.position, i.id;
```

`LinkedHashMap` và `List` giữ thứ tự nhận được từ ResultSet. Nhưng chúng không tự sắp xếp theo nghiệp vụ nếu query không có ORDER BY. Không dựa vào thứ tự vật lý của hàng trong bảng.

### 8.2. Không SELECT * trong mapping phức tạp

Với nhiều bảng cùng có cột `id`, `status` hoặc `created_at`, `SELECT *` dễ tạo tên cột mơ hồ. Hãy chọn rõ cột và alias:

```sql
SELECT
    o.id AS order_id,
    o.status AS order_status,
    i.id AS item_id,
    i.status AS item_status
...
```

Alias rõ ràng làm mapping trong Java ít nhầm và ít phụ thuộc vào thứ tự cột.

## 9. ResultSetExtractor trong NamedParameterJdbcTemplate

`NamedParameterJdbcTemplate` có overload nhận `ResultSetExtractor<T>`:

```java
<T> T query(
    String sql,
    SqlParameterSource paramSource,
    ResultSetExtractor<T> rse
);
```

Ví dụ:

```java
MapSqlParameterSource parameters =
    new MapSqlParameterSource("orderId", 42L);

OrderDetails details = jdbc.query(
    sql,
    parameters,
    extractor
);
```

Named parameters như `:orderId` được bind thành tham số JDBC phù hợp. Không nối trực tiếp ID hoặc giá trị request vào chuỗi SQL.

Nếu dùng `JdbcTemplate` positional parameters, truyền giá trị theo thứ tự dấu `?`:

```java
OrderDetails details = jdbcTemplate.query(
    sql,
    new Object[] { 42L },
    extractor
);
```

Chữ ký overload cụ thể của `JdbcTemplate` có thể thay đổi/deprecate giữa các phiên bản Spring Framework. Với code mới, dùng overload được khuyến nghị trong phiên bản đang dùng; nguyên tắc quan trọng là extractor nhận ResultSet do template quản lý.

### 9.1. Có thể dùng lambda thay cho class riêng

Vì `ResultSetExtractor<T>` là functional interface, lambda thường đủ rõ:

```java
ResultSetExtractor<OrderDetails> extractor = rs -> {
    // Duyệt toàn bộ ResultSet và trả một OrderDetails.
};
```

Nếu logic mapping dài, tạo một class riêng implement `ResultSetExtractor<T>` hoặc tách mapper/accumulator thành các lớp nhỏ. Không nên để một method repository quá dài với nhiều nhánh mapping không liên quan.

## 10. ResultSetExtractor không tự quản lý aggregate lifecycle

`ResultSetExtractor` là callback của **Spring JDBC**, không phải API lưu aggregate của Spring Data JDBC.

Nó giúp chạy SQL đọc, duyệt toàn bộ ResultSet, gom các hàng và tạo DTO/read model hoặc object kết quả do ứng dụng định nghĩa.

Nó không tự động:

- Áp dụng lifecycle callbacks của `JdbcAggregateTemplate`.
- Kiểm tra newness hoặc version của aggregate.
- Lưu aggregate và entity con theo quy tắc Spring Data JDBC.
- Theo dõi thay đổi object sau khi trả về.
- Tạo một persistence context hoặc lazy-loading proxy.

Nếu kết quả chỉ phục vụ đọc, DTO từ `ResultSetExtractor` là lựa chọn tự nhiên. Nếu cần cập nhật domain, tải aggregate bằng repository/aggregate operations theo mapping thích hợp rồi thực hiện thao tác ghi tường minh.

## 11. Phân trang khi gom nhiều hàng

Khi một query JOIN trả nhiều hàng cho mỗi object cha, không nên áp dụng `LIMIT/OFFSET` trực tiếp lên toàn bộ hàng JOIN nếu mục tiêu là phân trang theo object cha.

Ví dụ một đơn có 5 item. Nếu query JOIN giới hạn 10 hàng, 10 hàng đó có thể chỉ đại diện cho 2 đơn hoặc một phần item của đơn thứ hai. Kết quả gom sẽ không phải hai aggregate đầy đủ.

### 11.1. Phân trang ID cha trước

```sql
WITH page_orders AS (
    SELECT id
    FROM purchase_orders
    WHERE status = :status
    ORDER BY id DESC
    LIMIT :limit OFFSET :offset
)
SELECT
    o.id AS order_id,
    o.order_number,
    o.status,
    i.id AS item_id,
    i.product_code,
    i.quantity,
    i.unit_price
FROM page_orders p
JOIN purchase_orders o ON o.id = p.id
LEFT JOIN order_items i ON i.order_id = o.id
ORDER BY o.id DESC, i.id;
```

CTE `page_orders` chọn đúng tập đơn cần phân trang. Sau đó truy vấn lấy tất cả item của những đơn đó. Extractor có thể gom các hàng thành DTO cha/con mà không cắt bớt child ở cuối trang.

Cú pháp CTE và LIMIT/OFFSET phụ thuộc database dialect; hãy dùng dạng phù hợp với hệ quản trị của ứng dụng.

### 11.2. Count theo object cha

Nếu giao diện cần tổng số đơn, count query phải đếm đơn phù hợp:

```sql
SELECT COUNT(*)
FROM purchase_orders
WHERE status = :status;
```

Nếu filter dựa trên bảng con và JOIN làm nhân bản đơn, dùng `COUNT(DISTINCT o.id)` hoặc `EXISTS` để đếm root duy nhất.

### 11.3. Tổng số trang

Với `totalElements` và `pageSize`:

```java
long totalPages = totalElements / pageSize
    + (totalElements % pageSize == 0 ? 0 : 1);
```

Đảm bảo `pageSize > 0` trước khi tính. Nếu không cần tổng số, có thể lấy thêm một ID cha để xác định có trang tiếp theo thay vì chạy count.

## 12. Quản lý bộ nhớ và tập kết quả lớn

`ResultSetExtractor` thường gom kết quả vào các collection trong bộ nhớ. Nếu query trả về hàng trăm nghìn object, bộ nhớ cần thiết có thể lớn.

Trước khi dùng extractor để tạo một danh sách rất lớn, hãy xem xét:

- Thêm filter để giảm tập kết quả.
- Phân trang theo root.
- Chỉ SELECT các cột cần thiết.
- Dùng batch processing nếu có thể xử lý theo từng phần.
- Dùng `RowCallbackHandler` nếu chỉ cần xử lý từng hàng và không cần giữ toàn bộ kết quả.
- Dùng cơ chế streaming của Spring JDBC khi thật sự cần, đồng thời đóng stream đúng cách và giữ connection/transaction trong phạm vi tiêu thụ stream.

Không nên xem `ResultSetExtractor` là cơ chế streaming tự động. Callback thường cần giữ accumulator/collection để trả về kết quả cuối cùng; lượng dữ liệu giữ trong bộ nhớ phụ thuộc cấu trúc mà ứng dụng xây dựng.

## 13. Xử lý lỗi và tài nguyên JDBC

`ResultSetExtractor` chạy trong phạm vi quản lý của Spring JDBC template. Template chịu trách nhiệm quản lý các tài nguyên JDBC được tạo cho truy vấn, bao gồm statement và result set.

Trong extractor:

- Không tự đóng `ResultSet`.
- Không lưu ResultSet vào field để dùng sau khi callback hoàn tất.
- Không trả về `ResultSet` hoặc object phụ thuộc vào cursor.
- Chuyển các giá trị cần thiết thành object Java ngay trong callback.
- Để exception SQL được Spring dịch sang hệ exception truy cập dữ liệu phù hợp.

Ví dụ không nên làm:

```java
ResultSet savedResultSet = jdbc.query(
    sql,
    parameters,
    rs -> rs
);
```

Sau khi template hoàn tất truy vấn, ResultSet không còn là tài nguyên hợp lệ để service sử dụng.

Thay vào đó, trả về DTO/list đã map. Nếu mapping phát sinh lỗi, exception được truyền qua cơ chế xử lý của Spring JDBC và tài nguyên query vẫn được template quản lý.

## 14. Kiểm thử ResultSetExtractor

Một bộ kiểm thử nên xác nhận cả cấu trúc cha lẫn collection con.

| Dữ liệu SQL | Kết quả mong đợi |
|---|---|
| Đơn không tồn tại | `Optional.empty()` |
| Đơn có một item | Một DTO cha, một item |
| Đơn có nhiều item | Một DTO cha, danh sách item đầy đủ |
| Đơn không có item với LEFT JOIN | DTO cha tồn tại, danh sách rỗng |
| Nhiều đơn trong query | Mỗi ID cha có đúng một DTO |
| JOIN tạo hàng lặp item | Mỗi item ID chỉ xuất hiện một lần nếu dùng dedup map |
| Cột child nullable | Không tạo child giả từ NULL |
| Nhiều hàng cùng sort key | ORDER BY có tie-breaker giữ thứ tự xác định |

### 14.1. Ví dụ kiểm thử một đơn có nhiều item

```java
@DataJdbcTest
class OrderDetailsReadRepositoryTest {

    @Autowired
    OrderDetailsReadRepository repository;

    @Test
    void groupsRowsIntoOneOrderWithItsItems() {
        // Arrange: tạo order 42 và hai order_items trong database test.

        Optional<OrderDetails> result = repository.findById(42L);

        assertThat(result).isPresent();
        assertThat(result.get().items()).hasSize(2);
        assertThat(result.get().items())
            .extracting(OrderItemView::productCode)
            .containsExactly("KB-01", "MS-02");
    }
}
```

Đoạn test là khung minh họa; cần bổ sung SQL fixture hoặc repository setup tương ứng với schema test của dự án. Với custom JDBC query, nên dùng database/dialect phù hợp với production khi query phụ thuộc cú pháp cụ thể.

### 14.2. Kiểm thử đơn không có item

Vì query dùng `LEFT JOIN`, đơn không có dòng con vẫn được đọc:

```java
Optional<OrderDetails> result = repository.findById(orderWithoutItems);

assertThat(result).isPresent();
assertThat(result.get().items()).isEmpty();
```

Test này đặc biệt quan trọng để phát hiện lỗi tạo child giả từ các cột NULL.

## 15. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
|---|---|---|
| Một đơn xuất hiện thành nhiều object cha | Mỗi hàng JOIN được map độc lập | Gom theo parent ID bằng Map |
| Danh sách item có item giả với ID 0 | Dùng `getLong` mà không kiểm tra SQL NULL | Dùng `getObject` wrapper hoặc `wasNull()` |
| Item bị lặp | JOIN nhiều bảng con làm nhân bản hàng | Deduplicate theo child ID hoặc tổng hợp trước khi JOIN |
| Đơn không có item bị mất | Dùng INNER JOIN | Dùng LEFT JOIN nếu cần giữ parent |
| Danh sách item sai thứ tự | SQL không có ORDER BY phù hợp | Sắp xếp theo position/ID |
| Extractor giữ tài nguyên không hợp lệ | Trả ResultSet ra ngoài callback | Map thành DTO trước khi callback kết thúc |
| Bộ nhớ tăng cao | Gom tập dữ liệu quá lớn vào collection | Filter, phân trang root hoặc xử lý theo batch |
| Page cuối thiếu item | LIMIT/OFFSET áp dụng lên hàng JOIN | Phân trang parent ID trước rồi JOIN child |
| Tổng số đơn bị nhân lên | COUNT trên JOIN một-nhiều | COUNT(DISTINCT parent.id) hoặc EXISTS |
| DTO đọc bị thiếu cột | SQL không chọn đủ cột mapper cần | Chọn rõ và alias đủ các cột |
| SQL lỗi khi đổi database | Query phụ thuộc dialect | Dùng cú pháp đúng hệ quản trị và integration test |
| Dùng ResultSetExtractor để cập nhật aggregate | Nhầm read mapping với aggregate persistence | Dùng repository/aggregate operations cho thao tác ghi |

## 16. Bài thực hành

Giả sử một đơn hàng có nhiều dòng sản phẩm và ứng dụng muốn trả về một `OrderDetails` có danh sách `OrderItemView`.

**Bài 1.** Khi dùng `RowMapper` cho query JOIN, một hàng SQL thường tạo ra bao nhiêu object?

*Đáp án:* Một object cho mỗi hàng. Nếu một đơn có ba item, query JOIN có thể tạo ba object hàng riêng biệt.

**Bài 2.** `ResultSetExtractor<T>` khác `RowMapper<T>` ở đâu?

*Đáp án:* `RowMapper` xử lý từng hàng và trả một object cho hàng đó; `ResultSetExtractor` nhận toàn ResultSet và tự tạo một kết quả tổng hợp `T`.

**Bài 3.** Vì sao dùng `LEFT JOIN` khi đọc đơn có thể chưa có item?

*Đáp án:* Để đơn vẫn xuất hiện. Các cột phía bảng item là NULL; extractor kiểm tra khóa chính item và trả danh sách rỗng.

**Bài 4.** Vì sao cần Map theo ID cha?

*Đáp án:* Để nhận ra các hàng liên tiếp thuộc cùng một đơn và chỉ tạo một accumulator/object cha cho mỗi ID.

**Bài 5.** JOIN hai bảng con độc lập có thể làm gì với danh sách item?

*Đáp án:* Tạo hàng trung gian lặp lại item theo số hàng của bảng con còn lại. Dùng map khử trùng lặp theo ID hoặc tổng hợp bảng con trước khi JOIN.

**Bài 6.** Vì sao không LIMIT trực tiếp hàng JOIN nếu muốn lấy 20 đơn?

*Đáp án:* Một đơn có thể tạo nhiều hàng. LIMIT 20 giới hạn hàng JOIN, không phải 20 đơn. Hãy phân trang ID đơn trước.

**Bài 7.** Có nên trả ResultSet từ extractor cho controller?

*Đáp án:* Không. ResultSet phụ thuộc statement/connection và chỉ hợp lệ trong phạm vi tài nguyên JDBC. Hãy map thành DTO trước khi callback kết thúc.

## 17. Điều cần ghi nhớ

- **`ResultSetExtractor<T>`** nhận toàn bộ ResultSet và trả về một kết quả do ứng dụng định nghĩa.
- Dùng nó khi nhiều hàng SQL cần được gom thành một DTO cha có collection con hoặc một cấu trúc tổng hợp.
- **`RowMapper`** phù hợp khi mỗi hàng là một object độc lập; **`RowCallbackHandler`** phù hợp khi xử lý từng hàng bằng side effect.
- Dùng Map theo parent ID để chỉ tạo một object cha cho mỗi nhóm hàng.
- Với `LEFT JOIN`, kiểm tra khóa chính child để không tạo object con giả từ SQL NULL.
- Nếu JOIN nhiều bảng con, deduplicate theo ID hoặc tổng hợp từng bảng trước khi JOIN để tránh nhân bản hàng.
- SQL cần ORDER BY rõ ràng nếu thứ tự collection có ý nghĩa.
- Phân trang theo parent root trước khi JOIN child nếu mục tiêu là một trang gồm các object cha hoàn chỉnh.
- ResultSetExtractor là cơ chế đọc của Spring JDBC; nó không thay thế aggregate lifecycle hoặc API ghi của Spring Data JDBC.
- Không giữ ResultSet/Statement/Connection sau khi callback kết thúc; map dữ liệu thành object Java trong phạm vi template quản lý tài nguyên.

### Tài liệu tham khảo

- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): cách sử dụng JdbcTemplate, NamedParameterJdbcTemplate và các callback mapping.
- [Spring Framework — ResultSetExtractor API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/ResultSetExtractor.html): hợp đồng callback xử lý toàn bộ ResultSet.
- [Spring Framework — RowMapper API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/RowMapper.html): ánh xạ từng hàng thành một object.
- [Spring Framework — RowCallbackHandler API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/RowCallbackHandler.html): xử lý từng hàng mà không trả object từ callback.
- [Spring Data Relational — JDBC Reference](https://docs.spring.io/spring-data/relational/reference/jdbc.html): repository, aggregate mapping và hạ tầng Spring Data JDBC.

Khi triển khai, hãy chọn callback theo hình dạng kết quả cần tạo. Nếu SQL trả nhiều hàng cho một object cha, gom theo khóa cha và kiểm tra khóa con; nếu chỉ cần từng hàng độc lập, RowMapper đơn giản hơn.
