# anyOf() hoàn tất theo một công việc và giới hạn hủy các công việc còn lại

## 1. Mục tiêu: “có kết quả đầu tiên” không có nghĩa “mọi việc khác dừng”

Trong Java 17, `CompletableFuture.anyOf(...)` là công cụ kết hợp nhiều `CompletableFuture`: **future tổng hợp hoàn tất khi một trong các future đầu vào hoàn tất**, nhận kết quả hoặc trạng thái ngoại lệ tương ứng. Nó hữu ích khi muốn lấy phản hồi sớm nhất từ vài nguồn độc lập, chạy các phép tra cứu song song hoặc mô phỏng chiến lược *hedged requests*.

Tuy nhiên, có hai sự kiện rất khác nhau:

1. **Future tổng hợp đã hoàn tất:** caller có thể đọc kết quả đầu tiên, hoặc nhận lỗi của task hoàn tất trước.
2. **Công việc còn lại đã dừng:** worker thread, HTTP request, truy vấn DB hoặc side effect của các task còn lại không còn chạy nữa.

`anyOf()` **chỉ bảo đảm điều thứ nhất**. Nó không tự hủy, ngắt thread hoặc giải phóng kết nối của các công việc chưa thắng. Kể cả khi ta gọi `cancel(true)` trên một `CompletableFuture`, Java không bảo đảm công việc thực tế phía sau future bị ngừng.

**Ví dụ cần hình dung:** ứng dụng gửi yêu cầu đọc dữ liệu tới ba replica. Replica A phản hồi trong 100 ms; B và C còn đang xử lý. `anyOf(A, B, C)` cho phép caller dùng kết quả của A, **nhưng B và C vẫn có thể tiếp tục tiêu thụ CPU, thread, JDBC/HTTP connections và quota dịch vụ**. Nếu các request có side effect, cả ba có thể đã tác động tới hệ thống trước khi nhận kết quả đầu tiên; “chỉ trả một kết quả” không biến chúng thành “chỉ thực hiện một lần”.

Bài này đi từ hợp đồng API, luồng thời gian, ví dụ Java 17 chạy độc lập, cơ chế hủy thực tế và phương án xử lý trong Spring `@Async`.

## 2. Hợp đồng chính xác của CompletableFuture.anyOf()

Khai báo:

```java
public static CompletableFuture<Object> anyOf(
        CompletableFuture<?>... cfs)
```

Giả sử có ba future A, B và C:

```text
A ---- hoàn tất thành công ("A") -------|
                                        |
B ----------- đang chạy ----------------+--> anyOf(A, B, C) = "A"
                                        |
C -------------------- đang chạy -------|

Sau khi anyOf đã hoàn tất:
- Caller có thể tiếp tục với kết quả "A".
- B và C không tự chuyển thành cancelled.
- B và C có thể tiếp tục chạy và gây side effect.
```

Các quy tắc cần nhớ:

- **“Bất kỳ future nào hoàn tất”** bao gồm **hoàn tất thành công, hoàn tất ngoại lệ và hủy**. `anyOf` không mặc định “đợi future thành công đầu tiên”.
- Kết quả có kiểu **`CompletableFuture<Object>`**, do các future nguồn có thể trả các kiểu khác nhau. Không tự ép `Object` thành `String` nếu các đầu vào có kiểu không đồng nhất; dùng kiểu kết quả thống nhất hoặc wrapper/record gắn nhãn nguồn.
- Nếu một đầu vào hoàn tất ngoại lệ trước, future `anyOf` cũng hoàn tất ngoại lệ, thông thường thể hiện qua `CompletionException` khi gọi `join()`. Những đầu vào khác vẫn có thể thành công sau đó.
- Nếu **không truyền future nào**, `anyOf()` trả về một `CompletableFuture<Object>` **chưa hoàn tất**, không phải future hoàn tất với `null`. Gọi `join()` trên nó có thể chờ vô hạn nếu không ai hoàn thành thủ công.
- Nếu danh sách chứa future `null`, API báo `NullPointerException`; xác minh danh sách đầu vào.
- Nếu nhiều future đã hoàn tất hoặc hoàn tất gần như đồng thời, **không dựa vào thứ tự mảng để quyết định chắc chắn ai thắng**. Kết quả cuộc đua phụ thuộc thứ tự completion được quan sát.
- `anyOf` không tự tạo worker thread. Nó **kết hợp các future đã có**; nguồn có thực thi song song hay không phụ thuộc cách tạo các future, executor và các dependency thực tế.

### Phân biệt với các API gần giống

| API | Khi nào future tổng hợp hoàn tất? | Có tự hủy việc còn lại không? |
| --- | --- | --- |
| `anyOf(a, b, ...)` | Một đầu vào bất kỳ hoàn tất (kể cả lỗi) | **Không** |
| `allOf(a, b, ...)` | Tất cả đầu vào hoàn tất; nếu có lỗi sẽ hoàn tất ngoại lệ | **Không** |
| `applyToEither(other, fn)` | Áp dụng hàm cho một kết quả hoàn tất **bình thường** theo hợp đồng CompletionStage; lỗi cạnh tranh cần kiểm thử theo semantics thực tế | **Không** |
| `thenCompose(fn)` | Ghép bước tiếp theo phụ thuộc kết quả một future | **Không** |
| `orTimeout(timeout, unit)` | Hoàn tất ngoại lệ khi tới hạn nếu future được gọi vẫn chưa xong | **Không bảo đảm dừng computation phía sau** |
| `completeOnTimeout(value, timeout, unit)` | Gán giá trị dự phòng khi đến hạn nếu chưa xong | **Không bảo đảm dừng computation phía sau** |

Đừng xem `applyToEither` là sự thay thế không cần suy nghĩ cho bài toán **“kết quả thành công đầu tiên, bất kể các nhánh lỗi trước đó”**. Nếu nghiệp vụ cần bỏ qua lỗi của từng replica và chỉ thất bại khi **tất cả** replica thất bại, hãy viết một coordinator rõ ràng với chính sách kết quả/ngoại lệ cụ thể.

## 3. Vì sao future hoàn tất không làm worker bên dưới ngừng lại?

Một `CompletableFuture<T>` trước hết đại diện cho **trạng thái của kết quả trong tương lai**: chưa hoàn thành, hoàn thành với giá trị, hoàn thành ngoại lệ hoặc bị hủy. Nó không nhất thiết là một handle sở hữu khả năng điều khiển thread đang chạy.

Ví dụ:

```java
CompletableFuture<String> slow =
        CompletableFuture.supplyAsync(() -> callSlowService(), executor);

CompletableFuture<String> fast =
        CompletableFuture.supplyAsync(() -> callFastService(), executor);

CompletableFuture<Object> first =
        CompletableFuture.anyOf(fast, slow);

Object result = first.join();
```

Đây là đoạn minh họa trong phương thức có sẵn `executor` cùng các hàm nghiệp vụ `callSlowService` và `callFastService`; không phải chương trình độc lập.

Sau `first.join()`:

- Chỉ có **`first` đã hoàn tất** theo điều kiện “một đầu vào đã xong”; `slow.isDone()` có thể vẫn bằng `false`.
- Executor có thể vẫn đang giữ worker của `slow`.
- HTTP client có thể vẫn duy trì request tới remote host.
- JDBC query của nhánh chậm có thể vẫn đang chạy.
- Future chậm có thể hoàn thành sau và cập nhật cache, ghi log, gửi event hoặc tạo tác động ngoài ý muốn.
- `first` hoàn tất **không gọi** `slow.cancel(...)` hay `fast.cancel(...)` thay chúng ta.

Có ba tầng cần phân biệt:

```text
TẦNG 1: Result/Future state
   isDone(), complete(), completeExceptionally(), cancel()
          |
          v
TẦNG 2: Execution task
   Runnable/Callable, worker thread, CompletableFuture supplier
          |
          v
TẦNG 3: External work
   JDBC query, HTTP request, file I/O, remote side effect

Chuyển trạng thái ở tầng 1
  KHÔNG tự chứng minh tầng 2 và tầng 3 đã dừng.
```

Vì vậy chính sách “lấy kết quả đầu tiên và bỏ qua các nhánh còn lại” phải là **quyết định riêng**: có chấp nhận chúng chạy tiếp không, có yêu cầu dừng hợp tác không, có handle cho phép hủy thật không, và có idempotency cho tác dụng phụ không?

## 4. Ví dụ Java 17 chạy độc lập: chứng minh giới hạn hủy

Ví dụ dưới có ba thí nghiệm độc lập trong cùng một chương trình:

1. Một nhánh chậm **đang chạy trên executor**, nhánh nhanh được hoàn tất có kiểm soát. `anyOf` trả về kết quả nhanh, không tự hủy nhánh chậm.
2. Gọi `cancel(true)` trên `CompletableFuture` của nhánh chậm trong khi supplier vẫn chờ. Future chuyển thành **cancelled**, nhưng computation vẫn có thể tiếp tục sau khi được cho phép.
3. Một nhánh hoàn tất **ngoại lệ** trước; `anyOf` hoàn tất theo lỗi đó, không đợi nhánh khác thành công và cũng không hủy nhánh khác.

Dùng `CountDownLatch` để tránh phụ thuộc vào timing của `Thread.sleep`. Tạo tệp **`AnyOfCancellationDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public final class AnyOfCancellationDemo {
    private static void awaitOrFail(CountDownLatch latch, String stage) {
        try {
            if (!latch.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Timeout at " + stage);
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted at " + stage, ex);
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch slowStarted = new CountDownLatch(1);
        CountDownLatch releaseSlow = new CountDownLatch(1);
        CountDownLatch slowFinished = new CountDownLatch(1);
        AtomicBoolean sideEffect = new AtomicBoolean(false);

        try {
            CompletableFuture<String> slow =
                    CompletableFuture.supplyAsync(() -> {
                        slowStarted.countDown();
                        try {
                            // Supplier thật vẫn đang giữ một worker.
                            awaitOrFail(releaseSlow, "releaseSlow");
                            sideEffect.set(true);
                            return "SLOW";
                        } finally {
                            slowFinished.countDown();
                        }
                    }, pool);

            // Chắc chắn supplier chậm đã vào worker trước khi tiếp tục.
            awaitOrFail(slowStarted, "slowStarted");

            // Điều khiển hoàn tất một future khác: không phụ thuộc CPU.
            CompletableFuture<String> quick = new CompletableFuture<>();
            CompletableFuture<Object> first =
                    CompletableFuture.anyOf(quick, slow);

            quick.complete("QUICK");
            System.out.println("winner=" + first.join());
            System.out.println("slowDoneAtWinner=" + slow.isDone());
            System.out.println(
                    "slowAutoCancelled=" + slow.isCancelled());

            // cancel() thay đổi trạng thái CompletableFuture, không bảo đảm
            // ngắt worker đang chạy supplyAsync.
            boolean cancelled = slow.cancel(true);
            System.out.println("manualCancel=" + cancelled);
            System.out.println("slowCancelledNow=" + slow.isCancelled());

            // Dù future đã cancelled, supplier vẫn còn đợi releaseSlow.
            releaseSlow.countDown();
            awaitOrFail(slowFinished, "slowFinished");
            System.out.println(
                    "sideEffectAfterCancel=" + sideEffect.get());

            // Một future hoàn tất lỗi trước: anyOf đi theo lỗi đó.
            CompletableFuture<String> failed = new CompletableFuture<>();
            CompletableFuture<String> other = new CompletableFuture<>();
            CompletableFuture<Object> firstError =
                    CompletableFuture.anyOf(failed, other);

            failed.completeExceptionally(
                    new IllegalStateException("remote failed"));
            try {
                firstError.join();
            } catch (CompletionException ex) {
                System.out.println(
                        "firstError=" + ex.getCause().getClass().getSimpleName());
            }

            System.out.println(
                    "otherAutoCancelled=" + other.isCancelled());
            other.complete("RECOVERED");
            System.out.println("otherResult=" + other.join());

            // Mảng rỗng KHÔNG đồng nghĩa kết quả null đã hoàn tất.
            CompletableFuture<Object> empty = CompletableFuture.anyOf();
            System.out.println("emptyIsDone=" + empty.isDone());
        } finally {
            // Dọn dẹp kể cả khi một assertion hoặc bước khác thất bại.
            releaseSlow.countDown();
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Pool did not terminate");
            }
        }
    }
}
```

Chạy bằng **JDK 17+** tại thư mục chứa file:

```bash
javac AnyOfCancellationDemo.java
java AnyOfCancellationDemo
```

**Standard output trong đường chạy thành công** (không tính thông báo của JVM khi máy bị gián đoạn bất thường):

```text
winner=QUICK
slowDoneAtWinner=false
slowAutoCancelled=false
manualCancel=true
slowCancelledNow=true
sideEffectAfterCancel=true
firstError=IllegalStateException
otherAutoCancelled=false
otherResult=RECOVERED
emptyIsDone=false
```

### Phân tích từng phép đo

- `slowStarted` xác nhận supplier đã chạy trên worker và đang đợi `releaseSlow`. Do main chưa mở latch, `slow.isDone()` vẫn bằng `false`.
- `quick.complete("QUICK")` là điểm hoàn tất đầu tiên có kiểm soát, khiến `first.join()` trả `QUICK`. Không có logic hủy nhánh chậm nào bên trong `anyOf`.
- `slow.cancel(true)` chuyển **trạng thái của CompletableFuture** sang cancelled, nên `slowCancelledNow=true`. Theo Java 17 Javadoc, tham số `mayInterruptIfRunning` **không có tác dụng trong triển khai CompletableFuture** vì nó không dùng interrupt để điều khiển processing.
- Khi main mở `releaseSlow`, supplier vẫn đang chạy, thực hiện `sideEffect.set(true)` rồi kết thúc. Future `slow` **vẫn là cancelled**; completion result thật `"SLOW"` không thay thế trạng thái hủy đã thiết lập.
- `failed.completeExceptionally(...)` hoàn tất một nhánh trước. `firstError.join()` ném `CompletionException` với cause là `IllegalStateException`. Future `other` không tự hủy và vẫn có thể hoàn tất với `RECOVERED`.
- `anyOf()` không đối số trả một future chưa được hoàn tất: `emptyIsDone=false`. Không gọi `empty.join()` trong demo vì nó có thể chờ vô hạn.

**Giới hạn của thí nghiệm:** `quick` ở đây được hoàn tất thủ công để thứ tự sự kiện có thể chứng minh. Trong ứng dụng thật, cả fast và slow có thể là các tác vụ của executor hoặc các request HTTP chạy bất đồng bộ; khi đó nhánh thắng phụ thuộc vào thứ tự hoàn tất thực tế. Thí nghiệm vẫn chứng minh được rằng kết quả tổng hợp và vòng đời worker **không phải cùng một thứ**.

## 5. cancel(true) trên CompletableFuture thực sự có ý nghĩa gì?

Javadoc Java 17 nêu rõ: với `CompletableFuture.cancel(boolean mayInterruptIfRunning)`, việc hủy có hiệu lực như một dạng **hoàn tất ngoại lệ** với `CancellationException`. Tham số `mayInterruptIfRunning` không khiến CompletableFuture tự gửi interrupt tới thread đang tính toán.

| Hành động | Điều có thể xác nhận | Điều **không** được bảo đảm |
| --- | --- | --- |
| `anyOf(f1, f2)` hoàn tất | Một đầu vào đã hoàn tất và future tổng hợp có kết quả/lỗi | f2 dừng, bị hủy, giải phóng connection |
| `combined.cancel(true)` | Future tổng hợp chuyển sang trạng thái cancelled nếu chưa hoàn tất | Tất cả đầu vào bị hủy hoặc mọi task nguồn bị dừng |
| `f2.cancel(true)` | f2 có thể hoàn tất với `CancellationException`; `isCancelled()` phản ánh trạng thái | Supplier do `supplyAsync` khởi chạy sẽ bị interrupt/dừng |
| `future.isDone()` | Future không còn ở trạng thái chưa hoàn tất | Remote operation đã thực sự ngừng |
| `future.isCompletedExceptionally()` | Future thất bại/cancel/hoàn tất ngoại lệ | Worker chưa từng gây side effect |
| `Future<?> handle.cancel(true)` từ `ExecutorService.submit` | **Yêu cầu** hủy task, có thể interrupt worker nếu đang chạy | Task chắc chắn dừng ngay; I/O bắt buộc bị hủy |

### Hủy “future tổng hợp” cũng không tự hủy “nguồn”

```java
CompletableFuture<String> a = new CompletableFuture<>();
CompletableFuture<String> b = new CompletableFuture<>();
CompletableFuture<Object> combined = CompletableFuture.anyOf(a, b);

combined.cancel(true);

System.out.println("aggregateCancelled=" + combined.isCancelled());
System.out.println("aCancelled=" + a.isCancelled());
System.out.println("bCancelled=" + b.isCancelled());
```

Đây là **snippet độc lập trong method** (cần import `CompletableFuture`). Với hai đầu vào chưa hoàn tất, ba dòng kết quả tương ứng là `true`, `false`, `false`. Việc chuyển trạng thái của **aggregate** không tự động truyền hủy ngược về hai đầu vào.

### Hủy nhánh thua không đồng nghĩa việc thực thi dừng

Giả sử A đã thắng. Ta tự gọi `b.cancel(true)`. Nếu future B được hoàn tất bởi một supplier đang chạy, biến trạng thái B có thể chuyển sang cancelled, nhưng supplier, DB query hoặc HTTP call vẫn tiếp tục. Supplier sau đó có thể gọi `complete("B")` hoặc trả kết quả, nhưng kết quả ấy không thể thay thế trạng thái cancelled đã có; tác dụng phụ thực tế có thể vẫn xảy ra.

**Hệ quả:** một chương trình in `b.isCancelled() == true` **không chứng minh** nó đã tiết kiệm thread, kết nối hoặc chi phí remote request. Phải đo thread/task/HTTP client hoặc cơ chế cancellation của dependency.

## 6. Khi thật sự muốn dừng công việc: cancellation phải hợp tác

Việc dừng thực thi phụ thuộc vào **loại work** và **handle kiểm soát nó**.

### 6.1. Runnable/Callable với Future của ExecutorService

Nếu tự sở hữu task từ `ExecutorService.submit(Callable)`, kết quả nhận được là `Future<T>` có quan hệ trực tiếp hơn với task của executor. Gọi `cancel(true)` có thể cố ngắt worker thread nếu task đang chạy.

```java
Future<?> handle = executor.submit(() -> {
    while (!Thread.currentThread().isInterrupted()) {
        performSmallChunk();  // Mỗi phần việc nên hữu hạn và kiểm tra hủy.
    }
});

// Khi không cần task nữa:
handle.cancel(true);
```

Đây là snippet minh họa với `executor`, `performSmallChunk()` và import có sẵn; không phải chương trình độc lập. Nếu mã đã bị chặn trong phương thức có hỗ trợ interrupt, `InterruptedException` cần được xử lý đúng và thường nên khôi phục cờ interrupt khi không thể ném tiếp:

```java
try {
    blockingOperation();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
}
```

Lưu ý: không phải mọi API I/O hoặc native library đều phản ứng với interrupt giống nhau. Ngay cả `Future.cancel(true)` cũng là **yêu cầu hủy** chứ không phải giao kèo “mọi side effect bị rollback”.

### 6.2. Cờ dừng hợp tác

Một `AtomicBoolean stopRequested` hoặc cancellation token có thể được task kiểm tra giữa các bước:

```java
AtomicBoolean stopRequested = new AtomicBoolean(false);

CompletableFuture<String> task =
        CompletableFuture.supplyAsync(() -> {
            while (!stopRequested.get()) {
                doBoundedStep();
            }
            return "stopped";
        }, executor);

// Khi đã có kết quả cần dùng từ nhánh khác:
stopRequested.set(true);
```

Đây là snippet minh họa; `doBoundedStep()` và `executor` cần định nghĩa. Dùng cờ riêng theo task/operation; không dùng một cờ dừng toàn cục vô tình hủy công việc của request khác. Nếu một bước bên trong bị kẹt trong HTTP/JDBC không có timeout, kiểm tra cờ ở vòng sau cũng không giúp dừng ngay: cần deadline và cancellation tại client tương ứng.

**Quy tắc:** cancel token chỉ hữu ích nếu computation **thường xuyên quan sát token**, từng bước đủ ngắn, tài nguyên được đóng đúng cách và không tiếp tục gây side effect sau khi đã nhận tín hiệu dừng.

### 6.3. HTTP request, JDBC và tác vụ remote

- Với HTTP client bất đồng bộ, xem API hủy request/đóng response/connection hoặc cancel subscription theo client cụ thể. Không chỉ hủy `CompletableFuture` rồi tự nhận đã ngắt kết nối.
- Với JDBC, cần transaction/query timeout, cancellation API của driver (ví dụ `Statement.cancel()` nếu được hỗ trợ) và quản lý transaction/connection đúng vòng đời. Không giả định Java interrupt tự rollback câu SQL phía database.
- Với WebClient/Reactor, cancellation của `Mono`/`Flux` được đưa qua lifecycle subscription; nếu sử dụng `toFuture()`, phải xác minh semantics của phiên bản adapter và client, không suy rộng từ `CompletableFuture.cancel` thuần.
- Với lời gọi gRPC, message listener hoặc workflow engine, sử dụng API cancellation riêng của chúng. Một task đã đến server bên kia vẫn có thể hoàn thành dù caller không đợi kết quả nữa.
- Với dữ liệu có side effect, một thao tác đã commit **không thể bị “uncommit”** chỉ vì future bị hủy. Cần idempotency, transaction đúng phạm vi hoặc compensating action.

## 7. Khi chỉ cần kết quả nhanh nhất, có nên hủy các nhánh khác?

Không có đáp án duy nhất; hãy dựa trên chi phí và quy tắc nghiệp vụ.

**Có thể cho chạy tiếp** nếu mỗi nhánh là công việc nhẹ, sẽ hoàn tất gần như ngay, tiếp tục chạy không gây side effect nguy hiểm, và chi phí hủy còn cao hơn chi phí thực hiện. Ví dụ các phép tính ngắn dùng CPU có giới hạn, không cần cố gắng ngắt giữa chừng.

**Nên tìm cách dừng/cancel** nếu nhánh thua là HTTP request tốn quota, truy vấn DB dài hoặc tác vụ đòi nhiều worker/connection. Dùng API cancellation thật của client và đặt timeout; **đo** xem tài nguyên có được trả lại hay không.

**Không nên chạy đua nhiều bản sao** đối với thao tác ghi dữ liệu không idempotent. Ví dụ cùng gửi yêu cầu “thu tiền” tới hai endpoint rồi lấy phản hồi nhanh nhất có thể khiến **hai giao dịch được thực hiện** dù chỉ một future được hiển thị. Kết quả “first wins” không bảo vệ exactly-once.

Một kế hoạch thực tế:

1. Xác định mỗi nhánh có read-only/idempotent hay có side effect.
2. Giới hạn số bản sao được phép chạy (bulkhead, executor, connection pool).
3. Đặt **deadline** cho cả cuộc đua và timeout riêng từng dependency.
4. Khi có kết quả phù hợp, báo hiệu dừng cho nhánh thua qua **cơ chế riêng** (cờ hợp tác, cancellation handle, client cancellation).
5. Đợi/quan sát việc cleanup nếu nghiệp vụ đòi hỏi, nhưng không làm request đồng bộ chờ vô hạn chỉ để “hủy cho xong”.
6. Log và đo cancellation thực sự, task in-flight, active connections và chi phí request thừa.

## 8. anyOf() lấy completion đầu tiên, không nhất thiết lấy thành công đầu tiên

Giả sử có ba nguồn:

```text
t=50ms   A hoàn tất ngoại lệ: TimeoutException
t=90ms   B hoàn tất thành công: "DATA-B"
t=120ms  C hoàn tất thành công: "DATA-C"
```

`anyOf(A, B, C)` hoàn tất ngoại lệ từ A ở 50 ms. Nó **không chờ** B tới 90 ms và cũng không tự retry. Đây là hành vi đúng theo contract, nhưng có thể **không đáp ứng nghiệp vụ** “chỉ cần một replica trả thành công”.

Nếu muốn “thành công đầu tiên; chỉ thất bại khi tất cả cùng lỗi”, cần một coordinator khác. Ví dụ utility Java 17 tổng quát:

```java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicInteger;

public static <T> CompletableFuture<T> firstSuccessful(
        List<? extends CompletableFuture<? extends T>> inputs) {

    if (inputs.isEmpty()) {
        return CompletableFuture.failedFuture(
                new IllegalArgumentException("No candidate futures"));
    }

    CompletableFuture<T> answer = new CompletableFuture<>();
    AtomicInteger failuresRemaining = new AtomicInteger(inputs.size());

    for (CompletableFuture<? extends T> candidate : inputs) {
        candidate.whenComplete((value, error) -> {
            if (error == null) {
                answer.complete(value); // Một thành công đủ để thắng.
            } else if (failuresRemaining.decrementAndGet() == 0) {
                // Đến đây mọi candidate đều đã thất bại.
                answer.completeExceptionally(error);
            }
        });
    }
    return answer;
}
```

**Đây là một phương thức utility**, cần đặt vào class và import đầy đủ; không phải chương trình chạy độc lập. Code dùng callback `whenComplete`; tương tự `anyOf`, nó **không tự hủy những nguồn còn lại**. Nếu tất cả thất bại, ví dụ chỉ giữ lỗi của callback thất bại cuối cùng; hệ thống sản xuất có thể cần gom nguyên nhân, mã lỗi, deadline và thông tin từng replica để debug. Nếu nhiều thành công xảy ra cùng lúc, future kết quả chỉ hoàn tất thành công một lần; caller không nên suy diễn chính xác tác vụ vật lý nào chạm đích trước chỉ dựa vào thứ tự callback.

**Quan trọng:** phương thức này khác `anyOf` về **ngữ nghĩa chọn thành công**, không giải quyết hủy công việc. Cơ chế cleanup/stop task thua vẫn là vấn đề riêng.

### Gắn danh tính nguồn để tránh mất ngữ cảnh

Vì `anyOf` trả `Object`, nhiều service có cùng kiểu kết quả sẽ khó biết “ai thắng”. Có thể chuẩn hóa kết quả thành record:

```java
record Result(String source, String payload) {}

CompletableFuture<Result> a =
        sourceAFuture.thenApply(value -> new Result("A", value));
CompletableFuture<Result> b =
        sourceBFuture.thenApply(value -> new Result("B", value));

CompletableFuture<Object> raced = CompletableFuture.anyOf(a, b);
Result winner = (Result) raced.join();
```

Đây là snippet với `sourceAFuture`, `sourceBFuture` đã được tạo và đều trả `String`. Ép kiểu `Result` chỉ an toàn vì **cả hai input** được chuẩn hóa thành cùng một kiểu; nếu có thêm future trả kiểu khác vào `anyOf`, phải điều chỉnh mô hình.

## 9. Timeout và cancellation: hai vòng đời khác nhau

`CompletableFuture.orTimeout(...)` và `completeOnTimeout(...)` thường bị hiểu sai khi kết hợp với `anyOf`.

```java
CompletableFuture<Object> first =
        CompletableFuture.anyOf(remoteA, remoteB)
                .orTimeout(800, TimeUnit.MILLISECONDS);
```

Đây là snippet trong môi trường có hai future `remoteA`, `remoteB` và import `TimeUnit`. Nếu 800 ms trôi qua trước khi bất kỳ nhánh nào xong, future tổng hợp sẽ hoàn tất ngoại lệ với timeout theo API. **Điều đó không tự dừng** task nguồn, HTTP call hoặc DB query. Cũng cần lưu ý `orTimeout` tác động lên **chính future được gọi** (ở đây là aggregate), không phải tự tạo một tầng cancellation riêng bao trùm mọi nguồn.

Tương tự, `completeOnTimeout(defaultValue, ...)` có thể trả giá trị dự phòng khi đến hạn nhưng không tự giải phóng các task nền. Không đặt timeout ở ba lớp khác nhau và mặc định kết quả chỉ tiêu tốn đúng một khoảng timeout: thời gian xếp hàng executor, đợi connection, HTTP connect, response và retry có thể cộng dồn.

**Thiết kế deadline hợp lý:**

- Deadline của toàn request (ví dụ 1 giây).
- Timeout/giới hạn acquire của pool và client.
- Timeout của từng cuộc gọi remote.
- Điều kiện dừng cho các nhánh thua.
- Hạn mức concurrency và số lần retry.
- Quy trình trả connection/permit/transaction khi task lỗi hoặc bị hủy.

Nếu một nhánh không hỗ trợ hủy, **đừng quảng bá cancellation như một bảo đảm**; có thể chọn trả kết quả sớm rồi theo dõi nhánh ấy để cleanup khi thực sự xong.

## 10. Ví dụ tích hợp Spring @Async: đúng executor, đúng proxy, đúng giới hạn

Trong Spring Boot/Spring Framework, `@Async` có thể trả `CompletableFuture<T>`. Spring proxy submit phần thân phương thức tới executor; caller kết hợp các future bằng `anyOf`.

Đoạn cấu hình sau là **code tích hợp Spring**, không phải chương trình `javac` chỉ có JDK:

**`AsyncConfig.java`:**

```java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncConfig {

    @Bean("lookupExecutor")
    public ThreadPoolTaskExecutor lookupExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("lookup-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}
```

**`LookupService.java`:**

```java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class LookupService {
    @Async("lookupExecutor")
    public CompletableFuture<String> lookupPrimary(String key) {
        // Ví dụ rút gọn: thay bằng I/O thật với timeout/cancellation.
        return CompletableFuture.completedFuture("primary:" + key);
    }

    @Async("lookupExecutor")
    public CompletableFuture<String> lookupReplica(String key) {
        return CompletableFuture.completedFuture("replica:" + key);
    }
}
```

**`LookupCoordinator.java`:**

```java
import java.util.concurrent.CompletableFuture;
import org.springframework.stereotype.Service;

@Service
public class LookupCoordinator {
    private final LookupService lookupService;

    public LookupCoordinator(LookupService lookupService) {
        this.lookupService = lookupService;
    }

    public CompletableFuture<Object> fastest(String key) {
        CompletableFuture<String> first =
                lookupService.lookupPrimary(key);
        CompletableFuture<String> second =
                lookupService.lookupReplica(key);

        // Trả completion đầu tiên; KHÔNG tự hủy lời gọi còn lại.
        return CompletableFuture.anyOf(first, second);
    }
}
```

Những class này minh họa đường đi:

```text
Controller / caller
       |
       v
LookupCoordinator (Spring bean)
       |
       +-- gọi LookupService proxy.lookupPrimary() --> lookupExecutor task #1
       |
       +-- gọi LookupService proxy.lookupReplica() --> lookupExecutor task #2
       |
       +-- CompletableFuture.anyOf(task #1, task #2)
                           |
                           v
                    kết quả/lỗi đầu tiên
                           |
                           +--> tác vụ còn lại vẫn có thể chạy
```

**Lưu ý tích hợp:**

- `@EnableAsync` phải được bật; phương thức `@Async` phải được gọi qua **Spring-managed proxy**. `this.lookupPrimary(...)` bên trong cùng bean ở chế độ proxy mặc định có thể **bypass** interceptor và chạy ngay trên thread hiện tại.
- `@Async("lookupExecutor")` chọn đúng executor. Nếu không chỉ rõ tên, việc chọn executor tùy cấu hình Framework/Boot và bean thực tế.
- Hai method trả kết quả ngay trong ví dụ, vì vậy không dùng code này để khẳng định nhánh nào chắc chắn thắng hoặc kiểm tra tải thực. Trong hệ thống thật, thứ tự hoàn thành phụ thuộc scheduler, connection pool và remote latency.
- `ThreadPoolTaskExecutor` dùng core/max/queue và rejection policy riêng. Nếu pool/queue đầy, việc submit một nhánh có thể ném `TaskRejectedException` **trực tiếp ở caller**, trước khi phương thức coordinator trả aggregate; phải xử lý nếu hệ thống cho phép quá tải.
- Thay `CompletableFuture.completedFuture(...)` trong target bằng HTTP/JDBC thực cần timeout và chính sách cancel của dependency. `@Async` không biến tác vụ ngoại vi thành có thể hủy chắc chắn.
- `@Transactional` gắn với ranh giới proxy/transaction tại thread thực thi; transaction của caller không tự được chuyển sang worker khi thực sự dùng `@Async`.
- Một executor bean trong mỗi JVM chỉ giới hạn tải **cục bộ**, không đặt quota toàn cluster nếu có nhiều pod.

### Cẩn thận khi trả kết quả sớm khỏi controller

Nếu REST endpoint nhận future từ `fastest()` và trả response theo nhánh đầu tiên, các task thua có thể tiếp tục chạy sau khi response đã gửi. Hãy đo active tasks, thời gian phản hồi và chi phí downstream. Nếu cần “không tiếp tục làm việc sau khi client ngắt kết nối”, cần gắn cancellation từ web layer xuống HTTP client/executor bằng cơ chế hỗ trợ thực tế, không chỉ nhìn `anyOf`.

## 11. Kiểm soát chi phí và tài nguyên khi chạy đua nhiều tác vụ

Một lời gọi `anyOf` có thể tăng độ trễ được cảm nhận của **một request**, nhưng cũng tăng tải cho các nguồn.

Ví dụ một request đồng thời gọi ba replica, mỗi replica tốn một connection và 1 đơn vị quota:

```text
Một request:
   1 aggregate future
   3 remote calls đã nộp
   1 kết quả được dùng
   tối đa 2 calls thua có thể vẫn đang chạy

100 requests đồng thời:
   tối đa 300 remote calls được nộp,
   không phải chỉ 100, trừ khi admission control giới hạn.
```

Không đồng nhất “số aggregate đang chờ” với “số task/HTTP call thực tế”. Cần xét:

| Rủi ro | Kiểm soát phù hợp |
| --- | --- |
| Tạo nhiều bản sao cho mỗi request | Chỉ hedge khi cần; dùng ngưỡng độ trễ trước khi khởi tạo replica phụ |
| Bão hòa executor | Bounded `ThreadPoolTaskExecutor`, hàng đợi hữu hạn, rejection handling |
| Cạn JDBC/HTTP connection pool | Giới hạn connection/active calls phù hợp, deadline ở client |
| API đối tác có rate/concurrency quota | Rate limiter và bulkhead riêng theo dependency |
| Task thua tiếp tục gây side effect | Chỉ dùng cho đọc/idempotent, cancellation/compensation và idempotency key |
| Caller rời đi mà work còn chạy | Theo dõi lifecycle, cancellation propagation, cleanup trong `finally` |
| Retry storm khi một nhánh lỗi | Backoff/jitter, retry budget và circuit breaker |
| Nhiều replica cùng chậm | Deadline tổng; không tạo thêm replica vô hạn khi đã quá tải |

**Công thức tư duy:** nếu mỗi request có tối đa `k` nhánh, tải *submission* tối đa có thể gần `k × số request`. Mức in-flight thực tế còn phụ thuộc tốc độ hoàn thành, queue, client pool, giới hạn executor và thời điểm hedge. Cần đo thực tế, không giả định mọi nhánh thua được cắt bỏ khi `anyOf` hoàn tất.

## 12. Kiểm thử đúng cả kết quả lẫn vòng đời công việc

Một test “`assertEquals("A", anyOf.join())`” **chưa** chứng minh nhánh B được dừng. Hãy kiểm tra ở hai nhóm:

**Nhóm kết quả:**

1. Một nhánh thành công trước: aggregate trả đúng giá trị, có thể có kiểu `Object` cần chuẩn hóa.
2. Một nhánh lỗi trước: aggregate hoàn tất lỗi, không tự chờ nhánh sau thành công.
3. Một nhánh bị cancel trước: aggregate hoàn tất theo trạng thái ngoại lệ/cancellation của nhánh đó.
4. Các nhánh xong gần đồng thời: không phụ thuộc kết quả cố định nếu không kiểm soát thứ tự.
5. Không có input: aggregate chưa hoàn tất; không vô ý gọi `join()` gây chờ vô hạn.

**Nhóm vòng đời:**

1. Khi aggregate vừa xong, một supplier chậm đã thật sự bắt đầu chưa? Dùng `CountDownLatch`.
2. Supplier chậm có còn giữ worker/thread/connection không?
3. Sau khi gọi `CompletableFuture.cancel(true)`, supplier có tiếp tục chạy không? Ví dụ mục 4 chứng minh có thể tiếp tục.
4. Khi áp dụng cờ hợp tác hoặc client cancel, task có quan sát tín hiệu, đóng tài nguyên và ngừng side effect mới không?
5. Có exception hoặc task bị bỏ quên từ nhánh thua không? Có metric/log kết quả cho những task ấy không?
6. Với cancellation trong lúc đang ghi DB/remote, trạng thái nghiệp vụ được giữ nhất quán và retry idempotent chưa?
7. Khi executor shutdown, mọi task/connection có được cleanup đúng thời hạn không?

**Kỹ thuật test:** dùng latch hoặc barrier để tạo thứ tự xác định; không dùng duy nhất `Thread.sleep(100)` và kết luận chắc chắn “A luôn nhanh hơn B”. Dùng timeout cho `await`, `Future.get(timeout)` và shutdown để tránh bài test treo. Phân biệt exception **sinh ra trong task** với `TaskRejectedException` **khi submit**.

### Trực quan hóa các trạng thái khi debug

```text
anyOf result         : DONE (QUICK)
slow CompletableFuture: CANCELLED
slow supplier/worker  : STILL RUNNING
remote side effect    : POSSIBLY ALREADY COMMITTED

Các dòng này CÓ THỂ cùng đúng tại một thời điểm.
Không dùng isCancelled() để kết luận "worker đã dừng".
```

## 13. Những hiểu lầm thường gặp

### “anyOf trả lời rồi nên các task còn lại tự động bị hủy”

**Sai.** `anyOf` chỉ hoàn tất future tổng hợp; nguồn chưa thắng vẫn có thể chạy và hoàn thành. Nếu muốn dừng, phải chủ động dùng cơ chế riêng của task/client.

### “Gọi cancel(true) là chắc chắn ngắt thread đang chạy supplyAsync”

**Sai đối với `CompletableFuture.cancel`.** Java 17 Javadoc nêu tham số `mayInterruptIfRunning` không dùng để điều khiển xử lý trong implementation này. Task supplier vẫn có thể chạy tiếp, như ví dụ có latch.

### “isDone=true nghĩa là đã thực hiện xong công việc”

**Không nhất thiết.** Future bị hủy/đặt timeout có thể `isDone=true` trong khi underlying computation chưa dừng. Cần metric/task handle hoặc xác nhận cleanup thật.

### “anyOf chỉ hoàn tất khi có thành công đầu tiên”

**Sai.** Completion ngoại lệ hoặc cancellation cũng có thể kết thúc `anyOf` trước khi nhánh khác trả thành công. Nếu cần “first successful”, hãy xây coordinator có chính sách bỏ qua lỗi rõ ràng.

### “anyOf không đối số sẽ trả null ngay”

**Sai.** Nó trả future **chưa hoàn tất**. Ngược lại, `allOf()` không đối số tạo future hoàn tất với `null`; hai API không đối xứng ở trường hợp rỗng.

### “Đã gọi future.cancel thì request thanh toán đã gửi sẽ rollback”

**Sai.** Giao dịch/HTTP side effect đã tới hệ thống khác không được đảo ngược bằng việc đổi trạng thái future. Cần idempotency, transaction, trạng thái nghiệp vụ hoặc compensation có thiết kế.

### “Càng nhiều nhánh race thì càng tốt”

Không nhất thiết. Nhiều bản sao tăng tổng CPU, socket, thread, quota và có thể tự làm downstream chậm hơn. Cần bounded concurrency, cân đối tail latency với tài nguyên.

### “@Async luôn bảo đảm tác vụ được chạy song song”

Không hoàn toàn. Cần gọi qua Spring proxy, cấu hình executor có capacity, xử lý rejection và kiểm tra thứ tự scheduling. Cùng một executor chỉ có một worker vẫn xử lý tác vụ nối tiếp dù các phương thức gắn `@Async`.

### “Đặt orTimeout là đủ để hoàn tất cleanup”

Không. Timeout thay trạng thái future, không tự xác nhận supplier/HTTP request đã ngừng. Timeout của client, cancellation propagation và resource release là những vấn đề riêng.

## 14. Checklist thiết kế và tài liệu đối chiếu

Trước khi dùng `anyOf` cho một feature Spring:

1. **Mục đích là fastest-completion hay first-success?** Nếu muốn first-success, tự định nghĩa xử lý từng lỗi.
2. **Mọi nhánh có thể chạy đồng thời không?** Xác minh executor, queue và HTTP connection pool.
3. **Mỗi nhánh có side effect không?** Tránh hedge tác vụ ghi không idempotent.
4. **Ai sở hữu cancellation?** `CompletableFuture`, executor `Future`, HTTP client, reactive subscription, DB statement hay workflow controller?
5. **Hủy có dừng underlying work thật không?** Không chỉ nhìn `isCancelled()`; kiểm thử.
6. **Khi nào resource được giải phóng?** Dùng `finally`, timeout, đóng response/statement, đóng/giải phóng permit.
7. **Đường lỗi đầu tiên có phù hợp nghiệp vụ không?** `anyOf` không bỏ qua exception của nhánh thua/chưa thắng.
8. **Có số lượng nhánh tối đa và quota không?** Kiểm soát chi phí nhân bản tác vụ.
9. **Có deadline tổng và chính sách retry đúng không?** Tránh chờ vô hạn và retry storm.
10. **Có metric/log riêng cho nhánh thua không?** Đo completed/cancelled/actually-stopped, active tasks, remote calls và side effects.

**Tài liệu chính thức:**

- [Java SE 17 – CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `anyOf`, `allOf`, `cancel`, `orTimeout`, `join`, `whenComplete`.
- [Java SE 17 – Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): nghĩa của `cancel(boolean)` ở interface và nghĩa khác nhau theo implementation.
- [Java SE 17 – ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): `submit`, `Future` và shutdown.
- [Java SE 17 – CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): test có điểm đồng bộ.
- [Spring Framework – Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@Async`, `TaskExecutor`, lời gọi qua proxy và task scheduling.
- [Spring Framework – Asynchronous Return Types](https://docs.spring.io/spring-framework/reference/integration/scheduling.html#scheduling-annotation-support-async-return-types): trả `CompletableFuture` trong phương thức `@Async`.

**Ghi nhớ cuối cùng:** `anyOf` là **bộ chọn một trạng thái hoàn tất**, không phải **bộ quản lý vòng đời các công việc còn lại**. Nếu muốn tiết kiệm tài nguyên hoặc dừng nhánh thua, cần có cancellation handle/cooperative stop/client timeout đúng tầng, và phải kiểm tra việc thực thi thật đã dừng — không chỉ rằng một future có `isCancelled() == true`.
