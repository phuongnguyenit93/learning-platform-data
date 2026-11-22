# Gán dữ liệu lớn bằng luồng đầu vào trong JDBC

Trong chương **Dữ liệu lớn**, ứng dụng Java sử dụng JDBC có thể cần lưu ảnh, tài liệu PDF, tệp đính kèm hoặc văn bản dài vào cơ sở dữ liệu quan hệ. Nếu đọc toàn bộ nội dung thành `byte[]` hay `String` trước khi gọi `PreparedStatement`, mức sử dụng bộ nhớ có thể tăng mạnh khi nhiều yêu cầu tải tệp cùng lúc. JDBC cho phép **gán tham số SQL từ luồng**: `InputStream` cho dữ liệu nhị phân và `Reader` cho dữ liệu ký tự.

Ví dụ, một tệp 200 MB không nhất thiết phải tồn tại đồng thời dưới dạng mảng byte 200 MB trong heap Java chỉ để thực hiện `INSERT`. Ứng dụng có thể mở `InputStream`, truyền cho `PreparedStatement.setBinaryStream(...)` hoặc `setBlob(...)` rồi cho driver đọc trong quá trình thực thi. Tuy nhiên, **API luồng không bảo đảm mọi driver đều truyền dữ liệu theo từng phần với bộ nhớ hằng số**: driver có thể đệm dữ liệu vì giao thức, cấu hình, batching hoặc khả năng hỗ trợ BLOB/CLOB.

Bài này hướng dẫn chọn đúng phương thức JDBC, sử dụng `DataSource` và `PreparedStatement` để gửi nội dung lớn theo tham số, quản lý vòng đời luồng, xử lý độ dài dữ liệu, transaction và kiểm tra tính khả chuyển giữa driver. Các ví dụ áp dụng cho những thao tác CRUD có dữ liệu lớn nhưng vẫn dùng API JDBC chuẩn.

## 1. Phân biệt dữ liệu nhị phân và dữ liệu ký tự

Điểm đầu tiên là phân loại **bản chất** của dữ liệu được lưu:

| Dữ liệu đầu vào | Kiểu Java phù hợp | Kiểu cột SQL thường gặp | Phương thức JDBC |
| --- | --- | --- | --- |
| Ảnh, PDF, ZIP hoặc byte tùy ý | `InputStream` | `BLOB`, `VARBINARY`, `LONGVARBINARY` hoặc kiểu tương đương | `setBinaryStream(...)` hoặc `setBlob(...)` |
| Văn bản Unicode dài | `Reader` | `CLOB` hoặc kiểu văn bản lớn tương đương | `setCharacterStream(...)` hoặc `setClob(...)` |
| Văn bản quốc gia với kiểu NCHAR/NCLOB | `Reader` | `NCLOB`, `NVARCHAR`, `LONGNVARCHAR` | `setNCharacterStream(...)` hoặc `setNClob(...)` |
| Văn bản thật sự chỉ dùng US-ASCII | `InputStream` | Kiểu ký tự phù hợp | `setAsciiStream(...)` |

**`InputStream` đọc byte; `Reader` đọc ký tự.** Không nên dùng `setAsciiStream` cho tiếng Việt có dấu hoặc dữ liệu UTF-8 nhiều byte rồi giả định driver sẽ tự hiểu đúng Unicode. Đối với văn bản, chọn charset khi biến byte thành ký tự; với `Reader`, driver nhận nội dung ký tự và thực hiện chuyển đổi sang biểu diễn lưu trữ do DB hỗ trợ.

Với một tệp PDF, dữ liệu phải được giữ **nguyên từng byte**: dùng `InputStream`. Với một bài viết tiếng Việt, nếu nghiệp vụ cần tìm kiếm, so sánh hoặc xử lý như văn bản SQL, có thể dùng `Reader` và cột kiểu ký tự.

### Sơ đồ truyền dữ liệu

```text
Tệp/nguồn mạng
    |
    | InputStream (byte) / Reader (ký tự)
    v
PreparedStatement.setBinaryStream / setCharacterStream / setBlob / setClob
    |
    | Giá trị được bind vào tham số ?
    v
PreparedStatement.executeUpdate()
    |
    | Driver JDBC chuyển dữ liệu theo giao thức của DB
    v
Cột BLOB / CLOB / kiểu SQL tương ứng
```

Luồng **có thể được driver đọc khi `executeUpdate()` chạy**, không nhất thiết ngay tại lời gọi `setBinaryStream(...)`. Vì vậy, phải giữ nguồn dữ liệu mở và có thể đọc được đến khi thao tác thực thi hoàn tất.

## 2. Các overload cần biết khi gán luồng

`PreparedStatement` cung cấp nhiều overload để ứng dụng lựa chọn theo loại cột và thông tin độ dài:

| API | Loại nguồn | Ý nghĩa |
| --- | --- | --- |
| `setBinaryStream(index, inputStream)` | `InputStream` | Gửi byte, không khai báo trước độ dài |
| `setBinaryStream(index, inputStream, longLength)` | `InputStream` | Gửi byte với số byte dự kiến |
| `setBlob(index, inputStream)` | `InputStream` | Gán dữ liệu kiểu SQL `BLOB` từ nguồn byte |
| `setBlob(index, inputStream, longLength)` | `InputStream` | Gán `BLOB` với độ dài byte |
| `setCharacterStream(index, reader)` | `Reader` | Gửi dữ liệu ký tự khi không biết trước số ký tự |
| `setCharacterStream(index, reader, longLength)` | `Reader` | Gửi dữ liệu ký tự với số ký tự dự kiến |
| `setClob(index, reader)` | `Reader` | Gán kiểu SQL `CLOB` từ nguồn ký tự |
| `setClob(index, reader, longLength)` | `Reader` | Gán `CLOB` với số ký tự dự kiến |

Trong bảng, `longLength` chỉ giá trị kiểu `long`; không phải tên tham số thực tế trong Java. Những overload không truyền độ dài và các overload nhận `long` thuộc các phiên bản JDBC hiện đại, thông dụng từ JDBC 4.0. Driver cũ có thể chỉ hỗ trợ một số overload hoặc ném `SQLFeatureNotSupportedException`.

**Chọn theo kiểu cột:** Với cột `BLOB`, `setBlob(...)` thể hiện ý định rõ ràng. `setBinaryStream(...)` cũng thường được driver hỗ trợ cho dữ liệu nhị phân, nhưng các ràng buộc chuyển đổi kiểu có thể khác. Tương tự, `setClob(...)` rõ nghĩa với `CLOB`, còn `setCharacterStream(...)` có ích cho các kiểu văn bản lớn mà driver chấp nhận.

Các phương thức `setBytes(index, byte[])` và `setString(index, String)` vẫn phù hợp với nội dung nhỏ, đã nằm sẵn trong bộ nhớ. Với tệp rất lớn, tránh tạo mảng byte hoặc `String` khổng lồ chỉ để dùng hai phương thức đó.

## 3. Tạo bảng minh họa và định nghĩa hợp đồng dữ liệu

Giả sử ứng dụng có hai loại dữ liệu:

```sql
-- Cú pháp SQL minh họa: điều chỉnh cho hệ quản trị đang dùng.
CREATE TABLE attachment (
    id          BIGINT PRIMARY KEY,
    file_name   VARCHAR(255) NOT NULL,
    media_type  VARCHAR(100) NOT NULL,
    content     BLOB NOT NULL
);

CREATE TABLE article_document (
    id          BIGINT PRIMARY KEY,
    body        CLOB NOT NULL
);
```

Một số DB dùng `BYTEA`, `VARBINARY(MAX)`, `TEXT` hoặc loại LOB riêng thay cho `BLOB`/`CLOB`. Không nên giả định câu DDL này chạy nguyên xi trên mọi sản phẩm. Kiểm tra giới hạn kích thước của cột, driver và giao thức DB trước khi nhận tệp lớn.

Hợp đồng của ứng dụng nên nêu rõ:

- `attachment.content` lưu **byte gốc**; tải xuống phải khôi phục được chính xác nội dung đã tải lên.
- `article_document.body` lưu **ký tự**; byte trong tệp nguồn được giải mã bằng charset xác định, ví dụ UTF-8.
- `file_name` và `media_type` là metadata, không dùng làm bằng chứng rằng nội dung byte thật sự thuộc một định dạng nào đó.
- Giới hạn kích thước, định dạng được phép và nơi xác thực đầu vào phải được thiết kế rõ ràng trước khi thực thi SQL.

## 4. Ghi BLOB từ tệp bằng `setBinaryStream` có độ dài

Ví dụ sau nhận một `Path`, mở luồng từ tệp, gán độ dài bằng `Files.size(...)` rồi ghi dữ liệu với `PreparedStatement`.

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.Objects;
import javax.sql.DataSource;

public final class AttachmentRepository {
    private final DataSource dataSource;

    public AttachmentRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public void insert(long id, String fileName, String mediaType, Path file)
            throws IOException, SQLException {
        Objects.requireNonNull(file);
        Objects.requireNonNull(fileName);
        Objects.requireNonNull(mediaType);

        long byteCount = Files.size(file);
        String sql = """
                INSERT INTO attachment (id, file_name, media_type, content)
                VALUES (?, ?, ?, ?)
                """;

        try (Connection connection = dataSource.getConnection();
             InputStream input = Files.newInputStream(file);
             PreparedStatement ps = connection.prepareStatement(sql)) {

            ps.setLong(1, id);
            ps.setString(2, fileName);
            ps.setString(3, mediaType);
            ps.setBinaryStream(4, input, byteCount);

            int updated = ps.executeUpdate();
            if (updated != 1) {
                throw new SQLException(
                        "INSERT cần ảnh hưởng đúng một dòng: " + updated);
            }
        }
    }
}
```

Ví dụ dùng SQL *text block* (Java 15+); có thể thay bằng chuỗi thông thường ở Java cũ. Các tham số `?` giữ riêng giá trị dữ liệu khỏi câu SQL, tránh ghép byte hoặc tên tệp vào SQL. `try-with-resources` đóng `PreparedStatement` trước `InputStream`, rồi đóng hoặc trả `Connection` cho pool.

Giá trị `Files.size(file)` có kiểu `long` và đại diện cho **số byte** của tệp tại lúc kiểm tra. Với `setBinaryStream`, độ dài được truyền là số byte, không phải số ký tự. Ở những driver cũ chỉ hỗ trợ overload nhận `int`, không được ép `long` thành `int` nếu tệp có thể vượt `Integer.MAX_VALUE`.

**Giới hạn thực tế:** Giữa `Files.size` và lúc driver đọc, tệp có thể đã thay đổi. Nếu số byte thực không khớp với độ dài khai báo, driver có thể báo lỗi, đọc thiếu hoặc xử lý khác tùy cơ sở dữ liệu. Với tải lên quan trọng, hãy dùng nguồn bất biến trong thời gian ghi, xác minh kích thước, checksum và kiểm soát việc thay đổi tệp nguồn.

## 5. Khi không biết trước độ dài: overload không có `length`

Nguồn dữ liệu từ HTTP, object storage hoặc một luồng được tạo khi xử lý có thể không cung cấp tổng số byte đáng tin cậy. Khi driver hỗ trợ, dùng overload không có độ dài:

```java
import java.io.InputStream;
import java.io.IOException;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public void saveFromStream(
        DataSource dataSource, long id, String fileName,
        String mediaType, InputStream source)
        throws IOException, SQLException {
    String sql = """
            INSERT INTO attachment (id, file_name, media_type, content)
            VALUES (?, ?, ?, ?)
            """;

    // Phương thức nhận quyền sở hữu source và sẽ đóng sau khi executeUpdate().
    try (InputStream input = source;
         Connection connection = dataSource.getConnection();
         PreparedStatement ps = connection.prepareStatement(sql)) {
        ps.setLong(1, id);
        ps.setString(2, fileName);
        ps.setString(3, mediaType);
        ps.setBinaryStream(4, input);
        ps.executeUpdate();
    }
}
```

Đoạn mã minh họa cách truyền `InputStream` trực tiếp. Trong API thực tế, phải quyết định rõ **ai sở hữu trách nhiệm đóng `source`**: phương thức nhận luồng có thể đóng nó như ví dụ, hoặc để bên gọi quản lý, nhưng không nên đóng hai lần khi luồng gắn với một tài nguyên có vòng đời riêng.

**Không dùng `input.available()` để đo tổng độ dài.** `available()` chỉ ước lượng số byte có thể đọc mà không bị chặn ở thời điểm gọi, không phải kích thước toàn bộ luồng. Với nguồn không biết kích thước, nếu driver không hỗ trợ overload không có `length`, cần chuyển nguồn vào bộ lưu trữ tạm có giới hạn để biết tổng độ dài rồi mở lại một luồng mới, hoặc chọn cách ghi dữ liệu lớn được driver hỗ trợ.

Đừng mặc định `setBinaryStream(index, input)` sẽ tự chuyển dữ liệu theo từng chunk ở cấp giao thức. Driver có thể cần đệm nội dung để tính độ dài hoặc tối ưu statement; việc **không truyền length** không đồng nghĩa **không tốn bộ nhớ**.

## 6. Ghi văn bản dài bằng `Reader` và `setClob`

Với văn bản tiếng Việt, mục tiêu là lưu **ký tự**, không phải dãy byte từ một tệp. `Reader` cho phép giải mã nội dung theo charset ở ranh giới nguồn dữ liệu.

```java
import java.io.IOException;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public void insertArticle(
        DataSource dataSource, long id, Path utf8File)
        throws IOException, SQLException {
    String sql =
            "INSERT INTO article_document (id, body) VALUES (?, ?)";

    try (Connection connection = dataSource.getConnection();
         Reader reader = Files.newBufferedReader(
                 utf8File, StandardCharsets.UTF_8);
         PreparedStatement ps = connection.prepareStatement(sql)) {
        ps.setLong(1, id);
        ps.setClob(2, reader);
        ps.executeUpdate();
    }
}
```

`Files.newBufferedReader(..., UTF_8)` giải mã byte của tệp theo UTF-8 thành ký tự Java. Sau đó, `setClob(...)` yêu cầu driver lưu dữ liệu ký tự vào cột `CLOB`. Khi dùng cột văn bản dài khác `CLOB`, `setCharacterStream(2, reader)` có thể phù hợp nếu driver hỗ trợ kiểu đích.

**Không truyền `Files.size(utf8File)` làm `length` của `setClob` hoặc `setCharacterStream`.** `Files.size` đếm byte, còn overload nhận `Reader` yêu cầu số ký tự. Một chữ tiếng Việt có dấu hoặc ký tự ngoài ASCII có thể chiếm nhiều byte trong UTF-8. Việc đếm ký tự chính xác còn phải theo quy ước mà API/driver sử dụng; nếu chưa có số ký tự đã xác minh, dùng overload không truyền độ dài.

Với cột SQL mang kiểu quốc gia `NCLOB`, có thể sử dụng `setNClob(index, reader)` hoặc `setNCharacterStream(index, reader)` khi DB/driver hỗ trợ. Không phải DB nào cũng có kiểu `NCLOB` riêng; đừng chọn phương thức chỉ dựa vào việc văn bản có Unicode mà bỏ qua kiểu cột thật.

## 7. Quản lý vòng đời của `InputStream` và `Reader`

Một lỗi phổ biến là đóng nguồn ngay sau khi gọi `setBinaryStream`:

```java
// SAI: driver có thể chưa đọc dữ liệu tại thời điểm setBinaryStream.
InputStream input = Files.newInputStream(file);
ps.setBinaryStream(1, input);
input.close();
ps.executeUpdate(); // Có thể thất bại vì stream đã đóng.
```

Trình tự đúng:

```text
Mở nguồn và PreparedStatement
         |
         v
Gán InputStream/Reader vào tham số ?
         |
         v
executeUpdate()/execute() hoặc executeBatch()
         |
         v
Đợi JDBC thực thi xong, kiểm tra lỗi/update count
         |
         v
Đóng ResultSet (nếu có), Statement, InputStream/Reader
         |
         v
Kết thúc transaction và trả Connection đúng phạm vi quản lý
```

Các quy tắc cần nhớ:

1. **Giữ luồng mở cho đến khi statement thực thi xong.** Một số driver chỉ bắt đầu đọc trong `execute...()`.
2. **Một luồng đầu vào có trạng thái vị trí đọc.** Nếu đã đọc đến cuối, không thể giả định có thể gọi `executeUpdate()` lần nữa với cùng luồng và nhận cùng dữ liệu. Mở lại luồng mới khi cần thực thi lại.
3. **Không chia sẻ một luồng giữa nhiều yêu cầu đồng thời.** Dùng nguồn độc lập theo mỗi thao tác và để mỗi luồng có vòng đời rõ ràng.
4. **Đóng cả khi có lỗi.** `try-with-resources` xử lý các nhánh exception tốt hơn việc chỉ đóng trong nhánh thành công.
5. **Không cần nạp trước toàn bộ tệp.** `Files.readAllBytes(file)` hoặc `Files.readString(file)` rồi bọc bằng `ByteArrayInputStream`/`StringReader` vẫn đưa toàn bộ dữ liệu vào bộ nhớ; nó không giải quyết mục tiêu giảm heap.

Nếu nguồn là request HTTP hay stream của dịch vụ khác, quyết định rõ bên gọi hay repository chịu trách nhiệm đóng stream. Không để statement còn dùng luồng sau khi tầng web đã đóng request.

## 8. Luồng, transaction và lỗi giữa chừng

Ghi LOB là một thao tác dữ liệu của DB và chịu các quy tắc transaction giống các lệnh `INSERT`/`UPDATE` khác. Nếu nghiệp vụ vừa tạo bản ghi metadata vừa ghi dữ liệu LOB hoặc liên kết nhiều bảng, hãy đặt các lệnh liên quan **trong cùng transaction** khi DB hỗ trợ:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try (InputStream input = Files.newInputStream(file);
         PreparedStatement ps = connection.prepareStatement(
                 "UPDATE attachment SET content = ? WHERE id = ?")) {
        ps.setBinaryStream(1, input, Files.size(file));
        ps.setLong(2, attachmentId);

        if (ps.executeUpdate() != 1) {
            throw new SQLException("Không cập nhật đúng một đính kèm");
        }
        connection.commit();
    } catch (SQLException | IOException | RuntimeException failure) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
        throw failure;
    }
}
```

Đoạn này minh họa transaction do phương thức sở hữu, giả định `dataSource` trả kết nối mới có chế độ tự động commit phù hợp; với connection pool hoặc framework, phải tuân theo hợp đồng quản lý transaction và khôi phục trạng thái kết nối trước khi tái sử dụng. Mẫu trong dự án production nên xử lý thêm tình huống `commit()` thất bại và trạng thái transaction không rõ ràng; không tự động retry một thao tác tạo dữ liệu lớn nếu không có cơ chế chống trùng.

Nếu đọc luồng bị lỗi giữa lúc `executeUpdate()` chạy, driver có thể báo `SQLException` (và có thể gói lỗi nguồn). Câu lệnh có thể đã chuyển một phần dữ liệu đến DB; rollback transaction là bước cần thiết nếu toàn bộ thao tác phải nguyên tử. **Không suy ra rằng JDBC tự hủy toàn bộ transaction chỉ vì có exception**; và không giả định mọi engine đều có cùng cơ chế transaction đối với LOB.

Với đối tượng `BLOB`/`CLOB` dùng locator do DB tạo, vòng đời tài nguyên và transaction có thể khác cách truyền trực tiếp bằng `InputStream`/`Reader`. Bài này ưu tiên truyền luồng vào statement; nếu dùng locator, đọc kỹ tài liệu driver và quản lý `free()` khi cần.

## 9. Batch với dữ liệu lớn: cẩn trọng việc giữ luồng

`PreparedStatement.addBatch()` cho phép gửi nhiều bộ tham số, nhưng khi tham số là luồng dữ liệu lớn, không được cho rằng driver đã tiêu thụ chúng tại `addBatch()`.

```java
// SAI: stream có thể bị đóng trước lúc executeBatch() đọc dữ liệu.
for (Path file : files) {
    try (InputStream input = Files.newInputStream(file)) {
        ps.setBinaryStream(1, input);
        ps.addBatch();
    }
}
ps.executeBatch();
```

Để batch thực sự an toàn, mỗi phần tử cần nguồn riêng còn mở cho đến lúc `executeBatch()` hoàn tất, hoặc một cơ chế của driver **đã được xác minh** là tiêu thụ dữ liệu ngay khi thêm vào batch. Ví dụ tổ chức tài nguyên theo lô:

```java
List<InputStream> opened = new ArrayList<>();
try {
    for (Path file : files) {
        InputStream input = Files.newInputStream(file);
        opened.add(input);
        ps.setBinaryStream(1, input, Files.size(file));
        ps.addBatch();
    }

    int[] counts = ps.executeBatch();
    // Kiểm tra counts/BatchUpdateException, commit/rollback ở tầng sở hữu.
} finally {
    // Đóng theo chiều ngược sau khi executeBatch() kết thúc hoặc lỗi.
    for (int i = opened.size() - 1; i >= 0; i--) {
        try {
            opened.get(i).close();
        } catch (IOException closeFailure) {
            // Tích hợp với cơ chế ghi nhận lỗi/cleanup của ứng dụng.
        }
    }
}
```

Đoạn minh họa giả định `ps` đã được chuẩn bị, `files` và các kiểu `List`/`ArrayList`/`Path`/`InputStream`/`Files`/`IOException` đã được import. Trong code thực tế, cần giữ hoặc gắn *suppressed exception* cho lỗi đóng stream nếu việc đóng thất bại, tránh làm mất lỗi chính. Không nên tạo lô quá lớn: nhiều luồng mở đồng thời có thể dùng nhiều file descriptor; driver có thể đệm tất cả dữ liệu batch trong RAM.

Với LOB rất lớn, **thực thi từng dòng trong transaction hoặc chia thành các lô nhỏ** có thể dễ kiểm soát tài nguyên hơn batch lớn. Benchmark trên đúng DB/driver và đo heap, số kết nối, file descriptor và throughput trước khi chọn phương án.

## 10. Lỗi thường gặp và cách khắc phục

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng `Files.readAllBytes` cho tệp rất lớn | Heap tăng đột biến, dễ `OutOfMemoryError` | Dùng `InputStream` trực tiếp hoặc nguồn streaming có giới hạn |
| Đóng luồng trước `executeUpdate` | Driver đọc từ stream đã đóng | Giữ nguồn mở đến khi thực thi xong |
| Gọi `setBinaryStream` rồi thực thi lại cùng stream đã tiêu thụ | Thiếu dữ liệu hoặc lỗi EOF | Mở một stream mới cho mỗi lần thử |
| Dùng `setAsciiStream` cho văn bản Unicode | Sai ký tự hoặc mất dữ liệu | Dùng `Reader`, `setCharacterStream`/`setClob` với charset rõ ràng |
| Dùng `Files.size` làm độ dài của `Reader` | Nhầm số byte với số ký tự | Dùng overload không có độ dài hoặc tính đúng số ký tự |
| Ép độ dài `long` thành `int` | Tràn số, gán sai length | Dùng overload `long` nếu driver hỗ trợ và kiểm tra giới hạn DB |
| Dùng `InputStream.available()` để ước lượng độ dài tệp | Có thể khai báo độ dài thấp hơn thực tế | Dùng `Files.size` cho tệp ổn định; không biết length thì chọn overload thích hợp |
| Giả định `setBinaryStream` không bao giờ đệm toàn bộ tệp | Tốn RAM dù code không tạo `byte[]` | Đo bộ nhớ và kiểm thử với DB/driver thực |
| Dùng cùng luồng cho nhiều phần tử batch | Stream có thể đã hết hoặc bị driver giữ lại | Tạo stream riêng và giữ đến sau `executeBatch` |
| Quên rollback khi ghi lỗi giữa chừng | Dữ liệu metadata/LOB có thể không nhất quán | Dùng transaction, kiểm tra exception và rollback |
| Không giới hạn kích thước nguồn tải lên | Cạn dung lượng DB, disk hoặc file descriptor | Áp dụng quota, timeout và giới hạn upload |
| Ghi tệp lớn vào loại cột không phù hợp | Lỗi chuyển kiểu, cắt dữ liệu hoặc không hỗ trợ | Xác nhận BLOB/CLOB và tính năng driver |

## 11. Kiểm tra tính khả chuyển và hiệu năng

JDBC cung cấp các API chuẩn nhưng không bảo đảm mọi driver tối ưu và giới hạn giống nhau. Trước khi triển khai, cần kiểm chứng:

1. **Kiểu cột và dữ liệu:** DB có hỗ trợ kích thước BLOB/CLOB mong muốn? Kiểu `BLOB`/`CLOB` có cần cú pháp riêng không?
2. **Overload:** Driver hỗ trợ `setBinaryStream`/`setClob` có `length` và không có `length` không? Có ném `SQLFeatureNotSupportedException` với cột cụ thể không?
3. **Round-trip:** Ghi tệp nhị phân rồi đọc lại bằng `ResultSet.getBinaryStream(...)` hoặc `getBlob(...)`, tính hash để so byte; ghi văn bản Unicode rồi so nội dung ký tự sau đọc.
4. **Nguồn bất thường:** Stream kết thúc sớm, mất kết nối, lỗi đọc, tệp thay đổi kích thước trong quá trình ghi; ứng dụng xử lý exception và rollback ra sao?
5. **Kích thước:** Thử tệp nhỏ, tệp vài trăm MB và các kích thước sát giới hạn môi trường; đo heap, native memory, mạng và thời gian thực thi.
6. **Concurrency:** Nhiều upload đồng thời có khiến pool kết nối cạn, tăng GC, giữ transaction quá lâu hoặc làm DB quá tải không?
7. **Batch:** Nếu dùng `addBatch()` với stream, thử nhiều phần tử, thất bại giữa lô, update counts và mức dùng bộ nhớ trước khi phụ thuộc vào tính năng.
8. **Bảo mật:** Kiểm tra giới hạn kích thước, quyền truy cập, định dạng nội dung, xử lý mã độc theo yêu cầu dự án và tránh đưa nội dung tệp vào log.

### Đọc lại tệp đã lưu để kiểm chứng byte

Ví dụ minh họa cách tải BLOB từ `ResultSet` ra tệp mà không gọi `getBytes()` cho toàn bộ nội dung:

```java
import java.io.InputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public void download(
        DataSource dataSource, long id, Path output)
        throws IOException, SQLException {
    String sql = "SELECT content FROM attachment WHERE id = ?";

    try (Connection connection = dataSource.getConnection();
         PreparedStatement ps = connection.prepareStatement(sql)) {
        ps.setLong(1, id);

        try (ResultSet rs = ps.executeQuery()) {
            if (!rs.next()) {
                throw new IllegalArgumentException("Không tìm thấy đính kèm");
            }

            try (InputStream content = rs.getBinaryStream("content")) {
                if (content == null) {
                    throw new IllegalStateException("Cột content là NULL");
                }
                Files.copy(content, output);
            }
            // Không gọi rs.next() hay đóng ResultSet trước khi đọc xong stream.
        }
    }
}
```

Trong ví dụ, `Files.copy(...)` mặc định báo lỗi nếu `output` đã tồn tại; nên chọn đường dẫn đầu ra có kiểm soát. Đối với kiểm chứng, tính checksum (ví dụ SHA-256) của tệp nguồn và tệp tải xuống rồi so sánh. Việc đọc lại phải thực hiện với quyền và transaction phù hợp; đừng chỉ so `Files.size` vì hai tệp cùng kích thước vẫn có thể khác nội dung.

## 12. Thực hành: lưu tệp nhị phân và văn bản lớn

Hãy xây dựng một chức năng lưu tài liệu qua JDBC với hai loại đầu vào:

1. Tệp nhị phân `report.pdf` chứa byte bất kỳ.
2. Tệp `article.txt` UTF-8 có văn bản tiếng Việt và ký tự ngoài ASCII.

Thực hiện các bước:

- Tạo hai bảng `attachment` và `article_document` tương ứng với DB đang dùng; kiểm tra giới hạn kiểu LOB.
- Ghi `report.pdf` bằng `setBinaryStream(..., Files.size(file))`, sau đó thử `setBlob(..., InputStream)` trên cùng driver. So sánh kết quả và hiệu năng.
- Ghi `article.txt` bằng `Reader` và `setClob(...)`; thử `setCharacterStream(...)` nếu cột/driver hỗ trợ.
- Đọc lại bằng `getBinaryStream`/`getCharacterStream`, đối chiếu byte hoặc ký tự. Ghi nhận sự khác nhau giữa số byte UTF-8 và số ký tự.
- Thử một lần cố ý đóng stream trước `executeUpdate()` trong môi trường test để quan sát lỗi và cách JDBC báo lỗi; không dùng kết quả này để dự đoán mọi driver.
- Tạo nguồn lớn hơn bộ đệm nhỏ của ứng dụng và đo heap khi có nhiều yêu cầu đồng thời. Xác minh driver có đệm toàn bộ dữ liệu không.
- Thử transaction chứa cập nhật metadata và nội dung LOB; giả lập lỗi trước commit và kiểm tra rollback.

**Tự kiểm tra:** Vì sao `setBinaryStream` nhận `InputStream` nhưng `setClob` nhận `Reader`? Vì sao `Files.size` không thể truyền trực tiếp làm số ký tự của văn bản UTF-8? Điều gì xảy ra nếu đóng stream trước `executeBatch()`? Một chương trình không dùng `readAllBytes` đã chắc chắn dùng bộ nhớ hằng số chưa? Khi thao tác upload thất bại giữa chừng, ai chịu trách nhiệm rollback và đóng stream?

**Ghi nhớ:** Trong JDBC, dùng `InputStream` với `setBinaryStream`/`setBlob` cho dữ liệu nhị phân lớn, và `Reader` với `setCharacterStream`/`setClob` cho văn bản lớn. Giữ luồng mở đến khi statement thực thi hoàn tất, chọn overload độ dài theo đúng đơn vị byte/ký tự, quản lý kết nối và transaction rõ ràng, rồi **đo và kiểm chứng trên driver/DB thật** vì API streaming không tự bảo đảm chi phí bộ nhớ hoặc mức hỗ trợ giống nhau ở mọi hệ thống.
