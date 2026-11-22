# Chạy nhiều Callable, lấy kết quả theo thứ tự hoàn tất

## 1. Bài tập thực tế và kết quả mong đợi

Bạn cần chạy nhiều tác vụ độc lập trong Java, mỗi tác vụ trả về một giá trị qua `Callable<T>`. Thời gian hoàn tất của các tác vụ khác nhau: có tác vụ chậm do I/O, có tác vụ xử lý rất nhanh. Yêu cầu là **nhận và xử lý kết quả ngay khi từng tác vụ hoàn tất**, không bị kẹt đợi tác vụ được gửi trước nhưng chạy lâu hơn.

Sau bài, bạn có thể:

- Phân biệt **thứ tự gửi tác vụ**, **thứ tự bắt đầu**, **thứ tự hoàn tất** và **thứ tự tiêu thụ kết quả**.
- Giải thích tại sao lặp `Future.get()` theo danh sách submit không đáp ứng yêu cầu hoàn tất trước, trả kết quả trước.
- Sử dụng `ExecutorCompletionService<T>`, `submit()`, `take()` / `poll(timeout)` và `Future.get()` để lấy kết quả theo thứ tự hoàn tất.
- Xử lý tác vụ lỗi, timeout, cancellation, số lượng task, backpressure và shutdown mà không làm mất kết quả hay treo thread chờ.
- Viết chương trình Java 17+ chạy độc lập, có output được kiểm soát và kiểm thử được.

**Phạm vi:** Java concurrency nói chung (`java.util.concurrent`). Không sử dụng Spring hoặc cơ chế concurrency riêng của framework.

## 2. Đề bài

Giả sử ứng dụng cần tổng hợp ba phép tính độc lập:

| Tác vụ | Input giả định | Kết quả | Đặc điểm |
| --- | --- | --- | --- |
| A | Xử lý tập dữ liệu A | `A` | Hoàn tất muộn |
| B | Xử lý tập dữ liệu B | `B` | Hoàn tất sớm nhất |
| C | Xử lý tập dữ liệu C | `C` | Hoàn tất sau B, trước A |

Ứng dụng submit theo thứ tự **A → B → C**, nhưng muốn đọc kết quả theo thứ tự **B → C → A** khi đó là thứ tự thực tế hoàn tất.

Các tiêu chí nghiệm thu:

1. Dùng ít nhất ba `Callable<String>` trên một `ExecutorService`.
2. In/tiêu thụ mỗi kết quả **ngay khi completion queue trả về**, không chờ A chỉ vì A được submit trước.
3. Thu đúng ba kết quả (hoặc xử lý rõ trường hợp thất bại) mà không bỏ qua lỗi task.
4. Mỗi lần chờ có giới hạn thời gian hoặc có chiến lược deadline tổng; khi kết thúc phải giải phóng executor.
5. Có test hoặc demo kiểm chứng thứ tự hoàn tất **mà không dựa vào `Thread.sleep()` để cam kết lịch chạy**.

Đây là vấn đề về **thời điểm thu kết quả**, không phải cam kết B sẽ luôn nhanh hơn A trên mọi máy. Trong phần demo, `CountDownLatch` được dùng để tạo đúng thứ tự B → C → A một cách xác định, giúp kiểm tra API.

## 3. Vì sao cách dùng List<Future> dễ làm chậm kết quả?

Cách thường gặp:

```java
List<Future<String>> futures = new ArrayList<>();
futures.add(executor.submit(taskA));
futures.add(executor.submit(taskB));
futures.add(executor.submit(taskC));

for (Future<String> future : futures) {
    System.out.println(future.get());
}
```

Đây là **đoạn minh họa**, cần khai báo `executor`, ba callable, import và vòng đời executor nếu dùng trong chương trình thực.

Mỗi `submit` trả về một `Future`, nhưng **`Future.get()` chờ đúng future đó**. Vòng lặp duyệt list A, B, C nên nếu A mất 10 giây, thread tiêu thụ sẽ đợi A trước, dù B và C đã hoàn tất. Điều đó tạo **head-of-line blocking** ở phía lấy kết quả.

`Future.isDone()` có thể dùng để kiểm tra trạng thái từng future nhưng tự quét/polling liên tục dễ làm tăng độ phức tạp, tốn CPU và khó quản lý race giữa các lần quét. `Future.get(timeout)` chỉ áp dụng timeout cho một future cụ thể; nó **không tự đổi thứ tự** lặp trên list.

Cần một cơ chế thông báo “**bất kỳ tác vụ nào vừa hoàn tất**” cho thread tiêu thụ.

## 4. Giải pháp: ExecutorCompletionService

`ExecutorCompletionService<V>` thực hiện `CompletionService<V>`, kết hợp:

- Một **executor** để thực thi các task được submit.
- Một **completion queue** để lưu các `Future<V>` đã hoàn thành và chờ được lấy ra.

Luồng xử lý:

```text
Thread điều phối
   submit A ─┐
   submit B ─┼────> ExecutorService (worker threads)
   submit C ─┘              │
                            ├─ B kết thúc ──> completion queue ─┐
                            ├─ C kết thúc ──> completion queue ─┼─> take()/poll()
                            └─ A kết thúc ──> completion queue ─┘

Thread nhận kết quả:
   Future B → get() → xử lý B
   Future C → get() → xử lý C
   Future A → get() → xử lý A
```

`completion.submit(callable)` nộp task và trả `Future<V>` để có thể giữ lại nếu cần cancel hoặc đối chiếu id. Khi task hoàn tất, future được đưa vào completion queue.

- `completion.take()`: **blocking** cho tới khi có một future đã hoàn tất.
- `completion.poll()`: lấy ngay nếu có, trả `null` khi chưa có.
- `completion.poll(timeout, unit)`: chờ có giới hạn, trả `null` nếu hết thời gian.
- `completedFuture.get()`: nhận giá trị hoặc lỗi của **future đã hoàn tất**, vì thế bình thường không phải chờ tính toán của task đó nữa. Nếu task đã lỗi, `get()` ném `ExecutionException`; nếu đã bị hủy, nó ném `CancellationException`.

**Quan trọng:** “Đã hoàn tất” bao gồm thành công, thất bại và hủy. Completion service trả future theo **thứ tự đưa vào completion queue**, thường tương ứng thứ tự task kết thúc; không hứa một thứ tự ổn định khi nhiều task kết thúc gần như cùng lúc. Test không được assert thứ tự ngẫu nhiên nếu chưa điều phối lịch.

Completion service **không tự tạo worker**, không tăng khả năng xử lý và không tự đặt timeout cho công việc. Bạn sở hữu và phải quản lý `ExecutorService` bên dưới.

## 5. Lời giải Java 17+: thứ tự B, C, A xác định

Ví dụ dưới dùng ba latch mở cổng độc lập: cả A, B, C đã bắt đầu và cùng chờ, sau đó main cho B hoàn tất, lấy kết quả B; tiếp tục cho C hoàn tất, lấy C; cuối cùng cho A hoàn tất, lấy A.

Lưu toàn bộ vào tệp **`CompletionOrderDemo.java`**:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.CompletionService;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorCompletionService;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class CompletionOrderDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(3);
        CompletionService<String> completed =
                new ExecutorCompletionService<>(executor);

        CountDownLatch ready = new CountDownLatch(3);
        CountDownLatch allowA = new CountDownLatch(1);
        CountDownLatch allowB = new CountDownLatch(1);
        CountDownLatch allowC = new CountDownLatch(1);

        try {
            // Thứ tự submit: A, B, C.
            completed.submit(task("A", ready, allowA));
            completed.submit(task("B", ready, allowB));
            completed.submit(task("C", ready, allowC));

            if (!ready.await(5, TimeUnit.SECONDS)) {
                throw new TimeoutException("Not all tasks started");
            }

            allowB.countDown();
            System.out.println("completed: " + nextResult(completed));

            allowC.countDown();
            System.out.println("completed: " + nextResult(completed));

            allowA.countDown();
            System.out.println("completed: " + nextResult(completed));
        } finally {
            // Mở mọi cổng kể cả khi main gặp exception.
            allowA.countDown();
            allowB.countDown();
            allowC.countDown();
            executor.shutdownNow();
            executor.awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    private static Callable<String> task(
            String id, CountDownLatch ready, CountDownLatch allowFinish) {
        return () -> {
            ready.countDown();
            if (!allowFinish.await(5, TimeUnit.SECONDS)) {
                throw new TimeoutException("Gate timeout: " + id);
            }
            return id;
        };
    }

    private static String nextResult(
            CompletionService<String> completed) throws Exception {
        Future<String> future = completed.poll(5, TimeUnit.SECONDS);
        if (future == null) {
            throw new TimeoutException("No task completed in time");
        }
        return future.get();
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac CompletionOrderDemo.java
java CompletionOrderDemo
```

Kết quả khi thực thi bình thường:

```text
completed: B
completed: C
completed: A
```

### Vì sao output này đáng tin?

1. Pool có ba worker, đủ để cả ba task bước qua `ready.countDown()` rồi chờ gate; main đợi đủ ready trước khi mở gate.
2. Khi mở `allowB`, chỉ task B được phép trả kết quả; A và C vẫn bị chặn tại gate của riêng mình. `poll()` lấy B.
3. Main **đợi và in B xong** mới mở `allowC`, nên completion tiếp theo là C; tương tự với A.
4. `Future.get()` trả `String` đã được tính hoặc truyền exception. Không có giả định kiểu “ngủ 100 ms thì task chắc đã xong”.

Vì gate được dùng chỉ để tạo lịch thực thi minh họa, production **không cần** chèn ba latch vào các callable. Khi chạy công việc thật, worker kết thúc tự nhiên khi tính toán hoặc I/O hoàn tất; completion queue tự phản ánh thứ tự chúng hoàn tất. Sẽ không có bảo đảm B, C, A trong những lần chạy chưa được điều phối.

`shutdownNow()` ở `finally` giúp dọn demo và yêu cầu interrupt best-effort; không cam kết chấm dứt lập tức mọi loại I/O. Trong ứng dụng thực, nên dùng `shutdown()` trước, `awaitTermination(timeout)`, rồi `shutdownNow()` nếu cần, đồng thời quản lý deadline và các tác vụ chưa xong.

## 6. Cách triển khai ứng dụng thực: submit N task, thu N completion

Khi không cần điều phối thứ tự cụ thể, mẫu tổng quát là:

```java
ExecutorService executor = /* executor được cấu hình phù hợp */;
CompletionService<Result> completion =
        new ExecutorCompletionService<>(executor);

int submitted = 0;
for (Callable<Result> task : tasks) {
    completion.submit(task);
    submitted++;
}

for (int i = 0; i < submitted; i++) {
    Future<Result> done = completion.take();
    try {
        Result result = done.get();
        handle(result);
    } catch (ExecutionException failure) {
        handleFailure(failure.getCause());
    } catch (CancellationException cancelled) {
        handleCancellation();
    }
}
```

Đây là **mẫu tích hợp**, không phải chương trình Java độc lập: `Result`, `tasks`, `handle(...)`, `handleFailure(...)` và `handleCancellation()` là kiểu/hàm nghiệp vụ phải được định nghĩa; `ExecutionException`, `CancellationException` và các lớp concurrency cần import.

Phân biệt hai bộ đếm:

- `submitted`: số task **đã submit thành công**. Nếu `submit` bị từ chối vì executor đầy, `RejectedExecutionException` có thể ném ngay và task đó **không được tính là đã submit**.
- `received` hoặc biến `i`: số **future hoàn tất đã được lấy ra**, kể cả tương ứng task lỗi hoặc bị cancel. Muốn biết số thành công, dùng bộ đếm riêng.

Nếu mọi task thực thi thành công, vòng lặp nhận đúng một kết quả cho mỗi task. Nếu có lỗi, bạn vẫn cần đọc những completion còn lại hoặc thiết lập chính sách dừng/cancel rõ ràng. Không nên ngắt vòng lặp ngay khi thấy một exception mà bỏ mặc các task khác đang chạy.

Nếu phải giữ mapping từ kết quả về tác vụ đầu vào, trả về đối tượng mang **taskId**:

```java
record TaskResult(String taskId, long value) {}

Callable<TaskResult> task = () -> {
    long value = calculateValue();
    return new TaskResult("task-42", value);
};
```

`calculateValue()` chỉ là placeholder cho hàm nghiệp vụ trong đoạn minh họa. Với thành công, bạn biết id qua `result.taskId()`. Với thất bại, vì không nhận được `TaskResult`, có thể bọc callable để ném exception mang id hoặc lưu mapping từ `Future` trả bởi `submit()` đến id. Không dựa vào vị trí của completion trong queue để suy ra task A/B/C.

## 7. Timeout: không để thread thu kết quả đợi vô hạn

`take()` đợi vô hạn nếu không có future nào đi vào completion queue. Khi production có deadline, dùng `poll(timeout, unit)` và kiểm tra `null`:

```java
Future<Result> done = completion.poll(2, TimeUnit.SECONDS);
if (done == null) {
    // Không có task nào hoàn tất trong khoảng chờ vừa qua.
    // Quyết định hủy, báo timeout, retry có kiểm soát hoặc tiếp tục chờ.
} else {
    Result value = done.get();
}
```

Ví dụ này chờ tối đa hai giây cho **completion tiếp theo**, không giới hạn tổng thời gian của N completion. Nếu mỗi vòng cho phép đợi 2 giây, N vòng có thể mất gần `2 × N` giây chỉ để chờ. Đặt **deadline tổng** khi giao diện hoặc tác vụ có ngân sách thời gian cố định:

```java
long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);

for (int i = 0; i < submitted; i++) {
    long remaining = deadline - System.nanoTime();
    if (remaining <= 0) {
        throw new TimeoutException("Overall deadline exceeded");
    }
    Future<Result> done =
            completion.poll(remaining, TimeUnit.NANOSECONDS);
    if (done == null) {
        throw new TimeoutException("Overall deadline exceeded");
    }
    consume(done.get());
}
```

Đây là mã ghép vào luồng đã khai báo `submitted`, `completion`, `Result` và `consume`. Cách tính bằng `System.nanoTime()` đo khoảng thời gian trôi qua (không phụ thuộc thay đổi đồng hồ lịch). Đối với deadline cực dài hoặc khi xử lý edge case overflow, cần thiết kế phép tính deadline an toàn; ví dụ 5 giây chỉ nhằm minh họa.

**Lưu ý:** `poll()` timeout chỉ giới hạn **thời gian đợi của thread tiêu thụ**. Nó không tự dừng callable đang chạy; cần timeout riêng cho I/O/backend, hoặc `Future.cancel(true)` nếu task hỗ trợ interruption và chính sách cho phép.

Khi `InterruptedException` được ném từ `poll`/`take`/`get` đang chờ, không nuốt lỗi rồi tiếp tục vô hạn. Nếu tầng của bạn không thể ném tiếp, cân nhắc khôi phục cờ interrupt qua `Thread.currentThread().interrupt()`, cleanup và trả kết quả theo hợp đồng.

## 8. Lỗi, hủy và xử lý completion đúng nghĩa

Một `Future` được đưa vào completion queue khi task **kết thúc**, bao gồm:

| Trạng thái | `future.get()` | Cách xử lý |
| --- | --- | --- |
| Thành công | Trả kết quả | Xử lý dữ liệu ngay |
| Callable ném exception | Ném `ExecutionException` | Đọc `getCause()`, log/ghi failure theo task |
| Future bị hủy | Ném `CancellationException` | Ghi nhận cancel theo hợp đồng |
| Thread lấy kết quả bị interrupt khi chờ | Có thể ném `InterruptedException` ở `take`/`poll`/`get` | Dừng hoặc chuyển tiếp interrupt và cleanup |

Một lần `submit(callable)` có thể bị executor **từ chối ngay** trước khi task được nhận. Trường hợp `RejectedExecutionException` này không tạo một completion cần chờ trong loop N tác vụ. Tăng biến đếm chỉ sau khi submit thành công.

**Không mặc định retry ngay mọi lỗi.** Nếu nhiều backend cùng chậm, retry thiếu backoff, jitter hoặc ngân sách có thể làm executor đầy và tăng tải. Phải xác định lỗi nào retryable, số lần tối đa và deadline tổng. Nếu hệ thống có chính sách fail-fast, cần hủy các future còn lại và kiểm soát tài nguyên đang sử dụng; cancel chỉ là yêu cầu phối hợp, không bảo đảm task I/O dừng ngay.

**Không xem completion queue là result queue vô hạn độc lập với tài nguyên:** worker vẫn dùng CPU, bộ nhớ, socket và thread. Nếu submit một triệu task vào executor `newFixedThreadPool(10)`, queue thực thi mặc định có thể tăng rất lớn dù chỉ có mười task chạy. Hãy giới hạn input/batch hoặc dùng executor có queue bounded và chính sách backpressure.

## 9. Kiểm soát số task đang bay (in-flight)

Mẫu `submit tất cả → đợi tất cả` ổn khi danh sách task nhỏ. Với dữ liệu stream rất lớn hoặc vô hạn, nên giới hạn số task chưa được tiêu thụ kết quả: ví dụ tối đa 20 task cùng được submit nhưng chưa có completion được lấy.

Ý tưởng xử lý theo cửa sổ (sliding window):

1. Submit tối đa `maxInFlight` task đầu tiên.
2. Lấy completion tiếp theo bằng `poll(timeout)`.
3. Xử lý kết quả hoặc lỗi; giảm bộ đếm in-flight.
4. Nếu còn input, submit thêm một task và tăng lại bộ đếm.
5. Lặp cho đến khi hết input **và** in-flight về 0.

Bằng cách đó, cả tốc độ nhận việc và lượng bộ nhớ giữ future đều có giới hạn. Tuy nhiên completion service **không thay thế** giới hạn connection, request concurrency hoặc memory của backend; vẫn cần cấu hình executor và tài nguyên downstream.

Khi cần executor bounded, có thể dùng `ThreadPoolExecutor` với `ArrayBlockingQueue` và `AbortPolicy` để từ chối khi sức chứa cạn. Nếu chọn `CallerRunsPolicy`, một task bị đẩy ra có thể chạy ngay trên thread submit, làm chậm producer và thay đổi đặc tính điều phối; cần biết trước hành vi này.

**Lưu ý API:** nếu khởi tạo `ExecutorCompletionService` với completion queue tự cung cấp, tài liệu JDK giả định queue đó có thể nhận mọi future đã hoàn tất. Dùng queue completion bounded có thể làm việc đưa future hoàn tất vào queue thất bại, gây mất notification. Giới hạn số tác vụ in-flight ở tầng submit/executor thay vì thu nhỏ completion queue một cách thiếu kiểm soát.

## 10. Phân biệt với invokeAll, invokeAny và CompletableFuture

| API | Ý nghĩa | Phù hợp khi |
| --- | --- | --- |
| `ExecutorService.submit` + danh sách `Future` | Nộp riêng từng task, giữ future theo thứ tự bạn lưu | Cần kiểm soát future từng task; nếu loop `get` theo list thì thu theo submit order |
| `ExecutorService.invokeAll` | Chờ tất cả kết thúc (hoặc timeout), trả danh sách future **cùng thứ tự collection đầu vào** | Muốn xử lý cả batch sau khi kết thúc |
| `ExecutorService.invokeAny` | Trả kết quả của **một task hoàn thành thành công**; có thể hủy các task khác | Chỉ cần một đáp án thành công, không cần mọi đáp án |
| `ExecutorCompletionService` | Queue các future đã hoàn tất để người tiêu thụ lấy dần | Cần xử lý mọi completion theo thứ tự đến |
| `CompletableFuture.anyOf` | Future kết thúc theo completion đầu tiên trong nhóm, kể cả exceptional | Chỉ cần biết sự kiện đầu tiên; không tự lặp thu tất cả |
| `CompletableFuture.allOf` | Future đại diện việc cả nhóm hoàn thành; không tự trả danh sách kết quả theo completion order | Chờ cả nhóm, rồi đọc các kết quả |
| `CompletableFuture.whenComplete` / `thenAccept` | Đăng ký callback khi từng stage hoàn tất | Thiết kế theo callback, không cần thread chuyên chờ `take()` |

**`invokeAll()` không giải quyết bài toán này:** nó chỉ trả sau khi các task trong batch đã kết thúc và thứ tự danh sách tương ứng input. `invokeAny()` dừng ở một kết quả thành công; không cung cấp mọi kết quả theo completion order.

Với `CompletableFuture`, callback của mỗi task có thể xử lý kết quả ngay khi stage hoàn tất, nhưng callback mặc định có thể chạy trên thread hoàn tất stage hoặc thread đăng ký tùy trạng thái. Đừng đặt công việc blocking nặng trong callback mà không cân nhắc executor hoặc dùng biến thể `Async` với executor rõ ràng. Muốn giữ thứ tự xử lý callback theo thời gian hoàn tất, cần cơ chế serialization/queue phù hợp; callback chạy song song **không hứa thứ tự log**.

## 11. Kiểm thử bài tập bằng CountDownLatch

Thứ tự hoàn tất của các task thực tế phụ thuộc scheduling và I/O. Test viết kiểu “A ngủ 300 ms, B ngủ 100 ms, C ngủ 200 ms, do đó luôn nhận B–C–A” **không đáng tin** nếu tải máy hoặc JVM scheduling thay đổi.

Dùng các gate từ ví dụ chính để kiểm tra:

- **Thứ tự submit:** A, B, C.
- **Thứ tự cho phép hoàn tất:** B, C, A.
- **Thứ tự tiêu thụ kỳ vọng:** B, C, A.
- **Số phần tử:** đúng 3, không trùng hoặc bỏ sót.
- **Không có exception:** mọi `get()` thành công và chứa đúng task id.

Khi kiểm thử thất bại, có thể thay callable B bằng callable ném `IllegalStateException("B failed")` sau khi gate mở. Khi đó completion tương ứng B vẫn xuất hiện đầu tiên, nhưng `get()` ném `ExecutionException` với cause thích hợp; hệ thống phải xử lý nó thay vì ngầm coi completion nào cũng có kết quả bình thường.

Kiểm thử timeout: đừng mở gate A, gọi `poll(100, MILLISECONDS)` khi không có completion nào khác đang chờ; phải nhận `null`. Sau đó mở gate trong `finally` và dọn executor. Nếu test pool chỉ có hai worker trong khi ba task đều đợi cổng “ready”, test có thể tự deadlock; đảm bảo số worker đủ hoặc thiết kế gate hợp lý.

Một **test production** còn nên kiểm tra ngắt chờ, cancel, submit bị từ chối, task trả `null` hợp lệ, dữ liệu input rỗng, không rò thread và deadline tổng. `Callable<String>` có thể trả `null`; `Future.get()` trả `null` trong trường hợp đó, **không có nghĩa poll không tìm thấy completion**. Chỉ `poll()` trả `null` biểu thị không tìm được future trong thời hạn.

## 12. Bài tập mở rộng có thể tự thực hiện

### Bài A — Thu kết quả và lỗi nhưng tiếp tục

Thay ba task thành một danh sách gồm năm `Callable<Integer>`. Một task ném exception, bốn task trả số. Thu đủ năm **completion**; in các giá trị thành công theo thứ tự nhận được, ghi lại nguyên nhân lỗi và assert:

- `successes == 4`;
- `failures == 1`;
- `successes + failures == submitted`.

Không assert một thứ tự cụ thể trừ khi dùng latch để điều phối.

### Bài B — Đếm tổng deadline

Cho phép tổng thời gian xử lý batch tối đa 3 giây theo `System.nanoTime()`. Tính **thời gian còn lại** trước mỗi `poll`. Khi hết deadline, báo số task đã hoàn tất và hủy các future chưa xong theo chính sách; không gọi `poll(3, SECONDS)` từ đầu ở từng vòng rồi tưởng rằng tổng thời gian tối đa vẫn là 3 giây.

### Bài C — Cửa sổ in-flight

Có 100 request nhưng chỉ muốn tối đa 8 request đang submit và chưa thu xong. Implement sliding window ở mục 9, đo `maxObservedInFlight` và assert `maxObservedInFlight <= 8`. Tất cả 100 kết quả hoặc failure phải được phân loại, kể cả khi executor có giới hạn queue nhỏ. Tách rõ lỗi submit từ chối với lỗi callable thực thi.

### Bài D — Trả kết quả ngay nhưng lưu báo cáo theo input order

Cho mỗi task một `taskId` và một `inputIndex`. Xử lý progress theo completion order nhưng lưu kết quả vào một cấu trúc theo `inputIndex` để cuối cùng tạo báo cáo A, B, C. **Thứ tự tiêu thụ** và **thứ tự trình bày báo cáo** là hai yêu cầu khác nhau, có thể đồng thời đáp ứng.

## 13. Những lỗi thường gặp

- **Duyệt `List<Future>` theo thứ tự submit:** gây head-of-line blocking; dùng completion queue khi cần output theo completion order.
- **Gọi `get()` trước `take()` trên future đầu tiên:** vô tình quay lại lỗi chờ task chậm.
- **Nhầm completion với success:** task lỗi hoặc hủy vẫn là completion; phải xử lý `ExecutionException` và `CancellationException`.
- **Không giới hạn chờ:** `take()` có thể đợi mãi khi task không hoàn tất hoặc notification không tới; đặt deadline khi phù hợp.
- **Đếm cả submit bị từ chối:** sẽ chờ một completion không bao giờ được tạo cho task đó.
- **Submit lượng việc không giới hạn:** queue executor và giữ future có thể gây áp lực bộ nhớ; dùng giới hạn in-flight/backpressure.
- **Dùng `sleep` để chứng minh thứ tự:** test flaky và phụ thuộc môi trường; dùng latch/barrier khi muốn lịch xác định.
- **Cho nhiều task chờ gate hơn số worker:** test tự deadlock.
- **Bỏ quên mapping về task nguồn:** biết kết quả đến trước nhưng không biết nó thuộc input nào; gắn taskId hoặc mapping future.
- **Quên đóng executor:** thread còn sống sau bài test hoặc yêu cầu ứng dụng kết thúc.
- **Dùng completion queue bounded sai cách:** future hoàn tất có thể không được đưa vào queue; giới hạn lượng submit ở upstream.
- **Hiểu nhầm `allOf`/`invokeAll` là completion order:** chúng chờ nhóm task, không stream từng completion.

## 14. Checklist tự đánh giá

1. Tôi đã submit các `Callable` theo thứ tự nào, và kết quả được nhận theo sự kiện nào?
2. Tôi có gọi `poll(timeout)` hoặc `take()` trước khi gọi `get()` trên future đã hoàn tất không?
3. Tôi có thu đúng số completion đã submit thành công và ghi riêng số success/failure/cancel không?
4. Nếu một task không trả về hoặc một task ném lỗi, thread nhận kết quả có thoát và giải phóng tài nguyên không?
5. Tôi có đặt giới hạn số in-flight, xử lý rejection và tài nguyên downstream khi input lớn không?
6. Khi test yêu cầu một thứ tự cố định, tôi đã điều phối bằng cơ chế đồng bộ thay vì đoán từ thời gian sleep chưa?
7. Khi cần báo cáo cuối theo input order, tôi có gắn id/index vào kết quả thay vì mặc định queue đã giữ thứ tự submit không?

**Ghi nhớ:** `ExecutorCompletionService` giải quyết bài toán **nhiều Callable, tiêu thụ từng kết quả theo thứ tự hoàn tất**. Submit order không ràng buộc completion order; `Future.get()` theo danh sách có thể chặn kết quả đã sẵn sàng. Dùng `CompletionService.take()/poll()` để nhận future hoàn tất, sau đó `get()` để lấy giá trị hoặc phát hiện lỗi, kết hợp deadline, cancellation và giới hạn tài nguyên phù hợp.
