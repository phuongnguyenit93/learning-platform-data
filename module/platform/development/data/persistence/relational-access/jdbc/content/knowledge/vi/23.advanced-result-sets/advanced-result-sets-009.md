# Phân biệt cập nhật ResultSet và câu SQL cập nhật tường minh trong JDBC

Với **JDBC**, nhiều lập trình viên quen đọc dữ liệu bằng `PreparedStatement.executeQuery()`, lấy `ResultSet` rồi thực thi `UPDATE` riêng để sửa hàng. Ít người để ý rằng JDBC còn có loại **`ResultSet` cập nhật được** (*updatable result set*): con trỏ vừa đọc hàng, vừa có thể gọi `updateXxx(...)` và `updateRow()` để yêu cầu ghi thay đổi về cơ sở dữ liệu.

Hai kỹ thuật cùng phục vụ thao tác CRUD nhưng **không tương đương về tính khả chuyển, khả năng kiểm soát điều kiện cập nhật, phát hiện xung đột đồng thời và chi phí vận hành**. Một `ResultSet` được yêu cầu cập nhật được có thể bị driver hạ xuống chế độ chỉ đọc. Khi thành công, câu lệnh SQL được driver thực thi thay mặt ứng dụng cũng không nhất thiết có điều kiện và cách xử lý xung đột giống một câu `UPDATE ... WHERE ...` mà lập trình viên chủ động viết.

Bài thuộc chương **ResultSet nâng cao** của module **JDBC**. Mục tiêu là hiểu đúng các API `CONCUR_UPDATABLE`, `updateXxx()`, `updateRow()`, `deleteRow()`, `insertRow()` và so sánh chúng với `PreparedStatement.executeUpdate()`. Qua các ví dụ với `Connection`, `DataSource`, SQL tham số hóa, transaction và optimistic locking, bạn sẽ biết lựa chọn cách cập nhật phù hợp với môi trường và yêu cầu nghiệp vụ.

## 1. Hai con đường ghi dữ liệu trong JDBC

Giả sử ứng dụng quản lý giá sản phẩm. Bảng minh họa:

```sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    price DECIMAL(12, 2) NOT NULL,
    version BIGINT NOT NULL
);

INSERT INTO products (id, name, price, version)
VALUES (101, 'Notebook', 50000.00, 1);
```

Cú pháp dữ liệu số và định nghĩa bảng ở đây mang tính minh họa; có thể cần điều chỉnh cho hệ quản trị đang dùng. `version` là cột do ứng dụng quản lý để hỗ trợ kiểm soát cập nhật đồng thời.

**Cách A — cập nhật thông qua `ResultSet`:**

```text
Connection
   │
   ▼
PreparedStatement (CONCUR_UPDATABLE)
   │ executeQuery()
   ▼
ResultSet.next() → định vị hàng có id = 101
   │
   ├─ updateBigDecimal("price", ...)
   │      (thay đổi trong bộ đệm cập nhật của ResultSet)
   │
   └─ updateRow()
          └─ Driver thực hiện thao tác cập nhật ở database
```

**Cách B — viết `UPDATE` trực tiếp:**

```text
Connection
   │
   ▼
PreparedStatement("UPDATE products SET price = ? WHERE id = ?")
   │ setBigDecimal(), setLong()
   ▼
executeUpdate()
   │
   └─ Database chạy SQL → trả số hàng bị tác động
```

Khác biệt cốt lõi là **ai kiểm soát câu lệnh ghi và điều kiện của nó**:

- Với `ResultSet` cập nhật được, ứng dụng thay các cột của **hàng con trỏ đang đứng** và đề nghị driver ghi lại. Driver quyết định cơ chế SQL/cursor cụ thể để tìm và cập nhật hàng.
- Với `UPDATE` tường minh, ứng dụng chỉ rõ **bảng, tập cột, điều kiện `WHERE` và biểu thức cập nhật**, nhận số hàng bị tác động để kiểm tra hợp đồng nghiệp vụ.

Cả hai đều bị chi phối bởi transaction, ràng buộc, quyền và cơ chế khóa của database. Sự tồn tại của API `ResultSet.updateRow()` không tự bảo đảm transaction an toàn hay không mất dữ liệu khi hai yêu cầu cùng sửa một bản ghi.

## 2. ResultSet có ba đặc tính cần phân biệt

Một `ResultSet` có **type**, **concurrency** và **holdability**. Chúng không phải cùng một thuộc tính:

| Đặc tính | Giá trị JDBC tiêu biểu | Vai trò |
| --- | --- | --- |
| **Type** | `TYPE_FORWARD_ONLY` | Con trỏ chủ yếu di chuyển tiến bằng `next()`; thường đơn giản hơn. |
| **Type** | `TYPE_SCROLL_INSENSITIVE` / `TYPE_SCROLL_SENSITIVE` | Cho phép khả năng cuộn hoặc quan sát thay đổi theo ngữ nghĩa và mức hỗ trợ của driver. |
| **Concurrency** | `CONCUR_READ_ONLY` | Không cho sửa hàng thông qua API cập nhật `ResultSet`. |
| **Concurrency** | `CONCUR_UPDATABLE` | Yêu cầu một `ResultSet` có thể cập nhật hàng được chọn. |
| **Holdability** | `CLOSE_CURSORS_AT_COMMIT` / `HOLD_CURSORS_OVER_COMMIT` | Quy định khả năng con trỏ còn mở sau `commit()` theo hỗ trợ driver. |

**Scrollable không đồng nghĩa updatable**. `TYPE_SCROLL_INSENSITIVE` chỉ liên quan khả năng định vị con trỏ và mức nhạy với thay đổi; muốn sửa hàng qua `ResultSet` vẫn cần `CONCUR_UPDATABLE`.

Yêu cầu ở thời điểm tạo statement:

```java
String sql = "SELECT id, name, price, version FROM products WHERE id = ?";

try (PreparedStatement statement = connection.prepareStatement(
        sql,
        ResultSet.TYPE_FORWARD_ONLY,
        ResultSet.CONCUR_UPDATABLE)) {

    statement.setLong(1, 101L);

    try (ResultSet rs = statement.executeQuery()) {
        int actualConcurrency = rs.getConcurrency();
        int actualType = rs.getType();

        if (actualConcurrency != ResultSet.CONCUR_UPDATABLE) {
            throw new SQLFeatureNotSupportedException(
                    "Driver did not supply an updatable ResultSet");
        }

        // Chỉ bắt đầu updateXxx() khi rs.next() trả true.
    }
}
```

Đoạn này giả định `connection` do tầng gọi sở hữu, đã import các lớp `java.sql` cần thiết. Driver có thể **từ chối** yêu cầu bằng `SQLException`/`SQLFeatureNotSupportedException` hoặc **hạ cấp** cursor về `CONCUR_READ_ONLY` rồi phát `SQLWarning`. Vì vậy, không chỉ nhìn vào hai hằng đã truyền cho `prepareStatement(...)` mà kết luận `ResultSet` chắc chắn cập nhật được.

Khi cần, có thể thăm dò khả năng công bố qua `DatabaseMetaData.supportsResultSetConcurrency(type, concurrency)`. Tuy nhiên, phương thức này chỉ cho biết khả năng **chung**, không chứng minh mọi câu `SELECT` cụ thể có thể cập nhật. Hãy kiểm tra `rs.getConcurrency()` trên kết quả thật và xử lý ngoại lệ khi thực thi.

## 3. Các API cập nhật của ResultSet hoạt động theo hai giai đoạn

Khi `ResultSet` đang trỏ tới một hàng hợp lệ:

```java
rs.updateBigDecimal("price", new BigDecimal("57500.00"));
rs.updateString("name", "Notebook A5");

// Chỉ lúc này mới yêu cầu ghi thay đổi của hàng hiện tại:
rs.updateRow();
```

Hai giai đoạn phải được phân biệt:

1. `updateXxx(column, value)` thiết lập giá trị mới của cột trong **bộ đệm cập nhật cho hàng hiện tại** của `ResultSet`. Lời gọi này **không thay thế** việc ghi bằng `updateRow()`.
2. `updateRow()` yêu cầu cập nhật hàng hiện tại trong database. Nó có thể phát sinh `SQLException` nếu hàng không còn cập nhật được, bị xung đột, vi phạm ràng buộc hoặc kết nối có vấn đề.

Các phương thức liên quan:

| API | Công dụng | Giới hạn cần nhớ |
| --- | --- | --- |
| `updateString()`, `updateInt()`, `updateBigDecimal()`, `updateObject()`... | Đặt giá trị mới cho cột của hàng hiện tại | Không bảo đảm đã ghi xuống database cho đến khi `updateRow()` thành công. |
| `updateNull(column)` | Gán SQL `NULL` cho cột | Cột `NOT NULL` hoặc ràng buộc khác có thể từ chối khi cập nhật. |
| `updateRow()` | Gửi thay đổi của hàng hiện tại về database | Phải kiểm tra lỗi và trạng thái transaction; không trả số hàng như `executeUpdate()`. |
| `cancelRowUpdates()` | Hủy các `updateXxx()` còn **chưa gửi** cho hàng hiện tại | Không hoàn tác bản ghi đã được `updateRow()` hoặc commit thành công. |
| `refreshRow()` | Yêu cầu làm mới giá trị hàng từ nguồn dữ liệu | Có thể xóa những cập nhật cục bộ chưa gửi; hành vi khả dụng phụ thuộc driver/concurrency. |
| `deleteRow()` | Yêu cầu xóa hàng hiện tại | Cần cursor cập nhật được; trạng thái con trỏ sau xóa tùy driver. |
| `moveToInsertRow()`, `insertRow()`, `moveToCurrentRow()` | Ghi một hàng mới qua con trỏ | Không thay thế quy tắc kiểm tra ràng buộc hoặc nhu cầu lấy generated keys. |
| `rowUpdated()`, `rowDeleted()`, `rowInserted()` | Hỏi trạng thái hàng nếu driver cung cấp | Khả năng phát hiện thay đổi và ý nghĩa kết quả tùy loại `ResultSet` và driver. |

Những phương thức trên thao tác với **con trỏ và hàng hiện tại**. Vì vậy, trước khi `updateRow()` hay `deleteRow()` cần gọi `next()` hoặc định vị con trỏ thành công; không gọi khi còn ở **trước hàng đầu**, sau hàng cuối hoặc ở hàng không hợp lệ.

**Phân biệt hủy cập nhật cục bộ và rollback transaction:**

```java
rs.updateBigDecimal("price", new BigDecimal("60000.00"));
rs.cancelRowUpdates();  // Hủy giá trị pending trong ResultSet.

// Nếu đã rs.updateRow() thành công trước đó, cancelRowUpdates()
// KHÔNG phải cơ chế hoàn tác transaction. Khi chưa commit,
// muốn hoàn tác thay đổi đã thực thi phải dùng connection.rollback().
```

Đừng gọi `refreshRow()` như cách “lưu” thay đổi. Nó có mục đích **đọc lại** hàng, có thể làm mất các thay đổi trong bộ đệm của `ResultSet` chưa được ghi bằng `updateRow()`.

## 4. Ví dụ hoàn chỉnh: sửa một hàng qua ResultSet

Ví dụ Java sau đặt hai phương thức trong cùng DAO: một phương thức sửa qua `ResultSet`, một phương thức sửa bằng SQL tường minh. **Tầng gọi sở hữu `Connection` và transaction**; DAO không đóng kết nối được truyền vào, không tự ý `commit()` hoặc `rollback()`.

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;
import java.util.Objects;

public final class ProductPriceDao {
    private ProductPriceDao() {
    }

    // Cách A: cập nhật thông qua ResultSet có thể sửa được.
    public static void updateViaResultSet(
            Connection connection, long id, BigDecimal newPrice)
            throws SQLException {

        Objects.requireNonNull(connection, "connection");
        requirePrice(newPrice);

        String sql =
                "SELECT id, price FROM products WHERE id = ?";

        try (PreparedStatement statement = connection.prepareStatement(
                sql,
                ResultSet.TYPE_FORWARD_ONLY,
                ResultSet.CONCUR_UPDATABLE)) {

            statement.setLong(1, id);

            try (ResultSet rs = statement.executeQuery()) {
                if (rs.getConcurrency() != ResultSet.CONCUR_UPDATABLE) {
                    throw new SQLFeatureNotSupportedException(
                            "This query did not get an updatable ResultSet");
                }
                if (!rs.next()) {
                    throw new SQLException("Product does not exist: " + id);
                }

                rs.updateBigDecimal("price", newPrice);
                rs.updateRow(); // Yêu cầu driver ghi thay đổi của hàng.
            }
        }
    }

    // Cách B: SQL UPDATE tường minh, nhận được row count.
    public static boolean updateViaSql(
            Connection connection, long id, BigDecimal newPrice)
            throws SQLException {

        Objects.requireNonNull(connection, "connection");
        requirePrice(newPrice);

        String sql = "UPDATE products SET price = ? WHERE id = ?";

        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setBigDecimal(1, newPrice);
            statement.setLong(2, id);

            int changed = statement.executeUpdate();
            if (changed > 1) {
                throw new SQLException(
                        "Expected at most one updated product, got " + changed);
            }
            return changed == 1;
        }
    }

    private static void requirePrice(BigDecimal value) {
        if (value == null || value.signum() < 0) {
            throw new IllegalArgumentException(
                    "Price must be non-negative");
        }
    }
}
```

Đối với dữ liệu `id=101`, gọi phương thức thứ nhất có thể cập nhật `price` nếu driver cung cấp `ResultSet` thật sự cập nhật được. Nếu driver không hỗ trợ, nó báo lỗi; **không được âm thầm báo thành công**.

Phương thức thứ hai không yêu cầu cursor cập nhật được, đồng thời trả về `boolean` dựa trên số hàng SQL ảnh hưởng. `false` có nghĩa `UPDATE` không ảnh hưởng hàng nào; trong ví dụ đơn giản này thường là không tìm thấy khóa `id`, nhưng ở các truy vấn có điều kiện phiên bản hoặc điều kiện nghiệp vụ, `0` còn có thể là **xung đột điều kiện**. Nếu cần phân biệt, service phải đọc thêm dữ liệu hoặc thiết kế kết quả rõ ràng.

**Điểm tương đồng:** cả hai phương thức đều dùng tham số `?`, chứ không nối trực tiếp giá trị người dùng vào SQL. Cả hai có thể ném `SQLException` do quyền truy cập, ràng buộc `CHECK`, lỗi kết nối hoặc lỗi transaction, và cùng phải tham gia đúng phạm vi giao dịch mà bên gọi quản lý.

**Điểm khác:** `updateViaResultSet()` trước tiên phải `SELECT` hàng để lấy con trỏ; còn `updateViaSql()` có thể cập nhật trực tiếp với một câu `UPDATE`. Trong nhiều tình huống CRUD đơn giản, SQL tường minh ít bước hơn, dễ nhận biết điều kiện ghi hơn và có hành vi dễ kiểm thử hơn.

## 5. Vì sao một câu SELECT có thể không cho ResultSet cập nhật được?

JDBC cho phép yêu cầu `CONCUR_UPDATABLE`, nhưng việc **xác định hàng nguồn** và thực hiện cập nhật phụ thuộc database/driver. Một số trường hợp thường làm query không thích hợp cho updatable result set:

- Câu `SELECT` lấy dữ liệu từ nhiều bảng qua `JOIN`, khó xác định hàng nguồn cần sửa.
- `GROUP BY`, `DISTINCT`, hàm tổng hợp hoặc biểu thức kết quả không ánh xạ trực tiếp về một cột có thể sửa.
- Query thiếu khóa chính/định danh hàng cần thiết hoặc chứa alias/biểu thức mà driver không cập nhật được.
- `VIEW` không cập nhật được, hoặc có trigger/rule làm thay đổi ngữ nghĩa cập nhật view.
- Driver không hỗ trợ tổ hợp `ResultSet` type và concurrency được yêu cầu.
- Quyền của tài khoản kết nối chỉ đủ `SELECT` nhưng không đủ `UPDATE`.
- Các giới hạn riêng của SQL dialect, truy vấn hoặc cấu hình cursor/server.

Ví dụ:

```sql
-- Thường dễ nhận dạng hàng nguồn hơn:
SELECT id, price
FROM products
WHERE id = ?;

-- Có thể không hỗ trợ ResultSet cập nhật:
SELECT c.id, c.name, SUM(o.total)
FROM customers c
JOIN orders o ON o.customer_id = c.id
GROUP BY c.id, c.name;
```

Một query đơn giản trên một bảng với khóa chính cũng **không bảo đảm** updatable result set trong mọi hệ quản trị. Hãy kiểm tra `getConcurrency()`, tài liệu driver và thử trên database/phiên bản thật.

### Metadata dùng để thăm dò, không để kết luận tuyệt đối

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.ResultSet;
import java.sql.SQLException;

public static boolean advertisesUpdatableForwardOnly(
        Connection connection) throws SQLException {

    DatabaseMetaData meta = connection.getMetaData();

    return meta.supportsResultSetConcurrency(
            ResultSet.TYPE_FORWARD_ONLY,
            ResultSet.CONCUR_UPDATABLE);
}
```

`true` chỉ có nghĩa driver/database **công bố khả năng chung** cho tổ hợp này. Một truy vấn `JOIN` hoặc query tính toán vẫn có thể chỉ trả `CONCUR_READ_ONLY` hoặc ném lỗi. Nếu `false`, phương thức `PreparedStatement.executeUpdate()` với SQL tường minh thường là hướng khả chuyển hơn.

Khi có thông báo driver hạ cấp, kiểm tra `statement.getWarnings()` và `resultSet.getWarnings()` nếu phù hợp; xử lý `SQLWarning` là bước chẩn đoán, không tự biến kết quả thành updatable.

## 6. Thao tác INSERT và DELETE qua ResultSet có gì khác SQL tường minh?

Ngoài `updateRow()`, `ResultSet` cập nhật được còn có API chèn và xóa hàng. Ví dụ chỉ mang tính minh họa khi query/cursor tương thích:

```java
String sql = "SELECT id, name, price, version FROM products";

try (PreparedStatement statement = connection.prepareStatement(
        sql,
        ResultSet.TYPE_SCROLL_INSENSITIVE,
        ResultSet.CONCUR_UPDATABLE);
     ResultSet rs = statement.executeQuery()) {

    if (rs.getConcurrency() != ResultSet.CONCUR_UPDATABLE) {
        throw new SQLFeatureNotSupportedException(
                "Updatable ResultSet unavailable");
    }

    rs.moveToInsertRow();
    rs.updateLong("id", 102L);
    rs.updateString("name", "Pen");
    rs.updateBigDecimal("price", new BigDecimal("12500.00"));
    rs.updateLong("version", 1L);
    rs.insertRow();
    rs.moveToCurrentRow();
}
```

Đoạn code trên yêu cầu import `Connection`, `PreparedStatement`, `ResultSet`, `BigDecimal`, `SQLFeatureNotSupportedException` và phụ thuộc driver hỗ trợ tổ hợp scrollable + updatable. Khi chèn qua `ResultSet`, phải gán các cột bắt buộc hoặc có giá trị mặc định phù hợp. `moveToInsertRow()` dùng **hàng đệm đặc biệt để chèn**, không phải di chuyển đến hàng đã tồn tại. `moveToCurrentRow()` quay lại vị trí con trỏ trước khi chuyển sang hàng chèn; cách hiển thị hàng vừa chèn trong `ResultSet` đang mở tùy driver.

Xóa hàng hiện tại:

```java
if (rs.next()) {
    rs.deleteRow(); // Xóa hàng mà con trỏ đang đứng.
}
```

**Không đọc lại dữ liệu của hàng vừa xóa mà không kiểm tra khả năng driver**: trạng thái hàng và vị trí con trỏ sau `deleteRow()` có thể khác nhau. Những API `rowDeleted()`, `rowInserted()` hoặc `rowUpdated()` cũng không phải cơ chế xác nhận giao dịch đã commit.

So với hai câu SQL tường minh:

```sql
INSERT INTO products (id, name, price, version)
VALUES (?, ?, ?, ?);

DELETE FROM products WHERE id = ?;
```

SQL tường minh có ưu thế là dễ nhìn thấy điều kiện thao tác, trả `affected row count` từ `executeUpdate()`, kết hợp `RETURN_GENERATED_KEYS` (nếu driver hỗ trợ), điều kiện `WHERE` theo version và các tính năng SQL cần thiết. API `ResultSet.insertRow()` không phải giải pháp chung để nhận khóa tự sinh tương đương mọi driver.

## 7. Xung đột đồng thời: cập nhật ResultSet không tự tránh lost update

Đây là điểm quan trọng nhất khi so sánh hai cách. Giả sử bảng `products` có:

```text
id=101, price=50_000, version=1
```

Hai người dùng A và B cùng đọc sản phẩm để sửa:

```text
Thời gian   Transaction A                 Transaction B
---------   ---------------------------   ---------------------------
t1          SELECT price → 50_000
t2                                          SELECT price → 50_000
t3          Chọn giá mới 55_000
t4                                          Chọn giá mới 60_000
t5          Ghi giá 55_000; COMMIT
t6                                          Ghi giá 60_000; COMMIT
                                             (nếu DB cho phép ghi đè)
```

Kết quả cuối có thể là `60_000`; thay đổi của A mất. Đây là **lost update** ở mô hình đọc–sửa–ghi. Hành vi thực tế có thể khác: một transaction bị chặn, deadlock, báo lỗi hoặc ngăn xung đột do isolation/driver. Nhưng gọi `updateRow()` **không tự tạo ra hợp đồng optimistic locking thống nhất**.

Với `ResultSet` cập nhật được, JDBC không yêu cầu ứng dụng ghi rõ điều kiện `WHERE version = ?` cho thao tác do driver sinh. Một driver có thể kiểm tra nhiều giá trị gốc, khóa hàng, dùng câu SQL có định danh bản ghi hoặc cơ chế khác. Vì vậy, không thể kết luận “`updateRow()` luôn kiểm tra version” hay “`updateRow()` luôn ghi đè” nếu chưa xem hành vi sản phẩm cụ thể.

### SQL tường minh và optimistic locking

Cách dễ kiểm soát hơn là quản lý `version` ở mức ứng dụng. Sau khi đọc phiên bản hiện tại, ghi:

```sql
UPDATE products
SET price = ?, version = version + 1
WHERE id = ? AND version = ?;
```

Ví dụ Java:

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public final class OptimisticProductDao {
    private OptimisticProductDao() {
    }

    public static boolean updatePrice(
            Connection connection,
            long productId,
            long expectedVersion,
            BigDecimal newPrice) throws SQLException {

        if (newPrice == null || newPrice.signum() < 0) {
            throw new IllegalArgumentException("Invalid product price");
        }

        String sql =
                "UPDATE products " +
                "SET price = ?, version = version + 1 " +
                "WHERE id = ? AND version = ?";

        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setBigDecimal(1, newPrice);
            statement.setLong(2, productId);
            statement.setLong(3, expectedVersion);

            int updated = statement.executeUpdate();
            if (updated > 1) {
                throw new SQLException(
                        "Unexpected number of updated products: " + updated);
            }
            return updated == 1;
        }
    }
}
```

Hai transaction cùng đọc `version=1`. Nếu A cập nhật thành công, hàng có `version=2`. Câu `UPDATE` của B với `WHERE version = 1` sẽ **không khớp** sau khi A đã commit, hoặc có thể phải chờ/báo xung đột theo mức cô lập. Khi `executeUpdate()` trả `0`, service nhận diện **không tìm thấy hoặc phiên bản đã thay đổi** và quyết định báo xung đột, tải lại hoặc thử lại theo nghiệp vụ.

Cột `version` là phần của mô hình dữ liệu, phải được duy trì nhất quán bởi **mọi đường ghi**, không chỉ một DAO. Nếu các lệnh khác cập nhật `price` nhưng không tăng `version`, optimistic locking sẽ mất tác dụng. Cần thêm ràng buộc và kiểm thử đồng thời phù hợp.

**Lưu ý:** nếu transaction chạy ở isolation đặc biệt, database có thể ném `SQLException` do serialization/deadlock thay vì trả `0`. DAO cần xử lý cả số hàng và ngoại lệ; không nên tự xem mọi `SQLException` là “version mismatch”.

## 8. Cập nhật tương đối: SQL tường minh giúp tránh đọc–tính–ghi không cần thiết

Với nghiệp vụ “giảm tồn kho nếu đủ số lượng”, thay vì đọc `stock` sang Java rồi gán giá trị mới qua `updateInt(...)`:

```java
// Đọc số lượng hiện tại rồi ghi lại số lượng tính trong Java
// có nguy cơ tạo xung đột nếu hai transaction cùng thao tác.
int current = rs.getInt("available");
rs.updateInt("available", current - quantity);
rs.updateRow();
```

Có thể biểu đạt thao tác và ràng buộc bằng một câu SQL:

```sql
UPDATE inventory
SET available = available - ?
WHERE product_id = ? AND available >= ?;
```

Với `PreparedStatement`:

```java
String sql =
        "UPDATE inventory " +
        "SET available = available - ? " +
        "WHERE product_id = ? AND available >= ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setInt(1, quantity);
    statement.setLong(2, productId);
    statement.setInt(3, quantity);

    int changed = statement.executeUpdate();
    if (changed != 1) {
        // Không có sản phẩm phù hợp hoặc không đủ hàng.
    }
}
```

Giả sử `quantity > 0` đã được kiểm tra và `product_id` là duy nhất. Câu `UPDATE` có điều kiện tránh một vòng **đọc → tính trong Java → ghi toàn bộ giá trị** khi chỉ cần một phép biến đổi nguyên tử ở database. Hành vi tranh chấp khóa vẫn phụ thuộc engine/isolation, nhưng **điều kiện dữ liệu cần bảo vệ được biểu đạt trong chính câu lệnh ghi**.

Đây là lý do quan trọng để ưu tiên SQL tường minh cho số dư, số lượng, phiên bản và các ràng buộc nghiệp vụ. Không phải vì `ResultSet` cập nhật được “sai”, mà vì API con trỏ không làm rõ những phép biến đổi tương đối và điều kiện xung đột bằng SQL do ứng dụng kiểm soát.

## 9. Transaction, auto-commit và vòng đời tài nguyên

Cả hai cách cập nhật đều thực thi trên `Connection` và tuân theo transaction của kết nối đó. Khi một nghiệp vụ gồm nhiều câu lệnh:

1. Xác định **ai sở hữu transaction** (service, transaction manager hay DAO tự mượn connection).
2. Dùng **cùng `Connection`** cho mọi thao tác thuộc transaction.
3. Nếu tự quản lý transaction, dùng `autoCommit=false`, `commit()` khi tất cả thành công và `rollback()` khi lỗi.
4. Đóng `ResultSet`, `PreparedStatement`/`CallableStatement` bằng `try-with-resources`; nếu mượn từ pool thì trả kết nối theo đúng hợp đồng.
5. Nếu thay đổi `autoCommit`, isolation hoặc read-only, ghi nhận và **phục hồi sau khi transaction đã kết thúc**, không trong khi giao dịch chưa rõ trạng thái.

Với `ResultSet` cập nhật được, cần chú ý thêm:

- Giữ `ResultSet` mở trong lúc gọi `updateXxx()` và `updateRow()`. Đừng trả cursor ra service rồi đóng connection trước khi nó được sử dụng.
- Nếu `updateRow()` thành công nhưng transaction chưa commit, `connection.rollback()` vẫn là cơ chế hoàn tác giao dịch; `cancelRowUpdates()` không thay thế rollback.
- `close()` của con trỏ không phải lệnh commit và không phải bảo đảm rollback.
- `commit()` có thể đóng cursor tùy `ResultSet` holdability và driver. Không dùng `ResultSet` sau commit với giả định cursor luôn tồn tại và tiếp tục cập nhật được.
- Driver có thể tải hàng hoặc giữ server cursor/lock lâu hơn trong quá trình duyệt kết quả; tránh giữ ResultSet cập nhật được mở qua thao tác mạng ngoài DB hoặc tương tác người dùng.
- Nếu `rollback()` thất bại, không bật `setAutoCommit(true)` một cách máy móc, vì thay đổi chế độ auto-commit có thể commit phần giao dịch còn hoạt động. Kết nối không rõ trạng thái cần được loại bỏ theo cơ chế của connection pool.

### Một transaction bên ngoài sử dụng DAO

```java
// Đoạn minh họa cho Connection đã do service sở hữu.
connection.setAutoCommit(false);
try {
    boolean updated = ProductPriceDao.updateViaSql(
            connection, 101L, new BigDecimal("57500.00"));

    if (!updated) {
        throw new SQLException("No matching product");
    }

    writePriceAudit(connection, 101L); // Helper cùng Connection.
    connection.commit();
} catch (SQLException failure) {
    try {
        connection.rollback();
    } catch (SQLException rollbackError) {
        failure.addSuppressed(rollbackError);
    }
    throw failure;
}
```

Đây là **đoạn lõi minh họa**, chưa bao gồm phần lưu và khôi phục `autoCommit`, đóng kết nối và xử lý trường hợp rollback thất bại. Trong mã ứng dụng hoàn chỉnh, bên sở hữu transaction phải thực hiện các bước này trước khi trả kết nối về pool. `writePriceAudit(...)` là helper giả định không tự mở kết nối mới, để bản ghi kiểm toán và giá sản phẩm cùng transaction.

## 10. Hiệu năng: không chỉ là số lần gọi JDBC

So sánh:

| Khía cạnh | `ResultSet` cập nhật được | `UPDATE` tường minh qua `PreparedStatement` |
| --- | --- | --- |
| Bước SQL | Thường phải `SELECT`, định vị hàng, rồi `updateRow()` | Có thể dùng **một câu `UPDATE`** khi không cần đọc dữ liệu trước |
| Khả năng biểu đạt điều kiện | Phụ thuộc query đã tạo cursor và SQL driver sinh ra | `WHERE` có thể kết hợp ID, version, điều kiện tồn kho, trạng thái |
| Khả năng xác nhận hàng bị tác động | Không trả `int update count` trực tiếp từ `updateRow()` | `executeUpdate()` trả số hàng bị tác động |
| Phụ thuộc driver | Cao hơn; cần query/type/concurrency tương thích | Thường khả chuyển hơn với SQL DML đơn giản |
| Đọc–ghi cùng một hàng | Thuận tiện cho ứng dụng thao tác với hàng đã chọn | Có thể cần SELECT riêng nếu phải hiển thị hoặc dùng giá trị cũ |
| Khả năng viết phép cập nhật tương đối | Bị giới hạn bởi API `updateXxx()` | Dễ viết `SET balance = balance + ?` và điều kiện nguyên tử |
| Nhiều hàng cập nhật | Duyệt cursor và `updateRow()` từng hàng; hiệu quả phụ thuộc driver | Có thể dùng một `UPDATE WHERE...` hoặc `executeBatch()` |
| Khóa/cursor | Có thể liên quan server cursor, row lock và thời gian giữ cursor | Lock và kế hoạch phụ thuộc SQL/engine, dễ kiểm tra qua câu DML |
| Xử lý kết quả đồng thời | Driver có thể có cơ chế phát hiện riêng | Ứng dụng chủ động dùng version, row count, SQLState |
| Độ rõ ràng và review SQL | Một phần câu lệnh ghi nằm trong driver | Lập trình viên nhìn được SQL ghi và điều kiện dữ liệu |

Không nên tuyên bố `UPDATE` tường minh luôn nhanh hơn. Có hệ quản trị/driver tối ưu cursor update tốt; với màn hình chỉnh sửa từng dòng, một `ResultSet` updatable có thể tiện dụng. Tuy nhiên, một quy trình server-side CRUD thường ưu tiên SQL tường minh vì dễ kiểm soát **kết quả và điều kiện cập nhật**, không phải chỉ vì benchmark.

Để đo hiệu năng đúng, dùng cùng schema, chỉ mục, dữ liệu, isolation và số lượng bản ghi. Ghi nhận latency p95/p99, số round trip, thời gian giữ khóa/cursor, CPU/IO database, tỷ lệ retry và `SQLException`. Không so sánh `ResultSet` có `SELECT` đầu vào với một `UPDATE` khác hẳn ngữ nghĩa rồi kết luận về chi phí API.

## 11. Generated keys, trigger và giá trị đọc lại

Với `INSERT` tường minh, JDBC có cơ chế:

```java
PreparedStatement statement = connection.prepareStatement(
        "INSERT INTO products (name, price, version) VALUES (?, ?, ?)",
        java.sql.Statement.RETURN_GENERATED_KEYS);
```

Sau `executeUpdate()`, gọi `statement.getGeneratedKeys()` nếu driver hỗ trợ và câu SQL yêu cầu trả khóa. Cách nhận khóa không thống nhất hoàn toàn giữa driver; phải xác minh số dòng và kiểu khóa thực tế. `ResultSet.insertRow()` không phải một cam kết tương đương về cách nhận generated keys.

**Trigger, constraint và giá trị do database biến đổi** có thể ảnh hưởng cả hai kỹ thuật. Ví dụ trigger chuẩn hóa `name` hoặc tự cập nhật cột `updated_at`. Sau `updateRow()`, giá trị đang nằm trong bộ đệm của `ResultSet` không nhất thiết phản ánh ngay mọi thay đổi do server tự thực hiện. Có thể cân nhắc `refreshRow()` khi driver hỗ trợ và transaction cho phép, hoặc chạy `SELECT` lại để xác nhận giá trị đã lưu. Với SQL tường minh, ứng dụng cũng có thể cần `SELECT` tiếp theo hay cú pháp `RETURNING`/`OUTPUT` riêng của hệ quản trị để lấy dữ liệu server tạo ra.

Không nên suy từ việc `updateRow()` không ném lỗi rằng dữ liệu đã **commit** hoặc rằng trigger/constraint đã tạo ra đúng mọi kết quả nghiệp vụ. Cần kiểm tra transaction và các giả định dữ liệu có ý nghĩa.

## 12. Cách xử lý lỗi và phương án dự phòng

Khi yêu cầu `CONCUR_UPDATABLE`, có thể gặp:

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `getConcurrency() == CONCUR_READ_ONLY` | Driver hạ cấp yêu cầu hoặc query không đủ điều kiện | Đọc `SQLWarning`, xem lại query và tài liệu; chọn SQL `UPDATE` tường minh nếu phù hợp |
| `SQLFeatureNotSupportedException` | Driver không hỗ trợ tính năng/concurrency | Sử dụng phương án `PreparedStatement.executeUpdate()` được kiểm thử |
| `updateRow()` báo hàng không cập nhật được | Hàng thiếu định danh, query phức tạp, quyền không đủ hoặc xung đột | Xem SQLState/vendor code, quyền, khóa và cơ chế driver |
| `updateRow()` báo lỗi constraint | Giá trị mới vi phạm CHECK/UNIQUE/FOREIGN KEY hoặc kiểu | Sửa dữ liệu, rollback theo phạm vi transaction |
| Giá trị sau cập nhật khác mong đợi | Trigger, tính toán phía server, cache của ResultSet | Đọc lại dữ liệu bằng `SELECT` hoặc `refreshRow()` khi được hỗ trợ |
| Cập nhật đồng thời ghi đè nhau | Thiếu điều kiện phiên bản hoặc cơ chế đồng bộ phù hợp | Dùng optimistic locking, khóa hay isolation thích hợp |
| Lỗi ngay sau khi ghi nhưng trước khi lấy kết quả | Kết nối/timeout khiến trạng thái commit chưa rõ | Đối soát, dùng idempotency; không tự retry mù quáng |

Một chiến lược fallback **chỉ được thực hiện khi biết chắc lệnh ghi chưa xảy ra**. Ví dụ, `ResultSet` bị hạ xuống `CONCUR_READ_ONLY` trước khi gọi bất kỳ `updateXxx()` hay `updateRow()` nào, ứng dụng có thể chọn đường `PreparedStatement UPDATE` được hỗ trợ. Ngược lại, nếu `updateRow()` đã được gửi và phát sinh lỗi mạng, không tự chạy lại `UPDATE` chỉ vì không nhận được phản hồi: có thể server đã cập nhật và commit.

Khi phân loại lỗi, ưu tiên `SQLException.getSQLState()`, `getErrorCode()`, lớp ngoại lệ và tài liệu driver. Không đọc mỗi chuỗi `getMessage()` để đoán rằng “lỗi tạm thời”, “đã ghi” hoặc “không được ghi”. Những lỗi rollback/đóng tài nguyên cũng cần được giữ lại để chẩn đoán.

## 13. Bài thực hành: so sánh hai chiến lược trên cùng dữ liệu

**Chuẩn bị:** Dùng một database thử nghiệm, tạo bảng `products` như phần 1 và nạp vài hàng. Xác định tên DB, phiên bản JDBC driver, cấu hình connection pool, và các quyền đọc/ghi.

**Bài 1 — kiểm tra tính năng:**

1. Gọi `DatabaseMetaData.supportsResultSetConcurrency(TYPE_FORWARD_ONLY, CONCUR_UPDATABLE)`.
2. Chạy query `SELECT id, price FROM products WHERE id = ?` với `CONCUR_UPDATABLE`.
3. Ghi lại `rs.getType()`, `rs.getConcurrency()` và warnings. Nếu bị hạ cấp, không cố gọi `updateRow()` để minh họa “thành công”.
4. Thử thay query bằng một `JOIN` hoặc `GROUP BY` và quan sát khác biệt.

**Bài 2 — cập nhật và đọc lại:**

1. Đổi giá `id=101` bằng `updateBigDecimal(...)` rồi `updateRow()`, khi driver hỗ trợ.
2. Đọc lại bằng một `SELECT` mới và xác nhận giá trị.
3. Lặp lại với `UPDATE products SET price=? WHERE id=?`, kiểm tra `executeUpdate()` trả `0` hoặc `1`.
4. Thử `cancelRowUpdates()` trước `updateRow()` rồi đọc lại để xác nhận chưa ghi; so sánh với `rollback()` sau khi lệnh ghi đã chạy nhưng chưa commit.

**Bài 3 — kiểm tra cạnh tranh:**

1. Mở hai `Connection` A và B, dùng hai transaction độc lập. Cả hai đọc giá và phiên bản ban đầu.
2. Cho A cập nhật, commit. Sau đó cho B cập nhật dựa trên dữ liệu cũ bằng `ResultSet` và ghi nhận **thành công, blocking hay lỗi**, không giả định trước kết quả.
3. Lặp với câu `UPDATE ... SET version=version+1 WHERE id=? AND version=?`. Kiểm tra khi version không còn khớp: số hàng cập nhật bằng `0` hoặc database báo xung đột theo isolation.
4. Trình bày lý do vì sao kiểu kết quả và lỗi quan sát được phụ thuộc driver/database/isolation.

**Bài 4 — hiệu năng và tính khả chuyển:**

1. Chạy cập nhật một hàng và nhiều hàng ở cả hai phương án nếu driver hỗ trợ; đo thời gian, số câu SQL/round trip và thời gian giữ transaction.
2. Thử `executeBatch()` với `PreparedStatement` cho nhiều hàng, so với vòng lặp `updateRow()` khi khả thi.
3. Ghi một bảng quyết định: khi nào chọn ResultSet updatable, khi nào chọn SQL tường minh; nêu bằng chứng từ driver và workload thật.

### Ma trận kiểm thử tối thiểu

| Kịch bản | Kỳ vọng cần xác minh |
| --- | --- |
| `SELECT` đơn giản có khóa chính | Có hỗ trợ `CONCUR_UPDATABLE` không, `getConcurrency()` báo gì |
| Query `JOIN`/aggregate | Driver từ chối, hạ cấp hay vẫn cho phép với giới hạn |
| `updateXxx()` nhưng chưa `updateRow()` | Không coi thay đổi cục bộ là dữ liệu đã commit |
| `cancelRowUpdates()` | Chỉ hủy pending updates của hàng hiện tại |
| `updateRow()` thành công rồi `rollback()` | Thay đổi chưa commit được hoàn tác nếu database/engine hỗ trợ transaction |
| Hai người cùng sửa một sản phẩm | Ghi nhận lost update, chờ khóa hoặc lỗi xung đột thực tế |
| `UPDATE ... WHERE id=? AND version=?` | Phát hiện version mismatch qua update count hoặc lỗi có thể phân loại |
| Driver không hỗ trợ cursor update | DAO có phương án SQL tường minh, không báo thành công giả |
| Trigger thay đổi dữ liệu | Kiểm chứng bằng truy vấn lại thay vì tin bộ đệm cursor |
| Lỗi mạng sau khi gửi cập nhật | Không retry thao tác ghi khi kết quả chưa rõ |

## 14. Tổng kết quyết định kỹ thuật

Không nên đánh giá hai kỹ thuật bằng tiêu chí “cách nào ít code hơn” một cách đơn lẻ:

1. **ResultSet cập nhật được** phù hợp khi ứng dụng thật sự cần thao tác với một hàng đang duyệt, driver hỗ trợ query cụ thể và hợp đồng cập nhật không đòi hỏi nhiều điều kiện ghi tùy biến.
2. **SQL `UPDATE` tường minh** phù hợp hơn cho nhiều nghiệp vụ CRUD phía server vì điều kiện `WHERE`, phép biến đổi `SET` và `executeUpdate()` thể hiện rõ ý định, giúp kiểm soát row count, optimistic locking và batch.
3. **Yêu cầu `CONCUR_UPDATABLE` không phải bảo đảm.** Luôn kiểm tra `ResultSet.getConcurrency()`, xử lý cảnh báo/ngoại lệ và thử với database thật.
4. **`updateXxx()` chưa ghi ngay.** `updateRow()` mới yêu cầu cập nhật; `cancelRowUpdates()` không thay thế `rollback()`.
5. **Transaction và cạnh tranh quyết định tính đúng.** Cả hai cách đều cần transaction phù hợp, kiểm tra xung đột, ràng buộc và phương án khôi phục khi thất bại.
6. **Đo hiệu năng và khả chuyển trên workload thực tế.** SQL driver sinh cho cursor, kế hoạch truy vấn và lock có thể khác hẳn điều suy ra từ API.

**Kết luận:** `ResultSet` cập nhật được là một khả năng nâng cao của JDBC, nhưng không phải cách thay thế tổng quát cho `PreparedStatement.executeUpdate()`. Hãy dùng nó khi lợi ích thao tác theo con trỏ là thực tế và đã kiểm chứng; khi cần phát biểu chính xác điều kiện cập nhật, kiểm soát xung đột, số hàng bị ảnh hưởng và tính khả chuyển, **SQL cập nhật tường minh thường là lựa chọn dễ bảo trì hơn**.
