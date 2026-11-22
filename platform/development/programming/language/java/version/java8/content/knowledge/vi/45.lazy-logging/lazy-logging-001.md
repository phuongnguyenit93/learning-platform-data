# Logger với Supplier<String> — logging theo nhu cầu trong Java

## 1. Mục tiêu và vấn đề cần giải quyết

Logging giúp quan sát ứng dụng, xác định lỗi, phân tích hiệu năng và tra cứu các sự kiện vận hành. Tuy nhiên, một thông điệp log có thể tốn công **ngay cả khi mức log đó đang tắt**, nếu lập trình viên dựng chuỗi trước khi gọi logger:

```java
logger.fine("Order details: " + expensiveDescription(order));
```

*Đây là snippet minh họa; `logger`, `order` và `expensiveDescription` chưa được định nghĩa.*

Trong biểu thức này, Java phải thực hiện phép ghép chuỗi và gọi `expensiveDescription(order)` **trước khi** bước vào `logger.fine(...)`. Nếu môi trường production chỉ bật mức `INFO` trở lên, thông điệp `FINE` sẽ không xuất ra, nhưng công tính toán nói trên đã phát sinh.

Từ **Java 8**, `java.util.logging.Logger` có các overload nhận `Supplier<String>`. Chúng trì hoãn **việc tạo String**, cho đến khi logger quyết định thông điệp **được phép log theo effective level**:

```java
logger.fine(() -> "Order details: "
        + expensiveDescription(order));
```

*Snippet minh họa, không phải chương trình độc lập.*

Nếu `FINE` bị tắt ở Logger, phần thân lambda không được gọi. Nếu `FINE` được bật, Logger yêu cầu supplier tạo thông điệp rồi chuyển bản ghi đến các Handler/Filter theo cơ chế JUL (*java.util.logging*).

Bài học thuộc nhóm **“Logging theo nhu cầu”** và tập trung vào đề bài **“Logger với Supplier<String>”**. Bạn sẽ học:

1. Vì sao truyền `String` dựng sẵn và truyền `Supplier<String>` cho kết quả chi phí khác nhau.
2. Các overload `log(Level,Supplier<String>)`; `fine`, `finer`, `finest`, `info`, `warning`, `severe`, `config`.
3. Cách kiểm tra `isLoggable(Level)` và hiểu effective level, kế thừa từ logger cha.
4. Khác nhau giữa **mức của Logger**, **Filter của Logger**, **mức của Handler** và **Filter của Handler**.
5. Vì sao supplier có thể được tính dù Handler không xuất record.
6. Cách log exception bằng `log(Level,Throwable,Supplier<String>)` mà vẫn giữ `Throwable` trong `LogRecord`.
7. Cách gắn source class/method bằng `logp(Level,String,String,Supplier<String>)`.
8. Khi nào dùng logging có placeholder `{0}` và khi nào dùng supplier.
9. Lỗi khi đưa side effect, truy cập mutable state hoặc thông tin nhạy cảm vào supplier.
10. Kiểm thử logging bằng `Handler` thu thập record, không phụ thuộc log console, timestamp hay locale.
11. Cấu hình JUL đúng hai tầng Logger/Handler; phân biệt JUL với SLF4J hoặc `System.Logger`.
12. Các nguyên tắc đo hiệu năng, giảm log noise, tránh rò rỉ PII/secret và không dùng logger làm transaction/audit ledger.

Tất cả code runnable minh họa dùng **Java 17+**; API `Supplier<String>` trong `java.util.logging.Logger` đã tồn tại từ **Java 8** và vẫn hiện hành trong JDK mới. Ví dụ có thể chạy bằng JDK 17, 21, 24 hoặc 26.

## 2. Hiểu đúng `Supplier<String>`

`Supplier<T>` nằm trong `java.util.function` và có một phương thức trừu tượng `T get()`. Với `Supplier<String>`, `get()` trả về **chuỗi thông điệp log**.

```java
Supplier<String> message = () -> "Status: OK";
String value = message.get();
```

*Snippet cần import `java.util.function.Supplier`.*

Lambda `() -> ...` không tự chạy khi được tạo; chỉ khi một bên gọi `get()` thì biểu thức trong lambda mới được đánh giá. Logger khai thác đặc điểm đó để tránh tạo thông điệp vô ích khi mức log bị tắt.

Có thể viết bằng method reference:

```java
logger.fine(service::buildDiagnosticMessage);
```

*Snippet minh họa, giả định method không nhận tham số và trả về `String`. Không gọi `service.buildDiagnosticMessage()` bên ngoài dấu `::`.*

### 2.1. Điều được trì hoãn và điều không được trì hoãn

| Biểu thức | Đánh giá thông điệp khi nào? | Khi `FINE` tắt |
| --- | --- | --- |
| `logger.fine("x=" + calculate())` | Trước khi gọi `fine` | `calculate()` **vẫn chạy** |
| `logger.fine(String.format("%s", calculate()))` | Trước khi gọi `fine` | `calculate()` **vẫn chạy** |
| `logger.fine(() -> "x=" + calculate())` | Bên trong `Supplier.get()` | `calculate()` **không chạy** do logger-level check |
| `logger.log(Level.FINE, () -> calculate())` | Bên trong supplier | `calculate()` **không chạy** khi FINE tắt |
| `String value = calculate(); logger.fine(() -> value)` | `calculate()` đã chạy trước | **Không** tiết kiệm công tính trước |
| `logger.fine(() -> cachedValue)` | Trả lại giá trị đã có | Tiết kiệm ít nếu thông điệp vốn sẵn |

**Điểm quan trọng:** Java vẫn phải **tạo/capture đối tượng lambda** hoặc tham chiếu khi gọi API, dù JIT có thể tối ưu. Supplier **không** đảm bảo “zero allocation/zero overhead”; nó chủ yếu tránh **công việc tạo nội dung thông điệp** khi Logger không chấp nhận mức log.

Khi đã cần log, hàm tạo chuỗi vẫn chạy. Supplier không thay thế thiết kế logging hợp lý, batching, cấu hình mức log hoặc đo hiệu năng.

## 3. Các overload hiện hành của JUL Logger

`java.util.logging.Logger` có nhiều phương thức nhận supplier kể từ Java 8:

| Phương thức | Mức/ý nghĩa |
| --- | --- |
| `logger.log(Level.FINE, supplier)` | Đặt mức tùy chọn từ `Level` |
| `logger.finest(supplier)` | Chẩn đoán rất chi tiết |
| `logger.finer(supplier)` | Chẩn đoán chi tiết |
| `logger.fine(supplier)` | Chẩn đoán |
| `logger.config(supplier)` | Thông tin cấu hình |
| `logger.info(supplier)` | Sự kiện thông thường |
| `logger.warning(supplier)` | Cảnh báo |
| `logger.severe(supplier)` | Lỗi nghiêm trọng |
| `logger.log(level, throwable, supplier)` | Gắn throwable trong record |
| `logger.logp(level, className, methodName, supplier)` | Nêu source class/method rõ ràng |
| `logger.logp(level, className, methodName, throwable, supplier)` | Có source và throwable |

Các overload trên **không giống** những overload nhận `String`. Đừng viết `logger.log(Level.FINE, supplier.get())` nếu muốn lazy: bạn vừa gọi `get()` sớm.

Một số phương thức `logrb` dùng bundle name kiểu `String` đã được đánh dấu deprecated trong JDK hiện hành; **không dùng các overload legacy đó** cho code mới. Khi cần localization, ưu tiên API `ResourceBundle` vẫn được hỗ trợ hoặc tầng i18n được thiết kế rõ ràng.

### 3.1. Cách gọi phổ biến

```java
private static final Logger LOGGER =
        Logger.getLogger(OrderService.class.getName());

LOGGER.fine(() -> "count=" + currentCount);
LOGGER.log(Level.FINER, () -> buildTraceText());
LOGGER.warning(() -> "Validation failed for request=" + safeId);
LOGGER.log(Level.WARNING, exception,
        () -> "Saving request failed, requestId=" + safeId);
```

*Snippet trong class/service giả định có các giá trị và phương thức tương ứng, cần imports `java.util.logging.*`. Không phải chương trình chạy độc lập.*

**Quy ước production:** thường tạo logger có tên theo class/subsystem và lưu trong `private static final`. Trong các chương trình demo, ta dùng `Logger.getAnonymousLogger()` để tránh tình trạng các demo cùng tên bị ảnh hưởng cấu hình toàn cục và tạo Handler ghi console không kiểm soát.

## 4. Demo: FINE tắt thì supplier không chạy

Ta tạo một `Logger` riêng, tắt parent handlers, bật `INFO`, gắn Handler thu thập thông điệp. Counter chỉ dùng trong **test** để đo số lần supplier được gọi; không nên đặt side effect trong supplier production.

Lưu `LazyLoggerBasicsDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LazyLoggerBasicsDemo {
    static class CollectingHandler extends Handler {
        final List<String> messages = new ArrayList<>();

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                messages.add(record.getLevel().getName()
                        + ":" + record.getMessage());
            }
        }

        @Override public void flush() {}
        @Override public void close() {}
    }

    public static void main(String[] args) {
        Logger logger = Logger.getAnonymousLogger();
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        CollectingHandler handler = new CollectingHandler();
        handler.setLevel(Level.ALL);
        logger.addHandler(handler);

        AtomicInteger calls = new AtomicInteger();

        logger.fine(() -> "debug#" +
                calls.incrementAndGet());
        System.out.println("afterFine = " + calls.get());

        logger.info(() -> "info#" +
                calls.incrementAndGet());

        System.out.println("afterInfo = " + calls.get());
        System.out.println("messages = " + handler.messages);

        logger.removeHandler(handler);
        handler.close();
    }
}
```

Chạy:

```bash
javac LazyLoggerBasicsDemo.java
java LazyLoggerBasicsDemo
```

Stdout:

```text
afterFine = 0
afterInfo = 1
messages = [INFO:info#1]
```

`FINE` (500) nhỏ hơn `INFO` (800), nên `fine` không gọi supplier. Với `info`, supplier được gọi để tạo `"info#1"` và Handler nhận record.

**Đây không phải bằng chứng Logger chưa hề tiêu tốn CPU**: check level, dựng/capture lambda và gọi method vẫn có chi phí nhỏ; phần được bỏ qua là **tính nội dung** trong supplier.

## 5. Level của Logger hoạt động thế nào?

Trong JUL, các mức tiêu chuẩn có mức độ ưu tiên (giá trị số) như sau:

| Level | Numeric value | Ví dụ ý nghĩa |
| --- | ---: | --- |
| `OFF` | `Integer.MAX_VALUE` | Tắt logging |
| `SEVERE` | 1000 | Lỗi nghiêm trọng |
| `WARNING` | 900 | Cảnh báo |
| `INFO` | 800 | Thông tin thông thường |
| `CONFIG` | 700 | Thông tin cấu hình |
| `FINE` | 500 | Diagnostics |
| `FINER` | 400 | Diagnostics chi tiết |
| `FINEST` | 300 | Diagnostics rất chi tiết |
| `ALL` | `Integer.MIN_VALUE` | Cho phép mọi mức thông thường |

Ví dụ Logger hiệu lực `WARNING` chỉ nhận `WARNING` và `SEVERE` trong các mức tiêu chuẩn. `Logger.isLoggable(level)` kiểm tra **effective level của chính Logger**.

Lưu `SupplierLevelsDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class SupplierLevelsDemo {
    static class Capture extends Handler {
        final List<String> messages = new ArrayList<>();

        @Override
        public void publish(LogRecord r) {
            if (isLoggable(r)) {
                messages.add(r.getLevel().getName()
                        + ":" + r.getMessage());
            }
        }

        @Override public void flush() {}
        @Override public void close() {}
    }

    public static void main(String[] args) {
        Logger logger = Logger.getAnonymousLogger();
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.WARNING);

        Capture capture = new Capture();
        capture.setLevel(Level.ALL);
        logger.addHandler(capture);
        AtomicInteger evaluated = new AtomicInteger();

        logger.finest(() -> "finest#" +
                evaluated.incrementAndGet());
        logger.finer(() -> "finer#" +
                evaluated.incrementAndGet());
        logger.fine(() -> "fine#" +
                evaluated.incrementAndGet());
        logger.config(() -> "config#" +
                evaluated.incrementAndGet());
        logger.info(() -> "info#" +
                evaluated.incrementAndGet());
        logger.warning(() -> "warning#" +
                evaluated.incrementAndGet());
        logger.severe(() -> "severe#" +
                evaluated.incrementAndGet());

        System.out.println("evaluated = " +
                evaluated.get());
        System.out.println("messages = " + capture.messages);
        System.out.println("fineEnabled = " +
                logger.isLoggable(Level.FINE));
        System.out.println("warningEnabled = " +
                logger.isLoggable(Level.WARNING));

        logger.removeHandler(capture);
        capture.close();
    }
}
```

```bash
javac SupplierLevelsDemo.java
java SupplierLevelsDemo
```

```text
evaluated = 2
messages = [WARNING:warning#1, SEVERE:severe#2]
fineEnabled = false
warningEnabled = true
```

**Không đồng nhất numeric level với số lỗi:** chúng là các giá trị thứ bậc cho filtering. Bạn có thể định nghĩa custom `Level` nhưng cần tránh trộn mức mới tùy tiện nếu hệ thống vận hành đã dựa vào bộ mức JUL tiêu chuẩn.

### 5.1. Effective level và logger cha

`logger.getLevel()` có thể trả `null`, nghĩa là Logger kế thừa mức từ ancestor có level được cấu hình. `getLevel()==null` **không đồng nghĩa logging bị tắt**.

Lưu `InheritedLoggerLevelDemo.java`:

```java
import java.util.logging.Level;
import java.util.logging.Logger;

public class InheritedLoggerLevelDemo {
    public static void main(String[] args) {
        Logger parent = Logger.getAnonymousLogger();
        Logger child = Logger.getAnonymousLogger();
        parent.setUseParentHandlers(false);
        child.setUseParentHandlers(false);

        child.setParent(parent);
        parent.setLevel(Level.WARNING);
        child.setLevel(null);

        System.out.println("childDirectLevel = " +
                child.getLevel());
        System.out.println("fineBefore = " +
                child.isLoggable(Level.FINE));
        System.out.println("warningBefore = " +
                child.isLoggable(Level.WARNING));

        parent.setLevel(Level.FINE);

        System.out.println("fineAfter = " +
                child.isLoggable(Level.FINE));
    }
}
```

```bash
javac InheritedLoggerLevelDemo.java
java InheritedLoggerLevelDemo
```

```text
childDirectLevel = null
fineBefore = false
warningBefore = true
fineAfter = true
```

Trong ứng dụng thật, các logger thường được tổ chức theo tên gói/class và kế thừa cấu hình từ logger cha. `setLevel(null)` khôi phục cơ chế kế thừa, không được xem là “lỗi thiếu cấu hình”.

## 6. Hai tầng lọc: Logger chấp nhận, Handler có thể vẫn từ chối

`Supplier<String>` giúp tránh dựng chuỗi khi **logger-level check** không đạt. Nhưng sau khi Logger cho phép, record có thể tiếp tục bị:

- **Filter của Logger** loại.
- **Handler level** loại.
- **Filter của Handler** loại.
- Một cơ chế khác ở Handler hoặc formatter/đích xuất ngăn ghi.

**Đừng khẳng định:** “Nếu một thông điệp không xuất hiện trong file/console thì supplier chắc chắn không chạy”. Chỉ khi **mức Logger tắt** là có bảo đảm từ lazy overload rằng thông điệp không cần được tạo.

Ví dụ Logger cho phép `INFO` nhưng Handler chỉ xuất `WARNING`:

Lưu `TwoStageLoggingDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class TwoStageLoggingDemo {
    static class Capture extends Handler {
        final List<String> delivered = new ArrayList<>();

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                delivered.add(record.getLevel().getName()
                        + ":" + record.getMessage());
            }
        }

        @Override public void flush() {}
        @Override public void close() {}
    }

    public static void main(String[] args) {
        Logger logger = Logger.getAnonymousLogger();
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        Capture handler = new Capture();
        handler.setLevel(Level.WARNING);
        logger.addHandler(handler);

        AtomicInteger constructed = new AtomicInteger();

        logger.info(() -> "discarded#" +
                constructed.incrementAndGet());
        logger.warning(() -> "important#" +
                constructed.incrementAndGet());

        System.out.println("constructed = " +
                constructed.get());
        System.out.println("delivered = " +
                handler.delivered);

        logger.removeHandler(handler);
        handler.close();
    }
}
```

```bash
javac TwoStageLoggingDemo.java
java TwoStageLoggingDemo
```

```text
constructed = 2
delivered = [WARNING:important#2]
```

**Giải thích:** `INFO` đã vượt logger check nên supplier tạo `"discarded#1"`; sau đó Handler mức WARNING không xuất nó. `WARNING` vừa đạt logger check vừa qua Handler, nên xuất `"important#2"`.

**Hệ quả tối ưu:** Nếu bạn tốn hàng chục mili-giây dựng một thông điệp `INFO` nhưng Handler thường chỉ nhận `WARNING`, nên cân nhắc cấu hình lại **Logger level** chứ không kỳ vọng Handler loại record sẽ tiết kiệm chi phí dựng message.

### 6.1. Logger Filter cũng có thể kiểm tra sau khi supplier được gọi

Vì Logger cần bản ghi để áp dụng filter trên `LogRecord`, **không dùng Logger Filter để đảm bảo skip việc tính supplier**. Khi filter dựa vào nội dung message, có thể chính message phải được tạo trước khi filter quyết định. Thiết kế xác thực/thông tin nhạy cảm không được dựa vào “Filter sẽ chặn nên an toàn”.

Lưu `LoggerFilterDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LoggerFilterDemo {
    static class Capture extends Handler {
        final List<String> messages = new ArrayList<>();

        @Override
        public void publish(LogRecord r) {
            if (isLoggable(r)) {
                messages.add(r.getMessage());
            }
        }

        @Override public void flush() {}
        @Override public void close() {}
    }

    public static void main(String[] args) {
        Logger logger = Logger.getAnonymousLogger();
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);
        logger.setFilter(record ->
                record.getMessage().startsWith("KEEP"));

        Capture capture = new Capture();
        capture.setLevel(Level.ALL);
        logger.addHandler(capture);

        AtomicInteger calls = new AtomicInteger();
        logger.info(() -> "DROP " +
                calls.incrementAndGet());
        logger.info(() -> "KEEP " +
                calls.incrementAndGet());

        System.out.println("supplierCalls = " +
                calls.get());
        System.out.println("delivered = " + capture.messages);

        logger.removeHandler(capture);
        capture.close();
    }
}
```

```bash
javac LoggerFilterDemo.java
java LoggerFilterDemo
```

```text
supplierCalls = 2
delivered = [KEEP 2]
```

Đây là ví dụ về bộ lọc record, không phải khuyến nghị dùng `getMessage().startsWith(...)` cho tất cả hệ thống log. Nếu muốn từ chối thông điệp vì lý do bảo mật, tốt nhất **không tạo hoặc gửi thông điệp nhạy cảm từ đầu**.

## 7. Dựng String sớm khác hoàn toàn truyền Supplier

Lưu `EagerVsLazyDemo.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Level;
import java.util.logging.Logger;

public class EagerVsLazyDemo {
    private static final AtomicInteger calculations =
            new AtomicInteger();

    private static String describe() {
        return "detail#" + calculations.incrementAndGet();
    }

    public static void main(String[] args) {
        Logger logger = Logger.getAnonymousLogger();
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.WARNING);

        logger.fine("eager " + describe());
        System.out.println("afterEager = " +
                calculations.get());

        logger.fine(() -> "lazy " + describe());
        System.out.println("afterLazyDisabled = " +
                calculations.get());

        logger.warning(() -> "enabled " + describe());
        System.out.println("afterLazyEnabled = " +
                calculations.get());
    }
}
```

```bash
javac EagerVsLazyDemo.java
java EagerVsLazyDemo
```

```text
afterEager = 1
afterLazyDisabled = 1
afterLazyEnabled = 2
```

Ở dòng đầu, `describe()` chạy trước khi method logging nhận `String`, nên dù `FINE` đang bị tắt vẫn tăng counter. Dòng thứ hai có lambda trì hoãn. Dòng thứ ba đạt `WARNING` nên gọi supplier.

**Chú ý khi chép mẫu sang code thật:**

```java
String costly = buildExpensiveString();
logger.fine(() -> costly); // KHÔNG lazy phần build
```

Muốn trì hoãn, cả thao tác tốn công phải **nằm trong lambda**:

```java
logger.fine(() -> buildExpensiveString());
```

*Hai snippet minh họa; `buildExpensiveString` chưa được định nghĩa.*

## 8. Tham số `{0}` và Supplier là hai kỹ thuật khác nhau

JUL hỗ trợ logging message template với `Object` parameters:

```java
logger.log(Level.INFO,
        "order {0} amount {1}",
        new Object[]{orderId, amount});
```

*Snippet minh họa, giả định các giá trị đã khai báo.*

Trong quy trình JUL, `LogRecord.getMessage()` có thể giữ **template thô**, còn `LogRecord.getParameters()` giữ đối số. `Formatter.formatMessage` thường thực hiện định dạng theo **`java.text.MessageFormat`**, trong đó placeholder là `{0}`, `{1}`, không phải `%s` (của `String.format`) hay `{}` (của một số framework khác).

**Điểm hiệu năng:** đối số của lời gọi Java vẫn được tính **trước** khi truyền vào method. Ví dụ:

```java
logger.log(Level.FINE, "details {0}",
        expensiveObjectToCompute());
```

*Snippet minh họa, không độc lập.*

`expensiveObjectToCompute()` vẫn chạy kể cả khi logger không nhận FINE. Tuy nhiên, nếu bạn đã có object `orderId` và `amount`, overload với template và params có thể phù hợp; formatter có thể trì hoãn việc format và localization theo đích log. **Không** khẳng định Supplier luôn nhanh hơn tham số hóa; chọn theo chi phí tạo đối số và khả năng trình bày/structured logging của pipeline.

Lưu `MessageParametersDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class MessageParametersDemo {
    static class Capture extends Handler {
        final List<LogRecord> records = new ArrayList<>();

        @Override
        public void publish(LogRecord r) {
            if (isLoggable(r)) {
                records.add(r);
            }
        }

        @Override public void flush() {}
        @Override public void close() {}
    }

    public static void main(String[] args) {
        Logger logger = Logger.getAnonymousLogger();
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        Capture handler = new Capture();
        handler.setLevel(Level.ALL);
        logger.addHandler(handler);

        logger.log(Level.INFO,
                "order {0} amount {1}",
                new Object[]{42, "19.75"});
        logger.info(() -> "ready=42");

        LogRecord first = handler.records.get(0);
        Formatter formatter = new Formatter() {
            @Override
            public String format(LogRecord record) {
                return formatMessage(record);
            }
        };

        System.out.println("raw = " + first.getMessage());
        System.out.println("formatted = " +
                formatter.format(first));
        System.out.println("params = " +
                first.getParameters().length);
        System.out.println("supplierMessage = " +
                handler.records.get(1).getMessage());

        logger.removeHandler(handler);
        handler.close();
    }
}
```

```bash
javac MessageParametersDemo.java
java MessageParametersDemo
```

```text
raw = order {0} amount {1}
formatted = order 42 amount 19.75
params = 2
supplierMessage = ready=42
```

**Phân biệt:**

- `log(Level,String,Object[])` giữ template và params trong record; formatter nhận trách nhiệm diễn đạt.
- `log(Level,Supplier<String>)` tạo **một String** khi Logger cho phép, không tự biến chuỗi thành fields có cấu trúc.
- Nếu ứng dụng cần structured logs với fields truy vấn riêng, hãy thiết kế Handler/formatter hoặc logging framework phù hợp; đừng dùng concatenation như một hệ thống schema.

## 9. Log exception đúng cách mà vẫn lazy thông điệp

Gọi đơn thuần:

```java
logger.warning(() -> "failed: " + ex);
```

*Snippet minh họa, giả định `ex` là exception đã có.*

sẽ chứa văn bản `ex.toString()` trong message, nhưng **không gắn `Throwable` vào `LogRecord`**. Formatter/handler khó truy cập nguyên vẹn stack trace/causes theo cấu trúc.

JUL có overload:

```java
logger.log(Level.WARNING, ex,
        () -> "Saving request failed: requestId=" + safeId);
```

*Snippet minh họa, giả định `ex` và `safeId` đã khai báo.*

Tham số thứ hai là `Throwable`, thứ ba là `Supplier<String>`. **Không đảo thứ tự** thành `log(level,supplier,ex)`; đó không phải overload trên.

Lưu `ThrowableSupplierDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ThrowableSupplierDemo {
    static class Capture extends Handler {
        final List<LogRecord> records = new ArrayList<>();

        @Override
        public void publish(LogRecord r) {
            if (isLoggable(r)) {
                records.add(r);
            }
        }

        @Override public void flush() {}
        @Override public void close() {}
    }

    public static void main(String[] args) {
        Logger logger = Logger.getAnonymousLogger();
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.WARNING);

        Capture handler = new Capture();
        handler.setLevel(Level.ALL);
        logger.addHandler(handler);

        IllegalArgumentException exception =
                new IllegalArgumentException("invalid input");
        AtomicInteger builds = new AtomicInteger();

        logger.log(Level.FINE, exception,
                () -> "not-created#" +
                        builds.incrementAndGet());
        logger.log(Level.WARNING, exception,
                () -> "request=42 builds=" +
                        builds.incrementAndGet());

        LogRecord record = handler.records.get(0);
        System.out.println("message = " +
                record.getMessage());
        System.out.println("throwableClass = " +
                record.getThrown().getClass().getSimpleName());
        System.out.println("sameThrowable = " +
                (record.getThrown() == exception));
        System.out.println("builds = " + builds.get());

        logger.removeHandler(handler);
        handler.close();
    }
}
```

```bash
javac ThrowableSupplierDemo.java
java ThrowableSupplierDemo
```

```text
message = request=42 builds=1
throwableClass = IllegalArgumentException
sameThrowable = true
builds = 1
```

**Ranh giới bảo mật:** Exception có thể chứa thông tin nhạy cảm trong message/cause/stack context. Việc gắn throwable đúng không miễn trừ quy tắc redaction, access control hoặc data retention của hệ thống log.

## 10. Ghi rõ source class/method bằng `logp`

Đôi khi chương trình có lớp wrapper logging hoặc cần nêu source cụ thể. `Logger.logp` nhận source class và source method:

```java
logger.logp(Level.FINE,
        "OrderService", "save",
        () -> "validated=true");
```

*Snippet minh họa; cần `java.util.logging.Level`.*

Lưu `LogpSupplierDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LogpSupplierDemo {
    static class Capture extends Handler {
        final List<LogRecord> records = new ArrayList<>();

        @Override
        public void publish(LogRecord r) {
            if (isLoggable(r)) {
                records.add(r);
            }
        }

        @Override public void flush() {}
        @Override public void close() {}
    }

    public static void main(String[] args) {
        Logger logger = Logger.getAnonymousLogger();
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.FINE);

        Capture handler = new Capture();
        handler.setLevel(Level.ALL);
        logger.addHandler(handler);

        logger.logp(Level.FINE,
                "OrderService", "save",
                () -> "validated=true");

        LogRecord record = handler.records.get(0);
        System.out.println("source = " +
                record.getSourceClassName() + "."
                + record.getSourceMethodName());
        System.out.println("level = " +
                record.getLevel().getName());
        System.out.println("message = " +
                record.getMessage());

        logger.removeHandler(handler);
        handler.close();
    }
}
```

```bash
javac LogpSupplierDemo.java
java LogpSupplierDemo
```

```text
source = OrderService.save
level = FINE
message = validated=true
```

`logp` không bắt buộc cho mọi lời gọi; JUL cũng có khả năng suy ra caller trong một số overload, nhưng thông tin source phụ thuộc stack/cách wrapper thực hiện. Nếu việc nêu source rõ là quan trọng với framework wrapper, `logp` giúp tránh dựa vào suy đoán caller. Các chuỗi source do programmer cung cấp không phải chứng cứ xác thực nguồn bảo mật.

## 11. Đừng đặt side effect trong Supplier

Khi log ở `FINE` bị tắt, lambda **không chạy**. Điều đó có nghĩa bất cứ side effect trong lambda cũng sẽ biến mất: cập nhật counter nghiệp vụ, ghi database, gửi message, thay đổi trạng thái hoặc kiểm tra validation không được đặt trong Supplier chỉ vì tiện viết.

**Sai:**

```java
logger.fine(() -> {
    processedOrders++;
    return "processedOrders=" + processedOrders;
});
```

*Anti-pattern minh họa, không phải chương trình độc lập.*

Khi `FINE` bị tắt, `processedOrders++` không chạy. Khi mức log thay đổi trong runtime, số xử lý thay đổi theo cấu hình log — sai hoàn toàn về nghiệp vụ.

**Đúng:** làm nghiệp vụ **ngoài** lambda; supplier chỉ tạo văn bản quan sát:

```java
processedOrders++;
int snapshot = processedOrders;
logger.fine(() -> "processedOrders=" + snapshot);
```

*Snippet minh họa trong một ngữ cảnh đồng bộ phù hợp, chưa định nghĩa `processedOrders`. Nếu nhiều thread cùng cập nhật counter, phải dùng cấu trúc thread-safe thích hợp.*

**Không dùng việc log có được ghi ra hay không làm logic điều khiển chương trình.** Logging là quan sát, không phải cơ chế transaction hoặc đồng bộ state.

### 11.1. Nếu Supplier ném exception thì sao?

Hàm tạo message là code Java thật. Nếu nó ném `RuntimeException`, lời gọi logging có thể ném exception ngược lên caller. Vì vậy đừng đặt serialization phức tạp, thao tác I/O dễ lỗi hoặc logic không được bảo vệ vào các lambda này trên hot path.

Lưu `SupplierExceptionDemo.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Level;
import java.util.logging.Logger;

public class SupplierExceptionDemo {
    public static void main(String[] args) {
        Logger logger = Logger.getAnonymousLogger();
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.WARNING);

        AtomicInteger attempts = new AtomicInteger();

        logger.fine(() -> {
            attempts.incrementAndGet();
            throw new IllegalStateException("disabled");
        });

        boolean thrownWhenEnabled = false;
        try {
            logger.warning(() -> {
                attempts.incrementAndGet();
                throw new IllegalStateException("enabled");
            });
        } catch (IllegalStateException e) {
            thrownWhenEnabled = true;
        }

        System.out.println("disabledSkipped = " +
                (attempts.get() == 1));
        System.out.println("enabledThrows = " +
                thrownWhenEnabled);
        System.out.println("attempts = " +
                attempts.get());
    }
}
```

```bash
javac SupplierExceptionDemo.java
java SupplierExceptionDemo
```

```text
disabledSkipped = true
enabledThrows = true
attempts = 1
```

Counter ở ví dụ là instrumentation để xác nhận lazy behavior. Trong code thật, message supplier nên đơn giản, **không gây side effect** và ít nguy cơ ném exception.

Nếu formatter/handler xảy ra lỗi, cơ chế ErrorManager/Handler lại có contract riêng; đừng nhầm nó với exception xảy ra trực tiếp trong Supplier.

## 12. Capture trạng thái: snapshot hay giá trị đang thay đổi?

Lambda có thể tham chiếu một object mutable. Khi việc tạo thông điệp phụ thuộc state có thể đổi, người đọc log có thể khó hiểu:

```java
logger.info(() -> "state=" + sharedState.get());
```

*Snippet minh họa, `sharedState` phải được khai báo và thread-safe.*

Supplier sẽ đọc state **khi được gọi**, không phải “ảnh chụp lúc developer viết lambda”. Trong JUL thường Logger gọi supplier khi log level cho phép; không nên dựa vào thời điểm chính xác giữa nhiều thread đang thay đổi state.

Khi cần gắn log với một quyết định đã có, tạo snapshot ổn định:

```java
String stateAtDecision = sharedState.get();
logger.info(() -> "state=" + stateAtDecision);
```

*Snippet minh họa, biến local phải effectively final.*

Lưu `SupplierSnapshotDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class SupplierSnapshotDemo {
    static class Capture extends Handler {
        final List<String> messages = new ArrayList<>();

        @Override
        public void publish(LogRecord r) {
            if (isLoggable(r)) {
                messages.add(r.getMessage());
            }
        }

        @Override public void flush() {}
        @Override public void close() {}
    }

    public static void main(String[] args) {
        Logger logger = Logger.getAnonymousLogger();
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        Capture capture = new Capture();
        capture.setLevel(Level.ALL);
        logger.addHandler(capture);

        AtomicReference<String> shared =
                new AtomicReference<>("v1");
        String snapshot = shared.get();
        shared.set("v2");

        logger.info(() -> "snapshot=" + snapshot);
        logger.info(() -> "current=" + shared.get());

        System.out.println("messages = " + capture.messages);

        logger.removeHandler(capture);
        capture.close();
    }
}
```

```bash
javac SupplierSnapshotDemo.java
java SupplierSnapshotDemo
```

```text
messages = [snapshot=v1, current=v2]
```

**Hiểu đúng:** snapshot đã được tạo **trước** `logger.info`, nên nếu việc tạo snapshot rất tốn kém thì sẽ phát sinh ngay cả khi log disabled. Đó là lựa chọn có chủ đích khi nghiệp vụ cần dữ liệu snapshot. Nếu snapshot chỉ phục vụ debug, có thể cân nhắc tạo **trong** supplier từ một nguồn thread-safe, chấp nhận giá trị được quan sát tại thời điểm log được dựng.

### 12.1. Effectively-final và mutable container

Biến local được lambda capture phải `final` hoặc **effectively final**. Nhưng object mà biến local tham chiếu có thể mutable; tính effectively-final của biến không khiến object thành immutable.

`StringBuilder` hay `HashMap` dùng chung giữa threads không an toàn chỉ vì xuất hiện bên trong lambda. Đừng log bằng cách duyệt một collection đang bị sửa không đồng bộ từ thread khác; tốt hơn tạo snapshot an toàn hoặc log những field đã được xử lý và kiểm soát.

## 13. Logging có thể cấu hình khi runtime đang chạy

`Logger.setLevel` có thể thay đổi trong runtime. Do đó không được tạo message bằng cách đoán rằng “FINE luôn tắt” hoặc cache kết quả `isLoggable` vô thời hạn.

`logger.isLoggable(Level.FINE)` kiểm tra trạng thái **tại thời điểm gọi**:

```java
if (logger.isLoggable(Level.FINE)) {
    String trace = buildVeryExpensiveTrace();
    logger.fine(trace);
}
```

*Snippet minh họa.*

Mẫu này hợp lý khi việc tạo trace yêu cầu **nhiều bước ngoài một lambda** hoặc bạn cần tránh tạo đối tượng trung gian. Tuy nhiên có khoảng thời gian giữa `isLoggable` và `fine`: cấu hình có thể thay đổi. Đây là phép kiểm tra tối ưu **best-effort**, không phải giao dịch nguyên tử với thay đổi cấu hình.

Với một thông điệp đơn giản, thường ưu tiên:

```java
logger.fine(() -> buildVeryExpensiveTrace());
```

*Snippet minh họa.*

Đừng gọi `isLoggable` rồi vẫn dựng chuỗi **ngoài** điều kiện hoặc tin rằng check đó đảm bảo Handler sẽ xuất record.

Lưu `DynamicLevelDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class DynamicLevelDemo {
    static class Capture extends Handler {
        final List<String> messages = new ArrayList<>();

        @Override
        public void publish(LogRecord r) {
            if (isLoggable(r)) {
                messages.add(r.getMessage());
            }
        }

        @Override public void flush() {}
        @Override public void close() {}
    }

    public static void main(String[] args) {
        Logger logger = Logger.getAnonymousLogger();
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        Capture capture = new Capture();
        capture.setLevel(Level.ALL);
        logger.addHandler(capture);

        AtomicInteger calls = new AtomicInteger();

        logger.fine(() -> "trace#" +
                calls.incrementAndGet());

        logger.setLevel(Level.FINE);

        logger.fine(() -> "trace#" +
                calls.incrementAndGet());

        logger.setLevel(Level.WARNING);

        logger.fine(() -> "trace#" +
                calls.incrementAndGet());

        System.out.println("builds = " + calls.get());
        System.out.println("messages = " + capture.messages);
        System.out.println("currentFineEnabled = " +
                logger.isLoggable(Level.FINE));

        logger.removeHandler(capture);
        capture.close();
    }
}
```

```bash
javac DynamicLevelDemo.java
java DynamicLevelDemo
```

```text
builds = 1
messages = [trace#1]
currentFineEnabled = false
```

Đây là tuần tự thay đổi cấu hình để tạo kết quả xác định. Nếu nhiều thread thay đổi level đồng thời, không dựa trên số log chính xác cho correctness của ứng dụng.

## 14. Handler có trách nhiệm xuất/log format và có thể có chi phí riêng

Pipeline JUL có thể đơn giản hóa:

```text
logger.fine(() -> buildMessage())
       |
       v
Logger effective-level check
       | false --> return, không gọi supplier
       v true
Supplier.get()  (dựng String)
       |
       v
LogRecord (+ Logger Filter)
       |
       +--> Handler A level/filter --> Formatter --> console
       |
       +--> Handler B level/filter --> Formatter --> file
       |
       +--> Handler C level/filter --> Formatter --> collector
```

*Đây là sơ đồ khái niệm: thứ tự chi tiết có thể được implement tùy API, và một handler có thể dùng xử lý bất đồng bộ.*

`Formatter` có thể thực hiện string format, localization và xử lý parameters vào **thời điểm record được xuất**. `Supplier` **chỉ** trì hoãn việc tạo **message String theo Logger-level check**; nó không tự:

- Trì hoãn việc tạo `Throwable` đã có trước đó.
- Bảo đảm Handler không phải format message.
- Bảo đảm record được ghi xuống ổ đĩa thành công.
- Bảo đảm output được giữ nguyên mọi dữ liệu như JSON structured fields.
- Bảo đảm delivery exactly once.
- Thay thế kiểm soát queue/backpressure của handler bất đồng bộ.

Khi tạo custom Handler, phải quan tâm thread-safety. Javadoc Handler nêu rằng handler có thể bị gọi đồng thời từ nhiều thread, nên production handler không được dùng `ArrayList` không đồng bộ như các demo đơn-thread bên trên. Trong demo, `ArrayList` chỉ có một thread, không phải mẫu production.

### 14.1. Custom Handler thread-safe để quan sát LogRecord

Lưu `SafeCaptureHandlerDemo.java`:

```java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class SafeCaptureHandlerDemo {
    static class Capture extends Handler {
        final List<String> entries =
                new CopyOnWriteArrayList<>();

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                entries.add(record.getMessage());
            }
        }

        @Override public void flush() {}
        @Override public void close() {}
    }

    public static void main(String[] args) {
        Logger logger = Logger.getAnonymousLogger();
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        Capture capture = new Capture();
        capture.setLevel(Level.ALL);
        logger.addHandler(capture);

        logger.info(() -> "first");
        logger.warning(() -> "second");

        System.out.println("count = " +
                capture.entries.size());
        System.out.println("messages = " + capture.entries);

        logger.removeHandler(capture);
        capture.close();
    }
}
```

```bash
javac SafeCaptureHandlerDemo.java
java SafeCaptureHandlerDemo
```

```text
count = 2
messages = [first, second]
```

**Giới hạn:** `CopyOnWriteArrayList` thuận tiện cho demo/ít ghi và cho thread-safe collection, nhưng không nhất thiết phù hợp với logger nhận **hàng triệu event/giây**. Một logging pipeline production cần phân tích throughput, retention, backpressure, overflow policy và chi phí từng handler.

## 15. Cấu hình console và logger trong ứng dụng

Nếu muốn thấy `FINE` trên console của JUL, **cả logger và ConsoleHandler** phải nhận FINE. Chỉ `logger.setLevel(Level.FINE)` có thể chưa đủ nếu console handler ở mức INFO.

Một ví dụ cấu hình trong `logging.properties`:

```properties
handlers=java.util.logging.ConsoleHandler
.level=INFO
com.example.orders.level=FINE
java.util.logging.ConsoleHandler.level=FINE
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
```

Đây là **mẫu cấu hình**, không phải Java code runnable. `com.example.orders` là tên logger/package ví dụ và phải được thay bằng namespace thật. Hãy kiểm tra cấu hình root/parent handlers của ứng dụng để tránh xuất log trùng lặp.

Chạy một ứng dụng Java có cấu hình:

```bash
java -Djava.util.logging.config.file=logging.properties com.example.Main
```

*Lệnh minh họa khi đã có file cấu hình và class `com.example.Main` trên classpath. Không có file đó trong ví dụ độc lập.*

Nếu ứng dụng chạy trên server/container/framework có quản lý logging riêng, cấu hình JUL có thể được bridge hoặc chuyển tiếp đến backend khác. Cần xác định hệ thống logging thực sự đang sử dụng, tránh đồng thời gắn nhiều Handler dẫn tới duplicated log.

### 15.1. Không hiểu sai `Logger.getLogger` và `Logger.getAnonymousLogger`

- `Logger.getLogger("com.example.orders.OrderService")` lấy một named logger, tiện cho hierarchy và cấu hình production.
- `Logger.getAnonymousLogger()` tạo logger ẩn danh, phù hợp minh họa/test độc lập khi không muốn trùng tên.
- `logger.setUseParentHandlers(false)` trong các ví dụ giúp **không có output phụ từ root logger**.
- `logger.addHandler(handler)` gắn đích xuất; cần quản lý lifecycle khi là handler thật có I/O.
- `logger.setFilter(...)` chỉ là một lớp lọc, không tự đảm bảo bảo mật hoặc skip tính supplier.

Tránh dùng field `Logger.global` đã deprecated trong các JDK hiện hành. Trong code mới, tạo named logger theo class hoặc dùng API hệ thống phù hợp với framework.

## 16. Bảo mật: log ít nhất dữ liệu cần thiết

Supplier giúp giảm chi phí khi log disabled, **không phải cơ chế bảo vệ thông tin nhạy cảm**.

Một lambda như:

```java
logger.fine(() -> "Authorization: " + bearerToken);
```

*Anti-pattern minh họa; không được log token thật.*

khi bật FINE trong production có thể xuất token. Logger Filter hoặc Handler không đảm bảo dữ liệu không được tạo/đưa vào LogRecord. Đừng log password, API key, access token, session cookie, số thẻ, bí mật cá nhân, nội dung request/response đầy đủ không được phép, hay PII mà không có policy.

**Nên làm:**

- Log những mã định danh phi nhạy cảm, mã kết quả, loại sự kiện, thời gian xử lý đã được cho phép.
- Dùng redaction/masking nhất quán và review log schema.
- Phân quyền đọc log, giới hạn retention, encryption at rest/in transit theo hạ tầng.
- Không dùng log message được dựng theo ngôn ngữ tự do làm kho audit bắt buộc không được mất dữ liệu.

Lưu `SafeLoggingMessageDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class SafeLoggingMessageDemo {
    static class Capture extends Handler {
        final List<String> entries = new ArrayList<>();

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                entries.add(record.getMessage());
            }
        }

        @Override public void flush() {}
        @Override public void close() {}
    }

    public static void main(String[] args) {
        String rawEmail = "alice@example.com";
        String safeRequestId = "req-42";

        Logger logger = Logger.getAnonymousLogger();
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.WARNING);

        Capture capture = new Capture();
        capture.setLevel(Level.ALL);
        logger.addHandler(capture);

        logger.warning(() ->
                "request=" + safeRequestId + " validation_failed");

        System.out.println("count = " +
                capture.entries.size());
        System.out.println("messages = " + capture.entries);
        System.out.println("containsSensitive = " +
                capture.entries.stream()
                        .anyMatch(m -> m.contains(rawEmail)));

        logger.removeHandler(capture);
        capture.close();
    }
}
```

```bash
javac SafeLoggingMessageDemo.java
java SafeLoggingMessageDemo
```

```text
count = 1
messages = [request=req-42 validation_failed]
containsSensitive = false
```

Đây chỉ là **minh họa việc không đưa email vào message**. Trong hệ thống thật, ngay cả request ID hoặc business identifiers cũng cần được phân loại bảo mật; không tự mặc định mọi identifier đều public.

## 17. Có nên gọi `toString()` trên object nặng trong supplier?

Supplier tránh gọi `toString()` khi logger-level bị tắt nếu viết:

```java
logger.fine(() -> "payload=" + expensiveObject);
```

*Snippet giả định object đã tồn tại và `toString()` có thể tốn công.*

Khi FINE bật, phép nối chuỗi có thể gọi `toString()`. Cần thận trọng:

- `toString()` có thể tải một graph object rất lớn, sinh dữ liệu nhạy cảm hoặc có lỗi.
- `toString()` không nhất thiết thread-safe nếu đọc mutable object.
- Lazy logging không tự tránh N+1 SQL queries nếu getter/ORM `toString` truy cập dữ liệu lazily.
- Tránh serialization toàn bộ JSON/request trong hot loop nếu chỉ cần vài field chẩn đoán.
- Nếu cần cấu trúc/fields, tích hợp logger/formatter được thiết kế cho structured logging.

Không nên dựa vào `toString()` của dữ liệu domain làm log schema ổn định. Nếu thay đổi implementation, log text có thể thay đổi, làm hỏng việc tìm kiếm/alert.

## 18. So với SLF4J, Log4j và System.Logger

**JUL** là `java.util.logging` trong JDK, có API `Logger.log(Level,Supplier<String>)` từ Java 8. **SLF4J** là facade bên ngoài, còn **Log4j** là một framework logging. Chúng có các API, overloads và cơ chế parameterization/lazy evaluation khác nhau.

**Không chuyển nguyên xi cú pháp:**

```java
java.util.logging.Logger jul =
        java.util.logging.Logger.getLogger("app");
jul.fine(() -> "costly=" + compute());
```

*Snippet minh họa, `compute()` chưa được định nghĩa.*

sang `org.slf4j.Logger` và giả định nó nhận cùng Supplier ở mọi phiên bản. Hãy xem **đúng API và phiên bản** của framework dùng trong dự án.

Java 9 bổ sung `System.Logger` với overload nhận `Supplier<String>`, nhưng không phải cùng type `java.util.logging.Logger` và dùng các level `System.Logger.Level` riêng. Không import nhầm hoặc trộn `java.util.logging.Level` với `System.Logger.Level`.

**Chọn công cụ:** nếu ứng dụng đã dùng logging facade/framework được cấu hình thống nhất, thường nên tuân theo framework đó thay vì tạo JUL logger riêng gây nhiều pipeline. Bài này tập trung vào **API JUL** hiện hành đúng với Java 8+.

## 19. Kiểm thử logging đúng cách

Unit test cho logging theo nhu cầu nên phân biệt:

1. **Logger-level disabled:** supplier không bị gọi.
2. **Logger-level enabled:** supplier được gọi và tạo message.
3. **Handler-level blocked:** supplier có thể đã chạy nhưng handler không xuất.
4. **Logger Filter blocked:** supplier có thể đã chạy trước khi filter loại.
5. **Throwable overload:** `LogRecord.getThrown()` giữ exception gốc.
6. **logp overload:** `getSourceClassName()` và `getSourceMethodName()` có giá trị yêu cầu.
7. **Template formatting:** raw `getMessage()` khác `Formatter.formatMessage()` khi có parameters.
8. **Dynamic level:** bật/tắt thay đổi số lần supplier chạy.
9. **Side effects:** logic nghiệp vụ chạy **độc lập** với level.
10. **Privacy:** message không chứa secret/PII ngoài policy.
11. **Handler thread safety:** nếu test concurrent, sử dụng collection đồng bộ hoặc `CopyOnWriteArrayList`.
12. **Không phụ thuộc output console:** SimpleFormatter có thể thêm timestamp, thread, source, locale; dùng capture handler kiểm tra các field trong `LogRecord`.

Một unit test không nên cố kiểm tra chính xác millis/nanos log timestamp hoặc thứ tự giữa các thread không đồng bộ. Không nên bắt output mặc định của root logger nếu có thể kiểm soát một Handler riêng.

### 19.1. Chương trình kiểm thử nhanh lazy behavior

Lưu `LoggerSmokeTestDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LoggerSmokeTestDemo {
    static class Capture extends Handler {
        final List<LogRecord> entries = new ArrayList<>();

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                entries.add(record);
            }
        }

        @Override public void flush() {}
        @Override public void close() {}
    }

    public static void main(String[] args) {
        Logger logger = Logger.getAnonymousLogger();
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);
        Capture capture = new Capture();
        capture.setLevel(Level.ALL);
        logger.addHandler(capture);

        AtomicInteger calls = new AtomicInteger();
        logger.fine(() -> "hidden" +
                calls.incrementAndGet());
        logger.info(() -> "visible" +
                calls.incrementAndGet());

        boolean ok = calls.get() == 1
                && capture.entries.size() == 1
                && "visible1".equals(
                        capture.entries.get(0).getMessage());

        System.out.println("testPassed = " + ok);
        System.out.println("message = " +
                capture.entries.get(0).getMessage());

        logger.removeHandler(capture);
        capture.close();
    }
}
```

```bash
javac LoggerSmokeTestDemo.java
java LoggerSmokeTestDemo
```

```text
testPassed = true
message = visible1
```

Không cần một JDBC connection, service ngoài hay framework nào để test behavior của JUL; class `Logger` và `Handler` có sẵn trong JDK.

## 20. Hiệu năng: supplier có lợi khi nào?

Supplier rất có ích cho các debug messages thường bị tắt, đặc biệt khi dựng message tốn công:

- Dựng stack/diagnostic snapshot.
- Định dạng một object graph phức tạp.
- Đọc nhiều trường rồi tạo chuỗi.
- Phân tích kết quả xử lý chi tiết không cần thiết ở production.
- Tạo báo cáo trạng thái dài để chẩn đoán.

Nhưng có những giới hạn:

- Supplier/lambda vẫn có chi phí gọi method và có thể có allocation/capture.
- Khi mức log bật, mọi công dựng chuỗi vẫn diễn ra.
- Logger level cho phép nhưng Handler không ghi, supplier vẫn có thể đã chạy.
- Handler/formatter, file I/O, network collector và backpressure có thể mới là bottleneck.
- `Logger.isLoggable` có hiệu quả như một check, nhưng không phải snapshot atomic khi cấu hình thay đổi đồng thời.
- Các thao tác bên trong lambda **không nên có side effect** hoặc làm hỏng tính đúng đắn nếu không chạy.
- Dùng `System.nanoTime` đo một lần trong `main` rất dễ bị nhiễu JIT/GC và scheduler.

Benchmark có thể dùng **JMH** (OpenJDK Java Microbenchmark Harness) hoặc đo trên workload thực, thay đổi giữa mức `FINE` on/off, logger vs handler level và tần suất log. Đo **throughput, latency, allocations, GC, I/O** nếu phù hợp; không tự tuyên bố "supplier nhanh hơn N lần" khi không có số liệu.

### 20.1. Ba cấu hình cần so sánh

| Logger level | Handler level | Supplier cho log FINE chạy? | Record FINE tới handler? |
| --- | --- | --- | --- |
| INFO | ALL | Không | Không |
| FINE | INFO | Có | Handler INFO có thể từ chối |
| FINE | FINE | Có | Có nếu filter/handler khác cho phép |

Bảng giả định logger không có filter từ chối, Handler hoạt động bình thường và đối tượng đầu vào hợp lệ. Với nhiều handler, các đích có thể có chính sách khác nhau.

## 21. Các lỗi phổ biến

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| `logger.fine("x=" + expensive())` | Tính message dù log tắt | `logger.fine(() -> "x=" + expensive())` |
| `logger.fine(supplier.get())` | Gọi supplier quá sớm | Truyền supplier, không gọi `get` |
| `String s=expensive(); logger.fine(()->s)` | Chi phí đã trả trước khi log | Đưa phép tính vào lambda nếu chỉ dành cho log |
| Đặt cập nhật business counter trong supplier | Không thực hiện khi level tắt | Đưa business logic ra ngoài |
| Logger bật INFO nhưng Handler chỉ WARNING mà vẫn kỳ vọng lazy | Supplier INFO vẫn có thể chạy | Cấu hình lại logger level |
| Logger Filter chặn record thì tin supplier không chạy | Có thể tạo message rồi mới lọc | Không dựa vào Filter để skip/redact |
| Chỉ nối `exception.toString` vào message | Mất Throwable field trong record | `log(level,ex, supplier)` |
| Dùng `log(level,supplier,ex)` | Không có overload đó | Thứ tự đúng: level, throwable, supplier |
| Dùng `String.format` trên hot path trước khi gọi logger | Dựng message sớm | Đưa format vào supplier nếu cần |
| Nhầm `{0}` với `%s` hoặc `{}` | Formatter xử lý sai template | JUL MessageFormat `{0}` |
| Truy cập `HashMap`/`StringBuilder` mutable không đồng bộ | Race/exception/inconsistent log | Snapshot hoặc đồng bộ/ownership |
| Supplier có thể ném exception | Có thể ảnh hưởng business caller | Supplier gọn, defensive, không I/O nguy hiểm |
| Log password/token/PII rồi hy vọng debug luôn tắt | Mức có thể bật khi điều tra sự cố | Không đưa secret vào message |
| Coi `isLoggable` là giao dịch nguyên tử với `setLevel` | Race cấu hình | Dùng như check tối ưu best-effort |
| Test so timestamp ConsoleHandler | Không ổn định giữa môi trường | Capture LogRecord |
| Handler dùng ArrayList không đồng bộ trong production | Race/record loss | Thiết kế Handler thread-safe |
| Nhầm JUL `Logger` với SLF4J `Logger` | Không tương thích overload/API | Đọc đúng interface/framework |
| Dùng `Logger.global` deprecated | API cũ không phù hợp code mới | Named Logger/getLogger |
| Nghĩ lazy logging là audit chính xác/guaranteed delivery | Log có thể bị lọc/lỗi/thiếu | Audit ledger/transaction riêng |

## 22. Bài tập và lời giải

**Bài 1 — Lazy cơ bản.** Tạo Logger mức INFO, gọi `fine(() -> expensive())`. Đặt counter trong `expensive()` để chứng minh không gọi khi FINE disabled.

**Bài 2 — Hai tầng lọc.** Logger INFO, Handler WARNING. Gọi `info(() -> "...")` và `warning(() -> "...")`. Dự đoán supplier call count và message nào được Handler ghi.

**Bài 3 — Bật/tắt lúc chạy.** Đổi Logger từ INFO → FINE → WARNING. Gọi fine ở mỗi trạng thái và đếm số lần supplier chạy.

**Bài 4 — Template vs Supplier.** Viết hai cách log `"order 42 amount 19.75"` bằng `log(Level.INFO,"order {0} amount {1}",new Object[]{...})` và `info(() -> ...)`. Khác nhau giữa `LogRecord.getMessage` và `Formatter.formatMessage`?

**Bài 5 — Exception.** Khi bắt `SQLException`, log request ID đã ẩn danh bằng `log(Level.WARNING,ex,()->...)`. Vì sao điều này hơn việc chỉ nối `ex.getMessage()`?

**Bài 6 — Side effect.** Chứng minh đặt `processed++` trong supplier là sai: khi log bị tắt, nghiệp vụ có thể đổi kết quả. Chuyển phần tăng ra ngoài.

**Bài 7 — Bảo mật.** Viết chính sách log validation failed mà không chứa email/password/access token. Kiểm thử chuỗi output không chứa dữ liệu cần che.

**Bài 8 — Nền tảng khác.** Một dự án có SLF4J 2.x đã tích hợp và routing đến một backend. Có nên khởi tạo JUL logger mới và dùng cú pháp `fine(Supplier)` ở mọi lớp? Nêu các vấn đề tích hợp và API.

### 22.1. Chương trình tổng kết: chi phí log chỉ phát sinh khi cần

Lưu `LazyLoggingPracticeDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LazyLoggingPracticeDemo {
    record Order(int id, String state) {
    }

    static class Capture extends Handler {
        final List<String> messages = new ArrayList<>();

        @Override
        public void publish(LogRecord r) {
            if (isLoggable(r)) {
                messages.add(r.getMessage());
            }
        }

        @Override public void flush() {}
        @Override public void close() {}
    }

    private static String describe(
            Order order, AtomicInteger builds) {
        builds.incrementAndGet();
        return "order=" + order.id() +
                " state=" + order.state();
    }

    public static void main(String[] args) {
        Logger logger = Logger.getAnonymousLogger();
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        Capture capture = new Capture();
        capture.setLevel(Level.ALL);
        logger.addHandler(capture);

        Order order = new Order(7, "PAID");
        AtomicInteger builds = new AtomicInteger();

        logger.fine(() -> describe(order, builds));
        System.out.println("afterDisabled = " +
                builds.get());

        logger.setLevel(Level.FINE);
        logger.fine(() -> describe(order, builds));

        System.out.println("afterEnabled = " +
                builds.get());
        System.out.println("messages = " + capture.messages);

        logger.removeHandler(capture);
        capture.close();
    }
}
```

```bash
javac LazyLoggingPracticeDemo.java
java LazyLoggingPracticeDemo
```

```text
afterDisabled = 0
afterEnabled = 1
messages = [order=7 state=PAID]
```

Giải thích: ở lần đầu FINE bị tắt nên `describe` không được gọi. Khi FINE được bật, `describe` chạy một lần và trả String cho Logger. Counter thuộc demo để quan sát việc gọi supplier, không phải đề xuất đặt cập nhật nghiệp vụ vào supplier.

## 23. Checklist trước khi đưa vào production

- `Logger` đang dùng có phải `java.util.logging.Logger` hay một framework/facade khác?
- Code chỉ dùng các overload `Supplier<String>` hiện hành từ Java 8+?
- Có phép tính message expensive nào **đã chạy trước** khi tạo lambda không?
- Message builder có side effect hoặc I/O nguy hiểm không?
- Các field capture có stable snapshot hay đọc mutable shared state không đồng bộ?
- Có dùng `log(Level,Throwable,Supplier)` khi cần stack trace/exception field?
- `isLoggable` kiểm tra mức hiệu lực của Logger, không nhầm mức Handler?
- Có nhầm “record không thấy” thành “supplier không chạy” không?
- Handler/filter/formatter có riêng chi phí hoặc nguy cơ lỗi/đồng bộ không?
- Có dùng JUL placeholder `{0}` đúng với `MessageFormat` nếu chọn overload params?
- Cấu hình Logger + Handler có thống nhất, tránh đè/nhân đôi log qua root logger?
- Log message có chứa token, password, email hoặc PII ngoài policy không?
- Mức log bật tắt runtime có được xem là chuyện vận hành, không ảnh hưởng correctness?
- Custom Handler có thread-safe nếu được gọi từ nhiều thread?
- Đã test lúc level tắt, lúc level bật, handler từ chối và logger filter từ chối?
- Benchmark có warmup, chạy nhiều lần với workload thực thay vì một kết luận giả?
- Hệ thống đã có SLF4J/Log4j bridge thì có tuân theo pipeline logging thống nhất?
- Log có phải chỉ là quan sát, không bị dùng thay cho audit transaction không?

## 24. Tài liệu chính thức hiện hành

- Oracle Java SE 26 — `java.util.logging.Logger`, các overload `Supplier<String>` và `logp`: https://docs.oracle.com/en/java/javase/26/docs/api/java.logging/java/util/logging/Logger.html
- Oracle Java SE 26 — `Level` và numeric severity: https://docs.oracle.com/en/java/javase/26/docs/api/java.logging/java/util/logging/Level.html
- Oracle Java SE 26 — `Handler`, filtering và thread safety: https://docs.oracle.com/en/java/javase/26/docs/api/java.logging/java/util/logging/Handler.html
- Oracle Java SE 26 — `LogRecord` và Throwable/parameters/source: https://docs.oracle.com/en/java/javase/26/docs/api/java.logging/java/util/logging/LogRecord.html
- Oracle Java SE 26 — `Formatter`, `formatMessage` và localization: https://docs.oracle.com/en/java/javase/26/docs/api/java.logging/java/util/logging/Formatter.html
- Oracle Java SE 26 — `LogManager` và `logging.properties`: https://docs.oracle.com/en/java/javase/26/docs/api/java.logging/java/util/logging/LogManager.html
- Oracle Java SE 26 — `Supplier<T>`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/function/Supplier.html
- Oracle Java SE 26 — `System.Logger`, phân biệt với JUL: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/System.Logger.html
- Oracle Java 8 API — `java.util.logging.Logger`, Supplier overloads đã có từ 1.8: https://docs.oracle.com/javase/8/docs/api/java/util/logging/Logger.html
- OpenJDK JMH — benchmark Java đúng cách khi cần đánh giá overhead logging: https://github.com/openjdk/jmh

**Ghi nhớ:** `Logger` nhận `Supplier<String>` để trì hoãn **tạo message** cho đến khi **Logger effective level** cho phép log. Dùng `logger.fine(() -> expensiveMessage())` thay vì truyền String đã dựng; nhưng không nghĩ rằng mọi Handler/filter không xuất bản ghi đều tránh gọi supplier. **Không đặt side effect, business update, secret hoặc xử lý dễ lỗi vào supplier**. Kết hợp đúng Logger/Handler level, giữ Throwable trong `LogRecord`, cấu hình logging thống nhất và kiểm thử bằng capture Handler để có lazy logging chính xác, an toàn và dễ bảo trì.