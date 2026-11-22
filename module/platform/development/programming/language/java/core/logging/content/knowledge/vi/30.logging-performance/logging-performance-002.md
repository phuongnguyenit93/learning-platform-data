# Kiểm tra level trước log trong Java: tối ưu chi phí logging

## 1. Vì sao cần kiểm tra level trước khi ghi log?

Mỗi lời gọi logging có thể cần tính toán tham số, nối chuỗi, chuyển đối tượng sang JSON, truy vấn trạng thái, tạo stack trace hoặc gom dữ liệu ngữ cảnh. Khi mức `DEBUG`/`TRACE` bị tắt, framework thường **không phát sự kiện log đó**, nhưng Java vẫn **đánh giá đối số của lời gọi phương thức trước khi gọi logger**.

Ví dụ:

```java
log.debug("Payload: " + serializeToJson(payload));
```

Đây là mã minh họa trong một ứng dụng có logger `log` và phương thức `serializeToJson`. Nếu biểu thức `serializeToJson(payload)` tốn 20 ms, chi phí đó có thể vẫn xảy ra dù mức DEBUG bị tắt: Java phải tính chuỗi trước khi gọi `debug(...)`.

**Kiểm tra level trước log** là việc hỏi logger xem một mức có đang được bật hay không trước khi làm các công việc **chỉ phục vụ việc ghi log**:

```java
if (log.isDebugEnabled()) {
    log.debug("Payload: {}", serializeToJson(payload));
}
```

Mục tiêu là tránh thực hiện những phép tính không cần thiết trên đường chạy nóng (hot path) như xử lý từng request, từng phần tử trong vòng lặp hoặc từng sự kiện của stream.

Tuy nhiên, **không cần bao mọi lời gọi logger trong một `if`**. Với các tham số đã có sẵn và cú pháp logging tham số hóa, chính framework thường đã tối ưu việc định dạng thông điệp khi level bị tắt. Cần xác định cụ thể chi phí nào phát sinh **trước** lời gọi logger.

## 2. Cơ chế: Java đánh giá đối số trước lời gọi phương thức

Hãy tách một lời gọi log thành các giai đoạn:

```text
Ứng dụng tạo tham số/biểu thức
             |
             v
   Gọi logger.debug(...)
             |
             v
   Kiểm tra level/logger filter
             |
       +-----+------+
       |            |
    disabled      enabled
       |            |
     bỏ qua     tạo/ghi sự kiện
                    |
             handler/appender
                    |
                sink/queue
```

Đường `disabled` thường tránh được công việc ở những bước sau, nhưng **không quay ngược thời gian để hủy việc tạo tham số** đã diễn ra ở bước đầu.

Các dạng gọi có khác biệt lớn:

| Cách viết | Công việc diễn ra khi DEBUG tắt | Nhận xét |
| --- | --- | --- |
| `log.debug("ready")` | Gọi logger và kiểm tra mức | Thường không cần guard thủ công |
| `log.debug("id={}", id)` | Đánh giá/đọc đối số `id`; việc định dạng thường được trì hoãn | Phù hợp với giá trị đã sẵn có |
| `log.debug("value=" + expensive())` | **Gọi `expensive()` và nối chuỗi** | Nên thay bằng lazy evaluation hoặc guard |
| `log.debug("value={}", expensive())` | **Vẫn gọi `expensive()`** | Placeholder không làm phép tính đối số trở nên lazy |
| `if (log.isDebugEnabled()) { log.debug("value={}", expensive()); }` | Chỉ gọi `isDebugEnabled()` khi tắt | Hữu ích nếu `expensive()` thực sự tốn tài nguyên |
| `log.atDebug().addArgument(() -> expensive()).log("value={}")` | Supplier không cần chạy khi DEBUG tắt, với SLF4J 2.x hỗ trợ API này | Cần đúng phiên bản thư viện/provider |

Đối với Java, việc gọi `someObject.toString()`, `String.format(...)`, `objectMapper.writeValueAsString(...)` hoặc `buildStackTrace()` trong đối số đều có thể xảy ra **ngay lập tức**. Ngược lại, truyền chính đối tượng `someObject` cho API tham số hóa thường cho phép backend quyết định có cần chuyển nó sang chuỗi hay không.

## 3. Ví dụ Java 17 độc lập với java.util.logging

JDK có sẵn `java.util.logging` (JUL). Ta dùng ví dụ xác định được kết quả để chứng minh ba cách ghi log: tính thông điệp ngay, dùng `Supplier<String>`, và kiểm tra `isLoggable(...)` trước.

Lưu tệp **`LevelGuardDemo.java`**:

```java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LevelGuardDemo {
    private static int calculations;

    private static String expensiveMessage() {
        calculations++;
        return "details-" + calculations;
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.level-guard");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        Handler output = new Handler() {
            {
                setLevel(Level.ALL);
            }

            @Override
            public void publish(LogRecord record) {
                if (record != null && isLoggable(record)) {
                    System.out.println(record.getLevel().getName()
                            + ": " + record.getMessage());
                }
            }

            @Override
            public void flush() {
                System.out.flush();
            }

            @Override
            public void close() {
                flush(); // Không đóng System.out dùng chung.
            }
        };

        logger.addHandler(output);

        try {
            logger.fine(expensiveMessage()); // Tính dù FINE đang tắt.
            logger.fine(() -> expensiveMessage()); // Supplier: không tính.
            if (logger.isLoggable(Level.FINE)) {
                logger.fine(expensiveMessage()); // Không vào nhánh.
            }

            logger.info("Service ready");
            System.out.println("calculations(INFO)=" + calculations);

            logger.setLevel(Level.FINE);
            logger.fine(() -> expensiveMessage()); // Bây giờ Supplier chạy.
            System.out.println("calculations(FINE)=" + calculations);
        } finally {
            logger.removeHandler(output);
            output.close();
        }
    }
}
```

Biên dịch và chạy trên **JDK 17 trở lên**:

```bash
javac LevelGuardDemo.java
java LevelGuardDemo
```

Kết quả **`stdout`**:

```text
INFO: Service ready
calculations(INFO)=1
FINE: details-2
calculations(FINE)=2
```

Giải thích:

1. `logger.setLevel(Level.INFO)` khiến `FINE` không được logger chấp nhận.
2. `logger.fine(expensiveMessage())` vẫn chạy `expensiveMessage()` trước; biến đếm thành 1 dù dòng `FINE` bị bỏ.
3. `logger.fine(() -> expensiveMessage())` truyền một `Supplier<String>`. Khi FINE đang tắt, logger không cần gọi supplier; biến đếm vẫn là 1.
4. `logger.isLoggable(Level.FINE)` trả về `false`, nên khối `if` không chạy.
5. `logger.info("Service ready")` tạo sự kiện INFO và handler gửi ra stdout.
6. Sau khi bật `Level.FINE`, supplier được gọi, biến đếm thành 2 và sự kiện `FINE` xuất hiện.

Handler riêng dùng ở đây để có output xác định. `ConsoleHandler` tiêu chuẩn của JUL thường ghi vào `stderr`, trong khi ví dụ tự chọn `stdout`. Mã gỡ handler trong `finally` và không đóng stream toàn cục.

**Lưu ý:** bộ đếm minh họa việc tính toán, không phải phép đo thời gian. Khi logger bật, cả guard và supplier đều có thể phải chạy tác vụ tốn chi phí. Đặt guard chỉ tối ưu trường hợp log bị tắt.

## 4. Các API kiểm tra level trong Java

### 4.1. java.util.logging (JUL)

JUL sử dụng `Level.FINEST`, `FINER`, `FINE`, `INFO`, `WARNING`, `SEVERE` cùng `ALL`, `OFF`; không có hằng `Level.DEBUG` theo kiểu Logback.

```java
if (logger.isLoggable(Level.FINE)) {
    logger.fine(expensiveMessage());
}
```

Đây là **đoạn mã tích hợp**, giả định biến `logger` có kiểu `java.util.logging.Logger` và phương thức `expensiveMessage()` tồn tại. `isLoggable` giúp tránh phép tính đắt tiền khi level không được logger chấp nhận.

JUL cũng cung cấp các overload nhận `Supplier<String>`:

```java
logger.log(Level.FINE, () -> expensiveMessage());
logger.fine(() -> expensiveMessage());
```

Ở đây chuỗi chỉ được tạo khi lời gọi logging ở mức tương ứng thực sự đi qua kiểm tra bật/tắt ban đầu của logger. API này thường gọn hơn một `if` thủ công khi chỉ cần tạo **thông điệp** một cách lazy.

Đối chiếu:

```java
logger.log(Level.FINE, "Details: {0}", computeDetails()); // computeDetails chạy ngay
logger.log(Level.FINE, () -> "Details: " + computeDetails()); // Tạo khi cần
```

Cả hai dòng đều là mã minh họa có biến/logger và phương thức do ứng dụng cung cấp. Cú pháp `{0}` của JUL dùng quy tắc `MessageFormat`, khác placeholder `{}` của SLF4J.

Không nên coi `isLoggable(Level.FINE)` là lời hứa rằng sự kiện chắc chắn xuất hiện trong file: handler có thể có ngưỡng cao hơn, filter có thể từ chối, hoặc sink có thể gặp lỗi.

### 4.2. Java Platform Logging API (Java 9+)

JDK còn có `System.Logger` và `System.getLogger(...)`, khác interface JUL và khác `org.slf4j.Logger`. API này cũng cho phép hỏi `isLoggable`:

```java
System.Logger platformLogger = System.getLogger("demo.runtime");

if (platformLogger.isLoggable(System.Logger.Level.DEBUG)) {
    platformLogger.log(System.Logger.Level.DEBUG, expensiveMessage());
}
```

Đây là mảnh mã tích hợp vào class có `expensiveMessage()`; mức `System.Logger.Level.DEBUG` thuộc **Platform Logging API**, không phải `java.util.logging.Level`. Hành vi xuất log cuối cùng phụ thuộc logging provider được JVM/app chọn. Không trộn tên enum level giữa hai API.

## 5. SLF4J: `isDebugEnabled()`, placeholder và chi phí tham số

Trong ứng dụng Spring Boot hoặc Java sử dụng SLF4J, các kiểm tra phổ biến là:

| Câu hỏi | API SLF4J |
| --- | --- |
| TRACE đang bật? | `log.isTraceEnabled()` |
| DEBUG đang bật? | `log.isDebugEnabled()` |
| INFO đang bật? | `log.isInfoEnabled()` |
| WARN đang bật? | `log.isWarnEnabled()` |
| ERROR đang bật? | `log.isErrorEnabled()` |

Để dùng các API này cần dependency SLF4J và một provider/backend tương thích (ví dụ Logback Classic hoặc Log4j 2 qua provider thích hợp).

### 5.1. Khi đã có giá trị, hãy dùng placeholder

```java
log.debug("Order id={} status={}", orderId, status);
```

Đây là đoạn mã tích hợp, giả định `log` là `org.slf4j.Logger`, `orderId` và `status` đã có. Với log tham số hóa `{}`, backend thường trì hoãn việc chuyển các đối số thành thông điệp văn bản cho tới khi sự kiện được chấp nhận.

So sánh với:

```java
log.debug("Order id=" + orderId + " status=" + status);
```

Ở dạng nối chuỗi, Java tạo string trước lời gọi `debug` dù level đang tắt; trong một hot path bị gọi rất nhiều lần, chi phí này có thể đáng kể.

**Không đồng nghĩa tham số hóa là không tốn chi phí:** Java vẫn phải đánh giá biểu thức đối số. Nếu truyền nhiều đối số qua overload varargs, có thể còn phát sinh tạo mảng tham số, và framework vẫn phải kiểm tra level. Đánh giá hiệu năng nên dựa vào profiler/benchmark thay vì giả định “luôn bằng 0”.

### 5.2. Khi tham số cần được tính toán

Đoạn mã sau là **mã minh họa tích hợp**, không chạy độc lập nếu chưa có `log`, `order` và phương thức `serializeAsJson`:

```java
// Không tối ưu: tạo JSON ngay cả khi DEBUG tắt.
log.debug("Order JSON={}", serializeAsJson(order));

// Tối ưu khi phép serialize tốn kém và chỉ phục vụ debug.
if (log.isDebugEnabled()) {
    log.debug("Order JSON={}", serializeAsJson(order));
}
```

Nếu `order` vốn đã có `toString()` gọn, có thể viết `log.debug("Order={}", order)` và để backend quyết định định dạng. Ngược lại, `log.debug("Order={}", order.toString())` khiến `toString()` chạy ngay ở phía ứng dụng.

Guard hữu ích hơn khi một giá trị phải đọc từ nơi lưu trữ, dựng cấu trúc dữ liệu lớn, chuyển bytes thành chuỗi, chạy regex nặng hoặc serialize JSON chỉ để chẩn đoán. **Đừng thực hiện truy vấn database hay thay đổi dữ liệu nghiệp vụ chỉ để tạo message khi không thật sự cần.**

### 5.3. SLF4J 2.x: fluent logging và Supplier

Từ **SLF4J 2.0**, fluent API có thể nhận `Supplier` làm đối số lười đánh giá:

```java
// Đoạn tích hợp, yêu cầu SLF4J 2.x và log/order phù hợp.
log.atDebug()
        .addArgument(() -> serializeAsJson(order))
        .log("Order JSON={}");
```

Khi DEBUG tắt, builder thường là đối tượng no-op và không yêu cầu gọi supplier. Khi DEBUG bật, backend có thể lấy giá trị supplier để xử lý sự kiện. Điều này có thể tránh một khối `if` dài. Dòng `.log(...)` cuối cùng rất quan trọng: chỉ tạo builder hoặc thêm đối số không đồng nghĩa sự kiện đã được phát.

Không nhầm cú pháp này với SLF4J 1.x, vốn không có cùng fluent API. Với các hệ thống lâu năm, có thể dùng guard `isDebugEnabled()` để tương thích với API logging đang dùng.

### 5.4. Log4j 2 và Logback

Log4j 2 API có `logger.isDebugEnabled()` cùng phương thức logging tham số hóa; các phiên bản API/backend còn hỗ trợ dạng ghi log lazy. Phải dùng overload và loại `Supplier` phù hợp **phiên bản Log4j 2 thực tế**. Trong Logback, ứng dụng thường viết qua API SLF4J và dùng `log.isDebugEnabled()`/placeholder như trên. Tên method trên JUL (`isLoggable`) không có nghĩa SLF4J hoặc Log4j 2 dùng đúng cùng chữ ký.

## 6. Level ở logger khác level ở handler/appender

Việc kiểm tra trước log chỉ là **kiểm tra sơ bộ** cho chi phí phía ứng dụng. Một sự kiện đã qua logger vẫn có thể bị chặn ở các tầng sau.

Ví dụ JUL:

```text
Logger:  FINE
Handler: INFO

logger.isLoggable(FINE)  -> true
handler nhận FINE?      -> false
```

Tức là nếu code kiểm tra `logger.isLoggable(Level.FINE)` rồi tạo một chuỗi rất đắt tiền, handler vẫn có thể loại sự kiện FINE. Với backend khác, filter của appender hoặc route của collector có thể quyết định cuối cùng.

Trong Logback, một logger con được đặt DEBUG có thể phát sự kiện DEBUG ngay cả khi root logger có mức INFO, vì logger con có mức cấu hình riêng và sự kiện có thể đi theo đường additivity. Cần hiểu effective logger level và filter của từng appender.

**Điều có thể kết luận từ guard:** chương trình không làm công việc dành riêng cho mức log đó nếu guard trả `false` tại thời điểm kiểm tra.

**Điều không thể kết luận:** nếu guard trả `true` thì mọi sự kiện chắc chắn sẽ được ghi, flush, truyền tới collector hoặc tồn tại bền vững trên đĩa.

Thay đổi level lúc runtime còn tạo một tình huống đua: sau khi `isDebugEnabled()` trả `true`, luồng khác có thể tắt DEBUG trước lời gọi `log.debug(...)`. Backend thường kiểm tra lại trong đường logging; guard là một gợi ý hiệu năng, **không phải cơ chế đồng bộ hay cam kết ghi log**.

## 7. Guard không được che giấu logic nghiệp vụ

Một lỗi nguy hiểm là để lời gọi có tác dụng phụ nằm trong nhánh chỉ chạy khi DEBUG bật:

```java
// Sai về thiết kế: nghiệp vụ phụ thuộc mức logging.
if (log.isDebugEnabled()) {
    applyPayment(order);
    log.debug("Payment applied");
}
```

Nếu DEBUG tắt, `applyPayment(order)` hoàn toàn không chạy. Mức logging vì thế vô tình điều khiển nghiệp vụ.

Cách đúng:

```java
applyPayment(order);

if (log.isDebugEnabled()) {
    log.debug("Payment applied, details={}", describeForDebug(order));
}
```

Hai đoạn trên là **mã minh họa tích hợp**, không độc lập; các phương thức/biến do ứng dụng định nghĩa. `applyPayment(...)` thực thi bất kể logging có bật không, còn `describeForDebug(...)` chỉ phục vụ logging nên được guard.

Cũng không để việc cập nhật counter nghiệp vụ, tạo audit record bắt buộc hoặc validate dữ liệu chỉ xảy ra trong `Supplier` của logging. Supplier có thể không được gọi; một vài backend/filter còn có thời điểm đánh giá khác nhau. Hàm dùng để tạo message nên **tránh side effects**, xử lý input đã có, và không thay đổi hành vi ứng dụng nếu bị bỏ qua.

## 8. Exception và thông tin tốn kém

Log exception là nhu cầu thường gặp, nhưng việc **tự chuyển exception thành stack trace string** có thể tốn chi phí:

```java
// Không tối ưu nếu DEBUG bị tắt:
log.debug("Problem: {}", stackTraceToString(error));

// Nếu muốn xem exception khi DEBUG bật:
if (log.isDebugEnabled()) {
    log.debug("Problem while processing request", error);
}
```

Đây là **đoạn mã tích hợp** với SLF4J, yêu cầu `log`, `error` và helper `stackTraceToString`; không phải chương trình độc lập. Dạng truyền đối tượng `Throwable` cho backend thường giúp framework xử lý stack trace phù hợp khi sự kiện được chấp nhận. Đừng gọi `error.getStackTrace()`, `Arrays.toString(...)` hoặc tạo `new Exception()` trong mọi vòng lặp chỉ để chuẩn bị log mức bị tắt.

Nhưng nếu lỗi quan trọng và đáng ghi ở `ERROR`, **không hạ nó xuống DEBUG chỉ để tiết kiệm tài nguyên**. Chọn level phản ánh nhu cầu vận hành; sau đó tối ưu cách dựng message ở level đó.

Với PII, token hoặc bí mật, nguyên tắc “chỉ tính khi DEBUG bật” **không phải biện pháp bảo mật dữ liệu**: khi DEBUG được bật, thông điệp vẫn có thể lộ. Kiểm soát trường dữ liệu nào được phép ghi trước khi đưa vào logging.

## 9. Những chi phí khác mà guard không loại bỏ

Ngay cả khi các thông điệp DEBUG không được tạo, logging vẫn có những chi phí khác:

- **Kiểm tra level:** lời gọi method, lookup cấu hình hiệu lực; thường nhỏ nhưng không hoàn toàn bằng 0.
- **Tham số đã được tạo trước:** đối tượng nghiệp vụ hoặc dữ liệu context có sẵn vẫn chiếm tài nguyên vì nhu cầu của chương trình.
- **MDC và context propagation:** việc thiết lập `MDC.put(...)` trước guard vẫn có thể tốn chi phí, cần dựa trên yêu cầu tương quan chung của request.
- **Log được bật:** formatter/encoder, stack trace, caller information, file/network I/O, contention và lock vẫn phát sinh.
- **Queue bất đồng bộ:** lời gọi có thể bị chặn nếu queue đầy hoặc sink chậm; guard chỉ giảm số sự kiện ở một số level, không chữa được nghẽn của mọi kênh.
- **Fan-out nhiều appender:** một sự kiện được ghi sang nhiều sink có thêm chi phí; kiểm tra level ở source không thay thế việc thiết kế routing hợp lý.

Không giả định chỉ cần thêm `isDebugEnabled()` là khắc phục được p99 latency cao do log INFO quá nhiều hoặc do appender ghi file đồng bộ.

## 10. Khi nào nên thêm guard?

Nên xem xét guard hoặc lazy API khi:

1. Thông điệp chứa serialization JSON/XML, chuỗi khổng lồ hoặc một phép tính CPU nặng chỉ dùng để debug.
2. Một vòng lặp rất nóng phát sinh nhiều lời gọi DEBUG/TRACE và profiler cho thấy chi phí dựng đối số.
3. Việc tạo thông điệp cần truy cập dữ liệu chưa có sẵn hoặc thao tác với cấu trúc collection lớn.
4. Ghi thông tin chẩn đoán mang tính tùy chọn, cần tắt hoàn toàn chi phí xử lý khi level tương ứng không bật.
5. Backend không có API lazy phù hợp và `isXEnabled()` là lựa chọn rõ ràng nhất.

Thường **không cần** guard nếu:

1. Log là một literal, ví dụ `log.info("Server started")`.
2. Các tham số đơn giản đã có, chẳng hạn `log.debug("Status={}", status)`.
3. Phép tính là bắt buộc cho nghiệp vụ dù có ghi log hay không.
4. Chỉ có mục tiêu làm code “trông tối ưu” nhưng không có phép đo cho thấy logging là bottleneck.

Giữa guard thủ công và Supplier, chọn cách **dễ đọc, phù hợp phiên bản API**, rồi kiểm tra bằng profiler/benchmark trong tình huống thực tế.

## 11. Đo lường hiệu năng logging

Không có quy tắc rằng mọi `if (log.isDebugEnabled())` đều làm chương trình nhanh hơn một cách đáng kể. Cần phân biệt ít nhất bốn kịch bản:

| Kịch bản | Điều cần đo |
| --- | --- |
| DEBUG tắt, literal/placeholder với dữ liệu đã có | Chi phí cơ sở của lời gọi logger |
| DEBUG tắt, tính toán JSON/stack trace trong đối số | Chi phí lãng phí trước khi logger nhận sự kiện |
| DEBUG tắt, guard hoặc Supplier | Mức chi phí tránh được và overhead của guard/Supplier |
| DEBUG bật | Chi phí tạo thông điệp + formatter/appender + I/O hoặc queue |

Đo trong điều kiện giống ứng dụng thật: kích thước payload, số thread, logger level, số appender, cấu hình async, kiểu sink và tốc độ tạo log. Cần quan sát:

- **Throughput và latency** của đường nghiệp vụ; đặc biệt p95/p99 nếu log diễn ra trên request thread.
- **CPU/allocations/GC** do serialization, nối chuỗi và tạo đối tượng logging.
- **Số sự kiện được tạo, được ghi và bị drop**, nhất là với async logging.
- **Tác động ở trạng thái bật/tắt level**, vì một tối ưu cho DEBUG tắt có thể không cải thiện khi INFO đang quá tải.
- **Bộ nhớ và queue depth** khi bật logging ở mức chi tiết cao.

Với Java, dùng profiler (ví dụ Java Flight Recorder) để tìm allocation/call stack, rồi dùng JMH cho microbenchmark nếu cần so sánh overhead nhỏ. Khi benchmark logging, nên kiểm soát sink và tránh để việc ghi terminal/file thực sự lấn át phép đo nếu mục tiêu chỉ là chi phí dựng message. Đồng thời cần một bài load test end-to-end để thấy tác động I/O thực.

Đừng dùng một vòng `System.nanoTime()` đơn giản và kết luận chắc chắn về hiệu năng từ vài lần chạy: JVM JIT warmup, dead-code elimination, GC, CPU scheduling và I/O có thể làm kết quả sai lệch.

## 12. Những lỗi phổ biến

### Lỗi 1: “Dùng `{}` là không chạy phương thức expensive”

```java
log.debug("Body={}", expensiveBody());
```

**Sai.** Java vẫn tính `expensiveBody()` trước khi gọi `debug`. Hãy dùng guard hoặc Supplier nếu thích hợp.

### Lỗi 2: “Thêm guard cho mọi log đều tốt hơn”

```java
if (log.isInfoEnabled()) {
    log.info("Started");
}
```

Cách viết này thêm nhánh mà không tránh được phép tính đắt tiền nào; thường chỉ làm code dài hơn. Backend đã tự kiểm tra level cho lời gọi `info`.

### Lỗi 3: “Lưu `isDebugEnabled()` vào biến static để khỏi gọi lại”

```java
private static final boolean DEBUG_ENABLED = LOG.isDebugEnabled();
```

Đây là **đoạn mã minh họa** nhưng là thói quen không phù hợp khi hệ thống có khả năng đổi log level runtime: biến chỉ phản ánh trạng thái ở lúc khởi tạo, có thể trở nên cũ. Nên kiểm tra theo ngữ cảnh khi chuẩn bị phép tính nặng.

### Lỗi 4: “Guard true nghĩa là chắc chắn đã ghi tới file”

Không đúng. Handler/appender filter, async queue, sink lỗi hoặc tiến trình bị dừng vẫn có thể ngăn bản ghi đến đích.

### Lỗi 5: “Supplier giống mọi phép tính không có tác dụng phụ”

Supplier có thể không được gọi khi level tắt. Nếu hàm trong supplier cập nhật dữ liệu nghiệp vụ, code sẽ có hành vi khác khi đổi level. Hãy giữ việc tạo thông điệp chỉ để quan sát.

### Lỗi 6: “Không thấy DEBUG nên không mất hiệu năng”

Có thể mã đang nối chuỗi, serialize JSON hoặc tạo stack trace trước khi logger kiểm tra level. Cần profiler để xác nhận.

### Lỗi 7: “Bật DEBUG trong production không gây tác động vì đã có guard”

Khi DEBUG bật, guard cho phép chạy toàn bộ công việc tốn kém và còn phải ghi sự kiện. Cần giới hạn thời gian bật, phạm vi package/logger và dung lượng log.

## 13. Checklist thực hành

- Chọn level theo **ý nghĩa vận hành**: TRACE/DEBUG cho chẩn đoán chi tiết, INFO cho sự kiện thông thường, WARN/ERROR cho vấn đề cần chú ý; không dùng level chỉ để ép một hành vi tối ưu.
- Dùng **placeholder** thay nối chuỗi khi logging qua SLF4J/Log4j 2 phù hợp.
- Với phép tính chỉ phục vụ log và có chi phí đáng kể, dùng `isDebugEnabled()`, `isLoggable(...)` hoặc API **Supplier** được backend hỗ trợ.
- Đảm bảo điều kiện logging **không kiểm soát nghiệp vụ** và Supplier không mang side effects.
- Kiểm tra cả **logger level lẫn handler/appender filter**, đặc biệt khi có nhiều route.
- Không đánh giá sự thành công của logging chỉ từ guard trả `true`; cần kiểm tra sink và việc giao nhận.
- Tránh cache một cờ “DEBUG đang bật” bất biến nếu hệ thống đổi level trong runtime.
- Đo CPU, allocation, throughput, tail latency và hành vi khi log được bật/tắt trước khi tối ưu trên diện rộng.
- Giảm log quá chi tiết trong vòng lặp, giữ các event có ý nghĩa và tránh đưa secret/PII vào thông điệp.

**Kết luận:** Kiểm tra level trước log hữu ích nhất khi nó **ngăn Java làm một phép tính đắt tiền vốn chỉ phục vụ ghi log**. Với lời gọi đơn giản, framework đã kiểm tra level; với đối số nặng, cần guard hoặc lazy API thích hợp. Quy tắc này tối ưu chi phí tạo event, trong khi chi phí của appender, queue và sink vẫn phải được giải quyết bằng thiết kế logging toàn hệ thống.
