# Fork/Join trong Java: Xử lý ngoại lệ, hủy và trạng thái hoàn tất

## 1. Mục tiêu: biết khi nào một ForkJoinTask thực sự thành công

**Fork/Join** xuất hiện từ Java 7 và vẫn là API song song quan trọng trong **Java 17+**. `ForkJoinPool` dùng cơ chế *work stealing* để thực thi các tác vụ chia để trị, thường là `RecursiveTask<V>` có kết quả và `RecursiveAction` không trả kết quả. Cả hai là `ForkJoinTask`, hỗ trợ `fork()`, `join()`, `cancel()` và các phương thức quan sát trạng thái.

Điểm cốt lõi của bài **“Xử lý ngoại lệ, hủy và trạng thái hoàn tất”**: **`isDone() == true` không đồng nghĩa nhiệm vụ thành công**. Một task có thể:

- Hoàn thành bình thường với một kết quả.
- Kết thúc bất thường do `RuntimeException` hoặc `Error`.
- Được đánh dấu canceled, kể cả trước khi bắt đầu, hoặc khi phần thân vẫn chưa thôi chạy.

Một hệ thống xử lý dữ liệu phải hiểu sự khác biệt giữa **task state**, **kết quả tính toán**, **việc worker còn thực thi** và **trạng thái tài nguyên nghiệp vụ**. `cancel(true)` trong `ForkJoinTask` mặc định **không làm gián đoạn (interrupt)** worker như nhiều người lầm tưởng từ `FutureTask`.

Bài tập trung vào ngoại lệ, hủy và trạng thái của Fork/Join, sử dụng API vẫn áp dụng cho Java 17+, không đưa kiến thức lỗi thời vào quy trình.

## 2. Cơ chế cơ bản và nơi ngoại lệ xuất hiện

`RecursiveTask<Integer>` thường chia nhỏ một khoảng rồi tính song song:

```java
static final class SumTask extends RecursiveTask<Integer> {
    private final int from, to;

    SumTask(int from, int to) {
        this.from = from;
        this.to = to;
    }

    @Override
    protected Integer compute() {
        if (to - from <= 2) {
            int total = 0;
            for (int i = from; i < to; i++) {
                total += i;
            }
            return total;
        }

        int mid = (from + to) >>> 1;
        SumTask left = new SumTask(from, mid);
        left.fork();

        int rightResult = new SumTask(mid, to).compute();
        return left.join() + rightResult;
    }
}
```

Đây là một class minh họa bên trong một class có import `java.util.concurrent.RecursiveTask`; `main` đầy đủ ở mục 12.

- `left.fork()` chỉ **sắp xếp task có thể chạy bất đồng bộ**, không chờ kết quả.
- `right.compute()` tính một nhánh ngay tại thread hiện tại.
- `left.join()` chờ task bên trái hoàn tất và lấy kết quả hoặc ném lỗi.
- Nếu nhánh phải ném lỗi trước `left.join()`, nhánh trái có thể vẫn chạy. Đây là lý do cần có chính sách thu hồi subtasks khi root gặp lỗi.
- Sử dụng threshold giúp tránh fork các tác vụ quá nhỏ. Fork/Join thích hợp cho các phép tính CPU-bound có trạng thái độc lập hoặc được đồng bộ rõ ràng.

Nếu một `compute()` ném lỗi, `ForkJoinTask` sẽ đánh dấu bất thường; caller chỉ thấy lỗi khi đợi qua `join/get/invoke` hoặc kiểm tra thông tin trạng thái sau khi task hoàn tất. `fork()` trả về không có nghĩa “đã thành công”.

## 3. Bảng trạng thái chính thức của ForkJoinTask

Java SE 17 cung cấp `isDone()`, `isCompletedNormally()`, `isCompletedAbnormally()`, `isCancelled()` và `getException()`.

| Tình huống cuối | `isDone` | `isCompletedNormally` | `isCompletedAbnormally` | `isCancelled` | `getException` |
| --- | --- | --- | --- | --- | --- |
| Thành công | true | true | false | false | null |
| `compute` ném lỗi | true | false | true | false | Throwable từ tính toán |
| Đã hủy thành công | true | false | true | true | CancellationException |
| Chưa hoàn tất | false | false | false | false | Thường null |

Bảng mô tả trạng thái ổn định của task. Khi các thread chạy song song, trạng thái có thể thay đổi giữa hai lần đọc cờ. Để nhận kết quả đáng tin, dùng `join()` hoặc `get()` để chờ completion rồi mới phân loại.

### 3.1. `isDone()`

Trả `true` khi task đã hoàn tất *theo một trong ba trạng thái*. Cũng đúng khi task bị cancel **mà chưa hề được thực thi**. Vì vậy:

```java
if (task.isDone()) {
    // Không đủ để tuyên bố success.
}
```

`isDone` không chứng minh mọi child tasks đã thành công, không chứng minh dữ liệu được commit đúng, và khi cancellation xảy ra trong lúc body chạy thì không bảo đảm body đã thoát ngay.

### 3.2. `isCompletedNormally()`

`true` nếu task hoàn tất **không bị hủy và không ném exception**. Đây là tín hiệu trạng thái thành công của task. Nhưng code trong `compute()` vẫn có thể chứa bug, giá trị sai hoặc catch lỗi rồi trả fallback, nên phép kiểm chứng nghiệp vụ vẫn phải có.

### 3.3. `isCompletedAbnormally()`

`true` nếu task đã **bị hủy hoặc gặp exception**. Đây không phải “chỉ báo lỗi tính toán” riêng biệt. Để phân loại, kiểm tra `isCancelled()` trước; nếu không canceled nhưng abnormal, xem `getException()`.

### 3.4. `isCancelled()`

`true` khi task được đánh dấu canceled trước khi hoàn tất bình thường. Một task canceled có thể chưa bao giờ chạy; cũng có thể phần thân đang tiếp tục xử lý side effects khi cờ này đã true.

### 3.5. `getException()`

Trả Throwable nếu task kết thúc do exception, `CancellationException` nếu bị hủy, hoặc `null` nếu không có lỗi **hay task chưa hoàn tất**. Do đó **`getException()==null` không đủ để kết luận success**.

### 3.6. Mẫu phân loại sau khi đợi

```java
try {
    Integer result = task.join();
    // Nếu tới đây, task join trả kết quả bình thường.
} catch (CancellationException cancelled) {
    // Hủy, không phải lỗi tính toán thường.
} catch (RuntimeException failed) {
    // Lỗi tính toán unchecked; kiểm tra cause/context.
}
```

Trong ví dụ này `task` là `ForkJoinTask<Integer>` đã submit và `CancellationException` được import. `Error` không thuộc `RuntimeException`; không tự ý catch `Throwable` để im lặng bỏ qua lỗi nghiêm trọng.

## 4. `join()` và `get()` có hợp đồng khác nhau

### 4.1. `join()`

`join()` chờ task hoàn tất và trả kết quả. Khi task lỗi, `join()` ném một exception unchecked (`RuntimeException` hoặc `Error`), **không bọc vào `ExecutionException`**. Khi canceled, nó ném `CancellationException`.

Ngoài ra, `join()` **không thoát sớm bằng `InterruptedException` khi thread gọi bị interrupt**. Tại bên trong cây Fork/Join, `join()` thường là lựa chọn tự nhiên; ở biên hệ thống cần deadline/interruptible wait, `get(timeout, unit)` có thể phù hợp hơn.

### 4.2. `get()`

`ForkJoinTask` implements `Future`, vì vậy `get()` có semantics của Future:

- Kết quả bình thường → trả giá trị.
- `compute()` ném lỗi → ném `ExecutionException`, lấy nguyên nhân qua `getCause()`.
- Task đã hủy → ném **`CancellationException` trực tiếp**, không phải `ExecutionException`.
- Thread chờ bị interrupt trong hoàn cảnh được tài liệu chỉ định → `InterruptedException`.

```java
try {
    Integer value = task.get();
    System.out.println(value);
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    // Propagate/cleanup phù hợp.
} catch (ExecutionException failed) {
    Throwable underlying = failed.getCause();
    // Log/rethrow lỗi gốc phù hợp.
} catch (CancellationException cancelled) {
    // Task đã hủy.
}
```

Đây là snippet đặt trong phương thức, có import `java.util.concurrent.*`. Đừng bắt mỗi `ExecutionException` rồi tưởng đã xử lý cả cancellation.

### 4.3. `get(timeout, unit)`

```java
try {
    Integer value = task.get(2, TimeUnit.SECONDS);
} catch (TimeoutException timedOut) {
    // Timeout của việc chờ, không tự hủy task.
}
```

Đây chỉ là đoạn trích minh họa, cần xử lý thêm `InterruptedException`/`ExecutionException`/`CancellationException`. `TimeoutException` **không đồng nghĩa task bị cancel**. Nếu cần dừng work sau timeout, ứng dụng phải thực hiện cancellation riêng và xác nhận worker/subtasks an toàn.

### 4.4. `invoke()` và `pool.invoke(root)`

`ForkJoinTask.invoke()` cố thực thi task trong caller thread rồi chờ, trả kết quả hoặc ném unchecked exception. `ForkJoinPool.invoke(task)` gửi một root task tới pool và đợi; nếu task gặp unchecked exception/Error, lỗi được ném lại cho caller.

### 4.5. Bảng so sánh

| API | Chờ? | Khi task lỗi | Khi task canceled | Tác dụng |
| --- | --- | --- | --- | --- |
| `fork` | Không | Không trả lỗi computation tại đây | Không phải kết quả hủy | Schedule subtask |
| `join` | Có | RuntimeException/Error | CancellationException | Thu kết quả trong cây |
| `get` | Có | ExecutionException | CancellationException | Future-style wait |
| `get(timeout, unit)` | Có deadline | ExecutionException | CancellationException | Phân biệt timeout |
| `invoke` | Có | Unchecked | CancellationException | Bắt đầu và đợi |
| `quietlyJoin` | Có | Không ném lỗi task | Không ném cancellation của task | Thu thập trạng thái sau |

Không áp sai cách dùng `CompletableFuture.join()`, `FutureTask.cancel(true)` hoặc `Thread.interrupt` sang `ForkJoinTask` chỉ vì tên phương thức tương tự.

## 5. Lỗi tính toán được lan truyền ra sao?

### 5.1. Lỗi runtime tại leaf

```java
static final class FailingTask extends RecursiveTask<Integer> {
    @Override
    protected Integer compute() {
        throw new IllegalArgumentException("invalid leaf");
    }
}
```

Sau khi submit vào `ForkJoinPool`, task này có trạng thái:

```text
isDone                  true
isCompletedNormally     false
isCompletedAbnormally   true
isCancelled             false
getException            IllegalArgumentException
```

`task.get()` bọc lỗi vào `ExecutionException`, còn `task.join()` ném unchecked error. Ví dụ đầy đủ ở mục 12 kiểm tra cả hai và không phụ thuộc thứ tự worker scheduling.

### 5.2. Lỗi do input không hợp lệ

Khi `compute()` nhận dữ liệu không đáp ứng bất biến, nên ném một unchecked exception có message/cause hữu ích thay vì âm thầm trả 0:

```java
if (from < 0 || to < from) {
    throw new IllegalArgumentException("Invalid range");
}
```

Một task catch exception rồi trả 0 sẽ được đánh dấu hoàn tất bình thường, dù kết quả nghiệp vụ có thể bị sai. Chỉ dùng fallback nếu được thiết kế như một kết quả có trạng thái riêng.

### 5.3. Checked exceptions trong `compute()`

`RecursiveTask.compute()` không khai báo checked exception như `IOException`. Bạn **không thể** override bằng `protected Integer compute() throws IOException`; sẽ không compile.

Nếu phép toán thực sự có checked exception:
- Catch và bọc vào unchecked exception với **cause** rõ ràng.
- Hoặc cân nhắc abstraction/executor phù hợp hơn, đặc biệt khi tác vụ chủ yếu I/O blocking.
- Không catch rồi bỏ qua lỗi hoặc tự đổi thành thành công.

`ForkJoinTask` lý tưởng thực hiện các leaf computations ngắn, độc lập. Javadoc khuyến nghị hạn chế synchronization/blocking I/O; `ForkJoinPool.ManagedBlocker` được thiết kế cho trường hợp blocking chuyên biệt cần hợp tác với pool.

### 5.4. `Error` khác `RuntimeException`

`Error` có thể báo sự cố nghiêm trọng. Không viết `catch (Throwable ignored) { return 0; }` chỉ để giữ cho task “thành công”. Dùng `finally` cho cleanup, giữ nguyên lỗi khi cần propagate; ở ranh giới ngoài có thể logging/reporting theo chính sách.

### 5.5. Giữ thông tin lỗi ở caller

Đối với `ExecutionException`, bảo toàn `getCause()` để phân tích. Nếu log, nên ghi loại exception, context vừa đủ, task id/partition, không tiết lộ dữ liệu nhạy cảm. Đừng viết unit test so sánh toàn bộ stack trace vì stack trace có thể khác khi lỗi được truyền giữa các worker threads.

## 6. Hủy task: `cancel(false)` và `cancel(true)`

### 6.1. Default `ForkJoinTask.cancel(boolean)` **không interrupt worker**

Theo tài liệu Oracle Java SE 17, tham số `mayInterruptIfRunning` **không có hiệu lực** trong implementation mặc định của `ForkJoinTask` vì cancellation **không dùng interrupts để điều khiển worker**. Vậy:

```java
boolean accepted = task.cancel(true);
```

`true` chỉ nói task đã ở trạng thái canceled sau lời gọi. Không được khẳng định `Thread.interrupt` đã được gửi, phần thân `compute()` đã kết thúc hay side effects đã rollback.

### 6.2. Cancel trước khi bắt đầu

Nếu task chưa submit, `cancel(false)` thường thành công ngay; theo contract, nó bị đánh dấu:

- `isDone()==true`.
- `isCancelled()==true`.
- `isCompletedAbnormally()==true`.
- `getException()` là `CancellationException`.
- `join()`/`get()` ném `CancellationException`.
- Body **không cần được chạy** để đạt trạng thái done.

Điều này chứng minh rõ `isDone` không đồng nghĩa đã thực thi xong `compute()`.

### 6.3. Cancel khi task đã chạy

Nếu worker đã vào `compute()`, cancel có thể **đánh dấu task done/canceled trước khi body thực sự thoát**. Code trong worker có thể tiếp tục ghi vào shared data/file sau khi caller thấy `isDone()==true`.

Muốn dừng đúng, cần **cooperative cancellation**: một cờ `AtomicBoolean`/`volatile` ở phạm vi chia sẻ, các leaf tasks kiểm tra cờ ở điểm hợp lý, rồi return/fail có chủ đích. Nếu có resource dùng chung, chờ worker bodies thật sự kết thúc trước khi giải phóng.

### 6.4. Hủy không phải rollback

`cancel(true)` không:
- Undo những byte đã ghi.
- Roll back database transaction.
- Interrupt một `ForkJoinTask` đang chạy theo default behavior.
- Tự hủy đồng bộ tất cả subtasks.
- Đóng `ForkJoinPool`.
- Chứng minh mọi worker đã ngừng truy cập dữ liệu.

Nếu side effects là yêu cầu nghiệp vụ, cần staging, transaction, idempotency, compensation hoặc cleanup policy độc lập với cancellation state.

### 6.5. Cancel có thể không thành công

Nếu task đã hoàn tất hoặc không thể hủy vì lý do khác, `cancel(...)` có thể trả `false`. Trong môi trường có race giữa completion và cancellation, hãy phân loại status cuối và đừng ghi log “cancelled” chỉ vì đã gửi một yêu cầu.

Không gọi `fork()` lặp lại với task object cũ trong khi lifecycle của nó chưa an toàn. Muốn retry, thường tạo **task instance mới**.

## 7. Ví dụ hủy khi đang chạy: phân biệt task state với body

Mục 12 có `ControlledTask` sử dụng:
- `started` latch xác nhận worker đã bắt đầu.
- `release` latch giữ body lại để caller thực hiện cancellation.
- `stopRequested` là `AtomicBoolean` dùng để hợp tác dừng.
- `bodyFinished` latch xác nhận code `compute()` đã thoát khỏi phần thân.

Luồng kiểm thử:

```text
ForkJoinPool worker       Main thread
-----------------         --------------------------
started.countDown()
release.await(...) ------> started.await(...) returns
                          stopRequested.set(true)
                          running.cancel(true) -> true
                          running.isDone() -> true
release.countDown() <----- release.countDown()
đọc stopRequested=true
thoát body, countDown
                          bodyFinished.await(...) -> true
                          workerInterrupted=false
                          running.get() throws CancellationException
```

Latches có timeout chỉ dùng trong **test có điều khiển**, không phải pattern CPU-bound nên sao chép vào production. Ngoài đời nên tách công việc thành các vòng lặp ngắn, thỉnh thoảng kiểm tra stop flag và tránh block worker.

Điểm học được: **trạng thái cancelled của `ForkJoinTask` có thể đi trước việc code bên trong worker ngừng**. Vì thế không giải phóng buffer/resource ngay chỉ vì `isDone()==true` khi đang hủy.

## 8. Xử lý exception từ subtasks và `invokeAll`

### 8.1. Khi một nhánh fail, nhánh khác có thể còn chạy

Giả sử:

```java
LeftTask left = new LeftTask(...);
left.fork();

int right = computeRight();  // Có thể ném exception.
int leftValue = left.join();
return leftValue + right;
```

Đây là **pseudocode**, không phải chương trình runnable độc lập. Nếu `computeRight()` ném trước `left.join()` thì nhánh trái có thể vẫn pending. Root task trả exception nhưng sibling tiếp tục tác động dữ liệu dùng chung.

Không nên đóng tài nguyên của child hoặc publish kết quả một cách tùy tiện tại thời điểm root exception; cần có strategy thu hồi, hợp tác hủy và xác nhận tasks đã đạt trạng thái an toàn.

### 8.2. `ForkJoinTask.invokeAll(...)` gặp exception

Theo Javadoc Java 17, `ForkJoinTask.invokeAll` fork và join một nhóm tasks. Nếu một task gặp exception:
- Phương thức có thể ném unchecked exception đó.
- Các tasks còn lại **có thể** bị cancel.
- Trạng thái riêng của mọi task **không được bảo đảm khi return bất thường**; có task đã xong, có task canceled hoặc chưa xử lý.
- Nếu nhiều task gặp lỗi, phương thức có thể chọn một trong các exception để ném.

Vì vậy không được hiểu “`invokeAll` ném exception” là “toàn bộ siblings đã chắc chắn dừng”. Hãy kiểm tra từng task và áp dụng cleanup/quiescence nếu chia sẻ mutable state.

### 8.3. Một mẫu quan sát

```java
try {
    ForkJoinTask.invokeAll(tasks);
} catch (RuntimeException failure) {
    for (ForkJoinTask<?> task : tasks) {
        if (task.isCancelled()) {
            // Hủy.
        } else if (task.isCompletedAbnormally()) {
            Throwable why = task.getException();
            // Thất bại.
        } else if (!task.isDone()) {
            // Chưa có trạng thái cuối.
        }
    }
}
```

Đây là snippet minh họa với `tasks` là một collection hợp lệ. Nó **chỉ chụp trạng thái ณ thời điểm kiểm tra**, không buộc các tasks đang chạy phải dừng.

### 8.4. Gợi ý thiết kế khi muốn tất cả kết quả

- Đối với task thuần tính toán: mỗi child trả một value, root chỉ hợp nhất khi đủ kết quả.
- Nếu một child fail: định nghĩa fail-fast hay collect-all từ đầu.
- Nếu cần collect-all, chờ từng child theo semantics phù hợp và tổng hợp errors; đừng giả định `invokeAll` luôn hoàn tất tất cả trong nhánh exceptional.
- Nếu tasks có side effects: dùng cooperative stop/ownership của tài nguyên, không để root thoát bỏ quên child.
- Với transaction, dừng/rollback do transaction manager chứ không do `cancel` tự động.

## 9. `quietlyJoin` và API completion thủ công

### 9.1. `quietlyJoin()` không ném task exception

`quietlyJoin()` đợi task nhưng không trả result và không ném exception/cancellation của task. Nó có ích khi muốn đợi nhiều tasks để kiểm tra các cờ sau cùng. Tuy nhiên nếu gọi `quietlyJoin` rồi bỏ qua `getException` và `isCancelled`, lỗi có thể bị **nuốt**.

### 9.2. `complete(V)`

`complete(value)` đánh dấu task hoàn thành bình thường với value được cấp nếu chưa canceled/aborted. Đây là API nâng cao cho task bất đồng bộ/tùy biến, không phải cách sửa một phép toán sai rồi biến status thành success. Nếu body đang gây side effects, complete sớm có thể dẫn tới nhầm lẫn giữa completion state và an toàn tài nguyên.

### 9.3. `completeExceptionally(Throwable)`

`completeExceptionally(ex)` ghi nhận task hoàn tất bất thường. Theo Javadoc, nếu cung cấp checked exception không phải `RuntimeException`/`Error`, exception thực sự quan sát khi join có thể là một `RuntimeException` với cause là lỗi ban đầu. API này hữu ích cho tác vụ tự quản lý completion, không phải lựa chọn mặc định cho mọi phép chia để trị.

### 9.4. `reinitialize()` và retry

`reinitialize()` là API nâng cao có điều kiện nghiêm ngặt: task phải chưa fork hoặc đã hoàn tất và mọi outstanding joins đã kết thúc. Nếu cần retry, cách dễ kiểm chứng hơn là **tạo task mới**; không reset task object trong khi worker/other callers có thể còn tham chiếu nó.

## 10. Phân biệt task cancellation và pool shutdown

### 10.1. Hủy một task

`task.cancel(false)` chỉ ảnh hưởng trạng thái task ấy. Những tasks khác trong `ForkJoinPool` vẫn có thể làm việc; những children do root fork không tự biến thành một transaction cancel-all.

### 10.2. Shutdown pool riêng

`ForkJoinPool pool = new ForkJoinPool(2)` tạo một pool do scope hiện tại sở hữu. Khi công việc kết thúc:

```java
pool.shutdown();

try {
    if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
        pool.shutdownNow();
        if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Pool still running");
        }
    }
} catch (InterruptedException interrupted) {
    pool.shutdownNow();
    Thread.currentThread().interrupt();
    throw interrupted;
}
```

Đoạn này giả định đã xử lý kết quả các tasks và có import phù hợp. Timeout 5 giây là ví dụ, không phải giá trị chuẩn cho mọi workload. `shutdown()` không tự chờ pool terminated; `shutdownNow()` chỉ cố hủy/dừng best effort.

### 10.3. Không shutdown `commonPool()` như pool riêng

`ForkJoinPool.commonPool()` là pool chia sẻ do runtime quản lý; `shutdown()` và `shutdownNow()` gọi lên common pool **không làm thay đổi trạng thái hoạt động** theo Oracle Java SE 17. Không coi commonPool là resource có thể tự đóng theo từng request.

### 10.4. `awaitQuiescence` không thay cho kết quả nghiệp vụ

`awaitQuiescence` cố chờ/giúp pool đạt trạng thái quiescent theo contract, nhưng không tự kiểm tra mọi task có exception, cancellation, partial result hoặc side effects. Nếu cần biết root task thành công, luôn dùng `join/get` và báo failures.

## 11. Kỹ thuật kiểm thử trạng thái không flaky

Concurrency tests dễ sai khi chỉ `Thread.sleep(100)` rồi đọc cờ, bởi scheduling phụ thuộc CPU/OS. Mục 12 dùng các bước deterministic:

1. Một `SumTask` tính tổng từ 1 tới 8 là 36, không side effects.
2. Một `FailingTask` luôn ném `IllegalArgumentException`. Caller `get()` để đợi exception rồi kiểm tra `join()` và trạng thái.
3. Một `RecursiveTask` **chưa submit** được `cancel(false)` để chứng minh canceled-before-start có `isDone=true`.
4. Một `ControlledTask` đã bắt đầu, dùng latches có timeout để giữ worker ở điểm biết trước; caller đặt `stopRequested`, gọi `cancel(true)` rồi giải phóng latch, đợi `bodyFinished`.
5. Pool riêng `ForkJoinPool(2)` được shutdown và awaitTermination trong `finally`.
6. Output dựa vào statuses, exceptions và giá trị cố định, không dựa vào worker thread name hoặc sleep.

**Lưu ý:** latch blocking chỉ được dùng cho test nhỏ có deadline, không phải thuật toán Fork/Join CPU-bound thông thường. Production dùng cooperative checks, chia nhỏ việc và tránh blocking không cần thiết.

## 12. Chương trình Java 17+ độc lập đã kiểm thử

Lưu tệp **`ForkJoinCompletionDemo.java`**:

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

public final class ForkJoinCompletionDemo {
    static void check(boolean condition, String label) {
        if (!condition) throw new AssertionError(label);
    }

    static final class SumTask extends RecursiveTask<Integer> {
        private final int from, to;
        SumTask(int from, int to) {
            this.from = from;
            this.to = to;
        }
        @Override protected Integer compute() {
            if (to - from <= 2) {
                int total = 0;
                for (int i = from; i < to; i++) total += i;
                return total;
            }
            int mid = (from + to) >>> 1;
            SumTask left = new SumTask(from, mid);
            left.fork();
            int right = new SumTask(mid, to).compute();
            return left.join() + right;
        }
    }

    static final class FailingTask extends RecursiveTask<Integer> {
        @Override protected Integer compute() {
            throw new IllegalArgumentException("invalid leaf");
        }
    }

    static final class ControlledTask extends RecursiveTask<Integer> {
        final CountDownLatch started = new CountDownLatch(1);
        final CountDownLatch release = new CountDownLatch(1);
        final CountDownLatch bodyFinished = new CountDownLatch(1);
        final AtomicBoolean stopRequested = new AtomicBoolean(false);
        final AtomicBoolean workerInterrupted = new AtomicBoolean(false);
        final AtomicBoolean exitedCooperatively = new AtomicBoolean(false);

        @Override protected Integer compute() {
            started.countDown();
            try {
                if (!release.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("test latch timeout");
                }
                if (stopRequested.get()) {
                    exitedCooperatively.set(true);
                    return -1;
                }
                return 42;
            } catch (InterruptedException ex) {
                workerInterrupted.set(true);
                Thread.currentThread().interrupt();
                return -2;
            } finally {
                bodyFinished.countDown();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            SumTask normal = new SumTask(1, 9);
            int sum = pool.invoke(normal);
            check(sum == 36, "sum");
            System.out.println("normal.result=" + sum);
            System.out.println("normal.done=" + normal.isDone());
            System.out.println("normal.completedNormally="
                    + normal.isCompletedNormally());
            System.out.println("normal.abnormal="
                    + normal.isCompletedAbnormally());

            FailingTask failed = new FailingTask();
            pool.execute(failed);
            String getCause;
            try {
                failed.get();
                throw new AssertionError("get must fail");
            } catch (ExecutionException expected) {
                getCause = expected.getCause().getClass().getSimpleName();
                check(expected.getCause() instanceof IllegalArgumentException,
                        "Unexpected get cause");
            }
            String joinThrown;
            try {
                failed.join();
                throw new AssertionError("join must fail");
            } catch (IllegalArgumentException expected) {
                joinThrown = expected.getClass().getSimpleName();
            }
            System.out.println("failed.getCause=" + getCause);
            System.out.println("failed.joinThrows=" + joinThrown);
            System.out.println("failed.done=" + failed.isDone());
            System.out.println("failed.completedNormally="
                    + failed.isCompletedNormally());
            System.out.println("failed.abnormal="
                    + failed.isCompletedAbnormally());
            System.out.println("failed.exceptionType="
                    + failed.getException().getClass().getSimpleName());

            RecursiveTask<Integer> notStarted = new RecursiveTask<>() {
                @Override protected Integer compute() {
                    return 99;
                }
            };
            boolean accepted = notStarted.cancel(false);
            check(accepted, "cancel before start");
            System.out.println("cancelBeforeStart.accepted=" + accepted);
            System.out.println("cancelBeforeStart.done=" + notStarted.isDone());
            System.out.println("cancelBeforeStart.cancelled="
                    + notStarted.isCancelled());
            System.out.println("cancelBeforeStart.abnormal="
                    + notStarted.isCompletedAbnormally());
            System.out.println("cancelBeforeStart.exceptionType="
                    + notStarted.getException().getClass().getSimpleName());
            try {
                notStarted.join();
                throw new AssertionError("cancelled join must fail");
            } catch (CancellationException expected) {
                System.out.println("cancelBeforeStart.joinThrows="
                        + expected.getClass().getSimpleName());
            }

            ControlledTask running = new ControlledTask();
            pool.execute(running);
            try {
                check(running.started.await(5, TimeUnit.SECONDS),
                        "worker did not start");
                running.stopRequested.set(true);
                boolean cancelled = running.cancel(true);
                check(cancelled, "running cancellation");
                System.out.println("running.cancelAccepted=" + cancelled);
                System.out.println("running.taskDoneAfterCancel="
                        + running.isDone());
            } finally {
                running.release.countDown();
            }
            check(running.bodyFinished.await(5, TimeUnit.SECONDS),
                    "body did not finish");
            check(running.exitedCooperatively.get(), "cooperative stop");
            System.out.println("running.workerInterrupted="
                    + running.workerInterrupted.get());
            System.out.println("running.cooperativeStop="
                    + running.exitedCooperatively.get());
            System.out.println("running.cancelled=" + running.isCancelled());
            try {
                running.get();
                throw new AssertionError("cancelled get must fail");
            } catch (CancellationException expected) {
                System.out.println("running.getThrows="
                        + expected.getClass().getSimpleName());
            }
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
                if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("pool still running");
                }
            }
        }
        System.out.println("pool.terminated=" + pool.isTerminated());
        System.out.println("checks=PASS");
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 ForkJoinCompletionDemo.java
java ForkJoinCompletionDemo
```

**Stdout chính xác đã kiểm chứng khi chạy chương trình:**

```text
normal.result=36
normal.done=true
normal.completedNormally=true
normal.abnormal=false
failed.getCause=IllegalArgumentException
failed.joinThrows=IllegalArgumentException
failed.done=true
failed.completedNormally=false
failed.abnormal=true
failed.exceptionType=IllegalArgumentException
cancelBeforeStart.accepted=true
cancelBeforeStart.done=true
cancelBeforeStart.cancelled=true
cancelBeforeStart.abnormal=true
cancelBeforeStart.exceptionType=CancellationException
cancelBeforeStart.joinThrows=CancellationException
running.cancelAccepted=true
running.taskDoneAfterCancel=true
running.workerInterrupted=false
running.cooperativeStop=true
running.cancelled=true
running.getThrows=CancellationException
pool.terminated=true
checks=PASS
```

### 12.1. Kết quả tính tổng

`SumTask(1,9)` cộng `1+2+3+4+5+6+7+8=36`. Sau `pool.invoke`, `normal.isCompletedNormally` là `true` còn `normal.isCompletedAbnormally` là `false`. Lịch của workers có thể khác giữa các lần chạy nhưng kết quả tính tổng không thay đổi.

### 12.2. Lỗi unchecked và hai kiểu lấy kết quả

`FailingTask` ném `IllegalArgumentException("invalid leaf")`. `failed.get()` ném `ExecutionException` có `getCause()` là `IllegalArgumentException`. `failed.join()` ném `IllegalArgumentException`, không bọc `ExecutionException`. Do đó `failed.done=true`, `failed.completedNormally=false`, `failed.abnormal=true` và `getException()` cho đúng loại lỗi.

### 12.3. Cancel trước khi schedule

Task `notStarted` chưa chạy đã `cancel(false)`; `isDone=true`, `isCancelled=true`, `getException` và `join` cho `CancellationException`. Đây là ví dụ chứng minh task terminal state không phải bằng chứng body đã chạy.

### 12.4. Cancel khi body đang chạy

`ControlledTask` bắt đầu trên worker rồi chờ latch. Caller bật cờ stop và gọi `cancel(true)`. Kết quả `running.taskDoneAfterCancel=true` xuất hiện **trước** khi worker được giải phóng khỏi latch. Sau đó `bodyFinished.await` xác minh body đã ngừng. `running.workerInterrupted=false` xác nhận default cancel không gửi interrupt trong lần thử này; `running.cooperativeStop=true` cho thấy worker tự đọc cờ và thoát.

Dù `compute()` đã return một sentinel nội bộ, trạng thái task vẫn canceled, nên `running.get()` ném `CancellationException`. Không dùng sentinel ấy làm kết quả hợp lệ.

### 12.5. Pool shutdown

Pool thuộc scope `main`, được gọi `shutdown` trong `finally` rồi `awaitTermination`. Vì đây là custom pool và các tasks demo đã thoát, `pool.terminated=true`. Không gọi shutdown `commonPool()`.

## 13. Kiểm thử lỗi và trường hợp biên

| Ca kiểm thử | Kỳ vọng | Sai lầm phổ biến |
| --- | --- | --- |
| `RecursiveTask` bình thường | Done=true, Normally=true, Abnormally=false | Chỉ assert Done |
| `compute` ném IllegalArgumentException | Abnormally=true, Cancelled=false | Nhầm với cancellation |
| `join` sau failure | Ném RuntimeException/Error | Bắt mỗi ExecutionException |
| `get` sau failure | ExecutionException với cause đúng | Mất cause |
| `get` sau cancellation | CancellationException trực tiếp | Bắt nhầm ExecutionException |
| Cancel trước start | Done=true, Cancelled=true dù không chạy | Coi Done là đã thực thi |
| Cancel khi đang chạy | Status canceled trước khi body có thể dừng | Reuse resource sớm |
| `cancel(true)` default | Không dùng interrupt để điều khiển | Nghĩ worker đã nhận interrupt |
| `get(timeout)` hết hạn | Timeout không tự cancel | Gán status Cancelled |
| `getException()==null` trước completion | Không kết luận success | Ghi success giả |
| `invokeAll` khi một task fail | Các sibling states không được bảo đảm | Tưởng tất cả đều done |
| `quietlyJoin` sau task fail | Không throw; phải tự kiểm tra status | Nuốt lỗi |
| `pool.shutdown` | Bắt đầu shutdown, không tự chờ | Coi terminated ngay |
| `pool.shutdownNow` | Best effort | Coi worker dừng chắc chắn |
| `commonPool.shutdown` | Không thay đổi common pool run state | Coi common pool thuộc job |
| Checked exception trong `compute` | Cần wrap/cause hoặc API phù hợp | Override compute throws IOException |
| Retry cùng task object | Không an toàn nếu task chưa hoàn tất/joins còn pending | Re-fork tùy tiện |

### 13.1. Không dựa vào sleep để đồng bộ test

`Thread.sleep(100)` không chứng minh một task đã bắt đầu hay đã kết thúc; scheduling thay đổi theo máy. Dùng latches trong test có deadline, `Future.get` hoặc các phương thức trạng thái sau khi đã đợi để kiểm tra hành vi.

### 13.2. Lỗi từ một sibling không chứng minh toàn bộ sibling đã dừng

Khi root gặp failure trong một nhánh, các nhánh khác có thể đang chạy. Đừng đóng dữ liệu dùng chung dựa duy nhất vào exception của root; xác định cleanup policy dựa vào child ownership và cooperative stop.

### 13.3. Lỗi đã bị catch và “biến mất”

Nếu `compute()` catch mọi exception rồi trả mặc định, task có thể được đánh dấu normally dù dữ liệu sai. Nếu fallback là yêu cầu thật, trả result có metadata về failure/fallback, không giấu exception.

### 13.4. Hết timeout nhưng worker vẫn chạy

`get(timeout,unit)` hết giờ chờ không có nghĩa đang an toàn để hủy tài nguyên. Cần xác định remaining work, gửi stop signal nếu có, và đợi trạng thái an toàn.

## 14. Checklist code review

- [ ] Tách biệt success/failure/cancel, không dùng `isDone` như success.
- [ ] Phân biệt `isCompletedNormally` và `isCompletedAbnormally`.
- [ ] Xem `isCancelled` trước khi phân loại abnormal exception.
- [ ] Không coi `getException()==null` là completed normally nếu task chưa xong.
- [ ] `join` và `get` được catch theo exception model khác nhau.
- [ ] `get(timeout)` được xử lý riêng với cancellation.
- [ ] Nếu dùng `quietlyJoin`, luôn kiểm tra states sau đó.
- [ ] Lỗi không bị catch và im lặng trả 0.
- [ ] `ExecutionException.getCause` được giữ khi logging/propagate.
- [ ] Không fork child rồi bỏ quên khi nhánh còn lại có thể fail.
- [ ] `invokeAll` gặp lỗi được xử lý theo trạng thái riêng từng task.
- [ ] `cancel(true)` không bị hiểu là worker interrupt mặc định.
- [ ] Nếu side effects, có cờ hợp tác dừng và confirmation body đã thoát.
- [ ] Không dùng cancellation để giả định rollback tệp/database.
- [ ] Không reuse một task object khi lifecycle/joins chưa rõ.
- [ ] Fork/Join không chứa I/O blocking dài tùy tiện.
- [ ] Custom pool do đúng owner shutdown và awaitTermination.
- [ ] Không shutdown commonPool như resource riêng.
- [ ] Tests dùng latches/timeout, không dùng sleep suy diễn.
- [ ] Java 17+ code/stdout được kiểm chứng ở JDK thực.

## 15. Câu hỏi ôn tập

**Câu 1.** `isDone()==true` có luôn nghĩa thành công?  
**Đáp án:** Không. Nó đúng cả khi task failed hoặc canceled.

**Câu 2.** `isCompletedAbnormally()` có phân biệt failure với cancellation?  
**Đáp án:** Không. Dùng thêm `isCancelled` và `getException`.

**Câu 3.** `getException()==null` có đủ để khẳng định thành công không?  
**Đáp án:** Không. Task có thể chưa hoàn tất.

**Câu 4.** `join()` ném gì nếu task gặp RuntimeException?  
**Đáp án:** Lỗi unchecked, không phải ExecutionException.

**Câu 5.** `get()` ném gì khi task gặp lỗi?  
**Đáp án:** ExecutionException có cause là lỗi của phép tính.

**Câu 6.** `get()` ném gì khi task bị cancel?  
**Đáp án:** CancellationException trực tiếp.

**Câu 7.** `get(timeout)` ném TimeoutException có nghĩa task đã bị cancel chưa?  
**Đáp án:** Chưa. Đó chỉ là deadline chờ của caller.

**Câu 8.** `join()` có ném InterruptedException khi caller bị interrupt không?  
**Đáp án:** Không, theo ForkJoinTask.join contract.

**Câu 9.** `ForkJoinTask.cancel(true)` mặc định có interrupt worker không?  
**Đáp án:** Không. Tham số mayInterruptIfRunning không ảnh hưởng default implementation.

**Câu 10.** Vì sao task bị canceled vẫn có thể tác động dữ liệu?  
**Đáp án:** Body có thể đã bắt đầu và chưa dừng khi status canceled, nên cần cooperative stop.

**Câu 11.** `invokeAll` ném lỗi có bảo đảm mọi child đã dừng?  
**Đáp án:** Không. Javadoc nói trạng thái của từng task không được bảo đảm khi return bất thường.

**Câu 12.** `quietlyJoin` có làm task lỗi trở nên thành công?  
**Đáp án:** Không. Nó không ném lỗi task; phải kiểm tra status.

**Câu 13.** Có nên retry bằng fork lại một task đang chạy không?  
**Đáp án:** Không. Tạo task mới hoặc chỉ reinitialize khi đáp ứng đầy đủ điều kiện API.

**Câu 14.** `shutdownNow` có rollback side effects không?  
**Đáp án:** Không. Chỉ best effort; resource transaction thuộc nghiệp vụ.

**Câu 15.** `commonPool` có được shutdown như pool riêng sau mỗi request không?  
**Đáp án:** Không. Java API coi common pool là runtime-shared và lệnh shutdown không thay đổi run state của nó.

**Câu 16.** Vì sao nên dùng task CPU-bound thay vì blocking I/O trong Fork/Join?  
**Đáp án:** Blocking workers kéo dài có thể làm giảm khả năng progress của pool; cần abstraction thích hợp hoặc ManagedBlocker khi có cơ sở.

## 16. Kết luận và tài liệu chính thức

Khi dùng **Fork/Join**, hãy phân biệt:

- **Success:** `isCompletedNormally()==true`, `join/get` trả kết quả.
- **Failure:** `isCompletedAbnormally()==true` và `isCancelled()==false`; `getException` có Throwable, `join` ném unchecked, `get` bọc lỗi trong `ExecutionException`.
- **Cancellation:** `isCancelled()==true`, `join/get` ném `CancellationException`, và `cancel(true)` mặc định **không interrupt worker**.
- **Timeout:** hết thời hạn đợi, không tự biến task thành canceled.
- **Siblings/pool:** một task failed không tự đảm bảo những tasks khác đã ngừng, và cancellation không thay việc quản lý resource hoặc shutdown của owner.

Quy trình kiểm soát là **quan sát đúng trạng thái → bảo toàn cause → xử lý cancellation hợp tác → chờ thân worker/an toàn tài nguyên → cleanup và shutdown pool có chủ sở hữu**.

Các tài liệu chính thức Java SE 17 còn hiệu lực:

- [Oracle `ForkJoinTask`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinTask.html): `fork`, `join`, `get`, trạng thái, `cancel`, `invokeAll`, `getException`, `completeExceptionally`.
- [Oracle `ForkJoinPool`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): work stealing, custom/common pool, lifecycle và awaitTermination.
- [Oracle `RecursiveTask`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RecursiveTask.html): `compute()` có kết quả.
- [Oracle `RecursiveAction`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RecursiveAction.html): tác vụ không kết quả.
- [Oracle `Future`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `get`, cancellation và timeout.
- [Oracle `ExecutionException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutionException.html): checked wrapper của failure tại `get`.
- [Oracle `CancellationException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CancellationException.html): truy xuất kết quả task bị hủy.
