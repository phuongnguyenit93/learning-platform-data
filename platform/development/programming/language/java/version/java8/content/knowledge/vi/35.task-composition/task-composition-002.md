# thenCombine, thenAcceptBoth và runAfterBoth trong CompletableFuture (Java 8+)

> **Chủ đề:** Ghép tác vụ. Ba phương thức này thuộc `CompletionStage`/`CompletableFuture` trong `java.util.concurrent`. Chúng tạo một stage phụ thuộc **hai stage nguồn**; hành động được kích hoạt khi **cả hai hoàn thành bình thường**. `thenCombine` tạo **giá trị mới**, `thenAcceptBoth` **dùng cả hai kết quả** cho side effect, còn `runAfterBoth` chỉ cần biết cả hai thành công mà **không đọc kết quả**. Tất cả đều có từ Java 8 và vẫn áp dụng trên JDK hiện đại.

## 1. Mục tiêu học tập

Bạn sẽ phân biệt `BiFunction`, `BiConsumer` và `Runnable`; hiểu generic type và `CompletableFuture<Void>`; chọn bản thường hoặc `Async` với Executor; xử lý việc hai source hoàn tất ở thứ tự bất kỳ; thiết kế exception/cancellation đúng; và so sánh với `thenCompose`, `thenApply`, `allOf` cùng nhóm *either*.

## 2. CompletionStage và CompletableFuture

`CompletionStage<T>` là một giai đoạn có thể hoàn thành trong tương lai với giá trị `T` hoặc hoàn thành bất thường. `CompletableFuture<T>` là triển khai phổ biến, cung cấp `supplyAsync`, `completedFuture`, `complete`, `completeExceptionally`, `join` và các phương thức ghép.

```java
CompletableFuture<Integer> subtotal =
        CompletableFuture.supplyAsync(() -> 120);
CompletableFuture<Integer> shipping =
        CompletableFuture.supplyAsync(() -> 30);
```

`supplyAsync` tạo/lập lịch công việc nguồn. `thenCombine` và hai phương thức còn lại **không tự tạo dữ liệu nguồn**: nếu chỉ có hai `new CompletableFuture<>()` còn dang dở, chúng sẽ tiếp tục chờ cho tới khi một cơ chế khác hoàn tất source.

Trạng thái source có thể là bình thường (có giá trị, kể cả `null` nếu được cho phép), bất thường (exception/cancellation), hoặc chưa hoàn thành. Một `CompletableFuture<Void>` hoàn thành thành công có `join() == null` vì không có giá trị đầu ra hữu ích, **không có nghĩa nó chưa chạy**.

## 3. So sánh ba method

| Method | Điều kiện callback | Action nhận gì | Kết quả của callback | Stage trả về |
| --- | --- | --- | --- | --- |
| `a.thenCombine(b,fn)` | A và B thành công | `BiFunction<T,U,R>`, nhận hai kết quả | Giá trị `R` | `CompletableFuture<R>` |
| `a.thenAcceptBoth(b,action)` | A và B thành công | `BiConsumer<T,U>`, nhận hai kết quả | `void` | `CompletableFuture<Void>` |
| `a.runAfterBoth(b,action)` | A và B thành công | `Runnable`, không nhận kết quả | `void` | `CompletableFuture<Void>` |

```text
Future A ──┐
           ├── CẢ HAI complete normally ──> callback ──> Future kết quả
Future B ──┘
```

Thứ tự A/B hoàn thành là không xác định, nhưng tham số thứ nhất của callback luôn đến từ future đứng trước dấu chấm, tham số thứ hai đến từ `other`. Hai stage nguồn **không cần cùng kiểu**. Các callback phụ thuộc độc lập cũng không có bảo đảm thứ tự thực thi với nhau.

## 4. thenCombine: hai kết quả thành một

Chữ ký của `CompletionStage<T>`:

```java
<U,V> CompletionStage<V> thenCombine(
        CompletionStage<? extends U> other,
        BiFunction<? super T, ? super U, ? extends V> fn);
```

`T` là kiểu giá trị từ nguồn thứ nhất, `U` từ nguồn thứ hai, `V` là kiểu giá trị do hàm kết hợp trả về.

```java
CompletableFuture<Integer> price =
        CompletableFuture.completedFuture(120);
CompletableFuture<Integer> shipping =
        CompletableFuture.completedFuture(30);

CompletableFuture<Integer> total =
        price.thenCombine(shipping, (a, b) -> a + b);

int amount = total.join(); // 150.
```

Đối với hai completed future, callback có thể được thực thi ngay khi đăng ký. **Không** kết luận `thenCombine` tự tạo một thread mới.

Hai kiểu nguồn khác nhau vẫn được:

```java
CompletableFuture<String> customer =
        CompletableFuture.completedFuture("KH-42");
CompletableFuture<Integer> points =
        CompletableFuture.completedFuture(42);

CompletableFuture<String> message =
        customer.thenCombine(points,
                (id, p) -> id + " has " + p + " points");
// "KH-42 has 42 points".
```

Chọn `thenCombine` khi hai công việc độc lập có thể tiến hành đồng thời, nhưng bước sau cần cả hai giá trị: đơn hàng + phí giao hàng, dữ liệu hồ sơ + quyền hoặc dữ liệu giá + thuế.

**Không blocking quá sớm:** thay vì `a.join()`, `b.join()` trên request thread, tạo dependent stage và trả nó cho caller để luồng xử lý tiếp tục bất đồng bộ. Chỉ `join()` ở ranh giới đồng bộ thích hợp, ví dụ chương trình console hay unit test.

## 5. thenAcceptBoth: tiêu thụ hai giá trị

Chữ ký:

```java
<U> CompletionStage<Void> thenAcceptBoth(
        CompletionStage<? extends U> other,
        BiConsumer<? super T, ? super U> action);
```

`BiConsumer` nhận hai giá trị nguồn nhưng không trả một kết quả mới.

```java
CompletableFuture<Integer> a =
        CompletableFuture.completedFuture(120);
CompletableFuture<Integer> b =
        CompletableFuture.completedFuture(30);

AtomicReference<String> audit = new AtomicReference<>();

CompletableFuture<Void> audited = a.thenAcceptBoth(
        b, (x, y) -> audit.set("subtotal=" + x + ", shipping=" + y));

audited.join();
// audit.get() == "subtotal=120, shipping=30".
// audited.join() == null.
```

Snippet cần `import java.util.concurrent.atomic.AtomicReference;`. Trong ứng dụng thực, side effect có thể ghi audit, phát event, cập nhật UI/database. Cần tính đến retry, idempotency, transaction và nguy cơ duplicate: chỉ vì một callback hoàn thành bình thường **không** có nghĩa toàn workflow được bảo đảm exactly-once.

Nếu cần lấy giá trị kết quả cho stage sau, `thenCombine` sẽ phù hợp hơn. `thenAcceptBoth` trả `Void`; không mong `audited.join()` trả object audit.

## 6. runAfterBoth: không đọc dữ liệu của hai nguồn

Chữ ký:

```java
CompletionStage<Void> runAfterBoth(
        CompletionStage<?> other,
        Runnable action);
```

`Runnable` không nhận tham số; chỉ được gọi khi cả hai stage hoàn thành bình thường.

```java
CompletableFuture<Integer> a =
        CompletableFuture.completedFuture(120);
CompletableFuture<String> b =
        CompletableFuture.completedFuture("OK");
AtomicInteger count = new AtomicInteger();

CompletableFuture<Void> signaled =
        a.runAfterBoth(b, count::incrementAndGet);

signaled.join();
// count.get() == 1; signaled.join() == null.
```

Snippet cần `AtomicInteger`. Phù hợp khi chỉ cần đánh dấu cả hai bước chuẩn bị thành công, không cần dùng giá trị.

**Quan trọng: không phải finally.** Nếu một nguồn lỗi hoặc bị hủy, `Runnable` không chạy. `a.thenRun(r)` cũng **khác** `a.runAfterBoth(b,r)`: `thenRun` chỉ phụ thuộc A, còn `runAfterBoth` phụ thuộc A và B.

## 7. Nhiều dependent stage không có thứ tự tự động

```java
CompletableFuture<Integer> sum =
        a.thenCombine(b, (x, y) -> x + y);

CompletableFuture<Void> audit =
        a.thenAcceptBoth(b, (x, y) -> {
            // Dùng hai giá trị nguồn.
        });

CompletableFuture<Void> signal =
        a.runAfterBoth(b, () -> {
            // Chỉ cần trạng thái thành công.
        });
```

Trong snippet, giả định `a` và `b` đều có kiểu Integer. Ba nhánh trên cùng dựa vào A/B nhưng **không** tạo thứ tự `sum → audit → signal`. Nếu cần audit dựa vào sum rồi mới phát tín hiệu, nối stage:

```java
CompletableFuture<Void> ordered = sum
        .thenAccept(value -> {
            // Audit tổng đã tính.
        })
        .thenRun(() -> {
            // Chỉ chạy sau audit thành công.
        });
```

Khi muốn hàm kết hợp thuần tính toán, nên giữ `BiFunction` không có side effect và tách việc ghi dữ liệu sang một stage có trách nhiệm rõ ràng.

## 8. Bản thường và các biến thể Async

| Thường | Async mặc định | Async với Executor |
| --- | --- | --- |
| `thenCombine(b,fn)` | `thenCombineAsync(b,fn)` | `thenCombineAsync(b,fn,executor)` |
| `thenAcceptBoth(b,action)` | `thenAcceptBothAsync(b,action)` | `thenAcceptBothAsync(b,action,executor)` |
| `runAfterBoth(b,action)` | `runAfterBothAsync(b,action)` | `runAfterBothAsync(b,action,executor)` |

**Bản thường:** callback có thể chạy ở thread hoàn thành một source, hoặc một thread khác gọi phương thức hoàn tất; đừng giả định callback luôn chạy ở thread tạo pipeline.

**Async không truyền executor:** dùng default asynchronous execution facility của stage. Với `CompletableFuture` thông thường, mặc định liên quan `ForkJoinPool.commonPool` (có chi tiết thay thế theo cấu hình/runtime). Không tự coi đó là pool tối ưu cho blocking I/O.

**Async có executor:** chỉ định nơi lập lịch callback:

```java
ExecutorService pool = Executors.newFixedThreadPool(3);
try {
    CompletableFuture<Integer> x =
            CompletableFuture.supplyAsync(() -> 120, pool);
    CompletableFuture<Integer> y =
            CompletableFuture.supplyAsync(() -> 30, pool);
    CompletableFuture<Integer> total =
            x.thenCombineAsync(y, Integer::sum, pool);
    System.out.println(total.join()); // 150.
} finally {
    pool.shutdown();
}
```

`Async` không tự biến các nguồn thành công việc chạy song song: cách nguồn được tạo và kích thước Executor quyết định. Với callback ngắn không blocking, bản non-Async có thể phù hợp; với công việc cần cách ly tài nguyên, truyền Executor. Tránh `join()` một future còn phụ thuộc **chính thread pool nhỏ đang bị chiếm giữ**, vì dễ starvation/deadlock.

### Thread safety và memory consistency

Hai source và các callback độc lập có thể chạy trên nhiều thread. Hãy dùng immutable data, đồng bộ hóa hoặc các kiểu atomic khi chia sẻ mutable state. `CompletionStage` có quy tắc happens-before từ hành động của source tới dependent stage sau khi source hoàn thành, nhưng **không** đảm bảo thứ tự các callback độc lập. Ví dụ hoàn chỉnh đợi `allOf(...).join()` trước khi đọc các `AtomicReference`/`AtomicInteger` để không phụ thuộc thứ tự callback.

## 9. Khi chỉ một nguồn đã hoàn thành

```java
CompletableFuture<String> left = new CompletableFuture<>();
CompletableFuture<String> right = new CompletableFuture<>();

CompletableFuture<String> both =
        left.thenCombine(right, (x, y) -> x + "/" + y);

left.complete("A");
boolean completedYet = both.isDone(); // false.

right.complete("B");
String result = both.join(); // "A/B".
```

`thenCombine` **chờ cả hai nguồn thành công**. Thứ tự A/B hoàn thành không đảo vị trí tham số. Nếu một nguồn mãi không complete, dependent stage cũng có thể chờ vô hạn; bản thân `thenCombine` không cung cấp deadline hay tự động hủy source.

## 10. Exception, cancellation và recovery

```java
CompletableFuture<Integer> broken = new CompletableFuture<>();
CompletableFuture<Integer> ok =
        CompletableFuture.completedFuture(7);

CompletableFuture<Integer> combined =
        broken.thenCombine(ok, Integer::sum);

broken.completeExceptionally(
        new IllegalStateException("source failed"));
// combined hoàn thành bất thường; BiFunction không chạy.
```

Với nguồn hoàn thành bất thường, các callback của `thenCombine`, `thenAcceptBoth`, `runAfterBoth` không chạy; stage phụ thuộc cũng chịu exceptional completion theo quy tắc API. Không coi runAfterBoth như cleanup luôn được gọi.

**Recovery sau ghép:**

```java
CompletableFuture<Integer> recovered =
        combined.exceptionally(error -> -1);
// recovered.join() == -1 nếu combined thất bại.
```

`exceptionally` cho một giá trị thay thế trên nhánh lỗi; `handle((value,error)->...)` có thể xử lý cả thành công lẫn thất bại; `whenComplete((value,error)->...)` thiên về quan sát/tracing cho cả hai trạng thái, thông thường chuyển tiếp kết quả/lỗi ban đầu nếu callback không tự gây lỗi.

**Recovery trước ghép** sẽ tạo hành vi khác: mỗi nguồn được thay bằng một fallback rồi callback kết hợp có thể tiếp tục chạy. Không đặt mặc định 0 cho giá/đơn hàng hỏng nếu điều đó làm sai kết quả nghiệp vụ.

```java
CompletableFuture<Integer> safeA =
        a.exceptionally(error -> 0);
CompletableFuture<Integer> safeB =
        b.exceptionally(error -> 0);

CompletableFuture<Integer> value =
        safeA.thenCombine(safeB, Integer::sum);
```

Trong snippet này, `a` và `b` được giả định có kiểu `CompletableFuture<Integer>`. Fallback 0 chỉ là ví dụ cơ chế, **không phải khuyến nghị xử lý tiền**.

**Không giả định fail-fast tự động:** khi một nguồn lỗi và nguồn khác vẫn đang chạy, không mặc định source kia bị cancel hoặc dependent stage lập tức kết thúc theo đúng mốc bạn dự đoán. Quản lý timeout/cancellation/tài nguyên riêng. `join()` có thể ném `CompletionException` (hoặc `CancellationException` cho cancellation); `get()` có checked `InterruptedException`/`ExecutionException`. Cả `join` và `get` đều blocking. Các tiện ích timeout như `orTimeout` có trên JDK sau Java 8, nên code tương thích Java 8 không dùng chúng.

## 11. So sánh với thenCompose, allOf và nhóm either

| API | Ý nghĩa |
| --- | --- |
| `thenApply` | Biến đổi một giá trị đã có |
| `thenCompose` | Kết quả A mới tạo ra một stage B phụ thuộc A |
| `thenCombine` | Ghép hai source độc lập để tạo giá trị |
| `thenAcceptBoth` | Tiêu thụ dữ liệu từ hai source |
| `runAfterBoth` | Chạy khi hai source thành công, không đọc dữ liệu |
| `CompletableFuture.allOf` | Đợi nhiều future, **không tự gộp dữ liệu** |
| `applyToEither` / `acceptEither` / `runAfterEither` | Chạy khi **một trong hai** nguồn hoàn thành bình thường |

`thenCompose` phù hợp nếu B cần ID từ A:

```java
CompletableFuture<String> id =
        CompletableFuture.completedFuture("U42");
CompletableFuture<String> profile = id.thenCompose(x ->
        CompletableFuture.completedFuture("profile-for-" + x));
```

`allOf` trả `CompletableFuture<Void>`, không trả tuple hay list kết quả:

```java
CompletableFuture<Integer> x =
        CompletableFuture.completedFuture(120);
CompletableFuture<Integer> y =
        CompletableFuture.completedFuture(30);
CompletableFuture.allOf(x, y).join();
int total = x.join() + y.join(); // 150.
```

Với **hai** giá trị cần tổng hợp thành một, `thenCombine` diễn đạt trực tiếp hơn. Với nhiều tác vụ mà cần một barrier hoàn thành, `allOf` hợp lý hơn. Nếu chỉ cần một source thành công sớm, chọn nhóm *either*, không chọn nhóm *both*.

## 12. Chương trình Java 8 đầy đủ

Tạo file **`CombineStagesDemo.java`**. Chương trình thực hiện cả bản thường/Async, kiểm tra một source hoàn thành trước, và xác nhận không action nào trong bộ ba chạy khi source lỗi. Callback chỉ cập nhật biến atomic; các dòng output được in **sau khi join** nên không phụ thuộc thứ tự scheduling.

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class CombineStagesDemo {
    public static void main(String[] args) {
        ExecutorService executor = Executors.newFixedThreadPool(3);
        try {
            CompletableFuture<Integer> subtotal =
                    CompletableFuture.supplyAsync(() -> 120, executor);
            CompletableFuture<Integer> shipping =
                    CompletableFuture.supplyAsync(() -> 30, executor);

            CompletableFuture<Integer> total = subtotal.thenCombine(
                    shipping, (a, b) -> a + b);

            AtomicReference<String> note = new AtomicReference<>();
            CompletableFuture<Void> accepted = subtotal.thenAcceptBoth(
                    shipping, (a, b) -> note.set("subtotal=" + a + ", shipping=" + b));

            AtomicInteger signalCount = new AtomicInteger();
            CompletableFuture<Void> signaled = subtotal.runAfterBoth(
                    shipping, signalCount::incrementAndGet);

            CompletableFuture<String> asyncTotal =
                    subtotal.thenCombineAsync(shipping,
                            (a, b) -> "sum=" + (a + b), executor);

            AtomicReference<String> asyncNote = new AtomicReference<>();
            CompletableFuture<Void> asyncAccepted =
                    subtotal.thenAcceptBothAsync(shipping,
                            (a, b) -> asyncNote.set(a + "+" + b), executor);

            AtomicInteger asyncCount = new AtomicInteger();
            CompletableFuture<Void> asyncSignaled =
                    subtotal.runAfterBothAsync(shipping,
                            asyncCount::incrementAndGet, executor);

            CompletableFuture.allOf(total, accepted, signaled,
                    asyncTotal, asyncAccepted, asyncSignaled).join();

            System.out.println("thenCombine: " + total.join());
            System.out.println("thenAcceptBoth: " + note.get()
                    + " | result=" + accepted.join());
            System.out.println("runAfterBoth: " + signalCount.get()
                    + " | result=" + signaled.join());
            System.out.println("thenCombineAsync: " + asyncTotal.join());
            System.out.println("thenAcceptBothAsync: " + asyncNote.get());
            System.out.println("runAfterBothAsync: " + asyncCount.get());

            CompletableFuture<String> first = new CompletableFuture<>();
            CompletableFuture<String> second = new CompletableFuture<>();
            AtomicInteger combineCalls = new AtomicInteger();
            CompletableFuture<String> combined = first.thenCombine(
                    second, (x, y) -> {
                        combineCalls.incrementAndGet();
                        return x + "/" + y;
                    });
            first.complete("A");
            boolean beforeSecond = combined.isDone();
            second.complete("B");
            System.out.println("After only first completed: " + beforeSecond);
            System.out.println("After both completed: " + combined.join()
                    + " | calls=" + combineCalls.get());

            CompletableFuture<Integer> broken = new CompletableFuture<>();
            CompletableFuture<Integer> ok = CompletableFuture.completedFuture(7);
            AtomicBoolean mergeRan = new AtomicBoolean();
            AtomicBoolean acceptRan = new AtomicBoolean();
            AtomicBoolean runRan = new AtomicBoolean();
            CompletableFuture<Integer> failedMerge = broken.thenCombine(
                    ok, (a, b) -> {
                        mergeRan.set(true);
                        return a + b;
                    });
            CompletableFuture<Void> failedAccept = broken.thenAcceptBoth(
                    ok, (a, b) -> acceptRan.set(true));
            CompletableFuture<Void> failedRun = broken.runAfterBoth(
                    ok, () -> runRan.set(true));

            broken.completeExceptionally(new IllegalStateException("source failed"));
            int recovered = failedMerge.exceptionally(ex -> -1).join();
            String failureType;
            try {
                failedMerge.join();
                failureType = "none";
            } catch (CompletionException ex) {
                failureType = ex.getCause().getClass().getSimpleName();
            }
            boolean allFailed = failedMerge.isCompletedExceptionally()
                    && failedAccept.isCompletedExceptionally()
                    && failedRun.isCompletedExceptionally();

            System.out.println("Failed combined fallback: " + recovered);
            System.out.println("Failure cause: " + failureType);
            System.out.println("Both-dependent actions ran on failure: "
                    + mergeRan.get() + "/" + acceptRan.get() + "/" + runRan.get());
            System.out.println("All dependents exceptional: " + allFailed);

            if (total.join() != 150
                    || !note.get().equals("subtotal=120, shipping=30")
                    || accepted.join() != null
                    || signaled.join() != null
                    || signalCount.get() != 1
                    || !asyncTotal.join().equals("sum=150")
                    || !asyncNote.get().equals("120+30")
                    || asyncCount.get() != 1
                    || beforeSecond
                    || !combined.join().equals("A/B")
                    || combineCalls.get() != 1
                    || recovered != -1
                    || !failureType.equals("IllegalStateException")
                    || mergeRan.get() || acceptRan.get() || runRan.get()
                    || !allFailed) {
                throw new AssertionError("Combine stages demo mismatch");
            }
            System.out.println("Checks passed.");
        } finally {
            executor.shutdown();
        }
    }
}
```

Biên dịch trên JDK 17+ với chế độ API Java 8 (hoặc `javac` của JDK 8):

```bash
javac --release 8 CombineStagesDemo.java
java CombineStagesDemo
```

**Stdout đã chạy và kiểm thử bằng OpenJDK 24:**

```text
thenCombine: 150
thenAcceptBoth: subtotal=120, shipping=30 | result=null
runAfterBoth: 1 | result=null
thenCombineAsync: sum=150
thenAcceptBothAsync: 120+30
runAfterBothAsync: 1
After only first completed: false
After both completed: A/B | calls=1
Failed combined fallback: -1
Failure cause: IllegalStateException
Both-dependent actions ran on failure: false/false/false
All dependents exceptional: true
Checks passed.
```

Ý nghĩa: `thenCombine` trả tổng 150, `thenAcceptBoth` ghi audit nhưng kết quả stage `Void` là null, `runAfterBoth` tăng counter nhưng cũng trả Void. Bản Async dùng executor chỉ định. Tạo hai future thủ công chứng minh khi mới hoàn thành future đầu, dependent chưa done. Khi một source thất bại, cả ba action không được gọi và stage phụ thuộc hoàn thành bất thường; `exceptionally` cung cấp fallback -1. Pool được shutdown trong `finally`.

## 13. Lỗi phổ biến

| Sai lầm | Vấn đề | Cách xử lý |
| --- | --- | --- |
| Nghĩ `thenCombine` khởi chạy hai source | Chỉ đăng ký phụ thuộc | Tạo/hoàn tất nguồn riêng |
| Nghĩ một source xong là callback chạy | Phải đủ **cả hai nguồn thành công** | Test completion từng nguồn |
| Dùng `thenAcceptBoth` rồi chờ giá trị ở `join` | Stage là `Void` | Dùng `thenCombine` nếu cần dữ liệu |
| Dùng `runAfterBoth` như finally | Không chạy khi source lỗi | `whenComplete`/`handle` hoặc finally đúng phạm vi |
| Đăng ký ba nhánh rồi giả định callback chạy theo thứ tự | Không có guarantee thứ tự | Nối stage tuần tự |
| Coi non-Async chạy chắc chắn trên thread main | Có thể chạy ở thread hoàn thành source | Không phụ thuộc thread name |
| Coi Async luôn dùng thread riêng | Phụ thuộc executor | Chọn pool theo workload |
| Blocking `join` sâu trong executor nhỏ | Dễ starvation hoặc deadlock | Dùng composition, chờ ở ranh giới |
| Lỗi nguồn tự hủy tác vụ còn lại | Không được bảo đảm | Thiết kế cancellation/lifecycle |
| Dùng 0 làm fallback tiền khi một API thất bại | Làm sai tiền | Policy recover được chấp thuận |
| Callback ghi DB/gửi event mà không idempotency | Có thể trùng khi retry workflow | Kiểm soát side effect |
| Quên shutdown ExecutorService | Rò thread/tài nguyên | Quản lý vòng đời executor |
| Coi `allOf` trả danh sách kết quả | Trả stage `Void` | Ghép/lấy result cụ thể |

## 14. Bài tập có đáp án

**1.** Ghép future 8 và 5 thành 13? — `a.thenCombine(b,Integer::sum)`.

**2.** Có future tên và future tuổi, cần chuỗi giới thiệu? — `name.thenCombine(age,(n,a)->n+" "+a)`.

**3.** Cần audit hai giá trị nhưng không trả kết quả? — `thenAcceptBoth`, trả `CompletableFuture<Void>`.

**4.** Cần báo “hai bước hoàn tất” không đọc dữ liệu? — `runAfterBoth`, nhưng chỉ khi cả hai thành công.

**5.** A thành công, B lỗi, `runAfterBoth` có chạy? — Không.

**6.** A xong trước và B chưa xong, `thenCombine` có hoàn tất? — Chưa.

**7.** Muốn callback dùng executor riêng? — Bản `thenCombineAsync(other,fn,executor)` và biến thể Async tương ứng.

**8.** B cần ID do A tạo rồi mới gọi API? — `thenCompose`, không phải hai nguồn độc lập của `thenCombine`.

**9.** Có 10 future muốn đợi tất cả nhưng không cần gộp giá trị? — `CompletableFuture.allOf(...)`.

**10.** `CompletableFuture<Void>.join()` trả null có lỗi không? — Không, đó là kết quả thành công bình thường của stage Void.

## 15. Tài liệu chuẩn còn áp dụng

- [Oracle Java SE 27 — CompletionStage](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/CompletionStage.html): chữ ký chính xác, cả hai hoàn thành bình thường, biến thể Async, happens-before và quan hệ both/either.
- [Oracle Java SE 27 — CompletableFuture](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `supplyAsync`, `join`, `allOf`, exception và thực thi callback.
- [Oracle Java SE 27 — Executor](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Executor.html) và [ExecutorService](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ExecutorService.html): nơi chạy action và quản lý thread pool.
- [Oracle Java SE 8 — CompletionStage](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/CompletionStage.html): đối chiếu API từ Java 8.

**Kết luận:** Khi **cả hai nguồn thành công**, dùng `thenCombine` để tạo kết quả, `thenAcceptBoth` để dùng hai kết quả trong side effect, và `runAfterBoth` khi chỉ cần sự kiện cả hai xong. Cả ba **không chạy action khi nguồn lỗi**, không tự bảo đảm thứ tự callback, cancellation hay chạy song song; cần kết hợp Executor, recovery và thiết kế phụ thuộc đúng yêu cầu.
