# Logger của JDK: java.util.logging.Logger

**java.util.logging.Logger** là lớp logger tiêu chuẩn được cung cấp sẵn trong JDK, thuộc Java Logging API (thường gọi là **JUL**, viết tắt của *Java Util Logging*). Ứng dụng có thể dùng Logger để phát các sự kiện như khởi động, xử lý tác vụ, cảnh báo và lỗi mà không cần cài thêm SLF4J, Logback hoặc Log4j 2.

Điểm cốt lõi: **Logger nhận yêu cầu phát log và áp dụng quy tắc chấp nhận sự kiện; Handler nhận các sự kiện được chuyển tới và ghi ra đích; Formatter quyết định cách trình bày.** Chỉ gọi `logger.info(...)` không bảo đảm dòng log sẽ xuất hiện, vì mức log, filter, handler và cấu hình runtime đều có thể ảnh hưởng đến kết quả.

## 1. JUL nằm ở đâu trong JDK?

JUL có sẵn trong module chuẩn **java.logging**, thường dùng các lớp sau:

| Thành phần | Lớp/interface | Vai trò |
| --- | --- | --- |
| Logger | `java.util.logging.Logger` | Đối tượng mà mã ứng dụng gọi để tạo log event |
| Level | `java.util.logging.Level` | Mức độ chi tiết/nghiêm trọng |
| LogRecord | `java.util.logging.LogRecord` | Dữ liệu một sự kiện log, chứa level, message, tham số, exception và metadata |
| Handler | `java.util.logging.Handler` | Nhận và xuất log; có thể lọc theo level/filter |
| ConsoleHandler | `java.util.logging.ConsoleHandler` | Handler mặc định hướng tới console, thường ghi **stderr** |
| FileHandler | `java.util.logging.FileHandler` | Ghi log ra file, hỗ trợ giới hạn dung lượng và xoay file |
| Formatter | `java.util.logging.Formatter` | Biến LogRecord thành chuỗi đầu ra |
| Filter | `java.util.logging.Filter` | Kiểm tra thêm một LogRecord có được chấp nhận hay không |
| LogManager | `java.util.logging.LogManager` | Quản lý logger và cấu hình logging của JUL |

Mô hình khái niệm:

~~~text
Mã Java
   |
   | Logger.getLogger(...).info(...)
   v
java.util.logging.Logger
   |  kiểm tra Level, Filter tại logger phát
   v
LogRecord
   |
   +--> Handler tại logger (nếu có)
   |
   +--> Handler tại logger cha (nếu cho phép chuyển tiếp)
          |
          +--> kiểm tra Level/Filter của Handler
          |
          +--> Formatter
                    |
                    +--> stderr / file / đích khác
~~~

Đây là cách nhìn cho người học; trong implementation, `LogRecord` là đối tượng mà Logger chuyển cho Handler sau khi được chấp nhận, và Formatter thường được Handler sử dụng. Cấu hình khác nhau có thể khiến một sự kiện đi tới nhiều handler hoặc không đi tới handler nào.

JUL chạy được trên classpath của một ứng dụng Java SE thông thường. Nếu tự xây dựng **named Java module**, cần khai báo module phụ thuộc:

~~~java
// module-info.java: ví dụ cho ứng dụng modular
module demo.logging {
    requires java.logging;
}
~~~

Đây là một đoạn module descriptor minh họa, không phải chương trình độc lập; ứng dụng classpath không cần tạo `module-info.java` chỉ để dùng JUL.

## 2. Tạo và đặt tên Logger

Cách phổ biến nhất là dùng `Logger.getLogger(String name)`:

~~~java
import java.util.logging.Logger;

public final class OrderService {
    private static final Logger LOG =
            Logger.getLogger(OrderService.class.getName());

    public void acceptOrder(String orderId) {
        LOG.info("Order accepted: " + orderId);
    }
}
~~~

Đây là class hợp lệ nhưng là **đoạn minh họa**, không có `main` để chạy trực tiếp. Trong ứng dụng có package, `OrderService.class.getName()` trả tên đầy đủ, chẳng hạn `com.example.orders.OrderService`.

Một số điều quan trọng:

- **Logger có tên ổn định**, thường theo tên lớp hoặc package. Tên này giúp cấu hình mức log cho một thành phần mà không sửa toàn bộ ứng dụng.
- `Logger.getLogger(name)` trả logger đã đăng ký với tên phù hợp nếu đang có; không nên coi mỗi lời gọi là một instance logging độc lập mới.
- Mẫu **`private static final Logger`** giữ một tham chiếu mạnh tới logger trong vòng đời class và tránh phải tìm logger ở mỗi lần xử lý. JUL quản lý các logger có tên theo cơ chế có thể dùng tham chiếu yếu; không nên phụ thuộc vào việc một logger không được mã nguồn giữ tham chiếu sẽ tồn tại mãi.
- **Không dùng requestId, userId, orderId hoặc timestamp để tạo tên Logger động**. Đó là dữ liệu của sự kiện, nên đưa vào message/context; tên động làm số lượng logger tăng và cấu hình theo namespace trở nên khó kiểm soát.
- `Logger.getLogger("com.example.orders")` dùng được cho một logger chung của package hoặc subsystem, nhưng với log của từng lớp, dùng `Class.getName()` thường dễ truy vết hơn.

JUL còn có `Logger.getAnonymousLogger()` cho những trường hợp không cần tên đăng ký toàn cục. Logger ẩn danh có hành vi quản lý khác logger có tên; trong ứng dụng nghiệp vụ thông thường, logger có tên ổn định là lựa chọn dễ cấu hình và điều tra hơn.

### Root logger và Global logger

JUL có **root logger** với tên là chuỗi rỗng `""`. Các logger có tên thường nằm dưới root theo phân cấp. Có thể lấy root bằng:

~~~java
Logger root = Logger.getLogger("");
~~~

JUL cũng có logger tên **global** (`Logger.getGlobal()`), nhưng sử dụng logger riêng theo lớp thường cho biết nguồn sự kiện rõ hơn. Không đánh đồng logger global với root logger: đó là các logger khác nhau.

## 3. Phát log bằng API của JDK

`java.util.logging.Logger` cung cấp các phương thức tiện ích:

~~~java
logger.severe("Unrecoverable failure");
logger.warning("Retry scheduled");
logger.info("Task finished");
logger.config("Loaded configuration");
logger.fine("Cache lookup");
logger.finer("More detailed operation");
logger.finest("Fine-grained trace");
~~~

Đây là các câu lệnh minh họa bên trong phương thức đã có biến `logger` kiểu `java.util.logging.Logger`. Ngoài ra có các overload `log(...)`:

~~~java
logger.log(Level.INFO, "event=job_completed jobId={0}", jobId);
logger.log(Level.SEVERE, "event=job_failed", exception);
logger.log(Level.FINE, () -> "details=" + computeDetails());
~~~

Đoạn này giả định `jobId`, `exception`, `computeDetails()` đã tồn tại. Ba overload có ý nghĩa khác nhau:

- **`log(Level, String, Object)`** dùng một đối số để format message, theo dạng `{0}`.
- **`log(Level, String, Throwable)`** gắn một exception vào sự kiện để formatter có thể in stack trace.
- **`log(Level, Supplier<String>)`** chỉ tính message khi sự kiện vượt qua điều kiện level phù hợp; với dữ liệu tính toán đắt tiền, đây là lựa chọn hữu ích.

Đừng trộn cú pháp JUL **`{0}`, `{1}`** với cú pháp tham số **`{}`** của SLF4J. Hai kiểu Logger có tên đơn giản giống nhau nhưng thuộc hai API khác nhau.

## 4. Các mức log của JUL

JUL khai báo những level tiêu chuẩn sau:

| Level | Mục đích thường gặp | Ví dụ |
| --- | --- | --- |
| `SEVERE` | Lỗi nghiêm trọng khiến chức năng/tác vụ thất bại | Không thể hoàn tất job do dependency unavailable |
| `WARNING` | Bất thường đáng chú ý, có thể còn xử lý được | Retry, fallback, dữ liệu không mong đợi |
| `INFO` | Mốc hoạt động bình thường có ý nghĩa | Service ready, import completed |
| `CONFIG` | Thông tin cấu hình hoặc khởi tạo | Nạp cấu hình có liên quan đến vận hành |
| `FINE` | Chi tiết hỗ trợ chẩn đoán | Quyết định cache hit/miss |
| `FINER` | Chi tiết sâu hơn | Các bước trung gian |
| `FINEST` | Mức rất chi tiết | Theo dõi luồng xử lý mức thấp |
| `ALL` | Cho phép mọi level thông thường qua bước kiểm tra mức | Dùng khi muốn quan sát đầy đủ |
| `OFF` | Tắt các sự kiện log thông thường tại logger hoặc handler | Giảm/tắt ghi ở phạm vi chỉ định |

JUL so sánh level theo **mức độ ưu tiên số**. Với các level tiêu chuẩn, SEVERE nghiêm trọng hơn WARNING, WARNING hơn INFO, INFO hơn CONFIG và FINE. Khi ngưỡng là INFO, một sự kiện INFO/WARNING/SEVERE được logger chấp nhận về mức, nhưng CONFIG/FINE/FINER/FINEST bị chặn.

Đặt ngưỡng trực tiếp:

~~~java
logger.setLevel(Level.INFO);
~~~

Kiểm tra mức có được bật:

~~~java
if (logger.isLoggable(Level.FINE)) {
    logger.fine("Detailed state");
}
~~~

Nếu `logger.getLevel()` trả về **null**, điều đó thường có nghĩa logger **kế thừa mức hiệu lực từ logger cha**, không phải Logger không thể ghi log. Để xác định một sự kiện sẽ xuất thật, còn cần xem level/filter của Handler và đường đi tới handler.

Khi so sánh với SLF4J, nhớ rằng JUL dùng `SEVERE`/`WARNING`/`FINE`, trong khi SLF4J thường dùng `ERROR`/`WARN`/`DEBUG`. Hai bộ level tương ứng về mục đích vận hành ở nhiều trường hợp, nhưng không phải cùng enum hoặc cùng tên API.

## 5. LogRecord: dữ liệu của sự kiện

Trong JUL, một sự kiện có thể được biểu diễn bằng **`LogRecord`**. Đối tượng này mang các thông tin như:

- **Level:** mức phát sự kiện;
- **Message và Parameters:** template và dữ liệu được đưa vào template;
- **Logger name:** tên logger phát sự kiện;
- **Instant/timestamp:** thời điểm của record;
- **Thrown:** exception nếu có;
- **Thông tin luồng/thành phần khác:** metadata do hệ thống logging quản lý.

Ví dụ minh họa:

~~~java
LogRecord record = new LogRecord(
        Level.WARNING,
        "event=inventory_low sku={0} available={1}"
);
record.setParameters(new Object[]{"book-1", 2});
record.setLoggerName(logger.getName());
logger.log(record);
~~~

Đây là đoạn mã trong phương thức đã có `logger` và import `LogRecord`, `Level`. Trong phần lớn mã nghiệp vụ, `logger.log(Level, String, Object[])` đã đủ: **không cần tự tạo LogRecord cho mọi câu lệnh**.

`Formatter.formatMessage(record)` có thể kết hợp template và parameters để tạo text hiển thị. Nếu tự tạo Formatter mà chỉ trả về `record.getMessage()`, bạn có thể thấy nguyên `{0}` thay vì giá trị thật. Muốn giữ phần dữ liệu bổ sung như exception, phải xử lý `record.getThrown()` hoặc dùng Formatter phù hợp.

LogRecord còn hỗ trợ resource bundle để địa phương hóa message trong những ứng dụng cần thiết; đây là khả năng của JUL, không bắt buộc cho logging nghiệp vụ thông thường.

## 6. Handler và Formatter: vì sao gọi Logger chưa chắc có output?

Logger áp dụng mức log và filter tại nguồn phát. Sau đó sự kiện được chuyển tới Handler gắn với logger và, nếu cho phép, các Handler của logger cha.

Các Handler thường gặp:

- **`ConsoleHandler`**: in ra console, thông thường qua **stderr**; không nên mặc định tìm log ở stdout.
- **`FileHandler`**: ghi file; có tùy chọn rolling/rotation theo kích thước và số file.
- **`StreamHandler`**: cơ sở cho Handler ghi đến một stream; cần chú ý quản lý stream/flush.
- **`MemoryHandler`**: đệm log rồi đẩy tới một target Handler theo điều kiện được cấu hình.
- **Custom Handler**: gửi event đến đích riêng, cần xử lý lỗi, đồng bộ và vòng đời tài nguyên phù hợp.

Handler có ngưỡng riêng:

~~~java
logger.setLevel(Level.FINE);
handler.setLevel(Level.WARNING);
~~~

Ví dụ logger cho phép FINE nhưng Handler chỉ chấp nhận WARNING: lời gọi `logger.fine(...)` có thể qua được logger nhưng **bị handler chặn**. Đừng sửa một mình mức logger rồi kết luận backend bị hỏng khi chưa thấy FINE.

**Formatter** nhận LogRecord và tạo nội dung đầu ra. JUL có `SimpleFormatter` và `XMLFormatter` cùng khả năng viết formatter tùy chỉnh. Cách format timestamp, level, logger name, parameters và Throwable tùy Formatter. Chỉ tự chèn tất cả metadata vào message sẽ dễ gây dư thừa hoặc mâu thuẫn.

**Filter** có thể được gắn với Logger hoặc Handler để áp dụng điều kiện bổ sung ngoài mức log. Ví dụ chỉ cho phép một loại event; filter sai cũng có thể khiến bản ghi biến mất. Không phải mọi Handler cùng chia sẻ filter: mỗi Handler có thể quyết định độc lập.

## 7. Ví dụ Java 17+ chạy độc lập

Ví dụ đầy đủ sau dùng **chỉ JDK** để chứng minh bốn điều:

1. Mức INFO của logger cho phép INFO/WARNING/SEVERE nhưng loại FINE.
2. Message template JUL `{0}`, `{1}` được Formatter thay giá trị.
3. Throwable nằm riêng trong record và có thể được formatter xuất thông tin.
4. Đổi level sang FINE khiến lời gọi FINE tiếp theo xuất hiện.

Tạo tệp **JulLoggerDemo.java**:

~~~java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class JulLoggerDemo {
    private static final Logger LOG =
            Logger.getLogger(JulLoggerDemo.class.getName());

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.ALL);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                String cause = record.getThrown() == null
                        ? ""
                        : " | cause="
                                + record.getThrown().getClass().getSimpleName();
                return record.getLevel().getName()
                        + " | " + formatMessage(record)
                        + cause + System.lineSeparator();
            }
        });
        LOG.addHandler(console);

        LOG.fine(() -> "event=cache_probe");
        LOG.log(Level.INFO,
                "event=order_accepted orderId={0} units={1}",
                new Object[]{"ord-17", 3});
        LOG.log(Level.WARNING,
                "event=inventory_low item={0}", "book-1");
        LOG.log(Level.SEVERE, "event=payment_failed orderId=ord-18",
                new IllegalStateException("timeout"));

        LOG.setLevel(Level.FINE);
        LOG.fine(() -> "event=cache_probe");

        LOG.removeHandler(console);
        console.close();
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac JulLoggerDemo.java
java JulLoggerDemo
~~~

Kết quả chính xác trong **stderr** (đã loại bỏ timestamp bằng formatter được viết trong ví dụ):

~~~text
INFO | event=order_accepted orderId=ord-17 units=3
WARNING | event=inventory_low item=book-1
SEVERE | event=payment_failed orderId=ord-18 | cause=IllegalStateException
FINE | event=cache_probe
~~~

Giải thích lần lượt:

- Lời gọi FINE đầu tiên không sinh output vì Logger đang ở INFO. `Supplier` của lời gọi này không cần tạo message.
- INFO dùng template có hai tham số và được `formatMessage(record)` thay chính xác.
- WARNING có một tham số dạng chuỗi.
- SEVERE gắn `IllegalStateException` bằng overload nhận Throwable; formatter minh họa chỉ in **tên lớp exception**, không in toàn bộ stack trace.
- Sau `LOG.setLevel(Level.FINE)`, lời gọi FINE cuối cùng qua được logger và ConsoleHandler (handler đặt ALL).
- `setUseParentHandlers(false)` tránh sự kiện đi tiếp tới handler của root/cha và bị in thêm một lần; chương trình chủ động gỡ và đóng handler cuối main.

**Không nên dùng formatter chỉ in tên exception trong hệ thống cần phân tích lỗi nghiêm trọng.** Formatter production thường phải xuất stack trace theo chính sách bảo mật. Cấu hình Handler trong main chỉ để ví dụ tái hiện được kết quả, còn ứng dụng thực tế nên quản lý logging tập trung.

## 8. Phân cấp Logger trong JUL

JUL tổ chức logger theo tên có các thành phần phân cách bằng dấu chấm:

~~~text
""  (root logger)
  |
  +-- com.example
        |
        +-- com.example.orders
              |
              +-- com.example.orders.payment
~~~

`com.example.orders.payment` có thể là logger con của `com.example.orders` khi logger cha này tồn tại; cha trực tiếp thực tế là logger tổ tiên gần nhất đang tồn tại trong hệ thống. Có thể kiểm tra bằng `child.getParent()`.

Hai khái niệm **khác nhau**:

**A. Kế thừa level:** `child.setLevel(null)` nghĩa là logger con lấy level hiệu lực từ cha gần nhất có level được đặt cụ thể. Nếu cha WARNING, child INFO có thể bị loại ngay tại nguồn phát.

**B. Chuyển event tới handler của cha:** `child.setUseParentHandlers(true)` cho phép một record đã được child chấp nhận đi tới handler ở các logger cha. `false` ngăn con sử dụng parent handlers. Cơ chế này độc lập với việc child có kế thừa level hay không.

Quan trọng: **JUL không áp dụng lại level/filter của logger cha khi một LogRecord đã được chấp nhận ở logger con và được chuyển lên handler của cha.** Chính **handler của cha** kiểm tra level/filter của nó. Vì vậy child có level FINE, cha có level WARNING và handler cha ở ALL thì bản ghi FINE của child vẫn có thể xuất.

Ví dụ minh họa:

~~~java
Logger parent = Logger.getLogger("demo.orders");
Logger child = Logger.getLogger("demo.orders.payment");

parent.setLevel(Level.WARNING);
child.setLevel(null);  // child kế thừa WARNING
child.warning("retry requested");

child.setLevel(Level.FINE);   // child override level
child.fine("diagnostic info"); // có thể tới parent handler nếu handler cho phép
~~~

Đây chỉ là đoạn trong phương thức Java, không phải chương trình đầy đủ. Kết quả in ra còn phụ thuộc handler, filter và `setUseParentHandlers`.

Nếu vừa gắn ConsoleHandler vào child, vừa cho child chuyển tiếp tới ConsoleHandler ở root, một sự kiện có thể được in hai lần. Khi muốn child chỉ ghi qua handler riêng, dùng `setUseParentHandlers(false)` **và bảo đảm handler riêng tồn tại**.

Trong JUL, tên logger **không phải cây extends của class Java** và **không phải thread hierarchy**. Đây là phân cấp cấu hình/định tuyến theo tên logger, thường gắn với package hoặc tên lớp.

## 9. Cấu hình JUL bằng logging.properties

Thay vì gắn Handler và `setLevel` khắp mã nguồn, ứng dụng có thể đặt cấu hình trong một tệp `logging.properties`.

Ví dụ:

~~~properties
# Handler được gắn với root
handlers = java.util.logging.ConsoleHandler

# Mức chung cho các logger kế thừa từ root
.level = INFO

# Handler console có thể nhận cả FINE từ logger con
java.util.logging.ConsoleHandler.level = ALL
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter

# Giảm log ở phần lớn module orders
com.example.orders.level = WARNING

# Tăng chi tiết cho riêng payment
com.example.orders.payment.level = FINE
~~~

Chạy một class ứng dụng đã được biên dịch với tệp cấu hình:

~~~bash
java -Djava.util.logging.config.file=logging.properties MyApplication
~~~

Trong lệnh này, **MyApplication** là tên class ứng dụng giả định có `main`, không phải file bổ sung được cung cấp trong bài. Đặt property **trước tên class** để JVM truyền đường dẫn cấu hình cho JUL khi khởi tạo.

Điều cần nhớ:

- `handlers` ở ví dụ khai báo root handler; các logger con có thể chuyển event lên đó theo mặc định.
- `.level` là level của **root logger**; không phải cú pháp level cho tất cả Handler.
- `java.util.logging.ConsoleHandler.level` là ngưỡng riêng của Handler. Đặt root INFO nhưng Handler ALL cho phép các logger con tự đặt FINE xuất bản ghi FINE qua root Handler.
- `com.example.orders.payment.level=FINE` giúp tăng chi tiết ở package có tên tương ứng mà không mở FINE cho mọi thành phần.
- **Đường dẫn, môi trường chạy và thời điểm nạp cấu hình** phải đúng. Nếu mã trong `main` sau đó chủ động gọi `setLevel`, thêm/gỡ Handler hoặc thay Filter, nó có thể thay đổi hành vi so với file properties.
- Dùng `LogManager` để quản lý cấu hình tập trung khi ứng dụng cần nạp lại/cập nhật; thay đổi file trên đĩa **không mặc nhiên** khiến mọi logger đang chạy tự động cập nhật.

Các framework Java như Spring Boot thường có cấu hình logging riêng và backend mặc định của framework. Khi làm việc trong framework, kiểm tra hệ logging đang thực sự xử lý log trước khi dùng `logging.properties` như thể nó là nguồn cấu hình duy nhất.

## 10. Các phương thức và thuộc tính cần biết

| API JUL | Ý nghĩa | Chú ý |
| --- | --- | --- |
| `Logger.getLogger(name)` | Lấy logger theo tên | Dùng tên ổn định, thường từ class |
| `Logger.getGlobal()` | Lấy global logger | Ít ngữ cảnh nguồn hơn logger theo class |
| `Logger.getParent()` | Lấy logger cha hiện tại | Không có trên `org.slf4j.Logger` |
| `Logger.getLevel()` | Lấy level gắn trực tiếp | `null` có thể nghĩa là kế thừa |
| `Logger.setLevel(level)` | Đặt level của logger | `null` để kế thừa |
| `Logger.isLoggable(level)` | Kiểm tra ngưỡng chấp nhận ở logger | Không đủ để kết luận handler sẽ xuất |
| `Logger.log(Level, String)` | Phát message với level | Không gắn tham số định dạng |
| `Logger.log(Level, String, Object[])` | Phát template với nhiều tham số | JUL dùng `{0}`, `{1}` |
| `Logger.log(Level, String, Throwable)` | Ghi event có exception | Giữ Throwable thay vì chỉ gọi `getMessage()` |
| `Logger.log(Level, Supplier<String>)` | Tạo message lazy khi level được bật | Phù hợp với message tốn chi phí |
| `Logger.addHandler(handler)` | Gắn Handler vào logger | Có thể gây trùng nếu cha cũng xuất |
| `Logger.removeHandler(handler)` | Gỡ Handler | Tài nguyên handler cần được đóng phù hợp |
| `Logger.setUseParentHandlers(boolean)` | Bật/tắt chuyển event đến handler cha | Không thay đổi việc kế thừa level |
| `Logger.setFilter(filter)` | Đặt Filter bổ sung | Có thể chặn event dù level phù hợp |

Các method ở bảng thuộc **`java.util.logging.Logger`**. Không chuyển cú pháp nguyên xi sang SLF4J, Logback hoặc Log4j 2 chỉ vì chúng cũng có đối tượng gọi là Logger.

## 11. Phân biệt java.util.logging.Logger và System.Logger

Từ Java 9, JDK còn có **`java.lang.System.Logger`**, thường lấy qua **`System.getLogger(name)`**. Đây là một API logging cấp hệ thống của Java Platform, dùng các level thuộc `System.Logger.Level` như INFO, WARNING, ERROR, DEBUG và TRACE.

Ví dụ:

~~~java
System.Logger logger = System.getLogger("demo.platform");
logger.log(System.Logger.Level.INFO, "Application initialized");
~~~

Đây là đoạn minh họa trong một phương thức. `System.Logger` **khác kiểu** với `java.util.logging.Logger` và cũng khác `org.slf4j.Logger` của SLF4J.

Trong JDK thông thường, cơ chế `System.LoggerFinder` mặc định có thể định tuyến đến hệ logging nền tảng; implementation có thể được thay thế bởi một provider phù hợp. Vì vậy không nên mặc nhiên cho rằng mọi cách cấu hình JUL hoặc từng overload `Logger.log(...)` đều áp dụng cho `System.Logger`.

Khi chủ đề là **Java Util Logging**, hãy nhận diện import `java.util.logging.Logger` cùng `Level`, `Handler`, `LogManager`. Nếu dự án dùng `System.Logger` thì đó là API khác cần kiểm tra backend/bridge cụ thể.

## 12. Hiệu năng, concurrency và an toàn dữ liệu

### Hạn chế tạo message không cần thiết

Một lệnh như:

~~~java
logger.fine("state=" + expensiveStateDump());
~~~

vẫn gọi `expensiveStateDump()` **trước khi** Logger có thể loại FINE. Nếu dữ liệu này đắt tiền, dùng overload Supplier:

~~~java
logger.fine(() -> "state=" + expensiveStateDump());
~~~

Ở dạng lambda, việc tính message được hoãn cho tới khi sự kiện cần thiết ở mức log đang bật. Nếu chuẩn bị sẵn object/chuỗi đắt tiền **trước** câu lệnh lambda, lợi ích lazy sẽ không còn cho phần việc đã thực hiện.

Với dữ liệu nhỏ, không cần tạo logic phức tạp để né vài thao tác rẻ. Tối ưu tập trung vào hot path và các việc serialize/format tốn chi phí.

### Logger và đa luồng

Một logger theo lớp thường được nhiều thread sử dụng chung; JUL có các cơ chế nội bộ để quản lý logging trong môi trường đồng thời. Tuy vậy:

- Log từ nhiều thread có thể xen kẽ; không suy luận trình tự nghiệp vụ tuyệt đối chỉ từ vị trí các dòng.
- Từng Handler hoặc Formatter **tùy chỉnh** phải được viết để xử lý an toàn khi có nhiều thread, bao gồm state dùng chung và đầu ra.
- Một logger name không phải correlation ID. Để liên hệ các bản ghi từ cùng request/job, thêm requestId, jobId hoặc traceId vào event.
- Khi viết Handler ghi file/network, cân nhắc buffering, flush, shutdown, lỗi I/O và khả năng thất lạc log khi process kết thúc đột ngột.

### Kiểm soát nội dung nhạy cảm

Không ghi trực tiếp password, token, API key, Authorization header, session cookie, dữ liệu thẻ hoặc toàn bộ request/response chứa thông tin riêng tư. `logger.info("Request: " + request)` có thể vô tình đưa dữ liệu nhạy cảm ra file log qua `toString()`.

Nên chọn các field hữu ích như `event`, `requestId` nội bộ, `outcome`, `reason`, `durationMs`; loại hoặc che thông tin khác trước khi phát sự kiện. Với đầu vào không tin cậy chứa dấu xuống dòng/ký tự điều khiển, dùng encoding/escaping phù hợp để giảm nguy cơ **log injection** trong bản ghi text.

Placeholder `{0}` giúp định dạng tham số nhưng **không tự che secret** và không thay thế xử lý dữ liệu không tin cậy.

## 13. JUL trong ứng dụng có nhiều logging framework

JUL vừa là API vừa có implementation/handler sẵn trong JDK. **SLF4J** là facade khác, còn **Logback** và **Log4j 2 Core** là những backend khác có cấu hình riêng.

Một số ứng dụng muốn gom mọi event vào một backend. Khi đó có thể dùng bridge, ví dụ tuyến **JUL → SLF4J → backend được chọn**. Tuy nhiên việc thêm thư viện bridge vào dependency chưa chắc đã kích hoạt tuyến chuyển tiếp; với JUL thường phải cài bridge handler và quản lý các JUL handler hiện có để tránh log trùng.

Không tự động thêm nhiều bridge ngược chiều vì có thể tạo vòng lặp hoặc xung đột provider. Nếu framework đã cấu hình logging, ưu tiên cơ chế framework đang cung cấp.

Điều cần phân biệt rõ:

- **Logger của JUL** trong mã nguồn dùng `java.util.logging.Logger`, mức `Level.FINE`, handler của JUL.
- **Logger của SLF4J** dùng `org.slf4j.Logger`, mức DEBUG/WARN/ERROR, backend quyết định appender và output.
- **System.Logger** của Java Platform là một API riêng được hỗ trợ bởi logger finder phù hợp.

Để xác định một câu lệnh đang đi qua hệ thống nào, xem **import trong mã** và **dependency/runtime logging backend**, sau đó kiểm tra handler/appender thực tế.

## 14. Những lỗi JUL Logger thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `logger.fine(...)` không thấy | Effective level là INFO hoặc handler chặn FINE | Kiểm tra `getLevel()`, `isLoggable(FINE)`, level/filter của handler |
| `getLevel()` là null | Logger đang kế thừa level từ cha | Kiểm tra `getParent()` và level trên hierarchy |
| INFO xuất trùng hai lần | Thêm handler riêng nhưng vẫn dùng parent handlers | Kiểm tra `getHandlers()` và `getUseParentHandlers()` |
| Có logger nhưng không có bản ghi | Không có handler phù hợp, handler bị tắt, filter loại hoặc output nằm nơi khác | Theo tuyến Logger → Handler → Formatter → stdout/stderr/file |
| Log xuất ở stderr thay vì stdout | `ConsoleHandler` thường dùng stderr | Kiểm tra cả hai stream, đừng suy luận log bị mất |
| Message còn nguyên `{0}` | Formatter tùy chỉnh không gọi `formatMessage(record)` | Dùng Formatter xử lý parameters đúng |
| Stack trace bị mất | Chỉ ghi `exception.getMessage()` hoặc custom formatter bỏ `record.getThrown()` | Truyền Throwable; dùng formatter có xử lý exception |
| `logging.properties` không có tác dụng | JVM property sai thời điểm/đường dẫn, framework điều khiển backend hoặc mã override level | Kiểm tra lệnh JVM, file được nạp và cấu hình sau startup |
| Tưởng `Logger` của SLF4J là JUL | Import khác nhau | Xem tên package và method signatures |
| Một logger hoạt động không ổn định khi mã không giữ tham chiếu | Quản lý vòng đời logger có tên và tham chiếu yếu | Giữ logger `static final` theo lớp thay vì tạo rồi bỏ liên tục |
| Log quá dài hoặc lộ dữ liệu | Nối chuỗi hoặc ghi cả object/raw payload | Chọn field cần thiết, tránh dữ liệu nhạy cảm, dùng lazy log nếu phù hợp |
| Log từ nhiều thread khó liên hệ | Thiếu requestId/jobId/traceId | Đưa ID vào message/structured context, không vào tên Logger |

### Quy trình kiểm tra khi không thấy log

1. Xác nhận đường đi mã có thật sự chạy tới câu lệnh logger.
2. Kiểm tra logger thuộc JUL hay API khác và xác định đúng tên logger.
3. Kiểm tra level trực tiếp hoặc kế thừa, rồi thử `isLoggable(level)`.
4. Xem Filter tại logger, danh sách Handler và `setUseParentHandlers`.
5. Kiểm tra từng Handler: level, Filter, Formatter và đích xuất.
6. Xem log ở **stderr**, file hoặc container log; không giả định tất cả vào stdout.
7. Nếu đang dùng bridge/framework, kiểm tra dependency, vòng chuyển tiếp và cấu hình logging đang nạp thực tế.

Nếu một LogRecord bị loại ở Logger, tăng level của Handler không đủ. Nếu Logger chấp nhận nhưng Handler loại, thay mỗi level của Logger cũng không giải quyết vấn đề.

## 15. Bài tập thực hành

Giả sử cấu hình JUL như sau:

~~~text
Parent logger: demo.orders, level = WARNING
Child logger:  demo.orders.payment, level = null
Parent handler level = INFO
Child không có handler riêng
Child dùng parent handlers
~~~

Hãy dự đoán:

1. `child.info("start")` có được Logger chấp nhận không?
2. `child.warning("retry")` có được xuất ở parent handler không?
3. Nếu `child.setLevel(Level.FINE)`, lời gọi `child.fine("details")` có được xuất không?
4. Sau đó nếu `parentHandler.setLevel(Level.ALL)`, câu 3 thay đổi như thế nào?
5. Nếu `child.setUseParentHandlers(false)` mà vẫn không có handler riêng, bản ghi WARNING sẽ đi đâu?

**Đáp án:**

1. **Không**: child kế thừa WARNING nên INFO bị loại tại nguồn.
2. **Có**: WARNING qua được child và parent handler ở mức INFO.
3. **Chưa xuất**: child chấp nhận FINE, nhưng parent handler ở mức INFO loại FINE.
4. **Xuất**: handler cho phép ALL. Level WARNING của parent logger không được áp lại để lọc sự kiện mà child đã chấp nhận.
5. **Không có đích xuất** ở cấu hình đang xét, vì child đã ngừng chuyển tới handler cha nhưng không có handler riêng. Việc không có output không chứng minh level của child đã bị tắt.

Bài tập nhấn mạnh hai bước độc lập: **Logger có chấp nhận event không** và **event có đi tới Handler chấp nhận nó không**.

## 16. Ghi nhớ để sử dụng Logger của JDK hiệu quả

Khi viết Java Core, hãy tạo **`private static final Logger` theo lớp**, dùng tên logger ổn định, chọn mức log theo tác động thực tế, truyền template/parameters hoặc Throwable đúng overload và đặt cấu hình level/handler ở nơi có thể quản lý tập trung.

Muốn bật log chi tiết cho một nhóm lớp, dùng **hierarchy và level theo package**. Muốn điều khiển đầu ra, xem **Handler, Formatter, Filter và parent handlers**. Với code cần debug tốn chi phí, cân nhắc **Supplier**. Với dữ liệu nhạy cảm, loại bỏ từ nguồn phát.

**Logger của JDK là đủ cho nhiều ứng dụng Java cơ bản**, nhưng khi tích hợp framework hoặc hệ thống logging khác, phải xác định chính xác API và backend đang chạy. Một lệnh `logger.info(...)` chỉ bắt đầu một log event; mức log, cấu hình và handler mới quyết định bản ghi có xuất hiện và có hữu ích để điều tra hay không.