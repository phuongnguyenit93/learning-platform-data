# `CompletableFuture.handle`: chuyển đổi cả kết quả thành công và thất bại

Trong Java, chuỗi `CompletableFuture` không chỉ chuyển đổi giá trị khi tác vụ thành công; nó còn cần một cách biểu diễn kết quả khi tác vụ **thất bại**. Phương thức **`handle`** nhận *cả hai đường hoàn thành* của một stage: đường bình thường mang giá trị và đường ngoại lệ mang `Throwable`. Handler có thể trả một giá trị mới cùng hoặc khác kiểu, từ đó tạo một stage tiếp theo.

Chủ đề này thuộc **Java Core – Exception / CompletableFuture**. Các ví dụ dùng **Java 17+**. Sau bài học, bạn sẽ biết khi nào nên dùng `handle`, cách tránh che mất lỗi, cách xử lý `CompletionException`/hủy, và cách kết hợp `handle` với những stage khác.

## 1. Mô hình cốt lõi: một callback, hai đường vào

Một `CompletableFuture<T>` có thể:

- **Hoàn thành bình thường** với giá trị kiểu `T` (giá trị đó có thể là `null`).
- **Hoàn thành ngoại lệ** với một nguyên nhân thất bại.
- **Bị hủy**; với `CompletableFuture`, hủy được biểu diễn như một kiểu hoàn thành ngoại lệ có `CancellationException`.

`handle` đăng ký một callback có hai tham số:

```java
CompletableFuture<U> next = source.handle((value, error) -> {
    // Trả về U, tạo kết quả mới cho next.
});
```

Với `source` kiểu `CompletableFuture<T>`, kiểu callback về mặt khái niệm là `BiFunction<? super T, Throwable, ? extends U>`. Chữ ký trên `CompletionStage<T>` có dạng:

```java
<U> CompletionStage<U> handle(
        java.util.function.BiFunction<? super T, Throwable, ? extends U> fn);
```

Trong API `CompletableFuture<T>`, kết quả của overload tương ứng là `CompletableFuture<U>`.

| Trạng thái của source | `value` trong handler | `error` trong handler |
|---|---|---|
| Hoàn thành bình thường với giá trị khác `null` | Giá trị `T` | `null` |
| Hoàn thành bình thường với `null` | `null` | `null` |
| Hoàn thành ngoại lệ | `null` | `Throwable` khác `null` |
| Đã bị hủy | `null` | Lỗi biểu diễn hủy, thường là `CancellationException` |

**Muốn phân biệt thành công và thất bại, kiểm tra `error == null`, không chỉ kiểm tra `value == null`.** Một tác vụ hoàn thành thành công hoàn toàn có thể trả `null`.

Một sơ đồ nhỏ:

```text
CompletableFuture<T> nguồn
          |
          +-- success(value: T) ------+
          |                           |
          +-- failure(Throwable) -----+--> handle((value, error) -> U)
                                                |
                              +-----------------+------------------+
                              |                                    |
                         return U                            throw exception
                              |                                    |
                   stage tiếp theo thành công          stage tiếp theo thất bại
```

Lời gọi `handle(...)` **không chặn luồng** để chờ kết quả. Nó trả ngay stage phụ thuộc. Khi source hoàn tất, callback được thực thi theo quy tắc scheduling của phương thức; lệnh `join()` hoặc `get()` đặt **sau đó** mới là điểm caller có thể phải chờ.

## 2. Ví dụ cơ bản: cùng một `handle` xử lý hai trường hợp

Tạo tệp `HandleBasicsDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class HandleBasicsDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> success =
                CompletableFuture.completedFuture(42);

        CompletableFuture<Integer> failure =
                CompletableFuture.failedFuture(
                        new IllegalArgumentException("id không hợp lệ"));

        System.out.println(summarize(success).join());
        System.out.println(summarize(failure).join());
    }

    static CompletableFuture<String> summarize(
            CompletableFuture<Integer> source) {
        return source.handle((value, error) -> {
            if (error == null) {
                return "Thành công: " + value;
            }

            Throwable root = unwrap(error);
            return "Thất bại: "
                    + root.getClass().getSimpleName()
                    + " - " + root.getMessage();
        });
    }

    static Throwable unwrap(Throwable error) {
        while (error instanceof CompletionException
                && error.getCause() != null) {
            error = error.getCause();
        }
        return error;
    }
}
```

Chạy:

```bash
javac HandleBasicsDemo.java
java HandleBasicsDemo
```

Kết quả chính xác:

```text
Thành công: 42
Thất bại: IllegalArgumentException - id không hợp lệ
```

Giải thích:

1. `completedFuture(42)` tạo stage đã hoàn thành bình thường. Handler nhận `value=42`, `error=null`.
2. `failedFuture(new IllegalArgumentException(...))` tạo stage đã hoàn thành ngoại lệ. Handler nhận một `Throwable`; hàm `unwrap` gỡ các lớp `CompletionException` khi có, rồi lấy nguyên nhân gốc.
3. Trong cả hai nhánh, handler **trả `String`**. Stage kết quả vì vậy là `CompletableFuture<String>` và được hoàn thành **bình thường**.
4. Không có tác vụ nào được submit vào thread pool trong ví dụ này; hai source đã hoàn thành sẵn. `handle` vẫn có tác dụng chuyển đổi outcome như khi được đăng ký trước lúc source hoàn tất.

`handle` không làm thay đổi sự thật rằng source ban đầu đã thất bại. Nó tạo **một stage mới** có trạng thái độc lập. Nếu `handle` trả fallback thành công, caller đọc stage mới bằng `join()` sẽ có kết quả; caller đọc lại source lỗi vẫn gặp lỗi.

## 3. `handle` chuyển cả kiểu dữ liệu, không chỉ phục hồi lỗi

Kiểu `T` của source và kiểu `U` mà handler trả về **không cần giống nhau**. Đây là điểm khiến `handle` phù hợp để chuyển mọi outcome sang DTO kết quả, thông điệp UI, audit event, `Result<T>` hoặc response thuộc một hợp đồng ổn định.

Ví dụ `CompletableFuture<String>` chuyển thành `CompletableFuture<Outcome>` (chạy độc lập trên Java 17).

Tệp `HandleResultTypeDemo.java`:

```java
import java.util.Locale;
import java.util.concurrent.CompletableFuture;

public class HandleResultTypeDemo {
    record Outcome(boolean success, String text) {}

    static CompletableFuture<Outcome> convert(
            CompletableFuture<String> source) {
        return source.handle((value, error) -> {
            if (error != null) {
                return new Outcome(false, "không lấy được dữ liệu");
            }
            if (value == null) {
                return new Outcome(true, "<rỗng>");
            }
            return new Outcome(true,
                    value.trim().toUpperCase(Locale.ROOT));
        });
    }

    public static void main(String[] args) {
        Outcome a = convert(
                CompletableFuture.completedFuture(" java ")).join();
        Outcome b = convert(
                CompletableFuture.completedFuture(null)).join();
        Outcome c = convert(
                CompletableFuture.failedFuture(
                        new IllegalStateException("offline"))).join();

        System.out.println(a.success() + " | " + a.text());
        System.out.println(b.success() + " | " + b.text());
        System.out.println(c.success() + " | " + c.text());
    }
}
```

Lệnh:

```bash
javac HandleResultTypeDemo.java
java HandleResultTypeDemo
```

Đầu ra:

```text
true | JAVA
true | <rỗng>
false | không lấy được dữ liệu
```

Ở nhánh thành công có giá trị `null`, `error` vẫn là `null`. Đây là một kết quả hợp lệ, được chuyển thành `Outcome(true, "<rỗng>")`. Ở nhánh thất bại, `value` không có ý nghĩa và handler chọn kết quả hợp đồng `Outcome(false, ...)`.

Trong ứng dụng thực, hãy cân nhắc liệu `Outcome(false, "không lấy được dữ liệu")` đã chứa đủ thông tin cho người gọi hay chưa. Nếu cần truy vết, có thể lưu mã lỗi được phân loại, correlation ID và ghi log có giữ cause; không nên âm thầm biến mọi lỗi hạ tầng nghiêm trọng thành một chuỗi dự phòng.

## 4. Giá trị mới hay ngoại lệ mới: stage phụ thuộc có kết thúc thế nào?

Khi callback `handle` chạy:

- **`return U`**: stage phụ thuộc hoàn thành bình thường với `U` (kể cả `null` nếu kiểu cho phép).
- **`throw exception`**: stage phụ thuộc hoàn thành ngoại lệ; `join()` thường ném `CompletionException`, `get()` thường ném `ExecutionException` khi quan sát thất bại.
- **Source trước đó thất bại nhưng handler trả fallback**: stage mới thành công; source cũ vẫn thất bại.
- **Source trước đó thành công nhưng handler ném lỗi**: stage mới thất bại dù source cũ thành công.

Một ví dụ đơn giản để thấy handler có thể tạo lỗi:

```java
CompletableFuture<Integer> source =
        CompletableFuture.completedFuture(5);

CompletableFuture<Integer> next =
        source.handle((value, error) -> {
            throw new IllegalStateException("lỗi bên trong handle");
        });

// next.join() sẽ hoàn thành bằng ngoại lệ, không trả số 5.
```

Đây là **mảnh mã minh họa**, đặt trong phương thức có các import `CompletableFuture` phù hợp; không phải tệp Java độc lập. Nếu gọi `next.join()` ở đây và không bắt ngoại lệ, luồng caller có thể kết thúc bằng `CompletionException` có cause là `IllegalStateException`.

**Không được suy rằng có `handle` là mọi lỗi đã được khôi phục.** Callback chỉ khôi phục một lỗi khi nhánh lỗi trả giá trị bình thường. Nếu callback tiếp tục ném, chuỗi downstream vẫn là một đường lỗi.

## 5. Ví dụ chuỗi: lỗi từ một stage ở giữa được `handle` chuyển đổi

Tạo tệp `HandleChainDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class HandleChainDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> parsed =
                CompletableFuture.completedFuture("abc")
                        .thenApply(Integer::parseInt);

        CompletableFuture<String> report = parsed.handle(
                (number, error) -> {
                    if (error != null) {
                        return "parse failed";
                    }
                    return "value = " + number;
                });

        System.out.println(report.join());

        try {
            parsed.join();
        } catch (CompletionException e) {
            System.out.println("source cause = "
                    + e.getCause().getClass().getSimpleName());
        }
    }
}
```

Biên dịch:

```bash
javac HandleChainDemo.java
java HandleChainDemo
```

Output:

```text
parse failed
source cause = NumberFormatException
```

`thenApply(Integer::parseInt)` chạy trên chuỗi `"abc"` rồi ném `NumberFormatException`. Stage `parsed` hoàn thành ngoại lệ; `report` nhờ `handle` chuyển thất bại ấy thành thông điệp bình thường. Khi `parsed.join()` được gọi riêng, lỗi cũ vẫn có thể quan sát qua `CompletionException`.

Ví dụ cho thấy vì sao nên giữ tham chiếu tới stage **đúng cấp** mà mình muốn đọc. `parsed` và `report` không phải một kết quả bị viết đè; chúng là hai stage liên quan theo đồ thị phụ thuộc.

## 6. `handle`, `exceptionally`, `whenComplete`, `thenApply`: dùng đúng mục đích

Bốn phương thức thường đứng gần nhau nhưng hợp đồng khác nhau.

| Phương thức | Chạy khi source thành công? | Chạy khi source thất bại? | Có thể đổi `T` thành kiểu `U`? | Mục đích thường gặp |
|---|---|---|---|---|
| `thenApply(fn)` | Có | Không, nhánh callback bị bỏ qua | Có | Chuyển giá trị thành công |
| `exceptionally(fn)` | Không | Có | Không: trả kết quả cùng kiểu `T` | Cấp fallback cho trường hợp lỗi |
| `whenComplete(action)` | Có | Có | Không: bảo toàn kiểu kết quả của source | Quan sát outcome, log, metrics, cleanup |
| `handle(fn)` | Có | Có | **Có** | Chuẩn hóa outcome, chuyển giá trị hoặc phục hồi lỗi |

Có thể biểu diễn ý định:

```text
Chỉ đổi giá trị khi thành công        → thenApply
Chỉ phục hồi thất bại                 → exceptionally
Chỉ quan sát/log cả hai kết quả       → whenComplete
Biến cả hai kết quả thành kiểu mới    → handle
```

`exceptionally` trả về fallback loại `T` khi thất bại, không chạy hàm chuyển lỗi nếu source thành công. `whenComplete` nhận `(value, error)` nhưng callback kiểu `BiConsumer` không có giá trị trả về để thay kết quả. Nó hữu ích khi đo metric hoặc log; nếu action trong `whenComplete` ném ngoại lệ, stage mới có thể thất bại (trong trường hợp source đã lỗi, nguyên nhân lỗi ban đầu được ưu tiên theo hợp đồng). Vì vậy `whenComplete` cũng không hoàn toàn “vô tác dụng phụ” đối với trạng thái downstream.

Ví dụ so sánh rút gọn (mảnh mã minh họa):

```java
CompletableFuture<Integer> source =
        CompletableFuture.failedFuture(
                new IllegalArgumentException("bad"));

CompletableFuture<Integer> fallback =
        source.exceptionally(error -> -1);

CompletableFuture<String> summary =
        source.handle((value, error) ->
                error == null ? "value=" + value : "failed");

CompletableFuture<Integer> observed =
        source.whenComplete((value, error) -> {
            System.out.println("observed failure: " + (error != null));
        });
```

`fallback.join()` trả `-1`, `summary.join()` trả `"failed"`; `observed` vẫn chứa thất bại từ source nên `observed.join()` sẽ ném. Nếu chỉ cần ghi log mà giữ trạng thái lỗi nguyên vẹn, `whenComplete` thường thể hiện ý định chính xác hơn.

### Vì sao không đặt `handle` ở khắp mọi nơi?

Nếu mỗi bước đều dùng `handle` để trả giá trị mặc định, các lỗi có thể bị che lấp và downstream tưởng rằng dữ liệu hợp lệ. Giữ trạng thái lỗi tự lan xuống các stage cho tới ranh giới có trách nhiệm quyết định cách phục hồi. Dùng `handle` khi thật sự cần **xem xét cả giá trị lẫn lỗi**, thường ở ranh giới trả response, hiển thị thông báo, lưu outcome hoặc chọn chiến lược fallback.

## 7. `CompletionException` và nguyên nhân gốc

`CompletableFuture` thường dùng `CompletionException` (unchecked) để bọc lỗi từ stage bất đồng bộ. Nếu một stage kết thúc thất bại vì `IllegalStateException`, tham số `error` trong `handle` **có thể là ngoại lệ gốc hoặc một `CompletionException` bao ngoài**, tùy nguồn lỗi và cách stage được hoàn thành.

Ví dụ:

- `CompletableFuture.failedFuture(new IOException(...))` có thể đưa cause trực tiếp tới handler.
- Một callback như `thenApply` ném ngoại lệ có thể làm stage tiếp theo được đánh dấu lỗi qua cơ chế bọc `CompletionException`.
- `future.join()` báo lỗi bằng `CompletionException` trong các trường hợp lỗi thông thường, còn `future.get()` dùng `ExecutionException`. Đây là cơ chế *quan sát lỗi ở caller*, không phải cam kết rằng tham số `error` trong mọi handler luôn mang cùng đúng một lớp wrapper.

Nếu cần phân loại chính xác, bóc `CompletionException` **chỉ khi có cause**:

```java
static Throwable unwrapCompletion(Throwable failure) {
    while (failure instanceof java.util.concurrent.CompletionException
            && failure.getCause() != null) {
        failure = failure.getCause();
    }
    return failure;
}
```

Đây là **phương thức có thể chèn vào một class Java**; tham số đầu vào `failure` phải khác `null`. Không tự động bóc mọi `RuntimeException` hoặc mọi nguyên nhân sâu nhất, vì wrapper khác có thể mang ý nghĩa miền nghiệp vụ. Cần cẩn thận hơn khi xử lý `CancellationException` và `Error`.

Cách dùng phân loại:

```java
return source.handle((value, error) -> {
    if (error == null) {
        return new Outcome(true, value);
    }

    Throwable cause = unwrapCompletion(error);
    if (cause instanceof java.io.IOException) {
        return new Outcome(false, "I/O tạm thời không khả dụng");
    }

    throw new java.util.concurrent.CompletionException(cause);
});
```

Đoạn trên là **mẫu không độc lập**: giả định `source`, `Outcome` và phương thức `unwrapCompletion` đã được khai báo, và các kiểu giá trị tương thích. Chỉ phục hồi trường hợp đã có chính sách; trường hợp còn lại tiếp tục báo lỗi. Khi tạo ngoại lệ mới, **giữ cause** để stack trace gốc không bị mất. Không chuyển mọi lỗi, đặc biệt `Error` nghiêm trọng, thành kết quả “thành công giả”.

## 8. Cancellation: `handle` có nhận trường hợp hủy không?

Có. Với `CompletableFuture<T>`, gọi `cancel(...)` thành công làm nó hoàn thành ngoại lệ với `CancellationException`. Vì vậy một `handle` đăng ký trên source có thể nhận đường lỗi và quyết định trả fallback. Tuy nhiên, hủy là một **tín hiệu điều khiển vòng đời**, không nhất thiết là lỗi nghiệp vụ thông thường.

Ví dụ độc lập `HandleCancellationDemo.java`:

```java
import java.util.concurrent.CompletableFuture;

public class HandleCancellationDemo {
    public static void main(String[] args) {
        CompletableFuture<String> source = new CompletableFuture<>();

        CompletableFuture<String> recovered =
                source.handle((value, error) ->
                        error == null ? value : "fallback");

        boolean canceled = source.cancel(false);

        System.out.println("source cancel accepted = " + canceled);
        System.out.println("source canceled = " + source.isCancelled());
        System.out.println("recovered = " + recovered.join());
        System.out.println("recovered canceled = "
                + recovered.isCancelled());
    }
}
```

Chạy:

```bash
javac HandleCancellationDemo.java
java HandleCancellationDemo
```

Output:

```text
source cancel accepted = true
source canceled = true
recovered = fallback
recovered canceled = false
```

Handler đã xử lý ngoại lệ hủy bằng một giá trị fallback, nên stage phụ thuộc `recovered` hoàn thành bình thường. Trong khi đó `source` vẫn giữ trạng thái hủy.

Điểm quan trọng: **hủy stage nguồn không tự chứng minh luồng tính toán nền đã dừng**. `CompletableFuture.cancel(boolean)` dùng cùng hành vi bất kể `mayInterruptIfRunning` là `true` hay `false`; theo hợp đồng, tham số đó không dùng để điều khiển ngắt tác vụ trong chính `CompletableFuture`. Nếu cần dừng tài nguyên thực sự, phải có cơ chế điều phối riêng với task hoặc executor.

Nếu ứng dụng xem cancellation là tín hiệu không được phép che, hãy **phân loại** `CancellationException` và truyền trạng thái phù hợp cho người gọi thay vì trả fallback bất kể nguyên nhân. Chính sách khôi phục lỗi mạng thường khác chính sách hủy theo yêu cầu người dùng.

## 9. `handle` không nuốt interrupt của luồng đang chờ

Có hai bối cảnh cần phân biệt:

1. Một worker trong `supplyAsync(...)` bị interrupt khi đang gọi `sleep`, `take` hoặc thao tác chờ khác. Nếu worker ném ngoại lệ ra ngoài, source có thể hoàn thành ngoại lệ; `handle` ở downstream nhận `Throwable` biểu diễn thất bại đó.
2. Caller đang gọi `future.get()` hoặc `future.get(timeout, unit)` rồi **chính caller bị interrupt**. Caller nhận trực tiếp `InterruptedException`; điều này **không tự động chuyển** source thành exceptional completion, và không mặc nhiên kích hoạt `handle` như một lỗi của source.

Ví dụ kết hợp hai hướng (mảnh mã minh họa):

```java
CompletableFuture<String> normalized =
        source.handle((value, error) ->
                error == null ? value : "nguồn thất bại");

try {
    String result = normalized.get();
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    // Luồng hiện tại bị ngắt khi chờ; xử lý vòng đời của caller.
} catch (java.util.concurrent.ExecutionException failure) {
    // Chính normalized thất bại, ví dụ handler đã ném ngoại lệ.
}
```

Đoạn này dùng biến `source` kiểu `CompletableFuture<String>` đã có sẵn trong một phương thức. Việc gọi `get()` để chờ khác với callback `handle`: **`handle` mô tả chuyển đổi outcome của stage**, còn `get()` là thao tác chờ của thread đang gọi.

## 10. `handle()` và `handleAsync()`: chọn luồng thực thi callback

Ba overload trong `CompletableFuture`:

```java
<U> CompletableFuture<U> handle(
        java.util.function.BiFunction<? super T, Throwable, ? extends U> fn);

<U> CompletableFuture<U> handleAsync(
        java.util.function.BiFunction<? super T, Throwable, ? extends U> fn);

<U> CompletableFuture<U> handleAsync(
        java.util.function.BiFunction<? super T, Throwable, ? extends U> fn,
        java.util.concurrent.Executor executor);
```

`handle` thường có thể chạy callback ngay trong luồng hoàn thành source hoặc trong luồng đang đăng ký callback nếu source đã hoàn tất; **không được dựa vào một thread cố định**. `handleAsync` dùng cơ chế thực thi bất đồng bộ mặc định của `CompletableFuture` (thường là `ForkJoinPool.commonPool()` trong điều kiện phù hợp). Overload có `Executor` đưa callback vào executor do bạn chỉ định.

Tệp `HandleAsyncExecutorDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class HandleAsyncExecutorDemo {
    public static void main(String[] args) {
        ExecutorService handlers = Executors.newSingleThreadExecutor(
                task -> new Thread(task, "handler-worker"));

        try {
            CompletableFuture<Integer> source =
                    CompletableFuture.completedFuture(10);

            CompletableFuture<String> result =
                    source.handleAsync((value, error) ->
                            Thread.currentThread().getName()
                                    + ": " + value,
                            handlers);

            System.out.println(result.join());
        } finally {
            handlers.shutdown();
        }
    }
}
```

Chạy:

```bash
javac HandleAsyncExecutorDemo.java
java HandleAsyncExecutorDemo
```

Kết quả:

```text
handler-worker: 10
```

Handler chạy trong executor có thread được đặt tên rõ ràng, nên output ổn định. Đây là ví dụ về **chỉ định nơi thực thi callback**, không phải bắt source chạy lại. Source đã hoàn tất trước khi đăng ký handler.

### Khi nào dùng biến thể `Async`?

- Handler có xử lý đủ nặng để không nên chạy trên thread hoàn thành source.
- Muốn cô lập tài nguyên CPU, giới hạn số callback đồng thời hoặc tách loại workload.
- Muốn kiểm soát lifecycle executor và giám sát callback trong môi trường dịch vụ.

Không dùng `handleAsync` như một giải pháp cho mọi lỗi blocking. Nếu bên trong callback lại gọi `.join()` chờ một stage đang cần chính executor một luồng đó để chạy, có thể gặp starvation/deadlock. Cũng phải cân nhắc chi phí chuyển thread, queue đầy, executor bị shutdown hoặc từ chối task: trường hợp không thể lập lịch có thể khiến stage phụ thuộc hoàn thành ngoại lệ.

**Giữ handler nhanh, không blocking khi có thể.** Nếu cần chuỗi tác vụ bất đồng bộ mới, dùng các phép ghép stage phù hợp như `thenCompose`, tránh chờ đồng bộ trong callback.

## 11. `handle` trả về một Future khác có thể tạo lồng kiểu

Giả sử sau khi lỗi, chương trình muốn gọi một nguồn fallback **bất đồng bộ**. Nếu handler trả một `CompletableFuture<U>`, thì kết quả của `handle` có thể là `CompletableFuture<CompletableFuture<U>>`: một Future chứa một Future khác.

Ví dụ **mảnh mã minh họa** (phương thức `fallbackAsync()` do ứng dụng cung cấp):

```java
CompletableFuture<CompletableFuture<String>> nested =
        source.handle((value, error) -> {
            if (error == null) {
                return CompletableFuture.completedFuture(value);
            }
            return fallbackAsync();
        });

CompletableFuture<String> flat =
        nested.thenCompose(java.util.function.Function.identity());
```

Ở đây `source` là `CompletableFuture<String>` và `fallbackAsync()` trả `CompletableFuture<String>`. `thenCompose(Function.identity())` “làm phẳng” lớp Future bên ngoài. Nếu không, người gọi có thể nhầm tưởng `nested.join()` đã đợi xong cả tác vụ fallback; thực ra nó chỉ trả Future bên trong.

Khi cần phục hồi theo một tác vụ bất đồng bộ, có thể cân nhắc API như `exceptionallyCompose(...)` (Java 12+) để chỉ xử lý nhánh lỗi bằng stage mới, hoặc dùng `handle(...).thenCompose(...)` nếu phải xử lý cả hai đường. Tránh gọi `.join()` trực tiếp trong handler chỉ để lấy kết quả fallback.

## 12. Kết hợp `handle` với nhiều bước và vị trí đặt handler

Xem chuỗi sau (mảnh mã minh họa, các hàm `loadUser()`, `validateUser(...)`, `toView(...)` được ứng dụng định nghĩa):

```java
CompletableFuture<UserView> response =
        loadUser()
                .thenApply(this::validateUser)
                .thenApply(this::toView)
                .handle((view, error) -> {
                    if (error == null) {
                        return view;
                    }
                    return UserView.unavailable();
                });
```

`handle` ở cuối xử lý lỗi phát sinh từ **bất kỳ stage upstream nào** trong chuỗi phụ thuộc trực tiếp đó, đồng thời có thể chuẩn hóa giá trị thành công. Tuy nhiên nó cũng có thể che lỗi lập trình (ví dụ `NullPointerException` do bug) nếu luôn trả `unavailable()`. Trong API production, cần phân loại lỗi có thể phục hồi và lỗi phải ghi nhận/propagate.

Đặt handler trước hay sau biến đổi làm khác phạm vi lỗi mà nó quan sát:

```text
load → handle → validate
         ↑         ↑
   xử lý lỗi load   lỗi validate vẫn có thể làm downstream thất bại

load → validate → handle
                     ↑
            xử lý cả lỗi load và validate
```

Không lạm dụng một `handle` tổng ở cuối chỉ để biến mọi exception thành HTTP 200 hoặc trạng thái “thành công”. Nếu đầu vào thiếu hoặc lỗi logic, việc trả fallback quá rộng sẽ làm việc điều tra khó hơn.

## 13. Logging và quan sát thất bại mà không che lỗi

Nếu chỉ cần log hoặc đo thời gian, `whenComplete` thường phù hợp hơn:

```java
CompletableFuture<Data> observed =
        fetchData().whenComplete((data, error) -> {
            if (error == null) {
                metrics.success();
            } else {
                metrics.failure(error);
            }
        });
```

Đây là **mảnh mã minh họa** với `Data`, `fetchData()` và `metrics` do ứng dụng định nghĩa. `observed` giữ giá trị hoặc tình trạng lỗi của source, ngoại trừ khi chính callback tạo lỗi theo quy tắc của `whenComplete`.

Dùng `handle` cho kết quả nghiệp vụ:

```java
CompletableFuture<ApiResult> result =
        fetchData().handle((data, error) -> {
            if (error != null) {
                return ApiResult.failed(error);
            }
            return ApiResult.ok(data);
        });
```

Đây cũng là mảnh minh họa, giả định kiểu `ApiResult` và hàm `fetchData()` hợp lệ. Nếu `ApiResult.failed(error)` là một giá trị hoàn thành bình thường, downstream không còn thấy exceptional completion trừ khi kiểm tra trường trạng thái trong `ApiResult`. Đó là **sự chuyển đổi có chủ đích của hợp đồng**, cần được thống nhất ở lớp gọi.

Một chiến lược tốt là log một lần ở ranh giới có đủ ngữ cảnh; giữ cause khi chuyển sang lỗi ứng dụng; tránh mỗi tầng `handle` lại log cùng lỗi rồi trả fallback. Dữ liệu cần bảo mật không nên đưa nguyên message của exception nội bộ ra response công khai.

## 14. Lưu ý về đồng thời, timeout và vòng đời

`handle` không tự tạo timeout, không tự ngắt công việc nguồn và cũng không bảo đảm callback được gọi đúng một lần theo một thứ tự toàn cục giữa nhiều stage độc lập. Với **một stage phụ thuộc được tạo bởi một lời gọi `handle`**, callback được áp dụng khi source hoàn tất và kết quả hoàn thành stage phụ thuộc; đừng thiết kế ứng dụng dựa vào thứ tự callback giữa các stage sibling.

Một số tình huống cần thận trọng:

- **Source chưa bao giờ hoàn tất:** handler không được chạy, stage kết quả cũng có thể không hoàn tất. Có thể đặt timeout ở ranh giới thích hợp, ví dụ `orTimeout(...)` hoặc timeout của thao tác gốc.
- **Source bị hủy:** `handle` có thể thấy đường lỗi và trả fallback, nhưng điều đó không chứng minh worker hoặc tài nguyên đã dừng.
- **Handler chạy quá lâu:** stage downstream bị chậm; trên `handle` đồng bộ nó còn có thể chiếm thread đang hoàn thành source.
- **Handler chờ chéo trong executor nhỏ:** có nguy cơ starvation hoặc deadlock, nhất là khi worker chờ một tác vụ phải chạy trên cùng executor đã đầy.
- **Callback ném unchecked exception/Error:** stage mới có thể thất bại; giữ dấu vết nguyên nhân thay vì nuốt toàn bộ lỗi.
- **Thay đổi trạng thái chung:** callback có thể chạy ở thread khác thời điểm khác; dùng biến bất biến, thiết kế thread-safe và cơ chế đồng bộ phù hợp.

`CompletableFuture.orTimeout(duration, unit)` tạo exceptional completion với `TimeoutException` khi hết hạn và áp dụng lên chính future được gọi, không chỉ một “bản sao” độc lập. `completeOnTimeout(value, duration, unit)` đưa giá trị bình thường sau timeout khi chưa hoàn tất. Handler đặt sau hai phương thức này sẽ thấy outcome **sau chính sách timeout đã chọn**. Hãy phân biệt timeout của nguồn, timeout của caller khi chờ `get`, và việc thực sự hủy tác vụ nền.

## 15. Các lỗi phổ biến với `handle`

### 15.1. Chỉ kiểm tra `value == null`

Sai:

```java
source.handle((value, error) -> {
    if (value == null) {
        return "FAILED";
    }
    return value.toString();
});
```

Vì source **thành công với `null`** cũng đi vào nhánh `"FAILED"`. Sửa bằng `if (error != null)` để nhận lỗi; xử lý `value == null` sau đó theo hợp đồng dữ liệu.

### 15.2. Quên rằng source gốc không được sửa

```java
CompletableFuture<Integer> original =
        CompletableFuture.failedFuture(new IllegalArgumentException());

CompletableFuture<Integer> recovered =
        original.handle((value, error) -> error == null ? value : 0);
```

`recovered.join()` trả `0`, còn `original.join()` vẫn ném. Đừng mong một handler phía sau sẽ sửa trạng thái của object nguồn.

### 15.3. Dùng `handle` thay `whenComplete` chỉ để log

`handle` thích hợp khi muốn **trả một outcome mới**. Nếu dùng `handle` rồi vô tình trả `null` trong nhánh lỗi, có thể che mất lỗi và làm downstream thất bại muộn hơn bởi `NullPointerException`. Dùng `whenComplete` cho mục tiêu quan sát, hoặc truyền lỗi tiếp có chủ đích.

### 15.4. Nuốt mọi lỗi thành fallback

Nếu `Throwable` nhận được là bug trong code chuyển đổi hoặc `Error` nghiêm trọng, fallback có thể khiến người vận hành không nhận ra lỗi. Chỉ phục hồi nguyên nhân có chính sách rõ; các nguyên nhân còn lại nên được truyền tiếp giữ cause, hoặc chuyển thành outcome lỗi tường minh.

### 15.5. Giả sử `error` luôn là lớp exception nghiệp vụ trực tiếp

Trong chuỗi bất đồng bộ, `CompletionException` có thể bọc nguyên nhân thật. Hãy phân loại sau khi kiểm tra wrapper phù hợp, không ép `(MyBusinessException) error` một cách mù quáng.

### 15.6. Gọi `join()` trong handler để chạy “bất đồng bộ”

`join()` có thể chặn thread callback; trong thread pool nhỏ, nó có thể đợi chính công việc chưa có worker để chạy. Nếu handler cần bắt đầu một stage khác, cân nhắc trả stage rồi flatten với `thenCompose`.

### 15.7. Xử lý cancellation giống mọi lỗi hạ tầng

Hủy do người dùng hoặc shutdown không nhất thiết cần thử lại như lỗi mạng. Phải có chính sách riêng cho `CancellationException`, trạng thái hủy và việc dọn tài nguyên, nhất là khi callback biến đường lỗi thành thành công.

### 15.8. Coi `handleAsync` là lời hứa về thread cố định

Overload không có executor chạy theo cơ chế bất đồng bộ mặc định; nó không cam kết một tên thread. Nếu cần ranh giới tài nguyên và điều phối rõ, hãy truyền executor riêng và đóng nó đúng vòng đời.

## 16. Checklist khi sử dụng `handle`

Trước khi viết handler, hãy xác nhận:

1. **Mục đích:** cần chuyển *cả success lẫn failure* hay chỉ muốn log (`whenComplete`), xử lý lỗi (`exceptionally`) hoặc chuyển giá trị (`thenApply`)?
2. **Trạng thái success:** có cho phép `value=null` không? Có nên trả đúng kiểu `U` theo hợp đồng?
3. **Trạng thái failure:** `Throwable` có wrapper không? Có cần phân loại lỗi, giữ cause hoặc tiếp tục propagate?
4. **Cancellation/timeout:** hai sự kiện này có phải lỗi nên phục hồi bằng fallback hay cần giữ trạng thái hủy/hết hạn?
5. **Bảo toàn source:** code downstream đang đợi `source` hay stage mới do `handle` trả về?
6. **Threading:** handler có blocking, CPU nặng hoặc gọi dịch vụ khác không? Có cần `handleAsync(..., executor)` hoặc ghép bằng `thenCompose`?
7. **Quan sát:** lỗi đã được log ở đúng một ranh giới có ngữ cảnh chưa? Có làm lộ thông tin nội bộ ra response?
8. **Kiểm thử:** có đủ các ca thành công, thành công với `null`, lỗi gốc, lỗi bọc `CompletionException`, handler tự ném lỗi, hủy và timeout?

**Điểm nhớ lâu:** `handle((value, error) -> result)` là phép **chuyển đổi outcome** của một stage, chạy cho cả hoàn thành bình thường và ngoại lệ. Kiểm tra `error == null` để nhận biết thành công, trả `U` để tạo stage thành công mới, hoặc ném lỗi để giữ đường thất bại. Stage nguồn giữ trạng thái của chính nó; việc phục hồi, hủy hay xử lý exception ở stage sau luôn là quyết định có chủ đích.
