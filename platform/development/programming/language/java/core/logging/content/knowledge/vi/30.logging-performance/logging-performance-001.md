# Chi phí tạo log trong Java Core Logging

## 1. Logging có thể gây tốn tài nguyên ở đâu?

**Chi phí tạo log** (logging overhead) là tài nguyên ứng dụng Java tiêu thụ từ khi chuẩn bị dữ liệu cho một sự kiện, gọi logger, kiểm tra mức log, định dạng, mã hóa và gửi event cho tới khi được ghi vào console, file hoặc hệ thống thu thập. Nó có thể ảnh hưởng đến CPU, heap/GC, lock contention, I/O, network, storage và độ trễ xử lý request.

Ví dụ với SLF4J:

```java
logger.debug("orderId={} status={}", orderId, status);
logger.debug("order={}", loadAndSerializeOrder(orderId));
```

Nếu `DEBUG` đang tắt, dòng đầu thường rất nhẹ khi `orderId` và `status` đã có sẵn. Ở dòng thứ hai, **Java vẫn gọi `loadAndSerializeOrder(orderId)` trước khi gọi `debug(...)`**. Nếu hàm đó truy vấn cơ sở dữ liệu hoặc serialize object lớn, chi phí vẫn xảy ra dù không có dòng DEBUG nào được xuất.

Do đó, việc giảm log volume mới chỉ giải quyết một phần; cần hiểu **công việc tại call site**, bên trong logger/backend và pipeline vận chuyển. Mục tiêu là tránh dữ liệu log không cần thiết nhưng vẫn giữ event đủ để chẩn đoán và vận hành.

## 2. Vòng đời của một sự kiện log

```text
Code nghiệp vụ
  -> đánh giá đối số, tính chuỗi/payload
  -> logging API (JUL, SLF4J, ...)
  -> kiểm tra level/filter/sampling
  -> tạo event, timestamp, thread, MDC
  -> format message, Throwable, encode JSON/text
  -> appender: đồng bộ hoặc async queue
  -> console/file/socket/collector
  -> ingest, index, lưu trữ
```

Thứ tự cụ thể có thể khác nhau theo framework, encoder và async implementation. Tuy nhiên **đối số phương thức Java được đánh giá trước khi gọi**, nên một bộ lọc của logger không thể hoàn lại thời gian đã dùng để dựng đối số.

| Giai đoạn | Tài nguyên có thể tiêu thụ | Điểm cần chú ý |
| --- | --- | --- |
| Chuẩn bị đối số | CPU, heap, đôi khi DB/network | Hàm tạo payload chạy dù log bị tắt |
| Kiểm level/filter | CPU | Bộ lọc phức tạp cũng tốn chi phí |
| Tạo event | Allocation, clock, thread context | Tạo LogRecord, lấy MDC, caller data |
| Formatter/encoder | CPU, buffer | Thay placeholder, JSON escape, stack trace |
| Appender/queue | Lock, memory, contention | Đồng bộ chờ I/O; async phải enqueue |
| Sink/transport | Disk/network/flush/retry | Console, file, OTLP, agent |
| Cloud backend | Ingest/index/storage | Dữ liệu nhiều và lâu làm tăng chi phí |

Phân biệt **latency trên thread request** và **tổng chi phí hệ thống**. Chuyển log từ synchronous sang asynchronous appender có thể giảm thời gian request chờ nhưng vẫn dùng CPU, bộ nhớ và network ở thread consumer hoặc process khác.

## 3. Đối số eager: cái bẫy lớn nhất

Ba lời gọi sau đều tạo dữ liệu trước khi backend biết cần ghi hay không:

```java
logger.debug("payload=" + expensivePayload());
logger.debug(String.format("payload=%s", expensivePayload()));
logger.debug("payload={}", expensivePayload());
```

Ở dòng thứ nhất, phép nối chuỗi chạy sớm. Dòng thứ hai gọi `String.format` sớm. Dòng thứ ba dùng placeholder, nhờ đó backend có thể trì hoãn việc ghép message, nhưng **`expensivePayload()` vẫn chạy**. Nếu hàm này query DB, duyệt collection lớn hoặc tạo JSON, chi phí không biến mất.

Tương tự:

```java
logger.debug("user={}", user.toString());
```

`toString()` được gọi ngay. Với SLF4J, nếu chỉ cần format khi level bật, có thể chuyển object trực tiếp:

```java
logger.debug("user={}", user);
```

Cách thứ hai thường để backend quyết định có gọi `toString()` hay không. Nhưng object `user` vẫn phải được tạo trước, và bản thân `toString()` cần an toàn, không có side effect và không rò rỉ dữ liệu.

### Dùng parameterized logging đúng

```java
logger.info("requestId={} result={}", requestId, result);
```

Cách này thường tốt hơn nối chuỗi thủ công khi log có thể bị tắt. Với một hoặc hai đối số, một số overload SLF4J tránh việc tạo mảng varargs; song Java vẫn có thể thực hiện boxing primitive, gọi getter hoặc tạo object tạm tùy trường hợp. Không nên kết luận chắc chắn về số byte cấp phát nếu chưa benchmark với JDK và provider thật.

Giá trị log có thể được định dạng thành JSON, nhưng **structured logging cũng không miễn phí**. Encoder phải escape chuỗi, xử lý thời gian, chuyển số, format exception và có thể copy buffer. Đầu tư vào định dạng có cấu trúc giúp query/correlation tốt hơn; tối ưu phải xét cả lợi ích vận hành thay vì chỉ CPU của formatter.

## 4. Dùng guard hoặc supplier khi payload thật sự đắt

Nếu công việc tạo dữ liệu đáng kể, hãy kiểm tra mức log trước:

```java
if (logger.isDebugEnabled()) {
    String details = buildExpensiveDetails(order);
    logger.debug("order details={}", details);
}
```

Đây là đoạn minh họa SLF4J; cần khai báo `logger`, `order` và `buildExpensiveDetails` trong chương trình. Guard giúp tránh hàm đắt khi DEBUG tắt. Nó hợp lý cho serialize, duyệt nhiều bản ghi hoặc thực hiện tính toán; không nhất thiết phải bọc một lời gọi chỉ nhận ID đã có sẵn.

**JUL (java.util.logging)** của JDK có overload nhận `Supplier<String>`:

```java
logger.log(java.util.logging.Level.FINE,
        () -> "details=" + buildExpensiveDetails(order));
```

Khi mức `FINE` bị tắt ở logger, supplier không được gọi. Công việc phải nằm **trong lambda**; nếu tính trước rồi chỉ truyền biến vào lambda, lợi ích bị mất.

**SLF4J 2.x** cung cấp fluent logging với supplier cho đối số:

```java
logger.atDebug()
        .addArgument(() -> buildExpensiveDetails(order))
        .log("details={}");
```

Đoạn này cần SLF4J 2.x và provider tương thích; SLF4J 1.7 không có cùng fluent API. Supplier có thể tránh công việc ở call site khi level bị tắt, nhưng nếu một filter ở appender/collector mới loại event, payload có thể đã được tạo. Không đặt side effect nghiệp vụ vào supplier, vì khi log không được chấp nhận, nó có thể không chạy.

Một chi tiết: mức log có thể thay đổi giữa phép kiểm `isDebugEnabled()` và lệnh `debug(...)`. Guard dùng để tránh tính toán sớm, không phải giao thức bảo đảm event được ghi nguyên tử.

## 5. Ví dụ Java 17 hoàn chỉnh: eager, lazy và guard

Ví dụ dưới đây sử dụng **chỉ JDK** để làm rõ thứ tự đánh giá. Logger nhận `INFO` trở lên và tắt `FINE`. `buildPayload()` tăng một bộ đếm mỗi lần được gọi. Handler chỉ đếm event nhận được, không xuất thêm dòng log.

Tạo tệp `LoggingCostDemo.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LoggingCostDemo {
    private static final AtomicInteger COMPUTATIONS =
            new AtomicInteger();
    private static final AtomicInteger PUBLISHED =
            new AtomicInteger();

    private static String buildPayload() {
        COMPUTATIONS.incrementAndGet();
        return "payload";
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("example.logging.cost");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        Handler sink = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    PUBLISHED.incrementAndGet();
                }
            }

            @Override
            public void flush() {}

            @Override
            public void close() {}
        };

        sink.setLevel(Level.ALL);
        logger.addHandler(sink);
        try {
            logger.fine("eager=" + buildPayload());
            int eager = COMPUTATIONS.get();

            logger.log(Level.FINE,
                    () -> "lazy=" + buildPayload());
            int lazy = COMPUTATIONS.get();

            if (logger.isLoggable(Level.FINE)) {
                logger.fine("guarded=" + buildPayload());
            }
            int guarded = COMPUTATIONS.get();

            logger.info(() -> "visible=" + buildPayload());

            System.out.printf(
                    "eager=%d lazy=%d guarded=%d final=%d published=%d%n",
                    eager, lazy, guarded,
                    COMPUTATIONS.get(), PUBLISHED.get());
        } finally {
            logger.removeHandler(sink);
            sink.close();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac LoggingCostDemo.java
java LoggingCostDemo
```

Stdout chính xác:

```text
eager=1 lazy=1 guarded=1 final=2 published=1
```

Lý do:

1. Lời gọi `fine("eager=" + ...)` vẫn gọi `buildPayload()`: `eager=1` dù mức FINE tắt.
2. Supplier của lệnh `logger.log(Level.FINE, ...)` không được gọi: `lazy=1`.
3. Guard không thỏa điều kiện `isLoggable(Level.FINE)`, nên `guarded=1`.
4. Lệnh `info` có mức được bật, nên supplier chạy một lần, `final=2`, Handler nhận một event, `published=1`.

Đây là **ví dụ kiểm chứng ngữ nghĩa**, không phải benchmark nanosecond/op. `AtomicInteger` và test Handler cũng có overhead; để đánh giá production, phải đo logger, formatter và appender thật.

## 6. Chi phí tạo message và stack trace

Mỗi bản ghi có thể sinh một số object tạm: chuỗi, wrapper, mảng varargs, event, bản sao MDC, JSON buffer, mảng bytes hoặc stack trace. Khi log ở tốc độ cao, allocation rate tăng có thể gây áp lực lên GC và làm p95/p99 latency xấu đi.

Một số nguồn chi phí đáng chú ý:

- **`toString()` trên object lớn** có thể duyệt nhiều field, thực hiện lazy getter hoặc serialize dữ liệu không cần thiết.
- **`String.format`** có nhiều xử lý hơn nối chuỗi đơn giản; gọi nó trước logger làm phát sinh chi phí dù mức log tắt.
- **Throwable**: tạo `new Exception()` có thể thu thập stack trace; không tạo exception mới cho mọi checkpoint bình thường.
- **Caller location**: để ghi file, class, method, line number, backend có thể phải kiểm tra stack; trong async logging, thông tin này đôi khi cần được chụp sớm ở producer thread.
- **MDC/trace context**: thêm hoặc snapshot quá nhiều field khiến mỗi event lớn hơn và tốn copying.
- **Message dài hoặc JSON phức tạp**: tăng CPU serialize, buffer, bytes network và chi phí index.

Ví dụ tránh dump object khi chỉ cần thông tin cốt lõi:

```java
logger.info("orderId={} status={} itemCount={}",
        order.getId(), order.getStatus(), order.getItemCount());
```

Dù vậy các getter vẫn được đánh giá. Không gọi getter kích hoạt I/O nếu không cần; nếu dữ liệu log phức tạp, dùng guard/supplier.

Khi thực sự bắt được lỗi, có thể ghi `Throwable` hiện có:

```java
try {
    processOrder(orderId);
} catch (RuntimeException ex) {
    logger.error("Order failed id={}", orderId, ex);
    throw ex;
}
```

Đây là ví dụ SLF4J cần `processOrder`, `logger`, `orderId` từ ứng dụng. Lệnh `throw ex` là lựa chọn xử lý lỗi tùy hợp đồng; tránh nhiều lớp log trùng cùng stack trace, và không tạo Throwable mới chỉ để lấy call stack khi không cần.

## 7. Chi phí GC, đồng bộ và throughput

Với ứng dụng xử lý nhiều request, một lời gọi log đắt nhẹ nhân với hàng triệu lần có thể đáng kể. Mô hình ước lượng:

```text
events_per_minute = requests_per_minute × logs_per_request

serialized_bytes_per_day ≈ events_per_day × average_bytes_per_event

total_cost ≈ log_creation + encoding + dispatch + transport
             + contention + GC + ingest/storage
```

Các phép cộng này chỉ là mô hình khái niệm, không có nghĩa CPU/latency tuyến tính tuyệt đối theo số event. Thread chạy song song, JIT, buffering, compression, GC và network latency khiến quan hệ phức tạp.

Ví dụ: 20.000 request/phút, mỗi request tạo 5 log INFO, nghĩa là khoảng **100.000 event/phút**. Nếu giảm các bản ghi trùng xuống còn 2 log/request, volume còn **40.000 event/phút** khi traffic không đổi. Điều đó giảm tải cho formatter, đường truyền và ingest; không suy ra throughput ứng dụng tăng đúng tỷ lệ 2,5 lần.

Tranh chấp còn xuất hiện khi nhiều thread cùng ghi qua một synchronous appender, file lock hoặc queue chung. Một số định dạng đòi timestamp/caller extraction ở mỗi event. Trên thread pool, việc copy MDC lớn cũng có thể làm tăng allocations. Ưu tiên log ID, status, duration và error code có giá trị chẩn đoán thay vì toàn bộ request/response.

## 8. Async logging: giảm chờ trên request, không xóa tổng chi phí

**Synchronous logging** có thể format và ghi ngay trên thread phát log. **Asynchronous logging** thường ghi vào queue để consumer xử lý tiếp. Async giúp giảm thời gian chờ của thread nghiệp vụ khi queue thông thoáng, nhưng producer vẫn phải chuẩn bị event, snapshot context và enqueue; consumer vẫn encode và ghi I/O.

```text
worker A ---\
worker B ----+--> async queue --> consumer --> file/console/network
worker C ---/         |
                     +--> full: block / discard / fallback tùy config
```

| Hành vi khi queue đầy | Đánh đổi |
| --- | --- |
| Chặn producer | Có thể giữ event nhưng tăng latency hoặc timeout |
| Bỏ một số mức DEBUG/INFO | Bảo vệ throughput nhưng mất thông tin, phải đếm dropped events |
| Ghi đồng bộ dự phòng | Có thể gây spike latency lúc tải cao |
| Spool/retry | Tốn bộ nhớ/đĩa; phải giới hạn và kiểm recovery |
| Sampling trước queue | Giảm tải sớm nhưng cần bảo vệ event quan trọng |

Không giả định async bảo đảm **exactly-once**. Khi process crash, event chưa flush có thể mất; khi gửi lại sau network timeout, log có thể xuất hiện trùng. Kiểm tra chính sách shutdown/flush, queue capacity, backpressure và retry của framework/backend thật.

## 9. Sampling và vị trí lọc ảnh hưởng tới chi phí

Sampling các log INFO thành công lặp lại có thể giảm storage và network. Tuy nhiên, **lọc càng muộn thì càng ít tránh được chi phí tạo log ở upstream**.

| Lọc ở đâu | Tiết kiệm chính | Vẫn có thể phải trả |
| --- | --- | --- |
| Guard/call site trước tạo payload | Tránh tạo dữ liệu, event và dispatch | Phép kiểm mức log |
| Logger level/filter | Tránh format/dispatch khi event bị từ chối | Đối số đã đánh giá |
| Appender/queue | Tránh một phần I/O về sau | Tạo event và có thể encode |
| Agent/Collector | Giảm ingest/storage downstream | CPU JVM và vận chuyển trước điểm lọc |
| Backend storage | Giảm retention/index | Phần lớn tạo và truyền event trước đó |

Khi muốn xem diễn biến một request, sampling nhất quán theo request/trace ID thường dễ điều tra hơn giữ ngẫu nhiên từng dòng độc lập. ERROR, audit và những sự kiện bắt buộc lưu cần chính sách riêng. Không dùng tập log đã sampling để tính tỷ lệ lỗi/traffic chính xác; dùng metrics độc lập khi cần số liệu toàn bộ lưu lượng.

## 10. Benchmark logging đúng cách

Đo một vòng lặp bằng `System.nanoTime()` mà không warmup dễ bị nhiễu bởi JIT, GC, dead-code elimination, terminal buffering và I/O. Với microbenchmark trong Java, **JMH** giúp thiết kế warmup, fork JVM, iteration và state phù hợp; vẫn cần hiểu mình đo điều gì.

Nên tách:

1. **Disabled level:** chỉ đo cost tại call site của nối chuỗi, parameterized logging, guard và supplier.
2. **Enabled sink không I/O:** đo event creation, formatter và allocations trong JVM.
3. **Enabled sink thật:** file/console/network/OTLP, nhiều thread, message size và queue phù hợp production.
4. **End-to-end:** measure request throughput, p95/p99 latency, bytes/sec, GC, queue backlog, dropped logs và ingest latency.

Ghi rõ JDK/GC, hardware, API/backend version, format, mức log, số thread, event size, queue capacity, buffering và sink. Không kết luận logger A luôn nhanh hơn logger B chỉ từ một benchmark trên stdout máy cá nhân. Một cải tiến giảm ns/op của DEBUG tắt có thể không giúp nhiều nếu bottleneck thực là console hoặc Collector.

| Chỉ số | Ý nghĩa |
| --- | --- |
| Throughput hoặc ns/op | Thời gian mỗi thao tác trong workload đã định |
| Allocation B/op, bytes/sec | Áp lực bộ nhớ và GC |
| CPU, GC pause | Công việc toàn bộ JVM |
| p95/p99 request latency | Tác động lên request nhạy độ trễ |
| Queue depth/drop/retry | Nghẽn và mất tín hiệu |
| Serialized bytes/ingest rate | Chi phí truyền và lưu log |

Với test async, đợi flush hoặc điều kiện hoàn thành **có timeout** theo backend; không dùng `Thread.sleep(1000)` làm bằng chứng mọi event đã lưu. Xác minh event ID duy nhất và số lượng theo chính sách drop/sampling.

## 11. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| `logger.debug("x=" + expensive())` | Tạo dữ liệu dù DEBUG tắt | Guard hoặc supplier |
| `logger.debug("{}", expensive())` rồi tưởng lazy hoàn toàn | Placeholder lazy, đối số eager | Guard/supplier cho hàm đắt |
| Gọi `toString()` trước logger | Format sớm và có thể lộ dữ liệu | Chọn field hoặc để backend format khi cần |
| Dump object/response lớn mỗi request | CPU/heap/network tăng mạnh | Log ID, status, duration, error code |
| Tạo exception mới cho từng checkpoint | Tạo stack trace tốn chi phí | Chỉ log Throwable thật khi cần |
| Bật caller file/line khắp nơi | Stack walk tăng overhead | Bật có mục đích |
| Bật DEBUG rộng trong production | Bùng nổ volume | Giới hạn phạm vi, có thời hạn |
| Coi async miễn phí | Queue/consumer/GC vẫn tiêu tài nguyên | Đo cả request và tổng CPU |
| Lọc tận backend rồi muốn giảm CPU JVM | Event đã tạo và gửi | Lọc sớm khi phù hợp |
| Không đo dropped logs | Không nhận ra mất tín hiệu khi overload | Metrics queue, drop, retry |
| Benchmark trong IDE bằng console | I/O và JIT làm sai kết luận | Test có warmup và tải thực tế |
| Xóa mọi log để cải thiện tốc độ | Không thể điều tra sự cố | Giữ log quan trọng, giảm event trùng |

## 12. Checklist tối ưu chi phí tạo log

Trước khi sửa hệ thống logging, hãy lần lượt kiểm:

- **Call site:** có xây dựng chuỗi, JSON, query, gọi getter nặng, tạo exception dù level tắt không?
- **API:** có dùng parameterized logging và guard/supplier tương thích đúng phiên bản khi payload đắt không?
- **Backend:** có format quá nhiều field, stack trace, MDC, caller location hoặc trùng appender không?
- **Concurrency:** nhiều thread có contention, queue backlog, drop hoặc producer block không?
- **Storage:** có log INFO lặp lại, retention dài hoặc index field không cần thiết không?
- **Chất lượng quan sát:** sau tối ưu, log lỗi/audit, correlation ID và khả năng điều tra request còn đầy đủ không?
- **Đo lường:** đã so sánh CPU, allocations, GC, throughput, p95/p99, network bytes và dropped events trước/sau chưa?

**Ghi nhớ:** chi phí tạo log có thể phát sinh **trước cả khi logger quyết định có lưu event** vì Java đánh giá các đối số. Bước tối ưu thường mang lại lợi ích nhất là tránh tạo payload không cần thiết, giảm event trùng và kích thước dữ liệu, rồi cấu hình encoder/appender và pipeline hợp lý dựa trên đo đạc thực tế.
