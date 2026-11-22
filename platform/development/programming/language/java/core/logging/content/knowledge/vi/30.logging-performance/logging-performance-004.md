# Lazy message trong hiệu năng logging Java

## 1. Mục tiêu: chỉ tạo thông điệp khi thật sự cần

**Lazy message** (tạo thông điệp log theo nhu cầu) là cách trì hoãn xây dựng một chuỗi log hoặc tính một đối số tốn kém cho đến khi hệ thống logging quyết định có cần dùng nội dung đó hay không. Đây là kỹ thuật tối ưu hiệu năng quan trọng khi lệnh log nằm trên *hot path*: vòng lặp lớn, xử lý nhiều request, luồng batch hoặc code có nhiều DEBUG/FINE bị tắt trong production.

Ví dụ, ứng dụng đang đặt level INFO. Hai đoạn JUL sau có ý nghĩa khác nhau:

```java
// Eager: expensiveDetail() được tính trước khi logger kiểm tra mức FINE.
log.fine("detail=" + expensiveDetail());

// Lazy: phần thân lambda chỉ được chạy khi logger cho phép FINE.
log.fine(() -> "detail=" + expensiveDetail());
```

`log` ở đây là `java.util.logging.Logger` và `expensiveDetail()` là phương thức giả định. Phần 5 có chương trình Java 17+ chạy độc lập để chứng minh khác biệt.

Cần hiểu rõ ba điều:
- **Lazy** có thể tránh việc tạo message/đối số khi log bị tắt bởi kiểm tra level, nhưng không bảo đảm **không mất bất kỳ chi phí nào**. Java vẫn gọi API logging, có thể tạo lambda/capture biến và thực hiện kiểm tra level/filter.
- **Parameterized logging** (`"userId={}"`) có thể trì hoãn định dạng chuỗi, nhưng bản thân các biểu thức đối số của Java vẫn được tính trước lời gọi.
- **Asynchronous logging** là việc chuyển event sang worker/sink ở thời điểm khác. Nó không đồng nghĩa message và đối số mặc nhiên được tính lazy.

Sau bài này, bạn có thể lựa chọn đúng cách viết với JUL, `System.Logger`, SLF4J truyền thống, SLF4J 2.x fluent API và Log4j 2; viết test đếm số lần tính message; đánh giá tương quan giữa lazy, filter, async và throughput.

## 2. Cốt lõi nằm ở quy tắc đánh giá biểu thức của Java

Java đánh giá đối số trước khi gọi một phương thức. Vì vậy các lời gọi sau **không lazy** đối với phần tính toán đặt trong đối số:

```java
// Ví dụ tích hợp, không phải chương trình độc lập.
logger.debug("state=" + expensiveState());
logger.debug(String.format("state=%s", expensiveState()));
logger.debug("state={}", expensiveState());
```

Dù logger tắt DEBUG, Java vẫn cần:
1. Gọi `expensiveState()` để có giá trị của biểu thức.
2. Thực hiện nối chuỗi hoặc `String.format` nếu chúng nằm trong đối số.
3. Mới truyền đối số cho `logger.debug(...)`.

Ở dòng thứ ba, `{}` thường được SLF4J/Log4j 2 dùng để **định dạng**; nó không thay đổi cách Java tính `expensiveState()`. Do đó một câu có placeholder vẫn có thể tạo truy vấn DB, serialize JSON hoặc duyệt collection không cần thiết.

Ngược lại, lambda `() -> "state=" + expensiveState()` là một giá trị kiểu hàm. Java có thể tạo/capture đối tượng lambda tại call site, nhưng **không thực thi thân lambda** cho đến khi đối tượng nhận gọi `Supplier.get()`. Hệ thống logging có overload nhận Supplier sẽ quyết định thời điểm gọi đó.

So sánh:

```java
// Tính trước, Supplier chỉ trả về giá trị đã tính:
String detail = expensiveState();
log.fine(() -> "state=" + detail);

// Tính bên trong Supplier khi hệ thống cần:
log.fine(() -> "state=" + expensiveState());
```

Một thao tác bắt buộc cho nghiệp vụ **không được** đặt trong Supplier của logging. Nếu level tắt, Supplier có thể không bao giờ chạy.

## 3. Các chiến lược giảm chi phí message

| Cách dùng | Khi DEBUG/FINE tắt | Khi level bật | Phù hợp |
| --- | --- | --- | --- |
| Nối chuỗi: `log.debug("x=" + heavy())` | `heavy()` vẫn chạy | Tạo chuỗi trước khi gọi logger | Tránh khi `heavy()` đắt |
| Placeholder với biến sẵn: `log.debug("x={}", x)` | Đánh giá biến `x`, thường bỏ bước format | Format theo backend/layout | Đối số rẻ, đã có |
| Placeholder với hàm: `log.debug("x={}", heavy())` | `heavy()` vẫn chạy | Tạo giá trị và format | Chưa tối ưu đúng chỗ |
| Guard: `if (log.isDebugEnabled()) ...` | Bỏ cả khối tính toán | Tính khi guard true | SLF4J cũ, nhiều bước tính |
| JUL: `log.fine(() -> heavy())` | Supplier body không chạy nếu FINE tắt | Gọi Supplier khi mức cho phép | JUL Java 8+ |
| SLF4J 2: `atDebug().addArgument(() -> heavy())` | Supplier được bỏ qua khi DEBUG tắt | Cung cấp đối số khi log | SLF4J 2.0+ |
| Log4j 2: overload Supplier | Có thể bỏ phần tính toán khi mức lọc sớm loại | Tính khi event được chấp nhận | Log4j 2 API |

Bảng mô tả mục đích tối ưu. Event còn có thể bị loại bởi filter ở appender hoặc mất trong async pipeline; gọi Supplier thành công **không đồng nghĩa** thông điệp được lưu bền vững.

### Khi nào guard có giá trị?

Nếu chỉ log `LOG.debug("count={}", count)` với một biến int có sẵn, thêm guard có thể làm code rườm rà mà lợi ích nhỏ. Nhưng nếu cần tổng hợp cấu trúc lớn, thực hiện nhiều phép tính hay tạo một báo cáo chẩn đoán, guard giúp tránh cả khối:

```java
if (LOG.isDebugEnabled()) {
    String summary = buildOrderSummary(order);
    Map<String, Long> counters = calculateCounters(order);
    LOG.debug("summary={} counters={}", summary, counters);
}
```

Đây là đoạn SLF4J tích hợp (các phương thức, `order` và `Map` cần được định nghĩa). Kiểm tra level không phải giao dịch nguyên tử với phát event: backend có thể thay đổi cấu hình ngay sau guard. Vì logging phục vụ chẩn đoán, ta không dựa vào guard để điều khiển các hiệu ứng nghiệp vụ bắt buộc.

## 4. Lazy theo level không đồng nghĩa lazy đến tận sink

Luồng xử lý khái quát:

```text
Thread ứng dụng
      |
      +--> Java đánh giá các đối số thông thường (eager)
      |
      +--> Logger kiểm tra level / filter sớm
                    |
             không chấp nhận ---> bỏ event
                    |
              chấp nhận
                    |
                    v
          Supplier được đánh giá nếu API cần
                    |
                    v
          LogEvent / LogRecord
                    |
          appender / handler filter
                    |
          format, queue, file, collector
```

Thứ tự chi tiết phụ thuộc backend và chế độ sync/async. Đặc biệt:
- **JUL:** `Logger` kiểm tra mức log trước, rồi tạo `LogRecord`/áp dụng filter và gửi cho `Handler`. `Supplier<String>` được đánh giá khi logger cho phép level tương ứng; `Handler` còn có level/filter riêng.
- **Logback:** có kiểm tra logger level, `TurboFilter` sớm và filter thông thường ở appender. Nếu lọc cuối đường, event có thể đã được tạo.
- **Log4j 2:** có nhiều tầng filter (global, logger, appender reference, appender), nên cần đọc đúng contract của từng tầng.

Ví dụ: logger JUL được đặt `FINE` nhưng ConsoleHandler chỉ nhận `WARNING`. Khi chạy `logger.fine(() -> expensiveState())`, logger cho phép FINE nên Supplier có thể chạy; handler sau đó bỏ event. Khi tối ưu chi phí tính toán, ưu tiên không tạo event không cần ngay từ logger hoặc filter sớm, thay vì chỉ nâng threshold ở đích.

Tương tự, một logger có thể gửi INFO đến file và chỉ WARN đến collector. Vì event INFO vẫn cần cho file, không thể kết luận nó phải bị loại hoàn toàn chỉ vì collector đặt WARN.

## 5. Chương trình Java 17+ độc lập kiểm chứng lazy message

Đây là ví dụ chỉ dùng JDK, không cần JUnit, Logback hoặc SLF4J. Chương trình tạo logger JUL riêng, cài handler in stdout và dùng `AtomicInteger` đếm lần tạo nội dung tốn kém.

Tạo file **`LazyMessageDemo.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LazyMessageDemo {
    public static void main(String[] args) {
        Logger log = Logger.getAnonymousLogger();
        log.setUseParentHandlers(false);
        log.setLevel(Level.INFO);

        Handler sink = new Handler() {
            @Override
            public void publish(LogRecord event) {
                if (isLoggable(event)) {
                    System.out.println(event.getLevel().getName()
                            + " " + event.getMessage());
                }
            }

            @Override public void flush() {}
            @Override public void close() {}
        };

        sink.setLevel(Level.ALL);
        log.addHandler(sink);
        AtomicInteger builds = new AtomicInteger();
        Supplier<String> detail =
                () -> "payload-" + builds.incrementAndGet();

        try {
            // FINE bị tắt, lambda body không chạy.
            log.fine(() -> "debug " + detail.get());
            System.out.println("after-disabled=" + builds.get());

            // INFO được bật, Supplier được gọi.
            log.info(() -> "visible " + detail.get());
            System.out.println("after-enabled=" + builds.get());

            // Biểu thức eager vẫn được tính khi FINE bị tắt.
            log.fine("eager " + detail.get());
            System.out.println("after-eager=" + builds.get());
        } finally {
            log.removeHandler(sink);
            sink.close();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac LazyMessageDemo.java
java LazyMessageDemo
```

**Kết quả stdout chính xác của ví dụ này:**

```text
after-disabled=0
INFO visible payload-1
after-enabled=1
after-eager=2
```

Giải thích:
1. Logger ở `Level.INFO`, nên lời gọi `fine(Supplier<String>)` bị loại trước khi body lambda chạy: bộ đếm vẫn bằng 0.
2. `info(Supplier<String>)` được logger cho phép, nên lambda gọi `detail.get()`; handler in `INFO visible payload-1` và bộ đếm tăng thành 1.
3. `fine("eager " + detail.get())` phải tính `detail.get()` trước khi gọi JUL, dù FINE tắt; kết quả là 2 nhưng không in dòng FINE.
4. `getAnonymousLogger()` cùng `setUseParentHandlers(false)` cô lập ví dụ, tránh root handler in thêm lên stderr.
5. `finally` tháo handler. Với handler có file/network, cần đóng và flush theo hợp đồng thực tế.

Ví dụ chứng minh **số lần tạo message**, không phải benchmark nanosecond. Thay `log.setLevel(Level.INFO)` bằng `Level.FINE` để quan sát khi cả hai level đều bật, rồi giải thích vì sao dòng FINE được in và bộ đếm thay đổi.

## 6. Cách dùng Supplier của JUL và System.Logger

### JUL `java.util.logging.Logger`

Từ Java 8, JUL có `fine(Supplier<String>)`, `info(Supplier<String>)`, `log(Level, Supplier<String>)` và nhiều overload tương ứng. Dùng như sau:

```java
// Đoạn tích hợp: các phương thức sau được định nghĩa trong ứng dụng.
logger.fine(() -> "cache=" + dumpCacheSummary());
logger.log(java.util.logging.Level.FINER,
           () -> "state=" + expensiveState());
```

Nếu mức FINER/FINE bị tắt theo logger, JUL sẽ không tạo message bằng cách gọi các Supplier đó. Phương thức `dumpCacheSummary()`/`expensiveState()` là giả định, vì vậy đoạn này không chạy độc lập.

Khi có exception, giữ `Throwable` ở field riêng thay vì chỉ nối `ex.getMessage()`:

```java
try {
    processOrder();
} catch (Exception ex) {
    logger.log(
        java.util.logging.Level.SEVERE,
        ex,
        () -> "order_failed orderId=" + orderId);
    throw ex;
}
```

Đây cũng là đoạn tích hợp: `processOrder()`, `orderId` và logger phải tồn tại. JUL có overload `log(Level, Throwable, Supplier<String>)`; exception được lưu trong `LogRecord.thrown` để formatter ghi stack trace, còn message được xây dựng lazy theo level. Nếu chỉ ghi `ex.getMessage()`, bạn dễ mất ngữ cảnh stack trace.

### `System.Logger`

Từ Java 9, `java.lang.System.Logger` cũng hỗ trợ Supplier:

```java
System.Logger appLog = System.getLogger("demo.order");
appLog.log(System.Logger.Level.DEBUG,
           () -> "state=" + expensiveState());
```

Đây là đoạn tích hợp, cần phương thức `expensiveState()`. `System.Logger.Level.DEBUG` và `java.util.logging.Level.FINE` là hai enum/class khác nhau; không dùng hoán đổi. Backend cuối cùng của `System.Logger` được quyết định qua `LoggerFinder`/runtime, không phải qua cú pháp lambda.

**Lưu ý chung:** không đặt truy vấn mạng, ghi DB hoặc thao tác thay đổi trạng thái trong Supplier. Logger có quyền bỏ qua nội dung vì level đã tắt; một thao tác bắt buộc phải được thực hiện trong luồng nghiệp vụ trước khi ghi log.

## 7. SLF4J truyền thống: placeholder khác Supplier

SLF4J là một facade/API; Logback, Log4j 2 provider hoặc backend khác xử lý output. Cú pháp thường gặp:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

// Trong một class OrderService có logger và các biến tương ứng.
private static final Logger LOG =
        LoggerFactory.getLogger(OrderService.class);

// Tốt với đối số rẻ đã có sẵn:
LOG.debug("orderId={} status={}", orderId, status);
```

Đây là đoạn mã tích hợp cần SLF4J API/provider và các biến `orderId`/`status`. Với placeholder, SLF4J thường không thực hiện định dạng message nếu level bị tắt. Nhưng:

```java
// KHÔNG lazy đối với expensiveQuery():
LOG.debug("orderId={} details={}",
          orderId, expensiveQuery());
```

Do Java đánh giá arguments trước khi gọi, `expensiveQuery()` vẫn chạy dù DEBUG bị tắt. Trong SLF4J truyền thống (đặc biệt SLF4J 1.7), guard giải quyết được:

```java
if (LOG.isDebugEnabled()) {
    LOG.debug("orderId={} details={}",
              orderId, expensiveQuery());
}
```

Không lạm dụng guard khi chỉ ghi hằng số hoặc đối số rẻ: `LOG.debug("attempt={}", attempt)` thường đủ rõ.

### `toString()` cũng cần thận trọng

```java
LOG.debug("state={}", stateObject);            // Truyền tham chiếu.
LOG.debug("state={}", stateObject.toString()); // Gọi ngay.
```

Dòng đầu có thể giúp backend trì hoãn `toString()`/format khi log tắt. Dòng hai ép `toString()` chạy trước khi backend nhận event. Tuy vậy đối tượng `stateObject` vẫn phải được tạo/tìm ra trước lời gọi, và backend có thể snapshot hoặc format sớm khi event được chấp nhận. Không dựa vào một thời điểm gọi `toString()` bất biến giữa mọi backend hoặc async mode.

Phương thức `toString()` nên đơn giản, không gọi DB, không gửi HTTP và không có side effect. Nó cũng có thể được IDE/debugger, formatter hoặc thư viện khác gọi, nên không thích hợp làm nơi thực hiện nghiệp vụ.

## 8. SLF4J 2.x fluent API: trì hoãn đối số tốn kém

Từ SLF4J 2.0 có `atTrace()`, `atDebug()`, `atInfo()`, `atWarn()`, `atError()` trả về `LoggingEventBuilder`. Khi level tắt, builder không làm gì cho event bị tắt. API fluent hỗ trợ `Supplier<?>` ở `addArgument`.

Ví dụ tích hợp:

```java
LOG.atDebug()
   .setMessage("orderId={} details={}")
   .addArgument(orderId)
   .addArgument(() -> expensiveQuery())
   .log();
```

Giải thích:
- `orderId` là giá trị rẻ đã có, được truyền như argument thông thường.
- `expensiveQuery()` ở **thân lambda** nên không chạy nếu DEBUG tắt theo API fluent.
- `.log()` là lời gọi **bắt buộc để phát event**. Quên nó sẽ không ghi log dù level đang bật.
- Nếu trước đó bạn đã tính `String details = expensiveQuery();` thì truyền `() -> details` không thể lấy lại chi phí bị mất.

SLF4J 2.x còn có key-value cho structured logging:

```java
LOG.atInfo()
   .addKeyValue("orderId", orderId)
   .addKeyValue("status", status)
   .log("order_state_changed");
```

API lưu key/value để backend/layout sử dụng; cách xuất text/JSON phụ thuộc provider. Lưu ý `addKeyValue("details", expensiveQuery())` vẫn đánh giá `expensiveQuery()` theo quy tắc Java. Nếu muốn hoãn chi phí, dùng các overload Supplier được phiên bản cụ thể hỗ trợ hoặc kiểm tra level bằng guard trước khi tính.

### Chọn API theo phiên bản

| API | Cách viết nên dùng cho đối số đắt |
| --- | --- |
| SLF4J 1.7 | `isDebugEnabled()` + lời gọi `debug("{}", value)` |
| SLF4J 2.x truyền thống | Vẫn dùng guard nếu gọi phương thức tạo argument đắt |
| SLF4J 2.x fluent | `atDebug().addArgument(() -> expensive()).log("x={}")` |
| JUL | `fine(() -> expensive())` hoặc `log(Level, Supplier)` |
| Log4j 2 API | Overload nhận Supplier/lambda, xem mục 9 |

Đừng copy `atDebug()` sang dự án SLF4J 1.7: khác biệt nằm ở API compile-time, không phải file cấu hình Logback.

## 9. Log4j 2: Supplier cho đối số và message

Tài liệu Performance của Log4j 2 khuyến nghị truyền `Supplier` khi một đối số cần tính toán đắt tiền. Ví dụ tích hợp với Log4j API:

```java
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

// Bên trong class có orderId và expensiveQuery().
private static final Logger LOG =
        LogManager.getLogger(OrderService.class);

// Supplier chỉ được đánh giá khi quá trình logging cần dữ liệu.
LOG.debug("orderId={} details={}",
          () -> orderId,
          () -> expensiveQuery());
```

`OrderService` và `expensiveQuery()` là phần ứng dụng giả định; đoạn mã này cần Log4j API/core hoặc backend tương thích và không chạy bằng JDK thuần. Đối số đơn giản như `orderId` thường không cần lambda; mục tiêu là hoãn truy vấn/tạo dữ liệu tốn kém.

Log4j 2 cũng có kiểu Supplier tạo message, chẳng hạn `ParameterizedMessage`, tùy overload và phiên bản. Kiểm tra API import thực tế; không suy ra rằng cú pháp `debug("{}", () -> expensive())` chắc chắn hoạt động giống nhau trong JUL, SLF4J truyền thống và Log4j API.

**Filter và marker:** Log4j có nhiều tầng filter. Khi event đã vượt kiểm tra sớm nhưng bị một appender filter loại, chi phí Supplier có thể đã phát sinh. Lazy message tiết kiệm ở đúng điểm quyết định, không có nghĩa message chỉ tính nếu mọi sink cuối đường ghi thành công.

## 10. Giá trị snapshot và dữ liệu mutable

Một trong những lỗi ít được chú ý khi tối ưu là log tham chiếu đến object có thể thay đổi. Ví dụ:

```java
LOG.info("order={}", mutableOrder);
mutableOrder.setStatus("SHIPPED");
```

Nếu backend định dạng tham chiếu muộn hoặc event sử dụng dạng message mutable, dòng log có thể phản ánh trạng thái khác với lúc gọi. Nhiều backend snapshot thông điệp trên thread gửi, nhưng không phải mọi loại message/đối tượng đều bất biến. Log4j 2 đặc biệt lưu ý các dạng `MapMessage`, `StructuredDataMessage` và custom message khi async.

Cách rõ ràng hơn:

```java
String orderIdSnapshot = order.getId();
String statusSnapshot = order.getStatus();
LOG.info("orderId={} status={}", orderIdSnapshot, statusSnapshot);
```

Đây là đoạn tích hợp SLF4J/Log4j, phụ thuộc đối tượng nghiệp vụ. Khi cần log trạng thái chính xác, snapshot bất biến quan trọng hơn việc cố làm mọi dữ liệu lazy.

Với Supplier:

```java
LOG.atDebug()
   .setMessage("state={}")
   .addArgument(() -> mutableOrder.getStatus())
   .log();
```

Hãy xác định **khi nào** `getStatus()` được gọi theo API/backend. Tránh giả định nội dung nó đọc luôn là trạng thái tại thời điểm ứng dụng quyết định phát event. Nếu trạng thái có thể đổi đồng thời hoặc tính nhất quán quan trọng, chụp giá trị đúng lúc và chỉ lazy đối với phần format/chi phí không làm thay đổi ngữ nghĩa.

Trong Java, biến local bị lambda capture phải là final hoặc *effectively final*, nhưng **đối tượng được tham chiếu** vẫn có thể mutable. Điều này dễ gây nhầm lẫn giữa “capture tham chiếu” và “capture snapshot giá trị”.

## 11. Lazy và async logging là hai quyết định khác nhau

**Lazy**: khi nào tính message/đối số?  
**Async**: khi nào worker xử lý/ghi event và thread nào đưa nó ra sink?

```text
Thread ứng dụng
    |
    +-- kiểm tra level/filter sớm
    |
    +-- tạo/capture nội dung event cần thiết
    |
    +-- enqueue nếu backend async
                      |
                      +--> worker -> appender -> format -> file/collector
```

Sơ đồ là khái quát. Một số backend snapshot message/arguments trên thread gọi để bảo đảm dữ liệu; một số layout/encoder có thể format sau. **Không mặc định Supplier sẽ được thực thi trên background worker** chỉ vì appender bất đồng bộ. Kiểm tra API/backend/phiên bản nếu phụ thuộc chi tiết này.

Dù dùng Supplier, async queue vẫn có thể:
- Bị đầy, khiến producer chờ hoặc bỏ event theo chính sách.
- Tăng áp lực heap/GC khi backlog lớn.
- Trễ hoặc mất log khi worker/appender lỗi, shutdown đột ngột.
- Tạo khác biệt giữa tốc độ enqueue và tốc độ sink thực sự ghi.

Tối ưu logging cần nhìn cả tổng thể: mức log, filter, message construction, encoder, appender, queue, file/network và collector. Lazy chủ yếu tác động chi phí **call site** khi log không cần thiết.

### ThreadLocal, MDC và request context

Supplier đọc `ThreadLocal`/MDC ở thời điểm thực thi. Trong ứng dụng đa luồng hoặc virtual thread, cần phân biệt context đang thuộc thread nào và có được propagation khi tạo task mới không. Nhiều backend capture MDC vào event tại call site; vẫn nên dùng test để xác minh với provider và async mode thực tế.

Đặt `requestId`/`traceId` nhỏ, bất biến ở context theo yêu cầu. Không để Supplier đọc các đối tượng request lớn hoặc mutable rồi gắn trực tiếp vào event. Tránh dùng logger làm kênh truyền context nghiệp vụ.

## 12. Side effect, exception và dữ liệu nhạy cảm

Một Supplier chỉ dùng để tạo chuỗi log nên **thuần, nhanh và không làm thay đổi nghiệp vụ**. Ví dụ sai:

```java
logger.fine(() -> "charged=" + chargePayment());
```

Nếu FINE tắt, `chargePayment()` không chạy và nghiệp vụ sai. Nếu FINE bật, logger lại kích hoạt thanh toán. Hãy chạy `chargePayment()` trong nghiệp vụ, nhận kết quả, rồi log giá trị cần thiết.

Một Supplier có thể ném exception khi được gọi. Với level tắt không có lỗi; khi bật, lỗi của phép dựng message có thể đi vào cơ chế xử lý lỗi của backend hoặc ảnh hưởng lời gọi logger. Đừng đặt HTTP call, query DB hoặc thao tác I/O không có timeout chỉ để format log; nếu dữ liệu thực sự cần cho hoạt động nghiệp vụ, tính và xử lý lỗi ở đúng tầng trước khi log.

Lazy message **không phải biện pháp bảo vệ bí mật**:
- Không log password, token, khóa API, cookie phiên, số thẻ, payload riêng tư hay nguyên trạng object nhạy cảm.
- Redact/mask tại nguồn hoặc nơi dữ liệu đi vào event, có chính sách test/retention phù hợp.
- Dùng mã sự kiện và định danh request thay cho thông tin cá nhân.
- Hạn chế kích thước serialization/collection dump; một message lớn vẫn tốn bộ nhớ khi level bật.
- Đối với audit cần độ bền và bằng chứng pháp lý, thiết kế đường ghi bền vững riêng; lazy/async thông thường không bảo đảm delivery.

Đôi khi một chuỗi message chứa dữ liệu nhạy cảm đã được dựng **trước** lời gọi logger rồi bị filter cuối đường. Vì vậy tránh tạo nội dung nhạy cảm ngay cả khi nghĩ nó “chỉ để DEBUG”.

## 13. Cách kiểm thử lazy message

### 13.1. Kiểm tra chính xác số lần tính

Một test tốt đo hành vi rõ ràng thay vì đo nanosecond:
1. Dùng counter tăng trong hàm tạo message.
2. Đặt logger ở mức cao hơn mức test, ví dụ INFO để tắt FINE.
3. Gọi API Supplier và xác nhận counter **0**.
4. Bật level phù hợp, gọi lại, kiểm tra counter tăng khi event được chấp nhận.
5. Gọi phiên bản eager, xác nhận counter vẫn tăng dù level tắt.
6. Nếu cần kiểm tra event đến đích, dùng handler/appender test và kiểm tra thêm filter/queue.

`LazyMessageDemo` ở mục 5 thực hiện một phiên bản độc lập của phép kiểm tra này. Khi chuyển sang JUnit, dùng logger riêng hoặc cấu hình có thể khôi phục trong `finally`; không thay root logger toàn JVM trong nhiều test chạy song song.

### 13.2. Với SLF4J 2.x và Logback

Dùng `ListAppender` (hoặc appender thử nghiệm tương đương):
- DEBUG tắt: gọi `addArgument(() -> expensive())` và kiểm tra bộ đếm không tăng.
- DEBUG bật: kiểm tra level, thông điệp và số lần tính.
- Gọi `.log()`; bỏ `log()` nghĩa là builder chưa phát event.
- Dọn appender, level, MDC và context sau test.
- Với async, chờ event đến sink bằng tín hiệu/timeout thay vì `Thread.sleep` cố định.

### 13.3. Test filter ở nhiều tầng

Đừng chỉ thử mức DEBUG. Test thêm:
- Logger cho phép INFO nhưng appender filter bỏ INFO: Supplier có chạy không?
- Có hai appender với threshold khác nhau: mỗi đích có đúng tập event không?
- Event lớn trên hot path: cấp phát và latency có giảm khi đổi sang Supplier?
- Runtime level thay đổi trong lúc hệ thống chạy: test không dựa vào việc guard bảo đảm event được ghi tuyệt đối.

Các câu trả lời có thể phụ thuộc backend và cấu hình; ghi lại phiên bản để test không vô tình áp đặt hành vi của một triển khai cho tất cả.

## 14. Đo hiệu năng cho đúng

**Không kết luận “lazy nhanh hơn X lần” bằng một ví dụ ít dòng.** Lợi ích phụ thuộc mức log thường tắt hay bật, chi phí chuẩn bị message, tỷ lệ filter, JIT, layout và I/O.

Nên đo:
- Số lần call site log được gọi mỗi giây, tỷ lệ event được bật/loại.
- Thời gian xây message và số lượng object/bytes được cấp phát.
- CPU, GC pause, request throughput và p95/p99 latency.
- Với async: enqueue, queue depth, written/s, dropped/s, flush/shutdown.
- Tải dưới năng lực sink, burst ngắn và quá tải kéo dài.

Với JMH, thử từng cách viết trong trạng thái level tắt và bật, warmup JIT, chạy nhiều lần. Với integration benchmark, giữ cùng backend/provider, cùng sink, payload, level/filter và số event được ghi cuối đường. Không so eager ghi file với lazy event bị loại rồi kết luận backend nhanh hơn.

Ví dụ tính nhẩm: một hàm chẩn đoán tốn **1 ms** được gọi 1.000 lần/giây lúc DEBUG tắt sẽ tốn tổng cộng khoảng **1.000 ms thời gian thực thi của các lần gọi mỗi giây**. Dùng Supplier đúng chỗ có thể tránh số lần tính đó. Đây là minh họa về tổng chi phí lời gọi; không có nghĩa đương nhiên tiết kiệm đúng một CPU core, vì hàm có thể chờ I/O và thời gian thực chạy đồng thời.

### Thứ tự ưu tiên tối ưu

1. Cắt giảm log không cần thiết bằng level/marker/sampling.
2. Tránh nối chuỗi/serialize/đọc DB tại call site khi event có thể bị tắt.
3. Dùng placeholder với đối số rẻ; dùng Supplier hoặc guard cho đối số đắt.
4. Kiểm soát layout, stack trace và location lookup.
5. Xem queue/async, batching và đích xuất khi sink thực sự là nút thắt.
6. Đo lại độ trễ, throughput và mất log; dừng khi chi phí và khả năng quan sát đã phù hợp.

## 15. Lỗi phổ biến và cách sửa

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| `LOG.debug("x=" + expensive())` | Tính toán ngay khi DEBUG tắt | Supplier/guard |
| `LOG.debug("x={}", expensive())` | Placeholder không hoãn `expensive()` | Fluent Supplier/guard |
| `String.format(...)` trước logger | Định dạng sớm | Để logging API format |
| `String x = heavy(); log.fine(() -> x)` | Tính toán đã xảy ra | Đưa hàm `heavy()` vào lambda khi hợp lệ |
| `atDebug().addArgument(...);` thiếu `log()` | Không phát event | Kết thúc fluent builder bằng `log()` |
| Supplier có side effect | Tắt log làm thay đổi nghiệp vụ | Tách logic nghiệp vụ khỏi log |
| Supplier đọc object mutable sau khi state đổi | Event sai thời điểm | Snapshot khi cần tính nhất quán |
| Lọc muộn ở appender nhưng mong không tạo message | Supplier có thể đã chạy | Chọn filter/level sớm |
| Chỉ benchmark DEBUG tắt | Bỏ qua chi phí lúc level bật | Đo cả bật/tắt, sink, async |
| Kết luận log được lưu chỉ vì supplier chạy | Filter/async/I/O vẫn có thể bỏ/lỗi | Xác nhận ở điểm sink phù hợp |

## 16. Bài tập củng cố

1. Chạy `LazyMessageDemo` và giải thích tại sao `after-disabled=0`, `after-enabled=1`, `after-eager=2`.
2. Đổi logger sang `Level.FINE`; dự đoán chính xác số lần gọi Supplier và các dòng log bổ sung.
3. Giữ logger `Level.FINE` nhưng đổi handler sang `Level.WARNING`; xem Supplier chạy nhưng event không đến stdout ra sao.
4. Với SLF4J 1.7, viết guard `isDebugEnabled()` quanh một hàm tạo JSON tốn CPU. Giải thích khác biệt với `LOG.debug("{}", buildJson())`.
5. Với SLF4J 2.x, kiểm tra `atDebug().setMessage("detail={}").addArgument(() -> heavy()).log()` bằng counter khi DEBUG bật/tắt.
6. Với Log4j 2, chạy overload Supplier và đối chiếu hành vi khi đặt filter ở appender; ghi rõ API/backend version.
7. Tạo object mutable, log nó vào async appender rồi thay field; so với log các giá trị snapshot bất biến. Đừng suy rộng kết quả của một backend thành quy tắc mọi backend.
8. Benchmark hot path có 10.000 log calls mỗi giây, đo allocation, CPU, p99 latency và event written/s trước/sau khi dùng Supplier.

## 17. Ghi nhớ

- **Lazy message** trì hoãn tạo thông điệp hoặc một phần đối số tốn kém khi level có thể bị tắt.
- Placeholder `{}` giúp trì hoãn formatting, **không** khiến `heavy()` trong đối số Java tự động lazy.
- JUL có `Supplier<String>`, SLF4J 1.x thường dùng guard, SLF4J 2.x có fluent `addArgument(Supplier)` và Log4j 2 có overload Supplier.
- Lazy theo level không bảo đảm event đến file/collector hoặc không bị appender filter/async queue loại.
- Không đặt side effect, I/O không kiểm soát hay dữ liệu bí mật trong Supplier; dùng snapshot nếu cần log trạng thái chính xác.
- Đo cả khi log tắt lẫn bật, cùng backend và cùng sink trước khi tối ưu hàng loạt.

### Tài liệu tham khảo

- Oracle Java 17 — `java.util.logging.Logger`: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html
- Oracle Java 17 — `System.Logger`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.Logger.html
- SLF4J — *User Manual*, Fluent Logging API: https://www.slf4j.org/manual.html
- SLF4J — *FAQ*: https://www.slf4j.org/faq.html
- Apache Log4j 2 — *Performance* (Supplier và async): https://logging.apache.org/log4j/2.x/manual/performance.html
- Logback — *Architecture*: https://logback.qos.ch/manual/architecture.html
