# Consumer ghi log trong logging bất đồng bộ

## 1. Consumer ghi log là gì?

Trong **logging đồng bộ**, luồng đang xử lý nghiệp vụ thường thực hiện một phần hoặc toàn bộ công việc ghi log trước khi chạy tiếp: tạo sự kiện, định dạng thông điệp, gọi appender và ghi tới console, tệp hoặc đích khác. Nếu đầu ra chậm, thời gian chờ có thể ảnh hưởng trực tiếp đến độ trễ của yêu cầu.

Trong **logging bất đồng bộ**, luồng nghiệp vụ (producer) đưa một **log event** vào hàng đợi. Một hoặc nhiều luồng nền (consumer) nhận sự kiện từ hàng đợi và chuyển tới đích ghi log (sink/appender). Consumer là **thành phần tiêu thụ sự kiện log nội bộ**; không nhất thiết là Kafka consumer hay RabbitMQ consumer xử lý thông điệp nghiệp vụ.

```text
Luồng request A ── tạo log event ─┐
Luồng request B ── tạo log event ─┼──► [Hàng đợi log có giới hạn]
Luồng worker  C ── tạo log event ─┘                  │
                                                   ▼
                                      [Log consumer / worker]
                                                   │
                                     Định dạng / serialize
                                                   │
                                                   ▼
                                      [File / stdout / socket]
                                                   │
                                      (có thể qua collector)
                                                   ▼
                                        [Hệ thống tra cứu log]
```

Consumer chịu trách nhiệm **đọc, xử lý và bàn giao log event**; thiết kế cụ thể tùy framework. Tách việc ghi khỏi luồng nghiệp vụ giúp tránh để mỗi request phải chờ đích ghi log khi hệ thống còn đủ khả năng tiêu thụ. Tuy nhiên, hàng đợi vẫn có giới hạn: khi log phát sinh nhanh hơn khả năng ghi trong thời gian dài, hệ thống phải **chờ, loại bỏ hoặc chuyển hướng** sự kiện theo chính sách đã chọn.

Mục tiêu bài học: hiểu luồng xử lý của consumer, thứ tự và độ tin cậy của log, cách ứng xử khi hàng đợi đầy hoặc sink hỏng, cách dừng an toàn và cách quan sát consumer trong ứng dụng Java.

## 2. Consumer thực sự làm những gì?

Một chu trình xử lý thông thường:

1. **Chờ sự kiện** từ hàng đợi. Consumer có thể chờ bằng `BlockingQueue.take()`, cơ chế ring buffer hoặc API riêng của logging framework; không cần liên tục chạy vòng lặp kiểm tra rỗng.
2. **Nhận đúng đối tượng log event** đã được producer chuẩn bị. Các thông tin cần giữ nguyên gồm thời gian xảy ra sự kiện, mức log, logger name, message/argument, tên luồng phát log, ngữ cảnh truy vết (trace/span ID) và thông tin exception nếu có.
3. **Định dạng hoặc mã hóa** sự kiện sang định dạng sink yêu cầu: văn bản, JSON, định dạng nhị phân hay sự kiện truyền qua mạng. Một phần công việc định dạng có thể đã hoàn tất ở producer tùy implementation.
4. **Chuyển tới appender/sink**: ghi ra file, stdout hoặc đích tập trung. Một consumer có thể chuyển log cho appender con; appender đó có thể còn buffer riêng.
5. **Xử lý kết quả và lỗi**: theo dõi thất bại, khả năng retry, mất sự kiện, mức nghẽn hàng đợi; tuyệt đối không mặc định rằng lấy khỏi queue đồng nghĩa ghi xuống đĩa thành công.
6. **Hoàn tất khi shutdown**: ngừng nhận sự kiện mới theo hợp đồng hệ thống, xử lý phần còn trong queue và yêu cầu sink flush/close trong thời hạn phù hợp.

Điểm phân biệt quan trọng:

| Mốc | Điều đã xảy ra | Điều **chưa** được bảo đảm |
| --- | --- | --- |
| Gọi `logger.info(...)` | Producer gọi API log | Sink đã nhận dữ liệu |
| Đưa thành công vào queue | Log nằm trong bộ nhớ hàng đợi | Consumer đã xử lý |
| Consumer lấy khỏi queue | Consumer sở hữu event để xử lý | Ghi file thành công |
| Appender báo đã ghi | Đích ghi đã chấp nhận theo API của nó | Dữ liệu bền vững sau mất điện |
| Flush/close hoàn tất | Buffer tương ứng được đẩy/đóng theo hợp đồng | Mọi collector/backend bên ngoài đã lập chỉ mục |

Vì vậy không nên diễn đạt chung chung “đã log” nếu đang cần phân biệt **enqueue**, **write**, **flush** hay **durable persistence**.

## 3. Dữ liệu cần được chụp trước khi chuyển sang consumer

Ranh giới bất đồng bộ làm thay đổi **luồng thực thi**. Khi producer tạo log event, nó có thể đang xử lý request với `ThreadLocal`/MDC riêng; consumer thường chạy ở một luồng khác. Nếu consumer chỉ đọc `MDC.get(...)` trên chính luồng của mình, nó có thể nhận **ngữ cảnh rỗng hoặc nhầm**.

Thông tin cần được chụp hoặc chuyển an toàn cùng event:

- **Thời điểm phát sinh**: ghi timestamp tại producer, tránh dùng thời điểm consumer ghi ra file làm timestamp sự kiện, vì hàng đợi có thể tạo độ trễ.
- **Mức và nguồn log**: `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`, logger name và class nếu cần.
- **Thông điệp/đối số**: bảo đảm những đối tượng mutable không bị sửa trước khi consumer format. Tùy framework có thể cần chuẩn bị sẵn formatted message hoặc copy dữ liệu cần thiết.
- **Ngữ cảnh yêu cầu**: `trace_id`, `span_id`, request ID, tenant ID đã được cho phép và các trường MDC cần dùng.
- **Exception**: giữ stack trace, exception type và chain nguyên nhân bằng cách sử dụng cơ chế chụp sự kiện an toàn do framework cung cấp.
- **Thread name/caller data**: chụp ở producer nếu muốn biết luồng gọi log; tên luồng consumer **không phải** tên luồng request ban đầu.

Ví dụ sai về mặt ngữ nghĩa:

```java
// Mã minh họa: consumer chạy trên luồng khác producer.
String requestId = MDC.get("requestId"); // Có thể null hoặc không đúng request.
```

Cách đúng về nguyên tắc là capture `requestId` khi producer tạo event, hoặc sử dụng async logging integration hỗ trợ snapshot MDC. Trong chương trình Java thuần ở phần sau, `traceId` là trường bất biến được truyền trực tiếp vào `LogEvent` để minh họa cơ chế này.

**Không coi log context là môi trường thực thi mặc định của luồng consumer.** Nếu consumer tự ghi các log quản trị của mình, chúng phải có ngữ cảnh riêng và không được vô tình mang trace ID của request trước.

## 4. Hàng đợi, thứ tự ghi và số lượng consumer

### Queue có giới hạn và quan hệ producer–consumer

Hàng đợi **bounded** có sức chứa cố định. Nếu nhiều producer tạo log nhanh hơn consumer ghi log, queue sẽ đầy. Giới hạn là cần thiết để tránh log bùng nổ khiến ứng dụng tiêu thụ hết heap.

Một queue FIFO với **một consumer** sẽ lấy event theo thứ tự được enqueue thành công. Nhưng:

- Nhiều producer chạy đồng thời có thể enqueue theo thứ tự khác với timestamp lúc tạo log.
- Thứ tự file log phản ánh thứ tự appender nhận/ghi, không chứng minh thao tác nghiệp vụ xảy ra trước–sau trên tất cả các thread.
- Nhiều consumer hoặc nhiều queue/sink có thể tạo thứ tự đầu ra khác nhau.
- Nếu sink xử lý retry hoặc batch, **thứ tự được ghi/nhận tại backend** có thể khác thứ tự đọc queue.
- Việc một log event đã được consumer lấy ra không cho biết request đã hoàn tất; producer có thể tiếp tục chạy song song.

Muốn dựng quan hệ nhân quả, cần thêm timestamp, span parent/child, request/message ID và mã nguồn; không suy diễn chỉ từ vị trí các dòng log.

### Một consumer hay nhiều consumer?

| Kiểu | Ưu điểm | Rủi ro/điểm cần kiểm tra |
| --- | --- | --- |
| Một queue, một consumer | Đơn giản, FIFO theo dequeue, dễ shutdown | Ghi chậm tạo nghẽn toàn queue |
| Một queue, nhiều consumer | Có thể tăng tốc nếu sink cho phép song song | Có thể mất thứ tự hoàn tất, cạnh tranh I/O |
| Nhiều queue theo sink hoặc partition | Cô lập một số loại tải | Khó xác định thứ tự toàn cục, cần xử lý nhiều trạng thái shutdown |

Không tự tăng số consumer chỉ vì queue dài. Nếu sink thực tế chỉ ghi tuần tự vào một file/stream hoặc bị giới hạn IOPS, thêm thread có thể tăng tranh chấp thay vì tăng throughput.

## 5. Consumer chậm và chính sách khi queue đầy

Gọi `λ` là tốc độ tạo log (sự kiện/giây), `μ` là tốc độ consumer xử lý. Trong khoảng thời gian dài mà `λ > μ`, số sự kiện đang chờ có xu hướng tăng cho tới khi chạm giới hạn. Queue giúp hấp thụ **đỉnh ngắn hạn**; không giải quyết được tình trạng sink chậm kéo dài.

Các chính sách cần hiểu rõ:

| Chính sách | Khi đầy | Hệ quả |
| --- | --- | --- |
| **Chặn producer** (backpressure) | Producer chờ consumer giải phóng chỗ | Giữ sự kiện đã chấp nhận theo đường xử lý bình thường, nhưng tăng latency/giảm throughput của nghiệp vụ |
| **Bỏ event** | Producer/adapter loại bỏ một phần log theo cấu hình | Không chặn nghiệp vụ, nhưng mất quan sát; cần đếm drop |
| **Ghi đồng bộ tạm thời** | Thread phát log thực hiện công việc ghi | Có thể bảo toàn thêm sự kiện nhưng tạo độ trễ đột ngột cho request |
| **Đợi có thời hạn rồi thất bại/drop** | Chờ tối đa một khoảng đã chọn | Giới hạn thời gian chờ nhưng cần kế hoạch xử lý log không được chấp nhận |

Không có chính sách nào “tối ưu” cho mọi hệ thống. Log audit/quy định lưu trữ có yêu cầu riêng, không nên phụ thuộc vào queue log thông thường để đảm bảo tính bền vững. Với log vận hành, có thể chấp nhận giảm DEBUG/INFO khi quá tải nhưng vẫn phải cân nhắc khả năng mất WARN/ERROR do crash, shutdown timeout hoặc sink failure.

**“Không chủ động drop khi queue đầy” không có nghĩa “không bao giờ mất log”.** Dữ liệu còn nằm trong RAM vẫn có thể biến mất khi JVM/process bị kill, JVM crash, máy mất điện hoặc appender không flush kịp.

## 6. Ví dụ Java 17: một consumer ghi log từ hàng đợi bounded

Chương trình độc lập sau mô phỏng cơ chế một producer và một consumer. Producer đưa event vào `ArrayBlockingQueue` dung lượng 2; consumer dùng `take()` để chờ, ghi ra stdout trên luồng `log-consumer`. Khi đóng logger, producer gửi một đối tượng dừng đặc biệt (*poison pill*) **sau tất cả event đã enqueue**; consumer xử lý hết các event trước đó rồi dừng.

Ví dụ cố tình đơn giản để thấy rõ hoạt động của consumer. Đây **không phải** thư viện logging production, không có retry, durable queue hay kiểm soát sink failure đầy đủ.

Lưu thành tệp **`AsyncLogConsumerExample.java`**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class AsyncLogConsumerExample {
    private record LogEvent(String level, String traceId, String message) {
    }

    // Dùng cùng một đối tượng riêng biệt để báo consumer dừng.
    private static final LogEvent STOP = new LogEvent("", "", "");

    private static final class AsyncLogger implements AutoCloseable {
        private final BlockingQueue<LogEvent> queue = new ArrayBlockingQueue<>(2);
        private final Thread consumer = new Thread(this::consume, "log-consumer");
        private boolean stopped;

        AsyncLogger() {
            consumer.start();
        }

        // Đồng bộ log()/close() để STOP không chen trước một lần log đã chấp nhận.
        synchronized void log(String level, String traceId, String message)
                throws InterruptedException {
            if (stopped) {
                throw new IllegalStateException("Logger already closed");
            }
            // Queue đầy -> luồng gọi đợi đến khi consumer lấy bớt event.
            queue.put(new LogEvent(level, traceId, message));
        }

        private void consume() {
            try {
                while (true) {
                    LogEvent event = queue.take(); // Chờ; không busy-spin.
                    if (event == STOP) {           // So sánh đúng sentinel.
                        break;
                    }
                    System.out.printf(
                        "[%s] %s trace_id=%s | %s%n",
                        Thread.currentThread().getName(),
                        event.level(),
                        event.traceId(),
                        event.message()
                    );
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                System.err.println("Consumer interrupted; logs may be lost");
            } finally {
                System.out.flush();
            }
        }

        @Override
        public synchronized void close() throws InterruptedException {
            if (stopped) {
                return;
            }
            stopped = true;
            queue.put(STOP);   // Đứng sau các event đã enqueue thành công.
            consumer.join();   // Đợi consumer đọc STOP rồi kết thúc.
        }
    }

    public static void main(String[] args) throws InterruptedException {
        String traceId = "4bf92f3577b34da6a3ce929d0e0e4736";

        try (AsyncLogger logger = new AsyncLogger()) {
            logger.log("INFO", traceId, "Request accepted");
            logger.log("WARN", traceId, "Downstream latency increased");
            logger.log("ERROR", traceId, "Gateway timeout");
        }
    }
}
```

Chạy bằng JDK 17+:

```bash
javac --release 17 AsyncLogConsumerExample.java
java AsyncLogConsumerExample
```

Kết quả stdout chính xác khi thực hiện bình thường:

```text
[log-consumer] INFO trace_id=4bf92f3577b34da6a3ce929d0e0e4736 | Request accepted
[log-consumer] WARN trace_id=4bf92f3577b34da6a3ce929d0e0e4736 | Downstream latency increased
[log-consumer] ERROR trace_id=4bf92f3577b34da6a3ce929d0e0e4736 | Gateway timeout
```

Vì chỉ có một producer và một consumer với queue FIFO, **thứ tự ba dòng là xác định**; thời điểm consumer chạy ở giữa các lần gọi `log()` có thể thay đổi, nhưng không đổi thứ tự event được enqueue. `close()` không in thêm dòng cho sentinel.

Cách đọc mã:

- `LogEvent` là `record` bất biến, chụp `traceId` khi producer gọi `log()`.
- `queue.put(...)` minh họa **backpressure**: không tự drop khi queue đầy, nhưng producer có thể phải chờ. Nếu luồng producer bị interrupt khi đang đợi, lần gọi có thể không enqueue thành công.
- `take()` chờ sự kiện; consumer không chiếm CPU bằng vòng lặp thăm dò liên tục.
- Sentinel `STOP` là đối tượng riêng, kiểm tra bằng `==` nhằm tránh coi một thông điệp bình thường là lệnh dừng.
- `synchronized` chặn cạnh tranh giữa `log()` và `close()`, nên các lời gọi `log()` hoàn tất trước khi STOP được enqueue. Mẫu này có thể gây tranh chấp khi có nhiều producer và chỉ dùng để dạy cơ chế.
- `join()` giúp chương trình đợi consumer dừng thay vì kết thúc ngay lúc producer ghi dòng cuối.
- `System.out.flush()` yêu cầu đẩy buffer của `PrintStream`; **không tương đương** `fsync`, không bảo đảm collector hoặc ổ đĩa đã lưu bền vững.

**Giới hạn quan trọng của ví dụ:** nếu consumer chết bất ngờ hoặc đích ghi treo, producer/`close()` có thể chờ vô hạn; `close()` bị interrupt khi đang gửi STOP cũng cần một chiến lược dọn dẹp cẩn thận hơn. Hệ thống thật cần timeout shutdown có chính sách rõ ràng, phát hiện worker chết, báo lỗi sink và cơ chế xử lý interruption. Không sao chép nguyên mẫu này để thay Logback/Log4j2 trong production.

## 7. Gắn consumer với logging framework Java

Trong ứng dụng thực tế, nên dùng framework đã xử lý các cạnh tranh và vòng đời cơ bản. Ví dụ **Logback** có `AsyncAppender`: request thread ghi event vào hàng đợi, worker của appender chuyển event tới **appender con** như `FileAppender`. Worker không nhất thiết tự ghi hệ thống tệp; nó có thể gọi một appender có formatter/buffer khác.

Ví dụ cấu hình **`logback.xml`** (cần Logback trong ứng dụng, không dùng riêng với chương trình Java thuần ở trên):

```xml
<configuration>
    <appender name="FILE" class="ch.qos.logback.core.FileAppender">
        <file>logs/app.log</file>
        <append>true</append>
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] trace=%X{trace_id} %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ASYNC" class="ch.qos.logback.classic.AsyncAppender">
        <queueSize>1024</queueSize>
        <discardingThreshold>0</discardingThreshold>
        <neverBlock>false</neverBlock>
        <maxFlushTime>5000</maxFlushTime>
        <appender-ref ref="FILE"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="ASYNC"/>
    </root>
</configuration>
```

Ý nghĩa các lựa chọn trong ví dụ:

- `queueSize`: sức chứa hàng đợi event.
- `discardingThreshold=0`: tắt cơ chế chủ động bỏ sự kiện mức thấp theo ngưỡng dung lượng của `AsyncAppender`; không đồng nghĩa bảo toàn log trước mọi lỗi.
- `neverBlock=false`: khi queue đầy, việc enqueue có thể chặn producer; cân nhắc tác động đến latency.
- `maxFlushTime=5000`: giới hạn thời gian chờ worker hoàn tất khi stop (theo cơ chế của phiên bản Logback đang dùng). Nếu timeout hoặc dừng đột ngột, log còn lại có thể không được ghi.
- `appender-ref`: worker chuyển sự kiện tới `FILE`; quyền ghi và tình trạng đầy đĩa vẫn ảnh hưởng đến tốc độ tiêu thụ.

Mẫu `%X{trace_id}` chỉ có giá trị nếu ứng dụng/instrumentation **thực sự đưa `trace_id` vào MDC của sự kiện**. Với các thư viện OpenTelemetry/Logback khác phiên bản, tên khóa có thể được định nghĩa hoặc ánh xạ khác; cần kiểm tra log xuất ra thực tế. Khi cấu hình JSON logger, nên giữ trace ID thành trường riêng thay vì chỉ nội suy vào chuỗi thông điệp.

**Log4j2** cũng có các cấu hình asynchronous logging (ví dụ async logger hoặc async appender), với thuật toán hàng đợi/ring buffer và chính sách đầy riêng. Không sao chép tên thuộc tính Logback sang Log4j2. Khi chọn cơ chế, phải đọc tài liệu **đúng phiên bản framework** về queue size, mức drop, tình trạng block, location info và shutdown.

## 8. Flush, shutdown và độ tin cậy của consumer

Một quy trình dừng có kiểm soát thường gồm:

1. Ngừng hoặc hoàn tất producer và các request đang phát sinh log.
2. Không cho event mới đi vào queue sau điểm dừng đã xác định.
3. Thông báo consumer kết thúc sau khi xử lý các event đã nhận, hoặc dùng API stop của framework.
4. Đợi consumer drain trong thời gian cho phép; ghi nhận số event còn lại nếu hết hạn.
5. Flush/close sink theo hợp đồng, sau đó đóng collector/exporter nếu thuộc vòng đời ứng dụng.

Cần phân biệt hai trường hợp:

- **Shutdown bình thường:** có cơ hội drain, flush và đóng tài nguyên. Nếu giới hạn thời gian shutdown ngắn hơn thời gian tiêu thụ phần tồn, log có thể bị bỏ.
- **Process kill, crash, hết bộ nhớ hoặc mất điện:** không có cam kết chạy shutdown hook, consumer chưa kịp ghi, buffer trong RAM có thể mất; `finally` cũng không phải bảo đảm trong những tình huống này.

Nếu log là dữ liệu nghiệp vụ phải chứng minh lưu trữ, thiết kế **durable event store/outbox** hoặc cơ chế giao dịch và xác nhận riêng. Queue logging in-memory thường hướng tới khả năng quan sát, không mang mặc định ngữ nghĩa exactly-once.

Không bao giờ giả định “consumer lấy event khỏi queue = event đã được backend lưu”. Khi đích ghi lỗi giữa quá trình ghi và retry, có thể xảy ra **mất** hoặc **trùng** log; khả năng phát hiện tùy sink và định dạng sự kiện.

### Khi sink ghi lỗi

Consumer có thể gặp `IOException`, disk full, permission denied, socket reset, response lỗi, timeout hoặc blocked I/O. Phương án xử lý phụ thuộc tính chất sink:

- Thông báo lỗi bằng kênh không phụ thuộc cùng appender đang hỏng (ví dụ status manager, metric, stderr thận trọng).
- Dùng retry có giới hạn/backoff nếu phù hợp, nhưng kiểm soát bộ nhớ, duplicate và thứ tự.
- Phân biệt lỗi tạm thời với lỗi vĩnh viễn, theo dõi thời gian từ event đến write.
- Có chính sách khi sink không phục hồi: block producer, drop có đếm, degrade hoặc dừng dịch vụ nếu hệ thống yêu cầu.
- Tránh ghi lỗi của consumer **vào chính queue đang hỏng** theo cách tạo vòng lặp log vô hạn.

## 9. Thu thập trace/MDC mà không làm sai ngữ cảnh

Hệ thống nhiều request chạy song song có thể dùng MDC để ghi `trace_id`, `span_id`, `request_id`. Consumer thường là worker chung cho nhiều request, vì vậy phải gắn các trường này **theo từng event**, không lấy MDC hiện tại của thread worker rồi áp cho tất cả.

Một flow đúng về mặt dữ liệu:

```text
Request A có trace_id=A
    -> producer chụp event {message, trace_id=A, ...}
    -> queue
    -> consumer ghi event A, trace_id=A

Request B có trace_id=B
    -> producer chụp event {message, trace_id=B, ...}
    -> queue
    -> consumer ghi event B, trace_id=B
```

Điều cần kiểm tra ở Java:

- Framework async logging có **capture MDC, thread name và exception** ở thời điểm enqueue không?
- Code của ứng dụng có clear/restore MDC khi kết thúc request hoặc sau task trong thread pool không?
- Instrumentation có truyền trace context đúng qua HTTP, gRPC, executor và message headers không?
- Log trong sink có đồng thời các trường `timestamp`, `service`, `level`, `trace_id`, `span_id` để truy vấn không?
- Consumer có tránh lưu token, mật khẩu, cookie, Authorization header hoặc thông tin cá nhân chỉ nhằm “dễ debug” không?

Việc có một `trace_id` chung cho các dòng log giúp **correlate**; muốn dựng quan hệ giữa các thao tác phải xem thêm span và quan hệ parent/links trong tracing backend.

## 10. Đo sức khỏe consumer và tinh chỉnh dung lượng

Những tín hiệu hữu ích:

| Chỉ số | Ý nghĩa |
| --- | --- |
| `queue_depth` / `queue_capacity` | Hàng đợi đang đầy đến mức nào |
| `enqueued_total`, `written_total` | Sự kiện đã nhận và sự kiện đã xử lý thành công theo định nghĩa của adapter |
| `dropped_total` | Sự kiện bị loại (nên phân loại theo lý do/level nếu cardinality chấp nhận được) |
| `enqueue_block_duration` | Thời gian producer phải chờ để gửi log |
| `consumer_lag` | Khoảng thời gian từ timestamp event đến lúc consumer xử lý |
| `sink_write_duration` | Độ trễ của đích ghi |
| `sink_error_total` | Lỗi ghi theo loại sink/exception |
| `shutdown_pending` | Event còn tồn khi stop hết thời hạn |
| `consumer_alive` / worker state | Consumer có còn chạy không, có tự dừng vì lỗi hay không |

Những chỉ số này là **mô hình quan sát đề xuất**; tên và khả năng lấy số liệu thật phụ thuộc framework/collector. Không đưa `trace_id` hoặc `request_id` thành nhãn metric vì chúng có số lượng giá trị khác nhau rất lớn.

Cách điều chỉnh có căn cứ:

1. Đo tốc độ log thông thường, đỉnh ngắn hạn, mức sinh log theo level và độ trễ sink.
2. Chọn queue size đủ hấp thụ đỉnh dự kiến theo ngân sách bộ nhớ, tránh chọn thật lớn chỉ để che tình trạng sink chậm.
3. Quyết định trước hành vi đầy queue theo mức độ cần thiết của log: blocking, drop hay cơ chế khác.
4. Kiểm tra latency nghiệp vụ khi queue đầy; ghi nhận sự kiện bị mất/trì hoãn.
5. Load test kịch bản burst, disk gần đầy, sink ngừng đáp ứng, restart và shutdown dưới tải.

Một queue lớn có thể trì hoãn lúc chạm trần nhưng cũng khiến **lượng log chưa ghi tăng lên**, tiêu tốn heap và kéo dài thời gian drain khi shutdown.

## 11. Những lỗi triển khai hay gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Request chậm đột ngột dù bật async logging | Queue đầy và producer bị block; sink quá chậm | Đo enqueue wait, queue depth, tốc độ sink; xem lại chính sách overload |
| Mất DEBUG/INFO dưới tải | Framework chủ động discard khi còn ít chỗ | Kiểm tra discard policy, đếm log bị loại, điều chỉnh theo yêu cầu |
| Mất log cuối trước khi process dừng | Không stop/drain appender hoặc timeout quá ngắn | Quản lý vòng đời logging, shutdown budget và readback đầu ra |
| Log không có trace ID hoặc sai ID | Đọc MDC ở consumer thay vì capture ở producer; mất context | Snapshot context trong event, xác minh instrumentation |
| Log xuất hiện lệch thứ tự timestamp | Nhiều producer, buffering, retry hoặc nhiều consumer | Phân biệt enqueue order, event time và backend ingestion |
| CPU cao do consumer | Busy-spin, formatter quá nặng hoặc serialization không tối ưu | Dùng cơ chế chờ phù hợp, đo CPU/allocations, profile formatter |
| Log lặp lại sau lỗi mạng | Sink/adapter retry khi chưa biết ghi trước đó đã thành công chưa | Dùng event ID/dedup nếu backend hỗ trợ; làm rõ semantics |
| Consumer chết mà ứng dụng vẫn tiếp tục | Exception bị bỏ qua hoặc không có kiểm tra worker | Quan sát worker liveness, status lỗi, cơ chế phục hồi có giới hạn |
| Heap tăng liên tục | Unbounded queue hoặc giữ quá nhiều log event lớn | Dùng bounded queue, giới hạn kích thước event và logging volume |
| Đệ quy khi báo lỗi logging | Error handler lại gửi log qua cùng appender hỏng | Chuyển cảnh báo sang kênh độc lập, tránh self-logging loop |

## 12. Kiểm thử consumer: cần chứng minh điều gì?

- **FIFO trong phạm vi được bảo đảm:** với một producer và một consumer, enqueue 1–2–3 thì thứ tự write của event phải là 1–2–3. Với nhiều producer, không khẳng định thứ tự toàn cục từ timestamp.
- **Queue đầy:** cố ý làm sink chậm và phát log nhiều hơn dung lượng. Xác nhận producer block/drop đúng cấu hình; đo cả latency nghiệp vụ.
- **Context snapshot:** hai request có trace ID khác nhau; dù consumer dùng chung thread, từng dòng log vẫn mang ID của producer tương ứng.
- **Sink hỏng:** giả lập write exception/timeout/disk full, xác nhận alert, drop/retry và worker state đúng hợp đồng.
- **Shutdown dưới tải:** enqueue một tập event có ID rồi gọi stop đúng cách; so sánh số sự kiện được chấp nhận với số event thực sự ghi sau drain. Thử cả shutdown timeout.
- **Khởi động/dừng lặp:** không để thread sống sót ngoài vòng đời ứng dụng, không tạo nhiều consumer trùng, không kẹt khi appender chưa start hoặc đã stop.
- **Khả năng tìm kiếm:** kiểm tra log JSON có timestamp, level, service, trace ID/span ID đúng trường; exception được giữ đủ thông tin.

Tránh viết kiểm thử chỉ nhìn thấy “có dòng log” rồi kết luận consumer an toàn. Cần kiểm tra cả khi hệ thống áp lực, lỗi và kết thúc.

## 13. Nguyên tắc thiết kế để ghi nhớ

Consumer ghi log là **bộ phận chuyển sự kiện đã được tạo sang đích lưu/truy xuất**. Producer chịu trách nhiệm tạo log đúng ngữ cảnh; queue đệm chênh lệch tốc độ; consumer thực hiện công việc ghi và chịu tác động của sink. Những quyết định quan trọng nhất là:

- Chọn **bounded queue** và chính sách rõ ràng khi đầy; async không xóa được giới hạn I/O.
- Giữ thông tin sự kiện tại thời điểm phát log, đặc biệt timestamp, thread name, exception và trace/MDC.
- Không suy ra thứ tự nghiệp vụ hoặc độ bền dữ liệu chỉ từ thứ tự dequeue và thông báo enqueue thành công.
- Quan sát queue depth, lag, lỗi ghi, drop và thời gian block để biết async logging có còn giúp giảm độ trễ hay không.
- Chủ động stop, drain và flush theo khả năng của framework; hiểu log trong RAM có thể mất nếu process chết đột ngột.
- Dùng Logback/Log4j2 đúng phiên bản và xác minh cấu hình thực tế, thay vì tự viết worker logging không có cơ chế xử lý lỗi.

**Ghi nhớ:** consumer giúp chuyển chi phí ghi log ra khỏi luồng nghiệp vụ **trong điều kiện còn đủ năng lực xử lý**. Độ tin cậy của toàn bộ đường log vẫn phụ thuộc vào queue, chính sách quá tải, sink, cơ chế shutdown và khả năng quan sát lỗi.