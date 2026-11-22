# Ghi stack trace khi logging exception trong Java

## 1. Stack trace là gì và vì sao cần ghi?

Khi chương trình Java gặp lỗi, thông điệp như `"Payment failed"` hoặc `"Invalid configuration"` chỉ mô tả hiện tượng. Để điều tra nguyên nhân trong mã nguồn, người phát triển thường cần **stack trace**: danh sách các stack frame cho biết chuỗi lời gọi method liên quan đến vị trí một đối tượng `Throwable` được tạo hoặc nơi stack trace của nó được cập nhật.

Một stack trace điển hình chứa tên exception, thông điệp và các frame:

```text
java.lang.IllegalArgumentException: Invalid port: abc
    at Example.parsePort(Example.java:27)
    at Example.main(Example.java:12)
Caused by: java.lang.NumberFormatException: For input string: "abc"
    at java.base/java.lang.NumberFormatException.forInputString(...)
    ...
```

**Đây là dạng minh họa**, không phải output nguyên văn của chương trình trong bài: số dòng, frame của JDK và cách rút gọn stack phụ thuộc mã biên dịch, phiên bản Java và công cụ format. Chữ `...` là ký hiệu mô tả các frame bị lược trong minh họa.

Đối tượng exception lưu các thông tin quan trọng:

- **Kiểu exception**: `IllegalArgumentException`, `IOException`, `NullPointerException`…
- **Message**: mô tả lỗi, có thể không có.
- **Stack trace**: các `StackTraceElement` (class, method, file, line nếu có).
- **Cause**: nguyên nhân gốc được lưu qua `Throwable.getCause()`; có thể tạo thành chuỗi nhiều tầng.
- **Suppressed exceptions**: các lỗi phụ được đính kèm, thường xuất hiện khi đóng tài nguyên bằng `try-with-resources`.

**Ghi stack trace** trong logging thường có nghĩa là chuyển **nguyên đối tượng `Throwable`** cho framework logging, để formatter/backend hiển thị cả message, frames, cause và suppressed exceptions theo chính sách đã cấu hình.

> **Phân biệt:** stack trace của một exception mô tả call stack tại thời điểm stack trace được ghi nhận, **không phải** distributed trace liên kết các request qua nhiều service và không phải mức log có tên `TRACE` trong một số framework.

## 2. Dùng printStackTrace: trực tiếp nhưng có giới hạn

Mọi đối tượng `Throwable` có các phương thức:

```java
exception.printStackTrace();               // Mặc định ghi ra System.err.
exception.printStackTrace(printStream);    // Ghi vào PrintStream đã cung cấp.
exception.printStackTrace(printWriter);    // Ghi vào PrintWriter đã cung cấp.
```

Đây là **đoạn minh họa cú pháp**, giả định đã có biến `exception`, `printStream` và `printWriter` tương ứng.

Ví dụ Java đơn giản:

```java
public class PrintStackTraceDemo {
    public static void main(String[] args) {
        try {
            Integer.parseInt("not-a-number");
        } catch (NumberFormatException exception) {
            exception.printStackTrace();
        }
    }
}
```

Biên dịch/chạy:

```bash
javac PrintStackTraceDemo.java
java PrintStackTraceDemo
```

Khi chạy, `printStackTrace()` ghi ra **`System.err`**, gồm tên `NumberFormatException`, message và các frame. Phần xuất hiện từ JDK có thể khác giữa các bản Java. Không nên kỳ vọng số dòng hoặc toàn bộ output giống nhau trong mọi môi trường.

### Điểm hạn chế của printStackTrace

`printStackTrace()` hữu ích khi học, thử nghiệm nhỏ hoặc cần xem lỗi trong terminal. Tuy nhiên, trong ứng dụng cần logging có quản lý, gọi trực tiếp nó có những hạn chế:

- Không tự cung cấp level theo hệ thống logger, ví dụ `WARNING` hay `SEVERE`.
- Không tự thêm tên logger, request ID, trace ID, timestamp theo formatter logging đang dùng.
- Ghi thẳng tới luồng hoặc writer chỉ định; có thể không đi qua pipeline log tập trung, filter hoặc cấu hình đích log của ứng dụng.
- Có thể làm xuất hiện stack trace trên terminal dù logging ở ứng dụng đang tắt hoặc dùng đích khác.
- Có thể tạo log trùng khi vừa `printStackTrace()` vừa truyền cùng exception cho logger.

Với ứng dụng Java thực tế, **ưu tiên dùng API logging có hỗ trợ tham số `Throwable`**, thay vì gọi `printStackTrace()` rải rác trong mã nghiệp vụ.

## 3. Cách đúng trong Java Util Logging (JUL)

Thư viện chuẩn JDK có `java.util.logging.Logger`. Một overload quan trọng:

```java
logger.log(Level.SEVERE, "Unable to read configuration", exception);
```

Đây là đoạn minh họa cần biến `logger` và `exception` phù hợp. `Logger.log(Level, String, Throwable)` tạo một `LogRecord` với đối tượng lỗi được lưu tại trường `thrown`. Khi logger và handler cho phép bản ghi đi qua, **formatter** quyết định cách stack trace hiển thị.

Ví dụ tương đương trong trường hợp bắt `IOException`:

```java
try {
    loadConfiguration();
} catch (java.io.IOException exception) {
    logger.log(
            java.util.logging.Level.SEVERE,
            "Configuration loading failed",
            exception
    );
}
```

Đây là **đoạn minh họa**, giả định `loadConfiguration()` là method có sẵn có thể ném `IOException`. Tham số thứ ba quan trọng: nếu chỉ ghi `exception.getMessage()` hoặc `exception.toString()`, bản ghi log **không tự chứa tham chiếu đến Throwable**, nên formatter thường không có stack trace để hiển thị.

So sánh:

| Cách ghi | Thông tin logger nhận được |
| --- | --- |
| `logger.severe(exception.getMessage())` | Chỉ chuỗi message, không có `Throwable` |
| `logger.severe(exception.toString())` | Chuỗi gồm kiểu và message, không có stack frames |
| `logger.log(Level.SEVERE, "Operation failed", exception)` | Message có ngữ cảnh **và** nguyên `Throwable` |
| `exception.printStackTrace()` | Stack trace xuất trực tiếp ra stderr/writer, không theo pipeline logger |

Không phải mọi lỗi đều là `SEVERE`. Khi thao tác đang có cơ chế xử lý/fallback hợp lý, `WARNING` hoặc mức thấp hơn có thể phù hợp. Cần chọn level theo **tác động thực tế**, không theo tên class exception.

## 4. Ví dụ Java 17 chạy được: ghi đầy đủ stack trace bằng logger

Tạo file `StackTraceLoggingDemo.java`:

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Level;
import java.util.logging.Logger;
import java.util.logging.SimpleFormatter;

public class StackTraceLoggingDemo {
    private static final Logger LOG =
            Logger.getLogger(StackTraceLoggingDemo.class.getName());

    private static int parsePort(String input) {
        try {
            return Integer.parseInt(input);
        } catch (NumberFormatException cause) {
            // Giữ cause để chẩn đoán lỗi gốc.
            throw new IllegalArgumentException(
                    "Invalid port configuration: " + input, cause);
        }
    }

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.ALL);
        console.setFormatter(new SimpleFormatter());
        LOG.addHandler(console);

        try {
            try {
                int port = parsePort("abc");
                LOG.info("Configured port: " + port);
            } catch (IllegalArgumentException exception) {
                // Đưa nguyên Throwable vào LogRecord.
                LOG.log(Level.SEVERE, "Server startup configuration failed",
                        exception);
            }
        } finally {
            LOG.removeHandler(console);
            console.close();
        }
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac StackTraceLoggingDemo.java
java StackTraceLoggingDemo
```

**Kết quả cần quan sát trên stderr** (định dạng và số dòng có thể thay đổi):

- Một bản ghi `SEVERE` với nội dung `Server startup configuration failed`.
- Tên `java.lang.IllegalArgumentException` và message `Invalid port configuration: abc`.
- Các frame của `StackTraceLoggingDemo.parsePort` và `StackTraceLoggingDemo.main`.
- Phần `Caused by: java.lang.NumberFormatException` cùng stack của nguyên nhân gốc (có thể rút gọn những frame chung).

Dạng rút gọn minh họa:

```text
<timestamp> StackTraceLoggingDemo main
SEVERE: Server startup configuration failed
java.lang.IllegalArgumentException: Invalid port configuration: abc
    at StackTraceLoggingDemo.parsePort(StackTraceLoggingDemo.java:<line>)
    at StackTraceLoggingDemo.main(StackTraceLoggingDemo.java:<line>)
Caused by: java.lang.NumberFormatException: For input string: "abc"
    ...
```

Các ký hiệu `<timestamp>` và `<line>` chỉ dành cho sơ đồ kết quả; khi chạy thật, `SimpleFormatter` in timestamp và số dòng thực tế. JDK có thể in thêm các frame của `NumberFormatException`.

### Giải thích cơ chế

1. `parsePort("abc")` gọi `Integer.parseInt(...)`, làm phát sinh `NumberFormatException`.
2. `parsePort` chuyển lỗi thành `IllegalArgumentException` mới nhưng **truyền lỗi cũ làm cause** trong constructor, nên mối liên hệ nguyên nhân được giữ.
3. `LOG.log(Level.SEVERE, "...", exception)` truyền nguyên object vào log record. Không cần gọi `exception.printStackTrace()` thêm lần nữa.
4. `SimpleFormatter` của JUL nhận biết `LogRecord.getThrown()` và in chuỗi stack trace. Nếu dùng formatter tự viết chỉ xuất message, stack trace có thể bị bỏ qua.
5. `LOG.setUseParentHandlers(false)` tránh chuyển cùng record lên handler của logger cha, nhờ đó hạn chế log trùng trong ví dụ độc lập.
6. `ConsoleHandler` viết ra `System.err`. `close()` ở `finally` giải phóng handler do demo tạo.

**Không phải vì `Logger.log(...)` được gọi mà chắc chắn sẽ thấy stack trace:** logger level, handler level, filter, handler hoạt động và formatter vẫn quyết định bản ghi có được xuất hay không, và xuất được những phần gì.

## 5. Giữ cause khi bọc exception

Một lỗi tầng thấp thường cần được chuyển thành loại lỗi có ý nghĩa nghiệp vụ hoặc tầng kiến trúc. Chẳng hạn `IOException` khi đọc file cấu hình được chuyển thành `IllegalStateException` ở tầng khởi động:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public static String readSettings(Path path) {
    try {
        return Files.readString(path);
    } catch (IOException cause) {
        throw new IllegalStateException(
                "Cannot load application settings from " + path, cause);
    }
}
```

Đây là **method minh họa**; cần đặt trong một class và dùng đúng import. Constructor có tham số `cause` lưu nguyên nhân gốc. Sau đó, ở ranh giới xử lý có trách nhiệm báo lỗi, log `IllegalStateException` một lần:

```java
try {
    String settings = readSettings(Path.of("config.txt"));
} catch (IllegalStateException exception) {
    logger.log(Level.SEVERE, "Application initialization failed",
            exception);
}
```

Đoạn trên tiếp tục là minh họa, giả định `logger` đã khai báo và các import cần thiết. Khi formatter hỗ trợ Throwable, output có thể bao gồm cả lỗi bọc và `Caused by: java.io.IOException`.

**Sai lầm phổ biến:**

```java
throw new IllegalStateException("Cannot load settings: " + cause.getMessage());
```

Cách này chỉ ghi message vào exception mới mà **không giữ cause**; thông tin loại lỗi gốc và stack trace của `cause` bị tách khỏi chuỗi nguyên nhân. Nên ưu tiên constructor nhận `Throwable cause` khi cần bọc lỗi.

Một nguyên tắc khác: nếu bạn chỉ muốn ném lại đúng exception đang bắt và được phép về mặt kiểu khai báo, `throw exception;` giữ stack trace gắn với đối tượng đó. Tránh vô cớ tạo exception mới chỉ để ghi lại cùng nội dung.

## 6. Suppressed exceptions và try-with-resources

Ngoài `cause`, `Throwable` còn có các **suppressed exceptions** lấy bằng `getSuppressed()`. Trường hợp điển hình là `try-with-resources`: phần thân khối phát lỗi và khi tự động đóng tài nguyên lại phát thêm lỗi. Java giữ lỗi chính và gắn lỗi lúc đóng thành suppressed exception.

Ví dụ Java 17 độc lập, tạo `SuppressedTraceDemo.java`:

```java
public class SuppressedTraceDemo {
    static final class BrokenResource implements AutoCloseable {
        @Override
        public void close() {
            throw new IllegalStateException("close failed");
        }
    }

    public static void main(String[] args) {
        try (BrokenResource ignored = new BrokenResource()) {
            throw new IllegalArgumentException("work failed");
        } catch (Exception exception) {
            System.out.println("primary=" + exception.getMessage());
            System.out.println("suppressed="
                    + exception.getSuppressed().length);
        }
    }
}
```

Chạy:

```bash
javac SuppressedTraceDemo.java
java SuppressedTraceDemo
```

**Kết quả stdout chính xác:**

```text
primary=work failed
suppressed=1
```

Nếu trong `catch` dùng `exception.printStackTrace()` hoặc chuyển nguyên `Throwable` cho một formatter có hỗ trợ stack trace, output còn có phần `Suppressed: java.lang.IllegalStateException: close failed`. Điều này giúp phát hiện lỗi đóng tài nguyên mà việc chỉ ghi `exception.getMessage()` có thể bỏ sót.

Phân biệt:

- **Cause**: exception gây ra hoặc được bọc bên dưới một exception khác.
- **Suppressed**: exception phụ bị đính kèm khi đã có lỗi chính, không nhất thiết là nguyên nhân tạo lỗi chính.
- **Stack frame**: một vị trí lời gọi method trong stack trace của từng Throwable.

## 7. Ghi stack trace vào file log

Cơ chế **truyền exception cho logger không thay đổi** khi đích log là file. Với JUL, chỉ cần có `FileHandler` và formatter phù hợp:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.logging.FileHandler;
import java.util.logging.Level;
import java.util.logging.Logger;
import java.util.logging.SimpleFormatter;

public static void configureFileLog(Logger logger) throws IOException {
    Files.createDirectories(Path.of("logs"));

    FileHandler file = new FileHandler(
            "logs/errors.%g.log", 1_048_576, 3, true);
    file.setLevel(Level.WARNING);
    file.setFormatter(new SimpleFormatter());

    logger.addHandler(file);
    // Giữ tham chiếu file để đóng khi ứng dụng kết thúc.
}
```

Đây là **method minh họa** nằm trong một class, không phải chương trình độc lập. `FileHandler` dùng pattern tạo tên log, giới hạn kích thước, số thế hệ và chế độ append. Khi log exception:

```java
logger.log(Level.SEVERE, "Cannot open customer data", exception);
```

`SimpleFormatter` sẽ in stack trace vào file nếu bản ghi tới được handler. Nếu thay `SimpleFormatter` bằng formatter tùy biến chỉ in `record.getMessage()`, file có thể không còn stack trace, mặc dù logger đã nhận đúng exception.

Lưu ý `FileHandler` mặc định có thể sử dụng `XMLFormatter` nếu không cấu hình formatter. File khi ấy có cấu trúc XML, không nhất thiết là các dòng text quen thuộc. Chọn formatter theo công cụ xử lý log thực tế, và đặt rotation/retention để stack trace dài không làm đầy đĩa.

**Vòng đời handler:** Tạo file handler một lần trong giai đoạn khởi tạo, đóng nó tại shutdown do thành phần sở hữu thực hiện. Không tạo một `FileHandler` mới trong mỗi khối `catch`, vì thao tác này gây overhead, tranh quyền khóa tệp và khả năng phân tán log vào nhiều file.

## 8. Formatter tùy biến có thể làm mất stack trace

Một formatter tối giản thường trông như sau:

```java
import java.util.logging.Formatter;
import java.util.logging.LogRecord;

Formatter messageOnly = new Formatter() {
    @Override
    public String format(LogRecord record) {
        return record.getLevel() + ": "
                + formatMessage(record) + System.lineSeparator();
    }
};
```

Đoạn minh họa này chỉ in level và message. Nó **không sử dụng `record.getThrown()`**, nên stack trace của lỗi bị bỏ khỏi đầu ra, dù ứng dụng gọi `logger.log(Level.SEVERE, "error", exception)` đúng cách.

Một formatter viết riêng muốn hiển thị cả exception có thể thực hiện:

```java
import java.io.PrintWriter;
import java.io.StringWriter;
import java.util.logging.Formatter;
import java.util.logging.LogRecord;

Formatter withThrowable = new Formatter() {
    @Override
    public String format(LogRecord record) {
        StringBuilder result = new StringBuilder();
        result.append(record.getLevel())
              .append(": ")
              .append(formatMessage(record))
              .append(System.lineSeparator());

        Throwable error = record.getThrown();
        if (error != null) {
            StringWriter buffer = new StringWriter();
            error.printStackTrace(new PrintWriter(buffer));
            result.append(buffer);
        }
        return result.toString();
    }
};
```

Đoạn này là **minh họa code dùng bên trong method/class**, cần đặt import ở đầu file. `StringWriter` giữ văn bản trong bộ nhớ, còn `PrintWriter` nhận stack trace từ `Throwable.printStackTrace(PrintWriter)`. `StringBuilder.append(buffer)` gọi `toString()` của `StringWriter` để nối nội dung.

Điểm đánh đổi: cách này tạo ra chuỗi lớn chứa stack trace cho mỗi record có exception. Với logging ở mức lỗi cao tần suất lớn, điều đó có thể tăng bộ nhớ, CPU và lượng dữ liệu. Formatter thực tế cũng cần thời gian, tên logger, thông tin tương quan và định dạng thống nhất; không nên thay `SimpleFormatter` bằng formatter tối giản nếu chưa kiểm thử kỹ việc ghi Throwable.

## 9. Ghi stack trace với SLF4J / Logback: hiểu đúng overload

Trong ứng dụng Java dùng SLF4J và Logback hoặc một backend tương thích, nhiều mức log nhận `Throwable` làm tham số để backend hiển thị stack trace.

Ví dụ **minh họa cần dependency SLF4J và backend**:

```java
try {
    paymentService.charge(orderId);
} catch (PaymentException exception) {
    log.error("Payment failed for orderId={}", orderId, exception);
}
```

Ở đây giả định `log` là `org.slf4j.Logger` và các class/service đã tồn tại. Khi dùng overload/varargs phù hợp, SLF4J nhận `Throwable` cuối cùng làm throwable của sự kiện, còn `{}` là placeholder cho `orderId`. Điều kiện chính xác về API cần theo phiên bản SLF4J; nên kiểm tra output backend khi thiết kế formatter hoặc structured logging.

Một cách viết dễ làm mất thông tin:

```java
log.error("Payment failed: {}", exception.getMessage());
```

Lời gọi này chỉ truyền **chuỗi message** của exception vào placeholder và thông thường không đính kèm `Throwable`, nên không tự có stack frames. Cũng không nên tạo chuỗi từ `exception.toString()` rồi tưởng rằng backend vẫn nhận được exception.

Với Spring Boot, API của SLF4J thường dùng trong application code; nhưng định dạng stack trace do backend/encoder và cấu hình logging quyết định. `java.util.logging.Logger.log(Level, String, Throwable)` và `org.slf4j.Logger.error(...)` là hai API khác nhau; không trộn cú pháp.

## 10. Log một lần ở ranh giới xử lý hợp lý

Exception thường đi qua nhiều lớp: repository → service → controller → HTTP error handler. Nếu tầng nào cũng bắt và log cả stack trace, một lỗi gốc có thể xuất hiện nhiều lần.

Ví dụ luồng không mong muốn:

```text
Repository: SEVERE + stack trace
    ↓ rethrow
Service: SEVERE + cùng stack trace
    ↓ rethrow
HTTP handler: SEVERE + cùng stack trace
```

Hệ quả là log nhiều dòng trùng lặp, khó xác định lỗi thực sự được xử lý ở đâu, tăng dung lượng và có thể khiến cảnh báo lặp.

Cách lựa chọn:

- Nếu lớp thấp **không xử lý được lỗi** và chỉ chuyển tiếp, có thể **throw/wrap giữ cause** để lớp có trách nhiệm quyết định mức log và response.
- Ở **ranh giới xử lý cuối cùng** (ví dụ job runner, controller advice, message consumer hoặc entrypoint), ghi exception với đủ ngữ cảnh một lần nếu lỗi cần được báo.
- Nếu lớp thấp có thông tin đặc biệt không thể khôi phục ở tầng trên, thêm ngữ cảnh khi wrap hoặc ghi một bản ghi có mục đích rõ ràng, tránh in đầy đủ cùng stack trace lặp đi lặp lại.
- Một exception dự kiến và đã xử lý bình thường có thể chỉ cần log mức thấp hoặc không cần stack trace; lỗi chưa được xử lý hoặc ảnh hưởng khả dụng thường cần stack trace khi chẩn đoán.

**Không phải quy tắc cứng “chỉ được log một lần”**: trong một số hệ thống, log ở nhiều boundary có mục đích khác nhau. Nguyên tắc là tránh ghi trùng **cùng một thông tin** mà không bổ sung giá trị chẩn đoán.

## 11. Khi nào không nên ghi toàn bộ stack trace?

Stack trace có ích nhưng không phải mọi tình huống đều cần nó:

| Tình huống | Gợi ý |
| --- | --- |
| Exception lập trình không dự kiến, tác vụ thất bại | Log `Throwable` đầy đủ ở boundary thích hợp |
| Lỗi I/O, timeout, kết nối cơ sở dữ liệu chưa rõ nguyên nhân | Log full stack trace và ngữ cảnh an toàn |
| Validation thất bại thường xuyên, đầu vào người dùng sai dự kiến | Có thể chỉ log ngắn hoặc dùng metric, tránh noise |
| Hủy request/công việc theo tín hiệu dự kiến | Có thể không cần stack trace; giữ trạng thái và lý do |
| Một lỗi được retry nhiều lần | Tránh in lại full stack cho mọi lần retry nếu gây ngập log; ghi tóm tắt từng lần và chi tiết khi thất bại cuối |
| Exception bị chuyển thành lỗi nghiệp vụ có thể khôi phục | Chọn level và thông tin hợp lý với ngữ cảnh xử lý |

Mức log không nhất thiết đồng nhất với loại exception. Ví dụ `IllegalArgumentException` phát sinh từ input người dùng đã được xử lý có thể không đáng `SEVERE`; cũng kiểu exception ấy do lỗi cấu hình không mong muốn ở startup lại có thể là sự cố nghiêm trọng.

## 12. Bảo mật, quyền riêng tư và dữ liệu log

Stack trace có thể làm lộ:

- Tên package/class/method, file và vị trí mã nguồn.
- Chuỗi message exception chứa đường dẫn file, connection string, câu SQL, thông tin truy vấn hoặc định danh người dùng.
- Thông tin nằm trong message do ứng dụng tự thêm vào khi bọc exception.

**Không đưa trực tiếp toàn bộ stack trace kỹ thuật vào HTTP response cho người dùng cuối**. Thay vào đó, trả mã lỗi và thông báo an toàn; giữ chi tiết trong hệ thống log được bảo vệ. Khi log, hạn chế ghi mật khẩu, token, API key, cookie xác thực, số thẻ, body request và dữ liệu cá nhân nhạy cảm. Không giả định rằng “chỉ stack trace” thì không có dữ liệu nhạy cảm: `Throwable.getMessage()` và message của cause có thể đã chứa dữ liệu đầu vào.

Để liên kết nhiều sự kiện, log thêm `request_id` hoặc `trace_id` an toàn ở context (ví dụ MDC khi backend hỗ trợ), nhưng không ghi raw token hoặc PII làm ID. Thiết lập kiểm soát truy cập, retention, xoay vòng file và giám sát dung lượng. Stack trace dài có thể bị cắt bởi nền tảng thu thập log, giới hạn kích thước sự kiện hoặc encoder; kiểm tra end-to-end theo backend sử dụng.

## 13. Các trường hợp khó và cách chẩn đoán

### 13.1. Logger nhận exception nhưng không xuất stack trace

Kiểm tra:

1. Lời gọi có truyền nguyên `Throwable` vào overload hỗ trợ không?
2. Logger level và handler level có chấp nhận bản ghi không?
3. Formatter/encoder có hiển thị trường `thrown`/throwable không?
4. Có `Filter` hoặc cấu hình loại bỏ bản ghi không?
5. Console/file/log collector có cắt bớt nội dung dài không?
6. Exception có stack trace thật hay đã được tạo với stack trace bị vô hiệu hóa vì lý do hiệu năng?

Trong JUL, `LogRecord.getThrown()` giúp formatter truy cập object lỗi; `SimpleFormatter` đã hỗ trợ in stack trace. Nếu thay bằng formatter chỉ lấy `getMessage()`, phần stack trace sẽ biến mất ở đích ghi.

### 13.2. Cùng lỗi xuất hiện hai lần

Kiểm tra cả **nơi gọi logger** và **cấu hình handler**. Có thể vì hai tầng đều log cùng Throwable, hoặc một logger con và root cùng gắn handler và cho phép parent propagation. Dùng `setUseParentHandlers(false)` chỉ khi logger con đã có handler phù hợp; nếu không, bạn có thể vô tình làm mất log.

### 13.3. Stack trace không chỉ ra nơi người dùng thấy lỗi

Stack trace của một `Throwable` chủ yếu phản ánh call stack khi nó được tạo hoặc `fillInStackTrace()` được gọi. Nếu lỗi được **bắt rồi truyền sang thread khác**, hoặc một `CompletableFuture` bọc lỗi trong `CompletionException`, stack trace có thể gồm khung lời gọi ở thời điểm phát sinh và các wrapper ở thời điểm quan sát. Hãy xem **cause chain** và context của tác vụ bất đồng bộ để nối các giai đoạn.

### 13.4. Stack trace không đủ dữ liệu ngữ cảnh

Stack trace cho biết đường gọi hàm nhưng không tự nêu đơn hàng nào, cấu hình nào hoặc request nào dẫn đến lỗi. Cần message có ngữ cảnh an toàn, log correlation ID và có thể distributed trace để thấy đường đi của một request xuyên dịch vụ. Ghi một chuỗi dài từ `exception.toString()` không thể thay thế dữ liệu context đúng cách.

### 13.5. Nội dung lỗi gốc bị mất khi bọc exception

Nếu chỉ tạo exception mới với chuỗi message, hãy kiểm tra constructor có nhận cause không. Khi cần giữ nguyên lỗi, truyền `cause` và log exception ở lớp chịu trách nhiệm. Nếu stack trace thiếu frame, phân biệt việc code bắt rồi ném wrapper, hoạt động của các thư viện, và chính sách formatter/collector.

## 14. Checklist trước khi đưa exception logging vào production

1. **Chọn boundary:** vị trí nào thực sự chịu trách nhiệm báo lỗi và quyết định log level?
2. **Truyền Throwable:** dùng overload nhận exception, tránh chỉ log `getMessage()`.
3. **Giữ cause:** bọc exception bằng constructor có tham số `Throwable cause` khi chuyển tầng.
4. **Kiểm tra formatter:** stack trace, cause và suppressed exceptions có được hiển thị đầy đủ ở console/file/backend không?
5. **Kiểm tra mức lọc:** cả logger và handler/encoder/filter có chấp nhận bản ghi không?
6. **Tránh trùng:** kiểm tra log ở nhiều tầng và handler của logger cha.
7. **Giữ ngữ cảnh an toàn:** tên thao tác, ID tương quan; tránh dữ liệu bí mật trong message.
8. **Kiểm soát dung lượng:** chính sách lưu trữ, rotation, giới hạn log quá dài và retention.
9. **Kiểm thử lỗi thật:** tạo lỗi có cause hoặc suppressed exception, xác nhận dữ liệu cuối cùng trong hệ thống thu thập.
10. **Phân biệt output và response:** log kỹ thuật ở hệ thống nội bộ; phản hồi bên ngoài cung cấp thông tin vừa đủ và an toàn.

## 15. Câu hỏi tự kiểm tra

**Câu 1:** Vì sao `logger.severe(exception.getMessage())` thường không có stack trace?  
Vì lời gọi chỉ truyền chuỗi message; nó không đính kèm `Throwable` vào `LogRecord`.

**Câu 2:** Cách ghi exception có stack trace trong JUL là gì?  
Dùng `logger.log(Level.SEVERE, "Action failed", exception)` hoặc level thích hợp, đồng thời cấu hình formatter/handler hỗ trợ Throwable.

**Câu 3:** `printStackTrace()` mặc định ghi vào đâu?  
Vào `System.err`; nó không tự đi qua logger, level, filter hoặc handler của ứng dụng.

**Câu 4:** Làm sao giữ stack trace lỗi gốc khi đổi `IOException` sang `IllegalStateException`?  
Dùng constructor nhận cause, ví dụ `new IllegalStateException("Cannot load config", cause)`.

**Câu 5:** Trong try-with-resources, lỗi lúc đóng tài nguyên có thể nằm ở đâu?  
Trong danh sách `exception.getSuppressed()` của lỗi chính; formatter in đầy đủ Throwable có thể hiển thị mục `Suppressed:`.

**Câu 6:** Đã truyền đúng `Throwable` cho JUL mà vẫn không thấy frames, nên kiểm tra gì trước?  
Kiểm tra formatter có đọc `LogRecord.getThrown()` hay không, tiếp đến level, filter, handler, đích log và giới hạn của collector.

**Câu 7:** Stack trace và distributed trace có giống nhau?  
Không. Stack trace là chuỗi frame của một Throwable; distributed trace gồm các span thể hiện đường đi và thời lượng xử lý xuyên thao tác hoặc service.

**Ghi nhớ:** Muốn ghi stack trace đúng trong Java, hãy **truyền nguyên đối tượng `Throwable` cho API logging**, giữ cause khi bọc lỗi và dùng formatter hỗ trợ exception. Ghi đủ ngữ cảnh để tìm nguyên nhân, đồng thời tránh log trùng, lộ dữ liệu và bùng nổ dung lượng.
