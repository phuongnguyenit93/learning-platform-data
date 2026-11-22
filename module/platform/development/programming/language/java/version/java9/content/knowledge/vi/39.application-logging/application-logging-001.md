# Lấy bộ ghi qua System.getLogger trong Java

Java 9 giới thiệu API logging chuẩn trong module java.base: System.getLogger(String) trả về một System.Logger để ghi log qua backend mà runtime hoặc ứng dụng lựa chọn. API này tạo một điểm gọi thống nhất cho thư viện và mã nền tảng, đồng thời cho phép ứng dụng định tuyến log sang hệ thống logging phù hợp.

Điểm cần nhớ là System.getLogger là factory lấy logger, còn System.Logger là interface dùng để kiểm tra mức và ghi thông điệp. Logger nhận được không phải lúc nào cũng là một java.util.logging.Logger; nó là facade do System.LoggerFinder cung cấp.

## 1. System.getLogger và System.Logger

Lấy logger theo tên:

~~~java
private static final System.Logger LOG =
    System.getLogger(OrderService.class.getName());
~~~

Hoặc dùng tên package/class rõ ràng:

~~~java
System.Logger logger = System.getLogger("com.example.orders");
~~~

Tên logger thường dựa trên tên class hoặc package để tạo namespace phân cấp dễ cấu hình. API không bắt buộc một quy tắc tên cụ thể; quan trọng là giữ tên ổn định và có ý nghĩa.

System.getLogger(name) trả về logger cho caller hiện tại. Runtime truyền cả tên logger và module của caller tới System.LoggerFinder, vì vậy provider có thể định tuyến hoặc áp dụng chính sách theo module.

Các thao tác thường dùng:

- getName() trả về tên logger.
- isLoggable(level) kiểm tra mức hiện tại có được ghi hay không.
- log(level, message) ghi một thông điệp.
- log(level, format, params...) ghi thông điệp có tham số.
- log(level, message, throwable) gắn exception với log record.
- log(level, supplier) tạo thông điệp theo kiểu lazy.
- log(level, bundle, message, throwable) và overload tương ứng hỗ trợ localization.

Khác với java.util.logging.Logger, System.Logger không có các phương thức tiện ích riêng như info(), warning() hay severe(). Mọi thao tác dùng log() cùng một giá trị System.Logger.Level.

## 2. Các mức log hiện hành

System.Logger.Level có bảy giá trị theo thứ tự severity tăng dần:

| Level | Mục đích thường dùng |
|---|---|
| ALL | Marker bật mọi mức |
| TRACE | Thông tin chẩn đoán rất chi tiết |
| DEBUG | Chi tiết phục vụ gỡ lỗi |
| INFO | Sự kiện vận hành bình thường |
| WARNING | Tình huống bất thường cần chú ý nhưng chưa nhất thiết thất bại |
| ERROR | Lỗi cần được xử lý hoặc điều tra |
| OFF | Marker tắt mọi mức |

ALL và OFF là marker ở hai đầu dải severity. Khi dùng logger, chọn mức theo ý nghĩa vận hành của sự kiện, không theo độ dài hoặc mức độ quan trọng chủ quan của câu chữ.

Khi backend mặc định là java.util.logging, System.Logger.Level được ánh xạ theo severity như sau:

| System.Logger.Level | java.util.logging.Level |
|---|---|
| ALL | ALL |
| TRACE | FINER |
| DEBUG | FINE |
| INFO | INFO |
| WARNING | WARNING |
| ERROR | SEVERE |
| OFF | OFF |

Bảng này mô tả mapping của LoggerFinder mặc định dùng JUL. Một LoggerFinder tùy chỉnh có thể ánh xạ các mức theo backend của chính nó.

## 3. Ghi thông điệp cơ bản

Ví dụ:

~~~java
System.Logger logger = System.getLogger("com.example.orders");

logger.log(System.Logger.Level.INFO, "service started");
logger.log(System.Logger.Level.WARNING, "retrying request");
~~~

Ghi exception cùng thông điệp:

~~~java
try {
    processOrder(order);
} catch (IOException ex) {
    logger.log(
        System.Logger.Level.ERROR,
        "Could not process order",
        ex
    );
    throw ex;
}
~~~

Overload nhận Throwable lưu exception cùng log record để backend có thể hiển thị stack trace hoặc thông tin lỗi theo formatter. Không ghép ex.getMessage() vào chuỗi rồi bỏ mất chính đối tượng exception nếu cần điều tra stack trace.

### Thông điệp có tham số

~~~java
logger.log(
    System.Logger.Level.INFO,
    "Order {0} accepted for customer {1}",
    orderId,
    customerId
);
~~~

Chuỗi format dùng quy tắc MessageFormat, ví dụ {0} và {1}. Nó không dùng cú pháp printf như %s hoặc %d.

Nếu đã có chuỗi hoàn chỉnh thì dùng overload nhận String. Nếu cần đưa nhiều giá trị vào thông điệp, overload có tham số giúp backend thực hiện formatting phù hợp.

## 4. Dùng Supplier để tạo log theo kiểu lazy

Một số thông điệp cần thu thập dữ liệu hoặc thực hiện phép tính tốn kém. Nếu nối chuỗi trước khi gọi logger, chi phí đó vẫn phát sinh kể cả khi mức log đang bị tắt:

~~~java
logger.log(
    System.Logger.Level.DEBUG,
    "state=" + buildExpensiveDiagnosticSnapshot()
);
~~~

Dùng Supplier<String> để chỉ tạo nội dung khi mức log được bật:

~~~java
logger.log(
    System.Logger.Level.DEBUG,
    () -> "state=" + buildExpensiveDiagnosticSnapshot()
);
~~~

Theo hợp đồng API, supplier chỉ được gọi khi logger hiện đang bật mức tương ứng. Nếu mức DEBUG bị tắt, hàm buildExpensiveDiagnosticSnapshot() không chạy.

Có thể kiểm tra trước khi thực hiện nhiều phép tính độc lập:

~~~java
if (logger.isLoggable(System.Logger.Level.DEBUG)) {
    String state = buildExpensiveDiagnosticSnapshot();
    String metrics = buildMetricsSnapshot();
    logger.log(System.Logger.Level.DEBUG, "state={0}, metrics={1}",
            state, metrics);
}
~~~

Nếu chỉ tạo một chuỗi, overload Supplier thường gọn hơn. Tránh gọi isLoggable() rồi mới gọi một overload không cần thiết; supplier đã hỗ trợ lazy evaluation.

## 5. Localization với ResourceBundle

Có thể lấy một logger gắn với ResourceBundle:

~~~java
ResourceBundle bundle =
    ResourceBundle.getBundle("com.example.Messages");

System.Logger logger =
    System.getLogger("com.example.orders", bundle);

logger.log(
    System.Logger.Level.INFO,
    "order.accepted"
);
~~~

Nếu bundle có key order.accepted, logger localizable có thể chuyển key thành thông điệp theo locale phù hợp.

Cũng có thể truyền bundle trực tiếp vào overload log:

~~~java
logger.log(
    System.Logger.Level.WARNING,
    bundle,
    "order.retry",
    (Throwable) null
);
~~~

Các overload nhận ResourceBundle cho phép backend xử lý localization. Theo hành vi mặc định của wrapper localizable, chuỗi do Supplier<String> tạo ra được xem là thông điệp đã hoàn chỉnh và không tự động được dịch như một key trong bundle.

Overload System.getLogger(name, bundle) có thể kích hoạt việc nạp và khởi tạo LoggerFinder ngay. Tài liệu API khuyến nghị dùng overload này sau khi runtime đã khởi tạo đầy đủ. Với mã hệ thống cần ghi log rất sớm, có thể lấy logger bằng System.getLogger(name) rồi dùng overload log nhận bundle.

## 6. LoggerFinder và backend logging

System.LoggerFinder là service chịu trách nhiệm tạo logger và định tuyến thông điệp tới backend. Một runtime duy trì một LoggerFinder cấp hệ thống.

Quá trình lựa chọn:

1. Runtime tìm provider System.LoggerFinder bằng ServiceLoader với system class loader.
2. Nếu tìm thấy provider tùy chỉnh, provider đó được dùng.
3. Nếu không tìm thấy, runtime dùng LoggerFinder mặc định.

LoggerFinder mặc định có hành vi:

- Nếu module java.logging hiện diện, backend là java.util.logging (JUL); thông điệp được chuyển tới java.util.logging.Logger.
- Nếu module java.logging không hiện diện, runtime dùng simple logger ghi các thông điệp từ INFO trở lên ra System.err.

Do đó, không nên giả định log luôn xuất hiện trên console, stdout hay một file cụ thể. Đích đến và format phụ thuộc backend và cấu hình của nó.

### Cấu hình ở backend

Logger lấy qua System.getLogger() không cung cấp API để ứng dụng gọi setLevel() hoặc thêm handler trực tiếp. Việc cấu hình thuộc trách nhiệm của backend.

Nếu runtime dùng JUL, cấu hình thông qua API hoặc cấu hình của java.util.logging. Nếu ứng dụng dùng một logging framework bên ngoài, ứng dụng có thể cung cấp LoggerFinder tương thích để định tuyến System.Logger tới framework đó.

Thư viện chỉ cần ghi log nên tránh tự cấu hình backend. Nếu thư viện thay đổi cấu hình toàn cục, nó có thể ảnh hưởng tới các thành phần khác trong cùng tiến trình.

### Cung cấp LoggerFinder tùy chỉnh

Một ứng dụng/module có thể khai báo service provider trong module-info.java:

~~~java
module com.example.logging.provider {
    provides java.lang.System.LoggerFinder
        with com.example.logging.CustomLoggerFinder;
}
~~~

CustomLoggerFinder kế thừa System.LoggerFinder, có constructor không tham số và triển khai:

~~~java
@Override
public System.Logger getLogger(String name, Module module) {
    // Trả về System.Logger adapter tới backend của ứng dụng.
}
~~~

Đây là điểm tích hợp cấp runtime. Ứng dụng thông thường chỉ cần dùng System.getLogger(); không cần tự triển khai LoggerFinder nếu backend đã cung cấp adapter phù hợp.

## 7. Ví dụ Java chạy được

Ví dụ sử dụng System.getLogger() để ghi INFO, WARNING và một thông điệp DEBUG lazy. Nó cấu hình JUL chỉ để kết quả minh họa có format cố định; logger trong mã ứng dụng vẫn được lấy qua System.getLogger().

~~~java
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogManager;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class SystemGetLoggerExample {
    public static void main(String[] args) {
        Logger root = LogManager.getLogManager().getLogger("");
        for (Handler handler : root.getHandlers()) {
            root.removeHandler(handler);
        }

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.ALL);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return formatMessage(record) + System.lineSeparator();
            }
        });
        root.addHandler(console);
        root.setLevel(Level.INFO);

        System.Logger logger = System.getLogger("com.example.orders");
        AtomicBoolean debugSupplierCalled = new AtomicBoolean();

        logger.log(System.Logger.Level.INFO, "service started");
        logger.log(System.Logger.Level.INFO, "order {0} accepted", 42);
        logger.log(System.Logger.Level.DEBUG, () -> {
            debugSupplierCalled.set(true);
            return "diagnostic details";
        });
        logger.log(System.Logger.Level.WARNING, "retrying operation");

        System.out.println("debug supplier invoked="
                + debugSupplierCalled.get());
    }
}
~~~

Lưu trong SystemGetLoggerExample.java, biên dịch và chạy với Java 17 trở lên:

~~~shell
javac --release 17 -Xlint:all SystemGetLoggerExample.java
java SystemGetLoggerExample
~~~

Trong runtime mặc định có module java.logging, kết quả stdout chính xác:

~~~text
debug supplier invoked=false
~~~

Kết quả stderr chính xác:

~~~text
service started
order 42 accepted
retrying operation
~~~

DEBUG bị tắt bởi cấu hình mức INFO của backend, nên supplier không được gọi. Ví dụ cấu hình ConsoleHandler để format log tối giản; cấu hình này chỉ phục vụ minh họa và không phải yêu cầu bắt buộc khi dùng System.Logger.

## 8. Chọn tên logger và tổ chức log

Một logger theo class thường được khai báo một lần:

~~~java
private static final System.Logger LOG =
    System.getLogger(OrderService.class.getName());
~~~

Lợi ích:

- Tên ổn định, có thể lọc theo package hoặc class.
- Dễ nhận diện thành phần phát ra thông điệp.
- Không tạo một tên logger mới cho từng request hoặc từng object.
- Có thể tái sử dụng logger trong mọi method của class.

Thông điệp log nên cung cấp ngữ cảnh hữu ích: thao tác nào thất bại, đối tượng nghiệp vụ nào liên quan, request hoặc correlation ID nào cần tra cứu. Không ghi mật khẩu, token, khóa bí mật hoặc dữ liệu cá nhân nhạy cảm.

Không ghi cùng một exception nhiều lần ở mọi tầng nếu không bổ sung thông tin mới. Chọn tầng có đủ ngữ cảnh để ghi lỗi, rồi truyền exception lên hoặc xử lý theo hợp đồng của tầng đó.

## 9. Các lỗi thường gặp

- **Nhầm System.Logger với java.util.logging.Logger:** System.getLogger() trả về facade System.Logger; không gọi các phương thức cấu hình JUL trên đối tượng này.
- **Giả định backend luôn là JUL:** LoggerFinder tùy chỉnh có thể định tuyến sang backend khác.
- **Giả định log luôn ra stdout:** simple logger mặc định dùng System.err; backend khác có thể ghi vào file hoặc nơi khác.
- **Dùng %s trong format:** overload có tham số dùng quy tắc MessageFormat, ví dụ {0}.
- **Tạo chuỗi đắt tiền trước khi gọi log:** dùng Supplier để tránh tính toán khi level bị tắt.
- **Ghi exception chỉ bằng getMessage():** dùng overload nhận Throwable nếu cần stack trace.
- **Cấu hình logger từ thư viện:** cấu hình backend thuộc ứng dụng hoặc runtime; thư viện nên chỉ phát thông điệp.
- **Dùng tên logger thay đổi theo request:** tên package/class ổn định giúp lọc và cấu hình dễ hơn.
- **Giả định Supplier luôn được gọi:** supplier không được gọi khi level tương ứng không bật.
- **Dùng logger localizable cho chuỗi Supplier như message key:** supplier mặc định được xem là tạo ra chuỗi hoàn chỉnh, không phải key cần localization.
- **Gọi overload getLogger có ResourceBundle trong giai đoạn runtime khởi tạo sớm:** overload này có thể nạp LoggerFinder ngay; cân nhắc lấy logger cơ bản rồi truyền bundle khi log.
- **Cố dùng System.Logger để cấu hình handler hoặc level:** cấu hình phải thực hiện qua API của backend.

## 10. Tài liệu tham khảo chính thức

- [System.getLogger — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/System.html): lấy logger theo tên và theo ResourceBundle; logger gắn với module của caller.
- [System.Logger — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/System.Logger.html): các overload log, Supplier lazy, Throwable, ResourceBundle và isLoggable.
- [System.Logger.Level — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/System.Logger.Level.html): mức severity và mapping tới JUL.
- [System.LoggerFinder — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/System.LoggerFinder.html): ServiceLoader, backend mặc định, cấu hình và provider tùy chỉnh.
- [java.util.logging — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.logging/java/util/logging/package-summary.html): backend JUL và cách cấu hình handler/level.