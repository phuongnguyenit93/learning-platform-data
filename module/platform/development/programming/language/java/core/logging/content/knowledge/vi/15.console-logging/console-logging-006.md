# Flush console trong Java Logging — bộ đệm, handler và độ tin cậy

## 1. “Flush console” nghĩa là gì?

Trong Java, **flush** là hành động yêu cầu một tầng stream, writer, handler hoặc appender **đẩy dữ liệu còn đang nằm trong bộ đệm của tầng đó xuống đích phía dưới**. Đối với console logging, đích thường là **standard output (stdout)** hoặc **standard error (stderr)**. Mục tiêu của flush là làm giảm nguy cơ thông điệp đang đệm chưa được chuyển đi khi chương trình kết thúc hoặc khi người vận hành cần nhìn thấy kết quả sớm.

Ví dụ đơn giản:

```java
System.out.print("Batch started");
System.out.flush();
```

Lệnh `System.out.flush()` yêu cầu `PrintStream` hiện tại flush các byte còn được đệm qua output stream bên dưới. Nó **không phải thao tác in ra màn hình một cách bảo đảm**, không tự đồng bộ mọi logger và không chứng minh rằng hệ thống lưu trữ log bên ngoài đã nhận dữ liệu.

Một sự kiện trong ứng dụng Java có thể đi qua nhiều tầng:

```text
Java application
    |
    | logger.info(...)
    v
Logger + level/filter
    |
    v
Handler/Appender (có thể có buffer hoặc async queue)
    |
    v
Formatter/Layout/Encoder
    |
    v
System.out / System.err / OutputStream
    |
    v
OS pipe/terminal/container runtime
    |
    v
Collector / log shipper / remote storage
    |
    v
Search/index/retention
```

**Flush tại một tầng không đồng nghĩa tất cả tầng phía sau đều hoàn thành.** Ví dụ, gọi `System.out.flush()` không tự drain hàng đợi của một AsyncAppender vẫn chưa đưa event đến `System.out`; flush stream cũng không bắt collector phải index sự kiện ngay.

### Phân biệt bốn khái niệm

| Khái niệm | Ý nghĩa | Không bảo đảm điều gì? |
| --- | --- | --- |
| **publish/write** | Handler/appender đã nhận và chuyển dữ liệu xuống stream hoặc buffer. | Dữ liệu đã thật sự đi hết mọi tầng. |
| **flush** | Yêu cầu tầng có buffer đẩy dữ liệu đang giữ tới đích dưới. | Đã fsync, đã lưu bền vững hoặc có ACK từ collector. |
| **close/stop** | Kết thúc vòng đời, thường flush rồi giải phóng tài nguyên theo hợp đồng implementation. | Nếu tiến trình bị kill cưỡng bức thì cleanup vẫn được thực hiện. |
| **fsync / remote ACK / durable commit** | Các cơ chế xác nhận riêng ở hệ thống lưu trữ/transport. | Không được tự động suy ra chỉ từ `flush()` trên console. |

Một log đã được viết vào stdout thường tiếp tục đi qua pipe, terminal, container runtime và collector; những tầng này có chính sách buffer, mất kết nối và retention riêng. Bởi vậy, **“đã flush” là trạng thái cục bộ của một stream/handler**, không phải một cam kết giao nhận end-to-end.

## 2. Khi nào cần quan tâm đến flush console?

Những tình huống thường gặp:

1. **CLI tương tác:** chương trình in prompt bằng `print()` mà không xuống dòng rồi chờ người dùng nhập. Flush giúp prompt được đẩy ra trước khi chờ.
2. **Đoạn xử lý batch/long-running:** muốn quan sát tiến trình mà không phụ thuộc vào lúc buffer đầy hoặc chương trình thoát.
3. **Ứng dụng sắp kết thúc:** muốn log cuối cùng được đẩy khỏi buffer của handler, trước khi đóng tài nguyên theo lifecycle.
4. **Debug trong container/CI:** bản ghi xuất hiện trễ do nhiều tầng buffering, redirect, log collector hoặc async logging.
5. **Có một handler tự viết:** `publish()` dùng writer/stream có buffer và chưa gọi `flush()` tại thời điểm phù hợp.
6. **Ứng dụng dùng nhiều console appender:** cùng một luồng stdout/stderr có thể nhận dữ liệu từ nhiều thành phần và cần thống nhất chính sách flush.
7. **Chạy dưới systemd/Docker/Kubernetes:** các stream thường được chuyển qua pipe thay vì cửa sổ terminal tương tác; thời điểm dữ liệu hiện trong UI còn phụ thuộc thành phần thu thập.

**Không nên tự động gọi flush sau mỗi lời gọi logger** mà chưa hiểu thư viện. Nhiều console handler/appender mặc định đã flush từng event; thêm `System.out.flush()` ở code nghiệp vụ có thể chỉ tăng contention và giảm throughput, không khắc phục vấn đề thật.

## 3. Console không đồng nghĩa System.console()

Ba đối tượng dễ bị nhầm:

- `System.out`: `java.io.PrintStream` đại diện **stdout** của tiến trình Java.
- `System.err`: `PrintStream` đại diện **stderr**.
- `System.console()`: trả về `java.io.Console` khi JVM có console tương tác thích hợp; trong IDE, CI hoặc nhiều container, giá trị này có thể là `null`.

Với console logging của server, đích thường là stdout hoặc stderr, **không cần** có `System.console()`. Không viết mã production giả định `System.console() != null`.

Ví dụ:

```java
System.out.println("INFO | Service started");
System.err.println("ERROR | Connection unavailable");
System.out.flush();
System.err.flush();
```

Hai dòng thuộc **hai stream độc lập**. Khi công cụ terminal nhập cả stdout và stderr vào một cửa sổ, **thứ tự hiển thị giữa hai stream không được bảo đảm tuyệt đối**, đặc biệt khi process chạy đa luồng hoặc bị redirect qua các pipe khác nhau. Không dùng thứ tự trộn stdout/stderr làm bằng chứng thời gian chính xác của sự kiện; thay vào đó, ghi timestamp/correlation ID phù hợp.

Một số logging backend có thể ghi console mặc định sang stdout; ngược lại, **JUL `ConsoleHandler` mặc định ghi sang stderr**. Đây là khác biệt rất dễ làm người học tưởng log bị mất khi chỉ redirect stdout.

## 4. java.io.PrintStream: print, println và autoFlush

`System.out` và `System.err` là `PrintStream`. Bản thân `PrintStream` có thể được xây dựng với cờ `autoFlush`. Khi **autoFlush=true**, API `PrintStream` có cơ chế tự flush output stream bên dưới khi thực hiện những thao tác như `println(...)`, viết mảng byte hoặc viết newline theo hợp đồng của class.

Ví dụ với một PrintStream do ta **tự tạo**, cờ autoFlush được lựa chọn tường minh:

```java
// Đoạn minh họa; không đóng stream này nếu tài nguyên
// stdout đang được chia sẻ với những thành phần khác.
java.io.PrintStream p = new java.io.PrintStream(
        System.out,
        true,
        java.nio.charset.StandardCharsets.UTF_8);
p.println("Service ready");
p.flush();
```

**Không nên dựa vào một giả định về cờ autoFlush của `System.out` trên mọi môi trường.** Thư viện/launcher/container có thể thay thế luồng bằng `System.setOut(...)`; một `PrintStream` mới có cấu hình khác với luồng ban đầu. Nên kiểm soát cách tạo stream ở nơi bạn sở hữu nó và dùng explicit flush tại những ranh giới cần thiết.

### Vì sao println thường hiển thị sớm hơn print?

`println()` chèn ký tự kết thúc dòng; với `PrintStream` autoFlush bật, nó kích hoạt flush theo hợp đồng của PrintStream. `print()` không luôn có hành vi như vậy. Đặc biệt khi in prompt không kết thúc dòng, bạn nên gọi `flush()` trước khi đọc input:

```java
// Minh họa trong chương trình CLI đã có Scanner input.
System.out.print("Enter order ID: ");
System.out.flush();
// String orderId = input.nextLine();
```

**Lưu ý:** đây là cơ chế của `PrintStream`, **không phải chính sách logger level**. `PrintWriter` có quy tắc autoFlush riêng: khi bật autoFlush, nó flush trên `println/printf/format`, không phải chỉ vì bất kỳ thao tác `write` nào gặp ký tự newline. Đừng suy luận API của `PrintWriter` từ `PrintStream`.

### PrintStream và lỗi I/O

Khác với `OutputStream.write(...)` thường có thể ném `IOException`, các phương thức `print/println` của `PrintStream` nhìn chung **không truyền `IOException` ra caller**; chúng ghi trạng thái lỗi nội bộ. `checkError()` flush và kiểm tra trạng thái lỗi của stream:

```java
System.out.println("Service ready");
System.out.flush();
if (System.out.checkError()) {
    // Cần một kênh báo lỗi khác nếu stdout đã không ghi được.
}
```

Không dùng chính stdout đã hỏng để log vô hạn một lỗi ghi stdout. Tín hiệu `checkError()` cũng **không phải xác nhận của collector** và không phản ánh mọi lỗi có thể xảy ra phía sau pipe/network.

## 5. Logger/Handler và flush: đừng flush nhầm tầng

Với `java.util.logging (JUL)`, ứng dụng thường gọi:

```java
logger.info("Order accepted");
```

JUL đưa `LogRecord` tới các `Handler`. Nếu handler có buffer, hãy gọi **`handler.flush()` trên handler đúng** khi thực sự cần, thay vì nghĩ rằng `System.out.flush()` tự động flush mọi handler.

```text
logger.info(...)
     |
     v
JUL Logger
     |
     v
StreamHandler
     |
  Writer buffer <---- handler.flush() cần xử lý buffer này
     |
     v
System.out
     |
  PrintStream buffer <---- System.out.flush() chỉ ảnh hưởng từ đây
     |
     v
OS stream
```

Nếu `StreamHandler` vẫn giữ dữ liệu trong writer phía trên, gọi `System.out.flush()` **không nhất thiết** khiến dữ liệu được ghi xuống bởi handler. Ngược lại, gọi `handler.flush()` là API được thiết kế để đẩy buffer mà handler quản lý.

### ConsoleHandler trong JUL

JUL cung cấp `java.util.logging.ConsoleHandler`, là một subclass của `StreamHandler` và mặc định ghi `System.err`. Implementation thông thường của JDK thực hiện `publish(record)` rồi flush mỗi bản ghi. Khi `ConsoleHandler` đã làm điều này, việc gọi `System.err.flush()` sau từng `logger.warning(...)` thường không đem lại lợi ích.

Để thử cấu hình JUL:

```properties
handlers=java.util.logging.ConsoleHandler
.level=INFO
java.util.logging.ConsoleHandler.level=INFO
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
```

Đây là mẫu file `logging.properties` với formatter mặc định, không phải ví dụ stdout tất định: `SimpleFormatter` thường in timestamp, class/method và có thể thay đổi theo cấu hình. Trong ứng dụng thật còn phải xét root logger, logger parent và việc có handler khác gây log trùng.

**Một đặc điểm của `ConsoleHandler.close()`:** implementation JUL ghi flush nhưng không đóng `System.err` chia sẻ. Trái lại, `StreamHandler.close()` có thể đóng output stream được truyền vào. Đừng gọi close tùy tiện trên một `StreamHandler(System.out, ...)` nếu ứng dụng còn cần stdout.

### StreamHandler trong JUL

`java.util.logging.StreamHandler` có các phương thức quan trọng:

| API | Tác dụng |
| --- | --- |
| `publish(LogRecord)` | Format và ghi bản ghi tới output stream nếu qua level/filter. |
| `flush()` | Đẩy các bản ghi đang được buffer ở handler xuống output stream. |
| `close()` | Ghi đuôi formatter nếu có, flush và đóng output stream theo hợp đồng. |
| `setEncoding(String)` | Chọn encoding trước khi bắt đầu ghi record. |

Không suy diễn rằng `StreamHandler.publish()` phải flush mỗi lần: `ConsoleHandler` có hành vi đặc thù. Khi tự triển khai handler ghi stream, phải lựa chọn rõ **khi nào publish, khi nào flush, khi nào close** và ai sở hữu stream.

## 6. Ví dụ Java 17 độc lập: autoFlush và JUL StreamHandler

Ví dụ này chạy bằng JDK 17 thuần, **không cần Maven, Logback hoặc Log4j 2**. Mục tiêu là tách biệt hai điều:

1. `PrintStream` do ta tạo có `autoFlush=false/true`; có thể quan sát xem `flush()` của stream nền được gọi hay chưa.
2. `StreamHandler` ghi tới một `ByteArrayOutputStream`, sau đó explicit `handler.flush()` bảo đảm toàn bộ hai record xuất hiện trong vùng đệm thu thập.

Bài học dùng một `TrackingOutputStream` để **đếm lời gọi flush** ở mức stream. Nó không giả vờ đo sự xuất hiện trên terminal trong thời gian thực; tốc độ hiển thị terminal/CI/collector không phải phép đo ổn định. Chương trình cũng sử dụng text ASCII và ký tự newline `\n` cố định để số byte là tất định trên Java 17 ở mọi hệ điều hành.

### 6.1. Tạo tệp ConsoleFlushDemo.java

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class ConsoleFlushDemo {

    private ConsoleFlushDemo() {
    }

    public static void main(String[] args) throws Exception {
        // Phần A: chứng minh thời điểm gọi flush của PrintStream.
        TrackingOutputStream manualSink = new TrackingOutputStream();
        PrintStream manual = new PrintStream(
                manualSink, false, StandardCharsets.UTF_8);
        manual.println("ping");
        System.out.println("AUTO_FLUSH_DISABLED="
                + (manualSink.flushCalls == 0));

        manual.flush();
        System.out.println("MANUAL_FLUSH_CALLED="
                + (manualSink.flushCalls > 0));
        manual.close();

        TrackingOutputStream autoSink = new TrackingOutputStream();
        PrintStream automatic = new PrintStream(
                autoSink, true, StandardCharsets.UTF_8);
        automatic.println("pong");
        System.out.println("AUTO_FLUSH_ON_PRINTLN="
                + (autoSink.flushCalls > 0));
        automatic.close();

        // Phần B: ghi log qua JUL StreamHandler và flush đúng handler.
        Logger logger = Logger.getLogger("demo.console.flush");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        for (Handler existing : logger.getHandlers()) {
            logger.removeHandler(existing);
        }

        ByteArrayOutputStream captured = new ByteArrayOutputStream();

        Formatter formatter = new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + "|"
                        + formatMessage(record)
                        + "\n";
            }
        };

        StreamHandler handler = new StreamHandler(captured, formatter);
        handler.setEncoding("UTF-8");
        handler.setLevel(Level.ALL);
        logger.addHandler(handler);

        logger.info("Order O-17 accepted");
        logger.warning("Queue almost full");

        // Đây là flush của Handler, không chỉ của System.out.
        handler.flush();

        System.out.println("JUL_AFTER_FLUSH:");
        System.out.print(captured.toString(StandardCharsets.UTF_8));
        System.out.println("JUL_BYTES=" + captured.size());
        System.out.flush();

        logger.removeHandler(handler);
        // ByteArrayOutputStream do demo sở hữu, có thể đóng an toàn.
        handler.close();
    }

    private static final class TrackingOutputStream
            extends ByteArrayOutputStream {
        int flushCalls;

        @Override
        public void flush() throws IOException {
            flushCalls++;
            super.flush();
        }
    }
}
```

### 6.2. Biên dịch và chạy

Trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 ConsoleFlushDemo.java
java ConsoleFlushDemo
```

**Stdout chính xác của chương trình**:

```text
AUTO_FLUSH_DISABLED=true
MANUAL_FLUSH_CALLED=true
AUTO_FLUSH_ON_PRINTLN=true
JUL_AFTER_FLUSH:
INFO|Order O-17 accepted
WARNING|Queue almost full
JUL_BYTES=51
```

### 6.3. Giải thích và kiểm chứng từng dòng

1. `PrintStream(manualSink, false, UTF_8)` được tạo với `autoFlush=false`. `println("ping")` không tự gọi `manualSink.flush()`, nên giá trị đếm vẫn là 0: `AUTO_FLUSH_DISABLED=true`.
2. `manual.flush()` gọi flush trên stream bên dưới, vì vậy `manualSink.flushCalls > 0` là true.
3. `PrintStream(autoSink, true, UTF_8)` có `autoFlush=true`; `println("pong")` kích hoạt flush của stream nền, tạo `AUTO_FLUSH_ON_PRINTLN=true`.
4. JUL `Logger` chỉ dùng handler được gắn trong demo và không truyền record lên handler của logger cha; vì vậy không có dòng log ngoài dự kiến từ `ConsoleHandler` mặc định.
5. `StreamHandler(captured, formatter)` ghi dữ liệu tới `ByteArrayOutputStream`; gọi `handler.flush()` trước khi đọc kết quả bảo đảm dữ liệu đang được writer/handler đệm đã chuyển vào buffer thu thập.
6. Chuỗi `INFO|Order O-17 accepted\n` dài **25 byte** và `WARNING|Queue almost full\n` dài **26 byte** ở UTF-8 vì toàn ký tự ASCII; tổng là **51 byte**. `JUL_BYTES=51` không phụ thuộc ký tự xuống dòng của Windows/Linux vì formatter ghi `"\n"` rõ ràng.
7. `System.out.flush()` chỉ flush stdout sau khi đã in kết quả. Chương trình không gọi `System.out.close()` vì stdout là tài nguyên dùng chung.

**Tại sao không đo “trước khi flush có bao nhiêu byte” của StreamHandler?** Chi tiết buffering của từng triển khai writer/stream có thể khác. Bằng chứng đáng tin ở đây là **sau khi handler.flush(), hai record đã có trong đích thu thập**. Không cần khẳng định rằng mọi implementation luôn có chính xác 0 byte trước flush.

**Giới hạn của ví dụ:** nó đo lời gọi flush, không đo thời điểm dữ liệu được terminal hiển thị, không mô phỏng collector, mất điện hay giao nhận network. `ByteArrayOutputStream.flush()` bản thân không tạo độ bền; lớp `TrackingOutputStream` chỉ giúp thấy hợp đồng autoFlush của PrintStream. Production có thể có buffering của OS và collector ngoài tầm kiểm soát của đoạn code này.

## 7. Flush console khi dùng Log4j 2

Với **Apache Log4j 2**, ứng dụng thường gọi `org.apache.logging.log4j.Logger` và cấu hình `ConsoleAppender`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <Console name="Console"
                 target="SYSTEM_OUT"
                 immediateFlush="true">
            <PatternLayout pattern="%level|%msg%n"/>
        </Console>
    </Appenders>
    <Loggers>
        <Root level="INFO">
            <AppenderRef ref="Console"/>
        </Root>
    </Loggers>
</Configuration>
```

Đây là **file `log4j2.xml` hoàn chỉnh**, nhưng để ứng dụng thật chạy cần các dependency Log4j 2 API/Core tương thích, logger code và môi trường Java phù hợp.

Các thuộc tính chính:

- `target="SYSTEM_OUT"`: gửi tới stdout; `SYSTEM_ERR` gửi tới stderr.
- `immediateFlush="true"`: appender flush bộ đệm của Log4j và stream Java sau mỗi event theo chính sách được Log4j 2 hỗ trợ; **đây thường là giá trị mặc định**.
- `PatternLayout`: chỉ định cách hiển thị event; việc `%n` tạo dòng mới **không đồng nghĩa một collector đã lưu thành công**.
- `<AppenderRef>`: logger phải tham chiếu đúng appender; nếu không có tuyến này thì flush không giúp đưa event đến Console.

### immediateFlush=true so với false

| Giá trị | Mục tiêu | Đánh đổi |
| --- | --- | --- |
| `true` | Đẩy buffer của appender/stream theo mỗi event; cải thiện tính kịp thời ở tầng xuất. | Có thể tăng chi phí flush và contention, làm giảm throughput ở tải rất cao. |
| `false` | Giảm số lần flush, tận dụng batching/buffering. | Có thể tăng độ trễ hiển thị và nguy cơ mất record chưa đẩy khi process dừng bất ngờ. |

Với async logger/appender, Log4j 2 có thể flush ở **ranh giới cuối batch**; không mặc nhiên hiểu `immediateFlush=false` là “không bao giờ flush”. Đồng thời, nếu event **chưa thoát khỏi async queue**, `System.out.flush()` ở thread nghiệp vụ không thể tự làm queue đó rỗng.

**Không nên tắt immediateFlush chỉ để làm mất triệu chứng log chậm.** Tối ưu cần benchmark cùng sink và kiểm tra tỷ lệ log đến nơi nhận, p95/p99 latency, CPU, hàng đợi và hành vi shutdown.

### ConsoleAppender và System.setOut

Tài liệu Log4j 2 mô tả các chế độ truy cập stream: mặc định appender có thể giữ tham chiếu tới `System.out/System.err` ở thời điểm cấu hình; `follow=true` theo dõi thay đổi sau `System.setOut/System.setErr`; `direct=true` có thể ghi trực tiếp tới file descriptor tương ứng và bỏ qua wrapper `System.out`.

Điều này quan trọng khi **test code capture System.out**:

- Nếu logger context được tạo **trước khi** test thay `System.out`, appender mặc định có thể vẫn viết vào stream cũ.
- Nếu dùng `direct=true`, output có thể đi thẳng tới file descriptor và **không xuất hiện trong ByteArrayOutputStream** mà test dùng để thay `System.out`.
- Gọi flush vào `System.out` vừa được thay không tự tác động tới stream cũ mà appender đang giữ.

Khi không thấy log trong test/IDE, cần kiểm tra appender target và thời điểm khởi tạo, không chỉ gọi `flush()` thêm lần nữa.

## 8. Flush console trong Logback và SLF4J

Trong các ứng dụng dùng **SLF4J + Logback**, code thường gọi facade `org.slf4j.Logger`, còn Logback `ConsoleAppender` làm nhiệm vụ xuất log. Cấu hình ví dụ trong `logback.xml`:

```xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <immediateFlush>true</immediateFlush>
        <encoder>
            <pattern>%level|%msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

**Đây là cấu hình Logback, không phải `log4j2.xml`.** Logback dùng `OutputStreamAppender` làm lớp nền cho nhiều appender hướng stream; thuộc tính `immediateFlush` thường mặc định true. Trong Logback hiện đại, thuộc tính này đặt tại **appender**, không nên đặt nhầm vào encoder theo các ví dụ rất cũ.

Các điểm cần nhớ:

- SLF4J là **API facade**: việc `logger.info(...)` có flush hay không phụ thuộc backend/provider cuối cùng và appender cấu hình.
- Nếu Logback đang dùng ConsoleAppender có `immediateFlush=true`, thêm `System.out.flush()` sau mọi lời gọi logger thường không phải giải pháp hiệu quả.
- Nếu Logback sử dụng `AsyncAppender`, còn có queue trước ConsoleAppender; flush stdout không giải quyết việc queue chưa được tiêu thụ.
- Với nhiều logger/appender, có thể có sự kiện gửi stdout và stderr; thứ tự giữa hai stream không được bảo đảm qua aggregator.

**Không dùng cú pháp của Logback cho Log4j 2 hoặc JUL**: dù cùng ý tưởng flush console, tên class, XML và phương thức quản lý lifecycle khác nhau.

## 9. Buffering và flush theo từng tầng

Một lỗi tư duy phổ biến là xem pipeline như một buffer duy nhất. Trong thực tế có thể có các tầng:

1. **Biểu thức Java:** mã tạo message, gọi `toString()` hoặc serialize dữ liệu trước khi gọi logger. Flush không làm biểu thức này nhanh hơn.
2. **Logger/level gate:** event có thể bị chặn tại logger nếu level không đủ; flush không thể hồi phục event bị loại.
3. **Async queue:** event được enqueue nhưng chưa được consumer xử lý. Flush console không buộc consumer hoàn tất.
4. **Layout/encoder:** định dạng message thành byte; với một số handler có writer buffer riêng.
5. **Appender/handler buffer:** có thể giữ byte hoặc record trước khi chuyển xuống OutputStream.
6. **PrintStream/OutputStream:** có thể còn dữ liệu được đệm ở Java stream.
7. **OS pipe/container runtime:** stdout/stderr được chuyển tới terminal hoặc log runtime.
8. **Collector/agent:** vận chuyển log đến kho, có thể batching/retry/backpressure.
9. **Storage/index:** nhận và lập chỉ mục để người dùng tìm kiếm.

**Muốn “log hiển thị ngay” phải xác định tầng nào gây trễ.** Nếu chỉ có file trong container mà không thấy trên dashboard, flush stdout không thể sửa collector tail nhầm file. Nếu AsyncAppender queue đang đầy, cần xử lý queue/sink/backpressure thay vì thay đổi PrintStream autoFlush.

### Phân biệt buffer với độ trễ hiển thị giao diện

Có trường hợp event đã tới stdout nhưng dashboard UI làm mới mỗi vài giây; một lần `flush()` nữa không làm chỉ số UI thay đổi ngay. Dùng phép đo có timestamp ở từng ranh giới, log collector metrics và công cụ đọc stream trực tiếp để xác định điểm trễ.

## 10. Flush khi shutdown, crash và tín hiệu dừng

### Graceful shutdown

Trong điều kiện bình thường, hệ logging nên có vòng đời:

```text
Application stops accepting work
          |
Outstanding tasks finish / stop logging producers
          |
Async queue drain theo timeout và chính sách
          |
Appenders/handlers flush
          |
Log context stop / close owned resources
          |
Process exits
```

Với JUL, nếu ứng dụng tự tạo và sở hữu các handler riêng, cần gọi `flush()`/`close()` phù hợp trong teardown và gỡ handler khỏi logger khi không còn dùng. **Không đóng nhầm `System.out` hoặc `System.err`** dùng chung. Nếu handler/framework được LogManager hoặc container quản lý, để chủ sở hữu quản lý vòng đời.

Trong Log4j 2, lifecycle context có cơ chế stop/shutdown; trong Logback, LoggerContext có cơ chế stop, thường do framework quản lý. Không viết code service gọi stop context **mỗi request**; làm vậy có thể khiến các request tiếp theo mất log.

### Forced termination

Nếu process bị `kill -9`, crash, mất điện hoặc container vượt thời gian shutdown và bị kill, shutdown hook có thể **không chạy**. Các record còn trong application buffer/async queue có thể mất. Dù đã flush tới OS pipe, collector phía sau vẫn có thể không kịp nhận hoặc lưu.

**Không tuyên bố console logging đã “không thể mất” chỉ vì bật immediateFlush**. Bảo đảm audit nghiệp vụ phải dùng kiến trúc durability riêng như transactional outbox, append-only audit store và xác nhận lưu giữ phù hợp yêu cầu. Console là một kênh quan sát, không phải một giao dịch ACID.

### Flush không phải fsync

`flush()` trên `PrintStream`/`Handler` là cơ chế đẩy dữ liệu từ Java buffers; `fsync` là cơ chế đồng bộ dữ liệu file với hệ thống lưu trữ ở cấp thấp hơn, và remote ACK lại là một loại xác nhận khác. Ngay cả fsync cũng không chứng minh dữ liệu đã được index/replicate trong kho phân tán. Chọn cơ chế theo mục tiêu nghiệp vụ, không dựa vào tên method.

## 11. Tác động tới hiệu năng và chính sách flush

Flush từng event thường ưu tiên tính kịp thời, nhưng trong ứng dụng có lượng log lớn nó có thể làm tăng chi phí CPU, synchronization hoặc I/O. Batching có thể giảm overhead nhưng làm tăng độ trễ và độ rủi ro của dữ liệu đang chờ.

Một bảng lựa chọn khái quát:

| Tình huống | Chính sách cân nhắc | Lưu ý |
| --- | --- | --- |
| CLI in prompt rồi chờ input | Flush tường minh sau prompt. | Không phụ thuộc newline hay autoFlush. |
| ConsoleHandler JUL mặc định | Dựa vào hành vi publish/flush của handler. | Mặc định ghi stderr; filter và formatter vẫn ảnh hưởng. |
| ConsoleAppender synchronous | Giữ `immediateFlush=true` nếu cần log xuất sớm. | Đo throughput, không giả định collector đã lưu. |
| Log rate rất cao | Đo buffering/batching, cân nhắc thay chính sách theo backend. | Theo dõi số event được nhận, queue và mất log. |
| Async appender/logger | Thiết kế drain, queue-full, error monitoring và shutdown. | Flush stdout không flush event chưa enqueue/consume. |
| Audit/security bắt buộc | Dùng đường ghi bền vững có xác nhận phù hợp. | Không chỉ dựa vào console flush. |

Không có con số “luôn flush sau N dòng” phù hợp mọi ứng dụng. Nó phụ thuộc throughput, giới hạn latency, kiểu sink, runtime và mức chấp nhận mất dữ liệu. Một benchmark có giá trị cần ghi nhận:

- **Latency request p50/p95/p99**, không chỉ thời gian gọi `println()`.
- **Throughput thực nhận ở sink**, không chỉ số log được gọi ở ứng dụng.
- **CPU, allocation, GC, lock contention**, nhất là khi nhiều thread ghi stdout.
- **Độ trễ từ event time tới ingestion/index**, xem dashboard cập nhật sau bao lâu.
- **Số record bị drop, queue depth, lỗi appender/collector**, đặc biệt với async.
- **Ảnh hưởng khi stdout bị chặn hoặc pipe reader ngừng đọc**, vì flush tới một pipe đầy có thể block.

**Bật autoFlush không phải “miễn phí”**, nhưng tắt flush chỉ để tăng benchmark throughput có thể đánh đổi bằng việc log tới muộn hoặc mất khi dừng bất ngờ.

## 12. Multithreading, ordering và stdout/stderr

Nhiều request thread có thể cùng gọi logger. Handler/appender thường có cơ chế đồng bộ hoặc serialization theo implementation để tránh ghi nửa record, nhưng **không suy ra rằng mọi logger, mọi appender và mọi process duy trì thứ tự nghiệp vụ tuyệt đối**.

Đặc biệt:

- Log từ **hai stream stdout/stderr** có thể được thu qua hai pipe độc lập và hiển thị không đúng thứ tự wall-clock.
- Log từ **nhiều instance** không có một hàng đợi chung, nên cần timestamp UTC/offset và correlation/trace IDs.
- Với **async logger**, việc xuất ở background thread có thể tạo độ trễ khác giữa event time và ingestion time.
- **Flush không thêm ordering guarantee** cho event giữa các thread/process.
- Nếu code dùng `System.out.print(...)` bên cạnh appender direct tới file descriptor, từng write có thể xen nhau theo cách khó dự đoán.

Để điều tra thứ tự, ưu tiên event ID, timestamp, sequence ID trong phạm vi hợp đồng cho phép và trace context. Không cố dùng `flush()` làm cơ chế đồng bộ chương trình; việc đồng bộ trạng thái giữa threads phải dùng công cụ concurrency như lock, volatile, happens-before hoặc queue có hợp đồng phù hợp.

## 13. Bảo mật và lỗi vận hành liên quan console flush

**Flush không có tác dụng redaction.** Nếu message chứa password, access token, refresh token, cookie, private key hoặc thông tin nhạy cảm, flush chỉ đẩy thông tin nguy hiểm đi nhanh hơn. Hãy loại bỏ trường nhạy cảm từ lúc tạo event, dùng allowlist và encoder chuẩn để tránh log injection.

Một input chứa newline có thể giả mạo dòng log nếu được nối vào text layout không được escape. Điều này không được sửa bằng `System.out.flush()`; cần encode/escape hoặc structured logging (ví dụ JSON Lines) đúng chuẩn.

Những lỗi thường gặp:

1. **“Gọi `System.out.flush()` sẽ flush mọi JUL handler.”** Sai: mỗi handler có buffer và stream riêng; cần flush đúng handler hoặc dùng lifecycle framework.
2. **“Không thấy JUL logger.info trên stdout nên logger bị lỗi.”** JUL ConsoleHandler mặc định ghi **stderr**; hãy kiểm tra redirect và handler thực tế.
3. **“`println()` luôn bảo đảm log hiển thị lập tức ở dashboard.”** Sai: autoFlush là chuyện của PrintStream, còn collector và UI có thể chậm.
4. **“Log4j 2 immediateFlush=true bảo đảm dữ liệu trên disk.”** Sai: chỉ flush Java/appender buffers, không tự fsync hoặc remote commit.
5. **“Khi không thấy INFO, cần flush liên tục.”** Sai: có thể logger level, appender filter hoặc AppenderRef đang loại INFO.
6. **“`System.console()` là đối tượng duy nhất để console logging.”** Sai: có môi trường không có interactive console, vẫn có stdout/stderr.
7. **“Đóng stdout để bảo đảm log cuối đã flush.”** Sai: có thể làm hỏng logging của những thành phần khác; chỉ close tài nguyên bạn sở hữu.
8. **“Tắt immediateFlush luôn cải thiện throughput và không có nhược điểm.”** Sai: tăng buffer/rủi ro log chưa ra khi crash; đo cả dữ liệu thực nhận.
9. **“Bật async thì chỉ cần `System.out.flush()` lúc shutdown.”** Sai: phải drain async queue và đóng logging context đúng cách.
10. **“Khi PrintStream không throw exception thì stdout chắc chắn khỏe.”** Sai: PrintStream thường giữ error flag, và còn lỗi ngoài JVM không thể quan sát ngay.
11. **“Một dòng console là một record JSON hợp lệ.”** Sai: formatter/layout phải escape dấu nháy, backslash, newline và quy định schema.
12. **“Flush giúp giải quyết mất log khi collector bị ngắt mạng.”** Không trực tiếp: cần quan sát/khắc phục đường vận chuyển, retry/spool hoặc kho bền vững.

## 14. Quy trình tìm nguyên nhân console log xuất hiện chậm

Khi phát hiện log không xuất hiện hoặc đến trễ:

1. **Kiểm tra code path:** lời gọi logging có thực sự được thực hiện không?
2. **Kiểm tra level/filter:** logger, handler, AppenderRef và appender có chấp nhận record không?
3. **Xác định đúng đích:** stdout, stderr, file hay network? JUL ConsoleHandler mặc định stderr; Log4j/Logback ConsoleAppender có thể cấu hình target khác.
4. **Kiểm tra formatter/layout:** record có newline cuối dòng không? Có lỗi encoding, exception trong formatter hoặc message đặc biệt?
5. **Kiểm tra buffer ở handler:** loại handler có flush tự động không? Với JUL StreamHandler tự tạo, có gọi `handler.flush()` khi cần không?
6. **Kiểm tra PrintStream:** stream có autoFlush không? Có `System.setOut/System.setErr`, `direct/follow` khiến appender giữ stream khác không?
7. **Kiểm tra async layer:** có queue/backpressure, queue-full, consumer chậm hoặc event bị discard không?
8. **Kiểm tra OS/container:** pipe reader có hoạt động, buffer đầy, log driver bị lỗi, container bị restart hay không?
9. **Kiểm tra collector/index:** log đã vào stream nhưng chưa được thu, parse hoặc index? Có nhầm timezone, khoảng truy vấn hoặc retention?
10. **Kiểm tra graceful shutdown:** process có cơ hội drain và close appender/handler hay bị kill cưỡng bức?

**Dấu hiệu phân loại nhanh:**

| Hiện tượng | Kiểm tra trước |
| --- | --- |
| Thấy log nếu chạy trực tiếp, không thấy sau redirect | stderr/stdout khác nhau, stream buffering và redirect. |
| INFO không xuất, ERROR có | Level/filter của logger/handler/appender. |
| Log chỉ xuất khi app kết thúc | Writer/handler buffering, autoFlush, lifecycle. |
| Log xuất chậm khi tải lớn | Async queue, I/O, pipe backpressure, collector lag. |
| Test capture System.out không thấy Log4j | Appender init trước khi đổi stream, chế độ direct/follow. |
| Console thấy log, dashboard không thấy | Collector/parser/index/retention, không phải chỉ flush stream. |
| Hàng cuối log mất sau crash | Buffer chưa drain và thiếu bảo đảm lưu bền vững. |
| Log bị trùng | Parent handler/additivity hoặc hai appenders chung sink, không phải flush. |

## 15. Kiểm thử flush và bảo đảm nội dung

Một test tốt cần tách **logic flush cục bộ** khỏi **độ trễ ingest thực tế**:

| Test | Mong đợi |
| --- | --- |
| PrintStream autoFlush=false + println | Không giả định tự flush; probe của demo đếm được 0 trước explicit flush. |
| PrintStream autoFlush=true + println | Probe nhận ít nhất một lần flush ở stream bên dưới. |
| JUL StreamHandler + explicit flush | Nội dung đã chuyển khỏi buffer handler tới output stream được kiểm soát. |
| JUL ConsoleHandler | Event được xuất tới stderr theo chính sách của handler. |
| Handler logger level INFO, record FINE | Không có event dù gọi flush. |
| Log4j ConsoleAppender `immediateFlush=true` | Buffer appender/stream được yêu cầu flush cuối event theo cấu hình. |
| Logback ConsoleAppender `immediateFlush=false` | Kiểm tra hành vi buffering, shutdown và event nhận thật. |
| Async queue backlog | Flush stdout không được coi là phép kiểm tra queue đã drain. |
| stdout bị thay thế trong test | Kiểm tra appender dùng stream cũ hay mới, direct/follow. |
| Input có dấu nháy và newline | Encoder không tạo dòng giả, không lộ dữ liệu nhạy cảm. |
| SIGTERM/graceful shutdown | Sự kiện được drain theo timeout thực tế trước khi process thoát. |
| SIGKILL/crash | Xác định số event có thể mất, không tuyên bố không mất chỉ từ flush. |
| Collector delay | Có metric/timestamp cho event time, ingestion time và tình trạng drop. |

**Đừng dùng `Thread.sleep(100)` để “sửa” việc flush** trong test hoặc production. Sleep không tạo ra hợp đồng drain/ACK, và kết quả phụ thuộc tải máy. Tốt hơn là kiểm tra rõ API flush/stop của đúng handler/context, hoặc dùng in-memory stream/collector mock với tín hiệu xác nhận.

## 16. Checklist trước khi triển khai production

- [ ] Hiểu rõ log đang vào stdout, stderr, file hay remote appender.
- [ ] Biết logger/handler/appender nào đang sở hữu buffer cần flush.
- [ ] Phân biệt `System.out.flush()`, `Handler.flush()` và lifecycle `LoggerContext.stop()`.
- [ ] Đặt `PrintStream` autoFlush có chủ ý nếu tự tạo stream.
- [ ] Dùng `ConsoleHandler`/ConsoleAppender với chính sách flush thích hợp, không gọi thêm flush lặp không cần.
- [ ] Cấu hình level/filter đúng; không lẫn sự kiện bị lọc với sự kiện bị buffer.
- [ ] Với Log4j 2/Logback, hiểu `immediateFlush` và cách async batching ảnh hưởng tới thời điểm xuất.
- [ ] Không đóng stdout/stderr chia sẻ hoặc logging context từ luồng nghiệp vụ ngẫu nhiên.
- [ ] Có shutdown/drain/timeout cho async logging và quan sát số record chưa đến sink.
- [ ] Có test stdout và stderr riêng, không dựa vào thứ tự trộn hai stream.
- [ ] Có metric về collector ingestion lag, drop/error và độ trễ truy vấn.
- [ ] Không ghi token/password/PII ngoài nhu cầu; encoder escape dữ liệu chưa tin cậy.
- [ ] Nếu audit cần độ bền, có đường lưu xác nhận riêng, không dùng console flush làm bằng chứng duy nhất.
- [ ] Đã chạy thử artifact cuối dưới đúng môi trường container/CI/server và kiểm tra đến kho truy vấn.

## Tài liệu tham khảo

- [Java 17 — PrintStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PrintStream.html)
- [Java 17 — PrintWriter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PrintWriter.html)
- [Java 17 — java.util.logging.ConsoleHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/ConsoleHandler.html)
- [Java 17 — java.util.logging.StreamHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/StreamHandler.html)
- [Java 17 — java.util.logging.Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html)
- [Apache Log4j 2 — Appenders, buffering và immediateFlush](https://logging.apache.org/log4j/2.x/manual/appenders.html)
- [Logback — Appenders và immediateFlush](https://logback.qos.ch/manual/appenders.html)

**Ghi nhớ:** Flush console là **đẩy dữ liệu đang được đệm ở một tầng stream/handler/appender**, không phải xác nhận end-to-end rằng log đã tới kho bền vững. Trong Java, hãy flush **đúng đối tượng sở hữu buffer**, hiểu stdout và stderr, phân biệt JUL ConsoleHandler với StreamHandler, và không bỏ qua async queue, shutdown, collector hoặc chính sách bảo mật.