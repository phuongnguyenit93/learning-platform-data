# Đóng stream tài nguyên bằng try-with-resources trong Java 17

**Chủ đề:** Java 17  
**Chương:** Tệp và mã hóa ký tự  
**Bài học:** Đóng stream tài nguyên bằng try-with-resources

Khi làm việc với tệp, stream, socket hoặc kết nối cơ sở dữ liệu, chương trình thường phải giải phóng tài nguyên sau khi hoàn tất. Nếu quên đóng, ứng dụng có thể giữ file descriptor, socket, buffer hoặc connection lâu hơn cần thiết, gây rò rỉ tài nguyên và làm các thao tác sau thất bại.

Java cung cấp cú pháp **try-with-resources** để tự động gọi `close()` cho tài nguyên sau khi khối `try` kết thúc. Cú pháp này giúp việc giải phóng tài nguyên diễn ra cả khi khối `try` hoàn tất bình thường lẫn khi có exception hoặc `return`.

Trong Java 17, try-with-resources là tính năng ổn định từ Java 7; cú pháp dùng biến tài nguyên đã khai báo bên ngoài khối `try` được bổ sung từ Java 9. Đây là cách chuẩn của Java để quản lý những đối tượng có vòng đời cần đóng rõ ràng.

Bài học tập trung vào:

- Điều kiện để một đối tượng dùng được trong try-with-resources.
- Cách khai báo một hoặc nhiều tài nguyên.
- Thứ tự khởi tạo và đóng tài nguyên.
- Cách Java xử lý exception khi cả phần thân và `close()` đều lỗi.
- Cú pháp dùng biến tài nguyên đã khai báo trước.
- Ứng dụng với tệp văn bản UTF-8, byte stream và JDBC.
- Cách thiết kế quyền sở hữu tài nguyên để tránh đóng nhầm hoặc đóng nhiều lần.

## 1. Vì sao phải đóng tài nguyên?

Một số đối tượng Java đại diện cho tài nguyên bên ngoài heap:

- `InputStream` và `OutputStream` đọc/ghi byte.
- `Reader` và `Writer` đọc/ghi ký tự.
- `BufferedReader` và `BufferedWriter` cung cấp bộ đệm cho thao tác văn bản.
- `Socket` và các stream gắn với socket quản lý kết nối mạng.
- `Connection`, `Statement`, `PreparedStatement`, `ResultSet` quản lý tài nguyên JDBC.
- `ZipFile` và các API tương tự quản lý file hoặc cấu trúc lưu trữ.

Không phải mọi object Java đều cần gọi `close()`. Một `String`, `List` hoặc `BigDecimal` thông thường không đại diện cho tài nguyên có vòng đời đóng. Cần đóng những đối tượng mà API yêu cầu giải phóng tài nguyên.

Ví dụ đọc file:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class ReadFileExample {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("message.txt");

        BufferedReader reader =
                Files.newBufferedReader(path, StandardCharsets.UTF_8);

        String line;
        while ((line = reader.readLine()) != null) {
            System.out.println(line);
        }

        reader.close();
    }
}
```

Đoạn code đóng reader khi đọc hết bình thường. Nhưng nếu `readLine()` ném `IOException`, chương trình thoát khỏi phương thức trước khi đến `reader.close()`. Tài nguyên có thể không được giải phóng.

Có thể đặt `close()` trong `finally`, nhưng phải tự xử lý trường hợp `null`, exception từ thao tác đóng và việc không để lỗi đóng che mất lỗi đọc. Try-with-resources giải quyết những việc đó bằng cú pháp ngôn ngữ.

## 2. Điều kiện: tài nguyên phải triển khai AutoCloseable

Try-with-resources chỉ nhận những tài nguyên có kiểu triển khai `java.lang.AutoCloseable`.

```java
public interface AutoCloseable {
    void close() throws Exception;
}
```

Khi khối `try` kết thúc, Java tự gọi `close()` trên từng tài nguyên đã được khởi tạo thành công.

`java.io.Closeable` là interface con của `AutoCloseable`:

```java
public interface Closeable extends AutoCloseable {
    void close() throws IOException;
}
```

Vì vậy, các stream và reader/writer I/O chuẩn thường dùng được với try-with-resources. `Closeable.close()` khai báo exception hẹp hơn là `IOException`, trong khi `AutoCloseable.close()` có thể khai báo `Exception`.

Một số điểm cần hiểu:

- `AutoCloseable` mô tả một đối tượng có thao tác đóng.
- Việc triển khai `AutoCloseable` không có nghĩa đối tượng tự đóng ngay khi không còn tham chiếu.
- Java chỉ tự gọi `close()` ở cuối khối try-with-resources.
- Đối tượng tự tạo có thể triển khai `AutoCloseable` để tham gia cơ chế này.
- Nếu resource expression có giá trị `null`, Java không gọi `close()` trên giá trị đó.

### 2.1. Tạo một tài nguyên tự định nghĩa

```java
class ReportSession implements AutoCloseable {

    public void write(String message) {
        System.out.println("Write: " + message);
    }

    @Override
    public void close() {
        System.out.println("Release report session");
    }
}
```

Dùng với try-with-resources:

```java
try (ReportSession session = new ReportSession()) {
    session.write("Monthly report");
}
```

Khi rời khỏi khối `try`, Java gọi `session.close()` tự động. Người viết code không phải nhớ gọi `close()` ở từng nhánh `if`, `return` hoặc `catch`.

Nếu thao tác đóng cần báo lỗi, có thể khai báo exception phù hợp:

```java
class FileSession implements AutoCloseable {

    @Override
    public void close() throws IOException {
        // Giải phóng tài nguyên; có thể ném IOException.
    }
}
```

Nên thiết kế `close()` để giải phóng tài nguyên một cách rõ ràng, kết thúc nhanh và không thực hiện thêm công việc nghiệp vụ không liên quan.

## 3. Cú pháp cơ bản của try-with-resources

Cấu trúc tổng quát:

```java
try (ResourceType resource = createResource()) {
    // Dùng resource ở đây
} catch (SomeException exception) {
    // Xử lý lỗi nếu cần
} finally {
    // Phần này vẫn chạy sau khi resource đã được đóng
}
```

Phần trong ngoặc tròn là *resource specification*. Có thể khai báo một hoặc nhiều tài nguyên, phân cách bằng dấu chấm phẩy.

Ví dụ đọc tệp văn bản:

```java
Path path = Path.of("message.txt");

try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {

    String line;
    while ((line = reader.readLine()) != null) {
        System.out.println(line);
    }
}
```

Khi khối `try` kết thúc, `reader.close()` được gọi tự động. Điều này vẫn xảy ra nếu:

- Đọc đến cuối file.
- Có `return` bên trong khối.
- Có `break` hoặc `continue` làm thoát khỏi khối tương ứng.
- Một exception được ném ra trong phần thân.
- Có exception được xử lý ở `catch` sau khi tài nguyên đã đóng.

### 3.1. Khối catch chạy sau khi tài nguyên được đóng

```java
try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {

    System.out.println(reader.readLine());

} catch (IOException exception) {
    System.err.println("Không thể đọc file: " + exception.getMessage());
}
```

Trình tự là:

1. Java tạo tài nguyên.
2. Chạy phần thân `try`.
3. Khi phần thân kết thúc, gọi `close()`.
4. Sau khi xử lý đóng tài nguyên, chuyển đến `catch` phù hợp nếu có exception.
5. Chạy `finally` nếu có.

Vì vậy, trong `catch`, tài nguyên đã được đóng. Không nên tiếp tục sử dụng reader/stream đó như thể nó vẫn mở.

### 3.2. Khối finally vẫn được dùng bình thường

`finally` vẫn hữu ích cho những công việc không phải đóng resource, ví dụ cập nhật trạng thái hoặc giải phóng một tài nguyên khác không hỗ trợ `AutoCloseable`.

```java
try (var reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    process(reader);
} catch (IOException exception) {
    logReadFailure(exception);
} finally {
    updateRequestMetrics();
}
```

Thứ tự quan trọng: resource được đóng trước khi `catch` và `finally` bên ngoài chạy. Không cần đặt `reader.close()` trong `finally` nữa.

## 4. Nhiều tài nguyên trong cùng một try

Có thể khai báo nhiều tài nguyên trong cùng cặp ngoặc:

```java
try (
    var reader = Files.newBufferedReader(input, StandardCharsets.UTF_8);
    var writer = Files.newBufferedWriter(output, StandardCharsets.UTF_8)
) {
    String line;

    while ((line = reader.readLine()) != null) {
        writer.write(line);
        writer.newLine();
    }
}
```

Trong ví dụ này:

- `reader` được tạo trước.
- `writer` được tạo sau.
- Khi rời khối `try`, `writer` được đóng trước.
- Sau đó `reader` được đóng.

### 4.1. Tài nguyên được đóng theo thứ tự ngược

Quy tắc đóng là **last-in, first-out (LIFO)**: tài nguyên được khởi tạo sau sẽ đóng trước.

```text
Khởi tạo:
  1. resource A
  2. resource B
  3. resource C

Đóng tự động:
  1. resource C
  2. resource B
  3. resource A
```

Thứ tự này hữu ích khi tài nguyên sau phụ thuộc vào tài nguyên trước. Ví dụ writer/reader được tạo từ một file hoặc wrapper được tạo từ stream bên dưới; đóng wrapper trước giúp nó hoàn tất công việc trước khi stream gốc được đóng.

### 4.2. Chú ý khi khởi tạo tài nguyên thứ hai thất bại

Giả sử `reader` đã mở thành công nhưng việc tạo `writer` thất bại. Java vẫn đóng `reader` đã được khởi tạo trước đó.

```java
try (
    var reader = Files.newBufferedReader(input, StandardCharsets.UTF_8);
    var writer = Files.newBufferedWriter(output, StandardCharsets.UTF_8)
) {
    copy(reader, writer);
}
```

Nếu khởi tạo `writer` ném exception:

1. Phần thân `try` không chạy.
2. `reader` đã tạo thành công được đóng.
3. Exception từ việc khởi tạo `writer` được truyền ra.
4. Nếu `reader.close()` cũng ném exception, lỗi đóng được ghi nhận là suppressed exception của lỗi khởi tạo.

Đây là điểm quan trọng: tài nguyên đã mở không bị bỏ quên chỉ vì một tài nguyên khác trong cùng danh sách không tạo được.

## 5. Đóng tài nguyên và suppressed exceptions

Một tình huống thực tế là cả phần thân `try` lẫn phương thức `close()` đều ném exception.

Nếu dùng cách đóng thủ công trong `finally`, lỗi đóng có thể che mất lỗi ban đầu. Try-with-resources có quy tắc riêng để bảo toàn exception chính.

### 5.1. Exception trong phần thân là exception chính

```java
class DemoResource implements AutoCloseable {

    @Override
    public void close() throws IOException {
        throw new IOException("close failed");
    }
}

public class SuppressedExample {
    public static void main(String[] args) {
        try (DemoResource resource = new DemoResource()) {
            throw new IOException("body failed");
        } catch (IOException exception) {
            System.out.println("Primary: " + exception.getMessage());

            for (Throwable suppressed : exception.getSuppressed()) {
                System.out.println("Suppressed: " + suppressed.getMessage());
            }
        }
    }
}
```

Kết quả:

```text
Primary: body failed
Suppressed: close failed
```

Exception từ phần thân `try` được giữ làm **primary exception**. Exception phát sinh khi đóng tài nguyên được gắn vào exception chính bằng `addSuppressed()` và có thể đọc qua `getSuppressed()`.

Điều này giúp ta không mất nguyên nhân gốc khiến thao tác thất bại.

### 5.2. Nếu phần thân thành công nhưng close thất bại

```java
try (DemoResource resource = new DemoResource()) {
    System.out.println("Body completed");
} catch (IOException exception) {
    System.out.println("Caught: " + exception.getMessage());
}
```

Kết quả:

```text
Body completed
Caught: close failed
```

Khi phần thân không ném exception, lỗi đầu tiên xảy ra trong quá trình đóng được truyền ra như exception chính. Nếu có nhiều resource và nhiều lần đóng thất bại, các lỗi đóng tiếp theo được ghi nhận dưới dạng suppressed exception của lỗi đóng chính.

### 5.3. Đọc suppressed exceptions khi chẩn đoán

```java
try (DemoResource resource = new DemoResource()) {
    doWork();
} catch (IOException exception) {
    logger.error("Operation failed", exception);

    for (Throwable suppressed : exception.getSuppressed()) {
        logger.error("Resource close also failed", suppressed);
    }
}
```

Nhiều logger hiện đại có thể hiển thị suppressed exceptions trong stack trace của exception chính. Tuy vậy, `getSuppressed()` vẫn hữu ích khi cần xử lý hoặc báo cáo chúng riêng.

Không nhầm suppressed exception với cause:

- `getCause()` trả về nguyên nhân được liên kết bằng `initCause()` hoặc constructor tương ứng.
- `getSuppressed()` trả về những lỗi phụ phát sinh trong quá trình đóng tài nguyên sau khi lỗi chính đã xảy ra.

### 5.4. Nhiều tài nguyên cùng lỗi khi đóng

```java
class NamedResource implements AutoCloseable {
    private final String name;

    NamedResource(String name) {
        this.name = name;
    }

    @Override
    public void close() throws IOException {
        System.out.println("Closing " + name);
        throw new IOException("close " + name);
    }
}

public class MultipleCloseFailures {
    public static void main(String[] args) {
        try (
            NamedResource first = new NamedResource("first");
            NamedResource second = new NamedResource("second")
        ) {
            throw new IOException("body");
        } catch (IOException exception) {
            System.out.println("Primary: " + exception.getMessage());

            for (Throwable suppressed : exception.getSuppressed()) {
                System.out.println("Suppressed: " + suppressed.getMessage());
            }
        }
    }
}
```

Kết quả:

```text
Closing second
Closing first
Primary: body
Suppressed: close second
Suppressed: close first
```

Tài nguyên được đóng theo thứ tự ngược. Vì phần thân đã ném exception, lỗi đóng `second` và `first` đều được gắn vào exception `body` theo thứ tự chúng phát sinh.

## 6. Dùng biến tài nguyên đã khai báo trước (Java 9+)

Từ Java 9, resource specification có thể tham chiếu tới một biến tài nguyên đã được khai báo trước, miễn là biến đó là `final` hoặc *effectively final*.

Ví dụ:

```java
BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8);

try (reader) {
    System.out.println(reader.readLine());
}
```

Cú pháp này hữu ích khi:

- Tài nguyên được tạo ở một nhánh hoặc tầng xử lý trước đó.
- Muốn giữ biến trong phạm vi bên ngoài khối `try`.
- Một API nhận tài nguyên đã mở và cần quản lý việc đóng trong phạm vi cụ thể.

### 6.1. Biến phải final hoặc effectively final

Ví dụ hợp lệ:

```java
BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8);

try (reader) {
    process(reader);
}
```

Sau khi gán giá trị ban đầu, `reader` không được gán lại. Nó là effectively final.

Ví dụ không hợp lệ:

```java
BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8);

reader = Files.newBufferedReader(otherPath, StandardCharsets.UTF_8);

// Không hợp lệ: reader đã bị gán lại, không còn effectively final.
try (reader) {
    process(reader);
}
```

Nếu cần tạo một tài nguyên khác, khai báo biến mới hoặc dùng cú pháp khai báo trực tiếp bên trong resource specification.

### 6.2. Phạm vi biến khác nhau

Khai báo tài nguyên ngay trong `try`:

```java
try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    process(reader);
}

// reader không còn trong phạm vi ở đây.
```

Dùng biến khai báo trước:

```java
BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8);

try (reader) {
    process(reader);
}

// reader vẫn ở trong phạm vi lexical,
// nhưng tài nguyên đã đóng và không được dùng tiếp.
```

Biến còn nằm trong phạm vi ngôn ngữ không có nghĩa tài nguyên vẫn mở. Sau khi khối try-with-resources kết thúc, không tiếp tục đọc hoặc ghi qua nó.

### 6.3. Dùng nhiều biến đã khai báo trước

```java
BufferedReader reader =
        Files.newBufferedReader(input, StandardCharsets.UTF_8);
BufferedWriter writer =
        Files.newBufferedWriter(output, StandardCharsets.UTF_8);

try (reader; writer) {
    copy(reader, writer);
}
```

Các biến phải final/effectively final. Chúng vẫn đóng theo thứ tự ngược với thứ tự được liệt kê trong resource specification: `writer` trước, `reader` sau.

Cú pháp này có từ Java 9 và hoạt động bình thường trên Java 17.

## 7. Đọc và ghi tệp văn bản với UTF-8

Khi làm việc với văn bản, nên chỉ định charset rõ ràng để dữ liệu không phụ thuộc cấu hình mặc định của máy chạy.

### 7.1. Đọc file bằng BufferedReader

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class Utf8Reader {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("input.txt");

        try (BufferedReader reader =
                     Files.newBufferedReader(path, StandardCharsets.UTF_8)) {

            String line;
            while ((line = reader.readLine()) != null) {
                System.out.println(line);
            }
        }
    }
}
```

`Files.newBufferedReader(path, UTF_8)` tạo reader có buffer và dùng UTF-8. Nếu file không tồn tại, không đọc được hoặc có lỗi I/O, phương thức có thể ném `IOException`; nếu reader đã được tạo thành công, try-with-resources vẫn đóng nó khi xử lý lỗi.

### 7.2. Ghi file bằng BufferedWriter

```java
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class Utf8Writer {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("output.txt");

        try (BufferedWriter writer =
                     Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {

            writer.write("Xin chào Java 17");
            writer.newLine();
            writer.write("Try-with-resources");
        }
    }
}
```

Khi khối try kết thúc, `writer.close()` được gọi. Đóng writer cũng hoàn tất việc flush buffer theo hợp đồng của writer; không cần gọi `flush()` chỉ để bảo đảm dữ liệu trong buffer được ghi trước khi đóng.

Mặc định, `Files.newBufferedWriter(path, charset)` mở file để ghi, tạo file nếu cần và truncate file hiện có. Nếu cần append, hãy truyền các `StandardOpenOption` phù hợp.

### 7.3. Sao chép nội dung văn bản

```java
static void copyText(Path source, Path target) throws IOException {
    try (
        BufferedReader reader =
                Files.newBufferedReader(source, StandardCharsets.UTF_8);
        BufferedWriter writer =
                Files.newBufferedWriter(target, StandardCharsets.UTF_8)
    ) {
        String line;

        while ((line = reader.readLine()) != null) {
            writer.write(line);
            writer.newLine();
        }
    }
}
```

Cả reader và writer đều được đóng tự động. Writer đóng trước reader vì writer được khai báo sau.

**Lưu ý về nội dung:** `readLine()` loại bỏ dấu kết thúc dòng; `newLine()` ghi dấu kết thúc dòng phù hợp hệ điều hành. Vì vậy ví dụ này sao chép nội dung văn bản theo từng dòng nhưng có thể chuẩn hóa line ending. Nếu cần sao chép chính xác từng byte, dùng byte stream hoặc `Files.copy()` thay vì chuyển qua `readLine()`.

## 8. Dùng try-with-resources với byte stream

Khi làm việc với ảnh, PDF, file nén hoặc dữ liệu nhị phân, dùng `InputStream` và `OutputStream`.

```java
import java.io.InputStream;
import java.io.OutputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

static void copyBytes(Path source, Path target) throws IOException {
    try (
        InputStream input = Files.newInputStream(source);
        OutputStream output = Files.newOutputStream(target)
    ) {
        byte[] buffer = new byte[8192];
        int count;

        while ((count = input.read(buffer)) != -1) {
            output.write(buffer, 0, count);
        }
    }
}
```

`try-with-resources` đảm bảo cả hai stream được đóng kể cả khi `read()` hoặc `write()` ném `IOException`.

### 8.1. Wrapper stream và quyền sở hữu

Một wrapper như `BufferedInputStream` thường được tạo từ một stream khác:

```java
try (InputStream input = Files.newInputStream(path);
     BufferedInputStream buffered = new BufferedInputStream(input)) {
    // Đọc từ buffered.
}
```

Khi đóng `buffered`, nó thường đóng stream bên dưới. Sau đó try-with-resources tiếp tục gọi `input.close()` vì `input` cũng được khai báo là resource. Nhiều implementation stream chuẩn cho phép đóng lặp lại an toàn, nhưng không nên mặc định mọi `AutoCloseable` tự tạo đều idempotent.

Trong trường hợp wrapper sở hữu stream bên dưới, có thể chỉ khai báo wrapper là resource:

```java
try (BufferedInputStream input =
             new BufferedInputStream(Files.newInputStream(path))) {
    // Dùng input.
}
```

Khi đóng wrapper, nó chịu trách nhiệm đóng stream bên dưới. Hãy chọn một mô hình sở hữu rõ ràng để tránh nhiều tầng cùng tưởng rằng mình có quyền đóng cùng một tài nguyên.

## 9. Dùng try-with-resources với JDBC

Các interface JDBC hiện đại như `Connection`, `Statement`, `PreparedStatement` và `ResultSet` đều hỗ trợ `AutoCloseable`.

Ví dụ:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

static void listUsers(DataSource dataSource) throws SQLException {
    String sql = "SELECT id, username FROM users";

    try (
        Connection connection = dataSource.getConnection();
        PreparedStatement statement = connection.prepareStatement(sql);
        ResultSet resultSet = statement.executeQuery()
    ) {
        while (resultSet.next()) {
            long id = resultSet.getLong("id");
            String username = resultSet.getString("username");

            System.out.println(id + ": " + username);
        }
    }
}
```

Thứ tự đóng:

1. `ResultSet`.
2. `PreparedStatement`.
3. `Connection`.

Thứ tự này giúp đóng đối tượng phụ thuộc trước đối tượng mà nó được tạo từ đó.

### 9.1. Đóng Connection không nhất thiết đóng vật lý kết nối

Trong ứng dụng dùng connection pool, gọi `Connection.close()` thường trả connection về pool để tái sử dụng, thay vì đóng socket/database session vật lý ngay lập tức. Tuy nhiên, ứng dụng vẫn phải gọi `close()` để pool biết connection đã được trả lại.

Try-with-resources phù hợp với cả connection trực tiếp lẫn connection được quản lý bởi pool, vì nó gọi đúng phương thức `close()` theo hợp đồng JDBC.

### 9.2. Dùng PreparedStatement và tham số hóa

Try-with-resources quản lý vòng đời tài nguyên, không tự bảo vệ câu SQL khỏi injection. Hãy dùng placeholder và bind tham số:

```java
String sql = "SELECT id, username FROM users WHERE status = ?";

try (
    Connection connection = dataSource.getConnection();
    PreparedStatement statement = connection.prepareStatement(sql)
) {
    statement.setString(1, "ACTIVE");

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            System.out.println(resultSet.getString("username"));
        }
    }
}
```

`ResultSet` được khai báo trong khối try lồng nhau và đóng trước khi khối ngoài đóng `PreparedStatement` rồi `Connection`.

## 10. Try-with-resources và return, break, exception

Một điểm mạnh của try-with-resources là việc đóng tài nguyên không phụ thuộc vào đường thoát khỏi khối.

### 10.1. Có return vẫn đóng tài nguyên

```java
static String firstLine(Path path) throws IOException {
    try (BufferedReader reader =
                 Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
        return reader.readLine();
    }
}
```

Java lấy giá trị chuẩn bị trả về, đóng reader, sau đó hoàn tất `return`. Nếu `close()` ném exception trong lúc phương thức đang trả về bình thường, exception đóng có thể làm thao tác return không hoàn tất như dự định.

### 10.2. Exception vẫn đóng tài nguyên

```java
try (var input = Files.newInputStream(path)) {
    throw new IllegalStateException("Processing failed");
}
```

Ngay cả khi exception được ném trong phần thân, Java vẫn gọi `input.close()`. Nếu `close()` cũng lỗi, lỗi đóng được gắn vào exception chính như suppressed exception.

### 10.3. break và continue

```java
for (Path path : files) {
    try (var reader =
                 Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
        if (shouldSkip(path)) {
            continue;
        }

        process(reader);

        if (isComplete(path)) {
            break;
        }
    }
}
```

Mỗi lần thoát khỏi khối try-with-resources, reader của vòng lặp hiện tại được đóng trước khi vòng lặp tiếp tục hoặc kết thúc.

## 11. So sánh với đóng thủ công trong finally

Trước khi có try-with-resources, code thường dùng `try/finally`:

```java
InputStream input = null;

try {
    input = Files.newInputStream(path);
    process(input);
} finally {
    if (input != null) {
        input.close();
    }
}
```

Cách này có thể đóng tài nguyên, nhưng có các điểm phải tự xử lý:

- Biến phải có thể nhận `null`.
- Cần bảo đảm `close()` được gọi khi có exception.
- Nếu phần thân và `close()` cùng ném exception, exception từ `finally` có thể che mất exception ban đầu.
- Với nhiều tài nguyên, code lồng nhau hoặc nhiều nhánh đóng sẽ dài và dễ sai.

Try-with-resources thể hiện trực tiếp ý định sở hữu tài nguyên và có quy tắc suppressed exception chuẩn của ngôn ngữ.

Không cần tự viết `close()` trong `finally` cho tài nguyên đã khai báo trong resource specification; nếu gọi thủ công rồi để try-with-resources gọi lần nữa, bạn có thể tạo thao tác đóng lặp ngoài ý muốn.

## 12. Thiết kế AutoCloseable cho tài nguyên tự tạo

Khi một class sở hữu file, socket hoặc một resource khác, có thể triển khai `AutoCloseable` để caller quản lý bằng try-with-resources.

Ví dụ:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

final class DirectoryScanner implements AutoCloseable {

    private final Stream<Path> paths;

    DirectoryScanner(Path directory) throws IOException {
        this.paths = Files.list(directory);
    }

    Stream<Path> paths() {
        return paths;
    }

    @Override
    public void close() {
        paths.close();
    }
}
```

Sử dụng:

```java
try (DirectoryScanner scanner =
             new DirectoryScanner(Path.of("logs"))) {
    scanner.paths()
            .filter(path -> path.toString().endsWith(".log"))
            .forEach(System.out::println);
}
```

`Files.list()` trả về một stream gắn với tài nguyên hệ thống, nên phải đóng stream sau khi dùng. `DirectoryScanner` sở hữu stream đó và đóng nó trong `close()`.

### 12.1. Xác định rõ ai sở hữu tài nguyên

Một nguyên tắc thiết kế quan trọng:

- Nếu method tạo và trả về một resource mới, caller thường chịu trách nhiệm đóng nó.
- Nếu một object nhận resource do caller cung cấp nhưng không nhận quyền sở hữu, nó không nên tự ý đóng resource đó.
- Nếu object tạo và sở hữu resource bên trong, `close()` của object chịu trách nhiệm giải phóng resource.
- Khi chuyển quyền sở hữu, cần thể hiện rõ trong API hoặc tài liệu.

Ví dụ một method nhận `InputStream`:

```java
static void parse(InputStream input) throws IOException {
    // Nếu hợp đồng nói caller sở hữu input,
    // method này không đóng input.
    parseData(input);
}
```

Caller quyết định vòng đời:

```java
try (InputStream input = Files.newInputStream(path)) {
    parse(input);
}
```

Nếu `parse()` tự đóng input trong khi caller cũng quản lý nó, code có thể trở nên khó dự đoán. Cần thống nhất quyền sở hữu theo hợp đồng API.

### 12.2. Thiết kế close() có thể gọi an toàn

Với tài nguyên tự tạo, nên xác định trạng thái đóng và tránh giải phóng cùng một native resource nhiều lần nếu API bên dưới không cho phép.

```java
final class ManagedResource implements AutoCloseable {

    private boolean closed;

    public void use() {
        if (closed) {
            throw new IllegalStateException("Resource is closed");
        }

        System.out.println("Using resource");
    }

    @Override
    public void close() {
        if (!closed) {
            closed = true;
            System.out.println("Resource released");
        }
    }
}
```

Đây là minh họa cho resource đơn giản, không có đồng bộ đa luồng. Nếu đối tượng được chia sẻ giữa nhiều thread, cần thiết kế đồng bộ thích hợp cho trạng thái và thao tác đóng.

`AutoCloseable` không tự làm class thread-safe. Cũng không nên giả định mọi implementation `close()` đều idempotent; hãy đọc hợp đồng của loại tài nguyên đang sử dụng.

## 13. Tài nguyên lồng nhau và phạm vi quản lý

Có thể dùng try-with-resources lồng nhau khi vòng đời của một resource phụ thuộc vào resource khác hoặc cần phạm vi đóng khác nhau.

```java
try (var connection = dataSource.getConnection()) {
    try (var statement =
                 connection.prepareStatement("SELECT id FROM users")) {

        try (var resultSet = statement.executeQuery()) {
            while (resultSet.next()) {
                System.out.println(resultSet.getLong(1));
            }
        }
    }
}
```

Cách viết này rõ thứ tự nhưng dài. Có thể gom các tài nguyên có cùng phạm vi vào một try:

```java
try (
    var connection = dataSource.getConnection();
    var statement = connection.prepareStatement("SELECT id FROM users");
    var resultSet = statement.executeQuery()
) {
    while (resultSet.next()) {
        System.out.println(resultSet.getLong(1));
    }
}
```

Chọn cấu trúc theo vòng đời thực tế:

- Dùng một try khi các tài nguyên cùng được tạo và cần đóng trong cùng phạm vi.
- Dùng try lồng nhau khi resource bên trong chỉ tồn tại trong một đoạn con.
- Tránh lồng nhiều tầng chỉ vì thói quen nếu danh sách resource có thể thể hiện rõ ràng hơn.

## 14. Những lỗi thường gặp

### Lỗi 1. Quên đóng resource khi có exception

Dùng try-with-resources để Java tự đóng tài nguyên trên mọi đường thoát thông thường.

### Lỗi 2. Dùng object không triển khai AutoCloseable

Chỉ các kiểu tương thích `AutoCloseable` mới xuất hiện trong resource specification. Nếu class tự tạo quản lý tài nguyên, cân nhắc triển khai interface này.

### Lỗi 3. Tiếp tục dùng resource sau khối try

Sau khi khối try kết thúc, tài nguyên đã đóng. Biến có thể còn trong phạm vi nhưng không thể được xem như resource đang mở.

### Lỗi 4. Đóng sai thứ tự

Java đóng theo thứ tự ngược với thứ tự khởi tạo. Khi tự quản lý resource phụ thuộc nhau, hãy khai báo theo thứ tự tạo và dựa vào LIFO để đóng wrapper trước resource nền.

### Lỗi 5. Để lỗi close che lỗi xử lý

Try-with-resources giữ exception từ phần thân làm exception chính và gắn lỗi đóng vào `getSuppressed()`.

### Lỗi 6. Nghĩ catch chạy trước khi đóng

Tài nguyên được đóng trước khi điều khiển đi vào `catch` hoặc `finally` gắn với try đó.

### Lỗi 7. Dùng biến không effectively final trong resource specification

Với cú pháp `try (reader)` của Java 9+, biến phải final hoặc effectively final. Nếu đã gán lại biến, hãy tạo biến resource mới hoặc khai báo resource trực tiếp trong `try`.

### Lỗi 8. Khai báo resource đã được wrapper sở hữu rồi lại đóng tùy tiện

Wrapper thường đóng resource bên dưới. Hãy xác định rõ ai sở hữu và ai chịu trách nhiệm đóng để tránh nhiều lớp cùng đóng một resource không idempotent.

### Lỗi 9. Cho rằng try-with-resources xử lý encoding

Try-with-resources quản lý vòng đời; nó không tự chọn charset. Với văn bản, chỉ định charset rõ ràng, ví dụ `StandardCharsets.UTF_8`.

### Lỗi 10. Nhầm close với commit transaction

Đóng `Connection` không thay thế quy tắc commit/rollback của transaction. Nếu dùng JDBC transaction thủ công, hãy quản lý commit/rollback rõ ràng trước khi connection được đóng hoặc trả về pool.

### Lỗi 11. Nuốt exception trong close()

Không nên bắt exception trong `close()` rồi bỏ qua một cách im lặng nếu lỗi đó có ý nghĩa với việc giải phóng tài nguyên. Hãy tuân theo hợp đồng của resource và để try-with-resources giữ thông tin lỗi khi cần.

## 15. Quy trình chọn và sử dụng try-with-resources

Khi một API trả về đối tượng có thể đóng, hãy thực hiện theo các bước:

1. **Xác định loại resource:** kiểm tra class có triển khai `AutoCloseable` hoặc `Closeable` không.
2. **Xác định quyền sở hữu:** ai tạo resource và ai có trách nhiệm đóng?
3. **Chọn phạm vi:** xác định đoạn code ngắn nhất cần sử dụng resource.
4. **Khai báo trong try:** dùng `try (Resource resource = ...)`; với biến final/effectively final có thể dùng cú pháp `try (resource)` từ Java 9.
5. **Khai báo theo thứ tự phụ thuộc:** resource được tạo sau sẽ đóng trước.
6. **Xử lý exception:** bắt các exception cần xử lý ở bên ngoài khối try; kiểm tra suppressed exceptions nếu lỗi đóng cũng quan trọng.
7. **Chỉ định charset cho text:** dùng UTF-8 hoặc charset được giao thức quy định.
8. **Kiểm tra hợp đồng close():** không giả định mọi resource đều thread-safe hoặc đóng lặp lại an toàn.

## 16. Ví dụ hoàn chỉnh: đọc cấu hình và bảo đảm đóng file

Lưu file thành `TryWithResourcesDemo.java`:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class TryWithResourcesDemo {

    static int countNonEmptyLines(Path path) throws IOException {
        int count = 0;

        try (BufferedReader reader =
                     Files.newBufferedReader(path, StandardCharsets.UTF_8)) {

            String line;
            while ((line = reader.readLine()) != null) {
                if (!line.isBlank()) {
                    count++;
                }
            }
        }

        return count;
    }

    public static void main(String[] args) {
        Path path = Path.of("config.txt");

        try {
            int count = countNonEmptyLines(path);
            System.out.println("Non-empty lines: " + count);
        } catch (IOException exception) {
            System.err.println("Cannot read configuration: "
                    + exception.getMessage());
        }
    }
}
```

Biên dịch và chạy bằng JDK 17:

```bash
javac --release 17 TryWithResourcesDemo.java
java TryWithResourcesDemo
```

Kết quả phụ thuộc nội dung file `config.txt`. Điểm quan trọng là reader được đóng trước khi `countNonEmptyLines()` trả về hoặc truyền exception ra ngoài.

## 17. Bài tập tự luyện

### Bài 1. Xác định thời điểm đóng

```java
try (var input = Files.newInputStream(path)) {
    System.out.println(input.read());
} catch (IOException exception) {
    System.out.println("error");
}
```

**Câu hỏi:** `input.close()` được gọi trước hay sau khi vào `catch`?

**Đáp án:** Trước. Tài nguyên được đóng khi rời phần thân try, rồi mới xử lý `catch`.

### Bài 2. Xác định thứ tự đóng

```java
try (
    Resource a = new Resource("A");
    Resource b = new Resource("B");
    Resource c = new Resource("C")
) {
    work();
}
```

**Câu hỏi:** Thứ tự gọi `close()` là gì?

**Đáp án:** C, B, A. Tài nguyên đóng theo thứ tự ngược với khai báo.

### Bài 3. Exception nào là exception chính?

Phần thân try ném `IOException("read")`; `close()` ném `IOException("close")`.

**Đáp án:** `"read"` là exception chính; `"close"` xuất hiện trong `getSuppressed()`.

### Bài 4. Nếu thân try thành công nhưng close lỗi?

**Đáp án:** Exception từ thao tác đóng được truyền ra như exception chính và có thể được xử lý ở `catch`.

### Bài 5. Biến resource có được gán lại không?

```java
BufferedReader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8);
reader = Files.newBufferedReader(other, StandardCharsets.UTF_8);

try (reader) {
    process(reader);
}
```

**Đáp án:** Không hợp lệ. `reader` đã bị gán lại nên không còn effectively final. Cú pháp dùng biến khai báo trước yêu cầu biến final hoặc effectively final.

### Bài 6. Có cần gọi close thủ công trong khối try không?

```java
try (var input = Files.newInputStream(path)) {
    process(input);
    input.close();
}
```

**Đáp án:** Không cần. Java sẽ gọi `close()` khi khối kết thúc; gọi thủ công có thể dẫn tới đóng hai lần. Chỉ gọi sớm nếu hợp đồng API và thiết kế vòng đời yêu cầu rõ ràng, và vẫn hiểu rằng try-with-resources sẽ gọi close ở cuối.

### Bài 7. Đọc text có cần chỉ định charset?

**Đáp án:** Có. Dùng overload nhận `StandardCharsets.UTF_8` hoặc charset giao thức quy định để dữ liệu nhất quán giữa môi trường.

### Bài 8. `Connection.close()` có luôn đóng socket vật lý?

**Đáp án:** Không nhất thiết. Với connection pool, `close()` thường trả connection về pool. Ứng dụng vẫn phải gọi close để trả tài nguyên cho pool.

## 18. Tài liệu tham khảo chính thức

- [Java Language Specification 17 — `14.20.3 try-with-resources`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): quy tắc khởi tạo, đóng tài nguyên và xử lý suppressed exceptions.
- [JDK 17 API — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): hợp đồng của phương thức `close()` và cách dùng trong try-with-resources.
- [JDK 17 API — Closeable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Closeable.html): interface đóng tài nguyên I/O và quan hệ với `AutoCloseable`.
- [JDK 17 API — Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `getSuppressed()` và cơ chế suppressed exception.
- [OpenJDK JEP 213 — Milling Project Coin](https://openjdk.org/jeps/213): thay đổi Java 9 cho phép dùng biến final/effectively final đã khai báo trước trong try-with-resources.
- [JDK 17 API — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): API tạo reader, writer và stream gắn với file.
- [JDK 17 API — Connection](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html): vòng đời và phương thức đóng kết nối JDBC.

**Ghi nhớ:** Khai báo mọi tài nguyên có thể đóng trong `try (...)` để Java tự gọi `close()` khi rời khối. Tài nguyên được khởi tạo theo thứ tự khai báo và đóng theo thứ tự ngược. Nếu phần thân và `close()` cùng lỗi, lỗi phần thân được giữ làm exception chính, còn lỗi đóng nằm trong `getSuppressed()`. Dùng charset tường minh cho tệp văn bản và xác định rõ quyền sở hữu tài nguyên trong API của ứng dụng.
