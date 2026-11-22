# Console trong development — sử dụng logging hiệu quả khi phát triển Java

## 1. Vì sao console quan trọng khi phát triển?

Khi lập trình Java trên máy cá nhân, console của **IDE** hoặc **terminal** thường là nơi đầu tiên chúng ta nhìn thấy hoạt động của chương trình. Một log message xuất đúng thời điểm giúp trả lời các câu hỏi: luồng xử lý nào đã chạy, dữ liệu đầu vào đã qua kiểm tra ra sao, request gặp lỗi ở bước nào, chương trình đã thử lại bao nhiêu lần, và exception cụ thể là gì.

**Console logging** là việc gửi các sự kiện logging ra các luồng đầu ra chuẩn của tiến trình, thường là **standard output (stdout)** hoặc **standard error (stderr)**, thay vì bắt buộc phải ghi file hoặc gửi mạng. Trong **development**, console logging đặc biệt hữu ích vì nhanh, dễ xem, dễ lọc, gần với vòng lặp sửa code → chạy → quan sát → sửa.

Sau bài này, bạn có thể:

- Phân biệt **System.out**, **System.err** và **java.util.logging.ConsoleHandler**.
- Hiểu luồng Logger → LogRecord → Handler → Formatter và vì sao log DEBUG/FINE đôi khi không thấy trên console.
- Dùng **Java Util Logging (JUL)** để tạo log console rõ ràng trên Java 17+, quản lý level và Formatter.
- Biên dịch và chạy ví dụ độc lập, đọc chính xác nội dung ở stdout/stderr.
- Cấu hình console bằng **logging.properties** thay vì liên tục sửa code.
- Tổ chức việc quan sát log trong IntelliJ IDEA, Eclipse, VS Code và terminal mà không phụ thuộc vào một IDE cụ thể.
- Áp dụng cách đặt event name, request ID, level, exception, format, encoding và lọc khi debug.
- Tránh ghi log trùng, làm chậm ứng dụng, để lọt dữ liệu nhạy cảm hoặc nhầm console development với cơ chế kiểm toán bền vững.

**Phạm vi:** Bài thuộc nhóm **Console logging** trong **Java Core Logging**. Ví dụ chính dùng **JUL có sẵn trong JDK**, không yêu cầu Maven hay thư viện ngoài. Phần Log4j2/SLF4J được đề cập để chỉ rõ cách nhìn và cấu hình console ở những dự án sử dụng backend khác.

## 2. Console logging là gì và không phải là gì?

Ở mức hệ điều hành, chương trình thường có ba stream chuẩn:

| Stream | Vai trò | Java tương ứng |
| --- | --- | --- |
| **stdin** | Dữ liệu đầu vào của tiến trình | System.in |
| **stdout** | Đầu ra thông thường của chương trình | System.out |
| **stderr** | Thông báo lỗi hoặc thông tin chẩn đoán theo quy ước | System.err |

Console của IDE thường hiển thị stdout và stderr trong cùng một khung, đôi khi có màu khác nhau. Terminal cũng thường hiển thị cả hai lên màn hình. **Điều đó không có nghĩa hai stream là cùng một kênh.** Chúng có thể được redirect sang hai file riêng, được IDE gom lại hoặc được container/log collector thu thập theo cách khác.

Ví dụ Java tối giản:

~~~java
public class StandardStreamsDemo {
    public static void main(String[] args) {
        System.out.println("stdout: application ready");
        System.err.println("stderr: diagnostic example");
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 StandardStreamsDemo.java
java StandardStreamsDemo
~~~

Khi hiển thị trong một terminal thông thường, bạn thường thấy hai dòng. Nhưng thứ tự trộn giữa **stdout** và **stderr** không phải hợp đồng thứ tự tuyệt đối khi hai stream được buffer hoặc thu gom độc lập.

**System.out.println** và **System.err.println** là thao tác xuất trực tiếp. Chúng không tự thêm severity, tên Logger, thời điểm, context, cơ chế Filter hay routing của logging framework. Vì thế, dù hữu ích trong bài tập nhỏ, chúng **không thay thế** một kiến trúc logging cho ứng dụng nhiều module.

### 2.1. Console logging bằng logging API

Một luồng logging phổ biến:

~~~text
Java business code
    |
    v
Logger (level, logger name, optional filter)
    |
    v
LogRecord (severity, event, metadata, exception)
    |
    v
Console Handler / Console Appender
    |
    v
Formatter / Layout
    |
    v
System.err hoặc System.out
    |
    v
IDE console / terminal / log collector
~~~

**Tên gọi có thể khác nhau giữa backend:** JUL dùng **ConsoleHandler**, Log4j2 dùng **Console Appender**, Logback dùng **ConsoleAppender**. Cùng một ý tưởng “ghi ra console” nhưng API và cấu hình khác nhau. Không copy nguyên class/config của JUL sang Log4j2.

## 3. Chọn stdout hay stderr trong development?

Không có quy tắc Java bắt buộc rằng mọi INFO phải dùng stdout và mọi ERROR phải dùng stderr. Việc một log dùng luồng nào phụ thuộc **Handler/Appender và cấu hình**, không nhất thiết phụ thuộc level từng dòng.

### 3.1. Quy ước phổ biến

- **stdout:** đầu ra thông thường hoặc luồng log được hệ thống thu gom theo một chính sách thống nhất.
- **stderr:** lỗi, cảnh báo hoặc kênh chẩn đoán được định tuyến riêng nếu ứng dụng/công cụ chọn như vậy.
- **JUL ConsoleHandler:** **mặc định ghi vào System.err**, kể cả khi event là INFO.
- **Log4j2 Console Appender:** có thể chọn **SYSTEM_OUT** hoặc **SYSTEM_ERR** thông qua cấu hình target.

Do đó, nếu dùng **JUL ConsoleHandler**, lời gọi **logger.info(...)** cũng xuất qua stderr. **Không nên suy ra “stderr nghĩa là mọi record đều ERROR”.** Severity nằm trong nội dung LogRecord hoặc trường level của structured event.

| Hành vi | Có nghĩa gì? |
| --- | --- |
| System.out.println("hello") | Xuất text trực tiếp ra stdout; không có level |
| System.err.println("hello") | Xuất text trực tiếp ra stderr; không tự gán ERROR |
| JUL Logger.info(...) + ConsoleHandler | Có thể xuất một INFO record ra stderr |
| Log4j2 INFO + Console target SYSTEM_OUT | Có thể xuất INFO record ra stdout |
| Log4j2 ERROR + Console target SYSTEM_OUT | Vẫn có thể xuất ERROR ra stdout theo cấu hình |

### 3.2. Vì sao người dùng thấy log “lộn xộn” trên IDE?

Khi IDE gom stdout/stderr vào một khung, thứ tự hiển thị có thể khác thứ tự thực tế của lệnh gọi. Một vài nguyên nhân:
- Hai stream có buffering và lịch nhận dữ liệu riêng.
- IDE nhận/đọc output qua các luồng khác nhau.
- Chương trình chạy đa luồng, nhiều Logger phát sự kiện đồng thời.
- Framework xử lý log bất đồng bộ hoặc định tuyến qua queue.
- Test runner, Maven, Gradle hoặc container chèn output của chính công cụ vào cùng console.

Nếu cần chứng minh thứ tự nghiệp vụ, ghi **event name**, **timestamp**, **requestId** và thông tin liên quan; không coi vị trí hai dòng stdout/stderr trong cửa sổ IDE là bằng chứng chắc chắn về quan hệ nhân-quả.

## 4. Java Util Logging và ConsoleHandler

**java.util.logging.ConsoleHandler** là một Handler có sẵn trong JDK. Theo API Java 17:

- Nó kế thừa **StreamHandler**.
- Nó ghi record ra **System.err**.
- Formatter mặc định là **SimpleFormatter**.
- Level mặc định của **ConsoleHandler** là **INFO**, trừ khi cấu hình khác.
- Nó có các property cấu hình **level**, **filter**, **formatter** và **encoding**.
- **close()** flush nhưng không đóng **System.err** toàn cục.

Đây là lý do khi bạn chỉ viết:

~~~java
import java.util.logging.Logger;

Logger logger = Logger.getLogger("demo.service");
logger.fine("cache detail");
logger.info("service started");
~~~

thì không nên khẳng định chắc chắn sẽ thấy FINE: Logger có effective level riêng, các Handler cũng có level riêng. Hai dòng ở trên là mảnh code minh họa trong phương thức, chưa phải một lớp có main().

### 4.1. Logger và Handler đều có ngưỡng

Trong JUL, một record muốn được ghi qua một Handler thường phải:

1. Được Logger chấp nhận theo effective level và Logger Filter.
2. Được chuyển tới Handler đó (được gắn trực tiếp hoặc qua parent handlers).
3. Đạt level/filter của Handler.
4. Được Handler và Formatter xử lý, và stream còn khả dụng.

Giả sử không có Filter bổ sung:

| Logger level | ConsoleHandler level | INFO | FINE | WARNING |
| --- | --- | --- | --- | --- |
| INFO | INFO | Có | Không | Có |
| FINE | INFO | Có | Không | Có |
| FINE | FINE | Có | Có | Có |
| ALL | WARNING | Không | Không | Có |
| OFF | ALL | Không | Không | Không |

“Có” trong bảng là **đủ điều kiện qua ngưỡng level**, không có nghĩa chắc chắn đã ghi bền vững. Nếu ConsoleHandler không được gắn, bị Filter loại hoặc stderr bị chuyển đi nơi khác, kết quả quan sát sẽ khác.

**Câu hỏi thực hành:** đã gọi **logger.setLevel(Level.FINE)** nhưng không thấy FINE? Hãy kiểm tra **ConsoleHandler.getLevel()** và các Filter trước khi tăng level toàn hệ thống.

### 4.2. Logger cha và dòng log trùng

Logger có thể chuyển record lên Handler của cha. Nếu bạn tự gắn ConsoleHandler cho Logger con nhưng vẫn giữ **useParentHandlers=true**, record có thể được xử lý bởi cả Handler của con lẫn Handler của root. Kết quả: một dòng xuất hai lần, có thể với format khác nhau.

Nếu cố ý tạo pipeline riêng trong bài tập, có thể dùng:

~~~java
logger.setUseParentHandlers(false);
logger.addHandler(consoleHandler);
~~~

Đây là mã minh họa trong phương thức có hai biến đã khởi tạo. **Chỉ tắt parent handlers khi đã có Handler khác**. Nếu tắt forwarding mà Logger không có Handler, event có thể không còn đích xuất.

## 5. Ví dụ Java 17 chạy độc lập: tách stdout và stderr

Ví dụ này chứng minh bốn điều:

1. **System.out.println** ghi ra stdout.
2. **JUL ConsoleHandler** ghi ra stderr, dù level là INFO.
3. **Logger ở FINE nhưng Handler ở INFO** làm một event FINE bị loại.
4. Khi đổi Handler sang **FINE**, bản ghi chẩn đoán xuất hiện ngay, không phải tạo lại Logger.

Chương trình sử dụng **chỉ JDK**, không cần dependency ngoài. Formatter đơn giản được viết ngay trong ví dụ để output dễ kiểm tra và không phụ thuộc timestamp hoặc kiểu định dạng mặc định.

Tạo file **DevConsoleLoggingDemo.java**:

~~~java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class DevConsoleLoggingDemo {
    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.checkout");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.FINE);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.INFO);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                String result = record.getLevel().getName() + "|"
                        + record.getLoggerName() + "|" + formatMessage(record);
                if (record.getThrown() != null) {
                    result += "|error=" + record.getThrown().getClass().getSimpleName();
                }
                return result + System.lineSeparator();
            }
        });
        logger.addHandler(console);
        try {
            System.out.println("stdout|application booted");
            logger.fine("event=checkout.validation_detail");
            logger.log(Level.INFO, "event=checkout.started cartId={0}", "CART-42");
            logger.log(Level.WARNING, "event=checkout.coupon_rejected",
                    new IllegalArgumentException("coupon expired"));

            console.setLevel(Level.FINE);
            logger.fine("event=checkout.diagnostic_enabled");
        } finally {
            logger.removeHandler(console);
            console.flush();
            console.close();
        }
    }
}
~~~

### 5.1. Biên dịch và chạy

~~~bash
javac --release 17 -encoding UTF-8 DevConsoleLoggingDemo.java
java DevConsoleLoggingDemo
~~~

Khi chạy trên terminal thông thường, bạn có thể nhìn thấy bốn dòng sau, nhưng **thứ tự tương đối giữa stdout và stderr có thể thay đổi** nếu các stream được thu gom độc lập.

**stdout thực tế đã kiểm chứng:**

~~~text
stdout|application booted
~~~

**stderr thực tế đã kiểm chứng:**

~~~text
INFO|demo.checkout|event=checkout.started cartId=CART-42
WARNING|demo.checkout|event=checkout.coupon_rejected|error=IllegalArgumentException
FINE|demo.checkout|event=checkout.diagnostic_enabled
~~~

Trong quá trình kiểm chứng, chương trình đã được **javac --release 17** biên dịch và chạy thành công; đầu ra được đọc **riêng** từ stdout và stderr để tránh nhầm hai luồng.

### 5.2. Phân tích từng bước

**Bước 1 — Thiết lập Logger.** Logger tên **demo.checkout** được đặt ngưỡng FINE. **setUseParentHandlers(false)** ngăn forwarding lên root Handler để tránh xuất trùng hoặc format bổ sung.

**Bước 2 — Tạo ConsoleHandler.** Handler được đặt level INFO nên chỉ nhận record INFO trở lên. Formatter tạo dòng kiểu **LEVEL|logger|message**, dùng **formatMessage(record)** để áp dụng tham số JUL theo cú pháp MessageFormat **{0}**.

**Bước 3 — In stdout.** **System.out.println("stdout|application booted")** không đi qua Logger, không có level và không tự mang correlation fields. Đây chỉ là một thông điệp xuất trực tiếp.

**Bước 4 — Phát FINE đầu tiên.** **logger.fine("event=checkout.validation_detail")** đủ level ở Logger, nhưng Handler đang INFO nên không có dòng tương ứng trong stderr.

**Bước 5 — Phát INFO và WARNING.** INFO được Formatter thay **{0}** bằng **CART-42**. WARNING có Throwable, nên Formatter thêm **error=IllegalArgumentException**.

**Bước 6 — Hạ ngưỡng Handler.** **console.setLevel(Level.FINE)** cho phép dòng **event=checkout.diagnostic_enabled** xuất ra stderr. Đây là cách kiểm tra vai trò độc lập của Logger và Handler.

**Bước 7 — Dọn tài nguyên.** Sau khi xong, code tách Handler, flush và close. ConsoleHandler close không đóng System.err toàn cục. Trong ứng dụng server, không đóng Handler chia sẻ trong mỗi request; vòng đời Handler thuộc ứng dụng hoặc logging backend.

### 5.3. Giới hạn cố ý của demo

Formatter ở đây chỉ in **tên class của Throwable**, không in full stack trace. Đây là lựa chọn để có stdout/stderr **chính xác, dễ đối chiếu** trong bài học. Trong tình huống điều tra lỗi thực tế, bạn thường cần exception cause và stack trace; hãy dùng SimpleFormatter hoặc Formatter/Layout hỗ trợ chúng, và đảm bảo dữ liệu nhạy cảm được kiểm soát.

Đoạn demo tạo Handler bằng code; trong một ứng dụng lớn nên cấu hình qua framework hoặc file properties để không phải chỉnh mã nghiệp vụ mỗi lần thay level. Formatter tự viết trong ví dụ không phải một encoder JSON production và không xử lý đầy đủ log injection.

## 6. Redirect và quan sát hai stream trong terminal

Sử dụng redirect giúp bạn biết chắc **dòng nào thuộc stdout và dòng nào thuộc stderr**.

### 6.1. Linux/macOS shell

~~~bash
java DevConsoleLoggingDemo 1> app.stdout 2> app.stderr
~~~

- **1>** redirect file descriptor stdout.
- **2>** redirect file descriptor stderr.
- Sau lệnh, **app.stdout** có dòng **stdout|application booted**.
- **app.stderr** có ba dòng INFO/WARNING/FINE từ ConsoleHandler.

Muốn gom cả hai stream vào một file (nhưng không đảm bảo thứ tự thời gian hoàn hảo giữa các nguồn) có thể dùng:

~~~bash
java DevConsoleLoggingDemo > combined.log 2>&1
~~~

Muốn vừa xem vừa lưu, trong Bash có thể dùng:

~~~bash
java DevConsoleLoggingDemo 2>&1 | tee combined.log
~~~

**Cẩn thận:** redirect hai stream vào một dòng hiển thị không làm chúng tự có một total ordering chuẩn. Với nhiều thread hoặc buffer, phải dùng event timestamps/IDs để suy luận trình tự xử lý.

### 6.2. Windows PowerShell

Ví dụ chuyển stream ra hai file:

~~~powershell
java DevConsoleLoggingDemo 1> app.stdout 2> app.stderr
~~~

PowerShell có cơ chế xử lý riêng với native command và error streams; phiên bản PowerShell/console encoding khác nhau có thể làm biểu diễn của stderr khi redirect khác với byte gốc. Nếu đang điều tra vấn đề encoding hoặc cần giữ nguyên byte output, hãy kiểm thử trên đúng PowerShell version, hoặc dùng công cụ/process API có khả năng thu riêng các stream.

Có thể xem file bằng:

~~~powershell
Get-Content .\app.stdout
Get-Content .\app.stderr
~~~

**Windows cmd.exe**, PowerShell và Bash không hoàn toàn giống nhau về quoting, escaping và semantics của redirect. Không copy nguyên cú pháp của một shell sang shell khác mà không kiểm tra.

### 6.3. Tìm log bằng grep, findstr hoặc Select-String

**Linux/macOS**:

~~~bash
grep 'event=checkout' app.stderr
grep 'WARNING' app.stderr
~~~

**PowerShell**:

~~~powershell
Select-String -Path .\app.stderr -Pattern 'event=checkout'
Select-String -Path .\app.stderr -Pattern 'WARNING'
~~~

**Lợi ích khi dùng event key:** nếu mọi thành công của checkout dùng **event=checkout.started**, câu văn người đọc có thể thay đổi nhưng điều kiện tìm kiếm vẫn có một mã ổn định. Nếu chỉ grep cả câu tự nhiên, thay đổi wording hoặc bản dịch có thể làm truy vấn thất bại.

## 7. Cấu hình console bằng logging.properties

Trong dự án JUL, thay đổi level hoặc Formatter bằng file cấu hình có thể dễ duy trì hơn việc gọi **logger.setLevel** ở nhiều vị trí.

Ví dụ **logging.properties**:

~~~properties
# Root Logger
.level = INFO

# Output through JUL ConsoleHandler
handlers = java.util.logging.ConsoleHandler
java.util.logging.ConsoleHandler.level = INFO
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter
java.util.logging.ConsoleHandler.encoding = UTF-8

# Enable deeper diagnostics for one package
com.example.checkout.level = FINE

# Format: level|logger|message|optional throwable
java.util.logging.SimpleFormatter.format = %4$s|%3$s|%5$s%6$s%n
~~~

Khi khởi động ứng dụng đã được biên dịch:

~~~bash
java -Djava.util.logging.config.file=logging.properties -cp out com.example.Main
~~~

Lệnh này **minh họa** cách chỉ định file cấu hình. Nó giả định class **com.example.Main** đã tồn tại trong thư mục out. Nó **không phải lệnh chạy demo mục 5**, bởi demo đó tự tạo Handler và Formatter bằng code.

**Điểm đáng lưu ý:**
- **.level=INFO** đặt root Logger ở mức INFO.
- **ConsoleHandler.level=INFO** khiến console không hiện FINE dù Logger **com.example.checkout** có level FINE.
- Muốn FINE của checkout xuất ra, có thể đổi **java.util.logging.ConsoleHandler.level=FINE** trong cấu hình.
- **ConsoleHandler.encoding=UTF-8** giúp chọn encoding tại Handler; terminal/IDE/collector vẫn cần giải mã đúng.
- **SimpleFormatter.format** dùng cú pháp **java.util.Formatter**. Trong tài liệu JDK, **%3$s** là Logger name, **%4$s** là level, **%5$s** là message và **%6$s** là exception/stack trace nếu có.
- Chỉ định file bằng system property **lúc JVM khởi động**. Thay file trên ổ đĩa không có nghĩa JUL tự reload vào ứng dụng đang chạy.

### 7.1. Một cấu hình FINE dễ gây hiểu lầm

~~~properties
com.example.checkout.level = FINE
java.util.logging.ConsoleHandler.level = INFO
~~~

Nhìn vào phần đầu, bạn có thể nghĩ console sẽ xuất FINE; thực ra ngưỡng Handler đang loại FINE. Vì vậy, phải kiểm tra **cả Logger effective level lẫn Handler level**.

Trong JUL, Logger con có thể có level riêng khác root. Khi record đã qua ngưỡng của Logger con và được forward đến parent Handlers, ngưỡng của root Logger không nhất thiết được kiểm tra lại như lời gọi log mới; ngưỡng của Handler ở root vẫn được áp dụng.

### 7.2. Nạp lại cấu hình trong development

Việc chỉnh file rồi **restart ứng dụng** là cách đơn giản, ổn định. JUL có API **LogManager.readConfiguration** để nạp lại, nhưng thao tác này có thể reset config, tháo/đóng Handler đã gắn. Khi hot reload, phải có kế hoạch tái tạo/kiểm chứng pipeline logging; không gọi readConfiguration trong mỗi request.

Nếu đang dùng Spring Boot, Logback hoặc Log4j2, cách đặt mức level và reload sẽ thuộc hệ cấu hình được framework/backend đó thực sự sử dụng. Không assume logging.properties của JUL luôn điều khiển Logback hoặc Log4j2.

## 8. Console logging trong IDE

Vòng lặp development điển hình:

~~~text
Edit code
   |
   v
Run / Debug
   |
   v
Quan sát console (event, level, requestId, exception)
   |
   v
Đặt breakpoint / test giả thuyết
   |
   v
Sửa code hoặc mức logging
   |
   v
Run again
~~~

Trong IntelliJ IDEA, Eclipse hoặc VS Code, console của Run/Debug thường được gắn với tiến trình Java vừa chạy. Cách biểu diễn, filter và tab khác nhau theo phiên bản IDE, nhưng một số nguyên tắc chung luôn đúng:

- Xác nhận **đúng tiến trình/configuration** đang chạy. Nhiều chương trình Java hoặc test runner có thể có console riêng.
- Xem **stdout và stderr** có cùng khung hay không; IDE có thể dùng màu khác nhau nhưng không phải mọi màu đều là severity của log.
- Quan sát **thời điểm xuất log** trước/sau một breakpoint; debugger có thể tạm dừng một thread trong khi thread khác vẫn ghi.
- Nếu log bỗng biến mất, kiểm tra **Logger/Handler level**, Filter, đích console và việc cấu hình mới có thực sự được nạp hay không.
- Nếu console bị lấp bởi rất nhiều dòng, tăng khả năng tìm kiếm bằng event key hoặc requestId thay vì chỉ mở rộng bộ đệm console.

### 8.1. Console không thay thế debugger

Console giúp thấy chuỗi sự kiện và failure path; debugger giúp xem biến, call stack, trạng thái thread và ranh giới phương thức. Hai công cụ bổ trợ nhau:

| Bạn cần biết | Công cụ phù hợp |
| --- | --- |
| Request nào lỗi trong nhiều request | Log có requestId / traceId |
| Giá trị biến tại một breakpoint | Debugger |
| Thứ tự các event và retry | Log event + timestamps |
| Vì sao một nhánh được chọn | Debugger, test, log được đặt đúng chỗ |
| Lỗi xảy ra ở thread nào | Log thread field + debugger thread view |
| Lỗi lặp theo thời gian dài | Log storage/collector hoặc lưu file phù hợp |

Nếu một vấn đề chỉ xuất hiện trong production, debugger local có thể không tái hiện được. Khi đó structured logs, metrics và traces có vai trò lớn hơn; development logging cần chuẩn bị event/fields có thể dùng được cả trong môi trường khác.

## 9. Đặt message sao cho console dễ đọc

Một console log hữu ích không cần dài nhưng phải có thông tin để hành động. Ví dụ:

**Chưa tốt:**

~~~text
Started
OK
Error
Something failed
Retrying...
~~~

**Tốt hơn:**

~~~text
INFO event=checkout.started cartId=CART-42
WARNING event=checkout.coupon_rejected reasonCode=expired
INFO event=checkout.completed cartId=CART-42 durationMs=35
~~~

### 9.1. Event key và tham số

Chọn **mã sự kiện ổn định** như **checkout.started**, **checkout.completed**, **payment.retry**. Dữ liệu biến thiên nằm ở tham số/structured fields.

Trong JUL, tham số với **Formatter.formatMessage(LogRecord)** thường sử dụng **MessageFormat** và placeholder **{0}**, **{1}**:

~~~java
logger.log(Level.INFO, "event=checkout.started cartId={0}", "CART-42");
~~~

Đây là đoạn code minh họa trong phương thức đã có biến logger và import. Nếu dùng **SLF4J/Log4j2 API**, cú pháp parameterization phổ biến là **{}**, không phải **{0}**. Không trộn các quy ước rồi cho rằng mọi backend tự hiểu giống nhau.

**Dùng parameterization giúp format ổn định**, nhưng các biểu thức đối số vẫn được Java đánh giá trước lời gọi logger. Nếu việc tính một diagnostic value tốn kém, cân nhắc **logger.isLoggable(Level.FINE)** trong JUL hoặc cơ chế lazy logging của backend tương ứng.

### 9.2. Level phải phản ánh ý nghĩa

| Mức JUL | Ví dụ ở development |
| --- | --- |
| SEVERE | Tác vụ thất bại nghiêm trọng cần xử lý |
| WARNING | Retry, fallback, input không hợp lệ đáng chú ý |
| INFO | Thành phần khởi động, một operation thành công cần quan sát |
| CONFIG | Thông tin cấu hình được phép ghi |
| FINE | Quyết định nội bộ phục vụ debug |
| FINER, FINEST | Chi tiết rất sâu; bật trong phạm vi hẹp |

Bật **FINEST** toàn ứng dụng có thể tạo rất nhiều output và làm mất khả năng đọc dòng quan trọng. Khi điều tra một module, bật logging chi tiết ở package cụ thể, xác nhận Handler level và giảm level sau khi kết thúc.

### 9.3. Có nên in cả object?

Đừng mặc định **toString()** của object là an toàn hoặc rẻ. Nó có thể chứa password, token, email, session cookie, thông tin cá nhân, hoặc trả chuỗi quá lớn. Khi cần debug, chọn trường phù hợp, rút gọn nội dung và tránh gọi các operation phụ chỉ để format log.

**Một log line đẹp nhưng làm lộ dữ liệu hoặc thay đổi thời gian thực thi quá nhiều không phải log tốt.**

## 10. Exception trên console

Khi xảy ra lỗi, việc chỉ ghi **"Something went wrong"** thường không đủ. Trong JUL, bạn có thể truyền Throwable qua overload:

~~~java
try {
    performCheckout();
} catch (IllegalStateException ex) {
    logger.log(Level.WARNING, "event=checkout.failed", ex);
}
~~~

Đây là đoạn minh họa cần **performCheckout()** và biến **logger** đã có trong phương thức; nó chưa phải chương trình độc lập. Nếu Handler dùng **SimpleFormatter**, Throwable có thể được biểu diễn cùng stack trace, giúp xác định call stack.

**Một số lưu ý:**
- Chọn level theo mức độ ảnh hưởng, không phải mọi exception đều là SEVERE.
- Ghi exception ở **điểm xử lý có ý nghĩa**, tránh log cùng một exception ở repository, service và controller rồi đếm nhầm thành nhiều lỗi.
- Không nuốt Throwable làm mất nguyên nhân; nhưng cũng không xuất toàn bộ stack trace cho người dùng cuối.
- Exception message của thư viện có thể chứa URL, query, payload, token hoặc dữ liệu nhạy cảm; phải kiểm soát trước khi gửi tới sink.
- Một stack trace là nhiều dòng **của một event**. Khi gom log bằng grep hoặc collector, cần format/encoding để tránh nhầm các dòng con thành những sự kiện độc lập.

Demo mục 5 cố ý chỉ in **error type** để kết quả chính xác. Muốn xem stack trace trong thực tế, dùng Formatter/Layout phù hợp thay vì viết một formatter bỏ qua mọi chi tiết lỗi.

## 11. Console ở dự án dùng Log4j2 và SLF4J

Trong một số dự án, mã gọi SLF4J hoặc Log4j API thay vì JUL. **Console vẫn là một destination**, nhưng cấu hình do backend quyết định.

### 11.1. Ví dụ Console Appender của Log4j2

Một cấu hình XML minh họa:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
  <Appenders>
    <Console name="DEV_CONSOLE" target="SYSTEM_OUT">
      <PatternLayout pattern="%d{HH:mm:ss.SSS} %-5level [%t] %logger{1} - %msg%n"/>
    </Console>
  </Appenders>
  <Loggers>
    <Logger name="com.example.checkout" level="DEBUG" additivity="false">
      <AppenderRef ref="DEV_CONSOLE"/>
    </Logger>
    <Root level="INFO">
      <AppenderRef ref="DEV_CONSOLE"/>
    </Root>
  </Loggers>
</Configuration>
~~~

Đây là **file cấu hình Log4j2**, không phải code Java độc lập. Nó chỉ có hiệu lực khi Log4j2 implementation/provider phù hợp được nạp và file được phát hiện. Console Appender ở đây ghi **SYSTEM_OUT**, khác mặc định **System.err** của JUL ConsoleHandler. LoggerConfig checkout được đặt DEBUG; **additivity=false** ngăn sự kiện đã được xử lý tại đó chuyển thêm tới Root Appender.

**Không copy nguyên XML sang JUL logging.properties**: hai hệ thống dùng API và định dạng cấu hình khác nhau. Nếu ứng dụng dùng SLF4J facade, cần kiểm tra provider/backend được chọn (Logback, Log4j2 hoặc khác) trước khi thay đổi console logging.

### 11.2. Màu sắc log có cần thiết không?

Màu theo severity có thể giúp đọc console development nhanh hơn; một số backend/IDE hỗ trợ highlight và ANSI color. Nhưng:

- Không phải terminal/IDE nào cũng hỗ trợ ANSI giống nhau.
- ANSI escape codes có thể xuất hiện nguyên trong file khi redirect nếu không vô hiệu hóa styling phù hợp.
- Dữ liệu lưu lâu dài hoặc pipeline máy đọc nên có schema rõ, không phụ thuộc màu.
- Màu hiển thị không thay thế level/field của log.

Có thể bật màu trong môi trường development khi đã kiểm tra khả năng tương thích; đừng dựa vào màu để khẳng định một record là ERROR.

## 12. Console trong development và production

**Console không chỉ dùng cho development.** Trong môi trường container/Kubernetes hoặc một số nền tảng cloud, ứng dụng production thường ghi log ra stdout/stderr để runtime/log collector thu thập. Sự khác nhau là **chính sách cấu hình và vận hành**, không phải console tự nhiên trở nên sai ở production.

| Vấn đề | Development | Production |
| --- | --- | --- |
| Mục đích | Phản hồi nhanh khi sửa/test | Quan sát vận hành và điều tra sự cố |
| Level thường dùng | INFO, bật DEBUG/FINE khi cần | INFO/WARN/ERROR có giới hạn; debug có kiểm soát |
| Format | Dễ đọc cho người | Thường cần schema, timestamp, IDs, parse được |
| Nơi xem | IDE/terminal | Dashboard, collector, log search |
| Lưu trữ | Có thể tạm thời | Retention, quyền truy cập, chi phí rõ ràng |
| Khối lượng | Chấp nhận verbose trong phạm vi hẹp | Phải kiểm soát throughput, sampling, queue |
| Dữ liệu nhạy cảm | Vẫn phải bảo vệ | Bắt buộc quản lý chặt hơn theo policy |

**Đừng dựa vào console scrollback như một kho lưu trữ bền vững.** IDE có thể giới hạn số dòng hoặc xóa khi restart; terminal buffer không thay thế retention. Nếu log cần được giữ, cần file, collector hoặc nền tảng log với chính sách rõ ràng.

### 12.1. Console và container

Ứng dụng container thường ghi console để log collector bên ngoài ứng dụng thu nhận. Đường đi minh họa:

~~~text
Java application
   |
   +--> stdout / stderr
             |
             v
       Container runtime
             |
             v
      Log collection agent
             |
             v
      Central log backend
~~~

Không mặc định rằng **stderr luôn thành lỗi ở backend**. Runtime có thể gắn metadata của stream, còn severity thực sự thường nằm trong trường level hoặc nội dung event. Xây dựng schema để hệ thống tìm kiếm không phải suy đoán level từ stream name.

## 13. Encoding và tiếng Việt trên console

Java String hỗ trợ Unicode, nhưng đầu ra vẫn có thể bị lỗi dấu nếu charset ở các mắt xích không tương thích.

Ví dụ câu:

~~~text
INFO event=order.created message=Đơn hàng đã được tạo
~~~

Có thể trở thành ký tự lỗi nếu source file, JVM console encoding, terminal, IDE hoặc collector giải mã sai.

**Các bước kiểm tra:**
1. Lưu source và catalog bằng **UTF-8**.
2. Khi compile nguồn Java có ký tự có dấu, dùng **javac -encoding UTF-8** để rõ ràng về charset source.
3. Với JUL ConsoleHandler, cấu hình **java.util.logging.ConsoleHandler.encoding=UTF-8** khi phù hợp; vẫn kiểm tra terminal có hỗ trợ UTF-8.
4. Với những backend khác, cấu hình charset trong encoder/appender theo API của chúng.
5. Kiểm tra riêng stdout và stderr nếu chỉ một luồng bị lỗi hiển thị.
6. Không coi lỗi font hiển thị là chắc chắn dữ liệu gốc đã bị hỏng; có thể dữ liệu bytes đúng nhưng console render sai.

**Lưu ý:** **System.out.println** và **ConsoleHandler** là hai đường phát khác nhau, nên cấu hình encoding của ConsoleHandler không tự điều khiển mọi lệnh System.out.println trong ứng dụng.

## 14. Bảo mật và chất lượng log khi debug

Development thường khiến lập trình viên muốn ghi “toàn bộ request” để tìm lỗi. Đây là thói quen rủi ro:

- Không log **mật khẩu, OTP, access token, refresh token, cookie phiên, API key, private key**.
- Không log toàn bộ payload chứa dữ liệu cá nhân hoặc thông tin thanh toán.
- Không gửi những secret đó vào DEBUG/FINE rồi cho rằng “production không bật” là đủ; mức log có thể thay đổi.
- Không để raw input chứa newline/ký tự điều khiển tạo dòng giả trong console (**log injection**).
- Không để **toString()** của đối tượng tự in những trường bí mật ngoài dự kiến.
- Bật log chi tiết trong phạm vi hẹp và giới hạn thời gian; giảm ngưỡng sau khi điều tra.
- Đối với ngoại lệ, cân nhắc message/stack trace có thể chứa endpoint/query/token.

**Khuyến nghị:** sử dụng mã event và các field đã được chọn lọc, ví dụ **event=auth.login_failed reasonCode=invalid_credentials**, thay vì in username/password hay nguyên request body.

### 14.1. Tác động hiệu năng

Console I/O có thể chậm, đặc biệt khi ghi hàng nghìn dòng trong vòng lặp hoặc khi IDE/terminal bị quá tải. Những thao tác logging đồng bộ có thể làm tăng latency và khiến kết quả benchmark bị sai lệch.

Ví dụ nên tránh trong hot path:

~~~java
for (int i = 0; i < 1_000_000; i++) {
    System.out.println("processed=" + i);
}
~~~

Đây là đoạn minh họa, chưa phải chương trình độc lập. Nếu muốn đo throughput một thuật toán, không nên so sánh performance khi đang in một triệu dòng lên console rồi kết luận thuật toán chậm. Log ở mức phù hợp, kiểm soát tần suất và dùng metrics/benchmark chuyên dụng.

**Async logging** có thể cải thiện một số workload, nhưng cũng có giới hạn queue, dropped records, backpressure và shutdown. Không mặc định async luôn nhanh hơn hoặc luôn bảo toàn mọi event.

## 15. Console logging trong unit test và integration test

Log có ích khi test thất bại, nhưng **không nên biến text console thành output hợp đồng duy nhất của unit test** trừ khi mục tiêu test chính là formatter/handler.

Một số chiến lược:

- **Test nghiệp vụ:** assert kết quả nghiệp vụ, trạng thái và exception; dùng log để chẩn đoán, không thay assertion bằng “có một dòng INFO”.
- **Test logging policy:** gắn một Handler kiểm thử (in-memory) để kiểm tra event, level và parameters thay vì phụ thuộc IDE console.
- **Integration test:** phát một event mẫu, xác nhận sink và collector thực sự nhận event; kiểm tra không duplicate.
- **Test stream:** nếu cần kiểm tra stdout/stderr, tạo tiến trình con và thu hai stream riêng như demo đã làm; tránh thay **System.setOut** ở một suite test chạy song song.
- **Test encoding:** dùng ký tự tiếng Việt, dấu nháy, newline và ký tự điều khiển để kiểm tra formatter/encoder.

Vì Logger và Handler có thể là hạ tầng chung trong một JVM, test gắn/loại Handler phải khôi phục cấu hình để không làm ảnh hưởng test khác. Gọi **LogManager.reset()** trong mỗi unit test có thể phá logging của cả test runner.

## 16. Chẩn đoán các sự cố console thường gặp

### 16.1. “Tôi đã bật FINE nhưng không thấy dòng nào”

Xem lần lượt:

1. Logger name có đúng với cấu hình không?
2. Effective level của Logger có cho phép FINE? **logger.isLoggable(Level.FINE)** trả gì?
3. **ConsoleHandler.getLevel()** có vẫn là INFO?
4. Có Filter từ chối record không?
5. ConsoleHandler có thật sự gắn với Logger hoặc ancestor?
6. **useParentHandlers** có làm record không đi tới root Handler?
7. Ứng dụng dùng JUL hay runtime thực ra là SLF4J/Log4j2/Logback?
8. Console đang mở có phải của đúng tiến trình vừa chạy?

### 16.2. “INFO hiện trên stderr, vậy ứng dụng đã gặp lỗi?”

Không nhất thiết. **JUL ConsoleHandler ghi System.err mặc định**, kể cả INFO. Hãy đọc **Level của record**, không dùng tên stream thay cho severity.

### 16.3. “Một log xuất hai lần”

Kiểm tra **logger.getHandlers()**, parent handlers, Logger root, bridge và việc IDE/test runner có in lại output. Nếu đã gắn Handler riêng mà Logger vẫn forward lên root, hai đích có thể cùng ghi record.

### 16.4. “Các dòng không đúng thứ tự”

Xác định có phải hai stream riêng đang được IDE/terminal gom lại không, có xử lý đa luồng/async không. Gắn timestamp và requestId; không dựa vào thứ tự màu trong console để suy ra thứ tự business.

### 16.5. “Log mất khi chương trình thoát”

Kiểm tra Handler buffer/flush, async queue và vòng đời shutdown. ConsoleHandler của JUL thực hiện flush khi publish nhưng một pipeline khác có thể buffer. Khi ghi dữ liệu có yêu cầu độ bền, phải dùng cơ chế lưu trữ phù hợp chứ không phụ thuộc terminal buffer.

### 16.6. “Tiếng Việt hiện toàn ký tự lỗi”

Kiểm tra source encoding, javac encoding, Handler encoding, stdout/stderr encoding, terminal/IDE charset và collector. Test với một câu tiếng Việt cố định để khoanh vùng.

### 16.7. “Console quá nhiều dòng”

Giảm level của package không liên quan, lọc bằng event key/requestId, bỏ log trong hot loop và ưu tiên mỗi event có giá trị. Không dùng OFF bừa bãi trên những sự kiện lỗi quan trọng.

### 16.8. “Tôi thấy stack trace nhưng không thấy dòng log đầu”

Có thể Formatter nhiều dòng, IDE filter, output bị giới hạn, hoặc collector phân tách sai. Đảm bảo format exception và chính sách multiline phù hợp, kiểm tra đầu ra thô trước khi điều chỉnh parser.

## 17. Workflow thực hành cho một lỗi development

Giả sử checkout thỉnh thoảng từ chối coupon dù người dùng nghĩ coupon hợp lệ.

**Bước 1 — Đặt event ở ranh giới quan trọng.**

~~~text
event=checkout.started cartId=CART-42
event=coupon.validating couponType=PROMO
event=checkout.coupon_rejected reasonCode=expired
~~~

Không ghi raw coupon code nếu nó nhạy cảm; ghi reasonCode đã chuẩn hóa.

**Bước 2 — Bật log chi tiết chỉ ở package checkout.** Chỉnh level Logger và ConsoleHandler nếu dùng JUL, hoặc LoggerConfig/Appender nếu dùng backend khác.

**Bước 3 — Tái hiện lỗi bằng test có input đã kiểm soát.** Sử dụng debugger để kiểm tra điều kiện hết hạn, timezone và các trạng thái nghiệp vụ; log cho thấy bước nào đã diễn ra.

**Bước 4 — Lọc theo event và ID.** Với ứng dụng đa request, ghi requestId/traceId nếu có; tránh trộn log hai checkout khác nhau.

**Bước 5 — Kiểm tra exception.** Đọc class, cause và stack trace khi cần, nhưng không đưa thông tin bí mật lên console.

**Bước 6 — Xác nhận bản sửa.** Test case thành công/thất bại, đảm bảo log còn mang ý nghĩa đúng. Không thay test bằng việc thấy “INFO success”.

**Bước 7 — Khôi phục level.** Giảm verbosity sau điều tra để không làm console ồn hoặc tăng chi phí khi deploy.

Workflow này tận dụng console cho phản hồi nhanh mà vẫn giữ ranh giới giữa quan sát, kiểm thử và nghiệp vụ.

## 18. Checklist cho console logging tốt

Một cấu hình development có thể được coi là hữu ích khi:

- Console thể hiện **severity** và **logger/module name**.
- Những event quan trọng có **event key ổn định**.
- Có **requestId/traceId** khi cần điều tra request đồng thời, với context được truyền/dọn đúng cách.
- Sự kiện INFO/WARNING/SEVERE xuất theo ngưỡng mong muốn; DEBUG/FINE chỉ bật theo phạm vi.
- Biết rõ backend đang dùng **stdout hay stderr**.
- Handler/Appender được gắn đúng, không in duplicate ngoài ý muốn.
- Exception có đủ context, không làm lộ bí mật.
- Unicode/tiếng Việt được giữ đúng.
- Console không bị ngập bởi logs trong hot loop.
- Đã kiểm tra khả năng redirect/filter và thời điểm flush.
- Test nghiệp vụ vẫn có assertions độc lập.
- Có chính sách chuyển sang production với retention/quyền truy cập/collector phù hợp.

## 19. Bài thực hành và câu hỏi tự đánh giá

### Bài thực hành A — Phân biệt stdout/stderr

Chạy chương trình **DevConsoleLoggingDemo.java** và redirect:

~~~bash
java DevConsoleLoggingDemo 1> app.stdout 2> app.stderr
~~~

Xem nội dung từng file. Giải thích vì sao log ở level INFO lại nằm trong **app.stderr** thay vì app.stdout.

**Gợi ý:** JUL ConsoleHandler mặc định ghi ra System.err, còn System.out.println ghi ra stdout.

### Bài thực hành B — Ngưỡng Logger và Handler

Giữ Logger ở FINE. Đổi Handler từ INFO sang WARNING rồi chạy lại. Sau đó đổi sang FINE. Dự đoán số dòng console ở mỗi lần và giải thích bản ghi nào bị chặn ở tầng Handler.

**Gợi ý:** Handler WARNING loại INFO/FINE; Handler FINE nhận cả INFO/WARNING/FINE của Logger đã cho đi qua.

### Bài thực hành C — Đổi Formatter

Thêm một trường **thread name** hoặc **event time** vào Formatter. Không nên khẳng định output có timestamp cụ thể trong README vì giờ chạy thay đổi. Kiểm tra Logger name, level và message vẫn còn.

### Bài thực hành D — Không in duplicate

Thử bỏ **setUseParentHandlers(false)** khi Logger có Handler riêng, rồi quan sát. Kết quả phụ thuộc Handler đã gắn ở root và cấu hình môi trường. Phân tích tại sao cùng một event có thể được xuất nhiều lần.

### Bài thực hành E — Đổi logging.properties

Đặt root INFO, package checkout FINE và ConsoleHandler INFO; ghi nhận FINE bị chặn. Sau đó đặt ConsoleHandler FINE và so sánh. Hãy đảm bảo ứng dụng bạn chạy thật sự nạp file cấu hình đó, không dùng Handler tự cấu hình đè lên kỳ vọng.

### Bài thực hành F — Mô phỏng log injection

Dùng input có newline, ví dụ một tên sản phẩm chứa ký tự xuống dòng. Quan sát vấn đề khi nối trực tiếp vào message; đề xuất encoder/escaping để output không thể giả mạo một event mới. Chỉ dùng dữ liệu thử nghiệm không nhạy cảm.

### Câu hỏi kiểm tra

**1. System.out.println và ConsoleHandler có tương đương nhau không?**  
Không. System.out.println là xuất text trực tiếp; ConsoleHandler nhận LogRecord với level, Filter và Formatter, và ghi ra System.err mặc định.

**2. JUL ConsoleHandler mặc định ghi stdout hay stderr?**  
**System.err**, kể cả với INFO.

**3. Vì sao Logger FINE + Handler INFO không in FINE?**  
Vì record qua Logger nhưng bị Handler INFO loại.

**4. Mặc định ConsoleHandler dùng Formatter nào?**  
**SimpleFormatter** nếu không có cấu hình khác.

**5. Trong file properties, muốn xuất FINE ở console phải kiểm tra những ngưỡng nào?**  
Effective level của Logger và level của ConsoleHandler, cùng Filter/đường chuyển record.

**6. Có nên dùng màu trong console làm severity chính thức không?**  
Không. Màu phụ thuộc IDE/terminal/encoder, còn level là dữ liệu event.

**7. Tại sao console có thể hiển thị thứ tự khác lúc hai stream được ghi?**  
Vì stdout/stderr có cơ chế buffering và thu thập độc lập, cùng với đa luồng/async nếu có.

**8. Trong test, thấy dòng INFO success có thay được assertion không?**  
Không. Cần assert trạng thái và kết quả nghiệp vụ; log chỉ là thông tin bổ trợ.

**9. Có nên ghi token ở mức FINE trong development?**  
Không. Level có thể bật lại, và terminal/log collector vẫn có thể giữ dữ liệu nhạy cảm.

**10. Console có còn phù hợp ở production container không?**  
Có thể phù hợp khi stdout/stderr được container runtime/collector quản lý, nhưng phải có policy về schema, retention, quyền truy cập, volume và độ bền.

## 20. Tài liệu chính thức

- **Oracle Java 17 — ConsoleHandler:** https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/ConsoleHandler.html
- **Oracle Java 17 — java.util.logging package:** https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/package-summary.html
- **Oracle Java 17 — SimpleFormatter:** https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/SimpleFormatter.html
- **Oracle Java 17 — LogManager:** https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogManager.html
- **Apache Log4j2 — Appenders và Console Appender:** https://logging.apache.org/log4j/2.x/manual/appenders.html

Dùng tài liệu tương ứng với **JDK và backend thực tế** của dự án. Nếu ứng dụng đã chọn SLF4J/Logback/Log4j2, cấu hình Console Appender phải theo API của backend đó, không mặc định sử dụng các property của JUL.

## 21. Ghi nhớ cốt lõi

**Console trong development là công cụ phản hồi nhanh để quan sát chương trình, không phải chỉ là System.out.println.** Logging API giúp các dòng console có level, Logger name, message, context và chính sách lọc nhất quán. Với JUL, **ConsoleHandler mặc định ghi System.err và có ngưỡng INFO**, nên Logger ở FINE vẫn chưa đủ để thấy FINE nếu Handler chưa đổi.

Khi debug, hãy biết rõ **nguồn event → Logger → Handler/Appender → Formatter → stdout/stderr → IDE/terminal**, và kết hợp log với debugger, test, event IDs, chính sách bảo mật và kiểm soát log volume. Sự phân tách này giúp console hữu ích trong development, đồng thời tạo nền tảng logging có thể vận hành trong môi trường lớn hơn.
