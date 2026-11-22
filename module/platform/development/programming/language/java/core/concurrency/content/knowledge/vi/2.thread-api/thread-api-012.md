# Phân biệt công việc của thread và vòng đời task trong Java

> **Thông điệp chính:** **Thread** là luồng thực thi; **task** là một đơn vị công việc. Thread có vòng đời và trạng thái riêng của luồng thực thi. Task có tiến trình tiếp nhận, chạy, hoàn thành, thất bại hoặc hủy riêng. Hai vòng đời có thể liên quan nhưng không đồng nhất, đặc biệt khi dùng executor, thread pool và virtual thread.

Bài này chỉ xét **Java concurrency nói chung** với `Thread`, `Runnable`, `Callable` và `java.util.concurrent`; không bàn đến framework Spring hoặc vòng đời component do Spring quản lý.

## 1. Vì sao cần phân biệt?

Một thread giống **người thực hiện công việc**; một task giống **phiếu công việc**. Một người có thể làm nhiều phiếu lần lượt; phiếu chưa được nhận vẫn nằm trong hàng đợi; hoàn thành một phiếu không có nghĩa người đó rời khỏi hệ thống. Một phiếu bị hủy trước khi nhận không nhất thiết từng có ai thực thi nó.

| Khái niệm | Câu hỏi chính | Đại diện trong Java |
| --- | --- | --- |
| **Thread** | Mã đang chạy trên luồng nào? Luồng đã khởi động, đang chờ hay đã kết thúc? | `Thread`, `Thread.currentThread()`, `Thread.State` |
| **Task** | Công việc gì cần làm? Một lần xử lý đã bắt đầu, thành công, lỗi hoặc bị hủy chưa? | `Runnable`, `Callable<V>` |
| **Task handle** | Làm sao đợi và kiểm tra kết quả của một công việc bất đồng bộ? | `Future<V>`, `FutureTask<V>`, `CompletableFuture<V>` |
| **Executor** | Ai tiếp nhận, xếp hàng và bố trí thực thi các task? | `Executor`, `ExecutorService`, thread pool |

Không có quy tắc **mỗi task nhất thiết có một platform thread riêng**. Trong thread pool, một worker thread có thể chạy nhiều task nối tiếp. Một task nằm trong queue có thể chưa có thread nào bắt đầu thực thi. Một đối tượng `Runnable` có thể được dùng ở nhiều lần chạy, kể cả chạy đồng thời trên các thread khác nhau; vì vậy nếu task giữ trạng thái mutable chung phải đồng bộ đúng cách.

## 2. `Runnable` và `Callable` mô tả công việc

`Runnable` có phương thức `void run()`, không trả giá trị, không khai báo checked exception từ chữ ký `run()`:

~~~java
Runnable print = () -> System.out.println("Hello from task");
~~~

Dòng này chỉ tạo **mô tả công việc**. Nó chưa tạo thread và chưa thực thi `print.run()`. Gọi trực tiếp `print.run()` đồng nghĩa gọi phương thức bình thường trên **thread hiện tại**.

`Callable<V>` có phương thức `V call() throws Exception` nên thích hợp khi task có kết quả hoặc cần chuyển lỗi cho bên nhận:

~~~java
import java.util.concurrent.Callable;

Callable<Integer> calculate = () -> 6 * 7;
~~~

`Runnable` và `Callable` không tự quyết định thread nào chạy mình. Chúng có thể được thực thi bằng thread trực tiếp hoặc gửi tới một executor. Một lần gửi task thường là một **lần thực thi công việc**, không đồng nhất với identity của đối tượng lambda dùng làm task.

Ngược lại, đối tượng `Thread` biểu diễn một luồng thực thi:

~~~java
Runnable work = () -> System.out.println("working");
Thread worker = new Thread(work, "worker");
worker.start();
~~~

`new Thread(work)` tạo thread ở trạng thái `NEW`. `start()` yêu cầu JVM bắt đầu luồng thực thi riêng và sau đó thực thi `work.run()` trên luồng ấy. Một **đối tượng Thread chỉ được `start()` một lần**; start lần thứ hai ném `IllegalThreadStateException`. Muốn làm lại việc đó, tạo một `Thread` mới hoặc gửi một task mới đến executor phù hợp.

## 3. Ví dụ 1: `run()` trực tiếp khác `start()`

Tạo tệp `RunVsStart.java` (Java 17+):

~~~java
public class RunVsStart {
    public static void main(String[] args) throws InterruptedException {
        Thread mainThread = Thread.currentThread();
        Runnable work = () -> System.out.println(
                "on main = " + (Thread.currentThread() == mainThread));

        Thread worker = new Thread(work, "worker");

        System.out.println("initial = " + worker.getState());
        worker.run(); // Gọi trực tiếp trên main.
        System.out.println("after direct run = " + worker.getState());

        worker.start(); // Khởi động một thread mới.
        worker.join();  // Chờ worker kết thúc.
        System.out.println("after join = " + worker.getState());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac RunVsStart.java
java RunVsStart
~~~

Đầu ra:

~~~text
initial = NEW
on main = true
after direct run = NEW
on main = false
after join = TERMINATED
~~~

Vì `worker.run()` chỉ là lời gọi phương thức, body `work` lần đầu chạy ngay trong main và `worker` vẫn `NEW`. Chỉ `worker.start()` mới cho phép body chạy trên một thread khác. `join()` khiến main đợi thread mới kết thúc nên dòng cuối quan sát `TERMINATED`. Bài học: **một lần thực thi code trong `run()` không đồng nghĩa khởi động đối tượng `Thread`**.

Trong cách dùng `new Thread(runnable)` này, một vòng đời thread gắn với một lần gọi `run()` khi `start()`. Đó là quan hệ của cách tạo thread trực tiếp, **không phải quy tắc cho mọi task**.

## 4. Vòng đời của thread: sáu `Thread.State`

`Thread.getState()` trả về một trạng thái tại thời điểm đọc. Các trạng thái do Java định nghĩa:

| Trạng thái | Ý nghĩa |
| --- | --- |
| `NEW` | Chưa khởi động bằng `start()` |
| `RUNNABLE` | Đang thực thi trong JVM hoặc ở trạng thái có thể được lập lịch |
| `BLOCKED` | Chờ giành **monitor lock** để vào/re-enter khối `synchronized` |
| `WAITING` | Chờ vô thời hạn cho hành động từ thread khác, ví dụ `Object.wait()`, `join()` không timeout hoặc `LockSupport.park()` |
| `TIMED_WAITING` | Chờ với giới hạn thời gian, ví dụ `sleep`, `wait(timeout)`, `join(timeout)` |
| `TERMINATED` | Luồng đã kết thúc vì `run()` trả về hoặc thoát bởi lỗi không được bắt |

Sơ đồ đơn giản:

~~~text
NEW -- start() --> RUNNABLE <----> BLOCKED / WAITING / TIMED_WAITING
                         |
                         +-- run() kết thúc --> TERMINATED
~~~

Sơ đồ trên chỉ gợi nhớ; trạng thái chờ có thể chuyển qua lại nhiều lần và chi tiết phụ thuộc hoạt động của thread.

- `RUNNABLE` **không** chứng minh thread đang sử dụng CPU ngay lúc đó; nó có thể đang chờ được hệ điều hành lập lịch.
- `BLOCKED` là trạng thái **chờ monitor**, không phải tên chung cho mọi thao tác blocking như I/O hay queue.
- `WAITING` không mặc định là lỗi; worker trong pool có thể đang đợi task tiếp theo một cách hợp lệ.
- `getState()` chỉ là snapshot; kiểm tra state rồi hành động dựa trên giả định state không đổi là lỗi race condition.
- `TERMINATED` thuộc về **thread cụ thể ấy**. Task hoàn tất trong pool không đòi hỏi thread pool worker phải kết thúc.

Không dùng `Thread.sleep()` hoặc vòng lặp polling `getState()` làm công cụ điều phối thứ tự hai tác vụ. Sử dụng các primitive có hợp đồng đồng bộ như `join`, `Future.get`, `CountDownLatch`, `BlockingQueue` hoặc lock/condition khi cần thiết.

## 5. Vòng đời task: mô hình công việc, không phải `Thread.State`

Task có thể trải qua các giai đoạn logic:

~~~text
CREATED -> SUBMITTED -> QUEUED -> RUNNING -> SUCCEEDED
                            |         \----> FAILED
                            +---------------> CANCELLED
                                      \-----> CANCELLED (yêu cầu hủy lúc chạy)
~~~

Đây là **mô hình khái niệm**, không phải enum bắt buộc có sẵn trên mọi `Runnable`/`Callable`. Task chưa được gửi thì chưa có executor nào nhận; task có thể bị `RejectedExecutionException` khi executor không nhận công việc; một số task được thực thi trực tiếp mà không xếp queue; hủy trong lúc chạy không đồng nghĩa body đã dừng ngay.

Bảng đối chiếu hai trục:

| Tình huống | Thread | Task |
| --- | --- | --- |
| Vừa `new Thread(work)` | `NEW` | `work` chưa chạy trên thread ấy |
| Task nằm trong pool queue | Worker đang chạy task khác hoặc đợi việc | Task này **chưa bắt đầu** |
| Task đang gọi I/O hoặc đợi lock | Thread có thể `RUNNABLE`/`WAITING`/`BLOCKED`... tùy API | Task **đang thực thi**, nhưng chưa xong |
| Task vừa kết thúc trong thread pool | Worker có thể vẫn sống để nhận task khác | Task **completed** |
| Task ném exception trong `submit(Callable)` | Worker có thể tiếp tục phục vụ công việc | Future của task **done do failure** |
| Task hủy trước khi bắt đầu | Không có worker nào cần chạy body | Future có thể **done do cancellation** |

Một task đang đợi trong **executor queue** không có `Thread.State.WAITING` riêng, vì task chưa phải là thread. Cũng không thể nhìn worker ở `WAITING` rồi kết luận task nào đã hoàn thành. Cần theo dõi kết quả của task trực tiếp.

## 6. Executor tách nơi gửi công việc khỏi nơi chạy

`ExecutorService` có thể nhận `Runnable` hoặc `Callable`:

~~~java
// Minh họa API, chưa phải chương trình độc lập.
ExecutorService executor = Executors.newFixedThreadPool(2);
Future<Integer> answer = executor.submit(() -> 42);
int value = answer.get();
executor.shutdown();
~~~

Với thread pool hai worker, nhiều task có thể cùng xếp hàng; executor chủ động bố trí công việc lên worker có sẵn. Không đồng nghĩa có một thread riêng cho mỗi lần `submit`. `Future<Integer>` theo dõi kết quả **task**, không theo dõi trạng thái sống/chết của một worker.

`execute(Runnable)` gửi công việc mà không trả `Future`. `submit(...)` trả một `Future`; điều này hữu ích để đợi kết quả, phát hiện lỗi, hoặc yêu cầu hủy. Nếu `submit(Runnable)` mà không cung cấp result riêng, `Future.get()` sẽ trả `null` nếu thành công.

### Ví dụ 2: hai task, một worker vẫn sống sau khi task hoàn thành

Tạo `TwoTasksOneWorker.java` (Java 17+):

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class TwoTasksOneWorker {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Future<Thread> first =
                    executor.submit(() -> Thread.currentThread());
            Future<Thread> second =
                    executor.submit(() -> Thread.currentThread());

            Thread firstWorker = first.get();
            Thread secondWorker = second.get();

            System.out.println("same worker = "
                    + (firstWorker == secondWorker));
            System.out.println("first done = " + first.isDone());
            System.out.println("second done = " + second.isDone());
            System.out.println("worker alive = " + secondWorker.isAlive());
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Chạy:

~~~bash
javac TwoTasksOneWorker.java
java TwoTasksOneWorker
~~~

Đầu ra trong điều kiện worker hoạt động bình thường của ví dụ:

~~~text
same worker = true
first done = true
second done = true
worker alive = true
~~~

Hai task được xử lý tuần tự trên cùng một worker của `newSingleThreadExecutor()`. Các `get()` đã xác nhận **cả hai task xong**, trong khi worker vẫn còn sống do `shutdown()` chỉ được gọi về sau trong `finally`. Nếu worker gặp lỗi hỏng bất thường, executor có thể tạo worker thay thế; ví dụ này không phải bảo đảm identity worker vĩnh viễn.

Đây là khác biệt thực dụng: một worker thread có thể sống lâu hơn rất nhiều lần thực thi task mà nó nhận.

### Ví dụ 3: task chưa chạy vì đang xếp hàng

Tạo `QueuedTask.java` (Java 17+):

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class QueuedTask {
    public static void main(String[] args) throws Exception {
        CountDownLatch gate = new CountDownLatch(1);
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            Future<String> first = executor.submit(() -> {
                gate.await();
                return "first finished";
            });
            Future<String> second =
                    executor.submit(() -> "second finished");

            System.out.println("second done before release = "
                    + second.isDone());

            gate.countDown();
            System.out.println(first.get());
            System.out.println(second.get());
        } finally {
            gate.countDown();
            executor.shutdown();
        }
    }
}
~~~

Chạy:

~~~bash
javac QueuedTask.java
java QueuedTask
~~~

Đầu ra:

~~~text
second done before release = false
first finished
second finished
~~~

Trong executor một worker, task thứ nhất phải đợi `gate` nên task thứ hai không thể được worker thực thi trước khi main phát tín hiệu. `second.isDone()` chắc chắn là `false` ở phép kiểm tra đầu tiên. Không có thread khác đang chạy body của task thứ hai lúc ấy. Sau `countDown()`, hai `Future.get()` đợi lần lượt và lấy kết quả.

`CountDownLatch` ở đây cho quan hệ điều phối rõ ràng; dùng `Thread.sleep` để tạo một timing tình cờ sẽ khiến ví dụ phụ thuộc máy/tải.

## 7. `Future` theo dõi hoàn thành task ra sao?

`Future<V>` mô tả kết quả của một phép tính bất đồng bộ. Trong Java 17:

| API | Ý nghĩa chính |
| --- | --- |
| `get()` | Đợi nếu cần, rồi trả result; hoặc ném `ExecutionException`/`CancellationException`, hay `InterruptedException` nếu bên đợi bị ngắt |
| `get(timeout, unit)` | Đợi tối đa một khoảng; có thể ném `TimeoutException`, **không tự hủy task** |
| `isDone()` | `true` khi phép tính đã thành công, lỗi **hoặc bị hủy** |
| `isCancelled()` | `true` khi task handle đã bị hủy trước khi hoàn tất |
| `cancel(false)` | Yêu cầu hủy, không yêu cầu interrupt công việc đang chạy |
| `cancel(true)` | Yêu cầu hủy và thử interrupt thread đang thực thi nếu có thể |

**`isDone() == true` không có nghĩa “đã thành công”**. Một task có exception vẫn done. Một task bị hủy trước khi bắt đầu cũng done. Với `get()`, caller phân biệt kết quả thường, `ExecutionException` có cause từ task, và `CancellationException`.

Từ Java 19, `Future` có API bổ sung như `state()` với các trạng thái `RUNNING`, `SUCCESS`, `FAILED`, `CANCELLED`. Trong ngữ cảnh `Future.State`, `RUNNING` có thể bao gồm phép tính **chưa hoàn tất nhưng vẫn đang xếp hàng**; đừng đọc tên trạng thái đó thành “hiện đang chiếm CPU”. Ví dụ Java 17 nên dùng `get/isDone/isCancelled` nếu muốn chạy với baseline Java 17.

### Ví dụ 4: task thất bại, Future vẫn done

Tạo `TaskFailure.java`:

~~~java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class TaskFailure {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Future<Integer> future = executor.submit(() -> {
                throw new IllegalStateException("failed");
            });

            try {
                future.get();
            } catch (ExecutionException ex) {
                System.out.println("cause = "
                        + ex.getCause().getClass().getSimpleName());
            }

            System.out.println("done = " + future.isDone());
            System.out.println("cancelled = " + future.isCancelled());
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Chạy `javac TaskFailure.java` và `java TaskFailure`:

~~~text
cause = IllegalStateException
done = true
cancelled = false
~~~

`Future.get()` cho biết task bị lỗi và cung cấp nguyên nhân. Khi chạy `Runnable` bằng `Thread` tạo trực tiếp, `Thread.join()` **chỉ đợi thread kết thúc**, không tự trả giá trị hay ném lại exception từ thread khác. Nếu cần theo dõi uncaught exception của raw thread, dùng `Thread.UncaughtExceptionHandler` hoặc thiết kế kênh thông báo lỗi phù hợp. `submit(Callable)` thường tiện hơn cho tác vụ cần result/failure.

### Ví dụ 5: hủy một task chưa từng chạy

Tạo `CancelBeforeRun.java`:

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.FutureTask;

public class CancelBeforeRun {
    public static void main(String[] args) throws Exception {
        FutureTask<Integer> task = new FutureTask<>(() -> 42);

        System.out.println("cancel accepted = " + task.cancel(false));
        System.out.println("done = " + task.isDone());
        System.out.println("cancelled = " + task.isCancelled());

        try {
            task.get();
        } catch (CancellationException expected) {
            System.out.println("result unavailable");
        }
    }
}
~~~

Chạy `javac CancelBeforeRun.java` và `java CancelBeforeRun`:

~~~text
cancel accepted = true
done = true
cancelled = true
result unavailable
~~~

Trong ví dụ không hề có thread thực thi body `() -> 42`. `FutureTask.cancel(false)` thành công vẫn khiến task handle `isDone()` trả `true`. Một phép tính được đánh dấu hoàn tất vì **hủy**, khác xa “thread hoàn tất phần việc”.

## 8. Hủy task là hợp tác; không đồng nghĩa kết thúc thread

Nếu task đã bắt đầu, `future.cancel(true)` có thể thử interrupt thread đang thực thi. Cần nhớ:

1. `cancel(true)` báo một **yêu cầu**, không bảo đảm buộc code dừng ngay.
2. Task có thể bỏ qua cờ interrupt, đang xử lý I/O không phản hồi interrupt, hoặc chủ động hoàn tất theo cách riêng.
3. `Future` có thể đã báo canceled/done **trước khi body task thực sự thoát**.
4. Thread trong pool **không nên bị hiểu là tài sản của một task**; sau task kết thúc, worker có thể phục vụ task tiếp theo.
5. Tránh `Thread.stop()`: đây là API cũ nguy hiểm. Tác vụ dài cần cơ chế hủy hợp tác và giải phóng tài nguyên trong `finally`.

Ví dụ xử lý interruption cho một task có thể chờ:

~~~java
// Chỉ minh họa body task; không phải chương trình độc lập.
try {
    while (!Thread.currentThread().isInterrupted()) {
        doOneUnitOfWork();
    }
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    // Trả quyền quyết định cho tầng bên ngoài và thoát tác vụ.
} finally {
    releaseOwnedResources();
}
~~~

Trong code thực tế, tên các hàm `doOneUnitOfWork` và `releaseOwnedResources` phải được triển khai; đoạn trên minh họa **ngữ nghĩa interruption**. Nếu body dùng phương thức ném `InterruptedException` thì có thể thoát, xử lý dọn dẹp hoặc khôi phục cờ interrupt tùy hợp đồng. Không nuốt ngắt rồi tiếp tục vòng lặp vô hạn ngoài ý muốn.

## 9. `Thread.join()`, `Future.get()`, `awaitTermination()` khác nhau

| API | Đối tượng được chờ | Kết quả và lỗi |
| --- | --- | --- |
| `Thread.join()` | **Một thread** kết thúc | Không trả giá trị task; không chuyển exception trong thread sang caller |
| `Future.get()` | **Một phép tính** kết thúc/có kết quả | Có result hoặc lỗi/hủy tương ứng |
| `ExecutorService.awaitTermination(...)` | **Executor** dừng sau shutdown | Boolean về việc executor đã kết thúc trong thời hạn hay chưa |

`join()` và `Future.get()` đều có hợp đồng memory visibility: các hành động của thread kết thúc xảy ra trước các hành động sau `join()` thành công; hành động của phép tính bất đồng bộ xảy ra trước hành động theo sau `Future.get()` tương ứng ở thread khác. Vì vậy việc nhận kết quả sau các cơ chế này an toàn hơn việc polling thread state hoặc chờ một thời gian đoán trước.

`CompletableFuture.join()` cũng có tên `join` nhưng **không phải** `Thread.join()`: nó chờ và lấy kết quả của một completion stage, với ngữ nghĩa exception riêng. Phải xác định đúng đối tượng trước khi nói “join là đợi luồng”.

## 10. Vòng đời executor là trục thứ ba

Bên cạnh thread và task, executor còn có trạng thái hoạt động riêng:

- `shutdown()` bắt đầu đóng theo cách trật tự; không nhận task mới, nhưng tiếp tục xử lý task đã được nhận và **trả về ngay** (không tự chờ hoàn tất).
- `awaitTermination(timeout, unit)` đợi executor kết thúc sau khi có yêu cầu đóng; trả boolean, không cung cấp kết quả của từng task.
- `shutdownNow()` cố dừng task đang chạy bằng interruption và trả các task trong queue chưa bắt đầu. Đây là **best effort**: task có thể không phản hồi ngắt ngay.
- `isShutdown()` nói đã yêu cầu đóng, còn `isTerminated()` nói executor đã kết thúc sau shutdown. Một `Future` hoàn thành không tự làm executor chuyển sang terminated.

Mẫu đóng executor Java 17:

~~~java
// Minh họa với biến executor đã được tạo trước đó.
executor.shutdown();
try {
    if (!executor.awaitTermination(5, java.util.concurrent.TimeUnit.SECONDS)) {
        executor.shutdownNow();
    }
} catch (InterruptedException ex) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
}
~~~

Timeout 5 giây là thời gian chờ của caller, **không bảo đảm** mọi task dừng trong 5 giây. Thiết kế production cần xem xét timeout, backpressure, queue capacity, số worker, failure reporting và shutdown policy riêng.

## 11. Virtual thread trong Java 21+ làm rõ thêm sự khác biệt

Virtual thread vẫn là đối tượng `Thread` nhưng được JVM lập lịch trên carrier platform thread, không tương đương một OS thread mới cho từng task. Java 21 có executor tạo **một virtual thread cho mỗi task**:

~~~java
// VirtualPerTask.java — chỉ dành cho Java 21+
import java.util.concurrent.Executors;

public class VirtualPerTask {
    public static void main(String[] args) throws Exception {
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            var future = executor.submit(
                    () -> Thread.currentThread().isVirtual());
            System.out.println(future.get());
        }
    }
}
~~~

Chạy:

~~~bash
javac VirtualPerTask.java
java VirtualPerTask
~~~

Kết quả:

~~~text
true
~~~

Ở đây mỗi task được gán một **virtual thread mới**; các carrier platform thread có thể được runtime tái sử dụng. Virtual thread không xóa bỏ khái niệm task lifecycle và `Future`: task vẫn có thể hoàn thành, lỗi hay bị hủy; thread vẫn có identity và trạng thái riêng. `ExecutorService.close()`/try-with-resources cần JDK 19+; ví dụ đã ghi rõ Java 21, **không áp dụng cú pháp này cho Java 17**.

Điểm khác nhau giữa “mỗi task một virtual thread” và “mỗi task một platform thread” là cực kỳ quan trọng khi xét tài nguyên, lập lịch và khả năng mở rộng.

## 12. Chọn API theo câu hỏi cần trả lời

| Câu hỏi | Công cụ phù hợp | Sai lầm cần tránh |
| --- | --- | --- |
| Công việc có logic gì? | `Runnable`/`Callable` | Trộn logic công việc với thread identity |
| Muốn khởi động một raw thread? | `new Thread(work).start()` | Gọi `run()` rồi tưởng có concurrency |
| Task đã thành công hay thất bại? | `Future.get()`/completion-specific API | Chỉ nhìn `isDone()` hay `Thread.State` |
| Task nào đang chờ trong queue? | Executor/queue metrics, task ID | Đọc `Thread.State.WAITING` rồi gán cho task |
| Hai việc phải có thứ tự? | `join`, `Future.get`, `CountDownLatch`, `BlockingQueue` | `sleep()`, priority, suy đoán scheduling |
| Cần yêu cầu dừng task? | `cancel(...)`, `interrupt()`, logic dừng hợp tác | Cho rằng cancel cưỡng bức đã kết thúc code |
| Muốn executor nhận thêm công việc? | Kiểm tra shutdown policy, handle rejection | Nhìn một worker còn `RUNNABLE` |
| Cần đợi executor dừng? | `shutdown` + `awaitTermination` | Chỉ đợi một task Future |
| Muốn debug thread đang chờ gì? | Thread dump, stack, `Thread.getState()` | Đồng nhất thread state với business task state |

### Ba tình huống để tự phân tích

**Tình huống A:** Một pool có 4 worker và 1000 task đã được nhận. Có 1000 thread không? **Không.** Nhiều task có thể đang queue, chỉ một số được worker thực thi. Tùy chính sách executor, các task có thể còn chờ lâu.

**Tình huống B:** `Future.isDone() == true`, nhưng task bị hủy trước khi chạy. Có nhất thiết thread nào đã thực thi body task không? **Không.** Cờ done phản ánh trạng thái task handle, gồm cả cancellation.

**Tình huống C:** Một worker đang `WAITING`, còn `Future` của task trước đó đã thành công. Mâu thuẫn không? **Không.** Worker có thể chờ việc tiếp theo sau khi task trước hoàn tất.

## 13. Lỗi hiểu thường gặp

1. **“Task tạo rồi nghĩa là đang chạy.”** Sai: tạo object công việc khác với gửi, được nhận, được xếp lịch và thực thi.
2. **“`run()` và `start()` tương đương.”** Sai: gọi `run()` trực tiếp không tạo thread mới.
3. **“Một task hoàn thành thì thread của nó bị hủy.”** Sai với thread pool: worker thường được tái sử dụng.
4. **“`Thread.State.TERMINATED` cho biết Future thành công.”** Không: thread kết thúc không chuyển trạng thái thành công của một task tương ứng, đặc biệt nếu nhiều task được quản lý.
5. **“`isDone()` có nghĩa result thành công.”** Không: lỗi và hủy cũng done.
6. **“`cancel(true)` bảo đảm kill task ngay.”** Không: đây là nỗ lực phối hợp bằng interruption.
7. **“`Future.get(timeout)` tự hủy công việc khi timeout.”** Không: nó chỉ ngừng chờ và ném `TimeoutException`.
8. **“`shutdown()` xong là mọi worker/task đã dừng.”** Không: shutdown khởi phát đóng, còn termination là giai đoạn sau.
9. **“RUNNABLE chắc chắn đang dùng CPU.”** Không: trạng thái JVM không chứng minh lịch OS cấp CPU ở khoảnh khắc quan sát.
10. **“Virtual-thread-per-task nghĩa là một OS thread cho từng task.”** Không: virtual thread được JVM lập lịch trên các carrier thread.

## Nguồn API chính thức

- [Java SE 21 — `Thread`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html), [`Thread.State`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.State.html).
- [Java SE 21 — `Runnable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Runnable.html), [`Callable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Callable.html).
- [Java SE 21 — `Future`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html), [`FutureTask`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/FutureTask.html).
- [Java SE 21 — `ExecutorService`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html), [`Executors`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html).
- [Java Language Specification `17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html): nền tảng đồng bộ và *happens-before*.

**Ghi nhớ:** Khi hỏi **ai đang chạy/đang đợi**, quan sát thread. Khi hỏi **công việc đã xử lý đến đâu, thành công hay thất bại**, quan sát task và kết quả của nó. Khi hỏi **hệ thống có nhận/điều phối việc tiếp không**, quan sát executor.