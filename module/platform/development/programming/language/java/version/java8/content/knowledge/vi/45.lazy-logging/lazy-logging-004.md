# Giữ Supplier không có tác dụng phụ khi logging theo nhu cầu (Java 8+)

Trong logging theo nhu cầu (*lazy logging*), ứng dụng truyền một `Supplier<String>` để logger chỉ tạo nội dung thông điệp khi cấp độ log đang được bật. Java 8 đã bổ sung các overload nhận Supplier cho `java.util.logging.Logger`, nhờ đó có thể trì hoãn việc ghép chuỗi hoặc tính toán thông tin chẩn đoán đắt tiền.

Nguyên tắc của bài này: **Supplier chỉ tạo thông điệp log; không thực hiện công việc nghiệp vụ hoặc làm thay đổi trạng thái của ứng dụng.** Đây là quy tắc thiết kế, không phải điều mà compiler hay interface `Supplier` tự động cưỡng chế.

Khi Supplier không có tác dụng phụ, bật/tắt FINE hoặc DEBUG chỉ làm thay đổi chi phí và nội dung logging. Nó không làm thay đổi dữ liệu, metric, event hay kết quả request. Bài học tập trung vào API Java còn được hỗ trợ, dùng `java.util.logging` có từ Java 8.

## 1. Supplier trong lazy logging là gì?

`Supplier<T>` là functional interface trong `java.util.function` với method `T get()`. Với log message, kiểu thường dùng là `Supplier<String>`: một hàm không nhận tham số và trả về chuỗi khi được gọi.

~~~java
Supplier<String> message = () -> "request completed";
String text = message.get();
~~~

Nếu truyền Supplier cho logger, logger có thể trì hoãn việc gọi `get()` cho tới khi level tương ứng được bật:

~~~java
Logger logger = Logger.getLogger(OrderService.class.getName());

logger.fine(() -> "orderId=" + orderId + ", state=" + state);
~~~

Các overload nhận Supplier trong `java.util.logging.Logger` gồm `fine(Supplier<String>)`, `finer(...)`, `finest(...)`, `info(...)`, `warning(...)`, `severe(...)` và `log(Level, Supplier<String>)`. Chúng có từ **Java 8**. Cũng có overload `log(Level, Throwable, Supplier<String>)` để gắn exception với message được tạo lười.

Nếu `FINE` đang tắt, logger không cần tạo message. Nếu `FINE` đang bật, logger gọi Supplier để lấy nội dung. Đây là cách giảm chi phí format các thông điệp chỉ phục vụ chẩn đoán.

## 2. Eager logging và lazy logging

### Eager: tạo chuỗi trước khi logger kiểm tra level

~~~java
logger.fine("state=" + buildDiagnosticState());
~~~

Java đánh giá biểu thức nối chuỗi trước khi gọi `fine(String)`. Ngay cả khi `FINE` đang tắt, `buildDiagnosticState()` vẫn chạy và chuỗi vẫn được tạo.

Nếu method duyệt collection lớn, tính toán nhiều hoặc tạo một cấu trúc text dài, ứng dụng đã trả chi phí dù thông điệp không được ghi.

### Lazy: trì hoãn tạo message

~~~java
logger.fine(() -> "state=" + buildDiagnosticState());
~~~

Logger nhận Supplier và chỉ yêu cầu chuỗi khi level cho phép. Đây là cách thích hợp nếu `buildDiagnosticState()` chỉ tạo dữ liệu chẩn đoán, không thay đổi trạng thái và có thể bỏ qua an toàn.

**Supplier chỉ trì hoãn việc gọi hàm; nó không biến hàm có side effect thành hàm an toàn.** Nếu `buildDiagnosticState()` ghi database hoặc cập nhật trạng thái, đặt nó trong lambda vẫn là thiết kế sai.

Method reference cũng dùng được:

~~~java
logger.log(Level.FINER, this::buildDiagnosticMessage);
~~~

Method `buildDiagnosticMessage()` phải trả `String` và không nhận tham số. Cú pháp ngắn hơn nhưng vẫn phải tuân thủ cùng nguyên tắc.

## 3. Vì sao Supplier phải không có tác dụng phụ?

Giả sử ứng dụng cần tăng bộ đếm đã xử lý:

~~~java
logger.fine(() -> {
    metrics.incrementProcessed();
    return "processed=" + metrics.processedCount();
});
~~~

Đoạn này sai về thiết kế. Khi `FINE` tắt, Supplier không được gọi và `incrementProcessed()` cũng không chạy. Chỉ cần thay đổi cấu hình logging, metric và trạng thái quan sát của ứng dụng đã thay đổi.

Cách đúng:

~~~java
metrics.incrementProcessed(); // Công việc bắt buộc, độc lập với logging.

long processedSnapshot = metrics.processedCount();
logger.fine(() -> "processed=" + processedSnapshot);
~~~

Việc cập nhật metric diễn ra trong luồng nghiệp vụ. Supplier chỉ định dạng một snapshot đã có.

Không đặt các thao tác sau vào Supplier:

- Cập nhật object, collection hoặc biến dùng cho nghiệp vụ.
- Tăng/giảm counter, metric hoặc phát event bắt buộc.
- Ghi database, gửi HTTP request, publish message hoặc gọi service bên ngoài.
- Đọc rồi xóa file, đóng tài nguyên, giải phóng lock hoặc thay đổi cấu hình.
- Sinh ID/token mà luồng nghiệp vụ cần dùng ở nơi khác.
- Gọi method có thể thay đổi trạng thái dùng chung hoặc phụ thuộc thứ tự thực thi.

Supplier có thể thực hiện **tính toán thuần để tạo chuỗi**: nối các giá trị bất biến, chuyển số sang text hoặc format một snapshot đã có. Không dùng nó làm nơi chạy business logic.

### Side effect không phải lúc nào cũng rõ ràng

Một method có tên `toString()` hoặc `buildMessage()` vẫn có thể truy cập database, cập nhật cache hoặc thay đổi state nếu implementation được viết không tốt. Khi đưa method vào lambda, hãy xem xét hành vi thực tế của nó, không chỉ tên method.

## 4. Level check không phải điều kiện nghiệp vụ

`java.util.logging.Logger` kiểm tra level hiệu lực. Nếu level của request thấp hơn ngưỡng đang bật, logging call kết thúc sớm. Vì vậy, Supplier không được xem là nơi thực hiện công việc phải chạy.

~~~java
logger.setLevel(Level.INFO);

logger.fine(() -> buildDebugMessage()); // FINE bị tắt: Supplier không chạy.
logger.info(() -> buildInfoMessage());  // INFO được bật: Supplier được gọi.
~~~

Level có thể được cấu hình hoặc thay đổi trong runtime. Nếu một cập nhật nghiệp vụ chỉ xảy ra bên trong Supplier, kết quả ứng dụng sẽ phụ thuộc cấu hình logging — lỗi thiết kế rất khó phát hiện trong môi trường production.

Không viết:

~~~java
logger.fine(() -> {
    if (shouldPersist()) {
        repository.save(result);
    }
    return "saved";
});
~~~

Hãy thực hiện quyết định và thao tác lưu ở luồng nghiệp vụ, rồi log kết quả đã xác định:

~~~java
if (shouldPersist) {
    repository.save(result);
}

logger.fine(() -> "persisted=" + persistedSnapshot);
~~~

Logging level chỉ quyết định việc tạo thông điệp, không quyết định nghiệp vụ có xảy ra hay không.

## 5. Filter có thể loại log sau khi Supplier đã chạy

Không đồng nhất hai việc:

1. Supplier đã được gọi để xây message.
2. Log record cuối cùng đã được publish ra Handler hoặc sink.

Theo hợp đồng `Logger`, quá trình logging kiểm tra level trước, sau đó mới tạo `LogRecord` và gọi `Filter` nếu có. Vì vậy:

- Level tắt: Supplier không được gọi theo cơ chế lazy.
- Level bật nhưng Filter từ chối: Supplier có thể đã chạy, nhưng record không được publish.
- Level bật và Filter chấp nhận: record được chuyển tới Handler theo cấu hình.

Ví dụ:

~~~java
logger.setLevel(Level.FINE);
logger.setFilter(record -> false);

logger.fine(() -> buildDebugMessage());
~~~

Ở đây `FINE` đã qua bước kiểm tra level. Supplier được gọi để tạo message; sau đó Filter từ chối record.

Do đó không viết Supplier với giả định “nếu lambda chạy thì log chắc chắn đã được ghi”. Supplier cần không có tác dụng phụ ngay cả khi Filter có thể loại record. Việc Supplier đã chạy không phải bằng chứng rằng một thao tác nghiệp vụ đã hoàn tất hoặc một log đã tới sink.

## 6. Capture snapshot thay vì đọc object mutable

Lambda có thể capture biến cục bộ hoặc tham chiếu object. Biến cục bộ được capture phải là final hoặc effectively final, nhưng **object được tham chiếu vẫn có thể mutable**.

Ví dụ an toàn:

~~~java
final String requestId = request.getId();
final String statusSnapshot = order.getStatus().name();

logger.fine(() ->
        "requestId=" + requestId + ", status=" + statusSnapshot);
~~~

Supplier chỉ dùng các giá trị String đã chụp; nó không đọc lại object đang thay đổi.

Ví dụ cần thận trọng:

~~~java
logger.fine(() -> "order=" + mutableOrder);
~~~

Nếu thread khác sửa `mutableOrder` đồng thời, nội dung log có thể phản ánh trạng thái ở một thời điểm khác. Method `toString()` của object cũng có thể tốn kém, truy cập dữ liệu hoặc có side effect.

Với state dùng chung, hãy lấy snapshot theo cơ chế đồng bộ hoặc immutable phù hợp trước khi logging. Supplier chỉ nên format snapshot đó.

### Logger thread-safe không làm Supplier tự thread-safe

Tài liệu Java mô tả các method của `Logger` là multi-thread safe. Điều này bảo vệ thao tác logging của Logger; **không tự biến code bên trong lambda thành thread-safe**. Nếu Supplier đọc một collection mutable trong lúc thread khác cập nhật, ứng dụng vẫn cần snapshot hoặc đồng bộ thích hợp.

## 7. Không dùng Supplier làm nơi thực hiện I/O

Lazy logging thường được dùng để tránh format chuỗi đắt tiền. Tuy vậy, đặt I/O vào Supplier khiến latency và tải hệ thống thay đổi theo cấu hình log:

~~~java
// Không nên: khi FINE bật, thao tác này có thể đọc database.
logger.fine(() -> repository.loadFullOrder(orderId).toString());
~~~

Nếu cần thông tin từ database, hãy lấy nó trong luồng nghiệp vụ khi thật sự cần; sau đó truyền snapshot vào Supplier:

~~~java
OrderSnapshot snapshot = orderService.loadSnapshot(orderId);

logger.fine(() -> "order=" + snapshot);
~~~

Ví dụ giả định `OrderSnapshot` là kiểu dữ liệu do ứng dụng định nghĩa và có biểu diễn chuỗi an toàn. Nếu snapshot chỉ được tạo để logging, hãy cân nhắc chi phí trước khi tải nó.

Supplier có thể thực hiện phép tính CPU tương đối nặng nếu đó là phép tính chẩn đoán có thể bỏ qua khi level tắt, không làm thay đổi trạng thái và không gây lỗi nghiệp vụ. Vẫn cần giới hạn kích thước dữ liệu và tránh giữ tài nguyên lâu.

## 8. Counter, metric và random

### Counter nghiệp vụ

~~~java
// Sai: counter phụ thuộc log level.
logger.fine(() -> "processed=" + processedCounter.incrementAndGet());
~~~

Cách đúng:

~~~java
long current = processedCounter.incrementAndGet();
logger.fine(() -> "processed=" + current);
~~~

Counter tăng theo luồng nghiệp vụ; Supplier chỉ đọc giá trị đã có.

### Metric quan sát

~~~java
metrics.increment("cache.miss");
logger.fine(() -> "cache miss; size=" + cacheSizeSnapshot);
~~~

Nếu metric đếm số lần code đi qua một nhánh, cập nhật nó độc lập với logging. Không dùng Supplier làm cơ chế thu thập metric.

### Random hoặc ID

~~~java
// Không nên nếu ID này còn được dùng ở nơi khác.
logger.fine(() -> "traceId=" + UUID.randomUUID());
~~~

Nếu ID phải gắn với request, hãy tạo ID một lần trong luồng request rồi capture nó. Đừng để việc bật/tắt log quyết định ID có được tạo hay không.

## 9. Hợp đồng Supplier và giới hạn của việc dựa vào số lần gọi

`Supplier<T>` là interface cung cấp kết quả qua `get()`. Javadoc nêu rõ **không có yêu cầu mỗi lần gọi phải trả một kết quả mới hoặc khác biệt**. Interface này không phải công cụ đồng bộ, không tự bảo đảm purity và cũng không bảo đảm side effect của ứng dụng được thực hiện đúng số lần.

Với `java.util.logging.Logger`:

- Các overload nhận Supplier có từ Java 8.
- Logger gọi Supplier để tạo message khi level tương ứng đang bật.
- Level có thể được cấu hình hoặc thay đổi.
- Filter có thể từ chối record sau khi level đã được chấp nhận.
- Interface Supplier không yêu cầu mỗi lần `get()` trả về một kết quả mới.

Vì vậy hãy viết Supplier sao cho việc gọi hay không gọi nó không ảnh hưởng trạng thái nghiệp vụ. Một phép format thuần có thể được gọi mà không gây tác động; một lệnh cập nhật dữ liệu thì không.

Không dựa vào số lần Supplier được gọi như một phần logic ứng dụng. Để kiểm tra hành vi lazy trong unit test, có thể dùng một counter test riêng, nhưng không biến counter đó thành metric production.

## 10. Chọn overload phù hợp trong `java.util.logging`

Các overload hiện hành:

~~~java
Logger logger = Logger.getLogger(MyService.class.getName());

logger.fine(() -> buildFineMessage());
logger.finer(() -> buildFinerMessage());
logger.finest(() -> buildFinestMessage());

logger.log(Level.CONFIG, () -> buildConfigMessage());
logger.log(Level.INFO, () -> buildInfoMessage());
logger.log(Level.WARNING, () -> buildWarningMessage());
~~~

Chọn level theo ý nghĩa vận hành. Không dùng `SEVERE` chỉ để ép Supplier được gọi.

Nếu cần log exception kèm message lazy, Java 8 có overload:

~~~java
logger.log(Level.WARNING, exception,
        () -> "failed to load orderId=" + orderIdSnapshot);
~~~

Throwable được lưu riêng trong `LogRecord` để Formatter xử lý stack trace. Không cần tự ghép stack trace thành chuỗi trong Supplier khi logger đã có overload lưu Throwable.

### Message rẻ và message đắt

Với một chuỗi hằng:

~~~java
logger.fine("cache lookup started");
~~~

Không cần tạo Supplier cho mọi message nhỏ. Dùng Supplier khi việc tạo message có chi phí đáng kể và có thể bỏ qua nếu level tắt.

JUL cũng có overload message template:

~~~java
logger.log(Level.FINE, "orderId={0}, status={1}",
        new Object[] {orderId, status});
~~~

JUL thường dùng quy tắc format kiểu `MessageFormat` với placeholder `{0}`, `{1}`. Không nhầm cú pháp `{}` của một số logging framework khác với placeholder JUL.

## 11. `isLoggable` và kiểm tra thủ công

`Logger.isLoggable(Level)` cho biết level có được logger cho phép theo cấu hình hiệu lực hay không:

~~~java
if (logger.isLoggable(Level.FINE)) {
    String detail = buildDiagnosticMessage();
    logger.fine(detail);
}
~~~

Cách này hữu ích khi một đoạn chuẩn bị phức tạp được dùng cho nhiều lệnh log. Nếu chỉ cần tạo một message, overload Supplier thường ngắn và rõ hơn:

~~~java
logger.fine(() -> buildDiagnosticMessage());
~~~

Không đặt side effect vào nhánh `isLoggable` rồi coi việc kiểm tra level là một phần nghiệp vụ. Nếu cấu hình thay đổi giữa lần kiểm tra và lần ghi, message có thể đã được tính nhưng record cuối vẫn bị bỏ. Với phép tính thuần, đây chỉ là chi phí dư; với side effect, đó là lỗi thiết kế.

## 12. Ngoại lệ bên trong Supplier

Supplier của `Logger` trả `String` và không khai báo checked exception. Không nên đặt thao tác I/O có thể ném `IOException` vào lambda rồi dùng nó làm nơi xử lý lỗi nghiệp vụ.

~~~java
// Không nên: logging call trở thành nơi kích hoạt việc đọc file.
logger.fine(() -> readDiagnosticFile(path));
~~~

Việc đọc file cần policy lỗi, timeout và đóng resource riêng. Hãy thực hiện nó ở luồng nghiệp vụ nếu thực sự cần, sau đó truyền kết quả an toàn cho Supplier để format.

Nếu method tạo message có thể ném unchecked exception, hãy bảo đảm đó thực sự là lỗi format mà ứng dụng chấp nhận. Không dùng Supplier để nuốt lỗi rồi trả chuỗi giả khiến log sai sự thật.

## 13. Chương trình Java hoàn chỉnh: kiểm tra lazy evaluation và Filter

Tạo file **`LazyLoggingSupplierDemo.java`**. Chương trình dùng `java.util.logging` và một Handler trong bộ nhớ để quan sát kết quả mà không ghi log ra console. Nó minh họa ba tình huống:

1. Level `FINE` bị tắt: Supplier không được gọi.
2. Level `FINE` được bật nhưng Filter từ chối record: Supplier vẫn đã được gọi, nhưng record không được capture.
3. Level `INFO` được bật và Filter đã bỏ: Supplier được gọi, message được capture.

`AtomicInteger` trong Supplier ở chương trình này chỉ là **test instrumentation** để đếm số lần được gọi. Đây không phải mẫu code production; Supplier trong ứng dụng nên chỉ format snapshot và không tăng counter.

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Filter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LazyLoggingSupplierDemo {
    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    private static final class MemoryHandler extends Handler {
        private final List<String> messages = new ArrayList<>();

        @Override
        public synchronized void publish(LogRecord record) {
            if (isLoggable(record)) {
                messages.add(record.getLevel().getName() + ": " + record.getMessage());
            }
        }

        @Override public void flush() {}
        @Override public void close() {}

        synchronized List<String> messages() {
            return new ArrayList<>(messages);
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.lazy.supplier");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        MemoryHandler handler = new MemoryHandler();
        handler.setLevel(Level.ALL);
        logger.addHandler(handler);

        AtomicInteger supplierCalls = new AtomicInteger();

        boolean fineDisabled = !logger.isLoggable(Level.FINE);
        System.out.println("FINE enabled: " + !fineDisabled);
        logger.fine(() -> {
            supplierCalls.incrementAndGet(); // Test instrumentation only.
            return "debug details";
        });
        System.out.println("supplier calls after disabled FINE: " + supplierCalls.get());
        check(fineDisabled && supplierCalls.get() == 0, "disabled level is lazy");

        logger.setLevel(Level.FINE);
        Filter rejectFine = record -> record.getLevel() != Level.FINE;
        logger.setFilter(rejectFine);
        boolean fineEnabledBeforeFilter = logger.isLoggable(Level.FINE);
        System.out.println("FINE enabled before filter: " + fineEnabledBeforeFilter);
        logger.fine(() -> {
            supplierCalls.incrementAndGet(); // Test instrumentation only.
            return "filtered debug details";
        });
        System.out.println("supplier calls after filtered FINE: " + supplierCalls.get());
        System.out.println("captured after filtered FINE: " + handler.messages());
        check(fineEnabledBeforeFilter, "FINE passes level gate");
        check(supplierCalls.get() == 1, "supplier runs before filter");
        check(handler.messages().isEmpty(), "filter rejects record");

        logger.setFilter(null);
        logger.setLevel(Level.INFO);
        final String requestId = "req-42";
        final String status = "READY";
        logger.info(() -> {
            supplierCalls.incrementAndGet(); // Test instrumentation only.
            return "requestId=" + requestId + ", status=" + status;
        });

        System.out.println("supplier calls after INFO: " + supplierCalls.get());
        System.out.println("captured records: " + handler.messages());
        check(supplierCalls.get() == 2, "enabled level invokes supplier");
        check(handler.messages().equals(Collections.singletonList(
                "INFO: requestId=req-42, status=READY")), "published message");

        logger.removeHandler(handler);
        handler.close();
        System.out.println("all checks passed");
    }
}
~~~

Biên dịch và chạy trên JDK 17:

~~~bash
javac --release 17 -encoding UTF-8 LazyLoggingSupplierDemo.java
java LazyLoggingSupplierDemo
~~~

**Stdout đầy đủ đã kiểm thử:**

~~~text
FINE enabled: false
supplier calls after disabled FINE: 0
FINE enabled before filter: true
supplier calls after filtered FINE: 1
captured after filtered FINE: []
supplier calls after INFO: 2
captured records: [INFO: requestId=req-42, status=READY]
all checks passed
~~~

### Phân tích kết quả

- Khi `FINE` bị tắt, logger bỏ qua logging request và bộ đếm test vẫn bằng 0.
- Khi `FINE` được bật, Supplier chạy. Filter sau đó từ chối record nên danh sách capture vẫn rỗng.
- Khi `INFO` được bật và Filter được gỡ, Supplier chạy và Handler nhận message `INFO`.
- Sáu phép `check` xác nhận level gate, việc gọi Supplier trước Filter và message cuối cùng.
- Dòng `all checks passed` chỉ xuất hiện khi mọi kiểm tra đều thành công.

Chương trình dùng side effect trong Supplier **chỉ để đo hành vi lazy**. Trong mã ứng dụng thật, bỏ bộ đếm này và dùng Supplier thuần như `() -> "requestId=" + requestId`.

## 14. Những lỗi thường gặp

| Sai lầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| Tăng metric bên trong Supplier | Metric biến mất khi log level tắt | Tăng metric ngoài logging |
| Cập nhật DB trong Supplier | Dữ liệu thay đổi theo cấu hình log | Thực hiện nghiệp vụ riêng |
| Gửi HTTP/publish event từ Supplier | Logging gây I/O và side effect | Gửi event ở luồng nghiệp vụ |
| Sinh ID cần cho request trong Supplier | ID có thể không được tạo khi level tắt | Tạo ID một lần rồi capture |
| Cho rằng Supplier luôn chạy | Level có thể tắt | Không phụ thuộc Supplier cho nghiệp vụ |
| Cho rằng Supplier chạy nghĩa là log chắc chắn xuất hiện | Filter có thể loại record sau level check | Tách tạo message khỏi publish |
| Đặt hàm đắt tiền nhưng có side effect vào lambda | Lazy không làm nó thuần | Chuyển side effect ra ngoài |
| Capture object mutable rồi gọi toString | Có thể thấy state không nhất quán | Capture immutable snapshot |
| Dùng shared counter trong Supplier | Race/side effect | Cập nhật counter độc lập |
| Cho rằng Logger thread-safe thì lambda cũng thread-safe | Code Supplier do ứng dụng kiểm soát | Đồng bộ/snapshot state |
| Tạo chuỗi eager trước khi gọi logger | Vẫn tốn CPU/RAM khi level tắt | Truyền Supplier |
| Dùng Supplier cho mọi chuỗi hằng | Tăng độ phức tạp không cần thiết | Dùng String trực tiếp cho message rẻ |
| Dùng isLoggable như điều kiện nghiệp vụ | Cấu hình log không phải business rule | Dùng điều kiện nghiệp vụ riêng |
| Đọc file/network trong Supplier | Latency và lỗi I/O phụ thuộc log level | Đọc theo luồng nghiệp vụ, log snapshot |
| Nuốt exception trong Supplier | Log có thể báo sai trạng thái | Xử lý lỗi theo policy thật |
| Dựa vào số lần Supplier được gọi | Không phải hợp đồng nghiệp vụ | Supplier không side effect, không dựa call count |
| Coi Filter và level gate là một | Filter chạy sau level check | Hiểu thứ tự pipeline logging |
| Trộn cú pháp placeholder của framework khác | JUL dùng MessageFormat-style parameters | Dùng {0}, {1} với JUL |

## 15. Bài tập tự luyện có đáp án

### Bài 1 — Level FINE đang tắt

`logger.fine(() -> buildMessage())` được gọi khi FINE bị tắt. `buildMessage()` có chạy không?

**Đáp án:** Không theo lazy Supplier contract của `java.util.logging.Logger`. Vì vậy không đặt công việc nghiệp vụ vào method đó.

### Bài 2 — Metric trong Supplier

Đoạn `logger.fine(() -> { counter.incrementAndGet(); return "count"; })` có an toàn không?

**Đáp án:** Không. Khi FINE tắt, counter không tăng. Hãy tăng counter độc lập rồi capture giá trị để tạo message.

### Bài 3 — Filter từ chối

Logger level FINE bật nhưng Filter trả false. Supplier có thể đã chạy chưa?

**Đáp án:** Có. Logger kiểm tra level trước, rồi tạo record và áp dụng Filter. Supplier có thể đã tạo message trước khi Filter loại record.

### Bài 4 — Chụp snapshot

Một object Order có thể bị thread khác cập nhật. Làm sao log trạng thái nhất quán?

**Đáp án:** Lấy các giá trị cần log thành snapshot immutable/synchronized trước, rồi Supplier chỉ format snapshot đó.

### Bài 5 — Eager và lazy

Khác biệt giữa `logger.fine("state=" + buildState())` và `logger.fine(() -> "state=" + buildState())`?

**Đáp án:** Cách đầu gọi `buildState()` trước khi vào logger; cách thứ hai trì hoãn tạo message đến khi level cho phép. Cả hai chỉ nên gọi hàm không side effect.

### Bài 6 — Công việc phải xảy ra một lần

Ứng dụng cần ghi audit event bắt buộc. Có thể gọi `auditPublisher.publish(event)` trong Supplier của INFO không?

**Đáp án:** Không. Publish event ngoài Supplier; logging chỉ ghi lại kết quả hoặc ID của event.

### Bài 7 — Logger thread-safe

Logger được mô tả multi-thread safe. Có thể capture một HashMap mutable đang được cập nhật trong Supplier không?

**Đáp án:** Không mặc nhiên an toàn. Thread safety của Logger không bao phủ dữ liệu và code do ứng dụng capture; hãy dùng snapshot, immutable map hoặc đồng bộ.

### Bài 8 — Có cần Supplier cho mọi log?

Message chỉ là `"cache miss"`, không có phép tính đáng kể. Có bắt buộc viết lambda không?

**Đáp án:** Không. `logger.fine("cache miss")` rõ ràng và đủ tốt. Supplier hữu ích khi việc tạo message có chi phí có thể bỏ qua.

### Bài 9 — Exception trong message builder

Một method build log cần đọc file và có thể ném IOException. Có nên đưa việc đọc file vào Supplier không?

**Đáp án:** Không nên. Tách việc đọc file, đóng resource và xử lý IOException thành luồng rõ ràng; Supplier chỉ format kết quả đã có.

### Bài 10 — Đo số lần Supplier chạy

Muốn kiểm tra hành vi lazy trong test, có thể dùng counter trong Supplier không?

**Đáp án:** Có thể dùng test instrumentation trong một chương trình kiểm thử cô lập như demo; không dùng counter đó làm metric nghiệp vụ production. Đo hiệu năng bằng benchmark phù hợp.

## 16. Checklist code review

- [ ] Supplier chỉ tạo chuỗi log, không cập nhật trạng thái nghiệp vụ?
- [ ] Không có DB write, HTTP call, event publish hoặc file mutation trong lambda?
- [ ] Counter và metric cần thiết được cập nhật độc lập với log level?
- [ ] ID/token nghiệp vụ được tạo ở luồng chính, không phụ thuộc Supplier?
- [ ] Message đắt tiền có thật sự cần lazy evaluation?
- [ ] Message rẻ/hằng số có thể dùng String trực tiếp?
- [ ] Lambda capture giá trị immutable hoặc snapshot nhất quán?
- [ ] Không phụ thuộc vào số lần Supplier được gọi?
- [ ] Hiểu level check và Filter là hai bước riêng?
- [ ] Không nhầm Supplier đã chạy với log record đã được publish?
- [ ] Logger thread-safe không bị hiểu nhầm là state capture cũng thread-safe?
- [ ] Hàm tạo message không có side effect và không làm request thất bại vì lỗi phụ?
- [ ] Throwable được truyền qua overload phù hợp thay vì tự format stack trace?
- [ ] Dùng đúng API có từ Java 8 nếu project target Java 8?
- [ ] Demo, stdout và hành vi lazy đã được kiểm thử?

**Kết luận:** Supplier giúp Java logging trì hoãn việc tạo message cho đến khi level cho phép, nhưng chính điều đó khiến Supplier **không được sở hữu công việc nghiệp vụ**. Giữ lambda thuần, dựa trên snapshot bất biến, để việc bật/tắt log chỉ ảnh hưởng chi phí chẩn đoán và nội dung log. Đồng thời nhớ rằng Filter có thể loại record sau khi Supplier đã chạy; vì vậy “Supplier đã được gọi” không đồng nghĩa “log đã được ghi”.

### Tài liệu chính thức còn được hỗ trợ

- [`Logger` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.logging/java/util/logging/Logger.html): overload nhận Supplier từ Java 8, level check, Filter và các logging methods.
- [`Logger` — Java SE 8](https://docs.oracle.com/javase/8/docs/api/java/util/logging/Logger.html): xác nhận các Supplier overload đã có trong Java 8.
- [`Supplier<T>` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/function/Supplier.html): functional interface và hợp đồng `get()`.
- [`Filter` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.logging/java/util/logging/Filter.html): lọc LogRecord trước khi publish.
- [`LogRecord` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.logging/java/util/logging/LogRecord.html): biểu diễn record được chuyển tới Handler.