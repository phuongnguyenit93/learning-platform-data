# Log ra stderr trong Java: console logging đúng luồng

## 1. stderr là gì?

Khi một chương trình Java chạy trong terminal hoặc được hệ điều hành khởi động như một tiến trình, nó thường có hai luồng xuất chuẩn:

- **stdout (standard output):** luồng dành cho kết quả chính của chương trình. Trong Java truy cập qua `System.out`.
- **stderr (standard error):** luồng thường dành cho thông báo lỗi, cảnh báo và thông tin chẩn đoán. Trong Java truy cập qua `System.err`.

Hai luồng này **độc lập về mặt logic**. Chúng đều có thể hiện trên cùng một cửa sổ terminal, nhưng shell, IDE, container runtime hoặc hệ thống thu thập log có thể chuyển chúng tới **hai đích khác nhau**.

Trên các hệ điều hành và shell theo quy ước POSIX, stdout thường gắn với file descriptor **1**, còn stderr với file descriptor **2** (stdin là 0). Cú pháp chuyển hướng của các shell thường dựa vào số này.

```text
                    Ứng dụng Java
                          │
              ┌───────────┴───────────┐
              │                       │
              ▼                       ▼
     System.out / stdout       System.err / stderr
      file descriptor 1         file descriptor 2
              │                       │
              ▼                       ▼
     Kết quả / dữ liệu       Chẩn đoán / cảnh báo /
                               lỗi / stack trace
```

**Ý chính:** `stderr` là **đích xuất**, không phải một log level. Một bản ghi `INFO` có thể được gửi tới stderr; một bản ghi `ERROR` có thể được backend ghi vào stdout, file hoặc collector. Mức độ nghiêm trọng và luồng xuất là **hai quyết định riêng**.

### Khi nào nên dùng stderr?

Trong một **chương trình dòng lệnh (CLI)**, quy ước hữu ích là:

- **stdout:** dữ liệu hoặc kết quả để người dùng và các lệnh khác xử lý.
- **stderr:** lỗi, cảnh báo, tiến độ hoặc thông tin chẩn đoán không thuộc kết quả chính.
- **exit code:** mã kết thúc cho biết thành công hay thất bại; không thể thay bằng việc chỉ in chữ `ERROR`.

Ví dụ công cụ tính toán có thể in `42` trên stdout, còn thông báo `WARNING | Using fallback configuration` trên stderr. Người dùng vẫn có thể đưa stdout sang file để xử lý mà không làm lẫn những lời nhắn chẩn đoán.

Trong **ứng dụng server**, chính sách xuất stdout/stderr phụ thuộc hạ tầng và logging backend. Nhiều nền tảng container thu thập cả hai luồng; đôi khi chúng được gắn nhãn khác nhau nhưng không nên mặc định mọi nơi xử lý hai luồng giống nhau.

## 2. Cách ghi trực tiếp ra stderr trong Java

`System.err` là một đối tượng `java.io.PrintStream` do JVM cung cấp. Bạn có thể gọi `print`, `println` hoặc `printf`, tương tự như với `System.out`:

```java
System.out.println("result=42");                       // stdout
System.err.println("ERROR | Cannot open configuration"); // stderr
System.err.printf("WARNING | Retry attempt %d%n", 2);   // stderr
```

Đây là **đoạn mã minh họa**, đặt trong một method (chẳng hạn `main`) để chạy. `%n` trong `printf` tạo dấu xuống dòng theo nền tảng, phù hợp hơn ghi cứng ký tự xuống dòng trong nhiều trường hợp.

Dùng `System.err` có các ưu điểm:

1. Có sẵn trong JDK, không cần thêm thư viện.
2. Có thể chuyển hướng và thu thập tách khỏi kết quả `System.out`.
3. Phù hợp với lỗi tối giản trong CLI, thông báo startup khi hệ thống logger chưa khởi tạo, hoặc các demo nhỏ.

Nhưng `System.err.println(...)` **không tự trở thành một logging framework**: không có level filtering, tên logger, timestamp, correlation ID, rolling file, log retention, JSON encoder hoặc cơ chế định tuyến đa đích. Muốn điều khiển những yếu tố đó nên dùng JUL, SLF4J cùng backend, Logback, Log4j2 hoặc giải pháp logging đã được ứng dụng chọn.

### stderr không có nghĩa là “chương trình bị lỗi”

Mặc dù tên là *standard error*, vẫn hợp lý khi gửi **thông điệp chẩn đoán không nghiêm trọng** lên stderr, ví dụ chương trình đang khởi tạo hoặc thống kê tiến độ trong khi stdout chứa dữ liệu máy đọc. Điều quan trọng là **hợp đồng đầu ra** phải rõ ràng và nhất quán.

Ngược lại, nếu lỗi nghiêm trọng xảy ra, chỉ viết một dòng trên stderr **không tự làm exit code khác 0**. Chương trình cần trả mã lỗi phù hợp hoặc ném lỗi ra ngoài nếu đó là chính sách đã chọn.

## 3. Ví dụ Java 17 hoàn chỉnh: stdout cho kết quả, stderr cho chẩn đoán

Tạo file `CliStderrDemo.java`:

```java
import java.io.PrintStream;

public final class CliStderrDemo {

    static int run(String input, PrintStream out, PrintStream err) {
        try {
            int value = Integer.parseInt(input);
            out.println(value * 2);
            err.println("INFO | Parsed integer");
            return 0;
        } catch (NumberFormatException exception) {
            // Đây là lỗi nhập liệu dự kiến: không cần in full stack trace.
            err.println("ERROR | Input must be an integer");
            return 2;
        }
    }

    public static void main(String[] args) {
        if (args.length != 1) {
            System.err.println(
                    "ERROR | Usage: java CliStderrDemo <integer>");
            System.exit(2);
            return;
        }

        int exitCode = run(args[0], System.out, System.err);
        if (exitCode != 0) {
            System.exit(exitCode);
        }
    }
}
```

Đây là **một chương trình độc lập**, chạy với JDK 17 trở lên, không cần thư viện bên ngoài.

Biên dịch:

```bash
javac CliStderrDemo.java
```

Chạy với đối số hợp lệ:

```bash
java CliStderrDemo 21
```

**Hai dòng được tạo ra:**

```text
42
INFO | Parsed integer
```

Trong đó `42` thuộc **stdout**, còn `INFO | Parsed integer` thuộc **stderr**. Khi cả hai luồng cùng được vẽ trong một terminal, **không nên dựa vào thứ tự hiển thị hợp nhất** làm cam kết của API: buffering, terminal và cơ chế thu thập có thể ảnh hưởng thứ tự giữa các luồng.

Chạy với đầu vào không hợp lệ:

```bash
java CliStderrDemo abc
```

Chương trình không in dữ liệu kết quả ra stdout. Nó ghi chính xác một dòng lên stderr:

```text
ERROR | Input must be an integer
```

Trong trường hợp này tiến trình kết thúc với **exit code 2**, vì code gọi `System.exit(2)`. Với đối số hợp lệ, `main` kết thúc bình thường, exit code là **0**.

### Tại sao ví dụ có phương thức run(out, err)?

Việc đưa `PrintStream out` và `PrintStream err` vào method thay vì gọi `System.out/System.err` ở mọi nơi có một lợi ích lớn: **dễ kiểm thử**. Trong unit test, có thể truyền những `PrintStream` giả ghi vào bộ nhớ thay vì thay đổi hai luồng toàn cục của JVM. Cách này đặc biệt hữu ích khi ứng dụng có nhiều test chạy đồng thời.

Lỗi đầu vào được xử lý thành thông báo ngắn, không phải exception bất ngờ cần in cả stack trace. Nhờ đó stderr vẫn đọc được và không làm ngập log với các tình huống người dùng nhập sai thông thường.

## 4. Chuyển hướng stdout và stderr bằng shell

Hai luồng được phân biệt rõ nhất khi đưa chúng sang hai tệp khác nhau.

### 4.1. Bash, zsh và các shell tương thích trên Linux/macOS

Sau khi biên dịch `CliStderrDemo.java`, chạy:

```bash
java CliStderrDemo 21 1> success.out 2> success.err
```

Kết quả **chính xác**:

**Tệp `success.out`:**

```text
42
```

**Tệp `success.err`:**

```text
INFO | Parsed integer
```

Với đầu vào sai:

```bash
java CliStderrDemo abc 1> failure.out 2> failure.err
```

`failure.out` rỗng; `failure.err` có:

```text
ERROR | Input must be an integer
```

Kiểm tra mã thoát ngay sau lời gọi Java bằng `echo $?` ở Bash/zsh:

```bash
java CliStderrDemo abc 1> failure.out 2> failure.err
echo $?
```

Kết quả mã thoát là `2`. Nếu một lệnh khác được chạy xen giữa, `$?` có thể đã phản ánh lệnh trung gian đó thay vì Java.

Các cú pháp quen thuộc:

| Cú pháp shell | Ý nghĩa |
| --- | --- |
| `> output.txt` hoặc `1> output.txt` | Chuyển stdout sang file (ghi đè) |
| `2> error.txt` | Chuyển stderr sang file (ghi đè) |
| `1>> output.txt` | Nối thêm stdout vào file |
| `2>> error.txt` | Nối thêm stderr vào file |
| `> all.log 2>&1` | Đưa stdout vào file và trỏ stderr về cùng đích đã chọn cho stdout |
| `2> /dev/null` | Bỏ stderr trong shell POSIX; dùng có chủ đích |
| `1> /dev/null` | Bỏ stdout trong shell POSIX |

**Thứ tự toán tử có ý nghĩa:** `> all.log 2>&1` sẽ kết hợp hai luồng vào file; `2>&1 > all.log` có thể để stderr ở đích stdout **trước khi** stdout được chuyển sang file. Không đảo thứ tự mà không hiểu chính xác nó đang tham chiếu descriptor nào.

Dù hai luồng được trỏ về cùng tệp, thứ tự các dòng từ hai luồng **không phải lúc nào cũng phản ánh chính xác thứ tự các lời gọi Java**, đặc biệt khi có buffering hoặc nhiều thread/process.

### 4.2. Windows PowerShell

PowerShell cũng hỗ trợ chuyển hướng cho tiến trình Java bên ngoài:

```powershell
javac CliStderrDemo.java
java CliStderrDemo 21 1> success.out 2> success.err
java CliStderrDemo abc 1> failure.out 2> failure.err
$LASTEXITCODE
```

Sau lệnh Java cuối, `$LASTEXITCODE` dự kiến là `2`. Với lời gọi thành công gần nhất, giá trị dự kiến là `0`.

PowerShell có hệ thống luồng riêng của PowerShell và cách xử lý output/encoding của native commands có thể khác theo phiên bản. Vì vậy khi cần tích hợp tự động, kiểm tra nội dung file và exit code thực tế trên phiên bản PowerShell/Windows của môi trường đích. Đừng ngộ nhận thông báo stderr của Java là một exception bị ném trong PowerShell; đó là output của một tiến trình con.

### 4.3. Windows cmd.exe

Trong Command Prompt:

```bat
javac CliStderrDemo.java
java CliStderrDemo abc 1> failure.out 2> failure.err
echo %ERRORLEVEL%
```

Giá trị dự kiến là `2`. Cú pháp `1>` và `2>` ở đây cũng đại diện cho stdout và stderr.

### 4.4. Vì sao nên tách stdout trong CLI?

Nếu stdout được một pipeline dùng để đọc JSON, CSV, số liệu hoặc danh sách tệp, một dòng chẩn đoán chen vào stdout có thể làm **sai kết quả máy đọc**:

```text
SAI: stdout chứa cả dữ liệu và thông báo
42
WARNING | Using default configuration
```

Tách hai luồng:

```text
stdout: 42
stderr: WARNING | Using default configuration
```

Một command có thể vừa thành công vừa phát cảnh báo lên stderr; **có dòng stderr không tự đồng nghĩa exit code khác 0**. Các script tin cậy nên dựa vào exit code và hợp đồng dữ liệu, không chỉ tìm từ “ERROR” trong một file text.

## 5. Stack trace: Throwable.printStackTrace() mặc định ghi vào stderr

Trong Java, `Throwable.printStackTrace()` mặc định ghi chuỗi stack trace ra `System.err`.

Ví dụ độc lập: tạo file `StderrStackTraceDemo.java`:

```java
public final class StderrStackTraceDemo {
    public static void main(String[] args) {
        try {
            Integer.parseInt("invalid");
        } catch (NumberFormatException exception) {
            System.err.println("ERROR | Invalid port configuration");
            exception.printStackTrace();
        }
        System.out.println("demo-finished");
    }
}
```

Biên dịch, chạy và tách luồng:

```bash
javac StderrStackTraceDemo.java
java StderrStackTraceDemo 1> result.txt 2> trace.txt
```

**Tệp `result.txt` chính xác:**

```text
demo-finished
```

**Tệp `trace.txt`** có dòng thông báo lỗi và stack trace `NumberFormatException`; dạng minh họa:

```text
ERROR | Invalid port configuration
java.lang.NumberFormatException: For input string: "invalid"
    at java.base/java.lang.NumberFormatException.forInputString(...)
    ...
    at StderrStackTraceDemo.main(StderrStackTraceDemo.java:<line>)
```

Ký hiệu `...` và `<line>` **không phải output nguyên văn**. Stack frame và số dòng phụ thuộc JDK và mã nguồn được biên dịch. Không nên so sánh toàn bộ stack trace với một chuỗi cố định trong bài kiểm thử.

Có ba cách ghi khác nhau:

```java
exception.printStackTrace();               // Mặc định System.err.
exception.printStackTrace(System.err);    // Chỉ định rõ PrintStream.
System.err.println(exception);            // Chỉ toString(), không đủ frames.
```

Đây là các lời gọi **minh họa trong method có biến `exception`**. `System.err.println(exception)` thường chỉ in tên exception và message qua `toString()`, không phải các frame đầy đủ.

**Hạn chế quan trọng:** `printStackTrace()` đi trực tiếp tới stream/writer, không tự đi qua level, handler, filter, formatter, MDC hoặc hệ thống backend logging của ứng dụng. Trong ứng dụng đã dùng logging framework, nên truyền nguyên đối tượng `Throwable` cho logger ở vị trí xử lý lỗi phù hợp:

```java
logger.log(java.util.logging.Level.SEVERE,
        "Failed to load configuration", exception);
```

Đây là API của JUL, giả định `logger` là `java.util.logging.Logger`. Để exception hiện đủ stack trace, formatter/handler cần hỗ trợ `LogRecord.getThrown()`; `SimpleFormatter` của JUL làm được điều này.

Không gọi đồng thời `exception.printStackTrace()` và `logger.log(..., exception)` cho cùng lỗi nếu không có lý do rõ ràng, vì có thể tạo bản ghi trùng trong console/collector.

## 6. JUL: ConsoleHandler mặc định ghi ra stderr

`java.util.logging` (JUL) là logging API sẵn trong JDK. `ConsoleHandler` là handler đưa log ra console, và **theo mặc định nó xuất qua `System.err`**. Điều này **khác** với việc dùng `System.err.println(...)` trực tiếp:

| Đặc điểm | `System.err.println(...)` | JUL `ConsoleHandler` |
| --- | --- | --- |
| Đích mặc định | stderr | stderr |
| Level tại logger | Không có | Có |
| Level tại handler | Không có | Có |
| Formatter | Thông điệp do lập trình viên tự tạo | `Formatter`, mặc định thường là `SimpleFormatter` |
| Thông tin exception | Lập trình viên tự in | `LogRecord` có thể chứa `Throwable` |
| Kế thừa handler | Không có | Có cơ chế parent handlers |
| Định dạng, filter | Tự viết | Cấu hình JUL |

Một chương trình dùng `Logger.info(...)` **không bắt buộc** tạo dòng stdout; nếu record tới `ConsoleHandler` của JUL, nó có thể được in ra stderr dù level là INFO. Đây là một lý do phổ biến khiến người học thấy “log INFO nằm trong file lỗi” khi dùng `2> error.log`.

### 6.1. Ví dụ Java 17 chạy được với ConsoleHandler

Tạo file `JulStderrDemo.java`:

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class JulStderrDemo {
    public static void main(String[] args) {
        Logger logger = Logger.getLogger(JulStderrDemo.class.getName());

        // Lưu cấu hình cũ của logger để không giữ thay đổi sau demo.
        Level oldLevel = logger.getLevel();
        boolean oldParentHandlers = logger.getUseParentHandlers();
        Handler[] oldHandlers = logger.getHandlers();

        // Một handler của demo, không dùng handler mặc định của root.
        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.INFO);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " | "
                        + formatMessage(record) + System.lineSeparator();
            }
        });

        for (Handler handler : oldHandlers) {
            logger.removeHandler(handler);
        }
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.FINE);
        logger.addHandler(console);

        try {
            logger.fine("Hidden because console threshold is INFO");
            logger.info("Service ready");
            logger.warning("Using fallback configuration");
            System.out.println("result=OK");
        } finally {
            logger.removeHandler(console);
            console.close();
            logger.setLevel(oldLevel);
            logger.setUseParentHandlers(oldParentHandlers);
            for (Handler handler : oldHandlers) {
                logger.addHandler(handler);
            }
        }
    }
}
```

Biên dịch và chạy:

```bash
javac JulStderrDemo.java
java JulStderrDemo 1> jul.out 2> jul.err
```

**Tệp `jul.out` chính xác:**

```text
result=OK
```

**Tệp `jul.err` chính xác:**

```text
INFO | Service ready
WARNING | Using fallback configuration
```

Dòng `FINE` không xuất, **không phải vì stderr chỉ dành cho ERROR**, mà vì `console.setLevel(Level.INFO)` lọc FINE. Logger được đặt `FINE` nên chấp nhận bản ghi, nhưng handler lại lọc nó trước khi format.

`logger.setUseParentHandlers(false)` ngăn record chuyển lên handler của root logger, tránh log trùng trong demo. Code khôi phục level/propagation và handler đã tồn tại trong `finally`; `console.close()` chỉ đóng handler do demo tạo. Đây là chương trình học chạy riêng; trong server có nhiều request/thread, không nên tháo lắp handler dùng chung bất chợt trong lúc hệ thống đang phục vụ.

**Một lưu ý sâu hơn:** `ConsoleHandler` giữ luồng đích của nó trong vòng đời handler. Nếu chương trình gọi `System.setErr(...)` **sau khi** handler đã được tạo, không nên giả định handler đang tồn tại sẽ tự động đi theo stream mới. Cấu hình nơi nhận log nên được thiết lập lúc khởi tạo, thay vì thay stream toàn JVM một cách bất ngờ.

### 6.2. logging.properties của JUL

Có thể dùng file `logging.properties` để bật root ConsoleHandler:

```properties
handlers = java.util.logging.ConsoleHandler
.level = INFO
java.util.logging.ConsoleHandler.level = INFO
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter
```

Khi có ứng dụng JUL hợp lệ, chỉ định file lúc khởi động JVM:

```bash
java -Djava.util.logging.config.file=logging.properties MyApplication
```

`MyApplication` ở đây chỉ **một main class có sẵn trong ứng dụng**, không phải file demo mới. `ConsoleHandler` sẽ ghi các bản ghi được chấp nhận vào stderr theo hành vi của JUL. `SimpleFormatter` thường thêm thời gian, tên class/method và level, nên output không giống formatter rút gọn của `JulStderrDemo`.

Level của **logger** và level của **ConsoleHandler** là hai ngưỡng độc lập. Nếu logger cho phép FINE nhưng handler chỉ cho INFO, thông điệp FINE vẫn không xuất. Trong JUL, `getHandlers()` chỉ trả về handler gắn **trực tiếp** vào logger được gọi; log có thể đi tới handler của cha/root nếu `useParentHandlers` bật.

## 7. SLF4J SimpleLogger: cấu hình stderr như thế nào?

**SLF4J** là facade logging cho Java. Đối tượng `org.slf4j.Logger` không tự quyết định ghi stdout hay stderr; điều đó thuộc **provider/backend**.

Với provider `slf4j-simple`, thuộc tính `org.slf4j.simpleLogger.logFile` cho phép chọn đích:

```properties
org.slf4j.simpleLogger.defaultLogLevel=info
org.slf4j.simpleLogger.logFile=System.err
```

Đây là nội dung minh họa của `simplelogger.properties`, thường được đặt trên classpath, ví dụ `src/main/resources/simplelogger.properties` trong một ứng dụng Maven. `System.err` là một giá trị đích được `slf4j-simple` hỗ trợ; những triển khai SLF4J khác **không sử dụng cùng file và cùng tên thuộc tính**.

Ví dụ lời gọi SLF4J trong class có `org.slf4j.Logger LOG`:

```java
LOG.info("Application started");
LOG.error("Cannot process request");
```

Với cấu hình trên và provider hoạt động, **cả INFO lẫn ERROR đều có thể nằm trên stderr**. Điều này minh họa rằng **đích stderr không phải điều kiện tự động cho level ERROR**, và **level ERROR không tự chọn stderr**.

Nếu đổi property thành:

```properties
org.slf4j.simpleLogger.logFile=System.out
```

provider SimpleLogger sẽ hướng các log qua stdout theo cấu hình. Với backend Logback hoặc Log4j2, dùng cấu hình appender tương ứng thay vì property SimpleLogger.

SLF4J API 2.x cần provider runtime tương thích. Nếu thiếu provider, các lời gọi có thể rơi vào NOP và không ghi log như mong muốn; nếu có nhiều provider, lựa chọn backend có thể không như dự kiến. Khi không thấy dòng stderr, hãy kiểm tra **provider thực tế** và dependency tree thay vì chỉ sửa code gọi `LOG.error(...)`.

## 8. Logback: chọn System.err bằng ConsoleAppender

Với Logback Classic, `ConsoleAppender` có thuộc tính `target`. Trong `logback.xml`, có thể chỉ định:

```xml
<configuration>
    <appender name="STDERR"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.err</target>
        <encoder>
            <pattern>%-5level | %logger{1} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="STDERR"/>
    </root>
</configuration>
```

Đây là **file cấu hình Logback đầy đủ ở mức tối giản**; để sử dụng cần ứng dụng có SLF4J API và Logback backend/provider tương thích. Nếu code gọi:

```java
LOG.info("Service started");
LOG.warn("Slow dependency");
LOG.error("Request failed");
```

thì khi logger/root INFO và không có filter khác, cả ba bản ghi có thể xuất qua **stderr** vì appender đã chọn `System.err`. Đừng suy luận `INFO` tự động chuyển sang stdout hoặc `ERROR` tự động chuyển sang stderr: một appender có thể chứa nhiều level.

Nếu ứng dụng đã có Logback config riêng, cần chỉnh đúng file thực sự được nạp, không tạo thêm `logback.xml` cạnh tranh. Mã `org.slf4j.Logger` không có một API chung `setOutputStream(System.err)` để thay đích; việc định tuyến thuộc provider và appender.

## 9. Log4j2: ConsoleAppender target SYSTEM_ERR

Với **Apache Log4j2**, một Console appender có thể chỉ định `target="SYSTEM_ERR"` trong `log4j2.xml`:

```xml
<Configuration status="WARN">
    <Appenders>
        <Console name="StderrConsole" target="SYSTEM_ERR">
            <PatternLayout pattern="%level | %msg%n"/>
        </Console>
    </Appenders>

    <Loggers>
        <Root level="info">
            <AppenderRef ref="StderrConsole"/>
        </Root>
    </Loggers>
</Configuration>
```

Cấu hình trên có một console appender ghi mọi event **được root chấp nhận** từ mức INFO trở lên tới stderr. Để sử dụng, chương trình cần Log4j2 API/Core phù hợp với runtime; file `log4j2.xml` phải nằm ở nơi Log4j2 có thể nạp, ví dụ `src/main/resources/log4j2.xml` của Maven. Đây là **ví dụ cấu hình**, không phải một chương trình Java độc lập.

Ví dụ mã nguồn sử dụng Log4j2 API:

```java
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

public final class Log4jStderrSnippet {
    private static final Logger LOG =
            LogManager.getLogger(Log4jStderrSnippet.class);

    public static void main(String[] args) {
        LOG.info("Initialized");
        LOG.error("Unavailable dependency");
        System.out.println("result=OK");
    }
}
```

Class này **biên dịch nếu dự án đã cung cấp Log4j2 API dependency**, còn để ghi ra stderr như cấu hình cần Log4j2 Core và cấu hình `log4j2.xml` ở runtime. Tệp `Log4jStderrSnippet.java` không phải ví dụ chỉ dùng JDK; không chạy bằng `javac` thuần khi thiếu các JAR ngoài JDK.

### Muốn ERROR ra stderr, INFO/WARN ra stdout thì sao?

Đây là yêu cầu **khác** với “đưa toàn bộ console logging ra stderr”. Khi cần chia level theo stream, khai báo **hai appender khác nhau và lọc để chúng không chồng lặp**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="Stdout" target="SYSTEM_OUT">
            <ThresholdFilter level="ERROR"
                             onMatch="DENY"
                             onMismatch="NEUTRAL"/>
            <PatternLayout pattern="%level | %msg%n"/>
        </Console>

        <Console name="Stderr" target="SYSTEM_ERR">
            <ThresholdFilter level="ERROR"
                             onMatch="ACCEPT"
                             onMismatch="DENY"/>
            <PatternLayout pattern="%level | %msg%n"/>
        </Console>
    </Appenders>

    <Loggers>
        <Root level="INFO">
            <AppenderRef ref="Stdout"/>
            <AppenderRef ref="Stderr"/>
        </Root>
    </Loggers>
</Configuration>
```

Cấu hình mẫu này dành cho Log4j2 với các filter/level chuẩn:

- **Stdout:** khi event từ root có mức ERROR trở lên, filter từ chối; INFO/WARN được phép tiếp tục.
- **Stderr:** chỉ nhận ERROR/FATAL; INFO/WARN bị từ chối.
- **Root INFO:** loại DEBUG/TRACE trước khi event đến hai appender.

Đây là **ví dụ cấu hình tách stream**, không phải cơ chế mặc định của Log4j2. Các filter khác hoặc logger con với cấu hình riêng có thể thay đổi kết quả. Nếu không đặt filter đối ứng, một event ERROR có thể được **cả hai appender nhận** và xuất hai lần qua hai luồng.

**Lưu ý về phát hiện log trùng:** khi một event xuất trên cả stdout và stderr theo chủ đích, hệ thống thu thập có thể lưu nó như hai bản ghi. Nếu yêu cầu chỉ một đích cho mỗi level, phải kiểm tra cấu hình filter và additivity với log thử thực tế.

## 10. Phân biệt log level và luồng output

Tương quan thường gặp nhưng **không phải một quy tắc bắt buộc**:

| Lệnh / hệ thống | Level | Đích có thể nhận |
| --- | --- | --- |
| `System.out.println("OK")` | Không có log level | stdout |
| `System.err.println("Warning")` | Không có log level | stderr |
| `Throwable.printStackTrace()` | Không có log level JUL/SLF4J | stderr mặc định |
| JUL `Logger.info(...)` qua ConsoleHandler | INFO | stderr |
| JUL `Logger.severe(...)` qua ConsoleHandler | SEVERE | stderr |
| SLF4J `LOG.error(...)` | ERROR | Do provider/backend quyết định |
| Log4j2 `LOG.info(...)` + `target="SYSTEM_ERR"` | INFO | stderr |
| Logback `LOG.error(...)` + `target=System.out` | ERROR | stdout |

Một câu hỏi kiểm tra quan trọng: **“Nếu tôi gọi LOG.error(...) thì chắc chắn vào stderr không?”** — **Không**. Nó đi theo đường logger → provider/backend → filter → appender/handler → đích đã chọn.

Tương tự, **`System.err` không tự có level**. Nó nhận các chuỗi được gửi đến mà không hiểu chuỗi đó là “WARN” hay “ERROR”. Muốn thiết kế quy tắc INFO→stdout, ERROR→stderr, cần **logging backend hoặc logic CLI** thực thi quy tắc; không có phép ánh xạ chung bắt buộc trong Java.

## 11. Bắt output trong test mà không thay đổi System.err toàn cục

Một phương án dễ kiểm thử là đưa luồng output thành tham số, như `CliStderrDemo.run(String, PrintStream, PrintStream)` ở mục 3.

Ví dụ một phép kiểm thử không cần JUnit, dùng JDK 17. Tạo file `CliStderrCheck.java` trong cùng thư mục sau khi đã tạo `CliStderrDemo.java`:

```java
import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;

public final class CliStderrCheck {
    public static void main(String[] args) throws Exception {
        ByteArrayOutputStream outBytes = new ByteArrayOutputStream();
        ByteArrayOutputStream errBytes = new ByteArrayOutputStream();

        try (PrintStream out =
                     new PrintStream(outBytes, true, StandardCharsets.UTF_8);
             PrintStream err =
                     new PrintStream(errBytes, true, StandardCharsets.UTF_8)) {

            int exitCode = CliStderrDemo.run("21", out, err);
            out.flush();
            err.flush();

            String capturedOut =
                    outBytes.toString(StandardCharsets.UTF_8);
            String capturedErr =
                    errBytes.toString(StandardCharsets.UTF_8);

            boolean passed = exitCode == 0
                    && capturedOut.equals("42" + System.lineSeparator())
                    && capturedErr.equals(
                            "INFO | Parsed integer" + System.lineSeparator());

            System.out.println(passed ? "PASS" : "FAIL");
            if (!passed) {
                throw new AssertionError("Unexpected CLI streams");
            }
        }
    }
}
```

Đây là **chương trình kiểm thử độc lập** nhưng yêu cầu class `CliStderrDemo` cùng thư mục/classpath:

```bash
javac CliStderrDemo.java CliStderrCheck.java
java CliStderrCheck
```

**Stdout chính xác khi kiểm tra thành công:**

```text
PASS
```

Điểm đáng học: code kiểm thử bắt `PrintStream` giả và so sánh hai chuỗi riêng, không cần gọi `System.setOut(...)` hay `System.setErr(...)`. Các stream được đóng là **stream do test tạo**, không phải stream chuẩn của tiến trình.

### Vì sao nên thận trọng với System.setErr?

`System.setErr(PrintStream)` thay đổi tham chiếu stderr toàn cục của JVM. Đây có thể là kỹ thuật hỗ trợ một số test đặc thù, nhưng có rủi ro:

- Thread khác trong cùng JVM có thể bắt đầu ghi nhầm vào stream của test.
- Logging handler/appender đã được tạo **trước đó** có thể giữ một stream khác và không đi theo thay đổi.
- Nếu không khôi phục trạng thái, các test về sau có thể bị ảnh hưởng.
- Đóng nhầm `System.err` làm hỏng việc in lỗi của thành phần khác.

Với code CLI tự quản lý, **dependency injection của PrintStream** thường là cách rõ ràng và ít tác động hơn. Với logging framework, nên thử appender/handler ở môi trường kiểm thử hoặc dùng test appender của backend, thay vì thay đổi stream toàn cục tùy tiện.

## 12. stderr trong IDE, container và hệ thống thu thập log

### IDE

Các IDE Java có thể hiển thị stdout và stderr trong **cùng một console**, đôi khi dùng màu hoặc kiểu chữ khác nhau. Đây chỉ là **giao diện hiển thị**: không làm hai luồng trở thành một. Để xác nhận, có thể chạy chương trình trong shell với `1>` và `2>` như trên.

### Docker / Kubernetes

Nhiều nền tảng container thu thập cả stdout và stderr của tiến trình, rồi gửi tới driver/collector log. Ví dụ `docker logs` hoặc `kubectl logs` thường cho phép xem log do tiến trình trong container phát ra, nhưng cách lưu trữ, nhãn stream và chính sách giữ dữ liệu phụ thuộc môi trường.

Không mặc định rằng:

- Mọi container platform tự chuyển `stderr` thành severity ERROR.
- `stdout` không thể chứa WARN hoặc ERROR.
- Hai stream luôn được kết hợp theo đúng thứ tự thời gian.
- Mọi dòng đều được lưu lâu dài, không bị giới hạn kích thước hoặc cắt bớt.

Khi triển khai trên Kubernetes, log có thể được gom theo pod, container và instance. Nếu debug phân tán, nên có service name, request ID/trace ID hợp lệ và timestamp trong bản ghi. Tuy nhiên, **ghi trace ID vào log không tự tạo distributed trace**.

### Chương trình chạy nền

Service manager, task scheduler hoặc môi trường serverless có thể chuyển stderr sang journal, file, hệ thống thu thập hoặc giao diện giám sát riêng. “Tôi không thấy trên terminal” **không đồng nghĩa log không được phát**; cần kiểm tra đích mà môi trường chạy đang gắn với stream.

## 13. Những lưu ý khi dùng stderr trong production

**1. Đừng ghi bí mật.** Các dòng lỗi hoặc stack trace có thể chứa đường dẫn, SQL, header xác thực, token, API key hoặc dữ liệu người dùng. Không ghi toàn bộ request body chỉ vì đang debug. Một dòng lên stderr có thể được chuyển vào collector và tồn tại lâu.

**2. Đừng lạm dụng cho dòng thành công của CLI.** Nếu đầu ra chính sẽ được script đọc, hãy giữ stdout sạch. Một progress bar hoặc thông báo chẩn đoán có thể dùng stderr, nhưng nên cung cấp chế độ quiet/verbose phù hợp.

**3. Không tự động đóng stream chuẩn.** Tránh `System.err.close()` và `System.out.close()`. Các thành phần khác của ứng dụng có thể còn cần những luồng này. Chỉ đóng stream do mình tạo hoặc sở hữu.

**4. Đừng giả định flush bảo đảm dữ liệu bền vững.** `System.err.flush()` hoặc `PrintStream` flush bộ đệm trong phạm vi kiểm soát của nó, nhưng không cam kết log đã được lưu bền vững trên ổ đĩa/collector. Tiến trình có thể crash, collector có thể mất kết nối hoặc hàng đợi có thể đầy.

**5. Giữ một sự kiện thành một dòng khi có thể.** Trong ứng dụng đa luồng, nhiều lần `print(...)` rời rạc có thể dẫn tới các mảnh thông điệp xen kẽ; gọi `println(...)` với message hoàn chỉnh thường dễ đọc hơn. Stack trace vẫn có nhiều dòng và cần định dạng/collector phù hợp để không bị tách thành sự kiện mất ngữ cảnh.

**6. Chặn log injection.** Dữ liệu không đáng tin có thể chứa newline, tab hoặc ký tự điều khiển. Không chèn trực tiếp dữ liệu người dùng vào một dòng log với quyền tạo dòng giả. Có thể dùng structured logging, loại bỏ ký tự không an toàn và cơ chế escape phù hợp ở backend.

**7. Đừng tự đồng bộ mọi hoạt động trên System.err.** Nếu nhiều thread ghi log, logging framework quản lý sự kiện, level, format và sink sẽ phù hợp hơn các lệnh `println` rải rác. Tuy nhiên, framework cũng phải cấu hình đúng đích; một appender chậm có thể ảnh hưởng thông lượng.

**8. Có chính sách luồng nhất quán.** Nếu CLI quyết định `stdout=data` và `stderr=diagnostics`, hãy giữ quy tắc trong mọi nhánh thành công/thất bại. Nếu server dùng stdout cho tất cả structured logs, không cần ép ERROR sang stderr chỉ vì tên gọi của level.

## 14. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| `System.err.println` không xuất trong `out.txt` | stderr tách khỏi stdout; chỉ chuyển hướng `1>` | Dùng `2> err.txt` để bắt stderr |
| Log JUL `INFO` nằm trong file `err.txt` | `ConsoleHandler` mặc định xuất stderr | Đây là hành vi dự kiến, không có nghĩa INFO trở thành ERROR |
| `LOG.error(...)` xuất stdout | Backend/appender đặt `SYSTEM_OUT`/`System.out` | Kiểm tra config thực tế; level không quyết định stream |
| `LOG.info(...)` không thấy ở stderr | Logger hoặc handler lọc, provider/backend sai, stream chuyển hướng nơi khác | Kiểm tra logger level, handler/appender, file config và đích |
| Cùng exception xuất hai lần | Vừa gọi `printStackTrace` vừa logging, hoặc nhiều appender/handler | Chọn một pipeline và kiểm tra additivity/parent handlers |
| Chuyển hướng hai stream vào file nhưng thứ tự lạ | Buffering, nhiều thread hoặc thứ tự redirection | Đừng dựa vào thứ tự trộn; thêm timestamp/correlation ID |
| Exit code vẫn là 0 sau khi in ERROR | Chỉ in thông báo không thay trạng thái tiến trình | Đặt exit code chính xác, ví dụ `System.exit(2)` cho lỗi CLI |
| Không thấy stream trong IDE | IDE hợp nhất/ẩn stderr hoặc filter console | Chạy qua shell với `1>`, `2>` để đối chiếu |
| Test thay `System.setErr` khiến test khác lỗi | Thay đổi stream toàn cục, chưa khôi phục | Truyền `PrintStream` qua tham số hoặc thử appender test |
| Log bị cắt khi thu thập | Giới hạn độ dài sự kiện, multiline stack trace, collector | Kiểm tra pipeline end-to-end và cấu hình multiline |
| Chỉ INFO xuất nhưng FINE không xuất với JUL | Logger/ConsoleHandler ngưỡng INFO | Kiểm tra `isLoggable(Level.FINE)` và `handler.getLevel()` |
| File log không cập nhật dù stderr có bản ghi | Chỉ có Console appender/handler; không có file sink | Thêm appender/file handler có chính sách lưu phù hợp |

### Quy trình kiểm tra theo từng tầng

1. **API nguồn:** code đang gọi `System.err` trực tiếp, JUL, SLF4J hay Log4j2?
2. **Level:** sự kiện có bị lọc tại logger trước khi tạo không?
3. **Handler/appender:** đích được khai báo là `stderr`, `stdout` hay file?
4. **Filter và layout:** event có qua được đích không, có bị bỏ mất Throwable/context không?
5. **Process redirect:** shell/IDE/service manager chuyển `fd 1` và `fd 2` tới đâu?
6. **Collector:** nền tảng có gắn nhãn stream, cắt dòng hay áp retention khác nhau không?
7. **Exit status:** lệnh có trả mã lỗi chính xác, độc lập với dòng text stderr không?
8. **An toàn:** message và stack trace có làm lộ dữ liệu nhạy cảm hoặc tạo log trùng không?

## 15. Câu hỏi tự kiểm tra

**Câu 1:** Trong Java, lệnh nào ghi trực tiếp ra stderr?  
**Đáp án:** `System.err.println("...")` hoặc các phương thức tương tự trên `System.err`.

**Câu 2:** `System.err.println("ERROR")` có khiến chương trình tự trả exit code khác 0 không?  
**Đáp án:** Không. Ghi text và mã kết thúc tiến trình là hai việc khác nhau.

**Câu 3:** Với lệnh `java CliStderrDemo 21 > result.txt 2> diagnostic.txt`, giá trị `42` ở đâu?  
**Đáp án:** Trong `result.txt`. Dòng `INFO | Parsed integer` nằm trong `diagnostic.txt`.

**Câu 4:** JUL `ConsoleHandler` mặc định ghi stdout hay stderr?  
**Đáp án:** stderr. Nó có thể ghi bản ghi INFO/WARNING/SEVERE vào stderr nếu level và filter chấp nhận.

**Câu 5:** SLF4J `LOG.error(...)` có chắc chắn xuất stderr không?  
**Đáp án:** Không. Provider/backend và cấu hình handler/appender quyết định stream.

**Câu 6:** Vì sao `Throwable.printStackTrace()` dễ tạo log trùng?  
**Đáp án:** Nó in trực tiếp ra stderr; nếu cùng exception đã được truyền cho logger có console appender, cả hai đường có thể xuất cùng stack trace.

**Câu 7:** Muốn INFO/WARN qua stdout, ERROR/FATAL qua stderr với Log4j2, cần gì?  
**Đáp án:** Hai console appender với target `SYSTEM_OUT`/`SYSTEM_ERR` cùng filter phù hợp để không chồng lặp.

**Câu 8:** Vì sao không nên gọi `System.setErr(...)` trong mỗi unit test chạy song song?  
**Đáp án:** Nó thay stream toàn cục của JVM, có thể ảnh hưởng thread/test khác và không bảo đảm handler đã tồn tại tự đi theo stream mới.

**Câu 9:** Nếu một command có stderr nhưng exit code bằng 0, nó có thất bại chắc chắn không?  
**Đáp án:** Không. stderr có thể chứa cảnh báo hoặc tiến độ. Phải dựa vào hợp đồng chương trình và exit code thực tế.

**Ghi nhớ:** **stderr là một luồng xuất độc lập với stdout, không phải level ERROR.** Với CLI Java, giữ stdout cho kết quả và stderr cho chẩn đoán, đồng thời trả exit code hợp lý. Với framework logging, xác định rõ **logger → handler/appender → stream** và kiểm tra cấu hình backend trước khi kết luận một sự kiện sẽ được ghi vào đâu.
