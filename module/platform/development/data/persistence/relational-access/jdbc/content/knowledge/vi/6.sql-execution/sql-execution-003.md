# Đọc số dòng bị ảnh hưởng và phân biệt với số dòng kết quả

Trong **JDBC (Java Database Connectivity)**, khi Java thực thi SQL trên cơ sở dữ liệu quan hệ, kết quả của một câu lệnh có thể là **số dòng được câu lệnh tác động** (*update count*) hoặc **một tập dữ liệu để đọc** (*result set*). Đây là hai dạng thông tin khác nhau. Ví dụ, `UPDATE` có thể báo tác động đến 3 dòng, còn `SELECT` có thể trả về 3 bản ghi; con số tình cờ bằng nhau nhưng ý nghĩa và API JDBC dùng để lấy chúng hoàn toàn khác.

Bài học thuộc chương **Thực thi SQL**, tập trung vào cách đọc update count bằng `executeUpdate()`, `executeLargeUpdate()`, `getUpdateCount()`, và phân biệt chúng với số bản ghi thu được từ `ResultSet` hoặc hàm tổng hợp `COUNT(*)` trong SQL. Bạn cũng sẽ gặp các giá trị đặc biệt `0`, `-1` và kết quả thực thi theo lô (*batch*).

## 1. Hai loại kết quả SQL dễ bị nhầm lẫn

Giả sử bảng `orders` có cấu trúc đơn giản:

~~~sql
CREATE TABLE orders (
    id          BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status      VARCHAR(30) NOT NULL
);
~~~

Xét hai câu lệnh:

~~~sql
UPDATE orders
SET status = 'SHIPPED'
WHERE customer_id = 42 AND status = 'PAID';

SELECT id, status
FROM orders
WHERE customer_id = 42;
~~~

Câu `UPDATE` cần trả lời: **Có bao nhiêu dòng được báo là bị tác động bởi thao tác cập nhật?** JDBC cung cấp *update count* qua `executeUpdate()` hoặc API tương ứng.

Câu `SELECT` cần trả lời: **Những dòng dữ liệu nào được trả về, và giá trị từng cột là gì?** JDBC cung cấp một `ResultSet` và ta duyệt các dòng bằng `next()`. Muốn biết số dòng trong kết quả, có thể đếm lúc duyệt hoặc thực hiện một truy vấn đếm riêng như `SELECT COUNT(*) ...`.

~~~text
                            SQL
                             │
              ┌──────────────┴─────────────┐
              │                            │
        INSERT / UPDATE / DELETE        SELECT
              │                            │
       executeUpdate()                executeQuery()
              │                            │
              ▼                            ▼
         int updateCount                ResultSet
         "bị tác động mấy dòng?"         "dòng nào, dữ liệu gì?"
              │                            │
             0,1,2,...                  rows.next()
                                           │
                                     Đếm khi duyệt hoặc
                                     truy vấn COUNT(*) riêng
~~~

Bảng phân biệt nhanh:

| Câu hỏi | API / SQL phù hợp | Kết quả | Ý nghĩa |
| --- | --- | --- | --- |
| `UPDATE` đã tác động mấy dòng? | `PreparedStatement.executeUpdate()` | `int` | Update count của lệnh vừa chạy |
| Có bao nhiêu bản ghi được trả về từ `SELECT`? | Duyệt `ResultSet.next()` và tự đếm | `int` / `long` do ứng dụng đếm | Số lần con trỏ chuyển đến một dòng thành công |
| Có bao nhiêu bản ghi trong DB thỏa điều kiện? | `SELECT COUNT(*) FROM ... WHERE ...` | Một giá trị số trong `ResultSet` | Số lượng bản ghi theo điều kiện SQL tại thời điểm thực thi |
| Một lệnh có thể trả `ResultSet` hoặc update count? | `Statement.execute(...)`, rồi `getResultSet()` / `getUpdateCount()` | Tùy kiểu kết quả | Cần kiểm tra loại kết quả trước khi đọc |
| Update có thể ảnh hưởng hơn giới hạn `int`? | `executeLargeUpdate()` | `long` | Update count 64-bit, nếu driver hỗ trợ |

Không có phương thức JDBC chuẩn tên `ResultSet.getUpdateCount()`; update count gắn với **`Statement`**, trong khi dữ liệu hàng được đọc từ **`ResultSet`**.

## 2. Lấy số dòng bị ảnh hưởng bằng `executeUpdate()`

Với câu lệnh DML không trả một tập kết quả, mẫu dùng phổ biến là:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class OrderUpdates {
    private final DataSource dataSource;

    public OrderUpdates(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public int markShipped(long customerId) throws SQLException {
        String sql = """
                UPDATE orders
                SET status = ?
                WHERE customer_id = ? AND status = ?
                """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {

            statement.setString(1, "SHIPPED");
            statement.setLong(2, customerId);
            statement.setString(3, "PAID");

            // Không trả ResultSet: trả về update count.
            int affectedRows = statement.executeUpdate();
            return affectedRows;
        }
    }
}
~~~

Đoạn mã trên dùng Java text block (Java 15 trở lên). Nếu dùng Java cũ, thay text block bằng chuỗi SQL thông thường. `DataSource` phải được ứng dụng cấu hình trước, driver phù hợp phải có ở runtime và bảng minh họa phải tồn tại.

Khi gọi:

~~~java
OrderUpdates updates = new OrderUpdates(dataSource);
int affectedRows = updates.markShipped(42L);
System.out.println("Số dòng được báo là tác động: " + affectedRows);
~~~

Giả sử các dòng phù hợp và cơ sở dữ liệu báo update count là 3, kết quả sẽ là `3`. Nếu không có dòng nào thỏa `WHERE`, thông thường kết quả là `0`.

**Điều kiện quan trọng:** JDBC định nghĩa giá trị trả về của `executeUpdate()` là update count cho các câu DML có đếm được dòng tác động; với lệnh SQL không trả số dòng như một số câu DDL, API này trả `0`. Vì vậy không được dùng kết quả `0` để khẳng định lệnh SQL không chạy.

### Những loại lệnh thường dùng với `executeUpdate()`

| SQL | Cách dùng điển hình | Ý nghĩa update count |
| --- | --- | --- |
| `INSERT` | `statement.executeUpdate()` | Số dòng được báo là chèn |
| `UPDATE` | `statement.executeUpdate()` | Số dòng được báo là cập nhật/tác động |
| `DELETE` | `statement.executeUpdate()` | Số dòng được báo là xóa |
| DDL, chẳng hạn `CREATE TABLE` | `statement.executeUpdate()` khi driver hỗ trợ lệnh này | Thường trả `0` vì không có số dòng DML để đếm |
| `SELECT` thông thường | Dùng `executeQuery()` | Lấy `ResultSet`; không dùng `executeUpdate()` để đọc hàng |

Các câu lệnh đặc biệt như `MERGE`, `UPSERT`, stored procedure, hoặc `UPDATE ... RETURNING` có thể có ngữ nghĩa và hỗ trợ API khác nhau theo DB/driver. Không áp đặt một cách gọi JDBC duy nhất cho mọi cú pháp mở rộng của nhà cung cấp.

## 3. Hiểu đúng giá trị `0` từ executeUpdate

`0` **không nhất thiết là lỗi**. Với lệnh cập nhật, nó thường cho biết không có dòng nào được báo là bị tác động. Chẳng hạn:

~~~sql
UPDATE orders
SET status = 'CANCELLED'
WHERE id = 999999 AND status = 'PENDING';
~~~

Nếu không có dòng phù hợp, update count có thể bằng 0 và JDBC **không tự ném `SQLException`** chỉ vì vậy. Ứng dụng phải quyết định đây là tình huống hợp lệ hay xung đột nghiệp vụ.

Cũng cần phân biệt ba điều:

- **Không tìm thấy dòng**: điều kiện `WHERE` không khớp bản ghi nào.
- **Dòng tồn tại nhưng điều kiện khác không khớp**: ví dụ `id` đúng nhưng trạng thái đã chuyển khỏi `PENDING`.
- **Dòng đã mang sẵn giá trị được gán**: với một số DB/driver, số dòng được báo có thể phản ánh *dòng khớp điều kiện* hoặc *dòng thực sự thay đổi*, tùy cấu hình và ngữ nghĩa hệ quản trị.

Ví dụ, câu `UPDATE products SET price = 100 WHERE id = 1` khi `price` đã bằng `100` có thể dẫn tới cách diễn giải count khác nhau giữa những hệ quản trị/cấu hình driver. Nếu nghiệp vụ cần biết **dòng đã tồn tại hay chưa**, hoặc **giá trị thực tế thay đổi hay không**, hãy thiết kế điều kiện SQL hoặc truy vấn bổ sung phù hợp; không suy luận quá mức từ count.

Với DDL, `executeUpdate()` có thể trả `0` dù bảng đã được tạo thành công. Do đó:

~~~java
int count = statement.executeUpdate("CREATE TABLE sample (id INT)");
// count == 0 không có nghĩa lệnh CREATE TABLE thất bại.
~~~

Mã chỉ là minh họa; cú pháp DDL và quyền tạo bảng phụ thuộc cơ sở dữ liệu. Thành công hay thất bại của DDL được xác định bằng việc lệnh thực thi hoàn tất hoặc ném ngoại lệ, không phải do count lớn hơn 0.

## 4. Đọc tập kết quả bằng `executeQuery()` và `ResultSet`

`executeQuery()` trả về một `ResultSet` cho truy vấn tạo tập dữ liệu:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class OrderQueries {
    private final DataSource dataSource;

    public OrderQueries(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public long countReturnedOrders(long customerId) throws SQLException {
        String sql = """
                SELECT id, status
                FROM orders
                WHERE customer_id = ?
                ORDER BY id
                """;

        long rowCount = 0L;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {

            statement.setLong(1, customerId);

            try (ResultSet rows = statement.executeQuery()) {
                while (rows.next()) {
                    long id = rows.getLong("id");
                    String status = rows.getString("status");

                    // Ứng dụng đã thực sự đi qua một dòng kết quả.
                    rowCount++;

                    // Đây là xử lý dữ liệu từng dòng, chỉ để minh họa.
                    System.out.println(id + " -> " + status);
                }
            }
        }

        return rowCount;
    }
}
~~~

Ý nghĩa các lời gọi:

- `statement.executeQuery()` trả `ResultSet` và **không trả số dòng**.
- `rows.next()` trả `true` khi con trỏ chuyển đến một hàng dữ liệu hợp lệ; trả `false` khi không còn hàng.
- `rows.getLong("id")` và `rows.getString("status")` đọc **giá trị cột ở dòng hiện tại**.
- Biến `rowCount` do **ứng dụng tự đếm**, không phải update count lấy từ JDBC.
- Vòng lặp có thể không chạy lần nào nếu truy vấn không có bản ghi phù hợp. `ResultSet` vẫn là một kết quả hợp lệ, chỉ là rỗng.

Với kết quả lớn, duyệt tất cả chỉ để đếm có thể tốn thời gian, chiếm kết nối và truyền dữ liệu không cần thiết. Trong nhiều tình huống, truy vấn tổng hợp `COUNT(*)` hoặc thiết kế phân trang phù hợp hơn.

### `ResultSet.getRow()` không phải phương thức lấy tổng số dòng

`ResultSet.getRow()` trả **vị trí dòng hiện tại** theo đánh số bắt đầu từ 1, hoặc `0` khi con trỏ không ở trên dòng hợp lệ. Nó **không tự cho biết tổng số dòng của toàn bộ kết quả**.

Một số `ResultSet` kiểu *scrollable* hỗ trợ di chuyển đến dòng cuối rồi dùng `getRow()` để lấy vị trí cuối. Tuy nhiên:

- `ResultSet` mặc định thường là `TYPE_FORWARD_ONLY`, không hỗ trợ tùy ý gọi `last()`.
- Driver có thể cần buffer/di chuyển nhiều dữ liệu để định vị dòng cuối.
- Việc di chuyển con trỏ ảnh hưởng đến trạng thái đọc tiếp.
- Đếm bằng cách duyệt không đồng nghĩa với “tổng số bản ghi trong DB” nếu truy vấn có `LIMIT`/`OFFSET` hoặc xử lý khác.

Vì vậy, với nhu cầu đếm trong DB, nên ưu tiên một câu SQL đếm rõ ràng.

## 5. SQL `COUNT(*)`: một dòng kết quả chứa một giá trị đếm

Muốn biết có bao nhiêu đơn hàng phù hợp một điều kiện, ta có thể hỏi ngay cơ sở dữ liệu:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE customer_id = 42 AND status = 'PENDING';
~~~

Nếu có 1.250 đơn phù hợp, truy vấn **trả một dòng** và cột số đếm có giá trị `1250`.

~~~text
SELECT COUNT(*) ...                -- Một câu truy vấn tổng hợp
          │
          ▼
       ResultSet
       ┌───────────┐
       │ count     │
       ├───────────┤
       │ 1250      │  ← Một dòng chứa số 1250
       └───────────┘

Số dòng trong ResultSet = 1
Giá trị cột COUNT(*)   = 1250
Update count           = không áp dụng cho SELECT này
~~~

Mẫu Java:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public static long countPending(DataSource dataSource, long customerId)
        throws SQLException {

    String sql = """
            SELECT COUNT(*)
            FROM orders
            WHERE customer_id = ? AND status = ?
            """;

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql)) {

        statement.setLong(1, customerId);
        statement.setString(2, "PENDING");

        try (ResultSet rows = statement.executeQuery()) {
            if (!rows.next()) {
                throw new SQLException("COUNT(*) did not return a row");
            }
            return rows.getLong(1);
        }
    }
}
~~~

`getLong(1)` đọc giá trị cột đầu tiên; `COUNT(*)` thường dùng kiểu số nguyên có miền rộng, nên đọc bằng `long` phù hợp hơn `int` trong nhiều trường hợp. Tên và kiểu SQL trả về có thể khác theo driver, nhưng pattern truy vấn/đọc cột vẫn như trên.

**Hai chi tiết dễ nhầm:**

1. `SELECT COUNT(*)` thông thường (không có `GROUP BY` hoặc `HAVING` loại bỏ nhóm) trả **một dòng**, kể cả khi số bản ghi thỏa điều kiện là 0.
2. `SELECT category, COUNT(*) FROM products GROUP BY category` trả **nhiều dòng**, mỗi dòng chứa giá trị đếm của **một nhóm**. Số dòng của `ResultSet` khi ấy là số nhóm, không phải tổng các giá trị `COUNT(*)`.

Đếm trước rồi thực hiện một `SELECT` sau đó cũng có thể cho kết quả khác nếu dữ liệu thay đổi giữa hai truy vấn. Nếu yêu cầu nhất quán, đặt cả hai trong giao dịch với mức cô lập phù hợp, hoặc dùng giải pháp DB-specific.

## 6. So sánh bằng một tình huống thực tế

Giả sử đang có năm đơn hàng ở trạng thái `PENDING` cho khách 42:

| Bước | SQL | API | Giá trị nhận được |
| --- | --- | --- | --- |
| 1 | `SELECT COUNT(*) FROM orders WHERE customer_id=42 AND status='PENDING'` | `executeQuery()` | Một `ResultSet` chứa số `5` |
| 2 | `UPDATE orders SET status='PAID' WHERE customer_id=42 AND status='PENDING'` | `executeUpdate()` | `int` cập nhật, ví dụ `5` |
| 3 | `SELECT id FROM orders WHERE customer_id=42 AND status='PAID'` | `executeQuery()` | `ResultSet` chứa các dòng `id` (có thể nhiều hơn năm dòng) |

Ở bước 1, **`5` là một giá trị nằm trong tập kết quả**. Ở bước 2, **`5` là update count của một lệnh thay đổi dữ liệu**. Ở bước 3, số dòng có thể nhiều hơn năm nếu trước đó đã có các đơn `PAID`.

Ngay cả khi bước 1 và bước 2 được chạy sát nhau, không đảm bảo hai con số bằng nhau dưới mọi điều kiện: giao dịch khác có thể thay đổi dữ liệu, điều kiện `WHERE` khác nhau, hoặc driver/DB có quy tắc đếm khác. Dùng count như một tín hiệu, không xem nó là bằng chứng hoàn chỉnh về trạng thái dữ liệu.

## 7. `executeLargeUpdate()` và giới hạn số nguyên

`Statement.executeUpdate(...)` và `PreparedStatement.executeUpdate()` trả về `int`. Nếu một thao tác có thể tác động số dòng rất lớn (vượt khả năng biểu diễn của `int`), JDBC bổ sung API `executeLargeUpdate()` trả về `long`:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

// Ví dụ: xử lý một lượng dữ liệu lớn.
// Driver cần hỗ trợ JDBC large update API.
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
             "DELETE FROM old_events WHERE created_at < ?")) {

    statement.setTimestamp(1, cutoff);
    long affectedRows = statement.executeLargeUpdate();

    System.out.println("Affected rows: " + affectedRows);
}
~~~

`dataSource` và `cutoff` được cung cấp từ bên ngoài; không xóa dữ liệu thật khi chỉ học ví dụ. Driver có thể báo `SQLFeatureNotSupportedException` nếu phương thức large update không được hỗ trợ; vì vậy cần xác minh phiên bản JDBC driver khi chọn API này.

**Chọn kiểu trả về theo bài toán:**

| Phương thức | Kiểu trả về | Dùng khi |
| --- | --- | --- |
| `executeUpdate()` | `int` | Lượng dòng cập nhật nằm trong miền `int` |
| `executeLargeUpdate()` | `long` | Cần biểu diễn count lớn hơn giới hạn `int` và driver hỗ trợ |
| `getUpdateCount()` | `int` | Đọc update count của kết quả hiện tại sau `execute()` |
| `getLargeUpdateCount()` | `long` | Phiên bản count `long` của kết quả hiện tại nếu driver hỗ trợ |

Không nên tự ép `long` xuống `int` khi số dòng có thể lớn; phép ép kiểu sẽ mất thông tin.

## 8. `Statement.execute()` và `getUpdateCount()`

Không phải lúc nào ứng dụng cũng biết trước câu SQL sẽ trả về bảng dữ liệu hay update count. JDBC có phương thức tổng quát `Statement.execute(sql)`:

~~~java
boolean hasResultSet = statement.execute(sql);
~~~

Giá trị boolean mang ý nghĩa:

- `true`: **kết quả đầu tiên** là `ResultSet`; đọc bằng `statement.getResultSet()`.
- `false`: kết quả đầu tiên là update count **hoặc không có kết quả nào**; cần gọi `statement.getUpdateCount()` để phân biệt.

Ví dụ:

~~~java
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.Statement;
import java.sql.SQLException;

// sql là câu lệnh do ứng dụng kiểm soát, không ghép input trực tiếp.
try (Connection connection = dataSource.getConnection();
     Statement statement = connection.createStatement()) {

    boolean hasRows = statement.execute(sql);

    if (hasRows) {
        try (ResultSet rows = statement.getResultSet()) {
            while (rows.next()) {
                System.out.println(rows.getObject(1));
            }
        }
    } else {
        int count = statement.getUpdateCount();

        if (count == -1) {
            System.out.println("Không có update count");
        } else {
            System.out.println("Số dòng tác động: " + count);
        }
    }
}
~~~

### Khi nào `getUpdateCount()` trả `-1`?

Theo hợp đồng JDBC, `getUpdateCount()` trả **số dòng tác động của kết quả hiện tại**, hoặc `-1` khi **kết quả hiện tại là `ResultSet` hoặc không còn kết quả nào**.

Vì thế, phải kiểm tra ngữ cảnh:

| Tình trạng hiện tại | `execute(...)` / `getUpdateCount()` |
| --- | --- |
| Kết quả là `ResultSet` | `execute(...)` trả `true`; `getUpdateCount()` trả `-1` |
| Kết quả là update count `0` | `execute(...)` trả `false`; `getUpdateCount()` trả `0` |
| Kết quả là update count `n > 0` | `execute(...)` trả `false`; `getUpdateCount()` trả `n` |
| Không có kết quả hiện tại | `execute(...)` có thể trả `false`; `getUpdateCount()` trả `-1` |

**Đừng nhầm `-1` với “truy vấn tác động âm một dòng”**. Nó là giá trị báo **không có update count ở vị trí hiện tại**.

### Khi câu lệnh trả nhiều kết quả

Stored procedure hoặc SQL đặc thù của DB có thể trả nhiều result set và/hoặc update count. Sau khi xử lý kết quả hiện tại, dùng `getMoreResults()` để chuyển tiếp và tiếp tục kiểm tra `getUpdateCount()`:

~~~java
boolean hasRows = statement.execute(sql);

while (true) {
    if (hasRows) {
        try (ResultSet rows = statement.getResultSet()) {
            while (rows.next()) {
                // Đọc dữ liệu cần thiết.
                rows.getObject(1);
            }
        }
    } else {
        int count = statement.getUpdateCount();
        if (count == -1) {
            break; // Không còn kết quả.
        }

        System.out.println("Update count: " + count);
    }

    hasRows = statement.getMoreResults();
}
~~~

`getMoreResults()` mặc định có thể đóng `ResultSet` hiện tại khi chuyển tiếp; ví dụ đã đóng result set bằng `try-with-resources`. Mức hỗ trợ nhiều kết quả tùy DB/driver. Trong ứng dụng thông thường với một câu `SELECT` hoặc `UPDATE` rõ ràng, ưu tiên `executeQuery()` và `executeUpdate()` vì dễ đọc hơn.

## 9. Thực thi batch: mỗi lệnh có một giá trị count

Với `PreparedStatement.addBatch()` và `executeBatch()`, JDBC trả về một **mảng `int[]`**, không phải một số duy nhất:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.Statement;
import java.sql.SQLException;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
             "UPDATE orders SET status = ? WHERE id = ?")) {

    statement.setString(1, "SHIPPED");
    statement.setLong(2, 101L);
    statement.addBatch();

    statement.setString(1, "SHIPPED");
    statement.setLong(2, 102L);
    statement.addBatch();

    int[] counts = statement.executeBatch();

    for (int i = 0; i < counts.length; i++) {
        int count = counts[i];

        if (count >= 0) {
            System.out.println("Item " + i + ": " + count);
        } else if (count == Statement.SUCCESS_NO_INFO) {
            System.out.println("Item " + i + ": success, count unknown");
        } else if (count == Statement.EXECUTE_FAILED) {
            System.out.println("Item " + i + ": failed");
        }
    }
}
~~~

Các giá trị có ý nghĩa:

| Giá trị | Hằng số | Ý nghĩa |
| --- | --- | --- |
| `0` hoặc số dương | Số lượng cụ thể | Số dòng được báo là tác động bởi mục batch tương ứng |
| `-2` | `Statement.SUCCESS_NO_INFO` | Mục đó thành công nhưng driver không cung cấp số dòng tác động |
| `-3` | `Statement.EXECUTE_FAILED` | Mục đó thất bại (khi driver tiếp tục xử lý sau lỗi và báo kết quả từng mục) |

Khi batch gặp lỗi, `executeBatch()` có thể ném `BatchUpdateException`. `getUpdateCounts()` của exception cung cấp thông tin về các câu lệnh đã được xử lý; tùy driver, mảng có thể chỉ chứa các mục thành công trước khi dừng, hoặc chứa thêm `EXECUTE_FAILED` khi driver tiếp tục thực hiện sau lỗi. Nếu dùng `executeLargeBatch()`, kết quả là `long[]` với các giá trị sentinel tương ứng.

Không nên chỉ cộng tất cả phần tử của `counts` một cách mù quáng, vì `-2` và `-3` không phải số lượng dòng âm. Nếu hệ thống yêu cầu batch “tất cả thành công hoặc không gì thay đổi”, cần bọc các lệnh trong giao dịch được quản lý, xử lý rollback và đánh giá hành vi thực tế của driver/DB.

## 10. Ứng dụng update count vào kiểm soát nghiệp vụ

Update count không chỉ dành cho log; nó là tín hiệu hữu ích để xác định thao tác có thực sự khớp dòng mong đợi hay không.

Ví dụ, một yêu cầu cập nhật theo **optimistic locking** dựa trên cột `version`:

~~~sql
UPDATE products
SET price = ?, version = version + 1
WHERE id = ? AND version = ?;
~~~

Mẫu Java:

~~~java
public static boolean updatePrice(
        java.sql.Connection connection,
        long productId,
        int expectedVersion,
        java.math.BigDecimal newPrice) throws java.sql.SQLException {

    String sql = """
            UPDATE products
            SET price = ?, version = version + 1
            WHERE id = ? AND version = ?
            """;

    try (java.sql.PreparedStatement statement =
                 connection.prepareStatement(sql)) {

        statement.setBigDecimal(1, newPrice);
        statement.setLong(2, productId);
        statement.setInt(3, expectedVersion);

        int affected = statement.executeUpdate();
        if (affected > 1) {
            throw new java.sql.SQLException(
                    "Unexpected row count for primary key update: " + affected);
        }

        return affected == 1;
    }
}
~~~

Giả sử `products.id` là khóa chính: **`1`** thường cho biết một dòng khớp điều kiện id và version, **`0`** cho biết không có dòng khớp (bản ghi có thể đã bị xóa hoặc phiên bản đã thay đổi). Caller cần quyết định báo xung đột và có thể yêu cầu đọc lại dữ liệu.

Không nên lập trình kiểu:

~~~java
// Dễ gây hiểu nhầm nếu câu lệnh có thể tác động nhiều dòng.
if (statement.executeUpdate() > 0) {
    return true;
}
~~~

khi nghiệp vụ **đòi hỏi chính xác một dòng**. Với `UPDATE` theo khóa chính và điều kiện version, dùng `affected == 1` và xử lý `0` theo nghiệp vụ sẽ thể hiện ý định rõ ràng hơn.

### Count không thay thế transaction

`executeUpdate()` trả count không đồng nghĩa dữ liệu đã được commit vĩnh viễn. Nếu `autoCommit=false` và giao dịch bị rollback sau khi lệnh báo `1`, cập nhật đó vẫn có thể bị hoàn tác:

~~~text
connection.setAutoCommit(false)
    │
    ├── UPDATE ... → executeUpdate() trả 1
    ├── Một bước khác thất bại
    ├── connection.rollback()
    └── Dòng thay đổi trước đó bị hoàn tác theo giao dịch
~~~

Do đó, khi cần bảo đảm tính toàn vẹn của nhiều bước SQL, hãy dùng transaction rõ ràng, `commit()` khi thành công, `rollback()` khi thất bại và đóng tài nguyên. Với ứng dụng có transaction manager, để framework sở hữu transaction boundary và chỉ dùng update count như tín hiệu thực thi của câu lệnh.

## 11. Lệnh trả hàng đồng thời thay đổi dữ liệu: trường hợp riêng

Một số hệ quản trị cho phép cú pháp như:

~~~sql
UPDATE products
SET price = price + 10
WHERE id = 5
RETURNING id, price;
~~~

Đây là ví dụ về cú pháp **vendor-specific** (như PostgreSQL). Câu lệnh có tác dụng cập nhật dữ liệu nhưng đồng thời trả **các hàng**. Trong trường hợp này, API phù hợp để đọc kết quả và sự hỗ trợ của driver có thể khác với `UPDATE` thông thường; phải kiểm tra tài liệu driver/DB, có thể dùng `execute()` rồi phân tích `getResultSet()`.

**Không áp dụng máy móc** rằng mọi câu bắt đầu bằng chữ `UPDATE` đều bắt buộc phải gọi `executeUpdate()` hoặc không thể trả hàng. Ngược lại, một `SELECT` trả số lượng qua `COUNT(*)` vẫn là truy vấn trả `ResultSet`, dù trong kết quả có một số nguyên.

Khi cần lấy khóa vừa sinh từ `INSERT`, JDBC còn hỗ trợ `Statement.RETURN_GENERATED_KEYS` và `getGeneratedKeys()`. `executeUpdate()` có thể trả số dòng chèn, trong khi `getGeneratedKeys()` trả **ResultSet chứa các khóa**, là **hai kết quả với ý nghĩa riêng**:

~~~java
try (java.sql.PreparedStatement insert =
             connection.prepareStatement(
                     "INSERT INTO products(name) VALUES (?)",
                     java.sql.Statement.RETURN_GENERATED_KEYS)) {

    insert.setString(1, "Keyboard");
    int affected = insert.executeUpdate();

    try (java.sql.ResultSet keys = insert.getGeneratedKeys()) {
        if (affected == 1 && keys.next()) {
            long generatedId = keys.getLong(1);
            System.out.println("New ID: " + generatedId);
        }
    }
}
~~~

Cú pháp sinh khóa và mức hỗ trợ tùy DB/driver; `connection` là kết nối đã mở được truyền từ bên ngoài. `getGeneratedKeys()` không biến update count thành số dòng `ResultSet` và cũng không buộc kết quả khóa chứa đúng số dòng như count trong mọi trường hợp.

## 12. Bảng lỗi thường gặp và cách xử lý

| Nhầm lẫn | Hệ quả | Cách làm đúng |
| --- | --- | --- |
| Dùng `executeQuery()` cho `UPDATE` thông thường | Sai loại kết quả, có thể nhận `SQLException` | Dùng `executeUpdate()` cho DML không trả hàng |
| Dùng `executeUpdate()` cho `SELECT` thông thường | Không lấy được hàng dữ liệu, có thể nhận lỗi | Dùng `executeQuery()` và duyệt `ResultSet` |
| Thấy count `0` rồi coi là lỗi SQL | Xử lý sai trường hợp không có dòng khớp hoặc DDL thành công | Diễn giải theo loại câu lệnh và hợp đồng nghiệp vụ |
| Thấy `-1` từ `getUpdateCount()` rồi coi là trừ một dòng | Báo cáo sai số liệu | Hiểu `-1` là không có update count ở trạng thái hiện tại |
| Dùng `ResultSet.getRow()` để lấy tổng số dòng | Nhầm số thứ tự dòng hiện tại với tổng kết quả | Đếm khi duyệt hoặc truy vấn `COUNT(*)` |
| Coi số `COUNT(*)` là số dòng `ResultSet` | Nhầm “một dòng mang số đếm” với “nhiều dòng dữ liệu” | Đọc giá trị cột từ tập kết quả tổng hợp |
| Cộng `SUCCESS_NO_INFO` vào tổng batch | Tính toán âm và sai số | Kiểm tra các sentinel trước khi tổng hợp |
| Dùng update count để kết luận đã commit | Bỏ qua transaction/rollback | Quản lý transaction và kiểm tra kết quả cuối |
| Chỉ kiểm tra `affected > 0` khi cập nhật theo khóa chính | Bỏ sót trường hợp tác động nhiều dòng bất thường | Kiểm tra `affected == 1` nếu nghiệp vụ yêu cầu một dòng |
| Cho rằng `UPDATE...RETURNING` có cùng API với mọi `UPDATE` | Sai khi truy vấn trả tập hàng | Kiểm tra tính năng DB/driver và chọn API theo kiểu kết quả |

## 13. Câu hỏi tự kiểm tra

**Câu 1.** `UPDATE orders ...` trả `2` từ `executeUpdate()`. Số `2` có nghĩa gì?

Đó là **update count được driver báo cho câu lệnh vừa thực thi**, thường là hai dòng được tác động. Nó không nói rằng một `SELECT` tiếp theo chắc chắn trả đúng hai hàng hoặc rằng giao dịch đã commit.

**Câu 2.** `SELECT COUNT(*) FROM orders` trả số `500`. `ResultSet` chứa bao nhiêu dòng?

Với truy vấn tổng hợp không có `GROUP BY`, `ResultSet` thường chứa **một dòng** và một cột có giá trị `500`. Không phải 500 dòng.

**Câu 3.** `executeUpdate()` trả `0` có phải là `SQLException` không?

Không. Đây có thể là kết quả hợp lệ khi không có dòng DML nào khớp, hoặc với một câu DDL không có update count. Lỗi SQL được báo bằng ngoại lệ hoặc cơ chế lỗi tương ứng.

**Câu 4.** Khi `statement.execute(sql)` trả `false`, có chắc câu lệnh tác động 0 dòng?

Không. `false` chỉ cho biết kết quả đầu tiên **không phải `ResultSet`**. Hãy gọi `getUpdateCount()`: `0` là một count hợp lệ, `-1` báo không có update count hiện tại.

**Câu 5.** Khi `executeBatch()` trả `[1, -2, 0]`, tổng affected rows có phải bằng `-1` không?

Không. `-2` là `SUCCESS_NO_INFO`, nghĩa là mục batch thành công nhưng không biết số dòng tác động. Chỉ biết các mục khác có count lần lượt `1` và `0`; không thể tính tổng chính xác cho cả batch.

**Câu 6.** Vì sao optimistic locking thường kiểm tra `affected == 1`?

Vì với cập nhật theo khóa chính kèm version, đúng một dòng khớp cho thấy bản ghi đáp ứng điều kiện lúc câu lệnh thực thi. `0` có thể biểu thị bản ghi đã thay đổi hoặc không tồn tại; nếu nhiều hơn một dòng là điều bất thường cần điều tra.

**Điểm cần nhớ:** **`executeUpdate()` / `executeLargeUpdate()` trả số dòng được câu lệnh DML báo là tác động; `executeQuery()` trả `ResultSet` chứa các hàng dữ liệu; `SELECT COUNT(*)` trả một giá trị đếm nằm trong `ResultSet`.** Với `execute()` tổng quát, kiểm tra loại kết quả trước khi đọc `getUpdateCount()`; hiểu `0` và `-1` theo đúng ngữ cảnh. Luôn kiểm tra update count theo yêu cầu nghiệp vụ, đồng thời quản lý transaction và vòng đời JDBC riêng biệt.
