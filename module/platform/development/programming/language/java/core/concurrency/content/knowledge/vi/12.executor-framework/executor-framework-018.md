# beforeExecute(), afterExecute() và cách nhận biết ngoại lệ của tác vụ submit() trong Java

> **Phạm vi:** Executor Framework trong **Java concurrency nói chung**, đặc biệt là các hook `ThreadPoolExecutor.beforeExecute(Thread, Runnable)`, `afterExecute(Runnable, Throwable)`, cách truyền ngoại lệ giữa `execute()`, `submit()` và `Future`, cũng như logging, metrics, cleanup và lifecycle. Không bàn về interception, scheduler hoặc thread-pool abstraction riêng của Spring vì phần đó có chương độc lập.

## 1. Vấn đề thực tế: task thất bại nhưng log không hiện lỗi

Giả sử một ứng dụng chạy nhiều task trong `ThreadPoolExecutor`. Khi thực thi một `Runnable` ném `RuntimeException` qua `execute()`, exception có thể thoát khỏi `run()` của worker, khiến thread kết thúc bất thường và xuất hiện trong đường xử lý uncaught exception.

Nhưng khi giao một task ném lỗi bằng `submit()`, nhiều người nhận thấy:

- `afterExecute(r, t)` **được gọi** nhưng `t == null`;
- không có stack trace tự động xuất hiện theo cách họ kỳ vọng;
- `Future.get()` lại ném `ExecutionException` chứa ngoại lệ thực sự.

Đây không phải lỗi của Java. `submit()` thường **bọc Runnable/Callable trong một `FutureTask`**. `FutureTask.run()` bắt lỗi của task, lưu outcome vào trạng thái Future và **không ném lại cùng lỗi đó ra ngoài `run()`**. Vì vậy `ThreadPoolExecutor` thường xem lần gọi `task.run()` của wrapper đã trở về bình thường và truyền `null` ở tham số `Throwable` của hook.

**Kết luận quan trọng:** `afterExecute` không phải một “bẫy bắt tất cả lỗi” nếu chỉ kiểm tra tham số `Throwable`. Khi `Runnable r` là một `Future<?>` đã hoàn tất, cần kiểm tra outcome qua `Future.get()` và xử lý `ExecutionException` / `CancellationException` đúng cách.

## 2. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `Executor.execute(Runnable)` và `ExecutorService.submit(...)` về cách đóng gói task, kết quả và exception.
2. Giải thích chính xác khi nào `beforeExecute`, `afterExecute` và `terminated` được `ThreadPoolExecutor` gọi.
3. Giải thích tham số `Throwable t` của `afterExecute` thể hiện điều gì và vì sao thường là null với `submit()` dù task ném exception.
4. Viết hook `afterExecute` để nhận diện lỗi của cả task được `execute()` giao trực tiếp và task dạng `Future` đã hoàn thành.
5. Phân biệt `ExecutionException`, `CancellationException`, `InterruptedException`, rejection và lỗi phát sinh ngay trong chính hook.
6. Hiểu trường hợp **hook không chạy**: task chưa được worker thực thi, bị reject, bị loại khỏi queue, chạy qua một policy ngoài worker, hoặc `beforeExecute` ném exception.
7. Thiết kế logging/metrics/tracing/ThreadLocal cleanup **nhanh, không gây block vô hạn, không ném exception ngoài ý muốn**.
8. Kiểm thử kết quả từ Java 17 với lịch thực thi có kiểm soát và phân tích memory consistency, lifecycle của pool.

## 3. Trước hết, hiểu hai con đường thực thi

### 3.1. `execute(Runnable)`: chạy task do caller cung cấp

Ví dụ:

```java
pool.execute(() -> {
    throw new IllegalStateException("direct task failed");
});
```

Đây là **đoạn minh họa**, `pool` phải là một `Executor`/`ThreadPoolExecutor` được tạo ở bên ngoài. Một `Runnable` trực tiếp ném unchecked exception khi `run()` chạy. Đối với `ThreadPoolExecutor` thông thường, throwable này thoát khỏi `task.run()`, được `afterExecute(r, t)` nhận qua `t`; sau đó worker có thể kết thúc bất thường và được thay thế khi executor cần duy trì pool.

Không nên khẳng định mọi `execute()` luôn tạo lỗi ở tham số `t`: caller cũng có thể gọi `execute(futureTask)` hoặc `execute(wrapper)` mà wrapper tự bắt exception, khi đó `run()` không ném ra. Điều quyết định là **Runnable thật được worker gọi** có để exception thoát ra khỏi `run()` hay không.

### 3.2. `submit(...)`: đóng gói task và trả Future

Ví dụ:

```java
Future<Integer> result = pool.submit(() -> {
    throw new IllegalArgumentException("submitted task failed");
});
```

Đây là đoạn minh họa, cần import `java.util.concurrent.Future` và một `pool` là `ExecutorService`. `submit(Callable<T>)` thường tạo một `RunnableFuture<T>` như `FutureTask`, gửi wrapper đó vào `execute()` nội bộ rồi trả Future.

Khi `Callable.call()` ném `IllegalArgumentException`:

- `FutureTask` bắt throwable và lưu trạng thái **completed exceptionally**;
- `Future.get()` ném `ExecutionException`, trong đó `getCause()` là `IllegalArgumentException` gốc;
- `FutureTask.run()` không ném lại ngoại lệ đó ra bên ngoài;
- vì thế `afterExecute(r, t)` thường nhận `t == null`;
- `r` có thể là object có interface `Future<?>`, nên hook có thể đọc outcome từ Future sau khi task.run hoàn tất.

Tương tự, `submit(Runnable)` cũng thường bọc task để có Future, mặc dù `Runnable` không trả một giá trị kiểu T.

### 3.3. Bảng so sánh cốt lõi

| Câu hỏi | `execute(() -> throws)` trực tiếp | `submit(() -> throws)` |
|---|---|---|
| Đối tượng worker chạy | Runnable do caller cung cấp (hoặc wrapper do caller gửi) | Thường là `FutureTask`/`RunnableFuture` |
| API trả về | `void` | `Future<?>` / `Future<T>` |
| Khi logic task ném unchecked exception | Có thể thoát khỏi `Runnable.run()` | Thường bị wrapper bắt và lưu |
| `afterExecute(r, t)` | `t` thường chứa throwable nếu nó thoát từ `run()` | `t` thường `null` |
| Caller lấy lỗi qua `Future.get()` | Không có Future từ chính lời gọi `execute` | `ExecutionException.getCause()` |
| Worker bị kết thúc bởi exception task | Có thể có, khi exception thực sự thoát khỏi `run()` | Thường không, vì FutureTask đã bắt exception |
| `isDone()` / `isCancelled()` | Không có nếu task không tự là Future | Có trên Future trả về |

Bảng mô tả **đường chạy chuẩn trên ThreadPoolExecutor và FutureTask**, không là một khẳng định về mọi Executor implementation hay mọi Runnable wrapper tùy biến.

## 4. Các hook chính của ThreadPoolExecutor

`ThreadPoolExecutor` có ba phương thức hook được thiết kế để subclass override:

```java
protected void beforeExecute(Thread t, Runnable r)
protected void afterExecute(Runnable r, Throwable t)
protected void terminated()
```

Đây là **chữ ký API minh họa**, không phải một class Java độc lập.

### `beforeExecute(Thread thread, Runnable task)`

- Được worker thread gọi **ngay trước khi chạy `Runnable.run()`** cho task được lấy để thực thi.
- Dùng để gắn instrumentation, lấy timestamp, đặt context cục bộ theo thread, increment “task started” metric, hoặc kiểm tra điều kiện nhẹ.
- Tham số `thread` cho biết worker thread thực thi; `task` là Runnable thật sự đưa vào worker, **có thể là wrapper FutureTask** chứ không phải Callable ban đầu.
- JavaDoc khuyến khích override gọi `super.beforeExecute(thread, task)`, thường **ở đầu** method.

**Nguy hiểm:** nếu chính `beforeExecute` ném exception, task có thể **không được gọi `run()`**, và `afterExecute` **không được gọi cho task đó** theo cấu trúc worker loop chuẩn. Vì vậy không đặt validation tùy tiện ném exception trong hook nếu muốn theo dõi completion nhất quán.

### `afterExecute(Runnable task, Throwable error)`

- Được worker gọi **sau khi `task.run()` kết thúc**, bình thường hoặc ném ra throwable, **nếu `beforeExecute` đã trở về bình thường**.
- `error` khác null khi có throwable **thoát ra khỏi `task.run()`** tới vòng điều khiển worker.
- `error` thường null nếu `run()` trở về bình thường, kể cả trong trường hợp **logic bên trong một FutureTask đã thất bại** nhưng wrapper bắt được exception.
- Tham số `task` là wrapper Runnable mà worker vừa chạy, có thể đồng thời là `Future<?>`.
- Có thể đọc `Future.get()` nếu Future **đã hoàn thành** để xác định lỗi stored exception/cancellation.
- JavaDoc khuyến khích gọi `super.afterExecute(task, error)`, thường **ở cuối** method.

**Không dùng `afterExecute` để làm tác vụ dài hoặc blocking I/O.** Hook chạy trong **worker thread** đang chịu trách nhiệm thực thi work queue. Nếu hook mất vài giây để gọi network/logging đồng bộ, worker chưa sẵn sàng cho task tiếp theo; throughput giảm, queue tăng, có thể gây backpressure và deadlock.

### `terminated()`

Được gọi khi executor **chuyển sang trạng thái terminated** (sau khi task/workers đã đi đến lifecycle kết thúc theo contract), thường dùng để ghi một metric hoặc dọn state chung thuộc executor. Đây **không phải hook gọi sau mỗi task**.

`terminated()` không thay thế `shutdown()` hoặc `awaitTermination()` của caller; các điểm trên thuộc hai vai trò khác nhau.

## 5. Trình tự hook trong worker loop

Mô hình khái niệm của `ThreadPoolExecutor`:

```text
Worker lấy task từ workQueue hoặc nhận firstTask
             |
             v
    beforeExecute(thread, task)
             |
             v
         task.run()
         /       \
    trả về      throw ra
       \         /
        \       /
             v
   afterExecute(task, throwableOrNull)
             |
             v
     worker tiếp tục / kết thúc
```

Đây là **mô hình giản lược**; implementation còn phải giữ/nhả worker lock, cập nhật counters, xử lý interrupt, shutdown và worker replacement.

**Chi tiết quan trọng:** trong triển khai chuẩn, lời gọi `beforeExecute` ở ngoài phần `try/finally` bao quanh `task.run()` và `afterExecute`. Vì thế nếu `beforeExecute` tự ném exception, `task.run()` chưa chạy và `afterExecute` không được gọi. Ngoài ra, nếu `afterExecute` tự ném exception, worker cũng có thể kết thúc bất thường và làm exception handling/lifecycle phức tạp hơn.

**Không nhầm tham số thứ hai của `afterExecute` với “mọi Throwable từng xảy ra”.** Nó chỉ phản ánh throwable đi ra khỏi `task.run()` theo đường thực thi mà hook nhận được.

## 6. Tại sao afterExecute(Throwable) bỏ sót lỗi của submit()?

`AbstractExecutorService.submit` dùng một cơ chế kiểu `newTaskFor(...)` để biến `Runnable/Callable` thành `RunnableFuture`, thường là `FutureTask`, rồi gọi `execute` với wrapper.

Ý tưởng của `FutureTask.run()`:

```text
try:
    result = callable.call()
    save successful result
catch Throwable ex:
    save failure ex inside Future
return from run()
```

Mô tả này chỉ là **pseudocode**, không phải bytecode hoặc implementation đầy đủ của FutureTask.

Nếu worker gọi `task.run()` và wrapper trả về bình thường, `ThreadPoolExecutor` không thấy một Throwable thoát ra. Hook vì vậy nhận `t == null`. Tuy nhiên, **`Future.get()` biết failure** vì FutureTask đã lưu outcome.

Điều này giải thích hiện tượng hay gặp:

```java
// Minh họa lỗi giám sát chưa đủ.
@Override
protected void afterExecute(Runnable task, Throwable error) {
    super.afterExecute(task, error);
    if (error != null) {
        log(error);
    }
}
```

Đây là **method minh họa**, cần có `log(Throwable)` và một subclass của `ThreadPoolExecutor`. Nó phát hiện Throwable trực tiếp từ `execute(Runnable)`, nhưng có thể bỏ sót hầu hết exception do `submit()` lưu trong Future.

Cách chính xác là **kiểm tra cả hai kênh**, đồng thời xử lý cancellation, interrupt và tình huống task không phải Future.

## 7. Mẫu hook kiểm tra Future an toàn

Mẫu dùng trong một subclass `ThreadPoolExecutor`:

```java
@Override
protected void afterExecute(Runnable task, Throwable thrown) {
    try {
        Throwable failure = thrown;

        if (failure == null && task instanceof Future<?> future
                && future.isDone()) {
            try {
                future.get(); // completed Future: không chờ kết quả nữa
            } catch (CancellationException e) {
                recordCancellation(e);
            } catch (ExecutionException e) {
                failure = e.getCause();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                recordHookInterrupted(e);
            }
        }

        if (failure != null) {
            recordTaskFailure(failure);
        }
    } finally {
        super.afterExecute(task, thrown);
    }
}
```

Đây là **method minh họa**, chưa phải class độc lập: cần imports `Future`, `ExecutionException`, `CancellationException`, các phương thức `record...` và một subclass `ThreadPoolExecutor`. Những thao tác ghi metric/log trong hook phải **không ném exception không được xử lý và không block dài**.

Điều kiện `task instanceof Future<?>` cần thiết vì với `submit()`, task thường là `FutureTask`. Tuy nhiên, người gọi có thể truyền `FutureTask` trực tiếp qua `execute()`; hoặc một executor được subclass override `newTaskFor` trả một loại `RunnableFuture` khác. Vì thế nên dựa vào **interface Future** thay vì cố nhận diện task bằng cách chỉ kiểm tra nó được gửi từ method nào.

### Vì sao kiểm tra `future.isDone()`?

`afterExecute` được gọi sau khi `task.run()` hoàn thành và với một `FutureTask` chuẩn, Future đã done. Tuy nhiên, để không vô tình gọi `get()` blocking với một Runnable custom cũng implement Future nhưng semantics bất thường, mẫu kiểm tra `isDone()` trước. `isDone` true bao gồm thành công, thất bại hoặc canceled.

**Lưu ý:** một `Future` custom có thể vi phạm các kỳ vọng thực tế của code instrumentation, hoặc `isDone` có semantics được định nghĩa khác; không nên dùng một Future wrapper tùy ý không có contract rõ. Với FutureTask của JDK, đường kiểm tra trên là hợp lý.

### Xử lý các outcome riêng biệt

- **Task thành công:** `future.get()` trả kết quả; hook không cần sử dụng kết quả nếu chỉ thu metric.
- **Task thất bại:** `future.get()` ném `ExecutionException`; dùng **`getCause()`** để ghi lỗi gốc, không chỉ log wrapper.
- **Task bị hủy:** `future.get()` ném `CancellationException`; cancellation thường cần metric riêng, **không mặc định xem là business failure**.
- **Hook bị interrupt:** `get()` có thể ném `InterruptedException`. Nếu catch và không propagate, khôi phục interrupt status; ghi metric thích hợp mà không làm hook ném thêm.
- **`thrown != null`:** đã có lỗi thực sự thoát khỏi `Runnable.run()`; không cần gọi Future.get chỉ để tìm lại lỗi nếu quy tắc đã xác định kênh ưu tiên.

**Không được catch `Exception` rồi bỏ qua hết**: làm vậy vừa che lỗi task vừa che lỗi instrumentation. Hãy nêu rõ chính sách lưu lỗi và giữ hook đủ đơn giản.

## 8. Ví dụ Java 17 chạy được với cả execute() và submit()

Chương trình sau tạo subclass `ObservedPool` của `ThreadPoolExecutor` với một worker. Trong `beforeExecute`, pool đếm số lần task bắt đầu. Trong `afterExecute`, pool kiểm tra:

- `Runnable task` đồng thời implement `Future<?>`: đọc outcome từ `Future.get()`;
- task không phải Future có `error != null`: ghi lại loại exception từ `execute()` trực tiếp.

Một `CountDownLatch` đảm bảo main **đợi cả hai lần afterExecute kết thúc** trước khi in kết quả. `UncaughtExceptionHandler` được đặt thành handler rỗng **chỉ để stdout minh họa được xác định** khi task `execute()` cố ý ném exception; không sử dụng cách nuốt lỗi này trong production.

Tạo file **`ExecutorHookDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.CancellationException;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class ExecutorHookDemo {
    static final class ObservedPool extends ThreadPoolExecutor {
        final AtomicInteger beforeCount = new AtomicInteger();
        final AtomicInteger afterCount = new AtomicInteger();
        final AtomicReference<String> executeError = new AtomicReference<>("none");
        final AtomicReference<String> submitError = new AtomicReference<>("none");
        final CountDownLatch completedHooks = new CountDownLatch(2);

        ObservedPool() {
            super(1, 1, 0, TimeUnit.MILLISECONDS, new LinkedBlockingQueue<>());
            setThreadFactory(task -> {
                Thread thread = new Thread(task, "observed-worker");
                thread.setUncaughtExceptionHandler((t, e) -> { });
                return thread;
            });
        }

        @Override
        protected void beforeExecute(Thread thread, Runnable task) {
            super.beforeExecute(thread, task);
            beforeCount.incrementAndGet();
        }

        @Override
        protected void afterExecute(Runnable task, Throwable error) {
            try {
                if (task instanceof Future<?> future) {
                    if (future.isDone()) {
                        try {
                            future.get();
                        } catch (ExecutionException e) {
                            submitError.set(e.getCause().getClass().getSimpleName());
                        } catch (CancellationException e) {
                            submitError.set("cancelled");
                        } catch (InterruptedException e) {
                            Thread.currentThread().interrupt();
                            submitError.set("interrupted");
                        }
                    }
                } else if (error != null) {
                    executeError.set(error.getClass().getSimpleName());
                }
            } finally {
                afterCount.incrementAndGet();
                completedHooks.countDown();
                super.afterExecute(task, error);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        ObservedPool pool = new ObservedPool();
        try {
            Future<Integer> failed = pool.submit(() -> {
                throw new IllegalArgumentException("from submit");
            });
            try {
                failed.get();
            } catch (ExecutionException e) {
                System.out.println("callerSaw=" + e.getCause().getClass().getSimpleName());
            }

            pool.execute(() -> {
                throw new IllegalStateException("from execute");
            });

            if (!pool.completedHooks.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("hooks timed out");
            }
            System.out.println("beforeCount=" + pool.beforeCount.get());
            System.out.println("afterCount=" + pool.afterCount.get());
            System.out.println("submitHookError=" + pool.submitError.get());
            System.out.println("executeHookError=" + pool.executeError.get());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
```

Biên dịch và chạy với JDK 17:

```bash
javac --release 17 ExecutorHookDemo.java
java ExecutorHookDemo
```

**Stdout đã kiểm chứng:**

```text
callerSaw=IllegalArgumentException
beforeCount=2
afterCount=2
submitHookError=IllegalArgumentException
executeHookError=IllegalStateException
```

### Giải thích vì sao kết quả không phụ thuộc scheduler

1. `pool.submit(...)` trả Future của một task **cố ý** ném `IllegalArgumentException`.
2. Main gọi `failed.get()`, nhận `ExecutionException` rồi đọc cause. Vì thế dòng `callerSaw=IllegalArgumentException` luôn có khi task thực sự đã chạy tới lời ném và đường thực thi bình thường của demo hoàn tất.
3. `FutureTask.run()` lưu failure; ở hook `afterExecute`, `task instanceof Future<?>` đúng, `future.isDone()` đúng, `future.get()` ném `ExecutionException` và hook ghi `submitHookError`.
4. `pool.execute(...)` nhận Runnable trực tiếp, tự ném `IllegalStateException` ra khỏi `run()`; hook nhận error khác null và ghi `executeHookError`.
5. Cả hai task đều đi qua `beforeExecute` và `afterExecute` trong tình huống đã xác minh. `AtomicInteger` bảo đảm đếm thread-safe, cho `beforeCount=2` và `afterCount=2`.
6. `completedHooks` đếm xuống sau mỗi lần after hook xử lý outcome. Main đợi bằng `await(5, SECONDS)` nên đọc trạng thái hook **sau** hai lần hoàn tất, không phải phỏng đoán bằng `Thread.sleep`.
7. `CountDownLatch` có memory-consistency effects phù hợp, nên main quan sát đúng dữ liệu các hook đã ghi trước `countDown`.
8. `setUncaughtExceptionHandler((t,e)->{})` cố tình không in lỗi `execute` trong bài thực hành để stdout có thể so sánh chính xác. **Production phải có xử lý uncaught exception thích hợp**: log, metric, alert hoặc escalation. Không sao chép handler rỗng cho công việc quan trọng.

**Lưu ý:** chương trình chỉ có một task submit và một task execute; các trường `submitError`/`executeError` chứa một string mới nhất, không phải hệ thống thu thập lỗi đầy đủ cho nhiều task. Với sản phẩm thật, dùng logging/tracing tập trung hoặc metrics counters, không chỉ ghi vào một AtomicReference. Demo đợi hook bằng latch có timeout để tránh kẹt vô hạn trong kiểm thử.

## 9. Phân biệt “hook chạy xong” và “task hoàn thành”

Với `submit()`, `FutureTask` có thể đánh dấu Future đã done **trước khi `afterExecute` hoàn tất**. Vì vậy:

- `future.get()` xác nhận **logic task đã có outcome**, với memory guarantees của Future.
- Nó **không nhất thiết xác nhận toàn bộ logging/cleanup bên trong `afterExecute` đã hoàn tất**.
- Nếu caller cần quan sát chính xác hook đã hoàn tất (ví dụ test một custom pool), cần một tín hiệu riêng như `CountDownLatch` của demo, hoặc giao thức completion riêng được thiết kế rõ.

Đây là lý do demo không chỉ gọi `failed.get()` rồi lập tức kiểm tra `submitError`. Main còn chờ `completedHooks`, nên kết quả kiểm tra hook có ranh giới đồng bộ rõ ràng.

**Tương tự:** `shutdown()` không tự chờ hook/task kết thúc. `awaitTermination()` chỉ trả thành công khi executor thực sự terminated, nhưng nếu đang cần một kết quả task cụ thể, `Future.get()` thường là API trực tiếp hơn.

## 10. Khi nào hook hoàn toàn không được gọi?

Không được coi hook là sự kiện “mọi task từng submit đã được nhận và kết thúc”. Hook thuộc **worker execution path** của `ThreadPoolExecutor`, không thuộc một hệ thống audit mọi lần submit ở mọi trạng thái.

| Tình huống | `beforeExecute` / `afterExecute` có chạy không? |
|---|---|
| Task được worker lấy và `run()` trở về bình thường | Thường cả hai chạy |
| Task được worker lấy, `run()` ném unchecked throwable | `beforeExecute` và `afterExecute` nhận throwable, nếu before hook trở về bình thường |
| Task chạy qua `FutureTask` và lưu failure | Hook vẫn chạy nếu worker đã thực sự gọi wrapper; `t` thường null |
| Task bị reject tại `execute/submit` | **Không**, vì worker không chạy task |
| Task còn trong queue và bị `shutdownNow()` trả ra, chưa được chạy | **Không**, vì chưa đi vào worker |
| Task bị loại khỏi queue bởi `remove/purge` trước khi worker lấy | **Không** |
| `beforeExecute` tự ném exception | `task.run()` chưa được gọi; `afterExecute` **không được gọi** cho task đó |
| `CallerRunsPolicy` chạy task trong caller khi pool bão hòa | Không qua worker loop ⇒ không nên mong pool hook chạy |
| `DiscardPolicy` âm thầm bỏ task | Không qua worker loop ⇒ không có hook |
| Caller tự chạy `Runnable.run()` bên ngoài pool | Không qua ThreadPoolExecutor worker ⇒ không có hook |

**Task đã bị hủy (`cancel`) cũng cần phân biệt:** một `FutureTask` bị cancel **nhưng vẫn nằm trong queue và sau đó được worker gọi `run()`** có thể đi qua hooks; `run` thấy trạng thái canceled rồi return nhanh. Nhưng nếu nó đã được loại khỏi queue hoặc không bao giờ được worker xử lý, hooks sẽ không có cơ hội chạy. Vì thế số lần `afterExecute` **không tự bằng số task từng được submit**.

### Rejection trong `submit()` có đặc điểm riêng

Một implementation `submit()` thường tạo FutureTask rồi gọi `execute`. Nếu executor dùng `AbortPolicy` và reject, `RejectedExecutionException` được ném ngay cho caller. Nếu dùng handler bỏ task im lặng, caller có thể đã nhận một Future **không bao giờ done**, gây nguy cơ `get()` chờ mãi. Không chọn discard policy cho công việc cần acknowledgment chắc chắn.

Để theo dõi số task **được nhận, bị reject, hoàn thành, thất bại và bị hủy**, cần instrument cả **admission path** và **outcome/completion path**, không chỉ after hook.

## 11. Exception bên trong chính các hook nguy hiểm thế nào?

### `beforeExecute` ném exception

```java
@Override
protected void beforeExecute(Thread t, Runnable r) {
    super.beforeExecute(t, r);
    throw new IllegalStateException("hook failed before task");
}
```

Đây là **đoạn minh họa lỗi**, không nên đưa vào production. Khi before hook ném, task có thể không được chạy và `afterExecute` cũng không được gọi. Một Future của task bị bỏ qua có thể không bao giờ chuyển sang done nếu không có cơ chế fail/cleanup bổ sung. Worker có thể kết thúc bất thường.

Do đó hook chỉ nên làm việc **nhanh, bounded và exception-safe**. Không nên đưa logic khởi tạo bất định, truy vấn network hoặc parse dữ liệu bên ngoài có thể ném exception không được bắt vào `beforeExecute`.

### `afterExecute` ném exception

Nếu after hook ném, worker có thể kết thúc bất thường dù logic task đã chạy xong. Việc này làm nhiễu métrics, log hoặc vòng đời worker; pool có thể tạo replacement worker khi cần. **Không cho logging/metrics throw ra ngoài hook**. Nếu instrumentation thất bại, nên xử lý/ghi nhận theo một kênh an toàn, giới hạn thay vì làm hỏng executor.

### Không chặn executor bằng synchronous logging

Một hook gọi HTTP endpoint hoặc ghi file đồng bộ chậm trong mỗi task khiến **worker bị chiếm dụng**. Điều này có thể tăng queue wait time, gây rejection, thậm chí tạo vòng đợi nếu destination logging cũng dùng cùng pool.

Tốt hơn:

- Ghi metric đơn giản bằng counters hoặc công cụ telemetry nonblocking/bounded.
- Dùng logging có cấu hình queue/batching đúng; kiểm soát chính sách khi log backend đầy.
- Không đưa token, password, payload nhạy cảm hoặc exception message không lọc vào log.
- Phân biệt errors thật với cancellations có chủ đích để không tạo alert storm.
- Ghi event id/task id để biết lỗi thuộc công việc nào, thay vì chỉ class name như demo.

## 12. Thiết kế metrics trước–sau task

Hook thường hữu ích cho:

1. Đếm số lần **worker bắt đầu task** (`beforeExecute`).
2. Đo **thời gian thực thi trên worker** đến khi `afterExecute` được gọi.
3. Đếm outcome thành công, thất bại và hủy.
4. Thu thập thread name, queue depth, active worker count.
5. Dọn `ThreadLocal`/context được thiết lập cho task.
6. Thông báo theo dõi những trường hợp worker bất thường.

### Đo elapsed time bằng monotonic clock

Một pattern minh họa:

```java
// Thành viên subclass ThreadPoolExecutor:
private final ThreadLocal<Long> startedNanos = new ThreadLocal<>();

@Override
protected void beforeExecute(Thread thread, Runnable task) {
    super.beforeExecute(thread, task);
    startedNanos.set(System.nanoTime());
}

@Override
protected void afterExecute(Runnable task, Throwable error) {
    try {
        Long start = startedNanos.get();
        if (start != null) {
            long durationNanos = System.nanoTime() - start;
            observeDuration(durationNanos);
        }
        // Có thể phân tích Throwable/Future outcome tại đây.
    } finally {
        startedNanos.remove();
        super.afterExecute(task, error);
    }
}
```

Đây là **code minh họa**, cần `observeDuration(long)` xử lý nhanh, không ném và một subclass đã cấu hình. `System.nanoTime()` thích hợp đo **khoảng thời gian**, không phải timestamp tường thực. Nếu `beforeExecute` xảy ra lỗi trước khi hoàn tất, `afterExecute` có thể không chạy nên đường cleanup riêng cần xem xét.

**Ý nghĩa của metric:** khoảng from-before to after là thời gian task chạy trên worker (và overhead nhỏ của hook), **không tính thời gian task chờ trong executor queue trước khi worker lấy**. Muốn đo queue wait, phải ghi thời gian enqueue/submit và liên kết nó đến Runnable được worker thực thi, thường qua decorator/wrapper hoặc instrumentation của admission path.

### ThreadLocal cleanup

`ThreadPoolExecutor` tái sử dụng platform worker threads. Nếu một task để lại `ThreadLocal`, task sau chạy trên cùng worker có thể nhìn thấy context cũ. Dọn `ThreadLocal.remove()` trong `afterExecute` là một công cụ hữu ích, nhưng phải hiểu:

- Chỉ dọn những key/context mà component **thực sự sở hữu**.
- Hook không được gọi nếu task chạy bên ngoài worker qua một handler như `CallerRunsPolicy`.
- Hook không được gọi nếu `beforeExecute` ném exception.
- Nếu cần cleanup **bất kể đường chạy**, một wrapper per-task dùng `try/finally` quanh logic của chính task thường đáng tin hơn hook pool-level.
- Nếu dùng context tracing trong async tasks, phải có quy tắc truyền context qua task boundary, không kỳ vọng ThreadLocal tự theo request.

## 13. Cancellation, interruption và kết quả Future

Một `Future` có thể có nhiều trạng thái outcome:

```text
      NEW / running
         |        \
   completed       cancel(true/false)
      /   \              |
  value   failure       cancelled
           |               |
    get throws            get throws
 ExecutionException    CancellationException
```

Đây là sơ đồ khái niệm; trạng thái nội bộ cụ thể của FutureTask/JDK chi tiết hơn.

### `CancellationException`

Nếu `Future.cancel(...)` thành công và caller gọi `get()`, Future ném `CancellationException`. Trong hook, điều này không nên bị gộp bừa thành task failure do business logic; có thể là hủy hợp lệ khi đóng service.

### `InterruptedException`

Với `get()`, thread đang chờ có thể bị interrupt và nhận `InterruptedException`. Nếu hook catch, khôi phục flag bằng `Thread.currentThread().interrupt()` nếu không propagate, và tránh đổi status theo cách khiến worker vẫn phải chạy task tiếp mà không biết mình bị interrupt.

**Chú ý:** `future.get()` sau `future.isDone()` trên `FutureTask` chuẩn không chờ task hoàn thành nữa, nhưng vẫn có signature `throws InterruptedException` và những interface implementations khác nhau. Cần xử lý exception theo API chứ không bỏ catch vì nghĩ “đã done thì không bao giờ exception”.

### `cancel(true)` không phải kill chắc chắn

`cancel(true)` thường yêu cầu interrupt thread đang chạy task. Task đang thực hiện I/O không interruptible hoặc cố tình bỏ qua interrupt có thể tiếp tục. Future có thể ở trạng thái canceled trong khi side effect đang tiếp diễn; đánh dấu cancellation không bảo đảm transaction đã rollback hay thread đã ngừng ngay.

### `isDone()` không đồng nghĩa thành công

`isDone()` true với success, failure và cancel. Để phát hiện failure của task submit, không thể chỉ viết:

```java
if (future.isDone()) {
    metrics.success(); // Sai nếu completed exceptionally hoặc cancelled.
}
```

Đây là đoạn **minh họa sai**. Cần phân loại outcome bằng `get()` sau done hoặc một kênh result/callback phù hợp. Đặc biệt, khi `Future.get()` ném `ExecutionException`, **nguyên nhân thật nằm ở `getCause()`**.

## 14. afterExecute có thể làm thay đổi quan sát của task như thế nào?

Một số tác động của instrumentation lên hệ thống:

- **Latency:** xử lý hook lâu làm worker chậm nhận task kế tiếp.
- **Ordering:** logging đồng bộ trong hook có thể làm thread khác hoàn thành trước, thay đổi thứ tự quan sát.
- **Contention:** metrics dùng cùng monitor/lock cho mọi workers có thể trở thành bottleneck.
- **Memory:** giữ reference đến toàn bộ `Runnable`, payload hoặc stack trace trong collection không giới hạn có thể gây memory leak.
- **Privacy/security:** log exception message có thể chứa query strings, token hoặc thông tin người dùng; phải lọc theo chính sách bảo mật.
- **Lifecycle:** hooks ném exception làm worker kết thúc và pool phải xử lý replacement.
- **Backpressure:** nếu log pipeline quá tải, hook cố đẩy log vào queue bounded bằng `put()` có thể block worker, lan nghẽn ngược vào executor.

Do đó, hook nên **observability-oriented**, ít side effect, không làm thay đổi business outcome. Nếu cần retry/transaction của task thì xây trong layer quản lý công việc, không nhét logic retry tùy tiện vào `afterExecute`.

## 15. Ưu tiên wrapper per-task trong trường hợp nào?

Override `ThreadPoolExecutor` là giải pháp hệ thống cho **mọi task đi qua worker** của một pool. Nhưng không phải framework hay ứng dụng nào cũng kiểm soát được class pool hoặc bảo đảm mọi execution path đi qua hooks.

Trong nhiều trường hợp, một **decorator/wrapper Runnable** rõ ràng hơn:

```java
static Runnable observed(Runnable task) {
    return () -> {
        long started = System.nanoTime();
        try {
            task.run();
        } catch (RuntimeException | Error e) {
            recordFailure(e);
            throw e;
        } finally {
            recordDuration(System.nanoTime() - started);
            cleanupContext();
        }
    };
}
```

Đây là **static method minh họa**; `recordFailure`, `recordDuration` và `cleanupContext` được khai báo bên ngoài. Các method instrumentation cũng phải exception-safe nếu không muốn che mất lỗi gốc.

Ưu điểm:

- Vòng `try/finally` gắn trực tiếp với logic task thay vì phụ thuộc hook.
- Có thể áp dụng cho executor bất kỳ nếu mọi task đều được wrap.
- Nếu task chạy bằng `CallerRunsPolicy` trong caller, wrapper vẫn tự đo/cleanup.
- Có thể định nghĩa rõ context propagation, correlation id và failure policy.

Giới hạn: nếu task bị **reject trước khi chạy**, wrapper cũng không chạy; cần xử lý rejection ngay lúc submit. Với `Callable`, cần decorator tương tự trả giá trị và rethrow exception.

### Exception trong wrapper khi dùng submit

Nếu wrapper ném exception, `FutureTask` do submit tạo vẫn sẽ **bắt và lưu** exception; caller phải quan sát Future nếu cần biết task thất bại. Wrapper log giúp nhìn thấy lỗi sớm, nhưng không thay thế completion contract.

## 16. Phân biệt các lớp lỗi của executor

Không phải mọi exception quanh một executor đều là lỗi bên trong `task.run()`:

| Nguồn lỗi | Vị trí phát sinh | Hook có thấy không? |
|---|---|---|
| Rejection do pool bão hòa/shutdown | Lời gọi `execute/submit` | Thường **không**, task không được worker chạy |
| Lỗi ngay trong `beforeExecute` | Worker hook trước task | `afterExecute` thường không gọi cho task đó |
| Throwable thoát khỏi Runnable trực tiếp | `task.run()` trên worker | `afterExecute` có thể nhận qua `t` |
| Throwable của Callable qua `submit` | Được `FutureTask` lưu | `t` thường null; xem `Future.get()` |
| Hủy task trước khi worker nhận | `Future.cancel`, có thể loại khỏi queue | Có thể không có hook |
| Lỗi logging/metrics trong `afterExecute` | Hook code | Là lỗi instrumentation, có thể làm worker kết thúc |
| Uncaught exception của worker | Thread-level error handling | Có thể đến `UncaughtExceptionHandler` khi không bị FutureTask bắt |
| Timeout của `Future.get(timeout)` | Thread gọi `get` | **Không tự là lỗi task**, task có thể vẫn chạy |
| External side effect thất bại sau task outcome | Hệ thống ngoài JVM | Phải có protocol xác nhận/transaction riêng |

Để có error reporting đầy đủ, cần tối thiểu:

- Catch/reject metrics ở **admission/submission**.
- Task outcome qua `Future`, wrapper hoặc `afterExecute` thích hợp.
- Uncaught exception handler/centralized error reporting ở worker level.
- Cancellation/timeout metrics tách biệt.
- Application-level acknowledgment cho side effect/commit nếu yêu cầu.

Một đơn vị “completed tasks” từ pool không mặc định đồng nghĩa business success. `ThreadPoolExecutor.getCompletedTaskCount()` phản ánh task đã hoàn thành ở mức executor, kể cả khi logic task được FutureTask ghi nhận là thất bại.

## 17. ThreadFactory và UncaughtExceptionHandler

`ThreadFactory` có thể tạo worker với tên và handler nhất quán:

```java
ThreadFactory factory = runnable -> {
    Thread worker = new Thread(runnable, "business-worker");
    worker.setUncaughtExceptionHandler((thread, error) -> {
        reportUncaught(thread.getName(), error);
    });
    return worker;
};
```

Đây là đoạn code trong method cần import `java.util.concurrent.ThreadFactory` và method `reportUncaught`. Hàm báo lỗi không nên ném exception hoặc block vô hạn.

**Cần phân biệt:**

- Lỗi unchecked thoát khỏi `Runnable.run()` khi dùng `execute` có thể đi tới thread uncaught handler.
- Lỗi của `Callable.call()` được `FutureTask` bắt khi dùng `submit` **không thoát khỏi worker.run()`**, nên uncaught handler thường **không nhận lỗi đó**.
- `afterExecute` cho phép theo dõi task ở mức pool worker, nhưng cần kiểm tra Future như đã trình bày.
- Một worker chết do unchecked exception có thể được pool tạo worker khác để tiếp tục xử lý task; việc thay thế không làm side effect trước lỗi được rollback.

Trong demo chính, handler rỗng chỉ phục vụ **kết quả stdout kiểm chứng**, không phải khuyến nghị vận hành. Trong production, cần log/alert/metrics phù hợp cho uncaught exceptions.

## 18. Liveness và tránh deadlock khi thu lỗi

Không nên trong `afterExecute` thực hiện các thao tác như:

```java
// Mô tả nguy cơ: hook chạy trên worker của chính pool.
Future<?> next = pool.submit(() -> sendReport());
next.get(); // Có thể đợi task cần chính worker vừa bị chiếm bởi hook.
```

Đây là **đoạn code minh họa nguy hiểm**, pool, `sendReport()` và checked exceptions cần ngữ cảnh ngoài. Với single-thread pool, hook đang giữ worker duy nhất và chờ task mới xếp hàng; task mới không thể bắt đầu, tạo **thread starvation deadlock**.

Tương tự, trong `afterExecute` gọi `BlockingQueue.put` lên queue đã đầy mà consumer phải chạy trên chính pool này có thể treo. Hãy dùng kênh telemetry độc lập, không blocking hoặc có deadline/failure policy, không tạo vòng phụ thuộc.

Nếu hook gọi `Future.get()` trên **chính task vừa chạy và FutureTask đã done**, thao tác đó không chờ một task khác, nên không gây kiểu deadlock này. Đây là khác biệt giữa “đọc outcome của Future đã hoàn tất” và “submit một task mới rồi chờ nó”.

## 19. Java Memory Model và mối quan hệ completion

Executor Framework có memory consistency guarantees theo tài liệu `java.util.concurrent`:

- Hành động trong thread trước khi gửi `Runnable` cho `Executor.execute` xảy ra trước những hành động của task đó theo *happens-before*.
- Với `ExecutorService`, hành động trước khi submit task *happen-before* hành động trong task; hành động trong task *happen-before* hành động ở caller **sau khi lấy kết quả qua `Future.get()`** theo contract.
- `CountDownLatch` của demo tạo ranh giới HB cho việc main quan sát trạng thái hook trước khi in.
- Các atomic variables dùng để lưu counters/outcomes có memory semantics riêng theo API.

Nhưng cần phân biệt:

1. `Future.get()` làm caller thấy kết quả task đã hoàn tất, **không tự chờ mọi hook instrumentation hoàn tất**.
2. `afterExecute` nhận `Throwable` không có nghĩa nó được phép đọc những mutable objects của caller mà không có giao thức ownership/synchronization thích hợp.
3. Nếu nhiều tasks cùng sửa `HashMap` hoặc biến `int` thường mà không có đồng bộ, việc main đợi Futures **không sửa được data race/lost update giữa các tasks**.
4. Kết quả task được công bố đúng trong JVM không đồng nghĩa transaction database đã commit hoặc việc gửi email đã thực hiện exactly once.

Thiết kế an toàn vẫn cần state confinement, immutable objects, `synchronized`/`Lock` hoặc concurrent collections/atomic operations tương ứng với invariant.

## 20. Kiểm thử hook, submit failure và cancellation

Một chiến lược kiểm thử chặt chẽ:

1. **Success test:** task chạy bình thường, `beforeExecute`/`afterExecute` được gọi, Future.get trả kết quả, không ghi failure.
2. **Direct execute failure:** Runnable ném `IllegalStateException`, hook thấy `t` và uncaught handler có thể nhận throwable.
3. **Submit Callable failure:** Callable ném `IllegalArgumentException`, hook `t == null` nhưng Future.get ném `ExecutionException` có cause đúng.
4. **Submit Runnable failure:** Runnable do submit bọc trong FutureTask, outcome cần phân tích như Callable failure.
5. **Cancellation:** hủy Future trước/khi chạy, phân biệt cancellation với task failure; không giả định hook luôn được gọi nếu task bị remove trước execution.
6. **Rejection:** cấu hình pool có queue bounded, giữ worker bận bằng latch và thử submit quá capacity; kiểm tra handler/rejection metric.
7. **Hook itself fails:** trong test đặc biệt xác minh before hook exception có thể làm mất after hook, rồi sửa instrument để exception-safe. Không đưa hook cố ý ném vào workload production.
8. **Pool shutdown:** nộp task khi pool đã shutdown; rejection được xử lý ở caller, không dựa vào after hook.
9. **ThreadLocal cleanup:** chạy hai task nối tiếp trên cùng worker, xác minh context task đầu không rò sang task sau.
10. **Instrumented latency:** load test queue depth, task duration, admission latency và logging overhead; hook không làm throughput/latency vượt SLA.

### Kiểm thử race một cách xác định

Dùng `CountDownLatch` hoặc `CyclicBarrier` để tạo checkpoint, thay vì `Thread.sleep()` và mong scheduler chạy theo thứ tự mong muốn. Trong demo, `Future.get()` xác nhận logic task, còn `completedHooks.await(...)` xác nhận instrumentation đã xử lý cả hai task. Hai mốc được phân biệt rõ để test không bị flaky.

### Kiểm tra kết quả lỗi đúng tầng

Đối với `ExecutionException`:

```java
try {
    future.get();
} catch (ExecutionException e) {
    Throwable root = e.getCause();
    // report(root), trả lỗi hoặc quyết định retry theo contract
}
```

Đây là đoạn minh họa trong method có `future` là Future; còn cần xử lý/khai báo `InterruptedException`. Không nên catch `ExecutionException` rồi chỉ ghi “future failed” mà mất root cause. Cũng không retry tự động khi task có side effect không idempotent.

## 21. Các hiểu lầm phổ biến

1. **“`afterExecute` luôn nhận Throwable nếu task do submit ném exception.”** Sai; `FutureTask` thường lưu lỗi, để `t==null`.
2. **“`t==null` nghĩa là business task chắc chắn thành công.”** Sai; Future có thể completed exceptionally hoặc cancelled.
3. **“`beforeExecute` và `afterExecute` chạy cho mọi task đã nộp.”** Sai; reject, discard, task chưa chạy, caller-runs và hook failure có thể bỏ qua đường worker.
4. **“`Future.isDone()` nghĩa là success.”** Sai; isDone bao gồm fail/cancel.
5. **“`Future.get()` ném đúng exception của task trực tiếp.”** Thường ném `ExecutionException` bọc cause; cancellation dùng `CancellationException`.
6. **“Chỉ cần UncaughtExceptionHandler là bắt được mọi submit error.”** Sai; FutureTask thường bắt exception trước khi thoát thread.
7. **“`execute` luôn đưa lỗi vào afterExecute.t.”** Không nhất thiết; Runnable tự bắt exception, FutureTask được gửi qua execute hoặc wrapper khác có thể return bình thường.
8. **“`afterExecute` gọi Future.get là luôn an toàn.”** Phải kiểm tra loại và completed state; tuyệt đối tránh get của một task khác chưa done trong worker hook.
9. **“Đặt logging network trong afterExecute không ảnh hưởng hiệu năng.”** Sai; hook chạy trong worker và có thể block throughput.
10. **“Có hook thì có thể bỏ Future.get ở caller.”** Không nếu caller cần result/completion/cancellation theo business contract.
11. **“Future.get đợi cả afterExecute.”** Không được mặc định; FutureTask có thể done trước khi hook xong.
12. **“Throwable ở afterExecute là mọi lỗi của executor.”** Sai; rejection, before-hook failure và external side effects thuộc đường khác.
13. **“Cancel Future tức task dừng ngay.”** Không; cancellation/interrupt phải được task hỗ trợ.
14. **“ThreadPoolExecutor.getCompletedTaskCount là success count.”** Sai; task completed exceptionally vẫn có thể được tính hoàn tất ở mức pool.
15. **“Hook được gọi trên thread submit.”** Thường hook chạy trên worker; riêng caller-runs có thể chạy task trong caller nhưng không qua pool hook.
16. **“Override hooks có thể thỏa sức throw để phát hiện lỗi.”** Sai; exception từ hook làm hỏng worker lifecycle.
17. **“Log mọi exception message là an toàn.”** Không; cần tránh lộ secrets/PII và giới hạn kích thước payload.
18. **“Cùng ThreadLocal key thì mỗi task có context riêng.”** Sai; pooled worker tái sử dụng, phải cleanup và propagate context có kiểm soát.
19. **“Hook ghi nhận lỗi rồi có nghĩa side effect được rollback.”** Không; task failure và external transaction là hai hợp đồng độc lập.
20. **“Không thấy log nghĩa là không có lỗi.”** Không; kiểm tra Future, rejection, task wrapper và error channel.

## 22. Khi nào nên override ThreadPoolExecutor?

**Phù hợp khi:**

- Bạn sở hữu class `ThreadPoolExecutor` và muốn áp dụng instrumentation chung cho **mọi task do worker của pool chạy**.
- Muốn đo thời gian chạy trên worker, queue/active metrics, tagging hoặc dọn ThreadLocal được tạo bởi pool.
- Có thể đảm bảo hook nhanh, exception-safe, không block và không thay đổi business semantics.
- Có chính sách outcome rõ ràng cho `Future`, cancellations và Throwable trực tiếp.

**Không nên coi hook là điểm duy nhất khi:**

- Nguồn task có thể chạy qua nhiều loại `Executor` khác nhau.
- Rejection, caller-runs, tasks run directly hoặc delayed tasks phải được theo dõi một cách đồng nhất.
- Cần bao phủ toàn bộ lifecycle từ submission đến outcome, không chỉ “task đã qua worker”.
- Task có side effect external cần giao dịch, retry, idempotency hay audit bền vững.
- Cần truyền correlation context qua các asynchronous boundaries; wrapper per-task có thể rõ ràng hơn.

Một giải pháp observability hoàn chỉnh thường kết hợp **submission wrapper**, **rejection handler**, **Future/callback handling**, metrics mức pool, error handler và domain-specific result tracking. Hook là một điểm mở rộng hữu ích, không phải toàn bộ kiến trúc quản lý lỗi.

## 23. Câu hỏi tự kiểm tra và đáp án

**Câu 1.** `afterExecute(r, t)` nhận `t == null` sau task `submit` ném `IllegalArgumentException`. Có gì bất thường không?  
**Đáp án:** Không. `submit` thường bọc task bằng `FutureTask`, lưu Throwable bên trong Future; `run()` của wrapper trở về bình thường nên `t` null.

**Câu 2.** Muốn tìm ngoại lệ gốc của `Future` bị failed, xử lý gì?  
**Đáp án:** `future.get()` ném `ExecutionException`; gọi `e.getCause()` để lấy throwable gốc.

**Câu 3.** Trong `afterExecute`, khi nào được cân nhắc gọi `Future.get()`?  
**Đáp án:** Khi `r instanceof Future<?>` và Future đã done, để không block worker vô hạn; bắt `ExecutionException`, `CancellationException` và `InterruptedException` đúng.

**Câu 4.** `afterExecute` có luôn chạy nếu `beforeExecute` tự ném RuntimeException không?  
**Đáp án:** Không; theo worker loop của ThreadPoolExecutor, before hook ném trước task.run khiến after hook không được gọi cho task đó.

**Câu 5.** Task bị reject bởi `AbortPolicy` có đi qua `beforeExecute` không?  
**Đáp án:** Không. Nó không được worker thực thi; caller thường nhận `RejectedExecutionException` tại submit/execute.

**Câu 6.** Một task dùng `execute(new FutureTask<>(...))` ném ngoại lệ bên trong. `afterExecute.t` có chắc khác null không?  
**Đáp án:** Không. FutureTask.run bắt và lưu lỗi dù được gửi bằng execute. Điều quan trọng là Runnable wrapper có để lỗi thoát khỏi run hay không.

**Câu 7.** Tại sao test phải chờ latch hook riêng, dù đã `future.get()`?  
**Đáp án:** FutureTask có thể done trước khi after hook hoàn tất; latch tạo ranh giới đã chạy xong instrumentation.

**Câu 8.** `CallerRunsPolicy` khi pool bão hòa và chưa shutdown có chạy `beforeExecute` của ThreadPoolExecutor không?  
**Đáp án:** Không nên trông chờ điều đó. Task chạy trong thread caller qua handler, không phải worker loop của pool.

**Câu 9.** `shutdownNow` trả ra task chưa thực thi; có `afterExecute` cho task đó không?  
**Đáp án:** Không, vì worker chưa gọi `task.run()`. Completion/audit phải xử lý những task này riêng.

**Câu 10.** Vì sao gọi `pool.submit(...).get()` ngay bên trong after hook của **cùng single-thread pool** có thể deadlock?  
**Đáp án:** Hook giữ worker duy nhất và chờ một task mới đang xếp hàng, task đó không có worker để chạy.

**Câu 11.** `Future.isDone() == true` có đủ để tăng success counter không?  
**Đáp án:** Không. Future có thể failure hoặc cancellation. Phải đọc outcome đúng hoặc theo result contract.

**Câu 12.** Khi một exception được log trong after hook, có nghĩa task chắc chắn được retry an toàn không?  
**Đáp án:** Không. Log chỉ quan sát lỗi; retry có thể lặp side effect nếu không có idempotency/transaction.

**Câu 13.** Tại sao hooks nên tránh network I/O?  
**Đáp án:** Chúng chạy trên worker, block lâu khiến worker không nhận task kế tiếp, làm giảm throughput và tăng queue pressure.

**Câu 14.** ThreadLocal context được set trong `beforeExecute` có chắc được remove bằng `afterExecute` trong mọi tình huống không?  
**Đáp án:** Không; nếu before hook ném hoặc task được chạy ngoài worker loop, after hook không làm cleanup. Có thể cần wrapper `try/finally` riêng.

**Câu 15.** Nếu chỉ có `ExecutorService` interface và không kiểm soát implementation, có thể override `afterExecute` trực tiếp không?  
**Đáp án:** Không. Đó là hook của `ThreadPoolExecutor`, không phải method trong `ExecutorService` interface. Dùng wrapper/decorator hoặc kiểm soát custom pool.

## 24. Tài liệu tham khảo chính thức

- [Java SE 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): phần **Hook methods**, `beforeExecute`, `afterExecute`, `terminated`; JavaDoc đặc biệt lưu ý `submit` và `FutureTask`.
- [Java SE 17 — FutureTask](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/FutureTask.html): `run()`, lưu result/exception, `done()`, cancellation và trạng thái.
- [Java SE 17 — AbstractExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/AbstractExecutorService.html): `submit` và `newTaskFor`.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): `submit`, lifecycle, completion và memory consistency.
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `get`, `isDone`, `cancel`, `ExecutionException`, `CancellationException`.
- [Java SE 17 — Executor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html): `execute` và memory consistency.
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): phase synchronization và memory consistency.
- [Java SE 17 — Thread.UncaughtExceptionHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.UncaughtExceptionHandler.html): uncaught errors của thread.
- [Java Language Specification `17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): happens-before, thread lifecycle và memory model.

**Tóm tắt cần nhớ:** `beforeExecute` và `afterExecute` là hooks **của worker loop `ThreadPoolExecutor`**. `afterExecute` thấy throwable **thoát khỏi `Runnable.run()`**, chứ không tự giải mã mọi lỗi đã được `FutureTask` lưu. Khi dùng `submit()`, hãy kiểm tra `Future<?>` đã done và đọc outcome qua `get()`, phân loại success/failure/cancel; đồng thời xử lý rejection, lifecycle, uncaught exceptions và instrumentation không được làm nghẽn worker.