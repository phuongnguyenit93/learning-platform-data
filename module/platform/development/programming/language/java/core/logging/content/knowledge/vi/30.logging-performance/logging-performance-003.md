# Parameterized logging trong Java: ghi log đúng cách và tối ưu hiệu năng

## 1. Parameterized logging là gì?

**Parameterized logging** là cách truyền **mẫu thông điệp (message template)** và **các giá trị tham số (arguments)** riêng biệt cho API logging. Framework quyết định có ghi sự kiện hay không, sau đó mới định dạng thông điệp theo quy tắc của API. Cách này thường giảm chi phí tạo chuỗi không cần thiết khi mức log bị tắt, đồng thời giữ message nhất quán và dễ tìm kiếm.

Thay vì ghép chuỗi ngay tại nơi gọi:

~~~java
// String được ghép trước khi lời gọi debug có cơ hội kiểm tra level.
log.debug("orderId=" + orderId + ", status=" + status);
~~~

Với **SLF4J** hoặc **Log4j 2**:

~~~java
log.debug("orderId={} status={}", orderId, status);
~~~

Ở đây, `{}` là placeholder theo các API này. Framework nhận mẫu và các đối số riêng. Khi DEBUG bị tắt, logger thường có thể bỏ qua việc định dạng/`toString()` của đối số. Tối ưu này chỉ có ý nghĩa nếu không có thao tác tốn kém khác xảy ra trước khi gọi logger.

**Không nhầm các khái niệm:**

- **Parameterized message:** giữ mẫu và đối số tách biệt, ví dụ `"user={} action={}"` và `userId`, `action`.
- **Lazy/supplier logging:** trì hoãn **việc tạo đối số hoặc thông điệp**, ví dụ `() -> expensiveCalculation()`. Đây là một mức trì hoãn bổ sung.
- **Structured logging:** ghi trường như `userId`, `requestId`, `durationMs` thành các thuộc tính có tên trong log event hoặc JSON. Một message có placeholder chưa chắc là structured event.
- **Asynchronous logging:** producer đưa event vào queue để xử lý sau. Async và parameterized có thể kết hợp nhưng giải quyết hai bài toán hiệu năng khác nhau.

Mục tiêu là **giảm chi phí trên đường nóng (hot path)** trong khi log vẫn đủ ngữ cảnh, đúng level và không làm mất thông tin lỗi.

## 2. Vì sao nối chuỗi sớm gây lãng phí?

Java đánh giá biểu thức tham số **trước khi** gọi method. Với lệnh:

~~~java
log.debug("payload=" + serializeLargeObject(payload));
~~~

Nếu DEBUG bị tắt, phép `serializeLargeObject(payload)` và phép nối chuỗi vẫn có thể đã chạy. Logger không thể lấy lại thời gian CPU hoặc bộ nhớ đã cấp phát trước lời gọi.

Với dạng:

~~~java
log.debug("payload={}", payload);
~~~

Khi level bị tắt, nhiều implementation tránh định dạng và tránh gọi `payload.toString()`. Tuy nhiên, nếu viết:

~~~java
log.debug("payload={}", serializeLargeObject(payload));
~~~

thì `serializeLargeObject(payload)` **vẫn được gọi trước khi logger kiểm tra level**. Parameterized logging không tự động làm lazy mọi biểu thức tham số.

Dòng thời gian cần hình dung:

~~~text
A. Ghép chuỗi / gọi hàm đắt trước logger:
   buildString/expensive() -> logger.debug(...) -> kiểm tra level -> bỏ

B. Truyền đối tượng đã có:
   logger.debug(template, object) -> kiểm tra level -> (nếu bật) format/toString -> appender

C. Supplier ở API hỗ trợ:
   tạo supplier -> kiểm tra level -> (nếu bật) gọi supplier -> format -> appender
~~~

Ba trường hợp khác nhau về chi phí:

| Tình huống | Khi DEBUG tắt, chi phí còn lại |
| --- | --- |
| `"id=" + id` | Vẫn đánh giá phép ghép và các biểu thức liên quan; JIT có thể tối ưu một phần nhưng không nên dựa vào đó |
| `"id={}", id` | Đánh giá tham số và lời gọi logger; thường tránh format message |
| `"obj={}", obj` | Không tạo chuỗi từ `obj.toString()` khi framework bỏ qua event sớm; đối tượng `obj` đã phải tồn tại |
| `"x={}", expensive()` | **Vẫn gọi `expensive()`**, bất kể level |
| Supplier `() -> expensive()` | API hỗ trợ có thể trì hoãn `expensive()` cho đến khi mức log bật |
| `if (log.isDebugEnabled()) { ... }` | Tránh biểu thức đắt trong khối khi DEBUG tắt; chi phí thêm một phép kiểm tra level |

Khi mức log **được bật**, logger vẫn phải tạo event, format/encode, có thể lấy stack trace và ghi ra sink. Parameterized logging không làm chi phí I/O tự biến mất.

## 3. Cú pháp khác nhau giữa JUL, SLF4J và Log4j 2

Không có **một cú pháp placeholder chung cho mọi API logging Java**.

| API | Cách gọi tham số hóa | Cú pháp mẫu | Đặc điểm |
| --- | --- | --- | --- |
| JUL (`java.util.logging`) | `logger.log(Level.INFO, "user={0}", userId)` | `{0}`, `{1}` | Thường định dạng bằng `java.text.MessageFormat` ở `Formatter.formatMessage(...)` |
| `System.Logger` (Java 9+) | `logger.log(System.Logger.Level.INFO, "user={0}", userId)` | `{0}`, `{1}` | API logging cấp hệ thống của JDK, có overload Supplier |
| SLF4J 1.x/2.x | `log.info("user={}", userId)` | `{}` | API facade; backend/provider quyết định sink |
| SLF4J 2.x Fluent | `log.atInfo().addArgument(userId).log("user={}")` | `{}` | Hỗ trợ Supplier, key-value và cause |
| Log4j 2 API mặc định | `log.info("user={}", userId)` | `{}` | Message factory mặc định sử dụng `ParameterizedMessage` |

**Cú pháp thường nhầm:**

~~~java
// Với JUL: {0} là placeholder; {} không phải placeholder chuẩn.
julLogger.log(java.util.logging.Level.INFO, "user={0}", userId);

// Với SLF4J và Log4j 2 mặc định: {} là placeholder.
slf4jLogger.info("user={}", userId);
~~~

Hai dòng là **minh họa API**, cần các biến logger tương ứng đã được tạo. Không copy tên biến `slf4jLogger` vào chương trình thuần JDK mà chưa thêm thư viện SLF4J.

Không áp dụng `String.format("user=%s", userId)` cho SLF4J rồi hy vọng framework hoãn việc tạo chuỗi: vì `String.format(...)` chạy ngay trước khi logger nhận giá trị.

## 4. Ví dụ Java 17 chạy độc lập: tham số và Supplier thực sự khác nhau

Ví dụ dùng **JUL**, không cần bất cứ dependency ngoài JDK. Một biến đếm cho biết phương thức `expensive()` đã được gọi bao nhiêu lần khi level `FINE` bị tắt.

Tạo file **ParameterizedLoggingDemo.java**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class ParameterizedLoggingDemo {
    private static final Logger LOG =
            Logger.getLogger(ParameterizedLoggingDemo.class.getName());
    private static final AtomicInteger CALLS = new AtomicInteger();

    private static String expensive() {
        CALLS.incrementAndGet();
        return "computed";
    }

    public static void main(String[] args) {
        ConsoleHandler handler = new ConsoleHandler();
        handler.setLevel(Level.ALL);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " "
                        + formatMessage(record) + System.lineSeparator();
            }
        });

        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO); // FINE không được ghi.
        LOG.addHandler(handler);
        try {
            // expensive() VẪN chạy dù FINE đã tắt.
            LOG.log(Level.FINE, "disabled arg={0}", expensive());
            // Supplier KHÔNG chạy nếu FINE tắt.
            LOG.log(Level.FINE, () -> "disabled supplier=" + expensive());

            // JUL dùng {0}, {1}; Formatter xử lý arguments.
            LOG.log(Level.INFO, "order={0} state={1}",
                    new Object[] {"A17", "paid"});
            LOG.log(Level.INFO, () -> "computed=" + expensive());
            System.out.println("expensiveCalls=" + CALLS.get());
        } finally {
            LOG.removeHandler(handler);
            handler.flush();
            handler.close();
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 hoặc mới hơn**:

~~~bash
javac --release 17 ParameterizedLoggingDemo.java
java ParameterizedLoggingDemo
~~~

**Standard error (stderr) chính xác**, do `ConsoleHandler` mặc định gửi ra stderr:

~~~text
INFO order=A17 state=paid
INFO computed=computed
~~~

**Standard output (stdout) chính xác:**

~~~text
expensiveCalls=2
~~~

Chương trình thoát với mã `0`. Giá trị 2 đến từ:

1. `LOG.log(Level.FINE, "disabled arg={0}", expensive())`: **đối số được Java đánh giá trước** lời gọi; bộ đếm tăng lên 1 dù event sau đó bị bỏ.
2. `LOG.log(Level.FINE, () -> ...)`: Supplier không bị thực thi vì `FINE` đã tắt; bộ đếm không đổi.
3. `LOG.log(Level.INFO, "order={0} state={1}", ...)`: trình định dạng nhận hai chuỗi `"A17"` và `"paid"`. Nó không gọi `expensive()`.
4. `LOG.log(Level.INFO, () -> ...)`: `INFO` được bật, Supplier chạy; bộ đếm tăng thành 2.

`formatter.formatMessage(record)` thực hiện định dạng tham số từ `LogRecord`. Nếu một custom formatter chỉ in `record.getMessage()` thì nó có thể in nguyên mẫu `"order={0} state={1}"`; đó là lỗi/khác biệt của formatter, không phải các tham số không được gửi.

`LOG.setUseParentHandlers(false)` tránh root logger in trùng. `handler.setLevel(Level.ALL)` giúp ví dụ chỉ phụ thuộc ngưỡng của logger. Dù `CALLS` là `AtomicInteger` để minh họa đo đếm an toàn, đây **không phải benchmark hiệu năng**.

## 5. JUL: MessageFormat, parameters và lazy message

Trong JUL có hai kỹ thuật riêng:

**5.1. Tham số hóa theo vị trí**

~~~java
logger.log(Level.INFO, "user={0}, action={1}",
        new Object[] {userId, action});
~~~

Đây là đoạn code trong môi trường đã khai báo `java.util.logging.Logger logger`, `Level` và các biến. JUL lưu message template cùng mảng tham số trong `LogRecord`; một `Formatter` như `SimpleFormatter` hoặc formatter gọi `formatMessage(record)` sẽ dùng quy tắc `MessageFormat` khi cần.

Điểm cần nhớ:

- `{0}` là vị trí đầu tiên; `{1}` là vị trí thứ hai. `{}` thường **không** thay thế giá trị trong JUL.
- Quy tắc `MessageFormat` có escaping/format riêng, đặc biệt dấu nháy đơn và dấu ngoặc nhọn. Nếu message chứa ký tự đặc biệt, phải kiểm tra kết quả khi formatter chạy.
- Đừng tự nối chuỗi trước khi gọi: `"user=" + userId` khiến việc ghép đã xảy ra.
- Truyền object vào tham số không có nghĩa mọi phép tính trước đó đều lazy. `new Object[]{...}` và biểu thức chuẩn bị đối số vẫn phải chạy.

**5.2. Trì hoãn xây dựng toàn bộ message bằng Supplier**

~~~java
logger.log(Level.FINE, () -> "snapshot=" + expensiveSnapshot());
~~~

Overload `log(Level, Supplier<String>)` của JUL chỉ gọi supplier nếu mức log được bật. Đối với một exception có sẵn, dùng overload:

~~~java
logger.log(Level.WARNING, exception,
        () -> "Cannot process orderId=" + orderId);
~~~

Đây là đoạn minh họa: `exception` là `Throwable` đã bắt, `orderId` là giá trị có sẵn. Overload `log(Level, Throwable, Supplier<String>)` giữ ngoại lệ trong `LogRecord.thrown` để formatter có thể in stack trace. Không nên ghép `exception.getStackTrace()` thành chuỗi thủ công.

**5.3. Dùng `System.Logger` khi phù hợp**

Từ Java 9, API `System.Logger` cũng hỗ trợ overload thông điệp có tham số theo `MessageFormat` và Supplier:

~~~java
System.Logger sysLog = System.getLogger("demo.orders");
sysLog.log(System.Logger.Level.INFO, "order={0}", orderId);
sysLog.log(System.Logger.Level.DEBUG,
        () -> "snapshot=" + expensiveSnapshot());
~~~

`System.Logger` có cơ chế chuyển tiếp đến backend thông qua `LoggerFinder`. Nó **không** đồng nghĩa với `org.slf4j.Logger` hoặc `java.util.logging.Logger`, và cú pháp tham số vẫn phải theo API cụ thể.

## 6. SLF4J: cách viết hiệu quả với API truyền thống

SLF4J thường sử dụng mẫu `{}`:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class OrderService {
    private static final Logger LOG =
            LoggerFactory.getLogger(OrderService.class);

    public void update(String orderId, String status, long durationMs) {
        LOG.debug("order={} status={} durationMs={}",
                orderId, status, durationMs);
    }
}
~~~

Đây là class Java biên dịch khi dự án đã có **SLF4J API và provider phù hợp** (ví dụ Logback Classic). Nó không độc lập chỉ với JDK.

Ưu điểm:

- Giữ mẫu có ý nghĩa rõ ràng; log event có thể mang arguments riêng cho đến giai đoạn format.
- Đối với DEBUG bị tắt, cách này thường bỏ qua chi phí nối chuỗi và chuyển objects thành text.
- Dễ thống nhất tên trường trong message, ví dụ `orderId={} durationMs={}`.
- Giúp review và tìm kiếm mã nguồn vì mọi sự kiện cùng loại giữ một template.

Nhưng:

~~~java
// expensive() được tính ngay ở call site, dù DEBUG đã tắt.
LOG.debug("report={}", renderLargeReport());
~~~

Để tránh phép tính đắt với **SLF4J 1.x hoặc 2.x truyền thống**:

~~~java
if (LOG.isDebugEnabled()) {
    LOG.debug("report={}", renderLargeReport());
}
~~~

`isDebugEnabled()` bảo vệ biểu thức bên trong. Đây là chọn lựa hợp lệ khi kết quả quá tốn kém. Không cần bọc **mọi** lệnh parameterized log trong `if`; những đối số rẻ đã có thường không cần thêm nhánh.

**Overload đối số:** SLF4J có các overload tối ưu cho 1 hoặc 2 tham số thông thường. Với 3+ arguments, overload varargs có thể tạo mảng `Object[]`. Các bản triển khai và JIT có thể tối ưu khác nhau; không khẳng định “parameterized logging = zero allocations”. Với hot path và lưu lượng lớn, cần đo allocation thực tế.

**Autoboxing:** nếu truyền `int`, `long` hoặc kiểu nguyên thủy vào tham số kiểu `Object`, có thể xảy ra boxing. Trình biên dịch/JIT đôi khi tối ưu được một số trường hợp, nhưng kết quả phụ thuộc code, JDK và backend. Đừng thay mọi log bằng nối chuỗi chỉ để tránh boxing mà quên chi phí format.

## 7. SLF4J 2.x Fluent API: Supplier, key-value và cause

Từ **SLF4J 2.0**, API fluent cho phép xây event từng bước và cung cấp supplier:

~~~java
// Đoạn minh họa, cần biến Logger LOG và phương thức renderLargeReport().
LOG.atDebug()
        .setMessage("report={}")
        .addArgument(() -> renderLargeReport())
        .log();
~~~

Khi DEBUG tắt, builder không thực hiện ghi event và supplier không cần chạy. **Phải kết thúc chuỗi bằng `.log()`**; bỏ `.log()` thì ngay cả khi DEBUG bật cũng không tạo event.

Cũng có thể gọi ngắn gọn:

~~~java
LOG.atDebug().log("order={} status={}", orderId, status);
~~~

Tuy nhiên, gọi `renderLargeReport()` trực tiếp trong `log("report={}", renderLargeReport())` vẫn khiến method chạy trước khi framework xét level. Muốn thực sự trì hoãn, sử dụng `addArgument(Supplier<?>)` hoặc `setMessage(Supplier<String>)` phù hợp.

**Key-value không nhất thiết phải nằm trong message text:**

~~~java
LOG.atInfo()
        .addKeyValue("orderId", orderId)
        .addKeyValue("durationMs", durationMs)
        .setMessage("order completed")
        .log();
~~~

Cách này gắn key-value vào event builder, hữu ích khi backend/encoder hỗ trợ structured logging. **Không tự giả định mọi layout sẽ in đầy đủ key-value**: phải kiểm tra cấu hình encoder và log thu được thực tế.

**Gắn Throwable đúng cách trong fluent API:**

~~~java
LOG.atError()
        .setCause(exception)
        .addKeyValue("orderId", orderId)
        .log("order failed");
~~~

Đoạn minh họa đòi hỏi logger và các biến đã khai báo. `setCause(...)` cho backend biết đó là ngoại lệ, để stack trace có thể xuất hiện theo layout. Đừng biến stack trace thành chuỗi chỉ để nhét vào `{}`.

**Lưu ý phiên bản:** API fluent không có trong SLF4J 1.7. Hệ thống dùng SLF4J 2.x cần provider tương thích; nâng cấp chỉ API mà quên backend có thể khiến ứng dụng dùng NOP hoặc phát cảnh báo.

## 8. Log4j 2: ParameterizedMessage và Suppliers

Log4j 2 API mặc định dùng `{}` với message factory thích hợp:

~~~java
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

public final class BillingService {
    private static final Logger LOG = LogManager.getLogger();

    public void paid(String invoiceId, long amountCents) {
        LOG.info("invoice={} amountCents={}", invoiceId, amountCents);
    }
}
~~~

Đây là class cần **Log4j 2 API và implementation/bridge phù hợp**; không phải ví dụ chạy độc lập bằng JDK. Theo cơ chế mặc định, message thường sử dụng `ParameterizedMessage`; Log4j 2 có tối ưu cho các thông điệp tham số hóa và có thể tái sử dụng một số cấu trúc nội bộ theo cấu hình.

**Supplier cho thao tác tốn kém:**

~~~java
// Cần logger Log4j 2 và hàm expensiveReport() đã được khai báo.
LOG.debug("report={}", () -> expensiveReport());
~~~

Log4j 2 có các overload dùng `Supplier<?>` cho tham số hoặc toàn bộ thông điệp, giúp trì hoãn việc chạy hàm tới lúc level cho phép. Không mặc định suy ra mọi API tên là `debug(...)` đều hiểu supplier tương tự: ví dụ SLF4J truyền thống **không** có cùng overload Supplier ở `debug(String, Object)`.

Log4j 2 cũng hỗ trợ **fluent LogBuilder** ở các phiên bản phù hợp. Nếu dùng lựa chọn này, cần tuân thủ API và tài liệu của phiên bản thực tế thay vì copy từ SLF4J rồi đổi import.

**Formatter và message factory:** không trộn lẫn mặc định `{}` với `%s`. Log4j 2 có `getFormatterLogger()`/`printf(...)` cho dạng `String.format` khi cần, nhưng đường định dạng này có chi phí và quy tắc khác với `ParameterizedMessage`. Dùng `{}` mặc định trong hot path khi không có nhu cầu định dạng đặc biệt.

## 9. Đối số khi level tắt: những chi phí nào vẫn còn?

Parameterized logging tối ưu **phần định dạng message**, nhưng không xóa mọi chi phí. Khi đọc code, phải tách chi phí tạo đối số, phân nhánh và ghi sink.

**9.1. Tham số đã có sẵn**

~~~java
LOG.debug("userId={} retries={}", userId, retries);
~~~

Nếu `userId` là chuỗi có sẵn và `retries` là số nguyên, chi phí trước logger tương đối nhỏ. Trong nhiều hệ thống, đây là lựa chọn mặc định có lợi cho độ dễ đọc và hiệu năng.

**9.2. Phép tính đắt trong đối số**

~~~java
LOG.debug("requestDump={}", serialize(request));
~~~

Dù dùng `{}`, `serialize(request)` vẫn chạy ngay. Giải pháp là kiểm tra level hoặc dùng supplier với API hỗ trợ. Không gọi `request.toString()` trước khi đưa vào logger nếu mục tiêu là trì hoãn.

**9.3. Nhiều đối số, tạo map hoặc mảng**

~~~java
LOG.debug("a={} b={} c={}", a, b, c);
~~~

Ba tham số có thể sử dụng varargs; mảng phục vụ lời gọi có thể được tạo ngay cả khi DEBUG tắt. Nếu code tạo trước một `Map.of(...)` lớn để log một event DEBUG, bản đồ đó cũng đã được cấp phát. Đừng tạo cấu trúc phức tạp chỉ để làm arguments cho log bị tắt.

**9.4. Lambda không hoàn toàn miễn phí**

~~~java
LOG.atDebug().setMessage("snapshot={}")
        .addArgument(() -> snapshotOf(order)).log();
~~~

Với SLF4J 2.x, supplier tránh gọi `snapshotOf(order)` khi DEBUG tắt. Nhưng lambda có thể capture `order`, có chi phí tạo/cấp phát tùy JVM và tình huống; backend cũng có công việc riêng khi log bật. Chọn cách này cho phép tính đắt; không cần lạm dụng với từng giá trị đơn giản.

**9.5. Hiệu năng phụ thuộc cả sink**

Ngay cả khi format đã được tối ưu, console I/O, ghi file đồng bộ, flush, mã hóa JSON, exception stack trace, đồng bộ lock, network queue và collector có thể đắt hơn nhiều so với nối một chuỗi ngắn. Cần tối ưu toàn pipeline theo số liệu.

## 10. Exception logging và tham số hóa

Đừng vô tình biến ngoại lệ thành chuỗi, mất stack trace:

~~~java
// SLF4J hoặc Log4j 2; đoạn minh họa, biến đã có.
// Chưa tốt: mất cấu trúc Throwable nếu chỉ log message.
LOG.error("order={} failed: {}", orderId, ex.getMessage());

// Tốt hơn: truyền Throwable theo overload/convention của API.
LOG.error("order={} failed", orderId, ex);
~~~

Ở các API hỗ trợ, đối số `Throwable` cuối được nhận diện để chuyển vào trường exception của event. Hãy kiểm tra overload và cách đếm placeholder: đừng vô tình truyền exception như một tham số được format thành `{}` rồi bỏ mất cause.

Trong JUL, overload khác:

~~~java
julLogger.log(java.util.logging.Level.SEVERE, ex,
        () -> "order=" + orderId + " failed");
~~~

Ví dụ này dùng `java.util.logging.Logger` và `Throwable` `ex`. `log(Level, Throwable, Supplier<String>)` giữ cause để formatter nhận được.

**Đừng format stack trace mỗi lần gọi**:

~~~java
// Tránh làm việc tốn kém ngay cả khi ERROR không được xuất:
// log.error("error=" + Arrays.toString(ex.getStackTrace()));
~~~

Bản ghi exception đầy đủ thường cần bộ dữ liệu có cấu trúc và layout/encoder của backend. Tuy nhiên phải cân nhắc dữ liệu nhạy cảm trong message, stack trace, request payload và exception cause; parameterized logging không tự xóa secrets.

## 11. Template, placeholder và dữ liệu có cấu trúc

**Giữ message template ổn định** giúp đọc source và phân loại sự kiện:

~~~java
LOG.info("payment failed orderId={} provider={}", orderId, providerName);
~~~

Nếu nối một payload dài vào text mẫu hoặc dựng message với hàng trăm biến thể, backend và bộ tìm kiếm log có thể khó nhóm những bản ghi giống nhau.

Nhưng message parameterized **không tự động có schema**. Một JSON encoder có thể chỉ xuất:

~~~json
{
  "level": "INFO",
  "message": "payment failed orderId=A17 provider=acme"
}
~~~

Nếu muốn query theo `orderId` hoặc `provider` mà không phải parse text, hãy dùng MDC/context data, fluent key-value hoặc API structured logging phù hợp và kiểm tra kết quả trong sink:

~~~json
{
  "level": "INFO",
  "message": "payment failed",
  "orderId": "A17",
  "provider": "acme"
}
~~~

Hai JSON trên là **ví dụ minh họa**, không phải output đảm bảo của mọi backend.

Không đưa nguyên object chứa credential, token hoặc dữ liệu cá nhân vào `{}` chỉ vì nhanh viết. `toString()` của object có thể phơi bày nhiều trường không được mong muốn. Tối ưu hiệu năng không được đánh đổi chính sách dữ liệu logging.

## 12. Async logging: quan hệ giữa parameterized event và thời điểm format

Trong async logging, producer có thể đưa một event chứa template/arguments vào queue để worker format và ghi sau. Tối ưu giảm thời gian ở producer, nhưng cần hiểu **thời điểm chụp dữ liệu**.

~~~text
Producer:
  logger.debug("cart={}", cart)
       │ accepted?
       ▼
Async queue: event, arguments/context
       │
       ▼
Background consumer:
  format/toString/encode
       │
       ▼
File / console / remote sink
~~~

Nếu `cart` là object **mutable** và `toString()` được gọi muộn, dữ liệu hiển thị có thể phản ánh trạng thái **sau khi event được tạo** tùy framework/configuration. Một số backend chụp trước một phần dữ liệu, một số trì hoãn. Đừng phụ thuộc hành vi cụ thể khi chưa xác nhận. Khi cần chính xác, lấy snapshot các field bất biến (ID, trạng thái, timestamp) ở thời điểm tạo event.

**Không giữ reference đến bộ đệm tái sử dụng** như `StringBuilder` trong event được xử lý sau mà giả định nó không thay đổi. Nếu log cần giá trị tại thời điểm gọi, ghi một chuỗi/giá trị bất biến hoặc dùng cơ chế snapshot chuẩn của framework.

Parameterized logging không thay thế **drain/flush** async queue và không cung cấp độ bền dữ liệu. Việc mức log bị tắt, queue bị drop hoặc sink hỏng là các nguyên nhân riêng khiến sự kiện không xuất hiện.

## 13. Những sai lầm về cú pháp và tính chính xác

| Sai lầm | Điều xảy ra | Cách sửa |
| --- | --- | --- |
| Dùng `"id=" + expensive()` ở DEBUG | Tính và nối chuỗi trước khi level được kiểm tra | Dùng placeholder cho giá trị sẵn có, supplier/guard cho giá trị đắt |
| `LOG.debug("x={}", expensive())` rồi kỳ vọng lazy | `expensive()` vẫn chạy | Guard hoặc API Supplier |
| Dùng `{}` trong JUL | Không theo mẫu `MessageFormat` | Dùng `{0}`, `{1}` |
| Dùng `{0}` trong SLF4J | Không thay theo cú pháp `{}` | Dùng `{}` |
| `String.format(...)` trước logger | Format đã xảy ra tại call site | Truyền message template và arguments |
| Quên `.log()` trong SLF4J Fluent | Không phát event | Kết thúc builder bằng `log()` |
| Truyền lambda cho SLF4J classic `debug(String,Object)` | Không đảm bảo lambda được gọi để tạo dữ liệu; có thể chỉ format đối tượng lambda | Dùng fluent `addArgument(Supplier)` của SLF4J 2 hoặc guard |
| Ghi `ex.getMessage()` thay cause | Mất stack trace/cấu trúc exception | Dùng overload Throwable hoặc `setCause` |
| Truyền payload mutable vào async logger | Dữ liệu có thể thay đổi trước lúc format | Snapshot field tại thời điểm event |
| Tạo `Map.of(...)` chỉ để DEBUG | Vẫn cấp phát trước lời gọi | Guard hoặc structured API hỗ trợ lazy |
| Giả định varargs không cấp phát | Mảng/boxing có thể phát sinh | Đo allocation theo phiên bản/JVM thật |
| Coi `{}` là structured logging | Backend có thể chỉ in text | Dùng key-value/MDC và encoder có schema |
| Log nguyên object chứa secret | Dữ liệu nhạy cảm có thể xuất hiện qua `toString()` | Chọn trường an toàn, masking/redaction |
| Dùng placeholder sai số lượng | Output có thể giữ placeholder hoặc bỏ đối số tùy API | Test formatter, kiểm tra template/arguments |
| Dùng `%s` như thể mặc định Log4j 2 | Message factory mặc định dùng `{}` | Dùng đúng factory hoặc `printf/getFormatterLogger` |

## 14. Đo hiệu năng logging một cách đáng tin

Không nên kết luận “cách A nhanh hơn 30 lần” chỉ từ một phép đo thủ công, vì kết quả phụ thuộc vào JDK, CPU, backend, mức log, số lượng argument, kích thước object, encoder, async queue và I/O.

**14.1. Phân biệt hai chế độ benchmark**

- **Disabled level benchmark:** DEBUG/TRACE tắt; đo chi phí đi qua code và logger khi **không** xuất event. Đây là nơi sự khác biệt giữa concatenation, parameterized và Supplier thường rõ.
- **Enabled level benchmark:** DEBUG/INFO bật; đo định dạng, serializer, ghi sink, garbage collection, I/O và contention. Ở chế độ này tối ưu template không loại được chi phí ghi log.

**14.2. Đo cả throughput, độ trễ và allocation**

Các chỉ số hữu ích gồm số operation/giây, p95/p99 latency, bytes allocated/op, số lần GC, sự kiện drop và tốc độ sink. Với async logging, phải xác định điểm đo là “producer enqueue thành công” hay “bản ghi đã đến sink”. Đừng dùng throughput enqueue để khẳng định tốc độ ghi bền vững.

**14.3. Dùng benchmark framework phù hợp**

Dùng **JMH** cho microbenchmark Java thay vì lấy một vòng lặp `System.nanoTime()` trong một chương trình ngắn rồi so kết quả. JVM có JIT warmup, dead-code elimination và escape analysis; log level không ổn định hoặc một backend ghi ra console có thể làm kết quả bị méo.

Thiết kế case tối thiểu:

1. `debug("x=" + id)`.
2. `debug("x={}", id)`.
3. `debug("x={}", expensive())`.
4. `if (isDebugEnabled()) { debug("x={}", expensive()); }`.
5. Với SLF4J 2, `atDebug().addArgument(() -> expensive()).log("x={}")`.

Đảm bảo mỗi case có cùng tác vụ nguồn dữ liệu; đo lúc DEBUG bật và tắt; cố định provider/version và tập hợp kết quả nhiều lần chạy. Với số liệu từ production, quan sát thêm log drop và mức nghẽn của collector để tránh tối ưu “nhanh” nhưng mất log.

## 15. Quy tắc chọn giải pháp trong thực tế

| Điều kiện | Lựa chọn khuyến nghị | Lý do |
| --- | --- | --- |
| Có sẵn 1–2 giá trị rẻ | Placeholder `{}` với SLF4J/Log4j 2 | Ít code, không định dạng sớm |
| Giá trị phải query DB, serialize JSON hoặc chạy thuật toán | Supplier hoặc guard level | Không trả chi phí khi level tắt |
| Thư viện nội bộ chỉ dùng JDK | JUL với `{0}`, `{1}` hoặc `Supplier<String>` | Không thêm dependency, đúng API |
| Ứng dụng dùng SLF4J 1.7 | Placeholder + `isDebugEnabled()` khi cần | Fluent API chưa tồn tại |
| Ứng dụng dùng SLF4J 2.x | Placeholder; fluent `addArgument(Supplier)` cho giá trị đắt | Tạo message lazily, hỗ trợ key-value |
| Ứng dụng dùng Log4j 2 API | Placeholder mặc định hoặc Supplier overload | Có hỗ trợ message factories và lazy args |
| Cần query trường nghiệp vụ ở hệ thống log | Structured key-value/MDC và JSON encoder | Có schema và trường tìm kiếm |
| Event bất đồng bộ giữ mutable object | Snapshot giá trị bất biến trước khi enqueue | Tránh thay đổi nội dung trước khi format |
| Exception quan trọng | Gắn Throwable/cause đúng overload | Giữ stack trace và thông tin phân loại |
| Bài toán GC/throughput nghiêm ngặt | Benchmark toàn pipeline với JMH và tải thực | Tối ưu dựa trên số liệu, không dựa vào giả định |

## 16. Checklist khi review code và cấu hình

1. **Xác định API đang dùng:** JUL, `System.Logger`, SLF4J hay Log4j 2; ghi đúng mẫu placeholder.
2. **Tìm phép tính đắt tại call site:** JSON serialization, query, gọi `toString()` nặng, tạo collection/array, stack trace formatting, chuyển đổi byte.
3. **Phân biệt disabled và enabled:** nếu DEBUG tắt, method nào vẫn chạy, object nào vẫn được cấp phát?
4. **Dùng placeholder cho đối số đơn giản:** giảm nối chuỗi, giữ mẫu ổn định và đọc được.
5. **Dùng supplier hoặc guard cho đối số đắt:** không đặt side effect nghiệp vụ trong logging supplier vì supplier có thể không được chạy.
6. **Đếm placeholder và truyền Throwable đúng overload:** lỗi cú pháp thường không được compiler phát hiện.
7. **Duy trì ngữ nghĩa trong async:** snapshot khi cần; không dùng argument mutable bị thread khác sửa mà thiếu đồng bộ.
8. **Kiểm tra policy dữ liệu:** không log credentials/token và không serialize cả domain object ngoài chủ đích.
9. **Đánh giá kênh sink và formatter:** cần gọi `formatMessage` ở JUL custom formatter; cần encoder phù hợp để giữ key-value khi dùng structured API.
10. **Đo ở mức production:** throughput/latency/allocations/drop theo đúng backend và cấu hình.

## 17. Câu hỏi tự kiểm tra

1. Trong `log.debug("value={}", expensive())`, tại sao `expensive()` vẫn chạy nếu DEBUG tắt?
2. So sánh `log.debug("x=" + x)` và `log.debug("x={}", x)` khi `x` là object đã tồn tại. Điều gì thường được trì hoãn?
3. JUL dùng `{0}` hay `{}`? Vì sao custom `Formatter` có thể in nguyên template?
4. Tại sao `LOG.log(Level.FINE, () -> expensive())` không gọi Supplier khi mức `FINE` tắt?
5. SLF4J 2.x có API nào để trì hoãn một argument? Điều gì xảy ra nếu quên gọi `.log()`?
6. Với SLF4J 1.7, khi phải tính report tốn kém, cần làm gì trước khi gọi `debug`?
7. Parameterized logging có bảo đảm không cấp phát mảng/boxing ở tất cả phiên bản và số lượng argument không?
8. Vì sao message `"orderId={}"` chưa chắc tạo trường `orderId` có thể query như JSON?
9. Truyền object mutable cho async logger có thể sinh vấn đề gì?
10. Nếu một exception cần stack trace, nên truyền nó theo cách nào?
11. Khi benchmark, vì sao phải đo cả trường hợp DEBUG bật và tắt?
12. Parameterized logging có thay thế durability, flush hoặc chính sách drop của async logger không?

**Gợi ý đáp án:** (1) Java đánh giá đối số trước lời gọi; (2) tránh format/toString sớm, không tránh việc có object; (3) `{0}`, formatter phải dùng `formatMessage`; (4) overload Supplier được gọi có điều kiện; (5) `addArgument(Supplier)`, thiếu `log()` thì không có event; (6) `isDebugEnabled()` hoặc điều kiện level phù hợp; (7) không; (8) thiếu schema/encoder; (9) giá trị có thể thay đổi trước format; (10) overload Throwable hoặc setCause; (11) các điểm nghẽn khác nhau; (12) không.

## 18. Tài liệu tham khảo chính thức

- [SLF4J Manual — parameterized logging và Fluent API](https://www.slf4j.org/manual.html): `{}`, `LoggingEventBuilder`, `addArgument(Supplier)` và key-value.
- [SLF4J — LoggingEventBuilder API](https://www.slf4j.org/apidocs/org/slf4j/spi/LoggingEventBuilder.html): `addArgument(Supplier<?>)`, `setMessage`, `setCause` và `log()`.
- [SLF4J FAQ](https://www.slf4j.org/faq.html): provider, tham số hóa và tương thích phiên bản.
- [Java SE 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): `log(Level, String, Object...)` và Supplier.
- [Java SE 17 — java.util.logging.Formatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Formatter.html): `formatMessage(LogRecord)`, định dạng message.
- [Java SE 17 — System.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.Logger.html): API tham số và Supplier của JDK.
- [Apache Log4j 2 — API](https://logging.apache.org/log4j/2.x/manual/api.html): `{}`, message factories, throwable và các lựa chọn format.
- [Apache Log4j 2 — Messages](https://logging.apache.org/log4j/2.x/manual/messages.html): `ParameterizedMessage`, `ReusableParameterizedMessage` và structured messages.
- [Apache Log4j 2 — Logger javadoc](https://logging.apache.org/log4j/2.x/javadoc/log4j-api/org/apache/logging/log4j/Logger.html): Supplier overload, tham số và logger.

