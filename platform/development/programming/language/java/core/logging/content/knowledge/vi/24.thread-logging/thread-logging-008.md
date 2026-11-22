# Shutdown thread logging trong Java

## 1. Mục tiêu của bài học

Trong ứng dụng Java nhiều thread, việc gọi `logger.info(...)` không luôn có nghĩa bản ghi đã nằm an toàn trong tệp hay hệ thống tập trung. Với **asynchronous logging**, thread nghiệp vụ có thể chỉ đưa log vào hàng đợi; một thread khác sẽ lấy log ra và ghi xuống sink. Nếu ứng dụng kết thúc quá sớm, các log cuối cùng có thể vẫn còn trong queue.

**Shutdown thread logging** là quá trình dừng các thread ghi log và hệ thống logging đúng thứ tự: dừng nguồn sinh log, cho các tác vụ nghiệp vụ kết thúc, xả log đã được chấp nhận, flush các bộ đệm, đóng tài nguyên và chờ logging worker thoát. Chủ đề cũng bao gồm cách ghi log trong **JVM shutdown hook thread**, nơi rất dễ gặp lỗi thứ tự đóng hoặc thiếu context.

Sau bài học, bạn sẽ:
- Phân biệt dừng thread, drain queue, flush và close.
- Viết ví dụ Java 17 có logging thread và graceful shutdown kiểm chứng được.
- Hiểu tại sao `Thread.interrupt()`, daemon thread hoặc `System.exit()` không bảo đảm log cuối đã được lưu.
- Dừng logging backend (Logback, Log4j 2, JUL) đúng vòng đời; tránh xung đột với worker, executor và shutdown hook.
- Kiểm thử trường hợp tải cao, queue đầy, timeout, logging context/MDC và lỗi khi shutdown.

## 2. Synchronous logging và asynchronous logging

Với **synchronous logging**, thread gọi logger thực hiện công việc ghi qua appender trong phạm vi lời gọi. Tuy nhiên, buffer của stream, file system hoặc sink mạng vẫn có thể chưa được đồng bộ. Với **asynchronous logging**, producer gửi log vào queue/ring buffer và tiếp tục chạy; consumer xử lý log sau.

```text
business-thread-1 ─┐
business-thread-2 ─┼─> enqueue log event ─> queue ─> log-writer thread ─> appender ─> console/file
scheduler-thread  ─┘
```

Giả sử thread nghiệp vụ gọi `logger.info("Order completed")` rồi process thoát ngay. Log event có thể đã được enqueue thành công nhưng `log-writer` chưa đọc đến. Kết quả: đoạn code đã chạy qua lệnh logging, nhưng hệ thống quan sát không nhận được log.

| Khái niệm | Mục đích | Không nên nhầm với |
| --- | --- | --- |
| `shutdown`/`stop` | Bắt đầu hoặc hoàn tất vòng đời dừng của thành phần | Chỉ gửi yêu cầu dừng mà không đợi kết thúc |
| `drain` | Xử lý hết các sự kiện đã vào hàng đợi | Xóa queue hoặc bỏ bản ghi còn chờ |
| `flush` | Đẩy nội dung đang đệm của stream/appender sang tầng I/O tiếp theo | Đảm bảo log đã được ghi bền vững hoặc backend mạng xác nhận |
| `close` | Đóng file, socket, appender và tài nguyên | Cho phép tiếp tục ghi log sau khi đóng |
| `join`/`awaitTermination` | Chờ thread hoặc executor kết thúc | Tự động tạo cơ chế drain log |
| `interrupt` | Gửi tín hiệu gián đoạn hợp tác tới thread | Bắt buộc mọi log còn chờ phải được ghi |

Nếu mục tiêu là audit không được phép mất dữ liệu, logging pipeline best-effort không đủ; cần cơ chế lưu sự kiện có độ bền và xác nhận riêng.

## 3. Trình tự shutdown an toàn

Với ứng dụng có background logging, chu trình hợp lý là:

```text
RUNNING
    |
    | Ngừng nhận request, không cấp task mới
    v
QUIESCING
    |
    | Chờ business workers, request đang chạy và scheduled jobs cần thiết
    | Ghi thông điệp tổng kết shutdown khi logger còn hoạt động
    v
STOP_ACCEPTING_LOGS
    |
    | Không enqueue event mới; đưa tín hiệu dừng sau event đã nhận
    v
DRAINING
    |
    | Logging worker xử lý nốt queue, flush output
    v
STOPPED
    |
    | Đóng appender/backend, xác nhận không còn logging worker
```

Điểm cần giữ: **nguồn sinh log dừng trước logging backend**. Nếu executor, timer hoặc network callback vẫn hoạt động sau khi appender đã stop, chúng có thể ghi log bị mất hoặc lỗi. Ngược lại, nếu logging worker dừng quá sớm, queue vẫn còn event chưa xử lý.

Một đoạn minh họa khi ngừng `ExecutorService` do ứng dụng tự quản lý:

```java
executor.shutdown(); // Ngừng nhận task mới.
boolean finished = executor.awaitTermination(
        10, java.util.concurrent.TimeUnit.SECONDS);
if (!finished) {
    // Ghi nhận task còn chạy và áp dụng chính sách timeout.
}
// Chỉ đóng logging backend khi không còn producer cần ghi log.
```

Đây là đoạn tích hợp trong một phương thức có biến `executor`, không phải chương trình độc lập. `shutdown()` không chờ toàn bộ task; `awaitTermination` trả về `false` nếu quá thời hạn. `shutdownNow()` yêu cầu ngắt các task, nhưng không đảm bảo task dừng ngay hoặc logger đã flush.

Không nên chờ vô hạn một network appender không phản hồi; ứng dụng production cần deadline tổng, có phân bổ thời gian cho business shutdown và logging shutdown.

## 4. Ví dụ Java 17: thread ghi log và graceful shutdown

Ví dụ dưới đây tự tạo một asynchronous logger đơn giản bằng `ArrayBlockingQueue`. Business thread là producer; thread `log-writer` là consumer. Một bản ghi đặc biệt `STOP` được đưa vào **sau các log đã được chấp nhận**. Consumer đọc FIFO đến `STOP`, flush và thoát. Chương trình đợi thread này bằng `join()`.

Tạo tệp `ShutdownLoggingDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public final class ShutdownLoggingDemo {
    private record LogEvent(String message, boolean stop) {}

    private static final class AsyncLog implements AutoCloseable {
        private static final LogEvent STOP = new LogEvent("", true);

        private final BlockingQueue<LogEvent> queue =
                new ArrayBlockingQueue<>(32);
        private final Thread writer;
        private boolean closing;

        AsyncLog() {
            writer = new Thread(this::writeLoop, "log-writer");
            writer.setDaemon(false);
            writer.start();
        }

        // Dùng chung lock với close để không có log sau STOP.
        public synchronized void info(String message)
                throws InterruptedException {
            if (closing) {
                throw new IllegalStateException("Logger already closed");
            }
            queue.put(new LogEvent(message, false));
        }

        private void writeLoop() {
            try {
                while (true) {
                    LogEvent event = queue.take();
                    if (event.stop()) {
                        break;
                    }
                    System.out.printf("[%s] %s%n",
                            Thread.currentThread().getName(),
                            event.message());
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            } finally {
                System.out.flush();
            }
        }

        @Override
        public void close() {
            boolean interrupted = false;

            synchronized (this) {
                if (!closing) {
                    closing = true;
                    // Đảm bảo gửi STOP ngay cả khi caller bị interrupt.
                    while (true) {
                        try {
                            queue.put(STOP);
                            break;
                        } catch (InterruptedException ex) {
                            interrupted = true;
                        }
                    }
                }
            }

            // Chờ consumer ghi tất cả log trước STOP.
            while (true) {
                try {
                    writer.join();
                    break;
                } catch (InterruptedException ex) {
                    interrupted = true;
                }
            }

            if (interrupted) {
                Thread.currentThread().interrupt();
            }
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        try (AsyncLog log = new AsyncLog()) {
            log.info("service-started");

            Thread businessWorker = new Thread(() -> {
                try {
                    log.info("job-finished");
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            }, "business-worker");

            businessWorker.start();
            businessWorker.join();
            log.info("shutdown-requested");
        }

        System.out.println("shutdown-complete");
    }
}
```

Biên dịch và chạy trên JDK 17 hoặc mới hơn:

```bash
javac ShutdownLoggingDemo.java
java ShutdownLoggingDemo
```

**Stdout chính xác** trong lần chạy bình thường, không bị external interrupt hoặc lỗi I/O:

```text
[log-writer] service-started
[log-writer] job-finished
[log-writer] shutdown-requested
shutdown-complete
```

### Cơ chế bảo đảm thứ tự trong ví dụ

1. `info()` và việc đưa `STOP` vào queue trong `close()` cùng dùng khóa `this`. Event nào được chấp nhận cũng vào queue **trước STOP**; lời gọi log sau khi `closing=true` sẽ bị từ chối bằng exception thay vì bị xếp sau STOP.
2. `ArrayBlockingQueue<>(32)` có sức chứa giới hạn. `put()` **chặn producer** nếu queue đầy (backpressure), thay vì tự ý bỏ log. Ứng dụng thực tế cần chính sách khi writer chậm.
3. `businessWorker.join()` bảo đảm worker đã enqueue `job-finished` trước khi main enqueue `shutdown-requested`. Vì chỉ có một consumer và queue FIFO, thứ tự ba log là xác định.
4. `try-with-resources` tự gọi `close()`. Hàm này chặn log mới, đưa STOP vào queue và dùng `join()` để đợi thread ghi log kết thúc. `finally` ở consumer gọi `flush()`.
5. Dòng `shutdown-complete` do main tự in sau khi `close()` trở về; nó xác nhận thread `log-writer` đã dừng. Dòng này không đi qua `AsyncLog`.
6. Nếu thread gọi `close()` bị interrupt khi chờ, demo vẫn tiếp tục cố đưa STOP vào queue và chờ consumer kết thúc, sau đó khôi phục interrupt flag. Đây là lựa chọn **không giới hạn thời gian**, phù hợp để giải thích nguyên lý nhưng không phải chính sách production.

**Giới hạn của demo:** Nếu log-writer bất ngờ chết, bị interrupt trước khi đọc STOP, queue đầy và không còn consumer, hoặc đầu ra bị treo, `close()` có thể chờ mãi. Trong production cần timeout, cơ chế phát hiện worker failure, giám sát event còn tồn đọng, chính sách khi sink lỗi và thư viện logging được bảo trì. Đừng tự triển khai một logging framework mới chỉ vì cần asynchronous logging.

## 5. Daemon thread, interrupt và force shutdown

### `setDaemon(true)` không flush

Daemon thread không giữ JVM tồn tại khi không còn non-daemon thread. Nếu dùng daemon làm log-writer mà không có explicit shutdown, JVM có thể thoát trước khi worker xử lý hết queue. `setDaemon(false)` ở ví dụ giúp làm rõ rằng vòng đời logging worker cần được quản lý; bản thân non-daemon cũng không tự drain khi shutdown cưỡng bức.

### `interrupt()` không có nghĩa “ghi hết rồi dừng”

Khi consumer đang chờ `BlockingQueue.take()`, `interrupt()` thường khiến lời gọi ném `InterruptedException`. Nếu handler thoát vòng lặp ngay, event đang chờ có thể bị bỏ. Vì vậy, graceful shutdown nên dựa vào tín hiệu kết thúc đặt **sau những event hợp lệ**; interrupt chỉ dùng theo chính sách dừng khẩn cấp/deadline, với nguy cơ mất log đã biết.

Không dùng `Thread.stop()`: API này không an toàn vì có thể chấm dứt thread tại thời điểm giữ lock hoặc cập nhật trạng thái dở dang.

### `System.exit`, `Runtime.halt`, kill process

`System.exit(status)` khởi động quá trình shutdown JVM có trật tự và có thể chạy shutdown hooks, nhưng nó không tự chờ queue logger đã drain theo ý ứng dụng. `Runtime.getRuntime().halt(status)` kết thúc JVM ngay, không chạy hooks. Khi process bị kill cưỡng bức (như SIGKILL trên hệ hỗ trợ), lỗi hệ điều hành hay mất điện, ứng dụng không có cơ hội thực hiện cleanup. Không nên hứa bảo toàn log cuối cho các trường hợp đó.

## 6. Logging trong JVM shutdown hook thread

`Runtime.addShutdownHook` đăng ký một thread được JVM khởi động khi shutdown có trật tự:

```java
Runtime.getRuntime().addShutdownHook(
        new Thread(() -> {
            System.err.println("JVM shutdown hook started");
        }, "shutdown-observer")
);
```

Đoạn này có thể được đặt trong `main` khi JVM đang chạy bình thường. Ở đây `System.err` được chọn để minh họa độc lập với logging backend.

Những giới hạn thực tế:

- JVM khởi động các hook theo **thứ tự không xác định**, và nhiều hook có thể chạy đồng thời. Một hook đóng logger có thể chạy cạnh hook khác đang ghi log.
- Hook nên ngắn gọn, tránh deadlock và chờ không có thời hạn. Nếu hook chờ một worker mà worker lại chờ lock do hook giữ, shutdown có thể treo.
- Không gọi `System.exit` từ trong hook. Không đăng ký hook quá muộn; JVM có thể từ chối khi shutdown đã bắt đầu.
- Shutdown hook là thread **khác** thread đang xử lý request. `ThreadLocal`, MDC và trace context của request cuối **không tự truyền** vào hook. Log shutdown nên dùng metadata của service/instance, không dùng lại `request_id` hoặc `trace_id` cũ.
- Không phải kiểu kết thúc process nào cũng chạy hook, nhất là forced kill và crash.

Nếu framework đã có cơ chế quản lý vòng đời, nên điều phối ở đó: **ngừng request → dừng background workers → log tổng kết → stop logging backend**. Không dựa vào thứ tự hai shutdown hooks độc lập để tạo quan hệ phụ thuộc. Spring Boot có các cơ chế vòng đời như `SmartLifecycle`; lựa chọn cụ thể cần phù hợp phiên bản và hệ thống logging đã cấu hình.

## 7. Dừng backend: SLF4J, Logback, Log4j 2, JUL

SLF4J là **API facade**, không quy định một phương thức shutdown chung cho mọi logging implementation. Lệnh stop/flush phụ thuộc backend, appender, queue và môi trường khởi tạo.

| Thành phần | Hướng xử lý | Điều cần xác minh |
| --- | --- | --- |
| Logback Classic | Để runtime/framework quản lý lifecycle; nếu ứng dụng tự sở hữu, dừng `LoggerContext` ở bước cuối | `AsyncAppender`, queue, chính sách discard, `maxFlushTime` và timeout |
| Log4j 2 | Để hệ thống quản lý context; nếu tự quản lý, dùng lifecycle stop theo API/phiên bản tương ứng | Async logger/appender, shutdown hooks tích hợp, thời gian drain |
| `java.util.logging` | Flush/close các `Handler` do ứng dụng sở hữu đúng lúc | Ownership của handler, shared handler, các thread còn đang log |
| Custom worker | Chặn producer → STOP/drain queue → flush → join/đóng sink | Bất thường ở writer, capacity, blocking I/O, deadline |

### Ví dụ tích hợp Logback Classic

Lớp dưới dùng SLF4J và Logback Classic đã có trong classpath. Đây là **đoạn tích hợp**, không phải chương trình độc lập:

```java
import ch.qos.logback.classic.LoggerContext;
import org.slf4j.ILoggerFactory;
import org.slf4j.LoggerFactory;

public final class LogbackShutdown {
    public static void stopAfterBusinessWorkers() {
        ILoggerFactory factory = LoggerFactory.getILoggerFactory();
        if (factory instanceof LoggerContext context) {
            context.stop();
        }
    }
}
```

Trong ứng dụng **tự quản lý** backend, gọi sau khi các worker nghiệp vụ đã hoàn tất. `LoggerContext.stop()` dừng các thành phần Logback đang quản lý; `AsyncAppender` có thể chờ drain theo cấu hình và timeout tương ứng. Không suy ra rằng mạng, collector và nơi lưu trữ từ xa đã nhận và lưu bền vững mọi log.

**Đối với Spring Boot và những runtime đã sở hữu lifecycle logging**, không thêm lời gọi `context.stop()` thủ công nếu framework đang làm việc đó. Việc dừng sớm có thể làm mất các log do lifecycle callbacks khác phát sinh.

Với async backend, cần biết:
- Khi queue đầy, producer bị chặn hay appender tự bỏ log cấp thấp?
- Khi shutdown timeout, các bản ghi còn lại được xử lý hay bỏ đi?
- Appender mạng có retry/ack hoặc chỉ chuyển dữ liệu sang buffer phía sau?
- Shutdown hook của backend có được bật không? Có xung đột với hook ứng dụng không?
- Ai sở hữu quyền stop một lần, và khi đã stop có ai còn gọi logger không?

Các thuộc tính cấu hình và semantics phụ thuộc phiên bản Logback/Log4j 2; kiểm chứng trên stack thực tế thay vì mặc định mọi backend xử lý giống nhau.

## 8. Logging trong thread pool: MDC và trace context

MDC (Mapped Diagnostic Context) thường chứa `request_id`, `trace_id` hoặc thông tin hữu ích khác ở phạm vi thread. Thread pool tái sử dụng thread; nếu task không cleanup, log của request tiếp theo có thể mang metadata cũ. Shutdown hook thì chạy trong thread riêng nên không tự có MDC của request.

Ví dụ tích hợp với SLF4J, yêu cầu dependency tương ứng:

```java
import org.slf4j.MDC;

Runnable task = () -> {
    try {
        MDC.put("request_id", "req-123");
        // Thực hiện tác vụ và ghi log ở đây.
    } finally {
        MDC.remove("request_id");
    }
};
```

Nếu thread còn MDC key khác do tầng trên sở hữu, nên lưu và khôi phục snapshot thay vì `clear()` toàn bộ. MDC chỉ gắn trường log; muốn trace context đi qua executor, HTTP hoặc message queue phải dùng propagation/instrumentation phù hợp. Không lấy `ThreadLocal` của business thread từ logging worker để đoán request hiện tại; async logging backend có thể chụp MDC ngay lúc tạo log event hoặc cần cấu hình context propagation riêng.

Khi shutdown, lưu ý ba điểm:
1. Cho từng task ghi log kết thúc **trước khi** đóng tracing scope và dọn MDC; cleanup được đặt trong `finally` của đúng task.
2. Những log tổng kết sau khi request workers đã dừng nên dùng trường service-level (ví dụ event, instance, shutdown reason), không giả định tồn tại request context.
3. Nếu logging consumer và business workers dùng chung một executor, dừng executor quá sớm có thể khiến logger không còn thread để drain queue. Cần xác định rõ ownership và thứ tự dừng.

## 9. Queue đầy, deadline và shutdown trong container

**Queue đầy:** Bounded queue giới hạn bộ nhớ nhưng có thể block producer. Async logging framework khác nhau về chính sách block/drop. Khi tải log tăng vọt, một hệ thống cấu hình bỏ log sẽ không thể bảo đảm nhận đủ, ngay cả khi shutdown đã cố drain.

**Appender chậm hoặc mạng lỗi:** Flush có thể chờ I/O; nếu collector không phản hồi, shutdown sẽ chậm hoặc hết hạn. Theo dõi số event accepted, emitted, dropped, pending, độ trễ appender và trạng thái thread. Một queue còn dữ liệu trong khi writer đã chết là tín hiệu lỗi cần nhận diện.

**Deadline:** Ứng dụng production nên có thời hạn tổng cho dừng process. Chia thời gian cho nhận request cuối, dừng business workers, drain logs và đóng sink. Khi quá hạn, áp chính sách rõ ràng và chấp nhận khả năng mất log; đừng giữ JVM vô hạn chỉ để chờ một sink không thể truy cập.

**Container/SIGTERM:** Môi trường container/orchestrator có thể gửi tín hiệu dừng và sau một thời hạn sẽ force kill process. Logging backend cần được stop/flush **trong termination grace period**, sau khi producer dừng. Hook không thể cứu dữ liệu nếu process đã bị kill cưỡng bức.

**Log cuối mất nhưng API thành công:** Có thể logger đã enqueue thành công rồi process chết, hoặc backend đã flush nhưng collector chưa nhận. Cần phân biệt thành công enqueue, thành công ghi tệp cục bộ và xác nhận lưu ở đích cuối.

## 10. Kiểm thử và chẩn đoán

| Bài kiểm thử | Kỳ vọng |
| --- | --- |
| Producer ghi 3 log rồi `close` bình thường | Có đúng 3 log từ worker và marker hoàn tất sau chúng |
| Nhiều producer đồng thời | Mỗi log đã được chấp nhận được xử lý đúng một lần trong trường hợp không lỗi; thứ tự giữa producer có thể thay đổi |
| Enqueue sau khi bắt đầu close | Bị từ chối rõ ràng; không lọt phía sau STOP |
| Gọi close hai lần | Không enqueue STOP thừa; có thể chờ worker đã kết thúc |
| Queue bị đầy | Quan sát được block/drop theo chính sách thực tế |
| Worker bị interrupt hoặc lỗi I/O | Xử lý deadline và trạng thái lỗi; không tuyên bố đã drain nếu chưa xác minh |
| Thread pool tái sử dụng | Không rò rỉ `request_id`/`trace_id` giữa các request |
| JVM shutdown bình thường | Business workers dừng trước, logger dừng cuối, trong deadline |
| JVM bị force kill | Không kỳ vọng hook/flush được chạy |
| Async backend với collector lỗi | Có counters/metrics chứng minh event pending, dropped và lỗi xuất |

Với ví dụ mục 4, chạy `java ShutdownLoggingDemo` nhiều lần. Dòng `shutdown-complete` luôn nằm sau ba log từ thread `log-writer` vì main chỉ in khi `close()` đã đợi worker hoàn tất. Test chỉ ghi một sự kiện thường không phát hiện race; trong integration test nên tạo tải đủ lớn để queue thật sự tồn đọng, sau đó đếm event ở sink test và xác nhận timeout.

Khi ứng dụng không thoát, kiểm tra thread dump: có thread đang chờ `join()`, `BlockingQueue.put()`, `take()` hoặc I/O không? Nếu producer còn chạy, xem có đang giữ lock chặn shutdown không. Nếu consumer đã chết, không được chờ queue tự rỗng. Khi log thiếu, kiểm tra event đã enqueue, policy discard, flush timeout, log level, file permissions và exporter trước khi kết luận lỗi nằm ở shutdown hook.

## 11. Những sai lầm thường gặp

- **Dùng daemon như cơ chế dừng:** JVM có thể kết thúc khi queue còn log. Hãy shutdown và chờ logging worker.
- **Interrupt consumer ngay:** Thread có thể thoát khỏi `take()` trước khi đọc event cuối. Hãy drain trước, xử lý interrupt ở nhánh deadline.
- **Đóng logger rồi mới dừng executor:** Task vẫn chạy sẽ mất log. Hãy ngừng producer trước.
- **Chỉ gọi `shutdown()`:** Chưa có bằng chứng worker đã dừng. Hãy dùng `join()` hoặc `awaitTermination` và quan sát timeout.
- **Dựa vào thứ tự shutdown hooks:** JVM không đảm bảo thứ tự. Hãy có một lifecycle coordinator rõ ràng.
- **Giữ MDC của request khi vào hook:** Hook không chạy trong request thread. Ghi log shutdown bằng context phù hợp.
- **Cho rằng flush bằng lưu bền vững:** Flush chỉ xử lý bộ đệm theo hợp đồng của sink. Cần kiểm tra sự xác nhận của các tầng sau.
- **Chờ vô thời hạn:** Một appender bị treo có thể giữ process không thoát. Hãy có deadline, metrics và nhánh lỗi.
- **Tự stop backend hai lần khi framework đã quản lý:** Có thể đóng appender quá sớm và mất log cuối. Hãy xác định chủ sở hữu lifecycle.

## 12. Tiêu chí hoàn thành

Một ứng dụng được coi là có quy trình shutdown thread logging rõ ràng khi: xác định được thread nào tạo và xuất log; ngừng business producers trước; ngăn enqueue sau khi bắt đầu đóng; drain và flush theo hợp đồng của logging backend; đợi thread kết thúc trong thời hạn; báo cáo được số log pending/dropped; không rò rỉ MDC giữa thread; và đã kiểm thử shutdown bình thường, quá tải, timeout và lỗi sink.

**Điều quan trọng nhất:** shutdown logging là vấn đề **thứ tự vòng đời và dữ liệu còn trong hàng đợi**, không đơn thuần là dừng một thread. Không cơ chế nào chạy bên trong JVM có thể bảo đảm giữ log cuối nếu process bị kết thúc cưỡng bức trước khi flush.