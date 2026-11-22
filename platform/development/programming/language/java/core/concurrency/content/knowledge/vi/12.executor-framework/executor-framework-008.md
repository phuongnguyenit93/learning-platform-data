# ThreadFactory và UncaughtExceptionHandler trong Java Executor Framework

## 1. Tại sao cần quan tâm đến cách tạo thread và cách báo lỗi?

Một `ExecutorService` nhận các task và quyết định khi nào, ở worker nào chúng được chạy. Người viết ứng dụng thường chỉ gọi `execute(...)` hoặc `submit(...)`, nhưng trong vận hành cần trả lời thêm:

- Worker thread được **đặt tên** ra sao để đọc thread dump và log?
- Worker được tạo dưới **ThreadGroup**, daemon flag, priority, context class loader và handler nào?
- Nếu task ném `RuntimeException`/`Error` không được xử lý, **ai nhận biết**?
- Nếu task chạy qua `submit(...)` bị lỗi, vì sao `UncaughtExceptionHandler` có thể không được gọi?
- Khi một worker kết thúc bất thường, executor có tạo worker khác không? Lỗi của task cũ có tự được chạy lại không?
- Làm thế nào ghi nhận lỗi nhưng **không làm hỏng chính sách shutdown và quản lý tài nguyên**?

Hai API ở trung tâm:

1. **`java.util.concurrent.ThreadFactory`**: chiến lược tạo đối tượng `Thread` cho executor. Factory không quản lý queue, không tự chạy task và không tự quyết định lỗi task được biểu diễn ra sao.
2. **`Thread.UncaughtExceptionHandler`**: callback của một thread khi thread **đang kết thúc do một ngoại lệ không được bắt**. Nó không phải callback chung cho mọi task thất bại trong executor.

**Điểm phân biệt cốt lõi:** `ThreadPoolExecutor.execute(Runnable)` với một `Runnable` ném exception có thể khiến exception thoát khỏi worker và đến uncaught handler. Ngược lại, `submit(...)` thường bao task trong một `FutureTask`, nên exception được **lưu vào Future**, không thoát thành một uncaught exception từ `Thread.run()`.

Bài học này nằm trong phạm vi **Executor Framework và Java concurrency nói chung**. Các ví dụ sử dụng API chuẩn của JDK 17+ và không dựa vào framework khác.

### Mục tiêu học tập

Sau bài, bạn có thể:

1. Viết `ThreadFactory` đặt tên worker dễ đọc và gắn handler khi cần.
2. Hiểu vì sao factory phải trả về **thread chưa được start**, và vì sao một factory có thể được gọi nhiều lần trong suốt vòng đời pool.
3. Phân biệt exception đi qua `execute()`, `submit()`, `Future.get()` và `Thread.UncaughtExceptionHandler`.
4. Biết cách mở rộng `ThreadPoolExecutor.afterExecute(...)` để giám sát task đúng cách, kể cả lỗi bị Future giữ lại.
5. Quản lý worker failure, replacement, shutdown, retry và tránh hiểu nhầm handler là cơ chế khôi phục task.
6. Kiểm tra lỗi có kênh quan sát rõ ràng, không dựa vào thứ tự log của nhiều thread.

## 2. ThreadFactory: trách nhiệm và hợp đồng

### 2.1. Giao diện đơn giản nhưng tác động lớn

`ThreadFactory` là một functional interface:

~~~java
// Chữ ký API, không phải chương trình độc lập.
public interface ThreadFactory {
    Thread newThread(Runnable r);
}
~~~

Executor truyền một `Runnable` nội bộ cần được thực thi vào `newThread(r)`. Factory tạo và **trả về một Thread chưa được start**. Executor chịu trách nhiệm gọi `start()` khi thích hợp.

Một factory có thể thiết lập:

- **Name** có tiền tố chức năng cùng số tăng: `orders-worker-1`, `orders-worker-2`.
- **Daemon** khi có lý do lifecycle rõ ràng; thường tránh daemon cho công việc quan trọng phải được shutdown có kiểm soát.
- **Priority** nếu thật sự hiểu các giới hạn scheduler; không dùng thread priority làm bảo đảm thứ tự nghiệp vụ.
- **UncaughtExceptionHandler** để ghi nhận một số lỗi chưa được bắt ở cấp thread.
- ThreadGroup hoặc context class loader khi môi trường và ownership yêu cầu, không tùy tiện dùng để giải quyết lỗi ứng dụng.

Factory **không** nên tự `start()` thread, gọi `r.run()` ngay trong factory hoặc trả một thread đã được start. Những hành động đó phá giả định của executor về thời điểm tạo worker và có thể làm phát sinh `IllegalThreadStateException` hoặc hành vi không phù hợp.

### 2.2. Không tạo một thread cho mỗi task theo giả định

`newFixedThreadPool(2, factory)` có thể dùng cùng hai worker để chạy rất nhiều task. `ThreadFactory.newThread(...)` được gọi **khi executor cần tạo worker**, không phải mỗi lần gọi `submit()`.

Một số tình huống factory có thể được gọi thêm:

- Pool chưa có đủ worker và cần worker mới.
- Một worker **kết thúc bất thường** và pool cần duy trì số worker theo cấu hình/trạng thái.
- Pool co giãn hoặc thay thế worker dựa trên chính sách `ThreadPoolExecutor`.

Ngược lại, factory có thể **không được gọi** khi task mới được xếp queue và worker hiện có sẽ thực thi nó. Do đó không nên đặt initialization **cho mỗi task** vào factory. Dữ liệu ngữ cảnh của request/task nên được truyền qua task hoặc wrapper và dọn đúng vòng đời task.

### 2.3. Ví dụ tối giản về factory

~~~java
// Mã minh họa; cần imports và dùng bên trong một method.
AtomicInteger nextId = new AtomicInteger();

ThreadFactory factory = task -> {
    Thread thread = new Thread(
        task, "compute-worker-" + nextId.incrementAndGet()
    );
    thread.setDaemon(false);
    thread.setUncaughtExceptionHandler((t, error) -> {
        System.err.println(
            "Uncaught in " + t.getName() + ": " + error
        );
    });
    return thread; // Chưa start.
};

ExecutorService pool = Executors.newFixedThreadPool(2, factory);
~~~

Đặt `AtomicInteger` cho counter tên giúp factory an toàn khi nhiều caller cùng lúc yêu cầu tạo worker. Không mặc định rằng factory luôn được gọi từ đúng một thread.

**Giới hạn:** `UncaughtExceptionHandler` bên trên chỉ chạy khi có uncaught throwable tới tận ranh giới thread theo hợp đồng. Nó không quan sát tất cả lỗi từ `FutureTask`, và không phải nơi chạy xử lý retry nghiệp vụ.

## 3. Ví dụ 1 — đặt tên worker với ThreadFactory (Java 17+)

Để minh họa rằng hai thread của fixed pool có tên riêng mà không dựa vào thứ tự scheduling, ta cho cả hai task chờ tại một latch rồi in **tập tên đã sắp xếp**.

Tạo tệp `NamedWorkersDemo.java`:

~~~java
import java.util.List;
import java.util.TreeSet;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.ThreadFactory;

public class NamedWorkersDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger ids = new AtomicInteger();

        ThreadFactory factory = command -> {
            Thread worker = new Thread(
                command, "lesson-worker-" + ids.incrementAndGet()
            );
            worker.setDaemon(false);
            return worker;
        };

        ExecutorService pool =
            Executors.newFixedThreadPool(2, factory);
        CountDownLatch entered = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<String> first = pool.submit(() -> {
                entered.countDown();
                release.await();
                return Thread.currentThread().getName();
            });

            Future<String> second = pool.submit(() -> {
                entered.countDown();
                release.await();
                return Thread.currentThread().getName();
            });

            entered.await();
            release.countDown();

            TreeSet<String> names =
                new TreeSet<>(List.of(first.get(), second.get()));
            System.out.println("workers = " + names);
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

Biên dịch và chạy:

~~~bash
javac NamedWorkersDemo.java
java NamedWorkersDemo
~~~

Stdout khi hai task hoàn tất bình thường:

~~~text
workers = [lesson-worker-1, lesson-worker-2]
~~~

Giải thích:

1. `newFixedThreadPool(2, factory)` có đủ năng lực chạy hai task đồng thời.
2. `entered` bảo đảm cả hai task đã được worker nhận và tới điểm chờ; nếu chỉ một worker tồn tại, cả hai không thể cùng đếm latch trước khi một trong hai rời latch, nên executor phải tạo worker thứ hai để tiến triển.
3. `release` giải phóng cả hai task sau khi chúng đều đã tới điểm chờ.
4. `Future.get()` đợi kết quả của từng task và truyền lỗi task qua `ExecutionException` khi có lỗi.
5. `TreeSet` sắp tên trước khi in, tránh phụ thuộc task nào hoàn thành trước.
6. `shutdown()` kết hợp `awaitTermination()` thể hiện việc quản lý pool có kiểm soát. `shutdownNow()` trong đường timeout là yêu cầu hủy tốt nhất có thể (*best effort*), không phải phép ép tất cả task kết thúc.

**Không suy ra từ ví dụ rằng factory được gọi mỗi lần submit.** Lần chạy này chỉ chứng minh hai worker được tạo vì hai task cần chạy cùng lúc. Khi những task tiếp theo được gửi vào pool, chúng có thể được thực thi bởi chính hai worker đã tạo.

## 4. UncaughtExceptionHandler làm gì?

### 4.1. Callback cấp thread

`Thread.UncaughtExceptionHandler` có method:

~~~java
// Chữ ký giao diện, không phải chương trình độc lập.
void uncaughtException(Thread thread, Throwable error);
~~~

Khi một thread chuẩn bị kết thúc vì throwable không được xử lý, Java chuyển thông tin tới handler phù hợp. Handler có thể ghi lại tên thread, loại throwable, stack trace và số lần xảy ra lỗi.

Các cách gắn handler:

- `thread.setUncaughtExceptionHandler(handler)`: handler riêng cho thread đó.
- `Thread.setDefaultUncaughtExceptionHandler(handler)`: handler mặc định ở phạm vi JVM cho những thread không có handler rõ ràng, tùy cơ chế fallback/ThreadGroup.
- Gắn vào **mọi thread được tạo qua factory** để có phạm vi giám sát nhất quán đối với worker do factory tạo.

Với executor, thường nên gắn handler **khi factory khởi tạo thread**, thay vì cố tìm worker đang chạy để thay đổi handler.

### 4.2. Handler không thay thế exception handling trong task

Cần phân biệt ba ranh giới:

~~~text
Task business code
      |
      +--> tự try/catch lỗi: task đã xử lý, handler không thấy
      |
      +--> execute(Runnable) -> Runnable.run() throws
      |                       -> worker có thể chết bất thường
      |                       -> UncaughtExceptionHandler nhận Throwable
      |
      +--> submit(Runnable/Callable)
                              -> FutureTask.run() bắt Throwable
                              -> Future ghi nhận lỗi
                              -> Future.get() ném ExecutionException
                              -> Không có uncaught throwable từ task
~~~

`UncaughtExceptionHandler` không bắt lỗi checked exception theo nghĩa thay caller giải quyết mọi lỗi; `Runnable.run()` không khai báo checked exception. Nếu bạn chuyển checked exception thành `RuntimeException` và throwable đó thật sự thoát khỏi worker, handler mới có cơ hội nhận.

**Điểm bảo đảm cần dựa vào:** Lỗi task qua `submit` được đưa vào Future và phải quan sát qua Future hoặc một hook/cơ chế được thiết kế. Việc chỉ gắn handler cho thread pool **không** bảo đảm bạn sẽ thấy các lỗi của mọi task submit.

### 4.3. Giới hạn của chính handler

Một handler nên:

- **Ngắn gọn và an toàn**: ghi nhận lỗi, metric hoặc gửi tín hiệu cảnh báo bằng đường ít phụ thuộc.
- Tránh ném thêm exception; uncaught exception phát sinh từ chính handler thường bị cơ chế runtime bỏ qua ở ranh giới đó.
- Tránh chờ vô hạn, không lấy những lock có thể gây deadlock trong quá trình logging.
- Tránh gọi lại chính executor đang hỏng để gửi một task thông báo quan trọng mà không có fallback.
- Không gọi `Thread.stop()`, không “cứu sống” thread đang kết thúc hoặc giả vờ task thất bại đã được retry thành công.

Nếu ứng dụng muốn retry task lỗi, cần hệ thống retry theo idempotency, giới hạn lần thử, deadline và báo kết quả. **Handler chỉ là điểm quan sát thất bại của thread**, không phải retry policy.

## 5. execute() và submit(): khác biệt quan trọng nhất của bài

### 5.1. `execute(Runnable)`

`Executor.execute(Runnable)` chỉ yêu cầu executor thực thi task. Nó **không trả `Future`** cho caller để lấy kết quả hoặc checked exception.

Với `ThreadPoolExecutor` chuẩn khi một `Runnable` được truyền trực tiếp vào `execute` và ném `RuntimeException`/`Error` không được bắt, throwable có thể thoát khỏi `run()` của worker. `ThreadPoolExecutor` gọi `afterExecute` với throwable và worker có thể kết thúc bất thường; cơ chế uncaught của thread có thể nhận throwable đó.

**Không đánh đồng:** điều này đúng cho mô hình worker của `ThreadPoolExecutor` chuẩn, không phải lời hứa rằng bất kỳ `Executor` custom nào cũng có cùng chính sách. Một executor tự viết có thể bắt mọi throwable hoặc thực thi task ngay trên caller.

### 5.2. `submit(Runnable/Callable)`

`ExecutorService.submit(...)` trả về `Future<?>` hoặc `Future<V>`. Với triển khai `ThreadPoolExecutor` thông thường, task được chuyển thành `RunnableFuture` như `FutureTask`. `FutureTask.run()` bắt exception và lưu outcome.

Nếu task thất bại:

~~~java
// Mã minh họa; executor đã được tạo.
Future<?> result = executor.submit(
    () -> { throw new IllegalStateException("task failed"); }
);

try {
    result.get();
} catch (ExecutionException failure) {
    Throwable root = failure.getCause();
    // Báo lỗi, chuyển thành lỗi tầng caller hoặc xử lý có kiểm soát.
}
~~~

`get()` là cách tiêu chuẩn để caller biết lỗi task. Nếu caller **không lưu Future hoặc không gọi get/quan sát bằng cách khác**, lỗi có thể bị bỏ qua trong luồng điều phối mà không xuất hiện tại uncaught handler.

### 5.3. Lưu ý: `execute(FutureTask)` vẫn có thể giấu exception

Bí quyết không chỉ là “tên phương thức execute hay submit”, mà còn là **wrapper task có bắt throwable hay không**. Nếu bạn truyền một `FutureTask` trực tiếp cho `execute()`, chính `FutureTask.run()` có thể bắt lỗi và giữ nó trong FutureTask, nên uncaught handler vẫn không thấy lỗi đó.

Vì thế quy tắc vận hành là: **xem cách task được đóng gói và nơi kết quả/exception được lưu**, không chỉ đếm số lần handler được gọi.

## 6. Ví dụ 2 — lỗi từ execute() tới UncaughtExceptionHandler (Java 17+)

Ví dụ này gắn handler ngay trong factory và dùng latch để bảo đảm main đã thấy handler xử lý lỗi trước khi in. Để stdout ổn định, handler lưu **tên loại ngoại lệ** thay vì in stack trace ngẫu nhiên giữa các thread.

Tạo tệp `ExecuteUncaughtDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.ThreadFactory;

public class ExecuteUncaughtDemo {
    public static void main(String[] args)
            throws InterruptedException {
        CountDownLatch handled = new CountDownLatch(1);
        AtomicReference<String> observed =
            new AtomicReference<>("none");

        ThreadFactory factory = command -> {
            Thread worker = new Thread(command, "execute-worker");
            worker.setUncaughtExceptionHandler((thread, error) -> {
                observed.set(error.getClass().getSimpleName());
                handled.countDown();
            });
            return worker;
        };

        ExecutorService pool =
            Executors.newSingleThreadExecutor(factory);

        try {
            pool.execute(() -> {
                throw new IllegalStateException("from execute");
            });

            handled.await();
            System.out.println("handler = " + observed.get());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ExecuteUncaughtDemo.java
java ExecuteUncaughtDemo
~~~

Stdout trong mô hình `ThreadPoolExecutor` chuẩn của ví dụ:

~~~text
handler = IllegalStateException
~~~

Lần `execute` gửi một `Runnable` **không được FutureTask bọc**. `IllegalStateException` thoát khỏi `run()`, đi qua worker executor và cuối cùng tới handler của worker. Handler ghi loại throwable và đếm latch. Main chỉ in sau `handled.await()` nên không phụ thuộc vào thứ tự log của hai thread.

**Worker hỏng không đồng nghĩa toàn pool chết:** `ThreadPoolExecutor` thường có thể tạo worker thay thế theo chính sách pool khi worker cũ kết thúc bất thường. Nhưng **task vừa ném lỗi không tự chạy lại**. Dù có worker thay thế, lỗi task và kết quả nghiệp vụ vẫn phải được giám sát riêng.

Không đặt kỳ vọng tên worker luôn là `execute-worker` duy nhất trên mọi lần tạo; nếu factory dùng một tên cố định như ví dụ, worker thay thế có thể trùng tên. Trong sản phẩm thực, nên có counter tăng cho từng worker, như `NamedWorkersDemo`.

## 7. Ví dụ 3 — submit() giữ exception trong Future (Java 17+)

Ví dụ tương phản dùng cùng kỹ thuật handler nhưng gửi task bằng `submit`. Handler **không nhận lỗi task**, trong khi `Future.get()` trả lỗi rõ ràng.

Tạo tệp `SubmitCapturedDemo.java`:

~~~java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.ThreadFactory;

public class SubmitCapturedDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger handlerCalls = new AtomicInteger();

        ThreadFactory factory = command -> {
            Thread thread = new Thread(command, "submit-worker");
            thread.setUncaughtExceptionHandler((t, error) -> {
                handlerCalls.incrementAndGet();
            });
            return thread;
        };

        ExecutorService pool =
            Executors.newSingleThreadExecutor(factory);

        try {
            Future<?> future = pool.submit(() -> {
                throw new IllegalArgumentException("from submit");
            });

            try {
                future.get();
            } catch (ExecutionException failure) {
                System.out.println("future cause = "
                    + failure.getCause().getClass().getSimpleName());
            }

            System.out.println("handler calls = "
                + handlerCalls.get());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac SubmitCapturedDemo.java
java SubmitCapturedDemo
~~~

Stdout:

~~~text
future cause = IllegalArgumentException
handler calls = 0
~~~

Giải thích:

- `submit` trả `Future` và triển khai pool chuẩn lưu `IllegalArgumentException` làm nguyên nhân lỗi.
- `future.get()` chờ task hoàn thành rồi ném `ExecutionException`; `getCause()` là exception gốc của task.
- Vì exception không thoát khỏi `FutureTask.run()` để làm worker kết thúc bất thường, handler không nhận lỗi này.
- Nếu không gọi `get()` hoặc một cơ chế quan sát phù hợp, lỗi có thể bị bỏ sót dù chương trình vẫn chạy tiếp.

**Không suy luận rằng uncaught handler không hữu ích.** Nó vẫn có giá trị giám sát một số failure cấp thread/execute; chỉ không thay thế được kết quả của Future.

## 8. Một bảng quyết định chẩn đoán lỗi

| Task chạy như thế nào? | Exception đi đâu? | Có nhất thiết tới UncaughtExceptionHandler? | Cách quan sát chính |
| --- | --- | --- | --- |
| `new Thread(r).start()`, `r.run()` ném không bắt | Ranh giới thread | Có theo cơ chế uncaught của Thread | Handler + log |
| `ThreadPoolExecutor.execute(plainRunnable)`, `run()` ném | Qua worker, có thể làm worker kết thúc đột ngột | Thường có với pool chuẩn | Handler hoặc `afterExecute` |
| `ExecutorService.submit(Runnable)` ném | `FutureTask`/`Future` | **Không**, lỗi bị giữ lại | `Future.get()` |
| `ExecutorService.submit(Callable)` ném | `Future` | **Không**, lỗi bị giữ lại | `Future.get()` |
| `execute(FutureTask)` ném trong delegate | `FutureTask` | Không mặc định | `FutureTask.get()` |
| Task tự `try/catch` và xử lý lỗi | Code task | Không, nếu không rethrow | Kênh kết quả/log của task |
| `CompletableFuture.supplyAsync(...)` ném | Completion stage thất bại | Không cần tới handler | `join()`, `get()`, `whenComplete` |
| Task bị hủy qua `Future.cancel(true)` | Trạng thái Future và yêu cầu interrupt | Không mặc định | `CancellationException`/state + xác nhận cleanup riêng |

Không coi bảng này như cam kết về mọi `Executor` tự viết: chính cách triển khai executor/wrapper quyết định ranh giới bắt lỗi. Với `ExecutorService` thuộc JDK, tập trung vào hợp đồng Future và các hook chuyên biệt.

## 9. ThreadPoolExecutor.afterExecute(): giám sát cả execute và submit

### 9.1. Hook này giải quyết vấn đề gì?

`ThreadPoolExecutor` cung cấp hook:

~~~java
// Chữ ký method để override, không phải chương trình độc lập.
protected void afterExecute(Runnable task, Throwable error)
~~~

Nó được gọi khi một task trong executor vừa chạy xong. Nếu một `plain Runnable` ném exception trực tiếp khi `execute`, đối số `error` có thể là throwable. Nhưng với `submit`, task thông thường là một `FutureTask` bắt exception vào nội bộ; vì vậy **`error` thường là null ngay cả khi task thất bại**.

Nếu muốn quan sát lỗi từ `submit` ở hook này, cần xem `task instanceof Future<?>` và lấy outcome từ Future bằng cách thích hợp.

### 9.2. Mẫu hook an toàn và giới hạn

~~~java
// Mẫu trong subclass ThreadPoolExecutor, không phải chương trình độc lập.
@Override
protected void afterExecute(Runnable task, Throwable failure) {
    super.afterExecute(task, failure);

    Throwable observed = failure;
    if (observed == null && task instanceof Future<?> future) {
        try {
            future.get();
        } catch (CancellationException canceled) {
            // Cancellation là một trạng thái riêng, không mặc định lỗi task.
        } catch (ExecutionException executedWithFailure) {
            observed = executedWithFailure.getCause();
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
        }
    }

    if (observed != null) {
        reportTaskFailure(observed);
    }
}
~~~

Đoạn trên cần import các loại `Future`, `CancellationException`, `ExecutionException` và `InterruptedException`. Đây là mẫu JDK phổ biến; **không nên gọi `get()` mù quáng trên bất kỳ Future chưa hoàn thành** ở nơi khác. Trong `afterExecute` của `ThreadPoolExecutor`, task đã chạy xong theo cơ chế thông thường nên FutureTask do `submit` tạo đã hoàn tất và `get()` không cần chờ tác vụ đó chạy tiếp.

Cũng cần xem xét các wrapper khác: nếu một `Runnable` chứa Future của task khác chưa hoàn thành, hoặc một implementation tùy chỉnh trả Future không gắn với task vừa kết thúc, `get()` có thể block. Hook production không nên block vô hạn. Nếu có `Future.isDone()`, có thể kiểm tra trước khi lấy kết quả, hoặc chỉ unwrap những wrapper mình kiểm soát.

**Không ném exception ngoài ý muốn từ `afterExecute`.** Theo mô hình `ThreadPoolExecutor`, exception thoát từ hook có thể khiến worker kết thúc đột ngột, gây thêm thay thế worker và che mất nguyên nhân nghiệp vụ. Hãy ghi nhận lỗi bằng đường bền vững, ít phụ thuộc và tránh gọi I/O lâu trong hook nếu cần throughput tốt.

### 9.3. Ví dụ 4 — quan sát submit exception trong afterExecute (Java 17+)

Tạo tệp `AfterExecuteDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class AfterExecuteDemo {
    static final class ObservingPool extends ThreadPoolExecutor {
        final CountDownLatch observed = new CountDownLatch(1);
        final AtomicReference<String> cause = new AtomicReference<>("none");

        ObservingPool() {
            super(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new LinkedBlockingQueue<>()
            );
        }

        @Override
        protected void afterExecute(Runnable task, Throwable failure) {
            super.afterExecute(task, failure);

            Throwable found = failure;
            if (found == null && task instanceof Future<?> future) {
                try {
                    future.get();
                } catch (ExecutionException ex) {
                    found = ex.getCause();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            }

            if (found != null) {
                cause.set(found.getClass().getSimpleName());
            }
            observed.countDown();
        }
    }

    public static void main(String[] args) throws Exception {
        ObservingPool pool = new ObservingPool();
        try {
            Future<?> future = pool.submit(() -> {
                throw new IllegalArgumentException("sample");
            });

            try {
                future.get();
            } catch (ExecutionException expected) {
                // Caller đã nhận exception, hook cũng sẽ quan sát.
            }

            pool.observed.await();
            System.out.println("afterExecute = " + pool.cause.get());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac AfterExecuteDemo.java
java AfterExecuteDemo
~~~

Stdout:

~~~text
afterExecute = IllegalArgumentException
~~~

`future.get()` bên ngoài quan sát lỗi ở caller. `afterExecute` chạy sau task, thấy `failure == null` do wrapper FutureTask đã giữ exception, sau đó lấy `getCause()` từ Future. `observed` giúp main chờ hook đã ghi nhận xong trước khi in, nên không phụ thuộc thứ tự scheduling.

Ví dụ chỉ gửi một task thất bại và không hủy nó, nên không cần nhánh riêng cho `CancellationException`. **Trong ứng dụng thật**, hook phải xử lý cả Future bị hủy và mọi loại wrapper, cũng như giữ hook ngắn và không block. Mẫu này thể hiện cách nhìn rõ failure của task chứ không thay thế quản lý retry ở tầng nghiệp vụ.

### 9.4. Dùng hook hay quan sát Future ở caller?

- Khi caller **cần kết quả để ra quyết định**, dùng `Future.get()` hoặc stage composition phù hợp; exception thuộc contract xử lý kết quả.
- Khi cần **giám sát tập trung** mọi task của một `ThreadPoolExecutor` tự quản, `afterExecute` hoặc task wrapper có thể ghi nhận metric và lỗi.
- Khi chỉ cần log **uncaught thread failure**, handler là lớp bảo vệ bổ sung, không phải hệ thống xử lý mọi Future.

Có thể dùng kết hợp cả ba, nhưng cần tránh ghi lỗi trùng nhiều lần và nhớ rằng **log lỗi không phải nghiệp vụ đã xử lý lỗi**.

## 10. Worker chết bất thường và khả năng thay thế

### 10.1. Một task throw có nghĩa gì đối với pool?

Trong `ThreadPoolExecutor`, khi một `Runnable` thoát bằng throwable không bắt, worker đang chạy task đó có thể kết thúc bất thường. Pool có cơ chế quản lý worker count và **có thể tạo worker thay thế** tùy cấu hình và trạng thái executor.

Nhưng những điều sau **không tự xảy ra**:

- Task thất bại được tự chạy lại như một transaction.
- Side effect đã làm một nửa được rollback.
- Người submit qua `execute` tự có một Future để nhận exception.
- Future của task submit bị lỗi sẽ gửi exception qua handler.
- Mọi tài nguyên phụ thuộc ThreadLocal được dọn sạch trước khi worker chết.
- Shutdown của executor trở nên an toàn dù task đang giữ resource hoặc lock khác.

Nếu cần retry, phải thiết kế cơ chế xác định task có idempotent hay không, số lần thử, backoff/deadline và kênh trả kết quả. Với tác vụ gửi email/chuyển tiền, retry vô điều kiện có thể lặp side effect.

### 10.2. ThreadFactory không kiểm soát lịch task

Một factory được gọi khi pool cần worker. Nó **không** được gọi mỗi lần task bắt đầu nên:

- Không đặt request ID hoặc user context cho từng task bằng cấu hình thread cố định.
- Không gắn thông tin task hiện hành vào tên thread trong factory rồi giả định nó thay đổi theo task.
- Không dùng `UncaughtExceptionHandler` để xử lý business-level rollback của từng request.
- Với `ThreadLocal`/MDC, hãy đặt và xóa trong task wrapper hoặc hook được thiết kế, bằng `try/finally`.

Một worker có thể chạy hàng nghìn task; context còn sót của task trước có thể ảnh hưởng task sau, kể cả khi không có exception. Nếu bạn sửa tên thread cho từng task, hãy restore tên gốc trong finally để tránh rò rỉ metadata giữa task.

## 11. Daemon, priority, context class loader và security

### 11.1. Daemon workers

`Thread.setDaemon(true)` khiến thread là daemon. JVM có thể kết thúc khi chỉ còn daemon threads, vì vậy những công việc cần ghi dữ liệu, flush queue hay cleanup lúc shutdown **không nên chỉ dựa vào daemon status**.

Một pool có daemon worker **không** có nghĩa rằng task sẽ hoàn thành trước khi JVM thoát. Trái lại, non-daemon worker có thể giữ JVM sống nếu quên shutdown pool. Vì thế lựa chọn daemon phải đi kèm lifecycle, không phải thủ thuật chữa pool “không chịu thoát”.

Trong `ThreadFactory`, gọi `setDaemon(...)` trước khi thread start; không cố thay đổi daemon status của thread đã chạy. Tên và priority cũng nên được cấu hình trước khi return thread.

### 11.2. Thread priority

`setPriority(...)` phụ thuộc JVM và scheduler, không bảo đảm task priority, FIFO hoặc throughput theo công thức đơn giản. Không dùng thread priority thay cho queue có thứ tự hoặc cơ chế SLA.

### 11.3. Context class loader

Worker có thể kế thừa context class loader của thread tạo nó, tùy cách constructor/triển khai được sử dụng. Với môi trường plugin, module hoặc class loading phức tạp, việc giữ context class loader quá lâu có thể giữ reference ngoài ý muốn. Cần chính sách rõ về class loader, nhưng không tự đổi nó thành null hay system loader nếu chưa biết nhu cầu của thư viện gọi từ task.

### 11.4. ThreadGroup và handler mặc định

Khi không có handler riêng trên thread, cơ chế fallback có thể đi qua `ThreadGroup` và default handler. Điều này hữu ích cho chẩn đoán, nhưng handler ở factory là lựa chọn rõ ràng hơn nếu bạn muốn ghi nhận lỗi của **một nhóm worker cụ thể** mà không thay đổi hành vi của các thread khác trong JVM.

Không nên cấu hình `Thread.setDefaultUncaughtExceptionHandler(...)` như một thao tác cục bộ vô hại: nó có tác động ở cấp JVM và có thể ghi đè chính sách global của thư viện hoặc ứng dụng khác.

## 12. Lỗi task, cancellation và interrupt không giống nhau

### 12.1. `Future.cancel(true)` là yêu cầu hủy, không phải exception từ task

Một task đang chờ `BlockingQueue.take()` hay `Thread.sleep()` có thể phản ứng với interrupt bằng `InterruptedException`. Nếu task được chạy qua `submit`, việc task kết thúc do hủy hoặc exception thường được phản ánh qua **Future state** và contract riêng của executor.

Đừng chờ `UncaughtExceptionHandler` nhận mọi `InterruptedException`: đây là checked exception mà nhiều API task xử lý hoặc đưa vào Future; nó không mặc nhiên thoát khỏi `Thread.run()`. Với `Callable`, exception được ném vào boundary `FutureTask` và quan sát qua `get()`.

### 12.2. Future.cancel không xác nhận worker đã cleanup

`Future.cancel(true)` có thể đánh dấu future hủy dù code task vẫn đang chạy một thời gian, ví dụ vì nó không kiểm tra interrupt hoặc đang dọn tài nguyên. Nếu cần biết **cleanup đã hoàn tất**, dùng một kênh xác nhận riêng như latch, trạng thái task hoặc cấu trúc phối hợp thích hợp.

`CompletableFuture.cancel(true)` không dùng tham số `mayInterruptIfRunning` để điều khiển execution theo hợp đồng API. Vì vậy không suy ra CompletableFuture đang chạy sẽ bị interrupt giống một task qua `FutureTask`.

### 12.3. Một số lỗi có thể làm hỏng JVM hoặc process

`UncaughtExceptionHandler` là callback quan sát lỗi, không phải ranh giới phục hồi tin cậy cho mọi `Error`. Ví dụ tình trạng thiếu bộ nhớ, stack overflow hoặc lỗi hệ thống nghiêm trọng có thể khiến logging/metric trong handler cũng thất bại. Đừng cố đảm bảo mọi failure đều được handler ghi nhận hoặc có thể tiếp tục bình thường sau một `Error`.

## 13. Làm sao kiểm thử exception reporting?

### 13.1. Kiểm thử bằng latch và Future, không bằng ngủ đoán thời gian

Với handler, test có thể dùng `CountDownLatch` đặt ngay trong callback để xác nhận nó đã được gọi. Với `submit`, sử dụng `Future.get()` để quan sát nguyên nhân `ExecutionException`. Với `afterExecute`, dùng latch hoặc kênh kết quả để xác nhận hook đã hoàn thành trước khi assert.

Đừng viết:

~~~java
// Sai về cách kiểm chứng, không phải chương trình độc lập.
executor.execute(() -> { throw new RuntimeException("boom"); });
Thread.sleep(100);
assert handlerCalled;
~~~

Scheduler có thể khiến task/handler chưa chạy sau 100ms dù code đúng. Dùng latch với timeout trong bài test giúp phản ánh lỗi mà không để suite treo vĩnh viễn.

### 13.2. Những case nên kiểm tra

| Test | Kết quả cần xác nhận |
| --- | --- |
| Factory đặt tên worker | Tên có tiền tố, ID đủ phân biệt, thread chưa start ở factory |
| Pool tái sử dụng worker | Nhiều task có thể chạy chung worker, không dùng factory per-task |
| `execute(plainRunnable)` ném unchecked | Handler/hook nhận lỗi theo triển khai pool chuẩn |
| `submit(Callable)` ném unchecked | `Future.get()` có `ExecutionException` với cause đúng |
| `submit(Runnable)` ném unchecked | Handler không phải kênh nhận lỗi mặc định |
| `execute(FutureTask)` ném trong delegate | Lỗi được giữ trong FutureTask; không suy ra handler chạy |
| Task tự catch exception | Không có uncaught throwable nếu không rethrow |
| `afterExecute` với Future lỗi | Hook unwrap được cause sau khi Future hoàn tất |
| Future bị cancel | Phân biệt cancellation với failure thông thường |
| Worker kết thúc bất thường | Pool có thể tạo worker khác; task cũ không tự retry |
| Shutdown | Không rò rỉ worker, không chờ vô hạn; xử lý timeout |
| Handler/hook tự throw | Không để reporting path phá hỏng sự ổn định của pool |

### 13.3. Kênh kết quả và quan sát lỗi

Một thiết kế tốt nên trả lời: **ai sở hữu trách nhiệm xem lỗi task?**

- Caller của `submit` giữ Future và gọi `get()`, hoặc chuyển nó cho một tầng quản lý có trách nhiệm theo dõi.
- Một hệ thống fire-and-forget có thể dùng task wrapper: bắt `Throwable` ở ranh giới phù hợp, ghi nhận rồi **rethrow** nếu muốn giữ hành vi lỗi của worker, hoặc tạo kết quả lỗi có cấu trúc.
- Một `ThreadPoolExecutor` custom có thể dùng `afterExecute` để thống kê lỗi tập trung, miễn hook không block và kiểm soát cancellation.
- Uncaught handler là lớp bảo vệ cuối cho các lỗi **thật sự thoát khỏi thread**, chứ không thay thế observability của Future.

Nếu bắt `Throwable` trong task wrapper, hãy hết sức thận trọng với `Error`; thường không nên âm thầm nuốt các lỗi nghiêm trọng. Logging phải an toàn, side effect chỉ được chạy một lần khi retry được thiết kế rõ.

## 14. Chọn ThreadPoolExecutor hay Executors factory method?

### 14.1. Executors.newFixedThreadPool

`Executors.newFixedThreadPool(n, factory)` tiện khi cần số worker cố định và đặt tên/handler chung. Nhưng factory method này dùng một hàng đợi có khả năng tăng không giới hạn theo thiết kế chuẩn; nếu producer gửi task nhanh hơn khả năng xử lý lâu dài, queue có thể lớn và gây áp lực bộ nhớ.

Khi cần **bounded queue**, rejection/backpressure và giám sát rõ, có thể tạo `ThreadPoolExecutor` trực tiếp với capacity, handler từ chối và lifecycle phù hợp.

### 14.2. Ví dụ cấu hình có giới hạn

~~~java
// Mẫu cấu hình, không phải chương trình độc lập.
// factory đã được tạo theo chính sách đặt tên/handler.
ThreadPoolExecutor pool = new ThreadPoolExecutor(
    2, 4,
    30, TimeUnit.SECONDS,
    new ArrayBlockingQueue<>(100),
    factory,
    new ThreadPoolExecutor.AbortPolicy()
);
~~~

Mẫu này cần import `ThreadPoolExecutor`, `ArrayBlockingQueue` và `TimeUnit`. `AbortPolicy` ném `RejectedExecutionException` khi executor không thể nhận task theo chính sách; exception này có thể xảy ra **trong thread gọi execute/submit**, không phải uncaught failure của worker.

Đừng dựa vào `UncaughtExceptionHandler` để bắt task bị reject, vì task có thể **chưa được worker thực thi**. Caller phải xử lý `RejectedExecutionException`, retry/backpressure hoặc trả lỗi upstream.

### 14.3. Không lẫn trách nhiệm

| Thành phần | Trách nhiệm chính |
| --- | --- |
| `ThreadFactory` | Tạo worker thread với thuộc tính phù hợp |
| `RejectedExecutionHandler` | Quyết định cách xử lý task khi executor không thể nhận |
| `UncaughtExceptionHandler` | Nhận throwable thực sự không được bắt ở boundary của thread |
| `Future.get()` | Lấy kết quả/exception của task được biểu diễn bằng Future |
| `ThreadPoolExecutor.beforeExecute/afterExecute` | Hook trước/sau execution để đo/quan sát theo contract |
| `ExecutorService.shutdown/awaitTermination` | Quản lý lifecycle pool |
| Business retry policy | Quyết định task nào được thử lại, backoff, idempotency, deadline |

Càng tách rõ trách nhiệm, càng dễ tránh lỗi “đã có handler mà sao Future thất bại không ai biết”.

## 15. Các lỗi phổ biến cần tránh

**Lỗi 1 — Nghĩ `ThreadFactory` được gọi cho từng `submit`.** Worker có thể được tái sử dụng. Muốn context theo task, phải bọc task hoặc truyền dữ liệu trong task.

**Lỗi 2 — Factory gọi `thread.start()` trước khi trả.** Executor sở hữu thời điểm khởi động; trả thread chưa start.

**Lỗi 3 — Chỉ gắn `UncaughtExceptionHandler` rồi coi đã bắt mọi task exception.** `submit` thường lưu lỗi trong `Future`; người sở hữu Future phải quan sát.

**Lỗi 4 — Gửi `FutureTask` qua `execute` rồi chờ handler.** `FutureTask.run()` tự bắt throwable, do đó lỗi có thể không thoát ra worker.

**Lỗi 5 — Không bao giờ gọi `Future.get()` trên task quan trọng.** Lỗi bị lưu nhưng không ai nhìn; cần protocol kết quả hoặc giám sát tập trung.

**Lỗi 6 — `afterExecute` chỉ kiểm tra `Throwable error != null`.** Với `submit`, tham số đó có thể null ngay cả khi task thất bại. Phải unwrap Future khi phù hợp.

**Lỗi 7 — Gọi `get()` tùy tiện trong hook trên Future chưa done.** Có thể block worker/đặt ra dependency vô hạn; chỉ unwrap task hoàn tất thuộc executor và có guard thích hợp.

**Lỗi 8 — Ném exception từ handler hoặc hook rồi coi như đã xử lý lỗi.** Reporting code nên an toàn và không gây failure thứ cấp.

**Lỗi 9 — Cứ handler được gọi thì executor tự retry task.** Worker có thể được thay thế, nhưng task lỗi không tự được làm lại.

**Lỗi 10 — Dùng daemon workers để chữa việc quên shutdown.** JVM có thể thoát trước khi task quan trọng hoàn tất. Quản lý lifecycle đúng cách thay vì trông chờ daemon.

**Lỗi 11 — Không reset ThreadLocal/MDC giữa các task.** Worker tồn tại lâu hơn một task; dữ liệu request trước có thể rò sang task sau.

**Lỗi 12 — Xem `cancel(true)` là đã cleanup xong.** Tín hiệu hủy khác hoàn tất thực thi và side effect; cần xác nhận riêng.

**Lỗi 13 — Dùng một ThreadFactory cho nhiều executor với tên không phân biệt.** Thread dump khó đọc; nên có prefix theo pool và số ID.

**Lỗi 14 — Bỏ qua rejection ở caller.** Task bị từ chối chưa chắc chạy trên worker; handler uncaught của worker không xử lý chuyện này.

**Lỗi 15 — Chạy I/O lâu trong handler.** Thread đang xử lý lỗi có thể bị giữ quá lâu, làm chậm thay thế worker hoặc che giấu sự cố; nên report tối giản và có fallback.

## 16. Checklist review và bài tập

### Checklist triển khai

- `ThreadFactory.newThread` có luôn trả **Thread mới, chưa start** theo contract?
- Tên worker có prefix dễ nhận biết pool và ID tăng ổn định?
- Daemon/priority/context class loader có được quyết định chủ ý, không chỉ sao chép cấu hình tùy tiện?
- Handler có ghi nhận throwable đủ thông tin và tránh ném lỗi phụ, deadlock hoặc I/O dài?
- Task gửi qua `execute` và `submit` có **kênh nhận exception** khác nhau được tài liệu hóa?
- Caller có trách nhiệm quan sát từng Future quan trọng không?
- Nếu dùng `afterExecute`, có xử lý `Future.get()`/`ExecutionException`/`CancellationException`/interrupt đúng không?
- Có tránh block trên Future khác chưa hoàn tất trong hook?
- Có tách trạng thái task thất bại, bị hủy, bị reject và pool shutdown?
- Có hiểu rằng worker replacement **không** tự retry task thất bại?
- Có tránh rò rỉ `ThreadLocal` của task cũ qua task mới không?
- Có đo queue length, thời gian xử lý, số lỗi và latency, đồng thời quản lý pool shutdown?
- Có tránh gắn default handler toàn JVM ngoài phạm vi ownership?
- Có test exception reporting bằng latch/Future thay vì ngủ đoán scheduling?

### Câu hỏi 1

**Tại sao `ExecutorService.submit(...)` có thể thất bại mà `UncaughtExceptionHandler` không được gọi?**

Vì với `ThreadPoolExecutor` chuẩn, submit thường đóng gói task trong `FutureTask`. Wrapper đó bắt throwable và lưu vào Future; throwable không thoát khỏi worker như một uncaught exception. Caller cần gọi `get()` hoặc dùng kênh quan sát khác.

### Câu hỏi 2

**Nếu truyền `FutureTask` vào `execute(...)` thay vì gọi `submit(...)` thì handler chắc chắn thấy lỗi không?**

Không. `FutureTask.run()` vẫn giữ exception nội bộ; tên method `execute` không thay đổi hành vi wrapper.

### Câu hỏi 3

**Factory có nên start thread ngay để giảm độ trễ không?**

Không. `ThreadFactory.newThread` tạo và trả thread chưa start; executor quản lý `start()`. Start sớm có thể phá lifecycle và tính đúng đắn.

### Câu hỏi 4

**Khi `execute(plainRunnable)` ném exception, pool có tự chạy lại đúng task ấy không?**

Không. Worker có thể kết thúc và được thay thế, nhưng retry task là trách nhiệm riêng cần thiết kế điều kiện, giới hạn và idempotency.

### Câu hỏi 5

**`afterExecute(Runnable, Throwable)` nhận tham số Throwable là null có chứng minh submit task đã thành công không?**

Không. `FutureTask` có thể bắt exception nên tham số throwable null dù Future ở trạng thái lỗi. Có thể unwrap kết quả từ Future đã hoàn tất.

### Câu hỏi 6

**Tại sao đặt request ID vào tên thread trong factory không đủ để ghi nhận request hiện tại?**

Vì worker có thể thực thi nhiều task liên tiếp. Factory chỉ chạy lúc tạo worker, không chạy theo mỗi request. Metadata từng request cần được đặt/xóa theo scope task.

### Câu hỏi 7

**`Future.cancel(true)` hay `future.isCancelled()` có chứng minh worker đã release tài nguyên chưa?**

Không. Future cancellation state có thể thay đổi trước khi worker thực sự hoàn thành cleanup; dùng kênh xác nhận riêng khi cần.

### Câu hỏi 8

**Khi pool dùng queue có giới hạn và task bị reject, nơi nào nên xử lý?**

Chính thread gọi `execute/submit` và chính sách `RejectedExecutionHandler`. Task có thể chưa chạy trên worker, nên uncaught handler của worker không phải kênh nhận lỗi này.

**Tóm lại:** `ThreadFactory` xác định **worker được tạo như thế nào**, `UncaughtExceptionHandler` quan sát **throwable thật sự thoát khỏi thread**, còn `Future` và `afterExecute` giúp quan sát **kết quả hoặc lỗi của task** trong executor. Muốn vận hành đúng cần phân biệt worker lifecycle và task lifecycle, tránh nuốt lỗi submit, quản lý shutdown, cleanup và không coi handler là cơ chế retry hay phục hồi mọi exception.