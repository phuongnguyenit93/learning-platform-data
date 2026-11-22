# Filter theo message trong Java Logging

## 1. “Filter theo message” giải quyết bài toán gì?

Trong một ứng dụng Java, không phải thông điệp nào đã vượt qua mức log (`INFO`, `WARN`, `ERROR`...) cũng cần được ghi tới mọi đích. Ví dụ một service có hàng nghìn log `GET /actuator/health 200` mỗi phút; chúng hữu ích khi chẩn đoán probe, nhưng có thể che khuất sự kiện nghiệp vụ khi vận hành bình thường. **Message filtering** cho phép kiểm tra *nội dung thông điệp* của một log event rồi quyết định có cho event đi tiếp tới logger/appender/handler hoặc pipeline hay không.

Một yêu cầu thực tế:

- Loại các dòng **INFO** chứa mẫu `GET /actuator/health` khỏi console.
- **Giữ nguyên WARN/ERROR**, kể cả khi thông điệp có cùng chuỗi, vì tình huống health check lỗi có ý nghĩa vận hành.
- Tiếp tục lưu event INFO vào file điều tra nếu chính sách yêu cầu.
- Không lọc những thông điệp nghiệp vụ khác chỉ vì chúng vô tình chứa chữ “health”.

Chẳng hạn:

| Event được phát sinh | Console mong muốn | File ứng dụng mong muốn | Vì sao |
| --- | --- | --- | --- |
| `INFO GET /actuator/health 200` | Bỏ | Giữ nếu cần | Probe thành công gây nhiều nhiễu |
| `INFO order=42 created` | Giữ | Giữ | Sự kiện nghiệp vụ |
| `WARN GET /actuator/health 503` | Giữ | Giữ | Probe lỗi là tín hiệu quan trọng |
| `ERROR payment timeout` | Giữ | Giữ | Không được bỏ lỗi nghiệp vụ |
| `DEBUG GET /actuator/health 200` | Tùy logger level | Tùy logger level | Event DEBUG có thể bị loại trước bước message filter |

Bộ lọc theo message dùng khi thật sự cần quyết định dựa trên text. Với dữ liệu có cấu trúc và sự kiện ổn định, thường tốt hơn khi lọc theo **event code, logger name, Marker, MDC/ThreadContext hoặc structured attributes**; chúng ít phụ thuộc cách viết câu hơn.

## 2. Phân biệt logger level với message filter

Một luồng xử lý đơn giản:

```text
logger.info("GET /actuator/health {}", status)
                  │
                  ▼
        Level/logger có enable INFO?
             │ Không → dừng
             │ Có
             ▼
       Tạo logging event
             │
             ▼
      Filter (logger hoặc appender)
             │
      ┌──────┼────────────┐
      ▼      ▼            ▼
    DENY   NEUTRAL       ACCEPT
     bỏ   lọc tiếp/     chấp nhận ở
           quy tắc       phạm vi filter
           mặc định
             │
             ▼
     Layout/Encoder → sink
```

Vị trí filter thực tế thay đổi theo framework. Ví dụ Logback có `TurboFilter` được đánh giá sớm trong logging context và regular `Filter<ILoggingEvent>` gắn vào appender sau khi có logging event; Log4j 2 cho phép đặt filter ở nhiều mức, gồm context/logger/appender/appender-reference; JUL có `Filter` ở `Logger` hoặc `Handler`.

Cần phân biệt:

1. **Level filter** xét độ nghiêm trọng: `INFO`, `WARN`, `ERROR`...
2. **Message filter** xét nội dung: bắt đầu bằng, chứa chuỗi, khớp regex hoặc một predicate tùy chỉnh.
3. **Routing** xác định đích nào nhận event: console, file, remote appender...
4. **Formatting** quyết định dòng cuối cùng được in thế nào: mẫu thông điệp, tham số, timestamp, exception, MDC, JSON...

Nếu logger đã chặn `DEBUG`, bộ lọc theo message ở appender **không thể khôi phục** event DEBUG đó. Tương tự, lọc ở appender console không nhất thiết loại event khỏi appender file. Tránh mô tả message filter như một cách “đổi log level”; nó là một quy tắc quyết định trên event hoặc trên message.

## 3. Message thô và message đã format là hai thứ khác nhau

Nhiều API logging hỗ trợ message template và tham số:

```java
logger.info("GET /actuator/health status={}", statusCode); // SLF4J
```

Trong trường hợp này:

- **Raw message/template** là `GET /actuator/health status={}`.
- **Formatted message** có thể là `GET /actuator/health status=200`.
- Thông điệp cuối cùng được layout ghi ra còn có thể thêm timestamp, level, logger name, MDC, exception.

Với JUL:

```java
logger.log(Level.INFO, "Order {0} created", 42);
```

`LogRecord.getMessage()` trả về `Order {0} created`; `Formatter.formatMessage(record)` mới thực hiện bước thay placeholder (`MessageFormat`) để nhận `Order 42 created`. Vì vậy:

- Filter so sánh template ổn định: thường rẻ và ít thay đổi theo giá trị tham số.
- Filter phải tìm `status=500` trong text hoàn chỉnh: cần xét **formatted message** hoặc tốt hơn là xét trường status có cấu trúc.
- Tìm chuỗi `"500"` trên raw message có thể bỏ sót event vì số đó chỉ nằm trong tham số.
- Tìm chuỗi trên *dòng output* có thể dính prefix, exception, escaping và pattern khác nhau; không được mặc định rằng message filter sẽ thấy toàn bộ dòng text đã ghi ra file.

**Chốt rõ mình đang lọc ở cấp nào:** template, formatted message hay log record có thuộc tính. Quy tắc dựa vào text hiển thị cuối thường dễ vỡ khi ứng dụng đổi ngôn ngữ, format hoặc logging backend.

## 4. Các kiểu so khớp phổ biến

| Kiểu | Ví dụ điều kiện | Phù hợp | Hạn chế |
| --- | --- | --- | --- |
| Exact equality | `message.equals("GET /health 200")` | Event text được kiểm soát chặt | Chỉ cần đổi tham số/khoảng trắng là sai |
| Prefix | `message.startsWith("HEALTH_CHECK")` | Có tiền tố cố định | Có thể trùng với message không liên quan |
| Substring | `message.contains("GET /actuator/health")` | Loại nhiễu dễ nhận diện | Chỉ cần câu chứa chuỗi là bị ảnh hưởng |
| Regex | `Pattern.compile("^GET /health status=2\\d\\d$")` | Mẫu có quy tắc vị trí/biến thể | Tốn CPU và dễ khớp sai nếu regex rộng |
| Predicate kết hợp | `level < WARN && message.contains(...)` | Có điều kiện giữ log quan trọng | Logic cần test theo nhiều chiều |
| Trường cấu trúc | `eventType == HEALTH_PROBE && status < 500` | Sự kiện có schema ổn định | Cần thống nhất metadata trong code |

Một regex không tự động tốt hơn `contains()`. Nếu chỉ cần kiểm tra một literal, `contains()` rõ và thường rẻ hơn. Nếu cần tránh khớp `GET /healthz` với `GET /health`, có thể dùng anchor/biên từ phù hợp, nhưng phải kiểm tra thực tế với dấu slash, dấu cách, Unicode và các ký tự escape.

Ví dụ trong Java:

```java
import java.util.regex.Pattern;

Pattern pattern = Pattern.compile(
        "^GET /actuator/health status=2\\d{2}$");
boolean probeOk = pattern.matcher(message).matches();
```

`matches()` đòi hỏi **toàn bộ** chuỗi thỏa regex; `find()` chỉ cần **một đoạn** con khớp. Không thể thay hai API cho nhau mà giữ nguyên ý nghĩa. Pattern nên được **compile một lần** và tái sử dụng, không compile lại trên từng event khi lưu lượng lớn.

### 4.1. Ưu tiên giữ log lỗi

Quy tắc an toàn cho ví dụ health probe:

```text
IF level >= WARN:
    giữ event
ELSE IF message chứa "GET /actuator/health":
    bỏ event
ELSE:
    giữ event
```

Điều kiện level đứng đầu nhằm **không vô tình nuốt cảnh báo hoặc lỗi** khi đường dẫn health xuất hiện trong message. Trong hệ thống thật, cần thống nhất ý nghĩa các level của framework (Logback/Log4j 2 có WARN/ERROR; JUL dùng WARNING/SEVERE), không so sánh tên level bằng thứ tự alphabet.

## 5. Ví dụ Java 17+ chạy độc lập: java.util.logging.Filter

JDK có sẵn `java.util.logging.Filter`, phương thức `boolean isLoggable(LogRecord record)`. Khi gắn Filter vào `Handler`, nó quyết định một record có được handler đó ghi hay không. Ví dụ này **không cần SLF4J hoặc framework ngoài**.

Lưu thành `MessageFilterDemo.java`:

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Filter;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class MessageFilterDemo {
    private static final class OneLineFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            return record.getLevel().getName()
                    + " " + formatMessage(record) + "\n";
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.message.filter");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);

        Handler console = new ConsoleHandler();
        console.setLevel(Level.ALL);
        console.setFormatter(new OneLineFormatter());

        Filter keepImportantLogs = record -> {
            if (record.getLevel().intValue()
                    >= Level.WARNING.intValue()) {
                return true;
            }
            String rawMessage = record.getMessage();
            return rawMessage == null
                    || !rawMessage.startsWith("[HEALTH]");
        };
        console.setFilter(keepImportantLogs);
        logger.addHandler(console);

        try {
            logger.info("[HEALTH] GET /health -> 200");
            logger.info("order=42 created");
            logger.warning("[HEALTH] GET /health -> 503");
            logger.severe("payment gateway timeout");
        } finally {
            logger.removeHandler(console);
            console.close();
        }
    }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac --release 17 MessageFilterDemo.java
java MessageFilterDemo
```

`ConsoleHandler` của JUL mặc định ghi vào **stderr**. Vì vậy stdout của lệnh Java **trống**; stderr chứa chính xác:

```text
INFO order=42 created
WARNING [HEALTH] GET /health -> 503
SEVERE payment gateway timeout
```

Nếu terminal gộp stdout/stderr, người dùng vẫn nhìn thấy ba dòng trên. Chương trình cố ý sử dụng một logger riêng, `setUseParentHandlers(false)` và formatter ổn định để không bị handler cha tạo thêm dòng hoặc in timestamp khác. `close()` đóng handler sau khi dùng; nếu bỏ một filter vào logger dùng chung, phạm vi lọc sẽ khác.

Giải thích kết quả:

1. `INFO [HEALTH] ... 200` bị bỏ do raw message bắt đầu bằng `[HEALTH]` và level dưới WARNING.
2. `INFO order=42 created` vẫn được ghi.
3. `WARNING [HEALTH] ... 503` được giữ vì điều kiện kiểm tra WARNING đứng trước substring.
4. `SEVERE payment gateway timeout` được giữ.

Ví dụ chọn raw message để tránh format trước khi lọc. Nếu bài toán yêu cầu lọc theo **giá trị tham số đã render**, dùng thuộc tính riêng hoặc custom formatter/predicate có ý thức về tham số.

### 5.1. Khác biệt nếu gắn filter vào Logger

Vẫn cùng predicate nhưng:

```java
logger.setFilter(keepImportantLogs);
```

Khi filter gắn vào logger, nó chặn record tại nguồn logger; các handler nhận event từ logger này đều chịu tác động. Khi filter chỉ ở `console.setFilter(...)`, handler file khác vẫn có thể nhận event bị console bỏ. Ở JUL, logger/handler filter đều kết hợp với level check; `true` từ filter **không vượt qua** level đã tắt.

Nếu thêm `FileHandler` riêng, phải cấu hình `Formatter`, `level` và `Filter` tương ứng. Đừng gắn cả logger-level và handler-level cùng logic rồi khó giải thích vì sao log bị mất trên nhiều đích.

### 5.2. JUL và thông điệp tham số

Đoạn sau minh họa khác nhau giữa text thô và text đã format:

```java
logger.log(Level.INFO, "Order {0} created", 42);
```

Trong filter, `record.getMessage()` là `Order {0} created`, không phải `Order 42 created`. Trong `OneLineFormatter`, `formatMessage(record)` cho output `Order 42 created`. Do đó, nếu filter dùng `getMessage().contains("42")`, kết quả sẽ không như mong muốn. Nếu phải ra quyết định bằng mã order, cân nhắc giữ mã đó thành dữ liệu có cấu trúc riêng; lọc theo template và số đã render thường gây khó bảo trì.

## 6. Logback: custom Filter theo message của ILoggingEvent

Trong ứng dụng Java sử dụng **SLF4J + Logback**, regular filter có thể được gắn trực tiếp vào một appender. Để vừa loại dòng probe INFO, vừa giữ WARN/ERROR, viết một class filter rõ ràng. Ví dụ dùng Logback Classic tương thích với API `ch.qos.logback.classic.spi.ILoggingEvent`.

File `src/main/java/com/example/logging/HealthMessageFilter.java`:

```java
package com.example.logging;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.filter.Filter;
import ch.qos.logback.core.spi.FilterReply;

public final class HealthMessageFilter extends Filter<ILoggingEvent> {
    @Override
    public FilterReply decide(ILoggingEvent event) {
        if (event == null) {
            return FilterReply.NEUTRAL;
        }
        if (event.getLevel().toInt() >= Level.WARN_INT) {
            return FilterReply.NEUTRAL;
        }
        String message = event.getFormattedMessage();
        if (message != null
                && message.contains("GET /actuator/health")) {
            return FilterReply.DENY;
        }
        return FilterReply.NEUTRAL;
    }
}
```

Đây là **class dùng trong dự án đã có dependency Logback Classic**, không thể biên dịch độc lập chỉ với JDK. `getFormattedMessage()` chọn thông điệp sau khi thay placeholder của SLF4J. `FilterReply.DENY` chặn event ở appender này; `NEUTRAL` để các filter còn lại/mặc định xử lý. Vì level của logger được kiểm tra riêng, `NEUTRAL` không “bật” DEBUG nếu logger không enable DEBUG.

Gắn filter vào console trong `src/main/resources/logback-spring.xml` của Spring Boot (hoặc cấu hình Logback tương ứng của ứng dụng):

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <filter class="com.example.logging.HealthMessageFilter"/>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="FILE" class="ch.qos.logback.core.FileAppender">
        <file>logs/application.log</file>
        <append>true</append>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
        <appender-ref ref="FILE"/>
    </root>
</configuration>
```

**Kết quả mong đợi:** console không in các message INFO có `GET /actuator/health`; file vẫn ghi chúng vì không có filter đó. WARN/ERROR đến console và file nếu đã vượt logger level. Đường dẫn `logs/application.log` phụ thuộc working directory và quyền ghi; ví dụ file appender đơn giản này **chưa cấu hình rolling/retention** nên không dùng nguyên trạng cho hệ thống chạy lâu ngày có nhiều log.

Nếu muốn bỏ probe INFO ở **cả** console và file, có thể gắn filter phù hợp ở cả hai appender hoặc dùng cơ chế filter tại logging context sau khi xác định rõ phạm vi. Không chỉ thêm filter vào một appender rồi kết luận event biến mất khỏi toàn ứng dụng.

### 6.1. “Raw” và “formatted” trong Logback

`ILoggingEvent.getMessage()` lấy template trước khi thay placeholder; `ILoggingEvent.getFormattedMessage()` lấy message sau khi format. Với:

```java
log.info("GET /actuator/health status={}", statusCode);
```

- `getMessage()`: `GET /actuator/health status={}`.
- `getFormattedMessage()`: `GET /actuator/health status=200` nếu `statusCode=200`.

Dùng `getMessage()` nếu chính sách nhận diện **template cố định** và tránh chi phí render tham số. Dùng `getFormattedMessage()` khi phải xét nội dung đã thay tham số, nhưng cần đo overhead và cẩn trọng với `toString()` của object. Đừng đưa object đắt đỏ vào log chỉ để filter sau đó bỏ event.

### 6.2. Về EvaluatorFilter và cấu hình Janino cũ

Trong Logback, `EvaluatorFilter` có thể dùng một `EventEvaluator` chuyên biệt; tuy nhiên một số bài hướng dẫn cũ sử dụng `JaninoEventEvaluator` với expression nhúng trong XML. **Theo tài liệu Logback, `JaninoEvaluator` đã bị loại bỏ từ phiên bản 1.5.13 vì lý do bảo mật**. Với phiên bản hiện đại, nên dùng custom `Filter<ILoggingEvent>` như trên hoặc viết một `EventEvaluator` Java chuyên dụng, tránh dựa vào snippets Janino cũ có thể không còn chạy.

### 6.3. Vì sao không nên trả ACCEPT cho mọi message không khớp?

Trong Logback, `ACCEPT` cho phép bỏ qua các filter còn lại của cùng chain; `NEUTRAL` cho phép tiếp tục kiểm tra. Nếu một filter lọc theo message trả `ACCEPT` với mọi event không khớp, một filter tiếp theo dành cho dữ liệu nhạy cảm hoặc policy khác có thể không được thực hiện. Vì vậy, custom filter ở trên trả `DENY` khi đúng điều kiện cần loại, còn lại là `NEUTRAL`.

Nếu dùng nhiều filter, phải nêu rõ quy tắc ưu tiên: chẳng hạn filter bảo vệ dữ liệu nhạy cảm không được bị bỏ qua chỉ vì filter message trước đó trả ACCEPT.

## 7. Log4j 2: StringMatchFilter và RegexFilter

Log4j 2 có các filter cấu hình bằng XML. Theo tài liệu Log4j 2 hiện hành:

- `StringMatchFilter` khớp nếu **formatted message chứa chuỗi text** chỉ định.
- `RegexFilter` dùng regex, và **phải khớp toàn bộ message**; muốn tìm substring cần có `.*` hoặc một biểu thức bao phủ phần còn lại.
- `RegexFilter useRawMsg="false"` là mặc định, xét message đã format; `useRawMsg="true"` xét message thô theo loại `Message` hỗ trợ.
- Cả filter đều có `onMatch`, `onMismatch` và có thể giảm hiệu suất khi phải format message chỉ để quyết định bỏ.

### 7.1. Dùng StringMatchFilter và giữ WARN/ERROR

Ví dụ một ứng dụng đã có **Log4j 2 Core** làm backend, file `src/main/resources/log4j2.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <Filters>
                <ThresholdFilter level="WARN"
                    onMatch="ACCEPT" onMismatch="NEUTRAL"/>
                <StringMatchFilter
                    text="GET /actuator/health"
                    onMatch="DENY" onMismatch="NEUTRAL"/>
            </Filters>
            <PatternLayout pattern="%d{HH:mm:ss.SSS} %-5p %c - %m%n"/>
        </Console>

        <File name="FILE" fileName="logs/application.log"
              append="true">
            <PatternLayout
                pattern="%d{yyyy-MM-dd HH:mm:ss.SSS} %-5p %c - %m%n"/>
        </File>
    </Appenders>

    <Loggers>
        <Root level="INFO">
            <AppenderRef ref="CONSOLE"/>
            <AppenderRef ref="FILE"/>
        </Root>
    </Loggers>
</Configuration>
```

Với console:
1. `ThresholdFilter` trả `ACCEPT` cho `WARN`/`ERROR`, dừng chuỗi filter của appender console nên các event quan trọng được giữ.
2. Event dưới WARN tiếp tục (`NEUTRAL`) đến `StringMatchFilter`; nếu chứa `GET /actuator/health` thì `DENY`, còn lại tiếp tục bình thường.
3. File appender không đặt message filter nên nhận các event đã enable ở root.

Ở đây việc dùng `ACCEPT` có chủ đích để **ưu tiên WARN/ERROR hơn bộ lọc loại probe**; cần xem xét những filter khác nếu thêm vào sau. Ví dụ chỉ minh họa message filtering, **chưa có rotation, retention và quản lý file production**. Với Spring Boot, bảo đảm classpath chỉ có một backend/provider SLF4J tương thích và ứng dụng thực sự load cấu hình Log4j 2.

### 7.2. Khi cần regex thay cho substring

Có thể thay riêng `StringMatchFilter` trong ví dụ bằng:

```xml
<RegexFilter
    regex=".*GET /actuator/health.*"
    useRawMsg="false"
    onMatch="DENY"
    onMismatch="NEUTRAL"/>
```

Từ khóa `.*` hai đầu cần thiết vì Log4j 2 `RegexFilter` khớp **cả message**, không phải tự động tìm một đoạn con như `String.contains`. Nếu regex là `GET /actuator/health`, một message `INFO GET /actuator/health 200` thường **không khớp nguyên chuỗi**.

Một regex chặt hơn có thể nhận diện đúng bản ghi có prefix cấu trúc, nhưng nên viết test với thông điệp thật thay vì mở rộng bằng `.*` một cách thiếu kiểm soát. `useRawMsg="false"` có chi phí format; `true` có thể làm regex bỏ sót giá trị chỉ có trong tham số. Lựa chọn này là một quyết định về semantics và hiệu suất, không chỉ là một tùy chọn cú pháp.

### 7.3. Filter ở appender, logger hay AppenderRef?

Log4j 2 có thể đặt filter ở **context, logger, appender hoặc appender reference**. Filter trên console appender ảnh hưởng những event đi qua console đó; filter ở AppenderRef ảnh hưởng đường tham chiếu tương ứng; filter trên logger có phạm vi rộng hơn trước khi route tới các đích. Nếu đặt cùng điều kiện ở cả logger và appender, có thể làm mất event ở file dù dự định chỉ làm sạch console.

Đặc biệt, chính sách `onMismatch="DENY"` với filter “chỉ deny khi khớp” có thể gây hậu quả ngược: **mọi message không khớp** cũng bị loại. Khi mục tiêu chỉ loại noise, chọn `onMatch="DENY" onMismatch="NEUTRAL"`.

## 8. Filtering trước hay sau queue logging bất đồng bộ?

Thời điểm filter được áp dụng quyết định chi phí. Với một appender async:

```text
Caller thread
     │
     ├─ message filter trước queue ──(được giữ)──> [Async Queue] -> Sink
     │                                       │
     └─(bị loại) không enqueue                └─ Filter ở sink sau queue?
```

Nếu filter gắn **trên AsyncAppender** và chạy lúc nhận event, log bị loại trước khi enqueue, giảm số phần tử trong queue. Nếu chỉ lọc ở **appender đích nằm phía sau queue**, event có thể đã chiếm slot queue, tiêu tốn bộ nhớ và thời gian dequeue/format trước khi bị loại. Hãy xác định chính xác cấu trúc appender đang dùng; không mặc định tất cả logging framework áp dụng filter trước queue.

Ví dụ Logback có `ASYNC_FILE` bọc một `FILE` appender đã được định nghĩa:

```xml
<appender name="ASYNC_FILE"
          class="ch.qos.logback.classic.AsyncAppender">
    <filter class="com.example.logging.HealthMessageFilter"/>
    <queueSize>1024</queueSize>
    <discardingThreshold>0</discardingThreshold>
    <neverBlock>false</neverBlock>
    <appender-ref ref="FILE"/>
</appender>
```

Nếu mục tiêu là loại probe khỏi file, filter trên `ASYNC_FILE` xử lý trước khi event được đưa tới queue của nó; root nên tham chiếu `ASYNC_FILE` thay vì đồng thời tham chiếu cả `ASYNC_FILE` và `FILE` trực tiếp. Đây là **đoạn cấu hình bổ sung vào hệ thống đã khai báo FILE**, không phải file XML độc lập hoàn chỉnh.

- `queueSize` tính bằng event, không phải byte.
- `discardingThreshold=0` tắt chính sách discard sớm các log mức thấp của Logback AsyncAppender, nhưng không bảo đảm zero-loss.
- `neverBlock=false` cho phép producer chờ khi đầy; đổi sang `true` có thể làm drop event.
- Một async queue lỗi hoặc shutdown sớm vẫn có thể mất log **khác với** việc chủ động loại event theo message policy.

Đừng dùng message filter để giấu tác động của log volume mà không đo: có thể cần giảm log ở nguồn, hạ level có chọn lọc, throttle/rate-limit hoặc điều chỉnh health access logging riêng.

## 9. Chi phí hiệu năng của lọc theo nội dung

**Đặc tính hiệu suất phụ thuộc nơi lọc và cách dựng message**:

1. **Level check trước:** `DEBUG` bị tắt thì tránh tạo event và kiểm tra message (tùy framework). Đây thường là hàng rào rẻ nhất.
2. **Message raw/template:** kiểm tra literal có thể tránh format tham số và gọi `toString()` đắt đỏ.
3. **Formatted message:** đôi khi cần tạo String hoàn chỉnh dù sau đó bị DENY; chi phí này vẫn xảy ra trên thread gọi log nếu filter chạy tại đó.
4. **Regex:** compile pattern một lần, tránh biểu thức có backtracking quá mức khi message đến từ dữ liệu không tin cậy. Test worst-case input dài.
5. **I/O chỉ sau khi filter cho phép:** loại sớm giảm áp lực appender, disk, network và quota backend; loại quá muộn chỉ giảm bytes cuối cùng, chưa chắc giảm queue pressure.
6. **Async:** tăng thông lượng đỉnh có thể làm backlog lớn hơn nếu sink chậm; filter đặt đúng chỗ là một phần tối ưu nhưng cần xem queue-full policy.

Không đưa biểu thức regex do người dùng cung cấp trực tiếp vào logger filter. Regex phức tạp có thể gây tốn CPU bất thường; đầu ra log cũng có thể chứa input do bên ngoài kiểm soát. Bắt đầu bằng một danh sách event code rõ ràng thường an toàn, đo được và dễ review hơn.

Một chính sách lọc tối ưu cần quan sát được **tỷ lệ bị lọc**. Nếu hàng triệu probe log bị bỏ nhưng production không có số liệu về chúng, người vận hành có thể không nhận ra hành vi probe đã thay đổi. Có thể theo dõi counter/metrics tổng hợp thay cho giữ từng log INFO.

## 10. Rủi ro: lọc mất tín hiệu quan trọng và thông tin nhạy cảm

Message filtering có thể làm mất dữ liệu theo những cách khó thấy:

- **Substring quá rộng:** bỏ mọi dòng chứa “timeout” có thể loại đúng log báo sự cố quan trọng.
- **Thay đổi ngôn ngữ:** `"payment failed"` thành `"thanh toán lỗi"` khiến filter không còn khớp.
- **Thay đổi template:** thêm prefix hoặc placeholder làm quy tắc exact/prefix mất tác dụng.
- **Kết quả formatted thay đổi:** `toString()` của object hoặc locale khiến filter phụ thuộc nội dung động.
- **Exception/stack trace:** `getFormattedMessage()` thường chỉ là nội dung chính, **không phải toàn bộ stack trace** cuối được encoder/layout in ra. Nếu muốn quyết định dựa trên exception class, nên xét thuộc tính throwable chuyên biệt.
- **Log injection/newline:** nếu message chứa chuỗi do client gửi, kẻ tấn công có thể khiến log trông như nhiều event. Filter substring không thay thế escaping/structured logging.
- **MDC context:** filter theo message không tự biết `requestId`, `trace_id`, tenant hoặc user role trừ khi bạn đọc metadata; đừng trộn dữ liệu nhận dạng nhạy cảm vào message chỉ để lọc.

Một quy tắc cơ bản: **filter để giảm nhiễu, không phải để che bí mật**. Nếu thông điệp có password, token, access key hoặc thông tin cá nhân thì cần không tạo nội dung nhạy cảm từ đầu, hoặc redaction/masking được áp dụng trên **mọi đường xuất**, kể cả console, file, OTLP và fallback. Nếu chỉ lọc file mà console vẫn in secret, hệ thống chưa an toàn.

Đối với các event bắt buộc lưu như audit và thanh toán, không dựa vào việc message có hay không một keyword. Hãy dùng event schema và kênh ghi có yêu cầu durability/retention rõ ràng.

## 11. Kiểm thử chính sách filter theo message

Nên test **điều kiện và phạm vi** bằng một ma trận, ngoài việc chạy thử vài log bằng mắt:

| Trường hợp | Level | Message | Kết quả console với policy ví dụ |
| --- | --- | --- | --- |
| Probe thành công | INFO | `GET /actuator/health 200` | DENY |
| Probe lỗi | WARN | `GET /actuator/health 503` | Giữ |
| Probe exception | ERROR | `GET /actuator/health timeout` | Giữ |
| Nghiệp vụ bình thường | INFO | `order=42 created` | Giữ |
| Message chứa từ gần giống | INFO | `healthcheck cache warmed` | Giữ nếu không khớp đúng chuỗi |
| Message không có nội dung | INFO | `""` hoặc null ở filter hỗ trợ | Xử lý nhất quán, thường giữ |
| Log từ logger dưới threshold | DEBUG khi logger INFO | `GET /actuator/health` | Không tạo/không tới appender |
| Message tham số | INFO | template + tham số chứa path | Phụ thuộc raw hay formatted đã chọn |

Ngoài matrix nội dung, còn cần:

1. **Kiểm tra từng appender**: đảm bảo console bỏ event cần lọc, file giữ hoặc bỏ đúng thiết kế, không ghi đôi.
2. **Kiểm tra thứ tự filters**: `DENY`/`ACCEPT`/`NEUTRAL` có diễn giải đúng trong chain, không vô tình short-circuit bảo vệ khác.
3. **Kiểm tra WARN/ERROR**: filter không chặn log quan trọng trùng keyword.
4. **Kiểm tra template/parameter**: với `logger.info("status={}", status)`, test raw và formatted theo đúng API.
5. **Kiểm tra locale/encoding**: chữ hoa/thường, tiếng Việt, Unicode, newline, khoảng trắng, dấu slash, escaping.
6. **Kiểm tra regex worst case**: thông điệp rất dài và input bất thường không gây tăng latency nguy hiểm.
7. **Kiểm tra tốc độ và tải**: đo số log được tạo, bị filter, ghi ra sink; so CPU và queue depth trước/sau.
8. **Kiểm tra lỗi/sự cố**: exception và audit log vẫn xuất hiện, không bị loại chỉ vì chia sẻ keyword với noise.

Nếu unit test custom Logback Filter, có thể khởi tạo event kiểm thử với level/message, gọi trực tiếp `decide(...)` và assert `DENY` hoặc `NEUTRAL`. Test riêng integration với appender/runtime config để xác nhận XML được load và routing đúng, vì logic Java đúng chưa bảo đảm cấu hình production đã gắn filter vào appender mong muốn.

## 12. Chọn cơ chế lọc phù hợp

Dùng các lựa chọn theo thứ tự từ rõ ràng tới linh hoạt:

1. **Điều chỉnh điểm phát sinh log hoặc level** nếu message hoàn toàn không hữu ích. Ví dụ mã probe chỉ phát ở DEBUG; tránh tạo hàng triệu event rồi mới bỏ.
2. **Logger/package/Marker/event code** nếu chỉ muốn lọc một nhóm event được định danh ổn định.
3. **MDC/structured attributes** khi quyết định phụ thuộc request type, endpoint, status hoặc tenant; chuẩn hóa schema để log pipeline xử lý nhất quán.
4. **Substring/prefix/exact match** cho message ổn định, rule đơn giản và có test.
5. **Regex/custom predicate** khi phải xử lý biến thể phức tạp mà dữ liệu cấu trúc chưa có; đo overhead và bảo vệ log lỗi.
6. **Lọc tại collector/backend** khi cần giữ log raw ở nơi khác nhưng giảm một số luồng ingest/search; phải chấp nhận chi phí truyền/vận chuyển đã phát sinh và chính sách dữ liệu của từng destination.

Một message filter được thiết kế tốt phải xác định rõ **message nào được so khớp (raw hay formatted), filter chạy ở đâu, trường hợp nào được giữ ưu tiên, và làm sao phát hiện log bị loại quá nhiều**. Cấu hình đúng là cấu hình giảm nhiễu mà vẫn để lại đủ dữ liệu điều tra sự cố.

## Tài liệu tham khảo

- [Logback manual – Filters, FilterReply, regular và turbo filters](https://logback.qos.ch/manual/filters.html).
- [Logback manual – Logging architecture, effective level và appender filters](https://logback.qos.ch/manual/architecture.html).
- [Apache Log4j 2 – Filters: RegexFilter, StringMatchFilter, composition](https://logging.apache.org/log4j/2.x/manual/filters.html).
- [Oracle JDK 21 – java.util.logging.Filter](https://docs.oracle.com/en/java/javase/21/docs/api/java.logging/java/util/logging/Filter.html).
- [Oracle JDK 21 – LogRecord.getMessage và các tham số](https://docs.oracle.com/en/java/javase/21/docs/api/java.logging/java/util/logging/LogRecord.html).
- [Oracle JDK 21 – Formatter.formatMessage](https://docs.oracle.com/en/java/javase/21/docs/api/java.logging/java/util/logging/Formatter.html).