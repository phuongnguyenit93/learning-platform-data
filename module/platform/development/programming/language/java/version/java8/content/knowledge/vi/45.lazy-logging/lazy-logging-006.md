# Kiểm thử nội dung log cùng chi phí tạo thông điệp trong Java 8

## 1. Vì sao cần kiểm tra cả log lẫn chi phí tạo thông điệp?

Logging giúp quan sát ứng dụng: request nào đã được xử lý, một thao tác mất bao lâu, nhánh nghiệp vụ nào được chọn, lỗi nào xảy ra và nguyên nhân có thể nằm ở đâu. Một dòng log hữu ích cần đáp ứng hai yêu cầu: **nội dung đúng** và **chi phí hợp lý**.

Ví dụ:

~~~java
logger.fine("Request state: " + buildExpensiveSnapshot());
~~~

Java đánh giá biểu thức truyền vào phương thức trước khi gọi fine. Vì vậy buildExpensiveSnapshot() vẫn chạy kể cả khi level FINE không được ghi. Nếu snapshot phải duyệt collection lớn, gọi nhiều getter hoặc serialize object, chi phí vẫn xuất hiện trên đường xử lý chính.

Java 8 đã cung cấp overload nhận Supplier<String> cho java.util.logging.Logger:

~~~java
logger.fine(() -> "Request state: " + buildExpensiveSnapshot());
~~~

Nếu effective level của logger không cho phép FINE, supplier không được gọi và phần dựng message bên trong được bỏ qua. Đây là cách phù hợp cho thông điệp debug đắt tiền trong Java 8 trở lên.

Bài Knowledge **“Kiểm thử nội dung log cùng chi phí tạo thông điệp”** thuộc nhóm **Logging theo nhu cầu**, module **Java 8**. Bài tập trung vào java.util.logging (JUL), API có sẵn trong JDK: kiểm tra LogRecord, dùng Handler bắt log trong test, định dạng message có tham số, giữ exception trong record, kiểm soát logger level và handler level, lazy logging với Supplier, so sánh parameterized message với nối chuỗi, kiểm chứng chi phí tạo object và cách benchmark. Các API được dùng đều có trong Java 8 và tiếp tục được hỗ trợ ở Java hiện đại.

**Mục tiêu:** test được log như một phần của hợp đồng ứng dụng, đồng thời chứng minh bằng counter rằng phần tạo message đắt tiền có thực sự bị bỏ qua khi level không bật. Không suy ra hiệu năng từ một dòng code trông gọn; hãy đo đúng workload khi cần quyết định tối ưu.

## 2. Những thành phần cần hiểu trong java.util.logging

JUL chia quá trình logging thành các phần:

| Thành phần | Vai trò |
| --- | --- |
| **Logger** | Nhận yêu cầu log, kiểm tra effective level và filter của logger, tạo/chuyển LogRecord |
| **Level** | Mức độ quan trọng và ngưỡng lọc log |
| **LogRecord** | Giữ level, message, parameters, exception, logger name và metadata của sự kiện |
| **Handler** | Nhận record, kiểm tra level/filter riêng, sau đó ghi ra console, file, stream hoặc sink khác |
| **Formatter** | Chuyển LogRecord thành chuỗi đầu ra; thường định dạng tham số và localization |
| **Filter** | Quyết định có chấp nhận một log request/record hay không |
| **Supplier<String>** | Cung cấp message khi logger cho phép level tương ứng |

Một yêu cầu log thường đi qua luồng:

~~~text
logger.info(...)
     |
     v
kiểm tra effective Logger level
     |
     v
tạo LogRecord / lấy message từ Supplier nếu dùng overload lazy
     |
     v
Logger Filter (nếu có)
     |
     v
các Handler được đăng ký
     |
     +--> Handler level / Handler Filter
     |
     v
Formatter tạo text
     |
     v
console, file, socket, collector hoặc sink khác
~~~

Có hai điều quan trọng khi viết test:

- Logger.isLoggable(level) phản ánh **effective level của logger**, có tính đến level kế thừa từ logger cha. Nó không chứng minh một handler cụ thể sẽ ghi record ra sink.
- Handler có level và filter riêng. Logger có thể cho phép FINE, nhưng handler chỉ nhận WARNING trở lên; record FINE vẫn không xuất hiện ở handler đó.

### Các level chuẩn

JUL có các level thường dùng, từ cao xuống thấp:

| Level | Ý nghĩa thực tế thường gặp |
| --- | --- |
| SEVERE | Lỗi nghiêm trọng khiến một chức năng không thể hoàn thành |
| WARNING | Tình trạng bất thường cần chú ý, có thể tiếp tục |
| INFO | Sự kiện vận hành có ý nghĩa |
| CONFIG | Thông tin cấu hình |
| FINE | Chi tiết debug ở mức cơ bản |
| FINER | Chi tiết debug sâu hơn |
| FINEST | Trace chi tiết nhất |

Ngoài ra có OFF để tắt và ALL để cho phép tất cả level. Khi logger đặt ngưỡng INFO, các level INFO, WARNING, SEVERE được cho phép; CONFIG, FINE, FINER, FINEST bị loại ở bước kiểm tra level.

**Không dùng getLevel() == Level.FINE để quyết định log có bật hay không.** getLevel() có thể trả null khi logger kế thừa level từ cha. Dùng isLoggable(Level.FINE) để kiểm tra effective level.

## 3. LogRecord là đối tượng nên kiểm tra trong unit test

Nếu test chỉ đọc chuỗi console do SimpleFormatter tạo ra, kết quả có thể thay đổi theo thời gian chạy và timezone, thread thực thi, source class/method, cấu hình Formatter, định dạng stack trace, locale, resource bundle, handler và môi trường test.

Phần lớn test nghiệp vụ chỉ cần xác minh **record**:

- record.getLevel() có đúng level không?
- record.getMessage() có đúng message/template không?
- record.getParameters() có đúng tham số không?
- record.getThrown() có giữ đúng exception không?
- record.getLoggerName() có thuộc logger mong muốn không?
- Nếu cần kiểm chuỗi đã format, Formatter.formatMessage(record) có tạo nội dung đúng không?

Với message có tham số, getMessage() thường trả **template gốc**, ví dụ "Processed {0} rows for {1}". Các đối số nằm trong getParameters(). Formatter mới xử lý localization và định dạng kiểu MessageFormat.

### Bắt log bằng Handler riêng

Trong test, tạo logger độc lập, tắt truyền lên logger cha và gắn một handler chỉ lưu record:

~~~java
static final class CaptureHandler extends Handler {
    final List<LogRecord> records = new ArrayList<LogRecord>();

    @Override
    public void publish(LogRecord record) {
        if (isLoggable(record)) {
            records.add(record);
        }
    }

    @Override public void flush() {}
    @Override public void close() {}
}
~~~

Cấu hình logger:

~~~java
Logger logger = Logger.getAnonymousLogger();
CaptureHandler handler = new CaptureHandler();

logger.setUseParentHandlers(false);
logger.setLevel(Level.ALL);
handler.setLevel(Level.ALL);
logger.addHandler(handler);
~~~

Logger.getAnonymousLogger() tạo logger riêng cho test, tránh thay đổi logger có tên mà code production khác có thể dùng. setUseParentHandlers(false) tránh ghi trùng ra console hoặc handler toàn cục. Đặt cả logger và handler ở ALL để test không vô tình lọc mất record.

Sau test phải tháo handler:

~~~java
try {
    // Thực hiện và kiểm tra logging.
} finally {
    logger.removeHandler(handler);
    handler.close();
}
~~~

Trong test nhiều luồng, danh sách record nên là collection thread-safe hoặc handler tự đồng bộ publish(). Ví dụ trong bài chạy một luồng nên ArrayList đủ dùng.

**Không cần test timestamp, thread id hoặc nguyên văn toàn bộ dòng console** nếu chúng không thuộc hợp đồng nghiệp vụ. Hãy test dữ liệu log ổn định trước, rồi có integration test riêng cho cấu hình sink/formatter nếu cần.

## 4. Chương trình 1 — kiểm tra supplier chỉ tạo message khi level được bật

Tệp **SupplierLazinessDemo.java** dùng AtomicInteger đếm số lần supplier được gọi. Khi logger đặt INFO, lời gọi fine(Supplier) không chạy supplier. Sau khi bật FINE, supplier được gọi đúng một lần.

~~~java
import java.util.*;
import java.util.logging.*;
import java.util.concurrent.atomic.AtomicInteger;

public class SupplierLazinessDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    static final class CaptureHandler extends Handler {
        final List<LogRecord> records =
            new ArrayList<LogRecord>();

        public void publish(LogRecord record) {
            if (isLoggable(record)) records.add(record);
        }
        public void flush() {}
        public void close() {}
    }

    public static void main(String[] args) {
        Logger logger = Logger.getAnonymousLogger();
        CaptureHandler handler = new CaptureHandler();

        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);
        handler.setLevel(Level.ALL);
        logger.addHandler(handler);

        AtomicInteger builds = new AtomicInteger();

        try {
            logger.fine(() -> {
                builds.incrementAndGet();
                return "expensive snapshot";
            });

            int disabledBuilds = builds.get();
            int disabledRecords = handler.records.size();

            logger.setLevel(Level.FINE);
            logger.fine(() -> {
                builds.incrementAndGet();
                return "expensive snapshot";
            });

            check(disabledBuilds == 0, "supplier disabled");
            check(disabledRecords == 0, "no disabled record");
            check(builds.get() == 1, "supplier enabled");
            check(handler.records.size() == 1, "one record");
            check("expensive snapshot".equals(
                handler.records.get(0).getMessage()), "message");

            System.out.println(
                "supplierCallsWhenDisabled=" + disabledBuilds);
            System.out.println(
                "recordsWhenDisabled=" + disabledRecords);
            System.out.println(
                "supplierCallsAfterEnable=" + builds.get());
            System.out.println(
                "capturedMessage=" +
                handler.records.get(0).getMessage());
            System.out.println("PASS");
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 8:

~~~bash
javac -encoding UTF-8 SupplierLazinessDemo.java
java SupplierLazinessDemo
~~~

Trên JDK mới, có thể ép API tương thích Java 8:

~~~bash
javac --release 8 -encoding UTF-8 SupplierLazinessDemo.java
java SupplierLazinessDemo
~~~

**Stdout đã chạy và kiểm chứng:**

~~~text
supplierCallsWhenDisabled=0
recordsWhenDisabled=0
supplierCallsAfterEnable=1
capturedMessage=expensive snapshot
PASS
~~~

Kết quả chứng minh supplier body không được gọi khi effective logger level loại FINE, và được gọi một lần khi bật FINE.

### Supplier không có nghĩa là toàn bộ logging miễn phí

Overload lazy chỉ trì hoãn **việc tạo message trong supplier** cho đến khi logger cho phép level. Vẫn có chi phí gọi phương thức, kiểm tra level và có thể tạo/capture lambda object; JIT có thể tối ưu một số trường hợp nhưng không nên hứa “không có allocation” ở mọi runtime.

Ngoài ra, supplier có thể được gọi khi logger level cho phép dù một Logger Filter hoặc Handler level/filter sau đó loại record. Do đó, supplier giảm chi phí khi level tắt; nó không bảo đảm message chắc chắn được ghi ra sink.

## 5. Nối chuỗi, parameterized message và Supplier khác nhau thế nào?

Ba cách thường gặp:

### Cách A — nối chuỗi trước khi gọi logger

~~~java
logger.fine("Request state: " + buildSnapshot());
~~~

buildSnapshot() và phép tạo chuỗi xảy ra **trước khi** logger kiểm tra level. Khi FINE tắt, chi phí vẫn phát sinh.

### Cách B — template với tham số

~~~java
logger.log(Level.FINE,
    "Request {0} contains {1} items",
    new Object[] { requestId, itemCount });
~~~

JUL lưu template và parameters trong LogRecord; formatter thường định dạng chúng sau. Tuy nhiên, biểu thức requestId, itemCount và việc tạo Object[] vẫn được đánh giá trước lời gọi log(...). Nếu tạo tham số cần tính toán đắt tiền, công việc đó vẫn xảy ra ngay cả khi level không bật.

Parameterized message giúp tránh nối chuỗi thủ công và cho phép formatter localization/formatting; **nó không tự làm cho biểu thức tham số trở nên lazy**.

### Cách C — Supplier

~~~java
logger.fine(() ->
    "Request state: " + buildSnapshot());
~~~

Logger kiểm tra effective level trước; chỉ khi level được cho phép, supplier mới được gọi để dựng message. Đây là lựa chọn trực tiếp cho công việc dựng message đắt tiền trong JUL Java 8.

### Dùng isLoggable khi cần tương thích API không có Supplier

~~~java
if (logger.isLoggable(Level.FINE)) {
    logger.fine("Request state: " + buildSnapshot());
}
~~~

Guard tránh chạy buildSnapshot() khi logger không bật FINE. Trong JUL Java 8, overload nhận Supplier<String> thường gọn hơn. Guard vẫn hữu ích khi API logging đang dùng không có overload lazy tương đương.

Đừng kiểm tra logger.getLevel() trực tiếp: level có thể được kế thừa từ cha. isLoggable() kiểm tra effective level theo cấu hình hiện tại.

## 6. Chương trình 2 — template và tham số được formatter định dạng

Tệp **ParameterizedLogDemo.java** bắt một LogRecord, kiểm tra template gốc và tham số, rồi dùng Formatter.formatMessage() để xác minh nội dung sau định dạng. Cách này không phụ thuộc SimpleFormatter hoặc timestamp.

~~~java
import java.util.*;
import java.util.logging.*;

public class ParameterizedLogDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    static final class CaptureHandler extends Handler {
        final List<LogRecord> records =
            new ArrayList<LogRecord>();

        public void publish(LogRecord record) {
            if (isLoggable(record)) records.add(record);
        }
        public void flush() {}
        public void close() {}
    }

    public static void main(String[] args) {
        Logger logger = Logger.getAnonymousLogger();
        CaptureHandler handler = new CaptureHandler();

        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);
        handler.setLevel(Level.ALL);
        logger.addHandler(handler);

        try {
            logger.log(Level.INFO,
                "Processed {0} rows for {1}",
                new Object[] {
                    Integer.valueOf(3), "orders"
                });

            LogRecord record = handler.records.get(0);
            Object[] parameters = record.getParameters();

            java.util.logging.Formatter formatter =
                new java.util.logging.Formatter() {
                    public String format(LogRecord r) {
                        return formatMessage(r);
                    }
                };

            String formatted = formatter.format(record);

            check("Processed {0} rows for {1}".equals(
                record.getMessage()), "raw template");
            check(parameters.length == 2, "parameter count");
            check("Processed 3 rows for orders".equals(
                formatted), "formatted message");

            System.out.println("rawMessage=" + record.getMessage());
            System.out.println("formattedMessage=" + formatted);
            System.out.println("parameterCount=" + parameters.length);
            System.out.println("PASS");
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }
    }
}
~~~

~~~bash
javac --release 8 -encoding UTF-8 ParameterizedLogDemo.java
java ParameterizedLogDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
rawMessage=Processed {0} rows for {1}
formattedMessage=Processed 3 rows for orders
parameterCount=2
PASS
~~~

JUL dùng cú pháp tham số kiểu MessageFormat ({0}, {1}), không phải cú pháp {} của một số logging framework bên ngoài. Không trộn cú pháp giữa các thư viện; đọc API formatter của framework đang dùng.

### Một lưu ý với tham số là object mutable

LogRecord lưu tham chiếu tới các parameter object. Formatter có thể chạy muộn hơn lúc gọi log, đặc biệt với handler xử lý bất đồng bộ. Nếu object bị thay đổi trước lúc formatter gọi toString(), log có thể phản ánh trạng thái mới thay vì trạng thái lúc phát sinh sự kiện.

Khi cần snapshot chính xác, truyền giá trị bất biến hoặc tạo snapshot nhỏ, an toàn trước khi ghi record. Nếu snapshot đắt tiền, kết hợp với Supplier để chỉ tạo khi logger level cho phép.

## 7. Level của Logger và Handler là hai lớp lọc riêng

Một logger có thể cho phép FINE, nhưng handler không nhận mức thấp hơn WARNING. Ngược lại, handler đặt ALL cũng không thể phục hồi record đã bị logger loại ở bước effective level.

Để test chính xác, cần thiết lập cả hai ngưỡng:

- logger.setLevel(Level.ALL) cho phép logger chuyển mọi level tới handler.
- handler.setLevel(Level.WARNING) chỉ giữ record từ WARNING trở lên.
- logger.setUseParentHandlers(false) ngăn record đi sang console/handler toàn cục.
- Handler test phải gọi isLoggable(record) trong publish() để tôn trọng level/filter của chính nó.

Logger.isLoggable(Level.FINE) có thể trả true trong khi handler không lưu record FINE. Đừng dùng isLoggable() làm bằng chứng rằng log chắc chắn đã được ghi xuống file.

## 8. Chương trình 3 — handler loại FINE và INFO dù logger cho phép

Tệp **HandlerLevelDemo.java** đặt logger ở ALL, handler ở WARNING, rồi gửi ba record. Chỉ WARNING được handler lưu.

~~~java
import java.util.*;
import java.util.logging.*;

public class HandlerLevelDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    static final class CaptureHandler extends Handler {
        final List<LogRecord> records =
            new ArrayList<LogRecord>();

        public void publish(LogRecord record) {
            if (isLoggable(record)) records.add(record);
        }
        public void flush() {}
        public void close() {}
    }

    public static void main(String[] args) {
        Logger logger = Logger.getAnonymousLogger();
        CaptureHandler handler = new CaptureHandler();

        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);
        handler.setLevel(Level.WARNING);
        logger.addHandler(handler);

        try {
            logger.fine("debug detail");
            logger.info("request accepted");
            logger.warning("retry scheduled");

            check(handler.records.size() == 1,
                "handler threshold");
            check(handler.records.get(0).getLevel()
                == Level.WARNING, "warning retained");
            check(logger.isLoggable(Level.FINE),
                "logger allows FINE");

            System.out.println("loggerAllowsFine="
                + logger.isLoggable(Level.FINE));
            System.out.println("handlerThreshold="
                + handler.getLevel().getName());
            System.out.println("capturedRecords="
                + handler.records.size());
            System.out.println("capturedLevel="
                + handler.records.get(0).getLevel().getName());
            System.out.println("PASS");
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }
    }
}
~~~

~~~bash
javac --release 8 -encoding UTF-8 HandlerLevelDemo.java
java HandlerLevelDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
loggerAllowsFine=true
handlerThreshold=WARNING
capturedRecords=1
capturedLevel=WARNING
PASS
~~~

Ví dụ cũng giải thích vì sao test lazy message chỉ nên kiểm điều kiện level ở logger khi mục tiêu là xác minh supplier không chạy. Nếu logger bật FINE nhưng handler bỏ FINE, supplier vẫn có thể được gọi trước khi handler lọc record.

## 9. Kiểm thử exception: giữ Throwable trong LogRecord

Khi ghi lỗi, dùng overload nhận Throwable:

~~~java
logger.log(Level.SEVERE, "Could not complete operation", exception);
~~~

Không nên chỉ nối exception.toString() vào chuỗi. Overload nhận Throwable lưu exception vào LogRecord.getThrown(), để formatter có thể xuất stack trace theo cấu hình. Test nên xác minh **đúng object exception** hoặc ít nhất đúng loại/cause, không nhất thiết so toàn bộ stack trace.

Một lỗi thường gặp:

~~~java
// Chỉ ghi text; record không giữ Throwable riêng.
logger.severe("Operation failed: " + exception);
~~~

Dòng trên có thể hiển thị exception.toString() nhưng không lưu exception trong trường thrown. Khi cần stack trace và cause, dùng overload nhận Throwable.

## 10. Chương trình 4 — kiểm tra level, message và Throwable

Tệp **ThrowableLogDemo.java** xác minh exception được lưu trong LogRecord, không phụ thuộc cách formatter in stack trace.

~~~java
import java.util.*;
import java.util.logging.*;

public class ThrowableLogDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    static final class CaptureHandler extends Handler {
        final List<LogRecord> records =
            new ArrayList<LogRecord>();

        public void publish(LogRecord record) {
            if (isLoggable(record)) records.add(record);
        }
        public void flush() {}
        public void close() {}
    }

    public static void main(String[] args) {
        Logger logger = Logger.getAnonymousLogger();
        CaptureHandler handler = new CaptureHandler();

        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);
        handler.setLevel(Level.ALL);
        logger.addHandler(handler);

        IllegalStateException failure =
            new IllegalStateException("invalid transition");

        try {
            logger.log(Level.SEVERE,
                "Could not complete operation", failure);

            LogRecord record = handler.records.get(0);

            check(record.getLevel() == Level.SEVERE, "level");
            check("Could not complete operation".equals(
                record.getMessage()), "message");
            check(record.getThrown() == failure, "throwable");

            System.out.println("level="
                + record.getLevel().getName());
            System.out.println("message=" + record.getMessage());
            System.out.println("throwableClass="
                + record.getThrown().getClass().getSimpleName());
            System.out.println("sameThrowable="
                + (record.getThrown() == failure));
            System.out.println("PASS");
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }
    }
}
~~~

~~~bash
javac --release 8 -encoding UTF-8 ThrowableLogDemo.java
java ThrowableLogDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
level=SEVERE
message=Could not complete operation
throwableClass=IllegalStateException
sameThrowable=true
PASS
~~~

Trong production, nên ghi exception ở đúng boundary chịu trách nhiệm xử lý hoặc chuyển lỗi, tránh ghi cùng một exception lặp ở mọi tầng rồi tạo log trùng. Không ghi password, access token, session secret hoặc dữ liệu cá nhân trong message/parameters; exception message của thư viện cũng có thể chứa thông tin nhạy cảm, nên kiểm soát sink và chính sách redaction.

## 11. Chi phí thật của việc tạo message: biểu thức nào chạy khi log bị tắt?

Xét ba biểu thức:

~~~java
// A. Nối chuỗi: phần tạo snapshot chạy ngay.
logger.fine("state=" + buildSnapshot());

// B. Parameterized JUL: đối số vẫn được đánh giá ngay.
logger.log(Level.FINE, "state={0}",
    new Object[] { buildSnapshot() });

// C. Supplier: body chỉ chạy nếu logger cho phép FINE.
logger.fine(() -> "state=" + buildSnapshot());
~~~

Khi FINE bị tắt:

| Cách gọi | buildSnapshot() có chạy? | Ghi chú |
| --- | --- | --- |
| Nối chuỗi A | Có | Biểu thức đối số được đánh giá trước lời gọi |
| Parameterized B | Có | Đối số/array được tạo trước lời gọi; format có thể được trì hoãn |
| Supplier C | Không | Logger không gọi supplier khi effective level loại FINE |
| Guard if (isLoggable) | Không | Phần thân không chạy khi logger không cho phép |

Cần phân biệt hai khoản chi phí:

1. **Tạo đối số:** gọi hàm, dựng object, tạo array, đọc snapshot.
2. **Định dạng:** gọi toString(), thay {0}, tạo chuỗi cuối cùng, localization.

Parameterized JUL có thể trì hoãn việc định dạng đến Formatter, nhưng không trì hoãn việc đánh giá các biểu thức đối số. Supplier trì hoãn cả phần dựng message nằm trong supplier body cho tới khi logger cho phép level.

### Lambda có phải hoàn toàn không tốn chi phí?

Không nên hứa điều đó. Supplier có thể cần tạo/capture object tùy cách dùng và runtime; JIT có thể tối ưu một số call site. Bảo đảm quan trọng của API là **supplier body không được gọi khi level không được log**. Đây không phải cam kết rằng toàn bộ call site có zero allocation hoặc zero CPU.

### Logger Filter và Handler có thể lọc sau khi supplier đã chạy

JUL kiểm tra effective level của logger trước, sau đó mới dựng LogRecord từ supplier và đi tiếp qua filter/handler. Vì vậy nếu logger cho phép FINE nhưng một Logger Filter hoặc Handler level/filter loại record, supplier vẫn có thể đã chạy. Đặt level của logger đúng với mục tiêu vận hành sẽ giúp tránh tạo những thông điệp không cần thiết.

## 12. Chương trình 5 — đo số lần tạo object và gọi toString

Tệp **MessageCreationCostDemo.java** dùng hai counter để phân biệt:

- object đối số được tạo trước lời gọi parameterized log;
- toString() của object có thể được gọi muộn khi formatter định dạng record;
- supplier không tạo object khi level bị tắt;
- khi level bật, supplier tạo object và nối chuỗi bên trong supplier.

Đây là **kiểm thử số lần thực thi**, không phải benchmark nanosecond.

~~~java
import java.util.*;
import java.util.logging.*;
import java.util.concurrent.atomic.AtomicInteger;

public class MessageCreationCostDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    static final class ExpensiveValue {
        final AtomicInteger toStringCalls;

        ExpensiveValue(AtomicInteger calls) {
            toStringCalls = calls;
        }

        public String toString() {
            toStringCalls.incrementAndGet();
            return "snapshot";
        }
    }

    static final class CaptureHandler extends Handler {
        final List<LogRecord> records =
            new ArrayList<LogRecord>();

        public void publish(LogRecord record) {
            if (isLoggable(record)) records.add(record);
        }
        public void flush() {}
        public void close() {}
    }

    static ExpensiveValue create(
            AtomicInteger creations,
            AtomicInteger toStringCalls) {
        creations.incrementAndGet();
        return new ExpensiveValue(toStringCalls);
    }

    public static void main(String[] args) {
        Logger logger = Logger.getAnonymousLogger();
        CaptureHandler handler = new CaptureHandler();

        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);
        handler.setLevel(Level.ALL);
        logger.addHandler(handler);

        AtomicInteger creations = new AtomicInteger();
        AtomicInteger toStringCalls = new AtomicInteger();

        try {
            logger.log(Level.FINE, "value={0}",
                new Object[] {
                    create(creations, toStringCalls)
                });

            logger.fine(() -> "value="
                + create(creations, toStringCalls));

            if (logger.isLoggable(Level.FINE)) {
                logger.fine("guarded="
                    + create(creations, toStringCalls));
            }

            int createdWhileDisabled = creations.get();
            int disabledToStrings = toStringCalls.get();

            logger.setLevel(Level.FINE);
            logger.log(Level.FINE, "value={0}",
                new Object[] {
                    create(creations, toStringCalls)
                });

            int toStringsBeforeFormatting =
                toStringCalls.get();

            java.util.logging.Formatter formatter =
                new java.util.logging.Formatter() {
                    public String format(LogRecord record) {
                        return formatMessage(record);
                    }
                };

            String formatted =
                formatter.format(handler.records.get(0));

            logger.fine(() -> "value="
                + create(creations, toStringCalls));

            check(createdWhileDisabled == 1,
                "only eager parameter expression created");
            check(disabledToStrings == 0,
                "no disabled formatting");
            check(toStringsBeforeFormatting == 0,
                "parameter formatting deferred");
            check("value=snapshot".equals(formatted),
                "formatted parameter");
            check(creations.get() == 3,
                "enabled creation count");
            check(toStringCalls.get() == 2,
                "format and supplier");

            System.out.println("createdWhileDisabled="
                + createdWhileDisabled);
            System.out.println("toStringCallsWhileDisabled="
                + disabledToStrings);
            System.out.println("toStringCallsBeforeFormatter="
                + toStringsBeforeFormatting);
            System.out.println("formatted=" + formatted);
            System.out.println("totalCreations="
                + creations.get());
            System.out.println("totalToStringCalls="
                + toStringCalls.get());
            System.out.println("PASS");
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }
    }
}
~~~

~~~bash
javac --release 8 -encoding UTF-8 MessageCreationCostDemo.java
java MessageCreationCostDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
createdWhileDisabled=1
toStringCallsWhileDisabled=0
toStringCallsBeforeFormatter=0
formatted=value=snapshot
totalCreations=3
totalToStringCalls=2
PASS
~~~

Đọc kết quả:

1. Khi FINE tắt, lời gọi parameterized vẫn tạo một ExpensiveValue, nên createdWhileDisabled=1.
2. Supplier và guard không tạo thêm object trong cùng giai đoạn.
3. toString() chưa chạy khi record được bắt; formatter mới gọi nó, vì vậy toStringCallsBeforeFormatter=0.
4. Khi bật FINE, parameterized message tạo object thứ hai.
5. Formatter gọi toString() một lần.
6. Supplier chạy ở lần log tiếp theo, tạo object thứ ba và nối chuỗi, làm toString() chạy lần hai.

Điều này giải thích vì sao parameterized message có lợi cho formatting nhưng không đủ khi **bản thân biểu thức tạo tham số đã đắt**. Khi cần lazy toàn bộ snapshot, dùng Supplier hoặc guard.

## 13. Kiểm thử hợp đồng log của một service

Không nên chỉ test một logger giả lập gọi trực tiếp trong main. Một unit test có ích nên kiểm tra service thực sự phát log đúng ở các nhánh quan trọng:

- thao tác thành công tạo INFO với mã nghiệp vụ và số lượng;
- FINE debug chỉ được tạo khi logger bật;
- lỗi phát sinh tạo record đúng level và giữ Throwable;
- level tắt không làm chạy phần dựng thông tin debug đắt tiền.

Nên assert nội dung có ý nghĩa ổn định, ví dụ order ID và số lượng; tránh assert chuỗi chứa timestamp, hostname, thread ID hoặc absolute path nếu các thành phần đó không thuộc hợp đồng service.

Khi test service dùng JUL, có thể truyền Logger vào constructor để test kiểm soát level và handler. Cách này giúp tránh cấu hình logger toàn cục và tránh phải đọc file log thật trong unit test.

## 14. Chương trình 6 — test log INFO và debug lazy của OrderService

Tệp **LogContentContractDemo.java** mô phỏng service hoàn tất đơn hàng. Test kiểm tra template và parameters của INFO, rồi bật FINE và xác nhận debug supplier mới được gọi.

~~~java
import java.util.*;
import java.util.logging.*;
import java.util.concurrent.atomic.AtomicInteger;

public class LogContentContractDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    static final class CaptureHandler extends Handler {
        final List<LogRecord> records =
            new ArrayList<LogRecord>();

        public void publish(LogRecord record) {
            if (isLoggable(record)) records.add(record);
        }
        public void flush() {}
        public void close() {}
    }

    static final class OrderService {
        final Logger logger;
        final AtomicInteger debugBuilds;

        OrderService(Logger logger, AtomicInteger builds) {
            this.logger = logger;
            debugBuilds = builds;
        }

        void complete(String orderId, int items) {
            logger.log(Level.INFO,
                "Order {0} completed with {1} items",
                new Object[] {
                    orderId, Integer.valueOf(items)
                });

            logger.fine(() -> {
                debugBuilds.incrementAndGet();
                return "debug order=" + orderId
                    + ", items=" + items;
            });
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getAnonymousLogger();
        CaptureHandler handler = new CaptureHandler();

        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);
        handler.setLevel(Level.ALL);
        logger.addHandler(handler);

        AtomicInteger debugBuilds = new AtomicInteger();
        OrderService service =
            new OrderService(logger, debugBuilds);

        try {
            service.complete("O-17", 3);

            check(handler.records.size() == 1, "only INFO");

            LogRecord info = handler.records.get(0);
            check(info.getLevel() == Level.INFO, "INFO level");
            check("Order {0} completed with {1} items".equals(
                info.getMessage()), "template");
            check("O-17".equals(info.getParameters()[0]),
                "order");
            check(Integer.valueOf(3).equals(
                info.getParameters()[1]), "items");
            check(debugBuilds.get() == 0,
                "disabled supplier");

            logger.setLevel(Level.FINE);
            service.complete("O-18", 2);

            check(handler.records.size() == 3,
                "INFO and FINE records");

            LogRecord debug = handler.records.get(2);
            check(debug.getLevel() == Level.FINE, "FINE level");
            check("debug order=O-18, items=2".equals(
                debug.getMessage()), "debug message");
            check(debugBuilds.get() == 1, "built once");

            System.out.println("infoMessage=" + info.getMessage());
            System.out.println("infoOrder="
                + info.getParameters()[0]);
            System.out.println("infoItems="
                + info.getParameters()[1]);
            System.out.println("debugBuildsWhenInfoOnly=0");
            System.out.println("debugMessage="
                + debug.getMessage());
            System.out.println("totalRecords="
                + handler.records.size());
            System.out.println("PASS");
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }
    }
}
~~~

~~~bash
javac --release 8 -encoding UTF-8 LogContentContractDemo.java
java LogContentContractDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
infoMessage=Order {0} completed with {1} items
infoOrder=O-17
infoItems=3
debugBuildsWhenInfoOnly=0
debugMessage=debug order=O-18, items=2
totalRecords=3
PASS
~~~

Khi chỉ bật INFO, service phát một record INFO, tham số đúng và không tạo debug message. Khi bật FINE, lần xử lý thứ hai phát thêm một record INFO và một record FINE; supplier được gọi đúng một lần. Đây là kiểm tra nội dung lẫn lazy evaluation trong cùng một luồng nghiệp vụ.

## 15. Test nội dung log: nên kiểm gì và không nên kiểm gì?

Một ma trận thực tế:

| Mục tiêu | Assertion nên dùng |
| --- | --- |
| Mức độ log | record.getLevel() |
| Nội dung không tham số | record.getMessage() |
| Message template | record.getMessage() bằng template mong đợi |
| Tham số | record.getParameters() theo từng vị trí |
| Chuỗi sau định dạng | Formatter.formatMessage(record) |
| Exception | record.getThrown() hoặc class/cause |
| Logger đúng scope | record.getLoggerName() |
| Level bị tắt | Handler không nhận record; supplier counter vẫn 0 |
| Level bật | Supplier counter tăng đúng số lần |
| Handler threshold | Handler chỉ lưu record ở ngưỡng trở lên |
| Không log trùng | Đếm record theo sự kiện và logger |
| Resource cleanup của test | Handler đã remove/close trong finally |

Không nên mặc định assertion:

- toàn bộ output của SimpleFormatter bằng một chuỗi dài có timestamp;
- thread ID hoặc thứ tự record giữa các worker phải cố định;
- stack trace giống hệt trên mọi JDK;
- mọi handler đã được gọi chỉ vì Logger.isLoggable() trả true;
- một lần test counter bằng 0 chứng minh toàn bộ logging không allocation;
- không có record trong handler nghĩa là code không gọi logger (có thể handler/level/filter đã loại).

Nếu cần test cấu hình logging end-to-end, thêm test riêng với handler thật hoặc cấu hình triển khai. Unit test LogRecord nên tập trung vào **hợp đồng nội dung**.

## 16. Chi phí tạo message không phải toàn bộ chi phí logging

Tổng chi phí logging có thể bao gồm:

~~~text
đánh giá biểu thức và tạo tham số
       +
kiểm tra level/filter
       +
tạo LogRecord
       +
format/localization/stack trace
       +
đồng bộ, queue và chuyển thread
       +
I/O console/file/network/collector
~~~

Supplier<String> chủ yếu giúp giảm phần **tạo message** khi logger level tắt. Nó không làm I/O nhanh hơn khi log được bật, không thay đổi cách handler flush file, không làm stack trace miễn phí và không tự giới hạn lượng log được gửi tới hệ thống tập trung.

Các cách giảm chi phí hợp lý:

1. Chỉ bật FINE/FINER/FINEST khi cần chẩn đoán.
2. Dùng Supplier cho snapshot/serialization đắt tiền.
3. Dùng parameterized message cho giá trị đơn giản, tránh nối chuỗi thủ công.
4. Không log nguyên object lớn nếu chỉ cần một vài trường.
5. Không serialize cùng một object nhiều lần ở nhiều tầng.
6. Tránh log một dòng cho mỗi item trong workload khối lượng lớn nếu tổng hợp counter hoặc sampling đáp ứng nhu cầu.
7. Kiểm soát sink, retention và tốc độ ghi.
8. Không ghi secrets hoặc payload nhạy cảm để đổi lấy debug convenience.

### Khi nào dùng guard, khi nào dùng Supplier?

| Tình huống | Lựa chọn |
| --- | --- |
| JUL Java 8, dựng chuỗi debug đắt tiền | logger.fine(() -> ...) |
| API không có overload Supplier | if (logger.isLoggable(level)) |
| Message đơn giản, tham số rẻ | Parameterized logger.log(level, template, params) |
| Cần lưu Throwable/stack trace | Overload nhận Throwable |
| Handler lọc mạnh hơn logger | Cấu hình logger level phù hợp để tránh dựng message bị loại |
| Message có thể chứa thông tin nhạy cảm | Redact/whitelist trước khi log |

Một supplier nên thuần, ngắn và không có side effect nghiệp vụ. Đừng đặt cập nhật trạng thái quan trọng, gửi request mạng hoặc thay đổi database bên trong supplier: nếu level tắt, những hành động đó sẽ không chạy; nếu level bật, chúng lại chạy như một phần logging.

## 17. Đo hiệu năng: test counter khác benchmark

AtomicInteger trong các demo trả lời câu hỏi **supplier có được gọi hay không**. Nó không đo thời gian thực tế, allocation rate hoặc I/O throughput.

Nếu tối ưu logging là quyết định ảnh hưởng lớn, benchmark cần mô phỏng đúng các tình huống:

- Level bị tắt: nối chuỗi trực tiếp, parameterized log, Supplier, guard.
- Level bật với handler bỏ record hoặc sink nhẹ: đo chi phí tạo record/format.
- Level bật với sink thật: đo thêm formatter, lock, queue và I/O.
- Message rẻ và message đắt: phân biệt chi phí constant với serialize snapshot.
- Đo cả throughput, latency và allocation nếu các chỉ số đó quan trọng.

Dùng công cụ benchmark như **JMH** hoặc harness phù hợp thay vì vòng lặp System.nanoTime() tự viết rồi kết luận từ một lần chạy. Một benchmark đáng tin cần warmup JVM, nhiều measurement iteration/fork, tránh dead-code elimination, tiêu thụ kết quả và đo với workload/level/sink thực tế. JMH là thư viện/tool bên ngoài JDK; không phải API Java 8.

**Không dùng stdout console làm sink mặc định cho benchmark tạo message.** Console I/O có thể lớn hơn rất nhiều chi phí dựng chuỗi và làm sai câu hỏi đang đo. Nếu muốn biết riêng cost message, dùng sink kiểm soát được; nếu muốn biết cost vận hành, benchmark cả sink production.

## 18. Những điểm về localization và định dạng

JUL hỗ trợ ResourceBundle để dùng message key thay vì hard-code câu văn theo một ngôn ngữ. Formatter có thể lấy bản dịch rồi áp dụng tham số theo MessageFormat.

Ví dụ template:

~~~java
logger.log(Level.INFO,
    "order.completed",
    new Object[] { orderId, itemCount });
~~~

Khi logger/record có resource bundle tương ứng và formatter xử lý localization, message key được ánh xạ sang mẫu ngôn ngữ thích hợp. Khi test, cần cấu hình bundle/locale cụ thể nếu nội dung đa ngôn ngữ là hợp đồng; nếu không, test chỉ template và parameters để tránh phụ thuộc locale của máy chạy CI.

Không tự dùng String.format() cho JUL message rồi cho rằng logger sẽ lazy. String.format(...) tạo chuỗi ngay tại chỗ gọi. Nếu việc format đắt, đặt toàn bộ trong supplier:

~~~java
logger.fine(() -> String.format(
    "request=%s duration=%dms",
    requestId, durationMillis));
~~~

Với message đơn giản, parameterized JUL thường phù hợp hơn. MessageFormat của JUL có quy tắc riêng; không đồng nhất với Formatter của String.format.

## 19. Bảo mật và chất lượng nội dung log

Một message đúng về kỹ thuật vẫn có thể gây rủi ro nếu chứa dữ liệu không nên ghi. Trước khi log, cần xem xét:

- Password, API key, access token, refresh token, private key.
- Session ID, cookie, authorization header.
- Thông tin cá nhân hoặc dữ liệu thanh toán.
- SQL chứa dữ liệu đầu vào nhạy cảm.
- Payload lớn có thể gây log flooding hoặc tăng chi phí lưu trữ.
- Chuỗi đầu vào có newline/control character có thể làm giả dòng log hoặc gây khó đọc.
- Exception message do thư viện ngoài tạo ra có thể chứa URL, path hoặc thông tin nhạy cảm.

Nên log **mã định danh nội bộ đã được phép**, trạng thái, loại sự kiện và số liệu cần thiết; redact hoặc loại bỏ field nhạy cảm trước khi gửi tới handler. Logging không thay thế audit trail có kiểm soát, transaction history hoặc event store.

Không tạo message bằng cách ghép toàn bộ object tùy ý ("request=" + request) nếu toString() có thể in credential hoặc payload. Supplier giải quyết thời điểm tạo, **không tự làm nội dung an toàn**.

## 20. Những lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| logger.fine("state=" + expensive()) | expensive() chạy dù FINE tắt | Dùng Supplier hoặc isLoggable guard |
| Nghĩ parameterized log làm đối số lazy | Đối số vẫn được đánh giá trước call | Đặt phần tạo đắt tiền trong Supplier |
| Nghĩ isLoggable bảo đảm handler ghi | Handler level/filter vẫn có thể loại | Test Handler và sink riêng |
| Chỉ set logger level trong test | Handler có thể vẫn lọc record | Set cả logger và handler level |
| Không tắt parent handlers | Log test có thể lọt ra console/trùng | setUseParentHandlers(false) |
| Dùng logger có tên dùng chung | Test ảnh hưởng cấu hình test khác | Anonymous/unique logger và cleanup |
| Không remove handler | Handler còn giữ test state/reference | Remove/close trong finally |
| So sánh nguyên văn SimpleFormatter | Test phụ thuộc timestamp/locale/thread | Assert LogRecord fields |
| Kiểm message template như chuỗi đã format | Tham số chưa được áp | Dùng Formatter.formatMessage |
| Ghi exception bằng nối chuỗi | Không giữ Throwable trong record | Dùng overload nhận Throwable |
| Log toàn bộ object | toString() đắt hoặc lộ dữ liệu | Chọn field an toàn, dùng snapshot |
| Supplier có side effect nghiệp vụ | Hành vi thay đổi theo log level | Supplier chỉ dựng message |
| Cho rằng Supplier zero-allocation | Lambda/capture vẫn có thể có chi phí | Chỉ khẳng định body lazy; benchmark |
| Dùng guard theo getLevel() | Bỏ sót level kế thừa từ cha | isLoggable(level) |
| Dùng {} trong JUL | Formatter JUL không hiểu như SLF4J | Dùng {0}, {1} |
| Dùng String.format ngoài Supplier | Format xảy ra trước logger check | Đặt format trong Supplier nếu đắt |
| Benchmark một lần không warmup | Kết quả nhiễu do JIT/GC | Dùng JMH/harness chuẩn |
| Benchmark console rồi quy kết message cost | I/O chi phối kết quả | Tách benchmark message và sink |
| Log mỗi item ở volume rất cao | Tốn CPU, I/O, dung lượng | Sampling/aggregate theo nhu cầu |
| Log secret để debug nhanh | Lộ credential/PII trong sink | Redact/whitelist |

## 21. Ma trận kiểm thử nên có

| Trường hợp | Kỳ vọng |
| --- | --- |
| Logger INFO, gọi fine(Supplier) | Supplier không chạy |
| Logger FINE, gọi fine(Supplier) | Supplier chạy một lần |
| Logger INFO, nối chuỗi trước fine() | Hàm tạo chuỗi vẫn chạy |
| Logger INFO, parameterized log với factory làm argument | Factory vẫn chạy |
| Parameterized record được capture | Template và parameters còn nguyên |
| Formatter xử lý {0}/{1} | Message đã format đúng |
| Handler WARNING, logger ALL | Chỉ record WARNING trở lên được lưu |
| Logger INFO, handler ALL | FINE không tới handler |
| Logger ALL, handler ALL | Các level được test đều có thể tới handler |
| log(level,message,throwable) | getThrown() giữ đúng Throwable |
| Logger Filter loại record | Handler không nhận record |
| Handler Filter loại record | Handler không lưu record |
| Parent handlers disabled | Không phát sinh output ngoài capture handler |
| Test kết thúc | Handler được remove/close |
| Parameter object mutable | Xác minh snapshot/format timing theo thiết kế |
| Message chứa newline từ input | Sanitization theo policy |
| Message chứa token/PII | Không xuất dữ liệu nhạy cảm |
| Supplier có side effect | Test đảm bảo side effect không thuộc nghiệp vụ |
| Parallel logging | Capture handler an toàn thread và thứ tự không giả định |
| Benchmark FINE off | So sánh chi phí message creation |
| Benchmark FINE on | Đo format/sink riêng |
| JDK 8 compatibility | Các demo compile bằng --release 8 trên JDK mới |

## 22. Bài tập thực hành có đáp án

### Bài 1 — nối chuỗi khi level tắt

**Đề:** Logger đặt INFO. Lời gọi logger.fine("snapshot=" + buildSnapshot()) có chạy buildSnapshot() không?

**Đáp án:** Có. Java đánh giá đối số trước khi gọi fine. Dùng logger.fine(() -> "snapshot=" + buildSnapshot()).

### Bài 2 — Supplier

**Đề:** Logger đặt INFO. logger.fine(() -> expensive()) có gọi supplier không?

**Đáp án:** Không, nếu effective level của logger không cho phép FINE. Đây là hợp đồng lazy message của JUL.

### Bài 3 — Parameterized logging

**Đề:** logger.log(Level.FINE, "state={0}", buildSnapshot()) có lazy việc gọi buildSnapshot() không?

**Đáp án:** Không. Đối số được đánh giá trước lời gọi. Việc định dạng template có thể xảy ra muộn hơn, nhưng factory vẫn chạy.

### Bài 4 — Handler threshold

**Đề:** Logger bật FINE, Handler đặt WARNING. logger.isLoggable(FINE) có nghĩa handler sẽ lưu record FINE không?

**Đáp án:** Không. Logger level và Handler level là hai lớp lọc riêng.

### Bài 5 — kiểm message template

**Đề:** Record có message "Order {0}", parameter "O-17". record.getMessage() có phải "Order O-17" không?

**Đáp án:** Không. getMessage() giữ template; dùng Formatter formatMessage(record) để kiểm chuỗi sau định dạng.

### Bài 6 — exception

**Đề:** Muốn test logger giữ stack trace/cause, chỉ assert record.getMessage() đủ không?

**Đáp án:** Không. Kiểm record.getThrown() và exception/cause; message không chứa trường Throwable.

### Bài 7 — test console

**Đề:** Test unit assert toàn bộ dòng SimpleFormatter bao gồm timestamp. Vì sao dễ flaky?

**Đáp án:** Timestamp, timezone, thread, source metadata và formatter config có thể thay đổi. Nên bắt LogRecord và assert các field ổn định.

### Bài 8 — Supplier và filter

**Đề:** Logger level bật FINE, nhưng Logger Filter loại FINE. Supplier có chắc không chạy không?

**Đáp án:** Không nên giả định. Supplier được tạo message sau bước kiểm tra effective level; filter chi tiết có thể loại record ở bước sau.

### Bài 9 — object mutable

**Đề:** Parameterized log lưu một object mutable, handler format muộn. toString() có thể thấy trạng thái nào?

**Đáp án:** Có thể thấy trạng thái lúc formatter chạy nếu object đã bị thay đổi. Truyền snapshot bất biến khi cần ghi lại đúng thời điểm sự kiện.

### Bài 10 — benchmark

**Đề:** Một vòng lặp nanoTime() chạy một lần cho thấy Supplier nhanh hơn. Có đủ để quyết định không?

**Đáp án:** Không. Cần warmup, nhiều iteration/fork, kiểm JIT/dead-code elimination, đo allocation và sink thực tế; dùng JMH hoặc harness phù hợp.

### Bài 11 — Supplier có side effect

**Đề:** Đặt cập nhật biến nghiệp vụ trong Supplier của log debug có an toàn không?

**Đáp án:** Không. Khi level tắt supplier không chạy, làm thay đổi hành vi nghiệp vụ theo cấu hình log. Supplier chỉ dựng nội dung log.

### Bài 12 — logger kế thừa level

**Đề:** logger.getLevel() trả null. Có thể kết luận logger không log gì không?

**Đáp án:** Không. Null nghĩa là kế thừa level từ logger cha. Dùng logger.isLoggable(level) để kiểm effective level.

### Bài 13 — handler toàn cục

**Đề:** Test gắn handler vào logger dùng chung nhưng quên remove. Rủi ro gì?

**Đáp án:** Test khác có thể nhận record trùng, thứ tự lẫn và giữ reference đến test state. Dùng logger riêng và remove/close trong finally.

### Bài 14 — bảo mật

**Đề:** Supplier lazy dựng chuỗi "token=" + accessToken. Điều này có an toàn vì supplier có thể không chạy không?

**Đáp án:** Không. Khi level bật, token vẫn được ghi. Lazy evaluation không phải redaction; không đưa secret vào message.

## 23. Câu hỏi tự đánh giá

**1.** JUL nằm trong package nào? — java.util.logging.

**2.** Logger.isLoggable(level) kiểm tra gì? — Effective level của logger, có tính đến level kế thừa.

**3.** Handler có level riêng không? — Có.

**4.** LogRecord lưu message và parameters ở đâu? — getMessage() và getParameters().

**5.** Overload JUL lazy nhận kiểu gì? — Supplier<String>.

**6.** Supplier overload được bổ sung từ phiên bản nào? — Java 8.

**7.** Supplier có được gọi khi level bị logger loại không? — Không.

**8.** Supplier có bảo đảm handler chắc chắn ghi record không? — Không; filter/handler vẫn có thể loại.

**9.** Nối chuỗi trước logger.fine() có lazy không? — Không.

**10.** Parameterized log có làm biểu thức đối số lazy không? — Không.

**11.** Parameterized message của JUL dùng placeholder nào? — {0}, {1} theo MessageFormat.

**12.** Muốn test message đã format, dùng gì? — Formatter.formatMessage(record).

**13.** Muốn kiểm exception, dùng trường nào? — LogRecord.getThrown().

**14.** Vì sao tắt parent handlers trong unit test? — Tránh output đi lên handler toàn cục/console.

**15.** Vì sao phải remove Handler sau test? — Tránh rò rỉ handler và ảnh hưởng test khác.

**16.** getLevel()==null có nghĩa tắt logging không? — Không, logger có thể kế thừa level.

**17.** Supplier đảm bảo zero allocation không? — Không.

**18.** Counter test chứng minh điều gì? — Số lần supplier/factory chạy, không chứng minh nanosecond performance.

**19.** Benchmark logging nên tách những trường hợp nào? — Level off, level on, format, handler và sink.

**20.** Có nên log token/password không? — Không; redaction và whitelist dữ liệu.

## Tài liệu chính thức

- [Java SE 8 — Logger](https://docs.oracle.com/javase/8/docs/api/java/util/logging/Logger.html) — level, isLoggable, overload Supplier<String> từ Java 8, parameterized log và Throwable.
- [Java SE 26 — Logger](https://docs.oracle.com/en/java/javase/26/docs/api/java.logging/java/util/logging/Logger.html) — xác nhận API lazy logging và kiểm tra level vẫn hiện hành.
- [Java SE 8 — LogRecord](https://docs.oracle.com/javase/8/docs/api/java/util/logging/LogRecord.html) — message, parameters, thrown và metadata của log event.
- [Java SE 8 — Handler](https://docs.oracle.com/javase/8/docs/api/java/util/logging/Handler.html) — publish, level, filter, flush và close.
- [Java SE 8 — Formatter](https://docs.oracle.com/javase/8/docs/api/java/util/logging/Formatter.html) — formatMessage, localization và MessageFormat.
- [Java SE 8 — Level](https://docs.oracle.com/javase/8/docs/api/java/util/logging/Level.html) — level chuẩn và thứ tự.
- [Java SE 8 — Supplier](https://docs.oracle.com/javase/8/docs/api/java/util/function/Supplier.html) — functional interface dùng cho lazy message.
- [Java SE 26 — Handler](https://docs.oracle.com/en/java/javase/26/docs/api/java.logging/java/util/logging/Handler.html) — API handler hiện hành.

**Ghi nhớ:** kiểm thử log bằng LogRecord để xác minh level, template, parameters và Throwable; dùng Handler riêng, tắt parent handlers, đặt rõ level và dọn handler sau test. Nối chuỗi và tạo đối số parameterized vẫn xảy ra trước lời gọi logger. Với JUL Java 8, Supplier<String> giúp trì hoãn **phần dựng message** khi effective logger level tắt; nó không bảo đảm zero allocation hoặc chắc chắn handler sẽ ghi record. Kiểm chi phí bằng counter để xác minh lazy behavior, và dùng benchmark có warmup/fork cùng sink thực tế khi cần đo hiệu năng. Nội dung log phải an toàn, không chứa secrets hoặc dữ liệu nhạy cảm.