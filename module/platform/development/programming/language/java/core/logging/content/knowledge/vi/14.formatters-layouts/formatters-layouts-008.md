# Định dạng exception trong Java Logging: message, stack trace, cause và layout

## 1. Định dạng exception là gì?

**Định dạng exception** là quá trình biến thông tin trong một đối tượng `Throwable` thành nội dung có thể đọc, lưu trữ và tìm kiếm khi ứng dụng ghi log. Một bản ghi exception tốt không chỉ nói “đã có lỗi”, mà còn cho biết **thao tác nào thất bại, exception thuộc loại gì, nguyên nhân liên quan là gì, lỗi phát sinh ở đường gọi nào và sự kiện này thuộc request/job nào**.

Đối với Java Core Logging, cần phân biệt hai hoạt động:

1. **Ứng dụng tạo hoặc nhận exception**: Java cung cấp kiểu exception, message, stack trace, chuỗi cause và danh sách suppressed exceptions.
2. **Logging framework biểu diễn exception**: logger chuyển đối tượng `Throwable` tới backend; formatter/layout quyết định phần thông tin nào được in ra, trình bày thành nhiều dòng text hay một trường trong JSON, và có gắn thêm timestamp, level, logger name, trace/request ID hay không.

Ví dụ về **nội dung log minh họa**, không phải transcript cố định của một chương trình:

~~~text
2026-11-09 10:15:20.123 ERROR [http-worker-2] CheckoutService
requestId=req-42 operation=checkout outcome=failed
java.lang.IllegalStateException: Cannot complete checkout
    at example.CheckoutService.checkout(CheckoutService.java:48)
Caused by: java.io.IOException: Connection reset
    at example.StoreClient.read(StoreClient.java:71)
    ... 3 more
~~~

Ở đây có hai tầng thông tin: một **message nghiệp vụ** gắn ngữ cảnh `requestId` và một **exception được định dạng** chứa kiểu, stack trace, cause. Số dòng mã, timestamp và tên thread ở ví dụ chỉ để hình dung; thực tế phụ thuộc chương trình, phiên bản và layout.

**Lưu ý:** “exception formatting” không có nghĩa chỉ gọi `e.getMessage()`; cũng không đồng nghĩa ghi toàn bộ stack trace ra mọi đích. Mục tiêu là **giữ được thông tin chẩn đoán thích hợp ở đúng vị trí và theo định dạng pipeline có thể xử lý**.

## 2. Những thành phần nằm trong Throwable

`java.lang.Throwable` là lớp nền của `Exception` và `Error`. Khi ghi một exception, có năm nhóm thông tin chính:

| Thành phần | API | Ý nghĩa |
| --- | --- | --- |
| Loại exception | `e.getClass().getName()` | Phân biệt `IOException`, `IllegalStateException`, v.v. |
| Message | `e.getMessage()` | Mô tả ngắn do mã ném lỗi cung cấp; có thể `null` |
| Stack trace | `e.getStackTrace()` | Những stack frame liên quan tới nơi exception được tạo/ghi nhận |
| Cause | `e.getCause()` | Exception được gắn là nguyên nhân của exception hiện tại |
| Suppressed | `e.getSuppressed()` | Những lỗi bổ sung được giữ lại, thường gặp khi đóng resource trong `try-with-resources` |

Một exception có thể mang cả cause và suppressed:

~~~text
IllegalStateException: Cannot load order
  Caused by: IOException: read failed
    Suppressed: IOException: close failed
~~~

Sơ đồ trên mô tả quan hệ; cách `printStackTrace()` thực sự thụt lề và in `Suppressed`/`Caused by` có quy tắc riêng, không nhất thiết giống hệt sơ đồ.

### 2.1. getMessage() chỉ là một phần rất nhỏ

`e.getMessage()` có thể trả về `"Read timed out"` mà không chỉ ra thao tác, lớp Java hoặc đường thực thi đã tới điểm timeout. Nó có thể bằng `null`. Một số thư viện đặt đường dẫn, dữ liệu hoặc câu SQL trong message, vì vậy không mặc định nó luôn an toàn để đưa vào log công khai.

`e.toString()` thường biểu diễn tên lớp exception cộng message (nếu có), nhưng **không tương đương với stack trace đầy đủ**. Câu lệnh:

~~~java
// Minh họa trong một khối catch:
LOG.severe(e.toString());
~~~

chỉ đưa một chuỗi vào `LogRecord`. Formatter sẽ không có đối tượng `Throwable` để hiển thị các frame, cause và suppressed nếu không có nguồn khác.

### 2.2. Stack trace không phải message

Một stack frame thường có tên lớp, phương thức, tên tệp và số dòng, ví dụ:

~~~text
at example.StoreClient.read(StoreClient.java:71)
at example.OrderService.load(OrderService.java:33)
~~~

Đây là dấu vết của đường gọi; việc số dòng có tồn tại và chính xác ở mức nào còn phụ thuộc thông tin debug trong bytecode, môi trường và cách exception được tạo. Dùng stack trace giúp biết **vị trí**, nhưng không luôn tự chứng minh **nguyên nhân nghiệp vụ**. Nó nên được đọc cùng dữ liệu vận hành, input đã lọc an toàn và cause chain.

### 2.3. Cause chain

Khi chuyển lỗi giữa các tầng, cần giữ `cause`:

~~~java
// Minh họa trong một phương thức bắt IOException.
catch (java.io.IOException e) {
    throw new IllegalStateException("Cannot load order", e);
}
~~~

Constructor `IllegalStateException(String, Throwable)` giữ đối tượng lỗi gốc. Formatter tương thích có thể in phần `Caused by: java.io.IOException...` sau exception ngoài cùng.

Ngược lại:

~~~java
// Sai nếu muốn bảo toàn nguyên nhân.
catch (java.io.IOException e) {
    throw new IllegalStateException(e.getMessage());
}
~~~

đã làm mất liên kết tới `IOException`, vì exception mới không chứa `cause`. Formatter không thể tự phục hồi một Throwable mà mã ứng dụng đã bỏ.

### 2.4. Suppressed exceptions

Với `try-with-resources`, nếu thân khối ném lỗi A và `close()` ném lỗi B, Java thường giữ A là lỗi chính và gắn B vào `A.getSuppressed()`. Nếu chỉ có `close()` thất bại thì B có thể chính là lỗi được ném ra.

Thông tin suppressed khác với cause. Một exception có thể có nhiều suppressed, mỗi suppressed lại có stack trace hoặc cause riêng. Formatter chỉ in `e.getMessage()` sẽ bỏ qua toàn bộ quan hệ này; `Throwable.printStackTrace()` chuẩn có cơ chế thể hiện chúng.

## 3. Ba cách trình bày exception và mức độ thông tin

| Cách trình bày | Ví dụ | Thông tin giữ lại trong bản ghi |
| --- | --- | --- |
| Chỉ message | `"Read timed out"` | Rất ít; có thể mất cả loại và vị trí |
| Loại + message | `"IOException: Read timed out"` | Có thêm loại nhưng chưa có stack/cause/suppressed |
| Throwable đầy đủ | `Throwable` được logger giữ và formatter xuất stack trace | Có thể giữ loại, frame, cause, suppressed, tùy formatter và cấu hình |

Cách log tốt nhất không phải lúc nào cũng là “in đầy đủ ở mọi dòng”. Một timeout đã có retry và được xử lý hoàn toàn có thể chỉ cần DEBUG/WARN ngắn hoặc metric. Ngược lại, failure ở ranh giới HTTP/job cần điều tra thường nên có **một bản ghi chứa Throwable đầy đủ** và các trường ngữ cảnh thích hợp.

**Nguyên tắc:** khi cần stack trace, hãy **truyền đối tượng exception vào logging API**; đừng dựng chuỗi bằng `e.getMessage()` rồi kỳ vọng layout tự suy ra đường gọi và cause.

## 4. JUL: Formatter, LogRecord và getThrown()

Trong `java.util.logging` (JUL), logger tạo các `LogRecord`. Một `LogRecord` có thể mang:

- `record.getMessage()`: message/template.
- `record.getParameters()`: các tham số, nếu được truyền bằng overload phù hợp.
- `record.getThrown()`: `Throwable`, nếu lời gọi logger có truyền exception.
- `record.getLevel()`, `record.getLoggerName()`, timestamp, thread information và các trường khác.

`java.util.logging.Formatter` định nghĩa `format(LogRecord)` và có `formatMessage(LogRecord)` để xử lý thông điệp (bao gồm tham số `{0}` kiểu `MessageFormat` ở trường hợp tương ứng).

### 4.1. Truyền Throwable đúng overload

Đoạn nên dùng khi đây là điểm chịu trách nhiệm ghi lỗi:

~~~java
// Minh họa: LOG là java.util.logging.Logger, e là IOException.
LOG.log(java.util.logging.Level.SEVERE,
        "operation=readOrder outcome=failed",
        e);
~~~

Overload `Logger.log(Level, String, Throwable)` đưa `e` vào `LogRecord.getThrown()`. Nếu backend dùng `SimpleFormatter`, Throwable thường được in thành stack trace kèm cause/suppressed.

Đoạn dễ gây thiếu thông tin:

~~~java
// Không đính kèm Throwable vào LogRecord.
LOG.severe("readOrder failed: " + e.getMessage());
~~~

Câu sau vẫn có thể có ích khi chỉ muốn một mốc ngắn và lỗi đã được log đầy đủ nơi khác; nhưng nó không phải thay thế cho bản ghi exception chẩn đoán.

### 4.2. Message có tham số và exception cùng một record

JUL sử dụng placeholder `{0}`, `{1}` thay vì `{}` của SLF4J. Khi cần **đồng thời** tham số hóa message và đính kèm Throwable, có thể tạo `LogRecord`:

~~~java
// Đoạn minh họa nằm trong catch; orderId, e và LOG đã tồn tại.
java.util.logging.LogRecord record =
        new java.util.logging.LogRecord(
                java.util.logging.Level.SEVERE,
                "operation=loadOrder orderId={0} failed");

record.setParameters(new Object[] {orderId});
record.setThrown(e);
LOG.log(record);
~~~

Formatter gọi `formatMessage(record)` có thể thay `{0}` bằng `orderId`; một formatter in `record.getThrown()` còn giữ stack trace. Đây là mã minh họa trong phạm vi có sẵn các biến, không phải ứng dụng Java độc lập.

Đừng nhầm overload `log(Level, String, Object[])` với overload `log(Level, String, Throwable)`: chúng truyền **loại dữ liệu khác nhau** vào record. Nếu chỉ gọi `LOG.log(Level.SEVERE, "failed {0}", new Object[]{e})`, đối tượng e là một tham số message, không tự trở thành `getThrown()`.

### 4.3. SimpleFormatter và format string

`java.util.logging.SimpleFormatter` là formatter JUL phổ biến. Nó cho phép cấu hình format string theo quy ước của `String.format`; trong chuỗi này, các vị trí đáng chú ý gồm **`%4$s` (level), `%5$s` (message được format) và `%6$s` (Throwable/stack trace khi có)**.

Ví dụ một định dạng ý tưởng:

~~~text
%4$s %5$s%6$s%n
~~~

Đây là **mẫu dành cho thuộc tính định dạng của SimpleFormatter**, không phải template message của `Logger.log(...)`. Tập placeholder ở cấu hình formatter khác với `{0}` trong message của JUL và khác `{}` của SLF4J. Phần `%6$s` có thể là rỗng khi record không có Throwable và thường bao gồm xuống dòng/stack trace khi có.

Cẩn thận khi sửa format string: nếu chỉ in `%5$s` mà bỏ `%6$s`, bản ghi vẫn có thể giữ đối tượng `Throwable` nhưng **output text không hiển thị stack trace**. Không suy luận “cause đã bị mất ở chương trình” chỉ vì một console pattern không in throwable.

## 5. Ví dụ Java 17 độc lập: formatter thấy cause và suppressed

Ví dụ dưới đây dùng **JDK 17, không cần Maven, không cần thư viện ngoài JDK**. Nó mô phỏng lỗi xử lý và lỗi khi đóng resource, wrap exception để giữ cause, rồi đưa Throwable vào JUL `LogRecord`.

Để stdout **có thể dự đoán chính xác**, formatter của ví dụ chỉ in một bản tóm tắt cố định của exception. Phần sau sẽ giải thích cách thay formatter này bằng cách xuất đầy đủ stack trace trong ứng dụng thực tế.

Tạo tệp **ExceptionFormatterDemo.java**:

~~~java
import java.io.IOException;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class ExceptionFormatterDemo {
    private static final Logger LOG =
            Logger.getLogger(ExceptionFormatterDemo.class.getName());

    private static final class FailingResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    private static void runOperation() throws IOException {
        try (FailingResource ignored = new FailingResource()) {
            throw new IOException("operation failed");
        }
    }

    private static final class SummaryFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            StringBuilder out = new StringBuilder();
            out.append(record.getLevel().getName())
               .append(" ")
               .append(formatMessage(record))
               .append("\n");

            Throwable error = record.getThrown();
            if (error != null) {
                out.append("type=")
                   .append(error.getClass().getSimpleName())
                   .append("\n");
                out.append("message=")
                   .append(error.getMessage())
                   .append("\n");

                Throwable cause = error.getCause();
                if (cause != null) {
                    out.append("causeType=")
                       .append(cause.getClass().getSimpleName())
                       .append("\n");
                    out.append("causeMessage=")
                       .append(cause.getMessage())
                       .append("\n");
                    out.append("causeSuppressed=")
                       .append(cause.getSuppressed().length)
                       .append("\n");

                    for (Throwable suppressed : cause.getSuppressed()) {
                        out.append("suppressedMessage=")
                           .append(suppressed.getMessage())
                           .append("\n");
                    }
                }
            }
            return out.toString();
        }
    }

    private static void configureLogging() {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        Handler console = new StreamHandler(System.out,
                                            new SummaryFormatter()) {
            @Override
            public synchronized void publish(LogRecord record) {
                super.publish(record);
                flush();
            }
        };
        console.setLevel(Level.ALL);
        LOG.addHandler(console);
    }

    public static void main(String[] args) {
        configureLogging();

        try {
            runOperation();
        } catch (IOException original) {
            IllegalStateException wrapped =
                    new IllegalStateException("checkout failed", original);

            LOG.log(Level.SEVERE,
                    "operation=checkout requestId=req-17 outcome=failed",
                    wrapped);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ExceptionFormatterDemo.java
java ExceptionFormatterDemo
~~~

**Stdout của chương trình theo formatter đã định nghĩa:**

~~~text
SEVERE operation=checkout requestId=req-17 outcome=failed
type=IllegalStateException
message=checkout failed
causeType=IOException
causeMessage=operation failed
causeSuppressed=1
suppressedMessage=close failed
~~~

Vì sao có kết quả đó?

1. `runOperation()` ném `IOException("operation failed")` trong khối `try-with-resources`.
2. `FailingResource.close()` tiếp tục ném `IOException("close failed")`. Java giữ lỗi xử lý làm **primary** và gắn lỗi close thành **suppressed** của primary.
3. `IllegalStateException("checkout failed", original)` giữ primary exception làm cause. `LOG.log(..., wrapped)` gắn exception ngoài cùng vào `LogRecord.getThrown()`.
4. Formatter in tên loại, message, cause và `cause.getSuppressed()`. Số suppressed là `1`, message của suppressed là `close failed`.
5. Handler dùng `StreamHandler(System.out, ...)` và `flush()` sau mỗi publish; logger tắt parent handlers, do đó không có các dòng JUL mặc định bổ sung trên stderr.

**Ranh giới quan trọng của demo:** `SummaryFormatter` cố ý **không in các stack frame**, và chỉ kiểm tra suppressed trên cause trực tiếp. Đây là công cụ học cách đọc cấu trúc `Throwable`, **không phải lời khuyên thay stack trace đầy đủ bằng bản tóm tắt như vậy trong log production**. Nếu một exception có nhiều tầng cause/suppressed, formatter đầy đủ phải duyệt/định dạng tất cả các tầng cần thiết.

### 5.1. In stack trace đầy đủ trong formatter tùy biến

Nếu đang viết formatter JUL đặc thù, có thể lấy toàn bộ biểu diễn chuẩn của `Throwable` bằng `printStackTrace(PrintWriter)`:

~~~java
// Đoạn minh họa đặt bên trong Formatter.format(LogRecord record).
Throwable error = record.getThrown();
if (error != null) {
    java.io.StringWriter buffer = new java.io.StringWriter();
    java.io.PrintWriter writer = new java.io.PrintWriter(buffer);
    error.printStackTrace(writer);
    writer.flush();
    // Dùng buffer.toString() để ghép vào output của formatter.
}
~~~

`Throwable.printStackTrace` in exception ngoài cùng, các frame, cause và suppressed theo quy tắc chuẩn của Java, kể cả phần rút gọn frame chung dạng `... N more`. **Các số dòng và thứ tự frame phụ thuộc mã/biên dịch**, nên không đưa một transcript “chính xác” chung cho ví dụ in full stack.

Đoạn trên là **snippet trong phương thức**, không phải chương trình chạy độc lập. Nếu chỉ dùng `getStackTrace()` rồi nối các `StackTraceElement`, bạn phải tự lo việc duyệt cause/suppressed và tránh lặp/thiếu nhánh; dùng `printStackTrace` hoặc formatter đã được kiểm chứng thường an toàn hơn.

### 5.2. Vì sao không gọi trực tiếp e.printStackTrace() ở catch?

~~~java
// Cách không nên dùng làm pipeline logging chính ở ứng dụng server:
catch (IOException e) {
    e.printStackTrace();
}
~~~

`printStackTrace()` không đối số mặc định in ra **System.err**, không thông qua mức logger, appender, correlation ID, cấu hình retention hay encoder của ứng dụng. Nó có thể hữu ích trong thử nghiệm cực nhỏ, nhưng trong ứng dụng vận hành nên truyền Throwable qua logger, để formatter/layout xử lý thống nhất:

~~~java
// Minh họa dùng JUL.
catch (IOException e) {
    LOG.log(Level.SEVERE, "operation=load outcome=failed", e);
}
~~~

Lưu ý: ví dụ trên cũng là một đoạn code trong phương thức có `LOG`, không phải tệp Java độc lập.

## 6. SLF4J + Logback: exception qua ThrowableProxy và PatternLayout

Trong hệ thống dùng **SLF4J API với Logback Classic**, phần code thường sử dụng `org.slf4j.Logger`:

~~~java
// Minh họa trong lớp đã có SLF4J Logger LOG và requestId.
try {
    loadOrder();
} catch (java.io.IOException e) {
    LOG.error("operation=loadOrder requestId={} outcome=failed",
              requestId, e);
    throw e;
}
~~~

SLF4J thông thường nhận diện **Throwable ở vị trí cuối** trong lời gọi parameterized message là exception của sự kiện. Backend Logback có thể tạo `ThrowableProxy` để biểu diễn stack trace/cause/suppressed và render qua converter của layout. Nếu chỉ truyền `e.getMessage()` như argument thông thường, Throwable không được đính kèm.

Code snippet trên cần `loadOrder`, `requestId`, `LOG` và ngữ cảnh `throws IOException` của phương thức. Nó không biên dịch độc lập nếu thiếu phần khai báo tương ứng.

### 6.1. PatternLayout: dùng %ex hoặc %throwable

Ví dụ cấu hình `logback.xml` để log exception ra console:

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] %logger{36} requestId=%X{requestId} - %msg%n%ex{full}</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Các conversion word chính:

| Token | Vai trò |
| --- | --- |
| `%d{...}` | Timestamp theo pattern được chọn |
| `%-5level` | Mức log, căn lề |
| `%thread` | Thread tạo event |
| `%logger{36}` | Tên logger được rút gọn |
| `%X{requestId}` | Giá trị `requestId` trong MDC, nếu có |
| `%msg` | Nội dung message sau khi thay placeholder |
| `%n` | Dấu xuống dòng |
| `%ex{full}` | Throwable stack trace đầy đủ theo converter của Logback |

Token `%ex`/`%throwable` (tên converter tương ứng) là phần quan trọng của **exception formatting**. Nó cho phép Logback biểu diễn exception theo định dạng stack trace thay vì chỉ in một câu message.

**Cẩn thận:** một số phiên bản/cấu hình của Logback Classic có cơ chế **tự bổ sung thông tin throwable** vào PatternLayout khi bạn không khai báo converter throwable. Không nên dựa vào suy đoán “thiếu `%ex` luôn khiến stack trace biến mất”; hãy kiểm tra output thật và policy của backend. Ngược lại, nếu cấu hình chủ động dùng `%nopex` hoặc encoder tùy biến bỏ throwable, stack trace có thể không xuất dù `Logger.error(..., e)` đã truyền đúng.

Với `%ex{short}`, output stack trace được rút ngắn (tùy converter và phiên bản); dùng `%ex{full}` khi điều tra cần toàn bộ cause/suppressed. Đừng đặt `%ex` hai lần trong pattern vì có thể xuất trùng cùng một exception.

### 6.2. Layout không sửa được nguyên nhân đã bị bỏ

Nếu mã ứng dụng làm:

~~~java
// Không giữ cause trong exception mới.
throw new IllegalStateException("Cannot read data");
~~~

thì dù pattern có `%ex{full}`, layout cũng chỉ in stack trace của `IllegalStateException` đó; nó **không thể tìm lại IOException gốc** nếu mã không truyền nó vào constructor. Khi wrap:

~~~java
throw new IllegalStateException("Cannot read data", e);
~~~

cause chain được giữ để converter hiển thị.

### 6.3. Không ghi lặp ở mọi tầng

Nếu repository ném `IOException`, service wrap thành `OrderLoadException` với cause, còn API boundary là nơi log ERROR và trả response, thông thường chỉ cần **một bản ghi throwable đầy đủ tại boundary**. Ghi cùng lỗi ở ba tầng rồi rethrow có thể làm dashboard đếm một failure nhiều lần và khiến log quá nhiễu.

Điều này khác với việc cố tình ghi WARN ở một lần retry thành công hoặc một event có ý nghĩa khác. Chọn mức log theo tác động và trách nhiệm của tầng đó.

## 7. Apache Log4j 2: %throwable, %ex và PatternLayout

Trong **Log4j 2**, mã ứng dụng có thể sử dụng trực tiếp Log4j API:

~~~java
// Minh họa trong dự án đã có log4j-api và log4j-core.
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

private static final Logger LOG =
        LogManager.getLogger(MyService.class);
~~~

và truyền Throwable khi log:

~~~java
// Đoạn minh họa trong catch, với requestId và LOG hợp lệ.
LOG.error("operation=process requestId={} outcome=failed",
          requestId, e);
~~~

Thông điệp dùng placeholder `{}` theo Log4j2 parameterized message; `Throwable` được gắn với event theo overload/cách gọi tương thích. Backend/appender/layout quyết định cách in lỗi.

### 7.1. Cấu hình log4j2.xml với stack trace

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <PatternLayout pattern="%d{yyyy-MM-dd HH:mm:ss.SSS} %-5p [%t] %c{1.} requestId=%X{requestId} - %m%n%throwable{full}"/>
        </Console>
    </Appenders>

    <Loggers>
        <Root level="INFO">
            <AppenderRef ref="CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
~~~

Đặt file cấu hình ở `src/main/resources/log4j2.xml` nếu dự án đóng gói bằng Maven/Gradle theo cấu trúc thông thường.

Các token liên quan:

- `%m` hoặc `%msg`: message của event.
- `%n`: xuống dòng.
- `%throwable{full}` hoặc `%ex{full}`: biểu diễn stack trace/cause/suppressed của Throwable theo converter của Log4j2.
- `%X{requestId}`: giá trị từ `ThreadContext` map, nếu được đặt và truyền đúng qua execution context.
- `%d`, `%p`, `%t`, `%c`: timestamp, level, thread và logger name.

PatternLayout của Log4j2 có tùy chọn liên quan đến việc **tự thêm exception khi pattern chưa có converter Throwable** (như `alwaysWriteExceptions` ở các phiên bản hỗ trợ). Vì vậy không nên khẳng định thiếu `%throwable` thì chắc chắn không in stack trace. Với yêu cầu rõ ràng, hãy khai báo converter thích hợp và chạy test output.

### 7.2. Full, short và extended exception information

Các converter của Log4j2 có lựa chọn để rút ngắn hoặc mở rộng thông tin stack trace, với cú pháp và tính năng chi tiết phụ thuộc phiên bản. Ví dụ `%throwable{short}` là lựa chọn để rút ngắn exception output trong PatternLayout.

**Chọn full hay short theo mục đích**:

- Đối với log lỗi ở boundary mà chỉ có một bản ghi phục vụ điều tra, full trace thường có giá trị.
- Với nhiều retry, nếu nơi cuối cùng đã ghi full, các lần thử có thể chỉ ghi code lỗi, số lần thử và ngữ cảnh; không nhất thiết in full trace ở mỗi lần.
- Log cần phân tích theo field/JSON nên cân nhắc cách encode throwable như một chuỗi nhiều dòng đã escape hoặc thành các trường có cấu trúc, thay vì đưa các dòng stack trace rời rạc vào collector.

Không nhầm **extended stack trace** với việc tự động có thêm dữ liệu nghiệp vụ. Metadata về vị trí class/JAR có thể có, nhưng thông tin request ID, input an toàn và trạng thái nghiệp vụ vẫn phải được ứng dụng cung cấp.

## 8. Định dạng text nhiều dòng và structured logging

### 8.1. Một event có thể thành nhiều dòng vật lý

Thông thường một exception full stack trace tạo ra một message chứa newline:

~~~text
ERROR operation=checkout requestId=r-7 failed
java.lang.IllegalStateException: checkout failed
    at example.CheckoutService.checkout(CheckoutService.java:42)
Caused by: java.io.IOException: store unavailable
    at example.StoreClient.read(StoreClient.java:23)
~~~

Đây là ví dụ **minh họa**, không khẳng định stack frame thực tế của các chương trình trước. Nếu collector chỉ chia event bằng từng newline, nó có thể hiểu mỗi dòng `at ...` là một log event mới hoặc mất ngữ cảnh mức ERROR/request ID.

Hai hướng vận hành:

1. **Multiline-aware ingestion:** cấu hình log shipper/collector gộp các dòng liên quan thành một event trước khi index, dựa theo cấu trúc output.
2. **Structured logging:** sử dụng encoder/layout được thiết kế cho JSON hoặc định dạng event có cấu trúc, để stack trace là một giá trị string được escape đúng quy tắc JSON (chẳng hạn newline được biểu diễn thành `\n` trong giá trị chuỗi).

Không tự nghĩ “JSON = không có newline”: JSON hợp lệ vẫn có thể chứa nội dung chuỗi với escape newline, trong khi một file kiểu NDJSON yêu cầu **mỗi event là một JSON object trên một dòng vật lý**. Phải xác nhận encoder và collector thống nhất cùng giao thức.

### 8.2. Ví dụ mô hình sự kiện JSON

~~~json
{
  "timestamp": "2026-11-09T10:15:20Z",
  "level": "ERROR",
  "logger": "example.CheckoutService",
  "requestId": "req-17",
  "message": "operation=checkout outcome=failed",
  "error": {
    "type": "java.lang.IllegalStateException",
    "message": "checkout failed",
    "stack_trace": "java.lang.IllegalStateException: checkout failed\n\tat example.CheckoutService.checkout(CheckoutService.java:42)\nCaused by: java.io.IOException: operation failed"
  }
}
~~~

Đây là **schema minh họa do ứng dụng/encoder thiết kế**, không phải output mặc định mà JUL, Logback hoặc Log4j2 đều tự tạo. Tên field `error.type`, `error.stack_trace`, cách lưu cause và kiểu timestamp phụ thuộc encoder, version và cấu hình pipeline.

Một số stack-trace schema có thể tách exception thành `type`, `message`, `frames[]`, `cause` hoặc `suppressed[]` thay vì một chuỗi. Cách đó hỗ trợ truy vấn nhưng tăng độ phức tạp và volume; không có một schema bắt buộc duy nhất cho mọi framework.

**Phụ thuộc thư viện:** muốn JSON log trong Logback có thể cần encoder ngoài thư viện mặc định; với Log4j2, những layout structured nâng cao như JSON Template Layout có module/dependency riêng. Không sao chép cấu hình JSON từ backend khác rồi kỳ vọng chạy khi thiếu đúng module.

### 8.3. Chọn field phục vụ tìm kiếm

Các trường nên có khi phù hợp:

| Trường | Ý nghĩa |
| --- | --- |
| `timestamp` | Thời điểm event, có timezone rõ ràng |
| `level` | Mức log |
| `logger` | Class/component phát event |
| `thread` | Thread phát event, khi có ích |
| `service` / `environment` | Dịch vụ và môi trường xử lý |
| `requestId` / `traceId` / `spanId` | ID liên kết giữa các event, nếu được triển khai |
| `operation` | Thao tác đang xử lý |
| `error.type` | Loại exception |
| `error.message` | Message đã xét chính sách an toàn |
| `error.stack_trace` | Stack trace khi cần điều tra |

ID tương quan và loại lỗi có thể hữu ích hơn khi tìm kiếm so với việc phải regex trên stack trace nhiều dòng. Nhưng không lạm dụng field có độ đa dạng lớn làm nhãn metric hoặc khóa index không cần thiết; cần thiết kế chính sách quan sát phù hợp.

## 9. MDC/ThreadContext và exception: ghép ngữ cảnh đúng cách

Một stack trace cho biết đường gọi, nhưng nếu có hàng nghìn request đồng thời thì người xử lý vẫn cần nối exception với request cụ thể.

Trong dự án dùng **SLF4J + Logback**, có thể đặt `MDC`:

~~~java
// Mã minh họa trong request handler có requestId và LOG.
org.slf4j.MDC.put("requestId", requestId);
try {
    processRequest();
} finally {
    org.slf4j.MDC.remove("requestId");
}
~~~

Trong Logback PatternLayout, `%X{requestId}` giúp in ID đó. Với Log4j2 API dùng trực tiếp, `ThreadContext.put(...)` / `CloseableThreadContext` là cách phổ biến để gắn context; `%X{requestId}` có thể xuất field tương ứng.

**Cần nhớ:** MDC và ThreadContext thường gắn với thread hoặc context quản lý bởi framework, không mặc định truyền qua mọi `CompletableFuture` hay worker thread. Khi xử lý bất đồng bộ, phải truyền context đúng cơ chế, dọn khi hoàn thành và kiểm tra ID không “rò” sang request kế tiếp trên thread pool.

Giá trị MDC/ThreadContext không phải thay thế việc giữ `Throwable`. Một log có requestId nhưng không có cause/stack trace vẫn có thể không đủ chẩn đoán lỗi khó.

## 10. Chọn nơi log exception và tránh ghi trùng

Một kiến trúc thường gặp:

~~~text
Storage layer -> throws IOException
Service layer -> wraps ServiceException("load failed", IOException)
HTTP boundary -> logs ServiceException with Throwable + requestId
             -> returns safe error response
~~~

Tầng service có thể thêm ngữ cảnh bằng constructor nhận cause:

~~~java
throw new IllegalStateException("Cannot load orderId=" + safeOrderId, e);
~~~

Khi đó một bản ghi đầy đủ ở HTTP boundary có thể cho biết cả thao tác thất bại lẫn IOException gốc. Nếu mỗi tầng đều ghi ERROR và rethrow, cùng một failure có thể thành nhiều bản ghi giống nhau. Bên cạnh tốn dung lượng, nó làm khó phân biệt **một lỗi xảy ra ba lần** với **một lỗi được log ở ba tầng**.

Trường hợp đã xử lý được exception bằng fallback/retry thành công thì có thể ghi DEBUG/WARN/metric tùy tác động. Không phải mọi exception đều cần xuất ERROR full stack, đặc biệt các exception dự kiến trong control flow.

### 10.1. Không giấu nguyên nhân khi wrap

Các cách làm mất dấu vết thường gặp:

~~~java
// Tạo exception mới mà quên cause:
throw new IllegalStateException("Cannot load data");

// Chỉ lấy message, không còn stack trace gốc trong record:
LOG.error("Cannot load data: {}", e.getMessage());

// Catch rồi bỏ trống, không còn dấu hiệu thất bại:
catch (IOException ignored) {
}
~~~

Đây là **đoạn minh họa các lỗi thiết kế** trong những ngữ cảnh khác nhau, không phải một khối Java chạy độc lập. Cách sửa là giữ `Throwable` xuyên tầng và chỉ log đầy đủ ở điểm chịu trách nhiệm báo lỗi.

### 10.2. Bảo vệ thông tin trong response bên ngoài

Một API có thể trả:

~~~json
{
  "errorCode": "ORDER_READ_FAILED",
  "message": "The request could not be completed",
  "requestId": "req-17"
}
~~~

Đây là response minh họa, không phải yêu cầu bắt buộc của Java. Người dùng không cần thấy stack trace nội bộ, câu SQL, endpoint, path filesystem hay token. Hệ thống log nội bộ có thể giữ Throwable với quyền truy cập và retention hạn chế, nhưng cũng cần loại bỏ dữ liệu bí mật nếu exception message chứa chúng.

**Giữ cause trong hệ thống và không công khai stack trace ra HTTP response là hai quyết định hoàn toàn tương thích.**

## 11. An toàn khi định dạng và lưu exception

Exception message có thể chứa dữ liệu do người dùng kiểm soát hoặc dữ liệu của driver/framework. Ví dụ tên file, URL kết nối, tham số truy vấn, nội dung JSON lỗi hay đường dẫn nội bộ có thể xuất hiện trong message; stack trace có thể tiết lộ class/module/phiên bản.

Các nguyên tắc:

1. **Không ghi secret từ đầu.** Không đưa mật khẩu, API key, access token, session cookie, mã OTP hoặc payload nhạy cảm vào exception message hoặc log context. Không dựa hoàn toàn vào bước regex sau khi đã tạo text đầy đủ.
2. **Chọn level và đích phù hợp.** Full exception trace có thể dài; với lỗi quan trọng, lưu ở hệ thống chẩn đoán có phân quyền. Không in đầy đủ ra response người dùng.
3. **Chống log forging.** Dữ liệu không tin cậy có thể chứa newline hoặc ký tự điều khiển tạo dòng log giả. Encoder phải escape/normalize theo định dạng đích; JSON encoder đúng chuẩn có thể escape newline trong string.
4. **Giới hạn độ dài và volume.** Một cause chain sâu hoặc message lớn có thể làm log phình to, gây I/O/GC và tăng chi phí ingest. Giới hạn cần có chủ đích; nếu cắt stack trace, ghi rõ rằng thông tin bị rút gọn.
5. **Bảo vệ file và collector.** Đặt quyền truy cập, retention, mã hóa nơi cần thiết và xem xét các bản sao/backup.
6. **Không đưa dữ liệu cần bảo vệ vào MDC.** MDC có thể theo event tới nhiều appender và đích hơn bạn dự kiến.
7. **Đánh giá output khi có lỗi ở formatter/encoder.** Một exception không nên làm pipeline logging ném lỗi vô hạn; dùng backend/layout đã kiểm chứng và quan sát trạng thái appender.

Mục tiêu của formatter là giữ **thông tin cần điều tra** mà không tạo **rủi ro rò rỉ hoặc quá tải** không cần thiết.

## 12. Chi phí và hiệu năng của stack trace

In full exception không rẻ như log một giá trị số đơn giản:

- Tạo exception thường thu thập stack trace lúc xây dựng Throwable (chi phí phụ thuộc loại và cấu hình); một số kiểu Throwable có thể tắt hoặc giới hạn stack trace.
- Formatter/layout phải duyệt frame, cause, suppressed và có thể tạo nhiều chuỗi trung gian.
- Việc encode và ghi text/JSON nhiều byte làm tăng I/O, file size và chi phí collector/index.
- Nếu exception được tạo và log hàng nghìn lần/giây trong hot path, CPU, allocations và p95/p99 latency có thể tăng rõ.
- Với async logging, chi phí encode/ghi có thể chuyển sang worker, nhưng queue vẫn dùng bộ nhớ và có nguy cơ block/drop khi đầy; không phải bảo đảm không mất sự kiện.

**Đừng tối ưu sai bằng cách xóa mọi stack trace.** Hãy phân loại lỗi, chọn điểm log thích hợp, hạn chế log trùng và đo hiệu năng. Nếu một lỗi lặp rất nhiều, cân nhắc gộp số lượng bằng metric/rate limit trong phạm vi cho phép, nhưng giữ đủ dấu vết cho lỗi quan trọng.

Các chỉ số đáng theo dõi: log events/s, bytes/s, CPU, allocation/GC, queue depth, dropped events, p95/p99 latency và dung lượng lưu giữ. So sánh workload trước/sau khi thay layout, không chỉ đo thời gian chạy một `LOG.error(...)`.

## 13. Cách xác minh exception formatting thực tế

Để kiểm tra một dự án thay đổi `logback.xml`, `log4j2.xml` hoặc JUL handler, nên tạo một exception thử nghiệm có:

- Message ngoài cùng dễ nhận biết, ví dụ `"checkout failed"`.
- Cause gốc khác loại, ví dụ `IOException("operation failed")`.
- Suppressed exception, ví dụ lỗi `close()` trong `try-with-resources`.
- Request ID an toàn, ví dụ `req-17`.
- Cả sự kiện bình thường (không có Throwable) và lỗi (có Throwable).

Sau đó kiểm tra theo trình tự:

1. **Đúng backend:** JUL/Logback/Log4j2 nào thực sự nhận event? Logger có provider/implementation phù hợp không?
2. **Event có được chấp nhận:** logger level, filter và appender-ref/handler level có chặn ERROR không?
3. **Throwable có trong event:** với JUL xem `LogRecord.getThrown()`; với SLF4J/Log4j2 dùng overload nhận Throwable, không chỉ `getMessage()`.
4. **Formatter/layout có in stack trace:** JUL formatter có dùng Throwable/`%6$s` không? Logback có `%ex` hay cơ chế hiển thị tương ứng? Log4j2 có `%throwable` và encoder phù hợp không?
5. **Cause/suppressed có hiển thị:** tìm các phần `Caused by:` và `Suppressed:` trong full trace; nếu không có, kiểm tra cả dữ liệu exception lẫn chính sách format rút gọn.
6. **Ngữ cảnh có đúng:** requestId/traceId có gắn đúng request và không tồn tại sau khi thread xử lý xong?
7. **Collector có gộp multiline:** một exception có bị tách thành nhiều event không? JSON output có escape newline đúng cách không?
8. **Bảo mật:** trong log có secret, URL chứa credential, đường dẫn nội bộ không cần thiết hoặc payload từ input không tin cậy không?
9. **Hiệu năng:** test cả tải thường và lỗi lặp lại; đo throughput, bytes/s, CPU, GC và queue.
10. **Không log trùng:** cùng một exception có bị ghi ở nhiều tầng/appender không?

Khi cần kiểm thử output, không nhất thiết assert toàn bộ text stack trace có số dòng cố định: số dòng thay đổi theo refactor và compiler. Tốt hơn là kiểm tra các đặc tính ổn định như **exception type, message, cause type, suppressed count, requestId** và việc encoder có trường Throwable, rồi dùng integration test để khẳng định format thực tế.

## 14. Những lỗi thường gặp và cách sửa

| Sai lầm | Kết quả | Hướng xử lý |
| --- | --- | --- |
| `LOG.error("failed: {}", e.getMessage())` | Log chỉ chứa text, không có Throwable | Truyền `e` vào overload logging thích hợp |
| `System.err.println(e)` | Chỉ có `toString()`, không đi qua pipeline logging | Ghi qua logger với Throwable |
| `e.printStackTrace()` trực tiếp trong server | Có stack trace nhưng thiếu logger level, appender/context/retention thống nhất | Dùng logger và formatter/layout |
| Wrap bằng exception không có cause | Mất liên kết tới lỗi gốc | Dùng constructor `(message, cause)` |
| Chỉ render `getStackTrace()` | Có thể bỏ cause/suppressed | Dùng `printStackTrace` hoặc converter chuẩn |
| JUL pattern chỉ có `%5$s` | Có thể không hiện Throwable | Xem `%6$s` hoặc formatter có đọc `getThrown()` |
| Logback vô tình dùng `%nopex` | Có thể không in stack trace | Chọn converter throwable phù hợp |
| Log4j2 chỉ in `%m` và tắt auto exceptions | Không thấy stack trace | Thêm `%throwable{full}` hoặc bật chính sách phù hợp |
| Hai converter Throwable trong một pattern | Có thể in trùng exception | Chỉ đặt một converter theo mục tiêu |
| Stack trace nhiều dòng bị collector tách | Các frame mất level/requestId và khó tìm kiếm | Multiline parsing hoặc structured logging |
| Nghĩ JSON tự có exception fields | Encoder có thể chỉ lưu message | Chọn encoder/layout có hỗ trợ Throwable và test |
| Log cùng một failure ERROR ở mọi tầng | Trùng dữ liệu, tăng cảnh báo | Log đầy đủ ở ranh giới chịu trách nhiệm |
| In full stack ra API response | Lộ class/file/path/chi tiết nội bộ | Trả code/message an toàn, log nội bộ có phân quyền |
| Chỉ log “failed” không có requestId | Khó nối với request khác trong hệ thống | Thêm ID tương quan an toàn |
| Bỏ qua suppressed exceptions | Không thấy lỗi khi đóng resource | Sử dụng formatter hiển thị suppressed và kiểm tra cause |

## 15. Bài tập tự kiểm tra

1. **Khái niệm:** so sánh `e.getMessage()`, `e.toString()`, `e.getStackTrace()` và `e.printStackTrace(PrintWriter)`. Cách nào có thể bao gồm cause/suppressed theo định dạng chuẩn Java?
2. **JDK 17:** tạo `ExceptionFormatterDemo.java`, chạy bằng `javac`/`java` và giải thích tại sao `causeSuppressed=1`, `suppressedMessage=close failed`. Nếu `close()` không ném exception nữa, output nào thay đổi?
3. **JUL:** thiết kế một `LogRecord` dùng template `"orderId={0}"`, thêm parameters và `setThrown(e)`. Giải thích tại sao truyền exception chỉ như argument của `log(Level, String, Object[])` không có cùng ý nghĩa.
4. **Logback:** sửa pattern để in timestamp, level, requestId, message và `%ex{full}`. Với một error có cause, cần kiểm tra phần nào để biết nguyên nhân đã được bảo toàn?
5. **Log4j2:** so sánh `%m%n` với `%m%n%throwable{full}`. Vì sao phải xem cả `alwaysWriteExceptions` và backend thực tế trước khi kết luận một pattern không in exception?
6. **Structured:** thiết kế JSON fields cho exception, bảo đảm `stack_trace` là một string hợp lệ khi chứa newline. Nêu cách collector có thể phân biệt một event JSON với nhiều dòng plain text.
7. **Chi phí:** một service có 1.000 lỗi/giây, mỗi full trace khoảng 5 KB. Tính lượng dữ liệu thô/ngày và đề xuất cách giảm log lặp mà vẫn giữ đủ thông tin điều tra.
8. **An toàn:** exception message vô tình chứa token trong URL. Vì sao chỉ sửa layout không luôn đủ? Thiết kế cách ghi log nội bộ an toàn và response người dùng không lộ dữ liệu.
9. **Async:** nếu request ID được đặt ở MDC nhưng xử lý exception xảy ra trên thread khác, vì sao trường đó có thể trống? Nêu cách kiểm chứng context propagation.
10. **Ranh giới:** repository, service và controller đều nhận cùng một exception. Chọn điểm ghi full trace và cách giữ cause qua các tầng mà không sinh ba log ERROR trùng nhau.

## 16. Tóm tắt

**Định dạng exception** là cầu nối giữa cấu trúc `Throwable` của Java và bản ghi log mà con người hoặc hệ thống xử lý cần đọc. Muốn log hữu ích, hãy **truyền Throwable thật**, giữ **cause và suppressed**, chọn **formatter/layout hiển thị đủ thông tin**, và gắn ngữ cảnh an toàn như request ID. Trong JUL, quan tâm `LogRecord.getThrown()` và `Formatter`; trong Logback, quan tâm `PatternLayout` và converter `%ex`; trong Log4j2, quan tâm `%throwable` và cách encoder xuất event. Cuối cùng, kiểm tra multiline/JSON, hiệu năng, retention và bảo mật để exception log thật sự giúp tìm nguyên nhân thay vì tạo thêm nhiễu.