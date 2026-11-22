# CompletableFuture chưa hoàn tất: complete(), completeExceptionally() và cuộc đua hoàn tất

## 1. Mục tiêu: một kết quả được quyết định về sau

Ở nhiều workflow Java concurrency, ta **chưa có kết quả khi tạo đối tượng**, nhưng muốn đưa ngay cho caller một “tay cầm” để chờ, xử lý tiếp hoặc nhận lỗi. Chẳng hạn: một callback mạng sẽ báo kết quả sau, một worker xử lý request, một hệ thống nhận sự kiện sẽ trả lời theo correlation ID, hoặc nhiều nguồn cùng tranh quyền đưa ra kết quả đầu tiên.

`CompletableFuture<T>` hỗ trợ mô hình **promise có thể hoàn thành bằng tay**:

```java
CompletableFuture<String> promise = new CompletableFuture<>();

// Một lúc sau, một thread khác quyết định outcome:
promise.complete("OK");
```

Khi vừa được tạo bởi `new CompletableFuture<>()`, promise **chưa hoàn tất**. Nó không tự tạo thread, không tự thực thi Supplier hay Runnable, cũng không tự hoàn thành chỉ vì đã được trả cho caller.

Ba cách tác động tới trạng thái được quan tâm:

- **`complete(value)`**: cố hoàn tất bình thường với giá trị được cung cấp, trả `boolean` báo lời gọi có thực hiện chuyển trạng thái thành công hay không.
- **`completeExceptionally(error)`**: cố hoàn tất bất thường với `Throwable` được cung cấp, cũng trả `boolean` báo có thắng cuộc đua hoàn tất hay không.
- **`cancel(mayInterruptIfRunning)`**: cố hoàn tất theo trạng thái hủy. Với `CompletableFuture`, tham số `mayInterruptIfRunning` không được dùng để điều khiển thực thi bằng interrupt.

Điểm cốt lõi là **future chỉ có một lần chuyển từ chưa hoàn tất sang một outcome được chọn**, theo contract của `complete`/`completeExceptionally`/`cancel` thông thường. Các đối thủ cạnh tranh không thể thay kết quả thành công hoặc thất bại đã được quyết định bằng những phương thức hoàn tất thông thường.

Bài thuộc **Java Advance - concurrency → CompletableFuture**, phạm vi **Java concurrency nói chung**; không phụ thuộc Spring hay framework nào.

## 2. Phân biệt constructor với những factory method khác

| Cách tạo | Trạng thái ban đầu | Ai hoàn tất? |
| --- | --- | --- |
| `new CompletableFuture<T>()` | Chưa hoàn tất | Một thread/callback gọi `complete`, `completeExceptionally` hoặc `cancel`; cũng có thể do API khác hoàn tất |
| `CompletableFuture.completedFuture(v)` | Đã hoàn tất bình thường | Giá trị `v` được gắn ngay lúc tạo |
| `CompletableFuture.failedFuture(error)` | Đã hoàn tất bất thường | Throwable được gắn ngay lúc tạo |
| `CompletableFuture.supplyAsync(supplier)` | Có thể chưa hoặc đã hoàn tất khi trả về | Task chạy Supplier và hoàn tất future |
| `CompletableFuture.runAsync(runnable)` | Có thể chưa hoặc đã hoàn tất khi trả về | Task chạy Runnable, thành công với kết quả `null` |

Đừng nhầm **“khởi tạo một future pending”** với **“khởi động một công việc async”**. Constructor `new CompletableFuture<>()` không tự tìm một producer để tạo kết quả. Nếu mọi đường code đều quên hoàn tất nó, `join()` có thể chờ vô hạn.

`completedFuture(v)` không tương đương `new CompletableFuture<>()` cho tới khi bạn gọi `complete(v)`. Sau khi hoàn tất thì cả hai cho phép caller đọc kết quả bình thường, nhưng **trước khi hoàn tất** pending future có thể đăng ký continuation, chờ kết quả hoặc trở thành đối tượng của một cuộc đua giữa các producer.

## 3. Mô hình trạng thái và “first completion wins”

Một cách hình dung trạng thái:

```text
                     INCOMPLETE
                          |
           +--------------+---------------+
           |              |               |
     complete(value)  completeExceptionally  cancel(...)
           |              |               |
           v              v               v
      NORMAL(value)   EXCEPTIONAL(error)  CANCELLED
           \              |               /
            \             |              /
              TERMINAL OUTCOME
```

Sau khi đã hoàn tất, `isDone()` là true. Hoàn tất bình thường có thể có giá trị `null`; hoàn tất bất thường chứa một `Throwable`; hủy được mô hình hóa như một dạng exceptional completion có nguyên nhân `CancellationException`.

Với những phương thức **hoàn tất thông thường**:

- Lời gọi đầu tiên thực sự chuyển future từ chưa hoàn tất sang trạng thái kết thúc **thắng**.
- Các lời gọi cạnh tranh tới sau không thể ghi đè outcome đó.
- `complete` và `completeExceptionally` trả `true` nếu chính lời gọi đó làm future chuyển từ incomplete sang terminal.
- `complete` và `completeExceptionally` trả `false` nếu future đã completed trước khi lời gọi thử thành công.
- `cancel` có chi tiết return value riêng: nó trả `true` khi lời gọi khiến future bị hủy **hoặc future vốn đã ở trạng thái canceled**; không nên đếm số lần `cancel() == true` để suy ra số lần chuyển trạng thái thắng.
- Kết quả đọc bởi `join/get` đến từ outcome đã thắng, trừ khi có thao tác nâng cao chủ đích như `obtrudeValue`/`obtrudeException`.

**Không có quy luật “thread được tạo trước luôn thắng”**. Scheduler, công việc đang chạy, contention và thời điểm thực thi quyết định thứ tự thành công của các lời gọi hoàn tất.

## 4. `complete(value)`: hoàn tất bình thường

Chữ ký:

```java
public boolean complete(T value)
```

Ý nghĩa: nếu future **chưa hoàn tất**, gắn kết quả bình thường `value` và đánh thức/cho phép các dependent stages hoàn tất theo cơ chế của CompletableFuture. Nếu future đã completed, không thay đổi outcome bình thường bằng `complete`, trả false.

### Ví dụ 1: pending → success → lần hoàn tất sau thất bại

Tạo tệp `ManualCompletionBasicsDemo.java`:

```java
import java.util.concurrent.CompletableFuture;

public class ManualCompletionBasicsDemo {
    public static void main(String[] args) {
        CompletableFuture<String> promise = new CompletableFuture<>();

        System.out.println("initial done=" + promise.isDone());

        boolean first = promise.complete("READY");
        boolean second = promise.complete("TOO_LATE");

        System.out.println("first accepted=" + first);
        System.out.println("second accepted=" + second);
        System.out.println("final done=" + promise.isDone());
        System.out.println("result=" + promise.join());
    }
}
```

Biên dịch/chạy bằng **JDK 17+**:

```bash
javac ManualCompletionBasicsDemo.java
java ManualCompletionBasicsDemo
```

Output:

```text
initial done=false
first accepted=true
second accepted=false
final done=true
result=READY
```

Trước `complete`, promise chưa có outcome. Sau `complete("READY")` thành công, `join()` trả `"READY"`. Lời gọi `complete("TOO_LATE")` không đổi giá trị vì future đã terminal.

### Giá trị null hợp lệ

`CompletableFuture<String>` có thể được hoàn tất bình thường bằng:

```java
promise.complete(null);
```

Điều đó khác `completeExceptionally(null)`. Với `complete(null)`, `join()` trả null khi thành công; với `completeExceptionally(null)`, `Throwable` không hợp lệ và phương thức ném `NullPointerException` thay vì hoàn tất future bằng lỗi null.

**Không dùng `join() == null` làm cách kiểm tra future còn pending:** `join()` chờ nếu pending; null có thể là giá trị thành công thực sự.

## 5. `completeExceptionally(error)`: hoàn tất bằng lỗi

Chữ ký:

```java
public boolean completeExceptionally(Throwable ex)
```

Method này cố đưa future vào **exceptional completion** bằng một `Throwable` không null. Caller quan sát failure qua:

- `join()`: thường ném `CompletionException`, với `getCause()` là lỗi.
- `get()`: ném `ExecutionException` (checked) khi future hoàn tất bất thường, với `getCause()` là lỗi.
- `isCompletedExceptionally()`: true đối với future hoàn tất bất thường, kể cả cancellation.
- `isDone()`: true.
- `isCancelled()`: false đối với một lỗi bình thường như `IllegalStateException`; cần phân biệt với cancellation.

Nếu future đã thành công trước đó, `completeExceptionally` trả false và **không thể đổi success thành failure** bằng lời gọi này.

### Ví dụ 2: truy lỗi qua join và get

Tạo tệp `ManualExceptionalCompletionDemo.java`:

```java
import java.io.IOException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

public class ManualExceptionalCompletionDemo {
    public static void main(String[] args) throws InterruptedException {
        CompletableFuture<Integer> promise = new CompletableFuture<>();

        boolean first = promise.completeExceptionally(
                new IOException("source unavailable"));
        boolean late = promise.complete(42);

        System.out.println("exception accepted=" + first);
        System.out.println("late value accepted=" + late);
        System.out.println("done=" + promise.isDone());
        System.out.println("exceptional="
                + promise.isCompletedExceptionally());
        System.out.println("cancelled=" + promise.isCancelled());

        try {
            promise.join();
        } catch (CompletionException e) {
            System.out.println("join wrapper="
                    + e.getClass().getSimpleName());
            System.out.println("join cause="
                    + e.getCause().getClass().getSimpleName());
            System.out.println("join message=" + e.getCause().getMessage());
        }

        try {
            promise.get();
        } catch (ExecutionException e) {
            System.out.println("get wrapper="
                    + e.getClass().getSimpleName());
            System.out.println("get cause="
                    + e.getCause().getClass().getSimpleName());
        }
    }
}
```

```bash
javac ManualExceptionalCompletionDemo.java
java ManualExceptionalCompletionDemo
```

Output:

```text
exception accepted=true
late value accepted=false
done=true
exceptional=true
cancelled=false
join wrapper=CompletionException
join cause=IOException
join message=source unavailable
get wrapper=ExecutionException
get cause=IOException
```

Đây là một lỗi đã **được đưa vào promise một cách chủ động**, không phải do `join/get` tự tạo ra. `join/get` là các điểm **quan sát outcome**.

**Đừng chỉ log `e.getMessage()`** của wrapper rồi bỏ `getCause()`. Lỗi gốc và cause chain, stack trace, task ID mới giúp chẩn đoán.

## 6. Cuộc đua hoàn tất: một promise, nhiều producer

Giả sử ba nguồn trả lời cùng một yêu cầu:

```text
Producer A: complete("A")
Producer B: complete("B")
Watchdog: completeExceptionally(timeoutError)

                 \    |    /
                  \   |   /
                  [ shared future ]
                         |
             chỉ một transition thắng
                         |
              consumer nhận outcome
```

Các producer có thể chạy đồng thời. Dùng `CompletableFuture` như “**one-shot arbitration**” giúp chọn ra **một outcome đầu tiên được chấp nhận**, nhưng không tự dừng các producer thua cuộc và không hủy side effect họ có thể đang làm.

**Thao tác linearizable:** với một future pending, các lời gọi `complete/completeExceptionally` cạnh tranh để đặt outcome cuối. Chúng cung cấp một điểm quyết định nguyên tử mà caller có thể quan sát qua boolean return và kết quả future.

Vì không biết ai thắng, test đúng không nên giả định A luôn thắng. Test cần khẳng định:

1. Chỉ **một** trong các lời gọi complete hoặc completeExceptionally có return true trong cuộc đua một lần.
2. Future đã done.
3. Outcome là một trong những outcome hợp lệ của các contender.
4. Không thể dùng late `complete` để thay outcome.

### Tình huống business

Một gateway nhận response từ **server-primary** và **server-backup**, đồng thời có watchdog timeout. Future chỉ nhận outcome đến trước, nhưng hai request mạng còn lại có thể vẫn chạy. Cần chính sách cancel/release resource, tránh gửi yêu cầu có side effect trùng khi cả hai server cùng nhận request.

## 7. Ví dụ 3: kiểm thử cuộc đua không đoán winner

Tạo tệp `ConcurrentCompletionRaceDemo.java`:

```java
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class ConcurrentCompletionRaceDemo {
    public static void main(String[] args) throws InterruptedException {
        CompletableFuture<String> promise = new CompletableFuture<>();
        CountDownLatch ready = new CountDownLatch(3);
        CountDownLatch start = new CountDownLatch(1);
        AtomicInteger winners = new AtomicInteger();

        Runnable successA = () -> {
            ready.countDown();
            try {
                start.await();
                if (promise.complete("A")) {
                    winners.incrementAndGet();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Runnable successB = () -> {
            ready.countDown();
            try {
                start.await();
                if (promise.complete("B")) {
                    winners.incrementAndGet();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Runnable failure = () -> {
            ready.countDown();
            try {
                start.await();
                if (promise.completeExceptionally(
                        new IllegalStateException("timeout"))) {
                    winners.incrementAndGet();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Thread a = new Thread(successA, "producer-A");
        Thread b = new Thread(successB, "producer-B");
        Thread c = new Thread(failure, "watchdog");

        a.start();
        b.start();
        c.start();
        ready.await();
        start.countDown();

        a.join();
        b.join();
        c.join();

        boolean validOutcome;
        if (promise.isCompletedExceptionally()) {
            try {
                promise.join();
                validOutcome = false;
            } catch (CompletionException e) {
                validOutcome = e.getCause()
                        instanceof IllegalStateException;
            }
        } else {
            validOutcome = Set.of("A", "B").contains(promise.join());
        }

        System.out.println("accepted completions=" + winners.get());
        System.out.println("done=" + promise.isDone());
        System.out.println("valid outcome=" + validOutcome);
        System.out.println("late write="
                + promise.complete("AFTER_RACE"));
    }
}
```

```bash
javac ConcurrentCompletionRaceDemo.java
java ConcurrentCompletionRaceDemo
```

Output khi không có interrupt ngoài ý muốn:

```text
accepted completions=1
done=true
valid outcome=true
late write=false
```

**Chủ ý không in tên winner cố định.** A, B hoặc watchdog có thể thắng theo lịch chạy. `CountDownLatch` giúp cả ba thread sẵn sàng rồi cùng có cơ hội thử, nhưng **không** ép một thứ tự cụ thể. Chỉ một `complete`/`completeExceptionally` có thể thành công trong cuộc đua này.

Đây là cách kiểm thử concurrency đúng: **khẳng định invariant và tập outcome hợp lệ**, không assert thread nào nhận CPU đầu tiên.

## 8. Cuộc đua value và exception: ai hoàn tất trước?

Hai tình huống:

**Tình huống A: success trước, failure sau**

```java
CompletableFuture<Integer> promise = new CompletableFuture<>();
boolean success = promise.complete(10);                 // true
boolean failure = promise.completeExceptionally(
        new IllegalStateException("late"));            // false
int value = promise.join();                             // 10
```

Đây là đoạn minh họa. Outcome là success, dù producer khác đến sau cho rằng có lỗi.

**Tình huống B: failure trước, success sau**

```java
CompletableFuture<Integer> promise = new CompletableFuture<>();
boolean failure = promise.completeExceptionally(
        new IllegalStateException("first"));           // true
boolean success = promise.complete(10);                // false
// promise.join() ném CompletionException có cause IllegalStateException
```

Không có cơ chế “success luôn có ưu tiên hơn exception” hoặc “exception luôn thắng success”. **Đầu tiên thành công trong cuộc đua** là điều quyết định.

Với hệ thống cần policy khác, chẳng hạn **đợi xem có bất kỳ kết quả thành công nào trước deadline** thay vì lấy outcome đầu tiên, thì một `CompletableFuture` cạnh tranh trực tiếp như trên **chưa đủ**. Cần một bộ điều phối theo dõi số nguồn, loại outcome và deadline rồi mới gọi complete trên promise tổng.

## 9. `isDone()` không chứng minh success

`isDone() == true` có thể xảy ra sau:

- `complete("OK")`.
- `complete(null)`.
- `completeExceptionally(new IOException(...))`.
- `cancel(true)` hoặc `cancel(false)`.
- Một timeout action hoàn tất future bất thường, ví dụ `orTimeout`.

Vì vậy:

```java
if (future.isDone()) {
    // Không thể kết luận kết quả thành công tại đây!
}
```

Đây là phản ví dụ về suy luận. Muốn biết outcome:

- Dùng `get()/join()` và phân biệt success vs exception/cancel.
- Dùng `whenComplete((value,error) -> ...)` để quan sát.
- `isCompletedExceptionally()` cho biết lỗi/hủy, nhưng không trả cause.
- `isCancelled()` chuyên biệt hơn cho cancellation.

**Check-then-act race:** kiểm tra `!future.isDone()` rồi `future.complete(value)` không bảo đảm lời gọi complete sẽ thành công: một thread khác có thể complete trong khoảng đó. Hãy **dựa vào boolean trả về của `complete`**, không dựa vào pre-check.

## 10. `cancel()` trong cuộc đua hoàn tất

`CompletableFuture.cancel(boolean mayInterruptIfRunning)` là một cách hoàn tất bất thường theo trạng thái cancel. Với CompletableFuture, tham số `mayInterruptIfRunning` **không được dùng để gửi interrupt để điều khiển công việc**.

Các trường hợp:

- Pending future bị `cancel(true)`/`cancel(false)`: future chuyển canceled.
- `join()` trên canceled future thường ném `CancellationException` trực tiếp.
- `get()` trên canceled future ném `CancellationException`.
- `complete(value)` sau cancellation trả false.
- `completeExceptionally(error)` sau cancellation trả false.
- Nếu success/failure đã terminal trước, `cancel(...)` không thể thay outcome đó.
- Các lần `cancel()` gọi trên một future **đã bị hủy** có thể vẫn trả true. Vì vậy return true của `cancel` không tương đương với “tôi là người đầu tiên hủy”.

### Ví dụ 4: hủy một future pending

Tạo tệp `PendingCancellationDemo.java`:

```java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;

public class PendingCancellationDemo {
    public static void main(String[] args) {
        CompletableFuture<String> promise = new CompletableFuture<>();

        boolean firstCancel = promise.cancel(true);
        boolean repeatedCancel = promise.cancel(false);
        boolean lateValue = promise.complete("LATE");

        System.out.println("first cancel=" + firstCancel);
        System.out.println("repeated cancel=" + repeatedCancel);
        System.out.println("late value=" + lateValue);
        System.out.println("done=" + promise.isDone());
        System.out.println("cancelled=" + promise.isCancelled());
        System.out.println("exceptional="
                + promise.isCompletedExceptionally());

        try {
            promise.join();
        } catch (CancellationException e) {
            System.out.println("join cancellation="
                    + e.getClass().getSimpleName());
        }
    }
}
```

```bash
javac PendingCancellationDemo.java
java PendingCancellationDemo
```

Output:

```text
first cancel=true
repeated cancel=true
late value=false
done=true
cancelled=true
exceptional=true
join cancellation=CancellationException
```

Đây là ví dụ **không có worker**; cancellation chỉ điều khiển trạng thái của promise. Nếu một producer đã bắt đầu tính toán ở thread khác và tiếp tục chạy, cancel trạng thái promise **không tự ngắt hoặc rollback producer**.

**Không dùng `cancel(true)` như một lệnh kill thread.** Cần cooperative cancellation qua token, timeouts của I/O, quyền sở hữu executor hoặc cách dừng task được thiết kế riêng.

## 11. `completeExceptionally(new CancellationException(...))` so với `cancel()`

Một `CompletableFuture` có thể hoàn tất bất thường do `CancellationException` được cung cấp tường minh:

```java
CompletableFuture<String> f = new CompletableFuture<>();
f.completeExceptionally(
        new java.util.concurrent.CancellationException("not needed"));
```

Đây là đoạn minh họa. Các phương thức quan sát của `CompletableFuture` có thể coi exceptional completion do `CancellationException` là cancelled. Nhưng **đừng dùng một `CancellationException` làm lỗi nghiệp vụ tùy ý** chỉ vì thích tên class. Nếu công việc bị hủy theo yêu cầu caller, `cancel` truyền tải ý nghĩa rõ hơn; nếu task thất bại do logic khác, hãy sử dụng loại exception thể hiện đúng nguyên nhân.

Với các dependent stages, cancellation của source thường khiến dependent hoàn tất bất thường, có thể thông qua `CompletionException` bọc `CancellationException`. **Không suy ra mọi dependent đều tự có `isCancelled()==true`** khi source bị cancel; cần xem outcome của từng stage.

## 12. Dependent stages được kích hoạt sau khi promise hoàn tất

Một pending `CompletableFuture` có thể có continuation được đăng ký **trước** khi kết quả được đưa vào:

```java
CompletableFuture<Integer> source = new CompletableFuture<>();

CompletableFuture<Integer> doubled =
        source.thenApply(x -> x * 2);

source.complete(21);

int result = doubled.join(); // 42
```

Nếu `source` hoàn tất bình thường, `thenApply` nhận giá trị và tạo output stage. Nếu `source` hoàn tất bất thường, callback biến đổi thành công thường **không được chạy**; dependent stage hoàn tất bất thường theo chain.

Quan trọng: `thenApply` **không có `Async`** có thể chạy ngay trong thread gọi `complete`. Vì vậy đừng mặc định `complete` chỉ là một phép gán O(1) không gây chạy logic ứng dụng: việc hoàn tất có thể kích hoạt các dependent actions tương ứng.

### Ví dụ 5: producer hoàn tất, consumer dùng stage

Tạo tệp `ManualCompletionPipelineDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ManualCompletionPipelineDemo {
    public static void main(String[] args) throws InterruptedException {
        CompletableFuture<Integer> source = new CompletableFuture<>();
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            CompletableFuture<Integer> doubled =
                    source.thenApply(x -> x * 2);
            CompletableFuture<Integer> plusOne =
                    doubled.thenApplyAsync(x -> x + 1, executor);

            System.out.println("source initially=" + source.isDone());
            System.out.println("complete accepted=" + source.complete(21));
            System.out.println("source result=" + source.join());
            System.out.println("doubled result=" + doubled.join());
            System.out.println("plus one=" + plusOne.join());
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
```

```bash
javac ManualCompletionPipelineDemo.java
java ManualCompletionPipelineDemo
```

Output:

```text
source initially=false
complete accepted=true
source result=21
doubled result=42
plus one=43
```

`source.complete(21)` làm source terminal và cho phép dependent stages chạy. `thenApply` có thể chạy ngay trên caller; `thenApplyAsync(..., executor)` được nộp qua executor và có thể chạy trên worker của executor. Không dựa vào tên thread để chứng minh giá trị; kết quả 42 và 43 xuất phát từ logic toán học và các điểm `join()`.

## 13. Callback inline có thể gây block ngay lúc `complete()`

Ví dụ:

```java
CompletableFuture<String> pending = new CompletableFuture<>();
pending.thenApply(value -> {
    performSlowWork();
    return value.length();
});
pending.complete("hello");
```

Đây là đoạn minh họa, `performSlowWork()` do ứng dụng định nghĩa. Khi source được complete, callback `thenApply` có thể được thực thi **ngay trên thread gọi `complete`**. Nếu callback làm I/O hoặc giữ lock lâu, thread hoàn tất source có thể bị giữ lại dù kết quả source đã được quyết định.

Biện pháp:

- Đối với callback ngắn, thuần tính toán, non-Async có thể đơn giản và ít overhead.
- Với callback dài hoặc cần isolation, xem xét `thenApplyAsync(..., executor)` hoặc `whenCompleteAsync(..., executor)`.
- Truyền đúng executor có quyền sở hữu/lifecycle rõ ràng.
- Không chặn vô hạn trong một callback completion nếu các producer còn phụ thuộc vào callback đó.
- Nhớ rằng executor chỉ định có thể từ chối việc khi đang shutdown; dependent stage có thể hoàn tất bất thường vì rejection.

**Một nuance quan trọng:** `complete(value)` có thể làm source trở thành done **trước khi mọi dependent stage hoàn thành**. Nếu cần biết toàn pipeline đã xong, đợi **future cuối cùng** chứ không chỉ nhìn `source.isDone()`.

## 14. Ngoại lệ ở dependent stage khác ngoại lệ ở source

Giả sử source hoàn thành thành công:

```java
CompletableFuture<String> source = new CompletableFuture<>();
CompletableFuture<Integer> mapped = source.thenApply(value -> {
    throw new IllegalArgumentException("mapping failed");
});
source.complete("OK");
```

Khi đó:

- `source` thành công với `"OK"`.
- `mapped` thất bại do callback ném lỗi.
- `source.join()` vẫn trả `"OK"`.
- `mapped.join()` ném `CompletionException` bọc `IllegalArgumentException`.

Không được kết luận rằng “source completed successfully” có nghĩa toàn bộ chuỗi workflow thành công. Mỗi `CompletionStage` có outcome riêng.

Tương tự, nếu một `whenComplete` chỉ nhằm log nhưng callback của nó ném lỗi, stage trả về từ `whenComplete` có thể khác về outcome theo hợp đồng. Cần thiết kế logging không ném lỗi tùy tiện.

## 15. Ví dụ 6: callback lỗi nhưng source vẫn thành công

Tạo tệp `DependentFailureDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class DependentFailureDemo {
    public static void main(String[] args) {
        CompletableFuture<String> source = new CompletableFuture<>();
        CompletableFuture<Integer> mapped =
                source.thenApply(value -> {
                    throw new IllegalArgumentException("bad mapping");
                });

        source.complete("OK");

        System.out.println("source=" + source.join());
        System.out.println("source exceptional="
                + source.isCompletedExceptionally());
        System.out.println("mapped exceptional="
                + mapped.isCompletedExceptionally());

        try {
            mapped.join();
        } catch (CompletionException e) {
            System.out.println("mapped cause="
                    + e.getCause().getClass().getSimpleName());
        }
    }
}
```

```bash
javac DependentFailureDemo.java
java DependentFailureDemo
```

Output:

```text
source=OK
source exceptional=false
mapped exceptional=true
mapped cause=IllegalArgumentException
```

Ví dụ không dùng executor riêng vì việc ném lỗi xảy ra trong continuation. `source.complete("OK")` thiết lập outcome thành công; callback của `mapped` là nơi phát sinh lỗi mới. Caller đọc đúng **future của stage cần quan sát** để tìm lỗi.

## 16. `get()` và `join()` chờ một promise pending

Caller có thể đợi kết quả:

```java
String value = promise.join();
```

Nếu promise chưa hoàn tất, `join()` có thể chờ **vô hạn**. Với `get()` có thể dùng timeout:

```java
String value = promise.get(1, TimeUnit.SECONDS);
```

Phân biệt ngoại lệ:

| API | Outcome thành công | Outcome lỗi | Caller bị interrupt | Timeout |
| --- | --- | --- | --- | --- |
| `join()` | Trả `T` | Thường `CompletionException` | Không khai báo checked interrupt | Không nhận timeout |
| `get()` | Trả `T` | `ExecutionException` | `InterruptedException` | Không nhận timeout |
| `get(timeout, unit)` | Trả `T` | `ExecutionException` | `InterruptedException` | `TimeoutException` nếu chưa xong |
| `getNow(defaultValue)` | Trả `T` nếu done bình thường | Ném unchecked exception nếu done lỗi/hủy | Không chặn | Trả default nếu chưa done |

`get(timeout)` hết thời gian chờ **không tự hoàn tất promise**. Caller có thể timeout còn producer vẫn tiếp tục làm việc và complete về sau. Nếu timeout phải trở thành outcome của **chính promise**, có thể dùng `orTimeout` hoặc tự gọi `completeExceptionally` từ watchdog theo policy.

## 17. Timeout của caller khác hoàn tất promise bằng lỗi timeout

Hai kịch bản:

**A. Chỉ có caller hết thời gian chờ**

```java
try {
    promise.get(100, TimeUnit.MILLISECONDS);
} catch (TimeoutException e) {
    // Promise có thể vẫn incomplete và sau đó hoàn thành thành công.
}
```

Đây là đoạn minh họa, `promise` và import được cung cấp, checked exceptions xử lý ở tầng bao quanh. Outcome của promise không bị thay đổi bởi việc `get` hết hạn.

**B. Watchdog cố hoàn tất promise bằng lỗi**

```java
boolean accepted = promise.completeExceptionally(
        new TimeoutException("request expired"));
```

Nếu watchdog thắng cuộc đua, promise đã exceptional. Producer đến sau gọi `complete(value)` sẽ trả false. Nếu producer thắng trước, watchdog trả false và kết quả thành công còn nguyên.

**Đây là hai thiết kế API khác nhau.** A chỉ giới hạn thời gian caller **đợi**; B xác định “hết deadline là outcome chung của request”. Cần lựa chọn theo contract nghiệp vụ.

### Khi deadline đã hết

Nếu producer có side effect bên ngoài, hoàn tất promise bằng timeout không tự dừng task, không rollback database và không hủy request ngoài JVM. Phải có cancellation/cleanup riêng.

## 18. `orTimeout`: một contender hoàn tất bất thường

Trong Java 17, `CompletableFuture.orTimeout(timeout, unit)` thiết lập để future **hoàn tất bất thường với `TimeoutException` nếu nó vẫn incomplete khi timeout tới**. Method này trả về **chính CompletableFuture** đó, không phải một wrapper hoàn toàn độc lập.

```java
CompletableFuture<String> promise = new CompletableFuture<>();
promise.orTimeout(200, TimeUnit.MILLISECONDS);
```

Nếu producer `complete("OK")` trước timeout, future vẫn thành công và timeout action không được quyền ghi đè bằng hoàn tất thông thường. Nếu timeout thắng, producer gọi `complete` sau đó trả false.

### Ví dụ 7: orTimeout chắc chắn thắng khi không có producer

Tạo tệp `OrTimeoutPendingDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class OrTimeoutPendingDemo {
    public static void main(String[] args) {
        CompletableFuture<String> promise = new CompletableFuture<>();
        CompletableFuture<String> same =
                promise.orTimeout(20, TimeUnit.MILLISECONDS);

        System.out.println("same instance=" + (same == promise));

        try {
            promise.join();
        } catch (CompletionException e) {
            System.out.println("cause="
                    + e.getCause().getClass().getSimpleName());
            System.out.println("timeout cause="
                    + (e.getCause() instanceof TimeoutException));
        }

        System.out.println("done=" + promise.isDone());
        System.out.println("late success=" + promise.complete("LATE"));
    }
}
```

```bash
javac OrTimeoutPendingDemo.java
java OrTimeoutPendingDemo
```

Output nếu JVM tiếp tục thực thi và không bị can thiệp bất thường:

```text
same instance=true
cause=TimeoutException
timeout cause=true
done=true
late success=false
```

Không có producer nào để complete trước timeout, nên watchdog cuối cùng đưa promise vào exceptional completion. `orTimeout` thay đổi **chính future được gọi**, vì vậy những nơi khác giữ reference cùng promise cũng nhận outcome timeout.

## 19. `completeOnTimeout`: timeout thành một kết quả thành công

`completeOnTimeout(value, timeout, unit)` gần giống `orTimeout` ở việc lên lịch một lựa chọn hoàn tất khi chưa done, nhưng nếu timeout thắng thì nó hoàn tất **bình thường** bằng giá trị `value`:

```java
promise.completeOnTimeout("FALLBACK", 100, TimeUnit.MILLISECONDS);
```

Method cũng trả về **chính CompletableFuture** được gọi. Nếu producer hoàn tất trước, fallback không ghi đè. Nếu fallback thắng, producer hoàn tất sau đó trả false.

### Ví dụ 8: fallback thắng

Tạo tệp `CompleteOnTimeoutDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

public class CompleteOnTimeoutDemo {
    public static void main(String[] args) {
        CompletableFuture<String> promise = new CompletableFuture<>();

        CompletableFuture<String> returned =
                promise.completeOnTimeout(
                        "FALLBACK", 20, TimeUnit.MILLISECONDS);

        System.out.println("same instance=" + (returned == promise));
        System.out.println("result=" + promise.join());
        System.out.println("late normal=" + promise.complete("ACTUAL"));
        System.out.println("exceptional="
                + promise.isCompletedExceptionally());
    }
}
```

```bash
javac CompleteOnTimeoutDemo.java
java CompleteOnTimeoutDemo
```

Output khi không có producer khác:

```text
same instance=true
result=FALLBACK
late normal=false
exceptional=false
```

**Cảnh báo:** trả `FALLBACK` **không chứng minh nguồn dữ liệu thật đã hoàn tất**. Nếu cần phân biệt nguồn thật và fallback, nên dùng kiểu kết quả có metadata như `Result(value, fromFallback)` hoặc một sealed hierarchy phù hợp.

Một fallback hợp lệ cho hiển thị có thể là dữ liệu cache cũ; fallback mặc định cho giao dịch tài chính có thể là lựa chọn sai nghiêm trọng. Đây là quyết định nghiệp vụ, không phải quyết định của CompletableFuture.

## 20. Ba cuộc đua timeout: complete, exceptional, cancel

Một pending promise có thể cùng lúc nhận:

```text
Thread IO       -> complete(response)
Thread watchdog -> completeExceptionally(new TimeoutException())
Thread caller   -> cancel(true)
```

Outcome phụ thuộc **lời gọi hoàn tất thắng trước**. Không có bảo đảm timeout luôn thắng sau khi wall clock qua mốc nếu producer đã complete trước khi timeout action thực thi; cũng không có bảo đảm producer được ưu tiên.

Để làm rõ policy:

- Nếu **success thắng**, caller nhận response; timeout/cancel đến sau không thay bằng complete thông thường.
- Nếu **exception thắng**, caller nhận lỗi; success đến sau bị bỏ khỏi trạng thái promise.
- Nếu **cancel thắng**, caller nhận `CancellationException`; hai lời gọi complete đến sau thất bại.
- Các producer thua cuộc vẫn có thể thực thi logic bên ngoài; muốn dừng phải có giao thức riêng.

Một hệ thống phân tán đôi khi cần “deadline theo thời gian thực” chặt hơn “timeout task đã kịp chạy”: kiểm tra `System.nanoTime()` và điều phối bằng một state machine chứa deadline, không chỉ tin vào thứ tự thread được scheduler gọi.

## 21. Tại sao không `if (!isDone()) complete(...)`?

Phản ví dụ:

```java
if (!promise.isDone()) {
    promise.complete("OK");
    sendAcknowledgement();
}
```

Nếu một thread khác complete **giữa** hai lệnh, `promise.complete("OK")` trả false nhưng `sendAcknowledgement()` vẫn chạy, như thể thread hiện tại thắng.

Đúng hơn:

```java
if (promise.complete("OK")) {
    sendAcknowledgement();
}
```

Đây là đoạn minh họa. Boolean trả về là kết quả quyết định **thắng/thua của lời gọi complete**.

**Nhưng vẫn có giới hạn:** `sendAcknowledgement()` không nằm trong cùng một transaction với `complete()`. Nếu ack gửi lỗi hoặc process crash giữa hai bước, không có exactly-once guarantee. Cần thiết kế idempotency/outbox/transaction nếu ack là side effect quan trọng.

Tương tự, nếu `completeExceptionally` trả false, đừng tự ghi nhận “timeout đã thắng” dù watchdog vừa chạy. Phải quan sát outcome thực tế hoặc ghi metric “timeout attempt lost”.

## 22. Ví dụ 9: mô phỏng success thắng timeout một cách xác định

Tạo tệp `DeterministicSuccessWinsDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;

public class DeterministicSuccessWinsDemo {
    public static void main(String[] args) throws InterruptedException {
        CompletableFuture<String> promise = new CompletableFuture<>();
        CountDownLatch successWritten = new CountDownLatch(1);
        AtomicBoolean timeoutAccepted = new AtomicBoolean();

        Thread success = new Thread(() -> {
            promise.complete("RESPONSE");
            successWritten.countDown();
        });

        Thread timeout = new Thread(() -> {
            try {
                successWritten.await();
                timeoutAccepted.set(
                        promise.completeExceptionally(
                                new TimeoutException("late watchdog")));
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        success.start();
        timeout.start();
        success.join();
        timeout.join();

        System.out.println("result=" + promise.join());
        System.out.println("timeout accepted=" + timeoutAccepted.get());
        System.out.println("done=" + promise.isDone());
    }
}
```

```bash
javac DeterministicSuccessWinsDemo.java
java DeterministicSuccessWinsDemo
```

Output khi không bị interrupt bên ngoài:

```text
result=RESPONSE
timeout accepted=false
done=true
```

`CountDownLatch` ép watchdog chỉ thử `completeExceptionally` **sau khi** source success đã được cài. Đây là bài test **policy success trước timeout**, không phải kiểm tra thắng thua ngẫu nhiên. Để kiểm tra race thực sự không áp đặt thứ tự, dùng `ConcurrentCompletionRaceDemo` ở mục 7.

## 23. Cuộc đua của nhiều callback và hậu quả về thứ tự

Một `CompletableFuture` có thể có nhiều dependent stages:

```java
source.thenAccept(value -> auditA(value));
source.thenAccept(value -> auditB(value));
source.thenAccept(value -> auditC(value));
```

Đây là đoạn minh họa với helper ứng dụng. Khi source complete, các action đủ điều kiện chạy nhưng **không nên dựa vào thứ tự A/B/C** trừ khi pipeline tạo dependency rõ ràng.

Nếu bắt buộc audit B chạy sau audit A, có thể tạo chuỗi:

```java
CompletableFuture<Void> ordered =
        source.thenAccept(value -> auditA(value))
              .thenRun(() -> auditB());
```

Đây là đoạn minh họa. `thenRun` chỉ chạy khi stage trước thành công. Các callbacks độc lập được đăng ký với cùng source không có contract “theo thứ tự đăng ký”.

Cũng lưu ý **thời điểm complete() trả về không nhất thiết là thời điểm mọi stage phụ thuộc đã chạy xong**. Việc hoàn tất source và việc hoàn thành toàn bộ pipeline là hai sự kiện khác nhau. Dùng `ordered.join()` hoặc future cuối để xác nhận tất cả bước yêu cầu đã hoàn tất.

## 24. Hoàn tất future từ callback bên ngoài

Một API callback có thể không trả `CompletionStage` mà gọi `onSuccess/onFailure` về sau. Ta có thể bọc bằng một pending future:

```java
CompletableFuture<String> promise = new CompletableFuture<>();

api.start(
    value -> promise.complete(value),
    error -> promise.completeExceptionally(error)
);

return promise;
```

Đây là **pseudocode minh họa**: `api.start` và callbacks do thư viện/ứng dụng định nghĩa. Để dùng an toàn phải có:

1. **Chính sách callback một lần:** thư viện có thể gọi callback bất thường nhiều lần; dùng return `boolean` để phát hiện late/duplicate notifications.
2. **Lỗi ngay khi đăng ký:** `api.start` có thể ném exception đồng bộ; cần completeExceptionally trong catch hoặc trả lỗi đúng hợp đồng.
3. **Timeout/cancel:** caller có thể không chờ vô hạn; nên gắn deadline và cơ chế dừng nguồn bên ngoài.
4. **Vòng đời tài nguyên:** nếu caller cancel promise, chưa chắc `api` đã được hủy.
5. **Context và correlation ID:** nhiều request đồng thời cần bảo đảm callback đúng promise của request đó.
6. **Publisher có nhiều sự kiện:** một CompletableFuture chỉ biểu diễn **một terminal outcome**, không phải một stream dữ liệu nhiều event. Nếu cần phát liên tục, dùng một abstraction khác như `Flow.Publisher` hoặc queue.

**Không nên hoàn tất promise bằng callback trước khi đăng ký các resource/cleanup cần thiết**, nếu điều đó làm consumer bắt đầu xử lý khi producer chưa sẵn sàng. Thiết kế ownership cho state machine của request.

## 25. Ví dụ 10: mô phỏng adapter callback có thể báo hai lần

Tạo tệp `CallbackAdapterDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicInteger;

public class CallbackAdapterDemo {
    static void simulateCallback(
            java.util.function.Consumer<String> onSuccess,
            java.util.function.Consumer<Throwable> onFailure) {

        onSuccess.accept("DATA");
        onFailure.accept(new IllegalStateException("late error"));
    }

    public static void main(String[] args) {
        CompletableFuture<String> promise = new CompletableFuture<>();
        AtomicInteger accepted = new AtomicInteger();

        simulateCallback(
                value -> {
                    if (promise.complete(value)) {
                        accepted.incrementAndGet();
                    }
                },
                error -> {
                    if (promise.completeExceptionally(error)) {
                        accepted.incrementAndGet();
                    }
                }
        );

        System.out.println("accepted=" + accepted.get());
        System.out.println("result=" + promise.join());
        System.out.println("exceptional="
                + promise.isCompletedExceptionally());
    }
}
```

```bash
javac CallbackAdapterDemo.java
java CallbackAdapterDemo
```

Output:

```text
accepted=1
result=DATA
exceptional=false
```

Adapter được viết để **cố tình** báo success rồi failure; failure đến sau không thay result. Đây là tình huống giúp minh họa duplicate/late callback. Trong API thật, có thể log một late completion riêng như một tín hiệu lỗi protocol, nhưng không tự gửi một response thứ hai cho consumer.

## 26. Đảm bảo promise không bị bỏ quên mãi ở trạng thái pending

`new CompletableFuture<>()` rất linh hoạt nhưng cũng dễ bị quên hoàn tất một nhánh:

```java
CompletableFuture<String> promise = new CompletableFuture<>();

if (inputValid) {
    startAsyncWork(promise);
}
// Nếu input không hợp lệ và không có else, promise cứ pending.
return promise;
```

Đây là **phản ví dụ**. Caller có thể chờ vô hạn và các dependent stages vẫn chờ.

Khi thiết kế adapter, hãy vạch tất cả đường đi:

- Nguồn thành công → `complete(value)`.
- Nguồn thất bại → `completeExceptionally(error)`.
- Không thể bắt đầu công việc → hoàn tất lỗi hoặc ném exception theo API.
- Caller hủy → đóng/cancel nguồn bên ngoài nếu contract yêu cầu.
- Hết hạn → `orTimeout` hoặc watchdog có error/fallback rõ ràng.
- Process/service shutdown → quyết định outcome cho các promise còn pending và giải phóng tài nguyên.
- Callback đến sau khi timeout/hủy → `complete` trả false; code không được giả định lời gọi thắng.

Cần đặt **mốc timeout hợp lý**, ưu tiên truyền deadline end-to-end thay vì mỗi bước được chờ hết một timeout mới.

## 27. Pending future có thể giữ dependent stages và dữ liệu lâu

Khi tạo nhiều dependent stages trên một pending CompletableFuture:

```java
source.thenApply(value -> expensiveObject.transform(value));
```

Đây là đoạn minh họa. Closure có thể giữ reference tới `expensiveObject`, request context, buffer hoặc resource khác. Nếu source **không bao giờ complete**, các dependent actions và references có thể bị giữ lâu hơn dự kiến.

Điều đó có thể tạo **memory retention** đáng kể ở service xử lý hàng trăm nghìn request. Future pending không phải một leak trong mọi trường hợp; nó là trạng thái hợp lệ khi producer còn chạy. Nhưng khi request logic đã kết thúc mà promise vẫn pending, các callbacks/waiters không được giải phóng như mong đợi.

Giảm rủi ro bằng:

- Owner rõ ràng cho mỗi promise; đặt deadline và cleanup.
- Không đăng ký callback mới lặp lại mãi vào cùng pending future.
- Gỡ correlation ID khỏi pending request map khi hoàn tất/hủy.
- Hạn chế capture object lớn trong lambda nếu không cần.
- Monitor số promise pending và thời gian sống, không chỉ số thread.
- Không giữ queue vô hạn những công việc chờ một future không có producer.

`getNumberOfDependents()` tồn tại để ước lượng số dependent chưa hoàn tất nhưng chỉ phù hợp **giám sát/debug**, không phải một bộ đếm chính xác để điều khiển correctness.

## 28. Deadline end-to-end: không reset timeout qua nhiều bước

Một workflow có thể dùng:

```java
a.get(1, TimeUnit.SECONDS);
b.get(1, TimeUnit.SECONDS);
c.get(1, TimeUnit.SECONDS);
```

Nếu mỗi lời gọi có timeout 1 giây, tổng thời gian chờ có thể gần 3 giây. Khi nghiệp vụ yêu cầu **tổng 1 giây**, phải dùng một time budget chung.

Ý tưởng:

```java
long startedAt = System.nanoTime();
long totalNanos = TimeUnit.SECONDS.toNanos(1);

long remaining = Math.max(
        0L, totalNanos - (System.nanoTime() - startedAt));
String first = a.get(remaining, TimeUnit.NANOSECONDS);

remaining = Math.max(
        0L, totalNanos - (System.nanoTime() - startedAt));
String second = b.get(remaining, TimeUnit.NANOSECONDS);
```

Đây là đoạn minh họa trong method khai báo checked exceptions thích hợp, với `a` và `b` là `CompletableFuture<String>`. `System.nanoTime()` dùng đo elapsed monotonic trong cùng JVM, không phải Unix timestamp.

Khi hết budget, caller có thể ngừng chờ, completeExceptionally trên promise tổng, hoặc yêu cầu cancel theo chính sách. Đừng tự coi `TimeoutException` từ `get(timeout)` là bằng chứng nguồn đã dừng.

## 29. Java Memory Model: công bố kết quả giữa các thread

Một bên producer thường xây kết quả rồi complete:

```java
Result result = buildResult();
promise.complete(result);
```

Consumer ở thread khác gọi `promise.get()`/`join()` rồi đọc kết quả. `CompletableFuture` triển khai cơ chế đồng bộ cho completion, và `Future.get()` có bảo đảm memory consistency giúp công bố những hành động của asynchronous computation tới thread đã nhận kết quả.

Nhưng phải hiểu đúng:

- **Hoàn tất future công bố tham chiếu kết quả**, không clone object.
- Nếu producer tiếp tục sửa một mutable object **sau khi complete** mà không có đồng bộ, reader có thể gặp data race.
- Nếu result là immutable object được xây đầy đủ trước `complete`, consumer dễ lập luận correctness hơn.
- Nếu producer ném lỗi sau khi complete success, future không tự đổi thành failure.
- Nếu producer thực hiện side effect ngoài JVM trước/sau completion, CompletableFuture không tạo transaction cho database, filesystem hoặc mạng.

Một mẫu an toàn thường là tạo một immutable record/DTO hoàn chỉnh rồi mới `complete(result)`. Đừng `complete(new ArrayList<>())` sau đó cho nhiều thread cùng thêm vào list không đồng bộ.

### Happens-before và callback

Dependent stages quan sát kết quả đã hoàn thành theo giao thức đồng bộ của CompletableFuture. Tuy nhiên, nếu callback lấy một shared mutable object khác không liên quan và sửa nó đồng thời, future không tự giải quyết data race ở object đó. Dùng ownership, lock, atomic hoặc concurrent collection phù hợp.

## 30. Tránh dùng `join()` bên trong producer đang giữ lock

Một rủi ro liveness:

- Thread A giữ lock L rồi đợi `promise.join()`.
- Thread B cần lock L để tính kết quả và gọi `promise.complete(...)`.
- A không nhả L vì đang chờ; B không lấy được L; promise không bao giờ hoàn tất.

Đó là **deadlock** do giao thức lock và completion, không phải lỗi của `join` riêng lẻ.

Một rủi ro khác: thread A đang gọi `complete()` trong lúc giữ lock L. Dependent callback không-Async được kích hoạt inline và cố gọi API chờ thread B; B lại cần lock L. Kết quả có thể deadlock hoặc latency tăng bất thường.

Khuyến nghị:

1. Tránh gọi một callback completion phức tạp khi đang giữ lock nghiệp vụ nếu callback có thể chạy inline.
2. Tránh block vào `join/get` trong critical section khi producer cần cùng lock.
3. Dùng continuation nhẹ và executor rõ ràng nếu cần phân tách.
4. Sắp xếp lock order và ownership thống nhất.
5. Có deadline/cancel cho những chờ có thể kéo dài; nhưng timeout không tự giải deadlock nếu không có đường cleanup.

## 31. `complete()` từ nhiều thread không thay thế điều phối side effects

Khi dùng promise làm “first response wins”, có thể hình dung:

```java
if (promise.complete(receivedResult)) {
    publishResponse(receivedResult);
}
```

Đây là đoạn minh họa. Dùng return boolean tránh **caller thua** cũng phát response như người thắng, nhưng không cung cấp exactly-once delivery trong môi trường có crash/retry.

Các điểm cần xem xét:

- Nếu `publishResponse` fail sau khi promise đã complete, consumer của promise có thể đã nhận outcome thành công dù response bên ngoài chưa gửi.
- Nếu hai producer gọi service có side effect **trước khi complete**, cả hai side effect đã có thể xảy ra dù chỉ một promise outcome thắng.
- Nếu dùng timeout để completeExceptionally trước, producer đến sau có thể vẫn thực hiện commit database.
- Nếu consumer cần “first SUCCESS” chứ không phải “first TERMINAL outcome”, một future cạnh tranh trực tiếp với exceptional completions là mô hình thiếu chính sách.

Thường nên **tách kết quả điều phối** khỏi lifecycle của các tác vụ nguồn, dùng idempotency/correlation ID và một bộ quản lý các completion attempts.

## 32. `allOf()`, `anyOf()` và cuộc đua hoàn tất

`CompletableFuture.anyOf(a,b,c)` hoàn tất khi một trong các future đầu vào hoàn tất, **bình thường hoặc bất thường**. Nó không hứa chọn “successful response đầu tiên”.

`CompletableFuture.allOf(a,b,c)` hoàn tất khi các future đầu vào đều đã hoàn thành; nếu một hoặc nhiều đầu vào lỗi, future tổng có thể hoàn tất bất thường. Nó không tự gom kết quả thành `List<T>` và không phải lệnh cancel các task còn lại.

Nếu muốn tự điều phối “**hoàn tất khi có kết quả thành công đầu tiên, nhưng chỉ báo lỗi khi tất cả nguồn thất bại**”, bạn cần thêm state:

- Đếm số producer đã kết thúc.
- Mỗi success thử `promise.complete(value)`.
- Mỗi failure lưu nguyên nhân và tăng count.
- Chỉ khi **mọi producer đã thất bại** mới thử `completeExceptionally`.
- Đảm bảo count/collection failure thread-safe và không có race ở bước ra quyết định.
- Có deadline/cancel và tránh side effect lặp.

Một `AtomicInteger` cho số lượt failure và các completion primitives có thể giúp, nhưng phải chứng minh **đúng số lượng nguồn và race giữa success với “all failed”**. Không thay nguyên cả thiết kế bằng `anyOf` nếu semantics yêu cầu “first success”.

## 33. `completeAsync` và `supplyAsync` khác hoàn tất bằng tay

JDK 17 có `CompletableFuture.completeAsync(Supplier[,Executor])`: nó lên lịch **một Supplier để cố hoàn tất chính CompletableFuture hiện tại**, thay vì tạo một CompletableFuture nguồn mới như `supplyAsync`.

Ví dụ:

```java
CompletableFuture<String> promise = new CompletableFuture<>();
promise.completeAsync(() -> "computed", executor);
```

Đây là đoạn minh họa, `executor` tồn tại và được quản lý đúng. Cần phân biệt:

- `promise.complete("known")`: thử hoàn tất **ngay bằng giá trị đã có**.
- `promise.completeExceptionally(error)`: thử hoàn tất **ngay bằng lỗi**.
- `promise.completeAsync(supplier, executor)`: lên lịch supplier để **thử hoàn tất promise hiện tại về sau**.
- `CompletableFuture.supplyAsync(supplier, executor)`: tạo **một future mới** được hoàn thành bởi supplier.

Vì có thể có cuộc đua, `complete("manual")` có thể thắng trước khi `completeAsync` chạy xong; supplier đã lên lịch vẫn có thể thực thi/tiêu tốn resource theo điều kiện runtime. Không dựa vào completeAsync như một cách đảm bảo “chỉ một công việc duy nhất thực sự chạy” nếu có cạnh tranh.

## 34. `obtrudeValue` và `obtrudeException` là ngoại lệ với luật một lần

Hai API nâng cao của `CompletableFuture`:

```java
promise.obtrudeValue("FORCED");
promise.obtrudeException(new IllegalStateException("FORCED_ERROR"));
```

Chúng có thể **cưỡng bức thay trạng thái/result được các lượt đọc sau quan sát**, ngay cả khi future đã completed. Đây là cơ chế ngoại lệ, chủ yếu dành cho recovery đặc biệt, không phải flow thông thường.

**Cực kỳ quan trọng:** dependent stages đã hoàn tất hoặc đang chạy có thể đã nhận **outcome trước khi obtrude**, còn những lượt đọc sau nhận outcome mới. Điều đó phá vỡ suy luận đơn giản rằng toàn bộ hệ thống nhìn thấy cùng một terminal result.

Vì vậy:

- Không dùng `obtrudeValue/obtrudeException` để “sửa một lần complete nhầm” trong luồng nghiệp vụ bình thường.
- Không dùng chúng để điều phối producer thắng thua.
- Nếu cần sửa kết quả, tạo **future/version mới** hoặc một state machine ứng dụng có version rõ ràng.
- Cẩn trọng khi thư viện đưa CompletableFuture mutable ra ngoài API: caller có thể gọi complete/obtrude không mong muốn.

Quy tắc “first completion wins” ở bài này áp dụng **các completion methods thông thường**, không bao gồm thao tác ép thay trạng thái.

## 35. Thiết kế API: ai có quyền complete?

Một phương thức chỉ muốn cho caller **đọc kết quả** không nhất thiết nên trả trực tiếp một `CompletableFuture` mutable nếu muốn giữ quyền quyết định outcome trong một component.

Ví dụ:

```java
final class PendingRequest {
    private final CompletableFuture<String> writable =
            new CompletableFuture<>();

    public java.util.concurrent.CompletionStage<String> result() {
        return writable.minimalCompletionStage();
    }

    void succeed(String value) {
        writable.complete(value);
    }

    void fail(Throwable error) {
        writable.completeExceptionally(error);
    }
}
```

Đây là lớp minh họa độc lập về cấu trúc, không có `main`; `minimalCompletionStage()` có từ các JDK hỗ trợ Java 17. Nó trả một view với các phương thức `CompletionStage` phù hợp cho composition, giảm việc caller trực tiếp điều khiển các API mutable completion của promise nội bộ.

**Không coi đây là ranh giới bảo mật tuyệt đối.** Một caller có thể gọi `toCompletableFuture()` trên stage để lấy một CompletableFuture có thể điều khiển theo contract của view; mục tiêu là không trao thẳng quyền sửa **promise gốc** một cách vô tình, và xây rõ ownership của API.

Nếu thư viện thật cần hỗ trợ cancellation từ caller, thiết kế một method `cancelRequest(id)` hoặc một handle có contract riêng thay vì để caller có thể gọi bất kỳ `complete(...)` nào lên future sở hữu bởi producer.

## 36. Retry và nhiều lần thử hoàn tất

Khi một request cho phép retry, cần phân biệt **một request logical** và **nhiều attempt vật lý**. Nếu attempt đầu ném exception, không nhất thiết phải lập tức `completeExceptionally` promise tổng nếu policy yêu cầu retry.

Mô hình hợp lý:

```text
Request promise P (pending)
    |
  Attempt #1 fails
    |
  policy cho retry?
    +-- yes --> Attempt #2 starts --> success --> P.complete(value)
    |
    +-- no -------------------------> P.completeExceptionally(error)
```

Nếu attempt #1 và #2 chạy đồng thời, kết quả phải được điều phối theo policy: first success, fastest response, best quality, deadline hay consensus. Không dùng một `completeExceptionally` cho từng failure nếu vẫn còn nguồn có thể thành công, trừ khi mong outcome “bất kỳ lỗi nào xuất hiện đầu tiên cũng khiến request lỗi”.

Khi retry thao tác có side effect, phải có idempotency/reconciliation. Một task thua race **có thể đã làm side effect** trước khi complete trả false.

## 37. Kiểm thử race và terminal state đúng cách

### Điều cần assert

1. Khi mới tạo `new CompletableFuture<>()`, `isDone()==false`.
2. Lời gọi `complete` đầu thành công, lời gọi sau thất bại.
3. Lời gọi `completeExceptionally` đầu thành công, `get/join` báo đúng cause.
4. Khi nhiều thread cạnh tranh, tổng số **boolean true** từ các phương thức `complete/completeExceptionally` trong một cuộc đua một lần là **1**.
5. Future không bị thay bằng một late complete.
6. Sau `cancel`, `get/join` báo cancellation; `complete` trả false.
7. Sau timeout được áp dụng vào chính future qua `orTimeout`, lời gọi complete sau đó trả false khi timeout thắng.
8. Source hoàn thành không đồng nghĩa dependent stage đã hoàn thành.
9. Trạng thái giữa nhiều thread phải được quan sát bằng latch/`Future`/`join`, không đoán bằng `Thread.sleep`.

### Đừng assert người thắng là A/B

Nếu không có cơ chế đồng bộ để ép thứ tự, runtime tự chọn lịch chạy. Một test chỉ qua khi “A thắng” là test flaky. `ConcurrentCompletionRaceDemo` kiểm tra invariant thay vì người thắng cụ thể.

### Phải cleanup cả thread lẫn executor

Một test pending promise dễ treo nếu producer bị interrupt trước khi complete. Thiết kế `finally` để giải phóng latch, xử lý cancellation và đóng executor của test; nếu không, bộ test có thể giữ những worker chờ mãi.

### Không lấy `getNumberOfDependents()` làm condition đúng

Con số này chỉ là **ước lượng để monitoring**, không phải một latch chính xác. Nếu cần biết downstream đã xong, giữ dependent Future và gọi `join/get` trên nó.

## 38. Các lỗi phổ biến khi sử dụng pending CompletableFuture

### 38.1. Tạo promise rồi không có producer hoàn tất

`new CompletableFuture<>()` không tự chạy công việc. Nếu quên mọi nhánh success/failure/cancel/timeout, waiter có thể treo mãi.

### 38.2. Tưởng mọi `complete(value)` đều ghi đè

Chỉ lời gọi complete thắng khi future còn pending mới chuyển trạng thái. Lời gọi sau trả false.

### 38.3. Không kiểm tra boolean sau complete

Nếu side effect phụ thuộc việc chính caller là winner, phải kiểm tra return boolean. Nhưng bản thân side effect ngoài future vẫn không có exactly-once guarantee.

### 38.4. Kiểm tra isDone trước rồi complete như giao dịch

`if (!isDone()) complete(...)` có check-then-act race. Dùng chính kết quả của `complete(...)` để xác định ai thắng.

### 38.5. Nghĩ exceptional luôn ưu tiên success

Không có ưu tiên cố định. Success/failure/cancel tranh cùng một trạng thái terminal, theo chính sách API.

### 38.6. Nhầm `get(timeout)` với `orTimeout`

`get(timeout)` chỉ giới hạn lời chờ của caller, không tự complete promise. `orTimeout` có thể đưa **chính future** vào exceptional completion khi timeout.

### 38.7. Nghĩ `completeOnTimeout` chỉ tạo một wrapper fallback

Method trả chính future, nên fallback thắng sẽ là outcome của **chính future gốc**, ảnh hưởng tất cả consumer giữ reference đó.

### 38.8. Nghĩ cancel(true) luôn interrupt worker

Với `CompletableFuture`, mayInterruptIfRunning không điều khiển thực thi bằng interrupt; phải có giao thức dừng task riêng.

### 38.9. Đếm cancel(true) để tìm winner

Các lời gọi cancel lặp sau khi đã canceled có thể vẫn trả true; không dùng return value này như bộ đếm duy nhất cho chuyển trạng thái.

### 38.10. Bỏ qua callback lỗi ở dependent stage

Source có thể thành công nhưng dependent bị lỗi. Cần theo dõi **future cuối** hoặc từng stage có ý nghĩa nghiệp vụ.

### 38.11. Chạy callback blocking trong thread gọi complete

Continuation không-Async có thể chạy inline. Nếu callback chặn lâu dưới lock, có thể gây latency/deadlock.

### 38.12. Dùng obtrude để sửa outcome trong flow bình thường

Obtrude có thể khiến consumer cũ và mới thấy outcome khác nhau. Không dùng như một completion cạnh tranh thường.

### 38.13. Lộ CompletableFuture mutable ra API công khai

Caller có thể gọi complete/completeExceptionally/cancel khi không sở hữu quyền quyết định. Cân nhắc CompletionStage view và quyền quản lý hợp đồng rõ.

### 38.14. Hoàn tất success quá sớm

Nếu `complete(result)` xảy ra trước khi object được xây xong hoặc side effect bắt buộc commit, consumer có thể hành động dựa trên trạng thái chưa nhất quán. Công bố result immutable sau khi công việc cần thiết đã hoàn tất.

### 38.15. Tưởng timeout/hủy rollback tác vụ

Promise terminal không tự rollback database, dừng RPC hay đóng socket. Cancellation và cleanup ở tầng task vẫn là vấn đề riêng.

### 38.16. Dùng CompletableFuture cho stream vô hạn

Một promise chỉ cho một terminal result. Dữ liệu nhiều sự kiện cần stream/queue/publisher, không nên cố complete cùng future nhiều lần để gửi nhiều message.

## 39. Checklist thiết kế một promise tốt

Trước khi triển khai pending `CompletableFuture<T>`, hỏi:

- **Ai sở hữu?** Component nào được gọi `complete/completeExceptionally`?
- **Producer là ai?** Callback, worker, RPC response hay nhiều nguồn cạnh tranh?
- **Outcome là gì?** Giá trị thành công, lỗi, cancellation, timeout; phân biệt rõ từng nhánh.
- **Deadline ở đâu?** Caller chỉ dừng chờ hay chính request future phải terminal timeout?
- **Bộ điều phối có cần first success?** Nếu cần, đừng để mỗi failure trực tiếp terminate promise quá sớm.
- **Boolean return được dùng thế nào?** Ai được phép làm side effect khi thắng?
- **Late callbacks xử lý ra sao?** Bỏ, ghi metric, giải phóng resource, không phản hồi trùng?
- **Cleanup ở đâu?** Producer bị hủy/timeout có dừng mạng, I/O, worker và gỡ correlation map không?
- **Continuation có blocking không?** Cân nhắc executor và nguy cơ callback chạy inline.
- **Result có mutable không?** Công bố immutable snapshot hoặc dùng synchronization phù hợp.
- **Tài nguyên executor ai đóng?** Không để thread leak vì pending tasks.
- **Test có deterministic không?** Latch/barrier kiểm thử thứ tự có chủ đích; race test kiểm invariant thay vì cố định winner.
- **Có nhiều stage phụ thuộc?** Chờ final future, không chỉ `source.isDone()`.
- **Có side effect quan trọng?** Idempotency, commit state, retry và failure reporting thuộc tầng nghiệp vụ.

## 40. Bài tập thực hành

**Bài tập 1 – Pending rồi success.** Tạo `CompletableFuture<Integer>` pending. Kiểm tra `isDone()==false`; gọi `complete(7)`, xác nhận true và `join()==7`; gọi `complete(9)`, xác nhận false và kết quả vẫn 7.

**Bài tập 2 – Exception thắng.** Tạo promise pending, `completeExceptionally(new IOException("missing"))`. Quan sát `join` ném `CompletionException` và `get` ném `ExecutionException`, cả hai có cause tương ứng; `complete("OK")` sau đó false.

**Bài tập 3 – Hai producer tranh value.** Hai thread cùng đợi latch rồi `complete("A")`/`complete("B")`. Assert chỉ một boolean true và kết quả thuộc `{"A","B"}`. Không assert người thắng cố định.

**Bài tập 4 – Value, exception, cancel.** Thêm một watchdog có `completeExceptionally` và một caller `cancel`. Quan sát đặc biệt: các lần cancel lặp có thể trả true khi future đã canceled, do đó cách đếm winner phải thay đổi khi đưa cancel vào.

**Bài tập 5 – Timeout không hoàn tất future.** Dùng `get(30, MILLISECONDS)` trên pending promise chưa có producer; catch `TimeoutException` và kiểm tra promise còn incomplete. Sau đó `complete("LATE")` và `join()` thành công.

**Bài tập 6 – orTimeout thắng.** Dùng `orTimeout(30, MILLISECONDS)` trên promise không có producer, gọi `join` nhận cause TimeoutException; thử complete sau đó và xác nhận false.

**Bài tập 7 – completeOnTimeout.** Dùng `completeOnTimeout("DEFAULT", ..., ...)` trên pending future; xác nhận kết quả fallback. Thêm producer thật cùng thời điểm và chỉ assert outcome hợp lệ nếu không ép thứ tự.

**Bài tập 8 – Dependent pipeline.** Đăng ký `thenApply(x -> x * 2)` và `thenApplyAsync(x -> x + 1, executor)`, gọi complete và đợi stage cuối; phân biệt source done với toàn pipeline done.

**Bài tập 9 – Adapter callback.** Viết adapter callback `onSuccess/onFailure` về một promise. Cố ý gửi hai callback và kiểm tra late completion không làm thay outcome. Thêm cleanup correlation ID.

**Bài tập 10 – First success policy.** Có ba nguồn, hai nguồn fail và một nguồn success. Thiết kế coordinator để promise tổng chỉ lỗi khi cả ba fail, không phải khi nguồn đầu tiên fail. Test có các nguồn hoàn tất theo các thứ tự khác nhau.

## 41. Câu hỏi tự kiểm tra

**Câu 1.** `new CompletableFuture<String>()` có tự chạy Supplier không?

**Đáp án:** Không. Nó tạo future chưa hoàn tất; một producer/callback khác phải complete hoặc xử lý timeout/hủy.

**Câu 2.** `complete("A")` trả true nghĩa là gì?

**Đáp án:** Lời gọi này đã làm future chuyển từ incomplete sang normal completion với A.

**Câu 3.** Nếu sau `complete("A")` một thread gọi `complete("B")` thì sao?

**Đáp án:** Trả false và kết quả vẫn A theo completion thông thường.

**Câu 4.** `completeExceptionally(error)` nhận `Throwable` hay một String?

**Đáp án:** Nhận một `Throwable` không null. `completeExceptionally(null)` là không hợp lệ.

**Câu 5.** Nếu success và failure cùng gọi complete trên một pending future, có ưu tiên outcome nào không?

**Đáp án:** Không có ưu tiên mặc định. Lời gọi hoàn tất thắng trước quyết định outcome.

**Câu 6.** Dùng `if (!isDone()) complete(v)` có bảo đảm complete thành công không?

**Đáp án:** Không. Có race giữa kiểm tra và cập nhật. Dùng boolean trả về từ `complete`.

**Câu 7.** `cancel(true)` có luôn ngắt thread đang tính không?

**Đáp án:** Không. Với `CompletableFuture`, mayInterruptIfRunning không điều khiển thực thi qua interrupt.

**Câu 8.** Vì sao không đếm các lần `cancel() == true` để biết ai thắng?

**Đáp án:** Sau khi future đã canceled, cancel lặp có thể tiếp tục trả true; không nhất thiết chuyển trạng thái mới.

**Câu 9.** `get(timeout)` ném TimeoutException có làm future hoàn tất exceptional không?

**Đáp án:** Không tự động. Đó là timeout của caller đang chờ; promise có thể vẫn pending.

**Câu 10.** `orTimeout` có tạo một wrapper future khác không?

**Đáp án:** Không. Nó trả lại chính `CompletableFuture` được gọi và có thể hoàn tất bất thường future ấy khi timeout.

**Câu 11.** `completeOnTimeout` hoàn tất bình thường hay thất bại khi timeout thắng?

**Đáp án:** Hoàn tất bình thường với fallback value được truyền.

**Câu 12.** Một future nguồn đã complete, dependent stage có chắc đã done không?

**Đáp án:** Không. Dependent có thể đang được lên lịch hoặc xử lý; phải đợi dependent future.

**Câu 13.** `thenApply` trên pending future có thể chạy ở thread gọi complete không?

**Đáp án:** Có. Callback không-Async có thể chạy inline khi source hoàn tất.

**Câu 14.** Nếu source thành công nhưng `thenApply` ném exception, source có chuyển thành lỗi không?

**Đáp án:** Không. Dependent stage thất bại, còn source giữ outcome success.

**Câu 15.** Có thể dùng `obtrudeValue` như complete lần thứ hai thông thường không?

**Đáp án:** Không nên. Nó ép thay outcome quan sát về sau và có thể gây khác biệt với dependent đã nhận outcome cũ.

**Câu 16.** `CompletableFuture.anyOf` có hứa chỉ hoàn tất khi một nguồn thành công không?

**Đáp án:** Không. Một nguồn fail có thể làm anyOf hoàn tất lỗi trước các nguồn thành công khác.

**Câu 17.** Vì sao callback tới muộn sau khi timeout không nên gửi response lần thứ hai?

**Đáp án:** Promise đã terminal; complete trả false. Gửi thêm response có thể tạo duplicate/vi phạm giao thức.

**Câu 18.** Một pending promise giữ closure lớn có thể gây vấn đề gì?

**Đáp án:** Memory retention: nếu không bao giờ complete hoặc cleanup, dependent stages/objects có thể bị giữ lâu.

**Câu 19.** Hoàn tất future với object mutable có làm object tự thread-safe không?

**Đáp án:** Không. Future công bố reference/result; các sửa đổi mutable sau đó vẫn cần synchronization/ownership.

**Câu 20.** Nếu muốn “first success, all fail mới báo lỗi”, chỉ cần cho mọi failure gọi completeExceptionally trực tiếp không?

**Đáp án:** Không. Failure đầu tiên có thể thắng, chặn success muộn hơn. Cần coordinator theo dõi outcomes và đếm nguồn còn lại.

## 42. Tổng kết

`new CompletableFuture<T>()` tạo một **promise chưa hoàn tất**. `complete(value)` thử hoàn tất bình thường, `completeExceptionally(error)` thử hoàn tất bất thường; cả hai trả boolean để cho biết **lời gọi này có thắng cuộc đua chuyển trạng thái hay không**. Với nhiều thread, quy tắc cơ bản là **first successful completion wins**, không có ưu tiên cố định giữa success và failure.

Nhưng cần nắm những ranh giới:

- **`cancel`** tham gia cuộc đua terminal, có ngữ nghĩa boolean khác các complete method; cancel lặp khi đã canceled vẫn có thể trả true.
- **`get(timeout)`** chỉ timeout việc chờ của caller; **`orTimeout`** và **`completeOnTimeout`** có thể quyết định outcome của **chính future**.
- **Source completed** không đồng nghĩa **mọi dependent stage đã hoàn thành**. Callback không-Async có thể chạy inline ngay trong thread complete.
- **Cancellation/timeout không tự dừng producer**, không rollback database, không bảo đảm side effect exactly once.
- **`obtrudeValue/obtrudeException`** là API đặc biệt có thể ép thay outcome, không được coi như completion thường.
- **Một promise không phải stream**: nếu có nhiều events hoặc nhiều attempts, cần coordinator và protocol rõ ràng.
- **Không phụ thuộc lịch chạy thread trong test**; dùng latch để điều phối hoặc assert invariant và tập outcome hợp lệ.

Thiết kế đáng tin cậy luôn xác định rõ **owner được quyền hoàn tất**, các nhánh success/error/timeout/cancel, policy cho kết quả đến muộn, cleanup resource và cách kiểm tra final future. Đó mới là cách dùng `CompletableFuture` làm cầu nối an toàn giữa các thread và callback trong Java concurrency.
