# Console và file log trong Java

## 1. Console log và file log là gì?

Logging là việc ghi lại các sự kiện trong quá trình chương trình chạy để theo dõi trạng thái, tìm nguyên nhân lỗi và hỗ trợ vận hành. Một sự kiện log thường có **mức độ** (level), **thời điểm**, **nguồn phát sinh** (logger/class), **thông điệp** và đôi khi có **exception/stack trace**.

Hai đích xuất log phổ biến:

- **Console log**: ghi lên luồng đầu ra của tiến trình, thường là `stdout` hoặc `stderr`. Người chạy ứng dụng nhìn thấy trong terminal; Docker, systemd hay nền tảng triển khai cũng có thể thu thập các luồng này.
- **File log**: ghi vào tệp trên ổ đĩa, ví dụ `logs/app.0.log`, để đọc lại sau khi phiên terminal kết thúc. Cần quan tâm đường dẫn, dung lượng, xoay vòng tệp và quyền ghi.

Một sự kiện có thể được ghi **đồng thời ra cả console lẫn file**. Trong Java 17+, thư viện có sẵn `java.util.logging` (JUL) thực hiện điều này qua ba thành phần:

```text
Logger (tạo sự kiện, kiểm tra level)
  ├── ConsoleHandler (lọc level, định dạng) → System.err
  └── FileHandler    (lọc level, định dạng) → file trên đĩa
```

`Logger` quyết định sự kiện có được phát đi hay không; mỗi `Handler` lại có bộ lọc level riêng và một `Formatter` để biến sự kiện thành văn bản. Vì vậy muốn thấy `FINE` trong file, cả `Logger` **và** `FileHandler` phải cho phép `FINE`.

## 2. Chọn console hay file

| Tiêu chí | Console log | File log |
| --- | --- | --- |
| Đích ghi | `stdout`/`stderr` của tiến trình | Tệp trong hệ thống tệp |
| Quan sát trực tiếp | Thuận tiện khi chạy bằng IDE/terminal | Cần mở, tìm kiếm hoặc đọc tệp |
| Lưu giữ | Tùy terminal hoặc hệ thống thu thập log | Tồn tại theo vòng đời tệp và chính sách lưu trữ |
| Vận hành container | Thường phù hợp vì nền tảng thu thập luồng chuẩn | Cần volume bền vững hoặc công cụ chuyển tiếp nếu muốn giữ lâu |
| Rủi ro cần quản lý | Log bị trôi, khó tìm lại nếu không được thu thập | Đầy đĩa, thiếu quyền ghi, tệp quá lớn, trùng lặp dữ liệu |

Không dùng `System.out.println(...)` làm cơ chế logging chính cho ứng dụng: lời gọi này không có level, bộ lọc, formatter hoặc cơ chế xoay vòng tệp. `System.out` vẫn phù hợp cho **kết quả nghiệp vụ của chương trình dòng lệnh**; logging nên đi qua API logging. Riêng `ConsoleHandler` của JUL mặc định ghi vào **`System.err`**, dù màn hình terminal thường hiển thị cả hai luồng.

## 3. Ví dụ Java 17: ghi đồng thời ra console và file

Tạo tệp `ConsoleFileLoggingDemo.java`:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.logging.ConsoleHandler;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ConsoleFileLoggingDemo {
    private static final Logger LOG =
            Logger.getLogger(ConsoleFileLoggingDemo.class.getName());

    public static void main(String[] args) throws IOException {
        Files.createDirectories(Path.of("logs"));

        // Không chuyển tiếp lên handler của logger cha,
        // tránh cùng một sự kiện xuất hiện hai lần.
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        // Formatter ngắn để kết quả ví dụ dễ đối chiếu.
        Formatter format = new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " | "
                        + formatMessage(record) + System.lineSeparator();
            }
        };

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.INFO);
        console.setFormatter(format);

        // 1 MiB/tệp, tối đa 3 thế hệ, nối tiếp nội dung khi chạy lại.
        FileHandler file =
                new FileHandler("logs/app.%g.log", 1_048_576, 3, true);
        file.setLevel(Level.FINE);
        file.setFormatter(format);
        file.setEncoding("UTF-8");

        LOG.addHandler(console);
        LOG.addHandler(file);

        try {
            LOG.info("Application started");
            LOG.fine("Loaded application configuration");
            LOG.warning("Cache is nearly full");
        } finally {
            LOG.removeHandler(console);
            LOG.removeHandler(file);
            console.close();
            file.close();
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac ConsoleFileLoggingDemo.java
java ConsoleFileLoggingDemo
```

**Kết quả trên console (luồng stderr)** khi chạy chương trình:

```text
INFO | Application started
WARNING | Cache is nearly full
```

**Nội dung mới ghi vào `logs/app.0.log`** khi chạy lần đầu với thư mục `logs` chưa có log cũ:

```text
INFO | Application started
FINE | Loaded application configuration
WARNING | Cache is nearly full
```

Có thể xem file bằng `cat logs/app.0.log` trên Linux/macOS hoặc `Get-Content logs/app.0.log` trong PowerShell. Với `append=true`, lần chạy sau **nối thêm** bản ghi vào file hiện tại; nội dung file lúc đó có thể chứa các lần chạy trước. Nếu file đạt giới hạn và bị xoay vòng, bản ghi cũ có thể nằm ở thế hệ khác. Khi có nhiều tiến trình cùng tranh tên file, JUL có thể tự thêm hậu tố duy nhất vào tên.

**Giải thích từng quyết định:**

1. `Files.createDirectories(...)` tạo thư mục đích trước khi mở `FileHandler`; thiếu thư mục hoặc thiếu quyền ghi có thể khiến handler khởi tạo thất bại.
2. `LOG.setLevel(Level.ALL)` cho phép logger phát cả `FINE`, nhưng `console.setLevel(Level.INFO)` chỉ hiển thị `INFO` trở lên; `file.setLevel(Level.FINE)` vẫn nhận `FINE`.
3. `setUseParentHandlers(false)` ngăn sự kiện đi lên root logger và gây log trùng khi ứng dụng tự gắn handler như ví dụ.
4. `Formatter` ở đây cố tình bỏ timestamp để đầu ra ổn định, dễ học. Ứng dụng thực tế nên có thời gian, level, tên logger, ngữ cảnh và cách thể hiện exception.
5. Gọi `close()` ở `finally` để flush và giải phóng tài nguyên, kể cả khóa tệp do `FileHandler` sử dụng. Đối với ứng dụng chạy dài, giữ handler sống đến khi tắt ứng dụng thay vì tạo handler cho mỗi thông điệp.

Không gọi `new FileHandler(...)` trong mỗi request hoặc trong vòng lặp ghi log: điều đó tốn tài nguyên, tạo nhiều khóa tệp và có thể làm log bị phân tán.

## 4. Level quyết định log nào tới từng đích

Các mức thông dụng của JUL, từ nghiêm trọng đến chi tiết:

| Level | Cách dùng điển hình |
| --- | --- |
| `SEVERE` | Lỗi nghiêm trọng, thao tác không thể hoàn tất |
| `WARNING` | Bất thường đáng quan tâm nhưng chương trình có thể tiếp tục |
| `INFO` | Sự kiện vận hành quan trọng: khởi động, kết nối, hoàn tất thao tác |
| `CONFIG` | Thông tin cấu hình có ích khi chẩn đoán |
| `FINE`, `FINER`, `FINEST` | Thông tin kỹ thuật ngày càng chi tiết khi debug |

`ALL` cho phép mọi level; `OFF` vô hiệu hóa. Mức thấp hơn ngưỡng của **logger** sẽ không tạo sự kiện để handler xử lý. Mức thấp hơn ngưỡng của **handler** sẽ bị loại ở riêng đích đó.

Ví dụ: logger = `ALL`, console = `INFO`, file = `FINE` thì một bản ghi `FINE` chỉ có trong file. Nếu đổi logger thành `INFO`, bản ghi `FINE` **không xuất hiện ở đâu**, dù file handler vẫn đặt `FINE`. Mỗi handler còn có thể có `Filter` riêng.

Khi cần ghi lỗi kèm stack trace, dùng overload nhận exception:

```java
try {
    int port = Integer.parseInt("not-a-number");
} catch (NumberFormatException ex) {
    LOG.log(Level.SEVERE, "Invalid port configuration", ex);
}
```

Đoạn trên minh họa cách ghi exception **bên trong class đã khai báo `LOG` ở ví dụ trước**. Với formatter tùy biến ở mục 3, stack trace **chưa được in** vì formatter chỉ lấy level và message. Để hiển thị exception trong ứng dụng thực tế, dùng `SimpleFormatter` hoặc formatter tùy biến đọc `record.getThrown()` và in stack trace. Bản thân `LOG.log(..., ex)` vẫn lưu exception trong `LogRecord`.

## 5. Cấu hình bằng logging.properties

Với JUL, có thể thay đổi handler và level bằng file cấu hình khi khởi động JVM thay vì sửa mã mỗi lần. Đây là **một chương trình khác, độc lập với ví dụ tạo handler bằng code ở mục 3**.

Tạo `ConfiguredLoggingDemo.java`:

```java
import java.util.logging.Logger;

public class ConfiguredLoggingDemo {
    private static final Logger LOG =
            Logger.getLogger(ConfiguredLoggingDemo.class.getName());

    public static void main(String[] args) {
        LOG.info("Service started");
        LOG.fine("Configuration details loaded");
        LOG.warning("Cache nearing capacity");
    }
}
```

Tạo file `logging.properties` trong cùng thư mục:

```properties
handlers=java.util.logging.ConsoleHandler,java.util.logging.FileHandler
.level=INFO

java.util.logging.ConsoleHandler.level=INFO
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter

java.util.logging.FileHandler.level=FINE
java.util.logging.FileHandler.pattern=logs/configured.%g.log
java.util.logging.FileHandler.limit=1048576
java.util.logging.FileHandler.count=3
java.util.logging.FileHandler.append=true
java.util.logging.FileHandler.encoding=UTF-8
java.util.logging.FileHandler.formatter=java.util.logging.SimpleFormatter

ConfiguredLoggingDemo.level=FINE
```

Trước khi chạy, **tạo sẵn thư mục `logs`** vì `FileHandler` cấu hình được khởi tạo trong quá trình nạp cấu hình logging. Sau đó:

```bash
javac ConfiguredLoggingDemo.java
java -Djava.util.logging.config.file=logging.properties ConfiguredLoggingDemo
```

`SimpleFormatter` mặc định có timestamp, tên logger, level và có thể in stack trace; **không so sánh nguyên văn output** với ví dụ formatter ngắn ở mục 3. Kết quả logic vẫn là: console có `INFO`, `WARNING`; file có thêm `FINE`. Đường dẫn file cấu hình trong tham số `-Djava.util.logging.config.file` được JVM đọc khi khởi tạo cơ chế logging; đường dẫn tương đối tính từ thư mục làm việc hiện tại.

Chỉ chọn **một cách sở hữu cấu hình** cho ví dụ đang chạy: nếu vừa khởi tạo handler từ code vừa khai báo handler qua cấu hình, cần hiểu rõ logger cha và cơ chế truyền bản ghi để tránh trùng log. Với dự án có Spring Boot hoặc SLF4J/Logback, cấu hình thực tế do backend logging của dự án quyết định; không mặc nhiên áp dụng mọi khóa cấu hình JUL cho Logback.

## 6. Xoay vòng file, định dạng và nơi lưu

**Rotation (xoay vòng)** giữ cho một file không phình lên vô hạn. Với `FileHandler("logs/app.%g.log", 1_048_576, 3, true)`:

- `pattern` là mẫu tên; `%g` là số thế hệ, ví dụ `app.0.log`, `app.1.log`, `app.2.log`.
- `limit` giới hạn kích thước khoảng 1 MiB cho mỗi file trước khi xoay.
- `count=3` giữ tối đa ba thế hệ trong cơ chế xoay vòng này; bản ghi cũ có thể bị ghi đè khi quay vòng.
- `append=true` tiếp tục ghi vào file có sẵn nếu có thể; khác với chế độ ghi mới từ đầu.

JUL `FileHandler` **xoay theo dung lượng**, không tự cung cấp chính sách giữ theo ngày, nén file lâu ngày hoặc đẩy log lên hệ thống tập trung. Các nhu cầu đó cần cấu hình công cụ vận hành hoặc backend logging thích hợp. Tránh đặt file log vào thư mục source hoặc commit log vào Git; dùng thư mục triển khai có quyền ghi và chính sách lưu trữ rõ ràng.

**Định dạng:** `FileHandler` JUL mặc định thường dùng `XMLFormatter` nếu không cấu hình formatter; người đọc có thể ngạc nhiên vì file không phải dòng text đơn giản. Chọn `SimpleFormatter` hoặc formatter phù hợp nhu cầu đọc/truy vấn. Timestamp nên có múi giờ hoặc dùng định dạng nhất quán như ISO 8601. Khi chạy đa luồng/đa máy, timestamp và thứ tự log không bảo đảm tự phản ánh chính xác toàn bộ quan hệ nhân quả; thêm request/correlation ID khi cần truy vết.

**Console trong môi trường triển khai:** ưu tiên chuyển log ứng dụng tới luồng chuẩn và để nền tảng thu thập/tập trung hóa khi triển khai container. Nếu đồng thời xuất console và file, xác định nơi nào là nguồn lưu giữ chính để tránh thu thập hai lần hoặc lưu file cục bộ rồi mất khi container bị thay thế.

## 7. Lỗi thường gặp và cách kiểm tra

| Triệu chứng | Nguyên nhân có thể xảy ra | Cách xử lý |
| --- | --- | --- |
| Một sự kiện hiện hai lần trên console | Handler của logger hiện tại và logger cha đều xuất bản ghi | Kiểm tra `setUseParentHandlers(false)` hoặc cấu hình chuỗi logger/handler |
| Log `FINE` không xuất hiện trong file | Logger hoặc file handler đặt ngưỡng `INFO` | Kiểm tra **cả hai** level và các filter |
| Không tạo được file | Thư mục chưa tồn tại, không đủ quyền, đường dẫn sai | Tạo thư mục, xác nhận đường dẫn theo working directory, xem lỗi khởi tạo |
| File có XML thay vì text | Dùng `XMLFormatter` mặc định | Cấu hình `SimpleFormatter`/formatter mong muốn |
| File chứa nhiều bản ghi từ lần chạy trước | `append=true` | Đây là hành vi dự kiến; kiểm tra rotation và chính sách retention |
| File log đầy đĩa | Không giới hạn dung lượng/số thế hệ, không giám sát | Thiết lập rotation, retention và cảnh báo dung lượng |
| Có lời gọi `LOG.log(..., ex)` nhưng không thấy stack trace | Formatter tùy biến bỏ qua `getThrown()` | Dùng formatter hỗ trợ exception |
| Log biến mất khi container bị thay thế | File nằm trong hệ thống tệp tạm của container | Thu thập `stdout`/`stderr` hoặc cấu hình lưu trữ bền vững |

Khi debug vấn đề logging, kiểm tra tuần tự: **logger name → logger level → useParentHandlers → handler được gắn → handler level/filter → formatter → đường dẫn/quyền ghi → hệ thống thu thập log**. Cách này giúp phân biệt bản ghi bị lọc, bản ghi được định dạng khác dự kiến và lỗi thật sự ở đích ghi.

## 8. Thực hành tốt

- Dùng `INFO` cho trạng thái quan trọng, `WARNING` cho bất thường, `SEVERE` cho lỗi; chỉ bật `FINE/FINER/FINEST` khi cần chẩn đoán để hạn chế dung lượng và nhiễu.
- **Không ghi mật khẩu, token, khóa API, dữ liệu cá nhân nhạy cảm** hoặc toàn bộ request/response chứa thông tin bí mật; lọc hoặc che dữ liệu trước khi log.
- Log exception với đối tượng `Throwable` và formatter hỗ trợ stack trace; đừng chỉ ghi `ex.getMessage()` nếu cần tìm gốc lỗi.
- Chọn tên logger theo class/package để cấu hình mức độ chi tiết cho từng khu vực; hạn chế trộn lẫn `System.out.println` với hệ thống logger.
- Đặt chính sách rotation, retention, quyền truy cập và nơi thu thập log trước khi triển khai; quan sát cả lỗi ghi log vì log có thể mất khi đĩa đầy.
- Kiểm tra thực tế **cả hai đích**: sự kiện nào có trên console, sự kiện nào có trong file, định dạng có đủ ngữ cảnh không và exception có giữ stack trace không.

**Điểm cần nhớ:** Console và file là hai **đích nhận** của cùng sự kiện logging. Kết hợp `Logger`, level, `Handler` và `Formatter` cho phép điều khiển nội dung mỗi đích mà không phải nhân đôi các lời gọi log trong mã nguồn.
