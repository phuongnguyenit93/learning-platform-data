# Đo chi phí ghi nhật ký trước khi bật mức rất chi tiết

Bật DEBUG, TRACE hoặc mức chi tiết tương đương có thể làm thay đổi đáng kể hiệu năng của JVM. Chi phí không chỉ nằm ở việc ghi file: ứng dụng còn phải kiểm tra level, tạo message, chuyển đổi object, tạo LogRecord, thu thập context, xếp hàng, format, mã hóa và chuyển dữ liệu tới appender hoặc handler.

Trước khi bật mức log rất chi tiết, hãy đo trên workload đại diện. Tách riêng chi phí khi level bị tắt, chi phí tạo và dispatch LogRecord khi level bật, rồi đo thêm đường ghi thực tế tới file hoặc hệ thống log tập trung. Dùng kết quả để chọn phạm vi logger, thời gian bật, sampling và giới hạn lưu trữ.

## 1. Chi phí của một lời gọi log

Một lời gọi log có thể đi qua nhiều bước:

1. Kiểm tra level và filter của logger.
2. Đánh giá các biểu thức Java dùng làm đối số.
3. Tạo message, gọi toString, serialize object hoặc tạo stack trace.
4. Tạo LogRecord hoặc cấu trúc sự kiện tương ứng.
5. Thu thập timestamp, thread, logger name, source class/method và context như trace ID.
6. Chuyển record qua filter và handler/appender.
7. Format message, thêm metadata, encode thành byte.
8. Đưa vào queue hoặc ghi đồng bộ tới file, console, socket hay collector.
9. Flush, rotate file, retry hoặc xử lý backpressure khi đích ghi chậm.

Level bị tắt thường bỏ qua phần lớn pipeline phía logger, nhưng không tự hoàn tác công việc Java đã thực hiện trước khi gọi logger. Ví dụ, phép nối chuỗi và serialize object được đánh giá trước khi method log được gọi.

Chi phí cần quan sát gồm:

- CPU time và throughput.
- Allocation rate và GC pressure do message, LogRecord, context hoặc encoder.
- Request latency, đặc biệt p95/p99 khi handler chậm.
- Số event và số byte mỗi giây.
- Queue depth, queue wait, số event bị drop hoặc caller bị block.
- File I/O, network I/O, flush và rotation.
- Lock contention giữa các thread cùng ghi vào một appender.

Một log event có thể rất rẻ khi level bị tắt nhưng đắt khi được bật vì message chứa object lớn hoặc stack trace. Vì vậy đừng suy luận chi phí chỉ từ số dòng log trong source.

## 2. Mức log chi tiết không giống nhau giữa các API

Tên level phụ thuộc logging API:

| API | Mức chi tiết thường dùng |
|---|---|
| java.util.logging (JUL) | FINE, FINER, FINEST |
| System.Logger (Java 9+) | DEBUG, TRACE |
| SLF4J / Log4j và framework tương tự | DEBUG, TRACE |

Không giả định FINE tương đương tuyệt đối với DEBUG hoặc FINEST tương đương TRACE. Severity, filter hierarchy và cách cấu hình phụ thuộc provider/framework.

Java 9 bổ sung System.Logger làm facade logging của JDK. API này có level TRACE/DEBUG và overload nhận Supplier để trì hoãn tạo message:

~~~java
System.Logger logger = System.getLogger(MyService.class.getName());

logger.log(
        System.Logger.Level.TRACE,
        () -> buildExpensiveDiagnosticMessage()
);
~~~

Với java.util.logging, có thể dùng:

~~~java
Logger logger = Logger.getLogger(MyService.class.getName());

logger.fine(() -> buildExpensiveDiagnosticMessage());
~~~

Supplier chỉ được gọi khi level tương ứng được bật và event có thể được log. Đây là cách tránh tạo message đắt tiền khi mức log đang tắt.

## 3. Tránh tạo message trước khi kiểm tra level

Mẫu eager sau vẫn tạo chuỗi dù FINE đang tắt:

~~~java
logger.fine("request=" + buildExpensiveMessage(request));
~~~

Phép nối chuỗi và buildExpensiveMessage chạy trước khi logger kiểm tra level. Nếu buildExpensiveMessage đọc nhiều field, serialize object hoặc tạo stack trace, ứng dụng vẫn phải trả chi phí đó.

Có hai cách phổ biến để trì hoãn:

**Supplier của logger**

~~~java
logger.fine(() -> "request=" + buildExpensiveMessage(request));
~~~

**Kiểm tra level trước khi tính toán**

~~~java
if (logger.isLoggable(Level.FINE)) {
    logger.fine("request=" + buildExpensiveMessage(request));
}
~~~

Supplier thường gọn hơn nếu logger hỗ trợ overload này. Guard tường minh hữu ích khi một block tạo nhiều giá trị đắt tiền hoặc có nhiều lời gọi log cùng điều kiện.

Parameterized logging cũng giúp tránh format message khi level tắt:

~~~java
logger.log(Level.FINE, "request={0}, status={1}", new Object[] {
        requestId, status
});
~~~

Tuy nhiên, biểu thức tạo argument vẫn được đánh giá trước lời gọi. Ví dụ logger.debug("payload={}", serialize(payload)) vẫn serialize payload ngay cả khi DEBUG tắt. Muốn trì hoãn cả phép tính, dùng Supplier hoặc guard.

## 4. Đừng biến việc kiểm tra level thành công việc lặp lại

Nếu chỉ log một chuỗi rẻ, gọi logger trực tiếp thường đủ:

~~~java
logger.fine("cache lookup completed");
~~~

Nếu cần tạo message phức tạp, dùng Supplier:

~~~java
logger.fine(() -> describeCacheState(cache));
~~~

Nếu một block tạo nhiều giá trị đắt tiền:

~~~java
if (logger.isLoggable(Level.FINER)) {
    String index = buildIndexDump(indexState);
    String queryPlan = explainQuery(query);
    logger.finer("index=" + index + ", plan=" + queryPlan);
}
~~~

Không cần thêm isLoggable trước mọi lời gọi Supplier; việc kiểm tra level vốn đã nằm trong logger. Guard lặp lại có thể làm code rối và tạo một lần kiểm tra thừa.

Lưu ý rằng tạo lambda/Supplier cũng có thể có chi phí nhỏ. JVM thường tối ưu nhiều lambda không capture, nhưng không nên giả định mọi trường hợp đều miễn phí. Đo chính pattern thực tế bằng benchmark.

## 5. Những nguồn chi phí thường bị bỏ sót

### Chuyển đổi object và serialization

toString của object có thể duyệt graph lớn, truy vấn dữ liệu hoặc tạo chuỗi nhiều allocation. JSON serialization có thể tạo nhiều buffer và chuỗi tạm. Không log toàn bộ object chỉ vì TRACE đang bật.

### Stack trace

Tạo Throwable để lấy stack trace có thể tốn CPU và allocation. Ghi cùng một stack trace cho hàng nghìn request lỗi có thể tạo lượng log lớn. Dùng sampling, rate limit hoặc log một lần cho một loại lỗi nếu phù hợp.

### Context và caller location

MDC/thread context, trace ID, thread name, source class/method và caller inference cần được thu thập hoặc sao chép. Một số framework có thể phải tìm caller location qua stack walk; chi phí phụ thuộc implementation và cấu hình.

### Formatting và encoding

Message template, timestamp format, JSON layout, escaping, charset encoding và metadata có chi phí CPU. Format phức tạp và nhiều field làm tăng cả CPU lẫn kích thước event.

### I/O và flush

Ghi console, file, socket hoặc collector có thể block. Flush quá thường xuyên làm giảm khả năng batching. File rotation, DNS, TLS, network congestion hoặc collector chậm có thể làm latency tăng mạnh.

### Queue và async logging

Async appender chuyển một phần công việc khỏi thread ứng dụng, nhưng không xóa chi phí. Ứng dụng vẫn phải tạo event và enqueue; thread nền vẫn phải format/ghi. Khi queue đầy, framework có thể block caller, drop event hoặc áp dụng chính sách khác. Queue lớn cũng giữ nhiều object trong heap và có thể làm GC tăng.

Hành vi cụ thể phụ thuộc framework và cấu hình. Kiểm tra chính sách queue-full, discard, blocking, batching và shutdown flush trước khi bật TRACE.

## 6. Đo theo từng lớp để biết chi phí nằm ở đâu

Một kế hoạch đo nên tách các trường hợp sau:

| Trường hợp | Mục tiêu |
|---|---|
| Level tắt, message eager | Đo phần chi phí vẫn xảy ra trước logger |
| Level tắt, Supplier | Đo đường log bị loại sớm và chi phí Supplier |
| Level bật, handler loại bỏ output | Đo logger, LogRecord, filter và dispatch |
| Level bật, formatter thực tế | Đo format và encode |
| Level bật, file/network appender thật | Đo I/O, queue, flush và backpressure |
| Workload nhiều thread | Đo contention, throughput và tail latency |

Không so sánh một trường hợp ghi console với một trường hợp dùng handler loại bỏ output rồi kết luận khác biệt chỉ do level. Hãy giữ workload, JVM, input, số thread và sink tương đương khi so sánh.

### Đo lượng dữ liệu log

Ước lượng sơ bộ:

~~~text
log bytes/second = events/second * average bytes/event
daily bytes = log bytes/second * 86,400
~~~

Ví dụ 2.000 event/giây, trung bình 700 byte/event:

~~~text
2,000 * 700 = 1,400,000 bytes/second
1,400,000 * 86,400 = 120,960,000,000 bytes/day
~~~

Tương đương khoảng 121 GB/ngày theo đơn vị thập phân, chưa tính overhead của transport, index và replication. Khi bật log chi tiết, kích thước event trung bình có thể tăng do stack trace, context hoặc payload.

## 7. Dùng JMH cho microbenchmark

JMH là harness benchmark của OpenJDK, được thiết kế để xử lý warm-up, fork, measurement iteration và các vấn đề thường gặp khi đo JVM. Không nên đo một lời gọi log bằng một lần gọi System.nanoTime rồi lấy kết quả làm kết luận.

Một benchmark cần:

- Warm-up để JIT biên dịch và ổn định profile.
- Nhiều fork để tránh kết quả phụ thuộc trạng thái JVM trước đó.
- Nhiều measurement iteration.
- Input đại diện, không phải message hằng số dễ bị tối ưu hóa.
- Sink có kiểm soát để tránh console/file I/O làm nhiễu benchmark micro.
- Đo allocation bằng -prof gc.
- Chạy cả trường hợp level tắt và level bật.

Ví dụ benchmark dùng JUL và handler loại bỏ output. Đây là lớp benchmark cần JMH (jmh-core và annotation processor) trên benchmark classpath; nó không phải chương trình Java độc lập:

~~~java
import java.util.concurrent.TimeUnit;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.concurrent.atomic.LongAdder;

import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 8)
@Fork(3)
public class LoggingCostBenchmark {
    @Param({"INFO", "FINE"})
    public String threshold;

    private Logger logger;
    private DiscardHandler handler;
    private int sequence;

    @Setup(Level.Trial)
    public void setup() {
        logger = Logger.getLogger(
                "benchmark." + Thread.currentThread().getId()
        );
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.parse(threshold));

        handler = new DiscardHandler();
        handler.setLevel(Level.ALL);
        logger.addHandler(handler);
    }

    @TearDown(Level.Trial)
    public void tearDown() {
        logger.removeHandler(handler);
    }

    private String buildMessage(int id) {
        StringBuilder text = new StringBuilder(256);
        for (int i = 0; i < 16; i++) {
            text.append("request=").append(id)
                    .append(", field").append(i).append('=').append(i)
                    .append(';');
        }
        return text.toString();
    }

    @Benchmark
    public void eagerConcatenation() {
        int id = ++sequence;
        logger.fine("details=" + buildMessage(id));
    }

    @Benchmark
    public void lazySupplier() {
        int id = ++sequence;
        logger.fine(() -> "details=" + buildMessage(id));
    }

    @Benchmark
    public void guardedMessage() {
        int id = ++sequence;
        if (logger.isLoggable(Level.FINE)) {
            logger.fine("details=" + buildMessage(id));
        }
    }

    static final class DiscardHandler extends Handler {
        private final LongAdder consumedCharacters = new LongAdder();

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                consumedCharacters.add(record.getMessage().length());
            }
        }

        @Override
        public void flush() {
        }

        @Override
        public void close() {
        }
    }
}
~~~

Chạy JMH với các fork/warm-up/measurement đã khai báo và thêm profiler GC:

~~~bash
java -jar target/benchmarks.jar LoggingCostBenchmark -prof gc
~~~

Đọc kết quả theo từng threshold:

- Khi threshold là INFO, eagerConcatenation vẫn tạo message; Supplier và guard tránh phần lớn công việc tạo message.
- Khi threshold là FINE, cả ba pattern đều tạo message và dispatch event.
- gc.alloc.rate.norm giúp xem allocation trên mỗi operation.
- Average time không cho biết đầy đủ tail latency; dùng sample-time mode hoặc workload test nếu p95/p99 là mục tiêu.

DiscardHandler chỉ đo logger, record creation và dispatch tới handler giả lập. Nó không đại diện cho formatter JSON, file appender, network collector hay async queue thật.

## 8. Đo đường ghi thực tế bằng load test

Sau microbenchmark, chạy workload tích hợp với handler/appender giống production:

1. Dùng cùng input, dữ liệu, số request và số thread.
2. Chạy baseline với level hiện tại.
3. Bật đúng logger/package cần điều tra ở DEBUG/TRACE.
4. Dùng cùng formatter, queue, file rotation và network destination.
5. Chạy đủ lâu để queue, batching và rotation thể hiện hành vi.
6. So sánh throughput, p50/p95/p99, CPU, allocation, GC, disk/network I/O, queue depth và dropped events.
7. Lặp lại để xác nhận kết quả không phải biến động ngẫu nhiên.

Không dùng console output làm sink duy nhất cho benchmark throughput. Console thường chậm và có thể serialize các writer; kết quả khi đó chủ yếu đo terminal/pipe.

Không ghi vào cùng một file từ nhiều lần chạy benchmark nếu muốn so sánh chính xác. Dùng file riêng hoặc sink được kiểm soát, rồi kiểm tra cả dung lượng và chi phí rotation.

## 9. Dùng Java Flight Recorder để tìm hotspot

Java Flight Recorder (JFR) trên các JDK hiện hành giúp quan sát CPU samples, allocation, file/socket I/O, thread park và lock contention. JFR không tự đưa ra một con số duy nhất gọi là logging overhead; cần đọc các event và stack trace trong khoảng workload có bật log.

Khởi chạy ứng dụng với recording:

~~~bash
java -XX:StartFlightRecording=filename=log-cost.jfr,settings=profile,dumponexit=true -jar application.jar
~~~

Hoặc attach vào JVM đang chạy:

~~~bash
jcmd <pid> JFR.start name=LogCost settings=profile
jcmd <pid> JFR.dump name=LogCost filename=log-cost.jfr
jcmd <pid> JFR.stop name=LogCost
~~~

Mở file recording bằng Java Mission Control và tập trung vào:

- Execution samples có stack đi qua logger, formatter, encoder hoặc appender.
- Allocation hot spots như String, byte[], LogRecord, event/context object.
- FileRead/FileWrite và SocketRead/SocketWrite khi sink là file hoặc network.
- ThreadPark, JavaMonitorEnter và các wait liên quan queue hoặc lock.
- CPU load và GC trong cùng khoảng thời gian.

JFR có overhead riêng và profile settings có thể thu thập nhiều event. Dùng recording ngắn, cùng workload và cùng cấu hình cho baseline/verbose run. JFR giúp tìm nguyên nhân; load test vẫn cần đo tác động lên request latency và throughput.

JFR được tích hợp trong các JDK hiện hành; khi vận hành hệ thống Java 9 cũ, hãy kiểm tra khả năng và cách phân phối JFR của đúng vendor/build. Không lấy một lệnh JFR của JDK mới làm bằng chứng rằng mọi runtime Java 9 đều hỗ trợ cùng tính năng.

## 10. Kiểm soát khi bật log rất chi tiết

Không bật TRACE/FINEST toàn bộ JVM trong thời gian dài nếu chỉ cần điều tra một thành phần. Ưu tiên:

- Chỉ bật logger/package/class liên quan.
- Đặt thời gian bật ngắn và có người chịu trách nhiệm tắt.
- Dùng sampling hoặc rate limiting cho event lặp nhiều.
- Tránh log toàn bộ request body, object graph hoặc binary payload.
- Không ghi password, token, session ID, secret hoặc dữ liệu cá nhân không cần thiết.
- Giới hạn kích thước message và số stack trace.
- Kiểm tra retention, rotation, disk quota và chi phí ingest/index.
- Theo dõi queue depth, dropped events và appender errors.
- Đảm bảo shutdown có thời gian flush queue phù hợp.
- Có rollback nhanh nếu latency, CPU, heap hoặc disk vượt ngưỡng.

Async logging có thể giảm thời gian caller chờ I/O nhưng có thể mất event khi queue đầy hoặc JVM dừng đột ngột, tùy chính sách framework. Chọn rõ semantics: block, drop, fallback synchronous hay caller-runs. Không đánh đổi độ tin cậy của audit/security log chỉ để giảm latency.

## 11. Những lỗi đo lường thường gặp

**Chỉ đo khi log level bị tắt:** không thấy chi phí format, encode, appender hoặc I/O. Phải đo cả enabled path.

**Đo bằng một vòng lặp System.nanoTime:** JIT warm-up, dead-code elimination, timer overhead và scheduling làm kết quả thiếu tin cậy. Dùng JMH.

**Ghi console trong microbenchmark:** terminal/pipe thường trở thành bottleneck và che mất chi phí logger.

**Không kiểm tra allocation:** hai phương án có latency gần nhau nhưng một phương án tạo nhiều object hơn và gây GC khi chạy lâu.

**Dùng input hằng số:** JIT có thể tối ưu biểu thức hoặc không đại diện dữ liệu thật. Dùng state thay đổi và workload có phân bố thực tế.

**Chỉ xem average:** p99 có thể tăng do queue đầy, flush hoặc collector chậm. Đo tail latency trong load test.

**Bật mọi logger cùng lúc:** khó tìm nguồn chi phí và tạo lượng log không cần thiết. Bật theo phạm vi nhỏ.

**Cho rằng async là miễn phí:** queue, copy context, encoding và background I/O vẫn tốn tài nguyên.

**Bỏ qua log volume:** event nhỏ nhưng tần suất cao vẫn tạo hàng trăm GB mỗi ngày.

**Log dữ liệu nhạy cảm để debug:** log chi tiết có thể tồn tại lâu hơn request và được nhiều hệ thống truy cập. Redact dữ liệu trước khi ghi.

## 12. Quy trình quyết định trước khi bật TRACE/FINEST

- Xác định câu hỏi điều tra và logger cụ thể cần bật.
- Ước lượng event rate, average event size và thời gian bật.
- Kiểm tra Supplier/guard cho message có chi phí cao.
- Chạy JMH để tách chi phí eager, lazy, disabled và enabled.
- Chạy load test với formatter/appender thật.
- Dùng JFR để tìm CPU, allocation, I/O và contention hotspot.
- Đặt ngưỡng chấp nhận cho p95/p99, throughput, CPU, heap, disk và dropped events.
- Bật canary theo phạm vi nhỏ, theo dõi rồi mở rộng nếu đạt ngưỡng.
- Tắt mức chi tiết khi đã thu đủ dữ liệu và xác nhận log được lưu/đọc đúng.
- Ghi lại cấu hình, thời gian bật, lượng dữ liệu và kết luận.

Mục tiêu không phải làm cho log chi tiết luôn rẻ. Mục tiêu là biết chính xác chi phí của nó trên workload thật, giới hạn phạm vi và thời gian bật, đồng thời bảo đảm dữ liệu chẩn đoán đủ giá trị để xứng đáng với CPU, allocation, I/O và dung lượng lưu trữ phát sinh.

## Tài liệu tham khảo

- [System.Logger — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/System.Logger.html)
- [java.util.logging.Logger — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.logging/java/util/logging/Logger.html)
- [Java Flight Recorder — JDK Mission Control](https://docs.oracle.com/en/java/java-components/jdk-mission-control/)
- [OpenJDK JMH project and samples](https://github.com/openjdk/jmh)
- [JEP 328 — Flight Recorder](https://openjdk.org/jeps/328)
