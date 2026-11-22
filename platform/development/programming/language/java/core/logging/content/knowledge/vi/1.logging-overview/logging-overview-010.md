# Thuật ngữ cốt lõi trong Java Logging

Khi một ứng dụng Java hoạt động, **logging** là việc ghi lại các sự kiện có ý nghĩa để người phát triển và người vận hành hiểu điều gì đã xảy ra. Muốn đọc, cấu hình và phân tích log chính xác, cần phân biệt *sự kiện*, *bản ghi*, *logger*, *mức độ*, *bộ xử lý* và *nơi nhận log*. Tên gọi cụ thể thay đổi giữa Java Util Logging (JUL), SLF4J, Logback và Log4j 2, nhưng các vai trò nền tảng vẫn tương đồng.

## 1. Một sự kiện đi từ mã nguồn đến nơi lưu log như thế nào?

```text
Ứng dụng phát sinh sự kiện
  → gọi logger qua API
  → kiểm tra mức độ và bộ lọc
  → tạo/tiếp nhận log record (log event)
  → handler/appender + formatter/layout/encoder
  → console, file hoặc hệ thống thu thập log
```

Đây là **sơ đồ khái niệm**, không phải thứ tự xử lý bắt buộc của mọi thư viện. Có hệ thống lọc ở nhiều bước, ghi bất đồng bộ, gửi log qua mạng hoặc sử dụng bộ đệm. Một lần gọi logger cũng có thể được chuyển đến nhiều đích.

## 2. Thuật ngữ dùng khi tạo và xử lý log

| Thuật ngữ | Ý nghĩa | Ví dụ hoặc điểm cần phân biệt |
| --- | --- | --- |
| **Log / log entry** (dòng/bản ghi log) | Thông tin được ghi lại về một sự kiện. | `Order 42 accepted` là phần thông điệp; bản ghi đầy đủ còn có thể chứa thời điểm, level và metadata. |
| **Logging** | Hoạt động phát sinh, xử lý và chuyển các bản ghi log. | Ghi nhận lần khởi động dịch vụ hoặc lỗi gọi API. |
| **Event** (sự kiện) | Điều đã xảy ra trong hệ thống và cần quan sát. | `order.accepted`, `connection.failed`. Một sự kiện có thể được biểu diễn bằng một log record. |
| **Log record / log event** | Đối tượng dữ liệu mang thông tin sự kiện để hệ thống logging xử lý. | `java.util.logging.LogRecord` giữ level, logger name, message, parameters, thời điểm và thông tin khác. |
| **Message** (thông điệp) | Nội dung con người đọc được mô tả sự kiện. | `Order 42 accepted`; chỉ riêng message thường không đủ để điều tra toàn bộ yêu cầu. |
| **Message template / parameters** | Mẫu thông điệp và giá trị được gắn vào lúc ghi log. | JUL: `"Order {0} accepted"` + `42`; cú pháp placeholder phụ thuộc API. |
| **Logger** | Đối tượng/điểm gọi API mà mã ứng dụng dùng để phát sinh sự kiện log. | `Logger.getLogger("demo.orders")` trong JUL. Logger không đồng nghĩa với file log. |
| **Logger name / category** | Tên định danh nguồn phát log, thường gắn với package hoặc thành phần. | `com.example.orders.OrderService` giúp lọc theo khu vực chức năng. |
| **Log level / severity** | Nhãn thể hiện mức độ hoặc mục đích của sự kiện. | JUL có `FINE`, `INFO`, `WARNING`, `SEVERE`; các API khác thường có `DEBUG`, `INFO`, `WARN`, `ERROR`. |
| **Threshold / effective level** | Ngưỡng quyết định event nào được xử lý. | Ngưỡng `INFO` thường loại event `FINE` ở logger; ngưỡng handler là một bộ lọc bổ sung. |
| **Filter** | Quy tắc cho phép/từ chối bản ghi, có thể dựa trên level hoặc điều kiện khác. | Chặn event không cần thiết hoặc chọn event cho một đích riêng. |
| **Handler / appender** | Thành phần nhận record và ghi/chuyển đến một đầu ra; JUL gọi là `Handler`, Logback/Log4j 2 thường gọi `Appender`. | `ConsoleHandler`, `FileHandler` hoặc appender đến hệ thống tập trung. |
| **Formatter / layout / encoder** | Thành phần chuyển event thành dạng hiển thị hoặc dạng bytes phù hợp với đích. | Text nhiều dòng, pattern có timestamp, hoặc JSON có các trường. |
| **Sink / destination** | Nơi nhận log cuối cùng theo một nhánh xử lý. | Standard output, standard error, tệp, log collector. |
| **Backend / implementation** | Phần thực thi việc lọc, định dạng, định tuyến và xuất log. | Logback là một backend thông dụng khi ứng dụng dùng SLF4J. |
| **Facade / logging API** | Giao diện ổn định để mã nghiệp vụ gọi log, tách khỏi cách xuất log. | SLF4J là facade; JUL cung cấp cả API và các handler/triển khai trong JDK. |
| **Configuration** (cấu hình) | Thiết lập level, handler/appender, định dạng, đích và các chính sách liên quan. | Đặt level của package, cấu hình output JSON hoặc file rotation. |
| **Root logger / propagation** | Logger cấp gốc và cơ chế bản ghi được chuyển qua quan hệ logger cha–con nếu hệ thống hỗ trợ. | Trong JUL, parent handler có thể nhận log của logger con; cấu hình sai dễ tạo log trùng. |

**Phân biệt trọng tâm:** Logger là nơi mã ứng dụng *gọi* logging; handler/appender là nơi một record *được chuyển để xuất*; formatter/layout quyết định record *trông như thế nào*; sink là nơi record *đến*. Backend kết nối những vai trò đó theo cấu hình.

## 3. Thuật ngữ khi quan sát ứng dụng đang chạy

| Thuật ngữ | Ý nghĩa và cách sử dụng |
| --- | --- |
| **Timestamp** | Thời điểm event được tạo/ghi. Log tập trung nên có timezone rõ ràng (thường UTC); cần lưu ý đồng hồ các máy có thể lệch nhau. |
| **Thread name / thread ID** | Cho biết luồng đang phát log, hữu ích khi phân tích concurrency. Thread name không thay thế định danh request. |
| **Context / attributes / fields** | Dữ liệu có cấu trúc đi kèm event, ví dụ `orderId`, `service`, `environment`. Nên đặt tên trường nhất quán. |
| **Correlation ID / request ID** | Định danh giúp kết nối các log thuộc cùng một yêu cầu hoặc luồng xử lý. Cách sinh và phạm vi phụ thuộc ứng dụng. |
| **Trace ID / span ID** | Định danh của distributed tracing: trace nối các công việc liên quan; span đại diện một thao tác trong trace. Có thể đưa vào log để liên hệ log với trace. |
| **MDC / thread context** | Cơ chế của *một số framework* để gắn context theo luồng hoặc ngữ cảnh thực thi. Không phải tính năng MDC chuẩn của `java.util.logging`; qua executor/luồng bất đồng bộ có thể cần truyền context rõ ràng. |
| **Structured logging** | Ghi event thành các trường có kiểu/cấu trúc (thường JSON), giúp tìm kiếm theo `orderId` hay `level`, thay vì chỉ dò chuỗi. |
| **Exception / Throwable / stack trace** | Lỗi Java và chuỗi vị trí lời gọi gây lỗi. Ghi cả `Throwable` giúp giữ stack trace; chỉ log `exception.getMessage()` thường làm mất ngữ cảnh quan trọng. |
| **Centralized logging / collector** | Thu log từ nhiều tiến trình/máy về một hệ thống chung để tìm kiếm và liên hệ sự kiện. |
| **Rotation / retention** | Rotation thay/đóng file log theo kích thước hoặc thời gian; retention là thời gian/chính sách giữ dữ liệu. Đây là hai vấn đề khác nhau. |
| **Sampling / rate limiting** | Chọn một phần event hoặc hạn chế tần suất để giảm chi phí/tải. Cần cân nhắc vì event bị bỏ có thể ảnh hưởng điều tra hoặc yêu cầu audit. |

Một bản ghi có cấu trúc *minh họa* (không phải output mặc định của JUL):

```json
{
  "timestamp": "2026-11-09T10:00:00Z",
  "level": "INFO",
  "logger": "demo.orders",
  "event": "order.accepted",
  "orderId": "42",
  "correlationId": "req-123"
}
```

JSON là **định dạng dữ liệu**, không tự bảo đảm tính chính xác, an toàn hay khả năng truy vấn: hệ thống nhận log vẫn phải thu thập và lập chỉ mục đúng trường. `correlationId`, `traceId` và `spanId` có mục đích liên hệ khác nhau; không nên dùng thay nhau một cách tùy tiện.

## 4. Ví dụ Java 17: nhìn thấy logger, level, handler và formatter

JUL (`java.util.logging`) có sẵn trong JDK, nên ví dụ dưới đây không cần dependency ngoài. Lưu thành **`LoggingVocabularyDemo.java`**:

```java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class LoggingVocabularyDemo {
    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.orders");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        Handler output = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " | "
                        + formatMessage(record) + System.lineSeparator();
            }
        });
        output.setLevel(Level.ALL);
        logger.addHandler(output);

        logger.log(Level.FINE, "Checking order {0}", 42);
        logger.log(Level.INFO, "Order {0} accepted", 42);
        logger.log(Level.WARNING, "Order {0} is delayed", 42);

        output.flush();
        logger.removeHandler(output);
    }
}
```

Biên dịch và chạy:

```bash
javac LoggingVocabularyDemo.java
java LoggingVocabularyDemo
```

**Standard output chính xác** (không tính dấu nhắc lệnh):

```text
INFO | Order 42 accepted
WARNING | Order 42 is delayed
```

Giải thích từng thành phần:

1. `logger` có tên `demo.orders`. `setUseParentHandlers(false)` tránh chuyển các record này lên handler của logger cha, nhờ vậy ví dụ không in trùng bởi cấu hình JUL mặc định.
2. `logger.setLevel(Level.INFO)` chặn `FINE` trước khi record được chuyển đến handler. `output.setLevel(Level.ALL)` chỉ nói rằng handler sẵn sàng nhận mọi level **đã đi tới handler**; nó không thể khôi phục `FINE` bị logger chặn.
3. `StreamHandler` là **handler**, nhận record và ghi ra `System.out`. Formatter ẩn danh là **formatter**, tạo chuỗi `LEVEL | message` bằng `LogRecord`; `formatMessage(record)` thay tham số `{0}` bằng `42`.
4. `flush()` đẩy dữ liệu còn trong bộ đệm ra output; hành vi đệm/flush là lý do không nên suy từ một lần gọi logger rằng dữ liệu chắc chắn đã xuất hiện ngay ở đích.

Ví dụ chủ động tạo formatter đơn giản, vì định dạng mặc định của JUL có thể chứa timestamp, tên lớp và thông tin phụ thuộc cấu hình. Trong ứng dụng thật, thường cấu hình handler/appender một lần khi khởi động thay vì tạo mới trong mỗi lời gọi nghiệp vụ.

### Cú pháp placeholder không đồng nhất giữa các API

- **JUL:** `logger.log(Level.INFO, "Order {0} accepted", orderId)`; formatter thích hợp có thể dùng `MessageFormat` để thế `{0}`.
- **SLF4J:** `logger.info("Order {} accepted", orderId)`; `{}` thuộc quy ước của SLF4J.
- Không chép nguyên cú pháp placeholder từ framework này sang framework khác và kỳ vọng cùng kết quả. Dùng tham số thay vì nối chuỗi tùy tiện cũng giúp tránh dựng message tốn kém trước khi kiểm tra level, tùy API và cách gọi.

## 5. Những nhầm lẫn phổ biến

**Event không chỉ là message.** Một message `"Request failed"` thiếu dữ liệu để xác định request nào thất bại. Khi thích hợp, ghi thêm loại event, endpoint/operation, mã kết quả và một correlation ID đã được kiểm soát.

**Level không phản ánh thứ tự thời gian hay độ dài message.** `INFO` ghi nhận diễn biến bình thường, `WARNING` báo dấu hiệu bất thường cần chú ý và `SEVERE` biểu thị lỗi nghiêm trọng trong JUL. Chọn level theo ý nghĩa vận hành, tránh ghi tất cả dưới một mức.

**Log không đồng nghĩa với metric hoặc trace.** Log mô tả sự kiện cụ thể; metric tổng hợp giá trị theo thời gian (tỷ lệ lỗi, độ trễ); trace thể hiện đường đi và quan hệ các thao tác. Chúng bổ sung nhau khi điều tra sự cố.

**Ghi exception message không tương đương ghi exception.** Với JUL, khi xử lý một `Throwable error`, có thể gọi `logger.log(Level.SEVERE, "Operation failed", error)` để lưu thông tin ngoại lệ/stack trace. Hạn chế log cùng một exception lặp lại vô ích ở mọi tầng xử lý.

**Nhiều log hơn không mặc nhiên tốt hơn.** Log quá dày gây nhiễu và chi phí; log quá ít cản trở chẩn đoán. Tuyệt đối tránh đưa mật khẩu, access token, secret hoặc dữ liệu cá nhân không cần thiết vào log; chú ý cả giá trị tham số, URL và stack trace có thể chứa thông tin nhạy cảm. Thiết lập rotation, retention và quyền truy cập phù hợp.

## 6. Cách đọc một log record có phương pháp

Khi gặp một dòng log, tự trả lời theo thứ tự: **thời điểm** nào, **level** nào, **logger/thành phần** nào phát ra, **sự kiện** gì, **context** nào xác định request hoặc đối tượng liên quan, và nếu lỗi thì **Throwable/stack trace** dẫn đến đâu. Sau đó kiểm tra **handler/formatter/sink** để hiểu vì sao sự kiện có hoặc không có mặt trong đầu ra mong đợi.

Nắm chắc bộ từ vựng này giúp bạn đọc tài liệu logging của nhiều thư viện Java mà không nhầm lẫn giữa mã phát log, quy tắc lọc, biểu diễn bản ghi và nơi lưu trữ.