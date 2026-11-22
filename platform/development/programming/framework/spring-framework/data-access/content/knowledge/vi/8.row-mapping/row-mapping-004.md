# ResultSetExtractor xử lý toàn bộ tập kết quả

## 1. Vấn đề: một hàng SQL không phải lúc nào cũng là một đối tượng kết quả

Trong Spring Framework, `JdbcTemplate` giúp ứng dụng thực hiện SQL qua JDBC mà không phải lặp lại mọi bước tạo `Statement`, duyệt kết quả, đóng tài nguyên và dịch ngoại lệ. Khi cần ánh xạ kết quả, cách phổ biến là dùng `RowMapper<T>`: mỗi hàng của `ResultSet` thành một đối tượng `T`.

Nhưng nhiều yêu cầu cần **nhìn toàn bộ các hàng cùng lúc**:

- Gom nhiều hàng của phép `JOIN` thành một đối tượng cha kèm danh sách con.
- Tạo một `Map` tra cứu, một cấu trúc cây, danh sách có nhóm hoặc một đối tượng thống kê.
- Duyệt tập kết quả để quyết định trạng thái tổng thể dựa trên nhiều hàng.
- Kiểm tra điều kiện nhất quán giữa các hàng, hoặc kết hợp các giá trị liên quan.
- Xử lý tuần tự mà không bắt buộc trả `List` chứa một phần tử cho mỗi hàng.

Đó là vai trò của **`ResultSetExtractor<T>`**, callback mà `JdbcTemplate` gọi để chuyển **toàn bộ `ResultSet` của một truy vấn** thành **một kết quả Java tùy ý `T`**.

Ví dụ, với phép `LEFT JOIN`, ba khách hàng và ba đơn hàng có thể tạo **bốn hàng SQL**, nhưng kết quả mong muốn lại là **ba đối tượng khách hàng**, mỗi khách hàng có danh sách đơn hàng riêng. `RowMapper<Customer>` áp dụng độc lập cho từng hàng không tự động gom các hàng cùng khóa cha. `ResultSetExtractor` cho phép tạo một cấu trúc dùng chung trong suốt quá trình duyệt và kết thúc bằng kết quả đã gom.

**Tư tưởng chính:** `RowMapper` hỏi “hàng này thành đối tượng gì?”, còn `ResultSetExtractor` hỏi “cả tập hàng này thành một kết quả gì?”.

## 2. Hợp đồng API và trình tự thực thi

Giao diện thuộc `org.springframework.jdbc.core`:

```java
@FunctionalInterface
public interface ResultSetExtractor<T> {
    T extractData(ResultSet rs) throws SQLException, DataAccessException;
}
```

Đây là chữ ký rút gọn để học: mã nguồn thực tế có thể có annotation nullability, generic bound và Javadoc tùy phiên bản Spring. Các kiểu `SQLException` và `ResultSet` thuộc `java.sql`, `DataAccessException` thuộc `org.springframework.dao`.

- **`T`:** kiểu kết quả tổng thể muốn trả, ví dụ `List<CustomerView>`, `Map<Long, CustomerView>`, `Summary`, `Integer` hoặc `Optional<T>`.
- **`rs`:** kết quả của truy vấn đang thực thi, do `JdbcTemplate` sở hữu; khi callback bắt đầu, con trỏ thường ở **trước hàng đầu tiên** đối với `ResultSet` forward-only thông thường.
- **`extractData`:** tự gọi `rs.next()` để di chuyển con trỏ, đọc các cột và trả về giá trị cuối cùng. Callback có thể trả `null` theo hợp đồng, nhưng nên chọn một quy ước nhất quán, chẳng hạn danh sách rỗng nếu không có hàng.
- **Ngoại lệ:** thao tác JDBC có thể ném `SQLException`; `JdbcTemplate` xử lý và dịch thành ngoại lệ `DataAccessException` khi phù hợp. Không cần bắt `SQLException` chỉ để trả danh sách rỗng.
- **Tài nguyên:** callback **không được đóng `ResultSet` do `JdbcTemplate` cung cấp** và không được đóng `Connection` của template. Template phụ trách vòng đời tài nguyên thuộc truy vấn.

Luồng khái niệm:

```text
repository gọi jdbcTemplate.query(sql, extractor, args...)
                        |
                        v
              lấy Connection phù hợp
                        |
                        v
              tạo PreparedStatement
                        |
                        v
                  bind tham số
                        |
                        v
                 executeQuery()
                        |
                        v
              extractor.extractData(rs)
                        |
                        +--> rs.next() -> đọc hàng 1
                        +--> rs.next() -> đọc hàng 2
                        +--> ...
                        +--> trả một kết quả T
                        |
                        v
         JdbcTemplate đóng ResultSet/Statement
         và giải phóng Connection đúng ngữ cảnh
                        |
                        v
                 bên gọi nhận T
```

Thông thường, **một invocation của `query` tương ứng một lần gọi `extractData`** trên `ResultSet` của truy vấn đó; callback tự duyệt 0, 1 hoặc nhiều hàng. Đây không phải callback mỗi hàng. Nếu truy vấn không trả hàng nào, `extractData` vẫn nhận `ResultSet` rỗng và có thể trả danh sách rỗng.

## 3. So sánh RowMapper, RowCallbackHandler và ResultSetExtractor

| Tiêu chí | `RowMapper<T>` | `RowCallbackHandler` | `ResultSetExtractor<T>` |
| --- | --- | --- | --- |
| Phương thức | `mapRow(rs, rowNum)` | `processRow(rs)` | `extractData(rs)` |
| Một callback xử lý | **Một hàng** | **Một hàng** | **Cả tập kết quả** |
| Ai gọi `rs.next()`? | `JdbcTemplate` | `JdbcTemplate` | **Chính extractor** |
| Callback trả về | Một `T` cho hàng đó | `void` | Một `T` cho toàn bộ tập |
| Thường dùng | `List<T>`, DTO/record đơn giản | Tác vụ/thu thập theo hàng | Nhóm cha–con, `Map`, cây, thống kê tùy ý |
| Khi rỗng | `query(...mapper)` trả `List` rỗng | Handler không được gọi cho hàng nào | Extractor tự quyết định trả gì |
| Lưu trạng thái | Thường stateless | Có thể dùng trạng thái phạm vi lời gọi | Nên tạo state bên trong `extractData` |

**Quy tắc con trỏ quan trọng:** không gọi `rs.next()` trong `RowMapper` hoặc `RowCallbackHandler` vì Spring đã đặt con trỏ vào hàng hiện tại. Ngược lại, **phải tự gọi `rs.next()` trong `ResultSetExtractor`** nếu muốn đọc hàng dữ liệu.

`JdbcTemplate` có sẵn `RowMapperResultSetExtractor<T>`, một adapter dùng `RowMapper<T>` để gom kết quả thành `List<T>`. Điều này cho thấy về mặt cơ chế `ResultSetExtractor` có thể tạo danh sách, nhưng nếu bài toán thực sự là “một hàng thành một đối tượng”, **`RowMapper` vẫn là lựa chọn ngắn và rõ hơn**.

Không nên mặc định `ResultSetExtractor` là “nâng cấp luôn tốt hơn RowMapper”. Sức mạnh của nó đi kèm trách nhiệm kiểm soát duyệt, trạng thái tạm, tránh trùng và quy ước trả kết quả.

## 4. Dữ liệu mẫu: JOIN làm nhân số hàng

Xét hệ thống khách hàng và đơn hàng. Một khách hàng có thể chưa có đơn.

Schema SQL ví dụ dùng H2/PostgreSQL với kiểu `BOOLEAN` và `DECIMAL`:

```sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    active BOOLEAN NOT NULL
);

CREATE TABLE customer_order (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customer(id),
    amount DECIMAL(12, 2) NOT NULL
);

INSERT INTO customer (id, name, active) VALUES
    (1, 'Lan',  TRUE),
    (2, 'Minh', TRUE),
    (3, 'Vy',   TRUE);

INSERT INTO customer_order (id, customer_id, amount) VALUES
    (101, 1, 120.00),
    (102, 1,  80.00),
    (103, 2,  50.00);
```

Truy vấn:

```sql
SELECT
    c.id     AS customer_id,
    c.name   AS customer_name,
    o.id     AS order_id,
    o.amount AS order_amount
FROM customer c
LEFT JOIN customer_order o ON o.customer_id = c.id
WHERE c.active = ?
ORDER BY c.id, o.id;
```

Khi bind `true` cho tham số `?`, các hàng trả về là:

| customer_id | customer_name | order_id | order_amount |
| ---: | --- | ---: | ---: |
| 1 | Lan | 101 | 120.00 |
| 1 | Lan | 102 | 80.00 |
| 2 | Minh | 103 | 50.00 |
| 3 | Vy | `NULL` | `NULL` |

Có **4 hàng kết quả SQL**, vì khách hàng Lan có **2 đơn**. Khách hàng Vy vẫn có một hàng nhờ `LEFT JOIN`, nhưng cột đơn hàng là `NULL`.

Mục tiêu của bài toán ánh xạ lại là:

```text
[
  CustomerView(id=1, name=Lan,  orders=[101, 102]),
  CustomerView(id=2, name=Minh, orders=[103]),
  CustomerView(id=3, name=Vy,   orders=[])
]
```

**Không được nhầm “nhiều hàng SQL cùng customer_id” với dữ liệu khách hàng bị lưu trùng.** Đây là đặc trưng của quan hệ 1–N khi hiển thị dưới dạng bảng phẳng.

## 5. Tư duy xử lý toàn tập: từ các hàng phẳng sang nhóm cha–con

Một thuật toán đơn giản:

1. Khởi tạo `LinkedHashMap<Long, MutableCustomer>`: khóa là ID khách hàng, giá trị là bộ gom tạm.
2. `while (rs.next())`: đọc khóa khách hàng của hàng hiện tại.
3. Nếu khóa chưa có trong map, tạo bộ gom khách hàng mới; nếu đã có thì dùng lại.
4. Đọc `order_id`. Nếu không phải SQL `NULL`, thêm đơn hàng vào danh sách của bộ gom.
5. Sau khi hết tập kết quả, chuyển các bộ gom thành các đối tượng trả về, dùng `List.copyOf(...)` để không trả ra danh sách mutable nội bộ.

Pseudo-code:

```text
byCustomer = ordered map
while ResultSet.next():
    customerId = get customer_id
    bucket = byCustomer.get(customerId)
    if bucket is absent:
        bucket = new bucket(customerId, customerName)
        byCustomer.put(customerId, bucket)

    orderId = get order_id
    if orderId is NOT SQL NULL:
        bucket.orders.add(orderId, orderAmount)

result = []
for bucket in byCustomer.values():
    result.add(immutable snapshot of bucket)
return result
```

`LinkedHashMap` giữ **thứ tự xuất hiện** của khóa trong quá trình duyệt. Câu `ORDER BY c.id, o.id` trong SQL làm thứ tự xuất hiện **có thể dự đoán**: khách hàng theo ID, đơn hàng theo ID. Không dựa vào thứ tự tự nhiên của DB khi SQL không có `ORDER BY`.

Số lượng đầu ra sẽ là ba khách hàng, không phải bốn dòng SQL. Nếu không có khách hàng phù hợp, map rỗng và kết quả là `List.of()`/danh sách rỗng, không phải một đối tượng “rỗng giả” đại diện cho khách hàng không tồn tại.

## 6. Ví dụ Spring JDBC đầy đủ: một ResultSetExtractor dựng danh sách cha–con

Lớp sau dành cho **ứng dụng Spring đã cấu hình `JdbcTemplate`/`DataSource` và đã tạo schema ở mục 4**. Đây là mã tích hợp Spring; không phải chương trình độc lập biên dịch chỉ với JDK.

Tệp `CustomerOrderRepository.java`:

```java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.PreparedStatementSetter;
import org.springframework.jdbc.core.ResultSetExtractor;
import org.springframework.stereotype.Repository;

@Repository
public final class CustomerOrderRepository {
    private static final String SQL = """
        SELECT
            c.id     AS customer_id,
            c.name   AS customer_name,
            o.id     AS order_id,
            o.amount AS order_amount
        FROM customer c
        LEFT JOIN customer_order o ON o.customer_id = c.id
        WHERE c.active = ?
        ORDER BY c.id, o.id
        """;

    private final JdbcTemplate jdbc;

    public CustomerOrderRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public record OrderView(long id, BigDecimal amount) {}

    public record CustomerView(
        long id, String name, List<OrderView> orders
    ) {}

    private static final class MutableCustomer {
        final long id;
        final String name;
        final List<OrderView> orders = new ArrayList<>();

        MutableCustomer(long id, String name) {
            this.id = id;
            this.name = name;
        }
    }

    public List<CustomerView> findActiveWithOrders() {
        ResultSetExtractor<List<CustomerView>> extractor = rs -> {
            Map<Long, MutableCustomer> byId = new LinkedHashMap<>();

            // Với ResultSetExtractor, CHÍNH callback di chuyển con trỏ.
            while (rs.next()) {
                long customerId = rs.getLong("customer_id");

                MutableCustomer customer = byId.get(customerId);
                if (customer == null) {
                    customer = new MutableCustomer(
                        customerId,
                        rs.getString("customer_name")
                    );
                    byId.put(customerId, customer);
                }

                // LEFT JOIN: order_id có thể là SQL NULL.
                long orderId = rs.getLong("order_id");
                boolean orderExists = !rs.wasNull();
                if (orderExists) {
                    customer.orders.add(new OrderView(
                        orderId,
                        rs.getBigDecimal("order_amount")
                    ));
                }
            }

            // Không để lộ danh sách mutable của bộ gom ra bên ngoài.
            List<CustomerView> result = new ArrayList<>();
            for (MutableCustomer customer : byId.values()) {
                result.add(new CustomerView(
                    customer.id,
                    customer.name,
                    List.copyOf(customer.orders)
                ));
            }
            return result;
        };

        PreparedStatementSetter activeOnly =
            ps -> ps.setBoolean(1, true);

        return jdbc.query(SQL, activeOnly, extractor);
    }
}
```

### Phân tích từng điểm dễ sai

**a. Vì sao cần `while (rs.next())`?**  
Vì `extractData` nhận toàn tập và tự duyệt. Nếu gọi `rs.getLong(...)` ngay khi con trỏ còn ở vị trí trước hàng đầu tiên, JDBC có thể ném `SQLException` vì chưa có hàng hiện tại.

**b. Vì sao dùng `Map<Long, MutableCustomer>`?**  
Cùng `customer_id=1` xuất hiện ở hai hàng. Map bảo đảm cùng một bộ gom nhận cả đơn 101 và 102; nếu mỗi lần tạo một khách hàng mới thì sẽ sinh hai đối tượng Lan.

**c. Tại sao cần `wasNull()` ngay sau `getLong("order_id")`?**  
`ResultSet.getLong` trả `0` khi giá trị SQL là `NULL` và yêu cầu gọi `wasNull()` để phân biệt. Dùng `orderId != 0` để suy đoán `NULL` là sai tổng quát vì ID 0 có thể hợp lệ trong một schema. Phải kiểm tra `wasNull()` **trước khi gọi một getter khác** có thể thay đổi trạng thái “cột vừa đọc có NULL hay không”.

**d. Tại sao không đóng `rs` hoặc `Connection`?**  
`JdbcTemplate` sở hữu chúng. Sau khi callback trả về hoặc ném ngoại lệ, template giải phóng tài nguyên theo đúng ngữ cảnh giao dịch. Nếu tự `rs.close()` hoặc `connection.close()` trong extractor, có thể phá vỡ tiến trình JDBC và ranh giới giao dịch.

**e. Nếu DB không trả hàng nào?**  
Vòng lặp không chạy; map rỗng và kết quả là một `List<CustomerView>` rỗng. Đây là quy ước rõ ràng, dễ dùng hơn trả `null` cho tình huống không có dữ liệu.

**f. Kết quả với dữ liệu mẫu?**  
Ba đối tượng: Lan có đơn 101, 102; Minh có đơn 103; Vy có danh sách đơn rỗng. Các số tiền được đọc bằng `BigDecimal` để giữ ngữ nghĩa thập phân của cột `DECIMAL`.

**g. Callback có thể tái sử dụng an toàn giữa các request?**  
Ở ví dụ trên, mọi map và danh sách gom được tạo **bên trong `extractData`**, nên không có state của request cũ bị giữ trong singleton repository. Một extractor stateless có thể được tái sử dụng; không nên để `Map` mutable dùng chung làm trường của bean singleton mà không có yêu cầu và cơ chế đồng bộ rõ ràng.

## 7. Biến thể gọn: truyền extractor trực tiếp cho JdbcTemplate

Nếu logic không quá dài, có thể truyền lambda với kiểu rõ ràng:

```java
ResultSetExtractor<List<String>> extractor = rs -> {
    List<String> names = new ArrayList<>();
    while (rs.next()) {
        names.add(rs.getString("customer_name"));
    }
    return names;
};

List<String> names = jdbcTemplate.query(
    """
    SELECT name AS customer_name
    FROM customer
    WHERE active = ?
    ORDER BY id
    """,
    (PreparedStatementSetter) ps -> ps.setBoolean(1, true),
    extractor
);
```

Đoạn này minh họa API và cần các import phù hợp (`ArrayList`, `List`, `ResultSetExtractor`, `PreparedStatementSetter`). Nhưng với yêu cầu đơn giản trên, **dùng `RowMapper` còn rõ hơn**:

```java
List<String> names = jdbcTemplate.query(
    "SELECT name FROM customer WHERE active = ? ORDER BY id",
    (rs, rowNum) -> rs.getString("name"),
    true
);
```

Cả hai có thể tạo danh sách `["Lan", "Minh", "Vy"]` với dữ liệu mẫu. Chọn `ResultSetExtractor` khi bài toán thật sự cần **trạng thái xuyên nhiều hàng**, không phải chỉ vì API có thể làm mọi việc.

Các overload quan trọng của `JdbcTemplate` gồm:

```java
<T> T query(String sql, ResultSetExtractor<T> extractor);
<T> T query(String sql, ResultSetExtractor<T> extractor,
            Object... args);
<T> T query(String sql, PreparedStatementSetter setter,
            ResultSetExtractor<T> extractor);
<T> T query(PreparedStatementCreator creator,
            ResultSetExtractor<T> extractor);
```

Đây là chữ ký giản lược để so sánh, không phải mã khai báo trực tiếp trong ứng dụng. Với SQL chứa `?`, cần cung cấp tham số theo overload tương ứng. Trong một vài ngữ cảnh, **gán kiểu rõ cho biến extractor** giúp Java chọn đúng overload và tránh nhập nhằng lambda.

## 8. ResultSetExtractor trả về được những gì?

Khi `T` là **kết quả của cả tập**, cấu trúc trả về tùy yêu cầu:

| Kiểu `T` | Ví dụ sử dụng | Cần cẩn thận |
| --- | --- | --- |
| `List<CustomerView>` | Gom cha–con theo khóa chính | Tránh tạo trùng cha và phân biệt con `NULL` |
| `Map<Long, CustomerView>` | Tra cứu đối tượng theo ID | Chọn cách xử lý khóa trùng, thứ tự map |
| `Map<String, List<Item>>` | Nhóm theo trạng thái/nhãn | Chuẩn hóa khóa nếu cần; tránh state toàn cục |
| `Summary` (record) | Tính tổng hợp nhiều đại lượng cùng lúc | Tránh cộng trùng do SQL `JOIN` nhân hàng |
| `Optional<Account>` | Trả 0 hoặc 1 kết quả theo hợp đồng ứng dụng | Quyết định xử lý nếu SQL trả nhiều hàng |
| `Integer` / `Long` | Bộ đếm hoặc điều kiện trên toàn tập | Nếu chỉ cần `COUNT(*)`, để DB tổng hợp thường tốt hơn |
| `null` | Kết quả đặc biệt theo hợp đồng | Dễ khiến caller phải xử lý null; nên cân nhắc loại trả rõ ràng |

`ResultSetExtractor` **không ép callback phải trả danh sách**, không ép phải duyệt hết tất cả hàng nếu đã đáp ứng mục tiêu và không ép phải xử lý từng hàng như một đối tượng riêng. Tuy nhiên nếu muốn kết quả “toàn bộ tập”, phải chủ động duyệt hết những hàng liên quan; việc trả sớm cũng có thể bỏ qua dữ liệu cần thiết và không phù hợp yêu cầu.

### Ví dụ trả một Map đếm theo trạng thái

Với bảng `customer`, nếu muốn ánh xạ các hàng vào bộ đếm (mã minh họa trong ứng dụng Spring):

```java
ResultSetExtractor<Map<String, Integer>> extractor = rs -> {
    Map<String, Integer> counts = new LinkedHashMap<>();
    while (rs.next()) {
        String status = rs.getBoolean("active")
            ? "ACTIVE" : "INACTIVE";
        counts.merge(status, 1, Integer::sum);
    }
    return counts;
};

Map<String, Integer> counts = jdbcTemplate.query(
    "SELECT active FROM customer ORDER BY id",
    extractor
);
```

Dữ liệu mẫu có ba khách hàng đều active, nên map là `{ACTIVE=3}`. Nhưng khi chỉ cần đếm theo trạng thái, **`SELECT active, COUNT(*) ... GROUP BY active`** thường tối ưu hơn: DB có thể tổng hợp trước khi truyền dữ liệu qua mạng. Ví dụ Java giúp hiểu khả năng callback, không phải khuyến nghị luôn xử lý mọi aggregation ở client.

## 9. SQL NULL: lỗi cực dễ xảy ra khi JOIN ngoài

Một phép `LEFT JOIN` giữ lại cha không có con nhưng tạo các cột của bên phải bằng SQL `NULL`. Nếu đọc:

```java
long orderId = rs.getLong("order_id");
```

thì `orderId` sẽ là `0` khi SQL `NULL`. Để phân biệt:

```java
long orderId = rs.getLong("order_id");
if (!rs.wasNull()) {
    // Có bản ghi đơn hàng thực sự.
}
```

Hoặc driver JDBC hỗ trợ chuyển kiểu theo Java class:

```java
Long orderId = rs.getObject("order_id", Long.class);
if (orderId != null) {
    // Có đơn hàng.
}
```

Cách thứ hai tiện dụng nhưng khả năng hỗ trợ chuyển kiểu của các driver khác nhau; khi cần tính tương thích cao, kiểm tra driver và trường hợp `NULL` cụ thể. Đối với khóa chính cha, cột `customer_id` là `NOT NULL` theo DDL mẫu nên `getLong` đọc trực tiếp là hợp lý.

Đừng viết `if (rs.getString("customer_name") == null)` để xác định không có đơn: đó là cột của **bảng cha**, không phải dấu hiệu bản ghi con tồn tại. Hãy kiểm tra một khóa hoặc cột định danh **NOT NULL** của bảng con.

Nếu có nhiều bảng `LEFT JOIN` liên tiếp, mỗi nhóm cột nullable cần kiểm tra định danh riêng. Không sử dụng cùng một `wasNull()` lâu sau nhiều lời gọi getter vì nó phản ánh **getter gần nhất**.

## 10. Đúng khóa nhóm mới giữ đúng dữ liệu

**Nhóm theo ID, không nhóm theo tên hiển thị.** Hai khách hàng khác nhau có thể cùng tên “Lan”; một khách hàng có thể đổi tên nhưng khóa chính vẫn ổn định. Khóa map nên là `customer_id` hoặc khóa tổng hợp thể hiện đúng thực thể.

Giả sử dữ liệu:

```text
customer_id | customer_name
------------+--------------
1           | Lan
4           | Lan
```

Dùng `Map<String, Customer>` theo tên sẽ nhập nhầm hai người. Dùng `Map<Long, Customer>` theo `customer_id` vẫn giữ hai khách hàng.

**Cũng không nhầm việc xuất hiện nhiều hàng với duplicate cần xóa.** Hai hàng:

```text
customer=1, order=101
customer=1, order=102
```

là hai đơn hợp lệ của cùng khách hàng. Nếu gọi `DISTINCT customer_id, customer_name` quá sớm, bạn sẽ làm mất thông tin đơn. Ngược lại, nếu nối thêm `order_item`, một đơn có thể lặp do có nhiều dòng hàng hóa; khi gom đơn phải lưu các đơn trong map theo **`order_id`** để tránh nhân bản đơn.

Khi cần cây ba cấp `Customer → Order → Item`, thường cần:

- Map khách hàng theo `customer_id`.
- Bên trong mỗi khách hàng, map đơn theo `order_id`.
- Bên trong mỗi đơn, danh sách hoặc map item theo khóa item thích hợp.
- Chỉ tạo node mới khi khóa tương ứng lần đầu xuất hiện.
- Kiểm tra `NULL` ở từng cấp của `LEFT JOIN`.
- Biến các bộ gom mutable thành DTO cuối cùng sau khi duyệt.

Không nên chỉ dùng một `List<Order>` và thêm một `Order` trên **mỗi hàng SQL** khi một đơn có nhiều item, vì điều đó lặp order.

## 11. Trật tự hàng, dữ liệu lặp và độ đúng của phép gom

Câu SQL `ORDER BY c.id, o.id` trong ví dụ khiến thứ tự kết quả ổn định theo các khóa. `LinkedHashMap` giữ thứ tự khóa **gặp lần đầu**, nhưng bản thân `LinkedHashMap` **không khiến DB trả hàng có thứ tự**. Nếu ứng dụng cần thứ tự xác định, luôn yêu cầu DB sắp xếp theo đủ các khóa để giải quyết trường hợp bằng nhau.

Với logic chỉ cần gom theo khóa, `HashMap` vẫn có thể đúng về nội dung, nhưng thứ tự khi trả kết quả sẽ không được bảo đảm. `LinkedHashMap` kết hợp `ORDER BY` phù hợp để kết quả học tập có thứ tự dễ kiểm chứng.

Nếu kết quả có thể chứa bản ghi con lặp do nối nhiều bảng hoặc do nguồn dữ liệu, không tự dùng `Set` loại trùng “cho đẹp”. Trước hết xác định quy tắc nghiệp vụ: hai hàng có cùng `order_id` có thực sự là cùng thực thể không? Nếu đúng, có thể dùng `LinkedHashMap<Long, OrderAccumulator>`. Nếu không, giữ đủ từng bản ghi con. Loại trùng theo mọi cột hoặc theo tên hiển thị có thể che mất lỗi join và làm thất thoát dữ liệu.

## 12. Toàn tập không có nghĩa luôn đưa mọi dữ liệu vào RAM

Giả sử truy vấn trả một triệu hàng:

- Nếu extractor đưa mỗi hàng vào `ArrayList`, bộ nhớ Java có thể tăng theo số hàng.
- Nếu extractor tạo map khách hàng và các danh sách đơn, bộ nhớ tăng theo số thực thể/quan hệ cần giữ trong kết quả.
- Nếu extractor chỉ tăng một bộ đếm và không giữ hàng nào, dung lượng Java sử dụng cho kết quả có thể nhỏ, **nhưng driver JDBC vẫn có thể buffer dữ liệu** tùy loại DB, driver, fetch size và transaction.
- Giữ kết nối lâu trong lúc gọi API mạng khác, sleep hoặc xử lý tốn thời gian có thể làm connection pool thiếu kết nối.

Xét độ phức tạp của thuật toán gom mẫu: với `R` hàng trả về, việc duyệt thường là **O(R)** kỳ vọng khi map lookup trung bình O(1). Bộ nhớ của cấu trúc trả về khoảng **O(P + O)** với `P` số khách hàng và `O` số đơn được giữ, chưa tính buffer phía JDBC và overhead của Java.

Nếu chỉ cần tổng hợp:

```sql
SELECT customer_id, COUNT(*) AS order_count
FROM customer_order
GROUP BY customer_id;
```

thường nên để DB làm công việc tổng hợp. Nếu chỉ cần mười khách hàng đầu tiên, không nên truy vấn toàn bộ tập rồi dùng `subList(0, 10)`: phân trang ở DB và cân nhắc phân trang theo **khóa cha**, bởi `LIMIT 10` trên kết quả `JOIN` có thể cắt giữa danh sách đơn của khách hàng thứ mười.

Khi dữ liệu lớn, cân nhắc tách thành truy vấn phân trang parent và truy vấn lấy children theo tập ID, hoặc dùng streaming/fetch size/transaction phù hợp. `ResultSetExtractor` cho phép xử lý tuần tự nhưng **không tự bảo đảm chế độ streaming mạng hay RAM hằng số**.

## 13. Tương tác với giao dịch và quản lý tài nguyên Spring

`JdbcTemplate` lấy connection bằng hạ tầng tài nguyên của Spring và tham gia transaction hiện có khi cấu hình phù hợp. Khi dùng:

```java
@Transactional(readOnly = true)
public List<CustomerOrderRepository.CustomerView> load() {
    return repository.findActiveWithOrders();
}
```

đoạn code minh họa chỉ đúng khi phương thức thuộc Spring-managed service, annotation được Spring AOP/transaction infrastructure áp dụng thực sự, và repository đã được inject. `readOnly=true` là ý định read-only có thể hỗ trợ tối ưu ở các tầng, **không mặc định khóa tuyệt đối mọi ghi** ở mọi DB/driver. Một truy vấn duy nhất lấy cha–con cho phép ánh xạ từ một tập kết quả nhất quán theo semantics của statement; không có nghĩa mọi hệ thống luôn cung cấp một “snapshot” cố định qua nhiều câu SQL liên tiếp nếu isolation khác nhau.

Điều không nên làm:

```java
ResultSetExtractor<List<String>> wrong = rs -> {
    // Sai: ResultSet do JdbcTemplate sở hữu.
    rs.close();
    return List.of();
};
```

Nếu một extractor mở thêm file, socket hoặc stream riêng trong quá trình xử lý, chính nó phải đóng tài nguyên **do nó tự mở**. Nhưng `ResultSet` và statement cấp bởi template phải để template hoàn thành và dọn dẹp.

Tránh “chạy thêm một query trên cùng JdbcTemplate bên trong mỗi hàng” để lấy children: đó là vấn đề N+1 query, có thể tạo hàng trăm lượt round-trip DB. Hãy truy vấn đúng tập dữ liệu và gom theo khóa, hoặc dùng chiến lược truy vấn lô phù hợp.

### Ngoại lệ trong callback

`extractData` được phép ném `SQLException` khi đọc cột hoặc di chuyển con trỏ. Spring sẽ chuyển đổi nhiều lỗi SQL thành `DataAccessException`; các lỗi runtime do logic ứng dụng ném ra thường tiếp tục lan ra cho caller xử lý. Không nên:

```java
ResultSetExtractor<List<String>> unsafe = rs -> {
    try {
        // đọc dữ liệu
        return List.of();
    } catch (SQLException ex) {
        return List.of(); // Sai: che giấu lỗi DB bằng "không có dữ liệu".
    }
};
```

Đoạn này chỉ minh họa anti-pattern và không có thao tác đọc thực trong comment. Lỗi DB khác hoàn toàn việc query trả 0 hàng. Đối với ứng dụng thật, cho ngoại lệ đi ra khỏi callback để framework dọn tài nguyên và caller quyết định trả lỗi/rollback/retry an toàn.

## 14. Các tình huống thực tế: chọn ResultSetExtractor hay không?

### Tình huống A: truy vấn một bảng, mỗi hàng thành một DTO

```java
List<String> names = jdbcTemplate.query(
    "SELECT name FROM customer ORDER BY id",
    (rs, rowNum) -> rs.getString("name")
);
```

**Chọn `RowMapper`**, vì mỗi hàng là một tên; `ResultSetExtractor` chỉ làm code dài thêm.

### Tình huống B: JOIN cha–con trả nhiều hàng cho cùng cha

```text
Lan - 101
Lan - 102
Minh - 103
Vy - NULL
```

**Chọn `ResultSetExtractor`** nếu cần mỗi khách hàng đúng một đối tượng và có danh sách đơn. Gom theo khóa `customer_id`, kiểm tra `NULL` của `order_id`.

### Tình huống C: chỉ cần thống kê COUNT/SUM

**Ưu tiên SQL tổng hợp và `queryForObject`** nếu DB có thể trả một scalar:

```java
Long count = jdbcTemplate.queryForObject(
    "SELECT COUNT(*) FROM customer_order",
    Long.class
);
```

Với schema mẫu, `count` tương ứng `3`. Không cần kéo mọi hàng rồi dùng extractor để tăng biến `count`. Nếu cần cấu trúc tổng hợp tùy biến qua nhiều hàng/trường mà SQL không thuận tiện, extractor là một lựa chọn.

### Tình huống D: chỉ cần xử lý từng hàng mà không trả cấu trúc

`RowCallbackHandler` có `processRow(ResultSet rs)` phù hợp cho công việc theo hàng. Spring tự `rs.next()` trước mỗi lần gọi; handler không trả `T` tổng thể. Nếu cần trả `Map` hoặc cây dữ liệu, extractor thường mô tả ý định rõ hơn.

### Tình huống E: cần trả một đối tượng nếu SQL có tối đa một hàng

`queryForObject(sql, rowMapper, args...)` đã có hợp đồng **đúng một hàng**, và ném ngoại lệ nếu số hàng không phải 1. Nếu yêu cầu nghiệp vụ là “0 hoặc 1” với `Optional<T>`, có thể dùng `query` rồi xử lý danh sách, hoặc extractor chủ động kiểm tra hàng thứ hai; điều quan trọng là không âm thầm bỏ qua hàng thừa.

### Tình huống F: cần tải một cây lớn có nhiều bảng con

Extractor có thể xây map nhiều tầng, nhưng cần xem **fan-out**: nối cha với hai bảng con 1–N độc lập có thể nhân số hàng (ví dụ 3 đơn × 4 địa chỉ = 12 hàng). Khi tích Descartes lớn, tách query theo nhóm khóa rồi ghép ở Java có thể hiệu quả và ít nguy cơ lặp dữ liệu hơn. Không coi một truy vấn JOIN khổng lồ là luôn tối ưu.

## 15. Dữ liệu rỗng, kiểm tra số hàng và quy ước trả về

Điều kiện `while (rs.next())` giúp xử lý `ResultSet` rỗng tự nhiên:

```java
ResultSetExtractor<List<Long>> extractor = rs -> {
    List<Long> ids = new ArrayList<>();
    while (rs.next()) {
        ids.add(rs.getLong("customer_id"));
    }
    return ids;
};
```

Nếu không có hàng, trả `[]`. `extractData` không bị giới hạn phải trả danh sách; bạn có thể trả một record có tổng bằng zero hoặc một `Map` rỗng theo hợp đồng ứng dụng.

Khi yêu cầu “SQL phải trả đúng một nhóm”, hãy ghi rõ kiểm tra:

- Không có hàng: danh sách rỗng, `Optional.empty()` hoặc ngoại lệ? Tùy nghiệp vụ.
- Có một hàng: xử lý bình thường.
- Nhiều hàng bất ngờ: có cần báo lỗi hay không? Đừng chỉ lấy hàng đầu rồi im lặng.
- Có nhiều hàng SQL cho **cùng một thực thể cha**: không tự động coi là nhiều thực thể; phân biệt grain SQL và grain đối tượng trả ra.

`ResultSetExtractor` cho phép định nghĩa quy tắc, nhưng việc làm đúng hay sai phụ thuộc code của người viết. Một truy vấn có `ORDER BY` và khóa nhóm rõ ràng khiến việc kiểm thử dễ hơn.

## 16. Java 17 chạy độc lập: mô phỏng bước gom toàn tập

Để hiểu thuật toán mà không cần tải Spring hoặc mở DB, ví dụ dưới đây dùng **JDK 17 thuần**. Nó mô phỏng bốn hàng sau `LEFT JOIN` bằng một `List<JoinedRow>`, sau đó duyệt **toàn danh sách** để gom theo khóa khách hàng. Các record và phương thức `fold` là mã học tập, **không phải `ResultSetExtractor` thật**; trong ứng dụng JDBC, vòng `for` tương ứng với `while (rs.next())`.

Tạo tệp `ExtractorFoldDemo.java`:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class ExtractorFoldDemo {
    record JoinedRow(long customerId, String customerName, Long orderId) {}
    record CustomerSummary(long id, String name, List<Long> orderIds) {}

    private static final class Bucket {
        final long id;
        final String name;
        final List<Long> orderIds = new ArrayList<>();

        Bucket(long id, String name) {
            this.id = id;
            this.name = name;
        }

        CustomerSummary snapshot() {
            return new CustomerSummary(id, name, List.copyOf(orderIds));
        }
    }

    static List<CustomerSummary> fold(List<JoinedRow> rows) {
        Map<Long, Bucket> byId = new LinkedHashMap<>();
        for (JoinedRow row : rows) {
            Bucket bucket = byId.get(row.customerId());
            if (bucket == null) {
                bucket = new Bucket(row.customerId(), row.customerName());
                byId.put(row.customerId(), bucket);
            }
            if (row.orderId() != null) {
                bucket.orderIds.add(row.orderId());
            }
        }

        List<CustomerSummary> result = new ArrayList<>();
        for (Bucket bucket : byId.values()) {
            result.add(bucket.snapshot());
        }
        return result;
    }

    public static void main(String[] args) {
        List<JoinedRow> rows = List.of(
            new JoinedRow(1, "Lan", 101L),
            new JoinedRow(1, "Lan", 102L),
            new JoinedRow(2, "Minh", 103L),
            new JoinedRow(3, "Vy", null)
        );

        List<CustomerSummary> customers = fold(rows);
        System.out.println("raw rows=" + rows.size());
        for (CustomerSummary customer : customers) {
            System.out.println(customer.name() + " -> " + customer.orderIds());
        }
        System.out.println("customers=" + customers.size());
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac --release 17 ExtractorFoldDemo.java
java ExtractorFoldDemo
```

Đầu ra chính xác:

```text
raw rows=4
Lan -> [101, 102]
Minh -> [103]
Vy -> []
customers=3
```

**Giải thích:** `rows.size()` vẫn là 4 vì đây là số **hàng JOIN**. `customers.size()` là 3 vì hai hàng của Lan được gom thành một khách hàng. Với Vy, `orderId == null` được bỏ qua, giữ `orderIds=[]` chứ không tạo “đơn hàng có ID null”.

Ví dụ còn cho thấy một lỗi hay gặp: `List.of(null)` không được Java cho phép, nên dữ liệu `NULL` được biểu diễn bằng một trường `orderId` nullable bên trong một `JoinedRow` không-null; không cố tạo một danh sách với phần tử null bằng `List.of(...)`.

## 17. Kiểm thử ResultSetExtractor thế nào?

Nên kiểm thử **quy ước kết quả** chứ không chỉ kiểm tra câu SQL chạy:

| Trường hợp | Dữ liệu đầu vào | Kết quả mong muốn |
| --- | --- | --- |
| Không có hàng | `ResultSet` rỗng | Danh sách/map rỗng, không `null` nếu đã chọn quy ước này |
| Một cha, một con | 1 hàng | Một cha có một con |
| Một cha, nhiều con | 2+ hàng cùng khóa cha | Một cha chứa tất cả con hợp lệ |
| Cha không có con | Hàng `LEFT JOIN` với `order_id=NULL` | Cha có danh sách con rỗng |
| Hai cha trùng tên | Hai khóa chính khác nhau | Hai đối tượng cha riêng biệt |
| Hai bảng con cùng JOIN | Một con lặp vì fan-out | Không tạo trùng con nếu khóa định danh trùng |
| Nhiều hàng khác thứ tự | DB trả theo khóa sắp xếp | Kết quả giữ thứ tự mong đợi |
| SQL/driver báo lỗi | `SQLException` khi duyệt | Ngoại lệ không bị nuốt hoặc biến thành dữ liệu rỗng |

Có hai tầng kiểm thử:

1. **Unit test thuật toán gom:** truyền một danh sách hàng phẳng (như `ExtractorFoldDemo`), xác nhận kết quả theo khóa, `NULL` và thứ tự. Nếu muốn test chính callback, có thể cung cấp `ResultSet` giả lập bằng thư viện mock thích hợp; tránh dựng giả lập quá phức tạp so với lợi ích.
2. **Integration test với DB thật hoặc DB kiểm thử tương thích:** tạo schema, insert dữ liệu, gọi repository, xác nhận `List<CustomerView>` đúng. Test này có ích để phát hiện sai alias cột, kiểu dữ liệu, cú pháp SQL, cách driver xử lý `NULL` và sự khác biệt giữa các database.

Khi kiểm thử lỗi, không chấp nhận `catch(SQLException) { return List.of(); }` như “xử lý thành công” vì sẽ làm sai kết quả nghiệp vụ. Cũng nên bật theo dõi số query để phát hiện N+1 nếu callback vô tình gọi thêm DB cho từng hàng.

## 18. Các lỗi thường gặp và cách tránh

**Lỗi 1: Quên `rs.next()`.**  
Gọi `getLong` khi cursor chưa ở hàng hợp lệ. Sửa: dùng `while (rs.next())` hoặc `if (rs.next())` trong extractor.

**Lỗi 2: Dùng `RowMapper` nhưng tự gọi `rs.next()`.**  
Với `RowMapper` và `RowCallbackHandler`, Spring đã di chuyển cursor. Đừng chuyển thói quen giữa các callback mà quên hợp đồng khác nhau.

**Lỗi 3: Mỗi hàng JOIN tạo một cha.**  
Phép 1–N sinh nhiều hàng cho cùng khóa. Sửa: map cha theo ID và chỉ khởi tạo lần đầu.

**Lỗi 4: Đọc khóa con nullable bằng `getLong()` rồi kiểm tra `!= 0`.**  
Không phân biệt được SQL `NULL` và giá trị 0. Sửa: `wasNull()` ngay sau getter hoặc getter trả wrapper nullable phù hợp driver.

**Lỗi 5: Gom theo tên thay vì khóa chính.**  
Hai người cùng tên bị nhập thành một. Sửa: dùng khóa định danh đúng grain.

**Lỗi 6: Thêm đơn lặp khi nối thêm bảng con.**  
Một `Order` có nhiều `OrderItem` có thể xuất hiện nhiều lần. Sửa: gom mỗi cấp theo khóa riêng hoặc đổi chiến lược truy vấn.

**Lỗi 7: Cho rằng `LinkedHashMap` tạo thứ tự SQL.**  
Map chỉ nhớ thứ tự đầu vào. Sửa: `ORDER BY` rõ ràng và kiểm thử thứ tự.

**Lỗi 8: Gọi `rs.close()` trong extractor.**  
Trái với quyền sở hữu của `JdbcTemplate`. Sửa: để template dọn tài nguyên; chỉ đóng tài nguyên tự mở.

**Lỗi 9: Bắt mọi `SQLException` và trả danh sách rỗng.**  
Che giấu lỗi DB như tình huống không có dữ liệu. Sửa: để ngoại lệ được Spring dịch và caller xử lý.

**Lỗi 10: Giữ map/danh sách mutable làm trường singleton.**  
Có thể trộn kết quả giữa nhiều request. Sửa: tạo state ngay bên trong `extractData`; nếu tái sử dụng extractor, giữ nó stateless.

**Lỗi 11: Truy vấn quá rộng rồi chỉ dùng ít kết quả.**  
Đưa toàn bộ bảng từ DB về Java gây tốn I/O, CPU và RAM. Sửa: lọc, tổng hợp, phân trang hợp lý tại DB.

**Lỗi 12: `LIMIT` trực tiếp trên JOIN để phân trang cha.**  
Có thể cắt dở danh sách đơn của một cha. Sửa: phân trang danh sách ID cha trước, sau đó lấy đầy đủ con cho nhóm cha được chọn.

**Lỗi 13: Cho rằng extractor tự streaming với RAM hằng số.**  
Driver có thể buffer nhiều hàng, và map vẫn cần chứa đối tượng trả về. Sửa: đo lường với DB thực, cấu hình fetch size/transaction phù hợp và giới hạn tập dữ liệu.

**Lỗi 14: Gọi thêm query trong từng bước `rs.next()`.**  
Phát sinh N+1, giữ connection lâu, khó quản lý kết quả nhất quán. Sửa: thiết kế query tổng hợp hoặc batch query cho children.

## 19. Bài tập tự kiểm tra

**Câu 1.** `ResultSetExtractor<T>` xử lý một hàng hay toàn tập? Ai gọi `rs.next()`?

**Đáp án:** xử lý toàn `ResultSet`; extractor **tự** gọi `rs.next()`. `JdbcTemplate` không duyệt từng hàng hộ extractor như với `RowMapper`.

**Câu 2.** SQL trả bốn hàng: Lan–101, Lan–102, Minh–103, Vy–NULL. Kết quả gom theo khóa khách hàng có bao nhiêu cha và bao nhiêu đơn?

**Đáp án:** 3 cha và 3 đơn. Vy có danh sách đơn rỗng.

**Câu 3.** Vì sao `rs.getLong("order_id") == 0` không đủ để biết con không tồn tại?

**Đáp án:** JDBC trả 0 cho SQL `NULL` khi dùng primitive getter; phải kiểm tra `rs.wasNull()`. Một khóa có giá trị 0 cũng có thể là dữ liệu hợp lệ tùy schema.

**Câu 4.** Nếu muốn `List<Account>`, mỗi hàng đúng một Account, nên dùng gì?

**Đáp án:** thường là `RowMapper<Account>` cùng `JdbcTemplate.query(...)`, vì template đã thực hiện vòng lặp.

**Câu 5.** Nếu muốn `Map<Long, CustomerView>` nhóm theo ID và kết hợp nhiều hàng JOIN thì sao?

**Đáp án:** `ResultSetExtractor<Map<Long, CustomerView>>` phù hợp; dùng map theo khóa, duyệt cả tập và xây cấu trúc mong muốn.

**Câu 6.** Callback có cần tự đóng `ResultSet` được template truyền vào không?

**Đáp án:** Không. `JdbcTemplate` sở hữu và đóng nó. Callback chỉ đóng tài nguyên phụ do chính nó mở.

**Câu 7.** Có ba đơn, mỗi đơn hai item. JOIN khách hàng–đơn–item trả sáu hàng. Nếu thêm `Order` vào list mỗi hàng thì sao?

**Đáp án:** mỗi đơn có thể bị nhân bản hai lần. Cần nhóm theo `order_id` trước khi thêm item hoặc tách chiến lược lấy dữ liệu.

**Câu 8.** Nếu chỉ cần `COUNT(*)` số đơn, nên duyệt tất cả hàng bằng extractor không?

**Đáp án:** thường không. DB tổng hợp rồi `queryForObject(..., Long.class)` đơn giản và ít truyền dữ liệu hơn.

**Câu 9.** Với extractor ở mục 6, điều gì xảy ra nếu truy vấn không trả khách hàng nào?

**Đáp án:** vòng `while` không chạy; `byId` rỗng và phương thức trả danh sách rỗng, không tạo khách hàng giả.

**Câu 10.** Vì sao cần `ORDER BY` trong ví dụ dùng `LinkedHashMap`?

**Đáp án:** `LinkedHashMap` chỉ giữ thứ tự xuất hiện trong `ResultSet`. Nếu DB không sắp xếp, thứ tự xuất hiện không được bảo đảm; thêm `ORDER BY` để kết quả có thứ tự dự đoán được.

## 20. Tổng kết

- **`ResultSetExtractor<T>` = một callback, một kết quả `T` cho cả `ResultSet`.**
- Khác `RowMapper`, **extractor tự gọi `rs.next()`** và có thể giữ trạng thái xuyên nhiều hàng.
- Mẫu sử dụng hiệu quả nhất: `JOIN` 1–N → `LinkedHashMap` theo khóa chính → gom con → snapshot ra DTO/record.
- Luôn kiểm tra `NULL` của phía con trong `LEFT JOIN`; với getter primitive như `getLong`, dùng `wasNull()` ngay sau đó.
- `ResultSetExtractor` không tự giải quyết duplicate do JOIN, phân trang, thứ tự, mức tiêu thụ bộ nhớ hay đồng thời. Đúng khóa nhóm, SQL và thiết kế kết quả vẫn là trách nhiệm ứng dụng.
- `JdbcTemplate` chịu trách nhiệm dọn tài nguyên và xử lý ngoại lệ JDBC. Không đóng `ResultSet` hoặc `Connection` của template trong extractor.
- Khi chỉ cần DTO mỗi hàng, dùng `RowMapper`; khi chỉ cần `COUNT/SUM`, ưu tiên SQL aggregation; khi cần xử lý theo hàng mà không trả cấu trúc, cân nhắc `RowCallbackHandler`.
- **Bắt đầu từ hình dạng dữ liệu mong muốn** và số hàng SQL thực tế, rồi chọn callback phù hợp; không chọn callback chỉ vì nó tổng quát nhất.

### Tài liệu tham khảo

- [Spring Framework Javadoc — ResultSetExtractor](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/jdbc/core/ResultSetExtractor.html)
- [Spring Framework Javadoc — JdbcTemplate](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html)
- [Spring Framework Javadoc — RowMapper](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/jdbc/core/RowMapper.html)
- [Spring Framework Javadoc — RowMapperResultSetExtractor](https://docs.spring.io/spring-framework/docs/6.0.x/javadoc-api/org/springframework/jdbc/core/RowMapperResultSetExtractor.html)
- [Spring Framework Reference — Data Access with JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html)
