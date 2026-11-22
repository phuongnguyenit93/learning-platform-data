# Log trong virtual thread (Java 21+)

## 1. Mục tiêu và bối cảnh

**Virtual thread** là một `java.lang.Thread` do JVM quản lý, được chuẩn hóa từ Java 21 (JEP 444). Nó phù hợp với tác vụ có nhiều thời gian chờ I/O, chẳng hạn xử lý HTTP request, gọi dịch vụ và truy vấn cơ sở dữ liệu. Một virtual thread có thể tạm ngừng (unmount) khỏi **carrier thread** (platform thread dùng để thực thi nó) rồi tiếp tục trên carrier khác. Điều này giúp tăng khả năng phục vụ nhiều tác vụ chờ đồng thời, không làm CPU xử lý từng câu lệnh nhanh hơn.

Ghi log trong virtual thread vẫn dùng được `java.util.logging` (JUL), SLF4J + Logback, Log4j 2 hoặc framework tương thích. Điểm cần chú ý nằm ở **danh tính tác vụ**, **ngữ cảnh request**, **thứ tự log** và **chi phí ghi log** khi có rất nhiều virtual thread.

Sau bài này, bạn có thể:
- Ghi log từ virtual thread bằng Java 21+ và kiểm tra `Thread.currentThread().isVirtual()`.
- Gắn `requestId`/`traceId` để nối các log thuộc cùng nghiệp vụ mà không dựa vào carrier.
- Hiểu khi nào MDC/`ThreadLocal` được giữ nguyên và khi nào phải truyền context sang virtual thread mới.
- Phát hiện vấn đề về logging đồng bộ, dữ liệu nhạy cảm, lỗi tác vụ và pinning theo phiên bản JDK.

## 2. Thread nào thực sự xuất hiện trong log?

Trong mã đang chạy trên virtual thread, `Thread.currentThread()` trả về **virtual thread của tác vụ**. Khi JVM unmount rồi mount lại nó trên carrier khác, đối tượng `Thread` và dữ liệu `ThreadLocal` gắn với virtual thread đó vẫn thuộc về cùng một tác vụ.

Phân biệt ba loại thông tin:

| Thông tin | Ý nghĩa | Cách sử dụng trong log |
| --- | --- | --- |
| `Thread.currentThread().getName()` | Tên thread đang chạy code; virtual thread mặc định có thể không có tên | Hữu ích khi chẩn đoán nếu chủ động đặt tên |
| `Thread.currentThread().isVirtual()` | `true` khi code đang chạy trên virtual thread | Dùng để kiểm tra môi trường khi thử nghiệm |
| `requestId`, `traceId`, `spanId` | Định danh request hoặc lần thực thi nghiệp vụ | Dùng để tìm và ghép các log liên quan; ưu tiên trong production |

Không lấy tên/ID **carrier thread** làm định danh request: một carrier có thể phục vụ nhiều virtual thread, và một virtual thread có thể tiếp tục trên carrier khác. Tương tự, ID virtual thread không thay thế cho `requestId` vì một request có thể tạo nhiều tác vụ con.

`Executors.newVirtualThreadPerTaskExecutor()` tạo một **virtual thread mới cho mỗi task**; đây không phải pool tái sử dụng virtual thread. Có thể đặt tên khi tự tạo factory bằng `Thread.ofVirtual().name("req-vt-", 0).factory()`. Tên thread hỗ trợ tìm lỗi, nhưng nên giữ `requestId`/`traceId` trong từng bản ghi log để liên kết nghiệp vụ.

## 3. Ví dụ Java 21+ độc lập: ghi log từ hai virtual thread

Ví dụ chỉ dùng Java Development Kit, không cần dependency bên ngoài. Mỗi task nhận một `requestId` tường minh; `ConsoleHandler` của JUL được cấu hình để in ra thông điệp đơn giản.

Tạo tệp **`VirtualThreadLoggingDemo.java`**:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadFactory;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class VirtualThreadLoggingDemo {
    private static final Logger LOG =
            Logger.getLogger(VirtualThreadLoggingDemo.class.getName());

    static {
        LOG.setUseParentHandlers(false); // Tránh handler mặc định in trùng.
        ConsoleHandler handler = new ConsoleHandler();
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getMessage() + System.lineSeparator();
            }
        });
        LOG.addHandler(handler);
    }

    public static void main(String[] args) throws Exception {
        ThreadFactory factory =
                Thread.ofVirtual().name("req-vt-", 0).factory();

        try (ExecutorService executor =
                     Executors.newThreadPerTaskExecutor(factory)) {
            Future<?> first = executor.submit(() -> handle("req-101"));
            Future<?> second = executor.submit(() -> handle("req-102"));

            // get() đợi và chuyển lỗi của task thành ExecutionException.
            first.get();
            second.get();
        }
    }

    private static void handle(String requestId) {
        Thread current = Thread.currentThread();
        LOG.info(() -> "requestId=" + requestId
                + " thread=" + current.getName()
                + " virtual=" + current.isVirtual()
                + " event=handled");
    }
}
```

Biên dịch và chạy bằng JDK 21 trở lên:

```bash
javac VirtualThreadLoggingDemo.java
java VirtualThreadLoggingDemo
```

**Một kết quả có thể nhận được** (hai dòng có thể đổi chỗ vì hai task chạy đồng thời):

```text
requestId=req-101 thread=req-vt-0 virtual=true event=handled
requestId=req-102 thread=req-vt-1 virtual=true event=handled
```

Giải thích:
1. Factory tạo các virtual thread có tên `req-vt-0`, `req-vt-1`.
2. `executor.submit` khởi chạy hai task; thứ tự hoàn thành hoặc thứ tự ghi log không được bảo đảm.
3. `Future.get()` giúp main chờ và nhận lỗi phát sinh trong task. Khi rời `try`, executor được đóng.
4. `LOG.info(Supplier<String>)` chỉ dựng chuỗi khi mức log tương ứng được bật. Ví dụ tùy biến formatter để dễ đọc; hệ thống thật thường dùng formatter/JSON layout chung, có timestamp và level.

`ConsoleHandler` mặc định ghi ra standard error (stderr); vì vậy khi chuyển hướng stdout và stderr sang hai tệp riêng, bạn sẽ thấy hai dòng trong stderr. Ví dụ minh họa cách gắn context, không phải benchmark.

## 4. Liên kết log theo request: truyền tham số hay dùng MDC?

### 4.1. Truyền context tường minh

Cách đơn giản và dễ kiểm chứng là truyền `requestId`, `traceId` hoặc một đối tượng context bất biến làm tham số xuyên qua các phương thức:

```java
void processOrder(String requestId, String orderId) {
    log.info("requestId={} event=order_started orderId={}",
             requestId, orderId);
    // Gọi các bước nghiệp vụ, tiếp tục chuyển requestId nếu cần.
}
```

Đoạn trên minh họa **SLF4J**, cần logger `org.slf4j.Logger` và backend tương ứng; nó không phải chương trình độc lập. Placeholder `{}` là cơ chế parameterized logging của SLF4J, giúp tránh ghép chuỗi sớm không cần thiết. Trong hệ thống có nhiều lớp, việc truyền context bằng tham số rõ ràng nhưng có thể làm danh sách tham số dài.

### 4.2. MDC gắn dữ liệu theo thread

**Mapped Diagnostic Context (MDC)** cho phép đặt khóa/giá trị như `requestId`, `traceId` và cho layout log in chúng cùng thông điệp. Với SLF4J/Logback, API thường dùng là `MDC.put`, `MDC.getCopyOfContextMap`, `MDC.setContextMap` và `MDC.clear`. Chẳng hạn cấu hình Logback có thể dùng `%X{requestId}` trong pattern; JSON layout có thể đặt trường `requestId` riêng.

Điều quan trọng là phân biệt:
- **Cùng một virtual thread:** context dựa trên `ThreadLocal` vẫn gắn với virtual thread sau khi nó unmount/remount; JVM chuyển carrier không có nghĩa MDC tự mất.
- **Tạo một virtual thread mới hoặc chuyển task sang executor:** không mặc định giả định MDC của thread gọi sẽ xuất hiện ở thread mới. Cơ chế truyền context phụ thuộc MDC adapter/framework và cấu hình; nên chủ động chụp và khôi phục context.
- **Kết thúc scope:** phải dọn hoặc khôi phục MDC để tránh giữ dữ liệu quá lâu, sai ngữ cảnh trong code tái sử dụng và chiếm bộ nhớ không cần thiết.

Ví dụ helper truyền MDC qua ranh giới executor (dùng **SLF4J 2.x**, có `org.slf4j.MDC`; đây là đoạn phương thức tích hợp vào ứng dụng đã cấu hình SLF4J):

```java
import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Future;
import org.slf4j.MDC;

static <T> Future<T> submitWithMdc(
        ExecutorService executor, Callable<T> task) {

    // Chụp context ở thread gọi, trước khi submit.
    Map<String, String> captured = MDC.getCopyOfContextMap();

    return executor.submit(() -> {
        Map<String, String> previous = MDC.getCopyOfContextMap();
        try {
            if (captured == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(captured);
            }
            return task.call();
        } finally {
            // Khôi phục context của thread thực thi, kể cả khi task ném lỗi.
            if (previous == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(previous);
            }
        }
    });
}
```

Cách dùng có thể là: ở đầu request gọi `MDC.put("requestId", requestId)`; gọi `submitWithMdc(executor, task)`; sau khi chờ `Future.get()`, dùng `finally` để `MDC.remove("requestId")` (hoặc khôi phục context cũ nếu đang ở scope lồng nhau). Đây là **truyền context thủ công**. Nếu dùng web framework, OpenTelemetry hoặc thư viện context-propagation, kiểm tra cơ chế và phiên bản của chúng để tránh truyền hai lần, bỏ sót nhánh async hoặc tạo trace sai.

Trong hệ thống số lượng virtual thread rất lớn, chỉ giữ vài khóa MDC nhỏ, cần thiết. Tránh cất object lớn, cache kết nối, entity hoặc payload request vào `ThreadLocal`: mỗi virtual thread có không gian riêng và số lượng thread có thể rất cao. Nếu không cần MDC, truyền một context bất biến bằng tham số thường dễ kiểm soát bộ nhớ và vòng đời hơn.

## 5. Ghi log đúng khi có lỗi và khi chạy đồng thời

### Không nhầm thứ tự dòng log với thứ tự nghiệp vụ

Hai task có thể chạy song song; không thể suy luận `req-101` đã hoàn tất trước `req-102` chỉ từ thứ tự các dòng. Thời điểm ghi log, thời điểm event xảy ra và thời điểm đẩy đến hệ thống tập trung có thể khác nhau, nhất là với appender async.

Để dựng lại luồng sự kiện:
- Ghi `timestamp`, `level`, `logger`, `service`, `event` và `requestId`/`traceId` nhất quán.
- Thêm `durationMs` cho bước cần đo, `spanId` nếu có tracing, và mã lỗi ổn định.
- Khi so sánh thời gian giữa nhiều máy, dùng đồng hồ được đồng bộ; không tin chỉ vào thứ tự xuất hiện trên console hay hệ thống thu thập log.

### Bảo toàn exception

Không chỉ ghi `e.getMessage()` hoặc `e.toString()` khi cần chẩn đoán stack trace. Với JUL, chuyển exception làm tham số throwable:

```java
try {
    performWork();
} catch (Exception ex) {
    LOG.log(java.util.logging.Level.SEVERE,
            "requestId=req-101 event=work_failed", ex);
    throw ex;
}
```

`performWork()` là phương thức nghiệp vụ giả định, vì vậy đây là **đoạn minh họa**, không phải chương trình độc lập. Với SLF4J, cách tương ứng là `log.error("requestId={} event=work_failed", requestId, ex)`. Nếu dùng `executor.submit`, exception nằm trong `Future`; gọi `get()` hoặc cơ chế xử lý kết quả tương đương để không đánh mất lỗi. Với `Thread.ofVirtual().start(...)`, lỗi chưa bắt được đi qua `UncaughtExceptionHandler` như quy tắc thread thông thường.

### An toàn dữ liệu

Không ghi password, access token, cookie phiên, khóa API, thông tin thanh toán hay toàn bộ request body vào log. Khi có dữ liệu cá nhân, áp dụng redaction theo chính sách của hệ thống. Dùng định danh đủ để liên hệ log và trace; tránh dùng dữ liệu nhạy cảm làm tên virtual thread.

## 6. Hiệu năng: virtual thread rẻ không có nghĩa log rẻ

Tạo được rất nhiều virtual thread **không** làm thao tác format chuỗi, khóa appender, ghi file, console, mạng hoặc ingestion trở nên miễn phí. Nút thắt thường nằm ở lượng bản ghi và hệ thống nhận log.

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Throughput giảm khi bật DEBUG | Tạo/format quá nhiều thông điệp; I/O tăng | Giảm mức log, dùng parameterized/lazy logging, đo lại |
| Nhiều thread chờ ghi console/file | Appender hoặc đích I/O bị tranh chấp/khóa | Kiểm tra backend, batching/async appender phù hợp, giảm log trên hot path |
| Heap tăng khi lưu context | MDC/`ThreadLocal` giữ dữ liệu lớn trên rất nhiều virtual thread | Giữ context nhỏ, xóa ở `finally`, giới hạn độ lớn payload |
| Log bị mất khi tải tăng | Hàng đợi async đầy, chính sách drop/overwrite hoặc shutdown quá sớm | Theo dõi queue/drop metrics, cấu hình backpressure và flush khi dừng |
| Thiếu `requestId` trong một task con | Context không được chuyển qua ranh giới executor | Truyền tham số hoặc snapshot/restore MDC |
| Dòng log không theo thứ tự gọi `submit` | Scheduler và appender có đồng thời | Ghép theo ID/event/timestamp; không dựa vào thứ tự hiển thị |

**Synchronous logging** dễ hiểu nhưng có thể khiến task đợi lock hoặc I/O. **Asynchronous logging** giảm thời gian chờ ở luồng nghiệp vụ trong một số tình huống, nhưng tạo hàng đợi, thêm độ trễ và rủi ro mất log khi quá tải hoặc process dừng đột ngột. Cần định nghĩa rõ xử lý khi queue đầy, mức log bắt buộc và cơ chế flush/shutdown; đo bằng workload thật trước khi chọn.

Đừng tạo fixed pool nhỏ của virtual thread chỉ để giới hạn log hay số request: mỗi task nên có virtual thread của nó. Nếu cần chặn mức đồng thời truy cập một tài nguyên có giới hạn, sử dụng cơ chế như `Semaphore` hoặc giới hạn ở chính tài nguyên đó, và theo dõi thời gian chờ.

### Pinning phụ thuộc phiên bản JDK

Trên **JDK 21–23**, virtual thread có thể bị *pin* vào carrier khi chặn trong `synchronized` hoặc native/foreign code; nếu thao tác logging gây chờ lâu trong vùng như vậy, khả năng mở rộng có thể giảm. **JDK 24** (JEP 491) đã thay đổi việc đồng bộ để loại bỏ phần lớn pinning do `synchronized`; các trường hợp native/foreign vẫn cần đánh giá. Không quy mọi độ trễ log thành pinning và không áp dụng máy móc chẩn đoán JDK 21 cho JDK mới.

Có thể dùng Java Flight Recorder (JFR), thread dump và chỉ số latency/queue của appender để tìm nguyên nhân. Với JDK 21, sự kiện `jdk.VirtualThreadPinned` hỗ trợ tìm các lần pinning vượt ngưỡng cấu hình; trên JDK khác, kiểm tra sự kiện mà phiên bản đó hỗ trợ. Giám sát cả thời gian ghi log, tốc độ sinh log, tỷ lệ drop và mức sử dụng CPU/heap.

## 7. Lỗi thường gặp và cách tự kiểm tra

1. **Log trống cột thread:** virtual thread tạo mặc định có thể có tên rỗng. Đặt tên có giới hạn khi thật sự cần debug; luôn có `requestId`/`traceId`.
2. **Cho rằng MDC tự đi theo mọi task con:** `ThreadLocal` thuộc về từng thread, không phải toàn bộ request. Kiểm tra chỗ `submit`, callback và executor.
3. **Đưa cả request vào `ThreadLocal` để khỏi truyền tham số:** dễ giữ dữ liệu lớn khi có hàng chục nghìn tác vụ. Chỉ giữ các khóa gọn, dọn scope.
4. **Dùng `System.out.println` thay logger ở production:** thiếu level, cấu trúc, cấu hình và có thể gây tranh chấp console.
5. **Ghi log bằng carrier ID:** carrier là chi tiết thực thi, không định danh một nghiệp vụ.
6. **Không lấy `Future.get()`:** task có thể ném exception nhưng luồng gọi không kiểm tra kết quả.
7. **Tăng DEBUG toàn hệ thống rồi kết luận virtual thread chậm:** cần đo riêng chi phí sinh/ghi log và so với baseline.

**Bài thực hành:** chạy ví dụ ở mục 3 nhiều lần để quan sát thứ tự dòng log; bỏ `.name("req-vt-", 0)` để xem tên thread mặc định; thêm tác vụ thứ ba và truyền `requestId` riêng; cuối cùng chuyển cấu hình sang structured JSON log hoặc Logback MDC và xác minh mỗi dòng đều có ID của tác vụ. Khi chuyển từ JUL sang SLF4J, giữ nguyên ý tưởng nghiệp vụ nhưng thay API logger và cấu hình backend cho đúng.

## 8. Ghi nhớ

- Virtual thread là `Thread` thực sự đối với code logging; `Thread.currentThread()` vẫn chỉ ra đúng virtual thread sau khi JVM đổi carrier.
- Ưu tiên định danh nghiệp vụ (`requestId`, `traceId`) hơn tên hoặc ID thread.
- MDC/`ThreadLocal` có thể tồn tại qua một lần virtual thread park/unpark; khi tạo thread khác phải xử lý truyền context rõ ràng.
- Nhiều virtual thread có thể tạo ra lượng log rất lớn. Thiết kế level, format, queue, backpressure và bảo mật như các tài nguyên có giới hạn.
- Với vấn đề pinning, xem **đúng phiên bản JDK** và số liệu JFR/appender trước khi kết luận.

### Tài liệu tham khảo

- Oracle, *Virtual Threads* (Java 21): https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html
- OpenJDK, *JEP 444: Virtual Threads*: https://openjdk.org/jeps/444
- OpenJDK, *JEP 491: Synchronize Virtual Threads without Pinning*: https://openjdk.org/jeps/491
- SLF4J, *MDC API*: https://www.slf4j.org/api/org/slf4j/MDC.html
- SLF4J, *User Manual*: https://www.slf4j.org/manual.html
