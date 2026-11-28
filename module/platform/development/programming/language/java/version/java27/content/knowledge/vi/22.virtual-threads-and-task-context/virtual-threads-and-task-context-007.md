# Timeout, interruption và đóng executor theo vòng đời yêu cầu trong Java 27

Trong hệ thống xử lý request, một yêu cầu HTTP, một công việc xử lý đơn hàng hoặc một lần tổng hợp báo cáo có thể khởi tạo nhiều tác vụ con: đọc hồ sơ người dùng, kiểm tra tồn kho, gọi dịch vụ khác và ghi nhận kết quả. Các tác vụ đó có thể chạy bằng **virtual threads** để tận dụng mô hình lập trình đồng bộ dễ đọc khi chờ I/O.

Vấn đề quan trọng là **vòng đời của các tác vụ phải gắn với vòng đời của request**: khi request thành công, thất bại, hết thời gian hoặc bị hủy, ứng dụng phải biết tác vụ nào còn chạy, ai yêu cầu dừng và khi nào tài nguyên được đóng. Trong Java 27, các API ổn định như `Executors.newVirtualThreadPerTaskExecutor()`, `Future.get(timeout, unit)`, `Future.cancel(true)`, `Thread.interrupt()` và `ExecutorService.shutdown()/close()` là những công cụ nền tảng cho thiết kế này.

> **Phân biệt ba việc:** **timeout** giới hạn thời gian một thao tác đợi; **cancellation/interruption** yêu cầu công việc dừng; **shutdown/close** kết thúc vòng đời executor. Chúng **không đồng nghĩa** và không tự động thay thế cho nhau.

Các ví dụ dưới đây dùng API Java SE 27 đã ổn định; không yêu cầu `--enable-preview`. `StructuredTaskScope` trong tài liệu Java SE 27 vẫn được đánh dấu **preview**, nên không dùng nó làm điều kiện bắt buộc hoặc làm ví dụ cần biên dịch mặc định.

## 1. Mô hình vòng đời request và quyền sở hữu

Một request có thể có cây công việc:

```text
Request: GET /dashboard      budget 400 ms
│
├── Task A: tải profile       Future<Profile>
├── Task B: tải stock         Future<Stock>
└── Task C: tổng hợp response (chỉ khi có dữ liệu cần thiết)

START → submit subtasks → await within shared deadline
         ├── tất cả thành công → build response → COMPLETE
         ├── một task thất bại → cancel phần không cần → ERROR
         ├── hết deadline     → cancel phần chưa xong → TIMEOUT
         └── caller bị ngắt  → cancel phần chưa xong → INTERRUPTED
                               │
                               └── giải phóng tài nguyên đã sở hữu
```

**Nguyên tắc thiết kế:**

1. Request có **một thời hạn tổng** thay vì cấp lại toàn bộ timeout cho mỗi bước.
2. Khi một kết quả không còn cần thiết, request chủ động **hủy các task liên quan**; không để “orphan task” tiếp tục dùng tài nguyên ngoài ý muốn.
3. Task phải **hợp tác với hủy bỏ**: kiểm tra interrupt/cancellation và sử dụng I/O có timeout, không chỉ chờ lệnh từ caller.
4. Request chỉ đóng những tài nguyên **do chính request sở hữu**. Executor dùng chung toàn ứng dụng không được request tự ý shutdown.
5. Đóng executor phải có **chính sách riêng**. Đặc biệt, `close()` không phải một phép “đóng ngay sau timeout”.
6. Không để kết quả đến muộn ghi đè trạng thái hoặc phản hồi đã được xác nhận thất bại/hết hạn.

### 1.1. Phân biệt request, task, thread và executor

| Thành phần | Vai trò | Ai thường sở hữu? |
| --- | --- | --- |
| **Request context** | Request ID, thông tin tối thiểu cần thiết, deadline, chính sách hủy | Handler của request |
| **Task/Callable** | Một thao tác nghiệp vụ cụ thể | Handler tạo và theo dõi, executor thực thi |
| **Future** | Theo dõi hoàn tất, lỗi và yêu cầu cancel của một task | Handler nắm giữ khi còn cần kết quả |
| **Virtual thread** | Luồng thực thi một task; thường nhẹ khi chờ I/O | Java runtime/executor quản lý |
| **ExecutorService** | Nhận, chạy task và quản lý shutdown | Component tạo executor: app hoặc request |
| **Tài nguyên I/O** | Socket, response body, DB connection, stream | Phạm vi tạo hoặc nhận quyền sở hữu tài nguyên |

Tránh đồng nhất **“xong Future”** với **“thread đã thực sự dừng và mọi tài nguyên đã giải phóng”**. `Future.isDone()` cũng trả `true` khi Future **bị cancel**; điều đó không chứng minh một task không hợp tác đã ngừng thực thi.

## 2. Timeout giới hạn điều gì?

Từ “timeout” có thể áp dụng ở nhiều tầng khác nhau. Chọn sai tầng sẽ khiến request trả lỗi đúng hạn nhưng background task vẫn tiếp tục chiếm tài nguyên.

| Loại timeout | API ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Đợi kết quả của một Future** | `future.get(200, MILLISECONDS)` | Caller đợi tối đa khoảng này để lấy kết quả; khi timeout, **task không tự bị cancel** |
| **Đợi nhiều task cùng lúc** | `executor.invokeAll(tasks, timeout, unit)` | Đợi theo một giới hạn tổng cho lời gọi; các task chưa hoàn tất được cancel khi phương thức trả về |
| **Đợi một task thành công trong nhiều task** | `executor.invokeAny(tasks, timeout, unit)` | Trả kết quả thành công đầu tiên; task không cần thiết bị cancel theo hợp đồng |
| **Đợi executor chấm dứt** | `executor.awaitTermination(timeout, unit)` | Đợi executor kết thúc **sau khi** đã yêu cầu shutdown; trả `false` nếu hết thời gian |
| **I/O tới dịch vụ khác** | API socket/HTTP/DB với timeout riêng | Giới hạn thời gian kết nối/đọc/truy vấn theo hợp đồng API |
| **Toàn bộ request** | Một deadline tính theo `System.nanoTime()` | Ngân sách chung bao gồm nhiều công đoạn và thời gian đợi |

**Không nhầm `Thread.sleep(Duration)` với cơ chế timeout:** `sleep` chỉ tạm dừng thread hiện tại; nó không hủy một tác vụ khác và không đặt giới hạn thời gian cho socket, HTTP client hoặc `Future`.

### 2.1. Future.get(timeout) không tự dừng công việc

```java
import java.util.concurrent.*;

try (ExecutorService executor =
        Executors.newVirtualThreadPerTaskExecutor()) {

    Future<String> result = executor.submit(() -> {
        Thread.sleep(500);
        return "done";
    });

    try {
        System.out.println(result.get(20, TimeUnit.MILLISECONDS));
    } catch (TimeoutException timeout) {
        result.cancel(true); // Yêu cầu ngắt task khi còn chạy
        System.out.println("Timed out");
    }
}
```

Đây là mảnh code dành cho một method có thể khai báo `throws Exception`. `get(20, MILLISECONDS)` chỉ giới hạn thời gian **thread gọi `get` chờ**. Nếu bỏ `result.cancel(true)`, task có thể tiếp tục chạy sau khi caller nhận `TimeoutException`.

Ngay cả sau `cancel(true)`, đóng executor có thể còn phải đợi task phản hồi hủy. Trong ví dụ, `Thread.sleep` hỗ trợ interruption nên task thường dừng nhanh; đây **không phải cam kết** rằng mọi I/O hoặc thư viện bên ngoài cũng dừng nhanh như vậy.

### 2.2. Timeout của Future, cancel và I/O timeout là ba cơ chế

```text
Caller                  Task                 External service
  │ submit               │                          │
  ├──────────────────────>│── request ──────────────>│
  │ get(100 ms)           │                          │
  │ ...                   │ ... waiting for I/O       │
  │ TimeoutException      │                          │
  ├── cancel(true) ──────>│ request interruption     │
  │                       │                          │
  └─ return TIMEOUT       └── may still be unwinding ┘
```

Nếu ứng dụng cần một hạn mức thực sự đáng tin cậy, hãy cấu hình **connect/read/request/query timeout ở lớp I/O** bên cạnh `Future` deadline. Cần kiểm tra tài liệu của chính driver/client để biết thao tác nào có thể bị interrupt, thời gian chờ, quyền sở hữu kết nối và cách đóng khi hủy.

## 3. Deadline chung: không cấp lại toàn bộ timeout cho từng bước

Giả sử request có **300 ms** nhưng phải đợi hai Future. Cách sau không đúng với deadline chung:

```java
String profile = profileFuture.get(300, TimeUnit.MILLISECONDS);
String stock = stockFuture.get(300, TimeUnit.MILLISECONDS);
```

Trong trường hợp xấu, hai lần `get` nối tiếp có thể làm caller chờ gần **600 ms** (chưa kể thời gian chuẩn bị), dù yêu cầu nghiệp vụ chỉ cho phép 300 ms.

### 3.1. Đo khoảng thời gian bằng System.nanoTime()

`System.nanoTime()` thích hợp để đo **thời gian trôi qua** trong cùng JVM. Khác với đồng hồ ngày giờ như `Instant.now()`, phép đo này không nhằm biểu diễn thời điểm lịch trên thế giới và không nên dùng để lưu timestamp nghiệp vụ.

Mẫu dùng ngân sách chung:

```java
import java.time.Duration;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.ExecutionException;

static <T> T awaitWithin(
        Future<T> future,
        long startedNanos,
        long budgetNanos)
        throws InterruptedException, ExecutionException, TimeoutException {

    long elapsed = System.nanoTime() - startedNanos;
    long remaining = budgetNanos - elapsed;

    if (remaining <= 0) {
        throw new TimeoutException("Request deadline exceeded");
    }

    return future.get(remaining, TimeUnit.NANOSECONDS);
}
```

Caller cần tạo **một** giá trị `startedNanos` trước khi submit task và chuyển nó vào tất cả các lần `awaitWithin`. Mỗi lần chờ lấy **phần còn lại**, không tái cấp toàn bộ ngân sách.

Lưu ý kỹ thuật:

- Giả định ngân sách được giới hạn về giá trị hợp lý; `Duration.toNanos()` có thể ném `ArithmeticException` nếu giá trị quá lớn.
- Lấy hiệu hai giá trị `nanoTime` để đo trôi qua, không coi giá trị tuyệt đối của `nanoTime` là Unix timestamp.
- Kiểm tra deadline **trước các công đoạn tốn thời gian khác** khi cần (ví dụ trước khi ghi thay đổi trạng thái).
- Deadline là cơ chế điều phối, **không** bảo đảm JVM/hệ điều hành sẽ đánh thức thread chính xác từng nanosecond.
- Thời gian dùng để xử lý cleanup, flush và trả lỗi cũng cần được cân nhắc trong **ngân sách request tổng**.

### 3.2. Deadline khác timeout tương đối

- **Timeout tương đối:** “đợi tối đa 100 ms từ ngay bây giờ”.
- **Deadline chung:** “request phải xong trong 300 ms kể từ lúc bắt đầu”.

Khi có nhiều bước, deadline chung cho phép tầng dưới biết bao nhiêu thời gian **thực sự còn lại**. Nếu upstream còn 50 ms mà downstream tự đặt timeout 5 giây, yêu cầu đã mất ý nghĩa thời hạn tổng.

Trong các API nội bộ, có thể đóng gói thời gian bắt đầu và ngân sách vào một record hoặc đối tượng bất biến; điều đó giúp tránh truyền nhầm đơn vị `MILLISECONDS`/`SECONDS`. Khi cần truyền qua nhiều process, mỗi process nên quản lý deadline tương đối theo đồng hồ monotonic **riêng**, không chuyển số `System.nanoTime()` giữa các máy.

## 4. Interruption: yêu cầu dừng hợp tác, không phải cưỡng bức

`Thread.interrupt()` thiết lập cờ interrupted hoặc khiến một số thao tác chờ phản ứng bằng `InterruptedException`. Với task được gửi qua executor, `Future.cancel(true)` thường **yêu cầu** interrupt thread thực thi nếu implementation biết thread đó. Không cơ chế nào bảo đảm lập tức kết thúc một task bất kỳ.

### 4.1. Task ngủ/chờ và phản hồi interrupt

```java
import java.time.Duration;

static String fetchRemoteData() throws InterruptedException {
    Thread.sleep(Duration.ofMillis(200)); // Mô phỏng I/O blocking có thể ngắt
    return "remote-data";
}
```

Nếu caller cancel trong thời gian `sleep`, task nhận `InterruptedException` và method kết thúc bất thường. Ở đây khai báo `throws InterruptedException` là hợp lý: method chuyển tín hiệu hủy cho tầng quản lý thay vì nuốt nó.

Với `Runnable` không thể ném checked exception ra khỏi `run()`, xử lý theo chính sách rõ ràng:

```java
Runnable work = () -> {
    try {
        Thread.sleep(Duration.ofSeconds(10));
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt(); // Khôi phục cờ nếu không ném tiếp
        return; // Dừng sớm, không tiếp tục công việc
    }
};
```

Cách khôi phục `Thread.currentThread().interrupt()` phù hợp khi tầng hiện tại không thể hoặc không muốn ném tiếp checked exception, nhưng vẫn cần giữ tín hiệu cho code tiếp theo. Trường hợp `Callable` có thể khai báo `throws InterruptedException`, hãy **ưu tiên ném tiếp** khi chính sách tầng gọi cần biết request đã bị ngắt.

### 4.2. Điểm kiểm tra trong tác vụ CPU-bound

Một vòng lặp tính toán không có thao tác chờ interruptible cần **tự kiểm tra** trạng thái:

```java
import java.util.concurrent.CancellationException;

static long computeChecksums(long limit) {
    long checksum = 0;
    for (long i = 0; i < limit; i++) {
        if (Thread.currentThread().isInterrupted()) {
            throw new CancellationException("Computation interrupted");
        }
        checksum ^= i;
    }
    return checksum;
}
```

Ví dụ kiểm tra mỗi vòng để làm rõ nguyên tắc. Ở thuật toán CPU nặng, có thể kiểm tra theo lô để cân bằng overhead và độ trễ phản hồi hủy; khoảng kiểm tra phải dựa trên yêu cầu hệ thống.

**Phân biệt hai method:**

- `Thread.currentThread().isInterrupted()`: đọc cờ, **không xóa cờ**.
- `Thread.interrupted()`: method static kiểm tra **và xóa** cờ interrupt của thread hiện tại.

Không dùng `Thread.interrupted()` trong điều kiện mà không hiểu side effect của việc xóa cờ.

### 4.3. Cleanup trong finally và try-with-resources

```java
static void useResource() throws InterruptedException {
    try {
        Thread.sleep(Duration.ofSeconds(1));
        // Đọc/ghi tài nguyên theo nghiệp vụ
    } finally {
        // Đóng/hoàn trả tài nguyên do method sở hữu,
        // kể cả khi bị interrupt hoặc exception.
    }
}
```

Trong ứng dụng thực, dùng `try-with-resources` cho `AutoCloseable` và cần quyết định policy rollback giao dịch, tạm dừng retry, hủy HTTP call hoặc đóng socket. `Future.cancel(true)` **không tự động rollback** thay đổi DB, gọi API bên ngoài hay thao tác ghi đã hoàn tất.

### 4.4. Đừng nuốt InterruptedException

Đoạn sau có vấn đề:

```java
try {
    Thread.sleep(Duration.ofSeconds(2));
} catch (InterruptedException ignored) {
    // SAI: tiếp tục làm việc bình thường dù caller đã yêu cầu hủy.
}
```

Một thao tác chờ như `sleep` thường **xóa interrupted status khi ném `InterruptedException`**. Nếu bỏ qua exception, tín hiệu hủy có thể biến mất. Ném tiếp hoặc khôi phục trạng thái và dừng hợp lý theo hợp đồng của method.

## 5. Future.cancel(true): trạng thái Future không đồng nhất với việc task đã chết

Với `Future<?> future`:

```java
boolean accepted = future.cancel(true);
boolean cancelled = future.isCancelled();
boolean done = future.isDone();
```

Đặc tả `Future`:

- `cancel(true)` **thử** hủy, và có thể interrupt thread đang chạy.
- Nếu task chưa bắt đầu và được cancel hợp lệ, nó không nên được thực thi.
- `isCancelled() == true` cho biết Future đã vào trạng thái bị hủy.
- `isDone() == true` có thể do hoàn thành thành công, thất bại hoặc bị hủy.
- `future.get()` trên Future đã bị cancel ném `CancellationException`.
- Giá trị Boolean do `cancel(...)` trả về không nhất thiết thay thế được việc kiểm tra trạng thái cuối cùng bằng `isCancelled()`.

**Điểm quan trọng:** task có thể đang xử lý cleanup hoặc còn chạy trong một đoạn không đáp ứng interrupt, **dù Future đã báo cancelled**. Nếu tính đúng đắn yêu cầu không còn tác động phụ sau timeout, chỉ dựa trên `cancel` là chưa đủ; cần thiết kế ranh giới transaction, idempotency, rollback, version token hoặc điều kiện kiểm tra quyền ghi ở tầng lưu trữ.

### 5.1. Kết quả đến muộn và side effect

Ví dụ request hết hạn sau khi đã gửi tác vụ ghi bên ngoài:

```text
t0   request bắt đầu
t1   task gửi lệnh update tới DB
t2   caller hết deadline, gọi future.cancel(true)
t3   DB đã commit lệnh từ t1
t4   response báo timeout
```

`cancel(true)` không đảo ngược commit tại `t3`. Nếu request có thể được client retry, thiết kế nghiệp vụ nên sử dụng **idempotency key** hoặc cơ chế chống thực thi hai lần. Không hứa “cứ timeout là không có gì được ghi”.

## 6. ExecutorService.close: ý nghĩa chính xác theo Java SE 27

`ExecutorService` mở rộng `AutoCloseable` nên có thể dùng:

```java
try (ExecutorService executor =
        Executors.newVirtualThreadPerTaskExecutor()) {
    Future<String> f = executor.submit(() -> "ready");
    System.out.println(f.get());
} // close()
```

`close()` theo Java SE 27:

1. Bắt đầu **orderly shutdown** tương tự `shutdown()`: không nhận task mới, nhưng các task đã submit được phép hoàn tất.
2. **Chờ executor terminated**, tức không còn task đang chạy/đang chờ thực thi.
3. Nếu thread đang gọi `close()` **bị interrupt trong lúc chờ**, phương thức tiến hành hủy mạnh hơn như `shutdownNow()`, sau đó **tiếp tục đợi** các task đang chạy hoàn tất; trước khi trả về, cờ interrupt của caller được khôi phục.
4. Nếu executor đã terminated, gọi `close()` không có tác động thêm.

Vì vậy, **`close()` không phải API “đóng trong tối đa N mili-giây”**. Nếu một task không phản hồi interrupt, việc đóng có thể chờ rất lâu hoặc vô hạn.

### 6.1. So sánh các API shutdown

| API | Nhận task mới? | Task đang chạy/chờ | Có đợi kết thúc không? |
| --- | --- | --- | --- |
| `shutdown()` | Không | Cho các task đã submit hoàn tất theo thứ tự triển khai | **Không**, trả về sau yêu cầu shutdown |
| `shutdownNow()` | Không | Thử ngắt task đang chạy; dừng task đang chờ chưa bắt đầu | **Không**; chỉ best effort |
| `awaitTermination(timeout, unit)` | Không thay đổi trạng thái shutdown | Chỉ chờ trạng thái terminated sau yêu cầu shutdown | **Có giới hạn**, trả `true` hoặc `false` |
| `close()` | Không | Orderly shutdown; nếu caller bị ngắt lúc chờ thì thử shutdownNow | **Có, không có timeout cấu hình trực tiếp** |

**Không nhầm** `shutdownNow()` với một cơ chế cưỡng bức giết thread. Nó thường sử dụng interrupt và không cam kết task sẽ dừng khi không hợp tác.

### 6.2. Mối quan hệ giữa timeout của request và try-with-resources

```java
try (ExecutorService executor =
        Executors.newVirtualThreadPerTaskExecutor()) {

    Future<?> future = executor.submit(() -> {
        // Một thao tác I/O hoặc tác vụ tính toán
        return null;
    });

    try {
        future.get(100, TimeUnit.MILLISECONDS);
    } catch (TimeoutException timeout) {
        future.cancel(true);
    }
} // close() vẫn phải chờ executor kết thúc
```

Kể cả khi `get(...)` dừng chờ ở mức 100 ms, thời gian thoát khỏi khối `try` có thể **vượt 100 ms** vì `close()` còn chờ task dừng. Đây là hành vi đúng theo hợp đồng API, không phải lỗi của `try-with-resources`.

**Kết luận thiết kế:** dùng `try-with-resources` khi mọi task **hợp tác và có khả năng kết thúc trong thời gian hợp lý**, còn request deadline chặt chẽ cần kiểm soát cả I/O timeout, cancellation, phương án xử lý task còn tồn tại và ownership của executor.

### 6.3. Không đóng shared executor từ request

Nếu executor do application tạo một lần để phục vụ nhiều request, thì request **chỉ sở hữu các Future** đã submit, **không sở hữu executor**.

```text
Application startup:
  shared ExecutorService  ────┐
                              ├── request A → Futures A
                              ├── request B → Futures B
                              └── request C → Futures C

Request A timeout → cancel Futures A
                  → KHÔNG shutdown shared executor
Application shutdown → shutdown/awaitTermination shared executor
```

Nếu request A tự gọi `sharedExecutor.shutdown()` hoặc `close()`, request B/C có thể bị từ chối task mới hoặc bị ảnh hưởng bởi vòng đời của A. Đây là lỗi ownership, không phải lỗi của virtual threads.

## 7. Ví dụ Java 27 hoàn chỉnh: nhiều tác vụ với một deadline chung

Bài toán: trong một request, cần đồng thời lấy **tên người dùng** và **số lượng tồn kho**. Mỗi thao tác được mô phỏng bằng `Thread.sleep` để có thể hủy bằng interrupt. Executor thuộc **application**; method xử lý request chỉ quản lý các Future của mình.

Chương trình độc lập, lưu thành `RequestDeadlineDemo.java`:

```java
import java.time.Duration;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class RequestDeadlineDemo {

    record RequestContext(String requestId) {}
    record Response(String customer, int stock) {}

    static String fetchCustomer(RequestContext context)
            throws InterruptedException {
        Thread.sleep(Duration.ofMillis(120));
        return "Mai";
    }

    static int fetchStock(RequestContext context)
            throws InterruptedException {
        Thread.sleep(Duration.ofMillis(90));
        return 12;
    }

    static <T> T awaitWithin(
            Future<T> future,
            long startedNanos,
            long budgetNanos)
            throws InterruptedException, ExecutionException, TimeoutException {

        long elapsed = System.nanoTime() - startedNanos;
        long remaining = budgetNanos - elapsed;

        if (remaining <= 0) {
            throw new TimeoutException("Request deadline exceeded");
        }
        return future.get(remaining, TimeUnit.NANOSECONDS);
    }

    static Response handle(
            ExecutorService executor,
            RequestContext context,
            Duration budget)
            throws InterruptedException, ExecutionException, TimeoutException {

        if (budget.isNegative() || budget.isZero()) {
            throw new IllegalArgumentException("Budget must be positive");
        }

        long budgetNanos = budget.toNanos();
        long startedNanos = System.nanoTime();

        Future<String> customer = null;
        Future<Integer> stock = null;

        try {
            customer = executor.submit(() -> fetchCustomer(context));
            stock = executor.submit(() -> fetchStock(context));

            String name = awaitWithin(customer, startedNanos, budgetNanos);
            int quantity = awaitWithin(stock, startedNanos, budgetNanos);

            return new Response(name, quantity);
        } finally {
            // Sau khi đã trả response hoặc rời đi vì lỗi,
            // hủy bất kỳ Future nào vẫn còn cần cleanup.
            if (customer != null) customer.cancel(true);
            if (stock != null) stock.cancel(true);
        }
    }

    public static void main(String[] args) throws Exception {
        // Executor sống trong vòng đời application/demo, không đóng ở handle().
        try (ExecutorService executor =
                Executors.newVirtualThreadPerTaskExecutor()) {

            Response ok = handle(
                    executor,
                    new RequestContext("req-ok"),
                    Duration.ofSeconds(2));
            System.out.println("Success: " + ok);

            try {
                handle(
                    executor,
                    new RequestContext("req-slow"),
                    Duration.ofMillis(10));
            } catch (TimeoutException expected) {
                System.out.println("Request timed out");
            }
        }
    }
}
```

Đầu ra điển hình:

```text
Success: Response[customer=Mai, stock=12]
Request timed out
```

Thời gian thực tế còn phụ thuộc scheduler và tải hệ thống. Ví dụ đưa ra kết quả minh họa, không phải SLA thời gian chính xác.

**Vì sao ví dụ an toàn hơn cách dùng hai timeout độc lập?**

1. `startedNanos` được xác định **trước khi submit** các task.
2. Cả hai Future dùng **một** `budgetNanos`.
3. `finally` chạy trong cả trường hợp thành công, `TimeoutException`, `ExecutionException` và `InterruptedException`, yêu cầu cancel các task chưa kết thúc.
4. Mỗi task phản hồi `InterruptedException` từ `Thread.sleep`; đây là điều kiện để request nhanh chóng ngừng công việc thừa.
5. `handle()` **không đóng executor dùng chung**, nên không phá vỡ các request khác.
6. `main` mới là chủ sở hữu executor và chịu trách nhiệm đóng executor khi demo/application kết thúc.

Ví dụ này mô phỏng I/O; trong hệ thống thật cần cấu hình timeout của HTTP/DB client và kiểm soát side effect. Việc `cancel(true)` được gọi trên một Future đã hoàn tất không làm mất kết quả thành công trước đó.

### 7.1. Tại sao không trả partial response sau một task timeout?

Nếu nghiệp vụ yêu cầu cả customer và stock, khi một task thất bại hoặc quá hạn thì việc trả nửa dữ liệu có thể gây sai quyết định. API có thể chọn chính sách **all-or-nothing**, như ví dụ, hoặc **partial fallback** với dữ liệu dự phòng. Hãy quy định trước cách xử lý partial result; không để thứ tự hoàn tất các Future vô tình quyết định chính sách nghiệp vụ.

### 7.2. Phân biệt failure, timeout và interruption

| Tình huống | Biểu hiện tại caller | Cách xử lý gợi ý |
| --- | --- | --- |
| Task hoàn tất | `Future.get` trả kết quả | Tổng hợp dữ liệu theo hợp đồng |
| Task ném exception | `ExecutionException`, nguyên nhân ở `getCause()` | Ghi nhận lỗi, cancel task khác nếu không còn cần |
| Deadline đã hết | `TimeoutException` | Cancel task còn lại, trả lỗi timeout/fallback theo policy |
| Thread handler bị interrupt | `InterruptedException` | Cancel task còn lại; ném tiếp hoặc khôi phục cờ tại boundary |
| Task đã bị cancel | `CancellationException` khi `get()` | Không dùng kết quả, coi như bị hủy |
| Executor từ chối submit | `RejectedExecutionException` | Không giả định request đã được thực thi; xử lý quá tải/shutdown |

Có thể chuyển các tình huống đó thành HTTP 504/503/500 tùy vị trí và hợp đồng hệ thống; **không** có ánh xạ HTTP cố định trong `ExecutorService`.

## 8. Vòng đời executor theo request hay theo application?

Có hai mô hình hợp lệ, với cam kết khác nhau:

### 8.1. Executor riêng mỗi request

```java
static String handleRequestWithOwnExecutor() throws Exception {
    try (ExecutorService executor =
            Executors.newVirtualThreadPerTaskExecutor()) {
        Future<String> task = executor.submit(() -> {
            Thread.sleep(Duration.ofMillis(50));
            return "ok";
        });
        return task.get(1, TimeUnit.SECONDS);
    }
}
```

Ưu điểm: ownership rất rõ; khi method kết thúc, không còn executor do request tạo còn chạy. Nhưng **nếu task không dừng**, `close()` có thể block rất lâu. Mô hình này phù hợp khi tất cả task đã được thiết kế **phản hồi interruption/timeout và đóng I/O** hợp lý.

Nếu thêm catch timeout để gọi `task.cancel(true)`, method vẫn không có lời hứa chắc chắn trả trong đúng 1 giây vì `close()` phải đợi. Do đó không dùng chỉ mô hình này như cơ chế **deadline cứng**.

### 8.2. Executor dùng chung toàn ứng dụng

Một component service có thể nhận `ExecutorService` từ quá trình khởi tạo ứng dụng:

```java
final class DashboardService {
    private final ExecutorService executor;

    DashboardService(ExecutorService executor) {
        this.executor = executor;
    }

    // Handler chỉ submit/cancel Future do mình sở hữu.
    // Nó không gọi executor.shutdown() hoặc executor.close().
}
```

Application đóng executor khi shutdown. Request timeout có thể trả lỗi và cancel Future riêng, không bị **kẹt ở `executor.close()` theo từng request**. Đổi lại, cần quản lý cẩn thận:

- Giới hạn tổng số request/task đang hoạt động.
- Truy vết task bị cancel nhưng không phản hồi interrupt.
- Bảo đảm tài nguyên ngoài JVM có timeout/rollback.
- Không giữ tham chiếu request context vô hạn trong task bị treo.
- Có chính sách shutdown chung khi application ngừng nhận request.

**Virtual-thread-per-task executor không tự giới hạn số task đang chờ.** Nếu chỉ có 20 kết nối DB hoặc 50 lượt gọi API được phép, dùng cơ chế giới hạn tài nguyên (ví dụ `Semaphore`) hoặc backpressure ở tầng nhận request; **không tạo pool virtual threads** chỉ để hạn chế concurrency.

## 9. Đóng executor có giới hạn chờ khi shutdown ứng dụng

Khi ứng dụng dừng, có thể cần **grace period**: cho task đang chạy hoàn tất trong một khoảng thời gian, sau đó thử yêu cầu dừng mạnh hơn. `awaitTermination(timeout, unit)` cung cấp giới hạn chờ cho mỗi lần đợi.

```java
// File: ExecutorShutdown.java
import java.time.Duration;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;

public final class ExecutorShutdown {
    private ExecutorShutdown() {}

    static boolean stop(
            ExecutorService executor,
            Duration graceful,
            Duration forcedWait) {

        if (graceful.isNegative() || forcedWait.isNegative()) {
            throw new IllegalArgumentException("Durations must not be negative");
        }

        executor.shutdown(); // Không nhận task mới

        try {
            if (executor.awaitTermination(
                    graceful.toNanos(), TimeUnit.NANOSECONDS)) {
                return true;
            }

            executor.shutdownNow(); // Best effort: interrupt task còn chạy
            return executor.awaitTermination(
                    forcedWait.toNanos(), TimeUnit.NANOSECONDS);

        } catch (InterruptedException e) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
            return false;
        }
    }
}
```

Ví dụ sử dụng trong **application shutdown hook hoặc logic đóng service**:

```java
ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor();
try {
    // App sử dụng executor cho các request...
} finally {
    boolean terminated = ExecutorShutdown.stop(
            executor, Duration.ofSeconds(2), Duration.ofSeconds(1));
    if (!terminated) {
        System.err.println("Executor còn task chưa dừng");
    }
}
```

Điểm cần nhớ:

- Đoạn này chủ ý **không** bọc executor trong `try-with-resources`. Nếu thêm `close()` tự động sau helper, ứng dụng có thể lại chờ **không giới hạn**, làm mất ý nghĩa các lần `awaitTermination` có timeout.
- `shutdownNow()` không bảo đảm các task bất hợp tác đã dừng. `false` nghĩa là sau thời gian đã cho, executor **chưa được xác nhận terminated**; ứng dụng phải theo dõi hoặc xử lý theo chính sách vận hành.
- Khi thread gọi shutdown bị interrupt, helper yêu cầu dừng và **khôi phục interrupted status** rồi trả `false`.
- `Duration.toNanos()` cần dữ liệu giới hạn hợp lý, không lấy duration cực lớn không kiểm soát.
- Một ứng dụng shutdown an toàn còn phải dừng nhận request mới, kiểm soát việc trả task còn chờ, và xử lý các tài nguyên ngoài executor.

**Không dùng `Thread.stop()` để cố đạt SLA shutdown.** API cưỡng bức này không an toàn. Khả năng chấm dứt trong thời gian hữu hạn phụ thuộc vào thiết kế task và hệ thống bên ngoài.

## 10. invokeAll(timeout) và invokeAny(timeout) cho nhóm tác vụ

Nếu có một tập task biết trước, `ExecutorService` có các phép thao tác nhóm đã hỗ trợ timeout.

### 10.1. invokeAll với timeout tổng

```java
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

List<Callable<String>> tasks = List.of(
    () -> { Thread.sleep(40); return "profile"; },
    () -> { Thread.sleep(80); return "stock"; }
);

List<Future<String>> futures =
        executor.invokeAll(tasks, 100, TimeUnit.MILLISECONDS);

for (Future<String> future : futures) {
    if (future.isCancelled()) {
        System.out.println("Một task đã bị hủy");
    } else {
        System.out.println(future.get());
    }
}
```

Đây là mảnh code đặt bên trong method có `ExecutorService executor` và khai báo/giải quyết checked exceptions. `invokeAll(tasks, timeout, unit)` chờ cho tất cả task hoàn tất hoặc hết timeout, rồi **cancel những task chưa hoàn tất** theo hợp đồng. Danh sách Future được trả về theo thứ tự task đầu vào, **không** phải thứ tự hoàn tất.

Không suy ra rằng `Future.isDone()` đồng nghĩa các task được hủy đã hoàn tất cleanup. Như các API cancel khác, phần thực thi có thể còn đang phản hồi interruption.

### 10.2. invokeAny với timeout

Khi chỉ cần **một kết quả thành công** từ nhiều nguồn độc lập:

```java
String firstSuccessful = executor.invokeAny(
    List.of(
        () -> readReplicaA(),
        () -> readReplicaB()
    ),
    200,
    TimeUnit.MILLISECONDS
);
```

Giả định `readReplicaA/B()` là các method do ứng dụng định nghĩa, trả `String` và có thể ném exception. Khi có một task thành công, `invokeAny` trả kết quả đó và hủy những task không cần; nếu không có task thành công trước thời hạn, nó ném `TimeoutException` hoặc các exception thích hợp. Không dùng `invokeAny` nếu nghiệp vụ **cần tất cả kết quả**.

### 10.3. CompletableFuture.orTimeout cũng không phải hủy I/O

`CompletableFuture.orTimeout(...)` thiết lập để CompletableFuture **hoàn tất bất thường bằng `TimeoutException`** nếu chưa xong trước hạn. Điều này hữu ích cho API compositional, nhưng **không đồng nghĩa** thread/call I/O gốc đã bị hủy. Với tác vụ thực thi qua executor, vẫn cần thiết kế cơ chế cancellation/timeout ở nguồn công việc theo hợp đồng của thư viện đang dùng.

## 11. Quản lý ngữ cảnh request khi task chạy trên virtual threads

Một request thường mang các thông tin như request ID, tenant ID, time budget và quyền hạn. Đừng dùng một biến `static` có thể ghi để giữ “request hiện tại”: nhiều task chạy đồng thời sẽ ghi đè nhau.

### 11.1. Cách đơn giản và rõ ràng: truyền context bất biến

```java
record RequestContext(String requestId, String tenantId) {}

static String fetch(RequestContext context) {
    return "request=" + context.requestId()
            + ", tenant=" + context.tenantId();
}

// Khi submit:
Future<String> future = executor.submit(() -> fetch(context));
```

Đoạn này giả định `executor` và `context` là biến trong scope của handler. Lambda **capture** tham chiếu context. Với các component là immutable, việc truyền bằng tham số giúp audit rõ task được phép dùng dữ liệu nào và không phụ thuộc cơ chế thread-local ngầm định.

**Cần kiểm tra vòng đời của context:** nếu task tiếp tục sau khi request hết hạn, nó không được tham chiếu tài nguyên đã bị đóng (ví dụ response writer, session hay DB connection thuộc handler). Hạn chế capture cả object request nếu nó mang nhiều dữ liệu nhạy cảm hoặc tài nguyên mutable; chỉ truyền trường cần thiết.

### 11.2. ScopedValue và ThreadLocal

Trong Java 27, `ScopedValue` là API đã chính thức cho giá trị được ràng buộc theo phạm vi thực thi, có thể hữu ích khi cần truyền ngữ cảnh qua nhiều method mà không thêm một tham số vào mọi tầng.

```java
import java.lang.ScopedValue;

public class RequestScopeDemo {
    private static final ScopedValue<String> REQUEST_ID =
            ScopedValue.newInstance();

    public static void main(String[] args) {
        ScopedValue.where(REQUEST_ID, "req-007").run(() -> {
            System.out.println(REQUEST_ID.get()); // req-007
        });
    }
}
```

Việc binding có vòng đời rõ ràng trong thân `run(...)`. **Không tự giả định** rằng một lambda được gửi vào bất kỳ `ExecutorService` nào cũng tự nhận binding `ScopedValue` của thread gọi; propagation phụ thuộc mô hình API và cấu trúc công việc. Khi dùng executor task không có hợp đồng thừa kế ngữ cảnh rõ ràng, **truyền context tường minh** vào task như mục trước.

`ThreadLocal` vẫn là API được hỗ trợ, nhưng với rất nhiều virtual threads, mỗi thread mang nhiều giá trị thread-local có thể tốn bộ nhớ và gây rò rỉ logic nếu không quản lý đúng vòng đời. Với code mới, ưu tiên tham số hoặc scoped value khi phù hợp; không biến thread-local thành nơi lưu state mutable toàn cục.

## 12. Timeout và interruption không đủ để bảo đảm tính đúng đắn

Ngay cả khi ứng dụng xử lý đúng `InterruptedException`, có nhiều loại công việc cần chính sách bổ sung:

### 12.1. I/O bên ngoài phải có timeout riêng

- **HTTP:** cấu hình thời gian kết nối và timeout của request ở client; khi cần, hủy/đóng response body đúng cách.
- **Database:** cấu hình timeout truy vấn, timeout lấy kết nối và hành vi hủy của driver; xác định ranh giới transaction/rollback.
- **Message broker:** điều chỉnh timeout publish/ack, retry và cơ chế hủy theo API.
- **File/Socket:** xác định thao tác nào interruptible và ai sở hữu stream/socket cần đóng.

Một `Future.get(100 ms)` không khiến một truy vấn ở DB bị đặt timeout 100 ms trừ khi ứng dụng **chủ động truyền** thời hạn/timeout tương ứng tới client.

### 12.2. Cancellation token chỉ hữu ích khi task kiểm tra

Nếu ứng dụng bổ sung một cờ `AtomicBoolean cancelled` để phản ánh trạng thái request, hãy kiểm tra nó tại các điểm hợp lý trong công việc. Cờ hủy không tự ngắt socket đang chờ; có thể kết hợp với interrupt và I/O timeout.

Với tác vụ thực hiện ghi, kiểm tra trạng thái request **trước khi commit** có thể hữu ích, nhưng không thể loại bỏ mọi race giữa lần kiểm tra và lần ghi. Cần idempotency/transaction/versioning ở tầng có quyền quyết định cuối cùng.

### 12.3. StructuredTaskScope là preview trong Java SE 27

`StructuredTaskScope` nhắm tới mô hình structured concurrency: một phạm vi sở hữu các subtask và quản lý kết thúc/hủy theo vòng đời của phạm vi. Tuy nhiên, **Javadoc Java SE 27 đánh dấu nó là preview API**, cần tùy chọn preview khi biên dịch/chạy và có thể thay đổi qua phiên bản.

Vì bài học ưu tiên **các API ổn định**, các ví dụ sử dụng `ExecutorService`, `Future` và `try-with-resources`. Không sao chép ví dụ `StructuredTaskScope` từ một preview JDK khác rồi khẳng định chúng là mã Java 27 ổn định.

## 13. Tình huống lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `Future.get(timeout)` hết hạn nhưng task vẫn chạy | Timeout chỉ giới hạn caller chờ | Gọi `cancel(true)` khi không cần kết quả; bảo đảm task hợp tác |
| Request có 300 ms nhưng hai lần `get(300 ms)` chờ gần 600 ms | Dùng timeout riêng mỗi bước | Dùng deadline chung, truyền thời gian còn lại |
| Sau khi timeout, method vẫn không trả nhanh | `ExecutorService.close()` đang đợi task kết thúc | Phân biệt ownership; bảo đảm task có I/O timeout/hủy hợp tác |
| Đã gọi `cancel(true)` nhưng có side effect đến muộn | Hủy không rollback thao tác bên ngoài | Idempotency, transaction, version check, timeout I/O |
| `Future.isDone() == true` nhưng vẫn thấy tài nguyên đang dùng | Future đã cancel, worker chưa hoàn tất cleanup | Không xem trạng thái Future là bằng chứng thread đã dừng |
| Caller bị interrupt nhưng handler vẫn tiếp tục | Nuốt `InterruptedException` hoặc quên hủy task con | Ném tiếp/khôi phục cờ, cancel Future trong `finally` |
| Vòng lặp CPU bỏ qua cancel | Không kiểm tra interrupted/cancelled state | Kiểm tra định kỳ và thoát theo policy |
| `shutdownNow()` trả về nhưng còn task | `shutdownNow` là best effort, không đợi | `awaitTermination` và xử lý task không hợp tác |
| Request A timeout làm request B bị từ chối | A đóng shared executor | Chỉ app shutdown executor; request chỉ cancel Future của mình |
| Đóng executor trong một task do chính executor chạy | Tự đợi vòng đời của executor đang chứa mình | Để owner bên ngoài task quản lý shutdown |
| Số virtual threads lớn làm DB quá tải | Virtual thread không giới hạn tài nguyên ngoài | Pool DB, `Semaphore` hoặc backpressure |
| Task không thấy request context | Giả định context tự truyền sang thread mới | Capture context bất biến, hoặc dùng propagation theo hợp đồng rõ |
| `CompletableFuture.orTimeout` có lỗi timeout nhưng I/O vẫn chạy | Timeout Future không đồng nghĩa cancellation của nguồn | Thiết kế hủy nguồn và timeout client |
| `invokeAll(timeout)` trả Future đã cancel nhưng task chưa dừng ngay | Cancellation hợp tác | Thiết kế cleanup và quản lý tài nguyên |
| `close()` bị interrupt nhưng vẫn block | Theo Javadoc: shutdownNow rồi vẫn chờ kết thúc | Không dùng close như bounded shutdown; quản lý tác vụ cho phép thoát |
| Sử dụng StructuredTaskScope rồi cần `--enable-preview` | API vẫn là preview trong Java 27 | Với bài học stable dùng `ExecutorService`/`Future` |

## 14. Checklist thiết kế vòng đời request

1. **Ai sở hữu executor?** App hay request? Mỗi request chỉ được đóng executor do nó thực sự sở hữu.
2. **Có deadline chung chưa?** Tính ngân sách còn lại thay vì cấp lại toàn bộ timeout cho từng `get`.
3. **Đã phân biệt timeout và cancellation?** `get(timeout)` không tự cancel task.
4. **Task có phản hồi interrupt không?** Kiểm tra cờ trong CPU loop, xử lý `InterruptedException` ở blocking operations.
5. **Có I/O timeout riêng không?** Không chỉ dựa vào `Future` để dừng network/DB.
6. **Có thu hồi task thất bại/hết hạn không?** Dùng `finally` và `cancel(true)` cho Future không còn cần.
7. **Có ngăn side effect đến muộn không?** Xác định transaction, idempotency và cơ chế chống commit sai trạng thái.
8. **Có hiểu `close()` không?** Nó đợi executor terminated; không có timeout cấu hình trực tiếp.
9. **Có bounded shutdown cho app không?** `shutdown → awaitTermination → shutdownNow → awaitTermination` là lựa chọn có kiểm soát khi phù hợp.
10. **Có xử lý interruption ở caller không?** Ném tiếp hoặc khôi phục cờ trước khi kết thúc boundary; không nuốt lỗi.
11. **Có kiểm soát concurrency đến DB/API không?** Virtual threads không thay thế quota hoặc giới hạn số kết nối.
12. **Ngữ cảnh task có bất biến và tối thiểu không?** Truyền request ID/deadline cần thiết, không chia sẻ object request mutable bừa bãi.
13. **Có kiểm thử đầy đủ?** Test task xong sớm, xong muộn, throw exception, cancel trước khi chạy, task không đáp ứng interrupt, caller bị interrupt và shutdown executor.
14. **Có observability?** Ghi metric về thời gian chờ, timeout, task còn chạy sau cancel, queue size, số kết nối và lỗi cleanup.
15. **Dùng API ổn định?** Với Java 27, `StructuredTaskScope` vẫn là preview; không dùng làm mã mặc định nếu chính sách tránh preview.

## Tài liệu tham khảo chính thức (Java SE 27)

- [`ExecutorService` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ExecutorService.html) — `shutdown()`, `shutdownNow()`, `awaitTermination()`, `close()`, `invokeAll/invokeAny`.
- [`Executors` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Executors.html) — `newVirtualThreadPerTaskExecutor()` và factory executor khác.
- [`Future<V>` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Future.html) — `get(timeout,unit)`, `cancel`, `isCancelled`, `isDone` và exception.
- [`Thread` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Thread.html) — interruption, virtual threads và `Thread.sleep(Duration)`.
- [`TimeUnit` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/TimeUnit.html) — đo thời lượng và đổi đơn vị.
- [`CompletableFuture` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/CompletableFuture.html) — `orTimeout` và mô hình hoàn tất bất đồng bộ.
- [`ScopedValue` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ScopedValue.html) — ngữ cảnh ràng buộc theo scope thực thi.
- [`StructuredTaskScope` — Java SE 27 API (preview)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html) — mô tả trạng thái preview, không được sử dụng như API ổn định trong ví dụ.
- [Oracle Java SE 27: Virtual Threads](https://docs.oracle.com/en/java/javase/27/core/virtual-threads.html) — hướng dẫn workload, quản lý thread và giới hạn tài nguyên.
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444) — virtual threads chính thức từ Java 21.
