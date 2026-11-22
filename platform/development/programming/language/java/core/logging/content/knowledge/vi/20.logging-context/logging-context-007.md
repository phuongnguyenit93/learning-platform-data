# Context qua async trong Java Logging: MDC, ThreadContext và truyền ngữ cảnh an toàn

## 1. Vấn đề: log mất requestId khi chuyển thread

Một request trong ứng dụng Java có thể đi qua HTTP controller, service, `ExecutorService`, callback `CompletableFuture`, scheduler hoặc message consumer. Khi điều tra lỗi, người vận hành thường muốn các dòng log ở những bước đó chứa chung một `requestId` hoặc `traceId`.

Ví dụ kỳ vọng:

```text
INFO requestId=R-17 thread=http-worker  Request accepted
INFO requestId=R-17 thread=payment-1   Payment started
WARN requestId=R-17 thread=payment-1   Fallback selected
```

Nhưng nếu không truyền context, kết quả có thể là:

```text
INFO requestId=R-17   thread=http-worker Request accepted
INFO requestId=<none> thread=payment-1  Payment started
WARN requestId=<none> thread=payment-1  Fallback selected
```

Tệ hơn, nếu worker từng chạy một request trước đó và không dọn ngữ cảnh, log mới có thể mang **requestId cũ của request khác**. Đây không chỉ là lỗi hiển thị mà còn ảnh hưởng điều tra và tính riêng tư.

Nguyên nhân thường gặp là **MDC/ThreadContext gắn với thread thực thi**, thông qua cơ chế tương tự `ThreadLocal`. Khi ứng dụng chạy code trên một thread khác, dữ liệu của thread nguồn không tự động xuất hiện ở thread đích. Thread pool còn tái sử dụng các worker cho nhiều công việc không liên quan.

Bài học tập trung vào hai điều:

1. **Truyền logging context khi nghiệp vụ chuyển sang thread/callback khác.**
2. **Hiểu việc backend async logging giữ context bên trong log event như thế nào.**

Không được đánh đồng hai cơ chế này. Thay `ConsoleAppender` bằng `AsyncAppender` không thể tự sửa một business worker vốn chưa nhận `requestId`.

## 2. Hai ranh giới async hoàn toàn khác nhau

### 2.1. Business async: request thread gửi task

```text
Thread A: xử lý request
  MDC {requestId=R-17}
        |
        | executor.submit(task)
        v
Thread B: worker của executor
  MDC riêng, có thể rỗng/cũ
        |
        | logger.info("Payment started")
        v
LogEvent được tạo trên B
  với context của B
```

Trong tình huống này, cần **capture context ở A**, **install vào B trước khi gọi logger**, và **restore context cũ của B sau khi hoàn tất task**. Nếu không, event đã thiếu requestId ngay từ lúc được tạo.

### 2.2. Logging async: event được tạo rồi chuyển cho backend

```text
Thread A hoặc B: gọi logger
  MDC {requestId=R-17}
        |
        | logger.info("Payment started")
        v
LogEvent / ILoggingEvent
  gồm metadata và context snapshot
        |
        | async queue / LMAX Disruptor
        v
Thread C: consumer của logging backend
        |
        | Layout -> Appender -> stdout/file
        v
Collector / storage
```

Trong Log4j 2 Async Logger hoặc Logback AsyncAppender chuẩn, backend thường **lưu thông tin context cần thiết trong event** trước khi để thread nền xử lý. Không cần truyền nguyên ThreadLocal của request sang chính logging consumer. Custom layout/formatter phải đọc **context của event**, không đọc ThreadLocal của thread consumer và tưởng đó là dữ liệu request.

| Chuyển giao | Context cần đúng ở đâu? | Cách thực hiện |
| --- | --- | --- |
| HTTP/controller → executor worker | Worker trước lời gọi logger. | Snapshot → install → run → restore. |
| Thread gọi logger → backend async consumer | Bên trong LogEvent được tạo. | MDC/ThreadContext + backend/layout hỗ trợ snapshot. |
| Service A → service B qua HTTP/Kafka | Header/metadata và context local của B. | Inject/extract theo propagation protocol. |
| Reactor/coroutines đổi scheduler | Context của framework ở từng callback. | Tích hợp propagation đúng runtime; không trông chờ ThreadLocal. |

**Quy tắc nhớ:** xem logger được gọi tại **thread nào**. Ngữ cảnh ở thread đó quyết định giá trị event mang theo lúc phát log.

## 3. Các loại context trong hệ Java Logging

### SLF4J MDC

**Mapped Diagnostic Context (MDC)** là tập các cặp key-value như `requestId`, `traceId`, `tenantId`. Ví dụ:

```java
// Minh họa trong ứng dụng đã có SLF4J và provider hỗ trợ MDC.
MDC.put("requestId", "R-17");
try {
    logger.info("Payment started");
} finally {
    MDC.remove("requestId");
}
```

`MDC.put` thao tác trên **context của thread hiện tại** theo MDC adapter. Với backend như Logback, pattern `%X{requestId}` có thể xuất giá trị đó. Không mặc định `MDC.put` trên thread HTTP sẽ thấy trong `ExecutorService` worker.

### Log4j 2 ThreadContext

Log4j 2 dùng `org.apache.logging.log4j.ThreadContext`. Nó có:

- **Context Map (MDC):** cặp tên và giá trị, ví dụ `requestId=R-17`.
- **Context Stack (NDC):** stack ngữ cảnh lồng nhau, ví dụ scope `checkout` → `payment`.

```java
// Minh họa trong một method dùng Log4j 2.
ThreadContext.put("requestId", "R-17");
ThreadContext.push("payment");
try {
    logger.info("Calling gateway");
} finally {
    ThreadContext.pop();
    ThreadContext.remove("requestId");
}
```

Nếu ứng dụng có NDC stack, chỉ copy MDC map sẽ không truyền toàn bộ context. Cần quyết định rõ cả hai cấu trúc được propagation hay không.

### Distributed tracing context

Tracer như OpenTelemetry có context riêng cho span hiện tại, trace state, sampling và baggage. MDC có thể chứa **một bản chiếu của traceId/spanId để đưa vào log**, nhưng hai cơ chế không tự động là một.

- Có `MDC.put("traceId", ...)` không đồng nghĩa đã tạo distributed span.
- Có HTTP `traceparent` không có nghĩa JSON logger sẽ tự hiển thị traceId.
- Copy MDC không đảm bảo tracing context đã đi theo `CompletableFuture`.
- Propagation từ network cần inject/extract có kiểm soát, không gửi toàn bộ MDC.

Nếu framework/tracing agent đã có cơ chế propagation chính thức, ưu tiên sử dụng và kiểm tra tương thích trước khi tự viết thêm wrapper.

## 4. Tại sao ThreadLocal hoặc InheritableThreadLocal không đủ?

`ThreadLocal<T>` cung cấp mỗi thread một bản state riêng. Khi task từ thread A được chạy trên thread B, gọi `ThreadLocal.get()` ở B sẽ lấy state của B. Executor không mặc nhiên sao chép tất cả ThreadLocal của caller.

`InheritableThreadLocal` có thể truyền giá trị khi **tạo một thread con**, nhưng thread pool thường tái sử dụng worker được tạo trước đó. Một thread có thể chạy R-1, R-2, R-3 trong nhiều phút. Giá trị được kế thừa lúc tạo thread **không phải propagation cho từng task**.

Ví dụ lỗi:

```java
// Minh họa: MDC trên thread submit không tự truyền.
MDC.put("requestId", "R-1");
executor.submit(() -> logger.info("Task started"));
MDC.clear();
```

Ngay khi callback chạy sau, worker có thể không có R-1. Cũng có trường hợp worker còn R-0 do task trước quên clear. Bởi vậy, **không đoán dựa trên thread name hay thời điểm tạo worker**.

## 5. Quy trình chuẩn: capture → install → run → restore

Một wrapper an toàn tuân theo bốn giai đoạn:

```text
Caller A                                Worker B
───────────────────────────────────────────────────────
capture snapshot S
  ở thời điểm submit
         |
submit wrapped task ---------> snapshot state P vốn có
                               install bản sao S
                               try {
                                 task.run();
                               } finally {
                                 restore P;
                               }
Caller có thể sửa/clear
context sau submit
nhưng không làm đổi S
```

**Capture ở nơi gửi task**, không capture trong lambda đã chạy trên worker. **Copy map**, không chia sẻ đối tượng mutable với thread khác. **Restore trong finally**, không chỉ trên success path.

Vì sao cần restore thay vì luôn clear?

- Worker có thể có context hợp lệ của scope cha/nested task.
- Clear có thể phá context có trước task mới.
- Restore giúp wrapper có tính chất scope rõ ràng ngay cả khi callback sửa MDC.
- Nếu task throw, finally vẫn phục hồi khi stack unwind bình thường.
- Với một worker chạy nhiều request, restore tránh lộ ID và nhiễm context.

Khi áp dụng chính sách worker luôn rỗng tại job boundary, clear sau mỗi job cũng có thể là một hợp đồng hợp lệ. Nhưng **save/restore** là mẫu tổng quát an toàn hơn cho wrapper có thể lồng nhau.

Không truyền request object, database session, auth token, cookie hoặc password qua logging context để thuận tiện debug. Chỉ truyền các field đã được cho phép.

## 6. Ví dụ Java 17 có thể chạy: mất context, truyền context và kiểm tra leak

Ví dụ dưới đây chỉ dùng **JDK 17 và java.util.logging (JUL)**, không cần thư viện ngoài. JUL không cung cấp MDC chuẩn giống SLF4J/Log4j 2, vì vậy chương trình tự dùng `ThreadLocal<Map<String,String>>` như một context demo. JUL Logger và StreamHandler thật được dùng để phát các dòng log.

**Quan trọng:** formatter demo là **đồng bộ**, chạy trên thread gọi logger, nên có thể đọc ThreadLocal để minh họa. Trong Log4j/Logback async, custom layout phải lấy context **đã chụp trong event**; không nên đọc ThreadLocal request từ logging consumer.

Chương trình thực hiện:

1. Đặt R-1 ở main rồi gửi task không wrapper → không có requestId.
2. Gửi task có wrapper → worker nhận R-1.
3. Task cố ý đổi requestId thành INNER; wrapper phải khôi phục state của worker.
4. Gửi task không wrapper tiếp theo → không còn INNER/R-1.
5. Đặt R-2, gửi task có wrapper → nhận R-2.
6. Task cuối ở worker không wrapper → không còn R-2.
7. Main vẫn có R-2 trước khi dọn scope.

### 6.1. File AsyncContextDemo.java

```java
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class AsyncContextDemo {

    private static final ThreadLocal<Map<String, String>> CONTEXT =
            new ThreadLocal<>();
    private static final Logger LOG =
            Logger.getLogger("demo.async.context");

    private AsyncContextDemo() {
    }

    public static void main(String[] args) throws Exception {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        for (Handler previous : LOG.getHandlers()) {
            LOG.removeHandler(previous);
        }

        Handler console = new StreamHandler(System.out,
                new ContextFormatter()) {
            @Override
            public synchronized void publish(LogRecord record) {
                super.publish(record);
                flush();
            }
        };
        console.setLevel(Level.INFO);
        LOG.addHandler(console);

        ExecutorService pool = Executors.newSingleThreadExecutor(
                runnable -> new Thread(runnable, "context-worker"));

        try {
            install(Map.of("requestId", "R-1"));

            // Không truyền: worker không tự có R-1.
            pool.submit(() -> log("UNWRAPPED")).get();

            // Wrapper capture R-1 ở main thread.
            pool.submit(withContext(() -> {
                log("R1_WRAPPED");
                install(Map.of("requestId", "INNER"));
                log("R1_CHANGED_INSIDE");
            })).get();

            pool.submit(() -> log("AFTER_R1")).get();

            install(Map.of("requestId", "R-2"));
            pool.submit(withContext(() -> log("R2_WRAPPED"))).get();

            pool.submit(() -> log("AFTER_R2")).get();
            log("MAIN");
        } finally {
            CONTEXT.remove();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
            LOG.removeHandler(console);
            // Không close StreamHandler: có thể đóng System.out.
            console.flush();
        }
    }

    private static void log(String phase) {
        LOG.info(phase);
    }

    private static Runnable withContext(Runnable task) {
        Map<String, String> captured = snapshot();

        return () -> {
            Map<String, String> previous = snapshot();
            install(captured);
            try {
                task.run();
            } finally {
                install(previous);
            }
        };
    }

    private static Map<String, String> snapshot() {
        Map<String, String> current = CONTEXT.get();
        return current == null ? null : new HashMap<>(current);
    }

    private static void install(Map<String, String> values) {
        if (values == null || values.isEmpty()) {
            CONTEXT.remove();
        } else {
            CONTEXT.set(new HashMap<>(values));
        }
    }

    private static final class ContextFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            Map<String, String> current = CONTEXT.get();
            String requestId = current == null
                    ? "<none>"
                    : current.getOrDefault("requestId", "<none>");

            return record.getMessage()
                    + "|thread=" + Thread.currentThread().getName()
                    + "|requestId=" + requestId + "\n";
        }
    }
}
```

### 6.2. Biên dịch, chạy và stdout

Tạo file có đúng tên `AsyncContextDemo.java` và chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 AsyncContextDemo.java
java AsyncContextDemo
```

**Stdout chính xác** trong điều kiện ví dụ:

```text
UNWRAPPED|thread=context-worker|requestId=<none>
R1_WRAPPED|thread=context-worker|requestId=R-1
R1_CHANGED_INSIDE|thread=context-worker|requestId=INNER
AFTER_R1|thread=context-worker|requestId=<none>
R2_WRAPPED|thread=context-worker|requestId=R-2
AFTER_R2|thread=context-worker|requestId=<none>
MAIN|thread=main|requestId=R-2
```

Tại sao kết quả xác định?

- `Executors.newSingleThreadExecutor` chỉ dùng một worker, có tên do ThreadFactory đặt là `context-worker`.
- `Future.get()` chờ task kết thúc rồi mới đi tiếp; không dùng `Thread.sleep` để ép thứ tự.
- `withContext` được gọi ở main lúc gửi việc nên snapshot đúng requestId.
- Worker sao lưu context của mình, cài snapshot, chạy task và restore trong `finally`.
- Dù task đổi ID thành INNER, `AFTER_R1` vẫn là `<none>`.
- `MAIN` vẫn mang R-2 vì worker dùng bản sao Map, không làm đổi Map trong caller.
- Formatter chỉ đọc ThreadLocal ở thread phát log vì handler đồng bộ; đây không phải mẫu để dùng nguyên xi trong logging consumer async.
- Handler chủ động flush để output quan sát được; điều đó **không chứng minh log được collector remote nhận**.

Giới hạn: demo không mang context qua network, không xử lý OpenTelemetry, reactive scheduler, JSON encoder, transaction hoặc audit durability. Đó là mô hình học tập cho một ranh giới executor.

## 7. SLF4J + Logback: wrapper MDC cho Runnable

Trong dự án có `slf4j-api` và backend/provider hỗ trợ MDC, những API quan trọng gồm:

- `MDC.put(k,v)` và `MDC.get(k)` cho thread hiện tại.
- `MDC.getCopyOfContextMap()` trả một **bản sao Map**, có thể là null.
- `MDC.setContextMap(map)` thay map hiện tại (clear rồi copy).
- `MDC.clear()` xóa context trên thread hiện tại.

Một wrapper minh họa, đặt trong một Java class có import tương ứng:

```java
import java.util.Map;
import org.slf4j.MDC;

static Runnable withMdc(Runnable task) {
    // Gọi trên thread SUBMIT trước khi executor chạy.
    Map<String, String> captured = MDC.getCopyOfContextMap();

    return () -> {
        Map<String, String> previous = MDC.getCopyOfContextMap();
        try {
            installMdc(captured);
            task.run();
        } finally {
            installMdc(previous);
        }
    };
}

static void installMdc(Map<String, String> context) {
    MDC.clear();
    if (context != null && !context.isEmpty()) {
        MDC.setContextMap(context);
    }
}
```

Sử dụng bên trong request handling code đã có `executor` và `logger`:

```java
MDC.put("requestId", "R-17");
try {
    executor.submit(withMdc(
            () -> logger.info("Background payment processing")));
} finally {
    MDC.remove("requestId");
}
```

**Lưu ý:** đoạn ở trên là snippet phụ thuộc SLF4J, chưa phải project độc lập như mục 6. Cần xác nhận backend runtime thực sự hỗ trợ MDC. Một số MDC adapters có thể không lưu context hoặc không đưa vào log nếu layout không được cấu hình.

### Vì sao không chỉ gọi MDC.clear trong worker?

Trong wrapper tổng quát, worker có thể có map P trước khi chạy task. `clear()` ở cuối chỉ làm nó rỗng, phá P. Lưu `previous` rồi install lại giúp khôi phục trạng thái một cách rõ ràng.

### SLF4J 1.7 và 2.x

Một số phiên bản SLF4J 2.0 chấp nhận `null` trong `MDC.setContextMap(null)`, nhưng để giữ tương thích và tránh phụ thuộc chi tiết adapter, ví dụ **gọi MDC.clear() khi snapshot null**. Không đặt null key, tránh null value nếu provider không hỗ trợ.

### Callable có kết quả

Nếu task có return value/checked exception:

```java
import java.util.Map;
import java.util.concurrent.Callable;
import org.slf4j.MDC;

static <T> Callable<T> withMdc(Callable<T> task) {
    Map<String, String> captured = MDC.getCopyOfContextMap();

    return () -> {
        Map<String, String> previous = MDC.getCopyOfContextMap();
        try {
            installMdc(captured);
            return task.call();
        } finally {
            installMdc(previous);
        }
    };
}
```

Đoạn này dùng lại `installMdc(...)` ở trên. Dù `task.call()` throw, `finally` vẫn restore context.

**Sai thời điểm capture:**

```java
// SAI: withMdc được chạy ở worker, snapshot sai thread.
executor.submit(() -> withMdc(task).run());

// ĐÚNG: wrapper được tạo ở caller.
executor.submit(withMdc(task));
```

### MDC.putCloseable và nested scopes

`MDC.putCloseable(k,v)` hữu ích khi chỉ muốn gắn và sau đó loại bỏ một key. Nhưng đóng một `MDCCloseable` không đồng nghĩa đã snapshot và restore toàn bộ MDC trước đó; với nhiều scope lồng nhau, cần hiểu semantics của adapter. Wrapper full-map snapshot/restore phù hợp hơn khi phải cô lập context per-task.

## 8. Log4j 2: ThreadContext qua executor

Log4j 2 cung cấp cả map và stack:

```java
// Mã minh họa ở thread submit, có executor và LOGGER.
Map<String, String> map = ThreadContext.getImmutableContext();
List<String> stack = ThreadContext.getImmutableStack().asList();

executor.submit(() -> {
    try (CloseableThreadContext.Instance ignored =
                 CloseableThreadContext.putAll(map)
                         .pushAll(stack)) {
        LOGGER.info("Background job started");
    }
});
```

Import khi dùng đoạn trên:

```java
import java.util.List;
import java.util.Map;
import org.apache.logging.log4j.CloseableThreadContext;
import org.apache.logging.log4j.ThreadContext;
```

Các bước:

1. Capture map và stack ở thread gửi việc.
2. Trong worker, cài các giá trị qua `putAll`/`pushAll`.
3. `try-with-resources` kết thúc scope dù callback lỗi.
4. Nếu có NDC stack, không được bỏ qua nó mà vẫn tuyên bố truyền “toàn bộ context”.

**Khi worker có context cũ hoặc task có thể thay đổi tùy ý các key:** với yêu cầu cách ly mạnh, cần wrapper **snapshot toàn bộ state cũ, thay state bằng snapshot của task và restore state cũ**. Chỉ thêm vài key bằng một scope không đảm bảo xóa hết các key stale không thuộc scope.

Ví dụ map-only restore toàn bộ trong Log4j 2:

```java
static Runnable withLog4jMdc(Runnable task) {
    Map<String, String> captured =
            new java.util.HashMap<>(ThreadContext.getImmutableContext());

    return () -> {
        Map<String, String> previous =
                new java.util.HashMap<>(ThreadContext.getImmutableContext());
        try {
            ThreadContext.clearMap();
            ThreadContext.putAll(captured);
            task.run();
        } finally {
            ThreadContext.clearMap();
            ThreadContext.putAll(previous);
        }
    };
}
```

Đoạn này **chỉ xử lý map**, không xử lý NDC stack hoặc context tracing riêng. Khi hệ thống dùng NDC, cần thêm logic tương ứng hoặc dùng cơ chế scope của Log4j/framework. Không sao chép ngẫu nhiên một ThreadContext map giữa classloader/backend khác nhau.

### Hiển thị MDC trong layout

Đoạn `PatternLayout` của Log4j 2:

```xml
<PatternLayout
    pattern="%d{ISO8601} %-5p requestId=%X{requestId} [%t] %c - %m%n"/>
```

Với `JsonTemplateLayout`, một đoạn event template JSON có thể là:

```json
{
  "requestId": {
    "$resolver": "mdc",
    "key": "requestId"
  },
  "message": {
    "$resolver": "message",
    "stringified": true
  }
}
```

Đoạn này không phải toàn bộ cấu hình Logger/Appender. Để dùng JsonTemplateLayout cần module `log4j-layout-template-json` tương thích và appender được gắn đúng template. Nếu muốn query theo requestId, hãy để encoder xuất **field riêng**, không chỉ nối ID trong message.

## 9. Context trong Async Logger và AsyncAppender

**Async Logger không giống AsyncAppender**, nhưng đều có thể đẩy xử lý xuất log sang thread nền.

Trong Log4j 2 Async Logger, event được tạo với context liên quan ở thread gọi logger rồi được chuyển qua pipeline LMAX Disruptor. Logback AsyncAppender chuẩn bị dữ liệu xử lý trì hoãn, bao gồm MDC, trước khi worker appender tiêu thụ event.

```text
Business worker có MDC {requestId=R-17}
             |
             | logger.info(...)
             v
LogEvent/ILoggingEvent được tạo
  message, level, timestamp, context data
             |
          enqueue
             |
             v
Logger async consumer
   đọc event context đã chụp
             |
             v
Layout / Appender / stdout / file
```

**Hai kết luận quan trọng:**

- Nếu business worker thiếu requestId ở lúc phát log, event sẽ thiếu field từ đầu; đổi sang AsyncAppender không khắc phục.
- Nếu event được tạo với MDC đúng, backend async chuẩn thường có thể format giá trị context từ event dù consumer thread không mang MDC của request.

### Lỗi custom formatter

Một formatter custom đọc trực tiếp `MDC.get("requestId")` hoặc `ThreadContext.get("requestId")` **trên logging consumer thread** có thể đọc sai context. Phải sử dụng API đọc dữ liệu trên event như `ILoggingEvent`/`LogEvent` của backend, không truy cập request ThreadLocal vào lúc xuất.

### Mutable message

Thông điệp chứa `Map` hoặc object mutable có thể thay đổi giữa lúc phát log và lúc backend format, tùy loại Message và chính sách. Để tránh kết quả không phản ánh event time, hãy ghi giá trị bất biến đã chụp. Với Log4j 2 `MapMessage` hoặc custom Message, không mutate object sau lời gọi logger nếu dùng async.

### Queue full và shutdown

Propagation đúng không bảo đảm log không bị mất. Nếu queue đầy, appender chậm hoặc JVM bị kill trước khi drain, một event vẫn có thể bị block, drop theo policy hoặc chưa đến sink. Giám sát queue/backpressure và có quy trình shutdown; không dùng một log async có nguy cơ mất làm audit transaction duy nhất.

## 10. CompletableFuture và callback chain

`CompletableFuture.runAsync`, `supplyAsync` hoặc các stage `thenApplyAsync` có thể chạy trên executor hoặc common pool, tùy API và cấu hình. Không giả định chúng kế thừa MDC của code đăng ký callback.

Ví dụ chưa đủ:

```java
MDC.put("requestId", "R-17");
try {
    CompletableFuture.runAsync(
        () -> logger.info("Payment processed"), executor);
} finally {
    MDC.clear();
}
```

Mẫu truyền `Runnable`:

```java
MDC.put("requestId", "R-17");
try {
    CompletableFuture.runAsync(
        withMdc(() -> logger.info("Payment processed")),
        executor);
} finally {
    MDC.clear();
}
```

Đoạn này cần các import, biến và helper ở mục trước; đây là **snippet trong ứng dụng có SLF4J**, không phải chương trình JDK độc lập. Với `Supplier<T>`/`Function<T,R>` phải có wrapper đúng kiểu, cũng capture context tại lúc đăng ký hoặc gửi việc.

### Bẫy thời điểm callback thực sự chạy

```java
future.thenApply(value -> transform(value))
      .thenApplyAsync(value -> save(value), executor);
```

Một stage có thể thực thi trên completing thread, thread caller hoặc executor. Nếu wrapper `Executor.execute()` chỉ capture context vào **lúc stage được thực sự schedule**, caller lúc đó có thể là thread hoàn thành future, không phải thread đăng ký. Với chain phức tạp, cần wrapper **callback/function tại lúc đăng ký**, hoặc integration propagation chính thức của framework.

`exceptionally`, `handle` và `whenComplete` cũng có thể chạy trên thread khác. Bảo vệ cả success và failure paths, không chỉ một callback xử lý kết quả.

### Cancellation và exception

`try/finally` giúp restore khi callback thoát bình thường hoặc bằng exception. Khi Future bị cancel/interrupt, task có thể vẫn chạy một lúc hoặc bị ngắt; restore khi stack unwind. Nếu JVM bị kill cưỡng bức hoặc task bị treo vô hạn, không thể tuyên bố dọn dẹp đã hoàn tất.

## 11. Scheduler và background jobs dài hạn

Một scheduled task thường không còn thuộc request gốc. Nếu capture `requestId=R-17` khi đăng ký một job chạy mỗi phút, job có thể mang R-17 vô thời hạn:

```java
// Minh họa thiết kế có nguy cơ sai ngữ nghĩa.
scheduler.scheduleAtFixedRate(
    withMdc(() -> performPeriodicJob()),
    0, 60, TimeUnit.SECONDS);
```

Cách phù hợp hơn cho background job:

- Tạo `jobId` hoặc `runId` mới mỗi lần job chạy.
- Nếu job được tạo bởi request, có thể lưu `parentRequestId` để liên kết nhân quả theo policy.
- Không ngầm coi HTTP request đã kết thúc vẫn là context active của job.
- Tạo scope logging mới cho mỗi execution và clear/restore khi hoàn tất.
- Nếu job được retry hoặc chuyển qua queue, các ID phải được truyền theo metadata đã định nghĩa.

Ví dụ:

```text
HTTP request R-17
    |
    | enqueue export job J-42
    v
Background execution
  jobId=J-42
  parentRequestId=R-17 (nếu được phép)
  event=EXPORT_STARTED
```

Đừng dùng thread name làm ID duy nhất của một job vì worker có thể xử lý nhiều job.

## 12. Spring, Reactor và các runtime thay đổi thread

### Spring TaskDecorator

Trong Spring, `ThreadPoolTaskExecutor` có cơ chế `TaskDecorator` ở các phiên bản hỗ trợ. Một decorator có thể capture/install/restore MDC tập trung khi gửi task.

Nhưng cần xác minh **executor nào thực sự chạy công việc**: decorator của pool A không tự áp dụng cho pool B, `ForkJoinPool.commonPool()` hoặc một executor do thư viện tự tạo. Nếu framework/tracing đã có propagation tích hợp, tránh double wrapping gây ghi đè context.

### Reactor/WebFlux

Reactive pipeline có thể đổi scheduler ở nhiều điểm. Với Reactor, `Context` của framework được thiết kế để mang dữ liệu qua pipeline; `ThreadLocal` không mặc nhiên đi theo mỗi operator. Nếu cần hiển thị MDC, dùng bridge/context propagation tương thích với phiên bản Reactor/Spring và quản lý scope trong callback.

Đừng gọi `MDC.put` một lần ở controller rồi cho rằng tất cả `Mono/Flux`, callback và worker thread đều thấy giá trị. Phải test với các ranh giới `publishOn`, `subscribeOn`, timeout và error stages.

### Coroutines và virtual threads

Coroutine có thể suspend/resume trên thread khác; context phải theo coroutine abstraction. Virtual threads hoặc structured concurrency thay đổi mô hình tạo/sử dụng thread nhưng **không thay hợp đồng của từng thư viện logging và framework**. Không biến InheritableThreadLocal thành câu trả lời mặc định cho mọi runtime.

## 13. Qua ranh giới HTTP, Kafka, RabbitMQ

Nếu tác vụ async được thực hiện ở **JVM hoặc service khác**, không thể chỉ copy Java ThreadLocal.

```text
Service A:
 local tracing context + MDC
       |
       | inject trace metadata vào
       | HTTP headers hoặc message properties
       v
Network / message broker
       |
       v
Service B:
 extract + validate metadata
       |
 create local tracing/MDC scope
       |
 logger.info(...)
       |
 clear/restore local scope
```

Distributed tracing thường dùng chuẩn **W3C Trace Context** qua `traceparent`/`tracestate`. Baggage có thể mang metadata bổ sung theo hợp đồng riêng, nhưng không nên đưa token, cookie, password hoặc dữ liệu cá nhân tùy ý vào các headers được truyền xa.

Một số lưu ý:

- Validate trace identifiers nhận từ bên ngoài theo trust boundary.
- Không tạo traceId giả khác hệ thống tracing đang hoạt động.
- Phân biệt requestId ứng dụng với traceId/spanId của tracer.
- Với message retry hoặc DLQ, quy định copy/khởi tạo lại tracing context và causal link.
- Không truyền toàn bộ MDC map qua HTTP headers mà không có allowlist.
- Việc context được truyền qua giao thức **không tự khiến logger xuất field**; cần gắn vào local event và encoder.

## 14. Hiển thị context trong JSON logging

Ví dụ JSON Lines:

```json
{"timestamp":"2026-11-09T10:15:30Z","level":"INFO","requestId":"R-17","traceId":"4bf92f...","event":"PAYMENT_STARTED","message":"Payment started"}
```

Đây là schema minh họa. Muốn có kết quả tương tự, cần **cả ba điều kiện**:

1. Code/tracing đã đặt requestId/traceId vào logging context **đúng thread** lúc tạo event.
2. Backend đã giữ các giá trị đó trong event, kể cả khi ghi async.
3. Encoder JSON đã được cấu hình để xuất field đúng tên và collector giữ được mapping.

Nếu thiếu bước 1, format không thể tạo ID từ hư không. Nếu thiếu bước 3, MDC vẫn có giá trị nhưng JSON không xuất field. Nếu chỉ dùng `PatternLayout` dạng text, đừng gọi đó là structured JSON.

Giữ `requestId` là string field, `event` là mã ổn định, `message` là mô tả dễ đọc. Không chỉ nhúng ID vào message tự do rồi dùng regex tách lại.

## 15. Quy tắc bảo mật và tránh context leak

Logging context có thể được lặp trong **mọi log event của request**, nên một field nhạy cảm ở MDC có thể phát tán sang nhiều appender/sink.

Nên dùng một allowlist nhỏ:

| Field | Mục đích | Lưu ý |
| --- | --- | --- |
| `requestId` | Liên kết log thuộc request. | Không phải access token. |
| `traceId` | Liên kết phân tán. | Phải khớp tracing system. |
| `spanId` | Xác định span hiện tại. | Có thể thay đổi theo operation. |
| `jobId` | Liên kết task background. | Tạo mới theo job/run. |
| `tenantId` | Phân loại tenant khi được cho phép. | Có chính sách đa khách hàng/PII. |
| `operation` | Nghiệp vụ hiện tại. | Tên hữu hạn, không lấy raw input làm key. |

Không đưa password, OTP, access token, refresh token, session cookie, private key, raw request body hoặc toàn bộ object domain vào MDC. Không dựa vào `toString()` của entity để che bí mật.

**Stale context là lỗi privacy:** worker của request B mang ID của request A làm log bị gán sai. Điều đó có thể khiến báo cáo vận hành hoặc truy vết sự cố nhầm giữa khách hàng. Cần snapshot, restore trong finally và test reuse worker.

Giới hạn số lượng key, độ dài giá trị và lifetime. Không dùng requestId/traceId làm label metric có cardinality lớn; chúng phù hợp làm field log/tracing hơn.

## 16. Khi message hoặc dữ liệu context mutable

Ngay cả khi MDC đã được propagate đúng, dữ liệu log khác có thể bị mutate giữa lúc gọi logger và lúc backend async format.

```java
// Minh họa không an toàn khi backend định dạng muộn
// một object mutable do code vẫn tiếp tục sửa.
Map<String, Object> state = new HashMap<>();
state.put("status", "PENDING");
logger.info("State: {}", state);
state.put("status", "DONE");
```

Tùy loại Message và backend, format có thể snapshot sớm hoặc đọc object sau. Để bảo đảm event phản ánh trạng thái tại lúc phát:

```java
String statusAtEvent = String.valueOf(state.get("status"));
logger.info("State: {}", statusAtEvent);
```

Tương tự, snapshot MDC phải là bản sao theo task; caller đổi requestId sau submit không được làm context của task đã gửi thay đổi. Không coi mọi object trong log event là đã deep-copy chỉ vì context map được capture.

## 17. Test context qua async đúng cách

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Caller có R-1, task không wrap | Worker không được giả định kế thừa MDC. |
| Caller có R-1, task được wrap | Event worker mang R-1. |
| Caller thay context sau submit | Task giữ snapshot đúng thời điểm gửi. |
| Worker đã có context P | Wrapper tạm cài S rồi restore P. |
| Task sửa MDC thành INNER | Task sau không lộ INNER. |
| Task throw exception | Finally restore; Future báo lỗi đúng. |
| Task bị interrupt/cancel | Khi task thoát, context được dọn. |
| R-1 rồi R-2 trên cùng worker | Không có cross-request contamination. |
| CompletableFuture stage chạy muộn | Không capture nhầm context của completing thread. |
| Scheduled job định kỳ | Có jobId per-run, không mang requestId cũ mãi. |
| Logback AsyncAppender | Context của event giữ đúng khi consumer xuất. |
| Log4j 2 Async Logger | Backend đọc event context, không đọc consumer MDC. |
| JSON layout | requestId/traceId là field riêng đúng schema. |
| Distributed service | Trace metadata được inject/extract đúng. |
| Data privacy | Không propagate token/cookie/PII chưa duyệt. |

Không dùng `Thread.sleep(100)` như bằng chứng propagation đã thành công. Với task, dùng `Future.get()`/latch để đợi kết quả. Với logging backend async, chờ/drain theo API framework hoặc kiểm tra event tại sink test có xác nhận.

### Smoke test ở production-like environment

1. Phát request có `requestId=TEST-R-1`.
2. Ghi một event ở HTTP thread và một event ở worker.
3. Parse output JSON, đối chiếu requestId.
4. Phát request `TEST-R-2` liên tiếp trên cùng worker pool.
5. Kiểm tra không có ID của R-1 trong event của R-2.
6. Thử event trên nhánh exception/retry.
7. Kiểm tra traceId trùng trace thực tế nếu có tracing.
8. Xác minh collector/index không drop hay map sai field.
9. Kiểm tra không có token/PII xuất ra log.

## 18. Chẩn đoán khi log thiếu requestId

```text
Log thiếu requestId?
        |
        v
Caller có đặt context đúng không?
        |
        v
logger.info gọi ở thread nào?
        |
        +--- HTTP/caller:
        |      scope có bị clear sớm?
        |
        +--- Executor worker:
               snapshot trước submit?
               install trước logger?
               restore ở finally?
        |
        v
LogEvent có context tại lúc tạo không?
        |
        v
AsyncAppender/AsyncLogger đã nhận event?
        |
        v
Layout/JSON encoder có đọc context event?
        |
        v
Collector đã parse/index đúng?
```

Các sai lầm hay gặp:

1. Chỉ đặt MDC trên request thread, nhưng gọi logger trong executor worker.
2. Dùng InheritableThreadLocal như một giải pháp tự động cho thread pool.
3. Capture MDC trong worker thay vì ở thread gửi việc.
4. Quên finally, khiến requestId cũ rò sang task sau.
5. Chỉ clear sau task, làm mất context của scope cha.
6. Chia sẻ mutable Map và thay đổi sau submit.
7. Coi AsyncAppender tự copy context giữa **hai business threads**.
8. Custom formatter đọc ThreadLocal của logging consumer thay vì LogEvent.
9. Đặt MDC đúng nhưng quên cấu hình `%X{requestId}`/JSON resolver.
10. Thấy mất event do level/filter/queue/collector rồi kết luận MDC mất.
11. Truyền tất cả headers vào MDC, làm rò token.
12. Coi một traceId string trong MDC là toàn bộ distributed tracing.
13. Để job định kỳ dùng mã request của thời điểm đăng ký.
14. Dùng context-aware Executor wrapper ở thời điểm stage được thực thi muộn, capture nhầm completing thread.
15. Không test kết hợp exception, cancellation, nested tasks và thread reuse.

## 19. Hiệu năng và triển khai thực tế

Copy map, cài ThreadLocal và tạo snapshot có chi phí CPU/allocation. Không tối ưu bằng cách bỏ restore hoặc truyền shared mutable map; lỗi correlation có thể tốn kém hơn vài phép copy.

- Tập trung propagation ở **ranh giới executor/task framework** khi có cách chuẩn.
- Chỉ giữ vài key hữu ích, tránh copy toàn bộ request.
- Với tracing đã tích hợp, dùng công cụ propagation chính thức để tránh hai nguồn sự thật.
- Với reactive, ưu tiên context abstraction của runtime.
- Với job không thuộc request, tạo job context mới.
- Đo p50/p95/p99 latency, GC, số task, số event thiếu context và hiệu năng sink.
- Nếu logging backend async queue đầy, xử lý queue/backpressure riêng; sửa MDC không làm file/network nhanh hơn.
- Khi runtime hoặc library được nâng cấp, chạy lại tests vì cách context propagation và adapter có thể thay đổi.

## 20. Checklist triển khai

- [ ] Biết logger thực sự được gọi ở thread nào.
- [ ] Phân biệt business async handoff với async logging consumer.
- [ ] Dùng đúng API MDC của SLF4J/Logback hoặc ThreadContext của Log4j 2.
- [ ] Capture snapshot ở caller vào thời điểm submit/đăng ký callback thích hợp.
- [ ] Install vào worker trước khi logger được gọi.
- [ ] Restore state worker trong finally, kể cả khi exception.
- [ ] Không dùng InheritableThreadLocal thay propagation per-task.
- [ ] Nếu dùng NDC, có quy tắc propagation và khôi phục stack.
- [ ] CompletableFuture/Scheduler/Reactor dùng tích hợp đúng runtime.
- [ ] Background job không kế thừa mã request cũ vô thời hạn.
- [ ] Distributed trace metadata được inject/extract có kiểm soát.
- [ ] Layout/encoder xuất MDC từ event, không đọc ThreadLocal consumer.
- [ ] RequestId/traceId nằm ở field riêng với schema nhất quán.
- [ ] Không đưa token, password, cookie, dữ liệu riêng tư không cần thiết vào context.
- [ ] Không mutate object log sau khi phát sự kiện async.
- [ ] Test nhiều requests trên một worker pool và các nhánh lỗi.
- [ ] Test end-to-end tới sink/collector, không chỉ kiểm tra ThreadLocal.
- [ ] Có observability về event thiếu correlation ID, queue drops và ingest lag.

## Tài liệu tham khảo chính thức

- [SLF4J MDC API — getCopyOfContextMap, setContextMap và clear](https://www.slf4j.org/api/org/slf4j/MDC.html)
- [Logback — MDC và worker thread pools](https://logback.qos.ch/manual/mdc.html)
- [Log4j 2 — Thread Context, CloseableThreadContext, putAll/pushAll](https://logging.apache.org/log4j/2.x/manual/thread-context.html)
- [Log4j 2 — Asynchronous Loggers](https://logging.apache.org/log4j/2.x/manual/async.html)
- [Log4j 2 — JSON Template Layout và MDC resolver](https://logging.apache.org/log4j/2.x/manual/json-template-layout.html)
- [Java 17 — ThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html)
- [Java 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Java 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [W3C Trace Context — traceparent/tracestate](https://www.w3.org/TR/trace-context/)

**Ghi nhớ:** Context qua async cần **snapshot ở thread gửi việc → install ở thread thực thi → chạy task → restore trong finally**. Backend ghi log bất đồng bộ thường giữ context đã được chụp trong event, nhưng **không thể tự phục hồi** requestId vốn chưa được truyền tới business worker. Cần chứng minh đúng bằng log event thực tế, không có dữ liệu cũ rò sang task sau và encoder/collector xuất đúng các field tương quan.