# Đọc ghi CLOB/BLOB dạng luồng và đóng tài nguyên đúng vòng đời

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** Oracle JDBC  
> **Mục tiêu:** Đọc và ghi LOB lớn bằng JDBC streaming APIs; phân biệt CLOB, NCLOB và BLOB; chọn giữa bind stream trực tiếp và LOB locator; xử lý encoding và độ dài; quản lý transaction, connection, statement, result set, stream và locator đúng vòng đời; tránh tải toàn bộ LOB vào heap; xây dựng code an toàn với connection pool và xử lý lỗi.

## 1. Vì sao phải streaming LOB?

Oracle Database hỗ trợ lưu dữ liệu lớn trong các kiểu LOB:

- **CLOB:** dữ liệu ký tự theo database character set.
- **NCLOB:** dữ liệu ký tự theo national character set.
- **BLOB:** dữ liệu nhị phân.
- **BFILE:** locator trỏ tới file nhị phân bên ngoài database, chỉ đọc qua cơ chế Oracle hỗ trợ.

Một hàng có thể chứa tài liệu PDF, ảnh, video, nội dung HTML/XML/JSON dài, văn bản hợp đồng hoặc dữ liệu nhị phân lớn. Khi ứng dụng đọc hoặc ghi các giá trị này, cách xử lý ảnh hưởng trực tiếp đến bộ nhớ JVM, network traffic, thời gian giữ connection và transaction.

Nếu dùng cách tải toàn bộ nội dung vào bộ nhớ:

- CLOB có thể bị chuyển thành một String rất lớn.
- BLOB có thể bị chuyển thành một byte array rất lớn.
- Nhiều request đồng thời có thể làm heap tăng nhanh.
- Garbage collection có thể kéo dài.
- Ứng dụng có thể gặp OutOfMemoryError.
- Connection và transaction có thể bị giữ lâu trong lúc copy.

Streaming xử lý dữ liệu theo từng phần nhỏ. Thay vì giữ toàn bộ LOB trong heap, ứng dụng đọc hoặc ghi qua Reader/Writer hoặc InputStream/OutputStream.

~~~text
Không streaming:

Database LOB
     |
     v
JDBC driver
     |
     v
String / byte[] lớn trong heap
     |
     v
Ứng dụng xử lý

Streaming:

Database LOB
     |
     v
JDBC stream
     |
     v
Buffer nhỏ, lặp nhiều lần
     |
     v
File / HTTP response / Writer / OutputStream
~~~

Streaming không có nghĩa là không dùng bộ nhớ đệm. JDBC driver và ứng dụng vẫn có buffer, nhưng lượng dữ liệu giữ đồng thời có thể được giới hạn.

## 2. Phân biệt CLOB, NCLOB, BLOB và BFILE

| Kiểu | Nội dung | JDBC API thường dùng | Đơn vị độ dài |
|---|---|---|---|
| CLOB | Ký tự theo database character set | Clob, Reader, Writer | Ký tự |
| NCLOB | Ký tự theo national character set | NClob, Reader, Writer | Ký tự |
| BLOB | Byte nhị phân | Blob, InputStream, OutputStream | Byte |
| BFILE | File nhị phân ngoài database | BFILE locator/Oracle extension | Byte |

### 2.1. CLOB là dữ liệu ký tự

CLOB phù hợp với văn bản dài như:

- Nội dung bài viết.
- XML/JSON.
- Nội dung email.
- Tài liệu văn bản.
- Nội dung HTML.

JDBC đọc CLOB bằng Reader và ghi bằng Writer hoặc bind Reader vào PreparedStatement.

Không dùng getString() cho CLOB rất lớn nếu mục tiêu là streaming. getString() tạo String trong heap và có thể làm tăng memory pressure.

### 2.2. NCLOB và Unicode

NCLOB lưu dữ liệu theo national character set. JDBC cung cấp NClob và các API như getNCharacterStream/setNCharacterStream trong những trường hợp phù hợp.

Không tự chuyển mọi CLOB thành NCLOB chỉ vì dữ liệu có Unicode. Database character set hiện đại thường hỗ trợ Unicode; lựa chọn datatype cần theo schema và yêu cầu tương thích.

### 2.3. BLOB là byte, không phải text

BLOB dùng cho nội dung nhị phân như PDF, ảnh, audio, video, file nén hoặc dữ liệu mã hóa.

Dùng InputStream và OutputStream. Không dùng Reader/Writer cho BLOB vì chuyển đổi byte thành ký tự có thể làm hỏng dữ liệu.

Nếu lưu text trong BLOB, ứng dụng phải định nghĩa encoding rõ ràng, ví dụ UTF-8, và tự chuyển đổi giữa byte stream và character stream. Không dựa vào charset mặc định của JVM.

### 2.4. BFILE khác BLOB

BFILE là locator tới file bên ngoài database. Database không lưu nội dung file trong segment BFILE và BFILE được truy cập theo cơ chế read-only. Nó có yêu cầu DIRECTORY object và quyền filesystem phía database server.

Bài này tập trung vào CLOB/BLOB lưu trong database. Không dùng BFILE thay cho BLOB nếu ứng dụng cần transaction và backup semantics của dữ liệu LOB trong database.

## 3. Bảng ví dụ

Ví dụ bảng lưu tài liệu:

~~~sql
CREATE TABLE document_store (
    document_id   NUMBER PRIMARY KEY,
    document_name VARCHAR2(255) NOT NULL,
    text_body     CLOB,
    binary_body   BLOB,
    created_at    TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);
~~~

Một hàng có thể lưu một trong hai dạng nội dung tùy nghiệp vụ. Trong thiết kế thực tế, có thể tách metadata và LOB, hoặc tách loại tài liệu thành bảng riêng để quản lý quyền, retention và lifecycle.

### 3.1. NULL và EMPTY_CLOB/EMPTY_BLOB

Cột LOB có thể có giá trị NULL hoặc một LOB rỗng:

- NULL: chưa có locator/nội dung LOB.
- EMPTY_CLOB(): có LOB locator hợp lệ với độ dài 0.
- EMPTY_BLOB(): có BLOB locator hợp lệ với độ dài 0.

Phân biệt này quan trọng khi cập nhật qua locator. Nếu cột NULL, getClob/getBlob có thể trả null; không thể gọi setCharacterStream hoặc setBinaryStream trên locator null.

Ví dụ khởi tạo LOB rỗng:

~~~sql
INSERT INTO document_store (
    document_id,
    document_name,
    text_body,
    binary_body
)
VALUES (
    1001,
    'contract',
    EMPTY_CLOB(),
    EMPTY_BLOB()
);
~~~

Không phải mọi thao tác ghi stream đều cần locator trước đó; bind Reader/InputStream trực tiếp vào INSERT/UPDATE thường đơn giản hơn.

## 4. Các JDBC streaming API chính

### 4.1. Đọc CLOB

- ResultSet.getCharacterStream(column): trả Reader.
- ResultSet.getClob(column): trả Clob locator.
- Clob.getCharacterStream(): trả Reader.
- Clob.length(): độ dài ký tự.
- Clob.getSubString(position, length): tải một đoạn thành String; phù hợp với đoạn nhỏ.

### 4.2. Ghi CLOB

- PreparedStatement.setCharacterStream(index, reader): bind character stream.
- PreparedStatement.setClob(index, clob): bind Clob object.
- PreparedStatement.setClob(index, reader, length): bind Reader với độ dài đã biết, tùy JDBC/driver overload.
- Clob.setCharacterStream(position): lấy Writer để ghi từ vị trí LOB.
- Clob.truncate(length): cắt LOB về độ dài chỉ định.

### 4.3. Đọc BLOB

- ResultSet.getBinaryStream(column): trả InputStream.
- ResultSet.getBlob(column): trả Blob locator.
- Blob.getBinaryStream(): trả InputStream.
- Blob.length(): số byte.
- Blob.getBytes(position, length): tải một đoạn thành byte array; chỉ nên dùng với đoạn nhỏ.

### 4.4. Ghi BLOB

- PreparedStatement.setBinaryStream(index, inputStream): bind binary stream.
- PreparedStatement.setBlob(index, blob): bind Blob object.
- PreparedStatement.setBlob(index, inputStream, length): bind stream có độ dài, tùy JDBC/driver overload.
- Blob.setBinaryStream(position): lấy OutputStream để ghi.
- Blob.truncate(length): cắt BLOB về độ dài chỉ định.

Các overload phụ thuộc JDBC API và Oracle JDBC driver version. Kiểm tra phiên bản driver trong ứng dụng; tránh dùng một overload không được driver hỗ trợ.

## 5. Streaming khác với tải toàn bộ LOB

Không nên làm với LOB lớn:

~~~java
Clob clob = rs.getClob("TEXT_BODY");
String text = clob.getSubString(1, (int) clob.length());

Blob blob = rs.getBlob("BINARY_BODY");
byte[] bytes = blob.getBytes(1, (int) blob.length());
~~~

Vấn đề:

- CLOB/BLOB có thể lớn hơn giới hạn của int-based API.
- Toàn bộ dữ liệu được tạo thành object trong heap.
- Nhiều request đồng thời nhân dung lượng memory cần thiết.
- Việc tạo thêm String/byte[] có thể nhân đôi hoặc tăng nhiều lần memory footprint.
- Không thể xử lý dữ liệu theo luồng đến file hoặc HTTP output một cách tự nhiên.

Dùng getCharacterStream/getBinaryStream hoặc locator stream để xử lý theo buffer.

Không dùng InputStream.available() để đo tổng kích thước dữ liệu. available() chỉ là số byte có thể đọc mà không phải chờ trong một số implementation, không phải tổng chiều dài BLOB.

## 6. Hàm copy theo buffer

Các hàm copy là nền tảng để streaming. Dùng buffer vừa phải, ví dụ 8 KB đến 64 KB, rồi đo thực tế theo workload.

### 6.1. Copy ký tự

~~~java
import java.io.IOException;
import java.io.Reader;
import java.io.Writer;

public static long copyCharacters(Reader source, Writer target)
        throws IOException {

    char[] buffer = new char[16 * 1024];
    long total = 0;
    int count;

    while ((count = source.read(buffer)) != -1) {
        target.write(buffer, 0, count);
        total += count;
    }

    return total;
}
~~~

Buffer là mảng char nên số đếm là số ký tự Java được đọc, không phải số byte UTF-8.

### 6.2. Copy byte

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

public static long copyBytes(InputStream source, OutputStream target)
        throws IOException {

    byte[] buffer = new byte[16 * 1024];
    long total = 0;
    int count;

    while ((count = source.read(buffer)) != -1) {
        target.write(buffer, 0, count);
        total += count;
    }

    return total;
}
~~~

Buffer là mảng byte nên số đếm là byte. Không chuyển BLOB thành String trong quá trình copy.

### 6.3. Có cần flush không?

Khi ghi qua Writer/OutputStream, đóng stream thường flush dữ liệu trước khi giải phóng. Có thể gọi flush khi cần gửi dữ liệu sớm tới downstream, nhưng không thay thế close.

Với stream do JDBC cung cấp để ghi LOB, đóng Writer/OutputStream trước khi commit là bước quan trọng để hoàn tất thao tác ghi theo driver.

## 7. Đọc CLOB bằng Reader

Ví dụ đọc CLOB trực tiếp từ ResultSet:

~~~java
import java.io.IOException;
import java.io.Reader;
import java.io.Writer;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public static long readClob(
        Connection connection,
        long documentId,
        Writer destination
) throws SQLException, IOException {

    String sql =
        "SELECT text_body FROM document_store WHERE document_id = ?";

    try (PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setLong(1, documentId);

        try (ResultSet resultSet = statement.executeQuery()) {
            if (!resultSet.next()) {
                throw new SQLException("Document not found");
            }

            try (Reader reader = resultSet.getCharacterStream(1)) {
                if (reader == null) {
                    return 0L;
                }

                return copyCharacters(reader, destination);
            }
        }
    }
}
~~~

Trong ví dụ:

- PreparedStatement được đóng.
- ResultSet được đóng sau khi đọc xong.
- Reader được đóng bằng try-with-resources.
- Writer destination thuộc caller nên method không đóng nó.
- Connection thuộc caller nên method không đóng hoặc commit connection.

Reader được tiêu thụ trong khi ResultSet, Statement và Connection còn mở. Không trả Reader ra khỏi method rồi đóng ResultSet/Connection trước khi caller đọc.

### 7.1. Đọc CLOB ra file UTF-8

~~~java
import java.io.BufferedWriter;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

try (Writer output = Files.newBufferedWriter(
        outputPath,
        StandardCharsets.UTF_8
)) {
    long characters = readClob(connection, documentId, output);
    System.out.println("Characters copied: " + characters);
}
~~~

UTF-8 được chỉ định ở phía file. JDBC Reader đã cung cấp ký tự Java; không tự decode Reader như byte stream.

Không ghi file vào một path không được kiểm soát từ input user. File output cũng cần quota, quyền filesystem và retention phù hợp.

## 8. Đọc BLOB bằng InputStream

Ví dụ:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public static long readBlob(
        Connection connection,
        long documentId,
        OutputStream destination
) throws SQLException, IOException {

    String sql =
        "SELECT binary_body FROM document_store WHERE document_id = ?";

    try (PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setLong(1, documentId);

        try (ResultSet resultSet = statement.executeQuery()) {
            if (!resultSet.next()) {
                throw new SQLException("Document not found");
            }

            try (InputStream input = resultSet.getBinaryStream(1)) {
                if (input == null) {
                    return 0L;
                }

                return copyBytes(input, destination);
            }
        }
    }
}
~~~

### 8.1. Đọc BLOB ra file

~~~java
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

try (OutputStream output = Files.newOutputStream(
        outputPath,
        StandardOpenOption.CREATE,
        StandardOpenOption.TRUNCATE_EXISTING,
        StandardOpenOption.WRITE
)) {
    long bytes = readBlob(connection, documentId, output);
    System.out.println("Bytes copied: " + bytes);
}
~~~

Nếu file đích đã tồn tại, TRUNCATE_EXISTING xóa nội dung cũ trước khi ghi. Chỉ dùng khi hành vi ghi đè là chủ đích. Với file quan trọng, có thể ghi vào file tạm rồi atomic move sau khi hoàn tất và xác minh.

### 8.2. Streaming tới HTTP response

Trong web application, có thể copy BLOB trực tiếp tới ServletOutputStream hoặc response output stream để tránh tạo byte array lớn.

Cần:

- Giữ JDBC connection và ResultSet mở trong suốt quá trình stream.
- Thiết lập content type, content length nếu biết và content disposition.
- Không đóng output stream do servlet container sở hữu nếu framework quản lý lifecycle.
- Xử lý client disconnect.
- Đảm bảo connection được trả về pool sau khi stream kết thúc.
- Đặt timeout và giới hạn số download đồng thời.

Một download kéo dài có thể giữ connection database lâu. Cần đo tải và cân nhắc lưu file vào object storage nếu download lớn, thường xuyên hoặc kéo dài.

## 9. Ghi CLOB bằng PreparedStatement.setCharacterStream

Đối với INSERT/UPDATE thông thường, bind Reader trực tiếp thường là cách đơn giản:

~~~java
import java.io.Reader;
import java.nio.file.Files;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public static int insertTextDocument(
        Connection connection,
        long documentId,
        String documentName,
        java.nio.file.Path sourcePath
) throws Exception {

    String sql =
        "INSERT INTO document_store " +
        "(document_id, document_name, text_body) " +
        "VALUES (?, ?, ?)";

    try (Reader reader = Files.newBufferedReader(
            sourcePath, StandardCharsets.UTF_8);
         PreparedStatement statement = connection.prepareStatement(sql)) {

        statement.setLong(1, documentId);
        statement.setString(2, documentName);
        statement.setCharacterStream(3, reader);

        return statement.executeUpdate();
    }
}
~~~

Driver tiêu thụ Reader khi executeUpdate chạy. Reader phải còn mở trong toàn bộ thời gian thực thi statement.

Nếu driver hoặc API yêu cầu độ dài, dùng overload có length được hỗ trợ. Với Reader, length là số ký tự theo contract JDBC, không phải số byte của file UTF-8. Không truyền Files.size(path) làm character length cho Reader chứa Unicode.

### 9.1. UPDATE CLOB

~~~java
String sql =
    "UPDATE document_store SET text_body = ? WHERE document_id = ?";

try (Reader reader = Files.newBufferedReader(
        sourcePath, StandardCharsets.UTF_8);
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setCharacterStream(1, reader);
    statement.setLong(2, documentId);

    int updated = statement.executeUpdate();

    if (updated != 1) {
        throw new SQLException("Expected exactly one document row");
    }
}
~~~

Với transaction do ứng dụng quản lý, commit sau khi statement và input stream đã hoàn tất. Nếu cập nhật không đúng số hàng, rollback theo transaction contract.

### 9.2. Overload có length

JDBC có các overload nhận Reader và length. Ví dụ:

~~~java
statement.setCharacterStream(parameterIndex, reader, characterLength);
~~~

Dùng long length nếu driver hỗ trợ overload JDBC tương ứng. Với phiên bản cũ có thể chỉ có overload int. Nếu không biết số ký tự trước mà vẫn muốn streaming, dùng overload không có length khi driver hỗ trợ.

Đừng đọc toàn bộ file chỉ để đếm ký tự nếu điều đó phá mục tiêu streaming. Có thể dùng file format/metadata đã biết hoặc API không yêu cầu length.

## 10. Ghi BLOB bằng PreparedStatement.setBinaryStream

Ví dụ INSERT file nhị phân:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.PreparedStatement;

public static int insertBinaryDocument(
        Connection connection,
        long documentId,
        String documentName,
        Path sourcePath
) throws Exception {

    String sql =
        "INSERT INTO document_store " +
        "(document_id, document_name, binary_body) " +
        "VALUES (?, ?, ?)";

    try (InputStream input = Files.newInputStream(sourcePath);
         PreparedStatement statement = connection.prepareStatement(sql)) {

        statement.setLong(1, documentId);
        statement.setString(2, documentName);
        statement.setBinaryStream(3, input, Files.size(sourcePath));

        return statement.executeUpdate();
    }
}
~~~

Files.size trả số byte, phù hợp với binary stream length. Nếu file có thể thay đổi trong lúc đọc, kích thước đã lấy trước có thể không còn đúng; nên dùng file bất biến trong thời gian upload hoặc overload không length nếu driver hỗ trợ.

### 10.1. UPDATE BLOB

~~~java
String sql =
    "UPDATE document_store SET binary_body = ? WHERE document_id = ?";

try (InputStream input = Files.newInputStream(sourcePath);
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setBinaryStream(1, input, Files.size(sourcePath));
    statement.setLong(2, documentId);

    int updated = statement.executeUpdate();

    if (updated != 1) {
        throw new SQLException("Expected exactly one document row");
    }
}
~~~

Đối với dữ liệu lớn, theo dõi network, transaction duration, redo generation và storage throughput. Streaming giảm heap nhưng không loại bỏ chi phí I/O và redo.

## 11. Ghi qua LOB locator và SELECT FOR UPDATE

Một cách khác là lấy locator của LOB trong hàng đã khóa rồi ghi qua stream từ locator.

Mô hình:

1. Bắt đầu transaction.
2. SELECT LOB column FOR UPDATE.
3. Lấy Clob/Blob locator.
4. Truncate nội dung cũ nếu cần thay toàn bộ.
5. Mở Writer/OutputStream từ locator.
6. Copy dữ liệu theo buffer.
7. Đóng stream.
8. Đóng ResultSet/Statement.
9. Commit transaction.
10. Giải phóng locator.

### 11.1. Cập nhật CLOB locator

~~~java
import java.io.IOException;
import java.io.Reader;
import java.io.Writer;
import java.sql.Clob;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public static void replaceClob(
        Connection connection,
        long documentId,
        Reader source
) throws SQLException, IOException {

    if (connection.getAutoCommit()) {
        throw new SQLException(
            "replaceClob requires an explicit transaction"
        );
    }

    Clob clob = null;

    try {
        String sql =
            "SELECT text_body FROM document_store " +
            "WHERE document_id = ? FOR UPDATE";

        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, documentId);

            try (ResultSet resultSet = statement.executeQuery()) {
                if (!resultSet.next()) {
                    throw new SQLException("Document not found");
                }

                clob = resultSet.getClob(1);

                if (clob == null) {
                    throw new SQLException(
                        "CLOB is NULL; initialize it before locator write"
                    );
                }

                clob.truncate(0L);

                try (Writer writer = clob.setCharacterStream(1L)) {
                    copyCharacters(source, writer);
                }
            }
        }

        connection.commit();

    } catch (SQLException | IOException | RuntimeException error) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            error.addSuppressed(rollbackError);
        }
        throw error;

    } finally {
        if (clob != null) {
            clob.free();
        }
    }
}
~~~

Method yêu cầu transaction rõ ràng và tự commit/rollback trong ví dụ. Trong ứng dụng thực tế, nên thống nhất ai sở hữu transaction: service layer hoặc DAO method. Không để nhiều tầng cùng commit một transaction mà không có contract.

Source Reader thuộc caller; method tiêu thụ nhưng không tự đóng source. Caller cần đóng Reader sau khi method hoàn tất.

Nếu cột CLOB đang NULL, khởi tạo bằng EMPTY_CLOB() trong cùng transaction trước khi SELECT FOR UPDATE, hoặc dùng bind stream trực tiếp vào UPDATE.

### 11.2. Cập nhật BLOB locator

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.sql.Blob;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public static void replaceBlob(
        Connection connection,
        long documentId,
        InputStream source
) throws SQLException, IOException {

    if (connection.getAutoCommit()) {
        throw new SQLException(
            "replaceBlob requires an explicit transaction"
        );
    }

    Blob blob = null;

    try {
        String sql =
            "SELECT binary_body FROM document_store " +
            "WHERE document_id = ? FOR UPDATE";

        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, documentId);

            try (ResultSet resultSet = statement.executeQuery()) {
                if (!resultSet.next()) {
                    throw new SQLException("Document not found");
                }

                blob = resultSet.getBlob(1);

                if (blob == null) {
                    throw new SQLException(
                        "BLOB is NULL; initialize it before locator write"
                    );
                }

                blob.truncate(0L);

                try (OutputStream output = blob.setBinaryStream(1L)) {
                    copyBytes(source, output);
                }
            }
        }

        connection.commit();

    } catch (SQLException | IOException | RuntimeException error) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            error.addSuppressed(rollbackError);
        }
        throw error;

    } finally {
        if (blob != null) {
            blob.free();
        }
    }
}
~~~

LOB locator là handle tới dữ liệu trong database. free() giải phóng tài nguyên locator phía JDBC; nó không xóa hàng hoặc xóa giá trị LOB đã commit.

Trong production, ghi log nếu free() thất bại nhưng không làm mất exception gốc. Có thể dùng helper cleanup để thêm exception phụ vào exception chính.

### 11.3. Vì sao cần SELECT FOR UPDATE?

Locator update yêu cầu hàng có LOB được cập nhật trong transaction phù hợp. SELECT FOR UPDATE khóa hàng để tránh transaction khác thay đổi cùng hàng trong lúc stream ghi.

Khóa có thể tồn tại trong toàn bộ thời gian copy. Với file rất lớn hoặc source chậm, lock duration tăng và transaction giữ tài nguyên lâu. Nếu có thể, bind stream trực tiếp trong một DML statement hoặc dùng staging/asynchronous workflow phù hợp để giảm thời gian khóa.

## 12. LOB locator và stream có vòng đời khác nhau

Clob/Blob locator không giống Reader/Writer hoặc InputStream/OutputStream.

- Locator là đối tượng JDBC đại diện tới LOB trong database.
- Stream là đường đọc/ghi nội dung LOB.
- Connection cung cấp session/database context.
- Transaction quyết định khóa và thời điểm thay đổi được commit/rollback.

Đóng stream không nhất thiết giải phóng locator. Gọi free() giải phóng locator object. Đóng ResultSet/Statement giải phóng cursor/statement resources. Đóng Connection trả hoặc đóng database session tùy connection pool.

Mỗi tài nguyên cần được quản lý đúng loại và đúng thứ tự.

## 13. Quy tắc vòng đời tài nguyên

Một thứ tự an toàn phổ biến khi đọc LOB:

1. Lấy Connection.
2. Tạo PreparedStatement.
3. Execute query.
4. Lấy ResultSet.
5. Mở Reader/InputStream.
6. Copy hết dữ liệu.
7. Đóng Reader/InputStream.
8. Đóng ResultSet.
9. Đóng PreparedStatement.
10. Trả Connection về pool.

Khi ghi qua locator:

1. Lấy Connection.
2. Bắt đầu transaction, tắt auto-commit.
3. SELECT FOR UPDATE.
4. Lấy Clob/Blob locator.
5. Mở Writer/OutputStream.
6. Ghi hết dữ liệu.
7. Đóng Writer/OutputStream.
8. Đóng ResultSet/Statement.
9. Commit hoặc rollback.
10. Gọi free() cho locator.
11. Reset connection state và trả Connection về pool.

Một số thứ tự cleanup có thể được điều chỉnh theo driver, nhưng không đóng Connection hoặc ResultSet khi stream vẫn còn đang được sử dụng.

### 13.1. Dùng try-with-resources

Các lớp sau thường triển khai AutoCloseable và phù hợp với try-with-resources:

- Connection.
- PreparedStatement.
- Statement.
- ResultSet.
- Reader/Writer.
- InputStream/OutputStream.

Clob và Blob không phải AutoCloseable theo JDBC interface thông thường; gọi free() trong finally sau khi stream đã đóng.

### 13.2. Không đóng tài nguyên do caller sở hữu

Một DAO nhận Connection từ service layer không nên tự đóng connection nếu contract nói caller sở hữu. Tương tự, method nhận Writer/OutputStream do web framework quản lý không nên đóng output stream đó.

Ghi rõ ownership:

| Tài nguyên | Thường do ai sở hữu? | Ai đóng? |
|---|---|---|
| Connection do DAO tự lấy | DAO | DAO |
| Connection truyền từ transaction manager | Caller/framework | Caller/framework |
| PreparedStatement tạo trong method | Method | Method |
| ResultSet tạo trong method | Method | Method |
| Reader từ ResultSet | Method đang đọc | Method |
| Reader truyền vào method | Caller | Caller, theo contract |
| Writer từ Clob locator | Method đang ghi | Method |
| ServletOutputStream | Web container/framework | Framework hoặc caller theo contract |
| Clob/Blob locator | Code lấy locator | Code đó gọi free() |

## 14. Transaction và auto-commit

### 14.1. Ghi qua bind stream

Với INSERT/UPDATE dùng setCharacterStream hoặc setBinaryStream, driver tiêu thụ input stream khi thực thi statement. Transaction commit sau khi statement hoàn tất và stream đã được đóng.

Nếu ứng dụng bật auto-commit, statement thành công có thể được commit tự động theo JDBC semantics. Điều này có thể phù hợp cho một DML đơn lẻ, nhưng không phù hợp nếu LOB write là một phần của nhiều thay đổi cần atomic.

### 14.2. Ghi qua locator

Với SELECT FOR UPDATE và locator stream, cần transaction tường minh:

~~~java
connection.setAutoCommit(false);

try {
    // SELECT ... FOR UPDATE
    // Ghi LOB và đóng stream
    connection.commit();
} catch (Exception error) {
    connection.rollback();
    throw error;
}
~~~

Không commit khi Writer/OutputStream vẫn đang mở. Đóng stream trước để driver hoàn tất thao tác ghi.

### 14.3. Giữ transaction ngắn

Không giữ transaction mở trong khi:

- Chờ người dùng upload file chậm.
- Đọc file từ network share không ổn định.
- Gọi HTTP service.
- Chờ message broker.
- Chờ xử lý antivirus lâu.
- Nén/mã hóa payload rất lớn nếu có thể làm trước transaction.

Có thể upload file vào staging storage trước, kiểm tra kích thước/hash/virus, sau đó stream vào database trong transaction ngắn hơn. Hoặc lưu object storage và chỉ lưu metadata/reference trong Oracle nếu kiến trúc phù hợp.

### 14.4. Rollback

Nếu lỗi xảy ra giữa lúc ghi:

- Đóng stream đang mở.
- Rollback transaction.
- Không trả connection đang có transaction dở dang về pool.
- Ghi log lỗi và document ID/correlation ID.
- Xác minh dữ liệu cũ còn nguyên theo transaction semantics.
- Chỉ retry khi source còn đọc lại được và operation có semantics an toàn.

Rollback không thay thế cleanup. Stream, ResultSet, Statement và locator vẫn phải được giải phóng.

## 15. Connection pool và trạng thái session

Ứng dụng thường dùng HikariCP, UCP hoặc connection pool của application server. Connection.close() trong môi trường pool thường trả logical connection về pool, không nhất thiết đóng physical database session.

Trước khi trả connection:

- Đã đóng tất cả Reader/InputStream/Writer/OutputStream.
- Đã đóng ResultSet và Statement.
- Transaction đã commit hoặc rollback.
- Auto-commit được khôi phục theo pool policy.
- Read-only/isolation/schema/catalog/session state không bị để lại ngoài dự kiến.
- Không còn LOB locator/stream đang dùng.
- Không còn task nền đang giữ reference tới connection.

Không trả connection về pool trong khi một thread khác vẫn đang đọc BLOB. Connection JDBC thường không được thiết kế để nhiều thread đồng thời dùng chung.

### 15.1. Connection leak

Nếu stream download không kết thúc hoặc client ngắt kết nối mà ứng dụng không cleanup, connection có thể bị giữ lâu.

Dấu hiệu:

- Pool active connections tăng.
- Idle connections giảm.
- Connection acquisition timeout.
- Request chờ pool.
- Database session tồn tại lâu.
- Cursor/transaction còn mở.

Dùng try-with-resources và timeout ở cả JDBC, web server và tầng network. Kiểm tra behavior khi client disconnect để bảo đảm finally/cleanup vẫn chạy.

### 15.2. Không giữ connection trong background callback

Không đưa ResultSet, Blob locator hoặc InputStream JDBC vào executor rồi trả connection về pool trước khi task hoàn tất. Tất cả các object đó phụ thuộc connection/session lifecycle.

Nếu cần asynchronous processing, worker phải sở hữu connection riêng trong toàn bộ thời gian stream và đóng nó sau khi hoàn tất.

## 16. Encoding và độ dài

### 16.1. CLOB: ký tự và byte khác nhau

CLOB lưu ký tự. Java Reader/Writer làm việc với ký tự Java. Khi đọc file UTF-8 vào Reader, CharsetDecoder chuyển byte thành ký tự.

Một ký tự Unicode có thể chiếm nhiều byte UTF-8. Vì vậy:

- Character count không bằng byte count.
- Reader length không nên được tính bằng Files.size() của file UTF-8.
- Content-Length HTTP tính byte, không phải số ký tự.
- Không tự chuyển CLOB sang byte mà không chỉ định charset.

### 16.2. BLOB: byte

BLOB lưu byte nguyên trạng. InputStream/OutputStream không diễn giải encoding.

Nếu BLOB chứa JSON UTF-8, phải decode bằng UTF-8 khi cần đọc text:

~~~java
try (InputStream input = blob.getBinaryStream();
     Reader reader = new java.io.InputStreamReader(
         input,
         java.nio.charset.StandardCharsets.UTF_8
     )) {
    // Đọc ký tự theo stream.
}
~~~

Không dùng Charset.defaultCharset() cho dữ liệu cần trao đổi ổn định giữa các host.

### 16.3. CLOB length và BLOB length

Clob.length() trả độ dài theo ký tự của LOB. Blob.length() trả độ dài byte. Đây là long, không nên ép sang int cho LOB lớn.

Các phương thức getSubString/getBytes có tham số length kiểu int ở JDBC interface thông thường, vì vậy không dùng chúng để materialize toàn bộ LOB lớn.

### 16.4. Supplementary characters

Java String dùng UTF-16 code units. Một Unicode code point ngoài Basic Multilingual Plane có thể chiếm hai char. Khi đếm ký tự hiển thị, code point và UTF-16 code unit có thể khác nhau.

Không dùng length() của String như một phép đo byte hoặc luôn coi nó là số ký tự người dùng nhìn thấy.

## 17. LOB prefetch và hiệu năng

Oracle JDBC hỗ trợ LOB prefetch để driver có thể lấy metadata và một phần dữ liệu LOB cùng lần fetch row. Điều này có thể cải thiện hiệu năng với LOB nhỏ thường xuyên được đọc.

Với LOB lớn:

- Prefetch quá lớn có thể làm tăng memory/network usage.
- Streaming vẫn cần thiết để xử lý dữ liệu lớn.
- Có thể điều chỉnh LOB prefetch ở connection/statement theo Oracle JDBC driver.
- Thử nghiệm với phân bố LOB size thực tế.
- Đo round-trip, heap, throughput và p95 latency.

LOB prefetch không đồng nghĩa tải toàn bộ LOB. Nó là tối ưu hóa phần dữ liệu ban đầu và metadata.

### 17.1. Fetch size không giống LOB prefetch

Statement fetch size thường điều khiển số hàng được lấy mỗi round-trip. LOB prefetch điều khiển việc lấy trước metadata/phần dữ liệu LOB.

Tăng fetch size có thể giảm round-trip khi đọc nhiều hàng, nhưng cũng tăng memory. Điều chỉnh cả hai theo workload và kích thước LOB.

### 17.2. Buffer size

Buffer 8 KB, 16 KB hoặc 64 KB là điểm bắt đầu để benchmark, không phải quy tắc tuyệt đối. Buffer lớn hơn có thể giảm số lần gọi read/write nhưng tăng memory mỗi stream.

Nếu có hàng trăm stream đồng thời, 64 KB mỗi stream có thể tạo memory đáng kể. Đo theo concurrency thực tế.

### 17.3. Parallel streaming

Không mặc định một JDBC Connection có thể được chia sẻ giữa nhiều thread để đọc nhiều LOB song song. Mỗi worker nên có connection/statement/resource ownership riêng.

Giới hạn số stream đồng thời bằng connection pool và application semaphore. Nếu downstream chậm, backpressure phải truyền ngược để không mở quá nhiều connection.

## 18. LOB locator, temporary LOB và free()

JDBC cung cấp Connection.createClob() và Connection.createBlob() để tạo LOB object tạm trong database theo driver implementation. Những object này có thể dùng khi cần chuẩn bị LOB trước khi bind, nhưng phải giải phóng bằng free().

Ví dụ:

~~~java
Clob temporaryClob = connection.createClob();

try {
    try (Writer writer = temporaryClob.setCharacterStream(1L)) {
        copyCharacters(sourceReader, writer);
    }

    try (PreparedStatement statement = connection.prepareStatement(
            "INSERT INTO document_store(document_id, text_body) VALUES (?, ?)")) {
        statement.setLong(1, documentId);
        statement.setClob(2, temporaryClob);
        statement.executeUpdate();
    }
} finally {
    temporaryClob.free();
}
~~~

Đây là một cách tạo LOB object rồi bind, nhưng có thể cần thêm storage/temp resource và copy. Nếu driver hỗ trợ bind Reader trực tiếp, direct stream binding thường đơn giản hơn.

Không nhầm temporary LOB với persistent LOB trong bảng. Temporary LOB cần free() khi hoàn tất; persistent LOB locator free() chỉ giải phóng handle JDBC, không xóa dữ liệu đã commit.

## 19. Lỗi thường gặp khi đọc/ghi LOB

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| OutOfMemoryError | Dùng getString/getBytes cho LOB lớn | Dùng Reader/InputStream và buffer |
| ORA-22922 nonexistent LOB value | Locator không còn hợp lệ hoặc row/transaction context thay đổi | Kiểm tra locator, connection và transaction lifetime |
| ORA-22990 LOB locators cannot span transactions | Dùng locator qua transaction boundary không hợp lệ | Không giữ locator qua commit/rollback; lấy locator mới |
| ORA-22920 row containing the LOB value not locked | Ghi locator mà chưa khóa row phù hợp | SELECT FOR UPDATE trong transaction |
| LOB write bị cắt | Length bind sai hoặc source stream kết thúc sớm | Kiểm tra overload, character/byte length và source |
| Nội dung Unicode sai | Charset conversion sai hoặc dùng byte API cho CLOB | Reader/Writer và charset rõ ràng |
| BLOB hỏng | Chuyển binary qua Reader/String | Dùng InputStream/OutputStream |
| Data cũ còn ở cuối LOB | Ghi từ vị trí 1 nhưng không truncate phần đuôi | Truncate LOB trước khi replace toàn bộ |
| NULL locator | Cột LOB đang NULL | Dùng bind stream hoặc khởi tạo EMPTY_CLOB/EMPTY_BLOB |
| Connection pool exhausted | Stream/ResultSet/connection không được đóng | try-with-resources và timeout |
| Lock kéo dài | Stream ghi locator trong transaction lâu | Upload/stage trước, transaction ngắn |
| File output rỗng | Reader/stream không được tiêu thụ hoặc xử lý sai null | Kiểm tra resultSet.next(), null và copy loop |
| Driver exception khi stream | Dùng overload/driver không tương thích | Kiểm tra Oracle JDBC version và API |
| Client disconnect giữ connection | Cleanup không chạy đúng | finally/try-with-resources và cancellation handling |

### 19.1. ORA-22990 và transaction boundary

LOB locator có các quy tắc lifetime. Không lấy locator, commit transaction rồi tiếp tục dùng locator như thể nó vẫn hợp lệ. Sau transaction boundary, hãy query lại và lấy locator mới theo đúng semantics.

### 19.2. Lỗi khi đóng stream

Exception có thể xảy ra khi đọc, ghi hoặc close stream. try-with-resources giữ exception chính và gắn exception trong quá trình close dưới dạng suppressed exception.

Khi log, ghi cả exception chính và suppressed exceptions; không chỉ ghi getMessage().

## 20. Xử lý null, empty và replace toàn bộ

Trước khi mở stream:

- Kiểm tra hàng có tồn tại.
- Phân biệt LOB column NULL với LOB rỗng.
- Xác định operation là append, overwrite hay update một đoạn.
- Nếu replace toàn bộ bằng locator, truncate về 0 trước khi ghi.
- Nếu bind stream vào UPDATE, database nhận giá trị LOB mới theo semantics của DML.
- Nếu source rỗng, quyết định lưu EMPTY_CLOB/EMPTY_BLOB hay NULL theo contract nghiệp vụ.

Không coi file 0 byte, LOB rỗng và SQL NULL là cùng một trạng thái.

### 20.1. Append

Để append vào cuối LOB, cần lấy độ dài hiện tại rồi mở locator stream ở vị trí phù hợp, hoặc dùng API/SQL phù hợp với datatype và driver. Vị trí LOB theo JDBC bắt đầu từ 1.

Append qua locator cần row lock và transaction. Nếu nhiều session append cùng hàng, serialize theo lock và thiết kế retry.

### 20.2. Update một phần

Clob/Blob cung cấp API ghi tại vị trí. Cần xác định rõ semantics khi ghi vượt chiều dài hiện tại, overwrite một đoạn hoặc truncate. Với thao tác phức tạp, DBMS_LOB có thể phù hợp hơn, nhưng cần quản lý vị trí, length và transaction chính xác.

Không viết logic offset dựa trên byte cho CLOB; CLOB position theo character semantics của LOB API.

## 21. LOB và connection pool: mẫu service an toàn

Một service nên phân chia trách nhiệm:

- Repository/DAO thực hiện query và copy LOB.
- Service quản lý transaction boundary.
- Controller quản lý HTTP response lifecycle.
- Connection pool quản lý physical connection.
- Caller quản lý input/output stream bên ngoài theo contract.

Ví dụ flow download:

~~~text
HTTP request
     |
     v
Service validates access
     |
     v
Acquire JDBC connection
     |
     v
Query row and open LOB stream
     |
     v
Copy chunks to HTTP response
     |
     v
Close JDBC stream/resultset/statement
     |
     v
Return connection to pool
     |
     v
Complete HTTP response
~~~

Nếu client ngắt kết nối, copy có thể ném IOException. Khi đó phải đóng JDBC stream và giải phóng connection trong finally. Không để connection ở trạng thái active vô thời hạn.

### 21.1. Upload flow

~~~text
HTTP upload
     |
     v
Validate size/type/checksum
     |
     v
Stage file or bounded stream
     |
     v
Acquire JDBC connection
     |
     v
Bind InputStream to BLOB
     |
     v
Execute DML and commit
     |
     v
Close JDBC resources
     |
     v
Return connection to pool
~~~

Nếu request body có thể bị gửi chậm, tránh mở transaction và giữ row lock từ đầu upload. Có thể stage file trước hoặc dùng upload protocol hỗ trợ resumable storage.

## 22. Bảo mật khi xử lý LOB

LOB có thể chứa dữ liệu cá nhân, hợp đồng, giấy tờ hoặc file độc hại.

- Kiểm tra quyền truy cập object trước khi stream.
- Giới hạn kích thước upload/download.
- Kiểm tra MIME type bằng nội dung khi cần, không chỉ tin file extension.
- Quét malware theo policy.
- Mã hóa transport và storage theo yêu cầu.
- Không log toàn bộ LOB.
- Không đưa LOB content vào exception message.
- Hạn chế thời gian lưu file staging.
- Dùng tên file server-generated, tránh path traversal.
- Giới hạn concurrency để chống memory/connection exhaustion.
- Kiểm tra quyền ở từng request, tránh IDOR khi document ID do client cung cấp.

Đối với BLOB chứa file, không tin Content-Type do client gửi. Có thể dùng signature/magic bytes và scanner chuyên dụng trước khi công bố file cho người dùng khác.

## 23. Kiểm thử và đo hiệu năng

Một test LOB nên bao gồm nhiều kích thước và concurrency:

| Kích thước | Mục tiêu |
|---|---|
| 0 byte | NULL/empty semantics |
| Vài KB | Overhead cơ bản |
| 1 MB | Streaming thông thường |
| 10–100 MB | Heap và throughput |
| Rất lớn theo giới hạn nghiệp vụ | Timeout, backpressure và connection lifetime |

Đo:

- Throughput byte/second hoặc character/second.
- p50/p95/p99 thời gian.
- Heap usage và allocation rate.
- Garbage collection.
- JDBC connection hold time.
- Transaction duration.
- Database CPU, I/O và redo.
- Số stream đồng thời.
- Error và retry.
- Kết quả checksum hoặc content hash sau round-trip.

### 23.1. Kiểm tra tính toàn vẹn

Với BLOB, tính checksum/hash ở nguồn và sau khi đọc lại. Với CLOB, so sánh nội dung theo encoding/canonicalization đã định nghĩa.

Không chỉ kiểm tra row count. Một BLOB có thể tồn tại nhưng bị cắt hoặc sai byte; một CLOB có thể bị lỗi Unicode hoặc thiếu phần cuối.

### 23.2. Kiểm tra concurrency

Thử nhiều upload/download đồng thời. Xác nhận:

- Connection pool không cạn ngoài dự kiến.
- Memory tăng theo buffer/concurrency có giới hạn.
- Row lock không kéo dài bất thường.
- Không có stream dùng chung connection.
- Client disconnect vẫn cleanup.
- Retry không tạo dữ liệu trùng.
- Transaction rollback giữ dữ liệu đúng.

## 24. Checklist trước production

### API và datatype

- [ ] CLOB/NCLOB/BLOB/BFILE được chọn theo nội dung.
- [ ] CLOB dùng Reader/Writer; BLOB dùng InputStream/OutputStream.
- [ ] Không dùng getString/getBytes cho LOB lớn.
- [ ] Phân biệt NULL, EMPTY_CLOB và EMPTY_BLOB.
- [ ] Character length không bị nhầm với byte length.
- [ ] Encoding được xác định rõ.

### Streaming

- [ ] Dùng buffer có giới hạn.
- [ ] Source stream còn mở tới khi execute/copy hoàn tất.
- [ ] Reader/InputStream từ ResultSet được đọc trước khi đóng ResultSet/Connection.
- [ ] Writer/OutputStream locator được đóng trước commit.
- [ ] Không dùng InputStream.available() làm tổng size.
- [ ] LOB prefetch được đo và cấu hình theo workload.

### Transaction và resource lifecycle

- [ ] Connection ownership được xác định.
- [ ] Transaction boundary rõ ràng.
- [ ] SELECT FOR UPDATE được dùng khi locator update cần khóa row.
- [ ] Không commit/rollback khi stream còn mở.
- [ ] Statement, ResultSet và stream được đóng bằng try-with-resources.
- [ ] Clob/Blob locator được free() sau khi dùng.
- [ ] Connection được commit/rollback và reset trước khi trả pool.
- [ ] Không dùng connection/locator/stream trên nhiều thread đồng thời.

### Vận hành và bảo mật

- [ ] Upload/download có giới hạn kích thước.
- [ ] Có timeout và cancellation cleanup.
- [ ] Có checksum/integrity validation khi cần.
- [ ] Có kiểm soát quyền truy cập tài liệu.
- [ ] Có scan/validation file theo policy.
- [ ] Log không chứa nội dung hoặc secret nhạy cảm.
- [ ] Đã test driver version, large LOB và concurrent load.
- [ ] Đã test client disconnect, timeout, rollback và pool exhaustion.

## 25. Ghi nhớ cốt lõi

- CLOB là ký tự, NCLOB là ký tự theo national character set, BLOB là byte nhị phân; BFILE trỏ tới file ngoài database và có semantics khác.
- Dùng Reader/Writer cho CLOB và InputStream/OutputStream cho BLOB.
- Streaming theo buffer tránh materialize toàn bộ LOB thành String hoặc byte array.
- JDBC direct binding qua setCharacterStream/setBinaryStream phù hợp cho nhiều INSERT/UPDATE thông thường.
- LOB locator phù hợp khi cần thao tác trên LOB đã tồn tại; cập nhật locator thường cần SELECT FOR UPDATE và transaction tường minh.
- Khi replace toàn bộ qua locator, truncate trước khi ghi để không giữ phần đuôi dữ liệu cũ.
- NULL khác EMPTY_CLOB/EMPTY_BLOB; locator NULL không thể dùng để mở stream.
- CLOB length là ký tự; BLOB length là byte; không dùng file byte size làm character length.
- Reader/InputStream JDBC phụ thuộc ResultSet/Statement/Connection; phải tiêu thụ trước khi đóng resource nền.
- Writer/OutputStream ghi LOB phải đóng trước commit để hoàn tất thao tác.
- Clob.free()/Blob.free() giải phóng locator handle; không xóa dữ liệu LOB đã commit.
- Không dùng locator qua transaction boundary không hợp lệ; lấy locator mới sau commit/rollback.
- try-with-resources giúp đóng stream, ResultSet và Statement ngay cả khi có exception.
- Connection do transaction manager/pool quản lý không nên bị DAO đóng ngoài contract; hoàn tất transaction và cleanup trước khi trả pool.
- Không giữ row lock trong lúc chờ upload/network chậm; staging hoặc asynchronous processing có thể phù hợp hơn.
- LOB prefetch và fetch size là hai cơ chế khác nhau; đo theo kích thước LOB và concurrency.
- BLOB là byte; nếu nội dung là text, encoding phải được quy định rõ ràng.
- Kiểm thử checksum, Unicode, NULL/empty, large payload, concurrent stream và client disconnect trước production.

### Tài liệu Oracle và JDBC nên đối chiếu

- [Oracle Database JDBC Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/) — JDBC LOB support, streaming, LOB locators, prefetch and driver behavior.
- [Oracle Database JDBC Java API Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/jajdb/) — Oracle JDBC interfaces and extensions.
- [Java SE JDBC API — Clob](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Clob.html) — Character stream, locator, truncate and free.
- [Java SE JDBC API — Blob](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Blob.html) — Binary stream, locator, truncate and free.
- [Java SE JDBC API — PreparedStatement](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html) — setCharacterStream, setBinaryStream, setClob and setBlob overloads.
- [Java SE JDBC API — ResultSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html) — getCharacterStream, getBinaryStream, getClob and getBlob.

JDBC overload availability and Oracle LOB streaming/prefetch behavior depend on the JDK and Oracle JDBC driver version. Verify the deployed driver, test large payloads and transaction boundaries, and measure connection hold time and memory under representative concurrency before production rollout.

