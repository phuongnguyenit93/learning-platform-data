# Xử lý độ dài được khai báo và độ dài chưa biết trước trong JDBC

## 1. Bối cảnh: dữ liệu lớn không phải lúc nào cũng biết kích thước

Trong ứng dụng Java sử dụng **JDBC**, một cột có thể lưu ảnh, tệp PDF, âm thanh, tài liệu dài hoặc nội dung văn bản lớn. Các kiểu SQL thường gặp gồm `BLOB`/`VARBINARY` cho dữ liệu nhị phân và `CLOB`/`VARCHAR`/`TEXT` hoặc kiểu ký tự quốc gia cho văn bản. Tên kiểu và giới hạn thực tế phụ thuộc hệ quản trị cơ sở dữ liệu.

Khi đưa dữ liệu vào `PreparedStatement`, đôi khi ứng dụng đã biết chính xác kích thước: tệp trên đĩa có thể lấy số **byte** bằng `Files.size(path)`. Trong trường hợp khác, ứng dụng chỉ có luồng `InputStream` từ mạng, một bộ sinh dữ liệu hoặc `Reader` giải mã văn bản mà chưa biết tổng độ dài.

JDBC có các overload cho cả hai tình huống:

- **Độ dài đã biết/được khai báo:** cung cấp thêm `length`, ví dụ `setBinaryStream(index, stream, longLength)` hoặc `setCharacterStream(index, reader, longLength)`.
- **Độ dài chưa biết trước:** không cung cấp `length`, ví dụ `setBinaryStream(index, stream)` hoặc `setCharacterStream(index, reader)`.

Khác biệt này ảnh hưởng đến cách driver đọc luồng, khả năng tương thích, giới hạn bộ nhớ, thời điểm phát hiện dữ liệu thiếu hoặc thừa và chính sách xử lý lỗi.

Bài thuộc chương **Dữ liệu lớn** của module **JDBC**, tập trung vào driver, `DataSource`, `PreparedStatement`, `ResultSet`, xử lý dữ liệu lớn, SQL tham số hóa, transaction, quản lý kết nối, lỗi và hiệu năng thông qua API Java chuẩn.

Sau bài học, bạn có thể lựa chọn đúng overload stream, phân biệt **byte** với **char**, nhận diện trường hợp driver cần độ dài, đọc và ghi LOB không giữ toàn bộ dữ liệu trong heap, đồng thời thiết kế fallback an toàn cho đầu vào không rõ kích thước.

## 2. Hai mô hình truyền dữ liệu qua PreparedStatement

Giả sử bảng logic có dạng:

```sql
CREATE TABLE documents (
    document_id BIGINT PRIMARY KEY,
    file_name   VARCHAR(255) NOT NULL,
    payload     BLOB,
    note_text   CLOB
);
```

Đây là DDL minh họa theo tên kiểu SQL phổ biến. PostgreSQL có kiểu `bytea` cho nhị phân và `text` cho văn bản; MySQL, SQL Server, Oracle và các DB khác có các kiểu cùng cách xử lý LOB khác nhau. Phải chọn kiểu SQL, kích thước tối đa và cách bind tương thích với hệ quản trị/driver thực tế.

Câu SQL ghi dữ liệu có thể là:

```sql
INSERT INTO documents (document_id, file_name, payload)
VALUES (?, ?, ?)
```

Vị trí thứ 3 nhận dữ liệu lớn. Thay vì gọi `setBytes(3, byte[])` với toàn bộ file đã tải vào RAM, ứng dụng có thể truyền một `InputStream`.

### 2.1. Bảng đối chiếu API

| Kiểu dữ liệu | Có khai báo độ dài | Không khai báo độ dài | Đơn vị `length` |
|---|---|---|---|
| Nhị phân | `setBinaryStream(int, InputStream, long)` | `setBinaryStream(int, InputStream)` | **Số byte** |
| Ký tự | `setCharacterStream(int, Reader, long)` | `setCharacterStream(int, Reader)` | **Số char** do luồng ký tự cung cấp |
| Ký tự ASCII | `setAsciiStream(int, InputStream, long)` | `setAsciiStream(int, InputStream)` | **Số byte ASCII** |
| Dữ liệu BLOB | `setBlob(int, InputStream, long)` | `setBlob(int, InputStream)` | **Số byte** |
| Dữ liệu CLOB | `setClob(int, Reader, long)` | `setClob(int, Reader)` | **Số char** |
| Ký tự quốc gia | `setNCharacterStream(int, Reader, long)` | `setNCharacterStream(int, Reader)` | **Số char** |
| Dữ liệu NCLOB | `setNClob(int, Reader, long)` | `setNClob(int, Reader)` | **Số char** |

Các phương thức này thuộc `PreparedStatement`; trong Java JDBC hiện đại, nhiều overload không khai báo độ dài là API chuẩn. Tuy nhiên, mức hỗ trợ thực tế của driver, kiểu cột và cấu hình cơ sở dữ liệu **không đồng nhất**. Việc API tồn tại trong JDK không bảo đảm từng driver có thể truyền luồng mà không cần đệm hoặc không cần biết chiều dài.

Một số API còn có overload `int length` cũ hơn. Với dữ liệu lớn, nếu cần truyền độ dài tường minh, nên dùng overload `long length` để không bị giới hạn bởi số nguyên 32 bit.

### 2.2. “Khai báo độ dài” có nghĩa gì?

Khi gọi:

```java
ps.setBinaryStream(3, input, 10_000L);
```

ứng dụng đang đưa ra hợp đồng rằng tham số có **10.000 byte** từ `input`. Con số này phải phản ánh **dữ liệu thật sự được truyền**, chứ không chỉ là con số ước lượng.

Nếu độ dài khai báo nhỏ hơn dữ liệu thực tế, phần vượt quá có thể không được truyền hoặc driver có thể phản ứng khác tùy cách triển khai. Nếu luồng hết trước khi đủ độ dài, việc thực thi có thể thất bại hoặc driver có hành vi riêng. Không dựa vào cách driver xử lý chênh lệch này để cắt file hay tự sửa dữ liệu: hãy bảo đảm chiều dài khớp chính xác và kiểm thử trên driver đích.

Với overload không truyền `length`, driver phải xử lý việc xác định điểm kết thúc luồng. Điều này thuận tiện nhưng **không có nghĩa chắc chắn driver truyền từng chunk trực tiếp tới DB mà không đệm**.

## 3. Độ dài đã biết: lấy số byte thực tế từ tệp bất biến

### 3.1. Ví dụ JDBC đầy đủ với setBinaryStream có length

Ví dụ dùng Java 17+, `DataSource` và tệp nhị phân trên đĩa:

```java
import javax.sql.DataSource;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.Objects;

public final class DocumentWriter {
    private static final String INSERT_SQL = """
            INSERT INTO documents (document_id, file_name, payload)
            VALUES (?, ?, ?)
            """;

    private final DataSource dataSource;

    public DocumentWriter(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public void insertKnownLength(
            long documentId, String fileName, Path source
    ) throws SQLException, IOException {
        Objects.requireNonNull(source, "source");

        // Files.size() trả kích thước tệp theo byte, kiểu long.
        long byteLength = Files.size(source);

        try (InputStream input = Files.newInputStream(source);
             Connection connection = dataSource.getConnection();
             PreparedStatement ps =
                     connection.prepareStatement(INSERT_SQL)) {

            ps.setLong(1, documentId);
            ps.setString(2, fileName);
            ps.setBinaryStream(3, input, byteLength);

            int affected = ps.executeUpdate();
            if (affected != 1) {
                throw new SQLException(
                        "INSERT phải tác động đúng 1 hàng, thực tế: "
                                + affected);
            }
        }
    }
}
```

Mọi tài nguyên do phương thức tạo đều được đóng bằng `try-with-resources`. Luồng `input` vẫn mở trong suốt `executeUpdate()`, bởi driver có thể chỉ bắt đầu đọc nội dung khi lệnh được thực thi. Kích thước được truyền bằng kiểu `long`, nên không bị ép vào giới hạn của `int`.

**Điều kiện cần:** tệp phải giữ nguyên giữa lúc đo kích thước và lúc driver đọc. Nếu tiến trình khác sửa, thay thế hoặc cắt tệp trong khoảng đó, `Files.size(source)` có thể không còn khớp với dữ liệu. Trong hệ thống thực tế, dùng vùng lưu trữ tạm do ứng dụng sở hữu và không thay đổi trong khi gửi, hoặc kiểm tra tính nhất quán theo thiết kế.

### 3.2. Khi Files.size() không phải số byte sẽ được gửi

`Files.size(path)` chỉ là độ dài **tệp gốc**. Nếu ứng dụng tạo một luồng đã nén, mã hóa, giải nén, cắt đoạn hoặc ghép từ nhiều nguồn, số byte **sau biến đổi** có thể khác số byte tệp gốc.

Ví dụ:

```text
Tệp gốc:                  1.000.000 byte
       |
       v
Nén dữ liệu
       |
       v
Luồng đầu ra để gửi:       420.000 byte (chỉ là ví dụ)

Khai báo length = 1.000.000 cho luồng đã nén là sai.
```

Khi kích thước đầu ra chưa biết chính xác, có thể chọn overload **không khai báo độ dài**, hoặc ghi kết quả biến đổi vào tệp tạm để đo chính xác trước khi gọi JDBC.

Giá trị `Content-Length` do client HTTP cung cấp cũng chỉ đáng tin nếu quy trình đã kiểm chứng nó phù hợp với **số byte thực sự được ứng dụng truyền** và không có biến đổi trung gian.

### 3.3. Đừng ép size thành int

```java
long size = Files.size(path);

// Không an toàn nếu tệp lớn hơn Integer.MAX_VALUE.
int truncated = (int) size;

// Đúng khi API và driver hỗ trợ:
ps.setBinaryStream(3, input, size);
```

Ép kiểu từ `long` sang `int` có thể làm tràn giá trị và khiến driver đọc sai. Tuy nhiên, dùng `long` ở Java **không có nghĩa** database, driver, packet size hay cấu hình lưu trữ sẽ chấp nhận mọi kích thước tệp. Giới hạn SQL type và cấu hình server vẫn phải được kiểm tra.

## 4. Độ dài chưa biết: overload không có length

### 4.1. Ví dụ với InputStream do caller cung cấp

Một luồng từ HTTP request, bộ sinh file hoặc hệ thống lưu trữ khác có thể không biết chính xác số byte còn lại. Khi driver hỗ trợ overload tương ứng, có thể viết:

```java
import javax.sql.DataSource;
import java.io.InputStream;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.Objects;

public final class StreamingDocumentWriter {
    private final DataSource dataSource;

    public StreamingDocumentWriter(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public void insertUnknownLength(
            long documentId,
            String fileName,
            InputStream source
    ) throws SQLException {
        Objects.requireNonNull(source, "source");

        String sql = """
                INSERT INTO documents (document_id, file_name, payload)
                VALUES (?, ?, ?)
                """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, documentId);
            ps.setString(2, fileName);

            // Không khai báo length.
            ps.setBinaryStream(3, source);

            if (ps.executeUpdate() != 1) {
                throw new SQLException("Không thể thêm tài liệu");
            }
        }

        // Caller sở hữu và đóng source theo hợp đồng API.
    }
}
```

Điểm khác biệt với `insertKnownLength` chỉ nằm ở overload `setBinaryStream(3, source)`; quy trình bind tham số, chạy `PreparedStatement` và kiểm tra kết quả vẫn tương tự.

Trong ví dụ này, `source` thuộc quyền sở hữu của **caller**. Caller phải giữ nguồn mở cho tới khi `insertUnknownLength` kết thúc và tự đóng nó sau đó, chẳng hạn:

```java
try (InputStream upload = openUploadStream()) {
    writer.insertUnknownLength(documentId, fileName, upload);
}
```

`openUploadStream()` là hàm do ứng dụng cung cấp. Không đóng nguồn ngay sau `setBinaryStream(...)`, bởi driver có thể chưa đọc dữ liệu. Cũng không chia sẻ cùng một `InputStream` cho nhiều lời gọi thực thi: luồng thường chỉ đọc một lần và đã bị tiêu thụ sau lần đầu.

### 4.2. “Không biết độ dài” không đồng nghĩa “không giới hạn kích thước”

Nếu nhận một luồng không được kiểm soát từ bên ngoài, đọc tới EOF có thể kéo dài bất thường và tiêu tốn băng thông, thời gian, đĩa hoặc tài nguyên DB. Cần đặt giới hạn từ **tầng nhập dữ liệu**:

- Giới hạn số byte tối đa cho upload theo nghiệp vụ.
- Thiết lập timeout hoặc deadline hợp lý ở tầng HTTP/stream, JDBC và database.
- Đảm bảo stream có cách kết thúc khi nguồn không còn dữ liệu.
- Kiểm tra MIME type, checksum hoặc định dạng nội dung theo chính sách ứng dụng; `setBinaryStream` chỉ truyền byte, không xác thực định dạng.
- Không giữ connection trong lúc chờ mạng quá lâu nếu có thể đọc, kiểm tra và lưu tạm dữ liệu trước.

Một `InputStream` không cung cấp API chuẩn, tin cậy để hỏi “còn bao nhiêu byte đến EOF”. `available()` chỉ ước lượng số byte có thể đọc mà không bị chặn, **không phải** độ dài tổng của luồng. Vì vậy, không dùng `available()` làm đối số `length`.

### 4.3. Driver cần length hoặc tự đệm dữ liệu thì sao?

Một số JDBC driver có thể không hỗ trợ overload không khai báo độ dài cho một kiểu dữ liệu hoặc có thể tự đệm toàn bộ luồng trước khi gửi. Phản ứng có thể gồm `SQLFeatureNotSupportedException`, `SQLException` khác hoặc hành vi hiệu năng không như mong đợi.

Nếu driver yêu cầu biết kích thước, không nên “ước lượng” một con số để qua lỗi. Thay vào đó, **đọc nguồn và ghi ra tệp tạm có giới hạn**, đo số byte thực tế, mở một `InputStream` mới từ tệp đó rồi dùng overload có `long length`. Cách này đánh đổi dung lượng đĩa và một lượt đọc để có kích thước chính xác mà không giữ toàn bộ file trong heap.

> Không tự động retry bằng một overload khác trên **cùng InputStream** sau khi lời gọi đầu thất bại: driver có thể đã đọc mất một phần hoặc toàn bộ luồng. Muốn retry, cần nguồn có thể mở lại từ đầu và đã xác minh trạng thái ghi/transaction.

## 5. Phương án dự phòng: lưu tạm, đếm byte, mở lại luồng

### 5.1. Mẫu đếm byte an toàn

Đoạn mã sau chỉ sử dụng bộ đệm nhỏ và đặt giới hạn kích thước. Nó viết byte từ một `InputStream` vào tệp tạm:

```java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Objects;

public final class StreamStaging {
    private StreamStaging() {}

    public static long copyWithLimit(
            InputStream source, Path destination, long maxBytes
    ) throws IOException {
        Objects.requireNonNull(source, "source");
        if (maxBytes < 0) {
            throw new IllegalArgumentException("maxBytes không hợp lệ");
        }

        byte[] buffer = new byte[64 * 1024];
        long total = 0;

        try (OutputStream out = Files.newOutputStream(destination)) {
            int n;
            while ((n = source.read(buffer)) != -1) {
                // So sánh trước khi cộng để tránh tràn long.
                if (n > maxBytes - total) {
                    throw new IOException(
                            "Dữ liệu vượt giới hạn " + maxBytes + " byte");
                }
                out.write(buffer, 0, n);
                total += n;
            }
        }

        return total;
    }
}
```

Điều kiện `n > maxBytes - total` được dùng sau khi bảo đảm `total <= maxBytes`, tránh cộng vượt giới hạn khi luồng rất lớn. Hàm **không đóng `source`**, vì nguồn do caller sở hữu; nó đóng `OutputStream` mà nó tự tạo.

Khi dùng trong ứng dụng, quy trình hợp lý là:

```java
Path staged = Files.createTempFile("jdbc-upload-", ".bin");

try {
    long exactBytes = StreamStaging.copyWithLimit(
            uploadStream, staged, maxUploadBytes);

    // Chỉ mở DB connection sau khi đã nhận/kiểm tra luồng.
    try (InputStream reOpened = Files.newInputStream(staged)) {
        // Dùng chính độ dài exactBytes:
        // ps.setBinaryStream(parameterIndex, reOpened, exactBytes);
        // ps.executeUpdate();
    }
} finally {
    Files.deleteIfExists(staged);
}
```

Trong đoạn trích, `uploadStream`, `maxUploadBytes` và thao tác SQL nằm trong code gọi. Code thực tế cần gọi repository hoặc tạo `PreparedStatement` bên trong `try` mở lại tệp; tuyệt đối không đóng `reOpened` trước khi `executeUpdate()` hoàn tất.

Cần dành quota đĩa, bảo vệ quyền truy cập tệp tạm, dọn tệp khi lỗi và xem xét lỗi xóa tệp sao cho không làm mất nguyên nhân gốc. Ví dụ dùng `finally` nhấn mạnh việc dọn dẹp, nhưng một hệ thống sản xuất nên ghi nhận lỗi cleanup riêng và cân nhắc cơ chế khôi phục tệp tạm tồn đọng khi tiến trình chết.

### 5.2. Khi nào staging đáng giá?

| Bối cảnh | Cách xử lý đáng cân nhắc | Đánh đổi |
|---|---|---|
| File tĩnh trên đĩa, không bị sửa | `Files.size` + `setBinaryStream(..., length)` | Không cần sao chép dữ liệu |
| Upload mạng chưa có kích thước, driver hỗ trợ no-length | `setBinaryStream(..., stream)` | Ít thao tác trung gian; connection có thể mở lâu và driver có thể đệm |
| Upload mạng, driver yêu cầu kích thước | Lưu tạm có giới hạn, đếm byte, mở lại | Tốn I/O đĩa nhưng biết đúng length và có thể retry nguồn |
| Dữ liệu đã nén/mã hóa khi truyền | Đếm byte **sau biến đổi** hoặc staging | Không được dùng size của nguồn trước biến đổi |
| Dữ liệu vượt giới hạn DB | Từ chối sớm hoặc thiết kế lưu ngoài DB | Kiểu SQL và giới hạn driver không thể bị bỏ qua |

## 6. Văn bản: chiều dài ký tự không phải số byte UTF-8

### 6.1. setCharacterStream nhận Reader và độ dài ký tự

Với cột văn bản, ứng dụng có thể dùng `Reader`:

```java
try (Reader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8);
     Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(
             "INSERT INTO documents (document_id, note_text) VALUES (?, ?)")) {

    ps.setLong(1, documentId);

    // Không cần biết số char trước khi đọc.
    ps.setCharacterStream(2, reader);

    if (ps.executeUpdate() != 1) {
        throw new SQLException("Không thể thêm văn bản");
    }
}
```

Đoạn này cần import `java.io.Reader`, `java.nio.file.Files`, `java.nio.file.Path`, `java.nio.charset.StandardCharsets` và các kiểu JDBC. `Files.newBufferedReader(path, UTF_8)` chuyển byte UTF-8 thành các đơn vị `char` cho Java; `setCharacterStream` nhận **ký tự**, không nhận byte UTF-8 gốc.

Nếu biết trước số đơn vị ký tự mà `Reader` sẽ cung cấp, có thể viết:

```java
long exactCharacterLength = ...; // đã đo từ đúng Reader/dữ liệu
ps.setCharacterStream(2, reader, exactCharacterLength);
```

Không lấy `Files.size(path)` để làm `exactCharacterLength`: kết quả của `Files.size` là byte của file, không phải số ký tự sau giải mã.

### 6.2. Ví dụ Unicode giúp tránh nhầm

Với chuỗi minh họa **`"A😊"`**:

| Cách đo | Kết quả | Giải thích |
|---|---:|---|
| Số byte khi mã hóa UTF-8 | 5 | `A` dùng 1 byte; emoji dùng 4 byte |
| `String.length()` của Java | 3 | Java `String` dùng các đơn vị UTF-16: `A` 1, emoji 2 |
| Số Unicode code point | 2 | Một chữ `A` và một code point emoji |

Các overload `setCharacterStream(..., Reader, long)` định nghĩa độ dài bằng số **ký tự** truyền từ `Reader`; Java `Reader.read(...)` vận hành với phần tử `char` (đơn vị UTF-16). Đừng lấy số code point, số ký tự người dùng nhìn thấy hay số byte UTF-8 thay cho độ dài luồng mà không xác định chính xác quy ước chuyển đổi.

DB có thể dùng cách tính độ dài cột `VARCHAR` khác nhau (theo byte, ký tự, code point hoặc quy tắc cụ thể của engine/collation). Vì vậy, kiểm tra chiều dài ở Java không thay thế constraint và kiểm thử của DB.

### 6.3. Chọn đúng API cho kiểu văn bản

- `setCharacterStream` dùng luồng ký tự `Reader`; phù hợp cho văn bản lớn khi kiểu SQL/driver hỗ trợ.
- `setNCharacterStream` phục vụ các kiểu ký tự quốc gia như `NCHAR`, `NVARCHAR`, `NCLOB` nếu DB hỗ trợ. Không phải cứ văn bản UTF-8 thì bắt buộc dùng `setNCharacterStream`.
- `setClob(index, Reader[, length])` hoặc `setNClob(...)` phù hợp khi driver/DB mong đợi đúng kiểu LOB.
- `setAsciiStream` nhận byte **ASCII**; đừng gửi văn bản Unicode bằng API ASCII rồi trông chờ bảo toàn ký tự ngoài ASCII.
- `setString` với chuỗi đã có trong RAM đơn giản cho dữ liệu nhỏ, nhưng tạo/giữ một `String` khổng lồ để chỉ có thể gọi `setString` sẽ làm mất lợi thế xử lý theo luồng.

Một cột `TEXT` của DB không tự đồng nghĩa hoàn toàn với kiểu `CLOB` của JDBC. Kiểm tra tài liệu JDBC driver trước khi chọn `setClob` thay cho `setCharacterStream` hoặc `setString`.

## 7. Đọc dữ liệu lớn từ ResultSet: cũng nên dùng luồng

Bài toán độ dài không chỉ xuất hiện khi ghi. Khi đọc, các getter như `getBytes()` hoặc `getString()` có thể materialize toàn bộ dữ liệu trong Java heap. Các getter streaming giúp ứng dụng xử lý dần:

| Dạng dữ liệu | API đọc | Mục đích |
|---|---|---|
| Binary | `ResultSet.getBinaryStream(column)` | Nhận `InputStream` của dữ liệu nhị phân |
| Text | `ResultSet.getCharacterStream(column)` | Nhận `Reader` cho văn bản |
| BLOB object | `ResultSet.getBlob(column)` | Nhận `Blob`; có `length()` và `getBinaryStream()` |
| CLOB object | `ResultSet.getClob(column)` | Nhận `Clob`; có `length()` và `getCharacterStream()` |

**Lưu ý:** API trả một luồng không bảo đảm driver sẽ không đệm dữ liệu phía sau. Một số hệ quản trị lưu LOB ở vị trí riêng hoặc driver đọc theo từng khối; một số driver có thể tải nhiều dữ liệu vào bộ nhớ. Cần đo với driver thực tế.

### 7.1. Ví dụ tải BLOB sang OutputStream

Đây là ví dụ tự chứa về vòng đời tài nguyên. Hàm nhận một `OutputStream` do caller quản lý và trả `false` khi không tìm thấy tài liệu:

```java
import javax.sql.DataSource;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Objects;

public final class DocumentReader {
    private final DataSource dataSource;

    public DocumentReader(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public boolean copyPayload(
            long documentId, OutputStream destination
    ) throws SQLException, IOException {
        Objects.requireNonNull(destination, "destination");

        String sql = """
                SELECT payload
                FROM documents
                WHERE document_id = ?
                """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, documentId);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return false; // Không có hàng tài liệu.
                }

                InputStream value = rs.getBinaryStream("payload");
                if (value == null) {
                    throw new SQLException("payload là SQL NULL");
                }

                try (InputStream input = value) {
                    byte[] buffer = new byte[64 * 1024];
                    int n;
                    while ((n = input.read(buffer)) != -1) {
                        destination.write(buffer, 0, n);
                    }
                }

                return true;
            }
        }

        // Caller sở hữu destination và quyết định flush/close.
    }
}
```

Hàm **đọc và tiêu thụ stream trong khi `ResultSet` còn mở và vẫn đang ở hàng hiện tại**. Luồng `value` có thể trở nên không hợp lệ khi chuyển sang hàng tiếp theo, đóng `ResultSet` hoặc đóng connection; không giữ nó làm field hoặc trả ra ngoài rồi đóng connection.

Nếu ghi ra một file đích có thể bị thay thế, caller nên cân nhắc ghi vào file tạm và chỉ đổi tên sau khi sao chép xong để không để lại nội dung đích dở dang khi lỗi mạng hoặc lỗi JDBC. Nếu ghi ra HTTP response, cần xác định cách báo lỗi khi response đã gửi một phần; rollback DB không thể “thu hồi” những byte đã gửi cho client.

### 7.2. Có thể lấy độ dài khi đọc LOB không?

`Blob.length()` trả độ dài của giá trị BLOB tính bằng **byte** (kiểu `long`). `Clob.length()` trả độ dài theo **ký tự** của giá trị CLOB. Ví dụ:

```java
Blob blob = rs.getBlob("payload");

if (blob != null) {
    try {
        long byteLength = blob.length();
        try (InputStream input = blob.getBinaryStream()) {
            // Xử lý input theo từng khối.
        }
    } finally {
        blob.free();
    }
}
```

Đoạn này giả định `rs` còn mở, import `java.sql.Blob` và `java.io.InputStream`, và code gọi xử lý `SQLException`. `free()` giải phóng tài nguyên LOB theo hợp đồng API, nhưng cách driver quản lý và yêu cầu thời điểm giải phóng có thể khác nhau. Đọc `length()` có thể gây truy vấn/chi phí riêng hoặc không được hỗ trợ trong một số tình huống; không nên giả định nó luôn là thao tác O(1) và không tải dữ liệu.

`getBinaryStream()` hoặc `getCharacterStream()` có thể trả `null` khi cột SQL là `NULL`. Giá trị LOB rỗng có độ dài 0, **khác** với SQL NULL. Mapper cần phân biệt hai trạng thái này.

## 8. Connection, transaction và thời gian sống của stream

### 8.1. Ai sở hữu gì?

| Tài nguyên | Ai nên đóng? | Thời điểm |
|---|---|---|
| `InputStream`/`Reader` do repository mở từ tệp | Repository tạo nguồn | Sau khi `executeUpdate()` hoặc `executeBatch()` đã tiêu thụ xong và không cần lại |
| `InputStream`/`Reader` được caller truyền vào | Theo hợp đồng quyền sở hữu API, thường là caller | Sau khi lời gọi JDBC kết thúc |
| `PreparedStatement`/`CallableStatement` | Thành phần tạo statement | Sau khi thực thi và đọc xong kết quả cần thiết |
| `ResultSet` | Thành phần tạo/truy cập result set | Sau khi tiêu thụ stream trong hàng hiện tại |
| `Connection` | Tầng mở kết nối hoặc transaction manager | Sau khi commit/rollback và xử lý xong luồng phụ thuộc connection |

Một sai lầm phổ biến:

```java
InputStream stream;

try (ResultSet rs = ps.executeQuery()) {
    rs.next();
    stream = rs.getBinaryStream("payload");
}

// Sai: ResultSet đã đóng; stream có thể không đọc được nữa.
consume(stream);
```

Hãy đọc nội dung **bên trong** phạm vi `try` còn giữ `ResultSet` mở. Với giao dịch tường minh, không đóng connection trước khi driver hoàn tất truyền hoặc nhận dữ liệu.

### 8.2. Dữ liệu lỗi giữa chừng và transaction

Nếu driver gặp lỗi I/O khi đọc `InputStream`, `executeUpdate()` có thể ném `SQLException`, đôi khi có `IOException` làm `cause`. Không nên coi cập nhật đã được commit chỉ vì một phần luồng đã được đọc.

Với nghiệp vụ yêu cầu **ghi metadata và nội dung nhị phân nguyên tử**, nên dùng cùng một connection và transaction:

```text
Lấy Connection từ DataSource
       |
setAutoCommit(false)
       |
INSERT metadata + BLOB trên cùng Connection
       |
  +----+--------------------+
  |                         |
Thành công                 Có lỗi
  |                         |
commit()                 rollback()
  |                         |
close()                  close()
```

Tầng sở hữu transaction chịu trách nhiệm `commit`/`rollback`; repository nhận connection chỉ mượn kết nối, không tự đóng hoặc tự commit. Nếu việc ghi phụ thuộc vào upload mạng rất chậm, cân nhắc **staging trước khi mở transaction** để tránh giữ khóa và chiếm connection lâu.

Nếu lỗi kết nối xuất hiện **ngay khi commit**, trạng thái có thể không xác định; cần cơ chế request ID, idempotency và đối soát trước khi tự động retry ghi file. Việc đọc một stream thường chỉ tiến về phía trước: lần retry phải mở lại nguồn từ đầu và tránh ghi trùng.

### 8.3. Transaction và cơ chế cursor/fetch size

`PreparedStatement.setFetchSize(int)` chỉ đưa ra **gợi ý số hàng** nên lấy mỗi lần từ database, không phải kích thước chunk của một cột BLOB/CLOB. Một số driver cần `autoCommit=false` hoặc thiết lập cursor riêng để thực sự lấy nhiều hàng theo từng đợt. Điều kiện này **phụ thuộc driver/DB**; không tự áp dụng cấu hình của PostgreSQL cho mọi hệ quản trị.

Đối với nhiều hàng mà mỗi hàng có LOB lớn, hãy tiêu thụ một hàng và đóng stream trước khi gọi `rs.next()`. Nếu cần đọc đồng thời nhiều LOB, cần hiểu cách driver giữ tài nguyên khi có các luồng đang mở.

## 9. Lỗi thường gặp: chênh lệch length, bộ nhớ và giới hạn kiểu

| Hiện tượng | Nguyên nhân phổ biến | Cách xử lý |
|---|---|---|
| Driver báo dữ liệu ngắn hơn chiều dài khai báo | `length` lớn hơn số byte/char mà stream phát ra | Đo đúng độ dài hoặc dùng overload no-length được hỗ trợ |
| Dữ liệu bị cắt hoặc driver báo lỗi ở cuối stream | Khai báo `length` nhỏ hơn nội dung thực | Không dùng ước lượng; kiểm tra output/size |
| File UTF-8 dài N byte nhưng Reader cho ít char hơn | Nhầm `Files.size` với số char | Dùng `setCharacterStream` không length hoặc đếm đúng đơn vị char |
| Dùng `available()` làm size | `available()` không phải tổng độ dài | Dùng `Files.size` cho file ổn định hoặc staging |
| `SQLFeatureNotSupportedException` | Driver không hỗ trợ overload hoặc kiểu dữ liệu | Đối chiếu driver/SQL type; dùng overload hoặc chiến lược tương thích |
| `OutOfMemoryError` khi đọc/ghi LOB | Dùng `getBytes`/`getString` hoặc driver đệm toàn bộ | Chia thành stream/chunk, chọn driver phù hợp và đo heap |
| Tệp khác nội dung sau retry | Stream cũ đã tiêu thụ hoặc dữ liệu nguồn thay đổi | Mở lại nguồn từ đầu, checksum, idempotency và trạng thái transaction |
| Ghi thành công nhưng người dùng thấy lỗi | Lỗi `commit`/đóng kết nối xảy ra sau ghi | Đối soát request ID thay vì mặc định ghi lại |
| Nội dung rỗng bị coi là SQL NULL | Dùng `null` thay cho stream 0 byte | Phân biệt 0 byte, 0 char và SQL NULL |
| Gửi văn bản Unicode qua `setAsciiStream` | API chỉ dành cho byte ASCII | Dùng `Reader`/`setCharacterStream` hoặc API quốc gia phù hợp |
| Một stream dùng nhiều lệnh batch | Luồng bị tiêu thụ ở lần trước hoặc driver đệm/giới hạn | Tạo nguồn riêng cho từng item, kiểm thử batch streaming, dùng chunk |
| Đọc stream sau khi đóng ResultSet | Luồng phụ thuộc tài nguyên JDBC đã đóng | Đọc hết trong scope giữ ResultSet mở |
| Bị timeout khi truyền file lớn | Mạng/driver/DB/pool timeout hoặc upload quá chậm | Phân tích từng timeout, staging, giới hạn size, tối ưu I/O |

### 9.1. Cảnh giác khi bắt lỗi

Với thao tác JDBC, lỗi có thể đến từ nhiều lớp:

- `IOException` khi tự đọc tệp trong Java, hoặc lỗi I/O được driver bọc thành `SQLException` trong `executeUpdate()`.
- `SQLException` do kiểu SQL, dữ liệu, transaction, driver hoặc kết nối.
- `SQLDataException` hoặc SQLState class `22` cho dữ liệu không hợp lệ; `SQLFeatureNotSupportedException` nếu API không được hỗ trợ.
- Lỗi ứng dụng như `IllegalArgumentException` do length âm, số byte vượt giới hạn hoặc input sai hợp đồng.

Khi log, nên giữ tên thao tác, mã yêu cầu, kích thước dự kiến/thực tế (khi biết), `SQLState`, mã lỗi DB và nguyên nhân được phép ghi. Không log toàn bộ nội dung file, dữ liệu cá nhân, mật khẩu hay URL truy cập có token. Nếu cleanup cũng lỗi, giữ lỗi ban đầu và bổ sung suppressed exception theo cách quản lý tài nguyên.

### 9.2. Length và bảo mật

Không tin hoàn toàn con số length do người dùng hoặc hệ thống bên ngoài gửi lên:

1. Áp dụng giới hạn kích thước trên luồng **thực sự nhận được**.
2. Từ chối nội dung lớn hơn cấu hình nghiệp vụ trước khi đẩy vào DB.
3. Dùng checksum khi cần bảo đảm nội dung cuối trùng dữ liệu được dự kiến.
4. Kiểm tra phân quyền đọc/ghi, loại tệp và định dạng ở tầng ứng dụng.
5. Khi staging file tạm, thiết lập quyền truy cập, hạn ngạch và chính sách dọn dẹp phù hợp.

Cung cấp `length` cho JDBC là **thông tin điều khiển I/O**, không phải một cơ chế xác thực toàn vẹn hay xác thực nguồn gửi.

## 10. Batch, nhiều tệp và độ dài thay đổi

Với batch gồm nhiều tài liệu, mỗi phần tử có thể có kích thước khác nhau. Không được dùng cùng một `InputStream` và một giá trị length cho tất cả bộ tham số trừ khi chính dữ liệu đó đã được thiết kế để tái sử dụng bằng cách mở **nguồn mới cho mỗi lần thực thi**.

Về lý thuyết:

```java
for (UploadItem item : items) {
    ps.setLong(1, item.id());
    ps.setBinaryStream(2, item.source(), item.exactBytes());
    ps.addBatch();
}
ps.executeBatch();
```

Đây chỉ là mô tả API; `UploadItem` do ứng dụng định nghĩa. Đừng suy ra từ đoạn này rằng có thể đóng từng `item.source()` ngay sau `addBatch()`. Driver có thể chưa tiêu thụ nội dung cho đến `executeBatch()`. Nếu giữ hàng nghìn luồng/tệp mở cùng lúc, ứng dụng có thể cạn file descriptors hoặc bộ nhớ.

Với dữ liệu LOB lớn, thường nên:

- Thử nghiệm khả năng batch streaming của driver trước khi dùng.
- Dùng số phần tử/chunk nhỏ có giới hạn, hoặc thực thi từng tệp trong cùng transaction khi yêu cầu nguyên tử.
- Đóng từng nguồn sau khi driver đã tiêu thụ xong.
- Kiểm tra `BatchUpdateException.getUpdateCounts()` nếu có lỗi; số hàng đã thực thi **không xác nhận đã commit**.
- Khi retry, mở lại nguồn và đối soát trạng thái ghi theo mã yêu cầu ổn định.

Không phải driver nào cũng tối ưu batch LOB giống batch các giá trị nhỏ. Phép đo cần phản ánh tổng thời gian, I/O, memory và khả năng phục hồi sau lỗi.

## 11. Đo và kiểm chứng cách xử lý dữ liệu lớn

### 11.1. Thiết kế phép đo

Nên đo với đúng hệ quản trị, driver và loại cột dự định sử dụng. So sánh các tình huống:

| Biến số | Giá trị thử minh họa | Điều đo |
|---|---|---|
| Dung lượng nhị phân | 0 B, 1 B, 8 KB, 1 MB, hàng trăm MB | Đúng số byte, latency, heap |
| Kích thước đã biết/chưa biết | `setBinaryStream(..., length)` so với `setBinaryStream(..., stream)` | Hành vi driver, throughput, buffering |
| Nguồn dữ liệu | File, InputStream mạng, stream biến đổi | Thời gian đọc, kết nối giữ lâu, khả năng timeout |
| Văn bản Unicode | ASCII, tiếng Việt, emoji | Đúng ký tự, count char/byte, giới hạn cột |
| Đọc dữ liệu | `getBinaryStream` so với `getBytes` khi size phù hợp | Bộ nhớ, thời gian phản hồi, khả năng streaming |
| Transaction | Autocommit và transaction tường minh | Rollback khi lỗi, thời gian giữ transaction |
| Số hàng | Một tệp lớn vs nhiều tệp vừa | Tác động của row fetch và tài nguyên mở |

**Không kết luận** cách có length luôn nhanh hơn hoặc cách no-length luôn ít bộ nhớ hơn. Driver có thể đệm, gửi theo cơ chế giao thức riêng hoặc cần phân tích metadata; kết quả phải đo trong môi trường triển khai.

Nếu muốn biết driver có thực sự đọc theo từng đợt, có thể dùng `InputStream`/`Reader` đo số byte/char đọc được theo thời gian, quan sát heap và lưu lượng mạng, cùng tài liệu driver. Tuy vậy, chỉ số đọc phía Java không đủ chứng minh DB đã nhận/commit dữ liệu tại cùng thời điểm.

### 11.2. Kiểm thử tính đúng đắn

Tối thiểu cần các trường hợp:

1. **Đúng length:** Ghi file không rỗng bằng overload có `long length`, đọc lại và so sánh checksum hoặc từng byte.
2. **Không biết length:** Ghi cùng nội dung từ một luồng không hỗ trợ `mark/reset` và không biết kích thước, đọc lại so sánh.
3. **Length khai báo thiếu:** Giả lập stream kết thúc trước con số đã khai báo; xác nhận driver phản ứng ra sao, không dựa vào một mã lỗi cố định.
4. **Length khai báo thừa:** Gửi luồng dài hơn length, kiểm tra dữ liệu thực tế và chính sách ứng dụng; không coi hành vi cắt im lặng là đúng.
5. **Không có dữ liệu:** Luồng 0 byte, dữ liệu 0 char và SQL NULL phải được phân biệt.
6. **Unicode:** Thử `"A😊"` và chuỗi tiếng Việt có dấu với `Reader`; so sánh ký tự sau khi đọc lại.
7. **Giới hạn tài nguyên:** Nguồn vượt max size, nguồn bị lỗi giữa chừng, DB mất kết nối, đích ghi file hết dung lượng.
8. **Rollback:** Ghi metadata rồi gửi nội dung lỗi trong cùng transaction, sau đó dùng connection mới xác nhận không còn bản ghi dở dang.
9. **Đọc dữ liệu:** Không sử dụng InputStream sau khi đã đóng `ResultSet`; kiểm tra ứng xử khi hủy đọc giữa chừng.
10. **Driver portability:** Thử no-length overload, `setBlob`/`setClob`, và giới hạn kiểu SQL trên DB/driver mục tiêu.

Các kiểm thử trên nên dùng tài liệu thử nghiệm và môi trường riêng. Đừng đưa tệp bí mật thật vào log, fixtures công khai hoặc exception message.

## 12. Chọn chiến lược theo nguồn dữ liệu

| Nhu cầu | Giải pháp ưu tiên cân nhắc | Điều kiện |
|---|---|---|
| Có tệp nhị phân ổn định, biết size | `setBinaryStream(index, input, Files.size(path))` | File không đổi trong khi đọc; DB/driver hỗ trợ |
| Có stream nhị phân chưa rõ kích thước | `setBinaryStream(index, input)` | Driver hỗ trợ; có giới hạn đầu vào; caller quản lý nguồn |
| Stream chưa rõ kích thước nhưng driver yêu cầu length | Staging tệp tạm + đếm byte + overload length | Có quota đĩa và chính sách cleanup |
| Văn bản có Reader nhưng chưa biết char count | `setCharacterStream(index, reader)` | Giải mã ký tự đúng; driver hỗ trợ |
| Văn bản có count chính xác | `setCharacterStream(index, reader, charCount)` | Count đo theo luồng ký tự, không lấy từ file byte size |
| SQL BLOB/CLOB có API riêng | `setBlob`, `setClob`, `setNClob` | Khớp kiểu SQL và khả năng driver |
| Tải tài liệu lớn ra ngoài | `getBinaryStream`/`getCharacterStream` | Tiêu thụ khi ResultSet/Connection còn mở |
| Tác vụ có nhiều file | Chunk hoặc từng file trong cùng transaction phù hợp | Kiểm soát số luồng, lỗi batch và ranh giới commit |

### Bài tập thực hành

Xây dựng API `DocumentStore` với hai phương thức:

```java
void insertBinary(
        long id, String name, InputStream source, long byteCount);

void insertBinaryUnknownLength(
        long id, String name, InputStream source);
```

Thực hiện các bước:

1. Phương thức đầu dùng `setBinaryStream(index, stream, byteCount)`; phương thức sau dùng overload không `length`.
2. Cho cả hai ghi cùng một tệp thử nghiệm, đọc lại bằng `ResultSet.getBinaryStream` rồi so sánh SHA-256.
3. Tạo `InputStream` không hỗ trợ `mark/reset`, thử dùng `available()` làm size để quan sát vì sao nó không đáp ứng hợp đồng độ dài.
4. Cho stream ngừng giữa chừng hoặc cố tình khai báo length sai; ghi nhận exception và trạng thái transaction.
5. Nếu driver không hỗ trợ no-length, bổ sung staging có giới hạn và mở lại file, rồi dùng overload có `length`.
6. Thêm hỗ trợ văn bản UTF-8 qua `Reader`, kiểm tra chuỗi tiếng Việt và emoji, đối chiếu số byte, char và code point.
7. Đo peak heap, thời gian truyền và số lượng connection được sử dụng ở ba kích thước file khác nhau; ghi lại kết quả thực tế thay vì kết luận từ tên overload.

## 13. Ghi nhớ

- **`setBinaryStream(..., length)` khai báo số byte; `setCharacterStream(..., length)` khai báo độ dài ký tự**, không thể dùng lẫn nhau.
- **`Files.size(path)` cho byte, không cho số ký tự của Reader; `InputStream.available()` không phải tổng độ dài nguồn.**
- Với độ dài chưa biết, JDBC có overload không `length`, nhưng **khả năng hỗ trợ và hành vi đệm/streaming phụ thuộc driver**.
- Nguồn được truyền cho `PreparedStatement` phải còn mở cho đến khi lệnh đã tiêu thụ xong; không dùng lại stream đã đọc khi retry.
- Đọc LOB qua `ResultSet.getBinaryStream`/`getCharacterStream` khi hàng và tài nguyên JDBC còn sống; phân biệt giá trị rỗng với SQL NULL.
- Hãy giới hạn kích thước, kiểm thử nội dung sau khi đọc lại, đo hiệu năng trên DB thật và quản lý transaction/rollback khi I/O thất bại.
