# 5.3 java.util.logging: Logger, Handler, Formatter và cấu hình mức ghi

`java.util.logging` (thường viết tắt là **JUL**) là API logging có sẵn trong Java SE, thuộc module `java.logging`. Nó cho phép chương trình phát sinh bản ghi sự kiện mà không phụ thuộc trực tiếp vào đích xuất: cùng một lời gọi ghi log có thể được lọc theo mức độ, đưa tới console, file hoặc một `Handler` tùy biến, rồi định dạng theo cách thích hợp với người vận hành.

Trong chẩn đoán JVM, điều quan trọng không chỉ là gọi `logger.info(...)`. Người điều tra phải trả lời được: **vì sao một dòng FINE không xuất hiện, vì sao một sự kiện được in hai lần, vì sao stack trace bị mất, chính xác cấu hình nào đang có hiệu lực và việc tăng độ chi tiết sẽ ảnh hưởng hệ thống ra sao?**

Bài này hướng dẫn cơ chế dữ liệu `Logger → LogRecord → Handler → Formatter`, hệ thống `Level` và kế thừa theo tên, cấu hình qua `logging.properties` và qua mã Java 17+, các lỗi phổ biến khi thu thập log, cùng quy trình bật/tắt mức ghi có kiểm soát khi xử lý sự cố.

## 1. Mô hình xử lý một bản ghi JUL

Một lệnh như:

```java
private static final java.util.logging.Logger LOG =
        java.util.logging.Logger.getLogger("com.example.checkout");

LOG.info("checkout started"); // Minh họa trong một method, không phải file độc lập.
```

đi qua nhiều lớp có chức năng khác nhau:

```text
                         Logger "com.example.checkout"
  log(Level, message)  ─────────────┐
                                    ▼
                          Effective Logger Level
                          + Logger Filter (nếu có)
                                    │
                          cho qua → LogRecord
                                    │
                     ┌──────────────┴──────────────┐
                     ▼                             ▼
               Own Handlers              Parent Logger Handlers
                     │                    (mặc định có chuyển tiếp)
              Handler Level                        │
              + Handler Filter               Handler Level
                     │                       + Handler Filter
                     ▼                             ▼
                 Formatter                     Formatter
                     │                             │
                     ▼                             ▼
               stdout/file/…                   stderr/file/…
```

Phân chia trách nhiệm:

| Thành phần | Câu hỏi nó quyết định | Điều cần nhớ |
| --- | --- | --- |
| `Logger` | Bản ghi từ thành phần nào, mức độ nào có được tạo ra? | Có tên phân cấp; có mức hiệu lực và có thể có `Filter` |
| `Level` | Bản ghi đủ quan trọng để đi qua ngưỡng không? | Ngưỡng của Logger **khác** ngưỡng của Handler |
| `LogRecord` | Sự kiện chứa thời điểm, level, message, tham số và lỗi nào? | Là dữ liệu được chuyển qua pipeline |
| `Handler` | Gửi bản ghi tới đâu, có lọc tiếp không? | Mỗi Handler có mức và Filter riêng |
| `Formatter` | Chuyển LogRecord thành text/XML hoặc định dạng khác thế nào? | Không tự quyết định bản ghi có được tạo ra |
| `LogManager` | Quản lý namespace Logger và cấu hình tập trung ra sao? | Hỗ trợ file properties và thay đổi runtime |

**Một dòng log xuất hiện hay không là kết quả của cả pipeline**, không chỉ của `Logger.getLevel()`. Nếu Logger cho phép `FINE` nhưng `ConsoleHandler` vẫn đặt `INFO`, bản ghi FINE không được ConsoleHandler xuất. Ngược lại, khi child Logger tạo được LogRecord, việc gửi lên các Handler của parent theo mặc định không có nghĩa gọi lại toàn bộ bước xét level của parent Logger.

### 1.1. LogRecord chứa gì?

`LogRecord` ghi thông tin như:

- `getLevel()`, `getLoggerName()` và message gốc;
- `getInstant()`: thời điểm event dưới dạng `Instant` (Java 17);
- `getParameters()`: tham số để Formatter xử lý message;
- `getThrown()`: `Throwable` gốc, phục vụ stack trace;
- tên class/method nguồn nếu được cung cấp hoặc được suy ra;
- thread identity và metadata tùy API/phiên bản.

`LogRecord` không tự trở thành JSON có trace ID. JUL cơ bản **không có MDC/structured context giống một số framework khác**; nếu cần request/trace ID, hãy thiết kế cách truyền context, cách định dạng và sự tương thích với thread pool hoặc virtual threads riêng, tránh giả định context tự đi theo mọi tác vụ bất đồng bộ.

## 2. Logger: tên, phân cấp, mức hiệu lực và xử lý parent

### 2.1. Tạo Logger và giữ tham chiếu

Quy ước phổ biến là đặt tên theo package/class:

```java
import java.util.logging.Logger;

public final class CheckoutService {
    private static final Logger LOG =
            Logger.getLogger(CheckoutService.class.getName());

    public void process() {
        LOG.info("checkout accepted");
    }
}
```

Đây là **class có thể biên dịch bằng JDK 17+**, nhưng không có `main` nên chỉ là thành phần ứng dụng. `Logger.getLogger(name)` tìm hoặc tạo Logger được quản lý bởi `LogManager`. Nên giữ tham chiếu mạnh, chẳng hạn một trường `static final`: LogManager có thể chỉ giữ tham chiếu yếu tới Logger trong namespace, vì thế các lời gọi lấy Logger thoáng qua không phải lúc nào cũng trỏ đến cùng một object nếu không còn tham chiếu mạnh.

Dấu chấm trong tên Logger tạo quan hệ phân cấp, ví dụ:

```text
"" (root)
└── com
    └── com.example
        └── com.example.checkout
            └── com.example.checkout.PaymentService
```

Đây là **cây tên logic**; parent thực là Logger tổ tiên gần nhất **đang tồn tại**, không nhất thiết mọi nút trong sơ đồ đều đã được tạo. Root Logger có tên chuỗi rỗng `""`.

### 2.2. Level được chỉ định và level hiệu lực

`logger.getLevel()` trả level **đặt trực tiếp trên Logger**, có thể là `null`. Khi là `null`, Logger kế thừa level hiệu lực của parent gần nhất có mức xác định. Vì vậy:

- `logger.setLevel(Level.FINE)`: ghi đè ngưỡng của Logger này thành FINE.
- `logger.setLevel(null)`: bỏ ngưỡng riêng, lấy ngưỡng kế thừa.
- `logger.isLoggable(Level.FINE)`: kiểm tra yêu cầu ở mức FINE có qua **ngưỡng hiệu lực của Logger** không.
- `logger.getLevel() == null` **không** có nghĩa Logger đang tắt.

Thay đổi level của một parent có thể ảnh hưởng tới các child đang kế thừa. Child có level được đặt riêng tiếp tục dùng level riêng của mình.

**Cảnh báo chẩn đoán:** `isLoggable(Level.FINE) == true` không bảo đảm dòng FINE tới file/console. Handler vẫn có thể bác bỏ bản ghi bằng level hoặc Filter; việc xuất có thể thất bại do I/O hoặc cấu hình output.

### 2.3. Mức của Logger và Handler là hai cửa kiểm tra

Ví dụ:

| Logger effective level | ConsoleHandler level | Event phát sinh | Kết quả tại ConsoleHandler |
| --- | --- | --- | --- |
| `INFO` | `INFO` | `FINE` | Không tạo bản ghi ở ngưỡng Logger |
| `FINE` | `INFO` | `FINE` | Logger cho qua, Handler bỏ |
| `INFO` | `FINE` | `FINE` | Logger bỏ; handler thấp hơn không giúp |
| `FINE` | `FINE` | `FINE` | Có thể xuất nếu không bị Filter chặn |
| `WARNING` | `INFO` | `SEVERE` | Có thể xuất |
| `OFF` | `ALL` | `SEVERE` | Không tạo log vì Logger bị tắt |

Đây là ma trận cho **một Handler được kết nối**. Một Logger có thể gửi cùng LogRecord tới nhiều Handler; output cuối còn phụ thuộc parent handlers, filter, lỗi I/O và cài đặt của từng handler.

### 2.4. Parent handlers và lỗi “log in hai lần”

Mặc định `logger.getUseParentHandlers()` là `true`. Nếu một Handler được gắn vào Logger `com.example.checkout` và root cũng có ConsoleHandler, một LogRecord có thể được cả hai Handler in ra, trông như chương trình ghi hai lần.

```java
Logger log = Logger.getLogger("com.example.checkout");
log.setUseParentHandlers(false);
```

Đặt `false` chặn đường chuyển tiếp tới parent, **nhưng phải có Handler riêng hoặc cách xuất hợp lệ**; nếu không, log có thể biến mất. Nếu chủ đích là mọi service dùng root ConsoleHandler, cách đơn giản là không tự gắn thêm ConsoleHandler vào từng Logger. Khi phân tích trùng log, cũng kiểm tra log collector đọc cả stdout lẫn file, appender từ framework khác, bridge và pipeline gửi bản ghi nhiều lần.

Một bẫy chuyên sâu: **parent Logger level/filter không được áp dụng lại như vòng kiểm tra độc lập cho LogRecord đã được child chấp nhận** trên đường chuyển tiếp; điều quyết định tại parent output thường là cấu hình **parent Handler**. Vì vậy để chặn FINE tại console chung, xem level của ConsoleHandler chứ không chỉ root `.level`.

## 3. Thứ tự mức ghi (Level) và chọn mức đúng mục đích

Các mức JUL chuẩn, xếp từ ưu tiên cao xuống thấp:

| Level | Giá trị số chuẩn | Cách dùng thường gặp |
| --- | ---: | --- |
| `OFF` | `Integer.MAX_VALUE` | Tắt logging ở Logger/Handler tương ứng |
| `SEVERE` | 1000 | Lỗi nghiêm trọng khiến chức năng không thể hoàn tất |
| `WARNING` | 900 | Điều kiện bất thường có thể phục hồi hoặc cần chú ý |
| `INFO` | 800 | Mốc vận hành quan trọng, trạng thái lifecycle |
| `CONFIG` | 700 | Thông tin cấu hình, tùy use case |
| `FINE` | 500 | Chi tiết debug khi điều tra |
| `FINER` | 400 | Chi tiết sâu hơn, dễ phát sinh lượng log lớn |
| `FINEST` | 300 | Truy vết rất chi tiết, chỉ bật có giới hạn |
| `ALL` | `Integer.MIN_VALUE` | Cho phép mọi mức qua ngưỡng (trừ Filter khác) |

`Level.SEVERE` cao hơn `Level.WARNING`, rồi `INFO`... Một ngưỡng `INFO` chấp nhận `INFO`, `WARNING`, `SEVERE`. Một ngưỡng `FINE` chấp nhận cả các mức từ FINE trở lên. `ALL` và `OFF` là hai giá trị đặc biệt; các thư viện cũng có thể định nghĩa mức tùy biến, vì vậy khi so sánh phải nhớ quy tắc giá trị số.

**Gợi ý phân loại sự kiện:**

- `SEVERE`: giao dịch không thể xử lý vì một lỗi nghiêm trọng; phải kèm nguyên nhân và ngữ cảnh an toàn.
- `WARNING`: retry do dependency tạm thời, cấu hình không mong muốn, nhưng còn đường phục hồi.
- `INFO`: startup/shutdown, version/port/profile đã lọc dữ liệu nhạy cảm, kết quả vận hành quan trọng.
- `CONFIG`: thông tin chọn chiến lược cấu hình khi chẩn đoán; không được chứa secret.
- `FINE`/`FINER`/`FINEST`: quyết định nội bộ, đường đi xử lý, snapshot chi tiết có giới hạn.

Không coi INFO là nơi in toàn bộ payload request, không dùng SEVERE cho mọi exception được retry thành công, và không đặt FINEST làm mặc định cho production bận rộn.

## 4. API ghi log đúng cách

### 4.1. Phương thức tiện ích và `log(...)`

```java
Logger log = Logger.getLogger("com.example.checkout");

log.severe("payment failed");
log.warning("retry scheduled");
log.info("checkout completed");
log.config("strategy selected");
log.fine("cache miss");
log.finer("validation detail");
log.finest("per-field trace");
```

Đây là snippet trong scope một method hoặc static initializer, không phải ứng dụng độc lập. Tùy ngưỡng, chỉ một số lời gọi được tạo thành LogRecord. Có thể dùng overload nhận `Level`:

```java
log.log(Level.WARNING, "attempt={0}", 2);
log.log(Level.INFO, "order={0}, status={1}",
        new Object[]{"A-12", "accepted"});
```

Message ở đây dùng tham số dạng `{0}`, `{1}` theo phong cách `java.text.MessageFormat` khi Formatter gọi `formatMessage(record)`; **không phải** kiểu `%s` của `String.format` hay `{ }` của một số facade logging khác. Formatter tùy chỉnh không gọi `formatMessage` có thể để nguyên placeholders.

### 4.2. Ghi exception và stack trace đầy đủ

Dùng overload nhận `Throwable`:

```java
try {
    // Thao tác có thể ném lỗi.
} catch (RuntimeException ex) {
    log.log(Level.SEVERE, "Cannot complete checkout", ex);
}
```

Đây là snippet minh họa trong method, không chạy độc lập. Tham số `ex` được đặt vào `LogRecord.getThrown()`. Các formatter chuẩn phù hợp có thể xuất stack trace; **custom Formatter phải tự xử lý Throwable** nếu muốn giữ stack trace. `log.severe(ex.getMessage())` chỉ ghi một chuỗi, có thể mất loại exception, cause chain, stack frames và ngữ cảnh.

Tránh vừa ghi SEVERE ở tầng thấp vừa ném lại rồi ghi thêm cùng exception ở tầng controller nếu không có mục đích riêng; điều này dễ khiến một lỗi bị tính thành nhiều incident.

### 4.3. Sinh thông điệp theo nhu cầu để giảm chi phí

Với chuỗi tốn CPU/RAM để dựng:

```java
log.fine(() -> "snapshot=" + buildExpensiveSnapshot());
```

Đây là snippet; giả định method `buildExpensiveSnapshot()` tồn tại. `Supplier<String>` giúp hoãn dựng chuỗi nếu Logger không chấp nhận mức FINE. Cũng có thể dùng:

```java
if (log.isLoggable(Level.FINE)) {
    log.fine("snapshot=" + buildExpensiveSnapshot());
}
```

**Giới hạn:** `isLoggable` chỉ xét ngưỡng Logger, không biết Handler cuối có ghi thành công không. Dù dùng Supplier, log nhiều bản ghi, format stack trace, serialize đối tượng lớn, I/O đồng bộ và thu thập context vẫn có overhead. Không gửi trực tiếp toàn bộ object chứa password/token/PII vào `toString()` để “debug nhanh”.

### 4.4. Filter dùng khi cần quy tắc tinh hơn level

`Filter` có thể gắn vào Logger hoặc Handler:

```java
import java.util.logging.Filter;
import java.util.logging.LogRecord;

Filter onlyWarnings = new Filter() {
    @Override
    public boolean isLoggable(LogRecord record) {
        return record.getLevel().intValue()
                >= java.util.logging.Level.WARNING.intValue();
    }
};
```

Đây là đoạn minh họa, có thể đặt trong một method; `onlyWarnings` cần gắn qua `logger.setFilter(...)` hoặc `handler.setFilter(...)` để có hiệu lực. Dùng Filter của Handler khi muốn chỉ thay đổi **một sink** (ví dụ file cảnh báo) mà không ảnh hưởng sink khác. Không dùng Filter sơ sài để xử lý an toàn dữ liệu; vì thông điệp có thể chứa parameters/exception/stack trace, việc redaction cần thiết kế rõ và kiểm thử.

## 5. Ví dụ Java 17+ chạy độc lập: Logger + Handler + Formatter

Ví dụ này cố ý dùng `StreamHandler` nối với `System.out` và `Formatter` tự định nghĩa để có **stdout xác định**, không phụ thuộc ngày/giờ hiện tại. Đây là một chương trình Java hoàn chỉnh giúp thấy hai mức lọc và vì sao cần `flush()`.

Lưu tên file **`JulFlowDemo.java`**:

```java
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class JulFlowDemo {
    public static void main(String[] args) {
        Logger logger = Logger.getLogger("training.jul.flow");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.FINE);

        Formatter formatter = new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " | " + formatMessage(record)
                        + System.lineSeparator();
            }
        };

        StreamHandler handler =
                new StreamHandler(System.out, formatter);
        handler.setLevel(Level.FINE);
        logger.addHandler(handler);

        logger.fine("cache miss");
        logger.log(Level.WARNING, "attempt={0}", 2);
        logger.finest("not emitted");

        handler.flush();
        logger.removeHandler(handler);
        // Không close vì handler đang giữ System.out của demo.
    }
}
```

Biên dịch/chạy trong thư mục chứa file bằng **JDK 17+**:

```bash
javac JulFlowDemo.java
java JulFlowDemo
```

Stdout (nội dung từng dòng là cố định; ký tự xuống dòng phụ thuộc hệ điều hành):

```text
FINE | cache miss
WARNING | attempt=2
```

Tại sao chỉ có hai dòng?

1. Logger `training.jul.flow` có ngưỡng `FINE` nên chấp nhận FINE và WARNING, nhưng bỏ FINEST ngay từ đầu.
2. `StreamHandler` được đặt `FINE` nên chấp nhận cả hai `LogRecord` còn lại. Nếu handler đặt `INFO`, dòng FINE sẽ bị Handler bỏ.
3. `formatter.formatMessage(record)` xử lý placeholder `{0}` để được `attempt=2`.
4. `setUseParentHandlers(false)` ngăn các Handler của parent/root in trùng.
5. `StreamHandler` có thể buffer output, nên ví dụ gọi `flush()` để bảo đảm quan sát hai dòng trước khi chương trình kết thúc. `close()` của StreamHandler sẽ đóng underlying stream; không nên tùy tiện đóng `System.out` khi ứng dụng vẫn tiếp tục dùng nó.

**Lưu ý khi đưa vào ứng dụng:** không đặt cấu hình Handler trong mỗi request; khởi tạo logging tập trung một lần, quản lý vòng đời Handler, và tránh race khi nhiều thread cùng sửa level/handler. Chương trình trên minh họa cơ chế, không phải cấu hình production hoàn chỉnh.

## 6. Cấu hình bên ngoài bằng `logging.properties`

### 6.1. File cấu hình được nạp ra sao?

JUL dùng `LogManager` toàn cục. Cấu hình mặc định phụ thuộc runtime; có thể chỉ định file properties khi khởi động JVM:

```bash
java -Djava.util.logging.config.file=logging.properties \
     -cp . JulConfigDemo
```

`-Djava.util.logging.config.file=...` là **system property của JVM**, phải được truyền ở phần option trước tên main class. Nếu dùng đường dẫn tương đối, hãy chắc chắn working directory của service đúng như dự kiến. Trong deployment, đường dẫn tuyệt đối ổn định thường dễ kiểm toán hơn. `java.util.logging.config.class` là cơ chế khác để cung cấp lớp cấu hình; kiểm tra các startup flags thực khi file được chỉ định dường như không có hiệu lực.

Không nên nhầm `logging.properties` của JUL với `logback.xml`, `log4j2.xml` hoặc các property logging riêng của framework. Một ứng dụng có thể dùng facade hoặc bridge làm hành vi khác JUL thuần.

### 6.2. Ví dụ properties nhỏ và chương trình tương ứng

Tạo file **`logging.properties`** với nội dung:

```properties
# Handler của root logger.
handlers = java.util.logging.ConsoleHandler

# Ngưỡng chung.
.level = INFO

# Ngưỡng và định dạng của console; ConsoleHandler viết ra stderr.
java.util.logging.ConsoleHandler.level = FINE
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter

# Định dạng rút gọn để demo, không in timestamp.
java.util.logging.SimpleFormatter.format = %4$s: %5$s%6$s%n

# Chỉ tăng chi tiết cho logger mục tiêu.
training.jul.config.level = FINE
```

Lưu file **`JulConfigDemo.java`**:

```java
import java.util.logging.Logger;

public class JulConfigDemo {
    private static final Logger LOG =
            Logger.getLogger("training.jul.config");

    public static void main(String[] args) {
        LOG.fine("cache miss");
        LOG.info("service started");
        LOG.finest("not emitted");
    }
}
```

Biên dịch, chạy (Linux/macOS):

```bash
javac JulConfigDemo.java
java -Djava.util.logging.config.file=logging.properties \
     -cp . JulConfigDemo
```

Trong môi trường JDK 17 thuần, không có cấu hình logging khác ghi đè, **stderr** có các dòng:

```text
FINE: cache miss
INFO: service started
```

Không có dòng FINEST vì Logger mục tiêu ở FINE. Cả root handler và `ConsoleHandler` phải cho phép FINE để dòng chi tiết hiển thị; ví dụ đặt `.level=INFO` nhưng child có `training.jul.config.level=FINE` và handler có `ConsoleHandler.level=FINE`. Việc truyền tiếp đến root handler không xét lại root Logger level như một lần ghi độc lập.

Các ký hiệu `%4$s` và `%5$s` trong `SimpleFormatter.format` lần lượt chọn Level và message đã định dạng; `%6$s` chọn biểu diễn exception nếu có; `%n` là ký tự xuống dòng. Đây là cú pháp `java.util.Formatter` cho **format của record**, khác `{0}` của tham số message. Trên môi trường có system property `java.util.logging.SimpleFormatter.format` đặt sẵn, giá trị system property có thể ưu tiên hơn giá trị trong config file; cần xem startup args nếu output khác dự kiến.

### 6.3. Các khóa cấu hình cốt lõi

| Khóa trong properties | Tác dụng | Sai lầm phổ biến |
| --- | --- | --- |
| `handlers=...` | Danh sách Handler gắn lên root Logger | Nhầm thành danh sách tất cả Logger |
| `.level=INFO` | Level root logger | Nghĩ mức này luôn chặn record đã phát từ child có level thấp hơn |
| `com.example.level=FINE` | Level logger theo tên `com.example` và quan hệ kế thừa | Đặt tên không trùng Logger trong code |
| `com.example.handlers=...` | Handler riêng của logger được nêu | Quên kiểm tra `useParentHandlers`, dẫn tới trùng |
| `com.example.useParentHandlers=false` | Không chuyển record lên các Handler của parent | Không gắn Handler riêng, khiến log biến mất |
| `java.util.logging.ConsoleHandler.level=FINE` | Ngưỡng ConsoleHandler | Chỉ thay Logger level nên vẫn không thấy FINE |
| `java.util.logging.ConsoleHandler.formatter=...` | Chọn class Formatter | Class không được load hoặc không có constructor phù hợp |
| `java.util.logging.SimpleFormatter.format=...` | Điều khiển biểu diễn text của SimpleFormatter | Nhầm `%4$s` với placeholder message `{0}` |
| `java.util.logging.FileHandler.pattern=...` | Chỉ định file pattern | Đặt path không có quyền hoặc thư mục chưa tồn tại |

Các tên class Handler phải đúng và có thể được tạo bởi LogManager theo cách phù hợp. Mọi khóa, đường dẫn, level và handler class cần đọc trong **file đã deploy** chứ không chỉ trong bản local.

### 6.4. Vì sao cập nhật file không đổi ngay log của JVM đang chạy?

JUL thường đọc cấu hình khi LogManager được khởi tạo; sửa file trên đĩa không mặc nhiên làm Logger đang chạy tự cập nhật. Có thể đổi chương trình qua `Logger.setLevel`/`Handler.setLevel`, hoặc cơ chế quản trị tương ứng. `LogManager.readConfiguration(...)` đọc lại cấu hình, có thể reset/recreate Handler và thay đổi global logging state; không nên gọi trong một request để “load lại nhanh” nếu chưa hiểu tác động lên toàn ứng dụng và framework.

JDK còn cung cấp `LogManager.updateConfiguration(...)` cho cập nhật có cơ chế gộp; hành vi chi tiết phụ thuộc API và các property, không tương đương thay một level đơn giản. Trong production hãy dùng cơ chế cấu hình đã có, giới hạn phạm vi và ghi lại cách trả về mức trước đó.

## 7. Handler: nơi xuất bản ghi và quản lý vòng đời

### 7.1. Các Handler có sẵn

| Handler | Đích/đặc tính | Khi hữu ích |
| --- | --- | --- |
| `ConsoleHandler` | Xuất ra **`System.err`**, mặc định dùng `SimpleFormatter` và ngưỡng INFO | Ứng dụng container gom stdout/stderr và xử lý tập trung |
| `FileHandler` | Viết file, hỗ trợ quay vòng theo kích thước/số lượng | Khi cần file độc lập, có quy trình rotation/retention |
| `StreamHandler` | Viết ra `OutputStream`; cần chú ý flush/close | Test có output kiểm soát hoặc adapter |
| `MemoryHandler` | Đệm một số bản ghi, đẩy khi đạt ngưỡng kích hoạt | Điều tra tình huống chỉ muốn giữ cửa sổ trước lỗi |
| `SocketHandler` | Truyền records qua mạng theo định dạng cấu hình | Chỉ khi chi phí/kết nối/truyền dữ liệu được kiểm soát |
| Custom `Handler` | Tùy biến đích, filtering/buffering | Khi chuẩn có sẵn không đáp ứng observability contract |

Không phải mọi Handler đều bất đồng bộ; gọi log có thể đi qua formatting và I/O trên thread phát log. Thiết kế Handler chậm hoặc đích I/O lỗi có thể kéo dài latency hay gây mất dữ liệu. Cần hiểu buffering, flush, error reporting, các giới hạn của collector.

### 7.2. FileHandler, rotation và tên file

`FileHandler` có các property hay dùng:

```properties
handlers = java.util.logging.FileHandler
.level = INFO

java.util.logging.FileHandler.level = INFO
java.util.logging.FileHandler.formatter = java.util.logging.SimpleFormatter
java.util.logging.FileHandler.pattern = %t/checkout-%u-%g.log
java.util.logging.FileHandler.limit = 1048576
java.util.logging.FileHandler.count = 3
java.util.logging.FileHandler.append = true
```

`%t` là thư mục tạm hệ thống, `%u` là phần số giúp phân biệt khi có xung đột file, `%g` là generation để quay vòng. Ví dụ đặt giới hạn khoảng 1 MiB mỗi file và quay vòng 3 file; giới hạn là **xấp xỉ** theo thời điểm ghi. Đây là cấu hình học tập: thư mục tạm không mặc định là nơi lưu log bền vững hoặc bảo mật. Không giả định `count=3` là chính sách retention đủ cho production.

Một vài điều quan trọng:

- `FileHandler` mặc định có thể dùng `XMLFormatter`; khi mong text dễ đọc phải chọn formatter cụ thể.
- `append=false` có nguy cơ thay đổi/xóa nội dung file hiện có theo chính sách open/rotation; xem startup behavior.
- Nếu nhiều JVM cùng ghi file hoặc chạy trên network filesystem, cơ chế `%u`/file locking không phải đảm bảo phối hợp ghi log hoàn chỉnh trong mọi môi trường.
- Cần kiểm tra quyền ghi, quota disk, rotation do hệ điều hành/collector, container ephemeral storage và thời hạn giữ.
- Lỗi không ghi được file có thể chỉ được báo bằng `ErrorManager` hoặc stderr tùy Handler; thiếu file không luôn có nghĩa ứng dụng chưa phát event.

Trong container, thông lệ thường là **mỗi ứng dụng gửi log phù hợp ra stdout/stderr để collector thu**, thay vì tự tạo nhiều file trên filesystem tạm. Tuy nhiên lựa chọn cụ thể tùy hệ thống vận hành và yêu cầu bảo mật.

### 7.3. Gắn và tháo Handler

Các thao tác:

```java
Logger logger = Logger.getLogger("com.example.checkout");
Handler[] ownHandlers = logger.getHandlers();

for (Handler handler : ownHandlers) {
    logger.removeHandler(handler);
    handler.flush();
    // handler.close() nếu đây là Handler ứng dụng sở hữu
    // và được phép đóng theo lifecycle phù hợp.
}
```

`getHandlers()` trả các Handler **gắn trực tiếp** vào Logger này, không nhất thiết gồm Handler được kế thừa qua parent. Đừng vội đóng Handler dùng chung nếu không biết ownership. Với `StreamHandler` giữ `System.out`, `close()` có thể đóng cả output stream; ngược lại, Handler file cần được close để giải phóng tài nguyên khi shutdown. Thay Handler lúc runtime có thể gây mất hoặc lặp records trong một khoảng chuyển đổi nếu không phối hợp đúng.

## 8. Formatter và định dạng có ích cho chẩn đoán

### 8.1. SimpleFormatter và XMLFormatter

`SimpleFormatter` tạo chuỗi thân thiện với người đọc. Nó có thể chứa timestamp, caller, level, message và throwable; format mặc định không nên được hard-code như tiêu chuẩn bất biến giữa mọi cấu hình JDK.

`XMLFormatter` tạo biểu diễn XML cho records; định dạng cấu trúc hữu ích khi phù hợp pipeline, nhưng không đương nhiên tối ưu cho hệ thống log aggregation hiện đại. Nếu muốn JSON/structured logs, phải có formatter/bridge/adapter đúng, kiểm chứng escaping và schema; JUL trong JDK 17 không cung cấp sẵn một JSONFormatter chuẩn tương đương chỉ bằng đổi một thuộc tính.

### 8.2. Timestamp cần mốc, múi giờ và timezone rõ ràng

Trong Java 17, `LogRecord.getInstant()` cho thời điểm event. Formatter tùy chỉnh có thể xuất UTC:

```java
// Snippet bên trong một Formatter tùy chỉnh.
String timestampUtc =
        java.time.format.DateTimeFormatter.ISO_INSTANT
                .format(record.getInstant());
```

Cần đặt biến `record` là `LogRecord` trong method formatter, không chạy độc lập. Nếu dùng `SimpleFormatter` với `%1$...`, ngày/giờ được trình bày theo `ZoneId.systemDefault()` của JVM cho trường date. Hai pod có timezone khác nhau có thể hiển thị cùng instant thành chuỗi khác nhau. Dùng timestamp có offset/UTC và kèm instance/trace ID sẽ giúp ghép với GC/JFR/traces chính xác hơn.

**Precision khác accuracy:** in nanoseconds không bảo đảm clock node được đồng bộ nano giây. Khi so log từ nhiều host, đánh giá clock skew/ingestion delay, đặc biệt nếu suy luận thứ tự ở mức mili giây.

### 8.3. Formatter tùy chỉnh phải xử lý Throwable, escaping và output

Nếu định dạng text đơn giản như ví dụ `JulFlowDemo` chỉ dùng `formatMessage(record)`, nó sẽ không tự in stack trace cho `LogRecord.getThrown()`. Với production, Formatter nên:

- xử lý `record.getThrown()`, cause chain và stack trace theo chính sách;
- escape newline, dấu phân cách, dữ liệu đầu vào để tránh log injection và lỗi parsing;
- ghi timestamp UTC, level, logger, thread/request/trace ID khi thật sự có dữ liệu;
- giới hạn payload và che dữ liệu nhạy cảm, không cắt bỏ ngẫu nhiên thông điệp lỗi cốt lõi;
- tính đến định dạng thời gian và encoding (UTF-8 nếu pipeline yêu cầu);
- đồng bộ hóa/hiệu năng phù hợp cách Handler gọi formatter.

Nếu có structured logging, nên tách fields metadata khỏi message text để downstream không phải parse từng chuỗi bằng regex mong manh.

## 9. Quan sát và đổi mức ghi trên tiến trình đang chạy

### 9.1. Xác định JUL có thực sự được dùng không

Trước khi chỉnh `logging.properties`, xác minh log đang đi theo JUL hay qua SLF4J/Logback/Log4j2/container adapter. Một số ứng dụng có cầu nối JUL → SLF4J hoặc bridge khác; khi đó Handler và level cuối có thể chịu quản lý bởi framework đích. Không cài các bridge hai chiều tùy tiện vì có thể tạo loop, duplicate hoặc xung đột quản lý.

Đọc **launch args thật**, system property `java.util.logging.config.file` (nếu có), file config trong image/mount và các log framework đã deploy. `-Xlog:gc*` là **JVM Unified Logging** của HotSpot, độc lập với JUL `Logger` của code ứng dụng: thay JUL `FINE` không tự bật GC logs và ngược lại.

### 9.2. Quan sát cấu hình trong code

Một đoạn code chẩn đoán có thể in tên, level được đặt, useParentHandlers và Handler trực tiếp:

```java
Logger log = Logger.getLogger("com.example.checkout");
System.out.println("name=" + log.getName());
System.out.println("setLevel=" + log.getLevel());
System.out.println("parent=" +
        (log.getParent() == null ? "<none>" : log.getParent().getName()));
System.out.println("toParent=" + log.getUseParentHandlers());

for (java.util.logging.Handler h : log.getHandlers()) {
    System.out.println("handler=" + h.getClass().getName()
            + " level=" + h.getLevel());
}
```

Đây là **snippet đặt trong method**, không phải file đầy đủ. Nó chỉ liệt kê Handler **own**, chưa gồm tất cả Handler ở parent; `getLevel()` có thể null nhưng effective level vẫn xác định. Nếu một Logger đã bị framework/bridge thay Handler sau startup, chỉ đọc file `logging.properties` ban đầu sẽ không phản ánh toàn bộ trạng thái runtime.

Trên Java 17, có thể dùng `java.lang.management.PlatformLoggingMXBean` qua Java Management API để xem hoặc thay level của JUL loggers theo quyền và khả năng kết nối. Nó không phải giao diện sửa mọi Handler/filter. API `java.util.logging.LoggingMXBean` cũ đã deprecated; ưu tiên interface platform phù hợp phiên bản JDK.

### 9.3. Quy trình tăng mức chẩn đoán an toàn

1. **Chọn Logger hẹp** theo package/class có liên quan lỗi, ví dụ `com.example.checkout.PaymentGateway`; không nâng root toàn JVM nếu không cần.
2. **Ghi baseline:** effective level đang có, parent chain, Handler levels, log rate/giây, latency và disk/network budget.
3. **Xác định đích ghi thực:** ConsoleHandler, file, framework bridge hoặc collector; kiểm tra cả ngưỡng Handler, không chỉ Logger.
4. **Tăng tạm thời** từ INFO lên FINE (chỉ khi cần), trong một cửa sổ đã định và với khả năng quay lại mức cũ.
5. **Quan sát tín hiệu:** lượng logs tăng, CPU/GC, latency, I/O, disk quota, lỗi ghi logs; dừng nếu ảnh hưởng cao.
6. **Thu bản ghi có context:** timestamp UTC, instance, request/trace ID, phiên bản ứng dụng, mốc lỗi.
7. **Khôi phục và xác minh:** trả level/handler về baseline; xác nhận log rate và hiệu năng trở lại trạng thái thường.
8. **Lưu kết luận:** event nào đã phân biệt giả thuyết; ai xem được logs; thời hạn giữ dữ liệu.

Đừng bật `FINEST` trên toàn cluster vô thời hạn. Nếu lỗi chỉ xuất hiện rất hiếm, có thể chọn sampling/log theo request ID bằng cách ứng dụng cho phép, nhưng phải có thiết kế bảo mật và bảo đảm không bỏ lỡ bằng chứng quan trọng.

### 9.4. Tác động của việc reload cấu hình

Cập nhật live qua `Logger.setLevel` có phạm vi hẹp; đổi `Handler.setLevel` ảnh hưởng tất cả Logger cùng chia Handler đó. `LogManager.readConfiguration` có thể reset và đóng các Handler trước đó, phá cấu hình chương trình hoặc làm gián đoạn output nếu dùng tùy tiện. `LogManager.updateConfiguration` có hành vi merge/replace theo quy tắc API, cần kiểm thử với provider/handler cụ thể.

Không đánh đồng “config file đã sửa” với “JVM đã nhận config”. Khi xảy ra mất log ngay sau deploy, kiểm tra điều gì nạp cấu hình, thời điểm khởi tạo LogManager và output của ứng dụng lúc startup.

## 10. Ma trận xử lý sự cố với JUL

| Triệu chứng | Giả thuyết cần kiểm tra | Bằng chứng/việc kiểm tra |
| --- | --- | --- |
| `logger.fine(...)` không hiện | Logger effective level cao hơn FINE | `getLevel()`, parent chain, `isLoggable(FINE)` |
| `isLoggable(FINE)` true nhưng không có dòng FINE | Handler level/filter loại record; không có Handler tới sink | `getHandlers()`, Handler parent, `getUseParentHandlers()`, filter/collector |
| Một event xuất hai lần | Own Handler và parent Handler cùng ghi; hoặc collector đọc 2 nguồn | Cấu hình handlers, `useParentHandlers`, log path và collector pipeline |
| Không có log nào từ một package | Logger name khác property; `useParentHandlers=false` nhưng không có own Handler | So tên Logger trong code và file; inspect handler graph |
| Level đổi nhưng không thấy tác dụng | Chỉ đổi file, chưa reload; framework bridge; handler level cao | Startup arguments và trạng thái runtime, bridge, Handler hiện tại |
| INFO in stderr, không in stdout | `ConsoleHandler` viết `System.err` | Kiểm tra stdout/stderr collector, không giả định console = stdout |
| Có exception message nhưng thiếu stack trace | Đã log bằng `ex.getMessage()` hoặc Formatter bỏ `getThrown()` | API overload `log(..., ex)`, Formatter source/schema |
| FileHandler không tạo file | Path/permission/quota, directory chưa tồn tại, file locks | `pattern`, user/cwd, ErrorManager, filesystem |
| File chuyển tên khi đầy | Rotation theo `limit/count/%g/%u` | FileHandler properties, actual file names, retention |
| Timestamp lệch giờ khi ghép JFR/GC | Formatter dùng timezone host khác; ingest timestamp bị nhầm | `LogRecord.getInstant()`, timezone, event vs observed time |
| Lỗi chậm hơn sau khi bật FINEST | Nhiều log, format tốn CPU hoặc I/O blocking | Log rate, latency, CPU/disk, Handler implementation |
| Message có `{0}` chưa thay | Formatter không gọi `formatMessage`; record không có parameters | Cách gọi `log(...)`, Formatter method |
| Log giữa nhiều request bị trộn context | Tự dùng ThreadLocal nhưng task chạy bất đồng bộ | Request/trace ID propagation, lifecycle context, thread pools |
| JUL config không điều khiển log framework | Ứng dụng dùng Logback/Log4j2/bridge | Xác minh logging backend/bridges, configuration owner |

**Nguyên tắc chẩn đoán:** trước hết xác minh event có được tạo ở Logger không; sau đó lần theo *đường đi tới Handler cuối*; cuối cùng kiểm tra Formatter, I/O và collector. Cách này tránh việc liên tục hạ level mà không biết bản ghi đang bị loại ở đâu.

## 11. Chất lượng log cho điều tra sự cố JVM

### 11.1. Ghi thông tin đủ để tái hiện diễn tiến

Một bản ghi hữu ích cho incident thường cần:

- event timestamp có offset rõ (ưu tiên UTC), level, logger/service và instance;
- operation hoặc event code ổn định, tình trạng thành công/thất bại;
- request/trace/span ID khi có và được phép thu;
- object identifier đã làm sạch, duration và đơn vị nếu cần;
- exception type, cause, stack trace khi xảy ra lỗi thật;
- build version, deployment revision, JVM instance/host khi ghép nhiều nguồn.

Không phải thông tin nào cũng in trực tiếp trong `message`; nếu có schema structured log, các trường nên tách riêng. `LogRecord` vốn có level/message/time/thrown nhưng application context bổ sung phải được lập trình và kiểm thử.

### 11.2. Log level không thay thế metric hoặc tracing

- `INFO` giúp biết lifecycle và event quan trọng, nhưng không đo chính xác tỷ lệ lỗi hoặc p99.
- `FINE` giúp thấy đường xử lý, nhưng để biết CPU hotspot có thể cần JFR/profiler và để biết GC pause có thể cần JFR/GC logs.
- Nhiều dòng log có thể làm thêm I/O và làm nhiễu timing; không suy ra “thời điểm xảy ra” chỉ từ thứ tự collector nhận records.
- Nếu cần đo lượng request, metric counter có cấu trúc và label cardinality được kiểm soát thường thích hợp hơn ghi từng request vào log chi tiết.

### 11.3. Dữ liệu nhạy cảm, injection và retention

Không log plaintext password, API key, access token, session cookie, số thẻ, payload nhạy cảm hoặc toàn bộ `System.getProperties()`. Đối với exception, stack trace có thể vô tình mang path/hostname/query/parameter: giới hạn truy cập log và chính sách retention tương ứng.

Đầu vào người dùng chứa newline hoặc dấu phân cách có thể **giả mạo một dòng log khác** khi được nối thẳng vào plain text; Formatter/encoder phải escape phù hợp hoặc dùng structured fields. Kể cả khi chỉ bật FINE tạm thời, dữ liệu vẫn có thể được lưu lâu ở collector và backup.

## 12. Bài thực hành chẩn đoán hai lớp level

Từ ví dụ `JulFlowDemo`, sửa lần lượt và dự đoán output:

| Thay đổi | Dòng FINE có tới stdout? | Lý do |
| --- | --- | --- |
| Giữ Logger FINE, Handler FINE | Có | Cả hai ngưỡng cho qua |
| Đổi Logger INFO, giữ Handler FINE | Không | Logger bỏ trước khi tạo LogRecord FINE |
| Đổi Logger FINE, Handler INFO | Không | Handler bỏ sau khi Logger tạo LogRecord |
| Đổi cả Logger và Handler FINEST | Có; thêm dòng FINEST | Cả hai đều nhận FINEST |
| Gọi `setUseParentHandlers(true)` trong chương trình demo | Có thể thêm bản ghi ở Handler của parent | Phụ thuộc root config, có nguy cơ trùng output |

Với một ứng dụng thực, nếu thấy `isLoggable(FINE)` là true nhưng console không hiện FINE, hãy kiểm tra Handler level **trước khi** đổi thêm cấp Logger. Nếu FINE vẫn không tới collector dù cả hai ngưỡng cho qua, kiểm tra Filter, Handler presence, stream direction, output errors và pipeline collector.

## 13. Các sai lầm thường gặp

1. **Chỉ sửa Logger level và quên Handler level.** ConsoleHandler mặc định INFO có thể bỏ FINE.
2. **Hiểu `getLevel()==null` là không cấu hình.** Đó có thể là mức kế thừa từ parent.
3. **Gắn ConsoleHandler cho mọi class.** Dễ tạo log trùng vì còn parent handlers.
4. **Đặt `useParentHandlers=false` nhưng không gắn Handler riêng.** Dòng log có thể biến mất.
5. **Dùng `System.out.println` thay logging có cấu trúc.** Mất level, logger name, cấu hình và routing (dù println có thể hữu ích trong debug ngắn).
6. **Ghi exception chỉ bằng message.** Mất Throwable/stack trace và nguyên nhân sâu.
7. **Đưa `String.format`/nối chuỗi đắt tiền vào lệnh FINE bị tắt.** Tạo overhead không cần thiết.
8. **Cho rằng `ConsoleHandler` xuất stdout.** Nó xuất `System.err`.
9. **Dùng `%s` trong message có tham số JUL mà mong Formatter thay như SLF4J.** JUL thường dùng `{0}` với `MessageFormat`.
10. **Không biết cấu hình thực được nạp từ file nào.** File trong repo có thể không phải file được JVM dùng.
11. **Nhầm JUL với JVM `-Xlog` hoặc backend logging khác.** Sửa nhầm hệ thống không có hiệu quả.
12. **Bật FINEST mọi nơi khi có sự cố.** Có thể gây I/O, tăng log cardinality và thêm chi phí.
13. **Không flush/close đúng vòng đời Handler.** Có thể mất dữ liệu cuối phiên hoặc rò file descriptor.
14. **Custom Formatter bỏ Throwable và timestamp.** Khi incident xảy ra lại thiếu bằng chứng.
15. **Log dữ liệu nhạy cảm và không có giới hạn retention.** Mức ghi “debug” không phải ngoại lệ của chính sách bảo vệ dữ liệu.
16. **Không khôi phục mức cũ sau điều tra.** Log volume và rủi ro tăng lâu dài.

## 14. Checklist cấu hình trước production hoặc khi xử lý incident

- [ ] Có Logger đặt tên nhất quán theo package/class và giữ tham chiếu mạnh?
- [ ] Hiểu effective Logger level, level được chỉ định và quan hệ kế thừa?
- [ ] Đã kiểm tra level + Filter của từng Handler cùng parent handlers?
- [ ] Có chủ ý về `useParentHandlers`, tránh log trùng hoặc mất log?
- [ ] Đã xác nhận nguồn `logging.properties`, JVM `-D` và backend logging thực tế?
- [ ] Đã xác định destination `stderr`, stdout, file hay collector?
- [ ] Formatter có UTC/offset phù hợp, level, logger name, message và Throwable?
- [ ] Với FileHandler, đã dự trù path, rotation, quota, permission và retention?
- [ ] Đã tránh log payload bí mật, xử lý injection/escaping và quyền đọc?
- [ ] Có kế hoạch bật FINE/FINER/FINEST hẹp, có thời hạn và ngưỡng dừng?
- [ ] Có cách khôi phục level/handler và xác minh khôi phục thành công?
- [ ] Đã ghép log với metrics, JFR, GC log hoặc traces khi cần phân tích nguyên nhân?

**Câu hỏi tự kiểm tra:** ứng dụng có Logger `com.example.checkout` đặt `FINE`, ConsoleHandler ở root đặt `INFO` và `useParentHandlers=true`. Tại sao `logger.isLoggable(Level.FINE)` trả `true` nhưng FINE không xuất? Có hai cách khắc phục nào chỉ ảnh hưởng phạm vi cần thiết? Hãy giải thích rõ đường đi của `LogRecord`, hệ quả nếu thêm Handler riêng và cách tránh trùng dòng.

## Tài liệu tham khảo

- Oracle Java SE 17, [`java.util.logging` package](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/package-summary.html): kiến trúc và các thành phần JUL.
- Oracle Java SE 17, [`Logger` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): mức hiệu lực, hierarchy, parent handlers, Supplier, parameters và Throwable.
- Oracle Java SE 17, [`Level` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Level.html): thứ tự, giá trị và mức OFF/ALL.
- Oracle Java SE 17, [`Handler` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html) và [`ConsoleHandler`](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/ConsoleHandler.html): ngưỡng, Filter và `System.err`.
- Oracle Java SE 17, [`Formatter` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Formatter.html), [`SimpleFormatter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/SimpleFormatter.html): formatting và `formatMessage`.
- Oracle Java SE 17, [`FileHandler` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html): `pattern`, `limit`, `count`, `append`, `%u` và `%g`.
- Oracle Java SE 17, [`LogManager` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogManager.html): `logging.properties`, cấu hình startup và cập nhật runtime.
- Oracle Java SE 17, [`LogRecord` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html): dữ liệu sự kiện, thời điểm và Throwable.

Một cấu hình JUL đáng tin cậy cho chẩn đoán phải trả lời được **bản ghi sinh ở Logger nào → đi qua ngưỡng và Filter nào → tới Handler nào → được Formatter trình bày ra sao → collector có thực sự nhận được không**. Khi biết chính xác từng bước, bạn có thể tăng độ chi tiết đủ để tìm lỗi mà không làm nhiễu, làm mất hoặc nhân đôi bằng chứng.