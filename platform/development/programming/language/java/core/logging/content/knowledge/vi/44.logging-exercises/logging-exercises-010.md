# Đo hiệu năng Java Logging — dự án thực hành từ JDK 17 tới pipeline production

## 1. Mục tiêu và sản phẩm cuối

Khi phát triển Java service, logging có thể làm tốn thời gian CPU, sinh nhiều đối tượng trung gian, tăng GC, gây chặn I/O hoặc đưa event vào hàng đợi bất đồng bộ. Đồng thời, không thể chỉ xóa logs để có kết quả benchmark đẹp: chúng phục vụ điều tra sự cố, giám sát và đôi khi là audit bắt buộc.

Bài **Đo hiệu năng** thuộc **Dự án thực hành Java Core Logging** nhằm xây dựng một phép đo có thể chạy được, kết quả có giới hạn rõ ràng, rồi mở rộng thành phương pháp đánh giá logging trong production.

Sau bài này, người học có thể:

- Phân biệt chi phí **dựng message**, **kiểm level**, **tạo log event**, **format**, **ghi file**, **queue** và **transport**.
- Chạy một chương trình Java 17 độc lập so sánh năm chế độ logging.
- Áp dụng warm-up, nhiều trial và median mà không nhầm kết quả với một benchmark JMH chuẩn.
- Kiểm tra số sự kiện thực sự được ghi, thay vì tuyên bố throughput cao nhờ làm mất event.
- Đọc throughput, latency p95/p99, allocation, GC, disk usage, queue depth và ingestion lag.
- Thiết kế thí nghiệm cho SLF4J/Logback, MDC, JSON encoder, AsyncAppender và agent/collector.
- Xây performance budget, báo cáo kết quả có thể tái lập và nêu trade-offs giữa hiệu năng, privacy và reliability.

**Nguyên tắc:** kết luận chỉ có giá trị với workload, hệ thống và ranh giới đã đo; một số nanosecond từ vòng lặp nhỏ không mô tả toàn bộ chi phí của pipeline logs trong production.

## 2. Mỗi lời gọi logger gồm những chi phí nào?

~~~text
Application business logic
          |
          v
Check effective logging level
          |
          v
Evaluate arguments / create message
          |
          v
Build LogRecord / ILoggingEvent
          |
          v
Capture MDC and exception context
          |
          v
Serialize text / structured JSON
          |
          +------ synchronous appender ------+
          |                                  |
          +------ async queue + worker ------+
                                             |
                                             v
                                     stdout / file
                                             |
                                             v
                                      host agent
                                             |
                                             v
                                    collector / index
~~~

Một phép đo cần chọn rõ boundary:

| Boundary | Đã đo những gì? | Chưa chứng minh |
| --- | --- | --- |
| Java logger call | Thời gian lời gọi trên caller thread | Backend lưu event |
| Appender/memory handler | Provider tạo event và gọi handler | JSON/file/network có hoạt động |
| Local file | Bytes được ghi/flush theo semantics file handler | Disk durable qua mất điện hoặc collector đã ingest |
| Async enqueue | Caller đưa event vào queue | Queue đã drain hoặc không drop |
| Collector ACK | Server nhận theo protocol | Có thể chưa search được |
| Backend query | Có event được ingest/search | Không tự chứng minh completeness trong mọi trường hợp |

**Không lấy thời gian logger.info() return của async appender làm thời gian toàn tuyến.** App có thể enqueue rất nhanh nhưng hàng đợi tăng, disk đầy hoặc collector bỏ event.

## 3. Các chỉ số phải thu đúng đơn vị

| Chỉ số | Ý nghĩa | Rủi ro diễn giải |
| --- | --- | --- |
| operations/s | Số thao tác benchmark hoàn thành mỗi giây | Không tự bằng log records/s |
| log records/s | Số events thực sự được xử lý trong một stage | Có thể chưa tới storage |
| elapsed ms | Thời gian một trial | Nhiễu JIT/GC/scheduler |
| p50, p95, p99 | Phân vị độ trễ các operations/requests | Không phải median của trial durations |
| CPU utilization | Tài nguyên CPU của app/agent | Chờ I/O có thể chậm nhưng CPU thấp |
| allocation MB/s | Tốc độ cấp phát object | Có thể ảnh hưởng GC và latency |
| GC pause | Thời gian stop-the-world hoặc hoạt động GC liên quan | GC trùng lúc không phải luôn là root cause |
| bytes/s | Dữ liệu file/stdout/network | Bị ảnh hưởng bởi encoding/compression |
| queue depth | Backlog async | Queue rỗng không chứng minh remote storage |
| drop count | Event bị bỏ có chủ đích hoặc do quá tải | Throughput cao vì drop là kết quả không đạt |
| ingestion lag | Thời gian event sinh → backend truy vấn được | Phụ thuộc batching và index refresh |

Một báo cáo phải ghi **scope**, **mẫu số** và **định nghĩa sự kiện**. Chẳng hạn 10.000 calls/s với DEBUG disabled không bằng 10.000 INFO records/s tới JSON file.

## 4. Lập performance budget trước khi tối ưu

Không đo vì tò mò con số cao nhất. Hãy ghi tiêu chí hệ thống:

- Logging đề xuất được phép làm tăng **p99 latency** tối đa bao nhiêu theo SLO?
- Mỗi request ở mức tải bình thường tạo bao nhiêu event ở INFO/WARN/ERROR?
- Khi dependency lỗi và tạo nhiều stack traces, log volume tăng bao nhiêu?
- Diagnostic logs có thể sampling/drop theo policy nào; alert có counter về dropped events không?
- Audit/tuân thủ có yêu cầu bền vững và không được drop hay không?
- Disk quota, agent spool, network throughput và retention có giới hạn gì?
- Nếu collector không phản hồi trong 5 phút, app sẽ block hay vẫn phục vụ request?
- Có yêu cầu field privacy-sensitive không được rời application không?

Ví dụ một mẫu kế hoạch:

~~~yaml
experiment: java-logging-performance
baseline: "same business workload, same host configuration"
candidate: "one logging change at a time"
primarySli: "request p99 latency"
secondary:
  - "throughput"
  - "allocation bytes/operation"
  - "GC pauses"
  - "log records delivered"
  - "agent queue depth"
gates:
  - "required logs complete according to contract"
  - "synthetic secrets absent from every tested sink"
  - "performance regression within approved budget"
~~~

YAML này là mẫu **tài liệu đo**, không phải một cấu hình Java/Logback tự thực thi. Ngưỡng nghiệm thu phải do người quản lý SLO và dữ liệu baseline thực tế xác nhận, không đặt một mức cố định cho mọi service.

## 5. Ma trận thực nghiệm Java 17 ban đầu

Bắt đầu với một chương trình đơn luồng, input synthetic và logger riêng:

| Mode | Hoạt động | Mục đích |
| --- | --- | --- |
| BASELINE | Vòng lặp + checksum, không gọi logger | Đo workload tối thiểu |
| DISABLED_EAGER | Dựng message rồi gọi JUL logger ở FINE bị tắt | Thấy chi phí argument evaluation dù log không phát |
| DISABLED_GUARDED | isLoggable(FINE) trước khi dựng message | Kiểm lợi ích guard cho message đắt |
| ENABLED_MEMORY | INFO + handler chỉ đếm LogRecord | Tách chi phí provider khỏi file/JSON |
| ENABLED_FILE | INFO + FileHandler + UTF-8 line formatter | Khảo sát chi phí file output |

**Các chế độ không có công việc giống hệt nhau**: BASELINE không tạo message, memory handler không format JSON, FILE thực hiện disk I/O; điều này có chủ đích để tách tầng. Muốn so hai frameworks hoặc hai appenders một cách công bằng, cần giữ **cùng số events, cùng payload, formatter và sink**.

Benchmark đầu tiên dùng 20.000 operations cho bốn mode đầu và 2.000 cho file để tránh gây tải disk quá mức trong bài lab. Không so trực tiếp medianMs giữa hai mode có N khác nhau; ops/s chỉ là chỉ báo sơ bộ.

## 6. Yêu cầu môi trường và cách chạy

Chỉ cần **JDK 17 trở lên**, có javac và java trên PATH. Chương trình dùng java.util.logging (JUL) đi kèm JDK, không cần Maven hoặc internet.

Trước khi chạy, ghi lại:

~~~bash
java -version
javac -version
~~~

Nên chọn máy ít workload nền; ghi OS, CPU, RAM, JDK vendor, heap flags và loại filesystem. Trên Windows, antivirus/file indexing có thể ảnh hưởng file I/O; trên container, CPU quota, memory limits và ephemeral storage có thể làm biến đổi số liệu.

**Không dùng dữ liệu người dùng thật hoặc token production.** Tất cả requestId trong lab đều là chuỗi synthetic; output nằm trong file tạm do chương trình xóa sau khi kiểm tra.

## 7. Chương trình thực hành: LoggingPerformanceLab.java

Ví dụ sau dùng **JUL Logger + Handler + FileHandler**. Mỗi chế độ được warm-up 2 lượt, đo 5 lượt, sắp xếp durations và lấy median. Số event được kiểm sau mỗi lượt; với file output, chương trình xác minh có đúng N dòng và bytes dương sau khi đóng handler.

Tạo file **LoggingPerformanceLab.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.Locale;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.stream.Stream;

public final class LoggingPerformanceLab {
    enum Mode {
        BASELINE,
        DISABLED_EAGER,
        DISABLED_GUARDED,
        ENABLED_MEMORY,
        ENABLED_FILE
    }

    private static final int RECORDS = 20_000;
    private static final int FILE_RECORDS = 2_000;
    private static final int WARMUP_ROUNDS = 2;
    private static final int MEASURE_ROUNDS = 5;
    private static volatile long blackhole;

    private record Measurement(long nanos, long events, long bytes) {}

    private static final class CountingHandler extends Handler {
        long count;

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                count++;
            }
        }

        @Override public void flush() {}
        @Override public void close() {}
    }

    private static final class PlainLineFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            return record.getMessage() + "\n";
        }
    }

    private static String makeMessage(int value) {
        return "event=work_done requestId=req-"
                + (value & 1023) + " value=" + value;
    }

    private static Measurement runOnce(Mode mode, int n)
            throws Exception {
        Logger logger = Logger.getLogger("perf.lab." + mode.name());
        logger.setUseParentHandlers(false);

        boolean disabled = mode == Mode.DISABLED_EAGER
                || mode == Mode.DISABLED_GUARDED;
        logger.setLevel(disabled ? Level.WARNING : Level.INFO);

        Handler handler = null;
        CountingHandler counting = null;
        Path file = null;

        try {
            if (mode == Mode.ENABLED_MEMORY) {
                counting = new CountingHandler();
                counting.setLevel(Level.ALL);
                handler = counting;
                logger.addHandler(handler);
            } else if (mode == Mode.ENABLED_FILE) {
                file = Files.createTempFile("log-perf-", ".log");
                FileHandler output =
                        new FileHandler(file.toString(), false);
                output.setEncoding(StandardCharsets.UTF_8.name());
                output.setFormatter(new PlainLineFormatter());
                output.setLevel(Level.ALL);
                handler = output;
                logger.addHandler(handler);
            }

            long checksum = 0L;
            long start = System.nanoTime();
            for (int i = 0; i < n; i++) {
                checksum += (i & 1023);

                switch (mode) {
                    case BASELINE -> {
                        // Chi phi vong lap chung, khong ghi log.
                    }
                    case DISABLED_EAGER ->
                            logger.fine(makeMessage(i));
                    case DISABLED_GUARDED -> {
                        if (logger.isLoggable(Level.FINE)) {
                            logger.fine(makeMessage(i));
                        }
                    }
                    case ENABLED_MEMORY, ENABLED_FILE ->
                            logger.info(makeMessage(i));
                }
            }

            if (handler != null) {
                handler.flush();
            }
            long nanos = System.nanoTime() - start;
            blackhole = checksum;

            long events = counting == null ? 0L : counting.count;
            long bytes = 0L;

            if (mode == Mode.ENABLED_FILE) {
                logger.removeHandler(handler);
                handler.close();
                handler = null;

                bytes = Files.size(file);
                try (Stream<String> lines =
                             Files.lines(file, StandardCharsets.UTF_8)) {
                    events = lines.count();
                }
            }

            if ((mode == Mode.ENABLED_MEMORY
                    || mode == Mode.ENABLED_FILE) && events != n) {
                throw new IllegalStateException(
                        "Record count mismatch: " + events);
            }
            if (mode == Mode.ENABLED_FILE && bytes == 0L) {
                throw new IllegalStateException("Empty output file");
            }
            if ((mode == Mode.BASELINE || disabled) && events != 0L) {
                throw new IllegalStateException(
                        "Unexpected event from disabled logger");
            }
            return new Measurement(nanos, events, bytes);
        } finally {
            if (handler != null) {
                logger.removeHandler(handler);
                handler.close();
            }
            if (file != null) {
                Files.deleteIfExists(file);
            }
        }
    }

    private static void benchmark(Mode mode) throws Exception {
        int n = mode == Mode.ENABLED_FILE
                ? FILE_RECORDS : RECORDS;

        for (int i = 0; i < WARMUP_ROUNDS; i++) {
            runOnce(mode, n);
        }

        long[] times = new long[MEASURE_ROUNDS];
        Measurement last = null;
        for (int i = 0; i < MEASURE_ROUNDS; i++) {
            last = runOnce(mode, n);
            times[i] = last.nanos();
        }
        Arrays.sort(times);
        long median = times[MEASURE_ROUNDS / 2];
        double ms = median / 1_000_000.0;
        double throughput = n * 1_000_000_000.0
                / Math.max(1L, median);

        System.out.printf(Locale.ROOT,
                "mode=%s ops=%d medianMs=%.3f "
                + "opsPerSec=%.1f events=%d bytes=%d%n",
                mode.name(), n, ms, throughput,
                last.events(), last.bytes());
    }

    public static void main(String[] args) throws Exception {
        for (Mode mode : Mode.values()) {
            benchmark(mode);
        }
        System.out.println("sanity=PASS");
    }
}
~~~

Lệnh chạy:

~~~bash
javac LoggingPerformanceLab.java
java LoggingPerformanceLab
~~~

**Đặc điểm stdout:** Nếu tất cả kiểm tra thành công, chương trình in **6 dòng**: năm dòng mode theo thứ tự enum và một dòng **sanity=PASS**. Dưới đây là **mẫu cấu trúc output, KHÔNG phải số đo thật**. Các dấu ba chấm là vị trí giá trị sẽ thay đổi theo máy và môi trường.

~~~text
mode=BASELINE ops=20000 medianMs=... opsPerSec=... events=0 bytes=0
mode=DISABLED_EAGER ops=20000 medianMs=... opsPerSec=... events=0 bytes=0
mode=DISABLED_GUARDED ops=20000 medianMs=... opsPerSec=... events=0 bytes=0
mode=ENABLED_MEMORY ops=20000 medianMs=... opsPerSec=... events=20000 bytes=0
mode=ENABLED_FILE ops=2000 medianMs=... opsPerSec=... events=2000 bytes=...
sanity=PASS
~~~

Đây không phải bài yêu cầu stdout có thời gian cố định: **System.nanoTime, disk I/O và JIT làm các con số khác nhau**. Dòng sanity chỉ xác minh các invariants trong lab, không xác nhận tất cả records được collector lưu.

### Cách chương trình hoạt động

1. **BASELINE** vẫn cộng checksum, tránh vùng thử nghiệm hoàn toàn rỗng.
2. **DISABLED_EAGER** dựng message trước khi JUL kiểm level; FINE bị lọc vì level WARNING.
3. **DISABLED_GUARDED** kiểm isLoggable(FINE) trước, nên bỏ phần dựng message khi bị disable.
4. **ENABLED_MEMORY** tạo LogRecord, handler chỉ đếm; không định dạng JSON, không I/O.
5. **ENABLED_FILE** dùng custom PlainLineFormatter và UTF-8, ghi file tạm; sau khi flush và close, đọc số dòng để đảm bảo đúng N.
6. Thời gian mở FileHandler nằm **ngoài** vùng đo; thời gian phát event và flush nằm **trong** vùng đo; thời gian kiểm file và xóa file nằm **ngoài** vùng đo.
7. CountingHandler không đồng bộ cho nhiều threads; chương trình **chỉ đo tuần tự**. Không dùng handler này trong production hoặc benchmark concurrency.
8. Biến **blackhole** là một volatile field giúp giữ checksum có hiệu ứng quan sát được; nó không thay JMH Blackhole.
9. Chi phí allocation/GC không được in trực tiếp; cần JFR, profiler hoặc JMH có plugin phù hợp.
10. Chạy lại vài lần, giữ output thật. Không báo một số phần trăm cải thiện nếu chưa kiểm nhiễu và fairness.

## 8. Cách đọc kết quả từng mode

Không chỉ tìm dòng có opsPerSec cao nhất:

| Mode | Đọc số liệu thế nào? |
| --- | --- |
| BASELINE | Đặt mức nền của vòng lặp, không phải cost đầy đủ business code |
| DISABLED_EAGER | Thấy overhead khi vẫn tạo chuỗi dù FINE off |
| DISABLED_GUARDED | Có thể giảm cost dựng message khi FINE off |
| ENABLED_MEMORY | Chi phí logger/provider + handler cực nhẹ |
| ENABLED_FILE | Bao gồm formatter và local file I/O, thường biến động theo disk/cache |

**Không so trực tiếp medianMs của ENABLED_FILE (2.000 ops) với ENABLED_MEMORY (20.000 ops)**. Dù opsPerSec đã chuẩn hóa theo N, hai paths còn khác nhau về định dạng, sink và flush, nên đây chỉ là khảo sát.

Để so sánh appender A/B thật, chạy hai configurations với:

- N giống nhau.
- Payload/message fields và độ dài tương đương.
- Cùng JVM flags và hardware.
- Cùng level mix, error/stacktrace ratio.
- Cùng sync/async hoặc biết rõ tác động khác biệt.
- Cùng định nghĩa event accepted/delivered.

**Không tuyên bố “A nhanh hơn B X%” nếu workloads khác nhau.**

## 9. Kiểm tra correctness trước performance

Một benchmark có thể nhanh nhờ bỏ mất công việc. Bởi vậy cần:

- Sự kiện INFO được counting handler/file nhận đúng số lượng.
- Disabled FINE không lọt ra ngoài khi logger level WARNING.
- Không có root console handler in dữ liệu phụ làm sai thời gian.
- File appender được đóng trước khi đếm dòng.
- Kết quả so sánh không chứa stdout bên trong timed loop.
- Không có random inputs hoặc system clock trong message làm output khó tái lập.
- Các tài nguyên file/handler được cleanup ngay cả khi exception.
- Không có dữ liệu khách hàng hoặc token thật trong payload.
- Nếu mở rộng multi-thread: counter/thread-safety phải đúng.
- Không gắn nhãn “durable” cho bytes chỉ mới flush tới cache.

**Số sự kiện quan sát được phải là một phần của kết quả**, không chỉ time. Với async logging, số enqueue và số drained phải được báo riêng.

## 10. Warm-up, JIT và tối ưu hóa JVM

Java HotSpot thường compile/tối ưu code sau khi đã chạy đủ; những lần đầu có thể khác rõ so với steady state.

Những nguyên nhân nhiễu:

| Hiện tượng | Ảnh hưởng |
| --- | --- |
| JIT compile giữa trial | Kết quả warmup/measurement khác nhau |
| Dead-code elimination | Workload không còn tính toán như tưởng |
| Constant folding | Input quá cố định làm benchmark quá dễ |
| Escape analysis | Allocation khác code thực |
| GC và safepoints | Tạo spikes elapsed time |
| CPU turbo/thermal scaling | Trial chạy nhanh/chậm theo nhiệt |
| Disk page cache | File writes chưa phản ánh persistent media |
| Background tasks | Scheduler/I/O contention |

Trong lab có **2 warm-up rounds và 5 measurement rounds** rồi lấy median. Đó là thói quen tốt ban đầu nhưng **không bảo đảm kết quả có độ tin cậy thống kê cao**.

Khi quan sát chi phí isLoggable rất nhỏ, dùng **JMH** và nhiều JVM forks. Không lấy một vòng lặp System.nanoTime rồi khẳng định call chỉ tốn số nanosecond chính xác.

## 11. Khi nào nên dùng JMH?

JMH (Java Microbenchmark Harness) dành cho các phần rất nhỏ của JVM mà đo thủ công dễ sai:

- Check level và log disabled.
- Parameterized logging versus eager string concatenation.
- MDC.get/put/copy map chi phí.
- Cost JSON formatting và structured argument serialization.
- Một logging wrapper với giả lập sink nhất quán.
- Throwable stacktrace formatting.
- Allocation rate per operation.

Ví dụ một đoạn mã cho project có JMH dependencies:

~~~java
@State(Scope.Thread)
public class LogCallBench {
    private final org.slf4j.Logger logger =
            org.slf4j.LoggerFactory.getLogger("bench");

    private int value = 42;

    @Benchmark
    public void disabledDebugGuard() {
        if (logger.isDebugEnabled()) {
            logger.debug("value={}", value);
        }
    }
}
~~~

**Đây là snippet JMH tích hợp**, không phải chương trình độc lập: cần imports org.openjdk.jmh.annotations, JMH runner, SLF4J và backend/config. Đặc biệt phải **xác minh DEBUG thực sự disabled** trên logger được dùng.

Khi triển khai JMH, cấu hình warmup, measurement, forks, mode và profiler phù hợp; sử dụng JMH Blackhole hoặc benchmark state để tránh JVM loại công việc. Với benchmark có file/network, hãy giải thích riêng phần overhead vì đó không còn là thí nghiệm CPU-only nanosecond đơn giản.

**JMH throughput của một logger call không trực tiếp bằng p99 latency của request HTTP.** Hai câu hỏi cần hai kiểu test khác nhau.

## 12. Disabled level vẫn có thể tốn CPU và memory

Trong Java, arguments được tính trước khi gọi method:

~~~java
logger.debug("requestSummary={}", expensiveSerialize(request));
~~~

Đoạn trên dùng SLF4J, không phải JUL. Nếu DEBUG bị tắt, provider có thể không format ra chuỗi, nhưng **expensiveSerialize(request) vẫn đã chạy** để tạo argument.

Cách guard:

~~~java
if (logger.isDebugEnabled()) {
    logger.debug("requestSummary={}", expensiveSerialize(request));
}
~~~

**Cả hai chỉ là snippet minh họa tích hợp**. Không áp dụng vào raw request chứa PII ở production. Với argument rẻ, thêm guard có thể không cải thiện đáng kể và làm code phức tạp; nên đo khi argument có cost thật.

Cũng cần phân biệt:

- Dựng String bằng concatenation bên ngoài logger.
- Truyền object trong parameterized API để backend định dạng khi enabled.
- Tạo object/array parameters dù level disabled.
- Truyền supplier/lazy argument nếu API/version hỗ trợ.
- Serialization của record, DTO hoặc JSON lớn ngay trước logger call.

**Parameterized logging là công cụ hiệu năng, không phải redaction.** Dù dùng placeholder, dữ liệu nhạy cảm vẫn có thể bị xuất khi level bật.

## 13. Đo đúng Logback/SLF4J và không suy từ JUL

Program ở mục 7 dùng JUL. Nếu dự án thực tế dùng SLF4J + Logback hoặc Log4j 2, phải thực hiện benchmark riêng với đúng backend:

| Backend/stack | Các yếu tố nên đo |
| --- | --- |
| JUL | LogRecord, Handler, Formatter, FileHandler |
| SLF4J facade | Cost API và cách bind provider |
| Logback | ILoggingEvent, PatternLayout, MDC snapshot, appenders |
| Log4j 2 | Layout, message types, ThreadContext, async logger/appender |
| OpenTelemetry | SDK/Exporter/BatchProcessor, OTLP, Collector |
| Agent gateway | Parse, batch, compress, buffer, TLS, transport |

Khi đổi backend, giữ cùng level mix, schema, payload, output destination và durability assumptions. So Logback JSON với JUL CountingHandler là **so hai workloads khác nhau**, không phải một cuộc đua framework có ý nghĩa.

Đặt tên báo cáo chính xác: **“JUL line file test trên JDK 17”**, không viết thành **“Java logging performance”** chung chung mà không có điều kiện.

## 14. MDC và context propagation ảnh hưởng thế nào?

MDC giúp gắn requestId/traceId nhưng có chi phí:

1. Gán/đọc key trong ThreadLocal hoặc adapter.
2. Snapshot context map khi tạo log event.
3. Copy/restore map khi submit ExecutorService task.
4. Serialize các key thành JSON/text.
5. Cleanup key trong finally khi request/task kết thúc.

So sánh:

~~~text
Scenario A: no MDC
Scenario B: 2 keys (requestId, traceId)
Scenario C: 10 synthetic keys
Scenario D: copy/restore MDC across executor
~~~

Để biết overhead **chỉ của context copy**, nên test API map riêng bằng JMH. Để biết tổng tác động tới output, cho encoder xuất keys rồi đo bytes/event và throughput.

Nếu thêm 10 MDC keys làm JSON tăng dài, chênh lệch không chỉ do ThreadLocal mà còn là cost serialization, I/O và index. **Đừng bỏ MDC cleanup để tối ưu**: context leak giữa request A và B là lỗi correctness/privacy.

Tránh đưa email, access token hoặc raw customer object vào MDC. Những giá trị ấy làm tăng log volume và rủi ro rò PII.

## 15. Formatter, structured JSON và exception

Một event INFO rất ngắn khác xa một ERROR có stacktrace. Cần đo theo mix thực:

| Workload | Đặc điểm |
| --- | --- |
| INFO ngắn | eventCode, requestId, outcome |
| INFO có MDC | thêm traceId/spanId, service metadata |
| WARN retry | attemptNo, errorCode, dependency |
| ERROR throwable | class, message, cause, stacktrace theo policy |
| Long message | 1–10 KB synthetic string nếu workload cần |
| JSON special characters | dấu ngoặc kép, CR/LF, Unicode, escaping |
| High-cardinality fields | correlation IDs, dynamic exception types |
| Error storm | nhiều ERROR/stacktraces cùng lúc |

JSON serializer có cost escaping và field names, nhưng đem lại giá trị truy vấn. Không kết luận text tốt hơn JSON chỉ vì output ngắn hơn; hãy cân bằng **truy vấn, privacy, storage và CPU**.

**Không dump raw Throwable message** nếu nó có thể chứa URL/token/SQL params. Khi test performance, dùng exception synthetic vô hại; kiểm privacy là một release gate độc lập.

## 16. Đồng bộ và bất đồng bộ: hai loại độ trễ

**Synchronous logging** có thể làm caller chờ formatter/file stdout. **Asynchronous logging** giảm phần I/O trên caller bằng cách enqueue event.

| Chế độ | Thuận lợi | Rủi ro |
| --- | --- | --- |
| Sync appender | Dễ truy dấu đường I/O | p99 caller tăng khi sink chậm |
| Async bounded queue | Caller trả nhanh khi queue còn chỗ | Block/drop khi đầy |
| Unbounded queue | Hấp thụ burst ban đầu | Memory growth/OOM |
| File-backed spool | Có cơ hội retry/recover theo policy | Disk full, corruption, cleanup |
| Direct network appender | Ít tầng vận hành | Network gây coupling/latency |
| stdout + host agent | Tách vận chuyển khỏi JVM | Agent lag/rotation/collector drop |

**Bài test async phải đo cả caller latency, queue depth, drain rate, dropped count và ingestion lag.** Nếu chỉ đo logger.info() return, ta đo thời gian enqueue chứ không chứng minh log đã lưu.

Đừng mặc định async diagnostic logging đáp ứng yêu cầu audit bắt buộc. Audit có thể cần transaction/outbox hoặc durable store riêng.

## 17. Thử backpressure bằng sink chậm

Thí nghiệm staging:

1. Cấu hình async queue **nhỏ có chủ đích**.
2. Producer synthetic phát events ở tốc độ đủ vượt khả năng sink.
3. Chặn hoặc làm chậm sink bằng fixture được phép.
4. Theo dõi queue depth, enqueue time, blocked thread count, dropped events.
5. Giữ overload đủ để thấy chính sách block/backoff/discard.
6. Cho sink phục hồi; đo drain time.
7. Đối soát số events accepted, delivered, dropped và còn buffered.
8. Cleanup worker/queue sau thử nghiệm.

Mô hình định tính:

~~~text
arrivalRate = generated events per second
drainRate   = events processed per second

nếu arrivalRate > drainRate kéo dài:
  backlog tăng tới khi queue đầy
~~~

Đây là mô hình định tính, không phải công thức để dự đoán chính xác p99; batches, bursts và thời gian xử lý biến động làm hàng đợi phức tạp hơn.

**Tăng capacity queue không sửa nguyên nhân drain thiếu**, chỉ dời điểm bão hòa. Cần có log volume budget, output scaling, sampling cho diagnostic events phù hợp và cảnh báo.

## 18. File, flush, OS page cache và rotation

Khi đo file I/O:

- **Buffered write** có thể trả trước khi bytes thật sự bền vững trên ổ.
- FileHandler/OutputStream có thể flush mỗi event; config khác cho throughput khác.
- OS **page cache** làm kết quả thứ hai khác kết quả thứ nhất.
- SSD, network filesystem và container ephemeral volumes khác nhau.
- Rolling/renaming/compression có thể tạo spike.
- Disk/full partition có thể khiến application logging và business I/O cùng bị ảnh hưởng.
- File permission và ownership quyết định agent có đọc log mới sau rotation được không.

Vì vậy một phép đo “FileHandler ghi N dòng” chưa là benchmark durable storage. Nếu contract yêu cầu fsync hoặc outbox transaction, phải đo riêng đúng cơ chế ấy.

**Không chạy load tạo nhiều gigabytes log trên production** để lấy một số throughput; dùng môi trường được ủy quyền và quota an toàn.

## 19. End-to-end Java → agent → collector → backend

Bài đo đầy đủ có thể dùng synthetic canary events:

~~~text
JVM event with stable eventId
       |
       v
Local stdout / file
       |
       v
Host agent / DaemonSet
       |
       v
Collector: parse, batch, transform, retry
       |
       v
Backend storage + query
~~~

Quy trình:

1. Phát N events với eventId độc lập, timestamp và schema rõ.
2. Agent đọc từ đúng source; tránh thu cả file lẫn stdout tạo trùng.
3. Collector xử lý và gửi theo contract; đo queue, retry, parse errors.
4. Backend truy vấn được eventId trong deadline được phê duyệt.
5. Đếm unique eventId, duplicates, missing và in-flight.
6. Tính ingestion lag từ eventTime tới observedTime.
7. Thử collector tạm unreachable, phục hồi và đối soát.
8. Kiểm tra privacy synthetic canary không lộ raw token ngoài policy.

**Không coi query trả rỗng tức thì là mất event** khi backend có eventual consistency. Poll có deadline rõ, rồi phân loại result là pass, fail hoặc chưa đủ bằng chứng.

**Không đưa eventId/requestId/traceId làm metric labels**: cardinality cao. Dùng chúng trong logs/traces để điều tra, metrics dùng labels hữu hạn.

## 20. p95/p99 API latency và business impact

Muốn biết chiến lược log có làm hại người dùng, cần load test giữ business workload nhất quán:

| Metric | Vai trò |
| --- | --- |
| API throughput/RPS | Khả năng phục vụ |
| Success/error rate | Không được “nhanh hơn vì xử lý thất bại” |
| p50/p95/p99 latency | Ảnh hưởng tới trải nghiệm và tail latency |
| CPU/GC/allocation | Nguồn overhead có thể điều tra |
| Disk/network bytes | Chi phí pipeline |
| Async queue depth/drops | Bằng chứng điều kiện mất log |
| E2E ingestion lag | Log có còn kịp phục vụ alert? |
| Business state | Retry, transaction và audit không sai |

Không lấy **median elapsed time của năm trial** để gọi là p99 API latency. Phải thu phân phối latency theo request hoặc histogram được định nghĩa đúng.

So baseline/candidate trên cùng máy/traffic, lặp lại đủ lần; nếu chênh lệch 2% trong khi nhiễu 10%, chưa có bằng chứng kết luận. Monitoring của load generator cũng cần ổn định.

## 21. Concurrency và lock contention

Chương trình đơn luồng **không thể** dự đoán hiệu ứng nhiều request threads cùng ghi appender.

Nguồn contention gồm:

- Synchronized appender hoặc formatter.
- Async queue đa producer.
- Shared timestamp formatter, lock và cache.
- ThreadLocal/MDC map snapshots.
- Disk write serialization.
- Worker saturation và backpressure.
- Connection pool hoặc network client của remote appender.

Một matrix thực hành:

| Threads | Payload | Mục tiêu |
| --- | --- | --- |
| 1 | INFO ngắn | Baseline đơn thread |
| 2 | INFO ngắn | Coordination overhead |
| 4 | INFO + MDC | Context cost |
| 8 | INFO/WARN/ERROR mix | Allocation/stacktrace |
| 16 hoặc CPU budget | Error burst | Saturation và tail latency |

Dùng CountDownLatch/CyclicBarrier để đồng bộ điểm bắt đầu, có timeout/finally cleanup. Không dùng sleep như phép đo chính. Handler đếm trong bài lab không thread-safe; nếu mở rộng multi-thread cần LongAdder/atomic counter hoặc thiết kế đúng thread-safety.

## 22. Allocation, GC và công cụ chẩn đoán

MDC snapshot, JSON encoding, char arrays, Throwable formatting và message building tạo allocations. GC pressure có thể làm tăng p99 dù average throughput còn tốt.

Những công cụ hữu ích:

- **JFR**: profile CPU, allocations, GC events khi được cấp quyền.
- **jcmd**: truy vấn JVM theo quyền trong môi trường phù hợp.
- **JDK unified GC logging**: quan sát collector pauses và counters.
- **JMH GC profilers**: giúp ước lượng bytes/op ở microbenchmark.
- **APM/metrics**: tương quan logger volume và business latency.

Ví dụ bổ sung trên môi trường lab:

~~~bash
java -Xlog:gc=info LoggingPerformanceLab
~~~

Lệnh có thể in thêm GC events lên console; **stdout/stderr không còn đúng sáu dòng** như chương trình không có flags. Số GC events thay đổi theo heap và workload. Nếu không có event GC trong lúc chạy, có thể không có dòng GC bổ sung.

Heap dump có thể chứa PII/secrets và làm ảnh hưởng service; **không chụp heap dump production chỉ vì muốn đo logging**.

## 23. Phân biệt bottleneck và tối ưu giả

Một số sai lầm:

| Hiện tượng | Diễn giải sai | Cách kiểm |
| --- | --- | --- |
| Async queue nhanh hơn sync | “log đã lưu nhanh hơn” | Đo actual drain và ACK |
| Disabled logging nhanh | “INFO production cũng nhanh” | Đo enabled levels |
| Thêm guard tiết kiệm CPU | “mọi parameterized call cần if” | Phân biệt argument rẻ/đắt |
| Logger A ghi ít bytes hơn | “framework A tốt hơn” | Chuẩn hóa schema/payload |
| Sampling làm throughput tăng | “cải tiến không có trade-off” | Đếm sampled/dropped events |
| Log file trả nhanh | “durable sau mất điện” | Hiểu flush/fsync semantics |
| Throughput tăng khi backend lỗi | “scaling thành công” | Kiểm buffer, drops và business SLO |
| P99 tốt hơn khi bỏ stacktrace | “không ảnh hưởng observability” | Kiểm incident/audit requirements |

**Không tối ưu bằng cách bỏ dữ liệu bắt buộc**. Một release phải đạt **performance gates và correctness/privacy gates** đồng thời.

## 24. Báo cáo kết quả đúng cách

Mẫu bảng điền dữ liệu **thực sau khi chạy**:

| Mode | Operations | medianMs | opsPerSec | Events | Bytes | Ghi chú |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| BASELINE | 20.000 | *đo* | *đo* | 0 | 0 | Loop/checksum |
| DISABLED_EAGER | 20.000 | *đo* | *đo* | 0 | 0 | FINE off, vẫn tạo message |
| DISABLED_GUARDED | 20.000 | *đo* | *đo* | 0 | 0 | FINE off, skip message |
| ENABLED_MEMORY | 20.000 | *đo* | *đo* | 20.000 | 0 | Count handler |
| ENABLED_FILE | 2.000 | *đo* | *đo* | 2.000 | *đo* | File UTF-8 |

Các ô *đo* không phải số liệu được cung cấp sẵn. **Không tự sáng tác benchmark measurements**.

Công thức tham khảo:

~~~text
throughputOpsPerSec = operations / elapsedSeconds

relativeOverheadPercent
  = 100 * (candidateElapsed - baselineElapsed) / baselineElapsed
~~~

Tính relative overhead chỉ khi hai biến thể có **cùng operations và điều kiện**. Baseline rất nhỏ khiến phần trăm có thể nhiễu lớn. Báo cả raw values, number of trials và uncertainty, không chỉ một tỷ lệ phần trăm.

Nếu throughput từ local file cao bất thường, kiểm disk cache và counting; nếu không thấy events, performance result **không hợp lệ**.

## 25. Ghi cấu hình để tái lập

Mỗi kết quả nên đi kèm:

- JDK vendor/version, JVM flags, GC mode và heap size.
- Host OS, CPU, RAM, VM/container quotas.
- Disk type/filesystem/cache và mức tải nền.
- Logger API/backend version (JUL, SLF4J/Logback, Log4j 2).
- Effective logger level, formatter, encoder, sampling config.
- Message length, event field count, stacktrace ratio, MDC keys.
- Number of threads, warm-up, measurement trials, number of events.
- Type of sink: memory/file/stdout/agent/network.
- Flush/batching/queue limits, retry/drop policies.
- Throughput, p95/p99, GC, allocations, disk bytes và event completeness.
- Đường truy vấn backend và time window nếu có E2E.

Config được lưu theo quy trình, **không copy certificates, tokens, raw payload hoặc secrets** vào benchmark report.

## 26. Bài tập mở rộng theo thứ tự

**Bài A — message size:** tăng chiều dài synthetic message, đo bytes/s và chi phí formatter. Giữ N hợp lý, không tạo file lớn vô hạn.

**Bài B — disabled logging:** so eager concat, guarded concat và parameterized SLF4J. Kiểm lệnh serialize đắt có được gọi khi DEBUG disabled không.

**Bài C — JSON:** thay text layout bằng JSON encoder, giữ cùng event schema và sink. Đo CPU/allocations/bytes, kiểm escaping/parse, không bỏ field chỉ để nhanh hơn.

**Bài D — MDC:** so 0, 2 và 10 keys, ghi JSON. Đo copy/restore qua executor, test không leak ID giữa request A/B.

**Bài E — AsyncAppender:** dùng queue nhỏ, sink chậm, đo enqueue p99, drop, drain và shutdown flush. Không xem queue như durable storage.

**Bài F — collector outage:** dùng event IDs synthetic, tạm gián đoạn test collector, đo buffer/retry và end-to-end ingest lag. Đối soát unique events.

**Bài G — error storm:** tăng tỷ lệ ERROR có Throwable synthetic, đo spike GC, CPU, log volume, sampling/rate-limit behavior và dashboard usability.

**Bài H — production-like load:** dùng đúng business request profile (đã làm sạch dữ liệu), so p95/p99 và error rate giữa hai cấu hình, có performance budget được duyệt.

## 27. Những anti-pattern khi đo logging

| Anti-pattern | Vì sao gây sai | Thay bằng |
| --- | --- | --- |
| Một lần System.nanoTime | JIT/GC/scheduler nhiễu | Warmup, nhiều lần đo, JMH |
| In System.out trong timed loop | Console chi phối kết quả | In sau vùng đo |
| So disabled với enabled rồi quy kết framework | Workload không giống | Giải thích phạm vi và giữ config |
| Không kiểm event count | Drop làm throughput giả tăng | Positive correctness checks |
| So memory với file như ngang nhau | I/O và formatter khác | Same sink/bytes để kết luận |
| Đo async chỉ ở enqueue | Không biết backlog/drop | Drain rate + E2E |
| Không ghi JVM/OS/config | Không tái lập được | Run manifest |
| Dùng real personal data | Rò PII | Synthetic events |
| Tắt audit để lấy điểm cao | Thiếu bằng chứng nghiệp vụ | Durable audit design |
| Dựa vào INFO avg để dự đoán error storm | Stacktrace, allocation khác | Mix thực tế |
| Lấy median trial gọi p99 latency | Sai định nghĩa | Per-request samples/histogram |
| Chạy stress trên production không giới hạn | Nguy cơ outage | Staging, quota, approval |

## 28. Checklist nghiệm thu bài thực hành

Một kết quả đạt yêu cầu khi:

- **LoggingPerformanceLab.java** là chương trình Java 17 độc lập, có lệnh javac/java rõ.
- Chương trình in năm dòng mode và một dòng **sanity=PASS** khi checks thành công.
- Có warm-up, nhiều lượt đo và median đúng định nghĩa.
- Các mode enabled kiểm đúng số event; file count và bytes được xác minh.
- Không ghi dữ liệu người dùng thật, không tạo file tồn đọng có chủ đích.
- Không tuyên bố stdout timing cố định; chỉ cung cấp hình dạng output minh họa.
- Phân biệt **disabled level, memory handler, synchronous file** và full pipeline.
- Không so medianMs giữa hai biến thể có N khác nhau như cùng workload.
- Có hướng dẫn JMH khi cần microbenchmark thực sự.
- Có kế hoạch đo p95/p99, GC/allocations, async drops và E2E lag.
- Có performance budget và correctness/privacy/reliability gates.
- Có báo cáo ghi JDK/OS, config, trial count và giới hạn của phép đo.

**Kết luận:** Đo hiệu năng Java Logging là việc đo **chi phí đúng chỗ và có kiểm chứng**, không phải chỉ đạt ops/s cao nhất. Bắt đầu bằng Java 17 JUL lab để nhìn overhead của disabled logging và enabled handlers; dùng **JMH** khi cần đo micro-operation, dùng **load/integration/end-to-end tests** khi cần đánh giá Logback/JSON/MDC/AsyncAppender và collector trong thực tế. Một chiến lược tốt giữ được **log đúng, không lộ PII, không mất audit bắt buộc**, đồng thời phù hợp ngân sách CPU, latency và storage.