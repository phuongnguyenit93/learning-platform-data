# CompletableFuture: Khác biệt `get()` và `join()` khi xử lý lỗi

Trong Java, `CompletableFuture<T>` biểu diễn một kết quả có thể xuất hiện trong tương lai: hoàn thành bình thường với giá trị `T`, hoàn thành ngoại lệ (exceptional completion), hoặc bị hủy. Hai lời gọi `get()` và `join()` đều lấy kết quả cuối cùng và có thể **chờ** nếu future chưa hoàn thành. Điểm khác biệt quan trọng nhất khi xử lý lỗi là **kiểu ngoại lệ được ném ra cho bên gọi** và **cách xử lý ngắt luồng khi chờ**.

Bài này chỉ xét `java.util.concurrent.CompletableFuture` và các API concurrency của Java, không đi vào framework.

## 1. Bảng so sánh nhanh

| Tình huống | `get()` | `join()` |
|---|---|---|
| Hoàn thành thành công | Trả về `T` | Trả về `T` |
| Chưa hoàn thành | Chờ kết quả, có thể bị ngắt | Chờ kết quả, không kết thúc việc chờ chỉ vì bị ngắt |
| Future hoàn thành ngoại lệ thông thường | Ném `ExecutionException` (checked), `getCause()` thường là lỗi gốc | Ném `CompletionException` (unchecked), `getCause()` thường là lỗi gốc |
| Future bị hủy | Ném trực tiếp `CancellationException` (unchecked) | Ném trực tiếp `CancellationException` (unchecked) |
| Luồng đang chờ bị `interrupt()` | Có thể ném `InterruptedException` (checked) | Tiếp tục chờ và khôi phục cờ interrupted sau khi hoàn tất chờ |
| Chờ tối đa một khoảng thời gian | Có `get(timeout, unit)`, có thể ném trực tiếp `TimeoutException` (checked) | Không có overload nhận timeout |
| Yêu cầu khai báo `throws` hoặc `catch` checked exception | Có: `InterruptedException`, `ExecutionException`; bản timeout thêm `TimeoutException` | Không có checked exception trong chữ ký `join()` |

Các chữ ký liên quan:

```java
// Future<T>; CompletableFuture<T> implements Future<T>
T get() throws InterruptedException, ExecutionException;

T get(long timeout, TimeUnit unit)
    throws InterruptedException, ExecutionException, TimeoutException;

// CompletableFuture<T>
T join();
```

`ExecutionException` và `CompletionException` chủ yếu là **lớp vỏ báo lỗi bất đồng bộ**. Chúng cho biết thao tác chờ lấy kết quả thất bại; chi tiết nguyên nhân thường nằm ở `getCause()`. Không nên chỉ log tên lớp vỏ rồi bỏ qua nguyên nhân.

## 2. Vì sao cùng một future lại ném hai kiểu lỗi?

Một công việc bất đồng bộ có thể hoàn thành ngoại lệ vì hàm chạy bên trong ném lỗi, hoặc vì chương trình gọi `completeExceptionally(cause)`. CompletableFuture ghi nhận trạng thái thất bại ấy. `get()` và `join()` **không chạy lại công việc** và cũng không tạo hai lỗi độc lập: chúng chỉ diễn giải cùng trạng thái đã hoàn thành theo hợp đồng API khác nhau.

- `get()` kế thừa hợp đồng của `Future`. Vì `ExecutionException` là checked exception, mã gọi phải bắt hoặc khai báo ngoại lệ này; đồng thời phải xử lý `InterruptedException`.
- `join()` là API tiện dụng của `CompletableFuture`. Khi gặp thất bại thông thường, nó dùng `CompletionException`, một `RuntimeException`, nên phù hợp khi trả kết quả khỏi mã không muốn khai báo checked exception.
- Cả hai đều có thể ném `CancellationException` trực tiếp khi **chính future đang đợi** đã bị hủy. Đừng giả định mọi lỗi của `get()` là `ExecutionException` hoặc mọi lỗi của `join()` là `CompletionException`.

### Ví dụ hoàn chỉnh: cùng một lỗi, hai cách quan sát

Lưu nội dung sau thành `GetJoinErrorsDemo.java`:

```java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

public class GetJoinErrorsDemo {
    public static void main(String[] args) throws InterruptedException {
        CompletableFuture<String> failed =
                CompletableFuture.failedFuture(
                        new IllegalStateException("boom"));

        try {
            failed.get();
        } catch (ExecutionException e) {
            System.out.println("get(): " + e.getClass().getSimpleName()
                    + " -> " + e.getCause().getClass().getSimpleName()
                    + ": " + e.getCause().getMessage());
        }

        try {
            failed.join();
        } catch (CompletionException e) {
            System.out.println("join(): " + e.getClass().getSimpleName()
                    + " -> " + e.getCause().getClass().getSimpleName()
                    + ": " + e.getCause().getMessage());
        }

        CompletableFuture<String> cancelled = new CompletableFuture<>();
        cancelled.cancel(false);

        try {
            cancelled.get();
        } catch (CancellationException e) {
            System.out.println("get() cancelled: "
                    + e.getClass().getSimpleName());
        } catch (ExecutionException e) {
            throw new AssertionError("Unexpected wrapper", e);
        }

        try {
            cancelled.join();
        } catch (CancellationException e) {
            System.out.println("join() cancelled: "
                    + e.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy với Java 17+:

```bash
javac GetJoinErrorsDemo.java
java GetJoinErrorsDemo
```

Kết quả:

```text
get(): ExecutionException -> IllegalStateException: boom
join(): CompletionException -> IllegalStateException: boom
get() cancelled: CancellationException
join() cancelled: CancellationException
```

`CompletableFuture.failedFuture(...)` (có từ Java 9) tạo future đã thất bại, giúp ví dụ không phụ thuộc tốc độ của thread pool. Hai lần đọc `failed` cho thấy **nguyên nhân `IllegalStateException("boom")` giữ nguyên**, chỉ lớp vỏ phụ thuộc phương thức gọi. `cancel(false)` tạo trạng thái hủy; tham số `mayInterruptIfRunning` không khiến `CompletableFuture` cam kết ngắt công việc đang chạy.

## 3. Lấy đúng nguyên nhân lỗi và tránh bắt sai kiểu

Khi chủ động chờ bằng `get()`:

```java
try {
    String value = future.get();
    use(value);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Hoặc truyền tiếp InterruptedException nếu hợp đồng method cho phép.
    throw new IllegalStateException("Thread was interrupted", e);
} catch (ExecutionException e) {
    Throwable cause = e.getCause();
    reportFailure(cause);
} catch (CancellationException e) {
    reportCancellation(e);
}
```

Đoạn trên là **mẫu mã đặt trong một method đã có** các biến `future` và hàm `use`/`reportFailure`/`reportCancellation`; đây không phải chương trình độc lập. Đặt `CancellationException` ở nhánh riêng vì cancellation là trạng thái có ý nghĩa riêng.

Khi chủ động chờ bằng `join()`:

```java
try {
    String value = future.join();
    use(value);
} catch (CompletionException e) {
    reportFailure(e.getCause());
} catch (CancellationException e) {
    reportCancellation(e);
}
```

Nếu cần chuyển từ checked wrapper sang unchecked wrapper nhưng vẫn giữ nguyên nhân, ví dụ trong lớp adapter dùng `get()`, có thể viết `throw new CompletionException(e.getCause())` khi bắt `ExecutionException`. Cần đặt chính sách xử lý `InterruptedException` riêng; không gộp interruption với lỗi của công việc.

### Khi có nhiều lớp vỏ

Trong pipeline gồm nhiều stage, ngoại lệ có thể đã là `CompletionException` trước khi đến `get()`/`join()`. Nếu cần xác định lỗi nghiệp vụ cuối cùng, chỉ bóc các wrapper chuyên dùng cho kết quả bất đồng bộ:

```java
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

public final class FutureErrors {
    private FutureErrors() {}

    public static Throwable unwrap(Throwable error) {
        Throwable current = error;
        while ((current instanceof ExecutionException
                || current instanceof CompletionException)
                && current.getCause() != null) {
            current = current.getCause();
        }
        return current;
    }
}
```

Đây là lớp Java 17+ độc lập, có thể lưu thành `FutureErrors.java`. Vòng lặp dừng ở nguyên nhân không còn là hai loại wrapper trên, tránh tùy tiện bóc toàn bộ chuỗi `cause` của mọi ngoại lệ nghiệp vụ. Khi xử lý tại ranh giới ứng dụng, nên giữ cả wrapper và stack trace gốc trong log nếu chúng giúp xác định stage thất bại.

Một ngoại lệ được ném ra **trong tác vụ bất đồng bộ** có kiểu `InterruptedException` không đồng nghĩa `get()` bị interrupt khi đang chờ. Trường hợp đầu là lỗi của tác vụ, thường xuất hiện bên trong `ExecutionException` hoặc `CompletionException`; trường hợp sau là tín hiệu tác động đến chính luồng gọi `get()`.

## 4. Interruption: khác biệt về điều khiển luồng chờ

`get()` cung cấp thao tác chờ *interruptible*: khi thread đang chờ future chưa hoàn thành và một thread khác gọi `interrupt()` trên nó, `get()` có thể thoát bằng `InterruptedException`. Việc ném ngoại lệ này thường xóa cờ interrupted, vì vậy nếu mã đang bắt ngoại lệ nhưng không truyền tiếp, cách xử lý phổ biến là gọi `Thread.currentThread().interrupt()` để khôi phục tín hiệu cho lớp bên ngoài.

`join()` chờ theo cách *uninterruptible*: interrupt không làm `join()` thoát sớm bằng `InterruptedException`. Khi kết quả cuối cùng có sẵn, `join()` trả giá trị hoặc ném lỗi hoàn thành, và cờ interrupted vẫn được giữ/khôi phục để các tầng xử lý sau nhận biết. Điều này không có nghĩa thread hoặc công việc bất đồng bộ sẽ không bao giờ bị ảnh hưởng bởi các cơ chế hủy khác.

Lựa chọn thực tế:

- Luồng có vòng đời cần dừng khi bị ngắt (ví dụ worker đang thực hiện một tác vụ có thể hủy) thường phù hợp với `get()` và chính sách interruption rõ ràng.
- `join()` thuận tiện tại điểm tập hợp kết quả khi chủ đích là đợi đến lúc future hoàn thành, nhưng không thích hợp để thay thế cơ chế cancellation/interrupt của ứng dụng.
- Không nên gọi `Thread.interrupted()` chỉ để “xóa cờ” sau `join()`: lệnh này đọc **và xóa** trạng thái interrupted, có thể đánh mất tín hiệu của tầng khác.

**Lưu ý race:** nếu future đã có kết quả ngay tại thời điểm gọi, đường đi nhanh của `get()` có thể trả kết quả trước khi kiểm tra interrupt. Không dựa vào một ví dụ chạy đua giữa `complete()` và `interrupt()` để khẳng định thứ tự tuyệt đối; hợp đồng quan trọng là `get()` hỗ trợ chờ có thể ngắt còn `join()` không ném `InterruptedException`.

## 5. Timeout: lỗi chờ và lỗi hoàn thành không giống nhau

Có **hai loại timeout khác nhau**:

1. **Timeout của người đang đợi:** `future.get(200, TimeUnit.MILLISECONDS)` chờ tối đa khoảng thời gian chỉ định. Nếu chưa có kết quả, nó ném trực tiếp `TimeoutException`. Future **không tự động** bị đánh dấu thất bại hoặc hủy chỉ vì người gọi dừng chờ.
2. **Timeout của chính CompletableFuture:** `future.orTimeout(200, TimeUnit.MILLISECONDS)` (Java 9+) sắp xếp để future hoàn thành ngoại lệ bằng `TimeoutException` nếu thời hạn đến trước khi nó hoàn thành. Sau đó `get()` có thể ném `ExecutionException` với cause `TimeoutException`; `join()` có thể ném `CompletionException` với cause `TimeoutException`.

Hai dạng này có cơ chế và phạm vi ảnh hưởng khác nhau. Ví dụ chạy độc lập:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class WaitTimeoutDemo {
    public static void main(String[] args)
            throws InterruptedException, ExecutionException {
        CompletableFuture<String> pending = new CompletableFuture<>();

        try {
            pending.get(20, TimeUnit.MILLISECONDS);
        } catch (TimeoutException e) {
            System.out.println("Wait timed out");
        }

        System.out.println("Future done: " + pending.isDone());
        pending.complete("ready");
        System.out.println("Later result: " + pending.join());
    }
}
```

Lưu thành `WaitTimeoutDemo.java` và chạy:

```bash
javac WaitTimeoutDemo.java
java WaitTimeoutDemo
```

Kết quả:

```text
Wait timed out
Future done: false
Later result: ready
```

Không có thread nào gọi `complete()` trước khi chờ, nên timeout tại `get(20, ...)` sẽ xảy ra; sau đó `pending` vẫn chưa hoàn thành. Mốc 20 ms là thời gian chờ tối đa mang tính tương đối, không phải thời điểm chính xác đến từng mili giây.

Với `join()`, không có `join(timeout, unit)`. Nếu cần **chính future** thất bại khi quá hạn:

```java
CompletableFuture<String> bounded =
        new CompletableFuture<String>()
                .orTimeout(200, TimeUnit.MILLISECONDS);

try {
    bounded.join();
} catch (CompletionException e) {
    if (e.getCause() instanceof TimeoutException) {
        // Future đã hoàn thành ngoại lệ vì hết hạn.
    } else {
        throw e;
    }
}
```

Đây là đoạn mã bên trong một method đã import các lớp ở `java.util.concurrent`. `orTimeout` trả về **chính future đang cấu hình**; các stage khác đang phụ thuộc vào nó cũng có thể thấy trạng thái lỗi. Nếu muốn hết thời gian thì dùng giá trị mặc định thay vì lỗi, xem `completeOnTimeout(defaultValue, timeout, unit)`; phương thức đó hoàn thành bình thường bằng fallback nếu hết hạn trước.

## 6. Xử lý lỗi trong pipeline trước khi gọi get/join

`get()`/`join()` chỉ quan sát **trạng thái của future cuối cùng**. Nếu pipeline đã khôi phục lỗi, cả hai sẽ trả kết quả bình thường. Thường nên xử lý bất đồng bộ bằng các stage thay vì chờ từng stage:

| Stage | Khi nào chạy? | Tác dụng lên kết quả |
|---|---|---|
| `exceptionally(fn)` | Chỉ khi stage trước hoàn thành ngoại lệ | Trả giá trị thay thế để khôi phục; nếu handler lại ném lỗi, stage sau tiếp tục thất bại |
| `handle((value, error) -> ...)` | Cả thành công và thất bại | Biến đổi kết quả hoặc phục hồi theo cả hai nhánh |
| `whenComplete((value, error) -> ...)` | Cả thành công và thất bại | Chủ yếu quan sát/log; không tự biến lỗi thành thành công bằng giá trị trả về (callback không có kết quả) |
| `exceptionallyCompose(fn)` | Khi thất bại; có từ Java 12 | Khôi phục bằng **một CompletionStage bất đồng bộ khác** |

Ví dụ chạy được trên Java 17+:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class FutureRecoveryDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> original =
                CompletableFuture.failedFuture(
                        new IllegalArgumentException("invalid input"));

        CompletableFuture<Integer> recovered = original
                .exceptionally(error -> {
                    System.out.println("Recover: "
                            + error.getClass().getSimpleName());
                    return 42;
                });

        System.out.println("Recovered value: " + recovered.join());

        try {
            original.join();
        } catch (CompletionException e) {
            System.out.println("Original still failed: "
                    + e.getCause().getClass().getSimpleName());
        }
    }
}
```

Lưu thành `FutureRecoveryDemo.java`; biên dịch/chạy:

```bash
javac FutureRecoveryDemo.java
java FutureRecoveryDemo
```

Kết quả:

```text
Recover: IllegalArgumentException
Recovered value: 42
Original still failed: IllegalArgumentException
```

`exceptionally` tạo **future mới** với giá trị `42` khi nhánh gốc thất bại; nó không sửa trạng thái `original`. Trong các tổ hợp phức tạp, đối số `error` có thể đã được bọc bởi `CompletionException`, vì vậy nếu phân loại theo nguyên nhân thì hãy xử lý wrapper trước.

Điểm rất dễ nhầm: `whenComplete((v, e) -> log(e))` **không** phải recovery. Nếu input thất bại và callback chỉ log, future sau `whenComplete` vẫn thất bại; cuối pipeline gọi `join()` vẫn có thể ném `CompletionException`. Muốn tạo giá trị thay thế thì dùng `exceptionally` hoặc `handle`.

## 7. Cancellation và lỗi lan qua stage phụ thuộc

Một future có thể bị hủy bằng `cancel(...)`; đối với `CompletableFuture`, đây là một dạng hoàn thành ngoại lệ. Khi trực tiếp đọc đúng đối tượng đã bị hủy, cả `get()` lẫn `join()` ném `CancellationException`. Tuy nhiên, **stage phụ thuộc** tạo bởi `thenApply`, `thenCompose`, ... có thể hoàn thành ngoại lệ với `CompletionException` chứa `CancellationException` làm nguyên nhân.

Ví dụ ngữ nghĩa:

```java
CompletableFuture<String> parent = new CompletableFuture<>();
CompletableFuture<Integer> child = parent.thenApply(String::length);
parent.cancel(true);

// parent.join(): CancellationException trực tiếp.
// child.join(): có thể ném CompletionException,
//               nguyên nhân là CancellationException.
```

Đừng dùng duy nhất loại exception bên ngoài để kết luận “đây là lỗi nghiệp vụ” hay “đây là hủy tác vụ”; hãy kiểm tra trạng thái `isCancelled()` của future đang xét và nguyên nhân thực tế khi cần.

`cancel(true)` với `CompletableFuture` **không bảo đảm interrupt thread đang thực thi tác vụ**; theo hợp đồng của lớp này, tham số `mayInterruptIfRunning` không điều khiển xử lý vì interrupt không được dùng để quản lý việc thực thi bên trong. Tác vụ có thể tiếp tục chạy dù future đã ở trạng thái canceled. Cơ chế dừng thật sự cần được thiết kế riêng nếu công việc có tài nguyên hoặc tác dụng phụ.

## 8. Chọn get() hay join() trong mã thật?

- **Chọn `get()`** nếu đang tích hợp API `Future`, cần timeout **chỉ cho lần chờ của caller**, hoặc cần cho phép luồng đợi phản ứng với `InterruptedException`.
- **Chọn `join()`** nếu code đang làm việc trực tiếp với `CompletableFuture` và muốn lấy kết quả ở một ranh giới đồng bộ mà không buộc khai báo checked exception; vẫn phải có chiến lược xử lý `CompletionException`/`CancellationException` khi thất bại có thể xảy ra.
- **Ưu tiên kết hợp stage** (`thenApply`, `thenCompose`, `handle`, `exceptionally`) nếu có thể giữ pipeline bất đồng bộ. Chờ ngay giữa chuỗi dễ làm mất lợi thế non-blocking và, trong executor ít thread, có thể gây starvation hoặc deadlock do các công việc chờ nhau.
- Khi thực sự cần gom nhiều future, có thể dùng `CompletableFuture.allOf(...).join()` tại ranh giới chờ. Nó **không** cung cấp báo cáo đầy đủ từng lỗi một cách tự động: nếu cần phân tích từng tác vụ, phải kiểm tra từng future và xây dựng chính sách tổng hợp.

**Các lỗi phổ biến cần tránh:**

1. `catch (ExecutionException)` cho `join()` hoặc `catch (CompletionException)` cho `get()` rồi tưởng mọi nhánh thất bại được bao phủ. Hãy bắt đúng hợp đồng API và nhớ `CancellationException`.
2. Chỉ log `e.toString()` của wrapper rồi bỏ qua `e.getCause()`, làm mất ngữ cảnh lỗi thật.
3. Nuốt `InterruptedException` mà không truyền tiếp hoặc khôi phục cờ interrupt, khiến cơ chế dừng thread khó hoạt động đúng.
4. Coi `get(timeout, unit)` là lệnh hủy tác vụ; thao tác này mặc định chỉ giới hạn **lần chờ**.
5. Coi `whenComplete` là xử lý phục hồi hoặc dùng `exceptionally` trả về `null` mà không xét hợp đồng dữ liệu của các stage sau.
6. Bắt mọi `RuntimeException` rồi âm thầm trả fallback, che lấp lỗi lập trình nghiêm trọng và trạng thái hủy.
7. Dùng `join()` bên trong các stage chạy trên cùng một executor nhỏ để đợi một tác vụ cũng cần executor đó; có thể tạo vòng chờ làm pipeline không tiến triển.

## 9. Checklist xử lý lỗi

Trước khi chọn phương thức lấy kết quả, hãy xác định: **(1)** lỗi hoàn thành tác vụ cần được bọc bằng checked hay unchecked exception; **(2)** thread đợi có phải phản ứng với interrupt không; **(3)** giới hạn thời gian áp dụng cho người đợi hay cho bản thân future; **(4)** hủy có được xử lý riêng không; **(5)** recovery có thể thực hiện bằng stage trước khi chờ không.

Với cùng một future thất bại thông thường: **`get()` → `ExecutionException` → cause**, còn **`join()` → `CompletionException` → cause**. Riêng cancellation có đường ném `CancellationException` trực tiếp, còn interrupt và timeout là các điều kiện cần xét theo phương thức chờ. Hiểu rõ ba trường hợp này giúp mã Java giữ đúng nguyên nhân lỗi, có chính sách hủy rõ ràng và không vô tình chặn các luồng xử lý bất đồng bộ.
