# Callback không có hậu tố Async có thể chạy trên luồng hoàn tất hoặc luồng gọi — CompletableFuture Java

> **Phạm vi:** Java SE 17, phần **CompletableFuture** của Java concurrency nói chung. Bài giải thích một quy tắc rất dễ bỏ sót: các dependent callbacks như `thenApply`, `thenAccept`, `thenRun`, `whenComplete`, `handle` và `thenCompose` **không có hậu tố Async** không sở hữu một executor riêng, và có thể được thực thi trên **thread đang làm hoàn tất stage nguồn** hoặc **thread đang gọi/đăng ký completion khi nguồn đã hoàn tất**. Phần concurrency liên quan Spring thuộc chương riêng, không sử dụng các API Spring trong bài này.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **dependent stage** và **completion action** trong `CompletableFuture`.
2. Phân biệt **asynchronous computation** với **asynchronous callback dispatch**: một nguồn được tạo bằng `supplyAsync` không làm mọi callback `thenApply` trở thành `thenApplyAsync`.
3. Giải thích vì sao callback không `Async` có thể chạy trên thread gọi `complete` khi nó đăng ký từ trước, hoặc thread gọi `thenApply` khi nguồn đã complete.
4. Nắm đúng giới hạn của JavaDoc: đó là **chính sách cho phép nhiều thread tham gia thực thi**, không phải contract “luôn chạy ở completer” hay “luôn chạy ở caller”.
5. So sánh `thenApply`/`thenApplyAsync`, `thenAccept`/`thenAcceptAsync`, `thenCompose`/`thenComposeAsync` và `whenComplete`/`whenCompleteAsync`.
6. Hiểu ý nghĩa của `Async` không có executor (default asynchronous execution facility) và `Async(..., Executor)` có executor tường minh.
7. Nhận diện nguy cơ **block completion thread**, làm tăng latency, starvation/deadlock khi callback có blocking I/O hoặc `join()`.
8. Hiểu callback failure khác source failure, propagation qua dependent futures và cách quan sát exception.
9. Thiết kế callback gọn, không block, không đặt side effect nguy hiểm vào thread không xác định; truyền context có chủ đích thay vì kỳ vọng `ThreadLocal` tự truyền.
10. Biên dịch và chạy Java 17 để quan sát ba thread thực thi khác nhau trong những tình huống được kiểm soát, không phỏng đoán bằng `Thread.sleep`.
11. Phân biệt thứ tự completion với thứ tự callback, trách nhiệm shutdown executor và các bảo đảm Java Memory Model liên quan.
12. Viết tests theo **invariant về kết quả** thay vì assert rằng callback không `Async` luôn có một thread name cố định trong production.

**Quy tắc ghi nhớ:** *không có hậu tố `Async`* nghĩa là callback **không được yêu cầu dispatch bất đồng bộ qua một executor**. Nó có thể thực thi ngay trên thread tham gia quá trình hoàn tất, kể cả thread gọi API khi nguồn đã sẵn kết quả. *Có hậu tố `Async`* nghĩa callback được dispatch qua default execution facility hoặc executor được chỉ định; không có nghĩa mọi stage của pipeline chạy trên một thread riêng mới tạo.

## 2. Vì sao chủ đề này quan trọng?

Một ứng dụng tạo một future để nhận kết quả từ network hoặc từ pool. Sau đó code viết:

```java
CompletableFuture<Response> result =
        requestFuture.thenApply(this::parseAndValidate);
```

Đây là snippet trong một method; `Response`, `requestFuture` và `parseAndValidate` do ứng dụng định nghĩa.

Người mới học đôi khi nghĩ `parseAndValidate` luôn chạy trong “background pool” vì `requestFuture` là async. Nhưng **đó không phải điều `thenApply` hứa**:

- Nếu `requestFuture` **chưa hoàn tất** khi bạn đăng ký, callback có thể được thực thi ngay khi một thread hoàn tất source, kể cả thread xử lý I/O callback.
- Nếu `requestFuture` **đã hoàn tất** trước khi gọi `thenApply`, lời đăng ký có thể thực thi function ngay **trên chính thread đang gọi `thenApply`**.
- Nếu các dependent completions đan xen hoặc nhiều threads cùng tham gia completion, việc thực thi có thể nằm ở một thread tham gia completion khác theo chính sách JavaDoc.
- Nếu function chậm, thread vô tình thực thi nó có thể bị giữ lại lâu, dù function không hề dùng `synchronized`.

Hệ quả: chỉ nhìn code `thenApply(...)` không đủ để kết luận “callback luôn ở thread nào”. Phải hiểu **thời điểm source complete**, **thời điểm đăng ký callback** và **execution policy**.

## 3. Từ Future đến CompletionStage

Một `CompletableFuture<T>` vừa là một `Future<T>` có thể chờ/nhận kết quả, vừa thực hiện interface `CompletionStage<T>` cho phép khai báo các hành động phụ thuộc.

Ví dụ:

```java
CompletableFuture<String> source = new CompletableFuture<>();
CompletableFuture<Integer> length =
        source.thenApply(String::length);
CompletableFuture<String> message =
        length.thenApply(n -> "length=" + n);
source.complete("hello");
System.out.println(message.join()); // length=5
```

Đoạn code trong method; cần import `java.util.concurrent.CompletableFuture`.

- `source` là nguồn `CompletableFuture<String>`.
- `length` là dependent stage biến đổi String → Integer.
- `message` tiếp tục biến đổi Integer → String.
- `source.complete("hello")` đánh dấu nguồn hoàn tất bình thường.
- Khi dependent actions hoàn tất, `message.join()` trả chuỗi mong đợi.

Ở đây không có phương thức nào có chữ `Async`. Pipeline **không tự yêu cầu executor mới** cho các biến đổi. Có thể các callback chạy ngay khi `source.complete` được gọi. Với nguồn đã complete, chúng có thể chạy ngay khi stage mới được tạo.

### Completion khác execution

Một future là **đại diện cho trạng thái outcome**, không nhất thiết là chính thread/task nền:

- `new CompletableFuture<>()` tạo một future chưa hoàn tất, **không khởi chạy thread**.
- `complete(value)` đặt outcome của future nếu nó chưa complete, có thể kích hoạt dependent actions.
- `supplyAsync(supplier, executor)` tạo/gửi một computation bất đồng bộ đến executor.
- `thenApply(fn)` tạo dependent stage, **không yêu cầu** một background task mới cho function.
- `thenApplyAsync(fn, executor)` tạo dependent stage và yêu cầu callback execution qua executor đã chỉ định khi dependency sẵn sàng.

Sự khác biệt giữa “đã có asynchronous source” và “dependent callback cũng được dispatch asynchronous” là trục kiến thức của bài.

## 4. Chính sách thực thi theo Java SE 17

JavaDoc `CompletableFuture` mô tả chính sách cho các dependent completions **không có phương thức `Async`**: các actions này *may be performed by the thread that completes the current CompletableFuture, or by any other caller of a completion method*. Nói cách khác, Java **cho phép** thread đang complete hoặc một caller tham gia completion chạy callback.

Điều cần rút ra:

1. Không mặc định callback chạy trên thread đã **tạo CompletableFuture**.
2. Không mặc định callback chạy trên thread đã **đăng ký callback**.
3. Không mặc định callback chạy trên **ForkJoinPool.commonPool()`** nếu bạn không gọi phương thức `Async`.
4. Không mặc định callback chạy trên **cùng một thread cho mọi execution**.
5. Không dùng thread name như ràng buộc nghiệp vụ, trừ khi bạn chủ động đưa callback qua executor có contract phù hợp.
6. Một callback có thể được thực thi **inline** trong lời `complete` hoặc trong lời đăng ký callback trên source đã complete. Vì vậy đường gọi ban đầu có thể mất thời gian xử lý callback.
7. Phải xem **thread safety và latency** của callback giống mọi code có thể chạy trong một thread do người khác sở hữu.

JavaDoc nói **may** (có thể), không nói **must always** (bắt buộc luôn). Đó là lý do ví dụ dưới đây minh họa hành vi **đã kiểm thử trên Java 17**, còn quyết định production phải dựa trên execution policy thay vì dựa vào một timing duy nhất.

## 5. Trường hợp A: đăng ký trước, source complete sau

```java
CompletableFuture<String> pending = new CompletableFuture<>();

CompletableFuture<String> observed = pending.thenApply(
        text -> Thread.currentThread().getName() + ":" + text);

Thread completer = new Thread(
        () -> pending.complete("ready"), "completer-thread");
completer.start();
completer.join();
System.out.println(observed.join());
```

Đây là snippet trong một method có thể `throws InterruptedException`; cần import `CompletableFuture`.

- Callback `thenApply` được đăng ký khi `pending` chưa done.
- Thread `completer-thread` gọi `pending.complete("ready")`.
- Trong đường thực thi thông dụng của JDK 17, completion thread chạy callback không `Async` để hoàn tất `observed`.
- `completer.join()` chờ thread completer kết thúc; `observed.join()` chờ dependent stage done.
- Nếu chạy theo JDK 17 và thứ tự trên, output thường là `completer-thread:ready`, như ví dụ đầy đủ đã kiểm thử.

**Không biến đây thành khẳng định mọi callback không Async trong mọi hoàn cảnh đều do chính thread gọi `complete` thực hiện.** Có thể có những callers/threads khác tham gia completion, đặc biệt trong pipeline có nhiều dependencies và races.

## 6. Trường hợp B: nguồn đã complete trước khi đăng ký

```java
CompletableFuture<String> ready =
        CompletableFuture.completedFuture("ready");

CompletableFuture<String> observed = ready.thenApply(
        text -> Thread.currentThread().getName() + ":" + text);

System.out.println(observed.join());
```

Đây là snippet trong method. `ready` đã hoàn tất bình thường **trước** khi `thenApply` được gọi. Trong triển khai Java 17 bình thường, function chạy **ngay trên thread gọi `thenApply`** để tạo dependent outcome, thay vì được gửi sang một worker tự động.

Nếu code ở `main`, kết quả thường là `main:ready`. Nếu code đang xử lý một event-loop callback, thread gọi `thenApply` có thể chính là event-loop thread, và function có thể chạy ngay ở đó.

### Tại sao việc này làm nhiều người bất ngờ?

Bạn có thể có một API trả `CompletableFuture` nhưng đôi khi trả kết quả cache đã sẵn, đôi khi cần network:

- **Cache hit:** Future đã complete. `thenApply` có thể thực thi ngay trên thread xử lý request.
- **Cache miss:** Future chưa complete. `thenApply` có thể thực thi trên thread hoàn tất I/O về sau.

**Cùng một dòng source code** có thể tạo callback chạy ở hai loại thread khác nhau tùy data path. Nếu callback phụ thuộc vào thread affinity hoặc làm blocking I/O, sự khác biệt đó tạo bug khó tái hiện.

## 7. Trường hợp C: chọn executor tường minh bằng thenApplyAsync

```java
ExecutorService callbackPool =
        Executors.newSingleThreadExecutor(
                r -> new Thread(r, "callback-worker"));

try {
    CompletableFuture<String> ready =
            CompletableFuture.completedFuture("hello");

    CompletableFuture<String> processed =
            ready.thenApplyAsync(
                    text -> Thread.currentThread().getName()
                            + ":" + text.toUpperCase(),
                    callbackPool);

    System.out.println(processed.join());
} finally {
    callbackPool.shutdown();
}
```

Đây là snippet trong method, cần imports `CompletableFuture`, `ExecutorService`, `Executors`. Nếu dùng production, cần shutdown/awaitTermination và chính sách giới hạn queue/task duration.

Với executor có một worker được đặt tên `callback-worker`, output trong đường chạy bình thường là `callback-worker:HELLO`. **Nguồn đã complete** không làm function được chạy trực tiếp trên thread gọi `thenApplyAsync`; callback được dispatch qua `callbackPool` theo API.

### Async khác thread mới

`Async` không có nghĩa “tạo một Thread mới cho mỗi callback”. Với executor một worker, nhiều callbacks dùng chung worker ấy. Với `ForkJoinPool.commonPool()`, callbacks có thể sử dụng các common-pool workers khác nhau. Với executor tự tạo, tài nguyên/thread scheduling phụ thuộc cấu hình của executor.

### Executor rejection

Nếu executor đã shutdown hoặc từ chối task, dependent stage có thể hoàn tất bất thường với exception liên quan rejection. `thenApplyAsync` không bảo đảm callback luôn chạy thành công. Phải xác định ownership của executor, lifecycle và policy khi không còn capacity.

## 8. Ví dụ Java 17 đầy đủ đã biên dịch và chạy

Chương trình này minh họa **ba execution contexts** và tách lỗi của callback khỏi trạng thái nguồn:

1. Đăng ký `thenApply` khi nguồn chưa complete; một thread đặt tên `completer-thread` hoàn tất nguồn.
2. Đăng ký `thenApply` trên một nguồn đã complete; callback chạy trong thread `main` của ví dụ Java 17.
3. Đăng ký `thenApplyAsync` với executor tên `callback-worker`.
4. Một callback cố tình ném `IllegalArgumentException`; dependent failed nhưng nguồn vẫn bình thường.

Tạo file **`NonAsyncThreadDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class NonAsyncThreadDemo {
    public static void main(String[] args) throws Exception {
        CompletableFuture<String> pending = new CompletableFuture<>();
        CompletableFuture<String> earlyRegistration = pending.thenApply(
                s -> Thread.currentThread().getName() + ":" + s.toUpperCase());
        Thread completer = new Thread(() -> pending.complete("alpha"), "completer-thread");
        completer.start();
        completer.join();
        System.out.println("registeredBefore=" + earlyRegistration.join());

        CompletableFuture<String> ready = CompletableFuture.completedFuture("beta");
        CompletableFuture<String> lateRegistration = ready.thenApply(
                s -> Thread.currentThread().getName() + ":" + s.toUpperCase());
        System.out.println("registeredAfter=" + lateRegistration.join());

        ExecutorService callbackPool = Executors.newSingleThreadExecutor(
                task -> new Thread(task, "callback-worker"));
        try {
            CompletableFuture<String> explicitAsync = ready.thenApplyAsync(
                    s -> Thread.currentThread().getName() + ":" + s.toUpperCase(),
                    callbackPool);
            System.out.println("explicitAsync=" + explicitAsync.join());
        } finally {
            callbackPool.shutdown();
            if (!callbackPool.awaitTermination(5, TimeUnit.SECONDS)) {
                callbackPool.shutdownNow();
                throw new IllegalStateException("callback pool failed to stop");
            }
        }

        CompletableFuture<String> normalSource = CompletableFuture.completedFuture("bad");
        CompletableFuture<String> failed = normalSource.thenApply(s -> {
            throw new IllegalArgumentException("invalid value");
        });
        try {
            failed.join();
        } catch (CompletionException e) {
            System.out.println("callbackFailure=" + e.getCause().getClass().getSimpleName());
        }
        System.out.println("sourceStillNormal=" + !normalSource.isCompletedExceptionally());
    }
}
```

**Lệnh biên dịch và chạy trên JDK 17:**

```bash
javac --release 17 NonAsyncThreadDemo.java
java NonAsyncThreadDemo
```

**Stdout chính xác đã được kiểm thử:**

```text
registeredBefore=completer-thread:ALPHA
registeredAfter=main:BETA
explicitAsync=callback-worker:BETA
callbackFailure=IllegalArgumentException
sourceStillNormal=true
```

### Giải thích dòng 1

`earlyRegistration` được tạo khi `pending` chưa hoàn tất. Thread tên `completer-thread` gọi `pending.complete("alpha")` và JDK 17 trong ví dụ chạy callback `thenApply` trên thread đó. `Thread.currentThread().getName()` cho `completer-thread`, `alpha.toUpperCase()` cho `ALPHA`.

### Giải thích dòng 2

`ready` được tạo bằng `completedFuture("beta")` nên đã done trước khi main gọi `thenApply`. Trong execution thực nghiệm, function chạy ngay trên `main`, cho `main:BETA`.

### Giải thích dòng 3

`thenApplyAsync` nhận explicit executor `callbackPool`. ThreadFactory gắn tên `callback-worker`, nên callback chạy ở đó; main gọi `join()` chỉ để chờ dependent completion, không phải thực thi callback.

### Giải thích dòng 4–5

`normalSource` có outcome bình thường `"bad"`. Function của `failed` được gọi rồi ném `IllegalArgumentException`. Dependent `failed.join()` ném `CompletionException` chứa cause đó. Nhưng `normalSource` vẫn completed normally; vì vậy `sourceStillNormal=true`.

**Một lỗi phổ biến:** hiểu rằng “callback failed” làm future nguồn đã thành công cũng failed. Outcome của mỗi stage là độc lập. Dependent stage có thể failed do logic của chính callback, còn upstream vẫn có kết quả bình thường.

### Tính ổn định của kết quả mẫu

Mẫu chủ động điều khiển thứ tự bằng `start/join` và `completedFuture`, đồng thời đặt tên thread của completer/executor để quan sát. Kết quả trên đã được kiểm thử với Java 17. Trong ứng dụng production, **đừng assert thread name cố định cho callbacks không `Async`**; execution policy cho phép nhiều caller cùng tham gia completion và pipeline phức tạp có thể khác mẫu nhỏ.

## 9. Bảng so sánh các loại dependent callbacks

| Phương thức | Callback | Kiểu dependent | Có yêu cầu Async dispatch? |
|---|---|---|---|
| `thenApply(fn)` | `Function<T,U>` | `CompletableFuture<U>` | Không |
| `thenApplyAsync(fn)` | `Function<T,U>` | `CompletableFuture<U>` | Có, default facility |
| `thenApplyAsync(fn, executor)` | `Function<T,U>` | `CompletableFuture<U>` | Có, executor chỉ định |
| `thenAccept(action)` | `Consumer<T>` | `CompletableFuture<Void>` | Không |
| `thenAcceptAsync(action, executor)` | `Consumer<T>` | `CompletableFuture<Void>` | Có |
| `thenRun(action)` | `Runnable` | `CompletableFuture<Void>` | Không |
| `thenRunAsync(action, executor)` | `Runnable` | `CompletableFuture<Void>` | Có |
| `thenCompose(fn)` | `Function<T,CompletionStage<U>>` | `CompletableFuture<U>` | Không |
| `thenComposeAsync(fn, executor)` | `Function<T,CompletionStage<U>>` | `CompletableFuture<U>` | Có |
| `whenComplete(action)` | `BiConsumer<T,Throwable>` | `CompletableFuture<T>` | Không |
| `whenCompleteAsync(action, executor)` | `BiConsumer<T,Throwable>` | `CompletableFuture<T>` | Có |
| `handle(fn)` | `BiFunction<T,Throwable,U>` | `CompletableFuture<U>` | Không |
| `handleAsync(fn, executor)` | `BiFunction<T,Throwable,U>` | `CompletableFuture<U>` | Có |

**Hậu tố `Async` được áp dụng cho **callback của stage tương ứng**, không bảo đảm mọi stage upstream/downstream trong cả chuỗi cũng được dispatch theo cách ấy. Mỗi stage có execution policy của riêng nó.

### Callback không Async trên `thenCompose`

`thenCompose` nhận function trả một stage khác và **flatten** kết quả. Function có thể chạy inline theo chính sách không Async, còn stage mà function trả về có thể complete vào thời điểm/ở thread hoàn toàn khác. Vì thế `thenCompose` không biến toàn bộ I/O bên trong future mới thành synchronous, cũng không bảo đảm function chạy trong background thread.

## 10. Một source đã Async không kéo các callback chạy Async theo

Đoạn code:

```java
ExecutorService ioExecutor = Executors.newFixedThreadPool(4);
CompletableFuture<Payload> fetched =
        CompletableFuture.supplyAsync(() -> fetchRemote(), ioExecutor);

CompletableFuture<View> mapped =
        fetched.thenApply(this::toView);
```

Đây là đoạn minh họa trong method; `Payload`, `View`, `fetchRemote`, `toView` do ứng dụng định nghĩa. Với `fetched` chưa complete lúc đăng ký, `toView` có thể chạy trên worker hoàn tất supplier trong `ioExecutor`. Nếu fetched đã completed rồi, `toView` có thể chạy ngay trên thread đang đăng ký callback.

**`supplyAsync` tạo asynchronous source; `thenApply` là non-Async dependent.** Không có quy tắc “tất cả stage sau supplyAsync đều dùng ioExecutor”. Muốn callback được dispatch qua executor do bạn chọn, viết:

```java
CompletableFuture<View> mapped =
        fetched.thenApplyAsync(this::toView, mappingExecutor);
```

Đoạn code minh họa, `mappingExecutor` do ứng dụng tạo và sở hữu. Hãy phân biệt pool làm I/O, pool xử lý CPU, pool của event-loop và nơi continuation chạy.

## 11. Callback trên source đã hoàn tất có thể chạy ngay trong lời đăng ký

Nếu `source` là already-completed, đoạn:

```java
long start = System.nanoTime();
CompletableFuture<String> result =
        source.thenApply(this::expensiveTransformation);
long spentNanos = System.nanoTime() - start;
```

là đoạn code minh họa; `source` và `expensiveTransformation` do ứng dụng định nghĩa.

`spentNanos` có thể bao gồm gần như toàn bộ thời gian transformation vì callback chạy inline. Không được kết luận `thenApply` là một method “chỉ đăng ký không bao giờ chạy việc”. Đây là chỗ hay gây latency bất ngờ trong HTTP request thread hoặc UI event-loop.

Nếu source hoàn tất qua cache hit, `thenApply` nặng có thể chiếm ngay caller; nếu cache miss, cùng function lại chiếm completion thread. Một lỗi performance có thể biểu hiện không ổn định theo cache hit ratio.

**Thiết kế đúng:** nếu transformation nặng/đòi thread affinity, dùng `thenApplyAsync(..., properExecutor)` thay vì trông chờ source chưa complete.

## 12. Callback trên completer thread có thể làm chậm lời complete()

Xét mã:

```java
CompletableFuture<Integer> pending = new CompletableFuture<>();
pending.thenApply(value -> {
    heavyCpuTask(value);
    return value + 1;
});
pending.complete(10);
```

Đây là snippet trong method, `heavyCpuTask` được định nghĩa. Vì action không `Async` có thể thực thi ngay trong thread đang gọi `pending.complete`, lời `complete(10)` có thể phải thực thi thêm `heavyCpuTask` trước khi trả trong các execution tương ứng.

Điều này ảnh hưởng:

- **Latency:** thread phát sự kiện completion bị giữ lâu.
- **Throughput:** một I/O completion thread có thể mất thời gian làm CPU computation của callback.
- **Fairness:** một source có nhiều dependent callbacks nặng có thể làm thread tham gia completion xử lý một chuỗi dài.
- **Backpressure:** nếu completion thread còn phải nhận thêm events, queue dồn lại.
- **Thread affinity:** callback có thể chạy ở thread không phù hợp cho blocking hoặc UI operations.

Không cần một “thread mới” để có bất đồng bộ ở stage nguồn; nhưng việc lựa chọn *nơi callback chạy* phải được thiết kế tách biệt.

## 13. Dùng Async khi nào và không dùng khi nào?

### Thường phù hợp với non-Async

- Chuyển đổi rất nhanh, thuần túy: `String::trim`, convert enum, lấy một field từ immutable object.
- Mapping/validation nhẹ, không blocking I/O, không giữ lock lớn.
- Hoạt động không cần thread affinity.
- Chấp nhận callback chạy inline/caller/completer vì thời gian thực thi nhỏ và có thể dự đoán.
- Ưu tiên giảm overhead queue/dispatch khi workloads rất nhỏ.

### Thường phù hợp với Async và executor tường minh

- CPU-heavy mapping cần phân bổ qua compute pool.
- Blocking I/O hoặc thao tác có latency cao, được phân bổ sang pool phù hợp.
- Gửi log/metrics/tác vụ phụ mà không muốn chặn source completion thread.
- Code cần chạy trên một event loop/GUI thread chuyên biệt do executor đại diện.
- Tách bạch các phần có tài nguyên và SLA khác nhau.
- Muốn kiểm soát queue capacity, rejection policy, worker names, monitoring, lifecycle.

### Async không tự bảo đảm mọi thứ

`thenApplyAsync` không tự biến một callback không thread-safe thành thread-safe, không tạo transaction trên external state, không tự ngăn execution cạnh tranh với callbacks khác và không tự giải quyết deadlock khi callback block chờ một task không có worker.

Có một chi phí scheduling/queueing; nếu mỗi transformation chỉ mất vài nanoseconds, dispatch Async riêng có thể tốn nhiều hơn tính toán. Chọn policy dựa trên correctness/latency và đo tải thực tế.

## 14. Default asynchronous execution facility là gì?

Với `CompletableFuture` Java 17, các phương thức `Async` **không nhận Executor** thường sử dụng default asynchronous execution facility, thông thường `ForkJoinPool.commonPool()` khi đáp ứng điều kiện hỗ trợ parallelism theo JavaDoc. Có trường hợp runtime dùng thread mới cho mỗi task nếu common pool không hỗ trợ parallelism đủ mức mà implementation quy định.

Điều quan trọng:

- Đừng hard-code thread name của default Async.
- Không mặc định thread chạy callback là thread đã gọi `thenApplyAsync`.
- Nếu workload blocking nhiều, common pool có thể không phải nơi phù hợp.
- Không tùy tiện shutdown common pool như executor do ứng dụng tự tạo.
- Nếu cần isolation hoặc policy rõ, truyền `Executor` vào overload `Async`.
- Đừng dựa vào “Async luôn tạo thread mới”; common pool thường tái sử dụng workers.

### Ví dụ với explicit executor

```java
ExecutorService computePool = Executors.newFixedThreadPool(4);
CompletableFuture<String> source =
        CompletableFuture.completedFuture("hello");
CompletableFuture<String> mapped =
        source.thenApplyAsync(String::toUpperCase, computePool);
```

Đây là code minh họa trong method, imports `CompletableFuture`, `ExecutorService`, `Executors`. Nên đóng computePool theo owner lifecycle sau khi các tasks hoàn tất; snippet không bao gồm shutdown để tập trung vào execution policy.

## 15. Non-Async callbacks trong pipeline nhiều stage

Xét:

```java
CompletableFuture<String> result = source
        .thenApply(this::parse)
        .thenApply(this::normalize)
        .thenApply(this::render);
```

Đây là đoạn minh họa trong method, cần các methods tương thích.

Nếu `source` chưa done và một thread gọi `source.complete(...)`, nhiều continuation không `Async` có thể chạy trong cùng thread tham gia completion. Điều này là một **khả năng được phép**, không phải bảo đảm cố định cho mọi chuỗi/trạng thái cạnh tranh.

Một callback nặng ở giữa có thể kéo dài đường completion và trì hoãn các callbacks khác. Nếu muốn tách đoạn CPU-intensive:

```java
CompletableFuture<String> result = source
        .thenApply(this::parse)
        .thenApplyAsync(this::normalize, cpuExecutor)
        .thenApply(this::render);
```

Đây là snippet minh họa; `cpuExecutor` do ứng dụng định nghĩa. `normalize` được dispatch tới cpuExecutor. `render` không Async lại có thể chạy trên thread hoàn tất `normalize` hoặc thread khác tham gia completion sau đó, không phải chắc chắn “quay về main”.

**Một stage Async ở giữa không biến các stage kế tiếp thành có executor affinity cố định.** Nếu cần render trên UI thread, tiếp tục dùng `thenApplyAsync(..., uiExecutor)` cho stage render.

## 16. Sibling callbacks không có bảo đảm thứ tự

Nếu đăng ký nhiều callbacks trên một nguồn:

```java
CompletableFuture<String> source = new CompletableFuture<>();
source.thenAccept(v -> log("A:" + v));
source.thenAccept(v -> log("B:" + v));
source.complete("done");
```

Đây là snippet, `log(String)` do ứng dụng định nghĩa. **Không được dùng thứ tự xuất hiện trong source code để suy chắc chắn “A được gọi trước B”**. `CompletableFuture` không cung cấp transaction ordering cho independent sibling continuations theo đúng thứ tự đăng ký mà ứng dụng có thể dựa vào trong mọi hoàn cảnh.

Nếu B phải chạy sau A, tạo dependency rõ:

```java
CompletableFuture<Void> ordered =
        source.thenAccept(v -> log("A:" + v))
              .thenRun(() -> log("B:done"));
```

Đây là code minh họa trong method. `thenRun` stage phụ thuộc completion bình thường của previous stage, vì vậy tạo ordering logic thay vì trông chờ vào thứ tự scheduling giữa siblings.

Đặc biệt, **callback thread identity** và **callback execution order** là hai khía cạnh độc lập: hai actions có thể chạy trên cùng thread mà vẫn không có thứ tự đăng ký được hứa, hoặc trên các threads khác nếu dùng Async.

## 17. thenApply(), thenAccept(), thenRun(): tương đồng và khác biệt

| Method | Callback nhận | Callback trả | Dependent type | Có thể inline khi non-Async? |
|---|---|---|---|---|
| `thenApply(fn)` | Value T | U | `CompletableFuture<U>` | Có |
| `thenAccept(action)` | Value T | void | `CompletableFuture<Void>` | Có |
| `thenRun(action)` | Không nhận value | void | `CompletableFuture<Void>` | Có |

Ví dụ:

```java
CompletableFuture<Integer> number =
        CompletableFuture.completedFuture(10);

CompletableFuture<Integer> doubled =
        number.thenApply(n -> n * 2);
CompletableFuture<Void> recorded =
        doubled.thenAccept(n -> record(n));
CompletableFuture<Void> notified =
        recorded.thenRun(() -> notifyDone());
```

Đây là snippet với `record` và `notifyDone` được định nghĩa. Các callbacks đều không `Async`; vì nguồn đã completed, chúng có thể chạy ngay trong thread đăng ký theo JDK17, không phải mặc định có pool mới.

**Nếu callback phụ có side effect quan trọng**, đừng bỏ qua stage `recorded` hoặc `notified`. Cần join/get/handle exception của dependent tương ứng, vì source `number` thành công không chứng minh thao tác record/notify đã thành công.

## 18. thenCompose() và sự khác biệt giữa “thực thi Function” và “đợi Future con”

`thenCompose` giúp ánh xạ một value sang một `CompletionStage<U>` rồi flatten:

```java
CompletableFuture<User> fetched = lookupUserAsync(userId);

CompletableFuture<Profile> profile =
        fetched.thenCompose(user -> lookupProfileAsync(user.id()));
```

Đây là snippet trong method, với `User`/`Profile`/`lookupUserAsync`/`lookupProfileAsync` do ứng dụng định nghĩa.

Hai vấn đề khác nhau:

- **Function** `user -> lookupProfileAsync(...)` là callback của `thenCompose`. Vì không `Async`, Function này có thể chạy inline trên thread hoàn tất `fetched` hoặc caller.
- **Future con** do `lookupProfileAsync` trả về có thể là computation bất đồng bộ hoàn tất ở thread/time khác. `thenCompose` **không tự chặn chờ** nó như `join`; dependent stage chờ outcome bằng composition.

Nếu function chứa code nặng trước khi trả Future, nó vẫn có thể chặn completer/caller. Nếu function chỉ tạo/gửi một operation async rồi trả ngay, phần nặng có thể nằm ở executor riêng của operation.

`thenComposeAsync(fn, executor)` thay đổi **nơi Function được dispatch**, không áp đặt thread thực thi của mọi thao tác nội bộ do Function tự tạo.

## 19. whenComplete(), handle() và exceptionally(): callback khi có lỗi

Các callbacks `thenApply/thenAccept` thông thường chỉ chạy function khi stage nguồn completed normally. Khi stage nguồn completed exceptionally, dependent thường hoàn tất bất thường mà **không gọi Function trên value không tồn tại**.

Muốn quan sát lỗi, dùng `whenComplete` hoặc `handle`:

```java
CompletableFuture<String> source = new CompletableFuture<>();

CompletableFuture<String> observed = source.whenComplete(
        (value, error) -> {
            if (error != null) {
                recordFailure(error);
            }
        });

CompletableFuture<String> recovered = observed.exceptionally(
        error -> "fallback");
```

Đây là snippet, `recordFailure(Throwable)` do ứng dụng định nghĩa. `whenComplete` là observational action nhận cả value/error, thường giữ outcome trước đó nếu action tự hoàn thành bình thường. `exceptionally` cho phép chuyển failure thành fallback value.

### Execution policy vẫn áp dụng

`whenComplete` không `Async` có thể chạy trên completer/caller tương tự `thenApply`. Nếu logging trong `recordFailure` block vài giây, completion thread có thể bị chiếm dụng. Dùng `whenCompleteAsync(..., loggingExecutor)` nếu cần điều phối riêng, nhưng vẫn phải tránh backlog của executor.

`handle(fn)` chuyển cả success/failure thành một kết quả mới, còn `exceptionally(fn)` chỉ xử lý exceptional completion. Chúng có variants riêng; không đánh đồng với exception handler của `Thread` hay try/catch bao quanh lời đăng ký.

### Callback tự ném exception

Trong demo, source completed normally, `thenApply` ném `IllegalArgumentException` làm dependent failed. Với `whenComplete`, nếu action ném một exception mới, outcome phụ thuộc việc source đã failed hay chưa và contract của `CompletionStage`; đừng coi telemetry callback luôn vô hại. Thiết kế logging/metrics exception-safe để không che failure gốc hoặc làm stage theo dõi failed ngoài ý muốn.

## 20. Exception của source khác exception của dependent

Mô hình:

```text
                 SOURCE CompletableFuture<T>
                       /           \
               completed OK     completed FAIL
                    |                |
                thenApply fn       fn không chạy
                  /    \                |
            fn return  fn throw     dependent FAIL
              |          |
       dependent OK   dependent FAIL
```

Một `CompletableFuture` đã hoàn tất không bị “viết lại trạng thái” chỉ vì dependent action failed. Mỗi stage có state completion riêng.

### Quan sát exception

`join()` trên failed dependent thường ném `CompletionException` với root cause; `get()` ném `ExecutionException` với cause. `CancellationException` có semantics riêng nếu stage bị cancel.

```java
try {
    result.join();
} catch (CompletionException ex) {
    Throwable cause = ex.getCause();
    report(cause);
}
```

Đây là snippet, `result` và `report` đã định nghĩa. Nếu cancellation được phép, nên xử lý riêng `CancellationException`; đừng gộp cancellation vào business failure bất chấp context.

### Source completeExceptionally

`source.completeExceptionally(error)` làm source failed. Nếu `thenApply(fn)` đang phụ thuộc, function không được chạy bình thường với value; dependent nhận exceptional completion. Nhưng nếu dùng `handle`/`whenComplete`, callback chuyên về error có thể được chạy (và vẫn chịu non-Async execution policy).

## 21. Callback không Async và ThreadLocal context

`ThreadLocal` lưu dữ liệu **gắn với thread**, không gắn với logical request hay CompletableFuture. Một pipeline có thể chạy callback ở thread completer hoặc thread đăng ký tùy timing, nên ThreadLocal context không tự truyền đúng.

Ví dụ dễ lỗi:

```java
ThreadLocal<String> traceId = new ThreadLocal<>();
traceId.set("request-123");

CompletableFuture<String> source = new CompletableFuture<>();
CompletableFuture<String> traced =
        source.thenApply(value -> traceId.get() + ":" + value);
```

Đây là snippet trong method. Nếu một thread khác gọi `source.complete("ok")`, callback có thể chạy trên thread đó, nơi `traceId.get()` là `null` hoặc một giá trị của request khác còn sót nếu pooled thread không được cleanup.

**Không sửa bằng cách khẳng định non-Async luôn chạy trong caller.** Chính đặc tính này đang sai.

### Chiến lược tốt hơn

- Truyền context như một immutable value trong data flow, ví dụ `record Contextual<T>(String traceId, T value)`.
- Hoặc capture context ở thời điểm đăng ký rồi wrap callback để set/restore ThreadLocal **trong `try/finally`** khi bắt buộc tích hợp với thư viện dựa trên ThreadLocal.
- Đừng giữ references lớn/credentials trong ThreadLocal lâu hơn thời gian callback.
- Trong thread pool, nhớ cleanup/restore context để tránh rò sang task tiếp theo.
- Async với executor riêng cũng **không tự truyền ThreadLocal**; thread affinity và context propagation là hai vấn đề khác nhau.

Nếu cần đúng một UI/event-loop thread, dùng executor do framework UI cung cấp và không đợi blocking trên event loop đó. Không gắn với Spring-specific context trong bài này.

## 22. Non-Async callbacks và blocking I/O

Phần nguy hiểm nhất khi callbacks không `Async` là hoạt động blocking:

```java
CompletableFuture<String> response = readNetworkAsync();

CompletableFuture<String> audited = response.thenApply(value -> {
    writeAuditToDatabase(value); // Có thể block.
    return value;
});
```

Đây là snippet minh họa; `readNetworkAsync` và `writeAuditToDatabase` cần định nghĩa.

Nếu I/O completion thread gọi `response.complete`, callback có thể **thực thi database I/O ngay trên thread này**. Nếu thread đó còn phải xử lý các network events khác, nó có thể bị nghẽn.

Nếu callback được đăng ký khi source đã complete, chính request thread gọi `thenApply` có thể bị block. Vì vậy latency bug có thể khác nhau giữa cache hit/miss hoặc race timing.

### Một hướng sửa

```java
CompletableFuture<String> audited = response.thenApplyAsync(
        value -> {
            writeAuditToDatabase(value);
            return value;
        },
        auditExecutor);
```

Đây là snippet, `auditExecutor` do ứng dụng sở hữu, cần capacity/queue/timeout riêng và không đặt trên UI thread. Tuy nhiên, chỉ chuyển blocking I/O sang executor **không tự tạo transaction** giữa audit và kết quả source; phải xử lý exception, retry/idempotency nếu cần.

### Không dồn mọi callback vào common pool

Nếu callback có thể block lâu, một executor chuyên cho blocking I/O thường hợp lý hơn default common pool vốn được dùng bởi nhiều computations khác. Nhưng tránh tạo pool không giới hạn gây exhaustion; theo dõi queue depth, task duration, rejections và cleanup.

## 23. Thread starvation deadlock với một worker

Một ví dụ thiết kế có thể deadlock:

```java
ExecutorService oneWorker = Executors.newSingleThreadExecutor();

CompletableFuture<String> outer = CompletableFuture.supplyAsync(() -> {
    CompletableFuture<String> inner =
            CompletableFuture.supplyAsync(() -> "inner", oneWorker);
    return inner.join(); // Chờ task đang queue trên chính oneWorker.
}, oneWorker);
```

Đây là **snippet minh họa nguy hiểm**, không được chạy không timeout trong production. `outer` dùng worker duy nhất. Khi lambda đang chạy, nó enqueue `inner` vào cùng executor rồi `join()`. `inner` không thể bắt đầu vì worker bị chiếm bởi `outer` đang chờ. Đây là **thread-starvation deadlock**.

Trong callback không Async cũng có thể có kiểu vòng phụ thuộc tương tự nếu callback chạy trên worker đang làm complete và chờ một stage cần chính worker ấy.

### Sửa bằng composition, không blocking join

```java
CompletableFuture<String> outer =
        CompletableFuture.completedFuture("start")
                .thenCompose(value ->
                        CompletableFuture.supplyAsync(
                                () -> "inner", oneWorker));
```

Đây là snippet với `oneWorker` đã được tạo. `thenCompose` trả dependent chờ future con **bằng composition**, không chiếm worker chỉ để block tại `join`. Không phải mọi deadlock đều biến mất nhờ thenCompose nếu code bên trong vẫn có khóa/vòng phụ thuộc; nhưng nó giải quyết dạng “worker chờ task của chính pool” trong ví dụ.

## 24. Thực thi callback có thể khác với ngữ nghĩa nghiệp vụ

Giả sử một dependent stage `thenApply` đổi JSON thành DTO. Bạn muốn:

- DTO đúng theo schema.
- Exception được truyền đầy đủ.
- Không rò context giữa requests.
- Không làm block I/O completion thread.
- Chạy trong CPU pool để giới hạn tải.

**Không chỉ cần kết quả đúng.** Bạn còn phải chọn callback scheduling đúng để bảo vệ latency, fairness và resource isolation.

Ngược lại, nếu function chỉ `x -> x.id()` trên immutable object trong vài nanoseconds, thêm một executor hop có thể gây overhead và không tăng correctness. Non-Async callback có thể là lựa chọn tốt.

### Phân tích theo yêu cầu

| Yêu cầu | Lựa chọn điển hình |
|---|---|
| Mapping cực nhẹ, thuần túy | `thenApply` |
| Mapping CPU nặng | `thenApplyAsync(fn, cpuExecutor)` |
| Callback phải chạy trên một event loop | `thenAcceptAsync(action, eventLoopExecutor)` với executor thật sự đại diện event loop |
| Blocking DB audit | `thenApplyAsync(fn, boundedIoExecutor)` hoặc mô hình I/O bất đồng bộ có completion |
| Chỉ quan sát lỗi nhanh | `whenComplete` với telemetry nonblocking |
| Logging có thể chậm | `whenCompleteAsync(..., loggingExecutor)` hoặc queue bounded |
| Một stage trả Future khác | `thenCompose` hoặc `thenComposeAsync` tùy độ nặng/affinity của function |
| Callback cần context của caller | Explicit capture/propagation; không trông chờ ThreadLocal tự theo |

Chọn executor phù hợp vẫn cần quản lý lifecycle, deadlines và exception. Thread affinity không thay thế correctness của dữ liệu shared.

## 25. Completion race: ai được phép chạy callback?

Khi một source đang gần complete, thread T1 có thể gọi `complete` trong lúc thread T2 đang đăng ký callback. Một số lịch hợp lệ:

```text
Lịch A:
  T2: register thenApply while source incomplete
  T1: complete(source) -> executes dependent action

Lịch B:
  T1: complete(source)
  T2: thenApply on already-complete source -> executes action inline

Lịch C:
  T1/T2 cùng tham gia completion hoặc nhiều dependent stages
  callback có thể do thread tham gia completion khác thực thi
```

Điều thiết kế đúng không phụ thuộc vào lịch nào xảy ra:

- Function không dùng ThreadLocal ngầm sai.
- Function không block thread nhạy cảm nếu policy không bảo đảm.
- Function thread-safe nếu có thể chạy đồng thời với callbacks khác.
- Dependent outcome được đọc bằng `join()/get()` hoặc handler khi cần.
- Side effects/metrics không dựa vào thread name làm business identity.
- Cancellation và timeouts không được suy từ thread location.

### Không suy rằng callback luôn chạy “một lần mỗi lần complete gọi”

Một `CompletableFuture` có thể bị nhiều threads gọi `complete` cạnh tranh; chỉ một outcome thắng. Dependent action của một stage được quản lý theo completion protocol, không phải chạy lại một lần cho mỗi attempt gọi `complete`. Tuy nhiên, nếu bạn tự đăng ký **hai independent dependents** có cùng function side effect, đó là hai stage riêng và side effect có thể được thực hiện hai lần theo thiết kế.

## 26. Cancellation không giống interrupt callback thread

`CompletableFuture.cancel(true)` hoàn tất future bằng cancellation nếu còn pending, nhưng JavaDoc nói tham số `mayInterruptIfRunning` **không có tác dụng điều khiển interruption** trong implementation `CompletableFuture`.

- Hủy source có thể khiến dependents hoàn tất bất thường.
- Hủy dependent không mặc định hủy source.
- Hủy dependent không cam kết dừng một callback đang thực thi trong thread completer.
- Nếu callback là blocking I/O, cần deadline/cancellation handle của I/O thực tế.
- Nếu một source đã complete, cancel thường không đổi outcome.
- `isDone()` true bao gồm normal/exceptional/cancel.
- Callback `whenComplete` có thể cần phân loại `CancellationException` khỏi business errors.

**Không dùng `cancel(true)` như một biện pháp đảm bảo ngắt thread gây nghẽn trong `thenApply`.** Phân biệt Future completion state với execution control của underlying task.

## 27. Timeout và sự khác nhau của get(timeout), orTimeout

`result.get(100, TimeUnit.MILLISECONDS)` có thể ném `TimeoutException` cho **thread đang đợi**, nhưng không tự hoàn tất result và không dừng callback.

`result.orTimeout(100, TimeUnit.MILLISECONDS)` lên lịch để **chính future đó** completed exceptionally bằng `TimeoutException` nếu chưa complete tới deadline, nhưng không tự ngắt underlying callback/HTTP request.

`result.completeOnTimeout(defaultValue, 100, TimeUnit.MILLISECONDS)` có thể complete normally bằng fallback value khi hết hạn.

Đây là những semantics khác nhau:

| API | Ảnh hưởng chính | Tự cancel I/O thực tế? |
|---|---|---|
| `get(timeout, unit)` | Giới hạn caller wait | Không |
| `orTimeout(timeout, unit)` | Future có thể failed do timeout | Không |
| `completeOnTimeout(value, ...)` | Future có thể complete bằng fallback | Không |
| `cancel(...)` | Future marked canceled | Không bảo đảm dừng underlying work |

Nếu callback không Async chạy lâu ngay trên một completion thread, timeout future có thể đã xảy ra trong lúc work vẫn tiếp diễn. Thiết kế deadline trên I/O/task, không chỉ Future handle.

## 28. Java Memory Model và quan hệ visibility

`CompletableFuture`/`Future` cung cấp những cơ chế công bố kết quả và chờ completion, nhưng **vị trí thread thực thi callback** không tự xác định dữ liệu mutable có an toàn hay không.

Ví dụ dữ liệu kết quả được tạo trong một thread rồi future hoàn tất:

```java
record Payload(int id, String value) {}

CompletableFuture<Payload> result = new CompletableFuture<>();
// Trong thread producer khác:
result.complete(new Payload(42, "ready"));
// Trong callback:
result.thenApply(payload -> payload.id());
```

Đây là pseudocode đa thread có record Java 17. Future publication/consumption có memory ordering phù hợp để callback dùng dữ liệu đã tạo trước completion theo API. Record immutable giúp tránh races sau đó.

### Điều không được bảo đảm

- Nhiều callbacks cùng thay đổi một shared `int counter++` vẫn có thể lost update; cần `AtomicInteger`, lock hoặc ownership.
- `thenApply` không tự tạo một monitor lock quanh dữ liệu domain.
- Callback chạy trên same thread trong một execution không chứng minh nó luôn ở same thread về sau.
- `Thread.sleep` không tạo happens-before hợp lệ để publish mutable state.
- Dữ liệu mutable bị thread khác tiếp tục sửa sau khi Future complete cần synchronization riêng.
- Completion của Future không tự đồng bộ với external database transaction hoặc network acknowledgment.

### Dùng join/get đúng vai trò

`dependent.join()`/`get()` chờ dependent stage hoàn tất. Nếu muốn biết **callback đã chạy xong**, chờ dependent chứ không chỉ chờ source. Một source đã done không nhất thiết chứng minh callback được dispatch Async đã chạy xong.

Trong ví dụ, main gọi `explicitAsync.join()` để đợi callback trên `callback-worker`. Đọc source `ready.join()` chỉ biết nguồn đã thành công trước đó, không nói gì về callback mới.

## 29. Observability: theo dõi thread và thời lượng callback

Để phát hiện callback đang chiếm completion thread quá lâu:

- Ghi **stage name/correlation id**, không chỉ thread name.
- Ghi timing của callback và latency end-to-end.
- Quan sát executor queue/rejections nếu dùng `Async(..., executor)`.
- Dùng JFR/Java Flight Recorder cho các events phù hợp, thread dumps khi nghi starvation/blocking.
- Khi log, tách source failure và callback failure.
- Không log payload nhạy cảm hoặc secrets từ context.
- Không tạo logging nặng trong callback đang bị đo; chính instrumentation có thể gây latency.
- Nếu có UI/event loop, giám sát blocked event loop cảnh báo việc dùng non-Async sai nơi.

Đo time cần dùng `System.nanoTime()` cho duration, không dùng time wall-clock để so sánh chính xác những khoảng rất nhỏ.

Ví dụ instrumentation nhẹ:

```java
CompletableFuture<String> measured = source.thenApply(value -> {
    long start = System.nanoTime();
    try {
        return transform(value);
    } finally {
        observeNanos(System.nanoTime() - start);
    }
});
```

Đây là snippet, `transform`/`observeNanos` do ứng dụng định nghĩa. `observeNanos` phải ngắn và exception-safe để không vô tình làm dependent failed. Nếu `transform` ném, finally vẫn chạy để ghi duration.

## 30. Kiểm thử đúng thay vì assert thread affinity không được hứa

### Test đầu ra và exception

Dùng `CompletableFuture.completedFuture` cho normal input, `completeExceptionally` cho failed input và `join()/get()` để assert outcomes. Điều này ổn định và độc lập thread scheduler.

### Test minh họa policy

Bài demo cố tình đặt tên completer/executor để minh họa execution trên Java 17. Trong test tài liệu như vậy có thể assert thread name trong môi trường đã kiểm soát, nhưng **không biến output đó thành contract trên mọi pipeline/implementations**.

### Test callback nặng

Nếu cần chứng minh callback không block thread nhạy cảm, lựa chọn tốt nhất là **truyền executor có contract rõ** rồi dùng thread factory/metric kiểm tra; đừng cố ép một callback không Async lúc nào cũng chạy ở worker bằng sleep.

### Test concurrency

Dùng `CountDownLatch` để điều khiển thời điểm nguồn hoàn tất và callback registration nếu muốn tái hiện race. Không dựa vào `Thread.sleep(100)` để đảm bảo thread A đã đăng ký trước thread B.

### Test shutdown

Với `thenApplyAsync(..., executor)` do ứng dụng sở hữu, test shutdown/rejection policy và đảm bảo caller có deadline. Một code path chỉ test “happy path” nhưng không test executor shutdown có thể lỗi production.

## 31. Lỗi phổ biến

1. **“`thenApply` luôn chạy trên background thread.”** Sai; nó có thể chạy trên completer hoặc caller.
2. **“Nguồn tạo bằng `supplyAsync` thì toàn bộ chain mặc nhiên Async.”** Sai; `thenApply` không có hậu tố Async theo chính policy của nó.
3. **“Đăng ký callback chỉ lưu function, không chạy function ngay.”** Sai nếu source đã complete; callback có thể inline.
4. **“Callback không Async luôn chạy trên thread gọi `complete`.”** Sai; JavaDoc cho phép callers khác tham gia completion.
5. **“Callback không Async luôn chạy trên thread tạo source.”** Sai; creation không gắn thread ownership.
6. **“Callback không Async luôn chạy trên thread đăng ký.”** Sai nếu source chưa complete và thread khác hoàn tất.
7. **“`thenApplyAsync` tạo thread mới mỗi lần.”** Không; executor thường tái sử dụng workers.
8. **“`thenApplyAsync` luôn sử dụng executor của `supplyAsync` trước đó.”** Không; nếu không chỉ định, theo default async facility của stage.
9. **“Một stage Async biến mọi stage kế tiếp thành Async.”** Sai; từng stage có execution policy riêng.
10. **“Dùng ThreadLocal trong callback sẽ có context của request.”** Không bảo đảm; context cần truyền có chủ đích.
11. **“Block I/O trong `thenApply` không ảnh hưởng completion producer.”** Sai; function có thể inline trong completion.
12. **“Một callback nặng trong cache-hit path vẫn không ảnh hưởng caller.”** Sai; source ready có thể làm callback chạy ngay.
13. **“Các callbacks đăng ký trước sẽ chạy đúng thứ tự đăng ký.”** Không có thứ tự sibling callback mà business code nên dựa vào.
14. **“Callback throw làm source đã success chuyển sang failed.”** Sai; dependent failed, source vẫn có outcome riêng.
15. **“`source.join` chờ mọi dependent Async callbacks.”** Không; phải chờ dependent cụ thể.
16. **“`whenComplete` không có Async thì luôn nhẹ.”** API không giới hạn code của callback; do developer đảm bảo.
17. **“Hủy CompletableFuture sẽ interrupt callback thread.”** Không được bảo đảm.
18. **“Timeout `get` tự stop callback.”** Không; nó chỉ làm caller ngừng chờ.
19. **“Dùng `join` bên trong một worker cùng single-thread pool là luôn an toàn.”** Có thể thread-starvation deadlock.
20. **“thenCompose chặn chờ Future con như `join`.”** Không; composition nối stages mà không cần blocking join.
21. **“Non-Async callbacks không bao giờ concurrency-race với nhau.”** Những siblings/dependencies có thể chạy trên nhiều threads; shared mutable state vẫn cần synchronization.
22. **“Async giải quyết mọi thread-safety issue.”** Async chỉ thay dispatch, không thay data ownership.
23. **“Async luôn nhanh hơn non-Async.”** Không; dispatch overhead và queue delay có thể lớn hơn tiny callback.
24. **“Đặt executor mới trong từng request là vô hại.”** Dễ thread/resource leak nếu thiếu ownership/shutdown.
25. **“Thread name cho biết business request identity.”** Không; threads được tái sử dụng và callback có thể migrate theo completion policy.
26. **“Future done means all external side effects committed.”** Không; cần explicit acknowledgment/transaction.
27. **“Một callback có thể tự ý log secrets vì đang ở backend.”** Không; telemetry cũng phải tuân thủ privacy/security.
28. **“UI callback dùng thenAccept không Async là luôn UI-thread-safe.”** Sai; callback có thể chạy trên worker.
29. **“ThreadLocal của caller được tự copy sang thenApplyAsync.”** Không; phải propagate.
30. **“Tất cả callback threads đều do source executor quản lý.”** Sai; thread tham gia completion và explicit callback executor có thể khác nhau.

## 32. Checklist khi review CompletableFuture code

Trước khi merge một pipeline Java 17:

- **Stage ownership:** source nào được tạo/chạy ở đâu và ai complete nó?
- **Registration timing:** callback có thể đăng ký trước hoặc sau source complete không?
- **Execution policy:** callback dùng non-Async, default Async hay explicit Executor?
- **Thread affinity:** callback cần UI/event-loop/CPU/I/O thread cụ thể không?
- **Cost:** callback có blocking I/O, CPU-heavy compute, lock contention hoặc logging sync không?
- **Data safety:** callback mutate shared state không được bảo vệ?
- **ThreadLocal:** context có cần propagation và cleanup riêng?
- **Chaining:** thứ tự logic có được thể hiện bằng dependent stages, không phải sibling registration order?
- **Failure:** exception của source/callback được quan sát phân biệt?
- **Completion:** caller đợi source hay dependent, có timeout khi cần?
- **Cancellation:** hủy future có thực sự hủy underlying operation không?
- **Pool capacity:** executor có đủ workers cho những dependencies cần tiến triển?
- **Rejection/shutdown:** callback Async có thể bị reject khi executor ngừng nhận việc?
- **Observability:** callback latency và source completion latency được đo riêng?
- **Resource ownership:** executor tạo bởi ai và ai shutdown?
- **Testing:** đã test source incomplete, already complete, callback throwing, async executor và timeout?
- **Special scope:** bài toán chỉ liên quan Java concurrency, không trộn với framework-specific scheduling ngoài phạm vi?

## 33. Câu hỏi ôn tập và đáp án

**Câu 1.** `thenApply` không có Async có bảo đảm chạy trên thread gọi `thenApply` không?  
**Đáp án:** Không. Nếu source chưa complete, callback có thể chạy trên thread hoàn tất source; nếu source đã complete, nó có thể chạy inline trong caller theo Java17.

**Câu 2.** `thenApply` có bảo đảm chạy trên completer thread không?  
**Đáp án:** Không tuyệt đối. JavaDoc cho phép thread hoàn tất hoặc các callers tham gia completion, tùy race/implementation.

**Câu 3.** Tại sao cùng code khi cache hit và cache miss lại có latency khác?  
**Đáp án:** Cache hit có future đã complete nên non-Async callback có thể chạy ngay trong caller; cache miss có thể chạy trên thread hoàn tất I/O về sau.

**Câu 4.** Nguồn `supplyAsync` dùng executor A; `thenApply` sau đó có dùng executor A theo contract không?  
**Đáp án:** Không. Non-Async callback không có executor affinity. Nó có thể chạy trên thread hoàn tất A hoặc caller tham gia completion.

**Câu 5.** Muốn callback CPU-heavy chạy trong pool B, dùng gì?  
**Đáp án:** `thenApplyAsync(fn, poolB)` với pool B được cấu hình và quản lý lifecycle đúng.

**Câu 6.** `thenApplyAsync(fn)` không có executor có chắc chạy trên thread mới không?  
**Đáp án:** Không; thường dùng default asynchronous execution facility như common pool, có thể reuse workers.

**Câu 7.** Callback `thenApply` ném RuntimeException thì source đã success còn success không?  
**Đáp án:** Có; dependent stage failed, source outcome không đổi.

**Câu 8.** Cần đọc `source.join` hay `dependent.join` để bảo đảm callback Async đã chạy xong?  
**Đáp án:** Chờ `dependent.join`/get; source done chưa chứng minh dependent callback đã hoàn tất.

**Câu 9.** `thenAccept` và `thenRun` có cùng chính sách non-Async không?  
**Đáp án:** Có: nếu không dùng Async, callback có thể thực thi inline trên thread tham gia completion; khác nhau ở việc nhận value.

**Câu 10.** `thenCompose` có đợi blocking future con bằng `join` không?  
**Đáp án:** Không. Nó flatten một stage trả về, cho phép composition không blocking join.

**Câu 11.** Có nên đặt slow database call trong `thenApply` khi source có thể hoàn tất trên I/O event-loop không?  
**Đáp án:** Thường không; callback có thể chặn event-loop. Dùng I/O asynchronous API hoặc explicit bounded executor phù hợp.

**Câu 12.** `ThreadLocal` context của thread đăng ký có tự truyền tới completer callback không?  
**Đáp án:** Không. Cần explicit propagation và restore/cleanup.

**Câu 13.** Hai `thenAccept` siblings có luôn chạy A trước B theo đăng ký không?  
**Đáp án:** Không bảo đảm. Nếu cần order, chain `thenAccept(...).thenRun(...)`.

**Câu 14.** `cancel(true)` trên CompletableFuture có chắc interrupt underlying callback không?  
**Đáp án:** Không. Cần handle cancellation riêng cho underlying task nếu muốn dừng.

**Câu 15.** `orTimeout` có chắc hủy network request không?  
**Đáp án:** Không; nó thay đổi completion state của future tại deadline, underlying operation cần timeout/cancel riêng.

**Câu 16.** Nên assert tên thread nào cho non-Async callback trong production?  
**Đáp án:** Không assert một tên cố định nếu API không bảo đảm; kiểm thử correctness và dùng explicit executor nếu thread affinity là requirement.

**Câu 17.** Non-Async có nghĩa callback luôn thực thi đồng bộ trước khi method đăng ký trả về không?  
**Đáp án:** Không. Nếu source còn incomplete, callback có thể thực thi về sau; nếu source đã complete, nó có thể inline.

**Câu 18.** Một callback non-Async có thể chạy trong thread gọi `complete` nhưng callback khác chạy ở thread gọi `thenApply` không?  
**Đáp án:** Có, do timing của từng source/stage và completion registration khác nhau.

**Câu 19.** Dùng `thenApplyAsync` có cần shutdown executor tự tạo không?  
**Đáp án:** Có, nếu ứng dụng sở hữu executor và không có lifecycle manager khác. Phải quản lý pending callbacks và graceful shutdown policy.

**Câu 20.** Callback được dispatch qua explicit executor có nghĩa hệ thống ngoại vi cũng có transaction exactly-once không?  
**Đáp án:** Không; scheduling của callback và tính nguyên tử của external side effects là hai vấn đề độc lập.

## 34. Bài tập thực hành

### Bài tập A — trước/sau completion

Viết hai tests độc lập: test 1 đăng ký `thenApply` khi source còn pending rồi một named thread complete; test 2 tạo `completedFuture` rồi đăng ký callback trên main. Ghi thread name, giải thích vì sao cả hai thuộc execution policy được phép, và không đưa tên thread thành contract production.

### Bài tập B — Async executor

Tạo `ExecutorService` với custom ThreadFactory name, rồi dùng `thenAcceptAsync`. Assert callback hoàn tất trước khi main đọc kết quả, quản lý shutdown và test khi executor đã shutdown.

### Bài tập C — source success, dependent failure

Tạo `CompletableFuture.completedFuture("bad")`; `thenApply` kiểm tra dữ liệu và throw. Kiểm tra `source.isCompletedExceptionally()==false`, `dependent.isCompletedExceptionally()==true` và `join` của dependent có cause đúng.

### Bài tập D — một-worker deadlock

Viết test harness có timeout cho trường hợp supplier ở single-thread pool gọi `join` trên another task được gửi vào chính pool. Giải thích vì sao tasks không tiến triển, rồi refactor bằng `thenCompose` và không blocking join trong worker.

### Bài tập E — context propagation

Cho một non-Async callback đọc `ThreadLocal`. Chạy một source complete trên worker khác và quan sát giá trị không được truyền. Sửa bằng cách capture immutable context và truyền vào callback; nếu cần ThreadLocal thật, set/restore trong finally.

### Bài tập F — callback nặng

Thử `thenApply` với expensive mapping trên một source complete, đo thời gian thread gọi `complete` hoặc `thenApply` có thể bị chiếm. Đổi sang `thenApplyAsync(..., cpuExecutor)`, đo lại latency của caller/completer và tổng end-to-end latency. Đừng kết luận Async “luôn nhanh hơn”; đo cả queueing overhead.

### Bài tập G — callback ordering

Đăng ký hai siblings `thenAccept` trên cùng source, rồi thay bằng chain `thenAccept(...).thenRun(...)`. Assert business ordering chỉ ở phiên bản chain; không dựa vào thứ tự siblings trên một lần chạy may mắn.

## 35. Tài liệu tham khảo chính thức

- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): phần **Policies**, non-Async dependent completion execution, default async facility, `thenApply/thenApplyAsync`, `thenCompose`, `complete`, `cancel`, `join`.
- [Java SE 17 — CompletionStage](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html): semantics của dependent stages, function/consumer callbacks, synchronous/async variants và exceptional completion.
- [Java SE 17 — Executor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html): `execute` và memory consistency.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): thread pools, lifecycle, shutdown và Future completion.
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `get`, cancellation và memory consistency.
- [Java SE 17 — ForkJoinPool](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): common pool và work-stealing context.
- [Java SE 17 — CompletionException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionException.html): dependent failure và cause.
- [Java Language Specification `17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): happens-before, thread safety và memory visibility.

**Kết luận:** callback của `CompletableFuture` không có hậu tố `Async` **không được dispatch tới một executor cố định theo mặc định**. Nó có thể được thực thi bởi thread đang hoàn tất source hoặc một caller tham gia completion; nếu source đã hoàn tất, nó có thể chạy ngay trong thread đăng ký callback. Khi callback nặng, blocking hoặc có yêu cầu thread affinity, hãy dùng `Async(..., Executor)` với ownership, capacity và deadline rõ ràng. Kết quả và exception thuộc mỗi stage riêng, nên chờ dependent stage khi cần xác nhận callback đã hoàn tất và truyền context có chủ đích thay vì suy từ thread identity.