# Phân biệt độ dài ký tự và kích thước byte của cột

## 1. Vì sao một chuỗi ngắn vẫn có thể vượt giới hạn cột?

Khi dùng **JDBC** để ghi văn bản từ Java vào cơ sở dữ liệu quan hệ, một chuỗi có thể hợp lệ theo giới hạn **số ký tự** nhưng vẫn vượt giới hạn **số byte**; ngược lại, có hệ quản trị cơ sở dữ liệu diễn giải độ dài khai báo của cột theo byte ngay từ đầu.

Ví dụ, cả hai chuỗi sau đều gồm bốn ký tự Unicode nhưng chiếm số byte khác nhau khi mã hóa UTF-8:

| Giá trị | Số ký tự Unicode | Số byte UTF-8 |
| --- | ---: | ---: |
| `"ABCD"` | 4 | 4 |
| `"😀😀😀😀"` | 4 | 16 |

Nếu ứng dụng chỉ kiểm tra `text.length() <= 4`, kết luận càng dễ sai: trong Java, một emoji như `😀` thường chiếm **hai đơn vị mã UTF-16**, dù chỉ là **một code point Unicode** và chiếm **bốn byte UTF-8**.

Để chọn đúng kiểu cột, kiểm tra dữ liệu trước khi ghi và giải thích lỗi phát sinh qua `PreparedStatement`, cần phân biệt ít nhất ba đại lượng:

1. **Độ dài Java `String`:** số đơn vị mã UTF-16.
2. **Số ký tự Unicode/code point:** số mã Unicode trong chuỗi, khác với số “ký tự người nhìn thấy”.
3. **Số byte:** số đơn vị lưu trữ sau khi chuỗi được mã hóa bằng một bảng mã cụ thể, chẳng hạn UTF-8.

Ba con số này thường trùng nhau với ASCII nhưng không thể mặc định luôn bằng nhau.

## 2. Hiểu đúng các đơn vị đếm của văn bản

### 2.1. UTF-16, code point và cụm ký tự

Java lưu nội dung `String` theo các đơn vị mã UTF-16. Phương thức `String.length()` trả về **số đơn vị mã UTF-16**, không nhất thiết là số ký tự người đọc nhìn thấy.

Đối với chuỗi Unicode hợp lệ:

- Ký tự ASCII `A`: 1 đơn vị UTF-16, 1 code point, 1 byte UTF-8.
- Chữ `Đ`: 1 đơn vị UTF-16, 1 code point, 2 byte UTF-8.
- Chữ Hán `你`: 1 đơn vị UTF-16, 1 code point, 3 byte UTF-8.
- Emoji `😀` (U+1F600): 2 đơn vị UTF-16, 1 code point, 4 byte UTF-8.
- `e` + dấu sắc kết hợp U+0301 (`é`): 2 đơn vị UTF-16, **2 code point**, 3 byte UTF-8; người dùng thường nhìn thấy **một** chữ.

| Chuỗi | `String.length()` | Code point | Byte UTF-8 | Số cụm ký tự nhìn thấy (thông thường) |
| --- | ---: | ---: | ---: | ---: |
| `"A"` | 1 | 1 | 1 | 1 |
| `"Đ"` | 1 | 1 | 2 | 1 |
| `"你"` | 1 | 1 | 3 | 1 |
| `"😀"` | 2 | 1 | 4 | 1 |
| `"e\u0301"` | 2 | 2 | 3 | 1 |

*Code point* là một giá trị mã Unicode. *Grapheme cluster* (cụm ký tự) là đơn vị mà người đọc thường xem như một ký tự; một cụm có thể chứa nhiều code point, chẳng hạn emoji có ký tự nối, biến thể màu da hoặc chuỗi chữ có dấu kết hợp. Nếu yêu cầu là “tối đa 20 ký tự người dùng nhìn thấy”, không nên thay việc đếm cụm ký tự bằng `String.length()` hoặc `codePointCount()`. Cần một bộ phân đoạn grapheme theo chuẩn Unicode, chẳng hạn thư viện ICU4J, với phiên bản Unicode phù hợp.

### 2.2. Byte chỉ có ý nghĩa khi xác định bảng mã

Với cùng một chuỗi `"Đ"`, số byte tùy thuộc mã hóa. UTF-8 dùng 2 byte, còn UTF-16 thường dùng 2 byte cho code point này. Do đó, phát biểu “chuỗi này dài 2 byte” phải đi kèm ngữ cảnh **mã hóa nào**.

Trong JDBC, `PreparedStatement.setString(...)` nhận một **chuỗi Java**. Driver và hệ quản trị có thể chuyển đổi ký tự theo giao thức kết nối, charset của cột và charset của cơ sở dữ liệu. Không thể suy ra chính xác dung lượng lưu ở máy chủ chỉ từ `String.length()`.

Thêm nữa, **số byte của giá trị đã mã hóa** không đồng nghĩa với **dung lượng đĩa thực tế của cả hàng dữ liệu**: còn có header hàng, thông tin độ dài, chỉ mục, cơ chế nén và chi phí lưu trữ khác. Nội dung bài này tập trung vào giới hạn cột và độ dài byte của **giá trị văn bản**.

## 3. Ý nghĩa của `VARCHAR(n)` khác nhau giữa các hệ quản trị

Không nên đọc `VARCHAR(20)` thành “chứa tối đa 20 ký tự Unicode” mà chưa biết hệ quản trị và kiểu mã hóa.

| Hệ quản trị / kiểu cột | Ý nghĩa cơ bản của độ dài khai báo | Cách đo liên quan |
| --- | --- | --- |
| **PostgreSQL** `VARCHAR(n)` | `n` ký tự theo ngữ nghĩa ký tự của PostgreSQL; số byte tùy mã hóa cơ sở dữ liệu | `char_length(text)` / `octet_length(text)` |
| **MySQL** `VARCHAR(n)` | `n` ký tự; dung lượng byte thực tế còn phụ thuộc charset như `utf8mb4` và giới hạn hàng | `CHAR_LENGTH(text)` / `LENGTH(text)` |
| **Oracle Database** `VARCHAR2(n BYTE)` | `n` byte | `LENGTH(text)` / `LENGTHB(text)` |
| **Oracle Database** `VARCHAR2(n CHAR)` | `n` ký tự theo ngữ nghĩa ký tự của Oracle; vẫn chịu các giới hạn byte tổng thể | `LENGTH(text)` / `LENGTHB(text)` |
| **SQL Server** `VARCHAR(n)` | `n` byte; cách biểu diễn ký tự tùy collation và mã hóa | `LEN(text)` / `DATALENGTH(text)` |
| **SQL Server** `NVARCHAR(n)` | `n` **byte-pair** (đơn vị 2 byte) của UTF-16; ký tự bổ sung như emoji thường dùng hai byte-pair | `LEN(text)` / `DATALENGTH(text)` |

Các lưu ý khi diễn giải bảng:

- **PostgreSQL:** với mã hóa máy chủ UTF-8, `VARCHAR(8)` có thể chứa tám emoji đơn lẻ (8 code point, 32 byte UTF-8), nếu không có ràng buộc bổ sung. `VARCHAR(n)` không hứa dung lượng thực tế bằng `n` byte.
- **MySQL:** `utf8mb4` cho phép ký tự UTF-8 dùng tới bốn byte; giới hạn kích thước hàng và các giới hạn nội bộ vẫn có thể khiến việc tạo hoặc ghi cột `VARCHAR` lớn bị từ chối.
- **Oracle:** hãy xem rõ `BYTE` hay `CHAR` trên định nghĩa cột; thiết lập mặc định cho length semantics có thể ảnh hưởng định nghĩa không ghi rõ đơn vị.
- **SQL Server:** `NVARCHAR(8)` **không bảo đảm** lưu được tám emoji: mỗi emoji bổ sung thường chiếm hai đơn vị UTF-16, nên bốn emoji đã sử dụng tám byte-pair. `LEN` cũng có cách xử lý khoảng trắng cuối và ký tự bổ sung tùy collation; nó không phải phép đo byte.

Vì vậy, ví dụ SQL của hệ quản trị này không thể áp dụng nguyên xi cho hệ quản trị khác mà vẫn giữ cùng ngữ nghĩa độ dài.

## 4. Đo độ dài thực tế ngay trong cơ sở dữ liệu

### 4.1. Ví dụ PostgreSQL dùng UTF-8

Xác nhận mã hóa máy chủ trước khi kết luận về byte:

```sql
SHOW server_encoding;
-- Ví dụ kết quả: UTF8
```

Khi `server_encoding` là `UTF8`:

```sql
SELECT
    char_length('ABCD')    AS ascii_characters,
    octet_length('ABCD')   AS ascii_bytes,
    char_length('😀😀😀😀') AS emoji_characters,
    octet_length('😀😀😀😀') AS emoji_bytes;

-- Kết quả:
-- ascii_characters | ascii_bytes | emoji_characters | emoji_bytes
--                 4 |           4 |                4 |          16
```

`char_length` trả về số ký tự; `octet_length` trả về số **octet (byte)** biểu diễn giá trị theo mã hóa của máy chủ. Các hàm này đo **giá trị đang có**, khác với việc đọc ngưỡng cấu hình của cột.

Giả sử nghiệp vụ quy định nhãn có **tối đa 8 code point** và **tối đa 16 byte UTF-8**. Có thể thể hiện cả hai điều kiện bằng schema PostgreSQL:

```sql
CREATE TABLE ui_labels (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    label VARCHAR(8) NOT NULL,
    CONSTRAINT ck_ui_labels_max_bytes
        CHECK (octet_length(label) <= 16)
);
```

Trong ví dụ:

- `'abcdefgh'` có 8 ký tự, 8 byte → **hợp lệ**.
- `'😀😀😀😀'` có 4 ký tự, 16 byte → **hợp lệ**.
- `'😀😀😀😀😀'` có 5 ký tự, 20 byte → **không hợp lệ** do ràng buộc byte.
- `'abcdefghi'` có 9 ký tự, 9 byte → **không hợp lệ** do vượt `VARCHAR(8)`.

Ràng buộc trên dùng UTF-8 của PostgreSQL để thực hiện giới hạn byte; nếu triển khai sang hệ quản trị hoặc encoding khác, phải viết lại theo ngữ nghĩa phù hợp. Một cơ sở dữ liệu cũng có thể tự xử lý khoảng trắng ở cuối trong một số ngữ cảnh ép kiểu; không nên dựa vào việc cột tự cắt hoặc sửa chuỗi như một cơ chế xác thực nghiệp vụ.

Để xem **giới hạn cột theo metadata SQL**, PostgreSQL cung cấp các cột tiêu chuẩn:

```sql
SELECT
    column_name,
    data_type,
    character_maximum_length,
    character_octet_length
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'ui_labels'
  AND column_name = 'label';
```

`character_maximum_length` và `character_octet_length` thể hiện **giới hạn khai báo/khả năng tối đa**, không phải độ dài của từng bản ghi; đồng thời chúng không thay thế ràng buộc `CHECK` tùy chỉnh nói trên.

### 4.2. Ví dụ MySQL

Với cột văn bản dùng charset `utf8mb4`:

```sql
SELECT
    CHAR_LENGTH('😀') AS character_count,
    LENGTH('😀') AS byte_count;
-- Với utf8mb4: 1 và 4
```

Trong MySQL, `LENGTH()` trả về **byte**, không nên dùng thay `CHAR_LENGTH()` khi quy tắc sản phẩm giới hạn **ký tự**. Để áp dụng một giới hạn byte hoặc ký tự, cần kiểm tra phiên bản MySQL và cách thực thi ràng buộc `CHECK`, đồng thời xác nhận charset của cột và phiên kết nối.

## 5. Đo trong Java trước khi gọi JDBC

Java cho phép đo hai đơn vị liên quan đến quy tắc trên:

```java
import java.nio.charset.StandardCharsets;

public class TextSizes {
    public static void main(String[] args) {
        String value = "A😀e\u0301"; // A + emoji + e + dấu sắc kết hợp

        int utf16Units = value.length();
        int codePoints = value.codePointCount(0, value.length());
        int utf8Bytes = value.getBytes(StandardCharsets.UTF_8).length;

        System.out.println(utf16Units); // 5
        System.out.println(codePoints); // 4
        System.out.println(utf8Bytes);  // 8
    }
}
```

Giải thích phép tính byte: `A` chiếm 1 byte, `😀` chiếm 4 byte, `e` chiếm 1 byte và dấu sắc kết hợp U+0301 chiếm 2 byte, tổng cộng **8 byte UTF-8**.

Điểm cần chú ý:

- `String.length()` dùng cho độ dài UTF-16, ví dụ khi làm việc với chỉ số trong `String`; nó không tương đương `char_length` của PostgreSQL.
- `codePointCount(0, value.length())` đếm code point trong một chuỗi UTF-16 hợp lệ. Nếu chuỗi chứa **surrogate lẻ** không hợp lệ, phép đếm này vẫn có thể tính đơn vị đó, còn bộ mã hóa UTF-8 của Java có thể thay thế ký tự không hợp lệ. Cần xác thực Unicode hợp lệ nếu dữ liệu đến từ nguồn không tin cậy và quy tắc byte đòi hỏi tính chính xác.
- `getBytes(StandardCharsets.UTF_8).length` cho số byte trong **UTF-8**. Nó phù hợp để kiểm tra điều kiện byte ở ví dụ PostgreSQL UTF-8, nhưng có thể khác số byte của cột dùng mã hóa hoặc kiểu dữ liệu khác.
- Không sử dụng `value.getBytes()` không truyền charset để kiểm tra giới hạn: charset mặc định có thể khác theo môi trường/JDK và khiến kết quả thiếu ổn định giữa hệ thống.

### Chuẩn hóa Unicode làm thay đổi cả độ dài ký tự lẫn byte

Hai chuỗi có thể nhìn giống nhau nhưng được biểu diễn bằng code point khác nhau:

```java
import java.text.Normalizer;
import java.nio.charset.StandardCharsets;

String decomposed = "e\u0301";             // e + U+0301
String composed = Normalizer.normalize(
        decomposed, Normalizer.Form.NFC); // é

System.out.println(decomposed.codePointCount(0, decomposed.length())); // 2
System.out.println(composed.codePointCount(0, composed.length()));     // 1
System.out.println(decomposed.getBytes(StandardCharsets.UTF_8).length); // 3
System.out.println(composed.getBytes(StandardCharsets.UTF_8).length);   // 2
```

Nếu sản phẩm quy định chuẩn hóa NFC, hãy thực hiện **trước** khi đo và ghi qua JDBC, và nhất quán ở các đường nhập dữ liệu. Không tự động chuẩn hóa hoặc đổi biểu diễn của định danh, mật khẩu hay chuỗi có yêu cầu chính xác từng code point khi chưa có quy tắc nghiệp vụ.

## 6. Ghi và đọc qua `PreparedStatement`, `ResultSet`

Ví dụ sau dùng bảng PostgreSQL `ui_labels` đã tạo ở mục 4.1. `DataSource` được cấu hình sẵn cho cơ sở dữ liệu PostgreSQL dùng UTF-8. Ứng dụng kiểm tra giới hạn trước khi ghi để cung cấp thông báo dễ hiểu, còn cơ sở dữ liệu tiếp tục giữ vai trò xác thực cuối cùng.

```java
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class LabelRepository {
    private final DataSource dataSource;

    public LabelRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void insertLabel(String label) throws SQLException {
        validateLabel(label);

        String sql = "INSERT INTO ui_labels (label) VALUES (?)";
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(sql)) {
            statement.setString(1, label);
            statement.executeUpdate();
        }
    }

    public void inspectLabel(String label) throws SQLException {
        String sql = "SELECT label, char_length(label), octet_length(label) "
                   + "FROM ui_labels WHERE label = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(sql)) {
            statement.setString(1, label);

            try (ResultSet rs = statement.executeQuery()) {
                if (rs.next()) {
                    String loaded = rs.getString(1);
                    int charsInDatabase = rs.getInt(2);
                    int bytesInDatabase = rs.getInt(3);

                    System.out.printf(
                            "Value=%s; chars=%d; bytes=%d; equal=%b%n",
                            loaded, charsInDatabase, bytesInDatabase,
                            label.equals(loaded));
                }
            }
        }
    }

    private static void validateLabel(String label) {
        if (label == null) {
            throw new IllegalArgumentException("Nhãn không được null");
        }

        for (int i = 0; i < label.length(); i++) {
            char unit = label.charAt(i);
            if (Character.isHighSurrogate(unit)) {
                if (i + 1 >= label.length()
                        || !Character.isLowSurrogate(label.charAt(i + 1))) {
                    throw new IllegalArgumentException("UTF-16 không hợp lệ");
                }
                i++; // Đã xác nhận cặp surrogate hợp lệ.
            } else if (Character.isLowSurrogate(unit)) {
                throw new IllegalArgumentException("UTF-16 không hợp lệ");
            }
        }

        int codePoints = label.codePointCount(0, label.length());
        int utf8Bytes = label.getBytes(StandardCharsets.UTF_8).length;
        if (codePoints > 8 || utf8Bytes > 16) {
            throw new IllegalArgumentException(
                    "Nhãn tối đa 8 code point và 16 byte UTF-8");
        }
    }
}
```

Sử dụng khi đã có `dataSource` hợp lệ:

```java
LabelRepository repository = new LabelRepository(dataSource);
repository.insertLabel("A😀e\u0301");
repository.inspectLabel("A😀e\u0301");
// Value=A😀é; chars=4; bytes=8; equal=true
```

Trong ứng dụng thực tế, nên trả về một đối tượng chứa các số đo thay vì in ra màn hình; ví dụ sử dụng `System.out.printf` để người học nhìn rõ sự khác nhau. Các hàm `char_length` và `octet_length` ở truy vấn là hàm PostgreSQL; khi đổi DBMS, truy vấn phải tương ứng với hệ quản trị đó.

**Vai trò của từng API JDBC:**

1. `Connection` từ `DataSource` mở một phiên làm việc với DBMS. Charset và driver của kết nối ảnh hưởng việc chuyển đổi chuỗi.
2. `PreparedStatement.setString(1, label)` truyền giá trị dạng tham số, tránh ghép nối SQL và giữ nội dung văn bản theo hợp đồng driver/cột.
3. `executeUpdate()` thực thi lệnh ghi; nếu vượt giới hạn cột hoặc `CHECK`, DBMS phát sinh `SQLException`.
4. `ResultSet.getString(1)` đọc chính giá trị văn bản; `getInt(2)` và `getInt(3)` đọc hai **kết quả đếm** vốn là số nguyên. Không chuyển cột `label` sang kiểu số.
5. `try-with-resources` đóng `ResultSet`, `PreparedStatement` và `Connection` đúng cách, kể cả khi có lỗi.

Khi gặp `SQLException`, cần ghi lại mã `SQLState` và loại ràng buộc bị vi phạm, rồi chuyển thành lỗi nghiệp vụ phù hợp. Một số DBMS trả SQLState `22001` khi chuỗi vượt kích thước cột, trong khi vi phạm `CHECK` là lỗi khác; chi tiết thông điệp và ngoại lệ có thể khác theo driver/DBMS. Không nên tự ý cắt chuỗi để ghi lại vì có thể làm sai nội dung người dùng gửi.

## 7. Đọc metadata cột qua JDBC: đừng nhầm kích thước tối đa với dữ liệu thực

`DatabaseMetaData.getColumns(...)` có thể cho biết giới hạn được công bố của cột. Với cột văn bản, hai trường thường cần xem là:

- `COLUMN_SIZE`: kích thước cột được driver báo cáo; với kiểu văn bản thường là **độ dài theo ký tự**.
- `CHAR_OCTET_LENGTH`: số byte tối đa của kiểu cột ký tự nếu metadata hỗ trợ; kết quả có thể là `NULL` hoặc phụ thuộc driver/kiểu cột.

Ví dụ:

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.ResultSet;
import javax.sql.DataSource;

public final class LabelMetadataInspector {
    public static void printLabelColumnMetadata(DataSource ds)
            throws Exception {
        try (Connection connection = ds.getConnection()) {
            DatabaseMetaData metadata = connection.getMetaData();

            try (ResultSet columns = metadata.getColumns(
                    null, "public", "ui_labels", "label")) {
                while (columns.next()) {
                    System.out.println(
                            "COLUMN_SIZE=" + columns.getInt("COLUMN_SIZE"));
                    Object octets =
                            columns.getObject("CHAR_OCTET_LENGTH");
                    System.out.println("CHAR_OCTET_LENGTH=" + octets);
                }
            }
        }
    }
}
```

**Không dùng** `ResultSetMetaData.getColumnDisplaySize(...)` làm giới hạn byte cho đầu vào: nó mô tả kích thước hiển thị được báo cáo, không bảo đảm số byte lưu trữ. `getPrecision(...)` và `COLUMN_SIZE` cũng không thay được phép đo byte thực tế của giá trị.

Đặc biệt, với `ui_labels`, `VARCHAR(8)` là giới hạn độ dài văn bản nhưng ràng buộc `CHECK (octet_length(label) <= 16)` đặt thêm giới hạn byte: metadata cột thông thường có thể **không cho thấy** điều kiện `CHECK` này. Muốn kiểm tra đầy đủ phải đọc schema/ràng buộc hoặc thử ghi qua cơ sở dữ liệu.

## 8. Những lỗi thiết kế và xử lý thường gặp

| Tình huống | Sai lầm | Cách xử lý |
| --- | --- | --- |
| Dùng `name.length() <= 10` để bảo đảm vừa 10 ký tự Unicode | `length()` đo UTF-16, emoji chiếm hai đơn vị | Làm rõ ngữ nghĩa “ký tự”, dùng code point hoặc grapheme tùy yêu cầu |
| Dùng `String.getBytes(UTF_8).length` để kiểm tra cột `NVARCHAR` SQL Server | Độ dài byte UTF-8 không phản ánh số byte-pair UTF-16 của cột | Kiểm tra theo ngữ nghĩa cột và metadata SQL Server |
| Tưởng `VARCHAR(20)` luôn là 20 byte | Không đúng trên PostgreSQL và MySQL với mã hóa nhiều byte | Xác nhận DBMS, charset, semantics và ngưỡng kích thước |
| Dùng `LENGTH()` ở mọi DBMS như nhau | PostgreSQL và MySQL cho ngữ nghĩa khác với nhiều trường hợp; Oracle, SQL Server có hàm riêng | Chọn hàm đo ký tự và byte tương ứng từng DBMS |
| Trả lỗi ngay khi thấy `byteLength > n` với `VARCHAR(n)` PostgreSQL | `n` là giới hạn ký tự, không phải byte | Kiểm tra số ký tự; áp dụng thêm giới hạn byte nếu nghiệp vụ cần |
| Chỉ kiểm tra dữ liệu ở Java | Có thể có đường ghi khác hoặc schema đổi | Duy trì constraint DB và kiểm thử tích hợp |
| Cắt chuỗi bằng `substring(0, n)` | Có thể tách đôi surrogate pair hoặc cắt sai cụm ký tự | Từ chối dữ liệu hoặc cắt theo đơn vị đã quy định, có chính sách rõ ràng |
| Thấy `CHAR_OCTET_LENGTH` và tưởng đó là byte đang lưu của bản ghi | Metadata thể hiện khả năng kiểu cột, không phải giá trị từng hàng | Dùng phép đo byte trên giá trị thực tế, chẳng hạn `octet_length(label)` ở PostgreSQL |

## 9. Kiểm thử biên với văn bản nhiều byte

Với quy tắc **tối đa 8 code point** và **16 byte UTF-8** của bảng `ui_labels`, có thể lập các ca kiểm thử sau:

| Giá trị | Code point | Byte UTF-8 | Kết quả mong đợi |
| --- | ---: | ---: | --- |
| `"12345678"` | 8 | 8 | Hợp lệ |
| `"123456789"` | 9 | 9 | Bị từ chối do vượt 8 code point |
| `"😀😀😀😀"` | 4 | 16 | Hợp lệ tại ngưỡng byte |
| `"😀😀😀😀😀"` | 5 | 20 | Bị từ chối do vượt 16 byte |
| `"你你你你你"` | 5 | 15 | Hợp lệ |
| `"你你你你你你"` | 6 | 18 | Bị từ chối do vượt 16 byte |
| `"A😀e\u0301"` | 4 | 8 | Hợp lệ, dù Java `length()` bằng 5 |
| `null` | — | — | Bị từ chối theo `NOT NULL` và kiểm tra Java |

Một kiểm thử tích hợp cần ghi qua `setString`, đọc lại qua `getString`, so sánh `String.equals` và đo `char_length` / `octet_length` trên giá trị lưu thực tế. Nên chạy thử thêm với chuỗi có dấu kết hợp, emoji nhiều code point, khoảng trắng cuối, chữ không thuộc ASCII và dữ liệu sát giới hạn.

**Ghi nhớ:** “8 ký tự”, “8 đơn vị UTF-16” và “8 byte” là **ba ràng buộc khác nhau**. Trong JDBC, hãy xác định rõ hệ quản trị, mã hóa cột và đơn vị giới hạn; dùng `setString` / `getString` cho dữ liệu văn bản; đo độ dài theo yêu cầu nghiệp vụ; cuối cùng xác minh lại bằng quy tắc và phép đo của cơ sở dữ liệu.
