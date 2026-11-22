# Log vào file trong Java: FileHandler, RollingFileAppender và vận hành an toàn

## 1. Vì sao ứng dụng cần ghi log vào file?

**File logging** là cách ghi các sự kiện của chương trình vào một hoặc nhiều tệp trên hệ thống lưu trữ thay vì chỉ hiển thị trên terminal. Khi ứng dụng Java xử lý request, chạy job hoặc giao tiếp với database, log file có thể hỗ trợ:

- Tra cứu diễn biến trước và sau khi phát sinh sự cố.
- Giữ lại bằng chứng kỹ thuật sau khi phiên terminal kết thúc.
- Chuyển dữ liệu tới agent hoặc nền tảng tập trung bằng cơ chế đọc file.
- Phân tách log của các chương trình, môi trường hoặc loại sự kiện theo chính sách.
- Áp dụng rotation, nén, retention và phân quyền truy cập.

Ví dụ nội dung tệp `orders.log`:

```text
INFO | event=order_received orderId=ORD-7
WARNING | event=payment_retry_scheduled attempt=2
SEVERE | event=order_save_failed orderId=ORD-8
```

Trong ví dụ này, **nội dung đã được formatter tạo thành text**, còn file là **đích ghi**. Việc chuyển từ console sang file không tự thay đổi level, không tự tạo request ID và không tự làm message an toàn.

Đừng nhầm **ghi được vào file** với **bảo đảm log tồn tại vĩnh viễn**. File có thể bị xoay vòng, xóa theo chính sách, đầy ổ đĩa, lỗi I/O, không được collector thu hoặc còn nằm trong buffer khi tiến trình dừng đột ngột.

Đặc biệt, trong container/Kubernetes, ghi vào **stdout/stderr** để hệ thống thu thập đôi khi phù hợp hơn file cục bộ; lựa chọn phải dựa trên kiến trúc triển khai.

## 2. Các thành phần tham gia quá trình file logging

Một luồng xử lý điển hình:

```text
Java business code
    |
    | logger.info(...), logger.log(...)
    v
Logging API / facade
    |
    v
Logging backend, level và filter
    |
    v
Handler / Appender
    |
    +-- Formatter / Encoder
    |
    +-- Ghi vào orders.log
    |
    v
File system (buffer, quyền truy cập, dung lượng...)
    |
    v
Log collector / shipper (nếu có)
```

Tùy framework, thứ tự chi tiết giữa filter, formatter/encoder và appender khác nhau. Ý nghĩa chính:

| Thành phần | Ví dụ | Trách nhiệm |
|---|---|---|
| API | JUL `Logger`, SLF4J `Logger` | Ứng dụng tạo event |
| Level/filter | `INFO`, `WARNING`, `ERROR` | Chọn những event được giữ |
| File sink | JUL `FileHandler`, Logback `FileAppender` | Ghi các event được nhận tới file |
| Formatter/encoder | `SimpleFormatter`, `PatternLayoutEncoder` | Chuyển event thành text/XML/JSON |
| Rolling policy | Size/time based | Đổi tên/chuyển file đang ghi và kiểm soát lịch sử |
| File system | Local disk, volume | Thực sự lưu bytes; có thể gặp lỗi |
| Collector | Agent đọc file | Chuyển sự kiện đến nơi tìm kiếm/tổng hợp |

Một backend có thể cho phép gắn **nhiều appender** để vừa ghi console vừa ghi file. Khi đó hai bản sao có thể được chuyển tới hệ thống thu thập, dễ làm tăng gấp đôi số dòng nếu collector đọc cả hai đích. Cần xác định một pipeline chủ đạo.

## 3. Cách đơn giản nhất trong JDK: JUL FileHandler

`java.util.logging` (JUL) đi kèm JDK, không cần tải thư viện. Để ghi file, ta dùng:

- `java.util.logging.Logger`: nơi ứng dụng phát log.
- `java.util.logging.FileHandler`: handler ghi event xuống tệp.
- `java.util.logging.Formatter`: quyết định cách hiển thị.
- `java.util.logging.Level`: quyết định mức độ.
- `LogRecord`: một sự kiện log cùng message, parameters, Throwable và metadata.

Ví dụ ý tưởng:

```java
Logger log = Logger.getLogger("com.example.orders");
FileHandler file = new FileHandler("logs/orders.log", true);
file.setFormatter(new SimpleFormatter());
log.addHandler(file);
log.info("event=order_created");
```

Đây là **đoạn minh họa**, giả định thư mục `logs` đã tồn tại và imports được khai báo. Tham số `true` của constructor được dùng cho **append mode**: cố gắng thêm sự kiện vào file đã có thay vì bắt đầu lại từ đầu. Phần ví dụ hoàn chỉnh ở mục 5 sẽ tự tạo thư mục, đóng handler và chứng minh file ghi đúng.

### 3.1. Điều kiện đường dẫn và quyền ghi

`FileHandler` không phải công cụ quản lý toàn bộ cấu trúc thư mục. Ứng dụng nên bảo đảm thư mục cha tồn tại trước khi mở file và tài khoản chạy JVM có quyền ghi tại đó. Đường dẫn tương đối như `logs/orders.log` được diễn giải theo **working directory của process**, không nhất thiết là thư mục chứa tệp `.java` hoặc `.jar`.

Đường dẫn trong môi trường phát triển và production có thể khác nhau. Ví dụ chạy bằng IDE, Maven, service manager hoặc container thường có working directory riêng; nếu muốn cấu hình ổn định, dùng đường dẫn được chỉ định rõ trong runtime config.

### 3.2. Format mặc định không phải text một dòng như ví dụ

Khi tự tạo `FileHandler` mà không đặt formatter, JUL thường dùng **`XMLFormatter`**. Vì vậy việc gọi `new FileHandler(...)` không bảo đảm tệp chứa dòng text như `INFO event=...`. Muốn dùng text, có thể đặt `SimpleFormatter` hoặc tự viết `Formatter`.

`SimpleFormatter` có thể chứa thời gian, source, level, message và exception; output tùy pattern và cấu hình. Với dữ liệu để collector parse, hãy xác định schema và cách escaping thay vì dựa vào cảm giác “nhìn giống JSON”.

### 3.3. Appender khác Handler ở tên, không phải mục đích

Trong Logback, `FileAppender` hoặc `RollingFileAppender` đảm nhiệm vai trò gần với JUL `FileHandler`. Trong Log4j 2 có `File` và `RollingFile` appender. **Không sao chép trực tiếp cấu hình giữa chúng**: classes, level, XML properties và rolling policy có semantics khác nhau.

## 4. Append, overwrite và vòng đời của file

### 4.1. Ghi nối tiếp (append)

```java
new FileHandler("logs/orders.log", true);
```

Khi mở file thành công và không có xung đột lock, chế độ append giúp giữ nội dung hiện có rồi ghi thêm event mới. Phù hợp khi ứng dụng khởi động lại và cần tiếp tục cùng tệp.

Nhưng append **không thay thế rotation và retention**. Nếu không có giới hạn, file có thể tăng mãi cho tới khi đầy ổ. Với môi trường chạy lâu dài, cần cấu hình rolling/rotate hoặc giao trách nhiệm đó cho công cụ ngoài.

### 4.2. Ghi lại từ đầu (overwrite)

```java
new FileHandler("logs/orders.log", false);
```

Tùy constructor, pattern và cách backend mở file, `false` chọn chế độ **không append**. Đây là chế độ hữu ích cho demo hoặc test muốn output xác định; trong production nó có thể làm mất log trước đó khi process khởi động lại.

**Hãy quyết định append dựa trên yêu cầu lưu giữ log**, đừng chỉ chọn `false` để file nhìn ngắn hơn. Khi tái tạo đầu ra cho bài học, ta sẽ cố ý dùng `false` và chú thích rằng đây không phải policy production.

### 4.3. Flush và close

- `flush()` yêu cầu handler/stream đẩy dữ liệu đang được buffer.
- `close()` đóng resource, giải phóng file handle và cơ chế lock liên quan.
- Khi JVM chết đột ngột, `finally` hoặc shutdown hook **có thể không chạy**, và dữ liệu trong buffer/queue có thể mất.
- Flush tại ứng dụng không tự bảo đảm dữ liệu đã được fsync xuống ổ vật lý hoặc đã được collector xử lý.

Một chương trình ngắn phải đóng handler sau khi ghi, nhất là trước khi đọc lại file để xác minh nội dung. Chương trình server lâu dài thường để logging framework/quản lý vòng đời của process đóng ở giai đoạn shutdown phù hợp, không mở/đóng một handler riêng cho mỗi request.

## 5. Ví dụ Java 17+ hoàn chỉnh: ghi file, đóng handler, đọc lại kết quả

Ví dụ chỉ dùng **JDK**, không cần Maven, SLF4J, Logback hay các dependency khác. Tác dụng:

1. Tạo thư mục `logs` nếu chưa tồn tại.
2. Mở `logs/orders.log`, đặt mã hóa UTF-8 và formatter text.
3. Ghi INFO, WARNING, SEVERE; thử một event FINE để minh họa lọc tại handler.
4. Đóng file handler.
5. Đọc lại chính tệp đã ghi rồi xuất từng dòng ra **stdout**.

### 5.1. Tệp `FileLoggingDemo.java`

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class FileLoggingDemo {
    private static final Logger LOG =
            Logger.getLogger(FileLoggingDemo.class.getName());

    public static void main(String[] args) throws IOException {
        Path logDir = Path.of("logs");
        Files.createDirectories(logDir);

        Path logFile = logDir.resolve("orders.log");

        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        // false: bắt đầu file mới để kết quả demo xác định.
        FileHandler handler = new FileHandler(logFile.toString(), false);
        handler.setLevel(Level.INFO);
        handler.setEncoding(StandardCharsets.UTF_8.name());
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " | " + formatMessage(record)
                        + System.lineSeparator();
            }
        });

        LOG.addHandler(handler);
        try {
            LOG.log(Level.INFO,
                    "event=order_received orderId={0}", "ORD-7");
            LOG.log(Level.WARNING,
                    "event=payment_retry_scheduled attempt={0}", 2);
            LOG.fine("event=debug_probe");
            LOG.log(Level.SEVERE,
                    "event=order_save_failed orderId={0}", "ORD-8");
        } finally {
            LOG.removeHandler(handler);
            handler.flush();
            handler.close();
        }

        List<String> lines = Files.readAllLines(
                logFile, StandardCharsets.UTF_8);
        for (String line : lines) {
            System.out.println(line);
        }
    }
}
```

**Kiểm tra tên file và class:** class public là `FileLoggingDemo`, vì vậy mã phải nằm trong `FileLoggingDemo.java`. Chương trình chỉ gọi API có sẵn trong Java 17, không import Logback hay SLF4J.

### 5.2. Biên dịch và chạy

Trong thư mục chứa `FileLoggingDemo.java`, dùng JDK 17 trở lên:

```bash
javac -encoding UTF-8 FileLoggingDemo.java
java FileLoggingDemo
```

Với một tiến trình chạy riêng, có quyền ghi và không có tiến trình khác đang giữ lock trên `logs/orders.log`, **stdout chính xác do chương trình tạo**:

```text
INFO | event=order_received orderId=ORD-7
WARNING | event=payment_retry_scheduled attempt=2
SEVERE | event=order_save_failed orderId=ORD-8
```

Tệp `logs/orders.log` cũng chứa ba dòng tương ứng, dùng ký tự xuống dòng theo hệ điều hành. Chương trình không chủ động in log trực tiếp ra console từ JUL, vì `LOG.setUseParentHandlers(false)` và chỉ gắn `FileHandler`. **Stdout xuất hiện là do vòng lặp `System.out.println` sau khi đọc file**, không phải file handler tự ghi ra stdout. Trong trường hợp bình thường, stderr không chứa message logger của ví dụ.

### 5.3. Vì sao chỉ có ba dòng?

- `LOG.setLevel(Level.ALL)` cho phép logger phát các event chi tiết.
- `handler.setLevel(Level.INFO)` chỉ cho event ở mức INFO trở lên đi tới file.
- `LOG.fine("event=debug_probe")` bị **handler loại**, vì vậy không nằm trong file.
- `Formatter.formatMessage(record)` dùng dữ liệu parameters để thay `{0}` của JUL. Đây **không phải cú pháp `{}` của SLF4J**.
- Formatter dùng `getLevel().getName()` nên hiện `WARNING` và `SEVERE` đúng như mức JUL, không tự chuyển thành `WARN`, `ERROR`.
- `false` trong constructor làm file bắt đầu lại khi chạy demo, tránh cộng dồn nội dung từ lần chạy trước.
- `handler.close()` giúp giải phóng file trước khi vòng lặp đọc lại; tuy vậy khi có collision/lock hoặc lỗi I/O, cần xử lý ngoại lệ theo chính sách của ứng dụng.

Nếu đổi `handler.setLevel(Level.INFO)` thành `Level.ALL`, dòng `FINE` có thể xuất hiện. Nếu giữ handler `ALL` nhưng đổi logger thành `INFO`, `FINE` vẫn bị loại tại logger. **Logger và handler có hai tầng kiểm soát level**.

### 5.4. Một giới hạn có chủ đích của demo

Custom Formatter ở trên chỉ xuất level và message; nếu event chứa Throwable, ví dụ chưa xuất stack trace. Trong production, hãy dùng formatter hỗ trợ exception hoặc bổ sung xử lý `record.getThrown()` đúng cách. Đừng bỏ cause chain chỉ để log file trông gọn.

Cũng không nên gọi `Files.readAllLines` với file log khổng lồ: nó nạp toàn bộ file vào bộ nhớ. Phần đọc file ở ví dụ chỉ dùng để **xác minh đầu ra nhỏ**. Với file lớn, dùng streaming/tail/collector thay vì load cả file vào heap.

## 6. Ghi exception vào file: phải giữ Throwable và stack trace

Khi lỗi xảy ra, một lời gọi ghi log đúng có thể truyền đối tượng exception:

```java
try {
    repository.save(order);
} catch (Exception error) {
    LOG.log(Level.SEVERE, "event=order_save_failed", error);
    throw error;
}
```

Đoạn này là **minh họa JUL**, không phải chương trình độc lập; `repository` và `order` chưa được khai báo. Hơn nữa, **log rồi ném lại** có thể làm log trùng nếu tầng ngoài cũng log cùng exception. Tốt hơn thường chọn một boundary chịu trách nhiệm ghi lỗi cuối cùng; các tầng trung gian truyền exception và giữ cause.

Trong JUL, `LOG.log(Level.SEVERE, message, error)` gắn `Throwable` vào `LogRecord`. Tuy nhiên formatter phải quyết định trình bày nó. `SimpleFormatter` có khả năng xuất stack trace, còn formatter demo ở mục 5 không xuất `record.getThrown()`.

Nếu tự viết formatter, có thể lấy exception:

```java
Throwable error = record.getThrown();
if (error != null) {
    // Chọn quy trình đáng tin cậy để thêm stack trace/cause.
}
```

Đây là **fragment** trong `format(LogRecord)`. Không ghi đơn thuần `error.getMessage()` rồi kết luận đủ thông tin, vì có thể mất loại exception, nguyên nhân gốc và các suppressed exceptions.

### MessageFormat và Throwable là hai phần khác nhau

JUL dùng `{0}`, `{1}` cho tham số message. Nếu cần **vừa message có parameter vừa Throwable**, có thể tạo `LogRecord` với cả parameters và thrown:

```java
LogRecord record = new LogRecord(
        Level.SEVERE, "event=order_failed orderId={0}");
record.setParameters(new Object[]{"ORD-7"});
record.setThrown(error);
LOG.log(record);
```

Các đoạn trên minh họa API, giả định biến `error` đã tồn tại. Khi dùng formatter tùy chỉnh, `formatMessage(record)` xử lý parameters và phần riêng của formatter xử lý Throwable.

## 7. Cấu hình FileHandler bằng logging.properties

Không phải lúc nào cũng cần viết mã tạo handler. JUL hỗ trợ cấu hình `LogManager`, ví dụ file `logging.properties`:

```properties
handlers=java.util.logging.FileHandler
.level=INFO

java.util.logging.FileHandler.level=ALL
java.util.logging.FileHandler.pattern=logs/application.%g.%u.log
java.util.logging.FileHandler.limit=1048576
java.util.logging.FileHandler.count=3
java.util.logging.FileHandler.append=true
java.util.logging.FileHandler.encoding=UTF-8
java.util.logging.FileHandler.formatter=java.util.logging.SimpleFormatter

java.util.logging.SimpleFormatter.format=%4$-7s %3$s - %5$s%6$s%n
```

Cấu hình này là **ví dụ độc lập về file properties**; cần bảo đảm thư mục `logs` đã tồn tại hoặc dùng một đường dẫn chắc chắn ghi được. Tùy chính sách của tổ chức, có thể thay log path bằng thư mục được mount/được phân quyền riêng.

Trong cách nạp mặc định của JUL, có thể chỉ định file bằng JVM property khi chạy ứng dụng:

```bash
java -Djava.util.logging.config.file=logging.properties com.example.Main
```

Lệnh chỉ là **mẫu chạy**, yêu cầu class `com.example.Main` đã được biên dịch và file cấu hình nằm ở đường dẫn được chỉ định. Với application server/Spring Boot, hệ thống logging có thể được framework quản lý bằng cơ chế khác.

### 7.1. Ý nghĩa các thuộc tính

| Thuộc tính | Ý nghĩa |
|---|---|
| `handlers` | Những handler được gắn theo cấu hình |
| `.level` | Level của root logger theo cách tổ chức LogManager |
| `FileHandler.level` | Ngưỡng lọc riêng của handler ghi file |
| `FileHandler.pattern` | Mẫu tên file và token thay thế |
| `FileHandler.limit` | Kích thước giới hạn cho mỗi file theo quy tắc FileHandler |
| `FileHandler.count` | Số file được dùng trong vòng rotation |
| `FileHandler.append` | Ghi nối tiếp hay mở từ đầu |
| `FileHandler.encoding` | Encoding để ghi ký tự |
| `FileHandler.formatter` | Formatter dùng để chuyển LogRecord thành chuỗi |
| `SimpleFormatter.format` | Pattern text của SimpleFormatter |

Mức `.level=INFO` cùng handler `ALL` **không mở thêm FINE** nếu root logger đã lọc nó. Để xem FINE, phải xét level hiệu lực của logger, handler và filter trên đường đi.

### 7.2. Cú pháp pattern của JUL khác pattern Logback

Trong `SimpleFormatter`:

```text
%4$-7s  -> level, căn trái tối thiểu 7 ký tự
%3$s    -> logger name
%5$s    -> message đã format
%6$s    -> phần Throwable nếu có
%n      -> ký tự xuống dòng
```

Đây là syntax của `java.util.Formatter` dành cho `SimpleFormatter`. Nó **không phải** `%-7level`, `%logger`, `%msg` của Logback PatternLayout. Mỗi backend có bộ token riêng.

### 7.3. Vì sao cấu hình không có tác dụng?

Những nguyên nhân phổ biến:

- JVM chưa nạp đúng `logging.properties`; đường dẫn `-Djava.util.logging.config.file` sai.
- Framework/container đã cấu hình logger/handler theo một cách khác.
- Ứng dụng còn gắn handler riêng bằng code và event đi qua hai đường.
- Level hoặc filter chặn sự kiện trước khi đến FileHandler.
- Thư mục hoặc file không ghi được, nhưng lỗi được báo qua error handler/status thay vì nơi người phát log đang quan sát.
- Kiểu file format đang là XML thay vì text như mong muốn.

Không nên đoán “Logback không hoạt động” khi thực tế code đang dùng JUL. Hãy xác định logging API, backend và file config thật sự được nạp.

## 8. Xoay vòng file với JUL FileHandler

Nếu ứng dụng ghi log không giới hạn, file có thể trở thành gánh nặng lớn. **Rotation** là chuyển sang tệp mới khi đạt một điều kiện, thường là dung lượng hoặc thời gian.

JUL `FileHandler` hỗ trợ cơ chế rotation theo **dung lượng** và **số lượng file**. Constructor minh họa:

```java
FileHandler handler = new FileHandler(
        "logs/app.%g.%u.log",
        1_000_000,
        3,
        true);
```

Đây là fragment, yêu cầu imports và thư mục phù hợp. Các tham số theo thứ tự là:

1. Mẫu tên file.
2. Ngưỡng byte của mỗi file.
3. Số file trong chu trình luân chuyển.
4. Có append hay không.

Khi log tiến gần/đạt ngưỡng theo cách triển khai của FileHandler, backend luân chuyển qua các thế hệ file. Đừng suy ra rằng ba file luôn có đúng `1_000_000` bytes hoặc lần ghi nào cũng chia đúng biên; một record có thể làm kích thước vượt mốc tùy cơ chế ghi và rotation.

### 8.1. Token tên file

Những token quan trọng của `FileHandler`:

| Token | Ý nghĩa |
|---|---|
| `%g` | Số thế hệ file trong vòng rotation |
| `%u` | Số giúp phân biệt khi xảy ra va chạm tên/lock |
| `%t` | Thư mục tạm do hệ thống xác định |
| `%h` | Home directory của người dùng chạy JVM |
| `%%` | Dấu `%` thật |

Ví dụ `logs/app.%g.%u.log` giúp tách generation và unique index. Nếu bỏ `%g` trong mô hình rotation nhiều file, JUL có thể tự thêm phần generation vào tên. File name thực tế còn chịu tác động của trạng thái file lock, process khác, platform và pattern.

### 8.2. FileHandler không có đầy đủ rolling policy theo thời gian

Trong JDK, `FileHandler` **không tự cung cấp một bộ chính sách rolling theo ngày, nén `.gz`, giữ đúng N ngày và xóa theo tuổi** như nhiều rolling appender chuyên dụng.

Nếu cần:

```text
Mỗi ngày tạo một nhóm log file
File đạt 10 MB được chuyển sang file tiếp theo
Nén file lịch sử
Chỉ giữ 14 ngày
Giới hạn tổng dung lượng 1 GB
```

có thể cân nhắc **Logback RollingFileAppender**, Log4j 2 RollingFile, hệ thống log rotation ngoài JVM hoặc collector phù hợp. Không nên tự viết FileHandler phức tạp chỉ để bắt chước mọi rolling policy nếu dự án đã có backend hỗ trợ.

### 8.3. Rotation không đồng nghĩa retention chính xác theo thời gian

Một chính sách giới hạn file count có thể không đáp ứng yêu cầu “xóa log quá 90 ngày”. Cần phân biệt:

- **Size-based rotation:** đổi file khi đạt dung lượng.
- **Time-based rotation:** đổi file theo ngày/giờ hoặc khoảng thời gian.
- **Retention:** quyết định các file cũ tồn tại bao lâu hoặc giữ bao nhiêu.
- **Compression:** nén dữ liệu lịch sử; giảm dung lượng nhưng tạo thêm I/O.
- **Archiving:** chuyển log cũ đến kho lưu riêng; không mặc nhiên được thực hiện bởi rotation.

Hãy định nghĩa và kiểm thử từng trách nhiệm, đặc biệt trong môi trường có quy định lưu giữ dữ liệu.

## 9. Dùng SLF4J + Logback để ghi file

Trong ứng dụng dùng **SLF4J API** và **Logback backend**, `FileAppender` ghi trực tiếp file, còn `RollingFileAppender` thường được chọn khi cần rotation. Dưới đây là cấu hình để học cách chọn appender đích; nó **không dùng cú pháp JUL**.

### 9.1. FileAppender đơn giản

Tệp `logback.xml`:

```xml
<configuration>
    <appender name="FILE"
              class="ch.qos.logback.core.FileAppender">
        <file>logs/orders.log</file>
        <append>true</append>
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="FILE"/>
    </root>
</configuration>
```

Với Logback, `%d` là timestamp, `%-5level` là level đã căn, `%logger{36}` là logger name rút gọn cho trình bày và `%msg%n` là message cùng newline.

Đây là **file cấu hình Logback**; để chạy cần ứng dụng có SLF4J API và một provider Logback Classic tương thích. Không sử dụng `java.util.logging.FileHandler` nếu ứng dụng đang chọn backend Logback mà không có bridge phù hợp.

**Khác biệt với demo JUL:** Logback có thể tạo thư mục cha trong quá trình khởi tạo FileAppender theo khả năng của phiên bản, nhưng vẫn phải kiểm tra quyền ghi, mount và đường dẫn thực tế; không coi “tự tạo thư mục” là bảo đảm bất chấp lỗi I/O.

### 9.2. RollingFileAppender theo ngày và dung lượng

Một `logback.xml` đầy đủ hơn:

```xml
<configuration>
    <appender name="FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/orders.log</file>

        <rollingPolicy
                class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
            <fileNamePattern>logs/orders.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
            <maxFileSize>10MB</maxFileSize>
            <maxHistory>14</maxHistory>
            <totalSizeCap>1GB</totalSizeCap>
        </rollingPolicy>

        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="FILE"/>
    </root>
</configuration>
```

Cấu hình này minh họa một **SizeAndTimeBasedRollingPolicy** trong Logback với file đang ghi `logs/orders.log`, file lịch sử có cả ngày và chỉ số, cùng nén gzip.

- `%d{yyyy-MM-dd}` xác định nhóm theo ngày.
- `%i` phân biệt nhiều file trong cùng giai đoạn khi vượt kích thước.
- `maxFileSize` đặt ngưỡng kích thước cho việc chuyển file.
- `maxHistory=14` yêu cầu giữ số **giai đoạn lịch sử** tương ứng, không phải cam kết xóa theo đồng hồ chính xác từng phút.
- `totalSizeCap` đặt giới hạn dung lượng lịch sử theo policy và thứ tự cleanup của backend, không phải quota tổng thể cho cả ổ đĩa.

Cần kiểm tra các thuộc tính, vòng đời cleanup và behavior khi thay version Logback. **Đây không phải cam kết đã kiểm thử trên mọi filesystem**. File rotation có thể phát sinh nén/tạo file đáng kể, nên theo dõi I/O và storage.

### 9.3. Ví dụ mã Java gọi SLF4J

Trong ứng dụng đã có SLF4J + Logback provider:

```java
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(OrderService.class);

LOG.info("event=order_accepted orderId={}", orderId);
```

Đây là **fragment** trong class có `OrderService` và biến `orderId`; không phải tệp Java độc lập. Lời gọi dùng `{}` của SLF4J. Logback đọc cấu hình appender và ghi vào file; mã nghiệp vụ không cần gọi `new FileHandler(...)`.

Một ưu điểm là **thay FileAppender bằng RollingFileAppender thường không yêu cầu sửa các lời gọi SLF4J** nếu API backend đã được tách hợp lý.

## 10. Log4j 2: File và RollingFile appender

Log4j 2 cũng có appender ghi file và xoay vòng, nhưng với định dạng cấu hình riêng. Ví dụ `log4j2.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <RollingFile name="FILE"
                     fileName="logs/orders.log"
                     filePattern="logs/orders-%d{yyyy-MM-dd}-%i.log.gz">
            <PatternLayout
                    pattern="%d{ISO8601} %-5p %c{1} - %m%throwable%n"/>
            <Policies>
                <TimeBasedTriggeringPolicy interval="1"
                                           modulate="true"/>
                <SizeBasedTriggeringPolicy size="10 MB"/>
            </Policies>
            <DefaultRolloverStrategy max="10"/>
        </RollingFile>
    </Appenders>

    <Loggers>
        <Root level="info">
            <AppenderRef ref="FILE"/>
        </Root>
    </Loggers>
</Configuration>
```

Đây là ví dụ **cấu hình Log4j 2**, đòi hỏi Log4j 2 Core, API/provider phù hợp và version có hỗ trợ các thành phần trên.

`DefaultRolloverStrategy max="10"` liên quan đến chính sách chỉ số file trong quá trình rollover; nó **không nên được hiểu một cách đơn giản là giữ mọi log đúng 10 ngày**. Nếu cần xóa theo tuổi hoặc điều kiện đường dẫn, hãy dùng delete/retention strategy hỗ trợ bởi Log4j 2 và kiểm tra kết quả trên môi trường thật.

Không dùng XML Log4j 2 trong `logback.xml`; token `%d`, `%p` trông giống nhau nhưng hai backend không có chung một schema cấu hình.

### 10.1. Chọn giải pháp nào?

| Nhu cầu | Lựa chọn có thể hợp lý |
|---|---|
| Tool Java nhỏ, không dependency | JUL `FileHandler` |
| Ứng dụng SLF4J có Logback sẵn | Logback `FileAppender` hoặc `RollingFileAppender` |
| Ứng dụng chuẩn hóa Log4j 2 | `File`/`RollingFile` của Log4j 2 |
| Microservice container có collector stdout | Thường ưu tiên console appender + collector |
| Log audit cần tính toàn vẹn/bền vững | Thiết kế audit pipeline riêng hoặc lưu trữ đáp ứng quy định |

Không có backend nào tự giải quyết tất cả rủi ro chỉ nhờ tên “File” hoặc “Rolling”.

## 11. Ghi một file từ nhiều thread và nhiều process

### 11.1. Nhiều thread trong một JVM

Backend/handler chính thống thường xử lý đồng bộ hóa nội bộ ở mức phù hợp. Tuy nhiên, mức độ **thứ tự event** vẫn phụ thuộc thread scheduling và cơ chế queue/appender:

- Hai thread tạo event gần nhau có thể enqueue hoặc ghi theo thứ tự không trùng với thứ tự nghiệp vụ.
- Timestamp của event có thể khác thời điểm bytes thực sự được ghi xuống file.
- File content có thể phản ánh một thứ tự xử lý hợp lệ, nhưng không tự là lịch sử tuyến tính của toàn bộ hệ thống.

Khi cần biết luồng sự kiện của một request, hãy ghi `requestId`/`traceId` và các chỉ số nghiệp vụ cần thiết. Không dựa vào vị trí dòng file duy nhất để suy quan hệ nhân quả giữa các tác vụ đồng thời.

### 11.2. Nhiều JVM/process cùng ghi một file

Đây là bài toán khó hơn. Không mặc nhiên an toàn khi hai JVM cùng mở `logs/orders.log` bằng append mode. Có thể gặp xung đột lock, output xen kẽ, độ trễ hoặc rotation làm mất/trộn dữ liệu.

JUL `FileHandler` sử dụng cơ chế lock và token `%u` để hỗ trợ phân biệt file khi bị chiếm; không nên dựa vào đó để cho nhiều process viết chung một file với mọi filesystem. Với Logback/Log4j 2, cấu hình multi-process/prudent mode có giới hạn riêng về rolling và tính năng.

Cách thực tế thường an toàn hơn:

- Mỗi process/instance ghi một đích riêng có tên/ID ổn định.
- Hoặc phát log lên stdout/stderr và để platform thu thập nhiều instance.
- Hoặc dùng cơ chế tập trung/agent đã được thiết kế cho multi-process.

Không đưa PID hay ID của từng request vào tên logger; đó không giải quyết vấn đề phân tách file hoặc correlation.

### 11.3. File lock của JUL

Khi `FileHandler` đang mở, có thể thấy tệp khóa có đuôi `.lck` liên quan tới pattern. Sau khi handler đóng bình thường, lock thường được giải phóng. Nếu process chết bất thường hoặc môi trường có lỗi, cần điều tra trạng thái lock/collision và permission; đừng xóa tùy tiện file lock đang được process khác sử dụng.

## 12. Khi nào nên ghi file thay vì stdout/stderr?

Trong container hoặc hệ thống orchestration, ứng dụng thường được khuyến nghị xuất log vào stdout/stderr để runtime/agent thu thập, bởi vì file trong filesystem tạm của container có thể biến mất khi container bị thay mới.

Ưu điểm stdout/stderr:

- Không cần tự quản lý local file path và quyền thư mục riêng của ứng dụng.
- Collector có thể gắn định danh pod/container/service và chuyển log tập trung.
- Giảm nhu cầu xoay vòng file tại từng instance nếu platform đã có cơ chế xử lý.

Nhưng cần hiểu giới hạn:

- Runtime và collector vẫn có buffering, rotation, quota và nguy cơ mất log.
- Mỗi container platform có chính sách stdout/stderr và retention riêng.
- Ghi console quá nhiều có thể ảnh hưởng hiệu năng; stdout không “miễn phí”.
- Nếu cần forensic/audit theo yêu cầu, console collection thông thường có thể chưa đủ tính toàn vẹn.

File logging vẫn hợp lý với ứng dụng desktop, batch chạy trên máy cố định, phần mềm legacy, nhu cầu output tương thích file shipper hoặc môi trường cần lưu cục bộ. Hãy chọn theo **đường thu thập thực tế**.

## 13. Log rotation, retention và chi phí vận hành

Khi chọn ghi file, có ba nhóm câu hỏi:

### 13.1. Dung lượng và tốc độ tăng

Nếu một ứng dụng tạo 1.000 log events/giây, mỗi event trung bình 500 bytes, lưu lượng log thô xấp xỉ 500.000 bytes/giây. Trong một ngày lý tưởng không đổi tốc độ, đó là khoảng 43,2 GB dữ liệu trước nén và metadata. Đây chỉ là phép tính minh họa, chưa tính burst, stack trace hay output bị nhân bản.

Vì vậy cần:
- Giới hạn log volume bằng level/filter phù hợp.
- Tránh ghi toàn bộ payload, SQL result hoặc object lớn vô ích.
- Chọn rotation/retention và quota dựa trên peak chứ không chỉ trung bình.
- Quan sát storage pressure, inode count và tốc độ ship log.

### 13.2. Retention phải phù hợp chính sách

Không nên xóa log sớm hơn yêu cầu tuân thủ, nhưng cũng không giữ mãi dữ liệu cá nhân hoặc thông tin nhạy cảm không cần thiết. Các chính sách phụ thuộc miền nghiệp vụ, pháp luật và tổ chức; bài này không áp dụng một số ngày bắt buộc cho mọi ứng dụng.

Khi rolling policy nén/xóa file, xác nhận rằng collector đã đọc hết dữ liệu trước khi xóa. Một file có thể bị rotate và xóa **trước khi agent thu thập thành công** nếu pipeline bị gián đoạn đủ lâu.

### 13.3. Tính toán cả nơi lưu và nơi thu thập

Một ứng dụng có thể đồng thời:
1. Ghi log vào file cục bộ.
2. Agent đọc file rồi gửi tới collector.
3. Collector lưu thành chỉ mục và bản sao dự phòng.

Cần tính chi phí cả ba nơi, bao gồm retention, replication và network. **Xoay file ở ứng dụng không tự xóa dữ liệu trong collector**, và xóa dữ liệu trong collector không tự dọn file cục bộ.

## 14. Ghi file đồng bộ, bất đồng bộ và bảo đảm dữ liệu

Ghi file đồng bộ thường diễn ra ở đường gọi của thread phát event, nhưng Java stream/OS có thể vẫn buffer. Ghi bất đồng bộ thường thêm một queue trong JVM để giảm thời gian chờ của thread nghiệp vụ.

So sánh:

| Thuộc tính | FileAppender/FileHandler đồng bộ | Appender bất đồng bộ bọc file |
|---|---|---|
| Thread thực hiện phần ghi file | Thường là caller | Worker của appender |
| Độ trễ caller khi I/O chậm | Có thể tăng | Thường giảm khi queue còn chỗ |
| Bộ nhớ backlog | Ít hơn ở tầng logging | Queue giữ thêm events |
| Khi sink chậm lâu | Caller có thể chặn | Queue đầy → block/drop tùy policy |
| Khi JVM bị kill cưỡng bức | Buffer/record có thể mất | Có thêm event chưa được worker ghi |
| Shutdown | Cần flush/close | Cần drain queue rồi flush/close |

Một `AsyncAppender` của Logback có những tham số như `queueSize`, `discardingThreshold`, `neverBlock` và `maxFlushTime`. Cấu hình có thể ưu tiên latency hoặc giữ event bằng cách chặn producer khi queue đầy; **không có chế độ nào tự bảo đảm exactly-once delivery**.

Nếu log thực sự là dữ liệu nghiệp vụ bắt buộc không được mất (audit, đối soát, giao dịch), hãy dùng kiến trúc bền vững đã được thiết kế cho mục tiêu đó: transactional outbox, database/event log hoặc audit store có chính sách xác nhận, thay vì tin rằng `flush()` hoặc AsyncAppender là đủ.

## 15. Định dạng file: text, JSON và xử lý multiline

### 15.1. Text thuần

Text thường thuận tiện khi cần `tail` hay đọc trực tiếp:

```text
2026-11-09T08:15:03.125Z INFO  order-api event=order_accepted orderId=ORD-7
2026-11-09T08:15:04.140Z ERROR order-api event=order_save_failed orderId=ORD-8
```

Dòng trên là **ví dụ schema**, không phải output tự động của chương trình mục 5. Nếu parser dựa vào dấu cách, cần quy tắc ổn định khi message có khoảng trắng hoặc ký tự đặc biệt.

### 15.2. JSON lines

Một định dạng dễ xử lý bằng collector là **mỗi event một object JSON trên một dòng**:

```json
{"timestamp":"2026-11-09T08:15:03.125Z","level":"INFO","logger":"com.example.orders.OrderService","event":"order_accepted","orderId":"ORD-7","traceId":"trace-42"}
```

Đây là mẫu JSON minh họa. JUL `FileHandler` không tự chuyển message thành JSON có field nghiệp vụ; cần encoder/formatter hoặc công cụ chuyển đổi phù hợp. Logback/Log4j 2 cũng cần JSON layout/encoder được hỗ trợ và cấu hình đúng.

Không xây JSON bằng nối chuỗi khi có input tự do. Dấu ngoặc kép, backslash, newline và control characters phải được escape đúng bằng serializer chuẩn. **Placeholder của SLF4J/JUL không tự trở thành structured fields**.

### 15.3. Stack trace đa dòng

Khi formatter ghi full stack trace, một sự kiện ERROR có thể chiếm nhiều dòng text. Nếu file shipper mặc định coi **mỗi newline là một event mới**, nó có thể tách stack trace thành nhiều sự kiện rời rạc.

Giải pháp:
- Cấu hình multiline parsing ở shipper/collector theo pattern và backend thực tế.
- Hoặc dùng JSON line/structured format với exception được serialize thành trường hợp lệ.
- Đảm bảo không có nội dung nhập từ người dùng giả mạo dòng timestamp/level mới.

Mục tiêu là giữ cả message, cause chain và mối quan hệ của một exception, không phải chỉ làm console đẹp.

## 16. Bảo mật khi ghi log vào file

File log thường chứa định danh giao dịch, request ID, message ngoại lệ và đôi khi dữ liệu người dùng. File phải được quản lý như **tài sản dữ liệu có thể nhạy cảm**, không như một tệp debug vô hại.

### 16.1. Đường dẫn, quyền và người sở hữu

- Chọn thư mục log có quyền ghi cho process nhưng không mở công khai cho người dùng không liên quan.
- Hạn chế read permission của log file theo vai trò vận hành.
- Cẩn trọng với thư mục dùng chung, đường dẫn do input người dùng điều khiển, symlink hoặc mount có quyền quá rộng.
- Không tạo đường dẫn bằng cách ghép trực tiếp giá trị chưa kiểm soát như username, URL path hoặc arbitrary request parameter.
- Theo dõi quota để một lỗi lặp không làm đầy filesystem chứa dữ liệu quan trọng.

### 16.2. Không ghi bí mật và dữ liệu dư thừa

Không đưa password, access token, API key, session cookie, card data, chuỗi kết nối có credential hoặc body chứa dữ liệu cá nhân không cần thiết vào log. Exception message từ thư viện HTTP/JDBC cũng có thể chứa URL query, input hoặc thông tin nhạy cảm.

Redaction/masking cần áp dụng ở nguồn, encoder/formatter và pipeline nơi phù hợp. **Chỉ đổi level từ DEBUG sang INFO không bảo đảm dữ liệu nhạy cảm đã được loại bỏ**, vì giá trị đó có thể xuất trong INFO/ERROR.

### 16.3. Log injection

Nếu người dùng nhập một chuỗi chứa newline, họ có thể tạo output giả dạng nhiều dòng, làm hỏng công cụ phân tích. Formatter text phải xử lý hoặc encode input không tin cậy theo chính sách. Với JSON, dùng serializer chuẩn để escape newline và dấu ngoặc, không tự dựng JSON bằng concatenation.

### 16.4. File được ship đi nơi khác

Quyền file cục bộ không tự bảo vệ dữ liệu sau khi agent gửi đến collector. Cần thêm TLS/chính sách truyền, phân quyền truy cập, mã hóa/lưu trữ, thời hạn giữ, auditing quyền tra cứu và chính sách xóa dữ liệu tùy yêu cầu.

## 17. Xử lý lỗi khi ghi file thất bại

File logging có thể lỗi vì:
- Thư mục không tồn tại hoặc không có quyền.
- File bị process khác giữ lock.
- Disk full, inode exhaustion, quota hoặc filesystem read-only.
- Mount/network filesystem gặp sự cố.
- Appender bị đóng, cấu hình sai hoặc resource hết.
- Rotation/rename/compression thất bại.
- Collector chưa đọc/xử lý được file dù chương trình ghi thành công.

Với JUL, các lỗi nội bộ của handler có thể được chuyển tới `ErrorManager`/cơ chế báo lỗi của logging, không nhất thiết xuất thành exception thông thường ở dòng code `LOG.info(...)`. Với Logback/Log4j 2, cần xem **internal status reporting** và diagnostics của backend.

**Không giả định gọi logger thành công đồng nghĩa ghi file thành công.** Khi ứng dụng phụ thuộc vào log như một yêu cầu bắt buộc, cần cơ chế phát hiện lỗi và lưu dữ liệu phù hợp.

Một rủi ro khác là **recursive logging**: nếu appender ghi file thất bại rồi dùng chính logger/appender đó để ghi về lỗi của mình, có thể tạo vòng lặp, tăng tải và che mất nguyên nhân gốc. Cơ chế báo lỗi nội bộ phải có đường đi tách biệt.

## 18. Kiểm tra và khắc phục sự cố

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không thấy file log | Sai working directory, config chưa nạp hoặc appender chưa khởi tạo | Xác minh đường dẫn thực tế và status nội bộ |
| Bị từ chối quyền ghi | User chạy JVM không có quyền hoặc volume read-only | Điều chỉnh quyền thư mục/mount đúng chính sách |
| File có định dạng XML | JUL `FileHandler` chưa đổi formatter | Đặt `SimpleFormatter`/custom Formatter |
| File bị xóa nội dung sau restart | Đang mở với append=false | Chọn append=true và rolling policy thích hợp |
| File lớn mãi không rotate | Chỉ dùng FileAppender hoặc JUL FileHandler không có limit | Bật rolling/rotation đã được kiểm chứng |
| Có nhiều file tên lạ hoặc `.lck` | FileHandler generation/unique token, collision/lock | Kiểm tra pattern, process, lock và close |
| File log không thấy DEBUG/FINE | Logger level hoặc handler/appender level/filter loại | Xác nhận effective level ở cả hai tầng |
| Event hiển thị hai lần | Có console+file cùng được collector thu hoặc handler cha | Kiểm tra đường xuất và propagation/additivity |
| File có log nhưng dashboard trống | Agent/collector chưa thu, parser sai, index chậm | Kiểm tra file → shipper → collector end-to-end |
| File bị mất sau container restart | Ghi vào filesystem tạm của container | Dùng stdout collection hoặc persistent volume được quản lý |
| Stack trace bị tách thành nhiều bản ghi | Collector parse newline như event riêng | Cấu hình multiline hoặc JSON encoder |
| Log chứa ký tự Unicode sai | Encoding/decoder không thống nhất | Thống nhất UTF-8 và kiểm tra reader/collector |
| Log ghi được rồi ứng dụng chậm | I/O đồng bộ, log volume/formatting lớn | Đo throughput, điều chỉnh level, appender, async có chính sách |
| Shutdown mất phần log cuối | Chưa flush/close, async queue còn tồn, bị kill sớm | Thiết kế shutdown grace period và kiểm tra backlog |
| Ổ đĩa đầy | Không có retention/quota/monitoring | Bổ sung rolling, xóa lịch sử và alert dung lượng |
| Log file bị parse sai | Dùng format text không ổn định hoặc input chứa newline | Chuẩn hóa encoder/schema và escaping |

### Checklist điều tra theo thứ tự

1. Xác định **logging API và backend**: JUL, Logback, Log4j 2 hay bridge.
2. Xác định **file config thực sự được nạp** và handler/appender được khởi tạo.
3. Kiểm tra effective logger level, handler/appender level, filter.
4. Kiểm tra working directory, file pattern, file lock, quyền, dung lượng.
5. Kiểm tra formatter/encoding và thông điệp có tham số/exception.
6. Kiểm tra append/rotation/retention và việc nhiều instance cùng ghi.
7. Kiểm tra file thật có bytes mới hay không, rồi mới xem agent/collector.
8. Nếu file có dữ liệu nhưng dashboard không thấy, kiểm tra pipeline sau file thay vì thay level tùy tiện.

## 19. Bài tập tự kiểm tra

### Tình huống A: File logging bị “mất” sau mỗi lần chạy

Một tool Java dùng `FileHandler("logs/tool.log", false)`. Khi chạy lại, log cũ biến mất.

- Giải thích nguyên nhân.
- Đề xuất đổi sang append khi muốn giữ nội dung.
- Nếu chạy nhiều tuần, cần thêm cơ chế nào để tránh file tăng không giới hạn?

**Gợi ý:** `append=false` chọn không ghi nối tiếp. Chuyển thành `true` nếu muốn giữ nội dung; đồng thời chọn rotation, retention/quota và kiểm tra lock.

### Tình huống B: Khi chạy bằng Maven thì file xuất hiện ở nơi khác

Code mở `Path.of("logs", "app.log")`. Khi khởi động qua IDE và qua service manager, file nằm ở hai thư mục khác nhau.

**Giải thích:** path tương đối dựa trên working directory của process. Để ổn định, cấu hình log directory rõ ràng cho từng môi trường, hoặc sử dụng đích console/agent theo kiến trúc triển khai.

### Tình huống C: Log file có hai dòng cho một sự kiện

Một ứng dụng đồng thời gắn `FileHandler` trực tiếp vào logger và một handler cha khác; collector còn đọc cả console và file.

**Giải thích:** nhiều đường đi có thể nhân bản sự kiện. Xác định luồng logger→handler và appender→collector, tránh gắn đích trùng lặp ngoài chủ đích, không chỉ xóa một dòng code `logger.info(...)`.

### Tình huống D: ERROR cuối job không có trong file dù stdout có

Ứng dụng dùng async file appender, queue còn backlog và container bị terminate trước khi worker hoàn tất.

**Giải thích:** event đã được enqueue nhưng chưa chắc đã ghi xong. Cần shutdown/lifecycle phù hợp và đánh giá rủi ro mất event; dữ liệu audit bắt buộc nên dùng cơ chế bền vững hơn queue in-memory.

## 20. Checklist trước khi triển khai file logging

- [ ] Chọn đúng logging API/backend và **file appender/handler thật sự**.
- [ ] Đường dẫn file và working directory rõ ràng, có quyền ghi phù hợp.
- [ ] Chọn append/overwrite đúng theo mục đích, tránh xóa log khi restart.
- [ ] Logger level, handler/appender level và filters cho phép đúng những event cần ghi.
- [ ] Formatter/encoder có định dạng và encoding nhất quán, xử lý Throwable/cause.
- [ ] Đã chọn rotation theo dung lượng/thời gian và retention/quota theo yêu cầu.
- [ ] Đã kiểm tra khi file bị lock, disk full, permission denied hoặc mount lỗi.
- [ ] Không ghi chung một file tùy tiện từ nhiều JVM/instance.
- [ ] Nếu collector đọc file, đã xác minh end-to-end, multiline, rotation và độ trễ.
- [ ] Nếu dùng async, có chính sách queue đầy, flush/shutdown và mức mất log chấp nhận.
- [ ] Không ghi dữ liệu bí mật, có escaping và phân quyền phù hợp.
- [ ] Đã chọn stdout/stderr hay file theo kiến trúc container/server thực tế.
- [ ] Có công cụ giám sát dung lượng, lỗi ghi, file count và backlog collector.
- [ ] Đã chạy thử output và đọc lại file, kiểm chứng đúng level/encoding/format.

**Kết luận:** ghi log vào file trong Java có thể bắt đầu rất đơn giản bằng `FileHandler` của JUL hoặc `FileAppender` của Logback/Log4j 2. Nhưng file logging đáng tin cậy cần nhiều hơn một đường dẫn: **quản lý vòng đời file, quyền truy cập, định dạng, rotation, retention, lỗi I/O và pipeline thu thập**. Khi ứng dụng được đóng gói và triển khai trên nhiều instance/container, hãy cân nhắc stdout + collector trước khi mặc định mỗi process phải tự quản lý file log.
