# Đo overhead logging trong ứng dụng Java

## 1. Overhead logging là gì?

**Overhead logging** là phần tài nguyên và thời gian ứng dụng phải chi thêm để tạo, xử lý, vận chuyển và lưu log. Khi một luồng nghiệp vụ thực hiện `logger.debug(...)` hoặc `logger.info(...)`, chi phí có thể phát sinh ngay cả khi bản ghi cuối cùng không xuất hiện trong file. Mức chi phí phụ thuộc vào logger có bật hay không, cách tạo thông điệp, việc chụp ngữ cảnh, filter, formatter, queue, appender và tốc độ của đích ghi.

Một ứng dụng có thể “ghi log bất đồng bộ” nhưng vẫn chịu chi phí đáng kể trên luồng request: kiểm tra level, tính đối số, xây dựng event, copy MDC, cấp phát bộ nhớ và enqueue. Việc ghi tệp/socket được chuyển qua worker giúp giảm một số thao tác chặn trên đường request; nó không khiến chi phí logging bằng không.

Mục tiêu của **đo overhead logging** là xác định bằng bằng chứng:

- Mỗi sự kiện log hoặc mỗi request tốn thêm bao nhiêu **CPU, allocation và thời gian**?
- Logging ảnh hưởng thế nào đến **request throughput, p95/p99 latency, GC và mức sử dụng tài nguyên**?
- Chi phí đến từ **lời gọi logger, tạo message, định dạng, queue hay sink**?
- Khi log quá nhiều, hệ thống **chặn producer, drop event, tăng backlog** hay mất log lúc shutdown?
- Tăng mức DEBUG/TRACE để điều tra có gây vượt giới hạn vận hành không, và cách cấu hình nào giảm chi phí mà vẫn giữ đủ khả năng quan sát?

**Không có một con số “logging overhead của Java” dùng chung.** Cùng một lời gọi log có thể gần như không đáng kể nếu bị loại sớm, nhưng tốn nhiều thời gian khi formatter nặng, đối số đắt, ghi đồng bộ tới một sink chậm hoặc queue đầy.

## 2. Bóc tách đường đi của một log event

```text
[Ứng dụng gọi logger]
          │
          ▼
  1. Tính đối số Java
          │
          ▼
  2. Kiểm tra level/filter
          │
          ▼
  3. Tạo/chụp log event
          │       (timestamp, thread, MDC/trace, exception...)
          ▼
  4. Định dạng/serialize (thời điểm tùy framework)
          │
          ├── Logging đồng bộ ──► 5a. Appender / file / socket
          │                                      │
          └── Logging bất đồng bộ ──► 5b. Queue ─► Consumer ─► Sink
                                          │
                              Đầy queue: block / drop / fallback
          │
          ▼
  6. Collector / transport / index / lưu trữ backend
```

Để đo đúng, phải xác định **ranh giới phép đo**. Ít nhất có bốn đại lượng khác nhau:

| Đại lượng | Khoảng thời gian hoặc tài nguyên đo | Ý nghĩa và giới hạn |
| --- | --- | --- |
| **Call-site cost** | Trước khi gọi logger đến lúc API log trả về | Ảnh hưởng trực tiếp luồng nghiệp vụ, gồm tính đối số Java |
| **Event-processing cost** | Tạo event, MDC, filter, formatter, dispatch | Có thể phân bố giữa producer và consumer |
| **Sink cost** | Appender chuyển event đến file/socket/collector | Chưa mặc định là dữ liệu đã bền vững hoặc lập chỉ mục |
| **End-to-end delivery lag** | Thời điểm tạo event đến khi backend quan sát được | Bao gồm queue, truyền tải, retry, batch, ingestion |

**Nếu chỉ đo thời gian `logger.info(...)` trả về trong async logging**, bạn mới đo được chi phí phía producer trong điều kiện thử; không đo hết CPU worker, I/O và thời gian đẩy log tới backend.

### Ví dụ cùng một lời gọi nhưng chi phí khác nhau

```java
// Trích đoạn SLF4J; cần SLF4J + backend trong ứng dụng.
logger.debug("orderId={}", orderId);
```

Với DEBUG tắt, backend thường chỉ cần kiểm tra level và tránh phần lớn thao tác tạo event. Tuy nhiên **Java đã tính xong mọi biểu thức đối số** trước khi gọi method:

```java
// Hàm buildLargeSnapshot() vẫn được gọi dù DEBUG đang tắt.
logger.debug("snapshot={}", buildLargeSnapshot());
```

Để tránh chi phí tính đối số đắt khi level tắt:

```java
if (logger.isDebugEnabled()) {
    logger.debug("snapshot={}", buildLargeSnapshot());
}
```

Đây là trích đoạn, không phải chương trình độc lập. Bộ lọc phía appender vẫn có thể loại event ngay cả khi `isDebugEnabled()` trả về `true`. Với SLF4J 2.x, fluent API và supplier cho phép trì hoãn một số cách tính đối số; cần kiểm tra backend/API thực tế thay vì giả định mọi overload đều lazy.

## 3. Những chỉ số cần đo

Đo **chi phí trực tiếp** và **tác động đến dịch vụ** song song. Một phép đo đơn lẻ như “logger.info mất 20 ns” không nói được backend có kịp ghi hay request p99 có tăng không.

| Chỉ số | Cách hiểu | Cần chú ý |
| --- | --- | --- |
| `ns/op`, `µs/op` | Thời gian bình quân cho một phép ghi log có định nghĩa rõ | So sánh đúng kịch bản, không suy sang p99 |
| `CPU time/op` hoặc CPU% | CPU tạo, lọc, định dạng và vận chuyển log | Async worker có thể dùng CPU riêng |
| `bytes allocated/op` | Cấp phát heap mỗi lần log | Có thể gây GC ngay cả khi call-site latency thấp |
| `request throughput` | Request/giây với tải cố định | Logging có thể làm giảm throughput khi CPU/I/O bão hòa |
| `p50/p95/p99 latency` | Phân bố độ trễ nghiệp vụ | Cần đủ mẫu, so cùng loại request và tải |
| `GC pauses` và allocation rate | Áp lực bộ nhớ do tạo message/event | Đo cùng heap và cấu hình GC |
| `queue_depth` / `queue_capacity` | Mức tồn đọng ở async logger | Queue cao kéo dài là dấu hiệu consumer không theo kịp |
| `enqueue_wait` | Thời gian producer bị block khi queue đầy | Có thể tạo spike ở request p99 |
| `dropped_events_total` | Số log bị loại do policy/overload | Không coi throughput cao là tốt nếu mất log |
| `sink_write_latency` | Thời gian appender/consumer ghi đích | Khác với độ trễ request và enqueue |
| `delivery_lag` | Thời gian từ event đến backend có thể truy vấn | Phụ thuộc collector/transport và clock |
| `disk/network bytes/sec` | Chi phí tài nguyên ở sink/collector | Phân biệt appender ghi và backend ingest |

**Tỷ lệ event ghi được** phải được diễn giải theo các mốc riêng: *được gọi*, *được chấp nhận vào queue*, *đã xử lý bởi consumer*, *sink nhận thành công*, *backend đã lưu*. Đếm `enqueued_total` không thể thay cho `persisted_total` nếu hệ thống có crash hoặc mất kết nối.

Để phép đo có ý nghĩa, cũng ghi nhận JVM/JDK, số lõi CPU, heap/GC, backend logging và phiên bản, loại sink, queue size, batch policy, kích thước message, tỷ lệ các level, số producer, workload và thời gian chạy.

## 4. Thiết kế baseline: so sánh như thế nào?

### Cần tối thiểu một đường cơ sở

Đo cùng công việc nghiệp vụ ở các cấu hình có kiểm soát:

| Kịch bản | Cấu hình | Câu hỏi |
| --- | --- | --- |
| **A — Không phát log thử** | Đường nghiệp vụ tương đương nhưng không gọi logger ở điểm đo | Chi phí nền của công việc |
| **B — Level bị tắt** | Có lời gọi DEBUG nhưng effective logger level là INFO | Giá của kiểm tra logger và đối số |
| **C — Level bật, sink không I/O** | DEBUG/INFO bật; handler/appender chấp nhận nhưng không ghi console/file | Tạo, dispatch và định dạng (nếu có) tốn gì? |
| **D — Level bật, sink thực** | Cùng message, ghi ra file/stdout/network đã định nghĩa | Chi phí thêm khi ghi/serialize thật |
| **E — Async, sink thực** | Có queue/consumer, backpressure policy rõ | Chi phí trên request và chi phí nền thay đổi ra sao? |

Kịch bản C phải được mô tả chính xác: một `NullAppender`/`NoOpHandler` chỉ loại bỏ phần ghi I/O; nếu nó không chạy formatter, phép đo **không bao gồm** chi phí formatter. Khi muốn cô lập formatter, cần thêm kịch bản đưa event qua encoder nhưng thu byte vào đích bộ nhớ có kiểm soát.

Khi so **A và B**, đừng thay đổi logic nghiệp vụ hoặc dữ liệu chỉ vì bỏ logging. Ví dụ không thay lời gọi `logger.debug("{}", compute())` bằng “không làm gì” rồi kết luận toàn bộ chênh lệch là chi phí framework: `compute()` vốn vẫn bị đánh giá ở B. Cần nói rõ bạn đang đo **tổng chi phí tại call-site** hay **chỉ chi phí logger/backend**.

### Giữ tải thực tế ổn định

Một thử nghiệm ứng dụng nên giữ cố định: request mix, concurrency, dữ liệu, môi trường, endpoint, thứ tự triển khai, JVM flags, cấu hình heap/GC, cấu hình kết nối, tốc độ của downstream và sink. Có thể chạy theo cặp A/B lặp lại và đổi thứ tự A–B–B–A để giảm tác động của nhiệt CPU hoặc cache.

**Không so một cấu hình tại máy phát triển với cấu hình còn lại trong container production** rồi gọi số chênh là overhead logging. Điều kiện chạy quá khác nhau.

## 5. Đo latency và throughput mà không nhầm công thức

Giả sử cùng một bài tải cố định, có số liệu:

| Chỉ số | Logging OFF | Logging ON |
| --- | ---: | ---: |
| Throughput | 10.000 req/s | 9.200 req/s |
| p95 latency | 15 ms | 17 ms |
| CPU trung bình | 55% | 68% |

Các số trên chỉ **minh họa**. Khi đó:

- Mức giảm throughput so với OFF: `(10.000 − 9.200) / 10.000 = 8%`.
- Mức tăng p95: `17 − 15 = 2 ms`; mức tăng tương đối khoảng 13,3%.
- CPU tăng **13 điểm phần trăm**, không nói “CPU tăng 13%” vì phần trăm tương đối là `(68 − 55)/55 ≈ 23,6%`.

**Cảnh báo khi diễn giải:** hai giá trị p95 là phân vị của hai tập quan sát, không phải mỗi request đã chậm thêm chính xác 2 ms. Kết quả đo còn chịu nhiễu từ jitter, tải, GC, JIT và downstream. Chênh lệch không tự chứng minh nguyên nhân nếu cấu hình ngoài logging cũng thay đổi.

Nếu biết số **log event thật sự được tạo/chấp nhận** trong cùng workload, có thể ước lượng ngân sách tài nguyên:

```text
extra_cpu_time_per_accepted_event
  ≈ (total_cpu_time_logging_on - total_cpu_time_logging_off)
     / accepted_log_events_logging_on
```

Chỉ số này là **ước lượng chi phí tăng thêm theo event trong thí nghiệm**, không phải hằng số cho mọi level, message size hoặc concurrency. Không dùng số event `written` nếu các sự kiện bị drop và bạn đang muốn ước lượng chi phí *offered event*. Có thể báo cả **per attempted event** và **per delivered event** để tránh che chi phí của event bị loại.

Với async logger, báo đồng thời **request latency** và **CPU/I/O tổng thể**; nếu chỉ nhìn latency request giảm mà CPU worker tăng mạnh hoặc hàng đợi tích tụ, chưa thể kết luận giải pháp tốt hơn.

## 6. Java 17 chạy độc lập: quan sát chi phí call-site

Đoạn mã sau dùng **`java.util.logging` (JUL)** của JDK, không cần dependency ngoài. Nó minh họa bằng số đếm xác định:

1. Khi `FINE` bị tắt, **đối số eager** vẫn được Java tính trước khi gọi logger.
2. Khi `FINE` bị tắt, **`Supplier<String>`** chưa được gọi để tạo message.
3. Khi `FINE` được bật, supplier được gọi và event đi vào handler.
4. Khi `INFO` được bật với message đơn giản, event đi vào handler mà không chạy hàm xây message thử.

Chương trình đồng thời đo elapsed time thực bằng `System.nanoTime()`, nhưng **không khẳng định kết quả timing là benchmark chuẩn**: warmup ngắn, một thread, backend JUL và handler không ghi I/O. Kết quả thời gian thay đổi theo máy và JVM. Các đếm event giúp xác minh tình huống đo.

Lưu file **`LoggingOverheadDemo.java`**:

```java
import java.util.Locale;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LoggingOverheadDemo {
    private static final int WARMUP = 10_000;
    private static final int OPERATIONS = 50_000;
    private static final Logger LOG = Logger.getLogger("demo.overhead");
    private static int messageBuilds;

    private static final class CountingHandler extends Handler {
        private int delivered;

        CountingHandler() {
            setLevel(Level.ALL);
        }

        @Override
        public void publish(LogRecord event) {
            if (isLoggable(event)) {
                delivered++;
            }
        }

        @Override
        public void flush() {
            // Không ghi I/O: cô lập một phần chi phí logger/dispatch.
        }

        @Override
        public void close() {
            // Không có tài nguyên phải đóng.
        }

        void reset() {
            delivered = 0;
        }

        int delivered() {
            return delivered;
        }
    }

    private static String buildMessage() {
        messageBuilds++;
        return "payload-" + messageBuilds;
    }

    private static void measure(
            String name,
            Level level,
            Runnable operation,
            CountingHandler sink) {

        LOG.setLevel(level);
        for (int i = 0; i < WARMUP; i++) {
            operation.run();
        }

        messageBuilds = 0;
        sink.reset();

        long start = System.nanoTime();
        for (int i = 0; i < OPERATIONS; i++) {
            operation.run();
        }
        long elapsedNanos = System.nanoTime() - start;

        // stdout chứa kết quả kiểm đếm xác định.
        System.out.printf("%s | builds=%d | handled=%d%n",
                name, messageBuilds, sink.delivered());

        // stderr chứa phép đo biến thiên theo JVM/máy/thời điểm.
        System.err.printf(Locale.ROOT, "%s | elapsed_ms=%.3f%n",
                name, elapsedNanos / 1_000_000.0);
    }

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        CountingHandler sink = new CountingHandler();
        LOG.addHandler(sink);

        try {
            measure(
                "disabled-eager", Level.INFO,
                () -> LOG.fine("msg=" + buildMessage()),
                sink);

            measure(
                "disabled-lazy", Level.INFO,
                () -> LOG.fine(() -> "msg=" + buildMessage()),
                sink);

            measure(
                "enabled-lazy", Level.FINE,
                () -> LOG.fine(() -> "msg=" + buildMessage()),
                sink);

            measure(
                "enabled-constant", Level.INFO,
                () -> LOG.info("constant message"),
                sink);
        } finally {
            LOG.removeHandler(sink);
            sink.close();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 LoggingOverheadDemo.java
java LoggingOverheadDemo
```

**Stdout chính xác** (chỉ xét stdout; `stderr` có các số `elapsed_ms` thay đổi theo lần chạy):

```text
disabled-eager | builds=50000 | handled=0
disabled-lazy | builds=0 | handled=0
enabled-lazy | builds=50000 | handled=50000
enabled-constant | builds=0 | handled=50000
```

Giải thích kết quả:

- `disabled-eager`: `buildMessage()` gọi **50.000 lần**, mặc dù `LOG.fine` bị level INFO chặn, nên handler không nhận event nào. Chi phí đánh giá biểu thức xảy ra trước API logging.
- `disabled-lazy`: supplier không được đánh giá khi FINE bị chặn, nên cả `builds` và `handled` đều bằng 0.
- `enabled-lazy`: FINE bật; supplier được đánh giá và handler nhận đủ 50.000 bản ghi.
- `enabled-constant`: INFO bật; không cần tạo payload thử nhưng vẫn dispatch 50.000 `LogRecord` tới handler.
- `CountingHandler` **không ghi file, socket hay console**. Thời gian ở `stderr` đo lệnh gọi logger + dispatch và các thao tác minh họa, không phải tổng chi phí lưu log trong production.
- Hàm `measure` chạy warmup trước khi tính, nhưng mỗi kịch bản có nhánh logic khác nhau và có thể chịu JIT/GC/CPU noise. Không so các số `elapsed_ms` như bằng chứng hiệu năng cuối cùng.

**Giới hạn cần ghi rõ:** mẫu dùng biến đếm trong một thread; trong hệ thống nhiều thread, đo event counters bằng thiết kế thread-safe. Không dùng `System.out.println` ngay trong đường được đo, vì thao tác đó làm biến dạng chính kết quả cần quan sát.

## 7. Đo microbenchmark có độ tin cậy hơn bằng JMH

Đối với chi phí từng lời gọi logger, **JMH (Java Microbenchmark Harness)** phù hợp hơn một vòng lặp `System.nanoTime()` tự viết. JMH quản lý warmup, đo lặp, fork JVM và thống kê để giảm một phần sai lệch do JIT/khởi tạo.

Một bài benchmark nên định nghĩa chính xác các kịch bản, chẳng hạn:

- Logger **disabled**, đối số constant, không có allocation đáng kể.
- Logger **disabled**, đối số eager tốn chi phí.
- Logger **disabled**, đối số lazy/supplier.
- Logger **enabled** tới no-op sink, message constant.
- Logger **enabled** tới formatter JSON nhưng sink bộ nhớ có kiểm soát.
- Logger **enabled** tới file/stdout/socket, đo như một **system benchmark** ngoài JMH nếu I/O và backpressure là trọng tâm.

Ví dụ **khung JMH minh họa**, cần dependency `org.openjdk.jmh:jmh-core` cùng annotation processor `jmh-generator-annprocess` được cấu hình trong build. Đây **không phải file Java độc lập**:

```java
@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 8)
@Fork(2)
public class LoggerCallBenchmark {
    private final java.util.logging.Logger logger =
            java.util.logging.Logger.getLogger("bench.disabled");

    @Setup(Level.Trial)
    public void setUp() {
        logger.setUseParentHandlers(false);
        logger.setLevel(java.util.logging.Level.INFO);
    }

    @Benchmark
    public void disabledFineConstant() {
        logger.fine("constant message");
    }
}
```

Các annotation ở đây đến từ `org.openjdk.jmh.annotations.*`, nên cần import và cấu hình JMH khi dùng. Chỉ dùng kết quả của benchmark này cho **call-site disabled FINE**; nó **không đo** chi phí ghi tệp hoặc truyền mạng.

Khi triển khai JMH:

1. Dùng nhiều fork, warmup đủ dài và lặp nhiều vòng; báo khoảng phân tán/thống kê, không chỉ một số đẹp nhất.
2. Chọn một baseline phù hợp; tránh benchmark chỉ đo JVM tối ưu bỏ toàn bộ công việc. Với dữ liệu xây dựng hoặc formatter, dùng trạng thái/`Blackhole` đúng cách.
3. Không bật ghi console cho hàng triệu lần log trong microbenchmark nếu mục tiêu là chi phí logger thuần; terminal có thể thành nút thắt chính.
4. Nếu đo allocation, dùng profiler JMH phù hợp, chẳng hạn `-prof gc` khi khả dụng trong bản cài.
5. Tách từng độ dài message, loại đối số, mức logger, kiểu formatter và cấu hình sink thành các nhóm đo; không gom thành một con số.
6. Cẩn thận với phép đo đa luồng. Số thread, CPU affinity, GC và JIT compilation có thể làm kết quả biến đổi lớn.

## 8. Đo formatter, message size và allocation

Bên cạnh level và dispatch, lượng công việc thường nằm ở **tạo dữ liệu**:

- Nối chuỗi, `String.format`, tuần tự hóa object/JSON, định dạng timestamp và exception stack trace.
- Sao chép context MDC, `trace_id`, `span_id`, tên luồng/caller location.
- Chụp stack trace: có thể chi phí cao hơn thông điệp ngắn thông thường.
- Encoder JSON, escaping ký tự và các trường bổ sung của structured logging.
- Đối số lớn, `toString()` phức tạp hoặc đọc dữ liệu từ cơ sở dữ liệu chỉ để ghi log.

Thiết kế kịch bản độc lập: message 20 B, 200 B, 2 KB; có/không exception; 0/5/20 trường MDC; JSON vs plain text; thêm và bỏ caller location. Đừng dùng cùng một object nhỏ bất biến rồi kết luận về log payload lớn thực tế.

**Allocation và GC:** chi phí log có thể xuất hiện dưới dạng tốc độ cấp phát tăng và GC chạy thường xuyên hơn, ngay khi p50 của lời gọi logger trông nhỏ. Theo dõi allocation rate, bytes/op, young GC, pause time và heap occupancy trên cùng tải. Java Flight Recorder (JFR) là một công cụ hữu ích để điều tra allocation, CPU hotspot, socket/file I/O; hãy chọn sự kiện và cấu hình recording phù hợp để hạn chế overhead của công cụ đo.

Đừng tự gán mọi spike GC cho logging chỉ vì spike xuất hiện lúc bật DEBUG. So sánh trước/sau, nhìn allocation stack trace và thay đổi khối lượng request để xác nhận.

## 9. Đo I/O sink: đồng bộ và bất đồng bộ

### Logging đồng bộ

Khi `FileAppender` hoặc `ConsoleAppender` chạy trực tiếp trên request thread, thời gian gọi logger có thể bao gồm format và thao tác ghi. Tốc độ của ổ đĩa/terminal/stdout collector ảnh hưởng trực tiếp đến latency.

Đo ít nhất:

- Thời gian request thread chờ trong appender/write.
- Throughput và độ trễ request khi log volume tăng.
- CPU cho encoding, file write bytes/sec, disk IOPS, lỗi ghi.
- Chính sách flush/buffer, rotation, lock giữa các thread.
- Độ trễ backend nhận log nếu có collector phía sau.

Ghi vào `/dev/null` hoặc no-op sink không tương đương ghi file thực: loại bỏ hoặc thay đổi hoạt động của hệ thống file và bộ đệm. Ghi ra console trong IDE cũng khác stdout trong container được thu thập qua log driver.

### Logging bất đồng bộ

Với `AsyncAppender`/async logger, chia phép đo:

```text
Request thread:
  log call ─► tạo event ─► enqueue ─► trả về
                               │
                               ▼
                     Queue / consumer lag
                               │
                               ▼
Background worker:
                   format/write/flush ─► collector
```

Đo **hai phía**: call-site latency trên producer và tổng CPU + I/O + delivery lag trên consumer/sink. Khi queue đầy, tùy chính sách framework, producer có thể block, event bị loại hoặc chuyển sang xử lý đồng bộ. Điều này làm phép đo trên tải nhẹ khác hẳn phép đo tải cao.

Các chỉ số thiết yếu:

| Chỉ số | Cách dùng |
| --- | --- |
| `events_attempted_total` | Số lời gọi/event được đề nghị xử lý |
| `events_enqueued_total` | Số event được queue nhận |
| `events_dequeued_total` | Số event consumer đã lấy |
| `events_written_total` | Số event sink chấp nhận theo định nghĩa đo |
| `events_dropped_total` | Số event bị loại theo policy |
| `enqueue_wait_p99` | Producer có bị block khi queue đầy hay không |
| `queue_depth` và `consumer_lag` | Worker có theo kịp tốc độ sinh event hay không |
| `sink_error_total` | Ghi file/connection bị lỗi hoặc timeout |
| `shutdown_pending` | Số event còn tồn khi dừng |

Tên trên chỉ là **mô hình metric đề xuất**, không phải mọi framework đều xuất sẵn các chỉ số này. Cần đối chiếu instrumentation thực tế; nếu không có, thêm đo lường với chi phí đủ nhỏ hoặc lấy từ appender/collector.

**Điểm cốt lõi:** latency producer có thể rất thấp trong khi queue tăng đến đầy, nhiều log bị drop hoặc backend chậm hàng chục giây. So sánh “async nhanh hơn sync” mà không đo delivery/backlog là chưa đủ.

## 10. Phân tích queue, throughput và nguy cơ overload

Giả sử tốc độ event đến là `λ` và tốc độ consumer xử lý là `μ` (đơn vị events/s). Nếu `λ > μ` kéo dài, backlog tăng đến giới hạn. Queue chỉ hấp thụ các đợt burst ngắn; không tạo thêm năng lực I/O bền vững.

Có thể tính ngân sách đơn giản:

```text
incoming_log_bytes_per_sec ≈ events_per_sec × avg_encoded_bytes_per_event

estimated_buffer_bytes ≈ queue_capacity × avg_in_memory_event_bytes

required_sink_throughput >= sustained_incoming_log_bytes_per_sec
                         (nếu không muốn backlog tăng kéo dài)
```

Lưu ý kích thước event **trong heap** có thể lớn hơn chuỗi được ghi ra sink vì object header, tham chiếu, context và dữ liệu trung gian. Không suy ra heap queue từ kích thước JSONL trên đĩa một cách trực tiếp.

Ví dụ minh họa: 20.000 events/s × 300 B/event ≈ 6 MB/s dữ liệu encoded, chưa tính overhead của protocol, collector, index hay file rotation. Nếu sink chỉ xử lý được 4 MB/s trong thời gian dài, tăng queue size có thể trì hoãn lúc đầy nhưng không giải quyết nút thắt.

Khi thử tải, phải **báo cả số event mất**. Một cấu hình “nhanh hơn 30%” nhưng drop hầu hết DEBUG/WARN có thể không phù hợp mục tiêu quan sát.

## 11. Đo tác động lên request trong ứng dụng thật

Microbenchmark giúp thấy cơ chế, còn **load test** trả lời câu hỏi ứng dụng có chịu được logging hay không.

Quy trình đề xuất:

1. Chọn endpoint hoặc workflow có log thật (đơn hàng, đọc dữ liệu, xử lý batch). Ghi rõ tần suất từng mức log và kích thước event.
2. Chạy tải ổn định ở mức thấp, trung bình, gần giới hạn công suất; đừng chỉ thử lúc CPU gần như rảnh.
3. Đặt baseline OFF/INFO, sau đó mở DEBUG cho package cần điều tra và lặp lại **cùng request mix**.
4. Ghi p50/p95/p99, throughput, error rate, CPU, heap, GC, disk/network throughput và trạng thái logging queue.
5. Nếu logging bất đồng bộ, xác minh số event đã đến sink sau khi drain hoặc sau một khoảng đo thống nhất.
6. Lặp lại từng cấu hình, trộn thứ tự chạy và ghi nhận biến động giữa các lượt. Chỉ kết luận khi chênh lệch lớn hơn nhiễu đo.
7. Thử khi disk/collector chậm, queue gần đầy, burst log và shutdown dưới tải, vì đây thường là nơi overhead lộ rõ.

**Điều kiện so sánh:** với load kiểu *closed loop* (client chờ response rồi mới gửi tiếp), throughput và concurrency có thể cùng thay đổi; với load kiểu *open loop* gửi theo tốc độ đến cố định, latency có thể tích tụ khi server quá tải. Phải ghi rõ mô hình tải. Các phân vị chỉ so được khi cùng tỉ lệ lỗi, loại request, interval và cách xử lý timeout.

Nếu muốn xem logging ảnh hưởng độ trễ đầu cuối, dùng request tracing/metrics ở cùng điểm đo. Không chỉ đo nội bộ Java method nếu thời gian đợi socket, queue hoặc downstream chiếm phần lớn latency.

## 12. Dùng JFR và profiler để tìm phần chi phí đắt

Với JVM đang chạy, **JFR** giúp trả lời “CPU/allocation đang tiêu ở đâu?”. Các nhóm điểm cần quan sát:

- Stack trace có logger, formatter, JSON encoder hoặc exception rendering.
- Allocation của message/object/context, đặc biệt dưới mức DEBUG/TRACE.
- File write hoặc socket write và mức thời gian chặn trên luồng request.
- Thread state/lock contention quanh appender và các hàng đợi.
- GC pause và tốc độ cấp phát ở thời điểm thay logging level.
- Async consumer threads: CPU và I/O tiêu ở worker dù request thread trả nhanh.

Ví dụ lệnh mang tính **hướng dẫn** cho môi trường có `jcmd`, quyền attach tới JVM và JFR được hỗ trợ:

```bash
jcmd <PID> JFR.start name=logging-study settings=profile duration=60s filename=logging-study.jfr
```

Giải thích: thay `<PID>` bằng PID thật của tiến trình Java; recording tạo ra file để mở bằng JDK Mission Control hoặc công cụ phân tích tương thích. Tùy JVM/JDK, tên sự kiện và mặc định có thể khác. Cấu hình `profile` có thêm overhead so với `default`; nên đo với và không có công cụ profiler khi cần biết tác động của chính phép quan sát.

Không xuất hiện stack logging trong mẫu CPU **không chứng minh overhead bằng 0**: sampling có thể không bắt được đoạn rất ngắn; I/O wait, lock hoặc allocation cần các góc quan sát khác.

## 13. Phân biệt framework, version và cấu hình sink

Một phép đo có ý nghĩa phải nêu **backend logging đang thực sự chạy**:

- **SLF4J** là facade API; backend như Logback, Log4j2 hoặc JUL adapter mới thực hiện cơ chế lọc/xuất thực tế.
- **Logback** có logger level, filter, encoder, appender và tùy chọn `AsyncAppender`. Các tùy chọn queue/discard/neverBlock thay đổi cả chi phí và xác suất mất event.
- **Log4j2** có các đường đồng bộ/bất đồng bộ, layout và filter, với các cấu hình hàng đợi/ring buffer tùy version. Không dùng số benchmark Log4j2 để khẳng định về Logback.
- **JUL** có logger, handler và level riêng; hiệu năng bị ảnh hưởng bởi handler, formatter và bridge.
- **Spring Boot** có cấu hình logging mặc định và có thể dùng starter backend khác nhau; việc đổi `logging.level.*` chỉ điều chỉnh level chứ không thay thế đầy đủ cấu hình appender/sink.

Đừng so “Logback nhanh hơn Log4j2” chỉ từ hai cấu hình không tương đương: một bên ghi console JSON, bên kia ghi no-op text thì không có căn cứ. Cần cân bằng throughput, latency, CPU, allocation, event delivery, định dạng và độ an toàn khi quá tải.

## 14. Benchmark các trường hợp hay gây hiểu nhầm

| Hiện tượng đo được | Vì sao dễ hiểu sai | Cách sửa phép đo |
| --- | --- | --- |
| Disabled logger rất nhanh | Đối số toàn hằng hoặc JIT loại nhánh | Thêm kịch bản đối số tốn chi phí và dữ liệu đầu vào thực tế |
| Debug vẫn tốn CPU dù level OFF | Tính `toString()`/JSON trước lệnh logger | Dùng lazy evaluation hoặc kiểm tra level đúng chỗ |
| Async nhanh nhưng log biến mất | Queue đầy, discard policy hoặc shutdown thiếu drain | Đo attempted/enqueued/written/dropped và backlog |
| Ghi console chậm bất thường | Terminal/IDE/stdout collector làm bottleneck | Đo console riêng và trên môi trường triển khai thật |
| File appender có overhead thấp trong microbenchmark | OS page cache hoặc buffer che chi phí flush/disk | Đo dưới tải dài, rotation, flush và trạng thái disk |
| Benchmark chênh lệch liên tục | JIT, GC, scheduler, CPU frequency, noise | Fork/warmup/lặp đủ, báo phân tán, cố định môi trường |
| Chỉ số ns/op rất tốt nhưng p99 request xấu | Queue đầy hoặc lock contention ở tải cao | Load test concurrency và queue wait p99 |
| GC tăng sau bật DEBUG | Nhiều message/event/stack trace allocations | JFR/JMH allocation profiler, so same workload |
| Logger bị tắt nhưng message vẫn được tạo | Java đánh giá đối số trước method call | Kiểm tra call-site eager/lazy bằng đếm hoặc profiler |
| Không thấy log trong file sau benchmark | Filter ở appender, lỗi sink hoặc event bị drop | Kiểm tra pipeline và state của backend |
| So sánh CPU% trên máy khác nhau | Số core/capacity khác, tải khác | Dùng CPU time và host cố định |
| Ít log hơn làm ứng dụng nhanh hơn | Đã thay yêu cầu quan sát/retention | Báo số event delivered và mục tiêu chất lượng log |

## 15. Các biện pháp giảm overhead có cơ sở

### Giảm công việc không cần thiết ở call-site

- Dùng đúng mức log; không bật DEBUG/TRACE diện rộng khi chỉ cần INFO hoặc WARN.
- Khi tạo thông điệp đắt, kiểm tra level hoặc dùng supplier/lazy API phù hợp. Chú ý Java vẫn đánh giá các tham số được truyền như biểu thức thông thường.
- Tránh log quá nhiều trong vòng lặp cực nóng; cân nhắc aggregate/metric cho sự kiện có tần suất cao, nhưng giữ log chi tiết tại điểm cần điều tra.
- Đừng gọi `toString()` trên object lớn chỉ để in “cho chắc”. Với structured logging, chọn trường có giá trị thay vì serialize nguyên object.
- Hạn chế stack trace ở nơi thật sự không cần; vẫn giữ nguyên nhân/stack cho lỗi quan trọng.

### Tối ưu formatter và đầu ra

- Chọn encoder/pattern/JSON fields đủ dùng; cẩn thận với location/caller data có thể đắt.
- Đo chi phí MDC/trace context và các trường được copy cho async event.
- Dùng buffer/batch khi phù hợp; hiểu đánh đổi về độ trễ đưa log tới backend và mất dữ liệu khi process chết.
- Cân nhắc async appender khi sink làm chậm request, nhưng cấu hình queue bounded, policy khi đầy và shutdown drain.
- Có rotation/retention và giám sát lỗi file/collector để chi phí I/O không tăng không kiểm soát.
- Với access log lưu lượng lớn, tránh ghi body/header nhạy cảm; dùng route template và trường cần thiết.

### Không hy sinh khả năng điều tra

Tối ưu không nên là “tắt mọi WARN/ERROR” hoặc drop lặng lẽ khi queue đầy. Mục tiêu là **đạt ngân sách latency/CPU và đủ dữ liệu vận hành**. Khi tăng mức lọc, ghi rõ lớp log bị loại và điều kiện bật lại, bảo đảm có metric/trace bổ sung để không làm mù quan sát hệ thống.

## 16. Một mẫu báo cáo đo overhead có thể kiểm chứng

Một báo cáo nên ghi:

| Mục | Cần điền |
| --- | --- |
| Mục tiêu | Ví dụ: tác động của DEBUG ở `com.example.payment` |
| Hệ thống | JDK 17/21, backend logging/version, heap/GC, CPU, OS/container |
| Workload | Endpoint và tỉ lệ request, concurrency, arrival rate, payload |
| Cấu hình log | Level, message mix, encoder, sink, queue/discard/flush |
| Baseline | Kết quả OFF/INFO ở cùng tải |
| Kết quả | Call-site latency, CPU, allocation, p95/p99, throughput |
| Độ tin cậy | Số lần chạy, biến động, số request lỗi/timeouts |
| Delivery | Attempted/enqueued/written/dropped, backlog, lag |
| Kết luận | Chi phí được quan sát, nguồn chi phí có bằng chứng, giới hạn |
| Quyết định | Giữ INFO, mở DEBUG có thời hạn, tối ưu formatter hoặc thay sink |

Ví dụ kết luận có kiểm soát:

> “Ở cùng tải kiểm thử, bật DEBUG cho package payment làm throughput thấp hơn khoảng 8% và p95 cao hơn 2 ms. CPU tăng 13 điểm phần trăm. Log không bị drop trong cửa sổ đo đã kiểm tra. JFR cho thấy phần allocation tăng có liên quan tới định dạng payload. Cần lặp lại thử nghiệm dưới tải cao và xác nhận hành vi khi sink chậm trước khi áp dụng lâu dài.”

Nếu chưa đo JFR hoặc chưa đếm dropped events, **không viết** những mệnh đề đó như sự thật. Mẫu trên chỉ minh họa cách báo cáo khi đã có đủ chứng cứ.

## 17. Checklist trước khi kết luận về overhead logging

- [ ] Đã nói rõ đo **call-site**, **event processing**, **sink** hay **end-to-end delivery**, không dùng lẫn.
- [ ] Đã ghi chính xác framework/backend và cấu hình level, filter, encoder, async policy.
- [ ] Baseline và treatment chạy cùng workload, cùng tài nguyên, có warmup và nhiều lượt.
- [ ] Đã kiểm tra eager vs lazy message evaluation, không bỏ sót chi phí tính đối số.
- [ ] Đã đo CPU/allocations/GC ngoài elapsed wall time.
- [ ] Đã đo latency ứng dụng (p50/p95/p99), throughput và error rate khi mở logging.
- [ ] Với async, đã quan sát queue depth, enqueue wait, consumer lag và dropped events.
- [ ] Với sink thực, đã đo cả file/stdout/network throughput, lỗi ghi và chính sách flush.
- [ ] Đã tách event *attempted*, *accepted* và *delivered*; không đánh đồng enqueue với bền vững.
- [ ] Đã chạy tải cao, burst log, sink chậm và shutdown để thấy trường hợp xấu.
- [ ] Kết quả có đơn vị, số lần chạy, phân tán và giới hạn, không kết luận quá mức.
- [ ] Tối ưu vẫn giữ được log quan trọng và tránh ghi dữ liệu nhạy cảm.

**Ghi nhớ:** đo overhead logging tốt phải trả lời hai câu riêng: **logging tốn thêm bao nhiêu tài nguyên của ứng dụng** và **những sự kiện log nào thật sự tới nơi cần đến**. Một số `ns/op` thấp nhưng queue đầy hoặc log bị drop không đủ chứng minh hệ thống logging vận hành tốt.

### Tài liệu tham khảo

- [Java 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html)
- [OpenJDK JMH](https://github.com/openjdk/jmh)
- [Java Flight Recorder (JFR)](https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder.html)
- [Logback performance](https://logback.qos.ch/performance.html)
- [Apache Log4j2 performance](https://logging.apache.org/log4j/2.x/manual/performance.html)
