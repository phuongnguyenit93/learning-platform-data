# System.Logger.Level và ánh xạ mức nhật ký trong Java

## 1. System.Logger.Level là gì?

System.Logger.Level là enum được giới thiệu trong Java 9, nằm trong interface System.Logger. Nó chuẩn hóa bảy mức nhật ký mà code Java có thể dùng mà không phải phụ thuộc trực tiếp vào một logging framework cụ thể.

Các mức được sắp theo severity tăng dần:

~~~text
ALL < TRACE < DEBUG < INFO < WARNING < ERROR < OFF
~~~

- **ALL** và **OFF** là các mức đánh dấu: bật tất cả hoặc tắt tất cả.
- **TRACE** dùng cho thông tin chẩn đoán rất chi tiết.
- **DEBUG** dùng cho thông tin phục vụ phát triển và điều tra lỗi.
- **INFO** ghi nhận hoạt động bình thường có ý nghĩa.
- **WARNING** ghi nhận tình huống bất thường nhưng ứng dụng vẫn có thể tiếp tục.
- **ERROR** ghi nhận lỗi nghiêm trọng hoặc thao tác thất bại.

System.Logger.Level không phải một logging backend. Nó là tập mức thống nhất mà System.Logger chuyển đến LoggerFinder và backend thực tế.

## 2. Severity của từng mức

Mỗi enum constant có tên và giá trị severity nguyên. Severity càng lớn thì mức độ nghiêm trọng càng cao.

| System.Logger.Level | Severity | Ý nghĩa |
|---|---:|---|
| ALL | Integer.MIN_VALUE | Marker cho phép mọi mức |
| TRACE | 400 | Chẩn đoán chi tiết |
| DEBUG | 500 | Thông tin gỡ lỗi |
| INFO | 800 | Hoạt động thông thường |
| WARNING | 900 | Cảnh báo |
| ERROR | 1000 | Lỗi |
| OFF | Integer.MAX_VALUE | Marker tắt mọi mức |

Có thể đọc tên và severity bằng API:

~~~java
System.Logger.Level level = System.Logger.Level.WARNING;

String name = level.getName();
int severity = level.getSeverity();
~~~

Các phương thức tiện ích khác:

~~~java
System.Logger.Level[] levels = System.Logger.Level.values();
System.Logger.Level parsed = System.Logger.Level.valueOf("ERROR");
~~~

valueOf() yêu cầu tên enum chính xác và phân biệt chữ hoa chữ thường. Nếu tên không tồn tại, phương thức ném IllegalArgumentException; nếu truyền null, nó ném NullPointerException.

Không dùng ordinal() để biểu diễn severity trong cấu hình. ordinal chỉ là vị trí enum trong mã nguồn; getSeverity() mới là giá trị severity được API công bố.

## 3. Ánh xạ sang java.util.logging.Level

Khi backend mặc định sử dụng java.util.logging (JUL), System.Logger.Level được ánh xạ sang java.util.logging.Level có severity tương ứng:

| System.Logger.Level | java.util.logging.Level | Giá trị JUL |
|---|---|---:|
| ALL | ALL | Integer.MIN_VALUE |
| TRACE | FINER | 400 |
| DEBUG | FINE | 500 |
| INFO | INFO | 800 |
| WARNING | WARNING | 900 |
| ERROR | SEVERE | 1000 |
| OFF | OFF | Integer.MAX_VALUE |

Những điểm cần nhớ:

- TRACE ánh xạ sang FINER, không phải FINEST.
- DEBUG ánh xạ sang FINE.
- ERROR ánh xạ sang SEVERE vì JUL không có constant chuẩn tên ERROR.
- ALL và OFF là marker ở hai đầu thang severity.
- JUL có thêm CONFIG với severity 700, nhưng System.Logger.Level không có một mức CONFIG tương ứng.

Ánh xạ này là hợp đồng của LoggerFinder mặc định khi dùng JUL. Một LoggerFinder tùy chỉnh có trách nhiệm ánh xạ System.Logger.Level sang các mức mà backend riêng hỗ trợ; không được giả định mọi backend đều dùng tên hoặc số severity của JUL.

## 4. Vì sao Java có System.Logger?

System.Logger tạo một facade logging trong Java Platform. Thư viện hoặc lớp thuộc JDK có thể phát log mà không phải phụ thuộc cứng vào JUL hay một framework bên ngoài.

Lấy logger theo tên:

~~~java
System.Logger logger = System.getLogger(
    MyService.class.getName()
);
~~~

Tên logger thường dựa trên package hoặc class để backend có thể cấu hình theo namespace.

Ghi log:

~~~java
logger.log(System.Logger.Level.INFO, "Service started");
logger.log(System.Logger.Level.WARNING, "Retrying request");
logger.log(System.Logger.Level.ERROR, "Request failed", exception);
~~~

System.Logger cung cấp các overload cho:

- Message dạng String hoặc Object.
- Message có tham số định dạng.
- Throwable đi kèm.
- Supplier để tạo message lười.
- ResourceBundle để bản địa hóa message.

API này giúp thư viện phát log theo một giao diện ổn định trong khi ứng dụng lựa chọn backend phù hợp.

## 5. LoggerFinder chọn backend như thế nào?

System.LoggerFinder là service provider chịu trách nhiệm tạo logger và kết nối logger với backend.

Khi runtime cần một LoggerFinder:

1. Java tìm provider tùy chỉnh bằng ServiceLoader và system class loader.
2. Nếu không tìm thấy provider tùy chỉnh, Java dùng LoggerFinder mặc định.
3. LoggerFinder trả về System.Logger tương ứng với tên logger và module của caller.
4. Logger chuyển message cùng System.Logger.Level sang backend.

Hành vi của provider mặc định:

- Nếu module java.logging có mặt, backend là java.util.logging.
- Nếu java.logging không có, implementation đơn giản ghi các message từ INFO trở lên ra System.err.
- LoggerFinder tùy chỉnh có thể chuyển log sang framework khác.

Một thư viện chỉ cần phát log nên dùng System.Logger và không tự cấu hình backend. Việc cấu hình thuộc ứng dụng hoặc logging provider được chọn.

## 6. Cách ghi log theo mức

Ví dụ:

~~~java
private static final System.Logger LOG =
    System.getLogger(OrderService.class.getName());

void processOrder() {
    LOG.log(System.Logger.Level.INFO, "Order processing started");
    LOG.log(System.Logger.Level.DEBUG, "Validating order details");
    LOG.log(System.Logger.Level.WARNING, "Inventory is running low");
}
~~~

Chọn mức theo ý nghĩa của sự kiện:

| Mức | Nên dùng khi |
|---|---|
| TRACE | Theo dõi từng bước nội bộ hoặc dữ liệu rất chi tiết |
| DEBUG | Ghi trạng thái phục vụ chẩn đoán |
| INFO | Ghi sự kiện vận hành quan trọng |
| WARNING | Có điều kiện bất thường cần chú ý |
| ERROR | Một thao tác thất bại hoặc cần can thiệp |

Không ghi mọi sự kiện ở INFO hoặc ERROR. Việc phân loại nhất quán giúp người vận hành lọc log và đặt ngưỡng backend chính xác.

Không đưa password, token, session ID, dữ liệu cá nhân hoặc bí mật vào message. Cần che hoặc loại bỏ dữ liệu nhạy cảm trước khi ghi log.

## 7. isLoggable và kiểm tra trước khi tạo message

isLoggable(level) cho biết logger hiện có bật mức đó hay không:

~~~java
if (LOG.isLoggable(System.Logger.Level.DEBUG)) {
    LOG.log(System.Logger.Level.DEBUG, buildExpensiveDiagnostic());
}
~~~

Cách này tránh thực hiện công việc tạo message khi DEBUG đang bị tắt.

Có thể viết gọn hơn bằng Supplier:

~~~java
LOG.log(
    System.Logger.Level.DEBUG,
    () -> buildExpensiveDiagnostic()
);
~~~

Supplier chỉ được gọi khi logger đang bật mức tương ứng. Đây là lựa chọn tốt khi tạo message tốn CPU, truy vấn trạng thái lớn hoặc dựng chuỗi chi tiết.

isLoggable chỉ phản ánh cấu hình hiện tại của logger. Backend vẫn có thể áp dụng filter hoặc quy tắc bổ sung khi xử lý record.

## 8. Ghi log có tham số và Throwable

System.Logger hỗ trợ message có tham số:

~~~java
LOG.log(
    System.Logger.Level.INFO,
    "Processed order {0} in {1} ms",
    orderId,
    elapsedMillis
);
~~~

Format string của System.Logger dùng quy tắc MessageFormat, không phải cú pháp %s của String.format.

Có thể gắn Throwable để backend giữ lại thông tin exception:

~~~java
try {
    saveOrder();
} catch (Exception exception) {
    LOG.log(
        System.Logger.Level.ERROR,
        "Unable to save order",
        exception
    );
}
~~~

Truyền Throwable riêng giúp backend có thể ghi stack trace, loại exception và thông tin nguyên nhân theo formatter đang cấu hình.

Không chỉ ghi exception.getMessage() nếu cần điều tra lỗi. Message thường không chứa đầy đủ stack trace hoặc chuỗi nguyên nhân.

## 9. ResourceBundle và message localization

System.Logger hỗ trợ ResourceBundle cho message cần bản địa hóa.

~~~java
ResourceBundle bundle =
    ResourceBundle.getBundle("com.example.Messages");

System.Logger logger = System.getLogger(
    "com.example.OrderService",
    bundle
);

logger.log(
    System.Logger.Level.INFO,
    bundle,
    "order.saved",
    new Object[] { orderId }
);
~~~

Trong ResourceBundle, khóa order.saved có thể được ánh xạ sang thông điệp theo locale.

Dùng key ổn định thay vì ghép câu đã dịch trực tiếp trong code. Backend hoặc LoggerFinder chịu trách nhiệm áp dụng ResourceBundle và formatter theo API.

Các message tạo sẵn bằng Supplier được coi là nội dung đã hoàn chỉnh; không nên mặc định rằng Supplier trả về message key sẽ được bản địa hóa tự động.

## 10. Cấu hình mức log thuộc về backend

System.Logger instance lấy từ System.getLogger không có API setLevel(). Nó chỉ cung cấp khả năng ghi log và kiểm tra isLoggable.

Nếu LoggerFinder mặc định dùng JUL, cấu hình thông qua java.util.logging:

- Logger level quyết định mức tối thiểu của logger.
- Handler level quyết định record nào được handler xuất ra.
- Filter có thể loại thêm record.
- Formatter quyết định cách hiển thị message.

Ví dụ JUL có thể cấu hình qua logging.properties:

~~~properties
handlers=java.util.logging.ConsoleHandler
.level=INFO
java.util.logging.ConsoleHandler.level=ALL
com.example.level=FINE
~~~

Để bật TRACE từ System.Logger với backend JUL, logger và handler phải cho phép mức FINER tương ứng. Chỉ bật mức logger mà handler vẫn chặn FINER thì message vẫn không xuất hiện.

Nếu dùng framework khác, cấu hình theo tài liệu backend đó. Không gọi JUL API để cấu hình một System.Logger đang được LoggerFinder tùy chỉnh chuyển sang backend khác.

## 11. Dùng System.Logger trong named module

System.Logger thuộc java.base, nên code chỉ dùng facade này không cần khai báo requires java.logging.

Ví dụ module đơn giản:

~~~java
module example.app {
}
~~~

Nếu ứng dụng trực tiếp cấu hình JUL hoặc tham chiếu java.util.logging.Level, cần đọc module java.logging:

~~~java
module example.app {
    requires java.logging;
}
~~~

Ứng dụng có thể thay backend bằng một LoggerFinder provider thông qua cơ chế service provider. Trong module descriptor, provider được khai báo bằng provides cho System.LoggerFinder; trên classpath có thể đăng ký bằng file META-INF/services phù hợp.

Không tạo hoặc khởi tạo backend nặng trong constructor LoggerFinder. LoggerFinder có thể được nạp trong giai đoạn khởi động runtime; khởi tạo phức tạp có thể gây vòng lặp class loading hoặc deadlock.

## 12. Ví dụ hoàn chỉnh: severity và ánh xạ JUL

Chương trình sau in toàn bộ mức System.Logger.Level cùng severity và mức JUL tương ứng. Nó cấu hình JUL để minh họa log ở TRACE, DEBUG, INFO, WARNING và ERROR.

**Tệp SystemLoggerLevelDemo.java:**

~~~java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class SystemLoggerLevelDemo {
    private static final class CompactFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            String line = record.getLevel().getName() + ": "
                    + formatMessage(record);
            if (record.getThrown() != null) {
                line += " ["
                        + record.getThrown().getClass().getSimpleName()
                        + "]";
            }
            return line + System.lineSeparator();
        }
    }

    private static Level toJulLevel(System.Logger.Level level) {
        switch (level) {
            case ALL:
                return Level.ALL;
            case TRACE:
                return Level.FINER;
            case DEBUG:
                return Level.FINE;
            case INFO:
                return Level.INFO;
            case WARNING:
                return Level.WARNING;
            case ERROR:
                return Level.SEVERE;
            case OFF:
                return Level.OFF;
            default:
                throw new AssertionError(level);
        }
    }

    public static void main(String[] args) {
        String name = SystemLoggerLevelDemo.class.getName();
        Logger backend = Logger.getLogger(name);
        backend.setUseParentHandlers(false);
        backend.setLevel(Level.ALL);

        ConsoleHandler handler = new ConsoleHandler();
        handler.setLevel(Level.ALL);
        handler.setFormatter(new CompactFormatter());
        backend.addHandler(handler);

        System.Logger logger = System.getLogger(name);

        for (System.Logger.Level level : System.Logger.Level.values()) {
            System.out.println(level.getName() + " -> "
                    + toJulLevel(level).getName()
                    + " (" + level.getSeverity() + ")");
        }

        logger.log(System.Logger.Level.TRACE, "trace message");
        logger.log(System.Logger.Level.DEBUG, () -> "lazy debug message");
        logger.log(System.Logger.Level.INFO, "application started");
        logger.log(System.Logger.Level.WARNING, "slow response detected");
        logger.log(
                System.Logger.Level.ERROR,
                "operation failed",
                new IllegalStateException("demo")
        );
    }
}
~~~

Biên dịch và chạy trên JDK 17 trở lên:

~~~bash
javac --release 17 -Xlint:all SystemLoggerLevelDemo.java
java -cp . SystemLoggerLevelDemo
~~~

Output trên JDK chuẩn với LoggerFinder mặc định và module java.logging:

~~~text
ALL -> ALL (-2147483648)
TRACE -> FINER (400)
DEBUG -> FINE (500)
INFO -> INFO (800)
WARNING -> WARNING (900)
ERROR -> SEVERE (1000)
OFF -> OFF (2147483647)
FINER: trace message
FINE: lazy debug message
INFO: application started
WARNING: slow response detected
SEVERE: operation failed [IllegalStateException]
~~~

Chương trình đặt mức logger và handler thành ALL để tất cả ví dụ đều được xuất. Trong production, nên cấu hình mức phù hợp với môi trường thay vì bật mọi mức liên tục.

Output log có thể khác nếu runtime cài LoggerFinder tùy chỉnh hoặc backend khác. Bảng severity và ánh xạ JUL trong ví dụ mô tả provider mặc định sử dụng java.util.logging.

## 13. Lỗi thường gặp

- **Nhầm ERROR với JUL.SEVERE:** System.Logger dùng ERROR; JUL dùng SEVERE cho severity tương ứng.
- **Nhầm TRACE với FINEST:** TRACE được ánh xạ sang FINER.
- **Chỉ bật logger level mà quên handler level:** record có thể được logger chấp nhận nhưng handler vẫn loại bỏ.
- **Coi ALL và OFF là mức nghiệp vụ thông thường:** đây là marker bật/tắt thang log.
- **Dùng ordinal thay severity:** dùng getSeverity() để so sánh mức.
- **Dùng String.format với log format:** System.Logger dùng MessageFormat cho overload có tham số.
- **Tạo message đắt trước khi kiểm tra mức:** dùng isLoggable hoặc Supplier.
- **Giả định mọi backend đều ánh xạ giống JUL:** LoggerFinder tùy chỉnh chịu trách nhiệm ánh xạ riêng.
- **Cấu hình backend từ thư viện:** thư viện nên phát log qua facade; ứng dụng quản lý cấu hình backend.
- **Bỏ Throwable khi log lỗi:** truyền exception riêng để backend có thể ghi stack trace.
- **Ghi dữ liệu nhạy cảm:** lọc secret và thông tin cá nhân khỏi message.
- **Cho rằng java.logging luôn có mặt:** System.Logger thuộc java.base; default backend phụ thuộc module java.logging có hiện diện hay không.

## 14. Ghi nhớ

System.Logger.Level là enum Java 9 chuẩn hóa bảy mức ALL, TRACE, DEBUG, INFO, WARNING, ERROR và OFF. Severity lần lượt là Integer.MIN_VALUE, 400, 500, 800, 900, 1000 và Integer.MAX_VALUE. Với LoggerFinder mặc định dùng JUL, ánh xạ là ALL, FINER, FINE, INFO, WARNING, SEVERE và OFF. System.Logger là facade; LoggerFinder lựa chọn backend và chịu trách nhiệm ánh xạ mức. Dùng isLoggable hoặc Supplier để tránh tạo message không cần thiết, truyền Throwable riêng khi ghi lỗi và để ứng dụng cấu hình backend theo môi trường.

## 15. Tài liệu tham khảo

- [System.Logger.Level – Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.Logger.Level.html)
- [System.Logger – Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.Logger.html)
- [System.LoggerFinder – Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.LoggerFinder.html)
- [java.util.logging.Level – Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.logging/java/util/logging/Level.html)
