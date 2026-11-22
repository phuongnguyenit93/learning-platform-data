# Giới hạn của Java Util Logging (JUL)

## 1. Hiểu đúng về JUL và phạm vi bài học

**Java Util Logging (JUL)** là hệ thống logging có sẵn trong JDK, thuộc package `java.util.logging` và module `java.logging`. Ứng dụng có thể ghi log mà không phải thêm thư viện ngoài:

```java
import java.util.logging.Logger;

public class OrderService {
    private static final Logger LOG =
            Logger.getLogger(OrderService.class.getName());

    public void accept(String orderId) {
        LOG.info("event=order_accepted orderId=" + orderId);
    }
}
```

Đây là **lớp minh họa** không có phương thức `main`. JUL không chỉ là `System.out.println`. Những thành phần chính của nó gồm:

- `Logger`: nhận lời gọi ghi sự kiện, áp dụng level và quy tắc lọc.
- `Level`: `SEVERE`, `WARNING`, `INFO`, `CONFIG`, `FINE`, `FINER`, `FINEST`, cùng `OFF` và `ALL`.
- `LogRecord`: dữ liệu một sự kiện, gồm level, message, parameters, timestamp, logger name, thông tin nguồn, `Throwable` và metadata khác.
- `Handler`: đưa sự kiện ra console, file, stream, socket hoặc đích tùy biến.
- `Formatter`: biến `LogRecord` thành chuỗi có thể đọc/ghi.
- `Filter`: chấp nhận hoặc loại sự kiện theo điều kiện tùy chỉnh.
- `LogManager`: tổ chức logger và quản lý cấu hình.

**Giới hạn của JUL** cần được hiểu là sự khác nhau giữa **khả năng có sẵn trong JDK** và **khả năng cần tự mở rộng hoặc dùng công cụ ngoài**. JUL vẫn có thể được tùy biến bằng handler, formatter, filter và bridge. Câu hỏi thực tế là: những tính năng ấy có được cung cấp sẵn, dễ cấu hình, có hệ sinh thái phù hợp và đáng chi phí bảo trì không?

Bài tập trung vào những hạn chế thường gặp khi dùng JUL trong hệ thống có nhiều thành phần, lưu trữ log tập trung, lượng log lớn hoặc yêu cầu observability nâng cao. Không kết luận rằng JUL mặc nhiên không phù hợp với mọi ứng dụng production.

## 2. Tổng quan các giới hạn và cách khắc phục

| Nhu cầu | JUL chuẩn hỗ trợ | Phần cần bổ sung khi yêu cầu cao hơn |
|---|---|---|
| Level | `SEVERE`, `WARNING`, `INFO`, `FINE`… | Ánh xạ tên và chính sách khi tích hợp `ERROR/WARN/DEBUG/TRACE` |
| Định dạng | `SimpleFormatter`, `XMLFormatter`, custom `Formatter` | JSON schema, encoder có cấu trúc và field escaping đầy đủ |
| Dữ liệu ngữ cảnh | `LogRecord` với message, parameters, nguồn, timestamp và exception | MDC, `traceId`/`requestId`, key–value fields có tên |
| Đích ghi | `ConsoleHandler`, `FileHandler`, `StreamHandler`, `SocketHandler`, `MemoryHandler` | Routing phức tạp, retry, buffering, backpressure và collector |
| Rotation file | `FileHandler` theo dung lượng/số file | Rolling theo ngày, nén, retention theo tuổi hoặc chính sách đặc biệt |
| Message template | `{0}`, `{1}` thông qua `MessageFormat`/`formatMessage` | Không mặc định hiểu `{}` của SLF4J |
| Lazy message | Có `Supplier<String>` | Không hoãn tự động mọi biểu thức đối số |
| Async | Có thể tự tích hợp handler/hàng đợi | Không có một generic async appender giàu chính sách sẵn trong JDK |
| Cấu hình | `LogManager`, `logging.properties`, API runtime | Profile, reload động, điều khiển tập trung và tích hợp framework |
| Observability | Log sự kiện hỗ trợ chẩn đoán | Metrics, distributed tracing, correlation và audit trail có bảo đảm |

Không có sẵn một tính năng **không đồng nghĩa** với không thể làm bằng JUL. Tuy nhiên, tự viết nhiều extension làm tăng trách nhiệm về tính đúng, an toàn, kiểm thử và vận hành.

## 3. Giới hạn định dạng: text và XML sẵn có, JSON phải thêm công cụ

JUL đi kèm `SimpleFormatter` cho text và `XMLFormatter` cho XML. Người dùng có thể viết `Formatter` tùy chỉnh. Nhưng bộ JUL chuẩn **không cung cấp sẵn một JSON formatter/encoder tổng quát với schema field nghiệp vụ** tương tự các giải pháp structured logging chuyên dụng.

Ví dụ định dạng có cấu trúc mà hệ thống quan sát có thể cần:

```json
{
  "timestamp": "2026-11-09T08:15:03.125Z",
  "level": "ERROR",
  "service": "order-api",
  "logger": "com.example.orders.OrderService",
  "requestId": "req-42",
  "event": "order_save_failed",
  "orderId": "ORD-7"
}
```

Đây là **mẫu JSON minh họa**, không phải output tự động của JUL. Để tạo dạng này, ứng dụng phải có nguồn dữ liệu cho từng trường, formatter/serializer và cơ chế đưa record tới collector.

Có ba hướng thường gặp:

1. Viết `Formatter` tùy chỉnh và dùng thư viện JSON serializer đáng tin cậy để xử lý các trường.
2. Cài formatter/handler chuyên dụng của thư viện ngoài mà vẫn giữ API JUL.
3. Dùng bridge phù hợp để chuyển sự kiện JUL sang backend có encoder structured logging.

**Không nên ghép JSON bằng nối chuỗi**: dấu ngoặc kép, ký tự xuống dòng, backslash và control characters trong message/exception phải được escape chính xác. Cần thống nhất timezone, kiểu dữ liệu, khóa, kích thước, masking và xử lý stack trace. Chỉ xuất ra một dòng nhìn giống JSON không bảo đảm collector parse được hoặc dữ liệu được lưu bền vững.

### 3.1. `SimpleFormatter` có tùy biến nhưng không giống PatternLayout

JUL có thuộc tính `java.util.logging.SimpleFormatter.format` để đổi format text, theo các conversion kiểu `java.util.Formatter`. Ví dụ `logging.properties`:

```properties
handlers=java.util.logging.ConsoleHandler
.level=INFO
java.util.logging.ConsoleHandler.level=INFO
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
java.util.logging.SimpleFormatter.format=%4$s %3$s - %5$s%6$s%n
```

Trong `SimpleFormatter`, `%4$s` là level, `%3$s` là logger name, `%5$s` là message đã format và `%6$s` là phần Throwable nếu có. Đây **không phải** pattern `%level %logger %msg%n` của Logback/Log4j 2.

Ví dụ ứng dụng có class main `com.example.Main` đã biên dịch có thể dùng:

```bash
java -Djava.util.logging.config.file=logging.properties com.example.Main
```

Đây là **lệnh minh họa**; cần class và file cấu hình thật. Framework hoặc container có thể tùy biến cách nạp logging config. Việc đổi text format không biến `requestId=...` nằm trong message thành field JSON độc lập.

## 4. Giới hạn correlation context: JUL không có MDC chuẩn

Một log record có logger name, timestamp, message, level và các trường chuẩn. Nhưng với request web, nhiều tác vụ chạy xen kẽ; cần biết **sự kiện thuộc request/job nào**, thường thông qua `requestId`, `traceId`, `spanId` hoặc `jobId`.

Trong Logback/SLF4J/Log4j 2, MDC hoặc Thread Context là cơ chế phổ biến để đưa context vào log. **JUL chuẩn không có một API MDC/key–value map tương đương tích hợp trong `LogRecord`**. Ta có thể ghi thủ công:

```java
LOG.log(Level.INFO,
        "requestId={0} event=order_accepted orderId={1}",
        new Object[]{"req-42", "ORD-7"});
```

Nội dung hiển thị có request ID, nhưng ở mức `LogRecord` chuẩn, đây chủ yếu là **message template và parameters**, không phải một bản đồ trường nghiệp vụ có tên. Collector muốn truy vấn riêng `requestId` có thể phải parse text hoặc nhận schema được tạo bổ sung.

Giải pháp có thể là truyền context tường minh, tạo một model sự kiện có cấu trúc, custom handler/formatter hoặc tích hợp tracing và backend có MDC. Đừng đưa dữ liệu động vào **tên logger** như `Logger.getLogger("order." + orderId)`: tên logger nên ổn định theo class/package hoặc category.

**Lưu ý thread pool:** nếu tự dùng `ThreadLocal` làm context, phải dọn bằng `finally` và truyền đúng khi chuyển sang `ExecutorService`, `CompletableFuture` hoặc callback. Thread tái sử dụng có thể khiến request sau nhận nhầm context của request trước. Một formatter không thể phục hồi trường context chưa hề được truyền tới event.

## 5. Placeholder, message parameters và lazy evaluation

### 5.1. JUL không mặc định dùng `{}`

Trong JUL, message có tham số thường theo cú pháp `MessageFormat`:

```java
LOG.log(Level.INFO,
        "orderId={0} result={1}",
        new Object[]{"ORD-7", "ACCEPTED"});
```

Kết quả phần message:

```text
orderId=ORD-7 result=ACCEPTED
```

Formatter nên dùng `formatMessage(record)` để chèn parameters. Nếu tự viết formatter chỉ gọi `record.getMessage()`, có thể còn nguyên mẫu `{0}`.

So với JUL:

```java
// SLF4J (cần dependency và biến log đã khai báo):
log.info("orderId={} result={}", orderId, result);

// JUL (JDK):
LOG.log(Level.INFO,
        "orderId={0} result={1}",
        new Object[]{orderId, result});
```

Các dòng là **minh họa API**, chưa phải chương trình độc lập. `{}` kiểu SLF4J không được JUL tự động thay tham số. `MessageFormat` còn có quy tắc riêng về dấu nháy đơn, số/ngày và locale; cần kiểm thử khi log đa ngôn ngữ hoặc đòi hỏi output ổn định.

### 5.2. JUL có lazy message, nhưng phải sử dụng đúng overload

JUL đã có overload nhận `Supplier<String>`:

```java
// Nếu mức FINE bị tắt, lambda không cần được gọi:
LOG.log(Level.FINE, () -> buildDetailedMessage());
```

Trong khi đó:

```java
// Hàm được Java gọi trước khi logger nhận đối số:
LOG.log(Level.FINE, "detail={0}",
        new Object[]{buildDetailedMessage()});
```

Hai đoạn giả định `LOG` và `buildDetailedMessage()` đã tồn tại. Ở đoạn thứ hai, Java **đánh giá biểu thức khi tạo mảng**, kể cả nếu log bị lọc. Đây là giới hạn của cách gọi, không phải bằng chứng JUL hoàn toàn thiếu lazy logging. Khi cần định dạng có tham số và tối ưu chi phí, hãy chọn API/overload phù hợp và đo hiệu năng thực tế.

## 6. Đầu ra và chính sách file chưa phong phú như backend chuyên dụng

JUL có các handler trong JDK:

- `ConsoleHandler`: xuất ra console, thường qua `System.err`.
- `FileHandler`: ghi file, có thể xoay vòng theo **ngưỡng kích thước** và **số lượng file**.
- `StreamHandler`: ghi vào stream do ứng dụng cung cấp.
- `SocketHandler`: gửi dữ liệu qua socket, cần xử lý độ tin cậy ở kiến trúc tổng thể.
- `MemoryHandler`: lưu một lượng record trong bộ nhớ rồi đẩy tới handler đích theo điều kiện; **không đồng nghĩa** với async appender tổng quát.

Với nhu cầu **xoay file mỗi ngày, nén bản cũ, giữ đúng 14 ngày, xóa tự động theo tuổi**, `FileHandler` chuẩn không đưa ra cả bộ chính sách rolling đó trong một cấu hình hoàn chỉnh. Cần handler/agent riêng hoặc backend có rolling policy phù hợp.

Với log tập trung qua mạng, ứng dụng cần quyết định:

1. Khi collector bị ngắt kết nối thì retry, buffer, bỏ record hay chặn request?
2. Có giới hạn dung lượng queue, số lần retry và backpressure không?
3. Khi ứng dụng crash trước khi flush, những sự kiện nào có thể mất?
4. Các file có bị nhiều process ghi cùng lúc hoặc vượt giới hạn ổ đĩa không?
5. Ai chịu trách nhiệm retention, phân quyền và mã hóa đường truyền nếu cần?

Đây là **các bài toán vận hành**; thay formatter không giải quyết chúng.

## 7. Ghi bất đồng bộ và hiệu năng

Trong cấu hình JUL cơ bản, các handler thường xử lý log trên đường thực thi phát sự kiện; format và I/O có thể làm tăng độ trễ. Điều này phụ thuộc handler, formatter, buffer, hệ điều hành và đầu ra. Không có căn cứ để kết luận mọi ứng dụng JUL đều chậm.

JDK **không tích hợp một generic async appender giàu chính sách như một số backend logging**. Có thể tự viết `Handler` sử dụng queue và worker, dùng thư viện bên ngoài hoặc ghi stdout cho agent thu thập. Khi chọn async cần có quy tắc:

- Giới hạn queue và hành vi khi đầy: chặn, drop, ưu tiên hay giảm tải.
- Thời điểm format/snapshot context để tránh dùng dữ liệu mutable đã thay đổi.
- Quy tắc flush/shutdown và nguy cơ mất bản ghi khi process chết.
- Thứ tự phát sinh so với thứ tự được ghi, timestamp sự kiện so với timestamp I/O.
- Theo dõi queue backlog, dropped events, CPU, allocation và độ trễ.

Async **không tự bảo đảm delivery đúng một lần hoặc không mất log**. Trong hệ thống tải thấp, custom async handler có thể gây thêm độ phức tạp hơn lợi ích mang lại. Hãy đo throughput, latency và bộ nhớ trước/sau.

## 8. Cấu hình LogManager và những bẫy hay bị hiểu là giới hạn API

JUL dùng `LogManager` và có thể đọc `logging.properties` hoặc được cấu hình qua API. Không phải ứng dụng nào cũng tự nạp file ở bất kỳ đường dẫn nào; container và framework có thể dùng cấu hình hoặc `LogManager` riêng.

### 8.1. Cần kiểm tra level ở cả logger và handler

Ví dụ:

```java
LOG.setLevel(Level.FINE);
consoleHandler.setLevel(Level.INFO);
LOG.fine("event=debug_detail");
```

Đây là snippet giả định `consoleHandler` được gắn với `LOG`. Logger đã cho phép `FINE`, nhưng handler với mức `INFO` vẫn bỏ bản ghi. Ngược lại, nếu logger chỉ cho phép `INFO`, cấu hình handler `ALL` không làm `FINE` xuất hiện.

Các yếu tố khác gồm `Filter` trên logger/handler, cấu hình inherited level, handler được gắn ở đâu và việc forward tới logger cha.

### 8.2. Handler cha có thể làm log trùng

Với logger tên `com.example.orders.OrderService` và cấu hình phân cấp, record có thể được gửi tới handler gắn trực tiếp và handler của logger cha khi `useParentHandlers` đang bật. Kết quả là một lời gọi `LOG.log(...)` xuất hiện nhiều lần trên console.

`setUseParentHandlers(false)` có thể phù hợp trong một ví dụ tự cấu hình handler, nhưng khi vận hành cần hiểu hệ thống thu thập chung trước khi tắt propagation; nếu làm tùy tiện, log có thể biến mất khỏi pipeline chính.

### 8.3. Cấu hình runtime và môi trường

JUL có API để điều chỉnh logger level trong lúc chạy và cơ chế `LogManager` để nạp lại cấu hình theo cách triển khai cụ thể. Điều này **không đồng nghĩa** với việc JDK cung cấp sẵn một trang quản trị, tự theo dõi file thay đổi, hệ thống phân phối cấu hình an toàn hoặc profile production/staging cho mọi ứng dụng.

Khi ứng dụng được triển khai qua một framework, cần kiểm tra stack logging thực tế và cách framework quản lý cấu hình. Việc đặt `logging.properties` vào thư mục nguồn không chắc làm JVM sử dụng nó.

## 9. Hệ sinh thái: JUL là API cụ thể, SLF4J là facade

Khi mã nghiệp vụ viết:

```java
private static final java.util.logging.Logger LOG =
        java.util.logging.Logger.getLogger(MyService.class.getName());
```

mã đang phụ thuộc trực tiếp vào **API JUL**. Trong ứng dụng dùng SLF4J, lời gọi logging có thể đi qua facade rồi tới provider/backend như Logback hoặc Log4j 2; backend có thể thay đổi mà mã ứng dụng ít cần sửa hơn.

Tuy nhiên, **không nhất thiết phải viết lại mọi dòng JUL** để gửi log tới một backend khác. Có thể sử dụng bridge JUL → SLF4J hoặc tích hợp ở tầng thu thập, tùy mục tiêu.

Khi dùng bridge, hãy kiểm tra hướng chuyển tiếp, cấp độ, context, exception, logger name và overhead. Đặc biệt tránh cấu hình hai bridge đối nghịch khiến event chuyển vòng **JUL ↔ SLF4J/backend**, hoặc gắn cả JUL handler cũ và bridge mới tới cùng đích gây trùng log.

Bridge cũng **không thể tự khôi phục `traceId` chưa từng được gắn vào event**. Nó chỉ chuyển dữ liệu có sẵn hoặc những gì adapter được thiết kế để tạo.

### `System.Logger` từ Java 9 có giải quyết hết không?

`java.lang.System.Logger` là API logging nền tảng khác từ Java 9 với cơ chế provider; nó không có nghĩa JUL đã tự động có MDC chuẩn, JSON encoder, async/rolling policy và distributed tracing đầy đủ. Phải phân biệt **API ứng dụng gọi**, **provider/backend xử lý** và **collector lưu trữ**.

## 10. Observability, audit và bảo mật

### Logs không thay thế metrics/traces

JUL ghi lại sự kiện được ứng dụng phát ra, nhưng không tự tạo distributed trace giữa các service, không tính SLO/error rate và không cung cấp hệ thống metrics hoàn chỉnh. Một chuỗi log có cùng `traceId` giúp liên kết sự kiện; nó chưa có quan hệ span cha/con hoặc timing của hệ thống tracing nếu không được tích hợp thêm.

Đối với chỉ số lỗi, đừng mặc định **đếm dòng `SEVERE`** là đếm số request thất bại: một exception có thể bị log ở nhiều tầng, hoặc bản ghi có thể bị lọc/lấy mẫu. Metrics theo đơn vị công việc nên được thiết kế rõ.

### Log thường không tự là audit trail

Một sự kiện `INFO "user changed role"` chưa bảo đảm audit trail đáp ứng yêu cầu tính toàn vẹn, quyền truy cập, chống sửa đổi, thời hạn lưu hoặc thông tin chủ thể. Những bảo đảm ấy cần thiết kế riêng; không phụ thuộc tên logger hay framework logging.

### Không có redaction toàn diện tự động

JUL không tự che password, access token, API key, session cookie hoặc dữ liệu nhạy cảm trong message và exception. `Filter`/`Formatter` tùy chỉnh có thể hỗ trợ che dữ liệu, nhưng phải kiểm tra cả message, parameters, `Throwable`, context, logger name, collector và nơi lưu. Input chứa newline/control characters có thể gây **log injection** nếu formatter cho phép giả mạo nhiều dòng; dùng escaping/encoding có chủ đích và không ghi payload tùy tiện.

## 11. Ví dụ Java 17+ độc lập: minh họa giới hạn và khả năng JUL sẵn có

Ví dụ sau dùng **chỉ JDK**, không cần thêm dependency. Nó thể hiện cách JUL xử lý placeholder `{0}`, không mặc định hiểu `{}`, lọc mức `FINE` trước khi gọi supplier và lưu `Throwable` để formatter xử lý.

Tạo tệp `JulLimitsDemo.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class JulLimitsDemo {
    private static final Logger LOG =
            Logger.getLogger(JulLimitsDemo.class.getName());

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.ALL);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                String line = record.getLevel().getName()
                        + " | " + record.getLoggerName()
                        + " | " + formatMessage(record);
                Throwable error = record.getThrown();
                if (error != null) {
                    line += " exception="
                            + error.getClass().getSimpleName()
                            + ":" + error.getMessage();
                }
                return line + System.lineSeparator();
            }
        });
        LOG.addHandler(console);

        LOG.log(Level.INFO,
                "requestId={0} event=order_received orderId={1}",
                new Object[]{"req-42", "ORD-7"});

        LOG.info("SLF4J-style placeholder remains: {}");

        AtomicInteger supplierCalls = new AtomicInteger();
        LOG.log(Level.FINE, () -> {
            supplierCalls.incrementAndGet();
            return "expensive_detail";
        });
        LOG.info("fineSupplierEvaluations=" + supplierCalls.get());

        try {
            throw new IllegalStateException("cache unavailable");
        } catch (IllegalStateException error) {
            LOG.log(Level.SEVERE, "event=cache_refresh_failed", error);
        }

        console.flush();
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 JulLimitsDemo.java
java JulLimitsDemo
```

Các dòng hiển thị trên console:

```text
INFO | JulLimitsDemo | requestId=req-42 event=order_received orderId=ORD-7
INFO | JulLimitsDemo | SLF4J-style placeholder remains: {}
INFO | JulLimitsDemo | fineSupplierEvaluations=0
SEVERE | JulLimitsDemo | event=cache_refresh_failed exception=IllegalStateException:cache unavailable
```

`ConsoleHandler` ghi mặc định vào **stderr**, nên đoạn trên là nội dung stderr; chương trình không tự ghi stdout. Formatter ví dụ cố ý không chứa timestamp và chỉ xuất exception type/message để output ổn định. Trong vận hành thật, nên ghi timestamp, timezone, correlation ID và stack trace/cause chain đầy đủ khi phù hợp.

**Giải thích kết quả:**

1. `formatMessage(record)` chuyển `{0}`, `{1}` thành `req-42` và `ORD-7`.
2. JUL không thay `{}` kiểu SLF4J trong lời gọi `LOG.info(...)` không có parameters.
3. Level INFO lọc FINE trước khi thực thi `Supplier<String>`; biến `supplierCalls` vẫn bằng 0.
4. Handler đặt `ALL` không ép logger phát FINE vì logger đã lọc sự kiện.
5. `LOG.log(Level.SEVERE, message, error)` giữ `Throwable` trong record; formatter tùy chỉnh quyết định xuất phần nào. Ví dụ không xuất stack trace **không có nghĩa JUL không hỗ trợ truyền exception**.
6. Các field như `requestId` được nhập vào message text, không trở thành JSON fields hay MDC một cách tự động.

## 12. Khi nào vẫn dùng JUL và khi nào cần thay đổi?

| Tình huống | Lựa chọn nên cân nhắc | Lý do |
|---|---|---|
| CLI/tool nhỏ, Java library tối giản dependency | JUL thường đủ | Có sẵn trong JDK; logger, level, handler cơ bản |
| Service có logging volume vừa, stdout được agent thu thập | JUL có thể đáp ứng | Pipeline ngoài xử lý thu thập và lưu trữ |
| Nhiều microservice cần JSON schema, MDC và trace correlation | Backend/encoder hoặc thư viện bổ sung | Giảm công tự triển khai context và field mapping |
| Cần async với backpressure, nhiều đích, rolling/nén/retention | Backend chuyên dụng hoặc handler/agent được kiểm chứng | Có thêm các chính sách vận hành sẵn |
| Framework đã tích hợp SLF4J + một backend | Ưu tiên kiểm tra và tận dụng stack đó | Tránh nhiều cấu hình/bridge cùng xuất trùng |
| Hệ thống JUL lớn nhưng hoạt động ổn | Đánh giá nhu cầu cụ thể trước khi chuyển | Di chuyển không tự mang lại lợi ích nếu thiếu bài toán thật |

**Không có quy tắc mọi ứng dụng lớn phải bỏ JUL.** Một JUL pipeline được cấu hình đúng, có agent thu thập và nhu cầu rõ ràng vẫn có thể hoạt động tốt. Ngược lại, tự viết nhiều custom handler, formatter, thread context và rolling policy chỉ để tránh dependency có thể tạo thêm rủi ro.

Lộ trình cải tiến có thể thực hiện theo thứ tự: xác định mục tiêu → kiểm tra API/backend/handler đang chạy → chuẩn hóa event và level → bổ sung context và masking → thử formatter/agent/bridge hoặc backend khác → đo độ trễ, mất log, stack trace, lượng log trùng và khả năng tìm kiếm trên môi trường thật.

## 13. Lỗi thường gặp và cách xác định đúng nguyên nhân

| Dấu hiệu | Điều cần kiểm tra | Hướng xử lý |
|---|---|---|
| Không xuất `FINE` dù đã bật | Logger level, handler level, filter và inheritance | Bật đúng cả đường ghi, không chỉ một mức |
| Log trùng trên console | Handler cha, additivity/bridge và collector | Kiểm tra `useParentHandlers` và đường đi sự kiện |
| Placeholder `{}` giữ nguyên | Sử dụng cú pháp SLF4J trong JUL | Dùng `{0}` và overload tham số đúng |
| Placeholder `{0}` giữ nguyên | Formatter chỉ đọc `getMessage()` hoặc thiếu parameters | Dùng `formatMessage(record)` và arguments |
| Không có stack trace | Không truyền `Throwable` hoặc formatter không xuất | Dùng overload nhận Throwable và formatter phù hợp |
| Thiếu `requestId` | Context chưa được truyền/ghi, hoặc chuyển thread bị mất | Thiết kế correlation và xác nhận boundary async |
| Muốn JSON nhưng chỉ thấy text | Chưa cấu hình JSON formatter/encoder | Thêm serializer/schema/collector thích hợp |
| File không xoay theo ngày | `FileHandler` cấu hình theo dung lượng/số file | Dùng rolling policy hoặc agent phù hợp |
| Ứng dụng chậm khi ghi log | Formatter, socket, console/file I/O hoặc log volume | Đo và điều chỉnh, đánh giá buffering/async |
| Tệp `logging.properties` không có tác dụng | Không được nạp, framework sở hữu logging | Kiểm tra JVM property, LogManager và startup |
| Log đếm lỗi nhiều hơn request lỗi | Một exception bị log nhiều tầng | Chọn boundary logging và metric đơn vị công việc |

## 14. Checklist trước khi kết luận cần rời JUL

1. **Thiếu khả năng gì cụ thể?** Text/JSON, context, tracing, rolling, retention, async hay chỉ là cấu hình level?
2. **Đã kiểm tra handler thực tế chưa?** Nhiều trường hợp không thấy log do level/filter/đích ghi, không phải JUL không hỗ trợ.
3. **Có thể thêm một formatter hoặc collector mà vẫn đơn giản không?** Tính cả người chịu trách nhiệm bảo trì.
4. **Cần key–value fields thật hay chỉ cần message dễ đọc?** JSON schema và message text là hai cấp độ khác nhau.
5. **Yêu cầu sản lượng và độ tin cậy có được đo không?** Đừng mặc định async tốt hơn khi chưa kiểm chứng.
6. **Có giữ cause và stack trace không?** Formatter tự viết rất dễ bỏ mất thông tin exception.
7. **Dữ liệu nhạy cảm có được bảo vệ không?** Kiểm tra message, parameters, Throwable và nơi lưu.
8. **Nếu có bridge/backend mới, có còn log trùng hoặc vòng lặp không?** Kiểm thử cả nhiều môi trường.
9. **Có kiểm tra end-to-end với collector thật chưa?** Phân quyền, retention, encoding, JSON parsing, timestamp và dữ liệu bị rơi đều quan trọng.

JUL có nhiều khả năng cơ bản và mở rộng được. Những giới hạn đáng quan tâm nhất là **thiếu sẵn các tiện ích hiện đại cho structured context, JSON, routing/rolling phức tạp, async, quản lý cấu hình và observability xuyên dịch vụ**. Cách làm hiệu quả là xác định yêu cầu, hiểu rõ lớp nào chịu trách nhiệm và chọn mức mở rộng hợp lý, thay vì kết luận rằng “không có sẵn trong JDK” đồng nghĩa “không thể thực hiện”.
