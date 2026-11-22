# Kiểm thử đồng thời khi ghi log trong Java

## 1. Vì sao logging cần kiểm thử đồng thời?

Trong ứng dụng Java, nhiều request, tác vụ `ExecutorService`, callback và worker có thể gọi logger cùng lúc. Dù các backend logging thông dụng có cơ chế hỗ trợ gọi đồng thời, **cấu hình, appender tùy biến, bộ đệm, formatter và cách truyền ngữ cảnh** vẫn có thể tạo lỗi. Một chức năng chạy đúng ở một thread chưa chắc ghi log đúng khi có hàng chục thread cùng hoạt động.

Ví dụ lỗi điển hình:

- Hai thread cùng sửa `StringBuilder` dùng chung trước khi ghi log, khiến thông điệp bị trộn hoặc sai nội dung.
- Một appender tự viết lưu bản ghi vào `ArrayList` mà không đồng bộ: kích thước hoặc dữ liệu thu được có thể sai trong điều kiện tranh chấp.
- Giá trị `request_id` hoặc `trace_id` trong `ThreadLocal`/MDC bị giữ lại sau request và xuất hiện trong log của request khác khi thread pool tái sử dụng thread.
- Context không được chuyển sang `CompletableFuture` hoặc executor, nên log bất đồng bộ thiếu `trace_id`.
- Async appender có hàng đợi hữu hạn loại bớt bản ghi khi tải cao; một phép kiểm tra chạy ngay sau `logger.info(...)` đọc dữ liệu quá sớm rồi báo thiếu log.
- Bài test giả định thứ tự tuyệt đối của log từ các thread khác nhau, nên thất bại ngẫu nhiên dù ứng dụng và logger vẫn đúng.

Mục tiêu của **kiểm thử đồng thời logging** là chứng minh các bất biến quan sát được: mỗi sự kiện được yêu cầu ghi được biểu diễn đúng theo chính sách, không bị hỏng hoặc gắn sai ngữ cảnh, và hệ thống kết thúc/xuất log đúng trong mức tải được chọn. Cần phân biệt lỗi mất bản ghi do bug với việc lọc hoặc bỏ bản ghi **có chủ đích** bởi log level, sampling hay chính sách quá tải.

## 2. Những thuộc tính cần kiểm chứng

| Thuộc tính | Điều cần kiểm tra | Điều không nên mặc định |
| --- | --- | --- |
| **Đủ số lượng** | Với sink đồng bộ không lọc, thu đúng `threads × eventsPerThread` bản ghi | Async/sampling luôn giữ 100% log |
| **Không trùng** | Mỗi khóa sự kiện `(workerId, sequence)` xuất hiện một lần | Đếm số lượng bằng tổng dự kiến đã chứng minh không trùng |
| **Không hỏng dữ liệu** | Message, level, payload, timestamp, mã sự kiện khớp giá trị gốc | Nhiều thread có thể sửa chung một payload mutable an toàn |
| **Đúng context** | `request_id`, `trace_id`, `span_id` thuộc đúng tác vụ phát log | `ThreadLocal`/MDC tự đi theo thread mới |
| **Không rò rỉ context** | Sau tác vụ, giá trị của request cũ được khôi phục hoặc xóa | Thread của executor luôn mới |
| **Thứ tự có nghĩa** | Nếu sink có hợp đồng bảo toàn thứ tự mỗi producer, kiểm tra thứ tự đó | Có thứ tự toàn cục cố định giữa các thread |
| **Kết thúc và flush** | Bản ghi trong queue được xử lý sau tín hiệu hoàn tất/flush đúng chuẩn | Gọi logger xong nghĩa là backend đã ghi xong |
| **Xử lý quá tải** | Đúng cơ chế block, backpressure, retry, drop hoặc đếm số log bị bỏ | Mọi cấu hình async đều không mất dữ liệu |

Đừng chỉ kiểm `size()`. Nếu một event xuất hiện hai lần và một event khác bị thiếu, tổng số vẫn có thể đúng. Kiểm theo **định danh duy nhất và nội dung từng event**, rồi mới xét tổng số.

### Phân biệt thread safety và thứ tự log

Thread safety có nghĩa các thao tác đồng thời giữ đúng hợp đồng của đối tượng và không làm hỏng trạng thái; **không có nghĩa** thứ tự hai thread được lập lịch giống nhau ở mọi lần chạy. Với hai thread A và B:

```text
Thread A: A1 -> A2
Thread B: B1 -> B2
```

Sink có thể thấy `A1, B1, B2, A2` hoặc `B1, A1, A2, B2`. Nếu mỗi thread ghi đồng bộ tuần tự, ta thường có thể kiểm tra thứ tự trong riêng thread đó theo hợp đồng của sink. Khi đi qua async queue, batching, nhiều partition hoặc pipeline phân tán, phải đọc **hợp đồng ordering cụ thể** trước khi khẳng định thứ tự mà nơi lưu trữ sẽ quan sát.

## 3. Thiết kế một bài test đáng tin cậy

Một bài test đồng thời có thể lặp lại nên có các phần sau:

1. **Cô lập sink:** dùng appender/bộ nhận sự kiện chỉ dành cho test; không phụ thuộc console, file log chung hoặc trạng thái từ test khác.
2. **Đồng bộ điểm bắt đầu:** dùng `CountDownLatch` hoặc `CyclicBarrier` để các worker cùng sẵn sàng rồi bắt đầu, tăng cơ hội xuất hiện tranh chấp thật. Chỉ tạo nhiều thread mà không có cổng bắt đầu có thể vô tình chạy gần như tuần tự.
3. **Định danh duy nhất:** gắn `workerId` và `sequence` vào từng event; gắn request/trace ID riêng cho từng worker hoặc request.
4. **Thu thập an toàn:** sink giả lập có thể dùng `ConcurrentLinkedQueue` hoặc cơ chế đồng bộ phù hợp; test không được tự tạo data race làm sai kết quả đo.
5. **Chờ hoàn thành hữu hạn:** nhận kết quả qua `Future.get(timeout)`, latch và/hoặc cơ chế flush của backend; khi timeout phải thất bại có thông tin, tránh treo vô hạn.
6. **Đối chiếu sau khi hoàn thành:** kiểm tổng số, tính duy nhất, từng trường, context và các ràng buộc thứ tự được bảo đảm.
7. **Dọn tài nguyên:** dừng executor, đóng appender, khôi phục cấu hình logger và xóa/khôi phục MDC trong `finally`.

Các phép thử chính xác trên bộ nhận đồng bộ nên xác định được kết quả mỗi lần. Sau đó mới có bài stress tăng lượng thread, số event, lịch chạy và bật các cấu hình async/queue khác nhau để tìm lỗi hiếm. Stress test làm tăng xác suất phát hiện lỗi; vài lần chạy thành công không chứng minh tuyệt đối hệ thống không có race condition.

## 4. Ví dụ Java 17 chạy độc lập: kiểm thử ghi event từ nhiều thread

Ví dụ dưới đây mô phỏng **lõi phát log và test sink** bằng JDK, không phụ thuộc SLF4J/Logback. Bộ ghi dùng `ConcurrentLinkedQueue`, sự kiện là `record` bất biến. `ThreadLocal` đóng vai trò request context; mỗi worker phát 500 event, tám worker cùng đi qua một cổng bắt đầu. Chương trình xác minh số lượng, từng định danh và context, rồi chỉ in **một dòng PASS sau khi tất cả đã được kiểm tra**.

Lưu vào tệp `ConcurrentLoggingCheck.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class ConcurrentLoggingCheck {
    private static final int WORKERS = 8;
    private static final int EVENTS_PER_WORKER = 500;
    private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();
    private static final ConcurrentLinkedQueue<Event> EVENTS =
            new ConcurrentLinkedQueue<>();

    record Event(int worker, int sequence, String requestId, String message) {}

    private static void emit(int worker, int sequence) {
        String requestId = REQUEST_ID.get();
        EVENTS.add(new Event(
                worker, sequence, requestId, "event-" + sequence));
    }

    private static void verify() {
        int expected = WORKERS * EVENTS_PER_WORKER;
        if (EVENTS.size() != expected) {
            throw new AssertionError(
                    "Expected " + expected + " events, got " + EVENTS.size());
        }

        boolean[][] seen = new boolean[WORKERS][EVENTS_PER_WORKER];
        for (Event event : EVENTS) {
            int w = event.worker();
            int s = event.sequence();
            if (w < 0 || w >= WORKERS || s < 0 || s >= EVENTS_PER_WORKER) {
                throw new AssertionError("Unexpected event id: " + event);
            }
            if (seen[w][s]) {
                throw new AssertionError("Duplicate event: " + w + "/" + s);
            }
            seen[w][s] = true;

            if (!("req-" + w).equals(event.requestId())) {
                throw new AssertionError("Wrong context: " + event);
            }
            if (!("event-" + s).equals(event.message())) {
                throw new AssertionError("Corrupt message: " + event);
            }
        }

        for (int w = 0; w < WORKERS; w++) {
            for (int s = 0; s < EVENTS_PER_WORKER; s++) {
                if (!seen[w][s]) {
                    throw new AssertionError("Missing event: " + w + "/" + s);
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        CountDownLatch ready = new CountDownLatch(WORKERS);
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(WORKERS);

        try {
            List<Future<?>> futures = new ArrayList<>();
            for (int worker = 0; worker < WORKERS; worker++) {
                final int w = worker;
                futures.add(pool.submit(() -> {
                    REQUEST_ID.set("req-" + w);
                    try {
                        ready.countDown();
                        if (!start.await(10, TimeUnit.SECONDS)) {
                            throw new AssertionError("Start timeout");
                        }
                        for (int s = 0; s < EVENTS_PER_WORKER; s++) {
                            emit(w, s);
                        }
                    } finally {
                        REQUEST_ID.remove();
                        if (REQUEST_ID.get() != null) {
                            throw new AssertionError("Context not cleared");
                        }
                    }
                    return null;
                }));
            }

            if (!ready.await(10, TimeUnit.SECONDS)) {
                throw new AssertionError("Workers not ready");
            }
            start.countDown();

            for (Future<?> future : futures) {
                future.get(10, TimeUnit.SECONDS);
            }

            verify();
            System.out.println(
                    "PASS events=4000 workers=8 perWorker=500 context=correct");
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }
}
```

Biên dịch và chạy với Java 17 trở lên:

```bash
javac ConcurrentLoggingCheck.java
java ConcurrentLoggingCheck
```

Kết quả stdout khi tất cả kiểm chứng thành công:

```text
PASS events=4000 workers=8 perWorker=500 context=correct
```

Vì chương trình đợi tất cả `Future` và chỉ in sau `verify()`, stdout không phụ thuộc thứ tự scheduler. Nếu thiếu, trùng, sai request ID hoặc sai message, test ném `AssertionError` và không in dòng PASS. Nếu một worker lỗi, `Future.get` chuyển lỗi thành `ExecutionException` ở thread chính; timeout cũng làm test thất bại. `finally` thả cổng start và yêu cầu dừng executor, tránh để worker tiếp tục treo khi test thất bại.

**Giới hạn của ví dụ:** `ConcurrentLinkedQueue` đã là cấu trúc đồng thời an toàn. Bài test kiểm chứng luồng phát event, cách thu thập, xác định danh tính và cách kiểm tra; nó **chưa chứng minh** appender/file encoder/async queue của hệ thống thực là an toàn. Để kiểm thử sản phẩm, thay hàm `emit` bằng thao tác gọi logger thực và thu bản ghi ở appender/consumer được cấu hình riêng trong test.

## 5. Kiểm thử logger và appender thật

Với SLF4J và Logback, lời gọi `logger.info("request={} seq={}", requestId, seq)` cần được kiểm tra bằng dữ liệu thực sự đến **điểm nhận cuối**. Có thể dùng custom test appender đặt vào đúng `LoggerContext` của test. Đừng lấy trạng thái từ file stdout dùng chung giữa các test, đặc biệt khi test framework có thể chạy song song.

Ví dụ dưới đây là **đoạn minh họa** một test appender cho Logback Classic; cần thư viện Logback và SLF4J, cấu hình attach/detach appender, logger phù hợp, cùng một test JUnit hoặc ứng dụng gọi nó. Đây không phải chương trình độc lập:

```java
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.AppenderBase;
import java.util.List;
import java.util.Map;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;

record CapturedLog(String message, String threadName, String traceId) {}

final class CapturingAppender extends AppenderBase<ILoggingEvent> {
    private final Queue<CapturedLog> captured =
            new ConcurrentLinkedQueue<>();

    @Override
    protected void append(ILoggingEvent event) {
        event.prepareForDeferredProcessing();
        Map<String, String> mdc = event.getMDCPropertyMap();
        String traceId = mdc == null ? null : mdc.get("trace_id");

        captured.add(new CapturedLog(
                event.getFormattedMessage(),
                event.getThreadName(),
                traceId));
    }

    List<CapturedLog> snapshot() {
        return List.copyOf(captured);
    }
}
```

Phải bắt đầu appender (`start()`), gắn vào logger được kiểm thử, tháo ra và dừng trong `finally`/teardown. `captured` là hàng đợi an toàn; `CapturedLog` là bản chụp bất biến của message, tên thread và trace ID **tại thời điểm append**. Không giữ tham chiếu tới cấu trúc mutable rồi so sánh sau, vì dữ liệu có thể đổi khi test kiểm tra. Với backend khác, dùng API test appender tương ứng và không mặc định semantics của Logback áp dụng cho mọi thư viện.

Một test tích hợp hữu ích phát các chuỗi có khóa riêng, chẳng hạn:

```text
event=request-7 seq=0
event=request-7 seq=1
event=request-3 seq=0
```

Thay vì so sánh toàn bộ file log theo thứ tự, trích `requestId` và `seq`, kiểm đúng tập khóa cần có, message/level và context. Với các luồng chung, thứ tự giữa `request-7` và `request-3` là không xác định.

Nếu đang dùng **async appender**, cần đặt bộ bắt log ở **phía sau async appender** để test thực sự đi qua queue. Không khẳng định thiếu log chỉ vì vừa phát log xong mà chưa thấy trong sink. Đợi một điều kiện hoàn tất có timeout hoặc dùng cách flush/stop theo hợp đồng của backend; đo số drop nếu cấu hình cho phép bỏ bản ghi. Khi async queue được cấu hình drop mức INFO lúc bão hòa, kỳ vọng 100% bản ghi ở tải cao là sai; cần kiểm chính sách ưu tiên, số lượng drop và log quan trọng được giữ theo hợp đồng.

## 6. Kiểm thử MDC, ThreadLocal và context propagation

Trong nhiều framework Java, MDC lưu các trường như `request_id`, `trace_id` và `span_id` gắn với thread hiện tại. Test đồng thời thường phát hiện hai loại lỗi:

- **Mất context:** request đặt MDC ở thread A, nhưng tác vụ chạy trong executor ở thread B mà không truyền context. Dòng log ở B thiếu ID, dù log ở A có đủ.
- **Rò rỉ context:** worker xử lý request A rồi tái sử dụng cho request B; code không xóa hoặc khôi phục MDC, khiến log của B mang ID của A.

Test cần tạo nhiều request có ID khác nhau trên cùng thread pool, ép một số tác vụ chạy bất đồng bộ, rồi xác minh **mỗi event thuộc đúng request**. Sau khi tác vụ kết thúc, đưa một tác vụ khác vào pool và kiểm tra giá trị MDC không còn sót; phải thiết kế cách chạy sao cho kiểm được các worker liên quan, vì gửi một tác vụ mới không bảo đảm nó chạy lại đúng mọi thread cũ.

Đoạn minh họa dưới đây truyền **bản sao MDC** khi submit tác vụ sang `Executor`, rồi khôi phục MDC trước đó trong `finally`. Cần SLF4J, một `Executor` được cấp từ bên ngoài, và code trong lớp tiện ích; đây không phải chương trình độc lập:

```java
import java.util.Map;
import java.util.concurrent.Executor;
import org.slf4j.MDC;

static void executeWithMdc(Executor executor, Runnable task) {
    Map<String, String> captured = MDC.getCopyOfContextMap();

    executor.execute(() -> {
        Map<String, String> previous = MDC.getCopyOfContextMap();
        try {
            if (captured == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(captured);
            }
            task.run();
        } finally {
            if (previous == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(previous);
            }
        }
    });
}
```

Điểm cần test ở đây là `captured` được lấy lúc **giao việc**, không phải lúc worker bắt đầu chạy, và `previous` được phục hồi kể cả khi `task.run()` ném exception. Đoạn này chỉ truyền **MDC map**, không tự động truyền toàn bộ OpenTelemetry trace/span context; với ứng dụng đã instrument, ưu tiên giải pháp context-aware executor hoặc instrumentation phù hợp của stack hiện có. Việc copy MDC cũng không thay thế chính sách bảo vệ thông tin nhạy cảm: không đưa token, mật khẩu hoặc dữ liệu cá nhân không cần thiết vào context.

## 7. Kiểm thử khi log không đồng bộ và khi quá tải

Logger bất đồng bộ chia ít nhất hai mốc thời gian: **lời gọi ứng dụng chấp nhận sự kiện** và **consumer xuất sự kiện đến nơi lưu trữ**. Kết quả không thể kết luận đúng nếu test chỉ đợi thread ứng dụng mà không đợi pipeline xử lý log hoàn tất.

Thiết kế kiểm thử theo chính sách:

| Cấu hình/pipeline | Điều cần xác nhận |
| --- | --- |
| Sink đồng bộ không lọc | Đủ tất cả ID; không trùng/hỏng; trả lỗi theo hợp đồng nếu ghi thất bại |
| Async queue không drop trong mức tải thiết kế | Sau khi hoàn tất/flush, số lượng và dữ liệu khớp; không còn backlog ngoài dự kiến |
| Async queue hữu hạn có discard | Drop xảy ra theo cấu hình và được đo; test không đòi giữ các log được phép loại |
| Retry khi downstream lỗi tạm thời | Có giới hạn retry, thoát đúng timeout và không làm trùng event nếu hợp đồng yêu cầu `at-most-once` hoặc dedup |
| Pipeline batching hoặc nhiều partition | Thứ tự chỉ được kiểm tại phạm vi backend bảo đảm, thường không so sánh thứ tự toàn cục |
| Shutdown trong lúc tải | Flush/close theo chính sách, không treo vô hạn, không bỏ event đã được cam kết lưu nếu hợp đồng yêu cầu |

Cần phân biệt rõ **at-most-once**, **at-least-once** và **exactly-once**. Hệ thống có retry có thể tạo bản ghi trùng nếu giao hàng `at-least-once`; muốn loại trùng khi phân tích phải có event ID phù hợp. Test không được áp một giả định exactly-once cho một đường truyền không có hợp đồng đó.

Tránh `Thread.sleep(1000)` để “chờ log”: trên máy nhanh nó lãng phí, trên CI chậm vẫn có thể thiếu. Dùng `CountDownLatch` tại sink, tín hiệu flush được backend hỗ trợ, hoặc deadline hữu hạn kèm điều kiện quan sát được. Nếu shutdown async logger để flush, cần bảo đảm appender đã stop trước khi snapshot và không còn producer nào đang ghi.

## 8. Trường hợp lỗi nên chủ động tái hiện

| Tình huống | Kỳ vọng kiểm thử |
| --- | --- |
| Một worker ném exception trong lúc ghi | Không làm treo bài test; context dọn bằng `finally`; log lỗi theo chính sách |
| Nhiều thread ghi đồng thời với message dài/Unicode | Không cắt sai byte, không trộn payload, JSON/text log parse được |
| Một formatter/custom encoder chia sẻ trạng thái mutable | Không có dữ liệu bị trộn, timestamp/format hợp lệ khi tranh chấp |
| Thread pool xử lý liên tiếp request A và B | Không có log của B chứa `request_id`/trace ID của A |
| `CompletableFuture` chạy trên executor khác | Context được truyền đúng khi cấu hình propagation; không tự giả định |
| Nhiều service và trace context | `trace_id` nhất quán theo request, `span_id` khớp span tại thời điểm phát log |
| Burst lớn vượt queue capacity | Backpressure/drop/retry đúng hợp đồng, có chỉ số theo dõi |
| Test suite chạy song song | Các test không trộn appender, không thay đổi global root logger gây nhiễm kết quả |
| Sampling hoặc lọc `DEBUG`/`INFO` | Chỉ đối chiếu những event chính sách cam kết giữ; log lỗi/audit tuân theo chính sách riêng |

Đừng sửa bài test “cho qua” bằng cách giảm số worker tới mức không còn tranh chấp, tăng timeout vô hạn, bỏ hết assertion, hoặc sắp xếp log theo nội dung rồi tuyên bố đã xác minh thứ tự phát thực tế. Nếu test dễ thất bại ngẫu nhiên, xem lại đồng bộ điểm bắt đầu, điều kiện kết thúc, giả định về thứ tự, chính sách drop và cách cô lập logger trước khi kết luận là race trong ứng dụng.

## 9. Cách đọc kết quả và đưa vào CI

Một bộ kiểm thử phù hợp nên có **ba lớp**:

1. **Unit test:** test riêng logic tạo message, enrichment MDC và filter/sampling; dùng sink bất biến/thread-safe, dữ liệu cố định, kết quả xác định.
2. **Integration test:** khởi động backend logging thực với cấu hình và appender riêng; phát đồng thời, đợi flush, đọc log đã serialize, kiểm đúng trường/thông điệp/correlation ID.
3. **Stress/soak test:** tăng thread, tốc độ log, kích thước message, thời gian chạy, tình huống lỗi backend; đo throughput, queue size, dropped events, độ trễ của luồng nghiệp vụ và bộ nhớ. Những bài nặng có thể chạy trong pipeline riêng theo lịch, giữ bộ kiểm thử nhanh trong mỗi lần CI.

Với test bất kỳ, ghi rõ cấu hình: JVM/JDK, số thread, số event, loại appender, queue capacity, mẫu dữ liệu, cơ chế timeout, chính sách lọc/retention và backend. Một thất bại có giá trị điều tra khi báo được event ID bị thiếu, bị trùng, sai context hay thời điểm timeout, thay vì chỉ hiện “expected 4000 but was 3999”.

**Checklist hoàn tất:** có kích hoạt concurrent start thật; thu sự kiện an toàn; kiểm từng ID, message và context; xử lý kết quả `Future` cùng timeout; phân biệt ordering mỗi thread với ordering toàn cục; với async phải chờ tiêu thụ/flush; cleanup MDC, appender và executor; và quan sát drop theo chính sách. Khi các điều kiện này được kiểm đúng, bài test sẽ phát hiện được nhiều lỗi logging chỉ xuất hiện dưới tải đồng thời mà một bài test tuần tự bỏ sót.
