# Chi phí stack trace trong Java logging

## 1. Stack trace là gì và vì sao có chi phí?

**Stack trace** là danh sách các frame mô tả chuỗi lời gọi phương thức tại một thời điểm. Frame thường chứa tên class, tên phương thức, tên tệp và số dòng nguồn khi thông tin đó có sẵn. Trong ứng dụng Java, stack trace có hai mục đích logging khác nhau:

1. **Stack trace của `Throwable`:** cho biết nơi exception/`Error` được tạo và các lời gọi dẫn đến vị trí đó. Ví dụ `logger.error("Save failed", exception)`.
2. **Vị trí gọi logger (caller location):** dùng khi pattern log yêu cầu tên class, method, file hoặc dòng của chính lời gọi logging, chẳng hạn `%class`, `%method`, `%file`, `%line`, `%caller` trong Logback.

Hai loại dữ liệu này liên quan đến call stack, nhưng **được thu thập ở thời điểm và mục đích khác nhau**. Stack trace của exception đã tồn tại thường không phải được tạo từ đầu mỗi lần nó được ghi log. Ngược lại, tính vị trí lời gọi logger có thể cần đi qua stack ngay cả khi sự kiện không mang exception.

Một ví dụ thường thấy:

```text
ERROR OrderService - Failed to save order
java.io.IOException: Connection reset
    at example.Storage.save(Storage.java:42)
    at example.OrderService.submit(OrderService.java:18)
    ...
```

Đoạn trên là hình thức **minh họa**, không phải output cố định của một chương trình cụ thể. Số frame, tên tệp và dòng thay đổi theo mã, JDK và môi trường chạy.

Chi phí cần đánh giá không chỉ là “gọi `printStackTrace` có chậm không?”. Một sự kiện log có exception có thể phải: tạo/capture trace, materialize frame, format thông điệp và exception chain, tạo/đẩy event qua queue, encode thành văn bản/JSON, rồi ghi ra console, file hoặc mạng. **Mỗi giai đoạn có chi phí riêng**; một tối ưu ở tầng này không tự loại bỏ chi phí ở tầng khác.

## 2. Stack trace của `Throwable` được tạo lúc nào?

Với `Throwable` thông thường trong Java, constructor gọi cơ chế `fillInStackTrace()` để ghi nhận ngăn xếp tại **thời điểm tạo đối tượng**. Điều này quan trọng hơn nhiều người nghĩ:

```java
Exception error = new Exception("diagnostic"); // Thu stack tại đây.
logger.debug("Diagnostic only", error);         // Có thể bị lọc DEBUG.
```

Nếu `DEBUG` đang tắt, dòng `logger.debug(...)` có thể không phát event; **nhưng `new Exception(...)` vẫn đã chạy**, vì nó là câu lệnh độc lập trước lời gọi logger.

Tình huống này cũng xảy ra khi tạo exception ngay trong biểu thức tham số:

```java
logger.debug("Current call stack", new Exception("trace"));
```

Java đánh giá các argument trước khi gọi `debug`. Logger không thể quay ngược thời gian để ngăn `new Exception` được thực thi. Cơ chế lọc level chỉ có thể tránh những việc xảy ra **bên trong** lời gọi logging sau đó.

Một số đặc điểm quan trọng:

- `throw` một exception đã tồn tại **không tự làm mới** stack trace theo nơi throw lại. Muốn thay đổi trace phải có thao tác riêng, chẳng hạn `fillInStackTrace()`, vốn tự nó có chi phí và có thể làm mất ngữ cảnh gốc.
- `getStackTrace()` tạo dạng mảng `StackTraceElement[]` cho việc xem frame; việc hiện thực hóa và sao chép thông tin này có thể cấp phát thêm đối tượng.
- `printStackTrace()` phải chuyển exception, stack frame, `cause` và `suppressed exception` thành dạng dễ đọc rồi ghi qua `PrintStream` hoặc `PrintWriter`. Nó không chỉ là đọc một chuỗi có sẵn.
- Một số implementation/JVM có kỹ thuật trì hoãn materialize chi tiết frame, nhưng **không được suy luận rằng `new Exception()` là miễn phí**.
- `Throwable` có constructor được bảo vệ để vô hiệu hóa writable stack trace; đây là lựa chọn thiết kế đặc biệt cho một số loại exception, **không phải một tối ưu mặc định** cho lỗi cần chẩn đoán.

### Stack trace được ghi theo nơi tạo, không phải vị trí log

```java
IllegalStateException failure =
        new IllegalStateException("Bad state");

// Một số xử lý khác...

logger.error("Operation failed", failure);
```

Những frame trong `failure` gắn với nơi khởi tạo exception. Việc chuyển đối tượng này qua phương thức khác rồi mới log không biến stack của nó thành stack tại `logger.error`. Nếu cần thông tin nơi log, đó là **caller location**, có cơ chế thu thập riêng.

## 3. Bảng phân rã chi phí

| Thành phần | Khi nào phát sinh | Dấu hiệu/ảnh hưởng |
| --- | --- | --- |
| `new Throwable/Exception` thông thường | Khi tạo exception, kể cả log bị tắt nếu đã tạo ngoài guard | Đi qua stack, cấp phát, áp lực GC |
| `fillInStackTrace()` | Khi exception thông thường được xây dựng hoặc gọi tường minh | Chụp/ghi nhận call stack hiện tại |
| `getStackTrace()` | Khi code muốn đọc từng frame | Materialize/copy thông tin frame, thêm cấp phát |
| `printStackTrace()` hoặc formatter | Khi render thông tin lỗi ra text/JSON | Duyệt frame, xử lý cause/suppressed, tạo nhiều ký tự |
| Thông tin caller của event | Khi pattern/API yêu cầu file, line, method hoặc caller | Stack walking để xác định vị trí gọi logger |
| Ghi file, console, network | Khi appender/sink xuất event | I/O, encoding, lock, network, dung lượng lưu trữ |
| Queue của async appender | Khi tách producer khỏi sink | Memory, queue coordination, backpressure/drop khi quá tải |
| Tạo message đắt tiền | Khi code tự nối chuỗi, serialize object hoặc gọi hàm làm việc nặng | Vẫn tốn ngay cả khi logger bỏ event nếu biểu thức đã được đánh giá |

Không có tỷ lệ chi phí cố định đúng cho mọi hệ thống. Một exception ngắn ghi vào sink trong bộ nhớ có profile khác với exception có hàng trăm frame, nhiều `cause`, và output qua console hoặc mạng. Cần đo trong đúng tải và đúng backend.

### Độ sâu stack và tần suất lỗi

Trace càng dài có thể cần nhiều công việc hơn để chụp, chuyển đổi và in. Một lỗi đơn lẻ thường không gây vấn đề. **Lỗi lặp trong vòng lặp nóng** mới đáng lo: hàng nghìn exception/giây có thể kéo theo cấp phát, CPU format, GC và lượng bytes log tăng mạnh.

Ví dụ ba tầng bọc lỗi:

```text
ServiceException
  caused by RepositoryException
    caused by IOException
```

Khi format, backend còn có thể in chuỗi cause và suppressed exceptions. Ghi lại **toàn bộ stack trace tại mỗi tầng** làm tăng dữ liệu lặp: ứng dụng có thể log cùng nguyên nhân ba lần dù chỉ có một thất bại nghiệp vụ. Ưu tiên ghi thông tin nghiệp vụ ngắn gọn tại những tầng trung gian và log exception đầy đủ ở ranh giới xử lý thích hợp.

## 4. Ví dụ Java 17 chạy độc lập: log bị tắt vẫn tốn chi phí tạo exception

Ví dụ sau dùng `java.util.logging` (JUL), có sẵn trong JDK. Nó **đếm số lần code tạo exception hoặc xây message**, không giả vờ đo nanosecond chính xác. Logger được đặt `OFF` nên mọi lời gọi mức `FINE` đều bị lọc.

Tạo tệp `StackTraceCostDemo.java`:

```java
import java.util.logging.Level;
import java.util.logging.Logger;

public class StackTraceCostDemo {
    private static int exceptionsCreated;
    private static int messagesBuilt;

    private static Exception diagnosticException() {
        exceptionsCreated++;
        return new Exception("diagnostic stack");
    }

    private static String expensiveMessage() {
        messagesBuilt++;
        return "details computed";
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("example.stack.cost");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.OFF);

        // Argument được đánh giá trước khi logger.log(...) được gọi.
        logger.log(Level.FINE, "Hidden diagnostic", diagnosticException());
        System.out.println("Eager exceptions: " + exceptionsCreated);

        // Chỉ tạo exception nếu mức log đang được bật.
        if (logger.isLoggable(Level.FINE)) {
            logger.log(Level.FINE, "Guarded diagnostic",
                    diagnosticException());
        }
        System.out.println("Guarded exceptions: " + exceptionsCreated);

        // Supplier<String> chỉ được gọi nếu logger quyết định ghi.
        logger.log(Level.FINE, () -> expensiveMessage());
        System.out.println("Supplier messages: " + messagesBuilt);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac StackTraceCostDemo.java
java StackTraceCostDemo
```

**Stdout chính xác:**

```text
Eager exceptions: 1
Guarded exceptions: 1
Supplier messages: 0
```

Giải thích:

1. `diagnosticException()` chạy trong biểu thức argument của lời gọi đầu, tăng `exceptionsCreated` và khởi tạo `Exception` (thông thường sẽ capture stack). Logger sau đó bỏ event vì `Level.OFF`.
2. `isLoggable(Level.FINE)` trả `false`, vì vậy nhánh có `diagnosticException()` thứ hai không chạy.
3. Quá tải `Logger.log(Level, Supplier<String>)` của JUL không cần gọi supplier khi level bị tắt; `messagesBuilt` giữ nguyên `0`.
4. Để stdout ổn định, ví dụ chỉ in ba biến đếm, không in stack trace hay đo thời gian phụ thuộc máy.

**Chú ý:** biến đếm là bằng chứng **việc tạo đối tượng/hàm có chạy hay không**, không phản ánh số frame, số byte phân bổ hay thời gian thực. Cần profiler/JMH để đo chi phí hiệu năng.

### Vì sao không chỉ dùng `new Exception` ở mọi dòng debug?

`new Exception("where am I")` là một cách lấy vị trí call stack, nhưng nếu dùng ở nhiều sự kiện debug hoặc trong vòng lặp thì giá phải trả xảy ra lúc tạo đối tượng. Nếu mục tiêu chỉ là log vài trường nghiệp vụ, không cần dựng `Throwable`. Nếu cần caller location, nên dùng cơ chế caller/location được backend hỗ trợ và chỉ bật ở profile có nhu cầu.

## 5. Logging đúng cách với SLF4J

Trong nhiều ứng dụng Java, code gọi API SLF4J còn Logback hoặc Log4j2 xử lý ở backend.

### 5.1. Dùng parameterized logging

```java
logger.debug("Order {} status {}", orderId, status);
```

Phần `{}` cho phép backend tránh phần lớn việc format message khi `DEBUG` bị tắt. Tuy nhiên, **Java vẫn đánh giá các biểu thức argument trước khi gọi phương thức**. Nếu `orderId` và `status` là dữ liệu có sẵn thì chi phí thường nhỏ. Nếu đối số cần serialize, tính toán hoặc truy vấn phức tạp, nó vẫn chạy:

```java
// expensiveReport(order) chạy ngay cả khi DEBUG đang tắt.
logger.debug("Report: {}", expensiveReport(order));
```

Khi đó nên guard:

```java
if (logger.isDebugEnabled()) {
    logger.debug("Report: {}", expensiveReport(order));
}
```

Các đoạn trên **minh họa code trong ứng dụng có sẵn biến, logger và phương thức**, không phải file Java độc lập. Với SLF4J 2.x, fluent API `logger.atDebug().addArgument(() -> expensiveReport(order)).log("Report: {}");` cũng có thể hỗ trợ argument tính lười thông qua supplier, nếu dùng đúng phiên bản và đường gọi API. Không truyền `expensiveReport(order)` như một giá trị đã tính trước rồi gọi nó là lazy.

### 5.2. Khi thực sự có exception, giữ nguyên đối tượng lỗi

```java
try {
    operation.run();
} catch (Exception failure) {
    logger.error("Order operation failed, orderId={}", orderId, failure);
    throw failure;
}
```

Đây là **đoạn minh họa** trong phương thức có `operation` và `orderId` phù hợp; không thể biên dịch độc lập. Với SLF4J/Logback thông thường, `Throwable` ở vị trí cuối được ghi nhận là nguyên nhân để appender hiển thị stack trace, thay vì chỉ gọi `failure.toString()`.

Tránh:

```java
logger.error("Order operation failed: " + failure.getStackTrace());
```

`Throwable.getStackTrace()` trả về mảng frame; nối thẳng mảng vào String thường không cho nội dung trace hữu ích, lại chủ động materialize/cấp phát trước khi logger xét level. Nếu chỉ cần thông điệp ngắn, chọn `failure.getMessage()` và một vài trường an toàn; nếu cần stack, truyền chính `Throwable` để backend định dạng nhất quán.

### 5.3. Chỉ tạo diagnostic trace khi có nhu cầu

```java
if (logger.isDebugEnabled()) {
    logger.debug("Diagnostic stack for operationId={}",
            operationId, new Throwable("diagnostic only"));
}
```

Nhờ điều kiện, không tạo `Throwable` khi `DEBUG` bị tắt. Tuy nhiên, cách này vẫn tạo một stack trace mới mỗi khi log `DEBUG` được bật; chỉ dùng ở điểm điều tra hữu ích. Chọn cơ chế caller/location theo cấu hình nếu cần kiểm tra liên tục nguồn phát log.

Đừng nhầm **ghi lại một exception thật** với **chủ động tạo exception giả để lấy stack**: exception thật đã được tạo như một phần của đường đi lỗi; exception giả có chi phí chỉ để quan sát.

## 6. Chi phí của caller location trong pattern logging

Nhiều pattern chỉ cần thời gian, mức log, tên logger, thread và message:

```text
%d{HH:mm:ss.SSS} %-5level [%thread] %logger{36} - %msg%n
```

Một số pattern Logback yêu cầu thêm vị trí gọi:

```text
%class.%method(%file:%line) - %msg%n
```

Để lấy `%class`, `%method`, `%file`, `%line` hoặc `%caller`, backend có thể phải tìm **frame đúng của caller** trong call stack. Đây là công việc bổ sung, ngay cả khi message không chứa exception.

**`%logger` không giống `%class`:** tên logger có thể đã biết từ đối tượng logger; tên class tại vị trí gọi cần suy ra từ stack, trừ khi backend có cơ chế cung cấp location riêng. Nếu chỉ cần biết thành phần logic, tên logger/package đã đủ cho nhiều trường hợp.

| Trường | Vai trò | Lưu ý chi phí |
| --- | --- | --- |
| `%logger` | Tên logger đã được ứng dụng chọn | Thường rẻ hơn việc truy stack để lấy caller |
| `%thread` | Tên thread nguồn theo event | Hữu ích cho debug concurrency nhưng không định danh request |
| `%X{requestId}` | Correlation ID từ MDC | Không đồng nghĩa stack walk; cần context được đặt/lan truyền đúng |
| `%class`/`%method`/`%line` | Vị trí code gọi logger | Có thể đắt vì xác định caller stack |
| Stack trace của `Throwable` | Nơi tạo exception và chuỗi lỗi | Chi phí capture/format đặc thù, không thay cho caller location |

Trong hệ thống có lưu log thường xuyên, hãy ưu tiên trường có giá trị truy vấn thực tế. Chỉ bật caller location ở những logger/profile cần thiết khi lợi ích chẩn đoán bù được chi phí.

### Khi kết hợp với async logging

Với Logback `AsyncAppender`, thread nghiệp vụ enqueue event và worker thread xử lý ở phía sau. Một điểm dễ bỏ sót:

- Muốn biết **vị trí gọi logger của thread nghiệp vụ**, backend phải thu thập caller data khi còn ở ngữ cảnh thread nguồn. Sau khi event được chuyển qua worker, stack của worker **không phải** stack nguồn.
- Logback `AsyncAppender` có tùy chọn `includeCallerData`. Khi bật, nó chuẩn bị caller data ở phía producer để event async vẫn hiển thị vị trí gọi phù hợp. Đây là lựa chọn có chi phí đồng bộ ở thread nghiệp vụ.
- Nếu không cần file/line/method, không nên bật `includeCallerData` chỉ vì mọi log đi qua async appender.
- Việc ghi một exception thật vẫn cần xử lý thông tin `Throwable` đã được tạo/capture trước đó. Đẩy sự kiện vào queue không xóa chi phí mà ứng dụng đã chịu để tạo exception.

Đối với Log4j2 AsyncLogger hoặc AsyncAppender, khái niệm caller location cũng có thể tốn chi phí và cần cấu hình theo API/phiên bản cụ thể. **Không sao chép tên option của Logback sang Log4j2** nếu chưa kiểm tra backend được dùng.

Async logging giúp thread nghiệp vụ không nhất thiết chờ toàn bộ I/O của sink ở mỗi sự kiện, nhưng **không miễn phí**: queue cần bộ nhớ, có ngưỡng backpressure/discard, và việc chuẩn bị message/context/caller data trên producer vẫn tiêu tốn thời gian.

## 7. Log nhiều stack trace liên tiếp: điều gì xảy ra?

Giả sử hệ thống gặp lỗi timeout 10.000 lần trong một khoảng ngắn. Nếu mỗi lần:

1. tạo một exception mới,
2. lưu stack trace dài,
3. format message cùng nhiều frame,
4. đẩy hàng kilobyte dữ liệu qua file/collector,

thì ngoài chi phí xử lý timeout, hệ thống còn chịu thêm CPU, cấp phát và I/O của logging. Trong giai đoạn sự cố, log quá mức có thể làm hệ thống chậm hơn và tăng queue backlog, dẫn đến mất log tùy chính sách.

### Quy tắc tránh lặp trace mà vẫn đủ thông tin

- Ghi stack trace đầy đủ tại **ranh giới xử lý lỗi** có đủ ngữ cảnh, chẳng hạn lớp xử lý request/job cuối cùng.
- Ở lớp thấp hơn, có thể ném lại exception hoặc bọc thêm ngữ nghĩa bằng `cause` khi cần, thay vì log cùng stack ở từng layer.
- Nếu log ở lớp trung gian cần thiết để chẩn đoán một hành động khôi phục, dùng message ngắn và context thích hợp; đừng tự động in stack đầy đủ nhiều lần.
- Giữ mã nhận diện request/trace và loại lỗi nhất quán để nhóm các sự kiện có cùng nguyên nhân.
- Với lỗi lặp, cân nhắc rate limit, sampling hoặc tổng hợp số lượng theo khoảng thời gian **nếu đáp ứng yêu cầu vận hành và kiểm toán**. Không tự ý bỏ lỗi nghiêm trọng cần lưu đầy đủ.
- Nếu sink có quota, hiểu rõ chính sách drop trước khi quyết định làm nhẹ event; mất toàn bộ dấu vết lỗi khác với giảm bớt phần stack dư thừa.

Ví dụ cách log tránh nhân bản tại mỗi tầng:

```java
// Tầng repository: đưa lỗi lên, giữ cause.
throw new RepositoryException("Cannot save record", originalFailure);

// Tầng xử lý request/job: ghi một lần với correlation ID.
logger.error("Request failed, requestId={}", requestId, failure);
```

Đây là **mẫu minh họa**, giả định có class `RepositoryException` và biến được khai báo. Việc tạo `RepositoryException` mới vẫn có chi phí capture stack; chỉ bọc exception khi thật sự bổ sung ý nghĩa/contract, không bọc nhiều tầng chỉ để đổi vài chữ trong message.

## 8. Khi nào nên dùng stackless exception?

`Throwable` có protected constructor cho phép tắt suppression và writable stack trace. Ví dụ:

```java
public final class LightweightSignal extends RuntimeException {
    public LightweightSignal(String message) {
        super(message, null, false, false);
    }
}
```

Đây là **class Java độc lập có thể biên dịch nếu lưu trong `LightweightSignal.java`**. Tham số `writableStackTrace=false` khiến thông tin stack trace thường rỗng và tránh chi phí ghi stack theo cơ chế này. Đổi lại, khi sự cố xảy ra, ta không còn biết chuỗi vị trí tạo/throw dựa vào exception ấy. `enableSuppression=false` cũng tắt cơ chế ghi suppressed exceptions.

Cách này chỉ phù hợp với **tín hiệu đặc biệt được thiết kế trước, có đường xử lý rõ ràng và không cần stack để điều tra**. Nó không phải lựa chọn mặc định cho lỗi ứng dụng, I/O, database, hay điều kiện bất thường cần chẩn đoán. Không biến mọi exception thành stackless chỉ để làm đẹp benchmark; lợi ích vi mô có thể phải trả bằng thời gian tìm lỗi lớn hơn nhiều.

Một lựa chọn thiết kế còn tốt hơn khi không thật sự có lỗi là tránh dùng exception làm luồng điều khiển thông thường: trả về một kết quả có kiểu rõ ràng, kiểm tra điều kiện trước, hoặc dùng cấu trúc dữ liệu biểu đạt tình trạng mong đợi.

## 9. Đo chi phí như thế nào?

Đừng dùng một con số nanosecond truyền miệng để tối ưu mọi hệ thống. Hiệu năng chịu ảnh hưởng bởi độ sâu call stack, phiên bản JDK, JIT, CPU, GC, log level, backend, pattern, appender, encoder và tải thực tế.

### 9.1. Chia các phép đo riêng

| Kịch bản | Đối tượng muốn đo | Không gộp vào |
| --- | --- | --- |
| `new Exception(...)` | Chi phí tạo/capture Throwable | I/O console, render full trace |
| `exception.getStackTrace()` | Chi phí materialize/copy frame | Ghi file/mạng |
| `exception.printStackTrace(PrintWriter)` | Chi phí render trace và causes vào writer | Đồng bộ/flush sink production nếu dùng StringWriter |
| Logger tắt với argument đã có | Đường đi filtered logging thông thường | Tạo argument đắt tiền bên ngoài |
| Logger tắt với `new Throwable(...)` trực tiếp | Chi phí argument eager + filtered call | Chi phí lúc backend thật sự ghi |
| Caller location bật/tắt | Phụ phí lấy class/method/line cho event | Chi phí Throwable nếu không có exception |
| Sync/async appender cùng payload | Producer latency, throughput, queue, drain | Kết luận “async không mất log” nếu chưa kiểm tra discard |

Đo đủ **p50, p95, p99** về latency, throughput, allocation rate và GC; nếu có collector thực tế, đo số bytes/s và thời gian ingest. Giữ payload/số lượng exception/độ sâu stack giống nhau để so sánh.

### 9.2. Mẫu benchmark JMH

JMH giúp tránh nhiều sai lệch từ warm-up/JIT/Dead Code Elimination. Mẫu sau là **lớp benchmark**, không phải chương trình Java độc lập chỉ cần `javac`: để chạy cần dự án có dependencies và annotation processor JMH được cấu hình đúng.

```java
package example;

import java.io.PrintWriter;
import java.io.StringWriter;
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 3)
@Measurement(iterations = 5)
@Fork(2)
public class StackTraceBenchmark {
    @Benchmark
    public Exception captureOnly() {
        return new Exception("sample");
    }

    @Benchmark
    public StackTraceElement[] captureAndReadFrames() {
        return new Exception("sample").getStackTrace();
    }

    @Benchmark
    public String captureAndFormatInMemory() {
        Exception e = new Exception("sample");
        StringWriter buffer = new StringWriter();
        PrintWriter out = new PrintWriter(buffer);
        e.printStackTrace(out);
        out.flush();
        return buffer.toString();
    }
}
```

Các benchmark này lần lượt bao gồm thêm công việc (capture → capture + đọc frame → capture + format text); **không phải ba phép đo độc lập có thể lấy hiệu hai con số để suy ra chính xác chi phí của từng API**. Kết quả định lượng phụ thuộc vào độ sâu stack, bộ nhớ và JVM; bản thân `StringWriter` chưa phản ánh chi phí filesystem hay network.

Để chạy, dùng phiên bản `jmh-core` và `jmh-generator-annprocess` tương thích, bảo đảm annotation processor đã tạo metadata `META-INF/BenchmarkList`, sau đó chạy `org.openjdk.jmh.Main` qua classpath/JAR do dự án build ra. Tham khảo kết quả JMH thực tế và thông số environment, không công bố con số của một lần chạy đơn lẻ như bảo đảm chung.

### 9.3. Đo trong ứng dụng thực

Khi đã có số liệu microbenchmark, cần tiếp tục:

1. Profile CPU (Java Flight Recorder/JFR hoặc profiler phù hợp) để thấy thời gian ở `Throwable.fillInStackTrace`, stack walking, formatting, encoder và appender.
2. Profile allocations/GC: số lượng `Throwable`, `StackTraceElement`, `String`, buffer và event log.
3. So sánh khi cùng traffic/error rate, cùng log level và sink; tránh so môi trường dev ghi console với prod gửi collector khác.
4. Theo dõi queue async, drop count, thời gian chờ producer và thời gian drain khi shutdown nếu có.
5. Đảm bảo thử nghiệm không tiết lộ dữ liệu production và không tạo tác động tải không kiểm soát.

**Không đặt assertion kiểu `assertTrue(elapsedNanos < 1000)` trong JUnit chức năng**. Tốc độ JVM, scheduler, GC và máy CI thay đổi; dùng JMH cho so sánh định lượng, còn JUnit kiểm tra hành vi đúng/sai.

## 10. Kiểm thử để tránh tối ưu làm mất thông tin lỗi

Tối ưu stack trace cần bảo vệ hợp đồng chẩn đoán. Một bộ test nên kiểm chứng:

- **Khi level bị tắt:** hàm dựng diagnostic exception đắt tiền được bảo vệ bằng `isDebugEnabled` hoặc supplier phù hợp nên không chạy; có thể kiểm tra bằng counter như `StackTraceCostDemo`.
- **Khi lỗi thật được log:** appender nhận đúng `Throwable`, `cause` và thông điệp; không chỉ nhận `exception.toString()` nếu yêu cầu có stack.
- **Khi chuyển qua async appender:** log đã được worker tiêu thụ trước khi assert; dùng sink test có `BlockingQueue`/latch và timeout, tránh `Thread.sleep`.
- **Khi bật caller location:** tên class/file/line đến từ thread nguồn theo contract của backend; test cụ thể có thể kiểm tra class, không cố định số dòng nếu code thay đổi.
- **Khi rate limit/sampling:** kết quả khớp chính sách đã thỏa thuận; không loại mất những event thuộc nhóm bắt buộc.
- **Khi log lỗi lặp:** ứng dụng không tự tạo lại nhiều stack trace giả ở những nhánh code nóng; event còn đủ ID để tương quan.
- **Khi format exception chain:** có thể thấy nguyên nhân chính và các cause quan trọng; không làm mất thông tin cần điều tra chỉ vì rút gọn trace.
- **Khi bảo vệ dữ liệu:** đường dẫn, thông điệp exception, request context và suppressed exception không vô tình chứa token hoặc dữ liệu riêng tư.

Với test chụp log, hãy gắn appender riêng vào logger có tên xác định, gỡ appender và khôi phục level/MDC trong `finally`. Test có shared logger/backend không nên thay root configuration song song nếu chưa cô lập được.

## 11. Sai lầm phổ biến khi đánh giá chi phí stack trace

| Hiểu nhầm | Thực tế | Cách xử lý |
| --- | --- | --- |
| “Log DEBUG tắt thì `new Exception` trong argument miễn phí” | Java vẫn đánh giá argument | Guard trước khi dựng trace giả |
| “`throw e` làm mới stack tại điểm rethrow” | Trace của exception thường gắn với lúc tạo | Giữ nguyên cause, log ngữ cảnh phù hợp |
| “Có `%logger` là đã có số dòng caller” | Logger name và caller location là dữ liệu khác nhau | Chỉ bật file/line khi cần |
| “Async logging loại bỏ hết chi phí stack trace” | Capture/chuẩn bị event có thể vẫn ở producer | Đo producer latency, queue và sink riêng |
| “`printStackTrace` chỉ lấy một String có sẵn” | Phải format frames, cause/suppressed và ghi writer | Đo riêng capture, format, I/O |
| “Bọc lỗi mỗi tầng giúp nhiều thông tin miễn phí” | Tạo exception mới và log lặp làm tăng cost | Chỉ bọc khi có contract/ngữ cảnh mới; log đầy đủ tại boundary |
| “Stackless exception lúc nào cũng tốt hơn” | Mất thông tin chẩn đoán | Dùng có chủ đích cho tín hiệu đã thiết kế |
| “Một benchmark local là số nanosecond chuẩn” | JIT, CPU, stack depth, GC, backend khác nhau | JMH nhiều lần + profile workload thực |
| “Chỉ cần tắt TRACE/DEBUG là không còn log nhạy cảm” | `INFO/ERROR` và exception message cũng có thể lộ dữ liệu | Kiểm tra nội dung và redaction tại sink |
| “Log stack càng dài thì sự cố càng dễ điều tra” | Dữ liệu lặp có thể che tín hiệu chính, tăng chi phí và phí lưu | Dùng correlation ID, phân cấp lỗi, giữ cause có chọn lọc |

### Cân bằng giữa hiệu năng và khả năng điều tra

Khi cần tối ưu, ưu tiên thứ tự có căn cứ:

1. Xác minh có thật sự xảy ra lỗi lặp và stack trace đang chiếm đáng kể CPU/GC/I/O hay không.
2. Loại bỏ **trace giả tạo** trong nhánh log bị tắt và hàm dựng message đắt tiền không cần thiết.
3. Tránh log đầy đủ một exception ở mọi tầng; giữ một log đủ ngữ cảnh ở ranh giới quan trọng.
4. Tối ưu pattern caller location ở những nơi phát log nhiều; không cắt stack của lỗi quan trọng chỉ để tiết kiệm.
5. Cân nhắc sampling/rate limit, log aggregation, giới hạn dung lượng và pipeline phù hợp chính sách vận hành.
6. Đo lại trong môi trường tương đương sau thay đổi, đồng thời kiểm tra thông tin chẩn đoán còn đầy đủ.

## 12. Ghi nhớ

**Stack trace không chỉ có một chi phí.** `Throwable` thường capture stack lúc được tạo; `getStackTrace()` có thể materialize frame; formatter dựng text/JSON; appender xử lý I/O. Riêng caller location còn có thể yêu cầu stack walk ngay ở đường ghi log, đặc biệt đáng chú ý khi dùng async logger.

Cần ghi stack đầy đủ cho lỗi quan trọng, nhưng tránh tạo exception giả ở đường chạy nóng, tránh format/capture không cần thiết khi level bị tắt, và tránh nhân bản cùng lỗi tại nhiều tầng. Dùng guard/lazy API đúng phiên bản, cấu hình caller data có chủ đích, rồi đo bằng profiler/JMH với tải thực tế trước khi kết luận giải pháp nào tối ưu.
