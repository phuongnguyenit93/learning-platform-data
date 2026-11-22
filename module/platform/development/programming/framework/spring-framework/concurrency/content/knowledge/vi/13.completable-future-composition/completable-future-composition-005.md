# thenAccept() và thenRun() cho bước không có kết quả

## 1. Bối cảnh và mục tiêu

Khi kết hợp các tác vụ với `CompletableFuture`, không phải bước xử lý nào cũng sinh ra kết quả mới. Có lúc cần đọc kết quả của bước trước để ghi audit, in log hoặc gửi thông báo; có lúc chỉ cần làm một hành động sau khi công việc trước hoàn thành. Hai phương thức dành cho những bước như vậy là **`thenAccept()` và `thenRun()`**.

- `thenAccept(Consumer<? super T>)`: **nhận giá trị T** từ giai đoạn trước; callback thực hiện hành động có kiểu trả về `void`.
- `thenRun(Runnable)`: **không nhận kết quả T** của giai đoạn trước; callback chỉ chạy sau khi giai đoạn trước hoàn thành bình thường.
- Cả hai trả về `CompletableFuture<Void>` nếu gọi trên `CompletableFuture<T>`. Stage mới vẫn là một future để **theo dõi hành động đã xong hay bị lỗi**.

Sau bài học, bạn có thể giải thích đúng `Void` trong pipeline; chọn callback theo nhu cầu dữ liệu; kiểm soát thứ tự giữa các bước; hiểu failure/cancellation và non-Async/Async variants; sử dụng executor do Spring quản lý khi nối vào kết quả `@Async`; và viết test không dựa vào timing tình cờ.

**Trọng tâm:** những bước **không tạo kết quả mới** trong chuỗi `CompletableFuture`. Việc chọn `thenAccept` hoặc `thenRun` không tự bảo đảm side effect được ghi bền vững, không tạo transaction, không khắc phục race condition hay giải phóng request thread nếu caller vẫn `join()` ngay.

## 2. Cơ chế CompletionStage và kiểu Void

Một `CompletableFuture<T>` có thể:

1. Hoàn thành bình thường với kết quả `T`.
2. Hoàn thành bất thường với exception/cancellation.
3. Chưa hoàn thành; callbacks đang chờ điều kiện kích hoạt.

Khi đăng ký continuation, API tạo **dependent stage**. Giai đoạn phụ thuộc chỉ hoàn thành bình thường khi giai đoạn trước thành công và callback chạy xong không ném lỗi. Callback bị bỏ qua nếu tiền nhiệm đã hoàn thành bất thường.

```text
CompletableFuture<T> source
       |
       +------ success(T) ------+
       |                        |
       |                thenAccept(T -> action)
       |                    returns
       |                CompletableFuture<Void>
       |                        |
       |                thenRun(() -> signal)
       |                    returns
       |                CompletableFuture<Void>
       |
       +------ exceptional completion
                                |
                        callback normal-only bị bỏ qua
                        dependent stage kết thúc bất thường
```

Trong Java, `void` là từ khóa cho method không có giá trị trả về. `java.lang.Void` là một kiểu tham chiếu có thể dùng làm generic type argument. Với `CompletableFuture<Void>`, kết quả khi hoàn tất **bình thường** là `null`. Nó không có nghĩa rằng future bị bỏ qua hoặc không thể thất bại.

| API | Tham số callback | Nhận giá trị của source? | Tạo giá trị mới? | Kiểu kết quả stage mới |
| --- | --- | --- | --- | --- |
| `thenApply(fn)` | `Function<T, U>` | Có | Có, `U` | `CompletableFuture<U>` |
| `thenAccept(action)` | `Consumer<T>` | Có | Không | `CompletableFuture<Void>` |
| `thenRun(action)` | `Runnable` | Không | Không | `CompletableFuture<Void>` |
| `thenCompose(fn)` | `Function<T, CompletionStage<U>>` | Có | Ghép với future khác | `CompletableFuture<U>` |
| `whenComplete(action)` | `BiConsumer<T, Throwable>` | Giá trị và lỗi | Không nhằm tạo giá trị mới | Stage có cùng kiểu `T` |
| `handle(fn)` | `BiFunction<T, Throwable, U>` | Giá trị và lỗi | Có, `U` | `CompletableFuture<U>` |

Đây là các kiểu khi method được gọi trên `CompletableFuture`; interface `CompletionStage` khai báo tương ứng với kiểu kết quả là `CompletionStage`.

**Cách nhớ:** *apply* tạo giá trị, *accept* tiêu thụ giá trị, *run* không cần giá trị. Khi một operation phụ phải trả một future khác, *compose* mới là cách nối future đó vào luồng kết quả.

## 3. thenAccept(): nhận kết quả và thực hiện hành động

Chữ ký:

```java
CompletableFuture<Void> thenAccept(Consumer<? super T> action)
```

Ví dụ một future truy xuất kết quả đơn hàng:

```java
CompletableFuture<OrderSummary> source = loadOrder(orderId);
CompletableFuture<Void> audited =
        source.thenAccept(order -> auditService.record(order.id()));
```

Đây là **fragment trong project**: `OrderSummary`, `loadOrder` và `auditService` phải có trong ứng dụng. Callback nhận `OrderSummary` nên có thể truy cập ID, giá trị, trạng thái... Khi `auditService.record` trả về bình thường, `audited` mới được đánh dấu hoàn thành. Nếu audit ném lỗi, `audited` hoàn thành bất thường nhưng source có thể vẫn thành công.

Không hiểu `thenAccept` như một toán tử biến đổi dữ liệu. Callback có hợp đồng `Consumer.accept(T)` trả `void`, nên không thể trả một giá trị kiểu `String`/`OrderId` để làm kết quả của giai đoạn tiếp theo.

**Ví dụ cố ý sai kiểu, không biên dịch:**

```java
source.thenAccept(order -> {
    return order.id();
});
```

Nếu cần ID để truyền tiếp, dùng `thenApply(order -> order.id())`. Nếu chỉ cần ghi log ID, dùng `thenAccept(order -> System.out.println(order.id()))`.

### 3.1. Ví dụ Java 17+ hoàn chỉnh

Tệp `ThenAcceptThenRunDemo.java`:

```java
import java.util.concurrent.CompletableFuture;

public class ThenAcceptThenRunDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> source =
                CompletableFuture.completedFuture(21);

        CompletableFuture<Void> accepted =
                source.thenAccept(value ->
                        System.out.println("received=" + value));

        CompletableFuture<Void> finished =
                accepted.thenRun(() ->
                        System.out.println("audit-done"));

        finished.join();

        System.out.println("source=" + source.join());
        System.out.println("terminal=" + finished.join());
    }
}
```

Chạy bằng Java 17+:

```bash
javac ThenAcceptThenRunDemo.java
java ThenAcceptThenRunDemo
```

Kết quả:

```text
received=21
audit-done
source=21
terminal=null
```

Diễn giải:

1. Source đã có giá trị 21.
2. `thenAccept` nhận giá trị này và in dòng đầu.
3. `thenRun` được nối trên **`accepted`**, không phải đăng ký như nhánh độc lập của source, nên chỉ chạy sau khi `thenAccept` hoàn tất bình thường.
4. `join()` chờ future cuối; kết quả `null` là bình thường đối với `Void`.
5. `source.join()` vẫn trả 21: callback không lấy đi hay xóa kết quả của source.

Ví dụ này không tạo executor; mục đích là chứng minh **luồng dữ liệu và dependency**, không phải đo tốc độ chạy đồng thời.

### 3.2. Cách viết method reference

```java
CompletableFuture<String> source =
        CompletableFuture.completedFuture("ORDER-7");

CompletableFuture<Void> printed =
        source.thenAccept(System.out::println);
printed.join();
```

Đây là fragment Java 17+ và in `ORDER-7`. Method reference `System.out::println` ở đây đóng vai trò một `Consumer<String>`; kết quả source được truyền tới `println`. Nếu dùng `thenRun(() -> System.out.println("done"))` thì chỉ in thông điệp cố định, không được truyền `ORDER-7`.

## 4. thenRun(): chỉ cần điều kiện hoàn thành, không nhận T

Chữ ký:

```java
CompletableFuture<Void> thenRun(Runnable action)
```

`thenRun` nhận `Runnable` không có tham số. Hành động chỉ chạy sau khi stage trước hoàn thành **bình thường**. Dù source có kết quả `String`, `Integer` hay `OrderSummary`, `Runnable` không nhận giá trị đó qua API.

Tình huống đúng:

```java
CompletableFuture<Invoice> source = invoiceService.load(invoiceId);
CompletableFuture<Void> signaled =
        source.thenRun(() -> completionSignal.countDown());
```

Đây là fragment cần biến và service tương ứng. Nếu chỉ cần phát tín hiệu khi invoice được tải xong thành công, không phải đọc `Invoice`, `thenRun` phù hợp.

Nếu hành động **phải dùng invoice được tải từ source**, `thenAccept(invoice -> ...)` thường rõ ràng hơn. Không lưu invoice vào một field singleton chỉ để callback `thenRun` có dữ liệu, vì cách đó tạo shared mutable state dễ race.

### 4.1. thenRun vẫn có thể capture biến ngoài

```java
String requestId = "REQ-9";
CompletableFuture<Void> done =
        source.thenRun(() -> System.out.println(requestId));
```

Đây là **variable capture** của biến local effectively final, không phải source chuyển kết quả cho `thenRun`. Nếu biến capture trỏ tới object mutable, object đó vẫn có thể được chia sẻ giữa nhiều thread.

### 4.2. Ví dụ Java 17+: hành động không đọc giá trị

Tệp `ThenRunSignalDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicInteger;

public class ThenRunSignalDemo {
    public static void main(String[] args) {
        AtomicInteger signals = new AtomicInteger();

        CompletableFuture<String> source =
                CompletableFuture.completedFuture("READY");
        CompletableFuture<Void> signaled =
                source.thenRun(() -> signals.incrementAndGet());

        signaled.join();

        System.out.println("signals=" + signals.get());
        System.out.println("source=" + source.join());
        System.out.println("result=" + signaled.join());
    }
}
```

```bash
javac ThenRunSignalDemo.java
java ThenRunSignalDemo
```

Kết quả:

```text
signals=1
source=READY
result=null
```

`thenRun` chỉ quan tâm source thành công, không nhận chuỗi `READY`. Dùng `AtomicInteger` giúp biến đếm có thao tác cập nhật thread-safe khi ví dụ được chuyển sang callback Async. Trong ví dụ đơn giản không có cạnh tranh đồng thời.

## 5. Hai nhánh độc lập không đồng nghĩa với chuỗi tuần tự

Một nhầm lẫn quan trọng:

```java
source.thenAccept(order -> audit(order));
source.thenRun(() -> sendSignal());
```

Đây là hai **dependent stages riêng**, cùng gắn với `source`. Chúng chỉ phụ thuộc vào source, **không phụ thuộc lẫn nhau**. Vì thế không có bảo đảm `audit` chạy xong trước `sendSignal`. Nếu source đã complete sẵn, bạn có thể thấy hai callback chạy theo thứ tự đăng ký trong một lần test; đó không phải hợp đồng cho mọi tình huống.

Nếu cần `sendSignal` sau audit thành công, phải nối:

```java
CompletableFuture<Void> workflow =
        source.thenAccept(order -> audit(order))
              .thenRun(() -> sendSignal());

workflow.join();
```

Nếu audit lỗi, stage sau audit hoàn thành bất thường và `sendSignal` bị bỏ qua. Đó là hành vi mong muốn khi signal chỉ được phát sau audit thành công.

### 5.1. Khi hai nhánh thật sự độc lập

Tệp `TwoBranchesDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicInteger;

public class TwoBranchesDemo {
    public static void main(String[] args) {
        AtomicInteger actions = new AtomicInteger();
        CompletableFuture<String> source =
                CompletableFuture.completedFuture("INVOICE-1");

        CompletableFuture<Void> audit =
                source.thenAccept(value -> actions.incrementAndGet());
        CompletableFuture<Void> notify =
                source.thenRun(() -> actions.incrementAndGet());

        CompletableFuture.allOf(audit, notify).join();

        System.out.println("actions=" + actions.get());
        System.out.println("source=" + source.join());
    }
}
```

```bash
javac TwoBranchesDemo.java
java TwoBranchesDemo
```

Kết quả:

```text
actions=2
source=INVOICE-1
```

`CompletableFuture.allOf(...)` tạo một stage `Void` để chờ cả hai nhánh. Ví dụ **không** in thứ tự từng callback vì giữa hai nhánh không có thứ tự được bảo đảm. Khi các nhánh chạy đồng thời, dùng một counter thread-safe như `AtomicInteger` tốt hơn cập nhật `int` chung không có đồng bộ.

### 5.2. Vì sao không được bỏ tham chiếu đến future của callback?

**Phản mẫu:**

```java
source.thenAccept(this::sendEmail);
return source;
```

Nếu gửi email lỗi, lỗi nằm trên **dependent stage** do `thenAccept` tạo ra; caller chỉ giữ `source` có thể chỉ biết source thành công. Đối với side effect bắt buộc:

```java
return source.thenAccept(this::sendEmail);
```

Câu trên là fragment phù hợp với phương thức trả `CompletableFuture<Void>`. Quan trọng là caller/service phải thực sự quan sát future đó; nếu chỉ tạo rồi bỏ, bạn không có hợp đồng kết quả đáng tin cậy.

## 6. Non-Async và Async: callback chạy trên thread nào?

**Không có hậu tố Async không có nghĩa luôn chạy trong main/caller thread.** Với `CompletableFuture`, hành động `thenAccept`/`thenRun` có thể chạy bởi thread vừa hoàn thành stage trước hoặc bởi một thread tham gia quá trình completion. Nếu stage đã complete trước khi callback được đăng ký, action có thể chạy ngay trong lúc đăng ký. API không cung cấp một thread identity cố định.

Biến thể có hậu tố:

| API | Nhận T? | Cơ chế chạy |
| --- | --- | --- |
| `thenAccept(action)` | Có | Không chỉ rõ executor |
| `thenAcceptAsync(action)` | Có | Default asynchronous execution facility |
| `thenAcceptAsync(action, executor)` | Có | Executor được truyền |
| `thenRun(action)` | Không | Không chỉ rõ executor |
| `thenRunAsync(action)` | Không | Default asynchronous execution facility |
| `thenRunAsync(action, executor)` | Không | Executor được truyền |

Với `CompletableFuture` tiêu chuẩn Java, Async variants **không truyền executor** thường dựa trên `ForkJoinPool.commonPool()`; có điều kiện fallback nếu common pool không đủ mức parallelism. Chúng **không mặc nhiên sử dụng** pool của Spring `@Async`.

Đặc biệt trong Spring, nếu callback gửi HTTP blocking, truy vấn DB hoặc ghi log rất chậm, hãy dùng executor có giới hạn thích hợp thay vì mặc nhiên chiếm thread hoàn tất source hoặc common pool.

### 6.1. Ví dụ Java 17+: chỉ định executor

Tệp `NamedExecutorDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class NamedExecutorDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor =
                Executors.newSingleThreadExecutor(
                        task -> new Thread(task, "audit-worker"));

        try {
            CompletableFuture<String> source = new CompletableFuture<>();

            CompletableFuture<Void> done =
                    source.thenAcceptAsync(value -> {
                        System.out.println("value=" + value);
                        System.out.println("accept-thread="
                                + Thread.currentThread().getName());
                    }, executor).thenRunAsync(() ->
                        System.out.println("run-thread="
                                + Thread.currentThread().getName()),
                        executor);

            source.complete("A-17");
            done.get(5, TimeUnit.SECONDS);
        } finally {
            executor.shutdown();
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
value=A-17
accept-thread=audit-worker
run-thread=audit-worker
```

Giải thích: source hoàn thành bằng `complete("A-17")`, callback đầu được nộp vào executor có thread name xác định; callback sau chỉ được nộp khi dependent stage của callback đầu đã thành công. `get(5, TimeUnit.SECONDS)` đặt giới hạn chờ cho caller. `shutdown()` thuộc trách nhiệm của code tạo executor; trong Spring, executor nên là bean được container quản lý thay vì tạo một pool mới trong từng request.

**Không nên suy ra mọi overload `thenAcceptAsync` chắc chắn tạo một platform thread mới:** nếu cung cấp một `Executor` thực thi inline hoặc virtual-thread strategy, nơi chạy phụ thuộc vào executor đó. Điều API cung cấp là **cơ chế gửi tác vụ tới execution facility**.

### 6.2. Non-Async callback có thể làm worker nguồn chậm thêm

Nếu một worker hoàn thành `loadFromDb` rồi tự chạy `thenAccept` có blocking I/O vài giây, thread này có thể bị giữ lâu hơn dự tính. Tách `thenAcceptAsync(..., auditExecutor)` giúp quyết định tài nguyên cho callback nhưng không biến một dịch vụ chậm thành nhanh hơn năng lực thực. Vẫn phải có timeout, queue capacity, rate limit, backpressure và shutdown policy.

## 7. Exceptional completion: khi callback bị bỏ qua

Cả `thenAccept` lẫn `thenRun` chỉ chạy khi **tiền nhiệm hoàn thành bình thường**. Nếu stage trước thất bại/cancel, callback bị bỏ qua và dependent stage hoàn thành bất thường.

Nếu callback tự ném exception, dependent stage thất bại, trong khi original stage có thể vẫn thành công. Vì vậy một workflow có thể gồm **source success + audit failure**: đó không phải một mâu thuẫn, mà là hai stages khác nhau.

### 7.1. Ví dụ Java 17+: lỗi nguồn và phục hồi

Tệp `RecoveryDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.atomic.AtomicBoolean;

public class RecoveryDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> source = new CompletableFuture<>();
        AtomicBoolean invoked = new AtomicBoolean(false);

        CompletableFuture<Void> skipped =
                source.thenAccept(value -> invoked.set(true))
                      .thenRun(() -> System.out.println("unexpected"));

        source.completeExceptionally(
                new IllegalStateException("service unavailable"));

        try {
            skipped.join();
        } catch (CompletionException ex) {
            System.out.println("cause="
                    + ex.getCause().getClass().getSimpleName());
        }

        System.out.println("accept-called=" + invoked.get());

        CompletableFuture<Void> recovered =
                source.exceptionally(error -> 0)
                      .thenAccept(value ->
                              System.out.println("fallback=" + value));
        recovered.join();
    }
}
```

```bash
javac RecoveryDemo.java
java RecoveryDemo
```

Kết quả:

```text
cause=IllegalStateException
accept-called=false
fallback=0
```

Nhánh đầu bỏ qua cả hai callbacks do source lỗi. `exceptionally(error -> 0)` tạo stage mới thành công với fallback 0, nhờ đó `thenAccept` ở nhánh thứ hai được chạy. Giá trị fallback phải được chọn dựa trên nghiệp vụ; không nên thay lỗi thanh toán bằng 0 hoặc coi lỗi là thành công nếu hợp đồng không cho phép.

### 7.2. Ví dụ Java 17+: lỗi ở callback không thay đổi source

Tệp `CallbackFailureDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class CallbackFailureDemo {
    public static void main(String[] args) {
        CompletableFuture<String> source =
                CompletableFuture.completedFuture("ORDER-9");

        CompletableFuture<Void> audited =
                source.thenAccept(value -> {
                    throw new IllegalArgumentException("audit failed");
                });

        try {
            audited.join();
        } catch (CompletionException ex) {
            System.out.println("audit-error="
                    + ex.getCause().getClass().getSimpleName());
        }

        System.out.println("source=" + source.join());
    }
}
```

```bash
javac CallbackFailureDemo.java
java CallbackFailureDemo
```

Kết quả:

```text
audit-error=IllegalArgumentException
source=ORDER-9
```

`join()` thường ném `CompletionException` nếu stage hoàn thành bất thường; `get()` dùng checked exception `ExecutionException` để bọc lỗi. Không chỉ catch exception quanh **đoạn đăng ký callback**, vì với async continuation, lỗi có thể phát sinh về sau và nằm trong dependent future.

### 7.3. Phân biệt với whenComplete và handle

- `whenComplete((value, error) -> ...)` chạy khi stage trước **thành công hoặc lỗi**, thích hợp để ghi nhận cả hai đường; nó có quy tắc giữ outcome gốc và xử lý exception của chính callback.
- `handle((value, error) -> result)` cũng chạy khi có success/error, nhưng trả **một kết quả U mới** nên dùng được cho recovery/chuyển đổi.
- `exceptionally(error -> fallback)` phục hồi lỗi bằng fallback phù hợp.
- `thenAccept` và `thenRun` không chạy trên exceptional completion; **không dùng chúng như finally/cleanup cho mọi outcome**.

Ví dụ fragment:

```java
CompletableFuture<Void> done =
        source.whenComplete((value, error) -> {
            if (error != null) {
                reportFailure(error);
            }
        }).thenRun(() -> markSucceeded());
```

`markSucceeded` ở cuối vẫn chỉ chạy sau normal completion. `whenComplete` giúp quan sát lỗi, **không tự chữa** lỗi đó. Nếu bạn muốn cleanup luôn thực hiện, dùng một cleanup callback/primitive có semantics đúng và kiểm soát exception của cleanup.

## 8. Kết hợp với Spring @Async

Một method `@Async` của Spring có thể trả `CompletableFuture<T>` khi được gọi **qua Spring-managed proxy** và async processing đã bật (ví dụ `@EnableAsync`). Caller có thể gắn `thenAccept`/`thenRun` vào future nhận được.

**Snippet Spring tích hợp (không biên dịch đơn lẻ bằng javac):**

```java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

record InvoiceSummary(String invoiceId, int lineCount) {}

@Service
public class InvoiceQueryService {
    @Async("queryExecutor")
    public CompletableFuture<InvoiceSummary> load(String id) {
        return CompletableFuture.completedFuture(
                new InvoiceSummary(id, 3));
    }
}
```

Trong một bean khác, inject `InvoiceQueryService`, `AuditService` và executor:

```java
public CompletableFuture<Void> auditInvoice(String id) {
    return queryService.load(id)
            .thenAcceptAsync(summary ->
                    auditService.record(
                            summary.invoiceId(),
                            summary.lineCount()),
                    auditExecutor)
            .thenRun(() -> auditService.markCompleted(id));
}
```

Fragment trên giả định `queryService`, `auditService`, `auditExecutor` là dependency và đã được khai báo/inject. Stage cuối biểu diễn chuỗi: lấy summary thành công → audit thành công → đánh dấu hoàn tất.

**Chú ý:** `thenRun` ở cuối là non-Async, nên callback `markCompleted` có thể chạy trên thread hoàn thành audit. Nếu nó cũng là I/O blocking, nên cân nhắc `thenRunAsync(..., auditExecutor)` hoặc một executor khác thích hợp. `thenAcceptAsync` không truyền executor sẽ thường dùng default Java async facility, **không mặc nhiên là `queryExecutor` của Spring**.

### 8.1. Thread boundary và transaction

`@Async` có thể đã đổi thread, sau đó `thenAcceptAsync` có thể đổi sang executor khác. Spring transaction context, request-scoped object, MDC/trace context và security context gắn thread **không tự động đi theo** chuỗi future. Nếu audit cần transaction, mở/định nghĩa transaction tại boundary chạy audit thông qua cơ chế Spring phù hợp; ưu tiên truyền immutable ID/DTO thay vì managed JPA entity và `EntityManager` từ caller.

Nếu callback gọi API có side effect cần hoàn tất ngay trong transaction của request, phải xem lại thiết kế; đừng coi continuation bất đồng bộ là thành phần tự động của transaction ở caller.

### 8.2. Pool và quá tải

`thenAcceptAsync(action, executor)` có thể thất bại nếu executor đang shutdown hoặc từ chối task do quá tải. Khi side effect quan trọng, phải quan sát dependent stage, đặt admission control/queue hữu hạn và phản hồi lỗi theo SLA; không bỏ future rồi hy vọng callback chắc chắn chạy.

Spring `ThreadPoolTaskExecutor` cung cấp cách quản lý pool qua bean. Đừng tạo `Executors.newFixedThreadPool(...)` bên trong mỗi request để chạy callback; resource đó không tự do Spring đóng nếu chỉ là local object.

### 8.3. API trả kết quả và side effect có bắt buộc không?

Nếu caller cần phản hồi chỉ sau khi audit thành công, trả/await future **cuối** thay vì source. Nếu gửi email có thể hoàn tất sau HTTP response nhưng không được mất khi restart, lưu công việc bằng **durable queue/outbox/job store**, trả job ID/trạng thái theo hợp đồng; continuation trong RAM không thay thế durability.

## 9. Giữ giá trị nguồn nếu pipeline còn cần T

Sau `thenAccept`, stage mới là `Void`. Nếu cần tiếp tục xử lý `T`, đừng cố truyền giá trị từ `thenRun`:

### 9.1. Giữ T bằng thenApply

```java
CompletableFuture<Order> withAudit =
        source.thenApply(order -> {
            audit(order);
            return order;
        });
```

Fragment này giữ kiểu `Order` của stage mới và biến audit thành điều kiện thành công. Nếu audit lỗi, `withAudit` lỗi.

### 9.2. Quan sát outcome bằng whenComplete

```java
CompletableFuture<Order> observed =
        source.whenComplete((order, error) -> {
            if (error == null) {
                audit(order);
            } else {
                logFailure(error);
            }
        });
```

`whenComplete` giữ kiểu kết quả ban đầu. Tuy nhiên, callback này chạy **cả trên exceptional path**, nên cần ghi rõ điều kiện, tránh side effect không mong muốn; nếu callback ném lỗi, dependent stage có quy tắc exceptional completion riêng.

### 9.3. Nếu hành động phụ trả future: dùng thenCompose

**Dễ sai:**

```java
source.thenAccept(order -> auditAsync(order));
```

Nếu `auditAsync(order)` trả `CompletableFuture<Void>`, callback `thenAccept` chỉ gọi hàm và bỏ future con; stage `Void` do `thenAccept` trả về **không đợi** future đó hoàn tất.

**Đúng nếu cần đợi audit:**

```java
CompletableFuture<Void> done =
        source.thenCompose(order -> auditAsync(order));
```

`thenCompose` nối dependent stage vào future được trả về từ `auditAsync`, cho phép caller theo dõi lỗi và completion của nó. Quy tắc này đặc biệt quan trọng khi service Spring phụ trả `CompletableFuture`.

## 10. Kiểm thử thứ tự bằng CountDownLatch

Dùng `Thread.sleep(50)` để dự đoán thời điểm callback thực thi thường khiến test flaky. Thay vào đó, dùng latch giữ callback đầu và xác minh callback sau chưa thể hoàn tất.

Tệp `OrderedContinuationDemo.java` (Java 17+):

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class OrderedContinuationDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            CompletableFuture<String> source = new CompletableFuture<>();

            CompletableFuture<Void> done =
                    source.thenAcceptAsync(value -> {
                        entered.countDown();
                        try {
                            release.await();
                        } catch (InterruptedException ex) {
                            Thread.currentThread().interrupt();
                            throw new IllegalStateException(ex);
                        }
                    }, executor).thenRun(() ->
                            System.out.println("next-step-ran"));

            source.complete("ok");

            if (!entered.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("callback not started");
            }

            System.out.println("before-release=" + done.isDone());
            release.countDown();
            done.get(5, TimeUnit.SECONDS);
            System.out.println("after-release=" + done.isDone());
        } finally {
            release.countDown();
            executor.shutdown();
        }
    }
}
```

```bash
javac OrderedContinuationDemo.java
java OrderedContinuationDemo
```

Kết quả khi hoàn tất bình thường:

```text
before-release=false
next-step-ran
after-release=true
```

Đây là kiểm tra quan hệ phụ thuộc, **không phải** kiểm tra thread name. Source hoàn thành nhưng callback đầu đang đợi latch, nên `done` chưa thể hoàn thành. Khi release, callback đầu kết thúc, `thenRun` tiếp tục, future cuối mới hoàn tất. Chương trình đặt timeout để phát hiện lỗi thay vì treo vô hạn.

Trong JUnit, có thể kiểm tra `assertFalse(done.isDone())` trước khi release; `assertNull(done.get(timeout, unit))` sau khi release; và `assertThrows(CompletionException.class, failed::join)` ở test lỗi. Các assertion này là fragment cần JUnit/import phù hợp.

## 11. An toàn khi thao tác dữ liệu và side effect

### 11.1. Callback có thể chia sẻ object mutable

`thenAccept` nhận kết quả T từ source, **không tự clone** đối tượng đó. Nếu hai callback Async cùng sửa một `ArrayList` hoặc một field của singleton Spring bean, có thể xảy ra race condition.

**Phản mẫu:**

```java
List<String> shared = new ArrayList<>();
source.thenAcceptAsync(value -> shared.add("A"));
source.thenRunAsync(() -> shared.add("B"));
```

Đây là fragment. Hai task truy cập `ArrayList` mutable đồng thời không có đồng bộ. Hướng sửa là xác định ownership, tạo immutable snapshot, dùng cấu trúc đồng thời/lock phù hợp hoặc tuần tự hóa các thay đổi. Nối thứ tự chỉ điều phối những stage trong chuỗi đó; thread khác ngoài chuỗi vẫn có thể sửa cùng state.

### 11.2. Idempotency và retry

Một callback ghi DB/gửi email có thể được chạy lại nếu cả workflow bị retry. Nếu ghi dữ liệu thành công nhưng future bị đánh dấu lỗi trước khi caller nhận acknowledgment, retry có thể gây **tác động lặp**. `thenAccept` không bảo đảm exactly-once; cần idempotency key, unique constraint/deduplication hoặc transactional outbox tùy nghiệp vụ.

### 11.3. Timeout, cancel và backpressure

- `get(timeout, unit)` chỉ giới hạn thời gian **caller đợi**; không tự hủy I/O của callback.
- `orTimeout(...)` khiến stage hết hạn chuyển sang exceptional completion; normal-only callbacks sau đó bị bỏ qua nếu timeout thắng race hoàn tất.
- `completeOnTimeout(value, ...)` có thể tạo fallback normal completion, nên `thenAccept` sau đó có thể chạy với fallback.
- Hủy dependent future không có nghĩa mọi upstream work hay HTTP/DB client tự bị hủy.
- Với callback Async, đặt giới hạn queue, connection, deadline và rejection; không tạo nhiều stage rồi để RAM/worker tích tụ vô hạn.

### 11.4. Quan sát đúng stage

Theo dõi **source completion** và **terminal callback completion** riêng: một source trả kết quả đúng không chứng minh audit hay notification thành công. Các metric hữu ích: queue wait, task duration, completed/failed/rejected/cancelled, timeout, độ trễ p95/p99, kết nối downstream và số công việc pending.

## 12. Lỗi phổ biến và cách giải quyết

| Lỗi | Nguyên nhân | Cách giải quyết |
| --- | --- | --- |
| Dùng `thenRun` nhưng cần kết quả T | `Runnable` không được truyền T | Dùng `thenAccept` |
| Dùng `thenAccept` rồi muốn trả U | `Consumer` không trả giá trị | Dùng `thenApply` |
| Nghĩ `CompletableFuture<Void>` không cần chờ | Stage vẫn có completion và lỗi | Giữ/return terminal future |
| Đăng ký hai nhánh rồi nghĩ có thứ tự | Chỉ cùng phụ thuộc source | Nối `thenAccept(...).thenRun(...)` |
| Nghĩ non-Async luôn ở caller thread | Continuation có thể chạy trong thread completion | Không dựa vào identity; chỉ định executor khi cần |
| Nghĩ Async continuation dùng mặc định Spring pool | Không truyền executor thường dùng common pool | Truyền Spring-managed Executor |
| Source lỗi nhưng mong thenRun chạy cleanup | Normal-only callback bị bỏ qua | Dùng `whenComplete` hoặc cleanup phù hợp |
| Callback lỗi nhưng chỉ kiểm tra source | Lỗi nằm trên dependent stage | Quan sát terminal future |
| thenAccept gọi hàm trả future rồi bỏ đi | Không đợi tác vụ phụ | Dùng `thenCompose` |
| Dùng callback in-memory cho job không được mất | JVM restart làm mất stage đang chờ | Durable queue/outbox |
| Callback sửa shared mutable list/bean field | Data race và mất cập nhật | Immutable/ownership/đồng bộ |
| Đợi `join` ngay trong request rồi nghĩ không block | `join` vẫn chờ kết quả | Thiết kế async response/deadline phù hợp |

## 13. Bài tập thực hành và tiêu chí hoàn thành

**Bài 1 — Chọn method.** Cho `CompletableFuture<OrderSummary> future`: (a) in tổng tiền nhưng không trả kết quả mới; (b) phát tín hiệu sau khi hoàn thành mà không đọc summary; (c) lấy ID làm kết quả mới. Chọn lần lượt `thenAccept`, `thenRun`, `thenApply` và giải thích kiểu trả về.

**Bài 2 — Kiểm tra lỗi.** Tạo source thành công, `thenAccept` cố ý ném `IllegalStateException`, rồi nối `thenRun`. Chứng minh callback thứ hai bị bỏ qua, dependent future lỗi nhưng source gốc vẫn thành công.

**Bài 3 — Hai nhánh và chuỗi.** So sánh `source.thenAccept(audit)` và `source.thenRun(signal)` đăng ký độc lập với `source.thenAccept(audit).thenRun(signal)`. Dùng latch tạo thứ tự kiểm thử, không dùng `sleep`.

**Bài 4 — Executor trong Spring.** Đặt `@Async("queryExecutor")` trên service trả `CompletableFuture<Summary>`. Nối `thenAcceptAsync(..., auditExecutor)`. Xác minh `auditExecutor` là Spring-managed bean, log tên thread, đo queue/rejection và timeout.

**Bài 5 — Future con.** Viết `auditAsync` trả `CompletableFuture<Void>`. Quan sát khác biệt giữa `thenAccept(x -> auditAsync(x))` và `thenCompose(x -> auditAsync(x))` khi cần bảo đảm audit đã xong.

**Bài 6 — Độ tin cậy nghiệp vụ.** Thiết kế luồng gửi thông báo sau giao dịch. Phân biệt best-effort continuation với yêu cầu durable delivery; mô tả idempotency, outbox/job ID và cách trả trạng thái cho caller.

### Checklist

- [ ] Tôi nói đúng `thenAccept` nhận T, `thenRun` không nhận T.
- [ ] Tôi hiểu `CompletableFuture<Void>` vẫn có completion, lỗi và khả năng chờ.
- [ ] Tôi phân biệt `thenApply`, `thenCompose`, `whenComplete` và `exceptionally`.
- [ ] Tôi hiểu hai nhánh độc lập không có thứ tự mặc định.
- [ ] Tôi không nhầm non-Async với “luôn trên main thread”.
- [ ] Tôi biết chọn executor rõ cho `thenAcceptAsync`/`thenRunAsync`.
- [ ] Tôi biết các callback normal-only bị bỏ qua khi source lỗi/cancel.
- [ ] Tôi quan sát lỗi ở **dependent stage**, không chỉ ở source.
- [ ] Tôi có thể test ordering bằng latch và timeout.
- [ ] Tôi hiểu Spring `@Async` pool không tự áp dụng cho mọi Java continuation.
- [ ] Tôi biết khi nào side effect cần transaction, idempotency và lưu bền vững.

**Kết luận:** `thenAccept()` **tiêu thụ kết quả T nhưng không tạo giá trị mới**; `thenRun()` **không nhận T và chỉ đợi thành công để chạy hành động**. Cả hai đều tạo `CompletableFuture<Void>` có thể nối chuỗi và quan sát. Trong Spring, phải kiểm soát đúng dependent stage, executor và side effect để một bước “không trả kết quả” không biến thành một bước “không ai chịu trách nhiệm”.

## 14. Tài liệu chính thức

- Java SE 17 — [CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `thenAccept`/`thenRun` và các biến thể Async.
- Java SE 17 — [CompletionStage](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html): semantics của Function, Consumer, Runnable và exceptional completion.
- Java SE 17 — [Executor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html): hợp đồng gửi tác vụ và nơi thực thi.
- Spring Framework — [Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@Async`, `TaskExecutor` và cấu hình nguồn thực thi.

Khi chạy trong môi trường thật, đối chiếu phiên bản JDK/Spring của dự án và đo thread/queue/exception thực tế thay vì suy đoán từ tên phương thức.
