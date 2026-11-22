# Shutdown async logger: xả hàng đợi và đóng logging an toàn trong Java

**Bối cảnh:** Một async logger hoặc async appender cho phép thread nghiệp vụ đưa sự kiện log vào bộ đệm/hàng đợi, còn thread ghi log xử lý sau. Vì vậy, việc gọi `logger.info(...)` thành công **chưa đồng nghĩa** dòng đó đã được ghi xuống file, chuyển qua mạng hoặc lưu bền vững. Khi ứng dụng shutdown, nếu dừng writer hoặc JVM quá sớm, các sự kiện còn chờ có thể mất.

Bài này giải thích trình tự đóng đúng, rủi ro về thời gian chờ, khác biệt giữa Logback và Log4j 2, cùng ví dụ Java 17 chạy độc lập mô phỏng shutdown có xả queue.

## 1. Mô hình hoạt động và điểm có thể mất log

Một pipeline thường có dạng:

~~~text
Thread nghiệp vụ
  -> tạo LogEvent
  -> enqueue (có thể chặn hoặc từ chối)
  -> queue / ring buffer
  -> logging worker
  -> encoder và appender
  -> file / stdout / socket
  -> collector hoặc hệ thống lưu trữ
~~~

Có ít nhất bốn thời điểm khác nhau:

1. **Đã nhận (accepted/enqueued):** sự kiện vào được hàng đợi async. Dữ liệu có thể vẫn chỉ nằm trong bộ nhớ JVM.
2. **Đã xử lý (drained/dispatched):** worker đã lấy sự kiện và chuyển đến appender đích. Hàng đợi trống không chứng minh appender đích đã hoàn thành mọi I/O.
3. **Đã flush/close:** bộ đệm của writer/appender được đẩy sang tầng I/O bên dưới và tài nguyên được đóng theo hợp đồng của thư viện.
4. **Đã lưu bền vững hoặc chuyển tới nơi nhận:** đây là cam kết mạnh hơn; `Writer.flush()` thường không tương đương `fsync`, và ghi ra stdout/file cũng không chứng minh log collector đã ingest thành công.

**Shutdown an toàn phải được hiểu theo mức bảo đảm cần đạt.** Với log chẩn đoán, chờ xả queue có thể đủ. Với audit hay sự kiện nghiệp vụ không được phép thất lạc, log bất đồng bộ thông thường không phải cơ chế giao nhận bền vững; cân nhắc lưu giao dịch, outbox, hàng đợi có độ bền và xác nhận từ đích.

Các nguồn mất log điển hình gồm: producer vẫn log khi logger đã dừng; queue quá tải và có chính sách discard; hết thời gian chờ drain; appender ghi file/mạng báo lỗi; shutdown hook chạy sai thứ tự; JVM bị `kill -9`/crash hoặc bị container cưỡng bức kết thúc.

## 2. Trình tự graceful shutdown

Đừng bắt đầu bằng việc đóng appender khi request, job hoặc worker nghiệp vụ vẫn đang tạo log. Trình tự tham khảo:

1. **Quiesce nguồn công việc:** ngừng nhận request/job mới, dừng scheduler/consumer, đóng đường tạo task mới. Ghi nhận rằng ứng dụng đang bắt đầu dừng.
2. **Cho công việc đã nhận hoàn tất trong ngân sách thời gian:** chờ các request và thread pool nghiệp vụ kết thúc hoặc hủy có kiểm soát. Những thành phần này vẫn có thể log khi cleanup.
3. **Phát sự kiện log cuối cùng có ý nghĩa:** ví dụ `event=application_stopping` hoặc `event=worker_pool_stopped` sau khi đã chờ tác vụ. Nếu nhiều thành phần dừng song song, phải xác định rõ component nào vẫn được phép log.
4. **Dừng logging context/async appender:** từ chối thêm log mới, cho worker ghi xử lý backlog, flush và đóng appender đích theo cơ chế chính thức của framework. Chỉ đóng appender đích **sau khi** dữ liệu async đã được chuyển đến nó.
5. **Kiểm tra kết quả trong deadline:** quan sát timeout, queue còn lại, số log bị drop và lỗi I/O. Nếu không drain được, ghi nhận sự cố qua kênh chẩn đoán còn sống (ví dụ stderr của tiến trình) hoặc bộ giám sát ngoài; đừng ngầm coi là thành công.

~~~text
RUNNING -> STOP_ACCEPTING_WORK -> DRAIN_BUSINESS_TASKS
        -> FINAL_LOG_EVENT -> DRAIN_LOG_QUEUE -> FLUSH/CLOSE -> TERMINATED
~~~

Không có lời gọi `flush()` chung nào đảm bảo mọi implementation tuân theo cùng một hợp đồng. Một appender có thể không hỗ trợ flush tường minh, hoặc đằng sau nó còn một async sender khác. Cần dừng **toàn bộ chuỗi xử lý** theo thứ tự đúng và đọc tài liệu đúng phiên bản backend đang dùng.

### Vì sao chỉ gọi `shutdown()` hoặc `flush()` chưa đủ?

- `ExecutorService.shutdown()` từ chối task mới nhưng **không chờ** task cũ chạy xong; nếu tự xây một logger dựa trên executor, phải đồng bộ thêm bằng `awaitTermination()` hoặc `Future.get()`.
- `shutdownNow()` cố gắng interrupt các tác vụ và loại bỏ công việc chưa chạy; dùng bừa cho writer có thể đánh mất log đang chờ.
- `Writer.flush()` chỉ thao tác trên buffer của writer mà thread hiện tại truy cập; nếu event còn ở async queue thì flush writer **trước khi drain** không thể ghi chúng.
- `Thread.sleep(1000)` không là hàng rào đồng bộ: backlog có thể lớn, I/O có thể chậm, và ứng dụng vẫn nhận thêm event trong khi ngủ.
- Một dòng `"shutdown complete"` xuất hiện trong log không tự nó chứng minh tất cả event trước hoặc sau đó đã được lưu tại hệ thống thu thập từ xa.

## 3. Thiết kế thời gian chờ: an toàn và khả năng thoát

Mỗi môi trường có một deadline dừng tiến trình (ví dụ do orchestrator cấp). Hãy phân bổ thời gian cho việc dừng request, các job và drain log, đồng thời để khoảng dự phòng. **Không đặt timeout dài hơn toàn bộ ngân sách shutdown rồi kỳ vọng logger luôn xả xong.**

| Lựa chọn | Tác dụng | Đánh đổi |
| --- | --- | --- |
| Chờ drain không giới hạn | Có cơ hội xử lý hết backlog nếu đích còn hoạt động | Có thể treo mãi khi I/O bị kẹt; vẫn không chống được kill/crash |
| Chờ tối đa N mili giây | Giới hạn thời gian đóng logger | Có thể còn event chưa ghi khi deadline hết |
| Drop khi queue đầy | Giảm chặn thread nghiệp vụ | Có thể mất log **trước cả khi shutdown** |
| Block khi queue đầy | Tạo backpressure, giảm mất do overflow | Có thể làm chậm request hoặc kẹt luồng khi đích không tiến triển |
| Ghi đồng bộ các log đặc biệt | Giảm một tầng queue cho sự kiện cần ưu tiên | Tăng độ trễ; vẫn cần xử lý lỗi và độ bền của đích |

Ví dụ: nếu tổng thời gian tắt dịch vụ tối đa là 30 giây, không nên để job nghiệp vụ dùng hết 30 giây rồi mới yêu cầu logger chờ thêm 30 giây. Thời gian thực tế phụ thuộc tải, tốc độ đích và quy định vận hành; con số cấu hình trong ví dụ phía sau chỉ có tính minh họa.

## 4. Logback: đóng `AsyncAppender` thông qua `LoggerContext`

Với **Logback Classic**, `AsyncAppender` giữ sự kiện trong `BlockingQueue` và có worker chuyển sự kiện đến một appender đích. Để dừng sạch, cần stop `LoggerContext` (hoặc cho container/framework quản lý lifecycle của context), thay vì chỉ ngắt worker.

Ví dụ cấu hình `logback.xml` hoàn chỉnh, tập trung vào shutdown:

~~~xml
<configuration>
    <appender name="FILE" class="ch.qos.logback.core.FileAppender">
        <file>app.log</file>
        <append>true</append>
        <encoder>
            <pattern>%d{ISO8601} [%thread] %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ASYNC" class="ch.qos.logback.classic.AsyncAppender">
        <queueSize>1024</queueSize>
        <discardingThreshold>0</discardingThreshold>
        <neverBlock>false</neverBlock>
        <maxFlushTime>10000</maxFlushTime>
        <appender-ref ref="FILE"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="ASYNC"/>
    </root>
</configuration>
~~~

Ý nghĩa những thuộc tính liên quan:

- `queueSize=1024`: số sự kiện có thể chờ trong queue; đây không phải lời hứa log sẽ được lưu.
- `discardingThreshold=0`: tắt cơ chế tự loại log mức thấp theo ngưỡng còn chỗ trong queue. Mặc định `AsyncAppender` có thể bỏ TRACE/DEBUG/INFO khi queue gần đầy, vì vậy không thể lấy "cấu hình async" làm bằng chứng không mất log.
- `neverBlock=false`: khi queue đầy, producer có thể bị chặn thay vì tự động bỏ event do tùy chọn `neverBlock`. Việc chặn có thể ảnh hưởng mạnh đến latency.
- `maxFlushTime=10000`: khi stop, Logback chờ worker xả queue tối đa khoảng 10 giây; các event chưa xử lý sau giới hạn có thể bị bỏ. **Giá trị 0** yêu cầu chờ đến khi worker xử lý hết, nhưng có nguy cơ làm shutdown kéo dài không giới hạn nếu đích chậm/kẹt.

Trong ứng dụng Java độc lập có quyền quản lý lifecycle của Logback, thao tác stop có thể đặt ở **giai đoạn cuối** của quá trình dừng:

~~~java
import ch.qos.logback.classic.LoggerContext;
import org.slf4j.LoggerFactory;

// Đoạn minh họa đặt trong lifecycle manager của ứng dụng có Logback.
// Chỉ gọi sau khi đã ngừng những producer/worker còn tạo log.
LoggerContext context = (LoggerContext) LoggerFactory.getILoggerFactory();
context.stop();
~~~

Đây là **snippet phụ thuộc Logback/SLF4J**, không phải chương trình Java chuẩn chạy độc lập. Không gọi `context.stop()` sau mỗi request/job hoặc trong thư viện dùng chung; nó dừng logging của cả context. Với Spring Boot hoặc application server quản lý context, nên dựa vào lifecycle của hệ thống và sắp xếp việc dừng producer phù hợp, tránh stop trùng hoặc quá sớm.

**Giới hạn quan trọng:** `maxFlushTime=0` chỉ nói về việc chờ queue trong điều kiện shutdown bình thường. Nó không chống được việc JVM bị kill, I/O lỗi hoặc log shipper mất dữ liệu.

## 5. Log4j 2: phân biệt `AsyncAppender` và `AsyncLogger`

Log4j 2 cung cấp hai cơ chế khác nhau:

- **`AsyncAppender`:** đóng vai trò hàng đợi đứng trước appender khác. Thời gian dừng của component này được điều khiển bằng thuộc tính `shutdownTimeout` (mili giây); trong tài liệu Log4j 2, `0` nghĩa là đợi đến khi queue được xả.
- **`AsyncLogger`:** dùng cơ chế async logging dựa trên Disruptor/ring buffer và gắn với lifecycle của `LoggerContext`. Đừng mặc định cấu hình timeout của `AsyncAppender` sẽ điều khiển mọi `AsyncLogger`.
  
Ví dụ `log4j2.xml` cho **AsyncAppender** (không phải cấu hình toàn bộ logger thành `AsyncLogger`):

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <File name="FILE" fileName="app.log">
            <PatternLayout pattern="%d{ISO8601} [%t] %-5level %logger - %msg%n"/>
        </File>
        <Async name="ASYNC" bufferSize="1024"
               blocking="true" shutdownTimeout="10000">
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

Appender đích được khai báo trước `Async` để Log4j 2 có thể xử lý thứ tự lifecycle phù hợp. Với cấu hình trên, queue đầy có thể làm producer chờ; khi stop, `shutdownTimeout=10000` đặt giới hạn chờ worker, không phải cam kết bền vững của file hay hệ thống thu log.

**Đóng LoggerContext đúng lifecycle:** Log4j 2 thường quản lý shutdown bằng hook hoặc lifecycle của container. Với ứng dụng Java độc lập cần dừng Log4j 2 theo chủ đích, API mức cao là:

~~~java
// Dùng khi ứng dụng chủ động sở hữu lifecycle của Log4j 2:
org.apache.logging.log4j.LogManager.shutdown();
~~~

Không gọi lệnh này nếu các component vẫn tiếp tục log. Trong web container/framework, ưu tiên cơ chế stop do container quản lý; tránh tạo nhiều shutdown hook độc lập không kiểm soát thứ tự. Nếu hệ thống dùng `AsyncLogger` thực sự, kiểm tra phần cấu hình async logger, queue-full policy và quy tắc stop theo đúng phiên bản Log4j 2 đang dùng.

## 6. Ví dụ Java 17 chạy độc lập: stop nhận event, drain FIFO, flush và close

Ví dụ sau tự xây một **bộ ghi file async tối giản để học cơ chế shutdown**, chỉ dùng JDK. Đây **không phải** giải pháp logging production thay cho Logback/Log4j 2: hàng đợi của nó không giới hạn dung lượng, chưa hỗ trợ log rotation, batch, metrics hay timeout shutdown.

Lưu vào file **`AsyncLoggerShutdownDemo.java`**:

~~~java
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.LinkedBlockingQueue;

public class AsyncLoggerShutdownDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("async-logger-demo-", ".log");
        try {
            try (AsyncFileLogger logger = new AsyncFileLogger(file)) {
                logger.log("event=start jobId=A");
                logger.log("event=complete jobId=A");
                logger.log("event=shutdown");
            }
            System.out.println("saved=" + Files.readAllLines(
                    file, StandardCharsets.UTF_8).size());
        } finally {
            Files.deleteIfExists(file);
        }
    }

    private static final class AsyncFileLogger implements AutoCloseable {
        private record Entry(String text) {}
        private static final Entry STOP = new Entry(null);

        // Queue không giới hạn: chỉ dùng cho ví dụ nhỏ này.
        private final BlockingQueue<Entry> queue = new LinkedBlockingQueue<>();
        private final ExecutorService executor = Executors.newSingleThreadExecutor(
                task -> new Thread(task, "async-file-writer"));
        private final Future<?> writerFinished;
        private boolean stopping;

        AsyncFileLogger(Path file) {
            writerFinished = executor.submit(() -> {
                try (BufferedWriter out = Files.newBufferedWriter(
                        file, StandardCharsets.UTF_8)) {
                    while (true) {
                        Entry next = queue.take();
                        if (next == STOP) {
                            break;
                        }
                        out.write(next.text());
                        out.newLine();
                    }
                    out.flush();
                } catch (IOException e) {
                    throw new UncheckedIOException(e);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException("writer interrupted", e);
                }
            });
        }

        public synchronized void log(String message) {
            if (stopping) {
                throw new IllegalStateException("logger is stopping");
            }
            queue.add(new Entry(message));
        }

        @Override
        public void close() throws InterruptedException, ExecutionException {
            synchronized (this) {
                if (!stopping) {
                    stopping = true;
                    queue.add(STOP);
                }
            }
            try {
                writerFinished.get();
            } finally {
                executor.shutdown();
            }
        }
    }
}
~~~

Chạy bằng Java 17 trở lên:

~~~bash
javac AsyncLoggerShutdownDemo.java
java AsyncLoggerShutdownDemo
~~~

**Stdout xác định** khi chạy thành công (đã biên dịch và kiểm chứng với JDK):

~~~text
saved=3
~~~

Chương trình tạo file log tạm, ghi ba event, chờ worker hoàn thành, đọc số dòng rồi xóa file tạm. Trật tự thực thi giữa thread main và writer không được giả định; **thứ tự các message đã enqueue** vẫn được giữ vì queue FIFO có đúng một consumer.

Giải thích các hàng rào shutdown:

1. `log(...)` và phần đặt `stopping=true` trong `close()` được bảo vệ bởi cùng monitor. Một event đã được `log(...)` chấp nhận phải được enqueue **trước** marker `STOP`. Những lần `log(...)` đến sau bị từ chối.
2. `STOP` là một đối tượng `Entry` riêng, được so sánh bằng danh tính `==`; một message thông thường không thể vô tình trùng marker. Writer lấy các entry theo FIFO rồi mới thấy `STOP`.
3. Worker ghi bằng `BufferedWriter`; ra khỏi vòng lặp mới `flush()`, và `try-with-resources` đóng writer. Đóng đúng thứ tự giúp xử lý những event đã chấp nhận khi I/O thành công.
4. `writerFinished.get()` chờ tác vụ writer kết thúc và làm lộ lỗi dưới dạng `ExecutionException` nếu task ném exception (ví dụ lỗi I/O được bọc thành `UncheckedIOException`). Vì vậy câu lệnh in `saved=3` chỉ chạy sau khi writer đã thoát thành công.
5. `executor.shutdown()` được gọi khi không còn cần task mới. Đây là executor riêng cho ví dụ, không phải lời khuyên tắt pool nghiệp vụ trước khi chúng hoàn tất.

**Giới hạn có chủ ý:** `LinkedBlockingQueue<>` không giới hạn có thể chiếm quá nhiều bộ nhớ nếu log đến nhanh hơn writer xử lý; bản production cần queue hữu hạn, chính sách backpressure/drop, health check, phát hiện writer chết và timeout đóng. `Future.get()` không giới hạn thời gian có thể chờ mãi nếu đích I/O không tiến triển. Nếu writer gặp lỗi, dữ liệu còn trong queue chưa được lưu; exception phải được báo động, không được đánh dấu thành công.

Ví dụ sử dụng file tạm và xóa sau khi đếm số dòng. Nó chỉ chứng minh code có thể xả những event đã nhận trong điều kiện thử nghiệm, **không chứng minh fsync hoặc chuyển log đến dịch vụ bên ngoài**.

## 7. Khi chạy trong JVM, server và container

- **Chạy từ `main`:** chương trình nên quản lý vòng đời của producer và logger rõ ràng; đóng logger sau khi công việc kết thúc. Đối với framework có shutdown hook sẵn, tránh gọi stop lặp lại không cần thiết.
- **Spring Boot / application server:** dừng nhận lưu lượng, đợi hoặc hủy các job trong phạm vi cho phép, rồi để application context quản lý việc đóng logging. Đừng stop logging khi bean khác còn chạy callback cleanup có log.
- **Shutdown hook:** các hook JVM có thể chạy đồng thời, không bảo đảm tuần tự giữa những hook độc lập. Đặt một cơ chế điều phối lifecycle nhất quán hoặc để framework quản lý; không giả định hook đóng logger luôn chạy cuối.
- **SIGTERM và giới hạn của container:** shutdown bình thường có thể kích hoạt hook và cho thời gian drain; khi hết grace period, container có thể buộc dừng. Điều chỉnh thời gian xử lý nghiệp vụ, thời gian xả log và thời gian dự phòng để phù hợp.
- **Crash, `Runtime.halt(...)`, SIGKILL:** không thể trông cậy vào shutdown hook, flush hoặc finally. Nếu cần tính bền vững đặc biệt, phải thiết kế một đường ghi/đồng bộ tin cậy hơn.

Với stdout trong container, cần phân biệt **logger đã flush sang stdout** với **runtime/agent thu log đã chuyển đến backend**. Cả hai có thể có bộ đệm hoặc giới hạn riêng. Thử nghiệm hệ thống nên quan sát tới đích cuối thay vì chỉ kiểm tra số message trong bộ nhớ.

## 8. Những lỗi shutdown thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Đóng logger trước khi dừng task/request | Log cleanup đến sau có thể bị bỏ | Dừng nguồn phát trước, logger sau |
| Gọi `System.exit(...)` ngay sau log cuối | Dữ liệu còn trong queue có thể mất | Dùng lifecycle graceful, chờ drain với deadline |
| Chỉ kiểm tra `queue.size()==0` | Event có thể đang được worker xử lý hoặc nằm ở buffer sau queue | Chờ lifecycle stop/worker termination và close appender |
| Chỉ `sleep` một khoảng cố định | Không có bảo đảm worker đã hoàn thành | Dùng wait/join/future hoặc API stop của backend |
| Dùng `shutdownNow()` cho writer | Task/log chưa xử lý bị hủy | Chọn orderly stop và chính sách timeout rõ ràng |
| Đặt timeout 0 ở mọi môi trường | Có nguy cơ shutdown kẹt mãi khi đích I/O treo | Chọn deadline hợp lý với quy định vận hành |
| Tin rằng `neverBlock=false` bảo đảm không mất log | Vẫn có thể mất do discard threshold, timeout, lỗi I/O, crash | Xem toàn bộ chính sách queue và đích |
| Vừa stop framework thủ công vừa để framework đang vận hành | Log từ component còn sống có thể không còn đầu ra | Chỉ một chủ sở hữu lifecycle |
| Cho rằng ghi ra file tức là đã ingest vào hệ thống tập trung | Pipeline sau file/stdout còn có thể thất bại | Giám sát log shipper và đích cuối |

Không nên ghi một log thông báo lỗi shutdown thông qua chính logger **sau khi nó đã dừng**. Nếu không còn kênh log thông thường, dùng kênh chẩn đoán riêng còn hoạt động và giám sát ở bên ngoài tiến trình.

## 9. Cách kiểm thử và theo dõi

### Kiểm thử chức năng

1. **Drain đủ:** phát N log có mã tăng dần, đóng logger ngay, xác minh file/collector nhận đủ N record và writer đã kết thúc. Chạy nhiều lần để phát hiện race.
2. **Nhiều producer đua với close:** cho nhiều thread ghi đồng thời rồi đóng logger. Xác minh mọi lần `log()` được xác nhận là accepted đều đứng trước marker stop và có kết quả rõ ràng; những lần sau stop bị từ chối.
3. **Backlog lớn:** làm chậm appender đích để tạo queue còn tồn, shutdown với hai cấu hình timeout khác nhau; xác minh đo được thời gian chờ, số log còn lại/bị bỏ và phản ứng cảnh báo.
4. **I/O lỗi:** mô phỏng ổ đĩa đầy hoặc đích mạng không sẵn sàng; đảm bảo ứng dụng nhận biết lỗi từ worker và không báo "đã lưu hết" sai sự thật.
5. **Container shutdown:** chạy trong môi trường giống production, gửi SIGTERM trong lúc có tải, xác minh thứ tự tắt producer/logger. Thử thêm cưỡng bức kết thúc để biết mức mất log thực tế.

### Chỉ số hữu ích

Theo dõi **queue depth / ring-buffer utilization**, sự kiện bị discard/drop, thời gian producer bị block, tốc độ enqueue/dequeue, thời gian drain khi shutdown, lỗi appender, số task còn chạy và độ trễ ship log. Chỉ số chính xác phụ thuộc backend. Trong nhiều hệ thống, cần quan sát đồng thời log chưa nhận vào queue, log đã ghi ở appender và log đã đến nơi thu thập.

Gợi ý sự kiện vận hành (giá trị minh họa):

~~~text
event=shutdown_started activeJobs=12 logQueueDepth=450
event=business_tasks_stopped activeJobs=0
event=log_drain_completed durationMs=281 remaining=0 dropped=0
~~~

Dòng cuối phải phát từ cơ chế đo được kết quả shutdown **hoặc kênh giám sát còn sống**; nếu phát qua logger vừa đóng thì có thể không xuất hiện. Đừng tự đặt `remaining=0` khi chưa có bằng chứng.

## 10. Ghi nhớ để vận dụng

Một lần gọi log thành công có thể chỉ mới đưa dữ liệu vào bộ nhớ. Khi shutdown async logger, hãy **dừng nguồn phát, chờ công việc nghiệp vụ kết thúc, phát log cuối, yêu cầu backend xả queue, flush/đóng appender và xác minh trạng thái trong thời gian cho phép**. Phân biệt `AsyncAppender` với `AsyncLogger`, và hiểu chính sách timeout/overflow của backend thực tế. Không dùng shutdown hook hay `sleep` làm bằng chứng bền vững; lỗi I/O và kết thúc cưỡng bức luôn cần được tính đến trong yêu cầu độ tin cậy.

### Tài liệu tham khảo

- Logback — [AsyncAppender và `maxFlushTime`](https://logback.qos.ch/manual/appenders-async-sift.html).
- Apache Log4j 2 — [Async Appender, `shutdownTimeout` và vòng đời appender](https://logging.apache.org/log4j/2.x/manual/appenders/delegating.html).
- Apache Log4j 2 — [Asynchronous loggers](https://logging.apache.org/log4j/2.x/manual/async.html) và [FAQ về shutdown](https://logging.apache.org/log4j/2.x/faq.html).
- Java 17 — [`ExecutorService` và `ThreadPoolExecutor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html).