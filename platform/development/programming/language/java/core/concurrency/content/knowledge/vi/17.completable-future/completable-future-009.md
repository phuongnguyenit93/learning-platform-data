# `handle()`, `exceptionally()` và `whenComplete()` trong CompletableFuture

Một `CompletableFuture<T>` có thể hoàn tất bình thường (normal completion), hoàn tất bất thường (exceptional completion), hoặc chưa hoàn tất. Khi xây dựng một pipeline bất đồng bộ, cần phân biệt **xử lý lỗi để phục hồi** và **chỉ quan sát lỗi**. Ba phương thức phổ biến của `CompletionStage`/`CompletableFuture` phục vụ các mục tiêu khác nhau:

- **`handle((value, error) -> newValue)`** chạy **cả khi thành công lẫn thất bại** và tạo **giá trị kết quả mới**, có thể đổi kiểu `T` thành `U`. Nếu callback trả giá trị bình thường sau một lỗi, dependent future đã được phục hồi.
- **`exceptionally(error -> fallback)`** chỉ chạy khi **thất bại**, trả **fallback cùng kiểu `T`**. Khi thành công, callback không chạy và dependent future nhận lại giá trị thành công ban đầu.
- **`whenComplete((value, error) -> observe())`** chạy **cả hai nhánh**, dùng để log, ghi metric, theo dõi hoặc cleanup. Nó **không phải recovery API**: nếu callback trả bình thường, dependent future giữ nguyên giá trị hoặc lỗi của upstream.

Điểm quan trọng: **mỗi method trả một dependent stage mới**, không biến upstream đang lỗi thành upstream thành công. Kết quả của một chain phụ thuộc vị trí đặt handler.

Bài thuộc nhóm **CompletableFuture** của **Java concurrency nói chung**, sử dụng Java SE 17+ và không dùng Spring-specific APIs.

## 1. Mô hình outcome của CompletableFuture

`CompletableFuture<T>` có ba tình huống quan sát:

```text
           INCOMPLETE
                |
       +--------+---------+
       |                  |
  NORMAL(value)    EXCEPTIONAL(error)
       |                  |
  value có thể null  lỗi, cancellation,
                     lỗi từ continuation
```

Normal completion **có thể mang `null`**. Exceptional completion mang thông tin `Throwable` hoặc cancellation theo contract. `isDone()` true không đồng nghĩa task thành công; `isCompletedExceptionally()` còn bao gồm cancellation và các trường hợp lỗi từ continuation.

Các callback được kích hoạt khi **source stage hoàn tất**. Nếu source đã hoàn tất trước khi callback được đăng ký, handler có thể được kích hoạt ngay theo execution policy tương ứng; nếu chưa hoàn tất, handler phụ thuộc vào thời điểm source hoàn tất. Không có bảo đảm callback non-async luôn chạy ở main thread.

## 2. Bảng so sánh chính xác

| Thuộc tính | `handle` | `exceptionally` | `whenComplete` |
| --- | --- | --- | --- |
| Chạy khi success | Có | Không | Có |
| Chạy khi failure | Có | Có | Có |
| Callback | `BiFunction<T,Throwable,U>` | `Function<Throwable,T>` | `BiConsumer<T,Throwable>` |
| Trả một giá trị từ callback | Có | Có | Không |
| Kiểu dependent | `CompletableFuture<U>` | `CompletableFuture<T>` | `CompletableFuture<T>` |
| Có thể recover lỗi | Có | Có | **Không chủ đích** |
| Khi callback chạy thành công và source lỗi | Thành công với U | Thành công với fallback T | **Vẫn thất bại** |
| Trường hợp lý tưởng | Biến đổi cả success/failure | Fallback cho lỗi | Log, metric, audit |

**Quy tắc chọn nhanh:** muốn thay kết quả ở cả hai nhánh dùng `handle`; chỉ cần fallback khi lỗi dùng `exceptionally`; không muốn thay kết quả, chỉ quan sát dùng `whenComplete`.

## 3. Chữ ký phương thức (Java SE 17)

```java
<U> CompletableFuture<U> handle(
        BiFunction<? super T, Throwable, ? extends U> fn);

CompletableFuture<T> exceptionally(
        Function<Throwable, ? extends T> fn);

CompletableFuture<T> whenComplete(
        BiConsumer<? super T, ? super Throwable> action);
```

Đây là **trích lược chữ ký API**, không phải class độc lập. `handle` có type parameter mới `U`, còn `exceptionally`/`whenComplete` giữ `T`. `whenComplete` nhận `BiConsumer`, nên callback **không trả fallback**.

Hãy import các class cần thiết từ `java.util.concurrent`. Có thể dùng method trực tiếp trên `CompletableFuture` hoặc qua interface `CompletionStage`; tại interface, các operation trả `CompletionStage`.

## 4. `handle` trên success và failure

Ví dụ ý tưởng:

```java
CompletableFuture<String> normalized =
        source.handle((value, error) -> {
            if (error != null) {
                return "FAILED";
            }
            return "VALUE:" + value;
        });
```

Đoạn minh họa giả định `source` là `CompletableFuture<Integer>`.

- Success 15 → dependent success `"VALUE:15"`.
- Failure E → dependent success `"FAILED"` nếu callback không throw.
- Nếu callback tự throw F → dependent failure F.
- Source giữ nguyên outcome cũ trong mọi trường hợp.

`handle` có thể chuyển `CompletableFuture<Integer>` thành `CompletableFuture<String>` hoặc thành một object mô tả `Result<T>`. Nhưng nếu chỉ muốn fallback trên lỗi, `exceptionally` đơn giản hơn vì không cần viết logic cho success.

## 5. `exceptionally` chỉ xử lý lỗi

Ví dụ:

```java
CompletableFuture<Integer> safe =
        source.exceptionally(error -> -1);
```

Đoạn minh họa giả định `source` có kiểu `CompletableFuture<Integer>`.

- Success 15 → `safe` success 15; lambda **không chạy**.
- Failure E → lambda chạy, trả -1; `safe` success -1.
- Lambda throw → `safe` vẫn exceptional.

**Phục hồi nghĩa là một quyết định nghiệp vụ**: với cache read lỗi, giá trị trống có thể chấp nhận được; với thanh toán, trả `true` khi network lỗi sẽ tạo thông tin sai. Không nên dùng `exceptionally(e -> null)` cho mọi lỗi nếu null sau đó bị diễn giải là data hợp lệ.

## 6. `whenComplete` quan sát nhưng giữ outcome

`whenComplete` phù hợp để thống kê và theo dõi:

```java
CompletableFuture<Integer> observed =
        source.whenComplete((value, error) -> {
            if (error == null) {
                recordSuccess(value);
            } else {
                recordFailure(error);
            }
        });
```

Đây là snippet minh họa, `recordSuccess`/`recordFailure` thuộc application.

- Success 15 + callback return bình thường → dependent success 15.
- Failure E + callback return bình thường → dependent **failure E**.
- Callback tự ném lỗi → áp dụng quy tắc exception precedence ở phần sau.

**Ghi log exception không phải là catch/recover.** Muốn downstream nhận fallback phải thêm `exceptionally` hoặc `handle` ở vị trí phù hợp.

## 7. Ví dụ Java 17+: so sánh cả ba phương thức

Lưu thành `ThreeHandlersDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicBoolean;

public class ThreeHandlersDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> ok =
                CompletableFuture.completedFuture(7);
        CompletableFuture<Integer> bad =
                CompletableFuture.failedFuture(
                        new IllegalArgumentException("bad"));

        String handledOk = ok.handle(
                (v, e) -> e == null ? "OK:" + v : "FAIL").join();
        String handledBad = bad.handle(
                (v, e) -> e == null ? "OK:" + v : "FAIL").join();

        int normal = ok.exceptionally(e -> -1).join();
        int fallback = bad.exceptionally(e -> -1).join();

        AtomicBoolean observedError = new AtomicBoolean();
        CompletableFuture<Integer> watched =
                bad.whenComplete((v, e) ->
                        observedError.set(e != null));

        System.out.println("Handle success: " + handledOk);
        System.out.println("Handle failure: " + handledBad);
        System.out.println("Exceptionally success: " + normal);
        System.out.println("Exceptionally failure: " + fallback);
        System.out.println("Observed error: " + observedError.get());
        System.out.println("Observer recovered: "
                + !watched.isCompletedExceptionally());
    }
}
```

Biên dịch và chạy:

```bash
javac ThreeHandlersDemo.java
java ThreeHandlersDemo
```

Stdout chính xác:

```text
Handle success: OK:7
Handle failure: FAIL
Exceptionally success: 7
Exceptionally failure: -1
Observed error: true
Observer recovered: false
```

Hai source đã hoàn tất trước khi đăng ký handler, nên kết quả không cần dựa vào lịch chạy của thread. `watched` vẫn exceptional dù observer đã nhìn thấy lỗi.

## 8. Outcome matrix: hiểu dependent stage

| Upstream | Handler | Dependent (nếu callback không throw) |
| --- | --- | --- |
| Success 5 | `handle((v,e)->v+1)` | Success 6 |
| Failure E | `handle((v,e)->0)` | Success 0 |
| Success 5 | `exceptionally(e->0)` | Success 5 |
| Failure E | `exceptionally(e->0)` | Success 0 |
| Success 5 | `whenComplete(log)` | Success 5 |
| Failure E | `whenComplete(log)` | **Failure E** |

Không có method nào trong ba cái tự retry operation gốc. Một handler thường **biến outcome** của source thành outcome của dependent; nếu muốn retry, cần thiết kế một thao tác async mới với deadline, idempotency, cancellation và giới hạn số lần.

## 9. Success có giá trị null: lỗi kiểm tra phổ biến

Nếu source complete normal với `null`:

```java
CompletableFuture<String> empty =
        CompletableFuture.completedFuture(null);

String answer = empty.handle((value, error) ->
        error == null ? "NORMAL" : "FAILED").join();
```

`answer` là `"NORMAL"`, không phải `"FAILED"`.

Vì vậy đừng phân nhánh bằng `value == null` để đoán lỗi. `handle`/`whenComplete` cần xét **`error != null`**. `CompletableFuture<Void>` (thường từ `runAsync`/`thenRun`) càng làm rõ điều này: normal value là null.

Nếu business contract không cho null, hãy validation tách riêng bằng `thenApply` hoặc logic trong `handle`, nhưng không đánh đồng framework's normal completion với business validation.

## 10. Ví dụ Java 17+: null vẫn là normal outcome

Lưu thành `NullCompletionDemo.java`:

```java
import java.util.concurrent.CompletableFuture;

public class NullCompletionDemo {
    public static void main(String[] args) {
        CompletableFuture<String> source =
                CompletableFuture.completedFuture(null);

        String handled = source.handle((v, e) ->
                e == null ? "NORMAL_NULL" : "ERROR").join();

        String fallback = source.exceptionally(
                e -> "fallback").join();

        String observed = source.whenComplete(
                (v, e) -> {
                    if (e != null) {
                        throw new AssertionError("unexpected");
                    }
                }).join();

        System.out.println("Handle: " + handled);
        System.out.println("Exceptionally kept null: "
                + (fallback == null));
        System.out.println("WhenComplete kept null: "
                + (observed == null));
    }
}
```

```bash
javac NullCompletionDemo.java
java NullCompletionDemo
```

Stdout chính xác:

```text
Handle: NORMAL_NULL
Exceptionally kept null: true
WhenComplete kept null: true
```

`exceptionally` được bỏ qua vì không có exception, dù giá trị là null.

## 11. Exception propagation dọc một chain

Nhóm method `thenApply`/`thenAccept`/`thenRun` chỉ chạy callback khi upstream **complete normal**. Nếu upstream exceptional, dependent của chúng nhận failure mà **không chạy callback normal-only**.

```text
source success -> thenApply(validate) ---- throws E
                                      |
                                      v
                       thenApply(enrich) [skipped]
                                      |
                                      v
                          exceptionally(fallback)
                                      |
                                      v
                         thenApply(render) [runs]
```

Khi `exceptionally` hoàn tất normal với fallback, `thenApply` phía sau coi fallback là input bình thường. Do đó, vị trí xử lý lỗi rất quan trọng: handler **đặt trước** một stage thất bại không xử lý lỗi **sinh ra sau** nó.

## 12. Ví dụ Java 17+: recovery đặt đúng vị trí

Lưu thành `HandlerPositionDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicBoolean;

public class HandlerPositionDemo {
    public static void main(String[] args) {
        AtomicBoolean skipped = new AtomicBoolean();

        CompletableFuture<Integer> source =
                CompletableFuture.completedFuture(10);

        CompletableFuture<Integer> invalid =
                source.thenApply(n -> {
                    throw new IllegalArgumentException("invalid");
                });

        int result = invalid
                .thenApply(n -> {
                    skipped.set(true);
                    return n + 1;
                })
                .exceptionally(error -> 40)
                .thenApply(n -> n + 2)
                .join();

        CompletableFuture<Integer> lateFailure =
                source.exceptionally(error -> 99)
                      .thenApply(n -> {
                          throw new IllegalStateException("late");
                      });

        System.out.println("Recovered: " + result);
        System.out.println("Skipped normal callback: "
                + !skipped.get());
        System.out.println("Late failure remains: "
                + lateFailure.isCompletedExceptionally());
    }
}
```

```bash
javac HandlerPositionDemo.java
java HandlerPositionDemo
```

Stdout chính xác:

```text
Recovered: 42
Skipped normal callback: true
Late failure remains: true
```

Lỗi từ `invalid` khiến `thenApply` kế tiếp không chạy. `exceptionally` phục hồi 40, stage sau cộng 2. Trong nhánh khác, `exceptionally` đứng **trước** stage gây lỗi nên không thể sửa lỗi chưa phát sinh.

## 13. `handle` đổi kiểu kết quả T → U

`handle` là lựa chọn tự nhiên khi muốn đưa cả dữ liệu thành công và lỗi về cùng một **domain result**:

```java
record Outcome<T>(T value, Throwable error) {
    boolean success() {
        return error == null;
    }
}

CompletableFuture<Integer> source = ...;
CompletableFuture<Outcome<Integer>> result =
        source.handle(Outcome::new);
```

Đây là snippet Java 17 minh họa, không có class `main`. Khi source exceptional, dependent có thể complete normal với `Outcome` chứa lỗi; điều này **không có nghĩa upstream đã được sửa**.

Ưu điểm: API downstream có thể nhận một object trạng thái rõ ràng. Nhược điểm: nếu caller quên kiểm tra `error`, nó có thể vô tình coi failure thành success. Nếu muốn error type mạnh hơn, có thể dùng `sealed interface Result<T>` theo thiết kế ứng dụng.

`exceptionally` không đổi kiểu `T` sang `U`: nó trả fallback tương thích với kiểu gốc. `whenComplete` không tạo value từ callback.

## 14. Exception do chính callback tạo ra

Ba continuation đều có thể phát sinh exception mới:

- `handle` callback throw F → dependent stage **failure F**, kể cả source đã success.
- `exceptionally` callback throw F trong lúc đang xử lý lỗi → dependent **failure F**, không tự fallback thêm lần nữa.
- `whenComplete` callback throw F → phải xét thêm outcome **source** để xác định exception nào được ưu tiên.

Nếu muốn giữ nguyên một cause cũ khi rethrow, hãy dùng wrapping có cause thay vì chỉ tạo `new RuntimeException("failed")` không chứa nguyên nhân. Cũng đừng bắt mọi `Throwable` rồi đổi thành null, vì có thể che lỗi lập trình hoặc cancellation.

## 15. Quy tắc ưu tiên lỗi của `whenComplete`

Java `CompletionStage` quy định cụ thể:

1. Source **success** + observer return → dependent **success**, giữ value gốc.
2. Source **success** + observer throw F → dependent **failure F**.
3. Source **failure E** + observer return → dependent **failure E**.
4. Source **failure E** + observer throw F → dependent **failure E được ưu tiên** so với F.

Sơ đồ:

```text
source SUCCESS ---- whenComplete OK ----> SUCCESS original value
        |                |
        +---- observer throws F --------> FAILURE F

source FAILURE E -- whenComplete OK ----> FAILURE E
        |
        +---- observer throws F --------> FAILURE E (preferred)
```

Không giả định lỗi của observer nhất thiết được đưa vào suppressed exceptions. Hợp đồng chung chỉ cam kết **ưu tiên lỗi source** khi cả hai cùng thất bại.

Một callback logging có thể làm pipeline thành thất bại **mới** khi source vốn thành công. Vì vậy observer nên ngắn, được kiểm soát, và không throw ngoài ý muốn.

## 16. Ví dụ Java 17+: lỗi source được ưu tiên

Lưu thành `WhenCompletePrecedenceDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class WhenCompletePrecedenceDemo {
    static String cause(CompletableFuture<?> stage) {
        try {
            stage.join();
            return "NONE";
        } catch (CompletionException e) {
            return e.getCause().getClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        CompletableFuture<String> ok =
                CompletableFuture.completedFuture("ok");

        CompletableFuture<String> failed =
                CompletableFuture.failedFuture(
                        new IllegalArgumentException("original"));

        CompletableFuture<String> observerFailure =
                ok.whenComplete((v, e) -> {
                    throw new IllegalStateException("observer");
                });

        CompletableFuture<String> bothFailed =
                failed.whenComplete((v, e) -> {
                    throw new IllegalStateException("observer");
                });

        System.out.println("Success + observer throws: "
                + cause(observerFailure));
        System.out.println("Failure + observer throws: "
                + cause(bothFailed));
    }
}
```

```bash
javac WhenCompletePrecedenceDemo.java
java WhenCompletePrecedenceDemo
```

Stdout chính xác:

```text
Success + observer throws: IllegalStateException
Failure + observer throws: IllegalArgumentException
```

Code quan sát cause của `CompletionException` từ dependent stage, không suy kết quả từ thứ tự logging. Đây là trường hợp cần hiểu khi đặt `whenComplete` ở cuối một pipeline và callback tự lỗi.

## 17. `join()` và `get()` khi future exceptional

`CompletableFuture.join()` thuận tiện trong pipeline vì dùng unchecked exception: với exceptional completion thông thường nó ném `CompletionException` có cause gốc; cancellation có thể được báo bằng `CancellationException`.

`get()` theo `Future` contract có `InterruptedException` và `ExecutionException` khi thất bại; `get(timeout, unit)` còn có `TimeoutException`.

Một dependent callback có thể nhận `Throwable` đã là `CompletionException`, không phải exception nghiệp vụ trực tiếp. Helper minh họa:

```java
static Throwable unwrap(Throwable error) {
    if (error instanceof java.util.concurrent.CompletionException ce
            && ce.getCause() != null) {
        return ce.getCause();
    }
    return error;
}
```

Đây là method Java 17 minh họa; nó unwrap **một lớp** và giữ cause. Không unwrap tất cả tầng một cách mù quáng rồi mất context cần chẩn đoán.

## 18. Cancellation cũng là một exceptional outcome

Theo Java SE 17, `CompletableFuture.cancel(boolean)` hoàn tất future chưa done bằng `CancellationException`. Tham số `mayInterruptIfRunning` **không dùng để điều khiển underlying computation** của `CompletableFuture`.

Hệ quả:

- `handle` có thể thấy Throwable đại diện cancellation.
- `exceptionally` có thể chuyển cancellation thành fallback normal ở **dependent stage**.
- `whenComplete` chỉ ghi nhận cancellation và thường giữ exceptional outcome.
- Việc dependent recover **không đổi `isCancelled()` của source**.
- Không nên dùng fallback cho mọi cancellation nếu caller cần tôn trọng yêu cầu hủy.

Cancellation một `CompletableFuture` không chứng minh một I/O task đã bị interrupt, side effect đã rollback hoặc worker đã cleanup xong. Đó là một lifecycle contract khác.

## 19. Ví dụ Java 17+: observer không xóa cancellation

Lưu thành `CancellationHandlersDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicBoolean;

public class CancellationHandlersDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> source =
                new CompletableFuture<>();

        AtomicBoolean seen = new AtomicBoolean();
        CompletableFuture<Integer> observed =
                source.whenComplete((v, e) -> seen.set(e != null));
        CompletableFuture<Integer> fallback =
                observed.exceptionally(e -> -99);

        boolean canceled = source.cancel(true);

        System.out.println("Source canceled: " + canceled);
        System.out.println("Observed error: " + seen.get());
        System.out.println("Observed still exceptional: "
                + observed.isCompletedExceptionally());
        System.out.println("Fallback result: " + fallback.join());
        System.out.println("Source isCancelled: "
                + source.isCancelled());
    }
}
```

```bash
javac CancellationHandlersDemo.java
java CancellationHandlersDemo
```

Stdout chính xác:

```text
Source canceled: true
Observed error: true
Observed still exceptional: true
Fallback result: -99
Source isCancelled: true
```

Không có worker thật trong ví dụ nên không đưa ra bất kỳ lời hứa nào về interrupt một task đang chạy. Nó chỉ minh họa **state của source** và **state của dependent stages**.

## 20. Async variants: ai chạy callback?

Các method không có `Async` không cam kết chạy trên một thread cụ thể. Callback có thể được thực thi bởi thread hoàn tất source hoặc thread khác tham gia completion theo JDK policy.

Các biến thể:

```java
source.handleAsync(fn, executor);
source.whenCompleteAsync(action, executor);
source.exceptionallyAsync(recoveryFn, executor);
```

Đây là snippet Java 17 minh họa với các biến khai báo ở nơi khác.

- `...Async` chọn **execution facility cho callback**, không chuyển upstream computation sang executor đó.
- Nếu không truyền executor, default async facility của `CompletableFuture` thường dùng `ForkJoinPool.commonPool()` theo contract (có những ngoại lệ được Javadoc nêu).
- Callback async vẫn có thể block; `Async` không có nghĩa non-blocking.
- Executor có thể từ chối công việc khi shutdown/quá tải, làm dependent exceptional.
- Callback log lâu có thể giữ worker của executor, tăng tail latency.

Dùng executor riêng khi cần cô lập callback nặng; quản lý bounded queue, shutdown và rejection policy phù hợp.

## 21. Ví dụ Java 17+: executor được chỉ định rõ

Lưu thành `AsyncHandlerDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class AsyncHandlerDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor =
                Executors.newSingleThreadExecutor(
                        r -> new Thread(r, "named-worker"));
        AtomicReference<String> threadName =
                new AtomicReference<>();

        try {
            CompletableFuture<Integer> source =
                    CompletableFuture.completedFuture(10);

            int handled = source.handleAsync(
                    (value, error) -> value * 2,
                    executor).join();

            int observed = source.whenCompleteAsync(
                    (value, error) ->
                            threadName.set(
                                    Thread.currentThread().getName()),
                    executor).join();

            System.out.println("Handled: " + handled);
            System.out.println("Observer thread: " + threadName.get());
            System.out.println("Original: " + observed);
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
```

```bash
javac AsyncHandlerDemo.java
java AsyncHandlerDemo
```

Stdout trên đường chạy bình thường:

```text
Handled: 20
Observer thread: named-worker
Original: 10
```

`join()` của main đợi các callbacks trước khi in. Tên thread xác định vì executor được cấu hình tạo thread với tên đó. Không suy ngược rằng non-async callback luôn chạy trên main.

## 22. `exceptionallyCompose` khi fallback cũng bất đồng bộ

`exceptionally` đòi callback trả **`T`**, không phải một future khác. Nếu recovery cần gọi tiếp một asynchronous service, Java 17 có `exceptionallyCompose`:

```java
CompletableFuture<String> recovered =
        source.exceptionallyCompose(error ->
                fetchBackupAsync());
```

Đây là snippet minh họa; `fetchBackupAsync` trả `CompletionStage<String>` phù hợp.

Trong Java 17 còn có `exceptionallyAsync` và `exceptionallyComposeAsync` để lựa chọn execution facility. Phân biệt:

- `exceptionally`: fallback **T**.
- `exceptionallyAsync`: fallback **T** nhưng callback scheduled async.
- `exceptionallyCompose`: fallback **CompletionStage<T>**, và dependent theo kết quả async của stage đó.

Đừng viết `source.exceptionally(e -> fetchBackupAsync())` khi `source` là `CompletableFuture<String>`: type không khớp. Cũng không dùng `handle` với callback trả `CompletableFuture<T>` mà quên flatten, vì sẽ có nested future nếu không compose.

## 23. Đặt observer trước hay sau recovery?

Hai pipeline có ý nghĩa metric khác nhau:

```text
source
  |
whenComplete(logOriginalOutcome)
  |
exceptionally(fallback)
  |
whenComplete(logFinalOutcome)
  |
join/get
```

- Observer đầu thấy **failure gốc**.
- `exceptionally` có thể recover thành normal fallback.
- Observer cuối thấy **success đã phục hồi**, không còn biết lỗi cũ nếu không giữ context riêng.
- Source vẫn giữ exceptional completion.

Nếu chỉ đặt `whenComplete` **sau recovery**, metric failure có thể bị mất. Ngược lại, nếu log ở tất cả stages, cùng một lỗi có thể tạo duplicate stack traces và overhead.

Lưu ý: để bảo đảm quan hệ phụ thuộc, các stage phải **nối thành cùng chain** như sơ đồ. Một nhánh quan sát độc lập không tự bảo đảm callback chạy trước recovery ở nhánh khác.

## 24. Ví dụ Java 17+: ghi nhận lỗi gốc và success đã phục hồi

Lưu thành `RecoveryTelemetryDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicBoolean;

public class RecoveryTelemetryDemo {
    public static void main(String[] args) {
        AtomicBoolean originalError = new AtomicBoolean();
        AtomicBoolean recoveredSuccess = new AtomicBoolean();

        CompletableFuture<Integer> source =
                CompletableFuture.failedFuture(
                        new IllegalStateException("temporary"));

        int result = source
                .whenComplete((v, e) ->
                        originalError.set(e != null))
                .exceptionally(e -> 12)
                .whenComplete((v, e) ->
                        recoveredSuccess.set(
                                e == null && v == 12))
                .join();

        System.out.println("Original failed: "
                + originalError.get());
        System.out.println("Recovered value: " + result);
        System.out.println("Final succeeded: "
                + recoveredSuccess.get());
        System.out.println("Source still failed: "
                + source.isCompletedExceptionally());
    }
}
```

```bash
javac RecoveryTelemetryDemo.java
java RecoveryTelemetryDemo
```

Stdout chính xác:

```text
Original failed: true
Recovered value: 12
Final succeeded: true
Source still failed: true
```

Một stage được phục hồi thành công **không ghi đè source**. Đây cũng là lý do log và metrics cần đặt đúng điểm trong pipeline.

## 25. Những anti-pattern cần tránh

**1. "Đã `whenComplete` log exception nên lỗi đã được catch."** Sai; dependent vẫn exceptional trừ trường hợp callback tạo một lỗi mới được ưu tiên theo quy tắc.

**2. "`exceptionally` luôn chạy."** Sai; nó bỏ qua normal completion.

**3. "`handle` chỉ để ghi log."** Không. Nó tạo outcome mới, có thể đổi kiểu và recover.

**4. "`whenComplete` return một fallback value."** Không. Callback trả `void`.

**5. "`value == null` báo failure."** Sai. Normal result có thể null.

**6. "`exceptionally` phục hồi lỗi của các stage phía sau."** Không. Nó chỉ thấy lỗi đã tới stage đầu vào.

**7. "`whenComplete` callback throw không ảnh hưởng pipeline."** Sai khi upstream success; dependent sẽ fail.

**8. "Source fail E, observer throw F thì dependent luôn fail F."** Sai; E được ưu tiên.

**9. "Recovery làm source.isCompletedExceptionally() thành false."** Sai. Dependent là future khác.

**10. "`handleAsync` luôn chuyển source task sang executor mới."** Sai; nó lên lịch callback.

**11. "Cancellation luôn nên recover thành 0."** Không. Đó là chính sách có thể che yêu cầu hủy.

**12. "Callback luôn nhận exception nghiệp vụ không bọc."** Không. Có thể gặp `CompletionException`.

**13. "`join` và `get` cùng loại checked exception."** Sai. `get` có `ExecutionException` và `InterruptedException`.

**14. "Dùng callback blocking lâu không ảnh hưởng concurrency."** Sai; nó có thể giữ completion/executor thread.

**15. "`exceptionally` trả `CompletableFuture<T>` như `exceptionallyCompose`."** Sai; nó trả value `T`.

**16. "Mọi lỗi đều phải biến thành default thành công."** Không. Cần phân loại recoverable, fatal và cancellation theo contract nghiệp vụ.

## 26. Checklist review trước khi đưa vào production

1. **Stage nào có thể fail?** Source, validation, transformation, executor rejection, timeout hay cancellation?
2. **Handler nằm sau stage nào?** Không thể xử lý lỗi xuất hiện về sau.
3. **Cần quan sát hay recovery?** `whenComplete` khác `exceptionally/handle`.
4. **Cần đổi `T` thành `U`?** Dùng `handle` nếu phải xử lý cả hai outcome.
5. **Success có thể null?** Không suy failure bằng `value==null`.
6. **Fallback có rõ ý nghĩa nghiệp vụ?** Không tạo "thành công giả".
7. **Observer có thể throw/block?** Kiểm soát logging và cleanup.
8. **Nguồn lỗi có đang bị che bởi recovery không?** Đặt telemetry trước fallback nếu cần.
9. **Có cancellation?** Không tự nuốt yêu cầu hủy.
10. **Exception wrapper có được xử lý đúng?** Giữ cause/stack trace.
11. **Async callback dùng executor nào?** Định nghĩa ownership/shutdown.
12. **Có nhiều branches cùng dùng source?** Recovery một nhánh không sửa branches khác.
13. **Có kiểm thử callback tự throw?** Kiểm tra quy tắc `whenComplete` precedence.
14. **Có kiểm thử null và `Void`?**
15. **Có kiểm thử thành công/thất bại ở các thời điểm đăng ký callback khác nhau?**
16. **Có test không phụ thuộc `Thread.sleep` hoặc timestamp may rủi?** Dùng completed/failed futures và `join/get(timeout)`.
17. **Có side effect bên ngoài cần idempotency?** Handler không tự cung cấp transaction hoặc retry an toàn.
18. **Caller dùng `join()` hay `get()`?** Document exception contract phù hợp.

## 27. Câu hỏi tự kiểm tra

**Câu 1.** `completedFuture(5).exceptionally(e -> 10).join()` trả gì?

**5**, vì success không kích hoạt exception handler.

**Câu 2.** Source lỗi, `handle((v,e)->0)` trả 0 bình thường. Dependent có còn exceptional không?

**Không**, dependent complete normal với 0; source vẫn exceptional.

**Câu 3.** Source lỗi, `whenComplete` log rồi return. Dependent có hết lỗi không?

**Không**, lỗi source vẫn được truyền tiếp.

**Câu 4.** `whenComplete` throw khi source success thì sao?

Dependent fail vì lỗi observer.

**Câu 5.** Source fail E và observer cũng throw F, dependent ưu tiên gì?

**E**, theo `CompletionStage` contract.

**Câu 6.** `handle` có thể chuyển `CompletableFuture<Integer>` sang `CompletableFuture<String>`?

**Có**; callback trả `String`.

**Câu 7.** `exceptionally` trả thêm một asynchronous stage có đúng không?

Không; dùng `exceptionallyCompose` khi callback cần trả `CompletionStage<T>`.

**Câu 8.** `handle((v,e) -> v==null ? "failed" : "ok")` có an toàn khi null là value hợp lệ?

Không. Phải kiểm tra `e != null` để biết exceptional completion.

**Câu 9.** `exceptionally` trước `thenApply` có xử lý lỗi do `thenApply` tự tạo không?

Không. Lỗi xảy ra ở phía sau handler.

**Câu 10.** `cancel(true)` của `CompletableFuture` có bảo đảm interrupt worker không?

Không. Đó là exceptional state của future theo contract, không phải bảo đảm điều khiển underlying computation.

**Câu 11.** Sau fallback thành công, observer cuối nhìn thấy gì?

Normal result đã phục hồi; muốn log lỗi gốc phải quan sát upstream **trước** recovery hoặc giữ context riêng.

**Câu 12.** `get()` và `join()` có cùng exception contract không?

Không. `get` theo `Future` có checked exceptions; `join` thường dùng `CompletionException` unchecked.

## 28. Tổng kết

- **`handle`:** cả success/failure → tạo giá trị mới, có thể đổi kiểu và recover.
- **`exceptionally`:** chỉ failure → trả fallback cùng kiểu; không đụng normal result.
- **`whenComplete`:** cả success/failure → quan sát outcome, **không recover**, giữ result/lỗi gốc nếu observer return bình thường.
- **Exception precedence:** observer throw khi upstream success sẽ làm dependent fail; nếu upstream cũng fail, lỗi upstream được ưu tiên.
- **Null normal result** là hợp lệ; phải phân nhánh theo `Throwable`, không theo null value.
- **Continuation order** quyết định ai nhìn thấy lỗi; recovery sớm biến các stage phía sau thành normal flow.
- **Async variants** chọn execution facility cho callback; không đổi worker của source.
- **Cancellation** cũng có exceptional semantics của CompletableFuture; fallback không tự dừng computation.
- **Source và dependent là những stages khác nhau**; recovery không ghi đè source hay nhánh khác.

Mẹo ghi nhớ: **`handle` = "tôi quyết định lại outcome"; `exceptionally` = "chỉ khi lỗi tôi mới trả fallback"; `whenComplete` = "tôi quan sát, không sửa outcome"**.

**Tham khảo chính thức:** [CompletableFuture — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html) và [CompletionStage — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html).