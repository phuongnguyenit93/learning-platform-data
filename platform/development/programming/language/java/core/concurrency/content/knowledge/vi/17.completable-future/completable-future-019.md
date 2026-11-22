# CompletableFuture.getNow(): đọc kết quả không chặn và phân biệt null với chưa hoàn tất

> **Cốt lõi:** Trong Java 17, `CompletableFuture<T>.getNow(T valueIfAbsent)` **không chờ** computation hoàn thành. Nếu Future **chưa hoàn tất**, nó trả ngay **giá trị dự phòng** `valueIfAbsent`. Nếu đã hoàn tất thành công, nó trả **kết quả thật**, kể cả khi kết quả thật là `null`. Nếu hoàn tất do lỗi hoặc bị hủy, lời gọi có thể **ném exception ngay lập tức**; `valueIfAbsent` không phải fallback để che lỗi. Vì thế, `getNow(null) == null` **không đủ để kết luận Future đang pending**: hai trạng thái khác nhau có cùng giá trị đọc được.

Bài thuộc nhóm **CompletableFuture**, phạm vi **Java concurrency nói chung** theo Special Note, sử dụng Java SE 17+. Không sử dụng Spring. Mục tiêu là đọc trạng thái mà **không block thread gọi**, phân biệt kết quả hợp lệ `null` với thiếu kết quả, hiểu error/cancellation, và tránh các race trong các hệ thống bất đồng bộ.

## 1. Vấn đề thực tế

Giả sử một API đã khởi động công việc bất đồng bộ:

~~~java
// Snippet API, không phải chương trình độc lập.
CompletableFuture<String> future =
        CompletableFuture.supplyAsync(this::loadDisplayName);
~~~

Trong lúc render dashboard hoặc đọc cache, caller muốn biết **nếu kết quả đã sẵn sàng thì lấy ngay**, còn nếu chưa thì hiển thị trạng thái loading. Caller **không muốn đợi** worker xử lý xong.

Có một nhầm lẫn phổ biến:

~~~java
// MÃ SAI về phân biệt trạng thái:
String value = future.getNow(null);
if (value == null) {
    // Không được chắc chắn đây là "đang tải".
}
~~~

`null` có thể là kết quả hợp lệ, ví dụ “không tìm thấy tên”, “không có gợi ý”, hoặc một `CompletableFuture<Void>` đã hoàn thành bình thường. Khi dùng `null` như cả **kết quả nghiệp vụ** lẫn **tín hiệu pending**, caller mất khả năng phân biệt hai trạng thái.

### Ba câu hỏi tách biệt

1. **Task đã hoàn tất chưa?** Tham khảo `isDone()`, nhưng đây là một lần đọc trạng thái có thể thay đổi ngay sau đó.
2. **Task có hoàn tất thành công không?** `isDone()==true` chưa đủ: cần phân biệt success, failure và cancellation.
3. **Kết quả thành công có là `null` không?** Đây là một **giá trị hợp lệ theo contract của CompletableFuture**, trừ khi chính chương trình bạn định nghĩa rằng kết quả luôn non-null.

Đừng gộp ba câu hỏi vào một phép so sánh `getNow(null) == null`.

## 2. Hợp đồng API getNow trong Java 17

Chữ ký:

~~~java
public T getNow(T valueIfAbsent)
~~~

Ý nghĩa:

- **Chưa completed:** trả `valueIfAbsent` ngay, không đợi kết quả thật.
- **Completed normally với non-null T:** trả đúng giá trị đó, không dùng `valueIfAbsent`.
- **Completed normally với null:** trả `null`, dù `valueIfAbsent` là non-null.
- **Completed exceptionally:** ném `CompletionException` tương ứng với nguyên nhân lỗi (các trường hợp cancellation có exception riêng).
- **Cancelled:** thường ném `CancellationException` trực tiếp đối với CompletableFuture bị `cancel`; caller phải xử lý riêng.
- **Không đặt deadline:** nếu chưa completed, hàm trả dự phòng ngay, không chờ timeout hay ép worker tiến triển.
- **Không khởi động computation thay caller:** Nó đọc trạng thái completion hiện có; không phải `start()`/`submit()`/`complete()`.
- **Không tự cancel:** Trả fallback vì chưa completed không thay đổi state của Future.

`valueIfAbsent` là **giá trị dùng khi chưa có completion**, không phải `orElse` cho business-null, cũng không phải `exceptionally` để phục hồi lỗi.

### Bảng trạng thái cần nhớ

| Trạng thái Future tại thời điểm quan sát | `isDone()` | `isCancelled()` | `getNow("WAIT")` |
| --- | --- | --- | --- |
| Pending, chưa hoàn tất | `false` | `false` | `"WAIT"` |
| Completed normally, giá trị `"OK"` | `true` | `false` | `"OK"` |
| Completed normally, giá trị `null` | `true` | `false` | `null` |
| Completed exceptionally (ví dụ IllegalStateException) | `true` | `false` | Ném `CompletionException` |
| Cancelled | `true` | `true` | Ném `CancellationException` |

Bảng mô tả các **tình huống độc lập**. Khi một thread đọc `isDone` rồi gọi `getNow`, một thread khác có thể complete Future ở giữa hai thao tác. Hai lần đọc **không là một snapshot atomic duy nhất**.

## 3. So sánh get(), join() và getNow()

| Phương thức | Khi chưa completed | Thành công | Lỗi computation | Hủy |
| --- | --- | --- | --- | --- |
| `get()` | **Chờ**; có thể bị interrupt | Trả T, kể cả null | `ExecutionException` | `CancellationException` |
| `get(timeout, unit)` | Chờ tối đa timeout | Trả T, kể cả null | `ExecutionException` | `CancellationException` |
| `join()` | **Chờ**; dùng trong completion-style pipelines | Trả T, kể cả null | `CompletionException` | `CancellationException` |
| `getNow(valueIfAbsent)` | **Trả dự phòng ngay** | Trả T, kể cả null | `CompletionException` | `CancellationException` |

`get(timeout, unit)` là timed wait, không phải non-blocking poll. Dù timeout bằng một khoảng rất nhỏ, caller vẫn tham gia cơ chế chờ/timeout và cần xử lý checked exceptions. `getNow` không đợi result.

`join()` và `getNow` đều tiện trong pipeline khi caller không muốn khai báo `InterruptedException`/`ExecutionException` như `get()`, nhưng điều đó **không** làm lỗi biến mất: chúng đi qua unchecked completion/cancellation exceptions.

### Đừng hiểu isDone() là thành công

`isDone()==true` bao gồm:
- Hoàn tất bình thường với giá trị bất kỳ, kể cả `null`.
- Hoàn tất ngoại lệ.
- Bị hủy.

`isCompletedExceptionally()` đúng cho exceptional completion và có thể đúng khi cancelled; dùng `isCancelled()` khi cần phân biệt cancellation. Để lấy kết quả thật và phân loại lỗi cuối cùng, dùng `getNow`/`join` cùng catch tương ứng.

## 4. Ví dụ 1 — pending và completed-null cùng cho null nếu fallback là null

Tạo `GetNowNullAmbiguity.java` (Java 17+):

~~~java
import java.util.concurrent.CompletableFuture;

public class GetNowNullAmbiguity {
    public static void main(String[] args) {
        CompletableFuture<String> pending = new CompletableFuture<>();
        CompletableFuture<String> doneNull =
                CompletableFuture.completedFuture(null);

        System.out.println("pending getNow(null) = "
                + pending.getNow(null));
        System.out.println("done-null getNow(null) = "
                + doneNull.getNow(null));

        System.out.println("pending isDone = " + pending.isDone());
        System.out.println("done-null isDone = " + doneNull.isDone());

        System.out.println("pending getNow(WAIT) = "
                + pending.getNow("WAIT"));
        System.out.println("done-null getNow(WAIT) = "
                + doneNull.getNow("WAIT"));

        pending.complete("READY");
        System.out.println("pending after complete = "
                + pending.getNow("WAIT"));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac GetNowNullAmbiguity.java
java GetNowNullAmbiguity
~~~

Stdout chính xác:

~~~text
pending getNow(null) = null
done-null getNow(null) = null
pending isDone = false
done-null isDone = true
pending getNow(WAIT) = WAIT
done-null getNow(WAIT) = null
pending after complete = READY
~~~

Với `getNow(null)`, hai dòng đầu **giống hệt nhau**, dù một Future chưa hoàn tất và Future kia hoàn tất thành công với null. Dùng dự phòng `"WAIT"` giúp nhận diện trong ví dụ này, vì kết quả nghiệp vụ được giả định **không bao giờ thực sự là chuỗi "WAIT"**. Nếu nghiệp vụ có thể trả đúng `"WAIT"`, cách này **vẫn mơ hồ**.

Chú ý `pending.complete("READY")` là một thao tác làm Future completed; nó không cần worker riêng. Bài ví dụ được điều phối tuần tự để output không phụ thuộc scheduling.

## 5. Giá trị dự phòng khác null: sentinel và rủi ro va chạm

Một hướng giải quyết là dùng **sentinel**, nghĩa là một giá trị chỉ dùng để biểu thị “chưa có completion”.

~~~java
// Snippet, chỉ đúng khi business contract cấm trả "PENDING".
String value = future.getNow("PENDING");
if ("PENDING".equals(value)) {
    // Có thể pending, nhưng cũng có thể là kết quả thật "PENDING".
}
~~~

**Không sử dụng một giá trị phổ biến làm sentinel** khi chính domain có thể trả về giá trị ấy. Chẳng hạn `0` là kết quả đếm hợp lệ, `false` là kết quả boolean hợp lệ và chuỗi `"N/A"` có thể là kết quả thật.

### Sentinel theo identity

Nếu một Future có type `Object` và input/domain **không thể trả về chính sentinel object** đã tạo riêng, có thể dùng phép so sánh reference identity:

~~~java
// Snippet Java: CompletableFuture<Object> future phải do caller tạo.
Object sentinel = new Object();
Object current = future.getNow(sentinel);
if (current == sentinel) {
    // Chưa completed tại thời điểm quan sát getNow.
} else {
    // Completed normally; current có thể là null.
}
~~~

Ở đây không dùng `sentinel.equals(current)` vì identity mới là tính chất đặc biệt. Tuy nhiên cần bảo đảm sentinel **không lọt vào tập kết quả hợp lệ**. Nếu một Future thực sự hoàn tất bằng chính reference sentinel đó, phép phân biệt sẽ sai.

Với `CompletableFuture<String>`, không thể truyền `new Object()` trực tiếp vào `getNow(String)` vì sai type. Đừng dùng raw casts để lách type safety; chọn **một kiểu kết quả biểu diễn trạng thái rõ ràng** nếu domain của T không có sentinel bảo đảm độc nhất.

## 6. Ví dụ 2 — sentinel Object phân biệt pending, null và giá trị thật

Tạo `GetNowIdentitySentinel.java` (Java 17+):

~~~java
import java.util.concurrent.CompletableFuture;

public class GetNowIdentitySentinel {
    public static void main(String[] args) {
        Object notReady = new Object();
        CompletableFuture<Object> future = new CompletableFuture<>();

        Object before = future.getNow(notReady);
        System.out.println("pending = " + (before == notReady));

        future.complete(null);
        Object after = future.getNow(notReady);

        System.out.println("done = " + future.isDone());
        System.out.println("completed with null = " + (after == null));
        System.out.println("not sentinel = " + (after != notReady));

        CompletableFuture<Object> other =
                CompletableFuture.completedFuture("READY");
        System.out.println("value = " + other.getNow(notReady));
    }
}
~~~

Chạy:

~~~bash
javac GetNowIdentitySentinel.java
java GetNowIdentitySentinel
~~~

Stdout:

~~~text
pending = true
done = true
completed with null = true
not sentinel = true
value = READY
~~~

`notReady` là một object mới không được đưa làm giá trị kết quả của Future nào trong ví dụ. `getNow(notReady)` trước completion trả chính sentinel; sau `complete(null)` trả **null thật**, không trả sentinel. Vì vậy phép so sánh theo reference identity giải quyết đúng hai tình huống ở đây.

**Giới hạn kỹ thuật:** Bạn không thể khẳng định một sentinel theo identity là an toàn nếu code ngoài module có thể hoàn thành Future bằng chính reference ấy. Với public API hoặc data model phức tạp, cách biểu diễn completion **bằng kiểu dữ liệu riêng** rõ ràng hơn.

## 7. Biểu diễn kết quả với kiểu không null, thay vì đặt hai nghĩa vào null

Một cách thiết kế sạch hơn: Future **luôn trả về một envelope/holder non-null** cho kết quả thành công. Chẳng hạn:

- `CompletableFuture<Optional<T>>`: `Optional.empty()` nghĩa là **đã hoàn tất và không có giá trị nghiệp vụ**; bản thân `Optional` luôn non-null theo contract của ứng dụng.
- `CompletableFuture<Result<T>>` với một record/sealed hierarchy mô tả trạng thái success-with-value, success-without-value; failure vẫn để exceptional completion hoặc encode theo yêu cầu.
- `CompletableFuture<Outcome>` mà outcome là một record bất biến chứa thông tin kết quả và metadata.

Với `CompletableFuture<Optional<String>>`, nếu chương trình **cam kết không complete Future bằng null**, ta có thể dùng `getNow(null)` như dấu hiệu pending; sau khi hoàn tất thành công, giá trị sẽ là `Optional.empty()` hoặc `Optional.of(...)`.

~~~text
CompletableFuture<Optional<String>>

Pending:                 getNow(null) -> null
Completed with no value: getNow(null) -> Optional.empty()
Completed with value:    getNow(null) -> Optional.of("A")
Completed exceptionally: getNow(null) -> throws CompletionException
Cancelled:               getNow(null) -> throws CancellationException
~~~

Đây là phân biệt thông qua **contract của kiểu dữ liệu**, không phải do `getNow(null)` tự có khả năng biết tại sao null xuất hiện. Nếu bất kỳ code nào vẫn gọi `future.complete(null)`, sự mơ hồ quay lại; cần thống nhất invariant này trong toàn producer pipeline.

### Ví dụ 3 — CompletableFuture<Optional<T>> để không nhầm “no value” với “pending”

Tạo `OptionalResultStage.java` (Java 17+):

~~~java
import java.util.Optional;
import java.util.concurrent.CompletableFuture;

public class OptionalResultStage {
    public static void main(String[] args) {
        CompletableFuture<Optional<String>> future =
                new CompletableFuture<>();

        Optional<String> before = future.getNow(null);
        System.out.println("pending = " + (before == null));

        future.complete(Optional.empty());
        Optional<String> after = future.getNow(null);
        System.out.println("done = " + future.isDone());
        System.out.println("completed with no value = " + after.isEmpty());

        CompletableFuture<Optional<String>> withValue =
                CompletableFuture.completedFuture(Optional.of("Ada"));
        System.out.println("name = "
                + withValue.getNow(null).orElse("UNKNOWN"));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac OptionalResultStage.java
java OptionalResultStage
~~~

Stdout:

~~~text
pending = true
done = true
completed with no value = true
name = Ada
~~~

Lời gọi `after.isEmpty()` an toàn **do application đã hoàn thành Future bằng `Optional.empty()` và cam kết kết quả thành công không null**. Trong code thư viện nhận một `CompletableFuture<Optional<String>>` không đáng tin, cần kiểm tra null/validate contract trước khi gọi method.

**Không nhầm `Optional.empty()` với lỗi:** “Không tìm thấy dữ liệu” là success-without-value khi domain định nghĩa như thế; “DB connection hỏng” thường là exceptional completion, không nên tự chuyển mọi lỗi thành Optional.empty rồi âm thầm che giấu sự cố.

## 8. Ví dụ 4 — getNow không đổi trạng thái Future

Đọc fallback nhiều lần không làm công việc tự hoàn thành. Lần sau có thể vẫn pending nếu producer chưa `complete`.

Tạo `GetNowNoSideEffect.java` (Java 17+):

~~~java
import java.util.concurrent.CompletableFuture;

public class GetNowNoSideEffect {
    public static void main(String[] args) {
        CompletableFuture<Integer> future = new CompletableFuture<>();

        System.out.println("first read = " + future.getNow(-1));
        System.out.println("second read = " + future.getNow(-1));
        System.out.println("done after reads = " + future.isDone());

        System.out.println("complete accepted = " + future.complete(42));
        System.out.println("third read = " + future.getNow(-1));
        System.out.println("done after complete = " + future.isDone());
    }
}
~~~

Chạy:

~~~bash
javac GetNowNoSideEffect.java
java GetNowNoSideEffect
~~~

Stdout:

~~~text
first read = -1
second read = -1
done after reads = false
complete accepted = true
third read = 42
done after complete = true
~~~

`getNow(-1)` không phải `complete(-1)`. Nó chỉ cung cấp giá trị để **caller dùng tại thời điểm đọc**, còn Future vẫn chưa completed. Sau `complete(42)`, việc đọc trả 42.

Một rủi ro khác: fallback có thể trùng với giá trị thật. Nếu computation hợp lệ trả `-1`, cách so sánh `getNow(-1) == -1` lại không đủ phân biệt pending và done.

## 9. Exceptional completion không dùng valueIfAbsent làm fallback

Lưu ý trọng yếu: `getNow(valueIfAbsent)` dùng fallback **khi chưa completed**, không phải khi Future thất bại.

Một computation có thể hoàn tất ngoại lệ qua:

- `completeExceptionally(cause)`.
- Mapper/`Callable`/`Supplier` ném exception, khiến CompletableFuture dependent kết thúc exceptional.
- `orTimeout(timeout, unit)` đặt exceptional completion với `TimeoutException` nếu chưa completed.
- Exceptional completion từ source stage được propagate qua dependent stage chưa xử lý.
- Cancellation là trường hợp đặc biệt của completion bất thường.

Với lỗi như `IllegalArgumentException`, `getNow` thường ném `CompletionException` chứa cause. Caller phải dùng `getCause()` để phân loại root cause. Đừng bắt `Exception` rồi trả sentinel mặc định cho mọi lỗi nếu business không cho phép điều đó.

### Ví dụ 5 — success, failure và cancellation

Tạo `GetNowFailures.java` (Java 17+):

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class GetNowFailures {
    public static void main(String[] args) {
        CompletableFuture<String> success =
                CompletableFuture.completedFuture("OK");

        CompletableFuture<String> failed = new CompletableFuture<>();
        failed.completeExceptionally(
                new IllegalStateException("storage unavailable"));

        CompletableFuture<String> cancelled = new CompletableFuture<>();
        cancelled.cancel(false);

        System.out.println("success = " + success.getNow("WAIT"));

        try {
            failed.getNow("WAIT");
        } catch (CompletionException e) {
            System.out.println("failure cause = "
                    + e.getCause().getClass().getSimpleName());
        }

        try {
            cancelled.getNow("WAIT");
        } catch (CancellationException e) {
            System.out.println("cancelled exception = true");
        }

        System.out.println("failure done = " + failed.isDone());
        System.out.println("failure cancelled = "
                + failed.isCancelled());
        System.out.println("cancel done = " + cancelled.isDone());
        System.out.println("cancel cancelled = "
                + cancelled.isCancelled());
    }
}
~~~

Chạy:

~~~bash
javac GetNowFailures.java
java GetNowFailures
~~~

Stdout:

~~~text
success = OK
failure cause = IllegalStateException
cancelled exception = true
failure done = true
failure cancelled = false
cancel done = true
cancel cancelled = true
~~~

Không có dòng `WAIT` cho failure/cancel vì Future **đã completed** theo đường không bình thường; default chỉ dùng khi chưa có completion. `isDone()==true` không đồng nghĩa thành công. Với CompletableFuture bị `cancel`, `getNow` ném `CancellationException`; lỗi tính toán bình thường thường đi qua `CompletionException`.

**Không nhầm cancellation với body đã dừng:** `CompletableFuture.cancel(true)` không có hiệu lực interrupt computation theo implementation CompletableFuture, và Future cancelled có thể vẫn có worker thực hiện side effect/cleanup. Cancellation liên quan trạng thái kết quả, còn việc dừng task cần protocol riêng.

## 10. getNow và isDone: check-then-act không phải atomic snapshot

Một thiết kế thường gặp:

~~~java
// Snippet: có thể dùng để báo trạng thái gần đúng,
// nhưng đây KHÔNG phải một phép đọc atomic của hai sự kiện.
if (!future.isDone()) {
    return "PENDING";
}
return future.getNow(null);
~~~

Đây là mẫu có thể dùng để hiển thị trạng thái ở một thời điểm, **nếu chấp nhận status có thể cũ**. Future có thể completed ngay sau `isDone()==false`, khiến caller trả PENDING dù kết quả đã sẵn sàng một tích tắc sau đó.

Trong hướng ngược lại, khi `isDone()==true`, Future sẽ không quay lại pending với implementation CompletableFuture thông thường; `getNow` không phải chờ. Nhưng nó vẫn có thể ném `CompletionException`/`CancellationException`, và kết quả thật vẫn có thể là null.

**Không cố “sửa” race chỉ bằng check hai lần:**

~~~java
// Snippet không giải quyết transactional snapshot chung.
boolean done1 = future.isDone();
T observed = future.getNow(fallback);
boolean done2 = future.isDone();
~~~

Ba phép đọc xảy ra tại ba thời điểm. Nếu application cần một lần quan sát trạng thái được phân loại rõ ràng, dùng một **result envelope** và một protocol xử lý, hoặc snapshot rõ ràng của completion status ở caller. Với `getNow` riêng lẻ, một unique sentinel ở đúng kiểu có thể phân biệt pending/normal completion trong phạm vi **lần đọc đó**, còn exception handling phân biệt failure/cancel.

### Ví dụ 6 — trạng thái có thể đổi giữa isDone và getNow

Tạo `IsDoneRaceDemo.java` (Java 17+):

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public class IsDoneRaceDemo {
    public static void main(String[] args) throws InterruptedException {
        CompletableFuture<String> future = new CompletableFuture<>();
        CountDownLatch checked = new CountDownLatch(1);
        CountDownLatch continueReader = new CountDownLatch(1);
        AtomicBoolean doneAtCheck = new AtomicBoolean();
        AtomicReference<String> readLater = new AtomicReference<>();

        Thread reader = new Thread(() -> {
            doneAtCheck.set(future.isDone());
            checked.countDown();
            try {
                continueReader.await();
                readLater.set(future.getNow("WAIT"));
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        reader.start();
        checked.await();
        future.complete("READY");
        continueReader.countDown();
        reader.join();

        System.out.println("isDone at check = " + doneAtCheck.get());
        System.out.println("getNow later = " + readLater.get());
        System.out.println("isDone now = " + future.isDone());
    }
}
~~~

Chạy:

~~~bash
javac IsDoneRaceDemo.java
java IsDoneRaceDemo
~~~

Stdout:

~~~text
isDone at check = false
getNow later = READY
isDone now = true
~~~

Latches bắt buộc reader đọc `isDone()==false` **trước** khi main complete Future, rồi reader mới gọi `getNow`. Vì vậy đây là một interleaving xác định, không dựa vào may mắn của scheduler hay `Thread.sleep(100)`. Bài học: trạng thái quan sát ở t1 **không phải** trạng thái bất biến ở t2.

Ứng dụng thường không cần chính xác mọi microsecond của tiến triển; một dashboard có thể báo PENDING cũ rồi cập nhật ở event tiếp theo. Nhưng workflow tài chính hoặc transaction không thể ra quyết định khó đảo ngược chỉ từ một status đã cũ.

## 11. getNow() không chặn ngay cả khi task đang chạy lâu

Để minh họa, ta cần bảo đảm task đang hoạt động nhưng **không thể hoàn thành** trước lần đọc. Dùng `CountDownLatch` thay vì một phép đo timing mong manh.

### Ví dụ 7 — đọc ngay khi callback vẫn đang đợi

Tạo `GetNowWhileRunning.java` (Java 17+):

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class GetNowWhileRunning {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            CompletableFuture<String> future =
                    CompletableFuture.supplyAsync(() -> {
                        started.countDown();
                        try {
                            release.await();
                        } catch (InterruptedException e) {
                            Thread.currentThread().interrupt();
                            return "INTERRUPTED";
                        }
                        return "READY";
                    }, pool);

            started.await();
            System.out.println("getNow while running = "
                    + future.getNow("WAIT"));
            System.out.println("isDone while waiting = "
                    + future.isDone());

            release.countDown();
            System.out.println("join after release = " + future.join());
            System.out.println("getNow after finish = "
                    + future.getNow("WAIT"));
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac GetNowWhileRunning.java
java GetNowWhileRunning
~~~

Stdout trên đường chạy bình thường:

~~~text
getNow while running = WAIT
isDone while waiting = false
join after release = READY
getNow after finish = READY
~~~

Worker giảm `started` rồi **đợi release**; main không mở release cho tới sau khi gọi `getNow` và `isDone`. Vì thế result chắc chắn còn pending ở hai phép đọc. Sau khi main gọi `release.countDown()`, `join()` chờ worker return `READY` và `getNow` đọc kết quả thật.

Điểm cốt lõi: `getNow` **không block chờ latch**, còn `join` có thể block cho đến khi computation kết thúc. Đừng đặt một vòng `while(future.getNow("WAIT").equals("WAIT")) { }` không giới hạn rồi tưởng chương trình đã trở thành non-blocking system: từng lần đọc không chặn, nhưng vòng lặp có thể **spin CPU** vô hạn.

## 12. Vì sao getNow(null) đặc biệt dễ sai với CompletableFuture<Void>?

`CompletableFuture<Void>` thường xuất hiện từ:

- `CompletableFuture.runAsync(Runnable)`.
- `thenAccept(...)` / `thenAcceptAsync(...)`.
- `thenRun(...)` / `thenRunAsync(...)`.
- `CompletableFuture.allOf(...)` khi chờ nhiều Futures.
- Một task mà thành công **không có giá trị trả về**.

`Void` không có một instance non-null thông thường để caller truyền làm fallback. Với các stage thành công của kiểu `Void`, kết quả chuẩn là `null`; còn khi stage chưa completed, `getNow(null)` cũng trả null.

~~~java
// Snippet: cả hai có thể in null.
CompletableFuture<Void> pending = new CompletableFuture<>();
CompletableFuture<Void> done =
        CompletableFuture.completedFuture(null);

System.out.println(pending.getNow(null));
System.out.println(done.getNow(null));
~~~

Không nên ép tạo `Void` object hoặc raw cast để có sentinel. Đó là đi ngược type system.

### Cách quan sát khác

1. Sử dụng `isDone()` để báo **trạng thái gần đúng**; nếu true, phân loại success/failure/cancel qua `getNow(null)` trong try/catch. Trong trường hợp cần đánh giá cùng một thời điểm, lưu ý race giữa các lần đọc.
2. Tạo dependent stage mang **một marker non-null** sau khi source hoàn tất bình thường: `future.thenApply(ignored -> Boolean.TRUE)`. Khi đó `marker.getNow(Boolean.FALSE)` phân biệt pending/normal success theo contract rằng stage này **chỉ trả true khi thành công**.
3. Dùng `whenComplete`/`handle` để cập nhật một state machine của ứng dụng; đối với lỗi phải giữ nguyên thông tin thay vì che giấu.
4. Nếu API của bạn kiểm soát producer, có thể chọn `CompletableFuture<Optional<Result>>` hoặc kết quả bọc vào record thay cho `Void` khi cần biểu diễn thông tin trạng thái.

### Ví dụ 8 — biến Void completion thành marker Boolean

Tạo `VoidCompletionMarker.java` (Java 17+):

~~~java
import java.util.concurrent.CompletableFuture;

public class VoidCompletionMarker {
    public static void main(String[] args) {
        CompletableFuture<Void> action = new CompletableFuture<>();

        CompletableFuture<Boolean> marker =
                action.thenApply(ignored -> Boolean.TRUE);

        System.out.println("action getNow(null) = "
                + action.getNow(null));
        System.out.println("marker before = "
                + marker.getNow(Boolean.FALSE));

        action.complete(null);

        System.out.println("action getNow(null) after = "
                + action.getNow(null));
        System.out.println("marker after = "
                + marker.getNow(Boolean.FALSE));
    }
}
~~~

Chạy:

~~~bash
javac VoidCompletionMarker.java
java VoidCompletionMarker
~~~

Stdout:

~~~text
action getNow(null) = null
marker before = false
action getNow(null) after = null
marker after = true
~~~

Vì `thenApply` non-async được gắn trước khi `action` completed và callback chỉ return `TRUE`, sau `action.complete(null)`, dependent marker đã completed normally trong ví dụ, nên `getNow(FALSE)` cho true. Trước đó marker chưa completed và trả false. **Nếu source failed**, callback mapper không chạy và marker có thể exceptional; lúc ấy `getNow(FALSE)` không trả false mà ném completion exception.

Ở production, nếu dùng `thenApplyAsync` để tạo marker, nó có thể vẫn pending **sau** lúc source completed vì marker còn đợi executor. Đừng suy ra source/marker cùng completed tại mọi thời điểm.

## 13. Một helper phân loại trạng thái bằng getNow và exceptions

Khi cần hiển thị trạng thái từ một CompletableFuture có thể trả `null`, có thể tách kết quả thành **kiểu trạng thái rõ ràng**. Phần helper dưới đây dùng một lần `getNow` với sentinel riêng được quản lý trong kiểu `Object` để phân biệt pending/normal result, đồng thời catch lỗi và hủy.

### Ví dụ 9 — render Pending / Ready(null) / Ready(value) / Failed / Cancelled

Tạo `GetNowStatusView.java` (Java 17+):

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class GetNowStatusView {
    private static final Object PENDING = new Object();

    static String status(CompletableFuture<Object> future) {
        try {
            Object value = future.getNow(PENDING);
            if (value == PENDING) {
                return "PENDING";
            }
            if (value == null) {
                return "READY(null)";
            }
            return "READY(" + value + ")";
        } catch (CancellationException e) {
            return "CANCELLED";
        } catch (CompletionException e) {
            return "FAILED("
                    + e.getCause().getClass().getSimpleName() + ")";
        }
    }

    public static void main(String[] args) {
        CompletableFuture<Object> pending = new CompletableFuture<>();
        CompletableFuture<Object> doneNull =
                CompletableFuture.completedFuture(null);
        CompletableFuture<Object> doneValue =
                CompletableFuture.completedFuture(42);

        CompletableFuture<Object> failed = new CompletableFuture<>();
        failed.completeExceptionally(new IllegalArgumentException("bad"));

        CompletableFuture<Object> cancelled = new CompletableFuture<>();
        cancelled.cancel(false);

        System.out.println("pending = " + status(pending));
        System.out.println("null = " + status(doneNull));
        System.out.println("value = " + status(doneValue));
        System.out.println("failure = " + status(failed));
        System.out.println("cancel = " + status(cancelled));
    }
}
~~~

Chạy:

~~~bash
javac GetNowStatusView.java
java GetNowStatusView
~~~

Stdout:

~~~text
pending = PENDING
null = READY(null)
value = READY(42)
failure = FAILED(IllegalArgumentException)
cancel = CANCELLED
~~~

Điều kiện thiết kế của helper là **các producers không bao giờ complete Future bằng chính static reference `PENDING`**. Vì đây là một constant private chỉ dùng nội bộ để đọc trạng thái, ví dụ đáp ứng điều kiện ấy. Nếu public API cho phép caller lấy reference và complete bằng sentinel, phải bỏ assumption hoặc chuyển sang result-envelope có invariant chặt hơn.

Một helper cũng nên quyết định policy với `CompletionException` chứa cause bất thường/khác null; ví dụ tập trung vào lỗi `IllegalArgumentException` cụ thể. Không tự nuốt exceptions rồi trả `READY(null)`, vì có thể khiến báo cáo thành công giả.

## 14. Giá trị fallback có thể bị tính trước dù không được sử dụng

Trong Java, arguments được đánh giá **trước** khi gọi method. Do đó:

~~~java
// Snippet cảnh báo:
String value = future.getNow(expensiveFallback());
~~~

`expensiveFallback()` được gọi **ngay cả khi Future đã completed normally** và kết quả thật không cần fallback. `getNow` không phải API lazy `Supplier<T>`.

Nếu fallback cần I/O, allocation lớn hoặc side effect, đoạn code có thể trở nên chậm/block vì **đánh giá argument**, dù bản thân `getNow` không chờ Future.

### Ví dụ 10 — fallback được tính eager

Tạo `EagerDefaultArgument.java` (Java 17+):

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicInteger;

public class EagerDefaultArgument {
    static String fallback(AtomicInteger calls) {
        calls.incrementAndGet();
        return "WAIT";
    }

    public static void main(String[] args) {
        AtomicInteger calls = new AtomicInteger();
        CompletableFuture<String> done =
                CompletableFuture.completedFuture("READY");

        String observed = done.getNow(fallback(calls));
        System.out.println("observed = " + observed);
        System.out.println("fallback evaluated = " + calls.get());
    }
}
~~~

Chạy:

~~~bash
javac EagerDefaultArgument.java
java EagerDefaultArgument
~~~

Stdout:

~~~text
observed = READY
fallback evaluated = 1
~~~

Kết quả thật `READY` vẫn được trả; phương thức `fallback(calls)` đã được gọi vì Java cần tính đối số trước khi vào `getNow`. Ưu tiên sentinel constant hoặc value đã có sẵn, không đặt công việc expensive vào đối số với kỳ vọng chỉ được gọi khi pending.

## 15. getNow() không phải cơ chế thay cho callback bất đồng bộ

Nếu mục tiêu của bạn là “khi Future xong, hãy thực hiện logic ngay” thì thường **không cần poll**:

~~~java
// Snippet API, đặt trong một method có các biến phù hợp.
future.thenAccept(value -> updateUiModel(value));
future.whenComplete((value, error) -> logCompletion(value, error));
~~~

Đây là cách khai báo một dependent stage/callback phản ứng với completion. Cần chọn executor phù hợp nếu callback nặng hoặc blocking (`thenAcceptAsync(..., executor)`, `whenCompleteAsync(..., executor)`).

`getNow` hợp khi caller muốn một **snapshot tức thời**, ví dụ render trạng thái hiện tại mà không block. Nó không có chức năng chờ có tín hiệu, không cung cấp notification, cũng không lập lịch lại caller khi result thay đổi.

### Không busy-spin không giới hạn

Mẫu nguy hiểm:

~~~java
// MÃ SAI về tài nguyên và cả sentinel collision.
while (future.getNow("WAIT").equals("WAIT")) {
    // spin liên tục, có thể tốn CPU hoặc không bao giờ dừng
}
~~~

Rủi ro:

- Nếu result thật cũng bằng `"WAIT"`, vòng lặp có thể tiếp tục mãi dù completed normally.
- Nếu Future failed/cancelled, exception có thể thoát bất ngờ.
- Nếu chưa completed, loop liên tục lấy CPU, cạnh tranh với chính worker đang cần CPU.
- Nếu worker kẹt, không có timeout hoặc cleanup.
- `getNow` là mỗi lần đọc không chặn, nhưng **vòng lặp tổng thể vẫn có thể không kết thúc**.

Nếu cần chờ, hãy chọn `get(timeout)`, `join` khi hợp lý, callback composition hoặc synchronizer có timeout. Nếu cần event-loop polling, cần cơ chế scheduling/backoff và trạng thái non-null không va chạm, cùng cancellation/lifecycle.

## 16. getNow trong một pipeline có nhiều dependent stages

Một pipeline như:

~~~text
supplyAsync(fetch, ioExecutor)
     |
     v
thenApplyAsync(parse, cpuExecutor)
     |
     v
thenApply(validate)
     |
     v
thenComposeAsync(enrich, ioExecutor)
     |
     v
final Future
~~~

có **một Future cho mỗi stage**. Khi source completed, dependent `parse` có thể **chưa** completed vì còn chờ executor. Vì vậy:

- `source.getNow(fallback)` có thể trả dữ liệu tải về.
- `parseFuture.getNow(fallback)` vẫn có thể trả fallback.
- `validateFuture.getNow(fallback)` cũng có thể pending.
- Final Future vẫn pending hoặc exceptional dù một stage đầu đã successful.

Không dựa vào một `source.isDone()==true` để kết luận **toàn pipeline** đã xong. Giữ handle của **final stage** nếu caller quan tâm kết quả cuối. Trong mô hình fan-out, giữ handles của các nhánh riêng hoặc gộp chúng bằng `allOf`/`thenCombine` tùy dependency.

### Quan sát source exceptional

Nếu source failed, mapper `thenApply`/`thenApplyAsync` không được gọi. Dependent stage được hoàn tất exceptional theo propagation rules. `getNow` trên dependent sẽ ném exception nếu propagation đã hoàn tất; nó có thể còn pending trong một khoảng thời gian ngắn tùy trigger/scheduling. Đừng tự coi mọi kết quả fallback là “chưa có dữ liệu” mà bỏ qua khả năng failed.

Nếu cần phục hồi lỗi, dùng `exceptionally`, `handle` hoặc `exceptionallyAsync` theo contract, rồi quan sát **stage phục hồi**, không chỉ stage đã failed.

## 17. thenApplyAsync, timeout và việc không chặn ở lớp ứng dụng

`CompletableFuture.getNow` không chờ stage, nhưng logic bao quanh có thể vô tình block:

- Fallback expression làm I/O trước lúc gọi `getNow`.
- Callback logging/render làm synchronous network I/O.
- Tạo retry ngay lập tức nếu pending.
- Chạy nhiều `getNow` theo vòng polling không có backoff.
- Lấy lock ứng dụng trước khi đọc hoặc giữ lock qua một Future `join()` khác.

Vì vậy chỉ nói “API getNow non-blocking” là **hợp đồng của phép lấy kết quả này**, không phải cam kết toàn bộ call path luôn có latency thấp.

### Timeout khác cancellation

- `future.get(50, MILLISECONDS)` timeout: **caller đã chờ đủ lâu**, Future không tự bị hủy.
- `future.orTimeout(50, MILLISECONDS)`: đối với CompletableFuture, nếu chưa completed đúng hạn thì **Future được complete exceptionally** với `TimeoutException`. Nó thay đổi trạng thái Future, không tự interrupt computation thực.
- `future.completeOnTimeout(value, 50, MILLISECONDS)`: nếu chưa completed, Future được complete normally bằng fallback value sau hạn; worker vẫn có thể chạy và side effect tiếp tục.
- `future.cancel(true)`: Future bị cancel theo semantics CompletableFuture; tham số `mayInterruptIfRunning` không dùng để điều khiển xử lý trong implementation này.

Sau một lần `orTimeout` đã làm Future completed exceptionally, `getNow(default)` sẽ **ném exception**, không tiếp tục trả default. Sau `completeOnTimeout`, `getNow(default)` đọc giá trị đã được complete từ timeout policy, không phải một “pending fallback” do chính getNow chọn.

### Ví dụ 11 — completeOnTimeout và getNow

Tạo `GetNowAfterCompleteOnTimeout.java` (Java 17+):

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

public class GetNowAfterCompleteOnTimeout {
    public static void main(String[] args) {
        CompletableFuture<String> future = new CompletableFuture<>();
        future.completeOnTimeout("TIMEOUT_VALUE",
                0, TimeUnit.MILLISECONDS);

        System.out.println("result = " + future.join());
        System.out.println("getNow = " + future.getNow("PENDING"));
        System.out.println("done = " + future.isDone());
    }
}
~~~

Chạy:

~~~bash
javac GetNowAfterCompleteOnTimeout.java
java GetNowAfterCompleteOnTimeout
~~~

Stdout sau khi timeout action hoàn tất:

~~~text
result = TIMEOUT_VALUE
getNow = TIMEOUT_VALUE
done = true
~~~

Timeout bằng 0 làm Future đủ điều kiện complete bằng `TIMEOUT_VALUE` ngay khi scheduler xử lý; `join` đợi completion ấy rồi `getNow` trả **giá trị đã được hoàn tất**. Không dựa vào thời điểm scheduler cụ thể, vì chỉ in sau `join`.

**Không hiểu nhầm:** `completeOnTimeout` trả chính CompletableFuture theo contract và có thể thay đổi Future ấy; việc này khác với truyền `"PENDING"` vào `getNow`, vốn không complete Future.

## 18. Khi nào cần snapshot trạng thái rõ hơn một giá trị?

Trong một số ứng dụng, API phía trên cần hiển thị một trong các trạng thái:

~~~text
PENDING
READY(value)
READY(null/no-value)
FAILED(cause)
CANCELLED
~~~

Đây là **state model nghiệp vụ**, rộng hơn một phép đọc `getNow(null)`. Có thể giải quyết qua một sealed interface/record immutable, ví dụ:

~~~java
// Snippet data model, không phải chương trình hoàn chỉnh.
sealed interface View<T>
        permits Pending, Ready, Failed, Cancelled {}
record Pending<T>() implements View<T> {}
record Ready<T>(T value) implements View<T> {}
record Failed<T>(Throwable cause) implements View<T> {}
record Cancelled<T>() implements View<T> {}
~~~

Các record thể hiện rõ `Ready(null)` khác `Pending`. Nếu một library cần phân biệt cẩn thận thông tin lỗi/timeout/cancellation, helper như `GetNowStatusView` có thể xây một record cụ thể thay vì String để caller không phải parse.

**Lưu ý:** Việc một UI tạo state object `Pending` sau phép đọc cũng không ngăn Future hoàn tất ngay sau đó. Snapshot là **ảnh tại thời điểm quan sát**, không phải lock giữ state bất động. Nếu phải thực hiện một quyết định nghiệp vụ không thể đảo ngược, cần thêm synchronization/protocol/idempotency ở tầng phù hợp.

## 19. Java Memory Model: khi Future completed, đọc result có an toàn không?

`CompletableFuture` là một cấu trúc đồng bộ thread-safe quản lý completion; giá trị được publish qua result completion có thể được đọc từ thread khác bằng các cơ chế của Future/CompletionStage. Trong mô hình producer–consumer thông thường, một thread tính result rồi `complete(value)`, thread khác đọc result sau khi Future completed.

Nhưng phải phân biệt **publication của result** với **mọi mutation tiếp theo**:

~~~java
// Snippet diễn giải vấn đề ownership.
List<String> mutable = new ArrayList<>();
mutable.add("A");
future.complete(mutable);

// Nếu producer tiếp tục mutable.add("B") trong khi consumer
// duyệt list qua getNow(), có thể xảy ra data race.
~~~

`ArrayList` không tự trở thành thread-safe chỉ vì reference được truyền qua CompletableFuture. Để tránh race, trả immutable list (ví dụ `List.copyOf(mutable)`), chuyển ownership và không sửa nữa, hoặc dùng synchronization đúng.

Tương tự, một Future đã completed normally với `null` không có gì “sai memory visibility”: đó là **giá trị kết quả theo thiết kế**, không phải read chưa nhìn thấy completion.

### Không tự suy luận từ biến thường

Nếu muốn dùng flag riêng:

~~~java
// Snippet nguy hiểm nếu không có proper synchronization.
boolean ready;
Object result;
~~~

Hai thread cập nhật/đọc chúng không khóa có thể có data race. Đừng thay `CompletableFuture` bằng hai biến không volatile/không synchronization chỉ vì muốn tránh `getNow`. Nếu xây result-state machine riêng, cần thread-safety và atomic publish đúng.

## 20. Error handling: không giấu lỗi bằng default

Một anti-pattern là gộp tất cả lỗi thành `null`:

~~~java
// MÃ SAI về ý nghĩa nghiệp vụ.
try {
    return future.getNow(null);
} catch (Exception ignored) {
    return null;
}
~~~

Caller sau đó không biết:
- Future pending?
- Future done-null?
- Storage lỗi?
- Cancellation?
- Timeout?
- Callback bị reject?

Các trạng thái có hậu quả rất khác nhau. Một màn hình có thể chấp nhận hiển thị loading nếu pending; nhưng storage error cần ghi log, metric, retry policy hoặc thông báo rõ. Cancellation có thể là do người dùng rời trang và không cần retry. Timeout có thể cần deadline/backoff, tránh retry storm.

### Cách bắt exception có chủ đích

~~~java
// Snippet, giả sử future kiểu CompletableFuture<String>.
try {
    String result = future.getNow("PENDING");
    // Cẩn trọng sentinel collision và giá trị thật null.
} catch (CancellationException cancelled) {
    // Báo trạng thái hủy theo protocol.
} catch (CompletionException failed) {
    Throwable cause = failed.getCause();
    // Phân loại lỗi tính toán, timeout hoặc I/O.
}
~~~

Không catch `Throwable` bừa bãi để coi mọi thứ là “không có giá trị”. Những `Error` nghiêm trọng có thể đòi hỏi escalation, không nên âm thầm nuốt.

## 21. Quy tắc chọn cách đọc kết quả

| Nhu cầu | Cách phù hợp |
| --- | --- |
| Muốn lấy giá trị nếu đã có, không chờ | `getNow(valueIfAbsent)` + sentinel/invariant + xử lý exceptions |
| Cần phân biệt pending và successful-null một cách rõ ràng | Result envelope, `Optional<T>` non-null contract, hoặc sentinel không va chạm |
| Chỉ cần flag “đã xong” tại thời điểm đọc | `isDone()`, không coi đó là success |
| Cần phân biệt failure và cancellation | `getNow`/`join` với `CompletionException`, `CancellationException` |
| Muốn đợi tới completion | `join()`/`get()`, hiểu blocking |
| Muốn chờ có hạn | `get(timeout, unit)`, xử lý timeout |
| Muốn xử lý khi result xuất hiện | `thenApply`/`thenAccept`/`whenComplete` và các biến thể Async |
| Muốn tự động complete Future khi quá hạn | `orTimeout`/`completeOnTimeout`, hiểu semantics và side effects |
| Muốn query kết quả của final pipeline | Giữ handle của **stage cuối** |
| Muốn dừng task thực tế | Cooperative cancellation/deadline, không chỉ `getNow` hay `cancel` |

## 22. Những hiểu nhầm thường gặp

| Hiểu nhầm | Sự thật |
| --- | --- |
| “`getNow(null)==null` nghĩa là pending.” | Có thể đã completed normally với null |
| “getNow trả fallback khi completed-null.” | Không. Nó trả null thật; fallback chỉ dùng nếu chưa completed |
| “`valueIfAbsent` cũng dùng khi Future lỗi.” | Không. Exceptional/cancelled completion có exception riêng |
| “isDone true nghĩa là thành công.” | Success, failure và cancellation đều done |
| “getNow luôn trả một T không null.” | Có thể trả null hoặc ném exception |
| “`getNow` khởi động computation.” | Không, chỉ đọc state result |
| “Gọi getNow nhiều lần sẽ làm Future hoàn tất.” | Không |
| “`getNow` có timeout ngầm.” | Không cần timeout vì bản thân không chờ result |
| “`get(timeout)` giống getNow.” | get(timeout) là timed blocking wait |
| “`join()` không block.” | Có thể đợi vô hạn nếu Future không complete |
| “Dùng string PENDING làm default luôn an toàn.” | Kết quả thật có thể trùng string ấy |
| “Lấy sentinel Object làm fallback cho CF<String>.” | Sai kiểu; không lách generics bằng raw casts |
| “Optional.empty là pending.” | Nếu Future<Optional<T>> completed normally với Optional.empty, nó là ready-without-value |
| “Future<Void>.getNow(null)==null nghĩa là finished.” | Pending cũng trả null |
| “isDone và getNow đọc cùng một snapshot.” | Có thể có completion giữa hai calls |
| “Cancel Future nghĩa worker chắc đã dừng.” | CompletableFuture cancel không ép interrupt computation |
| “Exceptionally completed thì getNow trả default.” | Nó thường ném CompletionException |
| “Bỏ qua tất cả exceptions và trả null là recovery.” | Che mất failure/cancel/timeout và gây sai logic |
| “getNow non-blocking thì mọi code bao quanh non-blocking.” | Argument evaluation, locks, callbacks có thể block |
| “Đã nhận result qua Future thì object mutable bên trong thread-safe.” | Publication khác với mutation đồng thời |
| “getNow trên source done nghĩa final pipeline done.” | Mỗi dependent stage có completion riêng |
| “Poll getNow vòng nóng không tốn tài nguyên.” | Busy-spinning có thể chiếm CPU |
| “completeOnTimeout chỉ là fallback tạm thời.” | Nó thực sự complete Future nếu chưa hoàn tất khi timeout |

## 23. Câu hỏi tự kiểm tra

**Câu 1.** Một `CompletableFuture<String>` đang pending. `getNow(null)` trả gì?  
**Đáp án:** `null` ngay, không block.

**Câu 2.** Future đã `complete(null)`. `getNow("WAIT")` trả gì?  
**Đáp án:** `null` thật, không trả `"WAIT"`.

**Câu 3.** Dùng `getNow("WAIT")=="WAIT"` làm bằng chứng chắc chắn pending có đúng không?  
**Đáp án:** Không nếu kết quả thật có thể bằng `"WAIT"`.

**Câu 4.** Vì sao không truyền `new Object()` vào `CompletableFuture<String>.getNow(...)`?  
**Đáp án:** Tham số phải là `String` theo generic type, không chấp nhận `Object`.

**Câu 5.** CompletableFuture đã completed exceptionally với `IllegalStateException`. `getNow("WAIT")` trả fallback không?  
**Đáp án:** Không. Nó ném `CompletionException` với cause tương ứng.

**Câu 6.** CompletableFuture đã `cancel(false)`. `getNow("WAIT")` thường làm gì?  
**Đáp án:** Ném `CancellationException`, không trả fallback.

**Câu 7.** `isDone()==true` có đủ khẳng định Future hoàn tất thành công không?  
**Đáp án:** Không. Failure/cancellation cũng được tính là done.

**Câu 8.** `getNow` có tác dụng hủy task đang chạy nếu caller không có result không?  
**Đáp án:** Không. Nó chỉ đọc state mà không chờ.

**Câu 9.** Một Future<Optional<String>> hoàn tất bình thường bằng `Optional.empty()`; `getNow(null)` trả gì?  
**Đáp án:** Trả `Optional.empty()`, không phải null, nếu contract đảm bảo producer không complete bằng null.

**Câu 10.** Khi `isDone()` trả false ở t1, có thể `getNow("WAIT")` ở t2 trả kết quả thật không?  
**Đáp án:** Có. Future có thể complete ở giữa hai calls.

**Câu 11.** `CompletableFuture<Void>` completed normally bằng null. `getNow(null)` có phân biệt được pending không?  
**Đáp án:** Không. Cần trạng thái khác, hoặc marker stage/result envelope.

**Câu 12.** `getNow(expensiveFallback())` có tránh gọi fallback nếu Future đã completed không?  
**Đáp án:** Không. Java đánh giá argument trước lời gọi method.

**Câu 13.** `Future.get(100, MILLISECONDS)` timeout có tự hủy Future không?  
**Đáp án:** Không. Chỉ giới hạn thời gian đợi của caller.

**Câu 14.** `completeOnTimeout("X", ...)` khác `getNow("X")` ở điểm nào?  
**Đáp án:** completeOnTimeout có thể **complete** Future bằng X khi hết hạn; getNow chỉ **trả tạm X** cho caller khi pending, không đổi Future.

**Câu 15.** Một source stage đã xong nhưng dependent async mapper đang đợi executor. `getNow` trên final stage trả gì?  
**Đáp án:** Nếu final stage chưa completed, nó trả fallback; completion của source không đồng nghĩa final done.

**Câu 16.** Có nên luôn thay `thenAccept` bằng polling getNow liên tục không?  
**Đáp án:** Không. Nếu cần phản ứng khi hoàn tất, callback/composition thường rõ hơn và không cần busy-spin.

**Câu 17.** Future completed với một `ArrayList`; producer tiếp tục sửa list sau complete. Queue/CompletableFuture đã làm các sửa đó thread-safe chưa?  
**Đáp án:** Chưa. Cần immutable result, ownership transfer hoặc synchronization cho mutation sau publication.

**Câu 18.** Nếu cần phân biệt `READY(null)`, `FAILED`, `CANCELLED` và `PENDING` cho UI, nên thiết kế gì?  
**Đáp án:** Kết quả dạng typed state/result envelope hoặc helper có sentinel không va chạm và error handling, không gộp tất cả vào null.

## Tài liệu tham khảo Java SE 17

- [`CompletableFuture` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `getNow(T valueIfAbsent)`, completion, cancellation, timeout APIs, exceptional completion, `isDone`.
- [`CompletionStage` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html): dependent stages và completion propagation.
- [`Future` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `get` và timed wait, `isDone`, `isCancelled`.
- [`CompletionException` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionException.html): unchecked wrapper cho lỗi completion.
- [`CancellationException` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CancellationException.html): Future cancellation.
- [`Optional` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html): biểu diễn giá trị nghiệp vụ có thể vắng mặt.
- [`CountDownLatch` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): điều phối test không phụ thuộc scheduling.
- [`ExecutorService` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): quản lý worker/shutdown trong ví dụ.
- [Java Language Specification `15.7 — Evaluation Order](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.7): thứ tự đánh giá method arguments.
- [Java Language Specification `17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): happens-before và memory visibility.

**Ghi nhớ:** `getNow(valueIfAbsent)` trả **giá trị dự phòng chỉ khi Future chưa completed**, trả **kết quả thật (kể cả null) khi thành công**, và **ném exception khi failed/cancelled**. Với domain có giá trị null hợp lệ, đừng dùng `getNow(null)==null` để kết luận pending; hãy dùng **sentinel không va chạm**, **Optional/result envelope non-null contract** hoặc **state classification** rõ ràng, đồng thời hiểu race giữa các lần đọc và không biến một phép đọc không chặn thành vòng busy-spin.