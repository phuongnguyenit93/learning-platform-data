# Flush khi crash trong Java Logging: giới hạn, bảo vệ và kiểm chứng

## 1. “Flush khi crash” thực sự có nghĩa gì?

Trong **độ tin cậy logging**, “flush khi crash” là cách giảm nguy cơ mất các sự kiện log khi ứng dụng hoặc JVM dừng bất thường. Điều cần hiểu đầu tiên: **một tiến trình đã bị kết thúc thì không thể chạy thêm một lệnh flush sau thời điểm nó chết**. Ta chỉ có thể giảm khoảng dữ liệu chưa được chuyển khỏi bộ đệm **trước sự cố**, phối hợp shutdown khi hệ thống còn điều khiển được, và dùng hạ tầng lưu trữ đáng tin hơn nếu các bản ghi thật sự phải tồn tại sau crash.

Java logging có thể qua nhiều tầng:

~~~text
Business thread
   │ logger.error("...") / logger.info("...")
   ▼
Logging event: level + message + exception + context
   │
   ├─ Logger/appender đồng bộ: xử lý ngay trên luồng gọi
   │
   └─ Async queue / ring buffer: event có thể vẫn đang chờ
         │
         ▼
      Background consumer
         │
         ▼
      Encoder / BufferedWriter / byte buffer
         │ flush()
         ▼
      OS page cache / file system / socket
         │ force() / fsync hoặc cam kết ACK ở đích
         ▼
      Local storage / collector / durable log store
~~~

Một lệnh `logger.info(...)` trả về không nhất thiết chứng minh dữ liệu đã đi hết các tầng. “Flush” có thể nói đến **drain hàng đợi async**, **xả bộ đệm writer/appender** hoặc **ép dữ liệu xuống thiết bị lưu trữ**. Ba hành động có hợp đồng khác nhau; không thể dùng một từ “flush” để bảo đảm cả ba.

### Các trạng thái quan trọng

| Trạng thái | Ý nghĩa | Rủi ro còn lại |
| --- | --- | --- |
| Created | Caller đã tạo hoặc chuẩn bị log event | Chưa qua filter hoặc chưa được backend nhận |
| Accepted/enqueued | Event đã vào queue async hoặc được appender chấp nhận | JVM chết trước khi consumer xử lý; queue đầy có thể drop |
| Consumed/encoded | Consumer đã xử lý và có thể tạo byte | Byte vẫn có thể nằm trong bộ đệm Java/encoder |
| Writer flushed | `flush()` đẩy bộ đệm Java xuống stream/hệ điều hành | Không đồng nghĩa dữ liệu đã bền vững khi OS hoặc máy chủ crash |
| File forced | `FileChannel.force(...)` cố đẩy thay đổi tới thiết bị lưu trữ | Bảo đảm phụ thuộc local filesystem, phần cứng và phạm vi đồng bộ |
| Remote acknowledged | Collector nhận/ghi dữ liệu theo một hợp đồng ACK cụ thể | ACK “đã nhận” chưa chắc là ACK “đã commit bền vững” |

Đừng coi log file thông thường là giao dịch đã được commit. Nếu nghiệp vụ đòi hỏi **không mất audit event**, phải thiết kế write-ahead log, durable queue, transactional outbox hoặc kho dữ liệu có xác nhận bền vững phù hợp.

## 2. Những kiểu kết thúc JVM và khả năng flush

| Tình huống | Điều gì thường có thể xảy ra? | Có tin vào shutdown hook không? |
| --- | --- | --- |
| Ứng dụng hoàn tất bình thường | Code quản lý vòng đời đóng/flush appender; JVM có quá trình shutdown | Có thể chạy; vẫn phải tổ chức thứ tự shutdown đúng |
| `System.exit(code)` | Khởi động chuỗi shutdown của JVM và các hook đã đăng ký | Hook thường được khởi chạy, nhưng có thể bị giới hạn thời gian bởi môi trường |
| SIGTERM/interrupt được JVM xử lý | JVM có thể thực hiện shutdown có kiểm soát theo nền tảng | Có cơ hội; không là bảo đảm tuyệt đối khi có timeout hoặc cưỡng bức |
| `Runtime.getRuntime().halt(code)` | JVM kết thúc cưỡng bức, không bắt đầu/chờ shutdown hook | **Không** |
| SIGKILL / `kill -9` hoặc Windows `TerminateProcess` | Hệ điều hành chấm dứt tiến trình | **Không thể trông cậy** |
| JVM fatal error/native crash | JVM có thể dừng mà không đi qua lifecycle bình thường | Không có bảo đảm |
| Mất điện/OS crash/hỏng thiết bị | Cả tiến trình và hệ điều hành có thể ngừng làm việc | Không có cơ hội flush sau sự cố |

Một exception không bắt trong **một thread** không mặc nhiên bằng “JVM crash”. Handler của thread có thể ghi stack trace và các thread khác còn tiếp tục hoạt động; ứng dụng cũng có thể chủ động bắt và xử lý exception. Đừng mô phỏng crash bằng cách chỉ ném một `RuntimeException` trong task rồi kết luận shutdown hook được hay không được chạy.

**`System.exit(...)` khác `Runtime.halt(...)`.** JDK ghi rõ `halt` không khởi chạy shutdown hook. Vì vậy ví dụ thực nghiệm ở phần 5 dùng `halt` trong tiến trình con để kiểm tra điều gì xảy ra nếu writer không được đóng.

## 3. Phân biệt buffer Java, OS cache và lưu bền vững

### 3.1. `BufferedWriter.flush()`

Khi một `BufferedWriter` đã nhận text nhưng buffer chưa đầy, các ký tự có thể **chưa được đẩy** xuống `OutputStreamWriter`, `FileOutputStream` và hệ điều hành. Gọi `writer.flush()` sẽ xả các bộ đệm writer/stream ở phía Java theo hợp đồng của `Writer.flush()`.

~~~java
writer.write("event=order_paid");
writer.newLine();
writer.flush();
~~~

Đây là đoạn minh họa cần `writer` đã được tạo và quản lý. `flush()` làm thay đổi thời điểm byte tới tầng thấp hơn; nó **không** tương đương với đảm bảo “đã ghi lên thiết bị vật lý” trong trường hợp mất điện.

### 3.2. `FileChannel.force(boolean)`

Với tệp cục bộ, `FileChannel.force(true)` yêu cầu đồng bộ thay đổi **nội dung và metadata** xuống thiết bị lưu trữ; `force(false)` yêu cầu ít nhất đồng bộ nội dung. JDK 17 có hợp đồng mạnh cho tệp nằm trên **local storage device**, nhưng nói rõ không có bảo đảm tương tự cho tệp trên thiết bị không cục bộ.

Điều kiện quan trọng: dữ liệu còn trong `BufferedWriter` **chưa chắc đã được ghi vào channel**. Thứ tự đúng khi dùng hai tầng là:

~~~java
writer.flush();                     // Đưa byte xuống FileOutputStream.
fileOutputStream.getChannel().force(true); // Đồng bộ file qua channel liên kết.
~~~

Đoạn này cần `writer` được xây trên **chính** `fileOutputStream` tương ứng. Không tự mở một channel khác rồi gọi `force` và cho rằng mọi bộ đệm trong logger được xả; channel không có quyền biết dữ liệu đang nằm trong bộ đệm Java khác.

Đối với độ bền thực tế còn phụ thuộc filesystem, thiết bị, controller, cache có pin, cách fsync metadata của thư mục khi tạo/rename file, mạng và hợp đồng của storage layer. `force(true)` không tự động bảo đảm mọi điểm trong chuỗi log từ ứng dụng đến collector.

### 3.3. Flush của logger/appender

Một file appender có thể có `immediateFlush=true` để xả buffer sau khi xử lý event. Nhưng nếu một **AsyncAppender** đứng phía trước, event chưa đến file appender thì thuộc tính này chưa thể tác động. Cần phân biệt:

- **Queue drain:** worker đã lấy và xử lý các event trước một mốc.
- **Appender flush:** appender đã đẩy byte qua buffer của nó.
- **Durable commit:** tầng storage hoặc remote collector có cam kết bền vững.

Không tồn tại phương thức `Logger.flush()` chung cho tất cả JUL, SLF4J, Logback và Log4j 2. Phải dùng API lifecycle hoặc cơ chế barrier của từng backend.

## 4. Mất log ở đâu khi crash?

Xét một event được tạo lúc 10:00:00.000 và JVM bị kill lúc 10:00:00.005:

1. **Trước khi vào queue:** event có thể bị filter hoặc chưa được backend nhận.
2. **Trong queue async:** producer đã trả về nhưng consumer chưa lấy event; queue là dữ liệu trong RAM của tiến trình và biến mất khi JVM chết.
3. **Đang encode:** consumer đã lấy nhưng chưa hoàn thành định dạng; queue có thể đã rỗng dù log vẫn chưa tới file.
4. **Trong buffer writer/encoder:** event đã thành text/byte nhưng đang ở bộ đệm trong heap/direct buffer.
5. **Trong OS page cache:** JVM đã flush, nhưng crash hệ điều hành hoặc mất điện vẫn có thể mất dữ liệu chưa đồng bộ.
6. **Trên đường vận chuyển:** stdout của container, pipe, socket, logging agent hoặc collector có thể tồn tại buffer riêng.
7. **Tại collector:** HTTP 200, TCP write thành công hay “đã nhận” có thể không đồng nghĩa bản ghi đã được commit bền vững; cần xem hợp đồng cụ thể.

Nếu chỉ JVM chết còn hệ điều hành vẫn sống, byte đã flush tới OS có cơ hội tiếp tục được ghi và có thể đọc lại ngay. Nếu cả OS hoặc máy chủ chết, kết luận đó không còn đủ. Vì vậy các bài test “`kill -9` một Java process rồi đọc file” **không kiểm chứng** khả năng chống mất điện.

## 5. Ví dụ Java 17 chạy độc lập: giả lập dừng cưỡng bức của JVM con

Mục tiêu của ví dụ: **so sánh ba trạng thái của cùng một dòng text** khi JVM con bị `Runtime.halt(23)`. Tiến trình Java cha chạy tuần tự ba tiến trình con, đọc file sau khi mỗi tiến trình con kết thúc và in kết quả.

- `buffered`: ghi một dòng nhỏ vào `BufferedWriter` rồi halt mà chưa flush.
- `flushed`: flush writer trước khi halt.
- `forced`: flush writer, tiếp tục `FileChannel.force(true)` trước khi halt.

Tạo tệp **CrashFlushDemo.java**:

~~~java
import java.io.BufferedWriter;
import java.io.FileOutputStream;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;

public final class CrashFlushDemo {
    private static final String[] MODES =
            {"buffered", "flushed", "forced"};

    private static void runChild(String mode, Path path) throws Exception {
        // Không đóng stream: mô phỏng JVM bị dừng đột ngột.
        FileOutputStream file = new FileOutputStream(path.toFile());
        BufferedWriter writer = new BufferedWriter(
                new OutputStreamWriter(file, StandardCharsets.UTF_8), 8192);
        writer.write("event=critical");
        writer.newLine();

        if ("flushed".equals(mode) || "forced".equals(mode)) {
            writer.flush();
        }
        if ("forced".equals(mode)) {
            file.getChannel().force(true);
        }
        Runtime.getRuntime().halt(23);
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 3 && "--child".equals(args[0])) {
            runChild(args[1], Path.of(args[2]));
            return;
        }

        Path directory = Files.createTempDirectory("flush-crash-demo-");
        String executable = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT).contains("win")
                ? "java.exe" : "java";
        String java = Path.of(System.getProperty("java.home"),
                "bin", executable).toString();
        try {
            for (String mode : MODES) {
                Path path = directory.resolve(mode + ".log");
                Process process = new ProcessBuilder(
                        java, "-cp", System.getProperty("java.class.path"),
                        CrashFlushDemo.class.getName(),
                        "--child", mode, path.toString())
                        .start();
                int exit = process.waitFor();
                String content = Files.readString(path,
                        StandardCharsets.UTF_8).trim();
                if (content.isEmpty()) {
                    content = "<empty>";
                }
                System.out.println(mode + ": exit=" + exit
                        + " content=" + content);
                Files.deleteIfExists(path);
            }
        } finally {
            Files.deleteIfExists(directory);
        }
    }
}
~~~

Biên dịch và chạy trong thư mục chứa file source với **JDK 17+**:

~~~bash
javac --release 17 CrashFlushDemo.java
java CrashFlushDemo
~~~

**Stdout chính xác trong môi trường chạy thông thường có filesystem cục bộ:**

~~~text
buffered: exit=23 content=<empty>
flushed: exit=23 content=event=critical
forced: exit=23 content=event=critical
~~~

Tiến trình **cha** kết thúc mã `0`; ba tiến trình **con** đều kết thúc với mã `23`. Ví dụ không in gì ra stderr trong điều kiện bình thường.

**Giải thích kết quả:**

- `BufferedWriter` có buffer 8.192 ký tự; dòng nhỏ chưa đủ làm buffer đầy. Khi con gọi `halt(23)`, đoạn code không đóng/flush writer, file đã được tạo nhưng không chứa text.
- Khi gọi `writer.flush()`, text đi tới `FileOutputStream` và OS. Vì ở đây **chỉ JVM con** dừng, tiến trình cha đọc được byte đã tới OS.
- Chế độ `forced` gọi thêm `file.getChannel().force(true)` trên channel liên kết với chính stream đã flush. Kết quả **đọc lại** giống chế độ `flushed`, nhưng yêu cầu đồng bộ xuống storage là mạnh hơn theo hợp đồng JDK cho tệp cục bộ.
- Không thể chứng minh khác biệt giữa `flushed` và `forced` bằng cách chỉ đọc file ngay sau khi JVM con dừng: OS vẫn đang chạy và giữ cache.
- File được tạo trong thư mục tạm, mỗi mode có file riêng, sau đó bị xóa. Chương trình cố ý chỉ halt **tiến trình con** để không làm dừng chương trình chủ hoặc ứng dụng khác.

Ví dụ này là bài học về **buffer và tiến trình chết**, không phải implementation logger hoặc crash-test hệ điều hành. Không thêm `Runtime.halt(...)` vào ứng dụng nghiệp vụ để “kiểm tra flush” ở production; dùng test môi trường cô lập.

## 6. Với java.util.logging (JUL): flush handler không bằng cứu mọi crash

JUL là hệ thống logging có sẵn trong JDK; các handler phổ biến hoạt động đồng bộ trừ khi ứng dụng tự bổ sung cơ chế async. `java.util.logging.Handler` cung cấp `flush()` và `close()`; `StreamHandler` triển khai flush cho stream đích.

Đoạn minh họa trong ứng dụng đã có `java.util.logging.Logger logger`:

~~~java
for (java.util.logging.Handler handler : logger.getHandlers()) {
    handler.flush();
}
~~~

Lệnh này chỉ flush **các handler gắn trực tiếp** vào logger; event có thể đang được xử lý bởi handler của logger cha hoặc một tầng async tự triển khai. Nó không tạo ra cơ chế drain queue cho một custom async handler.

Khi dùng file logging:

- Kiểm tra `FileHandler` và formatter/handler level có được cấu hình đúng không.
- Xác định thời điểm `publish` và `flush` của handler thật; không mặc định mọi handler tùy biến có cùng semantics.
- Nếu tự tạo async handler, cần barrier có thứ tự: dừng nhận event mới, chờ worker xử lý các event trước barrier, flush handler đích rồi xác nhận hoàn tất.
- Nếu giữ handler chưa close khi tiến trình bị `halt`, `close()` hoặc shutdown hook sẽ không có cơ hội đảm bảo chạy.
- `Handler.flush()` và `FileChannel.force(...)` là hai tầng khác nhau; API `Handler` không tự cam kết fsync xuống thiết bị.

Nếu yêu cầu durability cao, phải đánh giá sink và chính sách của ứng dụng thay vì chỉ thêm một lệnh `flush()` khi gặp exception.

## 7. Với Logback Classic: immediateFlush và AsyncAppender

Logback `OutputStreamAppender` và `FileAppender` có tùy chọn `immediateFlush`. Mặc định nó là `true` trong các appender được tài liệu mô tả, nghĩa là sau khi appender **thực sự nhận và xử lý** một event, output stream được flush. Khi đặt `false`, throughput có thể tăng nhưng phần dữ liệu nằm trong bộ đệm có nguy cơ mất nếu appender không được đóng đúng cách.

Ví dụ **logback.xml** dành cho ứng dụng đã cài đúng Logback Classic:

~~~xml
<configuration>
    <appender name="FILE" class="ch.qos.logback.core.FileAppender">
        <file>logs/app.log</file>
        <append>true</append>
        <immediateFlush>true</immediateFlush>
        <encoder>
            <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ASYNC" class="ch.qos.logback.classic.AsyncAppender">
        <queueSize>2048</queueSize>
        <discardingThreshold>0</discardingThreshold>
        <neverBlock>false</neverBlock>
        <maxFlushTime>5000</maxFlushTime>
        <appender-ref ref="FILE"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="ASYNC"/>
    </root>
</configuration>
~~~

Các thuộc tính liên quan đến mất log:

| Thuộc tính | Công dụng | Giới hạn |
| --- | --- | --- |
| `immediateFlush=true` ở FILE | Đẩy buffer của file appender sau event đã được xử lý | Không thể flush event còn trong queue của ASYNC, không là fsync |
| `queueSize=2048` | Giới hạn số event chờ trong queue | Queue lớn hơn làm tăng lượng dữ liệu trong RAM có nguy cơ mất khi crash |
| `discardingThreshold=0` | Tắt chính sách chủ động discard TRACE/DEBUG/INFO khi queue gần đầy | Không tạo bảo đảm zero-loss khi kill hoặc lỗi sink |
| `neverBlock=false` | Khi queue đầy, producer thường bị chặn để tạo backpressure | Có thể tăng độ trễ ứng dụng; JVM vẫn có thể chết |
| `maxFlushTime=5000` | Khi stop async appender, chờ worker tối đa 5 giây để xử lý event còn chờ | Hết timeout thì log còn chờ có thể mất |

Mặc định, Logback AsyncAppender có thể drop TRACE/DEBUG/INFO khi queue còn khoảng 20% chỗ trống, nhằm bảo vệ throughput. Thay đổi `discardingThreshold` giúp điều chỉnh policy, không thay khả năng mất log do crash.

**Graceful shutdown đúng thứ tự:**

1. Ngừng nhận request, message hoặc job mới; đợi producer còn đang xử lý hoàn tất theo deadline.
2. Đảm bảo không còn thread sinh thêm log quan trọng vào context sắp bị dừng.
3. Dừng `LoggerContext` theo lifecycle của framework/container để AsyncAppender có thể drain queue và file appender được close/flush.
4. Đảm bảo deadline shutdown của container đủ bao phủ thời gian đợi; nếu bị SIGKILL sớm thì `maxFlushTime` không giúp gì.

Đoạn **minh họa** chỉ dành cho ứng dụng tự quản lý lifecycle của Logback:

~~~java
ch.qos.logback.classic.LoggerContext context =
        (ch.qos.logback.classic.LoggerContext)
                org.slf4j.LoggerFactory.getILoggerFactory();
context.stop();
~~~

Không gọi `context.stop()` ở mỗi request. Không kỳ vọng đoạn này chạy được sau `Runtime.halt`, SIGKILL hoặc mất điện. Với ứng dụng Spring Boot hoặc container đã quản lý vòng đời, dùng lifecycle do framework sở hữu để tránh stop lặp hoặc quá sớm.

## 8. Với Log4j 2: AsyncAppender, batch flush và shutdown

Log4j 2 phân biệt:

- **Async Appender:** appender có blocking queue, worker nhận event rồi chuyển sang appender đích.
- **Async Logger:** sử dụng Disruptor/ring buffer và cơ chế bất đồng bộ ở cấp logger.

Cả hai đều đưa thêm dữ liệu có thể nằm trong RAM khi sự cố xảy ra. Log4j 2 có hỗ trợ flush bộ đệm của file appender ở cuối event hoặc cuối batch, nhưng **không có cấu hình nào biến tất cả các logger async thành zero-loss khi tiến trình bị kill**.

Ví dụ **log4j2.xml** cho Async Appender:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <File name="FILE" fileName="logs/app.log"
              immediateFlush="true">
            <PatternLayout pattern="%d{ISO8601} %-5p %c - %m%n"/>
        </File>

        <Async name="ASYNC"
               bufferSize="1024"
               blocking="true"
               shutdownTimeout="5000">
            <AppenderRef ref="FILE"/>
        </Async>
    </Appenders>

    <Loggers>
        <Root level="info">
            <AppenderRef ref="ASYNC"/>
        </Root>
    </Loggers>
</Configuration>
~~~

Điểm cần hiểu:

- `Async` được khai báo **sau** `FILE` mà nó tham chiếu để hỗ trợ shutdown thứ tự đúng.
- `blocking=true` ưu tiên chặn producer khi queue đầy thay vì lập tức bỏ event theo một số queue-full policy; hành vi cụ thể còn tùy cấu hình và phiên bản.
- `shutdownTimeout=5000` giới hạn thời gian chờ worker xử lý log tồn khi Async Appender dừng. Theo tài liệu, `0` là chờ không giới hạn trong cơ chế được hỗ trợ, nhưng không cứu được tiến trình bị kill cưỡng bức.
- `immediateFlush=true` là chính sách flush buffer của file appender **sau khi nó nhận được event**; các sự kiện đang chờ trong async queue chưa được xử lý.
- `FileAppender` có thể flush ở cuối batch ngay cả khi `immediateFlush=false` trong chế độ async. “Flush to disk” trong tài liệu appender thường nói đến output buffer; vẫn cần phân biệt với `FileChannel.force(...)`/cam kết durable thực sự.

Nếu ứng dụng tự quản lý Log4j 2, có thể dùng API shutdown ở cuối vòng đời:

~~~java
org.apache.logging.log4j.LogManager.shutdown();
~~~

Đây là đoạn code trong dự án đã có Log4j 2 API/backend phù hợp. Đối với framework quản lý logging, phối hợp lifecycle thay vì tự stop từ một request. Cấu hình và API trên không làm shutdown hook tự xuất hiện sau `halt` hay SIGKILL.

## 9. Shutdown hook: có ích khi thoát bình thường, không cứu được crash

Shutdown hook hỗ trợ chạy code trước khi JVM dừng theo chuỗi shutdown chuẩn, ví dụ:

~~~java
Runtime.getRuntime().addShutdownHook(
        new Thread(() -> {
            // Chỉ có tác dụng khi JVM thực sự chạy chuỗi shutdown.
            // Thực hiện đóng logger qua lifecycle đúng framework.
        }, "logging-shutdown"));
~~~

Đoạn minh họa không đóng logger nào vì mỗi framework có API khác nhau. **Shutdown hook không phải bảo hiểm crash**:

- JVM không bắt đầu hook với `Runtime.halt(...)`.
- SIGKILL, TerminateProcess và native fatal crash có thể bỏ qua hook.
- Mất điện không cho chương trình cơ hội chạy.
- Hook có thể chạy đồng thời và không có thứ tự bảo đảm. Nếu một hook dừng logging trước khi hook khác ghi log, sự kiện cuối có thể bị mất.
- Môi trường container/orchestrator có thể ép kill sau thời hạn graceful shutdown.

Vì vậy, ứng dụng nên tổ chức lifecycle **bên ngoài hook khi có thể**: dừng nhận công việc, chờ producer, đóng async logging, rồi JVM kết thúc. Dùng hook như cơ chế bổ sung khi không có lifecycle manager; kiểm tra tránh đăng ký nhiều hook trùng nhau.

Khi hook ghi lỗi, nên có đường chẩn đoán tối thiểu như stderr hoặc health signal; chính backend logging đang được đóng có thể không hoạt động để báo lỗi của nó.

## 10. Console/stdout và log container có cần flush không?

Trong container, ứng dụng thường ghi ra stdout/stderr để runtime hoặc logging agent thu gom. Một dòng `System.out.println(...)` có thể đến pipe của container, nhưng sau đó còn những tầng khác:

~~~text
JVM PrintStream
    -> stdout/stderr pipe
    -> container runtime
    -> local log file / logging driver
    -> agent / collector
    -> remote storage/index
~~~

Gọi `System.out.flush()` chỉ tác động buffer của `PrintStream` và stream tương ứng **trong JVM**. Nó không buộc container runtime, log driver, agent mạng hoặc collector ghi bền vững. Nếu một ứng dụng dùng Logback AsyncAppender trước console appender, `System.out.flush()` cũng **không tự drain queue Logback**.

Các rủi ro khi crash:

- Event còn trong queue logging.
- Byte còn trong Java stream hoặc pipe ở lúc tiến trình bị kill.
- Logging driver/agent chưa xử lý hoặc không gửi kịp.
- Collector nhận nhưng chưa commit; lỗi mạng và retry có thể tạo trùng bản ghi.

Hãy xác minh chính sách buffer, retry, ACK và backpressure của từng tầng trong production. Nếu cần độ bền vượt quá JVM, nên dựa vào kho/queue chuyên dụng thay vì chỉ xả stdout trước khi thoát.

## 11. Thiết kế độ tin cậy theo mức quan trọng của log

Không phải sự kiện nào cũng cần chi phí fsync và chờ đồng bộ.

| Loại event | Mức bảo đảm thường phù hợp | Quyết định vận hành |
| --- | --- | --- |
| DEBUG/TRACE chẩn đoán | Có thể chấp nhận mất một phần khi crash | Async, batch, sampling, kiểm soát dung lượng |
| INFO vận hành thông thường | Giảm mất bằng flush appender và graceful shutdown | Giám sát backlog/drop, timeout có kiểm soát |
| ERROR/WARN quan trọng | Có thể cần sink ưu tiên, cảnh báo lỗi ghi | Không drop có chủ đích nếu yêu cầu điều tra cao |
| Audit bắt buộc/biến động giao dịch | Cần **cam kết bền vững** phù hợp trước bước nghiệp vụ quan trọng | Transactional outbox, durable stream/database, acknowledgment |
| Crash diagnostics | Phải có đường ngoài logger async khi khả thi | stderr, crash dump/JFR trước đó, log nền tảng |

Nếu cùng một sự kiện được ghi cả file lẫn remote collector, phải xác định cam kết thật sự: “ít nhất một sink nhận”, “cả hai sink commit” hay “không mất khi một replica chết”. Không có một cấu hình chung nào tự đạt mọi mục tiêu.

**Write-ahead log và outbox:** dữ liệu quan trọng được ghi cùng transaction nghiệp vụ hoặc một durable queue có chính sách ACK. Sau crash, worker có thể phát lại; cần idempotency, event ID và xử lý trùng lặp. Đây là kiến trúc lưu trữ sự kiện đáng tin, không phải một tùy chọn `flush=true` của logger.

## 12. Đo khoảng log có nguy cơ mất khi ứng dụng chết

Có thể ước tính số event còn chờ trong RAM tại một thời điểm:

~~~text
pending ≈ accepted_events - successfully_delivered_events
~~~

Nếu tốc độ nhận log là 4.000 event/giây và pipeline chậm hơn khoảng 2 giây ở một thời điểm, có thể có khoảng **8.000 event đang chờ** (ước tính đơn giản khi backlog gần tương ứng với 2 giây lưu lượng). Không thể dùng con số này để khẳng định chính xác 8.000 event sẽ mất vì có phần đã được sink xử lý/flush hoặc còn tồn ở tầng bên ngoài JVM.

Metrics đáng quan sát:

- Queue depth/ring buffer occupancy; tốc độ enqueue và consume.
- Số event drop/discard khi queue đầy; tỷ lệ overflow.
- Số lỗi I/O của appender, failed delivery và retry.
- Thời gian đợi flush/drain/shutdown; timeout và backlog còn lại.
- Độ trễ từ timestamp tạo event đến timestamp ở collector.
- Mức sử dụng disk, lỗi fsync/force, network errors, quota.
- Tỷ lệ bản ghi bị thiếu trong các sự kiện có ID liên tục hoặc marker kiểm thử.

Khi hệ thống không có counter số log đã **được sink nhận**, chỉ dùng `queue.size()==0` sẽ dẫn đến kết luận sai: worker có thể đã lấy event khỏi queue nhưng đang ghi/flush. Cần có mốc hoàn tất sau xử lý và một phép kiểm cuối cùng ở sink.

## 13. Quy trình shutdown giảm mất log

~~~text
SIGTERM / shutdown request
     │
     ▼
Ngừng nhận request, job hoặc message mới
     │
     ▼
Đợi producer kết thúc (deadline rõ)
     │
     ▼
Dừng dịch vụ còn tạo log
     │
     ▼
Stop logging context / drain async queue
     │
     ▼
Flush & close target appender / handler
     │
     ▼
Báo tiến trình hoàn tất và thoát JVM
~~~

Quy trình này chỉ hoạt động khi **hệ thống còn cho tiến trình chạy**. Nếu tổng thời gian graceful shutdown là 30 giây nhưng tác vụ nghiệp vụ chiếm 29 giây, logger có thể chỉ còn 1 giây để drain; phải phân bổ ngân sách thời gian cho toàn bộ đường thoát.

Các quyết định thực tế:

1. Đặt timeout drain nhỏ hơn deadline shutdown toàn tiến trình.
2. Nếu lượng log lớn, tăng khả năng xử lý sink và giới hạn backlog trước khi dựa vào timeout dài.
3. Không gọi `LoggerContext.stop()` hay `LogManager.shutdown()` khi producer còn tiếp tục ghi log quan trọng.
4. Không cố ghi một loạt log chẩn đoán lớn trong shutdown hook: có thể làm queue đầy thêm và kéo dài shutdown.
5. Ghi metric/status thất bại ở kênh độc lập nếu logging backend không còn sẵn.
6. Phân biệt “đã drain queue” và “đã durable” trong báo cáo vận hành.

## 14. Kiểm thử crash và flush như thế nào?

### 14.1. Kiểm thử theo từng loại kết thúc

| Thử nghiệm | Mục đích | Điều chưa chứng minh |
| --- | --- | --- |
| Thoát bình thường | Lifecycle close/flush hoạt động, file/log đủ | Cưỡng bức kill hay power loss |
| `System.exit(...)` | Shutdown hook/lifecycle có chạy không | `Runtime.halt`/SIGKILL |
| `Runtime.halt(...)` trong **child process** | Dữ liệu còn ở buffer JVM sẽ mất khi child dừng | Tính bền vững với OS crash |
| Kill cưỡng bức một process test | Đánh giá khả năng mất event chưa xử lý và log collector | Mất điện hoặc hỏng storage |
| Dừng trước khi async queue rỗng | Đo backlog/flush timeout/drop | Bảo đảm bền vững tới đích cuối |
| Lỗi I/O/network giả lập | Phản ứng khi sink không thể ghi | Tất cả lỗi hạ tầng thật |
| Crash test ở tầng máy/VM/storage cô lập | Kiểm tra policy fsync và recovery | Không thể suy ra cho mọi loại hardware/filesystem |

Không dùng crash injection ở một JVM production hoặc trong quá trình xử lý nghiệp vụ thật. Test nên sinh dữ liệu nhận diện bằng **event ID/sequence**, tạo sink riêng, kiểm tra log sau khởi động lại và đối chiếu với số event đã được chấp nhận.

### 14.2. Chứng minh đúng cấp độ

- **Đã có dòng trong file sau halt JVM:** chứng minh byte đã thoát khỏi một số buffer của JVM và OS còn đọc được.
- **Đã gọi `force(true)` thành công trên local file:** theo hợp đồng JDK, yêu cầu mạnh hơn ở cấp thiết bị lưu trữ cục bộ.
- **Đã gửi socket/HTTP:** không mặc định là remote durable commit; phải có ACK đúng nghĩa.
- **Đã đóng context logger đúng cách:** chứng minh có thực hiện đường graceful stop; không chứng minh điều gì về kill cưỡng bức.

Với bài test end-to-end, xác nhận thêm số event **thực sự đến** hệ thống log, thứ tự (nếu có hợp đồng), số event trùng và khoảng thiếu; tránh chỉ kiểm tra sự tồn tại của file hoặc exit code.

## 15. Sai lầm phổ biến

| Sai lầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| “Crash rồi sẽ flush trong `finally`” | `finally` không chạy nếu JVM bị cưỡng bức kết thúc | Dùng flush định kỳ/chính sách sink; đừng coi `finally` là crash hook |
| Tin shutdown hook luôn chạy | `halt`, SIGKILL, native crash và power loss không bảo đảm hook | Coi hook chỉ là graceful-shutdown aid |
| Gọi `System.out.flush()` để drain Logback AsyncAppender | Flush sai tầng; queue vẫn có thể còn event | Stop/drain đúng logging context |
| `queue.isEmpty()` nghĩa là log đã lưu | Consumer có thể đang xử lý event đã dequeue | Chờ xác nhận sau appender flush hoặc durable ACK |
| `immediateFlush=true` nghĩa là chống mất điện | Flush buffer stream không phải fsync | Dùng cam kết storage thích hợp |
| Gọi `force(true)` trước `writer.flush()` | Byte còn trong writer chưa vào FileChannel | Flush chain Java rồi force channel liên kết |
| `FileChannel.force(true)` là bảo đảm end-to-end | Không bao phủ async queue, remote collector và mọi storage phi cục bộ | Xác định phạm vi bảo đảm |
| Tăng queueSize vô hạn để “an toàn” | Tăng backlog RAM và lượng event có thể mất khi crash | Bounded queue, backpressure, throughput |
| Đặt `neverBlock=true` nhưng yêu cầu zero-loss | Queue đầy có thể drop event | Thiết kế policy drop/block theo yêu cầu |
| Không giám sát `maxFlushTime` timeout | Worker có thể còn log chưa xử lý khi app dừng | Đo số log còn chờ, tăng tốc sink và budget |
| Chạy test `Runtime.halt` trực tiếp trong process test chính | Dừng luôn runner, không thu được kết quả | Dùng tiến trình con cô lập như ví dụ |
| Chỉ test JVM halt rồi kết luận chịu được mất điện | OS page cache vẫn tồn tại sau khi JVM con chết | Cần test OS/storage riêng và hợp đồng fsync |
| Ghi audit bắt buộc vào async file logger rồi trả thành công | Có khoảng mất log khi crash | Dùng durable transaction/outbox/ACK |

## 16. Checklist trước khi triển khai

1. Xác định **mức độ mất log tối đa chấp nhận được** cho từng loại event: chẩn đoán, vận hành, bảo mật và audit.
2. Xác định logging backend thực sự: JUL, Logback, Log4j 2, đồng bộ hay async; không suy ra chỉ từ dependency facade.
3. Vẽ đường đi của event từ caller → queue → appender → file/stdout/network → collector.
4. Phân biệt flush buffer, drain queue, file force/fsync và durable acknowledgment; ghi rõ chỗ nào có hợp đồng.
5. Nếu dùng async, cấu hình queue, policy drop/block và thời hạn stop phù hợp với dung lượng và tốc độ sink.
6. Đảm bảo graceful shutdown dừng producer trước rồi mới dừng logger; kiểm tra container timeout.
7. Bật metrics cho queue backlog, event drop, lỗi sink, thời gian drain và missing events.
8. Kiểm thử cả normal exit, `System.exit`, `Runtime.halt` ở child process và tắt cưỡng bức trong môi trường riêng.
9. Nếu cần bền vững khi OS/power crash, chọn storage/queue có cam kết phù hợp; không coi `flush()` là điều kiện đủ.
10. Kiểm tra lại log sau restart bằng event ID, kể cả thiếu/trùng; đánh giá yêu cầu idempotency cho hệ thống audit.

## 17. Câu hỏi tự kiểm tra

1. Khi JVM chết trước khi `BufferedWriter.flush()`, tại sao dòng log có thể không xuất hiện dù `write()` đã trả về?
2. Vì sao một file còn đọc được sau `Runtime.halt(...)` **không** chứng minh dữ liệu sẽ tồn tại sau mất điện?
3. `writer.flush()` khác `file.getChannel().force(true)` như thế nào? Vì sao thứ tự hai lệnh quan trọng?
4. Nếu một async queue chưa rỗng nhưng `FileAppender.immediateFlush=true`, event nào vẫn có thể mất?
5. `System.exit()` và `Runtime.halt()` khác nhau về shutdown hook ra sao?
6. Tại sao `AsyncAppender.maxFlushTime=5000` không cứu được ứng dụng bị SIGKILL ngay?
7. Trong Log4j 2, khác biệt giữa Async Logger và Async Appender là gì về nơi giữ event tạm?
8. Tại sao `System.out.flush()` không bảo đảm collector của container đã commit log?
9. Vì sao một số audit event cần transactional outbox thay vì chỉ ghi file log async?
10. Khi kiểm thử crash, nên phân biệt event đã tạo, đã enqueue, đã ghi file và đã ACK bền vững như thế nào?

**Gợi ý đáp án:** (1) dữ liệu còn trong buffer heap; (2) OS cache vẫn còn sau khi chỉ một JVM con chết; (3) flush Java buffer trước, force xuống storage sau; (4) event còn trong queue; (5) exit khởi động shutdown, halt bỏ qua hook; (6) worker không có cơ hội hoàn tất; (7) queue appender và ring buffer logger; (8) có nhiều tầng phía sau JVM; (9) cần commit và phát lại bền vững; (10) đo ở từng ranh giới, không dùng một boolean “flushed”.

## 18. Tài liệu chính thức

- [Java SE 17 — Runtime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html): `exit`, `halt`, shutdown hook, giới hạn khi tiến trình bị dừng cưỡng bức.
- [Java SE 17 — Writer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Writer.html): `flush()` đẩy Java buffers tới OS nhưng không bảo đảm ghi thiết bị vật lý.
- [Java SE 17 — BufferedWriter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedWriter.html): buffer và `flush()`.
- [Java SE 17 — FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): `force(boolean)`, bảo đảm cục bộ và giới hạn của tệp phi cục bộ.
- [Java SE 17 — Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html): `flush()` và `close()` của JUL.
- [Logback — File/Console appenders](https://logback.qos.ch/manual/appenders-console-file.html): `immediateFlush` và nguy cơ mất buffer khi exit đột ngột.
- [Logback — AsyncAppender](https://logback.qos.ch/manual/appenders-async-sift.html): queue, `discardingThreshold`, `maxFlushTime` và stop.
- [Apache Log4j 2 — Async loggers](https://logging.apache.org/log4j/2.x/manual/async.html): lợi ích/đánh đổi của async và lưu ý với audit.
- [Apache Log4j 2 — Async Appender](https://logging.apache.org/log4j/2.x/manual/appenders/delegating.html): queue và shutdown.
- [Apache Log4j 2 — Appenders](https://logging.apache.org/log4j/2.x/manual/appenders.html): `immediateFlush` và flush buffer ở cuối event/batch.
