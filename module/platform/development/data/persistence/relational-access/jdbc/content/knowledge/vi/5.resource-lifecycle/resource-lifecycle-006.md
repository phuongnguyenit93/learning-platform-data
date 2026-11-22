# Đóng luồng dữ liệu và giải phóng tài nguyên LOB trong JDBC

Trong **JDBC (Java Database Connectivity API for relational database access)**, truy vấn một cột văn bản hay nhị phân lớn thường cần nhiều tài nguyên hơn việc đọc một số nguyên. Ngoài `Connection`, `PreparedStatement` và `ResultSet`, ứng dụng có thể tạo thêm **luồng dữ liệu** (`InputStream`, `OutputStream`, `Reader`, `Writer`) và đối tượng **LOB** (`Blob`, `Clob`, `NClob`). Nếu không xác định ai chịu trách nhiệm đóng từng tài nguyên, ứng dụng có thể giữ kết nối quá lâu, rò rỉ tài nguyên của driver hoặc làm hỏng quá trình truyền dữ liệu.

Trong chương *Vòng đời tài nguyên*, bài này tập trung vào hai kỹ năng: **đóng luồng đúng thời điểm** và **gọi `free()` để giải phóng LOB** khi sử dụng giao diện LOB của JDBC. Hai thao tác liên quan với nhau nhưng không thay thế cho nhau.

## 1. LOB là gì và tại sao cần quản lý vòng đời?

**LOB (Large Object)** là dữ liệu lớn được lưu trong cột hoặc cơ chế lưu trữ do hệ quản trị cơ sở dữ liệu (DBMS) cung cấp. JDBC có các giao diện cơ bản:

| Giao diện / tài nguyên | Dữ liệu thường xử lý | Cách giải phóng |
| --- | --- | --- |
| `java.sql.Blob` | Dữ liệu nhị phân lớn: ảnh, tệp đính kèm | `blob.free()` |
| `java.sql.Clob` | Văn bản lớn: nội dung tài liệu | `clob.free()` |
| `java.sql.NClob` | Văn bản lớn ở dạng kiểu ký tự quốc gia (nếu DBMS hỗ trợ) | `nclob.free()` |
| `java.io.InputStream` | Đọc tuần tự các byte | `input.close()` |
| `java.io.OutputStream` | Ghi tuần tự các byte | `output.close()` |
| `java.io.Reader` | Đọc tuần tự ký tự | `reader.close()` |
| `java.io.Writer` | Ghi tuần tự ký tự | `writer.close()` |

`Blob`/`Clob` là **đối tượng JDBC mô tả giá trị LOB**, có thể được driver hiện thực bằng dữ liệu lưu đệm, tham chiếu đến dữ liệu trong DBMS hoặc cơ chế riêng khác. Đối tượng LOB có thể giữ tài nguyên ở phía client và/hoặc database. `InputStream`/`Reader` là **kênh đọc** dữ liệu; một LOB có thể tạo ra luồng đọc qua `getBinaryStream()` hoặc `getCharacterStream()`.

Ví dụ, câu SQL minh họa một bảng có hai cột lớn:

```sql
CREATE TABLE stored_document (
    id BIGINT PRIMARY KEY,
    binary_data BLOB,
    text_data CLOB
);
```

**Lưu ý tính tương thích:** `BLOB` và `CLOB` được dùng ở đây để giải thích mô hình. Các DBMS có kiểu cột và cơ chế LOB riêng: PostgreSQL thường dùng `BYTEA`/`TEXT` hoặc hệ large object dựa trên OID; MySQL có `BLOB`/`LONGTEXT`; Oracle cung cấp `BLOB`/`CLOB`. Không giả định một đoạn DDL hoặc một getter LOB hoạt động giống nhau trên mọi driver.

## 2. Ba vòng đời phải quản lý riêng

Ứng dụng JDBC thường phải phối hợp ít nhất ba nhóm tài nguyên:

1. **Kết nối và câu lệnh:** `Connection` → `PreparedStatement` → `ResultSet`. Kết nối mở cho phép driver trao đổi với DBMS; result set tồn tại trong phạm vi câu lệnh phù hợp.
2. **Giá trị LOB:** `Blob`/`Clob` lấy từ `ResultSet` hoặc tạo bằng `Connection.createBlob()`/`createClob()`. Khi không còn dùng, gọi `free()` để giải phóng tài nguyên mà đối tượng LOB giữ.
3. **Luồng dữ liệu:** `InputStream`/`Reader` đọc nội dung LOB và `OutputStream`/`Writer` ghi dữ liệu đến tệp hay nơi nhận. Mỗi luồng cần được đóng theo quyền sở hữu của ứng dụng.

Sơ đồ thứ tự xử lý một BLOB:

```text
Connection
  └── PreparedStatement
       └── ResultSet
            └── Blob
                 └── InputStream ──> OutputStream ──> tệp

Khi hoàn tất:
1. Đọc xong dữ liệu.
2. Đóng InputStream và OutputStream.
3. Gọi Blob.free().
4. Đóng ResultSet.
5. Đóng PreparedStatement.
6. Đóng/hoàn trả Connection theo phạm vi sở hữu.
```

Thứ tự trên là **quy tắc an toàn để thiết kế mã**, không phải lời khẳng định rằng mọi driver buộc phải giữ các tài nguyên theo chính xác một cơ chế. Để tránh phụ thuộc hành vi cụ thể, hãy **tiêu thụ luồng khi result set, statement và connection vẫn còn mở**. Với LOB dựa trên locator, đọc sau khi đóng transaction/kết nối có thể thất bại.

## 3. `close()` khác `free()` ở điểm nào?

| Thao tác | Đối tượng | Tác dụng chính | Không nên suy luận |
| --- | --- | --- | --- |
| `InputStream.close()`, `Reader.close()` | Luồng đọc | Kết thúc và giải phóng tài nguyên của luồng | Đã tự gọi `Blob.free()`/`Clob.free()` |
| `OutputStream.close()`, `Writer.close()` | Luồng ghi | Kết thúc luồng, đẩy/đóng dữ liệu theo cơ chế đích | Đã commit giao dịch SQL |
| `Blob.free()`, `Clob.free()`, `NClob.free()` | Đối tượng LOB JDBC | Giải phóng tài nguyên mà LOB đang giữ; LOB không còn sử dụng được | Xóa dữ liệu đã lưu trong bảng |
| `ResultSet.close()` | Kết quả JDBC | Đóng result set và giải phóng tài nguyên liên quan | Mọi luồng/LOB có thể tiếp tục đọc sau đó |
| `Statement.close()` | Statement JDBC | Đóng statement và thường đóng result set hiện tại | Connection được đóng theo |
| `Connection.close()` | Kết nối JDBC | Giải phóng kết nối hoặc trả về pool | LOB/luồng trước đó vẫn hợp lệ |

**`Blob` và `Clob` không phải `AutoCloseable`** nên không thể đặt trực tiếp vào khai báo `try-with-resources` như `InputStream`. Chúng có phương thức riêng `free()` (JDBC 4.0 trở lên). Thực hành phổ biến là giữ chúng trong khối `try` và gọi `free()` trong `finally`.

Sau khi gọi `free()`, không tiếp tục sử dụng LOB để gọi `length()`, `getBinaryStream()`, `getCharacterStream()` hay các thao tác đọc/ghi khác. Driver có thể từ chối bằng `SQLException`. `free()` chỉ giải phóng **đối tượng LOB ở tầng JDBC**, không tương đương `DELETE`, `UPDATE` hoặc thao tác dọn dữ liệu phía DBMS.

## 4. Đọc BLOB lớn ra tệp: đóng stream trước, `free()` sau

Ví dụ này giả định kết nối JDBC hiện có, bảng `stored_document` có cột `binary_data` tương thích với `Blob`, và driver hỗ trợ `ResultSet.getBlob()`. Phương thức xuất nội dung nhị phân ra tệp mà **không giữ toàn bộ tệp trong một mảng `byte[]`**:

```java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Blob;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class BlobExporter {
    private BlobExporter() {}

    public static void export(
            Connection connection, long documentId, Path destination)
            throws SQLException, IOException {

        String sql =
                "SELECT binary_data FROM stored_document WHERE id = ?";

        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, documentId);

            try (ResultSet result = statement.executeQuery()) {
                if (!result.next()) {
                    throw new SQLException("Khong tim thay tai lieu");
                }

                Blob blob = result.getBlob("binary_data");
                if (blob == null) {
                    throw new SQLException("Tai lieu co binary_data NULL");
                }

                try {
                    try (InputStream input = blob.getBinaryStream();
                         OutputStream output =
                                 Files.newOutputStream(destination)) {

                        byte[] buffer = new byte[64 * 1024];
                        int count;
                        while ((count = input.read(buffer)) != -1) {
                            output.write(buffer, 0, count);
                        }
                    } // Dong luong doc va luong ghi truoc khi free LOB.
                } finally {
                    blob.free(); // Co gang free ke ca khi doc/ghi loi.
                }
            }
        }
    }
}
```

Phân tích vòng đời:

- **`PreparedStatement` và `ResultSet`** vẫn mở trong suốt thời gian đọc.
- **`Blob.getBinaryStream()`** trả luồng đọc nội dung BLOB; ví dụ chỉ cấp bộ đệm 64 KiB, nên kích thước bộ đệm của mã ứng dụng không tăng theo kích thước tệp. Driver có thể dùng bộ nhớ đệm riêng, vì thế không suy ra lượng RAM sử dụng toàn hệ thống luôn đúng 64 KiB.
- **`try-with-resources`** đảm bảo đóng cả luồng đọc và ghi nếu `read()` hay `write()` phát sinh `IOException`. Cần kiểm tra dung lượng tệp và quyền ghi thư mục trước khi đưa mã vào sản phẩm.
- **`finally`** gọi `blob.free()` sau khi các stream kết thúc, kể cả khi đang lan truyền lỗi. `free()` có thể ném `SQLException`; với hệ thống cần giữ nguyên cả lỗi truyền dữ liệu lẫn lỗi giải phóng, hãy bổ sung cơ chế lưu lỗi thứ cấp bằng `addSuppressed()`.
- **`Connection` do bên gọi cung cấp** nên phương thức không tự đóng connection. Bên gọi phải quản lý nó trong `try-with-resources` hoặc theo transaction manager.

Không giữ `Blob` và `InputStream` trong field để đọc sau khi phương thức trả về. Luồng gắn với result set, driver hoặc transaction có thể không còn hợp lệ tại thời điểm đó.

## 5. Khi nào chỉ cần `ResultSet.getBinaryStream()`?

Với một số cột nhị phân, ứng dụng có thể đọc luồng **trực tiếp từ `ResultSet`** mà không tạo đối tượng `Blob`:

```java
String sql = "SELECT binary_data FROM stored_document WHERE id = ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, documentId);

    try (ResultSet result = statement.executeQuery()) {
        if (!result.next()) {
            throw new SQLException("Khong tim thay tai lieu");
        }

        InputStream stream = result.getBinaryStream("binary_data");
        if (stream == null) {
            throw new SQLException("binary_data la SQL NULL");
        }

        try (InputStream input = stream;
             OutputStream output = Files.newOutputStream(destination)) {
            byte[] buffer = new byte[8192];
            int count;
            while ((count = input.read(buffer)) != -1) {
                output.write(buffer, 0, count);
            }
        }
    }
}
```

Đoạn ví dụ này được đặt **bên trong phương thức** có các biến `connection`, `documentId`, `destination` và có khai báo/điều khiển `SQLException`, `IOException`; cần import các kiểu tương ứng từ `java.sql`, `java.io` và `java.nio.file`.

Trường hợp này **không có đối tượng `Blob` trong mã để gọi `free()`**. Ứng dụng vẫn phải đóng luồng trả về, result set, statement và connection đúng phạm vi. Đọc luồng trực tiếp thường dễ hơn khi mục tiêu chỉ là sao chép dữ liệu tuần tự.

**Chú ý thời điểm đọc:** Với các getter dạng stream của `ResultSet`, việc gọi getter khác hoặc chuyển hàng bằng `next()` có thể khiến driver đóng luồng đang mở; theo hợp đồng JDBC, luồng được trả về từ một cột có thể bị đóng ngầm khi đọc giá trị cột khác. Hãy **đọc xong và đóng stream của hàng hiện tại trước khi truy cập cột tiếp theo hoặc chuyển hàng** nếu muốn tránh kết quả phụ thuộc driver.

## 6. Ghi tệp lớn vào cột BLOB bằng `setBinaryStream()`

Không cần tạo mảng `byte[]` bằng `Files.readAllBytes()` khi tệp có thể rất lớn. `PreparedStatement.setBinaryStream()` cho phép driver đọc dữ liệu từ luồng khi thực thi câu lệnh:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public final class BlobImporter {
    private BlobImporter() {}

    public static int insert(
            Connection connection, long documentId, Path source)
            throws SQLException, IOException {

        String sql =
                "INSERT INTO stored_document (id, binary_data) VALUES (?, ?)";
        long length = Files.size(source);

        try (InputStream input = Files.newInputStream(source);
             PreparedStatement statement = connection.prepareStatement(sql)) {

            statement.setLong(1, documentId);
            statement.setBinaryStream(2, input, length);
            return statement.executeUpdate();
        }
    }
}
```

**Điều quan trọng là giữ `input` mở cho đến sau `executeUpdate()`.** Một số driver chỉ tiêu thụ luồng trong lúc thực thi. Nếu tự đóng stream ngay sau `setBinaryStream()` nhưng trước `executeUpdate()`, việc truyền dữ liệu có thể bị lỗi.

Trong ví dụ, `Files.size(source)` trả **số byte** của tệp tại thời điểm đọc metadata. Tệp cần được giữ ổn định trong khi gửi để giá trị độ dài khớp dữ liệu thực. Có overload `setBinaryStream(index, input)` không truyền độ dài; khả năng hoạt động và cách xử lý kích thước lớn có thể phụ thuộc driver. Đừng giả định driver sẽ tự đóng luồng do ứng dụng tạo; dùng `try-with-resources`.

Đóng luồng **không đồng nghĩa commit**: với `autoCommit=false`, bên gọi vẫn phải `commit()` hoặc `rollback()` transaction. Nếu thao tác ghi thất bại, xử lý transaction theo chính sách ứng dụng; không chỉ đóng stream rồi coi dữ liệu đã được lưu thành công.

## 7. Xử lý CLOB: `Reader` và `Writer` thay cho byte stream

Đối với dữ liệu văn bản lớn, `Clob.getCharacterStream()` trả về một `Reader` để đọc **ký tự**. Dùng `Writer` để ghi text ra tệp theo encoding mong muốn. Tránh tự chuyển các byte thành chuỗi bằng charset mặc định của máy.

Ví dụ xuất một `CLOB` ra tệp UTF-8:

```java
import java.io.IOException;
import java.io.Reader;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Clob;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class ClobExporter {
    private ClobExporter() {}

    public static void exportText(
            Connection connection, long documentId, Path destination)
            throws SQLException, IOException {

        String sql = "SELECT text_data FROM stored_document WHERE id = ?";

        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, documentId);

            try (ResultSet result = statement.executeQuery()) {
                if (!result.next()) {
                    throw new SQLException("Khong tim thay tai lieu");
                }

                Clob clob = result.getClob("text_data");
                if (clob == null) {
                    throw new SQLException("text_data la SQL NULL");
                }

                try {
                    try (Reader input = clob.getCharacterStream();
                         Writer output = Files.newBufferedWriter(
                                 destination, StandardCharsets.UTF_8)) {

                        char[] buffer = new char[8192];
                        int count;
                        while ((count = input.read(buffer)) != -1) {
                            output.write(buffer, 0, count);
                        }
                    }
                } finally {
                    clob.free();
                }
            }
        }
    }
}
```

Luồng được đóng **trước** `clob.free()`. `StandardCharsets.UTF_8` xác định cách **tệp đích** được mã hóa; DBMS/driver chịu trách nhiệm ánh xạ kiểu ký tự từ CLOB sang các ký tự Java.

Đối với cột ký tự được hỗ trợ, cũng có thể dùng `ResultSet.getCharacterStream("text_data")` trực tiếp và chỉ đóng `Reader`, `Writer`, `ResultSet`, `Statement`. Khi sử dụng `NClob`, có thể dùng `getNClob()` và `free()` theo cùng nguyên tắc, với điều kiện hệ quản trị và driver hỗ trợ kiểu dữ liệu tương ứng.

### Ghi text lớn bằng `setCharacterStream()`

```java
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.PreparedStatement;

try (Reader input = Files.newBufferedReader(source, StandardCharsets.UTF_8);
     PreparedStatement statement = connection.prepareStatement(
             "UPDATE stored_document SET text_data = ? WHERE id = ?")) {

    statement.setCharacterStream(1, input);
    statement.setLong(2, documentId);
    statement.executeUpdate();
}
```

Ở đoạn trên, `source` là `Path` đến tệp UTF-8, `documentId` là `long` và `connection` là `Connection` có sẵn; đoạn mã nằm trong phương thức xử lý `IOException` và `SQLException`. Stream vẫn mở đến lúc `executeUpdate()` kết thúc.

**Không lấy `Files.size(source)` rồi mặc định đó là số ký tự để truyền cho overload `setCharacterStream(index, reader, length)`.** `Files.size()` tính **byte**, trong khi `Reader` và tham số length của `setCharacterStream` làm việc theo **ký tự Java**. Với UTF-8, nhiều ký tự tiếng Việt chiếm hơn một byte. Nếu không biết chính xác số ký tự và driver hỗ trợ, overload không có length sẽ phù hợp hơn.

## 8. LOB tạo trong ứng dụng: `createBlob()` và `createClob()`

Đôi khi ứng dụng muốn tạo đối tượng LOB trước khi gán nó vào `PreparedStatement`:

```java
import java.sql.Blob;
import java.sql.PreparedStatement;

Blob blob = connection.createBlob();
try {
    blob.setBytes(1, "small example".getBytes(
            java.nio.charset.StandardCharsets.UTF_8));

    try (PreparedStatement statement = connection.prepareStatement(
            "UPDATE stored_document SET binary_data = ? WHERE id = ?")) {
        statement.setBlob(1, blob);
        statement.setLong(2, documentId);
        statement.executeUpdate();
    }
} finally {
    blob.free();
}
```

`connection.createBlob()` và `connection.createClob()` là phương thức JDBC chuẩn, nhưng driver có thể hạn chế hoặc không hỗ trợ. Ví dụ dùng chuỗi nhỏ để minh họa `setBytes()`; với tệp lớn, lựa chọn `setBinaryStream()` thường tránh tạo bản sao dữ liệu trong heap ứng dụng.

Nếu dùng `blob.setBinaryStream(1)` để ghi vào LOB được tạo, phải đóng luồng ghi sau khi gửi xong dữ liệu và trước khi gọi `free()`. Tương tự, `clob.setCharacterStream(1)` trả `Writer` cần được đóng. Tài liệu driver sẽ cho biết chi tiết cơ chế lưu trữ, đồng bộ dữ liệu và giới hạn của LOB được tạo.

**Điểm chung:** dù LOB xuất phát từ `ResultSet.getBlob()` hay `Connection.createBlob()`, nếu ứng dụng sở hữu đối tượng và không còn sử dụng nó, cần gọi `free()`. Không dựa vào garbage collector để quyết định thời điểm giải phóng tài nguyên database.

## 9. Giao dịch, connection pool và LOB locator

Một số driver trả về **LOB locator**: đối tượng Java đại diện cho vị trí/giá trị LOB phía database, thay vì giữ tất cả byte/ký tự trong bộ nhớ. Locator có thể phụ thuộc vào **connection**, **transaction** và vòng đời statement/result set.

Những quy tắc thực hành quan trọng:

- **Không trả connection về pool khi còn luồng LOB đang được đọc.** `Connection.close()` trên connection lấy từ pool thường trả connection về pool, khiến luồng gắn với kết nối đó có thể mất hiệu lực hoặc làm rối việc sử dụng lại connection.
- **Không commit hoặc rollback giữa lúc đọc locator nếu chưa biết rõ hành vi DBMS.** Một số hệ quản trị gắn hiệu lực locator với transaction. Hãy đọc xong trong phạm vi transaction thích hợp.
- **Không đọc LOB sau khi `ResultSet`/`Statement` đã đóng** trừ khi tài liệu driver bảo đảm cách sử dụng đó. Cách an toàn là xử lý LOB hoàn toàn bên trong phạm vi của result set.
- **Không chia sẻ cùng một `Blob`, `Clob` hoặc stream giữa các request/luồng xử lý.** Quản lý một luồng cho một đơn vị công việc cụ thể và giải phóng ngay khi xong.
- **Giải phóng LOB không xóa dữ liệu trong DBMS.** Nếu cần loại bỏ tệp đã lưu trong bảng, phải thực hiện SQL thích hợp trong transaction nghiệp vụ.

Với PostgreSQL, cần đặc biệt phân biệt **`BYTEA`** (giá trị nhị phân trực tiếp trong cột) và **large object theo OID**. PostgreSQL JDBC có hành vi riêng với `getBlob()`/large-object API; không tự giả định một cột `BYTEA` được đọc đúng bằng `getBlob()` trong mọi trường hợp. Tương tự, cách đọc CLOB từ `TEXT` hay kiểu riêng của DBMS phải được kiểm tra theo driver. Khi chỉ muốn lấy nội dung của cột nhị phân/ký tự, các getter luồng trực tiếp có thể phù hợp hơn nếu driver hỗ trợ.

## 10. Xử lý ngoại lệ khi đóng tài nguyên

Một nguyên tắc hữu ích của `try-with-resources` là Java vẫn cố đóng tài nguyên đã mở khi phần xử lý bên trong ném exception. Nếu cả xử lý và đóng tài nguyên đều thất bại, exception lúc đóng thường được ghi thành **suppressed exception** trên lỗi chính.

```java
try (InputStream input = Files.newInputStream(source);
     OutputStream output = Files.newOutputStream(destination)) {

    byte[] buffer = new byte[8192];
    int count;
    while ((count = input.read(buffer)) != -1) {
        output.write(buffer, 0, count);
    }
}
```

Đoạn mã nằm trong phương thức xử lý `IOException`; `source` và `destination` là `Path`. Không cần gọi `input.close()`/`output.close()` thủ công trong cả nhánh thành công và nhánh lỗi.

Vì `Blob`/`Clob` không phải `AutoCloseable`, lời gọi `free()` ở `finally` vẫn có thể sinh **`SQLException`** khác với lỗi đọc/ghi. Trong hệ thống yêu cầu chẩn đoán đầy đủ, có thể bắt lỗi giải phóng riêng rồi gắn nó vào lỗi xử lý chính bằng `addSuppressed()` hoặc ghi log phù hợp, đồng thời bảo đảm không nuốt mất lỗi gốc.

Đừng đặt việc giải phóng LOB **chỉ sau lệnh xử lý thành công**:

```java
// Khong an toan: neu copy() nem IOException, blob.free() bi bo qua.
copy(blob.getBinaryStream(), destination);
blob.free();
```

Thay bằng `try-with-resources` cho stream và `finally` cho `free()`, như ví dụ xuất BLOB ở trên.

## 11. Các lỗi phổ biến và cách khắc phục

| Lỗi | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Chỉ đóng `ResultSet`, không đóng luồng do ứng dụng giữ | Luồng có thể giữ bộ đệm, descriptor hoặc tài nguyên driver | Đóng `InputStream`/`Reader` bằng `try-with-resources` |
| Chỉ đóng stream, không gọi `Blob.free()`/`Clob.free()` | Đối tượng LOB có thể giữ tài nguyên chưa được giải phóng | Gọi `free()` trong `finally` |
| Gọi `free()` khi vẫn đang đọc stream | Luồng có thể bị mất hiệu lực | Đọc xong, đóng stream rồi mới `free()` |
| Đọc LOB sau khi đóng connection hoặc trả về pool | Locator/stream có thể không còn hợp lệ | Đọc trong phạm vi connection, transaction và result set còn mở |
| Dùng `getBytes()` hoặc `Files.readAllBytes()` cho tệp rất lớn | Cấp phát mảng lớn, tăng áp lực bộ nhớ | Dùng `getBinaryStream()`/`setBinaryStream()` với bộ đệm giới hạn |
| Đóng stream đầu vào trước `executeUpdate()` | Driver có thể chưa tiêu thụ dữ liệu, gây ghi lỗi hoặc thiếu | Giữ stream mở đến khi lệnh hoàn thành |
| Dùng độ dài byte làm độ dài ký tự CLOB | Có thể sai số ký tự, đặc biệt với Unicode | Dùng overload phù hợp; phân biệt byte/character |
| Gọi getter khác của `ResultSet` trước khi đọc hết stream | Stream có thể bị đóng hoặc phần còn lại bị bỏ | Đọc trọn stream trước khi truy cập cột/hàng khác |
| Cho rằng `free()` xóa tệp trong database | Dữ liệu vẫn còn trong bảng | Thực hiện `DELETE`/`UPDATE` riêng khi có yêu cầu |
| Không xử lý exception khi giải phóng | Khó phát hiện lỗi tài nguyên; có thể che lỗi chính | Theo dõi lỗi `close()`/`free()` và giữ thông tin chẩn đoán |

## 12. Tự kiểm tra

**Câu 1.** Đọc dữ liệu bằng `Blob.getBinaryStream()` và đã đóng `InputStream`. Có cần gọi `Blob.free()` không?

*Gợi ý:* Có, nếu ứng dụng đang sở hữu đối tượng `Blob` và đã dùng xong. Đóng stream và giải phóng LOB là hai thao tác khác nhau.

**Câu 2.** Một tệp 3 GB được đưa vào `PreparedStatement.setBinaryStream()`. Có thể đóng `InputStream` ngay sau lệnh `setBinaryStream()` không?

*Gợi ý:* Không. Driver có thể chưa đọc dữ liệu cho tới khi `executeUpdate()`/`execute()` chạy xong. Hãy giữ stream mở trong toàn bộ thời gian thực thi.

**Câu 3.** Tại sao không nên đọc `Blob` sau khi trả `Connection` về connection pool?

*Gợi ý:* LOB locator có thể phụ thuộc connection và transaction. Connection đã được pool cấp cho công việc khác; việc đọc tiếp có thể lỗi hoặc không an toàn.

**Câu 4.** Nếu dùng `ResultSet.getBinaryStream()` trực tiếp, có cần gọi `Blob.free()` không?

*Gợi ý:* Không có đối tượng `Blob` để gọi `free()`. Nhưng vẫn cần đóng stream, result set, statement và connection đúng phạm vi.

**Câu 5.** Có thể dùng `Files.size(textFile)` làm `length` cho `setCharacterStream()` không?

*Gợi ý:* Không suy luận như vậy. `Files.size()` trả byte, còn `Reader` đọc ký tự; với UTF-8 nhiều ký tự sử dụng nhiều byte.

## Ghi nhớ

Trong JDBC, vòng đời tài nguyên LOB phải được xử lý **theo thứ tự và theo quyền sở hữu**: lấy `ResultSet` → đọc `Blob`/`Clob` hoặc stream → xử lý toàn bộ dữ liệu → đóng stream → `free()` đối tượng LOB (nếu có) → đóng result set/statement → đóng hoặc hoàn trả connection. Dùng `try-with-resources` cho luồng và tài nguyên JDBC `AutoCloseable`; dùng `finally` cho `Blob.free()`/`Clob.free()`. Với dữ liệu lớn, ưu tiên truyền tuần tự thay vì tải toàn bộ vào bộ nhớ; với LOB locator, luôn kiểm tra yêu cầu về connection, transaction và driver cụ thể.
