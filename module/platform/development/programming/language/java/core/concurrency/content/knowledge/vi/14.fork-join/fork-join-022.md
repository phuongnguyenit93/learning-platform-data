# ForkJoinTask.cancel() so với adaptInterruptible(Callable) trên Java 21

## 1. Vấn đề: hủy trạng thái Future khác với dừng tác vụ đang chạy

Trong Fork/Join, một tác vụ có thể đã được đưa vào hàng đợi, đang chạy trên worker hoặc đã hoàn thành. Khi caller không còn cần kết quả, phương thức `ForkJoinTask.cancel(boolean mayInterruptIfRunning)` cho phép **chuyển trạng thái của task sang canceled** nếu việc hủy thành công. Nhưng **canceled không mặc nhiên có nghĩa thread đang chạy đã bị interrupt hoặc thân task đã dừng**.

Ở Java 21, cần phân biệt rõ hai lựa chọn:

- `ForkJoinTask` thông thường, chẳng hạn một `RecursiveTask` hoặc tác vụ tạo bằng `ForkJoinTask.adapt(Callable)`: implementation mặc định của `cancel(...)` **không dùng interrupt để điều khiển hủy**; giá trị `mayInterruptIfRunning` không có tác dụng đối với implementation mặc định.
- `ForkJoinTask.adaptInterruptible(Callable<? extends T>)`: tạo một `ForkJoinTask<T>` đặc biệt; khi gọi `cancel(true)`, implementation **cố interrupt thread đang thực hiện Callable**, giúp tác vụ có khả năng hợp tác với cancellation.

Điểm chung: trong cả hai trường hợp, `isCancelled()` và `join()` phản ánh **kết quả logic của việc hủy**, không phải giấy chứng nhận rằng mọi side effect, I/O hoặc cleanup đã kết thúc.

Bài này tập trung vào **Java Concurrency chuẩn, không gắn với Spring**. Nội dung áp dụng cụ thể cho API Java 21; một số overload cùng tên được bổ sung ở các JDK sau nên không nên suy luận chúng tồn tại trong Java 21.

## 2. Những API cần biết

### 2.1. ForkJoinTask.cancel(boolean)

Chữ ký:

```java
public boolean cancel(boolean mayInterruptIfRunning)
```

Một lệnh hủy thành công có các hệ quả quan trọng:

1. Nếu task **chưa bắt đầu**, việc thực thi thân task được ngăn chặn.
2. `isCancelled()` và `isDone()` sẽ trả `true`, trừ khi có thao tác `reinitialize()` theo hợp đồng của lớp.
3. `join()`, `get()` và các cách lấy kết quả liên quan sẽ báo `CancellationException` thay vì giá trị kết quả.
4. Nếu task đang chạy, trạng thái canceled **không bảo đảm** thân task dừng ngay.
5. `cancel(true)` trên implementation mặc định không có tác động interrupt khác `cancel(false)`. Subclass có thể override nhưng vẫn phải giữ hợp đồng canceled và không được ném exception từ chính `cancel`.

Giá trị trả về `true` có nghĩa **task hiện đang ở trạng thái canceled** (kể cả tình huống đã được hủy trước đó), không biểu thị rằng worker chắc chắn vừa được ngắt hoặc đã kết thúc. Nếu task đã hoàn thành bình thường trước lúc hủy, yêu cầu hủy không chuyển được nó sang canceled.

### 2.2. adapt(Callable) và adaptInterruptible(Callable)

Java 21 cung cấp hai adapter từ `Callable<T>`:

```java
ForkJoinTask<Integer> ordinary =
        ForkJoinTask.adapt(() -> 6 * 7);

ForkJoinTask<Integer> interruptible =
        ForkJoinTask.adaptInterruptible(() -> 6 * 7);
```

Cả hai đều tạo `ForkJoinTask<Integer>`, thực thi `Callable.call()` và cho phép lấy kết quả qua `join()`. Ngoại lệ checked do `call()` ném được adapter chuyển thành một `RuntimeException` theo hợp đồng của API khi truy cập bằng cơ chế Fork/Join; riêng `Future.get()` vẫn có semantics `ExecutionException` của `Future`.

Khác biệt chủ yếu nằm ở **cancellation khi task đang chạy**:

- `adapt(Callable)` sử dụng cancellation kiểu Fork/Join mặc định; `cancel(true)` không có nghĩa gửi interrupt tới runner.
- `adaptInterruptible(Callable)` hỗ trợ cố interrupt runner khi gọi `cancel(true)`.
- Nếu gọi `cancel(false)` trên adapter interruptible, nó **không yêu cầu interrupt runner**; task đang chạy có thể tiếp tục.
- Task phải hợp tác với interruption: `CountDownLatch.await()`, `sleep()` hoặc các blocking API hỗ trợ có thể ném `InterruptedException`; vòng tính CPU cần kiểm tra interrupt flag, còn một số I/O có thể không phản ứng.

**Phiên bản API:** `adaptInterruptible(Callable)` xuất hiện từ Java 19 và có trong Java 21. Các overload `adaptInterruptible(Runnable)` và `adaptInterruptible(Runnable, T)` là API xuất hiện từ Java 22, vì thế đừng đưa chúng vào mã biên dịch với `--release 21`.

### 2.3. Bảng so sánh nhanh

| Câu hỏi | ForkJoinTask mặc định | `adaptInterruptible(Callable)` |
| --- | --- | --- |
| Hủy trước khi bắt đầu có ngăn thân task chạy? | Có nếu hủy thành công | Có nếu hủy thành công |
| `cancel(false)` trên task đang chạy | Đánh dấu canceled, không yêu cầu interrupt | Đánh dấu canceled, không yêu cầu interrupt |
| `cancel(true)` trên task đang chạy | Tham số true không có tác dụng interrupt trong implementation mặc định | **Cố interrupt thread** đang chạy Callable |
| `isCancelled()` sau hủy thành công | `true` | `true` |
| `join()` sau hủy thành công | Ném `CancellationException` | Ném `CancellationException` |
| Task đang chạy có thể tiếp tục sau khi canceled? | Có | Có nếu không xử lý interrupt hoặc interrupt không đủ dừng |
| Khi nào chọn? | Tính toán chia nhỏ không chặn, cancellation bằng trạng thái/kiểm tra hợp tác | Callable cần phản ứng khi đang chờ API có khả năng interrupt |

Không được diễn giải bảng thành “adapter interruptible cưỡng ép dừng thread”. Java không cung cấp biện pháp hủy an toàn mang tính cưỡng bức đối với mọi tác vụ tùy ý.

## 3. Ba mức trạng thái phải quan sát riêng

Một cách nghĩ chính xác là phân biệt ba sự kiện:

1. **Cancellation accepted:** `cancel(...)` đưa Future/task sang trạng thái canceled.
2. **Interruption requested:** với `adaptInterruptible(callable)` và `cancel(true)` khi callable đã chạy, implementation cố gửi interrupt đến thread thực thi.
3. **Task body actually exited:** code đi tới điểm thoát, chạy `finally` và trả lại các tài nguyên do nó giữ.

Ba thời điểm có thể khác nhau. Đặc biệt, khi trạng thái hủy đã được đánh dấu:

```java
boolean cancelled = task.isCancelled();
boolean done = task.isDone();
```

`cancelled == true` và `done == true` **không khẳng định** tác vụ đã thực sự thoát khỏi vòng lặp hoặc kết thúc side effect. `isDone()` nói về trạng thái của `ForkJoinTask`; nếu task bị hủy trong khi đang chạy, code có thể vẫn tiếp tục một thời gian.

Để xác minh thân task đã rời khỏi phần quan trọng, ứng dụng cần một cơ chế riêng nếu cần, ví dụ `CountDownLatch` được `countDown()` trong `finally`, hoặc đóng tài nguyên / kết thúc giao thức ở ranh giới phù hợp. Không dùng chính việc `get()` đã trả `CancellationException` làm xác nhận cleanup.

## 4. Ví dụ Java 21 chạy độc lập: quan sát cancel và interrupt

Ví dụ dưới đây cố ý cho Callable **chờ trên `CountDownLatch`** để tái hiện task đang chạy một cách có kiểm soát. Nó dùng ba tình huống:

1. `adapt(Callable)` + `cancel(true)`: task bị hủy về mặt trạng thái nhưng không nhận interrupt chỉ từ lệnh hủy mặc định.
2. `adaptInterruptible(Callable)` + `cancel(false)`: task bị hủy về mặt trạng thái nhưng không yêu cầu interrupt.
3. `adaptInterruptible(Callable)` + `cancel(true)`: runner nhận yêu cầu interrupt và `await()` thoát bằng `InterruptedException`.

`CountDownLatch` ở đây chỉ phục vụ minh họa ngữ nghĩa. Trong Fork/Join thực tế, task nên ngắn, có thể phân rã và tránh chờ lâu; nếu chủ yếu là I/O/blocking, cần đánh giá mô hình executor phù hợp.

Lưu tệp `ForkJoinCancellationDemo.java`:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.ForkJoinTask;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class ForkJoinCancellationDemo {
    public static void main(String[] args) throws InterruptedException {
        runCase("adapt + cancel(true)", false, true);
        runCase("interruptible + cancel(false)", true, false);
        runCase("interruptible + cancel(true)", true, true);
    }

    private static void runCase(
            String label, boolean useInterruptible, boolean interruptOnCancel)
            throws InterruptedException {

        ForkJoinPool pool = new ForkJoinPool(1);
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch exited = new CountDownLatch(1);
        AtomicBoolean caughtInterrupt = new AtomicBoolean(false);

        Callable<String> work = () -> {
            started.countDown();
            try {
                release.await();
                return "completed";
            } catch (InterruptedException interrupted) {
                caughtInterrupt.set(true);
                return "interrupted";
            } finally {
                exited.countDown();
            }
        };

        ForkJoinTask<String> task = useInterruptible
                ? ForkJoinTask.adaptInterruptible(work)
                : ForkJoinTask.adapt(work);

        try {
            pool.execute(task);
            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Task did not start");
            }

            boolean cancelled = task.cancel(interruptOnCancel);
            if (!cancelled || !task.isCancelled()) {
                throw new AssertionError("Cancellation was not accepted");
            }

            if (useInterruptible && interruptOnCancel) {
                // Task dùng await(): interrupt sẽ làm nó thoát.
                if (!exited.await(5, TimeUnit.SECONDS)) {
                    throw new AssertionError("Interrupt was not observed");
                }
            } else if (exited.getCount() == 0) {
                throw new AssertionError("Unexpected early exit");
            }

            // Cho cả những task không bị interrupt thoát an toàn.
            release.countDown();
            if (!exited.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Task body did not exit");
            }

            boolean joinCancelled = false;
            try {
                task.join();
            } catch (CancellationException expected) {
                joinCancelled = true;
            }

            System.out.println(label
                    + " | cancelled=" + task.isCancelled()
                    + " | caughtInterrupt=" + caughtInterrupt.get()
                    + " | joinCancelled=" + joinCancelled);
        } finally {
            release.countDown();
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Pool did not terminate");
            }
        }
    }
}
```

Biên dịch với **JDK 21**:

```bash
javac --release 21 ForkJoinCancellationDemo.java
java ForkJoinCancellationDemo
```

Stdout dự kiến trên JDK 21:

```text
adapt + cancel(true) | cancelled=true | caughtInterrupt=false | joinCancelled=true
interruptible + cancel(false) | cancelled=true | caughtInterrupt=false | joinCancelled=true
interruptible + cancel(true) | cancelled=true | caughtInterrupt=true | joinCancelled=true
```

Các latch tạo thứ tự rõ ràng: `started.await()` chỉ hoàn tất sau khi Callable bắt đầu; `release` giữ hai trường hợp không interrupt ở bên trong `await()`; `exited` xác nhận code đã rời thân tác vụ trước khi in kết quả. Trường hợp interruptible + true chỉ tiếp tục khi đã quan sát thân task thoát sau interrupt.

Mã trên **không dùng `Thread.sleep` để suy đoán task đã bắt đầu**. Các lệnh `await(timeout)` còn ngăn demo chờ vô hạn nếu môi trường quá tải hoặc API không có hành vi như mong đợi. Nếu pool không thể lập lịch một task trong 5 giây, demo cố ý báo `AssertionError` thay vì khẳng định một kết quả không quan sát được.

Một điểm dễ bỏ qua: Callable ở đây bắt `InterruptedException` và trả chuỗi `"interrupted"`, nhưng khi `cancel(true)` đã đánh dấu ForkJoinTask canceled thì **`join()` vẫn ném `CancellationException`**, không trả chuỗi đó. Đây là bằng chứng rõ ràng rằng **kết quả logic của Future** khác với **đường thoát thực tế của thân task**.

## 5. Vì sao cancel(true) không giống Thread.interrupt()?

`cancel(boolean)` thuộc giao diện `Future`, nhưng mỗi implementation có thể có quy tắc cụ thể về cách hủy tác vụ. Không nên chỉ nhìn tên tham số `mayInterruptIfRunning` rồi giả định mọi implementation đều gửi interrupt.

**ForkJoinTask mặc định** phục vụ những tính toán nhẹ, ngắn và có cấu trúc fork/join. Documentation Java 21 nêu rõ tham số `mayInterruptIfRunning` không có tác dụng trong implementation mặc định, bởi interrupt không được dùng để điều khiển hủy.

**Adapter interruptible** là một lựa chọn có chủ đích cho `Callable` cần cơ chế hủy phù hợp hơn với `Future` thông thường. Khi `cancel(true)`, nó cố interrupt runner đang thực hiện Callable. Nếu callable đang bị block trong `CountDownLatch.await()`, `Thread.sleep()` hoặc API chờ có thể ngắt, nó thường thoát nhanh bằng `InterruptedException`.

Sự khác biệt đó chỉ đúng khi **runner đã bắt đầu** và có thể tiếp nhận interrupt. Nếu task bị hủy **trước khi chạy**, cả hai có thể ngăn phần thân được thực thi; không có runner để interrupt. Nếu task đã hoàn thành, hủy không chuyển lại trạng thái sang canceled.

Cũng cần phân biệt **cancel từ bên ngoài** với **task tự dừng**. Bên trong `RecursiveTask.compute()`, task có thể tự trả về khi phát hiện cờ hủy do ứng dụng quản lý. Việc kiểm tra `isCancelled()` bên trong vòng lặp chỉ hữu ích nếu luồng điều khiển của ứng dụng thực sự có điểm kiểm tra và thoát.

## 6. Chọn API nào trong Java 21?

### 6.1. RecursiveTask/RecursiveAction cho bài toán chia để trị

Một `RecursiveTask<V>` thông thường chia công việc thành những phần nhỏ bằng `fork()` và `join()`. Cần tránh blocking lâu bên trong các nhánh, vì worker bị chiếm có thể khiến pool thiếu thread để xử lý các task còn lại.

```java
// Fragment trong compute() của một RecursiveTask<Long>.
if (hi - lo <= threshold) {
    return sumDirectly(data, lo, hi);
}
int mid = lo + (hi - lo) / 2;
SumTask left = new SumTask(data, lo, mid, threshold);
SumTask right = new SumTask(data, mid, hi, threshold);
left.fork();
long rightValue = right.compute();
return left.join() + rightValue;
```

Đây là fragment có các lớp/biến do ứng dụng định nghĩa, không phải chương trình độc lập. Nếu muốn hủy cả cây fork/join, **hủy mỗi root task không chứng minh mọi nhánh con đã dừng**. Thiết kế cần cơ chế phối hợp hợp tác, ví dụ cờ dừng được chia sẻ an toàn và các nhánh kiểm tra định kỳ trước khi fork thêm công việc.

### 6.2. adapt(Callable) khi cần chuyển Callable đơn giản

`ForkJoinTask.adapt(callable)` phù hợp nếu mục tiêu chính là đưa một Callable vào API Fork/Join và semantics mặc định về hủy là chấp nhận được. Đừng kỳ vọng `cancel(true)` làm ngắt blocking call đang chạy.

### 6.3. adaptInterruptible(Callable) khi cần phản ứng với hủy

`ForkJoinTask.adaptInterruptible(callable)` hữu ích nếu Callable có thể block hoặc cần dừng khi có yêu cầu hủy. Đây là API Java 21 hợp lệ cho Callable; một số chương trình có thể muốn tận dụng đặc tính này khi chạy công việc trong `ForkJoinPool`.

Nhưng không nên suy ra rằng **mọi tác vụ blocking đều phù hợp ForkJoinPool**. Pool tối ưu cho việc chia nhỏ tính toán. Blocking có thể làm giảm hiệu suất worker; xem xét `ForkJoinPool.ManagedBlocker`, executor khác, deadline cho I/O và giới hạn số task đang hoạt động khi thực sự cần.

### 6.4. Bảng quyết định

| Trường hợp | Gợi ý |
| --- | --- |
| Phân rã CPU-bound, mỗi subtask ngắn, ít blocking | `RecursiveTask` / `RecursiveAction`, cancellation hợp tác |
| Chuyển một `Callable<T>` sang `ForkJoinTask<T>` mà không cần interrupt-on-cancel | `ForkJoinTask.adapt(callable)` |
| Callable đang chờ API có hỗ trợ `InterruptedException` và cần `cancel(true)` cố ngắt runner | `ForkJoinTask.adaptInterruptible(callable)` |
| Công việc blocking dài và không thể hợp tác với interrupt | Thiết kế timeout và resource cancellation riêng; cân nhắc executor chuyên cho I/O |
| Task cần sống qua restart hoặc rollback side effect | Dùng trạng thái công việc và giao dịch/idempotency ở tầng ứng dụng; `ForkJoinTask` không cung cấp độ bền |

## 7. Kiểm tra trạng thái và cách lấy kết quả

Các API quan trọng:

| Phương thức | Ý nghĩa |
| --- | --- |
| `cancel(boolean)` | Cố chuyển task sang canceled; có thể hoặc không cố interrupt tùy implementation |
| `isDone()` | `true` nếu hoàn tất bình thường, lỗi hoặc bị hủy |
| `isCancelled()` | `true` nếu trạng thái là canceled |
| `isCompletedNormally()` | `true` nếu hoàn tất bình thường |
| `isCompletedAbnormally()` | `true` nếu lỗi hoặc hủy |
| `getException()` | Ngoại lệ tính toán hoặc `CancellationException` khi đã hủy; `null` nếu chưa có |
| `join()` | Đợi và lấy kết quả; khi hủy ném `CancellationException` (unchecked) |
| `get()` | Theo giao diện `Future`: có thể ném `InterruptedException`, `ExecutionException` hoặc `CancellationException` |

`join()` và `get()` không có cùng cách gói lỗi. `join()` ném exception bất thường dưới dạng unchecked (hoặc `Error`), còn `get()` biểu thị lỗi tác vụ qua `ExecutionException`. Với cancellation, cả hai có thể ném `CancellationException`.

Ví dụ fragment kiểm tra:

```java
if (task.isCancelled()) {
    System.out.println("Result unavailable");
} else if (task.isCompletedNormally()) {
    System.out.println(task.join());
} else if (task.isCompletedAbnormally()) {
    System.out.println("Failed: " + task.getException());
}
```

Đây là fragment với `task` đã được khai báo ở nơi khác. Những kiểm tra trạng thái này phục vụ phân loại kết quả; không thay thế cơ chế xác nhận thân task đã thực sự thoát hoặc cleanup xong.

### Ngoại lệ checked của Callable

`Callable.call()` cho phép checked exception, ví dụ `IOException`. `adapt` và `adaptInterruptible` chuyển checked exception gặp phải thành `RuntimeException` khi thể hiện dưới dạng `ForkJoinTask`. Caller cần thiết kế xử lý ngoại lệ gốc cho phù hợp; nếu dùng `get()`, lỗi thực thi được chuyển qua `ExecutionException` theo semantics `Future`.

Không bắt mọi `RuntimeException` rồi mặc định là “task canceled”: cancellation có exception riêng là `CancellationException`. Một Callable thất bại do lỗi nghiệp vụ hoặc I/O cần được phân biệt với cancellation do caller yêu cầu.

## 8. Hủy cây fork/join: tại sao hủy root chưa đủ?

Các subtask là các `ForkJoinTask` riêng biệt. Khi một root fork hai nhánh, chúng có trạng thái hoàn tất/hủy riêng. Hủy root có thể khiến `root.join()` báo hủy, nhưng không tự chứng minh mọi nhánh con đã được hủy, đặc biệt các nhánh đã chạy và đang có side effect.

Một kiểu hợp tác là dùng `AtomicBoolean` hoặc một cơ chế cancellation token do ứng dụng quản lý:

```java
// Fragment: các nhánh được truyền cùng AtomicBoolean stopRequested.
if (stopRequested.get()) {
    return 0L; // Chỉ phù hợp khi 0 là kết quả bỏ dở được quy ước.
}
long partial = computeChunk();
if (stopRequested.get()) {
    return 0L;
}
return partial;
```

**Cảnh báo về kết quả:** Trả `0` khi hủy ở đây chỉ minh họa chỗ thoát; trong bài toán tổng hợp thật, trả một tổng thiếu mà không ghi rõ canceled có thể gây sai nghiệp vụ. Thường nên để trạng thái hủy được biểu diễn riêng hoặc xử lý exception/cancellation theo hợp đồng của toàn phép tính.

Nếu muốn dừng mọi nhánh, phải truyền tín hiệu đến toàn cây và thiết kế cleanup. `adaptInterruptible(Callable)` chỉ cố ngắt **runner của task adapter đó**; không tự đi tìm và interrupt toàn bộ các subtask khác được fork từ bên trong Callable.

## 9. Interruption mang tính hợp tác

Các trường hợp thường gặp khi adapter interruptible gọi `cancel(true)`:

- **Đang ở `CountDownLatch.await()` hay `Thread.sleep()`:** nhận `InterruptedException` và có thể thoát nhanh.
- **Đang chạy vòng lặp CPU:** nếu không gọi API chờ, cần kiểm tra `Thread.currentThread().isInterrupted()` ở các checkpoint.
- **Đang làm I/O:** tùy API có hỗ trợ interruption hay không. Nhiều thao tác network cần timeout của chính client/socket để tránh kẹt lâu.
- **Đang giữ lock hoặc cập nhật trạng thái:** phải tránh dừng giữa một invariant chưa được khôi phục; dùng `try/finally` để đóng và giải phóng tài nguyên.
- **Đang gọi hệ thống bên ngoài:** interrupt thread Java không tự rollback request đã gửi.

Ví dụ một Callable kiểm tra interrupt khi tính toán:

```java
Callable<Long> calculation = () -> {
    long sum = 0L;
    for (int i = 0; i < 1_000_000; i++) {
        if (Thread.currentThread().isInterrupted()) {
            throw new InterruptedException("Computation interrupted");
        }
        sum += i;
    }
    return sum;
};
```

Khi dùng `adaptInterruptible(calculation)`, lệnh `cancel(true)` trên task đang chạy có thể khiến vòng lặp phát hiện interrupt ở lần kiểm tra kế tiếp. Nếu task hoàn tất trước khi hủy, `cancel` sẽ không chuyển lại một kết quả thành công sang canceled. Đừng dùng thời gian chạy thật để kỳ vọng việc cancel luôn thắng một cuộc đua.

### Xử lý InterruptedException

Nếu Callable không thể hoàn tất đúng cách khi bị ngắt, thường cho phép `InterruptedException` lan ra khỏi `call()` (nó khai báo `throws Exception`), để thân task thoát. Nếu bắt exception để dọn dẹp, có thể truyền tiếp:

```java
try {
    blockingStep();
} catch (InterruptedException interrupted) {
    cleanupLocalState();
    throw interrupted;
}
```

Đây là fragment dùng các hàm do ứng dụng định nghĩa. Nếu một phương thức không thể truyền checked exception, nên khôi phục interrupt flag bằng `Thread.currentThread().interrupt()` và thoát theo hợp đồng riêng. Không bỏ qua interrupt rồi tiếp tục vòng lặp vô hạn.

## 10. Thận trọng với shutdown, timeout và tài nguyên

`pool.shutdown()` ngừng nhận công việc mới và cho những tác vụ đã được nhận hoàn tất theo cơ chế shutdown thông thường; `pool.shutdownNow()` cố ngắt công việc đang chạy và xử lý công việc chưa bắt đầu theo hợp đồng `ExecutorService`. Không được đánh đồng shutdown của pool với `task.cancel(true)`.

Dù dùng adapter interruptible, **timeout ở caller** và **hủy task** vẫn là hai hành động khác nhau:

```java
try {
    String result = task.get(500, TimeUnit.MILLISECONDS);
    consume(result);
} catch (java.util.concurrent.TimeoutException timedOut) {
    task.cancel(true); // Chủ động yêu cầu hủy sau timeout.
}
```

Đây là fragment: `task` và `consume` do ứng dụng định nghĩa; để biên dịch độc lập cần xử lý thêm `InterruptedException`, `ExecutionException`, `CancellationException`. Bản thân `get(timeout)` ném `TimeoutException` **không tự động hủy** tác vụ; cần gọi `cancel(true)` nếu chính sách ứng dụng muốn dừng.

Tương tự, sau `cancel(true)`, nên có cách quan sát task thực sự thoát nếu việc giữ kết nối, lock hoặc resource là rủi ro quan trọng. Dùng deadline I/O và kiểm tra worker bị kẹt; đừng dựa vào `isCancelled()` đơn lẻ để quyết định một tài nguyên chắc chắn đã được giải phóng.

## 11. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Nghĩ `ForkJoinTask.cancel(true)` mặc định interrupt worker | Task đang block vẫn chạy/chờ; Future đã canceled | Phân biệt implementation mặc định và adapter interruptible |
| Nghĩ `adaptInterruptible` đảm bảo dừng cưỡng bức | Task không đáp ứng interrupt có thể vẫn chiếm tài nguyên | Thiết kế interruption checkpoint, I/O timeout và cleanup |
| Gọi `cancel(false)` rồi chờ runner bị interrupt | Tham số false không yêu cầu interrupt | Dùng true khi cần và có thể hủy cooperatively |
| Coi `isDone()` là task thành công | Canceled và failed cũng done | Dùng `isCompletedNormally()`, `isCancelled()`, `getException()` |
| Coi `join()` ném `CancellationException` là cleanup đã xong | Tài nguyên còn bị giữ bởi body chưa thoát | Quan sát completion của body/cleanup riêng |
| Gọi `pool.invoke(task)` đồng bộ rồi định cancel từ cùng thread | Thread gọi đang chờ `invoke` hoàn thành | Dùng `execute(task)` / `submit(task)` và giữ handle để cancel từ caller |
| Bỏ qua `InterruptedException` trong Callable | Task tiếp tục chạy sau yêu cầu hủy | Truyền tiếp hoặc xử lý và thoát |
| Hủy root rồi giả định mọi subtask đã dừng | Subtask có thể tiếp tục gây side effect | Tín hiệu hủy toàn cây, kiểm tra tại mỗi nhánh |
| Dùng overload `adaptInterruptible(Runnable)` trên Java 21 | Không biên dịch: overload này từ Java 22 | Dùng overload `Callable` trên Java 21 |
| Dùng ForkJoinPool cho I/O kéo dài mà không giới hạn | Worker starvation, throughput giảm | Đặt deadline, chọn executor phù hợp, cân nhắc ManagedBlocker |
| Coi task đã hủy là transaction rollback | Dữ liệu bên ngoài có thể đã thay đổi | Idempotency/compensation và xác minh trạng thái |

## 12. Checklist chọn và kiểm chứng cancellation

1. **Xác định loại task**: tính toán chia nhỏ hay Callable có blocking?
2. **Xác định implementation**: `RecursiveTask`/`adapt` mặc định hay `adaptInterruptible(Callable)`?
3. **Xác định trường hợp hủy**: trước khi chạy, đang chạy hay đã hoàn tất?
4. **Phân biệt ý nghĩa của boolean**: `cancel(true)` không tự động buộc thread dừng; implementation nào mới cố interrupt?
5. **Dùng tín hiệu có thể quan sát**: `CountDownLatch` hoặc cleanup completion nếu cần chứng minh thân task đã thoát.
6. **Đặt timeout cho I/O**: không dựa duy nhất vào interrupt khi thư viện không hỗ trợ.
7. **Dọn tài nguyên**: `try/finally`, `try-with-resources` và owner cho resource tạo trước khi task bắt đầu.
8. **Kiểm thử race**: hủy trước khi task chạy, sau khi bắt đầu và sau khi đã hoàn thành.
9. **Giữ contract kết quả**: `CancellationException`, lỗi tính toán và thành công phải là các nhánh khác nhau.
10. **Đối chiếu đúng phiên bản**: chỉ dùng API được công bố trong Java 21 nếu module nhắm Java 21.

## 13. Câu hỏi tự kiểm tra

**1. Với `RecursiveTask` bình thường, `cancel(true)` có interrupt worker không?**  
Không theo implementation mặc định của `ForkJoinTask`; tham số `mayInterruptIfRunning` không có tác dụng interrupt ở đó.

**2. `adaptInterruptible(Callable)` có từ Java 21 hay muộn hơn?**  
Có trong Java 21 (API được giới thiệu từ Java 19). Hai overload nhận `Runnable` xuất hiện từ Java 22.

**3. `cancel(true)` trên adapter interruptible có bảo đảm Callable đã ngừng mọi side effect khi trả về không?**  
Không. Nó chỉ cố interrupt runner; Callable cần hợp tác và tự cleanup.

**4. Task đã bị canceled nhưng thân Callable sau đó trả một giá trị thì `join()` trả giá trị đó chứ?**  
Không. Khi trạng thái canceled được thiết lập thành công, `join()` ném `CancellationException`, bất kể thân Callable sau đó đi tới một lệnh `return`.

**5. `isDone()==true` có nghĩa thân task đã thoát khỏi mọi xử lý chưa?**  
Không. Với task đã bị hủy trong khi chạy, trạng thái Future có thể done trước lúc code thực sự dừng.

**6. Có thể dùng `get(timeout)` thay cho `cancel(true)` không?**  
Không. `get(timeout)` chỉ giới hạn thời gian chờ của caller; hết hạn không tự gửi tín hiệu hủy.

**7. Vì sao không dùng `adaptInterruptible` như cách hủy cả cây fork/join?**  
Nó quản lý runner của một adapter task, không tự truyền hủy đến mọi subtask được tạo độc lập.

**8. Khi nào nên tránh ForkJoinPool?**  
Khi tác vụ chủ yếu blocking dài, phụ thuộc tài nguyên ngoài hoặc không thể chia nhỏ một cách hiệu quả; lúc đó cân nhắc executor và kiến trúc phù hợp hơn.

## Tài liệu tham khảo

- [Java SE 21 — ForkJoinTask](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ForkJoinTask.html)
- [Java SE 21 — ForkJoinPool](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ForkJoinPool.html)
- [Java SE 21 — Callable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Callable.html)
- [Java SE 21 — Future](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html)
- [Java SE 21 — RecursiveTask](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/RecursiveTask.html)
- [Java SE 22 — ForkJoinTask (đối chiếu overload mới)](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/util/concurrent/ForkJoinTask.html)
