# Placeholder trong log message của Java

## 1. Placeholder là gì?

Khi ghi log, ta thường muốn giữ một **mẫu thông điệp cố định** và chèn các giá trị thay đổi theo từng sự kiện. **Placeholder** là vị trí đánh dấu trong message template để API logging ghép giá trị tham số vào khi tạo thông điệp hiển thị.

Ví dụ về ý tưởng:

```text
Template: orderId=<order-id> status=<status>
Giá trị:  ORD-7, ACCEPTED
Hiển thị: orderId=ORD-7 status=ACCEPTED
```

Trong ví dụ trên, `<order-id>` và `<status>` chỉ là ký hiệu **minh họa**. Cú pháp placeholder thực sự phụ thuộc **logging API**. Hai dạng thường gặp trong Java là:

| API/hệ sinh thái | Cú pháp mẫu | Lời gọi |
|---|---|---|
| SLF4J (thường kết hợp Logback) | `{}`, thay lần lượt từ trái qua phải | `log.info("orderId={} status={}", orderId, status)` |
| Log4j 2 API với parameterized message thông thường | `{}`, thay lần lượt | `log.info("orderId={} status={}", orderId, status)` |
| `java.util.logging` (JUL) | `{0}`, `{1}`, dựa trên `MessageFormat` | `log.log(Level.INFO, "orderId={0} status={1}", new Object[]{orderId, status})` |

**Điểm cần nhớ:** `{}` và `{0}` **không phải hai cách viết tương đương**. Không thể sao chép template của SLF4J sang JUL rồi mặc định kết quả vẫn được thay tham số. Backend, formatter và phiên bản thư viện cũng quyết định chính xác cách render message.

Placeholder giúp mã logging dễ đọc, giữ cấu trúc thông điệp nhất quán và có thể tránh việc tạo chuỗi cuối cùng khi mức log bị tắt. Tuy nhiên, truyền tham số vào lời gọi logger **không có nghĩa là Java bỏ qua việc tính toán biểu thức đối số**; phần này được phân tích ở mục 6.

## 2. Vì sao nên dùng placeholder thay vì nối chuỗi?

So sánh hai cách ghi cùng một sự kiện trong ứng dụng dùng SLF4J:

```java
// Nối chuỗi:
log.debug("Loading order " + orderId + " from " + source);

// Placeholder:
log.debug("Loading order {} from {}", orderId, source);
```

Ở cách nối chuỗi, Java tạo chuỗi kết quả **trước khi gọi** `debug(...)`, kể cả khi sự kiện DEBUG không được ghi. Với cách placeholder, logger nhận mẫu và tham số riêng; nếu DEBUG bị tắt, backend thường có thể bỏ qua bước render chuỗi và gọi `toString()` cho tham số.

Đây không chỉ là câu chuyện hiệu năng:

- **Dễ đọc:** người đọc thấy một mẫu thông điệp rõ ràng và danh sách dữ liệu tương ứng.
- **Dễ nhất quán:** event tương tự có cùng template, thuận tiện khi nhóm các log message.
- **Bảo toàn ý định:** code thể hiện rõ phần văn bản cố định và phần giá trị biến đổi.
- **Tích hợp tốt hơn với công cụ:** một số backend/collector có thể giữ thêm template và arguments; việc đó tùy khả năng và cấu hình, **không tự xảy ra với mọi logger**.
- **Tách bước tạo message:** API có thể quyết định lúc nào và cách nào format đối số, thay vì để phép nối chuỗi của ứng dụng quyết định ngay.

Nhưng placeholder **không phải prepared statement của SQL**, không tự chống log injection, không che dữ liệu nhạy cảm và không biến message text thành JSON có cấu trúc. Những trách nhiệm đó vẫn cần thiết kế riêng.

## 3. SLF4J: placeholder `{}`

SLF4J là một **logging facade**; ứng dụng gọi API SLF4J, còn provider/backend thực hiện việc ghi và định dạng. Trong kiểu gọi parameterized logging thông dụng, ký hiệu `{}` đại diện cho tham số ở vị trí tương ứng.

### 3.1. Thay lần lượt các đối số

```java
String orderId = "ORD-7";
String status = "ACCEPTED";
int quantity = 3;

log.info("orderId={} status={} quantity={}", orderId, status, quantity);
```

Thông điệp sau khi render:

```text
orderId=ORD-7 status=ACCEPTED quantity=3
```

Đây là **đoạn minh họa SLF4J**, giả định biến `log` đã được tạo và backend có cấu hình ghi INFO. Output trên là **phần message**, không phải toàn bộ dòng console: appender/layout có thể tự thêm thời gian, level, logger name và tên thread.

Mỗi `{}` dùng tham số tiếp theo theo thứ tự. Nó không mang tên hoặc số chỉ mục như `{0}` của JUL; nếu cần cùng một giá trị ở hai chỗ, hãy truyền giá trị đó hai lần:

```java
log.info("orderId={} relatedOrderId={}", orderId, orderId);
```

Tránh ghép placeholder với nội dung có vị trí khó hiểu:

```java
// Dễ đọc và dễ tra cứu:
log.info("orderId={} paymentId={} result={}", orderId, paymentId, result);

// Khó hiểu nếu chỉ thấy giá trị:
log.info("{} {} {}", orderId, paymentId, result);
```

Một thông điệp tốt thường chứa **tên trường hoặc động từ mô tả sự kiện**. Placeholder chỉ là cơ chế chèn giá trị, không tự làm thông điệp có ý nghĩa.

### 3.2. Kiểu dữ liệu được render như thế nào?

Trong SLF4J, đối số số học, boolean và đối tượng thường được chuyển thành biểu diễn text phù hợp. Với đối tượng tùy biến, kết quả phụ thuộc vào `toString()` hoặc cơ chế định dạng của API/backend.

```java
log.info("attempt={} success={}", 2, false);
log.info("customer={}", customer);
```

Nếu `customer.toString()` trả về chuỗi chứa quá nhiều thông tin hoặc dữ liệu nhạy cảm, log cũng có thể làm lộ dữ liệu đó. Thường tốt hơn là ghi các trường có chủ đích:

```java
log.info("customerId={} status={}", customerId, status);
```

Với mảng, một số phiên bản/cơ chế định dạng của SLF4J xử lý phần tử hoặc mảng lồng nhau; đừng dựa vào `Object.toString()` làm định dạng chuẩn nghiệp vụ. Nếu hệ thống cần schema ổn định, dùng các trường structured logging thay vì chuyển cả object thành một chuỗi dài.

### 3.3. Placeholder không phải tên thuộc tính

Lời gọi:

```java
log.info("orderId={} status={}", orderId, status);
```

thường tạo **một message đã render** như `orderId=ORD-7 status=ACCEPTED`. Nó **không bảo đảm** collector tự nhận được hai trường JSON riêng có tên `orderId` và `status`.

Nếu cần lưu `orderId` như một trường có thể lọc chính xác, hãy dùng **structured arguments, key–value pairs, MDC hoặc cơ chế logging có cấu trúc** phù hợp với API/backend. Phân biệt rõ:

- **Message template:** chuỗi văn bản có placeholder.
- **Arguments:** giá trị dùng khi render template.
- **Structured fields:** các cặp tên–giá trị được backend/encoder ghi thành trường riêng, nếu đã cấu hình.

## 4. JUL: placeholder `{0}` và `MessageFormat`

`java.util.logging` có sẵn trong JDK. JUL không dùng quy tắc `{}` của SLF4J làm mặc định; với message có tham số, `java.util.logging.Formatter.formatMessage(LogRecord)` sử dụng các quy tắc của `java.text.MessageFormat` khi định dạng.

Ví dụ:

```java
Logger logger = Logger.getLogger("com.example.orders");
logger.log(Level.INFO,
        "orderId={0} status={1}",
        new Object[]{"ORD-7", "ACCEPTED"});
```

Mẫu `{0}` lấy phần tử thứ 0 và `{1}` lấy phần tử thứ 1 trong danh sách tham số. Khác với `{}` của SLF4J, **chỉ mục có ý nghĩa**: có thể đổi thứ tự hoặc lặp một tham số theo mẫu.

### 4.1. Điểm nối giữa LogRecord và Formatter

Khi phát sự kiện JUL, logger lưu message template và các tham số trong `LogRecord`. Formatter quyết định chuỗi hiển thị:

```java
// Bên trong lớp extends java.util.logging.Formatter:
String raw = record.getMessage();          // Mẫu, ví dụ "orderId={0}"
String shown = formatMessage(record);      // Giá trị đã được chèn
```

Đây là **hai dòng minh họa bên trong formatter**, chưa phải chương trình độc lập. Nếu tự viết formatter và chỉ dùng `getMessage()`, có thể thấy nguyên văn `{0}` trong output. Khi muốn message đã chèn tham số, dùng `formatMessage(record)`.

Nếu `LogRecord` có resource bundle, `formatMessage` còn xử lý việc tra message từ bundle trước khi format. Cần nhớ đó là bước của formatter; gọi `log.log(...)` không có nghĩa chuỗi được ghép ngay tại vị trí mã nguồn.

### 4.2. Ví dụ Java 17+ hoàn chỉnh, không cần thư viện ngoài

Tạo tệp `PlaceholderDemo.java`:

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class PlaceholderDemo {
    private static final Logger LOG =
            Logger.getLogger(PlaceholderDemo.class.getName());

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.INFO);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " " + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        LOG.addHandler(console);

        String requestId = "req-42";
        String orderId = "ORD-7";

        LOG.log(Level.INFO,
                "requestId={0} orderId={1} status={2}",
                new Object[]{requestId, orderId, "ACCEPTED"});

        LOG.log(Level.WARNING,
                "orderId={0} retryAttempt={1}",
                new Object[]{orderId, 2});

        LOG.log(Level.INFO,
                "order ''{0}'' completed",
                new Object[]{orderId});

        LOG.log(Level.FINE,
                "hiddenDebug={0}",
                new Object[]{orderId});

        console.flush();
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên từ thư mục chứa tệp:

```bash
javac -encoding UTF-8 PlaceholderDemo.java
java PlaceholderDemo
```

Kết quả hiển thị trên console:

```text
INFO requestId=req-42 orderId=ORD-7 status=ACCEPTED
WARNING orderId=ORD-7 retryAttempt=2
INFO order 'ORD-7' completed
```

Các dòng này nằm trên **stderr** vì `ConsoleHandler` của JUL ghi vào luồng lỗi chuẩn; **stdout không có nội dung từ ví dụ**. Đầu ra không có timestamp vì formatter ví dụ chỉ ghép level và message, giúp xác định chính xác từng dòng.

Giải thích:

1. `LOG.log(Level.INFO, template, Object[])` giữ mẫu và tham số. `formatMessage(record)` thay `{0}`, `{1}`, `{2}` trong thứ tự được chỉ định.
2. `retryAttempt={1}` nhận số nguyên `2` và xuất thành `2` trong trường hợp này.
3. `MessageFormat` coi dấu nháy đơn là ký hiệu điều khiển cú pháp. Viết `''` để xuất **một dấu nháy đơn**: mẫu `"order ''{0}'' completed"` cho ra `order 'ORD-7' completed`.
4. `Level.FINE` thấp hơn `Level.INFO` nên sự kiện `hiddenDebug` không xuất hiện; logger và handler đều đặt mức INFO.
5. `LOG.setUseParentHandlers(false)` tránh output bị nhân đôi do sự kiện đồng thời truyền lên các handler cha trong ví dụ; nó không đổi cú pháp placeholder.

**Lưu ý về `MessageFormat`:** ngoài `{0}`, nó hỗ trợ cách viết như `{0,number}`, `{0,date}` với các quy tắc locale. Các định dạng số/ngày có thể thay đổi theo locale hoặc timezone, do đó khi cần output ổn định giữa server, phải chọn quy ước rõ ràng. Không mặc định một message formatter tùy chỉnh sẽ hiểu hết cú pháp này nếu nó bỏ qua `formatMessage`.

### 4.3. Những cách gọi JUL dễ nhầm

```java
// Không phải placeholder tham số hợp lệ của JUL:
LOG.info("orderId={}");

// Đây chỉ là chuỗi text chứa hai dấu ngoặc nhọn.
// Sử dụng template của JUL và API có tham số:
LOG.log(Level.INFO, "orderId={0}", "ORD-7");
```

Đoạn trên minh họa các cách gọi; giả định `LOG` đã tồn tại và level INFO đang bật. Với `LOG.info("orderId={0}")` mà không truyền parameters, không có giá trị nào để chèn: formatter không thể tự biết mã đơn hàng. Với JUL, đừng thay `{0}` bằng `{}` theo thói quen khi chuyển từ SLF4J.

## 5. Log4j 2 và ranh giới của cú pháp placeholder

Log4j 2 API thường hỗ trợ parameterized message kiểu `{}`:

```java
// Ví dụ minh họa Log4j 2; cần dependency và cấu hình backend tương ứng.
private static final org.apache.logging.log4j.Logger LOG =
        org.apache.logging.log4j.LogManager.getLogger(OrderService.class);

LOG.info("orderId={} status={}", orderId, status);
```

Đây là **đoạn code minh họa**, không phải tệp Java hoàn chỉnh có thể chạy độc lập. Hành vi hiển thị cụ thể còn tùy loại `Message` được dùng và cấu hình Log4j 2. Tránh coi mọi tính năng của Log4j 2, SLF4J và JUL là một giao thức placeholder chung, dù trong tình huống đơn giản cùng dùng dấu `{}`.

Ngoài parameterized message, Log4j 2 có cơ chế message/structured logging khác nhau. Chọn API và loại message dựa trên backend thực tế, cách thu thập log và yêu cầu truy vấn. Khi chuyển hệ sinh thái, kiểm thử **cả kết quả render lẫn thông tin được lưu thành trường riêng**.

## 6. Placeholder giúp hiệu năng ở đâu và không giúp ở đâu?

### 6.1. Phần chuỗi được trì hoãn

Trong SLF4J:

```java
log.debug("Loaded item={} from cache={}", itemId, cacheName);
```

Khi DEBUG bị tắt, logger thường có thể bỏ qua việc tạo message hoàn chỉnh và chuyển đối tượng thành chuỗi. Điều này có lợi nếu ứng dụng ghi log rất nhiều hoặc đối tượng có `toString()` tương đối tốn chi phí.

Trái lại:

```java
log.debug("Loaded item=" + itemId + " from cache=" + cacheName);
```

Phép nối chuỗi thực hiện **trước lời gọi logger**, bất kể DEBUG có bị lọc hay không.

### 6.2. Biểu thức đối số vẫn được Java tính trước

Ví dụ:

```java
log.debug("Full report={}", buildExpensiveReport());
```

Java gọi `buildExpensiveReport()` trước khi gọi `log.debug(...)`, **ngay cả khi DEBUG bị tắt**. Placeholder không hoãn việc tính biểu thức.

Nếu phép tính thực sự tốn chi phí, có thể dùng guard:

```java
if (log.isDebugEnabled()) {
    log.debug("Full report={}", buildExpensiveReport());
}
```

Các đoạn này dùng API SLF4J giả định; muốn biên dịch cần khai báo `log` và dependency phù hợp. Guard chỉ nên thêm khi phép tính đáng kể, tránh làm code rối cho những tham số đơn giản.

### 6.3. Lazy message trong JUL

JUL có overload nhận `Supplier<String>` để tạo message khi level được bật:

```java
// LOG là java.util.logging.Logger:
LOG.log(Level.FINE, () -> "report=" + buildExpensiveReport());
```

Với mức FINE bị tắt, supplier không cần được thực thi. Đây là **đoạn code minh họa**, giả định `buildExpensiveReport()` tồn tại. Nó tạo ra một **chuỗi cuối cùng bằng supplier**, không phải cơ chế truyền mảng tham số `{0}`; khi cần chọn cách tiếp cận, hãy cân nhắc yêu cầu hoãn tính toán so với việc giữ template/arguments riêng.

JUL cũng có overload `log(Level, Throwable, Supplier<String>)` để ghi exception cùng message cung cấp theo kiểu lazy. API này hữu ích nhưng không thay đổi thực tế rằng nếu biểu thức đối số được tính bên ngoài lambda thì nó vẫn được tính sớm.

### 6.4. Fluent API của SLF4J 2.x

Trong các ứng dụng đã dùng **SLF4J 2.x**, fluent API có thể biểu đạt các giá trị và supplier theo cú pháp builder:

```java
// Minh họa SLF4J 2.x; cần biến log và dependency:
log.atDebug()
        .addArgument(() -> buildExpensiveReport())
        .log("Full report={}");
```

Supplier được backend/API gọi khi cần theo cách xử lý logging fluent, nên tránh tính giá trị đắt tiền chỉ để tạo một thông điệp bị tắt. Dùng phiên bản thư viện hỗ trợ API tương ứng; đây **không phải cú pháp của SLF4J 1.x hay JUL**.

## 7. Throwable có phải là tham số của placeholder?

Khi bắt exception, cần vừa mô tả ngữ cảnh vừa giữ được nguyên nhân lỗi. Đây là điểm thường gây nhầm giữa các overload:

```java
// SLF4J thông dụng: Throwable ở vị trí cuối.
log.error("Failed to save orderId={} stage={}", orderId, stage, error);
```

Với API SLF4J thông dụng, một `Throwable` ở vị trí tham số cuối trong lời gọi parameterized logging thường được nhận diện là **nguyên nhân lỗi**, để backend ghi stack trace, thay vì chỉ coi nó là giá trị cần in vào placeholder cuối. Điều này phụ thuộc vào overload và số lượng tham số; phải kiểm tra theo API đang dùng.

**Không nên làm như sau:**

```java
log.error("Failed to save: {}", error.getMessage());
```

Đoạn đó chỉ ghi một chuỗi message và có thể làm mất stack trace/cause chain. Khi thích hợp, truyền **đối tượng Throwable** qua overload của logger.

Với JUL, các overload cần phân biệt rõ:

```java
// Ghi exception trực tiếp, message không có tham số:
LOG.log(Level.SEVERE, "Failed to save order ORD-7", error);

// Ghi message có tham số (mảng arguments), không tự gắn throwable:
LOG.log(Level.SEVERE,
        "Failed to save order {0}",
        new Object[]{"ORD-7"});
```

Nếu cần **cả template có tham số và Throwable** trong JUL, có thể tạo một `LogRecord` và đặt hai thuộc tính riêng:

```java
// Đoạn minh họa; error là một Throwable đã bắt được.
LogRecord record = new LogRecord(Level.SEVERE,
        "Failed to save order {0}");
record.setParameters(new Object[]{"ORD-7"});
record.setThrown(error);
LOG.log(record);
```

`LogRecord` của JUL và các overload được dùng ở trên chỉ có tác dụng khi formatter/handler xử lý đầy đủ parameters và `getThrown()`. Một formatter tự viết chỉ trả `formatMessage(record)` có thể **bỏ mất stack trace**; cần formatter xử lý Throwable hoặc sử dụng formatter có sẵn phù hợp.

## 8. Placeholder và logging có cấu trúc

Dễ nhầm hai ý:

- **Parameterized message:** `"orderId={} status={}"` và đối số sẽ được chuyển thành một thông điệp người đọc thấy.
- **Structured logging:** log event có các trường độc lập, ví dụ `orderId`, `status`, `traceId`, được bộ mã hóa ghi ra JSON hoặc định dạng có cấu trúc.

Ví dụ message thông thường:

```text
INFO OrderService - orderId=ORD-7 status=ACCEPTED
```

Ví dụ JSON có cấu trúc:

```json
{
  "timestamp": "2026-11-09T08:15:03.125Z",
  "level": "INFO",
  "logger": "com.example.orders.OrderService",
  "event": "order_accepted",
  "orderId": "ORD-7",
  "status": "ACCEPTED",
  "traceId": "trace-42",
  "message": "Order accepted"
}
```

JSON trên **chỉ là minh họa schema**, không phải output tự động của các lời gọi logger ở trên. Nếu collector cần truy vấn `orderId` như một trường chính xác thay vì dùng regex trên chuỗi, phải cung cấp dữ liệu có cấu trúc và cấu hình layout/encoder/collector để bảo toàn trường đó.

**MDC/correlation context** giúp gắn cùng một requestId hoặc traceId vào nhiều log record; placeholder không tự truyền ngữ cảnh qua thread hoặc service. Với ứng dụng dùng thread pool, cần thiết kế sao chép và dọn MDC đúng thời điểm để không lẫn thông tin giữa các request.

## 9. Quy tắc format đặc thù và các bẫy thường gặp

### 9.1. Dấu nháy đơn trong `MessageFormat`

Với JUL, `MessageFormat` dùng dấu nháy đơn làm cú pháp trích dẫn. Nếu muốn có dấu `'` thật sự trong output khi format tham số, mẫu thường cần `''` như ví dụ Java chạy ở trên:

```text
Template: order ''{0}'' completed
Argument: ORD-7
Result:   order 'ORD-7' completed
```

Đừng coi quy tắc này là bắt buộc cho `{}` của SLF4J: mỗi hệ sinh thái có quy tắc khác nhau. Khi thông điệp chứa dấu nháy đơn, braces, ký tự escape hoặc nội dung tự nhiên của người dùng, cần kiểm thử trực tiếp với formatter thực tế.

### 9.2. Số placeholder không khớp số đối số

```java
// Thiếu một tham số so với hai placeholder:
log.info("orderId={} status={}", orderId);

// Truyền nhiều hơn dự định:
log.info("orderId={}", orderId, status);
```

Các đoạn dùng SLF4J giả định. Cách xử lý chỗ thiếu/thừa có thể khác nhau theo API, backend, overload và việc tham số cuối có phải Throwable hay không. Đừng xây logic nghiệp vụ dựa trên hành vi khôi phục khi sai số lượng tham số. Khi review, **đếm placeholder và kiểm tra thứ tự đối số**, nhất là sau khi sửa template.

Với JUL, mẫu `{0}`, `{1}` có chỉ mục rõ ràng; hãy chắc chắn mảng `Object[]` chứa đủ phần tử và có kiểu phù hợp nếu dùng định dạng `number`/`date`.

### 9.3. In object phức tạp

```java
log.info("order={}", order);
```

Nếu `order.toString()` có truy cập lazy fields, duyệt collection lớn hoặc in dữ liệu nhạy cảm, hệ quả có thể là chậm, lộ dữ liệu hoặc log khổng lồ. Ưu tiên thông điệp có ý nghĩa và trường nhỏ, ổn định:

```java
log.info("orderId={} itemCount={} state={}",
        order.getId(), order.getItemCount(), order.getState());
```

Dù dùng placeholder, **các getter vẫn được gọi trước khi vào logger** trong lời gọi Java thông thường. Nếu getter đắt tiền và level thường bị tắt, cân nhắc guard hoặc API supplier.

### 9.4. Ký tự xuống dòng và log injection

Ví dụ `customerName` đến từ dữ liệu nhập và chứa ký tự xuống dòng hoặc đoạn text giả làm một dòng log khác. Placeholder **không tự escape** dữ liệu đó thành một dòng an toàn. Hãy chọn encoder/formatter có escaping phù hợp, giới hạn kích thước, tránh ghi payload không kiểm soát và kiểm thử cách collector xử lý multiline.

Nếu xuất JSON, dùng encoder/serializer chuẩn để escape dấu ngoặc kép và control characters. Không xây JSON bằng nối chuỗi với giá trị tham số người dùng.

### 9.5. Lộ dữ liệu nhạy cảm

`log.info("Authorization={}", token)` vẫn ghi token nếu event được ghi; placeholder không phải masking. Tránh log password, access token, API key, dữ liệu thanh toán hay thông tin cá nhân không cần thiết. Áp dụng kiểm soát dữ liệu tại nguồn và redaction phù hợp với quy định của hệ thống.

### 9.6. Mất stack trace

`log.error("failed={}", error.getMessage())` là log một thông điệp, không truyền đối tượng Throwable. Nếu cần điều tra ngoại lệ, truyền Throwable vào API hỗ trợ; đảm bảo layout/encoder thực sự xuất exception. Tránh ghi lặp cùng exception ở mọi tầng.

### 9.7. Nhầm giữa số học và kiểu chuỗi

Với `MessageFormat`, các mẫu `{0,number}` hoặc `{0,date}` yêu cầu dữ liệu phù hợp. Nếu truyền sai kiểu hoặc thiếu tham số, việc format có thể cho kết quả không mong muốn hoặc gây lỗi trong quá trình render. Đối với log cần ổn định qua locale, dùng kiểu dữ liệu nhất quán và kiểm thử định dạng.

## 10. Khắc phục lỗi khi placeholder không được thay

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| Log hiển thị nguyên `{}` | Dùng cú pháp SLF4J trong JUL hoặc chưa có arguments | Chọn đúng API và tham số phù hợp |
| Log hiển thị nguyên `{0}` | Formatter chỉ lấy `getMessage()` hoặc không có tham số | Với JUL, dùng `formatMessage(record)` và overload nhận parameters |
| Message bị thiếu hoặc thừa giá trị | Số placeholder, thứ tự args hoặc overload không khớp | Soát template và call site, đặc biệt Throwable cuối |
| Log có dấu nháy đơn khác dự kiến | Cú pháp dấu `'` của `MessageFormat` | Escape `''` và viết test cho output |
| DEBUG đã tắt nhưng ứng dụng vẫn xử lý nặng | Đối số là lời gọi hàm được tính trước | Dùng guard hoặc API lazy/supplier thích hợp |
| Không có stack trace | Truyền `error.getMessage()` hoặc formatter bỏ Throwable | Ghi đối tượng Throwable và kiểm tra encoder |
| Giá trị object rất dài hoặc nhạy cảm | `toString()` chứa dữ liệu ngoài ý muốn | Ghi trường cụ thể, giới hạn và lọc dữ liệu |
| JSON không parse được | Tự nối JSON hoặc trộn text với JSON | Dùng structured encoder và kiểm thử parser |
| Khác định dạng giữa các service | Backend/locale/timezone hoặc template khác nhau | Thống nhất schema, convention và test thực tế |

Khi điều tra, trước hết xác định **logging API nào được gọi**, backend thực sự là gì, formatter/layout nào đang nhận sự kiện, và mức log có cho phép sự kiện tới đích không. Nếu sự kiện bị filter từ đầu thì việc đổi placeholder không thể làm nó xuất hiện.

## 11. Checklist viết log message với placeholder

1. **Đúng API:** chọn `{}` cho kiểu SLF4J/Log4j 2 parameterized logging thông dụng; chọn `{0}`, `{1}` cho JUL khi dùng `MessageFormat`.
2. **Tên sự kiện rõ:** viết message có động từ hoặc trường có tên, ví dụ `orderId={} status={}`.
3. **Đúng đối số:** kiểm tra thứ tự, số lượng, kiểu dữ liệu và overload dành cho Throwable.
4. **Giữ exception:** truyền `Throwable` thật sự nếu cần stack trace và kiểm tra formatter.
5. **Không tính phí vô ích:** hạn chế nối chuỗi; tránh gọi hàm đắt tiền trước logger khi level thường tắt.
6. **Không lộ bí mật:** kiểm tra tham số và `toString()`, escape ký tự nguy hiểm, giới hạn dung lượng.
7. **Phân biệt với structured fields:** nếu cần truy vấn chính xác theo khóa, dùng logging có cấu trúc thay vì mong collector tự hiểu phần message.
8. **Kiểm thử output thực tế:** đối chiếu cả level, text, exception, timezone/locale và hành vi khi log level tắt.

**Nguyên tắc thực hành:** giữ một message template ổn định, truyền tham số qua API tương ứng, và để formatter/backend xử lý cách biểu diễn. Placeholder giúp mã logging gọn, dễ hiểu và có thể giảm chi phí dựng chuỗi; chất lượng log vẫn phụ thuộc vào ngữ cảnh, mức log, bảo mật và cách thu thập dữ liệu.
