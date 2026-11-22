# Xử lý kết quả hỗn hợp gồm ResultSet và số dòng cập nhật

Khi dùng **JDBC (Java Database Connectivity)** để truy cập cơ sở dữ liệu quan hệ, người học thường bắt đầu bằng hai cách thực thi SQL: gọi `executeQuery()` cho câu truy vấn trả về hàng dữ liệu và gọi `executeUpdate()` cho câu lệnh cập nhật trả về số hàng bị ảnh hưởng. Tuy nhiên, một lần thực thi có thể tạo **nhiều kết quả nối tiếp nhau**, trong đó có cả `ResultSet` và **update count** (số hàng được cập nhật hoặc chịu ảnh hưởng bởi một lệnh).

Trường hợp này hay gặp khi gọi stored procedure, khi DBMS hỗ trợ một lần thực thi trả nhiều tập kết quả, hoặc khi một driver/DBMS cho phép chạy các lệnh có nhiều loại kết quả. Để xử lý đúng, JDBC cung cấp bộ phương thức:

- `Statement.execute()`: bắt đầu thực thi và cho biết **loại kết quả đầu tiên**.
- `Statement.getResultSet()`: lấy `ResultSet` hiện tại nếu kết quả đang xét là tập hàng.
- `Statement.getUpdateCount()`: lấy số hàng cập nhật hiện tại nếu kết quả đang xét là update count.
- `Statement.getMoreResults()`: chuyển sang kết quả tiếp theo.

Điểm dễ sai nhất là **`execute()` hoặc `getMoreResults()` trả về `false` không đồng nghĩa với “thất bại” hay “đã hết kết quả”**. Giá trị `false` có thể báo rằng kết quả hiện tại là **số dòng cập nhật**, kể cả khi số đó bằng `0`.

Bài thuộc chương **Thực thi SQL** này giải thích cơ chế từng bước, cách viết vòng lặp không bỏ sót kết quả, quản lý tài nguyên và các giới hạn cần xác minh với DBMS/driver thực tế.

## 1. Kết quả của một lần thực thi SQL có thể gồm những gì?

Hãy hình dung một procedure xử lý đơn hàng làm các việc sau:

1. Trả về danh sách các mặt hàng cần xử lý.
2. Cập nhật trạng thái đơn hàng.
3. Cập nhật tồn kho.
4. Trả về bảng tổng kết trạng thái mới.

Tùy DBMS, cách định nghĩa procedure và driver, ứng dụng có thể nhận một chuỗi kết quả minh họa như sau:

~~~text
Kết quả 1: ResultSet (3 hàng chi tiết đơn hàng)
Kết quả 2: Update count = 1
Kết quả 3: Update count = 0
Kết quả 4: ResultSet (1 hàng tổng kết)
Hết kết quả
~~~

**Lưu ý:** đây là chuỗi giả định để diễn giải API, không phải lời hứa rằng procedure trên mọi DBMS sẽ tự động phát ra update count cho từng `UPDATE`. Một số DBMS/driver ẩn, gom, bỏ qua hoặc không hỗ trợ nhiều kết quả; những hệ quản trị khác có thể trả thêm thông báo/update count. Phải kiểm tra đúng procedure và driver.

Hai loại kết quả cơ bản:

| Loại | Biểu diễn qua JDBC | Cách lấy | Ví dụ |
| --- | --- | --- | --- |
| **Tập hàng** | `ResultSet` | `getResultSet()` | Hai cột `order_id`, `status` với nhiều hàng |
| **Số hàng cập nhật** | `int` (hoặc `long` với API lớn) | `getUpdateCount()` (hoặc `getLargeUpdateCount()`) | `0`, `1`, `25` |

`ResultSet` có thể **rỗng** mà vẫn là một `ResultSet` hợp lệ. Tương tự, **update count bằng `0`** là một kết quả hợp lệ: câu lệnh có thể đã thực thi mà không tác động hàng nào.

Một lần thực thi cũng có thể **không tạo kết quả** nào thuộc hai loại trên. Khi đó cần xác định điểm kết thúc chuỗi bằng đúng hợp đồng JDBC.

## 2. Phân biệt ba phương thức `executeQuery`, `executeUpdate` và `execute`

| Phương thức | Dùng khi nào? | Giá trị trả về | Điều không nên suy diễn |
| --- | --- | --- | --- |
| `executeQuery()` | Câu SQL dự kiến trả về **một `ResultSet`** | `ResultSet` | Không dùng làm vòng lặp duyệt nhiều loại kết quả |
| `executeUpdate()` | `INSERT`/`UPDATE`/`DELETE` hoặc SQL phù hợp với update count | `int` update count hoặc `0` với một số lệnh không ảnh hưởng hàng | Không trả được chuỗi nhiều `ResultSet` |
| `execute()` | SQL hoặc procedure có thể trả kết quả chưa biết trước hoặc nhiều kết quả | `boolean` về loại **kết quả đầu tiên** | `false` không có nghĩa có lỗi |

Đối với `execute()`:

- `true`: kết quả hiện tại là `ResultSet`; gọi `getResultSet()`.
- `false`: kết quả hiện tại **không phải** `ResultSet`. Phải gọi `getUpdateCount()` để biết đó là update count hay không còn kết quả.
- Nếu `getUpdateCount()` trả `-1` khi không có `ResultSet` hiện tại, chuỗi kết quả đã kết thúc.

Khi thực thi thất bại theo nghĩa JDBC, API thường **ném `SQLException`**. Vì vậy, đừng viết điều kiện `if (!statement.execute()) { throw ...; }` chỉ vì nghĩ `false` biểu thị lỗi.

### Ví dụ: `execute()` trả `false` nhưng không lỗi

~~~java
String sql = "UPDATE inventory SET quantity = quantity - 1 WHERE id = ?";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 42L);

    boolean firstIsResultSet = ps.execute();
    // Thông thường: false, vì UPDATE tạo update count.

    if (!firstIsResultSet) {
        int count = ps.getUpdateCount();
        System.out.println("Đã tác động " + count + " hàng");
    }
}
~~~

Với câu lệnh `UPDATE` đơn thông thường, nên dùng `executeUpdate()` vì ý nghĩa trực tiếp hơn. Ví dụ chỉ minh họa vì sao `false` không phải lỗi.

## 3. Cơ chế con trỏ kết quả của `Statement`

Sau khi gọi `execute()`, đối tượng `Statement`/`PreparedStatement`/`CallableStatement` đang trỏ đến **kết quả đầu tiên**, nếu có. Các phương thức lấy kết quả làm việc với **kết quả hiện tại**, không trả về toàn bộ chuỗi ngay lập tức.

~~~mermaid
flowchart TD
    A["boolean hasResultSet = statement.execute()"] --> B{"hasResultSet?"}
    B -->|"true"| C["getResultSet(); xử lý/đóng ResultSet"]
    B -->|"false"| D["int count = getUpdateCount()"]
    D --> E{"count == -1?"}
    E -->|"Có"| F["Kết thúc chuỗi"]
    E -->|"Không"| G["Xử lý update count, kể cả 0"]
    C --> H["hasResultSet = getMoreResults()"]
    G --> H
    H --> B
~~~

Có hai điều kiện dừng cần kết hợp:

1. `getMoreResults()` (hoặc `execute()` ban đầu) trả `false`.
2. `getUpdateCount()` trả `-1`.

**Chỉ khi đồng thời không có `ResultSet` hiện tại và update count là `-1` mới biết đã hết các kết quả cần duyệt.** Nếu gặp update count `0`, vẫn xử lý và tiếp tục gọi `getMoreResults()`.

Vòng lặp có thể mô tả bằng trạng thái:

| `hasResultSet` | `getUpdateCount()` | Diễn giải | Hành động |
| --- | --- | --- | --- |
| `true` | Không cần gọi | Có `ResultSet` hiện tại | Lấy và duyệt `ResultSet` |
| `false` | `0` | Có update count bằng 0 | Ghi nhận kết quả, tiếp tục |
| `false` | Số không âm khác | Có update count | Ghi nhận kết quả, tiếp tục |
| `false` | `-1` | Không còn result/update count hiện tại | Dừng |

Không dùng `getUpdateCount() == 0` để xác định kết thúc. Một câu `UPDATE ... WHERE ...` hợp lệ hoàn toàn có thể ảnh hưởng 0 hàng.

## 4. Vòng lặp chuẩn để xử lý tất cả các kết quả

Ví dụ sau sử dụng **`CallableStatement`** để gọi một procedure giả định `process_order(?)`. Cú pháp escape `{call ...}` là cú pháp JDBC dùng cho stored procedure; việc procedure có trả nhiều kết quả hay không và cách tạo procedure phụ thuộc hệ quản trị.

~~~java
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.SQLException;

public final class MixedResultReader {
    private MixedResultReader() {}

    public static void processOrder(Connection connection, long orderId)
            throws SQLException {

        // Giả định DBMS có procedure phù hợp và driver hỗ trợ kết quả hỗn hợp.
        String sql = "{call process_order(?)}";

        try (CallableStatement cs = connection.prepareCall(sql)) {
            cs.setLong(1, orderId);
            boolean hasResultSet = cs.execute();
            int partNumber = 0;

            while (true) {
                if (hasResultSet) {
                    partNumber++;
                    try (ResultSet rs = cs.getResultSet()) {
                        ResultSetMetaData meta = rs.getMetaData();
                        int columnCount = meta.getColumnCount();
                        System.out.println("Phần " + partNumber + ": ResultSet");

                        while (rs.next()) {
                            for (int column = 1; column <= columnCount; column++) {
                                if (column > 1) {
                                    System.out.print(" | ");
                                }
                                System.out.print(rs.getObject(column));
                            }
                            System.out.println();
                        }
                    }
                } else {
                    int updateCount = cs.getUpdateCount();
                    if (updateCount == -1) {
                        break; // Không còn ResultSet hay update count.
                    }

                    partNumber++;
                    System.out.println(
                            "Phần " + partNumber
                            + ": update count = " + updateCount);
                }

                // Tiến sang kết quả tiếp theo; false vẫn có thể là update count.
                hasResultSet = cs.getMoreResults();
            }
        }
    }
}
~~~

Luồng của ví dụ này:

1. `cs.execute()` thực thi procedure và trả về loại kết quả đầu tiên.
2. Nếu đó là `ResultSet`, `getResultSet()` lấy đối tượng và vòng lặp `rs.next()` đọc hết các hàng; `try-with-resources` đóng nó.
3. Nếu không phải `ResultSet`, `getUpdateCount()` lấy số hàng tác động. `-1` nghĩa là đã hết, còn `0` vẫn là update count hợp lệ.
4. `getMoreResults()` chuyển sang kết quả tiếp theo và vòng lặp tiếp tục.
5. `CallableStatement` được đóng khi rời khối ngoài.

Ví dụ đọc cột bằng `getObject(column)` để không phụ thuộc schema của procedure minh họa; ứng dụng thực tế nên đọc theo kiểu cụ thể như `getLong`, `getString`, `getBigDecimal` và ánh xạ sang DTO. Việc in nguyên dữ liệu ra console chỉ phù hợp để học và có thể làm lộ thông tin nhạy cảm trong sản phẩm.

**Quan trọng:** vòng lặp này là thuật toán JDBC đúng về mặt điều hướng kết quả, nhưng nó không bảo đảm mọi DBMS sẽ tạo chuỗi “ResultSet, update count, ResultSet”. Cần có procedure thực tế và driver hỗ trợ; không thể chạy ví dụ nguyên trạng nếu `process_order` chưa được định nghĩa trên DB.

## 5. Diễn giải một chuỗi kết quả từng bước

Giả sử một stored procedure được DBMS báo về theo trình tự:

~~~text
ResultSet #1   : có 2 hàng
Update count #2: 1
Update count #3: 0
ResultSet #4   : có 1 hàng
End
~~~

Bảng sau mô tả vòng lặp:

| Lần | Giá trị `hasResultSet` | Kết quả từ API | Hành động | Kết thúc? |
| --- | --- | --- | --- | --- |
| Sau `execute` | `true` | `getResultSet()` có 2 hàng | Đọc và đóng tập hàng | Chưa |
| Sau `getMoreResults` lần 1 | `false` | `getUpdateCount() = 1` | Ghi nhận 1 hàng ảnh hưởng | Chưa |
| Sau `getMoreResults` lần 2 | `false` | `getUpdateCount() = 0` | Ghi nhận 0 hàng ảnh hưởng | Chưa |
| Sau `getMoreResults` lần 3 | `true` | `getResultSet()` có 1 hàng | Đọc và đóng tập hàng | Chưa |
| Sau `getMoreResults` lần 4 | `false` | `getUpdateCount() = -1` | Dừng | Có |

Đây là kiểm tra tư duy tốt: **hai lần liên tiếp nhận `false` vẫn có thể là hai update count khác nhau**. Nếu lỡ dừng ở lần `false` đầu tiên, bạn sẽ mất toàn bộ kết quả phía sau.

Một chuỗi khác có thể **bắt đầu bằng update count** hoặc **bắt đầu bằng `ResultSet` rỗng**. Thuật toán chuẩn vẫn xử lý được vì nó dựa trên loại kết quả hiện tại, không dựa trên thứ tự giả định.

## 6. Các lỗi vòng lặp thường gặp

### Lỗi A — Đọc `execute() == false` như thất bại

~~~java
// Sai về ngữ nghĩa: false có thể chỉ là update count.
if (!statement.execute(sql)) {
    throw new IllegalStateException("SQL failed");
}
~~~

JDBC thông báo lỗi thực thi bằng `SQLException`. Giá trị `boolean` của `execute` liên quan đến **loại kết quả đầu tiên**.

### Lỗi B — Dừng ngay khi `getMoreResults()` trả `false`

~~~java
// Sai: bỏ sót update count ở giữa chuỗi.
boolean hasResultSet = statement.execute(sql);
while (hasResultSet) {
    try (ResultSet rs = statement.getResultSet()) {
        // ...
    }
    hasResultSet = statement.getMoreResults();
}
~~~

Đoạn này chỉ đọc được những `ResultSet` liên tiếp. Nếu chuỗi bắt đầu bằng update count, nó không chạy lần nào; nếu update count xuất hiện giữa chuỗi, nó dừng quá sớm.

### Lỗi C — Coi update count `0` là đã hết

~~~java
// Sai: 0 là một số hàng cập nhật hợp lệ.
int count = statement.getUpdateCount();
if (count <= 0) {
    return;
}
~~~

Điều kiện dừng đúng theo cơ chế duyệt kết quả là `count == -1` **trong nhánh không có `ResultSet`**.

### Lỗi D — Quên chuyển sang kết quả tiếp theo

~~~java
// Sai: có thể lặp vô hạn trên cùng một result/update count.
while (true) {
    int count = statement.getUpdateCount();
    if (count == -1) {
        break;
    }
    System.out.println(count);
    // Thiếu statement.getMoreResults().
}
~~~

`getUpdateCount()` là phương thức **đọc** kết quả hiện tại. Nó không tự chuyển sang kết quả tiếp theo. `getMoreResults()` mới thực hiện bước chuyển.

### Lỗi E — Gọi `getResultSet()` sau mọi lần `getMoreResults()`

Nếu `getMoreResults()` trả `false`, kết quả có thể là update count. `getResultSet()` lúc đó thường trả `null`; không được gọi `rs.next()` khi chưa xác định có tập hàng.

## 7. Vòng đời `ResultSet` khi có nhiều kết quả

`ResultSet` có thể gắn với cursor và tài nguyên trên máy chủ. Khi chuyển tới kết quả tiếp theo, cần xác định phải làm gì với tập hàng hiện tại.

Theo hợp đồng JDBC, phương thức **`getMoreResults()` không tham số** mặc định đóng `ResultSet` hiện tại khi chuyển sang kết quả tiếp theo. Tuy nhiên, nên **đóng tường minh** bằng `try-with-resources` ngay sau khi đọc hết để mã có ranh giới tài nguyên rõ ràng.

JDBC còn có overload:

~~~java
boolean nextIsResultSet =
        statement.getMoreResults(Statement.CLOSE_CURRENT_RESULT);
~~~

Các lựa chọn chuẩn:

| Hằng | Ý nghĩa |
| --- | --- |
| `Statement.CLOSE_CURRENT_RESULT` | Đóng `ResultSet` hiện tại khi chuyển tiếp |
| `Statement.KEEP_CURRENT_RESULT` | Giữ `ResultSet` hiện tại mở nếu driver hỗ trợ |
| `Statement.CLOSE_ALL_RESULTS` | Đóng tất cả `ResultSet` đã mở từ statement trước khi chuyển tiếp |

Nếu cần giữ nhiều `ResultSet` mở đồng thời, kiểm tra:

~~~java
boolean supportsMultipleOpenResults =
        connection.getMetaData().supportsMultipleOpenResults();
~~~

Không nên giữ nhiều tập hàng mở chỉ để thuận tiện khi phần lớn ứng dụng có thể đọc, ánh xạ rồi đóng từng kết quả. **`KEEP_CURRENT_RESULT` không được bảo đảm khả dụng với mọi driver**, và các con trỏ mở lâu có thể giữ tài nguyên DBMS hoặc chặn việc tái sử dụng statement/connection.

### Tại sao phải đọc xong hoặc đóng `ResultSet` trước khi chuyển?

Một số driver **stream dữ liệu từ mạng** thay vì tải toàn bộ hàng vào bộ nhớ. Nếu ứng dụng đang đọc dở tập kết quả đầu rồi gọi `getMoreResults()`, driver có thể cần bỏ qua/phóng thích các hàng còn lại hoặc phát sinh hành vi riêng. Với truy vấn lớn, thao tác đó có thể tốn thời gian, mạng và tài nguyên.

Thiết kế an toàn là: xác định liệu nghiệp vụ cần mọi hàng hay không; đọc/đóng tập hiện tại một cách có chủ đích; sau đó mới chuyển sang kết quả tiếp theo. Không giữ cursor sau khi đã đóng statement hoặc connection.

## 8. Có thể dùng `PreparedStatement` thay `CallableStatement` không?

Có. Các phương thức quản lý nhiều kết quả được định nghĩa trên `Statement` và cũng áp dụng cho `PreparedStatement`/`CallableStatement` khi driver hỗ trợ:

~~~java
String sql = "/* câu SQL cụ thể mà DBMS hỗ trợ nhiều kết quả */";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    boolean hasResultSet = ps.execute();
    while (true) {
        if (hasResultSet) {
            try (ResultSet rs = ps.getResultSet()) {
                while (rs.next()) {
                    // Đọc kết quả hiện tại.
                }
            }
        } else {
            int count = ps.getUpdateCount();
            if (count == -1) {
                break;
            }
            // Xử lý update count, kể cả 0.
        }
        hasResultSet = ps.getMoreResults();
    }
}
~~~

Ví dụ khung này chưa có SQL cụ thể vì **khả năng trả nhiều loại kết quả không giống nhau giữa các DBMS**. Với `PreparedStatement`, hãy gắn toàn bộ tham số bằng `setXxx` trước `execute()` như bình thường.

Không nên suy ra rằng chỉ cần nối:

~~~sql
SELECT ...;
UPDATE ...;
SELECT ...;
~~~

thì mọi driver sẽ cho thực thi và trả ba kết quả trong một lần gọi. Một số driver **không cho phép nhiều statement trong một lệnh**, một số cần cấu hình riêng, và việc bật chế độ chạy nhiều câu lệnh có thể ảnh hưởng bảo mật. Ưu tiên API phù hợp với DBMS, stored procedure có hợp đồng rõ ràng hoặc tách các câu lệnh thành các lần gọi có quản lý transaction.

## 9. `CallableStatement`: kết quả hỗn hợp và OUT parameter

Stored procedure còn có thể trả **OUT parameter** bên cạnh `ResultSet` và update count. Đây là ba kênh thông tin khác nhau:

- **`ResultSet`:** bảng dữ liệu có nhiều hàng/cột.
- **Update count:** số hàng ảnh hưởng của một kết quả thuộc loại cập nhật.
- **OUT parameter:** giá trị được procedure gán vào tham số đầu ra.

Ví dụ minh họa procedure có tham số đầu vào và đầu ra kiểu số nguyên:

~~~java
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;

public static int executeProcedure(Connection connection, long orderId)
        throws SQLException {
    // Chỉ chạy nếu DBMS có procedure với hợp đồng đầu vào/đầu ra tương ứng.
    String call = "{call process_order_with_status(?, ?)}";
    try (CallableStatement cs = connection.prepareCall(call)) {
        cs.setLong(1, orderId);
        cs.registerOutParameter(2, Types.INTEGER);

        boolean hasResultSet = cs.execute();
        while (true) {
            if (hasResultSet) {
                try (ResultSet rs = cs.getResultSet()) {
                    while (rs.next()) {
                        // Xử lý từng hàng.
                    }
                }
            } else {
                int updateCount = cs.getUpdateCount();
                if (updateCount == -1) {
                    break;
                }
                // Xử lý update count.
            }
            hasResultSet = cs.getMoreResults();
        }

        return cs.getInt(2); // OUT parameter, sau khi xử lý các result.
    }
}
~~~

Ví dụ dùng thứ tự đọc **các result/update count trước, OUT parameter sau**, phù hợp với nhiều driver/procedure. Tuy nhiên một số hệ quản trị có quy định khác, hoặc procedure không thể trả đồng thời những loại kết quả này theo cách trên. Hãy xem tài liệu driver về `CallableStatement`, OUT parameter và nhiều result set.

Không xem OUT parameter như một update count. Giá trị trả bởi `cs.getInt(2)` được lấy từ tham số đã đăng ký bằng `registerOutParameter`, không phải từ `getUpdateCount()`.

## 10. Số dòng cập nhật có những giới hạn nào?

`getUpdateCount()` trả về `int` cho **kết quả cập nhật hiện tại**. Trong hợp đồng JDBC, giá trị `-1` được dùng khi không có update count hiện tại (ví dụ đang ở `ResultSet` hoặc hết kết quả). Vì vậy:

- `0` có thể biểu thị câu lệnh hợp lệ không ảnh hưởng hàng nào.
- `1` có thể biểu thị một hàng bị ảnh hưởng.
- Một số DBMS phân biệt “hàng khớp điều kiện” và “hàng thực sự đổi giá trị”; cách báo count có thể phụ thuộc driver/cấu hình.
- Một số lệnh không phải DML có thể tạo update count `0` hoặc không trả count theo quy tắc DBMS.
- Update count **không phải** mã trạng thái thành công/thất bại chung cho mọi nghiệp vụ.

Nếu hệ thống có khả năng cập nhật số hàng vượt giới hạn `int`, JDBC mới có `getLargeUpdateCount()` trả `long` và những phương thức tương ứng như `executeLargeUpdate()`. Cần kiểm tra mức hỗ trợ của driver; không thay `getUpdateCount()` bằng ép kiểu `long` rồi cho rằng đã loại bỏ giới hạn.

### Không nhầm với batch update count

`executeBatch()` trả một **mảng số lượng kết quả** tương ứng các lệnh trong batch:

~~~java
int[] counts = statement.executeBatch();
~~~

Trong batch, JDBC có thể dùng các giá trị đặc biệt như `Statement.SUCCESS_NO_INFO` (thực thi thành công nhưng không biết số hàng) và `Statement.EXECUTE_FAILED` (lệnh thất bại trong cách báo cáo batch phù hợp). Các giá trị này **không phải** quy tắc dừng `-1` của vòng lặp `getUpdateCount()`, và khi batch lỗi có thể gặp `BatchUpdateException`.

Đừng dùng vòng lặp `getMoreResults()` để thay thế việc xử lý mảng kết quả batch. Hai API có mô hình kết quả khác nhau.

### Không nhầm với khóa được sinh tự động

Khi thực thi `INSERT` và cần đọc khóa mới, JDBC có `getGeneratedKeys()`, thường dùng cùng `Statement.RETURN_GENERATED_KEYS` theo khả năng driver:

~~~java
String sql = "INSERT INTO customer (name) VALUES (?)";
try (PreparedStatement ps = connection.prepareStatement(
        sql, Statement.RETURN_GENERATED_KEYS)) {
    ps.setString(1, "Lan");
    ps.executeUpdate();
    try (ResultSet keys = ps.getGeneratedKeys()) {
        if (keys.next()) {
            long newId = keys.getLong(1);
            System.out.println(newId);
        }
    }
}
~~~

`getGeneratedKeys()` là một cơ chế **riêng** để lấy các giá trị khóa được sinh; không được mặc định rằng tập kết quả này sẽ xuất hiện như một phần tử trong chuỗi `getMoreResults()`. Khả năng hỗ trợ, kiểu và số cột khóa phụ thuộc DBMS/driver.

## 11. Giao dịch và lỗi khi xử lý nhiều kết quả

Một lần `execute()` có thể kích hoạt những thay đổi dữ liệu. Việc nhận được một `ResultSet` hoặc update count **không có nghĩa mọi thay đổi đã được commit theo yêu cầu nghiệp vụ**. Transaction cần được quản lý theo ranh giới phù hợp.

Với `autoCommit=false`, nếu procedure thực hiện nhiều thay đổi, ứng dụng phải quyết định `commit()` khi toàn bộ kết quả đã được xử lý và các điều kiện nghiệp vụ đều đạt. Nếu đọc result set, update count hoặc OUT parameter bị lỗi giữa chừng, thông thường cần `rollback()` để hủy transaction trong giới hạn DBMS cho phép.

~~~java
boolean originalAutoCommit = connection.getAutoCommit();
connection.setAutoCommit(false);
try {
    // Gọi procedure và duyệt hết chuỗi kết quả.
    // Kiểm tra các điều kiện nghiệp vụ trước khi chấp nhận.
    connection.commit();
} catch (SQLException | RuntimeException failure) {
    try {
        connection.rollback();
    } catch (SQLException rollbackFailure) {
        failure.addSuppressed(rollbackFailure);
    }
    throw failure;
} finally {
    // Chỉ khôi phục sau khi transaction đã được xử lý rõ ràng.
    connection.setAutoCommit(originalAutoCommit);
}
~~~

Đây là mẫu minh họa ranh giới giao dịch, chưa phải đoạn chương trình tự chạy vì `connection` đã được khai báo ở ngoài. Nếu dùng transaction manager của framework, để framework sở hữu commit/rollback. Việc khôi phục trạng thái khi rollback/commit bị lỗi cần tuân theo cơ chế connection pool; không mặc định kết nối còn an toàn để tái sử dụng.

**Lưu ý DBMS:** stored procedure có thể có quy tắc transaction riêng, một số loại lệnh có implicit commit hoặc không được chạy trong transaction theo cách bạn dự kiến. Hãy xác minh ngữ nghĩa đó trước khi cho rằng `rollback()` luôn hủy được mọi tác động.

### Lỗi xuất hiện sau một vài kết quả

Một procedure có thể trả tập hàng đầu tiên rồi phát sinh lỗi khi thực hiện phần tiếp theo. Vì thế:

- Nhận thành công `ResultSet` đầu tiên **không chứng minh** các kết quả sau đều thành công.
- `SQLException` có thể phát sinh ở `execute()`, `ResultSet.next()`, `getMoreResults()`, `getUpdateCount()` hoặc thao tác khác, tùy driver.
- Không kết luận nghiệp vụ thành công chỉ vì đã nhận update count dương của một bước.
- Nên duyệt/kiểm tra đầy đủ các kết quả mà hợp đồng nghiệp vụ yêu cầu, sau đó mới hoàn tất transaction.

## 12. Kiểm tra khả năng hỗ trợ của DBMS và JDBC driver

JDBC định nghĩa API chung nhưng không bảo đảm mọi driver tạo và công bố mọi kiểu chuỗi kết quả.

`DatabaseMetaData` cung cấp các phương thức:

~~~java
import java.sql.DatabaseMetaData;

DatabaseMetaData meta = connection.getMetaData();

System.out.println("supportsMultipleResultSets="
        + meta.supportsMultipleResultSets());
System.out.println("supportsMultipleOpenResults="
        + meta.supportsMultipleOpenResults());
~~~

Hai khả năng này khác nhau:

- `supportsMultipleResultSets()` cho biết driver có hỗ trợ trả nhiều `ResultSet` từ một lần thực thi hay không.
- `supportsMultipleOpenResults()` cho biết có thể giữ đồng thời nhiều `ResultSet` mở từ một statement hay không.

Kể cả khi driver trả `true`, chưa chắc một procedure cụ thể tự phát ra update count theo thứ tự bạn mong muốn. Ngược lại, metadata đơn thuần không thể mô tả hết các giới hạn của stored procedure, cấu hình driver, chế độ streaming hoặc phiên bản DBMS.

Khi cần chức năng này trong sản phẩm, nên có một bài thử tích hợp **trên chính phiên bản driver và DBMS triển khai**, chạy một procedure xác định rõ:

1. Trả một `ResultSet` có dữ liệu.
2. Có một bước tạo update count (nếu DBMS/driver hỗ trợ công bố).
3. Có một bước tác động 0 hàng.
4. Trả `ResultSet` khác.
5. Kết thúc chuỗi kết quả.

Ghi lại chuỗi mà driver thực tế phát ra, kể cả trường hợp nó gộp/ẩn count. Nếu DBMS không có cách cung cấp chuỗi như vậy, hãy thiết kế hợp đồng khác (ví dụ một result set tổng hợp hoặc OUT parameters) thay vì phụ thuộc vào hành vi không được hỗ trợ.

## 13. Kiểm thử vòng lặp và kết quả mong đợi

Với một nguồn kết quả hỗn hợp có thể kiểm soát trong môi trường thử nghiệm, hãy kiểm tra ít nhất các trường hợp:

| Trường hợp | Chuỗi kết quả cần mô phỏng/kiểm tra | Kỳ vọng |
| --- | --- | --- |
| Chỉ một result set | `ResultSet → end` | Đọc đủ hàng, không gọi nhầm update count |
| Chỉ một update count | `3 → end` | Ghi nhận 3 hàng ảnh hưởng |
| Update count bằng 0 | `0 → end` | Ghi nhận 0, vẫn chuyển tới end |
| Tập hàng rỗng | `ResultSet (0 hàng) → end` | Nhận đúng loại ResultSet, không coi là hết ngay |
| Trộn và xen kẽ | `ResultSet → 2 → 0 → ResultSet → end` | Ghi đúng thứ tự cả bốn phần |
| Mở đầu bằng update count | `1 → ResultSet → end` | Không bỏ qua ResultSet phía sau |
| Procedure ném lỗi giữa chừng | `ResultSet → SQLException` | Ghi nhận lỗi, quản lý rollback/cleanup |
| Driver không hỗ trợ nhiều result | Một kết quả hoặc lỗi tính năng | Xử lý theo hợp đồng driver, không dự đoán kết quả không có |

Với vòng lặp Java, có thể ghi nhận `partNumber` và loại kết quả theo thứ tự để so sánh với hợp đồng procedure; không ghi nội dung nhạy cảm vào log. Kiểm tra chắc chắn `ResultSet`, `Statement` và `Connection` được đóng ở mọi nhánh.

### Câu hỏi tự đánh giá

1. Vì sao `execute()` trả `false` không phải lỗi?
2. Khi `getMoreResults()` trả `false`, vì sao vẫn phải gọi `getUpdateCount()`?
3. Update count `0` khác `-1` ở điểm nào?
4. Vì sao nên đọc hoặc đóng `ResultSet` hiện tại trước khi chuyển sang kết quả kế tiếp?
5. `getGeneratedKeys()` và `executeBatch()` khác cơ chế `getMoreResults()` ra sao?
6. Điều gì cần xác minh trước khi giả định stored procedure trên một DBMS sẽ trả các update count xen kẽ result set?

## 14. Checklist áp dụng vào mã JDBC

1. Chọn `executeQuery()` hoặc `executeUpdate()` nếu chỉ cần loại kết quả đã biết; dùng `execute()` khi cần xử lý chuỗi hỗn hợp.
2. Đọc `boolean` của `execute()`/`getMoreResults()` như **cờ cho biết kết quả hiện tại là `ResultSet` hay không**.
3. Nếu là `ResultSet`, gọi `getResultSet()`, đọc và đóng tập hàng.
4. Nếu không phải `ResultSet`, gọi `getUpdateCount()`; **chỉ `-1` mới đánh dấu kết thúc**.
5. Với update count `0` hoặc dương, xử lý kết quả và gọi `getMoreResults()` để đi tiếp.
6. Đảm bảo mỗi kết quả hiện tại chỉ được xử lý một lần; không lặp vô hạn vì quên `getMoreResults()`.
7. Đóng `ResultSet`/`Statement` đúng vòng đời; kiểm tra streaming và khả năng giữ nhiều result mở.
8. Phân biệt update count, batch count, generated keys và OUT parameters.
9. Quản lý commit/rollback theo toàn bộ nghiệp vụ; xử lý lỗi có thể xuất hiện sau một vài kết quả.
10. Kiểm thử chính xác chuỗi kết quả trên DBMS/driver dự định triển khai.

**Ghi nhớ quy tắc hai bước:** sau mỗi lần `execute()` hoặc `getMoreResults()`, nếu kết quả là `true` thì đọc `ResultSet`; nếu là `false` thì đọc `getUpdateCount()`. **Chỉ dừng khi không có `ResultSet` và update count bằng `-1`.** Đây là chìa khóa để xử lý chính xác kết quả hỗn hợp trong JDBC mà không bỏ sót các cập nhật hoặc tập dữ liệu xuất hiện sau đó.
