# Đánh số tham số và gán giá trị đúng vị trí trong JDBC

## 1. Vì sao vị trí tham số lại quan trọng?

Trong chương **Truy vấn tham số**, `PreparedStatement` là công cụ trung tâm của **JDBC (Java Database Connectivity)**, API để Java truy cập cơ sở dữ liệu quan hệ. Thay vì ghép dữ liệu trực tiếp vào chuỗi SQL, ta đặt dấu hỏi `?` tại những vị trí cần truyền giá trị và sử dụng các phương thức `setXxx(index, value)` để gán tham số.

Ví dụ, ứng dụng cần tìm đơn hàng của một khách có tổng tiền từ 500.000 đồng trở lên:

~~~sql
SELECT id, customer_id, total_amount
FROM orders
WHERE customer_id = ? AND total_amount >= ?
~~~

Hai dấu `?` biểu diễn **hai tham số riêng biệt**. Tham số đầu tiên là mã khách hàng, tham số thứ hai là mức tiền tối thiểu. Nếu đảo vị trí, câu lệnh có thể lỗi kiểu dữ liệu hoặc tệ hơn là chạy thành công nhưng trả kết quả sai.

Sau bài này, bạn có thể xác định chính xác thứ tự các tham số trong SQL, gán giá trị đúng vị trí và kiểu, xử lý tham số lặp, giá trị `NULL`, câu SQL động và các lỗi thường xảy ra khi tái sử dụng `PreparedStatement`.

## 2. Quy tắc số một: JDBC đếm tham số từ 1

Đối với `java.sql.PreparedStatement`, **chỉ số tham số bắt đầu từ 1**, không bắt đầu từ 0 như mảng Java. Đọc câu lệnh SQL **từ trái sang phải**, đánh số cho từng dấu `?` đóng vai trò *parameter marker*:

~~~text
SQL:  SELECT id FROM orders
      WHERE customer_id = ? AND total_amount >= ? AND status = ?
                          [1]                    [2]            [3]

Java: ps.setLong(1, customerId);
      ps.setBigDecimal(2, minimumTotal);
      ps.setString(3, status);
~~~

Nếu SQL có ba marker thì phải gán đúng các tham số có chỉ số **1, 2, 3**:

| Vị trí `?` | Biểu thức SQL tương ứng | Giá trị Java | Lệnh gán |
| --- | --- | --- | --- |
| 1 | `customer_id = ?` | `long customerId` | `ps.setLong(1, customerId)` |
| 2 | `total_amount >= ?` | `BigDecimal minimumTotal` | `ps.setBigDecimal(2, minimumTotal)` |
| 3 | `status = ?` | `String status` | `ps.setString(3, status)` |

Các điểm cần ghi nhớ:

- **Chỉ số phụ thuộc vị trí dấu `?` trong câu SQL**, không phụ thuộc thứ tự cột trong bảng, vị trí biến Java, thứ tự điều kiện khi bạn hình dung, hay vị trí cột trong `ResultSet`.
- **Mỗi dấu `?` là một vị trí độc lập**, ngay cả khi hai vị trí phải nhận cùng một giá trị.
- Bạn có thể gọi các phương thức gán theo thứ tự bất kỳ, nhưng **giá trị cuối cùng tại từng chỉ số** phải khớp đúng marker tương ứng trước khi thực thi.
- `setXxx(0, ...)` là sai vì JDBC không có tham số thứ 0. Dùng chỉ số vượt số lượng marker cũng sẽ gây lỗi.
- JDBC `PreparedStatement` chuẩn dùng tham số **theo vị trí**; không tự hỗ trợ cú pháp tên như `:customerId` của một số framework.

> **Phân biệt:** `ResultSet.getString(1)` cũng đếm cột từ 1, nhưng chỉ số cột trong `ResultSet` **độc lập** với chỉ số tham số của `PreparedStatement`.

## 3. Ví dụ hoàn chỉnh: ba tham số ở ba vị trí

Giả sử có bảng `orders`:

~~~sql
CREATE TABLE orders (
    id           BIGINT PRIMARY KEY,
    customer_id  BIGINT NOT NULL,
    total_amount DECIMAL(15, 2) NOT NULL,
    status       VARCHAR(30) NOT NULL,
    note         VARCHAR(500)
);
~~~

Phương thức sau tìm đơn hàng của một khách hàng theo số tiền tối thiểu và trạng thái:

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class OrderSearch {
    private final DataSource dataSource;

    public OrderSearch(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void printOrders(long customerId, BigDecimal minimumTotal,
                            String status) throws SQLException {
        String sql = """
                SELECT id, customer_id, total_amount, status
                FROM orders
                WHERE customer_id = ?
                  AND total_amount >= ?
                  AND status = ?
                ORDER BY id
                """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, customerId);        // customer_id = ?
            ps.setBigDecimal(2, minimumTotal); // total_amount >= ?
            ps.setString(3, status);          // status = ?

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    long id = rs.getLong("id");
                    BigDecimal total = rs.getBigDecimal("total_amount");
                    System.out.println(id + ": " + total);
                }
            }
        }
    }
}
~~~

Ví dụ sử dụng Java 17 (text block `"""` khả dụng từ Java 15) và một `DataSource` đã cấu hình. Một lần gọi:

~~~java
OrderSearch search = new OrderSearch(dataSource);
search.printOrders(
        42L,
        new BigDecimal("500000.00"),
        "PAID");
~~~

đặt **42** vào marker 1, **500000.00** vào marker 2 và **PAID** vào marker 3. `try-with-resources` đóng `ResultSet`, `PreparedStatement` và `Connection` sau khi truy vấn kết thúc.

**Cách tự kiểm tra:** đọc phần SQL trước, ghi lại danh sách marker theo thứ tự xuất hiện, sau đó đối chiếu từng lời gọi `setXxx`. Không đoán thứ tự dựa trên tên biến.

## 4. Mỗi marker phải được gán giá trị tương ứng

### 4.1. Gọi thiếu setter

~~~java
String sql = "SELECT id FROM orders WHERE customer_id = ? AND status = ?";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 42L);
    // Quên ps.setString(2, "PAID").
    try (ResultSet rs = ps.executeQuery()) {
        // Có thể bị SQLException do tham số 2 chưa được gán.
    }
}
~~~

Một marker chưa có giá trị hợp lệ sẽ khiến câu lệnh không thể thực thi đúng theo hợp đồng JDBC; driver thường báo lỗi thiếu tham số. **Không** được giả định marker chưa gán sẽ tự trở thành SQL `NULL`.

### 4.2. Dùng chỉ số 0 hoặc vượt phạm vi

~~~java
String sql = "SELECT id FROM orders WHERE customer_id = ?";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    // Sai: không có tham số thứ 0.
    // ps.setLong(0, 42L);

    // Sai: SQL chỉ có một dấu hỏi.
    // ps.setLong(2, 42L);

    // Đúng:
    ps.setLong(1, 42L);
}
~~~

### 4.3. Đảo vị trí nhưng vẫn đúng kiểu dữ liệu

Một lỗi nguy hiểm là hai marker cùng kiểu, ví dụ:

~~~sql
UPDATE orders
SET status = ?
WHERE status = ?
~~~

~~~java
// Có thể chạy không lỗi cú pháp hay kiểu, nhưng logic bị đảo!
ps.setString(1, "PENDING");
ps.setString(2, "PAID");
~~~

Đoạn trên chuyển các đơn `PAID` về `PENDING`. Nếu mục tiêu là đổi `PENDING` thành `PAID`, giá trị phải theo thứ tự ngược lại. Điều này cho thấy JDBC chỉ biết *vị trí và kiểu tham số*, không biết ý định nghiệp vụ của bạn.

### 4.4. Gán lặp một tham số

Trong một câu lệnh đã chuẩn bị, nếu gọi `setXxx` nhiều lần vào cùng chỉ số trước khi thực thi thì lời gọi sau cập nhật giá trị tham số tại vị trí đó:

~~~java
ps.setString(1, "PENDING");
ps.setString(1, "PAID"); // Giá trị vị trí 1 hiện là "PAID".
~~~

Đây không phải cách tạo một tham số mới. Muốn gán marker thứ hai, phải truyền **chỉ số 2**.

## 5. Cùng một giá trị xuất hiện nhiều lần vẫn phải gán nhiều vị trí

Giả sử trừ tiền khỏi một tài khoản, đồng thời kiểm tra số dư hiện tại ngay trong câu `UPDATE`:

~~~sql
UPDATE account
SET balance = balance - ?
WHERE id = ? AND balance >= ?
~~~

SQL có **ba** marker. Giá trị số tiền xuất hiện ở marker 1 và marker 3, nhưng JDBC **không tự hiểu rằng hai marker dùng chung một giá trị**:

| Marker | Mục đích | Giá trị phải gán |
| --- | --- | --- |
| 1 | Số tiền cần trừ | `amount` |
| 2 | ID tài khoản | `accountId` |
| 3 | Số dư tối thiểu cần có | `amount` |

~~~java
String sql = """
    UPDATE account
    SET balance = balance - ?
    WHERE id = ? AND balance >= ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setBigDecimal(1, amount);
    ps.setLong(2, accountId);
    ps.setBigDecimal(3, amount); // Cùng amount nhưng marker riêng.

    int updatedRows = ps.executeUpdate();
    if (updatedRows != 1) {
        throw new SQLException("Không có tài khoản hoặc không đủ số dư");
    }
}
~~~

Điều kiện `balance >= ?` cùng câu `UPDATE` còn giúp database kiểm tra và thay đổi số dư như một thao tác nguyên tử tùy ngữ nghĩa DBMS, tránh mẫu “đọc số dư, kiểm tra trong Java rồi cập nhật” dễ bị cạnh tranh đồng thời. Quy tắc giao dịch cho nhiều câu SQL vẫn cần được quản lý riêng.

## 6. Chọn `setXxx` phù hợp với kiểu dữ liệu

Đúng vị trí nhưng **sai kiểu** vẫn có thể gây lỗi chuyển đổi, mất dữ liệu hoặc kết quả không đúng mong muốn. Một số ánh xạ phổ biến:

| Dữ liệu Java | Phương thức | Kiểu cột SQL thường gặp |
| --- | --- | --- |
| `long` | `setLong(index, value)` | `BIGINT` |
| `int` | `setInt(index, value)` | `INTEGER` |
| `String` | `setString(index, value)` | `VARCHAR`, `CHAR` |
| `BigDecimal` | `setBigDecimal(index, value)` | `DECIMAL`, `NUMERIC` |
| `boolean` | `setBoolean(index, value)` | `BOOLEAN` nếu DBMS hỗ trợ |
| `java.sql.Date` | `setDate(index, value)` | `DATE` |
| `java.sql.Timestamp` | `setTimestamp(index, value)` | `TIMESTAMP` |
| Giá trị SQL `NULL` | `setNull(index, sqlType)` | Kiểu do `java.sql.Types` chỉ định |

Ví dụ với `LocalDate`:

~~~java
java.time.LocalDate createdOn = java.time.LocalDate.of(2026, 11, 16);
ps.setDate(1, java.sql.Date.valueOf(createdOn));
~~~

Với JDBC 4.2 và driver hỗ trợ ánh xạ `java.time`, `ps.setObject(1, createdOn)` cũng có thể phù hợp. Những kiểu không chuẩn hoặc do nhà cung cấp định nghĩa có thể yêu cầu kiểu SQL hoặc cách gán riêng.

### 6.1. Gán SQL NULL đúng vị trí và kiểu

Nếu điều kiện `? IS NULL` hoặc cột cập nhật cho phép `NULL`, hãy phân biệt `null` của Java với chuỗi chữ `"null"`. Ví dụ cập nhật ghi chú tùy chọn:

~~~java
String sql = "UPDATE orders SET note = ? WHERE id = ?";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    String note = null;
    if (note == null) {
        ps.setNull(1, java.sql.Types.VARCHAR);
    } else {
        ps.setString(1, note);
    }
    ps.setLong(2, 42L);
    ps.executeUpdate();
}
~~~

`setNull(1, Types.VARCHAR)` gán **SQL NULL** cho marker 1. Không thể bỏ lời gọi setter chỉ vì dữ liệu Java là `null`. Một số driver hỗ trợ `setObject(index, null)`, nhưng xác định kiểu SQL rõ ràng giúp tránh trường hợp không suy ra được kiểu tham số.

**Lưu ý:** `WHERE note = NULL` hoặc `WHERE note = ?` với marker nhận SQL `NULL` **không tương đương** `WHERE note IS NULL` trong SQL ba giá trị. Khi cần tìm giá trị NULL, dùng `IS NULL` hoặc xây dựng biểu thức thích hợp với DBMS.

## 7. Câu SQL động làm thay đổi thứ tự tham số

Một nhu cầu phổ biến là tìm đơn hàng với một số điều kiện **không bắt buộc**. Khi thêm/bớt các mệnh đề có `?`, chỉ số của các marker sau đó cũng thay đổi. Không nên hardcode `setString(3, ...)` nếu truy vấn hiện tại chỉ có hai marker.

Ví dụ phương thức dưới đây đặt trong một lớp Java phù hợp, chỉ ghép các **đoạn SQL cố định do lập trình viên kiểm soát**; dữ liệu người dùng vẫn được truyền bằng `setXxx`:

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public void searchOptionalFilters(
        DataSource dataSource,
        Long customerId,
        BigDecimal minimumTotal,
        String status) throws SQLException {

    StringBuilder sql = new StringBuilder(
            "SELECT id, total_amount FROM orders WHERE 1 = 1");

    if (customerId != null) {
        sql.append(" AND customer_id = ?");
    }
    if (minimumTotal != null) {
        sql.append(" AND total_amount >= ?");
    }
    if (status != null) {
        sql.append(" AND status = ?");
    }
    sql.append(" ORDER BY id");

    try (Connection connection = dataSource.getConnection();
         PreparedStatement ps =
                 connection.prepareStatement(sql.toString())) {

        int index = 1;
        if (customerId != null) {
            ps.setLong(index++, customerId);
        }
        if (minimumTotal != null) {
            ps.setBigDecimal(index++, minimumTotal);
        }
        if (status != null) {
            ps.setString(index++, status);
        }

        try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                System.out.println(rs.getLong("id"));
            }
        }
    }
}
~~~

Ý nghĩa của `index++`: lấy giá trị chỉ số hiện tại để gán, **sau đó tăng lên 1**. Khi `customerId` không có nhưng `minimumTotal` có, điều kiện `total_amount >= ?` trở thành marker **1**. Nếu `status` cũng có, nó nhận marker **2**:

| Điều kiện được bật | SQL có marker theo thứ tự | Chỉ số phải gán |
| --- | --- | --- |
| Chỉ `customerId` | `customer_id = ?` | `customerId → 1` |
| Chỉ `minimumTotal` và `status` | `total_amount >= ?`, `status = ?` | `minimumTotal → 1`, `status → 2` |
| Cả ba | `customer_id = ?`, `total_amount >= ?`, `status = ?` | `1, 2, 3` tương ứng |
| Không có điều kiện tùy chọn | Không có marker | Không gọi `setXxx` |

Nếu số điều kiện phức tạp, có thể lưu một danh sách các đối tượng *parameter binder* tương ứng với mỗi mệnh đề theo đúng thứ tự được thêm vào câu SQL. Nguyên tắc quan trọng là **xây SQL và bind giá trị theo cùng một thứ tự**.

## 8. Danh sách `IN` không tự mở rộng từ một dấu hỏi

Trong JDBC chuẩn, **một `?` đại diện cho một tham số**, không tự tách một `List<Long>` thành nhiều placeholder:

~~~sql
-- Sai nếu dự định truyền trực tiếp một List<Long> để JDBC tự mở rộng:
SELECT id FROM orders WHERE id IN (?)
~~~

Nếu có ba ID, cách thông dụng là tạo ba marker:

~~~sql
SELECT id FROM orders WHERE id IN (?, ?, ?)
~~~

Ví dụ xây đủ số placeholder theo kích thước danh sách, rồi gán từ trái sang phải:

~~~java
List<Long> ids = java.util.List.of(10L, 20L, 30L);
if (ids.isEmpty()) {
    return; // Với nghiệp vụ "lọc theo ID", không có ID thì không có kết quả.
}

String placeholders = String.join(
        ", ", java.util.Collections.nCopies(ids.size(), "?"));
String sql = "SELECT id FROM orders WHERE id IN (" + placeholders + ")";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (int i = 0; i < ids.size(); i++) {
        ps.setLong(i + 1, ids.get(i));
    }
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong(1));
        }
    }
}
~~~

Đoạn ví dụ giả định các import, biến `connection` và bối cảnh phương thức đã tồn tại. `i` là chỉ số của danh sách Java (bắt đầu từ **0**), còn `i + 1` là chỉ số parameter marker JDBC (bắt đầu từ **1**). Việc ghép dấu `?` ở đây an toàn vì chỉ ghép chuỗi ký hiệu cố định, không ghép trực tiếp giá trị ID do người dùng cung cấp.

Một số DBMS/driver hỗ trợ SQL array hoặc table-valued parameters để truyền tập giá trị, nhưng cú pháp và API khác nhau; **không thể mặc định `IN (?)` tự biến thành `IN (?, ?, ?)`**.

## 9. Tái sử dụng PreparedStatement: gán lại đủ tham số

Một `PreparedStatement` có thể được thực thi nhiều lần với các giá trị khác nhau. Các giá trị tham số **có thể được giữ lại** qua các lượt thực thi, nên cần gán lại tất cả vị trí theo mỗi bộ dữ liệu; tránh vô tình dùng giá trị của lượt trước.

~~~java
String sql = "UPDATE orders SET status = ? WHERE id = ?";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    String[] statuses = {"PAID", "CANCELLED"};
    long[] ids = {10L, 11L};

    for (int i = 0; i < ids.length; i++) {
        ps.setString(1, statuses[i]); // Marker 1.
        ps.setLong(2, ids[i]);        // Marker 2.
        ps.executeUpdate();
    }
}
~~~

Nếu một tham số có thể không có giá trị ở một lượt, vẫn phải chủ động gán `NULL` đúng kiểu hoặc `clearParameters()` rồi gán lại đầy đủ. `clearParameters()` xóa các giá trị đã gán cho statement; **nó không thay thế thao tác gán tham số bắt buộc**:

~~~java
ps.clearParameters();
ps.setString(1, nextStatus);
ps.setLong(2, nextId);
ps.executeUpdate();
~~~

Với batch update, việc gán đủ từng bộ tham số trước `addBatch()` cũng quan trọng:

~~~java
try (PreparedStatement ps = connection.prepareStatement(
        "UPDATE orders SET status = ? WHERE id = ?")) {
    for (long id : new long[]{10L, 11L, 12L}) {
        ps.setString(1, "ARCHIVED");
        ps.setLong(2, id);
        ps.addBatch();
    }
    int[] updateCounts = ps.executeBatch();
}
~~~

Mỗi bộ dữ liệu cần được gán đầy đủ để bản ghi trong batch không lấy nhầm giá trị của lượt trước. Việc batch được commit lúc nào vẫn phụ thuộc chế độ `autoCommit`, giao dịch và DBMS, không phụ thuộc số thứ tự tham số.

## 10. Những giới hạn và lưu ý bảo mật

`PreparedStatement` bảo vệ việc truyền **giá trị** bằng cơ chế bind và tránh lỗi SQL injection do nối trực tiếp dữ liệu đầu vào thành cú pháp SQL:

~~~java
// Không nên: người dùng có thể làm thay đổi cú pháp SQL.
String sqlUnsafe = "SELECT id FROM orders WHERE status = '" + userStatus + "'";

// Nên: dữ liệu được truyền dưới dạng tham số.
String sqlSafe = "SELECT id FROM orders WHERE status = ?";
try (PreparedStatement ps = connection.prepareStatement(sqlSafe)) {
    ps.setString(1, userStatus);
}
~~~

Tuy nhiên, marker `?` **không thay thế được** tên bảng, tên cột, từ khóa SQL hay một đoạn mệnh đề:

~~~sql
-- Không thể bind tên cột để ORDER BY như một identifier:
SELECT id FROM orders ORDER BY ?
~~~

Câu trên (nếu được DBMS chấp nhận) thường hiểu `?` là một **giá trị**, không phải “chọn cột từ tên được truyền vào”. Nếu người dùng được phép chọn trường sắp xếp, hãy ánh xạ lựa chọn đó vào một tập tên cột hằng số được cho phép rồi ghép **chính tên cột đã được kiểm soát** vào SQL. Dùng `setXxx` cho mọi giá trị cần so sánh.

**Dấu `?` trong chuỗi ký tự hoặc cú pháp đặc thù của DBMS** có thể được driver xử lý khác với marker tham số. Không nên đếm tất cả ký tự `?` bằng cách quét chuỗi thô khi SQL có literal, comment hoặc toán tử riêng; hãy xác định marker thực sự theo cú pháp SQL và tài liệu driver.

## 11. Chẩn đoán lỗi vị trí tham số

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Lỗi chỉ số tham số `0` | Mang quy tắc đánh số từ 0 của mảng Java sang JDBC | Marker đầu tiên luôn là 1. |
| Lỗi “parameter index out of range” | Gán chỉ số lớn hơn số marker | Đếm lại marker thực tế trong SQL từ trái sang phải. |
| Lỗi thiếu tham số | Có dấu `?` chưa được bind, hoặc đã `clearParameters()` nhưng chưa gán đủ | Đối chiếu từng marker và setter trước `execute...`. |
| Truy vấn trả sai dòng dù không có lỗi SQL | Đảo giá trị cho hai marker cùng kiểu | Ghi bản đồ `index → biểu thức SQL → biến Java`. |
| Sai số hoặc lỗi chuyển kiểu | Dùng `setString`, `setInt` cho dữ liệu không phù hợp | Dùng setter tương ứng và kiểm tra kiểu cột SQL. |
| So sánh NULL không khớp | Bỏ setter hoặc dùng `= NULL` | Gán `setNull` đúng kiểu và dùng `IS NULL` khi cần. |
| SQL động bị lỗi chỉ số | Bớt một điều kiện nhưng giữ chỉ số hardcode | Xây câu SQL và bind bằng cùng thứ tự có điều kiện; dùng `int index = 1`. |
| Truy vấn `IN (?)` chỉ nhận một giá trị | Nghĩ rằng JDBC tự trải danh sách thành nhiều marker | Tạo số `?` phù hợp hoặc dùng chức năng riêng của DBMS. |
| Lượt thực thi sau có giá trị của lượt trước | Tái sử dụng statement nhưng không bind đủ vị trí | Gán lại tất cả tham số, hoặc `clearParameters()` rồi gán lại. |

JDBC có `PreparedStatement.getParameterMetaData()` và `ParameterMetaData.getParameterCount()` để truy vấn thông tin tham số **khi driver hỗ trợ**. Đây là công cụ hỗ trợ chẩn đoán, không phải bảo đảm mọi driver trả metadata đầy đủ:

~~~java
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    int count = ps.getParameterMetaData().getParameterCount();
    System.out.println("Số tham số: " + count);
}
~~~

Tránh log trực tiếp mọi giá trị bind trong môi trường thật, đặc biệt mật khẩu, token, định danh cá nhân hoặc dữ liệu tài chính. Có thể log tên truy vấn, số tham số, lỗi `SQLState` và vị trí tham số trong môi trường chẩn đoán có kiểm soát.

## 12. Bài tập thực hành

**Bài 1 — Điền chỉ số còn thiếu.** Với SQL:

~~~sql
SELECT id FROM orders
WHERE status = ? AND customer_id = ? AND total_amount BETWEEN ? AND ?
~~~

Hãy gán `"PAID"`, `42L`, `100000.00`, `500000.00`. Đáp án:

~~~java
ps.setString(1, "PAID");
ps.setLong(2, 42L);
ps.setBigDecimal(3, new BigDecimal("100000.00"));
ps.setBigDecimal(4, new BigDecimal("500000.00"));
~~~

**Bài 2 — Tìm lỗi.** Đoạn dưới sai ở đâu?

~~~java
String sql = "DELETE FROM orders WHERE customer_id = ? AND status = ?";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "CANCELLED");
    ps.setLong(2, 42L);
    ps.executeUpdate();
}
~~~

**Đáp án:** marker 1 là `customer_id` nên phải gọi `setLong(1, 42L)`; marker 2 là `status` nên gọi `setString(2, "CANCELLED")`. SQL và Java đều có hai tham số nhưng đang bị đảo vị trí.

**Bài 3 — SQL động.** Khi không có `customerId` nhưng có `status="PAID"`, hãy xác định chỉ số của `status` trong mẫu ở mục 7. Đáp án: **1** nếu không có điều kiện tùy chọn nào khác đứng trước được bật, hoặc **2** khi `minimumTotal` được bật trước nó.

**Bài 4 — Marker lặp.** Viết ba lời gọi setter cho SQL `UPDATE account SET balance = balance - ? WHERE id = ? AND balance >= ?`. Đảm bảo gán số tiền ở cả marker **1** và **3**, ID tài khoản ở marker **2**.

## 13. Checklist khi dùng PreparedStatement

- **Đọc SQL từ trái sang phải** để xác định mỗi marker `?` thực sự biểu diễn giá trị nào.
- **Đánh số bắt đầu từ 1**, độc lập với chỉ số mảng Java, thứ tự cột bảng và cột `ResultSet`.
- **Bind đủ từng marker**, kể cả các marker cần nhận cùng một giá trị hoặc SQL `NULL`.
- **Chọn đúng setter và kiểu SQL**, đặc biệt với tiền tệ, thời gian và kiểu nullable.
- **Khi thay đổi SQL động**, cập nhật thứ tự bind tương ứng; dùng bộ đếm chỉ số nếu phù hợp.
- **Khi tái sử dụng hoặc batch**, luôn gán lại tất cả tham số cho mỗi bộ dữ liệu.
- **Chỉ dùng dấu `?` cho giá trị**; mọi tên bảng, tên cột và cấu trúc SQL động phải đến từ danh sách cho phép.
- **Thực thi và xử lý `SQLException`**, kiểm tra số dòng cập nhật và đóng tài nguyên đúng vòng đời.

**Ghi nhớ:** trong JDBC, **marker thứ nhất `?` ứng với chỉ số 1, marker thứ hai ứng với chỉ số 2...**. Chính thứ tự xuất hiện của marker trong câu SQL quyết định nơi bạn phải gán giá trị bằng `PreparedStatement.setXxx(index, value)`. Viết đúng số lượng, vị trí và kiểu của từng tham số là điều kiện nền tảng để truy vấn có tham số chạy đúng và an toàn.
