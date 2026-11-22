# 5.5 Thu thập lỗi không được bắt qua UncaughtExceptionHandler

## Mục tiêu học tập

Trong ứng dụng Java nhiều luồng, một exception có thể làm **một thread kết thúc đột ngột** mà luồng gọi hoặc bộ phận giám sát không trực tiếp nhận được giá trị trả về. `Thread.UncaughtExceptionHandler` cung cấp một điểm quan sát cuối cùng khi một `Thread` sắp kết thúc vì `Throwable` không được bắt. Tuy nhiên, cơ chế này không thay thế việc xử lý exception trong nghiệp vụ và **không nhìn thấy mọi lỗi của tác vụ bất đồng bộ**.

Sau bài này, bạn có thể:

- Mô tả chính xác thời điểm JVM gọi `Thread.UncaughtExceptionHandler`, tham số `Thread`/`Throwable` và mức độ ảnh hưởng của exception đến thread/process.
- Thiết lập handler **riêng cho thread**, handler **mặc định toàn JVM**, hoặc gắn handler khi tạo worker thread qua `ThreadFactory`.
- Hiểu thứ tự phân giải handler: thread → `ThreadGroup` → default; biết vì sao `getUncaughtExceptionHandler()` có thể trả về `ThreadGroup`.
- Thu lại loại lỗi, thông điệp, stack trace/cause và ngữ cảnh chẩn đoán mà không làm phát sinh rủi ro logging quá mức.
- Phân biệt lỗi thoát ra khỏi `Thread.run()` với lỗi đã được `ExecutorService.submit()`, `Future`, `CompletableFuture` hoặc framework bắt và lưu.
- Tạo ví dụ **Java 17+ chạy được** và đối chiếu stdout chính xác cho hai đường thu thập lỗi.
- Nhận diện giới hạn của handler với OOM, lỗi native, `System.exit`, SIGKILL và các luồng tác vụ đã có cơ chế báo lỗi riêng.

## 1. “Không được bắt” nghĩa là gì?

Trong Java, `Throwable` là gốc của phân cấp gồm `Exception` và `Error`. Một lỗi được gọi là **uncaught** đối với thread khi nó lan qua các khung gọi mà không được mã Java thích hợp bắt/xử lý và cuối cùng làm thread **kết thúc bất thường**.

Ví dụ:

```java
Thread worker = new Thread(() -> {
    throw new IllegalStateException("invalid invoice");
}, "invoice-worker");
worker.start();
```

Đây là **đoạn minh họa**, không phải một chương trình độc lập. `IllegalStateException` không bị bắt bên trong `Runnable`; thread `invoice-worker` sẽ kết thúc vì lỗi. Nếu không có handler tùy chỉnh/default, cơ chế `ThreadGroup` chuẩn thường in thông điệp và stack trace ra **standard error (`System.err`)**. Nó không tự động gửi exception về thread gọi `start()`.

Phân biệt ba trường hợp:

1. **Được bắt trong worker:** `try/catch` xử lý và không ném tiếp; thread có thể tiếp tục. `UncaughtExceptionHandler` không được gọi cho exception đã bị bắt.
2. **Không được bắt và thoát khỏi thread:** JVM đi vào đường báo uncaught exception, gọi handler tương ứng trước khi thread hoàn tất việc kết thúc.
3. **Được framework/executor bắt:** lỗi của công việc có thể nằm trong `Future`, response, callback hoặc một hệ thống job riêng, dù logic của task đã thất bại. Handler của thread **không nhất thiết được gọi**.

**Quan trọng:** handler là nơi **quan sát và báo cáo thất bại sau cùng của thread**, không phải `catch` bao quanh mọi câu lệnh Java và không phải cơ chế tự phục hồi task.

## 2. API của `Thread.UncaughtExceptionHandler`

Java định nghĩa một functional interface:

```java
@FunctionalInterface
public interface Thread.UncaughtExceptionHandler {
    void uncaughtException(Thread t, Throwable e);
}
```

Đoạn trên mô tả **chữ ký API**, không phải tệp cần tự định nghĩa lại. Trong JDK, interface thực được khai báo bên trong `java.lang.Thread`. Hai tham số:

- `Thread t`: thread đang kết thúc vì uncaught exception, cung cấp tên, ID và một số metadata thread.
- `Throwable e`: đối tượng lỗi thực sự, có thể là `RuntimeException`, `Error` hoặc một `Throwable` phù hợp khác; nó chứa message, stack trace, cause và suppressed exceptions khi có.

Khi một thread sắp kết thúc do exception không bắt, JVM truy vấn `getUncaughtExceptionHandler()` và gọi `uncaughtException(t,e)`. Nếu **chính handler ném thêm một exception**, JVM **bỏ qua lỗi do handler ném**. Vì vậy handler nên nhỏ, ổn định và không dựa vào việc exception từ handler sẽ được truyền ra nơi khác.

Các API thiết yếu:

| API | Phạm vi | Ý nghĩa |
| --- | --- | --- |
| `thread.setUncaughtExceptionHandler(handler)` | Một `Thread` cụ thể | Đặt handler riêng cho thread đó |
| `thread.getUncaughtExceptionHandler()` | Một `Thread` cụ thể | Trả handler đã được chỉ định trực tiếp, hoặc `ThreadGroup` của thread nếu chưa có handler riêng (khi thread chưa kết thúc) |
| `Thread.setDefaultUncaughtExceptionHandler(handler)` | Mặc định cho JVM | Đặt handler được dùng theo đường fallback khi không có xử lý riêng từ thread/group |
| `Thread.getDefaultUncaughtExceptionHandler()` | Mặc định cho JVM | Xem handler mặc định hiện tại, có thể là `null` |
| `ThreadGroup.uncaughtException(t,e)` | Một nhóm thread | Có thể tiếp tục chuyển lên parent/default hoặc tự xử lý |

Không nhầm `getUncaughtExceptionHandler()` và `getDefaultUncaughtExceptionHandler()`: method thứ nhất **không luôn trả về default handler**. Nếu thread chưa được đặt handler riêng, `ThreadGroup` có thể là giá trị trả về.

Các phương thức thiết lập handler có thể ném `SecurityException` trong môi trường có chính sách quyền truy cập tương ứng. Với ứng dụng/framework có sẵn handler, không tự động ghi đè vì bạn có thể vô hiệu hóa logging/tracing đang được triển khai.

## 3. Thứ tự chọn handler: thread, ThreadGroup, default

Một cách hình dung đối với Java 17:

```text
Một Throwable thoát khỏi code thực thi của Thread
                   |
                   v
      Thread có handler riêng không?
          /                   \
        Có                   Không
        |                      |
        v                      v
  Handler của thread      ThreadGroup.uncaughtException
                             |
                             v
                        Parent group (nếu có)
                             |
                             v
                 Default handler (nếu có)
                             |
                             v
               Nếu không có, hành vi fallback:
                  in stack trace ra stderr
                 (ThreadDeath là ngoại lệ)
```

Các mũi tên của `ThreadGroup` biểu diễn **cơ chế mặc định**. Một subclass của `ThreadGroup` có thể override `uncaughtException` và xử lý khác, không nhất thiết chuyển tiếp. Vì vậy không đảm bảo default handler sẽ quan sát mọi lỗi nếu ứng dụng/framework đã tùy biến group.

**Ưu tiên thường gặp:**

- Một thread được đặt handler riêng sẽ chuyển thẳng lỗi cho handler đó; **default handler không tự động nhận thêm một bản sao**.
- Nếu không có handler riêng, `ThreadGroup` của thread là handler thực thi; hành vi chuẩn chuyển lên parent và sau đó default.
- Nếu không có default handler và `ThreadGroup` không xử lý đặc biệt, lỗi thông thường được in ra stderr; với `ThreadDeath` cơ chế fallback mặc định không in như những Throwable khác.
- `setDefaultUncaughtExceptionHandler(null)` bỏ default tùy chỉnh; không làm mất handler riêng đã đặt cho các thread.

Một handler **không nên tự gọi lại `ThreadGroup.uncaughtException` thiếu kiểm soát** để “giữ hành vi cũ”, vì cách này có thể đi vòng về chính default handler và gây recursion. Nếu cần kết hợp các hệ thống xử lý, thiết kế rõ delegation và chặn vòng lặp.

## 4. Đăng ký handler riêng cho thread

Áp dụng khi biết thread nào có trách nhiệm quan trọng hoặc muốn gắn nhãn theo từng nhóm nghiệp vụ. Ví dụ một worker chuyên nhập dữ liệu:

```java
Thread importThread = new Thread(
        () -> { throw new IllegalStateException("import failed"); },
        "import-worker");

importThread.setUncaughtExceptionHandler((thread, error) -> {
    System.err.println("Uncaught in " + thread.getName());
    error.printStackTrace(System.err);
});

importThread.start();
```

Đây là **đoạn minh họa**, không có `main` và stdout cố định. Handler sẽ in sang **stderr**, không phải stdout. Trong ứng dụng thực, nên chuyển sang logger có cấu trúc và cơ chế telemetry phù hợp; `printStackTrace` trực tiếp chỉ hữu ích khi demo hoặc khi có chủ đích ghi ra luồng lỗi được thu gom.

Thiết lập handler **trước `start()`** là cách dễ kiểm soát nhất. Nếu thay handler trong khi thread đang chạy, bạn tạo thêm khả năng race với thời điểm thread thất bại. Bên cạnh đó, code có quyền điều chỉnh thread khác không có nghĩa tác động đó không ảnh hưởng framework.

Khi nào nên dùng handler riêng?

- Worker chuyên biệt mà failure không được phép mất dấu.
- Thread được tạo thủ công và có component/job ID xác định.
- Một số nhóm worker cần cách báo lỗi khác với chính sách default toàn ứng dụng.

Không cần cài handler riêng lên **mọi** thread nếu một default handler và các cơ chế xử lý lỗi của executor/framework đã bao phủ đúng mục tiêu. Tránh tạo nhiều bản ghi cho cùng một exception.

## 5. Đặt default handler toàn JVM

Ví dụ:

```java
Thread.UncaughtExceptionHandler existing =
        Thread.getDefaultUncaughtExceptionHandler();

Thread.setDefaultUncaughtExceptionHandler((thread, error) -> {
    // Gửi thông tin tới logger/monitoring phù hợp.
    System.err.println("Uncaught failure on " + thread.getName());
    error.printStackTrace(System.err);
});
```

Đoạn này minh họa hai API. `existing` lưu handler trước đó để đội triển khai **xem xét phối hợp**; không nên tự động gọi lại handler cũ nếu có nguy cơ recursion hoặc logging trùng lặp. Chỉ quản lý/thay đổi chính sách default khi thành phần của bạn thực sự sở hữu việc cấu hình toàn JVM.

Nên cài default handler **sớm trong startup** trước khi ứng dụng tạo nhiều thread để hành vi dễ dự đoán. Tuy nhiên thời điểm cài sớm không đảm bảo toàn bộ lỗi đều đi qua nó, vì thread có handler riêng, `ThreadGroup` tùy chỉnh, executor và framework có thể có đường xử lý khác.

Trong server có application container, thư viện logging, job scheduler, observability agent hoặc framework, phải kiểm tra những cơ chế đã sẵn có. Việc thay default handler không nên vô hiệu hóa quy trình cảnh báo/sự kiện lỗi có chủ đích.

### 5.1 Default handler có làm toàn ứng dụng dừng không?

**Không.** Nếu một background thread kết thúc bất thường, handler có thể ghi nhận lỗi, nhưng nhiều thread khác vẫn tiếp tục chạy và tiến trình Java có thể còn sống. Nếu exception không bắt thoát khỏi `main`, main thread kết thúc, nhưng JVM chỉ tự kết thúc khi các điều kiện vòng đời thread/process tương ứng thỏa; các non-daemon threads còn hoạt động có thể giữ process sống.

Handler **không** tự khởi động lại thread, không tự retry một tác vụ, không rollback transaction và không bảo đảm trả response lỗi cho client. Phục hồi cần chính sách độc lập: supervisor, restart worker theo thiết kế, retry có giới hạn, circuit breaker, health check hoặc báo lỗi tới orchestrator.

## 6. Demo Java 17+: handler riêng, default và lỗi nằm trong Future

Ví dụ độc lập này cho thấy ba đường xử lý: một thread có handler riêng, một thread dùng default handler, và một task gửi qua `ExecutorService.submit` mà lỗi được giữ trong `Future`.

Tạo tệp **`UncaughtHandlerDemo.java`**:

```java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class UncaughtHandlerDemo {
    private static void report(String route, Thread thread, Throwable error) {
        System.out.println(route + " | " + thread.getName()
                + " | " + error.getClass().getSimpleName()
                + " | " + error.getMessage());
    }

    public static void main(String[] args) throws Exception {
        Thread.setDefaultUncaughtExceptionHandler(
                (thread, error) -> report("DEFAULT", thread, error));

        Thread invoice = new Thread(
                () -> { throw new IllegalStateException("invoice missing"); },
                "invoice-thread");
        invoice.setUncaughtExceptionHandler(
                (thread, error) -> report("PER_THREAD", thread, error));
        invoice.start();
        invoice.join();

        Thread parser = new Thread(
                () -> { throw new IllegalArgumentException("bad CSV"); },
                "parse-thread");
        parser.start();
        parser.join();

        ExecutorService pool = Executors.newSingleThreadExecutor(r -> {
            Thread thread = new Thread(r, "pool-thread");
            thread.setUncaughtExceptionHandler(
                    (t, error) -> report("POOL_UNCAUGHT", t, error));
            return thread;
        });

        Future<?> result = pool.submit(
                () -> { throw new IllegalStateException("task failed"); });

        try {
            result.get();
        } catch (ExecutionException exception) {
            Throwable cause = exception.getCause();
            System.out.println("FUTURE_CAUSE | "
                    + cause.getClass().getSimpleName()
                    + " | " + cause.getMessage());
        } finally {
            pool.shutdown();
        }

        System.out.println("END");
    }
}
```

Biên dịch và chạy với **JDK 17 trở lên**:

```bash
javac UncaughtHandlerDemo.java
java UncaughtHandlerDemo
```

Stdout **chính xác trong môi trường JDK 17 thông thường**:

```text
PER_THREAD | invoice-thread | IllegalStateException | invoice missing
DEFAULT | parse-thread | IllegalArgumentException | bad CSV
FUTURE_CAUSE | IllegalStateException | task failed
END
```

Giải thích từng dòng:

1. `invoice-thread` có handler riêng. Nó nhận `IllegalStateException`; default handler không in thêm dòng `DEFAULT` cho thread này.
2. `parse-thread` không có handler riêng nên đi qua `ThreadGroup` mặc định tới default handler đã cài.
3. `pool.submit(...)` tạo một task mà lỗi được **`FutureTask` bắt và lưu**. `result.get()` ném `ExecutionException`, có `getCause()` là `IllegalStateException`. Dòng `POOL_UNCAUGHT` **không xuất hiện**.
4. `invoice.join()` và `parser.join()` đợi từng thread kết thúc nên hai dòng handler xuất hiện theo thứ tự đã mô tả; `result.get()` đợi kết quả task trước dòng `FUTURE_CAUSE`.
5. `pool.shutdown()` yêu cầu pool ngừng nhận task mới và hoàn thành task đang chờ; ở đây task duy nhất đã hoàn tất. Code không dùng `Thread.stop()` hay `System.exit()` để giả lập sự cố.

Để tập trung vào **đường đi exception**, handler demo chỉ in loại lỗi và message. Trong production, bạn cần **stack trace/cause/suppressed exceptions** qua logger phù hợp; hai trường text không đủ để chẩn đoán. Đồng thời demo thay default handler cho **JVM của chương trình test**, không nên bê nguyên logic ghi đè mặc định vào server đang chạy mà chưa xác minh các handler của framework.

### 6.1 Vì sao demo không tự có stack trace dài trên stderr?

Cơ chế fallback của `ThreadGroup` thường tự in stack trace **khi không có default/custom handler tương ứng**. Ở đây đã có handler riêng và default handler, cả hai chỉ gọi `System.out.println`. JVM không tự in thêm một stack trace mặc định sau khi handler của bạn đã xử lý. Muốn thấy stack trace, chính handler phải gọi logger với đối tượng `Throwable` hoặc in trace có chủ đích.

### 6.2 Cách kiểm tra hiểu bài bằng thay đổi nhỏ

- Xóa dòng `invoice.setUncaughtExceptionHandler(...)`: `invoice-thread` sẽ dùng đường default thông thường; dòng đầu đổi nhãn thành `DEFAULT`.
- Bỏ cài đặt default handler: với các thread không có handler riêng, fallback chuẩn có thể in stack trace ra **stderr**, khiến bạn không thể so sánh chỉ stdout như bản gốc.
- Thay `pool.submit` bằng cơ chế `execute`: đường propagation của task có thể khác; không suy từ kết quả demo rằng mọi lỗi trong executor đều bị `Future` giữ.

## 7. Vì sao lỗi trong ExecutorService có thể không đến handler?

Đây là bẫy quan trọng nhất khi dùng `UncaughtExceptionHandler` để giám sát background processing.

### 7.1 `execute(Runnable)` và `submit(...)` không tương đương

| Đường gửi task | Cách lỗi thường được biểu hiện | Có nên trông chờ UncaughtExceptionHandler? |
| --- | --- | --- |
| `new Thread(r).start()`, `Runnable` ném lỗi không được bắt | Exception thoát khỏi đường chạy của `Thread`; thread kết thúc | **Có**, theo quy tắc handler của thread |
| `Executor.execute(r)` với `ThreadPoolExecutor` | `Runnable` ném lỗi có thể làm worker kết thúc đột ngột; executor có xử lý vòng đời worker | **Có thể**, nếu Throwable thật sự thoát đến thread; phụ thuộc executor và cách task được bọc |
| `ExecutorService.submit(r/c)` | Thường được bọc trong `FutureTask`; lỗi được lưu để `Future.get()` báo qua `ExecutionException` | **Không** với lỗi đã được `FutureTask` bắt |
| `CompletableFuture.supplyAsync/runAsync` | Exception được lưu thành **exceptional completion**, người tiêu thụ thấy qua `get()/join()` hoặc callback | **Không nên phụ thuộc** handler của worker |
| Thread/framework tự `try/catch` và log | Lỗi không thoát đến biên thread | Không, vì lỗi đã được xử lý ở lớp trong |
| Task bị từ chối bởi executor | `execute/submit` có thể ném `RejectedExecutionException` **trên thread gửi** | Không mặc định là uncaught trên worker; xử lý ở caller/rejection policy |

Chú ý: nếu chính thread của **caller** ném một `RejectedExecutionException` mà không bắt, handler của *caller thread* có thể được gọi khi thread đó kết thúc. Đó là hiện tượng khác với việc “worker bắt được lỗi trong job”.

### 7.2 Tại sao `Future.get()` là phần không được bỏ qua?

Một `FutureTask` có thể bắt `Throwable` từ nội dung công việc và ghi trạng thái thất bại. Nếu ứng dụng chỉ gọi `submit()` rồi **bỏ rơi `Future`**, lỗi có nguy cơ không xuất hiện trong log/alert theo cách bạn mong muốn.

```java
// Đoạn minh họa bên trong một phương thức có sẵn ExecutorService pool.
Future<?> future = pool.submit(() -> {
    throw new IllegalStateException("background task failed");
});

try {
    future.get();
} catch (ExecutionException ex) {
    Throwable rootCause = ex.getCause();
    // Ghi log rootCause kèm stack trace, job ID, thời gian, trạng thái.
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Áp dụng chính sách dừng/chuyển trạng thái thích hợp.
}
```

Đoạn này **không phải chương trình độc lập** và không phải lời khuyên luôn gọi `get()` ngay sau `submit()`, vì làm vậy có thể biến công việc bất đồng bộ thành chờ đồng bộ. Trong hệ thống thực, hãy có **thành phần theo dõi kết quả riêng**, completion queue, callback hoặc cơ chế framework nhận thất bại tương ứng, thay vì bỏ qua `Future`.

Trong `ThreadPoolExecutor.afterExecute(Runnable, Throwable)`, tham số `Throwable` có thể là `null` với `FutureTask` dù nội dung task đã thất bại, vì `FutureTask` đã bắt và lưu lỗi. Tài liệu chính thức khuyến nghị khi cần quan sát cả hai kiểu lỗi thì kiểm tra đối tượng `Future` đã `isDone()`, rồi lấy nguyên nhân qua `get()` và xử lý cả `CancellationException`/`InterruptedException`. Đừng mặc định `afterExecute` nhận non-null với mọi task lỗi.

### 7.3 `CompletableFuture`: quan sát exceptional completion

Ví dụ **đoạn mã tích hợp**, sử dụng một `Executor` đã có:

```java
CompletableFuture<String> stage =
        CompletableFuture.supplyAsync(() -> {
            throw new IllegalStateException("remote lookup failed");
        }, executor);

stage.whenComplete((value, failure) -> {
    if (failure != null) {
        // Ghi failure với context; có thể là wrapper CompletionException.
    }
});
```

Lớp `CompletableFuture` quản lý trạng thái hoàn thành đặc biệt; callback `whenComplete` hoặc đường `get()/join()` là nơi phù hợp để quan sát. `join()` báo thất bại qua unchecked `CompletionException` trong các tình huống tương ứng, trong khi `get()` dùng checked `ExecutionException`. Hãy xem `getCause()` khi có wrapper, nhưng không tự giả định mọi `Throwable` đều có cause khác `null`.

`whenComplete` có thể chạy trên thread hoàn thành stage hoặc một executor tùy cách đăng ký; logic báo lỗi nên đủ nhẹ và không được dựa vào thread name để suy luôn request ID.

## 8. Gắn handler vào ThreadFactory cho thread pool

Nếu ứng dụng **tự sở hữu cách tạo worker thread**, `ThreadFactory` giúp gắn tên và handler nhất quán ngay khi thread được tạo.

```java
// Đoạn mã tích hợp trong service có logger tên LOGGER.
AtomicInteger sequence = new AtomicInteger();

ThreadFactory factory = task -> {
    Thread worker = new Thread(
            task, "payment-worker-" + sequence.incrementAndGet());

    worker.setUncaughtExceptionHandler((thread, error) ->
            LOGGER.log(Level.SEVERE,
                    "Uncaught error in " + thread.getName(), error));

    return worker;
};

ExecutorService executor = Executors.newFixedThreadPool(4, factory);
```

Cần import `java.util.concurrent.*`, `java.util.concurrent.atomic.AtomicInteger` và `java.util.logging.Level` trong chương trình tích hợp. `LOGGER` là logger của service, không phải biến có sẵn trong JDK. Đoạn mã **không độc lập** và không tự bảo đảm mọi task lỗi đi qua handler, vì đường `submit` đã bọc lỗi như phần trên.

Những điều cần giữ:

- Đặt handler **trước khi trả worker** từ factory, để executor có thể chạy thread ngay sau đó.
- Đặt tên thread nhận diện nhóm công việc; không nhét token, payload hoặc thông tin cá nhân vào tên.
- Không coi thread name là job ID: một worker trong pool xử lý **nhiều task liên tiếp**, nên cần job/request ID trong logging context được gắn và xóa đúng vòng đời task.
- Giữ `ThreadFactory` nhỏ, không cấp phát tài nguyên lớn hoặc gọi API có thể block lâu khi tạo thread.
- Nếu framework đã cung cấp factory/handler, phối hợp với cơ chế đó thay vì thay đột ngột từ bên ngoài.
- Nếu lỗi thực sự làm worker chết, `ThreadPoolExecutor` có thể tạo worker thay thế tùy trạng thái/thiết lập; handler không tự động xác nhận task đã được retry hoặc khôi phục thành công.

## 9. Thu thập bằng chứng gì trong handler?

Mục tiêu là tạo một **sự kiện chẩn đoán có thể truy vết**, đủ dùng để người khác hiểu loại lỗi, thread, component và thời điểm xảy ra. Tối thiểu nên có:

| Nhóm thông tin | Trường hữu ích | Lý do |
| --- | --- | --- |
| Thời gian | UTC ISO-8601 có offset, timestamp chính xác | Ghép với log/trace/GC/event của hệ thống |
| Tiến trình | Service, environment, build/version, instance/pod, PID nếu có | Xác định đúng bản chạy và phạm vi tác động |
| Thread | Thread name, thread ID, loại worker, group khi có ích | Xác định luồng bị kết thúc |
| Exception | Loại Throwable, message đã kiểm soát, **toàn bộ stack trace, cause và suppressed** | Lần ngược đường code và cơ chế lỗi |
| Công việc | Job/task ID, request/trace/correlation ID, loại thao tác | Nối lỗi thread với yêu cầu nghiệp vụ |
| Tác động | Worker quan trọng hay không, công việc mất/chưa xử lý, cơ chế khôi phục | Phân biệt một task lỗi với mất khả năng phục vụ |
| Quan sát | Event counter, log location, alert/deduplication key | Tìm sự cố lặp và mức ảnh hưởng |

Ví dụ cách ghi bằng `java.util.logging` trong một class có logger:

```java
private static final java.util.logging.Logger LOGGER =
        java.util.logging.Logger.getLogger("runtime-diagnostics");

static void reportUncaught(Thread thread, Throwable error) {
    LOGGER.log(java.util.logging.Level.SEVERE,
            "Uncaught failure on " + thread.getName(), error);
}
```

Đây là **đoạn mã tích hợp**, không phải một ứng dụng độc lập. Overload `log(Level, String, Throwable)` chuyển đối tượng exception cho logging framework; cấu hình handler/formatter của logger quyết định nơi ghi và cách render stack trace. Đừng chỉ log `error.getMessage()` vì nó có thể trống và làm mất chain of causes.

### 9.1 Ngữ cảnh bất đồng bộ không tự truyền đi

Ở server Java, request ID có thể nằm trong `ThreadLocal`/MDC hoặc tracing context. Khi một nhiệm vụ được chuyển qua pool:

- Request context **không tự động** xuất hiện đầy đủ trong thread khác nếu không propagate theo thiết kế.
- Worker xử lý nhiều task; nếu không xóa MDC/ThreadLocal sau từng task, log có thể ghi **nhầm request ID** của task trước.
- Khi handler chạy sau lỗi, context có thể đã bị framework dọn hoặc không được đặt từ đầu.
- Một uncaught failure của thread quản trị/GC helper không nhất thiết gắn với bất kỳ HTTP request nào.

Cách đáng tin hơn là tạo **task context có ID rõ**, truyền context một cách chủ động và bảo đảm cleanup trong `finally`. Handler là đường cuối cùng, không thay thế log ở biên nhiệm vụ nơi còn biết đầy đủ nghiệp vụ.

### 9.2 Bảo vệ dữ liệu nhạy cảm

Stack trace, exception message, system properties hoặc nội dung request có thể chứa đường dẫn nội bộ, host, tên người dùng, URL có credential hoặc dữ liệu nghiệp vụ. Cần **che/redact** trước khi đưa vào nơi tập trung, thiết lập retention và phân quyền. Không in raw payload, token hoặc object `toString()` không kiểm soát chỉ để chẩn đoán.

Với lỗi lặp nhiều lần, đặt rate limit/deduplication và vẫn giữ số đếm tổng; nếu log tràn khi service đang lỗi, chính việc logging có thể làm CPU, I/O và dung lượng đĩa tệ hơn.

## 10. Handler phải an toàn trong thời điểm bất thường

Handler chạy đúng lúc thread sắp kết thúc do lỗi. Đừng biến nó thành một luồng xử lý nghiệp vụ phức tạp.

**Thiết kế tốt:**

- Ngắn và không chặn lâu. Ưu tiên logger/queue đã cấu hình sẵn; tránh gọi mạng đồng bộ có timeout dài hoặc lấy lock đang có nguy cơ deadlock.
- Giữ nguyên `Throwable` và stack trace; chỉ thêm metadata thực sự có sẵn.
- Đảm bảo lỗi trong logger không gây vòng lặp exception; có thể có đường fallback tối thiểu, nhưng cũng phải chấp nhận rằng fallback có thể thất bại khi tài nguyên cạn.
- Không gọi `System.exit()` chỉ vì một task lỗi, trừ khi ứng dụng có chính sách vận hành được thiết kế rõ cho lỗi chí mạng.
- Không cố “tiếp tục” chính thread đã kết thúc, không tự retry task trong callback nếu chưa biết idempotency, transaction và chính sách backoff.
- Không dùng `synchronized` trên tài nguyên đang có khả năng do chính thread lỗi giữ trong lúc thoát.
- Phân biệt error reporting với process supervision: chính sách restart nên nằm ở tầng supervisor/health/queue đúng trách nhiệm.

**Giới hạn khó tránh:**

- `OutOfMemoryError` có thể đến handler nếu vượt qua các lớp gọi và làm thread kết thúc, nhưng bản thân việc format stack, cấp phát đối tượng log và gửi dữ liệu có thể **thất bại do thiếu memory**. Không hứa ghi log thành công khi OOM.
- Với `StackOverflowError`, stack/resource có thể hạn chế khả năng logging.
- `SIGKILL`, OOM kill do kernel, `Runtime.halt()`, mất điện, crash native nghiêm trọng hoặc quá trình bị dừng đột ngột không bảo đảm Java handler được gọi.
- `System.exit()` khởi tạo quá trình shutdown JVM; không phải cơ chế ném uncaught exception để handler nhận.
- Nếu chính `uncaughtException` ném lỗi, JVM **bỏ qua lỗi đó**; không trông chờ handler khác sẽ tự động “bắt thay”.
- Async logging có thể chưa flush xong trước khi process chấm dứt. Với sự cố nghiêm trọng, kết hợp với process logs, container termination reason, crash files, JFR/metrics và log collector độc lập.

Cơ chế này giúp **giảm khả năng mất dấu** trong nhiều tình huống thường gặp; nó không bảo đảm 100% lỗi đều có bản ghi.

## 11. Phân biệt lỗi thread và lỗi toàn process

| Quan sát | Kết luận được phép nói | Cần kiểm tra thêm |
| --- | --- | --- |
| Handler ghi `IllegalStateException` của worker A | Thread A đã kết thúc do lỗi không bắt và handler đã chạy | Task nào bị ảnh hưởng, worker có thay thế không, có mất dữ liệu không |
| `Future.get()` trả `ExecutionException` | Task tương ứng đã thất bại và lỗi được lưu trong Future | Task đã được báo/khôi phục chưa, ai theo dõi Future |
| Log có `OutOfMemoryError` | JVM đã báo một loại resource error trong đường Java | Heap/native/metaspace/threads, cgroup, GC, trạng thái process |
| Container có `OOMKilled` và không có handler log | Có dấu hiệu kernel/container terminate vì memory condition | Cgroup events, memory peak, PID/container đúng, timestamp |
| App còn trả HTTP 200 sau khi một worker chết | Một số luồng vẫn phục vụ được | Mất năng lực xử lý nền hay queue có đang tăng không |
| Không có log uncaught trong một khoảng thời gian | Chưa quan sát được uncaught event trên đường thu hiện có | Future/callback/framework errors, log loss, crash/kill, instrumentation |

Phân biệt **`UncaughtExceptionHandler`** với **shutdown hook**: shutdown hook được dùng khi JVM đi vào quá trình shutdown có điều kiện phù hợp, trong khi uncaught handler được gọi khi thread chết vì Throwable không bắt. Hai cơ chế khác mục tiêu và đều không phải bảo đảm thu dữ liệu khi máy/process bị kill đột ngột.

## 12. Quy trình triển khai để chẩn đoán production

### Bước 1 — Xác định đường tạo và chạy thread

Liệt kê phạm vi cần bảo vệ: thread tự tạo, executor, scheduler, message consumer, event listener hay job framework. Xem framework có sẵn callback error handler hoặc cơ chế hoàn thành `Future` không. **Không cài default handler rồi cho rằng đã bao phủ tất cả.**

### Bước 2 — Chọn nơi thu lỗi tương ứng

- **Thread thô:** handler riêng hoặc default.
- **Pool do mình tạo:** `ThreadFactory` gắn tên/handler, kết hợp quan sát kết quả task.
- **`submit`/`Future`:** supervisor đọc kết quả hoặc completion pipeline; bắt `ExecutionException` và giữ cause.
- **`CompletableFuture`:** `whenComplete`, `handle`, `exceptionally` hoặc `get/join` có kiểm soát.
- **Framework-managed:** callback/filter/error hook riêng (HTTP, scheduling, messaging) để giữ ngữ cảnh nghiệp vụ.

### Bước 3 — Định nghĩa cấu trúc event và alert

Chọn chuẩn timestamp, service/build/env, thread name/ID, exception type, cause/stack, task ID, correlation ID và tác động. Thiết kế mức severity và cảnh báo dựa trên tần suất/tác động, đồng thời hạn chế trùng log giữa lớp task và global handler.

### Bước 4 — Tái hiện có kiểm soát

Dùng chương trình lab ở phần 6 và một task lỗi ở môi trường test. Kiểm chứng ba điều:

1. Handler riêng nhận lỗi của thread riêng và default không ghi đúp.
2. Default nhận lỗi của thread không có handler riêng trong cơ chế `ThreadGroup` mặc định.
3. Lỗi từ `submit` xuất hiện qua `Future.get` và không bị bỏ quên chỉ vì handler worker không chạy.

Đừng gây OOM, native crash hoặc kill production chỉ để xem handler có ghi log không; những đường đó vốn không có bảo đảm.

### Bước 5 — Kiểm tra dưới workload có thực

Quan sát số event, độ trễ logging, event loss, chi phí I/O, quota log và tác động của lỗi lặp. Với pool, theo dõi worker count, queue depth, task failures và throughput; handler event một mình không đủ để xác nhận hệ thống đã khôi phục.

### Bước 6 — Kết luận và theo dõi

Báo cáo rõ những **đường lỗi đã bao phủ**, đường chưa bao phủ, tín hiệu/dữ liệu đã thấy, giới hạn và cách phát hiện sự cố còn lại. Sau khi sửa nguyên nhân, chạy test hồi quy tại đúng điều kiện kích hoạt và xem metric/log/alert để xác nhận thay đổi.

## 13. Mẫu cấu trúc event phục vụ chẩn đoán

Ví dụ minh họa một event đã loại bỏ thông tin nhạy cảm:

```json
{
  "timestamp": "2026-10-29T08:00:00Z",
  "service": "invoice-service",
  "environment": "staging",
  "build": "demo-build-17",
  "event": "uncaught_thread_exception",
  "thread_name": "invoice-worker-2",
  "thread_id": 18,
  "exception_type": "java.lang.IllegalStateException",
  "message": "invoice missing",
  "trace_id": "synthetic-trace-001",
  "task_id": "synthetic-task-123",
  "severity": "ERROR",
  "recovery_state": "worker_terminated"
}
```

Đây chỉ là **cấu trúc minh họa**, không phải output tự động của `UncaughtExceptionHandler`; các giá trị trace/task ID phải thực sự được gắn từ ngữ cảnh công việc, không được tự suy hoặc chế khi thiếu. Trong triển khai thật, thêm exception stack trace/cause theo trường hoặc logging attachment thích hợp. `thread_id` là ví dụ, không mang nghĩa ID cố định trên mọi lần chạy.

Một số liệu kiện khác nên theo dõi:

```text
uncaught_thread_exceptions_total{service, component, exception_type}
background_task_failures_total{service, executor, task_type}
worker_restarts_total{service, component}
```

Đây là **tên metric gợi ý**; không phải metric mặc định JVM tự xuất. Khi thiết kế label, tránh đưa message, request ID hoặc task ID vào nhãn metric có số lượng giá trị vô hạn gây bùng nổ cardinality. Những ID riêng nên nằm trong log/trace, không phải label Prometheus có cardinality cao.

## 14. Các lỗi triển khai phổ biến

1. **Cài default handler rồi nghĩ đã thu mọi lỗi trong pool.** `FutureTask` và `CompletableFuture` thường giữ exception, không làm worker chết.
2. **Chỉ log `getMessage()`.** Có thể mất exception type, stack trace, cause và suppressed exceptions quan trọng.
3. **Ghi đè handler của framework.** Có thể phá chính sách giám sát, logging hay crash reporting hiện có.
4. **Nhầm `ThreadGroup` với default handler.** `getUncaughtExceptionHandler()` có thể trả group, không phải object từ `Thread.getDefaultUncaughtExceptionHandler()`.
5. **Gọi default handler thủ công từ handler khác mà không chặn recursion.** Một đường delegation có thể quay về chính nó hoặc tạo log trùng.
6. **Tin rằng handler khôi phục thread.** Handler chạy khi thread sắp kết thúc, không làm `Runnable` tiếp tục.
7. **Bỏ rơi `Future` sau `submit`.** Task thất bại nhưng không ai lấy kết quả hoặc báo alert.
8. **Gắn request context không rõ vòng đời vào pool thread.** MDC/ThreadLocal có thể thiếu hoặc mang dữ liệu của task trước.
9. **Ghi full request/token vào log lỗi.** Có thể lộ dữ liệu riêng; che bí mật và giới hạn dữ liệu.
10. **Log đồng bộ nặng ngay trong handler.** Một thread đã gặp lỗi nghiêm trọng có thể tiếp tục block khi gọi mạng, lấy lock hoặc flush file lớn.
11. **Tạo log không giới hạn khi lỗi lặp.** Gây I/O và disk pressure, làm sự cố trầm trọng thêm.
12. **Xem `OutOfMemoryError` như một trường hợp logging chắc chắn.** Memory có thể quá thiếu để tạo event.
13. **Xem exit code/process kill như một uncaught Java exception.** Kernel kill, `halt` và native crash không bảo đảm gọi handler.
14. **Giả định mất một worker là toàn process chết.** Nhiều thread còn chạy; cần health/restart policy riêng.
15. **Không phân biệt stderr và stdout khi kiểm thử.** Fallback mặc định thường in stacktrace ra stderr, còn demo tự in stdout.
16. **Thiếu test trên đúng con đường thực tế.** Thread tự tạo, executor `execute`, `submit`, scheduler và CompletableFuture có cách báo lỗi khác nhau.
17. **Lấy tên thread làm ID nghiệp vụ.** Pool tái sử dụng thread cho nhiều task; cần correlation ID theo từng task.
18. **Không báo tình trạng hồi phục.** Thu exception là bước đầu; cần biết task đã thất bại, được retry hay vẫn nằm trong queue.

## 15. Tự kiểm tra kiến thức

1. Một `Thread` ném `IllegalStateException` không bắt. JVM gọi API nào và handler nhận hai tham số gì?
2. Khi một thread đã cài handler riêng, default handler có tự động nhận cùng exception không? `ThreadGroup` đóng vai trò gì khi không có handler riêng?
3. Vì sao `thread.getUncaughtExceptionHandler()` có thể trả một `ThreadGroup` trong khi `Thread.getDefaultUncaughtExceptionHandler()` là handler do ứng dụng cài?
4. Vì sao exception trong `ExecutorService.submit` thường không xuất hiện ở handler của worker? Người dùng `Future` cần xử lý exception qua phương thức nào?
5. `Executor.execute` ném `RejectedExecutionException` trên thread gọi. Có phải lỗi đó mặc định thuộc về handler của worker không?
6. Một handler chỉ ghi `error.getMessage()` với giá trị null. Bạn cần bổ sung những trường nào để có thể điều tra?
7. Nếu `OutOfMemoryError` nảy sinh, có thể bảo đảm logger trong handler ghi event thành công không? Vì sao?
8. Handler ghi lỗi trên thread `scheduler-1`, nhưng process còn phục vụ HTTP. Những metric/task state nào bạn phải kiểm tra để đánh giá tác động?
9. Kết quả `CompletableFuture.join()` bị lỗi được báo qua kiểu exception nào trong tình huống thất bại thông thường? Vì sao global handler có thể không nhận?
10. Bạn sẽ kiểm tra như thế nào để đảm bảo task ID/trace ID ghi trong handler thực sự thuộc về task vừa thất bại, không phải ngữ cảnh còn sót từ task trước?
11. Vì sao `System.exit`, `SIGKILL` và native crash không được coi là những trường hợp handler sẽ thu thập đầy đủ?
12. Một lỗi xảy ra sau khi cài default handler mới nhưng không thấy event. Hãy nêu ít nhất bốn nguyên nhân khả dĩ mà không vội kết luận “không có lỗi”.

## Tài liệu tham khảo

- Oracle Java SE 17 — `Thread`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html
- Oracle Java SE 17 — `Thread.UncaughtExceptionHandler`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.UncaughtExceptionHandler.html
- Oracle Java SE 17 — `ThreadGroup`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadGroup.html
- Oracle Java SE 17 — `ThreadPoolExecutor`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- Oracle Java SE 17 — `ExecutorService`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html

**Ghi nhớ:** `UncaughtExceptionHandler` thu thập **Throwable thực sự thoát khỏi thread**, theo thứ tự handler riêng → nhóm thread → default. Nó rất hữu ích để không bỏ sót cái chết bất thường của thread, nhưng không thay cho việc quan sát `Future`, `CompletableFuture`, callback của framework hoặc lỗi kết thúc process. Bảo toàn stack trace, ngữ cảnh và thời điểm, đồng thời thiết kế chính sách khôi phục riêng cho công việc đã thất bại.