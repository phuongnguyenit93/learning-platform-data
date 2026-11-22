# Propagate lỗi trong chuỗi CompletableFuture của Java

`CompletableFuture<T>` đại diện cho một kết quả sẽ được hoàn tất trong tương lai, **bình thường bằng giá trị** hoặc **bất thường bằng exception/cancellation**. Khi ghép nhiều stages bằng `thenApply`, `thenCompose`, `thenAccept` hay `thenCombine`, lỗi ở một stage thường **lan truyền tới các stages phụ thuộc**. Những stage chỉ chạy trên kết quả thành công sẽ **không chạy**, trong khi những stage xử lý lỗi như `exceptionally`, `handle`, `whenComplete` có cơ hội can thiệp theo những semantics khác nhau.

Hiểu sai đường lan truyền lỗi có thể dẫn tới các vấn đề rất thực tế: bỏ qua lỗi rồi trả dữ liệu giả, vô tình nuốt exception, gọi fallback hai lần, báo lỗi sai do `CompletionException` wrapper, mất lỗi của một nhánh trong `allOf`, hoặc cho rằng `cancel(true)` đã dừng công việc nền.

Bài học tập trung vào **Java concurrency nói chung** với `java.util.concurrent.CompletableFuture` và các API JDK 17+; các cơ chế tích hợp riêng của Spring không thuộc phạm vi.

## 1. Hai trạng thái hoàn tất và một nguyên tắc quan trọng

Một `CompletableFuture<T>` có thể:

- **Complete normally**: có giá trị kiểu `T`, kể cả `null` nếu hợp đồng cho phép.
- **Complete exceptionally**: có một `Throwable` làm nguyên nhân lỗi; cancellation là một loại exceptional completion.
- **Incomplete**: chưa được hoàn tất; các dependent stages có thể chưa có kết quả.

Một future chỉ hoàn tất một lần qua các cách thông thường như `complete` hoặc `completeExceptionally`; các lời hoàn tất tiếp theo không tự ghi đè kết quả đầu tiên. Những API can thiệp mạnh như `obtrudeValue/obtrudeException` có hành vi khác và không nên dùng để sửa luồng nghiệp vụ thông thường.

**Câu then chốt:** stage `thenApply` không nhận một object `Throwable` để tự quyết định. Khi upstream thất bại, callback `thenApply` thường bị **bỏ qua**, còn future do `thenApply` tạo ra cũng hoàn tất bất thường. Chỉ các callback dành cho lỗi/completion mới quan sát được outcome thất bại.

### Sơ đồ propagation cơ bản

```text
supplyAsync(...) --success--> thenApply(...) --success--> thenCompose(...)
       |
       +--failure--> dependent exceptional completion
                          |
                          +--> thenApply callback SKIPPED
                          |
                          +--> exceptionally(...)  -> fallback value
                          |
                          +--> handle(...)         -> transform or recover
                          |
                          +--> whenComplete(...)   -> observe, not recover
```

Những đường này là **các cách gắn stage khác nhau**, không có nghĩa mọi callback đều được gọi trong một chain. Vị trí gắn và dạng callback quyết định hành vi.

## 2. Cơ chế lan truyền từ một stage thất bại

Xét chuỗi:

```java
CompletableFuture<Integer> output =
        CompletableFuture.supplyAsync(() -> loadValue())
                .thenApply(value -> normalize(value))
                .thenApply(value -> validate(value))
                .thenApply(value -> persist(value));
```

Đây là **snippet**, cần có các methods `loadValue/normalize/validate/persist` phù hợp type và import `CompletableFuture`.

Nếu `normalize` ném exception:

1. Future của bước `normalize` hoàn tất bất thường.
2. Callback `validate` **không được gọi** vì nó là `thenApply` chạy trên kết quả thành công.
3. Callback `persist` cũng **không được gọi**.
4. Future cuối hoàn tất bất thường, mang nguyên nhân lỗi theo semantics của chuỗi.
5. Caller quan sát lỗi bằng `join`, `get` hoặc một handler như `exceptionally/handle`.

Nếu `loadValue` thất bại ngay từ đầu, cả ba callback phía sau bị skip. Nếu `persist` thất bại, hai bước trước vẫn đã chạy và các side effects của chúng **không tự rollback**.

**Không nhầm “callback bị skip” với “task bị hủy”:** những bước **đã thực thi trước lúc lỗi** vẫn đã chạy. CompletableFuture không cung cấp transaction, undo hoặc cancellation tự động cho tất cả operations đã bắt đầu.

## 3. Java 17: lan truyền lỗi và recovery xác định

Tạo file **`PipelinePropagationDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.atomic.AtomicBoolean;

public class PipelinePropagationDemo {
    public static void main(String[] args) {
        AtomicBoolean downstreamRan = new AtomicBoolean(false);

        CompletableFuture<Integer> failed =
                CompletableFuture.completedFuture(5)
                        .<Integer>thenApply(value -> {
                            throw new IllegalStateException("bad value");
                        })
                        .thenApply(value -> {
                            downstreamRan.set(true);
                            return value * 2;
                        });

        String propagatedCause;
        try {
            failed.join();
            throw new AssertionError("Expected failure");
        } catch (CompletionException e) {
            propagatedCause =
                    e.getCause().getClass().getSimpleName();
        }

        int recovered = failed
                .exceptionally(error -> 40)
                .thenApply(value -> value + 2)
                .join();

        System.out.println(
                "originalExceptional=" + failed.isCompletedExceptionally());
        System.out.println("downstreamRan=" + downstreamRan.get());
        System.out.println("propagatedCause=" + propagatedCause);
        System.out.println("recovered=" + recovered);
    }
}
```

Chạy JDK 17+:

```bash
javac PipelinePropagationDemo.java
java PipelinePropagationDemo
```

Stdout:

```text
originalExceptional=true
downstreamRan=false
propagatedCause=IllegalStateException
recovered=42
```

**Giải thích:** `completedFuture(5)` là upstream thành công. Stage kế tiếp ném `IllegalStateException`, vì thế stage đánh dấu `downstreamRan` không được chạy. `join` ném `CompletionException`, bên trong có nguyên nhân gốc. Nhánh `exceptionally` tạo **một future khác** có giá trị thay thế `40`, rồi `thenApply` làm phép cộng cho kết quả `42`.

**Đặc biệt:** `failed` ban đầu vẫn exceptional sau khi tạo nhánh recovery. `exceptionally` không thay đổi trạng thái future nguồn; nó trả **dependent future** mới có thể thành công hoặc thất bại. Vì thế hai callers giữ hai nhánh khác nhau có thể quan sát outcome khác nhau mà không có mâu thuẫn.

Đây là demo deterministic: không tạo worker async, không phụ thuộc `Thread.sleep` hay thứ tự scheduler; mục tiêu là hiểu **composition semantics** trước khi mở rộng sang concurrency thực tế.

## 4. Bốn nhóm API cần phân biệt

| API | Khi upstream thành công | Khi upstream exceptional | Có recover thành normal completion? |
| --- | --- | --- | --- |
| `thenApply(fn)` | Gọi `fn(value)` | Skip fn, propagate lỗi | Không, trừ khi lỗi đã được xử lý trước đó |
| `thenAccept(consumer)` | Gọi consumer | Skip consumer, propagate lỗi | Không |
| `thenRun(action)` | Gọi action | Skip action, propagate lỗi | Không |
| `thenCompose(fn)` | Gọi fn trả một `CompletionStage` và flatten | Skip fn, propagate lỗi | Không nếu chưa gắn recovery |
| `exceptionally(fn)` | Không gọi fn, truyền giá trị | Gọi fn với lỗi; trả giá trị cùng kiểu T | **Có**, nếu fn return bình thường |
| `exceptionallyCompose(fn)` | Không gọi fn, truyền giá trị | Gọi fn trả stage fallback cùng kiểu T | **Có**, nếu fallback stage thành công |
| `handle(fn)` | Gọi với (`value`, `null`) | Gọi với (`null`, `error`) | **Có thể**, nếu fn return bình thường |
| `whenComplete(action)` | Gọi với (`value`, `null`) | Gọi với (`null`, `error`) | **Không**, chỉ quan sát/completion side effect |
| `thenCombine(other,fn)` | Chạy fn khi cả hai upstream thành công | Không chạy fn nếu dependency thất bại | Không |
| `allOf(...)` | Thành công khi tất cả thành công | Exceptional nếu ít nhất một thất bại | Không tự recover |
| `anyOf(...)` | Hoàn tất theo future đầu tiên hoàn tất | Nếu winner thất bại thì exceptional | Không tự chờ “winner thành công” |

**Chú ý:** các overload có `Async` tương ứng thay đổi **nơi callback được thực thi** (ví dụ trên executor), chứ không biến một method quan sát lỗi thành method recover.

## 5. `exceptionally`: fallback cho một failure

`exceptionally(Function<Throwable, ? extends T>)` chỉ chạy khi upstream hoàn tất bất thường. Nếu callback return một giá trị kiểu T, dependent future **chuyển về normal completion**.

```java
CompletableFuture<String> safe = remoteCall()
        .exceptionally(error -> "cached-value");
```

Đây là snippet; `remoteCall()` trả `CompletableFuture<String>`. Nếu remote thất bại, caller của `safe` có thể nhận `"cached-value"` bình thường.

### Khi nào fallback có ý nghĩa?

- Dữ liệu không quan trọng có thể dùng default cấu hình hợp lệ.
- Một service đề xuất có thể rơi về danh sách dự phòng.
- Một bước đọc optional có thể trả empty result có semantics rõ.
- Một nhà cung cấp phụ có thể không sẵn sàng và ta có fallback đã thiết kế.

### Khi nào không nên trả fallback mặc định?

Nếu bước ghi giao dịch thất bại nhưng callback trả `null` hoặc `0` rồi downstream vẫn tiếp tục báo thành công, lỗi nghiệp vụ nghiêm trọng đã bị **che giấu**.

Ví dụ **sai nếu buộc phải thanh toán thành công**:

```java
chargePayment()
        .exceptionally(error -> null)
        .thenApply(ignored -> markOrderPaid());
```

Đây là snippet, các methods do ứng dụng định nghĩa. Nếu charge thất bại, `exceptionally` tạo normal completion với null; `markOrderPaid` có thể được gọi dù chưa thu tiền. **Hãy chọn fallback theo contract**, không dùng `exceptionally` như cách tắt báo lỗi toàn cục.

### Chỉ recover lỗi mà bạn thật sự hiểu

```java
.exceptionally(error -> {
    Throwable cause = unwrapCompletion(error);
    if (cause instanceof KnownTemporaryFailure) {
        return fallbackValue();
    }
    throw new CompletionException(cause);
})
```

Đây là **snippet**, `KnownTemporaryFailure` và các helpers chưa định nghĩa; `CompletionException` thuộc `java.util.concurrent`. Các lỗi unexpected được **propagate** thay vì âm thầm biến thành success. Không rethrow mọi lỗi bằng cách làm mất cause hoặc stack trace.

Nếu bạn cần một future fallback **bất đồng bộ**, `exceptionallyCompose` là API phù hợp hơn việc return một future như là giá trị T hoặc block bằng `join` bên trong error handler.

## 6. `handle`: nhìn cả success lẫn failure, có thể đổi kiểu kết quả

Method `handle(BiFunction<? super T, Throwable, ? extends U>)` chạy khi upstream hoàn tất **theo cả hai hướng**.

```java
CompletableFuture<String> status = request()
        .handle((value, error) -> {
            if (error == null) {
                return "OK:" + value;
            }
            return "FAILED:" + error.getClass().getSimpleName();
        });
```

Đây là snippet, `request()` trả một `CompletableFuture<?>` có kiểu phù hợp. Callback trả chuỗi `String` và future kết quả hoàn tất bình thường nếu callback return bình thường.

**Không dùng `handle` chỉ để log mà quên throw lại**. Nếu handler viết:

```java
.handle((value, error) -> {
    if (error != null) log(error);
    return value;
})
```

thì trên failure, `value` thông thường là null, nên handler **trả null và biến failure thành success**. Bước downstream có thể nhận null thay vì được skip. Khi mục tiêu chỉ là logging, `whenComplete` thường đúng hơn.

### `handle` có thể transform result type

Ví dụ stage trước trả `Integer`, nhưng `handle` trả một object `Result`/status bao cả success và error. Đây là cách hữu ích nếu API public muốn **explicit result object** thay vì exception propagation. Tuy nhiên nó nên làm rõ status, không che lỗi.

`handleAsync(handler, executor)` giữ semantics quan sát/recovery nhưng chạy callback trên executor được chỉ định. Nếu executor bị shutdown và không nhận callback, dependent stage cũng có thể thất bại do scheduling/rejection; phải quản lý executor lifecycle.

## 7. `whenComplete`: log/metrics mà không nuốt lỗi

`whenComplete(BiConsumer<T, Throwable>)` được gọi khi upstream hoàn tất và trả về dependent future mang **cùng outcome** nếu callback không ném exception.

```java
CompletableFuture<Result> traced = call()
        .whenComplete((value, error) -> {
            if (error != null) {
                recordFailure(error);
            } else {
                recordSuccess();
            }
        });
```

Đây là snippet; `Result`, `call` và metrics functions do ứng dụng định nghĩa.

- Upstream success, observer success → downstream nhận đúng value.
- Upstream failure, observer success → downstream vẫn **exceptional** với lỗi upstream.
- Upstream success, observer throw → downstream **exceptional vì lỗi observer**.
- Upstream failure, observer cũng throw → theo hợp đồng, lỗi upstream vẫn là nguyên nhân ưu tiên cho dependent future; lỗi phụ có thể phải tự log nếu muốn giữ thông tin observer failure.

**Kết luận:** `whenComplete` thích hợp để ghi metrics, log và cleanup đơn giản, **không phải fallback stage**. Nếu cần recover, gắn `exceptionally` hoặc `handle` sau đó.

### Những câu hỏi cần đặt khi log

- Có log nhiều lần cùng exception ở mọi stage không, gây spam?
- Có ghi thông tin nhạy cảm trong exception message không?
- Logging function có thể ném exception do formatter/serializer/network không?
- Thay vì gọi I/O blocking trong callback, có nên ghi dữ liệu vào một queue bounded phục vụ diagnostics không?
- Có giữ correlation ID/workflow ID để tìm nguyên nhân gốc mà không nhầm lỗi wrapper?

## 8. `exceptionallyCompose`: fallback trả về một CompletionStage

Khi phục hồi cần gọi một nguồn async khác:

```java
CompletableFuture<String> value = primaryAsync()
        .exceptionallyCompose(error -> backupAsync());
```

Đây là snippet, `primaryAsync/backupAsync` trả `CompletableFuture<String>`. Nếu primary thất bại, callback tạo **fallback stage**; dependent future hoàn tất theo kết quả của fallback stage (thành công hoặc thất bại).

Nếu viết thay bằng:

```java
.exceptionally(error -> backupAsync().join())
```

thì error callback có thể **block thread** chờ fallback; nếu chạy trên executor nhỏ mà fallback cũng cần executor ấy, có nguy cơ **thread starvation**. `exceptionallyCompose` diễn đạt một asynchronous dependency mà không cần gọi `join` trong handler.

**Chú ý:** fallback cũng có thể ném hoặc trả một stage exceptional. Lỗi fallback khi đó lan truyền downstream; API không có bảo đảm fallback luôn thành công.

`exceptionallyCompose` có trên JDK 12+, vì thế hợp lệ trên Java 17. Các overload `exceptionallyComposeAsync` sử dụng default async execution facility hoặc executor chỉ định.

## 9. Java 17: so sánh whenComplete/handle/exceptionally/exceptionallyCompose

Tạo tệp **`RecoveryOperatorsDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.atomic.AtomicInteger;

public class RecoveryOperatorsDemo {
    public static void main(String[] args) {
        CompletableFuture<String> failed =
                CompletableFuture.failedFuture(
                        new IllegalArgumentException("invalid id"));

        AtomicInteger observerCalls = new AtomicInteger();

        CompletableFuture<String> observed =
                failed.whenComplete((value, error) ->
                        observerCalls.incrementAndGet());

        String recovered = observed
                .exceptionally(error -> "cached")
                .thenApply(String::toUpperCase)
                .join();

        String handled = failed
                .handle((value, error) ->
                        error == null ? value : "unavailable")
                .join();

        String composed = failed
                .exceptionallyCompose(error ->
                        CompletableFuture.completedFuture("backup"))
                .join();

        CompletableFuture<String> observerFailure =
                CompletableFuture.completedFuture("ok")
                        .whenComplete((value, error) -> {
                            throw new IllegalStateException(
                                    "observer failed");
                        });

        String observerCause;
        try {
            observerFailure.join();
            throw new AssertionError("Expected observer failure");
        } catch (CompletionException e) {
            observerCause =
                    e.getCause().getClass().getSimpleName();
        }

        System.out.println("observerCalls=" + observerCalls.get());
        System.out.println(
                "observedExceptional=" + observed.isCompletedExceptionally());
        System.out.println("recovered=" + recovered);
        System.out.println("handled=" + handled);
        System.out.println("composed=" + composed);
        System.out.println("observerFailure=" + observerCause);
    }
}
```

Chạy:

```bash
javac RecoveryOperatorsDemo.java
java RecoveryOperatorsDemo
```

Stdout:

```text
observerCalls=1
observedExceptional=true
recovered=CACHED
handled=unavailable
composed=backup
observerFailure=IllegalStateException
```

Giải thích từng kết quả:

1. `failed` đã exceptional trước khi tạo các dependents.
2. `whenComplete` chạy một lần, tăng counter và return bình thường; future `observed` **vẫn exceptional**.
3. `exceptionally` gắn phía sau `observed` biến lỗi thành `"cached"`, rồi stage tiếp theo viết hoa.
4. `handle` chạy với error không null, trả `"unavailable"` thành normal completion.
5. `exceptionallyCompose` trả một future fallback đã thành công `"backup"`, kết quả được flatten.
6. Một `whenComplete` observer ném lỗi khi upstream success sẽ làm dependent future **exceptional do chính observer**, dù upstream ban đầu mang `"ok"`.

Không có scheduling không xác định trong demo: mọi upstream dùng `completedFuture/failedFuture`; output minh họa **semantics của operator**, không phải benchmark.

## 10. Vị trí đặt recovery thay đổi ý nghĩa nghiệp vụ

Xét hai pipeline:

**Phục hồi sớm:**

```java
CompletableFuture<Integer> result = load()
        .exceptionally(error -> defaultValue())
        .thenApply(value -> validate(value))
        .thenApply(value -> persist(value));
```

**Phục hồi muộn:**

```java
CompletableFuture<Integer> result = load()
        .thenApply(value -> validate(value))
        .thenApply(value -> persist(value))
        .exceptionally(error -> defaultValue());
```

Cả hai là snippets với methods kiểu trả về phù hợp. Ý nghĩa rất khác:

- **Early recovery**: nếu `load` lỗi, stage sau vẫn chạy với **default value**. Đó có thể là điều mong muốn cho dữ liệu optional, hoặc nguy hiểm nếu việc ghi dựa vào dữ liệu thực.
- **Late recovery**: mọi lỗi ở load, validate hoặc persist đều có thể bị thay bằng default. Nếu persist là side effect quan trọng, late recovery dễ che nguyên nhân hỏng giao dịch.
- Nếu `defaultValue()` tự ném exception, dependent future vẫn exceptional.
- `exceptionally` chỉ bắt lỗi của **phần chuỗi phía trước nó**. Nó không tự bắt exception từ những stages được gắn **sau nó**, trừ khi tạo một handler khác ở phía sau.
- Mỗi lời `thenApply` tạo future mới; hai branches gắn ở điểm khác nhau có thể có policy lỗi khác nhau.

**Thiết kế tốt:** đặt error boundary ở ranh giới đúng của **một bước có thể được thay thế an toàn**. Lỗi không thể recover nên lan truyền tới tầng owner có khả năng đưa ra quyết định nghiệp vụ.

## 11. Synchronous/Async callback và nơi lỗi được ném

Các method như `thenApply`, `handle`, `whenComplete` có bản thường và bản `Async`. Với bản thường, callback có thể chạy trong thread hoàn tất predecessor hoặc thread khác đang thực hiện một completion-related action. **Không cam kết nó luôn chạy trên thread submit ban đầu**.

Với `thenApplyAsync(fn, executor)`, callback được lên lịch vào executor chỉ định. Nếu executor không còn nhận tasks hoặc handler ném exception, dependent future có thể exceptional. Với các overload không truyền executor, default async facility thường dùng `ForkJoinPool.commonPool` với các điều kiện JDK nêu rõ, nhưng không dựa vào thread name cố định cho correctness.

### Exception bên trong callback không thoát trực tiếp ra caller tạo pipeline

```java
CompletableFuture<Integer> stage =
        CompletableFuture.completedFuture(1)
                .thenApply(value -> {
                    throw new IllegalStateException("boom");
                });
```

Đây là snippet. Thông thường exception được **capture vào dependent future `stage`**, không buộc caller phải catch ngay quanh lời gọi `thenApply`. Caller quan sát qua `join/get/handler`. Điều này rất quan trọng: có một callback chạy xong nhưng không có log nào không nghĩa là task thành công — lỗi có thể đang nằm trong exceptional future.

**Trường hợp khác:** `executor.submit`/scheduling operation có thể ném lỗi đồng bộ như rejection ngay ở nơi gọi API. Phân biệt lỗi **khi đăng ký stage** và lỗi **trong asynchronous stage**; contract cụ thể quyết định nơi thấy exception.

## 12. `join()` so với `get()`: unwrap exception cho đúng

| API | Trường hợp thành công | Trường hợp thất bại thông thường | Interruptibility |
| --- | --- | --- | --- |
| `future.join()` | Trả value | Thường ném unchecked `CompletionException` bao cause | Không khai báo `InterruptedException` |
| `future.get()` | Trả value | Ném checked `ExecutionException` bao cause | Có thể ném `InterruptedException` |
| `future.get(timeout, unit)` | Trả value trước deadline | `ExecutionException` nếu future lỗi, `TimeoutException` nếu chờ quá deadline | Có thể bị interrupt |
| `future.join()` khi **future bị cancel trực tiếp** | Không có value | Có thể ném trực tiếp `CancellationException` | Không phải cancellation recovery |
| `get()` khi future bị cancel | Không có value | Ném `CancellationException` | Như contract Future |

Lỗi **được propagate qua dependent stage** có thể nằm bên trong một `CompletionException` có cause là `CancellationException`. Vì vậy không nên bắt duy nhất `CancellationException` trên **mọi dependent futures** rồi kỳ vọng luôn đúng. Hãy kiểm tra lớp wrapper và root cause.

### Mẫu unwrap có giới hạn

```java
static Throwable rootCause(Throwable error) {
    Throwable cursor = error;
    while ((cursor instanceof CompletionException
            || cursor instanceof ExecutionException)
            && cursor.getCause() != null) {
        cursor = cursor.getCause();
    }
    return cursor;
}
```

Đây là snippet, import `java.util.concurrent.CompletionException` và `ExecutionException`. Nó gỡ **những wrapper chuẩn thường gặp**, không có nghĩa luôn phải unwrap tới mọi nested cause của business exception. Nếu các tầng dùng custom exceptions có thông tin ngữ cảnh, hãy giữ nguyên chúng trong logs và error response; unwrap chỉ để **phân loại** lỗi phù hợp.

Không dùng `future.getNow(default)` như cơ chế recover mọi failure: nếu future đã hoàn tất bất thường, method đó vẫn có thể ném unchecked exception theo contract. Nếu cần fallback thực sự, dùng `exceptionally/handle`.

### Đừng nhầm `isDone` với success

`isDone()` có thể true cho **normal**, **exceptional** hoặc **cancelled** completion. `isCompletedExceptionally()` cho biết outcome exceptional, nhưng không thay thế đọc cause. `isCancelled()` trả true cho cancellation của future tương ứng, không khẳng định mọi computation worker đã bị hủy xong.

## 13. `thenCompose`: lỗi lan qua các tầng asynchronous

`thenCompose(fn)` thường dùng khi stage hiện tại cần gọi một asynchronous operation thứ hai. Nó **flatten** `CompletionStage<CompletionStage<U>>` thành một stage `U`:

```java
CompletableFuture<Order> result = fetchOrder(orderId)
        .thenCompose(order -> fetchDetails(order)
                .thenApply(details -> enrich(order, details)));
```

Đây là snippet, các types/methods do ứng dụng định nghĩa.

Các đường lỗi:

- `fetchOrder` lỗi → callback `thenCompose` không chạy; không gọi `fetchDetails`.
- `fetchOrder` success nhưng callback ném exception → composed stage exceptional.
- Callback trả future `fetchDetails`, và future ấy thất bại → lỗi của inner future được propagate tới stage bên ngoài.
- Callback trả `null` thay vì một `CompletionStage` hợp lệ → dependent stage exceptional (thường do null-related failure), không phải một normal null result.
- `enrich` ném exception → final future exceptional.

**Không làm mất kết quả bất đồng bộ** bằng cách viết:

```java
.thenApply(order -> fetchDetails(order))
```

nếu `fetchDetails` trả `CompletableFuture<Details>`. Đó là stage **nested** `CompletableFuture<CompletableFuture<Details>>`, và lỗi của inner future không tự được coi là kết quả lỗi của `thenApply` ngoài theo ý bạn. `thenCompose` là dạng đúng khi muốn kết quả và lỗi của inner stage **lan truyền**.

### Fail-fast theo business stage

Nếu một bước xác thực/thanh toán bắt buộc thất bại, stage downstream thường nên bị skip. Dùng `thenCompose`/`thenApply` mà **không recover** tại bước ấy trừ khi fallback nghiệp vụ thực sự hợp lệ. Error handler có thể đặt ở ranh giới request để tạo response lỗi phù hợp.

## 14. Fan-in: `allOf` khi một trong nhiều tác vụ lỗi

`CompletableFuture.allOf(f1,f2,f3)` tạo một future hoàn tất khi **tất cả các futures được cung cấp đã hoàn tất**. Nếu một future exceptional, `allOf` cũng exceptional. Nhưng:

- `allOf` trả `CompletableFuture<Void>`, **không gom giá trị** của các futures.
- Nó **không tự cancel sibling futures** khi một nhánh lỗi.
- Nếu nhiều nhánh lỗi, exception của aggregate thường **không đại diện đầy đủ mọi nguyên nhân**; không phụ thuộc vào “exception nào được chọn đầu tiên”.
- Khi `allOf` exceptional, một callback `thenRun/thenApply` phụ thuộc success sẽ bị skip.
- Muốn lấy mọi lỗi để báo cáo, cần đọc **outcomes của từng future** sau khi allOf hoàn tất hoặc gắn handler riêng vào từng nhánh.

### Dùng handler biến mỗi outcome thành một giá trị rõ ràng

```java
CompletableFuture<Result<Integer>> safeA =
        taskA.handle((value, error) ->
                error == null
                        ? Result.success(value)
                        : Result.failure(error));

CompletableFuture<Result<Integer>> safeB =
        taskB.handle((value, error) ->
                error == null
                        ? Result.success(value)
                        : Result.failure(error));
```

Đây là snippet giả định có type `Result<T>` phù hợp; `taskA/taskB` là `CompletableFuture<Integer>`. Lúc này `allOf(safeA,safeB)` có thể hoàn tất bình thường nếu **các handlers đều return bình thường**, rồi caller thu cả success/failure records. Điều đó **không tự động biến business workflow thành thành công**: tầng quyết định vẫn phải kiểm tra có lỗi nào bắt buộc abort.

Không nên swallow mọi lỗi bằng `exceptionally(error -> null)` rồi coi null là dữ liệu hợp lệ nếu không có outcome type rõ. Đặc biệt tránh làm mất error context khi fan-in.

## 15. Java 17: allOf và anyOf không tự recover

Tạo tệp **`FanInFailureDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.atomic.AtomicBoolean;

public class FanInFailureDemo {
    static String causeName(CompletableFuture<?> stage) {
        try {
            stage.join();
            return "none";
        } catch (CompletionException e) {
            return e.getCause().getClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        CompletableFuture<Integer> first = new CompletableFuture<>();
        CompletableFuture<Integer> second = new CompletableFuture<>();
        CompletableFuture<Integer> third = new CompletableFuture<>();

        CompletableFuture<Void> all =
                CompletableFuture.allOf(first, second, third);

        AtomicBoolean nextStageRan = new AtomicBoolean(false);
        CompletableFuture<Integer> next = all.thenApply(ignore -> {
            nextStageRan.set(true);
            return first.join() + second.join() + third.join();
        });

        first.complete(1);
        second.completeExceptionally(
                new IllegalStateException("subtask failed"));
        boolean allStillWaiting = !all.isDone();
        third.complete(3);

        System.out.println("allStillWaiting=" + allStillWaiting);
        System.out.println("allCause=" + causeName(all));
        System.out.println("nextStageRan=" + nextStageRan.get());
        System.out.println("nextCause=" + causeName(next));

        CompletableFuture<Integer> fastFailure = new CompletableFuture<>();
        CompletableFuture<Integer> slowSuccess = new CompletableFuture<>();
        CompletableFuture<Object> any =
                CompletableFuture.anyOf(fastFailure, slowSuccess);

        fastFailure.completeExceptionally(
                new IllegalArgumentException("first finished with error"));
        slowSuccess.complete(99);

        System.out.println("anyCause=" + causeName(any));
    }
}
```

Chạy:

```bash
javac FanInFailureDemo.java
java FanInFailureDemo
```

Stdout:

```text
allStillWaiting=true
allCause=IllegalStateException
nextStageRan=false
nextCause=IllegalStateException
anyCause=IllegalArgumentException
```

**Lập luận:**

1. `allOf` được gắn khi ba futures còn incomplete.
2. `first` thành công, `second` exceptional, nhưng `third` chưa complete → `allOf.isDone()==false` theo contract “all”.
3. Sau `third.complete(3)`, aggregate exceptional do second lỗi; callback `thenApply` sau aggregate bị skip.
4. `anyOf` được tạo khi cả hai inputs chưa complete; ta **chủ động complete failure trước** rồi mới complete success, nên winner là lỗi, aggregate exceptional. Nó **không** tự bỏ qua lỗi để đợi một success sau.
5. Không có scheduler chạy bất đồng bộ trong demo; các lần `complete` được gọi tuần tự, giúp output ổn định.

**Giới hạn quan trọng:** khi nhiều futures thật sự chạy đồng thời và thất bại gần nhau, `allOf` có thể chọn cause nào để đại diện aggregate theo internal completion semantics. Đừng assert tên một lỗi cụ thể khi **nhiều nhánh cùng lỗi** mà bạn không kiểm soát order/selection. Muốn đủ errors, lưu outcomes từng nhánh.

## 16. `anyOf` không phải “first successful result”

`anyOf` kết thúc theo **future đầu tiên hoàn tất**; nếu future ấy exceptional, aggregate cũng exceptional ngay. Một success đến sau không làm nó tự hồi phục.

Nếu yêu cầu là **first successful**, cần một thuật toán riêng:

- Duyệt/callback cho từng candidate, hoàn tất một promise thành công bằng `complete(value)` khi có success đầu tiên.
- Đếm failures và chỉ `completeExceptionally` khi **tất cả candidates đã thất bại**.
- Xem xét hủy các losers và quản lý cleanup/resource của các tasks vẫn chạy.
- Quyết định precedence giữa cancellation, timeout và success race.
- Không dùng một `AtomicBoolean` success mà quên happens-before/publication của payload.

Trong nhiều trường hợp, composition library hoặc domain-specific abstraction có thể làm việc này rõ ràng hơn. Nhưng **không gọi `anyOf` là first-success** vì cái tên dễ gây hiểu nhầm.

### Không có inputs

`allOf()` với mảng rỗng trả future đã completed bình thường; `anyOf()` với mảng rỗng trả một future chưa completed. Khi có thể nhận danh sách trống, phải định nghĩa semantics rõ, nếu không `join()` trên `anyOf()` không có input có thể chờ mãi.

## 17. Cancellation cũng là một đường exceptional completion

`CompletableFuture.cancel(mayInterruptIfRunning)` làm future hoàn tất bất thường bằng `CancellationException` nếu cancellation được chấp nhận. Các dependent stages chưa hoàn tất thường cũng hoàn tất bất thường (thường với `CompletionException` mà cause là `CancellationException`).

**Đặc biệt về implementation của CompletableFuture:** tham số `mayInterruptIfRunning` **không được dùng để điều khiển interruption** trong implementation này theo API documentation. Gọi `cf.cancel(true)` **không phải cam kết thread đang chạy supplier đã bị interrupt**.

### Java 17: cancellation lan sang dependent stage

Tạo **`CancellationAndTimeoutDemo.java`**:

```java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class CancellationAndTimeoutDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> source = new CompletableFuture<>();
        AtomicBoolean downstreamRan = new AtomicBoolean(false);

        CompletableFuture<Integer> dependent =
                source.thenApply(value -> {
                    downstreamRan.set(true);
                    return value + 1;
                });

        boolean cancelled = source.cancel(true);

        String dependentCause;
        try {
            dependent.join();
            throw new AssertionError("Expected dependent failure");
        } catch (CompletionException e) {
            dependentCause =
                    e.getCause().getClass().getSimpleName();
        }

        CompletableFuture<Integer> timedOut = new CompletableFuture<>();
        timedOut.orTimeout(50, TimeUnit.MILLISECONDS);

        String timeoutCause;
        try {
            timedOut.join();
            throw new AssertionError("Expected timeout");
        } catch (CompletionException e) {
            timeoutCause =
                    e.getCause().getClass().getSimpleName();
        }

        CompletableFuture<Integer> defaulted = new CompletableFuture<>();
        defaulted.completeOnTimeout(7, 50, TimeUnit.MILLISECONDS);

        System.out.println("cancelAccepted=" + cancelled);
        System.out.println("sourceCancelled=" + source.isCancelled());
        System.out.println("dependentCancelled=" + dependent.isCancelled());
        System.out.println("downstreamRan=" + downstreamRan.get());
        System.out.println("dependentCause=" + dependentCause);
        System.out.println("timeoutCause=" + timeoutCause);
        System.out.println("timeoutDefault=" + defaulted.join());
    }
}
```

Chạy:

```bash
javac CancellationAndTimeoutDemo.java
java CancellationAndTimeoutDemo
```

Stdout bình thường:

```text
cancelAccepted=true
sourceCancelled=true
dependentCancelled=false
downstreamRan=false
dependentCause=CancellationException
timeoutCause=TimeoutException
timeoutDefault=7
```

Giải thích:

- `source.cancel(true)` chuyển `source` sang cancelled. Dependent `thenApply` không có value thành công để xử lý, nên callback không chạy.
- Dependent exceptional bằng wrapper `CompletionException` có cause `CancellationException`, nhưng **không được cancel trực tiếp**, nên `dependent.isCancelled()` là false.
- `orTimeout` hoàn tất **chính future được gọi** bằng `TimeoutException` nếu tới hạn mà nó vẫn incomplete. Trong demo không ai complete `timedOut`, nên nó timeout.
- `completeOnTimeout(7, ...)` hoàn tất **chính future được gọi** bằng giá trị `7` khi tới hạn và future vẫn incomplete. Đây là **normal completion**, không phải exception.
- Demo không tạo supplier đang chạy, nên **không chứng minh thread interruption**. Trong ứng dụng thật, timeout/cancel của CompletableFuture không đảm bảo dừng I/O/tác vụ nền; phải thiết kế resource timeout/cooperative cancellation riêng.

Các khoảng 50 ms tạo đường timeout có chủ đích. Chương trình dùng `join()` để đợi trạng thái, không dựa vào `Thread.sleep` và không assert thời gian scheduler đánh thức chính xác 50 ms.

## 18. Timeout không giống `get(timeout)`

Đây là ba semantics thường bị nhầm:

| API | Future gốc bị thay trạng thái không? | Khi timeout | Tác vụ nền có dừng không? |
| --- | --- | --- | --- |
| `future.get(100, MILLISECONDS)` | **Không** chỉ vì caller timeout | Caller nhận `TimeoutException` | Không tự hủy task |
| `future.orTimeout(100, MILLISECONDS)` | **Có**, nếu future vẫn incomplete | Future hoàn tất exceptional bằng `TimeoutException` | Không được cam kết dừng computation |
| `future.completeOnTimeout(default, 100, MILLISECONDS)` | **Có**, nếu future vẫn incomplete | Future hoàn tất bình thường bằng default | Không được cam kết dừng computation |

**Quan trọng:** `orTimeout` và `completeOnTimeout` trả **chính CompletableFuture đó** để hỗ trợ chaining, chứ không luôn tạo một dependent future mới. Nếu nhiều callers cùng giữ reference của future gốc, họ cũng thấy trạng thái bị thay đổi khi timeout áp dụng.

Một nguồn công việc thực tế có thể hoàn tất **sau** khi future đã timeout. Lời `complete(value)` muộn sẽ không thay trạng thái đã hoàn tất bình thường/bất thường trước đó. Nhưng công việc/supplier **vẫn có thể tiêu CPU, giữ connection hoặc tạo side effect** nếu không được hủy hợp tác.

Nếu muốn **timeout chỉ tại điểm chờ của một caller** mà không thay đổi future nguồn, `get(timeout, unit)` có ý nghĩa khác. Nếu muốn timeout một **dependent view**, cần thiết kế wrapper/view riêng một cách có chủ đích.

## 19. Retry sau exceptional completion: đừng tưởng `exceptionally` tự retry

Một callback `exceptionally` **không chạy lại supplier nguồn**. Nó chỉ nhận exception và có thể trả fallback value. Muốn retry operation, phải **gọi lại logic tạo attempt mới** theo policy:

- Chỉ retry lỗi transient thực sự an toàn.
- Có giới hạn số attempts, deadline, backoff/jitter khi cần.
- Phân biệt request đã tạo side effect nhưng response bị mất; retry có thể thực hiện side effect lần thứ hai.
- Giữ idempotency key hoặc cơ chế deduplication/transaction nếu nghiệp vụ yêu cầu.
- Không block một executor thread bằng vòng `Thread.sleep`/`join` chỉ để đợi retry khi có mô hình async tốt hơn.
- Không để retry “cứ thất bại rồi retry mãi” và làm tăng concurrency không giới hạn.

### Ví dụ khái niệm

```java
CompletableFuture<Result> primary = attemptAsync();

CompletableFuture<Result> withOneRetry =
        primary.exceptionallyCompose(error -> {
            if (!isTransient(error)) {
                return CompletableFuture.failedFuture(error);
            }
            return attemptAsync();
        });
```

Đây là **snippet**, `Result/attemptAsync/isTransient` do ứng dụng định nghĩa. Nó tạo **attempt mới đúng một lần** khi lỗi được phân loại transient; nếu second attempt thất bại, lỗi của attempt mới propagate. Trong thực tế phải xử lý exception wrapper trước khi phân loại, và quản lý timeout/cancellation xuyên các attempts.

**Không ghi `exceptionally(error -> primary.join())`**: `primary` đã thất bại, nên `join()` chỉ ném lỗi cũ và không tạo retry.

## 20. Nếu handler ném exception hoặc trả future lỗi thì sao?

Các callback xử lý lỗi **không miễn nhiễm với failure**. Chúng có thể:

- Ném `IllegalStateException` do bug.
- Gọi DB/network và thất bại.
- Return một `CompletableFuture.failedFuture(...)` qua `exceptionallyCompose`.
- Đọc state đã bị shutdown/close.
- Bị executor từ chối scheduling nếu dùng bản Async.
- Gặp cancellation hoặc timeout ở fallback stage.

Ví dụ:

```java
CompletableFuture<Integer> recovered =
        source.exceptionally(error -> {
            throw new IllegalStateException("fallback failed");
        });
```

Đây là snippet, `source` là `CompletableFuture<Integer>`. Nếu source lỗi, callback ném → future `recovered` cũng exceptional, lần này do **fallback failed**. Exception gốc có thể không còn là exception chính của dependent. Nếu cần giữ cả hai, ứng dụng phải chủ động thiết kế chained causes/suppressed exceptions hoặc outcome object; không mặc định tất cả lỗi từ mọi đường nhánh được CompletableFuture lưu lại.

**Khi nào nên gắn `whenComplete` cuối pipeline?** Khi chỉ muốn log outcome cuối, bảo toàn exception chính của pipeline nếu callback không ném. Nhưng một observer throw cũng là lỗi; tránh để logging/metrics làm hỏng một kết quả nghiệp vụ thành công.

## 21. Exception handling và thread interruption

Một method `Future.get()` có thể ném `InterruptedException` nếu **thread đang chờ** bị interrupt. Điều này khác với một CompletableFuture **đã complete exceptionally vì `InterruptedException`** của worker. Phải phân biệt:

- **Interrupt caller đang đợi:** `get()` ném `InterruptedException` trực tiếp; thread caller nên propagate hoặc restore flag rồi thoát theo policy.
- **Supplier xử lý interrupt thành exceptional completion:** `get()` có thể ném `ExecutionException` với cause là một `InterruptedException` hoặc wrapper; đó là lỗi *của công việc* được báo qua future.
- **`join()` không khai báo `InterruptedException`**: không vì thế mà nó trở thành cơ chế cancel/cleanup.
- **`CompletableFuture.cancel(true)`**: không bảo đảm interrupt worker của supplier.
- **`FutureTask.cancel(true)`** từ executor khác có semantics may-interrupt khác; không suy diễn chúng giống hệt CompletableFuture.

Mẫu chờ đúng khi API cho phép truyền interruption:

```java
try {
    Result result = stage.get();
    consume(result);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    stopWaiting();
} catch (ExecutionException e) {
    handleTaskFailure(e.getCause());
}
```

Đây là snippet, các types/methods `Result/consume/stopWaiting/handleTaskFailure` do ứng dụng định nghĩa. Nếu method được phép khai báo `throws InterruptedException`, có thể **propagate** thay vì bắt và restore. Khi caller bị interrupt, đừng mặc định tất cả upstream stages đã được hủy; cần lifecycle control riêng.

## 22. Lỗi bên trong worker và lỗi của cả workflow

Một pipeline có thể có nhiều mức lỗi:

1. **Business validation**: invalid input; thường không retry.
2. **Transient I/O**: timeout, rate limit; có thể retry nếu idempotent.
3. **Permanent dependency failure**: service not available; fallback có thể hay không tùy contract.
4. **Cancellation**: user bỏ request hoặc deadline hết; thường nên dừng phần việc không cần thiết.
5. **Programming bug**: `NullPointerException`, invariant violation; không nên nuốt bằng một default bất kỳ.
6. **Resource exhaustion**: executor rejection, OOM risk, connection pool exhaustion; cần backpressure và telemetry.
7. **Observer/cleanup failure**: không thay thế lỗi gốc một cách âm thầm.

Khi thiết kế handler, nên định nghĩa **policy theo loại lỗi** thay vì “catch mọi Throwable rồi trả null”.

### Làm rõ outcome bằng kiểu dữ liệu

Một kiểu `sealed interface Result<T>` hoặc record `Success/Failure` có thể phù hợp khi nhiều nhánh cần thu và báo cáo lỗi có cấu trúc. Nhưng khi quyết định biến exception thành `Result.Failure`, hãy nhớ future sẽ hoàn tất **bình thường** với object Failure; các stage `thenApply` phía sau vẫn chạy nếu không kiểm tra status. Đây là lựa chọn API rõ ràng, không phải mechanism mặc định của CompletableFuture.

## 23. Propagation ở nhánh phụ và lỗi không được ai quan sát

Một future có thể exceptional mà **không ai gọi `get/join` hoặc gắn handler**, vì CompletableFuture không tự động in stack trace của mọi stage đã thất bại. Do đó:

```java
fireAndForgetAsync()
        .thenApply(value -> riskyTransform(value));
```

là snippet, có thể khiến lỗi bị giữ trong dependent future nhưng không được xử lý nếu ứng dụng bỏ reference. Với background work, cần owner quan sát completion, metric/error reporting và shutdown policy.

### Nhưng đừng log cùng lỗi ở mọi stage

Nếu mỗi stage gọi `whenComplete` rồi log stack trace cùng một failure, một lỗi gốc có thể tạo 10 log giống nhau. Chọn ranh giới phù hợp:

- Log **lần đầu** ở source nếu cần thông tin technical.
- Log **business outcome** ở request boundary.
- Dùng trace/correlation ID liên kết stages.
- Tránh leak dữ liệu nhạy cảm qua exception logs.
- Ghi aggregated status cho fan-in thay vì chỉ lỗi ngẫu nhiên một nhánh.

## 24. Lỗi trong `thenCombine`, `allOf` và dependencies nhiều nguồn

Với hai futures:

```java
CompletableFuture<Result> result =
        left.thenCombine(right, (a, b) -> combine(a, b));
```

Đây là snippet giả định các types/methods phù hợp. Nếu `left` hoặc `right` exceptional, callback `combine` không được gọi theo normal path. Nhưng **lỗi kết quả là lỗi của dependency**, không có nghĩa dependency còn lại tự bị cancel. Nếu cả hai thất bại, error selected cần được xem như **một outcome đại diện**, không thay đầy đủ logs của cả hai branches.

Tương tự với `allOf`, việc chờ các thành phần và tổng hợp kết quả sau khi tất cả complete là hai bước riêng. Một phương án thu đủ nguyên nhân:

```java
CompletableFuture<Outcome<A>> a = aTask
        .handle((value, error) -> toOutcome(value, error));

CompletableFuture<Outcome<B>> b = bTask
        .handle((value, error) -> toOutcome(value, error));

CompletableFuture<Void> all = CompletableFuture.allOf(a, b);
```

Đây là snippet, cần định nghĩa `Outcome` và `toOutcome`. Nếu từng handler **không ném**, `all` có thể thành công rồi controller đọc outcomes và quyết định retry/abort. **Không được biến mọi handler thành success rồi bỏ qua field error**.

Nếu yêu cầu **fail fast** và dừng sibling ngay khi một nhánh lỗi, `allOf` không tự cung cấp cơ chế đó. Cần cancellation propagation, quản lý tasks và resource cleanup riêng. Với dữ liệu cần consistent snapshot, đôi khi nên dùng transactional workflow hơn là ghép futures trần.

## 25. `minimalCompletionStage()`, `copy()` và việc bảo vệ upstream

Trong thiết kế thư viện, đôi khi bạn không muốn caller có quyền gọi `complete` hoặc `completeExceptionally` lên future nội bộ. `CompletableFuture.minimalCompletionStage()` cung cấp một view giới hạn các phương thức completion, còn `copy()` tạo một dependent future phản ánh completion của nguồn theo hợp đồng API.

Các thao tác đó giúp **giới hạn quyền can thiệp**, không làm cho lỗi tự disappear. Normal/exceptional outcome vẫn cần xử lý. `CompletionStage` có thể là kiểu trả về API phù hợp để không phơi toàn bộ mutator methods của `CompletableFuture`.

**Cảnh báo:** `toCompletableFuture()` từ một `CompletionStage` không luôn là reference gốc có thể mutate mà bạn sở hữu; đọc contract implementation. Không dùng `obtrudeException` để ép outcome vào một future đã hoàn tất trong workflow bình thường: dependents đã được trigger trước đó có thể giữ kết quả cũ và làm state hệ thống khó suy luận.

## 26. Những ngộ nhận phổ biến

| Ngộ nhận | Sai ở đâu? | Hướng đúng |
| --- | --- | --- |
| “`thenApply` vẫn chạy khi upstream lỗi với giá trị null” | Callback success bị skip | `exceptionally/handle` nếu cần recover |
| “`exceptionally` chỉ để log, không đổi outcome” | Return value biến failure thành success | Dùng `whenComplete` để quan sát |
| “`whenComplete` sẽ catch và recover exception” | Observer không recover | Gắn `exceptionally/handle` sau đó |
| “`handle` log rồi return value là an toàn” | Trên lỗi value có thể null, error bị nuốt | Propagate hoặc chuyển thành explicit outcome |
| “`join` và `get` ném cùng checked exception” | Wrapper/interrupt semantics khác | Bắt `CompletionException` vs `ExecutionException` |
| “`isDone()` đồng nghĩa thành công” | Exceptional/cancelled cũng done | Đọc outcome và cause |
| “`thenApply` với future-returning callback sẽ flatten” | Sinh nested future | `thenCompose` |
| “`allOf` hủy siblings ngay khi một lỗi” | Nó không tự cancel | Thiết kế cancellation riêng |
| “`allOf` gom mọi giá trị” | Trả `Void` | Đọc từng future sau completion |
| “`anyOf` trả success đầu tiên” | Nó lấy **completion** đầu tiên, có thể lỗi | First-success algorithm riêng |
| “`cancel(true)` trên CompletableFuture luôn interrupt worker” | CompletableFuture không điều khiển interrupt theo flag này | Cooperative cancellation/resource timeout |
| “`orTimeout` chỉ timeout caller” | Nó hoàn tất chính future nếu vẫn incomplete | `get(timeout)` để chỉ giới hạn wait |
| “`completeOnTimeout` tạo exception” | Nó hoàn tất bằng default value | Tách fallback và error theo contract |
| “Recover cuối chuỗi luôn tốt” | Có thể che lỗi ghi/payment | Placement theo bước có fallback hợp lệ |
| “Callback không ai gọi get thì JVM tự log lỗi” | Future có thể giữ exception im lặng | Observe ở owner boundary |
| “`exceptionally` tự retry supplier” | Không tạo attempt mới | Retry bằng supplier mới và policy |
| “`whenComplete` không thể làm stage đang success thất bại” | Observer ném có thể làm dependent exceptional | Observer nhẹ và an toàn |
| “Nhiều nhánh lỗi thì aggregate giữ tất cả errors” | Có thể chỉ một cause đại diện | Thu từng outcome riêng |
| “Async luôn non-blocking” | Supplier và `join` vẫn có thể block | Chọn executor và composition đúng |
| “Future đã cancelled nghĩa resource đã đóng” | Worker có thể vẫn chạy | Completion/cleanup handshake riêng |

## 27. Quy trình debug exception bị “mất” trong chuỗi

1. **Vẽ stage graph**, đánh dấu mỗi `thenApply/thenCompose/handle/exceptionally/whenComplete`.
2. **Xác định stage đầu tiên lỗi**: stack trace/source exception, không chỉ top-level `CompletionException`.
3. **Đánh dấu stages bị skip**: success callbacks không chạy nếu predecessor exceptional.
4. **Tìm recovery point**: có `exceptionally` trả default, `handle` return null hoặc `exceptionallyCompose` gọi fallback không?
5. **Tách nhánh**: có hai downstream futures từ cùng source, một recover và một vẫn lỗi?
6. **Phân biệt wrapper**: `join` → `CompletionException`; `get` → `ExecutionException`; direct cancel → `CancellationException`.
7. **Đếm fan-in failures**: `allOf` có bao nhiêu input exceptional, input nào chưa complete?
8. **Kiểm tra observer errors**: `whenComplete` logging/metrics có ném exception không?
9. **Kiểm tra cancellation/timeout**: `orTimeout` có mutate chính future không? Worker có còn chạy không?
10. **Kiểm tra thread starvation**: có `join/get` blocking ngay trong executor mà fallback cũng cần executor ấy?
11. **Kiểm tra executor rejection/shutdown**: callback `Async` được schedule thành công không?
12. **Kiểm tra ownership**: ai phải quan sát lỗi và cleanup sau khi response hoặc workflow kết thúc?
13. **Kiểm tra retry**: fallback có lặp side effects không, có quá nhiều tasks outstanding không?
14. **Test với future đã completed/failed**: isolate propagation khỏi scheduling noise.
15. **Báo cả nguyên nhân gốc và boundary**: log ngữ cảnh đủ nhưng không lặp hoặc lộ thông tin nhạy cảm.

### Kiểm thử paths thay vì chỉ happy path

Một bộ test tối thiểu nên có:

- Source thành công, toàn bộ stages thành công.
- Source exceptional, các `thenApply` callback bị skip.
- Intermediate stage ném unchecked exception; downstream skip.
- `thenCompose` trả inner future exceptional.
- `exceptionally` recover đúng lỗi; unexpected lỗi vẫn propagate.
- `handle` có case success/error và không vô tình nuốt lỗi.
- `whenComplete` observer thành công và observer ném.
- `exceptionallyCompose` fallback thành công và fallback thất bại.
- `allOf` một input lỗi, input khác chưa hoàn tất, nhiều inputs lỗi.
- `anyOf` winner failure rồi follower success.
- `cancel` nguồn và error propagation tới dependent.
- `get(timeout)` so với `orTimeout/completeOnTimeout`.
- Worker cleanup sau cancellation, không chỉ future state.
- Shutdown/executor rejection trên `Async` callbacks.
- Error metrics/logging không lặp và có correlation ID.

## 28. Câu hỏi tự kiểm tra

**1. `thenApply` có được gọi nếu predecessor exceptional không?** Không; dependent future mang lỗi, trừ khi stage đã được recovery trước khi tới thenApply.

**2. `exceptionally` có thay đổi trạng thái future gốc không?** Không; nó trả dependent future mới, có thể normal nếu callback trả fallback.

**3. `whenComplete` có recover không?** Không. Nếu observer return bình thường, outcome gốc được bảo toàn.

**4. `handle` có thể đổi lỗi thành thành công không?** Có. Nếu handler return value bình thường khi error không null, dependent future thành công.

**5. `exceptionallyCompose` khác `exceptionally` ở đâu?** Nó trả một `CompletionStage` làm đường fallback, tránh `join` để lấy giá trị trong handler.

**6. `thenCompose` có giữ lỗi inner future không?** Có; inner future exceptional khiến composed stage exceptional.

**7. `thenApply` trả một future có tự flatten không?** Không. Nó tạo nested stage với future là value.

**8. Vì sao `join()` thường thấy `CompletionException`?** Đây là wrapper unchecked theo API để truyền cause từ asynchronous stage.

**9. `get()` có thể ném gì khi worker thất bại?** `ExecutionException` bao cause, ngoài interruption/cancellation cases.

**10. `allOf` có gom các giá trị không?** Không; trả `CompletableFuture<Void>`, chỉ báo tất cả đã hoàn tất.

**11. `allOf` có tự cancel các siblings khi một input fail không?** Không.

**12. `anyOf` có đảm bảo thành công nếu một input success về sau không?** Không. Nếu winner đầu tiên failed, `anyOf` đã exceptional.

**13. Future `isDone()==true` có nghĩa value hợp lệ không?** Không; exceptional/cancelled cũng là done.

**14. `CompletableFuture.cancel(true)` có chắc interrupt worker supplier không?** Không; `mayInterruptIfRunning` không được dùng để điều khiển interruption của CompletableFuture theo docs.

**15. `orTimeout` có tạo một future độc lập không?** Không; nó hoàn tất chính CompletableFuture được gọi nếu vẫn incomplete, và trả lại cùng object.

**16. `get(timeout)` có làm future trở thành exceptional khi caller đợi quá thời gian không?** Không; caller nhận timeout nhưng future gốc vẫn có thể tiếp tục.

**17. Nếu một `whenComplete` ném lỗi trên một future đang success, chuyện gì xảy ra?** Dependent future có thể exceptional bởi observer failure.

**18. Nếu cả upstream và `whenComplete` observer cùng lỗi thì sao?** Upstream exception được ưu tiên trong outcome phụ thuộc theo contract; cần log observer failure riêng nếu quan trọng.

**19. Vì sao một `exceptionally` ở cuối chuỗi có thể nguy hiểm?** Nó có thể che cả lỗi ghi dữ liệu/side effects vốn không được phép fallback.

**20. Thế nào là retry thật sự?** Tạo và thực thi **một attempt mới**, có policy, deadline và idempotency; không phải chỉ trả một default trong exceptionally.

## 29. Checklist thiết kế production

- **Stage graph** có được mô tả đầy đủ từ source tới final result?
- Có xác định lỗi nào **recoverable**, lỗi nào phải fail toàn workflow?
- Các stages success-only có bị skip như mong đợi khi upstream lỗi?
- `exceptionally` có được đặt đúng boundary và trả fallback **thật sự hợp lệ**?
- `handle` có vô tình trả null trên error và nuốt failure không?
- `whenComplete` chỉ quan sát/log, không có I/O blocking/throw ngoài ý muốn?
- `exceptionallyCompose` được dùng khi fallback cần một async stage không?
- `thenCompose` được dùng đúng cho callback trả future, tránh nested stage?
- `join/get` có được gọi ở vị trí không gây thread starvation?
- Có unwrap `CompletionException/ExecutionException` khi **phân loại** lỗi?
- Có giữ full exception context cho logging/tracing thay vì chỉ message?
- Có xử lý cancellation/timeout riêng, không đánh đồng future state với worker termination?
- Có phân biệt `get(timeout)` và `orTimeout/completeOnTimeout`?
- `allOf` có quản lý kết quả và lỗi của **từng input**, không chỉ aggregate cause?
- `anyOf` có được dùng đúng khi muốn first **completion**, không phải first success?
- Fallback/retry có idempotency, budget, deadline và backpressure rõ?
- Async callbacks có executor được quản lý lifecycle, không dùng common pool tùy tiện?
- Owner của mỗi future chịu trách nhiệm quan sát lỗi, cleanup và shutdown?
- Tests có cases exceptional ở từng stage, fan-in, cancellation và observer failure?
- API public trả `CompletionStage`/Result type có thể giúp tránh callers mutate future nội bộ không?

**Kết luận:** Trong chuỗi `CompletableFuture`, lỗi **lan truyền qua các dependent stages** và thường **bỏ qua các callback chỉ chạy trên thành công**. `exceptionally` có thể đưa về fallback, `exceptionallyCompose` nối một fallback asynchronous, `handle` quan sát cả hai outcome và có thể chuyển đổi, còn `whenComplete` chủ yếu dùng để quan sát mà **không recover**. `join/get` phơi bày wrappers khác nhau; `allOf/anyOf` có semantics rõ nhưng không tự gom mọi lỗi, tự retry hoặc cancel siblings. Thiết kế đúng phải **đặt error boundary phù hợp nghiệp vụ**, phân loại lỗi, giữ nguyên root cause và quản lý cancellation, timeout, worker cleanup độc lập với trạng thái Future.

### Tài liệu tham khảo

- Oracle Java SE 17 API: [CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- Oracle Java SE 17 API: [CompletionStage](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html)
- Oracle Java SE 17 API: [CompletionException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionException.html)
- Oracle Java SE 17 API: [Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)