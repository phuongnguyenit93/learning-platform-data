# Cancellation và trạng thái của Future trong Java

> **Trọng tâm:** `Future<V>` là **handle của kết quả một tác vụ bất đồng bộ**, cho phép hỏi đã hoàn tất chưa, chờ kết quả, và **yêu cầu hủy**. Cần phân biệt rõ **kết quả Future** với **thread thực sự đã dừng**: `isDone() == true` có thể do thành công, lỗi hoặc hủy; `cancel(true)` chỉ *cố gắng interrupt* task đang chạy khi implementation hỗ trợ; `get(timeout, unit)` chỉ giới hạn **thời gian đợi của caller**, không tự hủy task. Với `ScheduledFuture`, phải tính cả trạng thái chờ lịch, periodic execution và chính sách xóa task đã hủy.

Bài nằm trong nhóm **Future & Scheduling** của Java concurrency nói chung. Mọi ví dụ độc lập dưới đây dùng Java SE 17+ (`ExecutorService`, `Future`, `FutureTask`, `ScheduledExecutorService` và `CompletableFuture` khi so sánh). Không bàn đến cơ chế của Spring.

## 1. Future đại diện cho điều gì?

Khi một thread gọi `ExecutorService.submit(Callable<V>)`, executor trả về một `Future<V>`. Future có thể được tạo **trước khi worker thực sự chạy**. Nó biểu thị khả năng nhận kết quả/tình trạng hoàn tất trong tương lai, không phải chính thread và không phải một lời hứa “task chắc chắn sẽ thành công”.

~~~text
Thread gọi submit()                Executor/worker
-------------------                ---------------
Future<V> f = submit(task) -----> [ task có thể đang xếp hàng ]
       |                                  |
       | f.isDone() = false                v
       |                              [ task bắt đầu ]
       |                                  |
       |                       +----------+-----------+
       |                       |          |           |
       |                    success      failure    cancellation
       |                       |          |           |
       +---- f.get() <---------+----------+-----------+
              result / ExecutionException / CancellationException
~~~

`Future` không cung cấp một enum trạng thái `NEW/QUEUED/RUNNING/SUCCEEDED` trong interface Java 17. Những tên này chỉ là **mô hình tư duy**, không phải API. Hai method chủ chốt để hỏi trạng thái là `isDone()` và `isCancelled()`; để biết kết quả hoặc nguyên nhân lỗi, caller sử dụng `get()` và xử lý exception.

### Những phương thức nền tảng

| API | Ý nghĩa và điểm cần nhớ |
| --- | --- |
| `boolean isDone()` | `true` nếu Future đã kết thúc theo hợp đồng: **bình thường, thất bại hoặc hủy**. Không có nghĩa task thành công. |
| `boolean isCancelled()` | `true` nếu Future đã bị hủy trước khi hoàn tất bình thường. Không đồng nghĩa thread đã dừng hẳn. |
| `V get()` | Đợi nếu cần; trả kết quả hoặc ném exception tương ứng. Không đặt deadline chờ. |
| `V get(long timeout, TimeUnit unit)` | Đợi tối đa khoảng thời gian chỉ định. `TimeoutException` **không tự hủy** task. |
| `boolean cancel(boolean mayInterruptIfRunning)` | Yêu cầu hủy: nếu chưa chạy thì ngăn chạy; nếu đang chạy thì tham số quyết định có cố interrupt hay không. Kết quả có thể phụ thuộc timing/implementation. |

`Future<V>` là interface, các implementation như `FutureTask`, `ScheduledFuture`, `CompletableFuture` có những khác biệt cụ thể. Không suy diễn mọi implementation phản ứng giống nhau với interruption hoặc cancellation.

## 2. Bảng trạng thái quan sát được qua Future

Hãy phân biệt trạng thái nội bộ giả định của task và **điều có thể kết luận từ API**:

| Tình huống | `isDone()` | `isCancelled()` | `get()` |
| --- | --- | --- | --- |
| Chưa hoàn thành: đang xếp hàng hoặc đang chạy | `false` | Thường `false` | Có thể **block** |
| Hoàn tất bình thường | `true` | `false` | Trả giá trị (có thể `null` với `Runnable`) |
| Hoàn tất do exception trong task | `true` | `false` | Ném `ExecutionException` (lấy nguyên nhân qua `getCause()`) |
| Đã chuyển sang cancelled | `true` | `true` | Ném `CancellationException` |
| Caller đợi quá hạn nhưng task vẫn còn chạy | Có thể vẫn `false` | Có thể vẫn `false` | `get(timeout)` ném `TimeoutException` tại lần gọi đó; các lần gọi sau vẫn có thể thành công |

Bảng là các tình huống điển hình, không phải một “snapshot atomically read” của cả hai flag và kết quả khi task đang hoàn tất cạnh tranh. Nếu đọc `isDone` rồi đọc `isCancelled` ở hai thời điểm, task có thể thay đổi trạng thái giữa chúng. **Đừng viết logic cần phân biệt chính xác nhiều tình huống chỉ bằng polling hai flag.** Khi cần kết quả cuối cùng, dùng `get()`/`get(timeout)` cùng xử lý exception.

### Phân biệt ba đường kết thúc

1. **Normal completion:** computation trả giá trị; `get()` trả đúng giá trị đó.
2. **Exceptional completion:** computation ném exception; với Future từ `submit`, `get()` ném `ExecutionException` bao quanh nguyên nhân gốc.
3. **Cancellation:** Future bị hủy thành công; `get()` ném `CancellationException`, không trả kết quả bình thường, ngay cả khi thân task đã thực hiện một số side effects.

Một exception trong body `Callable` **không** khiến `isCancelled()` thành true. Nó là failure, không phải cancellation. Tương tự, một Future bị cancel không có nghĩa business transaction được rollback.

## 3. Ví dụ 1 — thành công, lỗi và trạng thái sau khi hoàn tất

Tạo tệp `FutureOutcomes.java` (Java 17+):

~~~java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class FutureOutcomes {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<Integer> successful = pool.submit(() -> 6 * 7);
            Future<Integer> failed = pool.submit(() -> {
                throw new IllegalStateException("broken");
            });

            int value = successful.get(); // Đợi thành công.
            System.out.println("result = " + value);
            System.out.println("success done = " + successful.isDone());
            System.out.println("success cancelled = "
                    + successful.isCancelled());

            try {
                failed.get();
            } catch (ExecutionException ex) {
                System.out.println("failure cause = "
                        + ex.getCause().getClass().getSimpleName());
            }

            System.out.println("failure done = " + failed.isDone());
            System.out.println("failure cancelled = "
                    + failed.isCancelled());
            System.out.println("cancel completed = "
                    + successful.cancel(true));
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac FutureOutcomes.java
java FutureOutcomes
~~~

Đầu ra xác định trên đường chạy bình thường:

~~~text
result = 42
success done = true
success cancelled = false
failure cause = IllegalStateException
failure done = true
failure cancelled = false
cancel completed = false
~~~

Tại lúc in, `successful.get()` và `failed.get()` đã xác nhận cả hai Future kết thúc. Một Future thất bại vẫn có `isDone() == true` và `isCancelled() == false`. `cancel(true)` **không thể hủy lại một Future đã hoàn tất bình thường**.

`get()` còn cung cấp quan hệ *happens-before* từ hành động của computation tới hành động sau khi caller nhận completion qua `get()`. Điều đó giúp lấy kết quả công việc an toàn, nhưng **không biến mọi object mutable được chia sẻ ngoài Future thành thread-safe**.

## 4. `cancel(false)` và `cancel(true)` khác nhau thế nào?

`cancel(mayInterruptIfRunning)` là yêu cầu đổi trạng thái Future và, tùy tình huống, ngăn hoặc cố dừng computation.

### Trước khi task chạy

Nếu task vẫn chờ trong executor queue và một cancellation thành công, task tương ứng **không nên được chạy**. Cả `cancel(false)` và `cancel(true)` đều có thể hủy trước khi bắt đầu; tham số interrupt không cần thiết khi chưa có thread thực hiện task.

### Khi task đã bắt đầu

- `cancel(false)`: **không yêu cầu interrupt** worker đang chạy. Một implementation như `FutureTask` có thể chuyển Future sang cancelled trong khi computation **vẫn tiếp tục chạy** cho đến khi tự hoàn tất.
- `cancel(true)`: **cố interrupt** thread đang chạy, khi implementation biết thread đó và có hỗ trợ. Không buộc thread ngừng tức thì; kết quả phụ thuộc code có hợp tác với interruption hay không.
- Với cả hai, nếu Future bị hủy thành công, `isDone()`/`isCancelled()` có thể báo true và `get()` ném `CancellationException` **trước khi thân task thực sự dừng thực thi**.
- Nếu task đã hoàn tất trước `cancel`, cancellation không thay đổi kết quả đã hoàn thành; method thường trả `false`.
- Khi nhiều thread cùng gọi `cancel` trên một Future, kết quả boolean ở mỗi caller có thể khác nhau; sau đó nên kiểm tra `isCancelled()` nếu cần biết final cancellation state.

**Quan trọng:** `cancel` trả `true` là một **kết quả của yêu cầu hủy Future**, không phải bằng chứng mọi side effect của task đã dừng hoặc đã được rollback. Java không có cơ chế an toàn để cưỡng ép dừng một thread bất kỳ tại mọi điểm code.

## 5. Ví dụ 2 — hủy task còn xếp hàng, task không được chạy

Để tránh phụ thuộc scheduler, ta dùng executor **một worker**, chặn worker bằng latch, và hủy task thứ hai khi nó còn chắc chắn trong queue.

Tạo `CancelQueuedFuture.java` (Java 17+):

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class CancelQueuedFuture {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch occupied = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicBoolean ran = new AtomicBoolean(false);

        try {
            pool.execute(() -> {
                occupied.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });

            occupied.await();
            Future<?> pending = pool.submit(() -> ran.set(true));

            boolean acceptedCancel = pending.cancel(false);
            System.out.println("cancel accepted = " + acceptedCancel);
            System.out.println("isDone = " + pending.isDone());
            System.out.println("isCancelled = " + pending.isCancelled());

            try {
                pending.get();
            } catch (CancellationException expected) {
                System.out.println("get = CancellationException");
            }
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }

        System.out.println("task ran = " + ran.get());
    }
}
~~~

Chạy:

~~~bash
javac CancelQueuedFuture.java
java CancelQueuedFuture
~~~

Đầu ra khi không bị interruption ngoài:

~~~text
cancel accepted = true
isDone = true
isCancelled = true
get = CancellationException
task ran = false
~~~

Tại lúc `cancel(false)`, worker duy nhất đang đợi `release`; task thứ hai **chưa thể bắt đầu**. Cancellation của FutureTask do `submit` tạo ngăn phần computation tương ứng chạy. Sau khi nhả latch và shutdown/drain executor, cờ `ran` vẫn false.

**Không kết luận:** Future bị cancelled thì wrapper chắc chắn biến mất khỏi queue ngay. `ThreadPoolExecutor` có thể giữ lại cancelled FutureTask trong queue cho tới khi được dequeue hoặc `purge()`. `ScheduledThreadPoolExecutor` có chính sách remove-on-cancel riêng ở phần sau.

## 6. Ví dụ 3 — `cancel(false)` khi task đang chạy: Future done nhưng worker chưa xong

Đây là khác biệt quan trọng nhất giữa **trạng thái Future** và **thực thi thực tế của task**. Với `FutureTask` trong executor chuẩn, một task đang chạy có thể bị đánh dấu cancelled mà không bị interrupt khi gọi `cancel(false)`.

Tạo `CancelRunningWithoutInterrupt.java` (Java 17+):

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class CancelRunningWithoutInterrupt {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch bodyFinished = new CountDownLatch(1);

        try {
            Future<?> running = pool.submit(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                } finally {
                    bodyFinished.countDown();
                }
            });

            started.await();
            boolean cancelled = running.cancel(false);

            System.out.println("cancel(false) = " + cancelled);
            System.out.println("Future done = " + running.isDone());
            System.out.println("Future cancelled = "
                    + running.isCancelled());
            System.out.println("body finished yet = "
                    + (bodyFinished.getCount() == 0));

            try {
                running.get();
            } catch (CancellationException expected) {
                System.out.println("get = CancellationException");
            }

            release.countDown();
            bodyFinished.await();
            System.out.println("body finished later = "
                    + (bodyFinished.getCount() == 0));
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac CancelRunningWithoutInterrupt.java
java CancelRunningWithoutInterrupt
~~~

Đầu ra với `FutureTask` do executor Java SE 17 tạo:

~~~text
cancel(false) = true
Future done = true
Future cancelled = true
body finished yet = false
get = CancellationException
body finished later = true
~~~

`started.await()` đảm bảo task đã bắt đầu và chưa thể đi tới `bodyFinished.countDown()` khi `release` chưa được mở. `cancel(false)` không interrupt; Future chuyển thành cancelled, nhưng worker vẫn chờ latch. Chỉ khi main mở `release`, task mới tới phần `finally` của body.

**Hệ quả thực tiễn:** Không đóng tài nguyên mà body đang dùng **chỉ vì `future.isDone()` thành true sau cancel**, nếu closure thực sự cần đợi worker ngừng. Muốn xác nhận task đã dừng, cần một completion signal riêng từ thân task, trạng thái executor/task lifecycle thích hợp, hoặc một protocol cancellation/cleanup rõ ràng.

## 7. Interruption là cơ chế hợp tác, không phải dừng cưỡng bức

`Thread.interrupt()` đặt trạng thái interrupt của thread hoặc khiến một số blocking methods đáp ứng bằng `InterruptedException`. Nhiều API như `Thread.sleep`, `BlockingQueue.take`, `CountDownLatch.await`, một số `Future.get` có thể thoát khỏi việc chờ khi bị interrupt.

Đối với đoạn tính toán CPU thuần không blocking, việc đặt interrupt flag **không tự buộc vòng lặp dừng**. Task phải **kiểm tra cờ** hoặc có điểm chờ interruptible và quyết định thoát an toàn.

Mẫu xử lý:

~~~java
// Snippet minh họa bên trong Callable/ Runnable.
try {
    while (!Thread.currentThread().isInterrupted()) {
        doOneUnitOfWork();
    }
} finally {
    releaseOwnedResources();
}
~~~

Nếu công việc có hoạt động blocking, cần catch `InterruptedException` phù hợp:

~~~java
// Snippet khi method không muốn lan truyền InterruptedException.
try {
    queue.take();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt(); // Khôi phục flag.
    return;                              // Không tiếp tục chờ vô hạn.
}
~~~

**Đừng nuốt interruption** bằng một catch rỗng rồi tiếp tục vô tận. Nếu đang viết `Callable` và cho phép truyền exception, thường có thể lan truyền `InterruptedException` để cấp điều phối biết task không hoàn thành bình thường.

### Điều gì xảy ra khi task bỏ qua interrupt?

`cancel(true)` vẫn có thể khiến Future thành cancelled nhưng task không dừng. Chẳng hạn body chạy một vòng lặp vô hạn không kiểm tra interrupt, gọi native/blocking API không interruptible, hoặc catch `InterruptedException` rồi tiếp tục. Không nên dùng `Thread.stop()` như giải pháp: API đã deprecated và nguy hiểm vì có thể phá invariant.

Phải thiết kế **deadline, stop token, IO timeout, checkpoint và cleanup** cho task của mình thay vì tin cancellation của Future đủ để dừng mọi hoạt động.

## 8. Ví dụ 4 — `cancel(true)` đánh thức task đang chờ latch

Tạo `CancelInterruptibleTask.java` (Java 17+):

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class CancelInterruptibleTask {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch neverReleased = new CountDownLatch(1);
        CountDownLatch interruptionObserved = new CountDownLatch(1);

        try {
            Future<?> future = pool.submit(() -> {
                started.countDown();
                try {
                    neverReleased.await();
                } catch (InterruptedException e) {
                    interruptionObserved.countDown();
                    Thread.currentThread().interrupt();
                }
            });

            started.await();
            boolean accepted = future.cancel(true);

            interruptionObserved.await(); // Đợi thân task xác nhận.
            System.out.println("cancel(true) = " + accepted);
            System.out.println("interrupt observed = true");
            System.out.println("isDone = " + future.isDone());
            System.out.println("isCancelled = " + future.isCancelled());

            try {
                future.get();
            } catch (CancellationException expected) {
                System.out.println("get = CancellationException");
            }
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(10, TimeUnit.SECONDS);
        }
    }
}
~~~

Chạy:

~~~bash
javac CancelInterruptibleTask.java
java CancelInterruptibleTask
~~~

Stdout bình thường:

~~~text
cancel(true) = true
interrupt observed = true
isDone = true
isCancelled = true
get = CancellationException
~~~

`started.await()` xác nhận body đã chạy. `future.cancel(true)` khiến executor/FutureTask thử interrupt worker. Dù interrupt đến **trước khi** worker bắt đầu `neverReleased.await()`, cờ interrupt sẽ khiến lần chờ đó ném `InterruptedException`. `interruptionObserved.await()` là tín hiệu từ **chính body** xác nhận nó đã quan sát interrupt, tránh đoán từ thời gian ngủ hoặc chỉ nhìn `isCancelled`.

**Lưu ý:** Trong code thật nên tránh đợi một latch báo interruption **vô hạn** nếu implementation/task có thể không hợp tác; sử dụng timeout và nhánh fail-safe. Demo cố tình chọn task chắc chắn đang/chuẩn bị đợi một primitive interruptible để có output rõ ràng.

## 9. `Future.get(timeout)` không hủy computation

Nếu caller gọi `future.get(100, MILLISECONDS)` và task chưa hoàn tất trước deadline, method ném `TimeoutException`. Future vẫn có thể còn sống và hoàn thành sau đó. Việc caller **không muốn đợi nữa** không đồng nghĩa **task phải dừng**.

### Ví dụ 5 — timeout, rồi task hoàn tất bình thường

Tạo `TimeoutNotCancellation.java` (Java 17+):

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class TimeoutNotCancellation {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<String> future = pool.submit(() -> {
                started.countDown();
                release.await();
                return "done";
            });

            started.await();
            try {
                future.get(50, TimeUnit.MILLISECONDS);
            } catch (TimeoutException expected) {
                System.out.println("wait = TimeoutException");
            }

            System.out.println("cancelled = " + future.isCancelled());
            System.out.println("done before release = " + future.isDone());

            release.countDown();
            System.out.println("result = " + future.get());
            System.out.println("done after = " + future.isDone());
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac TimeoutNotCancellation.java
java TimeoutNotCancellation
~~~

Stdout:

~~~text
wait = TimeoutException
cancelled = false
done before release = false
result = done
done after = true
~~~

Khi main đang đợi, worker chưa thể trả về vì latch chưa mở; timeout là điều chắc chắn. Sau timeout, `isCancelled()` còn false và `isDone()` false. Khi mở latch, `future.get()` nhận `done` bình thường.

**Phân biệt hai timeout:**
- `get(timeout)`: giới hạn **thời gian caller chờ**.
- Deadline/cancellation của task: logic riêng phải yêu cầu dừng hoặc bỏ việc, thường với `cancel`, interrupt, thời hạn I/O và kiểm tra deadline.

### Khi nào cancel sau timeout?

Một pattern có thể phù hợp:

~~~java
// Snippet minh họa trong caller.
try {
    return future.get(timeout, TimeUnit.MILLISECONDS);
} catch (TimeoutException e) {
    future.cancel(true); // Yêu cầu hủy, không bảo đảm dừng tức khắc.
    throw e;
}
~~~

Nhưng không tự động áp dụng cho mọi nghiệp vụ. Một task ghi database hoặc gửi message có thể đã commit side effect trước lúc caller timeout; cancel không rollback. Nếu caller retry, có nguy cơ xử lý trùng. Dùng idempotency key, deadline, transaction boundaries và trạng thái công việc đáng tin cậy ở tầng hệ thống.

## 10. `InterruptedException` của caller khác cancellation của Future

Một caller đang `future.get()` có thể bị thread khác interrupt. Khi đó `get()` ném `InterruptedException`; đây là tín hiệu **thread đợi bị interrupt**, không chứng minh computation đã bị hủy.

~~~java
// Snippet minh họa, method gọi có thể quyết định policy.
try {
    Object value = future.get();
    consume(value);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Quyết định có cancel Future hay chỉ dừng chờ.
}
~~~

Khi xử lý, phải tự hỏi: caller dừng chờ có đồng nghĩa muốn dừng task không? Đôi lúc task là shared computation, các caller khác vẫn cần kết quả — hủy nó chỉ vì một caller bị interrupt là sai chính sách.

Không dùng `Thread.interrupted()` một cách vô ý trong polling vì method static đó **đọc và xóa interrupt status**. `Thread.currentThread().isInterrupted()` chỉ kiểm tra flag, không xóa. Cần biết mình đang muốn giữ hay consume tín hiệu.

## 11. FutureTask: implementation phổ biến và trạng thái nội bộ

`FutureTask<V>` vừa là `Runnable` vừa là `Future<V>`. `ExecutorService.submit` thường tạo một `RunnableFuture` tương đương để executor chạy và caller theo dõi completion. Nó hỗ trợ `run()`, `cancel`, `get`, `isDone`, `isCancelled`; các trạng thái nội bộ là **chi tiết implementation**, không phải hợp đồng chung của `Future`.

Có thể tạo thủ công:

~~~java
// Snippet API, không độc lập.
FutureTask<Integer> task = new FutureTask<>(() -> 42);
new Thread(task).start();
int result = task.get();
~~~

Cần hiểu rằng `FutureTask.cancel(false)` có thể chuyển state sang cancelled trong khi body đang chạy; body tiếp tục thực thi nếu không bị interrupt. Điều này đã được minh họa ở `CancelRunningWithoutInterrupt`.

### `isDone` không phải acknowledgment hoàn tất mọi side effect

Đặc biệt sau một cancel thành công, `isDone() == true` có thể xảy ra **trước khi computation body thực sự trả về**. Không nên đóng file/socket do body sở hữu hay giả định event đã được ghi xong chỉ dựa vào Future status. Cần một completion signal riêng hoặc phối hợp lifecycle của executor/thread mà chương trình sở hữu.

Với `Callable` ném exception nhưng không bị cancel, Future thường hoàn tất ngoại lệ; `isDone()` true, `isCancelled()` false, `get()` ném `ExecutionException`. Một Future completed normally không thể bị cancel ngược về trước.

## 12. ScheduledFuture: chưa đến hạn, đang chạy và periodic task

`ScheduledExecutorService` hỗ trợ `schedule`, `scheduleAtFixedRate` và `scheduleWithFixedDelay`. Kết quả của các lời gọi này là `ScheduledFuture<?>`, mở rộng `Future` với `getDelay` và `compareTo` trong `Delayed`.

Với task **one-shot**:
- Trước thời điểm scheduled, Future có thể chưa done; `get()` có thể đợi đến khi chạy xong.
- Nếu `cancel` thành công trước thời điểm chạy, task không nên được thực thi.
- Khi task chạy và hoàn tất bình thường/lỗi, các quy tắc `Future.get()` tương ứng áp dụng.

Với **periodic task**:
- Một periodic task thành công mỗi lần chạy thường **không có kết quả cuối cùng** theo mỗi chu kỳ; `get()` không trả bình thường chỉ vì một lần thực thi đã xong.
- Future của periodic task thường ở trạng thái not-done **trong khi lịch chạy vẫn được duy trì**.
- Nếu một lần chạy ném exception, các lần tiếp theo theo hợp đồng scheduler có thể bị suppress; Future có thể kết thúc exceptional và `get()` ném `ExecutionException`.
- Khi cancel periodic Future, các lần lập lịch tương lai bị hủy theo hợp đồng, còn lần đang chạy có thể phải hợp tác với interruption nếu cần dừng ngay.
- Shutdown và continuation của periodic task còn phụ thuộc policy của `ScheduledThreadPoolExecutor` (`continueExistingPeriodicTasksAfterShutdownPolicy`, `executeExistingDelayedTasksAfterShutdownPolicy`).

**Đừng định nghĩa “periodic done” là đã chạy một chu kỳ.** Với nhiệm vụ định kỳ cần shutdown, phải quản lý Future đại diện cho toàn chuỗi thực thi và lifecycle của scheduler.

### Không nhầm `getDelay` với runtime hay guaranteed start

`scheduled.getDelay(TimeUnit.MILLISECONDS)` phản ánh thời gian ước lượng tới thời điểm đủ điều kiện chạy theo clock của scheduler. Nó không đảm bảo task đã chạy ngay khi delay bằng 0: worker còn có thể bận, scheduler đang shutdown hoặc có tài nguyên khác hạn chế.

## 13. Ví dụ 6 — hủy task scheduled trước khi tới hạn

Tạo `CancelScheduledFuture.java` (Java 17+):

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class CancelScheduledFuture {
    public static void main(String[] args) throws InterruptedException {
        ScheduledThreadPoolExecutor scheduler =
                new ScheduledThreadPoolExecutor(1);
        scheduler.setRemoveOnCancelPolicy(true);
        AtomicBoolean ran = new AtomicBoolean(false);

        try {
            ScheduledFuture<?> future = scheduler.schedule(
                    () -> ran.set(true), 1, TimeUnit.DAYS);

            boolean cancelled = future.cancel(false);
            System.out.println("cancelled = " + cancelled);
            System.out.println("isDone = " + future.isDone());
            System.out.println("isCancelled = " + future.isCancelled());
            System.out.println("queue entries = "
                    + scheduler.getQueue().size());
            try {
                future.get();
            } catch (CancellationException expected) {
                System.out.println("get = CancellationException");
            }
        } finally {
            scheduler.shutdownNow();
            scheduler.awaitTermination(10, TimeUnit.SECONDS);
        }

        System.out.println("task ran = " + ran.get());
    }
}
~~~

Chạy:

~~~bash
javac CancelScheduledFuture.java
java CancelScheduledFuture
~~~

Đầu ra bình thường:

~~~text
cancelled = true
isDone = true
isCancelled = true
queue entries = 0
get = CancellationException
task ran = false
~~~

Task được lên lịch **một ngày sau**, nên hủy ngay lúc vừa schedule xảy ra trước thời điểm chạy. `setRemoveOnCancelPolicy(true)` khiến task bị hủy được loại **ngay** khỏi work queue của `ScheduledThreadPoolExecutor` thay vì tiếp tục giữ lại tới lúc delay đến hạn theo default policy; vì vậy số queue entries sau cancel bằng 0 trong ví dụ.

### Memory retention của task scheduled đã hủy

Theo tài liệu `ScheduledThreadPoolExecutor`, một task delayed được cancel theo mặc định có thể **không được loại khỏi queue ngay** cho đến khi thời điểm đủ điều kiện chạy đến, nhằm cho phép kiểm tra/tracking, nhưng có thể gây retention không cần thiết. `setRemoveOnCancelPolicy(true)` hữu ích khi nhiều task hẹn giờ bị hủy trước thời điểm chạy.

Không nhầm API này với `ThreadPoolExecutor` thông thường: nó là phương thức của `ScheduledThreadPoolExecutor`. Không tự biến mọi scheduler custom thành cùng một implementation.

## 14. CompletableFuture cũng là Future, nhưng hủy có khác biệt

`CompletableFuture<T>` triển khai `Future<T>` và `CompletionStage<T>`. Tuy vậy cancellation của nó không điều khiển worker giống `FutureTask`:

- `CompletableFuture.cancel(mayInterruptIfRunning)` hoàn tất CompletableFuture bằng `CancellationException` nếu chưa completed.
- Tham số **`mayInterruptIfRunning` không có hiệu lực** với chính implementation `CompletableFuture`, vì nó không dùng interrupt để điều khiển xử lý.
- Các dependent stages chưa hoàn tất có thể hoàn thành exceptional với `CompletionException` gây ra bởi cancellation.
- `CompletableFuture.join()` ném unchecked `CompletionException` đối với lỗi thông thường; nếu chính CompletableFuture đó bị cancel, `join()` có thể ném `CancellationException` trực tiếp.
- `isDone()` true nếu completed normally, exceptionally hoặc cancelled; `isCompletedExceptionally()` có thể true cả khi cancelled.

Vì vậy đừng viết code “`future.cancel(true)` luôn interrupt thread đang tính” rồi áp vào cả `FutureTask` lẫn `CompletableFuture`. Với `CompletableFuture.supplyAsync(...)`, việc cancel completion stage **không nhất thiết dừng Supplier đang chạy**.

Ví dụ minh họa đơn giản:

~~~java
// Snippet, có import java.util.concurrent.CompletableFuture.
CompletableFuture<Integer> cf = new CompletableFuture<>();
boolean cancelled = cf.cancel(true);
System.out.println(cf.isCancelled()); // true
// Điều này không chứng minh một thread thực thi bên ngoài bị interrupt.
~~~

Nếu cần stop công việc tính toán thực sự, thiết kế cancellation token, điều kiện dừng, deadline và quan hệ quản lý task riêng, không dựa duy nhất vào trạng thái của completion stage.

## 15. Cancellation và shutdown của ExecutorService không đồng nhất

`ExecutorService` có lifecycle của **executor**, tách biệt với Future của **từng task**.

| Thao tác | Điều thực hiện | Điều không bảo đảm |
| --- | --- | --- |
| `future.cancel(false)` | Yêu cầu hủy Future cụ thể, không interrupt running task | Không ngắt body đang chạy |
| `future.cancel(true)` | Yêu cầu hủy Future và cố interrupt running task | Không cưỡng bức body dừng tức thì |
| `executor.shutdown()` | Ngừng nhận task mới; xử lý task đã nhận theo hợp đồng | Không tự cancel mọi Future và không ép worker kết thúc ngay |
| `executor.shutdownNow()` | Cố interrupt tasks đang thực thi, trả về tasks chưa bắt đầu | Không bảo đảm mọi task dừng hay completed Future được ghi là cancelled |
| `executor.awaitTermination(timeout, unit)` | Đợi executor terminated sau shutdown | Không tự hủy computation còn sống |
| `Future.get(timeout, unit)` | Giới hạn thời gian đợi kết quả của caller | Không cancel, interrupt hoặc cleanup queued task |

Một lỗi khó phát hiện: **`shutdownNow()` trả danh sách `Runnable` chưa bắt đầu**. Nếu một số item tương ứng với Future mà caller đang giữ, cần quyết định rõ cách xử lý: chỉ vì task bị lấy ra khỏi queue không có nghĩa Future ấy tự được completed/cancelled trong mọi implementation. Nếu cần hoàn tất Future của các task chưa chạy, coordinator phải có protocol cancellation/result reporting thích hợp.

Đối với graceful shutdown, mẫu thông thường:

~~~java
// Snippet minh họa, caller có policy xử lý InterruptedException.
executor.shutdown();
if (!executor.awaitTermination(30, TimeUnit.SECONDS)) {
    java.util.List<Runnable> notStarted = executor.shutdownNow();
    // Ghi nhận/cancel hoặc chuyển tiếp notStarted theo chính sách.
    executor.awaitTermination(10, TimeUnit.SECONDS);
}
~~~

Một worker đang làm I/O không interruptible có thể không dừng đúng thời gian kỳ vọng. Dừng Future và dừng resources là các thao tác phải được phối hợp.

## 16. `invokeAll` và timeout của nhóm tác vụ

`ExecutorService.invokeAll(tasks)` chờ tất cả task trong nhóm hoàn tất và trả về danh sách Future, nhưng caller vẫn phải kiểm tra `get()` từng Future để phân biệt thành công và lỗi.

`invokeAll(tasks, timeout, unit)` có hợp đồng đáng chú ý: method trả về khi mọi task đã hoàn tất hoặc khi hết timeout; **các task chưa hoàn thành sẽ bị hủy** theo API. Đây là sự khác biệt với `Future.get(timeout)` — thứ **không tự cancel**.

Ví dụ khái niệm:

~~~java
// Snippet minh họa trong method throws InterruptedException.
java.util.List<java.util.concurrent.Callable<String>> tasks = ...;
java.util.List<Future<String>> futures =
        executor.invokeAll(tasks, 2, TimeUnit.SECONDS);

for (Future<String> future : futures) {
    if (future.isCancelled()) {
        // Task không hoàn tất trong hạn hoặc bị hủy vì lý do khác.
    } else {
        // get() để lấy kết quả hoặc bắt ExecutionException.
    }
}
~~~

Đoạn này không độc lập vì biến `tasks`/`executor` chưa khai báo đầy đủ. Cũng như cancellation chung, việc API đánh dấu Future cancelled **không tuyệt đối bảo đảm** mọi body đã dừng/đã rollback side effects.

Khi nhóm task có dependency hoặc cần partial results, thiết kế cách tổng hợp thành công/thất bại/timeout/cancel một cách rõ ràng, tránh coi mỗi Future done là successful.

## 17. Race conditions quanh việc hủy và hoàn tất

Cancellation **chạy cạnh tranh** với task completion:

~~~text
Thread A: cancel(true)  -------+
                               +--- ai cập nhật trạng thái trước?
Worker:   return result -------+
~~~

Một trong các kết quả có thể xảy ra:

- Task completed trước khi cancel có hiệu lực: `cancel` thường trả false; `get` trả kết quả hoặc lỗi đã completed.
- Cancel thắng khi Future còn chưa completed: `isCancelled` true và `get` ném `CancellationException`.
- Task đã bắt đầu side effect, cancel thắng Future state, nhưng body có thể tiếp tục side effect nếu không hợp tác hoặc nếu cancellation tới quá muộn.
- Hai caller đồng thời cancel có thể nhận giá trị boolean khác nhau; nhìn return của một caller không phải cách duy nhất suy ra trạng thái cuối.

**Quy tắc thiết kế:** Cancellation phải **idempotent và có thể quan sát được**, nhưng các side effects của task cần giao thức riêng. Với job gửi email, tạo đơn hàng, trừ tiền hoặc ghi database, `cancel(true)` không phải transaction rollback. Có thể cần idempotency key, stored job status, outbox, acknowledgment sau khi commit, compensating action và cách resume khi restart.

### State machine nghiệp vụ khác với Future state

Một API nghiệp vụ có thể có `PENDING`, `RUNNING`, `COMMITTED`, `CANCEL_REQUESTED`, `CANCELLED`, `FAILED`. Một `Future.isCancelled` không tự chứng minh job đã ở `CANCELLED` ở storage hoặc hệ thống ngoài JVM.

Ví dụ nếu khách hàng nhấn Cancel trong lúc giao dịch đang commit, coordinator phải chọn rõ:
- Không cho commit nếu cancellation thắng trước điểm quyết định.
- Hoặc chấp nhận commit đã hoàn tất và trả trạng thái hoàn thành, dù caller không còn cần kết quả.
- Hoặc ghi trạng thái cần compensation và xử lý bất đồng bộ.
Future API **không quyết định** policy này.

## 18. Task cancellation cooperative: những điểm cần kiểm soát

Một task có thể được hủy an toàn hơn khi:

1. Làm việc theo **đơn vị nhỏ** và thường xuyên kiểm tra `isInterrupted()` hoặc stop token hợp lệ.
2. Sử dụng blocking API có hỗ trợ interruption/timeout.
3. Khi bị interrupt, **thoát** hoặc truyền exception thay vì nuốt tín hiệu.
4. Đặt việc giải phóng tài nguyên vào `finally` hoặc try-with-resources.
5. Tránh đóng tài nguyên dùng chung bởi task khác nếu cancellation chỉ áp dụng cho một task.
6. Không viết vào shared mutable state dở dang; cập nhật các invariant theo bước atomic/transaction rõ.
7. Có deadline cụ thể khi làm I/O; interrupt không luôn hiệu quả với mọi thư viện bên ngoài.
8. Theo dõi được **task body actually stopped** nếu cần cleanup tài nguyên ngoài Future handle.
9. Khi có nhiều consumer của một Future/shared computation, cân nhắc ai **có quyền** cancel.
10. Khi tự retry, kiểm soát idempotency để không tạo duplicate side effect sau timeout.

Mẫu vòng CPU-bound:

~~~java
// Snippet của một task tính toán, không phải chương trình độc lập.
while (!Thread.currentThread().isInterrupted()) {
    if (workQueueIsEmpty()) {
        break;
    }
    processNextUnit();
}
cleanupAfterLoop();
~~~

Trong code thật, việc dequeue/kiểm tra queue phải có concurrency protocol phù hợp; snippet này chỉ nhấn mạnh kiểm tra interrupt flag, không cung cấp một queue implementation.

Đừng dựa vào `Thread.sleep(100)` để chứng minh cancellation được nhận “đúng lúc”; scheduler có thể thay đổi thời điểm. Dùng latch để kiểm soát test hoặc có timeout rõ ràng.

## 19. Kiểm chứng correctness của Future cancellation

Một test có giá trị cần tách **trạng thái Future** khỏi **tiến triển thực của worker**:

| Câu hỏi | Kỹ thuật kiểm chứng |
| --- | --- |
| Task đã bắt đầu chưa? | `CountDownLatch started` giảm ở đầu body |
| Task có chắc còn chờ trong queue? | Một single-worker executor bị giữ bằng latch, task thứ hai được submit |
| `cancel(false)` có interrupt worker không? | Task đang chờ latch và chỉ release sau khi đọc Future status |
| `cancel(true)` được body quan sát? | Latch `interruptionObserved` giảm trong catch `InterruptedException` |
| Caller bị timeout nhưng task có còn sống? | Chỉ release latch **sau** `get(timeout)` ném `TimeoutException` |
| Task đã thực sự dừng chưa? | Latch/callback cuối body, `join` hoặc executor termination phù hợp |
| Lỗi task được giữ trong Future? | `get()` và `ExecutionException.getCause()` |
| Task scheduled đã cancel có còn trong queue? | Kiểm tra remove-on-cancel policy của scheduler cụ thể |

Không dùng một kết quả `isDone() == true` để xác nhận resource cleanup sau cancel. Không kết luận cancellation dừng side effect chỉ vì `Future.get()` ném `CancellationException`.

### Đừng biến demo thành test treo mãi

Các ví dụ dùng latch và giả định không có interruption bên ngoài để có stdout xác định. Với **automated test suite thực tế**, các bước `await()`/`join()` nên có timeout, nhánh fail-safe và cleanup trong `finally`; nếu implementation sai hoặc task không hợp tác, test sẽ không treo vô hạn.

Khi cần đo performance, tách biệt thời gian queue wait, execution, cancellation latency và cleanup latency. Cancelled count cao có thể là dấu hiệu deadline quá ngắn hoặc executor backlog quá lớn.

## 20. Những nhầm lẫn cần tránh

| Nhầm lẫn | Sự thật |
| --- | --- |
| “`isDone()` true nghĩa là thành công.” | Có thể là normal, failure hoặc cancellation |
| “`isCancelled()` true nghĩa worker chắc đã dừng.” | Future state có thể cancelled trong khi task body vẫn chạy |
| “`cancel(false)` không thể hủy task đã bắt đầu.” | Với FutureTask, có thể đánh dấu cancelled mà không interrupt worker |
| “`cancel(true)` giống `Thread.stop()`.” | Chỉ cố interrupt, cần task hợp tác |
| “`cancel(true)` rollback database.” | Không có transaction/compensation tự động |
| “`get(timeout)` timeout sẽ hủy task.” | Nó chỉ giới hạn waiting time của caller |
| “Bắt `InterruptedException` rồi bỏ qua là được.” | Có thể làm task không phản hồi cancellation |
| “Caller `get()` bị interrupt nghĩa Future bị cancelled.” | Hai trạng thái khác nhau |
| “Future lỗi thì `isCancelled()` true.” | Task failure và cancellation khác nhau |
| “Một Future bị cancel sẽ tự mất khỏi queue ngay.” | Có thể còn wrapper queued; scheduler/remove-on-cancel policy khác nhau |
| “`ScheduledFuture.get()` của periodic task trả sau một chu kỳ.” | Periodic task thường không hoàn tất bình thường sau mỗi lần chạy |
| “`CompletableFuture.cancel(true)` interrupt supplier.” | Tham số interrupt không có hiệu lực với CompletableFuture |
| “`shutdownNow()` là cancel chính xác mọi Future.” | Cố interrupt và trả queued tasks, không cam kết mọi Future completed/cancelled |
| “`invokeAll(timeout)` giống `get(timeout)`.” | invokeAll timeout có hợp đồng cancel unfinished tasks |
| “Cancel xong có thể đóng tài nguyên mà body đang dùng.” | Phải phối hợp completion/cleanup thực tế |
| “`Future` có enum RUNNING/QUEUED trong Java 17.” | Interface Java 17 không có API trạng thái chi tiết đó |

## 21. Câu hỏi tự kiểm tra

**Câu 1.** `isDone() == true` và `isCancelled() == false` có chứng minh task thành công không?  
**Đáp án:** Không. Nó có thể đã ném exception; gọi `get()` và xử lý `ExecutionException`.

**Câu 2.** `future.cancel(false)` trả true trong khi FutureTask đang chạy. Body có tự dừng ngay không?  
**Đáp án:** Không nhất thiết; Future có thể cancelled nhưng body vẫn chạy vì không bị interrupt.

**Câu 3.** `future.cancel(true)` được gọi khi task đang block tại `CountDownLatch.await()`. Chuyện gì có thể xảy ra?  
**Đáp án:** Thread được cố interrupt; `await` có thể ném `InterruptedException` để body xử lý. Cần xác nhận body thực sự quan sát và thoát.

**Câu 4.** `get(50, MILLISECONDS)` ném `TimeoutException` thì `isCancelled()` tự chuyển true không?  
**Đáp án:** Không. Timeout chỉ áp dụng lần chờ đó.

**Câu 5.** Task ném `IllegalStateException`. `Future.get()` ném trực tiếp `IllegalStateException` không?  
**Đáp án:** Với Future từ `ExecutorService.submit`, `get()` ném `ExecutionException`; nguyên nhân gốc ở `getCause()`.

**Câu 6.** Future đã trả kết quả bình thường có thể cancel thành công sau đó không?  
**Đáp án:** Không; Future đã completed nên cancellation không thay đổi kết quả.

**Câu 7.** Một `ScheduledFuture` periodic chạy thành công ba lần, `isDone()` có bắt buộc true không?  
**Đáp án:** Không. Periodic Future chưa dừng lịch chạy thì thông thường còn not-done; `get()` không trả chỉ vì một chu kỳ kết thúc.

**Câu 8.** Vì sao nên cân nhắc `setRemoveOnCancelPolicy(true)` trong `ScheduledThreadPoolExecutor`?  
**Đáp án:** Giảm retention của delayed tasks bị cancel còn lưu trong queue đến thời điểm tới hạn theo default policy.

**Câu 9.** `CompletableFuture.cancel(true)` có bắt buộc interrupt thread đang chạy Supplier không?  
**Đáp án:** Không; `mayInterruptIfRunning` không có hiệu lực với implementation CompletableFuture.

**Câu 10.** `invokeAll(tasks, timeout, unit)` và `future.get(timeout, unit)` khác gì ở cancellation?  
**Đáp án:** invokeAll timed hủy những task chưa hoàn thành khi timeout; get timed không tự hủy Future.

**Câu 11.** Nếu caller bị interrupt khi `get()`, task có tự bị hủy không?  
**Đáp án:** Không. Caller phải quyết định có cancel task hay không theo ownership/policy.

**Câu 12.** Sau `cancel(true)`, `isDone()==true`, có được mặc định đóng ngay socket task đang dùng?  
**Đáp án:** Không. Body có thể vẫn đang thực thi; phải có protocol dừng/cleanup thực tế.

## Tài liệu tham khảo chính thức

- [`Future` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `get`, `isDone`, `isCancelled`, `cancel`, memory consistency.
- [`FutureTask` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/FutureTask.html): runnable future, cancellation của computation.
- [`ExecutorService` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): `submit`, `invokeAll`, `shutdown`, `shutdownNow`.
- [`ScheduledExecutorService` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html): `schedule`, `scheduleAtFixedRate`, `scheduleWithFixedDelay`.
- [`ScheduledFuture` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledFuture.html): Future cho scheduled computation.
- [`ScheduledThreadPoolExecutor` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html): remove-on-cancel và shutdown policies.
- [`CompletableFuture` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): cancellation/completion stages và interrupt semantics.
- [`CountDownLatch` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): điều phối test xác định.

**Ghi nhớ:** `Future` cho biết trạng thái **kết quả computation**; nó không phải khóa cưỡng bức thread. Muốn cancellation an toàn phải **định nghĩa ownership, cooperative interruption, deadline, side effect policy và tín hiệu body đã thực sự kết thúc**, đặc biệt với scheduling và executor shutdown.