# Ghi kèm Throwable và tham số định dạng với System.Logger trong Java

## 1. Mục tiêu của hai nhóm overload

System.Logger cung cấp API logging chuẩn trong Java Platform. Khi ghi một sự kiện, ứng dụng thường cần hai loại thông tin:

- **Thông điệp có tham số**: chèn dữ liệu như mã đơn hàng, tên khách hàng hoặc thời gian vào mẫu thông điệp.
- **Throwable đi kèm**: đính kèm exception đã gây ra lỗi để backend có thể ghi loại lỗi, stack trace và chuỗi nguyên nhân.

System.Logger có overload riêng cho từng mục đích. Tham số định dạng được truyền vào nhóm overload varargs; Throwable được truyền vào overload chuyên biệt. Phân biệt đúng hai nhóm này giúp log giữ đủ ngữ cảnh và nguyên nhân.

System.Logger và các overload dưới đây có từ Java 9. Ví dụ trong bài dùng Java 17 trở lên để biên dịch và chạy.

## 2. Lấy logger và chọn mức

Lấy logger theo tên class:

~~~java
private static final System.Logger LOG =
    System.getLogger(OrderService.class.getName());
~~~

Các mức phổ biến:

- TRACE: thông tin chẩn đoán rất chi tiết.
- DEBUG: thông tin phục vụ gỡ lỗi.
- INFO: sự kiện vận hành bình thường.
- WARNING: tình huống bất thường cần chú ý.
- ERROR: thao tác thất bại hoặc lỗi nghiêm trọng.

System.Logger là facade. LoggerFinder lựa chọn backend thực tế; backend có thể là java.util.logging hoặc provider tùy chỉnh. API ghi log không yêu cầu code gọi phải phụ thuộc trực tiếp vào backend đó.

## 3. Ghi thông điệp có tham số định dạng

Dùng overload:

~~~java
log(Level level, String format, Object... params)
~~~

Mẫu format sử dụng cú pháp của java.text.MessageFormat. Placeholder được đánh số từ 0:

~~~java
LOG.log(
    System.Logger.Level.INFO,
    "Order {0} processed for customer {1}",
    orderId,
    customerName
);
~~~

Nếu orderId là 731 và customerName là "An", message sau khi định dạng là:

~~~text
Order 731 processed for customer An
~~~

Có thể truyền một mảng tham số tường minh:

~~~java
Object[] params = { orderId, customerName };

LOG.log(
    System.Logger.Level.INFO,
    "Order {0} processed for customer {1}",
    params
);
~~~

Dùng mảng tường minh hữu ích khi tham số đã có sẵn trong Object[] hoặc khi muốn tránh nhầm overload.

## 4. Cú pháp MessageFormat thường dùng

System.Logger dùng MessageFormat cho overload có tham số, không dùng cú pháp %s của String.format.

| Pattern | Ý nghĩa |
|---|---|
| {0} | Chèn tham số thứ nhất |
| {1} | Chèn tham số thứ hai |
| {0,number} | Định dạng số |
| {0,number,currency} | Định dạng tiền tệ theo locale |
| {0,number,percent} | Định dạng phần trăm |
| {0,date,short} | Định dạng ngày |
| {0,time,short} | Định dạng giờ |
| {0,choice,...} | Chọn thông điệp theo khoảng giá trị |

Ví dụ:

~~~java
LOG.log(
    System.Logger.Level.INFO,
    "Order {0}: total={1,number,currency}, discount={2,number,percent}",
    orderId,
    total,
    discount
);
~~~

Kết quả hiển thị phụ thuộc locale và formatter của backend. Nếu cần output ổn định cho log machine-readable, hãy cân nhắc format rõ ràng hoặc dùng cấu trúc log mà backend hỗ trợ.

MessageFormat dùng dấu nháy đơn để quote cú pháp đặc biệt. Muốn ghi dấu nháy đơn literal trong pattern, viết hai dấu nháy đơn liên tiếp. Vì vậy, pattern có apostrophe cần được kiểm tra cẩn thận; một chuỗi có dấu nháy đơn không đúng vị trí có thể làm placeholder bị hiểu khác dự định.

## 5. Gắn Throwable vào log

Dùng overload chuyên biệt:

~~~java
log(Level level, String msg, Throwable thrown)
~~~

Ví dụ:

~~~java
try {
    repository.save(order);
} catch (IllegalStateException exception) {
    LOG.log(
        System.Logger.Level.ERROR,
        "Unable to save order " + order.getId(),
        exception
    );
}
~~~

Throwable được gắn riêng vào bản ghi log. Với backend JUL, nó được lưu trong trường thrown của LogRecord, không phải trong mảng parameters. Formatter có thể dùng trường này để xuất stack trace hoặc thông tin exception.

Đây là điểm khác biệt quan trọng:

- msg là message hoặc message key.
- thrown là Throwable gắn với sự kiện.
- Throwable không được tự động chèn vào placeholder {0}.

Không chỉ ghi exception.getMessage() khi cần điều tra lỗi. Cách đó làm mất stack trace và thông tin cause mà backend có thể ghi lại khi nhận Throwable đầy đủ.

## 6. Overload resolution: bẫy khi tham số cuối là Throwable

System.Logger có hai overload cùng bắt đầu bằng Level và String:

~~~java
log(Level level, String msg, Throwable thrown)
log(Level level, String format, Object... params)
~~~

Khi đối số thứ ba có kiểu Throwable, Java ưu tiên overload fixed-arity nhận Throwable. Ví dụ:

~~~java
Throwable failure =
    new IllegalStateException("database unavailable");

LOG.log(
    System.Logger.Level.ERROR,
    "Order {0} failed",
    failure
);
~~~

Lời gọi trên được hiểu là message đi kèm Throwable. failure không phải tham số định dạng; placeholder {0} vẫn còn nguyên nếu backend không có parameters để thay thế.

Nếu mục đích là đưa chính Throwable vào danh sách tham số định dạng, phải buộc compiler chọn overload varargs:

~~~java
LOG.log(
    System.Logger.Level.INFO,
    "Diagnostic object: {0}",
    new Object[] { failure }
);
~~~

Cách này chỉ định dạng biểu diễn của object theo formatter. Nó không đính kèm exception như một Throwable của bản ghi log. Khi cần stack trace, hãy dùng overload nhận Throwable.

Với một tham số thông thường không phải Throwable, ví dụ Integer hoặc String, overload varargs được chọn:

~~~java
LOG.log(
    System.Logger.Level.INFO,
    "Order {0} accepted",
    orderId
);
~~~

## 7. Vừa định dạng message vừa đính kèm Throwable

System.Logger không có một overload trực tiếp nhận đồng thời format, Object... params và Throwable. Có hai cách rõ ràng để giữ cả nội dung định dạng lẫn exception.

**Cách 1: định dạng trước bằng MessageFormat**

~~~java
String message = MessageFormat.format(
    "Could not process order {0} for customer {1}",
    orderId,
    customerName
);

LOG.log(System.Logger.Level.ERROR, message, failure);
~~~

Message đã được tạo trước; Throwable vẫn được gắn riêng vào bản ghi.

**Cách 2: dùng Supplier cùng Throwable**

~~~java
LOG.log(
    System.Logger.Level.ERROR,
    () -> MessageFormat.format(
        "Could not process order {0} for customer {1}",
        orderId,
        customerName
    ),
    failure
);
~~~

Supplier chỉ được gọi khi logger bật mức ERROR. Cách này tránh tạo message và chạy MessageFormat khi log level đang bị tắt.

Nếu message format đơn giản và không tốn chi phí, cách 1 dễ đọc. Nếu tạo message cần truy vấn hoặc tính toán đáng kể, cách 2 có thể tiết kiệm công việc không cần thiết.

## 8. Supplier để tạo message lười

Các overload nhận Supplier hữu ích khi dựng message tốn chi phí:

~~~java
LOG.log(
    System.Logger.Level.DEBUG,
    () -> buildDiagnosticReport(order)
);
~~~

Nếu logger không bật DEBUG, Supplier không được gọi theo hợp đồng của default implementation. Do đó, không cần tự dựng chuỗi trước khi gọi log.

Có overload kết hợp Supplier và Throwable:

~~~java
LOG.log(
    System.Logger.Level.ERROR,
    () -> "Order " + orderId + " failed after validation",
    failure
);
~~~

Overload này vừa tạo message lười, vừa đính kèm Throwable. Nếu cần placeholder MessageFormat, có thể gọi MessageFormat bên trong Supplier.

Không đặt side effect quan trọng trong Supplier. Backend có thể không gọi Supplier nếu mức log bị tắt; Supplier nên chỉ tạo nội dung chẩn đoán.

## 9. Kết hợp ResourceBundle và tham số

Khi cần message localization, dùng ResourceBundle overload:

~~~java
log(Level level, ResourceBundle bundle, String format, Object... params)
log(Level level, ResourceBundle bundle, String msg, Throwable thrown)
~~~

Ví dụ định dạng thông điệp đã bản địa hóa:

~~~java
ResourceBundle messages =
    ResourceBundle.getBundle("com.example.Messages");

LOG.log(
    System.Logger.Level.INFO,
    messages,
    "order.processed",
    new Object[] { orderId, customerName }
);
~~~

Trong ResourceBundle, order.processed có thể là mẫu như Order {0} processed for {1} ở một locale và có bản dịch khác ở locale khác. Sau khi chọn message theo bundle, các tham số được xử lý theo cú pháp MessageFormat.

Gắn Throwable với message key:

~~~java
LOG.log(
    System.Logger.Level.ERROR,
    messages,
    "order.save.failed",
    failure
);
~~~

Ở overload này, message key được tra trong bundle và Throwable vẫn được đính kèm riêng.

Có thể lấy localized logger:

~~~java
System.Logger localizedLogger =
    System.getLogger(OrderService.class.getName(), messages);
~~~

Với localized logger mặc định, các overload không nhận bundle được chuyển qua bundle đã gắn. Tuy nhiên, chuỗi do Supplier trả về được coi là message đã hoàn chỉnh, không mặc định là message key cần localization. Nếu cần tra key, hãy dùng overload nhận ResourceBundle tường minh.

## 10. Khi nào nên log Throwable?

Gắn Throwable khi exception là một phần quan trọng để hiểu sự kiện:

- Một thao tác I/O hoặc truy cập database thất bại.
- Một request không thể hoàn tất vì lỗi bên dưới.
- Một bước xử lý dữ liệu phát sinh exception cần điều tra.
- Một lỗi được chuyển thành exception khác và cần giữ cause.

Ví dụ:

~~~java
try {
    paymentGateway.charge(payment);
} catch (PaymentException exception) {
    LOG.log(
        System.Logger.Level.ERROR,
        "Payment failed for order " + payment.orderId(),
        exception
    );
    throw exception;
}
~~~

Chỉ log tại nơi có trách nhiệm xử lý hoặc kết thúc luồng lỗi. Nếu tầng dưới đã log cùng exception rồi tầng trên tiếp tục log lại nguyên stack trace, một lỗi có thể xuất hiện nhiều lần và gây nhiễu. Khi chuyển lỗi lên tầng trên, giữ nguyên cause:

~~~java
throw new OrderProcessingException(
    "Unable to complete order " + orderId,
    exception
);
~~~

Không bắt Throwable chỉ để log rồi tiếp tục như không có lỗi. Error thường biểu thị tình huống nghiêm trọng của JVM hoặc môi trường; chỉ bắt khi có lý do cụ thể và biết cách xử lý.

## 11. Backend quyết định cách hiển thị Throwable và format

System.Logger xác định dữ liệu được gửi đến LoggerFinder. Backend quyết định cách chuyển dữ liệu thành output.

Với JUL mặc định:

- Message và parameters được đưa vào LogRecord.
- Throwable được lưu trong LogRecord.getThrown().
- Formatter thường dùng MessageFormat để thay thế tham số.
- Handler quyết định nơi ghi log và cách xuất stack trace.

Một formatter có thể ghi cả message đã định dạng và stack trace. Formatter khác có thể ghi JSON, gửi dữ liệu đến hệ thống tập trung hoặc ẩn một số trường.

Không giả định mọi backend đều hiển thị stack trace giống nhau. Khi tích hợp backend tùy chỉnh, kiểm tra rằng adapter giữ nguyên Throwable thay vì chuyển nó thành chuỗi rồi làm mất cause.

## 12. Ví dụ hoàn chỉnh: tham số, Throwable và Supplier

Chương trình dưới đây cấu hình JUL để minh họa System.Logger. Formatter in message đã định dạng và loại/message của Throwable để output dễ kiểm tra.

**Tệp SystemLoggerThrowableDemo.java:**

~~~java
import java.text.MessageFormat;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class SystemLoggerThrowableDemo {
    private static final class CompactFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            StringBuilder result = new StringBuilder();
            result.append(record.getLevel().getName()).append(": ")
                    .append(formatMessage(record));

            if (record.getThrown() != null) {
                result.append(" [thrown=")
                        .append(record.getThrown().getClass().getSimpleName())
                        .append(": ")
                        .append(record.getThrown().getMessage())
                        .append("]");
            }

            return result.append(System.lineSeparator()).toString();
        }
    }

    public static void main(String[] args) {
        String loggerName = SystemLoggerThrowableDemo.class.getName();
        Logger jul = Logger.getLogger(loggerName);
        jul.setUseParentHandlers(false);
        jul.setLevel(Level.ALL);

        ConsoleHandler handler = new ConsoleHandler();
        handler.setLevel(Level.ALL);
        handler.setFormatter(new CompactFormatter());
        jul.addHandler(handler);

        System.Logger logger = System.getLogger(loggerName);
        int orderId = 731;
        String customer = "An";

        logger.log(
                System.Logger.Level.INFO,
                "Order {0} processed for customer {1}",
                new Object[] { orderId, customer }
        );

        IllegalStateException failure =
                new IllegalStateException("database unavailable");

        logger.log(
                System.Logger.Level.ERROR,
                "Could not save order " + orderId,
                failure
        );

        String formatted = MessageFormat.format(
                "Could not process order {0}",
                orderId
        );
        logger.log(System.Logger.Level.ERROR, formatted, failure);

        logger.log(
                System.Logger.Level.DEBUG,
                () -> "diagnostic for order " + orderId
        );
    }
}
~~~

Biên dịch và chạy trên JDK 17 trở lên:

~~~bash
javac --release 17 -Xlint:all SystemLoggerThrowableDemo.java
java -cp . SystemLoggerThrowableDemo
~~~

Output:

~~~text
INFO: Order 731 processed for customer An
SEVERE: Could not save order 731 [thrown=IllegalStateException: database unavailable]
SEVERE: Could not process order 731 [thrown=IllegalStateException: database unavailable]
FINE: diagnostic for order 731
~~~

JUL ánh xạ System.Logger.Level.ERROR sang SEVERE và DEBUG sang FINE. Formatter của ví dụ chỉ in loại exception và message; formatter production có thể ghi stack trace đầy đủ bằng printStackTrace hoặc cách xuất tương ứng.

## 13. Lỗi thường gặp

- **Dùng %s thay {0}:** overload tham số của System.Logger dùng cú pháp MessageFormat.
- **Truyền Throwable như tham số cuối và nghĩ nó sẽ thay placeholder:** compiler chọn overload nhận Throwable; exception được đính kèm chứ không vào parameters.
- **Bỏ Throwable, chỉ nối exception.getMessage():** mất stack trace và cause.
- **Dùng Throwable làm tham số định dạng khi cần stack trace:** new Object[] { throwable } chỉ biến nó thành tham số; dùng overload Throwable nếu cần đính kèm lỗi.
- **Không định dạng trước khi gọi overload Throwable:** nếu cần cả placeholder và exception, tạo message bằng MessageFormat rồi truyền message cùng Throwable, hoặc dùng Supplier+Throwable.
- **Định dạng message tốn kém trước khi kiểm tra level:** dùng Supplier để chỉ tạo message khi mức log được bật.
- **Đưa side effect vào Supplier:** Supplier có thể không được gọi; chỉ dùng để tạo message.
- **Quên truyền Object[] rõ ràng khi dữ liệu đã là mảng:** truyền mảng vào varargs để các phần tử trở thành tham số định dạng.
- **Nhầm format với localization:** ResourceBundle chọn mẫu theo locale; MessageFormat thay placeholder trong mẫu đó.
- **Log cùng một exception ở mọi tầng:** tạo nhiều bản ghi lặp; chọn một boundary chịu trách nhiệm log.
- **Backend làm mất Throwable:** adapter nên chuyển exception vào trường thrown của record, không chỉ nối thành chuỗi.
- **Ghi dữ liệu bí mật vào message:** không log password, token, credential hoặc thông tin cá nhân không cần thiết.

## 14. Ghi nhớ

Dùng log(level, format, params...) để thay placeholder MessageFormat. Dùng log(level, message, throwable) để đính kèm exception cho backend. Nếu cần cả hai, định dạng message trước bằng MessageFormat rồi gọi overload Throwable, hoặc dùng Supplier kết hợp Throwable để tạo message lười. Cẩn thận overload resolution: đối số cuối có kiểu Throwable sẽ chọn overload Throwable, không phải tham số format. Với localization, dùng ResourceBundle overload để dịch message key rồi định dạng tham số. Ghi log ở đúng boundary, giữ nguyên cause và tránh lặp lại cùng stack trace ở nhiều tầng.

## 15. Tài liệu tham khảo

- [System.Logger – Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.Logger.html)
- [System.LoggerFinder – Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.LoggerFinder.html)
- [MessageFormat – Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/MessageFormat.html)
- [LogRecord – Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.logging/java/util/logging/LogRecord.html)
- [Formatter – Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.logging/java/util/logging/Formatter.html)
