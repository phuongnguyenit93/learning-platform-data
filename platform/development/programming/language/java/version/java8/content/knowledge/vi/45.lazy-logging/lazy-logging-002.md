# Log level và điều kiện supplier được thực thi trong Java 8

## 1. Bài toán: tạo log chỉ khi thật sự cần thông điệp

Java 8 bổ sung các phương thức của `java.util.logging.Logger` nhận `Supplier<String>` để trì hoãn việc tạo nội dung log. Khi mức thông điệp thấp hơn ngưỡng hiệu lực của Logger, JUL (Java Util Logging) có thể bỏ qua lời gọi **mà không thực thi thân supplier**.

So sánh:

```java
// Đoạn minh họa với java.util.logging.Logger logger:
logger.fine("result=" + expensiveCalculation());     // Eager.
logger.fine(() -> "result=" + expensiveCalculation()); // Lazy.
```

Trường hợp đầu: Java gọi `expensiveCalculation()` và nối chuỗi **trước khi** chuyển kết quả vào `fine(String)`. Dù `FINE` bị tắt, công việc tốn kém vẫn xảy ra.

Trường hợp thứ hai: `() -> ...` tạo một đối tượng hàm cung cấp chuỗi, và nội dung trong lambda chỉ chạy khi Logger thực sự cần xây message theo điều kiện **effective log level**.

**Phân biệt cực kỳ quan trọng:** Một message có mức được Logger cho phép vẫn có thể bị `Filter` hoặc `Handler` loại bỏ **sau khi supplier đã được thực thi**. Vì thế lazy logging **không hứa** rằng hễ không có dòng log được xuất thì supplier chắc chắn chưa chạy.

Bài này giải thích mức log, điều kiện gọi supplier, level kế thừa, khác biệt giữa Logger và Handler, đường đi của Filter, tối ưu `isLoggable`, các overload kèm ngoại lệ hoặc source method, thông điệp tham số hóa, tác dụng phụ và các cách kiểm thử.

Đây là những kiến thức **còn áp dụng trong Java hiện đại**. API supplier của JUL có từ Java 8, các chương trình chạy độc lập trong bài dùng cú pháp Java 8+ và đã được kiểm thử trên JDK 21. Không nhầm JUL với `System.Logger` được thêm từ Java 9.

## 2. Level của Java Util Logging

Các mức được định nghĩa trong `java.util.logging.Level`.

| Level | Độ ưu tiên chuẩn | Mục đích thường gặp |
| --- | ---: | --- |
| `SEVERE` | 1000 | Lỗi nghiêm trọng |
| `WARNING` | 900 | Tình huống có nguy cơ lỗi |
| `INFO` | 800 | Thông tin vận hành |
| `CONFIG` | 700 | Chẩn đoán cấu hình |
| `FINE` | 500 | Chi tiết debug |
| `FINER` | 400 | Debug chi tiết hơn |
| `FINEST` | 300 | Chi tiết nhất |
| `OFF` | `Integer.MAX_VALUE` | Tắt ghi log |
| `ALL` | `Integer.MIN_VALUE` | Cho phép mọi mức |

**Quy tắc ngưỡng:** Khi Logger có effective level `INFO`, những sự kiện `INFO`, `WARNING` và `SEVERE` được phép đi qua bước kiểm tra level, trong khi `CONFIG`, `FINE`, `FINER`, `FINEST` bị chặn.

Không cần tự tính các số 800, 900, 500 trong code; sử dụng `Level.INFO`, `Level.WARNING` và các hằng chuẩn. `OFF` và `ALL` chủ yếu được dùng **cấu hình ngưỡng**, không phải nhãn sự kiện nghiệp vụ.

`logger.setLevel(Level.INFO)` đặt ngưỡng riêng. `logger.setLevel(null)` **không phải tắt logging**: null nghĩa là kế thừa ngưỡng từ Logger cha.

### 2.1. Effective level khác configured level

Một Logger con có thể có `getLevel()==null` và vẫn nhận `WARNING` nếu cha đang ở `WARNING`. `isLoggable(Level.WARNING)` cho biết mức đó đang được ngưỡng Logger chấp nhận, trong khi `getLevel()` chỉ trả Level được đặt trực tiếp.

Cấu hình `setUseParentHandlers(false)` ảnh hưởng **đường chuyển bản ghi lên Handler cha**, không ngăn sự kế thừa **effective level**. Hai cơ chế này độc lập.

## 3. Supplier<String> và những overload có từ Java 8

`Supplier<T>` trong `java.util.function` là functional interface có phương thức `T get()`. Với JUL, `Supplier<String>` cung cấp chuỗi khi logging implementation gọi `get()`.

Các overload tiêu biểu:

```java
// Chữ ký API minh họa, không phải class độc lập.
void log(Level level, Supplier<String> msgSupplier);

void log(
    Level level,
    Throwable thrown,
    Supplier<String> msgSupplier
);

void logp(
    Level level,
    String sourceClass,
    String sourceMethod,
    Supplier<String> msgSupplier
);

void info(Supplier<String> supplier);
void warning(Supplier<String> supplier);
void severe(Supplier<String> supplier);
void config(Supplier<String> supplier);
void fine(Supplier<String> supplier);
void finer(Supplier<String> supplier);
void finest(Supplier<String> supplier);
```

Ví dụ thông thường:

```java
// Minh họa:
logger.log(
    Level.FINE,
    () -> "input-size=" + calculateInputSize()
);

logger.warning(
    () -> "retryCount=" + retryCount
);
```

**Không tạo chuỗi trước lambda nếu muốn tiết kiệm công việc tạo chuỗi:**

```java
// Sai về mục tiêu lazy:
String message = expensiveCalculation();
logger.fine(() -> message);

// Đúng về mục tiêu lazy:
logger.fine(() -> expensiveCalculation());
```

Với message hằng số hoặc chuỗi rất ngắn, `logger.info("Started")` hoàn toàn hợp lệ. Supplier hữu ích nhất khi message xây dựng tốn CPU, cấp phát lớn, hoặc log chi tiết thường bị tắt.

## 4. Pipeline Logger: điểm quyết định gọi supplier

Một chuỗi xử lý JUL chuẩn có thể hình dung:

```text
logger.log(Level.FINE, () -> expensive())
    |
    v
Kiểm tra Logger effective level
    |-- Không đạt --> Trả về, không chạy supplier
    |
    v
Level được Logger cho phép
    |
    v
Supplier.get() tạo thông điệp
    |
    v
Tạo/chuyển LogRecord
    |
    v
Logger Filter (nếu có)
    |-- Loại --> Không publish
    |
    v
Handler(s), mỗi Handler có:
    - level riêng
    - Filter riêng
    - Formatter/đầu ra riêng
```

**Hệ quả:** Supplier được hoãn theo **bước kiểm tra level của Logger**. Nó có thể chạy dù một Handler cấp dưới đang không muốn ghi mức đó, hoặc Logger Filter/Handler Filter sau đó trả false.

`Logger.isLoggable(Level)` kiểm tra effective Logger level, không thực hiện đầy đủ quy tắc tất cả Handler/Filter. Do đó `isLoggable(INFO)==true` không đồng nghĩa **bản ghi xuất ra console, file hoặc logging collector**.

### 4.1. Không nhầm lazy với bất đồng bộ

Supplier-based logging trong JUL là **lazy evaluation có điều kiện**, không tự biến lời gọi log thành một tác vụ background. Cách một framework/handler khác gửi message bất đồng bộ là vấn đề khác và cần đọc hợp đồng của nó.

### 4.2. Không gắn nghiệp vụ bắt buộc vào supplier

Nếu hệ thống phải gửi email, ghi database, tăng counter nghiệp vụ hoặc trừ tiền, hãy thực hiện việc ấy **ngoài** supplier. Supplier có thể không chạy khi level bị tắt; nếu chạy rồi Handler loại bản ghi, side effect không tự được hoàn tác.

## 5. Ví dụ 1 — mức Logger quyết định việc đánh giá

Tạo file **LevelGateDemo.java**:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LevelGateDemo {
    public static void main(String[] args) {
        Logger logger = Logger.getAnonymousLogger();
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        AtomicInteger calls = new AtomicInteger();
        AtomicInteger published = new AtomicInteger();

        Handler handler = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    published.incrementAndGet();
                }
            }
            @Override public void flush() {}
            @Override public void close() {}
        };
        handler.setLevel(Level.ALL);
        logger.addHandler(handler);

        logger.fine(
            () -> "FINE-" + calls.incrementAndGet()
        );
        logger.info(
            () -> "INFO-" + calls.incrementAndGet()
        );
        logger.warning(
            () -> "WARN-" + calls.incrementAndGet()
        );

        System.out.println(
            "callsAtINFO=" + calls.get()
        );
        System.out.println(
            "publishedAtINFO=" + published.get()
        );
        System.out.println(
            "fineEnabled=" +
            logger.isLoggable(Level.FINE)
        );
        System.out.println(
            "warningEnabled=" +
            logger.isLoggable(Level.WARNING)
        );

        logger.setLevel(Level.OFF);
        logger.severe(
            () -> "OFF-" + calls.incrementAndGet()
        );
        System.out.println(
            "callsAtOFF=" + calls.get()
        );

        logger.setLevel(Level.ALL);
        logger.finest(
            () -> "ALL-" + calls.incrementAndGet()
        );
        System.out.println(
            "callsAtALL=" + calls.get()
        );
        System.out.println(
            "publishedTotal=" + published.get()
        );
    }
}
```

```bash
javac LevelGateDemo.java
java LevelGateDemo
```

Stdout đã kiểm thử:

```text
callsAtINFO=2
publishedAtINFO=2
fineEnabled=false
warningEnabled=true
callsAtOFF=2
callsAtALL=3
publishedTotal=3
```

Ở ngưỡng INFO, supplier của FINE không chạy, INFO và WARNING chạy. Với OFF, SEVERE cũng không chạy. Khi bật ALL, FINEST được thực thi.

`Logger.getAnonymousLogger()` được dùng để **cô lập thử nghiệm**, không phải khuyến nghị thiết kế logger production. Trong ứng dụng, dùng tên class/module như `Logger.getLogger(MyService.class.getName())` và cấu hình handler riêng.

## 6. Ví dụ 2 — eager và lazy tạo ra chi phí khác nhau

**EagerVsLazyDemo.java**:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Level;
import java.util.logging.Logger;

public class EagerVsLazyDemo {
    private static final AtomicInteger work =
        new AtomicInteger();

    private static String expensive() {
        return "heavy-" + work.incrementAndGet();
    }

    public static void main(String[] args) {
        Logger logger = Logger.getAnonymousLogger();
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        logger.fine("eager=" + expensive());
        System.out.println(
            "afterEager=" + work.get()
        );

        logger.fine(
            () -> "lazy=" + expensive()
        );
        System.out.println(
            "afterDisabledLazy=" + work.get()
        );

        logger.info(
            () -> "enabled=" + expensive()
        );
        System.out.println(
            "afterEnabledLazy=" + work.get()
        );
    }
}
```

```bash
javac EagerVsLazyDemo.java
java EagerVsLazyDemo
```

Stdout:

```text
afterEager=1
afterDisabledLazy=1
afterEnabledLazy=2
```

Lời gọi eager làm tăng counter dù FINE bị tắt. Lời gọi supplier FINE không tăng counter. Supplier INFO được gọi khi INFO được bật.

**Một trường hợp nhầm khác:**

```java
// Đoạn minh họa:
String snapshot = expensive();
logger.fine(() -> snapshot);
```

Dù có lambda, `expensive()` đã chạy **trước lời gọi Logger**. Phải đặt phép tính cần hoãn **trong thân** lambda.

## 7. Ví dụ 3 — Logger bật FINE nhưng Handler chỉ chấp nhận WARNING

**HandlerThresholdDemo.java**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class HandlerThresholdDemo {
    public static void main(String[] args) {
        Logger logger = Logger.getAnonymousLogger();
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.FINE);

        AtomicInteger supplies =
            new AtomicInteger();
        List<String> messages = new ArrayList<>();

        Handler handler = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    messages.add(record.getMessage());
                }
            }
            @Override public void flush() {}
            @Override public void close() {}
        };

        handler.setLevel(Level.WARNING);
        logger.addHandler(handler);

        logger.fine(
            () -> "fine-" + supplies.incrementAndGet()
        );
        logger.warning(
            () -> "warning-" + supplies.incrementAndGet()
        );

        System.out.println(
            "loggerFINEenabled=" +
            logger.isLoggable(Level.FINE)
        );
        System.out.println(
            "supplierCalls=" + supplies.get()
        );
        System.out.println(
            "handlerMessages=" + messages
        );

        handler.setFilter(record -> false);
        logger.severe(
            () -> "severe-" + supplies.incrementAndGet()
        );

        System.out.println(
            "afterHandlerFilterCalls=" +
            supplies.get()
        );
        System.out.println(
            "afterHandlerFilterMessages=" + messages
        );
    }
}
```

```bash
javac HandlerThresholdDemo.java
java HandlerThresholdDemo
```

Stdout:

```text
loggerFINEenabled=true
supplierCalls=2
handlerMessages=[warning-2]
afterHandlerFilterCalls=3
afterHandlerFilterMessages=[warning-2]
```

Hai message FINE/WARNING đi qua kiểm tra **Logger**, nên hai supplier đều chạy. Handler chỉ ghi WARNING. Sau khi Handler Filter luôn trả false, supplier SEVERE vẫn chạy nhưng message không được đưa vào danh sách.

Vì vậy **không thấy log không đồng nghĩa không tốn chi phí tạo message**.

## 8. Ví dụ 4 — Logger Filter có thể loại message sau khi supplier chạy

**LoggerFilterDemo.java**:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LoggerFilterDemo {
    public static void main(String[] args) {
        Logger logger = Logger.getAnonymousLogger();
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        AtomicInteger calls = new AtomicInteger();
        AtomicInteger published =
            new AtomicInteger();

        Handler handler = new Handler() {
            @Override
            public void publish(LogRecord record) {
                published.incrementAndGet();
            }
            @Override public void flush() {}
            @Override public void close() {}
        };

        handler.setLevel(Level.ALL);
        logger.addHandler(handler);
        logger.setFilter(record -> false);

        logger.info(
            () -> "computed-" + calls.incrementAndGet()
        );

        System.out.println(
            "isLoggableINFO=" +
            logger.isLoggable(Level.INFO)
        );
        System.out.println(
            "supplierCalls=" + calls.get()
        );
        System.out.println(
            "published=" + published.get()
        );
    }
}
```

```bash
javac LoggerFilterDemo.java
java LoggerFilterDemo
```

Stdout:

```text
isLoggableINFO=true
supplierCalls=1
published=0
```

Logger INFO được bật, supplier chạy, nhưng `logger.setFilter(record -> false)` chặn bản ghi. `isLoggable` chỉ phản ánh ngưỡng logger, không phải dự báo cuối cùng về mọi bộ lọc.

## 9. isLoggable và điều kiện kiểm tra tường minh

Với message đắt, cách thường dùng là supplier trực tiếp:

```java
// Đoạn minh họa:
logger.fine(() -> "snapshot=" + buildSnapshot());
```

Nếu cần chuẩn bị nhiều dữ liệu rồi log nhiều lần từ cùng snapshot, một guard `isLoggable` có thể tránh việc chuẩn bị khi không cần:

```java
// Đoạn minh họa:
if (logger.isLoggable(Level.FINER)) {
    Report snapshot = buildDiagnosticReport();
    logger.finer(() -> "report=" + snapshot);
    logger.finer(
        () -> "size=" + snapshot.size()
    );
}
```

Guard là **phép kiểm tra thời điểm**, không bảo đảm cấu hình level không đổi giữa lúc kiểm tra và lúc log. Handler/filter vẫn có thể từ chối bản ghi.

### Ví dụ 5 — ExplicitGuardDemo.java

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Level;
import java.util.logging.Logger;

public class ExplicitGuardDemo {
    public static void main(String[] args) {
        Logger logger = Logger.getAnonymousLogger();
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        AtomicInteger expensive =
            new AtomicInteger();

        if (logger.isLoggable(Level.FINE)) {
            int snapshot = expensive.incrementAndGet();
            logger.fine(
                () -> "snapshot=" + snapshot
            );
        }

        System.out.println(
            "atINFO=" + expensive.get()
        );

        logger.setLevel(Level.FINE);

        if (logger.isLoggable(Level.FINE)) {
            int snapshot = expensive.incrementAndGet();
            logger.fine(
                () -> "snapshot=" + snapshot
            );
        }

        System.out.println(
            "atFINE=" + expensive.get()
        );
    }
}
```

```bash
javac ExplicitGuardDemo.java
java ExplicitGuardDemo
```

Stdout:

```text
atINFO=0
atFINE=1
```

Chỉ dùng guard tường minh khi có lý do. Với một message đơn giản, supplier trực tiếp dễ đọc và giảm nguy cơ lặp điều kiện không cần thiết.

## 10. Kế thừa level từ cha không phụ thuộc parent handlers

### Ví dụ 6 — InheritanceDemo.java

```java
import java.util.logging.Level;
import java.util.logging.Logger;

public class InheritanceDemo {
    public static void main(String[] args) {
        Logger parent = Logger.getLogger(
            "lesson499.tests.parent"
        );
        Logger child = Logger.getLogger(
            "lesson499.tests.parent.child"
        );

        parent.setLevel(Level.WARNING);
        child.setLevel(null);
        child.setUseParentHandlers(false);

        System.out.println(
            "parentConnected=" +
            (child.getParent() == parent)
        );
        System.out.println(
            "declaredLevel=" + child.getLevel()
        );
        System.out.println(
            "inheritedINFO=" +
            child.isLoggable(Level.INFO)
        );
        System.out.println(
            "inheritedWARNING=" +
            child.isLoggable(Level.WARNING)
        );

        child.setLevel(Level.FINE);

        System.out.println(
            "overriddenINFO=" +
            child.isLoggable(Level.INFO)
        );
    }
}
```

```bash
javac InheritanceDemo.java
java InheritanceDemo
```

Stdout khi chạy độc lập:

```text
parentConnected=true
declaredLevel=null
inheritedINFO=false
inheritedWARNING=true
overriddenINFO=true
```

`getLevel()==null` nghĩa thừa kế từ parent. Khi child đặt level FINE, INFO trở thành được phép. `setUseParentHandlers(false)` không chặn thừa kế level mà chỉ chặn chuyển bản ghi lên Handler cha.

## 11. Logging ngoại lệ bằng supplier

Khi muốn log một `Throwable` cùng message tạo trễ, dùng overload:

```java
// Đoạn minh họa:
logger.log(
    Level.WARNING,
    exception,
    () -> "Cannot process order " + orderId
);
```

Overload `log(Level,Throwable,Supplier<String>)` lưu Throwable trong trường `thrown` của `LogRecord`, khác với việc chỉ nối `exception.toString()` vào message. Formatter có thể hiển thị stack trace dựa vào thuộc tính này.

### Ví dụ 7 — ThrownSupplierDemo.java

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ThrownSupplierDemo {
    public static void main(String[] args) {
        Logger logger = Logger.getAnonymousLogger();
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.WARNING);

        AtomicInteger calls = new AtomicInteger();
        List<String> entries = new ArrayList<>();

        Handler handler = new Handler() {
            @Override
            public void publish(LogRecord record) {
                entries.add(
                    record.getMessage() + ":" +
                    record.getThrown()
                        .getClass().getSimpleName() + ":" +
                    record.getThrown().getMessage()
                );
            }
            @Override public void flush() {}
            @Override public void close() {}
        };

        handler.setLevel(Level.ALL);
        logger.addHandler(handler);

        Exception problem =
            new IllegalArgumentException("invalid");

        logger.log(
            Level.FINE, problem,
            () -> "fine-" + calls.incrementAndGet()
        );
        logger.log(
            Level.WARNING, problem,
            () -> "warn-" + calls.incrementAndGet()
        );

        System.out.println(
            "supplierCalls=" + calls.get()
        );
        System.out.println(
            "records=" + entries
        );
    }
}
```

```bash
javac ThrownSupplierDemo.java
java ThrownSupplierDemo
```

Stdout:

```text
supplierCalls=1
records=[warn-1:IllegalArgumentException:invalid]
```

Trong demo cả hai bản ghi đều truyền Throwable, nên handler đọc `getThrown()` không kiểm tra null. Một Handler dùng chung cần kiểm tra null vì nhiều bản ghi log không có exception.

## 12. logp có Supplier và metadata source

Một overload khác của JUL Java 8:

```java
// Đoạn minh họa:
logger.logp(
    Level.FINE,
    "com.example.OrderService",
    "process",
    () -> "orderId=" + orderId
);
```

`logp` truyền source class và source method tường minh. Nếu level bị Logger chặn, supplier vẫn không chạy. Nếu level cho phép, message được xây và LogRecord có metadata nguồn yêu cầu.

### Ví dụ 8 — LogpDemo.java

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LogpDemo {
    public static void main(String[] args) {
        Logger logger = Logger.getAnonymousLogger();
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        AtomicInteger calls = new AtomicInteger();
        List<String> entries = new ArrayList<>();

        Handler handler = new Handler() {
            @Override
            public void publish(LogRecord record) {
                entries.add(
                    record.getSourceClassName() + "#" +
                    record.getSourceMethodName() + ":" +
                    record.getMessage()
                );
            }
            @Override public void flush() {}
            @Override public void close() {}
        };

        handler.setLevel(Level.ALL);
        logger.addHandler(handler);

        logger.logp(
            Level.FINE, "Lesson", "run",
            () -> "fine-" + calls.incrementAndGet()
        );
        logger.logp(
            Level.INFO, "Lesson", "run",
            () -> "info-" + calls.incrementAndGet()
        );

        System.out.println(
            "supplierCalls=" + calls.get()
        );
        System.out.println(
            "entries=" + entries
        );
    }
}
```

```bash
javac LogpDemo.java
java LogpDemo
```

Stdout:

```text
supplierCalls=1
entries=[Lesson#run:info-1]
```

Nên dùng `logp` khi source metadata tường minh có giá trị. Các lời gọi `logger.fine(Supplier)` ngắn hơn, và JUL có thể suy ra thông tin nguồn với độ chính xác phụ thuộc runtime.

## 13. Supplier ném exception khi level được bật

Thân supplier là code Java. Nếu nó ném `RuntimeException`, lỗi có thể truyền ra từ lời gọi logging và ảnh hưởng caller. Nếu level bị chặn, thân supplier không chạy và lỗi từ thân đó không xuất hiện.

### Ví dụ 9 — SupplierFailureDemo.java

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class SupplierFailureDemo {
    public static void main(String[] args) {
        Logger logger = Logger.getAnonymousLogger();
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        AtomicInteger calls = new AtomicInteger();
        AtomicInteger publishes =
            new AtomicInteger();

        Handler handler = new Handler() {
            @Override
            public void publish(LogRecord record) {
                publishes.incrementAndGet();
            }
            @Override public void flush() {}
            @Override public void close() {}
        };

        handler.setLevel(Level.ALL);
        logger.addHandler(handler);

        logger.fine(() -> {
            calls.incrementAndGet();
            throw new IllegalStateException("hidden");
        });

        System.out.println(
            "disabledCalls=" + calls.get()
        );

        try {
            logger.info(() -> {
                calls.incrementAndGet();
                throw new IllegalStateException("broken");
            });
        } catch (IllegalStateException ex) {
            System.out.println(
                "caught=" + ex.getMessage()
            );
        }

        System.out.println(
            "totalCalls=" + calls.get()
        );
        System.out.println(
            "published=" + publishes.get()
        );
    }
}
```

```bash
javac SupplierFailureDemo.java
java SupplierFailureDemo
```

Stdout:

```text
disabledCalls=0
caught=broken
totalCalls=1
published=0
```

Đây là bài học quan trọng: **logging không phải nơi thích hợp cho code nghiệp vụ hoặc message generation không an toàn**. Một lệnh log DEBUG có thể không gây lỗi ở production khi bị tắt, rồi làm hỏng request khi bật debug. Nên viết supplier ngắn, side-effect-free và có cách xử lý dữ liệu không hợp lệ.

## 14. Tham số log không giống Supplier

JUL còn có dạng:

```java
// Minh họa, dùng cú pháp MessageFormat {0}.
logger.log(
    Level.INFO, "items={0}", count
);
```

Formatter có thể xử lý mẫu `{0}` và parameters sau. Nhưng **giá trị đối số** của lời gọi được Java đánh giá trước khi Logger kiểm tra level:

```java
// heavy() vẫn chạy dù FINE bị Logger tắt:
logger.log(
    Level.FINE, "items={0}", heavy()
);

// heavy() được trì hoãn:
logger.log(
    Level.FINE, () -> "items=" + heavy()
);
```

### Ví dụ 10 — ParameterEvalDemo.java

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Level;
import java.util.logging.Logger;

public class ParameterEvalDemo {
    private static final AtomicInteger calls =
        new AtomicInteger();

    private static int heavy() {
        return calls.incrementAndGet();
    }

    public static void main(String[] args) {
        Logger logger = Logger.getAnonymousLogger();
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        logger.log(
            Level.FINE, "value={0}", heavy()
        );

        logger.log(
            Level.FINE, () -> "value=" + heavy()
        );

        System.out.println(
            "afterTwoAttempts=" + calls.get()
        );

        logger.log(
            Level.INFO, "value={0}", heavy()
        );

        System.out.println(
            "afterEnabledParam=" + calls.get()
        );
    }
}
```

```bash
javac ParameterEvalDemo.java
java ParameterEvalDemo
```

Stdout:

```text
afterTwoAttempts=1
afterEnabledParam=2
```

Lời gọi đầu đã chạy `heavy()` dù FINE tắt; lời gọi Supplier FINE không chạy. Lời gọi INFO tham số hóa lại chạy hàm vì đó là argument evaluation bình thường.

### Ví dụ 11 — ParameterizedRecordDemo.java

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ParameterizedRecordDemo {
    public static void main(String[] args) {
        Logger logger = Logger.getAnonymousLogger();
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        AtomicInteger calls = new AtomicInteger();

        Handler handler = new Handler() {
            @Override
            public void publish(LogRecord record) {
                System.out.println(
                    "rawPattern=" + record.getMessage()
                );
                System.out.println(
                    "param0=" + record.getParameters()[0]
                );
            }
            @Override public void flush() {}
            @Override public void close() {}
        };

        handler.setLevel(Level.ALL);
        logger.addHandler(handler);

        logger.log(
            Level.FINE,
            "value={0}",
            calls.incrementAndGet()
        );

        System.out.println(
            "afterSuppressedParam=" + calls.get()
        );

        logger.log(
            Level.INFO,
            "value={0}",
            calls.incrementAndGet()
        );

        System.out.println(
            "afterPublishedParam=" + calls.get()
        );
    }
}
```

```bash
javac ParameterizedRecordDemo.java
java ParameterizedRecordDemo
```

Stdout:

```text
afterSuppressedParam=1
rawPattern=value={0}
param0=2
afterPublishedParam=2
```

Handler nhận mẫu `value={0}` và một parameter riêng. Không nhầm **formatting có thể hoãn** với **tính argument có thể hoãn**: chỉ dùng Supplier mới giúp hoãn cả phép `heavy()` nằm trong lambda.

## 15. Tác dụng phụ trong supplier: lỗi logic khó tìm

Không làm điều này:

```java
// Phản ví dụ: nghiêm cấm phụ thuộc vào logging.
logger.info(() -> {
    orderRepository.save(order); // Business side effect.
    return "saved";
});
```

Nếu INFO bị tắt, lệnh `save` không chạy; nếu INFO bật nhưng Handler Filter loại, lệnh `save` đã chạy mà không có log được ghi. Nếu callback ném exception, việc log còn có thể làm hỏng luồng xử lý.

Cách đúng:

```java
// Đoạn minh họa:
orderRepository.save(order);
logger.info(() -> "saved orderId=" + order.getId());
```

Điều này chỉ tách trách nhiệm, **không tự tạo exactly-once transaction** giữa DB và hệ thống log. Với audit có yêu cầu bền vững, phải dùng cơ chế nghiệp vụ/transaction/outbox phù hợp.

Các side effect cần tránh trong supplier gồm:

- Gọi DB, HTTP, gửi email/SMS, phát message queue.
- Thay đổi state được dùng để quyết định nghiệp vụ.
- Tăng counter thành công hoặc cấp ID.
- Xóa file, giải phóng tài nguyên.
- Gọi API tạo đơn hàng/thanh toán.
- Tạo dữ liệu không thể khôi phục khi log bị bỏ.

Một bộ đếm bên trong supplier **chỉ phù hợp như công cụ kiểm thử** số lần chạy, không làm counter nghiệp vụ.

## 16. Handler, parent và cấu hình thực tế

Một Logger có thể dùng nhiều Handler, mỗi Handler có `Level`, `Filter` và `Formatter` riêng. Parent handlers có thể nhận thêm cùng `LogRecord` và gây xuất trùng nếu cấu hình không đúng.

Mẫu cấu hình ngắn:

```java
// Đoạn minh họa:
Logger logger =
    Logger.getLogger("com.example.OrderService");

logger.setLevel(Level.FINE);

ConsoleHandler console = new ConsoleHandler();
console.setLevel(Level.FINE);

logger.addHandler(console);
logger.setUseParentHandlers(false);
```

Nếu Logger ở FINE nhưng ConsoleHandler vẫn INFO, message FINE có thể được tính rồi bị handler loại. Trước khi tăng logging cho ứng dụng, kiểm tra **cả Logger lẫn Handler**.

Trong unit test, các chương trình bên trên dùng Handler tự viết để không phụ thuộc timestamp, locale, timezone, root logger hoặc SimpleFormatter của máy. Việc dùng `Logger.getAnonymousLogger()` chỉ để cô lập test, không phải gợi ý chuyển mọi logger ứng dụng thành anonymous.

### 16.1. Level động

`LogManager` hoặc `Logger.setLevel` có thể cập nhật cấu hình khi chương trình đang chạy. Một câu `if (logger.isLoggable(Level.FINE))` chỉ đọc trạng thái tại thời điểm gọi; có thể có thay đổi trước lệnh log thật. Vì vậy không đưa invariant nghiệp vụ vào sự nhất quán giữa hai lần kiểm tra.

### 16.2. Dữ liệu nhạy cảm và payload lớn

Supplier không che secrets, token, mật khẩu hay thông tin cá nhân. Khi mức FINE được bật, dữ liệu vẫn có thể bị dựng thành chuỗi và xuất qua handler. Cần kiểm soát trường được log, redaction, kích thước payload và thời gian giữ log theo chính sách hệ thống.

## 17. Hiệu năng: supplier giúp gì và không giúp gì?

Supplier có lợi khi:

1. Message cần serialization/formatting đắt.
2. Mức FINE/FINER/FINEST thường được tắt.
3. Chuỗi cần xây qua nhiều trường/danh sách.
4. Một nhánh debug hiếm khi được bật.
5. Logging level được bật/tắt tùy môi trường.

Supplier **không tự giải quyết**:

- Chi phí chạy lambda khi Logger level đang bật.
- Chi phí xử lý downstream Handler/Formatter/I/O.
- Chi phí chuẩn bị dữ liệu đã tính **ngoài** lambda.
- Handler/filter loại record sau khi supplier chạy.
- Các exception của code dựng message.
- Vấn đề đồng bộ khi đọc object mutable.
- Việc bảo đảm audit log đã được lưu.

Nếu cần đo hiệu năng, so sánh cùng workload với INFO/FINE và cấu hình handler thực tế. Đừng kết luận “không thấy log tức logging không tốn tài nguyên”.

## 18. Ma trận kiểm thử điều kiện supplier

| Logger level | Message level | Handler/Filter | Supplier chạy? | Handler xuất? |
| --- | --- | --- | --- | --- |
| INFO | FINE | Handler ALL | Không | Không |
| INFO | WARNING | Handler ALL | Có | Có |
| OFF | SEVERE | Handler ALL | Không | Không |
| ALL | FINEST | Handler ALL | Có | Có |
| FINE | FINE | Handler WARNING | Có | Không |
| FINE | WARNING | Handler WARNING | Có | Có |
| FINE | SEVERE | Handler Filter false | Có | Không |
| INFO | INFO | Logger Filter false | Có | Không |

Các dòng trong bảng được kiểm thử trên **JUL chuẩn**, với Handler tự viết như trong các demo. Chúng không khẳng định semantics của mọi thư viện logging khác.

**Nên kiểm tra hai bộ đếm độc lập:** số lần gọi `Supplier.get()` và số `LogRecord` được Handler nhận. Một test chỉ kiểm tra log output có thể không phát hiện chi phí supplier bị tính thừa.

## 19. Các lỗi phổ biến

1. **Gọi `logger.fine("x="+heavy())` rồi tưởng heavy bị hoãn.** Java đánh giá argument trước.
2. **Tạo chuỗi bên ngoài lambda.** `String m=heavy(); logger.fine(()->m)` vẫn eager.
3. **Coi `isLoggable` là bảo đảm output.** Handler/filter có thể loại.
4. **Logger FINE nhưng Handler INFO.** Supplier chạy dù FINE không được ghi.
5. **Coi Logger Filter trả false nghĩa Supplier không chạy.** JUL có thể tính trước Filter.
6. **Đặt thao tác nghiệp vụ trong Supplier.** Khi level tắt, thao tác có thể không xảy ra.
7. **Cho rằng Supplier là async logging.** Lazy message không đồng nghĩa background processing.
8. **Dùng `log(Level,String,Object)` với hàm tính đắt rồi tưởng lazy.** Đối số được tính trước.
9. **Nhầm `{0}` của JUL với `{}` của framework khác.** Dùng đúng formatter.
10. **Chỉ nối exception.toString() mà không truyền Throwable.** Mất thuộc tính `LogRecord.thrown`.
11. **Dùng `setLevel(null)` như cách tắt log.** Nó làm kế thừa level.
12. **Nghĩ `setUseParentHandlers(false)` chặn kế thừa level.** Chỉ chặn forwarding.
13. **Supplier có thể ném exception.** Lời gọi log có thể truyền lỗi cho caller.
14. **Log quá nhiều payload ở INFO.** INFO bật thì việc tạo chuỗi vẫn xảy ra.
15. **Log secrets khi bật debug.** Lazy không tự đảm bảo an toàn dữ liệu.
16. **Dùng side effect trong message để đếm số record xuất.** Supplier có thể chạy dù Handler loại.
17. **Unit test phụ thuộc root logger/ConsoleHandler.** Output có thể khác theo môi trường.
18. **Đặt nhiều Handler trùng nhau.** Một record có thể được output nhiều nơi.
19. **So kết quả trước và sau reconfiguration như thể atomic transaction.** Level có thể đổi.
20. **Nhầm JUL với `System.Logger` hoặc API framework khác.** `System.Logger` không tồn tại trong Java 8.
21. **Dùng OFF và ALL như thông điệp nghiệp vụ thông thường.** Chúng chủ yếu là mức cấu hình.
22. **Lấy logging làm hệ thống audit bền vững.** JUL không thay thế transaction/outbox.

## 20. Checklist code review

1. Có đang dùng `java.util.logging.Logger` hay framework khác?
2. Supplier API có phù hợp Java version target không?
3. Chi phí xây message đã nằm trong thân lambda chưa?
4. Có gọi hàm đắt trước khi capture không?
5. Effective level của Logger là bao nhiêu?
6. Logger có thừa kế level từ cha không?
7. `getLevel()==null` đã được hiểu là thừa kế chưa?
8. Handler có level riêng lọc message không?
9. Logger Filter/Handler Filter có thể loại sau khi Supplier chạy không?
10. `isLoggable` có đang bị dùng sai như output confirmation không?
11. Có cần guard cho việc chuẩn bị ngoài message không?
12. Guard có thể bị ảnh hưởng bởi thay đổi cấu hình đồng thời không?
13. Supplier có side effect nghiệp vụ không?
14. Supplier có thể ném exception không?
15. Supplier có đọc object mutable không an toàn không?
16. Mức FINE/FINER/FINEST có phù hợp độ chi tiết không?
17. Có tách Throwable vào `LogRecord` khi log lỗi không?
18. `logp` có sourceClass/sourceMethod đúng không?
19. Tham số hóa JUL có dùng `{0}`/`{1}` không?
20. Có hiểu đối số được Java tính trước lời gọi Logger không?
21. Parent handlers có thể tạo log trùng không?
22. Có che thông tin nhạy cảm trước khi log không?
23. Test có đo riêng supplier calls và handler publishes không?
24. Test có tránh phụ thuộc timestamp/locale/formatter không?
25. Có dùng cơ chế audit bền vững riêng nếu bắt buộc không?

## 21. Câu hỏi ôn tập

**1.** `logger.fine("x="+expensive())` có gọi expensive khi FINE bị tắt không?

**Đáp án:** Có. Đối số được tính trước khi Logger kiểm tra level.

**2.** `logger.fine(()->"x="+expensive())` có gọi expensive khi Logger ở INFO không?

**Đáp án:** Không, vì FINE thấp hơn INFO.

**3.** Logger ở INFO có cho phép WARNING và SEVERE không?

**Đáp án:** Có.

**4.** Logger ở INFO có cho phép FINER không?

**Đáp án:** Không.

**5.** OFF và ALL có ý nghĩa gì?

**Đáp án:** Tắt logging và cho phép mọi mức.

**6.** Logger FINE, Handler WARNING: supplier FINE có thể chạy không?

**Đáp án:** Có, nhưng Handler có thể loại bản ghi.

**7.** Logger Filter trả false có ngăn chắc chắn supplier chạy không?

**Đáp án:** Không. JUL chuẩn có thể gọi supplier trước khi Filter xét bản ghi.

**8.** `isLoggable(INFO)==true` chứng minh dòng log đã ra console không?

**Đáp án:** Không.

**9.** `setLevel(null)` có tắt log không?

**Đáp án:** Không, nó bật kế thừa level từ cha.

**10.** `setUseParentHandlers(false)` có chặn thừa kế level không?

**Đáp án:** Không, chỉ chặn routing tới handler cha.

**11.** Khi log kèm Throwable, nên dùng overload nào?

**Đáp án:** `log(Level,Throwable,Supplier<String>)` nếu muốn lazy message.

**12.** Vì sao chỉ nối Throwable vào chuỗi có thể không đủ?

**Đáp án:** Không đưa exception vào thuộc tính `thrown` để formatter xử lý stack trace.

**13.** `logp` bổ sung thông tin gì?

**Đáp án:** Source class và source method.

**14.** Supplier ném RuntimeException có thể ảnh hưởng caller không?

**Đáp án:** Có khi Supplier được thực thi.

**15.** Có thể dùng Supplier để gửi email bắt buộc không?

**Đáp án:** Không; Supplier có thể không chạy khi mức log bị tắt.

**16.** `log(Level.FINE,"x={0}",heavy())` có tránh gọi heavy không?

**Đáp án:** Không, vì Java tính argument trước lời gọi method.

**17.** JUL dùng `{0}` hay `{}` khi log parameterized message?

**Đáp án:** `{0}`, `{1}` theo MessageFormat.

**18.** Supplier có tự tạo thread background không?

**Đáp án:** Không.

**19.** Khi nào guard `isLoggable` hữu ích?

**Đáp án:** Khi có công việc chuẩn bị rất đắt hoặc cần snapshot chung trước nhiều dòng log.

**20.** Guard đảm bảo cấu hình không đổi cho tới lúc log không?

**Đáp án:** Không.

**21.** Vì sao unit test nên dùng custom Handler?

**Đáp án:** Để không phụ thuộc cấu hình console, timestamp, format và parent handlers.

**22.** Vì sao nên đếm cả Supplier và Handler?

**Đáp án:** Một Supplier có thể chạy dù Handler không xuất bản record.

**23.** `System.Logger` thuộc Java 8 không?

**Đáp án:** Không, nó được thêm ở Java 9; JUL Supplier có từ Java 8.

**24.** Lazy logging có làm chuỗi chứa mật khẩu an toàn không?

**Đáp án:** Không. Nếu level bật, nội dung vẫn có thể được tạo và xuất ra.

## 22. Tài liệu tham khảo chính thức

- [Oracle Java SE 26 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/26/docs/api/java.logging/java/util/logging/Logger.html): lazy supplier, `isLoggable`, `logp`, `log(Level,Throwable,Supplier)`, level inheritance và routing.
- [Oracle Java SE 26 — Level](https://docs.oracle.com/en/java/javase/26/docs/api/java.logging/java/util/logging/Level.html): thứ tự mức, OFF/ALL.
- [Oracle Java SE 26 — Handler](https://docs.oracle.com/en/java/javase/26/docs/api/java.logging/java/util/logging/Handler.html): `setLevel`, `setFilter`, `isLoggable(LogRecord)`.
- [Oracle Java SE 26 — Filter](https://docs.oracle.com/en/java/javase/26/docs/api/java.logging/java/util/logging/Filter.html): lọc LogRecord.
- [Oracle Java SE 26 — LogRecord](https://docs.oracle.com/en/java/javase/26/docs/api/java.logging/java/util/logging/LogRecord.html): message/parameters/source/thrown.
- [Oracle Java SE 26 — LogManager](https://docs.oracle.com/en/java/javase/26/docs/api/java.logging/java/util/logging/LogManager.html): cấu hình logging.
- [Oracle Java SE 26 — Supplier](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/function/Supplier.html): interface `Supplier<T>` và `get()`.
- [Oracle Java SE 8 — Logger](https://docs.oracle.com/javase/8/docs/api/java/util/logging/Logger.html): xác nhận overload Supplier có từ Java 8.
- [Oracle Java SE 26 — System.Logger](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/System.Logger.html): logging API riêng được thêm từ Java 9, không phải đối tượng chính của bài này.

**Ghi nhớ:** `Supplier<String>` giúp tránh tạo thông điệp khi **effective level của Logger** loại message. Nếu Logger cho phép mức log, Supplier có thể chạy ngay cả khi Filter/Handler sau đó loại bản ghi. Hãy tách hành động nghiệp vụ khỏi logic logging, không đồng nhất `isLoggable` với việc đã xuất log, và kiểm thử độc lập **số lần supplier thực thi** với **số bản ghi được Handler nhận**.