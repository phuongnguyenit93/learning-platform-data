# ExecutorService.close() và try-with-resources từ Java 21: điều kiện chờ kết thúc

## 1. Vấn đề: tạo executor xong thì khi nào các task thực sự kết thúc?

Một `ExecutorService` có thể nhận rất nhiều công việc (`Runnable`, `Callable`), rồi phân phối chúng cho worker thread hoặc một cơ chế thực thi khác. Khi một phương thức không còn cần gửi việc mới, ta phải quyết định **khi nào ngừng nhận việc**, **có chờ các task đã gửi chạy xong không**, **có hủy chúng khi chờ quá lâu không** và **khi nào được xem pool đã kết thúc thật sự**.

Trong Java 21, `ExecutorService` đã là một `AutoCloseable` và có phương thức `close()`. Vì thế có thể dùng:

```java
try (ExecutorService executor = Executors.newFixedThreadPool(2)) {
    executor.execute(() -> doWork());
} // close() được gọi tự động khi thoát try.
```

Đây là **snippet**, cần import `ExecutorService`, `Executors` và định nghĩa `doWork()`. Các chương trình hoàn chỉnh ở phần sau có thể biên dịch và chạy bằng JDK 21.

**Điểm cốt lõi:** mặc định, `close()` khởi động một **orderly shutdown** và **chờ tới khi các task đã nhận hoàn tất thực thi và executor terminated**. Nó **không** đơn thuần là đặt một cờ “đã đóng”, cũng **không** giống `shutdownNow()` ngay từ đầu.

**Mốc phiên bản chính xác:** API `ExecutorService.close()` và việc `ExecutorService` mở rộng `AutoCloseable` được bổ sung từ **Java 19**. Java 21 là một phiên bản LTS thường được dùng để áp dụng chính thức mô hình này cùng các tính năng mới như virtual threads. Vì vậy bài tập dùng **JDK 21+**; đoạn `try (ExecutorService executor = ...)` **không biên dịch với JDK 17** nếu static type của resource là `ExecutorService`.

Bài học chỉ nói về **Java concurrency nói chung**, không gắn với Spring hoặc framework khác.

## 2. Những trạng thái cần phân biệt trong vòng đời ExecutorService

| Khái niệm/API | Ý nghĩa |
| --- | --- |
| `execute()` / `submit()` | Gửi một task vào executor |
| `shutdown()` | Yêu cầu ngừng nhận task mới, cho phép task đã nhận tiếp tục chạy |
| `shutdownNow()` | Cố ngừng task đang thực thi (thường bằng interrupt) và không bắt đầu task còn đang chờ; nỗ lực **best effort** |
| `isShutdown()` | Executor đã bắt đầu quá trình shutdown, **không** có nghĩa đã kết thúc |
| `isTerminated()` | Executor đã thực sự kết thúc sau shutdown |
| `awaitTermination(timeout, unit)` | Thread gọi **chờ có hạn** đến khi executor terminated; trả boolean hoặc ném `InterruptedException` |
| `close()` | Tự khởi động orderly shutdown và **chờ kết thúc**; xử lý interrupt theo quy tắc riêng, **không có tham số timeout** |

Mối quan hệ:

```text
        đang nhận task
               |
      shutdown() / close()
               |
               v
     đã shutdown, đang drain
      |                    |
      | task hoàn tất      | nếu close() bị interrupt khi chờ:
      |                    | chuyển sang shutdownNow() kiểu best effort
      v                    v
      executor terminated (không còn task chạy/chờ)
               |
       close() mới trả về bình thường
```

Một lời gọi `shutdown()` **trả về ngay** sau khi đưa ra yêu cầu; task có thể vẫn chạy. Một lời gọi `close()` bình thường **không trở về** cho đến khi executor kết thúc. `awaitTermination()` thì cho phép chỉ **đợi có giới hạn**, nhưng caller phải tự quyết định làm gì nếu hết hạn.

### “Task đã hoàn tất” không nhất thiết là “nghiệp vụ thành công”

Một `Callable` kết thúc bằng exception vẫn là task đã hoàn tất thực thi, có thể khiến `Future.get()` ném `ExecutionException`. `close()` không tự gom những exception đó rồi ném lại cho caller; nó chờ kết thúc **vòng đời thực thi**, không đánh giá thành công nghiệp vụ. Khi cần kết quả/lỗi, hãy quản lý `Future` hoặc một cơ chế báo outcome khác.

## 3. Chính xác thì ExecutorService.close() làm gì?

Theo hợp đồng của **JDK 21**:

1. **Orderly shutdown:** các task đã nộp trước thời điểm shutdown được tiếp tục xử lý theo chính sách executor; từ chối việc nộp mới.
2. **Đợi termination:** thread gọi `close()` chờ cho tới khi executor đã thực sự kết thúc. Đây là điểm khiến `close()` có thể **blocking**.
3. **Nếu thread đang đợi bị interrupt:** `close()` chuyển sang nỗ lực dừng task đang thực thi **như gọi `shutdownNow()`**, và những task vẫn đang nằm trong hàng chờ **không được chạy** theo hợp đồng.
4. **Tiếp tục chờ task đang thực thi dừng:** sau khi yêu cầu dừng, `close()` vẫn chờ các task đang hoạt động kết thúc. Interrupt không khiến phương thức tự bỏ chờ ngay.
5. **Khôi phục interrupt status:** trước khi trở về, cờ interrupt của thread gọi được đặt lại.
6. **Nếu executor đã terminated:** gọi `close()` không còn tác dụng.

**Hệ quả quan trọng:** `close()` không khai báo ném `InterruptedException`. Người gọi **không thể** viết `catch (InterruptedException)` chỉ để bắt từ `close()` nếu trong khối tương ứng không có API nào khác ném checked exception đó. Khi bị interrupt trong giai đoạn chờ, `close()` xử lý theo quy tắc trên và đặt lại cờ trước lúc trả về.

**Đừng hiểu “shutdownNow” là kill mạnh:** việc dừng task đang chạy thường được yêu cầu thông qua `Thread.interrupt()`. Nếu task đang ở I/O không thể bị ngắt hoặc cố tình bỏ qua interrupt, executor có thể **chậm kết thúc hoặc không bao giờ terminated**; `close()` vì vậy cũng có thể chờ rất lâu. API không cung cấp một hard timeout tự động.

### Không có lời hứa “đóng resource là dừng tất cả ngay”

Try-with-resources đảm bảo gọi `close()` khi rời scope, **không** bảo đảm đóng trong vài mili-giây. Nếu task chờ một sự kiện mà chỉ code **sau khối try** mới có thể phát tín hiệu, thread gọi có thể tự mắc kẹt tại `close()`. Phải thiết kế dependency để task có khả năng hoàn tất **trước khi cần đi qua dòng code sau try**.

## 4. Java 21+: chương trình đầu tiên với try-with-resources

Tạo file `CloseWaitDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

public class CloseWaitDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch mayFinish = new CountDownLatch(1);
        AtomicInteger completed = new AtomicInteger();

        try (ExecutorService executor = Executors.newSingleThreadExecutor()) {
            executor.execute(() -> {
                started.countDown();
                try {
                    mayFinish.await();
                    completed.incrementAndGet();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });

            started.await();
            System.out.println("Inside try, completed: " + completed.get());
            mayFinish.countDown();
        }

        System.out.println("After close, completed: " + completed.get());
    }
}
```

Biên dịch/chạy bằng **JDK 21 trở lên**:

```bash
javac CloseWaitDemo.java
java CloseWaitDemo
```

Đầu ra khi không có interrupt từ bên ngoài:

```text
Inside try, completed: 0
After close, completed: 1
```

**Tại sao đầu ra ổn định?**

- Worker báo đã khởi động qua `started.countDown()` nhưng chưa được qua `mayFinish.await()`.
- Main chờ `started.await()` rồi in số task hoàn tất. Cổng vẫn đóng nên bộ đếm chắc chắn là 0.
- Main mở cổng và thoát `try`; `close()` được gọi tự động. Nếu worker chưa tăng bộ đếm, close còn phải chờ worker kết thúc.
- Dòng `After close` được thực thi **sau khi close trả về**, nên khi task hoàn tất bình thường kết quả là 1.

Đây là ví dụ với executor một worker để phân biệt rõ **thoát scope** và **termination**. Trong ứng dụng có nhiều task, close đợi tất cả task đã được nhận theo cơ chế orderly shutdown, không chỉ task cuối cùng được submit.

### Có cần Future.get() trước khi rời try không?

**Không bắt buộc nếu chỉ cần chờ task hoàn tất** theo mô hình `close()`. Nhưng nếu cần **giá trị trả về** hoặc **nguyên nhân thất bại**, vẫn cần `Future.get()` hoặc một cơ chế báo kết quả. `close()` chỉ chờ vòng đời, không trả một danh sách kết quả như `invokeAll()`.

## 5. Phân biệt close() với shutdown(), awaitTermination() và shutdownNow()

| Cách | Có yêu cầu ngừng nhận task mới? | Tự chờ kết thúc? | Có deadline chờ? |
| --- | --- | --- | --- |
| `shutdown()` | Có | Không | Không |
| `shutdownNow()` | Có, đồng thời cố dừng task đang chạy | Không | Không |
| `shutdown(); awaitTermination(timeout, unit)` | Có | Có, **tối đa theo timeout** cho mỗi lần await | Có |
| `close()` | Có | Có, đến khi executor terminated | **Không** |
| `try (ExecutorService e = ...)` | Có khi rời scope | Có qua `close()` | **Không** |

**Không gọi `awaitTermination()` trước `shutdown()` rồi mong executor tự dừng:** `awaitTermination` chỉ chờ termination, không tự yêu cầu shutdown. Nếu executor vẫn nhận việc và chưa có ai shutdown, lời gọi có thể timeout mà không thay đổi trạng thái pool.

**Không suy rằng `shutdownNow()` đã dừng xong:** phương thức này trả về danh sách task **đang chờ chưa bắt đầu** theo hợp đồng và cố tác động đến task đang chạy. Nó không chờ thread thực sự chấm dứt. Muốn kiểm tra kết thúc, dùng `awaitTermination()` hoặc `isTerminated()`.

### Khi nào nên chọn close()?

Phù hợp khi một scope sở hữu riêng executor, số task hữu hạn, task có thể kết thúc, và muốn chắc rằng **không còn task của executor đang chạy khi ra khỏi scope**.

Ví dụ fan-out theo yêu cầu: tạo executor, gửi ba Callable độc lập, thu thập kết quả rồi kết thúc phương thức. Try-with-resources giúp người viết không quên shutdown dù đường xử lý ném exception.

### Khi nào không nên dùng close() trực tiếp?

- Cần một **thời hạn kết thúc hữu hạn** (SLA, graceful shutdown 5 giây, rồi chuyển sang shutdownNow).
- Executor là **tài nguyên dùng chung**, do thành phần khác sở hữu và có các request khác đang dùng; một scope nhỏ không được đóng nó.
- Task có thể **chạy định kỳ vô hạn**, đợi sự kiện không thể phát ra trước khi ra khỏi scope, hoặc làm I/O không có điểm hủy.
- Một đoạn code đang giữ lock mà task cần mới có thể kết thúc; close trong lúc giữ lock có thể tạo deadlock.
- Cần kiểm soát thời điểm/chiến lược stop và quan sát các task chưa thực thi.

Trong các tình huống đó, thiết kế lifecycle riêng với `shutdown`, `awaitTermination` và `shutdownNow` phù hợp hơn; hoặc bảo đảm task kết thúc trước khi scope đóng.

## 6. Java 21+: giá trị và lỗi phải lấy qua Future

Dù mọi task đã dừng, `close()` không biết khái niệm nghiệp vụ “thành công” của task. Ví dụ một task thất bại thì try-with-resources vẫn đóng pool, và caller phải xem Future nếu muốn báo lỗi.

Tạo file `CloseWithFutureDemo.java`:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class CloseWithFutureDemo {
    public static void main(String[] args)
            throws InterruptedException, ExecutionException {
        try (ExecutorService executor = Executors.newFixedThreadPool(2)) {
            Future<Integer> ok = executor.submit(() -> 6 * 7);

            Callable<String> failing = () -> {
                throw new IllegalArgumentException("invalid");
            };
            Future<String> bad = executor.submit(failing);

            System.out.println("Value: " + ok.get());

            try {
                System.out.println("Other: " + bad.get());
            } catch (ExecutionException e) {
                System.out.println("Task error: "
                        + e.getCause().getClass().getSimpleName());
            }
        }

        System.out.println("Executor scope ended");
    }
}
```

Biên dịch/chạy:

```bash
javac CloseWithFutureDemo.java
java CloseWithFutureDemo
```

Đầu ra:

```text
Value: 42
Task error: IllegalArgumentException
Executor scope ended
```

- Task thứ nhất trả về 42.
- Task thứ hai ném `IllegalArgumentException`; `Future.get()` của nó ném `ExecutionException` chứa nguyên nhân.
- `close()` được gọi dù có exception ở bên trong scope. Ở đây exception từ `bad.get()` đã được xử lý; nếu không bắt, try-with-resources vẫn gọi close trước khi exception được truyền ra ngoài.
- Không được đọc việc đã đến cuối `close()` như bằng chứng rằng tất cả task đều trả kết quả thành công.

**Đặc biệt:** sau khi một exception thoát khỏi khối `try`, quá trình auto-close diễn ra **trước khi** exception được xử lý ở tầng ngoài. Nếu task còn chạy lâu hoặc kẹt, việc báo lỗi ra ngoài có thể bị trì hoãn vì đang chờ close.

## 7. Java 21+: close() khi caller đã nhận interrupt

Khi thread gọi `close()` đang chờ mà nhận interrupt, default implementation chuyển sang nỗ lực dừng các task theo hướng `shutdownNow()`, tiếp tục đợi các task đang chạy kết thúc rồi khôi phục interrupt status.

Có thể kiểm chứng bằng một task đang chờ latch. Tạo file `InterruptedCloseDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

public class InterruptedCloseDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch neverOpens = new CountDownLatch(1);
        AtomicBoolean workerSawInterrupt = new AtomicBoolean();

        try (ExecutorService executor = Executors.newSingleThreadExecutor()) {
            executor.execute(() -> {
                started.countDown();
                try {
                    neverOpens.await();
                } catch (InterruptedException e) {
                    workerSawInterrupt.set(true);
                    Thread.currentThread().interrupt();
                }
            });

            started.await();
            // Gửi interrupt cho chính caller trước lúc auto-close.
            Thread.currentThread().interrupt();
        }

        System.out.println("Worker interrupted: "
                + workerSawInterrupt.get());
        System.out.println("Caller flag restored: "
                + Thread.currentThread().isInterrupted());

        // Chỉ xóa cờ để bản demo kết thúc gọn.
        Thread.interrupted();
    }
}
```

Chạy bằng JDK 21+:

```bash
javac InterruptedCloseDemo.java
java InterruptedCloseDemo
```

Đầu ra khi không có tác động khác vào các thread:

```text
Worker interrupted: true
Caller flag restored: true
```

Giải thích:

1. Worker đã chạy và báo `started`, nhưng đang hoặc sắp chờ `neverOpens.await()`.
2. Caller tự đặt interrupt status trước khi ra khỏi scope. Khi `close()` đợi termination, việc chờ thấy interrupt và chuyển sang cơ chế nỗ lực stop giống `shutdownNow()`.
3. Worker nhận interrupt. Dù interrupt tới trước khi `await()` thực sự bắt đầu, lần await tiếp theo cũng phát hiện cờ và ném `InterruptedException`.
4. Worker bắt exception và kết thúc. Close **vẫn đợi** worker kết thúc thực thi, sau đó trả về với cờ caller được khôi phục.
5. Cờ của caller còn true sau close, không phải vì close ném `InterruptedException`.

**Đừng sao chép mẫu cố ý interrupt caller vào logic bình thường:** ví dụ này chỉ làm rõ hợp đồng của close. Trong ứng dụng thật, interrupt thường do yêu cầu hủy/shutdown đến từ một thành phần khác. Nếu task không phản hồi interrupt, close có thể vẫn chờ mãi, vì vậy không thể dùng close như giải pháp timeout.

## 8. Task không hợp tác interrupt có thể khiến close không kết thúc

Một task có thể:

- Lặp tính toán CPU mà **không kiểm tra `isInterrupted()`**.
- Chặn ở một điểm không interruptible, chẳng hạn chờ monitor `synchronized` đang do thread khác giữ.
- Gặp I/O có semantics interrupt riêng mà hệ thống không hỗ trợ dừng nhanh.
- Chờ một latch/condition mà tín hiệu hoàn tất chỉ được gửi **sau khi close trả về**.
- Gọi `Future.get()` trên một task khác trong cùng pool nhỏ gây thread starvation deadlock.

Trong các tình huống này, `close()` không cung cấp lối thoát timeout. Việc caller nhận interrupt chỉ thúc đẩy yêu cầu `shutdownNow()`, **không hứa toàn bộ mã task buộc phải dừng**.

### Mẫu tự deadlock cần tránh

```java
// Snippet NGUY HIỂM, không phải chương trình độc lập.
CountDownLatch mayFinish = new CountDownLatch(1);

try (ExecutorService executor = Executors.newSingleThreadExecutor()) {
    executor.execute(() -> {
        try {
            mayFinish.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    });
}

// Dòng này không tới được nếu close vẫn chờ worker:
mayFinish.countDown();
```

Nếu không có interrupt hay nguồn tín hiệu nào khác, task chờ latch; `close()` chờ task; code mở latch lại nằm **sau close**. Đó là chu trình chờ khiến chương trình có thể treo vô hạn.

**Sửa:** chuyển `mayFinish.countDown()` vào trước lúc thoát scope, hoặc thiết kế producer/timer/cancellation không phụ thuộc vào thread đang bị block ở close.

### Lock giữ trong lúc đóng executor

Nếu caller giữ `synchronized(lock)` rồi thoát try-with-resources bên trong vùng đó, mà một worker cần **cùng lock** để kết thúc, caller chờ close và worker chờ lock. Dù mọi API đều “thread-safe” riêng, tổ hợp vẫn deadlock. Trước khi đóng executor, tránh giữ các khóa/tài nguyên mà task cần để hoàn tất.

## 9. Java 17: cách quản lý vòng đời tương đương về mục tiêu

Trong Java 17, `ExecutorService` **chưa** mở rộng `AutoCloseable` và chưa có `close()`. Mẫu shutdown truyền thống phải viết rõ.

Tạo file `LegacyShutdownDemo.java`, có thể chạy Java 17+:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class LegacyShutdownDemo {
    private static void stopWithinBudget(ExecutorService pool) {
        pool.shutdown();
        try {
            if (!pool.awaitTermination(2, TimeUnit.SECONDS)) {
                pool.shutdownNow();
                if (!pool.awaitTermination(2, TimeUnit.SECONDS)) {
                    System.err.println("Pool has not terminated");
                }
            }
        } catch (InterruptedException e) {
            pool.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            Future<Integer> answer = pool.submit(() -> 40 + 2);
            System.out.println("Answer: " + answer.get());
        } finally {
            stopWithinBudget(pool);
        }
    }
}
```

Chạy với JDK 17 hoặc mới hơn:

```bash
javac LegacyShutdownDemo.java
java LegacyShutdownDemo
```

Đầu ra khi task hoàn tất bình thường:

```text
Answer: 42
```

So sánh với `close()`:

- `stopWithinBudget` cho pool **2 giây chờ orderly shutdown**, rồi yêu cầu `shutdownNow()` và đợi thêm **2 giây**. Sau đó nó có thể **trả về ngay cả khi pool chưa terminated** (đã ghi cảnh báo).
- `close()` mặc định chờ executor terminated **không giới hạn timeout**, kể cả sau khi chuyển sang shutdownNow vì bị interrupt.
- Ở ví dụ Java 17, xử lý `InterruptedException` của thread caller khởi động shutdownNow rồi **khôi phục cờ**, nhưng không tiếp tục chờ vô hạn.
- Đây là **hai hợp đồng khác nhau**. Dùng try-with-resources vì gọn **không tương đương** với shutdown có deadline nghiệp vụ.

**Một lưu ý riêng về process:** worker thread của các executor thông thường có thể khiến JVM tiếp tục chạy ngay cả khi caller ngừng chờ; việc gọi `shutdownNow()` cũng không bảo đảm worker đã dừng. Thiết kế shutdown cần theo dõi và xử lý task không phản hồi cancellation.

## 10. Virtual threads từ Java 21 và try-with-resources

Java 21 đưa virtual threads thành tính năng chính thức; `Executors.newVirtualThreadPerTaskExecutor()` tạo executor dùng **một virtual thread cho mỗi task**. Executor này cũng là `ExecutorService` nên hưởng lợi từ `close()`/try-with-resources.

Tạo file `VirtualThreadScopeDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class VirtualThreadScopeDemo {
    public static void main(String[] args) throws Exception {
        try (ExecutorService executor =
                Executors.newVirtualThreadPerTaskExecutor()) {
            Future<Integer> first = executor.submit(() -> 10);
            Future<Integer> second = executor.submit(() -> 20);

            System.out.println("Total: " + (first.get() + second.get()));
        }

        System.out.println("All scoped tasks ended");
    }
}
```

Chạy bằng JDK 21+:

```bash
javac VirtualThreadScopeDemo.java
java VirtualThreadScopeDemo
```

Đầu ra:

```text
Total: 30
All scoped tasks ended
```

Điểm cần hiểu:

- Executor tạo virtual thread cho từng task; không đồng nghĩa 2 task **đồng thời chạy CPU** hoặc phải hoàn tất theo thứ tự submit.
- `Future.get()` lấy kết quả của task, còn `close()` bảo đảm phạm vi executor đã kết thúc trước khi dòng cuối chạy.
- Virtual threads giúp mở rộng mô hình nhiều task blocking trong nhiều tình huống, **không sửa tự động** data race, deadlock, giao dịch hoặc task bỏ qua cancellation.
- Không tạo virtual thread executor ở mỗi tầng nhỏ nếu không hiểu ownership và thời điểm đóng; scope chỉ nên đóng những executor **mà chính scope sở hữu**.

### Vì sao close của virtual-thread-per-task executor đáng lưu ý?

Ví dụ fan-out: trong một hàm, gửi N lời gọi độc lập, chờ kết quả rồi đóng scope. Nếu một task vẫn còn chạy hoặc bị treo, `close()` có thể giữ hàm chưa trả về, dù virtual thread nhẹ hơn platform thread. Điều đó vừa có lợi (không bỏ quên task) vừa là rủi ro (chờ vô hạn) nếu deadline và cancellation chưa được thiết kế.

## 11. Trường hợp ScheduledExecutorService và task định kỳ

`ScheduledExecutorService` cũng là subtype của `ExecutorService`, nhưng task theo lịch đặt thêm câu hỏi: **task nào được phép tiếp tục sau shutdown?**

Với `ScheduledThreadPoolExecutor`, các chính sách như `setContinueExistingPeriodicTasksAfterShutdownPolicy(...)` và `setExecuteExistingDelayedTasksAfterShutdownPolicy(...)` ảnh hưởng task định kỳ/trì hoãn khi shutdown. Các giá trị mặc định được JDK quy định, nhưng khi cấu hình thay đổi, close có thể phải đợi các task còn được phép chạy theo chính sách.

**Không mặc định** rằng rời try-with-resources quanh một scheduler sẽ luôn hoàn tất tức thời. Nếu task delay còn rất lâu hoặc chính sách giữ task định kỳ sau shutdown, chương trình có thể chờ lâu/không kết thúc khi gọi close.

Khi xây dựng scheduler lâu dài, hãy quản lý vòng đời tại owner, hủy `ScheduledFuture` liên quan đúng lúc và xác định deadline shutdown rõ. Đừng đóng một scheduler dùng chung chỉ vì một phương thức đã đăng ký xong một task.

## 12. Exception trong try-with-resources và thứ tự đóng

Try-with-resources tự gọi `close()` khi rời khối **dù kết thúc bình thường, `return` hay exception**. Java đóng nhiều resource theo **thứ tự ngược với thứ tự khai báo**.

Ví dụ cấu trúc:

```java
// Snippet: openResource() trả một AutoCloseable khác.
try (AutoCloseable resource = openResource();
     ExecutorService executor = Executors.newFixedThreadPool(2)) {
    // Gửi task làm việc với resource.
}
// executor.close() chạy trước, sau đó resource.close().
```

Đây là **snippet**, vì `openResource()` chưa được định nghĩa. Việc để executor **được khai báo sau** resource trong trường hợp này làm nó được **close trước** resource, giúp các task còn chạy không truy cập một resource đã bị đóng sớm.

**Nếu đảo thứ tự resource**, resource có thể bị đóng trước khi executor hoàn tất task, gây lỗi sử dụng resource đã đóng. Vì vậy cấu trúc scope không chỉ là cú pháp rút gọn—**thứ tự đóng quyết định correctness** khi task phụ thuộc vào file, stream, connection hoặc resource khác.

Một exception do code trong `try` ném có thể chỉ được chuyển ra ngoài sau khi mọi resource đóng xong; exception từ quá trình đóng có quy tắc suppressed exceptions của Java. `ExecutorService.close()` không ném `InterruptedException` nhưng có thể gặp runtime exception như vấn đề quyền/ngữ cảnh triển khai. Khi quản lý nhiều resource, cần hiểu cả đường lỗi và việc đóng từng thành phần.

### Dùng resource variable đã tạo từ trước

Từ Java 9, try-with-resources có thể dùng một biến resource **final hoặc effectively final** đã được tạo trước đó:

```java
ExecutorService executor = Executors.newSingleThreadExecutor();
try (executor) {
    executor.execute(() -> System.out.println("work"));
}
```

Đoạn này là snippet trong phương thức/class phù hợp và dùng được với **JDK 21+** vì `ExecutorService` lúc đó là `AutoCloseable`. Nếu resource không thuộc quyền sở hữu của phương thức hiện tại (pool dùng chung), **không** đóng nó bằng try-with-resources chỉ vì cú pháp cho phép.

## 13. Điều kiện chờ kết thúc và memory visibility

`close()` chờ kết thúc vòng đời executor, nhưng nếu cần sử dụng kết quả của một task theo hợp đồng chương trình, **`Future.get()` là kênh công bố kết quả rõ ràng**. Hợp đồng của `ExecutorService` mô tả quan hệ memory-consistency quan trọng:

- Các hành động của thread trước khi submit task **happens-before** các hành động tương ứng bên trong task.
- Các hành động trong task **happens-before** những hành động sau khi kết quả được nhận qua `Future.get()`.

Khi task cập nhật shared mutable state, không thể mặc định rằng “dùng ExecutorService rồi close” sẽ làm mọi thao tác cập nhật **nguyên tử** hoặc tự bảo vệ bất biến trong lúc các task đang chạy. Hai task cùng `counter++` trên trường thường vẫn có thể mất cập nhật.

**Thiết kế đúng:** dùng `Future` cho giá trị/exception; dùng `AtomicInteger`, `synchronized`, `Lock` hoặc immutable snapshots khi task cùng truy cập state; dùng `close/awaitTermination` để quản lý **vòng đời**. Đây là ba trách nhiệm có liên quan nhưng không thay thế lẫn nhau.

### isShutdown khác isTerminated

- Sau `shutdown()`, `isShutdown() == true` nhưng `isTerminated()` có thể vẫn false.
- Sau `close()` **trả về bình thường** với default implementation và executor thực sự terminated, `isTerminated() == true`.
- Không cần đo bằng vòng `while (!executor.isTerminated())` busy-spin để chờ pool hoàn tất; dùng `awaitTermination(...)` hoặc close theo hợp đồng thích hợp.

## 14. Những hiểu nhầm thường gặp

1. **“`close()` được thêm vào ExecutorService đúng từ Java 21.”** Chính xác hơn: có **từ Java 19**; thường được học/dùng trong dự án JDK 21+.
2. **“JDK 17 cũng biên dịch try (ExecutorService e = ...).”** Sai: `ExecutorService` JDK17 chưa là `AutoCloseable`.
3. **“`close()` chỉ gọi shutdown và trả về ngay.”** Sai: nó chờ executor terminated.
4. **“`shutdown()` đã đợi mọi task kết thúc.”** Sai: nó chỉ yêu cầu orderly shutdown.
5. **“`shutdownNow()` chắc chắn giết mọi task.”** Sai: chỉ best-effort; task không phản hồi interrupt có thể vẫn chạy.
6. **“`close()` có một timeout mặc định.”** Sai: không có deadline chờ cố định theo API.
7. **“Khi caller bị interrupt, `close()` lập tức ném `InterruptedException`.”** Sai: close cố stop kiểu shutdownNow, tiếp tục chờ và khôi phục cờ trước khi trả về.
8. **“`close()` khẳng định mọi task thành công.”** Sai: cần `Future.get()` để biết outcome.
9. **“Rời scope nghĩa là side effect trong task đều rollback khi có lỗi.”** Sai: executor không phải transaction manager.
10. **“Một pool dùng chung có thể đóng ở bất kỳ nơi nào gọi nó.”** Sai: phải có chủ sở hữu lifecycle rõ.
11. **“Virtual threads khiến close không thể treo.”** Sai: virtual thread có thể chờ vô hạn nếu không có điều kiện tiến triển.
12. **“Task chỉ cần signal ở dòng sau try thì close sẽ cho dòng sau chạy.”** Sai: close chờ task; có thể tạo chu trình chờ.
13. **“Scheduled executor sẽ luôn đóng ngay khi hết khối try.”** Sai: delay/periodic policy có thể khiến chờ đáng kể.
14. **“Một Future hoàn tất nói mọi task trong executor đã dừng.”** Sai: Future chỉ đại diện task tương ứng, còn close/awaitTermination nói về executor.
15. **“close là cách thay thế cho thiết kế graceful shutdown theo SLA.”** Sai: có thể cần shutdown và timed awaitTermination với fallback.

## 15. Checklist áp dụng ExecutorService.close và try-with-resources

1. **JDK đang chạy là phiên bản nào?** Nếu muốn `try (ExecutorService...)` phải có API `AutoCloseable` của ExecutorService, thực tế dùng JDK 21+ theo bài.
2. **Ai sở hữu executor?** Chỉ scope sở hữu được tự đóng; pool dùng chung cần owner có vòng đời dài hơn.
3. **Task có hữu hạn và có thể tiến triển không?** Tránh tác vụ tự chờ tín hiệu chỉ xảy ra sau khi close.
4. **Có cần lấy giá trị và exception không?** Dùng `Future.get()`/kênh kết quả, không trông chờ close báo lỗi task.
5. **Deadline shutdown có giới hạn không?** Nếu cần, dùng `shutdown(); awaitTermination(timeout)` rồi chọn hành động tiếp theo; close không có timeout.
6. **Task có hợp tác với interrupt không?** Cấu trúc shutdownNow khi bị interrupt không phải cơ chế kill mạnh.
7. **Có đang giữ tài nguyên worker cần không?** Không đóng executor khi giữ một lock hay resource tạo vòng chờ.
8. **Nếu có nhiều AutoCloseable, thứ tự đóng có đúng không?** Resource worker sử dụng thường cần tồn tại tới khi executor đã dừng.
9. **Có scheduled/periodic/delayed task không?** Xem chính sách sau shutdown và hủy future khi cần.
10. **Có shared mutable state không?** Đóng executor không chữa data race; đồng bộ các task riêng.
11. **Đã thử đường normal/exception/interrupt chưa?** Dùng latch để tạo lịch tái hiện, kiểm tra trạng thái cờ và cleanup.
12. **Có quan sát lifecycle khi vận hành không?** Theo dõi `isShutdown`, `isTerminated`, thời gian shutdown, task bị kẹt và thread dump/JFR nếu cần.

## 16. Tài liệu chuẩn để đối chiếu

- [JDK 21: ExecutorService API và close()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [JDK 21: Executors API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html)
- [JDK 21: ThreadPoolExecutor API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)

**Tóm lại:** từ Java 19, `ExecutorService` có `close()` và trở thành `AutoCloseable`; trong các chương trình **Java 21+**, có thể dùng `try-with-resources` để gắn vòng đời executor với một scope. **Close chờ các task đã nhận và executor kết thúc**, không đơn thuần gọi shutdown rồi trả về. Nếu caller bị interrupt khi chờ, close chuyển sang yêu cầu dừng kiểu shutdownNow, **vẫn chờ task đang chạy kết thúc**, rồi khôi phục interrupt status. Hãy chọn close khi cần chờ đến cùng; chọn shutdown/awaitTermination có deadline khi hệ thống có giới hạn thời gian, và quản lý kết quả/lỗi qua Future.