# Thay đổi log level khi chương trình Java đang chạy

## 1. Thay đổi log level khi chạy nghĩa là gì?

**Log level** là ngưỡng kiểm soát những sự kiện logging được chấp nhận. Khi hệ thống đang chạy, đôi khi cần bật log chi tiết hơn để điều tra lỗi, rồi trả về ngưỡng ban đầu sau khi chẩn đoán. **Thay đổi level khi chạy (runtime log level change)** là điều chỉnh ngưỡng đó trong một tiến trình Java vẫn đang hoạt động, không phải sửa mã nguồn rồi biên dịch lại.

Ví dụ: bình thường ứng dụng ghi `INFO`, `WARNING` và `SEVERE`. Khi có vấn đề khó tái hiện ở tính năng thanh toán, đội vận hành tạm bật `FINE` ở logger liên quan, quan sát vài request, sau đó chuyển về `INFO`. Không cần ghi thêm lệnh log nếu các lệnh `logger.fine(...)` đã có trong code; chỉ cần cấu hình cho phép chúng được xuất bản ghi.

Cần phân biệt ba thao tác khác nhau:

1. **Đặt level lúc khởi động**: đọc cấu hình từ file, tham số JVM hoặc framework trước khi ứng dụng phục vụ request.
2. **Đổi level ngay trong JVM**: gọi API quản lý logger hoặc cơ chế quản trị logging mà framework cung cấp.
3. **Sửa file cấu hình trên đĩa**: thay đổi file **không nhất thiết** làm ứng dụng tự áp dụng giá trị mới; chỉ có hiệu lực lúc chạy nếu cơ chế reload đang hoạt động hoặc có thao tác reload rõ ràng.

Bài này trình bày trọng tâm trên **`java.util.logging` (JUL) của Java 17+**, sẵn trong JDK. Với SLF4J/Logback, Log4j2 hoặc Spring Boot, thao tác tương ứng phụ thuộc backend thực tế.

## 2. Ôn lại các mức log trong JUL

JUL có các level thường gặp theo thứ tự từ nghiêm trọng đến chi tiết:

| Mức | Ý nghĩa thực hành |
| --- | --- |
| `SEVERE` | Lỗi nghiêm trọng, tác vụ không hoàn thành |
| `WARNING` | Bất thường cần lưu ý nhưng tiến trình có thể tiếp tục |
| `INFO` | Các mốc hoạt động quan trọng |
| `CONFIG` | Thông tin cấu hình khi chẩn đoán |
| `FINE` | Chi tiết phục vụ debug |
| `FINER` | Chi tiết hơn `FINE` |
| `FINEST` | Chi tiết rất sâu |

Hai giá trị đặc biệt: `Level.ALL` cho phép mọi level và `Level.OFF` tắt các bản ghi đi qua bộ lọc đó.

Mức `INFO` cho phép `INFO`, `WARNING`, `SEVERE`; những bản ghi `CONFIG`, `FINE`, `FINER` và `FINEST` bị lọc. Khi hạ ngưỡng từ `INFO` xuống `FINE`, ứng dụng có thể phát thêm các bản ghi `CONFIG` và `FINE`.

> Trong SLF4J/Logback hoặc Log4j2 có mức `DEBUG` và `TRACE`. **JUL không có `Level.DEBUG` hay `Level.TRACE`**. Đừng sao chép tên level từ backend này sang backend khác mà không kiểm tra API và cấu hình hỗ trợ.

## 3. Logger level và handler level là hai ngưỡng riêng

Trong JUL, việc một dòng log có xuất hiện hay không phụ thuộc ít nhất vào **logger phát sinh** và **handler nhận bản ghi**:

```text
logger.fine("Preparing payment")
    |
    v
Logger: chấp nhận Level.FINE?
    | không -> loại ở logger
    | có
    v
Handler: chấp nhận Level.FINE?
    | không -> không xuất ở đích handler đó
    | có
    v
Console / file / đích log khác
```

Ví dụ:

| Logger level | ConsoleHandler level | `logger.fine(...)` |
| --- | --- | --- |
| `INFO` | `ALL` | Không thấy: logger đã chặn |
| `FINE` | `INFO` | Không thấy: handler đã chặn |
| `FINE` | `FINE` | Thấy trên console, nếu không có filter khác |
| `ALL` | `WARNING` | Không thấy trên console; handler chặn |
| `OFF` | `ALL` | Không thấy: logger chặn mọi bản ghi thông thường |

Để **bật một level chi tiết**, phải kiểm tra cả ngưỡng hiệu lực của logger và ngưỡng từng handler; mỗi handler có thể đặt mức khác nhau. Ví dụ console vẫn `INFO` để dễ đọc, nhưng file chấp nhận `FINE` để điều tra sâu.

Một logger có thể không gắn handler trực tiếp mà truyền record tới handler của logger cha, bao gồm root logger. Điều này còn phụ thuộc `useParentHandlers`. Khi record được truyền từ logger con lên, **JUL không áp lại level của từng logger cha**; handler trên đường đi vẫn tự lọc bằng level của nó. Do đó, chỉ thay đổi root level không bảo đảm mọi bản ghi của logger con sẽ biến mất hay xuất hiện như dự kiến.

## 4. Đổi level ngay bằng API Java

Một logger được lấy bằng tên và thay đổi qua `setLevel(...)`:

```java
import java.util.logging.Level;
import java.util.logging.Logger;

Logger paymentLogger = Logger.getLogger("com.example.payment");

// Khi cần điều tra:
paymentLogger.setLevel(Level.FINE);

// Kiểm tra mức FINE có qua bộ lọc logger không:
boolean allowed = paymentLogger.isLoggable(Level.FINE);

// Sau khi điều tra xong:
paymentLogger.setLevel(Level.INFO);
```

Đoạn code trên **minh họa cách gọi API**, cần đặt trong method/class thích hợp. Giá trị thay đổi tác động tới **logger cùng tên được quản lý trong JVM hiện tại**, không tác động JVM của dịch vụ khác. `Logger.getLogger(name)` không tự gửi lệnh đến mọi instance ứng dụng đang chạy.

Trong ứng dụng thực tế, nên giữ logger dưới dạng `static final` theo class hoặc giữ tham chiếu đến logger được cấu hình để tránh việc quản lý instance vô tình trở nên khó đoán. `setLevel` thay đổi hành vi lọc của logger cho những lần ghi tiếp theo; bản ghi đã bị lọc trước đó không thể tạo lại chỉ bằng đổi level.

### Mức kế thừa và Level null

`Logger.getLevel()` cho biết mức **được đặt trực tiếp** trên logger, không nhất thiết là mức hiệu lực hiện tại:

```java
Logger logger = Logger.getLogger("com.example.payment");

logger.setLevel(Level.FINE); // Đặt mức riêng.
logger.setLevel(null);       // Bỏ mức riêng: kế thừa mức từ cha.
```

`null` nghĩa là **kế thừa** từ logger cha gần nhất có level xác định, cuối cùng có thể là root logger; **không có nghĩa tắt log**. Khi logger đang kế thừa, thay đổi mức ở logger cha có thể đổi hành vi ghi log của logger con. Nếu logger con đã đặt level riêng, đổi level của cha không thay thế cấu hình riêng này.

Để biết một mức có thể được logger chấp nhận không, hãy dùng `isLoggable(Level.FINE)`; dù trả về `true`, handler vẫn có thể loại bản ghi.

## 5. Ví dụ Java 17 chạy được: thay đổi level ngay trong chương trình

Ví dụ này có một logger và một `ConsoleHandler`. Chương trình thay đổi level nhiều lần trong **cùng một lần chạy**, cho thấy bản ghi nào được phát ra sau mỗi thay đổi.

Tạo file `RuntimeLogLevelDemo.java`:

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class RuntimeLogLevelDemo {
    private static final Logger LOG =
            Logger.getLogger(RuntimeLogLevelDemo.class.getName());

    public static void main(String[] args) {
        Level oldLevel = LOG.getLevel();
        boolean oldUseParentHandlers = LOG.getUseParentHandlers();
        Handler[] existingHandlers = LOG.getHandlers();

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.INFO);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " | " + formatMessage(record)
                        + System.lineSeparator();
            }
        });

        // Cô lập các handler của demo, tránh nhân đôi bản ghi.
        for (Handler handler : existingHandlers) {
            LOG.removeHandler(handler);
        }
        LOG.setUseParentHandlers(false);
        LOG.addHandler(console);

        try {
            // Bước 1: WARNING trên logger, INFO trên handler.
            LOG.setLevel(Level.WARNING);
            LOG.info("INFO before change - hidden");
            LOG.warning("1. WARNING is visible");

            // Bước 2: hạ ngưỡng logger về INFO.
            LOG.setLevel(Level.INFO);
            LOG.info("2. INFO is now visible");
            LOG.fine("FINE while logger is INFO - hidden");

            // Bước 3: logger cho phép FINE nhưng handler vẫn INFO.
            LOG.setLevel(Level.FINE);
            LOG.fine("FINE while handler is INFO - hidden");

            // Bước 4: thay đổi handler để FINE thực sự được xuất.
            console.setLevel(Level.FINE);
            LOG.fine("3. FINE is now visible");

            // Bước 5: handler chỉ cho phép SEVERE.
            console.setLevel(Level.SEVERE);
            LOG.warning("WARNING while handler is SEVERE - hidden");
            LOG.severe("4. SEVERE is visible");
        } finally {
            LOG.removeHandler(console);
            console.close();

            // Khôi phục trạng thái logger ban đầu.
            LOG.setLevel(oldLevel);
            LOG.setUseParentHandlers(oldUseParentHandlers);
            for (Handler handler : existingHandlers) {
                LOG.addHandler(handler);
            }
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac RuntimeLogLevelDemo.java
java RuntimeLogLevelDemo
```

**Đầu ra từ `ConsoleHandler` trên `System.err`:**

```text
WARNING | 1. WARNING is visible
INFO | 2. INFO is now visible
FINE | 3. FINE is now visible
SEVERE | 4. SEVERE is visible
```

Vì formatter cố ý không in thời gian nên các dòng trên ổn định. Trong JUL, `ConsoleHandler` mặc định ghi ra **stderr**; đây không phải chương trình in kết quả qua `System.out.println(...)`.

**Giải thích theo thứ tự thực thi:**

1. Ở bước 1, logger đặt `WARNING` nên `INFO` bị chặn ngay tại logger. Handler đặt `INFO` vẫn nhận được `WARNING`.
2. Khi đổi logger thành `INFO` ở bước 2, bản ghi `INFO` bắt đầu qua bộ lọc và xuất hiện trên console.
3. Khi logger chuyển sang `FINE` nhưng handler vẫn `INFO`, bản ghi `FINE` đã được logger chấp nhận nhưng **handler loại bỏ**.
4. Sau `console.setLevel(Level.FINE)`, cả logger và handler đều cho phép `FINE` nên dòng chi tiết hiện ra.
5. Khi nâng ngưỡng handler lên `SEVERE`, bản ghi `WARNING` tiếp tục được logger chấp nhận nhưng không xuất qua console; `SEVERE` vẫn xuất.

Ví dụ lưu và khôi phục level, parent propagation, handler của logger; không gọi `close()` với các handler đã tồn tại vì chúng có thể thuộc thành phần khác. Đây là demo chạy một mình. Trong máy chủ đang chạy nhiều thread, việc thay handler hoặc cấu hình logger dùng chung có thể ảnh hưởng request khác; nên có cơ chế quản trị giới hạn quyền và đồng bộ hóa thay đổi theo vòng đời ứng dụng.

## 6. Chỉ đổi level của một package hoặc class

Trong ứng dụng lớn, thường không nên hạ ngưỡng root logger xuống `FINE` vì quá nhiều thành phần sẽ phát log chi tiết, làm tăng chi phí và có thể lộ thông tin nhạy cảm. Chọn logger hẹp theo chức năng:

```java
import java.util.logging.Level;
import java.util.logging.Logger;

Logger payment = Logger.getLogger("com.example.payment");
payment.setLevel(Level.FINE); // Chỉ phạm vi logger này và các con kế thừa.

Logger sql = Logger.getLogger("com.example.persistence");
sql.setLevel(Level.WARNING); // Giữ log ít chi tiết hơn.
```

Một logger tên `com.example.payment.PaymentService` có thể kế thừa mức `FINE` từ logger `com.example.payment` **nếu quan hệ cha–con được xác lập và nó không đặt level riêng**. Dấu chấm trong tên không đảm bảo từng logger trung gian đã tồn tại; khi cần chẩn đoán, kiểm tra `getParent()` và mức hiệu lực. Nếu `PaymentService` có `setLevel(Level.INFO)` riêng, thay level ở package `com.example.payment` chưa chắc tác động tới nó.

Để tắt tạm các bản ghi phát trực tiếp từ một logger:

```java
payment.setLevel(Level.OFF);
```

Chỉ dùng `OFF` có chủ đích; nó có thể che cả cảnh báo/lỗi cần thiết để vận hành. Sau khi điều tra, khôi phục level trước đó, **kể cả trường hợp trước đó là null** (kế thừa), thay vì luôn ép về `INFO`.

## 7. Đổi level ở root logger và vì sao có thể chưa đủ

Root logger JUL có tên rỗng `""`:

```java
Logger root = Logger.getLogger("");
root.setLevel(Level.WARNING);
```

Thay đổi root level có thể tác động đến logger con **đang kế thừa** mức từ root. Tuy nhiên:

- Logger con đã đặt level riêng vẫn dùng level riêng.
- Handler của root có bộ lọc level của chính nó; ví dụ handler đặt `INFO` sẽ không in `FINE`.
- Khi logger con phát record đã vượt qua level tại con, JUL chuyển record tới handler của cha mà không kiểm tra lại level cha.
- Logger con có thể tắt `useParentHandlers` hoặc dùng handler riêng, nên cấu hình root không trực tiếp quyết định đầu ra của nó.

Ví dụ muốn xem `FINE` ở logger cụ thể qua handler của root:

```java
Logger target = Logger.getLogger("com.example.payment");
target.setLevel(Level.FINE);

Logger root = Logger.getLogger("");
for (java.util.logging.Handler handler : root.getHandlers()) {
    handler.setLevel(Level.FINE);
}
```

Đây là **đoạn minh họa**, không phải khuyến nghị chạy nguyên xi trên production. Vòng lặp trên thay level của **tất cả handler gắn trực tiếp trên root**, làm thay đổi logging ở các khu vực khác. Nếu logger mục tiêu tắt parent propagation hoặc còn filter khác, việc đổi root handler cũng có thể không tạo kết quả mong muốn.

Với ứng dụng thực tế, cần xác định **handler thực sự nhận record** và kiểm soát đúng đích, thay vì chỉnh root trên toàn ứng dụng chỉ vì muốn debug một class.

## 8. Đổi level bằng cơ chế quản trị thay vì sửa mã nghiệp vụ

Nhiều ứng dụng cần thay level **sau khi khởi động**, theo thao tác của người vận hành. Một số lựa chọn:

### 8.1. JMX cho Java Util Logging

JDK có `java.lang.management.PlatformLoggingMXBean` dùng để quan sát và chỉnh level các logger có tên tại thời điểm chạy. Ví dụ **đoạn mã minh họa đặt trong phương thức**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.PlatformLoggingMXBean;

PlatformLoggingMXBean bean =
        ManagementFactory.getPlatformMXBean(PlatformLoggingMXBean.class);

if (bean != null) {
    // Logger cùng tên phải đang tồn tại trong LogManager.
    bean.setLoggerLevel("com.example.payment", "FINE");

    // Kiểm tra level đã đặt trực tiếp trên logger:
    String level = bean.getLoggerLevel("com.example.payment");
    System.out.println(level);

    // Trả về kế thừa level từ cha:
    bean.setLoggerLevel("com.example.payment", null);
}
```

Đây là API quản lý logging, **không phải API để ghi một dòng log**. Phương thức `setLoggerLevel` yêu cầu tên logger tồn tại và tên mức hợp lệ; nếu không có logger hoặc tên level không hợp lệ, thao tác có thể ném `IllegalArgumentException`. Level trả về của `getLoggerLevel` phản ánh level **được đặt trực tiếp**; chuỗi rỗng biểu thị logger kế thừa, còn `null` có thể biểu thị logger không tồn tại.

Khi triển khai qua công cụ JMX từ xa, phải kiểm soát xác thực, quyền thay đổi cấu hình và bảo mật kết nối. Thay đổi qua JMX là thay đổi trong JVM đang nhận lệnh, không mặc nhiên lan sang mọi JVM hoặc pod khác.

### 8.2. Cơ chế điều hành của framework

Ứng dụng dùng **SLF4J** thường gọi API logging độc lập với backend. Tuy nhiên, API logger chung của SLF4J không cung cấp một phương thức chuẩn như `setLevel(...)` áp dụng cho tất cả backend. Muốn thay level động, cần dùng cách mà backend cung cấp.

Ví dụ với **Logback Classic** (đoạn minh họa yêu cầu thư viện Logback tương ứng trong classpath):

```java
org.slf4j.Logger generic =
        org.slf4j.LoggerFactory.getLogger("com.example.payment");

if (generic instanceof ch.qos.logback.classic.Logger logbackLogger) {
    logbackLogger.setLevel(ch.qos.logback.classic.Level.DEBUG);
}
```

Không ép kiểu như trên khi ứng dụng thực tế dùng backend khác; thao tác có thể không có hiệu lực hoặc kiểu không phù hợp. Trong ứng dụng Spring Boot, cơ chế quản trị logging qua **Spring Boot Actuator** có thể hỗ trợ xem/đổi mức log động khi endpoint `loggers` được bật và được cấp quyền. Cách gọi, quyền truy cập và danh sách endpoint thực tế phải đối chiếu với phiên bản và cấu hình ứng dụng; **không công khai endpoint thay level cho người dùng không có quyền**.

### 8.3. Công cụ quản lý cấu hình hoặc lệnh quản trị nội bộ

Ứng dụng có thể chủ động cung cấp một thao tác quản trị dùng để cập nhật level ở runtime, ví dụ chọn logger theo tên và gọi `setLevel` trong JUL. Khi xây dựng cơ chế này nên:

- Cho phép danh sách logger được phép chỉnh; tránh thay đổi mọi logger tùy ý.
- Chỉ người có quyền vận hành mới có thể sử dụng; ghi audit thao tác và người thực hiện.
- Giới hạn các level cho phép trên production và thời gian bật level chi tiết.
- Có nút hoặc thời hạn **khôi phục giá trị ban đầu**, kể cả giá trị `null`.
- Hiển thị rõ sự khác nhau giữa cấu hình đang có trong bộ nhớ và cấu hình khởi động.
- Nếu có nhiều instance, cần áp dụng tới đúng tập instance; không giả định cập nhật một node là đủ.

## 9. Thay đổi file logging.properties trong lúc chạy

Với JUL, file `logging.properties` có thể cấu hình mức log ban đầu, ví dụ:

```properties
handlers=java.util.logging.ConsoleHandler
.level=INFO
java.util.logging.ConsoleHandler.level=INFO
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter

com.example.payment.level=FINE
```

Chạy JVM với cấu hình này:

```bash
java -Djava.util.logging.config.file=logging.properties MyApplication
```

`MyApplication` ở đây là tên class khởi động **minh họa cho ứng dụng có sẵn**, không phải class được cung cấp trong bài. `-Djava.util.logging.config.file` là **system property JVM** chỉ tới đường dẫn file cấu hình. Đường dẫn tương đối tính từ thư mục làm việc của tiến trình.

**Sửa file sau khi JVM đã chạy không tự động cập nhật level trong JUL mặc định.** Muốn nạp lại bằng API, JUL có `LogManager.readConfiguration(...)`:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.logging.LogManager;

public static void reloadJulConfiguration(Path file) throws IOException {
    try (InputStream in = Files.newInputStream(file)) {
        LogManager.getLogManager().readConfiguration(in);
    }
}
```

Đây là **method minh họa** phải đặt trong một class; phần import đặt ở đầu file. Lời gọi `readConfiguration(InputStream)` nạp lại cấu hình logging của **LogManager** và có thể reset lại nhiều thuộc tính, level, filter hoặc handler đang dùng; không tương đương với “chỉ đổi một logger từ INFO thành FINE”. Nó có tác động phạm vi JVM và có thể đóng hoặc thay thế các handler được quản lý. Chỉ thực hiện khi hiểu lifecycle và quyền sở hữu cấu hình của toàn ứng dụng.

Các thư viện/framework có thể cung cấp cơ chế tự reload cấu hình, nhưng **không phải cơ chế chung được JUL đảm bảo chỉ bằng cách sửa file**. Nếu dùng Logback hay Log4j2, hãy dùng tài liệu/cấu hình reload riêng của backend; file `logging.properties` JUL không nhất thiết quản lý logger của backend đó.

## 10. Khi thay level trong hệ thống nhiều instance

Ví dụ hệ thống có 3 bản sao service chạy ở 3 JVM riêng:

```text
Request ──> Load Balancer
             ├── Payment JVM A: INFO
             ├── Payment JVM B: FINE  <- đã đổi level
             └── Payment JVM C: INFO
```

Nếu chỉ gọi `setLevel(FINE)` tại **JVM B**, các bản ghi chi tiết xuất hiện ở B; A và C vẫn giữ INFO. Không thể suy ra “toàn bộ service đã bật FINE” chỉ từ phản hồi của một JVM.

Tình huống thực tế cần xác định:

1. **Phạm vi:** một logger, một package, toàn bộ ứng dụng hay một tập instance.
2. **Thời hạn:** thay đổi tạm trong bao lâu; khi nào hoàn nguyên.
3. **Độ bền:** đổi trong bộ nhớ có thể bị mất sau khi JVM restart hoặc cấu hình tự reload.
4. **Quan sát kết quả:** kiểm tra tại đúng instance và đúng đích handler; tránh nhầm dữ liệu từ node khác.
5. **Tác động hiệu năng:** FINE/FINER/FINEST có thể tăng thao tác format/I/O/CPU, áp lực đĩa và chi phí thu thập.

Nếu log được tổng hợp từ nhiều instance, gắn `service`, `instance_id`, `request_id` hoặc `trace_id` giúp truy ra node và request chính xác. Khi cần debug production, ưu tiên vùng hẹp và thời gian ngắn thay vì bật mọi log chi tiết vô thời hạn.

## 11. Thay đổi level có ảnh hưởng tới hiệu năng và dữ liệu không?

Có. Dù API đổi level thường đơn giản, **lượng log thực sự phát ra** có thể tăng mạnh.

**Logger lọc sớm:** nếu `isLoggable(Level.FINE)` là false, logger không tạo bản ghi ở mức đó. Tuy nhiên, Java sẽ tính các đối số của lời gọi method trước khi thực sự gọi hàm. Ví dụ:

```java
logger.fine("Payload = " + expensiveSerialize(payload));
```

`expensiveSerialize(payload)` vẫn chạy để nối chuỗi **ngay cả khi `FINE` đang bị lọc**. Đây là đoạn minh họa dùng biến/method giả định có sẵn. Với việc tạo thông điệp tốn kém, nên bảo vệ:

```java
if (logger.isLoggable(Level.FINE)) {
    logger.fine("Payload = " + expensiveSerialize(payload));
}
```

Hoặc dùng phương thức có **Supplier** của JUL:

```java
logger.log(Level.FINE,
        () -> "Payload = " + expensiveSerialize(payload));
```

Phần tính chuỗi nằm trong lambda được hoãn cho tới khi cần tạo message. Tuy vậy, lambda có thể chịu chi phí capture và bản ghi còn qua handler sau đó; cần đo thực tế thay vì giả định “bật log không tốn chi phí”.

Không ghi mật khẩu, token, khóa API, cookie xác thực, dữ liệu cá nhân nhạy cảm hoặc toàn bộ request body để debug. **Bật FINE không phải lý do bỏ qua quy tắc ẩn dữ liệu**. Dữ liệu có thể bị giữ trong hệ thống log tập trung lâu hơn thời gian debug và nhiều người có quyền xem.

## 12. Lỗi thường gặp khi đổi level

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Đã gọi `setLevel(FINE)` nhưng không thấy FINE | Handler đang để INFO/WARNING; logger không có handler nhận | Kiểm tra handler trực tiếp và trên chuỗi cha, propagation, filter |
| Đổi root sang WARNING nhưng vẫn thấy FINE | Logger con có level riêng và root handler cho phép FINE | Kiểm tra level thực sự của logger phát, handler root |
| `getLevel()` trả `null` | Logger kế thừa level từ cha | Dùng `isLoggable(...)`, kiểm tra `getParent()` |
| Thay file properties nhưng log không đổi | JVM chưa reload cấu hình | Dùng cơ chế reload chính thức hoặc API quản trị |
| Một dòng xuất hiện hai lần sau khi thêm handler | Cả logger con và logger cha/root có handler | Tránh gắn trùng hoặc kiểm soát `useParentHandlers` |
| Log mất sau khi gọi `setUseParentHandlers(false)` | Logger con không có handler riêng | Gắn handler phù hợp hoặc bật propagation |
| Chỉ một pod hiện log chi tiết | Thay đổi chỉ trong JVM/pod đó | Xác định và áp dụng phạm vi nhiều instance nếu cần |
| Restart xong mất cấu hình debug | Level chỉ thay trong RAM | Khôi phục có chủ đích hoặc đưa vào cấu hình khởi động |
| Bật FINE làm tăng latency hoặc dung lượng file | Ghi nhiều record, format/I/O lớn | Giới hạn logger, thời gian, sampling/retention phù hợp |
| Đổi level trong code JUL không ảnh hưởng log ứng dụng | Ứng dụng dùng SLF4J/Logback/Log4j2 | Kiểm tra logging backend thực sự và dùng API của backend |

**Cách kiểm tra tối thiểu trong JUL** (đoạn minh họa khi đã có biến `logger`):

```java
System.out.println("logger=" + logger.getName());
System.out.println("configuredLevel=" + logger.getLevel());
System.out.println("canLogFine=" + logger.isLoggable(Level.FINE));
System.out.println("useParentHandlers="
        + logger.getUseParentHandlers());

for (java.util.logging.Handler handler : logger.getHandlers()) {
    System.out.println("handler="
            + handler.getClass().getSimpleName()
            + " level=" + handler.getLevel());
}
```

`getHandlers()` chỉ trả về handler **gắn trực tiếp** vào logger đang kiểm tra; logger có thể còn xuất log qua handler của cha. Muốn chẩn đoán đầy đủ phải lần theo `getParent()` tới root nếu propagation đang bật.

## 13. Quy trình debug an toàn khi đang vận hành

Một cách thực hành cho service Java dùng JUL:

1. Ghi lại level hiện tại của logger **và các handler liên quan** trước khi đổi; phân biệt level đặt riêng với mức kế thừa (`null`).
2. Xác định logger hoặc package cần điều tra, instance và khoảng thời gian debug.
3. Đổi **logger mục tiêu** từ INFO sang FINE (hoặc mức phù hợp); nếu bản ghi bị chặn ở handler, chỉnh đúng handler theo quyền và phạm vi cho phép.
4. Tạo hoặc quan sát request liên quan. Tìm theo request ID/trace ID và xác nhận log xuất ra đúng console/file/backend.
5. Đọc log nhằm tìm mốc xử lý, bất thường và exception, tránh thu thập dữ liệu nhạy cảm.
6. **Hoàn nguyên** logger và handler theo giá trị đã lưu, kể cả null để tiếp tục kế thừa, ngay khi đủ dữ liệu.
7. Xác nhận lượng log trở lại bình thường và ghi nhận thay đổi cấu hình trong nhật ký vận hành nếu áp dụng cho production.

Với hệ thống có nhiều người vận hành, nên có thao tác “debug level tạm thời” được phân quyền, có thời hạn tự khôi phục và theo dõi được ai đã bật mức chi tiết. Trong ứng dụng phân tán, nếu thay đổi nhiều instance, cần ghi rõ những node nào đã cập nhật thành công và kiểm tra kết quả từng node.

## 14. Câu hỏi tự kiểm tra

**Câu 1:** Logger ở `INFO`, ConsoleHandler ở `FINE`; gọi `logger.fine(...)` có hiện không?  
**Đáp án:** Không. Logger lọc FINE trước khi handler nhận.

**Câu 2:** Logger ở `FINE`, ConsoleHandler ở `WARNING`; chỉ đổi logger sang `ALL` có làm dòng FINE xuất hiện không?  
**Đáp án:** Không. Handler vẫn lọc FINE. Phải điều chỉnh đúng handler nếu muốn xem FINE trên console.

**Câu 3:** `logger.setLevel(null)` có tắt log không?  
**Đáp án:** Không. Logger bỏ level đặt riêng và kế thừa từ cha.

**Câu 4:** Sửa file `logging.properties` trong khi JVM chạy có tự đổi ngưỡng không?  
**Đáp án:** Không bảo đảm và không phải hành vi tự động mặc định của JUL. Cần cơ chế reload/configuration được triển khai rõ ràng.

**Câu 5:** Bật FINE trên một pod có làm tất cả pod cùng bật FINE không?  
**Đáp án:** Không. Đây là thay đổi trong JVM đã nhận lệnh. Các instance khác cần được cấu hình tương ứng.

**Câu 6:** Tại sao cần nhớ level ban đầu là `null` hay `INFO`?  
**Đáp án:** `null` mang nghĩa kế thừa, khác với mức INFO cố định. Hoàn nguyên sai sẽ làm thay đổi hành vi logging lâu dài khi level logger cha đổi.

**Ghi nhớ:** Trong Java, đổi log level khi chạy chủ yếu là thao tác trên **logger hiện có** và có thể cả **handler đang nhận bản ghi**. Hiểu đúng quan hệ kế thừa, propagation và cấu hình backend mới giúp bật log chi tiết đúng phạm vi, quan sát được kết quả, rồi hoàn nguyên an toàn.
