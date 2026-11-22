# Lan truyền lỗi qua các stage phụ thuộc trong CompletableFuture (Java)

## 1. Một stage thất bại thì các stage phía sau ra sao?

`CompletableFuture<T>` biểu diễn một phép tính sẽ **hoàn tất bằng giá trị** hoặc **hoàn tất bất thường** (*exceptional completion*). Nhiều stage có thể nối với nhau thành một chuỗi xử lý bằng các phương thức như `thenApply`, `thenCompose`, `thenAccept`, `handle` hay `exceptionally`.

Quy tắc căn bản của chuỗi phụ thuộc là:

> Khi một stage nguồn hoàn tất bất thường, những stage phụ thuộc **cần giá trị thành công** của nguồn sẽ không chạy callback xử lý bình thường. Stage phụ thuộc vẫn được hoàn tất, nhưng **hoàn tất bất thường** để truyền thông tin thất bại xuống chuỗi, trừ khi có stage xử lý lỗi thích hợp.

Ví dụ:

```java
CompletableFuture<Integer> result =
        CompletableFuture.completedFuture(5)
            .thenApply(n -> n * 2)
            .thenApply(n -> {
                throw new IllegalStateException("cannot convert");
            });
```

Đây là **mảnh code đặt trong một phương thức** có import `java.util.concurrent.CompletableFuture`. Stage đầu trả `5`, stage kế trả `10`, callback cuối ném `IllegalStateException`. Future `result` hoàn tất bất thường, thay vì trả một `Integer`. Nếu có thêm `thenApply` phụ thuộc vào `result`, callback của nó **không được gọi** và stage mới cũng nhận trạng thái bất thường.

**“Truyền lỗi” không có nghĩa Throwable tự bay từ một worker thread sang call stack của một thread khác.** Đây là cơ chế **truyền trạng thái hoàn tất bất thường giữa các đối tượng stage**; caller chỉ nhận ngoại lệ khi chủ động chờ/lấy kết quả qua `join()`, `get()`, hoặc khi stage có handler xử lý lỗi.

## 2. Mô hình stage, dependency và completion

Một stage có thể ở những trạng thái khái niệm:

- **Incomplete:** chưa có kết quả cuối cùng; những stage phụ thuộc đang chờ điều kiện hoàn tất.
- **Completed normally:** có giá trị kết quả, có thể là `null` đối với kiểu `Void` hoặc hợp đồng cho phép.
- **Completed exceptionally:** kết thúc bất thường do exception, lỗi bị bọc, hoặc cancellation; không có kết quả thành công để truyền cho callback bình thường.

Một chuỗi:

```text
source (value)
   |
   v
thenApply A  --> thành công: output A
   |
   v
thenApply B  --> ném exception E
   |
   +-------------------------------+
   |                               |
   v                               v
thenApply C                     exceptionally D
(callback C bị bỏ qua)          (nhận E, có thể fallback)
   |                               |
   v                               v
exceptional completion          normal completion nếu D trả giá trị
```

Hai nhánh phụ thuộc vào cùng nguồn không nhất thiết có cùng kết quả cuối. Một nhánh có thể phục hồi để trả thành công; nhánh khác có thể tiếp tục thất bại. **Xử lý lỗi trong một stage phụ thuộc không sửa ngược trạng thái của stage nguồn**. Tư duy này quan trọng khi ghép nhiều luồng xử lý, API hoặc request.

## 3. Khi nào callback tiếp theo được chạy?

Phải phân biệt callback **chỉ nhận giá trị thành công**, callback **chỉ chạy khi lỗi**, và callback **xử lý cả hai**.

| API stage | Điều kiện gọi callback của stage đó | Kết quả khi upstream lỗi |
| --- | --- | --- |
| `thenApply(fn)` | Upstream thành công; cần giá trị | Bỏ qua `fn`; stage mới hoàn tất bất thường |
| `thenAccept(action)` | Upstream thành công | Bỏ qua `action`; stage mới hoàn tất bất thường |
| `thenRun(action)` | Upstream thành công (không dùng value) | Bỏ qua `action`; stage mới hoàn tất bất thường |
| `thenCompose(fn)` | Upstream thành công; `fn` trả stage khác | Upstream lỗi thì `fn` không gọi; stage mới lỗi |
| `thenCombine(other, fn)` | Cả hai nguồn thành công | Không gọi `fn` nếu điều kiện thành công không đủ; stage kết hợp lỗi |
| `exceptionally(fn)` | Upstream lỗi | `fn` có thể trả giá trị fallback và phục hồi |
| `handle((v,e) -> ...)` | Upstream thành công hoặc lỗi | Có thể biến kết quả/lỗi thành một giá trị hoặc ném lỗi mới |
| `whenComplete((v,e) -> ...)` | Upstream thành công hoặc lỗi | Chủ yếu quan sát; thông thường giữ trạng thái/kết quả cũ |

Trong cả ba phương thức `thenApply`, `thenAccept`, `thenRun`, nếu callback **được gọi và tự ném exception**, stage được tạo ra cũng hoàn tất bất thường. Cơ chế lan truyền lỗi vì thế xảy ra cả khi **upstream đã lỗi** lẫn khi **một callback downstream tự tạo lỗi mới**.

Một chi tiết đáng chú ý: `thenRun` không nhận value, nhưng nó **vẫn phụ thuộc vào sự hoàn tất thành công** của nguồn. Không dùng giá trị không có nghĩa callback sẽ chạy dù nguồn lỗi.

## 4. Lan truyền giữa các stage kế tiếp

Xét chuỗi:

```java
CompletableFuture<String> pipeline = fetchUser()
        .thenApply(user -> parseUser(user))
        .thenApply(parsed -> formatDisplay(parsed))
        .thenApply(text -> decorate(text));
```

Đây là **mảnh thiết kế**, các phương thức `fetchUser()`, `parseUser()`, `formatDisplay()` và `decorate()` do ứng dụng định nghĩa. Giả sử `parseUser` ném `IllegalArgumentException`:

1. Stage `fetchUser()` đã thành công, nên `parseUser` được gọi.
2. Callback `parseUser` ném exception, làm stage của `thenApply` thứ nhất **hoàn tất bất thường**.
3. `formatDisplay` cần giá trị `parsed` từ stage lỗi; do không có giá trị thành công, callback **không chạy**.
4. `decorate` cũng không được gọi vì stage trước đó hoàn tất bất thường.
5. Future `pipeline` ở cuối có trạng thái hoàn tất bất thường, dù code đã tạo đủ các stage khi dựng pipeline.

Không có yêu cầu mọi stage **phải chạy** để stage cuối hoàn tất. Khi dependency thất bại, runtime có thể truyền tín hiệu exceptional completion qua cả chuỗi mà không gọi callback xử lý dữ liệu nào phía sau.

Điều này giúp tránh xử lý một giá trị thiếu hoặc không hợp lệ; đồng thời dễ gây lỗi nếu ứng dụng đặt những hành động bắt buộc (*audit*, *cleanup*, *metrics*) trong `thenApply` cuối: khi stage trước lỗi, những hành động đó **không bao giờ chạy**. Dùng `whenComplete`, `handle` hoặc cơ chế cleanup riêng khi cần quan sát cả hai trạng thái.

## 5. Ví dụ Java 17+: kiểm chứng nhiều nhánh lan truyền và phục hồi

Chương trình độc lập dưới đây kiểm tra:

- Stage thứ hai ném `IllegalStateException`.
- Một `thenApply` nằm sau bị **bỏ qua**.
- `exceptionally` tạo fallback, cho phép stage sau chạy bình thường.
- `handle` chuyển lỗi thành kết quả.
- `whenComplete` quan sát lỗi nhưng **không tự phục hồi**.
- `thenCompose` nhận future con lỗi.
- `get()` và `join()` báo lỗi theo wrapper khác nhau.
- `allOf` cho trạng thái bất thường khi một thành viên lỗi, nhưng future độc lập vẫn thành công.

Tạo file **`CompletableFutureFailureChainDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.atomic.AtomicInteger;

public class CompletableFutureFailureChainDemo {
    static Throwable root(Throwable error) {
        while ((error instanceof CompletionException
                || error instanceof ExecutionException)
                && error.getCause() != null) {
            error = error.getCause();
        }
        return error;
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicInteger downstreamRuns = new AtomicInteger();

        CompletableFuture<Integer> chain =
                CompletableFuture.completedFuture(4)
                    .thenApply(n -> n * 2)
                    .thenApply(n -> {
                        if (n == 8) {
                            throw new IllegalStateException("conversion failed");
                        }
                        return n;
                    })
                    .thenApply(n -> {
                        downstreamRuns.incrementAndGet();
                        return n + 1;
                    });

        try {
            chain.join();
        } catch (CompletionException ex) {
            System.out.println("CHAIN: " + root(ex).getClass().getSimpleName());
        }
        System.out.println("DOWNSTREAM RUNS: " + downstreamRuns.get());

        CompletableFuture<Integer> recovered =
                chain.exceptionally(ex -> 99).thenApply(n -> n + 1);
        System.out.println("RECOVERY: " + recovered.join());

        CompletableFuture<String> handled = chain.handle((value, error) ->
                error == null ? "ok" : "failed");
        System.out.println("HANDLE: " + handled.join());

        CompletableFuture<Integer> observed = chain.whenComplete(
                (value, error) -> {
                    if (error != null) {
                        System.out.println("OBSERVED: "
                                + root(error).getClass().getSimpleName());
                    }
                });
        try {
            observed.join();
        } catch (CompletionException ex) {
            System.out.println("WHENCOMPLETE: "
                    + root(ex).getClass().getSimpleName());
        }

        CompletableFuture<Integer> composed =
                CompletableFuture.completedFuture(5)
                    .thenCompose(n -> CompletableFuture.<Integer>failedFuture(
                            new IllegalArgumentException("remote failed")))
                    .thenApply(n -> n + 1);
        try {
            composed.join();
        } catch (CompletionException ex) {
            System.out.println("COMPOSE: "
                    + root(ex).getClass().getSimpleName());
        }

        try {
            chain.get();
        } catch (ExecutionException ex) {
            System.out.println("GET: " + root(ex).getClass().getSimpleName());
        }

        CompletableFuture<Integer> independent =
                CompletableFuture.completedFuture(10);
        CompletableFuture<Void> combined =
                CompletableFuture.allOf(chain, independent);
        try {
            combined.join();
        } catch (CompletionException ex) {
            System.out.println("ALLOF: "
                    + root(ex).getClass().getSimpleName());
        }
        System.out.println("INDEPENDENT: " + independent.join());
        System.out.println("SOURCE STILL FAILED: " + chain.isCompletedExceptionally());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên, từ thư mục chứa file:

```bash
javac -encoding UTF-8 CompletableFutureFailureChainDemo.java
java CompletableFutureFailureChainDemo
```

Kết quả chuẩn:

```text
CHAIN: IllegalStateException
DOWNSTREAM RUNS: 0
RECOVERY: 100
HANDLE: failed
OBSERVED: IllegalStateException
WHENCOMPLETE: IllegalStateException
COMPOSE: IllegalArgumentException
GET: IllegalStateException
ALLOF: IllegalStateException
INDEPENDENT: 10
SOURCE STILL FAILED: true
```

**Diễn giải từng điểm quan trọng:**

1. `chain` được xây từ `4 → 8`, sau đó một callback ném lỗi. `thenApply` cuối của `chain` bị bỏ qua, nên `downstreamRuns` là `0`.
2. `chain.exceptionally(ex -> 99)` tạo **stage khác** trả `99`, rồi `thenApply` cộng `1` nên `recovered.join()` trả `100`. `chain` gốc vẫn exceptional.
3. `handle` nhận cả giá trị và lỗi; ở đường lỗi nó tạo chuỗi `"failed"` nên stage `handled` hoàn tất bình thường.
4. `whenComplete` in loại lỗi và stage `observed` vẫn thất bại. `whenComplete` là cơ chế quan sát, không phải fallback.
5. `thenCompose` nhận một future con đã hoàn tất bất thường qua `failedFuture`; lỗi đi vào stage `composed`, callback `thenApply` sau đó bị bỏ qua.
6. `join()` của một future exceptional thường ném `CompletionException`, còn `get()` ném `ExecutionException`; hàm `root` bỏ các wrapper này để in tên nguyên nhân.
7. `allOf` hoàn tất bất thường vì một trong hai thành viên lỗi. Future `independent` vẫn chứa `10`; lỗi của `chain` **không tự làm future độc lập thất bại**.
8. `chain.isCompletedExceptionally()` vẫn là `true` dù đã tạo các nhánh `recovered` và `handled` thành công.

Ví dụ dùng `completedFuture` và `failedFuture` để kết quả có thứ tự xác định, không phụ thuộc scheduler. `root` chỉ minh họa cách đọc cause chain có wrapper; trong ứng dụng thật không phải mọi `CompletionException`/`ExecutionException` đều nên được bỏ qua một cách máy móc nếu chính wrapper mang ngữ nghĩa nghiệp vụ.

## 6. `join()`, `get()` và nguyên nhân thực

Khi một `CompletableFuture` hoàn tất bất thường, caller không “nhận exception ngay lập tức” lúc dựng stage. Thông tin về lỗi được lưu trong trạng thái completion, sau đó các API chờ/lấy kết quả **ném exception ở luồng đang gọi API đó**.

| API | Khi future đã lỗi | Điểm cần nhớ |
| --- | --- | --- |
| `future.join()` | Thường ném `CompletionException`, nguyên nhân trong `getCause()` | Unchecked wrapper; không khai báo checked exception |
| `future.get()` | Ném `ExecutionException`, nguyên nhân trong `getCause()` | Đồng thời có thể ném `InterruptedException` nếu thread đang chờ bị ngắt |
| `future.get(timeout, unit)` | Tương tự `get()` nếu future lỗi, nhưng có thêm `TimeoutException` nếu chưa có kết quả kịp hạn | Timeout của caller không tự hủy upstream |
| `future.isCompletedExceptionally()` | Trả `true` khi future hoàn tất bất thường, gồm cancellation | Chỉ là trạng thái, không cung cấp chi tiết nguyên nhân |
| `future.isDone()` | Trả `true` khi hoàn tất bằng giá trị, lỗi hoặc hủy | Không đồng nghĩa thành công |
| `future.isCancelled()` | Cho biết chính future đó đã bị hủy | Phân biệt cancellation với lỗi nghiệp vụ |

Một stage phụ thuộc có thể chứa `CompletionException` có cause là exception ban đầu. Vì vậy `getCause()` có thể trả wrapper trung gian, tùy nguồn và cách hoàn tất. Khi cần chẩn đoán, đi theo cause chain với giới hạn, ghi cả bối cảnh stage, đừng chỉ in `ex.getMessage()` hoặc đoán loại lỗi từ text.

`InterruptedException` ở `future.get()` là tín hiệu **luồng caller đang chờ** bị ngắt, khác với lỗi của tác vụ nguồn. Khi caller không thể truyền tiếp `InterruptedException`, thường nên `Thread.currentThread().interrupt()` rồi kết thúc hoặc thực hiện chính sách hủy phù hợp. Việc caller bị ngắt **không tự hoàn tất hay hủy future nguồn**.

Một future đã bị `cancel(...)` có thể khiến `join()`/`get()` ném `CancellationException` trực tiếp; không dùng một `catch (CompletionException)` duy nhất rồi tuyên bố bao phủ mọi trường hợp cancellation.

## 7. Phục hồi với `exceptionally`: biến lỗi thành giá trị hợp lệ

`exceptionally(fn)` chỉ gọi `fn` khi stage nguồn hoàn tất bất thường. Nếu stage nguồn thành công, nó giữ nguyên kết quả thành công (theo kiểu result) mà không gọi fallback.

```java
CompletableFuture<Integer> finalCount = readCountAsync()
        .exceptionally(ex -> {
            recordFailure(ex);
            return 0;
        })
        .thenApply(n -> n + 1);
```

Đây là mảnh code có `readCountAsync()` và `recordFailure(Throwable)` do ứng dụng định nghĩa. Khi upstream lỗi, callback trả `0`, sau đó `thenApply` được gọi và tạo `1`. Khi upstream thành công với `n`, callback fallback không chạy và kết quả cuối là `n + 1`.

**Cẩn thận với giá trị fallback:** `0` có thể là một count thực sự hợp lệ; nếu `0` làm che lỗi quan trọng, caller sẽ tưởng đã đọc dữ liệu đúng. Chỉ dùng fallback khi nghiệp vụ cho phép và có cơ chế ghi nhận cảnh báo, độ tin cậy dữ liệu hoặc trạng thái “degraded” khi cần.

Nếu callback `exceptionally` tự ném lỗi, stage được trả về sẽ **hoàn tất bất thường vì lỗi mới**. Có thể giữ cause gốc bằng constructor có `cause` khi phù hợp, chẳng hạn:

```java
.exceptionally(ex -> {
    throw new IllegalStateException("Fallback also failed", ex);
})
```

Đây là mảnh chain, không phải toàn bộ chương trình. Một lần nữa, **stage mới** mang kết quả, còn stage upstream không bị sửa.

## 8. `handle`: thao tác trên cả kết quả và lỗi

`handle((value, error) -> result)` luôn nhận completion của stage trước, dù thành công hay bất thường:

- Khi thành công: `error == null` và `value` có kết quả (có thể chính giá trị là `null` nếu hợp đồng cho phép).
- Khi thất bại: `error != null` và không có giá trị thành công để dùng.
- Nếu callback trả giá trị bình thường, stage mới **thành công**.
- Nếu callback ném lỗi, stage mới **thất bại**.

Ví dụ:

```java
CompletableFuture<String> display = loadProfileAsync()
        .handle((profile, error) -> {
            if (error != null) {
                return "Profile temporarily unavailable";
            }
            return profile.displayName();
        });
```

Mảnh code trên giả định `loadProfileAsync()` trả một future có kiểu `Profile` với `displayName()`, không phải chương trình độc lập. Không nên gọi `profile.displayName()` khi `error != null`. Ngược lại, nếu loader có thể **thành công nhưng trả `null`**, vẫn cần kiểm tra `profile` theo hợp đồng để tránh tạo `NullPointerException` ở chính stage xử lý lỗi.

`handle` phù hợp khi muốn thống nhất hai đường thành một kiểu kết quả, chẳng hạn `Result<T>` chứa `value/error`. Nhưng nó cũng có thể vô tình nuốt lỗi nếu nhánh `error != null` luôn trả một giá trị giả mà không phản ánh thất bại cho tầng nghiệp vụ.

## 9. `whenComplete`: quan sát, không tự động phục hồi

`whenComplete((value,error) -> action)` cho phép thực thi một callback khi nguồn hoàn tất, dù thành công hay lỗi; thường dùng cho log, metric, trace hoặc cleanup không thay đổi kết quả:

```java
CompletableFuture<Order> observed = loadOrderAsync()
        .whenComplete((order, error) -> {
            if (error != null) {
                metrics.recordFailure(error);
            } else {
                metrics.recordSuccess();
            }
        });
```

Mảnh code trên cần `Order`, `loadOrderAsync()` và `metrics` do ứng dụng định nghĩa. Nếu nguồn thất bại và callback `whenComplete` chạy bình thường, stage `observed` vẫn hoàn tất bất thường. Nếu nguồn thành công và callback chạy bình thường, stage `observed` mang cùng kết quả.

**Lưu ý khi callback giám sát cũng ném exception:**

- Nguồn **thành công**, `whenComplete` ném lỗi → stage kết quả có thể **thất bại vì callback**.
- Nguồn **đã thất bại**, `whenComplete` cũng ném → theo hợp đồng `CompletionStage.whenComplete`, **lỗi gốc được ưu tiên** khi xác định exception của stage kết quả.
- Callback `whenComplete` không nên chứa nghiệp vụ phụ thuộc quá nhiều vào trạng thái bất định, hoặc làm thất bại toàn pipeline chỉ vì metric/log không sẵn sàng.

Nếu muốn **chuyển lỗi thành giá trị khác**, dùng `exceptionally` hoặc `handle`. Nếu muốn **chạy side effect và giữ kết quả**, dùng `whenComplete` với đường giám sát được thiết kế cẩn thận.

## 10. `thenCompose` và lan truyền từ future con

`thenCompose(fn)` được dùng khi một callback trả về **một stage khác**, ví dụ truy vấn thông tin tài khoản rồi tải giao dịch từ hệ thống ngoài. Nó giúp tránh kiểu lồng `CompletableFuture<CompletableFuture<T>>`.

```java
CompletableFuture<Account> result = findUserAsync(userId)
        .thenCompose(user -> findAccountAsync(user.accountId()));
```

Đây là mảnh code với `findUserAsync` và `findAccountAsync` đã được định nghĩa. Có **ba đường lỗi** chính:

1. `findUserAsync` thất bại → callback của `thenCompose` **không được gọi**; stage kết quả thất bại.
2. `findUserAsync` thành công nhưng callback `user -> ...` tự ném exception → stage kết quả thất bại.
3. Callback trả về một future con bình thường, nhưng **future con sau đó thất bại** → stage kết quả cuối cũng hoàn tất bất thường theo lỗi của future con.

`thenCompose` không tự bắt, retry hoặc rollback lỗi của future con. Nó cũng không bắt buộc chạy trên một thread nhất định; callback có thể chạy ở luồng hoàn tất nguồn hoặc luồng khác theo chính sách của API và phiên bản sync/async.

Với Java 17, có `CompletableFuture.failedFuture(Throwable)` để tạo một future đã hoàn tất bất thường, như ví dụ:

```java
CompletableFuture<Integer> unavailable =
        CompletableFuture.failedFuture(
                new IllegalStateException("backend unavailable"));
```

Đây là mảnh code hợp lệ bên trong một phương thức. Nó hữu ích để unit test đường lỗi mà không cần khởi tạo thread hay tạo kết nối thất bại thật.

## 11. `exceptionallyCompose`: fallback cũng là một hoạt động async

Khi quá trình phục hồi cần gọi **một future dự phòng** thay vì trả ngay giá trị, từ các JDK hiện đại (bao gồm JDK 17) có `exceptionallyCompose`:

```java
CompletableFuture<String> data = fetchPrimaryAsync()
        .exceptionallyCompose(ex -> fetchReplicaAsync());
```

Đây là mảnh minh họa với `fetchPrimaryAsync()` và `fetchReplicaAsync()` trả về `CompletableFuture<String>`. Nếu primary thành công, callback dự phòng không chạy. Nếu primary lỗi, callback được dùng để lấy một stage mới; stage mới thành công thì `data` thành công, còn stage dự phòng lỗi thì `data` cũng lỗi.

Tương tự `exceptionally`, callback fallback có thể tự ném exception; việc callback hoặc replica thành công không thay đổi trạng thái lỗi đã lưu ở stage primary. Nếu cần giữ cả lỗi primary khi replica cũng lỗi, cần thu thập bối cảnh/cause phù hợp; **không** được kỳ vọng API tự hợp nhất hai nguyên nhân thành danh sách đầy đủ.

Một fallback tự động có thể gây lưu lượng ngoài dự kiến hoặc chuyển dữ liệu qua miền tin cậy khác; hãy xác định timeout, độ nhất quán dữ liệu, chính sách retry và điều kiện bảo mật của replica.

## 12. Quan hệ lỗi ở nhánh rẽ (fan-out)

Một nguồn có thể có nhiều stage phụ thuộc:

```java
CompletableFuture<Data> source = loadAsync();
CompletableFuture<Summary> summary =
        source.thenApply(this::makeSummary);
CompletableFuture<Report> report =
        source.thenApply(this::makeReport);
```

Đây là mảnh trong một lớp có các kiểu `Data`, `Summary`, `Report` và phương thức `loadAsync()`, `makeSummary`, `makeReport`. Nếu `source` thất bại, **cả hai stage phụ thuộc cần giá trị thành công** có thể hoàn tất bất thường mà không gọi callback. Nếu `source` thành công nhưng `makeSummary` thất bại, `report` **không tự thất bại** chỉ vì nhánh chị em gặp lỗi; mỗi nhánh xử lý kết quả/cause riêng.

Các lưu ý thiết kế:

- Một nhánh gọi `exceptionally` và phục hồi không có nghĩa các nhánh khác cũng được phục hồi.
- Một nhánh ném exception trong callback không tự động cancel nhánh chị em.
- Nếu tất cả nhánh chia sẻ mutable object làm kết quả của `source`, lỗi một nhánh không tự rollback trạng thái object đã bị sửa.
- Nếu các callback chạy đồng thời, cần bảo đảm thread safety và không giả định thứ tự log.
- Với lỗi có thể quan sát ở nhiều stage, tránh ghi nhiều log cùng một sự cố mà không có correlation ID.

## 13. Kết hợp bằng `thenCombine`, `allOf` và `anyOf`

### `thenCombine` / `thenAcceptBoth` / `runAfterBoth`

Những phép kết hợp dạng *both* yêu cầu cả hai nguồn thành công trước khi chạy callback thành công:

```java
CompletableFuture<Result> combined =
        first.thenCombine(second, (a, b) -> merge(a, b));
```

Đây là mảnh code trong một phương thức có `first`, `second` và `merge` được định nghĩa. Nếu một nguồn lỗi, callback `merge` **không được gọi**; stage kết quả hoàn tất bất thường khi điều kiện hoàn tất của phép kết hợp được thỏa. Nếu **cả hai nguồn cùng lỗi**, API không cung cấp một danh sách đầy đủ cả hai exception dưới dạng kết quả mặc định; lựa chọn lỗi được quan sát có thể phụ thuộc quan hệ dependency và triển khai. Nếu cần audit cả hai, phải theo dõi riêng cả hai nguồn.

### `CompletableFuture.allOf(...)`

`allOf(a,b,...)` tạo một `CompletableFuture<Void>` hoàn tất khi **tất cả** future đầu vào hoàn tất. Nếu **bất kỳ** đầu vào nào hoàn tất bất thường thì `allOf` cũng hoàn tất bất thường. Nó không tạo một list kết quả; caller muốn lấy từng giá trị phải giữ các future con và đọc chúng theo hợp đồng sau khi phù hợp.

`allOf` **không tự cancel các future khác chỉ vì một future lỗi**. Việc một future độc lập đã thành công hay vẫn đang chạy là vấn đề riêng. Nếu nhiều future lỗi, exception lộ ra từ kết quả tổng hợp **không thay thế việc thu thập tất cả lỗi** khi ứng dụng cần đầy đủ chẩn đoán. Không giả định `allOf` là “fail fast và tự hủy sibling” giống một cơ chế structured concurrency đặc thù.

### `CompletableFuture.anyOf(...)`

`anyOf(a,b,...)` hoàn tất khi **bất kỳ** future nào hoàn tất đầu tiên theo điều kiện hoàn tất của nó. Nếu future đầu tiên hoàn tất **bất thường**, `anyOf` có thể cũng hoàn tất bất thường, dù future khác sau đó thành công. Đây không phải “trả về kết quả thành công đầu tiên”; muốn đợi **thành công đầu tiên** cần thiết kế riêng với điều kiện lỗi và hủy.

Nếu có nhiều future hoàn tất gần nhau, đừng phụ thuộc vào thứ tự xử lý hay loại lỗi “chắc chắn được chọn” nếu không có sự đồng bộ và ràng buộc rõ ràng.

## 14. Cancellation cũng có thể lan truyền dưới dạng exceptional completion

Khi gọi `cancel(...)` lên một `CompletableFuture` chưa hoàn tất, future ấy được **hoàn tất bất thường bằng `CancellationException`**. Những stage phụ thuộc vào thành công của nó sẽ không chạy callback thành công; các stage đó thường được hoàn tất bất thường, có thể xuất hiện `CompletionException` bọc `CancellationException` khi quan sát.

Cần phân biệt:

- **Cancel upstream:** các stage phụ thuộc không nhận được giá trị thành công của nguồn đã hủy; chúng có thể trở thành exceptional.
- **Cancel một dependent stage:** không mặc nhiên dừng công việc của upstream hoặc sibling; không suy ra có cơ chế hủy ngược lan truyền một cách tổng quát.
- **`CompletableFuture.cancel(boolean)`:** tham số `mayInterruptIfRunning` không có vai trò giống `FutureTask` trong việc ngắt luồng thực thi; việc cancel một `CompletableFuture` **không tự bảo đảm dừng mã đang chạy**.
- **Future wrapper:** `isCompletedExceptionally()` trả `true` cả khi bị cancel; muốn phân biệt cần dùng `isCancelled()` hoặc kiểm tra exception.
- **External side effects:** cancel future không tự rollback ghi DB, file, HTTP request đã được gửi.

Ví dụ quan sát một cancellation trực tiếp:

```java
CompletableFuture<Integer> source = new CompletableFuture<>();
CompletableFuture<Integer> dependent = source.thenApply(n -> n * 2);
source.cancel(false);
// dependent không thể chạy thenApply với giá trị thành công của source.
```

Đây là mảnh code minh họa. Không nên suy luận mọi dependent đều có `isCancelled() == true`; một dependent có thể hoàn tất bất thường qua wrapper chứa `CancellationException` mà **không tự mang cờ cancelled giống nguồn**.

Nếu dùng cả executor, task chạy nền và `CompletableFuture`, cần có giao thức hủy riêng phù hợp với API và trạng thái thực tế.

## 15. Timeout là một nguồn exceptional completion khác

Hai API hữu ích trên `CompletableFuture`:

- `orTimeout(timeout, unit)`: nếu chưa hoàn tất khi hết hạn, hoàn tất chính `CompletableFuture` đó bất thường bằng `TimeoutException`; các dependent stage xử lý thành công có thể bị bỏ qua.
- `completeOnTimeout(value, timeout, unit)`: nếu chưa hoàn tất khi hết hạn, hoàn tất chính future bằng **giá trị dự phòng**, do đó downstream có thể chạy bình thường.

Các phương thức này trả về future được gọi và **thay đổi trạng thái hoàn tất của chính nó**; không phải luôn tạo một dependent stage mới độc lập. Ví dụ nếu gọi `source.orTimeout(...)`, timeout có thể tác động tới mọi nhánh đang dùng cùng đối tượng `source`. Hãy chú ý khi một future được chia sẻ rộng rãi.

Timeout của future **không tự dừng** tác vụ nền hay hoàn tác side effect. Luồng tính toán có thể tiếp tục sau khi future đã hoàn tất do timeout; một lần `complete(...)` muộn hơn có thể không thay đổi kết quả đã được xác định. Với giao tiếp mạng, cần timeout ở client/dependency và cơ chế hủy/đối chiếu riêng nếu nghiệp vụ yêu cầu.

`get(timeout, unit)` có semantics khác: nó giới hạn **thời gian luồng gọi chờ**, không mặc nhiên hoàn tất `CompletableFuture` được chờ bằng lỗi timeout. Nhầm hai dạng timeout có thể khiến các nhánh dependent bị ảnh hưởng ngoài dự kiến.

## 16. Exception trong callback async và lựa chọn executor

Các phương thức có hậu tố `Async` như `thenApplyAsync` hoặc `thenComposeAsync` có thể thực thi callback trên executor khác; nếu không truyền executor tường minh, chúng sử dụng chính sách executor mặc định của API. Tuy nhiên, **quy tắc hoàn tất bất thường vẫn như nhau**: callback cần giá trị thành công không chạy nếu upstream đã lỗi; callback được chạy mà ném lỗi sẽ làm stage mới thất bại.

Ví dụ:

```java
CompletableFuture<String> result = fetchAsync()
        .thenApplyAsync(this::parse, executor)
        .thenApply(this::format)
        .exceptionally(ex -> fallbackText(ex));
```

Đây là mảnh code trong class có `executor` và các hàm ứng dụng. Nếu `parse` ném lỗi trong worker, `format` không được gọi, rồi `exceptionally` có thể tạo fallback. Lỗi không tự unwind đến `catch` bao quanh câu tạo pipeline đã kết thúc trước đó.

**Lỗi lập lịch cũng đáng chú ý:** nếu executor từ chối tác vụ (ví dụ đã `shutdown()`), cơ chế thực thi callback async có thể dẫn đến exceptional completion liên quan `RejectedExecutionException`. Tùy đường gọi và implementation, những lỗi xảy ra ngay lúc xây/sắp lịch stage có thể bộc lộ khác nhau. Phải quan sát cả lỗi đồng bộ khi dựng pipeline và trạng thái lỗi của future kết quả, thay vì tin rằng mọi thất bại đều chỉ xảy ra trong callback.

Callback không có hậu tố `Async` cũng **không đảm bảo chạy trên thread main**. Nếu nguồn đã hoàn tất trước khi đăng ký, callback có thể chạy ngay trong thread đăng ký; nếu nguồn hoàn tất về sau, một thread thực hiện completion có thể chạy callback. Không dùng `ThreadLocal` hoặc giả định MDC/tracing context sẽ tự chuyển qua mọi stage; cần cơ chế truyền ngữ cảnh khi có yêu cầu.

## 17. Chọn đúng điểm đặt handler lỗi

Vị trí của `exceptionally` hoặc `handle` trong chuỗi làm thay đổi những lỗi nào nó bắt được.

### Handler ở giữa

```java
CompletableFuture<Integer> result =
        source.thenApply(this::parseNumber)
              .exceptionally(ex -> 0)
              .thenApply(this::invert);
```

Đây là mảnh trong class có `source` và các hàm `parseNumber`, `invert`. Handler ở giữa xử lý lỗi xảy ra **trước nó** và trả `0`. Nhưng `invert(0)` có thể ném lỗi (ví dụ chia cho 0); lỗi này nằm **sau handler**, nên handler phía trước **không bắt** được. Stage cuối có thể thất bại.

### Handler ở cuối

```java
CompletableFuture<Integer> result =
        source.thenApply(this::parseNumber)
              .thenApply(this::invert)
              .exceptionally(ex -> 0);
```

Handler ở cuối nhận thất bại từ bất kỳ stage nào nằm trước trên **đường dependency này**, gồm `parseNumber` và `invert`. Nhưng nó cũng có nguy cơ gom các lỗi rất khác nhau thành một fallback duy nhất. Nếu lỗi parse do dữ liệu người dùng sai, còn lỗi invert do bug lập trình, chính sách phục hồi có thể cần khác nhau.

### Một handler cho nhánh không đồng nghĩa handler cho mọi nhánh

```java
CompletableFuture<Integer> a = source.thenApply(this::a);
CompletableFuture<Integer> b = source.thenApply(this::b);
CompletableFuture<Integer> safeA = a.exceptionally(ex -> -1);
```

Mảnh code này có các hàm phù hợp đã định nghĩa. `safeA` chỉ phục hồi nhánh `a`, không tự sửa `b`. Nếu cần quan sát toàn bộ failure fan-out, giữ handle từng nhánh hoặc dùng cơ chế tập hợp trạng thái.

## 18. Lỗi mới có thể thay thế lỗi cũ qua stage xử lý

Các phương thức handler có callback và callback có thể tự thất bại:

- `exceptionally(fn)`: nguồn lỗi E, nhưng `fn` ném F → stage mới thất bại vì F; nên giữ thông tin E qua `cause` khi phù hợp.
- `handle((v,e) -> ...)`: callback ném F → stage mới thất bại vì F, kể cả nếu nguồn thành công hoặc nguồn lỗi E.
- `whenComplete((v,e) -> ...)`: mục tiêu là giữ kết quả nguồn; nếu nguồn đã lỗi và callback cũng lỗi, exception nguồn được ưu tiên theo hợp đồng của phương thức.
- `thenApply(fn)`: nguồn thành công, `fn` ném F → stage mới lỗi F.
- `thenCompose(fn)`: nguồn thành công, callback ném F hoặc future con thất bại F → stage mới lỗi theo failure đó.

Ví dụ cần bảo toàn nguyên nhân:

```java
CompletableFuture<Integer> converted = source.exceptionally(ex -> {
    throw new IllegalStateException("Conversion fallback failed", ex);
});
```

Đây là mảnh code, với `source` là `CompletableFuture<Integer>`. Việc truyền `ex` làm cause giúp giữ lại bối cảnh. Tuy nhiên `ex` có thể là `CompletionException` wrapper; caller cần xem cause chain theo nhu cầu.

Không viết mã tự nhận mọi `RuntimeException` là lỗi tạm thời. Một bug như `NullPointerException` trong handler thường cần được phát hiện, cảnh báo và sửa, thay vì retry một cách mù quáng.

## 19. Khi cần thu thập tất cả lỗi, `allOf` chưa đủ

Giả sử chạy song song ba việc tải dữ liệu. Nếu chỉ viết:

```java
CompletableFuture<Void> all =
        CompletableFuture.allOf(loadA(), loadB(), loadC());
```

thì future `all` có thể báo rằng ít nhất một tác vụ lỗi, nhưng không tự cung cấp **danh sách đầy đủ các lỗi** và không cung cấp tất cả giá trị thành công. Nếu yêu cầu audit từng tác vụ, nên giữ các future con và chuyển từng completion thành kết quả cấu trúc.

Ví dụ cấu trúc (độc lập về ý tưởng, cần định nghĩa `Result<T>` cho ứng dụng):

```java
CompletableFuture<Result<String>> observedA = loadA()
        .handle((value, error) ->
                error == null ? Result.success(value) : Result.failure(error));

CompletableFuture<Result<String>> observedB = loadB()
        .handle((value, error) ->
                error == null ? Result.success(value) : Result.failure(error));
```

Đây là **mảnh thiết kế**, không phải chương trình độc lập; `Result.success` và `Result.failure` là API do ứng dụng chọn. Vì từng `handle` chuyển completion thành giá trị `Result` bình thường, có thể dùng `allOf(observedA, observedB)` và sau đó lấy từng `Result`. Nếu một handler tự ném exception, future tương ứng vẫn có thể thất bại, vì vậy cần thiết kế đường quan sát đáng tin cậy.

Không được cho rằng `allOf` tự dừng các task sibling khi một task lỗi; nếu tác vụ có side effect, phải có cơ chế cancellation, transaction và idempotency riêng.

## 20. Lan truyền lỗi không có nghĩa tự động rollback

Một pipeline có thể gồm:

```java
CompletableFuture<Void> job = updateDatabaseAsync()
        .thenCompose(ignored -> sendNotificationAsync())
        .thenRun(() -> markFinished());
```

Đây là mảnh code với ba phương thức ứng dụng đã định nghĩa. Nếu `updateDatabaseAsync` đã commit rồi stage `sendNotificationAsync` thất bại, `thenRun(markFinished)` bị bỏ qua và `job` lỗi. Nhưng database **đã commit**, và thông báo có thể đã gửi được nhưng mất ACK.

Vì vậy:

- Exceptional completion chỉ mô tả kết quả **pipeline**, không hủy tác dụng phụ đã xảy ra.
- Caller không nên retry toàn bộ pipeline khi chưa biết phần nào đã commit.
- Nếu có thể, ghi kết quả nghiệp vụ và ý định gửi sự kiện trong cùng transaction DB bằng outbox; dùng idempotency key để chống gửi/ghi lặp.
- Khi pipeline có nhiều nguồn, lưu request ID, stage ID, thời điểm thành công cuối và trạng thái chưa chắc chắn.
- Đừng dùng `exceptionally(ex -> null)` như cách biến mọi thất bại thành “thành công rỗng” nếu caller cần biết chưa hoàn thành nghiệp vụ.

Với một stage phục hồi bằng fallback, hãy xác định rõ: hệ thống đã thành công theo **hợp đồng nào**? “Đọc cache cũ” có thể là kết quả degraded chấp nhận được, còn “chuyển tiền rồi bỏ qua lỗi thông báo” cần bảo đảm dữ liệu và các bước còn lại được theo dõi.

## 21. Logging, tracing và quan sát lỗi đúng cách

Một pipeline dài có thể tạo ra nhiều exception wrapper; nếu mỗi stage ghi stack trace rồi ném tiếp, một lỗi gốc dễ tạo rất nhiều log trùng. Nên chọn ranh giới quan sát rõ:

1. Gắn correlation ID/request ID theo luồng nghiệp vụ, không phụ thuộc duy nhất vào tên thread.
2. Ghi nguyên nhân và bối cảnh stage: nguồn dữ liệu, thao tác, timeout, số lần retry, trạng thái upstream.
3. Có một nơi chịu trách nhiệm ghi failure cuối cùng của pipeline; nếu cần metric tại nhiều stage thì tránh spam log trùng.
4. Giữ `Throwable#getCause()` khi chuyển loại lỗi, và không tùy tiện xóa stack trace.
5. Không ghi token, password, payload riêng tư hoặc connection string nhạy cảm.
6. Nếu có fallback, phân biệt *normal completion with degraded result* với thành công đầy đủ để monitoring không bị mù.

Ví dụ:

```java
return callRemoteAsync()
        .whenComplete((value, error) -> {
            if (error != null) {
                metrics.failedOperation("remote-call");
            }
        });
```

Đây là mảnh trong một phương thức với `callRemoteAsync`, `metrics` do ứng dụng định nghĩa. Đường ghi metric phải đủ tin cậy; nếu nó ném exception khi upstream thành công, stage trả về có thể trở thành thất bại mới.

## 22. Kiểm thử lan truyền qua stage

Một bộ test tốt không chỉ `assertThrows` ở cuối mà còn xác minh **callback nào đã chạy, kết quả stage gốc có bị thay đổi không, và cause chain nào được giữ**.

| Kịch bản | Kỳ vọng |
| --- | --- |
| Stage nguồn thành công | Callback `thenApply` được gọi, dependent có giá trị |
| Callback `thenApply` ném exception E | Dependent hoàn tất bất thường |
| Stage trước lỗi E, stage sau là `thenApply` | Callback stage sau **không chạy**, dependent exceptional |
| Đặt `exceptionally` sau stage lỗi | Callback lỗi được gọi, trả fallback bình thường |
| Đặt `exceptionally` trước stage lỗi mới | Handler cũ không bắt được lỗi mới phía sau |
| `handle` nguồn thành công/lỗi | Nhận đúng `value` hoặc `error` và có thể tạo stage bình thường |
| `whenComplete` nguồn lỗi | Chạy callback quan sát nhưng stage trả về vẫn lỗi |
| `thenCompose` future con lỗi | Stage kết quả lỗi dù nguồn ngoài thành công |
| `thenCombine` một nguồn lỗi | Không gọi callback kết hợp thành công |
| `allOf` một nguồn lỗi | Future tổng hợp lỗi, future độc lập không bị tự cancel |
| `anyOf` future đầu hoàn tất bất thường | Kết quả tổng hợp có thể là exceptional |
| `CompletableFuture.cancel` | Các dependent phản ứng với exceptional completion; không suy ra upstream bị ngắt |
| `get` ở caller bị interrupt | `InterruptedException` thuộc caller; future nguồn không tự lỗi vì việc chờ bị ngắt |
| `orTimeout` trước khi nguồn hoàn tất | Future bị timeout và dependent thành công có thể bị bỏ qua |

Dùng `completedFuture`, `failedFuture` và `AtomicInteger` hoặc `CountDownLatch` để dựng tình huống chính xác. Không dùng `Thread.sleep` và suy đoán thời điểm callback chạy nếu có thể chờ một điều kiện rõ. Với các test timeout/hủy, chọn giới hạn hợp lý và dọn executor sau khi test để không treo bộ kiểm thử.

Nếu test ngữ cảnh async thực sự, có thể dùng một executor kiểm soát được và kiểm tra thread safety, nhưng **không phụ thuộc vào thứ tự callback** khi hợp đồng không cam kết.

## 23. Những ngộ nhận phổ biến

| Ngộ nhận | Thực tế |
| --- | --- |
| “Một stage lỗi thì mọi callback sau nó vẫn chạy và tự nhận `null`.” | Các callback xử lý thành công như `thenApply` **không được gọi** khi upstream exceptional. |
| “`thenRun` không dùng giá trị nên vẫn chạy khi upstream lỗi.” | `thenRun` vẫn yêu cầu nguồn hoàn tất **bình thường**. |
| “`exceptionally` sửa state của future nguồn.” | Nó tạo **stage mới**; nguồn giữ trạng thái đã có. |
| “`whenComplete` tự phục hồi lỗi.” | Nó chủ yếu quan sát; nếu không có cơ chế khác, lỗi vẫn lan truyền. |
| “`get()` và `join()` trả cùng loại wrapper.” | `get()` dùng `ExecutionException`; `join()` thường dùng `CompletionException` khi lỗi. |
| “`thenCompose` chỉ lỗi khi callback ngoài ném exception.” | Future con trả về từ callback cũng có thể thất bại về sau. |
| “Lỗi một nhánh làm mọi nhánh chị em tự hủy.” | Không có sự lan truyền hủy ngược/chéo một cách tổng quát. |
| “`allOf` trả list mọi kết quả và mọi exception.” | Nó trả `CompletableFuture<Void>`, không tự tạo list kết quả/lỗi đầy đủ. |
| “`anyOf` chờ thành công đầu tiên.” | Nó theo **future hoàn tất đầu tiên**, kể cả bất thường. |
| “Future báo timeout thì tác vụ nền chắc chắn dừng.” | Timeout completion và dừng computation/side effect là hai vấn đề khác. |
| “Exception ở worker lan thẳng tới `catch` quanh câu tạo pipeline.” | Error được ghi trong completion; caller phải quan sát future hoặc handler. |
| “Pipeline bị lỗi nên database đã rollback.” | Exceptional completion không tự hoàn tác các tác dụng phụ ngoài future. |

## 24. Checklist thiết kế chuỗi CompletableFuture

1. Vẽ các dependency giữa stage, xác định stage nào cần kết quả thành công để chạy.
2. Phân biệt **lỗi phát sinh từ callback** với **lỗi được truyền từ upstream**.
3. Đặt `exceptionally`/`handle` ở đúng nơi cần phục hồi; tránh fallback làm che lỗi nghiêm trọng.
4. Dùng `whenComplete` để quan sát cả thành công và thất bại, nhưng kiểm soát lỗi từ logging/metric.
5. Với `thenCompose`, theo dõi lỗi future con và chính sách hủy của toàn tác vụ.
6. Khi dùng `allOf` hoặc fan-out, giữ future con nếu cần mọi kết quả hoặc mọi nguyên nhân.
7. Hiểu wrapper `CompletionException`/`ExecutionException`, `CancellationException`, `TimeoutException` và `InterruptedException` của caller.
8. Không giả định callback chạy trên một thread cụ thể; chọn executor, context propagation và thread safety phù hợp.
9. Định nghĩa các trạng thái sau lỗi của side effect: chưa làm, đã commit, đang phục hồi, kết quả chưa rõ.
10. Test đường lỗi của từng stage, callback bị bỏ qua, callback phục hồi và nhánh độc lập bằng tín hiệu đồng bộ rõ ràng.

**Ghi nhớ:** trong `CompletableFuture`, khi một stage thất bại, các stage phụ thuộc cần giá trị thành công thường **được đánh dấu thất bại mà không chạy callback**. Muốn tiếp tục, phải có stage xử lý lỗi như `exceptionally` hoặc `handle` được đặt đúng chỗ; muốn biết nguyên nhân, phải quan sát completion và cause chain. Cơ chế này truyền trạng thái thất bại qua dependency, chứ không tự chuyển stack exception xuyên thread hay rollback công việc đã thực hiện.
