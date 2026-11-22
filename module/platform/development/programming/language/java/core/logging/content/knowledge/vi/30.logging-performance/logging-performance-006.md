# Chi phí serialization trong logging Java

## 1. Vì sao serialization ảnh hưởng đến hiệu năng logging?

Trong ứng dụng Java, một câu lệnh logging có thể làm nhiều việc hơn là ghi vài ký tự. Khi gọi logger, ứng dụng có thể tạo đối tượng sự kiện, đánh giá tham số, chuyển object thành chuỗi, chuẩn hóa timestamp, chụp MDC/trace context, mã hóa JSON, định dạng exception và cuối cùng ghi bytes ra console, tệp hoặc mạng.

**Serialization trong phạm vi logging** là quá trình biểu diễn dữ liệu của log event thành dạng có thể ghi hoặc truyền đi, thường là **chuỗi văn bản hoặc JSON**. Thuật ngữ này bao gồm việc gọi `toString()`, định dạng message/parameters, biến một object graph thành JSON và mã hóa các trường structured logging. Nó **khác** với Java native object serialization bằng `ObjectOutputStream`, `Serializable` và `serialVersionUID`; thông thường không cần dùng cơ chế đó để xuất application logs.

Chi phí serialization quan trọng vì một ứng dụng có thể tạo rất nhiều log event trong mỗi request. Ngay cả khi đích ghi nhanh, CPU và bộ nhớ dành cho việc chuẩn bị dữ liệu log vẫn có thể ảnh hưởng đến độ trễ và throughput của nghiệp vụ.

Sau bài học, bạn có thể:

- Xác định serialization diễn ra ở đâu trong chuỗi xử lý log và vì sao **log bị tắt vẫn có thể tốn chi phí**.
- Phân biệt **eager evaluation**, **lazy evaluation**, level/filter và serialization ở appender/encoder.
- Dùng Java 17 `java.util.logging` để chứng minh chi phí tạo chuỗi trước/sau kiểm tra level.
- Viết logging hiệu quả hơn với SLF4J/Logback/Log4j 2 và structured JSON logs.
- Đo chi phí CPU, allocation/GC, độ trễ và ảnh hưởng từ asynchronous logging một cách đáng tin cậy.

## 2. Một log event đi qua những giai đoạn nào?

Hãy hình dung luồng xử lý:

```text
Business thread
    |
    |  A. Đánh giá đối số trong Java trước khi gọi phương thức
    |     - nối chuỗi, String.format, toJson, toString gọi trực tiếp
    v
Logger API
    |
    |  B. Quyết định bật/tắt level và các filter sớm
    v
Log event
    |
    |  C. Chụp timestamp, thread name, MDC, tham số, Throwable...
    v
Async queue (nếu được cấu hình)
    |
    |  D. Chuẩn bị/chụp thêm dữ liệu cần để chuyển thread
    v
Appender / Encoder / Formatter
    |
    |  E. Render message, serialize structured fields/JSON,
    |     escape ký tự, format stack trace, mã hóa bytes
    v
File / stdout / network / collector
    |
    |  F. I/O, buffering, backpressure, gửi và nhận dữ liệu
```

**Điểm quan trọng nhất:** giai đoạn **A xảy ra trước** khi phương thức logger nhận tham số, theo quy tắc đánh giá biểu thức của Java. Logger không thể ngăn một lời gọi `toJson(order)` đã chạy xong chỉ vì level DEBUG đang tắt.

Thời điểm thực hiện C, D và E phụ thuộc logging framework, encoder/appender và chế độ đồng bộ hay bất đồng bộ. Một số provider tạo formatted message trước khi enqueue; một số giữ đối số rồi định dạng ở worker; một số structured encoder chỉ serialize giá trị khi xuất. Không nên mặc định “async logging” tự động làm serialization miễn phí hoặc luôn diễn ra trên thread nền.

Có thể tách chi phí tương đối thành:

\[
C_{\text{log}} = C_{\text{prepare}} + C_{\text{filter}} + C_{\text{event}} + C_{\text{serialize}} + C_{\text{queue}} + C_{\text{I/O}}
\]

Đây là **mô hình khái niệm**, không phải công thức đo chính xác: các bước có thể chồng lấp, thực hiện ở thread khác hoặc bị bỏ qua. Khi log level bị tắt, chi phí lý tưởng chỉ còn kiểm tra điều kiện rất nhỏ; eager serialization phá vỡ lợi ích đó.

## 3. Eager serialization và lazy serialization

### 3.1. Chi phí bị trả trước khi logger kiểm tra level

Những cách viết sau thực hiện công việc tốn kém **trước** lời gọi logger, bất kể log cuối cùng có được ghi hay không:

```java
// Mã tích hợp minh họa, giả định có logger, order và các hàm tương ứng.
logger.debug("Order = " + toJson(order));
logger.debug(String.format("Order: %s", expensiveFormat(order)));
logger.debug("Snapshot {}", buildLargeSnapshot(order));
```

Ở hai dòng đầu, phép nối chuỗi, `String.format`, `toJson`, `expensiveFormat` luôn chạy khi thực thi dòng code. Với SLF4J, dấu `{}` ở dòng thứ ba giúp backend định dạng message, nhưng **đối số `buildLargeSnapshot(order)` đã được Java tính xong** trước khi gọi `debug`.

Điều này thường gây tốn CPU và allocation ngay cả khi production đặt root level là INFO/WARN và DEBUG không được xuất.

### 3.2. Chuyển quyết định tốn kém sang sau bước kiểm tra level

Các lựa chọn tương ứng:

```java
// Mã tích hợp minh họa, logger là SLF4J logger đã khởi tạo.
if (logger.isDebugEnabled()) {
    logger.debug("Order = {}", toJson(order));
}
```

Đây là cách rõ ràng khi việc tạo đối số đắt và bản thân lời gọi không có side effect cần thiết. Với **SLF4J 2.x** có fluent API, có thể cung cấp `Supplier`:

```java
// Mã tích hợp cho SLF4J 2.x, toJson(order) là hàm của ứng dụng.
logger.atDebug()
      .addArgument(() -> toJson(order))
      .log("Order = {}");
```

Khi DEBUG bị vô hiệu theo cơ chế SLF4J 2.x, supplier không cần được đánh giá. Khi DEBUG được bật, giá trị sẽ được tạo để phục vụ event. API và tính năng của provider cần tương thích phiên bản; không áp dụng cú pháp này nguyên xi cho SLF4J 1.7.

Một lựa chọn khác là truyền **đối tượng** thay vì tạo JSON trước:

```java
// Mã tích hợp cho SLF4J. Cần hiểu semantics của backend.
logger.debug("Order = {}", order);
```

Cách này thường tránh nối chuỗi ngay tại call site khi DEBUG tắt, nhưng **không bảo đảm không có serialization** khi DEBUG bật. Backend có thể gọi `order.toString()`, serialize sớm hoặc chụp dữ liệu trước khi enqueue. Nếu `toString()` của object nặng, truy cập quan hệ lười tải (lazy-loaded entity) hoặc chứa dữ liệu nhạy cảm, vẫn có rủi ro CPU, I/O hoặc bảo mật.

## 4. Ví dụ Java 17 chạy độc lập: đếm số lần serialization

Ví dụ sử dụng **JUL** (`java.util.logging`) có sẵn trong JDK. Chúng ta mô phỏng hàm chuyển đối tượng `Order` thành text, tăng biến đếm khi hàm chạy, rồi thử:

1. **Eager:** nối chuỗi khi FINE đang tắt.
2. **Lazy:** truyền `Supplier<String>` khi FINE đang tắt.
3. Ghi INFO bình thường không cần serialization.
4. **Lazy khi INFO bật:** supplier được đánh giá.

Tạo file `LoggingSerializationCostDemo.java`:

```java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LoggingSerializationCostDemo {
    private record Order(long id, int amount) {}

    private static int serializationCalls;

    private static String serialize(Order order) {
        serializationCalls++;
        return "orderId=" + order.id() + ",amount=" + order.amount();
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("lesson.serialization.cost");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO); // FINE không được phép.

        Handler output = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println(record.getMessage());
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
        };
        output.setLevel(Level.ALL);
        logger.addHandler(output);

        try {
            Order order = new Order(7L, 420);

            logger.fine("eager " + serialize(order));
            logger.log(Level.FINE, () -> "lazy " + serialize(order));

            logger.info("info without payload");
            logger.log(Level.INFO,
                    () -> "info " + serialize(order));

            System.out.println("serializationCalls="
                    + serializationCalls);
        } finally {
            logger.removeHandler(output);
            output.close();
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

```bash
javac LoggingSerializationCostDemo.java
java LoggingSerializationCostDemo
```

**Stdout chính xác** trong một JVM mới với ví dụ trên:

```text
info without payload
info orderId=7,amount=420
serializationCalls=2
```

Giải thích:

- `logger.fine("eager " + serialize(order))` vẫn gọi `serialize` trước khi JUL xét level; bộ đếm chuyển thành **1**, nhưng FINE bị tắt nên dòng đó không xuất hiện.
- `logger.log(Level.FINE, () -> ...)` đưa vào một lambda; khi level FINE không được chấp nhận, JUL không cần gọi supplier. Bộ đếm vẫn là **1**.
- `logger.info("info without payload")` tạo event INFO được chấp nhận, nhưng không gọi hàm serialize mô phỏng.
- `logger.log(Level.INFO, () -> "info " + serialize(order))` gọi supplier khi INFO được chấp nhận, bộ đếm thành **2** và handler in message.
- Handler tự viết gọi `isLoggable(record)`, xuất vào `System.out` và không thêm timestamp nên kết quả không phụ thuộc đồng hồ. `finally` gỡ và đóng handler mà demo tự tạo.

**Giới hạn ví dụ:** Bộ đếm chỉ phản ánh số lần hàm `serialize` chạy, **không đo thời gian hoặc dung lượng bộ nhớ**. Hàm ở đây tạo text ngắn bằng phép nối chuỗi, chưa phải JSON serializer thật. Trong hệ thống production, chi phí serialization phụ thuộc độ sâu object graph, encoding, formatter, backend, JIT, allocation, heap và tải thực tế.

### 4.1. Guard thủ công với JUL

Nếu không dùng supplier, có thể đặt điều kiện trước phần tạo dữ liệu:

```java
// Mảnh code tích hợp: logger là java.util.logging.Logger.
if (logger.isLoggable(Level.FINE)) {
    logger.fine("order=" + serialize(order));
}
```

Điều kiện này giúp không gọi `serialize` khi FINE bị vô hiệu tại **logger**. Tuy nhiên, logger vẫn có thể tạo event rồi handler/appender filter **ở tầng sau** loại nó. Guard theo level không bảo đảm tránh serialization nếu event bị bỏ ở sink. Nếu cần tránh chi phí cho cả filter tại appender, phải xem lại thứ tự lọc/điểm đặt filter của framework.

Không đưa nghiệp vụ có side effect vào `Supplier` log: logging có thể bị tắt, filter loại event hoặc backend xử lý khác dự kiến. Ví dụ **không** đặt thao tác cập nhật trạng thái giao dịch hay gọi API trong hàm lazy chỉ để phục vụ log.

## 5. Chi phí của object.toString()

Nhiều logger hỗ trợ parameterized message:

```java
// Ví dụ SLF4J, cần logger và đối tượng đã khởi tạo.
logger.info("Customer = {}", customer);
```

Khi INFO được chấp nhận, backend có thể cần chuyển `customer` thành chuỗi. Nếu `toString()` là phép nối vài field nguyên thủy, chi phí có thể nhỏ. Nếu nó:

- Duyệt danh sách lớn hoặc object graph nhiều tầng.
- Gọi hàm format ngày giờ, số hoặc dữ liệu locale.
- Thực hiện lazy loading qua ORM.
- Chuyển byte array, ảnh, request body hoặc payload lớn thành Base64/JSON.
- Gọi hàm khác có lock, I/O hay truy cập network.
- Vô tình in thông tin nhạy cảm trong entity.

...thì chi phí và rủi ro có thể rất lớn. Một `toString()` có thể còn gây đệ quy nếu các object tham chiếu vòng, hoặc in một biểu diễn rất dài mà không đem lại giá trị chẩn đoán.

**Giải pháp:** log một tập trường có chủ đích thay vì cả object:

```java
// Mã tích hợp với SLF4J.
logger.info("Order accepted id={} itemCount={} state={}",
        order.id(), order.itemCount(), order.state());
```

Ví dụ dùng một kiểu `order` có các accessor được định nghĩa trong ứng dụng, không phải chương trình Java độc lập. Các accessor nên rẻ, không phát sinh I/O hoặc tải dữ liệu lớn. Nếu có object thay đổi giữa lúc tạo event và lúc encoder chạy, hãy ưu tiên giá trị bất biến/snapshot phù hợp để log diễn đạt đúng thời điểm xảy ra sự kiện.

Không in toàn bộ object chỉ vì nó đã có `toString()`; quyết định log field nên dựa trên tính hữu ích và yêu cầu bảo mật.

## 6. Serialization trong structured logging và JSON

**Structured logging** lưu các trường có cấu trúc như:

```json
{
  "timestamp": "2026-11-10T02:00:00Z",
  "level": "INFO",
  "logger": "com.example.orders.OrderService",
  "message": "Order accepted",
  "order_id": 7,
  "amount": 420,
  "duration_ms": 18
}
```

Dữ liệu trên là **minh họa**, không phải log được thu thập từ một hệ thống thật. Trong nhiều deployment, một encoder/JSON layout tạo văn bản JSON và chuyển sang UTF-8 khi xuất.

Những chi phí thường gặp:

| Thành phần | Ví dụ chi phí |
| --- | --- |
| Tạo log event | Allocation, timestamp, level, logger/thread metadata |
| Thu thập trường | Đọc accessor, tạo map/key-value, snapshot MDC hoặc fields |
| Render message | Thay placeholder, gọi `toString()`, escape nội dung |
| JSON encoding | Duyệt field/object, serialize value, escape dấu ngoặc kép và ký tự điều khiển |
| Text encoding | Chuyển ký tự sang UTF-8, tạo hoặc ghi byte buffer |
| Stack trace | Lấy/duyệt frames và format exception/cause chain |
| Async queue | Tạo queue entry, đồng bộ, copy/snapshot dữ liệu, cạnh tranh thread |
| I/O | Flush, file rotation, stdout pipe, network và collector |

Structured logging **không tự động nhanh hơn text logging**. JSON có ưu điểm là máy xử lý dễ truy vấn các field nhất quán; đổi lại có thêm tên field, dấu phân cách, escaping và chi phí serialize. Đánh giá phải dựa trên encoder, lượng field, format và pipeline cụ thể.

### 6.1. Tránh serialize cùng dữ liệu hai lần

Một lỗi thường gặp là tự tạo JSON rồi giao cho JSON encoder một chuỗi chứa JSON:

```java
// Mã tích hợp minh họa: thường không nên làm thế.
logger.info("payload={}", toJson(order));
```

Nếu encoder lại bọc message trong một JSON object, giá trị `toJson(order)` có thể bị escape thêm. Kết quả vừa tốn CPU/bytes, vừa khiến `payload` trở thành chuỗi JSON nằm trong JSON, khó truy vấn field con.

Tốt hơn là gửi **những trường cần quan sát** theo structured logging API tương thích với backend, hoặc chọn encoder có thể serialize đối tượng một lần. Cần biết framework có chấp nhận key-value arguments, lúc nào copy dữ liệu và có dùng JSON serializer nào trong encoder. Với **SLF4J 2.x** có thể gắn các trường qua fluent API:

```java
// Đoạn tích hợp; logger là SLF4J 2.x logger.
logger.atInfo()
      .addKeyValue("order_id", order.id())
      .addKeyValue("amount", order.amount())
      .log("Order accepted");
```

Chú ý: việc gọi `order.id()` và `order.amount()` trong ví dụ là **đánh giá trực tiếp**. API key-value không khiến mọi phép tính đối số tự động lazy. Backend/layout cũng cần hỗ trợ xuất key-value fields; nếu chỉ dùng pattern text, có thể không thấy những field đó ở output hoặc chúng được render theo cách khác. Không coi fluent API là lời hứa về chi phí bằng 0.

### 6.2. Giới hạn kích thước và độ sâu

Serialize cả request/response body, entity ORM hoặc nested map có thể tạo payload khổng lồ. Chi phí thường tăng theo **số phần tử và kích thước dữ liệu thực tế**, đồng thời có thể bùng nổ khi object graph có nhánh sâu, collection lớn hoặc vòng tham chiếu.

Các giải pháp:
- Chỉ chọn ID, trạng thái, số lượng, mã lỗi và các field phục vụ chẩn đoán.
- Giới hạn số item và độ dài chuỗi ở lớp chuẩn bị dữ liệu.
- Với payload lớn cần phân tích chuyên sâu, lưu ở hệ thống phù hợp và chỉ log reference có kiểm soát truy cập.
- Không serialize entity có trường nhạy cảm một cách tự động.

## 7. Exception và stack trace là một nguồn chi phí đáng kể

Ghi exception có thể gây chi phí từ nhiều chỗ:
1. **Tạo exception** thường thu thập stack trace tại thời điểm xây dựng `Throwable`.
2. **Format stack trace** chuyển các frame và cause/suppressed exception thành text.
3. **Serialize/escape stack trace** khi ghi JSON hoặc qua collector multiline.
4. **Xuất bytes** tới file, console hoặc mạng.

Ví dụ log exception đúng với SLF4J:

```java
// Mảnh code tích hợp trong khối catch, logger là SLF4J.
logger.error("Failed to process orderId={}", orderId, exception);
```

Backend có thể format stack trace của `exception`. Không cần tự gọi `exception.printStackTrace()` đồng thời ở nhiều tầng hoặc nối `Arrays.toString(exception.getStackTrace())` vào message, trừ khi bạn có yêu cầu định dạng đặc biệt và đã xác minh pipeline.

**Đừng tạo stack trace chỉ phục vụ một log bị tắt**. Nếu muốn in diagnostics chi tiết ở DEBUG, hãy đặt phần thu thập/format dưới guard hoặc dùng lazy API phù hợp. Ngược lại, không xóa stack trace khỏi log lỗi quan trọng chỉ vì muốn tiết kiệm CPU; hãy phân cấp mức độ, tránh log trùng cùng exception ở nhiều tầng và cân nhắc sampling tại nơi cho phép.

## 8. Async logging có làm serialization nhanh hơn không?

Async logger thường tách **business thread** khỏi một phần công việc định dạng/xuất log. Nó có thể giảm thời gian business thread chờ I/O, nhưng không xóa chi phí CPU và allocation; chi phí có thể được chuyển sang thread nền, đồng thời tạo queueing và backpressure.

Có ba khả năng:

1. **Eager serialization tại call site:** `toJson(order)` đã chạy trước khi gọi logger. Bật async backend không thay đổi điều đó.
2. **Chuẩn bị event tại producer:** logger/backend copy message, parameter values, MDC, thread name hoặc format message trước khi enqueue để bảo đảm dữ liệu ổn định.
3. **Encoding tại consumer:** worker chuyển event thành text/JSON và ghi sink. Lúc này chi phí CPU vẫn tồn tại, đồng thời có nguy cơ queue backlog nếu worker chậm hơn producer.

Các framework có thiết kế khác nhau. Trong một hệ thống async, nếu chỉ giữ reference tới object mutable rồi serialize sau, dữ liệu có thể bị thay đổi giữa thời điểm event xảy ra và thời điểm worker xuất log. Đừng tự giả định backend giữ snapshot hoặc trì hoãn `toString()` theo một cách cố định; cần kiểm tra contract và phiên bản đang dùng.

**Tình huống queue đầy:** nếu tốc độ phát log cao hơn tốc độ serialize/xuất, queue có thể đầy. Tùy policy, business thread bị block, log level thấp bị drop hoặc backend dùng fallback. Mục tiêu của tối ưu là giảm *tổng chi phí và tác động lên nghiệp vụ*, không chỉ làm cho phương thức `logger.info` trả về nhanh.

**Shutdown:** các event đã enqueue vẫn cần drain và flush trong deadline. Một benchmark chỉ đo thời gian enqueue nhưng bỏ qua số event bị drop/không flush là phép đo thiếu.

## 9. Đo chi phí serialization đáng tin cậy

Không kết luận từ một phép đo `System.nanoTime()` quanh một lần `toString()` hoặc từ một vòng lặp ngắn chưa warm-up. JVM có JIT, escape analysis, dead-code elimination, GC, tiered compilation và nhiều nhiễu hệ điều hành. Cách đo hữu ích gồm hai tầng.

### 9.1. Microbenchmark phần chuẩn bị message/JSON

Với JMH (Java Microbenchmark Harness), xây benchmark theo các kịch bản:
- Eager `toJson(order)` khi DEBUG tắt.
- Guard `isDebugEnabled()` rồi mới serialize.
- SLF4J 2.x fluent supplier/lazy argument.
- Truyền object/structured key-value với dữ liệu bất biến.
- JSON encoder đang dùng trong production.

Điều quan trọng: benchmark phải **tiêu thụ kết quả** (hoặc dùng cơ chế JMH phù hợp) để JVM không loại phép tính vì không có tác dụng; chuẩn bị dữ liệu đại diện cho kích thước/thành phần thực tế; tách chi phí serialize khỏi logging I/O khi mục tiêu là CPU/allocations.

Theo dõi:
- Thời gian mỗi lần serialize và throughput.
- Allocated bytes trên event, tần suất GC và thời gian pause.
- CPU profiles (ví dụ Java Flight Recorder) để nhận diện điểm nóng `toString`, formatter, JSON encoder, escaping, buffer copy.

### 9.2. Kiểm thử end-to-end dưới tải thực

Đặt ứng dụng với cùng backend, appender, queue, encoder, level và mức tải tương tự production. So sánh các cấu hình trên cùng input/kịch bản:

| Chỉ số | Điều cần trả lời |
| --- | --- |
| Throughput nghiệp vụ | Số request/job hoàn tất thay đổi như thế nào? |
| Latency p50/p95/p99 | Logging có làm chậm các request ở đuôi phân phối không? |
| CPU / memory / GC | Serialization hoặc allocation có chiếm đáng kể tài nguyên không? |
| Event accepted / emitted / dropped | Tối ưu có làm mất log để đổi lấy hiệu năng không? |
| Queue depth / enqueue blocking | Worker encoding có theo kịp producer không? |
| Bytes xuất ra | Có đang serialize object quá lớn/ghi field không cần thiết không? |
| Thời gian shutdown/flush | Event cuối có được xuất trong deadline không? |

Để tránh kết luận sai: ghi log ra appender không làm gì (no-op) cho biết phần overhead của API/event, nhưng không đại diện cho production. Ghi ra console terminal hoặc disk khác môi trường thật cũng có thể làm benchmark lệch. Hãy đo cả phần tách biệt lẫn toàn pipeline, và so sánh tỷ lệ event thực sự được giữ lại.

### 9.3. Một bài toán ước lượng đơn giản

Nếu một log event serialize object lớn và được tạo lặp lại ở đường nóng, tổng lượng công việc tăng theo **số event × chi phí trên mỗi event**. Khi phần lớn log đó đang bị tắt vì level, bỏ eager serialization có thể giảm đáng kể CPU và allocation. Khi log được bật và yêu cầu giữ toàn bộ, việc chuyển sang async chủ yếu phân phối lại công việc; khi đó giảm kích thước dữ liệu hoặc chọn encoder hiệu quả hơn mới tác động trực tiếp đến số bytes và CPU cần xử lý.

## 10. Các mẫu thực hành tốt

### Mẫu A — Chỉ log thông tin cần thiết

```java
// Mã tích hợp dùng SLF4J và object nghiệp vụ tương ứng.
logger.info("Payment completed paymentId={} status={} durationMs={}",
        payment.id(), payment.status(), durationMs);
```

Các primitive/giá trị nhỏ có chi phí serialization thấp hơn việc serialize toàn bộ payment entity, đồng thời giảm nguy cơ rò rỉ thông tin thẻ hay PII. Nhưng nếu accessor gọi database, giá trị ấy vẫn có thể đắt: kiểm tra cách implementation cung cấp dữ liệu.

### Mẫu B — Guard khi tính toán tốn kém và log có thể bị tắt

```java
// Mã tích hợp; giả định buildDiagnosticDump() là hàm tốn kém.
if (logger.isDebugEnabled()) {
    logger.debug("Diagnostics: {}", buildDiagnosticDump());
}
```

Khi filter ở appender có thể loại event sau bước này, guard theo logger level chưa tránh được mọi chi phí. Nếu chính sách loại đòi hỏi tránh tạo event hoàn toàn, cân nhắc logger/context filter sớm theo backend.

### Mẫu C — Lazy supplier khi API hỗ trợ

```java
// Mã tích hợp cho SLF4J 2.x.
logger.atTrace()
      .addArgument(() -> expensiveDiagnosticSnapshot())
      .log("Snapshot {}");
```

Đảm bảo supplier thuần, không có side effect nghiệp vụ, không phụ thuộc đối tượng có thể bị sửa bất ngờ, và có quyền truy cập dữ liệu hợp lý ở thời điểm supplier được đánh giá.

### Mẫu D — Structured fields, không lồng JSON trong message

```java
// Mã tích hợp cho SLF4J 2.x với backend xuất key-value.
logger.atInfo()
      .addKeyValue("invoice_id", invoiceId)
      .addKeyValue("result", result)
      .log("Invoice processed");
```

Khi các field là scalar/bất biến, structured encoder có thể xuất trực tiếp các trường cần truy vấn. Đảm bảo backend thực sự hỗ trợ key-value output và tên field ổn định; chỉ thêm field hữu ích, tránh object graph lớn.

### Mẫu E — Phân tầng mức log và kích thước payload

Log INFO có thể chứa ID, trạng thái và thời gian; log DEBUG có thể có thêm metadata chi tiết khi cần chẩn đoán. Hạn chế dùng TRACE/DEBUG cho payload nhạy cảm hoặc kích thước cực lớn theo mặc định. Lọc theo level và sampling là các công cụ phù hợp với mục tiêu quan sát, nhưng phải giữ các log lỗi/audit cần thiết theo chính sách của hệ thống.

## 11. Các lỗi phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| `logger.debug("x="+toJson(obj))` khi DEBUG tắt | Vẫn trả chi phí tạo JSON/chuỗi | Guard hoặc dùng supplier lazy |
| `logger.debug("x={}", toJson(obj))` | Placeholder không làm `toJson` lazy | Truyền object đơn giản, guard hoặc supplier |
| Log toàn bộ entity/request body | CPU/allocations lớn, log dài, dữ liệu nhạy cảm | Chọn field cần quan sát và giới hạn payload |
| Dùng `toString()` có I/O/lazy loading | Logging làm phát sinh truy vấn/khóa bất ngờ | Giữ `toString()` nhẹ, tránh tải graph lớn |
| Log cùng một exception ở nhiều tầng | Format stack trace và bytes lặp lại | Ghi ở tầng chịu trách nhiệm xử lý, giữ context hợp lý |
| Tự tạo JSON rồi JSON encoder escape thêm | Double serialization, khó truy vấn | Dùng structured fields/encoder một lần |
| Giả định async là “miễn phí” | Queue backlog, GC/CPU nền, mất event khi drop | Đo tổng pipeline và số event emitted/dropped |
| Truyền object mutable vào async event | Giá trị log có thể phản ánh thời điểm khác | Snapshot dữ liệu cần thiết theo contract backend |
| Chỉ đo thời gian enqueue | Che giấu chi phí encoder/flush | Đo CPU, allocation, queue, bytes và shutdown |
| Bật DEBUG diện rộng để “kiểm thử” | Phát sinh chi phí và rủi ro dữ liệu | Dùng môi trường kiểm thử, thời hạn và logger chọn lọc |
| Dựa vào log level để bảo vệ thông tin nhạy cảm | Thay đổi level có thể làm lộ dữ liệu | Redact/không tạo dữ liệu nhạy cảm ở mọi level |
| “Tối ưu” bằng cách bỏ log lỗi quan trọng | Giảm khả năng chẩn đoán và kiểm toán | Giữ log cần thiết; tối ưu field/encoder và chính sách |

## 12. Bài tập tự kiểm tra

**Câu 1.** Với SLF4J, DEBUG đang tắt:

```java
logger.debug("payload={}", toJson(order));
```

Hàm `toJson(order)` có chạy không? **Có.** Java đánh giá đối số trước khi gọi phương thức. Dấu `{}` chỉ là placeholder để backend format message.

**Câu 2.** Dùng JUL với level INFO:

```java
logger.log(Level.FINE, () -> expensiveDiagnostic());
```

Nếu `logger.isLoggable(Level.FINE)` là false, supplier có cần chạy không? **Không**, với overload `Logger.log(Level, Supplier<String>)`, thông điệp lazy không cần được tạo khi level bị tắt.

**Câu 3.** Đổi sang async logger có chắc giảm tổng CPU serialize JSON không? **Không.** Công việc có thể chuyển thread, có thêm overhead queue/snapshot và vẫn phải encode những event được giữ. Cần đo tổng tài nguyên và số log thực xuất.

**Câu 4.** Khi root INFO nhưng một appender chặn INFO, guard `logger.isInfoEnabled()` có chắc ngăn chi phí serialization không? **Không.** Logger có thể chấp nhận INFO nhưng appender filter loại event về sau. Cần hiểu nơi đặt filter.

**Câu 5.** Khi cần biết đơn hàng nào hoàn tất, nên log toàn bộ object `Order` hay `orderId`, `status` và `durationMs`? Thông thường chọn **những field nhỏ, cụ thể** để giảm CPU/bytes và nguy cơ lộ dữ liệu; chỉ bổ sung thông tin khác khi thật sự cần.

## 13. Checklist áp dụng trong dự án

Trước khi tối ưu chi phí serialization của logging Java, hãy xác nhận:

1. **Mức log thực tế:** logger, level kế thừa, filter và backend đang chạy.
2. **Vị trí serialize:** call site, khi tạo event, lúc enqueue hay tại encoder/appender.
3. **API đang dùng:** SLF4J 1.x/2.x, JUL, Log4j API hoặc các structured logging adapter; supplier/lazy semantics chính xác.
4. **Dữ liệu tạo log:** field nào tốn kém, payload có quá lớn, `toString` có side effect hoặc truy vấn không.
5. **Async safety:** object snapshot, queue, overflow, dropped events, flush/shutdown.
6. **Phương pháp đo:** benchmark có warm-up/tiêu thụ kết quả, đo CPU, allocated bytes, GC, p95/p99 và số event được ghi thật.
7. **Bảo mật:** không serialize token/PII/secret; kiểm tra cơ chế redact và quyền truy cập log.
8. **Độ hữu ích:** vẫn giữ thông tin cần truy vết, xử lý lỗi và kiểm toán.

Serialization cost trong logging là phần chi phí **tạo biểu diễn dữ liệu cho một sự kiện quan sát**. Tối ưu hiệu quả bắt đầu từ việc không tạo dữ liệu khi log đã tắt, giảm lượng dữ liệu không cần thiết khi log được bật, đặt filter đúng vị trí và đo toàn pipeline để thấy rõ tác động lên hiệu năng ứng dụng.