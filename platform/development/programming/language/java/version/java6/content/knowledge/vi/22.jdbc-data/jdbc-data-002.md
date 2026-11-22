# setNString, getNString và dữ liệu Unicode trong JDBC (Java 17+)

## 1. Vấn đề cần hiểu đúng

Java dùng `String` để biểu diễn văn bản theo UTF-16. Khi lưu chuỗi tiếng Việt, tiếng Nhật, tên riêng quốc tế, emoji hoặc ký tự toán học vào cơ sở dữ liệu (database), ứng dụng cần đảm bảo **các ký tự được truyền và đọc lại đúng**, không bị thay bằng dấu hỏi, mất dấu, cắt giữa surrogate pair hoặc bị so sánh sai.

JDBC cung cấp hai nhóm method trông giống nhau:

- `PreparedStatement.setString(int, String)` và `ResultSet.getString(...)`: truyền/đọc giá trị chuỗi qua ánh xạ kiểu chuỗi thông thường của JDBC.
- **`PreparedStatement.setNString(int, String)` và `ResultSet.getNString(...)`**: các API **national character** dành cho cột/biến tham số dạng **`NCHAR`, `NVARCHAR` hoặc `LONGNVARCHAR`**.

Chữ **N** ở đây biểu thị **national character type** của JDBC/SQL, **không** phải thao tác thêm dấu tiếng Việt, tự đổi charset thành UTF-8 hay tự chuẩn hóa Unicode. Cả `setString` và `setNString` đều nhận một Java `String`. Sự khác biệt nằm ở **kiểu SQL được yêu cầu và cách JDBC driver chuyển dữ liệu tới cơ sở dữ liệu**.

Bài học phải phân biệt ba lớp:

1. **Java layer:** `String` chứa chuỗi các UTF-16 code units; có thể gồm ký tự ngoài BMP dùng surrogate pair.
2. **JDBC/driver layer:** `setNString` yêu cầu binding theo national character SQL type; `getNString` yêu cầu đọc cột phù hợp về Java String; tính năng này **có thể không được driver hỗ trợ**.
3. **Database layer:** schema, encoding/character set, collation, độ dài cột, giới hạn kích thước, SQL dialect và phiên bản server quyết định dữ liệu thực sự được lưu/so sánh thế nào.

**Nguyên tắc:** Chọn kiểu cột Unicode đúng cho **DBMS cụ thể**, dùng method JDBC đúng contract, sau đó **kiểm thử round-trip trên driver và database thật**. Đừng mặc định gọi `setNString` sẽ chữa mọi lỗi Unicode, và cũng đừng kết luận `setString` luôn làm mất Unicode.

Nội dung theo API Java SE 17+ vẫn được tài liệu Java SE 25 hỗ trợ; không dùng `setUnicodeStream` đã deprecated như một phương án mới.

## 2. Phân biệt các kiểu SQL và ánh xạ JDBC

JDBC xác định các type constants trong `java.sql.Types` và enum trong `java.sql.JDBCType`. Các national character types tiêu biểu:

| JDBC type | SQL family | Cách hiểu |
| --- | --- | --- |
| `Types.NCHAR` / `JDBCType.NCHAR` | `NCHAR` | National character kiểu cố định chiều dài |
| `Types.NVARCHAR` / `JDBCType.NVARCHAR` | `NVARCHAR` | National character kiểu biến thiên chiều dài |
| `Types.LONGNVARCHAR` / `JDBCType.LONGNVARCHAR` | `LONGNVARCHAR` | Giá trị national character lớn, tùy DBMS |
| `Types.NCLOB` / `JDBCType.NCLOB` | `NCLOB` | National character large object |
| `Types.CHAR` / `VARCHAR` / `LONGVARCHAR` | Non-national character types | **Vẫn có thể hỗ trợ Unicode đầy đủ** khi charset/collation/DBMS cho phép |
| `Types.CLOB` | Character large object | Khả năng Unicode phụ thuộc schema/database/driver |

`setNString` thích hợp với ba loại **NCHAR/NVARCHAR/LONGNVARCHAR** và có thể chuyển theo giới hạn kích thước của driver. Với `NCLOB`, các API chuyên dụng hơn là `setNClob`/`getNClob`, hoặc `setNCharacterStream` nếu driver hỗ trợ.

**Quan trọng:** không có quy tắc portable rằng mọi DBMS đều có đúng các từ khóa SQL này. Java/JDBC định nghĩa **khả năng ánh xạ**, không buộc PostgreSQL, Oracle, SQL Server và MySQL có cùng kiểu cột hoặc cùng charset nội bộ. Ngay tên cột `NVARCHAR` có thể mang tính vendor-specific. Cần đọc driver documentation và thực hiện phép thử trước khi triển khai production.

### Chữ N không có nghĩa Java String “bắt đầu là UTF-8”

- Java `String` chứa Unicode text bằng **UTF-16 code units**.
- `setNString` nhận `String`, **không nhận byte array chứa UTF-8**.
- Driver chuyển Java text thành biểu diễn wire/database cần thiết theo hợp đồng của nó.
- Database có thể lưu bằng UTF-16, UTF-8 hoặc mã hóa khác tùy sản phẩm, kiểu cột và collation.
- `getNString` trả lại **Java String**, không trả bytes hoặc charset metadata.
- Những method này không chuẩn hóa `NFC`/`NFD` hay thực hiện case folding một cách tổng quát.

Không dùng `new String(value.getBytes(...), ...)` để “sửa Unicode” một cách mù quáng trước `setNString`. Khi input Java đã đúng, chuyển qua bytes rồi giải mã sai charset có thể làm dữ liệu hỏng **ngay trong JVM**.

## 3. `PreparedStatement.setNString(...)`: binding dữ liệu Unicode đúng kiểu

Javadoc Java SE 25:

~~~java
void setNString(int parameterIndex, String value) throws SQLException;
~~~

- `parameterIndex` là **vị trí dấu `?` trong SQL**, **bắt đầu từ 1**, không bắt đầu từ 0.
- `value` là `String`; driver chuyển thành SQL `NCHAR`/`NVARCHAR`/`LONGNVARCHAR` tùy kích thước và khả năng của driver.
- Nếu index sai, statement đã đóng, driver không hỗ trợ national character set, không chuyển đổi được dữ liệu hoặc DB lỗi, có thể phát sinh `SQLException`; riêng method không được hỗ trợ có thể ném **`SQLFeatureNotSupportedException`**.
- `setNString` **chỉ bind parameter**, không tự thực thi SQL; phải gọi `executeUpdate`, `executeQuery` hoặc `execute` tùy câu lệnh.

Ví dụ một đoạn JDBC thực tế với cột national character:

~~~java
String input = "Xin chào, 東京 😀";
String sql = "INSERT INTO note_text (id, body) VALUES (?, ?)";

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, 42L);
    statement.setNString(2, input);
    int affected = statement.executeUpdate();
}
~~~

Đây là **mã minh họa trong method**, có `dataSource` đã được cung cấp và database chứa bảng `note_text` với cột `body` phù hợp, chẳng hạn `NVARCHAR` trên DBMS hỗ trợ. Cần import `Connection`, `PreparedStatement` và xử lý `SQLException`. **Không có stdout cố định** vì ví dụ phụ thuộc database/driver/schema thật.

### Tại sao dùng PreparedStatement thay nối chuỗi SQL?

Sai:

~~~java
String sql = "INSERT INTO note_text (body) VALUES ('" + input + "')";
~~~

Đây là **anti-pattern minh họa**. Nối input vào SQL gây **SQL injection**, lỗi escaping và các vấn đề liên quan Unicode string literal theo dialect. Với JDBC parameter:

~~~java
PreparedStatement statement =
        connection.prepareStatement("INSERT INTO note_text (body) VALUES (?)");
statement.setNString(1, input);
~~~

Đây là đoạn minh họa trong method với connection/input đã có; trong code thật hãy đóng statement bằng try-with-resources. Driver chịu trách nhiệm truyền **giá trị parameter**, không tự ghép văn bản của người dùng vào SQL command.

**`setString` cũng bảo vệ khỏi SQL injection** nếu được dùng qua `PreparedStatement`. `setNString` không phải “phiên bản bảo mật hơn” của `setString`; nó là **yêu cầu ánh xạ kiểu national character**, và đúng/sai phụ thuộc database schema và driver.

### SQL NULL khác chuỗi rỗng

~~~java
statement.setNString(1, "");            // Một String rỗng.
statement.setNull(2, Types.NVARCHAR);    // SQL NULL có kiểu NVARCHAR.
~~~

Đây là **đoạn minh họa** với hai parameter trong SQL và có import `java.sql.Types`. Cách cột lưu chuỗi rỗng có thể phụ thuộc DBMS (đặc biệt có khác biệt ở Oracle), nhưng ở API binding phải phân biệt rõ ý định **empty text** và **SQL NULL**.

Có thể gặp code `statement.setNString(index, null)`; xử lý `null` trong setter còn phụ thuộc mapping và driver. Với nhu cầu diễn đạt SQL NULL có **kiểu xác định**, `setNull(index, Types.NVARCHAR)` rõ ràng và dễ kiểm thử hơn. `Types.NCHAR` hoặc `Types.LONGNVARCHAR` có thể phù hợp nếu cột yêu cầu kiểu đó.

### Dấu tiếng Việt và emoji được truyền như thế nào?

~~~java
String value = "Tiếng Việt 😀";
statement.setNString(1, value);
~~~

`value` có các ký tự tiếng Việt trong BMP cùng **U+1F600 GRINNING FACE** nằm ngoài BMP. Java `String` giữ U+1F600 thành surrogate pair hai `char`/code units. Phương thức nhận nguyên String; bạn không cần tách emoji thành hai giá trị SQL, không truyền hai parameter, và không cần encode UTF-8 thủ công.

Nếu cột/DBMS không hỗ trợ toàn bộ code points, có thể xảy ra lỗi, mất dữ liệu hoặc thay thế ký tự tùy driver/server/config. **Chỉ một phép thử insert và đọc lại trên DB thật** mới xác nhận deployment của bạn đáp ứng hợp đồng Unicode cần thiết.

## 4. `ResultSet.getNString(...)`: đọc ngược thành Java String

Hai overload chuẩn:

~~~java
String getNString(int columnIndex) throws SQLException;
String getNString(String columnLabel) throws SQLException;
~~~

- `columnIndex` là **thứ tự cột trong SELECT, bắt đầu từ 1**, không phải thứ tự property của entity.
- `columnLabel` là **nhãn cột**, đặc biệt là alias do `AS` trong truy vấn tạo ra; nếu không dùng `AS`, thường là tên cột.
- Cả hai trả một `String` cho các giá trị kiểu `NCHAR`/`NVARCHAR`/`LONGNVARCHAR`.
- Nếu giá trị là **SQL NULL**, kết quả là **Java `null`**.
- Khi method không được JDBC driver hỗ trợ, nó có thể ném **`SQLFeatureNotSupportedException`**; các lỗi khác dùng `SQLException`.
- Cần gọi `rs.next()` và kiểm tra có row trước khi đọc `getNString`; khi stream hết rows, `next()` trả `false`.

Ví dụ:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement query = connection.prepareStatement(
             "SELECT body AS localized_body FROM note_text WHERE id = ?")) {
    query.setLong(1, 42L);

    try (ResultSet rows = query.executeQuery()) {
        if (rows.next()) {
            String text = rows.getNString("localized_body");
            if (text == null) {
                System.out.println("Giá trị SQL NULL");
            } else {
                System.out.println("Đã nhận " + text.codePointCount(0, text.length())
                        + " code points");
            }
        }
    }
}
~~~

Đây là **mã minh họa trong method** với `dataSource` và schema hợp lệ; không phải file runnable tự đủ vì cần DB thật. `getNString("localized_body")` dùng alias trong SELECT, không phải bắt buộc tên vật lý `body`.

### Khi nào dùng `wasNull()`?

JDBC `ResultSet.wasNull()` trả `true` nếu giá trị **của lần đọc getter gần nhất** là SQL NULL. Với `getNString` trả object `String`, so sánh `text == null` đã đủ trong nhiều trường hợp. `wasNull()` hữu ích khi cần một cơ chế thống nhất với getter trả kiểu nguyên thủy, chẳng hạn `getInt` trả 0 cho cả SQL NULL và giá trị 0.

~~~java
String value = rows.getNString("optional_text");
boolean sqlNull = rows.wasNull(); // Gọi ngay sau getter cần kiểm tra.

if (sqlNull) {
    // Database column là SQL NULL.
} else if (value.isEmpty()) {
    // Có String rỗng.
}
~~~

Đây là đoạn minh họa đặt **sau `rows.next() == true`**. **Đừng gọi một getter khác giữa `getNString` và `wasNull()`**, vì khi đó `wasNull()` mô tả **getter vừa được gọi sau cùng**, không còn mô tả `optional_text`.

### `getString` có đọc được Unicode không?

Có thể có. **Không được khẳng định `getString` hoặc `setString` là “ASCII-only”**. Trên PostgreSQL dùng UTF-8 hoặc MySQL dùng `utf8mb4` với cột `VARCHAR`/`TEXT` phù hợp, String bình thường có thể lưu/đọc đầy đủ Unicode. SQL Server cũng có lựa chọn `VARCHAR` với UTF-8 collation ở các phiên bản hiện đại.

`getNString` được thiết kế cho JDBC **national character** SQL types. Nếu DBMS/driver không có cơ chế NCHAR/NVARCHAR tương ứng, driver có thể không hỗ trợ hoặc xử lý theo quy tắc riêng. Chọn theo **schema**, không theo cảm giác “có ký tự tiếng Việt thì bắt buộc dùng NString”.

## 5. Chuỗi dữ liệu từ Java đến Database và quay về

~~~text
Java String (UTF-16 code units)
          │
          │ setNString(parameterIndex, value)
          ▼
PreparedStatement + JDBC Driver
          │  ánh xạ sang national character parameter SQL
          │  theo khả năng driver và DBMS
          ▼
Database column NCHAR/NVARCHAR/LONGNVARCHAR (nếu schema có)
          │  lưu dạng nội bộ phụ thuộc database/charset/collation
          │
          │ SELECT ...
          ▼
JDBC Driver + ResultSet
          │
          │ getNString(columnIndex/columnLabel)
          ▼
Java String  → so sánh giá trị và code points
~~~

Cả hai phía phải kiểm thử. Nếu input `String` đã hỏng trước JDBC, không có setter nào khôi phục lại ký tự gốc. Nếu driver encode chính xác nhưng schema là một kiểu cột với character set không thể biểu diễn ký tự, hệ thống vẫn có thể mất dữ liệu. Và nếu database lưu đúng mà terminal/font hiển thị ô vuông, **đó có thể chỉ là lỗi hiển thị**, không chứng minh dữ liệu ở DB sai.

Hãy kiểm tra theo **code point, byte/encoding phù hợp và equality**, không chỉ quan sát hình dạng chữ trên console.

## 6. Chương trình Java 17+ chạy được không cần database: kiểm thử hợp đồng API

Để xác minh cách gọi `setNString`, `setNull`, `getNString`, `wasNull` và cách phân biệt Unicode/SQL NULL/empty string, chương trình sau sử dụng **dynamic proxy giả lập** `PreparedStatement` và `ResultSet`. Nó không mở TCP connection, không dùng PostgreSQL/SQL Server/Oracle/MySQL và **không kiểm chứng mã hóa trong database thật**.

Đây là sự phân chia có chủ đích:

- **Unit-style contract test:** API được gọi với đúng parameter index, xử lý Java String, SQL NULL, Unicode và code point.
- **Integration test:** có driver, DB server, schema và collation thật; chỉ nó mới chứng minh dữ liệu Unicode lưu round-trip qua database chính xác.

Tạo file duy nhất **`NStringContractDemo.java`** với toàn bộ nội dung:

~~~java
import java.lang.reflect.Proxy;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;
import java.sql.Types;
import java.text.Normalizer;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;

public final class NStringContractDemo {
    private static PreparedStatement prepared(Map<Integer, String> saved) {
        Map<Integer, String> parameters = new HashMap<>();
        return (PreparedStatement) Proxy.newProxyInstance(
                NStringContractDemo.class.getClassLoader(),
                new Class<?>[] {PreparedStatement.class},
                (proxy, method, arguments) -> switch (method.getName()) {
                    case "setNString" -> {
                        parameters.put((int) arguments[0], (String) arguments[1]);
                        yield null;
                    }
                    case "setNull" -> {
                        if ((int) arguments[1] != Types.NVARCHAR)
                            throw new SQLException("Expected NVARCHAR");
                        parameters.put((int) arguments[0], null);
                        yield null;
                    }
                    case "executeUpdate" -> {
                        saved.putAll(parameters);
                        yield 1;
                    }
                    case "close" -> null;
                    default -> throw new SQLFeatureNotSupportedException(
                            "Fake does not implement " + method.getName());
                });
    }

    private static ResultSet result(Map<Integer, String> saved) {
        AtomicBoolean advanced = new AtomicBoolean();
        AtomicBoolean lastWasNull = new AtomicBoolean();
        return (ResultSet) Proxy.newProxyInstance(
                NStringContractDemo.class.getClassLoader(),
                new Class<?>[] {ResultSet.class},
                (proxy, method, arguments) -> switch (method.getName()) {
                    case "next" -> !advanced.getAndSet(true);
                    case "getNString" -> {
                        Object key = arguments[0];
                        int index = key instanceof Integer
                                ? (Integer) key
                                : switch ((String) key) {
                                    case "body" -> 1;
                                    case "optional" -> 2;
                                    case "empty" -> 3;
                                    case "accent" -> 4;
                                    default -> throw new SQLException("Unknown column");
                                };
                        if (!saved.containsKey(index))
                            throw new SQLException("Missing column");
                        String value = saved.get(index);
                        lastWasNull.set(value == null);
                        yield value;
                    }
                    case "wasNull" -> lastWasNull.get();
                    case "close" -> null;
                    default -> throw new SQLFeatureNotSupportedException(
                            "Fake does not implement " + method.getName());
                });
    }

    public static void main(String[] args) throws SQLException {
        String input = "Tiếng Việt \uD83D\uDE00";
        String decomposed = "e\u0301";
        Map<Integer, String> saved = new HashMap<>();

        try (PreparedStatement ps = prepared(saved)) {
            ps.setNString(1, input);
            ps.setNull(2, Types.NVARCHAR);
            ps.setNString(3, "");
            ps.setNString(4, decomposed);
            System.out.println("affected rows: " + ps.executeUpdate());
        }

        try (ResultSet rs = result(saved)) {
            if (!rs.next()) throw new SQLException("No row");
            String value = rs.getNString("body");
            System.out.println("body exact: " + input.equals(value));
            System.out.println("contains supplementary: "
                    + value.codePoints().anyMatch(cp -> cp > 0xFFFF));
            System.out.println("UTF-16 units: " + value.length());
            System.out.println("code points: "
                    + value.codePointCount(0, value.length()));

            String optional = rs.getNString(2);
            System.out.println("optional SQL NULL: "
                    + (optional == null && rs.wasNull()));

            String empty = rs.getNString("empty");
            System.out.println("empty is not NULL: "
                    + (empty != null && empty.isEmpty() && !rs.wasNull()));

            String accent = rs.getNString("accent");
            System.out.println("decomposed preserved: "
                    + decomposed.equals(accent));
            System.out.println("NFC equivalent: "
                    + Normalizer.normalize(accent, Normalizer.Form.NFC)
                            .equals("\u00E9"));
        }
    }
}
~~~

Biên dịch và chạy với JDK 17+ tại thư mục chứa file:

~~~bash
javac --release 17 NStringContractDemo.java
java NStringContractDemo
~~~

**Stdout chính xác**, đã chạy trên OpenJDK **24.0.2** với `--release 17`:

~~~text
affected rows: 1
body exact: true
contains supplementary: true
UTF-16 units: 13
code points: 12
optional SQL NULL: true
empty is not NULL: true
decomposed preserved: true
NFC equivalent: true
~~~

### Ý nghĩa của phép kiểm tra

1. `setNString(1, input)` và `getNString("body")` trả đúng chuỗi **trong lớp giả lập**, nên `body exact: true`.
2. Chuỗi `"Tiếng Việt 😀"` có **13 UTF-16 code units** nhưng **12 Unicode code points**, vì emoji U+1F600 chiếm **hai** UTF-16 units. `String.length()` không phải số code points.
3. `setNull(2, Types.NVARCHAR)` khiến cột `optional` là SQL NULL trong mô phỏng: `getNString(2) == null` và `wasNull()` true.
4. `setNString(3, "")` là chuỗi rỗng chứ không phải null. Trên một số DBMS, semantics lưu empty string khác nhau; test giả lập không thay thế tích hợp thật.
5. `"e\u0301"` là **e + COMBINING ACUTE ACCENT**; được giữ nguyên trong fake, chứng minh code không tự gọi Normalizer trước khi đưa vào map. `Normalizer.normalize(..., NFC)` cho `é`, tức **canonical-equivalent** nhưng raw Strings khác nhau.
6. `executeUpdate() == 1` trong giả lập là một giá trị có chủ ý để minh họa thao tác statement; không chứng minh database thực sự thay đổi một row.
7. Proxy chỉ implement methods cần test và ném `SQLFeatureNotSupportedException` ở những chỗ còn lại. **Không đưa fake này vào production**, không dùng nó để kiểm thử SQL syntax, networking, charset hay database collation.

### Vì sao vẫn nên test với DB thật?

Trong fake, không có **wire encoding**, không có database column length, không có JDBC driver vendor và không có server SQL. Vì vậy tất cả các assertions đều có thể pass ngay cả khi driver production sau đó làm hỏng emoji hoặc DB schema cắt chuỗi.

Unit test giúp kiểm tra **luồng application code**; integration test giúp xác nhận **hợp đồng end-to-end**.

## 7. Ví dụ CRUD sử dụng database thật: giữ đúng ranh giới nguồn dữ liệu

Trên **Microsoft SQL Server** (ví dụ vendor-specific), một schema minh họa:

~~~sql
CREATE TABLE dbo.note_text (
    id BIGINT NOT NULL PRIMARY KEY,
    body NVARCHAR(200) NOT NULL,
    optional_text NVARCHAR(200) NULL
);
~~~

Đây là **DDL minh họa cho SQL Server**, không phải cú pháp portable cho tất cả DBMS. Khả năng lưu ký tự ngoài BMP như emoji phụ thuộc phiên bản/collation của SQL Server; dùng collation có hỗ trợ supplementary characters theo chính sách hệ thống. Trong SQL Server, thông số `n` của `NVARCHAR(n)` được đo theo **byte-pairs/đơn vị lưu trữ**, không thể mặc nhiên coi là “n Unicode code points” hay “n graphemes”. Đặc biệt một supplementary character cần một surrogate pair, có thể tốn **hai** byte-pairs.

Một phương thức dùng **`DataSource` được inject** có thể minh họa cả đường ghi/đọc:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;
import javax.sql.DataSource;

public final class NoteWriter {
    private final DataSource source;

    public NoteWriter(DataSource source) {
        this.source = source;
    }

    public boolean insertAndCheck(long id, String input) throws SQLException {
        try (Connection connection = source.getConnection()) {
            String insert = "INSERT INTO dbo.note_text "
                    + "(id, body, optional_text) VALUES (?, ?, ?)";
            try (PreparedStatement ps = connection.prepareStatement(insert)) {
                ps.setLong(1, id);
                ps.setNString(2, input);
                ps.setNull(3, Types.NVARCHAR);
                ps.executeUpdate();
            }

            String select = "SELECT body, optional_text "
                    + "FROM dbo.note_text WHERE id = ?";
            try (PreparedStatement ps = connection.prepareStatement(select)) {
                ps.setLong(1, id);
                try (ResultSet rs = ps.executeQuery()) {
                    if (!rs.next()) {
                        throw new SQLException("Không tìm thấy row vừa ghi");
                    }
                    String actual = rs.getNString("body");
                    String optional = rs.getNString("optional_text");
                    return input.equals(actual) && optional == null;
                }
            }
        }
    }
}
~~~

Đây là **class có thể biên dịch với Java 17**, nhưng cần **SQL Server JDBC driver, DataSource, credentials, schema và quyền DB thật** mới chạy thành công. Không có `main` và không có output cố định. Phương thức chỉ minh họa round-trip; một test thật cũng phải setup/cleanup row, không dùng production database.

**Lưu ý:** ứng dụng production có transaction manager, retry policy và giới hạn kết nối; đoạn này không thay thế những trách nhiệm đó. `input` phải không null vì method gọi `input.equals(actual)`. Nếu cột có chính sách normalization/collation hoặc DB/driver có chuyển đổi, equality có thể false — đây là dấu hiệu cần điều tra chứ không nên tự normalize và che lỗi.

### SQL literal `N'...'` khác binding JDBC

Trong SQL Server, literal Unicode thường có cú pháp:

~~~sql
SELECT N'Tiếng Việt';
~~~

Nhưng **không ghép literal đó bằng input của người dùng**:

~~~java
// Không làm với dữ liệu không tin cậy:
String unsafe = "SELECT N'" + userText + "'";
~~~

Đó là anti-pattern vì SQL injection/escaping. Với `PreparedStatement`, bạn sử dụng `?` và `setNString` cho cột national character; JDBC driver chịu trách nhiệm kiểu tham số, không cần tự thêm tiền tố `N` vào chuỗi đầu vào.

## 8. Khác biệt thực tế theo database/driver

Không có “một cách dùng NString là chuẩn cho mọi RDBMS”. Hãy xét ít nhất:

| Hệ quản trị | Dạng dữ liệu Unicode nên xem xét | Hệ quả đối với `setNString/getNString` |
| --- | --- | --- |
| **SQL Server** | `NCHAR`/`NVARCHAR`, hoặc `VARCHAR` với UTF-8 collation ở phiên bản hỗ trợ | Microsoft JDBC Driver hỗ trợ national-character APIs; cần cấu hình kiểu cột/collation, thử supplementary characters |
| **Oracle Database** | `NCHAR`, `NVARCHAR2`, `NCLOB` và các character types khác theo DB character set | National character types có semantics riêng; chọn JDBC mapping theo Oracle driver/version |
| **PostgreSQL** | `VARCHAR`/`TEXT` trong database encoding UTF8 | Unicode đầy đủ thường dùng `setString/getString`; không tự giả định driver ánh xạ `NString` giống SQL Server |
| **MySQL/MariaDB** | `VARCHAR`/`TEXT` với `utf8mb4` và collation phù hợp | `setString/getString` có thể lưu cả emoji khi charset thực sự là utf8mb4; hỗ trợ national API cần xem driver cụ thể |

### SQL Server: national types và supplementary characters

Microsoft SQL Server có `NVARCHAR`/`NCHAR` và Microsoft JDBC Driver công bố hỗ trợ `setNString`/`getNString`. Nhưng muốn lưu đúng emoji **ngoài BMP**, còn phải xét **supplementary-character-aware collations** và phiên bản SQL Server. Trong SQL Server hiện đại, `VARCHAR` với UTF-8-enabled collation cũng là một lựa chọn lưu Unicode đầy đủ. Vì vậy:

- Không nói `NVARCHAR` là cách duy nhất có Unicode trên SQL Server.
- Không nói cứ có `NVARCHAR` là mọi collation/phiên bản đều xử lý supplementary characters tương đương.
- Không so `NVARCHAR(10)` như thể chứa đúng 10 grapheme clusters hoặc 10 Unicode code points. Kiểm tra byte-pair/storage semantics.
- Không giả định `getNString` tự sửa chuỗi đã bị cắt, hoặc do DB đang dùng collation không phù hợp.
- Khi dùng SQL Server national parameter, `setNString` có thể giúp driver truyền giá trị với định danh kiểu national thích hợp thay vì phụ thuộc conversion ngầm của `VARCHAR`.

### PostgreSQL và MySQL: Unicode không đòi hỏi tên SQL NVARCHAR

PostgreSQL database encoding UTF8 cho phép lưu Unicode trong những cột `VARCHAR`/`TEXT` thông thường, và Java `String` có thể được đọc/ghi qua `setString`/`getString` của PostgreSQL JDBC driver. MySQL cần chọn `utf8mb4` thực sự (không dùng character set 3-byte khiến emoji ngoài BMP không biểu diễn được). Đây là vấn đề **schema/connection character set**, không phải yêu cầu rằng mọi code có tiếng Việt/emoji bắt buộc gọi `setNString`.

Kiểm tra driver hiện tại: có driver ném `SQLFeatureNotSupportedException` cho national-character methods hoặc có mapping riêng. Khi DB dùng cột `VARCHAR/TEXT` lưu UTF-8 đầy đủ, dùng `setString/getString` đúng driver/schema có thể là **giải pháp hiện đại và chính xác**.

### NCHAR có thể có padding

Cột `NCHAR(n)` có thể được DBMS **pad khoảng trắng** tới chiều dài cố định. Nếu đọc lại bằng `getNString` và so sánh chuỗi nguyên bản có thể thấy trailing spaces hoặc semantics khác tùy driver. Không tự dùng `trim()`/`strip()` trên mọi dữ liệu: khoảng trắng cuối có thể có ý nghĩa. Nếu cần text biến thiên, `NVARCHAR`/`VARCHAR` thường là lựa chọn rõ ràng hơn.

## 9. Unicode không chỉ là tiếng Việt có dấu

### UTF-16 code units, code points và grapheme clusters

Xét:

~~~java
String s = "Tiếng Việt \uD83D\uDE00";
System.out.println(s.length());                           // 13 UTF-16 units
System.out.println(s.codePointCount(0, s.length()));       // 12 code points
~~~

Đây là đoạn trong method với kết quả cố định về **Java String**, không phụ thuộc database. Một code point ngoài Basic Multilingual Plane như U+1F600 dùng **hai UTF-16 code units**. Một emoji sequence có zero-width joiner hoặc một ký tự có dấu kết hợp có thể bao gồm **nhiều code points nhưng được hiển thị thành một grapheme cluster**.

Hệ quả:

- `String.length()` không đồng nghĩa số “ký tự nhìn thấy” trên màn hình.
- `NVARCHAR(n)` của một DBMS không nhất thiết đo bằng code points hoặc grapheme clusters.
- Trước khi validate độ dài, phải nêu rõ đang giới hạn **bytes lưu trữ, code units, code points hay grapheme clusters**.
- Không cắt chuỗi Java bằng `substring(0, max)` theo code-unit boundary nếu có nguy cơ chia đôi surrogate pair.
- Dữ liệu Unicode có thể chứa combining marks, variation selectors, right-to-left marks và emoji sequences; thử cả những tình huống này.

### NFC/NFD và nguyên văn dữ liệu

Hai String sau có thể nhìn giống nhau nhưng **khác chuỗi UTF-16**:

~~~java
String composed = "\u00E9";  // é (một code point).
String decomposed = "e\u0301"; // e + dấu sắc (hai code points).

System.out.println(composed.equals(decomposed)); // false
System.out.println(
        Normalizer.normalize(composed, Normalizer.Form.NFC)
                .equals(Normalizer.normalize(
                        decomposed, Normalizer.Form.NFC))); // true
~~~

Đây là đoạn trong method cần import `java.text.Normalizer`. `setNString/getNString` không có hợp đồng tự chạy Unicode Normalization. Database collation có thể coi hai dạng tương đương khi **so sánh SQL**, nhưng điều đó không chứng minh giá trị bytes/Java String sau round-trip phải giống hệt.

**Đừng âm thầm normalize trong lớp persistence** nếu dữ liệu cần giữ nguyên văn, chữ ký số, audit, định danh hoặc tài liệu học thuật. Nếu nghiệp vụ cần canonical matching, định nghĩa policy rõ: lưu original, tạo normalized match key, và áp dụng nhất quán ở input/query.

### Ký tự thay thế `�` không đủ để chẩn đoán

U+FFFD REPLACEMENT CHARACTER xuất hiện có thể là dấu hiệu lỗi decoding ở một giai đoạn nào đó, nhưng cũng có thể là **ký tự thật được người dùng nhập**. Khi điều tra, kiểm tra input source, HTTP encoding, driver, DB schema, connection charset và dữ liệu raw tại từng ranh giới; không chỉ tìm dấu `?` hoặc `�` trong screenshot.

## 10. Dữ liệu lớn: `setNCharacterStream`, `getNCharacterStream` và `NClob`

Với national character text lớn, thay vì materialize toàn bộ giá trị trong RAM rồi gọi `setNString`, JDBC có:

~~~java
void setNCharacterStream(int parameterIndex, Reader reader, long length)
        throws SQLException;
void setNCharacterStream(int parameterIndex, Reader reader)
        throws SQLException;
~~~

Đây là chữ ký **minh họa API**. Javadoc nêu `length` là **số ký tự** trong stream, **không phải số byte UTF-8**; `java.io.Reader` đọc Java `char`/UTF-16 code units. Với supplementary characters, cần đếm đúng theo hợp đồng Reader/driver, không dùng `codePointCount` thay cho `String.length()` một cách máy móc.

Ví dụ:

~~~java
String text = "Bản dài có Unicode 😀";
try (StringReader reader = new StringReader(text);
     PreparedStatement ps = connection.prepareStatement(
             "INSERT INTO note_text (body) VALUES (?)")) {
    ps.setNCharacterStream(1, reader, text.length());
    ps.executeUpdate();
}
~~~

Đây là đoạn minh họa trong method: cần `java.io.StringReader`, `PreparedStatement`, `connection` và schema thích hợp; đoạn này không phải một file chạy độc lập. `StringReader` chỉ minh họa stream interface, **không tiết kiệm memory** vì `text` đã là String trong RAM. Với dữ liệu lớn thật, dùng reader có nguồn phù hợp. Giữ `Reader` mở cho tới khi statement thực thi xong, vì driver có thể **đọc trễ** trong `executeUpdate`.

Đọc stream:

~~~java
try (Reader reader = rows.getNCharacterStream("body")) {
    if (reader == null) {
        // SQL NULL; xử lý trước khi đọc.
    } else {
        char[] buffer = new char[4096];
        int count;
        while ((count = reader.read(buffer)) != -1) {
            // Xử lý các char với logic có thể đi qua ranh giới buffer.
        }
    }
}
~~~

Đây là đoạn minh họa trong method, cần `Reader` và xử lý `IOException`/`SQLException` theo môi trường. **Không** giả định một lần `Reader.read` trả về một grapheme hay một code point hoàn chỉnh: surrogate pairs có thể bị chia ở ranh giới buffer. Ngoài ra, với nhiều drivers, gọi getter mới trên cùng ResultSet có thể đóng stream đang mở; đọc/đóng stream trước khi yêu cầu cột tiếp theo.

Với `NCLOB`, JDBC có `NClob`, `setNClob`, `getNClob`. Chọn theo **kiểu cột và kích thước thực tế**, không phải vì `String` có Unicode. Dữ liệu thường vài KB không nhất thiết cần NCLOB.

## 11. Unicode correctness phải được chứng minh bằng integration test

Một unit test sử dụng fake `PreparedStatement` như phần 6 chỉ chứng minh code gọi API đúng. Một integration test cần có **driver chính thức, database thật, schema và connection config giống production**.

### Ma trận dữ liệu đầu vào

| Nhóm test | Input ví dụ | Muốn phát hiện |
| --- | --- | --- |
| ASCII | `"Hello"` | Trường hợp cơ sở |
| Tiếng Việt NFC | `"Tiếng Việt có dấu"` | Mất dấu hoặc encoding sai |
| Dạng decomposed | `"e\u0301"` | Normalization không mong muốn |
| CJK | `"東京 中文 한국어"` | Character set/collation giới hạn |
| Emoji ngoài BMP | `"😀"` | Surrogate pair và supplementary support |
| Emoji sequence | `"👩‍💻"` | ZWJ và nhiều code points |
| Ký tự RTL | Một chuỗi Arabic/Hebrew | Bảo toàn text, không nhầm giao diện RTL với storage |
| Chuỗi rỗng | `""` | Khác SQL NULL theo DBMS |
| SQL NULL | `setNull(i, Types.NVARCHAR)` | `getNString(...) == null` và `wasNull()` |
| Khoảng trắng | `"  "`, tab/newline | Không tự trim, đúng semantics cột |
| Dữ liệu nhiều byte | Đoạn dài có emoji/tiếng Việt | Length, truncation và resource behavior |
| Biên độ cột | Gần và vượt giới hạn NVARCHAR | Driver/server lỗi thay vì cắt âm thầm |
| Ký tự đặc biệt SQL | `"O'Reilly 😀"` | PreparedStatement binding an toàn |

### Kiểm tra round-trip thật

1. Dùng schema phù hợp và một **test database riêng**, không phải production.
2. Đọc `DatabaseMetaData.getColumns(...)` hoặc schema metadata để biết cột dùng SQL type nào; có thể so `DATA_TYPE` với `Types.NVARCHAR` và `TYPE_NAME` theo vendor. **Không** dựa 100% vào một mapping type name portable vì driver có thể trình bày khác nhau.
3. Insert input bằng `setNString` nếu national-character type và driver hỗ trợ.
4. Read bằng `getNString`, so `input.equals(output)` và kiểm tra các `codePoints()`, đặc biệt emoji/combining sequences.
5. Kiểm tra null/empty và có/không padding ở fixed-length types.
6. Chạy cùng DBMS version, collation, connection encoding và JDBC driver version production sẽ dùng.
7. Test upgrade JDBC driver và DB migration để phát hiện thay đổi conversion/collation.
8. Đảm bảo test cleanup các rows và đóng `ResultSet`, `Statement`, `Connection` bằng try-with-resources.

**Không test round-trip chỉ bằng cách in stdout**: terminal hoặc font có thể hiển thị sai dù text đúng. Dùng assertions trên Java String/code points; với yêu cầu byte-perfect, thêm kiểm tra format/encoding ở lớp lưu trữ phù hợp DBMS.

### Nếu `SQLFeatureNotSupportedException` xuất hiện

Đừng catch rồi **lặng lẽ đổi `setNString` thành `setString`** trong mọi trường hợp. Hãy xác định trước:

- Database có national-character type thật không?
- Driver có hỗ trợ `setNString/getNString` cho version đang dùng không?
- Cột có được thiết kế bằng `VARCHAR/TEXT` Unicode theo database encoding thay vì `NVARCHAR` không?
- Nếu dùng `setString/getString` thay thế, **một integration test có xác nhận Unicode round-trip không?**

**Fallback chỉ an toàn khi được chứng minh với schema/driver cụ thể**; nó không phải một quy tắc JDBC chung.

## 12. Hiệu suất, batch, indexing và collation

### Parameter type có thể ảnh hưởng execution plan

Trên một số database, parameter bound kiểu `NVARCHAR` được so sánh với cột `VARCHAR` có thể kích hoạt **implicit conversion**. Tùy direction conversion, collation và optimizer, điều này có thể ảnh hưởng cách sử dụng index hoặc execution plan.

Ví dụ, nếu schema dùng `VARCHAR` với UTF-8 collation và driver đã hỗ trợ Unicode đúng bằng `setString`, cố dùng `setNString` cho mọi parameter không nhất thiết cải thiện đúng/sai hay hiệu năng. Ngược lại, nếu cột thực sự là `NVARCHAR` trên SQL Server, national binding có thể giúp khớp kiểu tốt hơn.

**Chọn phương thức theo schema và đo với driver/DBMS thật**, không chọn vì tên method có vẻ “mới hơn”.

### Batch nhiều dòng

~~~java
try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO note_text (id, body) VALUES (?, ?)")) {
    for (int i = 0; i < texts.size(); i++) {
        ps.setLong(1, firstId + i);
        ps.setNString(2, texts.get(i));
        ps.addBatch();
    }
    ps.executeBatch();
}
~~~

Đây là **mã minh họa trong method** có `connection`, `texts`, `firstId` hợp lệ; schema và driver phải hỗ trợ. Thao tác batch không thay yêu cầu kiểm soát transaction, rollback, batch size, parameter count và failure semantics. Với văn bản rất lớn, giới hạn batch size để không gây áp lực bộ nhớ.

### Collation ảnh hưởng so sánh, không phải `getNString` tự “dịch nghĩa”

Một collation có thể case-insensitive hoặc accent-insensitive, nên SQL `WHERE name = ?` có thể coi hai chuỗi khác nhau là cùng key. Điều đó **không đồng nghĩa** `getNString` trả chuỗi đã lowercase, bỏ dấu hoặc NFC-normalized. Cần tách:

- **Storage / Unicode encoding:** dữ liệu nào được giữ nguyên.
- **Comparison/sort:** database collation định nghĩa equality/order.
- **Application normalization:** policy riêng nếu muốn chuẩn hóa cho search, uniqueness hoặc authentication.

Đặc biệt khi lưu định danh người dùng, đừng thay đổi normalization/collation mà không phân tích collision (ví dụ nhiều tên trước đây khác nhau có thể so sánh bằng nhau), index/unique constraints và migration.

## 13. Những lỗi thường gặp

| Nhận định hoặc code sai | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| “Tiếng Việt thì bắt buộc phải `setNString`.” | PostgreSQL UTF8 / MySQL utf8mb4 có thể lưu Unicode qua `VARCHAR/TEXT` và `setString` | Chọn theo schema và driver |
| “`setString` chỉ hỗ trợ ASCII.” | Java String và driver có thể truyền Unicode đầy đủ | Test DB encoding và mapping thực |
| “`setNString` đảm bảo không bao giờ mất emoji.” | DB collation/charset/length có thể không hỗ trợ | Test supplementary character round-trip |
| “JDBC NString = UTF-8.” | Java String UTF-16; N nói về SQL national character types | Phân biệt Java/driver/database |
| “`getNString` trả byte array.” | Trả Java `String` hoặc null | Dùng `String` và code points |
| “Parameter bắt đầu từ 0.” | JDBC parameter index bắt đầu từ 1 | `setNString(1, value)` |
| “Cột SELECT index bắt đầu từ 0.” | JDBC column index bắt đầu từ 1 | `getNString(1)` |
| “`getNString` null = empty.” | SQL NULL trả null, empty string khác | `setNull` và kiểm tra `wasNull` |
| “`wasNull()` sau getter khác vẫn nói về cột cũ.” | Nó phản ánh getter gần nhất | Gọi ngay sau getter cần kiểm tra |
| “`setNString` tự chạy câu INSERT.” | Chỉ bind parameter | Gọi `executeUpdate` |
| “Đầu vào có dấu phải `getBytes("UTF-8")` rồi bind.” | Dễ double-encode/ghi sai type | Truyền Java `String` trực tiếp |
| “Dùng `String.length()` để giới hạn code points.” | `length()` đếm UTF-16 code units | Chọn phép đo đúng với schema |
| “`NVARCHAR(10)` chứa 10 emoji trên mọi DBMS.” | Length units và supplementary handling phụ thuộc sản phẩm | Kiểm tra vendor semantics |
| “NString tự NFC-normalize.” | Không có hợp đồng normalization | Chính sách normalization riêng |
| “Mọi driver đều hỗ trợ national character API.” | Có thể ném `SQLFeatureNotSupportedException` | Kiểm tra driver version và integration |
| “Dùng `setNString` tránh SQL injection, `setString` thì không.” | Cả hai đều bind values qua PreparedStatement | Không nối input vào SQL |
| “Nếu test với proxy pass thì production DB chắc chắn đúng.” | Proxy không thực hiện transcoding/storage | Test DB thật |
| “Đổi sang `setUnicodeStream` vì là API Unicode.” | API này đã deprecated, không còn là hướng hiện đại | `setNString`/`setNCharacterStream` theo schema |
| “`NCHAR` không bao giờ thêm khoảng trắng.” | Fixed-length types có thể pad | Dùng type phù hợp, test exact |
| “Một câu SQL compare khác nhau chứng minh database đã sửa text.” | Collation equality khác raw String equality | Kiểm tra kết quả và code points |

## 14. Checklist triển khai

1. **Thiết kế schema:** biết database đang dùng `NCHAR/NVARCHAR` hay `VARCHAR/TEXT` với Unicode character set, cùng length semantics.
2. **Chọn API:** national character SQL types → cân nhắc `setNString/getNString`; Unicode column non-national → có thể là `setString/getString` đúng.
3. **Kiểm tra driver:** JDBC driver version hỗ trợ method và type cụ thể, không dựa vào tên method chung.
4. **Bảo vệ input:** dùng parameterized `PreparedStatement`, validate length trước/bên trong DB, không encode/escape tự phát.
5. **Thử emoji/CJK/tiếng Việt:** so input với output bằng `equals`/code points; xác nhận surrogate pairs và grapheme sequences.
6. **Xử lý SQL NULL:** `setNull(i, Types.NVARCHAR)` và `getNString(...) == null` khi phù hợp; phân biệt empty string theo DBMS.
7. **Kiểm tra normalization:** có cần giữ bản gốc NFC/NFD hoặc tạo match key riêng? Không tự NFKC mọi text.
8. **Kiểm tra collation:** case/accent sensitivity, duplicate keys và index behavior.
9. **Kiểm tra performance:** implicit conversions, batch size, connection usage và streaming large text.
10. **Cơ chế lỗi:** xử lý `SQLException`/`SQLFeatureNotSupportedException`, không âm thầm fallback có thể mất dữ liệu.
11. **Quản lý tài nguyên:** `Connection`, `PreparedStatement`, `ResultSet`, `Reader`/`NClob` đều cần lifecycle phù hợp.
12. **Regression:** chạy cùng driver/DBMS/charset/collation với production khi nâng cấp version.

## 15. Câu hỏi tự kiểm tra

1. **`setNString` nhận Java bytes hay String?** Nhận `String`; JDBC driver thực hiện conversion tới national character SQL type.
2. **`getNString` trả kiểu Java nào?** `String` hoặc null cho SQL NULL.
3. **Hai method NString nhắm những SQL types nào?** `NCHAR`, `NVARCHAR`, `LONGNVARCHAR` theo hợp đồng JDBC.
4. **Dùng `setNString(0, text)` đúng không?** Không, parameter index bắt đầu từ 1.
5. **Có nên dùng `setNString` cho mọi cột `VARCHAR` UTF8?** Không mặc nhiên; phụ thuộc database schema và driver.
6. **SQL NULL khác `""` như thế nào?** SQL NULL biểu thị thiếu/không có giá trị, còn empty là một String có độ dài 0 (semantics DBMS có thể khác).
7. **Cần `wasNull()` khi nào?** Khi muốn biết getter gần nhất có đọc SQL NULL; gọi ngay sau getter.
8. **Emoji U+1F600 chiếm bao nhiêu `char` trong Java?** Hai UTF-16 code units, một code point.
9. **`setNString` có tự chuẩn hóa NFC không?** Không; normalization là policy riêng.
10. **`SQLFeatureNotSupportedException` cho biết điều gì?** Driver không hỗ trợ method/feature đang dùng; xem lại driver và schema, không fallback mù.
11. **Vì sao unit test proxy không đủ?** Không có transcoding, DB column, collation hoặc socket thật.
12. **Dùng `getString` có mất Unicode trên PostgreSQL UTF8 không?** Không phải mặc định; driver/schema đúng có thể trả Unicode nguyên vẹn.
13. **Vì sao NCHAR fixed length có thể làm round-trip equality thất bại?** Padding spaces hoặc semantics cột.
14. **`setNCharacterStream` length tính theo bytes UTF8 hay Reader characters?** Theo số ký tự của Reader, không phải UTF8 bytes.
15. **`setNString` có chống SQL injection không?** Nó bind parameter, nhưng `setString` cũng vậy; mấu chốt là không ghép user text vào SQL.
16. **Nếu cột NVARCHAR đủ dài mà emoji vẫn sai, cần kiểm tra gì?** DBMS/version/collation supplementary support, driver, input String và pipeline encoding.

## 16. Tài liệu chuẩn còn áp dụng

- [Java SE 25 — PreparedStatement](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/PreparedStatement.html): `setString`, `setNString`, `setNull`, `setNCharacterStream`, `setNClob` và các exceptions.
- [Java SE 25 — ResultSet](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/ResultSet.html): `getNString` theo index/label, SQL NULL, `wasNull`, `getNCharacterStream`, `getNClob`.
- [Java SE 25 — java.sql.Types](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/Types.html): các type constants `NCHAR`, `NVARCHAR`, `LONGNVARCHAR`, `NCLOB`.
- [Java SE 25 — java.sql.JDBCType](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/JDBCType.html): SQLType enum mapping cho JDBC standard types.
- [Java SE 25 — java.sql.DatabaseMetaData](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/DatabaseMetaData.html): `getColumns` và metadata cho SQL types thực tế.
- [Java SE 25 — java.lang.String](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html): `length`, `codePoints`, `codePointCount` và UTF-16.
- [Unicode Standard Annex #15](https://www.unicode.org/reports/tr15/): Unicode Normalization Forms; không phải chức năng tự động của setNString.
- [Microsoft JDBC Driver for SQL Server — National character set support](https://learn.microsoft.com/en-us/sql/connect/jdbc/national-character-set-support): national character JDBC methods trên Microsoft driver.
- [Microsoft SQL Server — Collation and Unicode support](https://learn.microsoft.com/en-us/sql/relational-databases/collations/collation-and-unicode-support): supplementary characters, `NVARCHAR`, collation và UTF-8 options của SQL Server.
- [PostgreSQL — Character Types](https://www.postgresql.org/docs/current/datatype-character.html): `character varying`/`text` theo encoding của database, ví dụ UTF8.
- [MySQL — utf8mb4 Character Set](https://dev.mysql.com/doc/refman/8.4/en/charset-unicode-utf8mb4.html): Unicode data với utf8mb4, kể cả supplementary characters.

**Tổng kết:** `setNString` và `getNString` là API JDBC **đúng cho national character SQL types**, không phải “nút bật UTF-8” hay “bảo hiểm chống mất Unicode”. Chất lượng Unicode phụ thuộc **Java String → driver → schema/charset/collation → driver → String**. Chọn method đúng type, xử lý null/empty và supplementary characters chính xác, dùng PreparedStatement an toàn, kiểm thử cả unit lẫn database thật, không áp dụng các API deprecated.