# Throughput của appender trong Java Logging

## 1. Throughput của appender là gì?

**Appender** là thành phần của logging backend nhận một sự kiện log rồi chuyển nó tới đích như console, file, mạng hoặc collector. **Throughput của appender** là tốc độ sự kiện mà appender có thể xử lý trong một khoảng thời gian, thường biểu diễn bằng **events/second** hoặc **bytes/second**.

Trong hệ thống Java dùng SLF4J với Logback hay Log4j 2, lời gọi logger.info(...) có thể đi qua logger, filter, encoder/layout rồi tới appender. Đường xuất có thể đồng bộ trên luồng ứng dụng hoặc bất đồng bộ qua queue/ring buffer.

~~~text
Application threads
        |
        v
logger.info/debug/error(...)
        |
        v
    Logger + filter
        |
        v
  Async queue (nếu có)
        |
        v
 Appender + layout/encoder
        |
        +---> stdout / console
        +---> file / disk
        +---> network / collector
~~~

Nếu một appender ghi được 6.000 sự kiện/giây, mỗi sự kiện trung bình 500 byte, thông lượng dữ liệu đầu ra xấp xỉ 3.000.000 byte/giây (3 MB/giây theo hệ thập phân). Con số chưa tính các byte phát sinh do giao thức, metadata, header mạng hoặc định dạng bổ sung.

**Điểm quan trọng:** appender throughput là tốc độ xử lý ở **vị trí được đo**. Thời gian logger.info(...) trả về nhanh không tự chứng minh rằng log đã được ghi thành công tại đích. Khi dùng async, hàm có thể trả về ngay sau khi enqueue, còn worker chưa kịp ghi một sự kiện nào.

## 2. Những con số throughput không được đánh đồng

| Đại lượng | Điểm đo | Điều chưa khẳng định |
| --- | --- | --- |
| Producer call rate | Số lần ứng dụng gọi logger mỗi giây | Có bao nhiêu event qua được level/filter? |
| Accepted/enqueued rate | Số sự kiện được hệ thống logging nhận vào queue mỗi giây | Appender đã xử lý hoặc sink đã ghi? |
| Appender processed rate | Số sự kiện appender xử lý xong mỗi giây | Dữ liệu đã bền vững hay collector đã xác nhận? |
| Sink confirmed rate | Số event được hệ thống nhận đích xác nhận theo giao thức | Có thể đọc lại hoặc khôi phục sau sự cố theo mức đảm bảo nào? |
| Output bandwidth | Số byte được encode/ghi/chuyển mỗi giây | Bao nhiêu event và kích thước phân bố của chúng? |

Ví dụ: root logger chỉ bật WARN nhưng code gọi logger.debug(...) 500.000 lần/giây. Phần lớn các lời gọi có thể bị loại trước khi tạo event đầy đủ. Không thể gọi 500.000 là throughput của FileAppender.

Ngược lại, AsyncAppender có thể nhận 100.000 event trong một đợt ngắn nhưng FileAppender phía sau chỉ ghi được 10.000 event/giây. Các event còn lại nằm trong queue; nếu tình trạng kéo dài, queue sẽ đầy. Cần đếm cả event đã tạo, đã chấp nhận, đã xử lý, đã bỏ và đã xác nhận ở sink.

## 3. Peak throughput và sustainable throughput

**Peak/burst throughput** là tốc độ cao nhất quan sát được trong một cửa sổ ngắn. **Sustainable throughput** là tốc độ có thể duy trì đủ lâu mà backlog không tăng không kiểm soát, latency và tài nguyên vẫn trong ngưỡng mong muốn, đồng thời đáp ứng chính sách không mất log.

Một kết quả như "1 triệu events/second" có thể chỉ đo tốc độ **đưa vào RAM**, không phải tốc độ ghi bền vững. Cấu hình async đặc biệt giỏi hấp thụ burst nhờ queue, nhưng với tải kéo dài cao hơn năng lực đích thì lợi thế đó cạn dần.

Để diễn giải throughput, cần luôn mô tả:

- Backend và phiên bản: JUL, Logback Classic, Log4j 2 Core và bridge/binding liên quan.
- Loại appender: console, FileAppender, RollingFileAppender, network, AsyncAppender hoặc đích tuỳ biến.
- Payload: một dòng text ngắn, JSON, MDC/ThreadContext, stack trace, kích thước Unicode.
- Số producer threads, số worker, số đích xuất và cấu hình fan-out.
- Khoảng đo, warm-up JVM, CPU quota, bộ nhớ, disk/network và tải collector.
- Chính sách khi queue đầy, thời điểm flush và định nghĩa chính xác của "đã ghi".

Không so sánh những benchmark chỉ đo Logger API với benchmark ghi file và fsync như thể chúng đo cùng một thao tác.

## 4. Công thức và chỉ số cơ bản

Dùng counter tăng đơn điệu tại từng chặng. Với hai thời điểm t0 và t1, độ dài cửa sổ là Δt giây:

~~~text
produced_rate  = (produced[t1]  - produced[t0])  / Δt
accepted_rate  = (accepted[t1]  - accepted[t0])  / Δt
processed_rate = (processed[t1] - processed[t0]) / Δt
discarded_rate = (discarded[t1] - discarded[t0]) / Δt

output_bytes_per_second = (bytes[t1] - bytes[t0]) / Δt
average_bytes_per_event = Δbytes / Δprocessed
~~~

Ví dụ 60.000 event được appender xử lý trong 10 giây nghĩa là processed rate trung bình 6.000 events/s. Nếu cùng thời gian có 30.000.000 byte được encode thì throughput dữ liệu là 3.000.000 bytes/s, chưa chắc là băng thông thực tế của ổ đĩa.

Lưu ý khi đặt counter:

1. **Produced** nên phản ánh event được yêu cầu phát, có thể gồm cả event bị level/filter bỏ.
2. **Accepted** chỉ tăng khi enqueue hoặc pipeline thực sự chấp nhận event.
3. **Processed** phải có điểm đo rõ ràng, ví dụ appender đã hoàn thành công việc publish/append theo implementation.
4. **Confirmed** chỉ tăng khi đích cung cấp xác nhận có ý nghĩa đã định; không tự suy ra fsync hoặc durability từ việc gọi write().
5. **Dropped** phải đếm được các event bị loại do queue/filter/sampling nếu chính sách cần giám sát; không gộp tất cả nguyên nhân làm một số rồi kết luận queue đầy.

Để biết **độ trễ**, đo riêng thời gian lời gọi logger trên caller thread và thời gian từ tạo event đến lúc đích tiếp nhận. Throughput cao không đồng nghĩa p95/p99 latency thấp.

## 5. Queue quyết định khả năng chịu burst, không tạo thêm năng lực sink

Đặt:

- λ = tốc độ event **thực sự enqueue** vào queue (event/s).
- μ = tốc độ worker lấy/hoàn tất event để làm giảm backlog (event/s).
- C = sức chứa queue (event).
- Q0 = số event đang chờ ban đầu.

Nếu tốc độ gần ổn định và λ lớn hơn μ:

~~~text
Q(t) ≈ Q0 + (λ - μ) × t
t_full ≈ (C - Q0) / (λ - μ)
~~~

Ví dụ C = 12.000, Q0 = 0, λ = 9.000/s và μ = 6.000/s, queue có thể đầy sau khoảng 4 giây. Tăng C lên 24.000 chỉ kéo dài tới khoảng 8 giây nếu nút thắt không đổi. Đây là mô hình gần đúng, chưa tính biến động tải, drop, chi phí mỗi event hoặc producer bị block.

Khi queue đầy:

- **Block/backpressure:** caller đợi để có chỗ, có thể tăng latency request và timeout.
- **Discard/drop:** loại sự kiện theo chính sách; con số accepted hoặc processed có thể đẹp vì đã mất một phần log.
- **Fallback:** ghi đồng bộ hoặc chuyển tới appender khác theo khả năng của framework; vẫn có chi phí và rủi ro lỗi.
- **Timeout/reject:** thao tác enqueue bị từ chối sau thời gian chờ.

Vì vậy muốn biết appender theo kịp tải, hãy nhìn **độ dốc backlog** khi hệ thống ở tải ổn định: nếu queue tiếp tục tăng lâu dài, accepted input lớn hơn khả năng drain. Queue gần trống trong điều kiện tải nhẹ cũng không chứng minh appender có throughput tối đa cao.

## 6. Các nút thắt làm throughput giảm

### 6.1. Output sink và I/O

- **Console/stdout:** có thể bị giới hạn bởi pipe của container, terminal, agent thu thập hoặc runtime. Việc in ra console mỗi event trong benchmark có thể gây sai lệch lớn.
- **File:** disk throughput, filesystem, file locking, file rotation, buffering, flush, quota và kích thước dữ liệu đều tác động.
- **Network/collector:** RTT, TLS, băng thông, số kết nối, retry, tốc độ index và khả năng nhận event của dịch vụ ở xa ảnh hưởng throughput cuối.
- **Database hoặc sink tùy chỉnh:** một transaction cho mỗi event có chi phí khác batch hoặc durable queue. Gộp batch cải thiện một số đường truyền nhưng tăng thời gian chờ và phức tạp khi lỗi.

Ghi vào page cache của hệ điều hành, flush stream, fsync lên thiết bị và nhận ACK bền vững từ hệ thống khác là **các ranh giới xác nhận khác nhau**. Đừng dùng giá trị cao ở ranh giới đầu để cam kết độ bền ở ranh giới cuối.

### 6.2. Layout, encoding và kích thước event

Appender có thể tốn nhiều CPU chỉ để format message, timestamp, JSON, MDC/ThreadContext, stack trace hoặc thông tin class/file/line của caller. Một event ERROR có stack trace dài rất khác một event INFO 80 byte.

Với SLF4J, code thường dùng tham số hóa:

~~~java
// Đoạn minh họa trong lớp đã khai báo biến log (SLF4J).
log.debug("Order {} state {}", orderId, state);
~~~

Cách này tránh nối chuỗi tường minh khi level tắt, nhưng các tham số tính toán đắt vẫn được đánh giá trước khi truyền vào method. Khi có chi phí thật, có thể kiểm tra trước:

~~~java
// buildDiagnosticState() là hàm ứng dụng, không thuộc SLF4J.
if (log.isDebugEnabled()) {
    log.debug("State: {}", buildDiagnosticState());
}
~~~

Hạn chế đưa object lớn hoặc dữ liệu nhạy cảm vào log; tránh lấy caller location khi không cần vì việc truy stack frame có thể tốn kém. Khi so benchmark, giữ tương đương pattern/JSON layout và kích thước message.

### 6.3. Contention, CPU, GC và số thread

Nếu nhiều producer cùng ghi vào một appender đồng bộ hoặc hàng đợi có lock, contention có thể giới hạn throughput. Với logging async, worker vẫn cần CPU, memory và có thể cạnh tranh tài nguyên với nghiệp vụ. Allocation của event, String, byte[] và exception làm tăng áp lực GC.

Thêm worker thread không mặc nhiên tăng tốc khi mọi worker đều ghi vào một file hoặc collector có cùng giới hạn băng thông. Cần profile CPU, blocking time, GC, disk và network để tìm điểm nghẽn trước khi tăng số thread.

### 6.4. Nhiều appender và additivity

Một event có thể được gửi tới console, file và remote sink. Với appender đồng bộ, một đích chậm có thể kéo dài thời gian gọi logger. Với nhiều đường xuất bất đồng bộ, mỗi đích có backlog/độ trễ riêng; throughput của FILE không tự chứng minh REMOTE đã lưu sự kiện.

Nếu logger con và logger cha gắn trùng appender trong khi **additivity=true**, event có thể bị ghi lặp, khiến số event/s và chi phí tăng ngoài ý muốn. Kiểm tra routing trước khi tối ưu.

## 7. Ví dụ Java 17+ chạy độc lập: đo tốc độ một Handler

Trong Java Core, java.util.logging (**JUL**) sử dụng **Handler** để xử lý và xuất log; nó tương đương vai trò khái niệm với appender ở các framework khác. Ví dụ này đo chi phí đi qua logger, tạo nội dung UTF-8 và cập nhật counter trên **Handler trong bộ nhớ**, tuyệt đối không coi số đo là throughput file/network production.

Tạo file **AppenderRateDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.concurrent.atomic.LongAdder;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class AppenderRateDemo {
    static final class MeteredHandler extends Handler {
        private final LongAdder written = new LongAdder();
        private final LongAdder utf8Bytes = new LongAdder();

        MeteredHandler() {
            setLevel(Level.ALL);
        }

        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record)) {
                return;
            }

            String line = record.getLevel().getName() + " "
                    + record.getMessage() + "\n";
            utf8Bytes.add(line.getBytes(StandardCharsets.UTF_8).length);
            written.increment();
        }

        @Override public void flush() {}
        @Override public void close() {}

        // Chỉ reset khi không có thread đang publish().
        void resetMetrics() {
            written.reset();
            utf8Bytes.reset();
        }

        long count() { return written.sum(); }
        long bytes() { return utf8Bytes.sum(); }
    }

    public static void main(String[] args) {
        Logger log = Logger.getLogger("demo.throughput");
        log.setLevel(Level.INFO);
        log.setUseParentHandlers(false);

        MeteredHandler handler = new MeteredHandler();
        log.addHandler(handler);
        try {
            // Khởi động JIT/JVM trước lượt đo chính.
            for (int i = 0; i < 10_000; i++) {
                log.info("warmup");
            }
            handler.resetMetrics();

            int attempted = 50_000;
            long start = System.nanoTime();
            for (int i = 0; i < attempted; i++) {
                log.info("event-" + i);
            }
            long elapsed = System.nanoTime() - start;

            long processed = handler.count();
            double seconds = elapsed / 1_000_000_000.0;

            System.out.println("attempted=" + attempted);
            System.out.println("processed=" + processed);
            System.out.println("matches=" + (processed == attempted));
            System.out.println("utf8Bytes=" + handler.bytes());
            System.out.printf(Locale.ROOT,
                    "rate=%.0f events/sec%n", processed / seconds);
        } finally {
            log.removeHandler(handler);
            handler.close();
        }
    }
}
~~~

Biên dịch/chạy bằng JDK 17 trở lên:

~~~bash
javac AppenderRateDemo.java
java AppenderRateDemo
~~~

Bốn dòng output đầu là xác định với mã trên:

~~~text
attempted=50000
processed=50000
matches=true
utf8Bytes=838890
~~~

Dòng thứ năm có dạng **rate=... events/sec**, phụ thuộc CPU, JIT, GC và môi trường. Một lượt chạy có thể cho:

~~~text
rate=2541089 events/sec
~~~

**Không lấy số rate mẫu này làm benchmark production.** Handler ở trên **không ghi dữ liệu ra đĩa hay mạng**; processed nghĩa là hàm publish() đã tính byte và tăng counter. Cấu hình setUseParentHandlers(false) tránh đưa mọi event lên console root. LongAdder hỗ trợ cập nhật đồng thời, nhưng resetMetrics() chỉ an toàn khi không có luồng đang ghi, như trong ví dụ một producer.

System.nanoTime() dùng để đo thời gian trôi qua. Warm-up 10.000 sự kiện được loại khỏi lượt đo, nhưng đây vẫn là **thử nghiệm một lần, một thread, in-memory**, chưa có benchmark thống kê. Muốn kiểm tra throughput thực tế của FileAppender, thay đích bằng sink thật, đo số byte/event tới sink, lỗi I/O, tình trạng flush, thời gian chờ và chạy nhiều lượt trên hạ tầng gần production.

## 8. Logback AsyncAppender và bài toán throughput

Logback Classic thường được dùng qua SLF4J. Một **AsyncAppender** có queue, worker đưa event từ queue tới appender thực như RollingFileAppender. Ví dụ **logback.xml**:

~~~xml
<configuration>
  <appender name="FILE"
            class="ch.qos.logback.core.rolling.RollingFileAppender">
    <file>logs/application.log</file>
    <rollingPolicy
        class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
      <fileNamePattern>logs/application.%d{yyyy-MM-dd}.log</fileNamePattern>
      <maxHistory>7</maxHistory>
    </rollingPolicy>
    <encoder>
      <charset>UTF-8</charset>
      <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
    </encoder>
  </appender>

  <appender name="ASYNC" class="ch.qos.logback.classic.AsyncAppender">
    <queueSize>8192</queueSize>
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

Ý nghĩa trong bài đo:

| Tham số | Tác động |
| --- | --- |
| queueSize | Dung lượng backlog/burst; tăng queue không tự làm FILE ghi nhanh hơn |
| discardingThreshold | Mức còn chỗ để bắt đầu loại các log level thấp; 0 tắt cơ chế loại sớm |
| neverBlock=false | Queue đầy có thể gây block caller thay vì chỉ bỏ event |
| maxFlushTime | Thời hạn đợi worker xả queue khi dừng; không tăng tốc độ ghi bền vững |
| FILE + encoder | Nơi tiêu thụ tài nguyên định dạng/file I/O thực |

Theo tài liệu Logback, mặc định AsyncAppender có thể loại TRACE, DEBUG và INFO khi queue còn khoảng 20% chỗ trống. Nếu đo throughput rồi phát hiện số event không khớp, đừng chỉ xem queue lúc chạm 100%; sự kiện có thể đã bị drop trước đó. Ngược lại, đặt discardingThreshold=0 và neverBlock=false có thể làm tăng latency của caller khi sink không theo kịp.

Ví dụ XML cần Logback dependency, quyền ghi thư mục logs, chính sách retention và shutdown phù hợp. Với log audit bắt buộc bền vững, AsyncAppender RAM không phải cơ chế lưu trữ duy nhất có thể tin cậy.

## 9. Log4j 2: Async Appender khác Async Logger

Log4j 2 Core cung cấp:

- **Async Appender:** bao quanh appender đích, dùng queue và worker riêng; có chi phí cạnh tranh khi nhiều producer.
- **Async Logger:** dựa trên LMAX Disruptor/ring buffer ở tầng logger; có thể đạt tính năng hiệu năng khác nhưng phụ thuộc workload.

Ví dụ **log4j2.xml** dùng Async Appender:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
  <Appenders>
    <File name="FILE" fileName="logs/application.log">
      <PatternLayout pattern="%d{ISO8601} %-5p %c - %m%n"/>
    </File>
    <Async name="ASYNC" bufferSize="8192"
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

Với Log4j 2, **bufferSize** là dung lượng queue của Async Appender. Chính sách khi queue đầy phụ thuộc cấu hình và **log4j2.asyncQueueFullPolicy**; Default thường ưu tiên chờ, trong khi Discard có thể bỏ các sự kiện theo mức **log4j2.discardThreshold**. Không đọc cấu hình Logback như neverBlock/discardingThreshold rồi áp trực tiếp sang Log4j 2.

Log4j 2 mô tả async logging hữu ích khi có burst và khi muốn rút ngắn thời gian lời gọi logger trên luồng ứng dụng. Tuy nhiên, nếu tốc độ log kéo dài nhanh hơn appender đích, queue đầy và lợi thế giảm độ trễ sẽ biến mất. Backend này cũng khuyến nghị đo trên ứng dụng thực để chọn sync/async.

**Không xếp Async Appender lên Async Logger chỉ vì muốn số events/s lớn hơn.** Hai hàng đợi có thể tăng memory, latency và độ khó phân tích lỗi, trong khi file/network sink vẫn là điểm giới hạn. Nếu cần kết hợp, phải đo trạng thái và độ hoàn tất ở từng tầng.

## 10. So sánh logging đồng bộ với bất đồng bộ

| Góc nhìn | Đồng bộ | Bất đồng bộ |
| --- | --- | --- |
| Logger call latency | Có thể chịu encode/I/O trực tiếp | Thường chủ yếu tạo/enqueue event |
| Xử lý burst ngắn | Có thể gây chậm caller ngay | Queue có thể hấp thụ một phần |
| Throughput bền vững tới sink | Giới hạn bởi sink và overhead | Vẫn giới hạn bởi sink, overhead có thể khác |
| Quá tải kéo dài | Caller chậm theo sink | Backlog tăng rồi block/drop/fallback |
| Phát hiện lỗi sink | Gần luồng gọi hơn trong một số backend | Có thể xuất hiện sau trên worker |
| Shutdown/crash | Cần hiểu buffer/flush | Cần xả queue đang ở RAM trước khi dừng |

Một bài đo công bằng phải giữ nguyên **payload, logger level, encoder, disk/network, CPU quota, số producer, thời lượng và chính sách xử lý đầy queue**. So sánh latency của logger.info với throughput sink là hai phép đo khác nhau.

## 11. Thiết kế benchmark đúng

### 11.1. Đặt câu hỏi cụ thể

Ví dụ: “Ở 8 thread nghiệp vụ, mỗi log JSON trung bình 800 byte, appender FILE có thể ghi bền vững bao nhiêu event/s mà không drop, backlog không tăng mãi và p99 latency của request nằm trong ngưỡng?”.

Cần ghi rõ “ghi xong” nghĩa là append() trả về, file có thể đọc, fsync hay collector đã xác nhận. Các mức xác nhận này khác nhau. Chỉ đặt một con số mục tiêu nếu nó phục vụ SLO thực.

### 11.2. Tạo workload đại diện

- Thử các mức INFO, WARN, ERROR; message ngắn/dài; stack trace; JSON; Unicode và MDC.
- Thử 1, 4, 8, 16 producer threads; giữ quy tắc tạo event nhất quán.
- Bật/tắt caller location chỉ khi đã xác định yêu cầu và đo tác động.
- Warm-up JVM/JIT và sink; chạy nhiều lượt đo đủ dài; báo kết quả có biến thiên (median, percentiles) thay vì một giá trị may mắn.
- Tách **microbenchmark logger/layout** khỏi **integration benchmark file/network**. Dùng JMH cho microbenchmark khi cần đánh giá nghiêm túc, và load test end-to-end để kiểm tra đích thật.
- Gắn testRunId và sequence number, đợi queue drain/flush rồi đối chiếu event đã tới sink. Khi collector index chậm, đừng vội kết luận mất log.
- Giữ cố định nền hạ tầng: phiên bản backend, CPU limit, heap, disk, rotation, network, collector và môi trường container.

### 11.3. Theo dõi cả tốc độ, chất lượng và tài nguyên

| Metric | Vì sao cần? |
| --- | --- |
| Producer/accepted/processed events/s | Biết throughput ở từng chặng |
| Output bytes/s | Phân biệt tốc độ event với kích thước message |
| Queue size / capacity / oldest age | Biết backlog có tăng hay không |
| Dropped / rejected / appender errors | Phát hiện mất log, filter hoặc lỗi I/O |
| Caller latency p50/p95/p99 | Đo tác động đến nghiệp vụ |
| End-to-end lag tới sink | Đo mức trễ quan sát log |
| CPU, heap, allocations, GC pauses | Tìm nghẽn tính toán và cấp phát |
| Disk/network throughput, flush/ACK | Tìm nghẽn hạ tầng |
| Drain time khi shutdown | Biết có xả kịp queue trước khi dừng |

Đừng dùng COUNT(*) trên toàn bộ log khi có retry, duplicate, sampling hoặc collector lag để suy ra số event duy nhất đã ghi. Đối chiếu theo event ID/test ID và định nghĩa rõ các trường hợp loại có chủ đích.

## 12. Cách tìm throughput bền vững bằng load test

Một quy trình dễ tái lập:

1. **Baseline:** chạy ở tải thấp, queue gần trống; xác nhận log đúng định dạng và đúng số lượng.
2. **Tăng theo bậc:** nâng producer rate hoặc số thread qua các mức rõ ràng, mỗi bậc giữ đủ lâu.
3. **Quan sát backlog:** nếu kích thước queue tăng liên tục, accepted input vượt tốc độ drain tại mức tải đó.
4. **Kiểm tra SLO:** tỷ lệ drop, lỗi sink, độ trễ p99, CPU/GC và end-to-end lag có đạt ngưỡng?
5. **Lấy bậc cuối đạt tiêu chí:** đó là một ước lượng sustainable throughput trong điều kiện thử, không phải hằng số bất biến của framework.
6. **Thử burst và phục hồi:** tạo spike ngắn, sau đó giảm tải; đo thời gian queue về bình thường.
7. **Thử tình huống khó:** file rotation, collector chậm, disk gần đầy, network timeout, graceful shutdown/restart.

Nếu chỉ chạy một vòng lặp ghi 50.000 event trong một giây rồi dừng, có thể vô tình chỉ đo tốc độ enqueue hoặc cache. Tải kéo dài mới thể hiện giới hạn của appender và sink.

## 13. Tối ưu throughput theo nguyên nhân

### 13.1. Giảm số lượng event không cần

Chọn logger level cho từng package, tránh log trùng và log trong vòng lặp nóng; cân nhắc sampling/rate limiting cho sự kiện chẩn đoán được phép bỏ. Với log audit, thanh toán hoặc dữ liệu bắt buộc lưu, **không dùng sampling hoặc queue logging RAM làm bảo đảm lưu bền vững**.

### 13.2. Giảm chi phí mỗi event

Đơn giản hóa layout khi có thể, tránh stack trace lặp liên tục, caller file/line không cần thiết và payload quá lớn. Ưu tiên log có cấu trúc cho các thuộc tính cần truy vấn, nhưng hãy đo đúng encoder đang dùng. Đừng ghi token, mật khẩu hoặc dữ liệu cá nhân không cần thiết để thử throughput.

### 13.3. Tăng năng lực sink

Nếu disk bão hòa, tối ưu đường ghi, thiết bị và rotation. Nếu collector bị giới hạn bởi ACK hoặc network, tăng khả năng nhận hoặc dùng buffering/batching theo khả năng thực tế, có kiểm tra retry và độ bền. Nếu CPU encode là nút thắt, tối ưu formatter và tài nguyên. Không tăng worker một cách mù quáng khi tất cả dùng một đích chậm.

### 13.4. Chọn async đúng trường hợp

Dùng async khi cần giảm caller latency hoặc hấp thụ burst và đã đánh giá queue-full policy. Tăng queue để chịu đỉnh ngắn có thể hợp lý, nhưng nó tăng memory, độ trễ xuất log và thời gian flush. Nếu input cao hơn sink dài hạn, giải pháp là giảm input, tăng năng lực đích hoặc chấp nhận policy block/drop rõ ràng.

## 14. Các nhầm lẫn phổ biến

**“logger.info gọi nhanh tức appender nhanh.”** Với async, lời gọi có thể chỉ enqueue. Hãy đo consumer và sink.

**“Queue lớn làm throughput bền vững cao hơn.”** Queue cho thêm thời gian chịu burst, không tăng tốc file/network.

**“Không có lỗi nghĩa là không mất log.”** Có thể drop theo level/filter, queue-full policy, collector lỗi hoặc dữ liệu chưa được flush. Cũng có framework không cung cấp sẵn dropped counter.

**“Thêm thread worker luôn tăng throughput.”** Nếu một file/collector là nút thắt, tăng thread có thể làm tăng contention và overhead.

**“Mọi event đều tốn chi phí như nhau.”** Stack trace/JSON lớn có bytes/s và CPU encode rất khác log text nhỏ.

**“Log đã được enqueue là đã lưu an toàn.”** Event trong RAM vẫn có thể mất khi process chết, queue chưa drain hoặc sink lỗi. Với audit bắt buộc phải bền vững, dùng kho/transaction/outbox hoặc cơ chế chuyên dụng có bảo đảm tương xứng.

**“Số dòng dashboard bằng số event thực tế.”** Ingest delay, retry, duplicate, multiline, filter và cửa sổ truy vấn có thể làm lệch số. Cần định danh sự kiện để đối chiếu.

**“Benchmark của một máy dev đủ chọn cấu hình production.”** CPU quota, disk, collector, network, rotation và tải cạnh tranh trên production khác đáng kể. Đo trong môi trường gần thực tế.

## 15. Checklist nghiệm thu một phép đo appender

- [ ] Xác định rõ **throughput tại logger, queue, appender hay sink**.
- [ ] Có cả events/s, bytes/s và phân bố kích thước payload.
- [ ] Đã xác nhận logger level/filter để không đếm nhầm event bị bỏ.
- [ ] Có đo caller latency, end-to-end lag, CPU/GC và queue backlog.
- [ ] Biết backend/version, appender, encoder, chính sách full queue và thời gian shutdown.
- [ ] Có thử burst, tải dài, nhiều producer, payload lớn, rotation và sink chậm.
- [ ] Đã đối chiếu testRunId/sequence ID ở đích sau khi drain/flush.
- [ ] Không dùng throughput enqueue để cam kết dữ liệu đã lưu bền vững.
- [ ] Đã tìm bottleneck bằng metric/profiling trước khi đổi số thread hoặc queue size.
- [ ] Đã tách log bắt buộc lưu khỏi các chính sách discard/sampling không phù hợp.

**Ghi nhớ:** Throughput của appender là **tốc độ xử lý log tại một chặng xác định**. Để tối ưu hiệu năng logging Java có trách nhiệm, hãy đo cả tốc độ producer, năng lực drain của appender, độ hoàn tất tại sink, backlog, độ trễ và tỷ lệ mất sự kiện. Bộ đệm async giúp vượt qua burst; năng lực ghi bền vững dài hạn phụ thuộc vào đường xử lý và đích thực tế.

## Tài liệu tham khảo

- [Apache Log4j 2 — Performance](https://logging.apache.org/log4j/2.x/manual/performance.html): chi phí layout, location information, allocation và async.
- [Apache Log4j 2 — Asynchronous Loggers](https://logging.apache.org/log4j/2.x/manual/async.html): burst, sustainable throughput, queue-full policy và wait strategy.
- [Apache Log4j 2 — Delegating Appenders](https://logging.apache.org/log4j/2.x/manual/appenders/delegating.html): Async Appender, blocking queue và fallback.
- [Logback Manual — AsyncAppender](https://logback.qos.ch/manual/appenders-async-sift.html): queueSize, discardingThreshold, neverBlock và maxFlushTime.
- [Oracle Java SE 17 — java.util.logging.Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html): xử lý LogRecord bằng Handler.
- [OpenJDK JMH project](https://github.com/openjdk/jmh): công cụ microbenchmark Java; dùng kết hợp với load test thực tế.
