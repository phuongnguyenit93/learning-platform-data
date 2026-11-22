# isLoggable và thông điệp qua Supplier

## 1. Mục tiêu: tránh tạo thông điệp log khi không cần

Trong ứng dụng Java, logging thường xuất hiện ở nhiều mức như \`SEVERE\`, \`WARNING\`, \`INFO\`, \`CONFIG\`, \`FINE\`, \`FINER\` và \`FINEST\`. Mức log giúp ứng dụng điều khiển lượng thông tin được ghi theo môi trường chạy.

Một thông điệp debug có thể cần gọi hàm tốn CPU, duyệt object graph, serialize trạng thái hoặc ghép nhiều chuỗi. Nếu mức \`FINE\` đang tắt, việc tạo thông điệp trước khi gọi logger vẫn tiêu tốn tài nguyên dù không có bản ghi nào được phát đi.

\`java.util.logging.Logger\` cung cấp hai API bổ trợ:

- \`isLoggable(Level)\`: kiểm tra logger có bật mức log được yêu cầu theo effective level hiện tại hay không.
- \`log(Level, Supplier<String>)\`: chỉ tạo thông điệp bằng cách gọi Supplier khi logger bật mức tương ứng.

Các overload Supplier của \`Logger\`, bao gồm \`log(Level, Supplier<String>)\` và \`fine(Supplier<String>)\`, đã có từ Java 8. Chúng vẫn là API hiện hành trên Java 9 và các JDK mới hơn; không phải API mới được thêm riêng trong Java 9.

## 2. Logger level và isLoggable

Ví dụ:

~~~java
Logger logger = Logger.getLogger(OrderService.class.getName());

if (logger.isLoggable(Level.FINE)) {
    logger.fine("Preparing order diagnostics");
}
~~~

\`isLoggable\` trả về \`true\` khi logger hiện đang bật cho mức log được truyền vào. Việc kiểm tra dựa trên effective level của logger; nếu level riêng của logger là \`null\`, nó kế thừa level từ logger cha gần nhất có level cụ thể.

Các mức chuẩn có thứ tự độ nghiêm trọng từ cao xuống thấp:

| Level | Giá trị chuẩn | Ý nghĩa thường dùng |
|---|---:|---|
| \`SEVERE\` | 1000 | Lỗi nghiêm trọng |
| \`WARNING\` | 900 | Tình huống đáng cảnh báo |
| \`INFO\` | 800 | Sự kiện vận hành |
| \`CONFIG\` | 700 | Thông tin cấu hình |
| \`FINE\` | 500 | Thông tin debug |
| \`FINER\` | 400 | Chi tiết debug hơn |
| \`FINEST\` | 300 | Trace rất chi tiết |
| \`ALL\` | \`Integer.MIN_VALUE\` | Bật mọi mức |
| \`OFF\` | \`Integer.MAX_VALUE\` | Tắt logging |

Một mức log được chấp nhận khi giá trị mức đó bằng hoặc cao hơn effective level của logger. Ví dụ, logger có level \`INFO\` sẽ nhận \`INFO\`, \`WARNING\`, \`SEVERE\`, nhưng loại \`CONFIG\`, \`FINE\`, \`FINER\` và \`FINEST\`.

\`isLoggable\` là phép kiểm tra trạng thái tại thời điểm gọi. Nó không phải khóa, không đồng bộ hóa thread và không bảo đảm rằng handler cuối cùng sẽ xuất bản bản ghi.

## 3. Supplier giúp trì hoãn việc tạo thông điệp

\`Supplier<String>\` là hàm không nhận tham số và cung cấp một chuỗi khi được gọi. Có thể truyền lambda trực tiếp:

~~~java
logger.log(Level.FINE, () ->
        "Current order state = " + buildExpensiveSnapshot(order));
~~~

Nếu logger không bật \`FINE\`, Supplier không được gọi. Vì vậy, \`buildExpensiveSnapshot(order)\` và phép ghép chuỗi bên trong lambda đều không chạy.

So sánh hai cách:

~~~java
// Tạo chuỗi ngay, kể cả khi FINE đang tắt.
logger.fine("state = " + buildExpensiveSnapshot(order));

// Chỉ tạo chuỗi khi FINE được bật.
logger.fine(() -> "state = " + buildExpensiveSnapshot(order));
~~~

Cách thứ hai trì hoãn cả phép tính nằm bên trong lambda. Chỉ đặt phần nối chuỗi vào Supplier là chưa đủ nếu dữ liệu tốn kém đã được tính trước:

~~~java
// Vẫn eager: buildExpensiveSnapshot chạy trước khi gọi log.
String snapshot = buildExpensiveSnapshot(order);
logger.fine(() -> "state = " + snapshot);
~~~

Hãy đưa công việc cần trì hoãn vào bên trong Supplier hoặc đặt nó sau một kiểm tra \`isLoggable\` phù hợp.

## 4. Những overload Supplier thường dùng

\`Logger\` có các convenience method cho từng level:

~~~java
logger.severe(() -> createMessage());
logger.warning(() -> createMessage());
logger.info(() -> createMessage());
logger.config(() -> createMessage());
logger.fine(() -> createMessage());
logger.finer(() -> createMessage());
logger.finest(() -> createMessage());
~~~

Dạng tổng quát:

~~~java
logger.log(Level.FINE, () -> createMessage());
~~~

Nếu cần gắn một exception vào LogRecord:

~~~java
try {
    processRequest();
} catch (IOException ex) {
    logger.log(Level.WARNING, ex,
            () -> "Cannot process request " + requestId);
}
~~~

Trong overload có \`Throwable\`, exception được lưu vào thuộc tính thrown của LogRecord. Formatter có thể xử lý stack trace riêng; exception không được xem là một tham số thay thế trong message pattern.

Các API này phù hợp với thông điệp cần tính toán động. Với thông điệp cố định, overload nhận String đơn giản hơn.

## 5. Khi nào dùng Supplier, khi nào dùng isLoggable?

Nếu chỉ cần tạo chuỗi log một cách lazy, ưu tiên Supplier trực tiếp:

~~~java
logger.fine(() -> "cache entries = " + cache.size());
~~~

Không cần viết thêm:

~~~java
if (logger.isLoggable(Level.FINE)) {
    logger.fine(() -> "cache entries = " + cache.size());
}
~~~

Supplier đã tự trì hoãn việc tạo message khi level không bật. Kiểm tra lặp lại không làm việc log an toàn hơn và thường không đem lại lợi ích.

Dùng \`isLoggable\` khi phải thực hiện nhiều bước tốn kém trước khi có thể tạo message, hoặc khi kết quả tính toán còn được dùng cho nhiều câu lệnh:

~~~java
if (logger.isLoggable(Level.FINE)) {
    DiagnosticSnapshot snapshot = collectDiagnostics(order);
    String correlation = findCorrelationId(order);

    logger.log(Level.FINE, () ->
            formatDiagnostics(snapshot, correlation));
}
~~~

Ở đây, \`collectDiagnostics\` và \`findCorrelationId\` chỉ chạy khi FINE đang bật. Supplier tiếp tục trì hoãn bước format chuỗi đến lúc logger thực sự nhận mức log.

Nếu chỉ cần một phép tính để tạo message, đưa phép tính đó vào Supplier sẽ ngắn và ít lặp hơn.

## 6. isLoggable không bảo đảm handler sẽ ghi bản tin

Logger và Handler có các tầng lọc riêng:

1. Logger kiểm tra effective level của chính nó.
2. Nếu mức log được chấp nhận, Logger tạo LogRecord; với overload Supplier, message được tạo ở bước này.
3. LogRecord được chuyển đến các Handler thích hợp.
4. Mỗi Handler có thể tiếp tục kiểm tra level và Filter riêng trước khi publish.

Do đó:

- \`isLoggable(Level.FINE)\` có thể trả \`true\` nhưng không có dòng log nào xuất hiện nếu mọi Handler đều tắt FINE hoặc filter từ chối bản ghi.
- Supplier vẫn có thể đã được gọi vì logger đã chấp nhận mức log trước khi Handler lọc.
- \`isLoggable\` không kiểm tra trước tất cả các Filter của Handler và không bảo đảm log được ghi ra console, file hay hệ thống tập trung.

Khi chẩn đoán tình trạng không thấy log, hãy kiểm tra effective level của Logger, level của Handler, Filter, \`useParentHandlers\`, Formatter và cấu hình LogManager.

## 7. Tham số hóa thông điệp và giới hạn của nó

Java Util Logging hỗ trợ message pattern và tham số:

~~~java
logger.log(Level.FINE, "Order {0} has status {1}",
        new Object[] { orderId, status });
~~~

Cách này tránh tự ghép chuỗi trước khi gọi logger. Formatter có thể định dạng tham số khi xử lý LogRecord.

Tuy nhiên, biểu thức dùng để tạo tham số vẫn được Java đánh giá trước khi gọi phương thức:

~~~java
logger.log(Level.FINE, "Snapshot: {0}",
        buildExpensiveSnapshot(order));
~~~

\`buildExpensiveSnapshot(order)\` vẫn chạy kể cả khi FINE bị tắt. Nếu chính việc tạo tham số tốn kém, hãy dùng Supplier:

~~~java
logger.log(Level.FINE, () ->
        "Snapshot: " + buildExpensiveSnapshot(order));
~~~

Một quy tắc thực tế:

- Message cố định: dùng String.
- Message có tham số đơn giản: dùng message pattern.
- Message hoặc tham số cần tính toán tốn kém: dùng Supplier.
- Nhiều bước chẩn đoán tốn kém: dùng \`isLoggable\` để chặn toàn bộ khối, rồi dùng Supplier để format.

## 8. Supplier nên thuần và không có side effect

Không nên dùng Supplier để thực hiện nghiệp vụ:

~~~java
// Không nên: log level quyết định việc cập nhật trạng thái.
logger.fine(() -> {
    metrics.incrementCounter();
    return "counter updated";
});
~~~

Nếu FINE tắt, counter không tăng. Khi FINE bật, counter lại tăng chỉ vì cấu hình logging. Điều này làm thay đổi hành vi nghiệp vụ theo môi trường.

Supplier nên chỉ đọc trạng thái và tạo nội dung chẩn đoán. Tránh:

- Ghi dữ liệu hoặc cập nhật trạng thái nghiệp vụ.
- Gửi request mạng hoặc thực hiện I/O không cần thiết.
- Tiêu thụ stream, iterator hoặc tài nguyên dùng một lần.
- Gọi phương thức có side effect.
- Đọc dữ liệu nhạy cảm rồi đưa nguyên văn vào log.

Supplier chỉ được gọi khi logger bật mức tương ứng. Khi mức bị tắt, nội dung của Supplier không được thực thi; vì vậy không đặt logic bắt buộc vào đó.

Nếu Supplier ném unchecked exception khi được gọi, exception có thể truyền ngược ra caller của phương thức logging. Hãy giữ phần tạo message đủ ổn định để logging không làm hỏng luồng xử lý chính.

## 9. Cấu hình level và race condition

Một mẫu thường gặp:

~~~java
if (logger.isLoggable(Level.FINE)) {
    Snapshot snapshot = collectDiagnostics();
    logger.log(Level.FINE, () -> format(snapshot));
}
~~~

Cấu hình logging có thể thay đổi trong lúc chương trình đang chạy. Giữa lần gọi \`isLoggable\` và lần gọi \`log\`, level có thể bị thay đổi bởi thread quản trị logging:

- Nếu kiểm tra trả \`true\`, nhưng level bị tắt trước khi gọi \`log\`, snapshot đã được tính nhưng Supplier có thể không được gọi.
- Nếu kiểm tra trả \`false\`, nhưng level được bật ngay sau đó, khối không chạy và lần log đó bị bỏ qua.

Đây không phải lỗi của Logger; \`isLoggable\` là snapshot trạng thái, không phải thao tác đồng bộ với lần log tiếp theo.

Không dùng \`isLoggable\` để bảo vệ dữ liệu chia sẻ hoặc thay thế lock. Nếu dữ liệu chẩn đoán cần nhất quán giữa nhiều field, hãy dùng cơ chế đồng bộ hoặc tạo immutable snapshot theo quy tắc concurrency của ứng dụng.

## 10. Ví dụ Java hoàn chỉnh: chứng minh Supplier chỉ chạy khi FINE bật

Chương trình sau tạo Logger riêng, tắt parent handlers và gắn một Handler đơn giản để output ổn định. Nó đếm số lần Supplier được gọi ở hai trạng thái: FINE tắt và FINE bật. Ví dụ cũng cho thấy unchecked exception từ Supplier được truyền về caller.

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LoggerSupplierDemo {
    private static int expensiveCalculation() {
        return 42;
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger(
                "demo.supplier." + System.nanoTime());
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        Handler handler = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println(record.getLevel().getName()
                            + ": " + record.getMessage());
                }
            }

            @Override
            public void flush() { }

            @Override
            public void close() { }
        };
        handler.setLevel(Level.ALL);
        logger.addHandler(handler);

        AtomicInteger supplierCalls = new AtomicInteger();
        try {
            System.out.println("FINE enabled initially = "
                    + logger.isLoggable(Level.FINE));
            logger.log(Level.FINE, () -> {
                supplierCalls.incrementAndGet();
                return "expensive value=" + expensiveCalculation();
            });
            System.out.println("supplier calls while disabled = "
                    + supplierCalls.get());

            logger.setLevel(Level.FINE);
            System.out.println("FINE enabled after level change = "
                    + logger.isLoggable(Level.FINE));
            logger.log(Level.FINE, () -> {
                supplierCalls.incrementAndGet();
                return "expensive value=" + expensiveCalculation();
            });
            System.out.println("supplier calls after enabled = "
                    + supplierCalls.get());

            try {
                logger.log(Level.FINE, () -> {
                    throw new IllegalStateException("supplier failure");
                });
            } catch (IllegalStateException ex) {
                System.out.println("supplier exception = "
                        + ex.getClass().getSimpleName());
            }
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }
    }
}
~~~

Lưu mã nguồn thành \`LoggerSupplierDemo.java\`, biên dịch và chạy với Java 17 trở lên:

~~~bash
javac --release 17 -Xlint:all LoggerSupplierDemo.java
java LoggerSupplierDemo
~~~

Kết quả:

~~~text
FINE enabled initially = false
supplier calls while disabled = 0
FINE enabled after level change = true
FINE: expensive value=42
supplier calls after enabled = 1
supplier exception = IllegalStateException
~~~

Mã nguồn tương thích với Java 9; có thể kiểm tra bằng:

~~~bash
javac --release 9 -Xlint:all LoggerSupplierDemo.java
java LoggerSupplierDemo
~~~

Ví dụ xác nhận Supplier không được gọi khi FINE tắt và được gọi khi FINE bật. Handler được đặt ở ALL để bản ghi FINE đã được Logger chấp nhận có thể xuất hiện. Phần kiểm tra exception chỉ chạy khi FINE đã bật.

## 11. Module và cấu hình ứng dụng

Trong ứng dụng modular từ Java 9, nếu mã sử dụng \`java.util.logging\`, module cần khai báo dependency:

~~~java
module com.example.app {
    requires java.logging;
}
~~~

Nếu ứng dụng chạy trên classpath, không cần khai báo \`module-info.java\`.

Level có thể được cấu hình trong code, file cấu hình của LogManager hoặc qua hệ thống logging của ứng dụng. Tránh đặt level riêng của từng logger một cách tùy tiện trong thư viện dùng chung; ứng dụng triển khai nên là nơi quyết định mức log cho môi trường.

Không ghi password, access token, session cookie, private key hoặc dữ liệu cá nhân không cần thiết vào Supplier. Lazy evaluation chỉ tiết kiệm công tạo message khi level tắt; nó không tự làm sạch dữ liệu nhạy cảm hoặc giới hạn quyền truy cập file log.

## 12. Lỗi thường gặp

- **Ghép chuỗi trước khi gọi logger:** message đã được tạo dù level bị tắt; chuyển phần ghép chuỗi vào Supplier.
- **Tính toán đắt đỏ ngoài lambda:** Supplier lazy nhưng dữ liệu đã được tính trước; đặt phép tính vào lambda hoặc dùng \`isLoggable\`.
- **Luôn kiểm tra isLoggable trước Supplier:** thường là kiểm tra trùng; gọi Supplier trực tiếp nếu chỉ cần lazy message.
- **Dùng isLoggable như synchronization:** kiểm tra level không khóa dữ liệu và không đồng bộ với lần log sau.
- **Cho rằng isLoggable bảo đảm output:** Handler có level và Filter riêng, có thể loại bản ghi.
- **Đặt side effect trong Supplier:** hành vi nghiệp vụ sẽ phụ thuộc cấu hình logging.
- **Dùng parameterized logging nhưng truyền phép tính tốn kém:** tham số được tính trước khi gọi log; dùng Supplier khi cần trì hoãn phép tính.
- **Cho rằng Supplier exception luôn bị logger nuốt:** unchecked exception có thể truyền về caller; giữ message builder ổn định.
- **Log toàn bộ object tùy tiện:** \`toString()\` có thể tốn kém, ném exception hoặc lộ dữ liệu nhạy cảm.
- **Tạo logger mới liên tục:** logger được quản lý trong LogManager; nên dùng logger theo tên subsystem/class và giữ reference ổn định.

## 13. Checklist khi review logging

1. Mức log có đúng mục đích vận hành và debug không?
2. Message có được tạo trước khi kiểm tra level không?
3. Phần tính toán tốn kém có nằm trong Supplier hoặc sau \`isLoggable\` không?
4. Có kiểm tra \`isLoggable\` dư thừa trước Supplier không?
5. Có nhầm logger level với Handler level hoặc Filter không?
6. Supplier có side effect, I/O hoặc cập nhật nghiệp vụ không?
7. Supplier có thể ném exception làm gián đoạn luồng xử lý không?
8. Dữ liệu log có chứa thông tin bí mật hoặc dữ liệu cá nhân không cần thiết không?
9. Nếu level thay đổi runtime, code có phụ thuộc sai vào kết quả kiểm tra trước đó không?
10. Logger được cấu hình ở đúng tầng ứng dụng và module đã yêu cầu \`java.logging\` chưa?

## 14. Tài liệu tham khảo

- [Logger — Java SE 9 API](https://docs.oracle.com/javase/9/docs/api/java/util/logging/Logger.html)
- [Logger — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.logging/java/util/logging/Logger.html)
- [Level — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.logging/java/util/logging/Level.html)
- [Supplier — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/function/Supplier.html)
- [LogRecord — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.logging/java/util/logging/LogRecord.html)