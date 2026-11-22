# FileHandler trong Java Util Logging

**`java.util.logging.FileHandler`** là một `Handler` của Java Util Logging (**JUL**) dùng để ghi các `LogRecord` vào tệp trên hệ thống tệp. Thay vì chỉ thấy log trên console, ứng dụng có thể lưu lại sự kiện để điều tra sau khi tiến trình kết thúc. `FileHandler` hỗ trợ cấu hình mẫu tên tệp, ghi nối tiếp hay ghi mới, giới hạn dung lượng và luân phiên tệp (*rotation*), cùng lựa chọn formatter và level.

Để sử dụng đúng `FileHandler`, cần phân biệt ba việc: **logger có chấp nhận sự kiện không**, **handler có chấp nhận sự kiện không**, và **handler ghi bản ghi ra tệp ở định dạng nào**. Tạo ra một `FileHandler` mới chưa đủ: cần gắn nó vào logger hoặc cấu hình `LogManager`, thiết lập formatter/level, quản lý vòng đời handler và kiểm tra đầu ra thực tế.

## 1. Vai trò trong kiến trúc JUL

Một luồng logging điển hình:

```text
Mã Java
   |
   | logger.log(Level.INFO, "...") / logger.info(...)
   v
java.util.logging.Logger
   | kiểm tra effective level, filter
   v
java.util.logging.LogRecord
   | có thể chuyển qua logger cha
   v
java.util.logging.FileHandler
   | kiểm tra level, filter của handler
   | Formatter -> chuỗi/bytes
   v
Tệp log trên ổ đĩa
```

`FileHandler` là lớp con của `StreamHandler`; nó quản lý luồng ghi và các tệp liên quan. Phần nội dung của mỗi record được định dạng bởi `Formatter`, ví dụ `SimpleFormatter` hoặc `XMLFormatter`. `FileHandler` không tự quyết định một sự kiện là `INFO` hay `SEVERE`: mức do mã phát log chỉ định; handler có thể loại record dựa trên ngưỡng.

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| `Logger` | Tiếp nhận yêu cầu ghi log và quyết định có tạo/chuyển event. | `Logger.getLogger("com.example.orders")` |
| `Level` | Mức của event và ngưỡng lọc tương ứng. | `INFO`, `FINE`, `WARNING` |
| `LogRecord` | Đối tượng mang level, message, logger name, parameters, Throwable và metadata. | Event `order.failed` có `Throwable` |
| `FileHandler` | Nhận record để ghi vào file, quản lý việc mở/đóng, khóa và rotation. | `new FileHandler("app.log", true)` |
| `Formatter` | Biến record thành text/XML theo định dạng. | `SimpleFormatter`, `XMLFormatter` |
| `Filter` | Chấp nhận hoặc từ chối event theo quy tắc bổ sung. | Chỉ nhận record của một nhóm sự kiện |
| `LogManager` | Đọc và quản lý cấu hình JUL. | `logging.properties` |

**Phân biệt:** `ConsoleHandler` ghi qua luồng console (thường stderr); `FileHandler` ghi vào tệp. Cả hai đều là handler của JUL, có thể được gắn đồng thời vào một logger. Một record đến nhiều handler có thể được xuất ra nhiều đích. Điều đó khác với **log trùng**, là cùng record xuất hiện nhiều lần không mong muốn tại một đích do cấu hình handler và propagation.

## 2. Khởi tạo và gắn FileHandler

Một số constructor thường gặp:

| Constructor JUL | Công dụng |
| --- | --- |
| `new FileHandler()` | Dùng cấu hình mặc định hoặc thuộc tính JUL từ `LogManager`, bao gồm pattern và các chính sách ghi. |
| `new FileHandler(String pattern)` | Dùng pattern được chỉ định; ghi mới theo chế độ mặc định. |
| `new FileHandler(String pattern, boolean append)` | Chọn rõ ghi nối tiếp (`true`) hay bắt đầu tệp mới (`false`) khi mở. |
| `new FileHandler(String pattern, int limit, int count)` | Giới hạn số byte mỗi tệp, số thế hệ luân phiên; dùng chế độ append mặc định. |
| `new FileHandler(String pattern, int limit, int count, boolean append)` | Đặt rõ pattern, giới hạn, số thế hệ và chế độ nối tiếp. |

Trên các JDK hiện đại có thêm overload nhận `long limit`; khi cần giới hạn trên phạm vi `int` hãy kiểm tra phiên bản JDK và API chính thức. Các ví dụ trong bài dùng overload phổ biến có sẵn trên JDK 17.

Tạo `FileHandler` có thể ném `IOException` (không mở/tạo/khóa được tệp), hoặc các lỗi đối số/cấu hình không hợp lệ. Thư mục cha của đường dẫn phải tồn tại và tiến trình cần đủ quyền ghi. Khi tạo handler thủ công, cần xem xét cách xử lý thất bại lúc khởi động thay vì cho rằng thao tác luôn thành công.

Ví dụ tối thiểu (đoạn minh họa trong một phương thức, giả sử `logger` đã được tạo):

```java
import java.io.IOException;
import java.util.logging.FileHandler;
import java.util.logging.Level;
import java.util.logging.SimpleFormatter;

void attachFileLogging(java.util.logging.Logger logger)
        throws IOException {
    FileHandler file = new FileHandler("application.log", true);
    file.setLevel(Level.INFO);
    file.setFormatter(new SimpleFormatter());
    logger.addHandler(file);
}
```

Đoạn trên chỉ minh họa cách gắn handler, **không phải lớp Java hoàn chỉnh để chạy độc lập**. Vì handler tiếp tục hoạt động sau khi phương thức trả về, ứng dụng phải quản lý tham chiếu và gọi `close()` đúng lúc, thường khi dừng service. Không tạo một `FileHandler` mới cho từng request: mỗi instance có luồng ghi/khóa riêng và có thể tạo nhiều file hoặc làm cạn tài nguyên.

## 3. Mẫu tên tệp: pattern và các ký hiệu thay thế

`FileHandler` nhận một chuỗi `pattern` để xác định tên tệp. JUL hỗ trợ các dấu thay thế:

| Ký hiệu | Ý nghĩa | Trường hợp sử dụng |
| --- | --- | --- |
| `%h` | Thư mục home của người dùng chạy tiến trình. | `%h/application.log` |
| `%t` | Thư mục tạm theo hệ thống/JVM. | `%t/myapp.log` |
| `%g` | Chỉ số thế hệ file khi luân phiên (*generation number*), bắt đầu từ 0. | `app.%g.log` |
| `%u` | Số phân biệt khi phải tránh xung đột tên/khóa file. | `app.%u.log` |
| `%%` | Ký tự `%` trong tên tệp. | `metrics-%%-service.log` |

Trong pattern của JUL, các ký hiệu là **quy tắc của FileHandler**, không phải biến môi trường shell và không phải placeholder message như `{0}`. `%g` và `%u` được tính theo cơ chế quản lý file; không dùng chúng để thay `requestId` hoặc mã phiên triển khai.

Một số ví dụ:

```text
%h/java-app.log
%t/java-app-%u.log
%h/logs/app-%u.%g.log
```

Nếu đặt pattern trong `%h/logs/app-%u.%g.log` thì cần **tạo trước thư mục `logs`** dưới home hoặc có cơ chế chuẩn bị thư mục khi triển khai. `FileHandler` không phải một hệ thống tự tạo toàn bộ cây thư mục theo ý người dùng.

Lưu ý:

- Với nhiều thế hệ luân phiên (`count > 1`), nếu pattern không chứa `%g`, triển khai JUL tự bổ sung phần generation vào tên theo quy tắc của nó. Dùng `%g` rõ ràng để giảm nhầm lẫn.
- Nếu một tên tệp bị chiếm bởi handler/process khác và cần tên duy nhất, `FileHandler` có thể thêm phần uniqueness khi không có `%u`. Không suy đoán tên chính xác khi có đồng thời nhiều JVM; chọn pattern chứa `%u` và xem kết quả thực tế.
- Một instance `FileHandler` sử dụng các tệp do nó quản lý, không phải hệ thống gom log giữa nhiều máy. Nếu container được thay thế, tệp trong filesystem cục bộ có thể không còn tồn tại trừ khi đã mount volume hoặc chuyển tiếp log ra hệ thống khác.
- Đặt log ở thư mục có quyền ghi, đủ dung lượng, phù hợp chính sách bảo mật và retention. Tránh đường dẫn chứa thông tin nhạy cảm.

## 4. Append, ghi đè và xử lý vòng đời

**`append=false`** nghĩa là khi mở handler, chế độ ghi sẽ bắt đầu lại tệp đích (thay nội dung tệp hiện có theo cơ chế FileHandler). **`append=true`** cho phép nối thêm vào dữ liệu hiện có khi mở tệp phù hợp. Điều này không thay thế chính sách rotation/retention và không bảo đảm dữ liệu được ghi bền vững trong mọi tình huống crash.

```java
// Mẫu minh họa, không phải chương trình độc lập.
FileHandler overwrite = new FileHandler("app.log", false);
FileHandler append = new FileHandler("another-app.log", true);
```

Hai handler trong ví dụ cố ý dùng **hai file khác nhau** để tránh tranh chấp khóa; phải đóng cả hai sau khi sử dụng. Không mở hai handler cho cùng tệp rồi kỳ vọng cả hai đồng thời ghi an toàn vào một luồng chung.

### Khi nào đóng handler?

- Khi ứng dụng thực sự dừng hoặc đổi cấu hình logging, gọi `close()` để flush, đóng luồng và giải phóng tài nguyên/khóa.
- Khi tháo handler khỏi một logger bằng `removeHandler(handler)`, điều đó **không tự đóng** handler; cần gọi `close()`.
- Với logging trong unit test hoặc demo, dùng `try/finally` để bảo đảm đóng handler kể cả khi xử lý lỗi.
- `flush()` đẩy nội dung đang đệm đến luồng đầu ra; `close()` còn đóng luồng/giải phóng tài nguyên. Không xem `flush()` đồng nghĩa với cam kết dữ liệu đã được fsync xuống thiết bị lưu trữ.
- Không gọi `close()` ngay sau mỗi record: như vậy tạo ra chi phí I/O, khóa và quản lý tệp không cần thiết; handler thường có vòng đời dài bằng service.

`FileHandler` có thể tạo tệp khóa với hậu tố `.lck` khi đang hoạt động để phối hợp tránh nhiều handler chiếm cùng tên file. Tệp lock thường được giải phóng khi đóng handler đúng cách. Khi tiến trình bị dừng đột ngột, có thể thấy dấu vết lock cũ; cần xem hành vi của phiên bản JDK và hệ thống tệp trước khi xóa hoặc tái sử dụng, nhất là trên filesystem dùng chung.

## 5. Giới hạn dung lượng và rotation

Rotation giúp tránh một file log tăng kích thước mãi mãi. Với constructor:

```java
// Giới hạn xấp xỉ 1 MiB/file, giữ 3 thế hệ.
// Đoạn mã minh họa, không phải chương trình độc lập.
FileHandler handler = new FileHandler(
        "app-%u.%g.log",
        1024 * 1024,
        3,
        true
);
```

- **`pattern`** quyết định cách đặt tên file cho các thế hệ và instance.
- **`limit`** là ngưỡng kích thước tệp tính theo **byte**, không phải số record và không phải số ký tự Unicode.
- **`count`** là số tệp thế hệ mà một handler có thể quản lý cho pattern đó; phải là số dương.
- **`append`** điều khiển cách xử lý nội dung tệp khi mở và có tác động đến trường hợp log cũ còn tồn tại.

Khi kích thước đạt ngưỡng, `FileHandler` tiến hành luân phiên, giữ một tập các thế hệ file được cấu hình. Với `app-%u.%g.log`, thế hệ `0` thường là file hiện đang ghi, các thế hệ có số cao hơn lưu dữ liệu trước đó. Khi hết `count`, dữ liệu cũ nhất có thể bị thay thế theo cơ chế rotation. Rotation của JUL là **theo dung lượng**, không tự chạy theo mốc mỗi ngày hoặc theo số ngày lưu.

**Những giới hạn cần hiểu:**

1. Ngưỡng `limit` không phải bảo đảm rằng kích thước cuối cùng *không bao giờ vượt* đúng số byte cấu hình: một record lớn có thể khiến file vượt ngưỡng trước khi rotation diễn ra.
2. `count=3` không có nghĩa giữ lịch sử trong ba ngày; nếu tải lớn, ba thế hệ có thể được thay rất nhanh.
3. `limit=0` có ý nghĩa không áp giới hạn dung lượng rotation theo size trong JUL; muốn tránh đầy đĩa vẫn cần chính sách của hệ thống.
4. Rotation khác **retention**: retention là quy tắc xóa/lưu giữ lâu dài theo thời gian, dung lượng tổng hoặc yêu cầu quản trị. `FileHandler` không cung cấp đầy đủ một hệ thống retention, nén lưu trữ, index hay chuyển log lên server.
5. Khi ứng dụng tạo nhiều instance hoặc nhiều JVM, mỗi handler có cơ chế khóa và tệp riêng; không suy ra được tổng số file toàn máy chỉ từ `count` của một handler.

Nếu môi trường cần rotation theo ngày, nén file cũ, xóa theo thời gian hoặc lưu ở object storage, cân nhắc công cụ log collector/log rotation phù hợp hoặc backend hỗ trợ nhiều chính sách hơn. Cần tránh để hai hệ thống luân phiên cùng một tệp mà không hiểu tương tác vì có thể gây mất record hoặc ghi vào file không mong muốn.

## 6. Formatter: nội dung file được ghi ra như thế nào?

Mặc định của `FileHandler` trong JUL thường là `XMLFormatter`, nên nội dung file có thể không phải các dòng text đơn giản mà là XML có cấu trúc `<log>...`. Muốn đọc bằng text editor/grep thuận tiện, có thể dùng `SimpleFormatter` hoặc formatter tùy chỉnh.

```java
// Mẫu minh họa trong phương thức có biến handler.
handler.setFormatter(new java.util.logging.SimpleFormatter());
```

`SimpleFormatter` ghi văn bản dễ đọc và hỗ trợ hiển thị thông tin `Throwable`; output có thể chứa timestamp, logger/source, level, message và stack trace, tùy cấu hình. Nếu ứng dụng cần JSON để lọc theo field, phải dùng formatter/encoder phù hợp (của thư viện hoặc code có kiểm chứng); đổi file extension sang `.json` không tự tạo JSON hợp lệ.

### Encoding

Trong môi trường đa ngôn ngữ, nên xác định encoding khi log tiếng Việt và khi collector đọc file:

```java
// Mẫu minh họa; có thể ném UnsupportedEncodingException.
handler.setEncoding("UTF-8");
```

Thiết lập encoding cần nhất quán với formatter và công cụ phân tích file. Hãy chọn trước khi ghi các record cần bảo toàn tiếng Việt; không giả định mọi hệ điều hành/JDK đều dùng cùng charset mặc định. Không ghép nội dung text/JSON thủ công nếu nguồn dữ liệu có ký tự điều khiển không đáng tin cậy.

### Log exception

Muốn giữ dấu vết lỗi trong file, truyền đối tượng `Throwable` cho logger bằng overload thích hợp:

```java
// Mẫu trong catch; giả sử logger đã tồn tại và ex là Throwable.
logger.log(
        java.util.logging.Level.SEVERE,
        "event=order.persist_failed orderId=ord-42",
        ex
);
```

`FileHandler` nhận `LogRecord` chứa `thrown`. Formatter quyết định có hiển thị stack trace/cause hay không; một formatter tự viết chỉ xuất `record.getMessage()` sẽ làm mất phần lỗi trong file, dù `Throwable` đã được truyền đúng. Với JUL, truyền một exception cho overload `log(Level, String, Throwable)` khác với truyền tham số của placeholder `{0}`.

## 7. Ví dụ Java 17 chạy độc lập: ghi file và kiểm tra đầu ra

Ví dụ này tạo một thư mục tạm riêng, ghi hai sự kiện vào file với formatter đơn giản, đóng handler, đọc file ra console rồi xóa file tạm. Không cần dependency ngoài JDK. Đường dẫn tạm thay đổi theo máy, nên chương trình chỉ in **nội dung log**, không in path.

Lưu tệp **`FileHandlerDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class FileHandlerDemo {
    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("jul-file-handler-");
        Path logFile = directory.resolve("application.log");

        Logger logger = Logger.getLogger(FileHandlerDemo.class.getName());
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.FINE);

        FileHandler file = new FileHandler(logFile.toString(), false);
        file.setEncoding(StandardCharsets.UTF_8.name());
        file.setLevel(Level.INFO);
        file.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " | " + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        logger.addHandler(file);

        try {
            logger.fine("job=42 internal-validation");
            logger.log(Level.INFO, "job={0} started", 42);
            logger.log(Level.WARNING, "job={0} fallback", 42);
        } finally {
            logger.removeHandler(file);
            file.close();
        }

        for (String line : Files.readAllLines(
                logFile, StandardCharsets.UTF_8)) {
            System.out.println(line);
        }

        Files.deleteIfExists(logFile);
        Files.deleteIfExists(directory);
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac FileHandlerDemo.java
java FileHandlerDemo
```

**Standard output chính xác khi chạy thành công:**

```text
INFO | job=42 started
WARNING | job=42 fallback
```

Giải thích:

1. `Files.createTempDirectory` tạo thư mục riêng nên không đụng tới file log sẵn có; `application.log` là tên cố định trong thư mục tạm.
2. `logger.setLevel(Level.FINE)` cho logger chấp nhận cả `FINE`, nhưng `file.setLevel(Level.INFO)` khiến handler loại event `FINE`. Đây là minh họa rằng **ngưỡng ở logger và handler là hai bước khác nhau**.
3. `formatMessage(record)` thay placeholder JUL `{0}` bằng `42`; formatter tạo một dòng `LEVEL | message` cho mỗi record và không thêm timestamp thay đổi theo máy.
4. `removeHandler(file)` tháo liên kết khỏi logger; `file.close()` flush/đóng luồng và trả lại khóa. Vì vậy ta có thể đọc file sau đó.
5. `Files.readAllLines(..., UTF_8)` đọc đúng hai dòng đã viết; vòng lặp in ra console nên ví dụ không phụ thuộc đường dẫn hay timestamp ở output.
6. `Files.deleteIfExists` dọn file và thư mục demo. `FileHandler` thường dọn tệp lock khi đóng; nếu lỗi file hoặc quyền xảy ra, chương trình có thể ném exception. Đây là ví dụ giảng dạy, không phải cấu hình quản lý log thực tế cho service.

**Không dùng** vòng lặp tạo handler mới cho mỗi message trong ứng dụng thật. Thường khai báo logger theo class, cấu hình handler tập trung một lần và đóng nó ở lifecycle shutdown. Khi chạy trong container hoặc môi trường ephemeral, cân nhắc sử dụng console logging cộng với collector thay vì phụ thuộc hoàn toàn vào tệp cục bộ.

## 8. Cấu hình FileHandler bằng logging.properties

Trong ứng dụng JUL thuần, có thể cấu hình handler bằng tệp `logging.properties`. Ví dụ dưới đây dùng thư mục home của user (thông qua `%h`) để tránh yêu cầu một thư mục con chưa được tạo:

```properties
# Root logger: nhận INFO trở lên.
.level=INFO

# Ghi qua FileHandler (có thể thêm ConsoleHandler nếu muốn).
handlers=java.util.logging.FileHandler

# Pattern tên file; số %u tránh tranh chấp, %g dành cho rotation.
java.util.logging.FileHandler.pattern=%h/myapp-%u.%g.log

# 1 MiB/file, ba thế hệ, nối tiếp khi mở.
java.util.logging.FileHandler.limit=1048576
java.util.logging.FileHandler.count=3
java.util.logging.FileHandler.append=true

# Handler nhận INFO trở lên, định dạng text và UTF-8.
java.util.logging.FileHandler.level=INFO
java.util.logging.FileHandler.formatter=java.util.logging.SimpleFormatter
java.util.logging.FileHandler.encoding=UTF-8
```

Có thể chỉ định tệp cấu hình cho JVM khi khởi động một class có sẵn:

```bash
java -Djava.util.logging.config.file=logging.properties com.example.Main
```

Lệnh trên **là minh họa**, giả định `com.example.Main` đã được biên dịch và nằm trên classpath. Nó không nhằm chạy `FileHandlerDemo` ở mục 7 vì demo tự tạo/cấu hình handler bằng code.

Khi dùng cấu hình, chú ý:

- JVM phải đọc đúng tệp cấu hình ngay từ đầu; nếu ứng dụng hoặc framework sau đó cấu hình lại JUL thì kết quả có thể khác.
- `.level` điều khiển root logger, còn `FileHandler.level` điều khiển chính handler. Một logger con có thể đặt level khác.
- Pattern, quyền ghi của home, dung lượng, chế độ append và tác dụng của `%g`/`%u` đều phải kiểm tra trên môi trường triển khai.
- `SimpleFormatter` cho output dạng text, không tự chuyển thành structured JSON.
- Nếu app đang dùng SLF4J/Logback làm backend, tệp `logging.properties` này **không tự quản lý file appender của Logback**. Kiểm tra logging backend thực tế để tránh cấu hình nhầm.
- Gắn đồng thời FileHandler qua root và thủ công vào một logger có `useParentHandlers=true` có thể khiến event đến nhiều handler; nếu cùng đích hoặc formatter giống nhau sẽ xuất log trùng.

## 9. Những tình huống triển khai cần cân nhắc

### File log trong container

Container có thể bị thay thế, nên file trong filesystem cục bộ không phải nơi lưu bền vững đáng tin cho lịch sử log. Nếu tổ chức dùng collector đọc stdout/stderr, việc ghi console có thể đơn giản và phù hợp hơn. Nếu thực sự cần FileHandler, phải thiết kế volume, quyền ghi, rotation và pipeline thu log rõ ràng; đặc biệt khi nhiều replica hoạt động đồng thời.

### Nhiều JVM hoặc nhiều instance

Không ép nhiều process cùng ghi vào một file path không có kế hoạch phối hợp. `FileHandler` dùng cơ chế khóa và uniqueness nhưng không biến một file thành log chung có bảo đảm thứ tự trên nhiều máy. Pattern có `%u` giúp giảm xung đột local; trong hệ thống phân tán, thường gắn metadata instance/pod và gửi đến hệ thống thu thập tập trung.

### Lỗi ổ đĩa hoặc quyền truy cập

Có hai loại lỗi khác nhau:

- **Lỗi mở/tạo file** khi khởi tạo `FileHandler`: có thể ném `IOException` hoặc lỗi liên quan. Cần chọn chính sách startup rõ ràng, ví dụ dừng khởi động nếu logging file là yêu cầu bắt buộc, hoặc chuyển sang console nếu được phép.
- **Lỗi ghi trong lúc chạy** (hết dung lượng, quyền thay đổi, filesystem gặp lỗi): một số lỗi trong handler có thể được báo qua `ErrorManager`; không giả định mọi lệnh `logger.info(...)` sẽ ném exception để code nghiệp vụ bắt được. Cần giám sát tình trạng pipeline và dung lượng.

Ứng dụng cần hệ thống audit đáng tin hoặc log không được mất phải có thiết kế lưu trữ/ghi bền riêng. Một `FileHandler` thông thường không bảo đảm rằng mọi record đã được lưu không thể mất sau crash hay mất điện.

### Retention và dữ liệu nhạy cảm

Rotation theo kích thước không trả lời câu hỏi file cần được giữ trong bao lâu. Tổ chức vẫn cần chính sách retention, dọn log cũ, backup nếu cần, quyền đọc/ghi, và kiểm soát dữ liệu nhạy cảm. Không log mật khẩu, token, cookie phiên hoặc payload cá nhân không cần thiết, kể cả khi file chỉ nằm trên máy nội bộ.

## 10. Các lỗi thường gặp khi dùng FileHandler

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra và sửa |
| --- | --- | --- |
| Không thấy file được tạo | Handler chưa gắn với logger, đường dẫn sai, thư mục cha không tồn tại hoặc không có quyền ghi. | Xác nhận `addHandler`/`handlers`, absolute path, quyền tạo file; bắt lỗi từ constructor. |
| File tồn tại nhưng trống | Logger hoặc handler đang loại level, filter chặn, chưa xuất/đóng, hoặc đọc nhầm file thực tế. | Kiểm tra `Logger.getLevel()`/effective level, `Handler.getLevel()`, filter, pattern và tên file. |
| File có XML, không phải dòng text mong đợi | `FileHandler` dùng `XMLFormatter` hoặc formatter được cấu hình khác. | Chọn `SimpleFormatter` hoặc formatter thích hợp và đối chiếu lại file. |
| File bị xóa nội dung cũ khi khởi động | Mở với `append=false` hoặc thay thế do rotation. | Đánh giá chế độ append, pattern và giới hạn count/limit trước khi thay đổi. |
| Nhiều file có hậu tố lạ | Có generation/uniqueness hoặc cạnh tranh tên file. | Kiểm tra `%g`, `%u`, số handler/process và lock file. |
| Một sự kiện xuất hiện nhiều lần | Gắn handler ở nhiều cấp logger và truyền lên cha; hoặc cấu hình cả root và logger con. | Kiểm tra `useParentHandlers`, handler đã gắn và các sink. |
| File tăng quá lớn | `limit=0`, không rotation phù hợp, lượng log quá cao. | Thiết lập ngưỡng và số thế hệ, quản lý retention/dung lượng. |
| Không tìm được cause/stack trace | Formatter chỉ in `message` hoặc code chỉ gọi `getMessage()` của exception. | Truyền `Throwable` đúng API và kiểm tra formatter/pipeline. |
| Log tiếng Việt bị lỗi dấu | Encoding ghi và encoding đọc khác nhau. | Cấu hình UTF-8 và bảo đảm collector/reader sử dụng đúng charset. |
| Lúc shutdown mất một số log | Handler chưa flush/close, tiến trình chết đột ngột hoặc logging bất đồng bộ khác trong pipeline. | Đóng handler đúng lifecycle; hiểu giới hạn về độ bền dữ liệu. |
| Hai ứng dụng tranh chấp file | Dùng chung pattern cục bộ và quản lý khóa/uniqueness chưa đúng. | Dùng thư mục/file per instance hoặc collector tập trung; không ép dùng một file. |

## 11. Checklist trước khi dùng trong ứng dụng thật

1. **Mục đích:** Có cần log vào tệp không, hay console + collector phù hợp hơn?
2. **Đường dẫn:** Pattern rõ ràng, thư mục tồn tại, có quyền ghi và không có dữ liệu nhạy cảm trong tên tệp?
3. **Quy mô:** Giới hạn tính theo byte, số thế hệ và chiến lược retention có đủ với lưu lượng thật?
4. **Chế độ mở:** `append` và hành vi restart có đúng mong đợi, đặc biệt với file đã tồn tại?
5. **Cấu hình:** Ngưỡng logger và handler, filter, propagation, formatter, charset đã được kiểm tra?
6. **Ngoại lệ:** `Throwable` có được đính kèm record và formatter có xuất cause/stack trace khi cần?
7. **Vòng đời:** Handler được dùng lại, đóng khi shutdown và không bị tạo lặp qua mỗi request?
8. **Vận hành:** Có quan sát dung lượng, lỗi ghi và tác động I/O lên luồng xử lý không?
9. **An toàn:** Quyền truy cập, backup/xóa, mask dữ liệu, chính sách retention và filesystem của container đã được tính đến?
10. **QA:** Đã thử khởi động lại, rotation, đồng thời nhiều instance, lỗi quyền ghi và đầu ra thực tế trên môi trường gần production?

**Ghi nhớ:** `FileHandler` đảm nhiệm **ghi LogRecord ra tệp, quản lý tên file và rotation**; `Logger` và `Handler` cùng quyết định record nào được nhận; `Formatter` quyết định thông tin được ghi ra. Cấu hình đúng phải xét cả vòng đời, dung lượng và điều kiện vận hành, thay vì chỉ gọi `new FileHandler(...)`.