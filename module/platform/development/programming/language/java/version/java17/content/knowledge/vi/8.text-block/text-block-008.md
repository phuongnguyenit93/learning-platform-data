# Dùng `formatted()` với text block để chèn giá trị và giới hạn khi tạo SQL

Trong Java 17, **text block** giúp viết câu SQL nhiều dòng dễ đọc, còn phương thức **`String.formatted(...)`** giúp thay các ký hiệu định dạng như `%s`, `%d` bằng đối số. Hai tính năng này thường được dùng cùng nhau để tạo một chuỗi SQL có cấu trúc rõ ràng.

Tuy nhiên, cần phân biệt hai việc:

- `formatted()` chỉ **tạo ra một chuỗi đã thay thế ký hiệu định dạng**. Nó không hiểu SQL, không tự thêm dấu nháy, không escape dữ liệu theo quy tắc của cơ sở dữ liệu và không bind tham số.
- Với **giá trị do người dùng hoặc hệ thống bên ngoài cung cấp**, hãy dùng `PreparedStatement` và dấu tham số `?`. Đây là cách JDBC truyền giá trị tách khỏi câu lệnh SQL.

Bài này tập trung vào cách dùng `formatted()` đúng chỗ, những giới hạn khi tạo SQL và cách kết hợp text block với JDBC an toàn trong Java 17.

> **Phiên bản:** Text blocks và `String.formatted(...)` đều đã chính thức từ Java 15, nên dùng ổn định trong Java 17 mà không cần `--enable-preview`.

## 1. Text block và `formatted()` làm hai công việc khác nhau

Text block là cú pháp chuỗi nhiều dòng, mở bằng ba dấu nháy kép `"""`. Ví dụ:

~~~java
String sql = """
        SELECT id, name
        FROM users
        WHERE active = true
        ORDER BY name
        """;
~~~

Chuỗi này dễ đọc hơn cách ghép nhiều đoạn bằng dấu `+` hoặc viết ký tự xuống dòng `\n` thủ công.

`formatted()` là phương thức của `String`, dùng cú pháp định dạng tương tự `String.format(...)`:

~~~java
String message = "Xin chào, %s!".formatted("An");
System.out.println(message);
~~~

Kết quả:

~~~text
Xin chào, An!
~~~

Có thể gọi phương thức đó trực tiếp trên text block:

~~~java
String message = """
        Xin chào, %s!
        Bạn đang học Java %d.
        """.formatted("An", 17);
~~~

Ở đây:

- Text block cung cấp nội dung nhiều dòng.
- `%s` và `%d` là **format specifier**.
- Các đối số `"An"` và `17` được đưa vào vị trí tương ứng.
- Kết quả trả về vẫn là một đối tượng `String`; chuỗi mẫu ban đầu không bị sửa.

**Không nên hiểu `formatted()` là cú pháp đặc biệt của SQL.** Nó hoạt động trên mọi chuỗi Java, không phân tích ngữ nghĩa câu lệnh cơ sở dữ liệu.

## 2. Cú pháp và các format specifier thường dùng

Cách gọi:

~~~java
String result = "Mẫu %s có %d mục".formatted("A", 3);
~~~

Tương đương về ý nghĩa với:

~~~java
String result = String.format("Mẫu %s có %d mục", "A", 3);
~~~

`String.formatted(...)` được bổ sung từ Java 15. Nó sử dụng cơ chế định dạng của `Formatter`.

| Ký hiệu | Kiểu dữ liệu/ý nghĩa | Ví dụ |
|---|---|---|
| `%s` | Biểu diễn chuỗi thông qua `toString()` | `"Java".formatted()` không có đối số thì lỗi; dùng `"Xin chào %s".formatted("Java")` |
| `%d` | Số nguyên thập phân | `"ID=%d".formatted(25)` |
| `%f` | Số thực dạng thập phân | `"Giá=%.2f".formatted(12.5)` |
| `%b` | Giá trị boolean | `"active=%b".formatted(true)` |
| `%c` | Ký tự | `"Ký tự=%c".formatted('A')` |
| `%n` | Ký tự xuống dòng theo nền tảng | Thường không cần dùng trong SQL text block |
| `%%` | Dấu phần trăm literal | `"Hoàn thành %d%%".formatted(80)` cho ra `80%` |

Ví dụ:

~~~java
String report = """
        Mã: %d
        Tên: %s
        Điểm: %.2f
        Hoàn thành: %d%%
        """.formatted(1024, "Java", 8.756, 80);

System.out.println(report);
~~~

Kết quả có nội dung:

~~~text
Mã: 1024
Tên: Java
Điểm: 8.76
Hoàn thành: 80%
~~~

### 2.1. Chỉ số đối số và thứ tự

Thông thường, các specifier lấy đối số theo thứ tự xuất hiện:

~~~java
String text = "%s có mã %d".formatted("An", 12);
~~~

Có thể chỉ định vị trí đối số:

~~~java
String text = "%2$d - %1$s".formatted("An", 12);
~~~

Kết quả:

~~~text
12 - An
~~~

Điều này hữu ích khi cần sắp xếp lại vị trí hiển thị. Với câu SQL, hãy hạn chế mẫu định dạng phức tạp để người đọc có thể xác định rõ thành phần nào được chèn vào câu lệnh.

### 2.2. Định dạng độ rộng và độ chính xác

Một số ví dụ:

~~~java
String a = "%08d".formatted(42);       // 00000042
String b = "%.2f".formatted(3.14159);  // 3.14
String c = "%-10s".formatted("Java");  // Java được căn trái
~~~

Các cờ, độ rộng và precision phục vụ **định dạng hiển thị**. Chúng không kiểm tra tính hợp lệ của dữ liệu nghiệp vụ hoặc kiểu cột SQL.

Ví dụ `%.2f` làm tròn cách biểu diễn số thực theo quy tắc định dạng; nó không phải cách chuẩn để chuyển một giá trị tiền tệ thành literal SQL.

### 2.3. Lỗi định dạng xảy ra khi chạy

Nếu format specifier không khớp với đối số, `formatted()` có thể ném ngoại lệ thuộc họ `IllegalFormatException`.

~~~java
// Lỗi: %d yêu cầu kiểu số nguyên phù hợp, nhưng đối số là String.
String sql = "WHERE id = %d".formatted("ABC");
~~~

Một số lỗi thường gặp:

- Thiếu đối số cho một specifier, ví dụ `"ID=%d".formatted()`.
- Dùng kiểu đối số không phù hợp, ví dụ `%d` với chuỗi.
- Viết sai cú pháp specifier.
- Quên nhân đôi dấu phần trăm literal thành `%%` khi chuỗi được xử lý bởi Formatter.

Các lỗi này là lỗi **định dạng chuỗi Java**, không phải lỗi cú pháp SQL.

## 3. Dùng text block với `formatted()` để tạo mẫu SQL

Về mặt cú pháp, có thể viết:

~~~java
String template = """
        SELECT id, name
        FROM users
        WHERE status = '%s'
        """;

String sql = template.formatted("ACTIVE");
~~~

Kết quả là một chuỗi SQL đã thay `%s` bằng `ACTIVE`.

Nhưng ví dụ trên chỉ minh họa thao tác thay chuỗi. **Không dùng cách này để đưa dữ liệu runtime vào SQL thực thi**, kể cả khi đã đặt giá trị bên trong dấu nháy đơn. `formatted()` không escape dấu nháy, dấu gạch chéo hoặc cú pháp đặc biệt của SQL.

### 3.1. `%s` không tự thêm dấu nháy SQL

Đoạn:

~~~java
String query = "WHERE name = %s".formatted("An");
~~~

tạo ra:

~~~sql
WHERE name = An
~~~

Nếu viết:

~~~java
String query = "WHERE name = '%s'".formatted("An");
~~~

thì kết quả là:

~~~sql
WHERE name = 'An'
~~~

Dấu nháy đơn có mặt vì **người viết template đã tự gõ**, không phải vì `%s` hiểu chuỗi SQL.

Vấn đề là dữ liệu đầu vào có thể chứa ký tự làm thay đổi cấu trúc truy vấn. Ví dụ tên `O'Brien` sẽ làm literal SQL bị đóng sớm nếu chèn thẳng vào chuỗi. Dữ liệu có chủ ý xấu còn có thể thay đổi điều kiện hoặc cấu trúc câu lệnh.

**Không giải quyết vấn đề này bằng cách tự thay dấu nháy hoặc nối thêm dấu nháy.** Quy tắc escape phụ thuộc loại literal và hệ quản trị cơ sở dữ liệu; tự xử lý rất dễ bỏ sót trường hợp.

### 3.2. `%d` và `%f` cũng không phải parameter binding

Có thể nghĩ rằng chèn số bằng `%d` an toàn hơn vì không có dấu nháy:

~~~java
// Không nên dùng để truyền giá trị runtime vào SQL.
String sql = "SELECT * FROM orders WHERE id = %d".formatted(orderId);
~~~

Ngay cả khi `orderId` là số nguyên, cách làm này vẫn trộn dữ liệu với cấu trúc SQL, tạo chuỗi mới cho mỗi giá trị và bỏ qua cơ chế bind kiểu của JDBC. Nó cũng không thay thế được cách xử lý tham số của driver.

Với `double` hoặc `float`, định dạng còn có thể phụ thuộc locale mặc định, chẳng hạn dấu thập phân có thể khác nhau giữa môi trường. SQL cần giá trị theo quy tắc của DB/driver, không phải chuỗi số dành cho hiển thị.

Hãy dùng `PreparedStatement` cho **mọi giá trị runtime**, bất kể giá trị đó là chuỗi, số, ngày tháng hay boolean.

## 4. Cách đúng: text block cho cấu trúc, PreparedStatement cho giá trị

Đây là mẫu nên dùng trong ứng dụng Java 17:

~~~java
String sql = """
        SELECT id, name, email
        FROM users
        WHERE email = ?
          AND status = ?
        """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, email);
    statement.setString(2, status);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            long id = resultSet.getLong("id");
            String name = resultSet.getString("name");

            System.out.println(id + ": " + name);
        }
    }
}
~~~

Giải thích:

1. Text block giữ câu SQL nhiều dòng, dễ đọc và dễ bảo trì.
2. Dấu `?` là **parameter marker** của JDBC, đại diện cho một giá trị.
3. `setString(1, email)` truyền giá trị cho dấu hỏi thứ nhất.
4. `setString(2, status)` truyền giá trị cho dấu hỏi thứ hai.
5. Driver nhận câu SQL và các giá trị tham số riêng biệt, sau đó xử lý theo giao thức và kiểu dữ liệu tương ứng.

Giá trị như `O'Brien` được truyền như dữ liệu, không thể tự đóng literal để thay đổi cú pháp câu SQL.

**Thứ tự tham số bắt đầu từ 1**, không phải 0. Nếu đổi thứ tự dấu `?` trong SQL, phải cập nhật các chỉ số `setXxx` tương ứng.

### 4.1. Một tham số có thể được dùng ở nhiều vị trí

Mỗi dấu `?` là một vị trí riêng. Nếu cùng một giá trị cần xuất hiện hai lần, thường phải bind hai lần:

~~~java
String sql = """
        SELECT id, name
        FROM users
        WHERE created_by = ?
           OR updated_by = ?
        """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, username);
    statement.setString(2, username);

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getString("name"));
        }
    }
}
~~~

JDBC không dùng cú pháp placeholder có tên kiểu `:username` trong `PreparedStatement` chuẩn. Dấu hỏi được đánh số theo thứ tự xuất hiện. Một số thư viện bổ sung named parameter, nhưng đó là chức năng của thư viện chứ không phải cú pháp chuẩn của `String.formatted()`.

### 4.2. Giá trị null và kiểu dữ liệu

Khi bind dữ liệu, hãy dùng setter phù hợp:

| Kiểu Java / dữ liệu | Setter JDBC thường dùng |
|---|---|
| `String` | `setString(index, value)` |
| `int` | `setInt(index, value)` |
| `long` | `setLong(index, value)` |
| `BigDecimal` | `setBigDecimal(index, value)` |
| `LocalDate` | `setObject(index, value)` (tùy driver/JDBC) |
| Boolean | `setBoolean(index, value)` |

Với null và kiểu SQL cụ thể, có thể dùng `setNull(index, Types.VARCHAR)`, `setNull(index, Types.INTEGER)`, v.v. Việc chọn SQL type phù hợp giúp driver xử lý null chính xác.

Không nên biến null thành chuỗi literal `"null"` qua `formatted("%s")`; giá trị đó khác SQL `NULL`.

## 5. Giới hạn quan trọng: dấu ? chỉ bind giá trị, không bind tên bảng/cột

Một lỗi thiết kế phổ biến là nghĩ có thể dùng placeholder cho mọi thành phần:

~~~java
// Không hoạt động theo ý định: ? không đại diện tên bảng hoặc tên cột.
String sql = """
        SELECT *
        FROM ?
        ORDER BY ?
        """;
~~~

Trong JDBC, dấu `?` biểu diễn **giá trị dữ liệu**, không phải identifier hay từ khóa SQL. Driver không thay dấu hỏi đầu tiên bằng tên bảng và dấu hỏi thứ hai bằng tên cột theo cách đó.

Các thành phần thường không thể bind bằng parameter marker:

- Tên database, schema, bảng và cột.
- Từ khóa `ASC` hoặc `DESC`.
- Toán tử, tên hàm hoặc đoạn cú pháp SQL.
- Một danh sách nhiều phần tử như `1, 2, 3` chỉ bằng một tham số.

### 5.1. Với identifier động, dùng allowlist

Nếu ứng dụng cho phép người dùng chọn cột sắp xếp, ánh xạ lựa chọn đó sang các tên cột **do chương trình kiểm soát**:

~~~java
enum UserSort {
    NAME,
    CREATED_AT
}

String orderColumn = switch (sort) {
    case NAME -> "name";
    case CREATED_AT -> "created_at";
};

String orderDirection = descending ? "DESC" : "ASC";

String sql = """
        SELECT id, name, created_at
        FROM users
        WHERE status = ?
        ORDER BY %s %s
        """.formatted(orderColumn, orderDirection);

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, status);

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong("id"));
        }
    }
}
~~~

Trong ví dụ:

- `sort` là enum nên chỉ có lựa chọn đã định nghĩa.
- `orderColumn` chỉ có thể là `name` hoặc `created_at`.
- `orderDirection` chỉ có thể là `ASC` hoặc `DESC`.
- `status` vẫn được bind bằng dấu `?`.

Đây là trường hợp phù hợp để dùng `formatted()`: chèn **cấu trúc SQL đã được kiểm soát**, không chèn dữ liệu tùy ý. Trong hệ thống thực tế, identifier có thể cần quy tắc quote riêng của database; allowlist vẫn là bước kiểm soát đầu tiên.

**Không** viết:

~~~java
// NGUY HIỂM: không đưa input trực tiếp vào identifier.
String sql = """
        SELECT id, name
        FROM users
        ORDER BY %s
        """.formatted(userProvidedColumn);
~~~

Kể cả khi người dùng chỉ định tên cột, hãy chuyển nó qua enum hoặc map allowlist trước khi tạo câu SQL.

### 5.2. Dùng `formatted()` để tạo số lượng placeholder, không chèn giá trị

Một trường hợp hữu ích là câu lệnh `IN (...)` có số lượng phần tử thay đổi. Ta có thể tạo **số lượng dấu hỏi** theo kích thước danh sách rồi bind từng giá trị:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Collections;
import java.util.List;

static void findUsersByIds(Connection connection, List<Long> ids)
        throws SQLException {

    if (ids == null || ids.isEmpty()) {
        // IN () thường không hợp lệ; quyết định nghiệp vụ ở đây là không có kết quả.
        return;
    }

    String placeholders = String.join(
            ", ",
            Collections.nCopies(ids.size(), "?")
    );

    String sql = """
            SELECT id, name
            FROM users
            WHERE id IN (%s)
            """.formatted(placeholders);

    try (PreparedStatement statement = connection.prepareStatement(sql)) {
        for (int i = 0; i < ids.size(); i++) {
            statement.setLong(i + 1, ids.get(i));
        }

        try (ResultSet rs = statement.executeQuery()) {
            while (rs.next()) {
                System.out.println(
                        rs.getLong("id") + ": " + rs.getString("name")
                );
            }
        }
    }
}
~~~

Ví dụ nếu danh sách có ba ID, chuỗi placeholder được tạo thành:

~~~sql
WHERE id IN (?, ?, ?)
~~~

Giá trị thật được bind lần lượt bằng `setLong(1, ...)`, `setLong(2, ...)`, `setLong(3, ...)`.

Ở đây `formatted()` chỉ nhận chuỗi placeholder do chương trình tự sinh từ **số lượng phần tử**. Nó không nhận nội dung ID. Đây là một cách kết hợp text block, `formatted()` và `PreparedStatement` có thể kiểm soát được.

Cần xác định rõ hành vi khi danh sách rỗng: trả về không có kết quả, bỏ điều kiện, hoặc dùng một biểu thức luôn sai tùy yêu cầu. Không nên tạo `IN ()` rồi trông chờ mọi database xử lý giống nhau.

## 6. Dấu phần trăm trong SQL và `formatted()`

`Formatter` xem ký tự `%` là phần mở đầu của format specifier. Vì vậy, khi một text block được gọi `.formatted(...)`, dấu phần trăm literal phải viết thành `%%`.

Ví dụ thuần định dạng:

~~~java
String template = "WHERE score >= %d%%";
String result = template.formatted(80);
~~~

Kết quả:

~~~sql
WHERE score >= 80%
~~~

Trong SQL, ký tự `%` cũng có thể là wildcard của `LIKE`. Nếu **thực sự** gọi `formatted()` trên một template có wildcard literal, bạn phải viết `%%` để Formatter tạo ra một dấu `%`:

~~~java
String displayOnly = """
        SELECT id
        FROM users
        WHERE name LIKE '%%'
        """.formatted();
~~~

Sau khi định dạng, chuỗi chứa:

~~~sql
WHERE name LIKE '%'
~~~

Ví dụ trên chỉ minh họa quy tắc Formatter. Khi truy vấn thực tế, nên viết:

~~~java
String sql = """
        SELECT id
        FROM users
        WHERE name LIKE ?
        """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, "%" + searchTerm + "%");

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getString("id"));
        }
    }
}
~~~

Trong câu SQL dùng `PreparedStatement` này, không gọi `.formatted()`, nên wildcard SQL chỉ viết một dấu `%` bình thường. Giá trị pattern được bind như một tham số.

## 7. Text block có tự loại bỏ khoảng trắng không?

Text block có quy tắc xử lý **incidental indentation**: Java xác định phần thụt lề không mang ý nghĩa rồi loại bỏ phần chung theo vị trí của các dòng nội dung và dấu đóng. Nó không tự hiểu hay định dạng lại SQL.

Ví dụ:

~~~java
String sql = """
        SELECT id, name
        FROM users
        WHERE active = true
        """;
~~~

Cách thụt lề trong mã nguồn chủ yếu để người đọc dễ nhìn. Chuỗi kết quả vẫn có các dòng và ký tự xuống dòng theo quy tắc text block.

Một số điểm cần nhớ:

- Dấu đóng `"""` có vị trí ảnh hưởng đến lượng thụt lề bị loại bỏ.
- Dòng trống và khoảng trắng có thể ảnh hưởng nội dung kết quả.
- Dấu xuống dòng cuối thường được giữ nếu dấu đóng nằm trên dòng riêng như ví dụ.
- Text block vẫn xử lý escape sequence như chuỗi Java thông thường.
- Text block không tự loại bỏ khoảng trắng bên trong literal SQL, không tự sửa tên cột và không kiểm tra cú pháp SQL.

Nếu cần xem chuỗi SQL thực tế được tạo ra, có thể in ra trong môi trường phát triển hoặc dùng logger phù hợp. Khi ghi log truy vấn có tham số, tránh ghi dữ liệu nhạy cảm như mật khẩu, token hoặc thông tin cá nhân.

### 7.1. Escape sequence đặc biệt trong text block

Hai escape đáng biết:

| Escape | Ý nghĩa |
|---|---|
| `\s` | Tạo một dấu cách, hữu ích khi cần giữ dấu cách ở cuối dòng |
| `\` trước ký tự xuống dòng | Nối dòng nguồn, không đưa ký tự xuống dòng đó vào chuỗi kết quả |

Ví dụ:

~~~java
String text = """
        SELECT id, \
        name
        FROM users
        """;
~~~

Phần `SELECT id, \` được nối thành cùng một dòng trong chuỗi kết quả. Tuy nhiên, với SQL nhiều dòng, thường nên giữ xuống dòng để dễ đọc thay vì dùng nối dòng không cần thiết.

## 8. Những giới hạn của `formatted()` khi tạo SQL

Có thể dùng bảng sau để xác định việc gì nên và không nên làm:

| Nhu cầu | Dùng `formatted()`? | Cách phù hợp |
|---|---|---|
| Viết SQL nhiều dòng dễ đọc | Không cần cho riêng việc này | Text block |
| Chèn giá trị String do người dùng nhập vào `WHERE` | **Không** | `PreparedStatement` + `setString` |
| Chèn ID, số lượng, ngày tháng runtime | **Không** | Parameter marker + setter phù hợp |
| Chèn tên cột hoặc bảng do người dùng gửi | **Không trực tiếp** | Allowlist/enum rồi mới dựng cấu trúc |
| Chèn `ASC`/`DESC` theo lựa chọn | Chỉ sau khi ánh xạ sang tập hằng hợp lệ | Allowlist/enum |
| Tạo số lượng dấu `?` cho danh sách `IN` | Có thể | Sinh placeholder theo số phần tử, bind từng giá trị |
| Tạo DDL hoặc SQL migration từ metadata tin cậy | Có thể, có kiểm soát | Kiểm tra identifier và dialect |
| Tạo thông báo hoặc SQL preview phục vụ debug | Có thể | Không thực thi chuỗi đó như cách bind dữ liệu |

Các giới hạn quan trọng:

1. **Không bind tham số:** phương thức chỉ thay nội dung chuỗi trước khi gửi SQL đi.
2. **Không escape SQL:** `%s` không xử lý dấu nháy, comment, dấu chấm phẩy hay ký tự đặc biệt.
3. **Không kiểm tra cú pháp SQL:** chuỗi được tạo có thể sai cú pháp hoặc sai dialect.
4. **Không kiểm tra kiểu cột:** `%d` và `%f` chỉ định dạng Java value, không thay thế kiểm tra kiểu dữ liệu của database.
5. **Có thể phụ thuộc locale:** các định dạng số như `%f` có thể dùng quy tắc locale mặc định.
6. **Dấu `%` có ý nghĩa riêng với Formatter:** cần viết `%%` cho dấu phần trăm literal nếu gọi `formatted()`.
7. **Không thay thế query builder hoặc ORM:** khi câu truy vấn phức tạp, thư viện chuyên dụng có thể quản lý cấu trúc, dialect và tham số tốt hơn.

### 8.1. Tại sao không tự escape rồi dùng `formatted()`?

Một cách làm thường gặp là thay dấu nháy đơn trong dữ liệu trước khi chèn vào chuỗi. Đây không phải giải pháp tổng quát:

- Quy tắc escape literal phụ thuộc database và kiểu dữ liệu.
- Encoding, Unicode, ký tự điều khiển và các kiểu literal đặc biệt có thể phát sinh trường hợp khó xử lý.
- Dữ liệu vẫn bị ghép vào câu SQL, khiến trách nhiệm an toàn nằm ở code ứng dụng.
- Những thay đổi dialect hoặc driver có thể làm giả định cũ không còn đúng.

Hãy để JDBC driver xử lý việc bind giá trị. `PreparedStatement` là API được thiết kế cho mục đích này.

## 9. Một ví dụ hoàn chỉnh: lọc dữ liệu và sắp xếp an toàn

Ví dụ sau kết hợp cả hai cách:

- Text block tạo phần SQL nhiều dòng.
- `formatted()` chèn tên cột và chiều sắp xếp được ánh xạ từ enum.
- `PreparedStatement` bind các giá trị tìm kiếm.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

enum UserSort {
    NAME,
    CREATED_AT
}

public class UserRepositoryExample {

    public void search(
            Connection connection,
            String status,
            String searchTerm,
            UserSort sort,
            boolean descending
    ) throws SQLException {

        String orderColumn = switch (sort) {
            case NAME -> "name";
            case CREATED_AT -> "created_at";
        };

        String orderDirection = descending ? "DESC" : "ASC";

        String sql = """
                SELECT id, name, email, created_at
                FROM users
                WHERE status = ?
                  AND name LIKE ?
                ORDER BY %s %s
                """.formatted(orderColumn, orderDirection);

        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setString(1, status);
            statement.setString(2, "%" + searchTerm + "%");

            try (ResultSet rs = statement.executeQuery()) {
                while (rs.next()) {
                    System.out.printf(
                            "%d | %s | %s%n",
                            rs.getLong("id"),
                            rs.getString("name"),
                            rs.getString("email")
                    );
                }
            }
        }
    }
}
~~~

Những gì được đưa vào `formatted()` đều là lựa chọn cố định trong chương trình. Những gì đến từ người gọi (`status`, `searchTerm`) đều được bind bằng tham số.

Trong ứng dụng thực tế, cần kiểm tra `sort` không null hoặc quy định giá trị mặc định phù hợp. Nếu nhận lựa chọn sắp xếp dưới dạng chuỗi từ request, hãy parse sang enum và từ chối giá trị không nằm trong allowlist.

## 10. Kiểm tra nhanh khi làm việc với SQL template

Khi viết một text block có `.formatted()`, hãy tự hỏi:

1. Mỗi ký hiệu `%...` là specifier hay dấu phần trăm literal?
2. Đối số có đúng kiểu mà specifier yêu cầu không?
3. Giá trị chèn vào là **dữ liệu runtime** hay **một mảnh cú pháp được chương trình kiểm soát**?
4. Nếu là dữ liệu runtime, tại sao chưa dùng `PreparedStatement`?
5. Nếu là tên bảng/cột hoặc từ khóa, giá trị đó đã đi qua allowlist chưa?
6. SQL có được kiểm tra trên đúng hệ quản trị và dialect mục tiêu không?
7. Nếu dùng số thực hoặc ngày tháng, có đang nhầm định dạng hiển thị Java với cách biểu diễn dữ liệu SQL không?

Một nguyên tắc dễ nhớ:

~~~text
Text block       -> viết câu SQL nhiều dòng
formatted()      -> thay format specifier trong String
PreparedStatement -> bind giá trị runtime
Allowlist        -> kiểm soát identifier / SQL keyword động
Database driver  -> xử lý tham số theo kiểu dữ liệu
~~~

## 11. Bài tập thực hành

### Bài 1: Đọc kết quả của `formatted()`

Cho:

~~~java
String template = """
        SELECT id
        FROM users
        WHERE status = '%s'
          AND age >= %d
        """;

String result = template.formatted("ACTIVE", 18);
~~~

**Câu hỏi:** `result` chứa nội dung gì? Có nên dùng cách này cho giá trị nhận từ HTTP request không?

**Gợi ý:** Chuỗi nhận được có literal `'ACTIVE'` và `18` trong SQL. Không nên dùng cho dữ liệu request vì `formatted()` không bind hoặc escape SQL. Hãy đổi hai chỗ đó thành `?` và bind qua `PreparedStatement`.

### Bài 2: Sửa truy vấn an toàn

Mã ban đầu:

~~~java
String sql = """
        SELECT id, name
        FROM users
        WHERE email = '%s'
        """.formatted(email);
~~~

**Yêu cầu:** Viết lại bằng JDBC.

**Đáp án tham khảo:**

~~~java
String sql = """
        SELECT id, name
        FROM users
        WHERE email = ?
        """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, email);

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getString("name"));
        }
    }
}
~~~

### Bài 3: Sắp xếp theo lựa chọn người dùng

Yêu cầu hỗ trợ sắp xếp theo tên hoặc thời điểm tạo, tăng dần hoặc giảm dần.

**Câu hỏi:** Vì sao không thể dùng `ORDER BY ? ?` và bind tên cột/chiều sắp xếp?

**Gợi ý:** Dấu hỏi JDBC đại diện cho giá trị dữ liệu, không đại diện identifier hoặc từ khóa. Hãy ánh xạ enum sang các chuỗi cố định `name`/`created_at` và `ASC`/`DESC`, rồi dùng `formatted()` cho phần cấu trúc đã kiểm soát.

### Bài 4: Tạo danh sách placeholder

Cho danh sách có bốn ID. Hãy tạo phần `?, ?, ?, ?` bằng Java, sau đó bind bốn giá trị vào `PreparedStatement`.

**Đáp án tham khảo:**

~~~java
List<Long> ids = List.of(10L, 20L, 30L, 40L);

String placeholders = String.join(
        ", ",
        Collections.nCopies(ids.size(), "?")
);

String sql = """
        SELECT id
        FROM users
        WHERE id IN (%s)
        """.formatted(placeholders);

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    for (int i = 0; i < ids.size(); i++) {
        statement.setLong(i + 1, ids.get(i));
    }

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong("id"));
        }
    }
}
~~~

Nhớ xử lý danh sách rỗng trước khi tạo truy vấn.

### Bài 5: Phần trăm trong format string

Cho:

~~~java
String template = "WHERE discount >= %d%%";
String sql = template.formatted(20);
~~~

**Câu hỏi:** Vì sao cần viết `%%`? Kết quả là gì?

**Đáp án:** Formatter dùng `%` để bắt đầu format specifier. Muốn kết quả có một dấu phần trăm literal, phải viết `%%`. Kết quả là `WHERE discount >= 20%`.

### Bài 6: Chọn công cụ

Ghép nhu cầu với giải pháp:

| Nhu cầu | Giải pháp |
|---|---|
| Viết câu SQL nhiều dòng | Text block |
| Hiển thị một báo cáo có số và chuỗi | `formatted()` |
| Tìm user theo email đầu vào | `PreparedStatement` |
| Chọn cột sắp xếp trong tập lựa chọn cho phép | Enum/allowlist rồi tạo SQL structure |
| Bind danh sách giá trị có kích thước thay đổi | Tạo placeholder, bind từng giá trị |

## 12. Tài liệu tham khảo

- [Oracle Java SE 17 — Text Blocks](https://docs.oracle.com/en/java/javase/17/text-blocks/index.html): cú pháp text block, incidental indentation và escape sequence.
- [Oracle Java SE 17 — String API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#formatted(java.lang.Object...)): phương thức `String.formatted(Object... args)`.
- [Oracle Java SE 17 — Formatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Formatter.html): format specifier, conversion, flags, width, precision và locale.
- [Oracle Java SE 17 — PreparedStatement](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html): API bind tham số của JDBC.
- [Oracle Java SE 17 — JDBC Basics: Prepared Statements](https://docs.oracle.com/javase/tutorial/jdbc/basics/prepared.html): cách dùng prepared statement trong JDBC.
- [OWASP — SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html): nguyên tắc parameterized query và allowlist cho thành phần SQL động.

