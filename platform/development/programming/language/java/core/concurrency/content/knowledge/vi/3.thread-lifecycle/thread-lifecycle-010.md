# Vòng đời tài nguyên gắn với thread trong Java

Khi một `Thread` thực thi công việc, nó sử dụng nhiều loại tài nguyên: stack và thông tin điều phối do JVM quản lý, dữ liệu riêng của luồng (`ThreadLocal`), ngữ cảnh gắn với luồng, và các tài nguyên do mã ứng dụng mở như file, stream, socket hoặc kết nối. **Các tài nguyên này không nhất thiết sống và kết thúc cùng thời điểm.** Đặc biệt, một thread trong pool có thể phục vụ hàng nghìn tác vụ: tác vụ kết thúc không có nghĩa thread kết thúc, và thread kết thúc không tự động đóng mọi tài nguyên ứng dụng từng được mở.

Bài này tập trung vào **Java concurrency nói chung (Java 17+)**, thuộc chủ đề vòng đời `Thread`; không xét cơ chế quản lý luồng hoặc context riêng của Spring.

Sau bài học, bạn cần trả lời được:
- Tài nguyên nào thực sự thuộc JVM/Thread, tài nguyên nào thuộc một **tác vụ** hay một **phạm vi xử lý**?
- Dữ liệu trong `ThreadLocal` tồn tại bao lâu, tại sao tái sử dụng thread dẫn đến giữ dữ liệu cũ và cách dọn đúng?
- Khi có ngoại lệ, hủy, timeout, interrupt, ai chịu trách nhiệm đóng tài nguyên?
- Quản lý lifecycle của thread thủ công và `ExecutorService` khác nhau thế nào?
- Nhận diện và phòng tránh giữ bộ nhớ, rò rỉ handle, context sai và thread không kết thúc.

## 1. Phân biệt vòng đời thread, tác vụ và tài nguyên

Một **thread** là một luồng thực thi. Một **task** là phần việc được giao cho thread thực hiện. **Resource** là đối tượng hay khả năng truy cập cần được thu hồi, đóng hoặc khôi phục tại ranh giới sở hữu thích hợp.

~~~text
Vòng đời thread pool worker:
  Thread tạo ────────────────────────────────────────────────> Thread kết thúc
                 | Task A |  | Task B |  | Task C | ...
                   mở/đóng    mở/đóng    mở/đóng
                    resource   resource   resource

ThreadLocal của worker:
                   set(A) -> remove()
                                set(B) -> remove()
                                            set(C) -> remove()
~~~

Đối với `new Thread(task)` tự tạo, một thread thường chỉ thực thi một lần `run()` rồi kết thúc. Nhưng với `ExecutorService`, **worker thread tồn tại lâu hơn mỗi task** để được tái sử dụng. Vì vậy không được gắn sự dọn dẹp theo “khi nào thread chết” nếu resource chỉ dùng trong một tác vụ.

| Loại | Ví dụ Java | Thời điểm nên kết thúc/phục hồi | Ai chịu trách nhiệm |
| --- | --- | --- | --- |
| Nội bộ JVM phục vụ thread | Stack thực thi, trạng thái/metadata của thread | Khi thread kết thúc và JVM thu hồi phần tương ứng | JVM/hệ điều hành, theo cơ chế triển khai |
| Giá trị liên kết với một thread | `ThreadLocal<T>` | Hết phạm vi logic sử dụng (thường là cuối task), đặc biệt ở pool | Mã đặt giá trị phải `remove()` hoặc phục hồi giá trị trước đó |
| Ngữ cảnh thay đổi trên thread | Context class loader, thread name trong một scope | Khi thoát scope, kể cả lỗi | Mã thay đổi phải khôi phục |
| Tài nguyên của task | `InputStream`, `Reader`, `Socket`, JDBC `Connection` | Khi kết thúc phạm vi sở hữu; không phụ thuộc worker còn chạy | Mã sở hữu, thường bằng `try-with-resources` |
| Khóa phải giải phóng | `ReentrantLock` | Kết thúc đoạn tới hạn | `unlock()` trong `finally` sau khi lấy khóa thành công |
| Bộ thực thi | `ExecutorService` | Khi chủ sở hữu không nhận thêm công việc và muốn hoàn tất/huỷ các task còn lại | Thành phần tạo và sở hữu executor |

Một biến Java trở nên **không còn tham chiếu** không đồng nghĩa tài nguyên ngoài heap được đóng ngay. Garbage collector quản lý khả năng truy cập đối tượng; nó **không phải** cơ chế xác định thời điểm đóng kết nối, file hoặc socket. Đóng đúng lúc giúp tránh cạn tài nguyên và hành vi không dự đoán được.

## 2. Vòng đời của Thread không đồng nghĩa với vòng đời của resource

### 2.1. Những trạng thái quan trọng

`Thread.State` gồm `NEW`, `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING` và `TERMINATED`.

- `NEW`: đối tượng thread đã tạo nhưng chưa `start()`.
- `RUNNABLE`: đang chạy hoặc sẵn sàng chạy theo cách JVM biểu diễn; không nhất thiết đang dùng CPU ngay thời điểm quan sát.
- `BLOCKED`: đang chờ lấy monitor của `synchronized`.
- `WAITING` / `TIMED_WAITING`: đang chờ một điều kiện khác vô hạn hoặc có giới hạn thời gian, ví dụ `join()`/`sleep()`/một số cơ chế đồng bộ.
- `TERMINATED`: `run()` đã kết thúc, bình thường hoặc vì ngoại lệ chưa bắt.

Một `Thread` chỉ có thể `start()` **một lần**. Sau khi `run()` kết thúc, thread không thể khởi động lại. `join()` là cách người khác chờ thread kết thúc; `join()` không tự trả giá trị của tác vụ và không phải phương thức “đóng toàn bộ tài nguyên mà thread từng sử dụng”.

### 2.2. Điều gì xảy ra khi thread kết thúc?

Với platform thread thông thường trên Java 17, JVM/hệ điều hành có thể thu hồi tài nguyên phục vụ thực thi (ví dụ stack/native thread tương ứng) khi thread kết thúc. **Đối tượng `Thread` có thể vẫn được tham chiếu và còn tồn tại trên heap** sau đó; thread ở trạng thái `TERMINATED` không có nghĩa mọi object có liên quan đã lập tức được GC.

Giá trị trong `ThreadLocal` gắn với dữ liệu lưu trên thread, nên có thể được thu gom sau khi thread và dữ liệu của nó thực sự không còn tham chiếu phù hợp. Đây không phải lời hứa “ngay lúc `run()` kết thúc thì `close()` của ứng dụng tự động chạy”.

Ví dụ worker mở `FileInputStream` hoặc `Socket` rồi quên đóng: sự kết thúc thread **không cung cấp hợp đồng đóng** cho tài nguyên đó. Cần dùng `try-with-resources`/`finally` theo API tương ứng, ngay cả khi tác vụ chỉ chạy trên một thread ngắn hạn.

### 2.3. Daemon thread và liveness

`setDaemon(true)` phải được đặt trước khi thread được khởi động. Khi JVM chỉ còn daemon threads hoạt động (và không còn lý do khác để tiếp tục chạy theo cơ chế runtime), JVM có thể kết thúc mà không đợi những daemon thread hoàn tất tác vụ. Do đó không dùng daemon thread như một cách “tự dọn dẹp”; nó có thể bỏ dở thao tác ghi dữ liệu và `finally` cũng không được bảo đảm sẽ chạy khi JVM chấm dứt đột ngột.

Ngược lại, một thread không phải daemon bị kẹt có thể khiến ứng dụng không kết thúc. Vòng đời đúng cần kế hoạch dừng hợp tác, không chỉ thay `daemon`.

## 3. ThreadLocal: dữ liệu riêng của thread được giữ bao lâu?

`ThreadLocal<T>` giúp mỗi thread có một giá trị độc lập được tra cứu qua cùng một biến `ThreadLocal`. Nó thích hợp cho trạng thái **thực sự thuộc thread** hoặc dữ liệu ngữ cảnh **phải giới hạn thời gian sử dụng rất rõ**. Nó không tự đồng bộ hóa một đối tượng dùng chung và không chuyển dữ liệu giữa các thread.

Các thao tác:
- `set(value)`: ghi giá trị thuộc thread đang gọi.
- `get()`: lấy giá trị của **thread đang gọi**, hoặc giá trị khởi tạo nếu dùng `withInitial(...)`.
- `remove()`: xóa mapping của thread hiện tại với `ThreadLocal` này; lần `get()` tiếp theo có thể khởi tạo lại nếu cấu hình initializer.

~~~java
ThreadLocal<String> currentTask = new ThreadLocal<>();
currentTask.set("task-A");
try {
    // Mã chạy trong cùng thread có thể đọc currentTask.get().
} finally {
    currentTask.remove();
}
~~~

Đây là **đoạn mã minh họa**, dùng trong một phạm vi đã biết. `remove()` chỉ xóa liên kết trong `ThreadLocal`; **nó không gọi `close()` trên đối tượng từng chứa trong đó**. Nếu giá trị là tài nguyên cần đóng, cần đóng tài nguyên riêng và đồng thời dọn mapping.

### 3.1. Lỗi kinh điển: thread pool tái sử dụng dữ liệu của task trước

Vì pool giữ worker sống giữa các task, `ThreadLocal` sẽ giữ giá trị qua ranh giới task nếu quên dọn. Đó là lỗi logic (task B thấy context của task A) và cũng có thể kéo dài thời gian sống của một object lớn.

Ví dụ đầy đủ cho Java 17+ sử dụng executor **một worker** để bảo đảm hai task lần lượt chạy trên cùng một thread. Đây là thí nghiệm có chủ đích, không nên giữ nhánh thiếu cleanup trong mã sản phẩm.

~~~java
// ThreadLocalLifecycleDemo.java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ThreadLocalLifecycleDemo {
    private static void scenario(String label, boolean cleanup) throws Exception {
        ThreadLocal<String> context = new ThreadLocal<>();
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            pool.submit(() -> {
                context.set("request-A");
                try {
                    System.out.println(label + " first: " + context.get());
                } finally {
                    if (cleanup) {
                        context.remove();
                    }
                }
            }).get();

            pool.submit(() -> {
                try {
                    System.out.println(label + " second: " + context.get());
                } finally {
                    context.remove();
                }
            }).get();
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        scenario("unsafe", false);
        scenario("safe", true);
    }
}
~~~

Chạy:

~~~bash
javac ThreadLocalLifecycleDemo.java
java ThreadLocalLifecycleDemo
~~~

Stdout:

~~~text
unsafe first: request-A
unsafe second: request-A
safe first: request-A
safe second: null
~~~

**Giải thích:** Tác vụ đầu đặt `"request-A"`. Ở tình huống `unsafe`, task hoàn thành nhưng worker không kết thúc, nên task thứ hai đọc lại giá trị cũ. Ở `safe`, `remove()` chạy trong `finally` trước khi thread được tái sử dụng; lần `get()` ở task kế tiếp trả `null`. Hai tình huống sử dụng hai executor riêng; mỗi executor có chính xác một worker, tránh phụ thuộc vào lựa chọn worker của một pool nhiều luồng. Các lệnh `Future.get()` đảm bảo hai tác vụ theo thứ tự và lỗi trong chúng sẽ được chuyển tới caller.

**Nguyên tắc:** Mã đã `set()` dữ liệu mang ý nghĩa **một request/một task** phải có ranh giới dọn ở **cuối request/task**, không chờ pool đóng.

### 3.2. Giá trị tồn tại trong bộ nhớ như thế nào?

Một thread có cấu trúc lưu giá trị thread-local (triển khai của JDK dùng `ThreadLocalMap`). Trong triển khai thông dụng, khóa của entry tham chiếu yếu tới đối tượng `ThreadLocal`, còn value được giữ mạnh. Có hai tình huống đáng lưu ý:

1. Nếu `ThreadLocal` còn tồn tại, ví dụ biến `static final`, mỗi worker từng `set` có thể giữ giá trị đến khi được `remove`/thay hoặc worker được thu hồi.
2. Nếu chính đối tượng `ThreadLocal` không còn được tham chiếu mạnh ở nơi khác, khóa yếu có thể được thu gom, nhưng entry chứa value chưa chắc được dọn ngay; triển khai loại entry cũ trong các hoạt động phù hợp, nên không được trông chờ GC như chiến lược cleanup có thời hạn.

Vì vậy một pool sống lâu có thể giữ một đồ thị đối tượng lớn, thậm chí cả cấu trúc tham chiếu liên quan đến class loader. Không gọi mọi việc giữ bộ nhớ là “memory leak vĩnh viễn”: chính xác hơn là **giữ tham chiếu lâu hơn phạm vi cần thiết**, gây tăng sử dụng heap hoặc kéo dài vòng đời đối tượng.

### 3.3. Khi nào ThreadLocal không phù hợp?

- Kết quả cần chuyển từ worker sang caller: dùng `Future`, `Callable` hoặc cơ chế truyền dữ liệu rõ ràng.
- Context phải đi theo một task qua **nhiều thread**: truyền tham số hoặc sao chép context có kiểm soát; một `ThreadLocal` thông thường chỉ đọc giá trị của **thread hiện tại**.
- Có thể hoàn thành bằng biến cục bộ/phương thức tham số: phương án đó thường dễ hiểu hơn và có vòng đời ngắn hơn.
- Dữ liệu là tài nguyên cần `close()`: không coi `ThreadLocal.remove()` như thay thế `close()`.

## 4. Tài nguyên thuộc một task: đóng trong phạm vi sở hữu

### 4.1. Dùng try-with-resources, kể cả khi chạy qua ExecutorService

Nếu một tác vụ mở stream/reader/socket/kết nối thì task hoặc abstraction được chỉ định sở hữu phải đóng chúng sau khi hoàn thành. `try-with-resources` tự gọi `close()` khi thoát khối, kể cả khi có exception. Nếu có nhiều resource, chúng được đóng theo thứ tự ngược với thứ tự khai báo.

Ví dụ dưới đây vừa trả kết quả qua `Future`, vừa đóng resource và xóa `ThreadLocal` theo vòng đời task. `StringReader` chỉ dùng để tạo ví dụ chạy độc lập không cần file ngoài; với file/socket thật, quy tắc sở hữu tài nguyên vẫn như vậy.

~~~java
// TaskScopedResourceDemo.java
import java.io.BufferedReader;
import java.io.StringReader;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class TaskScopedResourceDemo {
    private static final ThreadLocal<String> CONTEXT = new ThreadLocal<>();

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            Callable<String> task = () -> {
                CONTEXT.set("request-7");
                try (BufferedReader reader =
                         new BufferedReader(new StringReader("alpha\nbeta"))) {
                    return CONTEXT.get() + ": " + reader.readLine();
                } finally {
                    CONTEXT.remove();
                }
            };

            System.out.println(pool.submit(task).get());
            System.out.println("next sees: " +
                pool.submit(() -> CONTEXT.get()).get());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac TaskScopedResourceDemo.java
java TaskScopedResourceDemo
~~~

Stdout:

~~~text
request-7: alpha
next sees: null
~~~

- `BufferedReader.close()` được gọi ở cuối khối `try-with-resources`, **trước khi task trả kết quả**; caller chỉ nhận chuỗi qua `Future.get()`.
- `finally { CONTEXT.remove(); }` bảo đảm context được xóa khi task kết thúc bình thường hoặc ném exception.
- Task kế tiếp được submit vào cùng executor một worker, nên thấy `null`. Đây là kết quả mong muốn.
- `shutdown()` quản lý vòng đời **executor**, không thay thế việc đóng reader và xóa context trong từng task.

Khi dùng connection, lưu ý “ai sở hữu?”: một connection do task tự mở có thể phải đóng ở cuối scope; connection được một thành phần khác cho mượn có thể có hợp đồng trả về riêng. Đừng đóng tài nguyên đang thuộc sở hữu của thành phần khác chỉ vì bạn đã sử dụng nó.

### 4.2. Các cơ chế cleanup không thể thay thế nhau

| Cơ chế | Làm gì? | Không làm gì? |
| --- | --- | --- |
| `ThreadLocal.remove()` | Xóa value liên kết với thread hiện tại | Không đóng resource được value trỏ tới |
| `AutoCloseable.close()` | Gọi phương thức đóng theo hợp đồng resource | Không tự xóa một mapping `ThreadLocal` bất kỳ |
| `finally` | Bảo đảm khối dọn chạy khi luồng điều khiển thoát bình thường/exception trong điều kiện JVM tiếp tục thực thi | Không bảo đảm chạy sau `Runtime.halt()`, JVM crash hoặc process bị kill |
| `Thread.join()` | Đợi một thread cụ thể kết thúc | Không đóng handle/tài nguyên của task |
| `Future.get()` | Đợi và quan sát kết quả/ngoại lệ của task | Không tự đóng resource bị task bỏ quên |
| `ExecutorService.shutdown()` | Ngừng chấp nhận task mới, cho task đã nhận hoàn tất | Không chờ hoàn tất, không tự dọn mọi resource do task mở |

`java.util.concurrent.locks.ReentrantLock` cũng cần dọn rõ ràng, nhưng **không phải `AutoCloseable`**: lấy khóa thành công rồi phải `unlock()` trong `finally`.

~~~java
// Ví dụ minh họa: giả sử lock là ReentrantLock đã khai báo.
lock.lock();
try {
    // Cập nhật trạng thái chia sẻ cần được bảo vệ.
} finally {
    lock.unlock();
}
~~~

Phạm vi `finally` phải bắt đầu sau khi thực sự lấy được khóa; không `unlock` một khóa mà thread chưa giữ.

## 5. Context gắn với thread: đừng mang giá trị sai sang task sau

### 5.1. Thread name và context class loader

Tên thread thường giúp chẩn đoán. Nếu bạn tạm thay đổi `Thread.currentThread().setName(...)` cho một task trên worker, hãy khôi phục tên cũ trong `finally` để task sau không nhận nhãn của task trước.

Context class loader cũng là trạng thái gắn với thread, truy cập qua `getContextClassLoader()` / `setContextClassLoader(...)`. Một số API tra cứu provider/service theo loader này. Thay đổi mà quên phục hồi có thể khiến tác vụ về sau dùng sai loader và giữ tham chiếu không cần thiết tới class loader.

~~~java
// Ví dụ minh họa: customLoader đã được xác định từ trước.
Thread current = Thread.currentThread();
String oldName = current.getName();
ClassLoader oldLoader = current.getContextClassLoader();
try {
    current.setName("worker-for-task-A");
    current.setContextClassLoader(customLoader);
    // Thực thi công việc cần context tạm thời.
} finally {
    current.setContextClassLoader(oldLoader);
    current.setName(oldName);
}
~~~

Đoạn trên **không phải file Java chạy độc lập**, vì `customLoader` cần được cung cấp. Điểm quan trọng là **save → change → use → restore**, kể cả khi thao tác thất bại. Nếu context có thể lồng nhau, việc phục hồi giá trị cũ đúng hơn là đơn giản gọi `ThreadLocal.remove()` lên một context đã có trước scope; xác định rõ ai là chủ sở hữu ngữ cảnh.

### 5.2. InheritableThreadLocal không tự truyền context theo task

`InheritableThreadLocal<T>` cho phép child thread nhận giá trị kế thừa khi thread được tạo, với cách kế thừa theo hợp đồng API. Nó **không bảo đảm** rằng mỗi task được gửi vào thread pool sẽ nhận context hiện tại của thread submit: worker có thể đã được tạo từ trước và tái sử dụng. Với value mutable, việc kế thừa tham chiếu cũng có thể gây chia sẻ trạng thái ngoài ý muốn.

Không dùng `InheritableThreadLocal` để giả định có cơ chế truyền “request context” xuyên mọi executor. Nếu cần context theo task, **truyền rõ ràng dữ liệu**, và chỉ đặt/khôi phục trong phạm vi task ở đúng thread thực thi khi thật sự cần.

## 6. Interrupt, timeout, cancel và ngoại lệ ảnh hưởng đến cleanup

### 6.1. Interrupt là tín hiệu hợp tác, không phải nút kill

Gọi `Thread.interrupt()` yêu cầu thread chú ý đến trạng thái gián đoạn. Các thao tác chặn có hỗ trợ interrupt như `Thread.sleep`, `Object.wait`, `Thread.join` và một số phép chờ trong concurrency API có thể ném `InterruptedException`. Khi ném ngoại lệ này, trạng thái interrupt thường bị xóa theo hợp đồng phương thức; nếu catch và không truyền tiếp, cần cân nhắc khôi phục bằng `Thread.currentThread().interrupt()`, sau đó kết thúc công việc/đưa tín hiệu lên tầng gọi.

~~~java
// Đoạn mã minh họa bên trong task; resource là AutoCloseable.
try (var resource = openResource()) {
    doInterruptibleWork(resource);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Thoát khỏi task hoặc báo hủy theo hợp đồng.
}
~~~

`openResource()` và `doInterruptibleWork(...)` là **placeholder giải thích cấu trúc**, không phải API Java có sẵn; đoạn này không phải chương trình độc lập. Điểm cần nhìn là resource được đóng khi thoát khỏi `try-with-resources` do interrupt gây ra. Dù vậy, không phải mọi thao tác I/O hoặc thư viện bên ngoài đều phản hồi interrupt ngay lập tức.

### 6.2. Future.cancel và ExecutorService.shutdownNow

- `Future.cancel(true)` thử hủy task, cho phép gián đoạn thread đang chạy nếu task đang chạy và implementation hỗ trợ. Đây **không phải bảo đảm** mã tác vụ dừng tức thì.
- `Future.get(timeout, unit)` chỉ giới hạn **thời gian chờ của caller**. `TimeoutException` không tự dừng task hoặc đóng tài nguyên của nó.
- `ExecutorService.shutdown()` dừng nhận việc mới; task đã được nhận vẫn có thể chạy.
- `ExecutorService.shutdownNow()` cố dừng task đang chạy bằng interrupt và trả về danh sách task đang đợi chưa chạy; nó không bảo đảm tất cả worker đã thực sự dừng.
- `awaitTermination(...)` cho caller khả năng đợi executor kết thúc trong một khoảng thời gian; nếu quá thời hạn, cần chính sách tiếp theo.

**Hệ quả với resource:** `finally`/`try-with-resources` trong task chỉ chạy khi luồng điều khiển của task thực sự thoát khỏi scope. Nếu task phớt lờ interrupt và tiếp tục chạy, caller `cancel` hoặc `shutdownNow` không có phép màu đóng thay những resource đang nằm trong task đó. Hãy thiết kế task có đường thoát hợp tác và deadline thích hợp.

### 6.3. Mẫu quản lý executor trên Java 17

~~~java
// ExecutorShutdownDemo.java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ExecutorShutdownDemo {
    public static void main(String[] args) {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            pool.execute(() -> System.out.println("task complete"));
        } finally {
            pool.shutdown();
            try {
                if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                    pool.shutdownNow();
                    if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                        System.err.println("executor still running");
                    }
                }
            } catch (InterruptedException e) {
                pool.shutdownNow();
                Thread.currentThread().interrupt();
            }
        }
    }
}
~~~

~~~bash
javac ExecutorShutdownDemo.java
java ExecutorShutdownDemo
~~~

Stdout trong lần chạy bình thường:

~~~text
task complete
~~~

Giải thích: `shutdown()` ngăn nhận task mới; `awaitTermination` chờ tối đa thời gian chỉ định; nếu chưa kết thúc, `shutdownNow()` yêu cầu hủy theo mức implementation cho phép. Trong ví dụ bình thường, một tác vụ in thông báo rồi kết thúc rất nhanh. Với hệ thống thực tế, thiết kế timeout/chính sách báo lỗi phải tương ứng với nhu cầu ứng dụng, và người dùng cần biết khi dừng không thành công.

**Lưu ý phiên bản:** Trên Java 17, `ExecutorService` chưa có cơ chế `AutoCloseable.close()` theo API mới hơn, nên hãy quản lý `shutdown`/`awaitTermination` chủ động như ví dụ. Không lấy ví dụ `try (ExecutorService executor = ...)` từ tài liệu JDK mới hơn rồi kỳ vọng biên dịch dưới Java 17.

### 6.4. Uncaught exception và cleanup

Một exception không được bắt có thể khiến `Thread.run()` kết thúc; với `Thread` thủ công, JVM có cơ chế uncaught-exception handler để báo lỗi. Nhưng đây **không phải** cách tự động dọn các resource mà code mở sai phạm vi. `finally` và `try-with-resources` trong những frame đang unwinding vẫn chạy trong điều kiện thực thi Java thông thường. Với task do `ExecutorService.submit`, lỗi thường được giữ trong `Future` và quan sát khi gọi `get()`. Không chỉ dựa vào log handler để biết task có hoàn tất thành công hay không.

## 7. Khác nhau giữa ThreadLocal và tài nguyên được truyền qua tham số

Giả sử một worker xử lý lần lượt task A và task B:
- Dùng **tham số** `process(order, requestId)`: giá trị thuộc lời gọi, dễ thấy ranh giới và không tự lưu trên worker.
- Dùng **ThreadLocal** cho `requestId`: nhiều phương thức sâu trong call stack có thể đọc mà không nhận tham số, nhưng mọi đoạn code cùng thread có thể đọc cùng mapping và phải bảo đảm dọn. Nếu code giao một bước cho thread khác, thread mới không mặc nhiên có giá trị.
- Dùng **một object mutable chia sẻ** qua nhiều worker: cần thiết kế thread safety của object độc lập với lifecycle; `ThreadLocal` không biến object đó thành bất biến hay ngăn race nếu nhiều thread trỏ tới cùng instance.

Quy tắc thực hành: **ưu tiên trạng thái theo phạm vi xử lý**, chỉ lưu trạng thái theo thread khi có lý do rõ ràng về API, hiệu năng hoặc ngữ cảnh thực thi. Một thread là công cụ chạy công việc, không nhất thiết là đơn vị nghiệp vụ “request”.

## 8. Chẩn đoán giữ tài nguyên quá lâu

### Dấu hiệu thường gặp

| Triệu chứng | Khả năng cần kiểm tra |
| --- | --- |
| Request sau thấy ID/context của request trước | `ThreadLocal` hoặc thread metadata không được dọn/khôi phục trên worker tái sử dụng |
| Heap tăng theo thời gian dù số request đã hoàn tất | Giá trị `ThreadLocal`, cache/task queue, hoặc object graph còn được giữ |
| Tăng số file descriptor/socket/connection | Resource ngoài heap chưa `close` đúng thời điểm |
| Ứng dụng không chịu thoát sau khi ngừng nhận việc | Executor chưa `shutdown`, worker không kết thúc, task chặn hoặc bỏ qua interrupt |
| Task hủy rồi nhưng vẫn giữ kết nối lâu | Timeout/cancel chỉ dừng chờ caller, task không thoát scope hoặc API không hỗ trợ ngắt |
| Task chạy trên thread khác mất context | `ThreadLocal` không truyền theo task; thread pool tái sử dụng không bảo đảm `InheritableThreadLocal` |

### Cách tìm nguyên nhân

1. **Xác định chủ sở hữu**: ai mở file/kết nối, ai `set` `ThreadLocal`, ai tạo executor? Ghi ranh giới chính xác: method call, task, request, worker hay toàn ứng dụng.
2. **Đo thời gian sống thật**: khi công việc xong, resource đã đóng chưa? Hãy đo số connection/descriptor đang mở, heap hoặc queue đang giữ task, số worker đang sống.
3. **Tìm đường thoát**: exception, return sớm, cancel, timeout và interrupt có đi qua `finally`/`try-with-resources` không? Có nhánh nào quên cleanup?
4. **Kiểm tra sử dụng thread pool**: chạy nhiều task liên tiếp trên cùng worker để phát hiện dữ liệu cũ trong `ThreadLocal`; đừng kiểm thử bằng hai thread mới rồi kết luận không có lỗi.
5. **Quan sát thread dump nếu nghi worker kẹt**: `jcmd <PID> Thread.print -l` có thể giúp xem trạng thái/chồng lời gọi của các thread đang hoạt động, nhưng **không tự cho biết mọi stream hoặc ThreadLocal đã được dọn**. Kết hợp log, heap dump hoặc công cụ đo tài nguyên thích hợp khi cần.
6. **Sửa theo hợp đồng sở hữu**: resource mở ở đâu thì đóng đúng chỗ; `ThreadLocal` theo task thì `remove` cuối task; trạng thái context tạm thời thì restore; executor do ứng dụng sở hữu thì shutdown đúng lifecycle.

Đừng mặc định “rò rỉ bộ nhớ” khi thấy heap lớn: cache hợp lệ, GC chưa thu hồi, task queue bị tồn đọng, thread-local giữ value hoặc reference ngoài phạm vi đều có thể gây biểu hiện tương tự. Cần lần theo đối tượng và thời điểm chúng còn được tham chiếu.

## 9. Checklist thiết kế và lỗi cần tránh

- **Task mở resource** → dùng `try-with-resources` nếu là `AutoCloseable`; bảo đảm close kể cả khi có lỗi.
- **Task đặt ThreadLocal** → `remove()` trong `finally`, hoặc lưu/khôi phục giá trị cũ nếu xử lý ngữ cảnh lồng nhau.
- **Task đổi thread name/context loader** → save giá trị trước và restore trong `finally`.
- **Thread dùng lock** → lấy khóa thành công rồi `unlock()` trong `finally`.
- **Executor do thành phần hiện tại sở hữu** → `shutdown()` và đợi hoàn tất có giới hạn, xử lý interrupt/cancel phù hợp.
- **Task cần dừng** → phản hồi interrupt hoặc có cơ chế hủy hợp tác; đừng phụ thuộc vào `Thread.stop()` (unsafe/deprecated).
- **Có nhiều worker** → không dùng `ThreadLocal` để truyền giá trị trả về hoặc mặc định chia sẻ context giữa thread.
- **Dùng daemon thread** → không xem daemon là cơ chế flush/close resource khi JVM thoát.
- **Có giá trị được cache theo thread** → cân nhắc chi phí bộ nhớ nhân với số worker và nhu cầu cleanup/eviction cụ thể.
- **Có ngoại lệ ở executor task** → quan sát kết quả `Future`, vì lỗi có thể không hiện ra theo cách mong đợi nếu chỉ `submit` rồi bỏ quên future.

### Sai lầm hay gặp

**“Đã xong request nên ThreadLocal sẽ tự trống.”** Sai nếu worker tiếp tục sống; mapping theo **thread**, không theo request.

**“Gọi ThreadLocal.remove() sẽ đóng Connection.”** Sai: remove chỉ tháo liên kết. `Connection.close()` tuân theo hợp đồng sở hữu riêng.

**“Thread kết thúc thì JVM đóng tất cả socket/file do nó mở.”** Không có bảo đảm như vậy. Thread và I/O resource có vòng đời khác nhau.

**“Future.get(timeout) timeout nghĩa là task đã bị hủy.”** Sai: caller ngừng chờ, task có thể đang chạy.

**“Dùng InheritableThreadLocal là context tự đi theo submit().”** Sai với pool: kế thừa xảy ra theo việc tạo thread, không theo mỗi lần submit task.

**“shutdownNow() chắc chắn dừng hết ngay.”** Sai: nó cố gián đoạn task đang chạy; task cần hợp tác và có thể không thoát.

**“Đợi join() là thay được close().”** Sai: join đợi thực thi kết thúc; resource của task cần chính task hoặc owner đóng đúng phạm vi.

## 10. Câu hỏi tự kiểm tra

1. **Một `ExecutorService` chỉ có một worker. Task A đặt `ThreadLocal` rồi kết thúc mà không remove. Task B đọc gì?** Nếu không có ghi đè/cleanup nào khác, B có thể đọc lại giá trị A, vì cả hai chạy trên cùng thread.
2. **Task A dùng `BufferedReader` trong `try-with-resources`, còn worker vẫn sống. Reader đã đóng chưa?** Đã đóng khi rời scope, không cần đợi worker chết.
3. **Bắt `InterruptedException` và tiếp tục xử lý như không có gì xảy ra có thể gây vấn đề gì?** Làm mất tín hiệu hủy/dừng, task kéo dài và resource được giữ lâu hơn; cân nhắc truyền tiếp hoặc khôi phục interrupt rồi thoát.
4. **Nếu `ThreadLocal` chứa một `Socket`, gọi remove có đóng socket không?** Không; owner phải đóng socket theo hợp đồng.
5. **Thay context class loader trong task có cần khôi phục không?** Có, để worker được tái sử dụng không mang loader của task trước.
6. **`shutdown()` rồi thoát `main` có chắc pool đã kết thúc không?** Không; cần chờ/cấu trúc lifecycle phù hợp nếu yêu cầu xác định thời điểm kết thúc.
7. **Dùng `InheritableThreadLocal` cho pool tạo từ đầu ứng dụng có đảm bảo task mới thấy context của thread submit không?** Không, vì giá trị kế thừa xảy ra khi tạo worker, không ở mỗi lần gửi task.

**Kết luận cần nhớ:** Xác định **resource thuộc phạm vi nào**, rồi đặt **cleanup ở cuối chính phạm vi đó**. Thread có thể sống lâu hơn task; vì vậy việc gỡ `ThreadLocal`, khôi phục context, giải phóng lock và đóng I/O phải do mã sở hữu thực hiện chủ động. `Thread.join()`, `Future.get()` và `ExecutorService.shutdown()` hỗ trợ điều phối vòng đời thực thi, nhưng không thay thế các thao tác cleanup của tài nguyên ứng dụng.