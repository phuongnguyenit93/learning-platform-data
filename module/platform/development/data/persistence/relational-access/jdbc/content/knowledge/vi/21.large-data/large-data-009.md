# Kiểm tra giới hạn kích thước và chuyển đổi bảng mã trong JDBC

Trong chương **Dữ liệu lớn**, một chuỗi văn bản dài “100 ký tự” có thể chiếm nhiều hơn 100 byte, một tệp được đọc đúng số byte vẫn có thể giải mã sai tiếng Việt, còn một cột được khai báo `VARCHAR(100)` chưa chắc lưu được mọi nội dung mà ứng dụng cho là hợp lệ. Khi dữ liệu tăng đến mức hàng chục MB hoặc GB, sai khác giữa **số ký tự, số byte, bảng mã, giới hạn cột và cách truyền dữ liệu** có thể dẫn đến cắt cụt dữ liệu, lỗi chuyển mã hoặc tiêu tốn quá nhiều bộ nhớ.

Với **JDBC**, ứng dụng Java truy cập cơ sở dữ liệu quan hệ qua driver và `DataSource`, dùng `PreparedStatement` để gửi SQL tham số hóa, `ResultSet` để đọc kết quả và transaction để bảo đảm tính nhất quán. Bài học này tập trung vào việc **đo đúng kích thước**, **kiểm soát mã hóa/giải mã** và **chọn phương thức JDBC phù hợp khi dữ liệu lớn**.

Sau bài học, bạn có thể:

- Phân biệt `String.length()`, Unicode code point, ký tự người dùng nhìn thấy và số byte khi mã hóa.
- Đọc `COLUMN_SIZE`, `CHAR_OCTET_LENGTH` và các giới hạn do driver công bố; xác định giá trị metadata nào chỉ có tính tham khảo.
- Phát hiện dữ liệu không thể mã hóa bằng bộ mã đã chọn, tránh thay thế ký tự âm thầm.
- Sử dụng `setString()`/`getString()` cho văn bản, `setBytes()`/`getBytes()` cho dữ liệu nhị phân, và các API stream cho nội dung lớn.
- Kiểm tra lỗi kích thước, lỗi bảng mã, giới hạn bộ nhớ và tình huống cần rollback hoặc retry.

## 1. “Kích thước” có nhiều đơn vị khác nhau

Một dữ liệu văn bản có thể được đo theo nhiều cách:

| Cách đo | Ý nghĩa | Ví dụ API |
| --- | --- | --- |
| **UTF-16 code units** | Số đơn vị mã 16 bit trong chuỗi Java | `String.length()` |
| **Unicode code points** | Số điểm mã Unicode | `String.codePointCount(0, s.length())` |
| **Grapheme clusters** | Các cụm ký tự người dùng nhìn thấy, có thể gồm nhiều code point | Cần xử lý phân đoạn Unicode phù hợp |
| **Encoded bytes / octets** | Số byte sau khi mã hóa theo charset cụ thể | `CharsetEncoder` hoặc `getBytes(charset)` |
| **Giới hạn cột SQL** | Số ký tự hoặc byte được DBMS cho phép theo khai báo và ngữ nghĩa kiểu | `DatabaseMetaData.getColumns(...)`, tài liệu DBMS |
| **Giới hạn truyền/đệm** | Giới hạn driver, protocol, packet, heap, thời gian chờ | Cấu hình/tài liệu driver và phép đo thực tế |

Các con số này **không nhất thiết bằng nhau**.

Ví dụ:

| Chuỗi | `String.length()` | Code points | Byte UTF-8 | Ghi chú |
| --- | ---: | ---: | ---: | --- |
| `ABC` | 3 | 3 | 3 | ASCII |
| `é` (dạng Unicode dựng sẵn, U+00E9) | 1 | 1 | 2 | Một code point |
| `e◌́` (chữ e + dấu sắc kết hợp U+0301) | 2 | 2 | 3 | Thường nhìn thành một cụm ký tự |
| `😀` | 2 | 1 | 4 | Một code point ngoài BMP, hai UTF-16 code units |
| `A😀` | 3 | 2 | 5 | Ba đơn vị UTF-16, hai code point |

Ví dụ về `e◌́` trong bảng mang nghĩa chuỗi có **hai code point** `U+0065` và `U+0301`; ký hiệu vòng tròn chỉ dùng để nhìn rõ dấu kết hợp. Trong code, chuỗi này có thể biểu diễn bằng `"e\u0301"`.

### Đo trong Java

~~~java
import java.nio.charset.StandardCharsets;

String text = "A😀";

int utf16Units = text.length(); // 3
int codePoints = text.codePointCount(0, text.length()); // 2
int utf8Bytes = text.getBytes(StandardCharsets.UTF_8).length; // 5

System.out.printf(
    "UTF-16 units=%d, code points=%d, UTF-8 bytes=%d%n",
    utf16Units, codePoints, utf8Bytes
);
~~~

`String.length()` **không trả số byte** và cũng không luôn là số ký tự người dùng nhìn thấy. Java lưu `String` theo mô hình chuỗi UTF-16, bất kể JVM tối ưu biểu diễn nội bộ ra sao.

`getBytes(StandardCharsets.UTF_8)` phù hợp để đo các chuỗi **đã được xác thực hợp lệ**. Nếu chuỗi chứa surrogate không ghép đôi hoặc cần mã hóa sang charset không biểu diễn được một ký tự, API encode thuận tiện có thể **thay thế ký tự lỗi**. Với đường đi yêu cầu bảo toàn dữ liệu, dùng `CharsetEncoder` với chính sách `REPORT` như phần 4.

## 2. Đường đi của dữ liệu và vị trí chuyển bảng mã

Khi nhận tệp hoặc gọi API rồi lưu vào một cột văn bản, dữ liệu thường đi qua các bước:

~~~mermaid
flowchart LR
    A["Byte đầu vào<br/>UTF-8 / charset nguồn"] --> B["Giải mã rõ charset<br/>thành Java String"]
    B --> C["PreparedStatement<br/>setString / setCharacterStream"]
    C --> D["JDBC driver<br/>và mã hóa giao tiếp"]
    D --> E["DBMS<br/>charset/encoding cột"]
    E --> F["ResultSet<br/>getString/getCharacterStream"]
    F --> G["Java String<br/>và mã hóa đầu ra nếu cần"]
~~~

Mỗi khâu có rủi ro riêng:

1. **Giải mã đầu vào sai:** Các byte của tệp UTF-8 bị đọc như Windows-1252, sinh chuỗi `CafÃ©` thay vì `Café` (*mojibake*). Khi đã tạo thành chuỗi sai, lưu JDBC bằng `setString()` vẫn có thể thành công nhưng dữ liệu bên trong đã sai.
2. **Mã hóa kết nối/DBMS không tương thích:** Cột hoặc kết nối dùng bộ mã không thể biểu diễn emoji hoặc ký tự đặc biệt; driver/DBMS có thể từ chối, thay thế ký tự hoặc chuyển đổi theo chính sách cấu hình.
3. **Giới hạn cột:** Dữ liệu văn bản hợp lệ về Unicode nhưng vượt giới hạn số ký tự hoặc byte mà DBMS áp dụng.
4. **Giới hạn tài nguyên:** Payload hợp lệ nhưng quá lớn cho heap Java, packet, bộ đệm driver, transaction log hoặc bộ nhớ của server.

**Chú ý:** JDBC **không có một API chuẩn chung** để ép mọi DBMS luôn dùng UTF-8 ở phía server. Mã hóa phía client/server có thể phụ thuộc driver, cấu hình kết nối và DBMS. Thực tế cần xem tài liệu driver và thông số charset/collation của cơ sở dữ liệu đích.

### Charset khác collation

- **Charset/encoding** quyết định cách biểu diễn hoặc chuyển đổi ký tự thành byte.
- **Collation** quyết định quy tắc so sánh/sắp xếp chuỗi, có thể liên quan phân biệt hoa thường, dấu hoặc tương đương Unicode.
- **Normalization** (`NFC`, `NFD`, v.v.) là quy tắc chuẩn hóa biểu diễn Unicode. Hai chuỗi nhìn giống nhau có thể khác số code point, số byte và kết quả so sánh.

Đừng coi cài đặt collation là bằng chứng rằng việc mã hóa đầu vào/đầu ra đã chính xác. Nếu nghiệp vụ cần chuẩn hóa Unicode, hãy định nghĩa thời điểm chuẩn hóa và đo/kiểm tra kích thước **sau chuẩn hóa**.

## 3. Tìm giới hạn được công bố bằng metadata JDBC

Giới hạn của cột hiện có thường được truy vấn qua `DatabaseMetaData.getColumns(...)`, thu được từ `Connection.getMetaData()`.

Các trường đáng chú ý:

| Trường metadata | Ý nghĩa |
| --- | --- |
| `DATA_TYPE` | Mã kiểu SQL theo `java.sql.Types`, ví dụ `VARCHAR`, `NVARCHAR`, `CLOB`, `BLOB` |
| `TYPE_NAME` | Tên kiểu mà DBMS/driver công bố |
| `COLUMN_SIZE` | Độ dài hoặc precision, **phải diễn giải theo loại dữ liệu** |
| `CHAR_OCTET_LENGTH` | Độ dài tối đa theo **byte** của kiểu ký tự, khi có thông tin |
| `DECIMAL_DIGITS` | Scale/chữ số thập phân đối với kiểu thích hợp, không phải byte |
| `NULLABLE`, `IS_NULLABLE` | Cột có cho phép `NULL` không |
| `COLUMN_DEF` | Giá trị mặc định khi có thông tin |

Ví dụ cột `title VARCHAR(100)` có thể có `COLUMN_SIZE = 100`. Với kiểu ký tự, thông tin này thường liên quan số ký tự, trong khi `CHAR_OCTET_LENGTH` cung cấp một giới hạn byte được công bố. Nhưng **không phải DBMS nào cũng dùng cùng ngữ nghĩa chiều dài**: có hệ phân biệt `BYTE` và `CHAR` khi khai báo, có giới hạn byte tổng của hàng, và có hệ dùng charset riêng cho từng cột.

### Ví dụ đọc metadata cột

~~~java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class ColumnSizeInspector {
    private ColumnSizeInspector() {}

    public record ColumnLimit(
        String typeName,
        int jdbcType,
        Integer declaredSize,
        Integer maxCharBytes
    ) {}

    public static ColumnLimit findTitle(Connection conn)
            throws SQLException {
        DatabaseMetaData meta = conn.getMetaData();

        // Ví dụ bảng documents, cột title; thay catalog/schema
        // cho đúng môi trường thực tế.
        try (ResultSet rs = meta.getColumns(
                conn.getCatalog(), null, "documents", "title")) {
            if (!rs.next()) {
                throw new SQLException(
                    "Không thấy metadata của documents.title"
                );
            }

            String typeName = rs.getString("TYPE_NAME");
            int jdbcType = rs.getInt("DATA_TYPE");

            int size = rs.getInt("COLUMN_SIZE");
            Integer declaredSize = rs.wasNull() ? null : size;

            int bytes = rs.getInt("CHAR_OCTET_LENGTH");
            Integer charBytes = rs.wasNull() ? null : bytes;

            return new ColumnLimit(
                typeName, jdbcType, declaredSize, charBytes
            );
        }
    }
}
~~~

Trong triển khai thực tế:

- Tham số thứ ba/thứ tư của `getColumns()` là **pattern**, ký tự `%` và `_` có ý nghĩa wildcard. Muốn tìm chính xác tên chứa wildcard phải escape với `getSearchStringEscape()`, rồi kiểm tra tên trả về.
- Các giá trị có thể là SQL `NULL`, do đó phải gọi `wasNull()` ngay sau `getInt()`. Giá trị không được công bố **khác với số 0 thật**.
- Catalog, schema, việc chuẩn hóa tên bảng và quyền đọc metadata phụ thuộc DBMS. Kết quả rỗng chưa chắc chứng minh bảng không tồn tại.
- Với `CHAR_OCTET_LENGTH`, metadata cho biết giới hạn được công bố; tính toán byte cho dữ liệu cụ thể vẫn phải dựa vào charset thực tế.
- Với `BLOB` và `CLOB`, `COLUMN_SIZE` có thể không có cùng ý nghĩa như `VARCHAR`; hãy tra quy định storage/LOB của DBMS.

### Các giới hạn khác từ `DatabaseMetaData`

~~~java
DatabaseMetaData meta = connection.getMetaData();

int maxCharLiteral = meta.getMaxCharLiteralLength();
int maxBinaryLiteral = meta.getMaxBinaryLiteralLength();
int maxSqlLength = meta.getMaxStatementLength();
int maxRowBytes = meta.getMaxRowSize();

System.out.println("SQL character literal: " + maxCharLiteral);
System.out.println("SQL binary literal: " + maxBinaryLiteral);
System.out.println("SQL statement length: " + maxSqlLength);
System.out.println("Maximum row size: " + maxRowBytes);
~~~

Với nhiều phương thức `getMax...()` của JDBC, `0` nghĩa là **không giới hạn hoặc không rõ giới hạn**, không phải giới hạn thực sự bằng 0.

**Điểm phân biệt rất quan trọng:** Giới hạn literal SQL (`getMaxCharLiteralLength()`) liên quan đến việc viết literal trực tiếp trong câu SQL. Nó **không tương đương** giới hạn kích thước giá trị truyền bằng placeholder `?` của `PreparedStatement`, cũng không quyết định giới hạn riêng của cột `VARCHAR`/`CLOB`. `getMaxStatementLength()` cũng không trực tiếp cho biết file tối đa có thể truyền bằng `setBinaryStream()`.

## 4. Chuyển đổi bảng mã nghiêm ngặt, tránh mất ký tự

Khi đọc dữ liệu từ tệp hoặc hệ thống bên ngoài, **phải biết hoặc xác định đáng tin charset nguồn**. Không được suy luận tất cả byte đều là UTF-8.

### 4.1. Mã hóa `String` với chế độ báo lỗi

`String.getBytes(charset)` có thể thay thế ký tự không mã hóa được hoặc chuỗi có surrogate lỗi. Nếu muốn dữ liệu được bảo toàn, dùng `CharsetEncoder` với `CodingErrorAction.REPORT`:

~~~java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.Charset;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;

public final class StrictEncoding {
    private StrictEncoding() {}

    public static byte[] encode(String value, Charset charset)
            throws CharacterCodingException {
        ByteBuffer encoded = charset.newEncoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .encode(CharBuffer.wrap(value));

        byte[] bytes = new byte[encoded.remaining()];
        encoded.get(bytes);
        return bytes;
    }
}
~~~

Ví dụ:

~~~java
import java.nio.charset.StandardCharsets;

String message = "Cà phê ☕";

byte[] utf8 = StrictEncoding.encode(
    message, StandardCharsets.UTF_8
);

System.out.println("Code points: "
    + message.codePointCount(0, message.length()));
System.out.println("UTF-8 bytes: " + utf8.length);
~~~

`CharsetEncoder` có thể ném `MalformedInputException` khi gặp chuỗi UTF-16 không hợp lệ, hoặc `UnmappableCharacterException` khi ký tự không biểu diễn được bằng charset đã chọn.

**Giới hạn của ví dụ:** Phương thức này tạo `byte[]` chứa toàn bộ dữ liệu mã hóa, phù hợp để kiểm tra **chuỗi ngắn hoặc trung bình**. Với tài liệu nhiều GB, không gọi nó chỉ để đo kích thước; dùng các API xử lý theo luồng.

### 4.2. Giải mã byte theo charset đã xác nhận

Nếu byte đầu vào là UTF-8, giải mã nghiêm ngặt như sau:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

static String decodeUtf8Strict(byte[] source)
        throws CharacterCodingException {
    return StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT)
        .decode(ByteBuffer.wrap(source))
        .toString();
}
~~~

Không chọn charset chỉ vì dữ liệu “hiển thị có vẻ đúng”. Những byte không hợp lệ có thể bị thay bằng `�` mà người dùng không phát hiện; tệp văn bản xuất lại sẽ không khôi phục được nội dung gốc.

Với tệp nhiều GB, sử dụng `InputStreamReader` với `CharsetDecoder` ở chế độ `REPORT` để giải mã theo luồng (xem phần 6).

### 4.3. Khi nào không nên chuyển mã?

Với ảnh, tài liệu PDF, video, tệp ZIP, khóa mã hóa hoặc bất kỳ payload nhị phân **không phải văn bản**, không áp dụng `new String(bytes, charset)` hay `getBytes(charset)` để lưu. Việc giải mã/biên mã có thể thay byte hoặc làm hỏng nội dung.

Thay vào đó:

- Dùng `setBytes()` hoặc `setBinaryStream()` để ghi vào kiểu nhị phân thích hợp.
- Dùng `getBytes()` hoặc `getBinaryStream()` khi đọc lại.
- So sánh kích thước byte và checksum nếu cần bảo đảm tính toàn vẹn.

Một cột `BLOB` chứa bytes không có “bảng mã Unicode” bắt buộc; chỉ khi nghiệp vụ quyết định giải mã nó thành văn bản mới cần biết charset.

## 5. Kiểm tra giới hạn trước khi `setString()`

Giả sử bảng có cột `documents.title` kiểu ký tự được công bố với kích thước 100. Một quy trình kiểm tra hợp lý:

1. Xác định kiểu và `COLUMN_SIZE`/`CHAR_OCTET_LENGTH` qua metadata.
2. Xác định quy tắc **độ dài ký tự** của DBMS/cột (ký tự, byte hay đơn vị khác), cùng encoding thực tế.
3. Nếu ứng dụng chuẩn hóa Unicode, chuẩn hóa **trước khi đo**.
4. Đo số ký tự và số byte theo quy tắc đã xác minh; không coi Java `String.length()` là byte hoặc code point.
5. Chặn payload rõ ràng vượt giới hạn đã biết; đưa dữ liệu qua `PreparedStatement` để DBMS kiểm tra cuối cùng.
6. Xử lý `SQLException` có thể phát sinh vì charset, giới hạn byte/row, constraint hoặc lỗi tài nguyên.

### Mẫu kiểm tra trước đối với cột UTF-8 tính chiều dài theo ký tự

Đoạn sau áp dụng trong tình huống **đã xác minh** cột văn bản có giới hạn số Unicode code point và charset mã hóa dùng để đánh giá byte là UTF-8. Đây là kiểm tra sớm, **không thay thế** ràng buộc của DBMS và không phải quy tắc chung cho mọi DBMS.

~~~java
import java.nio.charset.CharacterCodingException;
import java.nio.charset.StandardCharsets;

public final class TitleValidator {
    private TitleValidator() {}

    public static void validate(
            String title,
            Integer maxCodePoints,
            Integer maxEncodedBytes
    ) throws CharacterCodingException {
        if (title == null) {
            throw new IllegalArgumentException("title không được null");
        }

        int codePoints =
            title.codePointCount(0, title.length());

        if (maxCodePoints != null && maxCodePoints > 0
                && codePoints > maxCodePoints) {
            throw new IllegalArgumentException(
                "title vượt quá số ký tự cho phép"
            );
        }

        byte[] utf8 = StrictEncoding.encode(
            title, StandardCharsets.UTF_8
        );

        if (maxEncodedBytes != null && maxEncodedBytes > 0
                && utf8.length > maxEncodedBytes) {
            throw new IllegalArgumentException(
                "title vượt quá giới hạn byte"
            );
        }
    }
}
~~~

Có thể dùng `ColumnSizeInspector.findTitle(...)` để lấy các giới hạn được công bố, **sau khi** đã xác minh chúng phù hợp với ngữ nghĩa của cột. Đừng đơn giản gán mọi `COLUMN_SIZE` thành `maxCodePoints`: ví dụ có DBMS cho phép khai báo `VARCHAR2(100 BYTE)` hoặc dùng ngữ nghĩa đặc thù.

Trong Java, `codePointCount` cũng chưa chắc bằng số **grapheme clusters**; điều này quan trọng khi giao diện đặt giới hạn “số ký tự người dùng nhìn thấy”. Nếu kiểm tra giao diện theo grapheme, cần thuật toán phân đoạn Unicode thích hợp; cơ sở dữ liệu có thể đo theo quy tắc khác. Hai lớp giới hạn nên được mô tả riêng trong hợp đồng sản phẩm.

### Ví dụ đo bằng SQL trên DBMS cụ thể

Với PostgreSQL, khi chuỗi được biểu diễn ở kiểu `text` và server dùng UTF-8, có thể so sánh:

~~~sql
SELECT
    char_length(?::text) AS characters,
    octet_length(?::text) AS bytes;
~~~

Truyền **cùng giá trị** cho cả hai placeholder bằng `PreparedStatement.setString()`. `char_length` trả số ký tự theo cách DBMS hiểu; `octet_length` trả số byte của biểu diễn text mà DBMS sử dụng.

Trên MySQL, ví dụ tương đương thường là:

~~~sql
SELECT CHAR_LENGTH(?) AS characters,
       LENGTH(?) AS bytes;
~~~

`LENGTH` trong MySQL trả số byte, nhưng ở DBMS khác nó có thể mang nghĩa khác. **Không coi các hàm này là SQL portable một cách tuyệt đối.** Sử dụng ví dụ đúng hệ quản trị thực tế, tính đến connection/server charset và collation.

## 6. Truyền văn bản lớn bằng `Reader` và `setCharacterStream()`

Với vài MB hoặc GB văn bản, cách sau có thể gây áp lực lớn lên heap:

~~~java
String wholeFile = Files.readString(path, StandardCharsets.UTF_8);
preparedStatement.setString(2, wholeFile);
~~~

`Files.readString` tạo một chuỗi chứa toàn bộ nội dung. Nếu vừa giữ byte đầu vào, vừa tạo `String`, vừa mã hóa lại thành byte cho driver, bộ nhớ đỉnh có thể lớn hơn nhiều lần kích thước tệp ban đầu.

Khi cột/driver hỗ trợ truyền dữ liệu theo luồng, ưu tiên `setCharacterStream()`:

~~~java
import javax.sql.DataSource;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public final class LargeTextWriter {
    public static void save(
            DataSource source, long documentId, Path utf8File
    ) throws Exception {
        // Giải mã UTF-8 nghiêm ngặt; dữ liệu sai mã gây lỗi đọc.
        var decoder = StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT);

        try (Connection conn = source.getConnection();
             Reader text = new InputStreamReader(
                 Files.newInputStream(utf8File), decoder);
             PreparedStatement ps = conn.prepareStatement(
                 "INSERT INTO documents (id, body) VALUES (?, ?)")) {

            ps.setLong(1, documentId);
            ps.setCharacterStream(2, text); // JDBC 4+, không khai báo length.
            if (ps.executeUpdate() != 1) {
                throw new SQLException(
                    "Không thêm được đúng một tài liệu"
                );
            }
        }
    }
}
~~~

Trong ví dụ, cột `documents.body` phải là kiểu văn bản đủ lớn và phù hợp với DBMS đang dùng (ví dụ kiểu CLOB hoặc kiểu text có khả năng lưu nội dung lớn). Cú pháp DDL của kiểu này không hoàn toàn đồng nhất giữa các DBMS.

**Cần hiểu giới hạn của streaming:**

- `setCharacterStream(index, Reader)` là overload JDBC hỗ trợ truyền độ dài chưa biết, nhưng **một số driver hoặc phiên bản DBMS có thể hạn chế hỗ trợ** và có thể buffer nội dung phía client. Kiểm tra hành vi và memory thực tế.
- Overload `setCharacterStream(index, Reader, long length)` nhận **độ dài theo ký tự mà Reader cung cấp**, không phải số byte của file. Không đưa `Files.size(path)` vào đối số `length` khi văn bản có UTF-8 nhiều byte; dữ liệu có thể bị cắt cụt hoặc gây lỗi.
- Nếu driver bắt buộc biết length, cần xác định chính xác số ký tự theo hợp đồng API/driver, hoặc có chiến lược đếm trước bằng một lượt đọc; đừng dùng ước lượng byte.
- `Reader` phải còn mở trong suốt lúc driver cần tiêu thụ stream. Không đóng Reader ngay sau `setCharacterStream()` rồi mới gọi `executeUpdate()`.
- Nếu driver/DBMS không hỗ trợ stream không độ dài hoặc giới hạn LOB, cần chọn API/tính năng tương thích và tài liệu của driver.

### Đọc văn bản lớn qua `getCharacterStream()`

~~~java
import java.io.Reader;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

static void exportText(
        Connection conn, long documentId, Path output
) throws Exception {
    String sql = "SELECT body FROM documents WHERE id = ?";

    try (PreparedStatement ps = conn.prepareStatement(sql)) {
        ps.setLong(1, documentId);

        try (ResultSet rs = ps.executeQuery()) {
            if (!rs.next()) {
                throw new IllegalArgumentException(
                    "Không tìm thấy document"
                );
            }

            try (Reader in = rs.getCharacterStream("body");
                 Writer out = Files.newBufferedWriter(
                     output, StandardCharsets.UTF_8)) {
                if (in == null) {
                    throw new IllegalStateException("body là SQL NULL");
                }
                in.transferTo(out);
            }
        }
    }
}
~~~

`getCharacterStream()` trả một `Reader` cho văn bản, giúp xử lý theo luồng khi driver hỗ trợ. Đọc trước khi đóng `ResultSet`, `PreparedStatement` và `Connection`. Với một số driver, cần giữ transaction mở khi đang đọc LOB; điều này phụ thuộc DBMS và cách triển khai LOB locator.

**Không đồng nhất streaming API với cam kết “không bao giờ dùng nhiều bộ nhớ”:** Driver vẫn có thể buffer. Cần kiểm tra memory, thời gian, giới hạn driver và kích thước thực tế. Khi xuất dữ liệu ra file, nếu có lỗi giữa chừng, file đích có thể chỉ chứa một phần: nên ghi ra file tạm và đổi tên sau khi hoàn tất khi nghiệp vụ yêu cầu kết quả nguyên vẹn.

## 7. Dữ liệu nhị phân lớn: dùng `InputStream`, không chuyển sang `String`

Với PDF, ảnh, ZIP hoặc tệp media:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

static void saveBinary(
        Connection conn, long fileId, Path file
) throws Exception {
    long sizeInBytes = Files.size(file);

    try (InputStream in = Files.newInputStream(file);
         PreparedStatement ps = conn.prepareStatement(
             "INSERT INTO binary_files (id, payload) VALUES (?, ?)")) {

        ps.setLong(1, fileId);
        ps.setBinaryStream(2, in, sizeInBytes);

        if (ps.executeUpdate() != 1) {
            throw new SQLException("Không lưu được file");
        }
    }
}
~~~

`setBinaryStream(index, stream, long length)` nhận **số byte**, khác `setCharacterStream` nhận độ dài tính theo ký tự. Với file nguồn không được sửa trong lúc truyền, `Files.size` phù hợp làm độ dài byte; nếu tệp thay đổi trong khi đọc, driver có thể báo lỗi hoặc dữ liệu không còn nhất quán. Bảo đảm snapshot nguồn ổn định khi cần.

Truy vấn ngược:

~~~java
try (ResultSet rs = ps.executeQuery()) {
    if (rs.next()) {
        try (InputStream in = rs.getBinaryStream("payload")) {
            if (in != null) {
                Files.copy(in, outputPath);
            }
        }
    }
}
~~~

Đoạn xuất trên giả định `ps` đã được tạo và thực thi trước đó, và `outputPath` là đường dẫn được ứng dụng kiểm soát. `Files.copy` có thể báo lỗi nếu file đích đã tồn tại; xử lý thay thế/ghi tạm theo chính sách ứng dụng.

**Khi nào dùng gì?**

| Kiểu nội dung | JDBC ghi | JDBC đọc | Chuyển charset? |
| --- | --- | --- | --- |
| `VARCHAR` ngắn | `setString` | `getString` | Driver/DBMS xử lý theo kiểu text |
| `CLOB` hoặc văn bản rất lớn | `setCharacterStream`, `setClob` khi hỗ trợ | `getCharacterStream`, `getClob` | Có, nếu nguồn/đích là văn bản |
| `BLOB` hoặc tệp binary | `setBinaryStream`, `setBlob` khi hỗ trợ | `getBinaryStream`, `getBlob` | **Không** |
| Mảng byte nhỏ | `setBytes` | `getBytes` | Không, trừ khi nghiệp vụ cố ý giải mã |
| `NVARCHAR`/`NCLOB` | `setNString`/`setNCharacterStream` khi driver hỗ trợ | `getNString`/`getNCharacterStream` | Theo ngữ nghĩa kiểu quốc gia và DBMS |

Một số DBMS dùng kiểu text lớn thay cho `CLOB` và không hỗ trợ toàn bộ API National Character Set (`N*`). Tránh giả định rằng `Types.NVARCHAR` hoặc `setNString` khả dụng ở mọi driver.

## 8. Nhận diện lỗi kích thước, lỗi bảng mã và cắt cụt

Những lỗi thường gặp gồm:

| Hiện tượng | Nguyên nhân khả dĩ | Hướng điều tra |
| --- | --- | --- |
| `SQLException` khi ghi chuỗi dài | Vượt giới hạn cột, hàng, packet, tham số hoặc tài nguyên | So sánh kích thước và metadata; xem SQLState và vendor code |
| Chuỗi bị cắt cụt | Driver/DBMS có chính sách truncation hoặc API giới hạn kết quả | Kiểm tra update count, warning, dữ liệu đọc lại và cấu hình |
| Văn bản thành `�` hoặc `?` | Charset sai, ký tự không biểu diễn được, chuyển mã theo chính sách thay thế | Kiểm tra byte nguồn, đường giải mã và charset kết nối/DBMS |
| Emoji lưu lỗi | Bộ mã không biểu diễn được hoặc giới hạn byte bị vượt | Xác minh charset cột/kết nối, chiều dài byte |
| `OutOfMemoryError` | Đưa LOB lớn vào `byte[]`/`String`, driver buffer quá nhiều | Sử dụng streaming/chunking, đo heap và driver behavior |
| Dữ liệu nhị phân đọc lại khác | Đã chuyển thành `String` hoặc xử lý text/binary nhầm | Dùng binary stream, so checksum và kích thước |
| Lỗi giữa lúc đọc stream | Timeout, lỗi mạng, lỗi decoder hoặc connection/transaction đóng sớm | Quản lý vòng đời stream/connection và retry an toàn |

### SQLState và cảnh báo

SQLState thuộc lớp `22` thường liên quan **data exception**, với ví dụ theo quy ước SQL:

- `22001`: dữ liệu chuỗi vượt độ dài/cắt cụt khi ghi.
- `22021`: ký tự không thuộc tập ký tự cho phép (*character not in repertoire*).
- `22003`: giá trị số ngoài phạm vi (không phải lỗi bảng mã, nhưng thường gặp khi chuyển kiểu dữ liệu).

Driver không nhất thiết trả cùng mã cho mọi loại lỗi. Cũng có DBMS báo mã riêng hoặc thay thế dữ liệu theo chế độ cấu hình. Vì vậy, kiểm tra `getSQLState()`, `getErrorCode()` và chuỗi ngoại lệ thay vì chỉ dò một thông báo lỗi bằng chuỗi.

~~~java
import java.sql.SQLException;
import java.sql.SQLWarning;
import java.sql.PreparedStatement;

static void reportWriteIssues(
        PreparedStatement ps, SQLException error
) throws SQLException {
    if (error != null) {
        for (SQLException current = error;
             current != null;
             current = current.getNextException()) {
            System.err.println(
                "SQLState=" + current.getSQLState()
                + ", vendorCode=" + current.getErrorCode()
            );
        }
    }

    for (SQLWarning warning = ps.getWarnings();
         warning != null;
         warning = warning.getNextWarning()) {
        System.err.println(
            "JDBC warning: " + warning.getSQLState()
        );
    }
}
~~~

Ví dụ này minh họa cách đọc cảnh báo khi statement còn mở; nếu statement không còn khả dụng sau lỗi nghiêm trọng, lời gọi `getWarnings()` cũng có thể ném ngoại lệ. Không bỏ qua lỗi gốc hoặc cố tiếp tục transaction đã thất bại.

**Không được xem `executeUpdate() == 1` là bảo đảm mọi byte được bảo toàn.** Nếu DBMS/driver có chế độ chuyển mã thay thế hoặc truncation được chấp nhận, câu lệnh có thể ảnh hưởng một hàng nhưng nội dung đã thay đổi. Với dữ liệu cần độ tin cậy cao, hãy kiểm tra round-trip và checksum theo đúng đơn vị (bytes cho binary, văn bản đã chuẩn hóa theo chính sách rõ ràng cho text).

## 9. Batch, transaction và giới hạn bộ nhớ khi ghi dữ liệu lớn

Batch tăng thông lượng với nhiều câu `INSERT`/`UPDATE` nhưng có thể giữ nhiều bộ tham số trong bộ nhớ. Nếu mỗi tham số chứa một LOB 20 MB và bạn thêm 500 lần vào batch, driver có thể phải giữ dữ liệu rất lớn dù SQL tham số hóa.

Những nguyên tắc hữu ích:

1. **Không gom mọi payload lớn vào `List<byte[]>` hoặc `List<String>`** trước khi ghi nếu có thể đọc theo stream.
2. Chọn batch size theo **tổng số byte và đặc tính driver**, không chỉ số bản ghi.
3. Đừng giả định `addBatch()` với stream được driver đọc ngay; vòng đời stream, thứ tự đọc và khả năng lưu lại/thi hành lại phụ thuộc driver. Kiểm tra tính tương thích hoặc ghi LOB từng bản ghi nếu cần.
4. Nếu yêu cầu một nhóm bản ghi **cùng thành công hoặc cùng thất bại**, chạy trong transaction thích hợp với `autoCommit = false`, kiểm tra kết quả và rollback khi có lỗi.
5. **Chunk size** (số lệnh mỗi lần gửi) và **transaction size** (số lệnh giữa commit/rollback) là hai khái niệm khác nhau.
6. Với import cực lớn và có thể chấp nhận phần đã lưu, commit theo chunk và ghi checkpoint/idempotency. Chunk đã commit **không** thể bị rollback bởi transaction sau.
7. Không giữ connection/transaction mở trong lúc chờ người dùng hoặc gọi dịch vụ ngoài chậm.

Đối với `ResultSet` lớn, `Statement.setFetchSize()` là **gợi ý số hàng mỗi đợt fetch**, không phải giới hạn byte của từng giá trị. `setMaxRows()` giới hạn số hàng, không giải quyết việc một hàng chứa BLOB cực lớn. `setMaxFieldSize()` là API riêng có thể giới hạn byte dữ liệu trả về cho một số kiểu trường, có nguy cơ cắt nội dung: **không sử dụng để “tối ưu” khi yêu cầu bảo toàn toàn bộ LOB**.

### Lưu ý transaction khi stream LOB

Một số driver/DBMS dùng LOB locator gắn với transaction. Nếu gọi `commit()` hoặc đóng connection trước khi đọc hết stream, việc đọc có thể lỗi. Giữ `ResultSet` và tài nguyên liên quan mở trong thời gian tiêu thụ stream, theo tài liệu driver và chính sách transaction.

Nếu commit trả `SQLException` do mất kết nối, ứng dụng có thể **không biết server đã commit hay chưa**. Với ghi file lớn, cần khóa idempotency, định danh upload và đối soát trạng thái trước khi retry, tránh nhân đôi dữ liệu hoặc tạo bản ghi tham chiếu mồ côi.

## 10. Ví dụ tổng hợp: nhập tên và tài liệu có tiếng Việt

Bài toán: lưu tên tài liệu vào cột `title` và nội dung vào cột text lớn `body`. Tệp đầu vào được tuyên bố là UTF-8.

~~~mermaid
flowchart TD
    A["Nhận request + file UTF-8"] --> B["Xác minh kích thước request/file"]
    B --> C["Giải mã tên và text bằng charset đã xác nhận"]
    C --> D["Chuẩn hóa Unicode theo quy tắc nghiệp vụ (nếu có)"]
    D --> E["Đọc metadata và kiểm tra giới hạn title"]
    E --> F{"Dữ liệu hợp lệ?"}
    F -- "Không" --> G["Báo lỗi kích thước hoặc charset"]
    F -- "Có" --> H["PreparedStatement setString(title)"]
    H --> I["setCharacterStream(body)"]
    I --> J["Thực thi trong transaction phù hợp"]
    J --> K{"SQL và commit thành công?"}
    K -- "Có" --> L["Trả kết quả thành công"]
    K -- "Không" --> M["Rollback khi có thể; đối soát nếu commit chưa rõ"]
~~~

Một triển khai có thể chia thành các bước:

**Bước 1 — kiểm tra giới hạn tầng ứng dụng.** Không đọc tệp nhiều GB vào bộ nhớ để kiểm tra. Dùng kích thước tệp hoặc bộ đếm byte trong luồng, giới hạn phù hợp với nhu cầu sản phẩm; chặn sớm khi vượt mức chấp nhận.

**Bước 2 — đọc charset nguồn.** Chọn UTF-8 vì hợp đồng request/tệp quy định. Dùng decoder `REPORT` để biết ngay khi byte không hợp lệ, tránh lưu text bị thay thế.

**Bước 3 — kiểm tra tên.** Lấy metadata cột `title`, kiểm tra độ dài theo ngữ nghĩa xác minh của DBMS, kiểm tra encoding nếu có yêu cầu chuyển sang charset đích không Unicode. Nếu chuẩn hóa `NFC`, thực hiện trước khi đo và lưu.

**Bước 4 — ghi vào DB.** `setString()` cho tiêu đề ngắn; `setCharacterStream()` cho body lớn. Driver/DBMS chịu trách nhiệm kiểm tra constraint cuối cùng. Dùng transaction nếu còn những bước liên quan cần tính nguyên tử, chẳng hạn ghi metadata file và liên kết đến bản ghi upload.

**Bước 5 — xác minh và xử lý lỗi.** Theo dõi SQLState/vendor code, số bản ghi được cập nhật, trường hợp rollback lỗi và kết quả commit chưa xác định. Với nội dung nhị phân, so checksum bytes để bảo đảm không thay đổi khi lưu/đọc lại.

Tối ưu hiệu năng bằng cách đo memory, số byte, throughput, thời gian SQL và timeout trên bộ dữ liệu gần thực tế. Không tự suy đoán rằng dùng stream API đồng nghĩa driver hoàn toàn không buffer.

## 11. Các lỗi triển khai dễ gặp

| Sai lầm | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Dùng `String.length()` làm số byte UTF-8 | Bỏ qua trường hợp Unicode nhiều byte | Đo byte theo charset thực tế |
| Dùng `String.length()` làm số ký tự hiển thị | Emoji/surrogate/combining mark bị đếm sai | Chọn quy tắc code point hoặc grapheme đúng nghiệp vụ |
| Lấy `COLUMN_SIZE` luôn làm số byte | Sai với cột tính độ dài theo ký tự | Phân biệt metadata ký tự/byte và quy tắc DBMS |
| Coi `CHAR_OCTET_LENGTH` là giới hạn packet | Metadata cột không mô tả toàn bộ giao thức | Đọc cấu hình driver/server, đo payload |
| Coi `getMax...() = 0` là cấm dữ liệu | Từ chối mọi dữ liệu hợp lệ | Hiểu là không giới hạn hoặc chưa rõ |
| Gọi `new String(bytes)` không chỉ rõ charset | Dữ liệu phụ thuộc default charset và dễ mojibake | Dùng decoder với charset đã xác minh |
| Đổi `BLOB` sang `String` để lưu | Làm hỏng bytes tùy ý | Dùng `setBinaryStream()`/`getBinaryStream()` |
| Dùng `getBytes()` thuận tiện cho text không thể biểu diễn | Có thể thay ký tự âm thầm | Dùng `CharsetEncoder` với `REPORT` |
| Dùng `Files.size()` làm length cho `setCharacterStream()` | Byte UTF-8 khác số ký tự | Dùng overload không length hoặc đếm đúng ký tự |
| Dùng `setString()` với file vài GB | Rủi ro heap/driver buffer | Dùng `Reader` và stream, xác minh hỗ trợ |
| Đóng `Reader` trước `executeUpdate()` | Driver không còn nguồn dữ liệu khi tiêu thụ | Giữ stream mở suốt lần execute |
| Dùng `setFetchSize()` để giới hạn kích thước BLOB | Đây là gợi ý số hàng, không phải byte/LOB | Dùng stream và giới hạn payload riêng |
| Gặp SQLState `22001` mà retry vô hạn | Dữ liệu vẫn vượt giới hạn | Sửa dữ liệu hoặc schema, không retry mù |
| Giả định cột/driver luôn dùng UTF-8 | Có thể lỗi chuyển mã hoặc thay ký tự | Xác minh charset kết nối, server, cột |
| Không đối soát sau lỗi `commit()` | Có thể ghi trùng dữ liệu khi retry | Dùng idempotency và kiểm tra trạng thái |

## 12. Tình huống tự kiểm tra

**Tình huống A.** `String s = "A😀";`. Có thể dùng `s.length() == 3` để khẳng định chuỗi có ba Unicode code point không?

**Đáp án:** Không. `length()` trả ba UTF-16 code units. Chuỗi này có **hai code point** và **năm byte UTF-8**.

**Tình huống B.** Tên tài liệu dài 100 code points nhưng khi mã hóa UTF-8 chiếm 280 byte. Cột được khai báo giới hạn 100 ký tự. Có chắc câu `INSERT` sẽ thành công không?

**Đáp án:** Chưa chắc. Cần xác minh cột thực sự dùng ngữ nghĩa ký tự hay byte, charset, giới hạn byte của cột/hàng và các ràng buộc khác. Số code points chỉ là một lớp kiểm tra.

**Tình huống C.** `DatabaseMetaData.getMaxCharLiteralLength()` trả `0`. Có nghĩa không được dùng `setString()` không?

**Đáp án:** Không. `0` thường nghĩa không giới hạn hoặc không xác định; hơn nữa giới hạn literal SQL không tương đương giới hạn tham số `?` của `PreparedStatement`.

**Tình huống D.** File UTF-8 1.000.000 byte được truyền vào `setCharacterStream(index, reader, 1_000_000L)`. Điều này có đúng không?

**Đáp án:** Không chắc và thường sai khi có ký tự nhiều byte. `length` của character stream tính theo ký tự mà Reader cung cấp, không phải byte của file. Dùng overload không length nếu driver hỗ trợ, hoặc đếm đúng theo hợp đồng API.

**Tình huống E.** Một ảnh PNG đã được đọc thành `byte[]`. Bạn giải mã nó bằng UTF-8 trước khi ghi vào BLOB, rồi đọc lại không còn mở được. Nguyên nhân?

**Đáp án:** Ảnh là dữ liệu nhị phân; giải mã rồi mã hóa text có thể thay bytes. Dùng binary APIs để giữ nguyên byte.

**Tình huống F.** Một tệp khai báo UTF-8 nhưng chứa byte lỗi. `new String(bytes, UTF_8)` vẫn trả chuỗi có ký tự thay thế. Làm sao biết dữ liệu nguồn đã lỗi?

**Đáp án:** Dùng `CharsetDecoder` với `CodingErrorAction.REPORT` hoặc `InputStreamReader` dùng decoder nghiêm ngặt; khi đó lỗi giải mã sẽ được báo thay vì tự thay ký tự.

**Tình huống G.** Sau khi ghi document bằng stream, driver thông báo thành công nhưng khi đọc lại nội dung thiếu phần cuối. Những nguyên nhân nào cần kiểm tra?

**Đáp án:** Kiểm tra length truyền vào API, vòng đời stream, kích thước/giới hạn của cột, cảnh báo cắt cụt, hành vi driver buffering và charset chuyển đổi; đối chiếu dữ liệu đọc lại theo đơn vị phù hợp.

**Tình huống H.** Một JDBC batch có 100 dòng, mỗi dòng chứa BLOB 30 MB. `setFetchSize(100)` có giải quyết được vấn đề memory của batch không?

**Đáp án:** Không. `setFetchSize()` là gợi ý lấy **hàng kết quả**, không điều khiển việc buffer BLOB đầu vào. Cần giảm batch size, stream binary và xác minh driver thực thi.

**Tình huống I.** Hai chuỗi `é` và `e\u0301` trông giống nhau nhưng có byte UTF-8 khác nhau. Đây có nhất thiết là lỗi JDBC không?

**Đáp án:** Không. Chúng có thể là hai dạng chuẩn hóa Unicode khác nhau. Nếu nghiệp vụ muốn coi chúng tương đương, định nghĩa chính sách normalization và áp dụng nhất quán trước khi so sánh/ghi.

## Ghi nhớ

- **Đếm đúng đơn vị:** Java `String.length()` là số UTF-16 code units; số code points, grapheme clusters và số byte theo charset là những đại lượng khác nhau.
- **Kết hợp metadata với quy tắc DBMS:** `COLUMN_SIZE`, `CHAR_OCTET_LENGTH` và `getMax...()` giúp khám phá giới hạn, nhưng không thay thế xác minh charset, row size, packet và cột thực tế.
- **Luôn nêu rõ charset nguồn/đích khi chuyển mã.** Dùng `CharsetEncoder`/`CharsetDecoder` với `REPORT` nếu dữ liệu không được phép mất ký tự.
- **Text và binary phải đi theo đường API phù hợp:** `setString`/`setCharacterStream` cho văn bản; `setBytes`/`setBinaryStream` cho byte nhị phân.
- **Với LOB lớn, ưu tiên xử lý theo luồng**, quản lý vòng đời `Reader`/`InputStream`, `ResultSet` và connection; kiểm tra khả năng driver buffer dữ liệu.
- **Giới hạn cột khác giới hạn truyền/heap/transaction.** Theo dõi SQLState, vendor code, warning và đối soát nội dung; không retry mù khi kết quả commit chưa chắc chắn.
