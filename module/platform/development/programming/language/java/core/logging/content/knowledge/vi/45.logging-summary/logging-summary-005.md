# Checklist hiệu năng Java Logging: từ chi phí mỗi lời gọi đến pipeline production

## 1. Mục tiêu của checklist

**Checklist hiệu năng Java Logging** là bộ câu hỏi và phép kiểm chứng để đảm bảo hệ thống ghi log **đủ hữu ích để quan sát** nhưng không gây chi phí CPU, heap/GC, độ trễ, I/O, network, queue và lưu trữ vượt ngưỡng chấp nhận. Đây là bài **tổng kết Java Logging**: người học phải biết không chỉ viết API logger mà còn đo được tác động của logger, formatter, appender, shipper và backend đến ứng dụng.

Một hệ thống “nhanh” nhưng bỏ hết WARN/ERROR hoặc đánh mất audit log không phải là tối ưu thành công. Ngược lại, ghi mọi object, request body và stack trace trên mỗi thao tác có thể làm giảm throughput và tạo rủi ro bảo mật. Mục tiêu là cân bằng **tính hữu ích, mức độ an toàn, mức độ tin cậy và chi phí**.

**Phạm vi checklist:**

- Java 17+; JUL (`java.util.logging`), SLF4J với Logback, Log4j 2.
- Logger API, level/filters, parameterized logging, `Supplier` và điều kiện đánh giá đối số.
- Encoder/layout, exception, structured fields, MDC/ThreadContext.
- Synchronous vs asynchronous appenders, queue, batch, drops và shutdown.
- stdout/stderr, file, disk/rotation, network/OTLP/Collector, backend ingest và query.
- Benchmark, load test, profiling, metrics, budget, bảo mật và release gates.

**Nguyên tắc nền:** Mọi thay đổi đều phải có **baseline và kết quả đo lại** trong môi trường tương đương. Tăng throughput nhưng làm mất event quan trọng hoặc tăng độ trễ p99 là một regression theo góc nhìn vận hành.

## 2. Checklist nhanh trước release

Dùng các ô đánh dấu sau làm cổng review. Các mục có mức ưu tiên cao được đánh dấu **Bắt buộc** theo chính sách ví dụ của bài học; dự án thật phải gắn với SLO, threat model, logging contract và phân quyền đã phê duyệt.

- [ ] **Bắt buộc:** Xác định nhóm log phải giữ (security/audit/error) và nhóm có thể filter/sampling (diagnostics).
- [ ] **Bắt buộc:** Không nối chuỗi/serialize payload tốn chi phí trước lời gọi DEBUG/TRACE thường bị tắt.
- [ ] **Bắt buộc:** Dùng template phù hợp API: JUL `{0}`, SLF4J/Log4j 2 `{}`; phân biệt formatter với tính đối số.
- [ ] **Bắt buộc:** Không ghi token, password, raw headers/body hoặc PII ngoài policy, kể cả khi bật DEBUG.
- [ ] **Bắt buộc:** Có giới hạn cho queue, batch, kích thước event và tổng volume log.
- [ ] **Bắt buộc:** Hiểu chính sách khi queue đầy, exporter 429/503, disk full, shutdown/crash; không ngầm hứa zero loss.
- [ ] **Bắt buộc:** Có metrics cho log dropped/rejected, queue depth, retry, exporter failure và ingest lag.
- [ ] **Bắt buộc:** Chạy kiểm tra throughput, p95/p99 latency, allocation/GC với logging ở cấu hình dự kiến.
- [ ] Cố định hoặc ghi rõ backend, version, encoder, appender, log level, sink và số thread trong phép đo.
- [ ] Cảnh báo log storm, high-cardinality fields, stack trace lặp và duplicate event.
- [ ] Có kiểm tra correctness: message, level, exception, correlation, dữ liệu bí mật và count.
- [ ] Có khả năng bật diagnostic log có giới hạn thời gian và tự quay về cấu hình bình thường.
- [ ] Có kế hoạch rollback khi performance/observability regression sau release.
- [ ] Có bằng chứng rằng pipeline đến Collector/backend vẫn tìm kiếm được log quan trọng.

**Lưu ý:** Danh sách này là điểm bắt đầu. Các mục về durability/audit không thể giải quyết bằng tối ưu logger API mà phải được thực thi ở đúng storage/workflow.

## 3. Chọn mục tiêu đo trước khi tối ưu

Hãy ghi rõ **số đo nào được phép xấu đi và mức nào là không chấp nhận**.

| Nhóm | Chỉ số | Mục tiêu của bài đo |
| --- | --- | --- |
| Ứng dụng | Requests/s hoặc jobs/s | Không giảm throughput ngoài budget |
| Ứng dụng | p50/p95/p99 request latency | Không tăng đuôi trễ do I/O hoặc queue |
| CPU | CPU utilization, cycles spent formatting | Tìm hot spots liên quan logging |
| Heap/GC | Allocated bytes/op, young GC rate, pause time | Kiểm tra string/object churn |
| Logging | Log calls/s theo level, filtered/s, accepted/s | Biết log thực sự phát ra bao nhiêu |
| Logging | Message bytes/event, bytes/s | Đo tác động encoder và sink |
| Async | Queue occupancy, enqueue wait, drop/discard | Xác định saturation |
| Sink | File write latency/throughput, stdout blocking | Tìm nghẽn I/O |
| Collector | Receive/refused, export/sent/failed, retries | Biết record có rời pipeline không |
| Backend | Ingest lag, indexed/queryable records, indexing errors | Phân biệt “đã gửi” và “đã lưu” |
| An toàn | Secret leak, data classification, audit completeness | Đảm bảo tối ưu không làm hỏng hợp đồng |

**Đo theo workload thực tế:** một route đọc cache và một batch job xử lý 100.000 records khác nhau về mức độ log. Benchmark chỉ có một thread/câu INFO đơn giản có thể che mất contention trong production. Thử thêm 1, 4, 16 hoặc số concurrent workers tương đương deployment thật; không lấy con số đó làm ngưỡng áp dụng chung.

Đặt baseline **trước khi đổi** encoder, log level, queue size hay async mode. Mỗi kết quả phải ghi JDK version, JVM flags, machine/container CPU limit, GC, logging dependencies, output sink, volume, ngày kiểm thử và phương pháp đo.

## 4. Bản đồ đường dữ liệu và nơi phát sinh chi phí

~~~text
Business code
    │ argument evaluation, toString/serialization
    ▼
Logger API / facade
    │ level, markers, filters
    ▼
Logging event
    │ template + parameters + MDC + exception
    ▼
Formatter / JSON encoder
    │ CPU, allocations, stack trace processing
    ▼
Sync handler / async queue
    │ lock/contention, enqueue, block, discard
    ▼
Console / rolling file / network exporter
    │ syscall, disk, stdout buffering, TLS/network
    ▼
Container runtime / shipper / Collector
    │ parse, multiline, enrich, batch, retry
    ▼
Backend / index / storage
    │ ingest, indexing, retention, query
~~~

Mỗi tầng có thể tạo chi phí khác nhau. Nếu log call nhanh nhưng collector queue tăng tới mức drop, benchmark riêng API sẽ **báo kết quả đẹp nhưng hệ thống kém tin cậy**. Nếu appender đồng bộ gọi I/O chậm trong request thread, độ trễ p99 có thể tăng dù CPU không cao.

**Cần ghi rõ ranh giới đo:**

- **Caller cost:** thời gian ở lời gọi logger trên thread nghiệp vụ.
- **Encode cost:** thời gian tạo text/JSON từ LogEvent.
- **Enqueue cost:** chi phí đẩy vào async queue, có thể chờ khi đầy.
- **Delivery/ingest cost:** cho đến Collector/backend, thường bất đồng bộ.
- **Total application cost:** throughput và tail latency của request/worker.
- **Operational cost:** bytes/s, index size, tiền lưu trữ, rủi ro dữ liệu và thời gian điều tra.

Một phương án tăng tốc caller bằng async có thể **chỉ chuyển** CPU/memory/I/O sang thread khác, chứ không làm chúng biến mất.

## 5. Checklist API: tránh tạo chuỗi khi level đã tắt

Anti-pattern:

~~~java
// SLF4J/Log4j 2: nối chuỗi trước khi logger nhận đối số.
log.debug("order=" + orderId + " state=" + expensiveState());
~~~

Ngay cả khi DEBUG off, Java vẫn đánh giá `expensiveState()`. Việc tối ưu string concatenation của JDK mới không được phép xóa những lời gọi có hiệu ứng quan sát được.

Ưu tiên với giá trị có sẵn:

~~~java
// SLF4J hoặc Log4j 2.
log.debug("order={} state={}", orderId, state);
~~~

**Nhưng không kết luận mọi thứ đều lazy:**

~~~java
// Vẫn tính expensiveState() TRƯỚC khi Logger.debug chạy.
log.debug("order={} state={}", orderId, expensiveState());
~~~

Khi đối số đắt, dùng guard:

~~~java
if (log.isDebugEnabled()) {
    log.debug("order={} state={}", orderId, expensiveState());
}
~~~

Hoặc SLF4J **2.x Fluent API**:

~~~java
log.atDebug()
        .addArgument(orderId)
        .addArgument(() -> expensiveState())
        .log("order={} state={}");
~~~

Các snippet cần logger và hàm domain đã định nghĩa, **không chạy chỉ bằng JDK**; `log.atDebug()` ở đây thuộc SLF4J 2.x. Với Log4j 2, dùng Supplier overload/API phù hợp với phiên bản. Với JUL:

~~~java
// JUL dùng {0}, không dùng {} của SLF4J.
LOG.log(java.util.logging.Level.FINE, "order={0}", orderId);

// Trì hoãn tính toàn bộ message:
LOG.fine(() -> "state=" + expensiveState());
~~~

**Checklist chi tiết:**

- [ ] Không gọi `String.format(...)`, `MessageFormat.format(...)`, JSON serializer hay `toString()` đắt trong DEBUG/TRACE argument trước khi check level.
- [ ] Kiểm tra mọi lời gọi `log.debug("x={}", expensive())`: placeholder trì hoãn **format**, không trì hoãn **tính argument**.
- [ ] Không đặt business side effects bên trong biểu thức chỉ dùng để log.
- [ ] Chỉ dùng guard/Supplier cho nơi mang lại lợi ích; với biến primitive/immutable có sẵn, template thường đủ.
- [ ] Guard level không bảo đảm mọi filter/appender downstream sẽ nhận event; không quảng cáo nó là transaction guarantee.

## 6. JUL, SLF4J và Log4j 2 khác nhau ở điểm đo

| API | Placeholder thông thường | Trì hoãn message/argument | Tầng cần kiểm thử |
| --- | --- | --- | --- |
| JUL (JDK 17) | `{0}`, `{1}` qua `MessageFormat` | `Logger.fine(Supplier<String>)`, `log(Level, Supplier<String>)` | `LogRecord`, `Handler`, `Formatter` |
| SLF4J 1.7 facade | `{}` | Parameterized; guarded expensive calculations | Provider/Logback/Log4j 2 backend |
| SLF4J 2.x | `{}` | Fluent `addArgument(Supplier<?>)` | `LoggingEventBuilder` + provider |
| Logback Classic | Theo SLF4J | Backend có layouts/async appenders riêng | `ILoggingEvent`, appender và encoder |
| Log4j 2 API/Core | `{}` với parameterized message thông dụng | Supplier APIs, async components | `LogEvent`, message factory, layout/appender |

Không benchmark “SLF4J” mà không ghi **provider/backend**. SLF4J là facade, chi phí thực còn phụ thuộc Logback hoặc Log4j 2, pattern/JSON encoder, filters và sinks. Tránh kết luận một backend luôn nhanh hơn backend khác dựa trên microbenchmark không tương đương.

**Checklist:**

- [ ] Tên logger, hierarchy và effective level đúng.
- [ ] Tầng appender/handler cũng có filter/ngưỡng level phù hợp.
- [ ] Không có cấu hình additivity/parent handlers tạo duplicate output.
- [ ] Trong test, không thay root logger toàn JVM rồi ảnh hưởng các test khác.
- [ ] Logging framework/version và số thread load test giống runtime dự kiến.
- [ ] Không nhầm `LogRecord.getMessage()` (template) với text sau `Formatter.formatMessage`.

## 7. Ví dụ Java 17 độc lập: kiểm tra công việc vô ích khi FINE off

Đây là chương trình runnable, **không cần thư viện ngoài JDK 17**. Nó dùng `AtomicInteger` để đếm số lần gọi hàm, không tự nhận mình là benchmark tốc độ. Bài test xác minh:

1. Khi `FINE` bị tắt, nối chuỗi và gọi hàm argument trực tiếp vẫn chạy **10 lần** qua 5 vòng.
2. `Supplier` và `isLoggable` **không gọi** hàm lazy khi `FINE` bị tắt.
3. Khi bật `FINE`, Supplier được gọi và message đến `Handler` trong bộ nhớ.
4. JUL format `{0}`, `{1}` đúng qua `Formatter.formatMessage`.
5. Handler có thể thu 2 events; không phụ thuộc console, file, network hoặc tốc độ máy.

### 7.1. Tạo LoggingPerformanceChecklistLab.java

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LoggingPerformanceChecklistLab {
    private static final Logger LOG = Logger.getLogger("lab.logging.performance");
    private static final AtomicInteger EAGER_CALLS = new AtomicInteger();
    private static final AtomicInteger LAZY_CALLS = new AtomicInteger();

    private static String eagerValue() {
        return "eager-" + EAGER_CALLS.incrementAndGet();
    }
    private static String lazyValue() {
        return "lazy-" + LAZY_CALLS.incrementAndGet();
    }

    record Captured(Level level, String rendered) {}

    static final class CapturingHandler extends Handler {
        private final List<Captured> events = new ArrayList<>();
        private final Formatter messageOnly = new Formatter() {
            @Override public String format(LogRecord record) {
                return formatMessage(record);
            }
        };
        CapturingHandler() { setLevel(Level.ALL); }
        @Override public void publish(LogRecord record) {
            if (!isLoggable(record)) return;
            events.add(new Captured(
                    record.getLevel(), messageOnly.format(record)));
        }
        @Override public void flush() {}
        @Override public void close() {}
        List<Captured> snapshot() { return List.copyOf(events); }
    }

    static void require(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        CapturingHandler sink = new CapturingHandler();
        boolean oldParent = LOG.getUseParentHandlers();
        Level oldLevel = LOG.getLevel();
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);
        LOG.addHandler(sink);
        try {
            for (int i = 0; i < 5; i++) {
                LOG.fine("concat=" + eagerValue());
                LOG.log(Level.FINE, "param={0}", eagerValue());
                LOG.fine(() -> "supplier=" + lazyValue());
                if (LOG.isLoggable(Level.FINE)) {
                    LOG.fine("guard=" + lazyValue());
                }
            }
            require(EAGER_CALLS.get() == 10, "eager arguments");
            require(LAZY_CALLS.get() == 0, "disabled Supplier/guard");
            require(sink.snapshot().isEmpty(), "disabled records");
            System.out.printf(
                    "DISABLED eagerCalls=%d lazyCalls=%d emitted=%d%n",
                    EAGER_CALLS.get(), LAZY_CALLS.get(), sink.snapshot().size());

            LOG.setLevel(Level.FINE);
            LOG.fine(() -> "supplier=" + lazyValue());
            LOG.log(Level.INFO, "order={0} state={1}",
                    new Object[]{"ORD-42", "PAID"});
            List<Captured> events = sink.snapshot();
            require(events.size() == 2, "enabled event count");
            require(events.get(0).level() == Level.FINE
                    && events.get(0).rendered().equals("supplier=lazy-1"),
                    "enabled Supplier message");
            require(events.get(1).level() == Level.INFO
                    && events.get(1).rendered().equals(
                            "order=ORD-42 state=PAID"),
                    "parameterized JUL rendering");
            System.out.printf(
                    "ENABLED eagerCalls=%d lazyCalls=%d emitted=%d%n",
                    EAGER_CALLS.get(), LAZY_CALLS.get(), events.size());
            System.out.println("LAST=" + events.get(1).rendered());
        } finally {
            LOG.removeHandler(sink);
            LOG.setUseParentHandlers(oldParent);
            LOG.setLevel(oldLevel);
            sink.close();
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 LoggingPerformanceChecklistLab.java
java LoggingPerformanceChecklistLab
~~~

**Stdout chính xác:**

~~~text
DISABLED eagerCalls=10 lazyCalls=0 emitted=0
ENABLED eagerCalls=10 lazyCalls=1 emitted=2
LAST=order=ORD-42 state=PAID
~~~

**Stderr:** trống; **exit code:** `0` khi assertions đúng.

### 7.2. Kết luận đúng từ bài lab

- Năm vòng có hai lời gọi eager mỗi vòng: `5 × 2 = 10`. Vì `FINE` bị tắt, **không có event nào tới handler**, nhưng hai hàm vẫn đã chạy.
- Supplier và guard chỉ tạo work khi level cho phép; trong giai đoạn disabled chúng không chạy.
- Khi bật FINE, Supplier chạy một lần, event thứ nhất là `supplier=lazy-1`.
- Event thứ hai là `INFO`, formatter chuyển template `order={0} state={1}` thành `order=ORD-42 state=PAID`.
- Kết quả **không đo allocation, nanoseconds/op hay throughput**. Code chạy đồng bộ, một thread và sink in-memory; đây là **correctness test về lazy evaluation**, không thể dùng để tuyên bố Logback/Log4j 2, stdout hay exporter nhanh bao nhiêu.

**Cảnh báo đồng thời:** `ArrayList` trong `CapturingHandler` là fixture một thread. Nếu viết load test đa luồng, cần collector thread-safe, data snapshot và mốc hoàn tất phù hợp; không đọc danh sách không được đồng bộ rồi suy luận kết quả đúng.

## 8. Chi phí tạo message, StringBuilder và JDK 17

Một lỗi code review thường gặp là đổi:

~~~java
log.debug("id=" + id + " state=" + state);
~~~

thành:

~~~java
log.debug(new StringBuilder().append("id=").append(id)
        .append(" state=").append(state).toString());
~~~

Điều này **không giải quyết** việc tính message trước lời gọi logger. JVM/JDK hiện đại có tối ưu hóa string concatenation; số lượng allocation không thể suy ra chỉ từ số dấu `+`. Tối ưu đúng là **không thực hiện công việc vô ích**:

~~~java
log.debug("id={} state={}", id, state); // SLF4J/Log4j 2
~~~

Nếu `state` cần gọi `expensiveState()`, phải guard/Supplier. `String.format`, `MessageFormat.format`, JSON serialization, `Arrays.deepToString`, `Collectors.joining` và custom `toString()` cũng là tính trước nếu gọi trực tiếp.

**Đánh giá từng trường hợp:**

- Giá trị `String` đã có sẵn: templates là đủ trong đa số trường hợp.
- Primitive/object nhỏ: chi phí varargs/boxing và phương thức logger có thể tồn tại; đo nếu hot path đặc biệt nhạy cảm.
- Object lớn/mutable: không dump toàn bộ chỉ để điều tra; dùng summary đã allowlist và giới hạn độ dài.
- Hàm đọc file/DB/network: **không làm công việc này chỉ để ghi DEBUG** trừ khi có thiết kế/guard và tác động được đánh giá.
- Exception: truyền `Throwable` đúng overload, không tạo chuỗi từ `exception.toString()` hoặc stack trace ngay từ caller.

Đừng biến mọi `log.debug` thành một khối `if` dài nếu đối số rẻ. Giữ code đọc được và dùng profiler để tập trung vào hot spots.

## 9. Các nhóm log và mức độ nên phát

| Nhóm sự kiện | Mức logging phù hợp theo policy | Đánh đổi hiệu năng |
| --- | --- | --- |
| Event lifecycle ít xảy ra, có ý nghĩa | INFO | Hữu ích để chẩn đoán, volume vừa phải |
| Tình trạng bất thường có thể phục hồi | WARN/WARNING | Không spam theo mọi vòng retry |
| Thất bại có ảnh hưởng | ERROR/SEVERE | Giữ exception/correlation cần thiết, tránh duplicate |
| Chi tiết branch/biến nội bộ | DEBUG/FINE | Bật có mục đích và giới hạn |
| Bước rất chi tiết trong loops/IO | TRACE/FINER/FINEST | Có thể volume cực cao; thường off |
| Security/audit quan trọng | Kênh/event schema riêng theo policy | Không phụ thuộc chỉ vào DEBUG level |

**Không tối ưu bằng cách tắt mọi ERROR/AUDIT.** Nếu nghiệp vụ cần dấu vết bắt buộc, phải lựa chọn durable recorder/stream với retention và bảo vệ thích hợp. Log trên console có thể best-effort; không thay thế transaction outbox/audit store nếu cần giao nhận cùng giao dịch.

**Checklist:**

- [ ] Không phát INFO trong inner loop cho từng item nếu chỉ cần summary/batch statistics.
- [ ] Cùng một exception không bị ghi ERROR ở service, controller và worker liên tiếp nếu contract chỉ yêu cầu một logical failure.
- [ ] Retry attempts được biểu diễn bằng `attempt`/`reasonCode` và có rate limit nếu có thể tạo storm.
- [ ] Sự kiện quan trọng vẫn hiện diện ở cấu hình production (level/filter/sampling).
- [ ] Các thay đổi level động có người phê duyệt, phạm vi, thời hạn và cách revert.

## 10. Chi phí trong hot loops và N+1 logging

Ví dụ:

~~~java
// Anti-pattern trong một vòng lặp xử lý số lượng lớn.
for (Order order : orders) {
    log.info("processing order={}", order.id());
    process(order);
}
~~~

Đây là code minh họa với `orders`, `Order`, `log`, `process` đã định nghĩa. Nếu mỗi batch xử lý 100.000 orders, nó tạo ít nhất 100.000 events INFO, chưa kể retries, exception logs và infrastructure logs.

Phương án thay thế tùy mục đích:

~~~java
long processed = 0, failed = 0;
for (Order order : orders) {
    try {
        process(order);
        processed++;
    } catch (RecoverableOrderException e) {
        failed++;
        // Chỉ ghi per-item nếu cần điều tra và được phép.
        // Giữ safe order reference/reason code trong nhánh lỗi.
    }
}
log.info("batch processed={} failed={}", processed, failed);
~~~

Snippet cần domain `Order`, `RecoverableOrderException` và `process`; không phải một chương trình độc lập. Trong code production phải quyết định rõ retry, xử lý exception và invariant nghiệp vụ trước khi sao chép.

**Checklist:**

- [ ] Đo số **events/business operation** ở peak, không chỉ đo average.
- [ ] Dùng summary theo batch/cửa sổ cho những thông tin tổng hợp.
- [ ] Dùng metrics cho counters/histograms; log cho những events có ngữ cảnh cần đọc.
- [ ] Không sampling audit/security mà chính sách yêu cầu đầy đủ.
- [ ] Có cách bật diagnostic theo service/route/trace có giới hạn để điều tra một trường hợp.
- [ ] Không thay việc lưu business state bằng một “batch succeeded” log khi phải có durability.

## 11. Log format: text, JSON và structured events

Một pattern text đơn giản thường rẻ hơn một encoder JSON đầy tính năng **trong một số workload**, nhưng không thể kết luận tổng chi phí chỉ từ CPU caller. JSON giúp query theo field và giảm parse regex downstream, nhưng có thể phát sinh:

- Chuyển đổi giá trị object, ngày/giờ, number, exception.
- Escaping Unicode/quotes/newlines và kiểm tra field.
- Tạo nhiều key/metadata trên mỗi event.
- Loại/mask dữ liệu nhạy cảm.
- Mapping MDC/ThreadContext, markers và key-value pairs.
- Tăng raw bytes, index cardinality hoặc kích thước storage.

Ví dụ structured event:

~~~json
{
  "timestamp": "2026-11-10T02:00:00Z",
  "service.name": "orders-api",
  "severity": "WARN",
  "event.code": "DEPENDENCY_TIMEOUT",
  "trace_id": "0123456789abcdef0123456789abcdef",
  "reason_code": "DB_TIMEOUT",
  "attempt": 2,
  "duration_ms": 250
}
~~~

**Đây là JSON minh họa**, không có nghĩa raw object này đã là OTLP. Nếu dùng OpenTelemetry, `service.name` thường nằm trong Resource, severity có `SeverityText`/`SeverityNumber`, event fields có thể nằm ở attributes; phải mapping qua bridge/collector đúng.

**Checklist JSON/encoder:**

- [ ] Encoder hỗ trợ UTF-8 và escaping chuẩn; không tự nối raw input thành JSON.
- [ ] Giữ event code ổn định, hạn chế field dư, có schema version khi cần.
- [ ] Không serialize toàn DTO để “đỡ viết field”.
- [ ] Đo bytes/event trước và sau khi chuyển sang structured logs.
- [ ] Test type: `attempt` number, `duration_ms` number, không ép mọi thứ thành string.
- [ ] Test privacy ở output thực của encoder, không chỉ mock event.
- [ ] Kiểm tra parser/Collector cùng schema/version để tránh reject hoặc field explosion.

## 12. Stack trace: chi phí và giá trị điều tra

Một `Throwable` có thể được format thành stack trace nhiều dòng, gồm cause và suppressed exceptions. Nếu lặp lại cho mỗi retry hoặc trong vòng lặp, volume và CPU có thể rất lớn.

~~~java
// Truyền Throwable để backend xử lý đúng cấu trúc.
log.error("request failed code={} attempt={}",
        safeReasonCode, attempt, failure);
~~~

Snippet thuộc SLF4J/Log4j 2 với `log` và các biến đã có. Cần kiểm tra overload/version để `failure` thực sự được nhận là Throwable, không trở thành một argument định dạng ngoài ý định. Với JUL:

~~~java
LOG.log(java.util.logging.Level.SEVERE,
        "request failed", failure);
~~~

**Không khuyến khích** nối `failure` hoặc stack trace thành chuỗi rồi gửi `log.error("... " + failure)`: dễ mất thông tin cause, tăng công việc eager và có thể lộ dữ liệu qua `Throwable.getMessage()`.

**Checklist:**

- [ ] Một logical failure chỉ có số stack trace thực sự cần thiết.
- [ ] Khi retry thường xuyên, dùng reason code/count/metric, không in full stack trace mỗi lần nếu policy không yêu cầu.
- [ ] Không xóa mọi exception chỉ để tiết kiệm bytes nếu điều tra cần cause.
- [ ] Giới hạn log storm, size và quyền truy cập, nhưng không truncate làm mất yếu tố cần thiết mà không có marker.
- [ ] Kiểm tra data minimization trong message/cause/suppressed exceptions.
- [ ] Đo CPU/allocated bytes của exception layout ở enabled logging.

## 13. MDC/ThreadContext: tiện ích và chi phí

MDC trong SLF4J/Logback và ThreadContext trong Log4j 2 cung cấp context như `trace_id`, `request_id`, `tenant_ref` (khi được phép). Context giúp tìm log nhanh nhưng có overhead khi cập nhật, sao chép/propagate và serialize.

Với SLF4J:

~~~java
// Trong một request scope; slf4j-api cần được đưa vào dependencies.
try (org.slf4j.MDC.MDCCloseable close =
             org.slf4j.MDC.putCloseable("request_id", safeRequestId)) {
    processRequest();
}
~~~

Đây là snippet không độc lập; cần hàm `processRequest` và `safeRequestId`. Lưu ý `MDC.putCloseable` khôi phục/loại key khi đóng theo API, nhưng nếu code thay đổi cùng key ở giữa cần đọc kỹ semantics và kiểm tra provider. Với thread pools/reactive/async tasks, **MDC không tự động propagate qua mọi ranh giới**; context phải được truyền/snapshot theo đúng framework.

**Checklist:**

- [ ] Context chỉ có fields hữu ích, đã allowlist và không chứa PII/secret.
- [ ] Không đặt một JSON payload 100 KB vào MDC để mọi event ghi đi ghi lại.
- [ ] Có cleanup ở cuối scope, tránh leak context giữa requests cùng thread.
- [ ] Context propagation được test cho executor, CompletableFuture, reactive pipelines và message consumers.
- [ ] Không giả định `trace_id` là metric label có cardinality thấp.
- [ ] Đo bytes/event và latency khi thêm nhiều fields MDC/ThreadContext.
- [ ] Không lấy `ThreadLocal` context của consumer hiện tại rồi giả định luôn đúng khi render trên async worker.

## 14. Synchronous logging: khi request thread phải ghi ra sink

Ở chế độ sync, một lời gọi log có thể chờ:

- Lock hoặc contention trong appender/handler.
- Formatter/encoder xử lý JSON, exception, timestamp.
- Stream/file write, flush và syscall.
- Disk/network buffer hoặc stdout pipe khi consumer chậm.
- File rollover, compression hoặc permission errors tùy backend.

**Không suy từ tên “sync” rằng đã fsync hoặc remote commit.** `Writer.flush()`, `OutputStream.flush()` và `FileChannel.force(...)` có phạm vi đảm bảo khác nhau, và còn phụ thuộc filesystem/storage. Flush một appender không chứng minh collector đã index xong.

**Checklist:**

- [ ] Đo p95/p99 latency trên request thread khi INFO/WARN/ERROR bật.
- [ ] Dùng load test gần production với sink thật, không benchmark log vào `/dev/null` rồi khẳng định I/O an toàn.
- [ ] Kiểm tra latency spikes tại rotation và peak log burst.
- [ ] Có giới hạn logging per request/loop để tránh blocking burst.
- [ ] Khi sink lỗi, biết handler có drop, report error, throw, block hay retry.
- [ ] Không bật flush per record chỉ vì “an toàn” mà không hiểu chi phí và durability.
- [ ] Không bỏ qua việc console trong container có thể bị chặn nếu runtime log reader chậm.

## 15. Async logging: nhanh ở caller không phải toàn hệ thống

Async appender/logger thường đưa event vào queue để worker xử lý. Có thể giảm thời gian request thread phải chờ formatter/I/O, nhưng đổi lại:

- Memory và CPU của queue/worker.
- Enqueue/dequeue contention và cache effects.
- Độ trễ từ event time tới sink.
- Queue đầy, event bị discard/block hoặc fallback sync theo policy.
- Mất pending events khi `Runtime.halt`/SIGKILL/process crash.
- Rủi ro snapshot của mutable argument/context và việc render sau.

~~~text
Request threads
    └─ log(event) → bounded queue ─┐
                                  ▼
                             async worker
                                ├─ format/encode
                                └─ write stdout/file/export
                                       │
                                       ▼
                                   Collector
~~~

**Checklist async:**

- [ ] Đã biết mức queue capacity và kích thước event trung bình/max.
- [ ] Đã biết chính sách discard theo level, blocking/fallback khi queue đầy.
- [ ] Có metrics queue depth, enqueue wait, drops/discards và worker errors.
- [ ] Load test cả burst ngắn và tải kéo dài, không chỉ throughput steady state.
- [ ] Sau enqueue, event có thể chưa được xuất; test dùng barrier/drain/await hợp lệ.
- [ ] Có lifecycle shutdown đủ thời gian để drain; không kỳ vọng được flush khi SIGKILL.
- [ ] Có trường hợp lỗi sink và đầy disk để test retry/drops.
- [ ] Có test context snapshot và mutable parameters để log không bị thay nội dung sau emit.

**Đừng tăng queue vô hạn** để tránh drop. Một queue quá lớn có thể tăng heap pressure, OOM và **ingestion lag**, che giấu vấn đề downstream. Phải xác định rõ policy khi không thể giữ tất cả events.

## 16. Logback AsyncAppender và kiểm tra cấu hình

Với **Logback Classic**, `AsyncAppender` bao một appender khác, đẩy event vào queue. Một cấu hình rút gọn để học (cần Logback và ứng dụng đã cấu hình Logback đúng):

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ASYNC"
              class="ch.qos.logback.classic.AsyncAppender">
        <queueSize>1024</queueSize>
        <discardingThreshold>0</discardingThreshold>
        <neverBlock>false</neverBlock>
        <maxFlushTime>5000</maxFlushTime>
        <appender-ref ref="CONSOLE"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="ASYNC"/>
    </root>
</configuration>
~~~

**Không copy config này thành production mặc định.** Các giá trị 1024/5000 ms là **minh họa**, cần sizing theo throughput, tail latency, memory và delivery policy. `discardingThreshold=0` tắt ngưỡng discard dựa vào remaining capacity trong cấu hình Logback phổ biến; **không** có nghĩa queue không thể mất event khi tiến trình chết, appender lỗi hoặc hết khả năng xử lý.

Với Logback Classic, cần hiểu:

- `queueSize` giới hạn số event chờ.
- `neverBlock=false` thường khiến enqueue **block khi queue đầy**, tăng request latency nhưng giảm bỏ event ở tầng đó.
- `neverBlock=true` có thể bỏ event khi queue đầy thay vì chặn caller.
- `discardingThreshold` điều khiển discard mức độ thấp trong điều kiện queue gần đầy; mặc định/version có thể thay đổi. Test semantics bằng runtime version cụ thể.
- `maxFlushTime` là giới hạn chờ worker xử lý backlog khi stop; **không** bảo đảm durability khi kill/power loss.
- `AsyncAppender` không phải durable broker; event còn trong RAM có thể mất.

**Kiểm thử thực:** Sinh nhiều DEBUG/INFO/WARN/ERROR events, đo queue, drops, p99, memory và số event xuất cuối trong từng loại; kiểm thử graceful stop và cưỡng bức riêng.

## 17. Log4j 2 AsyncAppender và Async Loggers

Log4j 2 có hai cơ chế khác nhau:

- **AsyncAppender:** nhận LogEvent qua appender có queue.
- **Async Loggers:** cơ chế xử lý bất đồng bộ với ring buffer/Disruptor tùy cấu hình và version.

Đừng gọi chúng tương đương trong benchmark. Cùng một logger API nhưng backend async mode, disruptor dependency, queue size, wait strategy, location information và layout đều có thể làm kết quả thay đổi.

**Checklist:**

- [ ] Đã chọn rõ AsyncAppender hoặc Async Logger, không bật nhiều tầng async vô tình gây queue chồng nhau.
- [ ] Kiểm tra cấu hình và dependency `log4j-core`/`disruptor` cần thiết theo version.
- [ ] Đo queue/ring buffer utilization, blocked producers, drops hoặc lỗi khi queue đầy.
- [ ] Đo throughput và latency cả ở caller **lẫn** lúc sink nhận event.
- [ ] Không bật includeLocation/caller location nếu không cần và chưa đo overhead lấy stack.
- [ ] Tùy config `immediateFlush`, batch/flush và shutdown timeout, đánh giá event loss window.
- [ ] Kiểm tra `ThreadContext` và immutable event snapshots khi qua async.
- [ ] Không so một mẫu AsyncLogger ấm máy với một appender sync đang phải viết file network rồi kết luận loại nào “nhanh hơn tuyệt đối”.

**Quan trọng:** Các defaults/behavior có thể thay đổi theo Log4j 2 version, config và appender target. Đối chiếu tài liệu hiện hành của version dự án và kiểm thử đúng artifact đang deploy.

## 18. stdout/stderr, container runtime và blocking

Trong Kubernetes/container, pattern thường dùng là **ghi JSONL/text ra stdout/stderr**, để runtime/agent thu gom. Điều này đơn giản hơn quản lý nhiều file trong container, nhưng có chi phí riêng:

- Console write vẫn là I/O; pipe/reader có thể chậm hoặc block.
- Runtime có thể thêm wrapper CRI, chia partial lines và xoay log theo giới hạn.
- Ghi một stack trace multiline có thể khiến agent tạo nhiều records nếu parser không ghép.
- Một dòng JSONL có quote/newline chưa escaped có thể phá ranh giới event.
- Sidecar/agent cũng cần CPU, disk và network, không phải miễn phí.
- Nếu vừa ship file **và** stdout chứa cùng event, backend có thể đếm duplicate.

**Checklist:**

- [ ] Ghi đúng stream/formatter; không giả định stderr nghĩa là ERROR trong mọi logger.
- [ ] Kiểm tra cỡ dòng tối đa, CRI partials, Unicode, newline và stack trace parser.
- [ ] Đo stdout byte/s và runtime disk usage ở peak.
- [ ] Đảm bảo node agent đọc kịp trước rotation/TTL cục bộ.
- [ ] Có cảnh báo khi log filesystem gần đầy hoặc shipper backlog tăng.
- [ ] Không dùng `kubectl logs` làm kho retention tập trung; cần backend nếu phải truy vấn dài hạn.
- [ ] Không gắn sensitive debug output vào stdout khi downstream có nhiều người được quyền xem.

## 19. File logging: buffer, rotation, compression và disk

File appender có thể phù hợp cho VM/bare-metal và những môi trường cần log cục bộ, nhưng cần tính:

- Độ trễ write/flush, contention giữa threads, buffer sizes.
- Rollover theo thời gian/kích thước và việc nén archive.
- Số file và tổng bytes giữ cục bộ; disk full và inode exhaustion.
- File permission, rotation với agent đang tail, rename vs copytruncate.
- Lỗi storage và chính sách báo lỗi của appender.
- Local retention so với backend retention/snapshots.

**Không nhầm cơ chế:**

- JUL `FileHandler(limit,count)` xoay theo file size/count, **không phải giữ count ngày**.
- Logback `maxHistory` điều khiển số period archive, `totalSizeCap` có thể xóa sớm hơn kỳ vọng nếu đạt size cap.
- Log4j 2 RollingFile có rolling strategies và Delete action; điều kiện `IfLastModified` dựa vào mtime file, không phải từng event timestamp.
- Khi nén archive, CPU có thể tăng tại rollover, nên benchmark phải bao phủ giai đoạn này.
- Xóa file cục bộ không xóa event đã vào backend; backend xóa index không xóa queue/backup/export tự động.

**Checklist:** Đặt retention/rotation rõ, test file access và shipper checkpoint, disk watermarks, owner của cleaning job và hành động khi gần đầy. Không truncate active audit file để khắc phục tạm nếu chưa qua quy trình bảo toàn và phê duyệt.

## 20. Network exporter, OTLP, retry và pipeline latency

Nếu Java app hoặc agent gửi log qua HTTP/gRPC/OTLP, chi phí nằm ở TLS, batch, connection pools, retry, queue và payload size. Một cuộc gọi logger có thể return nhanh trong khi downstream đang tụt lại hàng giờ.

~~~text
Java app logs
   → OTLP exporter hoặc stdout/file shipper
   → Collector receiver
   → processors (parse/filter/batch/enrich)
   → exporter retry/queue
   → backend ingest/index
~~~

**Checklist:**

- [ ] Rõ đường đi: raw JSONL stdout phải qua agent/filelog parser, **không** gửi như OTLP request rồi kỳ vọng receiver hiểu.
- [ ] Đo event timestamp → Collector observed timestamp → backend searchable timestamp; xét clock skew.
- [ ] Có timeout, backoff, queue cap, auth/TLS và handling với HTTP 429/503.
- [ ] Có quy tắc khi 400 invalid schema: reject/quarantine thay vì retry vô hạn.
- [ ] Bản ghi bị drop/filtered có metric; không chỉ biết số bytes gửi đi.
- [ ] Không tin rằng “exporter HTTP 200” luôn đồng nghĩa backend đã durable/index.
- [ ] Khi ACK bị mất, retry có thể gây duplicate; có event ID/dedup nếu workflow yêu cầu.
- [ ] Collector own telemetry không đẩy một vòng lặp log storm khi downstream đang lỗi.
- [ ] Query canary/test events có ID duy nhất để xác minh pipeline hoàn chỉnh.
- [ ] Kiểm tra backend quota/index reject/retention/query latency, không chỉ metrics của Java.

**Độ trễ ingestion** cần được tách khỏi request latency; một giải pháp caller nhanh nhưng backend searchable trễ không đạt mục tiêu điều tra thời gian thực.

## 21. Log volume, cardinality và storage cost

Một thay đổi tưởng nhỏ như thêm raw payload hoặc stack trace có thể nhân lượng log vài lần.

Cách ước lượng:

~~~text
eventsPerSecond = requestsPerSecond × eventsPerRequest
rawBytesPerSecond ≈ eventsPerSecond × avgBytesPerEvent
rawBytesPerDay = rawBytesPerSecond × 86,400
storedBytes ≈ rawBytesPerDay × measuredStorageFactor × retentionDays
~~~

`measuredStorageFactor` phụ thuộc nén, index overhead, replicas, metadata và backend; **không** phải một hằng số áp dụng chung.

Ví dụ minh họa: `2.000 request/s × 3 events/request × 400 bytes/event ≈ 2,4 MB/s raw`, tương đương khoảng **207,36 GB raw/ngày** theo đơn vị thập phân. Nếu không kiểm soát duplicate/retry, bytes thực tế có thể lớn hơn.

**Cardinality:**

- `service.name`, `environment`, `event_code` thường có tập giá trị hữu hạn, hữu ích cho filter/aggregation.
- `trace_id`, `request_id`, `message_id`, `user_ref` có cardinality rất cao.
- Không đưa IDs chi tiết thành **Prometheus metric labels**; trong backend log cũng cần kiểm tra chiến lược indexing/labels theo công nghệ cụ thể.
- Loki labels không nên chứa trace ID/request ID mỗi event do chi phí streams/index/cardinality; thường giữ dưới dạng structured metadata/body để query khi cần.
- OpenSearch/Elasticsearch dynamic mapping theo fields không kiểm soát có thể gây field explosion và chi phí memory/index.

**Checklist:**

- [ ] Có budget events/s, bytes/s, peak burst và retention theo class.
- [ ] Không có field growth không giới hạn (arbitrary user keys).
- [ ] Không index mọi JSON key vô điều kiện.
- [ ] Giảm duplicate tại nguồn thay vì chỉ tìm cách lưu trữ rẻ hơn.
- [ ] Có chính sách sampling/rate limit cho diagnostics, không áp lên audit bắt buộc.
- [ ] Có alert khi ingest volume tăng đột ngột sau deploy.

## 22. Sampling, rate limit và cách giữ tín hiệu

Một cách tiết kiệm là **sampling** các event nhiều volume nhưng ít cần từng bản riêng. Ví dụ DEBUG từ vòng lặp có thể chỉ giữ mẫu nhỏ, trong khi INFO lifecycle và ERROR có event codes quan trọng cần đầy đủ theo policy.

**Những điều cần phân biệt:**

- **Head sampling theo request/trace:** quyết định sớm theo trace, giúp giữ context nhất quán nếu implement đúng.
- **Log sampling theo level/event:** drop một phần logs theo rule/volume/priority.
- **Rate limiting:** đặt giới hạn logs trên một cửa sổ, có thể giữ counter “suppressed N similar events”.
- **Deduplication:** giảm duplicate logical events hoặc retry copies dựa trên identity đáng tin.
- **Aggregation:** thay nhiều per-item logs bằng thống kê dạng metric/batch summary.

**Checklist:**

- [ ] Biết event nào phải giữ 100% theo nghĩa vụ/audit; không sampling chúng âm thầm.
- [ ] Nếu sampling, có số liệu bao nhiêu records bị bỏ và cơ chế diễn giải query.
- [ ] Quy tắc nhất quán across replicas/collector khi cần.
- [ ] Không dùng một tỷ lệ sampling ngẫu nhiên rồi suy luận số lỗi thực từ count raw không hiệu chỉnh.
- [ ] Khi muốn điều tra một trace đặc biệt, có cơ chế ghi chi tiết giới hạn và bảo vệ dữ liệu.
- [ ] Không để suppression thông báo ERROR/WARN quan trọng biến mất mà không có counter/alert phù hợp.

**Đừng cho rằng sampling luôn tăng độ tin cậy:** giảm volume có thể giúp pipeline khỏe hơn, nhưng làm mất context cần điều tra. Chọn theo event class và nhu cầu truy vấn.

## 23. Backpressure, queue đầy và chính sách mất event

Khi tốc độ tạo log lớn hơn tốc độ sink xử lý:

~~~text
log producer rate > exporter/sink service rate
         → queue depth tăng
         → wait/drop/retry/disk spool theo policy
         → latency, memory, loss hoặc backlog
~~~

**Các chiến lược chính:**

| Policy khi đầy | Ưu điểm | Rủi ro |
| --- | --- | --- |
| Block caller | Giảm việc bỏ tại queue đó | Tăng request p99, có thể ảnh hưởng availability |
| Drop/discard ưu tiên thấp | Bảo vệ request latency/memory | Mất diagnostics; cần metrics và contract |
| Spill to bounded disk | Chống outage ngắn, không đẩy tất cả vào RAM | Disk/quota/checkpoint/IO và quản lý dữ liệu |
| Fallback sync | Có thể giữ event quan trọng khi async lỗi | Đột ngột tăng caller latency |
| Fail operation | Tạo tín hiệu rõ về không ghi được log | Có thể không phù hợp với availability; cần policy cho audit |

Không có câu trả lời đúng cho mọi log. Audit bắt buộc và debug diagnostics có mục tiêu khác nhau. **Đừng nói “không mất” khi queue chỉ ở RAM** hoặc không có cơ chế xác nhận lưu bền vững.

**Bài kiểm thử bắt buộc:** điều gì xảy ra khi sink cố tình chậm hơn 10 lần, backend trả 429/503, disk spool gần đầy, app process bị kill? Ghi rõ mức event loss/latency quan sát được, không chỉ benchmark trong điều kiện lành mạnh.

## 24. GC, allocation và JFR/JMH: benchmark như thế nào?

**JFR (Java Flight Recorder)** và profiler là nơi bắt đầu khi ứng dụng thực có CPU/GC tăng. Tìm hotspots như `StringBuilder/StringConcatFactory`, `toString`, JSON encoder, `ThrowableProxy`/stack trace processing, logger locks, async queue, write syscall và disk/network waits. Điều tra cả giai đoạn disabled và enabled levels.

**JMH (Java Microbenchmark Harness)** phù hợp để đo một tác vụ nhỏ khi muốn so sánh các cách dùng logger:

- Có warmup, measurement, fork, JVM/JDK flags và quản lý dead-code elimination.
- Dùng logging backend/provider và sink tương đương giữa variants.
- Kiểm tra GC allocation rate và benchmark modes phù hợp.
- Không gộp I/O console thật vào một variant rồi chỉ dùng no-op appender ở variant khác.
- Ghi message size, argument types, exception yes/no, threads, level và filter.
- Đo cả call latency và throughput nhưng **không kết luận end-to-end durability** từ JMH.

**Đừng dùng chương trình phần 7 làm benchmark tốc độ.** Counter test ở đó chứng minh tính toán eager/lazy; nó không có warmup/measurement control. Ngược lại, một microbenchmark JMH nhanh **không chứng minh** production latency p99 không xấu khi có disk/network/GC.

**Checklist khi đo:**

- [ ] Warmup đủ, đo nhiều forks/repetitions khi thích hợp.
- [ ] Không tính thời gian startup/class loading vào steady-state mà không ghi rõ.
- [ ] Kết quả có stddev/percentiles/confidence interval, không chỉ một con số tốt nhất.
- [ ] So workload và cấu hình cùng cấp công bằng.
- [ ] Có kiểm tra không bị JIT bỏ đi phép đo không quan sát được.
- [ ] Bao phủ rollover, burst, outage và recovery bằng integration/load test riêng.
- [ ] Bảo mật test fixtures và profiler artifacts cũng được quản lý.

## 25. Load test thực tế: ma trận tối thiểu

| Kịch bản | Cấu hình | Quan sát chính | Tiêu chí đạt |
| --- | --- | --- | --- |
| Baseline | Logger configured nhưng không phát diagnostics | Throughput/latency nền | Làm chuẩn so sánh |
| DEBUG disabled, nhiều call sites | Supplier/guards và eager variants | CPU/calls/allocations | Không tính hàm đắt ngoài ý định |
| INFO steady | Payload nhỏ, sink bình thường | events/s, bytes/s, p95/p99 | Trong budget và đủ events |
| ERROR burst | Nhiều exceptions/stack traces | CPU, GC, queue, sink | Không OOM, có alert/loss policy |
| JSON vs text | Cùng semantic fields/volume | CPU, bytes, parse/schema | Không mất thông tin cần thiết |
| Sync vs async | Cùng sink/format/load | Caller latency, queue, drops | Đánh đổi đã chấp nhận |
| High concurrency | N threads tương đương workload | Lock contention, CPU, tail latency | Không regression vượt SLO |
| File rotation | Chạm mốc size/time | Latency spike, missing events | Lifecycle theo policy |
| Collector throttling | 429/503 tạm thời | Queue/retry/drop/backoff | Không storm/OOM |
| Disk full/permission | Sink error | Handler response, app availability | Có tín hiệu và hành động an toàn |
| Graceful shutdown | Có pending events | Drain, timeout, incomplete | Đúng contract, không hứa kill guarantee |
| SIGKILL/Runtime.halt | Process dừng cưỡng bức | Event loss window | Được hiểu và đánh giá rủi ro |
| Pipeline end-to-end | Query event ID từ backend | Ingest lag, schema, completeness | Queryable trong SLO đã định |

**Đừng dùng một workload chỉ có INFO và response cache** để kết luận cấu hình tối ưu cho ERROR burst. Sự kiện exception đắt hơn message nhỏ; throughput bị chi phối bởi kích thước log và sink.

## 26. Mẫu phiếu đo hiệu năng có thể sao chép

Điền các giá trị **thực đo được** vào mẫu sau (các dấu `<...>` là nhãn cần điền, không phải kết quả đã xác nhận):

~~~text
Experiment: logging-perf-<run-id>
Service/build/JDK: <name>/<version>/<JDK+flags>
Backend/provider: <JUL|Logback|Log4j2 + exact versions>
Sink/encoder: <stdout/file/network + layout/JSON schema>
Levels/filters: <effective logger/appender levels>
Traffic: <requests/s; concurrency; burst length>
Event mix: <DEBUG/INFO/WARN/ERROR ratios; bytes/event>
Baseline p50/p95/p99 latency: <values + units>
Candidate p50/p95/p99 latency: <values + units>
Baseline/candidate throughput: <values + units>
CPU/allocated bytes/op/GC pauses: <measured values>
Queue depth/drops/retry/exporter errors: <measured values>
Backend ingested/queryable events: <count and deadline>
Privacy/correlation/audit checks: <PASS/FAIL with evidence>
Decision/owner/revert plan: <approved or rejected with reason>
~~~

Trước khi tối ưu nên xác định **acceptance budget** của dự án. Ví dụ “p99 không tăng hơn một ngưỡng đã phê duyệt, không bỏ event phải giữ, queue không tăng mãi và backend query nhận các IDs” là một hợp đồng kiểm thử; **không có ngưỡng phần trăm chung** cho tất cả tổ chức.

Nếu test chạy trên shared CI, ghi nhận background load hoặc chạy lại trong môi trường có thể tái lập. So dữ liệu theo cùng phiên bản JDK/GC/CPU quota, không dùng số “cải thiện 40%” từ hai môi trường khác nhau.

## 27. Theo dõi production: telemetry của chính logging pipeline

Một pipeline có thể thoải mái xử lý vài giờ rồi đột ngột backlog; vì vậy **cần liên tục theo dõi health**.

**Tầng JVM/appender:**

- Số events tạo ra theo level và class; filtered/discarded nếu backend cung cấp.
- Queue occupancy và thời gian chờ enqueue.
- Số errors từ file/network appenders.
- Bytes/s và số events/s, kích thước trung bình/max.
- Worker thread errors, shutdown loss nếu có thể quan sát.

**Tầng agent/Collector:**

- Receiver accepted/refused records.
- Parser errors, truncated/oversized events, dropped by filters.
- Exporter sent/failed records, retries, backpressure và queue depth.
- Disk buffer pressure, checkpoint lag, receiver/restart health.
- Ingest lag và số log thiếu resource/trace/event code cần thiết.

**Tầng backend/query:**

- Ingest/index reject và latency, query p95/p99, retention/compaction health.
- Volume/cost theo service, env, event class.
- Duplicated events hoặc expected-but-missing canary events.
- Access errors, tenant isolation và dữ liệu nhạy cảm trong logs.

**Metrics naming phụ thuộc version/distribution.** Không hard-code một tên metric từ ví dụ rồi kết luận pipeline không hoạt động khi metric đó không tồn tại ở Collector đang dùng.

**Alert giá trị:** Queue không ngừng tăng, drop rate vượt policy, raw log bytes tăng sau release, CPU/GC tăng cùng encode, exporter liên tục lỗi, event ID test không thể query đúng deadline.

## 28. Troubleshooting theo triệu chứng

| Triệu chứng | Giả thuyết khả dĩ | Kiểm tra tiếp |
| --- | --- | --- |
| CPU tăng khi DEBUG off | Eager argument `toString/serialize/concat` | Profiler + counter test phần 7 |
| GC tăng nhưng events/s thấp | Payload object/exception/JSON fields quá lớn | Allocation profile, bytes/event |
| p99 request tăng khi log burst | Synchronous sink hoặc async queue block | Thread dumps, queue metrics, syscall latency |
| App nhanh, dashboard chậm | Agent/Collector/exporter/backend backlog | Ingest lag, queue, index rejects |
| WARN/ERROR mất khi peak | Discard/drop policy hoặc sink errors | Level-specific count, queue full, shutdown |
| Lặp log cùng lỗi nhiều lần | Double logging ở layers, retry hoặc double shipping | Event ID, logger/additivity, source routes |
| File quá lớn | DEBUG spam, stack trace, retention không chạy | Rotation config, volume, cleaning errors |
| CPU tăng khi đổi text → JSON | Encoder/field conversion, Throwable rendering | Benchmark cùng semantic fields |
| Collector 429 liên tục | Quota/backpressure | Rate, exporter retry, queue/batch policy |
| Một pod không có logs | Agent path/permissions/CRI/rotation | Raw runtime log và file cursor |
| Log không parse được | Raw newline, invalid JSON, charset/partial records | Encoder output và parser fixtures |
| Dữ liệu bí mật vào index | Dump DTO/exception/MDC chưa được lọc | Stop propagation, security response, sanitization |
| Metrics hiện “no errors” nhưng users báo lỗi | Logging/metrics pipeline có thể hỏng | User impact, probes, cross-signal triangulation |
| Tối ưu khiến audit mất record | Sampling/discard sai class | Audit completeness test, durable contract |
| Benchmark nhanh nhưng production chậm | Sink/load/threads/JIT/config không tương đương | Reproduce near-production, đo end-to-end |

**Thứ tự điều tra:** Xác minh tác động → tìm nghẽn bằng metrics/traces/profiler → khoanh vùng một tầng → thay một biến → kiểm thử correctness/perf → triển khai có rollback. Không tăng queue size hoặc tắt ERROR reflexively.

## 29. Review bảo mật cũng là review hiệu năng

Một số “tối ưu nhanh” có hậu quả xấu:

- Bỏ JSON escaping để giảm CPU → log injection và parser errors.
- Dump raw DTO để tiết kiệm thời gian chọn fields → tăng bytes, PII và storage costs.
- Tắt audit để giảm logging overhead → mất bằng chứng và vi phạm policy.
- Gửi logs chưa mã hóa tới remote endpoint → rủi ro trên đường truyền.
- Giữ mọi DEBUG trong backend lâu dài → tăng chi phí và bề mặt dữ liệu.
- Giảm quyền truy cập không đúng cách làm SRE không điều tra được sự cố → giảm khả năng phản ứng.

**Checklist bảo mật cho performance change:**

- [ ] Không lộ passwords/tokens/cookies/auth headers hoặc raw payload; có test synthetic sentinel.
- [ ] Lưu đúng exception/trace context cần thiết nhưng tránh field nhạy cảm.
- [ ] Giữ JSON encoding/escaping và giới hạn kích thước event.
- [ ] Sampling/rate limit không vô tình bỏ audit/security bắt buộc.
- [ ] Đảm bảo TLS/auth khi xuất mạng và tenant isolation ở backend.
- [ ] Retention/rotation phù hợp từng log class; không giữ hoặc xóa vô hạn trái policy.
- [ ] Profiler traces, heap dumps và benchmark outputs cũng được xem là tài liệu có thể nhạy cảm.

**Kết luận:** Hiệu năng, khả năng điều tra và quyền riêng tư phải được đo như ba trục cùng lúc.

## 30. Kế hoạch cải thiện từng bước trong một sprint

**Ngày 1 — Inventory và baseline:** Thống kê call sites, các levels, payload và sinks; bật instrumentation cho throughput/latency/GC/queue. Xác định danh sách event bắt buộc.

**Ngày 2 — Sửa eager calculations:** Chuyển nối chuỗi DEBUG sang parameterized, dùng Supplier/guard ở expensive paths, bỏ dump raw DTO/headers. Unit test disabled level và privacy.

**Ngày 3 — Kiểm soát volume:** Gộp per-item diagnostics thành batch summary/metrics, thêm event codes, sửa duplicate logging, xác định sampling/ratelimits cho kênh được phép.

**Ngày 4 — Đo formatter và sink:** Benchmark text vs structured, stack trace, sync vs async, rollover, burst và exporter outage. Đánh giá p99 và dropped records, không chỉ CPU.

**Ngày 5 — E2E và rollout:** Query canary events ở backend, đo ingest lag, kiểm tra incident drill/rollback, chốt tiêu chí release và dashboard quan sát pipeline. Rollout tăng dần nếu quy trình cho phép; theo dõi regression.

Đây chỉ là **cách tổ chức bài tập**, không phải lịch cam kết mọi dự án hoàn thành sau năm ngày. Nếu thay đổi policy bảo mật, compliance hoặc backend vendor, cần thêm review/phê duyệt trước triển khai.

## 31. Tiêu chí nghiệm thu và bằng chứng cần lưu

Một bản tối ưu logging được đánh giá **đạt** khi:

1. **Correctness:** Unit tests assert template/level/Throwable/correlation và số event cần thiết; không có message thay đổi nghĩa.
2. **Performance:** Có baseline/candidate đồng điều kiện; throughput và p95/p99 latency phù hợp budget; CPU, allocation và GC đã được xem xét.
3. **Reliability:** Không làm mất event bắt buộc; queue full/shutdown/outage có behavior được ghi rõ và test; có telemetry cho discard/errors.
4. **Security:** Không sinh raw secrets, log injection hoặc mở rộng quyền đọc ngoài policy.
5. **Operability:** Dashboards, retention và E2E query hoạt động; runbook xử lý thiếu log đã được cập nhật; có owner/rollback.
6. **Reproducibility:** Benchmark/test có thể chạy lại trên cùng backend/JDK/config, lưu số liệu và thông số sử dụng.

**Không đạt** khi chỉ báo “logger nhanh hơn 30%” từ một microbenchmark nhưng p99 request xấu đi, queue mất WARN, error count không ổn định hoặc dữ liệu nhạy cảm vào backend.

Nếu logging throughput là bottleneck, hãy đặt ngưỡng mục tiêu cụ thể như `maxEventsPerSecond`, `maxBytesPerSecond` và `maxDropRate` theo từng class **do đội vận hành xác nhận**, không dùng số tưởng tượng làm thực tế.

## 32. Sai lầm thường gặp khi tối ưu Java Logging

| Sai lầm | Vì sao không hiệu quả hoặc nguy hiểm | Sửa thế nào |
| --- | --- | --- |
| Dùng `{}` nhưng argument vẫn gọi `expensive()` | Java đánh giá argument trước call | Supplier/guard |
| Coi `StringBuilder` là lazy logging | String vẫn dựng trước logger | Template + args |
| Benchmark chỉ khi DEBUG off | Bỏ qua encoder/sink/stack trace costs khi on | Đo cả on/off |
| Benchmark một thread/sink no-op | Không phản ánh contention/I/O | Load đa thread với sink thật |
| Chỉ đo throughput | Bỏ qua p99 latency và event drops | Đo tail latency + loss |
| Tăng async queue không giới hạn | RAM/OOM, lag tăng | Bounded queue + metrics |
| Bật `neverBlock=true` không theo dõi | Có thể bỏ events khi đầy | Thử overload và đo drops |
| Coi flush là durable commit | Stream flush != fsync/backend index | Xác định delivery boundaries |
| Ghi stack trace mỗi retry | CPU/bytes cao và trùng bằng chứng | Reason code + trace ở mốc phù hợp |
| Đổ toàn bộ payload vào JSON | Lộ PII, field explosion, index cost | Structured safe allowlist |
| Dùng trace ID làm metric label | Cardinality cực cao | Giữ ID trong logs/traces |
| Sampling mọi WARN/ERROR | Mất context quan trọng | Policy theo event class |
| Ghi file và stdout cùng lúc rồi ship cả hai | Duplicate ingest và chi phí | Một route chính hoặc dedup đúng |
| Chỉ tăng retention/index | Không sửa log storm tại nguồn | Giảm volume/duplicates trước |
| Không đo lúc rollover/shutdown | Bỏ qua spike và loss window | Test lifecycle |
| Không theo dõi Collector | App khỏe nhưng logs biến mất | Internal telemetry/canary |
| Suy đoán version defaults | Config thay đổi theo backend | Pin version và test behavior |
| Tối ưu xong không rollback được | Regression có thể kéo dài | Release gate và revert plan |

## 33. Câu hỏi tự kiểm tra

1. Vì sao `log.debug("x={}", expensive())` vẫn tốn chi phí khi DEBUG off?
2. Khi nào parameterized logging đã đủ, khi nào cần thêm Supplier/guard?
3. JUL dùng placeholder `{0}` hay `{}`?
4. Trong lab, tại sao `eagerCalls=10` dù `emitted=0`?
5. Vì sao kết quả lab không phải số đo nanoseconds/op hoặc bytes/op?
6. SLF4J có phải một backend ghi file/network tự thân không?
7. Nếu AsyncAppender caller nhanh hơn, còn những chi phí nào có thể tăng?
8. Queue 1024 records có đồng nghĩa giữ được 1024 records sau SIGKILL không?
9. Tại sao `neverBlock=true` có thể làm mất diagnostics trong overload?
10. Vì sao chỉ đo CPU mà không đo p99 latency là thiếu?
11. Khi nào batch summary tốt hơn INFO per item?
12. Tại sao exception message và stack trace có thể đắt và không an toàn?
13. `trace_id` có nên là Prometheus metric label không?
14. Khi log JSONL được ship qua Collector, HTTP 200 từ exporter có chứng minh backend đã index không?
15. Một request không tìm được logs có nghĩa request chưa từng chạy không?
16. Vì sao test sync vs async phải dùng cùng sink/layout và workload?
17. Vì sao chỉ nhìn log drops tổng mà không phân biệt severity/event class là nguy hiểm?
18. Khi nào nên chọn durable audit store/outbox thay vì best-effort diagnostic logging?
19. Nếu sampling DEBUG 10%, có thể suy luận count DEBUG bằng count sự kiện thật không?
20. Một thay đổi giảm bytes/s nhưng làm mất correlation IDs có được coi là tối ưu tốt không?
21. Làm sao kiểm tra việc bật DEBUG tạm không để lại rủi ro lâu dài?
22. Cần thu thập những dữ liệu gì để chứng minh một logging performance regression đã được khắc phục?

**Gợi ý:** (1) argument được tính trước method call; (2) sẵn có/rẻ dùng template, đắt dùng lazy; (3) `{0}`; (4) hai eager calls/vòng × năm; (5) chỉ test counter đúng/sai; (6) không, cần provider/backend; (7) CPU worker, queue memory, ingest lag, drops; (8) không; (9) bỏ event khi queue đầy; (10) blocking và outliers; (11) khi per-item volume lớn nhưng không cần từng detail; (12) nhiều frame/cause + secret; (13) không; (14) chưa chắc; (15) không, có thể pipeline/query hỏng; (16) so tương đương; (17) có thể mất WARN/AUDIT; (18) khi nghiệp vụ cần lưu đầy đủ/durable; (19) không nếu thiếu sampling semantics; (20) không nếu correlation thuộc hợp đồng; (21) scope, thời hạn, revert, audit và privacy; (22) baseline, candidate, config, workload, CPU/GC/p99, drops, ingest và correctness.

## 34. Tài liệu chính thức tham khảo

- [Java SE 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): JUL level checks, parameter overloads và `Supplier`.
- [Java SE 17 — LogRecord](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html): message/parameters/exception/metadata.
- [Java SE 17 — Formatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Formatter.html): `formatMessage`.
- [Java SE 17 — Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html): `publish`, `isLoggable` và lifecycle.
- [Java SE 17 — Java Flight Recorder](https://docs.oracle.com/en/java/javase/17/jfapi/): quan sát performance và JFR API.
- [OpenJDK — JMH](https://github.com/openjdk/jmh): microbenchmark với warmup/fork/measurement.
- [SLF4J Manual](https://www.slf4j.org/manual.html): parameterized logging, SLF4J 2 Fluent và Supplier arguments.
- [Logback — AsyncAppender](https://logback.qos.ch/manual/appenders.html#AsyncAppender): queue, discard, blocking và maxFlushTime.
- [Logback — RollingFileAppender](https://logback.qos.ch/manual/appenders-rolling.html): rolling/retention/size cap.
- [Apache Log4j 2 — Asynchronous Loggers](https://logging.apache.org/log4j/2.x/manual/async.html): async loggers/appenders, tradeoffs và cấu hình.
- [Apache Log4j 2 — Garbage-free logging](https://logging.apache.org/log4j/2.x/manual/garbagefree.html): allocation và các cân nhắc hiệu năng.
- [Apache Log4j 2 — Pattern Layout](https://logging.apache.org/log4j/2.x/manual/pattern-layout.html): chi phí layout và trường định dạng.
- [OpenTelemetry — Collector Architecture](https://opentelemetry.io/docs/collector/architecture/): receivers/processors/exporters.
- [OpenTelemetry — Collector Troubleshooting](https://opentelemetry.io/docs/collector/troubleshooting/): đo dropped/refused records, queue và failures.
- [Kubernetes — Logging Architecture](https://kubernetes.io/docs/concepts/cluster-administration/logging/): stdout/stderr, rotation, CRI và node-level agents.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): giảm thiểu dữ liệu, log injection, access control và retention.

**Tóm tắt quyết định:** Trước tiên bỏ work vô ích và log thừa; tiếp theo đo encoder, sink, queue và pipeline dưới tải thật; cuối cùng tối ưu dựa trên **throughput + p99 + loss + data security** chứ không dựa riêng vào tốc độ một lời gọi logger.
