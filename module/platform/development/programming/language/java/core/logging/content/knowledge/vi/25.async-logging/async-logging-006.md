# Flush async log trong Java

## 1. Flush async log là gì và giải quyết vấn đề nào?

Trong **logging bất đồng bộ (asynchronous logging)**, lời gọi `logger.info(...)` hoặc `logger.error(...)` thường đưa một sự kiện vào hàng đợi hoặc bộ đệm rồi trả quyền điều khiển cho luồng ứng dụng. Một luồng nền lấy các sự kiện đó, định dạng và chuyển tới file, console, mạng hoặc hệ thống tập trung. Nhờ vậy, luồng xử lý nghiệp vụ ít phải chờ I/O, nhưng tại một thời điểm có thể vẫn còn log **chưa được ghi ra nơi nhận**.

**Flush async log** là thao tác hoặc quá trình bảo đảm một nhóm sự kiện đã được nhận trước một mốc xác định được **xử lý hết qua hàng đợi và đẩy bộ đệm đầu ra xuống tầng đích** theo hợp đồng cụ thể của logger/appender. Cần phân biệt từng tầng để tránh tưởng rằng một lời gọi ghi log đã lưu dữ liệu an toàn.

~~~text
Luồng ứng dụng
   │ logger.info("order-created")
   ▼
[Queue / Ring Buffer] -- sự kiện đã được nhận, có thể còn chờ
   │
   ▼
[Consumer / Async Appender] -- định dạng, chuyển sự kiện
   │
   ▼
[Buffered writer / File appender] -- byte có thể còn trong bộ đệm
   │ flush()
   ▼
[OS / File system / Network] -- đã được chuyển xuống tầng kế tiếp
   │ fsync / ACK bền vững (nếu hệ thống hỗ trợ và yêu cầu)
   ▼
[Durable storage / Remote collector]
~~~

Cùng một từ “đã ghi” có thể mô tả các mốc khác nhau:

| Mốc | Điều đã xảy ra | Điều chưa được bảo đảm |
| --- | --- | --- |
| **Accepted / enqueued** | Async logger chấp nhận sự kiện và có thể trả về cho caller | Consumer đã xử lý hay chưa; có bị discard sau đó không |
| **Dispatched / processed** | Consumer lấy sự kiện và gọi appender đích | Bộ đệm của appender đã flush chưa; appender đích thành công hay không |
| **Flushed to OS / transport** | Bộ đệm của writer/appender đã được đẩy xuống stream, hệ điều hành hoặc transport theo API | Mất điện hoặc crash máy chủ sẽ không làm mất dữ liệu |
| **Durable / acknowledged** | Có cam kết bền vững phù hợp, ví dụ sync storage hoặc ACK có hợp đồng rõ ràng từ hệ thống nhận | Không có bảo đảm end-to-end vượt quá phạm vi ACK |

Ví dụ `BufferedWriter.flush()` bảo đảm phần ký tự còn trong bộ đệm Java được ghi xuống writer bên dưới, nhưng **không tương đương** `FileChannel.force(true)` hay bảo đảm fsync. Nếu log truyền qua mạng, flush phía gửi cũng không đồng nghĩa hệ thống nhận đã lưu bền vững.

## 2. Khi nào cần flush?

Những thời điểm thường quan trọng:

1. **Graceful shutdown/redeploy:** dừng tiếp nhận công việc mới, đợi các tác vụ phát log hoàn tất, để logging context tiêu thụ hàng đợi, flush và đóng appender trước khi JVM dừng.
2. **Chuyển đổi hoặc đóng sink:** trước khi đóng, đổi file hoặc ngắt kết nối, cần hoàn thành những bản ghi đang chờ theo cơ chế của appender/framework.
3. **Kiểm thử tích hợp:** sau khi phát log bất đồng bộ, cần một mốc hoàn tất xác thực được trước khi mở file đọc hay kiểm tra kết quả.
4. **Điểm kiểm soát có yêu cầu rõ về log:** một công cụ quản trị hoặc luồng xử lý cần chờ các log trước mốc đó được xử lý. Cần xem framework có thực sự cung cấp API drain/flush phù hợp không.
5. **Sau một đợt ghi lớn:** có thể dùng batch flush ở tầng appender nếu được hỗ trợ, nhưng không nên tạo flush đồng bộ trên mỗi sự kiện nếu mục tiêu là throughput.

**Không mặc định flush sau mọi request hoặc mọi câu lệnh log.** Làm vậy có thể triệt tiêu lợi ích async, làm tăng tail latency và tranh chấp I/O. Nếu một sự kiện kiểm toán hoặc giao dịch tài chính bắt buộc được lưu bền vững **trước khi trả thành công**, hãy dùng cơ chế ghi có xác nhận bền vững (cơ sở dữ liệu, outbox, durable queue, đồng bộ hóa phù hợp), thay vì coi file log async thông thường là nguồn sự thật giao dịch.

## 3. Điều kiện để “đã flush” thực sự có ý nghĩa

Một thiết kế flush đúng cần trả lời rõ ba câu hỏi:

**(a) Đang chờ tập sự kiện nào?** Mốc flush phải được đặt **sau** các sự kiện cần bảo đảm. Với nhiều thread đồng thời, một sự kiện vừa được tạo ra nhưng chưa enqueue có thể nằm **sau** mốc flush. Khi shutdown, cần kiểm soát producer còn chạy hay không.

**(b) Đang chờ đến công đoạn nào?** Chỉ kiểm tra `queue.size() == 0` không đủ: consumer có thể đã lấy sự kiện cuối khỏi queue nhưng vẫn đang ghi file hoặc gửi mạng. Mốc hoàn thành cần được xác nhận **sau khi** consumer xử lý các sự kiện trước đó và gọi flush trên sink.

**(c) Thất bại được phản hồi thế nào?** Flush có thể timeout hoặc I/O lỗi. Hệ thống nên có chính sách cho phép chờ bao lâu, có retry/failover hay không, báo lỗi ra kênh nào và thống kê những sự kiện bị drop. Nếu async framework bắt hoặc ghi nội bộ lỗi ở background thread, caller không nhất thiết được nhận exception.

Không thay các điều kiện đó bằng `Thread.sleep(1000)`: chờ cố định một giây chỉ làm tăng xác suất consumer chạy xong, không tạo quan hệ bảo đảm.

## 4. Ví dụ Java 17 chạy độc lập: dùng barrier trong hàng đợi

Ví dụ sau sử dụng `ExecutorService.newSingleThreadExecutor()` như **mô phỏng consumer async** và `BufferedWriter` làm sink. Hai thao tác ghi và thao tác flush được gửi **theo đúng thứ tự** lên cùng một executor. `Future.get()` của tác vụ flush là **barrier**: khi trả về bình thường, consumer đã chạy xong hai thao tác trước nó và đã gọi `writer.flush()`.

Tạo tệp **AsyncFlushDemo.java**:

~~~java
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class AsyncFlushDemo {
    private static void append(BufferedWriter writer, String line) {
        try {
            writer.write(line);
            writer.newLine();
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    private static void flush(BufferedWriter writer) {
        try {
            writer.flush();
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    public static void main(String[] args) throws Exception {
        Path path = Path.of("async-demo.log");
        ExecutorService worker = Executors.newSingleThreadExecutor();
        try (BufferedWriter writer =
                     Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
            Future<?> first = worker.submit(
                    () -> append(writer, "event=start"));
            Future<?> second = worker.submit(
                    () -> append(writer, "event=done"));
            Future<?> barrier = worker.submit(() -> flush(writer));

            barrier.get(); // Chờ các thao tác ghi trước đó và flush kết thúc.
            first.get();   // Phát hiện IOException từ tác vụ ghi thứ nhất.
            second.get();  // Phát hiện IOException từ tác vụ ghi thứ hai.
            System.out.println("flush complete");
            System.out.println(Files.readAllLines(path, StandardCharsets.UTF_8));
        } finally {
            worker.shutdown();
            if (!worker.awaitTermination(5, TimeUnit.SECONDS)) {
                worker.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac --release 17 AsyncFlushDemo.java
java AsyncFlushDemo
~~~

**Stdout chính xác:**

~~~text
flush complete
[event=start, event=done]
~~~

File `async-demo.log` chứa hai dòng:

~~~text
event=start
event=done
~~~

**Vì sao ví dụ hoạt động?**

- `newSingleThreadExecutor()` thực thi các tác vụ đã nhận lần lượt theo thứ tự nộp vào executor.
- `append(...)` ghi vào `BufferedWriter`. Khi tác vụ ghi kết thúc, dữ liệu **có thể vẫn ở bộ đệm**.
- Tác vụ thứ ba gọi `writer.flush()`, tiếp theo `barrier.get()` chờ flush thật sự hoàn thành. Lúc đó mới đọc file để kiểm tra.
- `first.get()` và `second.get()` phát hiện ngoại lệ của hai tác vụ ghi; chỉ chờ barrier mà không kiểm tra lỗi tác vụ trước đó có thể bỏ sót lỗi.
- `shutdown()` và `awaitTermination(...)` thu hồi executor; `try-with-resources` đóng writer. Thứ tự ở ví dụ an toàn vì barrier đã hoàn thành trước lúc thoát khỏi khối `try`.

Đây là **mô hình minh họa**, không phải một logger production. Executor mặc định có hàng đợi không giới hạn cố định theo `newSingleThreadExecutor()`; ứng dụng thật cần chính sách dung lượng, backpressure, giám sát, timeout và xử lý lỗi khi sink bị treo. Mốc barrier ở đây chỉ bao phủ **các tác vụ đã được enqueue trước nó vào cùng executor**. Nếu những producer khác tiếp tục submit đồng thời, cần đồng bộ hóa điểm nhận log hoặc dừng producer để xác định ranh giới flush. Nó cũng không bảo đảm fsync của hệ điều hành.

## 5. Flush trong Java Util Logging (JUL)

`java.util.logging.Handler` có phương thức:

~~~java
public abstract void flush();
~~~

Theo tài liệu JDK, hợp đồng là flush **đầu ra được buffer của Handler**. `StreamHandler.flush()` cũng mô tả việc flush các bản ghi đã được buffer trong stream. Nhưng:

- JUL chuẩn **không mặc định biến mọi `Logger` thành logger async**. Với handler đồng bộ, `flush()` chủ yếu đẩy bộ đệm stream.
- Nếu ứng dụng tự tạo `AsyncHandler` có queue riêng và ủy quyền tới `FileHandler`, gọi `underlyingFileHandler.flush()` **không buộc** các sự kiện còn trong async queue phải tới handler đó trước.
- Custom async handler muốn hỗ trợ flush cần có **drain barrier** hoặc cơ chế tương đương, gọi flush của handler đích **sau khi** xử lý hết các sự kiện thuộc mốc đó, và công bố rõ timeout/cách báo lỗi.
- `Logger` của JUL không có phương thức `flush()` tổng quát. Việc duyệt `logger.getHandlers()` chỉ nhìn các handler gắn trực tiếp vào logger đó; còn có thể tồn tại handler ở logger cha.

Ví dụ minh họa thao tác flush trên handler đã có:

~~~java
for (java.util.logging.Handler handler : logger.getHandlers()) {
    handler.flush();
}
~~~

Đoạn trên cần biến `logger` đã được khai báo và cấu hình; nó **không phải một giải pháp drain queue** cho mọi kiến trúc async, và không bao phủ các handler của logger cha.

## 6. Logback: AsyncAppender drain khi LoggerContext dừng

Với Logback Classic, `AsyncAppender` sử dụng `BlockingQueue` và một worker nền để chuyển sự kiện sang appender đích. Khi ứng dụng tắt/redeploy, cần **stop LoggerContext** để async appender có cơ hội xử lý các sự kiện còn trong queue. Phương thức stop sẽ đợi tối đa theo `maxFlushTime`.

Ví dụ tệp **logback.xml** (đã có dependency Logback Classic và SLF4J phù hợp):

~~~xml
<configuration>
    <appender name="FILE" class="ch.qos.logback.core.FileAppender">
        <file>app.log</file>
        <append>true</append>
        <encoder>
            <pattern>%d{ISO8601} %-5level [%thread] %logger - %msg%n</pattern>
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

Ý nghĩa các tham số:

| Thuộc tính | Tác dụng và đánh đổi |
| --- | --- |
| `queueSize=2048` | Tối đa 2.048 sự kiện chờ trong queue của AsyncAppender; không nên đặt theo cảm tính nếu tốc độ ghi/sink biến động. |
| `discardingThreshold=0` | Tắt quy tắc mặc định chủ động bỏ bản ghi TRACE/DEBUG/INFO khi queue gần đầy; **không phải** bảo đảm tuyệt đối không mất log. |
| `neverBlock=false` | Khi queue đầy, producer có thể bị chặn cho đến khi có chỗ; chọn backpressure thay vì thả rơi vì cấu hình `neverBlock=true`. |
| `maxFlushTime=5000` | Khi stop, cho worker chờ tối đa khoảng 5 giây để hoàn tất việc đẩy sự kiện còn tồn; những sự kiện chưa xử lý kịp có nguy cơ mất. |

Trong Logback, `maxFlushTime=0` có nghĩa chờ **không giới hạn** cho worker hoàn tất lúc stop; điều đó giảm nguy cơ mất sự kiện do timeout nhưng có thể làm shutdown treo nếu sink chậm hoặc ngừng đáp ứng. Chọn timeout và thời gian graceful termination của môi trường chạy một cách nhất quán.

Với ứng dụng **tự quản lý vòng đời Logback** (không để framework điều khiển), đoạn sau minh họa lệnh stop tại cuối quá trình shutdown:

~~~java
import ch.qos.logback.classic.LoggerContext;
import org.slf4j.LoggerFactory;

// Thực hiện một lần khi ứng dụng dừng, sau khi producer đã hoàn tất.
LoggerContext context =
        (LoggerContext) LoggerFactory.getILoggerFactory();
context.stop();
~~~

Đây là đoạn minh họa cần thư viện Logback; không chạy độc lập bằng JDK. Trong Spring Boot hoặc container, ưu tiên cơ chế lifecycle do framework quản lý và đảm bảo nó được thực thi. **Không gọi `context.stop()` ở cuối mỗi request**, vì việc stop vô hiệu hóa logging context và appender cho công việc tiếp theo.

**Lưu ý:** Logback có thể discard sự kiện ít nghiêm trọng khi queue còn khoảng 20% dung lượng, theo cấu hình mặc định. `discardingThreshold=0` thay đổi chính sách discard này nhưng không cứu được log khi máy chủ bị kill, thiếu dung lượng đĩa, lỗi sink, hoặc shutdown quá thời gian.

## 7. Log4j 2: Async Appender và shutdownTimeout

Log4j 2 có **Async Appender** (hàng đợi và background thread) cùng cơ chế **Async Logger** (dùng Disruptor); đây là hai lựa chọn kiến trúc khác nhau. Ví dụ này sử dụng **Async Appender**.

Tạo **log4j2.xml** trong classpath của ứng dụng đã cấu hình `log4j-api` và `log4j-core`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <File name="FILE" fileName="app.log">
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

- `bufferSize` giới hạn hàng đợi Async Appender.
- `blocking=true` khiến caller chờ hoặc áp dụng queue-full policy thích hợp khi không có chỗ; xem chính sách queue đầy của phiên bản Log4j đang chạy. Các cấu hình discard/failover có thể thay đổi hành vi.
- `shutdownTimeout=5000` cho phép chờ worker dừng trong tối đa 5.000 ms khi Async Appender shutdown. Theo tài liệu Log4j 2, giá trị `0` đợi tới khi queue rỗng.
- Appender đích `FILE` cần được khai báo **trước** `ASYNC` mà nó tham chiếu để hỗ trợ shutdown đúng thứ tự.
- Async Appender của Log4j 2 flush bộ đệm appender đích về phía OS **sau một batch khi queue trống**. Việc đó không bảo đảm dữ liệu đã được đồng bộ bền vững xuống thiết bị lưu trữ.

Nếu ứng dụng **tự quản lý** Log4j 2, có thể đóng logging context ở cuối vòng đời:

~~~java
org.apache.logging.log4j.LogManager.shutdown();
~~~

`LogManager.shutdown()` là thao tác đồng bộ, có thể chờ xử lý log tồn đọng (kể cả thao tác qua mạng), và dừng context tương ứng của caller. Không gọi trong code xử lý bình thường hoặc test đang tiếp tục ghi vào cùng context. Trong ứng dụng được container/framework quản lý, phối hợp lifecycle để tránh đóng context quá sớm.

Đừng nhầm `immediateFlush=true` của file appender với “caller chờ toàn bộ async queue”. Cấu hình file appender chỉ quyết định cách nó đẩy buffer **khi consumer đã gọi đến appender**, còn queue phía trước vẫn có thể đang chứa sự kiện.

## 8. Quy trình graceful shutdown an toàn

Một chuỗi shutdown tiêu biểu:

~~~text
Nhận tín hiệu shutdown
  → ngừng nhận request/message/job mới
  → đợi hoặc hủy có kiểm soát tác vụ đang chạy
  → ngừng producer tạo log mới
  → stop logging context/async appender (drain queue + flush sink)
  → giải phóng file, socket, worker logging
  → JVM kết thúc trong thời hạn của môi trường chạy
~~~

Cần đặt **thời gian chờ thoát của JVM/container lớn hơn tổng ngân sách** đóng kết nối, hoàn tất công việc và flush log. Nếu container gửi SIGKILL ngay sau khi timeout, shutdown hook hoặc worker logging không có thêm cơ hội chạy.

Phân biệt:

- **Graceful exit:** logger được stop và có cơ hội đẩy hàng đợi theo thời hạn.
- **Đóng đột ngột:** `kill -9`, JVM crash, lỗi hệ điều hành, mất điện có thể làm mất mọi sự kiện chưa thực sự bền vững.
- **Sink bị treo:** chờ vô hạn có thể giữ tiến trình sống; timeout giúp thoát nhưng phải chấp nhận log có thể bị mất.
- **Producer còn hoạt động:** nếu một thread vẫn phát log sau khi logging context đã dừng, sự kiện mới có thể bị từ chối hoặc không được ghi; cần phối hợp thứ tự dừng.

Shutdown hook có thể hỗ trợ nhưng không thay thế quản lý lifecycle của container. Không dựa vào `finally` hoặc shutdown hook để khẳng định bảo đảm khi JVM bị kill cưỡng bức.

## 9. Những cách “flush” không đúng

| Cách làm dễ nhầm | Vì sao sai hoặc chưa đủ | Cách phù hợp |
| --- | --- | --- |
| Gọi `logger.info(...)` rồi lập tức mở file kiểm tra | Lời gọi có thể mới enqueue; consumer chưa chạy | Dùng barrier/flush chính thức hoặc stop context trong bài test |
| `Thread.sleep(500)` trước khi tắt | Không có cam kết thời gian drain, phụ thuộc tải và I/O | Chờ tín hiệu hoàn thành với deadline có ý nghĩa |
| Chờ đến khi `queue.isEmpty()` | Consumer có thể vẫn đang xử lý sự kiện vừa lấy | Chờ worker hoàn thành + flush đích |
| Gọi `System.out.flush()` khi dùng async file logger | Flush sai stream và bỏ qua hàng đợi logging | Dùng cơ chế của async appender và file sink tương ứng |
| Bật `immediateFlush=true` rồi tin mọi `logger.info` là đồng bộ | Producer còn cách consumer một queue | Phân biệt flush sink và drain queue |
| Đặt `neverBlock=true` để giảm latency rồi kỳ vọng zero-loss | Queue đầy có thể làm rơi sự kiện | Xác định rõ yêu cầu mất log, backpressure và capacity |
| Chờ vô hạn khi shutdown | Sink hỏng có thể làm tiến trình không thoát | Chọn thời hạn, giám sát, cảnh báo, đường dự phòng |
| Gọi `LoggerContext.stop()` sau mỗi request | Context bị dừng, request tiếp theo không còn appender hoạt động như trước | Chỉ đóng tại lifecycle shutdown |
| Coi `flush()` là fsync hay remote durable ACK | Flush thường chỉ đẩy dữ liệu tới tầng kế tiếp | Dùng cơ chế đồng bộ bền vững nếu nghiệp vụ yêu cầu |

## 10. Cách thiết kế và vận hành để hạn chế mất log

**Chính sách queue.** Chọn dung lượng, block hoặc discard dựa trên tỷ lệ sinh log và tốc độ sink xử lý. Ví dụ, ứng dụng phát 8.000 sự kiện/giây trong burst còn sink xử lý 6.000 sự kiện/giây, mức tồn tăng khoảng 2.000 sự kiện/giây trong khoảng burst; queue 10.000 phần tử có thể đầy sau khoảng 5 giây nếu bắt đầu rỗng và tải giữ nguyên. Đây chỉ là cách ước tính thô để thử tải, không thay benchmark thực tế.

**Đo các điểm nghẽn.** Quan sát số sự kiện đang chờ, tỷ lệ drop, thời gian producer bị block, tốc độ sink, lỗi I/O, độ trễ flush và thời gian stop. Tên metric phụ thuộc framework và hệ thống giám sát; không giả định mỗi thư viện tự xuất đủ các metric này.

**Phân loại độ quan trọng.** INFO/DEBUG thông thường có thể chịu rủi ro mất mát nhất định để đạt throughput. Log phục vụ kiểm toán bắt buộc có yêu cầu chặt hơn: thiết kế kho lưu trữ/queue bền vững, cơ chế ACK, idempotency và chính sách retry riêng. Async logging file không phải mặc định là hệ thống audit durable.

**Quản lý sink.** Xác định dữ liệu đi vào file, stdout của container, agent thu thập hay endpoint mạng. Với stdout được container thu gom, flush trong JVM mới đưa dữ liệu tới pipe/stream; vẫn có buffer và rủi ro mất mát trên đường thu thập phía ngoài JVM. Với endpoint mạng, “đã gửi” khác “server đã nhận” và “server đã commit”.

**Giữ đúng ranh giới dữ liệu.** Tệp lớn có rollover/rotation riêng; không tự đóng `FileOutputStream` của appender từ bên ngoài hoặc force một file handle khác với giả định rằng nó sẽ xả toàn bộ dữ liệu đang nằm trong queue của logger.

## 11. Kiểm thử flush và shutdown

Bộ tình huống tối thiểu:

1. **Không có tải:** ghi hai sự kiện, chờ barrier/flush phù hợp, xác minh chúng xuất hiện đúng thứ tự trong sink. Ví dụ Java 17 ở trên kiểm tra chính xác điều này.
2. **Tải cao nhưng sink theo kịp:** phát nhiều log đồng thời, dừng producer, shutdown context, đếm số log có ID duy nhất so với số được chấp nhận; đo thời gian drain.
3. **Sink chậm hoặc tạm dừng:** thử queue đầy, xác minh chính sách block/discard và số log mất; thử deadline shutdown.
4. **Shutdown khi queue còn sự kiện:** đảm bảo đóng context thực sự chờ worker trong thời hạn, đồng thời không còn producer mới.
5. **Lỗi I/O:** ổ đĩa đầy, file không ghi được, network bị ngắt; quan sát framework báo lỗi qua status logger, metrics hoặc ErrorManager, và kiểm tra ngoại lệ có tới caller hay không.
6. **Đóng cưỡng bức:** thử ngắt tiến trình không graceful trong môi trường kiểm thử; ghi nhận số log còn thiếu để hiểu giới hạn thiết kế.

Kiểm thử phải phân biệt **số sự kiện producer gọi logger**, **số sự kiện framework thực sự chấp nhận**, và **số sự kiện xuất hiện ở sink**. Nếu cấu hình cho phép drop khi queue đầy, một phép đếm thiếu mà không biết điểm mất sẽ khiến kết luận sai. Khi cần kiểm tra durability, phải có test phù hợp với hợp đồng fsync hoặc xác nhận của hệ thống nhận, không chỉ đọc lại một file ngay sau `flush()`.

## 12. Câu hỏi tự luyện

1. Tại sao `logger.info(...)` đã trả về nhưng dòng log vẫn có thể chưa xuất hiện trong file?
2. Vì sao `queue.isEmpty()` chưa đủ để xác nhận flush hoàn tất?
3. Trong ví dụ `AsyncFlushDemo`, điều gì làm `barrier.get()` có ý nghĩa? Nếu dùng một executor **khác** cho barrier thì điều gì không còn được bảo đảm?
4. `BufferedWriter.flush()` khác `FileChannel.force(true)` ở đâu?
5. Trong Logback, `maxFlushTime=0` và `maxFlushTime=5000` khác nhau như thế nào? Vì sao `discardingThreshold=0` không có nghĩa zero-loss?
6. Trong Log4j 2, `immediateFlush` có buộc thread nghiệp vụ phải chờ async queue rỗng không?
7. Nếu ứng dụng chạy trong container bị SIGKILL trước khi async appender stop xong, những log nào có thể mất?
8. Khi có log kiểm toán bắt buộc bền vững, vì sao cần cơ chế xác nhận vượt ra ngoài async file logger?

**Gợi ý đáp án:** (1) log mới enqueue; (2) consumer có thể đang ghi; (3) cùng executor một luồng bảo đảm thứ tự, khác executor không có barrier cho queue cũ; (4) flush Java buffer không đồng nghĩa force thiết bị; (5) chờ không giới hạn và tối đa 5 giây, vẫn có các nguyên nhân mất log khác; (6) không; (7) những sự kiện chưa bền vững/được hệ thống nhận cam kết; (8) cần durability và acknowledgment rõ ràng.

## 13. Tài liệu chính thức để đối chiếu

- [Java SE 17 — java.util.logging.Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html): hợp đồng `flush()`, `close()`.
- [Java SE 17 — StreamHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/StreamHandler.html): flush bộ đệm bản ghi của handler.
- [Logback — AsyncAppender](https://logback.qos.ch/manual/appenders-async-sift.html): `queueSize`, `discardingThreshold`, `neverBlock`, `maxFlushTime` và shutdown.
- [Apache Log4j 2 — Delegating Appenders / Async](https://logging.apache.org/log4j/2.x/manual/appenders/delegating.html): queue, batch flush, `shutdownTimeout` và queue full.
- [Apache Log4j 2 — Asynchronous loggers](https://logging.apache.org/log4j/2.x/manual/async.html): phân biệt Async Logger và Async Appender, chính sách queue đầy.
- [Apache Log4j 2 — LogManager API](https://logging.apache.org/log4j/2.x/javadoc/log4j-api/org/apache/logging/log4j/LogManager.html): phương thức shutdown của logging context.

