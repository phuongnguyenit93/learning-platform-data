# Áp dụng try-with-resources cho tệp, kênh, cơ sở dữ liệu và tài nguyên tự định nghĩa

> **Chủ đề Java 7 — try-with-resources.** Cú pháp `try (Resource r = ...) { ... }` quản lý tự động vòng đời đối tượng triển khai `AutoCloseable`. Trong Java hiện đại (Java 17+), đây vẫn là lựa chọn chuẩn cho luồng đọc/ghi tệp, channel NIO, tài nguyên JDBC và nhiều đối tượng do ứng dụng tự xây dựng. Điều cốt lõi là xác định **ai sở hữu tài nguyên, lúc nào cần giải phóng và lỗi khi đóng được xử lý ra sao**. Bài dùng API còn phù hợp hiện nay, đồng thời đánh dấu các tiện ích được bổ sung sau Java 7.

## 1. Cơ chế chung: không phải tài nguyên nào cũng chỉ là file

Một tài nguyên có vòng đời xác định thường thực hiện chu trình **acquire → use → release**: lấy quyền truy cập, sử dụng, sau đó trả lại file descriptor, socket, connection, khóa hoặc trạng thái bên ngoài.

```java
try (SomeResource resource = createResource()) {
    use(resource);
}
```

Đây là **mẫu cú pháp**, với `SomeResource` và helper do ứng dụng định nghĩa. Để đứng trong header, kiểu tài nguyên phải triển khai `java.lang.AutoCloseable` (hoặc một subtype như `java.io.Closeable`).

Khi khối `try` kết thúc bình thường, gặp `return` hoặc phát sinh exception, Java cố gọi `resource.close()`. Nếu khai báo nhiều resource trong header, chúng được khởi tạo **từ trái sang phải**, rồi được đóng **từ phải sang trái**, kể cả khi một bước sau đó thất bại. `catch`/`finally` gắn với cùng câu lệnh chạy sau bước đóng tự động.

### 1.1. Những loại tài nguyên có thể quản lý

| Nhóm | API tiêu biểu | Tại sao cần đóng? |
| --- | --- | --- |
| Tệp dạng byte | `InputStream`, `OutputStream`, `FileInputStream`, `FileOutputStream` | Giải phóng file handle và tài nguyên I/O |
| Tệp dạng ký tự | `Reader`, `Writer`, `BufferedReader`, `BufferedWriter` | Kết thúc đọc/ghi, flush khi API quy định, giải phóng handle |
| Duyệt tệp/thư mục theo luồng | `Stream<String>` từ `Files.lines`, `Stream<Path>` từ `Files.walk`/`Files.list` | Đóng tài nguyên I/O mà stream đang nắm giữ |
| Kênh NIO | `FileChannel`, `SeekableByteChannel`, `SocketChannel` | Giải phóng kênh, file/socket liên quan |
| JDBC | `Connection`, `Statement`, `PreparedStatement`, `ResultSet` | Trả lại connection, giải phóng statement/cursor và tài nguyên DB |
| Tự định nghĩa | `AutoCloseable`/`Closeable` do ứng dụng triển khai | Kết thúc session, lease, scope hoặc thao tác sở hữu tài nguyên |

**Không phải đối tượng nào cũng cần đưa vào `try-with-resources`.** Một `String`, `List` hoặc luồng tính toán thuần bộ nhớ không tự nhiên đòi hỏi `close()`. Chỉ dùng cơ chế này khi đối tượng có hợp đồng đóng rõ ràng, được sở hữu bởi phạm vi hiện tại và không cần sống lâu hơn khối `try`.

### 1.2. Từ khóa `close()` được định nghĩa ở đâu?

`AutoCloseable` có method:

```java
public interface AutoCloseable {
    void close() throws Exception;
}
```

Đây là chữ ký rút gọn để giải thích hợp đồng, không phải file cần biên dịch. Một class có thể triển khai `close()` không ném checked exception hoặc khai báo subtype hẹp hơn `Exception`.

`Closeable` (trong `java.io`) kế thừa `AutoCloseable` và khai báo `close() throws IOException`. Nhiều tài nguyên file/channel dùng giao diện này. Do đó compiler không mặc định mọi `close()` đều ném `IOException`: phải xét **kiểu tĩnh thật sự** của tài nguyên và chữ ký `close()`.

## 2. Áp dụng cho tệp văn bản: `BufferedReader` và `BufferedWriter`

Trong ứng dụng sử dụng `Path` và `Files`, cách đọc/ghi nhiều dòng văn bản là tạo reader/writer trong header rồi làm việc trong thân `try`. Java tự đóng chúng khi ra khỏi scope, kể cả khi đọc/ghi thất bại.

Lưu thành `FileTextResourcesDemo.java`:

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class FileTextResourcesDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("text-resource-", ".txt");

        try {
            try (BufferedWriter writer =
                     Files.newBufferedWriter(file, StandardCharsets.UTF_8)) {
                writer.write("alpha");
                writer.newLine();
                writer.write("beta");
                writer.newLine();
            }

            try (BufferedReader reader =
                     Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
                System.out.println("first=" + reader.readLine());
                System.out.println("second=" + reader.readLine());
                System.out.println("third=" + reader.readLine());
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 --release 17 FileTextResourcesDemo.java
java FileTextResourcesDemo
```

Khi hệ thống cho phép tạo tệp tạm, stdout:

```text
first=alpha
second=beta
third=null
```

**Giải thích:**

- `Files.newBufferedWriter` trả về `BufferedWriter`; `Files.newBufferedReader` trả về `BufferedReader`. Cả hai đều có hợp đồng `close()`.
- Khối ghi kết thúc và writer được đóng **trước khi** khối đọc bắt đầu. Đây là trình tự đúng khi muốn đọc nội dung vừa ghi.
- `writer.newLine()` dùng dấu xuống dòng theo nền tảng, nhưng `reader.readLine()` hiểu các dấu ngắt dòng được hỗ trợ nên kết quả nội dung vẫn ổn định.
- Khi không còn dòng nào, `readLine()` trả `null`; dấu `null` ở stdout xuất hiện do phép ghép chuỗi Java.
- `Files.createTempFile` và `Files.newBufferedReader/newBufferedWriter` thuộc NIO.2 từ Java 7. `StandardCharsets.UTF_8` cũng là API được dùng phổ biến trên Java hiện đại.
- `Files.deleteIfExists` trong `finally` dọn file tạm do chương trình **sở hữu**; đây là việc quản lý một tài nguyên trên filesystem, khác với đóng stream. Với file người dùng, **không tự xóa file** khi reader/writer đóng.
- `main` khai báo `throws IOException` để ví dụ không che lỗi I/O. Trong ứng dụng thật, xử lý lỗi theo chính sách API (trả trạng thái, retry hợp lệ hoặc propagate).

### 2.1. Có nên dùng try-with-resources khi gọi `Files.readString`?

Không phải lúc nào cũng phải tạo reader bằng tay. Từ Java 11:

```java
String content = Files.readString(path, StandardCharsets.UTF_8);
Files.writeString(path, "Hello", StandardCharsets.UTF_8);
```

Đây là **snippet** với `Path path` đã có và import tương ứng. Các phương thức tiện ích này tự quản lý tài nguyên I/O nội bộ cần thiết; caller không nhận về một đối tượng `Closeable` để tự đóng. Nếu chỉ đọc/ghi toàn bộ tệp nhỏ, API tiện ích thường rõ ràng hơn. Với tệp lớn, luồng dữ liệu hoặc yêu cầu xử lý từng dòng, reader/writer trong `try-with-resources` giúp giới hạn bộ nhớ và quản lý scope tốt hơn.

**Lưu ý:** `Files.writeString` thường ghi/truncate theo các lựa chọn mặc định phù hợp. Trước khi ghi dữ liệu quan trọng, kiểm tra `OpenOption`, quyền truy cập và chiến lược thay thế file an toàn; `try-with-resources` chỉ giải quyết vòng đời resource, không tự ngăn ghi đè dữ liệu.

## 3. Áp dụng cho stream byte: input và output trong cùng một try

Một thao tác truyền nội dung từ nguồn sang đích cần `InputStream` và `OutputStream`. Đặt cả hai vào header khiến chúng được đóng theo thứ tự **output trước, input sau**.

Lưu thành `StreamCopyResourcesDemo.java`:

```java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class StreamCopyResourcesDemo {
    public static void main(String[] args) throws IOException {
        Path source = Files.createTempFile("copy-source-", ".txt");
        Path target = Files.createTempFile("copy-target-", ".txt");

        try {
            Files.writeString(source, "Java17", StandardCharsets.UTF_8);

            long copied;
            try (
                InputStream input = Files.newInputStream(source);
                OutputStream output = Files.newOutputStream(target)
            ) {
                copied = input.transferTo(output);
            }

            System.out.println("bytes=" + copied);
            System.out.println(
                "text=" + Files.readString(target, StandardCharsets.UTF_8)
            );
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(source);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 StreamCopyResourcesDemo.java
java StreamCopyResourcesDemo
```

Stdout trong môi trường có quyền thao tác file tạm:

```text
bytes=6
text=Java17
```

**Vì sao đúng?**

- `InputStream` và `OutputStream` là hai tài nguyên implement `Closeable`.
- Nếu mở input thành công nhưng khởi tạo output thất bại, input sẽ được đóng tự động. Java chỉ quản lý các resource **đã được khởi tạo thành công** trong header.
- Khi thân kết thúc, output đóng trước input; dù thân có `return` hoặc exception, logic đóng tự động vẫn được áp dụng.
- `InputStream.transferTo` được bổ sung ở **Java 9**, còn `Files.readString`/`writeString` từ **Java 11**; minh họa chạy trên Java 17+. `Files.newInputStream` và `Files.newOutputStream` vẫn là API NIO.2 hiện hành.
- Với thao tác copy file đơn thuần, cũng có `Files.copy(...)`. Ví dụ này cố tình lấy hai stream để làm rõ tài nguyên nào thuộc quyền sở hữu của khối try.
- Tệp đích có thể bị tạo hoặc ghi đè tùy các `OpenOption`; trong ứng dụng thực tế cần xác nhận không copy vào chính nguồn và không làm mất dữ liệu quan trọng.

### 3.1. Thứ tự đóng không phải thứ tự dữ liệu chạy

Dòng chương trình đọc `input` rồi ghi `output` tùy logic trong body; nhưng thứ tự đóng là do **vị trí resource trong header**, không phụ thuộc bạn gọi `read` trước hay `write`. Có thể để output đóng cuối nếu đổi thứ tự khai báo, nhưng phải cân nhắc dependency và khả năng khởi tạo thất bại. Thứ tự hợp lý là thứ tự bảo đảm vòng đời và ownership, không chỉ thứ tự làm việc.

### 3.2. Stream có cần flush thủ công không?

`BufferedWriter` và một số wrapper output thường flush trong quá trình `close()` theo hợp đồng. Tuy nhiên **không nên đồng nhất close với sự bảo đảm dữ liệu đã được lưu bền vững lên thiết bị vật lý**: việc flush ở tầng Java không tự có nghĩa dữ liệu đã được fsync hoặc commit transaction. Nếu ứng dụng đòi hỏi durability, hãy tra cứu API cụ thể như `FileChannel.force(...)` và chiến lược cập nhật file phù hợp.

## 4. Áp dụng cho stream từ `Files.lines`, `Files.walk`, `Files.list`

Một khác biệt quan trọng với stream collection thông thường: một số `Stream` được trả về từ `Files` nắm giữ **tài nguyên I/O mở** để duyệt dữ liệu một cách lazy.

Ví dụ Java 17+:

```java
try (java.util.stream.Stream<String> lines =
         Files.lines(path, StandardCharsets.UTF_8)) {
    long nonBlank = lines.filter(line -> !line.isBlank()).count();
    System.out.println("nonBlank=" + nonBlank);
}
```

Đây là **snippet trong method** với `Path path` và import `Files`/`StandardCharsets` thích hợp. `Files.lines` có từ Java 8; `String.isBlank` từ Java 11. Khi dùng stream này, hãy đóng bằng `try-with-resources` sau khi hoàn tất terminal operation như `count()`.

Tương tự:

```java
try (java.util.stream.Stream<Path> entries = Files.list(directory)) {
    entries.forEach(System.out::println);
}

try (java.util.stream.Stream<Path> paths = Files.walk(directory)) {
    long fileCount = paths.filter(Files::isRegularFile).count();
    System.out.println("fileCount=" + fileCount);
}
```

Đây là snippet với `Path directory` đã được định nghĩa, các import phù hợp và thư mục tồn tại. `Files.list`/`Files.walk` có từ Java 8, vẫn được dùng. Không giữ stream sống bên ngoài khối try rồi tiếp tục xử lý khi tài nguyên đã đóng.

**Phân biệt:** `list.stream()` trên `List` thuần bộ nhớ không sở hữu file descriptor; `Files.lines(path)` và `Files.walk(dir)` có thể giữ handle tới file/thư mục. Cả hai cùng là `Stream` nhưng **nghĩa vụ đóng phụ thuộc nguồn dữ liệu và tài liệu API**, không chỉ kiểu generic `Stream<T>`.

### 4.1. Không để API trả về stream đã đóng

Ví dụ thiết kế **không nên dùng**:

```java
static java.util.stream.Stream<String> wrong(Path path) throws IOException {
    try (var lines = Files.lines(path)) {
        return lines; // Stream đã đóng khi method trả về.
    }
}
```

Đây là đoạn code hợp lệ về mặt cú pháp trong ngữ cảnh import phù hợp, nhưng **sai vòng đời**: method trả về một `Stream` đã qua `close()`. Một consumer tiếp tục duyệt có thể gặp lỗi.

Nếu muốn giữ việc sở hữu tài nguyên trong method, trả về dữ liệu đã materialize:

```java
static java.util.List<String> readAll(Path path) throws IOException {
    try (var lines = Files.lines(path)) {
        return lines.toList();
    }
}
```

`Stream.toList()` được thêm ở Java 16, dùng được với Java 17+. Với file rất lớn, materialize toàn bộ danh sách không phù hợp; hãy thiết kế API nhận callback/consumer hoạt động **bên trong scope** hoặc công bố rõ caller phải đóng resource.

## 5. Áp dụng cho kênh NIO: `FileChannel` và `ByteBuffer`

`java.nio.channels.FileChannel` làm việc với file bằng `ByteBuffer`, hỗ trợ truy cập vị trí, thao tác đọc/ghi và một số khả năng kiểm soát I/O nâng cao. `FileChannel` là một `Channel`/`Closeable` và phù hợp với `try-with-resources`.

Lưu thành `FileChannelResourcesDemo.java`:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class FileChannelResourcesDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("channel-resource-", ".dat");

        try {
            try (FileChannel channel = FileChannel.open(
                    file,
                    StandardOpenOption.READ,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING
            )) {
                ByteBuffer source = StandardCharsets.UTF_8.encode("channel");
                while (source.hasRemaining()) {
                    channel.write(source);
                }

                channel.position(0);
                ByteBuffer target = ByteBuffer.allocate((int) channel.size());
                while (target.hasRemaining() && channel.read(target) != -1) {
                    // Đọc cho đến khi đủ buffer hoặc tới cuối file.
                }

                target.flip();
                System.out.println("bytes=" + target.remaining());
                System.out.println(
                    "text=" + StandardCharsets.UTF_8.decode(target)
                );
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 FileChannelResourcesDemo.java
java FileChannelResourcesDemo
```

Stdout trong môi trường file tạm thông thường:

```text
bytes=7
text=channel
```

**Phân tích:**

- `FileChannel.open(...)` trả về một đối tượng cần được đóng. Khi thoát `try`, `channel.close()` được gọi; không cần `finally { channel.close(); }` tự viết.
- `ByteBuffer` là vùng chứa byte trong bộ nhớ, **không implement `AutoCloseable`** theo API này, vì vậy không đưa `ByteBuffer` vào header.
- `StandardOpenOption.READ`/`WRITE`/`TRUNCATE_EXISTING` mô tả chế độ mở. Ở đây file tạm đã tồn tại, nên có thể truncate để ghi dữ liệu kiểm thử.
- `ByteBuffer` ban đầu chứa chuỗi ASCII dài 7 byte. Sau khi ghi, `channel.position(0)` chuyển về đầu file trước khi đọc.
- Vòng `while` khi ghi xử lý tình huống `FileChannel.write` chỉ ghi một phần buffer; vòng khi đọc cũng không giả định một lần `read` sẽ luôn lấy hết dữ liệu.
- Cả `FileChannel`, `ByteBuffer`, `StandardOpenOption` đều thuộc API còn được hỗ trợ và có ích trên JDK 17+.

### 5.1. Các channel khác

`SeekableByteChannel` từ `Files.newByteChannel(...)`, `SocketChannel` và một số channel/selector khác cũng có vòng đời cần đóng. Khi tạo channel thuộc sở hữu của một request/tác vụ, khai báo trong `try-with-resources` để tránh giữ file descriptor hoặc socket lâu hơn cần thiết.

Đừng suy ra mọi đối tượng NIO đều là AutoCloseable. Ví dụ `ByteBuffer` là container dữ liệu; `Path` là biểu diễn đường dẫn, không phải file handle đang mở. Chỉ quản lý bằng try-with-resources những object thực sự có hợp đồng `close()`.

### 5.2. Tính đúng đắn của thao tác kênh không chỉ là đóng

`try-with-resources` giúp giải phóng handle. Nhưng với file cần độ bền dữ liệu, đồng bộ nhiều luồng hoặc truy cập ngẫu nhiên, cần xét thêm `FileChannel.force(...)`, kiểm soát position/locking và chính sách ghi an toàn. Với mạng không đồng bộ, không đóng channel ở cuối scope **trước khi tác vụ bất đồng bộ hoàn tất**. Tài nguyên chỉ nên được đóng khi vòng đời công việc sử dụng nó thật sự kết thúc.

## 6. JDBC: quản lý `Connection`, `PreparedStatement`, `ResultSet`

Trong ứng dụng truy cập cơ sở dữ liệu theo JDBC, ba loại thường đi cùng nhau:

- **`Connection`:** kết nối logic giữa ứng dụng và database. Nếu lấy từ connection pool, `close()` thường trả kết nối về pool thay vì đóng kết nối vật lý, tùy pool.
- **`PreparedStatement`:** đối tượng thực thi câu SQL đã chuẩn bị và các tham số ràng buộc.
- **`ResultSet`:** cursor/tập kết quả từ truy vấn; có thể giữ tài nguyên phía driver/database và cần đóng.

Cả ba implement `AutoCloseable`. Java 7+ cho phép:

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
         connection.prepareStatement("SELECT name FROM customers WHERE id = ?")) {

    statement.setLong(1, customerId);

    try (ResultSet rows = statement.executeQuery()) {
        if (rows.next()) {
            String name = rows.getString("name");
            // Dùng name trong phạm vi ResultSet còn mở.
        }
    }
}
```

Đây là **snippet** với `DataSource dataSource` và `long customerId` do caller cung cấp, các import `java.sql.*`/`javax.sql.DataSource`. Query và schema `customers` là ví dụ minh họa, không giả định tồn tại trong mọi database.

**Thứ tự ở ví dụ:** mở `connection`, tạo `statement`, thực thi truy vấn để tạo `rows`; sau khi dùng xong, đóng `rows`, rồi `statement`, cuối cùng `connection`. Khi exception xuất hiện, Java cũng cố đóng các resource đã khởi tạo thành công.

### 6.1. Tại sao thường lồng `ResultSet` trong `try` của statement?

`executeQuery()` cần statement đã được cấu hình (ví dụ gọi `setLong`). Vì vậy mô hình:

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, id);
    try (ResultSet resultSet = statement.executeQuery()) {
        // Dùng resultSet.
    }
}
```

phù hợp tự nhiên với trình tự JDBC. Cũng có thể sắp xếp lại các scope theo API, nhưng phải giữ **statement/connection sống đủ lâu khi đang đọc ResultSet**. Một số driver tự đóng result set khi statement đóng; tuy thế không nên dựa vào hiệu ứng phụ đó thay cho ownership rõ ràng ở code ứng dụng.

### 6.2. Mẫu JDBC biên dịch được bằng JDK 17

Lưu thành `JdbcLookupPattern.java`:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import javax.sql.DataSource;

public final class JdbcLookupPattern {
    private JdbcLookupPattern() {
    }

    public static Optional<String> findName(
            DataSource dataSource, long customerId
    ) throws SQLException {
        String sql = "SELECT name FROM customers WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                 connection.prepareStatement(sql)) {

            statement.setLong(1, customerId);

            try (ResultSet rows = statement.executeQuery()) {
                if (rows.next()) {
                    return Optional.ofNullable(rows.getString(1));
                }
                return Optional.empty();
            }
        }
    }
}
```

Có thể **biên dịch phần Java API chuẩn** với:

```bash
javac -encoding UTF-8 --release 17 JdbcLookupPattern.java
```

Ví dụ **không có `main` và không có stdout mặc định**, vì đây là *mẫu tích hợp JDBC*, không phải chương trình độc lập kết nối thật. Muốn thực thi truy vấn phải cung cấp **driver JDBC**, cấu hình `DataSource`/connection pool, địa chỉ và quyền truy cập database, cùng bảng `customers` với các cột thích hợp. JDK có giao diện JDBC tiêu chuẩn nhưng **không nên giả định luôn có sẵn driver cho database cụ thể**.

**Điểm đáng học:**

- `PreparedStatement` sử dụng placeholder `?` và `setLong` để truyền giá trị, thay vì nối trực tiếp dữ liệu đầu vào vào SQL.
- `Optional<String>` được tạo bằng dữ liệu đã đọc trong khi `ResultSet` còn mở; caller **không nhận cursor sống** sau khi method trả về.
- Dù có `return` trong khối `try (ResultSet ...)`, Java đóng `rows` trước, rồi statement và connection trước khi hoàn tất trả kết quả.
- `SQLException` là checked exception, nên method công bố `throws SQLException`. Một lỗi trong query, lấy connection hoặc đóng resource cũng có thể dẫn đến SQLException.
- Khi lấy từ pool, `connection.close()` là hành động **trả tài nguyên về pool** theo hợp đồng của pool; không tự giữ connection này trong static field hoặc gửi ra nơi sử dụng sau khi scope kết thúc.
- Không đưa cả `DataSource` do ứng dụng sở hữu chung vào `try-with-resources` của từng request; vòng đời quản lý pool thuộc cấu hình ứng dụng và API pool cụ thể.

### 6.3. Điều `try-with-resources` không tự làm cho JDBC

**Đóng connection không đồng nghĩa với commit transaction.** Khi tự quản lý transaction (đã `setAutoCommit(false)`), ứng dụng phải quyết định **commit khi thành công, rollback khi thất bại** theo hợp đồng database/connection pool. Không dùng việc rời scope hay `close()` như một cách thay thế `commit`/`rollback`.

Ví dụ cấu trúc giao dịch với connection được sở hữu trong method:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    try {
        // Thực hiện các thao tác SQL, mỗi statement/result set có scope riêng.
        connection.commit();
    } catch (SQLException | RuntimeException error) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            error.addSuppressed(rollbackFailure);
        }
        throw error;
    }
}
```

Đây là **snippet minh họa trong method khai báo `throws SQLException`**, với `dataSource` đã có. Trong hệ thống production, cần xét cả khôi phục `autoCommit`, trạng thái connection khi commit/rollback lỗi, giao dịch do framework quản lý và quy ước của pool. Nếu ứng dụng dùng JPA, Spring transaction manager hoặc một framework khác, thường phải để **thành phần quản lý transaction/connection** sở hữu vòng đời theo hợp đồng của nó, không tùy tiện tự đóng một connection được framework đưa cho dùng chung.

## 7. Tài nguyên tự định nghĩa với `AutoCloseable`

Một class do ứng dụng viết có thể đại diện cho session, lease, lock scope, handle hoặc quá trình cần kết thúc có cấu trúc. Chỉ cần implement `AutoCloseable` và cài đặt `close()` đúng hợp đồng của resource đó.

Lưu thành `CustomAutoCloseableDemo.java`:

```java
public class CustomAutoCloseableDemo {
    static final class WorkSession implements AutoCloseable {
        private boolean closed;

        WorkSession() {
            System.out.println("open session");
        }

        String execute() {
            if (closed) {
                throw new IllegalStateException("session already closed");
            }
            return "done";
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                System.out.println("close session");
            }
        }
    }

    public static void main(String[] args) {
        try (WorkSession session = new WorkSession()) {
            System.out.println("result=" + session.execute());
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 CustomAutoCloseableDemo.java
java CustomAutoCloseableDemo
```

Stdout:

```text
open session
result=done
close session
```

**Cơ chế hoạt động:**

- `WorkSession implements AutoCloseable` làm class đủ điều kiện xuất hiện trong header `try (WorkSession session = ...)`.
- Constructor có thể thiết lập tài nguyên; `close()` định nghĩa cách kết thúc. Ở ví dụ, đó là chuyển trạng thái và in log, giúp ta quan sát vòng đời.
- `close()` được override **không khai báo checked exception**, nên method `main` không cần `throws Exception` chỉ để dùng tài nguyên này.
- `execute()` kiểm tra trạng thái để tránh dùng lại session sau khi nó bị đóng.
- Biến `closed` làm `close()` của ví dụ có thể được gọi nhiều lần mà không in/đóng lại. Đây là **quyết định triển khai của class**, không phải bảo đảm chung của mọi `AutoCloseable`.
- Ứng dụng thực tế có thể dùng cùng mẫu này để release một lease hoặc mở/đóng context, nhưng logic phải phù hợp với resource thực tế (nhất là trong môi trường nhiều thread).

### 7.1. Khi nào nên implement `Closeable` thay vì `AutoCloseable`?

Nếu object đại diện cho tài nguyên I/O có hành vi đóng bằng `IOException`, implement `Closeable` có thể thể hiện hợp đồng rõ ràng hơn. Nếu class chỉ sở hữu một trạng thái/tác vụ ứng dụng và không gắn với I/O, `AutoCloseable` là lựa chọn tổng quát.

| Tiêu chí | `AutoCloseable` | `Closeable` |
| --- | --- | --- |
| Package | `java.lang` | `java.io` |
| Chữ ký `close` | `throws Exception` | `throws IOException` |
| Mục tiêu | Tài nguyên có cleanup bất kỳ | Tài nguyên I/O hoặc tương tự I/O |
| Quan hệ | Interface nền | Kế thừa `AutoCloseable` |
| Có dùng trong try-with-resources? | Có | Có |

Không cần khai báo `throws Exception` trong `close` của custom class nếu thật sự không phát sinh checked exception. Chữ ký hẹp giúp caller dễ làm việc hơn. Nếu việc đóng có thể thất bại, đừng im lặng nuốt một lỗi quan trọng chỉ để làm chữ ký “đẹp”.

## 8. Exception trong thân `try` và khi đóng custom resource

Với tài nguyên custom có `close()` ném lỗi, có thể xuất hiện đồng thời lỗi của công việc chính và lỗi cleanup. Java giữ một lỗi **primary** và gắn các lỗi đóng thành **suppressed exceptions** theo quy tắc `try-with-resources`.

Lưu thành `CustomCloseFailuresDemo.java`:

```java
import java.io.IOException;

public class CustomCloseFailuresDemo {
    static final class FailingResource implements AutoCloseable {
        private final String name;

        FailingResource(String name) {
            this.name = name;
            System.out.println("open " + name);
        }

        @Override
        public void close() throws IOException {
            System.out.println("close " + name);
            throw new IOException("close-" + name);
        }
    }

    public static void main(String[] args) {
        try (
            FailingResource a = new FailingResource("A");
            FailingResource b = new FailingResource("B")
        ) {
            throw new IllegalStateException("work-failed");
        } catch (Exception error) {
            System.out.println("primary=" + error.getMessage());

            for (Throwable suppressed : error.getSuppressed()) {
                System.out.println(
                    "suppressed=" + suppressed.getMessage()
                );
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 CustomCloseFailuresDemo.java
java CustomCloseFailuresDemo
```

Stdout:

```text
open A
open B
close B
close A
primary=work-failed
suppressed=close-B
suppressed=close-A
```

**Giải thích từng điểm:**

1. A khởi tạo, rồi B khởi tạo.
2. Body ném `IllegalStateException("work-failed")`: đây là primary.
3. Java cố đóng B trước; `B.close()` ném `IOException("close-B")` và được **suppress** vào primary.
4. Java vẫn cố đóng A; `A.close()` ném `IOException("close-A")` và tiếp tục được suppress.
5. `catch` chạy sau giai đoạn đóng; `getSuppressed()` trả hai lỗi đóng theo thứ tự B, A.

Nếu body hoàn thành bình thường mà **cả hai close** đều lỗi, lỗi từ B.close (được gọi trước) thường là **primary**, còn lỗi A.close là suppressed. Điều này bảo toàn thông tin và phù hợp với mô hình nhiều resource hiện nay.

**Cẩn thận:** suppress không có nghĩa lỗi cleanup không quan trọng. Trong database, flush/close thất bại có thể tác động đến trạng thái giao dịch hoặc độ bền dữ liệu. Hãy ghi log/diagnostic có cả primary, cause và suppressed, đồng thời tránh ghi nội dung nhạy cảm vào log.

## 9. Nhiều resource và khởi tạo dở dang

Với:

```java
try (
    ResourceA a = acquireA();
    ResourceB b = acquireB();
    ResourceC c = acquireC()
) {
    doWork(a, b, c);
}
```

Đây là mã minh họa với class/helper giả định. Java đánh giá từ trái sang phải:

- Nếu A mở thành công, B mở thành công và C mở thất bại: Java đóng **B rồi A** trước khi truyền lỗi khởi tạo C ra ngoài.
- Nếu A mở thành công nhưng B mở thất bại: Java đóng **A**, không thử tạo C.
- Nếu A mở thất bại ngay: B và C không được tạo, cũng chưa có resource được đăng ký để tự đóng.
- Nếu một constructor/factory tự cấp phát tài nguyên nội bộ rồi thất bại **trước khi trả đối tượng**, factory/constructor phải tự dọn phần đó. Try-with-resources không thể tự đóng một đối tượng chưa khởi tạo thành công.

Đặt thao tác `acquire...` **trong header** là ưu điểm lớn khi ghép nhiều tài nguyên. Nếu tự mở tất cả bên ngoài:

```java
ResourceA a = acquireA();
ResourceB b = acquireB(); // Nếu lỗi ở đây thì chưa vào try.
try (a; b) {
    doWork(a, b);
}
```

Cú pháp dùng biến đã tồn tại `try (a; b)` được bổ sung từ **Java 9** cho biến final/effectively final, nhưng nó **không tự bảo vệ việc mở B trước khi vào try**. Nếu B lỗi trong ví dụ này, A có thể không được đóng. Cần đặt hoạt động cấp phát đúng bên trong phạm vi được quản lý hoặc dùng một cơ chế cleanup ngoài phù hợp.

## 10. Ownership: khi nào không được đóng?

Đây là câu hỏi quan trọng ngang với “có implement AutoCloseable không?”. Một đối tượng có `close()` không có nghĩa **method hiện tại sở hữu quyền đóng nó**.

### 10.1. Các handle do method tự mở

Ví dụ `Files.newInputStream(path)` hoặc `FileChannel.open(path)` trong một method: nếu method sở hữu handle đó và không truyền ownership đi, nên dùng try-with-resources. Đóng ở ranh giới hẹp nhất mà công việc với tài nguyên đã hoàn tất.

### 10.2. Handle do caller/framework cung cấp

Nếu method nhận `InputStream input` từ caller, **thường không tự đóng** trừ khi hợp đồng công bố method nhận ownership. Nếu đóng một stream dùng chung quá sớm, các method khác sẽ thất bại. Ví dụ tránh:

```java
static void readBorrowed(java.io.InputStream input) throws IOException {
    try (input) {
        input.read();
    }
}
```

Đây là snippet hợp lệ trên Java 9+ khi tham số `input` effectively final, nhưng **chỉ đúng nếu caller chuyển quyền sở hữu cho method**. Nếu `input` là tài nguyên mượn, nên đọc mà không đóng; caller sẽ chịu trách nhiệm kết thúc vòng đời.

**Đặc biệt tránh** tự đặt `System.in`/`System.out`/`System.err` trong try-with-resources ở một tác vụ nhỏ: đây là các stream toàn cục của tiến trình. Một wrapper như `Scanner` trên `System.in` có thể đóng luôn stream bên dưới khi wrapper đóng; phải xác định rõ ownership.

### 10.3. Wrapper quản lý cả tài nguyên bên trong

Ví dụ:

```java
try (java.io.BufferedInputStream buffered =
         new java.io.BufferedInputStream(Files.newInputStream(path))) {
    int firstByte = buffered.read();
}
```

Đây là snippet với `Path path` và import `Files`, chạy trong method xử lý `IOException`. `BufferedInputStream.close()` sẽ đóng underlying stream theo hợp đồng của class này, vì vậy thường chỉ cần khai báo wrapper trong header. Nếu đăng ký cả raw stream và wrapper, underlying có thể bị đóng hai lần; không phải mọi tài nguyên đều cho phép close trùng một cách an toàn.

**Không nên có hai chủ sở hữu cùng gọi close**, trừ khi API thiết kế rõ điều đó. `AutoCloseable` không yêu cầu `close()` phải idempotent.

### 10.4. JDBC pool và framework transaction

Connection do `DataSource` cấp cho một request thường cần được đóng/trả pool khi xong. Nhưng `DataSource` hoặc pool có vòng đời ứng dụng, thường **không** được đóng sau mỗi câu SQL. Tương tự, framework transaction manager có thể sở hữu connection hiện tại; tuân thủ API của framework thay vì tự tạo thêm một scope đóng connection mà framework đang quản lý.

## 11. Chọn phạm vi scope theo công việc thực tế

Một try-with-resources tốt có ranh giới rõ:

- **Tệp nhỏ:** dùng `Files.readString`/`writeString` khi hợp lý, không tạo reader chỉ để có `try`.
- **File lớn/từng dòng:** dùng `BufferedReader` hoặc stream từ `Files.lines`, đóng ngay sau khi xử lý hoàn tất.
- **Copy/transform byte:** dùng `InputStream` + `OutputStream`, quản lý đồng thời khi cả hai cùng thuộc một tác vụ.
- **Channel:** dùng `FileChannel`/`SeekableByteChannel` trong scope mà dữ liệu được đọc/ghi; kết thúc trước khi xóa/đổi tên file nếu nền tảng yêu cầu.
- **JDBC:** lấy connection, chuẩn bị statement và đọc result set trong scope phù hợp; trả connection về pool; tách transaction logic khỏi hành động close.
- **Custom:** thiết kế `close` thực hiện cleanup xác định, an toàn khi lỗi và tương thích ownership của class.

Đừng giữ tài nguyên mở trong khi làm công việc tính toán hoặc gọi mạng không liên quan. Ngược lại, không đóng khi một callback, stream lazy, iterator hoặc tác vụ async **chưa tiêu thụ xong** dữ liệu của tài nguyên. Try-with-resources là quản lý vòng đời **đồng bộ theo phạm vi từ vựng của mã**, không tự chờ một tác vụ async kết thúc.

### 11.1. Mã trả về dữ liệu hay tài nguyên sống?

Mẫu API tốt là trả về **giá trị đã materialize** hoặc chuyển ownership một cách rõ ràng. Ví dụ `JdbcLookupPattern.findName` trả `Optional<String>`, không trả `ResultSet` đã đóng. Với đọc file, nếu cần trả dữ liệu qua stream lazy, caller phải biết có nhiệm vụ đóng stream — hoặc API cung cấp callback xử lý trong scope.

### 11.2. Resource và object lifetime không đồng nhất

Một `Path` hoặc `DataSource` có thể được sử dụng lâu dài mà không cần đóng ở mỗi lệnh. `FileChannel` hoặc `Connection` là handle sống cần quản lý. Chỉ vì hai đối tượng liên quan đến file/database không có nghĩa vòng đời giống nhau.

## 12. Lỗi phổ biến khi áp dụng cho từng nhóm

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Quên đóng `Files.lines`/`Files.walk` | Stream có thể giữ handle file/thư mục | Dùng `try (Stream<?> lines = ...)` hoặc thiết kế ownership rõ |
| Cho `ResultSet` thoát khỏi try của statement | Cursor có thể bị đóng khi method kết thúc | Đọc/materialize kết quả khi scope còn mở |
| Giả định JDK có driver JDBC cho mọi DB | JDBC API chuẩn không đồng nghĩa có driver cụ thể | Cấu hình driver, DataSource và DB đúng môi trường |
| Coi `connection.close()` là `commit()` | Không bảo đảm hoàn tất giao dịch | Quản lý commit/rollback theo transaction contract |
| Đóng cả wrapper và underlying không cần thiết | Dễ double-close, lỗi lifecycle | Chỉ định một owner và kiểm tra wrapper contract |
| Đóng stream do caller cho mượn | Caller có thể tiếp tục cần stream | Chỉ đóng khi nhận ownership theo hợp đồng |
| Đặt việc acquire A và B trước `try (a; b)` rồi giả định an toàn | Nếu mở B lỗi, A chưa nằm trong scope cleanup | Acquire ngay trong header hoặc tự bảo vệ các bước trước try |
| Giả định mọi `close()` chỉ ném `IOException` | `AutoCloseable.close` có thể khai báo `Exception` | Xem kiểu tĩnh/overridden method và checked exceptions |
| Bỏ qua suppressed exception | Có thể mất lỗi cleanup/flush | Xem `getSuppressed()` và giữ cause khi wrap |
| Bắt `Exception` rồi trả thành công | Có thể che lỗi đọc/ghi/database | Trả lỗi rõ hoặc truyền exception phù hợp |
| Đóng channel khi tác vụ async vẫn đang dùng | Truy cập tài nguyên sau khi đóng | Định rõ completion và lifetime của tác vụ |
| Dùng `try-with-resources` cho mọi object | Không phải object nào cũng AutoCloseable hoặc cần cleanup | Chỉ dùng cho resource được sở hữu |
| Dựa vào close để đảm bảo data durability | Flush/close không đồng nghĩa đồng bộ bền vững mọi tầng | Tra API I/O, transaction/force khi cần |
| Tự tạo custom AutoCloseable nhưng `close` không cleanup thật | Mất ý nghĩa hợp đồng, dễ leak | Xây dựng close có thể kiểm thử, dùng trạng thái và chính sách lỗi rõ |

## 13. Quy trình triển khai trong dự án

Khi thêm một `try-with-resources`, có thể kiểm tra theo checklist:

1. **Tài nguyên nào được cấp phát?** Nêu class cụ thể: `BufferedReader`, `FileChannel`, `Connection`, `ResultSet` hay custom handle.
2. **Resource có `AutoCloseable` không?** Nếu không, hãy dùng cơ chế cleanup mà API cung cấp, không giả định đóng được bằng header.
3. **Ai sở hữu?** Method này tạo và sở hữu, hay caller/framework/pool chuyển cho mượn?
4. **Mở ở đâu?** Nếu có nhiều resource, cố gắng acquire trong header để cleanup đúng khi bước sau thất bại.
5. **Đóng theo thứ tự nào?** Các resource được đóng ngược thứ tự khai báo; wrapper hoặc dependency có yêu cầu riêng không?
6. **Lỗi từ `close` là gì?** Có checked exception? Có cần giữ primary/suppressed/cause?
7. **Tài nguyên còn được dùng sau scope không?** Tránh trả `ResultSet`/stream lazy đã đóng hoặc đóng channel trước khi async hoàn tất.
8. **Hợp đồng bên ngoài?** Với JDBC transaction, commit/rollback rõ; với file, cập nhật/ghi đè an toàn; với custom resource, close thật sự giải phóng.
9. **Kiểm thử lỗi:** đường thành công, lỗi khi mở resource thứ hai, lỗi trong body, lỗi khi close và tình huống nhiều lỗi cùng lúc.
10. **Phiên bản:** kiểm tra các tiện ích được dùng trong code (`Files.readString` từ Java 11, `InputStream.transferTo` từ Java 9, `Stream.toList` từ Java 16), không nhầm chúng với cú pháp try-with-resources từ Java 7.

Không cần tự viết `finally` chứa `close` khi một resource phù hợp `AutoCloseable` đã do scope sở hữu. Tuy nhiên `finally` vẫn có thể có ích cho những hoạt động **không phải close** như dọn file tạm do chương trình tạo, hoặc phục hồi trạng thái tùy hợp đồng.

## 14. Bài tập tự kiểm tra và đáp án

**Câu 1.** `Path`, `ByteBuffer`, `FileChannel` và `InputStream`: những đối tượng nào thường được đưa vào header try-with-resources?  
**Đáp án:** `FileChannel` và `InputStream` là những resource cần đóng. `Path` mô tả đường dẫn và `ByteBuffer` chứa byte, không phải handle `AutoCloseable` tương ứng.

**Câu 2.** Mở input thành công nhưng `Files.newOutputStream(...)` ném exception trong cùng header. Input có được đóng không?  
**Đáp án:** Có, vì input đã được khởi tạo thành công và thuộc quyền quản lý của header; Java không chạy body và vẫn cố đóng input.

**Câu 3.** Tại sao phải dùng `try (Stream<String> lines = Files.lines(path))` trong nhiều trường hợp, còn `list.stream()` thì không có nhu cầu tương tự?  
**Đáp án:** Stream từ `Files.lines` có thể giữ tài nguyên I/O; stream từ list thuần bộ nhớ không sở hữu file handle.

**Câu 4.** Trong JDBC, ai thường được đóng sau cùng: `ResultSet`, `PreparedStatement` hay `Connection`?  
**Đáp án:** Khi tạo theo trình tự connection → statement → result set và scope tương ứng, result set được đóng trước, rồi statement, connection sau cùng.

**Câu 5.** Một method JDBC đóng connection bằng try-with-resources nhưng không commit/rollback khi đã tắt auto-commit. Có an toàn không?  
**Đáp án:** Không thể dựa vào close để quyết định transaction. Phải quản lý commit/rollback theo hợp đồng driver/pool/framework.

**Câu 6.** Custom class chỉ implement `AutoCloseable`, `close()` không khai báo checked exception. Caller có bắt buộc thêm `throws Exception` không?  
**Đáp án:** Không chỉ vì class đó, nếu kiểu tĩnh của resource là class có `close()` hẹp/không ném checked exception và các thao tác khác cũng không ném checked exception.

**Câu 7.** `close()` của B và A đều ném lỗi, trong khi body ném lỗi trước. Lỗi nào là primary?  
**Đáp án:** Lỗi từ body; lỗi đóng B, A được thêm vào danh sách suppressed theo thứ tự đóng ngược.

**Câu 8.** Một method nhận `InputStream` do caller sở hữu. Có nên tự động đặt tham số vào `try (input)` không?  
**Đáp án:** Không, trừ khi hợp đồng nói method nhận ownership. Nếu chỉ mượn, caller chịu trách nhiệm đóng.

**Câu 9.** Có nên return `ResultSet` từ một method có `try (ResultSet rows = ...)` không?  
**Đáp án:** Không nên; khi method trả về, result set đã bị đóng. Trả dữ liệu đã trích xuất hoặc thiết kế transfer ownership hợp lệ.

**Câu 10.** Vì sao `try (existingResource)` có thể không bảo vệ được tài nguyên đầu tiên nếu việc tạo tài nguyên thứ hai trước try bị lỗi?  
**Đáp án:** Vì cả hai phép acquire diễn ra trước khi bắt đầu scope; try-with-resources chỉ quản lý resource từ lúc bắt đầu statement đó. Dạng biến đã tồn tại cũng yêu cầu Java 9+.

**Thực hành A – File:** Chạy `FileTextResourcesDemo`, thêm dòng thứ ba, đọc đến `null`, rồi thử một đường lỗi I/O được kiểm soát để quan sát cleanup.

**Thực hành B – Channel:** Chạy `FileChannelResourcesDemo`, đổi `StandardOpenOption` và kiểm tra compiler/runtime; thêm `FileChannel.force(true)` khi cần tìm hiểu durability, không giả định nó cần thiết cho mọi tác vụ.

**Thực hành C – JDBC:** Viết DAO nhận `DataSource` và trả `Optional<String>` hoặc một DTO đã materialize, sử dụng `Connection`, `PreparedStatement` và `ResultSet` trong scope. Sau đó tích hợp driver/DB test thật, kiểm tra pool metrics trước và sau nhiều lượt truy vấn.

**Thực hành D – Custom:** Thay `WorkSession.close()` để ném một checked exception có kiểm soát, chạy `CustomCloseFailuresDemo` và in `getSuppressed()`. Giải thích tại sao custom `close` là phần hợp đồng quản lý resource.

## 15. Tài liệu chính thức

- [Java Language Specification 17 — `14.20.3, try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): resource specification, trình tự đóng và xử lý exception.
- [Java SE 17 — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): hợp đồng `close`, lưu ý về tính idempotent.
- [Java SE 17 — Closeable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Closeable.html): giao diện tài nguyên I/O.
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): reader/writer, byte streams, `lines`, `walk` và các tiện ích tệp.
- [Java SE 17 — FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): API kênh file NIO.
- [Java SE 17 — JDBC Connection](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html), [PreparedStatement](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html), [ResultSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html): vòng đời tài nguyên JDBC.
- [Java SE 17 — Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `getCause()`, `getSuppressed()` và truy vết lỗi.

**Tóm tắt cốt lõi:** `try-with-resources` không chỉ dành cho file. Nó quản lý mọi đối tượng phù hợp `AutoCloseable` **mà scope hiện tại thực sự sở hữu**: reader/writer, stream byte, stream duyệt tệp, channel, connection/statement/result set hoặc custom session. Đóng đúng phạm vi giúp giảm rò rỉ tài nguyên; thiết kế đúng ownership, transaction, ngoại lệ và thời gian sống mới bảo đảm chương trình hoạt động an toàn trong Java hiện đại.
