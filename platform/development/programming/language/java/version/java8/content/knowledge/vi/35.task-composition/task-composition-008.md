# `whenComplete` và quan sát không thay ý nghĩa kết quả trong `CompletableFuture` (Java 8+)

Một chuỗi xử lý bất đồng bộ thường có hai nhu cầu **khác nhau**: (1) *biến đổi kết quả hoặc xử lý lỗi* và (2) *quan sát kết quả hoặc lỗi để ghi log, đo metric, trace*. Java 8 cung cấp `CompletableFuture.whenComplete(BiConsumer<T, Throwable>)` cho mục tiêu thứ hai. Nó được gọi khi stage kết thúc **thành công hoặc thất bại**, thấy cả `result` và `Throwable`, nhưng **không có giá trị trả về để thay kết quả nghiệp vụ**.

Điều quan trọng hơn tên API: `whenComplete` **không phải một bảo đảm tuyệt đối rằng toàn bộ pipeline sẽ không đổi**. Nếu callback quan sát **trả về bình thường**, stage phụ thuộc nhận lại **cùng kết quả hoặc cùng trạng thái thất bại** của stage nguồn; nếu callback **ném ngoại lệ**, stage phụ thuộc có thể chuyển thành thất bại. Tác vụ logging chậm cũng làm chậm pipeline nếu các bước tiếp theo phụ thuộc vào stage `whenComplete` trả về. Vì thế muốn *quan sát không thay ý nghĩa kết quả*, ta cần chọn đúng vị trí trong pipeline và giữ callback quan sát **ngắn, an toàn, không ném lỗi**.

Bài này dùng `CompletableFuture`, `CompletionStage`, `BiConsumer`, `whenComplete`, `whenCompleteAsync`, `handle`, `exceptionally` và `Executor`. Các API cốt lõi ở đây có từ Java 8 và vẫn được hỗ trợ trong Java hiện đại. Ví dụ đầy đủ biên dịch bằng JDK 17 và sử dụng các hàm có từ Java 8.

## 1. Thế nào là một `CompletionStage` đã kết thúc?

Một `CompletionStage<T>` mô tả giai đoạn xử lý có thể kết thúc:

- **Bình thường:** có giá trị kiểu `T`. Giá trị này **có thể là `null`**; ví dụ `CompletableFuture.completedFuture(null)` vẫn là thành công.
- **Bất thường:** có ngoại lệ liên quan. Ngoại lệ có thể xuất phát từ phép xử lý trước, từ `completeExceptionally(...)` hoặc từ việc hủy `CompletableFuture`.
- **Chưa xong:** chưa có kết quả hoặc ngoại lệ cuối cùng; action phụ thuộc chưa được thực hiện cho đến khi stage hoàn tất.

Bất đồng bộ ở đây nói về **khả năng hoàn thành sau**, không hứa rằng mọi callback đều chạy trên thread khác. `whenComplete` là một action phụ thuộc có thể chạy theo chính sách non-async của `CompletableFuture`; `whenCompleteAsync` dùng cơ sở thực thi bất đồng bộ.

### 1.1. Hai tham số của callback

Chữ ký ý tưởng:

~~~java
CompletionStage<T> observed = stage.whenComplete(
    (value, error) -> {
        // Observe the completed stage.
    });
~~~

Đây là snippet minh họa với biến `stage` kiểu `CompletionStage<T>`. `whenComplete` nhận `BiConsumer<? super T, ? super Throwable>`, nên action **không trả lại giá trị T**. Khi chạy:

| Kết cục nguồn | `value` | `error` |
| --- | --- | --- |
| Thành công với chuỗi `"OK"` | `"OK"` | `null` |
| Thành công với giá trị `null` | `null` | `null` |
| Thất bại | `null` | `Throwable` khác `null` |
| Hủy `CompletableFuture` nguồn | Thường `null` | Ngoại lệ liên quan `CancellationException` |

**Phân biệt thất bại bằng `error != null`, không phải `value == null`.** Một stage `CompletableFuture<Void>` thành công thường có `value == null`; nếu coi giá trị null là lỗi thì metric sai.

### 1.2. Kết quả trả về là một **stage mới**

Với biến `CompletableFuture<T> source`, lời gọi:

~~~java
CompletableFuture<T> observed =
        source.whenComplete((value, error) -> record(value, error));
~~~

trả về một `CompletableFuture<T>` **phụ thuộc**. `observed` không phải `source`. Stage mới hoàn thành khi action `whenComplete` hoàn tất. Do đó mọi phép `thenApply`, `thenCompose`, `join` gắn **sau `observed`** có thể chờ cả action quan sát.

`record(value,error)` ở đây là hàm minh họa do ứng dụng cung cấp; hãy giữ nó không ném ngoại lệ nếu mục tiêu là bảo toàn kết cục nguồn.

## 2. Hợp đồng trung tâm của `whenComplete`

Giả sử:

~~~java
CompletableFuture<String> source =
        CompletableFuture.completedFuture("42");

CompletableFuture<String> observed =
        source.whenComplete((value, error) -> {
            System.out.println("saw: " + value);
        });

String result = observed.thenApply(x -> "id=" + x).join();
// id=42.
~~~

Khi action quan sát không ném lỗi, stage `observed` giữ cùng `"42"`. Với source thất bại, callback vẫn chạy để thấy ngoại lệ, rồi kết quả phụ thuộc vẫn thất bại; `whenComplete` **không tự phục hồi lỗi**.

Bảng quy tắc **đã được đặc tả**:

| Nguồn | Callback `whenComplete` | Stage trả về |
| --- | --- | --- |
| Thành công với `x` | Trả về bình thường | Thành công với **cùng `x`** |
| Thất bại với `e` | Trả về bình thường | Thất bại với **`e`** (theo quy tắc propagation) |
| Thành công với `x` | Ném `logError` | **Thất bại với `logError`** |
| Thất bại với `e` | Ném `logError` | **Ưu tiên thất bại nguồn `e`** |

Vì thế phát biểu **“`whenComplete` luôn giữ nguyên kết quả”** là không đủ chính xác. Cách phát biểu đúng:

> **`whenComplete` được thiết kế cho hành động quan sát; nó bảo toàn kết cục nguồn ở stage phụ thuộc khi callback hoàn tất bình thường.**

Ngoại lệ ban đầu được ưu tiên nếu *cả source lẫn callback* đều thất bại. Đây là hợp đồng hiện hành của `CompletionStage.whenComplete`, không phải hành vi ngẫu nhiên của một phiên bản JVM.

## 3. Ví dụ thành công: thêm log không biến đổi `T`

~~~java
CompletableFuture<String> lookup =
        CompletableFuture.completedFuture("order-42");

CompletableFuture<String> observed = lookup.whenComplete(
        (value, error) -> {
            if (error == null) {
                System.out.println("loaded " + value);
            } else {
                System.out.println("lookup failed: " + error);
            }
        });

String result = observed.thenApply(id -> "confirmed:" + id).join();
// confirmed:order-42.
~~~

**Luồng thực hiện theo dependency**:

~~~text
lookup: "order-42"
        |
        v
whenComplete: ghi nhận thành công, không đổi giá trị
        |
        v
thenApply: "confirmed:order-42"
~~~

Ở đây giá trị được biến đổi bởi **`thenApply`**, không phải `whenComplete`. Callback `whenComplete` có thể dùng để cập nhật metric thành công, tính thời gian xử lý từ dữ liệu đo sẵn hoặc ghi log với correlation ID. Nếu callback ném lỗi, bước `thenApply` sau nó sẽ không được gọi vì stage nhận đầu vào bị thất bại.

### Nếu kết quả thành công là null

~~~java
CompletableFuture<String> empty =
        CompletableFuture.completedFuture(null);

String state = empty.whenComplete((value, error) -> {
    if (error == null) {
        System.out.println("successful completion, value=" + value);
    }
}).handle((value, error) -> error == null ? "success" : "failure").join();
// success.
~~~

Đừng dùng `if (value != null)` làm điều kiện duy nhất của log thành công. Với `CompletableFuture<Void>`, null là kết quả bình thường.

## 4. Quan sát lỗi nhưng **không nuốt lỗi**

Một stage thất bại có thể được tạo bằng:

~~~java
CompletableFuture<String> failed = new CompletableFuture<>();
failed.completeExceptionally(
        new IllegalStateException("db unavailable"));
~~~

Gắn một callback quan sát:

~~~java
CompletableFuture<String> observed = failed.whenComplete(
    (value, error) -> {
        if (error != null) {
            System.out.println("operation failed: " + error.getMessage());
        }
    });
~~~

Nếu action không ném, `observed` vẫn **thất bại**. Cả `observed.join()` và các dependent stage yêu cầu thành công đều phản ánh thất bại đó. `whenComplete` không tự chuyển lỗi thành chuỗi dự phòng.

Để phục hồi thật sự:

~~~java
String result = failed
        .whenComplete((value, error) -> {
            if (error != null) System.out.println("recorded failure");
        })
        .exceptionally(error -> "fallback")
        .join();
// fallback.
~~~

**`exceptionally`** mới là stage chọn giá trị thay thế khi bị lỗi. Nếu muốn mapping trên **cả** nhánh thành công và lỗi, dùng `handle`; nếu cần chuyển sang một tác vụ bất đồng bộ mới theo điều kiện, chọn API composition thích hợp (`thenCompose` hoặc recovery API được hỗ trợ).

### Nguyên tắc nguồn lỗi

Đối số `Throwable error` có thể là lỗi gốc hoặc `CompletionException` bao lỗi tùy stage nguồn và cách lỗi được lan truyền. Đừng mã hóa điều kiện duy nhất kiểu `error instanceof IllegalStateException` cho mọi pipeline nếu ở tầng trên đã wrap thành `CompletionException`. Khi phân tích log, có thể kiểm tra `getCause()` có kiểm soát và lưu cả exception type, stack trace; **không tự suy rằng `error.getCause()` luôn tồn tại**.

`join()` thường ném `CompletionException` không checked cho exceptional completion; `get()` dùng `ExecutionException` (checked) và có thể ném `InterruptedException`. Với nguồn được hủy, `CancellationException` cũng cần được xét. Không gọi `join()` trên chính source **bên trong** callback để “tìm lỗi”; callback đã nhận cả hai tham số.

## 5. Trường hợp nguy hiểm: callback quan sát tự ném lỗi

Giả sử nghiệp vụ đã chạy thành công:

~~~java
CompletableFuture<String> source =
        CompletableFuture.completedFuture("42");

CompletableFuture<String> observed = source.whenComplete(
        (value, error) -> {
            throw new IllegalArgumentException("metrics down");
        });
~~~

`source` vẫn thành công với `"42"`, nhưng **`observed` thất bại** vì action quan sát ném lỗi. Nếu nối bước nghiệp vụ tiếp theo **sau `observed`**, pipeline có thể bị dừng chỉ vì metric/logging bị lỗi. Điều này trái với mục tiêu “quan sát không thay ý nghĩa kết quả”.

Ngược lại, nếu `source` đã thất bại với `IllegalStateException("db unavailable")` và callback lại ném `IllegalArgumentException("logger down")`, stage phụ thuộc theo đặc tả **ưu tiên lỗi nguồn `db unavailable`**. Không giả định lỗi logger luôn thay thế lỗi nguồn, và cũng không dựa vào việc lỗi logger nhất thiết được gắn `suppressed` vào Throwable gốc.

**Biện pháp:** xử lý lỗi ghi nhận ở ngay callback bằng chính sách rõ ràng, giữ action quan sát kết thúc bình thường nếu telemetry là **best-effort**. Đừng lạm dụng `catch(Throwable)` để che giấu các lỗi nghiêm trọng của JVM; cân nhắc bắt ngoại lệ runtime đã biết từ client logging/metrics.

~~~java
CompletableFuture<String> safe = source.whenComplete((value, error) -> {
    try {
        metricsClient.recordOutcome(error == null);
    } catch (RuntimeException telemetryError) {
        // Chính sách best-effort: báo qua kênh dự phòng an toàn;
        // không được để lỗi telemetry phủ lên kết cục nghiệp vụ.
    }
});
~~~

Đây là **snippet tích hợp**, giả định `metricsClient` là dependency đã được cung cấp và `source` là một `CompletableFuture<String>`. Phải quyết định trước liệu việc mất metric/log có được bỏ qua theo yêu cầu kiểm toán hay không; với audit bắt buộc, không nên giả vờ đó là quan sát best-effort.

**Không được suy ra “không ném lỗi” nghĩa là không tác động bên ngoài.** Callback vẫn thực hiện side effect; nếu nó chỉnh sửa object kết quả mutable, ghi vào database hoặc thay đổi shared state, ý nghĩa nghiệp vụ có thể thay đổi dù `CompletableFuture` trả cùng tham chiếu. Dùng DTO bất biến, dữ liệu snapshot hoặc chỉ đọc để giảm nguy cơ.

## 6. Phân biệt `whenComplete`, `handle`, `exceptionally` và `thenApply`

| API | Chạy khi thành công? | Chạy khi thất bại? | Giá trị trả về của callback | Vai trò chính |
| --- | --- | --- | --- | --- |
| `thenApply(Function<T,U>)` | Có | Không | `U` | Biến đổi giá trị thành công |
| `thenAccept(Consumer<T>)` | Có | Không | `void` | Dùng kết quả cho side effect trên nhánh thành công; stage phụ thuộc thường là `Void` |
| `thenRun(Runnable)` | Có | Không | `void` | Chạy action không nhận kết quả khi thành công |
| `whenComplete(BiConsumer<T,Throwable>)` | Có | Có | `void` | Quan sát cả kết quả và lỗi, giữ kết cục nguồn nếu action không ném |
| `handle(BiFunction<T,Throwable,U>)` | Có | Có | `U` | **Ánh xạ** cả thành công và lỗi thành kết cục mới |
| `exceptionally(Function<Throwable,T>)` | Không (trong nhánh thành công) | Có | `T` | Trả kết quả dự phòng khi lỗi |

Ví dụ thành công:

~~~java
CompletableFuture<Integer> source =
        CompletableFuture.completedFuture(5);

int transformed = source.thenApply(x -> x * 2).join();
// 10.

int observed = source.whenComplete((x, error) -> {
    if (error == null) System.out.println("received=" + x);
}).join();
// 5, không phải 10.

String handled = source.handle((x, error) ->
        error == null ? "value=" + x : "failed").join();
// value=5.
~~~

Ở nhánh thất bại, `thenApply` không chạy và stage phụ thuộc nhận lỗi, còn `whenComplete` vẫn chạy để ghi nhận lỗi. `handle` có thể trả về `"failed"` để **biến thất bại thành thành công**, còn `exceptionally` thường thích hợp cho fallback chỉ trên nhánh lỗi.

### 6.1. `whenComplete` không phải `finally` có thể tùy ý viết lại dữ liệu

Có thể ví von `whenComplete` với hành động cleanup hoặc `finally`: nó nhìn thấy cả hai kết cục. Nhưng khác một khối `finally` thông thường ở chỗ callback thuộc về **stage phụ thuộc**, lịch chạy của nó chịu completion model và executor. Nếu action ném lỗi, hậu quả tuân theo đặc tả `CompletionStage`.

Đừng coi `whenComplete` là transaction boundary. Nếu một bước thật sự cần commit log audit thành công trước khi trả kết quả cho khách, hãy mô hình hóa **một thao tác nghiệp vụ có xử lý thất bại**, có retry/idempotency/transaction phù hợp, không chèn một `whenComplete` best-effort rồi tuyên bố audit chắc chắn đã lưu.

### 6.2. Thứ tự trước và sau quan sát tạo khác biệt

~~~java
CompletableFuture<String> result = fetchAsync()
    .thenApply(this::validate)
    .whenComplete(this::recordOutcome)
    .thenApply(this::formatResult);
~~~

Đây là **minh họa trong một service** có các method `fetchAsync`, `validate`, `recordOutcome`, `formatResult` được định nghĩa bởi ứng dụng. Giả sử các bước đều hoạt động theo hợp đồng và `recordOutcome` không ném:

- `whenComplete` nhìn thấy kết quả **sau validate** và cả lỗi của các bước trước.
- Nếu `formatResult` tự thất bại, callback `recordOutcome` ở trên **không quan sát lỗi ấy**, vì nó nằm **trước** bước format.
- Nếu muốn quan sát toàn bộ phép tính, gắn `whenComplete` ở cuối chuỗi cần được theo dõi.
- Nếu callback ném, `formatResult` ở sau không chạy vì nhận một stage thất bại.

Vị trí của observer thể hiện **phạm vi kết quả** được quan sát; đừng đặt tên log "request finished successfully" ở một stage mà request vẫn còn các bước có thể thất bại.

## 7. `whenCompleteAsync`: nơi chạy callback không có nghĩa bảo toàn pipeline

`whenCompleteAsync` có hai overload:

~~~java
CompletableFuture<T> observed =
        source.whenCompleteAsync((value, error) -> audit(value, error));

CompletableFuture<T> observedOnPool =
        source.whenCompleteAsync((value, error) -> audit(value, error),
                                 observerExecutor);
~~~

Đây là snippet minh họa với biến nguồn, `audit` và `observerExecutor` do ứng dụng cung cấp.

- `whenComplete(...)` là **non-async**. Theo chính sách `CompletableFuture`, action có thể chạy trên thread hoàn thành nguồn hoặc thread khác tham gia completion; nếu stage đã xong trước khi đăng ký, thực tế có thể chạy ngay khi đăng ký. **Không dựa vào tên thread cụ thể**.
- `whenCompleteAsync(action)` dùng **default asynchronous execution facility** của stage. Với `CompletableFuture` thông thường, đây thường là `ForkJoinPool.commonPool()` theo quy tắc tài liệu; không được giả định mọi môi trường đều có common-pool đủ tài nguyên hoặc cùng tên worker.
- `whenCompleteAsync(action, executor)` dùng `Executor` được cung cấp. Bạn có thể dành một executor riêng cho telemetry có kiểm soát tài nguyên, hàng đợi và chính sách từ chối.

**Quan trọng:** `whenCompleteAsync` vẫn trả về stage **phụ thuộc vào việc callback xong**. Nếu bạn viết:

~~~java
CompletableFuture<String> result = source
        .whenCompleteAsync((value, error) -> audit(value, error), auditPool)
        .thenApply(this::nextBusinessStep);
~~~

thì `nextBusinessStep` **chờ callback audit hoàn thành**. Chữ `Async` chỉ nói cách action được lên lịch thực thi, **không bảo đảm** rằng callback chậm sẽ không làm chậm nhánh phụ thuộc.

Ngược lại, nếu chỉ muốn một observer tách nhánh:

~~~java
CompletableFuture<String> source = fetchAsync();

CompletableFuture<String> auditBranch = source.whenCompleteAsync(
        (value, error) -> audit(value, error), auditPool);

CompletableFuture<String> businessBranch =
        source.thenApply(this::nextBusinessStep);
~~~

`businessBranch` không phụ thuộc trực tiếp vào `auditBranch`, nên callback audit chậm **không phải điều kiện hoàn thành** của `businessBranch`. Tuy nhiên, hai nhánh vẫn có thể cạnh tranh tài nguyên chung và không có thứ tự thực thi được bảo đảm. Nếu người gọi bỏ qua `auditBranch`, lỗi callback có thể không được ai xử lý. Nếu công việc audit cần đảm bảo bền vững, **không** nên mô hình hóa nó như fire-and-forget branch không được quản lý.

### 7.1. Đừng chặn common pool bằng tác vụ logging nặng

Không đặt các thao tác block I/O lâu, chờ semaphore không giới hạn, hoặc gọi `join()` trên future có quan hệ phụ thuộc ngược trong một callback đang chạy trong pool hạn chế. Các hành động này có thể làm tăng độ trễ, bão hòa thread, thậm chí gây deadlock ở thiết kế không đúng.

Nếu ghi log cần I/O, cân nhắc logging async có backpressure/queue policy rõ ràng hoặc hệ telemetry chuyên trách. Việc tách executor **không thay thế** timeout, giới hạn hàng đợi hoặc cơ chế vận hành khi executor từ chối task.

### 7.2. Executor có thể từ chối

Nếu `executor.execute(...)` từ chối tác vụ, stage phụ thuộc có thể hoàn thành bất thường; callback không nhất thiết đã được chạy. Vì thế không thể hứa tuyệt đối "callback quan sát luôn thực hiện được" khi ứng dụng đóng, executor shutdown hoặc hệ thống quá tải. Với metric best-effort, lựa chọn chính sách mất dữ liệu có chủ đích; với audit bắt buộc, lưu thông điệp audit theo kiến trúc durable riêng.

## 8. Một ví dụ `whenCompleteAsync` với executor chủ động

~~~java
ExecutorService observerPool =
        Executors.newSingleThreadExecutor(
            task -> new Thread(task, "audit-executor"));

try {
    CompletableFuture<String> source =
            CompletableFuture.completedFuture("42");

    CompletableFuture<String> observed = source.whenCompleteAsync(
        (value, error) -> {
            System.out.println("callback thread=" +
                    Thread.currentThread().getName());
        },
        observerPool);

    String sameValue = observed.join();
    // Khi action không ném, sameValue = "42".
} finally {
    observerPool.shutdown();
}
~~~

Đây là ví dụ Java cần `import java.util.concurrent.*;`. Vì cung cấp `ThreadFactory` với tên `audit-executor` nên ví dụ có tên thread xác định; ứng dụng thực tế nên quản lý lifecycle của executor, giám sát queue, không tạo một pool mới cho từng request.

`observed.join()` đợi action `whenCompleteAsync` hoàn thành, cho thấy phần quan sát là một mắt xích phụ thuộc. Không dựa vào việc gọi `shutdown()` đồng nghĩa mọi task đã xong; trong ví dụ này `join()` đã xác nhận stage quan sát kết thúc trước khi đóng pool.

## 9. Quan sát cancellation đúng ý nghĩa

`CompletableFuture.cancel(...)` được mô hình hóa là **exceptional completion** với `CancellationException`. Callback `whenComplete` được gọi với `error != null` khi cancellation lan tới stage đang được theo dõi.

~~~java
CompletableFuture<String> source = new CompletableFuture<>();

CompletableFuture<String> observed = source.whenComplete(
        (value, error) -> {
            if (error instanceof CancellationException) {
                System.out.println("cancelled");
            }
        });

source.cancel(false);
~~~

Một số điều cần phân biệt:

- `source.isCancelled()` thể hiện trạng thái hủy của chính source.
- Stage phụ thuộc `observed` có thể hoàn thành bất thường với `CompletionException` bao `CancellationException`; không mặc định mọi dependent đều trả `isCancelled() == true`.
- `cancel(true)` trong `CompletableFuture` không bảo đảm ngắt thread đang chạy; tham số `mayInterruptIfRunning` không kiểm soát việc interrupt processing theo hợp đồng triển khai của lớp này.
- Hủy future **không** tự rollback side effect đã bắt đầu (ghi DB, gọi HTTP, log).
- Nếu task của bạn có cancellation token riêng, hãy mô hình hóa quy tắc hủy và cleanup rõ trong domain; không chỉ dựa vào log của `whenComplete`.

## 10. Nhánh thành công, lỗi và null trong điều kiện quan sát

Một callback có thể phân loại kết cục như sau:

~~~java
CompletableFuture<String> observed = source.whenComplete(
        (value, error) -> {
            if (error == null) {
                metrics.incrementSuccess();
            } else if (error instanceof CancellationException) {
                metrics.incrementCancelled();
            } else {
                metrics.incrementFailed();
            }
        });
~~~

Ở đây `metrics` là một dependency do ứng dụng cung cấp. Nếu `metrics.increment...()` có thể ném, chuỗi trên **chưa** thỏa mục tiêu bảo toàn kết cục; phải có chính sách best-effort hoặc xử lý telemetry với kênh tin cậy riêng.

Đừng kiểm tra `value == null` để quyết định failure, vì `CompletableFuture<Void>` và những stage thành công null vẫn hợp lệ. Đừng mặc định mọi `Throwable` trực tiếp là `CancellationException`: trong pipeline, có thể xuất hiện `CompletionException` bọc cause. Khi cần thống kê cancellation chính xác theo nguồn, phải xác định muốn đo "source bị cancel" hay "stage phụ thuộc thất bại vì cancellation".

### 10.1. Đối với thành công, log gì là đủ?

Tập thông tin quan sát thường gồm mã tác vụ, correlation/trace ID, thời lượng xử lý đo bằng nguồn clock phù hợp, loại kết cục và error type. Hạn chế ghi nguyên payload chứa thông tin nhạy cảm vào log. Không dựa vào `value.toString()` cho DTO lớn, có thể lỗi hoặc lộ dữ liệu.

Khi ghi exception, ưu tiên log stack trace/cause theo chính sách bảo mật và cấu trúc logging. Không đổ lặp cả stack trace ở mọi stage, vì một lỗi có thể đi qua nhiều `whenComplete` và gây log trùng.

## 11. Từ "quan sát" tới "không thay ý nghĩa": những bất biến cần giữ

Một thiết kế observer tốt cần kiểm tra:

1. **Bình thường:** `source.join()` và `observed.join()` trả cùng kết quả `T` nếu callback không ném.
2. **Bất thường:** lỗi nguồn vẫn đến nhánh phục hồi/caller, không bị observer tự đổi thành fallback.
3. **Thành công null:** observer báo success khi `error == null`.
4. **Callback lỗi:** biết rõ failure từ callback có thể làm stage phụ thuộc thất bại; không gọi nó là an toàn nếu chưa xử lý.
5. **Thời gian:** callback chậm có thể làm chậm các stage nối sau nó; nếu tách nhánh, không suy có thứ tự hoàn thành.
6. **Concurrency:** side effect thread-safe, không dùng shared `ArrayList` chưa đồng bộ từ nhiều callback chạy đồng thời.
7. **Tính bất biến của data:** observer không sửa DTO mutable hoặc nguồn dữ liệu mà business branch đang dùng.
8. **Vận hành:** executor có lifecycle/queue/circuit-breaker hoặc cơ chế telemetry phù hợp.
9. **Nhạy cảm dữ liệu:** log/metric không tiết lộ token, tài khoản, thông tin cá nhân ngoài phạm vi cho phép.
10. **Chính sách bắt buộc:** audit phải chắc chắn không nên phụ thuộc vào best-effort callback đơn lẻ.

## 12. Chương trình Java độc lập: kiểm chứng cả hai kết cục và lỗi observer

Tạo file **`WhenCompleteObservationDemo.java`**. Chương trình dùng các API `CompletableFuture` có từ Java 8, chạy được trên JDK 17+. Các future cho kết quả đã biết, log không phụ thuộc tên thread của common pool; phần `whenCompleteAsync` dùng một executor có tên `audit-executor`. Chương trình còn tự kiểm tra các bất biến bằng `check(...)`, và in `all checks passed` chỉ khi thành công.

~~~java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.*;

public class WhenCompleteObservationDemo {
    static CompletableFuture<String> fail(String message) {
        CompletableFuture<String> future = new CompletableFuture<>();
        future.completeExceptionally(new IllegalStateException(message));
        return future;
    }

    static String outcome(CompletableFuture<?> future) {
        try {
            return "ok: " + future.join();
        } catch (CompletionException ex) {
            Throwable cause = ex.getCause();
            return "error: " + cause.getClass().getSimpleName()
                    + ": " + cause.getMessage();
        } catch (CancellationException ex) {
            return "cancelled";
        }
    }

    static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        List<String> events = new ArrayList<>();
        CompletableFuture<String> source = CompletableFuture.completedFuture("42");
        CompletableFuture<String> observed = source.whenComplete((value, error) -> {
            events.add("observed: " + value + ", error=" + error);
        });
        String result = observed.thenApply(s -> "id=" + s).join();
        System.out.println(events.get(0));
        System.out.println("pipeline: " + result);
        System.out.println("source unchanged: " + source.join());

        CompletableFuture<String> failed = fail("db unavailable");
        AtomicReference<String> seenFailure = new AtomicReference<>();
        CompletableFuture<String> failedObserved = failed.whenComplete((value, error) -> {
            seenFailure.set(error.getClass().getSimpleName()
                    + ": " + error.getMessage());
        });
        String propagated = outcome(failedObserved);
        System.out.println("failure observed: " + seenFailure.get());
        System.out.println("failure propagates: " + propagated);

        CompletableFuture<String> successfulObserverCrash = source.whenComplete(
            (value, error) -> { throw new IllegalArgumentException("metrics down"); });
        System.out.println("observer throws on success: " +
                outcome(successfulObserverCrash));
        System.out.println("original still: " + outcome(source));

        CompletableFuture<String> failingObserverCrash = failed.whenComplete(
            (value, error) -> { throw new IllegalArgumentException("logger down"); });
        System.out.println("observer throws on failure: " +
                outcome(failingObserverCrash));

        AtomicInteger failureMetric = new AtomicInteger();
        String recovered = failed
                .whenComplete((value, error) -> { if (error != null) failureMetric.incrementAndGet(); })
                .exceptionally(ex -> "fallback").join();
        String handled = failed.handle((value, error) ->
                error == null ? value : "handled").join();
        System.out.println("exceptionally recovers: " + recovered);
        System.out.println("handle maps failure: " + handled);

        CompletableFuture<String> cancelled = new CompletableFuture<>();
        AtomicReference<String> cancelledSeen = new AtomicReference<>();
        CompletableFuture<String> afterCancel = cancelled.whenComplete(
                (value, error) -> cancelledSeen.set(
                        error.getClass().getSimpleName()));
        cancelled.cancel(false);
        String cancelledOutcome = outcome(afterCancel);
        System.out.println("cancel observed: " + cancelledSeen.get());
        System.out.println("dependent after cancel: " + cancelledOutcome);

        ExecutorService observerPool = Executors.newSingleThreadExecutor(
                task -> new Thread(task, "audit-executor"));
        try {
            CompletableFuture<String> asyncObserved =
                    source.whenCompleteAsync((value, error) -> {
                        System.out.println("async callback thread: " +
                                Thread.currentThread().getName());
                    }, observerPool);
            System.out.println("async result: " + asyncObserved.join());
            check(asyncObserved.join().equals(source.join()),
                    "async observation changed result");
        } finally {
            observerPool.shutdown();
        }

        check(failureMetric.get() == 1, "failure metric missing");
        check(failedObserved.isCompletedExceptionally(), "failure swallowed");
        check(seenFailure.get().startsWith("IllegalStateException"),
                "failure invisible");
        check(successfulObserverCrash.isCompletedExceptionally(),
                "observer failure invisible");
        check(outcome(failed).contains("db unavailable"),
                "original failure changed");
        check(cancelled.isCancelled(), "cancelled source was not cancelled");
        check(outcome(failingObserverCrash).contains("db unavailable"),
                "original failure lost");
        System.out.println("all checks passed");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 WhenCompleteObservationDemo.java
java WhenCompleteObservationDemo
~~~

**Stdout tham chiếu**, đã kiểm thử với JVM và đầu vào cố định:

~~~text
observed: 42, error=null
pipeline: id=42
source unchanged: 42
failure observed: IllegalStateException: db unavailable
failure propagates: error: IllegalStateException: db unavailable
observer throws on success: error: IllegalArgumentException: metrics down
original still: ok: 42
observer throws on failure: error: IllegalStateException: db unavailable
exceptionally recovers: fallback
handle maps failure: handled
cancel observed: CancellationException
dependent after cancel: error: CancellationException: null
async callback thread: audit-executor
async result: 42
all checks passed
~~~

### Giải thích những dòng quan trọng

1. `observed: 42, error=null`: callback thấy giá trị thành công và không có ngoại lệ. `pipeline: id=42` đến từ `thenApply` sau quan sát, không phải callback `whenComplete`.
2. `source unchanged: 42`: future nguồn vẫn hoàn thành thành công.
3. `failure observed: IllegalStateException: db unavailable`: lỗi nguồn được truyền vào đối số `Throwable`. `failure propagates` cho thấy stage do `whenComplete` trả về vẫn thất bại.
4. `observer throws on success`: observer ném `IllegalArgumentException`, làm **dependent stage** thất bại; `original still: ok: 42` chứng minh source vẫn thành công.
5. `observer throws on failure`: cả nguồn và observer đều lỗi; lỗi nguồn `db unavailable` có quyền ưu tiên trong stage phụ thuộc.
6. `exceptionally recovers: fallback` và `handle maps failure: handled`: hai API này **biến đổi kết cục**, trái với mục đích `whenComplete` quan sát.
7. `cancel observed` thấy `CancellationException`; `dependent after cancel` nhận exceptional completion, có thể biểu diễn dưới dạng `CompletionException` với cause hủy.
8. `async callback thread: audit-executor` chứng minh action thực thi qua executor cung cấp; `async result: 42` xác nhận giữ nguyên giá trị thành công.
9. Các phép `check(...)` bảo đảm kết quả observer, lỗi nguồn, ngoại lệ callback, cancellation và nhánh async không trái hợp đồng.

### Những điều demo cố tình không hứa

- Đây là ví dụ chạy với nguồn đã hoàn thành, **không** khẳng định các callback non-async luôn chạy tại thread gọi `whenComplete`.
- Đây không phải bảo đảm callback sẽ thực thi trong mọi tình huống executor từ chối task, máy bị tắt hoặc tiến trình dừng.
- Một exception có thể có wrapper `CompletionException` ở các pipeline khác; `getClass().getSimpleName()` trong ví dụ ổn định nhờ nguồn được tạo trực tiếp bằng `completeExceptionally`.
- Ví dụ dùng `ArrayList` cho action non-async gắn trên future đã hoàn thành, có đường đi đơn giản; khi nhiều callback chạy đồng thời trên thread khác, cần cấu trúc thread-safe hoặc context riêng.
- `whenComplete` không đưa ra giao dịch đảm bảo dữ liệu observability được ghi bền vững; chọn kiến trúc audit khác nếu yêu cầu đúng một lần/không mất bản ghi.

## 13. Thực hành: gắn quan sát đúng vị trí để không làm sai kết quả

### 13.1. Theo dõi kết cục cuối cùng của pipeline

Giả sử có ba bước bất đồng bộ: lấy hồ sơ, chuẩn hóa, tính tổng. Nếu muốn ghi một metric phản ánh **toàn bộ** nghiệp vụ, gắn callback ở sau bước cuối:

~~~java
CompletableFuture<Integer> pipeline =
    CompletableFuture.completedFuture("12")
        .thenApply(Integer::parseInt)
        .thenApply(x -> x * 2)
        .whenComplete((value, error) -> {
            if (error == null) {
                System.out.println("pipeline succeeded");
            } else {
                System.out.println("pipeline failed");
            }
        });

System.out.println(pipeline.join());
// pipeline succeeded
// 24
~~~

Ví dụ có source hoàn thành ngay và action không ném; stdout thể hiện quan sát kết cục cuối rồi lấy kết quả. Nếu muốn theo dõi từng bước cụ thể, có thể gắn các observer ở từng ranh giới, nhưng cần gắn nhãn `stepName` chính xác để không báo thành công toàn giao dịch quá sớm.

### 13.2. Gắn observer trước hay sau fallback?

~~~java
CompletableFuture<String> source = new CompletableFuture<>();
source.completeExceptionally(new IllegalStateException("service unavailable"));

// Theo dõi lỗi gốc trước khi recovery:
CompletableFuture<String> a = source
    .whenComplete((value, error) -> {
        if (error != null) System.out.println("original attempt failed");
    })
    .exceptionally(error -> "fallback");

// Theo dõi kết cục sau recovery:
CompletableFuture<String> b = source
    .exceptionally(error -> "fallback")
    .whenComplete((value, error) -> {
        if (error == null) System.out.println("final result is available");
    });
~~~

Cả `a.join()` và `b.join()` đều là `"fallback"` nếu callback không ném, **nhưng thông tin được quan sát khác nhau**. Với nhánh A, observer thấy lỗi nguồn. Với nhánh B, observer thấy kết quả đã được recovery thành công. Một hệ thống metric thường cần đo **số lần thử thất bại** và **số request cuối cùng thất bại** bằng hai metric riêng, chứ không gộp chúng vào một cờ.

### 13.3. Không làm mất trace context

Khi callback chạy qua `whenCompleteAsync(..., executor)`, các context gắn với thread như MDC/ThreadLocal **không mặc nhiên chuyển** sang thread mới. Nếu cần correlation ID, truyển ID tường minh bằng biến bất biến được capture, hoặc dùng cơ chế propagation chính thức của framework.

~~~java
String correlationId = "req-42";
CompletableFuture<String> source =
        CompletableFuture.completedFuture("ok");

CompletableFuture<String> observed = source.whenComplete(
    (value, error) -> {
        String outcome = error == null ? "success" : "failure";
        System.out.println(correlationId + ": " + outcome);
    });
~~~

Ví dụ này không tự phụ thuộc vào ThreadLocal hoặc thông tin nhạy cảm. Trong hệ thống thật, cần quản lý lifecycle và giới hạn kích thước log. Không nên ghi toàn bộ payload kết quả vào log chỉ vì callback nhận được nó.

## 14. Những lỗi thiết kế thường gặp

| Sai lầm | Hệ quả | Cách làm đúng |
| --- | --- | --- |
| Nghĩ `whenComplete` luôn là một observer hoàn toàn “vô hình” | Callback ném có thể làm stage phụ thuộc thất bại | Action quan sát nên hoàn thành bình thường; test lỗi observer |
| Dùng `whenComplete` để trả fallback | `BiConsumer` không trả `T` | `exceptionally` hoặc `handle` |
| Dùng `handle` chỉ để in log rồi trả đại một giá trị | Có thể vô tình đổi kết quả/lỗi | `whenComplete` nếu chỉ quan sát |
| Dùng `thenAccept` để quan sát cả thất bại | Chỉ chạy khi thành công | `whenComplete` cho cả hai |
| Phân loại `value == null` là lỗi | Thành công null/`Void` bị tính sai | Kiểm tra `error != null` |
| Gọi `whenComplete` rồi chỉ dùng `source` và nghĩ observer chắc chắn hoàn tất trước | Hai nhánh không có dependency chờ observer | Theo dõi `observed` hoặc thiết kế telemetry riêng |
| Dùng `whenCompleteAsync` rồi tưởng nhánh nối sau không chờ callback | Stage `whenCompleteAsync` hoàn thành sau callback | Tách nhánh nếu telemetry không phải điều kiện nghiệp vụ |
| Chạy log I/O nặng trên thread completion | Tắc thread đang hoàn tất tác vụ | Callback ngắn; executor/telemetry pipeline phù hợp |
| Dùng shared `ArrayList` không đồng bộ cho nhiều callback chạy song song | Race condition, sai metric | Dùng counter thread-safe/queue chuyên dụng |
| Callback ghi đè, sửa DTO kết quả mutable | Business branch thấy dữ liệu đã đổi | Quan sát bất biến hoặc snapshot |
| Giả định `whenComplete` luôn chạy trên thread gọi đăng ký | Chính sách non-async không hứa thread cố định | Không lệ thuộc tên thread, dùng executor khi cần |
| Giả định `whenCompleteAsync` luôn chạy trên commonPool giống nhau | Implementation/default facility có chính sách riêng | Cung cấp executor nếu cần kiểm soát |
| Không xử lý lỗi executor từ chối | Telemetry có thể không chạy và dependent fail | Quản lý queue, rejection và shutdown |
| Đặt `whenComplete` trước stage còn có thể lỗi nhưng log “request succeeded” | Metric thành công sai phạm vi | Đặt ở cuối phần nghiệp vụ cần đo |
| Gắn observer sau fallback và gọi đó là số lỗi nguồn | Lỗi đã được phục hồi | Quan sát trước fallback để đo attempt failure |
| Nuốt mọi `Throwable` từ observer, kể cả lỗi nghiêm trọng của VM | Che giấu sự cố quan trọng | Chính sách bắt lỗi cụ thể/giám sát an toàn |
| Coi `CancellationException` luôn là hủy trực tiếp của mọi dependent | Hủy có thể được wrap thành lỗi dependency | Theo dõi source, unwrap có kiểm soát |
| Gọi `join()` trên future đang đợi chính callback hiện tại | Có thể chặn hoặc deadlock | Dùng tham số `value`, `error` đã có |
| Coi fire-and-forget observer là audit không mất dữ liệu | Process crash/reject có thể bỏ qua log | Thiết kế durable audit/outbox nếu bắt buộc |
| Log token, mật khẩu, nguyên request hoặc payload nhạy cảm | Rò rỉ thông tin | Redaction và telemetry schema tối thiểu |
| Chỉ unit test trường hợp success | Bỏ qua lỗi nguồn, lỗi callback và cancellation | Ma trận test đầy đủ |

## 15. Bài tập tự luyện có lời giải

### Bài 1 — Thành công giữ nguyên

`CompletableFuture.completedFuture(10).whenComplete((v,e)-> System.out.println(v)).join()` trả về gì?

**Đáp án:** Số `10`. Action nhìn thấy giá trị 10 và trả về bình thường, nên dependent stage giữ cùng kết quả. Giá trị do `System.out.println` trả về (void) không biến đổi T.

### Bài 2 — Source đã thất bại

Một stage hoàn thành bất thường với `IllegalStateException("network")`. Callback `whenComplete` chỉ ghi log rồi kết thúc. `join()` trên stage phụ thuộc trả fallback hay ném?

**Đáp án:** Ném exceptional completion; `whenComplete` không phục hồi. Dùng `exceptionally(ex -> fallback)` nếu chủ đích là trả giá trị dự phòng.

### Bài 3 — Logger cũng ném lỗi

Source đã thành công `"OK"`, nhưng callback `whenComplete` ném `IllegalArgumentException("log failed")`. Stage nào bị lỗi?

**Đáp án:** Stage phụ thuộc trả về bởi `whenComplete` bị lỗi với ngoại lệ của callback; source `"OK"` vẫn thành công.

### Bài 4 — Hai lỗi cùng lúc

Source thất bại với `IllegalStateException("business")`, callback ném `IllegalArgumentException("log")`. Stage `whenComplete` trả về ưu tiên lỗi nào?

**Đáp án:** Theo hợp đồng của `CompletionStage`, **lỗi nguồn có quyền ưu tiên**. Không giả định lỗi callback được tự động bảo đảm xuất hiện trong `suppressed`.

### Bài 5 — Thành công với null

`CompletableFuture.completedFuture(null)` có phải là thất bại vì callback nhìn thấy `value == null`?

**Đáp án:** Không. `error == null` mới là dấu hiệu callback thấy thành công. Đây là trường hợp bình thường của nhiều `CompletableFuture<Void>`.

### Bài 6 — Chọn `handle` hay `whenComplete`

Bạn cần biến mọi lỗi thành chuỗi `"unavailable"` để UI hiển thị, và mọi thành công thành `"available: " + value`. API nào thích hợp?

**Đáp án:** `handle((v,e) -> e == null ? "available: " + v : "unavailable")` vì nó **trả một giá trị mới** cho cả hai trạng thái; `whenComplete` chỉ dùng để quan sát.

### Bài 7 — Callback chậm trên nhánh chính

Một request có pipeline `fetch().whenCompleteAsync(audit,pool).thenApply(render)`. Audit mất 4 giây, fetch trả ngay. Render có phải chờ audit không?

**Đáp án:** Có, vì `thenApply(render)` phụ thuộc vào stage trả về bởi `whenCompleteAsync`. Nếu muốn nhánh business không chờ audit, tách các dependent từ `fetch()`, đồng thời quản lý giám sát lỗi và độ bền của nhánh telemetry.

### Bài 8 — Quan sát lỗi trước/sau phục hồi

Tại sao `source.whenComplete(observe).exceptionally(recover)` cho metric khác `source.exceptionally(recover).whenComplete(observe)`?

**Đáp án:** Observer đầu nhìn thấy lỗi gốc, observer sau nhìn thấy kết quả đã phục hồi nếu recovery thành công. Cả hai cách có thể đúng nhưng đo những chỉ tiêu khác nhau.

### Bài 9 — Cancellation

Hủy một `CompletableFuture` có nghĩa callback `whenComplete` chắc chắn chạy với `error == null` và `value == null`?

**Đáp án:** Không. Cancellation là exceptional completion; callback nhận lỗi liên quan đến `CancellationException`. Dependent stage có thể bọc nó bằng `CompletionException`. Hủy không tự rollback side effect.

### Bài 10 — Quan sát không làm đổi dữ liệu mutable

Stage trả một `List<String>` có thể sửa. Callback `whenComplete` làm `list.clear()`, nhưng không ném. Stage có giữ nguyên kết quả theo hợp đồng không?

**Đáp án:** Về kết cục `CompletableFuture`, stage vẫn có cùng đối tượng tham chiếu; **nhưng nội dung list đã bị sửa**. Vì vậy “quan sát không thay ý nghĩa” đòi callback chỉ đọc hoặc sử dụng snapshot/kiểu bất biến.

## 16. Checklist code review

- [ ] `whenComplete` chỉ dùng để quan sát, không dùng để phục hồi hoặc biến đổi kết quả?
- [ ] Callback có thể ném không; nếu có, hậu quả với stage phụ thuộc đã được xử lý?
- [ ] Nguồn thất bại vẫn đi tới caller/recovery theo hợp đồng?
- [ ] Đã test source thành công, thất bại, thành công null và cancellation?
- [ ] Khi cả nguồn và callback đều lỗi, đã biết lỗi nguồn được ưu tiên?
- [ ] Đã phân biệt `handle`, `exceptionally`, `thenApply`, `thenAccept` và `whenComplete`?
- [ ] Observer đặt trước/sau fallback đúng phạm vi metric?
- [ ] Observer đặt sau mọi bước cần được đo như một operation?
- [ ] Nếu dùng `whenCompleteAsync`, executor có lifecycle, backpressure và policy rejection?
- [ ] Có tránh block I/O trong callback non-async/completion thread?
- [ ] Nhánh business có thật sự phải chờ action quan sát hay nên tách dependency?
- [ ] Khi tách nhánh, đã xác định cách theo dõi lỗi và độ tin cậy telemetry?
- [ ] Side effect observer có thread-safe, không đổi DTO/shared state?
- [ ] Không phụ thuộc vào thread name hoặc thứ tự hai nhánh không có ràng buộc?
- [ ] Error logging có xử lý `CompletionException` và cancellation theo nguồn cụ thể?
- [ ] Dữ liệu log đã được hạn chế/redact để tránh lộ thông tin nhạy cảm?
- [ ] Audit bắt buộc có kiến trúc lưu tin cậy thay vì chỉ một callback best-effort?
- [ ] Mã Java và kết quả stdout được biên dịch, chạy và đối chiếu thực tế?

**Kết luận:** `CompletableFuture.whenComplete` là công cụ **quan sát cả thành công và thất bại mà không chủ động ánh xạ kết quả**, không phải phương pháp xử lý lỗi. Nếu callback hoàn thành bình thường, stage trả về giữ cùng kết quả hoặc sự thất bại nguồn; nếu callback ném, stage phụ thuộc có thể thất bại khác với nguồn. `whenCompleteAsync` quyết định nơi chạy observer nhưng không tự loại bỏ dependency chờ. Muốn bảo toàn ngữ nghĩa nghiệp vụ, dùng callback ngắn, an toàn, không thay đổi kết quả mutable và đặt ở đúng ranh giới đo lường.

### Tài liệu chính thức còn được hỗ trợ

- [`CompletionStage` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletionStage.html): `whenComplete` và `whenCompleteAsync`; quy tắc ưu tiên lỗi nguồn, phân biệt `handle` và `exceptionally`.
- [`CompletableFuture` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletableFuture.html): triển khai các stage phụ thuộc, chính sách non-async/async, `join`/`get`, cancellation và executor.
- [`BiConsumer` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/function/BiConsumer.html): callback nhận hai tham số và không trả giá trị.
- [`CompletionException` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletionException.html): wrapper cho exceptional completion của các stage.
- [`Executor` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Executor.html): chạy tác vụ và chính sách chấp nhận.
- [`CancellationException` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CancellationException.html): biểu diễn hủy future.
