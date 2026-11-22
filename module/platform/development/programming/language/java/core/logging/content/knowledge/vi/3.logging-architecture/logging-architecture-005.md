# Tầng appender và handler trong kiến trúc logging Java

Trong kiến trúc logging, **logger** là nơi ứng dụng phát ra sự kiện; **appender/handler** là tầng nhận sự kiện đã được chấp nhận và đưa sự kiện đó đến một hoặc nhiều đích lưu trữ, hiển thị hoặc chuyển tiếp. Tầng này quyết định log đi **đâu**, có được **lọc thêm** hay không, được **biểu diễn** như thế nào và được **ghi/đẩy** bằng cơ chế gì.

Hiểu tầng appender/handler giúp giải thích các hiện tượng rất thường gặp: gọi `logger.info(...)` nhưng không thấy log; một sự kiện bị ghi hai lần; một số log chỉ xuất hiện trong file; hoặc log mất khi bộ đệm chưa được xả.

## 1. Vị trí của appender/handler trong luồng logging

Một luồng logging điển hình có dạng:

```text
Mã ứng dụng
    |
    v
Logging API / Logger
    |  Kiểm tra mức (level), filter ở logger, tạo sự kiện
    v
Phân phối sự kiện đến đích
    |
    +--> Handler/Appender A --> Filter/threshold --> Formatter/Layout/Encoder --> Console
    |
    +--> Handler/Appender B --> Filter/threshold --> Formatter/Layout/Encoder --> File
    |
    +--> Handler/Appender C --> Filter/threshold --> Biểu diễn / truyền --> Đích khác
```

Đây là sơ đồ khái niệm: thứ tự chính xác và tên thành phần phụ thuộc framework. Ví dụ, `java.util.logging` (JUL) dùng `Handler` và `Formatter`; Logback thường dùng `Appender`, `Encoder` hoặc `Layout`; Log4j 2 dùng `Appender` và `Layout`. Không nên coi các interface hoặc cơ chế nội bộ của chúng là hoàn toàn giống nhau.

**Các vai trò cần tách bạch:**

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| **Logger** | Nhận lời gọi log, kiểm tra điều kiện để phát sự kiện và chuyển đến đầu ra được gắn | `Logger.info(...)`, `logger.warn(...)` |
| **Log event / record** | Mang level, message, thời điểm, logger name, exception và ngữ cảnh hỗ trợ | `java.util.logging.LogRecord` |
| **Handler / Appender** | Tiếp nhận, có thể lọc thêm và phân phối sự kiện tới đích | `ConsoleHandler`, `RollingFileAppender` |
| **Filter / threshold** | Quyết định một sự kiện có được xử lý tại một điểm trong pipeline không | Chỉ nhận `WARNING` trở lên |
| **Formatter / Layout / Encoder** | Chuyển sự kiện thành biểu diễn đầu ra: text, JSON, byte, stack trace | Timestamp + level + message |
| **Sink / destination** | Nơi log thực sự đến | `stderr`, `stdout`, file, collector |

Một **logger** có thể gắn nhiều handler/appender để phát cùng sự kiện tới nhiều đích. Ngược lại, nhiều logger có thể cùng sử dụng handler/appender được kế thừa hoặc tham chiếu theo cấu hình.

Ví dụ: yêu cầu HTTP thất bại được logger phát ở mức `WARNING`. Cùng sự kiện có thể được hiển thị ở console để người vận hành theo dõi, đồng thời được đưa vào file quay vòng để phân tích lại. Đây là **fan-out** (phân phối một sự kiện ra nhiều nhánh), không nhất thiết là lỗi ghi trùng.

## 2. Tên gọi và API trong Java

| Hệ sinh thái | Lớp/tầng gửi log | Tầng đầu ra | Thành phần định dạng |
| --- | --- | --- | --- |
| Java Util Logging (JUL, có sẵn trong JDK) | `java.util.logging.Logger` | `java.util.logging.Handler` và các lớp con | `java.util.logging.Formatter` |
| SLF4J | API `org.slf4j.Logger` | Phụ thuộc **backend** được liên kết | Phụ thuộc backend |
| Logback | Logger của Logback (thường được gọi qua SLF4J) | `Appender`, ví dụ `ConsoleAppender`, `RollingFileAppender` | `Encoder`/`Layout` |
| Log4j 2 | Log4j API và Log4j Core | `Appender`, ví dụ Console, File, RollingFile | `Layout`, ví dụ Pattern/JSON |

**SLF4J là facade/API**, không phải một handler hay appender cụ thể. Khi ứng dụng chỉ gọi `org.slf4j.Logger`, backend thực tế mới chịu trách nhiệm cấu hình và ghi sự kiện. Nếu backend là Logback, ta cấu hình appender theo Logback; không thể gọi `java.util.logging.ConsoleHandler` là appender Logback.

Với JUL, lớp trừu tượng `Handler` có ba phương thức quan trọng:

- `publish(LogRecord record)`: nhận và xử lý một bản ghi. Triển khai phải tôn trọng điều kiện lọc thích hợp, thường kiểm tra `isLoggable(record)`.
- `flush()`: yêu cầu xả dữ liệu đang đệm nếu triển khai có bộ đệm.
- `close()`: giải phóng tài nguyên và thường xả dữ liệu còn lại theo hợp đồng triển khai.

`Handler` còn có `setLevel(...)`, `setFilter(...)`, `setFormatter(...)` và các cấu hình liên quan. Tuy nhiên, **handler tự viết không tự động áp dụng formatter**: phương thức `publish` của nó phải thực sự gọi formatter nếu cần. Các handler có sẵn như `ConsoleHandler` đã thực hiện phần ghi/định dạng tương ứng.

### Những handler có sẵn trong JUL

- `ConsoleHandler`: ghi log vào `System.err`; hữu ích khi log được hệ thống vận hành thu thập từ tiến trình.
- `FileHandler`: ghi vào file, hỗ trợ cấu hình pattern tên file, số file và giới hạn dung lượng; cần quan tâm đến quyền ghi, chế độ append, vòng đời file và khả năng thu thập log.
- `StreamHandler`: ghi các bản ghi đã định dạng vào một `OutputStream`.
- `SocketHandler`: gửi sự kiện qua socket đến đầu nhận được cấu hình; cần cân nhắc lỗi mạng và độ tin cậy.
- `MemoryHandler`: giữ bản ghi trong bộ nhớ rồi đẩy đến handler đích khi gặp điều kiện kích hoạt. Không phải một hệ thống lưu log bền vững độc lập.

Tên gần giống nhau **không đảm bảo semantics giống nhau** giữa JUL, Logback và Log4j 2. Khi chọn triển khai, cần đối chiếu tài liệu của backend đang được ứng dụng sử dụng.

## 3. Level và filter hoạt động ở nhiều vị trí

Một sự kiện không xuất hiện ở đích có thể đã bị loại ở **logger** hoặc ở **handler/appender**. Hai điểm này độc lập về mặt cấu hình.

Trong JUL, một bản ghi được xử lý theo các bước cơ bản:

1. Logger nhận lời gọi `fine`, `info`, `warning` hoặc `log(...)`.
2. Logger kiểm tra mức hiệu lực và filter của chính logger. Nếu không đạt, sự kiện **không được phát** đến các handler.
3. Nếu được chấp nhận, `LogRecord` được chuyển tới các handler gắn với logger, và có thể tiếp tục đến handler của logger cha.
4. Mỗi handler lại quyết định có ghi hay bỏ sự kiện theo level và filter của **handler đó**.
5. Handler được chọn định dạng và ghi/đẩy sự kiện đến đích.

Ví dụ với các mức JUL theo thứ tự tăng dần `FINE` → `INFO` → `WARNING` → `SEVERE`:

| Logger level | Handler level | Sự kiện | Có tới đích này? | Vì sao |
| --- | --- | --- | --- | --- |
| `INFO` | `FINE` | `FINE` | Không | Bị chặn ngay tại logger |
| `FINE` | `INFO` | `FINE` | Không | Qua logger nhưng bị handler chặn |
| `FINE` | `INFO` | `INFO` | Có | Đạt cả hai ngưỡng, nếu filter khác cho phép |
| `FINE` | `WARNING` | `WARNING` | Có | Đạt cả hai ngưỡng, nếu filter khác cho phép |
| `INFO` | `SEVERE` | `WARNING` | Không | Handler yêu cầu mức cao hơn |

Bảng giả định không có filter bổ sung và logger không bị tắt bằng `OFF`. Với Logback hoặc Log4j 2, bộ lọc theo level có thể đặt ở các vị trí/cấu hình khác; không suy ra rằng mọi appender đều có `setLevel` như JUL. Ví dụ, Logback thường dùng `ThresholdFilter` khi muốn một appender chỉ nhận sự kiện từ một mức nhất định.

**Lưu ý riêng của JUL:** Khi một logger con đã chấp nhận `LogRecord` và truyền lên các handler của cha, **level/filter của logger cha không được áp dụng lại cho record đã phát**; level/filter của handler cha vẫn áp dụng. Do đó, lúc chẩn đoán log JUL phải kiểm tra cả logger phát sự kiện lẫn các handler trên đường kế thừa.

## 4. Ví dụ Java 17+: một logger, hai handler và hai ngưỡng log

Chương trình độc lập dưới đây minh họa ba khái niệm: logger có thể phát tới nhiều handler; handler lọc theo mức riêng; và handler tự tạo cần triển khai logic xử lý bản ghi.

Ta cấu hình:

- Logger nhận từ `FINE` trở lên.
- `ConsoleHandler` chỉ ghi `WARNING` trở lên vào **stderr**.
- `BufferHandler` tự viết chỉ thu `INFO` trở lên trong bộ nhớ và cho in danh sách ra **stdout** ở cuối.

Lưu file `HandlerLayerDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class HandlerLayerDemo {
    static final class BufferHandler extends Handler {
        private final List<String> events = new ArrayList<>();

        BufferHandler() {
            setLevel(Level.INFO);
        }

        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record)) {
                return;
            }
            events.add(record.getLevel().getName()
                    + " | " + record.getMessage());
        }

        @Override
        public void flush() {
            // Ví dụ này chỉ giữ dữ liệu trong List, không có stream để xả.
        }

        @Override
        public void close() {
            // Ví dụ này không giữ tài nguyên bên ngoài.
        }

        List<String> snapshot() {
            return List.copyOf(events);
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.logging.handlers");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.FINE);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.WARNING);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " | " + formatMessage(record)
                        + System.lineSeparator();
            }
        });

        BufferHandler buffer = new BufferHandler();

        logger.addHandler(console);
        logger.addHandler(buffer);

        logger.fine("requestId=req-7 stage=received");
        logger.info("requestId=req-7 stage=validated");
        logger.warning("requestId=req-7 stage=retry");

        System.out.println("bufferCount=" + buffer.snapshot().size());
        for (String event : buffer.snapshot()) {
            System.out.println("buffer> " + event);
        }

        logger.removeHandler(console);
        logger.removeHandler(buffer);
        console.close();
        buffer.close();
    }
}
```

Biên dịch và chạy trên JDK 17 hoặc mới hơn:

```bash
javac -encoding UTF-8 HandlerLayerDemo.java
java HandlerLayerDemo
```

**Stdout chính xác:**

```text
bufferCount=2
buffer> INFO | requestId=req-7 stage=validated
buffer> WARNING | requestId=req-7 stage=retry
```

**Stderr chính xác:**

```text
WARNING | requestId=req-7 stage=retry
```

Thứ tự hiển thị giữa hai luồng **stdout** và **stderr** nếu terminal gộp chúng lại có thể khác nhau; nội dung từng luồng như trên. Dòng `FINE` không xuất hiện ở đích nào vì cả hai handler đều lọc nó. Dòng `INFO` chỉ vào buffer. Dòng `WARNING` vào cả hai đích.

**Giải thích các điểm chính trong code:**

1. `logger.setUseParentHandlers(false)` ngăn chuyển bản ghi tới handler của logger cha, nhờ đó output của demo không bị thêm log từ cấu hình mặc định.
2. `logger.setLevel(Level.FINE)` cho logger phát cả `FINE`, `INFO` và `WARNING`; từng handler tự chọn mức được nhận.
3. `ConsoleHandler` dùng `Formatter` tùy chỉnh để output xác định, dễ đối chiếu; formatter này cố ý bỏ timestamp để bài minh họa ngắn, không phải cấu hình vận hành đầy đủ.
4. `BufferHandler.publish` gọi `isLoggable(record)`, vì một handler tự viết cần tôn trọng level/filter trước khi xử lý.
5. `removeHandler` và `close` giải phóng liên kết/tài nguyên do demo tạo.

`BufferHandler` trong bài **chỉ phục vụ việc học**. Nó dùng `ArrayList` không đồng bộ, không giới hạn số record và không đảm bảo an toàn khi nhiều luồng cùng publish; không dùng nguyên trạng làm handler production. Với hệ thống thật, dùng triển khai đã kiểm chứng và kiểm soát bộ đệm, bộ nhớ, tính đồng thời và vòng đời tài nguyên.

### Nếu không dùng `setUseParentHandlers(false)` thì sao?

Trong JUL, mỗi logger nằm trong một hệ phân cấp. Khi `useParentHandlers` là `true` (giá trị mặc định), record còn có thể đi đến các handler gắn với logger cha. Nếu cả con và cha cùng ghi vào console, một sự kiện có thể xuất hiện nhiều lần ở cùng đích.

Chặn kế thừa không phải luôn là cách cấu hình đúng cho toàn ứng dụng: nếu hệ thống dựa vào root logger để tập trung log, tắt kế thừa ở từng logger có thể làm mất bản ghi. Hãy xem ai chịu trách nhiệm gắn handler, đặt level/filter nhất quán và **tránh gắn cùng đích ở nhiều tầng ngoài ý muốn**.

## 5. Appender trong Logback: cấu hình đầu ra tách khỏi lời gọi log

Với ứng dụng dùng **SLF4J + Logback**, lời gọi ở mã Java thường có dạng:

```java
// Đoạn minh họa: cần dependency SLF4J và một backend Logback.
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(OrderService.class);

LOG.info("orderId={} stage=validated", orderId);
```

Đoạn trên **không phải chương trình độc lập**: `OrderService` và `orderId` đại diện cho lớp và biến có sẵn trong ứng dụng. Nó minh họa mã nghiệp vụ chỉ phát event, còn nơi ghi được khai báo riêng.

Ví dụ cấu hình Logback trong `logback.xml`:

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="FILE" class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/application.log</file>
        <rollingPolicy class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>logs/application.%d{yyyy-MM-dd}.log</fileNamePattern>
            <maxHistory>7</maxHistory>
        </rollingPolicy>
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE" />
        <appender-ref ref="FILE" />
    </root>
</configuration>
```

**Cách đọc cấu hình:**

- `CONSOLE` là một `ConsoleAppender`; `FILE` là `RollingFileAppender`.
- `root level="INFO"` đặt mức log của root logger. Những logger sử dụng mức kế thừa tương ứng sẽ không phát sự kiện `DEBUG` tới các appender này.
- Hai thẻ `appender-ref` khiến một sự kiện đi đến cả console và file. Đây là chủ ý thiết kế, không phải hai lời gọi logger.
- `encoder` tạo chuỗi đầu ra và thêm xuống dòng bằng `%n`.
- `TimeBasedRollingPolicy` dùng pattern ngày trong tên file lưu trữ; `maxHistory` giới hạn số kỳ lịch sử được giữ theo chính sách này. Cần đảm bảo đường dẫn ghi được, cấu hình lưu trữ đáp ứng nhu cầu vận hành, và có cơ chế quản lý dung lượng phù hợp.

Ví dụ này yêu cầu Logback tương thích đã có trong runtime và là **một đoạn cấu hình**, không chạy bằng `javac` như chương trình JUL. Trong ứng dụng cụ thể, cấu hình có thể được nạp từ `logback.xml`, một file do framework tích hợp cung cấp, hoặc cơ chế cấu hình khác.

**Không trộn cú pháp giữa các backend:** `<appender-ref>`, `<encoder>` ở trên là Logback. Log4j 2 có sơ đồ `Appenders`/`Loggers` và cú pháp cấu hình riêng; JUL thường cấu hình handler bằng Java code hoặc `logging.properties`.

## 6. Formatter, layout và encoder: ghi đúng sự kiện chưa đủ

Appender/handler trả lời câu hỏi log đi đâu; formatter/layout/encoder quyết định người và hệ thống thu thập **đọc được log như thế nào**.

Một định dạng text nhất quán thường có:

```text
2026-11-09T10:15:30.123Z INFO  service=checkout logger=OrderService requestId=req-7 event=validated
2026-11-09T10:15:30.180Z WARN  service=checkout logger=PaymentClient requestId=req-7 event=retry attempt=1
```

Đây là **dòng log giả định**. Khi triển khai, timestamp nên ghi kèm múi giờ rõ ràng (ví dụ UTC/ISO 8601), nhất là với hệ thống nhiều node. Với JSON logging, cấu trúc trường thường hỗ trợ lọc theo `requestId`, `service`, `level`, `errorCode` tốt hơn so với việc phải tách chuỗi text tự do.

Nên có ít nhất: thời điểm, mức, tên logger/thành phần, thông điệp, correlation ID khi có và exception/stack trace nếu có thất bại. Trong các backend hỗ trợ MDC/thread context, formatter/encoder có thể lấy các trường ngữ cảnh đó; JUL chuẩn không tự cung cấp một MDC tương đương. Khi xử lý bất đồng bộ hoặc chuyển sang thread khác, ứng dụng cần truyền ngữ cảnh theo cách được hệ sinh thái đang dùng hỗ trợ.

Nếu nhiều sink dùng formatter khác nhau, cùng một sự kiện vẫn có thể hiện ra với **hình thức khác nhau**. Tránh để các pipeline thu thập giả định mọi đích đều có cùng trường hoặc cùng timezone.

Khi in dữ liệu không tin cậy, cần xử lý ký tự xuống dòng và ký tự điều khiển để giảm nguy cơ làm giả nhiều dòng log. Không dùng việc “log tất cả tham số” để điều tra nếu tham số có thể chứa token, mật khẩu, nội dung riêng tư hoặc dữ liệu nhạy cảm.

## 7. Đồng bộ, bất đồng bộ, đệm và độ tin cậy

Trong cách ghi **đồng bộ**, lời gọi logging thường thực hiện đáng kể phần công việc ghi trước khi trả điều khiển. Đích I/O chậm có thể làm chậm request ứng dụng. Với **asynchronous appender/handler**, sự kiện thường được đưa vào hàng đợi rồi một worker khác xử lý; lời gọi ứng dụng có thể nhanh hơn nhưng xuất hiện thêm rủi ro về bộ đệm và vòng đời.

| Khía cạnh | Ghi đồng bộ | Ghi bất đồng bộ |
| --- | --- | --- |
| Độ trễ trên luồng gọi | Có thể chịu chi phí format/I/O trực tiếp | Thường giảm chi phí trên luồng gọi khi queue còn khả năng nhận |
| Khi sink chậm | Luồng gọi có thể bị chậm theo | Hàng đợi có thể tăng hoặc đầy |
| Khi queue đầy | Không có queue kiểu này trong nhánh ghi đồng bộ | Tùy backend/cấu hình: chặn, loại bỏ, hoặc dùng chính sách khác |
| Khi tắt/crash | Có thể vẫn còn dữ liệu hệ điều hành đang đệm | Record chưa xử lý trong queue có nguy cơ mất nếu shutdown không xả hoặc crash |
| Thứ tự | Dễ hiểu hơn trong một luồng ghi, vẫn cần cân nhắc concurrency | Không tự bảo đảm thứ tự tổng thể xuyên nhiều worker/sink |

Không có cam kết chung rằng “bật async thì không mất log”. Cần xem **queue capacity, discard policy, flush/stop timeout, xử lý lỗi của sink** và khả năng giám sát việc drop/bị nghẽn theo backend cụ thể. Khi thiết kế log phục vụ audit quan trọng, không dùng pipeline logging thông thường làm cơ chế ghi dữ liệu nghiệp vụ duy nhất.

**Lựa chọn đích theo môi trường:**

- **Console / stdout / stderr:** thường phù hợp tiến trình chạy trong container khi hệ thống bên ngoài đã thu thập dòng log; tránh phụ thuộc file nội bộ dễ mất khi container thay mới.
- **Rolling file:** hữu ích khi cần file cục bộ; phải quản lý rotation, thời gian lưu, quota/dung lượng, quyền truy cập và việc chuyển file vào hệ thống tập trung.
- **Gửi trực tiếp qua mạng:** giảm bước chuyển tiếp nhưng phụ thuộc mạng và đích nhận. Cần timeout, retry/backpressure, bảo vệ kết nối và chính sách khi đích không khả dụng.
- **Appender bất đồng bộ:** thích hợp khi cần tách I/O khỏi luồng xử lý, với điều kiện có giới hạn queue và giám sát mất bản ghi.

## 8. Additivity, propagation và lỗi ghi log trùng

**Propagation** là việc record đi qua hệ phân cấp logger; **additivity** là tên gọi cơ chế tương ứng trong những framework như Logback.

Giả sử `com.example` có appender console, còn `com.example.orders` cũng có console của riêng nó. Nếu logger con được phép chuyển record lên cha và cả hai nhánh ghi tới cùng console, một thông điệp có thể hiện **hai lần**. Cấu hình đúng phụ thuộc chủ đích:

- **Muốn kế thừa đầu ra tập trung:** gắn appender ở một cấp phù hợp, cho logger con kế thừa, tránh thêm appender trùng không cần thiết.
- **Muốn một logger có đầu ra riêng:** gắn appender riêng và kiểm soát propagation; trong JUL dùng `setUseParentHandlers(false)`, trong Logback có thuộc tính `additivity="false"` trên logger tương ứng.

Không nhầm việc cùng một event có mặt ở **console và file** với lỗi ghi hai lần vào **cùng sink**. Khi tìm trùng log, kiểm tra tên logger, mọi appender/handler gắn trực tiếp, các tầng cha và bridge giữa các hệ logging.

Cũng cần phân biệt propagation với **bridge logging**: một số ứng dụng chuyển sự kiện giữa JUL, SLF4J, Log4j API và backend khác nhau. Cấu hình bridge vòng lặp hoặc nhiều backend không đúng có thể tạo log lặp, mất record hoặc hành vi khó đoán. Sử dụng một đường đi logging nhất quán được framework hỗ trợ.

## 9. Điều tra nhanh khi appender/handler không hoạt động như mong đợi

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Gọi `logger.info` nhưng không có log | Logger level, filter, handler level, filter ở sink hoặc chưa gắn handler | Truy đường đi từ logger tới từng sink, kiểm tra ngưỡng ở từng điểm |
| Chỉ thấy `WARNING`, không thấy `INFO` | Handler/appender đang lọc theo ngưỡng cao hơn | Xác nhận filter/threshold của đích; so sánh với logger level |
| Một sự kiện in hai lần ở console | Logger con và cha cùng gắn output, additivity/propagation, bridge trùng | Kiểm tra hệ phân cấp và chỉ giữ đường phát có chủ đích |
| Log hiện ở stderr nhưng tool chỉ đọc stdout | `ConsoleHandler` JUL mặc định dùng stderr; tool thu thập sai luồng | Thu thập đúng luồng hoặc điều chỉnh cấu hình sink |
| Không tạo được file log | Đường dẫn, quyền ghi, filesystem read-only, cấu hình file/appender | Kiểm tra lỗi khởi tạo appender và quyền hệ điều hành |
| Log mất lúc ứng dụng thoát | Buffer/queue chưa xả hoặc handler chưa đóng đúng | Cấu hình shutdown, `flush`/`close` theo hợp đồng framework; giám sát hàng đợi |
| Console có log nhưng hệ thống tập trung không có | Collector/agent không chạy, parse sai, mạng lỗi, pipeline lọc | Kiểm tra agent, đường truyền, định dạng và thống kê drop |
| Đã có message nhưng thiếu stack trace | Chỉ log `exception.getMessage()` hoặc formatter bỏ phần throwable | Truyền `Throwable` vào API log và chọn formatter/encoder có hỗ trợ |
| Log quá nhiều, hệ thống chậm | Mức log quá chi tiết, sink chậm, format tốn chi phí | Giảm log nhiễu, tối ưu cấu hình, đo hiệu năng và chính sách async |

Đối với JUL, nếu một handler lỗi khi publish/flush/close, API có cơ chế `ErrorManager` để báo lỗi. Việc ứng dụng không thấy exception trực tiếp khi gọi logger **không chứng minh log đã được ghi bền vững**. Với Logback/Log4j 2, cũng cần kiểm tra thông báo trạng thái nội bộ của framework, cấu hình sink, và khả năng thu nhận của hệ thống lưu trữ.

## 10. Checklist thiết kế và vận hành tầng đầu ra

1. **Xác định backend thực tế.** Ứng dụng dùng JUL, SLF4J + Logback hay Log4j 2? Không sao chép cấu hình giữa các backend.
2. **Vẽ đường đi mỗi sự kiện.** Logger → level/filter → handler/appender → formatter/encoder → sink; chú ý propagation.
3. **Gắn đúng đích.** Console, file hoặc collector phục vụ mục đích rõ ràng. Tránh đích trùng không mong muốn.
4. **Chọn level/filter theo trách nhiệm từng đích.** Logger không phát thì handler không thể khôi phục sự kiện; một handler có thể chọn ít sự kiện hơn handler khác.
5. **Giữ định dạng ổn định.** Có timestamp kèm timezone, level, thành phần, correlation ID và lỗi kỹ thuật khi cần.
6. **Quản lý dữ liệu và tài nguyên.** Giới hạn bộ đệm, số lượng log, thời gian lưu, dung lượng đĩa; không ghi bí mật hoặc dữ liệu nhạy cảm ngoài phạm vi cho phép.
7. **Kiểm chứng đường đi thật.** Tạo một log thử ở các mức `INFO`, `WARNING` và một exception; đối chiếu từng sink, bộ thu thập và tình huống dừng ứng dụng.
8. **Theo dõi bản thân pipeline.** Quan sát lỗi mở file, mạng chậm, queue đầy, record bị bỏ và lỗi parse/ingest.

Hiểu tầng appender/handler nghĩa là có thể giải thích **vì sao một sự kiện được phát nhưng không xuất hiện ở đích**, **vì sao cùng sự kiện đến nhiều nơi**, và **cần cấu hình hoặc vận hành điểm nào** để log đủ hữu ích, dễ tìm, có giới hạn và đáng tin cậy.
