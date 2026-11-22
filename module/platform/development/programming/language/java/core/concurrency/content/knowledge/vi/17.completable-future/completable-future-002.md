# CompletableFuture: `completedFuture()`, `supplyAsync()` và `runAsync()` trong Java

## 1. Bài toán mà ba factory method giải quyết

Khi lập trình concurrent Java, một lời gọi có thể có **kết quả ngay**, hoặc cần đưa một công việc cho executor xử lý và nhận kết quả **về sau**. `CompletableFuture<T>` đại diện cho một phép tính có thể hoàn thành với giá trị kiểu `T`, hoàn thành thất bại hoặc bị hủy. Nó còn cho phép ghép các bước xử lý với `thenApply`, `thenCompose`, `thenAccept`, `thenRun` và nhiều API khác.

Ba điểm khởi đầu rất phổ biến:

```java
CompletableFuture<Integer> ready =
        CompletableFuture.completedFuture(42);

CompletableFuture<Integer> computed =
        CompletableFuture.supplyAsync(() -> 21 * 2);

CompletableFuture<Void> performed =
        CompletableFuture.runAsync(() ->
                System.out.println("doing background work"));
```

Đây là các đoạn minh họa cần `import java.util.concurrent.CompletableFuture;`. Cả ba đều trả về một `CompletableFuture`, nhưng khác nhau về **thời điểm hoàn thành, có tạo công việc mới không, kiểu kết quả và cách chạy code**.

- **`completedFuture(value)`**: tạo một future **đã hoàn thành bình thường** với `value`. Không tự nộp lambda/task cho worker.
- **`supplyAsync(supplier)`**: nộp `Supplier<T>` để thực thi bất đồng bộ; lấy giá trị do `Supplier.get()` trả về và hoàn thành future với giá trị đó.
- **`runAsync(runnable)`**: nộp `Runnable` để thực thi bất đồng bộ; future có kiểu `CompletableFuture<Void>` và khi task thành công nó hoàn thành bình thường với giá trị kết quả `null`.

**Lưu ý:** tên có chữ `Async` không hứa hẹn task lập tức chạy trên một core khác ngay khi method trả về. Task được **sắp lịch** qua executor; nó có thể bắt đầu sớm, trễ, hoặc gặp trường hợp executor từ chối thực thi. Quan hệ thời gian giữa caller và worker là concurrent, không có thứ tự cố định nếu thiếu đồng bộ.

Bài này nằm trong **Java Advance – concurrency → CompletableFuture**, chỉ sử dụng **Java Concurrency nói chung**, không phụ thuộc Spring hay framework nào.

## 2. Bảng so sánh cốt lõi

| Tiêu chí | `completedFuture(value)` | `supplyAsync(supplier)` | `runAsync(runnable)` |
| --- | --- | --- | --- |
| Đầu vào | Giá trị `T` có sẵn | `Supplier<T>` | `Runnable` |
| Có tự tạo task để chạy? | Không | Có | Có |
| Giá trị khi hoàn thành thành công | Chính `value` đã cung cấp | Giá trị do `get()` trả về | `null` |
| Kiểu trả về | `CompletableFuture<T>` | `CompletableFuture<T>` | `CompletableFuture<Void>` |
| Trạng thái ngay khi phương thức trả về | Đã hoàn thành bình thường | Có thể chưa hoặc đã hoàn thành | Có thể chưa hoặc đã hoàn thành |
| Mặc định dùng executor? | Không | Có, nếu không truyền executor thì dùng cơ chế mặc định | Có, nếu không truyền executor thì dùng cơ chế mặc định |
| Có overload nhận `Executor`? | Không cần và không có | Có | Có |
| Thất bại | Factory không chạy code gây lỗi; giá trị đã có | Exception/error từ supplier được ghi nhận như exceptional completion | Exception/error từ runnable được ghi nhận như exceptional completion |
| Use case | Kết quả cache có sẵn; nhánh fallback đồng bộ | Tính toán/đọc dữ liệu có kết quả | Ghi log, phát sự kiện, cleanup, side effect |

**Trạng thái future và trạng thái nghiệp vụ là hai việc khác nhau.** `CompletableFuture<Void>` hoàn thành bình thường chỉ có nghĩa `Runnable.run()` kết thúc mà không ném lỗi ra ngoài; không tự chứng minh dữ liệu đã được commit bền vững ở hệ thống khác.

## 3. CompletableFuture có những trạng thái nào?

Một future có thể ở trạng thái **chưa hoàn thành**, rồi chuyển tới **hoàn thành bình thường**, **hoàn thành bất thường** hoặc **bị hủy**. Với `CompletableFuture`, cancel được mô hình hóa là một dạng exceptional completion (thường chứa `CancellationException`).

```text
                 INCOMPLETE
                  /   |    \
                 /    |     \
                v     v      v
        NORMAL(value)  EXCEPTIONAL(cause)  CANCELLED
```

Các API quan sát:

- `isDone()` trả `true` khi future đã hoàn thành theo bất cứ outcome nào, kể cả lỗi/hủy.
- `isCompletedExceptionally()` kiểm tra exceptional completion; **future bị cancel cũng thuộc trường hợp này**.
- `isCancelled()` kiểm tra cancellation.
- `get()` đợi và trả kết quả, hoặc ném checked/unchecked exceptions theo trạng thái.
- `join()` đợi và trả kết quả; khi computation thất bại thường ném `CompletionException` (unchecked), khi canceled có thể ném `CancellationException` trực tiếp.
- `getNow(valueIfAbsent)` trả giá trị ngay nếu đã hoàn thành bình thường, hoặc trả fallback khi chưa hoàn thành; nếu future hoàn thành lỗi, nó **ném exception**, không trả fallback.

`completedFuture(x)` tạo trạng thái NORMAL(x) **ngay lập tức**. `supplyAsync` và `runAsync` tạo cơ hội để future hoàn thành về sau do một task chạy trên executor.

Không dùng `isDone()==true` làm bằng chứng thành công. `isDone` có thể true vì fail hoặc cancel; muốn biết outcome phải quan sát giá trị/exception.

## 4. `completedFuture(value)` hoạt động như thế nào?

Chữ ký:

```java
public static <U> CompletableFuture<U> completedFuture(U value)
```

Nó tạo **một CompletableFuture mới**, đã hoàn thành bình thường với giá trị `value` được truyền vào.

Nếu bạn đã có giá trị `T`, method này **không tính lại**, không gọi một `Supplier`, không cấp phát task để xử lý trong `ForkJoinPool`. Nó chỉ tạo đối tượng biểu diễn kết quả đã hoàn tất.

Ví dụ:

```java
CompletableFuture<String> ready =
        CompletableFuture.completedFuture("cached");

System.out.println(ready.isDone()); // true
System.out.println(ready.join());   // cached
```

Đây là đoạn minh họa với import `CompletableFuture`; hai dòng kết quả là `true` và `cached`.

### Ví dụ 1: giá trị đã có, kết quả null và kiểm tra trạng thái

Tạo tệp `CompletedFutureDemo.java`:

```java
import java.util.concurrent.CompletableFuture;

public class CompletedFutureDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> answer =
                CompletableFuture.completedFuture(42);

        CompletableFuture<String> noValue =
                CompletableFuture.completedFuture(null);

        System.out.println("answer done=" + answer.isDone());
        System.out.println("answer=" + answer.join());
        System.out.println("null done=" + noValue.isDone());
        System.out.println("null result=" + noValue.join());
        System.out.println("exceptional="
                + answer.isCompletedExceptionally());
    }
}
```

Biên dịch/chạy trên JDK 17+:

```bash
javac CompletedFutureDemo.java
java CompletedFutureDemo
```

Output:

```text
answer done=true
answer=42
null done=true
null result=null
exceptional=false
```

**`null` là kết quả hoàn thành bình thường hợp lệ** của `CompletableFuture<T>`. Điều đó khác với “future chưa hoàn thành”. Kiểm tra `isDone()` hoặc sử dụng API outcome phù hợp để không nhập nhằng.

## 5. Khi nào dùng `completedFuture`?

### Giá trị cache đã biết

Một API thống nhất luôn trả `CompletableFuture<User>` dù dữ liệu đã ở trong bộ nhớ:

```java
CompletableFuture<User> findUser(String id) {
    User cached = cache.get(id);
    if (cached != null) {
        return CompletableFuture.completedFuture(cached);
    }
    return loadUserAsync(id);
}
```

Đây là **mã minh họa**, `User`, `cache` và `loadUserAsync` do ứng dụng định nghĩa. Nhánh cache không cần tạo việc bất đồng bộ vô ích. Nhánh còn lại có thể dùng `supplyAsync` với một executor phù hợp hoặc một API I/O async thật sự.

### Giá trị mặc định

```java
CompletableFuture<String> fallback =
        CompletableFuture.completedFuture("guest");
```

Không có worker riêng chỉ để trả về chuỗi literal.

### Ghép pipeline với return type thống nhất

Khi dùng `thenCompose`, callback cần trả một `CompletionStage<U>`; nếu đã có kết quả trong một nhánh, `completedFuture(result)` giúp giữ cùng kiểu trả về:

```java
future.thenCompose(result -> {
    if (result.isReady()) {
        return CompletableFuture.completedFuture(result);
    }
    return enrichAsync(result);
});
```

Đây là đoạn minh họa với `future`, `result` và `enrichAsync` do ứng dụng định nghĩa. Method này giúp **tránh lồng future không cần thiết**.

### Chú ý tính đồng bộ của continuation

Khi gọi một continuation **không có hậu tố `Async`**, ví dụ `thenApply(fn)` trên future **đã hoàn thành**, callback có thể được thực thi **ngay trong thread đăng ký**. Tức là:

```java
CompletableFuture.completedFuture(10)
        .thenApply(value -> expensiveCalculation(value));
```

không có nghĩa `expensiveCalculation` được chạy nền. Nếu callback dài hoặc blocking, caller đăng ký callback có thể bị giữ lại. `completedFuture` không có nhiệm vụ biến mọi bước downstream thành asynchronous.

## 6. `completedFuture` không deep-copy giá trị

`completedFuture(object)` giữ **tham chiếu đến object** được truyền vào; nó không clone object. Nếu object mutable và có thread khác sửa nó không đồng bộ, future không tự làm object ấy thread-safe.

```java
List<String> data = new ArrayList<>();
data.add("A");

CompletableFuture<List<String>> future =
        CompletableFuture.completedFuture(data);

data.add("B");
// future.join() vẫn tham chiếu cùng list data.
```

Đây là đoạn minh họa với import `java.util.*` và `CompletableFuture`. Kết quả `future.join()` có thể nhìn thấy nội dung list đã sửa, vì chính list đã đổi, **không phải future thay kết quả**.

Nếu cần giá trị kết quả bất biến, có thể truyền `List.copyOf(data)` hoặc một value object immutable. `List.copyOf` tạo danh sách không sửa được qua API collection, nhưng không deep-copy những phần tử mutable bên trong.

Trong workflow concurrent, tạo object rồi xuất bản an toàn là một bước; **hạn chế sửa mutable object sau khi công bố** mới giúp các consumer đọc nhất quán.

## 7. `supplyAsync(supplier)`: tạo phép tính bất đồng bộ có kết quả

Chữ ký overload phổ biến:

```java
public static <U> CompletableFuture<U> supplyAsync(
        Supplier<U> supplier);

public static <U> CompletableFuture<U> supplyAsync(
        Supplier<U> supplier, Executor executor);
```

`Supplier<U>` là functional interface trong `java.util.function`:

```java
@FunctionalInterface
public interface Supplier<T> {
    T get();
}
```

Lambda không nhận tham số và **trả về giá trị**:

```java
CompletableFuture<Integer> future =
        CompletableFuture.supplyAsync(() -> {
            int a = 20;
            int b = 22;
            return a + b;
        });
```

`supplyAsync` nộp Supplier cho executor. Khi `get()` trả một giá trị, future hoàn thành bình thường bằng giá trị đó; nếu Supplier ném exception/error, future chuyển sang exceptional completion.

**Điểm khác với `completedFuture`:** Supplier là **công việc cần thực thi**, không phải giá trị đã có. Vì vậy `future.isDone()` ngay sau `supplyAsync` có thể là true hoặc false tùy thời điểm task hoàn tất. Không viết test giả định **luôn false** ngay sau lời gọi.

## 8. `runAsync(runnable)`: thực hiện bất đồng bộ, không có kết quả riêng

Chữ ký:

```java
public static CompletableFuture<Void> runAsync(
        Runnable runnable);

public static CompletableFuture<Void> runAsync(
        Runnable runnable, Executor executor);
```

`Runnable` có method:

```java
@FunctionalInterface
public interface Runnable {
    void run();
}
```

Dùng `runAsync` khi mục tiêu là một hành động không cần trả dữ liệu của task, chẳng hạn thực hiện housekeeping, kích hoạt side effect, chuẩn bị tài nguyên hoặc gửi một yêu cầu mà người gọi chỉ cần biết **hành động đã kết thúc thành công/thất bại**.

```java
CompletableFuture<Void> done =
        CompletableFuture.runAsync(() ->
                System.out.println("updated"));

done.join(); // null nếu thành công.
```

Dù Future có kiểu `Void`, nó vẫn **mang thông tin hoàn thành, lỗi và cancellation**. Không có giá trị nghiệp vụ trả về không có nghĩa caller nên bỏ Future mà không theo dõi outcome.

### Vì sao không thể dùng supplyAsync với lambda không return?

`supplyAsync` yêu cầu `Supplier<T>` có phương thức `T get()` trả về giá trị. Lambda:

```java
() -> System.out.println("hello")
```

thường được dùng làm `Runnable` vì biểu thức gọi `println` không trả kết quả; không thể trực tiếp biến nó thành `Supplier<String>` để `supplyAsync` hoàn thành với string nào đó.

Nếu thật sự cần một marker kết quả, có thể:

```java
CompletableFuture<Boolean> done =
        CompletableFuture.supplyAsync(() -> {
            performAction();
            return true;
        });
```

Đây là đoạn minh họa, `performAction()` do ứng dụng định nghĩa. Nhưng nếu `Boolean.TRUE` không chứa thông tin nghiệp vụ đáng kể, `runAsync` có thể biểu đạt ý định rõ ràng hơn.

## 9. Ví dụ 2: supplyAsync trả kết quả, runAsync báo hoàn thành

Tạo tệp `SupplyAndRunAsyncDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class SupplyAndRunAsyncDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newFixedThreadPool(2);
        AtomicBoolean actionCompleted = new AtomicBoolean();

        try {
            CompletableFuture<Integer> number =
                    CompletableFuture.supplyAsync(() -> 21 * 2, executor);

            CompletableFuture<Void> action =
                    CompletableFuture.runAsync(
                            () -> actionCompleted.set(true),
                            executor);

            int result = number.join();
            Void actionResult = action.join();

            System.out.println("number=" + result);
            System.out.println("action value=" + actionResult);
            System.out.println("action completed="
                    + actionCompleted.get());
            System.out.println("number done=" + number.isDone());
            System.out.println("action done=" + action.isDone());
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
javac SupplyAndRunAsyncDemo.java
java SupplyAndRunAsyncDemo
```

Kết quả khi hai task hoàn tất bình thường:

```text
number=42
action value=null
action completed=true
number done=true
action done=true
```

Vì `join()` được gọi trước khi in, chương trình không cần dự đoán worker nào thực thi trước. `number` cho giá trị `42` từ Supplier; `action` cho `null` vì kiểu `Void`, nhưng vẫn xác nhận Runnable đã kết thúc. `AtomicBoolean` ở đây giúp diễn đạt trạng thái một cách an toàn khi có thread khác ghi.

**Không cần cố tình gọi `Thread.sleep(...)` để “đợi cho task xong”.** `join()`/`get()` là cơ chế đồng bộ phù hợp để quan sát hoàn thành. Với ứng dụng production, đợi vô hạn không phải lúc nào cũng phù hợp; có thể cần timeout/deadline.

## 10. Executor mặc định khi không truyền tham số

Với overload chỉ có Supplier/Runnable:

```java
CompletableFuture.supplyAsync(() -> compute());
CompletableFuture.runAsync(() -> update());
```

Java thường sử dụng `ForkJoinPool.commonPool()` cho những asynchronous task này. Theo chính sách của `CompletableFuture`, khi common pool không hỗ trợ mức song song cần thiết (ví dụ mức parallelism dưới hai), implementation có thể tạo thread mới cho mỗi async task thay vì dùng common pool.

**Không nên phụ thuộc vào một tên thread cụ thể** như `ForkJoinPool.commonPool-worker-1`; phiên bản JDK, cấu hình JVM, pool và môi trường có thể khác.

### Ưu điểm

- Tạo task đơn giản, ít boilerplate.
- Thích hợp công việc ngắn, CPU-bound hoặc thử nghiệm.
- Không cần một executor riêng cho mọi ví dụ nhỏ.

### Nhược điểm

- Common pool là tài nguyên **chia sẻ**, có thể còn được dùng bởi những phần khác của ứng dụng như parallel streams.
- Workload blocking dài có thể chiếm worker, ảnh hưởng độ trễ những công việc cùng pool.
- Khó kiểm soát mức song song, chính sách từ chối, tên thread, phân tách workload hoặc SLA từng nhóm công việc.
- Không quản lý vòng đời của common pool như một executor riêng do mình tạo.

**Không tự gọi `ForkJoinPool.commonPool().shutdown()`** sau một lời gọi supplyAsync không truyền executor. Đó không phải tài nguyên riêng của lời gọi này.

Khi cần thread ownership, throttling, naming và shutdown theo service lifecycle, truyền **executor chuyên dụng**.

## 11. Overload nhận Executor và quyền sở hữu tài nguyên

Ví dụ:

```java
ExecutorService executor = Executors.newFixedThreadPool(4);

CompletableFuture<Integer> result =
        CompletableFuture.supplyAsync(() -> 10 + 5, executor);

CompletableFuture<Void> action =
        CompletableFuture.runAsync(() -> doWork(), executor);
```

Đây là đoạn minh họa; `doWork()` do ứng dụng định nghĩa. Cả hai task được nộp vào **executor được chỉ định**, thay vì dùng chính sách mặc định.

**Quy tắc ownership:**

- Thành phần tạo `ExecutorService` chịu trách nhiệm quyết định **khi nào shutdown**, và có thể chờ `awaitTermination()`.
- Thành phần chỉ nhận một `Executor` được cung cấp từ bên ngoài không nên tùy ý đóng tài nguyên dùng chung nếu hợp đồng không cho phép.
- Không tạo `newFixedThreadPool` trong mỗi request rồi quên shutdown; có thể gây thread leak.
- Không đóng executor quá sớm nếu còn các stage `thenApplyAsync`/`thenComposeAsync` dự kiến nộp vào nó về sau.

**Quan trọng:** `CompletableFuture.join()` đợi future có kết quả hoặc exceptional completion, nhưng không tự đóng executor; hoàn tất một task không làm các worker của pool biến mất.

## 12. Ví dụ 3: chỉ định thread name cho executor

Tên thread giúp debug executor nào chạy một task. Ta có thể tạo một `ThreadFactory` cho executor sở hữu trong phạm vi `main`.

Tạo tệp `NamedExecutorDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class NamedExecutorDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor(
                runnable -> new Thread(runnable, "lesson-worker"));

        try {
            CompletableFuture<String> name =
                    CompletableFuture.supplyAsync(
                            () -> Thread.currentThread().getName(),
                            executor);

            CompletableFuture<Void> action =
                    CompletableFuture.runAsync(
                            () -> {
                                String current =
                                        Thread.currentThread().getName();
                                if (!current.equals("lesson-worker")) {
                                    throw new IllegalStateException(
                                            "unexpected worker");
                                }
                            },
                            executor);

            System.out.println("supplier thread=" + name.join());
            System.out.println("runnable done=" + action.join());
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
javac NamedExecutorDemo.java
java NamedExecutorDemo
```

Kết quả:

```text
supplier thread=lesson-worker
runnable done=null
```

`NamedExecutorDemo` cố ý đặt tên cho worker nên output tên thread có thể kiểm tra. Với executor đơn, hai task được nộp tuần tự và được xử lý bởi worker của executor; nếu worker bị lỗi bất thường và executor thay thế nó, ThreadFactory vẫn đặt tên `lesson-worker` cho thread mới.

**Không suy rộng:** chỉ vì các task ban đầu chạy trên `lesson-worker` không có nghĩa **mọi callback không có hậu tố Async của future** cũng luôn chạy trên worker đó. Stage phụ thuộc có thể được thực thi bởi thread đăng ký callback hoặc thread hoàn tất stage theo hoàn cảnh.

## 13. Khi nào future thật sự hoàn thành?

`supplyAsync`/`runAsync` thường trả về trước khi task chạy xong, nhưng task rất nhanh **có thể kết thúc ngay trước khi phương thức factory trả về**.

Vì vậy, đoạn sau là một test yếu:

```java
var future = CompletableFuture.supplyAsync(() -> 1);
assert !future.isDone(); // Không được bảo đảm.
```

Đây là đoạn **phản ví dụ**. Tùy scheduler, `future.isDone()` có thể đã true.

Nếu muốn demo chắc chắn một future ban đầu chưa hoàn thành, dùng `CountDownLatch` để task thông báo đã bắt đầu rồi chờ tín hiệu từ caller; kiểm tra trạng thái trước khi mở latch. Không dùng `sleep(100)` và cầu may.

### Ví dụ 4: trạng thái trước/sau được điều phối bằng latch

Tạo tệp `AsyncStateLifecycleDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class AsyncStateLifecycleDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            CompletableFuture<String> future =
                    CompletableFuture.supplyAsync(() -> {
                        started.countDown();
                        try {
                            release.await();
                        } catch (InterruptedException e) {
                            Thread.currentThread().interrupt();
                            throw new IllegalStateException("interrupted", e);
                        }
                        return "ready";
                    }, executor);

            started.await();
            System.out.println("before release=" + future.isDone());

            release.countDown();
            System.out.println("result=" + future.join());
            System.out.println("after join=" + future.isDone());
        } finally {
            release.countDown();
            executor.shutdownNow();
            executor.awaitTermination(10, TimeUnit.SECONDS);
        }
    }
}
```

```bash
javac AsyncStateLifecycleDemo.java
java AsyncStateLifecycleDemo
```

Output khi main không bị interrupt bên ngoài và task hoàn thành bình thường:

```text
before release=false
result=ready
after join=true
```

Task báo đã bắt đầu bằng `started.countDown()`, sau đó chờ `release.await()`. Main đợi `started` và đọc trạng thái lúc `release` chưa mở, nên `future.isDone()` chắc chắn false; sau khi mở latch, task có thể trả `"ready"` và `join()` xác nhận hoàn thành.

Ví dụ dùng `shutdownNow()` trong `finally` để tránh quên cleanup khi có lỗi ở main, nhưng **sau khi future đã hoàn tất** đường bình thường sẽ không hủy kết quả vừa được in. Trong ứng dụng cần graceful shutdown, nên chọn shutdown hai giai đoạn theo SLA.

## 14. Kiểu kết quả: `T`, `Void` và `null`

So sánh ba đoạn:

```java
CompletableFuture<String> a =
        CompletableFuture.completedFuture("OK");

CompletableFuture<String> b =
        CompletableFuture.supplyAsync(() -> "OK");

CompletableFuture<Void> c =
        CompletableFuture.runAsync(() -> recordSuccess());
```

Đây là các đoạn minh họa; `recordSuccess()` do ứng dụng định nghĩa.

- `a.join()` trả `"OK"` ngay.
- `b.join()` trả `"OK"` khi Supplier hoàn thành; nếu chưa xong, caller chờ.
- `c.join()` trả `null` khi Runnable hoàn tất bình thường.

**`Void` không phải `void`.** `Void` là một reference type đại diện cho “không có giá trị hữu ích”; vì `CompletableFuture` là generic, `CompletableFuture<Void>` được dùng để biểu diễn future mà kết quả thành công là `null`.

Nếu một `Supplier<String>` trả `null` thì `CompletableFuture<String>` cũng có thể hoàn thành bình thường với `null`. Vì vậy không thể dùng mỗi `future.join() == null` để phân biệt “task chưa chạy” hay “task fail”. Khi fail, `join()` thường **ném exception**; khi chưa xong, nó **đợi**.

## 15. Ví dụ 5: pipeline kết hợp kết quả đã có và async task

Một pipeline có thể bắt đầu từ giá trị đã có rồi đưa **một bước thật sự tốn công** vào executor:

```java
CompletableFuture<Integer> result =
        CompletableFuture.completedFuture(5)
                .thenApply(value -> value + 1)
                .thenApplyAsync(value -> value * 10, executor);
```

Đây là đoạn minh họa; `executor` do ứng dụng sở hữu. `thenApply` **không bắt buộc chạy trên worker**, còn `thenApplyAsync(..., executor)` yêu cầu stage được lên lịch qua executor đó.

### Mã đầy đủ

Tạo tệp `CompletablePipelineDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class CompletablePipelineDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            CompletableFuture<Integer> pipeline =
                    CompletableFuture.completedFuture(5)
                            .thenApply(value -> value + 1)
                            .thenApplyAsync(value -> value * 10, executor);

            CompletableFuture<Integer> asynchronous =
                    CompletableFuture.supplyAsync(() -> 2, executor)
                            .thenApply(value -> value + 3);

            System.out.println("pipeline=" + pipeline.join());
            System.out.println("asynchronous="
                    + asynchronous.join());
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
javac CompletablePipelineDemo.java
java CompletablePipelineDemo
```

Output:

```text
pipeline=60
asynchronous=5
```

Dù các stage có thể chạy trên các thread khác nhau, phép cộng/nhân thuần của ví dụ không phụ thuộc thứ tự chạy. Caller đợi `join()` trước khi in nên output xác định.

**Điểm quan trọng:** `thenApplyAsync` khác `supplyAsync`. `supplyAsync` bắt đầu một nguồn tính toán độc lập từ `Supplier`; `thenApplyAsync` tạo stage **phụ thuộc kết quả của future trước** và áp dụng `Function` lên giá trị đã có.

## 16. Biến `runAsync` thành một stage trong workflow

`runAsync` cho `CompletableFuture<Void>`. Sau khi hành động kết thúc, ta có thể dùng các callback:

```java
CompletableFuture<Void> action =
        CompletableFuture.runAsync(() -> update());

CompletableFuture<String> status =
        action.thenApply(ignored -> "completed");
```

Đây là đoạn minh họa. Stage sau được gọi khi `action` hoàn thành **bình thường**; nếu `action` thất bại, `status` cũng có thể thất bại mà không chạy lambda thành công.

Các API thường dùng với `CompletableFuture<Void>`:

- `thenRun(() -> audit())`: chạy một `Runnable` **sau khi** stage trước hoàn thành bình thường, không nhận giá trị.
- `thenApply(ignored -> value)`: tạo một giá trị từ tín hiệu hoàn thành.
- `thenCompose(ignored -> nextAsync())`: nối sang một thao tác async khác.
- `whenComplete((ignored, error) -> ...)`: quan sát outcome thành công/thất bại.
- `handle((ignored, error) -> ...)`: biến cả kết quả hoặc lỗi thành một giá trị/nhánh xử lý mới.

Đừng bỏ Future chỉ vì hành động “không trả kết quả”. Nếu side effect quan trọng, caller cần **quan sát exceptional completion** và xây retry/idempotency nếu hợp lý.

## 17. Thất bại trong `supplyAsync` và `runAsync` được báo thế nào?

Nếu Supplier/Runnable ném một exception không được xử lý bên trong task, `CompletableFuture` tương ứng thường hoàn thành **bất thường**. Lỗi có thể được truy qua `join()` hoặc `get()`:

- `join()` thường ném `CompletionException` với nguyên nhân tại `getCause()` khi computation thất bại.
- `get()` ném `ExecutionException` đối với lỗi của computation, ngoài `InterruptedException` nếu caller bị ngắt.
- Với future bị cancel, `get()`/`join()` có thể ném `CancellationException` trực tiếp.
- Lỗi phát sinh **ngay lúc nộp** vì executor từ chối có thể được báo trực tiếp tại factory method, chứ không nhất thiết tạo ra một future đã hoàn thành lỗi.

`completedFuture(value)` không tự chạy code chứa exception; nó hoàn thành bình thường. Muốn tạo một future **đã hoàn thành thất bại**, Java 17 hỗ trợ `CompletableFuture.failedFuture(cause)`.

### Ví dụ 6: lỗi của Supplier và Runnable

Tạo tệp `AsyncFailureDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

public class AsyncFailureDemo {
    public static void main(String[] args) throws InterruptedException {
        CompletableFuture<Integer> supplied =
                CompletableFuture.supplyAsync(() -> {
                    throw new IllegalArgumentException("bad input");
                });

        CompletableFuture<Void> performed =
                CompletableFuture.runAsync(() -> {
                    throw new IllegalStateException("write failed");
                });

        try {
            supplied.join();
        } catch (CompletionException e) {
            System.out.println("supply wrapper="
                    + e.getClass().getSimpleName());
            System.out.println("supply cause="
                    + e.getCause().getClass().getSimpleName());
            System.out.println("supply message="
                    + e.getCause().getMessage());
        }

        try {
            performed.get();
        } catch (ExecutionException e) {
            System.out.println("run wrapper="
                    + e.getClass().getSimpleName());
            System.out.println("run cause="
                    + e.getCause().getClass().getSimpleName());
            System.out.println("run message="
                    + e.getCause().getMessage());
        }
    }
}
```

```bash
javac AsyncFailureDemo.java
java AsyncFailureDemo
```

Output (trong môi trường bình thường không interrupt caller):

```text
supply wrapper=CompletionException
supply cause=IllegalArgumentException
supply message=bad input
run wrapper=ExecutionException
run cause=IllegalStateException
run message=write failed
```

Hai task có thể chạy theo thứ tự nào cũng được. Main **đợi từng future** và in kết quả theo thứ tự đoạn code, nên output không cần dự đoán thứ tự chạy của worker.

**Không “nuốt” lỗi** bằng cách chỉ gọi `supplyAsync` hoặc `runAsync` rồi bỏ Future. Với `CompletableFuture`, exception được **ghi trong outcome của future**; không thể dựa hoàn toàn vào `UncaughtExceptionHandler` của worker để biết tất cả task đã lỗi.

## 18. Phân biệt lỗi ở callback, lỗi ở task và lỗi từ executor

Có ba nguồn thất bại khác nhau:

**A. Supplier/Runnable ném exception:** Task đã được nhận và khi chạy phát sinh lỗi. Future hoàn thành exceptionally và caller có thể đọc cause.

**B. Executor từ chối task:** Ví dụ `ThreadPoolExecutor` đã shutdown, hoặc queue đầy với `AbortPolicy`. Lời gọi `supplyAsync(..., executor)` hoặc `runAsync(..., executor)` có thể ném `RejectedExecutionException` **ngay tại lúc nộp**, trước khi caller nhận Future.

**C. Stage callback ném lỗi:** `thenApply` hoặc `thenApplyAsync` tạo một **future phụ thuộc riêng**. Future nguồn có thể thành công nhưng future của stage sau thất bại.

Không gộp cả ba thành “lỗi của future gốc”. Khi debug phải biết lỗi xuất hiện ở **factory**, trong **source task**, hay trong **continuation**.

### Ví dụ 7: executor đã đóng, factory bị từ chối

Tạo tệp `AsyncRejectionDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;

public class AsyncRejectionDemo {
    public static void main(String[] args) {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        executor.shutdown();

        try {
            CompletableFuture.supplyAsync(() -> 42, executor);
        } catch (RejectedExecutionException e) {
            System.out.println("supply rejected");
        }

        try {
            CompletableFuture.runAsync(() ->
                    System.out.println("should not execute"), executor);
        } catch (RejectedExecutionException e) {
            System.out.println("run rejected");
        }

        System.out.println("shutdown=" + executor.isShutdown());
    }
}
```

```bash
javac AsyncRejectionDemo.java
java AsyncRejectionDemo
```

Output với executor tiêu chuẩn và rejection policy mặc định:

```text
supply rejected
run rejected
shutdown=true
```

Không có async task nào được nhận nên không có worker đang làm những action đó. Với một `ThreadPoolExecutor` có `RejectedExecutionHandler` tùy biến, hành vi khi bị từ chối có thể khác; luôn xem hợp đồng của executor được truyền vào.

**Lưu ý:** kiểm tra `!executor.isShutdown()` rồi mới nộp task không tránh được race: executor có thể shutdown **giữa** hai lệnh. Đường nộp cần xử lý rejection.

## 19. Xử lý ngoại lệ bằng `exceptionally`, `handle` và `whenComplete`

Có thể quan sát hoặc phục hồi failure **trong pipeline**:

```java
CompletableFuture<Integer> recovered =
        CompletableFuture.supplyAsync(() -> loadValue(), executor)
                .exceptionally(error -> {
                    report(error);
                    return 0;
                });
```

Đây là đoạn minh họa; `loadValue` và `report` là helper của ứng dụng. `exceptionally` có thể **biến exceptional completion thành giá trị mặc định**. Chỉ nên làm vậy nếu `0` thật sự có nghĩa hợp lệ với nghiệp vụ; nếu không, việc bỏ lỗi có thể làm kết quả sai.

`handle((value,error) -> ...)` được gọi khi future nguồn hoàn thành bình thường hoặc bất thường, tạo một outcome mới. `whenComplete((value,error) -> ...)` chủ yếu dùng để **quan sát**, thường giữ kết quả/exception gốc trừ khi callback tự ném lỗi.

### Mẫu giữ nguyên cause

```java
CompletableFuture<Integer> checked =
        CompletableFuture.supplyAsync(() -> parse(), executor)
                .whenComplete((value, error) -> {
                    if (error != null) {
                        logger.error("parse failed", error);
                    }
                });
```

Đây là **pseudocode tích hợp logging**, cần khai báo `parse`, `logger`. Không giả định rằng `error` luôn là exception nghiệp vụ trực tiếp; nó có thể là `CompletionException` hoặc wrapper khác. Khi cần tìm nguyên nhân, đi qua `getCause()` và giữ toàn bộ stack trace, không chỉ một message.

### Không tự động retry mọi lỗi

Một Supplier có thể đã thực hiện **side effect một phần** trước khi ném lỗi: ghi database, gửi request hoặc cập nhật state. Retry không có idempotency hoặc transaction có thể làm thực thi trùng. `CompletableFuture` chỉ ghi nhận outcome của phép tính, không rollback hệ thống bên ngoài.

## 20. `get()`, `join()`, timeout và cách chờ

`get()` và `join()` đều cho phép lấy kết quả sau khi future hoàn thành, nhưng có hợp đồng exception khác nhau:

| API | Khi success | Khi task fail | Khi caller bị interrupt | Khi future bị cancel |
| --- | --- | --- | --- | --- |
| `get()` | Trả `T` | `ExecutionException` | `InterruptedException` | `CancellationException` |
| `join()` | Trả `T` | Thường `CompletionException` | Không khai báo checked interrupt | `CancellationException` |
| `get(timeout, unit)` | Trả `T` | `ExecutionException` | `InterruptedException` | `CancellationException`; có thể `TimeoutException` khi chưa xong |

**`get(timeout)` hết thời hạn không tự gọi `cancel(true)`.** Future có thể tiếp tục chạy dù caller dừng chờ.

`join()` không nhận timeout trong Java 17. Có thể tạo deadline bằng `get(timeout, unit)` hoặc thiết kế pipeline có timeout thông qua `orTimeout`/`completeOnTimeout` tùy yêu cầu.

Đừng dùng `Thread.sleep(100)` rồi đoán task đã xong; nó chỉ ngủ một khoảng thời gian, không đồng bộ với điều kiện hoàn thành.

### Ví dụ 8: timeout khi task đang đợi, sau đó vẫn hoàn thành

Tạo tệp `CompletableTimeoutDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class CompletableTimeoutDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            CompletableFuture<String> future =
                    CompletableFuture.supplyAsync(() -> {
                        started.countDown();
                        try {
                            release.await();
                            return "complete";
                        } catch (InterruptedException e) {
                            Thread.currentThread().interrupt();
                            throw new IllegalStateException(e);
                        }
                    }, executor);

            started.await();
            try {
                future.get(30, TimeUnit.MILLISECONDS);
            } catch (TimeoutException e) {
                System.out.println("timed out");
            }

            System.out.println("cancelled=" + future.isCancelled());
            release.countDown();
            System.out.println("later=" + future.join());
        } finally {
            release.countDown();
            executor.shutdown();
            if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
```

```bash
javac CompletableTimeoutDemo.java
java CompletableTimeoutDemo
```

Output khi không có interrupt ngoài ý muốn:

```text
timed out
cancelled=false
later=complete
```

Task chưa thể hoàn thành khi `release` chưa mở, nên lần chờ đầu **phải hết hạn**. `get(30ms)` không tự cancel; sau khi main mở latch, Supplier trả kết quả và `join()` lấy kết quả.

Ví dụ cố tình chờ không deadline ở lần cuối để chứng minh timeout không phải cancellation. Trong một API có SLA end-to-end thật, phải dùng thời gian còn lại hoặc ngừng đợi theo chính sách.

## 21. `cancel(true)` của CompletableFuture không đảm bảo interrupt task

Đây là một bẫy quan trọng. `CompletableFuture.cancel(boolean mayInterruptIfRunning)` không giống việc luôn điều khiển một `FutureTask` chạy trong một `ThreadPoolExecutor`. Theo hợp đồng của `CompletableFuture`, tham số `mayInterruptIfRunning` **không có tác dụng điều khiển thực thi bằng interrupt trong implementation này**.

Hệ quả:

- `future.cancel(true)` có thể chuyển CompletableFuture sang trạng thái cancelled/exceptional completion.
- **Không đảm bảo Supplier/Runnable thực sự ngừng chạy** nếu đã bắt đầu.
- Có thể xảy ra trường hợp future đã cancel nhưng task vẫn đang thực hiện side effect hoặc cleanup.
- Những stage phụ thuộc có thể nhận trạng thái hoàn thành lỗi/cancel theo contract, nhưng không có nghĩa mọi hành động in-flight đều đã bị dừng.
- Nếu cần stop thật, phải dùng **cơ chế hủy hợp tác**: token, cờ `AtomicBoolean`, timeout của I/O, kiểm tra interrupted status khi code có đường ngắt, hoặc quyền sở hữu task/executor có giao thức rõ ràng.

**Không phát biểu `cancel(true)` luôn interrupt worker chạy `supplyAsync`.** Điều đó không được CompletableFuture bảo đảm.

Một cách minh họa ý tưởng: Supplier đọc `AtomicBoolean stopRequested` ở những điểm an toàn, caller set cờ khi request đã hết hạn. Cần đảm bảo không dừng giữa các cập nhật nhiều field nếu sẽ làm hỏng invariant, và không rò rỉ tài nguyên khi thoát.

## 22. Kiểm soát thread và tránh deadlock do blocking

Giả sử dùng executor chỉ có một worker:

```java
ExecutorService executor = Executors.newSingleThreadExecutor();

CompletableFuture<Integer> outer =
        CompletableFuture.supplyAsync(() -> {
            CompletableFuture<Integer> inner =
                    CompletableFuture.supplyAsync(() -> 42, executor);
            return inner.join();
        }, executor);
```

Đây là **phản ví dụ**. Worker duy nhất đang chạy `outer` nhưng block ở `inner.join()`. `inner` cũng cần chính worker đó để chạy. Khi không có worker khác, workflow có thể **thread-starvation deadlock**.

Không chạy phản ví dụ này trong test đơn giản nếu không có cơ chế hủy và timeout phù hợp. Một cách sửa là **composition thay vì blocking**:

```java
CompletableFuture<Integer> outer =
        CompletableFuture.supplyAsync(() -> "start", executor)
                .thenCompose(ignored ->
                        CompletableFuture.supplyAsync(() -> 42, executor));
```

Đây là đoạn minh họa. `thenCompose` tạo dependency nhưng **không buộc worker thứ nhất giữ một task đang chạy trong khi block chờ task thứ hai**. Stage đầu hoàn thành, rồi stage tiếp theo được nộp; worker có thể xử lý nhiệm vụ mới sau khi stage đầu rời.

Tuy nhiên, việc chọn executor và thiết kế callback vẫn quan trọng: nếu callback tự chặn dài, hoặc có vòng phụ thuộc giữa các future, deadlock vẫn có thể xảy ra.

## 23. Blocking I/O: có nên dùng supplyAsync với common pool?

Một đoạn code:

```java
CompletableFuture<String> data =
        CompletableFuture.supplyAsync(() -> blockingRead());
```

không tự biến `blockingRead()` thành **non-blocking I/O**. Nó chỉ đưa lời gọi chặn sang một thread trong executor mặc định. Trong lúc I/O chặn, worker vẫn có thể bị giữ.

Khi có nhiều request hoặc I/O chặn lâu, cân nhắc:

- Truyền **executor riêng** được sizing và quản lý theo workload.
- Giới hạn số request đồng thời và queue/backpressure.
- Đặt **connect/read/request timeout** ở API I/O thật sự.
- Dùng API asynchronous I/O nếu domain và thư viện có hỗ trợ.
- Thu thập metrics về queue, thread, latency, rejection và timeout.
- Không nộp hàng trăm nghìn blocking Supplier vào common pool mà không kiểm soát.

Với tác vụ CPU-bound ngắn và độc lập, common pool có thể hợp lý. Không có quy tắc “mọi supplyAsync đều phải dùng pool riêng”, nhưng **chính sách executor phải phù hợp kiểu công việc**, không chỉ phù hợp cú pháp lambda.

### runAsync cũng có thể chặn

`runAsync(() -> sendEmail())` vẫn có thể blocking nếu `sendEmail()` thực hiện network I/O đồng bộ. Việc không trả giá trị không giúp worker tự giải phóng khi I/O đang đợi.

## 24. Độ an toàn của dữ liệu chia sẻ và happens-before

Một `CompletableFuture` hoàn thành không làm mọi object mà Supplier/Runnable đụng tới tự động thread-safe.

Ví dụ nguy hiểm:

```java
List<String> results = new ArrayList<>();

CompletableFuture<Void> a =
        CompletableFuture.runAsync(() -> results.add("A"));
CompletableFuture<Void> b =
        CompletableFuture.runAsync(() -> results.add("B"));
```

Đây là đoạn **phản ví dụ**, vì hai Runnable có thể sửa **cùng một `ArrayList`** không đồng bộ, gây data race/corruption. Việc caller đợi cả `a.join()` và `b.join()` **sau cùng** không sửa được race đã xảy ra giữa hai writer.

Các hướng đúng:

- Mỗi Supplier trả một **giá trị độc lập**, sau đó kết hợp khi future hoàn thành.
- Sử dụng concurrent collection hoặc khóa nếu thật sự cần shared mutable state.
- Tổ chức một owner duy nhất cập nhật kết quả.
- Xuất bản immutable DTO/result thay vì sửa shared list từ nhiều worker.

### Ví dụ 9: ghép kết quả hai Supplier không chia sẻ biến mutable

Tạo tệp `CombineIndependentResultsDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class CombineIndependentResultsDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            CompletableFuture<Integer> left =
                    CompletableFuture.supplyAsync(() -> 20, executor);

            CompletableFuture<Integer> right =
                    CompletableFuture.supplyAsync(() -> 22, executor);

            CompletableFuture<Integer> total =
                    left.thenCombine(right, Integer::sum);

            System.out.println("total=" + total.join());
            System.out.println("left=" + left.join());
            System.out.println("right=" + right.join());
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
javac CombineIndependentResultsDemo.java
java CombineIndependentResultsDemo
```

Output:

```text
total=42
left=20
right=22
```

Hai nguồn tạo giá trị bất biến riêng. `thenCombine` chỉ chạy khi cả hai đã hoàn thành bình thường và kết hợp hai giá trị thành một future mới. Không cần một biến `static int sum` hoặc `ArrayList` chung để thu kết quả.

Về memory visibility: `Future.get()` và cơ chế completion của `CompletableFuture` cung cấp quan hệ đồng bộ để caller đọc kết quả đã được công bố. Nhưng nếu các worker tiếp tục sửa object mutable ngoài giao thức, phải dùng các nguyên tắc Java Memory Model phù hợp.

## 25. `thenApply`, `thenApplyAsync`, `thenCompose` và ba factory method

Dễ nhầm `supplyAsync` với mọi API có chữ “Async”. Hãy phân tách rõ:

- `completedFuture(v)`: **nguồn đã có kết quả**.
- `supplyAsync(supplier)`: **nguồn bất đồng bộ mới**, có giá trị do Supplier tạo.
- `runAsync(runnable)`: **nguồn bất đồng bộ mới**, không có giá trị hữu ích.
- `thenApply(fn)`: biến đổi kết quả **của một stage đã có**, có thể chạy inline trên thread liên quan.
- `thenApplyAsync(fn, executor)`: biến đổi kết quả stage trước nhưng **lên lịch callback** qua executor.
- `thenCompose(fn)`: callback trả một `CompletionStage<U>` để **nối phẳng** một phép tính async tiếp theo.
- `thenCombine(other, fn)`: kết hợp hai future độc lập khi cả hai hoàn thành bình thường.

Ví dụ khi một bước trả future:

```java
CompletableFuture<CompletableFuture<Integer>> nested =
        CompletableFuture.completedFuture(1)
                .thenApply(value ->
                        CompletableFuture.supplyAsync(() -> value + 1));
```

Nếu muốn kết quả `CompletableFuture<Integer>` thay vì future lồng future:

```java
CompletableFuture<Integer> flat =
        CompletableFuture.completedFuture(1)
                .thenCompose(value ->
                        CompletableFuture.supplyAsync(() -> value + 1));
```

Đây là các đoạn minh họa. `thenCompose` dùng đúng khi hàm biến đổi **tự trả về CompletionStage**, không phải khi chỉ có phép cộng thuần.

**Không phải mọi bước đều cần async.** `thenApply(x -> x + 1)` cho phép xử lý nhẹ inline, không cần overhead nộp task chỉ để cộng một số.

## 26. Async continuation có luôn chạy trên thread của Supplier không?

Không. Với continuation **không có hậu tố `Async`**:

- Nếu stage nguồn **đã hoàn thành** khi callback được đăng ký, callback có thể chạy ngay ở thread đăng ký.
- Nếu stage nguồn hoàn thành sau khi đăng ký, callback có thể được chạy bởi thread hoàn thành stage hoặc một thread tham gia hoàn thành theo chính sách implementation.
- Không nên viết correctness logic phụ thuộc tên thread hoặc số lần context switch.

Với `thenApplyAsync(fn, executor)`, callback được lên lịch bằng executor được chỉ định (có thể bị từ chối nếu executor shutdown). Nhưng một `Executor` có thể có policy chạy inline, ví dụ `Runnable::run`, nên chữ `Async` ở API nói về **cách nộp qua executor**, không phải cam kết tuyệt đối “luôn khác thread caller”.

### ThreadLocal và context

Vì callbacks có thể chạy trên những thread khác nhau, dữ liệu `ThreadLocal` của thread gọi **không được tự động truyền** qua CompletableFuture stage. Nếu cần correlation ID, security context hay request metadata, phải **truyền tường minh** trong dữ liệu hoặc dùng một cơ chế context propagation được kiểm soát.

Đặc biệt, `ThreadLocal` đặt trên pooled worker có thể **tồn tại giữa các task** nếu không `remove()` trong `finally`. Cần quản lý cleanup, không dựa vào CompletableFuture để xóa ThreadLocal thay mình.

## 27. Nộp nhiều task và đợi tổng thể bằng `allOf()`

Ví dụ các Supplier độc lập:

```java
CompletableFuture<String> a =
        CompletableFuture.supplyAsync(() -> "A", executor);
CompletableFuture<String> b =
        CompletableFuture.supplyAsync(() -> "B", executor);

CompletableFuture<Void> all = CompletableFuture.allOf(a, b);
all.join();

String combined = a.join() + b.join();
```

Đây là đoạn minh họa với `executor` hợp lệ. `allOf` trả một `CompletableFuture<Void>` báo khi các stage đầu vào đã hoàn tất. Nó không gom sẵn kết quả thành `List<T>`; muốn có các value, caller vẫn đọc các future riêng sau khi tổng thể thành công.

Nếu một future đầu vào thất bại, `allOf` có thể hoàn thành lỗi. **Đừng nghĩ `allOf` tự cancel tất cả task còn lại hay rollback tác dụng phụ**. Nó chỉ xây quan hệ hoàn tất; chính sách dừng/retry/cleanup thuộc tầng ứng dụng.

`anyOf` thì hoàn thành khi một future đầu vào hoàn thành (bình thường hoặc bất thường); nó có kiểu `CompletableFuture<Object>` nếu dùng overload chung. Không tự mặc định `anyOf` chọn “kết quả thành công đầu tiên” như một cơ chế failover tối ưu.

## 28. Phân biệt `completedFuture`, `failedFuture` và `new CompletableFuture<>()`

Ba cách tạo future này khác nhau:

```java
CompletableFuture<String> success =
        CompletableFuture.completedFuture("OK");

CompletableFuture<String> failure =
        CompletableFuture.failedFuture(
                new IllegalStateException("failed"));

CompletableFuture<String> pending =
        new CompletableFuture<>();
```

- `success`: đã hoàn thành **bình thường**.
- `failure`: đã hoàn thành **bất thường**; `join()` có thể ném `CompletionException`.
- `pending`: **chưa hoàn thành**; một thread/callback khác cần gọi `complete(value)`, `completeExceptionally(error)` hoặc `cancel(...)`.

`new CompletableFuture<>()` không tự lên lịch bất kỳ task nào. Nếu không ai hoàn thành nó, `join()` có thể đợi vô hạn.

Một lỗi thường gặp là dùng `new CompletableFuture<>()` thay cho `supplyAsync` rồi quên viết code hoàn thành tương ứng. Khi có công việc ở nguồn, dùng factory async hoặc một callback được quản lý là cách rõ ràng hơn.

## 29. Quan sát kết quả nhưng không block thread caller

Nếu mục tiêu là tiếp tục xử lý khi kết quả có sẵn mà **không block thread hiện tại**, dùng stage completion thay vì gọi `join()` quá sớm:

```java
CompletableFuture<Integer> loaded =
        CompletableFuture.supplyAsync(() -> load(), executor);

CompletableFuture<Void> reported =
        loaded.thenAccept(value -> report(value));
```

Đây là đoạn minh họa; `load`, `report` và `executor` được ứng dụng định nghĩa. `thenAccept` tạo một stage hoàn tất khi callback tiêu thụ value thành công. Không cần chặn caller ngay ở giữa pipeline.

**Nhưng:** nếu ứng dụng rời scope, đóng executor hoặc process thoát trước khi stage hoàn tất, task có thể chưa được thực hiện hết theo yêu cầu nghiệp vụ. Phải có một **owner của pipeline**, quyết định khi nào chờ/tổng hợp/cancel và đóng tài nguyên.

Nếu cần được thông báo khi hoàn thành, có thể lưu Future và `whenComplete` log outcome; nếu cần giới hạn latency, cấu hình deadline và đảm bảo cleanup. Việc không gọi `join()` ngay không có nghĩa lỗi được bỏ qua hoặc workflow tự được quản lý.

## 30. Hoàn tất và shutdown executor có trật tự

Một ứng dụng thường muốn:

1. Tạo/nhận executor thuộc scope phù hợp.
2. Nộp các task ban đầu bằng `supplyAsync`/`runAsync`.
3. Xây **toàn bộ pipeline phụ thuộc** trước khi bắt đầu đóng executor.
4. Đợi **future cuối cùng** hoặc một tập outcome với deadline nếu cần.
5. Xử lý exceptional completion, cancellation, retry/recovery.
6. Nếu **chính mình sở hữu executor**, yêu cầu shutdown và đợi termination có giới hạn.

Một helper cho JDK 17:

```java
static boolean stopExecutor(ExecutorService executor)
        throws InterruptedException {
    executor.shutdown();

    if (executor.awaitTermination(5, TimeUnit.SECONDS)) {
        return true;
    }

    executor.shutdownNow();

    return executor.awaitTermination(5, TimeUnit.SECONDS);
}
```

Đây là đoạn minh họa trong class có imports phù hợp. Nó đóng hai giai đoạn, ưu tiên graceful rồi cố hủy các task còn lại. `shutdownNow()` không bảo đảm dừng thread ngay; nếu bước cuối trả false thì lifecycle chưa xác nhận terminated.

### Bẫy: đóng executor trước khi stage phụ thuộc được schedule

Ví dụ:

```java
CompletableFuture<Integer> first =
        CompletableFuture.supplyAsync(() -> 1, executor);

CompletableFuture<Integer> second =
        first.thenApplyAsync(value -> value + 1, executor);

executor.shutdown(); // Có thể quá sớm cho stage phụ thuộc.
```

Đây là đoạn **phản ví dụ**. Stage `second` có thể cần gọi executor để schedule **sau khi `first` hoàn thành**. Nếu executor đã shutdown, nó có thể không nhận stage ấy, dẫn tới exceptional completion liên quan rejection. Không đồng nhất “đã nộp source task” với “mọi dependent task tương lai đã được executor chấp nhận”.

Một pattern dễ kiểm soát hơn là xây/đợi các pipeline cuối trước khi shutdown hoặc dùng một lifecycle coordinator biết chính xác những dependent stages cần nộp về sau.

## 31. Timeout chung cho nhiều future

Một lỗi latency: gọi `first.get(1, SECONDS)` rồi `second.get(1, SECONDS)` rồi `third.get(1, SECONDS)`, nhưng nghĩ tổng thời gian chờ được giới hạn 1 giây. Thực tế có thể chờ gần 3 giây cộng overhead.

Nếu có ngân sách end-to-end, dùng `System.nanoTime()` đo elapsed và tính **remaining** ngay trước từng `get(timeout, TimeUnit.NANOSECONDS)`:

```java
long started = System.nanoTime();
long budget = TimeUnit.SECONDS.toNanos(1);

long remaining1 = Math.max(
        0L, budget - (System.nanoTime() - started));
T1 firstValue = first.get(remaining1, TimeUnit.NANOSECONDS);

long remaining2 = Math.max(
        0L, budget - (System.nanoTime() - started));
T2 secondValue = second.get(remaining2, TimeUnit.NANOSECONDS);
```

Đây là **pseudocode generic** (`T1`, `T2` và các future phải có kiểu thực tế). Nếu budget hết, cần phản hồi timeout theo contract, không cứ dùng lại toàn bộ thời hạn ban đầu.

`System.nanoTime()` là đồng hồ đo elapsed trong JVM; không phải Unix timestamp. Không dùng `System.currentTimeMillis()` như monotonic deadline nếu có thể bị chỉnh wall clock.

`get(timeout)` giới hạn **thời gian chờ**, không tự hủy task; nếu request hết SLA, chính sách cancel và xử lý side effects phải được thiết kế riêng.

## 32. Kiểm thử CompletableFuture đáng tin cậy

### Không assert future async luôn chưa done

Task rất nhanh có thể hoàn thành trước khi caller đọc `isDone()`. Dùng `CountDownLatch` như `AsyncStateLifecycleDemo` để giữ task tại một điểm xác định.

### Không dùng `Thread.sleep` để chờ kết quả

Sử dụng `join()`/`get()` khi test cần xác nhận completion, cùng timeout lớn hơn dao động scheduler nếu test có deadline. Khi dùng latch, phải có đường mở latch trong `finally` để test không làm rò rỉ worker khi exception xuất hiện.

### Kiểm tra cả hai outcome

Không chỉ assert giá trị thành công; với lỗi, kiểm tra wrapper/cause của `join/get`. Với `runAsync`, kiểm tra action thực sự hoàn tất, không chỉ thấy một Future type `Void`.

### Đóng executor test đúng cách

Nếu test tạo `ExecutorService` riêng, shutdown trong `finally`, đợi có giới hạn và báo lỗi nếu vẫn không terminated. Đừng “sửa” lỗi thread leak bằng cách làm tất cả thread thành daemon: daemon thread có thể khiến JVM thoát trước khi resource/side effect hoàn tất.

### Tránh assert tên thread của common pool

`CompletableFuture.supplyAsync(() -> Thread.currentThread().getName())` không có tên thread được đảm bảo. Muốn test executor selection, dùng một `ThreadFactory` do test kiểm soát như `NamedExecutorDemo`.

### Kiểm tra rủi ro shared state

Nếu hai task sửa cùng một `ArrayList` hoặc cấu trúc mutable, việc đọc kết quả qua `join` sau cùng không xóa data race. Dùng immutable results hoặc concurrency primitives đúng.

## 33. Các lỗi thường gặp

### 33.1. Nghĩ `completedFuture` chạy task bất đồng bộ

Sai. Nó tạo một Future đã hoàn thành bình thường với giá trị có sẵn. Không nộp Supplier/Runnable lên worker.

### 33.2. Nghĩ `supplyAsync` luôn trả về trước khi task kết thúc

Không bảo đảm. Một Supplier rất nhanh có thể hoàn tất trước khi method trả về; không assert `!isDone()` ngay sau factory.

### 33.3. Dùng `runAsync` rồi cố lấy giá trị kiểu nghiệp vụ từ `join()`

`CompletableFuture<Void>` hoàn thành bình thường với `null`. Nếu cần giá trị thật, dùng `supplyAsync`.

### 33.4. Cho rằng tất cả callback downstream đều chạy trên cùng worker

`thenApply` không đảm bảo affinity; `thenApplyAsync` chỉ rõ scheduling qua executor (nếu truyền). Không dựa vào ThreadLocal hoặc thread name ngoài contract.

### 33.5. Dùng common pool để chạy I/O chặn không kiểm soát

Có thể giữ worker lâu và ảnh hưởng task khác; chọn executor, timeout và giới hạn concurrency phù hợp.

### 33.6. Tạo executor mới cho từng lời gọi rồi không shutdown

Có thể làm thread/resource tăng mãi theo request. Xác định owner và lifecycle của pool.

### 33.7. Bỏ Future vì “fire-and-forget”

Exception của Runnable/Supplier có thể chỉ được ghi trong outcome của CompletableFuture. Nếu không ai quan sát, lỗi bị bỏ sót từ góc nhìn ứng dụng.

### 33.8. Catch `CompletionException` nhưng bỏ cause

Thông tin lỗi chính thường nằm ở `getCause()`; log cả throwable/cause chain khi cần chẩn đoán.

### 33.9. Nhầm `get(timeout)` với cancel

Timeout chỉ kết thúc **lời chờ** ở caller; task có thể tiếp tục. Cancellation phải theo chính sách riêng.

### 33.10. Nghĩ `CompletableFuture.cancel(true)` chắc chắn interrupt Supplier

Không. Đối với CompletableFuture, `mayInterruptIfRunning` không điều khiển việc thực thi bằng interrupt theo hợp đồng; dùng hợp tác hủy khi cần.

### 33.11. Đóng executor khi pipeline vẫn có dependent stage chưa nộp

Các stage `...Async(..., executor)` phụ thuộc có thể bị rejected sau shutdown. Đợi final stages hoặc điều phối lifecycle đúng.

### 33.12. Gọi `join()` của task con trên chính worker duy nhất của executor

Có thể gây thread-starvation deadlock. Ưu tiên composition thay vì blocking.

### 33.13. Trả về mutable object rồi cho nhiều thread sửa

CompletableFuture công bố outcome, không tự biến object mutable thành thread-safe. Dùng immutable DTO hoặc synchronization phù hợp.

### 33.14. Bỏ qua lỗi của dependent stage

Future nguồn thành công không có nghĩa `thenApply`/`thenAccept`/`thenCompose` tiếp theo thành công. Quan sát **future cuối** hoặc toàn bộ outcome cần thiết.

### 33.15. Dùng fallback mặc định không xét nghiệp vụ

`exceptionally(error -> 0)` có thể che một lỗi nghiêm trọng. Chỉ phục hồi khi fallback thật sự hợp lệ.

### 33.16. Lẫn lộn hành động đã kết thúc và side effect đã commit

`runAsync` thành công nghĩa Runnable trả về bình thường; nếu I/O/transaction bên trong có semantics riêng, phải đảm bảo durable success theo hợp đồng nghiệp vụ.

## 34. Checklist chọn API

Trước khi viết một thao tác bất đồng bộ, tự hỏi:

1. **Đã có giá trị ngay?** → `completedFuture(value)`.
2. **Có một công việc cần chạy và trả dữ liệu?** → `supplyAsync(supplier[, executor])`.
3. **Có công việc cần chạy, chỉ quan tâm completion/failure?** → `runAsync(runnable[, executor])`.
4. **Kết quả có cần được biến đổi?** → `thenApply` hoặc `thenApplyAsync`.
5. **Bước tiếp theo tự trả CompletionStage?** → `thenCompose` để flatten.
6. **Hai phép tính độc lập cần kết hợp?** → `thenCombine` hoặc `allOf` tùy loại kết quả.
7. **Task có blocking I/O, CPU-heavy hoặc side effect?** → chọn executor và timeout tương ứng.
8. **Ai sở hữu Future?** → nơi nào sẽ quan sát kết quả/lỗi, timeout, cancel?
9. **Ai sở hữu executor?** → nơi nào shutdown và đảm bảo không có dependent stage đang cần schedule?
10. **Có shared mutable state?** → dùng immutable result, đồng bộ hoặc ownership rõ ràng.
11. **Có yêu cầu deadline tổng?** → không reset timeout ở mỗi bước.
12. **Task fail hoặc bị cancel?** → propagate, log, retry, recovery và cleanup thế nào?

Một lựa chọn đúng phải dựa trên **ngữ nghĩa công việc**, không chỉ ký hiệu API ngắn nhất.

## 35. Bài tập thực hành

**Bài tập 1: cache hit / cache miss.** Xây method trả `CompletableFuture<String>`. Nếu Map có key, dùng `completedFuture`; nếu không, dùng `supplyAsync` với executor phù hợp. Đừng nhầm kiểm tra `containsKey` và `get` là giao dịch nguyên tử nếu Map đang bị sửa.

**Bài tập 2: tính tổng hai phép tính.** Dùng hai `supplyAsync` trả `20` và `22`. Ghép bằng `thenCombine(Integer::sum)`. Assert `42` mà không dựa vào thứ tự worker.

**Bài tập 3: một action không có result.** Dùng `runAsync` với `AtomicInteger` tăng một lần; gọi `join()`, kiểm tra `Void` trả `null` và biến đếm bằng 1.

**Bài tập 4: kiểm tra lifecycle.** Dùng `CountDownLatch` để Supplier chờ. Xác nhận `isDone()==false` trước khi release và true sau `join()`.

**Bài tập 5: rejection.** Tạo single-thread executor, shutdown, sau đó gọi `runAsync(..., executor)`. Kiểm tra `RejectedExecutionException` được xử lý ở **thời điểm nộp task**.

**Bài tập 6: cancel hợp tác.** Trong Supplier CPU-bound, đọc token `AtomicBoolean` tại các điểm an toàn. Caller set token sau deadline, theo dõi thời điểm task thực sự dừng và phân biệt với trạng thái canceled của CompletableFuture.

**Bài tập 7: chuyển stage.** Khởi đầu từ `completedFuture(10)`, `thenApply` nhân 2, `thenApplyAsync` cộng 5 trên custom executor. Assert `25`, không assert callback chạy trên một tên worker cố định nếu không điều khiển ThreadFactory.

**Bài tập 8: không block cùng executor.** Thử composition `thenCompose` để task con trên executor đơn, phân biệt với phản ví dụ inner.join() có nguy cơ deadlock.

## 36. Câu hỏi tự kiểm tra

**Câu 1.** `CompletableFuture.completedFuture(42)` có khởi động thread để tính 42 không?

**Đáp án:** Không. Nó tạo một CompletableFuture đã hoàn thành bình thường với giá trị 42.

**Câu 2.** `supplyAsync` nhận functional interface nào và trả kiểu future gì?

**Đáp án:** Nhận `Supplier<T>`; trả `CompletableFuture<T>` hoàn thành bằng giá trị `Supplier.get()`.

**Câu 3.** `runAsync` nhận gì và trả loại future nào?

**Đáp án:** Nhận `Runnable`; trả `CompletableFuture<Void>`. Khi thành công, `join()` trả null.

**Câu 4.** Vì sao không thể assert `!future.isDone()` ngay sau `supplyAsync(() -> 1)`?

**Đáp án:** Task rất nhanh có thể hoàn thành trước lúc caller kiểm tra; thứ tự phụ thuộc lịch chạy.

**Câu 5.** Không truyền executor, supplyAsync/runAsync thường dùng gì?

**Đáp án:** Mặc định thường dùng `ForkJoinPool.commonPool()`, với fallback tạo thread mới trong những điều kiện parallelism đặc thù theo contract CompletableFuture.

**Câu 6.** Nếu cần kiểm soát tên worker và shutdown, dùng overload nào?

**Đáp án:** `supplyAsync(supplier, executor)` hoặc `runAsync(runnable, executor)` với một executor do thành phần sở hữu quản lý.

**Câu 7.** `completedFuture(null)` có phải một future chưa done không?

**Đáp án:** Không. Nó đã hoàn thành bình thường với kết quả null; `isDone()` là true.

**Câu 8.** Supplier ném IllegalArgumentException; `future.join()` thường báo gì?

**Đáp án:** Thường ném `CompletionException`, với `getCause()` là `IllegalArgumentException`.

**Câu 9.** Khi dùng `future.get()` với task bị lỗi, wrapper checked thường là gì?

**Đáp án:** `ExecutionException`; xem `getCause()` để truy lỗi task.

**Câu 10.** `future.get(100, MILLISECONDS)` timeout có tự hủy task không?

**Đáp án:** Không. Nó chỉ giới hạn thời gian chờ caller, trừ khi ứng dụng chủ động áp dụng chính sách hủy.

**Câu 11.** `CompletableFuture.cancel(true)` có bảo đảm ngắt thread đang chạy Supplier không?

**Đáp án:** Không. `mayInterruptIfRunning` không dùng để điều khiển thực thi bằng interrupt trong CompletableFuture.

**Câu 12.** Nếu future nguồn đã completed, `thenApply` có bắt buộc chạy trên worker không?

**Đáp án:** Không. Callback có thể chạy trong thread đăng ký, nên không dùng nó để cam kết background execution.

**Câu 13.** Tại sao dùng `thenCompose` khi callback trả về CompletableFuture?

**Đáp án:** Để nối phẳng stage, tránh kiểu lồng `CompletableFuture<CompletableFuture<T>>`.

**Câu 14.** Hai Supplier ghi đồng thời vào cùng `ArrayList`; chỉ đợi `allOf` có đủ thread-safe không?

**Đáp án:** Không. Đợi sau khi task xong không khắc phục race giữa hai writer. Cần cấu trúc dữ liệu/giao thức đồng bộ đúng.

**Câu 15.** Gọi shutdown executor sau khi nộp source task nhưng trước khi dependent `thenApplyAsync` sẵn sàng có thể xảy ra gì?

**Đáp án:** Dependent stage có thể bị executor từ chối khi cần schedule, dẫn tới completion lỗi; cần điều phối lifecycle của cả pipeline.

**Câu 16.** Vì sao nên quản lý executor theo scope service thay vì tạo mới mỗi request?

**Đáp án:** Để kiểm soát số worker, queue/backpressure, reuse và shutdown, tránh thread/resource leak.

**Câu 17.** Khi nào dùng `runAsync` thay vì `supplyAsync`?

**Đáp án:** Khi công việc không có dữ liệu trả về hữu ích, chỉ cần biết completed/failed; nếu có kết quả nghiệp vụ, dùng Supplier.

**Câu 18.** Dùng `completedFuture(mutableObject)` có tự deep-copy object không?

**Đáp án:** Không. Future giữ reference; cần immutable snapshot/đồng bộ nếu object được dùng giữa các thread.

## 37. Tóm tắt

Ba factory method của `CompletableFuture` giải quyết ba nhu cầu khác nhau:

- **`completedFuture(value)`**: đã có một giá trị, tạo future **đã hoàn thành bình thường** ngay, không tự chạy tác vụ nền.
- **`supplyAsync(supplier[, executor])`**: cần **thực thi công việc có kết quả**; future hoàn thành với giá trị do Supplier trả hoặc lỗi do Supplier ném.
- **`runAsync(runnable[, executor])`**: cần **thực thi công việc không có giá trị trả về**; future kiểu `Void` hoàn thành bình thường với `null` hoặc hoàn thành lỗi nếu Runnable thất bại.

Các thao tác async không cam kết rằng `isDone` chắc chắn false lúc factory trả về, không cam kết tên thread cụ thể và không tự làm shared mutable state an toàn. Không truyền executor thường dùng common pool; với workload blocking/lifecycle đặc thù nên dùng executor do ứng dụng sở hữu và quản lý shutdown.

Khi viết ứng dụng, hãy giữ Future và kiểm tra outcome qua `join/get` hoặc pipeline xử lý lỗi, phân biệt `CompletionException` / `ExecutionException` / timeout / cancellation, dùng composition để tránh chặn worker trong cùng executor, và thiết kế deadline cũng như hủy hợp tác. **CompletableFuture là công cụ tổ chức luồng hoàn tất của công việc; tính đúng đắn còn phụ thuộc executor, dữ liệu và giao thức nghiệp vụ.**
