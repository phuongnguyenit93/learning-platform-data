# Level của JUL trong Java: ý nghĩa, thứ tự và cách lọc bản ghi

## 1. JUL và log level

**Java Util Logging** (thường gọi là **JUL**) là API logging có sẵn trong JDK, nằm trong package `java.util.logging`. Khi chương trình gọi `Logger` để ghi một sự kiện, **`Level`** cho biết mức độ quan trọng hoặc mức chi tiết của sự kiện đó. JUL dùng level để quyết định bản ghi nào được tạo và chuyển tới các đích như console hoặc file.

Ví dụ, chương trình có thể ghi:

```java
logger.info("Ứng dụng đã khởi động");
logger.warning("Bộ nhớ đệm gần đầy");
logger.log(java.util.logging.Level.SEVERE, "Không thể lưu dữ liệu", exception);
```

Đây là các lệnh **minh họa**, giả định biến `logger` là `java.util.logging.Logger` và `exception` là một đối tượng `Throwable` đã có. Level của sự kiện không đồng nghĩa với việc nó chắc chắn xuất hiện: bản ghi còn đi qua **ngưỡng của logger**, **handler** và những bộ lọc khác nếu được cấu hình.

Mục tiêu của bài:

- Nắm đủ các level chuẩn của `java.util.logging.Level` và **thứ tự ưu tiên** của chúng.
- Hiểu sự khác nhau giữa **level của bản ghi**, **level của logger** và **level của handler**.
- Biết cách áp dụng level khi viết mã, cấu hình JUL và kiểm tra bản ghi bị lọc.
- Tránh nhầm `FINE/FINER/FINEST` của JUL với `DEBUG/TRACE` ở các logging backend khác.

## 2. Danh sách level chuẩn của JUL

Mỗi level trong JUL có một **tên**, một **giá trị số** (truy cập bằng `intValue()`) và cách dùng phù hợp.

| Level | Giá trị số | Mục đích thường gặp |
| --- | ---: | --- |
| `SEVERE` | 1000 | Lỗi nghiêm trọng: tác vụ không thể hoàn tất, chức năng bị ảnh hưởng. |
| `WARNING` | 900 | Điều bất thường hoặc nguy cơ lỗi cần chú ý; ứng dụng có thể tiếp tục. |
| `INFO` | 800 | Thông tin vận hành quan trọng như startup, shutdown, hoàn tất thao tác. |
| `CONFIG` | 700 | Chi tiết cấu hình hữu ích khi chẩn đoán cách ứng dụng hoạt động. |
| `FINE` | 500 | Chi tiết phục vụ debug, chẳng hạn rẽ nhánh xử lý hoặc bước gọi phụ. |
| `FINER` | 400 | Thông tin chi tiết hơn, như các bước bên trong thuật toán. |
| `FINEST` | 300 | Thông tin rất chi tiết, thường dành cho điều tra sâu. |
| `OFF` | `Integer.MAX_VALUE` | Giá trị đặc biệt: tắt việc ghi log tại ngưỡng đang áp dụng. |
| `ALL` | `Integer.MIN_VALUE` | Giá trị đặc biệt: cho phép mọi level thông thường qua ngưỡng. |

Các giá trị số lần lượt là: `SEVERE=1000`, `WARNING=900`, `INFO=800`, `CONFIG=700`, `FINE=500`, `FINER=400` và `FINEST=300`. Giá trị số **càng lớn** tương ứng với mức **càng nghiêm trọng/ít chi tiết**. `ALL` và `OFF` là hai giá trị điều khiển đặc biệt, không phải mức để gắn vào một sự kiện nghiệp vụ thông thường.

Có thể nhớ thứ tự:

```text
Nghiêm trọng / ít chi tiết
     SEVERE (1000)
        |
     WARNING (900)
        |
       INFO (800)
        |
      CONFIG (700)
        |
       FINE (500)
        |
      FINER (400)
        |
      FINEST (300)
Chi tiết hơn / thường phát sinh nhiều bản ghi hơn
```

**Không có `DEBUG` hoặc `TRACE` trong các hằng level chuẩn của JUL.** Những mức này quen thuộc trong SLF4J/Logback hoặc Log4j2, nhưng không thể viết `java.util.logging.Level.DEBUG` hay `java.util.logging.Level.TRACE`. Mức chi tiết trong JUL thường dùng `FINE`, `FINER` và `FINEST`. Cách quy đổi giữa framework phải dựa vào bridge/backend và cấu hình thật, không mặc định mọi tên mang ý nghĩa tương đương tuyệt đối.

### Ví dụ phân loại sự kiện

| Tình huống | Level gợi ý | Lý do |
| --- | --- | --- |
| Ứng dụng khởi động thành công | `INFO` | Sự kiện vòng đời quan trọng. |
| Cấu hình dùng chế độ cache nào | `CONFIG` | Hỗ trợ chẩn đoán nhưng thường không cần ở log vận hành hàng ngày. |
| Có thể retry do dịch vụ ngoài trả lỗi tạm thời | `WARNING` | Bất thường cần theo dõi, chưa chắc toàn bộ thao tác thất bại. |
| Yêu cầu bắt buộc bị hủy vì lỗi không khôi phục được | `SEVERE` | Tác vụ thất bại đáng kể. |
| Chọn nhánh xử lý tính giá | `FINE` | Chi tiết phục vụ debug. |
| Theo dõi từng bước/giá trị trung gian của thuật toán | `FINER` hoặc `FINEST` | Chỉ bật khi cần điều tra sâu. |

Đây là **quy ước thực hành**, không có quy tắc cứng buộc mọi `IOException` phải ở `SEVERE` hoặc mọi `IllegalArgumentException` phải ở `WARNING`. Hãy chọn mức theo **tác động của sự kiện trong ngữ cảnh xử lý**.

## 3. Ngưỡng level hoạt động thế nào?

Một level đặt trên logger/handler đóng vai trò là **ngưỡng tối thiểu**. Với các level thông thường, nếu giá trị số của bản ghi **lớn hơn hoặc bằng** ngưỡng, nó có thể đi qua bộ lọc level.

Ví dụ ngưỡng `INFO=800`:

- `SEVERE=1000`: được phép.
- `WARNING=900`: được phép.
- `INFO=800`: được phép.
- `CONFIG=700`, `FINE=500`, `FINER=400`, `FINEST=300`: bị lọc.

Ngưỡng `FINE=500` cho phép cả `FINE`, `CONFIG`, `INFO`, `WARNING` và `SEVERE`, nhưng vẫn lọc `FINER` và `FINEST`.

| Ngưỡng | Các mức thông thường có thể đi qua |
| --- | --- |
| `SEVERE` | Chỉ `SEVERE` |
| `WARNING` | `WARNING`, `SEVERE` |
| `INFO` | `INFO`, `WARNING`, `SEVERE` |
| `CONFIG` | `CONFIG`, `INFO`, `WARNING`, `SEVERE` |
| `FINE` | `FINE`, `CONFIG`, `INFO`, `WARNING`, `SEVERE` |
| `FINER` | Như trên, thêm `FINER` |
| `FINEST` | Tất cả bảy mức thông thường |
| `ALL` | Cho phép mọi mức tại bộ lọc level |
| `OFF` | Không cho phép bản ghi qua bộ lọc level |

Có một ngoại lệ kỹ thuật cần nhớ: `OFF` và `ALL` có cách xử lý **đặc biệt**, nên không sử dụng phép so sánh số học đơn giản để suy luận mọi tình huống. Trong mã ứng dụng, kiểm tra bằng API `logger.isLoggable(level)` thay vì tự so sánh mọi giá trị `intValue()`.

## 4. Phân biệt level của bản ghi, logger và handler

Ba thành phần dùng level theo vai trò khác nhau:

- **Level của bản ghi (record)**: mức được truyền vào lời gọi `logger.log(Level.FINE, ...)` hoặc từ phương thức ngắn như `logger.info(...)`.
- **Level của logger**: ngưỡng để logger quyết định có phát bản ghi hay không.
- **Level của handler**: ngưỡng độc lập để đích xuất log (console/file/...) quyết định có nhận bản ghi hay không.

Luồng xử lý cơ bản:

```text
logger.fine("Loading cache")
          |
          v
Logger level có cho phép FINE?
          |
     Không | Có
       X   |----> LogRecord(level=FINE)
                         |
                         v
                ConsoleHandler / FileHandler
                         |
                         v
                 Handler có cho FINE?
                    Không | Có
                      X   |----> Formatter ---> Console / File
```

Bảng dưới giả định không có filter bổ sung và handler thật sự nhận được record:

| Logger level | Handler level | Ghi `FINE` | Kết quả ở handler |
| --- | --- | --- | --- |
| `INFO` | `ALL` | `logger.fine(...)` | Bị chặn tại logger. |
| `FINE` | `INFO` | `logger.fine(...)` | Logger cho qua, handler chặn. |
| `FINE` | `FINE` | `logger.fine(...)` | Có thể xuất bản ghi. |
| `ALL` | `WARNING` | `logger.info(...)` | Handler chặn INFO. |
| `WARNING` | `ALL` | `logger.severe(...)` | Có thể xuất SEVERE. |
| `OFF` | `ALL` | `logger.severe(...)` | Logger không phát bản ghi. |

Vì thế **`logger.setLevel(Level.FINE)` chưa chắc làm bản ghi FINE xuất hiện**. Nếu `ConsoleHandler` vẫn ở `INFO` thì bản ghi bị chặn tại handler. Ngược lại, chỉ hạ `ConsoleHandler` xuống `FINE` không giúp ích nếu logger vẫn ở `INFO`.

Một `Logger` có thể chuyển bản ghi cho handler của logger cha, không nhất thiết có handler riêng. Khi điều tra vì sao bản ghi xuất hiện, cần xét **logger phát sinh, quan hệ cha–con, `useParentHandlers`, handler thực nhận, level của handler và filter**.

## 5. Ví dụ Java 17 đầy đủ: kiểm tra nhiều level

Ví dụ tạo một logger JUL riêng, gắn `ConsoleHandler` và định dạng ngắn để dễ kiểm tra. Chương trình thay ngưỡng logger và handler trong một lần chạy để phân biệt rõ hai nơi lọc.

Tạo file `JulLevelsDemo.java`:

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class JulLevelsDemo {
    private static final Logger LOG =
            Logger.getLogger(JulLevelsDemo.class.getName());

    public static void main(String[] args) {
        // Lưu cấu hình hiện tại để khôi phục sau ví dụ.
        Level oldLevel = LOG.getLevel();
        boolean oldParents = LOG.getUseParentHandlers();
        Handler[] oldHandlers = LOG.getHandlers();

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.ALL);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " | "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });

        for (Handler old : oldHandlers) {
            LOG.removeHandler(old);
        }
        LOG.setUseParentHandlers(false);
        LOG.addHandler(console);

        try {
            // 1. Logger INFO, handler ALL.
            LOG.setLevel(Level.INFO);
            LOG.fine("Hidden by logger");
            LOG.info("Service started");
            LOG.warning("Slow dependency");

            // 2. Logger FINE, handler WARNING.
            LOG.setLevel(Level.FINE);
            console.setLevel(Level.WARNING);
            LOG.fine("Hidden by handler");
            LOG.warning("Retry scheduled");

            // 3. Cả logger và handler đều cho phép FINE.
            console.setLevel(Level.FINE);
            LOG.fine("Cache key computed");
            LOG.config("Cache mode configured");

            // 4. OFF chặn bản ghi ở logger.
            LOG.setLevel(Level.OFF);
            LOG.severe("Hidden because logger is OFF");
        } finally {
            LOG.removeHandler(console);
            console.close();

            LOG.setLevel(oldLevel);
            LOG.setUseParentHandlers(oldParents);
            for (Handler old : oldHandlers) {
                LOG.addHandler(old);
            }
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa file:

```bash
javac JulLevelsDemo.java
java JulLevelsDemo
```

**Kết quả ở luồng stderr của `ConsoleHandler`:**

```text
INFO | Service started
WARNING | Slow dependency
WARNING | Retry scheduled
FINE | Cache key computed
CONFIG | Cache mode configured
```

Không có các dòng `Hidden by logger`, `Hidden by handler` và `Hidden because logger is OFF`.

**Giải thích:**

1. Ở giai đoạn 1, logger mức INFO loại bỏ FINE trước khi handler được gọi. `INFO` và `WARNING` đi qua, vì handler đặt ALL.
2. Ở giai đoạn 2, logger mức FINE chấp nhận FINE; nhưng handler mức WARNING loại bỏ FINE. `WARNING` vẫn được xuất.
3. Ở giai đoạn 3, handler chuyển thành FINE, vì vậy bản ghi `FINE` và `CONFIG` đều qua được cả hai ngưỡng.
4. Ở giai đoạn 4, `Level.OFF` trên logger chặn cả lời gọi `severe(...)`.
5. `setUseParentHandlers(false)` ngăn bản ghi lan lên handler mặc định của root logger để tránh in trùng. Chương trình khôi phục cấu hình đã thay đổi trong `finally`.

`ConsoleHandler` của JUL mặc định viết vào **`System.err`**, không phải `System.out`. Nếu terminal hiển thị hai luồng cùng nhau, vẫn nên biết chúng là các luồng riêng khi redirect hoặc thu thập log. `Formatter` của ví dụ cố tình bỏ timestamp; trong ứng dụng thật, timestamp, tên logger, context và exception thường rất cần thiết.

## 6. Các API Level quan trọng

### 6.1. Sử dụng phương thức ghi log

JUL có các phương thức tiện lợi cho mức thông dụng:

```java
logger.severe("Cannot connect to primary database");
logger.warning("Retrying operation");
logger.info("Application ready");
logger.config("Using in-memory cache");
logger.fine("Selecting query plan");
logger.finer("Entering helper method");
logger.finest("Visited state 42");
```

Đây là **đoạn minh họa** cần biến `logger` đã khai báo trong class/method. Tương đương có thể dùng phương thức chung:

```java
logger.log(Level.WARNING, "Retrying operation");
logger.log(Level.FINE, "Selecting query plan");
```

Phương thức `logger.log(Level.SEVERE, message, throwable)` còn nhận nguyên `Throwable` để formatter có thể in stack trace; đừng chỉ ghép `throwable.getMessage()` khi cần thông tin lỗi chi tiết.

### 6.2. Kiểm tra ngưỡng trước khi ghi

`Logger.isLoggable(Level.FINE)` trả về liệu logger có cho phép mức FINE hay không theo level hiệu lực của logger:

```java
if (logger.isLoggable(Level.FINE)) {
    logger.fine("Calculated subtotal = " + calculateSubtotal());
}
```

Đây là đoạn code minh họa giả định method `calculateSubtotal()` tồn tại. Kiểm tra này giúp tránh tính toán thông điệp đắt đỏ khi logger đã chặn FINE, nhưng **không đảm bảo** có handler nào thực sự xuất bản ghi.

Vì Java đánh giá đối số trước khi gọi method, đoạn code:

```java
logger.fine("Calculated subtotal = " + calculateSubtotal());
```

vẫn gọi `calculateSubtotal()` dù level FINE đang bị lọc ở logger. JUL hỗ trợ phương thức dùng `Supplier<String>` để tạo message khi cần:

```java
logger.log(Level.FINE,
        () -> "Calculated subtotal = " + calculateSubtotal());
```

Trong ví dụ này, nội dung trong lambda chỉ được tạo khi logger chấp nhận level. Tuy nhiên, handler vẫn có thể lọc bản ghi sau đó; Supplier không đảm bảo loại bỏ mọi chi phí. Với nội dung nhạy cảm, vẫn phải kiểm soát giá trị được ghi, kể cả ở level FINEST.

### 6.3. Khám phá tên và giá trị số của level

`Level.getName()` trả về tên (ví dụ `"WARNING"`), còn `intValue()` trả về giá trị số. `Level.parse(String)` hỗ trợ phân tích tên level đã đăng ký hoặc biểu diễn số hợp lệ.

```java
import java.util.logging.Level;

public class JulLevelValues {
    public static void main(String[] args) {
        System.out.println(Level.WARNING.getName());
        System.out.println(Level.WARNING.intValue());
        System.out.println(Level.parse("FINE") == Level.FINE);
    }
}
```

Biên dịch và chạy:

```bash
javac JulLevelValues.java
java JulLevelValues
```

**Kết quả stdout chính xác:**

```text
WARNING
900
true
```

Khi xử lý chuỗi cấu hình không đáng tin cậy, cần bắt `IllegalArgumentException` nếu tên level không hợp lệ, ví dụ `Level.parse("DEBUG")` trên JUL chuẩn không xác định một hằng DEBUG và thường ném lỗi nếu chưa có level tùy biến tên đó được đăng ký. Nếu dự án đăng ký các level riêng qua class con `Level`, tập tên có thể khác; không nên mặc định mọi ứng dụng chỉ có đúng các tên trong bảng level chuẩn.

## 7. Level đặt trực tiếp, level kế thừa và root logger

Các logger JUL có thể có quan hệ cha–con. Một logger đặt `setLevel(null)` nghĩa là **không đặt ngưỡng riêng** và sẽ **kế thừa level hiệu lực từ cha** gần nhất có level cụ thể, cuối cùng thường là root logger.

Ví dụ minh họa bên trong method:

```java
Logger parent = Logger.getLogger("com.example.payment");
Logger child = Logger.getLogger("com.example.payment.PaymentService");

parent.setLevel(Level.WARNING);
child.setLevel(null); // Kế thừa từ parent.
System.out.println(child.getLevel());                  // null
System.out.println(child.isLoggable(Level.INFO));      // false
System.out.println(child.isLoggable(Level.SEVERE));    // true

child.setLevel(Level.FINE); // Có ngưỡng riêng.
System.out.println(child.isLoggable(Level.FINE));      // true
```

Đoạn này **không phải file Java độc lập**; đặt trong `main` có import `java.util.logging.Level` và `Logger` để chạy. Do code tạo logger `parent` trước `child` và thiết lập level, child sẽ có parent tên `com.example.payment` trong ví dụ này. `getLevel()==null` **không có nghĩa OFF**: nó chỉ báo logger kế thừa.

Trong trường hợp logger trung gian chưa tồn tại, một logger tên dài có thể có cha trực tiếp là root. Vì vậy muốn phân tích quan hệ thật, dùng `getParent()` thay vì suy đoán chắc chắn từ các dấu chấm trong tên logger.

### Root level và handler của root

Root logger JUL có tên chuỗi rỗng `""`:

```java
Logger root = Logger.getLogger("");
root.setLevel(Level.INFO);
```

Thay đổi root level thường ảnh hưởng đến logger con **đang kế thừa mức từ root**, nhưng không ghi đè level riêng của từng logger. Một điểm quan trọng: khi logger con đã tạo một log record và chuyển lên handler của logger cha/root, JUL **không kiểm tra lại level của logger cha**; mỗi handler vẫn tự kiểm tra level/filter của nó.

Ví dụ:

- Root logger `WARNING`.
- Logger con có level riêng `FINE`.
- Handler của root đặt `FINE`.
- Logger con bật `useParentHandlers` và trên đường tới root không bị chặn.

Kết quả: bản ghi `FINE` của logger con **vẫn có thể xuất** qua handler của root, dù level ở root là WARNING. Người học dễ nhầm rằng root WARNING sẽ luôn chặn FINE từ mọi logger con.

Mặc định, logger con có thể chuyển record lên cha bằng `useParentHandlers=true`. Nếu cả logger con và root đều gắn handler ghi console, một record có thể xuất hai lần. Khi muốn logger con sử dụng handler riêng, có thể gọi `setUseParentHandlers(false)`, nhưng phải bảo đảm logger con đã có handler nhận log; nếu không các bản ghi có thể không đi tới đích nào.

## 8. Cấu hình level qua logging.properties

Khi ứng dụng dùng JUL, có thể cấu hình level **lúc khởi động JVM** thay vì viết `setLevel(...)` trong mã nguồn.

Tạo file `logging.properties`:

```properties
# Handler console gắn ở root logger.
handlers = java.util.logging.ConsoleHandler

# Level mặc định cho logger kế thừa từ root.
.level = INFO

# Handler có ngưỡng riêng.
java.util.logging.ConsoleHandler.level = FINE
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter

# Chỉ package logger này ghi tới mức FINE.
demo.jul.level = FINE
```

Tạo file `JulConfigDemo.java` trong cùng thư mục:

```java
import java.util.logging.Logger;

public class JulConfigDemo {
    private static final Logger LOG = Logger.getLogger("demo.jul");

    public static void main(String[] args) {
        LOG.info("Service started");
        LOG.fine("Diagnostic detail");
    }
}
```

Biên dịch và chạy:

```bash
javac JulConfigDemo.java
java -Djava.util.logging.config.file=logging.properties JulConfigDemo
```

`SimpleFormatter` thường ghi ra console cả hai bản ghi **INFO** và **FINE** (kèm ngày giờ, tên logger, thread/source tùy định dạng), vì:

- `demo.jul.level=FINE` cho logger `demo.jul` phép tạo record FINE.
- `ConsoleHandler.level=FINE` cho phép handler của root xuất FINE.
- Root level INFO dùng làm ngưỡng kế thừa mặc định; nó không loại lại FINE khi record từ logger con được chuyển tới handler root.

Không nên đối chiếu nguyên văn console output của `SimpleFormatter` với ví dụ ở mục 5, vì SimpleFormatter có thêm thời gian và các trường khác. Nếu bỏ `demo.jul.level=FINE`, logger demo sẽ kế thừa root INFO và **không phát bản ghi FINE**. Nếu đổi `ConsoleHandler.level` thành INFO, log FINE có thể được logger chấp nhận nhưng **không hiển thị trên console**.

`-Djava.util.logging.config.file` là thuộc tính hệ thống của JVM trỏ tới file cấu hình. Với đường dẫn tương đối, JVM đọc từ thư mục làm việc lúc chạy. Việc **sửa file** sau khi JVM đã khởi động **không tự cập nhật** JUL nếu không có thao tác reload hoặc cơ chế quản trị được cấu hình; một thay đổi level lúc chạy qua `Logger.setLevel(...)` cũng thường không tồn tại sau khi restart nếu không ghi nhận ở cấu hình khởi động.

**Lưu ý về framework:** Spring Boot thông thường log qua SLF4J và backend như Logback. Các thuộc tính `java.util.logging.ConsoleHandler.level` chỉ điều khiển handler JUL, không tự cấu hình toàn bộ logger của backend khác. Cần xác định backend thực tế và các bridge trước khi đổi level.

## 9. Chỉnh level khi chạy và giá trị null

JUL cho phép đổi level trong JVM đang chạy:

```java
Logger payment = Logger.getLogger("com.example.payment");

Level previousLevel = payment.getLevel();
try {
    payment.setLevel(Level.FINE);  // Tạm bật log chi tiết.
    // Thực hiện tác vụ cần quan sát.
} finally {
    payment.setLevel(previousLevel); // Khôi phục, kể cả null.
}
```

Đây là **đoạn minh họa**. Trong ứng dụng đa luồng, việc đổi logger được dùng chung có thể ảnh hưởng các request khác cùng lúc. Cần giới hạn người có quyền đổi, phạm vi logger, thời gian bật log chi tiết và nơi nhận dữ liệu. Nếu ứng dụng chạy trên nhiều JVM, đổi level tại một JVM **không lan tự động** sang JVM khác.

Lưu ý: `getLevel()` trả về level được đặt **trực tiếp**, có thể là `null` khi kế thừa. Khôi phục `null` rất quan trọng: ép mọi logger về INFO sau debug có thể vô tình phá cơ chế kế thừa level từ logger cha.

Nên điều chỉnh logger cụ thể theo package/class thay vì mặc định chuyển toàn bộ root logger sang FINEST. Tăng độ chi tiết quá rộng làm tăng số bản ghi, chi phí I/O, dung lượng lưu trữ và nguy cơ ghi dữ liệu bí mật.

## 10. Level trong exception logging

Có thể truyền nguyên `Throwable` cho JUL:

```java
try {
    saveOrder();
} catch (java.io.IOException exception) {
    logger.log(Level.SEVERE, "Cannot save order", exception);
}
```

Đây là đoạn minh họa giả định `saveOrder()` là method có sẵn và `logger` là `Logger`. Mức SEVERE phù hợp nếu thao tác bắt buộc thất bại và không còn phương án xử lý. Nếu ứng dụng có fallback và sẽ thử lại bình thường, mức WARNING hoặc INFO có thể hợp lý hơn tùy trường hợp.

Truyền `Throwable` làm tham số cho `log(Level, String, Throwable)` giữ exception trong `LogRecord`. Có thấy stack trace hay không còn phụ thuộc formatter: `SimpleFormatter` hỗ trợ in exception, còn formatter tùy biến chỉ lấy `record.getMessage()` có thể làm mất stack trace. Level không tự quyết định việc in hay không in các frame của stack trace.

Tránh vừa `exception.printStackTrace()` vừa `logger.log(..., exception)` cho cùng lỗi ở cùng boundary khi không có lý do rõ ràng; cách đó dễ tạo log trùng. Với tác vụ đáng lỗi thật sự, chọn level phù hợp rồi ghi đủ ngữ cảnh an toàn để điều tra.

## 11. Chi phí và bảo mật khi chọn level

Bật các mức `FINE`, `FINER`, `FINEST` giúp điều tra lỗi nhưng có chi phí:

- Nhiều log record hơn làm tăng CPU, thao tác format và I/O.
- File log có thể tăng nhanh nếu không có rotation/retention.
- Hệ thống thu thập tập trung có thể tính phí theo dung lượng; log quá nhiều gây khó tìm sự kiện quan trọng.
- Nội dung debug có thể vô tình chứa khóa API, token, cookie xác thực, thông tin cá nhân, câu SQL kèm tham số nhạy cảm.

Không đưa password, token hay nội dung người dùng nhạy cảm vào thông điệp log dù level là FINEST. Log level không phải cơ chế kiểm soát quyền truy cập dữ liệu. Hãy bảo vệ cả điểm tạo bản ghi, formatter và quyền đọc ở hệ thống lưu log.

Về hiệu năng, thường có lợi khi chặn sớm những message tốn chi phí tạo chuỗi, ví dụ dùng `isLoggable` hoặc overload `Supplier<String>`. Tuy nhiên, logic tạo log cũng không nên có side effect thiết yếu: khi level bị lọc, supplier có thể không được chạy.

## 12. Lỗi thường gặp và cách kiểm tra

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `logger.fine(...)` không hiển thị | Logger đang INFO/WARNING; handler INFO; filter khác | Kiểm tra `logger.isLoggable(Level.FINE)`, handler level, propagation và filter. |
| Đổi logger sang ALL nhưng vẫn không thấy FINEST | Handler chỉ nhận INFO hoặc WARNING | Điều chỉnh đúng handler nếu muốn xem FINEST. |
| `logger.getLevel()` trả về null | Logger kế thừa mức từ cha | Không coi null là OFF; kiểm tra `getParent()` và `isLoggable(...)`. |
| Đổi root level nhưng một logger vẫn phát FINE | Logger con đã đặt level riêng; root handler chấp nhận | Kiểm tra level tại logger phát và handler nhận. |
| Cùng sự kiện xuất hai lần | Logger con và cha/root đều có handler, propagation bật | Chỉ dùng handler chung hoặc tắt propagation khi có handler riêng. |
| File log không có CONFIG dù console có | Handler file có level cao hơn CONFIG, hoặc filter khác | Kiểm tra ngưỡng `FileHandler`, formatter và đường dẫn. |
| Đổi `logging.properties` khi chạy nhưng mức không thay | Không có tự động reload | Dùng cơ chế reload/quản trị hoặc khởi động lại theo quy trình. |
| Dùng `Level.DEBUG` gây lỗi biên dịch | JUL không định nghĩa DEBUG | Chọn level JUL tương ứng theo nhu cầu. |
| Log có message nhưng thiếu stack trace | Ghi mỗi `exception.getMessage()` hoặc formatter bỏ `getThrown()` | Truyền nguyên Throwable và dùng formatter hỗ trợ exception. |
| Level FINEST khiến log quá nhiều | Cấu hình phạm vi rộng và không giới hạn lưu | Chỉ bật tạm ở logger cần thiết; thiết lập rotation, retention và thu hồi. |

### Checklist chẩn đoán một bản ghi bị mất

1. Xác nhận ứng dụng đang dùng `java.util.logging.Logger` hay backend khác.
2. Xác nhận logger **phát** bản ghi: tên logger và level đặt trực tiếp.
3. Kiểm tra level hiệu lực qua `logger.isLoggable(mứcCầnGhi)`, nhớ xét kế thừa nếu `getLevel()==null`.
4. Kiểm tra handler gắn trực tiếp (`logger.getHandlers()`) và handler của các logger cha nếu `getUseParentHandlers()` bật.
5. Kiểm tra mức `handler.getLevel()`, filter, formatter và khả năng ghi vào console/file.
6. Kiểm tra bản ghi có thực sự được tạo ở nhánh mã đang chạy không, sau đó xác nhận hệ thống thu thập có giữ dữ liệu hay không.

`logger.getHandlers()` chỉ trả về các handler gắn **trực tiếp** lên logger được gọi; độ dài mảng bằng 0 **không đủ** để kết luận không có nơi xuất log, vì bản ghi có thể đi lên root.

## 13. Tự kiểm tra hiểu biết

**Câu 1.** Logger mức INFO; ConsoleHandler mức ALL. `logger.fine(...)` có xuất lên console không?

**Đáp án:** Không. Logger INFO loại bỏ FINE trước khi handler nhận.

**Câu 2.** Logger mức FINE; FileHandler mức INFO. `logger.config(...)` có vào file không?

**Đáp án:** Không. CONFIG=700 đạt ngưỡng FINE=500 tại logger nhưng thấp hơn INFO=800 tại FileHandler.

**Câu 3.** Muốn quan sát `FINER`, chọn mức tối thiểu ở cả logger và handler là gì?

**Đáp án:** `FINER` hoặc mức chi tiết hơn (`FINEST`/`ALL`), với điều kiện không có filter khác chặn và handler thực nhận record.

**Câu 4.** `logger.setLevel(null)` có vô hiệu hóa logging không?

**Đáp án:** Không. Nó làm logger kế thừa level từ cha gần nhất có mức xác định.

**Câu 5.** Vì sao root logger WARNING mà bản ghi FINE của logger con vẫn có thể xuất qua root handler?

**Đáp án:** Logger con có thể đặt mức riêng FINE và phát record. Khi record được chuyển lên, JUL không kiểm tra lại root logger level; root handler tự quyết định theo mức/filter của nó.

**Câu 6.** Mức `CONFIG` được lọc như thế nào tại ngưỡng `INFO`?

**Đáp án:** Bị lọc vì CONFIG=700 nhỏ hơn INFO=800. Hạ ngưỡng tới CONFIG hoặc FINE/FINER/FINEST/ALL nếu muốn nhìn thấy CONFIG.

**Câu 7.** Bật toàn bộ FINEST trên production có nên duy trì lâu dài?

**Đáp án:** Thường không. Nên chỉ bật ở vùng cần debug trong thời gian ngắn, kiểm soát dữ liệu nhạy cảm và dung lượng, sau đó khôi phục ngưỡng ban đầu.

**Ghi nhớ:** JUL có bảy mức thông thường **SEVERE → WARNING → INFO → CONFIG → FINE → FINER → FINEST**, cùng **OFF** và **ALL**. Level của record phải đi qua **ngưỡng logger**, rồi qua **ngưỡng handler**. Kế thừa level và chuyển bản ghi qua logger cha là hai cơ chế khác nhau; hiểu cả hai mới điều khiển log chính xác.
