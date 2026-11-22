# Giữ dữ liệu đầu vào an toàn bằng tham số hóa thay vì ghép chuỗi — Java 17 Text Block

Khi ứng dụng Java làm việc với cơ sở dữ liệu, nó thường phải đưa dữ liệu người dùng vào câu lệnh SQL: tìm tài khoản theo email, lọc đơn hàng theo trạng thái, cập nhật tên hoặc xóa bản ghi. Nếu nối trực tiếp dữ liệu đầu vào vào chuỗi SQL, ký tự đặc biệt có thể làm thay đổi cấu trúc câu lệnh. Đây là nguyên nhân phổ biến của **SQL injection**.

Cách xử lý chuẩn trong JDBC là dùng **`PreparedStatement` và bind parameter** để tách cấu trúc SQL khỏi giá trị dữ liệu. Java 17 có **text block** (chuỗi nhiều dòng, cú pháp `"""`) giúp trình bày SQL dễ đọc. Tuy nhiên, text block chỉ cải thiện cách viết chuỗi. Nó **không tự tham số hóa, không tự escape dữ liệu và không tự ngăn SQL injection**. Muốn an toàn, hãy kết hợp text block với `PreparedStatement`.

## 1. Text block giải quyết vấn đề trình bày SQL

Trước Java 15, một câu SQL nhiều dòng thường phải nối chuỗi:

```java
String sql =
        "SELECT id, email, display_name " +
        "FROM users " +
        "WHERE status = ? " +
        "ORDER BY created_at DESC";
```

Java 17 hỗ trợ text block:

```java
String sql = """
        SELECT id, email, display_name
        FROM users
        WHERE status = ?
        ORDER BY created_at DESC
        """;
```

Cả hai cách đều tạo ra một đối tượng `String`. Text block làm cho câu SQL gần với cách viết trong công cụ quản trị cơ sở dữ liệu, thuận tiện khi đọc và bảo trì. Text block bắt đầu bằng `"""`, chứa nội dung nhiều dòng và kết thúc bằng `"""` đóng. Java áp dụng quy tắc xử lý khoảng trắng đầu dòng và dòng kết thúc; phần thụt lề chung được loại bỏ.

Text block vẫn chỉ là chuỗi. Java không phân tích nội dung này thành câu lệnh SQL và cũng không tự nhận diện phần nào là dữ liệu đầu vào.

## 2. Vì sao ghép chuỗi với dữ liệu người dùng nguy hiểm?

Giả sử ứng dụng tìm tài khoản bằng email. Cách viết sau không an toàn:

```java
String email = inputFromUser;

String sql = "SELECT id, email FROM users WHERE email = '"
        + email + "'";

try (Statement statement = connection.createStatement();
     ResultSet result = statement.executeQuery(sql)) {
    // Đọc kết quả...
}
```

Ứng dụng đã trộn **cấu trúc SQL** với **giá trị dữ liệu** trong cùng một chuỗi. Nếu email bình thường là `lan@example.com`, câu lệnh trông có vẻ hoạt động.

Nhưng người dùng có thể nhập một giá trị chứa cú pháp SQL, ví dụ:

```text
' OR '1'='1
```

Sau khi ghép, câu SQL có thể trở thành:

```sql
SELECT id, email FROM users
WHERE email = '' OR '1'='1'
```

Điều kiện `'1'='1'` luôn đúng, nên câu lệnh có thể trả về nhiều tài khoản thay vì chỉ tài khoản có email được yêu cầu. Tùy câu lệnh và quyền của tài khoản cơ sở dữ liệu, SQL injection có thể dẫn đến đọc, sửa hoặc xóa dữ liệu ngoài ý định.

Không nên cố giải quyết bằng cách tự thay dấu nháy đơn hoặc tự viết hàm escape cho mọi loại đầu vào. Quy tắc escape phụ thuộc ngữ cảnh và hệ quản trị cơ sở dữ liệu; cách xử lý thủ công thiếu sót rất dễ để lại lỗ hổng.

## 3. Kết hợp text block với PreparedStatement

Thay vì ghép email vào chuỗi SQL, viết một dấu `?` làm vị trí tham số:

```java
String sql = """
        SELECT id, email
        FROM users
        WHERE email = ?
        """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, email);

    try (ResultSet result = statement.executeQuery()) {
        while (result.next()) {
            System.out.println(result.getLong("id"));
            System.out.println(result.getString("email"));
        }
    }
}
```

Có hai phần riêng biệt:

1. **SQL template:** câu lệnh có cấu trúc cố định và vị trí tham số `?`.
2. **Giá trị tham số:** được truyền bằng `setString(1, email)`.

Cơ sở dữ liệu nhận biết giá trị được bind là dữ liệu của tham số, không phải một phần cú pháp SQL cần phân tích lại. Nếu người dùng nhập `' OR '1'='1`, toàn bộ chuỗi đó được so sánh như giá trị email; nó không biến thành toán tử `OR` hay điều kiện mới.

### Số thứ tự tham số bắt đầu từ 1

Trong JDBC, chỉ số của tham số `?` bắt đầu từ **1**, không phải 0.

```java
String sql = """
        SELECT id, email
        FROM users
        WHERE email = ?
          AND status = ?
        """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, email);
    statement.setString(2, "ACTIVE");

    try (ResultSet result = statement.executeQuery()) {
        // Xử lý kết quả...
    }
}
```

Tham số đầu tiên là `email`, tham số thứ hai là `status`. Thứ tự gọi `set...` phải khớp thứ tự dấu `?` trong câu SQL.

### Không đặt dấu nháy quanh dấu hỏi

**Sai:**

```java
String sql = """
        SELECT id, email
        FROM users
        WHERE email = '?'
        """;
```

`'?'` là một chuỗi ký tự trong SQL, không phải placeholder tham số. JDBC không thể bind email vào vị trí đó như mong muốn.

**Đúng:**

```java
String sql = """
        SELECT id, email
        FROM users
        WHERE email = ?
        """;
```

Không tự thêm dấu nháy quanh placeholder. Driver xử lý cách truyền giá trị theo kiểu dữ liệu đã bind.

## 4. Ví dụ đầy đủ: tìm người dùng bằng email

Ví dụ sau sử dụng JDBC chuẩn, text block và `PreparedStatement`. Phương thức nhận một `Connection` do bên gọi cung cấp; phương thức không tự đóng connection đó.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;

public class UserRepository {

    public record User(long id, String email, String displayName) {
    }

    public static Optional<User> findByEmail(
            Connection connection,
            String email
    ) throws SQLException {

        String sql = """
                SELECT id, email, display_name
                FROM users
                WHERE email = ?
                """;

        try (PreparedStatement statement =
                     connection.prepareStatement(sql)) {

            statement.setString(1, email);

            try (ResultSet result = statement.executeQuery()) {
                if (!result.next()) {
                    return Optional.empty();
                }

                User user = new User(
                        result.getLong("id"),
                        result.getString("email"),
                        result.getString("display_name")
                );

                return Optional.of(user);
            }
        }
    }
}
```

Các điểm cần chú ý:

- Câu SQL được viết nhiều dòng bằng text block nên dễ đọc.
- Dữ liệu `email` không được nối vào câu SQL.
- `setString(1, email)` bind email vào placeholder đầu tiên.
- `PreparedStatement` và `ResultSet` được đóng bằng try-with-resources.
- `Connection` thuộc quyền quản lý của bên gọi; đóng connection ở đây có thể làm hỏng một transaction hoặc tác vụ khác đang sử dụng nó.

Đoạn mã giả định bảng `users` có các cột `id`, `email` và `display_name`. Tên bảng, cột và kiểu dữ liệu thực tế phải phù hợp với schema của ứng dụng.

## 5. Text block không tự làm cho câu SQL an toàn

Một lỗi hiểu nhầm phổ biến là cho rằng chuyển chuỗi ghép sang text block sẽ giải quyết SQL injection.

**Sai — vẫn ghép đầu vào không đáng tin cậy:**

```java
String sql = """
        SELECT id, email
        FROM users
        WHERE email = '%s'
        """.formatted(email);
```

`String.formatted` chỉ định dạng chuỗi. Nếu `email` chứa cú pháp SQL, nó vẫn được đưa trực tiếp vào câu lệnh.

**Sai — text block không biến phép nối thành tham số:**

```java
String sql = """
        SELECT id, email
        FROM users
        WHERE email = '""" + email + """
        '
        """;
```

Đoạn trên vẫn ghép chuỗi. Việc dùng dấu `"""` không thay đổi bản chất của phép nối.

**Đúng — giữ placeholder trong text block và bind riêng:**

```java
String sql = """
        SELECT id, email
        FROM users
        WHERE email = ?
        """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, email);
    try (ResultSet result = statement.executeQuery()) {
        // ...
    }
}
```

| Thành phần | Vai trò | Có chống SQL injection khi dùng riêng? |
| --- | --- | --- |
| Text block `"""` | Viết chuỗi nhiều dòng dễ đọc. | Không. |
| `String.format` / `formatted` | Chèn giá trị vào chuỗi theo định dạng. | Không. |
| Nối chuỗi `+` | Ghép các đoạn chuỗi. | Không. |
| `PreparedStatement` với bind parameter | Tách giá trị dữ liệu khỏi cấu trúc câu SQL. | Có, đối với các giá trị được bind đúng cách. |

## 6. Bind đúng kiểu dữ liệu

JDBC cung cấp nhiều phương thức để gán giá trị theo kiểu:

| Kiểu Java thường dùng | Phương thức JDBC |
| --- | --- |
| `String` | `setString(index, value)` |
| `int` | `setInt(index, value)` |
| `long` | `setLong(index, value)` |
| `boolean` | `setBoolean(index, value)` |
| `BigDecimal` | `setBigDecimal(index, value)` |
| `LocalDate` | Chuyển qua `java.sql.Date.valueOf(value)` rồi dùng `setDate` |
| `LocalDateTime` | Chuyển qua `java.sql.Timestamp.valueOf(value)` rồi dùng `setTimestamp` |
| Giá trị `null` | `setNull(index, Types.TYPE)` với kiểu SQL phù hợp |

Ví dụ tìm đơn hàng theo trạng thái, mã khách và ngày tạo:

```java
import java.sql.Connection;
import java.sql.Date;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalDate;

public class OrderSearch {

    static void search(
            Connection connection,
            long customerId,
            String status,
            LocalDate createdOn
    ) throws SQLException {

        String sql = """
                SELECT id, customer_id, status, created_at
                FROM orders
                WHERE customer_id = ?
                  AND status = ?
                  AND created_at >= ?
                ORDER BY created_at DESC
                """;

        try (PreparedStatement statement =
                     connection.prepareStatement(sql)) {

            statement.setLong(1, customerId);
            statement.setString(2, status);
            statement.setDate(3, Date.valueOf(createdOn));

            try (ResultSet result = statement.executeQuery()) {
                while (result.next()) {
                    System.out.println(
                            result.getLong("id") + " "
                            + result.getString("status")
                    );
                }
            }
        }
    }
}
```

Bind theo kiểu dữ liệu giúp driver chuyển giá trị phù hợp với kiểu SQL. Tránh chuyển tất cả thành chuỗi rồi tự thêm dấu nháy vào câu lệnh.

Ví dụ trên giả định `created_at` có kiểu ngày phù hợp với `java.sql.Date`. Nếu cột là timestamp, hãy chọn kiểu Java/JDBC tương ứng, chẳng hạn `LocalDateTime` kết hợp `Timestamp.valueOf` hoặc API thời gian phù hợp với hệ quản trị.

Nếu một tham số có thể `null`, hãy quyết định rõ ý nghĩa nghiệp vụ. Ví dụ, để tìm bản ghi có cột `deleted_at` là SQL NULL, dùng `IS NULL`; không viết `deleted_at = ?` rồi truyền `null` và kỳ vọng nó tương đương `IS NULL` trong SQL.

## 7. Tham số hóa câu lệnh INSERT, UPDATE và DELETE

Nguyên tắc bind parameter không chỉ dùng cho `SELECT`.

### INSERT

```java
String sql = """
        INSERT INTO users (email, display_name, status)
        VALUES (?, ?, ?)
        """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, email);
    statement.setString(2, displayName);
    statement.setString(3, "ACTIVE");

    int insertedRows = statement.executeUpdate();
    System.out.println("Số dòng được thêm: " + insertedRows);
}
```

`executeUpdate()` trả số dòng bị tác động đối với câu lệnh cập nhật dữ liệu như `INSERT`, `UPDATE` và `DELETE`.

### UPDATE

```java
String sql = """
        UPDATE users
        SET display_name = ?, status = ?
        WHERE id = ?
        """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, displayName);
    statement.setString(2, status);
    statement.setLong(3, userId);

    int updatedRows = statement.executeUpdate();
    System.out.println("Số dòng được cập nhật: " + updatedRows);
}
```

### DELETE

```java
String sql = """
        DELETE FROM users
        WHERE id = ?
        """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, userId);

    int deletedRows = statement.executeUpdate();
    System.out.println("Số dòng được xóa: " + deletedRows);
}
```

Với `UPDATE` và `DELETE`, đặc biệt chú ý điều kiện `WHERE`. Tham số hóa bảo vệ giá trị đầu vào khỏi biến thành cú pháp SQL, nhưng không tự đảm bảo câu lệnh có phạm vi tác động đúng. Một lệnh `DELETE` thiếu `WHERE` vẫn có thể xóa toàn bộ bảng.

## 8. Không thể bind tên bảng, tên cột hoặc từ khóa SQL bằng placeholder

Placeholder của `PreparedStatement` dành cho **giá trị dữ liệu**, không phải tên bảng, tên cột, toán tử, từ khóa hay hướng sắp xếp.

**Sai — cố bind tên cột:**

```java
String sql = """
        SELECT id, email
        FROM users
        ORDER BY ?
        """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, "email");
}
```

Trong nhiều hệ quản trị, câu lệnh trên không sắp xếp theo cột `email` như mong muốn. Placeholder được hiểu là một giá trị biểu thức, không phải identifier để thay thế cấu trúc SQL.

**Sai — nối trực tiếp tên cột do người dùng gửi:**

```java
String sortColumn = inputFromUser;

String sql = """
        SELECT id, email
        FROM users
        ORDER BY
        """ + sortColumn;
```

Nếu `sortColumn` không được kiểm soát, người dùng có thể đưa thêm cú pháp SQL vào vị trí cấu trúc.

### Cách đúng: whitelist identifier được phép

Nếu ứng dụng cho phép sắp xếp theo một số trường cố định, ánh xạ đầu vào sang các tên cột đã định nghĩa trong code:

```java
import java.util.Map;

public class UserSort {

    private static final Map<String, String> SORT_COLUMNS = Map.of(
            "email", "email",
            "created", "created_at",
            "name", "display_name"
    );

    static String buildQuery(String requestedSort, boolean ascending) {
        String column = SORT_COLUMNS.get(requestedSort);

        if (column == null) {
            throw new IllegalArgumentException("Trường sắp xếp không hợp lệ");
        }

        String direction = ascending ? "ASC" : "DESC";

        return """
                SELECT id, email, display_name
                FROM users
                ORDER BY %s %s
                """.formatted(column, direction);
    }
}
```

Ở đây, `requestedSort` chỉ được ánh xạ sang các chuỗi hằng đã khai báo trong code; `direction` chỉ có thể là `ASC` hoặc `DESC`. Trong ví dụ này, `formatted` được dùng cho identifier và từ khóa đã được whitelist/kiểm soát chặt chẽ. **Giá trị dữ liệu** như email, tên người dùng hoặc mã đơn hàng vẫn phải bind bằng `PreparedStatement`.

Nếu không cần sắp xếp động, tốt nhất viết sẵn câu SQL với cột và hướng sắp xếp cố định.

## 9. Tìm kiếm bằng LIKE: bind giá trị nhưng hiểu rõ wildcard

Có thể bind mẫu tìm kiếm cho `LIKE`:

```java
String sql = """
        SELECT id, display_name
        FROM users
        WHERE display_name LIKE ?
        """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, "%" + keyword + "%");

    try (ResultSet result = statement.executeQuery()) {
        while (result.next()) {
            System.out.println(result.getString("display_name"));
        }
    }
}
```

Việc nối `"%" + keyword + "%"` ở đây tạo **giá trị của tham số**, không nối `keyword` vào cấu trúc SQL. Placeholder vẫn được bind an toàn.

Tuy nhiên, `%` và `_` là ký tự wildcard của `LIKE` trong nhiều hệ quản trị: `%` khớp không hoặc nhiều ký tự; `_` khớp một ký tự. Nếu nghiệp vụ muốn tìm chuỗi theo nghĩa đen, cần escape các wildcard theo cú pháp `ESCAPE` được hệ quản trị hỗ trợ. Đây là vấn đề **ngữ nghĩa tìm kiếm**, khác với SQL injection.

## 10. Truy vấn IN với số lượng tham số thay đổi

Không thể truyền một danh sách ID bằng cách bind một chuỗi chứa dấu phẩy rồi kỳ vọng SQL tách nó thành nhiều giá trị.

**Sai:**

```java
String sql = "SELECT id FROM users WHERE id IN (?)";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, "10,20,30");
}
```

Dấu `?` là **một giá trị**. Chuỗi `"10,20,30"` không tự biến thành ba tham số SQL.

### Tạo số placeholder theo kích thước danh sách

Số lượng dấu `?` có thể được tạo từ **số phần tử**, trong khi từng giá trị vẫn được bind riêng:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Collections;
import java.util.List;

public class UserBatchSearch {

    static void findByIds(
            Connection connection,
            List<Long> ids
    ) throws SQLException {

        if (ids.isEmpty()) {
            return;
        }

        String placeholders = String.join(
                ", ",
                Collections.nCopies(ids.size(), "?")
        );

        String sql = """
                SELECT id, email
                FROM users
                WHERE id IN (%s)
                """.formatted(placeholders);

        try (PreparedStatement statement =
                     connection.prepareStatement(sql)) {

            for (int i = 0; i < ids.size(); i++) {
                statement.setLong(i + 1, ids.get(i));
            }

            try (ResultSet result = statement.executeQuery()) {
                while (result.next()) {
                    System.out.println(result.getLong("id"));
                }
            }
        }
    }
}
```

Với danh sách ba ID, SQL template có dạng:

```sql
SELECT id, email
FROM users
WHERE id IN (?, ?, ?)
```

Các giá trị `10`, `20` và `30` được bind lần lượt vào vị trí 1, 2, 3. Nội dung SQL động chỉ phụ thuộc vào **số lượng phần tử**, không phụ thuộc vào chuỗi dữ liệu của từng ID.

Lưu ý:

- Xử lý danh sách rỗng trước khi tạo `IN ()`; cú pháp này không được mọi hệ quản trị chấp nhận.
- Kiểm soát số lượng phần tử để tránh vượt giới hạn tham số của database/driver.
- Nếu danh sách rất lớn, cân nhắc batch, bảng tạm hoặc cơ chế phù hợp với hệ quản trị.
- Không nối các giá trị ID thành chuỗi SQL.

## 11. Tránh dùng Statement cho dữ liệu không đáng tin cậy

JDBC có ba loại statement thường gặp:

| Loại | Cách tạo | Cách dùng |
| --- | --- | --- |
| `Statement` | `connection.createStatement()` | Thực thi câu SQL đã hoàn chỉnh; không có API bind parameter theo vị trí. |
| `PreparedStatement` | `connection.prepareStatement(sql)` | Dùng placeholder `?` và các phương thức `set...` để bind giá trị. |
| `CallableStatement` | `connection.prepareCall(sql)` | Gọi stored procedure; có hỗ trợ tham số theo quy tắc JDBC. |

Với câu SQL có dữ liệu đầu vào từ bên ngoài, ưu tiên `PreparedStatement`. Text block dùng được với cả `Statement` và `PreparedStatement`, nhưng mức bảo vệ phụ thuộc cách truyền dữ liệu.

**Sai:**

```java
String sql = """
        SELECT id
        FROM users
        WHERE email = '%s'
        """.formatted(email);

try (Statement statement = connection.createStatement()) {
    statement.executeQuery(sql);
}
```

**Đúng:**

```java
String sql = """
        SELECT id
        FROM users
        WHERE email = ?
        """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, email);
    statement.executeQuery();
}
```

Với câu SQL cố định, không chứa dữ liệu đầu vào không đáng tin cậy, `Statement` vẫn là API JDBC hợp lệ. Điểm quan trọng là không đưa dữ liệu không đáng tin cậy vào cấu trúc SQL bằng phép ghép chuỗi.

## 12. Tham số hóa không thay thế transaction

`PreparedStatement` giúp tách dữ liệu khỏi cú pháp SQL, nhưng không tự tạo transaction và không bảo đảm nhiều câu lệnh cùng thành công hoặc cùng thất bại.

Nếu nghiệp vụ cần nhiều thao tác SQL như chuyển tiền, tạo đơn hàng cùng các dòng chi tiết hoặc cập nhật nhiều bảng, hãy quản lý transaction bằng `Connection`:

- Bắt đầu transaction bằng cách tắt auto-commit khi phù hợp.
- Thực hiện từng câu lệnh bằng `PreparedStatement` và bind các giá trị.
- Gọi `commit()` khi toàn bộ công việc thành công.
- Gọi `rollback()` khi một bước thất bại.
- Khôi phục trạng thái connection theo quyền sở hữu và quy ước của ứng dụng.

Connection pool, transaction framework hoặc ORM có thể quản lý transaction thay cho code JDBC trực tiếp. Không nên tự commit một connection đang thuộc transaction do lớp gọi quản lý.

## 13. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| Dùng text block là đã chống SQL injection. | Text block chỉ là cách viết `String` nhiều dòng; vẫn cần bind parameter. |
| Đã dùng `PreparedStatement` thì có thể nối dữ liệu tùy ý vào SQL. | Chỉ các giá trị nằm ở placeholder mới được bind. Identifier và cú pháp động phải được whitelist hoặc thiết kế an toàn. |
| Có thể đặt `?` cho tên bảng hoặc tên cột. | `?` là vị trí cho giá trị, không phải identifier. |
| Truyền `"1,2,3"` vào một placeholder sẽ tương đương ba phần tử `IN`. | Đó chỉ là một giá trị chuỗi. Cần tạo từng placeholder và bind từng phần tử. |
| Dữ liệu đã bind thì không cần kiểm tra nghiệp vụ. | Tham số hóa chống thay đổi cú pháp SQL, không thay thế validation, authorization hay kiểm tra phạm vi tác động. |
| `LIKE ?` không còn wildcard. | `%` và `_` vẫn có ý nghĩa wildcard của `LIKE`; cần xử lý nếu muốn tìm chuỗi nghĩa đen. |
| Có thể tự escape dấu nháy rồi dùng nối chuỗi. | Tự escape dễ sai ngữ cảnh và không thay thế parameterization. |
| `PreparedStatement` tự mở và đóng transaction. | Transaction vẫn do connection và ứng dụng quản lý. |

## 14. Các nguyên tắc an toàn bổ sung

Tham số hóa là biện pháp quan trọng, nhưng một truy vấn an toàn trong ứng dụng còn cần một số nguyên tắc khác.

### Chỉ lấy quyền cơ sở dữ liệu cần thiết

Tài khoản ứng dụng nên có đúng quyền cần cho chức năng. Ví dụ, thành phần chỉ đọc báo cáo không nên dùng tài khoản có quyền xóa bảng hoặc thay đổi cấu trúc schema. Nếu một lỗi SQL xảy ra, quyền tối thiểu giúp hạn chế phạm vi thiệt hại.

### Kiểm tra quyền truy cập bản ghi

Một truy vấn có bind parameter vẫn có thể cho phép người dùng xem dữ liệu của tài khoản khác nếu thiếu điều kiện phân quyền:

```java
String sql = """
        SELECT id, email
        FROM users
        WHERE id = ?
          AND tenant_id = ?
        """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, userId);
    statement.setLong(2, currentTenantId);
    // ...
}
```

`userId` và `currentTenantId` phải đến từ ngữ cảnh đã xác thực/phân quyền phù hợp. Không nên tin một giá trị tenant do client gửi lên mà không kiểm tra quyền của người gọi.

### Không ghi log dữ liệu nhạy cảm tùy tiện

Tránh ghi toàn bộ email, token, mật khẩu, số thẻ hoặc thông tin cá nhân vào log khi không cần thiết. Log nên cung cấp đủ thông tin chẩn đoán mà không làm lộ dữ liệu nhạy cảm.

### Validation vẫn cần thiết

Ví dụ, bind `quantity = -100` vẫn an toàn về cấu trúc SQL, nhưng có thể vi phạm nghiệp vụ. Hãy kiểm tra giới hạn, định dạng, quyền và trạng thái trước khi thực hiện thao tác.

### Không trả lỗi database thô cho người dùng

Thông báo SQL chi tiết có thể tiết lộ tên bảng, cột, cấu trúc schema hoặc thông tin nội bộ. Ghi log lỗi ở phía máy chủ theo chính sách bảo mật và trả thông báo phù hợp cho client.

## 15. Bài thực hành

Các bài sau dùng Java 17 và JDBC. Bạn cần một cơ sở dữ liệu thử nghiệm có bảng tương ứng và JDBC driver phù hợp để chạy truy vấn. Các câu SQL minh họa dùng cú pháp phổ biến; kiểu cột, tên bảng và cấu hình kết nối có thể cần điều chỉnh theo hệ quản trị.

### Bài 1 — chuyển truy vấn ghép chuỗi sang tham số hóa

Cho đoạn mã không an toàn:

```java
String sql = """
        SELECT id, email
        FROM users
        WHERE email = '%s'
        """.formatted(email);
```

Hãy:

1. Thay `%s` bằng placeholder JDBC.
2. Tạo `PreparedStatement` từ câu SQL.
3. Bind `email` bằng `setString`.
4. Thực thi truy vấn và duyệt `ResultSet`.

### Bài 2 — nhiều tham số có kiểu khác nhau

Viết truy vấn:

```sql
SELECT id, total
FROM orders
WHERE customer_id = ?
  AND status = ?
  AND total >= ?
```

Bind lần lượt `long customerId`, `String status` và `BigDecimal minimumTotal`. Dùng đúng phương thức JDBC cho từng kiểu.

### Bài 3 — sắp xếp theo cột được chọn

Cho phép client chọn một trong ba giá trị `email`, `name` hoặc `created`. Viết một whitelist ánh xạ chúng sang các cột SQL đã định nghĩa trong code. Nếu giá trị không thuộc danh sách, từ chối yêu cầu.

Không nối trực tiếp chuỗi client gửi vào `ORDER BY`.

### Bài 4 — tìm kiếm theo từ khóa

Viết câu SQL:

```sql
SELECT id, display_name
FROM users
WHERE display_name LIKE ?
```

Bind mẫu `"%" + keyword + "%"`. Giải thích vì sao phép nối này tạo giá trị tham số chứ không tạo cú pháp SQL. Sau đó tìm hiểu cách escape wildcard nếu yêu cầu tìm chuỗi nghĩa đen.

### Bài 5 — truy vấn danh sách ID

Cho `List<Long> ids` có số lượng phần tử thay đổi. Xử lý trường hợp danh sách rỗng, tạo số placeholder tương ứng với số ID và bind từng ID vào `PreparedStatement`.

Không bind toàn bộ danh sách thành một chuỗi có dấu phẩy.

## 16. Ghi nhớ nhanh

| Nhu cầu | Cách làm |
| --- | --- |
| Viết SQL nhiều dòng dễ đọc | Dùng Java text block `""" ... """`. |
| Truyền giá trị người dùng vào SQL | Dùng `PreparedStatement` với `?`. |
| Bind chuỗi | `statement.setString(1, value)`. |
| Bind số nguyên | `setInt` hoặc `setLong` phù hợp. |
| Thêm/sửa/xóa dữ liệu | Dùng `executeUpdate()` và kiểm tra số dòng bị tác động. |
| Đọc dữ liệu | Dùng `executeQuery()` và đóng `ResultSet`. |
| Tên cột/bảng hoặc hướng sắp xếp động | Whitelist giá trị identifier và từ khóa được phép. |
| Danh sách cho `IN` | Tạo số placeholder theo số phần tử và bind từng giá trị. |
| Xử lý tìm kiếm `LIKE` | Bind mẫu tìm kiếm; hiểu riêng ý nghĩa wildcard `%` và `_`. |
| Nhiều thao tác phải thành công cùng nhau | Quản lý transaction bằng `Connection`. |

**Nguyên tắc cốt lõi:** Text block giúp câu SQL trong Java 17 dễ đọc; `PreparedStatement` mới là cơ chế tách dữ liệu khỏi cú pháp SQL. Hãy giữ cấu trúc truy vấn cố định, bind mọi giá trị đầu vào bằng phương thức JDBC phù hợp, và chỉ tạo phần SQL động từ các lựa chọn đã được whitelist.
