# Đọc ghi chuỗi Unicode và kiểu văn bản quốc gia trong JDBC

Ứng dụng Java thường phải lưu họ tên có dấu tiếng Việt, nội dung nhiều ngôn ngữ, biểu tượng cảm xúc hoặc tài liệu dài vào cơ sở dữ liệu quan hệ. Khi làm việc với **JDBC**, việc truyền một `String` không tự bảo đảm mọi ký tự sẽ được lưu và đọc lại chính xác: kiểu cột SQL, bộ mã cơ sở dữ liệu, JDBC driver và phương thức gán/đọc tham số đều có vai trò.

Trong chủ đề **Số và văn bản**, bài này giải thích cách dùng các API JDBC chuẩn cho Unicode, phân biệt văn bản thông thường với **kiểu ký tự quốc gia** (*national character types*), thao tác với `NCHAR`, `NVARCHAR`, `LONGNVARCHAR`, `NCLOB`, và kiểm tra dữ liệu sau khi ghi. Các ví dụ kết hợp `DataSource`, `Connection`, `PreparedStatement`, `ResultSet` và SQL tham số hóa để áp dụng trực tiếp vào CRUD.

## 1. Unicode trong Java và cơ sở dữ liệu là hai lớp khác nhau

`String` trong Java biểu diễn văn bản dưới dạng các đơn vị mã UTF-16. Một chuỗi có thể chứa ký tự Latin, tiếng Việt, chữ Nhật, chữ Ả Rập, emoji và các hệ chữ viết khác:

```java
String text = "Tiếng Việt: Hà Nội | 日本語 | العربية | 🌏";
```

Tuy nhiên, từ `String` đến bản ghi trong cơ sở dữ liệu vẫn có các bước chuyển đổi:

```text
Java String (UTF-16)
        │
        ▼
PreparedStatement.setString() / setNString()
        │
        ▼
JDBC driver và giao thức kết nối
        │
        ▼
Kiểu cột + bộ mã + quy tắc đối chiếu của cơ sở dữ liệu
        │
        ▼
ResultSet.getString() / getNString()
        │
        ▼
Java String
```

Phân biệt ba khái niệm:

- **Unicode:** tập ký tự và mã điểm phục vụ trao đổi văn bản đa ngôn ngữ. UTF-8 và UTF-16 là những cách mã hóa Unicode; không phải hai bảng chữ cái khác nhau.
- **Kiểu cột văn bản:** ví dụ `VARCHAR`, `NVARCHAR` hoặc `NCLOB`. Kiểu được hỗ trợ và cách lưu Unicode tùy hệ quản trị.
- **Collation / quy tắc so sánh:** ảnh hưởng phép so sánh, sắp xếp, phân biệt dấu hoặc chữ hoa/thường; không đồng nghĩa với khả năng lưu đầy đủ ký tự Unicode.

Vì vậy, ký tự hiển thị đúng trong bộ nhớ Java vẫn có thể bị mất dấu hoặc chuyển thành `?` nếu đi qua cột, kết nối hoặc phép chuyển kiểu không tương thích.

## 2. Văn bản thông thường và văn bản quốc gia

JDBC phân biệt các kiểu SQL ký tự thông thường với kiểu ký tự quốc gia thông qua những hằng số trong `java.sql.Types` và phương thức `setN...` / `getN...`.

| Họ kiểu SQL/JDBC | Hằng số JDBC | Cách đọc, ghi thường dùng | Phù hợp với |
| --- | --- | --- | --- |
| `CHAR`, `VARCHAR`, `LONGVARCHAR` | `Types.CHAR`, `VARCHAR`, `LONGVARCHAR` | `setString()`, `getString()`, `setCharacterStream()`, `getCharacterStream()` | Cột ký tự thông thường; **vẫn có thể lưu Unicode** nếu hệ quản trị và cấu hình hỗ trợ. |
| `NCHAR` | `Types.NCHAR` | `setNString()`, `getNString()` | Ký tự quốc gia có độ dài cố định; cách đệm khoảng trắng tùy hệ quản trị. |
| `NVARCHAR` | `Types.NVARCHAR` | `setNString()`, `getNString()` | Văn bản quốc gia có độ dài biến thiên. |
| `LONGNVARCHAR` | `Types.LONGNVARCHAR` | `setNCharacterStream()`, `getNCharacterStream()` | Văn bản quốc gia dài theo kiểu JDBC; sự hỗ trợ khác nhau giữa các driver. |
| `NCLOB` | `Types.NCLOB` | `setNClob()`, `getNClob()` | Đối tượng văn bản quốc gia rất lớn. |

Chữ `N` thường gắn với *national character*, nhưng **không thể kết luận rằng chỉ cột có tiền tố `N` mới lưu được Unicode**. Chẳng hạn, ở hệ quản trị sử dụng UTF-8 cho cột văn bản thông thường, `VARCHAR` hoặc `TEXT` cũng có thể lưu đầy đủ tiếng Việt và emoji. Ngược lại, một số hệ quản trị phân biệt rõ kiểu `VARCHAR` và `NVARCHAR` về cách mã hóa, truyền tham số hoặc tập ký tự.

Ví dụ về cách ánh xạ trong các hệ quản trị:

| Hệ quản trị | Điều cần chú ý |
| --- | --- |
| SQL Server | Có `NCHAR`, `NVARCHAR`; kiểu `NVARCHAR(MAX)` thường được dùng cho văn bản dài. Việc truyền chuỗi qua driver và cách chuyển đổi `VARCHAR`/`NVARCHAR` cần được kiểm tra. |
| Oracle Database | Có `NCHAR`, `NVARCHAR2`, `NCLOB`, và khái niệm *national character set* riêng. |
| PostgreSQL | Các kiểu `text`/`varchar` dùng mã hóa của cơ sở dữ liệu, thường là UTF-8. Không nên giả định driver có ánh xạ `NCLOB`/`NVARCHAR` giống Oracle. |
| MySQL | `utf8mb4` là bộ mã Unicode thường dùng cho các cột văn bản; `NATIONAL VARCHAR` và hành vi các API `setN...` tùy phiên bản, driver và cấu hình. |

Do khác biệt về DDL và cách ánh xạ kiểu, **không có một câu `CREATE TABLE` với mọi kiểu quốc gia chạy nguyên vẹn trên tất cả hệ quản trị**. Chọn kiểu cột dựa trên hệ quản trị đang triển khai, rồi xác minh API JDBC hỗ trợ kiểu đó.

## 3. Ghi chuỗi Unicode ngắn bằng `setNString()`

Giả sử ứng dụng có bảng `user_profiles` với hai cột `id` và `display_name`. Ở cơ sở dữ liệu hỗ trợ `NVARCHAR`, định nghĩa minh họa là:

```sql
CREATE TABLE user_profiles (
    id BIGINT PRIMARY KEY,
    display_name NVARCHAR(150) NOT NULL
);
```

> Cú pháp `NVARCHAR` ở đây mang tính minh họa. Với cơ sở dữ liệu dùng tên kiểu khác, hãy chuyển DDL sang kiểu văn bản Unicode tương ứng và kiểm tra khả năng hỗ trợ `setNString()` của driver.

Ví dụ Java dùng `DataSource` lấy kết nối và tham số `?` để ghi tên hiển thị:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class UserProfileRepository {
    private final DataSource dataSource;

    public UserProfileRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void insert(long id, String displayName) throws SQLException {
        String sql = "INSERT INTO user_profiles (id, display_name) VALUES (?, ?)";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {

            statement.setLong(1, id);
            statement.setNString(2, displayName);

            int affectedRows = statement.executeUpdate();
            if (affectedRows != 1) {
                throw new SQLException("Expected one inserted profile, got "
                        + affectedRows);
            }
        }
    }

    public String findDisplayName(long id) throws SQLException {
        String sql = "SELECT display_name FROM user_profiles WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {

            statement.setLong(1, id);

            try (ResultSet result = statement.executeQuery()) {
                if (!result.next()) {
                    return null; // Không tồn tại hồ sơ; cột display_name là NOT NULL.
                }
                return result.getNString("display_name");
            }
        }
    }
}
```

Sử dụng repository:

```java
String original = "Nguyễn Ánh 🌸 — 日本語";
repository.insert(1001L, original);

String loaded = repository.findDisplayName(1001L);
System.out.println(original.equals(loaded)); // Kỳ vọng true nếu dữ liệu được giữ nguyên.
```

Ý nghĩa các API:

- `setNString(parameterIndex, value)` gán một giá trị `String` cho tham số được xử lý như **chuỗi ký tự quốc gia**. Chỉ số tham số bắt đầu từ `1`.
- `getNString(columnLabel)` nhận chuỗi quốc gia từ cột kết quả. Có thể dùng vị trí cột, ví dụ `getNString(1)`.
- `executeUpdate()` trả **số hàng bị ảnh hưởng**, không trả giá trị chuỗi đã lưu; cần `SELECT` lại để kiểm chứng round-trip.
- `getNString(...)` trả `null` khi giá trị SQL là `NULL`; ví dụ khai báo `NOT NULL` để `null` của `findDisplayName` biểu thị không tìm thấy hàng.
- `try-with-resources` đóng `ResultSet`, `PreparedStatement` và `Connection`, kể cả khi câu lệnh gặp lỗi. Khi dùng connection pool, việc đóng kết nối thường trả nó về pool.

Các dữ liệu từ người dùng luôn nên truyền bằng placeholder `?` và phương thức setter. Nối nội dung văn bản trực tiếp vào chuỗi SQL có thể tạo lỗi dấu nháy, lỗi chuyển mã và nguy cơ SQL injection.

## 4. Khi nào dùng `setString()` thay vì `setNString()`?

Hai cặp API không đồng nghĩa với hai chất lượng Unicode khác nhau:

```java
// Cột VARCHAR/TEXT có cấu hình và driver hỗ trợ Unicode:
statement.setString(1, "Chào bạn 🌏");

// Cột kiểu ký tự quốc gia có API tương ứng được driver hỗ trợ:
statement.setNString(1, "Chào bạn 🌏");
```

Lựa chọn dựa trên **kiểu SQL thực tế và tài liệu driver**, không dựa vào việc chuỗi có dấu tiếng Việt hay không.

Một số hệ quản trị lưu Unicode đầy đủ trong `VARCHAR` với UTF-8 và sử dụng `setString()`/`getString()` bình thường. Ở những hệ quản trị phân biệt kiểu ký tự quốc gia, `setNString()`/`getNString()` diễn đạt đúng ý định hơn khi cột là `NCHAR`/`NVARCHAR`. Tuy nhiên, driver có thể chuyển đổi kiểu ngầm hoặc không hỗ trợ một phương thức `setN...`; không nên tự động thay tất cả `setString()` thành `setNString()` trong dự án đang hoạt động.

Để đưa ra quyết định:

1. Xác nhận kiểu cột, bộ mã cơ sở dữ liệu và quy tắc collation đang dùng.
2. Kiểm tra tài liệu JDBC driver và phiên bản triển khai đối với các API `setN...`/`getN...`.
3. Ghi rồi đọc lại bộ dữ liệu kiểm thử gồm tiếng Việt có dấu, ký tự ngoài bảng BMP (ví dụ emoji) và một số ngôn ngữ khác.
4. Kiểm tra việc so sánh, tìm kiếm, sắp xếp và ràng buộc độ dài bằng chính cơ sở dữ liệu đích.

## 5. Văn bản rất dài: `NCLOB` và stream

Với đoạn mô tả ngắn, một `String` và `setNString()` thường đủ thuận tiện. Nếu cần lưu tài liệu lớn, JDBC có thể làm việc với kiểu `NCLOB` thông qua các API chuyên dụng:

- `PreparedStatement.setNClob(index, Reader)` hoặc `setNClob(index, Reader, length)` để cung cấp nội dung ký tự từ `Reader`.
- `ResultSet.getNClob(column)` để lấy đối tượng `java.sql.NClob`.
- `NClob.getCharacterStream()` để đọc dần nội dung bằng `Reader`.
- `NClob.free()` để giải phóng tài nguyên của đối tượng LOB sau khi sử dụng.

Ở hệ quản trị có cột `NCLOB`, một thao tác ghi minh họa có thể như sau. Đối số `Reader` giúp tầng gọi truyền luồng dữ liệu thay vì buộc DAO nhận toàn bộ văn bản dưới dạng `String`:

```java
import javax.sql.DataSource;
import java.io.Reader;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public void insertDocument(DataSource dataSource,
                           long id,
                           Reader contentReader) throws SQLException {
    String sql = "INSERT INTO documents (id, content) VALUES (?, ?)";

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql)) {

        statement.setLong(1, id);
        statement.setNClob(2, contentReader);

        if (statement.executeUpdate() != 1) {
            throw new SQLException("Cannot insert Unicode document");
        }
    }
}
```

Giả sử bảng `documents` có khóa `id` và cột `content` thuộc kiểu `NCLOB` thực sự được driver hỗ trợ. Tầng gọi chịu trách nhiệm mở/đóng `contentReader` và giữ luồng mở cho đến khi `executeUpdate()` hoàn tất. Ví dụ đọc một tệp Unicode với mã hóa được chỉ định rõ:

```java
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

try (Reader reader = Files.newBufferedReader(
        Path.of("document.txt"), StandardCharsets.UTF_8)) {
    insertDocument(dataSource, 5001L, reader);
}
```

Ở chiều đọc, lấy `NClob`, mở `Reader` và giải phóng đối tượng LOB sau khi xử lý:

```java
import javax.sql.DataSource;
import java.io.IOException;
import java.io.Reader;
import java.io.Writer;
import java.sql.Connection;
import java.sql.NClob;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public void copyDocument(DataSource dataSource, long id, Writer output)
        throws SQLException, IOException {

    String sql = "SELECT content FROM documents WHERE id = ?";

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql)) {

        statement.setLong(1, id);
        try (ResultSet result = statement.executeQuery()) {
            if (!result.next()) {
                return;
            }

            NClob content = result.getNClob("content");
            if (content == null) {
                return; // Giá trị SQL NULL.
            }

            try {
                try (Reader reader = content.getCharacterStream()) {
                    char[] buffer = new char[4096];
                    int count;
                    while ((count = reader.read(buffer)) != -1) {
                        output.write(buffer, 0, count);
                    }
                }
            } finally {
                content.free();
            }
        }
    }
}
```

Trong ví dụ, bên gọi quản lý vòng đời của `output` và cần `flush()` khi phù hợp; có thể truyền một `Writer` ghi tệp UTF-8 hoặc luồng phản hồi. Cách chuyển từng khối ký tự vào cùng một `Writer` cũng tránh tách ký tự UTF-16 nhiều đơn vị thành các chuỗi độc lập ở ranh giới buffer. Khi xử lý tài liệu lớn, nên ghi dần thay vì nối toàn bộ vào một `String`.

`NCLOB` không phải lựa chọn bắt buộc cho mọi văn bản dài. Một số hệ quản trị dùng `TEXT`, `CLOB` hay `NVARCHAR(MAX)` và driver tương ứng cung cấp các API khác. `setNClob()` cũng có thể báo `SQLFeatureNotSupportedException` khi driver không hỗ trợ. Hãy chọn cặp kiểu SQL/API thích hợp thay vì giả định `NCLOB` có sẵn ở mọi cơ sở dữ liệu.

### Trường hợp `setNCharacterStream()` và `getNCharacterStream()`

JDBC còn hỗ trợ truyền và nhận văn bản quốc gia dưới dạng luồng ký tự qua `setNCharacterStream()` và `getNCharacterStream()`, thường gắn với các kiểu `NCHAR`, `NVARCHAR`, `LONGNVARCHAR` theo khả năng của driver:

```java
// Ghi văn bản quốc gia từ một Reader đang mở:
statement.setNCharacterStream(1, reader);

// Sau khi executeQuery() và result.next() thành công:
try (Reader text = result.getNCharacterStream(1)) {
    if (text != null) {
        char[] chunk = new char[2048];
        int count;
        while ((count = text.read(chunk)) != -1) {
            output.write(chunk, 0, count); // output là Writer do bên gọi quản lý.
        }
    }
}
```

Trong mã sản phẩm, luôn giữ lại giá trị trả về từ `read(chunk)` để biết **có bao nhiêu ký tự hợp lệ** trong buffer ở từng lượt, thay vì xử lý toàn bộ buffer. Luồng từ `ResultSet` thường phụ thuộc vòng đời kết quả và kết nối; hãy tiêu thụ luồng trước khi đóng chúng. Các overload có tham số `length` yêu cầu cung cấp độ dài nội dung theo hợp đồng của API và driver; không tự lấy kích thước byte của tệp UTF-8 làm số ký tự.

## 6. Những vấn đề Unicode thường bị bỏ sót

### 6.1. `String.length()` không phải số ký tự nhìn thấy

Java sử dụng UTF-16 code unit. Với ký tự ngoài *Basic Multilingual Plane*, như nhiều emoji, một ký tự Unicode có thể chiếm hai đơn vị UTF-16:

```java
String value = "A🌏";

System.out.println(value.length());              // 3 đơn vị UTF-16
System.out.println(value.codePointCount(
        0, value.length()));                     // 2 Unicode code point
```

Các dấu kết hợp còn khiến số code point khác với số ký tự người dùng cảm nhận. Giới hạn `NVARCHAR(100)` không có cùng ý nghĩa về số byte, ký tự Unicode, đơn vị UTF-16 hoặc grapheme ở mọi hệ quản trị. Vì vậy, hãy kiểm tra cách hệ quản trị tính độ dài cột và kiểm thử các ký tự nhiều đơn vị mã.

### 6.2. Chuỗi trông giống nhau chưa chắc bằng nhau

Một chữ có dấu có thể biểu diễn bằng ký tự dựng sẵn hoặc ký tự cơ sở đi cùng dấu kết hợp:

```java
import java.text.Normalizer;

String composed = "é";
String decomposed = "e\u0301";

System.out.println(composed.equals(decomposed)); // false

String normalized = Normalizer.normalize(
        decomposed, Normalizer.Form.NFC);
System.out.println(composed.equals(normalized)); // true
```

Chuẩn hóa Unicode (`NFC`, `NFD`, v.v.) là **quyết định của nghiệp vụ**. Có thể cần chuẩn hóa thống nhất cho tìm kiếm, định danh hay kiểm thử, nhưng không nên âm thầm biến đổi dữ liệu nếu phải giữ nguyên nội dung người dùng nhập. Kết quả phép `=` và `ORDER BY` trong SQL còn chịu ảnh hưởng của collation.

### 6.3. `?`, `�` và ký tự lạ sau khi đọc lại

Nếu dữ liệu mất ký tự trước khi tới JDBC, phương thức `setNString()` không thể khôi phục phần đã mất. Nếu ký tự bị thay thế trong quá trình chuyển kiểu hoặc lưu, `getNString()` cũng không khôi phục được. Khi thấy dữ liệu hỏng, hãy truy dấu theo thứ tự: nguồn đầu vào → `String` Java → tham số JDBC → cột SQL/bộ mã → `ResultSet` → thiết bị hiển thị. Dùng phép so sánh trực tiếp giữa chuỗi gốc và chuỗi đọc lại để khoanh vùng, đồng thời kiểm tra console/log có hỗ trợ Unicode hay không.

### 6.4. Null, chuỗi rỗng và giới hạn chiều dài

`setNString(index, null)` có thể được driver chấp nhận theo hợp đồng JDBC, nhưng khi muốn biểu đạt kiểu SQL rõ ràng có thể dùng:

```java
statement.setNull(2, java.sql.Types.NVARCHAR);
```

`NULL` khác chuỗi rỗng `""` theo SQL nói chung, dù một số hệ quản trị có quy tắc riêng cho chuỗi rỗng. Chuỗi quá dài có thể gây lỗi, cắt ngắn hoặc hành vi phụ thuộc chế độ và hệ quản trị. Nên xác thực giới hạn ở ứng dụng **và** giữ ràng buộc cột tại cơ sở dữ liệu.

## 7. Khả năng hỗ trợ của driver và cách xử lý lỗi

Các phương thức `setNString()`, `getNString()`, `setNClob()`, `getNClob()` và họ `NCharacterStream` nằm trong các phiên bản JDBC hiện đại, nhưng driver không bắt buộc hỗ trợ mọi kiểu dữ liệu quốc gia của mọi hệ quản trị. Có thể gặp `SQLFeatureNotSupportedException`, một `SQLException` khi chuyển kiểu, hoặc dữ liệu được chuyển thành loại khác theo quy tắc driver.

| Triệu chứng | Nguyên nhân cần xem xét | Cách kiểm tra/khắc phục |
| --- | --- | --- |
| `setNString()` báo không hỗ trợ | Driver hoặc kiểu cột không hỗ trợ đường truyền ký tự quốc gia | Đối chiếu tài liệu driver; nếu cột Unicode thông thường được hỗ trợ, thử `setString()` và kiểm thử round-trip. |
| Lưu xong xuất hiện dấu `?` | Mất dữ liệu ở bước mã hóa/chuyển kiểu | Kiểm tra mã hóa nguồn, cột SQL, phép chuyển kiểu ngầm và cấu hình kết nối. |
| Tiếng Việt đúng nhưng emoji sai | Đường truyền/cột không hỗ trợ đầy đủ ký tự bổ sung hoặc xử lý sai surrogate pair | Kiểm tra UTF-8 đầy đủ (ví dụ `utf8mb4` nếu phù hợp), driver và giới hạn kiểu cột. |
| `getNString()` không đọc được cột | Kiểu SQL/driver không tương thích API | Xác định kiểu cột thực tế; dùng `getString()` nếu hợp lệ với cấu hình Unicode của hệ quản trị. |
| Ghi hoặc đọc `NCLOB` lỗi | Hệ quản trị không có kiểu `NCLOB`, hoặc driver chưa hỗ trợ API LOB quốc gia | Dùng kiểu text/LOB thay thế được hỗ trợ và phương thức JDBC tương ứng. |
| So sánh/sắp xếp khác kỳ vọng | Collation, normalization hoặc quy tắc phân biệt dấu/chữ | Kiểm tra collation, chuẩn hóa theo quy tắc nghiệp vụ, thử dữ liệu thực tế. |

Khi xử lý `SQLException`, kiểm tra `getSQLState()`, `getErrorCode()` và thông điệp lỗi của driver; không dựa riêng vào chuỗi thông báo để phân loại lỗi. Không dùng `catch (SQLException ignored)` để che lỗi Unicode. Nếu xây dựng chức năng chuyển đổi dự phòng sang `setString()`/`getString()`, phải chứng minh kiểu cột và driver thực sự lưu Unicode đúng; chuyển đổi âm thầm có thể khiến dữ liệu bị mất mà ứng dụng vẫn báo thành công.

## 8. Unicode trong CRUD, batch và transaction

Các thao tác `UPDATE` cũng dùng `setNString()` giống `INSERT`:

```java
String sql = "UPDATE user_profiles SET display_name = ? WHERE id = ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setNString(1, "Trần Minh 🌟");
    statement.setLong(2, 1001L);
    int updated = statement.executeUpdate();
    // updated == 0: không có hồ sơ phù hợp; > 0: có hàng bị ảnh hưởng.
}
```

Với nhiều bản ghi, có thể dùng `addBatch()`/`executeBatch()` để giảm số lượt trao đổi với cơ sở dữ liệu. Giá trị Unicode vẫn được truyền bằng setter tham số ở mỗi phần tử batch; sự hỗ trợ API `setN...` và xử lý lỗi từng phần tử vẫn phụ thuộc driver. Nếu một nghiệp vụ cập nhật nhiều bảng và cần tính nguyên tử, dùng **cùng một `Connection`**, `setAutoCommit(false)`, rồi `commit()` hoặc `rollback()` phù hợp. Việc đọc lại chuỗi đúng trước khi commit chưa chứng minh transaction đã được commit thành công.

Riêng với LOB/stream, vòng đời luồng dữ liệu, khả năng tái sử dụng sau khi chạy lệnh và khả năng chạy batch cần kiểm tra trên driver cụ thể. Không tái sử dụng một `Reader` đã được tiêu thụ nếu chưa đặt lại vị trí hoặc mở luồng mới.

## 9. Bài thực hành: xác minh Unicode round-trip

1. Tạo một bảng có khóa chính và một cột Unicode trên cơ sở dữ liệu đang học. Ghi rõ **tên kiểu cột** và **driver** đã chọn.
2. Viết phương thức `insert` bằng `PreparedStatement`; với cột quốc gia được hỗ trợ, dùng `setNString()`. Viết phương thức `SELECT` dùng `getNString()` và đóng tài nguyên bằng `try-with-resources`.
3. Ghi và đọc lại các chuỗi `"Đặng Thị Hồng"`, `"東京"`, `"العربية"`, `"🌏"`, và `"e\u0301"`. So sánh bằng `String.equals()` với giá trị gốc, ghi nhận trường hợp khác biệt.
4. Thử `NULL`, chuỗi rỗng, chuỗi gần và vượt giới hạn cột. Nếu lưu văn bản dài, thử `setNClob()`/`getNClob()` trên hệ quản trị có hỗ trợ hoặc kiểu LOB tương đương.
5. Chạy cùng bài thực hành bằng `setString()`/`getString()` nếu kiểu cột và driver cho phép; đối chiếu kết quả thay vì giả định một cặp API luôn tốt hơn.

**Cần nhớ:** JDBC cung cấp các API `setNString()`, `getNString()`, `setNClob()`, `getNClob()` và luồng ký tự quốc gia để làm việc với những kiểu SQL tương ứng. Lưu đúng Unicode đòi hỏi lựa chọn kiểu cột phù hợp, cấu hình driver chính xác, truyền SQL bằng tham số và kiểm tra dữ liệu ở cả hai chiều. Không đồng nhất tiền tố `N` với khả năng Unicode: hãy xác minh trên hệ quản trị đang dùng.
