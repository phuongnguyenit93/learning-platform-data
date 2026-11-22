# Context và thread trong Java Logging

## 1. Context của log là gì và vì sao thread quan trọng?

**Logging context** là thông tin bổ sung cho một sự kiện log để người đọc biết **sự kiện thuộc request, tác vụ, giao dịch, trace hoặc luồng xử lý nào**. Trong ứng dụng xử lý song song, một dòng `INFO request.completed` không đủ để phân biệt hai request đang chạy xen kẽ.

Ví dụ không có context:

```text
INFO  event=order.received
INFO  event=order.received
WARN  event=payment.retry
INFO  event=order.completed
```

Ví dụ có context:

```text
INFO  [http-1] requestId=req-A event=order.received
INFO  [http-2] requestId=req-B event=order.received
WARN  [pool-1] requestId=req-A event=payment.retry
INFO  [http-2] requestId=req-B event=order.completed
```

Những dòng trên chỉ là **minh họa**. Khi có `requestId`, ta nối được các dòng của cùng một request dù chúng xen kẽ với nhau và có thể chạy ở **các thread khác nhau**. Tên thread cho biết **nơi phát log tại thời điểm đó**, không phải danh tính bền vững của request.

Trong Java, cách đơn giản để giữ context theo từng thread là `ThreadLocal`. Các logging framework như **Logback** hỗ trợ **MDC (Mapped Diagnostic Context)** thông qua API `org.slf4j.MDC`; Log4j 2 có cơ chế `ThreadContext`; JUL (`java.util.logging`) không có MDC chuẩn tương tự, nhưng có thể dùng context tường minh hoặc `ThreadLocal` do ứng dụng tự quản lý.

Điểm cốt lõi của bài:

> **Context lưu theo thread không tự động đồng nghĩa context đi theo một công việc.** Khi task chuyển tới `ExecutorService`, `CompletableFuture`, callback, message listener hoặc luồng xử lý bất đồng bộ, phải hiểu và kiểm soát quá trình **capture → install → execute → restore**.

### Mục tiêu

Sau bài học, bạn có thể:

1. Phân biệt **thread name/thread ID** với **requestId, traceId, spanId và jobId**.
2. Hiểu `ThreadLocal`, MDC và giới hạn của việc giữ context theo thread.
3. Biết vì sao thread pool có thể gây **mất context** hoặc **rò context sang task khác**.
4. Truyền, khôi phục và xóa context một cách an toàn với `Runnable`, `ExecutorService` và `CompletableFuture`.
5. Hiểu khác biệt giữa context của **thread phát event** và thread **xử lý output log bất đồng bộ**.
6. Áp dụng trong SLF4J/Logback, nhận diện trường hợp cần distributed tracing hoặc context propagation của framework.
7. Chạy một chương trình **Java 17 chỉ dùng JDK** để chứng minh hiện tượng và cách sửa.

## 2. Đừng đồng nhất thread với request

Một hệ thống HTTP hoặc xử lý sự kiện có thể diễn ra như sau:

```text
Request req-A
  |
  +--> http-worker-1: validate input
  |
  +--> executor-worker-2: call payment provider
  |
  +--> http-worker-1: return response

Request req-B
  |
  +--> http-worker-1: receive request sau khi req-A kết thúc
  |
  +--> executor-worker-3: process asynchronously
```

Ở đây:

- **Một request có thể chạy trên nhiều thread**: `req-A` xuất hiện trên cả `http-worker-1` và `executor-worker-2`.
- **Một thread có thể phục vụ nhiều request theo thời gian**: `http-worker-1` dùng lại cho `req-B`.
- Thread pool thường **tái sử dụng thread** thay vì tạo thread mới cho mỗi task.
- Tên thread có thể là `main`, `worker-1`, `ForkJoinPool.commonPool-worker-*` hoặc một tên do framework đặt. Tên này không phải correlation ID xuyên hệ thống.
- `requestId` và `traceId` thường phải được tạo hoặc tiếp nhận ở ranh giới request, gắn vào context, rồi **truyền cùng công việc** khi thực thi ở nơi khác.

Do đó, chỉ thêm `%thread` vào layout vẫn **không** giải quyết được việc tìm mọi log của một request. Tên thread chỉ là một chiều chẩn đoán hữu ích.

| Thông tin | Dùng để làm gì? | Có ổn định xuyên thread không? |
| --- | --- | --- |
| Thread name | Xác định thread đã phát log | Không; có thể thay ở bước khác |
| Thread ID | Xác định thread trong một phạm vi runtime | Không phải ID request, không dùng làm khóa phân tán |
| `requestId` | Gom log của một HTTP request hoặc một lượt xử lý | Có, nếu được truyền đúng |
| `jobId` | Gom log của một background job | Có, nếu được gắn/lan truyền đúng |
| `traceId` | Liên kết hoạt động của một distributed trace | Có, nếu tracing được propagate đúng |
| `spanId` | Xác định một đơn vị công việc trong trace | Có thể thay giữa các bước/span |
| `userId` | Ngữ cảnh nghiệp vụ có thể hữu ích nhưng nhạy cảm | Không nên đưa vào log khi không có nhu cầu và quyền phù hợp |

**Không đặt request ID vào tên Logger.** Logger name nên cố định theo package/class, ví dụ `com.example.order.OrderService`. Đặt tên `com.example.order.req-A` cho từng request gây bùng nổ số Logger và khó cấu hình level. Hãy giữ ID trong MDC hoặc event fields.

## 3. ThreadLocal hoạt động như thế nào?

`ThreadLocal<T>` cho phép cùng một biến `ThreadLocal` được truy cập từ nhiều thread, nhưng **mỗi thread có giá trị riêng**. Một thread gọi `set(...)` không có nghĩa thread khác gọi `get()` sẽ nhìn thấy giá trị đó.

Ví dụ **mảnh Java**:

```java
private static final ThreadLocal<String> REQUEST_ID =
        new ThreadLocal<>();

REQUEST_ID.set("req-42");
try {
    logger.info("event=request.received");
} finally {
    REQUEST_ID.remove();
}
```

Đây là **mảnh minh họa trong một phương thức**, giả sử `logger` đã có. `set(...)` gắn giá trị với thread hiện tại; `get()` đọc ở chính thread đó; `remove()` dọn giá trị sau phạm vi xử lý.

### 3.1. Vì sao phải dọn context?

Thread trong pool có thể sống suốt thời gian ứng dụng. Nếu request A gắn `requestId=req-A` rồi quên xóa, thread đó có thể xử lý request B và **tiếp tục đọc req-A**, làm log của hai người dùng/giao dịch bị trộn nhầm.

Đây vừa là lỗi quan sát vừa có thể là **rò thông tin giữa các request**. Dọn context bằng `finally` là quy tắc quan trọng, kể cả khi task ném exception.

### 3.2. `remove()` không tương đương `set(null)` trong mọi trường hợp

Với `ThreadLocal` thông thường, `remove()` loại entry của thread hiện tại, còn `set(null)` vẫn đặt một giá trị `null` cho key. Nếu `ThreadLocal.withInitial(...)` được dùng, sau `remove()`, lần `get()` tiếp theo có thể gọi lại supplier khởi tạo. Vì vậy cần hiểu ngữ nghĩa khi thiết kế context.

Đối với context scope, có thể **khôi phục giá trị trước đó** thay vì luôn xóa. Điều này đặc biệt quan trọng khi các phạm vi **lồng nhau** (request → operation → subtask), hoặc một wrapper chạy trên thread đang có ngữ cảnh hợp lệ của chính nó.

### 3.3. ThreadLocal không thay việc truyền dữ liệu rõ ràng

Một `ThreadLocal` giúp giảm việc truyền cùng một chuỗi ID qua mọi phương thức chỉ để in log. Nhưng logic nghiệp vụ quan trọng (quyền truy cập, tenant, giao dịch, deadline) **không nên âm thầm phụ thuộc vào một MDC/ThreadLocal dành riêng cho logging**. Khi cần dữ liệu để ra quyết định nghiệp vụ, nên truyền bằng tham số, một `Context` object bất biến hoặc cơ chế context được framework quy định rõ.

## 4. MDC trong SLF4J và Logback

**MDC — Mapped Diagnostic Context** — là API phổ biến để lưu cặp `String key → String value` gắn với context diagnostic của thread hiện tại.

Ví dụ:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

Logger log = LoggerFactory.getLogger("com.example.checkout");

MDC.put("requestId", "req-42");
MDC.put("operation", "placeOrder");
try {
    log.info("event=order.received orderId={}", "ord-17");
} finally {
    MDC.remove("operation");
    MDC.remove("requestId");
}
```

Đây là **mảnh mã dùng trong một phương thức**, không phải lớp Java độc lập. Cần có `slf4j-api` và một provider hỗ trợ logging theo cấu hình thực tế.

Với Logback, mẫu pattern:

```xml
<pattern>%-5level [%thread] requestId=%X{requestId} operation=%X{operation} %logger{36} - %msg%n</pattern>
```

được đặt bên trong `<encoder>` của Appender. `%X{requestId}` đọc giá trị từ MDC của logging event; `%thread` hiển thị tên thread phát log, không phải giá trị trong MDC.

Một dòng minh họa:

```text
INFO  [http-1] requestId=req-42 operation=placeOrder c.e.checkout.OrderService - event=order.received orderId=ord-17
```

**Chú ý:** SLF4J là facade/API; hành vi lưu trữ và xuất MDC cụ thể phụ thuộc MDC adapter và backend. Với một provider không hỗ trợ MDC hữu ích, việc gọi API MDC không đảm bảo mọi field được ghi ra output. Phải xác nhận backend được chọn và encoder/layout thực sự xuất context.

### 4.1. MDC không phải global map chia sẻ cho mọi thread

`MDC.put` ghi vào context của **thread hiện tại**. Không nên hiểu `MDC.get("requestId")` là một cấu hình toàn cục dùng chung cho toàn JVM.

Nếu hai thread ghi:

```text
thread-A: MDC.put("requestId", "req-A")
thread-B: MDC.put("requestId", "req-B")
```

mỗi thread phải thấy context của chính mình theo implementation MDC hỗ trợ. Một thread không tự nhìn thấy context của thread khác chỉ vì cả hai cùng dùng key `requestId`.

### 4.2. `getCopyOfContextMap` và `setContextMap`

SLF4J MDC có hai API then chốt:

- `MDC.getCopyOfContextMap()`: lấy **bản sao** của map của thread gọi, có thể trả `null` nếu không có context.
- `MDC.setContextMap(map)`: xóa context map hiện tại rồi **copy** map được truyền vào cho thread đang chạy.
- `MDC.clear()`: xóa mọi entry của thread hiện tại.
- `MDC.remove(key)`: xóa một key.
- `MDC.putCloseable(key, value)`: tạo một scope tiện dụng có thao tác remove key khi đóng; **không nên mặc định nó tự khôi phục giá trị cũ bị ghi đè của cùng key**.

Không truyền nguyên một mutable `Map` dùng chung và tiếp tục sửa sau khi submit. Hãy capture snapshot trước khi giao task; nếu cần immutable snapshot, tạo bản sao như `Map.copyOf(...)` đối với dữ liệu key/value khác `null`.

**Phiên bản:** từ SLF4J 2.0, `setContextMap(null)` được chấp nhận theo API; trong các đoạn minh họa muốn tương thích linh hoạt, có thể dùng `MDC.clear()` khi snapshot là `null`.

## 5. Vì sao context mất khi dùng ExecutorService?

Ví dụ **đoạn minh họa**:

```java
MDC.put("requestId", "req-42");

ExecutorService executor = Executors.newFixedThreadPool(2);
executor.submit(() -> {
    // Thread worker có thể không có requestId của thread gọi.
    logger.info("event=async.work");
});
```

Trong đoạn này, `MDC.put` chạy ở thread gọi, còn `logger.info` chạy ở thread do pool quản lý. Không có cơ chế propagate rõ ràng, bạn **không được giả định** worker có cùng MDC. Ví dụ cũng chưa xử lý shutdown/cleanup; nó được dùng để chỉ ra điểm mất context, **không phải chương trình độc lập hoàn chỉnh**.

Một hình dung:

```text
Thread HTTP-1                        Thread pool-1
MDC: {requestId=req-42}              MDC: {}
    |                                     ^
    +---- submit(Runnable) ---------------+
                                          |
                                    logger.info(...)
                                    requestId trống
```

`submit` chuyển **công việc**, không mang theo toàn bộ các `ThreadLocal` của thread nguồn. Trong executor tái sử dụng thread, tình huống còn nguy hiểm hơn: nếu một task trước đã quên cleanup, worker có thể có **context cũ** chứ không đơn thuần là rỗng.

### 5.1. `InheritableThreadLocal` có giải quyết không?

`InheritableThreadLocal` có thể truyền một giá trị từ thread cha sang **thread con được tạo mới** theo cơ chế kế thừa lúc tạo thread. Nó **không phải giải pháp mặc định cho thread pool**:

- Pool tạo hoặc giữ thread trước khi một request tới.
- Một worker xử lý nhiều task khác nhau; giá trị kế thừa lúc tạo thread không tự đổi theo từng lần submit.
- Nếu pool tạo thread khi một request đang hoạt động, worker có thể mang context lúc đó sang các task về sau.
- Kế thừa một reference mutable có thể dẫn tới chia sẻ trạng thái ngoài ý muốn nếu không snapshot phù hợp.

Vì vậy dùng `InheritableThreadLocal` để “chữa” MDC trong pool thường không đủ hoặc không an toàn. Truyền context theo **ranh giới task** hoặc dùng instrumentation/framework hỗ trợ đúng sẽ rõ ràng hơn.

## 6. Quy trình chuẩn: capture → install → execute → restore

Mô hình an toàn cho context theo thread:

```text
Thread gọi:
  1. Capture snapshot context hiện tại
  2. Submit công việc kèm snapshot

Thread worker:
  3. Lưu context cũ của worker
  4. Install snapshot của task
  5. Thực hiện công việc và ghi log
  6. Trong finally: khôi phục context cũ hoặc clear
```

Vì sao **khôi phục** thay vì đơn thuần `clear`? Nếu task được bọc chạy trong một scope có context hợp lệ trước đó (hoặc wrapper lồng nhau), việc clear bừa bãi có thể xóa context thuộc scope ngoài. Khôi phục context trước khi wrapper chạy giữ đúng ngữ nghĩa phạm vi. Trong những hệ thống chủ động yêu cầu worker phải rỗng sau task, một chính sách clear cũng có thể phù hợp, nhưng phải được định nghĩa rõ.

### 6.1. Ví dụ wrapper SLF4J MDC dùng `Runnable`

```java
import java.util.Map;
import org.slf4j.MDC;

// Gọi từ thread đang có MDC, tại thời điểm submit.
Map<String, String> captured = MDC.getCopyOfContextMap();

executor.submit(() -> {
    Map<String, String> previous = MDC.getCopyOfContextMap();
    try {
        if (captured == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(captured);
        }

        logger.info("event=async.work");
        doWork();
    } finally {
        if (previous == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(previous);
        }
    }
});
```

Đây là **mảnh mã**, giả sử `executor`, `logger` và `doWork()` đã định nghĩa, không phải một chương trình Java hoàn chỉnh. Snapshot được capture **ngoài lambda, trên thread submit**; nếu gọi `MDC.getCopyOfContextMap()` lần đầu **bên trong worker**, bạn đã đọc context sai thread.

Những điểm quan trọng:

- `getCopyOfContextMap` tạo bản sao; task không phụ thuộc vào thay đổi MDC của thread gọi sau khi submit.
- Wrapper **install snapshot trước khi gọi** logic nghiệp vụ.
- `finally` chạy kể cả khi `doWork()` ném lỗi, giúp tránh rò context.
- Nếu worker trước đó có context hợp lệ của scope ngoài, wrapper khôi phục nó.
- Cần coi snapshot MDC chỉ là **context diagnostic**, không mặc định chứa đầy đủ mọi thông tin về security/tracing/transaction.
- `MDC.setContextMap` có thao tác thay thế toàn map, nên không chỉ khôi phục một key tùy tiện khi đã cài cả map.

### 6.2. Trường hợp task được hủy hoặc bị từ chối

Nếu task **chưa từng chạy**, lambda không có cơ hội đi vào `finally` của worker, nhưng nó cũng chưa install context vào worker. Tuy nhiên snapshot gắn trong object task có thể giữ dữ liệu cho tới khi hàng đợi giải phóng nó; vì vậy không capture dữ liệu nhạy cảm hoặc object quá lớn.

Nếu task được chạy rồi bị interrupt hoặc ném exception, `finally` vẫn là cơ chế cleanup cốt lõi. Lưu ý `finally` không thể đảm bảo chạy khi JVM chết đột ngột hoặc process bị kill.

### 6.3. Scope MDC lồng nhau và putCloseable

Nếu đang ở `requestId=req-A`, một operation tạm đặt `requestId=req-B` rồi kết thúc, bạn có thể muốn **khôi phục req-A**. `MDC.putCloseable("requestId", "req-B")` giúp remove key khi đóng, nhưng không nên coi nó là một stack restore đầy đủ cho giá trị cũ của cùng key.

Một mẫu cho riêng **một key**:

```java
String previous = MDC.get("requestId");
try {
    MDC.put("requestId", "req-B");
    logger.info("event=nested.operation");
} finally {
    if (previous == null) {
        MDC.remove("requestId");
    } else {
        MDC.put("requestId", previous);
    }
}
```

Đây là mảnh mã minh họa. Với nhiều key hoặc task wrapper, lưu/khôi phục **cả context map** thường ít lỗi hơn tự thao tác hàng loạt từng key.

## 7. Ví dụ Java 17 chạy độc lập, không cần dependency ngoài

Chương trình sau chỉ dùng **JDK 17**, `java.util.logging` và `ThreadLocal<Map<String,String>>`. Đây là ví dụ kiểm chứng **bản chất context gắn với thread**, không phải minh họa rằng JUL có MDC chuẩn.

Chương trình được thiết kế để cho thấy:

1. Thread `main` có `requestId=req-42`.
2. Task thứ nhất trên thread pool chạy **không propagate** nên in `requestId=-`.
3. Task thứ hai được bọc bằng snapshot nên in `requestId=req-42`.
4. Sau khi wrapper chạy xong và cleanup, task kế tiếp trên **cùng worker** không thấy requestId cũ.
5. Thread main vẫn giữ context của mình cho đến khi `finally` dọn.

Để stdout xác định, chương trình sử dụng một `Handler` JUL **đồng bộ** tự in ra `System.out` và lấy context ngay ở thread gọi `Logger.info(...)`. Đó là lựa chọn phục vụ demo; không dùng cách đọc `ThreadLocal` trong một Handler bất đồng bộ ở thread ghi output, vì khi đó context có thể thuộc **thread ghi**, không phải thread phát log.

### 7.1. File `ContextThreadDemo.java`

```java
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class ContextThreadDemo {
    private static final ThreadLocal<Map<String, String>> CONTEXT =
            new ThreadLocal<>();
    private static final Logger LOG =
            Logger.getLogger("demo.logging.ContextThreadDemo");

    public static void main(String[] args) throws Exception {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        Handler handler = new Handler() {
            @Override
            public synchronized void publish(LogRecord record) {
                if (!isLoggable(record)) {
                    return;
                }
                Map<String, String> context = CONTEXT.get();
                String requestId = context == null
                        ? "-" : context.getOrDefault("requestId", "-");
                System.out.println(Thread.currentThread().getName()
                        + " requestId=" + requestId
                        + " " + record.getLevel().getName()
                        + " " + record.getMessage());
            }

            @Override
            public void flush() {
                System.out.flush();
            }

            @Override
            public void close() {
                flush();
            }
        };
        handler.setLevel(Level.ALL);
        LOG.addHandler(handler);

        ExecutorService executor = Executors.newSingleThreadExecutor(
                task -> new Thread(task, "worker-1"));
        try {
            CONTEXT.set(Map.of(
                    "requestId", "req-42", "operation", "submitOrder"));
            LOG.info("event=main.begin");

            executor.submit(() ->
                    LOG.info("event=worker.no_context")).get();

            Map<String, String> captured = snapshot();
            executor.submit(withContext(captured, () ->
                    LOG.info("event=worker.with_context"))).get();

            executor.submit(() ->
                    LOG.info("event=worker.after_cleanup")).get();
            LOG.info("event=main.end");
        } finally {
            CONTEXT.remove();
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
            LOG.removeHandler(handler);
            handler.close();
        }
    }

    private static Map<String, String> snapshot() {
        Map<String, String> current = CONTEXT.get();
        return current == null ? null : Map.copyOf(current);
    }

    private static Runnable withContext(
            Map<String, String> captured, Runnable work) {
        return () -> {
            Map<String, String> previous = CONTEXT.get();
            try {
                if (captured == null) {
                    CONTEXT.remove();
                } else {
                    CONTEXT.set(captured);
                }
                work.run();
            } finally {
                if (previous == null) {
                    CONTEXT.remove();
                } else {
                    CONTEXT.set(previous);
                }
            }
        };
    }
}
```

### 7.2. Biên dịch và chạy

Tại thư mục chứa `ContextThreadDemo.java`:

```bash
javac ContextThreadDemo.java
java ContextThreadDemo
```

**Stdout chính xác với JDK 17 và cách chạy thông thường:**

```text
main requestId=req-42 INFO event=main.begin
worker-1 requestId=- INFO event=worker.no_context
worker-1 requestId=req-42 INFO event=worker.with_context
worker-1 requestId=- INFO event=worker.after_cleanup
main requestId=req-42 INFO event=main.end
```

Chương trình đã được **kiểm tra biên dịch bằng `javac --release 17` và chạy**, với đúng đầu ra trên. Không cần Maven/Gradle và không cần logging backend ngoài JDK.

### 7.3. Phân tích từng bước

- `CONTEXT` là `ThreadLocal` giữ một map context cho mỗi thread.
- `Map.of(...)` và `Map.copyOf(...)` tạo context map bất biến, tránh worker vô tình làm thay đổi snapshot của thread gọi. Các key/value của demo đều khác `null`; `Map.copyOf` không chấp nhận key/value null.
- `newSingleThreadExecutor` bảo đảm các task chạy lần lượt trên cùng một worker nếu không xảy ra tình huống thay worker do lỗi; `ThreadFactory` đặt tên worker là `worker-1`.
- `Future.get()` đợi task trước hoàn tất trước khi submit/quan sát tiếp, nên thứ tự dòng log được xác định.
- Task đầu tiên không cài context cho worker, nên `CONTEXT.get()` trên worker là `null`, in dấu `-`.
- `snapshot()` được gọi ở **main thread**, nơi có `req-42`.
- `withContext` nhớ giá trị cũ trên worker, cài snapshot, chạy task rồi khôi phục trong `finally`.
- Task cuối của worker không thấy `req-42`, xác minh **không rò context giữa các task**.
- Cuối cùng main còn `req-42` cho `event=main.end`; chỉ `finally` ở main mới dọn context của main.

### 7.4. Giới hạn của Handler trong demo

Custom Handler đọc `Thread.currentThread().getName()` và `CONTEXT.get()` ngay trong `publish(LogRecord)`. Với JUL Handler đồng bộ và các lời gọi `LOG.info` trong ví dụ, `publish` chạy ở thread phát event nên hai giá trị đúng.

**Không chuyển nguyên Handler này vào hệ thống async** mà mong nó ghi đúng context. Nếu một handler queue event rồi một worker khác mới format, `ThreadLocal` ở thread output **có thể không còn context của producer**. Trong production, cần **chụp thông tin context ngay khi logging event được tạo**, lưu vào event/structured field hoặc dùng backend/appender đã hỗ trợ deferred processing đúng cách.

Ngoài ra, Handler dùng `record.getMessage()` trực tiếp và demo không có JUL message parameters. Nếu dùng message `"orderId={0}"`, một Formatter hoàn chỉnh nên gọi `formatMessage(record)` để thay tham số. Ví dụ này cố ý đơn giản nhằm chứng minh **context và thread**, không thay thế đầy đủ Formatter/Encoder sản xuất.

## 8. Áp dụng với Spring, Servlet Filter, background job và messaging

### 8.1. HTTP request boundary

Một Filter/Interceptor ở ranh giới request thường:

1. Tạo hoặc kiểm tra `requestId` hợp lệ.
2. Lưu vào MDC trước khi vào controller/service.
3. Chạy logic và log event.
4. Trong `finally`, khôi phục/xóa MDC sau khi response kết thúc.

Phần cần chú ý: nếu xử lý request **tiếp tục bất đồng bộ**, lifecycle của context không phải lúc nào cũng trùng với phạm vi của một lời gọi Filter đồng bộ. Framework có thể chuyển thread hoặc dispatch lại request. Cần sử dụng cơ chế hỗ trợ async dispatch và context propagation của framework để đảm bảo correlation ID không biến mất hoặc bị gán sai.

### 8.2. Scheduled/background jobs

Không phải task nào cũng có HTTP request. Một scheduler có thể tạo `jobId`, `runId` hoặc `operation` cho **mỗi lần chạy**, install context ở đầu job và clear/restore cuối job. Không dùng `requestId` của lần chạy HTTP gần nhất làm context mặc định cho background task.

Nếu một job submit các subtask vào executor, lại cần snapshot/propagate đúng ranh giới task.

### 8.3. Message consumers

Consumer Kafka/RabbitMQ hoặc một hàng đợi khác thường có thread pool và tái sử dụng thread. Khi đọc một message, hãy:

- Lấy ID correlation/trace hợp lệ từ message metadata/headers theo chính sách.
- Install context cho **từng message** hoặc từng xử lý.
- Log các event với `messageId`, `consumerGroup`, `partition`/`offset` nếu được phép.
- Trong `finally` khôi phục/xóa trước khi xử lý message kế tiếp.
- Khi gửi task hoặc message sang bước khác, truyền đúng context theo cơ chế truyền tải, không dựa vào ThreadLocal của JVM nguồn.

### 8.4. CompletableFuture

`CompletableFuture.supplyAsync(...)` hoặc `runAsync(...)` có thể thực thi trên một executor khác thread gọi. Nếu không truyền executor, thường dùng `ForkJoinPool.commonPool()` theo điều kiện runtime. **Không giả định MDC/ThreadLocal của thread gọi được truyền tự động**.

Ví dụ **mảnh code**:

```java
Map<String, String> captured = MDC.getCopyOfContextMap();

CompletableFuture<Void> future =
        CompletableFuture.runAsync(() -> {
            Map<String, String> previous = MDC.getCopyOfContextMap();
            try {
                if (captured == null) MDC.clear();
                else MDC.setContextMap(captured);

                logger.info("event=async.completed");
            } finally {
                if (previous == null) MDC.clear();
                else MDC.setContextMap(previous);
            }
        }, executor);

future.join();
```

Giả sử `logger` và `executor` đã có, cùng import `CompletableFuture`, `Map` và `MDC`. Trong dự án thật có nhiều stage, việc bọc từng lambda có thể khó bảo trì; nên dùng executor decorator/instrumentation hoặc context propagation có hỗ trợ từ framework phù hợp.

### 8.5. Reactive pipelines

Reactive execution như Reactor có thể chuyển thread nhiều lần; MDC thông thường gắn với ThreadLocal nên không phải nguồn context đáng tin nếu không có tích hợp. Framework reactive thường có **context riêng gắn với subscriber/signal** hoặc cơ chế truyền context qua instrumentation.

Không nên ép toàn bộ pipeline về một thread chỉ để giữ MDC. Hãy dùng giải pháp context propagation chính thức của stack reactive/tracing, sau đó xuất context tại thời điểm tạo logging event.

## 9. InheritableThreadLocal, thread pool và các phản ví dụ

| Kỹ thuật | Tình huống phù hợp | Rủi ro/chú ý |
| --- | --- | --- |
| `ThreadLocal` | Dữ liệu gắn với scope của một thread | Không tự chuyển sang worker mới; phải cleanup |
| `InheritableThreadLocal` | Một số mô hình tạo child thread thực sự | Kế thừa lúc tạo thread, không theo từng task pool |
| SLF4J MDC | Gắn key-value diagnostic vào event | Phụ thuộc adapter/backend; phải truyền khi đổi thread |
| `Map.copyOf` snapshot | Bản sao context immutable trước submit | Không chấp nhận null key/value, không đưa secret/objects lớn |
| Truyền `LogContext` làm tham số | Logic nghiệp vụ/trace cần rõ ràng, kiểm thử được | Cần truyền qua các tầng hoặc dùng framework carrier |
| Executor decorator | Nhiều task cần propagate thống nhất | Phải wrap cả `Runnable` và `Callable`/callbacks đúng chỗ |
| Tracing instrumentation | Truyền trace/span qua thread/process/network | Cần cấu hình đúng framework, propagation headers và sampling |
| Đọc ThreadLocal trong async encoder | Không khuyến nghị | Có thể đọc context của thread output, không phải producer |

### 9.1. Context không nên là global mutable map

Cách sai:

```java
static final Map<String, String> CURRENT_REQUEST =
        new HashMap<>();
```

Đây là **mảnh minh họa anti-pattern**. Nếu mọi request cùng sửa một `HashMap` global, các thread có thể tranh chấp và ghi đè giá trị của nhau. Đổi sang `ConcurrentHashMap` **không** làm thông tin tự tách theo request; nó chỉ thay đặc tính concurrency của map chung.

Thay vào đó, dùng **context instance riêng cho mỗi request/task** hoặc một framework context carrier phù hợp, và quy định nơi nó được install/restore.

### 9.2. Không sửa map mutable sau khi submit

Cách dễ gây lỗi:

```java
Map<String, String> captured = mutableContext;
executor.submit(() -> logWith(captured));
captured.put("requestId", "req-other");
```

Đây là **mảnh minh họa lỗi**. `captured` và `mutableContext` có thể cùng trỏ một object; worker đọc giá trị nào phụ thuộc thời điểm, đồng thời có thể xuất hiện data race nếu map không thread-safe.

Dùng snapshot độc lập khi submit, ví dụ `Map.copyOf(mutableContext)` nếu map có dữ liệu hợp lệ và không bị sửa đồng thời trong lúc copy. Một thiết kế tốt hơn là tạo **context bất biến ngay từ đầu**, thay vì dùng shared mutable map.

## 10. Mối quan hệ giữa context của producer và AsyncAppender

Có hai nghĩa khác nhau của “async”:

1. **Business task async:** tác vụ nghiệp vụ chuyển từ thread A sang thread B. Bạn phải propagate context **trước khi task tạo log**.
2. **Logging output async:** event đã được tạo ở thread B, nhưng Appender/encoder chuyển việc ghi ra thread C. Backend phải giữ **snapshot các trường của event** để thread C encode đúng, không đọc lại MDC hiện tại của thread C.

Sơ đồ:

```text
Request thread A
  MDC {requestId=req-42}
        |
        | submit with captured context
        v
Business worker B
  install MDC {requestId=req-42}
  logger.info(...)
        |
        | logging event mang context snapshot
        v
Async logging worker C
  encoder xuất requestId=req-42
        |
        v
stdout/file/collector
```

**Nếu thiếu bước A→B**, event có thể được tạo với context rỗng. Một AsyncAppender làm việc đúng cũng **không tự tạo lại requestId** đã mất trước đó.

**Nếu logging handler tùy chỉnh đọc ThreadLocal ở C**, nó có thể lấy context của C thay vì B. Vì vậy backend chuẩn thường có cơ chế chuẩn bị event trước khi xử lý hoãn, ví dụ Logback `AsyncAppender` chuẩn bị những dữ liệu cần thiết cho deferred processing. Với appender/encoder tự viết, phải kiểm tra điểm chụp dữ liệu và tính bất biến của arguments/structured fields.

### 10.1. Task context và logging event snapshot là hai lớp khác nhau

- **Task context snapshot:** truyền từ caller sang worker **để worker biết request nào đang xử lý**.
- **Logging event snapshot:** đóng gói context tại thời điểm `logger.info` để formatter/appender **xuất chính xác sự kiện đã xảy ra**.

Không xử lý thiếu snapshot ở lớp này bằng cách tắt async một cách máy móc. Hãy tìm đúng ranh giới nơi context bị mất rồi sửa việc propagate/capture.

### 10.2. Thread name của logger không thể thay trace context

Một AsyncAppender có thể có worker output riêng. Nếu formatter lấy tên thread trực tiếp từ `Thread.currentThread()` ở worker output, nó sẽ thấy thread output. Backend đúng nên lấy **thread name đã được logging event ghi nhận lúc tạo event**, nếu muốn thể hiện thread phát log. Tương tự, MDC/trace ID phải được capture từ event, không hỏi ThreadLocal của worker output.

## 11. Context và distributed tracing

**MDC giúp in context**, nhưng **MDC không tự truyền trace qua HTTP, gRPC hoặc message broker**. Nếu request A gọi service B, cần có cơ chế truyền trace context qua **headers/metadata** được hai bên hiểu, thường thông qua instrumentation và các tiêu chuẩn như W3C Trace Context.

Phân biệt:

- `requestId`: ID của một request/operation theo chính sách ứng dụng.
- `traceId`: ID của toàn distributed trace.
- `spanId`: ID của một span, có thể đổi qua từng đoạn công việc.
- **MDC:** vị trí tiện dụng để xuất các ID đó vào logging event.
- **Tracing context carrier:** giữ span đang hoạt động và thông tin propagation qua executor/network.

Một hệ thống tracing tốt có thể tự gắn `traceId`/`spanId` vào log thông qua integration. Nếu tự đặt MDC, cần tránh mâu thuẫn với tracing context thật, không tái sử dụng ID không hợp lệ và không kết luận một chuỗi tự đặt bất kỳ là một trace được collector nhận diện.

### 11.1. Correlation ID từ client cần kiểm tra

Nếu lấy `X-Request-ID` hoặc metadata tương tự từ client:

1. Giới hạn chiều dài và bộ ký tự.
2. Không dùng nguyên giá trị đó để quyết định đường dẫn file, tenant hoặc quyền truy cập.
3. Có thể tạo ID nội bộ mới nếu input không hợp lệ hoặc không đáng tin.
4. Không đưa header chứa token/cookie vào MDC.
5. Ghi rõ quan hệ giữa external request ID và trace ID nội bộ nếu phải dùng đồng thời.

Trong trường hợp cần phân quyền, luôn dựa trên security context đã được xác thực, không tin một MDC key chỉ vì nó có giá trị.

## 12. Chọn field và định dạng log có context

Một schema log nên thống nhất những trường cần thiết:

| Field | Kiểu phổ biến | Mục đích |
| --- | --- | --- |
| `timestamp` | ISO 8601 UTC hoặc epoch milliseconds | Thời điểm sự kiện |
| `level` | String | INFO/WARN/ERROR |
| `logger` | String | Package/class nguồn |
| `thread` | String | Thread phát event |
| `service` | String | Ứng dụng phát event |
| `requestId` | String | Correlation theo request |
| `jobId` | String | Correlation theo background job |
| `traceId` | String | Distributed trace |
| `spanId` | String | Span hiện tại |
| `event` | String | Loại sự kiện ổn định |
| `errorCode` | String | Mã lỗi phân loại |
| `durationMs` | Number | Độ trễ xử lý |

MDC truyền thống có **giá trị String**. Nếu muốn `durationMs` là number thực trong JSON, nên dùng structured key-value API/encoder phù hợp; đừng đặt mọi thứ thành String trong MDC và giả định collector tự chuyển kiểu.

Ví dụ log JSON có thể trông như:

```json
{
  "timestamp": "2026-01-12T10:15:00Z",
  "level": "INFO",
  "logger": "com.example.checkout.OrderService",
  "thread": "worker-1",
  "service": "checkout",
  "requestId": "req-42",
  "traceId": "0123456789abcdef0123456789abcdef",
  "spanId": "0123456789abcdef",
  "event": "order.completed",
  "durationMs": 120
}
```

Đây là **JSON minh họa**, không phải định dạng mặc định của mọi Logback encoder. Cần chọn encoder có khả năng xuất field đúng schema và đúng kiểu. Khi dùng `%X{requestId}` trong text PatternLayout, nó chỉ tạo một chuỗi ký tự, không tự tạo JSON field.

### 12.1. Context tối giản tốt hơn context quá lớn

Không nên copy toàn bộ request body, header map, object User, entity Hibernate hoặc security token vào MDC. Việc nhân bản context qua hàng nghìn task có thể tăng memory, CPU, kích thước event và nguy cơ lộ dữ liệu. Các key như `requestId`, `traceId`, `operation`, `errorCode` thường có giá trị chẩn đoán cao hơn những payload không kiểm soát.

`requestId` và `traceId` có cardinality cao — phù hợp để tra cứu log/trace cụ thể, nhưng không nên tự ý tạo metric label duy nhất cho từng ID hoặc tên logger động theo ID.

## 13. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| Có requestId ở controller nhưng mất ở task async | Context không được propagate sang worker | Capture trước submit, install trên worker, restore trong finally |
| Request B có requestId của A | Thread pool tái sử dụng thread có MDC cũ | Kiểm tra mọi đường chạy/exception đều cleanup |
| Một thread có nhiều requestId lẫn nhau | Context mutable/global hoặc scope ghi đè | Dùng snapshot riêng, khôi phục scope cũ |
| `MDC.get` trống dù thread có tên đúng | Tên thread không phải MDC; adapter/provider khác | Xác nhận MDC được put và backend hỗ trợ |
| Context có trong event nhưng layout không hiện | Pattern thiếu `%X{...}` hoặc JSON encoder không xuất MDC | Kiểm tra encoder/layout và tên field |
| `CompletableFuture` mất context | Stage chạy trên executor khác thread gọi | Bọc từng ranh giới async hoặc dùng propagation của framework |
| `InheritableThreadLocal` cho kết quả lạ | Pool thread được tạo ở thời điểm khác | Không dựa inheritance cho per-task context |
| Dùng MDC ở thread ghi async nhưng ID sai | Đọc ThreadLocal ở consumer thay vì snapshot event | Capture context ở producer khi phát log |
| `MDC.clear()` trong wrapper xóa context ngoài | Không lưu context cũ trước install | Khôi phục map cũ trong finally |
| `putCloseable` không khôi phục giá trị cũ bị ghi đè | Chỉ remove key khi đóng | Chủ động giữ previous value/map nếu scope lồng nhau |
| Trace ID chỉ có trong một service | Không propagate headers/metadata xuyên process | Kiểm tra tracing instrumentation và carrier |
| JSON có `requestId` kiểu sai/field sai | Encoder schema khác kỳ vọng | Inspect JSON thực, mapping field và MDC |
| Log của task bị thiếu do NOP provider | SLF4J runtime không có backend phù hợp | Kiểm tra SLF4J binding/provider và output target |
| Các log test thay đổi thứ tự thất thường | Task chạy song song, không có ordering guarantee | Dùng Future/latch khi test, không giả định thứ tự toàn hệ thống |
| Bộ nhớ tăng ở thread pool lâu sống | Không remove ThreadLocal hoặc giữ object lớn | Cleanup, immutable small context, đánh giá lifecycle |
| Log lộ thông tin cá nhân | Copy quá nhiều headers/body vào context | Allowlist context và quyền đọc log |

### 13.1. Quy trình kiểm tra theo từng ranh giới

1. **Chọn một requestId test duy nhất** và xác định nơi tạo/gắn ID.
2. Ghi một log **trước khi submit** ở caller.
3. Ghi log **ngay đầu worker**, trước khi xử lý nghiệp vụ.
4. Xác minh context đã được capture **ở caller** chứ không phải lần đầu trong worker.
5. Ghi log sau khi install snapshot, trước khi gọi service.
6. Trong `finally`, log hoặc assert context được khôi phục/clear đúng, không rò sang task kế tiếp.
7. Kiểm tra sự khác biệt giữa business executor, listener, callback và logging AsyncAppender.
8. Đọc bản ghi qua encoder/collector thực tế để xem `requestId` xuất từ event đúng chưa.
9. Nếu còn mất context qua network, kiểm tra tracing headers/broker metadata, không chỉ MDC nội bộ.

Một test chỉ có một request tuần tự thường không phát hiện được rò context; nên có test hai request **A/B xen kẽ trên cùng pool** và trường hợp task ném exception.

## 14. Các anti-pattern nên tránh

### 14.1. Chỉ `MDC.put` một lần khi server khởi động

Context theo request không phải cấu hình toàn ứng dụng. Nếu `requestId` được set trong thread main ở startup, các worker của server không tự có request ID chính xác. Context nên được install ở **ranh giới mỗi request/task**, không phải một lần cho toàn process.

### 14.2. Xóa context trước khi task thực thi

Một đoạn code có thể capture **quá muộn**:

```java
MDC.put("requestId", "req-42");
executor.submit(() -> {
    Map<String, String> capturedTooLate =
            MDC.getCopyOfContextMap();
});
MDC.clear();
```

Đây là **đoạn minh họa lỗi**. Worker đang đọc MDC của chính worker, không phải bản sao request ở caller trước khi clear. Cách đúng: capture snapshot **trước `submit`**, rồi truyền snapshot vào lambda để install.

### 14.3. Bỏ `finally` vì nghĩ task luôn thành công

Task có thể ném `RuntimeException`, timeout, bị interrupt hoặc trả kết quả lỗi. Nếu không có `finally`, context có thể nằm lại trên worker và ảnh hưởng task sau. Dọn context nên độc lập với kết quả nghiệp vụ.

### 14.4. Dùng ThreadLocal làm security context toàn cục

Không tin `MDC.get("tenantId")` là bằng chứng user được phép truy cập tenant. MDC là thông tin chẩn đoán, có thể bị code ghi đè và không có cơ chế xác thực. Authorization phải dựa vào context bảo mật đã được xác thực, với lifecycle/propgation riêng.

### 14.5. Lấy tất cả field từ request đưa vào MDC

Ghi toàn bộ header, query string, cookie hoặc request body làm tăng rủi ro rò token/PII, log injection, tăng dung lượng và khó quản trị retention. Giữ context tối thiểu, kiểm tra nguồn và dùng field allowlist.

### 14.6. Dựa vào việc “task nào cũng ở pool-1-thread-1”

Một worker vẫn có thể xử lý nhiều task và một task có thể chuyển sang thread khác. Việc tên thread trùng không chứng minh task cùng request; việc tên thread khác không chứng minh task khác request. Dùng ID correlation được propagate đúng.

## 15. Checklist áp dụng vào dự án

- [ ] Đã thống nhất `requestId`, `traceId`, `spanId`, `jobId` và các key context có nghĩa rõ ràng.
- [ ] Logger name giữ ổn định theo class/package; request ID không nằm trong Logger name.
- [ ] Context được gắn ở ranh giới **mỗi request/task**, không phải lúc startup.
- [ ] ThreadLocal/MDC được dọn/khôi phục trong `finally` ở mọi nhánh thành công/thất bại.
- [ ] Nếu task chạy trên executor, snapshot được capture ở **thread submit**.
- [ ] Wrapper lưu context cũ của worker, install context của task, rồi restore đúng.
- [ ] Không dựa vào `InheritableThreadLocal` để tự giải quyết propagation trong thread pool.
- [ ] Có giải pháp cho `CompletableFuture`, listener và callbacks thực sự chạy trên thread khác.
- [ ] Reactive pipeline sử dụng context propagation chính thức của framework.
- [ ] Event logging bất đồng bộ capture context và thread name của **producer**, không đọc ThreadLocal ở output worker.
- [ ] Đã xác minh SLF4J provider/backend và layout/encoder thực sự xuất các key MDC cần thiết.
- [ ] MDC/Context chỉ chứa key allowlist cần thiết; không giữ token/cookie/body hay object lớn.
- [ ] Trace context truyền qua process/network bằng carrier/instrumentation, không trông chờ MDC.
- [ ] Đã test hai request xen kẽ trên cùng pool, task ném exception và scope lồng nhau.
- [ ] Đã xem log thực tại stdout/file/collector để xác nhận đúng ID, đúng request, không rò context.
- [ ] Đã kiểm tra ảnh hưởng lên CPU/memory, kích thước log và dữ liệu nhạy cảm.

### Tài liệu tham khảo kỹ thuật

- [Java 17 — ThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): ngữ nghĩa lưu giá trị riêng theo thread và `remove()`.
- [Java 17 — InheritableThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/InheritableThreadLocal.html): kế thừa giá trị khi tạo child thread.
- [Java 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): cơ chế quản lý và thực thi task.
- [SLF4J MDC Javadoc](https://www.slf4j.org/api/org/slf4j/MDC.html): `getCopyOfContextMap`, `setContextMap`, `clear`, `remove`, `putCloseable`.
- [Logback Manual — Mapped Diagnostic Context](https://logback.qos.ch/manual/mdc.html): MDC và sự cố context với Executor-managed threads.
- [Logback Manual — Appenders](https://logback.qos.ch/manual/appenders.html): logging output và AsyncAppender.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/): cách truyền trace context giữa các hệ thống.

**Kết luận:** **Context và thread** có quan hệ chặt chẽ nhưng không phải một. `ThreadLocal`/MDC giúp một thread gắn `requestId` và metadata vào log; khi công việc chuyển qua thread pool, `CompletableFuture` hay reactive pipeline, context có thể **mất hoặc bị rò sang task khác** nếu không được truyền và dọn đúng. Quy tắc đáng nhớ là **capture trên thread nguồn → install trong worker → execute → restore trong finally**, còn encoder/AsyncAppender cần dùng context đã được chụp trong logging event. Khi điều tra xuyên service, dùng tracing propagation để kết nối các bước, không dựa vào thread name hoặc MDC đơn lẻ.
