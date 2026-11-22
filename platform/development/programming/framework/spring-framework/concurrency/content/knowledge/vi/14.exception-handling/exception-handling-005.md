# exceptionally(), handle() và whenComplete() trong CompletableFuture và Spring @Async

Khi lập trình đồng thời với Spring Framework, một phương thức `@Async` có thể trả về `CompletableFuture<T>` để caller nhận kết quả sau hoặc ghép các bước xử lý. Nhưng tác vụ có thể lỗi: truy vấn cơ sở dữ liệu thất bại, dịch vụ ngoài timeout, tham số không hợp lệ, hoặc callback trong chuỗi pipeline tự ném exception. Ba API **`exceptionally()`**, **`handle()`** và **`whenComplete()`** giải quyết ba nhu cầu khác nhau: **phục hồi lỗi**, **biến đổi kết quả bất kể thành công hay thất bại**, và **quan sát kết quả mà vẫn giữ nguyên trạng thái hoàn thành**.

Điểm quan trọng nhất: cả ba API tạo **một completion stage phụ thuộc mới**. Chúng không tự sửa kết quả của stage gốc. Thứ tự gắn callback quyết định callback nhìn thấy kết quả **trước** hay **sau** khi đã phục hồi lỗi. Bài học thuộc nhóm **Xử lý ngoại lệ**, tập trung vào hợp đồng Java 17+ và cách sử dụng trong ứng dụng Spring `@Async`.

## 1. Bạn cần nắm được điều gì?

Sau bài này, bạn có thể:

- Giải thích `CompletableFuture` hoàn thành thành công, hoàn thành lỗi hoặc bị cancel, và exception được lưu/truyền giữa các stage như thế nào.
- Phân biệt chính xác thời điểm chạy, kiểu callback, kiểu trả về và khả năng phục hồi của `exceptionally`, `handle`, `whenComplete`.
- Biết lựa chọn API cho retry/fallback, đổi kiểu kết quả, logging/metrics, hoặc giữ lỗi để tầng trên quyết định.
- Hiểu trường hợp callback tự ném exception, đặc biệt quy tắc **giữ lỗi gốc của `whenComplete`** khi nguồn vốn đã lỗi.
- Biết rằng callback dạng không có hậu tố `Async` có thể chạy trên thread hoàn tất stage hoặc thread gắn callback, không có cam kết một worker mới.
- So sánh `get()`, `join()`, `ExecutionException`, `CompletionException` và `CancellationException`.
- Dùng trong Spring `@Async` có `ThreadPoolTaskExecutor`, phân biệt **lỗi trong task** với **rejection khi gửi task**.
- Tránh nuốt lỗi, fallback sai nghiệp vụ, logging trùng, blocking callback, mất thread context và suy luận sai về cancellation/timeout.
- Chạy được một ví dụ Java 17+ có kết quả xác định và viết test không phụ thuộc `Thread.sleep()`.

## 2. Nền tảng: CompletionStage và ba trạng thái kết thúc

`CompletableFuture<T>` thực hiện cả `Future<T>` và `CompletionStage<T>`. Một Future ban đầu có thể chưa hoàn thành; khi kết thúc, nó có thể:

1. **Hoàn thành bình thường:** chứa một giá trị `T`; giá trị này **có thể là `null`**.
2. **Hoàn thành ngoại lệ:** chứa một nguyên nhân thất bại, ví dụ `IllegalArgumentException` hoặc `IOException` đã được bọc ở mức phù hợp.
3. **Bị hủy:** `cancel(...)` của `CompletableFuture` về bản chất dẫn tới một dạng hoàn thành ngoại lệ với `CancellationException`.

Một giai đoạn có thể kết thúc thành công hoặc lỗi trong lúc một stage khác đang chờ nó:

~~~text
CompletableFuture<T> source
       |
       +--- completed normally (value T)
       |
       +--- completed exceptionally (Throwable)
       |
       +--- cancelled (CancellationException)
       |
       +--- dependent stage: callback tùy loại
                |
                +--- completed normally (T/U)
                |
                +--- completed exceptionally (old/new cause)
~~~

Một stage phụ thuộc được tạo bằng `thenApply` thường chỉ xử lý khi nguồn **thành công**. Nếu nguồn lỗi, callback xử lý giá trị không chạy; lỗi có thể lan tiếp trong pipeline. Ba phương thức trong chủ đề giúp định nghĩa rõ cách ứng dụng sẽ xử lý hoặc quan sát lỗi.

### Hai nguyên tắc trước khi viết callback

- **Kết quả `null` không đồng nghĩa thất bại.** Với `handle((value, error) -> ...)` hay `whenComplete((value, error) -> ...)`, kiểm tra `error == null` để biết nguồn thành công, không kiểm tra riêng `value == null`.
- **Stage gốc và stage mới khác nhau.** `CompletableFuture<Integer> recovered = source.exceptionally(...)` không “chữa” `source`; `source` vẫn có thể hoàn thành exceptionally trong khi `recovered` thành công với fallback.

## 3. Bảng so sánh quan trọng nhất

| Tiêu chí | `exceptionally(fn)` | `handle(fn)` | `whenComplete(action)` |
| --- | --- | --- | --- |
| Khi nào callback được gọi? | Chỉ khi nguồn hoàn thành **ngoại lệ** | Cả thành công lẫn lỗi | Cả thành công lẫn lỗi |
| Hàm callback | `Function<Throwable, ? extends T>` | `BiFunction<? super T, Throwable, ? extends U>` | `BiConsumer<? super T, ? super Throwable>` |
| Dữ liệu callback nhận | Exception | Giá trị hoặc `null`, cùng exception hoặc `null` | Giá trị hoặc `null`, cùng exception hoặc `null` |
| Callback có trả giá trị? | Có, phải phù hợp kiểu `T` | Có, cho phép chuyển sang kiểu `U` | Không, chỉ thực hiện side effect |
| Stage mới khi nguồn lỗi và callback trả bình thường | **Thành công với fallback** | **Thành công với giá trị mới** | **Vẫn lỗi như nguồn** |
| Stage mới khi nguồn thành công | Giữ nguyên giá trị nguồn; callback không chạy | Kết quả do callback tính toán | Giữ nguyên giá trị nguồn nếu action không lỗi |
| Có thể đổi kiểu `T -> U`? | Không, cùng kiểu `T` | Có | Không, cùng kiểu `T` |
| Có thể chỉ quan sát lỗi mà không “nuốt” lỗi? | Không tự nhiên; phải ném lại | Có nhưng dễ đổi semantics nếu trả fallback | **Có, lựa chọn phù hợp nhất** |
| Nếu callback tự ném lỗi | Stage mới thất bại vì callback | Stage mới thất bại vì callback | Nếu nguồn thành công, stage mới thất bại vì callback; nếu nguồn đã lỗi, lỗi nguồn được ưu tiên |
| Mục tiêu chính | Error recovery/fallback | Kết hợp success/failure, map kết quả | Logging, metric, tracing, cleanup nhẹ |

**Quy tắc ghi nhớ:** `exceptionally` giống một nhánh `catch` với giá trị thay thế; `handle` giống `try/catch` có tính toán giá trị cuối trên **mọi đường**; `whenComplete` giống một callback quan sát `finally` nhưng **không phải `finally` của Java ở mọi khía cạnh**: nếu observer tự lỗi trên đường thành công, stage mới cũng lỗi.

## 4. exceptionally(): chỉ chạy trên đường thất bại

Chữ ký trong `CompletableFuture<T>`:

~~~java
public CompletableFuture<T> exceptionally(
        java.util.function.Function<Throwable, ? extends T> fn)
~~~

Nếu stage nguồn thành công, `fn` **không chạy** và stage mới nhận cùng giá trị. Nếu nguồn thất bại (bao gồm cancel), `fn` chạy với `Throwable` của completion và trả một giá trị thay thế cùng kiểu `T`. Khi callback kết thúc bình thường, **stage mới trở thành thành công**, không còn giữ trạng thái lỗi trước đó.

Ví dụ Java 17:

~~~java
CompletableFuture<String> source =
        CompletableFuture.failedFuture(
                new IllegalStateException("service unavailable"));

CompletableFuture<String> fallback =
        source.exceptionally(error -> "cached-value");

System.out.println(fallback.join());             // cached-value
System.out.println(source.isCompletedExceptionally()); // true
~~~

Đây là **đoạn Java có thể đặt trong method với import `java.util.concurrent.CompletableFuture`**. Nó cho thấy việc phục hồi chỉ xảy ra ở `fallback`, còn `source` vẫn lỗi. Nếu exception handler tự ném exception thì stage `fallback` cũng kết thúc lỗi.

### Chỉ fallback khi nguyên nhân có thể xử lý

Một anti-pattern thường gặp:

~~~java
CompletableFuture<Order> safe =
        loadOrder(id).exceptionally(error -> new Order());
~~~

Đây là **mã minh họa chưa độc lập**, `Order`/`loadOrder` là thành phần ứng dụng. Nếu lỗi là mất kết nối DB, thông tin đơn hàng không tồn tại, bug lập trình hoặc lỗi bảo mật, trả đơn hàng rỗng có thể khiến hệ thống diễn giải sai. Nên xác định loại lỗi có thể phục hồi:

~~~java
CompletableFuture<Price> safe =
        priceClient.fetch(sku).exceptionally(error -> {
            Throwable cause = unwrapCompletion(error);
            if (cause instanceof PriceServiceUnavailableException) {
                return priceCache.getIfPresent(sku);
            }
            throw new java.util.concurrent.CompletionException(cause);
        });
~~~

Đây là **mã thiết kế minh họa trong ứng dụng**, cần định nghĩa `Price`, `PriceServiceUnavailableException`, `priceClient`, `priceCache` và helper `unwrapCompletion`. Fallback cache cũng có thể trả `null`; phải xác định chính sách nghiệp vụ nếu cache miss. Không tự động biến mọi exception thành giá trị mặc định.

### Thứ tự hồi phục lỗi

~~~java
CompletableFuture<Integer> recovered =
        CompletableFuture.<Integer>failedFuture(
                new IllegalArgumentException("bad"))
                .exceptionally(error -> 5)
                .thenApply(value -> value * 2);
~~~

`recovered.join()` bằng **10** vì `exceptionally` biến lỗi thành giá trị 5, sau đó `thenApply` có thể chạy. Nhưng nếu đặt `thenApply` **trước** `exceptionally`, khi nguồn lỗi thì `thenApply` bị bỏ qua và fallback sẽ là giá trị nhận trực tiếp ở `exceptionally`, không được nhân đôi.

## 5. handle(): xử lý cả thành công lẫn lỗi và cho phép đổi kiểu

Chữ ký điển hình:

~~~java
public <U> CompletableFuture<U> handle(
        java.util.function.BiFunction<? super T, Throwable, ? extends U> fn)
~~~

`handle` luôn nhận được kết quả hoặc lỗi của nguồn và có thể trả về giá trị **kiểu `U`**, nên rất phù hợp để biểu diễn một **Result object**, chuyển giá trị thành thông báo hoặc áp quy tắc fallback cho cả hai đường.

Ví dụ:

~~~java
CompletableFuture<Integer> number =
        CompletableFuture.completedFuture(42);

CompletableFuture<String> result =
        number.handle((value, error) -> {
            if (error != null) {
                return "failed";
            }
            return "value=" + value;
        });

System.out.println(result.join()); // value=42
~~~

Với nguồn lỗi, callback vẫn chạy và có thể trả `"failed"`; stage mới hoàn thành **bình thường**. Khi cần giữ lỗi cho caller, có thể ném lại một exception phù hợp thay vì vô điều kiện trả fallback.

### Phân biệt null với lỗi

~~~java
CompletableFuture<String> nullable =
        CompletableFuture.completedFuture(null);

CompletableFuture<String> state =
        nullable.handle((value, error) ->
                error == null ? "success-even-if-null" : "failed");
~~~

`state.join()` là `success-even-if-null`. Nếu dùng `value == null` để suy ra lỗi, ứng dụng sẽ làm sai với mọi API cho phép kết quả null và `CompletableFuture<Void>`, bởi task kiểu Void khi hoàn tất thành công thường có value null.

### Dùng handle để chuẩn hóa kết quả ứng dụng

Giả sử một API cần phân biệt trạng thái thay vì ném lỗi xuống tất cả các tầng, có thể tạo một lớp `Outcome<T>` chứa `value` hoặc `failure` rồi dùng:

~~~java
CompletableFuture<Outcome<Customer>> outcome =
        customerService.load(id)
                .handle((value, error) ->
                        error == null
                                ? Outcome.success(value)
                                : Outcome.failure(unwrapCompletion(error)));
~~~

Đây là **đoạn tích hợp**, cần các class `Outcome`, `Customer` và service thật; bản thân nó không biên dịch độc lập. Quan trọng là khi `handle` trả `Outcome.failure(...)` thì **stage ở cấp Future thành công**, nhưng **nghiệp vụ có thể thất bại**. Người tiêu thụ phải kiểm tra `Outcome`, không chỉ `isCompletedExceptionally()`.

### Khi handle tự ném exception

Nếu callback `handle` ném `IllegalStateException` trong bất kỳ nhánh nào, stage mới hoàn thành exceptionally bởi lỗi đó. Lỗi nguồn trước đây không tự được giữ nguyên nếu callback chọn ném lỗi mới. Vì thế nên thiết kế chuyển đổi exception cẩn thận, tránh che nguyên nhân ban đầu.

## 6. whenComplete(): quan sát và giữ nguyên kết quả hoặc lỗi nguồn

Chữ ký điển hình:

~~~java
public CompletableFuture<T> whenComplete(
        java.util.function.BiConsumer<? super T, ? super Throwable> action)
~~~

`whenComplete` được gọi cả khi thành công lẫn lỗi, nhưng callback **không trả giá trị**. Stage mới thường **mang cùng kết quả hoặc cùng thất bại** với nguồn. Điều này phù hợp cho logging, metrics, tracing, instrumentation và cleanup ngắn ở lúc công việc hoàn tất.

~~~java
CompletableFuture<String> original =
        CompletableFuture.completedFuture("ready");

CompletableFuture<String> observed =
        original.whenComplete((value, error) -> {
            if (error == null) {
                System.out.println("completed");
            } else {
                System.err.println("failed: " + error);
            }
        });
~~~

`observed.join()` vẫn là `"ready"`, miễn callback không lỗi. Nếu nguồn đã hoàn thành exceptionally, `observed.join()` cũng sẽ báo exception đó, ngay cả khi callback chỉ in log và không ném.

### Không dùng whenComplete để “trả fallback”

Sai kỳ vọng:

~~~java
CompletableFuture<Integer> result =
        failedIntegerFuture.whenComplete((value, error) -> {
            if (error != null) {
                System.out.println("Using default 0");
            }
        });
~~~

Đây là **đoạn minh họa** với `failedIntegerFuture` đã tồn tại. Nó **không** làm `result` có giá trị 0. `whenComplete` không có giá trị trả về để thay thế. Nếu cần fallback hãy dùng `exceptionally`; nếu cần ánh xạ hai nhánh hãy dùng `handle`.

### Nếu observer tự ném exception: có quy tắc ưu tiên

Theo hợp đồng `CompletionStage`:

1. Nguồn **thành công**, observer ném lỗi -> stage phụ thuộc **thất bại vì lỗi observer**.
2. Nguồn **đã thất bại**, observer cũng ném lỗi -> stage phụ thuộc **ưu tiên giữ lỗi nguồn** thay vì thay bằng lỗi observer.
3. Nguồn hoàn thành bất kỳ trạng thái nào, observer kết thúc bình thường -> stage phụ thuộc giữ đúng trạng thái nguồn.

Ví dụ:

~~~java
CompletableFuture<Integer> normal =
        CompletableFuture.completedFuture(3);

CompletableFuture<Integer> brokenObserver =
        normal.whenComplete((value, error) -> {
            throw new IllegalStateException("logging unavailable");
        });
// brokenObserver thất bại vì IllegalStateException.

CompletableFuture<Integer> failed =
        CompletableFuture.failedFuture(
                new IllegalArgumentException("invalid"));

CompletableFuture<Integer> stillOriginalError =
        failed.whenComplete((value, error) -> {
            throw new IllegalStateException("observer also failed");
        });
// stillOriginalError vẫn ưu tiên IllegalArgumentException của nguồn.
~~~

Đây là **mã Java trong method**. Quy tắc này hữu ích khi phân tích nguyên nhân thất bại, nhưng đừng dựa vào nó để cho phép logging callback ném lỗi tùy ý. Một bộ quan sát tốt nên không làm phát sinh exception thứ cấp và nên nhẹ.

### whenComplete không đồng nhất với finally

`finally` trong cú pháp Java chạy khi rời khối `try` tương ứng; `whenComplete` chạy khi **stage được gắn vào** hoàn tất. Nếu callback `whenComplete` được đăng ký *sau* một `exceptionally` đã phục hồi, nó sẽ thấy **đường thành công**. Nếu đăng ký *trước* `exceptionally`, nó thấy **lỗi gốc**.

## 7. Ví dụ Java 17+ chạy độc lập: so sánh cả ba phương thức

Ví dụ sau dùng những future hoàn thành sẵn để có stdout **xác định**, không phụ thuộc scheduler hoặc thời gian ngủ. Nó cũng kiểm tra ưu tiên lỗi khi `whenComplete` tự ném và cancellation.

Tệp **CompletionHandlersDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public final class CompletionHandlersDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> success =
                CompletableFuture.completedFuture(10);
        AtomicInteger recoveryCalls = new AtomicInteger();

        CompletableFuture<Integer> unchanged =
                success.exceptionally(error -> {
                    recoveryCalls.incrementAndGet();
                    return -1;
                });

        System.out.println("success=" + unchanged.join());
        System.out.println("exceptionallyCalled=" + recoveryCalls.get());

        CompletableFuture<Integer> failed =
                CompletableFuture.failedFuture(
                        new IllegalArgumentException("bad input"));

        CompletableFuture<Integer> recovered =
                failed.exceptionally(error -> 7);

        System.out.println("recovered=" + recovered.join());
        System.out.println("originalFailed="
                + failed.isCompletedExceptionally());

        CompletableFuture<String> mapped =
                success.handle((value, error) ->
                        error == null ? "value=" + value : "error");
        CompletableFuture<String> mappedFailure =
                failed.handle((value, error) ->
                        error == null ? "value=" + value : "failure");

        System.out.println("handleSuccess=" + mapped.join());
        System.out.println("handleFailure=" + mappedFailure.join());

        AtomicBoolean noticed = new AtomicBoolean();
        CompletableFuture<Integer> observed =
                failed.whenComplete((value, error) ->
                        noticed.set(error != null));

        try {
            observed.join();
        } catch (CompletionException ex) {
            System.out.println("observedCause="
                    + ex.getCause().getClass().getSimpleName());
        }
        System.out.println("observerCalled=" + noticed.get());

        CompletableFuture<Integer> newError =
                success.whenComplete((value, error) -> {
                    throw new IllegalStateException("observer failed");
                });
        try {
            newError.join();
        } catch (CompletionException ex) {
            System.out.println("observerOnSuccess="
                    + ex.getCause().getClass().getSimpleName());
        }

        CompletableFuture<Integer> originalWins =
                failed.whenComplete((value, error) -> {
                    throw new IllegalStateException("second failure");
                });
        try {
            originalWins.join();
        } catch (CompletionException ex) {
            System.out.println("observerOnFailure="
                    + ex.getCause().getClass().getSimpleName());
        }

        CompletableFuture<String> nullSuccess =
                CompletableFuture.completedFuture(null);
        System.out.println("nullIsSuccess="
                + nullSuccess.handle((value, error) -> error == null).join());

        CompletableFuture<Integer> cancelled = new CompletableFuture<>();
        cancelled.cancel(false);
        System.out.println("cancelled=" + cancelled.isCancelled());
        System.out.println("cancelFallback="
                + cancelled.exceptionally(error -> 99).join());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac CompletionHandlersDemo.java
java CompletionHandlersDemo
~~~

Stdout trong lần chạy thành công:

~~~text
success=10
exceptionallyCalled=0
recovered=7
originalFailed=true
handleSuccess=value=10
handleFailure=failure
observedCause=IllegalArgumentException
observerCalled=true
observerOnSuccess=IllegalStateException
observerOnFailure=IllegalArgumentException
nullIsSuccess=true
cancelled=true
cancelFallback=99
~~~

**Giải thích từng nhóm kết quả:**

- Với `success`, callback `exceptionally` không chạy nên counter vẫn bằng 0.
- Với `failed`, `exceptionally` cho giá trị 7 ở stage mới; `failed` vẫn exceptional, vì recovery **không sửa stage nguồn**.
- `handle` biến thành công thành chuỗi `value=10`, biến lỗi thành chuỗi `failure`; cả hai stage mới đều thành công.
- `whenComplete` ghi nhận exception nhưng không phục hồi; `observed.join()` ném `CompletionException` với cause `IllegalArgumentException`.
- Nếu observer lỗi trên nguồn thành công, stage mới mang lỗi observer; nếu nguồn vốn lỗi, source exception được ưu tiên.
- `CompletableFuture.completedFuture(null)` vẫn là thành công: `handle` nhìn `error==null`.
- `cancelled.exceptionally(...)` có thể trả fallback 99 vì cancellation là một loại exceptional completion. Điều này **không** có nghĩa cancel đã được hoàn tác trên `cancelled`: `cancelled.isCancelled()` vẫn true.

Ví dụ sử dụng Java 17+, có class/file trùng tên, không phụ thuộc Spring và không dùng `Thread.sleep()`. Những đoạn tích hợp Spring ở các phần sau cần dependency của dự án.

## 8. Thứ tự callback quyết định lỗi nào được nhìn thấy

Giả sử một future nguồn thất bại. Hai pipeline sau **khác nhau về nghĩa**:

~~~java
CompletableFuture<String> a =
        source.whenComplete((value, error) -> {
            if (error != null) {
                recordOriginalError(error);
            }
        }).exceptionally(error -> "fallback");

CompletableFuture<String> b =
        source.exceptionally(error -> "fallback")
              .whenComplete((value, error) -> {
                  recordFinalState(value, error);
              });
~~~

Đây là **đoạn code minh họa với biến/hàm ứng dụng** `source`, `recordOriginalError` và `recordFinalState`. Ở `a`, observer chạy **trước recovery** nên thấy lỗi gốc, trong khi consumer cuối nhận fallback. Ở `b`, observer chạy **sau recovery** nên có thể thấy giá trị `"fallback"` và `error==null`.

Nếu cần vừa ghi lỗi gốc vừa báo kết quả cuối cùng, có thể chủ động có hai stage observer khác nhau với tên metric khác nhau. Không gọi cả hai chỉ để ghi cùng một lỗi, vì dễ đếm trùng.

### Callback phục hồi đặt sớm hay muộn?

~~~java
CompletableFuture<Integer> a =
        source.thenApply(value -> value * 2)
              .exceptionally(error -> 5);

CompletableFuture<Integer> b =
        source.exceptionally(error -> 5)
              .thenApply(value -> value * 2);
~~~

Với `source` lỗi, `a` cho 5 vì `thenApply` bị bỏ qua; `b` cho 10 vì `exceptionally` phục hồi thành 5 trước, rồi `thenApply` chạy. Hai biểu thức đều hợp lệ khi `source` có kiểu `CompletableFuture<Integer>`.

**Bài học:** mỗi callback làm việc với **stage ngay bên trái** của nó, không phải “toàn bộ pipeline” một cách tự động. Muốn tạo error boundary cho toàn bộ chuỗi, gắn `exceptionally` ở điểm phù hợp sau tất cả thao tác cần bao phủ.

## 9. Gỡ lớp bao exception: CompletionException và ExecutionException

Khi một stage lỗi, Java có thể truyền cause dưới lớp bọc `CompletionException`. Khi consumer gọi `join()`, lỗi thường xuất hiện dưới dạng unchecked `CompletionException` với `getCause()` là exception gốc. Khi consumer gọi `get()`, lỗi tác vụ thường được báo bằng checked `ExecutionException`.

~~~java
CompletableFuture<String> bad =
        CompletableFuture.failedFuture(
                new IllegalArgumentException("invalid"));

try {
    bad.join();
} catch (CompletionException ex) {
    Throwable root = ex.getCause();
    System.err.println(root.getClass().getSimpleName());
}

try {
    bad.get();
} catch (java.util.concurrent.ExecutionException ex) {
    Throwable root = ex.getCause();
    System.err.println(root.getClass().getSimpleName());
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
}
~~~

Đoạn Java này dùng trong method có imports `CompletableFuture` và `CompletionException`; nó thể hiện cả hai đường lỗi. `get(timeout, unit)` còn có thể ném `TimeoutException`. `CancellationException` có thể được ném trực tiếp khi future bị cancel.

**Không được giả định** đối số `error` của callback luôn có một lớp `CompletionException`. Nếu nguồn là `failedFuture(new IllegalArgumentException(...))`, callback có thể nhận chính `IllegalArgumentException`. Nếu lỗi lan qua stage phụ thuộc, có thể có `CompletionException`. Vì vậy khi cần phân loại lỗi, hãy unwrap có giới hạn.

Mẫu helper:

~~~java
static Throwable unwrapCompletion(Throwable throwable) {
    Throwable current = throwable;
    while (current instanceof CompletionException
            || current instanceof java.util.concurrent.ExecutionException) {
        if (current.getCause() == null) {
            break;
        }
        current = current.getCause();
    }
    return current;
}
~~~

Đây là **method Java minh họa**, cần import `CompletionException` và có thể đặt trong utility class. Nó chỉ gỡ hai wrapper đại diện cho future completion, không tùy tiện gỡ mọi exception có cause. Khi logging nên giữ cả stack trace có wrapper lẫn root cause nếu cần điều tra.

## 10. Exception của Spring @Async khác với submission rejection

Trong Spring Framework, method được đánh dấu `@Async` có thể trả `CompletableFuture<T>` nếu được gọi qua Spring proxy và `@EnableAsync` đã bật. Có hai điểm lỗi khác nhau:

1. **Lỗi khi submit:** executor không thể nhận task vì bão hòa/shutdown, thường ném `TaskRejectedException` (đối với `ThreadPoolTaskExecutor` và `AbortPolicy`) ngay tại lời gọi proxy. Lúc này caller có thể **chưa nhận được future** để gắn callback.
2. **Lỗi trong task đã nhận:** body ném exception sau khi executor nhận việc, hoặc một stage sau tự lỗi. Future trả về sẽ hoàn thành exceptionally, và `exceptionally`/`handle`/`whenComplete` có thể xử lý.

Ví dụ method Spring:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class PricingAsyncService {

    @Async("pricingExecutor")
    public CompletableFuture<Integer> calculatePrice(int units) {
        if (units < 0) {
            throw new IllegalArgumentException("units must be non-negative");
        }
        return CompletableFuture.completedFuture(units * 100);
    }
}
~~~

Đây là **Spring service** cần `spring-context`, executor tên `pricingExecutor` và lời gọi từ một bean khác qua proxy. Bên trong target method, `completedFuture(...)` là handle tạm để thỏa chữ ký; Spring proxy trao cho caller một handle đại diện cho tác vụ thực tế. Không suy ra phương thức này chạy đồng bộ chỉ vì nó tạo completedFuture trong worker.

Một consumer khác:

~~~java
CompletableFuture<Integer> result;
try {
    result = pricingAsyncService.calculatePrice(3);
} catch (org.springframework.core.task.TaskRejectedException ex) {
    // Executor không nhận task: phản hồi overload/đưa vào kho bền vững.
    throw ex;
}

CompletableFuture<Integer> visible =
        result.whenComplete((value, error) -> {
            if (error != null) {
                logJobFailure(error);
            }
        }).exceptionally(error -> 0);
~~~

Đây là **đoạn code tích hợp** với `pricingAsyncService` đã inject và `logJobFailure` do ứng dụng định nghĩa. Nếu `calculatePrice(-1)` bị lỗi trong worker, observer có thể log exception và `exceptionally` có thể trả fallback 0. Tuy nhiên **trả giá 0 khi tính lỗi là ví dụ về semantics dễ sai nghiệp vụ**; trong hệ thống bán hàng, phải có chính sách rõ ràng hoặc giữ nguyên lỗi thay vì tự đưa giá 0.

### Cấu hình executor minh họa

~~~java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class PricingAsyncConfig {

    @Bean(name = "pricingExecutor")
    public ThreadPoolTaskExecutor pricingExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("pricing-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}
~~~

Đây là **Spring configuration class** không có `main` độc lập. Cấu hình queue/rejection chỉ để minh họa; trong production phải sizing theo workload và giám sát queue, active thread, response time, timeout và rejection.

Một chi tiết: `@Async void` **không** trả `CompletableFuture`, nên không có nơi để caller gọi ba phương thức này. Lỗi không bắt trong body của `@Async void` thường đi qua `AsyncUncaughtExceptionHandler`. Chọn kiểu `CompletableFuture<T>` khi caller cần quan sát hoặc compose kết quả.

## 11. Chọn callback nào cho logging, metrics và fallback?

### Nhu cầu A: log mọi lần hoàn tất mà không thay giá trị

~~~java
CompletableFuture<Order> tracked =
        orderService.load(orderId)
                .whenComplete((order, error) -> {
                    if (error == null) {
                        metrics.incrementSuccess();
                    } else {
                        metrics.incrementFailure();
                    }
                });
~~~

Đây là **mã minh họa** với `Order`, `orderService` và `metrics` do ứng dụng định nghĩa. `whenComplete` giữ nguyên kết quả/lỗi từ `load` nếu callback metrics chạy bình thường. Metric handler phải nhanh, thread-safe, không làm I/O chậm hoặc ném exception không kiểm soát.

### Nhu cầu B: lỗi mạng có fallback được xác định

~~~java
CompletableFuture<Stock> current =
        stockService.fetch(sku)
                .exceptionally(error -> {
                    Throwable cause = unwrapCompletion(error);
                    if (cause instanceof RemoteStockTimeoutException) {
                        return lastKnownStock(sku);
                    }
                    throw new CompletionException(cause);
                });
~~~

Đây là đoạn **mô hình thiết kế**, các type/service/helper ngoài Java cần được khai báo trong dự án. Nếu fallback stale làm vi phạm nghiệp vụ, đừng dùng. Nên gắn metric để phân biệt số lần trả dữ liệu thật và số lần dùng cache.

### Nhu cầu C: API phải trả kết quả chuẩn hóa cả khi lỗi

~~~java
CompletableFuture<ApiResult<Report>> api =
        reportService.generate(reportId)
                .handle((report, error) -> {
                    if (error == null) {
                        return ApiResult.ok(report);
                    }
                    return ApiResult.failure(
                            classify(unwrapCompletion(error)));
                });
~~~

`ApiResult`, `Report` và `classify` là thành phần ứng dụng. Stage `api` hoàn thành **bình thường** với `ApiResult.failure` nếu `handle` trả về bình thường. Tầng HTTP phải xem trạng thái `ApiResult` và chọn status code phù hợp; `future.isCompletedExceptionally()==false` không có nghĩa nghiệp vụ thành công.

### Nhu cầu D: log lỗi rồi để lỗi truyền tiếp

~~~java
CompletableFuture<Report> visible =
        reportService.generate(reportId)
                .whenComplete((report, error) -> {
                    if (error != null) {
                        logFailure(unwrapCompletion(error));
                    }
                });
~~~

Đây là trường hợp `whenComplete` thường thích hợp hơn `exceptionally`: callback quan sát lỗi nhưng **không thay lỗi bằng một giá trị giả**. Nếu chỉ muốn log lỗi và không quan tâm đường thành công, vẫn có thể dùng `whenComplete` với nhánh điều kiện.

## 12. async variants và thread nào thực thi callback?

Các phương thức có nhiều biến thể:

- `exceptionally(fn)`, `handle(fn)`, `whenComplete(action)`.
- `exceptionallyAsync(fn)`, `handleAsync(fn)`, `whenCompleteAsync(action)`.
- Các overload `...Async(fn, Executor executor)` cho phép chọn executor cụ thể.

Với phương thức **không có hậu tố Async**, callback có thể chạy trên thread hoàn thành stage hoặc thread đăng ký callback nếu stage đã hoàn tất. Không nên ghi giả định “tất cả callback đều chạy trên worker của @Async” vào logic nghiệp vụ. Với biến thể `...Async`, công việc callback được lên lịch qua executor mặc định của stage (thường `ForkJoinPool.commonPool()` đối với `CompletableFuture` chuẩn) hoặc executor được truyền vào.

~~~java
CompletableFuture<String> result =
        source.handleAsync(
                (value, error) -> error == null
                        ? value.toUpperCase()
                        : "FALLBACK",
                callbackExecutor);
~~~

Đây là **đoạn minh họa** với `source` kiểu `CompletableFuture<String>` và `callbackExecutor` kiểu `Executor`. Chọn executor riêng có lợi khi callback có việc CPU/I/O đáng kể và cần cách ly khỏi thread đang hoàn tất nguồn; nhưng cũng thêm queue, rejection, shutdown và yêu cầu quản lý context.

Cần tránh hai hiểu lầm:

1. **Hậu tố Async không bảo đảm tự tạo thread mới.** Nó dùng cơ chế scheduling đã chỉ định; một executor có thể chọn thực thi trực tiếp trên caller hoặc bị bão hòa.
2. **Không có hậu tố Async không có nghĩa callback luôn chạy đồng bộ ở thời điểm bạn đăng ký.** Nếu nguồn chưa hoàn tất, callback sẽ chạy khi nguồn hoàn tất; nó chỉ không yêu cầu lịch riêng qua một executor khác.

### Cảnh báo blocking callback

Nếu dùng `whenComplete` để gọi HTTP, ghi file hoặc chờ một `Future.join()` khác, callback có thể block chính thread đang hoàn tất tác vụ nguồn. Điều này gây tăng latency cho các stage khác, giữ worker lâu hơn và có thể starvation khi callback chờ tác vụ dùng chung một pool nhỏ. Ưu tiên callback nhanh; khi có việc nặng, bố trí executor/queue và quan sát overload một cách riêng biệt.

## 13. Lỗi mới sinh trong callback: đừng làm mất nguyên nhân gốc

Ba API có điểm chung: nếu callback tính toán gặp exception chưa được xử lý, **stage trả về có thể hoàn thành exceptionally**. Nhưng `whenComplete` có luật ưu tiên lỗi gốc khi cả nguồn và observer đều lỗi, trong khi `handle` và `exceptionally` là nơi chủ động tính toán kết quả mới, nên lỗi mới của chúng có thể thay thế đường lỗi trước.

Một cách đặt callback có chủ ý:

~~~java
CompletableFuture<Result> pipeline =
        doRemoteWork()
                .whenComplete((value, error) -> auditResult(value, error))
                .handle((value, error) -> {
                    if (error == null) {
                        return Result.success(value);
                    }
                    return Result.failure(unwrapCompletion(error));
                });
~~~

Đây là **mẫu thiết kế** cần `Result`, `doRemoteWork` và `auditResult` do ứng dụng cung cấp. Nếu `auditResult` ném exception trên đường nguồn thành công, stage `whenComplete` sẽ thất bại vì observer và `handle` thấy lỗi observer, không phải lỗi làm việc từ xa. Vì vậy logging, tracing và metric phải tránh exception không kiểm soát.

Nếu một lỗi được phục hồi ở `exceptionally` trước khi đi qua một `whenComplete` khác, observer sau đó sẽ thấy **thành công**, dù thao tác nguồn từng lỗi. Muốn ghi cả lỗi gốc và phục hồi, phân biệt metric theo stage.

## 14. Cancellation và timeout cũng là nguồn exceptional completion

`CompletableFuture.cancel(true)` không giống việc chắc chắn interrupt một worker: với `CompletableFuture` chuẩn, tham số `mayInterruptIfRunning` không dùng để điều khiển interruption của task. Cancellation biểu diễn exceptional completion, nên `exceptionally`, `handle` hoặc `whenComplete` có thể được kích hoạt.

~~~java
CompletableFuture<String> source = new CompletableFuture<>();
source.cancel(false);

CompletableFuture<String> converted =
        source.exceptionally(error -> "cancelled-or-failed");
~~~

`converted.join()` cho `"cancelled-or-failed"`, nhưng `source.isCancelled()` vẫn `true`. Tự động phục hồi mọi cancellation thành giá trị thành công có thể **che đi ý định hủy** của caller. Nếu cancel có ý nghĩa dừng quy trình, nên phân biệt `CancellationException` với lỗi nghiệp vụ khác.

`orTimeout(2, TimeUnit.SECONDS)` có thể hoàn thành **chính future đó** exceptionally với `TimeoutException` nếu chưa xong. `completeOnTimeout(fallback, ...)` có thể hoàn thành chính future đó bằng giá trị fallback. Hai phương thức là quyết định completion/deadline; không tự dừng I/O hay rollback side effect đã diễn ra.

Đặc biệt, khi đặt `exceptionally` phía sau timeout, callback sẽ xem lỗi timeout như một nhánh failure. Nếu có retry, phải xác định task cũ đã ngừng chưa, có idempotency hay không và có thể có side effect trùng lặp không.

## 15. Chuỗi xử lý phức tạp: allOf, thenCompose và lỗi lan truyền

Các stage khác như `thenApply`, `thenCompose`, `thenCombine` và `allOf` có thể hoàn thành exceptionally khi nhánh phụ thuộc lỗi. Đặt error handler ở điểm phù hợp sẽ quyết định scope fallback.

Ví dụ một chuỗi tác vụ:

~~~java
CompletableFuture<Receipt> receipt =
        customerService.load(customerId)
                .thenCompose(customer -> paymentService.charge(customer))
                .thenApply(payment -> receiptMapper.toReceipt(payment))
                .whenComplete((value, error) ->
                        metrics.recordPaymentAttempt(error == null))
                .exceptionally(error -> {
                    throw new CompletionException(
                            unwrapCompletion(error));
                });
~~~

Đây là **mã kiến trúc minh họa**, không biên dịch độc lập vì cần các service/type của hệ thống. `whenComplete` quan sát completion trước recovery. `exceptionally` cuối ở đây chỉ ném lại lỗi đã unwrap, **không tạo fallback**, nên có thể là dư thừa; một cách rõ hơn là để lỗi tự lan tiếp và bắt tại boundary thích hợp.

Với tác vụ **charge/payment có side effect**, không dùng `exceptionally(error -> successReceipt)` để tạo receipt thành công giả. Cần lưu trạng thái giao dịch, idempotency, reconciliation và xử lý lỗi bất định theo yêu cầu thực tế.

### allOf và một nhánh lỗi

`CompletableFuture.allOf(a,b)` trả `CompletableFuture<Void>`, hoàn thành khi cả hai đã kết thúc; nếu một nhánh lỗi, future tổng cũng kết thúc exceptionally. Có thể đặt `whenComplete` trên future tổng để đo kết quả chung. Nếu cần thống kê **từng nhánh**, gắn `handle`/`whenComplete` trên từng nguồn thay vì suy luận từ chỉ một exception của tổng.

Nếu muốn báo cáo **mọi** thất bại mà không để lỗi một nhánh ngăn việc đọc nhánh khác, có thể dùng `handle` để biến mỗi nhánh thành một `Outcome` chứa success/failure, rồi ghép các `Outcome` lại. Đó là lựa chọn có ý thức, không phải cách “nuốt” lỗi vì tiện.

## 16. Transaction, ThreadLocal và logging context trong Spring

Trong Spring `@Async`, body thường chạy trên executor thread. Transaction gắn với caller thread không tự được kế thừa, tương tự nhiều `ThreadLocal` chứa SecurityContext, MDC/log correlation và trace context. Callback `thenApply/handle/whenComplete` không có hậu tố Async có thể chạy trên **thread bất kỳ hoàn thành stage**, nên cũng không an toàn khi mặc định nó thấy context request.

Những tình huống dễ gây lỗi:

- Callback `whenComplete` lấy MDC request ID nhưng thread hoàn tất là worker không có MDC.
- `exceptionally` fallback đọc thông tin security principal từ ThreadLocal thay vì tham số an toàn.
- `handle` ghi vào database nhưng transaction của controller đã commit/rollback từ trước.
- Dùng `@Async` gửi việc trước khi transaction nguồn commit; worker thấy dữ liệu chưa tồn tại hoặc bị rollback.

Giải pháp: truyền metadata cần thiết như giá trị bất biến; dùng `TaskDecorator` hoặc cơ chế propagation phù hợp với executor; xác định transaction boundary riêng trong worker; khi cần đảm bảo sau commit, dùng event after-commit hoặc transactional outbox. **Không chọn callback nào chỉ dựa trên kỳ vọng thread context tự tồn tại.**

## 17. Thiết kế logging và metrics tránh mất hoặc đếm trùng lỗi

Một pipeline có thể có nhiều stage:

~~~text
source (exception)
   |
   +--> whenComplete(log original) ---> exceptionally(fallback)
   |                                    |
   |                                    +--> whenComplete(log recovered)
   |
   +--> handle(create Outcome.failure)
~~~

Nếu cả ba nơi ghi cùng metric `failed_jobs++`, hệ thống sẽ đếm trùng một job. Nên phân định:

- **Nguồn lỗi thật:** metric ở boundary thực thi hoặc observer gắn trực tiếp vào source.
- **Fallback được sử dụng:** metric riêng, đếm số lần thay thế kết quả.
- **Kết quả cuối theo nghiệp vụ:** metric ở response/job-status boundary.
- **Lỗi xử lý callback:** metric riêng hoặc log riêng để không nhầm với lỗi source.

Không log nguyên exception object bằng cách chỉ gọi `error.toString()` rồi bỏ stack trace trong hệ thống cần điều tra sự cố. Nhưng cũng không log dữ liệu nhạy cảm từ request/exception. Khi logging callback có khả năng ném lỗi, hãy cô lập nó hoặc đảm bảo sink đáng tin và xử lý ngoại lệ nhẹ, vì `whenComplete` có thể làm pipeline thành công biến thành thất bại.

## 18. Testing với CompletableFuture: xác định, không ngủ đoán

### Test logic riêng của ba API

Dùng `CompletableFuture.completedFuture(value)` và `CompletableFuture.failedFuture(error)` để kiểm tra từng nhánh **không cần executor**. Có thể assert:

1. `exceptionally` **không được gọi** khi nguồn thành công.
2. `exceptionally` trả fallback khi nguồn lỗi, nhưng nguồn vẫn exceptional.
3. `handle` chạy trên cả hai nhánh và có thể đổi `Integer` thành `String`.
4. `whenComplete` thấy lỗi nhưng stage phụ thuộc vẫn exceptional.
5. Observer `whenComplete` tự lỗi trên đường thành công thì stage phụ thuộc lỗi vì observer.
6. Observer cũng lỗi khi nguồn đã lỗi thì stage phụ thuộc ưu tiên lỗi nguồn.
7. Nguồn thành công với giá trị `null` phải được xử lý đúng bằng `error == null`.
8. Cancellation có thể kích hoạt exceptional completion nhưng không tự được hoàn tác trên nguồn.

### Test tích hợp với Spring @Async

Để kiểm thử đường task thật:

- Tạo bean `@Async` được Spring quản lý, bật `@EnableAsync`, và **gọi qua Spring proxy**, không dùng `this.method()` từ cùng bean trong proxy mode.
- Dùng `CountDownLatch entered` để xác nhận worker bắt đầu, `CountDownLatch release` để kiểm soát thời điểm worker hoàn thành. Không dùng `Thread.sleep(...)` để tạo race.
- Trả `CompletableFuture.completedFuture(value)` hoặc để exception ném từ body; kiểm tra Future của proxy với `get(timeout, unit)`, `whenComplete` và `exceptionally`.
- Test riêng tình huống submit bị từ chối khi executor/queue đầy; lỗi submit có thể xảy ra **trước khi có Future** và không thể kiểm thử chỉ bằng callback gắn sau.
- Test cleanup của executor và bảo đảm giải phóng latch trong `finally` để không làm CI treo.
- Test thread identity nếu ứng dụng có yêu cầu executor/context cụ thể; không suy ra tính async từ việc future còn pending trong một thời điểm ngẫu nhiên.

Ví dụ assertions JUnit 5 minh họa:

~~~java
CompletableFuture<Integer> failed =
        CompletableFuture.failedFuture(
                new IllegalArgumentException("invalid"));

assertEquals(10, failed.exceptionally(error -> 10).join());

CompletableFuture<String> mapped =
        failed.handle((value, error) ->
                error == null ? "ok" : "failure");
assertEquals("failure", mapped.join());

CompletableFuture<Integer> observed =
        failed.whenComplete((value, error) ->
                assertNotNull(error));
assertThrows(CompletionException.class, observed::join);
~~~

Đây là **fragment JUnit 5**, cần các static imports `Assertions.assertEquals`, `assertNotNull`, `assertThrows`, các imports `CompletableFuture` và `CompletionException`, và một test method/test class. Không xem nó là chương trình standalone.

## 19. Các lỗi phổ biến cần tránh

1. **Dùng `whenComplete` và tưởng đã khôi phục lỗi.** Observer không trả fallback, lỗi vẫn lan tiếp.
2. **Dùng `exceptionally` để ghi log nhưng vô tình trả default.** Caller nhận thành công giả và có thể không thấy lỗi nguồn.
3. **Dùng `handle` và không kiểm tra `error`.** Có thể truy cập `value` bằng null khi nguồn lỗi hoặc coi null là lỗi dù nguồn thành công.
4. **Cho rằng cả ba API sửa trực tiếp future nguồn.** Mỗi API trả một stage phụ thuộc mới; nguồn không bị sửa.
5. **Đặt fallback quá sớm trong pipeline.** Một lỗi quan trọng bị chuyển thành thành công và các stage sau vẫn chạy side effect.
6. **Đặt fallback quá muộn khi cần phục hồi một nhánh cụ thể.** Các phép biến đổi ở giữa đã bị bỏ qua vì lỗi lan truyền.
7. **Bắt mọi Throwable rồi trả dữ liệu mặc định.** Có thể che bug lập trình, lỗi dữ liệu, interruption/cancellation và sự cố hệ thống.
8. **Không gỡ `CompletionException` khi phân loại nguyên nhân.** Kiểm tra nhầm wrapper thay vì root cause.
9. **Gỡ mọi lớp exception bằng vòng lặp không giới hạn loại.** Làm mất ngữ nghĩa nghiệp vụ của các exception có cause riêng.
10. **Dùng `join()` rồi nghĩ non-blocking.** `join()` vẫn chờ nếu stage chưa hoàn thành; chỉ loại bỏ checked exceptions.
11. **Cho rằng `whenComplete` luôn an toàn và không thể làm stage lỗi.** Observer tự ném lỗi trên nguồn thành công sẽ làm stage phụ thuộc thất bại.
12. **Block lâu trong callback không có hậu tố Async.** Có thể chiếm chính worker vừa hoàn tất nguồn và gây tắc nghẽn.
13. **Dùng `handleAsync` không cấp executor rồi mặc định vẫn chạy trên Spring pool.** Có thể chuyển sang commonPool/default execution facility.
14. **Quên submission rejection.** Nếu executor không nhận task, caller chưa có Future để gắn `exceptionally`.
15. **Đặt `@Async void` và cố gọi `whenComplete` trên lời gọi trả void.** Không có handle; cần Future hoặc job-state khác.
16. **Nhầm cancel với ngắt việc thật.** `CompletableFuture.cancel` không chắc dừng CPU/I/O đang chạy.
17. **Nhầm timeout của Future với rollback side effect.** Task có thể tiếp tục sau khi người chờ bỏ cuộc.
18. **Gắn cùng metric ở nhiều stage mà không phân biệt scope.** Đếm trùng lỗi hoặc báo success do fallback thành success thật.
19. **Không test nguồn thành công null và cancellation.** Logic phân biệt trạng thái dễ bị sai ở hai trường hợp này.
20. **Bỏ qua thread context ở callback.** MDC, security, transaction không tự bảo đảm chuyển từ request thread sang worker.
21. **Thêm callback chỉ để biến exception thành một thông điệp quá chung.** Mất nguyên nhân điều tra và semantic error code.
22. **Dùng fallback cho thao tác tài chính hoặc side effect quan trọng.** Trả “thành công” giả có thể tạo sai lệch dữ liệu; phải có job status, retry và reconciliation.

## 20. Chọn API qua câu hỏi ngắn

| Câu hỏi của ứng dụng | Lựa chọn |
| --- | --- |
| Nguồn lỗi, tôi muốn trả một giá trị dự phòng cùng kiểu `T`? | `exceptionally` |
| Nguồn thành công hoặc lỗi, tôi muốn biến cả hai thành kiểu `U` khác? | `handle` |
| Tôi chỉ cần ghi log/metric cho mọi kết quả, không đổi kết quả hoặc lỗi? | `whenComplete` |
| Tôi muốn giữ exception cho caller nhưng thêm thông tin quan sát? | `whenComplete` trước khi lan lỗi |
| Tôi muốn nhận `Outcome<T>` thay vì exceptional future? | `handle` tạo `Outcome` có status rõ ràng |
| Tôi muốn dùng callback nặng chạy ở một executor chuyên dụng? | `handleAsync`/`whenCompleteAsync`/`exceptionallyAsync` với executor explicit |
| Tôi muốn fallback bằng một công việc khác cũng bất đồng bộ? | `exceptionallyCompose` trong Java 17+ hoặc tổ chức `handle` + `thenCompose`; cần kiểm soát executor và retry |
| Tôi muốn xử lý lỗi `@Async void`? | `AsyncUncaughtExceptionHandler` hoặc đổi chữ ký sang Future |
| Tôi muốn biết lúc executor từ chối task trước khi trả Future? | Bắt `TaskRejectedException` ở chỗ gọi proxy, không đợi callback |
| Tôi muốn job không mất khi ứng dụng restart? | Durable queue/job table với idempotency/retry, không phải chỉ `CompletableFuture` |

### Thêm về exceptionallyCompose

`exceptionally` đòi callback trả trực tiếp giá trị `T`. Nếu fallback bản thân nó phải gọi một dịch vụ **bất đồng bộ** trả `CompletionStage<T>`, Java 17 có `exceptionallyCompose(fn)` để ghép một stage fallback mà không tạo Future lồng nhau. Ví dụ mô hình:

~~~java
CompletableFuture<String> result =
        primary.fetch(key)
                .exceptionallyCompose(error -> secondary.fetch(key));
~~~

Đây là **fragment tích hợp**: `primary`/`secondary` là dịch vụ giả định trả `CompletableFuture<String>`. Việc fallback sang nguồn thứ hai phải kiểm soát timeout, circuit breaker và không tạo vòng retry vô hạn. Nếu chỉ cần giá trị mặc định trong RAM, `exceptionally` đơn giản hơn.

## 21. Câu hỏi tự kiểm tra

1. Trong ba API, phương thức nào **chỉ chạy khi nguồn lỗi**?
2. Phương thức nào có thể đổi `CompletableFuture<Integer>` thành `CompletableFuture<String>` bằng một callback?
3. Tại sao `whenComplete((v,e)->log(e))` không có nghĩa là lỗi đã được khôi phục?
4. Khi nguồn thành công nhưng observer `whenComplete` ném exception, stage phụ thuộc có trạng thái gì?
5. Khi nguồn đã lỗi và observer cũng lỗi, lỗi nào được ưu tiên ở stage `whenComplete`?
6. `CompletableFuture.completedFuture(null)` là thành công hay thất bại? Trong `handle` nên kiểm tra field nào?
7. Vì sao `source.exceptionally(...)` không làm `source.isCompletedExceptionally()` chuyển từ true sang false?
8. Cách đặt `whenComplete` trước hay sau `exceptionally` ảnh hưởng kết quả logging thế nào?
9. `join()` có non-blocking hơn `get()` không? Hai phương thức khác nhau về cách báo exception ra sao?
10. Dùng `handleAsync` không truyền executor trong ứng dụng Spring có thể làm callback chạy ở thread pool nào?
11. Với `@Async`, lỗi từ method body và `TaskRejectedException` khi submit khác nhau ở điểm nào?
12. Một `CompletableFuture` đã bị cancel nhưng được `exceptionally` chuyển thành fallback ở stage sau có nghĩa task trước đó tiếp tục hay đã dừng?
13. Nếu metric observer thất bại, bạn muốn nó có khả năng đổi kết quả nghiệp vụ không? Thiết kế callback ra sao?
14. Vì sao lỗi thao tác thanh toán không được phục hồi thành “thành công” chỉ bằng một giá trị mặc định?
15. Nếu fallback cần gọi một dịch vụ trả `CompletionStage<T>`, `exceptionallyCompose` khác `exceptionally` ở điểm nào?

## 22. Tài liệu tham khảo chính thức

- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 17 — CompletionStage (quy tắc whenComplete và handle)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html)
- [Java SE 17 — CompletionException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionException.html)
- [Java SE 17 — ExecutionException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutionException.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — @Async Javadoc](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/scheduling/annotation/Async.html)
- [Spring Framework — ThreadPoolTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)

**Ghi nhớ:** **`exceptionally()`** phục hồi đường lỗi bằng giá trị cùng kiểu; **`handle()`** luôn biến đổi kết quả/lỗi và có thể đổi kiểu; **`whenComplete()`** quan sát cả hai đường nhưng giữ nguyên kết quả/lỗi nguồn khi callback thành công. Chúng tạo stage mới chứ không sửa stage gốc; trong Spring `@Async` phải xử lý thêm lỗi submit, executor và thread context để pipeline đáng tin cậy.