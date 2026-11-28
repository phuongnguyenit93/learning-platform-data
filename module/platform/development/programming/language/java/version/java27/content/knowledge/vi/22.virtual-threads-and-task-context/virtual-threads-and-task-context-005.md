# ThreadLocal trên virtual thread và chi phí dữ liệu theo luồng trong Java 27

Trong chương **Virtual threads và ngữ cảnh tác vụ**, một thay đổi quan trọng khi thiết kế ứng dụng Java là chuyển từ mô hình **một nhóm nhỏ platform thread được tái sử dụng** sang mô hình **mỗi tác vụ có thể được thực thi trên một virtual thread riêng**. Virtual thread đã là tính năng chính thức từ Java 21 và tiếp tục được hỗ trợ trong Java 27.

`ThreadLocal<T>` vẫn hoạt động trên virtual thread. Tuy nhiên, một cách sử dụng rất phổ biến trước đây — **dùng ThreadLocal làm cache cho mỗi worker thread** — có thể trở nên tốn bộ nhớ khi hệ thống tạo hàng chục nghìn virtual thread. Muốn thiết kế đúng, cần hiểu: giá trị `ThreadLocal` thực sự thuộc **thread nào**, tồn tại **bao lâu**, được tạo **khi nào** và có chi phí gì khi số lượng tác vụ tăng.

Bài học này tập trung vào `ThreadLocal`, `InheritableThreadLocal`, `ScopedValue`, vòng đời request/task, cách ước lượng bộ nhớ và chiến lược thay thế cache theo luồng trong **Java 27**. Những cách sử dụng phụ thuộc vào việc tái sử dụng worker thread không được xem là mặc định phù hợp với virtual thread.

## 1. Virtual thread và carrier thread là hai khái niệm khác nhau

Virtual thread là một `java.lang.Thread` được JVM quản lý với chi phí tạo và chờ thấp hơn platform thread trong nhiều workload I/O. Khi cần chạy mã Java, virtual thread có thể được **mount** lên một platform thread bên dưới (thường được gọi là *carrier*). Khi thực hiện một số thao tác blocking có hỗ trợ, JVM có thể **unmount** virtual thread để carrier làm công việc khác; sau đó virtual thread được mount trở lại, có thể lên một carrier khác.

```text
Virtual thread A (request A) ---- chạy ---- chờ I/O ---- tiếp tục ---- kết thúc
                                 |                       |
                              carrier #1             carrier #3

Virtual thread B (request B) ------------ chạy --------- chờ -------- kết thúc
                                           |
                                        carrier #2
```

Sơ đồ thể hiện khả năng chuyển carrier, không phải lịch trình bắt buộc. Mã ứng dụng **không được giả định** rằng một virtual thread luôn chạy trên cùng một carrier.

Những điểm nền tảng:

- Mỗi virtual thread vẫn có **danh tính Java thread riêng** và có thể dùng `Thread.currentThread()`, interruption, `join()` và `ThreadLocal`.
- Carrier thread **không phải chủ sở hữu logic** của các giá trị `ThreadLocal` trong virtual thread.
- Virtual thread có ích nhất với lượng lớn tác vụ thường phải chờ I/O. Nó không tự làm một thuật toán CPU-bound chạy nhanh hơn.
- Virtual thread **không được pool để tái sử dụng cho các request khác nhau**. Một tác vụ có thể có virtual thread riêng, thay vì mượn đi mượn lại một worker có số lượng giới hạn.

### 1.1. Điều gì xảy ra với `ThreadLocal` khi chuyển carrier?

Giá trị của `ThreadLocal` gắn với **virtual thread đang thực thi mã ứng dụng**, không phải gắn với carrier được sử dụng tại một thời điểm cụ thể. Nếu tác vụ đang xử lý request `R-42`:

```java
REQUEST_ID.set("R-42");
```

thì sau một đoạn chờ I/O, mã trên **cùng virtual thread** vẫn thấy `REQUEST_ID.get()` là `"R-42"` cho đến khi giá trị được thay đổi hoặc xóa. Điều đó đúng ngay cả khi JVM đổi carrier trong lúc chạy.

**Không nên tự thiết kế logic để “sao chép ThreadLocal giữa các carrier”.** Mô hình của Java đã bảo toàn thread-local state theo danh tính virtual thread.

## 2. `ThreadLocal<T>` hoạt động như thế nào?

`ThreadLocal<T>` là một khóa cho phép mỗi thread giữ một giá trị riêng. Một field `static final ThreadLocal<T>` chỉ có nghĩa **khóa được chia sẻ**, không có nghĩa **giá trị được chia sẻ giữa các thread**.

```java
private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();
```

Các thao tác quan trọng:

| API | Ý nghĩa |
| --- | --- |
| `get()` | Lấy giá trị gắn với thread hiện tại; nếu chưa có, có thể tạo giá trị ban đầu |
| `set(value)` | Gán giá trị mới cho thread hiện tại |
| `remove()` | Xóa giá trị ở thread hiện tại; lần `get()` tiếp theo có thể khởi tạo lại |
| `ThreadLocal.withInitial(supplier)` | Khai báo cách tạo giá trị khi thread gọi `get()` lần đầu sau khi chưa có giá trị |

Thông thường, `initialValue()` của `ThreadLocal` trả `null` nếu không được override. `withInitial` tiện hơn khi mỗi thread phải có một giá trị được khởi tạo theo nhu cầu.

```java
private static final ThreadLocal<Integer> COUNTER =
    ThreadLocal.withInitial(() -> 0);

static int increment() {
    int next = COUNTER.get() + 1;
    COUNTER.set(next);
    return next;
}
```

`COUNTER` ở trên **không phải** bộ đếm toàn cục. Mỗi thread có bộ đếm độc lập, thường bắt đầu từ `0`.

### 2.1. Vì sao `withInitial` không tạo sẵn một giá trị cho mọi thread?

Giá trị được khởi tạo khi thread đó thực sự gọi `get()` mà chưa có giá trị lưu, chứ không phải khi khai báo field `ThreadLocal`. Đây là **lazy initialization**.

```java
static final ThreadLocal<byte[]> BUFFER =
    ThreadLocal.withInitial(() -> new byte[64 * 1024]);
```

Việc khai báo `BUFFER` không cấp phát ngay 64 KiB cho hàng triệu thread. Nhưng nếu **10.000 virtual thread cùng gọi `BUFFER.get()` và giữ giá trị**, chúng có thể đồng thời giữ lượng payload đáng kể (xem mục 5).

### 2.2. `remove()` khác `set(null)` như thế nào?

```java
REQUEST_ID.set("R-42");
REQUEST_ID.remove();
```

`remove()` xóa entry gắn với thread hiện tại. Nếu `ThreadLocal` có `withInitial`, lần gọi `get()` sau có thể chạy supplier một lần nữa.

```java
static final ThreadLocal<String> LABEL =
    ThreadLocal.withInitial(() -> "initial");

LABEL.set(null);
System.out.println(LABEL.get()); // null (entry vẫn tồn tại)

LABEL.remove();
System.out.println(LABEL.get()); // initial (khởi tạo lại)
```

Không dùng `set(null)` làm cách thay thế mặc định cho `remove()`, nhất là khi giá trị thread-local có thể chứa tham chiếu đến object lớn hoặc tài nguyên có vòng đời riêng.

## 3. Ví dụ chạy được: mỗi virtual thread có ngữ cảnh riêng

```java
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class VirtualThreadLocalDemo {
    private static final ThreadLocal<String> REQUEST_ID =
        new ThreadLocal<>();

    private static String execute(String id) {
        REQUEST_ID.set(id);
        try {
            if (!Thread.currentThread().isVirtual()) {
                throw new IllegalStateException("Expected a virtual thread");
            }
            return "Processed " + REQUEST_ID.get();
        } finally {
            REQUEST_ID.remove();
        }
    }

    public static void main(String[] args) throws Exception {
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            Future<String> a = executor.submit(() -> execute("request-A"));
            Future<String> b = executor.submit(() -> execute("request-B"));

            System.out.println(a.get()); // Processed request-A
            System.out.println(b.get()); // Processed request-B
        }
    }
}
```

Diễn giải:

1. `newVirtualThreadPerTaskExecutor()` tạo **virtual thread mới cho mỗi task**, không dùng pool virtual thread.
2. Cả hai task cùng tham chiếu đến một **khóa** `REQUEST_ID`.
3. Hai virtual thread có **giá trị độc lập**: `"request-A"` và `"request-B"`.
4. `finally` gọi `remove()` dù phần thân gặp exception.
5. `Future.get()` chờ kết quả và truyền lỗi từ task theo contract của `Future`.
6. `ExecutorService.close()` đóng scope executor khi kết thúc `try-with-resources`.

Đây là ví dụ chứng minh **tính cô lập ngữ cảnh**. Nó không chứng minh scheduler đã đổi carrier — việc đổi carrier là chi tiết thực thi mà ứng dụng không cần dựa vào.

## 4. ThreadLocal gắn với virtual thread, không gắn với request theo định nghĩa

Thường gặp các tên như `requestIdThreadLocal`, `userContext` hoặc `transactionContext`. Tuy nhiên, **ThreadLocal luôn gắn với thread**, không có khái niệm nghiệp vụ “request” bên trong API này.

Nếu một request chạy hoàn toàn trên một virtual thread, hai vòng đời có thể gần tương đương. Nhưng nếu một request tách thành nhiều task/thread khác nhau, `ThreadLocal` **không tự truyền ngữ cảnh sang các thread mới**.

```java
private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

REQUEST_ID.set("R-42");

Thread child = Thread.ofVirtual().start(() -> {
    System.out.println(REQUEST_ID.get());
    // null: ThreadLocal thường không tự được kế thừa
});

child.join();
REQUEST_ID.remove();
```

`REQUEST_ID` ở child là giá trị của **child thread**, không phải của caller. Việc child chạy trên virtual thread không thay đổi quy tắc này.

### 4.1. Pipeline bất đồng bộ có thể làm mất ngữ cảnh ngầm

Đừng mặc định rằng các stage `CompletableFuture` hay callback của một thư viện sẽ chạy trên cùng virtual thread. Tác vụ có thể đổi thread ở ranh giới asynchronous API; ThreadLocal chỉ đọc dữ liệu của **thread thực sự chạy callback**.

Khi cần truyền context qua task boundary, các phương án rõ ràng hơn gồm:

- Truyền `RequestContext` như tham số.
- Tạo binding `ScopedValue` trong **chính task nhận context**, khi phù hợp.
- Dùng abstraction context propagation đã được framework hỗ trợ và hiểu rõ quy tắc capture/restore.

Không tự truy cập hoặc thao tác ThreadLocal của carrier để “khôi phục” request context.

## 5. Chi phí bộ nhớ của ThreadLocal theo số virtual thread

Với platform-thread pool nhỏ, một cache theo thread thường chỉ có số instance gần với kích thước pool. Với virtual thread-per-task, số instance có thể gần với **số task đang sống đã sử dụng cache**.

Gọi:

- `T` là số virtual thread **đang còn sống**.
- `K` là số `ThreadLocal` khác nhau mà mỗi thread đã truy cập.
- `V` là kích thước trung bình của object graph mà mỗi entry giữ.
- `M` là overhead cho thread-local map, entry, reference, alignment và cấu trúc liên quan.

Một ước lượng sơ bộ:

```text
ThreadLocal footprint ≈ T × K × V + M
```

Đây **không phải công thức đo heap chính xác**: mọi object không nhất thiết đều là bản sao độc lập, thread-local map có thể được cấp phát theo nhu cầu và JDK có thể tối ưu. Công thức hữu ích để nhận ra yếu tố **nhân theo số thread**.

### 5.1. Một con số đủ lớn để gây vấn đề

Giả sử ứng dụng có cache:

```java
private static final ThreadLocal<byte[]> CACHE =
    ThreadLocal.withInitial(() -> new byte[64 * 1024]);
```

Nếu có **10.000 virtual thread đang sống** và tất cả đã gọi `CACHE.get()`, riêng 10.000 mảng `byte[]` 64 KiB chiếm khoảng:

```text
10.000 × 64 KiB = 640.000 KiB ≈ 625 MiB
```

Con số này **chỉ tính payload của mảng**, chưa gồm header, padding, thread objects, stack chunks, các object khác, overhead của map và heap/GC. Nếu có thêm các ThreadLocal cache khác, mức giữ bộ nhớ có thể tăng đáng kể.

Một virtual thread đang chờ I/O có thể không dùng carrier nhưng vẫn **giữ các giá trị ThreadLocal** vì chính virtual thread đó còn sống.

### 5.2. Đừng nhầm số request tổng cộng với số thread đồng thời

Nếu 1 triệu request được xử lý **tuần tự, từng request kết thúc nhanh**, 1 triệu virtual thread đã được tạo không có nghĩa 1 triệu thread cùng sống tại một thời điểm. Chi phí giữ đồng thời phụ thuộc số virtual thread **reachable và còn tồn tại** cùng các object chúng đang giữ.

Ngược lại, nếu 50.000 request đang chờ một downstream service chậm, 50.000 virtual thread có thể cùng sống và giữ context/cache, dù chỉ một số ít carrier đang chạy Java code tại một thời điểm.

Cần đo:

- Số lượng tác vụ/virtual thread đang sống.
- Kích thước object graph giữ trong ThreadLocal.
- Số lượng ThreadLocal được khởi tạo trên mỗi task.
- Thời gian chờ I/O, cancellation và thời gian hoàn tất task.
- Heap live set sau GC, allocation rate và GC pressure.

## 6. Vì sao cache object lớn theo ThreadLocal thường không hợp với virtual thread?

Trước đây, một số ứng dụng dùng `ThreadLocal` để cache formatter, buffer, parser hoặc connection vì worker thread đắt và thường được tái sử dụng để xử lý nhiều tác vụ.

Ví dụ cần **tránh dùng như mặc định** với virtual thread:

```java
// MINH HỌA ANTI-PATTERN: mỗi virtual thread có thể tạo một buffer lớn.
static final ThreadLocal<byte[]> PER_THREAD_BUFFER =
    ThreadLocal.withInitial(() -> new byte[128 * 1024]);

static int inspect(byte[] input) {
    byte[] buffer = PER_THREAD_BUFFER.get();
    // Giả định xử lý tạm...
    return Math.min(input.length, buffer.length);
}
```

Nếu mỗi task có virtual thread riêng, `PER_THREAD_BUFFER` tạo một cache cho **mỗi task** và rất ít cơ hội được tái sử dụng giữa các task. Đặt buffer trong ThreadLocal không tự làm object rẻ hơn; nó còn có thể kéo dài thời gian giữ bộ nhớ tới cuối đời thread hoặc tới khi `remove()`.

### 6.1. Các lựa chọn thay thế

| Nhu cầu thực sự | Lựa chọn thường phù hợp |
| --- | --- |
| Một object bất biến và thread-safe | Chia sẻ một instance, chẳng hạn `static final` |
| Bộ đệm nhỏ chỉ cần trong một phép xử lý | Biến cục bộ, cấp phát theo kích thước cần |
| Resource có lifecycle cụ thể như JDBC connection | Connection pool + `try-with-resources`, không cache connection theo virtual thread |
| Muốn giới hạn số yêu cầu tới downstream | `Semaphore`, rate limiter hoặc pool tài nguyên tương ứng |
| Object mutable nặng, phải được tái sử dụng có kiểm soát | Một object pool có giới hạn kích thước và chính sách acquire/release rõ |
| Read-only request context đi qua chuỗi method | Tham số tường minh hoặc `ScopedValue` |
| Context mutable bắt buộc gắn với thread | `ThreadLocal` có lifecycle/cleanup rõ, cân nhắc chi phí |

Không phải object pool lúc nào cũng tốt: nó thêm độ phức tạp, đồng bộ và nguy cơ rò rỉ tài nguyên. Ưu tiên API bất biến hoặc cấp phát đơn giản nếu chi phí đã đủ thấp.

### 6.2. Ví dụ formatter dùng chung

Khi chỉ cần định dạng thời gian, `DateTimeFormatter` là một object bất biến và thread-safe có thể chia sẻ:

```java
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;

public final class Formatters {
    private static final DateTimeFormatter ISO_UTC =
        DateTimeFormatter.ISO_OFFSET_DATE_TIME.withZone(ZoneOffset.UTC);

    public static String format(Instant instant) {
        return ISO_UTC.format(instant);
    }
}
```

Không cần `ThreadLocal<DateTimeFormatter>` chỉ để tránh tạo lại formatter ở mỗi task. Việc chia sẻ object bất biến giúp giảm số instance khi số virtual thread tăng cao.

## 7. Vòng đời đúng của ThreadLocal: `try/finally` và `remove()`

Nếu vẫn cần ThreadLocal cho mutable per-thread context, hãy đặt logic **set – use – remove** trong cùng scope rõ ràng:

```java
import java.util.Objects;

final class RequestScope {
    private static final ThreadLocal<String> ID = new ThreadLocal<>();

    static void run(String requestId, Runnable action) {
        Objects.requireNonNull(requestId);
        Objects.requireNonNull(action);

        ID.set(requestId);
        try {
            action.run();
        } finally {
            ID.remove();
        }
    }

    static String currentId() {
        return ID.get();
    }
}
```

Ví dụ:

```java
RequestScope.run("R-42", () ->
    System.out.println(RequestScope.currentId())
);
```

Điểm mạnh: nếu `action.run()` ném exception, `remove()` vẫn chạy. Trên **platform-thread pool được tái sử dụng**, cleanup đặc biệt quan trọng để ngăn request sau nhìn thấy ngữ cảnh của request trước. Trên virtual thread-per-task, việc không tái sử dụng thread loại bỏ một số rủi ro cross-request nhưng **không tự làm giá trị giữ trong thread biến mất khi task chưa kết thúc**.

### 7.1. Cẩn thận với lồng scope

Đoạn `RequestScope.run` ở trên phù hợp khi mỗi task chỉ có **một scope**. Nếu gọi lồng:

```java
RequestScope.run("outer", () -> {
    RequestScope.run("inner", () -> {
        // "inner"
    });
    // Sau khi inner kết thúc, ID.get() là null, KHÔNG trở về "outer".
});
```

`ThreadLocal.remove()` không tự khôi phục giá trị trước đó. Nếu buộc phải cho phép nested ThreadLocal scopes, bạn cần thiết kế logic lưu và **restore đúng cả trạng thái đã có hoặc chưa có giá trị**. Một biến `previous = get()` đơn giản không phân biệt chắc chắn “chưa có entry” với “entry chứa null”.

Khi yêu cầu là binding lồng nhau với việc **khôi phục tự động** và dữ liệu chỉ đọc, `ScopedValue` là một lựa chọn hợp lý hơn.

### 7.2. `remove()` không giải phóng tài nguyên mà object đang giữ

Nếu giá trị là `Connection`, `InputStream` hoặc một object triển khai `AutoCloseable`, xóa ThreadLocal **không thay thế** `close()`.

```java
// Giả sử connection được acquire riêng:
try (var connection = dataSource.getConnection()) {
    // Làm việc với connection trong scope của owner.
}
// close() trả connection về pool theo contract của pool.
```

Quyền sở hữu tài nguyên, cách đóng và thời gian sử dụng phải được kiểm soát độc lập với API `ThreadLocal`.

## 8. `InheritableThreadLocal` và chi phí sao chép sang thread con

`InheritableThreadLocal<T>` khác `ThreadLocal<T>` thông thường: khi tạo thread con, thread đó có thể nhận **các giá trị ban đầu** từ thread tạo nó.

```java
private static final InheritableThreadLocal<String> TRACE =
    new InheritableThreadLocal<>();

TRACE.set("trace-7");

try {
    Thread child = Thread.ofVirtual().start(() ->
        System.out.println(TRACE.get()) // trace-7
    );
    child.join();
} finally {
    TRACE.remove();
}
```

Giá trị được kế thừa khi **thread con được tạo**, không phải cơ chế đồng bộ live state giữa parent/child. Nếu parent đổi `TRACE` sau đó, child không tự thấy bản cập nhật với kiểu `String` bất biến.

### 8.1. Giá trị ban đầu không đồng nghĩa deep copy

Mặc định, `InheritableThreadLocal.childValue(parentValue)` trả chính reference từ parent. Nếu reference trỏ tới object mutable, parent và child có thể cùng quan sát hoặc thay đổi object đó.

```java
static final InheritableThreadLocal<java.util.List<String>> TAGS =
    new InheritableThreadLocal<>();

TAGS.set(new java.util.ArrayList<>());
Thread child = Thread.ofVirtual().start(() -> {
    // TAGS.get() mặc định có thể là CÙNG object List với parent.
});
```

Đây là vấn đề về **chia sẻ tham chiếu**, không được `InheritableThreadLocal` bảo đảm thread safety. Nếu cần tách biệt, cần copy có ý nghĩa hoặc chọn immutable context.

### 8.2. Có thể tắt kế thừa cho virtual thread

Java 27 hỗ trợ:

```java
Thread child = Thread.ofVirtual()
    .inheritInheritableThreadLocals(false)
    .start(() -> {
        // Không kế thừa giá trị TRACE của parent.
        System.out.println(TRACE.get()); // null nếu chưa tự gán
    });

child.join();
```

Theo `Thread.Builder`, mặc định có thể kế thừa giá trị InheritableThreadLocal khi tạo thread, nhưng **có thể opt out** bằng `inheritInheritableThreadLocals(false)`.

Không dùng `allowSetThreadLocals(false)` từ các ví dụ **preview rất cũ**: method này không có trong `Thread.Builder.OfVirtual` chính thức của Java 27. Khi kiểm tra hướng dẫn trên mạng, luôn đối chiếu Javadoc phiên bản đích.

### 8.3. Chi phí và ranh giới bảo mật

Việc kế thừa có thể phải sao chép cấu trúc ánh xạ ThreadLocal sang thread con; với rất nhiều task, overhead này đáng chú ý. Quan trọng hơn, việc tự động kế thừa auth context hoặc thông tin tenant có thể làm lan truyền dữ liệu sang những tác vụ không nên được cấp quyền.

Một codebase dùng `InheritableThreadLocal` nên có chính sách rõ:

- Dữ liệu nào thực sự cần được kế thừa?
- Có thể dùng immutable context không?
- Task mới có thuộc cùng trust boundary và request scope không?
- Có nên tắt kế thừa ở nơi tạo thread?
- Khi task kết thúc, ai dọn context/tài nguyên liên quan?

## 9. `ScopedValue`: cách biểu đạt context chỉ đọc có scope rõ ràng

**`java.lang.ScopedValue` đã là API chính thức từ Java 25**, vì vậy có thể dùng trực tiếp trong Java 27, không cần dựa vào mô tả preview cũ.

Khác với ThreadLocal dựa vào `set()`/`remove()`, ScopedValue gắn một **binding** vào khoảng thời gian chạy một đoạn code. Khi thoát đoạn code, binding cũ được khôi phục tự động, kể cả khi có exception.

```java
import java.lang.ScopedValue;

public class ScopedValueDemo {
    record RequestContext(String requestId, String tenantId) { }

    private static final ScopedValue<RequestContext> CONTEXT =
        ScopedValue.newInstance();

    static void service() {
        RequestContext ctx = CONTEXT.get();
        System.out.println(ctx.requestId() + " / " + ctx.tenantId());
    }

    static void handle(String requestId, String tenantId) {
        RequestContext ctx = new RequestContext(requestId, tenantId);

        ScopedValue.where(CONTEXT, ctx).run(() -> service());
        // Ra khỏi run: binding vừa tạo không còn hiệu lực.
    }

    public static void main(String[] args) {
        handle("R-42", "tenant-a");
    }
}
```

`RequestContext` được mô hình hóa bằng record gồm các `String` bất biến. **ScopedValue bảo vệ binding khỏi việc gán lại tùy tiện từ callee**, nhưng không tự biến một object mutable được bind thành immutable. Nếu bind một `ArrayList`, code được cấp reference vẫn có thể sửa nội dung list. Tốt nhất là truyền dữ liệu context read-only và immutable.

### 9.1. So sánh trực tiếp

| Tiêu chí | `ThreadLocal` | `ScopedValue` |
| --- | --- | --- |
| Đưa giá trị vào context | `set(value)` | `ScopedValue.where(key,value).run/call(...)` |
| Đọc trong cùng scope | `get()` | `get()` |
| Thay đổi binding từ callee | Có thể `set()` lại | Không có `set()` trên ScopedValue |
| Kết thúc scope | Caller phải `remove()` hoặc restore chủ động | Binding tự rời scope khi `run/call` kết thúc |
| Nested scope | Cần tự lưu và restore khi dùng ThreadLocal | Có rebinding lồng nhau, tự trở về binding ngoài |
| Giữ dữ liệu | Có thể giữ giá trị suốt đời thread | Binding có giới hạn theo phạm vi dynamic scope |
| Kế thừa giữa các task/thread | `InheritableThreadLocal` có quy tắc riêng | Có cơ chế kế thừa **trong structured task scope phù hợp** |
| Trường hợp điển hình | Mutable per-thread state khi thật sự cần | Truyền dữ liệu context chỉ đọc qua nhiều lớp gọi |

ScopedValue phù hợp với **one-way transmission**: caller cung cấp context, callee chỉ đọc và sử dụng. Khi callee thực sự cần thay đổi trạng thái trong cùng thread theo thời gian, ThreadLocal hoặc một object mutable được truyền tường minh có thể hợp với mô hình hơn.

### 9.2. Rebinding lồng nhau tự khôi phục

```java
private static final ScopedValue<String> REGION =
    ScopedValue.newInstance();

static void nested() {
    ScopedValue.where(REGION, "global").run(() -> {
        System.out.println(REGION.get()); // global

        ScopedValue.where(REGION, "asia").run(() -> {
            System.out.println(REGION.get()); // asia
        });

        System.out.println(REGION.get()); // global
    });
}
```

Không cần một biến `previous` hoặc `finally { remove(); }`. Ranh giới binding chính là ranh giới lời gọi `run`.

### 9.3. Đọc khi chưa được bind

Khi chưa có binding, `get()` không trả một giá trị mặc định tùy ý; nó có thể ném `NoSuchElementException`. Các API như `isBound()`, `orElse(other)` và `orElseThrow(...)` hỗ trợ viết logic rõ ràng.

```java
static String currentRegion() {
    return REGION.orElse("unknown");
}
```

Nếu một dịch vụ bắt buộc có context, hãy coi “not bound” là lỗi contract thay vì âm thầm biến thành một identity nào đó.

## 10. Truyền ScopedValue qua virtual thread mới: không tự động trong mọi trường hợp

ScopedValue **không phải** một global variable vô hình được mọi thread con tự kế thừa. Binding được chia sẻ qua các thread trong những **trường hợp có cấu trúc** được API hỗ trợ.

Trong Java 27, `StructuredTaskScope` vẫn được đánh dấu **preview**; cơ chế này hỗ trợ capture/inherit ScopedValue bindings theo contract khi fork child tasks trong scope. Nếu dự án không sử dụng preview, **đừng giả định** việc gọi `Thread.ofVirtual().start(...)` hoặc `ExecutorService.submit(...)` sẽ tự mang binding của parent sang child.

Cách không phụ thuộc preview: **truyền context rõ ràng tới task** và bind lại ở nơi task thực thi:

```java
import java.util.concurrent.Executors;

record RequestContext(String requestId) { }

static final ScopedValue<RequestContext> CTX = ScopedValue.newInstance();

static void childTask() {
    System.out.println(CTX.get().requestId());
}

static void submitTask(RequestContext context) throws Exception {
    try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
        var future = executor.submit(() -> {
            ScopedValue.where(CTX, context).run(() -> childTask());
        });
        future.get();
    }
}
```

Task mới nhận `context` qua captured lambda reference, sau đó **tự tạo binding trong chính virtual thread của task**. Đây là chiến lược rõ ràng cho code Java 27 không cần preview feature.

**Cẩn trọng:** nếu một context được chia sẻ cho nhiều task đồng thời, object đó phải bất biến hoặc được đồng bộ đúng cách. `ScopedValue` giữ reference, không thực hiện deep copy cho context.

## 11. Khi nào cần truyền context tường minh thay vì ambient context?

Mặc dù ThreadLocal và ScopedValue giúp giảm việc truyền tham số qua nhiều lớp, không phải mọi giá trị đều nên đặt trong ambient context.

Ví dụ các tham số nghiệp vụ quan trọng:

```java
Order calculatePrice(Order order, PriceRules rules);
```

thường nên được truyền **tường minh** để API dễ hiểu và kiểm thử. Trái lại, request ID phục vụ tracing hoặc tenant context đã được kiểm soát có thể là ứng viên cho ScopedValue nếu nhiều lớp trung gian chỉ cần đọc và không muốn thay đổi chữ ký của mọi method.

| Dữ liệu | Phương án nên ưu tiên |
| --- | --- |
| Số lượng và mã đơn hàng cho logic nghiệp vụ | Tham số phương thức |
| Logger hoặc formatter bất biến | Shared singleton/`static final` hợp lý |
| Request correlation ID qua nhiều lớp | ScopedValue hoặc context propagation được framework hỗ trợ |
| Authentication/tenant context | API context rõ và giới hạn quyền; ScopedValue có thể hỗ trợ nhưng **không thay thế authorization** |
| Mutable accumulator tạm thời trong một phép xử lý | Biến cục bộ hoặc object được truyền tường minh |
| JDBC connection/transaction | Resource lifecycle/transaction scope; tránh cache theo virtual thread |
| Buffer lớn | Cấp phát đúng vòng đời hoặc pool giới hạn kích thước có contract |
| State cần tồn tại qua nhiều thread và async boundary | Truyền rõ context/khai báo ownership; không trông cậy ThreadLocal thường |

### 11.1. Không để quyền truy cập bị che giấu

Nếu một method tự đọc `TenantContext.get()` từ ThreadLocal/ScopedValue mà không thể hiện trong chữ ký, người dùng API có thể không nhận ra nó phụ thuộc vào context. Hãy tài liệu hóa precondition, tổ chức điểm bind context ở boundary và viết test cho trường hợp chưa có context.

ThreadLocal và ScopedValue đều là **cơ chế truyền dữ liệu**, không phải mô hình phân quyền người dùng. Code đọc được tenant ID không có nghĩa nó tự động có quyền truy cập mọi dữ liệu của tenant đó.

## 12. Throttling tài nguyên: đừng giới hạn virtual thread bằng thread pool

Khi chuyển từ platform threads sang virtual threads, mục đích không phải tạo một pool nhỏ chứa 20 virtual threads để xử lý mọi task. Virtual threads đủ nhẹ để mô hình hóa **task**; những tài nguyên khan hiếm phải được kiểm soát trực tiếp.

Giả sử chỉ có tối đa 16 truy vấn đồng thời được phép gọi một downstream service:

```java
import java.util.concurrent.Semaphore;

final class RateLimitedClient {
    private final Semaphore permits = new Semaphore(16);

    String fetch(String key) throws InterruptedException {
        permits.acquire();
        try {
            return callDownstream(key);
        } finally {
            permits.release();
        }
    }

    private String callDownstream(String key) {
        return "value:" + key; // Thay bằng request I/O thật trong ứng dụng.
    }
}
```

Nhiều virtual threads có thể chờ ở semaphore mà không cần chiếm platform thread theo kiểu blocking truyền thống của một worker pool.

Nếu tài nguyên thực tế đã được quản lý bằng JDBC connection pool có giới hạn, pool đó **đã có cơ chế hạn chế concurrency cho resource tương ứng**; không nhất thiết chồng thêm một semaphore giống hệt nếu không có yêu cầu nghiệp vụ khác.

Quan trọng: `ThreadLocal<Connection>` không thay thế connection pooling. Connection còn có ownership, transaction scope và điều kiện dùng lại; `close()` phải được gọi đúng theo hợp đồng pool.

## 13. Chi phí không chỉ là byte[]: reference, map và retained object graph

Một số rủi ro memory footprint khó nhìn thấy từ type của ThreadLocal:

```java
static final ThreadLocal<RequestState> STATE = new ThreadLocal<>();

record RequestState(
    String requestId,
    java.util.List<Object> cachedResults,
    byte[] payload
) { }
```

`STATE` chỉ là một `ThreadLocal<RequestState>` nhưng `RequestState` có thể tham chiếu tới cả một **object graph**: list, result objects, payload array và nhiều kiểu dữ liệu khác. Khi tính memory, cần tính những object được **giữ reachable** thông qua chuỗi tham chiếu đó chứ không chỉ kích thước của `RequestState`.

Một context nhỏ cũng có thể vô tình giữ object lớn:

```java
// Không nên đặt toàn bộ HTTP request/session trong ambient context
// nếu code chỉ cần một requestId hoặc tenantId nhỏ.
```

Nếu có thể, chỉ truyền **các giá trị đã tách khỏi resource lớn** như `String requestId`, `UUID`, `Instant` hoặc một record immutable nhỏ.

### 13.1. Thời gian giữ object và GC pressure

Tác vụ chờ I/O lâu giữ virtual thread còn sống. Nếu thread có ThreadLocal values, chúng có thể vẫn reachable cho đến khi entry được xóa hoặc thread không còn reachable và GC xử lý.

Điều này có thể làm:

- Heap live set lớn hơn khi có nhiều task cùng chờ.
- Allocation rate tăng nếu mỗi task đều khởi tạo cache riêng.
- GC phải quét nhiều object hơn.
- Độ trễ hoặc throughput giảm vì bộ nhớ ứng dụng bị chiếm cho context không cần thiết.

Tuy nhiên, **một virtual thread không có ThreadLocal nào không tự chịu tất cả những chi phí như trên**. Không được nhân số thread với kích thước một cache mà không xác định cache đó có được truy cập/khởi tạo thực tế.

### 13.2. Static ThreadLocal và khả năng giữ giá trị

Javadoc `ThreadLocal` mô tả mỗi thread có tham chiếu ngầm tới bản sao giá trị của mình khi thread còn sống và ThreadLocal có thể truy cập. Với platform thread tồn tại lâu, đây là lý do phải chú trọng `remove()` và cache retention. Với virtual thread thường kết thúc sau một task, giá trị có thể trở thành GC-eligible khi thread kết thúc và không còn tham chiếu liên quan.

Không nên suy rằng chỉ vì `ThreadLocal` là field `static final` thì mọi giá trị của thread đã kết thúc sẽ mãi sống. Thời gian giữ thực tế phụ thuộc thread còn reachable, object graph và các tham chiếu khác.

## 14. ThreadLocal trong thư viện bên thứ ba và framework

Một thư viện có thể dùng ThreadLocal **ngầm** để giữ formatter, buffer, tracing context, transaction state hoặc dữ liệu parser. Chuyển sang virtual thread không tự sửa những cách dùng đó.

Checklist khi tích hợp:

1. Có ThreadLocal dùng để **cache object lớn** không?
2. Mỗi request/virtual thread có khiến cache được khởi tạo không?
3. Thư viện có `remove()`/close/clear context trong `finally` không?
4. Có giả định task luôn ở cùng platform worker không?
5. Context được truyền qua async API và callback theo cách nào?
6. Có dùng `InheritableThreadLocal` để truyền dữ liệu nhạy cảm tự động không?
7. Có thể dùng một singleton bất biến, object pool có giới hạn hoặc explicit context thay thế không?

Việc dùng virtual threads với thư viện async được thiết kế cho số worker nhỏ có thể làm bộc lộ các cache ThreadLocal trước đây chỉ có vài instance. Khi đánh giá hiệu năng, hãy quan sát **số instance/cấp phát thực tế**, không chỉ đọc tên API.

Không kết luận tất cả việc dùng ThreadLocal trong framework là sai. Một context nhỏ, được quản lý vòng đời đúng và chỉ được dùng khi cần có thể hoàn toàn hợp lý.

## 15. Điều tra bộ nhớ và tình trạng virtual thread

Java 27 có các công cụ giám sát để xác định vấn đề là lượng virtual thread sống quá lớn, context per-thread quá nặng, hay một nguyên nhân khác.

### 15.1. Các metric quan trọng

| Metric | Dùng để trả lời |
| --- | --- |
| Số request/task đang chạy hoặc chờ | Có bao nhiêu công việc cùng sống? |
| Số virtual thread được tạo/kết thúc theo thời gian | Có task nào không kết thúc theo kỳ vọng? |
| Heap used sau GC | Live set có tăng cùng concurrency không? |
| Allocation rate | Có bao nhiêu object mới được tạo mỗi request? |
| Heap histogram / heap dump | `byte[]`, `RequestState`, wrapper nào giữ nhiều bộ nhớ? |
| Connection pool active/pending | Task đang kẹt vì tài nguyên downstream? |
| I/O latency, timeout, cancellations | Vì sao virtual thread tồn tại lâu hơn dự kiến? |

Một heap dump lớn có thể chứa request data, token hoặc PII. Chỉ thu thập trong môi trường được cấp quyền và bảo vệ artifact.

### 15.2. Thread dump hiện đại

JDK có lệnh xuất thread dump phù hợp với virtual threads:

```text
jcmd -l
jcmd <pid> Thread.dump_to_file -format=json threads.json
```

Có thể phân tích xem nhiều virtual thread đang chờ ở cùng vị trí, ví dụ chờ semaphore, JDBC connection pool hoặc network operation. Thread dump **không trực tiếp đo tổng byte[] giữ trong ThreadLocal**; muốn biết heap retention cần thêm heap profiling hoặc heap dump.

### 15.3. Flight Recorder và heap profiling

JDK Flight Recorder (JFR) có thể quan sát allocation, execution, blocking và một số sự kiện virtual thread tùy cấu hình recording:

```text
jcmd <pid> JFR.start name=TaskContext settings=profile duration=60s filename=task-context.jfr
```

Phân tích recording bằng Java Mission Control hoặc công cụ được hỗ trợ. Nếu nghi ThreadLocal giữ payload lớn, đo allocation theo class/call path và quan sát object retention bằng công cụ heap phù hợp.

**Không mặc định JFR tự liệt kê đầy đủ mọi ThreadLocal key/value trong mọi virtual thread.** Cần đối chiếu số thread, object allocation, heap retention, thời gian sống task và call path cụ thể.

### 15.4. Đo trước và sau thay đổi

Một quy trình hợp lý:

1. Chạy workload xác định, ghi concurrency, throughput, p95/p99 latency, heap used, allocation rate và GC pauses.
2. Tìm `ThreadLocal.withInitial`/`set` được gọi trên đường xử lý phổ biến; xác định phần nào tạo object lớn.
3. Thay cache bằng singleton immutable, local allocation hoặc pool giới hạn đúng nơi cần.
4. Giữ nguyên workload và đo lại.
5. Kiểm tra kết quả nghiệp vụ và context isolation, không chỉ bộ nhớ.
6. Đánh giá tác động khi downstream chậm hoặc nhiều task bị treo.

Các con số như “virtual thread chỉ tốn X byte” không phải contract cố định của Java. Memory footprint chịu ảnh hưởng của stack depth, JDK, GC, object graph, context và workload.

## 16. Kiểm thử cách ly ngữ cảnh và cleanup

Một test tích hợp tốt cần phát hiện **giá trị lẫn giữa request**, mất context ở child task và cleanup không đầy đủ.

### 16.1. Ví dụ kiểm tra cô lập trên nhiều virtual thread

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class VirtualThreadContextTest {
    private static final ThreadLocal<Integer> ID = new ThreadLocal<>();

    static int task(int id) {
        ID.set(id);
        try {
            int observed = ID.get();
            if (observed != id) {
                throw new AssertionError("Context leak: " + observed);
            }
            return observed;
        } finally {
            ID.remove();
        }
    }

    public static void main(String[] args) throws Exception {
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            List<Future<Integer>> results = new ArrayList<>();

            for (int i = 0; i < 100; i++) {
                final int id = i;
                results.add(executor.submit(() -> task(id)));
            }

            for (int i = 0; i < results.size(); i++) {
                if (results.get(i).get() != i) {
                    throw new AssertionError("Wrong task identity");
                }
            }
        }

        System.out.println("Context isolation passed");
    }
}
```

Test xác minh các task đọc đúng giá trị đã tự gán trong virtual thread của mình. Test này **không đo heap footprint** và không chứng minh không có rò rỉ memory; cần bổ sung test tài nguyên/benchmark nếu muốn kiểm chứng hai mục tiêu đó.

### 16.2. Kiểm tra ThreadLocal không tự kế thừa

```java
ThreadLocal<String> local = new ThreadLocal<>();
local.set("parent");

try {
    Thread child = Thread.ofVirtual().start(() -> {
        if (local.get() != null) {
            throw new AssertionError("Unexpected ThreadLocal inheritance");
        }
    });
    child.join();
} finally {
    local.remove();
}
```

**Lưu ý:** exception ném trong một thread riêng **không tự được truyền** qua `Thread.join()` sang caller. Để biến ví dụ thành assertion chắc chắn, dùng `Future.get()`/`ExecutorService` hoặc `AtomicReference<Throwable>` để thu lỗi từ child. Đoạn trên chỉ minh họa vị trí kiểm tra, không nên xem là một unit test đáng tin cậy.

### 16.3. Kiểm tra nested ScopedValue

```java
private static final ScopedValue<String> TEST_ID =
    ScopedValue.newInstance();

static void verifyNestedBinding() {
    ScopedValue.where(TEST_ID, "outer").run(() -> {
        if (!"outer".equals(TEST_ID.get())) {
            throw new AssertionError();
        }

        ScopedValue.where(TEST_ID, "inner").run(() -> {
            if (!"inner".equals(TEST_ID.get())) {
                throw new AssertionError();
            }
        });

        if (!"outer".equals(TEST_ID.get())) {
            throw new AssertionError("Binding was not restored");
        }
    });

    if (TEST_ID.isBound()) {
        throw new AssertionError("Binding leaked outside scope");
    }
}
```

Ví dụ này kiểm tra chính đặc tính scope mà ThreadLocal thông thường không tự cung cấp.

## 17. Lỗi thường gặp và hướng sửa

| Sai lầm | Vì sao không đúng | Hướng xử lý |
| --- | --- | --- |
| “ThreadLocal của virtual thread nằm trên carrier” | Giá trị gắn với virtual `Thread`, không phải worker/carrier | Dựa vào `Thread.currentThread()` theo logic task |
| Dùng ThreadLocal để giữ buffer lớn cho mọi virtual thread | Cache nhân theo số task đồng thời, ít cơ hội reuse giữa task | Dùng shared immutable object, local buffer hoặc pool có giới hạn |
| Nghĩ virtual thread kết thúc là object được GC ngay | Reachability/GC không có deadline cố định | Quản lý task lifecycle, tránh giữ các thread/result không cần |
| Quên `remove()` khi dùng platform-thread pool | Request sau có thể thấy context cũ | `try/finally` và ownership rõ |
| Dùng `remove()` để đóng JDBC connection | Xóa entry không gọi `close()` trên connection | `try-with-resources` và pool contract |
| Nghĩ `InheritableThreadLocal` sao chép sâu object | Mặc định có thể giữ cùng mutable reference | Immutable context hoặc copy đúng nghĩa |
| Dùng `ThreadLocal` thường rồi mong child thread có giá trị | ThreadLocal thường không kế thừa | Truyền context tường minh hoặc dùng API propagation phù hợp |
| Cho rằng ScopedValue được mọi executor thread tự thừa kế | Kế thừa bị giới hạn theo structured propagation | Bind context trong task hoặc dùng structured scope phù hợp |
| Binding `ScopedValue` với một object mutable và coi nó immutable | Chỉ binding không đổi; nội dung object vẫn có thể sửa | Record/immutable context hoặc đồng bộ |
| Dùng `ThreadLocal` như global counter | Mỗi thread có một bản riêng | Dùng `AtomicLong`, `LongAdder` hoặc metric phù hợp |
| Chồng thêm thread pool để giới hạn virtual thread | Không trực tiếp giới hạn resource khan hiếm | Dùng semaphore/rate limiting/resource pool |
| Nghĩ nhiều virtual thread làm CPU xử lý nhanh hơn | Virtual threads hỗ trợ scale cho blocking workloads | Profile CPU bottleneck và chọn concurrency phù hợp |
| Lặp lại số request lịch sử làm số thread cùng sống | Thread đã kết thúc không còn giữ per-thread value khi GC-eligible | Đo concurrency và retention thực |
| Áp dụng method `allowSetThreadLocals` của bản preview cũ | Không có trong API Java 27 chính thức | Dùng `inheritInheritableThreadLocals(false)` nếu cần tắt kế thừa |
| Đọc một heap snapshot rồi kết luận leak | Có thể đang đo workload peak hợp lệ | Đo baseline sau khi task hoàn tất và so sánh nhiều lần |

## 18. Checklist lựa chọn context cho Java 27

Khi xây dựng dịch vụ dùng virtual threads, nên trả lời:

1. Dữ liệu cần truyền là **tham số nghiệp vụ**, hay chỉ là ngữ cảnh tracing/request?
2. Có thực sự cần mutable per-thread state không? Nếu không, có thể truyền tham số hoặc `ScopedValue` không?
3. Đã xác định **task boundary** chưa, đặc biệt khi dùng `ExecutorService`, callback hoặc async stage?
4. Có library nào dùng ThreadLocal để cache buffer/formatter/parser lớn không?
5. Nếu mỗi task đều gọi `ThreadLocal.get()`, tổng số object được tạo cùng lúc là bao nhiêu?
6. Giá trị ThreadLocal có giữ reference đến payload, session, connection hoặc object graph lớn không?
7. `set()` có được đi cùng `try/finally` và cleanup hợp lệ không?
8. Với nested context, có cần automatic rebinding/restore của `ScopedValue` không?
9. Nếu dùng `InheritableThreadLocal`, đã đánh giá sharing mutable reference và nguy cơ truyền context nhạy cảm không?
10. Tác vụ có bị giữ lâu vì I/O/connection pool không? Đã có timeout, cancellation và metric hợp lý chưa?
11. Có đang pool virtual threads chỉ để giới hạn concurrency thay vì giới hạn tài nguyên thực không?
12. Có đo heap, allocation và throughput bằng workload đại diện trước/sau khi đổi thiết kế không?

**Nguyên tắc kết luận:** `ThreadLocal` trên virtual thread vẫn đúng về ngữ nghĩa, nhưng chi phí của giá trị được giữ **nhân theo số virtual thread đang thực sự sử dụng nó**. Dùng `ThreadLocal` cho trạng thái nhỏ cần thay đổi theo thread khi thật sự cần; tránh dùng nó để cache object đắt đỏ chỉ vì thói quen từ worker pool. Với dữ liệu ngữ cảnh chỉ đọc cần scope rõ, **`ScopedValue` là lựa chọn hiện đại của Java 27**.

## Tài liệu tham khảo chính thức

- [Java SE 27 — Virtual Threads](https://docs.oracle.com/en/java/javase/27/core/virtual-threads.html): đặc tính của virtual thread, thread-per-task, carrier scheduling, lời khuyên tránh cache dữ liệu đắt đỏ trong ThreadLocal.
- [Java SE 27 API — `ThreadLocal<T>`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ThreadLocal.html): per-thread values, `get`, `set`, `remove`, `withInitial`.
- [Java SE 27 API — `InheritableThreadLocal<T>`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/InheritableThreadLocal.html): kế thừa giá trị ban đầu và `childValue`.
- [Java SE 27 API — `Thread.Builder.OfVirtual`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Thread.Builder.OfVirtual.html): tạo virtual thread, `inheritInheritableThreadLocals(false)`.
- [Java SE 27 API — `ScopedValue<T>`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ScopedValue.html): dynamic scope, rebinding, quyền truy cập binding và structured inheritance.
- [Java SE 27 API — `Executors`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Executors.html): `newVirtualThreadPerTaskExecutor`.
- [Java SE 27 API — `Semaphore`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Semaphore.html): giới hạn đồng thời theo tài nguyên.
- [Java SE 27 — `jcmd` Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jcmd.html): thread dump và Flight Recorder.
- [OpenJDK JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): rationale về virtual threads, ThreadLocal và khuyến nghị thiết kế.
- [OpenJDK JEP 506 — Scoped Values](https://openjdk.org/jeps/506): ScopedValue trở thành tính năng chính thức.
