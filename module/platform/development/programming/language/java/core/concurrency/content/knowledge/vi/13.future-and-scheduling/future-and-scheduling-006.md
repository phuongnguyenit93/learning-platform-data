# invokeAll() cho nhóm kết quả trong Java ExecutorService

## 1. Mục tiêu: gửi một nhóm tác vụ và nhận đủ các Future

Khi có nhiều công việc độc lập, ví dụ tính giá của một nhóm sản phẩm hoặc tổng hợp nhiều mảnh dữ liệu, việc tự tạo một thread cho từng việc vừa khó quản lý vừa dễ vượt quá tài nguyên. `ExecutorService` cho phép nộp nhiều `Callable` vào một pool rồi quản lý kết quả bằng `Future`.

**`invokeAll()`** là API dành cho một **nhóm task**: executor gửi các task để thực thi, **chờ đến khi tất cả hoàn tất** (hoặc đến hạn nếu dùng phiên bản timeout), rồi trả về một `List<Future<T>>`. Mỗi `Future` đại diện cho kết quả hoặc trạng thái thất bại/hủy của **một task tương ứng**.

Điểm khác với gọi `submit()` trong một vòng lặp: `invokeAll()` gom bước submit + chờ nhóm vào một lời gọi, có phiên bản áp dụng **một ngân sách timeout chung** cho toàn nhóm. Nhưng:

- `invokeAll()` **không** đồng nghĩa mọi task đều **thành công**.
- `invokeAll()` **không** trả trực tiếp một `List<T>`; nó trả `List<Future<T>>`, caller vẫn phải xử lý `get()` từng phần tử.
- `invokeAll()` **không** cam kết thứ tự **bắt đầu** hay **kết thúc** task.
- Danh sách Future trả về **theo thứ tự tương ứng của các task trong collection được truyền vào theo thứ tự iterator**, không theo thứ tự hoàn tất. Với `List.of(...)`, thứ tự đó là thứ tự các phần tử trong List.
- Nếu dùng `invokeAll(tasks, timeout, unit)`, những task chưa hoàn tất khi hết hạn sẽ được **yêu cầu hủy**; việc chấm dứt thân task phụ thuộc khả năng hợp tác với interrupt.
- Đây là concurrency ở **Java/JDK nói chung**; không phụ thuộc framework.

## 2. API và ý nghĩa hai overload

`ExecutorService` khai báo hai dạng thường dùng:

```java
<T> List<Future<T>> invokeAll(
        Collection<? extends Callable<T>> tasks)
        throws InterruptedException;

<T> List<Future<T>> invokeAll(
        Collection<? extends Callable<T>> tasks,
        long timeout,
        TimeUnit unit)
        throws InterruptedException;
```

Đoạn trên là **chữ ký phương thức rút gọn từ API**, không phải một file Java chạy độc lập.

| Dạng | Khi nào trả về bình thường? | Trạng thái Future được trả về |
| --- | --- | --- |
| `invokeAll(tasks)` | Sau khi **tất cả task hoàn tất**, bất kể kết quả thành công hay ném lỗi | Các Future đã hoàn tất; `get()` trả giá trị hoặc báo lỗi/hủy |
| `invokeAll(tasks, timeout, unit)` | Khi tất cả đã hoàn tất **hoặc** ngân sách chờ hết | Các Future đã hoàn tất hoặc bị hủy; task còn dở được yêu cầu hủy |

**Lưu ý về checked exceptions:** hai overload khai báo `InterruptedException` khi thread **đang gọi invokeAll** bị interrupt trong lúc chờ. Phiên bản có timeout **không ném `TimeoutException` cho caller** khi hết hạn; nó trả danh sách `Future` sau khi xử lý cancellation cho những task chưa hoàn tất. Phải đọc `future.isCancelled()` hoặc xử lý `CancellationException` khi lấy kết quả.

Một `Callable<T>` có thể trả `T` hoặc ném `Exception`. Việc một Callable ném lỗi **không làm `invokeAll` lập tức ném exception của Callable**; lỗi được lưu trong Future tương ứng và xuất hiện qua `get()` dưới dạng `ExecutionException`.

### Hình dung vòng đời

```text
List<Callable<T>> input
         |
         v
ExecutorService.invokeAll(...)
         |
         +--> Callable A --> Future A
         +--> Callable B --> Future B
         +--> Callable C --> Future C
         |
         v
Chờ đến khi cả nhóm xong hoặc deadline hết
         |
         v
List<Future<T>> theo thứ tự A, B, C
         |
         +--> get() thành công -> giá trị T
         +--> get() thất bại  -> ExecutionException
         +--> get() bị hủy   -> CancellationException
```

**Thứ tự danh sách là thứ tự ánh xạ task → Future**. Task B có thể hoàn tất trước A, nhưng `futures.get(0)` vẫn tương ứng với task A.

## 3. Ví dụ Java 17+: chạy ba phép tính và tổng hợp kết quả

Tạo file `InvokeAllBasic.java`:

```java
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class InvokeAllBasic {
    public static void main(String[] args)
            throws InterruptedException, ExecutionException {
        ExecutorService pool = Executors.newFixedThreadPool(3);
        try {
            List<Callable<Integer>> tasks = List.of(
                    () -> 2 * 2,
                    () -> 3 * 3,
                    () -> 4 * 4
            );

            List<Future<Integer>> futures = pool.invokeAll(tasks);
            int total = 0;
            for (Future<Integer> future : futures) {
                total += future.get();
            }

            System.out.println("Future count: " + futures.size());
            System.out.println("Sum: " + total);
        } finally {
            pool.shutdown();
        }
    }
}
```

Biên dịch/chạy:

```bash
javac InvokeAllBasic.java
java InvokeAllBasic
```

Đầu ra:

```text
Future count: 3
Sum: 29
```

Giải thích:

1. `Executors.newFixedThreadPool(3)` dùng tối đa ba worker chạy task đồng thời; số core và scheduling thực tế do JVM/hệ điều hành quyết định.
2. `List.of(...)` giữ thứ tự rõ ràng của ba Callable.
3. `invokeAll(tasks)` chờ cả ba task hoàn tất bình thường; danh sách Future có ba vị trí tương ứng.
4. Vì các task chỉ tính số và không ném lỗi, `future.get()` lần lượt trả 4, 9, 16; tổng luôn là 29, **không phụ thuộc thứ tự task hoàn tất**.
5. `finally` gọi `shutdown()` để executor không tiếp nhận task mới. Với ứng dụng lâu dài, cần quản lý vòng đời executor ở tầng sở hữu, không tạo pool không shutdown cho mỗi lần gọi nghiệp vụ.

Trong ví dụ này `main` không cần `awaitTermination()` để nhìn thấy ba kết quả: `invokeAll` đã đợi các task trong nhóm hoàn tất, và `get()` xác nhận từng kết quả. `shutdown()` vẫn cần thiết để đóng vòng đời worker sau cùng.

## 4. Thứ tự Future khác thứ tự hoàn tất

Ta có thể **cố ý buộc task thứ hai hoàn tất trước task thứ nhất** và quan sát thứ tự List không đổi.

Tạo file `InvokeAllOrdering.java`:

```java
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class InvokeAllOrdering {
    public static void main(String[] args) throws Exception {
        CountDownLatch secondFinished = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            List<Callable<String>> tasks = List.of(
                    () -> {
                        secondFinished.await();
                        return "first";
                    },
                    () -> {
                        secondFinished.countDown();
                        return "second";
                    }
            );

            List<Future<String>> results = pool.invokeAll(tasks);
            System.out.println("Index 0: " + results.get(0).get());
            System.out.println("Index 1: " + results.get(1).get());
        } finally {
            pool.shutdown();
        }
    }
}
```

Biên dịch/chạy:

```bash
javac InvokeAllOrdering.java
java InvokeAllOrdering
```

Đầu ra:

```text
Index 0: first
Index 1: second
```

Vì pool có hai worker, task thứ hai có cơ hội chạy và gọi `countDown()`, cho phép task thứ nhất rời `await()`. **Task thứ nhất không thể hoàn tất trước khi task thứ hai gọi `countDown()`**, nhưng không cần đoán chính xác thứ tự các câu lệnh sau tín hiệu; hai giá trị được ánh xạ theo **vị trí đầu vào**. Nếu pool chỉ có **một worker** và task thứ nhất chờ một task thứ hai **đang nằm trong hàng đợi cùng pool**, chương trình có thể tự tạo **thread starvation deadlock**. Vì vậy cần hiểu quan hệ phụ thuộc giữa các task, không chỉ số lượng Future.

**Khi cần xử lý kết quả ngay khi từng task hoàn tất**, đừng dùng thứ tự List như một completion queue. `ExecutorCompletionService` hoặc thiết kế callback/`CompletableFuture` phù hợp hơn.

## 5. Xử lý lỗi từng Callable: invokeAll không phải fail-fast

Một task trong nhóm có thể thất bại nhưng nhóm vẫn có những kết quả hợp lệ khác. `invokeAll` **chờ tất cả task hoàn tất** theo overload không timeout; nó không tự dừng mọi việc khi thấy một Future chứa exception.

Tạo file `InvokeAllFailures.java`:

```java
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class InvokeAllFailures {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            List<Callable<String>> tasks = List.of(
                    () -> "ok-A",
                    () -> {
                        throw new IllegalArgumentException("bad input");
                    },
                    () -> "ok-C"
            );

            List<Future<String>> futures = pool.invokeAll(tasks);

            for (int index = 0; index < futures.size(); index++) {
                try {
                    System.out.println(index + ": "
                            + futures.get(index).get());
                } catch (ExecutionException e) {
                    System.out.println(index + ": ERROR "
                            + e.getCause().getClass().getSimpleName());
                }
            }
        } finally {
            pool.shutdown();
        }
    }
}
```

Chạy:

```bash
javac InvokeAllFailures.java
java InvokeAllFailures
```

Đầu ra:

```text
0: ok-A
1: ERROR IllegalArgumentException
2: ok-C
```

Phân tích:

- `invokeAll` trả về một Future cho **mỗi** Callable theo thứ tự List.
- Task ở index 1 ném `IllegalArgumentException`. Khi gọi `get()` của Future đó, caller nhận `ExecutionException`; nguyên nhân là exception gốc.
- Hai task còn lại đã hoàn tất bình thường, vẫn lấy được kết quả.
- Nếu caller chỉ duyệt một phần danh sách, lỗi ở Future không được gọi `get()` có thể bị bỏ sót ở tầng tổng hợp. Vì vậy khi cần báo cáo đầy đủ, phải kiểm tra từng Future.
- Đừng bắt `ExecutionException` quanh `invokeAll(tasks)` vì đây **không phải** checked exception mà lời gọi `invokeAll` khai báo; hãy bắt khi gọi `future.get()`.

**Chính sách xử lý khi có lỗi:** nếu bắt buộc **tất cả phần** phải thành công, có thể gom lỗi rồi đánh dấu toàn batch thất bại; nếu cho phép kết quả từng phần, báo rõ phần thành công và phần thất bại. Đây là quyết định nghiệp vụ, không phải semantics tự động của `invokeAll`.

## 6. Dùng timeout cho **toàn nhóm** và hủy phần chưa hoàn tất

Overload có hạn thời gian:

```java
List<Future<Result>> results =
        pool.invokeAll(tasks, 500, TimeUnit.MILLISECONDS);
```

Đây là snippet; `Result`, `pool` và `tasks` phải được khai báo. Thời gian 500 ms là một **ngân sách chung** cho lời gọi, **không phải 500 ms riêng từng task**. Khi hết thời gian, những task chưa hoàn tất bị **cancel** theo hợp đồng; nó không bảo đảm mã task thực sự ngừng ngay nếu đang trong một đoạn không hợp tác với interrupt.

### Java 17+: tạo timeout có kiểm soát mà không dựa vào sleep

Tạo file `InvokeAllTimeout.java`:

```java
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class InvokeAllTimeout {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch gate = new CountDownLatch(1);

        try {
            List<Callable<String>> tasks = List.of(
                    () -> {
                        gate.await();
                        return "A";
                    },
                    () -> {
                        gate.await();
                        return "B";
                    }
            );

            List<Future<String>> results =
                    pool.invokeAll(tasks, 50, TimeUnit.MILLISECONDS);

            long cancelled = results.stream()
                    .filter(Future::isCancelled)
                    .count();

            System.out.println("Future count: " + results.size());
            System.out.println("Cancelled on timeout: " + cancelled);
        } finally {
            gate.countDown();
            pool.shutdownNow();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac InvokeAllTimeout.java
java InvokeAllTimeout
```

Đầu ra khi không có interrupt ngoài:

```text
Future count: 2
Cancelled on timeout: 2
```

**Vì sao hai Future đều bị hủy?** Trong thời gian `invokeAll` đang chờ, `gate` chưa thể được mở bởi main (main còn ở trong chính lời gọi). Task đã chạy thì mắc ở `gate.await()`, task chưa chạy thì vẫn chưa thể tự trả kết quả. Khi timeout, `invokeAll` yêu cầu hủy các Future chưa xong. `gate.countDown()` trong `finally` đảm bảo không cố ý giữ cổng đóng khi chương trình rời phạm vi ví dụ.

Các task bị hủy có thể nhận interrupt tại `await()`, nhưng điều quan trọng của `isCancelled()` là **trạng thái Future**, không phải lời chứng minh rằng mọi thread đã ngừng trước thời điểm phương thức trả về. Trong thực tế còn có side effect, I/O hoặc đoạn CPU không kiểm tra interrupt; chúng cần giao thức hủy và cleanup phù hợp.

**Không dùng `Future.get()` trên các phần tử này với kỳ vọng nhận kết quả bình thường:** Future đã cancelled sẽ ném `CancellationException`. Nếu vẫn cần giá trị thay thế, phải định nghĩa default hoặc retry theo nghiệp vụ.

### Nếu task hoàn tất sát deadline thì sao?

Kết quả có thể nằm ở ranh giới: một task đã hoàn thành trước khi việc cancel được áp dụng có thể có `isCancelled() == false` và chứa giá trị/exception; task chưa xong bị yêu cầu hủy. Đừng suy từ thời gian gần deadline để khẳng định một task cụ thể chắc chắn bị hủy. Chương trình ví dụ dùng latch đóng để loại trừ khả năng task hoàn tất bình thường trước timeout.

### Timeout không phải giới hạn tuyệt đối của toàn bộ workflow

`invokeAll(..., timeout, unit)` giới hạn nỗ lực chờ **nhóm task** theo hợp đồng API. Việc thu thập kết quả, serialize dữ liệu, ghi file hay gọi dịch vụ bên ngoài sau đó có thể tiếp tục tốn thời gian. Scheduling và cancellation cleanup cũng có thể ảnh hưởng độ trễ thực tế. Khi cần deadline cuối-đến-cuối, dùng một ngân sách thời gian chung và truyền **thời gian còn lại** cho từng bước hỗ trợ timeout.

## 7. Interrupt của caller trong lúc invokeAll

`invokeAll` là một **phương thức blocking interruptible**. Nếu thread đang chờ nhóm Future bị interrupt, nó có thể ném `InterruptedException` và các task chưa hoàn tất được yêu cầu hủy theo hợp đồng.

Có hai tầng riêng biệt:

1. **Caller thread**: thread gọi `invokeAll` đang chờ, có thể nhận `InterruptedException`.
2. **Worker threads**: đang chạy `Callable` trong executor, có thể nhận yêu cầu interrupt khi task bị cancel.

`InterruptedException` ở caller **không đồng nghĩa** mọi worker đã dừng hoặc mọi tài nguyên đã rollback. Task đang làm CPU lâu có thể cần kiểm tra `Thread.currentThread().isInterrupted()`; I/O có thể có semantics interrupt/close khác nhau; một số critical section cần kết thúc bước cập nhật rồi mới hợp tác hủy.

### Mẫu xử lý đúng khi caller nhận interrupt

```java
// Snippet: pool và tasks đã được tạo, phương thức bao quanh
// không khai báo throws InterruptedException.
try {
    List<Future<Integer>> futures = pool.invokeAll(tasks);
    consumeResults(futures);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
```

Đoạn trên là **snippet**, `consumeResults` và biến xung quanh chưa được khai báo. Khi bắt `InterruptedException` mà không truyền tiếp, khôi phục cờ bằng `Thread.currentThread().interrupt()` để tầng gọi có thể biết yêu cầu dừng. Nếu phương thức cho phép `throws InterruptedException`, truyền thẳng ngoại lệ thường đơn giản hơn.

**Không nên** nuốt `InterruptedException` rồi lập tức lặp lại `invokeAll` vô hạn. Điều đó có thể tạo công việc trùng, làm hỏng chính sách shutdown và khiến hệ thống khó hủy.

## 8. Task có phụ thuộc nhau: nguy cơ thread starvation deadlock

`invokeAll` phù hợp nhất với những task có thể chạy độc lập hoặc có giao thức phụ thuộc được thiết kế kỹ. Một lỗi phổ biến là task A đang chạy trong pool nhỏ, rồi **chờ task B cũng phải được chính pool đó chạy**.

Ví dụ nguy hiểm, chỉ mô tả ý tưởng:

```text
Pool có 1 worker:
  Worker nhận task A
  A đợi kết quả task B
  B đang trong queue của cùng pool
  Không worker nào rảnh để thực thi B
```

`invokeAll` ở caller có thể chờ vĩnh viễn nếu không có timeout hoặc cách giải phóng phụ thuộc. Lỗi nằm ở **thiết kế quan hệ chờ**, không phải ở `invokeAll` tự nó.

Cách phòng tránh:

- Không cho task đang chiếm toàn bộ worker chờ một task khác chỉ có thể chạy trên chính pool đó.
- Nếu phải phân pha, tách công việc, dùng dependency graph hoặc `CompletableFuture` mà không chặn worker một cách không cần thiết.
- Chọn pool size và queue policy theo workload, nhưng **tăng số thread không phải bản sửa nền tảng** cho một chu trình phụ thuộc.
- Dùng timeout và log/metrics để phát hiện, không chỉ dựa vào deadlock detector cho monitor: thread starvation deadlock không nhất thiết là monitor deadlock.

Ví dụ `InvokeAllOrdering` dùng **hai worker** nhằm cho phép task thứ hai mở latch của task thứ nhất, tránh tự chặn.

## 9. invokeAll() khác submit(), invokeAny() và CompletionService

| API | Lúc nào caller có thể nhận thông tin? | Thứ tự / kết quả |
| --- | --- | --- |
| `submit(task)` | `submit` thường trả Future ngay; caller chọn lúc `get()` | Một Future cho một task; không chờ ngay tại `submit` |
| `invokeAll(tasks)` | Trả sau khi cả nhóm hoàn tất | List Future theo thứ tự task đầu vào |
| `invokeAll(tasks, timeout, unit)` | Trả khi hoàn tất toàn nhóm hoặc timeout | List Future theo thứ tự đầu vào; phần chưa xong bị cancel |
| `invokeAny(tasks)` | Trả một kết quả thành công theo hợp đồng | Trả **một giá trị T**, không phải List Future; các task khác được yêu cầu hủy |
| `ExecutorCompletionService` | Caller có thể `take()/poll()` từng Future khi chúng hoàn tất | Thứ tự **hoàn tất**, không phải thứ tự nộp |
| `CompletableFuture.allOf(...)` | Một future tổng báo khi tất cả future thành phần hoàn tất | Không tự tạo List kết quả typed; cần truy xuất từng future |

### Khi nào dùng `invokeAny`?

Nếu chỉ cần **một kết quả thành công** từ nhiều nguồn (ví dụ hỏi nhiều máy chủ tương đương và dùng phản hồi hợp lệ đầu tiên), `invokeAny` có thể phù hợp hơn. Nó có thể bỏ qua task thất bại để chờ task khác thành công; nếu không có task nào thành công, sẽ báo lỗi theo hợp đồng. Nó không nhằm tập hợp mọi kết quả.

**Không dùng `invokeAny` để thay thế một batch mà mọi phần đều phải hoàn tất.** Còn nếu yêu cầu là cập nhật giao diện ngay khi từng kết quả sẵn sàng, `ExecutorCompletionService` thường tự nhiên hơn `invokeAll`.

### `CompletableFuture.allOf` và `invokeAll`

`CompletableFuture.allOf(f1, f2, ...)` tạo một `CompletableFuture<Void>` báo hiệu cả nhóm đã hoàn tất. Nó hỗ trợ composition không nhất thiết chặn thread caller cho tới khi gọi `join/get`, nhưng **không tự cung cấp một `List<T>`** và không tự biến nhiều task thành transaction. Mô hình cancellation/timeout của các future thành phần cũng cần xem xét riêng.

`invokeAll` đơn giản hơn khi code đồng bộ muốn nộp một Collection Callable, chờ một lần và gom các Future theo cùng thứ tự.

## 10. Tính đúng đắn dữ liệu và giới hạn của “batch”

`invokeAll` không làm các task chạy theo một transaction, không bảo đảm tất cả dùng chung một snapshot dữ liệu và không tự tạo một lock cho các cấu trúc mutable mà các task cùng truy cập.

Ví dụ nếu mọi Callable cùng `counter++` trên một trường thường, kết quả vẫn có thể sai vì data race/lost update. Pool và Future chỉ quản lý **thực thi và kết quả task**, không thay `AtomicInteger`, `synchronized` hoặc các cơ chế bảo vệ state.

### Memory visibility khi dùng Future

Hợp đồng memory-consistency của `java.util.concurrent` cho `ExecutorService`/`Future` có các quan hệ hữu ích:

- Các hành động của thread **trước khi submit một task** happens-before các hành động trong task theo hợp đồng executor.
- Các hành động của task happens-before những hành động **sau khi caller lấy được kết quả bằng `Future.get()`**.

Vì thế việc đọc kết quả qua `get()` giúp công bố hiệu ứng của task theo giao thức. Nhưng không nên suy rằng **hai task khác nhau** có thứ tự lẫn nhau chỉ vì chúng cùng một lời gọi `invokeAll`. Nếu cùng sửa trạng thái, cần đồng bộ riêng giữa các worker.

### Xử lý side effect khi có timeout/cancel

Một task có thể đã ghi dữ liệu, gửi sự kiện hoặc thực hiện một phần nghiệp vụ **trước khi bị hủy**. `Future.isCancelled()` chỉ mô tả trạng thái Future; nó không xác nhận side effect đã rollback.

Cần làm rõ:

1. Task nào được phép chạy nhiều lần khi retry?
2. Có idempotency key hoặc dấu phiên bản để tránh ghi trùng?
3. Có thể xử lý kết quả từng phần không, hay cần bù trừ?
4. Nếu timeout, có tiếp tục chờ cleanup ở tầng khác không?
5. Task có phản hồi interrupt và giải phóng tài nguyên trong `finally` không?

Nếu nghiệp vụ yêu cầu **all-or-nothing**, phải thiết kế transaction hoặc cơ chế điều phối thích hợp tại nơi sở hữu dữ liệu; `invokeAll` không cung cấp all-or-nothing.

## 11. Pool sizing, queue và nguy cơ quá tải

`invokeAll` có thể nhận rất nhiều task; nếu dùng pool ít worker và queue lớn, một phần lớn task sẽ chờ đến lượt. Cần cân nhắc:

- **`Executors.newFixedThreadPool(n)`** thường dùng queue không giới hạn thực tế; nộp batch rất lớn có thể tiêu thụ bộ nhớ và gây latency tăng.
- **`ThreadPoolExecutor` với bounded queue** cho phép giới hạn backlog nhưng có thể phát sinh `RejectedExecutionException` khi hết khả năng tiếp nhận. Không giả định `invokeAll` luôn có thể chèn trọn batch.
- Khi một task bị chặn lâu, worker tương ứng không tiến triển; nếu nhiều task cũng đang đợi tài nguyên, số worker còn thực thi hữu ích có thể ít hơn pool size.
- Dùng chunking, giới hạn concurrency, rate limiting hoặc backpressure nếu input lớn; không tạo hàng triệu Callable chỉ để chờ toàn bộ trong một lần.
- Quản lý thời gian chờ queue và execution riêng nếu cần phân tích latency; timeout của `invokeAll` tính theo lời gọi, không phải “chỉ tính lúc task bắt đầu chạy”.

**Đừng suy từ số lượng `Future` trả về rằng từng task đã chạy trong worker.** Với timeout/cancellation/rejection, có thể có task bị hủy khi còn trong queue và chưa vào `call()`. Với rejection policy chạy task tại caller, một phần công việc có thể còn chạy trên thread gọi; hiểu đúng policy là quan trọng khi đo thời gian và tổng số task hoàn thành.

## 12. Thiết kế API tổng hợp kết quả rõ ràng

Nếu cần bảo toàn thứ tự và nêu rõ lỗi từng tác vụ, ta có thể tạo một model kết quả cho batch. Ví dụ dưới đây **chạy độc lập**, trả chuỗi thành công hoặc lỗi theo vị trí.

Tạo file `InvokeAllSummary.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class InvokeAllSummary {
    record ItemResult(int index, String outcome) {}

    static List<ItemResult> execute(
            ExecutorService pool,
            List<Callable<String>> tasks) throws InterruptedException {
        List<Future<String>> futures = pool.invokeAll(tasks);
        List<ItemResult> output = new ArrayList<>();

        for (int i = 0; i < futures.size(); i++) {
            try {
                output.add(new ItemResult(i, "OK: " + futures.get(i).get()));
            } catch (ExecutionException e) {
                output.add(new ItemResult(i,
                        "ERROR: "
                        + e.getCause().getClass().getSimpleName()));
            }
        }
        return List.copyOf(output);
    }

    public static void main(String[] args) throws InterruptedException {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            List<Callable<String>> tasks = List.of(
                    () -> "alpha",
                    () -> { throw new IllegalArgumentException("x"); },
                    () -> "gamma"
            );

            List<ItemResult> result = execute(pool, tasks);
            for (ItemResult item : result) {
                System.out.println(item.index() + " " + item.outcome());
            }
        } finally {
            pool.shutdown();
        }
    }
}
```

Chạy:

```bash
javac InvokeAllSummary.java
java InvokeAllSummary
```

Đầu ra:

```text
0 OK: alpha
1 ERROR: IllegalArgumentException
2 OK: gamma
```

Ở đây `record` của Java 17 là một immutable value carrier cho chỉ số và outcome. `execute` chỉ gom danh sách **sau khi tất cả task đã hoàn tất** vì dùng overload không timeout. Nếu chuyển sang phiên bản timeout, cần thêm xử lý `CancellationException` hoặc kiểm tra `future.isCancelled()` trước `get()`; nếu không, task bị cancel có thể khiến phương thức tổng hợp kết thúc bất ngờ.

**Không nên dùng `get()` vô thời hạn trên các Future tùy ý trong một vòng lặp nếu từng Future được tạo bởi `submit` và chưa biết hoàn tất:** nếu task đầu chạy rất lâu, kết quả task sau dù đã xong vẫn bị giữ lại về mặt xử lý. `invokeAll` có chủ đích **đợi toàn nhóm** rồi mới tổng hợp, nên hành vi này phù hợp với batch. Nếu muốn stream kết quả sớm, chuyển sang CompletionService.

## 13. Những hiểu nhầm phổ biến

1. **“`invokeAll()` trả về một List kết quả T.”** Sai: trả `List<Future<T>>`.
2. **“Danh sách Future theo thứ tự task hoàn tất.”** Sai: tương ứng thứ tự task theo iterator đầu vào.
3. **“Một task lỗi khiến `invokeAll` ném `ExecutionException` ngay.”** Sai: thường thấy lỗi qua `future.get()`.
4. **“`invokeAll()` không timeout có fail-fast.”** Sai: chờ tất cả task hoàn tất, kể cả có task thất bại.
5. **“Bản timed sẽ ném `TimeoutException`.”** Sai: timed `invokeAll` trả List Future sau khi cancel task chưa hoàn tất.
6. **“`future.isCancelled()` chứng minh code task đã dừng.”** Sai: task có thể chưa hợp tác với interrupt hoặc còn cleanup.
7. **“Các task trong batch cùng lúc bắt đầu.”** Sai: chúng bị giới hạn bởi worker, queue và scheduling.
8. **“`invokeAll` cho nhóm kết quả thì các task có thể sửa chung ArrayList an toàn.”** Sai: cần bảo vệ shared mutable state riêng.
9. **“Đủ Future nghĩa là đủ kết quả thành công.”** Sai: mỗi Future có thể thành công, thất bại hoặc bị hủy.
10. **“Lấy `Future.get()` xong là phải `shutdownNow()` pool.”** Sai: pool có thể được tái sử dụng; chính owner quản lý lifecycle và shutdown hợp lý.
11. **“Timeout làm mọi side effect của các task đã chạy bị hoàn tác.”** Sai: cancellation không phải transaction.
12. **“Chỉ cần tăng số worker để chữa task A chờ task B cùng pool.”** Không phải lúc nào cũng đúng: cần sửa dependency hoặc giao thức chờ.
13. **“Một Future là một thread riêng.”** Sai: executor quyết định số worker và điều phối nhiều task qua cùng các thread.
14. **“HashSet task vẫn cho thứ tự nghiệp vụ rõ ràng.”** Không nên dựa vào iteration order không được quy định; dùng List khi cần mapping theo index.
15. **“`invokeAll` có thể gọi trên mọi Executor.”** Sai: phương thức này thuộc `ExecutorService`; interface `Executor` cơ bản chỉ có `execute`.

## 14. Checklist trước khi dùng invokeAll trong hệ thống thật

1. **Mục tiêu cần đủ kết quả hay chỉ kết quả đầu tiên?** Đủ kết quả dùng `invokeAll`; một thành công có thể dùng `invokeAny`.
2. **Có cần kết quả đến đâu xử lý đến đó?** Nếu có, cân nhắc `ExecutorCompletionService` hoặc `CompletableFuture`.
3. **Task có độc lập không?** Tránh worker chờ task khác vẫn xếp hàng trong chính pool nhỏ.
4. **Có yêu cầu thứ tự output không?** Dùng `List<Callable<T>>` để xác định mapping index → Future.
5. **Có chính sách lỗi rõ không?** Kiểm tra mọi Future qua `get()`, phân biệt lỗi task và lỗi caller.
6. **Có deadline chung không?** Dùng overload timeout, xử lý cancellation và side effect chưa hoàn tất.
7. **Callable có hợp tác interrupt?** Nếu dùng timeout/cancellation, kiểm tra blocking points, vòng CPU và cleanup trong `finally`.
8. **Có cần all-or-nothing không?** Đây là yêu cầu transaction nghiệp vụ, không phải tính chất của `invokeAll`.
9. **Pool có đủ khả năng nhận batch không?** Đánh giá worker, queue, rejection, backpressure và memory.
10. **Có shared mutable state không?** Thiết kế thread safety của state độc lập với quản lý Future.
11. **Có quản lý executor lifecycle không?** Shutdown khi owner hoàn tất công việc; không bỏ lại các non-daemon worker.
12. **Có kiểm thử thứ tự, thất bại, timeout và interrupt không?** Dùng latch để tạo ranh giới có kiểm soát, tránh kiểm thử timing bằng `sleep` tùy ý.

**Kết luận:** `ExecutorService.invokeAll()` là lựa chọn trực tiếp khi cần **gửi một collection Callable, chờ cả nhóm và nhận List Future theo đúng thứ tự task đầu vào**. Overload có timeout áp dụng **một ngân sách chung** và yêu cầu hủy những task chưa hoàn tất. Hãy kiểm tra từng Future để phân biệt kết quả, lỗi và hủy; quản lý interrupt, pool, quá tải và side effect theo giao thức của ứng dụng, thay vì xem `invokeAll` như một transaction hoặc một cơ chế đảm bảo mọi task đều thành công.