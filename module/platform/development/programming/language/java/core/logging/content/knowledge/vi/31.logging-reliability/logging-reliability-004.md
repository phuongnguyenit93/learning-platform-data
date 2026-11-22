# Log bị chặn ứng dụng trong Java Core Logging

## Mục tiêu

Bài học thuộc nhóm **Độ tin cậy logging**, với đề bài **Log bị chặn ứng dụng**. “Logging chặn ứng dụng” (*logging-induced blocking*) xảy ra khi việc tạo hoặc chuyển log khiến luồng nghiệp vụ phải **chờ** trước khi tiếp tục xử lý, làm tăng thời gian đáp ứng, giảm throughput hoặc gây nghẽn dây chuyền. Đây là một rủi ro về độ tin cậy: hệ thống ghi log để quan sát lỗi, nhưng đường ghi log hoạt động kém có thể trở thành nguyên nhân khiến ứng dụng chậm hoặc không còn phục vụ được request.

Sau bài này, bạn có thể:

- Giải thích sự khác biệt giữa **lời gọi logger bị chặn**, **worker/sink bị nghẽn**, **log đến chậm** và **log bị bỏ**.
- Chỉ ra các điểm chặn thường gặp trong synchronous logging, asynchronous logging, stdout/container, file, network, lock và shutdown.
- Hiểu quan hệ giữa queue capacity, tốc độ sinh log, tốc độ ghi log, backpressure và latency của ứng dụng.
- Đọc các dấu hiệu trong thread dump, Java Flight Recorder (JFR), metrics và profiler để xác nhận nguyên nhân.
- Chạy hai ví dụ Java 17 độc lập: một handler đồng bộ giữ luồng nghiệp vụ và một queue bounded làm producer phải chờ.
- Chọn chính sách phù hợp khi sink chậm hoặc queue đầy, đồng thời cân bằng latency, khả năng quan sát và nguy cơ mất log.

## 1. Chính xác điều gì bị “chặn”?

Trong một ứng dụng Java, phương thức ghi log như `logger.info(...)` thường được gọi ngay trong request thread, scheduler, consumer hoặc worker nghiệp vụ. Nếu phương thức này phải chờ một lock, thiết bị I/O hay chỗ trống trong queue, **luồng đang gọi** không thể tiến tới bước nghiệp vụ tiếp theo.

Ví dụ một request:

```text
HTTP thread:
validate request
    |
    v
call logger.info("request accepted")
    |
    +---- synchronous appender chờ file / stdout
    |          hoặc
    +---- async enqueue chờ queue có chỗ trống
    |
    v
call payment service
    |
    v
return HTTP response
```

Nếu việc ghi log chậm 500 ms trước khi gọi payment service thì request sẽ chịu thêm thời gian chờ, dù logic business không làm gì sai. Khi nhiều request đồng thời bị kẹt trong logging, thread pool của web server có thể cạn, request mới phải xếp hàng và timeout lan sang dịch vụ khác.

**Phân biệt bốn tình huống:**

| Tình huống | Đang xảy ra | Hệ quả đối với ứng dụng |
| --- | --- | --- |
| **Caller blocked** | Thread nghiệp vụ chờ trong/ở đường gọi logger | Request/consumer/job chậm ngay tại điểm gọi log |
| **Async writer stalled** | Worker nền đang chờ disk/stdout/network; producer vẫn enqueue được | Trước mắt request có thể bình thường; backlog đang tăng |
| **Queue full + backpressure** | Producer không thể enqueue theo chính sách blocking | Async logging bắt đầu **chặn caller**, p95/p99 có thể tăng |
| **Log dropped/delayed downstream** | Event bị bỏ hoặc tới collector/index muộn | Có thể thiếu log hoặc nhìn thấy chậm, kể cả khi caller không bị chặn |

Từ “blocked” trong vận hành **không đồng nhất** với `Thread.State.BLOCKED`. Trong Java, một thread có thể bị chặn trên đường logging nhưng hiện trạng thái `WAITING` (đợi condition/latch), `TIMED_WAITING` (đợi có timeout), `BLOCKED` (đợi monitor) hoặc `RUNNABLE` trong lúc lời gọi native I/O đang treo. Luôn đối chiếu stack trace và thời gian chờ, không chẩn đoán chỉ từ tên trạng thái thread.

## 2. Nguyên nhân của logging làm chậm ứng dụng

### 2.1. Synchronous appender chịu I/O ngay trên caller

Với logging đồng bộ, code thường đi qua:

```text
request thread
  -> logger level/filter
  -> event creation / format
  -> appender lock (nếu có)
  -> write console/file/network
  -> return to business
```

Một số hoạt động có thể chậm: ghi console bị pipe đầy, file trên ổ đĩa chậm hoặc đã đầy, file rotation, filesystem trên network, encode exception lớn, socket write chờ mạng, external destination timeout hoặc tranh chấp lock của appender. Cơ chế và mức độ chờ tùy logging framework, layout, appender và hạ tầng.

**Không nên suy ra rằng stdout luôn nhanh.** Trong container, `System.out` hoặc `ConsoleAppender` thường ghi tới stdout pipe do runtime quản lý. Nếu bộ phận đọc pipe, log driver hoặc host I/O bị nghẽn, thao tác ghi có thể chậm hoặc chặn luồng. Chuyển từ file sang stdout không tự loại bỏ bottleneck.

### 2.2. Async appender vẫn có đường chặn

Với async logging:

```text
producers                              consumer
    |                                     |
    +--> event --> bounded queue -------->+--> formatter --> sink
                 ^                 |
                 |                 +--> sink bị chậm
                 |
            queue đầy
                 |
       producer block / drop / fallback
```

Một queue thường nằm trong bộ nhớ và có sức chứa hữu hạn. Khi worker ghi ra sink chậm hơn tốc độ producer tạo event trong thời gian dài, backlog tăng. Queue đầy thì logging framework phải có chính sách: **block producer**, **drop**, **discard theo mức log**, hoặc **thực hiện đồng bộ trên caller** trong một số cấu hình/phiên bản. Do đó “đã bật async” không đủ để kết luận request thread không thể bị ảnh hưởng bởi logging.

Một event đã enqueue thành công **chưa chắc đã được ghi**: worker có thể chưa xử lý, process có thể bị kill, appender có thể gặp lỗi hoặc collector chưa nhận được. Chính sách giảm thời gian block thường có thể làm tăng nguy cơ log bị mất.

### 2.3. Tranh chấp lock và thứ tự khóa

Một số encoder/appender đồng bộ hóa khi nhiều thread cùng ghi vào một sink. Nếu một thread giữ monitor để format hoặc write chậm, các thread khác phải đợi monitor đó. Stack trace có thể cho thấy `Thread.State.BLOCKED` tại một phương thức liên quan appender, `PrintStream` hoặc lock dùng chung.

Rủi ro lớn hơn nếu ứng dụng **gọi logger khi đang giữ lock nghiệp vụ**. Ví dụ thread A giữ lock của cache, sau đó bị kẹt khi ghi log; thread B cần lock cache để phục vụ request khác. Thậm chí có thể tạo vòng chờ nếu appender/callback lại cần lock do thread B giữ. Không thể khẳng định deadlock chỉ vì một stack trace có tên logger; cần chứng minh chu trình phụ thuộc lock bằng thread dump/JFR hoặc công cụ phát hiện deadlock.

### 2.4. Chi phí chuẩn bị event trên caller

Ngay cả khi enqueue không chặn, thread nghiệp vụ có thể tốn CPU vào việc tạo argument, gọi `toString()`, serialize object, format stack trace, capture caller location hoặc copy MDC.

Ví dụ:

```java
logger.debug("payload=" + expensiveJsonSerialization(payload));
```

Biểu thức Java được đánh giá **trước khi gọi method**, kể cả khi DEBUG bị tắt. Parameterized logging:

```java
logger.debug("payload={}", expensiveJsonSerialization(payload));
```

tránh nối chuỗi trong code gọi, nhưng vẫn **thực hiện** `expensiveJsonSerialization(payload)` trước lời gọi. Với SLF4J, nếu dữ liệu tạo rất đắt và không có hỗ trợ lazy đúng yêu cầu, có thể dùng:

```java
if (logger.isDebugEnabled()) {
    logger.debug("payload={}", expensiveJsonSerialization(payload));
}
```

Các đoạn trên là trích đoạn dùng SLF4J và các biến/method giả định, không phải chương trình Java độc lập. `isDebugEnabled()` giúp tránh công việc chuẩn bị khi DEBUG tắt, nhưng trạng thái cấu hình có thể đổi giữa kiểm tra và lời gọi; dùng cho tối ưu thông thường, không phải bảo đảm giao dịch. Nếu phiên bản hỗ trợ fluent/lazy Supplier, kiểm tra semantics cụ thể trước khi áp dụng.

## 3. Queue đầy: vì sao latency tăng đột biến?

Gọi **λ** là tốc độ ứng dụng tạo log (events/giây) và **μ** là tốc độ thực tế worker/sink xử lý (events/giây):

- Nếu `λ < μ` trong điều kiện ổn định, queue có khả năng tiêu hết backlog giữa các burst.
- Nếu `λ ≈ μ`, một burst hoặc pause nhỏ có thể tạo hàng đợi dài và tăng p99.
- Nếu `λ > μ` đủ lâu, backlog tăng gần `λ - μ` events/giây cho đến lúc bounded queue đầy, sau đó chính sách backpressure quyết định hành vi.

Ví dụ hệ thống phát **6.000 events/s** nhưng sink chỉ xử lý **4.000 events/s**. Backlog tăng xấp xỉ 2.000 events/s trong mô hình đơn giản. Nếu queue ban đầu trống và chứa 8.000 events, nó có thể đầy sau khoảng 4 giây ở tải đó, bỏ qua biến động và overhead. Sau khi đầy:

- Với **blocking enqueue**, thời gian gọi logger có thể tăng theo tốc độ sink giải phóng chỗ trống.
- Với **non-blocking drop**, caller có thể quay lại nhanh nhưng một số log không còn.
- Với **synchronous fallback**, business thread có thể phải trực tiếp chịu chi phí I/O, tạo tail latency bất ngờ.

**Tăng queue size chỉ kéo dài thời gian trước khi đầy** khi `λ > μ` kéo dài; không làm sink xử lý nhanh hơn. Queue lớn còn giữ nhiều object trong heap và có thể khiến log xuất hiện trễ hơn. Để giải quyết tải bền vững cần giảm log noise, tối ưu sink/collector hoặc tăng năng lực tiêu thụ, cùng với chính sách overload rõ ràng.

Theo định luật Little ở trạng thái ổn định, `L = λ × W` trong một phạm vi đo nhất quán, với `L` là số event trung bình đang chờ/xử lý và `W` là thời gian trung bình của event trong phạm vi đó. Không dùng công thức như một cam kết latency khi queue đang overflow, event bị drop hoặc hệ thống chưa ổn định.

## 4. Ví dụ Java 17: chứng minh synchronous handler chặn request thread

Ví dụ sau dùng **JDK 17**, chỉ `java.util.logging` và `CountDownLatch`. Một Handler giả lập sink phải chờ tín hiệu mới được trả về. Luồng request gọi `logger.info(...)` sẽ không thể tiếp tục cho đến khi Handler được giải phóng. Chương trình không dựa vào thời gian ngủ hoặc tốc độ máy nên đầu ra có tính xác định.

Tạo file **`BlockingLoggerDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class BlockingLoggerDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch enteredHandler = new CountDownLatch(1);
        CountDownLatch releaseHandler = new CountDownLatch(1);
        AtomicBoolean loggerReturned = new AtomicBoolean(false);

        Logger logger = Logger.getLogger("demo.blocking");
        logger.setLevel(Level.INFO);
        logger.setUseParentHandlers(false);

        Handler slowSink = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (!isLoggable(record)) {
                    return;
                }

                enteredHandler.countDown();
                try {
                    releaseHandler.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }

            @Override
            public void flush() {
            }

            @Override
            public void close() {
            }
        };
        slowSink.setLevel(Level.ALL);
        logger.addHandler(slowSink);

        Thread request = new Thread(() -> {
            logger.info("request-accepted");
            loggerReturned.set(true);
        }, "http-request");

        try {
            request.start();
            enteredHandler.await();

            System.out.println("logger_returned_before_release="
                    + loggerReturned.get());

            releaseHandler.countDown();
            request.join();

            System.out.println("logger_returned_after_release="
                    + loggerReturned.get());
            System.out.println("request_finished="
                    + !request.isAlive());
        } finally {
            releaseHandler.countDown();
            request.join();
            logger.removeHandler(slowSink);
            slowSink.close();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac BlockingLoggerDemo.java
java BlockingLoggerDemo
```

**stdout chính xác:**

```text
logger_returned_before_release=false
logger_returned_after_release=true
request_finished=true
```

**Vì sao đúng?**

1. `request` gọi `logger.info(...)`; JUL chuyển `LogRecord` cho Handler trên **cùng thread** với caller.
2. Handler báo `enteredHandler.countDown()` rồi chờ `releaseHandler.await()`; đến thời điểm main thread nhận tín hiệu, `logger.info(...)` vẫn chưa thể trả về nên `loggerReturned=false`.
3. Main thread cho phép Handler đi tiếp bằng `releaseHandler.countDown()`. Request hoàn tất phương thức logger, đặt `loggerReturned=true`, rồi `join()` bảo đảm đã kết thúc trước khi in kết quả tiếp theo.
4. Handler không in chính event để stdout chỉ chứa ba dòng kiểm tra. `setUseParentHandlers(false)` chặn JUL parent handlers để tránh output không mong đợi.
5. `finally` mở chốt kể cả khi chương trình bị ngắt trong quá trình chờ và gỡ Handler để không để cấu hình test tồn tại sau khi kết thúc.

Đây là **mô phỏng sync sink bị treo**, chưa phải phép đo độ trễ đĩa, container hay mạng. Trong ứng dụng thật, sink có thể chờ file write, stdout pipe, socket, lock hoặc flush. Đo bằng `System.nanoTime()` quanh lời gọi logging để có số liệu caller latency; không lấy hai biến boolean trong ví dụ làm latency thực tế.

**Thử nghiệm:** bỏ dòng `releaseHandler.countDown()` trong khối `try` nhưng giữ `finally`. Khi đó ba dòng output không còn xuất hiện theo thứ tự cũ vì chương trình sẽ chờ `join()` tới khi được `finally` giải phóng (mà `finally` chỉ chạy sau khi rời `try`), tạo tình trạng tự chờ vô hạn. Đừng chạy thay đổi này mà không đặt timeout trong môi trường kiểm thử. Bài học là việc chờ logger/sink không được thiết kế dựa vào vòng chờ khóa lẫn nhau.

## 5. Ví dụ Java 17: bounded async queue khiến producer đợi chỗ trống

Cơ chế queue là một nguyên nhân độc lập với Handler chậm: khi queue đã đầy, `BlockingQueue.put` **đợi** đến khi có khả năng chèn phần tử hoặc thread bị ngắt. `offer` không có timeout có thể trả `false` ngay khi đầy; `offer` có timeout có thể đợi một thời gian hữu hạn. Các lựa chọn thể hiện rõ tradeoff blocking và log loss.

Tạo file **`AsyncQueueBackpressureDemo.java`**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class AsyncQueueBackpressureDemo {
    public static void main(String[] args) throws Exception {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(1);
        queue.put("first");

        CountDownLatch beforePut = new CountDownLatch(1);
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            Future<?> pending = pool.submit(() -> {
                beforePut.countDown();
                try {
                    queue.put("second");
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(e);
                }
            });

            beforePut.await();
            boolean notFinishedWhileFull;
            try {
                pending.get(100, TimeUnit.MILLISECONDS);
                notFinishedWhileFull = false;
            } catch (TimeoutException expected) {
                notFinishedWhileFull = true;
            }

            String first = queue.take();
            pending.get();
            String second = queue.take();

            System.out.println("capacity=1");
            System.out.println("not_finished_while_full="
                    + notFinishedWhileFull);
            System.out.println("first=" + first);
            System.out.println("second=" + second);
            System.out.println("queue_empty=" + queue.isEmpty());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Biên dịch/chạy với JDK 17+:

```bash
javac AsyncQueueBackpressureDemo.java
java AsyncQueueBackpressureDemo
```

**stdout chính xác:**

```text
capacity=1
not_finished_while_full=true
first=first
second=second
queue_empty=true
```

Queue chỉ có một chỗ và chứa `first` trước khi worker cố `put("second")`. `Future.get(100, ...)` không thể trả kết quả hoàn tất khi chưa có ai lấy `first` khỏi queue, nên phép chờ hết thời hạn. Sau `queue.take()`, worker mới có thể enqueue `second`, và `pending.get()` bảo đảm nó đã xong trước khi main lấy event tiếp theo.

**Giới hạn của phép thử:** `not_finished_while_full` chứng minh tác vụ chưa thể hoàn tất khi queue đầy; nó không đo chính xác số mili giây worker thực sự nằm trong `put`, vì JVM scheduler có thể trì hoãn thời điểm worker bắt đầu gọi `put` sau tín hiệu `beforePut`. Giá trị 100 ms là deadline minh họa, không phải SLO hay benchmark. Để đo thời gian blocked thật cần instrumentation quanh enqueue và chẩn đoán stack/metrics trong tải đại diện.

Trong logging framework thật, queue có thể là `BlockingQueue`, ring buffer hoặc cấu trúc khác; ví dụ này minh họa tính chất hữu hạn và backpressure, **không giả định Logback/Log4j 2 dùng nguyên mã trên**. Event trong queue ở đây chỉ là chuỗi, không có LogRecord, layout hay log sink.

## 6. Logback: cấu hình nào có thể làm app thread bị chặn?

Với SLF4J + Logback Classic, một `AsyncAppender` nhận event từ logger rồi chuyển cho worker gửi tới appender đích. Logback có các cấu hình quan trọng:

- `queueSize`: số event tối đa trong queue; tăng capacity giúp hấp thụ burst lớn hơn nhưng tiêu tốn RAM và có thể tăng thời gian chờ xuất log.
- `discardingThreshold`: ngưỡng còn chỗ khiến AsyncAppender có thể loại các event cấp thấp theo chính sách; không đồng nghĩa full queue. Trong Logback Classic thông thường, các mức TRACE/DEBUG/INFO là các mức có thể discard theo chính sách này.
- `neverBlock=false`: khi không enqueue được, producer có thể **chờ** đến khi queue có chỗ. Điều này ưu tiên giữ event qua tầng queue, đổi lại nguy cơ tăng caller latency.
- `neverBlock=true`: dùng nhánh non-blocking khi queue đầy, có thể **bỏ event** thay vì chờ. Khi đó phải có chính sách log loss/giám sát và không xem event đã được lưu.
- `maxFlushTime`: ngân sách chờ worker drain khi appender dừng; shutdown cưỡng bức hoặc quá hạn có thể để lại event chưa được ghi.
- `includeCallerData`: khi bật tính dữ liệu vị trí caller, producer có thể chịu overhead cao hơn vì phải xác định stack/caller.

Ví dụ **`logback.xml`** để khảo sát chính sách backpressure; cần dependency Logback/SLF4J tương thích và môi trường được quyền ghi stdout:

```xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ASYNC"
              class="ch.qos.logback.classic.AsyncAppender">
        <queueSize>1024</queueSize>
        <discardingThreshold>0</discardingThreshold>
        <neverBlock>false</neverBlock>
        <includeCallerData>false</includeCallerData>
        <maxFlushTime>5000</maxFlushTime>
        <appender-ref ref="CONSOLE"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="ASYNC"/>
    </root>
</configuration>
```

**Diễn giải đúng:**

1. Ứng dụng thường enqueue trước rồi worker gọi CONSOLE appender. Khi stdout chậm, queue có thể dồn event.
2. `discardingThreshold=0` tắt cơ chế discard sớm theo ngưỡng còn chỗ; nó không làm queue vô hạn.
3. `neverBlock=false` để producer có thể chờ khi queue đầy, nên **cấu hình này không cam kết “logger.info không chặn”**.
4. `maxFlushTime=5000` giới hạn khoảng chờ drain lúc stop theo cơ chế của Logback; không phải thời gian tối đa được phép block tại mọi `logger.info`.
5. Dùng ConsoleAppender không đảm bảo log đã được collector/index nhận. Để đánh giá end-to-end cần xem pipeline của container và backend.

Nếu sửa `neverBlock=true`, phải **đo event bị drop** khi quá tải và xác minh chính sách đối với event quan trọng. Không chỉ sửa cấu hình rồi coi như giải quyết triệt để reliability. Nếu muốn giảm log volume, giới hạn level/package/noisy events ở nguồn có thể hữu ích hơn việc để queue tự rơi vào overflow.

**Khi nào dùng async logging?** Khi chi phí sink có thể được tách khỏi caller và hệ thống chấp nhận mô hình hàng đợi/backpressure đã thiết kế. Không nên gửi log audit quan trọng duy nhất qua một queue chỉ tồn tại trong RAM rồi tuyên bố bảo đảm zero loss. Audit cần đường lưu durable được thiết kế theo yêu cầu nghiệp vụ và pháp lý cụ thể.

## 7. Log4j 2: AsyncLogger, AsyncAppender và chính sách queue full

Log4j 2 có **AsyncLogger** và **AsyncAppender**. AsyncLogger dùng ring buffer dựa trên LMAX Disruptor trong các cấu hình được hỗ trợ. AsyncAppender là cơ chế đẩy event sang worker trước khi đi vào appender đích. Hai cách có implementation, overhead, context capture và chính sách queue đầy khác nhau theo phiên bản.

Với AsyncLogger, cần kiểm tra cấu hình **AsyncQueueFullPolicy** thực tế. Khi buffer đầy, một hệ thống có thể thực hiện công việc logging trên thread hiện hành, đợi hoặc loại event ở một số level theo policy. Nếu chuyển sang ghi đồng bộ trên caller, việc “async” ở trạng thái bình thường vẫn có thể gây tăng latency đột ngột trong sự cố.

Các điểm kiểm tra:

- Chạy đúng chế độ async mong muốn; kiểm tra dependency và cấu hình được framework nạp.
- Xác định queue/ring buffer size, chiến lược khi full và xử lý event mức `ERROR`/`WARN`.
- Đo thời gian publish trên caller **khi tải vượt khả năng sink**, không chỉ benchmark throughput trong trạng thái queue trống.
- Xác minh chi phí caller location, ThreadContext/MDC capture, exception message/stack trace.
- Quan sát queue utilization, discard/drop và error status nếu stack có expose metrics.
- Thử stdout/file/network sink chậm, rolling file, shutdown, retry hoặc collector unavailable.

Không copy property từ ví dụ trên mạng mà không đối chiếu tài liệu **đúng phiên bản Log4j 2** của dự án; tên property, policy mặc định và chế độ cấu hình có thể thay đổi. Đặc biệt không coi “async logger” và “non-blocking logging” là hai khái niệm đồng nghĩa.

## 8. Log bị chặn ứng dụng khác log bị mất thế nào?

Một chiến lược chỉ được đánh giá “tốt” khi kết hợp cả **latency, số lượng log nhận được và mức độ quan trọng của event**.

| Chính sách khi sink/queue chậm | Ảnh hưởng caller | Khả năng quan sát và độ bền |
| --- | --- | --- |
| **Blocking enqueue** | Caller có thể chờ lâu, làm nghẽn request pool | Ít mất event tại queue do đầy nếu có tiến triển; vẫn có thể mất khi crash/sink lỗi |
| **Non-blocking offer/drop** | Đường enqueue có thể nhanh | Event bị bỏ khi full; cần metric và chính sách ưu tiên |
| **Bounded wait rồi fallback/drop** | Giới hạn một phần thời gian chờ do enqueue | Phụ thuộc framework/logic; cần định nghĩa rõ đường fallback và log loss |
| **Synchronous fallback** | Caller trực tiếp chịu formatter/I/O khi quá tải | Có thể giữ thêm event nhưng làm tăng tail latency |
| **Sampling/rate limiting tại nguồn** | Giảm áp lực ổn định lên queue/sink | Bỏ có chủ đích sự kiện ít giá trị; phải giữ metric/critical events |
| **Tách tuyến audit/critical** | Đường nghiệp vụ khác nhau tùy loại event | Cần thiết kế độ bền, truy cập và khả năng khôi phục riêng |

Một số loại log có thể sampling hoặc aggregate như healthcheck thành công, cache hit, repetitive debug. Nhưng log lỗi giao dịch, security alert và audit bắt buộc phải theo chính sách riêng; không thể tùy tiện drop để cải thiện p99. Với sự kiện nghiệp vụ cần bền vững, có thể cần transactional outbox, broker bền vững hoặc kho audit thích hợp, không đặt tính đúng đắn của giao dịch phụ thuộc vào logger chung.

**Lưu ý về bounded wait:** Không phải mọi logging framework expose một tùy chọn “chờ tối đa N ms rồi drop”. Nếu muốn có chiến lược đó, phải kiểm tra API/implementation thực tế và bảo đảm không làm thay đổi semantics của audit/log critical ngoài ý muốn.

## 9. Chẩn đoán: xác nhận logging là bottleneck

Triệu chứng thường gặp:

- Request latency p95/p99 tăng đồng thời log volume bùng phát hoặc collector bị nghẽn.
- CPU ứng dụng không quá cao nhưng request threads chờ nhiều; thread pool web server đầy.
- Log có độ trễ xuất hiện tăng, queue utilization cao, cảnh báo “appender queue full” hoặc tốc độ write sink giảm.
- Nhiều thread stack lặp lại ở đường appender/`PrintStream`/`BlockingQueue.put`/`LockSupport.park`.
- Thời điểm sự cố trùng với disk full, rolling file, stdout driver slowdown, network logging outage hoặc thay đổi log level sang DEBUG.
- Application throughput giảm khi bật logging chi tiết và phục hồi sau khi giảm volume trên môi trường kiểm thử.

### 9.1. Đọc thread dump đúng cách

Lấy nhiều thread dump cách nhau một khoảng ngắn khi sự cố còn xảy ra, xác định thread nghiệp vụ và call stack chung. Ví dụ **stack minh họa**, không phải một dump thực tế:

```text
"http-nio-8080-exec-17" WAITING
  at java.util.concurrent.locks.LockSupport.park(...)
  at java.util.concurrent.ArrayBlockingQueue.put(...)
  at ...AsyncAppender...append(...)
  at ...Logger.info(...)
  at com.example.checkout.OrderService.process(...)
```

Nếu nhiều request thread lặp cùng stack và queue đang đầy, đây là bằng chứng mạnh của backpressure tại logging. Dù vậy phải kiểm tra code và thread dump **thực tế** để xác nhận một implementation có gọi `ArrayBlockingQueue.put` hay không; Logback/Log4j 2 có thể dùng lớp/cấu trúc khác và stack khác.

Với I/O đồng bộ, stack có thể hiển thị `FileOutputStream`, `PrintStream`, socket write hoặc encoder. Một số I/O call có thể ở trạng thái `RUNNABLE` khi chờ I/O native, nên đừng chỉ lọc các thread ở `BLOCKED`. Với deadlock, dùng `ThreadMXBean.findDeadlockedThreads()` hoặc công cụ phù hợp để tìm chu kỳ monitor/ownable synchronizers, rồi đọc lock owners/stack.

### 9.2. Công cụ Java thường dùng

- **`jcmd <pid> Thread.print`:** lấy thread dump, có thể kết hợp nhiều lần để so sánh.
- **Java Flight Recorder (JFR):** phân tích thread park, monitor blocked, file/socket I/O, GC pauses và bối cảnh hoạt động; event khả dụng tùy phiên bản JDK và recording settings.
- **ThreadMXBean / profiler:** xem thread states, thời gian block/wait và code path tiêu tốn CPU/allocation.
- **Metrics của logger/appender/collector:** queue depth/capacity, event/s, dropped count, disk write, network retries, ingest lag.
- **APM/tracing:** so sánh endpoint latency với thời điểm gọi logging, đồng thời kiểm tra context/trace IDs.

`jcmd <pid> Thread.print` là ví dụ lệnh trong môi trường có JDK tools, với `<pid>` được thay bằng process ID thực tế. Không thu thập dump/JFR bừa bãi từ production nếu tổ chức có quy trình truy cập dữ liệu riêng; các stack/event có thể chứa thông tin cần bảo vệ.

### 9.3. Đo caller latency

Dùng `System.nanoTime()` quanh một lời gọi logging cụ thể để đo elapsed duration cùng JVM:

```java
long started = System.nanoTime();
logger.info("processing payment");
long elapsedNs = System.nanoTime() - started;
```

Đây là **trích đoạn**, chưa bao gồm khai báo logger và nơi ghi kết quả. Tránh log ngay chính `elapsedNs` bằng cùng logger trong mỗi lần đo, vì sẽ tạo thêm traffic và có thể tự làm vòng lặp nghẽn. Ưu tiên metric histogram hoặc sampling instrumentation. Cần đo nhiều lần dưới tải thực, thống kê p50/p95/p99, số mẫu và tỷ lệ drop; chỉ một lần đo không đại diện.

Phân biệt các mốc:

| Chỉ số | Ranh giới đo | Câu hỏi |
| --- | --- | --- |
| **Caller logging duration** | Trước lời gọi logger → sau khi trả về | Business thread bị giữ bao lâu? |
| **Enqueue wait** | Khi bắt đầu enqueue → khi được nhận vào queue | Có backpressure do queue đầy không? |
| **Queue residence** | Khi vào queue → khi worker lấy ra | Worker/sink có backlog không? |
| **Sink completion** | Khi event tạo → appender hoàn thành | Đã ghi theo semantics của sink chưa? |
| **Visibility latency** | Khi event tạo → có thể search ở backend | Người vận hành nhìn thấy log sau bao lâu? |

Mốc “sink completion” không nhất thiết là `fsync` xuống đĩa hay xác nhận bền vững từ collector; muốn đo durability phải định nghĩa riêng điều kiện xác nhận.

**Không cộng p99 enqueue và p99 sink để gọi đó là p99 end-to-end**: các percentile từ các tập event khác nhau không cộng tuyến tính. Để đo end-to-end, gắn mã event/timestamp phù hợp và tính latency theo từng event được ghép đúng.

## 10. Quy trình điều tra một sự cố logging-induced blocking

Một runbook ngắn gọn:

1. **Xác nhận ảnh hưởng:** endpoint p95/p99, request timeout, số active/queued request, thread pool utilization, job/consumer lag.
2. **Kiểm tra tương quan với logging:** log volume theo level/logger, kích thước message/stack trace, thay đổi config gần đây, queue depth và sink throughput.
3. **Xem thread dump/JFR:** bao nhiêu thread kẹt quanh logger/appender, queue, lock hoặc I/O; tìm cùng stack qua nhiều mẫu.
4. **Phân biệt chỗ nghẽn:** nếu caller block nhưng queue rỗng, xem sync sink/lock/formatting; nếu queue đầy, xem tốc độ consumer; nếu JVM sink ghi nhanh nhưng search chậm, xem agent/collector/index.
5. **Chọn biện pháp giảm tải an toàn:** giảm DEBUG và log noise, kiểm tra slow sink/agent, tăng năng lực thu thập hoặc áp dụng policy đã được duyệt. Không tắt ERROR/audit bừa bãi.
6. **Xác minh phục hồi:** p99 caller giảm, throughput trở lại, queue hồi phục, log critical tiếp tục được nhận, không xuất hiện missing event ngoài policy.
7. **Ngăn tái diễn:** alert queue occupancy/drop, kịch bản overload test, ngân sách log volume, cấu hình shutdown và review thay đổi logging.

**Khi cần giảm tải ngay:** trước tiên tìm logger/package tạo burst và sink chậm. Nếu policy cho phép, giảm mức log của package gây noise có thể cắt áp lực ngay. Không thay `neverBlock` hoặc thiết lập discard cho tất cả log mà không kiểm tra rủi ro mất dữ liệu. Nếu một logging sink đang treo làm ảnh hưởng request, cần xem khả năng cô lập sink và vận hành recovery theo runbook của hệ thống thực tế.

## 11. Thiết kế để logging không trở thành single point of failure

### 11.1. Giảm chi phí tại nguồn

- Dùng level theo package/environment, tránh DEBUG/TRACE toàn hệ thống kéo dài.
- Dùng parameterized messages; kiểm tra enabled level trước khi tính dữ liệu đắt.
- Tránh serialize payload lớn, toàn bộ object graph hoặc stack trace lặp khi không cần.
- Không log lặp cùng exception ở mọi tầng; chọn ranh giới báo lỗi có ngữ nghĩa.
- Dùng metrics cho counters/high-volume success thay vì mỗi lần sinh một dòng log.

### 11.2. Thiết kế sink và queue

- Dùng queue bounded có sức chứa được tính theo burst và RAM; đo backlog cùng chính sách full.
- Tách sink lỗi hoặc audit ra đúng domain, tránh để một downstream chậm chặn toàn bộ đường logging nếu không cần.
- Chọn flush, batching, retention/rotation và log shipping phù hợp throughput và latency.
- Kiểm tra stdout pipeline trong container; agent hoặc logging driver vẫn có thể là bottleneck.
- Có cơ chế graceful shutdown/flush với giới hạn và giám sát rõ. Không coi async queue trong RAM là durable storage.
- Tránh logging trong lock nóng, code có thể re-enter appender hoặc callback lỗi của chính logging framework.

### 11.3. Bảo mật và tính đúng đắn

- Không ghi secret, token, cookie, toàn bộ request body hoặc dữ liệu cá nhân không cần thiết vào log.
- Khi pipeline gặp lỗi, không cố “cứu” log bằng việc gửi log nhạy cảm sang sink khác có quyền truy cập rộng hơn.
- Đối với audit cần bảo đảm lưu vết, thiết kế đường write durable hoặc transactional mechanism riêng theo yêu cầu; không suy ra từ `logger.info` trả về thành công.
- Phân biệt **filtered by policy**, **dropped due to overflow**, **sink write failed** và **collector not ingested**. Bốn trường hợp có nguyên nhân, trách nhiệm và cảnh báo khác nhau.

## 12. Bộ kiểm thử tải và failure injection

Một bài test độ tin cậy cần chạy trên staging hoặc môi trường kiểm soát tương đương. Bắt đầu bằng baseline khi sink khỏe, rồi thay đổi **một** yếu tố để xác định nguyên nhân.

| Kịch bản | Cách thử | Kết quả cần kiểm tra |
| --- | --- | --- |
| Bình thường | Tải ổn định với log volume đại diện | p50/p95/p99 caller, queue depth và end-to-end latency trong ngân sách |
| Log burst | Tăng log DEBUG hoặc event volume trong khoảng ngắn | Queue high-water, producer block/drop, thời gian hồi phục |
| Slow sink | Mô phỏng stdout/file/collector chậm | Worker stalled, queue đầy và ảnh hưởng latency request |
| Sink down | Collector unreachable hoặc file permission lỗi trên môi trường thử | Error/retry/drop policy rõ ràng, không treo vô hạn ngoài dự kiến |
| Queue full | Dùng queue capacity thấp hoặc sink rate thấp trong test | Chính sách block/drop/sync fallback đúng như cấu hình |
| Lock contention | Nhiều request ghi cùng sink khi có xử lý chậm | Không phát sinh lock chain hoặc deadlock; đo p99 |
| Shutdown | Dừng graceful khi queue còn event | Worker flush/drain theo ngân sách, ghi nhận event chưa được lưu |
| Crash/kill | Dừng process cưỡng bức trong môi trường test | Quan sát event loss theo thiết kế, không giả định zero loss |
| Sensitive logs | Payload chứa token giả | Redaction/route đúng cả khi lỗi và retry |

Thực hiện **bài test có mã event duy nhất** để đối chiếu số event ứng dụng định phát, số được queue nhận, số sink xử lý, số collector nhận và số searchable. Các con số không nhất thiết khớp ngay lập tức vì pipeline async và retry; đặt thời hạn quan sát phù hợp rồi xác minh.

Khi so sánh hai cấu hình, giữ workload, số thread, log level, message size, sink, CPU/memory và log collector tương đương. Một phép benchmark chỉ đếm số lần `logger.info` trả về mỗi giây có thể trông rất nhanh nhờ event bị drop hoặc còn backlog chưa xử lý; phải tính cả dữ liệu đã ghi và độ trễ ứng dụng.

### Ví dụ đặt mục tiêu đo

Giả sử nhóm chọn ngân sách **caller logging p99 dưới 5 ms ở tải mục tiêu**, không bỏ event `ERROR` tại tầng queue trong kịch bản bình thường, và event thử nghiệm được truy vấn ở backend trong 10 giây. Đây chỉ là **mục tiêu minh họa**, không phải tiêu chuẩn chung của Java. Cần xác định định nghĩa “không bỏ event” và các ngoại lệ như process crash, disk full, network partition; nếu yêu cầu thật là durable audit, dùng cơ chế lưu trữ tương ứng.

Theo dõi thêm `logging_queue_utilization`, `logging_blocked_enqueue_duration`, `logging_dropped_events_total`, `logging_sink_errors_total`, throughput và request latency. Tên metric là ví dụ, không mặc định được mọi phiên bản framework xuất sẵn.

## 13. Những hiểu lầm thường gặp

| Nhận định sai | Điều đúng hơn |
| --- | --- |
| “Đã bật AsyncAppender nên logger không bao giờ chặn.” | Queue đầy, queue policy hoặc đồng bộ fallback có thể tác động trực tiếp lên caller. |
| “Chỉ thread state BLOCKED mới nghĩa là logging chặn app.” | Còn WAITING, TIMED_WAITING hoặc RUNNABLE trong native I/O, tùy cơ chế. |
| “Tăng queue size sẽ giải quyết slow sink.” | Tăng thời gian hấp thụ burst; nghẽn bền vững vẫn tồn tại khi λ > μ. |
| “neverBlock=true bảo đảm độ tin cậy.” | Có thể giảm chờ producer nhưng làm mất log khi queue đầy. |
| “logger.info trả về nghĩa là log đã lưu.” | Async có thể mới enqueue; sync write có thể chưa durable hoặc chưa tới collector. |
| “Ghi stdout luôn là thao tác không chặn.” | Pipe, logging driver và host I/O có thể nghẽn. |
| “Cần tắt hết log ERROR để phục hồi nhanh.” | Mất khả năng chẩn đoán/audit; nên tìm nguồn noise, bottleneck và policy phù hợp. |
| “p99 log call thấp nghĩa là không mất log.” | Có thể đã drop nhiều event; cần đo cả drop rate và sink counts. |
| “DEBUG bị tắt thì mọi công việc tạo message biến mất.” | Java vẫn tính argument expression trước khi gọi logger. |
| “Một stack trace có appender là đủ chứng minh root cause.” | Cần nhiều mẫu, queue/sink metrics, tương quan thời điểm và loại trừ nguyên nhân khác. |

## 14. Checklist vận hành và tự đánh giá

Trước khi áp dụng cấu hình logging cho production, hãy tự trả lời:

1. Logger của ứng dụng dùng sync appender, async appender hay cả hai? Đường nào có thể block business thread?
2. Queue có bounded capacity không, và policy khi đầy là block, drop, discard hay fallback?
3. Khi stdout, file hoặc collector chậm, tác động dự kiến lên p95/p99 endpoint là gì?
4. Có log nào không được phép mất? Cơ chế lưu của chúng có thật sự đáp ứng yêu cầu durability không?
5. Event nào có thể giảm bằng level, sampling, aggregation hoặc rate limiting trước khi tới queue?
6. Thread dump/JFR nào chứng minh các request đang chờ trong logging, và có metric queue/sink nào củng cố kết luận?
7. Khi shutdown hoặc process crash, event trong RAM được xử lý ra sao và log loss được nhận diện như thế nào?
8. Có kiểm thử tải, sink failure, backpressure và log recovery end-to-end trước khi release chưa?
9. Khi cần thay đổi policy để phục hồi dịch vụ, quyền truy cập và quy trình rollback/configuration audit ra sao?

**Tiêu chí hoàn thành:** Bạn giải thích được đường chặn ứng dụng do logging, chạy và lý giải hai chương trình Java 17, phân biệt blocking với delayed/dropped logs, đọc được dấu vết trong thread dump và metrics, và đề xuất được chính sách cân bằng giữa độ trễ nghiệp vụ với dữ liệu log phải giữ.

## Tài liệu tham khảo

- [Java 17 — Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html): semantics xuất `LogRecord` qua Handler.
- [Java 17 — BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): `put`/`offer`/`take` và hành vi chờ.
- [Java 17 — Thread.State](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.State.html): `BLOCKED`, `WAITING`, `TIMED_WAITING` và `RUNNABLE`.
- [Java 17 — ThreadMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html): kiểm tra thread, contention và deadlocks.
- [Logback — AsyncAppender](https://logback.qos.ch/manual/appenders.html#AsyncAppender): bounded queue, discarding, `neverBlock`, shutdown.
- [Apache Log4j 2 — Asynchronous Loggers](https://logging.apache.org/log4j/2.x/manual/async.html): AsyncLogger, AsyncAppender và queue-full strategies.
- [Java Flight Recorder](https://docs.oracle.com/en/java/javase/17/jfapi/): ghi nhận các sự kiện JVM để điều tra wait/I/O/GC.
