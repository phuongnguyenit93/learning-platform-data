# Log có thread name, task ID và correlation ID trong Java concurrency

Khi nhiều tác vụ chạy đồng thời, các dòng log của chúng đan xen: cùng một thread có thể xử lý nhiều task nối tiếp, một task có thể chuyển qua nhiều thread, và một yêu cầu có thể tạo ra nhiều task con. Nếu log chỉ chứa thông điệp như `started` hoặc `timeout`, ta khó biết dòng nào thuộc tác vụ nào, do request nào khởi phát và sự cố xảy ra ở worker nào.

Ba trường thông tin bổ sung giúp chẩn đoán:

- **Thread name:** cho biết thread đã **thực sự phát ra sự kiện log**; hữu ích để quan sát worker pool, deadlock, starvation và hành vi lập lịch.
- **Task ID:** cho biết đơn vị công việc đang được thực hiện. Tùy hợp đồng, có thể là ID công việc logic ổn định khi retry hoặc ID lần thực thi; nên phân biệt rõ hai loại.
- **Correlation ID:** nối các log cùng một yêu cầu/luồng nghiệp vụ xuyên qua nhiều phương thức, task và dịch vụ. Nhiều task ID có thể cùng một correlation ID.

Bài này tập trung vào **Java concurrency nói chung**: thread, `ExecutorService`, `CompletableFuture`, `ThreadLocal`, Java Util Logging và cách chuyển ngữ cảnh giữa các tác vụ. Không phụ thuộc vào cơ chế cấu hình log, interceptor hay context propagation riêng của Spring.

## 1. Tại sao một trường log không đủ?

Giả sử một yêu cầu nhập dữ liệu tạo hai task xử lý hai nhóm bản ghi. Ví dụ log thiếu ngữ cảnh:

```text
Started
Started
Timeout
Completed
```

Không thể chắc chắn task nào timeout, liệu `Completed` là kết quả của task nào, hay cùng một worker đã chạy lại công việc hay chưa.

Khi có đủ ba trường:

```text
level=INFO thread=import-worker-1 taskId=batch-84-part-1 correlationId=req-84 event=started
level=INFO thread=import-worker-2 taskId=batch-84-part-2 correlationId=req-84 event=started
level=WARN thread=import-worker-2 taskId=batch-84-part-2 correlationId=req-84 event=timeout
level=INFO thread=import-worker-1 taskId=batch-84-part-1 correlationId=req-84 event=completed
```

Ta thấy task `batch-84-part-2` gặp lỗi, nhưng cả hai task đều thuộc `req-84`. Thread name làm rõ worker xử lý thời điểm đó. **Đừng suy ra task luôn gắn với một thread**: async pipeline có thể đổi thread giữa các bước, và pool tái sử dụng thread cho nhiều task khác nhau.

### Quy ước trường nên nhất quán

| Trường | Nguồn gốc | Vòng đời | Vai trò |
|---|---|---|---|
| `thread.name` | `Thread.currentThread().getName()` | Theo thread; có thể đổi tên | Chẩn đoán worker đang phát log |
| `task.id` | Khi tạo đơn vị công việc | Theo task logic | Lọc toàn bộ bước xử lý của task |
| `task.attempt` hoặc `execution.id` | Khi bắt đầu một lần thử | Theo lần thực thi/retry | Phân biệt chạy lại, takeover, retry |
| `correlation.id` | Ranh giới request/job, hoặc nhận từ upstream sau xác thực | Theo chuỗi xử lý liên quan | Gom log của nhiều task/thread/dịch vụ |
| `parent.task.id` (tùy chọn) | Task cha | Theo quan hệ cha–con | Dựng quan hệ fan-out/fan-in |
| `event`, `level`, `time`, `duration` | Điểm phát log | Theo sự kiện | Hiểu kết quả và diễn biến |

Thông thường một `correlation.id` giữ nguyên khi một request tạo nhiều task. `task.id` của từng task con riêng biệt; nếu cần theo dõi nhiều lần thử, lưu thêm `attempt` thay vì tạo ID task mới mà không giữ liên kết với task logic. Nếu task nền không thuộc HTTP request nào, tạo correlation ID tại đầu workflow/job.

## 2. Đặt tên thread để biết tài nguyên nào đang làm việc

Java cho phép đặt tên khi tạo thread, qua `ThreadFactory`, hoặc thay đổi bằng `Thread.setName()`. Với executor, ưu tiên đặt tên **lúc tạo worker**:

```java
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.atomic.AtomicInteger;

final class NamedThreads {
    private static final AtomicInteger NEXT = new AtomicInteger();

    static ThreadFactory factory(String prefix) {
        return job -> new Thread(job, prefix + "-" + NEXT.incrementAndGet());
    }
}
```

Đây là class minh họa, không có `main`. Có thể đưa factory vào `Executors.newFixedThreadPool(4, NamedThreads.factory("import-worker"))`. Khi đó tên như `import-worker-1` giúp quan sát thread dump và log. Không dùng thread name làm khóa nghiệp vụ: tên không được Java đảm bảo duy nhất toàn JVM hay qua restart; hai instance có thể cùng tên worker. Nếu muốn phân biệt nhiều instance, thêm `service.instance`, `host`, `process.id` hoặc nhãn triển khai vào log.

Trong các ứng dụng có virtual thread (Java 21+), số lượng thread có thể rất lớn và có thể không được đặt tên theo ứng dụng. Thread name vẫn là thông tin bổ trợ hữu ích, nhưng không thay thế `task.id`. Phân tích deadlock, task stall hoặc downstream bottleneck cần kết hợp logs với thread dump, JFR và metric, không chỉ tên thread.

## 3. Ví dụ Java 17 đầy đủ: log đồng nhất và truyền context qua executor

Đây là chương trình độc lập dùng **`java.util.logging` của JDK** và một `ThreadLocal` giữ ngữ cảnh cho thread đang chạy. Một `record` bất biến biểu diễn correlation ID và task ID. Khi nộp task, mã chụp snapshot context, đặt nó vào worker trước khi chạy và **khôi phục context cũ trong `finally`** để tránh rò rỉ sang task tiếp theo.

Tạo tệp `ContextLoggingDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ContextLoggingDemo {
    record Context(String correlationId, String taskId) {}

    private static final ThreadLocal<Context> CURRENT = new ThreadLocal<>();
    private static final Logger LOG = Logger.getLogger("demo.concurrent");

    static {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        ConsoleHandler handler = new ConsoleHandler();
        handler.setLevel(Level.INFO);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                Context context = CURRENT.get();
                String taskId = context == null ? "-" : context.taskId();
                String correlationId =
                        context == null ? "-" : context.correlationId();

                return "level=" + record.getLevel().getName()
                        + " thread=" + Thread.currentThread().getName()
                        + " taskId=" + taskId
                        + " correlationId=" + correlationId
                        + " event=" + record.getMessage()
                        + System.lineSeparator();
            }
        });
        LOG.addHandler(handler);
    }

    static Runnable withContext(Context captured, Runnable action) {
        return () -> {
            Context previous = CURRENT.get();
            try {
                if (captured == null) {
                    CURRENT.remove();
                } else {
                    CURRENT.set(captured);
                }
                action.run();
            } finally {
                if (previous == null) {
                    CURRENT.remove();
                } else {
                    CURRENT.set(previous);
                }
            }
        };
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor(job -> {
            Thread worker = new Thread(job);
            worker.setName("worker-1");
            return worker;
        });

        try {
            CURRENT.set(new Context("req-42", "task-A"));
            Future<?> first = pool.submit(
                    withContext(CURRENT.get(), () -> LOG.info("started")));
            first.get();

            CURRENT.set(new Context("req-42", "task-B"));
            Future<?> second = pool.submit(
                    withContext(CURRENT.get(), () -> LOG.info("completed")));
            second.get();

            CURRENT.remove();
            Future<?> background = pool.submit(
                    withContext(CURRENT.get(), () -> LOG.info("background")));
            background.get();
        } finally {
            CURRENT.remove();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac ContextLoggingDemo.java
java ContextLoggingDemo
```

Đầu ra ba dòng (mặc định `ConsoleHandler` ghi vào **stderr**, không có timestamp do formatter tự định nghĩa):

```text
level=INFO thread=worker-1 taskId=task-A correlationId=req-42 event=started
level=INFO thread=worker-1 taskId=task-B correlationId=req-42 event=completed
level=INFO thread=worker-1 taskId=- correlationId=- event=background
```

Lệnh `get()` khiến ba task hoàn thành theo thứ tự hiển thị, nên đầu ra không phụ thuộc vào thời gian lập lịch giữa các worker. Một thread `worker-1` được tái sử dụng cho cả ba task, nhưng context là `task-A`, rồi `task-B`, rồi rỗng. Kết quả chứng minh **thread name không phải task ID** và cho thấy cleanup hoạt động.

Trong ví dụ, `Formatter.format()` của `ConsoleHandler` được gọi đồng bộ khi phát log, nên đọc `ThreadLocal` đúng worker. **Production logging có thể định dạng/ghi ở thread khác nếu dùng asynchronous appender**. Khi đó context phải được gắn vào **log event lúc tạo sự kiện**, chẳng hạn thông qua structured fields/MDC của thư viện logging, thay vì chỉ đọc `ThreadLocal` trong một formatter chạy trễ. Không sao chép nguyên ví dụ formatter này vào pipeline ghi log bất đồng bộ mà chưa kiểm tra thời điểm chụp context.

### Vì sao dùng `try/finally` và lưu `previous`?

Worker thread có thể sống lâu và xử lý hàng nghìn job. Nếu chỉ gọi `CURRENT.set(context)` rồi quên `remove()`, task B có thể nhìn thấy ID của task A. Ngoài việc làm sai chẩn đoán, đây còn là nguy cơ lẫn dữ liệu giữa người dùng/tenant. Nếu task gọi một wrapper con lồng bên trong, chỉ `remove()` sẽ đánh mất context cha: mẫu **lưu context trước rồi khôi phục chính xác** an toàn hơn trong cả trường hợp lồng nhau.

Bảo đảm cleanup ngay cả khi `action.run()` ném exception. Không dùng `ThreadLocal` làm nơi chứa dữ liệu nghiệp vụ cần tồn tại qua restart; nó chỉ gắn metadata vào luồng thực thi hiện tại. `ThreadLocal` không tự truyền sang các thread của executor. `InheritableThreadLocal` cũng không giải quyết được context propagation cho thread pool có sẵn, bởi worker thường được tạo một lần và phục vụ nhiều request khác nhau.

## 4. Truyền ngữ cảnh qua ranh giới bất đồng bộ

**Quy tắc:** tạo context tại ranh giới công việc, chụp snapshot khi submit, khôi phục ở thread chạy, cleanup sau khi xong. Đừng dựa vào ngẫu nhiên thread thực thi vẫn là thread cũ.

| Ranh giới | Hành động cần thiết |
|---|---|
| Gọi phương thức đồng bộ trên cùng thread | `ThreadLocal` hiện tại có thể truy cập, nhưng phải quản lý scope |
| `Executor.execute/submit` | Chụp context lúc submit, wrap `Runnable`/`Callable` |
| `CompletableFuture.supplyAsync/thenApplyAsync` | Chụp context và wrap **mỗi async stage** tương ứng |
| `CompletableFuture.thenApply` không có `Async` | Stage có thể chạy trên thread hoàn tất stage trước hoặc thread gọi; không mặc định thread context nào |
| `ScheduledExecutorService` | Rõ ràng chọn context của job tại lúc schedule/lúc trigger; không giữ nhầm request context quá lâu |
| Message queue / process boundary | Serialize ID vào metadata/header của message, sau đó xác thực/kiểm tra đầu vào và tái dựng context |
| Virtual thread | Truyền context theo scope task; không dựa vào quan hệ carrier thread |

Ví dụ đoạn mã minh họa cho `CompletableFuture` với helper `withContext` dạng `Runnable` ở trên không đủ cho lambda trả giá trị. Với `Supplier<T>`, tạo wrapper **cùng ý tưởng** nhưng trả kết quả và dùng `try/finally`:

```java
import java.util.function.Supplier;

static <T> Supplier<T> contextualSupplier(Context captured, Supplier<T> action) {
    return () -> {
        Context previous = CURRENT.get();
        try {
            if (captured == null) CURRENT.remove();
            else CURRENT.set(captured);
            return action.get();
        } finally {
            if (previous == null) CURRENT.remove();
            else CURRENT.set(previous);
        }
    };
}
```

Đây là **đoạn phương thức minh họa** đặt trong class có `Context` và `CURRENT` như ví dụ trước, không phải file chạy độc lập. Khi dùng `CompletableFuture.supplyAsync(contextualSupplier(captured, supplier), executor)`, giá trị `captured` phải lấy tại ranh giới submit thích hợp. Sau một `thenApplyAsync` mới, lại truyền context cho stage mới; không giả định `ThreadLocal` tự theo `CompletableFuture`.

Nếu đã dùng thư viện có MDC (Mapped Diagnostic Context), có thể dùng `MDC.put`, `MDC.getCopyOfContextMap`, `MDC.setContextMap`, `MDC.clear` **theo API thực tế của thư viện và adapter đang dùng**. MDC thường gắn với thread, không phải tính năng mặc định của `java.util.logging`; nó vẫn cần capture/restore khi đổi thread. Context propagation phù hợp còn cần đảm bảo classloader/thread-local lifecycle trong executor dài hạn. Không lẫn MDC với distributed tracing hoàn chỉnh.

## 5. Đặt ID đúng ranh giới và đúng ý nghĩa

Một quy tắc khả dụng:

1. **Tại điểm vào:** nhận correlation ID hợp lệ từ upstream tin cậy hoặc tạo ID mới. Tránh tin mù quáng chuỗi do client cấp; giới hạn độ dài, bộ ký tự và xác thực ranh giới truy cập. Nếu có tiêu chuẩn trace context, dùng định dạng/thỏa thuận tương thích.
2. **Khi tạo task:** cấp `task.id` và giữ quan hệ với `correlation.id`. Với fan-out, mỗi child task có task ID riêng; đặt thêm parent task ID nếu cần.
3. **Khi retry:** giữ `task.id` logic nếu đó là cùng một nghiệp vụ; gắn `attempt` hoặc `execution.id` mới để phân biệt lần thử. Không dùng correlation ID làm idempotency key trừ khi hợp đồng thật sự định nghĩa chúng đồng nhất.
4. **Khi ghi log:** luôn truyền ID vào log event, kể cả thông điệp exception, timeout, cancel, retry, queue wait và result.
5. **Khi kết thúc:** restore/clear context theo đúng scope. Nếu task tạo task con chạy sau khi task cha kết thúc, child phải nhận snapshot riêng trước khi cha cleanup.

Ví dụ một pipeline:

```text
request (correlation=req-42)
   |
   +-- task-A (taskId=task-A, attempt=1) --> worker-1
   |
   +-- task-B (taskId=task-B, attempt=1) --> worker-2
   |       |
   |       +-- retry task-B (attempt=2) --> worker-3
   |
   +-- completion event (correlation=req-42)
```

Các log đều có `req-42`; khi filter `task-B`, có thể thấy hai lần thử. Nếu chỉ dùng thread name, các lần thử bị tách rời và dễ nhầm một worker với một nghiệp vụ.

### Correlation ID, trace ID và span ID

Correlation ID là một chuỗi nhận diện yêu cầu/luồng nghiệp vụ do hệ thống định nghĩa. Trong **distributed tracing**, `trace_id` liên kết trace và `span_id` nhận diện một span; trace/span có quy tắc về độ dài, propagation và parent khác với task ID. Có thể hiển thị `trace_id` cùng `correlation.id` trong log nếu ứng dụng có tracer, nhưng đừng khẳng định chúng luôn đồng nghĩa. Một workflow kéo dài có thể mang correlation ID qua nhiều trace; một trace có thể gồm nhiều thread và task.

**Không nối log bằng thread ID hay timestamp đơn thuần**: thread được dùng lại, clock giữa máy có thể lệch, nhiều event trùng mili-giây. ID và quan hệ nhân quả cần được truyền tường minh.

## 6. Ghi log cho những thời điểm mang giá trị chẩn đoán

Đặt log có chủ ý tại điểm chuyển trạng thái, không spam log mọi bước nội bộ:

| Điểm phát log | Trường bổ sung hữu ích |
|---|---|
| `submitted` | `task.id`, `correlation.id`, queue name, accepted/rejected |
| `started` | thread name, attempt, queue wait duration |
| `waiting_for_lock` / `waiting_for_permit` | resource name, wait budget |
| `retry_scheduled` | retry reason, attempt, delay, remaining deadline |
| `cancel_requested` | caller/timeout reason; đừng ghi `cancelled` khi chưa chắc task dừng |
| `failed` | exception type, code, latency, **stack trace** nếu cần |
| `completed` | duration, outcome, phần kết quả an toàn để log |
| `shutdown` | pool name, task count, chờ hoàn tất và số reject |

Phải đo **queue wait** và **execution time** riêng. Nếu chỉ log `started` mà không log `submitted`, độ trễ queue thường bị bỏ sót. Dùng đồng hồ monotonic như `System.nanoTime()` cho khoảng thời gian, còn timestamp chuẩn UTC hoặc offset rõ ràng cho log dùng để đối chiếu giữa máy. Không giả định timestamp giữa máy cho thứ tự nhân quả tuyệt đối.

Với lỗi Java, phát log exception bằng API logger phù hợp, ví dụ `LOG.log(Level.WARNING, "task failed", ex)` của `java.util.logging`, giúp giữ stack trace khi formatter hỗ trợ. Không nên chỉ `LOG.warning(ex.getMessage())` rồi mất type và stack. Ví dụ formatter tối giản ở trên chỉ hiện `record.getMessage()`; formatter production phải thêm stack trace hoặc sử dụng encoder chuẩn để không bỏ mất `LogRecord.getThrown()`.

## 7. Structured logging: dễ tìm kiếm và không làm hỏng dữ liệu

Log dạng `key=value` như demo dễ đọc, nhưng nếu ID/event có dấu cách, dấu bằng, ký tự xuống dòng hoặc ký tự điều khiển, parser đơn giản sẽ đọc sai hoặc bị **log injection**. Trong production, ưu tiên encoder có cấu trúc (ví dụ JSON được escape đúng), không tự nối chuỗi từ dữ liệu không tin cậy. Một record nên giữ các trường tách biệt, chẳng hạn:

```json
{
  "timestamp": "2026-01-15T10:20:30.123Z",
  "level": "WARN",
  "service": "importer",
  "thread.name": "import-worker-2",
  "task.id": "batch-84-part-2",
  "task.attempt": 1,
  "correlation.id": "req-84",
  "event": "downstream_timeout",
  "duration_ms": 2200
}
```

Đây là **minh họa cấu trúc**, không phải log thực đã ghi bởi chương trình phía trên. Mỗi log nên có event name nhất quán (`task_submitted`, `task_started`, `task_failed`, `task_completed`) và level phản ánh mức độ: `INFO` cho mốc quan trọng, `DEBUG` cho chi tiết chẩn đoán, `WARN` cho tình huống phục hồi được nhưng đáng theo dõi, `ERROR` hoặc `SEVERE` theo quy ước framework cho lỗi thật sự.

Vấn đề **cardinality**: correlation ID và task ID có số lượng giá trị rất lớn. Chúng phù hợp làm field để tìm kiếm log, nhưng thường **không** phù hợp làm label metric Prometheus hay dimension tổng hợp luôn giữ trong bộ nhớ. Dùng nhãn ít biến thể cho metric (`pool`, `operation`, `status`), giữ ID riêng trong log/tracing.

Không đưa password, token truy cập, cookie, dữ liệu cá nhân nhạy cảm hoặc payload nguyên bản vào log. Với ID do người dùng cung cấp, cần validate/truncate và escape. Đảm bảo phạm vi truy cập log không khiến người thuộc tenant này xem được dữ liệu tenant khác. Nếu có sampling, ưu tiên giữ error/slow path cùng metadata đủ nối chuỗi; log sampling có thể làm vắng một phần hành trình và cần nêu rõ cho người điều tra.

## 8. Phân biệt context propagation và tình trạng cạnh tranh dữ liệu

`ThreadLocal` giúp mỗi worker có **giá trị context riêng**, chứ không làm cho mọi thao tác đồng thời trở nên thread-safe. Nếu nhiều task cùng sửa một object `HashMap` hoặc cùng tăng counter không nguyên tử, log ID đầy đủ không sửa được race. Thread dump cho thấy thread nào chờ lock; log correlation giúp liên hệ với task; cùng lúc vẫn cần đúng synchronization, atomic types hoặc cấu trúc dữ liệu concurrent.

Tương tự, context có thể bị rò nếu:

- Quên cleanup trong `finally` khi action ném exception.
- Set context trên worker nhưng reset trên **thread gọi**, không phải worker.
- Copy đối tượng context **mutable** qua thread rồi sửa từ nhiều nơi.
- Dùng `InheritableThreadLocal` với pool và tưởng rằng nó theo từng lần submit.
- Tạo callback bất đồng bộ mà quên wrap một stage, làm log có `task.id=-`.
- Dùng `CompletableFuture` mặc định chạy trong `ForkJoinPool.commonPool()` nhưng vẫn giả định context request theo sang.
- Dùng formatter/appender bất đồng bộ đọc thread-local **sau khi** worker đã cleanup.
- Dùng tên thread làm khóa duy nhất cho nghiệp vụ; tên giống nhau qua instance/restart.

Nên dùng context bất biến (ví dụ `record` Java 17) và chỉ truyền metadata cần thiết. Nếu có nesting, phải khôi phục context cũ; nếu không có context cha, phải `remove()` thay vì để placeholder tồn tại mãi trong `ThreadLocal`.

## 9. Kiểm thử tính đúng đắn của logging đồng thời

Log có giá trị khi **đủ, đúng ngữ cảnh và không bị lẫn** trong tình huống thật:

| Ca kiểm thử | Điều cần thấy |
|---|---|
| Hai task chạy trên cùng worker lần lượt | Hai `task.id` khác nhau, thread name giống nhau |
| Một request fan-out thành nhiều task | Correlation ID như nhau, task ID khác nhau |
| Task chuyển thread qua `thenApplyAsync` | Context vẫn đúng khi được wrap, tên thread phản ánh nơi chạy thật |
| Task ném exception | `finally` cleanup, task kế tiếp không lấy ID cũ |
| Task bị cancel/timeout | Log mô tả trạng thái chính xác, không nhầm yêu cầu hủy với hoàn tất |
| Task retry nhiều lần | Cùng logical task ID, `attempt` phân biệt các lần thử |
| Tác vụ nền không có request | Context được khởi tạo hợp lệ hoặc field thiếu được biểu diễn có chủ ý |
| Bất kỳ client gửi ID dài hoặc xuống dòng | Encoder escape/giới hạn, không tạo dòng log giả |
| Async appender ghi trên thread riêng | Log event đã chụp đúng ID khi phát sinh |
| Nhiều JVM có worker cùng tên | Instance ID giúp phân biệt nơi chạy |

Một kiểm thử quan trọng là dùng **single-thread executor** nộp lần lượt task A có context, task B với context khác, task C không có context, rồi đọc log: task C không được chứa ID của task A hoặc B. Kiểm thử thêm case exception giữa chừng để đảm bảo `finally` luôn chạy.

Khi có log đầy đủ, có thể dựng một truy vấn chẩn đoán theo thứ tự: lọc `correlation.id` để xem toàn workflow; chọn `task.id` lỗi; chia theo `attempt`; kiểm tra `submitted/started/failed/completed`; sau đó đối chiếu `thread.name`, pool name, queue wait, lock wait, JFR/thread dump hoặc metric để tìm nút nghẽn. Với nhiều máy, ưu tiên quan hệ causal ID hơn thứ tự timestamp tuyệt đối.

## 10. Checklist thực hành

Trước khi triển khai logging cho hệ thống concurrent Java, hãy kiểm tra:

1. Có định nghĩa rõ **correlation ID**, **logical task ID**, **execution/attempt ID** và phạm vi duy nhất của chúng.
2. Thread factory đặt tên worker dễ nhận diện; log còn có service/instance để tránh nhầm nhiều JVM.
3. Khi submit async task, đã capture context ở đúng thời điểm và restore/clear trong **thread thực thi** với `try/finally`.
4. Mọi continuation async được bọc theo ngữ cảnh phù hợp; không dựa vào `InheritableThreadLocal` cho executor.
5. Logger/encoder gắn context **lúc tạo log event**, đặc biệt nếu appender bất đồng bộ.
6. Log các mốc submit/start/retry/cancel/error/complete với duration và outcome trung thực.
7. Log được escape, kiểm soát dữ liệu nhạy cảm, size, retention, sampling và quyền truy cập.
8. Metric có nhãn cardinality thấp; ID dùng cho log/tracing.
9. Có bài kiểm thử task lỗi, retry, worker reuse, context rỗng và chuyển thread.
10. Khi chẩn đoán concurrency, kết hợp log với thread dump/JFR, metric và dữ liệu queue thay vì kết luận chỉ từ tên thread.

**Nguyên tắc then chốt:** thread name trả lời *điều gì đang chạy ở đâu*, task ID trả lời *đơn vị công việc nào*, correlation ID trả lời *những sự kiện nào thuộc cùng một hành trình*. Trong concurrency, việc **truyền và dọn ngữ cảnh qua ranh giới bất đồng bộ** quan trọng không kém việc thêm ba trường vào mẫu log.
