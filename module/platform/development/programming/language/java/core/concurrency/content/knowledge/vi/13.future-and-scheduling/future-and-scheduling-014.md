# Future.State, resultNow() và exceptionNow() trong Java 21+

## 1. Vấn đề: cần đọc trạng thái và kết quả Future mà không chờ

`Future<V>` mô tả kết quả của một phép tính bất đồng bộ. Trước đây, khi cầm một `Future`, ta thường kết hợp `isDone()`, `isCancelled()` và `get()` để phân biệt kết quả thành công, thất bại hoặc bị hủy. Tuy nhiên, `isDone()` chỉ nói tác vụ đã hoàn tất theo nghĩa rộng; nó **không phân biệt hoàn tất thành công với thất bại hay hủy**. `get()` có thể **block** cho đến khi tác vụ hoàn tất và ném các ngoại lệ tương ứng.

Các phương thức mới trên `java.util.concurrent.Future`:

- `Future.State state()`: trả về **trạng thái quan sát được** của phép tính.
- `V resultNow()`: lấy kết quả đã hoàn tất **thành công**, không chờ.
- `Throwable exceptionNow()`: lấy ngoại lệ từ phép tính đã hoàn tất **thất bại**, không chờ.

Trong Java 21, enum `Future.State` có bốn trạng thái: **`RUNNING`, `SUCCESS`, `FAILED`, `CANCELLED`**.

> **Lưu ý về phiên bản:** Bài học dùng **JDK 21 trở lên** theo chủ đề, nhưng ba API `state()`, `resultNow()` và `exceptionNow()` thực tế được giới thiệu từ **Java 19** (trong Javadoc có “Since: 19”). Vì vậy không nên ghi rằng chúng “được thêm lần đầu ở Java 21”. Chúng không có trong interface `Future` của Java 17. Mọi ví dụ biên dịch trực tiếp dưới đây dùng `javac` và `java` của **JDK 21+**, không phải Java 17.

### Mục tiêu

Sau bài học, bạn có thể:

1. Hiểu ngữ nghĩa bốn giá trị `Future.State`, đặc biệt vì sao `RUNNING` **không nhất thiết là đang chạy CPU**.
2. Chỉ gọi `resultNow()` sau khi `state() == SUCCESS` và `exceptionNow()` sau khi `state() == FAILED`.
3. Phân biệt lỗi `IllegalStateException` của truy cập sai trạng thái với `ExecutionException`, `CancellationException`, `InterruptedException` từ `get()`.
4. Biết lúc nào cần **chờ** với `get()`, lúc nào chỉ cần **kiểm tra ngay** với ba API mới.
5. Áp dụng cho `FutureTask`, `CompletableFuture`, task `ExecutorService.submit` và `ScheduledFuture`.
6. Không nhầm `CANCELLED` với bảo đảm worker đã dừng và dọn dẹp xong.
7. Thiết kế theo nguyên tắc safe publication, concurrency cancellation và observability của Java nói chung, không phụ thuộc framework.

## 2. Future truyền thống và vấn đề đặt câu hỏi sai

Một ví dụ Java 17 quen thuộc:

~~~java
// Mẫu Java 17+, không phải chương trình độc lập.
Future<Integer> future = executor.submit(() -> calculate());

if (future.isDone()) {
    try {
        Integer value = future.get();
        use(value);
    } catch (ExecutionException failed) {
        report(failed.getCause());
    } catch (CancellationException cancelled) {
        recordCancellation();
    }
}
~~~

Dù kiểm tra `isDone()` trước, `get()` vẫn buộc caller xử lý nhiều đường kết quả. Nếu `future` chưa xong, `get()` không timeout có thể chờ vô thời hạn; nếu task bị hủy, `isDone()` vẫn trả true; nếu task ném exception, `isDone()` cũng trả true.

Với Java 21+, ta có thể **hỏi trực tiếp outcome** và lấy kết quả tương ứng:

~~~java
// Mẫu Java 21+, không phải chương trình độc lập.
switch (future.state()) {
    case RUNNING -> notePending();
    case SUCCESS -> use(future.resultNow());
    case FAILED -> report(future.exceptionNow());
    case CANCELLED -> recordCancellation();
}
~~~

Mẫu này tách bạch bốn nhánh. Nhưng nó không thay `get()` ở nơi **phải chờ** kết quả; `resultNow()` không được thiết kế để chờ một task đang chạy hoàn tất.

### Vì sao “kiểm tra không chờ” hữu ích?

- Hiển thị dashboard tiến độ: bao nhiêu Future chưa hoàn tất, thành công, lỗi, bị hủy.
- Thu thập kết quả của các task **đã hoàn tất** mà không block thread tổng hợp.
- Gộp lỗi từ các Future đã kết thúc, phân loại nguyên nhân để ghi log hoặc báo cáo.
- Phân loại `ScheduledFuture` đang chờ thời điểm kích hoạt hoặc đã bị hủy.
- Tương tác với `CompletableFuture`/`FutureTask` thông qua hợp đồng `Future` mà không cần suy diễn từ một chuỗi lệnh try/catch `get()`.

**Không nên** polling `state()` liên tục trong một vòng bận chỉ để đợi kết quả; khi mục tiêu là đợi, hãy chọn `get()`/`get(timeout, unit)`, completion callback hoặc cơ chế phối hợp phù hợp.

## 3. Future.State: bốn trạng thái cần nhớ

### 3.1. Enum và ý nghĩa

Trong Java 21:

~~~java
// Tên các hằng enum, không phải chương trình độc lập.
Future.State.RUNNING
Future.State.SUCCESS
Future.State.FAILED
Future.State.CANCELLED
~~~

| State | Ý nghĩa hợp đồng | Kết quả và cách lấy |
| --- | --- | --- |
| `RUNNING` | Phép tính **chưa hoàn tất** | Chưa thể gọi `resultNow()` hoặc `exceptionNow()` để lấy outcome |
| `SUCCESS` | Phép tính hoàn tất **thành công** | `resultNow()` lấy giá trị, kể cả khi giá trị hợp lệ là `null` |
| `FAILED` | Phép tính hoàn tất bằng **exception** | `exceptionNow()` lấy Throwable gốc |
| `CANCELLED` | Phép tính đã được **hủy theo trạng thái Future** | Không có kết quả/ngoại lệ của một lần hoàn thành FAILED để lấy qua hai method Now |

Enum này không có `NEW`, `QUEUED`, `WAITING` hoặc `TERMINATED`. Vì vậy **`RUNNING` chỉ có nghĩa “not completed”**. Một task **chưa được worker nhận**, đang nằm trong queue, đang chờ delay scheduled, hoặc đang thực sự chạy đều có thể xuất hiện là `RUNNING`. Không dùng nó để kết luận thread đã bắt đầu thực thi task.

### 3.2. Chuyển trạng thái về mặt outcome

~~~text
                       +----------------+
                       |    RUNNING     |
                       | (chưa hoàn tất) |
                       +-------+--------+
                               |
             +-----------------+-----------------+
             |                 |                 |
         hoàn thành        ném exception      hủy được chấp nhận
             |                 |                 |
       +-----v-----+     +-----v-----+     +-----v-------+
       |  SUCCESS  |     |  FAILED   |     | CANCELLED   |
       +-----------+     +-----------+     +-------------+
~~~

Đối với một Future thông thường, trạng thái outcome cuối cùng không chuyển trở lại `RUNNING`. `CANCELLED` có thể được quan sát ngay sau khi việc hủy được chấp nhận, **trước khi tất cả mã bên trong worker hoàn tất cleanup**.

Không suy diễn rằng mọi implementation sẽ thông báo hoặc chạy callback theo thứ tự tuyệt đối tương ứng với cách bạn gọi `state()`. Đây là một **snapshot trạng thái**, không phải một sự kiện hàng đợi được lưu vĩnh viễn.

### 3.3. Thời điểm lấy mẫu và tính đồng thời

~~~java
// Mẫu quan sát, không phải chương trình độc lập.
Future.State seen = future.state();

if (seen == Future.State.RUNNING) {
    // Ngay sau đây, worker vẫn có thể đã hoàn tất.
}
~~~

Kết quả `RUNNING` có thể lập tức cũ khi method trở về. Không có khóa nào từ việc gọi `state()` bảo đảm Future vẫn chưa hoàn tất trong khoảng thời gian tiếp theo.

Ngược lại, nếu thấy `SUCCESS`/`FAILED`/`CANCELLED` ở một Future thực thi đúng contract, đó là outcome kết thúc; các phương thức `resultNow()`/`exceptionNow()` trên đúng nhánh phù hợp. Việc ghi nhận những state terminal là hữu ích để lập báo cáo kết quả, nhưng **lifecycle của side effect** bên ngoài vẫn có thể cần kênh xác nhận riêng khi bị hủy.

## 4. resultNow(): đọc kết quả thành công ngay lập tức

### 4.1. Hợp đồng

`V resultNow()` trả kết quả tính toán **không chờ** khi Future đã hoàn tất thành công.

~~~java
// Mẫu Java 21+, không phải chương trình độc lập.
if (future.state() == Future.State.SUCCESS) {
    V result = future.resultNow();
    consume(result);
}
~~~

Khi nào `resultNow()` ném `IllegalStateException`?

- Future chưa hoàn tất (`RUNNING`).
- Future hoàn tất bằng exception (`FAILED`).
- Future bị hủy (`CANCELLED`).

**Quan trọng:** `SUCCESS` không có nghĩa giá trị khác `null`. Ví dụ một `Callable<Void>` hay `Runnable` được `submit` có thể kết thúc thành công với result `null`. `resultNow() == null` không phải tín hiệu thất bại.

### 4.2. Vì sao không dùng resultNow() như get()?

`get()` có mục đích **đợi** task hoàn thành (nếu chưa xong) và truyền outcome hoặc lỗi qua `ExecutionException`, `CancellationException`, `InterruptedException`. `resultNow()` có mục đích **đọc kết quả đã có** và đưa lỗi sử dụng API vào `IllegalStateException` nếu state chưa đúng.

Nếu caller thực sự cần giá trị để tính bước tiếp theo, có thể dùng:

~~~java
// Mẫu đợi kết quả, dùng được từ Java 5; không độc lập.
try {
    Integer answer = future.get(2, TimeUnit.SECONDS);
    process(answer);
} catch (TimeoutException timedOut) {
    // Quyết định deadline/cancel theo nghiệp vụ.
}
~~~

Đoạn này còn cần xử lý hoặc truyền `InterruptedException` và `ExecutionException` theo hợp đồng method. `TimeoutException` nghĩa là chờ đã hết thời gian, **không tự động hủy Future**.

## 5. exceptionNow(): đọc nguyên nhân khi Future đã FAILED

`Throwable exceptionNow()` trả throwable đã làm phép tính kết thúc thất bại, khi state là `FAILED`:

~~~java
// Mẫu Java 21+, không phải chương trình độc lập.
if (future.state() == Future.State.FAILED) {
    Throwable failure = future.exceptionNow();
    report(failure);
}
~~~

Trong Javadoc Java 21, `exceptionNow()` ném `IllegalStateException` nếu task:

- Chưa hoàn tất (`RUNNING`).
- Đã hoàn tất bình thường (`SUCCESS`).
- Đã bị hủy (`CANCELLED`).

`FAILED` là trạng thái hoàn tất bởi exception, không phải “đã bị cancel”. Việc `cancel(true)` gửi interrupt tới worker rồi worker bắt `InterruptedException` **không** bắt buộc biến Future thành `FAILED`; nếu trạng thái Future đã hủy thành công, kết quả thường là `CANCELLED`.

### 5.1. So sánh với Future.get()

Khi task FAILED:

~~~java
// Mẫu Java, không độc lập.
try {
    future.get(); // Có thể chờ nếu chưa xong.
} catch (ExecutionException wrapper) {
    Throwable cause = wrapper.getCause();
    report(cause);
}
~~~

`get()` ném `ExecutionException` bao bọc nguyên nhân. `exceptionNow()` trả trực tiếp `Throwable` nguyên nhân **khi đã FAILED**; caller không cần bóc thêm `ExecutionException` trong nhánh đó.

Không cố gọi cả hai method Now “để xem cái nào không lỗi”. **Đọc `state()` trước rồi chọn đúng method** sẽ rõ nghĩa hơn và tránh dùng exception như luồng điều khiển bình thường.

## 6. Ví dụ 1 — quan sát đủ bốn trạng thái (Java 21+)

Ta tạo bốn `CompletableFuture` có trạng thái được thiết lập có chủ đích. Không cần thread phụ hoặc `sleep`; do đó đầu ra ổn định.

Tạo tệp `FutureStatesDemo.java`:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Future;

public class FutureStatesDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> pending =
            new CompletableFuture<>();

        CompletableFuture<Integer> success =
            CompletableFuture.completedFuture(42);

        CompletableFuture<Integer> failed =
            CompletableFuture.failedFuture(
                new IllegalArgumentException("bad input")
            );

        CompletableFuture<Integer> cancelled =
            new CompletableFuture<>();
        cancelled.cancel(false);

        System.out.println("pending = " + pending.state());
        System.out.println("success = " + success.state());
        System.out.println("failed = " + failed.state());
        System.out.println("cancelled = " + cancelled.state());

        System.out.println("result = " + success.resultNow());
        System.out.println("failure type = "
            + failed.exceptionNow().getClass().getSimpleName());
        System.out.println("success state constant = "
            + Future.State.SUCCESS);
    }
}
~~~

Biên dịch/chạy bằng **JDK 21+**:

~~~bash
javac FutureStatesDemo.java
java FutureStatesDemo
~~~

Stdout:

~~~text
pending = RUNNING
success = SUCCESS
failed = FAILED
cancelled = CANCELLED
result = 42
failure type = IllegalArgumentException
success state constant = SUCCESS
~~~

**Phân tích chính xác:**

1. `pending` chưa có ai gọi `complete(...)`, nên `state()` là `RUNNING`, dù **không có thread nào thực sự đang chạy nó**.
2. `completedFuture(42)` đã có result từ đầu, nên `SUCCESS` và `resultNow() == 42`.
3. `failedFuture(...)` đã hoàn tất ngoại lệ, nên `FAILED` và `exceptionNow()` trả Throwable gốc.
4. `cancel(false)` trên `CompletableFuture` chưa hoàn tất đặt trạng thái `CANCELLED`. Không có worker nào để ngắt ở ví dụ này.
5. `Future.State` là enum nằm trong interface `Future`, không phải enum của riêng `CompletableFuture`.

Đây là một cách học rất rõ nghĩa vì nó không trộn các trường hợp outcome với tính ngẫu nhiên của scheduler.

## 7. Ví dụ 2 — guard các method Now và IllegalStateException (Java 21+)

Tạo tệp `FutureNowGuardsDemo.java`:

~~~java
import java.util.concurrent.CompletableFuture;

public class FutureNowGuardsDemo {
    public static void main(String[] args) {
        CompletableFuture<String> pending =
            new CompletableFuture<>();
        CompletableFuture<String> ok =
            CompletableFuture.completedFuture(null);
        CompletableFuture<String> bad =
            CompletableFuture.failedFuture(
                new IllegalStateException("business failure")
            );

        try {
            pending.resultNow();
        } catch (IllegalStateException expected) {
            System.out.println("pending resultNow rejected");
        }

        try {
            ok.exceptionNow();
        } catch (IllegalStateException expected) {
            System.out.println("success exceptionNow rejected");
        }

        try {
            bad.resultNow();
        } catch (IllegalStateException expected) {
            System.out.println("failed resultNow rejected");
        }

        System.out.println("null result success = "
            + (ok.state() == java.util.concurrent.Future.State.SUCCESS
                && ok.resultNow() == null));

        System.out.println("failed exception = "
            + bad.exceptionNow().getMessage());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac FutureNowGuardsDemo.java
java FutureNowGuardsDemo
~~~

Stdout:

~~~text
pending resultNow rejected
success exceptionNow rejected
failed resultNow rejected
null result success = true
failed exception = business failure
~~~

**Lưu ý:** Cả exception đại diện thất bại nghiệp vụ và exception do **gọi sai API** đều có thể thuộc kiểu `IllegalStateException`. Trong ví dụ, `bad.exceptionNow()` trả về đối tượng `IllegalStateException("business failure")` từ task; còn lời gọi `bad.resultNow()` tự ném một `IllegalStateException` vì state không phải SUCCESS. Đừng nhập hai lỗi này làm một khi ghi log.

Khi xây dựng API hỗ trợ người dùng, thông thường nên **chuyển trạng thái thành nhánh rõ ràng**, thay vì dùng các exception `resultNow()`/`exceptionNow()` để thăm dò trạng thái.

## 8. Ví dụ 3 — task ExecutorService ở trạng thái RUNNING rồi SUCCESS

Để minh họa `RUNNING` khi task đã được đưa vào executor nhưng chưa hoàn tất, ta điều khiển điểm chờ bằng `CountDownLatch`. Không dùng `Thread.sleep` để phỏng đoán worker đã chạy.

Tạo tệp `ExecutorFutureStateDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ExecutorFutureStateDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<Integer> future = pool.submit(() -> {
                started.countDown();
                release.await();
                return 21;
            });

            started.await();
            System.out.println("before = " + future.state());

            release.countDown();
            System.out.println("get = " + future.get());
            System.out.println("after = " + future.state());
            System.out.println("resultNow = " + future.resultNow());
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch/chạy bằng JDK 21+:

~~~bash
javac ExecutorFutureStateDemo.java
java ExecutorFutureStateDemo
~~~

Stdout khi task không bị interrupt:

~~~text
before = RUNNING
get = 21
after = SUCCESS
resultNow = 21
~~~

**Vì sao xác định được?**

- Worker đếm `started` trước khi chờ `release`; main đợi `started` rồi mới gọi `future.state()`.
- Main **chưa** đếm `release` ở thời điểm in `before`; callable không thể trả về 21 trước khi latch mở. Vì vậy state là RUNNING.
- Main giải phóng worker bằng `release.countDown()`, sau đó `future.get()` đợi cho đến khi tính toán hoàn tất.
- Sau `get()` thành công, `state()` là SUCCESS và `resultNow()` trả 21 ngay.
- `finally` luôn mở latch để tránh làm worker kẹt nếu caller ném exception trước khi release, và quản lý pool lifecycle.

**Giới hạn:** Nếu đã thấy RUNNING, code không nên kết luận “worker hiện đang chiếm một CPU”. Ở ví dụ này worker đang **chờ latch**. Không có enum `QUEUED`/`BLOCKED`/`WAITING` trong `Future.State`.

## 9. Ví dụ 4 — exceptionNow với Future từ executor (Java 21+)

Tạo tệp `ExecutorFailureNowDemo.java`:

~~~java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ExecutorFailureNowDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            Future<Integer> future = pool.submit(() -> {
                throw new IllegalArgumentException("invalid number");
            });

            try {
                future.get();
            } catch (ExecutionException ex) {
                System.out.println("get cause = "
                    + ex.getCause().getClass().getSimpleName());
            }

            System.out.println("state = " + future.state());
            System.out.println("exceptionNow = "
                + future.exceptionNow().getMessage());

            try {
                future.resultNow();
            } catch (IllegalStateException expected) {
                System.out.println("resultNow rejected");
            }
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac ExecutorFailureNowDemo.java
java ExecutorFailureNowDemo
~~~

Stdout:

~~~text
get cause = IllegalArgumentException
state = FAILED
exceptionNow = invalid number
resultNow rejected
~~~

`submit(...)` trả Future giữ kết quả của task. `future.get()` khi task FAILED ném `ExecutionException`; nguyên nhân `IllegalArgumentException` được bao trong `getCause()`. Sau đó `future.state()` trả FAILED, còn `exceptionNow()` trả trực tiếp nguyên nhân để xử lý/log.

**Đừng đánh đồng exceptionNow với lời gọi làm task thất bại.** Task đã ném exception trong executor; `exceptionNow()` chỉ **quan sát** một outcome đã được lưu. Gọi `exceptionNow()` không retry, cancel hay khởi chạy lại task.

## 10. CANCELLED: hủy Future không phải dừng mọi side effect ngay

### 10.1. Cancel có thể đến trước hoặc trong thực thi

`Future.cancel(boolean mayInterruptIfRunning)` yêu cầu hủy. Nếu task chưa bắt đầu, việc hủy được chấp nhận có thể khiến task không chạy. Nếu task đã bắt đầu, `mayInterruptIfRunning == true` cho phép implementation thử interrupt thread chạy task khi biết được thread đó.

Nhưng interrupt vẫn là **cơ chế hợp tác**: worker có thể đang ở đoạn tính toán không kiểm tra cờ, giữ tài nguyên, hoặc chạy cleanup. Vì vậy:

- `future.state() == CANCELLED` không bảo đảm worker đã thoát.
- `future.isDone() == true` có thể là trạng thái cancel chứ không phải nghiệp vụ hoàn thành.
- `future.get()` trên Future hủy ném `CancellationException`, không trả kết quả nghiệp vụ.
- `resultNow()` và `exceptionNow()` không trả outcome của task thành công/thất bại trên Future CANCELLED; hai method này ném `IllegalStateException` theo contract.
- Nếu cần biết worker đã đóng file, release resource hoặc ghi lại trạng thái cuối, dùng latch/kênh xác nhận **riêng**.

### 10.2. Ví dụ 5 — CANCELLED và tín hiệu tới worker (Java 21+)

Tạo tệp `FutureCancellationStateDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.FutureTask;
import java.util.concurrent.CancellationException;
import java.util.concurrent.atomic.AtomicBoolean;

public class FutureCancellationStateDemo {
    public static void main(String[] args)
            throws InterruptedException {
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        AtomicBoolean interrupted = new AtomicBoolean();

        FutureTask<Integer> task = new FutureTask<>(() -> {
            entered.countDown();
            try {
                for (;;) {
                    Thread.sleep(1_000);
                }
            } catch (InterruptedException ex) {
                interrupted.set(true);
                Thread.currentThread().interrupt();
                return 0;
            } finally {
                finished.countDown();
            }
        });

        Thread worker = new Thread(task, "cancellable-worker");
        worker.start();
        entered.await();

        boolean accepted = task.cancel(true);
        finished.await();
        worker.join();

        System.out.println("cancel accepted = " + accepted);
        System.out.println("state = " + task.state());
        System.out.println("worker observed interrupt = "
            + interrupted.get());
        System.out.println("worker finished = " + !worker.isAlive());

        try {
            task.get();
        } catch (CancellationException ex) {
            System.out.println("get throws CancellationException");
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac FutureCancellationStateDemo.java
java FutureCancellationStateDemo
~~~

Stdout khi worker không có interrupt/lỗi ngoài thiết kế:

~~~text
cancel accepted = true
state = CANCELLED
worker observed interrupt = true
worker finished = true
get throws CancellationException
~~~

**Tại sao vẫn CANCELLED nếu task trong catch trả `0`?** `cancel(true)` đã chấp nhận cancel Future trước khi worker kết thúc. Kết quả trả về sau đó **không thay đổi** trạng thái outcome của Future đã bị cancel thành SUCCESS. `get()` trên Future này ném `CancellationException`.

`entered` bảo đảm worker đã vào callable trước khi main hủy. Nếu cancel đến ngay trước khi worker gọi `sleep`, cờ interrupt vẫn khiến sleep phản hồi bằng exception; nếu đến trong khi sleep, lời chờ bị ngắt. `finished` và `worker.join()` xác nhận đường code cuối và thread thật sự đã kết thúc **trước khi** chương trình in kết quả.

Ví dụ này có kênh `finished` vì `CANCELLED` không tự nói tài nguyên đã cleanup. Trong ứng dụng thực, đặt cleanup vào `finally` hoặc try-with-resources, xử lý lỗi cleanup và có xác nhận khi nghiệp vụ thật sự cần.

## 11. ScheduledFuture cũng là Future

`ScheduledExecutorService` có thể trả về `ScheduledFuture<V>`. Interface này vừa mang thông tin delay (`Delayed`) vừa kế thừa `Future<V>`, vì thế dùng được `state()`, `resultNow()` và `exceptionNow()` ở Java 21+.

### 11.1. One-shot scheduled task

~~~java
// Mẫu Java 21+, không phải chương trình độc lập.
ScheduledFuture<String> future =
    scheduler.schedule(() -> "done", 2, TimeUnit.SECONDS);

if (future.state() == Future.State.RUNNING) {
    // Có thể đang đợi lịch hoặc đang thực thi; chưa kết thúc.
}
~~~

**RUNNING không có nghĩa scheduled task đã tới thời điểm chạy.** Một scheduled task đang chờ delay vẫn chưa hoàn tất nên thuộc RUNNING. Để hỏi thời lượng delay còn lại dùng `getDelay(TimeUnit.MILLISECONDS)`, nhưng giá trị này cũng chỉ là quan sát tức thời.

### 11.2. Ví dụ 6 — scheduled task thành công và scheduled task bị hủy (Java 21+)

Tạo tệp `ScheduledFutureStateDemo.java`:

~~~java
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

public class ScheduledFutureStateDemo {
    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler =
            Executors.newSingleThreadScheduledExecutor();

        try {
            ScheduledFuture<String> immediate =
                scheduler.schedule(
                    () -> "ready", 0, TimeUnit.MILLISECONDS
                );

            ScheduledFuture<String> later =
                scheduler.schedule(
                    () -> "too late", 1, TimeUnit.DAYS
                );

            System.out.println("scheduled result = " + immediate.get());
            System.out.println("scheduled state = " + immediate.state());
            System.out.println("resultNow = " + immediate.resultNow());

            System.out.println("later before = " + later.state());
            later.cancel(false);
            System.out.println("later after = " + later.state());
            System.out.println("cancelled = "
                + (later.state() == Future.State.CANCELLED));
        } finally {
            scheduler.shutdownNow();
            if (!scheduler.awaitTermination(5, TimeUnit.SECONDS)) {
                System.out.println("scheduler still shutting down");
            }
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac ScheduledFutureStateDemo.java
java ScheduledFutureStateDemo
~~~

Stdout thông thường với lịch hệ thống ổn định và scheduler dừng trong 5 giây:

~~~text
scheduled result = ready
scheduled state = SUCCESS
resultNow = ready
later before = RUNNING
later after = CANCELLED
cancelled = true
~~~

Lần schedule đầu có delay 0 và callable trả `"ready"`; `get()` chờ hoàn tất rồi `resultNow()` đọc kết quả đã có. Task `later` có delay một ngày nên chưa hoàn tất khi kiểm tra ngay trong ví dụ thông thường: `RUNNING` chỉ mang nghĩa “not completed”. `cancel(false)` hủy task chưa bắt đầu, đổi trạng thái Future thành CANCELLED. Không có kết quả `"too late"` được công bố.

**Lưu ý về tính xác định:** Dòng `later before = RUNNING` dựa trên lịch chạy thông thường, một độ trễ 1 ngày và việc không có thao tác bên ngoài nào sửa đồng hồ/lịch lập lịch cực đoan; đây không phải chứng minh tổng quát rằng delay luôn tồn tại đúng như thời gian đồng hồ tường. Nếu cần bài test trạng thái hoàn toàn xác định, dùng một `CompletableFuture` chưa hoàn tất như ví dụ 1 hoặc một latch chặn callable như ví dụ 3.

### 11.3. Periodic ScheduledFuture

`scheduleAtFixedRate(...)` và `scheduleWithFixedDelay(...)` trả `ScheduledFuture<?>` cho chuỗi thực thi lặp lại:

- Trong lúc tác vụ lặp còn được lịch hóa, Future thường vẫn ở `RUNNING`: các lần chạy riêng hoàn tất **không** đồng nghĩa toàn chuỗi đã SUCCESS.
- Với task lặp vô hạn bình thường, lời gọi `get()` có thể chờ mãi nếu không bị hủy/thất bại hoặc không có chính sách kết thúc khác.
- Nếu một lần chạy ném exception không xử lý, các lần chạy tiếp theo theo hợp đồng scheduled executor bị **suppressed**, Future có thể hoàn tất `FAILED`.
- Khi hủy được chấp nhận, Future chuyển `CANCELLED`; task đang chạy có thể vẫn cần hợp tác dừng/cleanup.

Không diễn giải `Future.State.SUCCESS` sau mỗi tick định kỳ. Nếu cần thống kê thành công/thất bại **mỗi lần chạy**, task cần ghi metric/kết quả ở từng tick bằng cơ chế riêng.

## 12. state(), resultNow() và exceptionNow() có thực sự không block?

Theo hợp đồng API, đây là các phép **quan sát kết quả mà không chờ task hoàn tất**. Với `Future` interface, chúng được cung cấp dưới dạng default method:

- `resultNow()` bản mặc định kiểm tra `isDone()` rồi gọi `get()` khi Future đã hoàn tất.
- `exceptionNow()` bản mặc định kiểm tra `isDone()`/`isCancelled()` và dùng `get()` để lấy exception nếu đã kết thúc.
- `state()` bản mặc định dùng `isDone()`, `isCancelled()` và `get()` để phân loại outcome.

Do đó **implementation đúng hợp đồng phải bảo đảm tính nhất quán của trạng thái hoàn tất với get**. `FutureTask` và `CompletableFuture` có thể có triển khai/đường tối ưu riêng tùy JDK. Không tự tạo `Future` custom có `isDone() == true` nhưng `get()` còn block kéo dài hoặc vĩnh viễn; đó là một contract không nhất quán và có thể làm các phương thức quan sát hoạt động sai kỳ vọng.

Với một Future đã terminal, đọc outcome không đợi tác vụ chạy tiếp. Tuy nhiên, **độ dài thực thi CPU của một lời gọi method** không phải lời hứa deadline realtime tuyệt đối: thời gian còn phụ thuộc scheduler, khóa nội bộ, JIT và việc xử lý giá trị.

### 12.1. Các default method có ý nghĩa tương thích

Vì ba phương thức đã được thêm làm **default methods trên `Future`**, class implement Future cũ vẫn có thể thừa hưởng hành vi mặc định khi chạy trong JDK mới, miễn tuân thủ contract của `isDone`, `isCancelled` và `get`. Nhưng source code gọi `resultNow()` vẫn phải **biên dịch bằng API Java 19+**, ví dụ `javac` JDK 21; với `--release 17`, ba method đó không tồn tại trong API mục tiêu.

Không dùng reflection để “tự bịa” tên method khi target của ứng dụng là Java 17. Nếu cần hỗ trợ Java 17, giữ `isDone/isCancelled/get`, wrapper tương thích hoặc thiết kế API riêng.

## 13. So sánh get(), get(timeout), join() và các phương thức Now

| API | Có thể chờ kết quả? | Thành công | Thất bại | Hủy |
| --- | --- | --- | --- | --- |
| `Future.get()` | **Có** | Trả `V` | `ExecutionException` | `CancellationException` |
| `Future.get(timeout, unit)` | **Có giới hạn** | Trả `V` | `ExecutionException` hoặc timeout | `CancellationException` |
| `Future.state()` | **Không chờ task hoàn tất** | `SUCCESS` | `FAILED` | `CANCELLED` |
| `Future.resultNow()` | **Không** | Trả `V` | `IllegalStateException` | `IllegalStateException` |
| `Future.exceptionNow()` | **Không** | `IllegalStateException` | Trả `Throwable` | `IllegalStateException` |
| `CompletableFuture.join()` | **Có** nếu chưa xong | Trả `V` | `CompletionException` (thường) | `CancellationException` |
| `CompletableFuture.getNow(default)` | **Không** | Trả giá trị (nếu đã xong) | `CompletionException` (thường) | `CancellationException` |

**Chi tiết cần nhớ:**

- `Future.get()` còn có thể ném `InterruptedException` khi **thread đang chờ** bị ngắt.
- `Future.get(timeout, unit)` thêm `TimeoutException`; timeout **không tự cancel**.
- `CompletableFuture.getNow(default)` dùng giá trị fallback khi **chưa hoàn tất**, còn `Future.resultNow()` **ném `IllegalStateException`** khi chưa hoàn tất.
- `Future.resultNow()` thuộc interface Future nên áp dụng cả cho Future do executor/scheduler trả, không riêng CompletableFuture.
- `CompletableFuture.join()` thuộc class CompletableFuture, không phải method của mọi Future.

### 13.1. Vì sao không dùng isDone() && !isCancelled() để kết luận SUCCESS?

~~~java
// SAI: không đủ phân biệt SUCCESS và FAILED.
if (future.isDone() && !future.isCancelled()) {
    Integer value = future.resultNow(); // Có thể IllegalStateException.
}
~~~

Điều kiện này cũng đúng khi Future đã FAILED. Nếu muốn gọi `resultNow()`, dùng `future.state() == Future.State.SUCCESS`; nếu FAILED thì gọi `exceptionNow()`.

### 13.2. Nếu kết quả null thì sao?

`null` có thể là kết quả của một task thành công, chẳng hạn `submit(Runnable)` không gán result cụ thể hoặc một `Callable<String>` trả null. Dùng `state()` thay vì so sánh `resultNow() == null` để quyết định tác vụ lỗi hay thành công.

## 14. Tổng hợp danh sách Future không chờ

Một ứng dụng có tập Future tương ứng nhiều task. Nếu cần **lấy kết quả hiện có mà không block**, có thể lọc state trước.

### Mẫu tổng hợp

~~~java
// Java 21+, đoạn minh họa trong method có List<Future<Integer>>.
List<Integer> successes = futures.stream()
    .filter(f -> f.state() == Future.State.SUCCESS)
    .map(Future::resultNow)
    .toList();

List<Throwable> failures = futures.stream()
    .filter(f -> f.state() == Future.State.FAILED)
    .map(Future::exceptionNow)
    .toList();
~~~

Ở đây `List` và `Future` cần được import. Mẫu không block để chờ các task chưa xong; những Future `RUNNING`/`CANCELLED` bị bỏ qua. Khi một Future đổi từ RUNNING sang SUCCESS ngay sau lúc được kiểm tra, kết quả của nó có thể **không xuất hiện trong lượt quét hiện tại**; lần sau có thể thu nhận.

Nếu yêu cầu “đợi **tất cả** rồi tổng hợp một lần”, đừng quét liên tục như trên. Có thể sử dụng `Future.get()` trên từng task với deadline, hoặc `CompletableFuture.allOf(...)` với semantics exception phù hợp.

### 14.1. Ví dụ 7 — tổng hợp có kết quả ổn định (Java 21+)

Tạo tệp `FutureCollectNowDemo.java`:

~~~java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Future;

public class FutureCollectNowDemo {
    public static void main(String[] args) {
        List<Future<Integer>> tasks = List.of(
            CompletableFuture.completedFuture(3),
            CompletableFuture.failedFuture(
                new IllegalArgumentException("broken")
            ),
            CompletableFuture.completedFuture(5),
            new CompletableFuture<>()
        );

        List<Integer> values = tasks.stream()
            .filter(f -> f.state() == Future.State.SUCCESS)
            .map(Future::resultNow)
            .toList();

        List<String> errors = tasks.stream()
            .filter(f -> f.state() == Future.State.FAILED)
            .map(f -> f.exceptionNow().getClass().getSimpleName())
            .toList();

        long unfinished = tasks.stream()
            .filter(f -> f.state() == Future.State.RUNNING)
            .count();

        System.out.println("values = " + values);
        System.out.println("errors = " + errors);
        System.out.println("unfinished = " + unfinished);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac FutureCollectNowDemo.java
java FutureCollectNowDemo
~~~

Stdout:

~~~text
values = [3, 5]
errors = [IllegalArgumentException]
unfinished = 1
~~~

Bốn Future có trạng thái được tạo sẵn, không chạy worker ngoài và không có thread khác cập nhật, nên kết quả lọc và thứ tự list cố định. `Stream.toList()` giữ encounter order của `List` nguồn, còn `Future::resultNow` chỉ gọi với Future đã SUCCESS.

Trong ứng dụng thực, tập Future có thể hoàn thành đồng thời; bảng tổng hợp tức thời không phải snapshot nguyên tử của **toàn bộ** tập task. Muốn bảo đảm mọi task được tính đúng một lần, cần một giao thức thu thập outcome có trạng thái riêng.

## 15. Java Memory Model và tính nhất quán của kết quả

Javadoc `Future` mô tả memory-consistency effect: **các hành động của phép tính bất đồng bộ happen-before những hành động sau lời gọi `Future.get()` tương ứng ở thread khác**. Vì vậy `get()` là một điểm đồng bộ quan trọng khi caller nhận kết quả đã hoàn tất.

Các implementation Future của JDK còn có cơ chế hoàn tất và công bố outcome an toàn. Tuy nhiên, không nên dùng `state()` như một khóa bảo vệ cho **mọi dữ liệu mutable bên ngoài Future**. Một Future SUCCESS không làm các object khác của ứng dụng tự trở thành bất biến, và không thay thế synchronization nếu kết quả chứa tham chiếu tới object tiếp tục bị thread khác sửa.

### 15.1. Phân biệt ba tầng

1. **Task outcome:** Future đã RUNNING/SUCCESS/FAILED/CANCELLED.
2. **Task business data:** dữ liệu kết quả có mutable không, còn được thread nào cập nhật không?
3. **External side effects:** file/network/database có hoàn tất, rollback hoặc cleanup thật sự chưa?

`Future.State` chủ yếu giải quyết tầng thứ nhất. `resultNow()` cho phép lấy kết quả thành công của tầng thứ nhất; nếu giá trị là một mutable object được chia sẻ, tầng thứ hai vẫn cần invariant và ownership. `CANCELLED` cũng không đảm bảo tầng thứ ba đã dừng.

### 15.2. Đừng chờ giả bằng Thread.sleep

~~~java
// SAI về mặt phối hợp, không phải chương trình độc lập.
Thread.sleep(50);
if (future.state() == Future.State.SUCCESS) {
    use(future.resultNow());
}
~~~

Lần chờ 50ms không bảo đảm task đã hoàn tất. Nếu caller cần chờ, `get(timeout, unit)` biểu diễn deadline rõ ràng; nếu caller chỉ muốn xem trạng thái ngay, không cần thêm `sleep`. Hãy dùng latch/barrier trong test khi cần xác định interleaving.

## 16. Những lỗi phổ biến

| Sai lầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Tưởng ba API bắt đầu từ Java 21 | Javadoc ghi `Since: 19` | Ghi rõ **Java 19+**, ví dụ chạy bằng JDK 21+ |
| Tưởng `RUNNING` = thread đang thực thi | RUNNING nghĩa chưa hoàn tất, gồm queued/delayed | Dùng metric executor/thread dump để biết đang thực thi |
| Chỉ thấy `isDone() == true` liền gọi `resultNow()` | FAILED và CANCELLED cũng là done | Kiểm tra `state() == SUCCESS` |
| Gọi `exceptionNow()` khi CANCELLED | CANCELLED không phải FAILED outcome | Ghi nhận cancel riêng |
| Gọi `resultNow()` trên task RUNNING để “chờ ngắn” | Ném `IllegalStateException`, không đợi | Dùng `get(timeout, unit)` nếu cần chờ |
| Dùng `exceptionNow()` như một cách ném exception gốc | Method **trả Throwable**, không throw nó như result | Quyết định report/rethrow theo contract |
| Coi `resultNow() == null` là lỗi | Task thành công có thể trả null | Phân loại qua `state()` |
| Coi `cancel(true)` là worker đã cleanup xong | Future cancellation và worker lifecycle khác nhau | Latch/ack/kênh kết quả riêng |
| Coi mỗi lần periodic task chạy xong là Future SUCCESS | Periodic schedule chưa kết thúc | Thu outcome theo mỗi tick nếu cần |
| Lặp polling `state()` trong spin loop | Tốn CPU và không có hợp đồng deadline | Blocking get, callback hoặc primitive chờ |
| Không đóng scheduled/executor pool | Worker sống lâu, queue còn task | `shutdown`, `awaitTermination`, fallback `shutdownNow` |
| Tin `get(timeout)` tự hủy task khi hết giờ | Timeout chỉ giới hạn chờ của caller | Quyết định `cancel` riêng |
| Bỏ qua InterruptedException của `get()` | Mất tín hiệu hủy của thread đang chờ | Propagate hoặc restore flag theo hợp đồng |
| Bỏ qua nguyên nhân `ExecutionException` | Mất thông tin task FAILED | Đọc `getCause()` hoặc `exceptionNow()` sau FAILED |
| Coi `state()` là snapshot atomic của toàn tập Future | Mỗi Future thay đổi độc lập | Thiết kế aggregation barrier nếu cần |
| Sử dụng `--release 17` với API mới | `Future` Java 17 chưa có ba default method | Biên dịch với target Java 19+ |

## 17. Checklist review khi áp dụng

- Đang biên dịch/chạy với **JDK 21+** hoặc Java 19+ cho ba phương thức mới?
- Có phân biệt rõ `RUNNING` với “đang chạy thực tế” trên worker không?
- `resultNow()` chỉ được gọi khi Future thật sự SUCCESS?
- `exceptionNow()` chỉ được gọi khi Future thật sự FAILED?
- Có xử lý CANCELLED thành outcome riêng thay vì coi đó là exceptionNow?
- Khi cần đợi kết quả, code có dùng `get()` hoặc deadline `get(timeout, unit)` đúng thay vì polling không giới hạn?
- Với Future FAILED, có báo nguyên nhân Throwable thay vì chỉ in `FAILED`?
- Với nullable result, có phân biệt SUCCESS null với thất bại?
- Với `ScheduledFuture`, có hiểu task delayed có thể RUNNING và periodic task không SUCCESS từng tick?
- Có phân biệt Future cancellation state với worker shutdown/cleanup không?
- Có quản lý executor/scheduler `shutdown` và timeout để không rò thread?
- Nếu implementation `Future` là custom, các method `isDone/isCancelled/get` có nhất quán cho default methods hoạt động đúng?
- Có tránh giả định một lượt quét state() cho nhiều Future là một snapshot chung nguyên tử?
- Khi cần visibility của dữ liệu kết quả, có dựa vào `Future.get()` hoặc giao thức đồng bộ thích hợp?
- Special Note của module được tuân thủ bằng việc chỉ nói về Java concurrency và API chuẩn JDK?

## 18. Câu hỏi tự kiểm tra

**1.** `Future.State.RUNNING` có chắc nghĩa là worker đã bắt đầu thực thi task?

**Không.** RUNNING chỉ nghĩa tính toán chưa hoàn tất. Task trong queue hoặc đợi delay cũng có thể RUNNING.

**2.** `isDone()` trả true, có được gọi `resultNow()` không?

**Không thể suy ra**. Future có thể SUCCESS, FAILED hoặc CANCELLED. Chỉ gọi `resultNow()` khi `state() == SUCCESS`.

**3.** `exceptionNow()` trả gì khi task FAILED?

Trả **Throwable gây thất bại** đã được lưu, không chờ. Khác với `get()` ném `ExecutionException` bao bọc nguyên nhân.

**4.** `exceptionNow()` có trả `CancellationException` nếu Future CANCELLED không?

Không theo hợp đồng phương thức này. Với CANCELLED, `exceptionNow()` ném `IllegalStateException` vì Future không phải FAILED. `get()` trên Future bị hủy mới ném `CancellationException`.

**5.** Future SUCCESS có thể trả `null` từ `resultNow()` không?

Có. SUCCESS mô tả outcome, không buộc result là non-null.

**6.** `resultNow()` có chờ task hoàn tất giống `get()` không?

Không. Nếu chưa hoàn tất hoặc kết thúc ở trạng thái không thành công, nó ném `IllegalStateException`.

**7.** Một `ScheduledFuture` hẹn chạy sau một ngày có thể báo RUNNING ngay sau schedule không?

Có. Trong enum Future, RUNNING chỉ có nghĩa “chưa hoàn tất”, không phải đang thực thi CPU.

**8.** Task periodic chạy xong lần đầu. `ScheduledFuture.state()` có bắt buộc SUCCESS không?

Không. Một periodic future thường còn đại diện cho **các lần chạy kế tiếp**; khi tiếp tục được lịch hóa, nó chưa hoàn tất toàn bộ.

**9.** `Future.cancel(true)` đổi trạng thái thành CANCELLED có chứng minh worker đã đóng mọi tài nguyên không?

Không. Cần xác nhận hoàn thành cleanup riêng nếu nghiệp vụ đòi hỏi.

**10.** Ba API được thêm lần đầu ở Java 21 hay Java 19?

**Java 19.** Chúng có sẵn trong Java 21; ví dụ dùng JDK 21+ để khớp môi trường bài học.

**11.** Có thể dùng `Future::resultNow` trong stream mà không kiểm tra state không?

Không an toàn khi stream chứa các Future RUNNING, FAILED hay CANCELLED. Lọc `f.state() == Future.State.SUCCESS` trước.

**12.** Nếu Future FAILED thì `get()` với `exceptionNow()` khác nhau về biểu diễn exception thế nào?

`get()` ném `ExecutionException`, lấy nguyên nhân qua `getCause()`. `exceptionNow()` trả `Throwable` gốc khi Future đã FAILED.

## 19. Tóm tắt và tài liệu chuẩn

**Quy tắc ngắn gọn:**

~~~text
Future.State.RUNNING   -> Chưa có outcome, không gọi method Now
Future.State.SUCCESS   -> future.resultNow()
Future.State.FAILED    -> future.exceptionNow()
Future.State.CANCELLED -> Xử lý hủy riêng; không lấy result/exceptionNow
~~~

`Future.state()` giúp phân loại một outcome không cần chờ. `resultNow()` và `exceptionNow()` giúp đọc đúng kết quả đã hoàn tất mà không cần gọi `get()` để thăm dò. Khi phải **đợi**, dùng `get()` và quản lý deadline/cancellation; khi phải **xác nhận cleanup**, có kênh hoàn tất riêng. Luôn phân biệt Future outcome với trạng thái worker và với side effect ở hệ thống ngoài.

Tài liệu chính thức để đối chiếu hợp đồng và mốc “Since: 19”:

- [Future (JDK 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html)
- [Future.State (JDK 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.State.html)
- [ScheduledExecutorService (JDK 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html)

**Ghi nhớ:** Đọc trạng thái **không phải** đợi hoàn tất; SUCCESS/FAILED/CANCELLED là ba outcome khác nhau, còn RUNNING chỉ có nghĩa “chưa xong”. Chọn đúng API theo câu hỏi mà ứng dụng đang cần trả lời.