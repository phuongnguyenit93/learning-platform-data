# Ánh xạ kết quả nối bảng có đối tượng con không tồn tại trong JDBC

## 1. Vấn đề cần giải quyết

Khi ứng dụng Java dùng **JDBC** để truy cập cơ sở dữ liệu quan hệ, `PreparedStatement` thực thi câu SQL và `ResultSet` trả về từng hàng dữ liệu phẳng. Nhưng mô hình Java thường có quan hệ cha–con: một khách hàng **có thể** có hồ sơ bổ sung; một đơn hàng **có thể** có nhiều dòng hàng hoặc chưa có dòng hàng nào.

Nếu truy vấn dùng `LEFT JOIN`, hàng của bảng cha vẫn được trả về khi không có bản ghi ở bảng con. Khi đó, các cột thuộc bảng con trong `ResultSet` nhận giá trị SQL `NULL`. Phép ánh xạ phải quyết định **có tạo đối tượng con hay không**, trước khi đọc các thuộc tính khác của con.

Ví dụ với quan hệ khách hàng–hồ sơ tùy chọn:

| `customer_id` | `customer_name` | `profile_id` | `profile_phone` | Cách hiểu đúng |
|---:|---|---:|---|---|
| 10 | An | `NULL` | `NULL` | Khách hàng An tồn tại; **không có** hồ sơ |
| 11 | Bình | 81 | `NULL` | Khách hàng Bình có hồ sơ 81; số điện thoại **chưa có giá trị** |
| 12 | Chi | 82 | 0912345678 | Khách hàng Chi có hồ sơ 82 và số điện thoại |

Hai trạng thái đầu không tương đương: **không có đối tượng con** khác với **có đối tượng con nhưng một thuộc tính của nó là `NULL`**.

Bài thuộc chương **Ánh xạ bản ghi** của module JDBC, tập trung vào cách sử dụng `ResultSet`, SQL nối bảng, quản lý kết nối qua `DataSource`, truy vấn tham số hóa và kiểm soát lỗi khi dựng đối tượng Java. Sau bài này, bạn có thể:

1. Phân biệt không tìm thấy bản ghi cha, có cha nhưng thiếu con, và có cha với các cột con nullable.
2. Ánh xạ `LEFT JOIN` thành đối tượng con tùy chọn trong quan hệ **1–0..1**.
3. Gom nhiều hàng SQL thành một đối tượng cha chứa danh sách con trong quan hệ **1–0..N**.
4. Tránh tạo đối tượng con “ảo”, bỏ mất cha khi không có con, tạo trùng cha/con hoặc làm sai trạng thái `NULL`.
5. Thiết kế SQL, code Java và trường hợp kiểm thử giúp phép ánh xạ dễ bảo trì.

## 2. Hiểu đúng ngữ nghĩa `LEFT JOIN`

Giả sử quan hệ khách hàng–hồ sơ có dạng:

```text
customers                  customer_profiles
---------                  -----------------
id (PK)                    id (PK)
name                       customer_id (FK, UNIQUE)
                           phone (nullable)

customers (1) ---------- (0..1) customer_profiles
```

Truy vấn:

```sql
SELECT c.id    AS customer_id,
       c.name  AS customer_name,
       p.id    AS profile_id,
       p.phone AS profile_phone
FROM customers c
LEFT JOIN customer_profiles p
       ON p.customer_id = c.id
WHERE c.id = ?
```

- Nếu khách hàng không tồn tại, truy vấn trả **0 hàng**.
- Nếu khách hàng tồn tại nhưng không có hồ sơ, truy vấn trả **1 hàng** với `customer_id` khác `NULL` và `profile_id` bằng `NULL`.
- Nếu khách hàng có hồ sơ, `profile_id` khác `NULL`; `profile_phone` vẫn có thể là `NULL` nếu cột đó cho phép.

`LEFT JOIN` giữ các hàng bên trái và bổ sung cột từ bên phải khi có hàng khớp. Nó không tự tạo một hàng “rỗng” đại diện cho một khách hàng không tồn tại.

### Vì sao nên kiểm tra khóa của đối tượng con?

Để xác định có tồn tại một hàng bảng con, hãy kiểm tra **khóa chính không nullable** của bảng con, được chọn ra trong câu SQL (ví dụ `p.id AS profile_id`). Không nên suy đoán từ `phone`, `description`, `date_of_birth` hoặc một thuộc tính nghiệp vụ được phép `NULL`.

| Điều kiện trong `ResultSet` | Kết luận |
|---|---|
| `profile_id IS NULL` | Không có hàng hồ sơ khớp với `LEFT JOIN` |
| `profile_id IS NOT NULL`, `profile_phone IS NULL` | Có hồ sơ; trường `phone` chưa có giá trị |
| Không có `rs.next()` | Không có hàng kết quả, có thể do khách hàng không tồn tại hoặc bị lọc |

**Điều kiện tiên quyết:** `profile_id` thật sự đến từ cột khóa của bảng con và khóa đó không thể `NULL` trong hàng bảng con hợp lệ. Nếu truy vấn không lấy khóa, nên bổ sung khóa hoặc một chỉ dấu tồn tại có ý nghĩa rõ ràng, thay vì đoán sự tồn tại qua một tập thuộc tính nullable.

## 3. Ánh xạ quan hệ 1–0..1: tạo đối tượng con khi có khóa

Với Java 17+, có thể biểu diễn kết quả bằng `record`:

```java
public record ProfileView(long id, String phone) {}

public record CustomerView(long id, String name, ProfileView profile) {}
```

Ở đây, quy ước của `CustomerView` là `profile == null` nghĩa là khách hàng **không có** hồ sơ. Đây là lựa chọn thiết kế của DTO, không phải quy tắc bắt buộc của JDBC. Nếu ứng dụng muốn diễn đạt rõ hơn, API của tầng nghiệp vụ có thể dùng một kiểu biểu diễn sự có/không tồn tại, chẳng hạn `Optional<ProfileView>`, với quy ước nhất quán.

### 3.1. Mapper đọc một hàng

Ví dụ sau giả định `ResultSet` đã được di chuyển tới một hàng hợp lệ bằng `rs.next()`:

```java
import java.sql.ResultSet;
import java.sql.SQLException;

public final class CustomerRowMapper {
    public record ProfileView(long id, String phone) {}
    public record CustomerView(long id, String name, ProfileView profile) {}

    public static CustomerView map(ResultSet rs) throws SQLException {
        long customerId = rs.getLong("customer_id");
        if (rs.wasNull()) {
            throw new SQLException("Thiếu khóa customer_id");
        }

        long profileId = rs.getLong("profile_id");
        boolean hasProfile = !rs.wasNull(); // kiểm tra ngay sau getLong

        ProfileView profile = hasProfile
                ? new ProfileView(
                        profileId,
                        rs.getString("profile_phone"))
                : null;

        return new CustomerView(
                customerId,
                rs.getString("customer_name"),
                profile
        );
    }
}
```

**Lưu ý về `rs.wasNull()`:** `ResultSet.getLong(...)` trả `0` khi giá trị SQL là `NULL`, giống một giá trị `long` hợp lệ có thể có trong dữ liệu. Vì vậy, gọi `rs.wasNull()` **ngay sau getter vừa đọc** để biết lần đọc đó gặp SQL `NULL` hay không. Không thể chỉ dựa vào `profileId == 0`.

Trong nhánh `hasProfile == false`, chương trình bỏ qua hoàn toàn việc tạo `ProfileView`. Trong nhánh còn lại, `phone` có thể là `null`, nhưng `ProfileView` vẫn được tạo vì hàng hồ sơ thực sự tồn tại.

### 3.2. Phân biệt khách hàng không tồn tại

Sau khi gán tham số và chạy truy vấn, tầng gọi mapper cần kiểm tra trước:

```java
try (ResultSet rs = statement.executeQuery()) {
    if (!rs.next()) {
        return Optional.empty(); // không tìm thấy khách hàng
    }

    CustomerRowMapper.CustomerView customer = CustomerRowMapper.map(rs);
    return Optional.of(customer);
}
```

Đoạn này minh họa **phần đọc kết quả** của một phương thức có kiểu trả về `Optional<CustomerRowMapper.CustomerView>`; biến `statement` là một `PreparedStatement` đã chuẩn bị, và cần import `java.util.Optional`. Đối với truy vấn bằng khóa duy nhất, ràng buộc dữ liệu phải bảo đảm tối đa một hồ sơ cho một khách hàng. Nếu quan hệ thực tế là 1–N, việc chỉ đọc hàng đầu tiên sẽ làm **mất dữ liệu con**; phải áp dụng kỹ thuật gom nhóm ở phần sau.

### 3.3. Không tự tạo “hồ sơ mặc định” để che giấu sự vắng mặt

Đoạn mã sau có lỗi:

```java
// Sai: tạo ProfileView ngay cả khi LEFT JOIN không có hàng bảng con.
ProfileView profile = new ProfileView(
        rs.getLong("profile_id"),
        rs.getString("profile_phone")
);
```

Với `profile_id = NULL`, lời gọi `getLong` trả `0`; đối tượng `ProfileView(0, null)` trở thành **đối tượng ảo**. Lỗi này có thể đi xa đến bước lưu dữ liệu, hiển thị sai trạng thái hoặc kiểm tra nghiệp vụ dựa trên việc `profile != null`.

## 4. Ánh xạ quan hệ 1–0..N: gom hàng theo cha, chỉ thêm con thật

Với một đơn hàng và nhiều dòng hàng, `LEFT JOIN` có thể tạo **nhiều hàng SQL cho cùng một cha**. Nếu đơn hàng chưa có dòng nào, vẫn có một hàng kết quả với các cột dòng hàng bằng `NULL`.

Ví dụ:

| `order_id` | `order_code` | `line_id` | `line_product_name` | Kết quả mong muốn |
|---:|---|---:|---|---|
| 501 | OD-501 | 901 | Bàn phím | Đơn 501 chứa dòng 901 |
| 501 | OD-501 | 902 | Chuột | Đơn 501 chứa thêm dòng 902 |
| 502 | OD-502 | `NULL` | `NULL` | Đơn 502 tồn tại, danh sách dòng **rỗng** |

Không thể tạo một `OrderView` mới cho **mỗi** hàng SQL: làm vậy sẽ có hai đơn hàng 501. Cũng không thể luôn thêm `LineView`: làm vậy đơn hàng 502 sẽ có dòng hàng giả.

### 4.1. Cấu trúc bảng và câu SQL tham số hóa

Giả sử ứng dụng có hai bảng:

```sql
CREATE TABLE orders (
    id         BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    order_code VARCHAR(40) NOT NULL
);

CREATE TABLE order_lines (
    id           BIGINT PRIMARY KEY,
    order_id     BIGINT NOT NULL REFERENCES orders(id),
    product_name VARCHAR(200) NOT NULL,
    quantity     INTEGER NOT NULL,
    unit_price   DECIMAL(18, 2) NOT NULL
);
```

Truy vấn lấy đơn hàng của một khách hàng cùng các dòng hàng tùy chọn:

```sql
SELECT o.id           AS order_id,
       o.order_code   AS order_code,
       li.id          AS line_id,
       li.product_name AS line_product_name,
       li.quantity    AS line_quantity,
       li.unit_price  AS line_unit_price
FROM orders o
LEFT JOIN order_lines li ON li.order_id = o.id
WHERE o.customer_id = ?
ORDER BY o.id, li.id
```

Dấu `?` sẽ được gán bằng `PreparedStatement.setLong`, giúp tham số hóa giá trị `customer_id`. Tên và alias cột rõ ràng cũng ngăn trường hợp cả hai bảng đều có `id` khiến mapper đọc nhầm cột.

### 4.2. Ví dụ hoàn chỉnh với `DataSource` và `ResultSet`

Đoạn sau đọc dữ liệu bằng các API JDBC chuẩn, giữ mỗi đơn hàng một lần trong `LinkedHashMap`, chỉ thêm dòng hàng khi `line_id` có giá trị và trả về danh sách con bất biến:

```java
import javax.sql.DataSource;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class OrderQueryService {
    public record LineView(
            long id,
            String productName,
            int quantity,
            BigDecimal unitPrice
    ) {}

    public record OrderView(
            long id,
            String code,
            List<LineView> lines
    ) {}

    private static final class OrderAccumulator {
        final long id;
        final String code;
        final List<LineView> lines = new ArrayList<>();

        OrderAccumulator(long id, String code) {
            this.id = id;
            this.code = code;
        }

        OrderView toView() {
            return new OrderView(id, code, List.copyOf(lines));
        }
    }

    private final DataSource dataSource;

    public OrderQueryService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public List<OrderView> findOrdersForCustomer(long customerId)
            throws SQLException {
        String sql = """
                SELECT o.id            AS order_id,
                       o.order_code    AS order_code,
                       li.id           AS line_id,
                       li.product_name AS line_product_name,
                       li.quantity     AS line_quantity,
                       li.unit_price   AS line_unit_price
                FROM orders o
                LEFT JOIN order_lines li ON li.order_id = o.id
                WHERE o.customer_id = ?
                ORDER BY o.id, li.id
                """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, customerId);

            try (ResultSet rs = statement.executeQuery()) {
                Map<Long, OrderAccumulator> byOrderId =
                        new LinkedHashMap<>();

                while (rs.next()) {
                    // Bảng cha là bên trái LEFT JOIN.
                    long orderId = rs.getLong("order_id");
                    if (rs.wasNull()) {
                        throw new SQLException("Thiếu order_id");
                    }

                    OrderAccumulator order = byOrderId.get(orderId);
                    if (order == null) {
                        order = new OrderAccumulator(
                                orderId,
                                rs.getString("order_code")
                        );
                        byOrderId.put(orderId, order);
                    }

                    // Bảng con là bên phải LEFT JOIN: có thể vắng mặt.
                    long lineId = rs.getLong("line_id");
                    boolean hasLine = !rs.wasNull();
                    if (!hasLine) {
                        continue;
                    }

                    int quantity = rs.getInt("line_quantity");
                    if (rs.wasNull()) {
                        throw new SQLException(
                                "line_quantity là NULL tại line_id=" + lineId);
                    }

                    String productName = rs.getString("line_product_name");
                    BigDecimal unitPrice = rs.getBigDecimal("line_unit_price");
                    if (productName == null || unitPrice == null) {
                        throw new SQLException(
                                "Dòng hàng thiếu dữ liệu tại line_id=" + lineId);
                    }

                    order.lines.add(new LineView(
                            lineId,
                            productName,
                            quantity,
                            unitPrice
                    ));
                }

                List<OrderView> result = new ArrayList<>();
                for (OrderAccumulator order : byOrderId.values()) {
                    result.add(order.toView());
                }
                return result;
            }
        }
    }
}
```

#### Diễn giải thuật toán

1. **Đọc từng hàng SQL:** `while (rs.next())`.
2. **Tìm hoặc tạo cha:** dùng `order_id` làm khóa trong `LinkedHashMap`. Đơn hàng 501 xuất hiện nhiều hàng SQL nhưng chỉ có một `OrderAccumulator`.
3. **Kiểm tra khóa con:** đọc `line_id` và gọi `wasNull()` ngay lập tức. Nếu `NULL`, giữ cha và bỏ qua bước tạo dòng hàng.
4. **Tạo con khi hiện hữu:** đọc các trường của dòng hàng, xử lý `NULL` không hợp lệ theo hợp đồng bảng rồi thêm `LineView` vào cha.
5. **Đóng gói kết quả:** chuyển mỗi accumulator thành `OrderView` và dùng `List.copyOf` để tránh sửa danh sách con ngoài ý muốn.

`DataSource` cung cấp kết nối; `try-with-resources` bảo đảm đóng `ResultSet`, `PreparedStatement` và `Connection` khi kết thúc hoặc phát sinh `SQLException`. Việc quản lý transaction và kết nối thuộc về thiết kế tầng dữ liệu của ứng dụng; mapper có thể được tách khỏi lớp truy vấn nếu nhiều phương thức cần tái sử dụng.

**Với dữ liệu ví dụ:** kết quả gồm hai `OrderView`, trong đó đơn 501 có hai `LineView` và đơn 502 có `lines = []`. Nếu không có đơn hàng nào khớp `customer_id`, kết quả là danh sách đơn hàng rỗng.

### 4.3. Vì sao kết quả 1–N thường dùng danh sách rỗng?

Trong quan hệ 1–N, `lines = []` biểu đạt “đơn hàng có **0** dòng”, trong khi `lines = null` thường gây thêm nhánh kiểm tra cho các vòng lặp và thao tác đếm. Với quan hệ 1–0..1, một trường `profile = null` lại là cách biểu đạt tự nhiên rằng đối tượng con chưa tồn tại.

| Mối quan hệ | Dạng Java thường dùng | Khi không có con |
|---|---|---|
| 1–0..1 | `CustomerView(..., ProfileView profile)` | `profile == null` hoặc biểu diễn tùy chọn có quy ước |
| 1–0..N | `OrderView(..., List<LineView> lines)` | `lines.isEmpty()` |
| Không có bản ghi cha | Kiểu trả về ở tầng truy vấn | `Optional.empty()` cho truy vấn một cha, hoặc `List.of()` cho truy vấn tập cha |

Đừng lẫn lộn **vắng cha**, **vắng con** và **con có giá trị thuộc tính bằng `NULL`**: ba trạng thái này có ý nghĩa nghiệp vụ khác nhau.

## 5. Những lỗi hay gặp khi nối bảng

### 5.1. Đặt điều kiện lọc con trong `WHERE`

Xét yêu cầu lấy **mọi đơn hàng**, kèm những dòng hàng có `quantity > 0`. Truy vấn sau dễ gây lỗi:

```sql
-- Sai nếu muốn giữ cả đơn hàng không có dòng hàng phù hợp.
SELECT o.id AS order_id, li.id AS line_id
FROM orders o
LEFT JOIN order_lines li ON li.order_id = o.id
WHERE o.customer_id = ?
  AND li.quantity > 0
```

Khi không có dòng hàng, `li.quantity` bằng `NULL`, điều kiện `li.quantity > 0` không được đánh giá là `TRUE`, nên hàng cha bị loại khỏi kết quả. Với yêu cầu trên, hãy để điều kiện về con nằm trong `ON`:

```sql
SELECT o.id AS order_id, li.id AS line_id
FROM orders o
LEFT JOIN order_lines li
       ON li.order_id = o.id
      AND li.quantity > 0
WHERE o.customer_id = ?
```

Lúc này, đơn hàng không có dòng phù hợp vẫn được trả về với `line_id = NULL`. Nếu yêu cầu nghiệp vụ **chỉ lấy những đơn có dòng hàng thỏa điều kiện**, lọc trong `WHERE` có thể là chủ ý; cần chọn theo semantics thực tế.

### 5.2. Kiểm tra tất cả cột con bằng `NULL`

Đừng viết logic “nếu `phone` là `null` thì không có profile”. Một hồ sơ tồn tại hoàn toàn có thể chưa có số điện thoại. Kiểm tra khóa con (hoặc chỉ dấu tồn tại được thiết kế rõ ràng) nhất quán hơn và tránh làm mất đối tượng.

Nếu bảng con sử dụng **khóa ghép**, hãy bảo đảm truy vấn trả đủ các thành phần khóa và xây quy tắc nhận biết khớp tương ứng. Không dùng một thuộc tính nullable bất kỳ như khóa nhận biết.

### 5.3. Không xử lý `NULL` của getter kiểu nguyên thủy

`getLong`, `getInt`, `getBoolean` cho giá trị mặc định khi đọc SQL `NULL`; `wasNull()` cho biết lần đọc gần nhất có `NULL` hay không. Nếu cần giữ trạng thái nullable, có thể dùng wrapper như `Long` và logic chuyển đổi tương ứng. `getObject(column, Long.class)` có thể hữu ích khi driver hỗ trợ phép chuyển đổi đó, nhưng vẫn nên kiểm thử với driver và kiểu SQL thực tế.

### 5.4. Tạo trùng con khi nối nhiều quan hệ 1–N

Ví dụ:

```sql
SELECT o.id, li.id AS line_id, note.id AS note_id
FROM orders o
LEFT JOIN order_lines li ON li.order_id = o.id
LEFT JOIN order_notes note ON note.order_id = o.id
```

Nếu một đơn có 2 dòng hàng và 3 ghi chú, kết quả có thể chứa **6 hàng** cho đơn đó. Mapper đơn giản của phần trước sẽ thêm cùng một `LineView` nhiều lần nếu áp dụng nguyên trạng cho truy vấn này.

Có thể xử lý bằng cách:

- Dùng tập khóa đã gặp theo **từng cha và từng loại con** (ví dụ `Set<Long> lineIds` và `Set<Long> noteIds`) trước khi thêm vào danh sách tương ứng.
- Tách thành các truy vấn đọc cha, dòng hàng và ghi chú theo tập ID rồi ghép trong Java, đặc biệt khi nhiều quan hệ 1–N khiến tích Descartes quá lớn.
- Xem xét truy vấn tổng hợp hoặc cấu trúc kết quả riêng của hệ quản trị dữ liệu, nhưng cần nắm rõ cách ánh xạ và sự hỗ trợ của driver.

Quy tắc **“gom cha theo khóa và tạo con khi khóa con có mặt”** vẫn đúng; với nhiều phép nối, phải bổ sung việc chống trùng con nếu phép nối tạo nhiều hàng cho cùng một con.

### 5.5. Nhầm alias hoặc tên cột

Các bảng cùng có trường `id`, `name` hoặc `created_at`. Dùng `SELECT o.id, li.id` rồi gọi `rs.getLong("id")` dễ gây nhầm. Khuyến nghị dùng alias cụ thể như `order_id`, `line_id` và đọc nhất quán theo alias.

`ResultSetMetaData` có thể giúp quan sát nhãn cột trong truy vấn động, nhưng không tự quyết định rằng `line_id = NULL` nghĩa là không tạo `LineView`; quy tắc về quan hệ cha–con phải nằm trong mapper hoặc hợp đồng dữ liệu.

## 6. Thiết kế theo yêu cầu nghiệp vụ

### Đối tượng con thật sự tùy chọn hay bản ghi dữ liệu không hợp lệ?

Quan hệ cho phép 0 con là một trường hợp dữ liệu hợp lệ. Ví dụ khách hàng chưa tạo profile hoặc đơn hàng còn nháp và chưa thêm dòng hàng. Hãy mô hình hóa rõ trường hợp này bằng `null`, `Optional` hoặc danh sách rỗng phù hợp.

Ngược lại, khi `line_id` **có mặt** nhưng `line_quantity` lại `NULL` dù schema quy định `NOT NULL`, đó là tín hiệu lỗi dữ liệu/hợp đồng truy vấn. Mapper nên báo lỗi thay vì bỏ con hoặc tự thay `quantity = 0`.

### Phân biệt lọc con với không có con

Một đơn hàng có dòng hàng trong cơ sở dữ liệu nhưng tất cả đều bị lọc bởi điều kiện trong `ON` sẽ xuất hiện như đơn hàng có **0 dòng khớp truy vấn**. DTO khi đó mô tả **tập con đã chọn theo truy vấn**, không khẳng định đơn hàng không có dòng hàng nào trong toàn bộ cơ sở dữ liệu. Tên phương thức và tài liệu API nên phản ánh phạm vi này, ví dụ `findOrdersWithPositiveQuantityLines`.

### Một hay nhiều truy vấn?

| Phương án | Khi phù hợp | Điểm cần lưu ý |
|---|---|---|
| Một `LEFT JOIN` đọc cha và con | Danh sách vừa phải, một quan hệ 1–N, muốn tránh nhiều lượt truy vấn | Lặp cột cha trên từng hàng; cần gom nhóm và xử lý con vắng mặt |
| Truy vấn cha rồi truy vấn con theo **tập ID** | Nhiều loại con, tập cha được phân trang, tránh tăng số hàng khi nối nhiều 1–N | Cần ghép theo khóa và cân nhắc tính nhất quán giao dịch |
| Truy vấn từng cha rồi từng con riêng lẻ | Chỉ vài cha hoặc yêu cầu rất đặc biệt | Với nhiều cha dễ gặp vấn đề **N+1 query**, tăng số lượt tới DB |

Với các tập kết quả lớn, giữ toàn bộ `OrderView` trong bộ nhớ có chi phí theo số cha và số con. Có thể phân trang cha, xử lý theo lô hoặc dùng kỹ thuật đọc theo dòng kết quả. Nếu dùng `LIMIT` trực tiếp trên phép nối 1–N, số hàng giới hạn là **hàng SQL sau join**, có thể cắt ngang danh sách con của một đơn. Muốn phân trang cha, thường cần chọn tập khóa cha trước rồi lấy các con tương ứng.

## 7. Kiểm thử phép ánh xạ

Nên kiểm thử với cơ sở dữ liệu và driver gần môi trường thực, vì hành vi kiểu dữ liệu, nullability và metadata phụ thuộc vào SQL/driver. Tập tình huống tối thiểu:

| Trường hợp | Dữ liệu đầu vào | Kỳ vọng |
|---|---|---|
| Không có cha | Không có khách hàng/đơn hàng khớp `WHERE` | `Optional.empty()` hoặc danh sách rỗng |
| Cha có, con không có | Khách hàng không có profile; đơn chưa có dòng | Cha vẫn có mặt; `profile = null` hoặc `lines = []` |
| Con có, thuộc tính nullable | Profile tồn tại nhưng `phone = NULL` | Có `ProfileView`, `phone = null` |
| Cha có một con | Một đơn với một dòng | Một cha, một con |
| Cha có nhiều con | Một đơn với nhiều dòng | Một cha, đủ con, không lặp cha |
| Có nhiều cha xen kẽ | Nhiều đơn thuộc cùng khách hàng | Các dòng được ghép đúng `order_id` |
| Lọc con nhưng giữ cha | Mọi dòng không thỏa điều kiện trong `ON` | Cha còn, không có con khớp |
| Nhiều quan hệ 1–N | Các hàng bị nhân lên do nhiều `LEFT JOIN` | Không lặp con khi có cơ chế khử trùng |
| Dữ liệu bất thường | Khóa con có mặt, trường bắt buộc bị `NULL` | Báo lỗi phù hợp, không tạo đối tượng thiếu dữ liệu |

Khi kiểm thử, hãy so sánh **cấu trúc và giá trị object Java**, không chỉ đếm tổng hàng SQL. Ví dụ hai hàng SQL cùng `order_id = 501` phải tạo ra **một** `OrderView` chứa **hai** dòng. Cũng nên thử thay đổi thứ tự cột trong `SELECT` nhưng giữ nguyên alias để bảo đảm mapper dựa vào tên thay vì chỉ số cột.

## 8. Ghi nhớ và thực hành

Khi nhận một `ResultSet` từ `LEFT JOIN`, hãy làm theo thứ tự:

1. Xác định **cha** là bảng nào và điều kiện truy vấn có thực sự giữ được cha không.
2. Kiểm tra có hàng kết quả hay không. Không có hàng khác với có cha nhưng không có con.
3. Dùng **khóa không nullable của bảng con** để xác định hàng con có tồn tại trong kết quả không; kiểm tra `wasNull()` ngay sau getter kiểu nguyên thủy.
4. Với 1–0..1, tạo một đối tượng con khi có khóa; nếu không, biểu diễn sự vắng mặt theo hợp đồng DTO.
5. Với 1–0..N, gom cha theo khóa, chỉ thêm con khi khóa con có giá trị; dùng danh sách rỗng cho cha chưa có con.
6. Nếu nối nhiều tập con hoặc phân trang, kiểm soát việc trùng con và nguy cơ cắt ngang tập con.

**Bài tập tự thực hành:** mở rộng ví dụ đơn hàng để chỉ trả các dòng có `quantity > 1` mà vẫn giữ đơn không có dòng phù hợp. Thử chuyển điều kiện từ `ON` sang `WHERE` và giải thích vì sao số lượng cha thay đổi. Sau đó thêm quan hệ `order_notes`, tái hiện việc trùng `LineView`, rồi dùng `Set<Long>` theo đơn hàng để tránh thêm cùng một dòng nhiều lần. Điều quan trọng nhất là kiểm thử cả trường hợp con tồn tại nhưng **một thuộc tính con là `NULL`**: không được nhầm nó với con hoàn toàn không tồn tại.
