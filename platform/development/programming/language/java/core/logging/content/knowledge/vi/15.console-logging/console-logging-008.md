# Giới hạn console log trong Java: nguyên nhân, kiểm soát dung lượng và độ tin cậy

**Console logging** là việc ghi sự kiện ra luồng chuẩn của tiến trình, thường là `stdout` hoặc `stderr`, để terminal, hệ điều hành, container runtime hoặc hệ thống thu thập log tiếp nhận. Đây là lựa chọn đơn giản và hữu ích khi phát triển cũng như khi vận hành ứng dụng container. Tuy nhiên, console **không phải kho lưu trữ vô hạn, không đảm bảo mọi sự kiện được giữ mãi và không tự kiểm soát kích thước log cho ứng dụng**.

Chủ đề **“Giới hạn console log”** gồm hai vấn đề có liên quan nhưng khác nhau:

1. **Giới hạn và rủi ro của việc ghi ra console:** output có thể quá nhiều, làm chậm ứng dụng, bị cắt/rotation ở hệ thống thu thập, khó tìm kiếm hoặc chứa thông tin không nên lộ.
2. **Cách chủ động giới hạn console log:** lọc theo level, giảm log lặp, giới hạn kích thước message, hạn chế tốc độ, sử dụng output có cấu trúc và cấu hình chính sách lưu trữ/thu thập.

Mục tiêu là **log đủ để chẩn đoán, không làm cạn tài nguyên và biết điều gì đã bị lọc hoặc mất**. Không có một giới hạn cố định, áp dụng cho mọi chương trình Java, về “console chỉ chứa tối đa bao nhiêu dòng” hay “mỗi dòng được bao nhiêu ký tự”. Giới hạn cụ thể phụ thuộc **từng tầng** trong đường đi.

## 1. Console log đi qua những tầng nào?

```text
Java code
   |
   | logger.info(...) / logger.warn(...) / System.err.println(...)
   v
Logging API và backend (JUL, Logback, Log4j 2...)
   |
   | level, filter, formatter, encoder, appender/handler
   v
stdout hoặc stderr của tiến trình JVM
   |
   | OS stream/pipe, terminal, redirect hoặc container runtime
   v
Log driver / node agent / collector
   |
   | buffer, giới hạn bytes, batching, retry, rotation, retention...
   v
Log storage / tìm kiếm / dashboard / giao diện hiển thị
```

Một lời gọi log thành công ở JVM **không tự chứng minh** bản ghi đã được ghi bền vững ở log storage. Ngược lại, nếu một terminal chỉ hiển thị vài nghìn dòng gần nhất, điều đó **không chứng minh** các dòng cũ đã biến mất khỏi file hoặc collector.

| Tầng | Giới hạn/đặc điểm có thể gặp | Ai kiểm soát? |
| --- | --- | --- |
| API/backend trong JVM | Level, filter, max message, async queue, buffer, sampling | Mã ứng dụng và cấu hình logging |
| JVM/standard stream | Encoding, flush, blocking khi pipe/đích chậm; hai stream riêng | Runtime và cách ứng dụng ghi |
| Terminal/IDE | Giới hạn scrollback, gấp dòng, cắt output hiển thị, màu ANSI | Terminal hoặc IDE |
| Docker/container runtime | File/log driver, rotation, kích thước và chính sách retention | Cấu hình container runtime |
| Kubernetes/node | Thu thập stdout/stderr, rotation log container, log agent | Node/kubelet, runtime và nền tảng |
| Collector/pipeline | Kích thước record, line framing, bộ đệm, retry, drop, sampling | Đội vận hành/pipeline observability |
| Storage/dashboard | Retention, quota, quyền truy cập, giới hạn tìm kiếm và UI | Nền tảng lưu trữ log |

**Không cộng dồn các giới hạn này thành một con số chung.** Một event dài 100 KB có thể được ứng dụng phát ra nhưng bị collector chia nhỏ hoặc cắt; một event INFO có thể bị filter từ trước nên không hề đi tới stdout/stderr.

## 2. Các loại giới hạn thường gặp

### 2.1. Giới hạn theo log level

Ứng dụng chỉ nên ghi những mức phù hợp với môi trường và nhu cầu điều tra.

| Level thường gặp | Khi nào dùng | Khi nên hạn chế? |
| --- | --- | --- |
| TRACE | Theo dõi rất chi tiết từng bước, dữ liệu nội bộ | Hầu hết production trừ khi có phiên debug ngắn hạn |
| DEBUG | Điều tra luồng xử lý, nhánh quyết định, trạng thái | Khi lưu lượng cao hoặc không có sự cố cần điều tra |
| INFO | Những sự kiện vận hành quan trọng, thay đổi trạng thái | Khi một request tạo quá nhiều INFO không có ích |
| WARN | Lỗi dự kiến nhưng đáng chú ý, retry bất thường, suy giảm dịch vụ | Khi một cảnh báo lặp hàng nghìn lần mà không thay đổi |
| ERROR | Thao tác thất bại, exception cần can thiệp hoặc điều tra | Không tắt tùy tiện; phân loại để tránh báo động giả |

Các tên level **khác nhau theo API**: JUL sử dụng `FINE`, `INFO`, `WARNING`, `SEVERE`; SLF4J/Logback thường có `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`. Không mặc định JUL có method `logger.debug()`.

**Filter theo level làm giảm số event được xuất**, nhưng không phải giới hạn tổng số bản ghi hoặc kích thước của từng message. Một event `ERROR` có payload 10 MB vẫn có thể quá lớn.

### 2.2. Giới hạn theo số event hoặc tốc độ

Ví dụ một lỗi mạng sinh 20.000 cảnh báo giống nhau trong một phút. Nếu ghi toàn bộ, log có thể che khuất sự kiện quan trọng, tăng I/O, chiếm dung lượng và làm quá tải collector.

Các kỹ thuật:

- **Rate limiting:** giới hạn số event của một nhóm lỗi trong một khoảng thời gian, ví dụ một loại lỗi không quá N event/phút tại mỗi instance. Cần đặt rõ giới hạn **theo key nào**: level, logger, errorCode, endpoint hay dependency.
- **Sampling:** chỉ giữ một phần event lặp lại, với xác suất/tần suất có thể kiểm soát. Dùng cẩn thận cho lỗi hiếm hoặc sự kiện cần kiểm toán.
- **Deduplication:** gom lỗi lặp thành bản tổng hợp, chẳng hạn `errorCode=UPSTREAM_TIMEOUT count=128 window=60s`.
- **Điều chỉnh level:** chuyển một sự kiện dự kiến xảy ra thường xuyên từ WARN sang INFO/DEBUG nếu đúng chính sách nghiệp vụ.
- **Aggregation/metrics:** đếm số lần lỗi qua counter và giữ một mẫu log đủ ngữ cảnh.

**Cảnh báo:** Giới hạn bằng cách im lặng bỏ event có thể khiến người vận hành đánh giá sai số lỗi. Với production nên công bố chính sách drop/sampling và xuất metrics như `logs_dropped_total`, `logs_suppressed_total`, hoặc `log_queue_depth` theo khả năng backend. Không dùng sampling tùy tiện cho audit log có yêu cầu pháp lý.

### 2.3. Giới hạn kích thước message và record

Không phải mọi loại dữ liệu đều phù hợp để log nguyên văn. Những nguồn thường làm event quá lớn:

- HTTP request/response body hoặc header dài.
- JSON lồng nhiều cấp, danh sách hàng nghìn phần tử.
- Stack trace rất dài, nhiều `Caused by` hoặc suppressed exceptions.
- Nội dung binary, tệp, ảnh được biến thành text/Base64.
- Dữ liệu đến từ người dùng với ký tự xuống dòng hoặc điều khiển.

Một ứng dụng nên ưu tiên **log bản tóm tắt có cấu trúc**:

```text
WARN event=import_rejected requestId=req-17 fileId=file-8 errorCount=350 shownErrors=5
```

thay vì ghi toàn bộ hàng chục nghìn lỗi validation. Nếu chi tiết đầy đủ thật sự cần cho điều tra, lưu ở **kho dữ liệu phù hợp với phân quyền và retention**, rồi ghi mã tham chiếu an toàn trong log.

Có hai khái niệm kích thước dễ nhầm:

- **Số ký tự/code point** của message Java, hữu ích để người đọc kiểm soát nội dung.
- **Số byte sau khi encode** (ví dụ UTF-8), thường mới là yếu tố ảnh hưởng giới hạn của pipe, collector hoặc file. Chữ tiếng Việt có thể chiếm nhiều byte UTF-8 hơn số ký tự hiển thị.

Cắt message theo một số code point không đồng nghĩa đã bảo đảm **giới hạn byte** ở mọi encoding. Với hệ thống có giới hạn nghiêm ngặt, cần tính kích thước sau encoding/serialization, gồm metadata, dấu phân cách, JSON escaping và stack trace.

### 2.4. Giới hạn thời gian lưu trữ và khả năng xem lại

Lệnh `System.out.println` không tự cung cấp retention hoặc rotation. Lịch sử có thể nằm trong terminal, IDE, file redirect, container runtime, journald hoặc storage tập trung, tùy nơi ứng dụng chạy.

- **Scrollback của terminal**: chỉ giới hạn phần nội dung người dùng có thể cuộn xem, thường khác hoàn toàn lượng log đã ghi ra file.
- **Rotation của container runtime**: có thể đổi file cũ theo kích thước/số lượng nếu được cấu hình; file bị xóa sau rotation không thể lấy lại chỉ bằng mở terminal.
- **Retention của log storage**: quyết định số ngày và lượng dữ liệu được giữ; cấu hình này không phải thuộc tính chung của ConsoleAppender.
- **Quota và ingest limit**: có thể gây từ chối, chậm hoặc drop khi hệ thống trung tâm quá tải.

Vì thế “không còn thấy log cũ khi dùng `docker logs` hoặc giao diện Kubernetes” cần điều tra **đúng nơi log đang được lưu** thay vì tăng level DEBUG để tạo thêm log.

## 3. `stdout` và `stderr` không giống nhau

Trong Java:

```java
System.out.println("application started");
System.err.println("validation failed");
```

- `System.out` ghi **standard output**.
- `System.err` ghi **standard error**.
- Trong CLI, stdout thường dành cho kết quả chương trình, stderr dành cho chẩn đoán. Trong service/backend, quy ước output phụ thuộc môi trường và logging configuration.
- Hai stream là **hai đường xuất riêng**. Nếu terminal hiển thị chung, thứ tự bạn nhìn thấy không nhất thiết phản ánh thứ tự toàn cục mà log storage sẽ ghi nhận.

**JUL `java.util.logging.ConsoleHandler` ghi vào `System.err`**. Đây là hành vi của handler chuẩn, không phải quy tắc bắt buộc của Logback hay Log4j 2. Trong Logback, `ConsoleAppender` có cấu hình target; trong Log4j 2, `Console` appender cũng có target. Đừng giả định mọi logger gửi `ERROR` tới stderr và `INFO` tới stdout: điều đó tùy cấu hình backend.

Có thể redirect trong shell Unix-like:

```bash
java ConsoleLimitDemo >app.out 2>app.err
```

Ví dụ này chỉ có ý nghĩa sau khi biên dịch class ở phần thực hành; nó sẽ ghi stdout vào `app.out` và stderr vào `app.err`. Khi gộp `2>&1`, hai luồng dùng một đích từ góc nhìn shell, nhưng vẫn cần xem buffering và thời điểm publish khi muốn tái dựng thứ tự trong môi trường bất đồng bộ.

**Không dùng `System.out.println` làm hệ logging chính** của server có yêu cầu vận hành: nó không tự mang level, logger name, correlation ID, exception pipeline, sampling hay cấu hình appender. Có thể dùng println cho output của CLI đơn giản; với service nên dùng logging API/backend được quản lý.

## 4. Giới hạn console có thể ảnh hưởng hiệu năng như thế nào?

Ghi ra console không miễn phí. Mỗi event có thể có chi phí:

1. Tạo message và xử lý tham số, đôi khi gọi `toString()` của object lớn.
2. Tạo metadata: thời gian, tên logger, thread, exception, MDC.
3. Định dạng chuỗi/JSON, encode thành bytes.
4. Ghi vào stream, có thể cần đồng bộ hóa và flush.
5. Chuyển qua pipe/socket/file của hệ điều hành đến runtime hoặc collector.

Nếu đích đọc chậm, pipe/buffer đầy, hoặc backend viết đồng bộ trên request thread, thao tác ghi **có thể chặn hoặc tăng latency**. Mức ảnh hưởng tùy JVM, handler/appender, hệ điều hành, cấu hình buffering và container runtime; không có quy tắc “mọi INFO log đều chặn x millisecond”.

Logging bất đồng bộ có thể giảm thời gian request chờ I/O bằng cách đưa event vào queue rồi để thread khác ghi. Tuy nhiên:

- Queue có **giới hạn dung lượng**.
- Nếu producer nhanh hơn consumer, queue có thể đầy.
- Tùy backend và chính sách, khi đầy hệ thống có thể chặn producer, bỏ một số event hoặc chuyển cách xử lý.
- Shutdown/crash có thể làm mất event chưa được flush.
- Log quá lớn vẫn chiếm CPU, bộ nhớ và bandwidth dù được queue.

**Không coi async logging là giải pháp loại bỏ giới hạn**: nó chỉ thay đổi nơi đặt backpressure và cách xử lý queue. Phải đo throughput, p95/p99 latency, queue depth, drop counters và tốc độ ingest thực tế.

### Giảm chi phí khi level đang tắt

Ví dụ SLF4J trong dự án có provider:

```java
// Fragment trong lớp có org.slf4j.Logger LOG.
LOG.debug("orderId={} state={}", orderId, state);
```

Placeholder `{}` giảm nhu cầu nối chuỗi sớm. Nhưng Java **vẫn đánh giá các biểu thức tham số** trước khi gọi method, nên đoạn:

```java
LOG.debug("snapshot={}", buildHugeSnapshot());
```

vẫn chạy `buildHugeSnapshot()` ngay cả khi DEBUG bị tắt. Với tính toán chỉ phục vụ log:

```java
if (LOG.isDebugEnabled()) {
    LOG.debug("snapshot={}", buildHugeSnapshot());
}
```

Những fragment trên giả định biến và method đã tồn tại, **không chạy độc lập**; không đặt side effect nghiệp vụ vào tính toán chỉ phục vụ logging.

## 5. Ví dụ Java 17 độc lập: giới hạn level, độ dài và số event

Ví dụ dùng **Java Util Logging (JUL)** có sẵn trong JDK 17, không cần Maven hay thư viện ngoài. Nó minh họa ba lớp giới hạn ở phía ứng dụng:

1. **Level:** đặt logger và `ConsoleHandler` ở `INFO`; event `FINE` bị lọc.
2. **Message length:** formatter escape ký tự điều khiển và chỉ giữ tối đa **32 Unicode code points** trước khi gắn hậu tố `...[truncated]`.
3. **Event count:** một filter demo chỉ cho qua **3 record đầu tiên** mà handler nhìn thấy ở level hợp lệ.

Lưu file **`ConsoleLimitDemo.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class ConsoleLimitDemo {
    private static final Logger LOG =
            Logger.getLogger(ConsoleLimitDemo.class.getName());

    private static String boundedOneLine(String value) {
        String escaped = value
                .replace("\\", "\\\\")
                .replace("\r", "\\r")
                .replace("\n", "\\n")
                .replace("\t", "\\t");

        int maxCodePoints = 32;
        if (escaped.codePointCount(0, escaped.length()) <= maxCodePoints) {
            return escaped;
        }

        int end = escaped.offsetByCodePoints(0, maxCodePoints);
        return escaped.substring(0, end) + "...[truncated]";
    }

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        AtomicInteger attempts = new AtomicInteger();
        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.INFO);
        console.setFilter(record -> attempts.incrementAndGet() <= 3);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " | "
                        + boundedOneLine(formatMessage(record))
                        + System.lineSeparator();
            }
        });

        LOG.addHandler(console);
        try {
            LOG.fine("debug-not-visible");
            LOG.info("event=start");
            LOG.info("payload=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789");
            LOG.warning("client=line1\r\nSEVERE forged");
            LOG.info("event=after-limit");
        } finally {
            LOG.removeHandler(console);
            console.close();
        }

        System.out.println("done=true");
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 ConsoleLimitDemo.java
java ConsoleLimitDemo
```

**Stderr chính xác trong ví dụ:**

```text
INFO | event=start
INFO | payload=ABCDEFGHIJKLMNOPQRSTUVWX...[truncated]
WARNING | client=line1\r\nSEVERE forged
```

**Stdout chính xác trong ví dụ:**

```text
done=true
```

Lý do có đúng ba dòng trên stderr:

- `LOG.fine(...)` bị mức `INFO` của logger lọc trước khi tới handler.
- `LOG.info("event=start")` là record được filter chấp nhận đầu tiên.
- Thông điệp `payload=...` dài hơn 32 code point. `"payload="` chiếm 8 vị trí, 24 ký tự tiếp theo là `ABCDEFGHIJKLMNOPQRSTUVWX`; formatter thêm hậu tố `...[truncated]`.
- `LOG.warning` là record thứ ba được cho qua. `"\r\n"` trong Java là hai ký tự điều khiển CR/LF; formatter biến chúng thành chuỗi chữ `\\r\\n` nên thông điệp giả `SEVERE forged` **không tách thành một dòng log độc lập**.
- `LOG.info("event=after-limit")` là lần gọi thứ tư đến handler ở level đủ cao, nên filter từ chối.
- `ConsoleHandler` viết ra **stderr**, còn `System.out.println` in `done=true` ra **stdout**. Khi terminal gộp hai stream, thứ tự hiển thị giữa chúng có thể thay đổi.

**Giới hạn cố ý của demo:** `attempts` chỉ là bộ đếm số record đưa tới filter, **không phải bộ đếm event được xuất thành công ở hệ thống lưu trữ**. Chương trình này bỏ event thứ tư một cách im lặng để minh họa `Filter`; **không nên sao chép nguyên cơ chế im lặng bỏ log này vào production**. Trong ứng dụng thật, phải có chính sách theo thời gian/key, metrics số event bị giới hạn, ưu tiên theo mức độ và cảnh báo nếu logging pipeline quá tải.

Hàm `boundedOneLine` chỉ escape backslash, CR, LF và tab; nó **không phải bộ lọc bảo mật hoàn chỉnh**. Những ký tự điều khiển khác, terminal escape ANSI, Unicode separator, dữ liệu nhạy cảm và giới hạn bytes phải được xử lý theo tiêu chuẩn encoder/serializer và chính sách dữ liệu. Hậu tố `...[truncated]` cũng làm message dài hơn 32 code point; ngưỡng 32 chỉ áp dụng **phần nội dung được giữ**. Muốn giới hạn tổng byte tuyệt đối, phải tính cả hậu tố, metadata, encoding và newline.

### Vì sao không tự `substring(0, n)` cho mọi message?

Java string dùng UTF-16; một ký tự Unicode có thể sử dụng **hai code unit** (surrogate pair). Cắt bằng `substring` tại vị trí code unit bất kỳ có thể chia một cặp surrogate. Trong demo, `offsetByCodePoints(0, n)` chọn ranh giới code point hợp lệ; đây là lựa chọn tốt hơn khi giới hạn theo code point.

Tuy nhiên, code point vẫn không đồng nghĩa **grapheme cluster** hoặc “một ký tự hiển thị”: emoji kết hợp và dấu tổ hợp có thể gồm nhiều code point. Nếu yêu cầu hiển thị không làm vỡ cụm ký tự, cần cơ chế grapheme segmentation phù hợp. Giới hạn bytes theo UTF-8 lại là bài toán khác.

## 6. Thay đổi mức console log bằng cấu hình

Một quy tắc thực tế là **tách chính sách level/đích ghi khỏi code nghiệp vụ**, để có thể điều chỉnh theo môi trường mà không sửa lời gọi logger.

### JUL: level ở logger và handler

```java
// Fragment trong ứng dụng đã có Logger LOG và ConsoleHandler console.
LOG.setLevel(java.util.logging.Level.WARNING);
console.setLevel(java.util.logging.Level.WARNING);
```

JUL có thể lọc ở cả logger lẫn handler; nếu logger chặn record thì handler không thể làm nó xuất hiện lại. Nếu logger cho `FINE` nhưng handler chỉ cho `INFO`, event FINE cũng không xuất ra console qua handler đó. Ví dụ chính trong mục 5 dùng mức INFO ở cả hai.

### Logback: ConsoleAppender và logger level

Ví dụ **`logback.xml` hoàn chỉnh** dành cho dự án dùng Logback:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level [%thread] %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.verbose" level="WARN"/>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

Root cho INFO trở lên; nhóm `com.example.verbose` có ngưỡng WARN. Đây là cấu hình Logback, **không phải** Log4j2 hoặc JUL. Lưu ý: nếu một logger con có level riêng hoặc filter/appender bổ sung, kết quả phải được kiểm tra theo cấu hình thực tế; Logback có cơ chế kế thừa level và additivity riêng.

### Log4j 2: Console appender

Ví dụ **`log4j2.xml` hoàn chỉnh** cho Log4j 2 Core:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="Console" target="SYSTEM_ERR">
            <PatternLayout pattern="%d{HH:mm:ss.SSS} %-5p %c - %m%n"/>
        </Console>
    </Appenders>
    <Loggers>
        <Logger name="com.example.verbose" level="warn"/>
        <Root level="info">
            <AppenderRef ref="Console"/>
        </Root>
    </Loggers>
</Configuration>
```

`SYSTEM_ERR` chỉ định stderr; `Root` đặt mức INFO và gắn appender. Định dạng mức, tên logger và message lấy từ `PatternLayout`. Cả Logback và Log4j2 có thể cung cấp filter/rate limit/async appender tùy backend, nhưng **cú pháp và hành vi không giống nhau**. Không mang `<encoder>` của Logback vào Log4j 2.

Các cấu hình trên **không áp đặt số dòng tối đa hoặc kích thước mỗi record**. Chúng là ví dụ giới hạn theo level — một trong nhiều biện pháp giảm console volume.

## 7. Console log trong container và Kubernetes

Trong ứng dụng container, việc ghi log ra stdout/stderr thường giúp nền tảng thu thập tập trung mà không cần ứng dụng tự ghi file. Nhưng **stdout/stderr chỉ là đầu ra của tiến trình**; điều gì được giữ lại phụ thuộc cấu hình runtime và pipeline.

Một luồng thường gặp:

```text
Java service
   |
   +--> stdout / stderr
            |
            v
    Container runtime
            |
            v
    Log file hoặc log driver trên node
            |
            +--> kubectl logs / docker logs (tùy hệ)
            |
            v
    Node log agent / collector
            |
            v
    Central log storage & dashboard
```

Với Kubernetes:

- `kubectl logs` cho xem nội dung log container thông qua cơ chế của nền tảng, nhưng **không phải hệ thống lưu trữ log dài hạn**.
- Log trên node có thể được **rotation** theo kích thước/số file; các cấu hình kubelet/runtime quyết định chính sách thực tế.
- Log agent/collector cần phù hợp với format thực tế, đặc biệt khi message có **nhiều dòng**, stack trace hoặc JSON.
- Nếu container bị thay thế và log cũ không còn, cần quan sát tính sẵn có của hệ thống thu thập tập trung, thời gian retention và các chính sách node. Không mặc định một lệnh `kubectl logs` sẽ khôi phục mọi log của phiên deploy cũ.

Với Docker, logging driver và tùy chọn rotation có thể khác giữa môi trường. Không viết cứng một “giới hạn mặc định” cho tất cả Docker/Kubernetes: hãy kiểm tra cấu hình **runtime/cluster đang chạy**.

Trong các hệ có hạn chế ingest lớn, nên dự trù volume theo request rate × event/request × bytes/event, có biên cho exception và thời kỳ lỗi tăng đột biến. Đây là phép ước lượng tài nguyên, không phải bảo đảm về độ trễ hay chi phí. **Tăng số lượng log khi có sự cố** có thể gây hiệu ứng dây chuyền nếu pipeline đang quá tải.

## 8. Console và structured logging: hạn chế lỗi phân tách dòng

Console handler thường thêm `%n` hoặc newline sau mỗi event. Nếu message hoặc exception chứa CR/LF, **một event có thể trở thành nhiều dòng vật lý**. Collector đọc từng dòng có thể coi phần tiếp nối là một event riêng, mất timestamp, level và request ID.

Ví dụ text minh họa:

```text
ERROR requestId=req-17 stage=reserve failed
java.lang.IllegalStateException: invalid stock state
    at com.example.StockService.reserve(StockService.java:42)
    at com.example.OrderService.create(OrderService.java:19)
```

Đây có thể là **một event có Throwable**, nhưng bốn dòng vật lý. Nếu collector có giới hạn bytes/record hoặc không cấu hình multiline, bản ghi có thể bị tách hay cắt.

Một hướng là xuất **một JSON object trên một dòng**:

```json
{"level":"ERROR","event":"reserve_failed","requestId":"req-17","errorCode":"INVALID_STOCK_STATE","message":"reserve failed","exception":"java.lang.IllegalStateException: invalid stock state\n    at com.example.StockService.reserve(...)"}
```

Đây là **JSON minh họa** (giá trị `exception` chứa newline được JSON-escaped). Để giữ một event là một record vật lý, encoder cần **compact JSON** và escape control characters; không pretty-print đối tượng thành nhiều dòng khi collector chỉ đọc dòng đơn.

**Đừng tự nối JSON từ chuỗi người dùng.** Hãy dùng serializer/structured encoder của backend, vì việc escape dấu ngoặc kép, backslash, ký tự điều khiển và newline là bắt buộc để tránh record hỏng hoặc log injection.

Một lựa chọn khác là giữ text multiline nhưng cấu hình collector có parser ghép dòng continuation/stack trace. Cách này yêu cầu kiểm thử riêng với thread đồng thời, exception dài và các message chứa timestamp/level giả.

## 9. Log injection, dữ liệu nhạy cảm và giới hạn bảo mật

Console log có thể được đọc bởi người vận hành, CI/CD, hệ thống giám sát hoặc nhà cung cấp hạ tầng, tùy nơi lưu trữ và quyền truy cập. **Không được coi console là nơi mặc định an toàn cho dữ liệu bí mật.**

Không log nguyên văn:

- Mật khẩu, access token, API key, session cookie, header `Authorization`.
- Dữ liệu thanh toán, thông tin cá nhân nhạy cảm, request body không được phê duyệt.
- Cả URL/query string chứa secret hay định danh không được phép.
- Nội dung binary/tệp lớn hoặc `toString()` của object có trường nhạy cảm.

Ngoài rò rỉ dữ liệu, input không tin cậy có thể chứa `\r`, `\n`, escape ANSI và các ký tự điều khiển làm terminal hiển thị khó hiểu hoặc **giả mạo dòng log**. Trong ví dụ Java, `client=line1\r\nSEVERE forged` được escape thành **một dòng** để tránh một record giả trông giống level `SEVERE`.

**Thứ tự xử lý nên là:**
1. Chọn chỉ những trường có mục đích chẩn đoán.
2. Che/xóa dữ liệu nhạy cảm theo allowlist hoặc chính sách redaction.
3. Serialize/escape theo định dạng đích.
4. Giới hạn độ dài sau khi biết dữ liệu thực tế được phát ra, cộng các metadata và dấu phân cách.
5. Theo dõi số record bị cắt, bỏ hoặc bị collector từ chối nếu nền tảng hỗ trợ.

**Truncation không phải redaction**: cắt message còn 100 ký tự vẫn có thể giữ nguyên token nếu token nằm ở đầu. Ngược lại, chỉ redaction không giải quyết payload còn quá dài. Cần làm cả hai khi phù hợp.

## 10. Khi nào nên dùng file logging hoặc log collector thay vì chỉ console?

Console thường thuận tiện cho ứng dụng container có agent thu thập. File hoặc hệ thống lưu trữ riêng có thể phù hợp khi cần retention độc lập, audit, truy vấn dài hạn hay đáp ứng chính sách lưu giữ.

| Yêu cầu | Cân nhắc |
| --- | --- |
| Xem log cục bộ lúc lập trình | Console với level phù hợp, hiển thị dễ đọc |
| Ứng dụng trong container | stdout/stderr kèm runtime collector, structured encoder |
| Tìm lỗi nhiều ngày trước | Centralized log storage có retention và quyền truy cập |
| Log không được mất trong một số nghiệp vụ | Xây dựng cơ chế lưu trữ/queue có xác nhận phù hợp; không coi console là nguồn kiểm toán duy nhất |
| Rolling file trên VM | File appender với size/time rotation, quota và quyền ghi |
| Log nhiều request đồng thời | Metadata `requestId`, `traceId`, thread, service và timestamp |
| Thời điểm lỗi phát sinh log ồ ạt | Rate limit/sampling có metrics, queue/backpressure, quota theo tầng |

Không dùng một policy đơn giản “ERROR luôn phải giữ tất cả, DEBUG luôn có thể xóa” nếu hệ thống có yêu cầu tuân thủ khác. Cần phân loại log vận hành, audit/security và business event; mỗi loại có retention, mức độ chính xác và quyền truy cập riêng.

## 11. Các lỗi phổ biến về giới hạn console log

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra / khắc phục |
| --- | --- | --- |
| Console tràn đầy DEBUG | Level bật quá rộng, module spam log | Chỉnh level theo package, giảm event không cần |
| Không thấy INFO dù `logger.info` đã gọi | Logger/handler/backend filter hoặc provider sai | Kiểm tra cả mức logger và appender/handler |
| Chỉ thấy vài dòng gần nhất trong IDE | Giới hạn scrollback/output view | Kiểm tra nơi log thật được lưu, không suy ra đã mất |
| `docker logs`/ `kubectl logs` thiếu log cũ | Rotation, retention, container lifecycle | Kiểm tra runtime/cluster và log storage tập trung |
| Request chậm khi lỗi nhiều | Logging đồng bộ, formatter/pipe/collector quá tải | Đo latency, bớt event, cân nhắc async/backpressure |
| Event biến mất khi bật async | Queue đầy, drop policy, shutdown thiếu flush | Đo queue/drop, kiểm tra lifecycle và cấu hình |
| Stack trace bị cắt giữa chừng | Giới hạn bytes/record hoặc field size của collector | Kiểm tra encoder, pipeline và cách lưu Throwable |
| Một exception thành nhiều entries | Multiline parser không được cấu hình | Compact JSON hoặc cấu hình ghép dòng |
| Bản ghi quá lớn dù đã cắt message | Metadata/JSON escaping/Throwable khiến bytes còn tăng | Kiểm tra kích thước record sau encode |
| Dữ liệu nhạy cảm vẫn xuất hiện | Chỉ truncate mà chưa redact | Redact trước, không log body/token không cần |
| Log hiện ký tự lạ hoặc xuống dòng giả | CRLF injection, ANSI, encoding mismatch | Escape/serialize và thống nhất UTF-8 |
| Log trùng hai lần | Gắn appender trùng, JUL parent handlers, additivity | Kiểm tra cấu hình propagation và đích ghi |
| Không biết bao nhiêu log bị bỏ | Rate limit/filter drop không có metrics | Thêm counter/tổng hợp số bị suppress |
| Stdout và stderr xem như bị đảo thứ tự | Hai stream hoặc async buffer khác nhau | Dùng event timestamp/sequence và correlation ID |
| Tăng retention nhưng không tìm thấy log | Retention đã áp dụng ở storage, event chưa từng được ingest | Kiểm tra từng tầng từ appender đến collector |

**Phân tích đúng cấp:** Nếu backend lọc event ngay trong JVM, tăng retention của collector không giúp gì. Nếu collector cắt event vì giới hạn bytes, giảm scrollback terminal cũng không giải quyết. Hãy xác định **tầng đầu tiên nơi log biến mất hoặc thay đổi**.

## 12. Thiết kế chính sách console log cho production

Một chính sách có thể bao gồm các câu hỏi sau, không nên chỉ đặt một con số “max lines”:

1. **Mục đích:** log giúp vận hành, điều tra lỗi hay kiểm toán? Những loại này có yêu cầu giữ dữ liệu khác nhau.
2. **Level:** ngưỡng theo môi trường và theo module, có thể thay tạm trong khoảng thời gian giám sát.
3. **Volume:** ước lượng events/s và bytes/s trong trạng thái bình thường lẫn thời kỳ sự cố.
4. **Message limit:** giới hạn theo trường/ngữ cảnh; có hướng lưu nội dung đầy đủ ở nơi khác nếu thật sự cần.
5. **Rate control:** nhóm event theo khóa ổn định, tránh suppress mọi lỗi không phân biệt; công bố số lượng bị bỏ.
6. **Structured output:** một event có cấu trúc, timestamp UTC/timezone, logger, level, correlation ID, errorCode và Throwable đúng cách.
7. **Stream contract:** backend gửi stdout/stderr như thế nào, collector thu cả hai stream hay không?
8. **Pipeline:** buffer/queue/flush/backpressure, giới hạn record bytes, retry/drop, rotation, retention và quyền truy cập.
9. **Bảo mật:** redaction/allowlist, log injection, dữ liệu nhạy cảm và thời gian lưu.
10. **Kiểm thử:** tăng tải, sự cố dependency, exception dài, đa thread, container restart và hệ thống collector chậm.
11. **Metrics:** theo dõi volume, drop, ingest lag, queue depth và mức tăng bất thường.
12. **Tài liệu vận hành:** có hướng dẫn tìm log khi sự cố, cách thay level có kiểm soát và hoàn nguyên sau điều tra.

### Bài tập kiểm chứng nhỏ

Từ `ConsoleLimitDemo.java` ở mục 5, thực hiện:

- Thay `LOG.setLevel(Level.INFO)` bằng `Level.WARNING`. Quan sát event INFO không còn tới handler và số thứ tự những event được filter chấp nhận thay đổi.
- Thay ngưỡng 32 code point bằng 12. Kiểm tra `payload` bị cắt nhiều hơn; hậu tố không nằm trong quota nội dung.
- Thay mức handler thành `Level.WARNING` nhưng giữ logger INFO. Quan sát handler từ chối INFO.
- Xóa `setUseParentHandlers(false)` để thấy cấu hình JUL mặc định có thể tạo bản ghi trùng/khác format, tùy runtime.
- Tăng số record gửi để thấy filter giới hạn số event trong demo, nhưng **không có bảo đảm giữ log tại collector**.
- So sánh kết quả khi chạy với redirect `>app.out 2>app.err` để thấy console handler và chương trình phát ở hai stream khác nhau.

Đối với hệ thống thật, mở rộng thành kiểm thử tải và integration test trên logging pipeline mà production sử dụng; không đo performance bằng demo có vài event rồi suy ra throughput của hàng nghìn request/giây.

## 13. Tóm tắt trọng tâm

**Giới hạn console log** không chỉ là “cắt bớt một chuỗi”: ứng dụng Java có thể lọc theo level/số lượng/kích thước, nhưng các tầng stdout/stderr, runtime, collector, storage và UI vẫn có giới hạn riêng. Để log vừa hữu ích vừa bền vững:

- Chỉ phát **đúng sự kiện cần thiết**, mức phù hợp, tránh ghi payload lớn.
- Giữ **đủ ngữ cảnh** (request ID, error code, Throwable) thay vì chỉ tăng số lượng dòng.
- Nếu giới hạn bằng rate/sampling/truncation, **biết event nào có thể bị bỏ và đo được lượng bị bỏ**.
- Dùng structured encoder và escaping để giảm phân tách multiline, log forging và lỗi parser.
- Kiểm tra **đường đi thực tế đến collector/storage**, không suy ra thành công chỉ từ việc println/log method chạy xong.
- Chọn retention/rotation và chiến lược lưu trữ riêng cho yêu cầu audit hoặc dữ liệu không được phép mất.

**Kết quả học tập:** Bạn giải thích được vì sao console có thể tràn, chậm, mất hoặc cắt log; phân biệt giới hạn trong Java với giới hạn ở nền tảng; tự viết được một bộ giới hạn đơn giản bằng JUL trên JDK 17; và biết khi nào phải dùng policy ở backend/collector thay vì xử lý mọi việc bằng `System.out.println`.

## Tài liệu chính thức

- Oracle Java 17 — `ConsoleHandler`: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/ConsoleHandler.html
- Oracle Java 17 — `Logger`, `Filter` và `Formatter`: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/package-summary.html
- Logback — Architecture và appenders: https://logback.qos.ch/manual/architecture.html và https://logback.qos.ch/manual/appenders.html
- Apache Log4j 2 — Configuration: https://logging.apache.org/log4j/2.x/manual/configuration.html
- Kubernetes — Logging Architecture: https://kubernetes.io/docs/concepts/cluster-administration/logging/
