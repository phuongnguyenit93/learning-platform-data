# Truyền context qua Runnable, Callable và executor trong Java

## 1. Bài toán: context đi theo tác vụ hay theo thread?

Trong chương trình đồng thời, **context** là dữ liệu cần mang theo để xử lý đúng một công việc: `requestId` / `traceId`, người khởi tạo, locale, thông tin phân vùng dữ liệu (tenant), thời hạn xử lý, hoặc dữ liệu phục vụ ghi log. Đây là *dữ liệu của tác vụ*, không đương nhiên là dữ liệu của thread chạy tác vụ.

Ví dụ: thread nhận yêu cầu A có `requestId="req-A"` và gọi:

```java
executor.submit(() -> processRequest());
```

`processRequest()` thường chạy trên một thread khác. Nếu nó đọc `ThreadLocal` do thread nhận yêu cầu A thiết lập thì mặc định nó **không thấy giá trị của thread A**. Với executor dùng thread pool, worker được tái sử dụng; giá trị `ThreadLocal` còn sót của một tác vụ trước đó còn có thể khiến tác vụ mới đọc **sai context** nếu không dọn dẹp.

Ba khái niệm cần tách biệt:

| Khái niệm | Trả lời câu hỏi | Tác động |
| --- | --- | --- |
| **Context payload** | Tác vụ cần dữ liệu gì? | Xác định các trường dữ liệu, tính bất biến, quyền truy cập |
| **Context capture** | Chụp dữ liệu ở thời điểm nào? | Thường tại lúc tạo/gửi tác vụ, trước khi chuyển sang thread khác |
| **Context activation/cleanup** | Khi task thực sự chạy, cài context vào thread nào và khôi phục ra sao? | Đảm bảo code bên trong đọc đúng dữ liệu, không rò sang task sau |

**Nguyên tắc ưu tiên:** nếu có thể, truyền một đối tượng context bất biến thành **tham số tường minh** cho hàm/tác vụ. Chỉ cần cơ chế context ngầm (`ThreadLocal`, thư viện logging MDC, ...) khi phải phục vụ các API sâu trong call stack không nhận tham số.

Phạm vi bài này là concurrency chuẩn của Java: `Runnable`, `Callable`, `Executor`, `ExecutorService`, `Future` và `ThreadLocal`. Mỗi thư viện tự quản lý context riêng có thể yêu cầu adapter riêng.

## 2. Runnable, Callable và ExecutorService thay đổi điều gì?

`Runnable` có phương thức `void run()`; nó không trả kết quả và không khai báo checked exception. `Callable<V>` có phương thức `V call() throws Exception`, cho phép trả kết quả hoặc báo lỗi có kiểm soát.

| Cách gửi việc | Giá trị nhận | Quan sát hoàn tất/lỗi |
| --- | --- | --- |
| `Executor.execute(Runnable)` | `void` | Không có `Future`; lỗi phụ thuộc executor/handler |
| `ExecutorService.submit(Runnable)` | `Future<?>` | `get()` trả `null` nếu thành công; lỗi của task được báo qua `ExecutionException` |
| `ExecutorService.submit(Runnable, V result)` | `Future<V>` | `get()` trả giá trị `result` đã cấp khi task thành công |
| `ExecutorService.submit(Callable<V>)` | `Future<V>` | `get()` trả kết quả từ `call()`; lỗi được bọc trong `ExecutionException` |
| `ExecutorService.invokeAll(Collection<Callable<V>>)` | Danh sách `Future<V>` | Mỗi phần tử phải được bọc context trước khi gửi |

Các API trên **chuyển việc sang một ranh giới thực thi bất đồng bộ**. Chúng không tự sao chép một `ThreadLocal` bất kỳ của caller sang worker. `submit()` có thể xếp hàng; task thực thi muộn hơn, lúc context của caller đã bị thay đổi hoặc dọn.

Có hai bảo đảm cần phân biệt:

- Với `ExecutorService`, các hành động xảy ra trước khi gửi task *happen-before* hành động của task; hành động của task *happen-before* lúc thread khác đọc kết quả bằng `Future.get()`.
- **Happens-before** giúp xuất bản dữ liệu đúng cách theo Java Memory Model, nhưng **không có nghĩa JVM chuyển các entry trong `ThreadLocal` sang thread thực thi task**. Đây là hai cơ chế khác nhau.

## 3. Cách đơn giản và an toàn nhất: context là tham số tường minh

Giả sử thông tin mỗi request được đóng gói bằng `record` (Java 16+):

```java
record RequestContext(String requestId, String actor) {}

static String handle(RequestContext context) {
    return context.requestId() + "/" + context.actor();
}
```

Khi tạo tác vụ, đưa context trực tiếp vào lambda:

```java
RequestContext snapshot = new RequestContext("req-42", "alice");
Future<String> future = executor.submit(() -> handle(snapshot));
String answer = future.get();
```

Đây là **đoạn minh họa đặt bên trong phương thức có biến `executor`**, không phải tệp chạy độc lập. `Runnable` cũng áp dụng tương tự:

```java
RequestContext snapshot = new RequestContext("req-43", "bob");
executor.execute(() -> audit(snapshot));
```

Ưu điểm: nguồn dữ liệu hiện ngay trong chữ ký, dễ kiểm thử, không phụ thuộc thread pool, không cần dọn `ThreadLocal`. Với async chain, mỗi stage có thể nhận `snapshot` qua lambda mà không phụ thuộc nơi chạy.

**Lưu ý về “snapshot”:** một `record` chỉ làm tham chiếu tới các trường thành phần bất biến theo nghĩa không gán lại; nếu trường là `Map` / `List` hoặc object mutable, bản thân object ấy vẫn thay đổi được. Hãy copy phòng thủ những trường mutable ở ranh giới tạo task nếu cần ảnh chụp ổn định, ví dụ `Map.copyOf(attributes)`. Tránh truyền đối tượng chứa thông tin có tuổi đời ngắn mà worker giữ sau khi request kết thúc.

## 4. Khi cần context ngầm: ThreadLocal là trạng thái của thread thực thi

`ThreadLocal<T>` có một giá trị độc lập cho **mỗi thread** truy cập nó. Trong cùng một thread, các hàm sâu trong call stack có thể đọc context mà không phải truyền tham số qua mọi tầng.

```java
private static final ThreadLocal<RequestContext> CURRENT =
        new ThreadLocal<>();
```

Lỗi điển hình khi sử dụng pool:

```java
CURRENT.set(new RequestContext("req-101", "alice"));
executor.submit(() -> log(CURRENT.get()));  // worker có thể đọc null
CURRENT.remove();                           // chỉ xóa giá trị của caller
```

Dòng `CURRENT.remove()` của caller **không dọn ThreadLocal của worker**. Nếu trước đây worker từng có context khác, `get()` của worker còn có thể trả giá trị cũ.

Để truyền context qua executor có thread pool, cần **chụp context trên thread gửi**, rồi **cài nó trên thread chạy task**, và **khôi phục đúng trạng thái trước khi trả worker về pool**:

```text
Caller thread                 Worker thread
  CURRENT = context-A
          |
   snapshot = CURRENT.get()
          |
     submit(wrapper) ----->  previous = CURRENT.get()
                             CURRENT.set(snapshot)
                             try { task.run()/call(); }
                             finally {
                                 restore(previous)
                             }
          |
   Caller tự quản lý          Worker sẵn sàng nhận task khác
   vòng đời context
```

Tại thời điểm worker bắt đầu chạy, không nên gọi lại `CURRENT.get()` của worker để “chụp” context của caller: lúc đó đã đứng ở **sai thread**. Cũng không nên giữ reference tới một object mutable trong suốt thời gian chờ hàng đợi rồi gọi đó là snapshot bất biến.

## 5. Hai wrapper đúng: Runnable và Callable

Có thể đóng gói cùng một quy tắc context scope cho cả hai interface. Thiết kế dưới đây giả định `null` là không có context và `CURRENT` là `new ThreadLocal<>()` không định nghĩa giá trị khởi tạo:

**Wrapper cho `Runnable`:**

```java
static Runnable withContext(Runnable task, RequestContext snapshot) {
    return () -> {
        RequestContext previous = CURRENT.get();
        if (snapshot == null) CURRENT.remove();
        else CURRENT.set(snapshot);

        try {
            task.run();
        } finally {
            if (previous == null) CURRENT.remove();
            else CURRENT.set(previous);
        }
    };
}
```

**Wrapper cho `Callable<V>`:**

```java
static <V> Callable<V> withContext(
        Callable<V> task, RequestContext snapshot) {
    return () -> {
        RequestContext previous = CURRENT.get();
        if (snapshot == null) CURRENT.remove();
        else CURRENT.set(snapshot);

        try {
            return task.call();
        } finally {
            if (previous == null) CURRENT.remove();
            else CURRENT.set(previous);
        }
    };
}
```

Đây là **hai đoạn phương thức**, cần đặt trong class có `CURRENT` và import `Runnable` / `Callable` thích hợp. Ví dụ chương trình độc lập ở phần tiếp theo ghép đầy đủ tất cả thành phần.

Tại sao cần từng bước?

1. `previous = CURRENT.get()`: ghi lại context đã hiện diện trên **worker**, có thể là của scope bên ngoài trong một lời gọi lồng nhau.
2. `CURRENT.set(snapshot)` hoặc `remove()`: áp context của task mới; snapshot `null` phải có nghĩa “không có context”, tránh dùng giá trị cũ.
3. `try`: chạy công việc, bất kể trả kết quả hay ném ngoại lệ.
4. `finally`: luôn khôi phục giá trị cũ. Nếu trước đó không có giá trị thì dùng `remove()` để tránh lưu trạng thái thừa suốt đời thread pool.

**Vì sao restore thay vì luôn remove?** Nếu một task gọi một hàm khác cũng kích hoạt context tạm thời trên cùng thread, wrapper bên trong phải trả lại context của wrapper bên ngoài. Còn với pool worker có context rỗng ban đầu, restore sẽ dẫn đến `remove()`.

Không nên dùng chung một `ThreadLocal` cho dữ liệu mutable của nhiều request rồi sửa trực tiếp cùng object. Việc set một object ở hai thread không biến object đó thành thread-safe; concurrency safety của dữ liệu vẫn cần thiết.

## 6. Ví dụ Java 21 hoàn chỉnh, có kết quả xác định

Chương trình sau dùng **một platform worker** (`newFixedThreadPool(1)`) để chứng minh cả hai loại task có thể nhận context riêng, sau đó worker trở về trạng thái không có context. Ví dụ cố ý đợi bằng `Future.get()` trước mỗi lần in để stdout không phụ thuộc thứ tự lập lịch.

Tạo tệp **ContextPropagationDemo.java**:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicReference;

public class ContextPropagationDemo {
    record RequestContext(String requestId, String actor) {}

    private static final ThreadLocal<RequestContext> CURRENT =
            new ThreadLocal<>();

    static Runnable withContext(Runnable task, RequestContext snapshot) {
        return () -> {
            RequestContext previous = CURRENT.get();
            if (snapshot == null) CURRENT.remove();
            else CURRENT.set(snapshot);
            try {
                task.run();
            } finally {
                if (previous == null) CURRENT.remove();
                else CURRENT.set(previous);
            }
        };
    }

    static <V> Callable<V> withContext(
            Callable<V> task, RequestContext snapshot) {
        return () -> {
            RequestContext previous = CURRENT.get();
            if (snapshot == null) CURRENT.remove();
            else CURRENT.set(snapshot);
            try {
                return task.call();
            } finally {
                if (previous == null) CURRENT.remove();
                else CURRENT.set(previous);
            }
        };
    }

    static String describe() {
        RequestContext c = CURRENT.get();
        return c.requestId() + "/" + c.actor();
    }

    public static void main(String[] args) throws Exception {
        RequestContext a = new RequestContext("req-101", "alice");
        RequestContext b = new RequestContext("req-202", "bob");

        try (ExecutorService executor = Executors.newFixedThreadPool(1)) {
            Future<String> call = executor.submit(
                    withContext(() -> "Callable: " + describe(), a));
            System.out.println(call.get());

            AtomicReference<String> output = new AtomicReference<>();
            Future<?> run = executor.submit(
                    withContext(
                            () -> output.set("Runnable: " + describe()), b));
            run.get();
            System.out.println(output.get());

            Future<Boolean> cleared =
                    executor.submit(() -> CURRENT.get() == null);
            System.out.println("Context cleared: " + cleared.get());
        }
    }
}
```

Biên dịch/chạy bằng **JDK 21+**:

```bash
javac ContextPropagationDemo.java
java ContextPropagationDemo
```

**Stdout chính xác:**

```text
Callable: req-101/alice
Runnable: req-202/bob
Context cleared: true
```

Phân tích:

- `call` là `Callable<String>`. Snapshot `a` được truyền cùng wrapper từ caller; dữ liệu được cài trên worker khi `call()` bắt đầu, rồi được dọn trong `finally`.
- `run` là `Runnable`. Nó ghi chuỗi kết quả vào `AtomicReference`, main đợi `Future.get()` trước khi in. Không cần ép `Runnable` có kiểu trả về.
- Bài dùng pool một worker để chắc chắn tác vụ kiểm tra có cơ hội quan sát **chính worker đã chạy hai task trước đó**; `Context cleared: true` xác nhận cleanup trong trường hợp này.
- `try (ExecutorService ...)` yêu cầu JDK 19+ vì `ExecutorService` hỗ trợ `AutoCloseable` từ Java 19; JDK 21 là lựa chọn ổn định cho chương trình này.
- `Future.get()` vừa chờ hoàn thành vừa cho phép quan sát exception trong task. Nếu một task ném lỗi, `finally` vẫn chạy trước khi `get()` ném `ExecutionException`.

Ví dụ chứng minh cách cài/khôi phục context; nó không được dùng làm benchmark cho throughput hoặc latency của executor.

## 7. Context capture ở đúng thời điểm

Điểm dễ sai nhất là **capture muộn**. So sánh:

**Sai: capture trong task chạy trên worker**:

```java
executor.submit(() -> {
    RequestContext snapshot = CURRENT.get(); // đọc ThreadLocal của worker
    handle(snapshot);
});
```

**Đúng: capture trước khi submit**:

```java
RequestContext snapshot = CURRENT.get(); // trên caller
executor.submit(withContext(() -> handle(CURRENT.get()), snapshot));
```

Hai đoạn trên giả định đã có `executor`, `CURRENT` và `handle(...)` trong scope; chúng minh họa ranh giới capture, không phải tệp biên dịch độc lập.

Những chi tiết tác động đến tính đúng:

- **Queue delay**: task có thể khởi chạy sau vài giây/phút; capture lúc `submit` đem đúng dữ liệu liên quan tới tác vụ ban đầu.
- **Mutable context**: snapshot kiểu tham chiếu vẫn có thể đổi nội dung; hãy tạo object bất biến/copy giá trị liên quan trước khi submit.
- **Cancellation**: nếu task chưa chạy và bị hủy, wrapper chưa kích hoạt context; không có trạng thái worker cần restore. Nếu đang chạy và bị interrupt, `finally` vẫn là nơi cleanup đáng tin.
- **Rejected submission**: `RejectedExecutionException` xảy ra trước khi wrapper thực thi. Context caller phải được quản lý theo scope của caller, không mong chờ cleanup của worker.
- **Nested submission**: nếu task đang có `context-A` rồi gửi tiếp một task mới, cần capture lại `A` ở thời điểm gửi; executor mới không tự kế thừa context của task cha.
- **Timeout**: `future.get(timeout, unit)` timeout chỉ ảnh hưởng caller đợi; bản thân task **không tự dừng**. Cần quyết định hủy/interrupt và tính nhất quán của dữ liệu context.

## 8. Bọc Executor.execute và giới hạn của decorator

Nếu mã có nhiều nơi gọi `execute(Runnable)`, có thể bọc ở cấp `Executor` để mỗi lệnh được capture tự động:

```java
static Executor contextAware(Executor delegate) {
    return command -> {
        RequestContext snapshot = CURRENT.get(); // đang ở caller
        delegate.execute(withContext(command, snapshot));
    };
}
```

Đây là **phương thức minh họa**, cần import `java.util.concurrent.Executor` và dùng cùng `CURRENT`/`withContext` đã định nghĩa. Đặt wrapper khi cấu hình dependency:

```java
Executor decorated = contextAware(underlyingExecutor);
decorated.execute(() -> performWork());
```

Ở đây `snapshot` được lấy **mỗi lần gọi `execute`**, không lấy một lần khi tạo `decorated`. Nếu chụp lúc tạo wrapper, các task của những request khác nhau sẽ cùng dùng context sai.

**Giới hạn rất quan trọng:** `Executor` chỉ có `execute`. Wrapper trên **không tự mang các API** `submit`, `invokeAll`, `schedule` hoặc `CompletableFuture.supplyAsync` của những interface khác. Đừng ép kiểu wrapper thành `ExecutorService`. Có ba lựa chọn:

1. Với `ExecutorService`, bọc trực tiếp từng `Runnable`/`Callable` trước `submit` hoặc trước khi tạo collection cho `invokeAll`.
2. Nếu cần “decorate toàn bộ service”, triển khai một adapter `ExecutorService` hoàn chỉnh, bao phủ mọi đường gửi task, shutdown, exception, scheduling (nếu là `ScheduledExecutorService`). Một wrapper chỉ ghi đè `execute` có thể không bao phủ phương thức chuyên biệt của delegate.
3. Nếu có thể sửa API nghiệp vụ, tiếp tục ưu tiên truyền `RequestContext` như tham số; cách này không cần decorator.

Dùng `CompletableFuture`:

```java
RequestContext snapshot = CURRENT.get();
CompletableFuture<String> result =
        CompletableFuture.supplyAsync(() -> handle(snapshot), executor);
```

Đoạn trên **truyền tường minh** snapshot trong lambda; `supplyAsync` không tự mang `ThreadLocal` của caller. Với chuỗi `thenApplyAsync` / `thenComposeAsync`, cần xem **mỗi stage chạy ở executor nào**, từ đâu được kích hoạt và liệu nó đọc context ngầm không. Không mặc định chain sẽ kế thừa context vì stage trước có giá trị đúng.

## 9. Lỗi phổ biến khi truyền context qua executor

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Cài `ThreadLocal` trên caller rồi tin worker sẽ đọc được | Worker thấy `null` hoặc dữ liệu của task khác | Truyền tham số hoặc capture/activate đúng trên worker |
| Đọc `CURRENT.get()` lần đầu bên trong lambda trên worker | Capture sai thời điểm và thread | Capture **trước submit** |
| `set()` nhưng không `remove()`/restore trong `finally` | Context rò sang task sau, đặc biệt nguy hiểm với trace/user/tenant | Restore giá trị trước đó trong `finally` |
| Luôn `remove()` mà không giữ `previous` | Phá scope bên ngoài khi wrapper lồng nhau | Save/restore trạng thái worker |
| Giữ một `HashMap` mutable làm snapshot giữa các request | Data race hoặc thông tin thay đổi trong lúc chờ | Copy bất biến / giới hạn ownership |
| Bọc `execute` rồi cho rằng đã tự bọc `submit`, `invokeAll`, `schedule` | Đường gửi task khác bỏ qua propagation | Bọc từng API đúng loại hoặc làm adapter đầy đủ |
| Không gọi `Future.get()` khi cần phát hiện lỗi | Exception trong `submit` có thể nằm trong `Future` mà không được báo | Quan sát `Future`, xử lý `ExecutionException` |
| Sử dụng `InheritableThreadLocal` với pool và kỳ vọng mỗi task thừa kế | Giá trị chỉ liên quan lúc tạo child thread, không phải mỗi lần submit task | Propagation có chủ đích tại task boundary |
| Giữ context có secrets/đối tượng nặng qua task kéo dài | Tăng nguy cơ lộ dữ liệu và giữ tham chiếu không cần thiết | Chỉ chuyển các trường tối thiểu, hạn chế lifetime |

### Phân biệt InheritableThreadLocal, virtual threads và ScopedValue

- `InheritableThreadLocal` chuyển giá trị khởi tạo ở **thời điểm tạo thread con** theo quy tắc của Java; worker thread pool đã tạo từ trước không tự nhận giá trị mới của mỗi lần `submit`. Thêm nữa, mutable value được kế thừa bằng tham chiếu vẫn có thể chia sẻ trạng thái ngoài ý muốn.
- Virtual thread vẫn là một `Thread` Java và vẫn hỗ trợ `ThreadLocal`. Mô hình “một virtual thread cho một tác vụ” giảm một số nguy cơ tái sử dụng thread của pool, nhưng **không biến task của một executor bất kỳ thành con logic được tự động truyền mọi context**. Đừng trộn vòng đời thread với ranh giới request.
- `ScopedValue` được hoàn thiện trong **JDK 25** (JEP 506), hữu ích để truyền dữ liệu chỉ đọc theo **dynamic scope**. Với việc gửi task bất kỳ sang executor, vẫn phải xác định rõ cách tạo binding trên thread chạy task; một binding của caller không tự lan sang mọi executor. Đây là lựa chọn bổ sung của Java hiện đại, không phải điều kiện để chạy ví dụ Java 21 ở trên.

Ví dụ JDK 25+ với `ScopedValue` (đoạn minh họa, không độc lập):

```java
static final ScopedValue<RequestContext> CTX =
        ScopedValue.newInstance();

RequestContext snapshot = currentContext;
executor.execute(() ->
        ScopedValue.where(CTX, snapshot).run(() -> performWork()));
```

`ScopedValue.where(...).run(...)` tạo binding chỉ trong thời gian `run`. Quy tắc truy cập và truyền cho child tasks của structured concurrency phải theo tài liệu phiên bản JDK tương ứng.

## 10. Kiểm thử và quan sát đường truyền context

Nên kiểm thử cả **đúng dữ liệu** lẫn **không còn dữ liệu**:

1. Cho hai tác vụ có context khác nhau chạy nối tiếp trên **cùng một worker**; kiểm tra task B không đọc lẫn context A.
2. Cho một task ném exception khi đã activate context; sau khi `Future.get()` báo lỗi, gửi task kiểm tra ThreadLocal rỗng.
3. Với wrapper lồng nhau, xác nhận context phía ngoài được **khôi phục** sau khi scope trong đóng.
4. Với thread pool nhiều worker và task trộn lẫn requestId, thêm test concurrent/stress để phát hiện tham chiếu mutable chia sẻ sai.
5. Với queue delay, thay đổi context trên caller sau `submit` và xác nhận task vẫn dùng snapshot đã capture.
6. Kiểm tra nhánh `RejectedExecutionException`/cancellation, và bảo đảm không giữ context không cần thiết.

Đối với logging, nên gắn `requestId` của context vào bản ghi khi task chạy; mỗi tác vụ phải quan sát đúng ID của chính nó. Nếu dùng MDC của thư viện logging, MDC thường dựa trên thread-local riêng: việc propagate một biến `CURRENT` **không tự động propagate toàn bộ MDC**. Mỗi hệ thống context có cách snapshot, restore và cleanup riêng.

Không nên ghi dữ liệu xác thực nhạy cảm vào log chỉ để debug propagation. Những ID dùng để tương quan có thể được log tùy chính sách; credential/token nên có đường quản lý riêng.

## 11. Chọn chiến lược nào?

| Nhu cầu | Chiến lược đề xuất | Lý do |
| --- | --- | --- |
| Nắm quyền sửa chữ ký hàm nghiệp vụ | `handle(context)`, lambda capture giá trị bất biến | Dễ đọc, dễ test, không có trạng thái ngầm |
| Legacy API sâu cần “current context” | Wrapper `Runnable`/`Callable` với `ThreadLocal`, restore trong `finally` | Tương thích call stack hiện tại, tránh rò context |
| Nhiều lệnh `execute` | Decorate `Executor` với snapshot tại thời điểm từng lần `execute` | Giảm lặp mã ở caller |
| Dùng cả `submit`, `invokeAll`, scheduling | Bọc tác vụ tại từng API hoặc adapter đầy đủ | Không bỏ sót đường chạy |
| Async chain qua nhiều executor | Truyền context tường minh cho từng stage hoặc decorator có coverage xác định | Không dựa vào giả định chain kế thừa ngầm |
| Java 25+ cần context chỉ đọc trong dynamic scope | Cân nhắc `ScopedValue`, vẫn làm rõ task boundary | Scope rõ hơn, tránh mutable thread-local kéo dài |

Bộ câu hỏi tự kiểm tra:

1. **Vì sao đặt `ThreadLocal` trong caller trước `submit` không đủ?** Vì `ThreadLocal` gắn với từng thread và task có thể chạy trên worker khác.
2. **Snapshot nên tạo lúc nào?** Lúc caller xây/gửi task; activation xảy ra sau, trên worker khi task thực thi.
3. **Vì sao restore `previous` thay vì chỉ remove?** Vì wrapper có thể được gọi lồng nhau trên cùng thread; scope bên ngoài phải giữ nguyên context của nó.
4. **Có thể suy ra ThreadLocal được truyền qua `Future.get()` happens-before không?** Không. Happens-before đảm bảo thứ tự hiển thị bộ nhớ, không sao chép state theo thread.
5. **Wrapper `Executor.execute` có tự hỗ trợ `ExecutorService.submit` không?** Không. `Executor` chỉ công bố `execute` và phải kiểm soát riêng các API khác.

## 12. Tài liệu chuẩn

- [Java SE 21 — ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html): `submit`, `invokeAll`, `Future` và bảo đảm memory consistency.
- [Java SE 21 — Runnable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Runnable.html) và [Callable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Callable.html): hợp đồng thực thi task.
- [Java SE 21 — ThreadLocal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ThreadLocal.html): giá trị theo thread, `get`/`set`/`remove`.
- [Java SE 21 — InheritableThreadLocal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/InheritableThreadLocal.html): giới hạn kế thừa ở thời điểm tạo thread.
- [Java SE 25 — ScopedValue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.html) và [JEP 506](https://openjdk.org/jeps/506): context binding kiểu scope trên Java hiện đại.

