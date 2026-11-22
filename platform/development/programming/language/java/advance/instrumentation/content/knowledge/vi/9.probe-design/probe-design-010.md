# Không suy ra thời gian hoàn thành tác vụ bất đồng bộ từ lúc phương thức trả `Future`

> **Ngữ cảnh:** Java Advance → Instrumentation → **Thiết kế điểm đo**. Một phương thức trả `Future` hoặc `CompletionStage` có thể chỉ **bàn giao một handle cho kết quả tương lai**. Nếu một Java agent đặt mốc kết thúc ngay tại opcode `areturn` hoặc tại thời điểm interceptor nhận lại handle, số đo thường phản ánh **thời gian gọi/điều phối** chứ chưa phản ánh **thời gian hoàn thành công việc bất đồng bộ**. Bài dựa trên Java 17+, có ví dụ chạy và output kiểm chứng trên OpenJDK 21.

## 1. Phân biệt thời điểm trả về với thời điểm hoàn thành

Xét một API:

~~~java
CompletableFuture<String> fetchAsync() {
    return CompletableFuture.supplyAsync(() -> loadRemoteData(), executor);
}
~~~

Nếu agent đo:

~~~java
long start = System.nanoTime();
CompletableFuture<String> future = fetchAsync();
long end = System.nanoTime();
recordDuration(end - start); // Chỉ thời gian gọi fetchAsync và nhận handle
~~~

thì `end - start` đo **thời gian đi vào và trả về từ `fetchAsync()`**. Nó **không** chắc chắn bao gồm thời gian xếp hàng trong executor, chạy task, kết nối mạng, retry, xử lý exception hoặc hoàn tất stage. Trong trường hợp này method có thể trả về gần như ngay lập tức trong khi tác vụ vẫn đang chờ thread rảnh.

Ngược lại, đừng phát biểu rằng mọi `Future` đều *chưa hoàn thành* tại thời điểm trả về. Method có thể trả `CompletableFuture.completedFuture(value)`, `failedFuture(error)`, một future đã hoàn tất sớm trên thread khác, hoặc thậm chí thực hiện nhiều việc đồng bộ trước khi tạo handle. **Điều đúng là: không được suy ra trạng thái hoàn thành từ riêng sự kiện method return.** Phải dựa trên hợp đồng của future và mốc hoàn tất của đúng stage cần đo.

### Các mốc thời gian hữu ích

~~~text
Caller thread                       Worker/executor thread
─────────────                       ─────────────────────
t0: gọi fetchAsync()
    ├─ chuẩn bị, schedule work ----> [queue ...]
t1: method trả Future                  t2: task thực sự bắt đầu
    │                                   ├─ CPU / IO / retry ...
    │                                   └─ t3: worker hoàn tất công việc
    │                                                │
    │                                        t4: Future terminal
    │                                                │
    └── callback quan sát Future <-------------------+
         t5: observer ghi nhận SUCCESS / FAILURE / CANCELLED
~~~

Sơ đồ thể hiện **một trường hợp async điển hình**, không phải thứ tự thời gian bất biến cho mọi API. Task có thể bắt đầu hoặc thậm chí kết thúc **trước `t1`**; một `CompletableFuture` có thể được complete từ thread bất kỳ; nhiều future chỉ biểu diễn một phần của pipeline.

| Mốc | Nó đo điều gì? | Thường có sẵn ở đâu? |
|---|---|---|
| `t0` — bắt đầu gọi | Invocation bắt đầu | Method entry / interceptor / bytecode probe |
| `t1` — method trả future | Phần đồng bộ của API kết thúc, có handle | Method exit sau khi lấy return value |
| `t2` — work bắt đầu | Task được executor/thread bắt đầu thực thi | Wrapper của `Runnable`/`Callable` hoặc hook trong producer |
| `t3` — work hoàn tất thực tế | Đường xử lý của producer tới điểm kết thúc | `try/finally` bên trong worker, sau khi làm xong phần công việc được định nghĩa |
| `t4` — Future terminal | Future chuyển sang trạng thái kết thúc: success, failure hoặc cancellation | Completion mechanics của Future/CompletionStage |
| `t5` — observer ghi mốc | Code đo nhận thông báo hoàn tất | `whenComplete`, listener, `FutureTask.done()` hoặc hook phù hợp |

Các độ đo nên được **đặt tên khác nhau**:

- **Method/dispatch latency:** `t1 - t0` — thời gian synchronous của method.
- **Queue delay:** `t2 - t_schedule` — thời gian từ lúc task được chấp nhận/xếp hàng đến lúc thực thi (cần hook vào executor).
- **Task execution:** `t3 - t2` — thời gian worker thực sự chạy (cần instrument producer).
- **Observed future latency:** `t5 - t0` — thời gian từ invocation đến khi observer nhìn thấy Future terminal. Đây thường là số đo hợp lý cho API bất đồng bộ nhưng **không nhất thiết chính xác bằng thời điểm work vật lý hoàn tất**.
- **Business completion:** có thể còn muộn hơn `t4`, ví dụ callback tiếp theo cần commit, publish event hoặc nhận xác nhận từ hệ thống khác. Chỉ kết luận khi đã xác định đúng hợp đồng nghiệp vụ.

Nếu ghi mỗi `method.duration` ở `t1` rồi đặt tên `task.duration`, dashboard sẽ báo tốc độ rất nhanh ngay cả khi backlog executor lớn hoặc downstream bị treo. Đó là sai **ranh giới đo**, không chỉ là sai cách đổi đơn vị.

## 2. `Future` và `CompletableFuture` thật sự bảo đảm gì?

### `Future<V>` chỉ bảo đảm có thể kiểm tra/chờ/lấy kết quả

Với `java.util.concurrent.Future<V>`:

- `isDone()` cho biết Future **đã kết thúc** tại thời điểm gọi. Kết thúc có thể do thành công, lỗi hoặc hủy; **không đồng nghĩa success**.
- `isCancelled()` phân biệt trạng thái hủy do Future ghi nhận.
- `get()` có thể chặn thread cho tới khi Future kết thúc, trả kết quả hoặc ném `ExecutionException`/`CancellationException`; `get(timeout, unit)` còn có thể ném `TimeoutException` khi **bản thân lời đợi** hết thời gian. Timeout của một lượt `get` không có nghĩa Future đã terminal.
- `cancel(...)` **cố gắng hủy**; hủy Future không bảo đảm mọi thao tác nền hoặc hệ thống bên ngoài đều đã dừng. Ví dụ đang chạy I/O có thể không hủy ngay, tùy implementation và cơ chế interruption.

Interface `Future` cổ điển trên Java 17 **không cung cấp callback completion chuẩn kiểu `whenComplete`**. Vì vậy Java agent chỉ thấy phương thức trả một `Future<?>` thường **không thể tự biết chính xác lúc Future kết thúc** nếu không thêm điểm đo vào producer/executor hoặc một cơ chế observer thích hợp.

**Đừng gọi `future.get()` trong method-exit interceptor chỉ để đo!** Thao tác đó có thể chặn caller, đổi hành vi API từ non-blocking thành blocking, gây thread starvation và deadlock khi task chờ chính thread đang bị chặn.

### `CompletableFuture<T>` vừa là `Future` vừa là `CompletionStage`

`CompletableFuture` cho phép đăng ký hành động hoàn tất:

~~~java
future.whenComplete((result, error) -> {
    // error == null thường là completion bình thường
    // error != null thể hiện completion bất thường, gồm các trường hợp hủy
});
~~~

Theo hợp đồng `CompletionStage.whenComplete`, callback nhận outcome của stage được quan sát khi stage đó hoàn tất. Nó **trả một dependent stage mới** có kết quả/exception của stage nguồn nếu observer không gây lỗi. Nếu callback itself ném exception, dependent stage có thể hoàn tất theo exception đó khi stage gốc thành công. Vì vậy code đo lường phải phòng thủ để logging/metrics không làm thay đổi trạng thái stage được **trả cho caller**.

Chú ý ba sắc thái:

1. **Stage đã hoàn thành trước khi gắn listener:** callback có thể chạy ngay khi đăng ký; không được giả định callback lúc nào cũng đến trên worker thread.
2. **Stage chưa hoàn thành:** callback non-async có thể chạy trên thread hoàn thành stage hoặc caller khác tham gia completion; callback không phải một “interrupt” có timestamp tuyệt đối chính xác.
3. **`whenCompleteAsync`:** việc chạy observer còn phải qua executor, nên `t5` có thể muộn hơn nhiều so với `t4`; latency đo bằng callback async bao gồm cả queue delay của observer.

Muốn thời gian đo ít bị lệch, ghi `System.nanoTime()` ngay **đầu** callback non-async và giữ thao tác callback nhẹ. Dù vậy đó vẫn là **mốc quan sát terminal**, không phải timestamp bên trong JVM tại khoảnh khắc chuyển trạng thái.

### Hủy `CompletableFuture` khác với ngừng worker

Theo Javadoc, `CompletableFuture.cancel(boolean)` hoàn tất future với `CancellationException`; tham số `mayInterruptIfRunning` **không dùng để điều khiển xử lý đang chạy trong implementation này**. Vì vậy `isDone() == true` và `isCancelled() == true` có thể xảy ra trong lúc mã producer hoặc I/O vẫn đang chạy. Nếu instrumentation cần **thời gian work thật sự dừng**, cần hook ngay trong worker và cơ chế hủy thực tế, không chỉ nghe future cancellation.

## 3. Gắn điểm đo đúng vòng đời mà không đổi hợp đồng API

Giả sử một Java agent/interceptor quan sát được phương thức và return value. Có hai đường:

**Đường đồng bộ:**

~~~text
method entry → execute original method → normal return / synchronous throw
             → ghi method.duration
~~~

**Đường bất đồng bộ khi return value là `CompletionStage`:**

~~~text
method entry → original method trả stage
             → ghi method/dispatch.duration
             → gắn listener cho đúng stage
             → trả NGUYÊN đối tượng return value cho caller
             → khi stage terminal → ghi future.observed.duration + outcome
~~~

Ví dụ pattern cho Java 17+; đây là **helper minh họa**, gọi sau khi method gốc trả về, không phải agent độc lập:

~~~java
import java.util.concurrent.CompletionStage;

final class AsyncMetrics {
    static Object observeReturnedValue(String operation, long startNanos,
                                       Object originalReturn) {
        long returnedAt = System.nanoTime();
        recordMethodTime(operation, returnedAt - startNanos);

        if (originalReturn instanceof CompletionStage<?> stage) {
            stage.whenComplete((value, failure) -> {
                long observedAt = System.nanoTime();
                try {
                    recordFutureTime(operation, observedAt - startNanos,
                                     failure == null ? "SUCCESS" : "FAILURE_OR_CANCEL");
                } catch (RuntimeException telemetryFailure) {
                    // Tránh ném lỗi telemetry vào dependent stage.
                    // Kênh log nội bộ nên độc lập và không chặn đường hoàn tất.
                }
            });
        }
        return originalReturn; // Bảo toàn return-value identity/hợp đồng caller.
    }

    private static void recordMethodTime(String name, long nanos) {
        // Gửi metric có giới hạn cardinality trong ứng dụng thực tế.
    }

    private static void recordFutureTime(String name, long nanos, String outcome) {
        // Gửi metric/tracing; không block thread hoàn thành.
    }
}
~~~

**Vì sao trả `originalReturn`?** `whenComplete` tạo **một stage phụ thuộc mới**. Không nên thay Future trả về bằng stage mới chỉ để chèn logging nếu không có yêu cầu thiết kế: bạn có thể làm đổi identity, khả năng gọi `cancel`, cách library quan sát exception hoặc loại concrete của return value. Code trên chỉ gắn observer rồi trả lại handle ban đầu.

Đoạn helper dùng outcome `FAILURE_OR_CANCEL` để tránh gộp mọi `failure != null` thành lỗi business. Khi cần phân biệt, xác định chính sách phân loại `CancellationException`, `CompletionException` và Future gốc (nếu implement `Future`) thật rõ. Đừng dựa vào exception message chưa chuẩn hóa.

**Synchronous throw:** nếu method gốc ném exception **trước khi trả Future**, không tồn tại handle để gắn callback. Interceptor phải ghi một sự kiện `METHOD_THROW` riêng ở đường exception; không đợi `whenComplete` không bao giờ xuất hiện.

**Điểm dễ sai với AOP/bytecode:** gắn listener chỉ sau khi nhận return value có thể bỏ qua một số thông tin về thời điểm task thực sự bắt đầu. Nếu công việc đã kết thúc trước khi method return, observer có thể chạy ngay trong caller thread. Khi cần queue time hoặc actual execution time, thêm điểm đo ở executor/worker, chứ không cố suy luận từ callback ở method exit.

## 4. Thực hành Java 17+: chứng minh bằng `CountDownLatch`

Thí nghiệm này tạo **hai** tác vụ trong `ExecutorService`: một hoàn thành bình thường, một ném `IllegalArgumentException`. Mỗi worker sẽ đứng chờ tại một latch, nên method đã trả `CompletableFuture` mà work **chắc chắn chưa hoàn tất** tại thời điểm main in mốc. Main chỉ cho work kết thúc sau khi đã ghi log return; listener in mốc completion.

Dùng latch để điều khiển thứ tự thay vì `Thread.sleep(100)`, giúp kết quả ít phụ thuộc scheduling. **Các dòng stdout bên dưới đã được kiểm chứng khi biên dịch `--release 17` và chạy trên OpenJDK 21.**

### 4.1 File `FutureTimingDemo.java`

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicLong;

public final class FutureTimingDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService workers = Executors.newSingleThreadExecutor();
        try {
            runCase(workers, "ok", false);
            runCase(workers, "bad", true);
        } finally {
            workers.shutdownNow();
        }
    }

    private static void runCase(ExecutorService workers, String name, boolean fail)
            throws InterruptedException {
        CountDownLatch taskStarted = new CountDownLatch(1);
        CountDownLatch releaseTask = new CountDownLatch(1);
        AtomicLong completionObservedAt = new AtomicLong();

        long invokedAt = System.nanoTime();
        CompletableFuture<String> future = CompletableFuture.supplyAsync(() -> {
            taskStarted.countDown();
            try {
                releaseTask.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("interrupted", e);
            }
            if (fail) {
                throw new IllegalArgumentException("boom");
            }
            return "OK";
        }, workers);
        long returnedAt = System.nanoTime();

        taskStarted.await();
        System.out.println("[RETURN] " + name + " done=" + future.isDone());
        CompletableFuture<String> observed = future.whenComplete((value, error) -> {
            completionObservedAt.set(System.nanoTime());
            System.out.println("[COMPLETE] " + name + " outcome="
                    + (error == null ? "SUCCESS" : "FAILURE"));
        });

        System.out.println("[CONTROL] " + name + " release");
        releaseTask.countDown();
        try {
            System.out.println("[RESULT] " + name + " value=" + observed.join());
        } catch (CompletionException e) {
            System.out.println("[RESULT] " + name + " cause="
                    + e.getCause().getClass().getSimpleName());
        }
        System.out.println("[CHECK] " + name + " returnedBeforeCompletion="
                + (completionObservedAt.get() > returnedAt));
        if (invokedAt > returnedAt) {
            throw new AssertionError("non-monotonic clock");
        }
    }
}
~~~

Lệnh biên dịch và chạy từ thư mục chứa file:

~~~bash
javac --release 17 FutureTimingDemo.java
java FutureTimingDemo
~~~

Trên Windows PowerShell cũng dùng đúng hai lệnh trên. Class không khai báo package và tên public class khớp tên file, nên không cần `-cp` riêng nếu đứng tại thư mục chứa `.class`.

### 4.2 Stdout đã kiểm chứng trên OpenJDK 21

~~~text
[RETURN] ok done=false
[CONTROL] ok release
[COMPLETE] ok outcome=SUCCESS
[RESULT] ok value=OK
[CHECK] ok returnedBeforeCompletion=true
[RETURN] bad done=false
[CONTROL] bad release
[COMPLETE] bad outcome=FAILURE
[RESULT] bad cause=IllegalArgumentException
[CHECK] bad returnedBeforeCompletion=true
~~~

**Giải thích chính xác:**

- `future` được trả ra khi worker còn đang chờ `releaseTask`. Do đó `isDone()` tại mốc kiểm tra là `false` trong cả hai case.
- `[CONTROL] ... release` xuất hiện trước khi task có thể trả kết quả hoặc ném exception. Dòng `[COMPLETE]` đến từ `whenComplete` **sau khi future đã được hoàn tất**.
- `observed.join()` được dùng **chỉ trong chương trình thử nghiệm** để đợi stage observer và xác định thứ tự log. **Không** đưa `join` vào production method-exit interceptor. Với case lỗi, `join` của dependent stage ném `CompletionException` có cause `IllegalArgumentException`.
- `returnedBeforeCompletion=true` so sánh timestamp ngay sau lần trả Future với timestamp ghi trong callback. Cả hai case đều có `true` vì callback không thể chạy trước lúc main giải phóng latch.
- `System.nanoTime()` được sử dụng làm đồng hồ monotonic để tính chênh lệch trong **cùng JVM**. Ví dụ chỉ in boolean nhằm tránh hard-code một con số mili giây phụ thuộc tốc độ CPU/scheduling.

**Phạm vi chứng minh:** đây là một mô hình controlled asynchronous computation. Nó cho thấy không thể coi method return là completion. Nó không hứa mọi future đều chưa hoàn tất lúc trả về: một API khác có thể trả future đã completed.

## 5. Nếu chỉ nhận `Future<?>`, lấy dấu mốc completion thế nào?

Ví dụ:

~~~java
Future<String> submitted = executor.submit(() -> {
    return doWork();
});
~~~

`Future<String>` chỉ có `isDone`/`get`/`cancel`; nó không bắt buộc hỗ trợ callback. Có ba chiến lược thích hợp, tùy quyền kiểm soát:

| Vị trí instrument | Mốc thực sự quan sát | Ưu điểm và giới hạn |
|---|---|---|
| Wrapper quanh `Runnable`/`Callable` trước khi `ExecutorService.submit` | Thời điểm task **bắt đầu** và **rời thân worker** | Biết queue/run time; `finally` chạy cả khi exception; phải bao bọc đúng tác vụ và tránh chồng probe |
| `FutureTask.done()` nếu **bạn sở hữu implementation FutureTask** | Notification khi FutureTask chuyển sang terminal, kể cả cancellation | Hữu ích cho trạng thái Future, nhưng cancellation có thể đến trước khi worker vật lý ngừng |
| Completion listener/callback do framework cung cấp | Mốc observer nhận completion của chính framework | Khớp contract của framework; cần đọc quy tắc thread và cancellation |
| `Future.get()` của caller | Thời điểm caller **nhận** kết quả sau khi chờ | Có thể muộn hơn terminal và bị chặn; không dùng làm mốc completion tuyệt đối |

Không nên khởi tạo một thread chỉ để `get()` cho **mỗi Future**. Điều này tạo thread/wait overhead, có thể làm hệ thống cạn tài nguyên và vẫn chỉ đo thời điểm observer nhận được kết quả. Nếu framework không có callback mà không thể instrument worker, hãy ghi metric mang tên “return latency” và mô tả giới hạn, thay vì tự gán “completion latency” giả.

### Wrapper producer, khi bạn kiểm soát tác vụ

Đoạn **minh họa trong một method có sẵn `executor`, `task` và `metrics`**, không phải chương trình độc lập:

~~~java
long submittedAt = System.nanoTime();
Future<Result> future = executor.submit(() -> {
    long startedAt = System.nanoTime();
    try {
        return task.call();
    } finally {
        long finishedAt = System.nanoTime();
        metrics.recordQueueWait(startedAt - submittedAt);
        metrics.recordExecution(finishedAt - startedAt);
    }
});
~~~

Các mốc `submittedAt`, `startedAt`, `finishedAt` đo **task đã được wrap**, không phải tự động là thời điểm mọi side effect của toàn hệ thống hoàn thành. Nếu công việc bên trong `task.call()` lại kích hoạt công việc async mới rồi trả về sớm, bạn chỉ đang đo **một tầng async**. Tương tự, nếu cancellation ngăn task chạy từ đầu thì thân `Callable` không được gọi, do đó không có mốc `startedAt/finishedAt`; trạng thái Future phải được đo riêng.

## 6. Vì sao “Future complete” cũng phải được định nghĩa đúng?

### Stage nối tiếp có nhiều thời điểm kết thúc

~~~java
CompletableFuture<String> fetched = fetchAsync();
CompletableFuture<String> processed = fetched.thenApplyAsync(this::process, executor);
CompletableFuture<Void> persisted = processed.thenAcceptAsync(this::save, executor);
return persisted;
~~~

Đây là **pseudocode trong instance method** có `fetchAsync`, `process`, `save` và `executor`; không phải file Java tự biên dịch. Nếu API trả **`persisted`**, đo completion của `fetched` sẽ **bỏ sót processing và persistence**. Phải gắn observer lên **stage đúng với lời hứa của API**. Nếu API trả `fetched`, ngược lại không tự đo cả `persisted` vì có thể đó là công việc độc lập ngoài hợp đồng của API.

`thenApply`, `thenApplyAsync`, `thenCompose` và `thenComposeAsync` có semantics khác nhau về scheduling/flattening. Với `thenApply` trả thêm một future lồng bên trong, stage ngoài có thể hoàn tất khi đã tạo ra inner Future chứ chưa chờ inner hoàn tất; khi cần kết quả cuối, `thenCompose` là API dùng để compose/flatten.

### `allOf`, `anyOf`, timeout và cancellation

- `CompletableFuture.allOf(a, b)` mô tả **một stage tổng hợp** và chờ các stage cấu thành hoàn tất theo hợp đồng. Ghi outcome aggregate riêng với outcome của từng thành phần.
- `CompletableFuture.anyOf(a, b)` hoàn tất khi **một** thành phần hoàn tất; không suy ra mọi work còn lại đều dừng.
- `orTimeout(...)` có thể làm `CompletableFuture` terminal với `TimeoutException` ngay cả khi công việc nền chưa thực sự dừng. Tương tự `completeOnTimeout(...)` có thể cung cấp fallback value; future complete không đồng nghĩa tác vụ gốc thành công.
- `cancel(...)` trên `CompletableFuture` chủ yếu đổi trạng thái promise, không mặc nhiên interrupt hoặc rollback side effect.

Vì vậy nên phân biệt rõ **lifecycle của promise/stage** và **lifecycle vật lý của việc đang chạy**, đặc biệt khi đo latency cho RPC, message queue, batch job, streaming hoặc retry.

### Một số API có lazy hoặc nhiều nguồn hoàn tất

Một phương thức trả `CompletionStage` thường đại diện cho công việc đã được khởi động hoặc hoàn tất, nhưng interface không bắt buộc mọi implementation cùng cách scheduling. Những API reactive khác, ví dụ publisher, có thể chỉ kích hoạt công việc sau khi **subscribe**. Không áp công thức “attach `whenComplete` cho `Future`” vào kiểu trả về khác nếu không đọc contract của nó.

Với HTTP client hoặc database async, hãy hỏi “future hoàn tất khi nào?”: khi nhận headers, khi nhận cả body, khi ghi thành công, khi commit hay chỉ khi request được chấp nhận? Đặt tên metric theo **event có ý nghĩa** chứ không dùng nhãn “finished” chung chung.

## 7. Thiết kế instrumentation trong agent: trước/sau method return

Một agent có thể dùng Byte Buddy, ASM hoặc AOP interceptor để ghi `t0` ở method entry và `t1` ở method exit. Với method trả `CompletionStage`, cần thêm observer để tính `t5 - t0` sau này.

~~~text
METHOD ENTRY
    record t0, operation identity, trace context
      |
      v
METHOD EXIT
    if synchronous throw:
        record method.error + method latency
    else:
        record method return latency (t1 - t0)
        if return instanceof CompletionStage:
            attach lightweight completion observer
        return original return object
      |
      v
COMPLETION CALLBACK
    record t5 and outcome of EXACT returned stage
    emit async completion latency (t5 - t0)
    release tracing references/resources safely
~~~

### Những điều agent phải giữ đúng

1. **Không chặn caller:** không gọi `get()` hay `join()` để “đợi đủ thời gian” ngay trong Advice/MethodExit.
2. **Không thay đổi đối tượng return:** attach observer, trả original reference; `whenComplete` trả stage khác có thể làm đổi exception/cancellation semantics nếu vô ý dùng làm return.
3. **Đừng giả định `returnValue` luôn non-null:** method có thể trả `null`; xử lý theo contract thay vì dereference.
4. **Ghi cả synchronous throw:** nếu method chưa trả future đã ném lỗi thì observer sẽ không tồn tại.
5. **Phân loại terminal outcome:** success, failure, cancellation, timeout, và các trường hợp business-specific có thể cần metric riêng. `error != null` không nhất thiết là lỗi hệ thống.
6. **Thực thi observer nhẹ và an toàn:** callback non-async có thể chạy trên thread hoàn thành business task. Không block, không làm I/O đồng bộ quá nặng; đừng để telemetry exception ảnh hưởng stage phụ thuộc.
7. **Quản lý trace context qua thread:** không dựa vào `ThreadLocal` của caller tự xuất hiện trong worker. Lưu correlation ID/span context có giới hạn trong callback hoặc dùng cơ chế context propagation của framework.
8. **Giữ cardinality hợp lý:** đừng gắn user ID, URL chứa tham số nhạy cảm hoặc ID duy nhất vào metric label. Dùng tên operation ổn định và status.
9. **Quan tâm liveness:** Future không bao giờ hoàn tất sẽ giữ observer/reference; cần giám sát pending, timeout nghiệp vụ và memory retention.
10. **Tránh instrument đệ quy:** nếu agent tự gọi logging/executor cũng đang bị instrument, phải có filter chống self-instrumentation, class loader guard và xử lý reentrancy.

Với instrumentation có sampling, phải bảo đảm cùng một invocation dùng chung quyết định sampling giữa mốc method và mốc future; nếu không, dashboard có thể có completion metric nhưng không có corresponding entry hoặc ngược lại.

### Trường hợp Future đã complete tại method exit

Nếu method trả một `CompletableFuture.completedFuture("cached")`, listener được gắn sau method return có thể chạy **ngay trong code gắn listener**. Trong tình huống đó:

~~~text
invocation → completedFuture(...) → method returns already-completed stage
                                    → attach whenComplete → observer runs immediately
~~~

Nếu ghi `t5 - t0`, giá trị bao gồm cả overhead di chuyển từ method return đến observer registration. Đừng suy diễn chính xác “task kết thúc tại t5”; đó là thời điểm quan sát. Nếu hệ thống cần thời gian hoàn tất chính xác đến microsecond, hãy instrument **ngay điểm producer complete** hoặc trong pipeline có thể điều khiển, đồng thời mô tả overhead của probe.

## 8. Checklist về độ chính xác của phép đo

| Câu hỏi khi review | Cách kiểm tra hợp lý |
|---|---|
| Metric “async duration” bắt đầu ở đâu? | Chọn invocation, enqueue hoặc producer start và đặt tên nhất quán |
| Metric kết thúc tại đâu? | Chính stage trả cho caller terminal, hoặc business event được định nghĩa tường minh |
| Có nhầm `t_return` với `t_complete` không? | Với tác vụ bị latch chặn, return vẫn xảy ra trước completion |
| Phương thức có thể trả future đã xong không? | Thử `completedFuture`/`failedFuture` và xem callback đăng ký sau completion |
| Có ghi cả exception và cancellation? | Thử normal, exceptional, cancelled, timeout, synchronous throw |
| `get(timeout)` ném `TimeoutException` có nghĩa future terminal chưa? | Không nhất thiết; kiểm tra lại `isDone`, không tự coi timeout của wait là completion |
| Có đo đúng stage của pipeline không? | Nếu API trả `thenCompose/thenApplyAsync/allOf`, gắn observer lên stage được trả |
| Tác vụ thật có thể tiếp tục sau cancellation/timeout? | Có; cần producer-side điểm đo nếu muốn actual work stop |
| Chạy nhiều thread có ảnh hưởng số đo? | Chênh lệch `nanoTime` trong cùng JVM được dùng cho duration; scheduler/observer latency có overhead |
| Instrumentation có làm đổi API? | Return đúng instance; không chặn thread; telemetry không ném exception qua business stage |

### Một ví dụ dashboard bị sai

Giả sử một lời gọi trả `CompletableFuture` sau 2 ms nhưng xử lý hoàn tất sau 480 ms. Nếu agent ghi `request.duration=2ms` tại `areturn` rồi nhóm vào “async end-to-end latency”, dashboard sẽ báo 2 ms. Trong khi đó người gọi đợi dữ liệu khoảng 480 ms. Đây là **số minh họa**, không phải một benchmark đo được. Cách ghi đúng hơn:

~~~text
method_return_latency = 2 ms
observed_future_completion_latency = ~480 ms
outcome = SUCCESS
~~~

Nếu underlying worker tiếp tục sau khi future bị timeout hoặc cancel, thêm metric `worker_execution_duration` thay vì tự khẳng định `observed_future_completion_latency` là toàn bộ runtime vật lý.

## 9. Câu hỏi tự kiểm tra

1. **Tại sao method exit không chứng minh async task đã hoàn tất?** Vì return value có thể chỉ là handle; producer vẫn có thể đang queue hoặc chạy.
2. **Future luôn chưa xong khi trả về?** Không; có thể đã completed, failed hoặc cancel từ trước. Phải quan sát trạng thái cụ thể.
3. **`isDone() == true` có nghĩa thành công?** Không; có thể failed/cancelled.
4. **Có thể instrument plain `Future` bằng `whenComplete` không?** Không; `whenComplete` thuộc `CompletionStage`/`CompletableFuture`, không thuộc `Future` Java 17.
5. **Đợi `get()` ở interceptor có ổn không?** Không; phá non-blocking behavior và có thể gây deadlock.
6. **`whenCompleteAsync` có thể làm timestamp completion bị trễ không?** Có; observer được schedule thêm.
7. **Nên gắn callback lên `fetched` hay `persisted`?** Lên stage đúng với hợp đồng của phương thức; nếu trả `persisted` thì đo `persisted`.
8. **Future cancelled có nghĩa remote operation đã dừng?** Không nhất thiết; cancellation có thể chỉ thay trạng thái promise.
9. **Callback observer ném exception ảnh hưởng gì?** Stage phụ thuộc do `whenComplete` tạo có thể hoàn tất bất thường; nên giữ observer không ném và không thay return value của caller.
10. **Đồng hồ phù hợp đo duration trong cùng JVM?** `System.nanoTime()`; không dùng wall-clock làm nguồn duy nhất cho chênh lệch ngắn, không so trực tiếp giá trị `nanoTime()` giữa các JVM.

## 10. Tài liệu chuẩn

- [Java SE 21 — `Future`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html): `get`, `isDone`, cancellation, thời điểm result có thể được lấy.
- [Java SE 21 — `CompletableFuture`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html): completion, `whenComplete`, cancellation semantics, `join`, chaining.
- [Java SE 21 — `CompletionStage`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletionStage.html): hợp đồng dependent stage, callbacks và xử lý lỗi.
- [Java SE 21 — `ExecutorService`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html): `submit`, queue, asynchronous execution và shutdown.
- [Java SE 21 — `FutureTask`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/FutureTask.html): `done()` và trạng thái terminal trong implementation FutureTask.
- [Java SE 21 — `System.nanoTime()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#nanoTime()): đo elapsed time dựa trên difference trong cùng JVM.
