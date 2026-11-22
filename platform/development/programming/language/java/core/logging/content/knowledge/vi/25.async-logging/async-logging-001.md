# Async logging là gì? Cơ chế, lợi ích và đánh đổi trong Java

## Mục tiêu bài học

**Async logging (ghi log bất đồng bộ)** là cách tách bước **ứng dụng tạo sự kiện log** khỏi bước **ghi sự kiện đó đến đích** như console, file hoặc hệ thống thu thập log. Thay vì buộc luồng xử lý nghiệp vụ chờ hầu hết công việc ghi log, hệ thống chuyển sự kiện vào vùng đệm/hàng đợi và để một hoặc nhiều luồng chuyên trách xử lý sau.

Sau bài này, bạn sẽ hiểu: đường đi của một log event, sự khác nhau giữa synchronous và asynchronous logging, vì sao async có thể giảm độ trễ nhưng không bảo đảm nhanh hơn trong mọi trường hợp, chuyện gì xảy ra khi queue đầy hoặc ứng dụng dừng, cách đọc cấu hình Logback/Log4j và cách kiểm thử một ví dụ Java 17 chạy độc lập.

## 1. Async logging giải quyết vấn đề gì?

Xét một API nhận yêu cầu, kiểm tra dữ liệu, lưu database và ghi vài dòng log. Với **synchronous logging**, thao tác ghi log có thể thực hiện phần lớn việc định dạng và chuyển dữ liệu xuống đích ngay trong đường thực thi gọi logger. Nếu đích chậm (I/O file, console bị nghẽn, hệ thu thập log phản hồi chậm), thời gian xử lý yêu cầu có thể tăng theo.

Với **async logging**, lời gọi logger thường chỉ chuẩn bị sự kiện và đưa nó vào buffer/queue; một worker sẽ đọc và ghi sự kiện ra đích sau. Luồng nghiệp vụ quay lại công việc nhanh hơn **khi vùng đệm còn chỗ và bước tạo/đẩy sự kiện đủ nhẹ**.

~~~text
SYNC:
request thread ── tạo log ── định dạng/ghi đích ── tiếp tục nghiệp vụ
                              ^ có thể phải chờ I/O

ASYNC:
request thread ── tạo log ── enqueue ── tiếp tục nghiệp vụ
                                │
                                ▼
                          queue / buffer
                                │
                                ▼
                         background worker ── appender ── file/console/collector
~~~

Async logging **không có nghĩa ứng dụng hoàn toàn không bao giờ chờ logging**. Nó vẫn phải tạo log event, lấy timestamp/context, định dạng một phần tùy thư viện và đưa event vào queue. Khi queue đầy, chính sách cấu hình có thể bắt luồng gọi **chờ**, **ghi đồng bộ** hoặc **loại bỏ sự kiện**. Hệ thống cũng không thể ghi bền vững nhanh hơn khả năng thực tế của disk, stdout/collector hay đích cuối.

### Một ví dụ thực tế

Nếu một service phát sinh nhiều log trong khoảng tải tăng đột biến, background worker có thể ghi dần trong khi request thread tiếp tục xử lý. Đây là tình huống async giúp hấp thụ burst. Nhưng nếu tốc độ phát sinh log **liên tục lớn hơn** tốc độ worker tiêu thụ, queue cuối cùng sẽ đầy; lúc đó bài toán chuyển từ “tăng tốc caller” sang “kiểm soát quá tải và mất dữ liệu”.

## 2. Synchronous và asynchronous logging khác nhau ở đâu?

| Tiêu chí | Synchronous logging | Asynchronous logging |
| --- | --- | --- |
| Đường đi thường gặp | Caller tham gia trực tiếp vào việc đưa log đến appender/đích. | Caller gửi event đến queue; worker chuyển đến appender/đích sau. |
| Độ trễ của lời gọi logger | Dễ bị kéo dài bởi công việc ghi log và I/O. | Thường thấp hơn khi queue thông thoáng; vẫn có chi phí enqueue/context. |
| Khả năng hấp thụ burst | Hạn chế hơn vì caller chịu áp lực ngay. | Queue giúp hấp thụ burst tạm thời. |
| Bộ nhớ | Ít cần bộ đệm sự kiện riêng cho async. | Cần buffer/queue, giữ event đến khi được xử lý. |
| Khi đích ghi log chậm | Caller thường bị ảnh hưởng trực tiếp. | Queue tăng dần; sau đó sẽ phải block, drop hoặc fallback. |
| Trước khi ứng dụng dừng | Ít event còn nằm trong queue async riêng. | Phải drain/flush đúng cách, nếu không log có thể thất lạc. |
| Thứ tự ghi | Dễ suy luận trên một luồng gọi, nhưng nhiều luồng vẫn cạnh tranh. | Phụ thuộc thứ tự enqueue, số worker, nhiều appender và pipeline phía sau. |
| Độ bền dữ liệu | Không tự động đồng nghĩa đã fsync hoặc được collector nhận. | Enqueue thành công càng không đồng nghĩa đã lưu bền vững. |

Một async logger có thể cải thiện **latency của request thread** hoặc khả năng chịu tải đột biến mà chưa chắc cải thiện **end-to-end throughput của hệ thống**. Muốn kết luận, phải đo trên chính workload, appender và môi trường triển khai.

## 3. Các thành phần trong luồng ghi log bất đồng bộ

1. **Logger API**: mã ứng dụng gọi phương thức như info/warn/error. Với SLF4J, đây chủ yếu là facade; hành vi sync/async do backend và cấu hình quyết định.
2. **Log event**: cấu trúc dữ liệu chứa level, message, thời điểm, logger name, exception và metadata khác (thread, MDC/trace) nếu được thu thập.
3. **Queue/buffer**: nơi trung chuyển giữa caller và worker. Queue hữu hạn giúp giới hạn một phần mức sử dụng bộ nhớ và cho phép áp dụng chính sách khi đầy.
4. **Consumer/worker**: luồng lấy event khỏi queue, có thể xử lý theo lô rồi gọi appender đích.
5. **Appender/sink**: nơi ghi console, file, socket hoặc đẩy vào logging pipeline. Đích thực tế có thể vẫn chậm hoặc gặp lỗi.
6. **Lifecycle**: startup, shutdown, flush, xử lý exception và chỉ số để quan sát sức khỏe của đường ghi log.

### Điều gì xảy ra khi gọi logger?

Với luồng xử lý điển hình, các bước là:

~~~text
Tạo thông điệp và metadata cần thiết
  → lọc theo level / filter
  → tạo event hoặc snapshot giá trị cần dùng
  → đưa event vào queue / buffer
  → trả quyền điều khiển cho caller
  → worker lấy event
  → appender ghi đến đích
  → có thể flush theo chiến lược của đích
~~~

Thứ tự chi tiết khác nhau giữa các thư viện/cấu hình. Ví dụ một số tham số cần được định dạng hoặc chụp snapshot **trong caller thread** để không bị thay đổi trước khi worker ghi; một số thao tác format có thể được dời sang worker. Vì vậy câu “async đưa toàn bộ chi phí logging sang luồng khác” là sai.

## 4. Ví dụ Java 17 chạy độc lập: một queue và một worker

Để hiểu bản chất, chương trình sau tạo một logger tối giản bằng **ArrayBlockingQueue** và một worker. Caller thêm **LogEvent** vào hàng đợi; worker in chúng. Khi đóng logger, chương trình gửi một sentinel **STOP** nằm sau các event đã nhận rồi chờ worker hoàn thành.

Đây là **mô phỏng để học**, không phải thư viện logging dùng cho production: chưa có rolling file, logging level filter, hệ thống metrics, xử lý lỗi I/O toàn diện hoặc phối hợp dừng ứng dụng phức tạp.

Lưu thành **AsyncLoggingDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public final class AsyncLoggingDemo implements AutoCloseable {
    private record LogEvent(String level, String message) {}

    private static final LogEvent STOP = new LogEvent("", "");

    private final BlockingQueue<LogEvent> queue =
            new ArrayBlockingQueue<>(8);
    private final Thread writer;
    private boolean closed;

    public AsyncLoggingDemo() {
        writer = new Thread(this::writeLoop, "async-log-worker");
        writer.start();
    }

    public synchronized void log(String level, String message)
            throws InterruptedException {
        if (closed) {
            throw new IllegalStateException("Logger da dong");
        }
        // Co the cho neu queue day: day la backpressure.
        queue.put(new LogEvent(level, message));
    }

    private void writeLoop() {
        try {
            while (true) {
                LogEvent event = queue.take();
                if (event == STOP) {
                    return;
                }
                System.out.printf("[%s] %s: %s%n",
                        Thread.currentThread().getName(),
                        event.level(),
                        event.message());
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    @Override
    public synchronized void close() throws InterruptedException {
        if (!closed) {
            // STOP vao queue sau tat ca log da duoc chap nhan.
            queue.put(STOP);
            closed = true;
        }
        // Cho worker xu ly het event truoc STOP.
        writer.join();
    }

    public static void main(String[] args) throws Exception {
        try (AsyncLoggingDemo logger = new AsyncLoggingDemo()) {
            logger.log("INFO", "Tiep nhan yeu cau");
            logger.log("WARN", "Xu ly cham");
        }
        System.out.println("[main] Da cho ghi xong log");
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac AsyncLoggingDemo.java
java AsyncLoggingDemo
~~~

Kết quả chuẩn trong điều kiện chạy bình thường:

~~~text
[async-log-worker] INFO: Tiep nhan yeu cau
[async-log-worker] WARN: Xu ly cham
[main] Da cho ghi xong log
~~~

**Vì sao thứ tự này xác định được?** Chương trình chỉ có một producer là luồng main; queue FIFO nên hai log được worker lấy theo đúng thứ tự đã enqueue. **STOP** được chèn sau chúng; phương thức **close()** đợi **join()** xong mới trả về. Vì vậy dòng cuối luôn xuất hiện sau hai dòng log. Nếu bỏ cơ chế chờ lúc đóng, chương trình có thể in thông báo hoàn tất khi worker chưa in xong.

Điểm đáng chú ý:

- **queue.put** có thể chặn caller khi queue đầy. Async logging thường nhanh khi queue còn chỗ, nhưng không được hứa là luôn non-blocking.
- **queue.take** cho worker chờ sự kiện mà không phải tự quay vòng tiêu tốn CPU.
- **STOP** là một instance duy nhất và được nhận diện bằng phép so sánh tham chiếu; nó không va chạm với log message thông thường.
- **synchronized** ở ví dụ giúp việc nhận log và đóng logger không đưa event mới vào sau STOP. Cách này dễ hiểu nhưng có thể hạn chế khả năng mở rộng khi nhiều producer; thư viện thực tế dùng cơ chế phối hợp tối ưu hơn.
- Worker in ra console, **không bảo đảm fsync ra ổ đĩa** và không chứng minh log đã đến backend tập trung.
- Worker bị interrupt hoặc sink gặp lỗi là tình huống cần chính sách phục hồi riêng; mã trên chỉ minh họa quá trình dừng bình thường. Không sao chép nguyên mẫu này thành logger production.

### Biến thể: nếu không đợi worker khi shutdown?

Nếu chương trình kết thúc hoặc bị kill trước khi worker xử lý hết event trong queue, log chưa ghi có thể mất. Vì vậy trong server thực tế, phải cho logging framework dừng có trật tự, đợi flush trong khoảng thời gian hợp lý và kiểm tra giới hạn shutdown. **SIGKILL**, mất điện, JVM crash hoặc container bị kết thúc cưỡng bức có thể khiến dữ liệu đang chờ biến mất dù app có cơ chế shutdown thông thường.

## 5. Queue đầy: ba chính sách quan trọng

Giả sử ứng dụng phát sinh log nhanh hơn sink có thể ghi:

| Chính sách | Cách xử lý khi queue đầy | Đánh đổi |
| --- | --- | --- |
| **Block / backpressure** | Caller chờ đến khi queue có chỗ. | Ít bỏ log do đầy queue, nhưng lời gọi logger bị chậm; độ trễ nghiệp vụ có thể tăng mạnh. |
| **Drop / discard** | Loại bớt event theo mức độ ưu tiên hoặc cấu hình. | Giữ caller thông thoáng hơn nhưng có nguy cơ mất dữ liệu quan sát, đặc biệt nguy hiểm với log audit/sự cố. |
| **Synchronous fallback** | Trong một số cấu hình, event được ghi theo nhánh đồng bộ khi queue đầy. | Hạn chế mất log theo một số chính sách nhưng tạo spike latency ở caller; thứ tự với luồng ghi async cần kiểm tra. |

Một hệ thống có thể kết hợp các chính sách theo level và trạng thái. Không được giả định “ERROR luôn không mất” nếu chưa kiểm tra implementation, bộ lọc, queue-full policy và shutdown policy.

**Ví dụ tính dung lượng:** nếu đỉnh tải tạo **9.000 event/giây** trong 2 giây, còn sink tiêu thụ **5.000 event/giây**, mức tồn đọng do burst đó xấp xỉ **(9.000 − 5.000) × 2 = 8.000 event**, bỏ qua chênh lệch thời điểm/scheduling. Queue cần có dư địa tương ứng để hấp thụ burst này mà không block/drop. Nhưng tăng queue lên quá lớn sẽ làm tăng lượng bộ nhớ bị giữ lại và thời gian drain. Nếu tốc độ đầu vào cao hơn đầu ra **liên tục**, mọi queue hữu hạn đều cuối cùng sẽ đầy.

Trong production cần quyết định rõ: log nào bắt buộc phải giữ, log nào có thể sampling/drop, SLA chấp nhận được khi queue đầy, và cách báo động khi xảy ra mất sự kiện.

## 6. Cấu hình async logging bằng thư viện phổ biến

### 6.1. SLF4J là API, backend mới quyết định cách ghi

Đoạn Java sử dụng API SLF4J điển hình:

~~~java
// Mã minh họa; cần dependency SLF4J và backend phù hợp.
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(MyService.class);

public void process(String orderId) {
    LOG.info("Processing order {}", orderId);
}
~~~

Đây **không phải chương trình độc lập** vì cần class **MyService** và dependency logging. Lời gọi **LOG.info** không đủ để xác nhận hệ thống đang dùng async logging. Phải xem backend thực tế (ví dụ Logback hoặc Log4j2) và appender/logger configuration.

Nếu dùng placeholder **{}**, framework có thể tránh việc tự nối chuỗi khi level bị tắt, nhưng vẫn có chi phí tạo tham số, lập event và xử lý khác. Không gọi phép tính tốn kém hoặc có side effect chỉ để tạo tham số log mà không cân nhắc điều kiện level.

### 6.2. Logback AsyncAppender

Trong dự án đã tích hợp Logback Classic, cấu hình minh họa **logback.xml** có thể là:

~~~xml
<configuration>
    <appender name="FILE" class="ch.qos.logback.core.FileAppender">
        <file>application.log</file>
        <append>true</append>
        <encoder>
            <pattern>%d{ISO8601} %-5level [%thread] %logger - %msg%n</pattern>
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
~~~

Ý nghĩa các lựa chọn:

- **FILE** là appender thật ghi file, còn **ASYNC** nhận log và chuyển cho FILE trên luồng khác.
- **queueSize=1024** đặt sức chứa queue. Đây là con số minh họa, cần sizing theo workload và bộ nhớ.
- **discardingThreshold=0** tắt cơ chế bỏ các event level thấp theo ngưỡng dung lượng còn trống của AsyncAppender; không có nghĩa hệ thống đã bảo đảm durability trong mọi lỗi.
- **neverBlock=false** nghĩa là khi queue đã đầy, caller có thể bị block cho đến khi có chỗ thay vì đơn giản bỏ event do queue full.
- **maxFlushTime=5000** cho phép đợi worker trong tối đa khoảng 5 giây khi context dừng; event chưa kịp xử lý sau thời hạn có nguy cơ bị bỏ. Muốn ưu tiên cố gắng drain hết thì phải cân nhắc thời gian shutdown cho phép.
- Root chỉ tham chiếu ASYNC; không tham chiếu đồng thời FILE ở root nếu mục tiêu là tránh ghi trùng log qua hai đường.

Theo tài liệu Logback, mặc định AsyncAppender có cơ chế bỏ bớt **TRACE/DEBUG/INFO** khi queue sắp đầy theo ngưỡng và có lựa chọn **neverBlock**. Do đó phải đọc **cấu hình thực tế**, không suy diễn rằng mọi AsyncAppender đều có hành vi của mẫu trên.

Khi cần caller class, method hoặc line number trong log, lưu ý dữ liệu vị trí caller có thể tốn chi phí lấy stack trace. Với Logback, tùy chọn **includeCallerData** cho phép thu thập nhưng đánh đổi hiệu năng. Thread name và MDC cũng cần được snapshot đúng lúc để không lẫn thông tin với thread nền.

### 6.3. Log4j2: Async Appender và Async Logger

Log4j2 cung cấp hai cơ chế có thể gặp:

- **Async Appender**: queue sự kiện rồi chuyển đến appender đích trên thread riêng.
- **Async Logger**: cơ chế logger bất đồng bộ dùng **LMAX Disruptor/ring buffer**, có cấu hình và dependency cần thiết theo phiên bản triển khai.

Hai cơ chế không hoàn toàn giống nhau về đường đi event, cấu hình hay hiệu năng; không tự ý xếp cả hai tầng async lên nhau rồi cho rằng sẽ nhanh hơn. Với Log4j2, cấu hình queue-full policy có thể cho phép **block** hoặc **discard** tùy chính sách; chi tiết phải theo phiên bản và cấu hình đang sử dụng.

Nếu ứng dụng là Spring Boot, framework không tự biến mọi logger thành async chỉ vì API/controller bất đồng bộ. Cần xem backend thực tế, file logging configuration, các profile và nơi appender được đăng ký. Dùng dependency và tài liệu khớp với phiên bản đang chạy.

## 7. Thứ tự, thời gian và thông tin context trong log

Async logging tạo khoảng cách giữa **thời điểm xảy ra sự kiện** và **thời điểm worker ghi nó xuống đích**. Hai thời điểm này có thể khác nhau đáng kể khi queue backlog.

### Thứ tự

- Một producer, một queue FIFO, một consumer: thứ tự tiêu thụ thường theo thứ tự được chấp nhận vào queue.
- Nhiều producer: thứ tự thực tế phản ánh lúc enqueue được chấp nhận, không nhất thiết đúng theo thời điểm nghiệp vụ đã xảy ra trong các luồng.
- Nhiều consumer, nhiều appender, hệ thống phân tán hoặc log pipeline tập trung: không hứa tổng thứ tự toàn cục. Khi phân tích, dựa vào timestamp, trace/span ID, sequence hoặc correlation ID phù hợp.

Không dùng sự xuất hiện trễ của dòng log trong file để kết luận chắc chắn rằng thao tác nghiệp vụ cũng xảy ra trễ.

### Thread và MDC/trace context

Worker ghi log thường là một thread khác. Nếu nó tự lấy **Thread.currentThread().getName()** hoặc dữ liệu từ **ThreadLocal/MDC** của nó, kết quả có thể thuộc worker thay vì thread đã tạo event. Một logging backend đúng phải chụp metadata cần dùng theo cơ chế của nó **trước khi chuyển ngữ cảnh**, hoặc hỗ trợ propagation thích hợp.

Ví dụ ở phần Java 17 cố tình in **async-log-worker** để bạn thấy luồng thực sự ghi; đó không có nghĩa các framework logging nhất thiết sẽ hiển thị tên worker. Framework thường cung cấp cách giữ thread name/MDC của caller trong event.

Async logging và **async business processing** cũng là hai khái niệm khác nhau: đưa business task vào ExecutorService không tự động khiến log được ghi bất đồng bộ, và bật AsyncAppender không tự động truyền **traceId** qua các tác vụ business.

### Mutable message và exception

Nếu đối tượng được đưa vào log bị thay đổi sau lời gọi logger, một cơ chế trì hoãn định dạng mà không snapshot đủ dữ liệu có thể thấy trạng thái mới thay vì trạng thái ban đầu. Cần hiểu cách backend xử lý tham số mutable; ưu tiên log dữ liệu bất biến hoặc snapshot có chủ đích. Khi log exception, truyền exception đúng API để stack trace được ghi theo formatter; đừng tự cắt bỏ thông tin lỗi quan trọng chỉ để giảm kích thước queue.

## 8. Async logging có bảo đảm không mất log không?

**Không.** Có nhiều thời điểm khác nhau:

~~~text
Event được tạo
    ↓
Enqueue thành công                [mới vào bộ nhớ ứng dụng]
    ↓
Worker lấy event
    ↓
Appender viết/flush              [có thể vẫn nằm trong cache/buffer]
    ↓
File/collector xác nhận          [tùy cơ chế]
    ↓
Lưu bền vững hoặc index để truy vấn [tùy đích và chính sách]
~~~

Trạng thái “đã vào queue” khác với “đã ghi ra file”, “đã fsync” hay “đã được hệ thống tập trung tiếp nhận”. Nếu ứng dụng crash, JVM bị kill cưỡng bức, máy mất điện, sink lỗi hoặc queue bị drop, event chưa bền vững có thể mất.

Với **audit/security/financial event** cần bảo toàn cao, phải xác định yêu cầu lưu trữ cụ thể. Có thể chọn đường ghi bền vững riêng, nhật ký giao dịch, transactional outbox hoặc cơ chế xác nhận thích hợp. Không lấy async logging thông thường thay cho cơ chế bảo đảm dữ liệu nghiệp vụ.

## 9. Khi nào nên dùng và khi nào cần cân nhắc?

**Phù hợp khi:**

- Ứng dụng ghi nhiều log, có những đợt traffic hoặc log burst ngắn.
- Đường ghi file/console tạo latency spike ảnh hưởng tới xử lý request.
- Chấp nhận được việc log đến đích muộn trong một khoảng ngắn và đã có chiến lược bảo vệ khi queue đầy.
- Có quan sát được backlog, drop, blocked time và shutdown drain.

**Cần cân nhắc kỹ khi:**

- Khối lượng log thấp; thêm queue và worker chỉ làm tăng độ phức tạp.
- Đích ghi log đã cực nhanh, benchmark không cho thấy lợi ích.
- Ứng dụng có giới hạn bộ nhớ/CPU nghiêm ngặt.
- Log mang tính audit, pháp lý hoặc cần thứ tự/độ bền mạnh.
- Container thường bị kết thúc nhanh hoặc logging backend chưa có lifecycle quản lý đúng.
- Đã gặp overload kéo dài: async queue không thể giải quyết sink thiếu năng lực xử lý.

Một cấu hình phù hợp với benchmark trong môi trường staging chưa chắc phù hợp production nếu sink, filesystem, mức độ log hoặc burst distribution khác nhau.

## 10. Vận hành và kiểm thử

### Các chỉ số cần quan sát

| Nhóm chỉ số | Mục đích |
| --- | --- |
| **Queue occupancy / capacity** | Biết buffer gần đầy hoặc đã tích tụ backlog. |
| **Events enqueued / processed** | So tốc độ tạo và tốc độ tiêu thụ; phát hiện worker theo không kịp. |
| **Discard count theo level** | Biết có mất log do chính sách quá tải hay không. |
| **Thời gian enqueue bị block** | Đo ảnh hưởng ngược lên latency của luồng nghiệp vụ. |
| **Appender errors / collector failures** | Phát hiện đích log không ghi được dù enqueue có thể vẫn thành công. |
| **Drain/flush duration và số event còn lại lúc shutdown** | Ước lượng nguy cơ mất log khi deploy hoặc restart. |
| **CPU, heap, GC, throughput, p95/p99 request latency** | Đánh giá hiệu năng tổng thể, không chỉ tốc độ trả về của logger. |

Không phải mọi thư viện đều cung cấp tất cả metric trên mặc định. Có thể phải bật instrumentation hoặc đo tại appender/pipeline.

### Các tình huống nên kiểm thử

1. **Normal load:** gửi log cùng một luồng, kiểm tra chúng xuất hiện đủ và có thứ tự hợp lý.
2. **Burst:** tạo tải ngắn lớn hơn tốc độ sink, đo backlog và thời gian hồi phục.
3. **Sustained overload:** làm sink chậm lâu dài; xác nhận block/drop/fallback đúng chính sách đã công bố.
4. **Shutdown có trật tự:** dừng logger/app khi queue còn event; kiểm tra thời hạn drain, số event còn lại và log warning.
5. **Shutdown cưỡng bức:** thử kill process trong môi trường thử nghiệm để hiểu giới hạn durability, không đặt kỳ vọng “không mất log” nếu không có thiết kế đảm bảo.
6. **MDC/trace và đa luồng:** bảo đảm correlation ID, timestamp và caller data không bị biến thành dữ liệu của worker hoặc request khác.
7. **Sink thất bại:** permission/file full/collector offline; xác nhận ứng dụng và hệ quan sát phản ứng đúng.
8. **Kích thước message lớn:** đo sử dụng bộ nhớ, GC và ảnh hưởng của các exception stack trace dài.

Để chọn queue size, dùng số đo burst thực tế, kích thước event trong bộ nhớ và thời gian chấp nhận backlog. Đừng cấu hình queue cực lớn rồi bỏ qua cảnh báo vì điều đó chỉ trì hoãn lúc quá tải.

## 11. Những hiểu lầm phổ biến

- **“Async log = không bao giờ block.”** Sai: enqueue có thể block khi buffer đầy; một số backend có đường fallback đồng bộ.
- **“Gọi log xong là dữ liệu đã nằm an toàn trên disk.”** Sai: có thể chỉ mới enqueue trong RAM.
- **“Async logging luôn tăng throughput.”** Sai: có overhead đồng bộ, phân bổ object, chuyển thread và giới hạn tốc độ sink.
- **“Sự kiện ghi log sẽ xuất hiện trong đúng thứ tự nghiệp vụ của mọi thread.”** Sai: thứ tự toàn cục không được bảo đảm theo cách đó.
- **“Bật AsyncAppender là tự có traceId/MDC xuyên thread pool business.”** Sai: cần propagation cho tác vụ nghiệp vụ và snapshot metadata log phù hợp.
- **“Queue càng lớn càng tốt.”** Sai: queue lớn dùng nhiều bộ nhớ, tăng độ trễ tồn đọng và thời gian shutdown; quá tải dài hạn vẫn làm đầy.
- **“Mọi ERROR đều không bị mất.”** Sai: còn phụ thuộc chính sách drop, shutdown, sink và độ bền lưu trữ.
- **“Một async appender và async logger cùng lúc luôn nhanh gấp đôi.”** Sai: xếp thêm tầng đệm/worker không bảo đảm lợi ích; có thể tăng overhead và khó chẩn đoán.

## 12. Kết luận

Async logging là một **kỹ thuật tách producer khỏi đường ghi log có thể chậm**. Điểm lợi chính là làm nhẹ đường thực thi của request khi queue có khả năng hấp thụ tải; điểm đánh đổi là **buffer, độ trễ log xuất hiện, chính sách quá tải và rủi ro log còn tồn đọng lúc dừng**. Học cách đọc queue policy, khôi phục đúng caller context, đo queue/backpressure và kiểm tra graceful shutdown sẽ giúp bạn dùng async logging có trách nhiệm trong ứng dụng Java.

**Tài liệu kỹ thuật tham khảo:**

- Logback Manual – AsyncAppender: https://logback.qos.ch/manual/appenders-async-sift.html
- Apache Log4j – Asynchronous loggers: https://logging.apache.org/log4j/2.x/manual/async.html
- Apache Log4j – Performance and trade-offs: https://logging.apache.org/log4j/2.x/manual/performance.html
