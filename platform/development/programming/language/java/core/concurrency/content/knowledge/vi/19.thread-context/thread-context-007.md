# ThreadLocal khi chạy hàng nghìn virtual threads trong Java 21+

`ThreadLocal<T>` cho phép mỗi thread lưu và đọc **giá trị riêng của thread đó**, không phải truyền giá trị qua mọi tham số gọi hàm. Virtual threads từ Java 21 vẫn hỗ trợ `ThreadLocal` như platform threads. Nhưng khi số virtual thread tăng từ vài chục lên hàng nghìn hoặc hàng triệu, những giả định về cache, tuổi thọ và tái sử dụng thread có thể khiến ứng dụng tiêu thụ nhiều bộ nhớ không cần thiết.

Phạm vi bài này là **Java concurrency thuần**, không phụ thuộc Spring. Chúng ta sẽ quan sát context riêng của từng virtual thread, biết cách truyền context qua ranh giới thread, giải phóng binding, nhận diện chi phí bộ nhớ của `withInitial(...)` và lựa chọn thay thế.

## 1. Nguyên lý của ThreadLocal

| API | Hành vi |
|---|---|
| `get()` | Đọc bản sao giá trị của **thread hiện tại**; nếu chưa có, khởi tạo bằng `initialValue()` (mặc định `null`). |
| `set(value)` | Đặt giá trị của **thread hiện tại**; không đặt giá trị cho thread khác. |
| `remove()` | Xóa binding của thread hiện tại; `get()` về sau có thể gọi lại initializer. |
| `ThreadLocal.withInitial(supplier)` | Tạo `ThreadLocal` với supplier khởi tạo **lười**, được gọi riêng trên từng thread khi `get()` lần đầu. |

Biến `static final ThreadLocal<String> TRACE` là một **khóa chung** để tra cứu, nhưng giá trị `TRACE.get()` nằm trong trạng thái từng thread. Nếu thread A gọi `TRACE.set("A")` thì thread B không đương nhiên thấy `"A"`.

Virtual thread vẫn là đối tượng `java.lang.Thread`. Dữ liệu `ThreadLocal` gắn vào **virtual thread đang chạy code**, không gắn vào carrier thread — platform thread tạm thực thi virtual thread.

~~~text
                 static final ThreadLocal<String> TRACE
                                  |
            cùng một khóa, binding riêng theo từng thread
                                  |
         +------------------------+--------------------+
         |                        |                    |
  Virtual Thread V1        Virtual Thread V2      Main Thread
  TRACE = "req-1"          TRACE = "req-2"        TRACE = "caller"
         |
      carrier A
         |
     chờ I/O tương thích -> virtual thread unmount
         |
      carrier B
      TRACE vẫn là "req-1" của V1
~~~

Khi virtual thread unmount khỏi một carrier và resume trên carrier khác, **binding của nó không mất và không biến thành binding của carrier**. Ngược lại, truyền công việc sang **virtual thread khác** có thể làm mất context nếu không truyền rõ ràng.

## 2. Ví dụ runnable: ba virtual thread, ba request ID

Lưu file **`ThreadLocalVirtualDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ThreadLocalVirtualDemo {
    private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

    private static String nestedCall() {
        return REQUEST_ID.get();
    }

    public static void main(String[] args) throws Exception {
        REQUEST_ID.set("caller");
        try {
            System.out.println("caller=" + REQUEST_ID.get());

            try (ExecutorService executor =
                         Executors.newVirtualThreadPerTaskExecutor()) {

                List<Future<String>> futures = new ArrayList<>();

                for (int id = 1; id <= 3; id++) {
                    final int taskId = id;
                    futures.add(executor.submit(() -> {
                        String before = REQUEST_ID.get();
                        REQUEST_ID.set("req-" + taskId);
                        try {
                            return "task-" + taskId
                                    + " before=" + before
                                    + " nested=" + nestedCall()
                                    + " virtual="
                                    + Thread.currentThread().isVirtual();
                        } finally {
                            REQUEST_ID.remove();
                        }
                    }));
                }

                for (Future<String> future : futures) {
                    System.out.println(future.get());
                }
            }

            System.out.println("caller-after=" + REQUEST_ID.get());
        } finally {
            REQUEST_ID.remove();
        }
    }
}
~~~

Biên dịch/chạy bằng JDK 21+:

~~~bash
javac ThreadLocalVirtualDemo.java
java ThreadLocalVirtualDemo
~~~

Stdout:

~~~text
caller=caller
task-1 before=null nested=req-1 virtual=true
task-2 before=null nested=req-2 virtual=true
task-3 before=null nested=req-3 virtual=true
caller-after=caller
~~~

Điều quan sát được:

1. `main` gán `"caller"` vào `ThreadLocal` của main thread.
2. Mỗi `executor.submit(...)` tạo một **virtual thread mới**. `ThreadLocal` thông thường **không tự kế thừa** giá trị từ thread đã submit, vì vậy `before=null`.
3. Trong từng task, `set("req-N")` tạo binding riêng. `nestedCall()` đọc đúng giá trị đó dù không nhận tham số, vì nó vẫn chạy **trên cùng virtual thread**.
4. `finally { REQUEST_ID.remove(); }` xóa binding của virtual thread, không xóa `"caller"` trên main thread.
5. Các task chạy/hoàn thành theo lịch không xác định; stdout có thứ tự ổn định vì vòng `for` gọi `Future.get()` theo thứ tự danh sách.

**Bài học:** mang context theo call stack **trong một thread** là khả năng của `ThreadLocal`. Muốn đi **sang thread mới**, cần truyền context chủ động.

## 3. Vì sao số lượng virtual thread thay đổi chi phí bộ nhớ?

Trong `Executors.newFixedThreadPool(16)`, nhiều task tái sử dụng 16 platform worker threads. Một `ThreadLocal` khởi tạo cache theo worker có thể tạo khoảng 16 object nếu mỗi worker truy cập. Nhưng `Executors.newVirtualThreadPerTaskExecutor()` tạo **một virtual thread mới trên mỗi task**; các virtual threads không được pool để chạy nhiều task khác nhau. Vì vậy cache theo thread được cấp phát **lặp lại trên từng task**.

Ví dụ một anti-pattern (snippet, không phải chương trình độc lập):

~~~java
static final ThreadLocal<byte[]> PER_THREAD_BUFFER =
        ThreadLocal.withInitial(() -> new byte[64 * 1024]);

void process() {
    byte[] buffer = PER_THREAD_BUFFER.get();
    // Dùng buffer ở đây ...
}
~~~

Nếu **10.000 virtual threads đang sống đồng thời** và mỗi thread đã `get()` buffer 64 KiB, chỉ riêng dữ liệu mảng có kích thước danh nghĩa **625 MiB** (`10_000 × 64 KiB`), chưa tính object header, thread stack, map hoặc object khác. Đây chỉ là phép tính minh họa, **không phải đo peak heap của JVM**. Với task hoàn tất nhanh, GC có thể thu hồi nhiều buffer; với task chờ I/O lâu, rất nhiều buffer có thể còn sống đồng thời.

Phân biệt hai chỉ số:

- **Số lần cấp phát trong toàn bộ thời gian chạy**: tăng theo số virtual thread có gọi `get()` của `ThreadLocal`.
- **Bộ nhớ còn giữ tại một thời điểm**: phụ thuộc bao nhiêu virtual thread còn sống đang tham chiếu buffer, và độ lớn của các object reachable.

`ThreadLocal.withInitial(...)` là **lazy**: chỉ khai báo key không tạo 10.000 object ngay. Nhưng mỗi thread gọi `get()` lần đầu tạo một giá trị mới, kể cả khi thread khác đã có giá trị.

Đặc biệt tránh dùng `ThreadLocal` để cache `SimpleDateFormat`, buffer lớn hoặc connection với kỳ vọng tái sử dụng giữa nhiều task trên **một virtual thread**; điều đó không xảy ra với mô hình thread-per-task. Ưu tiên `DateTimeFormatter` bất biến chia sẻ, quản lý resource theo scope, hoặc pool thật sự cho tài nguyên đắt (ví dụ DB connection pool). Không dùng `ThreadLocal` làm cơ chế giới hạn số request vào downstream.

## 4. Ví dụ runnable: 1.000 task tạo 1.000 buffer

Tạo file **`ThreadLocalAllocationDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public class ThreadLocalAllocationDemo {
    private static final AtomicInteger CREATED = new AtomicInteger();

    private static final ThreadLocal<byte[]> BUFFER =
            ThreadLocal.withInitial(() -> {
                CREATED.incrementAndGet();
                return new byte[1024];
            });

    public static void main(String[] args) throws Exception {
        int tasks = 1_000;

        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {

            List<Future<?>> futures = new ArrayList<>();

            for (int i = 0; i < tasks; i++) {
                futures.add(executor.submit(() -> {
                    try {
                        BUFFER.get()[0] = 1;
                    } finally {
                        BUFFER.remove();
                    }
                }));
            }

            for (Future<?> future : futures) {
                future.get();
            }
        }

        System.out.println("tasks=" + tasks);
        System.out.println("buffer-initializations=" + CREATED.get());
    }
}
~~~

Chạy:

~~~bash
javac ThreadLocalAllocationDemo.java
java ThreadLocalAllocationDemo
~~~

Stdout:

~~~text
tasks=1000
buffer-initializations=1000
~~~

`CREATED` dùng `AtomicInteger` để đếm chính xác giữa các task đồng thời. Mỗi task được chạy trên virtual thread mới, gọi `BUFFER.get()` một lần, nên supplier được chạy đúng **1.000 lần**. `remove()` dọn binding của từng thread nhưng **không tạo cơ chế tái sử dụng** buffer cho thread khác.

Nếu bỏ `BUFFER.get()`, supplier sẽ không chạy; nếu gọi `remove()` rồi `get()` lần nữa **trên cùng thread**, supplier được gọi lại. Không dùng thời gian chạy của ví dụ nhỏ để kết luận hiệu năng ứng dụng thực tế.

## 5. Phạm vi sống của giá trị và cleanup đúng cách

Một `ThreadLocal<String>` nhỏ chứa trace ID hoặc correlation ID có thể hợp lý khi rất nhiều hàm sâu trong cùng một task cần biết context, nhưng không muốn truyền tham số qua toàn bộ thư viện cũ.

Mẫu task sở hữu binding từ đầu đến cuối:

~~~java
// Snippet minh họa bên trong một Runnable; TRACE đã khai báo.
TRACE.set(traceId);
try {
    handleTask();
} finally {
    TRACE.remove();
}
~~~

Với context lồng nhau, khi code được gọi trong thread **đã có** giá trị, cần tránh xóa nhầm binding của caller:

~~~java
// Snippet: lưu và khôi phục nếu hợp đồng quy định null là "không có".
String previous = TRACE.get();
TRACE.set(traceId);
try {
    handleTask();
} finally {
    if (previous == null) {
        TRACE.remove();
    } else {
        TRACE.set(previous);
    }
}
~~~

Đây chỉ là snippet; `handleTask()` và `TRACE` do code gọi cung cấp. Nếu dùng `ThreadLocal.withInitial(...)`, lệnh `get()` để chụp `previous` có thể tự khởi tạo giá trị; lựa chọn mô hình binding phù hợp với ngữ nghĩa default/absent của ứng dụng.

Dùng `try/finally` để cleanup cả đường đi return, exception, retry, timeout hoặc cancellation. Lợi ích:

- Giải phóng tham chiếu đến dữ liệu (kể cả object graph lớn) ngay khi task không còn cần.
- Đảm bảo một thao tác sau trên **cùng thread** không đọc nhầm context cũ.
- Tương thích an toàn hơn nếu thư viện cũng được dùng trên **platform thread pool**: worker tái sử dụng dễ khiến binding task trước rò sang task tiếp theo nếu quên `remove()`.
- Giữ ranh giới lifecycle của request/task rõ ràng.

**Không khẳng định mọi ThreadLocal trên virtual thread đều rò rỉ vĩnh viễn:** khi virtual thread kết thúc và các giá trị không còn reference khác, chúng có thể được GC thu hồi. Rủi ro chính là **quá nhiều thread đang sống đồng thời giữ object**, hoặc object bị giữ thêm bởi reference ngoài. `remove()` giúp dọn sớm, nhưng không thay thế backpressure, timeout và giới hạn số task outstanding.

`set(null)` không giống `remove()`: `set(null)` đặt một binding có giá trị `null`; `remove()` bỏ binding và lần `get()` sau có thể gọi initializer lại.

## 6. Truyền context qua ranh giới thread

`ThreadLocal` thường **không truyền** giá trị của thread gửi task sang virtual thread. Đây là ví dụ snippet:

~~~java
TRACE.set("trace-A");
try (var executor =
        java.util.concurrent.Executors.newVirtualThreadPerTaskExecutor()) {
    var future = executor.submit(() -> TRACE.get());
    // future.get() sẽ là null nếu thread mới chưa đặt TRACE.
}
~~~

Phương án rõ nhất là **capture giá trị bất biến rồi truyền tham số**:

~~~java
// Snippet: traceId và process(String) được khai báo ở nơi gọi.
final String capturedTraceId = traceId;
try (var executor =
        java.util.concurrent.Executors.newVirtualThreadPerTaskExecutor()) {
    var future = executor.submit(() -> process(capturedTraceId));
    future.get();
}
~~~

Nếu API kế thừa chỉ đọc `ThreadLocal`, hãy wrap từng task để `set()` **bên trong thread thực thi**, sau đó cleanup bằng `finally`. Nếu wrapper có thể lồng nhau thì phải lưu/khôi phục giá trị trước đó theo hợp đồng của ứng dụng.

Đừng nhầm việc **virtual thread thay carrier** với **công việc chuyển sang virtual thread khác**. Trường hợp đầu không làm đổi `ThreadLocal`. Trường hợp sau cần truyền context rõ ràng. Khi dùng `CompletableFuture`, callbacks, worker pools hoặc executor khác, hãy xác định chính xác đoạn nào chạy trên thread nào trước khi dựa vào context ẩn.

## 7. InheritableThreadLocal kế thừa như thế nào?

`InheritableThreadLocal<T>` khác `ThreadLocal<T>` ở chỗ có thể đưa **giá trị ban đầu** của parent thread vào child thread **khi tạo thread**. Với `Thread.Builder`, hành vi mặc định là kế thừa; có thể tắt bằng `inheritInheritableThreadLocals(false)`.

Tạo file **`InheritableVirtualDemo.java`**:

~~~java
public class InheritableVirtualDemo {
    private static final InheritableThreadLocal<String> CONTEXT =
            new InheritableThreadLocal<>();

    public static void main(String[] args) throws Exception {
        CONTEXT.set("from-parent");
        try {
            Thread inherited = Thread.ofVirtual().start(() ->
                    System.out.println("inherited=" + CONTEXT.get()));
            inherited.join();

            Thread isolated = Thread.ofVirtual()
                    .inheritInheritableThreadLocals(false)
                    .start(() ->
                            System.out.println("isolated=" + CONTEXT.get()));
            isolated.join();
        } finally {
            CONTEXT.remove();
        }
    }
}
~~~

Chạy:

~~~bash
javac InheritableVirtualDemo.java
java InheritableVirtualDemo
~~~

Stdout:

~~~text
inherited=from-parent
isolated=null
~~~

`inherited.join()` đảm bảo dòng đầu được in trước khi tạo và đợi thread thứ hai. Với `inheritInheritableThreadLocals(false)`, child không nhận binding `"from-parent"`. Một child đã tạo **không được tự đồng bộ mọi lần parent đổi giá trị** sau đó.

Cảnh báo quan trọng: `InheritableThreadLocal.childValue(parentValue)` mặc định trả **cùng reference**. Nếu value là một `ArrayList` hoặc một object mutable, parent và child có thể cùng tham chiếu object đó dù mỗi thread có binding riêng. Không có deep copy tự động. Việc tự động kế thừa nhiều binding qua hàng nghìn thread cũng có thể tăng chi phí và mang theo dữ liệu ngoài ý muốn; không chuyển toàn bộ `ThreadLocal` thành `InheritableThreadLocal` để “sửa” mọi vấn đề propagation.

## 8. Thay thế phù hợp với nhu cầu và phiên bản JDK

| Nhu cầu | Lựa chọn | Ưu điểm |
|---|---|---|
| Chỉ vài hàm cần request/trace ID | Tham số hoặc `record RequestContext(...)` bất biến | Dòng dữ liệu rõ, dễ test |
| Thư viện cũ đọc context sâu trong cùng task | `ThreadLocal` nhỏ, cleanup bằng `finally` | Tương thích Java 21 |
| Context chỉ đọc, có lexical scope | `ScopedValue` theo phiên bản JDK | Giới hạn vòng đời binding và giảm chi phí |
| Formatter bất biến dùng lại ở nhiều task | `static final DateTimeFormatter` | Dùng chung an toàn, không cấp phát cache per thread |
| Tài nguyên hữu hạn (DB connection) | Connection pool, `Semaphore`, backpressure | Giới hạn đúng nguồn lực |

`ScopedValue` là **preview API từ JDK 21**, tiếp tục được phát triển trong các preview tiếp theo và **chính thức ở JDK 25** (JEP 506). Cú pháp dưới đây là **snippet dành cho JDK 25+**, không phải chương trình Java 21 chạy mặc định:

~~~java
private static final ScopedValue<String> TRACE = ScopedValue.newInstance();

ScopedValue.where(TRACE, "trace-123").run(() -> {
    System.out.println(TRACE.get());
});
// Bên ngoài run() không còn binding của scope này.
~~~

Trong một ngữ cảnh khai báo hợp lệ, đoạn trên in `trace-123`. `ScopedValue` thích hợp với context **chỉ đọc bên trong một phạm vi gọi hàm**, và có cơ chế kế thừa có kiểm soát với structured concurrency. Không mặc định giả định binding sẽ tự truyền cho **bất kỳ** `executor.submit(...)` nào. Với JDK 21 không dùng preview, ưu tiên truyền tham số hoặc `ThreadLocal` có lifecycle rõ.

## 9. Kiểm tra và tối ưu hệ thống hàng nghìn virtual threads

Trước khi chuyển thư viện sang virtual threads hoặc tối ưu `ThreadLocal`, cần đo những điều thực sự ảnh hưởng tải:

1. Mỗi giá trị `ThreadLocal` giữ **bao nhiêu byte**, và có đang tham chiếu đến buffer/cache/connection/object graph lớn không?
2. Có bao nhiêu **virtual thread đang sống đồng thời**, không chỉ tổng số task xử lý từ lúc ứng dụng khởi động?
3. Supplier của `withInitial(...)` được gọi bao nhiêu lần; có tạo object đắt cho **mỗi task** không?
4. Đường đi thành công, exception, timeout, cancel, retry đã cleanup/restore đúng ngữ cảnh chưa?
5. Có context nào bị mất khi bước qua ranh giới `CompletableFuture`, thread mới hoặc executor khác?
6. DB/network/connection pool có thời hạn và giới hạn rõ; producer có backpressure trước khi submit hàng loạt không?

Dùng JFR, allocation profiler, heap dump, heap usage/GC metrics, số task outstanding và p95/p99 latency dưới tải thực tế. Nếu thấy nhiều byte array/cache object còn sống thông qua virtual-thread context, xác định **ai tạo và ai giữ** giá trị đó trước khi sửa. Thư viện bên thứ ba cũng có thể tạo thread-local cache ngầm.

### Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Tưởng binding theo carrier | Sai về context khi JVM remount | Binding gắn với virtual thread |
| Dùng `withInitial` để cache buffer lớn per thread | Hàng nghìn lần cấp phát và có thể giữ heap lớn | Dùng immutable shared object, cấp phát theo scope |
| Không cleanup context | Giữ data lâu, hoặc rò task trước trên worker pool | `try/finally` và `remove()`/restore |
| Nghĩ `ThreadLocal` tự truyền sang thread mới | Task con đọc `null` | Capture và truyền tham số/wrap task |
| Kế thừa mutable object qua `InheritableThreadLocal` | Parent/child có thể dùng chung object không an toàn | Truyền immutable, kiểm soát inheritance |
| Dùng `set(null)` thay `remove()` | Không tái khởi tạo theo ngữ nghĩa mong đợi | Bỏ binding bằng `remove()` |
| Submit lượng task vô hạn chờ DB | Nhiều virtual thread giữ memory và queue | Backpressure, limit, timeout |
| Dùng API `ScopedValue` JDK 25 trên JDK 21 mặc định | Không biên dịch | Phân biệt preview 21 và finalized 25 |

## 10. Tự kiểm tra

**Câu 1:** Virtual thread chuyển từ carrier A sang B. `ThreadLocal` có đổi thành giá trị của B không? **Không.** Dữ liệu thuộc virtual thread.

**Câu 2:** `ThreadLocal.withInitial(() -> new byte[65536])` được `get()` trên 10.000 virtual threads. Có một buffer dùng chung không? **Không.** Có thể tạo 10.000 buffer riêng; peak heap còn phụ thuộc số virtual thread/buffer sống cùng lúc.

**Câu 3:** Một virtual thread kết thúc nhưng chưa `remove()`. Có luôn rò vĩnh viễn không? **Không.** Giá trị có thể được GC thu hồi khi không còn reference giữ. Cleanup sớm vẫn nên làm.

**Câu 4:** Main thread `TRACE.set("A")` rồi `executor.submit(() -> TRACE.get())`. Task mới có thấy `"A"` không? **Không**, nếu `TRACE` là `ThreadLocal` thường và task chưa tự set.

**Câu 5:** Có nên chuyển mọi context thành `InheritableThreadLocal` không? **Không.** Thừa kế chỉ xảy ra lúc tạo thread và mutable value có thể bị chia sẻ reference.

**Thực hành:** Thử đổi ví dụ allocation thành 100, 1.000 và 10.000 task; quan sát `CREATED`. Thay cache mảng bằng `DateTimeFormatter` dùng chung rồi phân tích khác biệt về số lần khởi tạo. Thêm đường đi exception vào ví dụ request ID để xác nhận `finally` luôn cleanup.

## 11. Ghi nhớ

- `ThreadLocal` hoạt động trên virtual threads Java 21+, và giá trị gắn với **virtual thread**, không gắn với carrier.
- Rất nhiều virtual threads có thể dẫn đến **rất nhiều binding và bản sao object**. Không dùng `ThreadLocal` như cache tái sử dụng giữa nhiều task có virtual thread riêng.
- `withInitial` khởi tạo lười theo từng thread; `remove()` bỏ binding của thread hiện tại. Quản lý scope bằng `try/finally`.
- `ThreadLocal` thông thường không propagate sang thread khác. `InheritableThreadLocal` chỉ thừa kế lúc tạo child thread, cần thận trọng với mutable value.
- Ưu tiên tham số/record bất biến khi có thể; `ScopedValue` được finalized ở JDK 25, còn JDK 21 là preview.
- Đo allocation, heap/GC, số virtual thread đồng thời và tài nguyên downstream trước khi tối ưu.

### Tài liệu chính thức

- Java SE 21 `ThreadLocal` API: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ThreadLocal.html
- Java SE 21 `Thread` và inheritance: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html
- Oracle Java 21 Virtual Threads: https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html
- JEP 444 — Virtual Threads: https://openjdk.org/jeps/444
- JEP 506 — Scoped Values (JDK 25): https://openjdk.org/jeps/506
