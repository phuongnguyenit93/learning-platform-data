# Ngăn SQL injection bằng tham số hóa giá trị

Trong **JDBC (Java Database Connectivity)**, ứng dụng gửi câu lệnh SQL đến cơ sở dữ liệu quan hệ để đọc và sửa dữ liệu. Nếu đưa dữ liệu từ người dùng vào chuỗi SQL bằng phép nối chuỗi, ứng dụng có thể vô tình biến **dữ liệu** thành **một phần cú pháp SQL**. Lỗ hổng này được gọi là **SQL injection**.

Biện pháp cốt lõi là **tham số hóa giá trị** bằng `PreparedStatement`: viết cấu trúc SQL cố định với dấu `?` tại vị trí của giá trị, rồi truyền từng giá trị qua phương thức `setXxx`. Cần hiểu rõ giới hạn của phương pháp này, đặc biệt khi ứng dụng tạo tên bảng, tên cột, danh sách `IN` hoặc `ORDER BY` động.

## 1. SQL injection xảy ra như thế nào?

Giả sử một ứng dụng tra cứu người dùng theo email. Đoạn mã sau **không an toàn**:

~~~java
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.Statement;

String email = inputFromRequest; // Dữ liệu từ HTTP/API/form

String sql = "SELECT id, email FROM app_user WHERE email = '"
        + email + "'";

try (Statement statement = connection.createStatement();
     ResultSet rs = statement.executeQuery(sql)) {
    while (rs.next()) {
        System.out.println(rs.getLong("id") + ": " + rs.getString("email"));
    }
}
~~~

Nếu người dùng nhập địa chỉ bình thường như `alice@example.com`, SQL được tạo ra sẽ gần như:

~~~sql
SELECT id, email
FROM app_user
WHERE email = 'alice@example.com'
~~~

Nhưng nếu đầu vào là:

~~~text
' OR '1'='1
~~~

câu lệnh có thể trở thành:

~~~sql
SELECT id, email
FROM app_user
WHERE email = '' OR '1'='1'
~~~

Điều kiện `'1'='1'` luôn đúng, nên truy vấn có thể trả về nhiều bản ghi hơn dự định. Trong ứng dụng khác, việc ghép đầu vào với câu lệnh `UPDATE`/`DELETE` hoặc kiểm tra quyền còn có thể gây hậu quả nghiêm trọng hơn. Cú pháp khai thác cụ thể và khả năng thực thi phụ thuộc hệ quản trị, driver, quyền tài khoản DB và cấu trúc SQL.

**Nguyên nhân:** dữ liệu đầu vào trở thành một phần văn bản SQL *trước khi* SQL được DB phân tích cú pháp. Vì dấu nháy đơn là ký tự cú pháp chuỗi trong SQL, người dùng có thể thay đổi ý nghĩa câu lệnh nếu ứng dụng ghép trực tiếp.

## 2. `PreparedStatement` tách cấu trúc SQL và giá trị

Cách viết đúng với JDBC:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public static Long findUserIdByEmail(
        Connection connection,
        String email
) throws SQLException {
    String sql = "SELECT id FROM app_user WHERE email = ?";

    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        ps.setString(1, email);

        try (ResultSet rs = ps.executeQuery()) {
            return rs.next() ? rs.getLong("id") : null;
        }
    }
}
~~~

Ở đây:

1. `SELECT id FROM app_user WHERE email = ?` định nghĩa cấu trúc truy vấn.
2. `?` là **parameter marker** đại diện cho một **giá trị** cần bind.
3. `ps.setString(1, email)` gắn giá trị đầu tiên, với chỉ số bắt đầu từ **1**, không phải 0.
4. `executeQuery()` thực thi câu lệnh với các giá trị đã gắn.
5. `try-with-resources` đóng `ResultSet` và `PreparedStatement` kể cả khi phát sinh lỗi.

Ngay cả khi `email` chứa dấu nháy, khoảng trắng hoặc văn bản giống SQL, giá trị đó vẫn được xử lý như **một chuỗi dữ liệu** của điều kiện `email = ?`. Ví dụ đầu vào `' OR '1'='1` được so sánh như một địa chỉ email nguyên văn; nó không thêm điều kiện `OR` vào câu lệnh.

Tùy driver và cấu hình, cơ chế bên dưới có thể sử dụng prepared statement phía máy chủ hoặc binding/escaping phía client. **Cam kết quan trọng ở mức API** là một driver JDBC đúng chuẩn phải xử lý giá trị được bind như dữ liệu, không xem nó như cú pháp truy vấn.

### Sơ đồ luồng an toàn

~~~mermaid
flowchart TD
    A["Ứng dụng tạo SQL có ?"] --> B["connection.prepareStatement(sql)"]
    C["Dữ liệu người dùng"] --> D["ps.setString / setInt / setObject"]
    B --> E["Driver JDBC"]
    D --> E
    E --> F["DB xử lý cấu trúc SQL và giá trị tham số"]
    F --> G["Kết quả đúng điều kiện"]
~~~

Điều then chốt là **SQL đã có sẵn các vị trí tham số trước khi giá trị không tin cậy được gắn vào**.

## 3. Gắn tham số đúng kiểu dữ liệu

JDBC cung cấp nhiều phương thức `setXxx` để gắn giá trị. Chọn phương thức dựa trên kiểu cột và ý nghĩa dữ liệu:

| Giá trị Java | Cách gắn thường dùng | Ví dụ vị trí SQL |
| --- | --- | --- |
| `String` | `setString(index, value)` | `WHERE username = ?` |
| `int` / `long` | `setInt` / `setLong` | `WHERE id = ?` |
| `boolean` | `setBoolean` | `WHERE enabled = ?` (nếu DB/driver hỗ trợ boolean) |
| `BigDecimal` | `setBigDecimal` | `SET balance = ?` |
| `LocalDate` | `setObject` với driver JDBC 4.2 | Cột `DATE` |
| `LocalDateTime` | `setObject` với driver JDBC 4.2 | Cột `TIMESTAMP` không có múi giờ |
| `null` | `setNull(index, Types.<kiểu>)` | `INSERT`/`UPDATE` cột cho phép NULL |

Ví dụ cập nhật giá trị từ nhiều kiểu:

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public static int updatePrice(
        Connection connection,
        long productId,
        BigDecimal price,
        boolean enabled
) throws SQLException {
    String sql = """
        UPDATE product
        SET price = ?, enabled = ?
        WHERE id = ?
        """;

    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        ps.setBigDecimal(1, price);
        ps.setBoolean(2, enabled);
        ps.setLong(3, productId);
        return ps.executeUpdate();
    }
}
~~~

Ví dụ trên dùng Java text block (Java 15+). Với Java cũ hơn, dùng chuỗi SQL bình thường. `executeUpdate()` trả về số hàng chịu ảnh hưởng; ứng dụng cần kiểm tra giá trị này nếu nghiệp vụ yêu cầu cập nhật đúng một hàng.

**Không tự thêm nháy đơn quanh `?`**:

~~~java
// Sai: dấu ? nằm trong chuỗi literal của SQL, không phải marker.
String wrongSql = "SELECT id FROM app_user WHERE email = '?'";

// Đúng: driver xử lý việc bind/escaping cho giá trị.
String correctSql = "SELECT id FROM app_user WHERE email = ?";
~~~

## 4. Tham số hóa các lệnh `SELECT`, `INSERT`, `UPDATE`, `DELETE`

Không chỉ truy vấn đọc; bất kỳ giá trị đầu vào nào tham gia câu lệnh SQL đều cần bind nếu cú pháp cho phép.

~~~java
// INSERT: bind tên và email, không ghép chuỗi từ request.
String insert = "INSERT INTO app_user (name, email) VALUES (?, ?)";
try (PreparedStatement ps = connection.prepareStatement(insert)) {
    ps.setString(1, requestedName);
    ps.setString(2, requestedEmail);
    int inserted = ps.executeUpdate();
}

// DELETE: bind mã bản ghi; cần kiểm tra quyền xóa ở tầng nghiệp vụ.
String delete = "DELETE FROM app_user WHERE id = ?";
try (PreparedStatement ps = connection.prepareStatement(delete)) {
    ps.setLong(1, requestedId);
    int deleted = ps.executeUpdate();
}
~~~

Các phương thức `setXxx` phải được gọi **trước** `executeQuery` hoặc `executeUpdate` và đúng chỉ số, đủ số tham số. Nếu tái sử dụng `PreparedStatement` nhiều lần, cần đảm bảo mọi vị trí có giá trị phù hợp mỗi lần thực thi; không nên dựa vào tham số còn sót từ lần trước.

### Giá trị `NULL`

Khi ghi `NULL`, dùng `setNull` với kiểu SQL tương ứng:

~~~java
import java.sql.Types;

String sql = "UPDATE app_user SET nickname = ? WHERE id = ?";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setNull(1, Types.VARCHAR);
    ps.setLong(2, userId);
    ps.executeUpdate();
}
~~~

Lưu ý `WHERE nickname = ?` với tham số `NULL` sẽ không khớp các hàng có nickname null theo ngữ nghĩa SQL ba trị. Để tìm giá trị `NULL`, viết `WHERE nickname IS NULL`. Đây là vấn đề **ngữ nghĩa NULL**, không phải lỗi injection.

## 5. `PreparedStatement` vẫn có thể không an toàn nếu ghép chuỗi

Tên lớp `PreparedStatement` không tự sửa một truy vấn đã bị xây dựng bằng dữ liệu không tin cậy. Ví dụ sau **vẫn có nguy cơ SQL injection**:

~~~java
// Không an toàn: chuỗi email được ghép thành cú pháp SQL trước prepare.
String sql = "SELECT id FROM app_user WHERE email = '"
        + requestedEmail + "'";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    try (ResultSet rs = ps.executeQuery()) {
        // ...
    }
}
~~~

Đúng là:

~~~java
String sql = "SELECT id FROM app_user WHERE email = ?";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, requestedEmail);
    try (ResultSet rs = ps.executeQuery()) {
        // ...
    }
}
~~~

Tương tự, những đoạn ghép chuỗi dạng `"... WHERE id = " + requestedId` hoặc `"... LIKE '%" + searchText + "%'"` cũng cần loại bỏ, ngay cả khi ứng dụng đã validate đầu vào ở một bước khác.

**Validation là lớp kiểm soát dữ liệu hợp lệ, không phải cơ chế thay thế parameter binding.** Escape HTML, URL encoding hoặc xóa dấu nháy theo cách thủ công cũng không thay thế được tham số hóa SQL.

## 6. Không thể bind tên bảng, tên cột hay cú pháp SQL

`?` đại diện cho một **giá trị**, không đại diện cho một phần ngữ pháp SQL. Những thành phần sau không nên hoặc không thể truyền qua `setString` để mong thay thế cú pháp:

- Tên bảng, tên schema, tên cột.
- Từ khóa `ASC`/`DESC`, tên hàm SQL, toán tử.
- Một toàn bộ biểu thức `WHERE` hoặc mệnh đề `ORDER BY`.
- Danh sách nhiều phần tử viết thành một chuỗi `"1,2,3"` cho `IN (?)`.

Ví dụ `ORDER BY ?` không có nghĩa “sắp xếp theo tên cột do người dùng chọn”; marker được hiểu là giá trị/biểu thức tham số, và cách DB xử lý còn phụ thuộc cú pháp SQL. Giải pháp là **ánh xạ lựa chọn bên ngoài sang danh sách cấu trúc SQL cho phép**.

### Sắp xếp động bằng danh sách cho phép

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public static void listProducts(
        Connection connection,
        String sortKey,
        boolean descending,
        String category
) throws SQLException {
    String sortColumn;
    switch (sortKey) {
        case "name":
            sortColumn = "product_name";
            break;
        case "created":
            sortColumn = "created_at";
            break;
        case "price":
            sortColumn = "price";
            break;
        default:
            throw new IllegalArgumentException("Sort key không hợp lệ");
    }

    String direction = descending ? "DESC" : "ASC";
    String sql = "SELECT id, product_name, price FROM product "
            + "WHERE category = ? "
            + "ORDER BY " + sortColumn + " " + direction;

    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        ps.setString(1, category);
        try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                // Xử lý kết quả.
            }
        }
    }
}
~~~

Ở đây phần ghép chuỗi chỉ lấy từ **ba tên cột đã định nghĩa sẵn trong chương trình** và từ hai hằng `ASC`, `DESC`. Giá trị `category` từ người dùng vẫn được bind. Cách này áp dụng tương tự cho lựa chọn tên bảng, cột lọc hoặc toán tử: dùng tập phương án được phê duyệt; không đưa nguyên văn input vào vị trí cú pháp.

Nếu cần chọn giữa nhiều bảng, các bảng đó cũng phải là những tên cố định trong code hoặc metadata đã được kiểm soát. Không lấy tên bảng tùy ý từ HTTP request rồi nối vào SQL.

## 7. Danh sách `IN` với số phần tử thay đổi

Một marker `?` chỉ đại diện cho **một giá trị**. Vì vậy:

~~~sql
-- Đây chỉ có một vị trí tham số, không phải ba ID.
SELECT id FROM app_user WHERE id IN (?)
~~~

Không thể gắn `"10,20,30"` vào `?` rồi mong driver tự tách thành ba giá trị. Với các hệ quản trị SQL phổ biến, cách đơn giản và dễ kiểm soát là tạo **đúng số marker**, sau đó bind riêng từng ID:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Collections;
import java.util.List;

public static void findUsersByIds(
        Connection connection,
        List<Long> ids
) throws SQLException {
    if (ids.isEmpty()) {
        return; // Không tạo cú pháp IN () có thể không hợp lệ.
    }
    if (ids.size() > 100) {
        throw new IllegalArgumentException("Danh sách ID quá dài");
    }

    String markers = String.join(", ",
            Collections.nCopies(ids.size(), "?"));
    String sql = "SELECT id, email FROM app_user WHERE id IN ("
            + markers + ")";

    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        for (int i = 0; i < ids.size(); i++) {
            ps.setLong(i + 1, ids.get(i));
        }

        try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                // Xử lý kết quả.
            }
        }
    }
}
~~~

Số lượng marker được tính từ độ dài danh sách, còn **nội dung từng ID không bao giờ được chèn vào SQL**. Giới hạn kích thước danh sách giúp tránh câu lệnh quá lớn hoặc vượt giới hạn tham số của DB/driver. Một số DB còn hỗ trợ mảng, bảng tạm hoặc tham số dạng bảng; đó là lựa chọn khác cần dùng đúng API riêng của DB.

## 8. `LIKE`: ngăn injection và kiểm soát ký tự đại diện

Truy vấn tìm kiếm thường cần chứa chuỗi con. Cách **an toàn về mặt SQL injection** là bind cả pattern:

~~~java
String sql = "SELECT id FROM product WHERE product_name LIKE ?";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "%" + searchText + "%");
    try (ResultSet rs = ps.executeQuery()) {
        // ...
    }
}
~~~

Phần trăm ở ví dụ trên là ký tự đại diện `LIKE`. Dữ liệu vẫn được truyền như giá trị, vì vậy dấu nháy hoặc chuỗi SQL trong `searchText` không biến thành cú pháp.

Tuy nhiên, nếu người dùng nhập `%` hoặc `_`, kết quả tìm kiếm có thể rộng hơn dự kiến: `%` đại diện chuỗi ký tự bất kỳ và `_` đại diện một ký tự. Đây là vấn đề **kiểm soát ngữ nghĩa tìm kiếm**, khác với SQL injection.

Nếu yêu cầu là *tìm đúng văn bản người dùng gõ*, có thể escape các ký tự đặc biệt của `LIKE`. Ví dụ dùng ký tự escape `!` theo cú pháp SQL `ESCAPE`:

~~~java
public static String escapeLikeTerm(String term) {
    return term
            .replace("!", "!!")
            .replace("%", "!%")
            .replace("_", "!_");
}

String sql = "SELECT id FROM product "
        + "WHERE product_name LIKE ? ESCAPE '!'";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    String pattern = "%" + escapeLikeTerm(searchText) + "%";
    ps.setString(1, pattern);
    try (ResultSet rs = ps.executeQuery()) {
        // ...
    }
}
~~~

Cú pháp `ESCAPE`, kiểu collation, khả năng phân biệt hoa thường và cách xử lý các pattern có thể khác nhau theo hệ quản trị. Cần kiểm chứng trên DB đang dùng. Đừng nhầm việc escape ký tự tìm kiếm của `LIKE` với cơ chế ngăn SQL injection: **marker `?` vẫn là lớp phòng vệ chính**.

## 9. Phòng vệ đi kèm việc tham số hóa

Tham số hóa bảo vệ ranh giới **dữ liệu → cú pháp SQL**. Để bảo vệ truy cập dữ liệu toàn diện, ứng dụng vẫn cần nhiều kiểm soát khác:

| Biện pháp | Mục đích | Ví dụ |
| --- | --- | --- |
| Kiểm tra quyền truy cập | Ngăn đọc/sửa dữ liệu không thuộc quyền người dùng | `WHERE tenant_id = ? AND id = ?` kết hợp xác thực ở tầng ứng dụng |
| Quyền DB tối thiểu | Giới hạn hậu quả nếu một đường truy cập gặp lỗi | Tài khoản chỉ đọc không có quyền `DELETE` hoặc `DROP` |
| Validation dữ liệu | Loại bỏ dữ liệu sai định dạng, giới hạn độ dài, số lượng | ID phải dương, danh sách ID có giới hạn, email đúng giới hạn độ dài |
| Bảo vệ thông tin kết nối | Không để lộ credential hoặc chuỗi kết nối | Dùng cơ chế lưu secret; tránh ghi password vào log |
| Xử lý lỗi có kiểm soát | Không tiết lộ schema hoặc SQL nhạy cảm qua API | Log kỹ thuật phù hợp và trả lỗi tổng quát cho client |
| Kiểm thử đường SQL động | Tìm chỗ nối chuỗi còn sót | Rà soát các thao tác `Statement`, `prepareStatement` và query builder |

Ví dụ lọc theo quyền sở hữu bản ghi:

~~~java
String sql = "SELECT id, amount FROM invoice "
        + "WHERE tenant_id = ? AND id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    // authenticatedTenantId phải đến từ thông tin xác thực đã được kiểm tra,
    // không nhận trực tiếp từ trường tenantId do client tự gửi.
    ps.setLong(1, authenticatedTenantId);
    ps.setLong(2, requestedInvoiceId);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            // Chỉ xử lý bản ghi trong tenant đã xác thực.
        }
    }
}
~~~

Truy vấn trên có hai giá trị được bind. Nhưng **chỉ dùng `PreparedStatement` không tự thực hiện phân quyền**: nếu ứng dụng cho người dùng tự chọn `authenticatedTenantId`, họ vẫn có thể truy cập dữ liệu khác dù câu SQL không thể bị injection.

### Stored procedure không phải ngoại lệ

`CallableStatement` cũng có thể bind tham số:

~~~java
import java.sql.CallableStatement;

try (CallableStatement cs =
        connection.prepareCall("{call find_user_by_email(?)}")) {
    cs.setString(1, requestedEmail);
    cs.execute();
}
~~~

Việc bind trong Java giúp truyền đầu vào an toàn đến procedure, nhưng **procedure vẫn có thể tự tạo lỗ hổng** nếu bên trong nó nối các tham số vào SQL động rồi thực thi. Khi đó phải dùng phương thức bind tham số thích hợp *ngay trong procedure* hoặc phương án cú pháp an toàn của DB.

## 10. Kiểm thử và rà soát

Khi viết mã JDBC, ngoài các case chức năng bình thường, nên thử các đầu vào có ký tự đặc biệt để xác minh rằng chúng được coi là **dữ liệu nguyên văn**:

| Đầu vào kiểm thử | Kết quả mong đợi khi đã bind đúng |
| --- | --- |
| `alice@example.com` | Chỉ tìm đúng bản ghi email tương ứng |
| `O'Connor` | Giữ dấu nháy trong giá trị, không lỗi cú pháp vì ghép chuỗi |
| `' OR '1'='1` | Không làm thay đổi cấu trúc `WHERE`; chỉ so sánh như chuỗi |
| `%` hoặc `_` trong tìm kiếm `LIKE` | Hành vi đúng theo chính sách wildcard/escape đã chọn |
| Danh sách ID rỗng | Xử lý chủ động, không tạo `IN ()` sai cú pháp |
| Nhiều ID hoặc chuỗi quá dài | Áp dụng giới hạn tài nguyên và validation |
| `sortKey` không nằm trong whitelist | Từ chối trước khi tạo SQL |

Khi rà soát code, tìm các biểu hiện như:

~~~java
connection.createStatement();             // Cần rà soát nếu SQL động.
connection.prepareStatement(sqlText);      // Cần kiểm tra sqlText được dựng thế nào.
"WHERE id = " + requestId;                // Mẫu ghép giá trị không an toàn.
"ORDER BY " + requestedColumn;            // Mẫu ghép cú pháp không kiểm soát.
~~~

`Statement` không có lỗi chỉ vì được dùng: chạy một câu SQL **hoàn toàn cố định** bằng `Statement` có thể an toàn về injection. Vấn đề là có hay không **giá trị không tin cậy được chèn vào cấu trúc SQL**. Tương tự, ORM hoặc thư viện query builder vẫn cần được kiểm tra ở những điểm nhận **raw SQL** hoặc nối chuỗi động.

## 11. Những hiểu nhầm cần tránh

**“Đã dùng `PreparedStatement` thì mọi vị trí trong truy vấn đều an toàn.”** Sai. Những đoạn SQL được nối trước khi gọi `prepareStatement` vẫn có thể bị injection, đặc biệt ở `ORDER BY`, tên bảng và phần `WHERE` động.

**“Chỉ cần xóa dấu nháy đơn khỏi input.”** Sai. Cách lọc ký tự bằng blacklist vừa dễ thiếu trường hợp, vừa phá dữ liệu hợp lệ (chẳng hạn họ `O'Connor`). Bind tham số xử lý đúng ranh giới cú pháp và dữ liệu.

**“Chỉ cần xác thực người dùng là đủ.”** Sai. Người dùng đã đăng nhập vẫn có thể gửi đầu vào chứa SQL độc hại. Xác thực, phân quyền và tham số hóa giải quyết những vấn đề khác nhau.

**“`IN (?)` có thể nhận chuỗi nhiều ID.”** Sai. Một marker đại diện một giá trị; cần nhiều marker, dùng array/table parameter đặc thù DB hoặc giải pháp tương đương được hỗ trợ.

**“Dùng `LIKE ?` thì mọi ký tự đều được tìm chính xác.”** Chưa chắc. `%` và `_` là wildcard theo quy tắc `LIKE`; cần escape chúng nếu chức năng là tìm đúng ký tự.

## 12. Quy trình áp dụng nhanh trong một tính năng JDBC

1. Xác định câu SQL và phân loại mỗi thành phần thành **cú pháp cố định** hoặc **giá trị thay đổi**.
2. Đặt `?` cho **tất cả giá trị thay đổi** trong SQL; không bọc marker trong nháy đơn.
3. Tạo `PreparedStatement`, bind giá trị bằng `setXxx`/`setObject` theo **đúng vị trí và kiểu**.
4. Với tên cột/bảng, hướng sắp xếp hoặc mệnh đề động, ánh xạ các lựa chọn sang **whitelist cú pháp đã biết**, không chèn chuỗi tùy ý.
5. Dùng `try-with-resources` để đóng tài nguyên JDBC; kiểm tra quyền, giới hạn dữ liệu và xử lý lỗi phù hợp.
6. Kiểm thử dấu nháy, chuỗi giống SQL, wildcard `LIKE`, danh sách `IN` và mọi nhánh có xây dựng SQL động.

**Nguyên tắc thực hành:** **viết SQL như cấu trúc, truyền dữ liệu như tham số**. Khi mọi dữ liệu không tin cậy đều đi qua binding và phần SQL động được kiểm soát bằng các lựa chọn cố định, mã JDBC có thể ngăn SQL injection ngay tại ranh giới truy cập cơ sở dữ liệu.
