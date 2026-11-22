# Nhà cung cấp mặc định cùng java.util.logging

`System.Logger` là facade logging được Java cung cấp từ Java 9. Code ứng dụng hoặc thư viện có thể gọi `System.getLogger(name)` mà không phụ thuộc trực tiếp vào một framework logging cụ thể. Việc tạo logger và chuyển log record đến backend do dịch vụ `System.LoggerFinder` đảm nhiệm.

Khi module `java.logging` hiện diện và không có provider `LoggerFinder` tùy chỉnh, provider mặc định dùng `java.util.logging` (JUL) làm backend. Log từ `System.Logger` khi đó được chuyển đến một `java.util.logging.Logger` tương ứng. JUL chịu trách nhiệm lọc mức log, quản lý logger hierarchy, gửi record qua Handler và định dạng đầu ra.

Nếu runtime không có module `java.logging`, provider mặc định dùng simple logger ghi các mức INFO trở lên ra `System.err`. Nếu ứng dụng cài một provider `LoggerFinder` tùy chỉnh, provider đó được dùng thay provider mặc định. Vì vậy, không nên giả định mọi runtime đều dùng JUL; cần biết module và provider thực tế của ứng dụng.

## 1. Vai trò của System.Logger và LoggerFinder

Có ba phần cần phân biệt:

| Thành phần | Vai trò |
|---|---|
| `System.Logger` | API facade để code gửi log message theo các level chuẩn của Java |
| `System.LoggerFinder` | Service Provider Interface (SPI) tạo logger và kết nối facade với backend |
| `java.util.logging` | Backend mặc định trên runtime có module `java.logging`, quản lý log record, level, handler và formatter |

Lấy logger bằng API Java 9:

```java
System.Logger logger = System.getLogger("com.example.payment");
logger.log(System.Logger.Level.INFO, "Payment accepted");
```

Tên logger thường phản ánh package hoặc thành phần ứng dụng. Các logger có tên phân cấp bằng dấu chấm, ví dụ `com.example` và `com.example.payment`, giúp cấu hình mức log theo từng vùng chức năng.

`System.Logger` thuộc module `java.base` nên có thể dùng mà không cần import JUL. Nếu code trực tiếp cấu hình hoặc gọi các class trong `java.util.logging`, module ứng dụng cần đọc module `java.logging`.

Trong named module:

```java
module com.example.app {
    requires java.logging;
}
```

Nếu ứng dụng chỉ gọi `System.getLogger` và không tham chiếu trực tiếp JUL, không cần khai báo `requires java.logging` chỉ để dùng facade. Tuy vậy, provider mặc định vẫn có thể sử dụng JUL nếu module logging hiện diện trong runtime.

## 2. Provider mặc định chọn backend nào?

Quy trình chọn provider của một Java Runtime:

1. Runtime tìm provider `System.LoggerFinder` do ứng dụng hoặc môi trường triển khai cung cấp bằng cơ chế `ServiceLoader` với system class loader.
2. Nếu tìm thấy provider phù hợp, provider đó tạo các logger và định tuyến message đến backend mà nó hỗ trợ.
3. Nếu không có provider tùy chỉnh, runtime dùng default LoggerFinder.
4. Default LoggerFinder dùng JUL khi module `java.logging` có mặt.
5. Nếu `java.logging` không có mặt, default implementation dùng simple logger ghi các message từ INFO trở lên ra `System.err`.

Một runtime chuẩn thường có module `java.logging`. Tuy nhiên, runtime tối giản được tạo bằng `jlink` có thể loại module này nếu ứng dụng không cần nó. Khi đó, hành vi của default logger thay đổi sang simple logger; các cấu hình JUL như Handler hay `logging.properties` sẽ không điều khiển logger đó.

Default LoggerFinder là lựa chọn mặc định, không phải cam kết rằng mọi ứng dụng Java đều dùng JUL. Ứng dụng có thể thay thế nó bằng một provider khác, kể cả khi module `java.logging` vẫn có mặt.

## 3. Ánh xạ System.Logger.Level sang JUL Level

`System.Logger.Level` định nghĩa bảy mức chuẩn. Default LoggerFinder chuyển các mức này sang mức có severity tương ứng của `java.util.logging.Level`:

| System.Logger.Level | java.util.logging.Level | Ý nghĩa thường dùng |
|---|---|---|
| `ALL` | `ALL` | Bật mọi mức |
| `TRACE` | `FINER` | Thông tin truy vết chi tiết |
| `DEBUG` | `FINE` | Thông tin phục vụ debug |
| `INFO` | `INFO` | Sự kiện thông thường |
| `WARNING` | `WARNING` | Tình huống bất thường cần chú ý |
| `ERROR` | `SEVERE` | Lỗi cần xử lý |
| `OFF` | `OFF` | Tắt logging |

Mức JUL có thứ tự severity riêng. Một handler hoặc logger chỉ phát record khi mức của record đủ nghiêm trọng so với ngưỡng cấu hình. Vì `TRACE` ánh xạ sang `FINER` và `DEBUG` ánh xạ sang `FINE`, cấu hình JUL chỉ bật INFO sẽ không hiển thị hai mức này.

`ALL` và `OFF` là các marker ở hai đầu dải severity. Chúng chủ yếu dùng để cấu hình ngưỡng; không nên xem `OFF` như một mức message thông thường cần ghi.

## 4. Đường đi của một log message trong JUL

Khi default LoggerFinder chuyển một lời gọi `System.Logger` sang JUL, message đi qua các thành phần sau:

1. `Logger` nhận yêu cầu ghi log và kiểm tra mức hiệu lực.
2. Nếu được bật, logger tạo hoặc chuyển tiếp một `LogRecord` chứa level, message, logger name, thời gian, thread và exception nếu có.
3. Record được chuyển đến các `Handler` gắn với logger.
4. Nếu logger cho phép truyền lên parent, record tiếp tục đến handler của logger cha và root logger.
5. Handler kiểm tra level riêng, sau đó dùng `Formatter` để chuyển record thành văn bản hoặc định dạng khác.
6. Handler xuất dữ liệu đến đích như console hoặc file.

Các thành phần chính:

- `Logger`: đặt tên, phân cấp, mức hiệu lực và quan hệ parent.
- `Level`: xác định mức độ nghiêm trọng.
- `LogRecord`: gói dữ liệu của một sự kiện log.
- `Handler`: xuất record đến console, file hoặc đích khác.
- `Formatter`: định dạng record thành văn bản hoặc XML.
- `Filter`: áp dụng điều kiện bổ sung để chấp nhận hoặc loại record.
- `LogManager`: quản lý cấu hình và tập logger dùng chung.

Logger level và Handler level là hai bộ lọc riêng. Một record có thể vượt qua logger level nhưng vẫn bị handler loại bỏ. Để bật DEBUG/TRACE, cần kiểm tra cả level của logger lẫn level của handler nhận record.

## 5. Ví dụ Java 17: System.Logger dùng backend JUL mặc định

Chương trình sau cấu hình root logger và console handler để hiển thị mọi mức. Formatter được thay bằng formatter ngắn để đầu ra console có thể kiểm tra chính xác. Chương trình dùng `System.Logger` để ghi log; nó không gọi `java.util.logging.Logger` trực tiếp để phát message.

**Main.java**

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.LogManager;
import java.util.logging.Logger;

public class Main {
    public static void main(String[] args) {
        Logger root = LogManager.getLogManager().getLogger("");
        root.setLevel(Level.ALL);

        for (Handler handler : root.getHandlers()) {
            root.removeHandler(handler);
        }

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.ALL);
        console.setFormatter(new java.util.logging.Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + ": "
                        + formatMessage(record) + System.lineSeparator();
            }
        });
        root.addHandler(console);

        System.Logger logger = System.getLogger("example.service");

        logger.log(System.Logger.Level.TRACE, "trace message");
        logger.log(System.Logger.Level.DEBUG, "debug message");
        logger.log(System.Logger.Level.INFO, "info message");
        logger.log(System.Logger.Level.WARNING, "warning message");
        logger.log(System.Logger.Level.ERROR, "error message");
        logger.log(System.Logger.Level.INFO, "processed {0} records", 3);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 -Xlint:all Main.java
java Main
```

Kết quả console (ConsoleHandler mặc định ghi ra `System.err`):

```text
FINER: trace message
FINE: debug message
INFO: info message
WARNING: warning message
SEVERE: error message
INFO: processed 3 records
```

Kết quả thể hiện default provider đã định tuyến `System.Logger` đến JUL: TRACE xuất hiện dưới tên level FINER, DEBUG thành FINE, ERROR thành SEVERE. Lời gọi có tham số dùng định dạng `MessageFormat`, vì vậy `{0}` được thay bằng giá trị 3.

Ví dụ cấu hình root và handler ở mức ALL để minh họa đầy đủ mapping. Cấu hình production thường không bật mọi mức vì TRACE/DEBUG có thể tạo lượng log lớn.

## 6. Vì sao đặt logger level và handler level đều quan trọng?

Giả sử root logger có level INFO nhưng ConsoleHandler có level ALL:

- TRACE/FINER và DEBUG/FINE bị loại ngay tại logger.
- INFO, WARNING và SEVERE có thể tiếp tục đến handler.
- Handler không thể khôi phục record đã bị logger loại.

Ngược lại, nếu root logger là ALL nhưng ConsoleHandler đặt INFO:

- Logger cho phép record ở mọi mức.
- Handler loại FINER và FINE.
- Chỉ INFO trở lên được xuất ra console.

Để thấy TRACE và DEBUG, cả đường logger lẫn handler đều phải cho phép các mức tương ứng. Ví dụ ở phần trước đặt cả hai thành ALL.

Logger con có thể có level riêng. Nếu level của logger con được đặt tường minh, mức đó được dùng cho logger con; nếu để null, logger kế thừa mức hiệu lực từ parent. Khi `useParentHandlers` là true (mặc định), record được chuyển tiếp đến handler của parent sau khi qua logger con.

Không nên thêm cùng một ConsoleHandler vào cả logger con và root nếu không muốn cùng record xuất hiện hai lần qua hai handler khác nhau.

## 7. Cấu hình JUL bằng logging.properties

Ứng dụng có thể cấu hình JUL từ file properties khi khởi động. Ví dụ:

**logging.properties**

```properties
handlers=java.util.logging.ConsoleHandler
.level=INFO

java.util.logging.ConsoleHandler.level=ALL
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter

com.example.level=FINE
```

Khởi chạy:

```bash
java -Djava.util.logging.config.file=logging.properties -cp out Main
```

Trong ví dụ:

- `.level=INFO` đặt mức mặc định cho root logger.
- `java.util.logging.ConsoleHandler.level=ALL` cho handler nhận mọi mức mà logger chuyển tới.
- `com.example.level=FINE` bật DEBUG/FINE cho logger thuộc nhánh `com.example`.
- Các logger khác tiếp tục kế thừa mức INFO của root nếu không có cấu hình riêng.

`LogManager` đọc cấu hình ban đầu từ file được chỉ định bởi system property `java.util.logging.config.file`. Nếu không chỉ định, JUL thường dùng file `conf/logging.properties` trong Java runtime. Có thể dùng `java.util.logging.config.class` để cung cấp lớp tự khởi tạo cấu hình thay cho file properties.

Trong ứng dụng cần thay đổi cấu hình lúc chạy, JUL có API quản lý tương ứng. Tuy nhiên, thư viện dùng `System.Logger` nên để ứng dụng chủ quản cấu hình backend; thư viện không nên tự ý thay đổi root logger hoặc cài handler toàn cục.

## 8. Khi nào cần LoggerFinder tùy chỉnh?

Nếu ứng dụng muốn gửi log đến backend khác, ví dụ một logging framework đã được tổ chức chọn, có thể cung cấp implementation của `System.LoggerFinder`.

Provider cần:

- Kế thừa `System.LoggerFinder`.
- Có constructor không tham số phù hợp để ServiceLoader tạo instance.
- Triển khai các factory method để trả về logger cho tên và module được yêu cầu.
- Trả về logger có thể chuyển các lời gọi `System.Logger` sang backend tương ứng.
- Ánh xạ `System.Logger.Level` sang các mức mà backend hỗ trợ.

Trong named module, khai báo provider bằng directive `provides`:

```java
module com.example.logging.provider {
    provides java.lang.System.LoggerFinder
        with com.example.logging.CustomLoggerFinder;
}
```

Provider cũng có thể được khai báo theo cơ chế service configuration khi triển khai trên class path. Runtime tìm provider bằng `ServiceLoader`; nếu không tìm thấy provider tùy chỉnh thì mới dùng default LoggerFinder.

Một runtime duy trì một LoggerFinder system-wide. Do đó, lựa chọn provider ảnh hưởng đến các logger hệ thống trong runtime, không chỉ riêng một class. Việc cài provider cần được thực hiện có chủ đích ở cấp ứng dụng hoặc môi trường chạy.

Không nên viết LoggerFinder tùy chỉnh chỉ để đổi định dạng console. JUL đã hỗ trợ Handler và Formatter. Hãy cân nhắc provider mới khi thật sự cần tích hợp backend hoặc chính sách logging khác.

## 9. System.Logger và JUL: nên dùng API nào?

| Nhu cầu | API phù hợp |
|---|---|
| Thư viện hoặc code muốn tránh phụ thuộc backend | `System.Logger` |
| Ứng dụng dùng JUL làm backend và cần cấu hình logger/handler | `java.util.logging` |
| Ứng dụng muốn backend khác cho System.Logger | Cung cấp `System.LoggerFinder` |
| Chỉ cần ghi message theo level | `System.Logger` là đủ |
| Cần tạo Handler, Formatter, Filter hoặc thay LogManager configuration | JUL API |

Một thư viện thường nên gọi `System.getLogger` và không tự cài đặt cấu hình logging toàn cục. Nhờ vậy ứng dụng có thể chọn provider/backend theo môi trường mà không phải sửa thư viện.

Một ứng dụng đã chuẩn hóa trên JUL có thể tiếp tục dùng `java.util.logging.Logger` trực tiếp nếu cần các tính năng đặc thù của JUL. Không cần chuyển toàn bộ code sang `System.Logger` chỉ vì Java 9 cung cấp facade mới; hãy chọn một quy ước nhất quán cho từng codebase.

## 10. Ghi log hiệu quả và an toàn

- Dùng level đúng mục đích: TRACE/DEBUG cho chẩn đoán, INFO cho sự kiện vận hành, WARNING cho tình huống bất thường, ERROR cho lỗi cần xử lý.
- Không ghi mật khẩu, access token, khóa bí mật, dữ liệu cá nhân hoặc payload nhạy cảm.
- Tránh tạo chuỗi hoặc thực hiện phép tính tốn kém khi level đang tắt.
- Dùng Supplier để trì hoãn việc tạo message:

```java
logger.log(
        System.Logger.Level.DEBUG,
        () -> buildExpensiveDiagnosticMessage()
);
```

Supplier chỉ được gọi khi logger đang bật level tương ứng. Cách này tránh chi phí tạo message không cần thiết.

- Với exception, truyền Throwable qua overload tương ứng để backend có thể ghi stack trace:

```java
try {
    processRequest();
} catch (IllegalStateException exception) {
    logger.log(
            System.Logger.Level.ERROR,
            "Request processing failed",
            exception
    );
}
```

- Không dùng log level để thay thế xử lý lỗi hoặc kiểm soát luồng nghiệp vụ.
- Không ghi cùng một exception ở mọi tầng nếu điều đó tạo nhiều bản log trùng lặp; chọn tầng có đủ ngữ cảnh để ghi nhận lỗi.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Chỉ thấy INFO trở lên | Root logger hoặc handler đặt ngưỡng INFO | Kiểm tra cả logger level và handler level |
| TRACE/DEBUG không xuất hiện | TRACE/DEBUG được ánh xạ sang FINER/FINE và bị lọc | Bật FINE/FINER ở cả logger và handler |
| System.Logger không dùng backend mong muốn | Provider tùy chỉnh chưa được ServiceLoader phát hiện | Kiểm tra module/service declaration và class loader |
| Cấu hình JUL không có tác dụng | Runtime không có module java.logging hoặc provider khác đang được dùng | Kiểm tra module graph và LoggerFinder thực tế |
| Một message xuất hiện hai lần | Handler được gắn ở logger con và parent/root cùng lúc | Kiểm tra useParentHandlers và danh sách handler |
| Message tốn CPU dù DEBUG bị tắt | Chuỗi được tạo trước khi gọi log | Dùng Supplier hoặc isLoggable |
| Thay đổi cấu hình toàn cục từ thư viện | Thư viện can thiệp backend của ứng dụng | Để ứng dụng chủ quản lý cấu hình |

## 12. Checklist triển khai

- Code đang dùng facade `System.Logger` hay API JUL trực tiếp?
- Runtime có module `java.logging` không?
- Có LoggerFinder provider tùy chỉnh được nạp qua ServiceLoader không?
- Nếu dùng default provider, mapping level sang JUL đã được tính đến chưa?
- Logger level và Handler level có cho phép các mức cần thiết không?
- Cấu hình production được nạp từ đúng file hoặc cấu hình runtime chưa?
- Handler có bị đăng ký trùng trên logger con và parent không?
- Message có chứa dữ liệu nhạy cảm hoặc được tạo tốn kém khi level bị tắt không?
- Thư viện có tránh thay đổi cấu hình backend toàn cục của ứng dụng không?

`System.Logger` cung cấp facade logging thống nhất từ Java 9; `System.LoggerFinder` quyết định backend. Trên runtime có module `java.logging` và không có provider tùy chỉnh, default LoggerFinder định tuyến đến `java.util.logging` với mapping TRACE→FINER, DEBUG→FINE, INFO→INFO, WARNING→WARNING và ERROR→SEVERE. Hãy cấu hình JUL qua LogManager, logger và handler; chỉ cài LoggerFinder riêng khi ứng dụng thực sự cần một backend khác.
