# Log ra stdout trong Java Core Logging

## 1. stdout là gì và tại sao dùng nó để ghi log?

Mỗi tiến trình Java thông thường có ba **standard streams** do môi trường chạy cung cấp:

| Luồng | Tên Java | Mục đích điển hình |
| --- | --- | --- |
| **Standard input** | `System.in` | Nhận dữ liệu đầu vào, nếu chương trình có dùng |
| **Standard output (stdout)** | `System.out` | Xuất kết quả hoặc thông tin mà tiến trình muốn công bố |
| **Standard error (stderr)** | `System.err` | Xuất chẩn đoán, cảnh báo và lỗi theo quy ước CLI |

**Log ra stdout** nghĩa là dữ liệu logging được ghi vào **luồng standard output của tiến trình**, thay vì mặc định ghi tệp hoặc stderr. Trên terminal, stdout và stderr thường xuất hiện cùng một cửa sổ, nên **nhìn thấy dòng log trên màn hình chưa chứng minh đó là stdout**.

Ví dụ:

```java
System.out.println("RESULT order_id=ORD-101");
System.err.println("DIAGNOSTIC gateway unavailable");
```

Đây là **hai câu lệnh minh họa**, không phải chương trình Java đầy đủ. Câu đầu viết lên stdout, câu sau viết lên stderr. Hệ điều hành, shell, container runtime hoặc process manager có thể **chuyển hướng** mỗi luồng sang file hoặc collector độc lập với code Java.

Khi muốn logging ra stdout, ta vẫn cần phân biệt:

1. **Sự kiện log**: level, message, tên logger, exception, mã tương quan.
2. **Formatter/Layout/Encoder**: cách biểu diễn sự kiện thành chuỗi văn bản hoặc JSON.
3. **Handler/Appender**: nơi và cách viết chuỗi/byte, ở đây là stdout.
4. **Đường thu thập**: terminal, Docker/Kubernetes, systemd, CI hoặc log collector nhận dữ liệu sau khi tiến trình ghi.

**Ghi stdout không có nghĩa log đã được lưu bền hoặc đã đến dashboard.** Nó chỉ xác định một điểm xuất của tiến trình. Việc thu thập, lập chỉ mục, phân quyền, rotation và retention thuộc hạ tầng sau đó.

## 2. Luồng thực tế từ Java đến hệ thống log

```text
Ứng dụng Java
    |
    +-- logger.info("event=...")
    |          |
    |          v
    |    Logger / LogEvent
    |          |
    |          v
    |    Level / Filter
    |          |
    |          v
    |    Formatter / Layout
    |          |
    |          v
    |    Console Handler/Appender -> stdout
    |                                  |
    +-- System.out.println(...) -------+
                                       |
                                       v
                              OS standard output
                                       |
                      +----------------+---------------+
                      |                |               |
                      v                v               v
                   Terminal       Redirect file    Container runtime
                                                        |
                                                        v
                                                  Log agent/collector
                                                        |
                                                        v
                                                Search / retention
```

Điểm quan trọng: **stdout không phải là “đích lưu log” cuối cùng trong mọi kiến trúc**. Khi chạy ở một máy chủ trực tiếp, stdout có thể xuất hiện trong terminal hoặc được shell chuyển vào tệp. Khi chạy trong container, runtime có thể thu stdout và chuyển tới logging driver/agent. Khi chạy trong CI, job runner thường thu đầu ra để hiển thị và lưu theo chính sách.

Do đó một cấu hình “ghi console stdout” chỉ giải quyết **đầu ra của ứng dụng**. Muốn có khả năng giám sát, phải kiểm tra toàn bộ đường thu, đặc biệt là nơi lưu, thời gian giữ, bộ lọc và quyền truy cập.

## 3. stdout khác stderr ra sao?

Về API Java, cả `System.out` và `System.err` là `java.io.PrintStream`. Chúng là hai luồng riêng; việc một luồng được nối tới đâu phụ thuộc tiến trình được khởi chạy như thế nào.

| Khía cạnh | stdout | stderr |
| --- | --- | --- |
| API mặc định của JDK | `System.out` | `System.err` |
| Quy ước command-line | Kết quả máy/người dùng cần đọc | Chẩn đoán, thông báo lỗi |
| Chuyển hướng trên shell POSIX | `> file` hoặc `1> file` | `2> file` |
| Dòng log có cấp ERROR có bắt buộc nằm ở đây không? | **Không**: có thể ghi cả INFO, WARN, ERROR nếu appender chọn stdout | **Không**: không phải tất cả lỗi đều phải ghi vào stderr |
| Tác động khi terminal hiển thị cùng nhau | Dễ nhầm stdout với stderr | Dễ nhầm stderr với stdout |

**Level khác luồng.** `ERROR` là cấp độ của LogEvent. `stdout` là một đích I/O. Nếu một Console Appender được cấu hình `SYSTEM_OUT`, cả `INFO` và `ERROR` có thể đi vào stdout. Việc level cao hơn không tự chuyển output sang stderr, trừ khi cấu hình backend có cơ chế định tuyến theo level.

Đối với một **CLI dùng stdout để trả dữ liệu mà công cụ khác sẽ parse**, cách tốt thường là giữ **stdout sạch** cho dữ liệu/đáp án và ghi chẩn đoán sang stderr, hoặc lưu log ở kênh khác. Ví dụ CLI trả JSON ra stdout nhưng đồng thời log text vào stdout có thể làm:

```text
INFO Started processing
{"orderId":"ORD-101","status":"OK"}
```

Dữ liệu đó **không còn là một tài liệu JSON duy nhất hợp lệ** cho công cụ đọc stdout. Vậy nên “log ra stdout” phù hợp hay không phụ thuộc **hợp đồng của tiến trình**:

- Một dịch vụ nền/container có log collector đọc stdout: thường phù hợp.
- Một CLI trả dữ liệu máy đọc qua pipe: cần tách log khỏi stdout của kết quả.
- Một chương trình giáo dục chạy terminal: có thể dùng stdout để quan sát đơn giản.

## 4. Cách trực tiếp nhất: `System.out.println`

Java cho phép in ra stdout mà không cần thư viện logging:

```java
public final class PrintlnDemo {
    private PrintlnDemo() {
    }

    public static void main(String[] args) {
        System.out.println("event=application_started");
        System.out.println("event=order_created order_id=ORD-101");
    }
}
```

Lưu thành `PrintlnDemo.java` rồi chạy:

```bash
javac -encoding UTF-8 PrintlnDemo.java
java PrintlnDemo
```

**Stdout chính xác:**

```text
event=application_started
event=order_created order_id=ORD-101
```

**Stderr của ứng dụng:** không có dòng nào trong điều kiện chạy bình thường.

### Vì sao `println` chưa đủ cho logging nghiêm túc?

`System.out.println` chỉ ghi một chuỗi và xuống dòng. Nó **không tự** đưa vào những chức năng thường cần của hệ thống logging:

- Lọc theo cấp `DEBUG`, `INFO`, `WARN`, `ERROR`.
- Logger name, timestamp, thread, correlation ID theo cấu hình chung.
- Cấu trúc sự kiện và tham số định dạng theo API logging.
- Hỗ trợ Throwable/cause/stack trace nhất quán.
- Appender/Handler, filter, formatter, định tuyến và chính sách đa đích.
- Điều khiển độ chi tiết qua cấu hình mà không sửa từng câu lệnh trong mã.

`println` vẫn phù hợp cho **đầu ra kết quả chương trình** và các bài minh họa nhỏ. Nhưng đối với sự kiện vận hành nên dùng logger của JUL, SLF4J với provider, Logback hoặc Log4j2; chọn stdout **ở lớp cấu hình đích ghi**, thay vì thay mọi lời gọi bằng `System.out.println`.

Không nên coi `System.out.println` là một cách tự động ghi “log có cấu trúc”. Nếu output chỉ là chuỗi `key=value`, collector có thể vẫn phải parse nó; JSON thật còn cần escaping và schema đúng.

## 5. java.util.logging (JUL): một bẫy quan trọng về stdout

**`java.util.logging.ConsoleHandler` của JDK mặc định ghi tới `System.err`, không phải `System.out`.** Tên `ConsoleHandler` nói đến console, không nói chắc stdout. Đây là nguyên nhân thường gặp khi người học nghĩ chương trình “đã log ra stdout” chỉ vì log xuất hiện trên terminal.

Ví dụ JUL:

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Level;
import java.util.logging.Logger;

public final class JulConsoleDemo {
    private JulConsoleDemo() {
    }

    public static void main(String[] args) {
        Logger log = Logger.getLogger("example.jul");
        log.setUseParentHandlers(false);
        log.setLevel(Level.INFO);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.INFO);
        log.addHandler(console);

        try {
            log.info("event=application_started");
        } finally {
            log.removeHandler(console);
            console.close();
        }
    }
}
```

Lưu `JulConsoleDemo.java`, biên dịch và chạy với JDK 17+:

```bash
javac -encoding UTF-8 JulConsoleDemo.java
java JulConsoleDemo
```

Dòng `event=application_started` được **ConsoleHandler gửi tới stderr**. Formatter mặc định có thể kèm thời gian, tên lớp/phương thức và mức log nên không khẳng định một chuỗi toàn dòng cố định. Chương trình không chủ động ghi gì ra stdout.

Có thể kiểm tra bằng cách chạy trong shell POSIX:

```bash
java JulConsoleDemo > stdout.log 2> stderr.log
```

Kỳ vọng: `stdout.log` rỗng; `stderr.log` chứa bản ghi JUL. `System.err` không đồng nghĩa chỉ dùng cho cấp `SEVERE`: `ConsoleHandler` có thể đưa cả `INFO` lên stderr.

**Không có cấu hình tiêu chuẩn trên `ConsoleHandler` để chỉ đổi đích từ stderr sang stdout bằng lời gọi `setTarget`.** Nếu muốn dùng JUL mà ghi stdout, hãy dùng một `Handler` khác có đích `System.out`, chẳng hạn `StreamHandler`, hoặc một handler tùy biến được quản lý đúng vòng đời.

## 6. Ví dụ Java 17+ đầy đủ: JUL ghi đúng stdout

`java.util.logging.StreamHandler` hỗ trợ khởi tạo với `OutputStream` tùy chọn. Nhờ đó ta có thể đặt `System.out` làm đích của một handler. Nhưng **StreamHandler có buffer** và `close()` của nó **đóng OutputStream được cung cấp**, nên ví dụ sẽ flush tường minh và **không đóng `System.out`**.

Lưu toàn bộ mã sau thành **`StdoutLoggingDemo.java`**:

```java
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class StdoutLoggingDemo {
    private static final Logger LOG =
            Logger.getLogger(StdoutLoggingDemo.class.getName());

    private StdoutLoggingDemo() {
    }

    public static void main(String[] args) throws Exception {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        Formatter formatter = new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        };

        StreamHandler stdout =
                new StreamHandler(System.out, formatter);
        stdout.setLevel(Level.INFO);
        stdout.setEncoding("UTF-8");
        LOG.addHandler(stdout);

        try {
            LOG.log(Level.INFO,
                    "event=order_created order_id={0}", "ORD-101");
            LOG.log(Level.WARNING,
                    "event=payment_retry order_id={0} attempt={1}",
                    new Object[] {"ORD-101", 2});

            stdout.flush();
        } finally {
            LOG.removeHandler(stdout);
            stdout.flush();
            // Không gọi stdout.close(): StreamHandler sẽ đóng System.out.
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 StdoutLoggingDemo.java
java StdoutLoggingDemo
```

**Stdout chính xác:**

```text
INFO event=order_created order_id=ORD-101
WARNING event=payment_retry order_id=ORD-101 attempt=2
```

**Stderr của ứng dụng:** không có bản ghi trong điều kiện chạy bình thường. Chương trình không gọi `System.err` và không gắn `ConsoleHandler`.

### Vì sao ví dụ thực sự ghi stdout?

1. `new StreamHandler(System.out, formatter)` liên kết handler với chuẩn đầu ra. Đây là khác biệt quyết định so với `new ConsoleHandler()`.
2. `LOG.setUseParentHandlers(false)` chặn việc một LogRecord tiếp tục lên handler cha, tránh những bản sao ngoài ý muốn trên stderr.
3. Logger và handler đều ở ngưỡng `INFO`; `INFO` và `WARNING` được chấp nhận.
4. `formatMessage(record)` định dạng tham số JUL dạng `{0}`, `{1}`. Đây là cú pháp của JUL/`MessageFormat`, **không phải `{}` của SLF4J hoặc Log4j2**.
5. Formatter tạo một dòng ổn định cho mỗi sự kiện, không in timestamp hoặc stack trace vì code minh họa không yêu cầu chúng.
6. `stdout.flush()` đẩy dữ liệu của `StreamHandler` ra luồng `System.out` để quan sát ngay. Không nên suy ra flush đồng nghĩa log đã được lưu bền trên đĩa hoặc collector đã nhận.
7. Sau ví dụ, handler được **gỡ khỏi logger** rồi flush. Không gọi `StreamHandler.close()` vì constructor đã nhận **stream dùng chung của toàn tiến trình**.

### Lưu ý về vòng đời

Ví dụ là một chương trình ngắn nên dùng cách đơn giản: **gỡ handler và flush, để stdout tiếp tục thuộc về tiến trình**. Trong dịch vụ chạy lâu, nơi quản lý logging phải thiết kế vòng đời cho handler và cấu hình một lần khi khởi động. Nếu muốn tạo một handler có thể `close` an toàn mà không đóng stdout, cần dùng wrapper `OutputStream` không đóng stream gốc hoặc handler tùy biến có chính sách close phù hợp.

Đừng thêm `StreamHandler(System.out, ...)` mỗi lần xử lý request: mỗi lần gắn sẽ tăng số handler và có thể sinh log trùng. Đừng tự đóng `System.out` trong một thư viện dùng chung, vì thành phần khác của ứng dụng còn có thể sử dụng luồng đó.

Đây là ví dụ JUL **thật sự chạy chỉ với JDK 17**, không yêu cầu Maven, SLF4J hay Log4j2.

## 7. Kiểm chứng bằng chuyển hướng stdout và stderr

Cách chắc chắn nhất để biết một log đang dùng luồng nào là **tách stdout và stderr ở môi trường chạy**.

### Shell Linux/macOS

```bash
javac -encoding UTF-8 StdoutLoggingDemo.java

java StdoutLoggingDemo > stdout.log 2> stderr.log
cat stdout.log
cat stderr.log
```

Với chương trình ở phần 6:

- `stdout.log` có **đúng hai dòng** đã nêu.
- `stderr.log` rỗng nếu không có cảnh báo/lỗi JVM hoặc môi trường.
- Kết quả từ `cat stdout.log` được in ra stdout của **lệnh cat**, không phải một lần chạy thứ hai của Java.

Một số mẫu shell thông dụng:

| Lệnh | Ý nghĩa |
| --- | --- |
| `java StdoutLoggingDemo > app.log` | Chỉ hướng stdout của tiến trình Java vào `app.log` |
| `java StdoutLoggingDemo 2> errors.log` | Chỉ hướng stderr vào `errors.log` |
| `java StdoutLoggingDemo > app.log 2> errors.log` | Tách hai luồng |
| `java StdoutLoggingDemo > combined.log 2>&1` | Hướng stdout vào file, sau đó hướng stderr về cùng đích |
| `java StdoutLoggingDemo 2>&1 | tee combined.log` | Gộp hai luồng vào pipe và hiển thị/lưu qua `tee` |
| `java StdoutLoggingDemo > /dev/null` | Bỏ output stdout ở môi trường POSIX |
| `java StdoutLoggingDemo 2> /dev/null` | Bỏ output stderr ở môi trường POSIX |

**Thứ tự redirection có ý nghĩa.** `> combined.log 2>&1` khác với `2>&1 > combined.log` khi xét nơi stderr cuối cùng được chuyển đến. Dấu `|` tạo pipe, và shell/OS quyết định cách các luồng được kết hợp.

### Windows

Trong **PowerShell** và **Command Prompt**, ký hiệu redirection có điểm giống nhau nhưng ngữ nghĩa pipeline, encoding và cách chuyển error stream có thể khác. Để kiểm chứng cơ bản với chương trình thuần Java trên Windows, có thể dùng:

```powershell
java StdoutLoggingDemo 1> stdout.log 2> stderr.log
Get-Content stdout.log
Get-Content stderr.log
```

Không khẳng định mọi bản PowerShell lưu byte với cùng encoding hoặc mọi lỗi Java đều là PowerShell error record. Với log có ký tự tiếng Việt, kiểm tra encoding toàn đường từ Java đến terminal/file/collector.

### Lỗi “log không thấy” dù chương trình chạy

Nếu chỉ dùng `java App > app.log` và ứng dụng dùng **JUL ConsoleHandler mặc định**, log có thể vẫn xuất hiện trên terminal vì nó ở **stderr**, không đi vào `app.log`. Đây là một lỗi kiểm tra rất phổ biến.

## 8. Log4j2: cấu hình ConsoleAppender tới stdout

Trong **Apache Log4j 2**, ConsoleAppender hỗ trợ chọn đích là `SYSTEM_OUT` hoặc `SYSTEM_ERR`. Đích mặc định của ConsoleAppender thông thường là **`SYSTEM_OUT`**, nhưng nên cấu hình **tường minh** để dễ hiểu và giảm nhầm lẫn.

Ví dụ file `src/main/resources/log4j2.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="STDOUT" target="SYSTEM_OUT">
            <PatternLayout charset="UTF-8"
                    pattern="%p %c{1} - %m%n"/>
        </Console>
    </Appenders>
    <Loggers>
        <Root level="INFO">
            <AppenderRef ref="STDOUT"/>
        </Root>
    </Loggers>
</Configuration>
```

Đây là **file cấu hình Log4j2 hoàn chỉnh**, nhưng để biên dịch chương trình dùng Log4j2 còn cần thư viện `log4j-api` và `log4j-core` ở phiên bản tương thích. Không dùng `javac` với chỉ JDK để chạy đoạn code Log4j2.

Đoạn code minh họa trong một lớp đã có dependency:

```java
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

public final class OrderService {
    private static final Logger LOG =
            LogManager.getLogger(OrderService.class);

    public void create(String orderId) {
        LOG.info("event=order_created order_id={}", orderId);
    }
}
```

Class trên **biên dịch với Log4j API** nhưng không có `main` nên không tự tạo output khi chạy trực tiếp. Nếu phương thức `create("ORD-101")` được gọi với file cấu hình trên, dòng output có dạng:

```text
INFO OrderService - event=order_created order_id=ORD-101
```

Đó là **message minh họa theo cấu hình**, không phải stdout của một chương trình `main` hoàn chỉnh ở phần này.

### Những thuộc tính đáng biết của ConsoleAppender

- `target="SYSTEM_OUT"`: ghi vào standard output.
- `target="SYSTEM_ERR"`: ghi vào standard error.
- `PatternLayout`: quy định level, logger name, message, newline. Nó **không quyết định** đích I/O.
- `immediateFlush`: khi bật, appender flush thường xuyên hơn; không bảo đảm collector đã persist log.
- `follow="true"`: theo tham chiếu `System.out`/`System.err` hiện tại khi có code thay đổi standard streams lúc chạy; không giống hành vi mặc định dùng stream tại lúc cấu hình.
- `direct="true"`: dùng file descriptor chuẩn trực tiếp trong một số cấu hình, có thể cải thiện hiệu năng nhưng cần đánh giá tương tác với những thành phần cũng viết vào standard streams.
- `follow` và `direct` không dùng kết hợp theo tài liệu cấu hình; đừng bật cả hai tùy tiện.

Khi chương trình thay `System.setOut(...)` ở runtime, appender đã được cấu hình trước đó **không nhất thiết đi theo** standard output mới trừ khi mode thích hợp được chọn. Đừng tự thay standard stream chỉ để “sửa” logging khi có thể cấu hình đúng đích ngay từ đầu.

### Nếu muốn in ERROR ra stderr, INFO ra stdout?

Đây là một **yêu cầu định tuyến theo mức**, không chỉ một thuộc tính của PatternLayout. Có thể dùng hai ConsoleAppender (một `SYSTEM_OUT`, một `SYSTEM_ERR`) và filter/routing thích hợp để tránh một `ERROR` bị ghi cả hai nơi. Không nhầm `ERROR` (level) với stderr (stream); nếu chỉ gắn một appender stdout cho root, mọi level được chấp nhận có thể đi ra stdout.

## 9. SLF4J là API; stdout phụ thuộc provider

Khi code dùng SLF4J:

```java
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(OrderService.class);

LOG.info("event=order_created order_id={}", orderId);
```

câu lệnh này **không quyết định stdout hay stderr**. SLF4J là facade. **Provider/backend** như Logback, `slf4j-simple` hoặc một adapter đến JUL mới quyết định nơi bản ghi xuất ra. Hai ứng dụng chạy cùng code SLF4J có thể ghi hai luồng khác nhau vì runtime có provider khác nhau.

### Với Logback

Logback có `ConsoleAppender` với `target` nhận `System.out` hoặc `System.err`. Trong cấu hình Logback, ví dụ file `logback.xml`:

```xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%level %logger{0} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

Đây là **file cấu hình Logback**, không phải `log4j2.xml`. Nó chỉ có tác dụng khi ứng dụng thực sự chọn provider Logback (ví dụ `logback-classic` tương thích với SLF4J API). `System.out` trong Logback **không viết thành `SYSTEM_OUT` của Log4j2**; hai hệ thống có cú pháp riêng.

`%msg` lấy message, `%level` lấy mức, `%n` xuống dòng; `%logger{0}` trình bày tên logger rút gọn theo converter của Logback. Output và các trường khác còn tùy template/phiên bản backend.

### Với slf4j-simple

`slf4j-simple` **mặc định ghi ra `System.err`**. Nếu muốn đổi sang stdout, có thể cấu hình thuộc tính JVM:

```bash
java -Dorg.slf4j.simpleLogger.logFile=System.out -cp "app-and-dependencies/*" example.Main
```

Đây là **lệnh minh họa**. `example.Main` và `app-and-dependencies/*` là tên/đường dẫn giả định; cần thay bằng ứng dụng thật và classpath chứa `slf4j-api`, `slf4j-simple` tương thích. Thuộc tính chỉ có tác dụng khi runtime chọn **SimpleLogger** làm implementation, không tự chuyển đích của Logback hay Log4j2.

Có thể đặt trong file `simplelogger.properties` trên classpath:

```properties
org.slf4j.simpleLogger.logFile=System.out
org.slf4j.simpleLogger.defaultLogLevel=info
```

Với cấu hình này, một lời gọi SLF4J `LOG.info(...)` có thể xuất ra stdout; định dạng còn gồm các thành phần do SimpleLogger quyết định. Không nên gắn thêm nhiều SLF4J provider chỉ để thử chuyển stderr sang stdout.

### Bảng so sánh nhanh

| Hệ thống Java logging | Cách đưa về stdout | Mặc định cần nhớ |
| --- | --- | --- |
| `System.out.println` | Gọi trực tiếp `System.out` | Là stdout nhưng chưa phải hệ thống logging có level |
| JUL `ConsoleHandler` | **Không** đổi target trực tiếp; dùng `StreamHandler(System.out, formatter)` hoặc handler riêng | `ConsoleHandler` → **stderr** |
| Log4j2 `ConsoleAppender` | `target="SYSTEM_OUT"` | ConsoleAppender thường mặc định stdout |
| Logback `ConsoleAppender` | `<target>System.out</target>` | Thường mặc định stdout |
| SLF4J + `slf4j-simple` | `org.slf4j.simpleLogger.logFile=System.out` | Mặc định **stderr** |
| SLF4J + provider khác | Cấu hình backend tương ứng | Không suy ra đích từ API SLF4J |

## 10. stdout trong Docker và Kubernetes

Một lý do phổ biến để ghi log ra stdout là ứng dụng được chạy trong **container**. Thay vì ứng dụng tự quản lý hàng loạt file log trong container, nhiều kiến trúc để runtime thu **stdout/stderr của tiến trình**, rồi giao cho logging driver, agent hoặc dịch vụ giám sát.

```text
Java service / Logger
          |
          v
    Console Appender
          |
          v
 stdout / stderr của PID
          |
          v
    Container runtime
          |
          v
 Log driver / node agent
          |
          v
  Collector / index / dashboard
```

Lợi ích vận hành:

- Không bắt buộc mỗi ứng dụng cấu hình đường dẫn tệp riêng trong filesystem tạm của container.
- Thống nhất đường thu giữa nhiều dịch vụ nếu nền tảng đã có agent.
- Dễ gắn thêm metadata như namespace, workload, pod, container hoặc instance ở **tầng thu thập**, nếu pipeline được cấu hình.
- Đơn giản hóa thay đổi đích lưu log mà không cần sửa mọi lời gọi logging trong mã Java.

**Nhưng không có bảo đảm tự động:** container runtime có thể xoay vòng/giới hạn log; pod có thể bị xóa, collector có thể mất kết nối, lọc/sampling có thể bỏ sự kiện, retention có thể ngắn. `kubectl logs` giúp xem log theo khả năng và trạng thái thực tế của workload, **không phải kho lưu trữ dài hạn mặc định**.

### Ví dụ Docker

Khi container chạy ứng dụng đã cấu hình log stdout:

```bash
docker logs my-java-service
```

Lệnh có thể hiển thị **cả stdout và stderr** tùy Docker logging driver/runtime. Vì vậy thấy bản ghi bằng `docker logs` **không đủ chứng minh nó được phát từ stdout**. Muốn phân biệt, kiểm tra cấu hình appender và khả năng gắn nhãn stream của hệ thống thu.

### Ví dụ Kubernetes

```bash
kubectl logs my-pod -c my-container
```

Lệnh chỉ là minh họa cú pháp: phải dùng tên pod/container thực tế và context cluster thích hợp. Nhiều giải pháp logging tận dụng dữ liệu log container để gắn metadata; không phải chỉ cần ghi stdout là mọi field như `trace_id` hoặc `service` tự tồn tại trong bản ghi.

**Khuyến nghị thiết kế:** một ứng dụng container nên có một chiến lược console logging được quản lý ở cấu hình logging framework, giữ message nhất quán, và xác minh hạ tầng thật sự nhận/retention theo yêu cầu. Không đồng thời bật nhiều nguồn (console và file được agent đọc) một cách vô tình khiến collector ingest cùng sự kiện hai lần.

## 11. Một dòng stdout có cấu trúc: JSON lines

Đối với hệ thống log tập trung, dùng JSON một sự kiện trên một dòng (**JSON Lines/NDJSON**) thường hữu ích hơn chuỗi text tự do nếu collector hỗ trợ.

Ví dụ **một event** minh họa:

```json
{"timestamp":"2026-11-09T12:00:00Z","level":"INFO","service":"checkout","event":"order_created","order_id":"ORD-101","correlation_id":"req-7"}
```

Đây là **JSON minh họa**, không phải output mặc định của JUL, Log4j2 hoặc Logback nếu chưa có encoder/layout. Với JSON, collector có thể phân tích các trường như `level` và `order_id` mà không phải đoán vị trí trong một câu văn.

Khi xuất JSON ra stdout, chú ý:

1. **Một sự kiện một JSON object trên một dòng** nếu bộ thu mong đợi NDJSON. JSON dạng pretty-print nhiều dòng có thể bị collector tách thành nhiều bản ghi.
2. **Escape đúng dữ liệu động**: dấu nháy kép, backslash, newline, ký tự điều khiển. Không tự ghép JSON bằng chuỗi cộng nối tùy ý.
3. **Tên trường ổn định**: `event`, `reason_code`, `correlation_id`, `duration_ms` có ý nghĩa/kiểu/đơn vị nhất quán.
4. **Timestamp có múi giờ rõ**: nhiều hệ thống dùng UTC ISO 8601; tránh timestamp thiếu timezone khi log từ nhiều host.
5. **Throwable/stack trace**: backend/encoder cần cấu hình để giữ thông tin exception thành chuỗi hoặc trường có cấu trúc phù hợp, không làm vỡ framing.
6. **Không ghi secret**: JSON hợp lệ vẫn có thể chứa dữ liệu không nên lưu trữ. Log collector có thể phân phối đến nhiều người và nhiều hệ thống.
7. **Giới hạn log volume**: stdout dễ thu nhưng việc ingest, index và retention vẫn có chi phí.

Với Log4j2 có thể xem `JsonTemplateLayout` (cần artifact `log4j-layout-template-json`); với Logback có thể dùng encoder JSON phù hợp với phiên bản/backend. Khi dùng SLF4J 2.x, `addKeyValue` chỉ đưa dữ liệu vào sự kiện: **provider/encoder quyết định việc những trường đó có được đưa vào JSON hay không**.

## 12. Ghi nhiều cấp log cùng stdout

Đích stdout và mức log là hai vấn đề **độc lập**. Có thể cho mọi level đã bật đi cùng stdout:

```text
INFO event=application_started
WARN event=cache_unavailable action=use_database
ERROR event=order_save_failed
```

Đây là output minh họa, không phải chương trình chạy trong phần 6.

Một số tổ chức muốn **INFO/DEBUG vào stdout** và **WARN/ERROR vào stderr** để shell hoặc hệ thống vận hành tách hai nhóm. Điều này cần **hai appender/handler cùng bộ lọc phù hợp**. Nếu chỉ gắn hai appender không filter, sự kiện `ERROR` có thể bị xuất ở cả hai luồng, gây trùng log.

Cũng không nên chuyển tất cả exception sang stderr bằng `System.err.println(e)` nếu ứng dụng đã có logger quản lý cấp và formatter. Khi đó thông tin về logger name, correlation ID và mẫu sự kiện có thể bị mất, còn stack trace không được quản lý nhất quán.

Quy tắc thực dụng:

- Chọn level theo **tác động nghiệp vụ và vận hành**, không theo đích stdout/stderr.
- Chọn luồng theo **hợp đồng CLI** hoặc **hạ tầng thu log**.
- Khi nhiều appender cùng tồn tại, kiểm tra filter, additivity và số bản ghi cuối cùng.
- Nếu stdout đang chứa dữ liệu máy đọc, tránh trộn log vào đó bất kể level.

## 13. Buffering, flush và độ tin cậy

Ghi vào stdout có nhiều lớp đệm tùy API và môi trường. Một lời gọi logger có thể:

1. Tạo LogEvent/LogRecord.
2. Được Handler/Appender chuyển thành text/bytes.
3. Nằm trong buffer của formatter/stream/appender hoặc queue async.
4. Đi ra stdout của tiến trình.
5. Được runtime/agent thu thập.
6. Được parser/collector lưu trong hệ thống tra cứu.

**Không phải bước nào cũng xác nhận bước sau đã hoàn tất.**

### `println` khác `StreamHandler.flush()`

`System.out.println` yêu cầu in một chuỗi, thường có hành vi flush theo cấu hình `PrintStream` được tạo bởi JVM. Trong ví dụ `StreamHandler`, LogRecord có thể được giữ trong buffer cho tới khi gọi `flush`. Do đó ví dụ làm rõ bước flush trước khi kết thúc.

**Đừng tùy tiện gọi `StreamHandler.close()` khi nó đang sở hữu `System.out`.** Theo API của Java 17, `StreamHandler.close()` đóng stream đích. Ngược lại, JUL `ConsoleHandler.close()` được thiết kế chỉ flush mà **không đóng `System.err`**.

### Async logging

Với appender/handler bất đồng bộ, lời gọi `LOG.info` thường đưa sự kiện vào queue rồi trả về; thread khác sẽ format/gửi sau. Khi ứng dụng kết thúc quá nhanh hoặc crash, sự kiện trong queue có thể chưa được xuất. Cần dừng logging framework đúng vòng đời và hiểu giới hạn buffer/queue khi tải cao.

### stdout không phải cơ chế lưu trữ bền vững

Ngay cả khi đã flush, stdout có thể là pipe đến process khác, file descriptor do runtime quản lý hoặc terminal. Nếu collector bị nghẽn, pipe có thể tạo **backpressure**, khiến thread ghi log chậm hoặc bị chặn. Nếu collector bỏ bản ghi quá dài hoặc giới hạn lưu trữ, một sự kiện trên stdout vẫn có thể không xuất hiện trên dashboard.

Với dữ liệu bắt buộc lưu (audit, giao dịch), không nên chỉ dựa vào log stdout. Cần nguồn dữ liệu nghiệp vụ có tính bền vững và cơ chế audit được thiết kế riêng.

## 14. Vấn đề bảo mật khi log stdout

Không vì stdout “chỉ ở trong container” mà xem nó là kênh riêng tư. Hạ tầng có thể thu tập trung, nhân bản và cấp quyền đọc cho nhiều người.

Những việc nên làm:

- **Tối thiểu hóa dữ liệu**: không đưa password, token, API key, OTP, số thẻ hoặc toàn bộ payload nhạy cảm vào message.
- **Mã hóa/escape đúng format**: với text lines, tránh CRLF injection; với JSON, dùng JSON encoder có hỗ trợ escape chính xác.
- **Kiểm soát độ dài**: một message chứa dữ liệu đầu vào rất lớn có thể làm tăng chi phí hoặc bị cắt thành nhiều phần trong collector.
- **Gắn correlation ID an toàn**: mã tương quan giúp tra cứu, nhưng không phải lý do để nhét PII hoặc bí mật vào MDC/ThreadContext.
- **Phân quyền**: giới hạn ai được đọc log ứng dụng, console CI và bản lưu tập trung.
- **Retention và xóa**: biết thời hạn lưu, nơi dữ liệu được nhân bản và cơ chế xử lý dữ liệu cần xóa.
- **Không dùng message text làm nguồn giao dịch chính thức**: log có thể bị trùng, mất, lấy mẫu hoặc đến chậm.

Đặc biệt với CLI, một script hoặc process cha có thể vô tình thu stdout của chương trình con và đưa toàn bộ vào ticket/build artifact. Việc in secret ra stdout có thể làm lộ dữ liệu ra những nơi không ai nghĩ là “hệ thống log”.

## 15. Phát hiện và sửa lỗi thường gặp

| Triệu chứng | Khả năng cần kiểm tra |
| --- | --- |
| Thấy log trên terminal nhưng `> output.log` không ghi được | Log đang ở stderr, điển hình JUL `ConsoleHandler` hoặc `slf4j-simple` mặc định |
| Không thấy `DEBUG` trên stdout | Logger/backend threshold hoặc appender/handler filter đang bỏ DEBUG |
| Dòng `ERROR` xuất hiện trên stdout | Console Appender được cấu hình xuất stdout; level không tự quyết định stream |
| Log có hai bản giống nhau | Logger cha/handler cha, additivity hoặc gắn hai appender tới cùng stdout |
| Gọi JUL `StreamHandler` nhưng output đến muộn | Chưa `flush` hoặc đang dùng buffer |
| Sau khi đóng handler, `System.out.println` không còn xuất | Có thể đã gọi `StreamHandler.close()` và vô tình đóng `System.out` |
| Console logging không hiện trên dashboard | Collector chưa thu stdout, parser lỗi, filter/sampling hoặc retention |
| Docker logs có dòng nhưng không phân biệt stream | `docker logs` có thể hiển thị cả stdout và stderr; cần dựa trên cấu hình và metadata |
| JSON không parse được | Bị trộn log text và JSON trên cùng stdout hoặc encoder/framing sai |
| Log chứa dòng giả từ user input | Thiếu escaping newline/CRLF cho dữ liệu không tin cậy |
| Dấu tiếng Việt bị hỏng | Encoding của handler/layout, terminal và bộ thu chưa đồng nhất |
| Log biến mất khi container restart | Runtime/collector/retention/rotation không bảo đảm lưu bền |
| CLI output không parse JSON được | Thông điệp logging đã trộn vào stdout vốn dành cho kết quả máy đọc |
| Khi tải cao chương trình chậm do log | I/O stdout, lock, buffer, collector backpressure hoặc quá nhiều sự kiện |

### Cách chẩn đoán theo thứ tự hợp lý

1. Xác định chương trình **đã gọi logger** chưa, và level có được bật không.
2. Xác định **provider/backend** hoặc JUL đang thực sự chạy.
3. Tìm **Handler/Appender đích**: `System.out`, `System.err`, file hay socket.
4. Kiểm tra **formatter/layout/encoder** có đang tạo một bản ghi có thể đọc/parse không.
5. Tách stdout và stderr bằng redirect để biết log nằm ở luồng nào.
6. Nếu ở container, xác nhận runtime/agent đã thu và ghi nhận nguồn đúng.
7. Nếu bytes đã ra stdout mà dashboard thiếu, kiểm tra collector/parser/filter/retention.
8. Với hiện tượng trùng, kiểm tra additivity/parent handler và nhiều nguồn thu.

Đây là quá trình từ nơi phát đến nơi nhận; không nên chỉ đổi `System.out.println` hay tăng level để “chữa” mọi hiện tượng thiếu log.

## 16. Lựa chọn cho từng môi trường

| Môi trường | Cách dùng stdout thường hợp lý |
| --- | --- |
| Bài tập Java trên terminal | `System.out.println` để quan sát kết quả; dùng JUL `StreamHandler` khi cần level và formatter |
| CLI xuất dữ liệu cho chương trình khác | Giữ stdout cho dữ liệu, chẩn đoán sang stderr hoặc kênh log khác |
| Dịch vụ Java trong Docker/Kubernetes | Console Appender ra stdout theo chính sách nền tảng, kèm collector có giám sát |
| Ứng dụng desktop | Console có thể không được người dùng nhìn thấy; cân nhắc file hoặc phương án chẩn đoán phù hợp |
| Service do systemd/process manager chạy | stdout/stderr có thể do process manager thu; kiểm tra cấu hình và retention cụ thể |
| Batch job trong CI | stdout thường được CI ghi lại; kiểm soát bí mật, lượng log và độ dài |
| Dịch vụ có yêu cầu audit nghiêm ngặt | stdout để quan sát, thêm cơ chế audit lưu bền thích hợp nếu bắt buộc |

Một dịch vụ dùng logger theo lớp có thể đổi từ file sang stdout **chỉ bằng cấu hình backend**, không cần sửa mọi lời gọi `LOG.info(...)`. Đây là lợi ích lớn của việc tách logger, formatter và handler/appender.

## 17. Tự kiểm tra kiến thức

1. **`System.out.println` ghi vào đâu?** Standard output của tiến trình.
2. **`System.err.println` ghi vào đâu?** Standard error của tiến trình.
3. **JUL `ConsoleHandler` mặc định là stdout hay stderr?** **Stderr**.
4. **Làm sao dùng JUL với stdout?** Chẳng hạn `new StreamHandler(System.out, formatter)`, quản lý flush và vòng đời chính xác.
5. **Có nên gọi `StreamHandler.close()` khi truyền vào `System.out` không?** Không tùy tiện; API này đóng output stream. Cần tránh đóng stdout dùng chung.
6. **`ERROR` có bắt buộc ở stderr không?** Không. Mức log và luồng đích là hai cấu hình độc lập.
7. **Cấu hình Log4j2 ConsoleAppender stdout bằng gì?** `target="SYSTEM_OUT"`.
8. **Cấu hình Logback ConsoleAppender stdout bằng gì?** `<target>System.out</target>`.
9. **`slf4j-simple` mặc định ghi đâu?** `System.err`; có thể đổi bằng thuộc tính `org.slf4j.simpleLogger.logFile=System.out`.
10. **Vì sao một CLI xuất JSON không nên log text ra stdout?** Vì stdout sẽ lẫn log và dữ liệu, làm công cụ parse JSON thất bại.
11. **Tại sao thấy dòng bằng `docker logs` chưa xác nhận stdout?** Runtime có thể hiển thị cả stdout lẫn stderr.
12. **`flush` có chứng minh collector đã lưu bền không?** Không. Nó chỉ đưa dữ liệu ra khỏi những buffer liên quan tại phía gửi.
13. **Vì sao phải có `%n` hoặc newline khi xuất text log?** Để tách các sự kiện theo dòng cho người đọc và collector.
14. **Một stdout JSON object có luôn được lập chỉ mục thành field không?** Không. Collector phải được cấu hình parse JSON và giữ trường.
15. **Nếu ứng dụng gắn hai handler cùng xuất stdout, điều gì xảy ra?** Một LogRecord có thể tạo hai bản giống nhau.
16. **Log stdout trong Kubernetes có tự lưu vĩnh viễn không?** Không. Phải xét runtime, log rotation, collector, retention và quyền truy cập.
17. **Có thể vừa ghi stdout vừa file không?** Có, bằng nhiều appender/handler; phải kiểm soát trùng ở pipeline.
18. **Có nên dùng log stdout làm nguồn duy nhất xác nhận giao dịch tài chính đã thành công không?** Không; phải dựa vào nguồn trạng thái nghiệp vụ bền vững.

## 18. Tài liệu tham khảo

- Oracle Java 17, `ConsoleHandler`: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/ConsoleHandler.html
- Oracle Java 17, `StreamHandler`: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/StreamHandler.html
- Apache Log4j 2, Console Appender: https://logging.apache.org/log4j/2.x/manual/appenders.html
- Logback, ConsoleAppender: https://logback.qos.ch/manual/appenders-console-file.html
- SLF4J SimpleLogger: https://www.slf4j.org/apidocs-2.0.17/org/slf4j/simple/SimpleLogger.html

**Ghi nhớ:** **stdout là đích I/O của tiến trình, không phải cấp độ log hay định dạng log**. Trong Java, `System.out.println` in trực tiếp, JUL `ConsoleHandler` mặc định đi stderr còn `StreamHandler(System.out, formatter)` có thể đi stdout; Log4j2 và Logback chọn stdout bằng ConsoleAppender, còn SLF4J cần cấu hình provider. Luôn kiểm chứng bằng tách luồng, quản lý buffer/vòng đời, bảo vệ dữ liệu nhạy cảm và kiểm tra toàn bộ pipeline từ stdout đến nơi lưu.
