# National character stream và truyền dữ liệu văn bản lớn trong JDBC (Java 17+)

## 1. Bài toán: lưu và đọc văn bản Unicode lớn từ cơ sở dữ liệu

Trong ứng dụng Java, cột dữ liệu có thể chứa mô tả sản phẩm nhiều ngôn ngữ, tài liệu pháp lý, nội dung bài viết, phụ đề, bản thảo hoặc log văn bản dài. Nếu mọi lần ghi đều đọc toàn bộ file bằng `Files.readString(...)` rồi đưa vào `PreparedStatement.setString(...)`, ứng dụng phải giữ một `String` rất lớn trong bộ nhớ. Khi truy vấn, `ResultSet.getString(...)` cũng tạo một đối tượng `String` chứa toàn bộ nội dung.

JDBC có nhóm API **national character streams** dựa trên `java.io.Reader`, cho phép truyền dữ liệu ký tự từ nguồn vào database và đọc ra theo từng phần. Hai phương thức trọng tâm:

```java
preparedStatement.setNCharacterStream(2, reader);
Reader content = resultSet.getNCharacterStream("body");
```

Đây là **snippet**: `preparedStatement` và `resultSet` phải là các đối tượng JDBC còn mở, `reader` phải là `Reader` hợp lệ; thứ tự bind parameter và tên cột tùy câu SQL thực tế.

**Chữ N trong national character** liên quan các SQL/JDBC data types như `NCHAR`, `NVARCHAR`, `LONGNVARCHAR` và `NCLOB`. Driver thực hiện chuyển đổi từ định dạng ký tự Java sang **national character set** của cơ sở dữ liệu (hoặc ngược lại) nếu hỗ trợ. Không nên suy từ chữ “national” rằng mọi database đều có một bảng mã N riêng hay rằng VARCHAR không lưu được Unicode. Nhiều hệ DB hiện đại đã hỗ trợ Unicode ngay trong VARCHAR/TEXT với encoding phù hợp, và một số driver **không** hỗ trợ những JDBC N-methods.

### Mục tiêu học tập

Sau bài này, bạn sẽ biết:
1. Khi nào nên dùng `setNCharacterStream`/`getNCharacterStream` thay vì `setNString`/`getNString`.
2. Phân biệt `NCHAR`, `NVARCHAR`, `LONGNVARCHAR`, `NCLOB` và LOB APIs.
3. Chuyển dữ liệu từ UTF-8 file sang `Reader`, giữ stream mở suốt `executeUpdate()` và đóng đúng thứ tự.
4. Hiểu lengthless overload với overload `long length`, phân biệt bytes, UTF-16 code units, Unicode code points và ký tự hiển thị.
5. Áp dụng `ResultSet` streaming, xử lý SQL NULL, transaction, driver không hỗ trợ và kiểm thử round-trip tiếng Việt/emoji.
6. Biên dịch và chạy chương trình Java 17+ độc lập, rồi xem chương trình JDBC thực tế cần driver và database.

## 2. National SQL types và API Java tương ứng

Bốn JDBC type codes được khai báo trong `java.sql.Types`:

| JDBC type | Ý nghĩa khái quát | API liên quan | Lưu ý |
| --- | --- | --- | --- |
| `Types.NCHAR` | Ký tự national có độ dài cố định. | `setNString`, `getNString`, `getNCharacterStream`. | Cột fixed-length có thể chịu padding/trailing spaces theo DB. |
| `Types.NVARCHAR` | Chuỗi national độ dài biến đổi. | `setNString`, `getNString`, `setNCharacterStream`. | Có giới hạn độ dài theo schema/driver. |
| `Types.LONGNVARCHAR` | Văn bản national dài. | `setNCharacterStream`, `getNCharacterStream`. | Data type cụ thể trong SQL DDL thay đổi theo vendor. |
| `Types.NCLOB` | National character large object. | `setNClob`, `getNClob`, `java.sql.NClob`. | Có vòng đời LOB/transaction riêng, hỗ trợ theo driver. |

`Types.NCHAR` và các hằng còn lại là **JDBC type codes**, không nhất thiết là tên SQL DDL có thể copy nguyên cho mọi hệ quản trị. PostgreSQL, MySQL, Oracle, SQL Server và các database khác có loại cột, giới hạn và cơ chế Unicode riêng. Việc dùng `NCHAR/NVARCHAR/LONGNVARCHAR/NCLOB` phải dựa vào **schema, metadata và driver vendor** chứ không phải giả định một SQL DDL phổ dụng.

### 2.1. So sánh các nhóm API

| Nhu cầu | API nên cân nhắc | Đặc điểm |
| --- | --- | --- |
| Ghi một chuỗi national ngắn/đã có trong RAM | `PreparedStatement.setNString(index, value)` | Nhận `String`; đơn giản, nhưng dữ liệu phải có sẵn. |
| Ghi national character data từ nguồn text dài | `setNCharacterStream(index, Reader)` | Nhận `Reader`, không yêu cầu materialize toàn bộ vào `String`. |
| Ghi với length đã được xác định chính xác | `setNCharacterStream(index, Reader, long length)` | Thông báo số ký tự dự kiến; driver có thể tối ưu hơn. |
| Đọc national character data theo stream | `ResultSet.getNCharacterStream(index/label)` | Trả `Reader`, có thể là `null` nếu SQL NULL. |
| Đọc nội dung không quá lớn thành `String` | `ResultSet.getNString(index/label)` | Materialize chuỗi, không phù hợp tải cực lớn. |
| Ghi cột NCLOB trực tiếp từ text stream | `PreparedStatement.setNClob(index, Reader)` | Định hướng driver truyền dữ liệu như SQL `NCLOB`. |
| Đọc cột NCLOB | `ResultSet.getNClob(index/label)` | Trả `NClob`, có thể đọc qua `getCharacterStream()` và `free()`. |
| Ghi kiểu character thông thường, không phải N | `setCharacterStream` / `setClob` | Cũng có thể lưu Unicode nếu DB/driver encoding hỗ trợ. |

**Không tự chuyển `setNCharacterStream` thành “Unicode bắt buộc”:** Java `Reader` luôn làm việc với dữ liệu ký tự; `setCharacterStream` cũng nhận `Reader` và có thể truyền Unicode đúng nếu column encoding tương thích. `N` là một hợp đồng **SQL national character types**, không phải một kiểu mã hóa UTF-8 trực tiếp của Java.

## 3. setNCharacterStream: cách truyền Reader vào PreparedStatement

JDBC cung cấp hai overload chính:

```java
void setNCharacterStream(int parameterIndex, Reader value)
        throws SQLException;

void setNCharacterStream(int parameterIndex, Reader value, long length)
        throws SQLException;
```

Đây là **chữ ký API rút gọn**, không phải source hoàn chỉnh. Với Java 17+, cả hai overload được hỗ trợ ở mức JDBC interface; một JDBC driver cụ thể có thể báo `SQLFeatureNotSupportedException` hoặc `SQLException`.

### 3.1. Overload không cần length

```java
try (Reader reader =
        Files.newBufferedReader(inputPath, StandardCharsets.UTF_8);
     PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO localized_docs(doc_id, body) VALUES (?, ?)")) {

    ps.setLong(1, docId);
    ps.setNCharacterStream(2, reader);
    ps.executeUpdate();
}
```

Đây là **snippet** trong method có `Path inputPath`, `long docId`, `Connection connection`, cần import `java.nio.file.Files`, `java.nio.charset.StandardCharsets`, `java.io.Reader`, `java.sql.PreparedStatement`. Không phải chương trình standalone.

**Cách hoạt động:**
1. `Files.newBufferedReader(..., UTF_8)` giải mã file text UTF-8 thành dữ liệu `char` cho `Reader`.
2. `ps.setNCharacterStream(2, reader)` bind reader vào parameter thứ **hai**, vì JDBC parameter indexes bắt đầu từ **1**.
3. `ps.executeUpdate()` thực hiện câu SQL; driver có thể đọc reader **khi thực thi**, không nhất thiết ngay lúc bind.
4. `try-with-resources` giữ reader và statement mở trong suốt execute rồi đóng cả hai khi rời block, kể cả có exception.

**Không đóng `reader` ngay sau `setNCharacterStream(...)` rồi mới gọi `executeUpdate()`.** Nhiều driver đọc dữ liệu vào lúc execute và sẽ gặp stream đã đóng.

### 3.2. Overload có length

```java
long declaredLength = ...; // Số ký tự thật Reader sẽ cung cấp.
ps.setNCharacterStream(2, reader, declaredLength);
```

Đây là snippet minh họa; cần xác định `declaredLength` thật chính xác từ source. **`length` đếm ký tự của stream, không phải số byte UTF-8 của file.** Đừng truyền `Files.size(path)` làm length cho file UTF-8 có dấu tiếng Việt hoặc emoji, vì `Files.size` trả **bytes**.

Các chi tiết cần nhớ:
- `Reader.read(char[])` cung cấp các đơn vị `char` (UTF-16) của Java. Một Unicode code point ngoài BMP thường sử dụng **hai `char`** (surrogate pair).
- `String.length()` đếm UTF-16 code units; `String.codePointCount(...)` đếm Unicode code points; đó là hai đại lượng khác nhau.
- `Reader.transferTo(Writer)` trả số **ký tự Java `char` đã chuyển** theo hợp đồng API, không phải UTF-8 bytes.
- Theo Javadoc, `length` của `setNCharacterStream` là **number of characters** trong parameter data. Nếu chưa thể xác định đáng tin, dùng overload **không length**; đừng dựa vào số bytes hoặc tự đoán.
- Với overload có length, driver có thể kiểm tra stream ngắn/dài khác số khai báo, gây lỗi hoặc cắt theo hợp đồng của nó. Cần test với JDBC driver thật, nhất là khi nội dung có surrogate pairs/combining marks.

Đối với nguồn file lớn, việc quét một lượt chỉ để đếm có thể tốn I/O và làm mất lợi ích streaming. Hãy xem driver docs; một số driver tối ưu tốt hơn khi biết length, nhưng không nên đặt length sai để đổi lấy hiệu năng.

### 3.3. Reader khác InputStream

| `Reader` | `InputStream` |
| --- | --- |
| Đọc **ký tự** (`char`). | Đọc **bytes**. |
| `Files.newBufferedReader(path, UTF_8)` giải mã từ bytes. | `Files.newInputStream(path)` đưa bytes thô. |
| Phù hợp `setNCharacterStream`, `setNClob`. | Phù hợp binary APIs như `setBinaryStream`, `setBlob`. |
| Độ dài API là số ký tự. | Độ dài binary API là số bytes. |

Không truyền một `InputStream` chưa được decode cho `setNCharacterStream`: chữ ký đòi `Reader`. Cũng không dùng `new String(bytes)` mà không khai báo charset khi dữ liệu đến từ file/network.

## 4. getNCharacterStream: đọc chuỗi national theo từng phần

`ResultSet` cung cấp:

```java
Reader getNCharacterStream(int columnIndex) throws SQLException;
Reader getNCharacterStream(String columnLabel) throws SQLException;
```

Đây là chữ ký API rút gọn. Method được thiết kế cho `NCHAR`, `NVARCHAR` và `LONGNVARCHAR`. Với SQL `NULL`, nó trả **`null`**, không phải một `Reader` rỗng.

Cách đọc đúng:

```java
try (ResultSet rs = ps.executeQuery()) {
    if (rs.next()) {
        try (Reader reader = rs.getNCharacterStream("body")) {
            if (reader != null) {
                try (Writer out = Files.newBufferedWriter(
                        outputPath, StandardCharsets.UTF_8)) {
                    reader.transferTo(out);
                }
            }
        }
    }
}
```

Đây là **snippet**, cần `PreparedStatement ps` đã cấu hình, `Path outputPath` và imports `ResultSet`, `Reader`, `Writer`, `Files`, `StandardCharsets`. Nếu bạn muốn phân biệt rõ “không có hàng” và “SQL NULL”, cần xử lý chúng thành hai nhánh khác nhau theo policy ứng dụng.

**Ranh giới vòng đời:** reader nhận từ `ResultSet` gắn với current row/statement/connection. Hãy **đọc xong và đóng stream trước khi gọi `rs.next()`, gọi getter khác có thể làm stream bị đóng, hoặc đóng `ResultSet`/`Statement`**. Các driver có thể stream từ server cursor; cố giữ reader sau khi connection đã trả về pool rất dễ gây lỗi.

`Reader.transferTo(writer)` có từ Java 10 và dùng được trên Java 17+. Nó chuyển ký tự theo từng phần mà không cần tự code vòng `read`/`write`; không tự đóng input/output, vì vậy phải dùng `try-with-resources` cho cả hai.

### 4.1. Khi nào dùng getNString?

`getNString("body")` tiện với một value vừa và nhỏ đã phù hợp giới hạn bộ nhớ. Nhưng với hàng trăm MB hoặc GB văn bản, nó materialize toàn bộ nội dung thành một `String` lớn và có thể làm tăng heap usage/OOM. `getNCharacterStream` thường phù hợp hơn cho export, migration hay xử lý luồng.

**Không khẳng định việc dùng stream bảo đảm O(1) memory trên mọi JDBC driver.** Ứng dụng có thể đọc với buffer cố định, nhưng driver/server đôi khi đã buffer dữ liệu, hoặc phải materialize/truyền lại theo cách riêng. Chỉ kiểm tra memory behavior bằng benchmark/heap profiling trên driver thực tế.

## 5. Java Unicode: char, code point, UTF-8 bytes và ký tự người dùng nhìn thấy

Đối với text nhiều ngôn ngữ, bốn khái niệm khác nhau:

1. **UTF-8 bytes:** số bytes trên đĩa/mạng, tùy ký tự. `Files.size(...)` cho file UTF-8 trả số bytes (còn tính BOM/newlines nếu có).
2. **Java UTF-16 code units:** `String.length()` và `char[]` đếm đơn vị `char`.
3. **Unicode code points:** `String.codePoints()` hoặc `codePointCount(...)` đếm các code points, có thể khác `length()` khi có ký tự ngoài BMP.
4. **Grapheme clusters:** cụm ký tự cảm nhận bởi người dùng, có thể gồm nhiều code points (chữ và dấu, emoji sequences); `length()` hoặc code point count không thay thế grapheme segmentation.

Ví dụ chuỗi `"Việt Nam 🌏"` có:
- 11 Java UTF-16 `char` units.
- 10 Unicode code points.
- 15 bytes khi mã hóa UTF-8.

Vì vậy, đừng dùng `getBytes(UTF_8).length` thay cho `length` khi gọi `setNCharacterStream(..., long length)`. Ngay cả cách đếm code points cũng không tự bằng số `char` mà một `Reader` trả. Unicode normalization (NFC/NFD/NFKC/NFKD) là quyết định thiết kế **khác** với JDBC streaming; không nên tự chuyển đổi hoặc bỏ dấu trong pipeline chỉ vì dùng national character stream.

## 6. Ví dụ Java 17+ độc lập: copy một Reader theo chunks

Để thấy sự khác biệt về đơn vị đo và xác minh cơ chế `Reader`/`Writer` trước khi tích hợp JDBC, chạy chương trình sau **không cần cơ sở dữ liệu hoặc driver ngoài JDK**.

Tạo file **`ReaderChunkDemo.java`**:

```java
import java.io.Reader;
import java.io.StringReader;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;

public final class ReaderChunkDemo {

    public static void main(String[] args) throws Exception {
        String original = "Vi\u1EC7t Nam \uD83C\uDF0F";

        try (Reader source = new StringReader(original);
             StringWriter destination = new StringWriter()) {

            char[] buffer = new char[4];
            long transferred = 0;
            int n;

            while ((n = source.read(buffer)) != -1) {
                destination.write(buffer, 0, n);
                transferred += n;
            }

            String restored = destination.toString();

            System.out.println("text=" + restored);
            System.out.println("codePoints=" +
                    restored.codePointCount(0, restored.length()));
            System.out.println("utf16Units=" + restored.length());
            System.out.println("utf8Bytes=" +
                    restored.getBytes(StandardCharsets.UTF_8).length);
            System.out.println("streamedUnits=" + transferred);
            System.out.println("same=" + original.equals(restored));
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 ReaderChunkDemo.java
java ReaderChunkDemo
```

**Stdout chính xác**, đã kiểm thử trên một JDK hiện đại:

```text
text=Việt Nam 🌏
codePoints=10
utf16Units=11
utf8Bytes=15
streamedUnits=11
same=true
```

Giải thích:
- Text có dấu tiếng Việt và emoji vẫn được copy **nguyên vẹn**.
- Buffer chỉ có bốn `char`, nhiều lần `read` được nối vào `StringWriter`.
- `streamedUnits=11` là số đơn vị `char` đọc/ghi, không phải số bytes UTF-8 hoặc số code points.
- `same=true` cho thấy ghép lại tất cả `char` đã khôi phục đúng chuỗi gốc, kể cả surrogate pair của emoji.
- `StringWriter` dùng cho demo nhỏ nên giữ dữ liệu trong RAM; **đừng dùng nó như bộ đệm xuất dữ liệu hàng GB**. Trong ứng dụng thực tế, xuất thẳng ra `BufferedWriter`/file/network target có kiểm soát.

**Với JDBC:** chúng ta sẽ dùng nguyên tắc `Reader` này để bind parameter hoặc chuyển từ `ResultSet` sang file, nhưng kết quả thật còn phụ thuộc schema và driver.

## 7. Chương trình JDBC Java 17+ hoàn chỉnh: ghi và xuất text national

Chương trình tiếp theo **biên dịch chỉ với JDK**, nhưng để **thực thi** cần một JDBC driver và database thật có hỗ trợ `setNCharacterStream`/`getNCharacterStream`.

### 7.1. Điều kiện schema

Giả sử database đã có bảng logic:

```sql
CREATE TABLE localized_docs (
    doc_id BIGINT PRIMARY KEY,
    body LONGNVARCHAR
);
```

**Đây là DDL minh họa, không bảo đảm chạy nguyên văn trên mọi DBMS.** Cột `body` phải là một kiểu text/large national-character tương thích với driver và JDBC N APIs; có hệ thống dùng `NVARCHAR(MAX)`, `NCLOB` hoặc kiểu Unicode text theo vendor, và mỗi kiểu lại có API khuyến nghị khác nhau. Đừng đổi `LONGNVARCHAR` thành SQL type tùy tiện mà không kiểm tra database manual.

Nếu schema dùng **`NCLOB`**, cân nhắc `setNClob(..., Reader)` và `getNClob(...)` (trình bày ở mục 9) thay cho bản `LONGNVARCHAR` demo.

### 7.2. File JdbcNationalStreamExample.java

```java
import java.io.IOException;
import java.io.Reader;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Properties;

public final class JdbcNationalStreamExample {

    private static void insert(
            Connection connection, long id, Path input)
            throws SQLException, IOException {

        String sql =
                "INSERT INTO localized_docs (doc_id, body) VALUES (?, ?)";

        try (PreparedStatement ps = connection.prepareStatement(sql);
             Reader reader = Files.newBufferedReader(
                     input, StandardCharsets.UTF_8)) {

            ps.setLong(1, id);
            ps.setNCharacterStream(2, reader);

            int rows = ps.executeUpdate();
            if (rows != 1) {
                throw new SQLException(
                        "Unexpected insert count: " + rows);
            }
        }
    }

    private static long export(
            Connection connection, long id, Path output)
            throws SQLException, IOException {

        String sql =
                "SELECT body FROM localized_docs WHERE doc_id = ?";

        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, id);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException("Document not found: " + id);
                }

                try (Reader reader =
                             rs.getNCharacterStream("body")) {
                    if (reader == null) {
                        throw new SQLException(
                                "Document body is SQL NULL");
                    }

                    try (Writer writer = Files.newBufferedWriter(
                            output, StandardCharsets.UTF_8)) {
                        return reader.transferTo(writer);
                    }
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 4) {
            System.err.println(
                    "Usage: java JdbcNationalStreamExample "
                    + "<jdbc-url> <id> <input.txt> <output.txt>");
            return;
        }

        long id = Long.parseLong(args[1]);
        Properties login = new Properties();

        String user = System.getenv("DB_USER");
        String password = System.getenv("DB_PASSWORD");
        if (user != null) {
            login.setProperty("user", user);
        }
        if (password != null) {
            login.setProperty("password", password);
        }

        try (Connection connection =
                     DriverManager.getConnection(args[0], login)) {

            insert(connection, id, Path.of(args[2]));
            long units =
                    export(connection, id, Path.of(args[3]));

            System.out.println("inserted=true");
            System.out.println("exportedUtf16Units=" + units);
        }
    }
}
```

### 7.3. Cách chạy với driver phù hợp

Biên dịch Java:

```bash
javac -encoding UTF-8 JdbcNationalStreamExample.java
```

Giả sử bạn đã có JDBC driver tương thích là `driver.jar` trong cùng thư mục, đã chuẩn bị bảng và đặt `JDBC_URL` (chỉ chứa địa chỉ DB, không chứa password), ví dụ trên Linux/macOS:

```bash
java -cp ".:driver.jar" JdbcNationalStreamExample \
  "$JDBC_URL" 42 input.txt exported.txt
```

Trong Windows PowerShell, dùng dấu phân cách classpath `;` và biến môi trường PowerShell:

```powershell
java -cp '.;driver.jar' JdbcNationalStreamExample $env:JDBC_URL 42 input.txt exported.txt
```

`driver.jar` là **placeholder tên JAR tùy vendor**, bạn phải thay bằng JAR thật. Cách run qua Maven/Gradle có thể dùng runtime classpath do build tool quản lý. Nếu DB yêu cầu login, sample đọc `DB_USER` và `DB_PASSWORD` từ environment; với production ưu tiên secret manager/credential provider thay cho hard-coded password hoặc URL chứa secret.

**Ý nghĩa chương trình:**
1. Tham số `<jdbc-url>`: URL của database test. `<id>` là primary key mới, chưa tồn tại; chạy lại cùng ID có thể bị lỗi duplicate key.
2. `input.txt` phải là text UTF-8, có thể có nội dung tiếng Việt/emoji; code dùng `Files.newBufferedReader(..., UTF_8)`.
3. Reader input còn mở cho đến **sau** `ps.executeUpdate()`; driver có thể đọc theo nhu cầu trong lúc execute.
4. Sau khi INSERT, code SELECT cùng ID; `rs.getNCharacterStream("body")` cho Reader và `reader.transferTo(writer)` xuất ra `exported.txt`.
5. Output writer được mở bằng `Files.newBufferedWriter` và theo cấu hình mặc định của phương thức này có thể **tạo hoặc ghi đè/truncate file đích**; chỉ dùng đường dẫn output an toàn khi test, đừng dùng file quan trọng.
6. Chương trình tự dùng auto-commit mặc định của connection. Trong service thật, hãy thiết kế transaction/rollback và xử lý lỗi file I/O cùng DB transaction cho nhất quán.
7. Đây không phải benchmark streaming. App dùng Reader, nhưng driver có thể buffer toàn bộ text; cần đo thực tế khi dữ liệu rất lớn.

**Không có một stdout cố định cho ví dụ JDBC thực:** lỗi hay thành công phụ thuộc driver, DB connection, loại cột, quyền SQL, khóa đã tồn tại, encoding và kích thước dữ liệu. Nếu tất cả phù hợp, chương trình in `inserted=true` và `exportedUtf16Units=<số ký tự Java đã chuyển>`. Không được tuyên bố một số units cụ thể khi chưa biết nội dung file.

### 7.4. Lưu ý transaction và khôi phục khi lỗi

Nếu kết nối dùng `autoCommit=true`, `INSERT` có thể commit trước khi chương trình bắt đầu export. Nếu export gặp lỗi I/O, DB row đã ghi có thể vẫn còn, trong khi file chưa hoàn chỉnh. Với workflow production cần all-or-nothing:
- Cân nhắc transaction DB rõ ràng và `rollback` khi SQL/IO failure.
- Viết file ra đường dẫn temporary, `fsync` hoặc chuyển tên file có kiểm soát khi cần; DB và filesystem **không tự có distributed transaction** chỉ vì dùng một Java try-block.
- Không tin `Files.newBufferedWriter` là atomic write.
- Có idempotency key và xử lý rerun để không gặp duplicate key hoặc ghi đè file ngoài ý muốn.
- Đóng toàn bộ JDBC resources/Readers trước khi commit khi driver có LOB streams gắn với transaction.

## 8. Null, NCHAR/NVARCHAR và các giới hạn của driver

### 8.1. SQL NULL khác chuỗi rỗng

`getNCharacterStream(...)` trả **null** khi cột là SQL NULL. `""` lại là một giá trị chuỗi rỗng hợp lệ. Phải phân biệt:

```java
Reader reader = rs.getNCharacterStream("body");
if (reader == null) {
    // Cột có giá trị SQL NULL; chọn policy riêng.
} else {
    try (reader) {
        reader.transferTo(writer);
    }
}
```

Đây là snippet trong method có `ResultSet rs` và `Writer writer`; không phải chương trình độc lập. Nếu ứng dụng không cho phép NULL, báo lỗi có ý nghĩa; đừng tự ghi file rỗng và mất thông tin.

Để **đặt SQL NULL** với parameter national, có thể dùng:

```java
ps.setNull(2, java.sql.Types.NVARCHAR);
```

Đây là snippet khi cột phù hợp SQL `NVARCHAR`. Với NCLOB dùng `Types.NCLOB` và kiểm tra driver. `setNCharacterStream(index, null)` có thể có behavior riêng theo driver; `setNull` thể hiện ý định SQL NULL rõ ràng.

### 8.2. Không phải mọi DB có national character set riêng

Một database UTF-8 có thể lưu chuỗi tiếng Việt rất tốt trong `VARCHAR` hoặc `TEXT`. Nhưng JDBC `NCHAR` methods vẫn có thể không được hỗ trợ hoặc chuyển đổi không phù hợp. Driver có thể báo:
- `SQLFeatureNotSupportedException`: overload không được driver triển khai.
- `SQLException`: DB không hỗ trợ national character set, lỗi chuyển đổi, lỗi cột, statement/connection đã đóng.
- Lỗi về maximum length/truncation khi dữ liệu vượt giới hạn SQL column.
- Lỗi encoding/IO nguồn trước hoặc trong lúc driver đọc stream.

Không coi `SQLFeatureNotSupportedException` là dấu hiệu “DB không hỗ trợ Unicode”. Trường hợp driver không hỗ trợ `N` methods nhưng cột UTF-8/Unicode text hỗ trợ `VARCHAR/TEXT`, có thể dùng `setCharacterStream`/`getCharacterStream` theo driver docs, schema và test. **Đừng tự fallback sang API khác trong catch nếu chưa biết nó lưu dữ liệu đúng**, vì có nguy cơ sai encoding hoặc mất dữ liệu.

### 8.3. Kiểm tra JDBC metadata

Trong những tình huống cần quyết định mapping tự động, có thể đọc:
- `ResultSetMetaData.getColumnType(i)` cho JDBC type code của cột SELECT.
- `ResultSetMetaData.getColumnTypeName(i)` cho tên kiểu DB-specific.
- `DatabaseMetaData.getColumns(...)` cho thông tin cột, độ dài, NULLability.
- `DatabaseMetaData.getTypeInfo()` cho các SQL types được driver quảng bá.

Ví dụ:

```java
ResultSetMetaData meta = rs.getMetaData();
int typeCode = meta.getColumnType(1);
String vendorType = meta.getColumnTypeName(1);
```

Đây là snippet với `rs` là ResultSet có cột đầu tương ứng. Metadata giúp hướng dẫn mapping, **không đủ chứng minh mọi overload N-stream thực sự chạy đúng**. Test integration là bắt buộc cho driver/version cụ thể.

## 9. NCLOB: LOB dành cho national characters

`java.sql.NClob` extends `java.sql.Clob` và đại diện SQL `NCLOB`. Với cột được triển khai là **NCLOB**, nên cân nhắc API LOB chuyên biệt:

### 9.1. Ghi NCLOB từ Reader

```java
try (Reader source = Files.newBufferedReader(
        input, StandardCharsets.UTF_8);
     PreparedStatement ps = connection.prepareStatement(
        "UPDATE localized_docs SET body = ? WHERE doc_id = ?")) {

    ps.setNClob(1, source);
    ps.setLong(2, id);
    ps.executeUpdate();
}
```

Đây là snippet khi schema `body` thực sự là NCLOB và driver hỗ trợ overload `setNClob(int, Reader)`. Khác `setNCharacterStream`, `setNClob` **báo cho driver rằng parameter cần truyền dưới dạng NCLOB**. Các driver có thể tối ưu upload LOB khác nhau.

### 9.2. Đọc NCLOB rồi free

```java
NClob lob = rs.getNClob("body");

if (lob != null) {
    try {
        try (Reader reader = lob.getCharacterStream()) {
            reader.transferTo(outputWriter);
        }
    } finally {
        lob.free();
    }
}
```

Đây là snippet có `ResultSet rs`, `Writer outputWriter` và import `java.sql.NClob`, `java.io.Reader`. `NClob` là đối tượng liên quan tới SQL LOB; nó hợp lệ trong transaction tương ứng và có method `free()` từ `Clob` để giải phóng resources. Không giữ `NClob` sau khi transaction/connection đã kết thúc với kỳ vọng server vẫn cho đọc.

**Đừng nhầm `getNCharacterStream` và `getNClob`:** `getNCharacterStream` được Javadoc mô tả chủ yếu cho `NCHAR/NVARCHAR/LONGNVARCHAR`; `getNClob` trả đối tượng SQL `NCLOB`. Chọn method theo schema và driver. Một số driver cho phép đọc NCLOB qua stream khác nhưng cần kiểm tra vendor docs; không tự giả định mọi driver đồng nhất.

### 9.3. setNClob với length và createNClob

JDBC còn có `setNClob(int, Reader, long length)` và `setNClob(int, NClob)`. `Connection.createNClob()` tạo một `NClob` rỗng khi driver hỗ trợ; một số driver không có implementation và có thể ném `SQLFeatureNotSupportedException`. Với dữ liệu file đã ở dạng Reader, `setNClob(index, reader)` thường đơn giản hơn việc tạo NClob trong RAM rồi ghi toàn bộ dữ liệu vào đó.

**Không quên `free()`** cho NClob do ứng dụng nhận/tạo nếu driver cung cấp resources gắn với nó; xử lý ngoại lệ ở khâu cleanup theo chính sách và giữ lỗi gốc nếu có.

## 10. Cập nhật qua ResultSet.updateNCharacterStream

Ngoài `PreparedStatement`, một số JDBC drivers hỗ trợ **updatable ResultSet**:

```java
rs.updateNCharacterStream("body", reader);
rs.updateRow();
```

Đây là snippet với `ResultSet rs` kiểu **updatable** (ví dụ `CONCUR_UPDATABLE`), `Reader reader` phải còn mở đến khi `updateRow()` chạy; đồng thời statement/driver phải thực sự hỗ trợ cập nhật cột national type.

**Quan trọng:** `updateNCharacterStream` **chỉ cập nhật row buffer của ResultSet**; thao tác cần `rs.updateRow()` (hoặc `insertRow()` nếu làm việc trên insert row) để đẩy thay đổi xuống database. Không thể dựa vào việc gọi updater method để kết luận DB đã commit. Với `ResultSet.CONCUR_READ_ONLY`, các thao tác update có thể bị từ chối; nhiều driver cũng không hỗ trợ updatable cursor cho LOB. Trong các hệ thống backend thông thường, `PreparedStatement UPDATE ... SET body=? WHERE id=?` thường đơn giản, dễ portable và rõ transaction hơn.

Nếu cần overload có length, `ResultSet.updateNCharacterStream(label/index, Reader, long)` cũng có, nhưng phải bảo đảm length thật sự khớp source theo driver contract.

## 11. Vòng đời stream và thứ tự đóng tài nguyên

`Reader` lấy từ database thường **không phải một bản copy độc lập** của toàn bộ dữ liệu. Nó có thể kéo dữ liệu theo cursor hoặc giao thức driver. Quy tắc an toàn:

1. **Lúc ghi:** mở Reader từ file, bind vào PreparedStatement, thực hiện `executeUpdate`/`execute` khi Reader vẫn mở, rồi mới close.
2. **Lúc đọc:** sau `rs.next()`, gọi getter stream và **đọc hết trước** khi chuyển cursor, gọi getter khác có thể ảnh hưởng stream, đóng ResultSet/Statement, commit transaction hoặc trả connection về pool.
3. Dùng `try-with-resources` cho `PreparedStatement`, `ResultSet`, `Reader`, `Writer`; đóng resource theo thứ tự đảo của lúc mở.
4. Với LOB, tuân thủ transaction validity; gọi `NClob.free()` khi kết thúc xử lý.
5. Không giữ `Reader` làm field hoặc trả ra khỏi method sau khi đã đóng `ResultSet`/`Connection`.
6. Không tái sử dụng **cùng một Reader đã đọc đến EOF** cho nhiều lần `executeUpdate` hoặc batch executions. Nếu cần chạy lại, **mở Reader mới** hoặc có source rewind đáng tin cậy.
7. Với download/export dài, cân nhắc timeout, cancellation và backpressure theo ứng dụng; đừng để connection bị chiếm vô hạn.

**Streams không tự giúp bạn quản lý connection pool.** Nếu export hàng GB, physical connection có thể bị giữ rất lâu, gây thiếu connection cho request khác. Kiến trúc batch/offline export cần pool quota, timeout, giới hạn concurrency và theo dõi resource sử dụng.

## 12. Performance: streaming thật hay chỉ streaming ở giao diện API?

### 12.1. Lợi ích ở phía ứng dụng

Nếu bạn chuyển từ `Files.readString(path)` sang `Files.newBufferedReader(path, UTF_8)`, ứng dụng không cần tạo một `String` chứa toàn bộ file chỉ để bind vào statement.

Khi đọc, `rs.getNCharacterStream(...)` kết hợp `reader.transferTo(writer)` không yêu cầu tạo một `String` lớn trong business layer. Memory cần cho **buffer ứng dụng** có thể nhỏ và ổn định theo cách code của bạn.

### 12.2. Driver/server có thể buffer

Điều này **không đảm bảo** driver sẽ stream dữ liệu qua mạng theo các chunk nhỏ. Một số driver:
- Đọc và giữ dữ liệu tạm trước khi gửi.
- Yêu cầu length để tối ưu đường truyền.
- Materialize toàn bộ LOB dù API trả Reader.
- Dùng network packet buffers, server-side cursors hoặc temporary storage riêng.

Hãy kiểm tra docs và benchmark với đúng JDK, driver, DBMS, column type và data size. Quan sát **peak heap, GC, DB I/O, latency, throughput, kích cỡ result set và thời gian chiếm connection**. Không kết luận “stream O(1) RAM” chỉ dựa trên tên API.

### 12.3. Khi nào dùng known-length?

Nếu đã có nguồn ký tự với số đơn vị được tính chính xác (ví dụ một nguồn text được pre-count), overload length có thể giúp driver lên kế hoạch đọc. Nhưng nếu nguồn là UTF-8 file lớn, phải decode để đếm ký tự theo quy tắc Reader, không truyền `Files.size()`.

Nếu driver hỗ trợ lengthless tốt, **overload không length** tránh vòng đọc phụ và tránh lỗi length mismatch. Hãy cân nhắc trade-off theo JDBC driver documentation.

### 12.4. Batch, transaction và retry

- Với rất nhiều hàng, hãy giới hạn batch size và concurrency. Batch chứa nhiều stream parameters có thể có lifecycle đặc biệt, cần test driver.
- Đừng reuse một Reader giữa batch items hoặc lần retry sau khi đã bị consume.
- Khi transaction thất bại, DB có thể rollback dữ liệu nhưng nguồn text (file/network) không tự được “rewind”.
- Đối với upload lớn, cân nhắc retry/idempotency theo primary key và transaction boundary; tránh ghi trùng dữ liệu hoặc tạo file xuất nửa chừng.

## 13. Encoding, dữ liệu quốc tế và tính toàn vẹn

### 13.1. File UTF-8 → Reader → JDBC N stream → SQL column

```text
File bytes (UTF-8)
        |
Files.newBufferedReader(path, UTF_8)
        |
Java Reader (UTF-16 char units)
        |
PreparedStatement.setNCharacterStream(...)
        |
JDBC driver chuyển đổi ký tự theo national charset
        |
SQL NCHAR / NVARCHAR / LONGNVARCHAR (nếu hỗ trợ)
        |
ResultSet.getNCharacterStream(...)
        |
Reader.transferTo(Writer UTF-8)
        |
File bytes (UTF-8)
```

Sơ đồ chỉ minh họa pipeline khi driver/schema tương thích, không phải bảo đảm mọi database có national charset tách biệt. `Reader` không phải file UTF-8 bytes; nó cung cấp Unicode text đã được giải mã.

### 13.2. BOM, malformed input và normalization

- Một file có UTF-8 BOM, newline style hoặc encoding không khớp có thể gây khác biệt dữ liệu. Hãy quyết định chính sách decode/normalize rõ.
- `Files.newBufferedReader(..., UTF_8)` có thể ném `MalformedInputException` khi bytes không hợp lệ theo charset. Không âm thầm decode bằng charset mặc định rồi bỏ qua lỗi.
- JDBC national stream **không tự chuẩn hóa Unicode NFC/NFD**, không tự bỏ dấu tiếng Việt và không đảm bảo các chuỗi canonical-equivalent trở thành cùng bytes.
- Khi kiểm tra round-trip, so sánh text/các code points hoặc hash trên **bytes ở cùng encoding** có chủ đích; không chỉ so sánh hình ảnh trên màn hình.
- Với emoji hoặc ký tự ngoài BMP, phải test chính sách surrogate pairs, Unicode conversions và khả năng cột/driver chứa dữ liệu nguyên vẹn.
- Nếu schema/driver có giới hạn theo bytes hoặc kí tự, kiểm tra đúng unit của **database**; đừng lấy giới hạn `NVARCHAR(100)` của một DB suy ra giới hạn mọi DB khác.

### 13.3. Readback trước khi kết luận

Một lần `executeUpdate()` thành công chưa chứng minh text đa ngôn ngữ đã bảo toàn chính xác trong mọi cấu hình. Tốt nhất test insert → select → export và so sánh original/export, bao gồm tiếng Việt kết hợp dấu, CJK và emoji.

Với file lớn, có thể tính hash trên byte streams **sau khi đã đảm bảo encoding, newline và normalization policy giống nhau**. Nếu pipeline chủ ý chuyển charset/normalization, không dùng byte hash nguyên gốc để đòi trùng tuyệt đối mà hãy định nghĩa điều kiện tương đương.

## 14. Xử lý lỗi an toàn

| Lỗi/sự cố | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `SQLFeatureNotSupportedException` ở `setNCharacterStream` | Driver chưa hỗ trợ method hoặc national types. | Kiểm tra driver/version và mapping; cân nhắc `setCharacterStream` nếu schema Unicode phù hợp. |
| `SQLException` chuyển đổi ký tự | DB national charset không biểu diễn được dữ liệu hoặc driver phát hiện lỗi chuyển đổi. | Kiểm tra encoding/schema/data, không tự bỏ emoji/dấu. |
| Truncation/column length lỗi | Văn bản dài hơn column limit. | Dùng loại cột có sức chứa phù hợp; test kích cỡ thật. |
| Stream closed/IO error khi execute | Reader bị đóng trước khi driver đọc xong hoặc source không đọc được. | Giữ Reader mở xuyên suốt execute; bắt/quan sát cause. |
| Mismatch length overload | Truyền bytes làm số ký tự hoặc đếm sai surrogate pairs. | Dùng lengthless overload hoặc đo đúng Reader chars. |
| `getNCharacterStream` trả null | Cột SQL NULL. | Xử lý null khác text rỗng. |
| Reader lỗi khi di chuyển cursor | Đọc sau `rs.next()`/close hoặc driver chỉ cho một stream. | Đọc hết stream trước getter khác/chuyển row. |
| OOM dù đã dùng stream | Driver materialize hoặc ứng dụng gom text vào `StringWriter`/String. | Profile driver, dùng file Writer/buffer, đổi chiến lược LOB. |
| Unicode mất dấu/sai emoji | Charset mismatch, DB collation/type/driver conversion. | Kiểm tra round-trip với code points và UTF-8. |
| `NClob` không hợp lệ | Giữ LOB sau transaction hoặc không `free()` đúng lúc. | Đọc trong transaction, đóng Reader và free LOB. |
| Export file thiếu cuối | Exception giữa transfer, writer flush/close không hoàn tất. | Dùng temp file + atomic rename có kiểm soát khi cần. |
| Query SQL injection | Xây SQL từ chuỗi người dùng. | Dùng `PreparedStatement` bind parameters, allowlist identifier động. |

**Không tự động retry bất kỳ lỗi stream nào.** Reader có thể đã bị consume và DB transaction có thể đã thay đổi. Mở nguồn mới, xác minh trạng thái DB, thiết kế idempotency/rollback trước khi retry.

### 14.1. Catch SQLFeatureNotSupportedException trước SQLException

`SQLFeatureNotSupportedException` là subclass của `SQLException`:

```java
try {
    ps.setNCharacterStream(2, reader);
    ps.executeUpdate();
} catch (SQLFeatureNotSupportedException e) {
    // Driver không hỗ trợ: chọn phương án thay thế đã kiểm chứng.
} catch (SQLException e) {
    // Lỗi JDBC khác: connection, SQL, conversion, truncation...
}
```

Đây là snippet trong method đã có `PreparedStatement ps` và `Reader reader`, cần import hai exception classes. Với IO khi `Reader` bị đọc, driver có thể bọc lỗi và ném `SQLException`; nên xem cause/nextException chain theo policy diagnostics, không log nội dung nhạy cảm.

## 15. Dữ liệu nhạy cảm và an toàn khi upload/download lớn

- **Không dùng filenames/paths trực tiếp từ user input** nếu chưa validate/authorize. Chặn path traversal; đặt file trong thư mục được cấp phép và kiểm soát overwrite.
- **Không in nội dung cột ra logs** chỉ để debug driver: tài liệu có thể chứa PII, hợp đồng, token hoặc dữ liệu riêng tư.
- **Dùng `PreparedStatement` với bind params** thay nối chuỗi SQL có input người dùng; tên cột/table động phải dùng allowlist.
- **Giới hạn dung lượng, timeout và concurrency** để tránh một request chiếm tất cả connection pool/đĩa/heap. Check max document size theo nghiệp vụ trước khi nạp.
- **Không lưu secrets trong JVM arguments/JDBC URL** nếu có cách quản lý credentials tốt hơn; ví dụ dùng environment chỉ mang tính minh họa. Với production dùng secret manager và cấu hình kết nối an toàn.
- **Không ngầm coi stream là kiểm tra virus/data policy.** Nếu nhận file từ người dùng, còn cần các lớp validation/inspection của ứng dụng.
- **Thống nhất encoding** ở byte boundary và kiểm tra round-trip; quốc tế hóa không đồng nghĩa cho phép mọi ký tự control.
- **Phân tách upload transaction và export** trong thiết kế thực tế; xử lý file output đang tạo dở khi thất bại.

## 16. Kiểm thử tích hợp theo driver

Các ca nên có trước khi dùng national streams trong production:

**Test 1 — API support:** Kiểm tra `setNCharacterStream`, `getNCharacterStream`, `setNClob`, `getNClob` với driver và column type thật. Bắt `SQLFeatureNotSupportedException` và kiểm tra dữ liệu không bị ghi sai.

**Test 2 — Unicode cơ bản:** Ghi/đọc tiếng Việt có dấu, CJK và emoji; so sánh code points trước/sau.

**Test 3 — NULL vs empty:** Kiểm tra `getNCharacterStream` trả null cho SQL NULL, nhưng trả Reader có EOF ngay với empty string; đừng trộn hai trạng thái.

**Test 4 — length và no-length:** Với source thực, so sánh overload không length và có length đúng. Thử length sai trong môi trường test; xem driver báo lỗi thế nào, không đoán tự động truncation.

**Test 5 — Large file:** Vài MB → hàng trăm MB theo SLA; đo peak heap, GC, network, thời gian giữ connection và throughput; kiểm tra driver có buffer không.

**Test 6 — Reader lifetime:** Cố tình đóng Reader trước execute trong test để biết lỗi, rồi sửa bằng try-with-resources đúng phạm vi.

**Test 7 — Cursor lifetime:** Đọc từng dòng hoàn chỉnh trước `rs.next()`; xác nhận không giữ Reader sau khi ResultSet đóng.

**Test 8 — Driver-specific type mapping:** So sánh national types với regular Unicode text types theo schema của vendor; không suy từ SQL DDL của database A cho database B.

**Test 9 — Transaction rollback:** Khi lỗi giữa upload/export, bảo đảm row state và file state theo chính sách. Không giả định rollback tự xóa output file.

**Test 10 — Connection pool và concurrency:** Không chia sẻ `ResultSet`/`Reader` giữa threads; limit simultaneous long exports, kiểm tra pool starvation.

**Test 11 — Round-trip file:** Đọc input/output với UTF-8 và so sánh codepoints/hash theo policy newline/normalization.

**Test 12 — NClob lifetime:** Với driver hỗ trợ NCLOB, đọc qua `NClob.getCharacterStream()` trong transaction và gọi `free()`; không giữ LOB sau commit.

## 17. Câu hỏi ôn tập

**Câu 1.** `setNCharacterStream` dùng kiểu dữ liệu Java gì?

**Đáp án:** `java.io.Reader`, vì mục tiêu là dữ liệu ký tự Unicode. Không truyền trực tiếp `InputStream` bytes vào overload này.

**Câu 2.** `setNCharacterStream(2, reader, length)`: length là số bytes trong file UTF-8 phải không?

**Đáp án:** Không. Javadoc nói length là số **ký tự** của parameter data. Với `Reader`, đếm dữ liệu ký tự được đọc, không phải `Files.size` (bytes).

**Câu 3.** Vì sao `reader.close()` trước `ps.executeUpdate()` nguy hiểm?

**Đáp án:** Driver có thể đọc Reader khi execute; lúc đó nguồn đã đóng và câu SQL thất bại hoặc bị thiếu dữ liệu.

**Câu 4.** `getNCharacterStream` trả gì nếu SQL column là NULL?

**Đáp án:** `null`, cần phân biệt với Reader chứa chuỗi rỗng.

**Câu 5.** `getNCharacterStream` có dùng cho NCLOB giống hệt `getNClob` không?

**Đáp án:** Không nên coi là tương đương toàn diện. `getNCharacterStream` dành cho `NCHAR/NVARCHAR/LONGNVARCHAR`; `getNClob` trả object `NClob` với vòng đời LOB riêng.

**Câu 6.** Vì sao đã dùng `Reader` mà app vẫn có thể OOM?

**Đáp án:** Driver có thể buffer dữ liệu, hoặc code tự gom toàn bộ vào `StringWriter`/`String`. Streaming API không bảo đảm memory cố định của mọi tầng.

**Câu 7.** Với file `"Việt Nam 🌏"`, số UTF-8 bytes, UTF-16 units, code points có bằng nhau không?

**Đáp án:** Không. Ví dụ đã chạy chứng minh lần lượt **15 bytes**, **11 UTF-16 units**, **10 code points**.

**Câu 8.** Khi dùng `ResultSet.updateNCharacterStream` có cần gọi `updateRow`?

**Đáp án:** Có, với updatable ResultSet update method chỉ sửa row buffer; `updateRow` đẩy thay đổi xuống DB (và transaction commit còn tùy connection).

**Câu 9.** Nếu driver không hỗ trợ N API, có đồng nghĩa database không lưu được tiếng Việt?

**Đáp án:** Không. Có DB dùng UTF-8 trong `VARCHAR/TEXT`; có thể chọn regular character stream APIs theo vendor docs và kiểm thử.

**Câu 10.** Vì sao file output sau SELECT không tự được rollback khi DB transaction lỗi?

**Đáp án:** DB transaction không quản lý filesystem. Phải thiết kế temp file, cleanup và idempotency riêng.

## 18. Checklist triển khai

1. **Xác định column type thực sự** và việc driver hỗ trợ JDBC national-character APIs.
2. **Chọn đúng setter/getter**: `setNCharacterStream/getNCharacterStream` cho national string/long string, `setNClob/getNClob` cho NCLOB nếu hỗ trợ.
3. **Dùng `Reader` với encoding rõ ở byte boundary**, thường `Files.newBufferedReader(path, UTF_8)`.
4. **Giữ Reader mở tới khi execute xong** và reader từ ResultSet còn mở tới khi đã đọc hết, trước khi chuyển row/đóng cursor.
5. **Không dùng byte size làm character length**; ưu tiên no-length overload nếu không biết chính xác.
6. **Phân biệt UTF-8 bytes, UTF-16 chars, Unicode codepoints và grapheme clusters**.
7. **Dùng try-with-resources**, `NClob.free()` và connection/statement lifecycle rõ.
8. **Không materialize toàn bộ text vào String** nếu đang xử lý dữ liệu rất lớn; đo driver buffering thực tế.
9. **Bảo vệ schema và SQL parameters**, không ghép SQL từ input chưa tin cậy.
10. **Không ghi đè output file quan trọng** và có cơ chế cleanup khi exception.
11. **Có transaction/idempotency policy** khi phối hợp DB và filesystem.
12. **Test round-trip Unicode** và ca SQL NULL/empty với driver/version thật.
13. **Giới hạn concurrency, size, timeout** để bảo vệ connection pool và ổ đĩa.
14. **Không sử dụng API cũ/lỗi thời**; các APIs `Reader`, `PreparedStatement`, `ResultSet`, `NClob` và `Types` trong bài vẫn được hỗ trợ ở Java 17+.

## 19. Tài liệu API chính thức

- [Java SE 17 — PreparedStatement](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html) — `setNCharacterStream`, `setNClob`, `setNString`, JDBC parameter binding.
- [Java SE 17 — ResultSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html) — `getNCharacterStream`, `getNString`, `getNClob`, `updateNCharacterStream`.
- [Java SE 17 — NClob](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/NClob.html) — contract national CLOB và vòng đời.
- [Java SE 17 — Types](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Types.html) — `NCHAR`, `NVARCHAR`, `LONGNVARCHAR`, `NCLOB`.
- [Java SE 17 — Reader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Reader.html) — `read`, `close`, `transferTo`.
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html) — `newBufferedReader`/`newBufferedWriter` with explicit charset.
- [Java SE 17 — SQLFeatureNotSupportedException](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLFeatureNotSupportedException.html) — driver functionality unavailable.
- [Java SE 25 — PreparedStatement](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/PreparedStatement.html) — đối chiếu API vẫn còn được hỗ trợ trong JDK hiện đại.
