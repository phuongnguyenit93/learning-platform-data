# Tạo logger trong Java

**Logger** là đối tượng mà mã Java sử dụng để phát các sự kiện cần ghi nhận: bắt đầu một thao tác, hoàn tất xử lý, phát hiện bất thường hoặc bắt được ngoại lệ. Khi tạo logger đúng cách, mỗi sự kiện có **định danh nguồn phát ổn định**, đi theo cấu hình logging của ứng dụng và có thể truy tìm theo lớp, package hoặc nhóm chức năng.

Bài này tập trung vào **cách tạo và lấy logger**, nơi đặt tham chiếu, cách đặt tên, sự khác nhau giữa `java.util.logging` (JUL), SLF4J và Log4j 2, cùng những lỗi thường gặp. Ví dụ chính dùng **Java 17+ và JUL có sẵn trong JDK**, không cần thư viện bên ngoài.

## 1. Logger là gì và việc “tạo logger” có nghĩa gì?

Một sự kiện logging đi qua các vai trò khái niệm sau:

```text
Mã ứng dụng
    |
    | gọi logger.info(...) / logger.log(...)
    v
Logger được định danh theo tên
    |
    | kiểm tra level/filter tại logger
    v
Log event / LogRecord
    |
    | truyền tới handler/appender theo cấu hình
    v
Đích nhận: console, file, hệ thống thu thập log...
```

Lấy logger chỉ tạo hoặc truy xuất **đầu mối phát log**. Thao tác này không đảm bảo một file sẽ được mở, không tự gắn handler mới vào mọi logger và không quyết định rằng mọi thông điệp sẽ xuất hiện ở console. **Logger** quyết định sự kiện được phát từ đâu và mức nào có thể được phát; **handler/appender** cùng cấu hình backend quyết định cách lọc, định dạng, phân phối và ghi tới đích.

Ba khái niệm cần tách bạch:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Tên logger** | Nguồn phát/category của sự kiện | `com.example.order.OrderService` |
| **Mức log** | Mức độ chi tiết hoặc mức nghiêm trọng | JUL: `FINE`, `INFO`, `WARNING`, `SEVERE` |
| **Handler/appender** | Nơi chuyển sự kiện tới và cách xử lý thêm | `ConsoleHandler`, rolling file, collector |

Một yêu cầu HTTP có thể được xử lý qua nhiều logger của các lớp khác nhau. ID yêu cầu được mang theo **log event**, trong khi logger name thường giữ nguyên theo lớp. Không tạo một logger mới có tên thay đổi theo từng request.

## 2. Tạo logger trong JUL bằng `Logger.getLogger`

JDK cung cấp `java.util.logging.Logger`. Trong một lớp Java, cách khai báo phổ biến là:

```java
import java.util.logging.Logger;

public final class OrderService {
    private static final Logger LOGGER =
            Logger.getLogger(OrderService.class.getName());

    public void createOrder(String orderId) {
        LOGGER.info("Creating order");
    }
}
```

Đoạn này là một lớp hợp lệ, có thể lưu trong `OrderService.java` và biên dịch với JDK, nhưng **không có `main` để chạy độc lập**. `OrderService.class.getName()` trả về tên lớp đầy đủ, gồm package nếu có, ví dụ `com.example.order.OrderService`.

**Vì sao dùng `private static final`?**

- `private`: logger phục vụ triển khai nội bộ của lớp, không cần phơi ra thành API nghiệp vụ.
- `static`: các instance của cùng lớp dùng chung một tham chiếu, tránh thao tác lấy logger lặp lại trong mỗi lời gọi.
- `final`: tham chiếu không bị gán sang logger khác sau khi khởi tạo.
- `OrderService.class.getName()`: tên logger ổn định, theo sát tên lớp khi đổi package/refactor.

Tên biến có thể là `LOGGER`, `LOG` hoặc `log`, tùy quy ước codebase. **Tên biến** không phải **tên logger**: việc đổi `LOGGER` thành `LOG` không làm thay đổi logger name được tạo bởi `getLogger(...)`.

### `Logger.getLogger(String)` hoạt động như thế nào?

JUL dùng `LogManager` để quản lý các logger được đặt tên. `Logger.getLogger(name)` tìm một logger đã tồn tại theo tên trong ngữ cảnh quản lý thích hợp hoặc đăng ký một logger tương ứng. Lời gọi không có nghĩa là tạo ra một instance độc lập mới mỗi lần. Trong ứng dụng bình thường, trường `static final` giúp giữ tham chiếu ổn định; `LogManager` có thể giữ tham chiếu yếu đối với logger do ứng dụng tạo, nên không nên dựa vào việc gọi lại một tên sau khi không còn tham chiếu mạnh để lưu trạng thái tùy chỉnh.

Không tự gọi `new Logger(...)` cho nhu cầu thông thường: constructor của JUL `Logger` không phải API công khai để tạo logger ứng dụng, và hệ thống có `LogManager` để quản lý tên cũng như phân cấp.

Nếu khai báo logger trong nhiều lớp, hãy dùng **tên lớp của chính lớp đó**. Ví dụ, `InvoiceService` nên lấy `Logger.getLogger(InvoiceService.class.getName())`, thay vì sao chép nhầm tên `OrderService` làm log khó truy nguồn.

## 3. Chương trình Java 17 hoàn chỉnh: lấy logger và ghi ba sự kiện

Ví dụ tạo một logger theo tên lớp và **gắn một `ConsoleHandler` cho riêng chương trình minh họa**. Ta cấu hình mức `FINE` cho cả logger và handler, dùng formatter cố định để có output dễ kiểm tra.

Lưu thành **`CreateLoggerDemo.java`**:

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class CreateLoggerDemo {
    private static final Logger LOGGER =
            Logger.getLogger(CreateLoggerDemo.class.getName());

    public static void main(String[] args) {
        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.FINE);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " " + record.getLoggerName()
                        + " - " + formatMessage(record)
                        + System.lineSeparator();
            }
        });

        LOGGER.setUseParentHandlers(false);
        LOGGER.setLevel(Level.FINE);
        LOGGER.addHandler(console);

        try {
            LOGGER.fine("stage=start");
            LOGGER.log(Level.INFO,
                    "requestId={0} stage=validated", "req-17");
            LOGGER.warning("stage=done");
        } finally {
            LOGGER.removeHandler(console);
            console.close();
        }
    }
}
```

Biên dịch và chạy với **JDK 17 hoặc mới hơn**:

```bash
javac -encoding UTF-8 CreateLoggerDemo.java
java CreateLoggerDemo
```

**Đầu ra chính xác trên `stderr`:**

```text
FINE CreateLoggerDemo - stage=start
INFO CreateLoggerDemo - requestId=req-17 stage=validated
WARNING CreateLoggerDemo - stage=done
```

Chương trình không chủ động ghi ra `stdout`. JUL `ConsoleHandler` mặc định ghi vào `System.err`. Một terminal hiển thị đồng thời stdout/stderr vẫn có thể cho thấy các dòng trên; công cụ chỉ thu stdout thì không.

Phân tích chương trình:

1. `Logger.getLogger(CreateLoggerDemo.class.getName())` lấy logger có tên `CreateLoggerDemo` (vì lớp đang ở package mặc định của ví dụ).
2. `LOGGER.setLevel(Level.FINE)` cho logger phát các record có mức `FINE` trở lên; `console.setLevel(Level.FINE)` bảo đảm handler không loại riêng dòng `FINE`.
3. `LOGGER.setUseParentHandlers(false)` chặn việc chuyển tiếp record đến handler của logger cha, tránh phần output bổ sung do cấu hình môi trường. **Không tự động áp dụng lệnh này cho mọi logger production** nếu đang dựa vào hệ thống logging tập trung.
4. `Formatter.formatMessage(record)` định dạng thông điệp JUL có tham số `{0}`; chuỗi `requestId={0}` biến thành `requestId=req-17`. JUL sử dụng cú pháp này theo `MessageFormat`, khác với `{}` thường dùng ở SLF4J.
5. `removeHandler` và `close` xử lý vòng đời handler mà ví dụ chủ động gắn vào logger. Trong ứng dụng thật, handler/appender chung nên được quản lý tập trung khi khởi động và tắt ứng dụng.

Formatter cố ý bỏ timestamp để output xác định; khi vận hành thực tế, log cần timestamp có múi giờ, thành phần, correlation ID và thông tin ngoại lệ phù hợp.

### Thử thay đổi mức log

Giữ nguyên logger ở `Level.FINE` nhưng thay:

```java
console.setLevel(Level.WARNING);
```

Đây là một **chỉnh sửa một dòng trong chương trình trên**, không phải chương trình độc lập. Khi chạy lại, handler chỉ ghi dòng `WARNING`; `FINE` và `INFO` đã được logger phát nhưng bị handler lọc. Nếu đặt **`LOGGER.setLevel(Level.INFO)`**, sự kiện `FINE` bị chặn ngay tại logger, nên dù handler đặt `FINE`, nó cũng không thể khôi phục record chưa được phát.

## 4. Nên tạo một logger theo lớp hay theo tên tùy chọn?

### Định danh theo lớp

```java
private static final Logger LOGGER =
        Logger.getLogger(InventoryService.class.getName());
```

Đoạn này giả định đang nằm trong lớp `InventoryService`. Tên đầy đủ của class thường phù hợp với hệ phân cấp package, ví dụ `com.example.inventory.InventoryService`. Khi điều tra, có thể lọc log theo class hoặc package.

### Định danh theo category

```java
private static final Logger AUDIT_LOG =
        Logger.getLogger("com.example.audit");
```

Đặt tên thủ công có thể hợp lý khi dự án định nghĩa một category dùng chung, ví dụ log truy cập hoặc audit. Tuy nhiên, nếu tất cả lớp đều dùng một tên chung `"application"`, việc tìm nơi phát sự kiện sẽ khó hơn. Với audit mang yêu cầu pháp lý hoặc giao dịch, một logger thông thường không thay thế hệ thống audit bền vững có kiểm soát.

### Không tạo logger theo người dùng hoặc request

```java
// Đoạn không nên áp dụng; requestId là biến có sẵn.
Logger logger = Logger.getLogger("request." + requestId);
```

Nếu tên logger biến đổi theo hàng triệu yêu cầu, sẽ xuất hiện nhiều category khó cấu hình và dễ tạo áp lực quản lý. Thay vào đó, dùng một logger ổn định theo lớp và truyền `requestId`, `jobId` hoặc correlation ID vào **nội dung/metadata của sự kiện**. Không đưa dữ liệu nhạy cảm trực tiếp vào tên logger.

### Đặt logger ở trường instance có được không?

Có, nếu thiết kế thực sự cần một logger thay thế được, injection hoặc abstraction riêng. Nhưng việc khai báo `Logger.getLogger(...)` tại từng đối tượng thường không có lợi nếu cùng một lớp sử dụng cùng tên. Đa số ứng dụng Java chọn **một trường `private static final` cho mỗi lớp**.

## 5. Tạo logger với SLF4J (thường dùng cùng Logback)

Nhiều ứng dụng hiện đại dùng **SLF4J** làm API chung. Cú pháp khác JUL:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class PaymentService {
    private static final Logger LOG =
            LoggerFactory.getLogger(PaymentService.class);

    public void authorize(String paymentId) {
        LOG.info("Authorizing paymentId={}", paymentId);
    }
}
```

Đây là lớp hợp lệ trong **dự án đã cung cấp SLF4J API cùng provider/backend tương thích**, chẳng hạn Logback; **không biên dịch với JDK thuần** nếu thiếu dependency.

`LoggerFactory.getLogger(PaymentService.class)` lấy logger đặt tên theo lớp. SLF4J là **facade/API**; phía sau phải có provider xử lý logging. Khi dùng Logback, các `Appender`, `Encoder`, mức log và rolling file được cấu hình ở Logback, không phải bằng cách tạo appender trong từng `PaymentService`.

Placeholder của SLF4J là **`{}`**:

```java
// Fragment: LOG thuộc SLF4J; paymentId và status đã có trong phương thức.
LOG.info("paymentId={} status={}", paymentId, status);
```

Không sao chép cú pháp này vào JUL. JUL có cách truyền tham số và formatter riêng, ví dụ `LOGGER.log(Level.INFO, "paymentId={0}", paymentId)`.

Khi một thư viện hoặc framework đã chọn SLF4J làm API chính, mã nghiệp vụ nên tuân theo quy ước đó. Không thêm backend khác tùy ý chỉ để có `LoggerFactory`: nhiều provider hoặc các bridge không tương thích có thể khiến hệ thống vận hành khó đoán.

### Logger do Lombok tạo

Nếu dự án đã cài **Lombok** và bật xử lý annotation, `@Slf4j` có thể sinh trường logger SLF4J:

```java
import lombok.extern.slf4j.Slf4j;

@Slf4j
public class ShippingService {
    public void ship(String shipmentId) {
        log.info("Shipping shipmentId={}", shipmentId);
    }
}
```

Đây không phải ví dụ JDK thuần. Lombok giảm phần khai báo nhưng **không phải backend ghi log**; vẫn cần SLF4J và provider/runtime phù hợp. Việc sử dụng Lombok là lựa chọn của codebase, không phải điều kiện bắt buộc để tạo logger.

## 6. Tạo logger bằng Log4j 2

Nếu ứng dụng dùng API Log4j 2 trực tiếp, có thể viết:

```java
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

public final class ReportService {
    private static final Logger LOG =
            LogManager.getLogger(ReportService.class);

    public void generate(String reportId) {
        LOG.info("Generating reportId={}", reportId);
    }
}
```

Đoạn này cần các dependency Log4j 2 thích hợp, không chạy chỉ với JDK. `LogManager.getLogger(ReportService.class)` lấy logger theo lớp. Nếu backend là Log4j 2 nhưng ứng dụng đã dùng SLF4J làm facade, mã nghiệp vụ **vẫn có thể lấy logger qua `LoggerFactory`**, miễn là provider/binding được cấu hình đúng. Không cần đổi sang Log4j API chỉ vì backend lưu log là Log4j.

| Hệ sinh thái | Factory/lời gọi lấy logger | Kiểu logger | Đầu ra do ai quản lý? |
| --- | --- | --- | --- |
| JUL | `Logger.getLogger(MyClass.class.getName())` | `java.util.logging.Logger` | JUL `Handler` và cấu hình JUL |
| SLF4J | `LoggerFactory.getLogger(MyClass.class)` | `org.slf4j.Logger` | Provider/backend, thường là Logback hoặc triển khai tương thích |
| Log4j 2 API | `LogManager.getLogger(MyClass.class)` | `org.apache.logging.log4j.Logger` | Log4j Core/triển khai cấu hình thực tế |
| Lombok `@Slf4j` | Sinh trường `log` khi biên dịch | Logger SLF4J | Provider/backend SLF4J |

**Bẫy về import:** JUL, SLF4J và Log4j 2 đều có lớp/interface tên `Logger`, nhưng chúng không phải một kiểu. Tránh trộn `import java.util.logging.Logger` với `LoggerFactory.getLogger(...)` hoặc truyền `org.slf4j.Logger` vào API chỉ nhận JUL `Logger`.

### `System.getLogger` có giống JUL không?

JDK 9+ còn cung cấp:

```java
System.Logger log = System.getLogger("com.example.ReportService");
log.log(System.Logger.Level.INFO, "Starting report");
```

Đây là **`java.lang.System.Logger`**, một API khác với `java.util.logging.Logger`, sử dụng cơ chế `System.LoggerFinder` của runtime để chọn triển khai. Không ép kiểu giữa hai kiểu logger hoặc áp dụng máy móc mọi quy tắc cấu hình JUL cho `System.Logger`. Chọn API theo kiến trúc dự án.

## 7. Logger name, package và kế thừa cấu hình JUL

Logger JUL có phân cấp tên bằng dấu chấm, ví dụ:

```text
(com.example)
   |
   +-- com.example.order
          |
          +-- com.example.order.OrderService
          +-- com.example.order.OrderController
```

Sơ đồ minh họa **phân cấp tên**, không khẳng định mọi logger cha luôn đã tồn tại như một đối tượng do code khai báo. `LogManager` quản lý quan hệ giữa các logger được tạo và có thể tạo/điều chỉnh liên kết cha khi các logger xuất hiện.

Hai cơ chế dễ nhầm:

- **Level được kế thừa:** nếu `logger.getLevel() == null`, logger có thể lấy **level hiệu lực** từ cha; `null` không đồng nghĩa với `OFF` hoặc lỗi.
- **Handler được kế thừa đường phát:** nếu `logger.getUseParentHandlers()` là `true`, record đã được logger chấp nhận có thể đi đến handler của logger cha. Handler cha vẫn áp dụng level/filter riêng của nó.

Điều này giải thích vì sao logger vừa được lấy mà vẫn có log dù ứng dụng không gắn handler trực tiếp: hệ thống có thể đã cấu hình handler của root logger.

Cẩn thận với việc gắn một `ConsoleHandler` riêng vào từng logger con trong khi root logger cũng ghi console. Khi propagation bật, sự kiện có thể **xuất hiện hai lần** ở cùng đích. Ví dụ trước dùng `setUseParentHandlers(false)` để có output xác định; ứng dụng production nên xác định rõ ai quản lý đường đi chung.

JUL cho phép quản lý cấu hình thông qua `LogManager` và file `logging.properties` (tùy cách bootstrap runtime). Việc gọi `Logger.getLogger(...)` trong mã nghiệp vụ không thay thế cấu hình hệ thống. Đối với SLF4J/Logback, các level, appender và additivity được cấu hình theo quy ước của Logback; không dùng syntax file `logging.properties` của JUL để cấu hình nhầm Logback.

## 8. Hiệu năng, exception và ngữ cảnh sau khi tạo logger

### Không tạo message đắt đỏ nếu level đã tắt

Một ví dụ có thể tốn tài nguyên:

```java
// Fragment: expensiveSummary() là phương thức ứng dụng tự định nghĩa.
LOGGER.fine("state=" + expensiveSummary());
```

Dù `FINE` đang bị tắt, Java vẫn tính biểu thức `expensiveSummary()` trước khi gọi `fine`. JUL hỗ trợ supplier tạo message lười:

```java
// Fragment: LOGGER là java.util.logging.Logger; Level đã được import.
LOGGER.log(Level.FINE, () -> "state=" + expensiveSummary());
```

Supplier chỉ được gọi nếu mức log được logger chấp nhận. Điều đó không bảo đảm mọi handler sẽ ghi record; handler còn có level/filter riêng. Không dựa vào side effect trong supplier vì khi mức log tắt, side effect không xảy ra.

Ở SLF4J, dùng placeholder `{}` giúp tránh nối chuỗi trước lời gọi:

```java
// Fragment: LOG là org.slf4j.Logger; count là số đã tính.
LOG.debug("Processed {} records", count);
```

Tuy nhiên, nếu viết `LOG.debug("Report {}", expensiveSummary())` thì biểu thức `expensiveSummary()` vẫn được Java gọi trước khi vào API. Với phép tính tốn kém, dùng cơ chế lazy hoặc kiểm tra mức phù hợp của API/backend.

### Logger không thay thế xử lý lỗi

Có logger rồi, khi gặp exception vẫn phải quyết định nghiệp vụ: trả lỗi, rollback, retry, khởi động lại hay ném tiếp. Để lưu dấu vết kỹ thuật, nên truyền **đối tượng `Throwable`**:

```java
// Fragment bên trong khối catch, LOGGER và exception e đã tồn tại.
LOGGER.log(Level.SEVERE, "Could not initialize settings", e);
```

Backend/formatter sẽ quyết định cách hiển thị stack trace. Chỉ ghi `e.getMessage()` thường bỏ mất lớp gây lỗi và chuỗi `Caused by`. Cũng tránh log cùng một exception đầy đủ ở mọi tầng rồi ném tiếp nếu không có thêm ngữ cảnh, vì một lỗi có thể bị ghi như nhiều sự cố.

### Định danh theo lớp, ngữ cảnh theo sự kiện

`requestId`, `jobId`, phiên bản triển khai và những trường liên quan nên gắn vào sự kiện để điều tra. Hệ sinh thái logging có thể có MDC/thread context hoặc cơ chế khác để bổ sung các trường. Nhưng ngữ cảnh theo thread **không tự động truyền qua mọi thread pool hoặc service**; khi dùng bất đồng bộ phải thiết kế truyền và dọn ngữ cảnh đúng cách. Không bao giờ log token, mật khẩu, cookie phiên hay dữ liệu nhạy cảm không cần thiết.

## 9. Những lỗi thường gặp khi tạo logger

| Vấn đề | Vì sao xảy ra | Cách kiểm tra hoặc khắc phục |
| --- | --- | --- |
| `getLogger` thành công nhưng không thấy log | Logger level, handler/appender level, filter hoặc sink | Xác định đường đi từ logger đến đích; kiểm tra tất cả điểm lọc |
| Không thấy dòng `FINE` | Logger hoặc handler chỉ cho phép `INFO` trở lên | Kiểm tra `isLoggable(Level.FINE)` và handler level |
| Một sự kiện in hai lần | Con và cha cùng ghi console, handler gắn trùng, bridge logging | Kiểm tra propagation/additivity và đường đi của sự kiện |
| Tất cả log đều mang cùng một tên lớp | Sao chép nhầm `.class` khi tạo logger | Lấy tên lớp đang sở hữu trường logger |
| Lỗi biên dịch `LoggerFactory` hoặc `LogManager` | Sai import/dependency hoặc nhầm JUL với SLF4J/Log4j | Kiểm tra FQCN, API đã chọn và backend tương thích |
| SLF4J chạy nhưng log không đến đích mong muốn | Thiếu/sai provider hoặc cấu hình appender | Kiểm tra provider/runtime và cấu hình backend |
| Tạo logger mới với tên động ở mỗi request | Quá nhiều category, khó quản lý | Logger theo lớp; correlation ID ở log event |
| Dùng `System.out.println` thay logger | Không có level, category và chính sách thống nhất | Sử dụng logger phù hợp cùng cấu hình chung |
| Dùng `LOGGER.fine("x=" + heavy())` khi mức tắt | Giá trị đắt đỏ vẫn được tạo | Supplier hoặc guard phù hợp |
| Lấy logger mỗi lần xử lý và gắn handler mới | Dễ nhân đôi log, tăng tài nguyên | Lấy logger theo lớp; quản lý handler tập trung |
| Log có message nhưng thiếu stack trace | Không truyền `Throwable` hoặc formatter bỏ thông tin lỗi | Truyền exception và kiểm tra formatter/backend |
| Log chỉ có ở stderr | JUL `ConsoleHandler` dùng stderr | Cấu hình công cụ thu thập đúng stream |

**Không suy ra rằng logger chưa được tạo chỉ vì console không hiển thị gì.** Logger có thể đã phát sự kiện nhưng handler chặn, đích ghi có lỗi, hoặc hệ thống thu thập đang đọc nhầm stdout/stderr.

## 10. Cách tự kiểm tra sau khi tạo logger

Khi thêm logger vào một lớp, có thể đi theo các bước sau:

1. **Chọn đúng API:** JUL nếu muốn dùng tính năng có sẵn của JDK; SLF4J hay Log4j 2 nếu dự án đã chọn ecosystem đó. Không trộn `Logger` từ các package khác nhau.
2. **Đặt tên theo lớp:** ưu tiên tên đầy đủ để lọc theo package; không đưa `requestId` vào logger name.
3. **Khai báo một lần:** dùng `private static final` khi phù hợp; không lấy/gắn handler lại ở mỗi request.
4. **Xác định cấu hình thực tế:** level hiệu lực ở logger, handler/appender, formatter và propagation.
5. **Chạy thử các mức:** phát `INFO`, một mức chi tiết và một cảnh báo/exception; đối chiếu đúng console/file/collector.
6. **Kiểm tra thông điệp:** có ngữ cảnh, không chứa bí mật, không tạo dữ liệu nặng khi mức log bị tắt.
7. **Kiểm tra đồng thời và vòng đời:** một logger dùng chung cho nhiều luồng là thông thường; không đóng handler chung trước khi ứng dụng kết thúc.

**Kết quả cần đạt:** Khi đọc một dòng `Logger.getLogger(...)`, `LoggerFactory.getLogger(...)` hoặc `LogManager.getLogger(...)`, bạn biết **logger được định danh theo gì**, **nó thuộc API nào**, **đâu là phần cấu hình đích ghi**, và **cần kiểm tra điểm nào khi một sự kiện không xuất hiện**. Một logger tốt có tên nhất quán, được tái sử dụng đúng phạm vi và phát log qua hệ thống logging được cấu hình có chủ đích.
