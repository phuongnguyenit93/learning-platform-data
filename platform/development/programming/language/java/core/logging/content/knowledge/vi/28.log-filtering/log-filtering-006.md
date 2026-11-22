# Filter theo exception trong Java Logging

## 1. Filter theo exception là gì?

**Filter theo exception** là quy tắc quyết định một sự kiện log có được tiếp tục đến một hoặc nhiều nơi nhận (console, file, hệ thống log tập trung) dựa trên **ngoại lệ (exception) gắn với sự kiện**. Điều kiện có thể là loại exception, quan hệ kế thừa, chuỗi nguyên nhân (`cause`), mức log hoặc ngữ cảnh nghiệp vụ.

Ví dụ ứng dụng xử lý hàng nghìn dữ liệu nhập không hợp lệ mỗi phút. Mỗi lần chuyển chuỗi `"abc"` sang số có thể sinh `NumberFormatException`. Nếu những lỗi nhập liệu này đã được xử lý và có metric riêng, hệ thống có thể **lọc các bản ghi INFO lặp lại về exception đã dự kiến**, nhưng vẫn giữ các bản ghi WARNING/ERROR khi sự cố cần điều tra.

Điểm phân biệt quan trọng: **lọc sự kiện log không bắt, không xóa và không làm thay đổi exception trong luồng thực thi Java**. Một `catch` quyết định xử lý ngoại lệ trong chương trình; một logging filter chỉ quyết định có xuất bản ghi hay không. Nếu đã quyết định lọc, ngoại lệ vẫn có thể được ném/lan truyền bình thường.

Sơ đồ luồng xử lý tổng quát:

~~~text
try/catch hoặc tầng xử lý lỗi
       │ logger.log(level, message, throwable)
       ▼
  Logger level / cấu hình
       │ nếu được phép tạo log event
       ▼
  Log event + Throwable/proxy
       │
       ▼
  Exception filter: loại + cause + level + context
       ├── DROP / DENY: không gửi tới đích được gắn filter
       └── KEEP / NEUTRAL: tiếp tục pipeline
                                 │
                                 ▼
                          Appender / Handler
                                 │
                                 ▼
                          Console / File / Remote
~~~

Vị trí của filter khác nhau theo framework. Filter ở **logger** có thể ảnh hưởng nhiều handler/appender; filter ở **một sink** chỉ ảnh hưởng đầu ra đó. Vì vậy, cần xác định **phạm vi áp dụng** trước khi chọn nơi gắn filter.

## 2. Chọn điều kiện lọc đúng: type, cause, level và ngữ cảnh

| Tiêu chí | Ý nghĩa | Ví dụ và lưu ý |
| --- | --- | --- |
| Loại exception trực tiếp | So với `Throwable` gắn ở log event | `NumberFormatException`, `IOException` |
| Kế thừa | Cho phép hoặc từ chối cả subclass | `instanceof IllegalArgumentException` khớp cả `NumberFormatException`; chiều ngược lại không đúng |
| Chuỗi `cause` | Tìm exception bị bọc bởi ngoại lệ khác | `CompletionException` có thể chứa `IOException` ở `getCause()` |
| Mức log | Giữ sự kiện có tác động cao | Chỉ drop dưới WARNING; giữ WARNING/SEVERE dù type trùng |
| Logger/sink | Chỉ giảm nhiễu ở kênh quan sát | Drop ở console nhưng giữ ở file điều tra |
| Context nghiệp vụ | Phân biệt “đã dự kiến” và “bất thường” | Cùng `IOException` nhưng `event=retry` khác `event=data_loss` |

Ví dụ chuỗi nguyên nhân:

~~~text
CompletionException
    └── IOException
          └── SocketException
~~~

Nếu policy là “giữ sự cố I/O”, chỉ kiểm tra `event.getThrown() instanceof IOException` sẽ **không khớp** khi wrapper ngoài cùng là `CompletionException`. Cần đi qua `getCause()` hoặc API proxy tương ứng. Ngược lại, tìm tất cả nguyên nhân để loại `IOException` có thể xóa cả những lỗi quan trọng đã bị bọc; phải phối hợp level và ngữ cảnh.

Một chính sách rõ ràng nên mô tả:

- **Khi nào drop:** chỉ một tập exception có ý nghĩa đã được dự kiến, ở các mức log thấp, trong kênh đã chỉ định.
- **Khi nào giữ:** WARNING/ERROR, lỗi không khớp, bản ghi không có exception và các sự kiện audit/security.
- **Khi nào đo đếm:** số bản ghi bị lọc, tần suất và kết quả xử lý lỗi vẫn cần quan sát qua metric hoặc event tổng hợp.
- **Điều gì không xét:** ví dụ policy chỉ theo chuỗi `cause`, không duyệt `getSuppressed()`; nếu suppressed exceptions quan trọng thì phải mở rộng logic có chủ đích.

Không dựa vào `exception.getMessage()` hoặc stack trace dạng chuỗi để suy ra loại lỗi nếu hệ thống đã có `Throwable`. Message có thể thay đổi theo phiên bản, ngôn ngữ, dữ liệu đầu vào; message do người dùng cung cấp còn có nguy cơ chứa thông tin nhạy cảm.

## 3. API Java Util Logging (JUL): Filter và LogRecord

Với `java.util.logging` có sẵn trong JDK:

- `java.util.logging.Filter` là functional interface với phương thức `boolean isLoggable(LogRecord record)`.
- `LogRecord.getThrown()` trả về `Throwable` được gắn với sự kiện, hoặc `null` nếu không có.
- `record.getLevel()` cho phép xét mức độ nghiêm trọng. `Level.WARNING`, `Level.SEVERE` là các mức chuẩn của JUL.
- `Logger.setFilter(...)` gắn filter ở logger phát sự kiện; `Handler.setFilter(...)` gắn filter ở handler đích. Handler còn có level riêng, nên bản ghi phải vượt qua level và filter liên quan mới được xuất.
- Khi gọi `logger.log(Level.WARNING, "message", exception)`, overload ba tham số có `Throwable` lưu ngoại lệ vào `LogRecord.thrown`. Nếu chỉ nối `exception.toString()` vào message, `getThrown()` vẫn là `null`.

Ví dụ gắn filter cho một console handler:

~~~java
ConsoleHandler handler = new ConsoleHandler();
handler.setFilter(new MyExceptionFilter());
logger.addHandler(handler);
~~~

Đây là đoạn minh họa cần `logger` và `MyExceptionFilter` đã được định nghĩa. Filter tại một handler không đương nhiên chặn sự kiện tới các handler khác. Khi cần giữ bản ghi đầy đủ trong file để phục vụ điều tra, có thể dùng filter chỉ trên kênh console và không gắn nó vào kênh audit/file.

Trong JUL, `isLoggable(...)` trả về `true` nghĩa là **filter này cho qua bước hiện tại**; nó không cam kết sink đã ghi thành công vì các điều kiện về level, handler hoặc I/O khác vẫn có thể chặn.

## 4. Ví dụ Java 17 chạy độc lập: lọc lỗi parse đã dự kiến

Chính sách demo:

1. Giữ **mọi sự kiện WARNING trở lên**, không phụ thuộc exception.
2. Với sự kiện **dưới WARNING**, bỏ bản ghi khi `NumberFormatException` xuất hiện trực tiếp hoặc trong chuỗi `cause`.
3. Giữ bản ghi khác, kể cả bản ghi không có Throwable.
4. Chỉ áp dụng quy tắc cho **ConsoleHandler** đang cấu hình trong ví dụ.

Tạo tệp **ExceptionFilterDemo.java**:

~~~java
import java.io.IOException;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;
import java.util.logging.ConsoleHandler;
import java.util.logging.Filter;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class ExceptionFilterDemo {
    private static final Logger LOG =
            Logger.getLogger(ExceptionFilterDemo.class.getName());

    private static final class DropExpectedParsing implements Filter {
        @Override
        public boolean isLoggable(LogRecord record) {
            // Cảnh báo quan trọng luôn được giữ.
            if (record.getLevel().intValue() >= Level.WARNING.intValue()) {
                return true;
            }
            // Set theo identity tránh vòng lặp nếu cause graph bị tạo chu kỳ.
            Set<Throwable> seen =
                    Collections.newSetFromMap(new IdentityHashMap<>());
            for (Throwable cause = record.getThrown();
                 cause != null && seen.add(cause);
                 cause = cause.getCause()) {
                if (cause instanceof NumberFormatException) {
                    return false;
                }
            }
            return true;
        }
    }

    public static void main(String[] args) {
        ConsoleHandler handler = new ConsoleHandler();
        handler.setLevel(Level.ALL);
        handler.setFilter(new DropExpectedParsing());
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " "
                        + formatMessage(record) + System.lineSeparator();
            }
        });

        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);
        LOG.addHandler(handler);
        try {
            LOG.log(Level.INFO, "expected parse failure",
                    new NumberFormatException("bad value"));
            LOG.log(Level.INFO, "wrapped parse failure",
                    new IllegalStateException("outer",
                            new NumberFormatException("bad value")));
            LOG.log(Level.INFO, "network failure",
                    new IOException("timeout"));
            LOG.log(Level.WARNING, "parsing escalation",
                    new NumberFormatException("important"));
            LOG.info("application healthy");
        } finally {
            LOG.removeHandler(handler);
            handler.flush();
            handler.close();
        }
    }
}
~~~

Dùng JDK 17+:

~~~bash
javac --release 17 ExceptionFilterDemo.java
java ExceptionFilterDemo
~~~

**Standard error (stderr) chính xác:**

~~~text
INFO network failure
WARNING parsing escalation
INFO application healthy
~~~

**Standard output (stdout):** trống. `ConsoleHandler` mặc định ghi ra stderr; formatter của ví dụ chủ động chỉ in level và message để đầu ra ổn định. Chương trình kết thúc với exit code `0`.

**Giải thích theo từng sự kiện:**

| Sự kiện | Level | Exception | Kết quả |
| --- | --- | --- | --- |
| `expected parse failure` | INFO | `NumberFormatException` trực tiếp | **Drop** |
| `wrapped parse failure` | INFO | `IllegalStateException` → `NumberFormatException` | **Drop** vì cause khớp |
| `network failure` | INFO | `IOException` | **Keep** |
| `parsing escalation` | WARNING | `NumberFormatException` | **Keep** vì mức cao |
| `application healthy` | INFO | Không có exception | **Keep** |

`LOG.setLevel(Level.ALL)` và `handler.setLevel(Level.ALL)` đảm bảo chính filter quyết định việc loại bản ghi ở ví dụ. `LOG.setUseParentHandlers(false)` ngăn root handler in trùng; ngoài chương trình demo, cần tính đến chính sách của logger hierarchy.

**Các lựa chọn có chủ đích:**

- `instanceof NumberFormatException` nhận cả subclass (nếu có); không khớp mọi `IllegalArgumentException` khác.
- `IdentityHashMap` lưu các đối tượng Throwable đã đi qua theo identity để tránh lặp vô hạn nếu `cause` bất thường có chu kỳ. Đây là bảo vệ nhỏ trong một filter phải chạy nhanh.
- Không duyệt `getSuppressed()`; policy này chỉ theo chuỗi cause. Nếu cần xét suppressed exceptions, phải duyệt theo cây/đồ thị có tập `seen` và giới hạn tài nguyên.
- Filter không thay đổi hoặc bắt exception trong xử lý nghiệp vụ. Nó chỉ quyết định sự kiện nào xuất hiện trong console.
- Trong ứng dụng thực tế, loại `NumberFormatException` theo type có thể quá rộng. Nên thêm logger name, event code, context hoặc nhóm endpoint cụ thể để chỉ loại các trường hợp thực sự đã dự kiến.

## 5. Các bẫy khi gắn Throwable vào log event

### 5.1. In text không phải gắn Throwable

~~~java
try {
    Integer.parseInt("oops");
} catch (NumberFormatException ex) {
    LOG.info("Parse failed: " + ex); // Chỉ là chuỗi.
    LOG.log(Level.INFO, "Parse failed", ex); // Có Throwable.
}
~~~

Ở lệnh đầu, `LogRecord.getThrown() == null`; filter theo exception sẽ không nhận diện được dù message chứa tên class. Lệnh thứ hai đi qua overload `log(Level, String, Throwable)` để gắn đúng đối tượng. Tùy chính sách dữ liệu, không nên ghi nguyên văn `ex.getMessage()` nếu nó chứa dữ liệu cá nhân/bí mật.

Với SLF4J, lời gọi phổ biến:

~~~java
log.warn("Failed to process order", exception);
~~~

Đoạn này cần `log` là logger SLF4J đã khởi tạo. Các overload SLF4J thông thường đưa `Throwable` cuối làm thông tin lỗi cho backend. Trái lại, `log.warn("Failure: {}", exception.getMessage())` chỉ log chuỗi; event có thể không chứa Throwable. Khi dùng overload varargs hoặc fluent API, cần kiểm tra đúng cách truyền cause theo phiên bản đang dùng.

### 5.2. Exception bị bọc

Ví dụ bất đồng bộ:

~~~java
Throwable outer = new java.util.concurrent.CompletionException(
        new java.io.IOException("connection reset"));
~~~

Nếu chỉ kiểm tra `outer instanceof IOException` thì thất bại; đi vào `outer.getCause()` mới thấy `IOException`. Hệ thống cũng có thể dùng `ExecutionException`, `InvocationTargetException` hoặc exception wrapper của framework. Không suy đoán wrapper chỉ từ tên message.

### 5.3. Không có Throwable

Một sự kiện `log.error("Remote call failed")` có thể không mang exception. Nếu filter mặc định `DENY` khi `getThrown()==null`, bạn có thể vô tình mất rất nhiều lỗi không có stack trace. Với chính sách **loại vài exception đã dự kiến**, mặc định nên **giữ (keep/neutral)** tất cả event không khớp.

### 5.4. Exception không phải lúc nào cũng là sự cố

Một `NumberFormatException` có thể phản ánh lỗi nhập liệu đã xử lý; nhưng nó cũng có thể chỉ ra mã ứng dụng parse sai dữ liệu nội bộ. Do đó, cần điều kiện thêm như `eventId`, logger name, domain, route hoặc level. Không áp dụng quy tắc “đã từng gặp exception này” cho mọi service hoặc mọi môi trường.

## 6. Logback Classic: filter theo ThrowableProxy ở appender

Với ứng dụng dùng **SLF4J + Logback Classic**, Logback có regular appender filter bằng `ch.qos.logback.core.filter.Filter<ILoggingEvent>`. Sự kiện có `event.getThrowableProxy()` kiểu `IThrowableProxy`. Proxy có `getClassName()` và `getCause()`; đó không nhất thiết là cùng đối tượng `Throwable` ở code nghiệp vụ.

Ví dụ một class filter chỉ loại event **dưới WARN** nếu chuỗi exception có tên chính xác `java.lang.NumberFormatException`. Đây là code dành cho **dự án đã có Logback Classic** và sẽ cần đặt trong package được nêu ở đầu file.

Tạo tệp **src/main/java/com/example/logging/ExpectedParseFilter.java**:

~~~java
package com.example.logging;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.classic.spi.IThrowableProxy;
import ch.qos.logback.core.filter.Filter;
import ch.qos.logback.core.spi.FilterReply;

public final class ExpectedParseFilter extends Filter<ILoggingEvent> {
    @Override
    public FilterReply decide(ILoggingEvent event) {
        if (event.getLevel().isGreaterOrEqual(Level.WARN)) {
            return FilterReply.NEUTRAL;
        }

        IThrowableProxy exception = event.getThrowableProxy();
        // Giới hạn độ sâu để filter luôn có chi phí hữu hạn.
        for (int depth = 0; exception != null && depth < 32; depth++) {
            if ("java.lang.NumberFormatException"
                    .equals(exception.getClassName())) {
                return FilterReply.DENY;
            }
            exception = exception.getCause();
        }
        return FilterReply.NEUTRAL;
    }
}
~~~

Gắn nó vào một appender trong **logback.xml**:

~~~xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <filter class="com.example.logging.ExpectedParseFilter"/>
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger - %msg%n%ex</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

**Giải thích:**

- `DENY` nghĩa là bỏ event tại appender này; `NEUTRAL` nghĩa là nhường quyết định cho filter tiếp theo (nếu không còn filter nào chặn thì appender tiếp tục xử lý).
- `NEUTRAL` cho event WARN trở lên để không vô tình bypass các filter khác; không dùng `ACCEPT` chỉ vì muốn giữ event, bởi `ACCEPT` có thể kết thúc chuỗi filter của cùng giai đoạn.
- Kiểm tra `IThrowableProxy.getClassName()` bằng tên đầy đủ chỉ khớp **chính xác loại đó**, không tự xử lý mọi subclass. Nếu muốn khớp hierarchy, cần thiết kế thêm rule cho các loại cụ thể hoặc cơ chế so type có kiểm soát.
- Mẫu `<filter>` nằm trong appender `CONSOLE` nên chỉ tác động kênh này. Nếu đồng thời có appender audit/file riêng không gắn filter, bản ghi có thể vẫn xuất hiện ở đó.
- `ILoggingEvent.getThrowableProxy()` có thể là null; code giữ event không gắn exception.
- `%ex` của encoder dùng để **hiển thị stack trace** của event được giữ; việc có hay không có pattern stack trace không thay đổi quyết định của filter.

Đừng dùng `JaninoEventEvaluator` theo ví dụ cũ mà không kiểm tra phiên bản: **Logback 1.5.13 đã loại bỏ** evaluator này. Một custom filter Java đơn giản tránh sự phụ thuộc vào biểu thức cấu hình và dễ kiểm thử. Cần khớp đúng phiên bản `logback-classic`/`logback-core`/SLF4J của ứng dụng.

**Regular filter và TurboFilter:** regular filter có `ILoggingEvent` đầy đủ, thuận lợi để kiểm tra `ThrowableProxy`. TurboFilter chạy sớm hơn, trước hoặc trong quá trình tạo event và có tham số riêng; không thể bê nguyên phương thức `decide(ILoggingEvent)` vào TurboFilter. Với ứng dụng cần hiệu năng cao, đánh giá chi phí/độ chính xác và test overload logging thực tế trước khi đổi vị trí filter.

## 7. Log4j 2: phân biệt event filter và lọc text

Log4j 2 Core hỗ trợ các vị trí filter ở global configuration, logger configuration, appender reference và appender. Kết quả filter là:

| Kết quả | Ý nghĩa |
| --- | --- |
| `DENY` | Loại sự kiện tại giai đoạn lọc đang xét |
| `NEUTRAL` | Chưa quyết định; để các rule/level tiếp tục xử lý |
| `ACCEPT` | Chấp nhận ở giai đoạn hiện tại, có thể bỏ qua các filter/kiểm tra tiếp theo tùy vị trí |

Muốn xét exception thực sự, dùng `org.apache.logging.log4j.core.LogEvent.getThrown()` trong **custom filter/plugin phù hợp Log4j 2 Core**. API này trả về `Throwable` nếu có, vì vậy logic có thể xét `instanceof` và `getCause()` như ví dụ JUL.

Mã minh họa **phần logic trong một class filter Log4j 2 đã được khai báo và đăng ký đúng** (không phải class Java độc lập):

~~~java
@Override
public Result filter(LogEvent event) {
    if (event.getLevel().isMoreSpecificThan(Level.WARN)) {
        return Result.NEUTRAL;
    }
    for (Throwable cause = event.getThrown();
         cause != null;
         cause = cause.getCause()) {
        if (cause instanceof NumberFormatException) {
            return Result.DENY;
        }
    }
    return Result.NEUTRAL;
}
~~~

Đoạn logic này cần imports, class mở rộng API Filter của Log4j 2, plugin registration và cơ chế giới hạn vòng lặp `cause` trong triển khai thực tế. Khi dùng tên các class ở đây, `Level` là `org.apache.logging.log4j.Level` và `LogEvent` là `org.apache.logging.log4j.core.LogEvent`; chúng **không** phải các class tương ứng của JUL/Logback. `isMoreSpecificThan(Level.WARN)` được dùng để giữ WARN và các mức nghiêm trọng hơn.

**Không nhầm loại filter:**

- `RegexFilter` của Log4j 2 chủ yếu lọc theo nội dung message/chuỗi đã định dạng; nó **không phải kiểm tra cấu trúc cây Throwable bằng `instanceof`**.
- `ThresholdFilter` lọc theo level, không tự biết class exception.
- Pattern/layout hiển thị stack trace chỉ ảnh hưởng cách render bản ghi; muốn drop event cần filter trong pipeline.
- `DENY` ở cấp global/logger có phạm vi rộng hơn `DENY` ở một appender; cần thiết kế rõ kênh nào được phép mất log.

Trong ứng dụng có async logger/appender, chỗ đặt filter còn ảnh hưởng chi phí: lọc sau khi event đã vào queue có thể giúp giảm I/O nhưng không loại được toàn bộ chi phí enqueue. Lọc trước queue có thể tiết kiệm hơn nhưng phải giữ đúng ngữ nghĩa và khả năng nhận diện Throwable tại giai đoạn đó.

## 8. Nên filter trong code hay filter tại framework?

**Ở chỗ xử lý lỗi (source-level):**

~~~java
try {
    Integer.parseInt(rawInput);
} catch (NumberFormatException ex) {
    // Ví dụ: input không hợp lệ đã được xử lý theo nghiệp vụ.
    // Thống kê metric hoặc log một mã sự kiện ổn định nếu cần.
    log.debug("Invalid numeric input for field {}", fieldName);
}
~~~

Đây là đoạn minh họa trong ứng dụng có `rawInput`, `fieldName` và logger SLF4J `log`; không phải chương trình độc lập. Ưu điểm là người viết code biết bối cảnh: lỗi đã dự kiến hay bất thường. Nhược điểm là phải kiểm soát ở nhiều điểm ghi và có thể không can thiệp được thư viện ngoài.

**Ở framework (logger/appender filter):** tập trung một policy cho nhiều điểm ghi, hữu ích khi một dependency ghi nhiều exception dạng lặp. Nhưng nếu rule quá rộng, nó có thể che mất một lỗi mới có cùng exception type. Thích hợp khi policy đã được kiểm chứng với mẫu log thật và có kênh chẩn đoán thay thế.

Chọn theo phạm vi:

| Nhu cầu | Cách thường phù hợp |
| --- | --- |
| Không cần log ở trường hợp lỗi nhập liệu đã xử lý | Điều chỉnh lời gọi log tại nơi xử lý |
| Một appender console quá nhiễu, cần giữ file đầy đủ | Filter ở console appender/handler |
| Thư viện bên ngoài ghi exception thường xuyên | Filter theo logger name + exception + level |
| Cần liên kết exception với request/trace | Giữ MDC/trace ID và log cấu trúc, chưa vội drop |
| Cần audit, bảo mật hoặc độ bền | Không dựa vào filter loại bỏ toàn bộ bằng chứng; dùng kênh audit phù hợp |

## 9. Các vấn đề về cause, suppressed và ngoại lệ đa luồng

**Cause chain:** nhiều framework bọc exception gốc. Có thể xét toàn chuỗi `Throwable.getCause()`; đặt giới hạn hoặc tập identity khi code chạy trên dữ liệu bất thường để tránh tiêu tốn CPU.

**Suppressed exception:** `try-with-resources` có thể gắn ngoại lệ phát sinh khi đóng tài nguyên qua `getSuppressed()`, không nhất thiết nằm trong `cause`. Ví dụ JUL ở trên **không** xem suppressed exception. Nếu policy yêu cầu, dùng thuật toán duyệt đồ thị có cả cause và suppressed, tập visited và giới hạn số nút; test trường hợp error gốc khác error suppressed.

**Async và thread pool:** exception từ `Future.get()` thường được bọc bởi `ExecutionException`, từ chuỗi `CompletableFuture` có thể xuất hiện `CompletionException`. Cần xem Throwable **được truyền tới logger** chứ không tự giả định logger sẽ khai mở mọi nguyên nhân.

**Error khác Exception:** `Throwable` bao gồm cả `Error` như `OutOfMemoryError`, `StackOverflowError`. Đừng viết rule mặc định “drop mọi Throwable thuộc nhóm lỗi” chỉ để giảm noise, đặc biệt trong production. Khi hệ thống thiếu tài nguyên, filter phức tạp tự nó có thể tăng rủi ro: tránh tạo stack trace mới, I/O hoặc lock trong filter.

**Runtime context:** exception cùng class ở hai service hoặc hai nhánh xử lý có thể mang ý nghĩa khác nhau. Kết hợp logger name, event code, trace ID và level giúp phân loại đúng hơn so với chỉ class name.

## 10. Hiệu năng và an toàn của custom filter

Filter có thể được gọi với **mỗi sự kiện log**. Thực hành tốt:

1. Dùng điều kiện nhanh trước: level, logger name, event code; chỉ duyệt cause khi thật sự cần.
2. Ưu tiên so loại bằng `instanceof` hoặc danh sách tên class chuẩn xác; tránh tạo regex/stack trace mới cho mỗi event.
3. Viết filter thuần hàm theo event, tránh trạng thái mutable không đồng bộ. Ví dụ JUL dùng biến cục bộ và có thể được gọi từ nhiều thread.
4. Giới hạn độ sâu cause/suppressed khi cần và kiểm soát ngoại lệ bất thường trong filter. Không làm sink log thất bại vì filter ném exception không được xử lý.
5. Không gửi request mạng hoặc ghi log lại bằng chính logger đang lọc trong `isLoggable/decide`: dễ gây đệ quy, deadlock hoặc tăng độ trễ.
6. Đếm số sự kiện đã drop bằng metric hoặc bộ đếm phù hợp nếu policy yêu cầu, nhưng tránh mỗi lần drop lại tạo một event log mới qua cùng pipeline.
7. Nếu lọc làm giảm log thành phần, giữ số liệu lỗi, latency, status code và cảnh báo từ hệ thống giám sát; thiếu log không đồng nghĩa lỗi đã biến mất.
8. Khi filter dựa vào tên exception như proxy Logback, cân nhắc rủi ro đổi tên class/package qua nâng cấp thư viện.

Đánh giá chi phí thực tế bằng benchmark theo lưu lượng, không chỉ dựa vào số dòng filter. Với ứng dụng có hàng nghìn event/giây, việc phân tích stack trace hoặc regex dài ở mỗi event có thể làm mất lợi ích của async logging.

## 11. Bộ kiểm thử tối thiểu

Các trường hợp cần kiểm tra **trước và sau** khi bật filter:

| Test | Exception và level | Kỳ vọng của policy demo |
| --- | --- | --- |
| Trực tiếp | `NumberFormatException`, INFO | Bị loại ở console |
| Bị bọc | `IllegalStateException → NumberFormatException`, INFO | Bị loại ở console |
| Không khớp | `IOException`, INFO | Được giữ |
| Lỗi nghiêm trọng | `NumberFormatException`, WARNING | Được giữ |
| Không có Throwable | INFO bình thường | Được giữ |
| Message có tên exception nhưng không gắn `Throwable` | INFO | Được giữ |
| Exception subclass | Một subclass của loại policy | Xác nhận hành vi match theo `instanceof` (hoặc tên proxy) |
| Chuỗi dài/có chu kỳ | Cause lạ hoặc sâu | Không treo; có giới hạn xử lý |
| Nhiều thread đồng thời | Log hỗn hợp có/không có Throwable | Không race, không leak event khác |
| Appender khác | Cùng event đi file và console | Xác nhận scope filter đúng |
| Async queue/shutdown | Event chờ khi kết thúc chương trình | Drain/flush theo cơ chế framework; không nhầm filter với bảo đảm lưu |

Với Logback/Log4j 2, sử dụng test appender hoặc sink tạm và **khởi tạo đúng framework version** trong test. Đừng chỉ assert code trả về `DENY`; cần kiểm tra bản ghi thực sự vắng mặt/hiện diện ở đúng sink. Nếu không gắn Throwable đúng overload, test sẽ không đo policy exception.

Một phương pháp kiểm tra nhanh có thể dùng các event có ID ổn định:

~~~text
exception-filter-check id=E1 type=NumberFormatException level=INFO  -> console: none
exception-filter-check id=E2 type=IOException          level=INFO  -> console: E2
exception-filter-check id=E3 type=NumberFormatException level=WARN -> console: E3
~~~

Đây là **bảng kỳ vọng kiểm thử**, không phải stdout của chương trình Java ở mục 4.

## 12. Sai lầm phổ biến

| Sai lầm | Hệ quả | Cách tránh |
| --- | --- | --- |
| Chỉ lọc `exception.getMessage()` | Phụ thuộc text, dễ sai và lộ dữ liệu | Dùng Throwable/proxy và loại exception |
| Dùng `getThrown() == null` để drop hết | Mất log lỗi không mang stack trace | Mặc định giữ event không khớp |
| Kiểm tra chỉ exception ngoài cùng | Bỏ sót cause bị bọc | Duyệt `getCause()` với giới hạn/visited |
| Bỏ qua level hoặc audit | Xóa cảnh báo quan trọng | Giữ WARN/ERROR và kênh audit |
| Dùng `ACCEPT` cho mọi event muốn giữ | Có thể bypass các filter khác cùng giai đoạn | Dùng `NEUTRAL` khi chưa muốn kết thúc chuỗi |
| Gắn filter vào root/global mà không xác định scope | Loại log ở nhiều sink ngoài dự kiến | Gắn đúng appender/handler trước |
| Dùng `RegexFilter` để “match exception class” | Lọc message chứ không kiểm tra Throwable | Dùng custom filter dựa trên event |
| Log event chỉ chứa `ex.toString()` | `getThrown()` null | Truyền exception vào overload hỗ trợ Throwable |
| Filter gọi lại logger hoặc làm network I/O | Đệ quy, nghẽn và deadlock | Giữ filter nhanh, side effect tối thiểu |
| Lọc làm mất mọi tín hiệu lỗi | Điều tra sự cố không còn bằng chứng | Giữ metric và sampling hoặc kênh đầy đủ |
| Copy code JUL sang Logback/Log4j 2 | Khác API, loại level, semantics | Dùng API đúng theo backend |
| Cho rằng filter đồng nghĩa bắt exception | Lỗi nghiệp vụ vẫn xảy ra | Xử lý exception trong code; filter chỉ quyết định log |

## 13. Câu hỏi tự kiểm tra

1. Vì sao `logger.log(Level.INFO, "failed: " + ex)` thường không cho phép filter JUL nhận diện exception qua `LogRecord.getThrown()`?
2. Nếu `CompletionException` bọc `IOException`, kiểm tra mỗi Throwable ngoài cùng có đủ không?
3. Tại sao filter ở `ConsoleHandler` chỉ làm mất log ở console, trong khi filter ở logger có thể ảnh hưởng nhiều handler?
4. Vì sao policy “drop NumberFormatException ở INFO” phải giữ nguyên WARNING/SEVERE trong ví dụ?
5. Khi sử dụng Logback `IThrowableProxy.getClassName()` để so chuỗi, nó có tự động nhận diện subclass không?
6. `DENY`, `NEUTRAL` và `ACCEPT` khác nhau ở điểm nào?
7. Vì sao `Throwable.getSuppressed()` cần được xét riêng khi policy yêu cầu phân tích toàn bộ lỗi?
8. Khi nào điều chỉnh code ghi log ở chỗ xử lý exception phù hợp hơn một filter chung?
9. Làm thế nào kiểm tra filter đang làm giảm noise mà không che khuất sự cố mới?
10. Nếu async appender đã chấp nhận event, filter ở sink có bảo đảm event đã được lưu bền vững không?

**Gợi ý trả lời:** (1) exception chỉ được nối vào text; (2) phải duyệt cause; (3) phạm vi lọc khác nhau; (4) tránh che tín hiệu nghiêm trọng; (5) không, so tên class là exact match; (6) drop, tiếp tục đánh giá, hoặc kết thúc lựa chọn ở giai đoạn tùy framework; (7) suppressed không nằm bắt buộc trong cause chain; (8) khi source biết lỗi đã dự kiến và điều kiện nghiệp vụ; (9) dùng test và metric drop/error; (10) không, lọc không đồng nghĩa flush/durability.

## 14. Tài liệu chính thức

- [Java 17 — java.util.logging.Filter](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Filter.html): hợp đồng `isLoggable(LogRecord)`.
- [Java 17 — LogRecord](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html): `getThrown()`, `getLevel()`.
- [Java 17 — Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): overload ghi Throwable, logger-level filter, parent handlers.
- [Java 17 — Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html): handler-level filter và level.
- [Logback — Filters](https://logback.qos.ch/manual/filters.html): regular filters, TurboFilters, `DENY/NEUTRAL/ACCEPT`.
- [Logback — ILoggingEvent](https://logback.qos.ch/apidocs/ch.qos.logback.classic/ch/qos/logback/classic/spi/ILoggingEvent.html): `getThrowableProxy()`.
- [Log4j 2 — Filters](https://logging.apache.org/log4j/2.x/manual/filters.html): các vị trí filter và semantics.
- [Log4j 2 — LogEvent](https://logging.apache.org/log4j/2.x/javadoc/log4j-core/org/apache/logging/log4j/core/LogEvent.html): `getThrown()` của sự kiện.

