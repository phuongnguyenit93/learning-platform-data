# FutureTask trong Java: một Runnable có thể được theo dõi bằng Future

## 1. Vấn đề cần giải quyết

Giả sử bạn có một `Runnable` mô tả công việc chạy nền. Bạn có thể truyền nó cho `Thread` hoặc `Executor.execute()`, nhưng một `Runnable` đơn thuần không có sẵn API để hỏi **“xong chưa?”**, đợi hoàn tất, lấy lỗi thực thi hoặc yêu cầu hủy. Trong khi đó, `Future<V>` biểu diễn **kết quả và trạng thái của một phép tính bất đồng bộ** nhưng bản thân interface `Future` không bắt buộc là một tác vụ có thể đưa trực tiếp vào `Thread`.

`java.util.concurrent.FutureTask<V>` nối hai nhu cầu đó:

~~~text
                 Runnable                 Future<V>
                    |                         |
              void run()                get(), cancel(),
                    |                   isDone(), isCancelled()
                    |                         |
                    +---------+---------------+
                              |
                      RunnableFuture<V>
                              |
                         FutureTask<V>
                              |
                Có thể truyền vào Thread,
                Executor.execute() hoặc gọi run()
                và vẫn giữ một handle Future<V>.
~~~

Bài này thuộc mục **Future & Scheduling** trong **Java Advance - concurrency**. Phạm vi tập trung vào cơ chế chuẩn **Java SE 17+**, không có nội dung riêng của Spring vì Spring đã có chương riêng.

Sau bài, bạn có thể:
- Giải thích `FutureTask<V>` triển khai `RunnableFuture<V>`, vừa có `run()` vừa có `get()/cancel()/isDone()`.
- Tạo FutureTask từ **`Callable<V>`** hoặc từ **`Runnable` + giá trị kết quả `V`**.
- Chạy cùng đối tượng FutureTask bằng `new Thread(task).start()` hoặc `executor.execute(task)`, rồi giữ **chính đối tượng đó** làm Future handle.
- Phân biệt giá trị trả về của `FutureTask(Runnable, result)` và giá trị trả về từ `Callable<V>.call()`.
- Hiểu `FutureTask` là **one-shot computation**: nhiều lời gọi `run()` không làm task tự chạy lại từ đầu.
- Đọc đúng `isDone`, `isCancelled`, `get`, `get(timeout)`, `ExecutionException` và `CancellationException`.
- Hiểu `cancel(true)` chỉ yêu cầu interrupt, không cưỡng bức dừng worker hay rollback side effect.
- Tránh các lỗi ownership, bọc FutureTask hai lần qua `submit`, chờ `get` vô hạn, race giữa cancellation và completion.
- Biết `done()`, `runAndReset()` có vai trò gì ở mức mở rộng và vì sao FutureTask **không tự là một scheduler**.

## 2. Nắm chắc bốn interface/lớp liên quan

### 2.1. Runnable — mô tả hành động

~~~java
Runnable work = () -> {
    System.out.println("processing");
};
~~~

`Runnable.run()` trả về `void`. Một `Runnable` thường chỉ mô tả mã để thực thi; nó không có `get()`, không định nghĩa kết quả trả về và không cung cấp trạng thái completion để caller theo dõi. Nếu đưa trực tiếp vào `Thread`, có thể đợi bằng `Thread.join()`, nhưng `join` không tự trả kết quả, không gói exception của `run` thành `ExecutionException` và không phải Future API.

**`Runnable` không bắt buộc chạy trên thread khác.** Gọi `work.run()` là gọi method bình thường trên **thread hiện tại**. Chỉ khi dùng `new Thread(work).start()` hoặc executor thích hợp thì việc chạy mới được lập lịch ở execution context khác.

### 2.2. Callable<V> — mô tả phép tính trả kết quả

~~~java
Callable<Integer> calculation = () -> 6 * 7;
~~~

`Callable<V>.call()` trả một giá trị kiểu `V` và có thể khai báo `throws Exception`. Nhưng `Callable` **không tự triển khai `Runnable`**, nên không thể truyền trực tiếp như một `Runnable` cho constructor `Thread(Runnable)`.

FutureTask có thể nhận `Callable<V>` và tạo một tác vụ vừa chạy được, vừa quan sát được:

~~~java
FutureTask<Integer> task = new FutureTask<>(calculation);
new Thread(task).start();
Integer result = task.get();
~~~

Ba dòng trên là đoạn minh họa trong một method có import thích hợp và xử lý/khai báo `InterruptedException`, `ExecutionException`.

### 2.3. Future<V> — hợp đồng quan sát kết quả

| Phương thức | Mục đích |
| --- | --- |
| `V get()` | Chờ và lấy kết quả; có thể bị interrupt hoặc nhận lỗi của computation |
| `V get(timeout, unit)` | Chờ có hạn; có thể ném `TimeoutException` |
| `boolean cancel(mayInterruptIfRunning)` | Yêu cầu hủy kết quả/computation |
| `boolean isDone()` | Đã hoàn tất, thất bại hoặc cancelled? |
| `boolean isCancelled()` | Future đã chuyển sang trạng thái cancelled? |

Một Future **không nhất thiết** là một Runnable. Không thể suy rằng mọi implementation của Future đều cho bạn `run()` để tự đưa vào Thread.

### 2.4. RunnableFuture<V> và FutureTask<V>

`RunnableFuture<V>` kế thừa **cả `Runnable` và `Future<V>`**. `FutureTask<V>` là implementation concrete phổ biến của interface này.

~~~java
public class FutureTask<V> implements RunnableFuture<V>
~~~

Dòng trên nhằm minh họa ý nghĩa khai báo kiểu, không phải một định nghĩa lại lớp JDK. Khi bạn có:

~~~java
FutureTask<Integer> task = new FutureTask<>(() -> 42);
~~~

thì cùng **một object `task`** đồng thời:
- Có thể chạy qua `task.run()`, `new Thread(task).start()` hoặc `executor.execute(task)`.
- Có thể theo dõi qua `task.isDone()`.
- Có thể lấy kết quả qua `task.get()`.
- Có thể yêu cầu hủy qua `task.cancel(true)`.

Đây là khác biệt chính giữa một Runnable thông thường và một FutureTask.

## 3. Hai constructor quan trọng

| Constructor | Đầu vào | Giá trị `get()` khi thành công | Dùng khi |
| --- | --- | --- | --- |
| `FutureTask(Callable<V> callable)` | Một phép tính trả `V` | Giá trị do `call()` trả | Tính toán tạo kết quả thật |
| `FutureTask(Runnable runnable, V result)` | Hành động `void` và giá trị `result` có sẵn | Giá trị `result` truyền lúc khởi tạo | Cần theo dõi completion của Runnable có sẵn |

### 3.1. Khi dùng Callable

~~~java
Callable<String> call = () -> "READY";
FutureTask<String> task = new FutureTask<>(call);
~~~

Sau khi task thực thi thành công, `get()` trả `"READY"`. Nếu `call()` ném exception, `get()` ném `ExecutionException` chứa lỗi gốc.

### 3.2. Khi dùng Runnable + result

~~~java
Runnable action = () -> saveLocalState();
FutureTask<String> task = new FutureTask<>(action, "SAVED");
~~~

Đây là snippet với `saveLocalState()` đã tồn tại. Khi `action.run()` **hoàn tất bình thường**, `task.get()` trả đúng giá trị `"SAVED"` do caller **cung cấp trước**. `Runnable` không tự sinh ra chuỗi này.

Nếu `run()` ném unchecked exception, FutureTask ghi nhận failure và `get()` ném `ExecutionException`, **không trả `"SAVED"`**. Nếu task bị cancel, `get()` ném `CancellationException`, bất kể `result` đã được truyền vào constructor.

**Có thể truyền `null` làm result** khi chỉ cần biết task thành công hay thất bại:

~~~java
FutureTask<Void> task = new FutureTask<>(runnable, null);
~~~

Sau khi hoàn tất bình thường, `get()` trả `null`. Để phân biệt “task thành công và trả null” với “chưa chạy”, **không dựa vào giá trị null**; dùng trạng thái Future và cách `get()` kết thúc.

## 4. Ví dụ Java 17 độc lập: Runnable được gắn Future

Tạo file **`RunnableFutureTaskDemo.java`**:

~~~java
import java.util.concurrent.FutureTask;
import java.util.concurrent.atomic.AtomicInteger;

public class RunnableFutureTaskDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger operations = new AtomicInteger();

        Runnable runnable = () -> operations.incrementAndGet();
        FutureTask<String> tracked =
                new FutureTask<>(runnable, "COMPLETED");

        System.out.println("doneBeforeStart=" + tracked.isDone());

        Thread worker = new Thread(tracked, "tracked-worker");
        worker.start();

        String result = tracked.get();
        worker.join();

        System.out.println("result=" + result);
        System.out.println("operations=" + operations.get());
        System.out.println("doneAfterGet=" + tracked.isDone());
        System.out.println("cancelled=" + tracked.isCancelled());
    }
}
~~~

Biên dịch/chạy bằng JDK 17+:

~~~bash
javac RunnableFutureTaskDemo.java
java RunnableFutureTaskDemo
~~~

Stdout:

~~~text
doneBeforeStart=false
result=COMPLETED
operations=1
doneAfterGet=true
cancelled=false
~~~

**Giải thích:**
1. `AtomicInteger operations` bắt đầu bằng 0. `Runnable` tăng biến này đúng một lần khi chạy.
2. Constructor `FutureTask<>(runnable, "COMPLETED")` dùng chuỗi làm **kết quả cố định nếu task thành công**.
3. Trước khi gọi `Thread.start()`, `isDone()==false`: tạo object FutureTask **không tự thực thi** tác vụ.
4. `worker.start()` đưa FutureTask vào một thread. `tracked.get()` chờ computation và trả `"COMPLETED"`.
5. `worker.join()` đợi worker rời run; main mới đọc `operations`. Không dự đoán thứ tự giữa `get` và việc thread thực sự kết thúc toàn bộ vòng đời, nên dùng `join` khi cần biết thread đã thoát.
6. `isDone()==true` và `isCancelled()==false` khi task hoàn tất bình thường.

**Lưu ý về output:** ví dụ không in thread name/timing vì scheduler quyết định lúc nào worker được cấp CPU. Những giá trị in là xác định khi không có interruption hay lỗi ngoài ý muốn.

**Lưu ý về runnable:** `() -> operations.incrementAndGet()` hợp lệ với functional interface trả `void` vì một lời gọi method có thể được dùng làm statement expression; kết quả số của `incrementAndGet()` bị bỏ qua ở phía `Runnable`. FutureTask trả chuỗi `"COMPLETED"` do constructor cung cấp.

## 5. Ví dụ Java 17: Callable và giá trị thực sự được tính

Tạo file **`CallableFutureTaskDemo.java`**:

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;

public class CallableFutureTaskDemo {
    public static void main(String[] args) throws Exception {
        Callable<Integer> calculation = () -> 6 * 7;
        FutureTask<Integer> task = new FutureTask<>(calculation);

        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            pool.execute(task);

            System.out.println("value=" + task.get());
            System.out.println("valueAgain=" + task.get());
            System.out.println("isDone=" + task.isDone());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(1, TimeUnit.MINUTES)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac CallableFutureTaskDemo.java
java CallableFutureTaskDemo
~~~

Stdout:

~~~text
value=42
valueAgain=42
isDone=true
~~~

Hai lần `get()` **không làm Callable chạy hai lần**. `FutureTask` ghi nhận kết quả của một lần thực thi; các lần `get()` sau completion đọc lại kết quả đã được công bố. Với một computation đã kết thúc, `get()` không cần chạy lại phép tính.

### Vì sao dùng execute(task), không cần submit(task)?

`ExecutorService.execute(Runnable)` nhận một Runnable và trả `void`. Vì `FutureTask` đã **là Runnable** và **là Future**, bạn có thể:

~~~java
FutureTask<Integer> task = new FutureTask<>(() -> 42);
pool.execute(task);
Integer value = task.get();
~~~

Đây là snippet có `pool`, import và xử lý exception phù hợp. Bạn vẫn giữ handle `task` dù `execute` không trả Future.

Đừng vô tình viết:

~~~java
FutureTask<Integer> inner = new FutureTask<>(() -> 42);
Future<?> outer = pool.submit(inner);
~~~

Vì `submit(Runnable)` thường **tạo một Future khác bao quanh Runnable được truyền vào**, nên lúc này có hai handle: `inner` do bạn tạo, `outer` do executor trả về. `outer.get()` theo overload Runnable có thể trả `null`, còn `inner.get()` trả 42. Hủy `outer` không tạo một bảo đảm trừu tượng rằng `inner` đã chuyển sang trạng thái cancelled hoặc mọi side effect bên trong dừng. Mẫu này làm ownership và cancellation khó suy luận.

**Chọn một trong hai lối rõ ràng:**
- Muốn executor tự quản lý Future: `Future<Integer> f = pool.submit(() -> 42);`.
- Muốn **tự sở hữu một FutureTask** và tùy biến trạng thái/hook: tạo `FutureTask<Integer> task` rồi `pool.execute(task)`, dùng trực tiếp `task.get()/cancel()`.

Không cần bọc một FutureTask trong FutureTask khác chỉ vì muốn có Future.

## 6. FutureTask là one-shot: run() nhiều lần không chạy lại tác vụ

Một câu hỏi quan trọng: FutureTask vừa có `run()`, vậy gọi `run()` lần thứ hai có tính lại không?

**Không.** Với `FutureTask.run()` thông thường, chỉ một lần thực thi của computation được chấp nhận. Sau khi task đã hoàn tất, những lần `run()` tiếp theo không chạy lại `Callable`/`Runnable`.

Tạo file **`FutureTaskOneShotDemo.java`**:

~~~java
import java.util.concurrent.FutureTask;
import java.util.concurrent.atomic.AtomicInteger;

public class FutureTaskOneShotDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger calls = new AtomicInteger();

        FutureTask<Integer> task = new FutureTask<>(() -> {
            return calls.incrementAndGet();
        });

        task.run(); // Thực thi đồng bộ trên main.
        task.run(); // Không thực thi lại.
        task.run(); // Vẫn không thực thi lại.

        System.out.println("result=" + task.get());
        System.out.println("calls=" + calls.get());
        System.out.println("done=" + task.isDone());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac FutureTaskOneShotDemo.java
java FutureTaskOneShotDemo
~~~

Stdout:

~~~text
result=1
calls=1
done=true
~~~

**Hai hiểu lầm cần tránh:**
1. `task.run()` không tạo thread mới. Trong ví dụ này task chạy **trên main thread** và hoàn thành trước khi dòng sau được thực thi.
2. `FutureTask` không phải lịch lặp. Nếu cần thực hiện phép tính nhiều lần như `1s/lần`, sử dụng `ScheduledExecutorService`/`ScheduledFuture` hoặc tạo **mỗi lần một FutureTask mới**, thay vì tái gọi `run()` của FutureTask đã hoàn tất.

Với nhiều thread cùng gọi `run()` trên một FutureTask **chưa hoàn tất**, cơ chế điều phối của FutureTask chỉ cho một runner thực thi body cho computation đó. Không dùng việc gọi run nhiều lần như cách “tăng tốc bằng nhiều worker”: những caller còn lại sẽ không nhận một phép tính riêng.

### So sánh với Runnable thông thường

~~~java
Runnable work = () -> System.out.println("run");
work.run();
work.run(); // In hai lần vì Runnable không tự ngăn thực thi lại.
~~~

Snippet trên chạy trong main sẽ in hai dòng `run`. `Runnable` là một contract mô tả body; `FutureTask` là một **computation có trạng thái hoàn tất** và bộ nhớ kết quả, nên semantics khác.

## 7. Trạng thái của FutureTask và giá trị get()

Bảng sau mô tả những tình huống caller quan sát:

| Sự kiện | `isDone()` | `isCancelled()` | `get()` |
| --- | --- | --- | --- |
| Chưa chạy / đang chạy | `false` (khi chưa có terminal outcome) | `false` | Chờ |
| Hoàn tất bình thường | `true` | `false` | Trả giá trị `V` |
| Callable/Runnable ném exception | `true` | `false` | Ném `ExecutionException` |
| Cancel thành công | `true` | `true` | Ném `CancellationException` |

**Không dùng `isDone()` để kết luận thành công.** Nó cũng đúng khi task lỗi hoặc bị hủy. Nếu muốn biết task chạy thành công và lấy dữ liệu, thường dùng `get()` rồi xử lý exception.

`isCancelled()==false` cũng **không** có nghĩa task chắc chắn thành công; task có thể chưa chạy, đang chạy hoặc kết thúc bằng exception.

### get() và memory visibility

Theo hợp đồng memory consistency của `Future`, những hành động xảy ra trong computation bất đồng bộ **happens-before** những hành động sau `Future.get()` tương ứng của thread khác. Điều này giúp caller nhìn thấy dữ liệu được công bố bởi computation sau khi `get()` hoàn tất theo contract.

Dù vậy:
- Không dùng `get()` như một transaction bảo vệ **mọi shared mutable object** đang bị các thread khác tiếp tục sửa.
- Nếu task trả về một `ArrayList` rồi thread khác còn mutate list, cần thêm ownership/synchronization.
- `Future.get()` không tự làm các thao tác nhiều bước trên database thành atomic.
- Nếu chỉ có `isDone()`, đừng tự thay thế phần reasoning memory consistency của `get()` mà không đọc contract cụ thể.

### Một số thứ không thể suy từ FutureTask

- `isDone()==true` sau `cancel(true)` **không chứng minh** Callable thực sự đã rời stack hoặc xong cleanup.
- `get(timeout)` ném `TimeoutException` **không tự hủy** FutureTask.
- `cancel(true)` không cưỡng bức mọi I/O hoặc CPU code dừng.
- Completion bình thường không có nghĩa một remote transaction bên ngoài chắc chắn được commit, nếu Callable không báo trạng thái business đầy đủ.

## 8. Ví dụ Java 17: timeout và execution exception

Khi cần giới hạn thời gian đợi, `get(timeout, unit)` có thể ném `TimeoutException`. Với lỗi trong Callable, `get()` ném `ExecutionException` và `getCause()` cho biết lỗi gốc.

Tạo file **`FutureTaskOutcomeDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class FutureTaskOutcomeDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        FutureTask<Integer> slow = new FutureTask<>(() -> {
            entered.countDown();
            release.await();
            return 7;
        });

        Thread worker = new Thread(slow, "slow-worker");
        worker.start();
        entered.await();

        try {
            slow.get(20, TimeUnit.MILLISECONDS);
        } catch (TimeoutException e) {
            System.out.println("timedGet=TimeoutException");
        }

        System.out.println("stillNotCancelled=" + !slow.isCancelled());
        release.countDown();

        System.out.println("resultAfterRelease=" + slow.get());
        worker.join();

        FutureTask<String> failed = new FutureTask<>(() -> {
            throw new IllegalArgumentException("bad input");
        });
        failed.run(); // Chạy trên main, FutureTask giữ exception.

        try {
            failed.get();
        } catch (ExecutionException e) {
            System.out.println("failureCause="
                    + e.getCause().getClass().getSimpleName());
        }

        System.out.println("failedIsDone=" + failed.isDone());
        System.out.println("failedIsCancelled=" + failed.isCancelled());
    }
}
~~~

Chạy:

~~~bash
javac FutureTaskOutcomeDemo.java
java FutureTaskOutcomeDemo
~~~

Stdout khi không có interruption ngoài ý muốn:

~~~text
timedGet=TimeoutException
stillNotCancelled=true
resultAfterRelease=7
failureCause=IllegalArgumentException
failedIsDone=true
failedIsCancelled=false
~~~

**Tại sao kết quả xác định?**
- `slow` báo đã vào Callable rồi chờ trên `release.await()`. Vì main chưa hạ latch, timed `get(20ms)` không thể lấy kết quả và ném `TimeoutException`.
- `get(timeout)` **không gọi `cancel`**, nên `slow.isCancelled()` vẫn false.
- Khi main hạ `release`, Callable trả 7; `slow.get()` sau đó nhận 7.
- FutureTask `failed` thực thi `Callable` ném `IllegalArgumentException`, nhưng `run()` của FutureTask **ghi nhận lỗi**, không ném nguyên lỗi lên main như khi gọi Callable trực tiếp.
- Lỗi được quan sát qua `failed.get()` dưới dạng `ExecutionException`; `getCause()` là `IllegalArgumentException`.
- `failed.isDone()==true` vì đã kết thúc bằng lỗi, còn `isCancelled()==false` vì không có yêu cầu cancel được chấp nhận.

**Đừng dùng timeout như bằng chứng task không có side effect**: nếu caller retry ngay sau `TimeoutException`, task cũ vẫn có thể chạy và thực hiện I/O. Cần idempotency hoặc cancellation policy nếu nghiệp vụ nhạy cảm.

## 9. cancel(false) và cancel(true) trên FutureTask

Constructor khiến FutureTask có một handle hủy, nhưng cancellation không phải kill không điều kiện.

~~~java
boolean accepted = task.cancel(true);
~~~

Ý nghĩa:
- Khi task chưa chạy, cancel thành công làm computation không được thực thi về sau.
- Khi task đang chạy, `FutureTask.cancel(true)` cố interrupt thread runner.
- `cancel(false)` có thể đánh dấu cancelled mà **không interrupt** runner; mã đang chạy có thể tiếp tục tới khi tự xong.
- Khi task đã completed bình thường hoặc lỗi, không thể “đổi ngược” terminal state bằng cancel.
- Khi cancellation thành công, `isCancelled()==true` và `get()` ném `CancellationException`.
- **`isDone()==true` khi cancelled không đồng nghĩa worker đã rời Callable**.

### Interruption mang tính hợp tác

`Thread.interrupt()` đặt cờ interrupt. Những API như `Thread.sleep()`, `Object.wait()`, `BlockingQueue.take()` và `CountDownLatch.await()` có thể ném `InterruptedException`; CPU loop tự tính không kiểm tra cờ có thể tiếp tục. Tùy I/O, việc interrupt có thể không khiến thao tác trả ngay.

Nếu bắt `InterruptedException` ở tầng không thể truyền tiếp, thường khôi phục trạng thái bằng `Thread.currentThread().interrupt()` **và thoát hoặc chuyển trạng thái theo chính sách hủy**. Chỉ khôi phục cờ rồi tiếp tục business logic vô điều kiện sẽ làm cancel không có hiệu lực.

### Một FutureTask bị hủy vẫn có thể chạy code

Nếu Callable bỏ qua interrupt hoặc đang trong cleanup, nó có thể còn làm việc sau khi Future đã cancelled. FutureTask không tự rollback file, database hay HTTP request đã thực hiện. Với side effect, ứng dụng cần thiết kế timeout ở đúng API, idempotency và cơ chế commit/compensation.

## 10. Ví dụ Java 17: yêu cầu hủy và quan sát worker thực sự thoát

Tạo file **`FutureTaskCancelDemo.java`**:

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.FutureTask;

public class FutureTaskCancelDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch exited = new CountDownLatch(1);

        FutureTask<String> task = new FutureTask<>(() -> {
            started.countDown();
            try {
                Thread.sleep(60_000);
                return "normal-result";
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return "stopped-by-interrupt";
            } finally {
                exited.countDown();
            }
        });

        Thread worker = new Thread(task, "cancel-worker");
        worker.start();
        started.await();

        boolean accepted = task.cancel(true);
        exited.await();
        worker.join();

        System.out.println("cancelAccepted=" + accepted);
        System.out.println("cancelled=" + task.isCancelled());
        System.out.println("done=" + task.isDone());
        System.out.println("workerExited=" + (exited.getCount() == 0));

        try {
            task.get();
        } catch (CancellationException e) {
            System.out.println("get=CancellationException");
        }
    }
}
~~~

Chạy:

~~~bash
javac FutureTaskCancelDemo.java
java FutureTaskCancelDemo
~~~

Stdout trên đường chạy bình thường:

~~~text
cancelAccepted=true
cancelled=true
done=true
workerExited=true
get=CancellationException
~~~

**Giải thích:**
1. `started.await()` đảm bảo body Callable đã bắt đầu; nó chưa thể hoàn thành bình thường trước `cancel` vì đang tiến tới hoặc chờ ở `sleep(60_000)`.
2. `task.cancel(true)` chấp nhận hủy, cố interrupt runner. Nếu interrupt đến **trước** lời gọi `sleep`, `sleep` cũng quan sát interrupt status và ném exception; nếu đến trong sleep, nó thức dậy bằng exception.
3. `finally` hạ latch `exited` và main dùng `worker.join()` để biết worker đã thật sự kết thúc.
4. Trạng thái kết quả của FutureTask vẫn **cancelled**, nên `get()` ném `CancellationException`, **không** trả chuỗi `"stopped-by-interrupt"` mà Callable tạo trong catch.

**Giới hạn:** demo đợi latch không thời hạn để thể hiện sự khác biệt giữa Future cancelled và worker exited. Với task thực tế có thể không hợp tác, **đặt deadline** cho việc chờ cleanup và đưa ra chính sách giám sát nếu worker không thoát.

### Cancel trước khi task được lên lịch

~~~java
FutureTask<String> task = new FutureTask<>(() -> "NEVER");
boolean accepted = task.cancel(false);
task.run(); // Không thực thi Callable vì task đã cancelled.
~~~

Đây là snippet. Với FutureTask mới, cancel thành công trước `run()` khiến body không được chạy; `get()` sẽ ném `CancellationException`. Mặc dù sau đó ta gọi `run()`, FutureTask là one-shot với terminal state.

## 11. Sử dụng FutureTask với ExecutorService cho đúng

### 11.1. Chạy trực tiếp bằng execute

~~~java
ExecutorService pool = Executors.newFixedThreadPool(4);

FutureTask<Integer> task = new FutureTask<>(() -> expensiveCompute());
pool.execute(task);

try {
    Integer answer = task.get();
    use(answer);
} finally {
    pool.shutdown();
}
~~~

Đây là snippet, đã có `expensiveCompute()` và `use(...)`, cần import các class. Trong production cần xử lý exception/cancel, shutdown timeout và ownership. Điểm chính: `execute(task)` nhận đúng **Runnable** là FutureTask, còn `get()` thực hiện trên cùng FutureTask do caller giữ.

### 11.2. Khi không cần FutureTask tự tạo

~~~java
Future<Integer> answer = pool.submit(() -> expensiveCompute());
Integer result = answer.get();
~~~

`ExecutorService.submit(Callable)` **đã trả một Future**, nên phần lớn ứng dụng không phải tự dựng `FutureTask`. Việc tự tạo FutureTask hữu ích khi:
- Phải dùng một nơi chỉ nhận `Runnable` nhưng vẫn cần Future handle.
- Cần chuyển **cùng một object** qua API `execute` rồi quản lý completion ở nơi khác.
- Muốn subclass FutureTask để can thiệp `done()` hoặc tích hợp với một queue/scheduler tùy biến.
- Muốn test/lập luận lifecycle `run/get/cancel` tường minh.

**Không bọc lồng FutureTask qua `submit(Runnable)` chỉ vì quen sử dụng `submit`**. Điều đó tạo thêm Future và thêm lớp cancellation/lifecycle không cần thiết.

### 11.3. Executor có thể từ chối task

`execute(task)` có thể ném `RejectedExecutionException`, chẳng hạn executor đã shutdown hoặc chính sách từ chối của pool kích hoạt. Nếu `FutureTask` của bạn **chưa được chạy hoặc hủy**, gọi `task.get()` sau một lần submit bị từ chối có thể **chờ vô hạn**, vì không worker nào hoàn thành nó.

Mẫu xử lý:

~~~java
FutureTask<Integer> task = new FutureTask<>(() -> 42);
try {
    pool.execute(task);
} catch (RejectedExecutionException e) {
    task.cancel(false);
    throw e;
}
~~~

Snippet giả định `pool` và imports tồn tại. `task.cancel(false)` trong nhánh này khiến những bên đang giữ handle không mắc kẹt ở một Future chưa được lên lịch. Tuy nhiên **đừng tự động làm vậy nếu rejection handler đã thực thi task bằng chính sách caller-runs hoặc một bên khác đang sở hữu task**; cần biết hợp đồng của executor/rejection policy thực tế. Chỉ một lần `execute` đã bị từ chối không chứng minh body chưa hề chạy trong mọi custom executor.

### 11.4. Dùng chung một FutureTask với hai executor?

Đưa **cùng một FutureTask** vào hai nơi không tạo hai computation độc lập. Tính one-shot có thể khiến một bên không làm gì; thứ tự chịu ảnh hưởng scheduler, và ownership/cancellation trở nên rối. Muốn hai lần chạy độc lập, tạo **hai FutureTask** (hoặc hai `Callable` submissions) riêng.

### 11.5. Cần kết quả theo thứ tự hoàn thành?

`FutureTask.get()` đợi **một Future cụ thể**. Nếu bạn có nhiều FutureTask, tuần tự gọi get theo thứ tự submit có thể gây **head-of-line blocking**: task đầu chậm làm chậm việc xử lý kết quả của task sau đã xong.

Khi cần lấy kết quả theo **completion order**, có thể cân nhắc `ExecutorCompletionService<V>` thay vì tự polling `isDone()` của hàng nghìn FutureTask. `ExecutorCompletionService` kết hợp submit công việc và completion queue, nhưng nó không thay đổi điều kiện chung rằng caller phải quản lý lỗi, timeout và hủy các task còn lại.

## 12. FutureTask.done(): hook khi chuyển sang trạng thái terminal

`FutureTask` cung cấp protected method `done()` để subclass override. Nó được gọi khi FutureTask chuyển sang trạng thái hoàn tất (normal, exception hoặc cancellation). Hook này giúp thực hiện một hành động cực ngắn khi completion xảy ra.

### Ví dụ Java 17: subclass và đếm callback

Tạo file **`FutureTaskDoneHookDemo.java`**:

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.FutureTask;
import java.util.concurrent.atomic.AtomicInteger;

public class FutureTaskDoneHookDemo {
    static final class TrackedTask<V> extends FutureTask<V> {
        private final AtomicInteger hookCalls = new AtomicInteger();

        TrackedTask(Callable<V> callable) {
            super(callable);
        }

        @Override
        protected void done() {
            hookCalls.incrementAndGet();
        }

        int hookCalls() {
            return hookCalls.get();
        }
    }

    public static void main(String[] args) throws Exception {
        TrackedTask<String> task =
                new TrackedTask<>(() -> "OK");

        task.run();
        task.run(); // Không hoàn thành lần hai.

        System.out.println("result=" + task.get());
        System.out.println("hookCalls=" + task.hookCalls());
        System.out.println("cancelled=" + task.isCancelled());
    }
}
~~~

Chạy:

~~~bash
javac FutureTaskDoneHookDemo.java
java FutureTaskDoneHookDemo
~~~

Stdout:

~~~text
result=OK
hookCalls=1
cancelled=false
~~~

**Điều quan trọng:**
- `done()` **không phải** callback cho mỗi lần `run()` được gọi; FutureTask chỉ có một completion của computation.
- Khi `run()` thực thi đồng bộ trên main, hook cũng chạy trong flow tương ứng. Nếu cancellation thắng, `done()` có thể chạy trong **thread gọi `cancel`**, không nhất thiết worker.
- **Không mặc định `done()` là dấu hiệu worker đã thật sự thoát khi cancel.** Future có thể chuyển sang cancelled, gọi hook, trong khi callable chưa rời stack.
- Tránh I/O lâu, blocking `get()` hoặc lock khó kiểm soát ngay trong `done()`. Một hook block có thể kéo dài luồng hoàn tất/cancel và gây contention, deadlock.
- Trong hook, nếu muốn biết outcome, phải xử lý các trường hợp normal, exception và canceled thay vì gọi `get()` rồi giả định luôn trả giá trị.
- Thời điểm notification và wakeup của waiter có thể khác với thời điểm xử lý hook; đừng dùng thứ tự giữa chúng để tạo invariant không được Javadoc cam kết.

### Có nên dùng done() để publish kết quả?

Một callback completion có thể gửi tín hiệu tới component khác, nhưng nếu kết quả dùng để quyết định giao dịch, cần có một state/commit protocol rõ ràng. `done()` có thể chạy khi computation thất bại hoặc bị hủy; chỉ dựa vào “hook được gọi” không đủ chứng minh success.

## 13. FutureTask không phải ScheduledFuture

Tên FutureTask nằm trong nhóm **Future & Scheduling**, nhưng `FutureTask` chỉ biểu diễn **một phép tính có thể chạy và quan sát trạng thái**. Nó tự nó **không** giữ một mốc giờ để bắt đầu hay chu kỳ lặp.

Để lập lịch sau delay hoặc định kỳ, `ScheduledExecutorService` và `ScheduledFuture` có API thích hợp:

~~~java
ScheduledExecutorService scheduler =
        Executors.newSingleThreadScheduledExecutor();

ScheduledFuture<?> scheduled = scheduler.schedule(
        () -> System.out.println("run once"),
        1, TimeUnit.SECONDS);
~~~

Đây là snippet, cần imports và shutdown scheduler ở cuối lifecycle. `ScheduledFuture<?>` kết hợp khả năng Future với `Delayed` (thời gian còn lại trước khi chạy). `scheduleAtFixedRate` và `scheduleWithFixedDelay` có semantics periodic theo contract riêng.

**Đừng cố gọi lại `futureTask.run()` mỗi giây để tạo tác vụ định kỳ.** FutureTask thông thường là one-shot. `FutureTask` có protected `runAndReset()` dành cho những trường hợp mở rộng có thể chạy body rồi reset trạng thái **mà không công bố kết quả terminal** nếu thành công, được sử dụng trong những cơ chế tùy biến. Đây là API protected, không phải lệnh bên ngoài “reset một FutureTask đã done”.

### runAndReset() có nên được sử dụng trong ứng dụng?

Thông thường **không**. Nó có semantics hẹp và cần subclass/kiểm soát state đúng:
- Không dùng được để “làm mới” FutureTask đã hoàn tất bình thường.
- Không có ý nghĩa thay `ScheduledExecutorService` cho periodic jobs phổ thông.
- Nếu Callable ném exception hoặc task bị cancel, việc reset/tiếp tục phụ thuộc contract và state.
- Đòi hỏi hiểu kỹ lifecycle, concurrency và override hook; nên ưu tiên abstraction chuẩn thay vì tự viết scheduler bằng protected method.

Lập lịch và theo dõi completion là hai trách nhiệm khác nhau: executor/scheduler quyết định **khi nào** task chạy; FutureTask quản lý **kết quả và trạng thái** của một computation.

## 14. Những lỗi phổ biến khi dùng FutureTask

1. **Tạo FutureTask rồi gọi `get()` ngay nhưng không start/run/execute.** Không có worker nào hoàn tất task, `get()` có thể chờ mãi. Phải thực sự schedule/run hoặc sử dụng timeout.
2. **Tưởng constructor `FutureTask(Runnable, result)` khiến Runnable trả `result`.** Result là giá trị cố định do caller cung cấp; chỉ công bố khi Runnable chạy thành công.
3. **Gọi `task.run()` và tưởng tạo thread mới.** Đó chỉ là method call trên thread hiện tại, trừ khi được Thread/executor gọi.
4. **Gọi `run()` hai lần và mong chạy lại.** FutureTask là one-shot, không phải scheduler.
5. **Dùng `submit(futureTask)` rồi nhầm Future bên ngoài với chính FutureTask.** Có thể xuất hiện hai handle với return/cancel semantics khác nhau; ưu tiên `execute(futureTask)`.
6. **Dùng `isDone()==true` để kết luận task thành công.** Task có thể thất bại hoặc cancelled.
7. **Dùng `isCancelled()==false` để kết luận task đã hoàn thành.** Có thể chưa bắt đầu/đang chạy.
8. **Gọi `get(timeout)` rồi giả định task đã bị cancel khi timeout.** Timed get chỉ kết thúc chờ của caller.
9. **Xem `cancel(true)` như lệnh kill.** Worker có thể bỏ qua interrupt, đang block I/O hoặc tiếp tục cleanup.
10. **Gọi `task.get()` trong callback/lock quan trọng mà không có timeout hoặc dependency graph.** Có thể gây deadlock nếu task cần chính lock đang giữ hoặc executor có quá ít worker.
11. **Dùng một thread pool có một worker, task A chờ `taskB.get()` mà task B cũng nằm sau A trong cùng queue.** B không có cơ hội chạy: thread-starvation deadlock.
12. **Đẩy cùng FutureTask vào nhiều executor vì muốn nhân đôi tính toán.** One-shot khiến không có hai result độc lập; ownership không rõ.
13. **Không xử lý `ExecutionException`.** Lỗi thực thi nằm trong `getCause()`, không nhất thiết xuất hiện ở nơi gọi `execute`.
14. **Không xử lý `CancellationException`.** Đây là trạng thái hợp lệ của một tác vụ bị hủy, không có kết quả để đọc.
15. **Quên restore interrupt status khi đã bắt `InterruptedException` nhưng không propagate.** Caller cao hơn có thể mất tín hiệu hủy.
16. **Dùng `done()` làm nơi thực hiện blocking I/O lâu.** Hook có thể chạy trên worker hoặc canceller, tăng latency và tạo deadlock.
17. **Không cleanup sau `cancel(true)`.** Future cancelled không chứng minh lock/permit/connection đã được trả.
18. **Không xử lý `RejectedExecutionException` từ executor.** FutureTask có thể ở NEW mãi mà không ai chạy.
19. **Giao side effect quan trọng cho task rồi coi Future cancelled là rollback.** Remote system có thể đã commit; cần idempotency hoặc reconciliation.
20. **Không phân biệt `FutureTask` và `CompletableFuture`.** Cả hai expose Future API, nhưng graph completion/cancellation/interrupt semantics khác nhau theo implementation.

## 15. Test FutureTask như thế nào?

Tập trung xác nhận **cả trạng thái Future và hành vi thực thi**.

### 15.1. Các test nên có

| Kịch bản | Assertion |
| --- | --- |
| Chưa chạy | `isDone()==false`, không có side effect |
| Runnable hoàn tất | `get()` trả giá trị constructor; body chạy một lần |
| Callable hoàn tất | `get()` trả đúng giá trị tính được |
| Gọi `run()` nhiều lần | Body vẫn thực thi một lần |
| Callable ném exception | `get()` ném `ExecutionException` với cause gốc |
| Timed get hết hạn | `TimeoutException`, Future có thể hoàn thành sau |
| Cancel trước chạy | Body không chạy, `get()` ném `CancellationException` |
| Cancel khi đang block interruptible | Future cancelled, worker xử lý interrupt và cleanup |
| Cancel khi task bất hợp tác | Future có thể cancelled trong khi body còn chạy |
| Executor từ chối | Không chờ `get()` trên một task không bao giờ được schedule |
| Hook `done()` | Được gọi tại terminal transition, không mặc định có kết quả success |
| Nhiều thread chờ cùng Future | Mọi waiter nhận cùng outcome của computation |

### 15.2. Điều phối race bằng latch

Một cách test đáng tin là dùng `CountDownLatch`:
- `started`: xác nhận worker đã vào body.
- `release`: giữ worker ở vị trí nhất định cho tới khi main kiểm tra một sự kiện.
- `exited`: xác nhận worker đã rời body.
- `Future.get(timeout)`: bảo vệ test khỏi treo không thời hạn khi có bug.

`Thread.sleep(100)` chỉ gợi ý thời gian chờ, **không chứng minh** worker đã bắt đầu hoặc đang bị block ở đoạn code bạn quan tâm. Dùng latch/barrier để tạo quan hệ thứ tự rõ ràng.

### 15.3. Kiểm thử bằng stdout

Đừng in thời gian thực thi hay thứ tự thread nếu không bảo đảm scheduling. Nếu demo có nhiều worker chạy cạnh tranh, output cần dựa trên:
- Giá trị cuối sau `join/get`.
- Số lần side effect được đếm bằng primitive đồng bộ thích hợp.
- Trạng thái logic đã được điều phối.
- Exception loại nào theo contract.
- Chỉ in những kết quả tất định trong điều kiện demo đã nêu.

### 15.4. Vòng đời thread và tài nguyên

Sau khi dùng executor, thường có:

~~~java
pool.shutdown();
try {
    if (!pool.awaitTermination(1, TimeUnit.MINUTES)) {
        pool.shutdownNow();
    }
} catch (InterruptedException e) {
    pool.shutdownNow();
    Thread.currentThread().interrupt();
}
~~~

Đây là snippet có `pool` đã khai báo. `shutdown()` ngừng nhận task mới nhưng cho các task đã submit hoàn thành; `shutdownNow()` chỉ **cố gắng** ngắt các task đang chạy. `awaitTermination` giúp caller quan sát executor thực sự kết thúc; không tự hứa mọi task có thể bị ngắt tức thời.

## 16. Lựa chọn FutureTask hay API nào khác?

| Nhu cầu | Lựa chọn thường rõ ràng |
| --- | --- |
| Chỉ chạy hành động trên thread khác, caller không cần handle | `Runnable` + `Thread` hoặc `Executor.execute` |
| Chạy Callable và nhận Future, không cần tự tạo object | `ExecutorService.submit(Callable)` |
| Có Runnable sẵn, vẫn muốn `get/cancel/isDone` trên cùng object truyền vào execute | **`FutureTask(Runnable, result)`** |
| Muốn tự giữ một Future/Runnable object, custom `done()` | Subclass **`FutureTask`** có kiểm soát |
| Định kỳ theo lịch | `ScheduledExecutorService` / `ScheduledFuture` |
| Xử lý nhiều completion theo thứ tự xong | `ExecutorCompletionService` |
| Pipeline transformation/composition bất đồng bộ | `CompletableFuture`; hiểu khác biệt cancellation |
| Phân tầng cancellation tới nhiều child tasks | Ownership, Future handles, token/deadline và cleanup policy |
| Cần dừng tác vụ ngay lập tức, kể cả I/O không hợp tác | Không có bảo đảm tổng quát bằng `FutureTask.cancel(true)`; phải thiết kế timeout/cancellation ở resource |

**Chọn theo nhu cầu**, không phải độ “cao cấp” của tên class. FutureTask phù hợp khi bạn cần một object **vừa Runnable, vừa Future**. Nếu chỉ cần submit một Callable rồi `get()`, cách ngắn nhất thường là `executor.submit(callable)`.

## 17. Câu hỏi tự kiểm tra

1. `FutureTask<V>` implement interface nào để vừa chạy được vừa theo dõi được? **`RunnableFuture<V>`**, kết hợp `Runnable` và `Future<V>`.
2. `FutureTask<>(runnable, "OK")` lấy giá trị `"OK"` từ đâu? **Từ tham số constructor**, không phải từ `Runnable.run()`.
3. Khi Runnable ném exception, `FutureTask.get()` trả `"OK"` không? **Không**, nó ném `ExecutionException`.
4. Khác biệt giữa `new Thread(task).start()` và `task.run()`? **start tạo/lập lịch thread; run chỉ gọi method trên thread hiện tại**.
5. `task.run()` ba lần có gọi Callable ba lần không? **Không**, FutureTask one-shot.
6. Vì sao `execute(futureTask)` đủ khi caller vẫn giữ object? **FutureTask đã là Runnable và Future**, không cần executor trả handle.
7. Vì sao `submit(futureTask)` có thể gây nhầm? **Submit(Runnable) thường trả một Future bao ngoài**, khác inner FutureTask.
8. `isDone()==true` có chắc nhiệm vụ thành công không? **Không**, có thể exception/cancel.
9. `isCancelled()==false` có chứng minh task đang chạy không? **Không**, có thể chưa bắt đầu hoặc đã hoàn tất**.
10. Khi task throw, lấy lỗi gốc từ đâu? **`ExecutionException.getCause()`**.
11. `get(timeout)` timeout có tự cancel task không? **Không**.
12. `cancel(true)` có bảo đảm thread đã thoát khi trả `true` không? **Không**, có thể còn chạy/cleanup.
13. Sau cancel thành công, `get()` ném gì? **`CancellationException`**.
14. Có nên gọi `get()` trên FutureTask chưa hề được schedule không? **Không nếu không có cơ chế sẽ chạy hoặc timeout**, vì có thể chờ vô hạn.
15. Một FutureTask đã cancel trước `run()` có thực thi Callable không? **Không**, cancellation terminal ngăn body chạy.
16. Vì sao `done()` không nên làm I/O dài? **Hook có thể chạy trong worker/canceller và làm chậm completion/cancellation hoặc deadlock**.
17. `done()` gọi có bảo đảm task đã kết thúc cleanup không? **Không phải với cancellation**, Future có thể terminal trước khi body rời stack.
18. FutureTask có tự chạy định kỳ khi gọi run lặp lại không? **Không**, dùng `ScheduledExecutorService`.
19. Để chờ kết quả theo thứ tự hoàn tất của nhiều task, nên cân nhắc gì? **`ExecutorCompletionService`**.
20. Có cần tự dựng FutureTask khi chỉ muốn `pool.submit(() -> 42)`? **Không bắt buộc**, submit đã trả Future.
21. Khi `execute` bị từ chối, nguy cơ nếu vẫn gọi `task.get()`? **Có thể chờ mãi vì task không được chạy**.
22. `Future.get()` có memory consistency guarantee gì? **Hành động trong computation happens-before hành động sau `get()` tương ứng ở thread khác**.
23. Task bị cancel sau khi đã ghi database có được rollback bằng FutureTask không? **Không**; phải có giao thức nghiệp vụ tại nơi có side effect.
24. Hai thread cùng gọi `run()` trên một FutureTask tạo hai kết quả độc lập không? **Không**, vẫn cùng một computation.
25. Chương trình có thể dùng FutureTask với một `Runnable` vốn không trả kết quả để biết “đã xong chưa” không? **Có**, thông qua `get/isDone` hoặc `FutureTask<Void>` với result null.

## Kết luận

`FutureTask<V>` là một **implementation cụ thể của `RunnableFuture<V>`**. Nó biến một `Runnable` hoặc `Callable<V>` thành **một computation one-shot vừa có thể được thực thi, vừa có thể được theo dõi bằng Future**:

~~~text
FutureTask(Runnable, result) hoặc FutureTask(Callable)
          |
          +---> Thread.start() / Executor.execute() / run()
          |
          +---> isDone() / isCancelled()
          |
          +---> get() / get(timeout) / cancel(true|false)
~~~

Với `Runnable`, kết quả `get()` là giá trị truyền vào constructor **nếu tác vụ hoàn tất bình thường**; với `Callable<V>`, đó là giá trị do `call()` trả. Các lỗi được bọc trong `ExecutionException`, cancellation dẫn tới `CancellationException`, và timed get **không tự hủy computation**.

`FutureTask` giúp quản lý vòng đời kết quả của một tác vụ, nhưng **không tự là scheduler định kỳ, không bắt buộc mọi I/O phản hồi interrupt, và không thay thế giao thức cleanup/commit**. Khi executor đã có `submit(Callable)` và không cần custom lifecycle, bạn có thể dùng Future được trả về trực tiếp thay vì tạo thêm FutureTask.

## Tài liệu tham khảo Java SE 17

- [FutureTask](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/FutureTask.html): constructors, `run`, `done`, `runAndReset`, `get` và cancellation.
- [RunnableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RunnableFuture.html): kết hợp Runnable và Future.
- [Runnable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runnable.html): contract `run`.
- [Callable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Callable.html): phép tính trả kết quả hoặc exception.
- [Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): get, cancel, isDone, memory consistency.
- [ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): execute, submit, shutdown.
- [ScheduledExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html): lập lịch delayed và periodic.
- [ExecutorCompletionService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorCompletionService.html): xử lý kết quả theo completion order.
- [CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): completion pipelines và sự khác biệt cancellation.
