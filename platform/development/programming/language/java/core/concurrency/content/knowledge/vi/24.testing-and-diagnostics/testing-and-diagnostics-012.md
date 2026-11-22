# Đọc stack trace khi Future và async stage lỗi trong Java

Lỗi bất đồng bộ khó chẩn đoán vì **nơi phát sinh lỗi**, **nơi chuyển lỗi thành trạng thái của future** và **nơi người gọi nhìn thấy lỗi** có thể nằm trên những thread và thời điểm khác nhau. Với `CompletableFuture`, một exception ở `thenApply` có thể được lưu trong future; đến lúc gọi `join()` hoặc `get()` ở thread khác, người gọi mới nhận được exception bao ngoài. Nếu chỉ đọc vài dòng đầu của stack trace, rất dễ sửa nhầm vị trí.

Bài học này tập trung vào **Java concurrency nói chung**: cách đọc nguyên nhân gốc, hiểu ranh giới từng asynchronous stage, phân biệt wrapper do Java tạo với lỗi ứng dụng, bổ sung ngữ cảnh chẩn đoán, và xử lý cancellation/timeout/multiple failures. Các ví dụ dùng API JDK 17+, không cần framework bên ngoài.

## 1. Ba vị trí cần phân biệt khi đọc lỗi

Xét chuỗi công việc:

```text
request thread                   worker thread / executor
      |                                   |
      | supplyAsync(fetch) --------------> fetch()
      |                                   |
      |                             thenApply(parse)
      |                                   | 
      |                                   X throws IllegalArgumentException
      |                                   |
      |                         stage hoàn tất exceptional
      |                                   |
      | join() / get() <------------------+
      |    |
      |    X throws wrapper to caller
```

Có ba nơi khác nhau:

1. **Throw site (nơi gây lỗi):** frame code nghiệp vụ đầu tiên ném `IllegalArgumentException`, `IOException` hoặc loại lỗi cụ thể. Đây thường là điểm sửa trực tiếp.
2. **Completion site (nơi future chuyển trạng thái):** mã JDK, executor hoặc callback ghi kết quả thất bại vào stage. Stack có thể chứa `CompletableFuture$UniApply.tryFire`, `AsyncSupply.run`, `ForkJoinTask.doExec`, `ThreadPoolExecutor.runWorker`. Các frame này cho thấy cách tác vụ được chạy và chuyển trạng thái, nhưng không tự nói lỗi nghiệp vụ nằm ở đó.
3. **Observation site (nơi nhận lỗi):** thread gọi `join()`/`get()`, hoặc callback downstream nhận `Throwable`. Nó có thể tạo/thấy wrapper `CompletionException` hoặc `ExecutionException` sau khi thao tác gốc đã hoàn tất từ lâu.

**Một exception có thể chứa nhiều stack:** wrapper được tạo ở một điểm; cause bên trong được tạo ở điểm khác. Trace của wrapper vì vậy có thể bắt đầu tại `CompletableFuture.reportJoin` hoặc frame JDK tương tự, còn trace của **cause** bắt đầu từ phương thức ứng dụng làm hỏng tác vụ. Tùy đường đi và phiên bản JDK, line number/frame nội bộ thay đổi; hãy đọc **loại exception, chuỗi cause và tên phương thức ứng dụng**, không dựa cứng vào số dòng JDK.

## 2. Các API Future bộc lộ lỗi khác nhau như thế nào?

| Thao tác | Khi thành công | Khi future thất bại | Khi bị hủy | Khi chờ |
| --- | --- | --- | --- | --- |
| `Future.get()` | Trả kết quả | Ném checked `ExecutionException`, nguyên nhân ở `getCause()` | Ném `CancellationException` | Chờ đến khi xong; có thể ném `InterruptedException` |
| `Future.get(timeout, unit)` | Trả kết quả | Ném `ExecutionException` | Ném `CancellationException` | Có thể ném `TimeoutException` nếu chưa xong đúng hạn |
| `CompletableFuture.join()` | Trả kết quả | Thường ném unchecked `CompletionException`, nguyên nhân ở `getCause()` | Có thể ném trực tiếp `CancellationException` khi future bị cancel | Chờ không có tham số timeout |
| `CompletableFuture.getNow(default)` | Trả kết quả đã có, hoặc giá trị default nếu chưa xong | Khi đã thất bại, có thể ném `CompletionException` | Ném `CancellationException` nếu đã hủy | Không chờ |
| `CompletableFuture.whenComplete(...)` | Chuyển tiếp kết quả gốc khi observer thành công | Observer nhận `Throwable`; stage trả về vẫn exceptional nếu nguồn exceptional | Observer nhận trạng thái thất bại/hủy tùy nguồn | Không tự chặn chờ |
| `CompletableFuture.handle(...)` | Callback nhận `(value, null)` | Callback nhận `(null, throwable)` và có thể tạo kết quả thay thế | Callback cũng có thể nhìn thấy cancellation | Không tự chặn chờ |
| `CompletableFuture.exceptionally(...)` | Bỏ qua callback nếu thành công | Callback nhận lỗi, có thể phục hồi hoặc ném lỗi khác | Có thể được gọi với cancellation như một completion exceptional | Không tự chặn chờ |

**`get()` và `join()` không trả về exception như giá trị:** chúng ném lỗi khi future exceptional. `get()` dùng checked exception và hỗ trợ interruptible waiting; `join()` thuận tiện hơn khi compose code không muốn khai báo checked exception. Tất cả callback `handle`/`whenComplete`/`exceptionally` có thể chạy đồng bộ trên thread hoàn thành stage hoặc thread đăng ký callback nếu stage đã xong; thêm hậu tố `Async` để yêu cầu asynchronous execution.

`CompletionException` và `ExecutionException` là **vỏ mang nguyên nhân thất bại**, không nhất thiết là bug ở JDK. `CancellationException` chỉ ra future đã bị cancel; `TimeoutException` của `get(timeout, ...)` thường cho biết thread gọi **hết thời gian chờ**, không khẳng định công việc nền dừng hay future thất bại.

Các lỗi khác cần nhận diện: `RejectedExecutionException` có thể đến từ executor không nhận nhiệm vụ; `InterruptedException` báo thread chờ bị interrupt; lỗi do task ném (`IllegalStateException`, `NullPointerException`, `IOException` được bọc vào exception phù hợp) giữ ngữ nghĩa riêng trong cause chain.

## 3. Cách đọc một stack trace có nhiều "Caused by"

Ví dụ **minh họa**, đã lược bỏ frame và số dòng tùy JVM:

```text
java.util.concurrent.CompletionException: java.lang.IllegalArgumentException: invalid payload
    at java.base/java.util.concurrent.CompletableFuture.encodeThrowable(...)
    at java.base/java.util.concurrent.CompletableFuture$UniApply.tryFire(...)
    ...
Caused by: java.lang.IllegalArgumentException: invalid payload
    at example.Parser.decode(...)
    at example.Pipeline.lambda$parse$0(...)
    at java.base/java.util.concurrent.CompletableFuture$UniApply.tryFire(...)
    ...
```

Đọc từ **loại lỗi ngoài cùng**, đi xuống từng `Caused by:`, rồi tìm **frame ứng dụng đầu tiên** trong phần cause thích hợp:

- `CompletionException`: signal cho người gọi rằng stage hoàn tất exceptional.
- `IllegalArgumentException: invalid payload`: lỗi cụ thể, chứa message có ích.
- `example.Parser.decode`: vị trí nghiệp vụ xảy ra lỗi.
- `UniApply.tryFire`: JDK thực thi một dependent stage dạng apply. Frame này giúp biết đường thực thi, nhưng không phải nơi tạo dữ liệu sai.

**Không mặc định "cause cuối cùng" luôn đủ để hiểu lỗi.** Nếu ứng dụng bọc `InvalidOrderException("orderId=...")` quanh `SQLException`, wrapper nghiệp vụ chứa context quan trọng. Cần đọc **toàn bộ causal chain** và thông điệp của từng tầng; chỉ tìm root cause để xác định nguồn hỏng, rồi trở lại các tầng bên ngoài để hiểu request, stage, retry và tài nguyên.

Ngoài `Caused by`, Java có **suppressed exceptions** (hiển thị bằng `Suppressed:`), thường đến từ xử lý đóng tài nguyên trong `try-with-resources` hoặc khi code gọi `addSuppressed`. Chúng khác cause: lỗi đóng tài nguyên được giữ kèm lỗi chính, không thay thế lỗi chính. Khi trace rút gọn, nhiều công cụ logging loại bớt frame trùng bằng dấu `... N more`; đây là cách hiển thị, không có nghĩa mọi frame đã biến mất.

Một stack trace của một thread **không tự tái tạo toàn bộ lịch sử async** qua các thread khác. Khi callback được chạy trong executor mới, các frame gọi ban đầu có thể không xuất hiện trong exception được ném ở worker. Cần kết hợp stage name, request ID, dữ liệu đầu vào đã an toàn, và các sự kiện hoàn thành để dựng lại đường đi.

## 4. Ví dụ Java 17 chạy độc lập: nhìn rõ join(), get() và origin

Ví dụ bên dưới dùng executor một worker, cố ý ném exception trong stage parse. Code **không in toàn bộ stack trace** để stdout vẫn xác định được giữa các máy; thay vào đó in loại wrapper, cause, message và frame ứng dụng đầu tiên. Có thể bật `printStackTrace` khi cần xem trace đầy đủ.

Lưu thành `FutureFailureDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class FutureFailureDemo {
    static Integer parse(String payload) {
        throw new IllegalArgumentException("invalid payload");
    }

    static Throwable unwrapAsyncWrapper(Throwable failure) {
        Throwable current = failure;
        while ((current instanceof CompletionException
                || current instanceof ExecutionException)
                && current.getCause() != null) {
            current = current.getCause();
        }
        return current;
    }

    public static void main(String[] args) {
        ExecutorService executor = Executors.newSingleThreadExecutor(
                task -> new Thread(task, "parse-worker"));
        try {
            CompletableFuture<Integer> stage =
                    CompletableFuture.supplyAsync(() -> "bad", executor)
                            .thenApplyAsync(FutureFailureDemo::parse, executor);

            try {
                stage.join();
            } catch (CompletionException failure) {
                Throwable cause = unwrapAsyncWrapper(failure);
                StackTraceElement origin = cause.getStackTrace()[0];
                System.out.println("join=" + failure.getClass().getSimpleName());
                System.out.println("cause=" + cause.getClass().getSimpleName());
                System.out.println("message=" + cause.getMessage());
                System.out.println("origin=" + origin.getClassName()
                        + "." + origin.getMethodName());
            }

            try {
                stage.get();
            } catch (ExecutionException failure) {
                Throwable cause = unwrapAsyncWrapper(failure);
                System.out.println("get=" + failure.getClass().getSimpleName());
                System.out.println("getCause=" + cause.getClass().getSimpleName());
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("interrupted while waiting", interrupted);
            }
        } finally {
            executor.shutdown();
        }
    }
}
```

Biên dịch/chạy với JDK 17 trở lên:

```bash
javac FutureFailureDemo.java
java FutureFailureDemo
```

Stdout xác định:

```text
join=CompletionException
cause=IllegalArgumentException
message=invalid payload
origin=FutureFailureDemo.parse
get=ExecutionException
getCause=IllegalArgumentException
```

Dòng `origin` chỉ tới phương thức **ném lỗi thật**, khác với nơi gọi `join()`. Trong thực tế để xem tất cả frame, thay dòng in ngắn bằng:

```java
failure.printStackTrace(System.err);
```

Đoạn trên **chỉ là dòng chèn vào block catch**, không phải chương trình Java độc lập. Stack đầy đủ sẽ hiển thị cả wrapper, `Caused by`, worker/executor frames và line numbers phụ thuộc nguồn/JDK. Không nên viết test so sánh nguyên văn toàn bộ stack trace; hãy assert loại, cause chain, message và stage context quan trọng.

**Tại sao dùng `thenApplyAsync(..., executor)`?** Lời gọi này yêu cầu parse diễn ra qua executor đã chọn, nhờ vậy mô phỏng ranh giới bất đồng bộ rõ ràng. Nếu dùng `thenApply`, dependent action có thể được thực thi bởi thread hoàn thành parent stage hoặc bởi thread đang đăng ký action khi parent đã hoàn tất. Không thể suy ra từ tên `thenApply` rằng callback luôn được chạy trên thread tạo pipeline.

## 5. Vị trí lỗi trong một chuỗi stage

`CompletableFuture` biểu diễn một **đồ thị phụ thuộc**. Mỗi stage có thể thành công hoặc hoàn tất exceptional. Một stage thất bại thường làm các dependent stage bình thường không chạy body:

```java
CompletableFuture<String> result =
        CompletableFuture.supplyAsync(() -> readPayload(), executor)
                .thenApply(payload -> decode(payload))
                .thenApply(value -> enrich(value))
                .thenApply(value -> render(value));
```

Đây là **mẫu minh họa**, cần có `executor` và các hàm tương ứng. Nếu `decode` ném lỗi, các action `enrich` và `render` của đường thành công không chạy; future cuối hoàn tất exceptional. Khi chỉ có stack trace ở cuối, không nên kết luận `render` lỗi: phải dò cause và biết stage nào thực sự đã chạy.

Phân biệt một số operator:

| Operator | Khi upstream thành công | Khi upstream exceptional |
| --- | --- | --- |
| `thenApply(fn)` | Chạy `fn` và chuyển kết quả | `fn` không được chạy; lỗi chuyển xuống dependent stage |
| `thenCompose(fn)` | Chạy `fn` trả future rồi “flatten” future đó | `fn` không được chạy; lỗi chuyển tiếp; nếu inner future lỗi, stage mới cũng lỗi |
| `thenAccept(action)` | Chạy action với kết quả | Bỏ qua action, lỗi chuyển tiếp |
| `thenRun(action)` | Chạy action không nhận kết quả | Bỏ qua action, lỗi chuyển tiếp |
| `whenComplete(observer)` | Quan sát kết quả, thường giữ nguyên outcome | Quan sát lỗi, thường giữ nguyên outcome; observer ném lỗi có ngữ nghĩa riêng |
| `handle(handler)` | Cho phép map giá trị sang kết quả mới | Cho phép recovery/transform; nếu handler trả fallback, downstream không còn thấy lỗi cũ |
| `exceptionally(handler)` | Không chạy handler | Chạy trên completion exceptional, có thể fallback hoặc ném lỗi tiếp |

**`thenCompose` khác `thenApply` với hàm trả future:** `thenApply` có thể tạo `CompletableFuture<CompletableFuture<T>>`, làm dễ quên quan sát inner future; `thenCompose` giúp flatten, làm exception của inner future hiển thị trên stage cuối. Khi callback trả future nhưng pipeline chỉ đợi outer future, có thể bỏ sót lỗi inner.

Lỗi phát sinh ở `whenComplete` cũng cần đọc cẩn thận. Nếu upstream thành công mà observer ném exception, stage do `whenComplete` trả về sẽ thất bại với exception của observer. Nếu upstream đã thất bại và observer lại ném exception, stage mới thường giữ nguyên lỗi upstream theo hợp đồng API; không thể dùng `whenComplete` để khôi phục một kết quả thay thế. Dùng `handle` hoặc `exceptionally` khi muốn **chủ động thay outcome**.

## 6. Bổ sung breadcrumbs để biết stage và request nào lỗi

Vì call stack của worker không chứa đầy đủ đường gọi ở request thread, log nên có:

- **Correlation/request ID** để nối sự kiện trước và sau asynchronous boundary.
- **Stage name** rõ nghĩa: `fetch`, `decode`, `validate`, `persist`...
- **Operation context** không nhạy cảm: loại tác vụ, key nghiệp vụ đã giảm độ chi tiết, attempt number, deadline, executor hoặc pool name.
- **Thread name** như thông tin phụ; thread có thể được tái sử dụng cho nhiều request.
- **Throwable object thật** để logger in causal chain, thay vì chỉ `failure.getMessage()`.

Ví dụ **mẫu minh họa**, đặt trong lớp có biến `logger` và `requestId`, không phải tệp chạy độc lập:

```java
CompletableFuture<Result> observed = source.whenComplete((value, failure) -> {
    if (failure != null) {
        logger.log(
                java.util.logging.Level.SEVERE,
                "requestId=" + requestId + ", stage=decode",
                failure);
    }
});
```

`source` phải là `CompletableFuture<Result>`. Dùng callback observer ngắn, không block và không ném exception khi logging. Nếu callback ném lỗi, pipeline do `whenComplete` trả về có thể đổi trạng thái và làm khó chẩn đoán hơn. Đặt logging **ở ranh giới thích hợp**, tránh log cùng một exception tại mọi stage rồi tạo hàng chục bản lặp.

Nếu cần bọc lỗi với ngữ cảnh nghiệp vụ, **giữ cause**:

```java
static Item decodePayload(String payload, String requestId) {
    try {
        return decode(payload);
    } catch (IllegalArgumentException failure) {
        throw new DecodeStageException(
                "stage=decode, requestId=" + requestId,
                failure);
    }
}
```

Đây là đoạn minh họa; `Item`, `decode` và `DecodeStageException` là kiểu/hàm ứng dụng. `DecodeStageException` phải có constructor nhận `String` và `Throwable` và chuyển cause tới `super(message, cause)`. Nhờ vậy trace sẽ có cả ngữ cảnh stage lẫn nguyên nhân kỹ thuật. Nếu thay bằng `throw new RuntimeException(failure.getMessage());`, trace và exception type/cause gốc bị mất.

Không biến mọi lỗi thành `"unknown error"` hoặc bắt `Throwable` rồi trả fallback khi chưa có chính sách recovery. Đặc biệt `Error` như `OutOfMemoryError` thường cần được phép lan truyền qua cơ chế xử lý lỗi nghiêm trọng thích hợp; không coi nó như lỗi dữ liệu bình thường.

## 7. Unwrap exception: làm đúng và không xóa mất ngữ cảnh

Một tiện ích diagnostic có thể bỏ lớp wrapper chuẩn của async:

```java
static Throwable unwrapCompletion(Throwable failure) {
    Throwable current = failure;
    while ((current instanceof java.util.concurrent.CompletionException
            || current instanceof java.util.concurrent.ExecutionException)
            && current.getCause() != null) {
        current = current.getCause();
    }
    return current;
}
```

Đây là **mẫu có thể đặt vào một class Java**, không phải tệp runnable độc lập. Chỉ unwrap **wrapper đã biết**, không tự động đi tới cause sâu nhất của mọi exception nghiệp vụ; nếu không sẽ mất thông tin `DecodeStageException`, `RetryExhaustedException` hay `RequestContextException` nằm trên đường đi.

Lưu ý `CompletionException` có thể do code ứng dụng cố ý ném để thể hiện lỗi bất đồng bộ. Nó không phải lúc nào cũng được JDK tạo ở cùng một vị trí. Một `ExecutionException` có thể bao bọc `CompletionException` hoặc ngoại lệ gốc tùy đường chuyển tiếp; vì vậy vòng lặp unwrap hai loại có ích cho báo cáo nguyên nhân. **Sau khi unwrap để phân loại**, vẫn nên log exception gốc nhận được nếu cần giữ đầy đủ chuỗi causal chain.

**Không biến phân loại lỗi thành logic nghiệp vụ chỉ dựa vào message:** text của exception có thể đổi theo JDK, thư viện hoặc localization. Dùng type, error code/application contract và metadata riêng khi cần hành vi retry hay báo lỗi.

## 8. Nhiều Future thất bại: allOf không tự tạo danh sách đầy đủ

`CompletableFuture.allOf(a, b, ...)` tạo future hoàn tất khi mọi thành phần hoàn tất; nếu có ít nhất một thành phần exceptional, future tổng cũng exceptional. **Nó không cung cấp sẵn danh sách tất cả nguyên nhân lỗi**. Chỉ gọi `allOf(...).join()` và đọc một cause có thể bỏ sót lỗi của những tác vụ còn lại.

Ví dụ Java 17 chạy độc lập, lưu thành `FanInFailureDemo.java`:

```java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class FanInFailureDemo {
    public static void main(String[] args) {
        CompletableFuture<String> first =
                CompletableFuture.failedFuture(
                        new IllegalStateException("task A failed"));
        CompletableFuture<String> second =
                CompletableFuture.failedFuture(
                        new IllegalArgumentException("task B failed"));

        CompletableFuture<Void> all = CompletableFuture.allOf(first, second);
        System.out.println("allFailed=" + all.isCompletedExceptionally());

        List<CompletableFuture<String>> tasks = List.of(first, second);
        for (int index = 0; index < tasks.size(); index++) {
            try {
                tasks.get(index).join();
            } catch (CompletionException failure) {
                Throwable cause = failure.getCause();
                System.out.println("task" + (index + 1) + "=" + cause.getMessage());
            }
        }
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
allFailed=true
task1=task A failed
task2=task B failed
```

Ví dụ cố ý dùng hai failed futures đã hoàn tất để kết quả cố định. Trong hệ thống thật, mỗi task có thể bị lỗi, bị hủy, thành công hoặc còn pending; muốn thống kê từng task thì lưu reference đến từng future và quan sát chúng **sau khi trạng thái cần thiết đã sẵn sàng**. Đừng chọn cause của `allOf` làm “lỗi duy nhất” rồi bỏ qua các task còn lại. `anyOf` thì hoàn tất khi **một** future hoàn tất trước, nên lại càng không có nghĩa toàn bộ nhóm đã xong.

Với pipeline fan-out/fan-in thực tế, cân nhắc gán ID riêng cho từng nhánh, log hoặc lưu `Result<T>` thể hiện success/failure, rồi tổng hợp các lỗi theo thứ tự rõ ràng. Nếu muốn ném một exception tổng hợp với nhiều lỗi, có thể chọn một lỗi chính và `addSuppressed` các lỗi phụ, nhưng phải quyết định chính sách rõ và tránh lưu dữ liệu nhạy cảm trong exception message.

## 9. Timeout, cancellation và interrupted waiting dễ bị hiểu sai

### 9.1. `get(timeout, unit)` chỉ giới hạn thời gian đợi

`future.get(100, TimeUnit.MILLISECONDS)` có thể ném `TimeoutException` vì caller không nhận được kết quả trong 100 ms. **Future gốc chưa chắc đã hoàn tất**, và tác vụ executor có thể vẫn đang chạy. Nếu task kết thúc sau đó với lỗi khác, cần cơ chế quan sát completion riêng, nếu không sẽ bỏ mất exception thật.

`CompletableFuture.orTimeout(duration, unit)` (JDK 9+) là hành vi khác: nó làm **chính CompletableFuture đó** hoàn tất exceptional với `TimeoutException` khi hết hạn nếu trước đó chưa complete. `completeOnTimeout(value, ...)` thay bằng giá trị mặc định. Cả hai đều không hứa chấm dứt I/O hoặc interrupt tác vụ nguồn thực tế chỉ vì future đã có kết quả timeout. Khi cần hủy công việc thật, phải thiết kế cancellation/deadline đến tác vụ và tài nguyên phía dưới.

### 9.2. Cancellation không đồng nghĩa worker đã dừng

`future.cancel(true)` làm future chuyển trạng thái canceled nếu thành công. Riêng `CompletableFuture`, tham số `mayInterruptIfRunning` **không kiểm soát interrupt** của công việc thực thi như một `FutureTask` có thể làm. Không suy từ `CancellationException` rằng thread hoặc network call đã dừng. Dependent stages có thể hoàn tất exceptional bằng wrapper mang cancellation cause.

Nếu callback của future bị cancel thực hiện cleanup, phải làm idempotent; cancellation, timeout và normal completion có thể cạnh tranh. Đừng phát permit, đóng connection hoặc báo thành công hai lần do nhiều handler đua nhau.

### 9.3. Xử lý interruption đúng

`Future.get()` có thể ném `InterruptedException` khi thread đang chờ bị interrupt. Khi không thể xử lý ở tầng hiện tại, thường cần **đặt lại cờ interrupt** rồi truyền tín hiệu lên tầng gọi:

```java
try {
    return future.get();
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("wait interrupted", interrupted);
} catch (ExecutionException failed) {
    throw new IllegalStateException("operation failed", failed.getCause());
}
```

Đoạn này là **mẫu minh họa bên trong một phương thức có `future` phù hợp**, không phải tệp runnable độc lập. Trong môi trường dùng checked exception hoặc có policy cancellation riêng, có thể khai báo và ném `InterruptedException` để caller xử lý. Đừng nuốt interrupt rồi thử chờ vô hạn.

**`join()` không có phiên bản timed wait:** nếu cần deadline rõ và chính xác của thread đang chờ, dùng `get(timeout, ...)` hoặc thiết kế completion timeout và cancellation phù hợp. Timeout/chờ là một chiều của hệ thống; latency, queue wait, retry và deadline end-to-end cần được theo dõi nhất quán.

## 10. ThreadLocal, logging context và ranh giới async

Một số hệ thống đặt `requestId` vào `ThreadLocal`, rồi mong callback ở thread khác tự đọc được giá trị ấy. Nhưng `ThreadLocal` là trạng thái gắn với **thread hiện tại**, và executor thường tái sử dụng thread cho nhiều request. `thenApplyAsync` hay `supplyAsync` chuyển công việc sang thread khác, nên context không được chuyển tự động; `InheritableThreadLocal` cũng không đáng tin để truyền context qua thread pool có sẵn.

Cách đơn giản nhất là **truyền context như dữ liệu bất biến**:

```java
record RequestContext(String requestId) {}

static CompletableFuture<String> runPipeline(
        RequestContext context,
        java.util.concurrent.Executor executor) {

    return CompletableFuture.supplyAsync(() -> "payload", executor)
            .thenApply(payload -> decode(payload, context.requestId()));
}
```

Đây là **trích đoạn minh họa** trong class Java 17+, cần định nghĩa `decode`. `context` được capture rõ ràng trong callback; không phụ thuộc worker đã được thread pool dùng cho request trước đó. Nếu ứng dụng dùng hệ thống trace/MDC, cần cơ chế **capture/restore/clear** context có chủ đích ở boundary executor và bảo đảm cleanup trong `finally` để tránh rò context sang tác vụ sau.

Thread name có thể giúp nhận biết worker pool (`ForkJoinPool.commonPool-worker-*` hoặc thread tùy chỉnh), nhưng tên không phải unique request ID. Với `CompletableFuture.*Async` không truyền executor, chính sách thực thi mặc định thường sử dụng `ForkJoinPool.commonPool()` (với ngoại lệ về common pool parallelism trong đặc tả). Khi điều tra tính tái lập và độ nghẽn, **truyền executor tường minh** giúp biết hệ thống đang chạy ở đâu và dễ kiểm soát capacity.

## 11. Những mẫu lỗi phổ biến khi gắn callback quan sát

### 11.1. Dùng `exceptionally` để log nhưng vô tình nuốt lỗi

```java
CompletableFuture<String> recovered = source.exceptionally(failure -> {
    log(failure);
    return "OK";
});
```

Đoạn code **minh họa**, cần có `source` và `log`. Nếu upstream lỗi, future `recovered` sẽ thành công với `"OK"`. Downstream không còn nhận exceptional completion. Đó là recovery thực sự, chỉ nên làm khi fallback là hành vi đúng theo hợp đồng, ví dụ dữ liệu optional có giá trị mặc định an toàn. Nếu mục đích chỉ quan sát, dùng `whenComplete` và để outcome lan truyền.

### 11.2. Chỉ log message

```java
System.err.println(failure.getMessage());
```

Đoạn này mất loại exception, stack, cause và suppressed exceptions. Với logging có hỗ trợ `Throwable`, chuyển cả đối tượng lỗi:

```java
logger.log(java.util.logging.Level.SEVERE, "stage=parse failed", failure);
```

Hai đoạn là **minh họa không độc lập**, lần lượt cần `failure` hoặc `logger`. Hệ thống sản xuất cần kiểm soát dữ liệu nhạy cảm trong log và tránh spam ở mọi stage.

### 11.3. Quên chờ hoặc quan sát future

`CompletableFuture.runAsync(() -> doWork());` trả future ngay. Nếu caller bỏ reference và không có một terminal observer hoặc owner quản lý lifecycle, lỗi trong task có thể nằm trong trạng thái future mà không được báo cáo rõ ràng trong luồng gọi ban đầu. Đừng suy “không thấy stack trace trên console” nghĩa là tác vụ đã thành công. Thiết kế rõ nơi join/handle/whenComplete và trách nhiệm báo cáo lỗi.

### 11.4. Gắn observer nhưng không hiểu future mới

Các phương thức `thenApply`, `whenComplete`, `handle`, `exceptionally` đều trả về **future khác**. Một callback có thể tạo thêm failure; nếu chỉ quan sát future gốc mà bỏ mất future mới, lỗi callback lại không được theo dõi. Cần xác định **terminal future** mà caller chờ và các stage quan trọng phải được quan sát.

### 11.5. Block hoặc retry ngay trong callback

Dùng `join()` bên trong stage cùng executor nhỏ để chờ việc khác chạy trên chính executor ấy có nguy cơ starvation hoặc deadlock. Retry nóng trong `exceptionally` có thể tạo retry storm. Ưu tiên nonblocking composition (`thenCompose`), giới hạn retry/backoff, deadline và có ownership rõ cho tác vụ nền.

## 12. Quy trình điều tra một lỗi async trong thực tế

Giả sử cảnh báo nhận được: `CompletionException` từ `CompletableFuture.join()` nhưng không rõ stage nào lỗi. Làm theo thứ tự:

1. **Đảm bảo có full throwable:** thu trace gồm `Caused by` và `Suppressed`, loại bỏ việc chỉ log message. Giữ log/correlation ID của cùng công việc.
2. **Phân biệt observation và throw site:** nhận diện `join()`/`get()` ở caller, mở các `Caused by` và tìm frame ứng dụng đầu tiên ở từng tầng.
3. **Xác định stage:** tra lại chuỗi `supplyAsync → thenApply → thenCompose → whenComplete...`; xem stage nào được chạy và stage nào bị bỏ qua vì upstream exceptional.
4. **Kiểm tra thread/executor:** stage thường, stage `Async`, custom executor, tình trạng shutdown/rejection, queue saturation và worker starvation. Chú ý callback có thể chạy trên thread đăng ký nếu parent đã hoàn tất.
5. **Kiểm tra loại failure:** lỗi dữ liệu, lỗi downstream, cancellation, timeout hay interruption. Tách lỗi thật trong task khỏi timeout chỉ xảy ra ở caller.
6. **Đọc các nhánh song song:** với `allOf`, quan sát từng child future; không coi cause duy nhất của aggregate là toàn bộ bức tranh.
7. **Xác nhận chính sách xử lý:** `handle`/`exceptionally` có biến lỗi thành fallback? `whenComplete` có observer ném lỗi mới? Có nơi bỏ terminal future mà không log?
8. **Tái hiện có kiểm soát:** dùng executor xác định, `CompletableFuture.completedFuture` hoặc `failedFuture`, điều khiển completion bằng tay, và assert exception types/cause chain thay vì timing tùy hứng.

Khi báo cáo nguyên nhân gốc, dùng câu cụ thể như: “Stage `decode` của request ID X chạy trên executor Y, ném `IllegalArgumentException` do payload không hợp lệ; future cuối báo `CompletionException` tại `join()` trong caller.” Cách trình bày này phân biệt nguyên nhân, đường lan truyền và nơi phát hiện.

## 13. Kiểm thử các đường lỗi mà không phụ thuộc timing

Một unit test tốt cho pipeline bất đồng bộ phải khống chế được kết quả và không cần `Thread.sleep()`. Ví dụ JDK 17 với một `CompletableFuture` chủ động complete exceptionally:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class FailurePropagationTestDemo {
    public static void main(String[] args) {
        CompletableFuture<String> upstream = new CompletableFuture<>();
        CompletableFuture<Integer> downstream = upstream.thenApply(String::length);

        upstream.completeExceptionally(
                new IllegalStateException("upstream failed"));

        try {
            downstream.join();
            throw new AssertionError("Expected exceptional completion");
        } catch (CompletionException expected) {
            Throwable cause = expected.getCause();
            if (!(cause instanceof IllegalStateException)
                    || !"upstream failed".equals(cause.getMessage())) {
                throw new AssertionError("Unexpected cause", expected);
            }
            System.out.println("failure propagated");
        }
    }
}
```

Chạy:

```bash
javac FailurePropagationTestDemo.java
java FailurePropagationTestDemo
```

Stdout:

```text
failure propagated
```

Ở đây `String::length` không chạy vì upstream đã hoàn tất exceptional. Kiểm thử có thể tiến thêm bằng biến đếm `AtomicInteger` trong callback để assert `0` invocation. Dùng `CompletableFuture.failedFuture(cause)` (Java 9+) khi không cần kiểm soát thời điểm completion; dùng `new CompletableFuture<>()` khi cần mô phỏng race giữa các nhánh.

Những trường hợp nên có test riêng:

- **Failure at source:** `supplyAsync`/`runAsync` ném lỗi; dependent success-only stage không chạy và terminal future exceptional.
- **Failure at intermediate stage:** callback `thenApply` ném exception; `join` có `CompletionException` và nguyên nhân gốc được bảo toàn.
- **Recovery:** `exceptionally`/`handle` trả fallback chỉ khi đã quyết định hợp đồng; không còn exception ở terminal future.
- **Observer:** `whenComplete` log nhưng không nuốt exception; callback logging không ném lỗi.
- **Failure in inner future:** dùng `thenCompose`, kiểm tra exceptional completion được propagate đúng.
- **Multiple failures:** `allOf` báo tổng thất bại; từng child có lý do riêng.
- **Cancellation/timeout:** cancel không bị diễn giải thành task đã ngừng; các deadline được kiểm thử với đồng hồ/scheduler điều khiển được khi cần.
- **Interrupted wait:** thread gọi `get()` nhận `InterruptedException` và policy preserve/propagate interrupt được tuân thủ.

Đừng dùng assert nguyên văn stack trace hoặc giả định dòng `CompletableFuture.java:XXXX` luôn cố định. Khi cần kiểm tra nơi phát sinh, assert cause type, message/context và một số frame ứng dụng ổn định; để integration/stress test xác nhận các điều kiện scheduling thực tế.

## 14. Bảng nhận diện nhanh

| Triệu chứng | Cách đọc/kiểm tra |
| --- | --- |
| Trace bắt đầu ở `CompletableFuture.join` hoặc `reportJoin` | Đây thường là **observer**; mở `Caused by` để tìm nơi lỗi được tạo |
| `ExecutionException` xuất hiện ở `get()` | Lấy `getCause()` và đọc causal chain |
| Exception chỉ xuất hiện trong callback `whenComplete` | Xác định đó là lỗi upstream được observer nhìn thấy hay chính observer đã ném lỗi |
| `CompletionException` lồng nhau | Unwrap chỉ wrapper chuẩn; vẫn giữ và log full trace |
| Không có frame gọi `supplyAsync` trong cause | Thread hop làm mất stack call chain trực tiếp; bổ sung correlation/stage breadcrumbs |
| `allOf` trả một nguyên nhân nhưng nhiều task lỗi | Kiểm tra từng child future sau completion |
| Người gọi nhận `TimeoutException` | Xác định timeout do `get(timeout)` hay `orTimeout`; xem tác vụ nền còn chạy không |
| `CancellationException` | Phân biệt trạng thái canceled của future với việc worker/IO thật đã dừng |
| Không thấy log khi async task lỗi | Future có được quan sát/ghi nhận terminal outcome chưa? |
| Đã dùng `exceptionally` nhưng downstream báo thành công | Có thể handler trả fallback và chủ động khôi phục |
| Lỗi xảy ra ngẫu nhiên khi pool tải cao | Kiểm tra scheduler, queue, rejection, starvation, shared state và races; không đoán chỉ từ trace |

**Điều cần nhớ:** Stack trace trong Java async là bằng chứng theo **chuỗi exception/cause và ranh giới stage**, không phải một call stack tuyến tính của cả request. Muốn chẩn đoán đúng, xác định exception gốc, giữ nguyên causal chain, gắn stage/correlation ID, hiểu `join()`/`get()`/callback và phân biệt lỗi thật với timeout hoặc cancellation.