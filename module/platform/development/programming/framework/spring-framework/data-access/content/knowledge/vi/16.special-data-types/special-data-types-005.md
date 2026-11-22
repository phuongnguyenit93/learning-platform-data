# LOB dạng BLOB hoặc CLOB: đọc toàn bộ và đọc luồng trong JDBC/Spring

Trong ứng dụng Spring Framework Data Access, một cột SQL có thể chứa dữ liệu rất lớn: ảnh, tệp PDF, dữ liệu nhị phân, văn bản dài, tài liệu XML hoặc nội dung biên tập. JDBC gọi nhóm giá trị này là **Large Object (LOB)**. Hai loại cốt lõi là **BLOB** (*Binary Large Object*) và **CLOB** (*Character Large Object*).

Điểm quan trọng của bài không chỉ là chọn kiểu cột, mà còn là **chọn cách lấy dữ liệu từ database về Java**: đọc toàn bộ vào `byte[]`/`String`, hay tiêu thụ dần bằng `InputStream`/`Reader`. Hai cách có thể cho cùng dữ liệu nhưng có đặc điểm bộ nhớ, tuổi thọ connection, độ trễ và khả năng xử lý lỗi rất khác nhau.

## 1. BLOB, CLOB và dữ liệu thường khác nhau thế nào?

| Kiểu giá trị | Lưu gì? | Đại diện Java/JDBC | Ví dụ |
| --- | --- | --- | --- |
| `BLOB` | Chuỗi **byte**; database không diễn giải nội dung thành chữ theo kiểu CLOB | `byte[]`, `java.sql.Blob`, `InputStream` | Ảnh PNG, file PDF, dữ liệu ZIP, file nhị phân |
| `CLOB` | Chuỗi **ký tự** lớn; chịu ảnh hưởng của charset/collation của database | `String`, `java.sql.Clob`, `Reader` | Nội dung bài viết, văn bản dài, XML, tài liệu |
| `NCLOB` | Dạng character LOB dùng national character set theo cách RDBMS hỗ trợ | `java.sql.NClob`, `Reader` | Văn bản quốc tế trong hệ hỗ trợ kiểu NCLOB |
| `VARBINARY`/`VARCHAR` | Byte/ký tự có kích thước thường nhỏ hơn hoặc giới hạn khác LOB | `byte[]`/`String` | Hash, mã trạng thái, đoạn mô tả ngắn |

**BLOB là byte, CLOB là ký tự.** Đừng giải mã PDF/PNG bằng `getString()`, và đừng xử lý văn bản Unicode lớn như byte tùy tiện mà không có quy tắc charset. Chuỗi tiếng Việt hoặc emoji là dữ liệu ký tự; một tệp UTF-8 có thể là byte nếu ứng dụng chủ động lưu nguyên nội dung tệp vào BLOB.

Tên SQL và cách lưu trữ khác nhau theo hệ quản trị. PostgreSQL thường dùng `bytea` và `text`; Oracle có `BLOB`/`CLOB`/`NCLOB`; MySQL có họ `BLOB`/`TEXT`; H2 hỗ trợ `BLOB`/`CLOB`. **Không thể suy luận rằng mọi cột chứa byte đều trả về `java.sql.Blob` qua mọi driver.** Chọn JDBC getter dựa trên SQL type, driver và hợp đồng ứng dụng.

Ví dụ lược đồ dùng trong bài (H2, cú pháp tương tự nhiều RDBMS):

```sql
CREATE TABLE documents (
    id BIGINT PRIMARY KEY,
    picture BLOB,
    body CLOB
);
```

Một hàng có thể chứa ảnh dài 20 MB và văn bản dài 200.000 ký tự. Nếu chỉ cần hiển thị danh sách tên tài liệu, ứng dụng nên truy vấn metadata hoặc cột nhỏ thay vì luôn `SELECT *` và lôi cả LOB về.

## 2. Hai chiến lược đọc: materialize và stream

### 2.1. Đọc toàn bộ (materialization)

Đọc toàn bộ nghĩa là ứng dụng yêu cầu JDBC tạo ra một đối tượng chứa **toàn bộ giá trị** ở phía Java trước khi tiếp tục xử lý.

```java
byte[] image = rs.getBytes("picture");  // BLOB dạng byte[]
String text = rs.getString("body");     // CLOB dạng String
```

Đây là **đoạn mã minh họa** bên trong vòng xử lý `ResultSet rs`, không phải chương trình độc lập. Nó phù hợp khi kích thước được giới hạn chặt, cần truy cập ngẫu nhiên hoặc nhiều thao tác trên toàn bộ nội dung. `getBytes()` và `getString()` có thể trả `null` nếu giá trị SQL là `NULL`.

Đọc toàn bộ có những hệ quả:

- Một BLOB kích thước `N` byte cần ít nhất một `byte[]` tỉ lệ với `N`, chưa kể bộ đệm của driver và các bản sao khi xử lý hoặc gửi phản hồi.
- Một CLOB tạo `String` tỉ lệ với số ký tự và có thể cần bộ nhớ tạm cho việc chuyển mã; không giả định một ký tự luôn chiếm một byte.
- Nhiều hàng LOB được nạp cùng lúc vào `List` có thể nhân nhu cầu heap lên đáng kể.
- Khi đã có `byte[]` hoặc `String`, ứng dụng có thể dùng dữ liệu sau khi đóng `ResultSet`/connection vì đây là dữ liệu Java đã được tách khỏi tài nguyên JDBC.

### 2.2. Đọc luồng (streaming)

Đọc luồng nghĩa là ứng dụng sử dụng dữ liệu **theo từng phần** trong khi vẫn giữ tài nguyên JDBC cần thiết ở trạng thái hợp lệ.

```java
InputStream binary = rs.getBinaryStream("picture");
Reader characters = rs.getCharacterStream("body");
```

Hai dòng trên chỉ minh họa các API. Với stream lấy từ `ResultSet`, hãy **tiêu thụ xong một stream trước khi gọi getter của cột khác**; theo hợp đồng JDBC, lời gọi getter kế tiếp có thể đóng stream hiện tại. Với BLOB dùng `InputStream` đọc một mảng `byte[] buffer`; với CLOB dùng `Reader` đọc một mảng `char[] buffer`.

Đọc luồng có thể giữ **bộ nhớ xử lý tại ứng dụng** gần với kích thước buffer (ví dụ 8 KiB) thay vì kích thước toàn bộ LOB, nếu ứng dụng chuyển thẳng từng phần ra file, mạng hoặc một bộ xử lý tăng dần. Tuy nhiên:

- **API stream không bảo đảm driver/database thực sự truyền từng phần qua mạng**. Driver có thể nạp trước LOB hoặc đệm một phần/toàn phần. Phải kiểm tra phiên bản driver, cấu hình và thử nghiệm bộ nhớ thực tế.
- Tổng lượng dữ liệu phải truyền từ database đến đích vẫn phụ thuộc kích thước LOB; streaming giảm nhu cầu giữ toàn bộ dữ liệu cùng lúc, không làm dữ liệu biến mất.
- Connection/`ResultSet`/LOB locator có thể cần sống trong suốt quá trình đọc; một người dùng tải xuống chậm có thể giữ connection database rất lâu.
- `InputStream.readAllBytes()` hoặc `InputStream.transferTo(new ByteArrayOutputStream())` **vẫn gom toàn bộ dữ liệu vào heap**, dù đầu vào ban đầu là stream.

### 2.3. Bảng lựa chọn nhanh

| Tiêu chí | Đọc toàn bộ | Đọc luồng |
| --- | --- | --- |
| API điển hình | `getBytes`, `getString`; `Blob.getBytes`, `Clob.getSubString` | `getBinaryStream`, `getCharacterStream`; `Blob/Clob` stream |
| Đối tượng đầu ra | `byte[]`, `String` | `InputStream`, `Reader` được tiêu thụ trong phạm vi còn mở |
| Bộ nhớ ứng dụng | Tỉ lệ với kích thước dữ liệu, có thể có bản sao | Có thể gần kích thước buffer nếu không tích lũy và driver hỗ trợ tốt |
| Truy cập ngẫu nhiên | Thuận tiện | Thường tiêu thụ tuần tự; muốn đọc lại có thể cần truy vấn lại |
| Thời gian giữ connection | Có thể kết thúc sau khi materialize | Thường kéo dài cho tới khi đọc xong |
| Trường hợp phù hợp | Thumbnail nhỏ, đoạn text đã giới hạn, cần xử lý toàn bộ | Tệp lớn, xuất dữ liệu lớn, xử lý tuần tự, sao chép trực tiếp |

Không có ngưỡng MB đúng cho mọi hệ thống. Ngưỡng cần dựa vào tải đồng thời, heap, driver, kích thước LOB thực tế, chi phí giữ connection và yêu cầu nghiệp vụ.

## 3. API JDBC tương ứng: `Blob`, `Clob` và `ResultSet`

Có hai lối tiếp cận:

**Đọc trực tiếp từ `ResultSet`:**

```java
byte[] allBytes = rs.getBytes(1);
String allText = rs.getString(2);

InputStream byteStream = rs.getBinaryStream(1);
Reader charStream = rs.getCharacterStream(2);
```

Đây là các lời gọi **thay thế hoặc theo trình tự hợp lệ**, không phải chỉ dẫn mở cả bốn nguồn dữ liệu đồng thời trên một hàng. Với cách đọc stream, đóng và tiêu thụ nguồn trước khi chuyển sang getter khác.

**Lấy đối tượng LOB trước:**

```java
Blob blob = rs.getBlob("picture");
Clob clob = rs.getClob("body");
```

`java.sql.Blob` và `java.sql.Clob` mô tả LOB theo chuẩn JDBC, thường thông qua một *locator* mà driver dùng để truy cập dữ liệu. Với `Blob`:

- `length()` trả số **byte** dưới dạng `long`.
- `getBytes(long pos, int length)` lấy một đoạn thành `byte[]`.
- `getBinaryStream()` lấy `InputStream`; có overload lấy đoạn với `pos`, `length`.
- `free()` giải phóng tài nguyên liên quan đến `Blob` khi không còn dùng.

Với `Clob`:

- `length()` trả độ dài **ký tự** mà JDBC/driver mô tả, dưới dạng `long`.
- `getSubString(long pos, int length)` lấy một đoạn thành `String`.
- `getCharacterStream()` lấy `Reader`; có overload lấy đoạn.
- `free()` giải phóng tài nguyên liên quan đến `Clob`.

**Cả `getBytes(pos, length)` và `getSubString(pos, length)` dùng `pos` bắt đầu từ 1, không phải 0.** Tham số `length` là `int`, nên không thể ép một `long length()` tùy ý thành `int` để lấy toàn bộ LOB. Với LOB lớn, đọc từng phần hoặc streaming.

Ví dụ mảnh mã an toàn hơn khi một đối tượng `Blob blob` đã được đọc và được xác nhận không null:

```java
long size = blob.length();
long maxAllowed = 8L * 1024 * 1024; // 8 MiB: giới hạn minh họa
if (size > maxAllowed) {
    throw new IllegalArgumentException("BLOB too large for full read");
}
byte[] all = blob.getBytes(1L, Math.toIntExact(size));
```

`Math.toIntExact` từ chối một `long` vượt miền `int`, nhưng giới hạn 8 MiB phía trước mới là **chính sách bộ nhớ** của ví dụ. Đừng dựa riêng vào giới hạn kiểu `int` để bảo vệ heap. Sau khi dùng stream hoặc dữ liệu đã sao chép từ locator, đóng stream rồi gọi `free()` khi driver hỗ trợ và không còn cần `Blob`/`Clob`.

Đừng gọi `getAsciiStream()` của CLOB để xử lý văn bản tiếng Việt/Unicode: nó chỉ cho luồng biểu diễn ASCII và không thay thế `getCharacterStream()` khi cần ký tự đầy đủ.

## 4. Ví dụ chạy được Java 17 + H2: cùng dữ liệu, hai cách đọc

Ví dụ này sử dụng H2 in-memory để không cần máy chủ database riêng. Cần **JDK 17+** và file JDBC driver **H2 2.x** (đặt tên `h2.jar` trong thư mục chạy). JDBC class được nạp từ classpath theo cơ chế Java Service Provider; trong mã không cần import lớp riêng của H2. Dữ liệu mẫu cố ý nhỏ để dễ xác minh kết quả; cùng nguyên tắc đọc được áp dụng khi LOB có kích thước lớn.

Tạo file `LobReadDemo.java` với toàn bộ nội dung sau:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.Reader;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

public final class LobReadDemo {
    private static final long DOCUMENT_ID = 1L;

    public static void main(String[] args) throws Exception {
        try (Connection connection =
                DriverManager.getConnection("jdbc:h2:mem:lobdemo", "sa", "")) {
            createData(connection);
            readAllAtOnce(connection);
            readInChunks(connection);
        }
    }

    private static void createData(Connection connection) throws SQLException {
        try (Statement statement = connection.createStatement()) {
            statement.execute("""
                CREATE TABLE documents (
                    id BIGINT PRIMARY KEY,
                    picture BLOB,
                    body CLOB
                )
                """);
        }

        try (PreparedStatement statement = connection.prepareStatement(
                "INSERT INTO documents (id, picture, body) VALUES (?, ?, ?)")) {
            statement.setLong(1, DOCUMENT_ID);
            statement.setBytes(2, new byte[] {0, 1, 2, (byte) 0xFF});
            statement.setString(3, "Xin chào JDBC");
            statement.executeUpdate();
        }
    }

    private static void readAllAtOnce(Connection connection)
            throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(
                "SELECT picture, body FROM documents WHERE id = ?")) {
            statement.setLong(1, DOCUMENT_ID);
            try (ResultSet rs = statement.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException("Document not found");
                }

                // Materialize toàn bộ BLOB và CLOB vào heap.
                byte[] bytes = rs.getBytes("picture");
                String text = rs.getString("body");

                if (bytes == null || text == null) {
                    throw new SQLException("Unexpected SQL NULL");
                }

                System.out.println("all_blob_bytes=" + bytes.length);
                System.out.println("all_clob_text=" + text);
            }
        }
    }

    private static void readInChunks(Connection connection)
            throws SQLException, IOException {
        try (PreparedStatement statement = connection.prepareStatement(
                "SELECT picture, body FROM documents WHERE id = ?")) {
            statement.setLong(1, DOCUMENT_ID);
            try (ResultSet rs = statement.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException("Document not found");
                }

                long byteCount = 0;
                try (InputStream input = rs.getBinaryStream("picture")) {
                    if (input == null) {
                        throw new SQLException("BLOB is SQL NULL");
                    }
                    byte[] buffer = new byte[8192];
                    int size;
                    while ((size = input.read(buffer)) != -1) {
                        byteCount += size;
                    }
                } // Đóng stream nhị phân trước khi đọc cột khác.
                System.out.println("stream_blob_bytes=" + byteCount);

                long charCount = 0;
                try (Reader reader = rs.getCharacterStream("body")) {
                    if (reader == null) {
                        throw new SQLException("CLOB is SQL NULL");
                    }
                    char[] buffer = new char[4096];
                    int size;
                    while ((size = reader.read(buffer)) != -1) {
                        charCount += size;
                    }
                }
                System.out.println("stream_clob_chars=" + charCount);
            }
        }
    }
}
~~~

Biên dịch từ thư mục có `LobReadDemo.java`:

~~~bash
javac -encoding UTF-8 LobReadDemo.java
~~~

Chạy trên Linux/macOS (sử dụng dấu `:` để ngăn cách classpath):

~~~bash
java -cp ".:h2.jar" LobReadDemo
~~~

Hoặc trên Windows PowerShell (sử dụng dấu `;` để ngăn cách classpath):

~~~powershell
java -cp ".;h2.jar" LobReadDemo
~~~

**Kết quả kỳ vọng với dữ liệu vừa tạo:**

~~~text
all_blob_bytes=4
all_clob_text=Xin chào JDBC
stream_blob_bytes=4
stream_clob_chars=13
~~~

Vì `"Xin chào JDBC"` dài 13 đơn vị ký tự UTF-16 trong ví dụ này, vòng lặp trên `Reader` đếm được 13. Khi gặp ký tự bổ sung như emoji, số đơn vị `char` Java đọc được có thể khác với số Unicode code point mà người dùng nhìn thấy. Đừng đồng nhất ký tự, code point, byte UTF-8 và số chữ hiển thị.

**Giải thích tại sao ví dụ chứng minh sự khác nhau:** `readAllAtOnce` tạo `byte[]` và `String` rồi dùng sau khi getter trả về; `readInChunks` giữ một `byte[8192]` và `char[4096]`, chỉ đếm những phần đã đọc mà không gom vào mảng lớn. Trên dữ liệu 4 byte và 13 ký tự, cả hai phù hợp; lợi thế bộ nhớ của cách thứ hai chỉ rõ khi kích thước LOB tăng và driver không giữ sẵn toàn bộ giá trị.

Trong chương trình thật, vòng lặp streaming thường **ghi dữ liệu ra đích** hoặc đưa từng phần qua bộ xử lý. Ví dụ trên chỉ đếm để dễ kiểm tra đầu ra; nó không tạo file.

## 5. Đọc luồng hữu ích khi chuyển dữ liệu sang một đích thực

### 5.1. Sao chép BLOB ra file

Khi `ResultSet rs` đang đứng trên đúng hàng, đoạn sau có thể ghi một BLOB vào file, sử dụng `java.nio.file.Files`. Đây là **mảnh mã minh họa trong phạm vi ResultSet/Statement/Connection còn mở**:

~~~java
Path output = Path.of("download.bin");
try (InputStream source = rs.getBinaryStream("picture");
     OutputStream target = Files.newOutputStream(output)) {
    if (source == null) {
        throw new IllegalStateException("SQL NULL cannot be downloaded");
    }
    long bytesCopied = source.transferTo(target);
    System.out.println("bytesCopied=" + bytesCopied);
}
~~~

Cần import `java.io.InputStream`, `java.io.OutputStream`, `java.nio.file.Path`, `java.nio.file.Files`. `InputStream.transferTo(OutputStream)` (Java 9+) sao chép tuần tự; khi đích là `FileOutputStream`, nó không yêu cầu giữ toàn bộ nội dung trong một `byte[]` của ứng dụng. **Không mở file xuất chính thức trước khi xác minh dữ liệu tồn tại**, hoặc dùng file tạm và đổi tên nguyên tử sau khi sao chép thành công để tránh để lại file hỏng khi truyền lỗi.

Ví dụ này giả định đường dẫn do ứng dụng kiểm soát. Trong dịch vụ thực tế phải kiểm soát nơi ghi, quyền filesystem, path traversal, dung lượng đĩa và phương án xóa file tạm nếu lỗi.

### 5.2. Xử lý CLOB qua `Reader`

Với văn bản, `Reader` trả từng khối **ký tự**, không phải byte. Nếu muốn lưu ra file UTF-8, phải chỉ định charset khi tạo `Writer`:

~~~java
Path output = Path.of("article.txt");
try (Reader source = rs.getCharacterStream("body");
     Writer target = Files.newBufferedWriter(output, StandardCharsets.UTF_8)) {
    if (source == null) {
        throw new IllegalStateException("SQL NULL cannot be exported");
    }
    long charsCopied = source.transferTo(target);
    System.out.println("charsCopied=" + charsCopied);
}
~~~

Cần import `java.io.Reader`, `java.io.Writer`, `java.nio.charset.StandardCharsets` và các lớp `Path`/`Files`. Phương thức `Reader.transferTo(Writer)` trả về **số `char` Java đã chuyển**; kích thước file UTF-8 sinh ra có thể nhiều byte hơn. Đừng dùng `new String(byte[], charset)` theo từng chunk nhị phân bất kỳ: một ký tự UTF-8 có thể bị cắt giữa hai chunk. Với CLOB, dùng `Reader`; khi thực sự chỉ có nguồn byte văn bản, dùng `InputStreamReader` có charset và decoder trạng thái phù hợp.

### 5.3. Các thao tác vô tình làm mất lợi ích streaming

Những mẫu sau có thể dẫn đến **giữ toàn bộ LOB trong heap**:

~~~java
byte[] all = rs.getBinaryStream(1).readAllBytes();
ByteArrayOutputStream memory = new ByteArrayOutputStream();
rs.getBinaryStream(1).transferTo(memory);
StringWriter text = new StringWriter();
rs.getCharacterStream(2).transferTo(text);
~~~

Đây chỉ là **ví dụ phản diện ngắn**, không phải một trình tự chạy liên tiếp trên cùng `ResultSet`. `readAllBytes`, `ByteArrayOutputStream` và `StringWriter` đều tích lũy nội dung. Streaming chỉ thật sự giảm bộ nhớ phía ứng dụng khi **đích hoặc phép xử lý cũng hoạt động theo từng phần**, chẳng hạn file, bộ đếm, checksum, parser tăng dần hoặc một kết nối mạng đã có cơ chế backpressure.

## 6. Vòng đời tài nguyên: phần dễ sai nhất với LOB

LOB có thể được driver biểu diễn bằng locator trỏ tới dữ liệu phía database; các đối tượng `Blob`/`Clob` được mô tả là có vòng đời gắn với transaction tạo chúng. Ngoài ra, stream trả về từ `ResultSet` phụ thuộc vào tài nguyên `ResultSet` và statement. Vì vậy:

1. Mở connection và statement, chạy truy vấn.
2. `rs.next()`, kiểm tra có hàng; gọi getter LOB.
3. **Đọc hết hoặc xử lý phần mong muốn ngay trong phạm vi còn mở.**
4. Đóng `InputStream`/`Reader`, giải phóng `Blob`/`Clob` locator nếu đã tạo và driver hỗ trợ.
5. Sau đó mới đóng `ResultSet`, `Statement` và trả connection cho pool.

Một lỗi hay gặp:

~~~java
// SAI về thiết kế vòng đời: phương thức trả stream sau khi đóng ResultSet.
InputStream fetchLater(Connection connection) throws SQLException {
    try (PreparedStatement ps = connection.prepareStatement(
            "SELECT picture FROM documents WHERE id = 1");
         ResultSet rs = ps.executeQuery()) {
        if (!rs.next()) {
            return null;
        }
        return rs.getBinaryStream(1);
    } // ResultSet và PreparedStatement đóng ở đây.
}
~~~

Khi người gọi bắt đầu `read()` trên stream đã trả, connection/result set có thể đã đóng và thao tác thất bại. Một số driver đệm hết dữ liệu làm lỗi **không lộ ra trong môi trường thử nghiệm**, nhưng cách viết này không an toàn về hợp đồng tài nguyên.

**Cách đúng:** truyền `OutputStream`/`Writer` hoặc một hàm callback vào tầng truy vấn, thực hiện sao chép hoặc xử lý trong callback, rồi chỉ trả **kết quả đã độc lập với JDBC** (số byte, checksum, đường dẫn file đã hoàn tất, DTO metadata). Với dữ liệu nhỏ, trả `byte[]`/`String` sau khi materialize là hợp lệ nếu kích thước đã được chặn.

Đừng giữ `ResultSet`, `Blob`, `Clob`, `InputStream` hoặc `Reader` JDBC trong field của singleton Spring bean hoặc cache application như đối tượng sử dụng lâu dài. Đặc biệt, trả stream database trực tiếp cho một tác vụ bất đồng bộ hoặc HTTP response được ghi sau khi method repository kết thúc rất dễ vượt vòng đời transaction/connection.

### Transaction có vai trò gì?

Với một số driver, truy cập LOB locator có thể cần **transaction vẫn còn mở**. Cơ chế auto-commit, cursor, cách server lưu LOB, hành vi khi commit/rollback và khả năng stream sau khi commit khác nhau giữa RDBMS. Nếu quy trình đọc có yêu cầu transaction, hãy đảm bảo nó bao trọn hành động đọc, trên đúng connection/transaction manager. **Không tự giả định `@Transactional(readOnly = true)` sẽ giữ transaction trong một thread async khác**, vì transaction Spring thông thường gắn với thread hiện tại.

Một request HTTP tải file lớn trực tiếp từ database có thể giữ connection của pool cho tới khi client tải xong; khi có nhiều client chậm, pool có thể cạn. Cân nhắc giới hạn thời gian/kích thước, lưu nội dung vào object storage hoặc tạo file tạm hợp lệ rồi phát từ kho riêng nếu vòng đời download dài. Đó là quyết định kiến trúc, không phải điều kiện bắt buộc cho mọi LOB nhỏ.

## 7. Spring JDBC: dùng `JdbcTemplate` đúng vòng đời

`JdbcTemplate` quản lý connection, statement, `ResultSet` và chuyển lỗi `SQLException` thành `DataAccessException`. Nó **không** tự làm cho một JDBC stream an toàn sau khi callback kết thúc. Vì vậy việc đọc luồng phải diễn ra **bên trong** `ResultSetExtractor` hoặc `RowCallbackHandler`.

Ví dụ sau là **một lớp repository trong dự án Spring** dùng `spring-jdbc`, `DataSource` và bảng `documents` đã tồn tại. Nó thể hiện song song đọc toàn bộ một BLOB nhỏ và chép BLOB lớn bằng streaming. Phương thức `copyBlobTo` nhận `OutputStream` do bên gọi quản lý và **không tự đóng đích**.

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.UncheckedIOException;

import org.springframework.dao.DataRetrievalFailureException;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.ResultSetExtractor;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class DocumentLobRepository {
    private final JdbcTemplate jdbcTemplate;

    public DocumentLobRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public byte[] loadSmallBlob(long id) {
        return jdbcTemplate.queryForObject(
                "SELECT picture FROM documents WHERE id = ?",
                (rs, rowNum) -> rs.getBytes(1),
                id);
    }

    @Transactional(readOnly = true)
    public long copyBlobTo(long id, OutputStream destination) {
        Long copied = jdbcTemplate.query(
                "SELECT picture FROM documents WHERE id = ?",
                (ResultSetExtractor<Long>) rs -> {
                    if (!rs.next()) {
                        throw new EmptyResultDataAccessException(1);
                    }

                    try (InputStream input = rs.getBinaryStream(1)) {
                        if (input == null) {
                            throw new DataRetrievalFailureException(
                                    "Document BLOB is SQL NULL");
                        }
                        return input.transferTo(destination);
                    } catch (IOException ex) {
                        throw new UncheckedIOException(ex);
                    }
                },
                id);
        return copied;
    }
}
~~~

**Điểm cần hiểu:**

- `loadSmallBlob` dùng `queryForObject`/`getBytes`; hợp lý khi chính sách nghiệp vụ đảm bảo ảnh nhỏ. Nếu không tìm thấy hàng, Spring ném ngoại lệ số lượng kết quả không mong đợi. Nếu cột là SQL `NULL`, giá trị trả về có thể là `null`.
- `copyBlobTo` dùng `ResultSetExtractor<Long>`: Spring giữ `ResultSet` còn mở trong lúc callback chuyển dữ liệu sang `destination`.
- `EmptyResultDataAccessException` thể hiện **không tìm thấy hàng**; `DataRetrievalFailureException` ở đây thể hiện **hàng có BLOB NULL**, hai tình huống khác nhau.
- `IOException` được bọc thành `UncheckedIOException` vì callback `ResultSetExtractor` khai báo `SQLException` và `DataAccessException`, không khai báo checked `IOException`.
- Spring quản lý việc đóng connection/statement; repository đóng riêng `InputStream` mà nó đã mở. Bên gọi quản lý `destination` và phải đóng nó sau khi phương thức kết thúc.
- `@Transactional(readOnly = true)` giúp biểu đạt phạm vi đọc nếu phương thức được gọi thông qua Spring proxy và có transaction manager thích hợp; annotation không bảo đảm mọi driver thật sự stream hoặc chặn write ở DB.
- Một callback sao chép ra HTTP response có thể chặn vì client đọc chậm; với tải đồng thời cao phải cân nhắc ảnh hưởng lên pool và thời gian giữ connection.

Đối với CLOB, thay `InputStream` bằng `Reader`, `OutputStream` bằng `Writer`, và `rs.getBinaryStream(1)` bằng `rs.getCharacterStream(1)`; `Reader.transferTo(Writer)` cung cấp số đơn vị ký tự đã truyền. Nếu cần map nhiều hàng và xử lý từng hàng, `RowCallbackHandler` thích hợp, nhưng hãy xử lý xong stream của **mỗi hàng** trước khi Spring chuyển sang hàng kế tiếp.

### Phần lưu trữ: cũng có đọc toàn bộ và ghi theo stream

Với file nhỏ, có thể chèn bằng `PreparedStatement.setBytes(index, bytes)`, hoặc CLOB nhỏ bằng `setString(index, text)`. Với nguồn lớn có sẵn dưới dạng stream:

~~~java
// Mảnh mã bên trong callback PreparedStatement hoặc JDBC method.
ps.setLong(1, documentId);
ps.setBinaryStream(2, inputStream);
ps.setCharacterStream(3, reader);
ps.executeUpdate();
~~~

Với driver cần biết trước kích thước, JDBC có overload nhận `long length` và các dạng thích hợp. Một stream đầu vào phải còn mở **cho tới khi JDBC hoàn tất việc tiêu thụ trong execute**, và bên sở hữu phải đóng nó. Không tạo `byte[]` khổng lồ chỉ để gọi `setBytes` nếu đã có nguồn stream. Đồng thời không giả định `setBinaryStream` tự bảo đảm DB truyền theo từng chunk; phải kiểm tra driver.

## 8. `NULL`, độ dài và dữ liệu văn bản Unicode

Ba tình huống sau **khác nhau**:

1. **Không có hàng**: truy vấn không trả hàng nào; `rs.next()` trả `false`.
2. **Có hàng, LOB bằng SQL `NULL`**: `getBytes`/`getString`/`getBinaryStream`/`getCharacterStream` có thể trả `null`; `getBlob`/`getClob` cũng có thể trả `null`.
3. **Có hàng, LOB rỗng**: thường có thể lấy mảng dài 0, chuỗi rỗng, hoặc stream kết thúc ngay; cách tạo/phân biệt LOB rỗng phụ thuộc RDBMS.

Không nên viết `rs.getBinaryStream(...).transferTo(...)` mà chưa xử lý `null` nếu cột cho phép SQL `NULL`. Khi cột là `NOT NULL`, vẫn cần phân biệt trường hợp không có hàng.

**Độ dài:** `Blob.length()` tính byte; `Clob.length()` tính ký tự theo JDBC/DB; `String.length()` và bộ đếm `Reader` của Java dùng đơn vị UTF-16 `char`. Từ đó, byte UTF-8 trên đĩa, Unicode code point và ký tự người dùng nhìn thấy không nhất thiết có cùng con số. Với nội dung cần giới hạn theo giao diện, chọn đơn vị đo và xử lý Unicode nhất quán.

**Charset:** CLOB được JDBC biểu diễn bằng dữ liệu ký tự, nên `Reader` giúp tránh việc tự giải mã byte ở tầng ứng dụng. Nếu một nguồn là BLOB chứa văn bản UTF-8 có chủ đích, muốn biến thành ký tự phải sử dụng charset cụ thể (ví dụ `StandardCharsets.UTF_8`) và bộ giải mã có thể xử lý ký tự trải qua ranh giới chunk. Không dùng `Reader` cho bytes nhị phân ngẫu nhiên.

## 9. Rủi ro hiệu năng và giới hạn cần đặt

Những điều sau giúp hiểu rõ việc dùng LOB trong môi trường thực:

- **Kích thước và số lượt đồng thời:** 30 request cùng đọc toàn bộ 40 MiB đã yêu cầu khoảng 1,2 GiB dữ liệu mảng gốc, chưa kể bộ đệm/copy của Java và driver. Đó là ví dụ nhân số học về **bộ nhớ tối thiểu của các mảng đó**, không phải phép đo heap thực tế.
- **Kích thước buffer:** thường bắt đầu từ vài KiB tới vài chục KiB (ví dụ 8 KiB); đo throughput và latency thay vì luôn tăng buffer. Buffer quá lớn nhân với số request đồng thời cũng tiêu tốn heap.
- **Driver có thể prefetch/buffer:** stream API không tự xác nhận truyền theo chunk. Theo dõi heap, GC, round trips và JDBC/DB driver trên môi trường thực.
- **Connection pool:** streaming lâu giữ connection; cần timeout, giới hạn kích thước/tốc độ nếu phù hợp, và xử lý huỷ khi client ngắt kết nối.
- **Không `SELECT *` trên danh sách:** truy vấn metadata và LOB riêng, theo ID; tối ưu index và hạn chế lấy dữ liệu không dùng.
- **Nén/chuyển mã:** không tự nén những dạng vốn đã nén như JPEG/ZIP rồi kỳ vọng tiết kiệm đáng kể; không chuyển BLOB thành Base64 nếu có thể truyền byte trực tiếp, vì Base64 tăng dung lượng.
- **Bảo mật:** giới hạn quyền xem tải LOB theo người dùng, loại MIME/filename được tin cậy, vùng ghi file, chống path traversal và ghi log tránh làm lộ nội dung nhạy cảm.
- **Kiến trúc dữ liệu:** với nội dung rất lớn hoặc rất nhiều lượt tải, cân nhắc object storage và chỉ giữ khóa, metadata hoặc URL ký có thời hạn trong database. Chọn phương án theo nghiệp vụ, backup, bảo mật, giao dịch và chi phí.

## 10. Kiểm thử và xác minh

Một bài kiểm thử LOB đầy đủ nên có các ca:

| Trường hợp | Kiểm tra |
| --- | --- |
| BLOB nhỏ chứa `0x00`, `0xFF`, byte không in được | Đọc đầy đủ và streaming trả **chuỗi byte giống hệt** khi ghi ra `ByteArrayOutputStream` trong test có kích thước giới hạn, hoặc so checksum |
| CLOB chứa tiếng Việt, xuống dòng, emoji | Nội dung sau đọc giống bản gốc, không sai dấu; không nhầm số byte với ký tự |
| LOB rỗng | Phân biệt 0 byte/0 ký tự với `NULL` |
| SQL `NULL` | Getter xử lý `null`, không ném `NullPointerException` ngoài ý muốn |
| Không có bản ghi theo ID | Trả trạng thái “not found” phù hợp, không báo file rỗng |
| LOB lớn hơn ngưỡng đọc toàn bộ | Từ chối theo chính sách hoặc chuyển sang streaming; không tràn khi ép `long` thành `int` |
| Đích ghi file lỗi giữa chừng | Stream/statement/connection được đóng, file tạm được dọn đúng chính sách |
| Nhiều lượt tải đồng thời | Đo heap, GC, database connections, thời gian chờ pool và throughput |
| Kết thúc transaction sớm | Đảm bảo không trả stream đang phụ thuộc ResultSet/connection đã đóng |

Khi so sánh hai chiến lược, hãy kiểm tra **nội dung** bằng checksum (với BLOB) hoặc so sánh chuỗi/từng ký tự (với CLOB), không chỉ so sánh độ dài. Hai chuỗi byte khác nhau có thể cùng kích thước.

Một integration test với đúng JDBC driver và hệ quản trị triển khai là cần thiết để xác định streaming có thật sự giảm heap và cách driver xử lý locator, transaction, fetch size, charset, `NULL`. Test trên H2 chứng minh cơ chế JDBC cơ bản, **không bảo đảm driver khác có cùng đặc tính bộ nhớ hoặc transaction**.

## 11. Các nhầm lẫn thường gặp

**“Cứ gọi `getBinaryStream()` thì chắc chắn dùng ít RAM?”** Chưa chắc. Luồng giúp code ứng dụng xử lý tuần tự, nhưng driver có thể đệm; thêm vào đó nếu đưa nó vào `readAllBytes()` thì ứng dụng lại materialize toàn bộ.

**“`Blob.getBytes(1, (int) blob.length())` luôn an toàn?”** Không. `length()` là `long`; phép ép kiểu có thể làm sai độ dài và việc tạo mảng lớn dễ gây hết heap. Giới hạn kích thước trước và chọn streaming khi cần.

**“CLOB và BLOB chỉ khác tên kiểu SQL?”** Không. CLOB chứa ký tự, BLOB chứa byte. Quy tắc chuyển mã, API, độ dài và cách xử lý dữ liệu khác nhau.

**“Một `InputStream` trả về từ repository có thể đọc sau khi `JdbcTemplate.query` kết thúc?”** Không nên dựa vào điều này; Spring đóng tài nguyên JDBC sau callback. Hãy tiêu thụ stream trong callback hoặc trả dữ liệu đã độc lập với JDBC.

**“`@Transactional` ở controller đồng bộ sẽ tự bảo vệ một `StreamingResponseBody` chạy sau?”** Không bảo đảm. Tác vụ viết response có thể thực thi bất đồng bộ trên thread khác, không tự thừa hưởng transaction gắn với thread đã tạo response. Thiết kế phạm vi truy cập DB và sao chép dữ liệu rõ ràng.

**“Tăng `fetchSize` luôn tối ưu tải một BLOB khổng lồ?”** Không. Fetch size chủ yếu điều chỉnh cách driver lấy **nhiều hàng**; hành vi chuyển dữ liệu của một LOB còn phụ thuộc driver và cấu hình khác.

**“Đọc 200.000 ký tự CLOB nghĩa là tải 200.000 byte?”** Không. Byte khi lưu/truyền còn phụ thuộc charset/encoding; Java `String`/Reader cũng có đơn vị `char` riêng.

## 12. Câu hỏi tự kiểm tra

1. Một hàng có BLOB 300 MiB, ứng dụng chỉ cần chuyển byte ra tệp. Vì sao `ResultSet.getBytes()` thường không phải lựa chọn tốt? **Vì nó materialize mảng lớn; có thể sao chép trực tiếp từ `getBinaryStream()` vào `OutputStream` bằng buffer nhỏ**, với lưu ý khả năng đệm của driver và vòng đời connection.
2. Cột CLOB có văn bản “Chào bạn”. Nên dùng `InputStream` hay `Reader`? **`Reader`** vì cần xử lý ký tự/Unicode; chỉ dùng byte khi đã có quy ước encoding rõ ràng.
3. Repository trả về `Blob` locator cho service gọi sau khi transaction kết thúc. Có an toàn không? **Không có bảo đảm**; locator thường phụ thuộc transaction/connection. Nên xử lý trong phạm vi còn mở hoặc materialize dữ liệu nhỏ có kiểm soát.
4. `rs.next()` là `true` nhưng `rs.getBinaryStream("picture")` trả `null`. Điều đó có nghĩa gì? **Bản ghi tồn tại, giá trị cột là SQL `NULL`**, không đồng nghĩa file dài 0 byte.
5. Trong ví dụ H2, vì sao cả hai cách cho ra cùng số byte và ký tự? **Vì cùng đọc một giá trị LOB đến hết**, sự khác biệt nằm ở phương thức giữ/di chuyển dữ liệu, không phải ở nội dung.

## 13. Tài liệu tham khảo

- Java SE 17, `java.sql.Blob` — length, `getBytes`, `getBinaryStream`, `free`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Blob.html
- Java SE 17, `java.sql.Clob` — `getSubString`, `getCharacterStream`, `free`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Clob.html
- Java SE 17, `java.sql.ResultSet` — `getBytes`, `getString`, `getBinaryStream`, `getCharacterStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html
- Spring Framework, `JdbcTemplate` và các callback JDBC: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring `ResultSetExtractor<T>`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/ResultSetExtractor.html
- H2 Database, loại dữ liệu `BLOB`/`CLOB`: https://h2database.github.io/html/datatypes.html