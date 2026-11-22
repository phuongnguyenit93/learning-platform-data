# Phân biệt API ghi nhật ký với nơi lưu và chính sách vận hành

## Mục tiêu

Logging trong ứng dụng Java gồm nhiều phần có trách nhiệm khác nhau. API ghi nhật ký cho phép code phát ra sự kiện; handler quyết định sự kiện được chuyển đến đâu; formatter quyết định cách biểu diễn; cấu hình và chính sách vận hành quyết định mức nào được ghi, dữ liệu được giữ bao lâu, ai được xem và hệ thống xử lý khi đích ghi gặp lỗi.

Với Java, `java.util.logging` (JUL) là logging API có sẵn trong JDK. Nó cung cấp `Logger`, `LogRecord`, `Level`, `Filter`, `Handler`, `Formatter` và `LogManager`. API này không đồng nghĩa với một nơi lưu trữ cụ thể hoặc một chính sách vận hành hoàn chỉnh.

Cần tách biệt bốn câu hỏi:

1. **API:** Code phát ra sự kiện log bằng cách nào?
2. **Destination (đích ghi):** Sự kiện được chuyển đến console, file, socket, collector hay hệ thống nào?
3. **Format:** Sự kiện được trình bày thành text, XML, JSON hay định dạng có cấu trúc nào?
4. **Operational policy (chính sách vận hành):** Mức log, lọc, bảo mật, rotation, retention, quyền truy cập, buffering và xử lý sự cố được quản lý ra sao?

Việc tách các trách nhiệm này giúp thay đổi nơi lưu hoặc chính sách mà không phải sửa từng câu lệnh logging trong business code.

## 1. Kiến trúc logging trong Java

Với JUL, đường đi phổ biến của một sự kiện là:

~~~text
Business code
    |
    v
Logger.log(...)
    |
    +--> Logger level / Filter
    |
    v
LogRecord
    |
    v
Handler level / Filter
    |
    v
Formatter
    |
    v
Destination
    |
    +--> Console / stdout / stderr
    +--> File
    +--> Socket / remote collector
    +--> Custom handler / logging service
    |
    v
Storage, indexing, alerting và retention do hệ thống vận hành quản lý
~~~

Các thành phần không có cùng trách nhiệm:

| Thành phần | Trách nhiệm | Không quyết định |
|---|---|---|
| `Logger` | Nhận sự kiện từ code, đặt tên logger, kiểm tra level và chuyển record đến handler | Nơi lưu cuối cùng và thời gian giữ log |
| `LogRecord` | Mang dữ liệu của một sự kiện: level, message, thời gian, logger, exception, tham số | Chính sách retention hoặc quyền truy cập |
| `Level` | Phân loại mức độ quan trọng | Cấu hình vận hành của toàn hệ thống |
| `Filter` | Cho phép hoặc loại bỏ record theo điều kiện | Đích lưu trữ |
| `Handler` | Nhận record và chuyển đến đích ghi | Chính sách nghiệp vụ về thời gian lưu |
| `Formatter` | Chuyển record thành dạng biểu diễn | Việc record được lưu bền vững hay không |
| `LogManager` | Quản lý logger và cấu hình JUL | Hạ tầng lưu trữ bên ngoài JVM |

Một logger có thể gửi cùng một record đến nhiều handler. Một handler có thể được gắn vào logger con hoặc logger cha. Vì vậy, việc phát ra một log record không đồng nghĩa với việc nó chỉ được ghi một lần hoặc chỉ đến một đích.

## 2. API ghi nhật ký: Logger, LogRecord và Level

### Logger

Code ứng dụng thường lấy logger theo tên lớp hoặc theo một namespace:

~~~java
private static final Logger LOGGER =
        Logger.getLogger(PaymentService.class.getName());
~~~

Logger cho phép ghi theo mức:

~~~java
LOGGER.severe("Payment provider is unavailable");
LOGGER.warning("Retrying payment");
LOGGER.info("Payment accepted");
LOGGER.fine("Internal diagnostic details");
~~~

Tên logger thường theo cấu trúc package hoặc tên thành phần, ví dụ `app.payment`, `app.payment.gateway`, `app.storage`. JUL sử dụng quan hệ cha/con theo dấu chấm trong tên logger để kế thừa level và chuyển record lên handler của logger cha.

### LogRecord

Mỗi lần ghi log, JUL tạo hoặc chuyển một `LogRecord` chứa thông tin sự kiện. Các dữ liệu thường dùng gồm:

- Level và message.
- Thời điểm tạo record.
- Tên logger.
- Tên class và method nguồn nếu có thể xác định.
- Tham số của message.
- Throwable nếu log gắn với exception.
- Resource bundle và mã message khi dùng localization.

Nên ghi thông tin có ý nghĩa chẩn đoán như request ID, order ID hoặc operation name. Tránh đưa password, access token, secret hoặc dữ liệu cá nhân không cần thiết vào message.

### Level

Các mức chuẩn của JUL, từ nghiêm trọng đến chi tiết, gồm:

| Level | Mục đích thường dùng |
|---|---|
| `SEVERE` | Lỗi nghiêm trọng làm một thao tác hoặc thành phần không thể tiếp tục |
| `WARNING` | Tình huống bất thường cần chú ý nhưng ứng dụng có thể tiếp tục |
| `INFO` | Sự kiện vận hành quan trọng, trạng thái nghiệp vụ cần theo dõi |
| `CONFIG` | Thông tin cấu hình |
| `FINE` | Thông tin debug ở mức chi tiết |
| `FINER` | Trace chi tiết hơn |
| `FINEST` | Trace rất chi tiết |
| `OFF` | Tắt logging |
| `ALL` | Cho phép mọi mức |

Level là nhãn phân loại. Ý nghĩa cụ thể của `INFO` hay `WARNING` phải được đội phát triển và vận hành thống nhất. Không nên dùng `SEVERE` cho mọi exception hoặc dùng `INFO` cho từng bước nội bộ có tần suất rất cao.

## 3. Handler quyết định đích ghi

`Handler` là điểm nối từ logging API sang destination. JUL có sẵn một số handler phổ biến:

| Handler | Đích ghi | Trường hợp sử dụng |
|---|---|---|
| `ConsoleHandler` | Console, mặc định là stderr | Chạy local, CLI, container log qua stdout/stderr |
| `FileHandler` | File trên máy chạy ứng dụng | Ứng dụng tự quản lý log file cục bộ |
| `SocketHandler` | Kết nối socket đến hệ thống nhận log | Gửi record đến dịch vụ ở xa |
| Custom `Handler` | Đích do ứng dụng hoặc thư viện tích hợp tự định nghĩa | Cloud logging client, queue hoặc collector riêng |

### ConsoleHandler

~~~java
ConsoleHandler console = new ConsoleHandler();
console.setLevel(Level.INFO);
console.setFormatter(new SimpleFormatter());

logger.addHandler(console);
~~~

ConsoleHandler ghi ra console. Trong container, stdout/stderr thường được runtime nền tảng thu thập và chuyển tiếp đến hệ thống log tập trung. Việc lưu lâu dài do container platform hoặc log collector quản lý.

### FileHandler

~~~java
FileHandler file = new FileHandler(
        "%h/app-%g.log",
        5_000_000,
        5,
        true
);
file.setLevel(Level.FINE);
file.setFormatter(new SimpleFormatter());

logger.addHandler(file);
~~~

Ví dụ này ghi file trong thư mục home của user, giới hạn khoảng 5 MB mỗi file và giữ tối đa 5 file trong chu kỳ rotation của FileHandler. Tham số cuối bật append. Đây là cơ chế rotation theo kích thước và số file, không phải một chính sách retention hoàn chỉnh theo ngày hoặc theo yêu cầu tuân thủ.

### SocketHandler và custom Handler

`SocketHandler` gửi log qua socket đến đầu nhận. Khi dùng destination từ xa, cần thiết kế timeout, bảo mật đường truyền, khả năng mất kết nối và cách xử lý lỗi.

Custom `Handler` có thể chuyển record vào queue, gọi logging service hoặc xuất JSON. Tuy nhiên, một custom handler phải xác định rõ hành vi khi đích ghi chậm hoặc lỗi: block caller, buffer, drop record hay báo lỗi qua `ErrorManager`.

Handler là nơi tích hợp destination; nó không tự tạo ra cam kết lưu trữ bền vững nếu hệ thống nhận phía sau không có cam kết đó.

## 4. Formatter quyết định hình dạng log

Formatter chuyển `LogRecord` thành chuỗi hoặc dạng biểu diễn phù hợp với handler. JUL có `SimpleFormatter` và `XMLFormatter`; ứng dụng cũng có thể viết formatter riêng.

Ví dụ định dạng ngắn:

~~~java
public final class LineFormatter extends Formatter {
    @Override
    public String format(LogRecord record) {
        return record.getLevel().getName()
                + " " + record.getLoggerName()
                + " - " + formatMessage(record)
                + System.lineSeparator();
    }
}
~~~

Formatter có thể thêm timestamp, thread ID, request ID hoặc trường có cấu trúc. Nếu cần JSON, nên dùng serializer phù hợp để escape đúng chuỗi và tránh tự ghép JSON bằng nối chuỗi.

Không nhầm formatter với nơi lưu: đổi từ `SimpleFormatter` sang JSON formatter chỉ đổi cách biểu diễn record. Record vẫn được handler chuyển đến destination đã cấu hình.

## 5. Level và Filter có thể được áp dụng ở nhiều lớp

Một record thường phải vượt qua nhiều điều kiện:

1. Logger phải cho phép level đó.
2. Filter của logger, nếu có, phải chấp nhận record.
3. Handler nhận record phải cho phép level.
4. Filter của handler, nếu có, phải chấp nhận record.

Ví dụ:

~~~java
logger.setLevel(Level.FINE);
console.setLevel(Level.INFO);
~~~

Logger nhận cả `INFO` và `FINE`, nhưng ConsoleHandler chỉ ghi từ `INFO` trở lên. Nếu FileHandler có level `FINE`, file có thể nhận thêm record debug trong khi console vẫn chỉ nhận log ít chi tiết hơn.

Filter cho phép lọc theo nội dung hoặc metadata:

~~~java
logger.setFilter(record ->
        !record.getMessage().contains("health-check-poll")
);
~~~

Filter ví dụ chỉ để minh họa; trong ứng dụng thật nên dùng field hoặc marker có cấu trúc thay vì phụ thuộc vào việc tìm chuỗi trong message.

## 6. Cấu hình JUL tách khỏi business code

Có thể cấu hình JUL qua file properties, thường là `logging.properties`:

~~~properties
handlers=java.util.logging.ConsoleHandler
.level=INFO

app.payment.level=FINE
java.util.logging.ConsoleHandler.level=INFO
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
~~~

Trong ví dụ này:

- Logger root mặc định ở `INFO`.
- Logger `app.payment` nhận đến mức `FINE`.
- ConsoleHandler vẫn chỉ ghi từ `INFO` trở lên.
- Handler và formatter được chọn bằng cấu hình.

Chạy ứng dụng với file cấu hình riêng:

~~~bash
java -Djava.util.logging.config.file=/path/to/logging.properties -jar app.jar
~~~

JUL cũng có thể được cấu hình trong quá trình khởi động bằng `LogManager.readConfiguration(InputStream)`. Nên nạp cấu hình trước khi các thành phần khởi tạo logger và handler, để tránh trạng thái cấu hình ban đầu đã được sử dụng.

Có thể lấy LogManager hiện tại:

~~~java
LogManager manager = LogManager.getLogManager();
~~~

LogManager quản lý namespace và cấu hình logger trong JVM. Nó không phải hệ thống lưu log từ xa hoặc công cụ quản lý retention.

## 7. Logger hierarchy và việc log bị lặp

Tên logger tạo thành cây phân cấp. Ví dụ:

~~~text
app
 |
 +-- app.payment
 |      |
 |      +-- app.payment.gateway
 |
 +-- app.storage
~~~

Một logger có thể chuyển record lên logger cha khi `useParentHandlers` đang bật (mặc định). Nếu cùng một handler được gắn ở logger con và logger cha, một record có thể xuất hiện nhiều lần.

Có thể tắt propagation khi muốn logger tự quản lý handler:

~~~java
logger.setUseParentHandlers(false);
~~~

Chỉ nên tắt propagation khi đã cấu hình handler riêng cho logger đó. Nếu không, record có thể không có đích ghi nào.

Khi debug log bị lặp, kiểm tra handler được gắn ở cả logger con và logger cha, cùng với `useParentHandlers`, trước khi thay đổi code ghi log.

## 8. System.Logger trong Java 9

Java 9 bổ sung `System.Logger` và `System.LoggerFinder` như một logging API cho các thành phần nền tảng và thư viện muốn tránh phụ thuộc trực tiếp vào một logging implementation cụ thể.

Ví dụ:

~~~java
private static final System.Logger LOGGER =
        System.getLogger(MyComponent.class.getName());

LOGGER.log(System.Logger.Level.INFO, "Component started");
~~~

`System.Logger` là API để phát log. `System.LoggerFinder` cho phép runtime/provider cung cấp implementation phù hợp. API này không quy định log phải ghi vào file nào, lưu bao lâu hoặc ai được quyền truy cập.

Khi tích hợp với logging framework, cần hiểu provider/bridge đang được ứng dụng sử dụng và tránh cấu hình vòng lặp giữa các bridge. `System.Logger` không phải một hệ thống lưu trữ độc lập.

## 9. API facade và backend trong hệ sinh thái Java

Ngoài JUL, ứng dụng có thể sử dụng facade bên thứ ba như SLF4J. Cần phân biệt:

- **Logging API/facade:** kiểu logger và phương thức mà business code gọi.
- **Backend/implementation:** thành phần thực sự xử lý record và cung cấp appender/handler.
- **Destination:** file, console, socket, collector hoặc dịch vụ lưu trữ phía sau backend.

Ví dụ, SLF4J là facade; Logback hoặc Log4j2 có thể là backend. Một ứng dụng cũng có thể dùng bridge để chuyển log từ JUL sang backend đã chọn.

Không nên thêm nhiều logging backend chỉ để giải quyết việc thay đổi destination. Chọn một kiến trúc rõ ràng, xác định facade và backend, rồi cấu hình handler/appender và bridge nhất quán. Tránh bridge theo vòng tròn khiến cùng record đi qua lại giữa các hệ thống.

## 10. Chính sách vận hành không chỉ là cấu hình API

Một hệ thống logging dùng được trong production cần chính sách rõ ràng cho các vấn đề sau:

| Chính sách | Câu hỏi cần trả lời |
|---|---|
| Level | Môi trường production ghi INFO/WARNING/SEVERE hay bật debug tạm thời? Ai được phép thay đổi? |
| Destination | Log ở stdout, file cục bộ, socket hay collector tập trung? |
| Rotation | Khi file đạt kích thước hoặc thời gian nhất định, hệ thống tạo file mới ra sao? |
| Retention | Giữ log bao nhiêu ngày/tháng? Ai xóa và theo tiêu chí nào? |
| Access control | Ai được xem, tải hoặc xóa log? |
| Redaction | Token, password, cookie, secret và dữ liệu cá nhân được loại bỏ thế nào? |
| Integrity | Audit log có cần chống sửa đổi, kiểm tra tính toàn vẹn hoặc lưu riêng không? |
| Capacity | Giới hạn dung lượng, tốc độ ingest và chi phí lưu trữ là bao nhiêu? |
| Failure handling | Khi disk đầy hoặc collector mất kết nối, ứng dụng block, buffer hay drop log? |
| Monitoring | Theo dõi log pipeline bị trễ, mất record hoặc lỗi ghi như thế nào? |

### Rotation và retention là hai việc khác nhau

Rotation tạo file hoặc segment mới để một file không tăng vô hạn. Retention quyết định dữ liệu cũ được giữ bao lâu trước khi xóa hoặc chuyển archive.

`FileHandler` hỗ trợ rotation theo kích thước và số lượng file. Chính sách retention theo ngày, lưu trữ lâu dài, archive và xóa an toàn thường do hệ điều hành, log agent hoặc nền tảng lưu trữ quản lý.

### Bảo mật nội dung

Không ghi password, access token, private key, session cookie hoặc dữ liệu cá nhân không cần thiết. Nếu cần định danh một giao dịch, dùng ID nghiệp vụ hoặc correlation ID đã được kiểm soát thay vì ghi toàn bộ payload.

Cần tránh log injection: dữ liệu đầu vào có thể chứa newline hoặc ký tự điều khiển làm giả dòng log. Formatter/structured logger phải escape dữ liệu đúng cách.

### Logging và audit

Log vận hành giúp chẩn đoán hệ thống. Audit trail phục vụ theo dõi hành động có ý nghĩa về bảo mật hoặc tuân thủ. Một dòng log thông thường không tự trở thành audit record đáng tin cậy.

Nếu audit cần chống sửa đổi, quyền truy cập hạn chế, timestamp đáng tin cậy hoặc retention bắt buộc, hãy thiết kế pipeline và kho lưu trữ chuyên biệt cho yêu cầu đó.

### Logging bất đồng bộ và mất log

Handler bất đồng bộ có thể giảm thời gian business thread chờ I/O, nhưng cần xác định:

- Dung lượng queue.
- Chính sách khi queue đầy: block, drop, sampling hay fallback.
- Thời gian flush khi shutdown.
- Hành vi khi collector hoặc mạng không khả dụng.
- Cách theo dõi record bị mất.

Không thể giả định log đã được ghi bền vững chỉ vì lệnh `logger.info()` đã trả về. Cam kết delivery phụ thuộc handler và destination.

## 11. Ví dụ hoàn chỉnh: API tách biệt với destination

Ví dụ dưới đây dùng JUL Logger để phát record, một Handler riêng để chọn đích stdout và một Formatter riêng để định dạng. Business code không trực tiếp nối chuỗi hoặc ghi file.

Tệp `LoggingSeparationDemo.java`:

~~~java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LoggingSeparationDemo {
    private static final class LineFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            return record.getLevel().getName() + " "
                    + record.getLoggerName() + " - "
                    + formatMessage(record) + System.lineSeparator();
        }
    }

    private static final class StdoutHandler extends Handler {
        @Override
        public synchronized void publish(LogRecord record) {
            if (record != null && isLoggable(record)) {
                System.out.print(getFormatter().format(record));
            }
        }

        @Override
        public void flush() {
            System.out.flush();
        }

        @Override
        public void close() {
            flush();
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("app.payment");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        Handler destination = new StdoutHandler();
        destination.setLevel(Level.INFO);
        destination.setFormatter(new LineFormatter());
        logger.addHandler(destination);

        logger.info("payment accepted");
        logger.fine("internal diagnostic");
        logger.log(Level.WARNING, "retry for order {0}", "ORD-42");

        logger.removeHandler(destination);
        destination.close();
    }
}
~~~

Biên dịch và chạy bằng JDK 9 trở lên:

~~~bash
javac --release 9 -Xlint:all LoggingSeparationDemo.java
java LoggingSeparationDemo
~~~

Stdout chính xác:

~~~text
INFO app.payment - payment accepted
WARNING app.payment - retry for order ORD-42
~~~

Dòng `FINE` không xuất hiện vì logger và handler đều đặt level `INFO`. Nếu đổi handler thành FileHandler, business code vẫn có thể giữ nguyên; chỉ cần thay destination và cấu hình phù hợp.

Ví dụ dùng custom handler để minh họa ranh giới API/destination. Trong ứng dụng thật, ưu tiên handler có sẵn hoặc backend đã được quản lý; custom handler cần tự xác định buffering, error handling và lifecycle.

## 12. Cách ghi log có ích và tiết kiệm

### Dùng message có tham số

~~~java
logger.log(Level.INFO, "Order {0} accepted", orderId);
~~~

JUL hỗ trợ tham số message để formatter xử lý. Cách này giúp message nhất quán và tránh tự ghép chuỗi ở mọi call site.

### Trì hoãn tạo message debug tốn kém

~~~java
logger.fine(() -> buildExpensiveDiagnosticMessage());
~~~

Supplier chỉ được gọi khi logger cho phép level tương ứng, tránh tạo chuỗi debug tốn kém khi log đang tắt.

### Gắn exception đúng cách

~~~java
try {
    processPayment();
} catch (PaymentException error) {
    logger.log(Level.SEVERE, "Payment processing failed", error);
    throw error;
}
~~~

Truyền Throwable giúp formatter/backend có thể ghi stack trace. Không chỉ log `error.getMessage()` nếu cần chẩn đoán nguyên nhân.

### Dùng correlation ID

Khi một request đi qua nhiều service, log nên có request ID hoặc trace ID để ghép sự kiện. Tránh dựa vào thứ tự dòng log giữa nhiều thread như một cách chứng minh thứ tự nghiệp vụ.

## 13. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Nghĩ Logger quyết định log lưu ở đâu | Logger chỉ phát và chuyển record đến handler | Cấu hình Handler/destination riêng |
| Đổi formatter để cố chuyển log sang file | Formatter chỉ thay cách biểu diễn | Dùng FileHandler hoặc backend phù hợp |
| Chỉ cấu hình logger level | Handler có level/filter riêng nên record vẫn có thể bị loại | Kiểm tra cả logger và handler |
| Gắn handler ở logger con và logger cha | Record propagate lên cha và có thể được ghi lặp | Kiểm tra useParentHandlers và vị trí gắn handler |
| Dùng FINE trong production mà không kiểm soát | Debug volume có thể tăng mạnh | Đặt level theo môi trường và có quy trình bật tạm |
| Nghĩ FileHandler rotation đồng nghĩa retention | Rotation theo kích thước/count khác với thời gian lưu | Định nghĩa retention và archive riêng |
| Ghi secret để tiện debug | Log thường được nhiều hệ thống và người dùng truy cập | Redact hoặc không ghi dữ liệu nhạy cảm |
| Coi log vận hành là audit trail | Log thông thường không có cam kết chống sửa hoặc lưu bắt buộc | Thiết kế audit pipeline riêng |
| Dùng async handler mà không có overflow policy | Queue đầy có thể làm block hoặc mất log | Định nghĩa capacity, backpressure và drop policy |
| Cho rằng logger.info trả về nghĩa là log đã durable | Handler có thể buffer hoặc destination chưa xác nhận | Xác định delivery guarantee của pipeline |
| Dùng nhiều bridge theo vòng tròn | Một record có thể bị lặp hoặc quay lại backend ban đầu | Chỉ định một luồng bridge rõ ràng |
| Tạo message debug bằng nối chuỗi đắt tiền | Chuỗi vẫn được tạo dù level đã tắt | Dùng Supplier hoặc kiểm tra isLoggable |

## 14. Checklist triển khai

- Chọn API/facade rõ ràng: JUL, System.Logger hoặc facade của ứng dụng.
- Xác định backend và Handler/Appender đang thực thi việc ghi.
- Xác định destination thực tế: stdout, file, socket hay collector.
- Tách Formatter khỏi destination.
- Quy định level theo logger và handler cho từng môi trường.
- Kiểm tra logger hierarchy để tránh mất log hoặc log trùng.
- Cấu hình rotation, retention, archive và capacity riêng.
- Redact secret, token và dữ liệu cá nhân.
- Xác định quyền truy cập và yêu cầu integrity cho log/audit.
- Có chính sách khi handler, disk, network hoặc collector gặp lỗi.
- Nếu dùng async logging, định nghĩa queue, overflow và shutdown flush.
- Theo dõi tình trạng pipeline và kiểm thử cả trường hợp destination bị lỗi.
- Không coi việc gọi API logging là bằng chứng record đã được lưu bền vững.

## 15. Tài liệu tham khảo

- [java.util.logging — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/package-summary.html)
- [Logger — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html)
- [Handler — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html)
- [FileHandler — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html)
- [System.Logger — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.Logger.html)
- [JEP 264 — Platform Logging API](https://openjdk.org/jeps/264)

API ghi nhật ký xác định cách code phát ra sự kiện và cách record được chuyển qua handler. Destination quyết định log đi đâu; formatter quyết định log trông như thế nào; chính sách vận hành quyết định log được lọc, bảo vệ, lưu giữ và giám sát ra sao. Giữ rõ các ranh giới này giúp thay đổi hạ tầng logging mà không làm business code phụ thuộc vào một nơi lưu cụ thể.