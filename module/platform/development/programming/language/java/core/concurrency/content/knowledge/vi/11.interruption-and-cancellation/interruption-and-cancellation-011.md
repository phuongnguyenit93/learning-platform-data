# Phân tầng tín hiệu hủy trong chuỗi xử lý Java Concurrency

## 1. Bài toán và kết quả học tập

Một request không nhất thiết được xử lý bởi một thread duy nhất. Caller có thể gửi một `Callable` vào `ExecutorService`; parent task lại tạo các task con; child gọi `BlockingQueue`, chờ I/O, chạy CPU hoặc ghi kết quả vào hệ thống khác. Khi caller timeout hoặc người dùng hủy, câu hỏi không chỉ là **“đã gọi `cancel(true)` chưa?”**, mà là **“tín hiệu hủy có đi tới đúng từng tầng và tác vụ đã thực sự ngừng/cleanup/commit theo chính sách chưa?”**

~~~text
Caller / Service shutdown
          |
          v
Coordinator (Parent Future) ---> Child A (CPU / queue)
          |                   \
          |                    +-- checkpoint / interrupt
          v
     Child B (I/O) ----------> timeout / close / remote request
          |
          v
     Publish / commit -------> state generation, idempotency
          |
          v
        Cleanup -------------> locks, permits, connections
~~~

Có hai dòng thông tin cần phân biệt:
- **Từ trên xuống:** cancellation request, deadline, interrupt, cancellation token và chính sách ngừng từng child.
- **Từ dưới lên:** kết quả, exception, trạng thái worker thực sự rời task, cleanup đã xong và nghiệp vụ đã/không commit.

Sau bài, bạn sẽ biết:
1. Phân biệt **ý định hủy**, **interrupt status**, **Future cancelled**, **deadline**, **worker exited** và **business finality**.
2. Truyền cancellation từ parent xuống các task con **mà parent sở hữu**, thay vì tưởng hủy parent tự lan ra toàn cây.
3. Dùng đúng `InterruptedException`, `Thread.currentThread().isInterrupted()`, `Future.cancel(true)`, token và timeout.
4. Xác định ranh giới mà interruption không thể tự ngắt, như một số I/O, `synchronized` monitor acquisition hay side effect ở hệ thống khác.
5. Tránh lost cancellation, orphan tasks, resource leaks, result đến muộn và commit trùng khi retry.
6. Chạy ví dụ độc lập trên **Java 17+** với stdout và giải thích vì sao kết quả là như vậy.

**Phạm vi:** Java SE và concurrency của Java nói chung. Không đưa cơ chế riêng của Spring vào bài vì phần liên quan Spring có chương riêng.

## 2. Phân biệt các tầng của việc hủy

| Tầng hoặc trạng thái | Ý nghĩa | Điều không được suy ra |
| --- | --- | --- |
| Caller requested cancellation | Người dùng/caller muốn bỏ công việc | Task đã ngừng |
| Future.cancel(true) accepted | Future đã chấp nhận chuyển sang trạng thái hủy, và implementation có thể yêu cầu interrupt runner | Mọi child đã ngừng hoặc side effect đã rollback |
| Thread interrupt status | Một thread được báo có yêu cầu interrupt | CPU loop và mọi loại I/O sẽ tự thoát |
| Cancellation token | Ý định hủy được chia sẻ tới những stage kiểm tra token | Thread block sẽ tự thức dậy |
| Deadline expired | Thời gian ngân sách đã hết | Remote server chắc chắn dừng |
| Worker exited | Callable/Runnable đã hoàn tất thực thi | Tất cả remote side effect đã bị hủy |
| Resource cleanup finished | Lock/permit/stream/connection đã được giải phóng theo giao thức | Dữ liệu nghiệp vụ đã được rollback |
| Business commit finalized | Nơi ghi kết quả quyết định trạng thái cuối | Có thể suy từ một cờ local cancelled |

**`Future.isDone() == true` bao gồm cả completed, failed hoặc cancelled.** Một Future đã cancelled có thể báo isDone ngay cả khi callable còn thực hiện cleanup. `Future.get()` sau cancellation ném `CancellationException`, nhưng không phải chứng chỉ rằng mọi nhánh trong xử lý đã dừng.

Một yêu cầu có thể đang ở chuỗi trạng thái khác nhau:

~~~text
Future:   RUNNING -> CANCELLED -> isDone = true
Worker:   RUNNING -> nhận interrupt -> cleanup -> EXITED
Remote:   REQUEST_RECEIVED -> COMMITTED (dù caller đã cancel)
Resource: ACQUIRED -> CLEANUP_PENDING -> RELEASED
~~~

Do đó hãy đo/kiểm tra từng trạng thái ở đúng tầng, không gộp tất cả thành một boolean `cancelled`.

## 3. Tầng caller: nguồn tín hiệu hủy và thời hạn

Hủy có thể xuất phát từ:
- Người dùng nhấn hủy hoặc client disconnect.
- `Future.get(timeout, unit)` hết thời gian chờ.
- Một bước downstream vượt deadline.
- Một child gặp lỗi không thể phục hồi khiến các nhánh còn lại không cần.
- Service đang shutdown, cần dừng nhận request mới và giải phóng tài nguyên.
- Đã có một kết quả đủ tốt từ nhiều nhánh tìm kiếm, những nhánh còn lại không cần thiết.

Những nguyên nhân này có thể có **chính sách khác nhau**. Ví dụ một báo cáo tạm thời có thể bỏ phần tính toán còn lại, nhưng một thao tác đã gửi giao dịch ra hệ thống ngoài cần biết kết quả cuối hoặc bù trừ trước khi coi là hoàn tất.

### `Future.get(timeout)` chỉ giới hạn thời gian caller chờ

~~~java
try {
    return future.get(timeoutMillis, TimeUnit.MILLISECONDS);
} catch (TimeoutException e) {
    future.cancel(true); // Tín hiệu hủy riêng; get(timeout) không tự làm.
    throw e;
}
~~~

Đây là snippet trong method trả kiểu của Future, đã có `future`, `timeoutMillis` và import tương ứng. Nếu `get(timeout)` ném `TimeoutException`, task **có thể vẫn nằm trong queue hoặc đang chạy**, và `isCancelled()` không tự chuyển true. Gọi `cancel(true)` chỉ mới gửi yêu cầu hủy; phải xử lý tiếp theo contract.

### Deadline tổng khác timeout theo từng stage

Giả sử request có ngân sách 500 ms:

~~~text
Stage A mất 410 ms.
Stage B không được tự cấp lại 500 ms nếu deadline là toàn request.
Stage B chỉ còn khoảng 90 ms (trừ overhead/cleanup).
~~~

Nếu mỗi stage được phép dùng nguyên 500 ms, một chuỗi năm stage có thể khiến request chờ nhiều lần quá deadline. Mang **deadline chung** hoặc **ngân sách còn lại** qua các tầng.

Với duration trong một JVM, có thể dùng `System.nanoTime()` để tính elapsed/remaining; nó không phải timestamp UTC và không được chuyển nguyên giá trị sang JVM khác. Khi truyền deadline qua mạng cần giao thức thời gian giữa các máy và biên an toàn thích hợp.

## 4. Tầng Future và executor: ai thực sự bị hủy?

`Future<V>.cancel(boolean mayInterruptIfRunning)` có hai khía cạnh:
- **Hủy kết quả** đại diện bởi Future.
- Nếu `mayInterruptIfRunning=true` và implementation hỗ trợ, **cố interrupt thread** đang chạy task.

Bảng quan sát thông dụng:

| Tình huống | `cancel(true)` | `cancel(false)` |
| --- | --- | --- |
| Task chưa chạy | Hủy thành công ngăn task được chạy | Tương tự |
| Task đang chạy | Đánh dấu cancelled, implementation có thể interrupt runner | Không yêu cầu interrupt runner |
| Task đã hoàn thành | Không hủy kết quả đã hoàn tất | Tương tự |
| Future đã được đánh dấu cancelled | `get()` ném `CancellationException` | Tương tự |

`cancel(true)` không phải `Thread.stop()`. Interrupt là một yêu cầu **hợp tác**, không phải kill không điều kiện. `FutureTask` và các `Future` từ executor thông dụng hỗ trợ cancel bằng cách cố interrupt runner; nhưng `Future` là **interface**, nên phải xem implementation cụ thể.

Đặc biệt, theo Javadoc **Java 17**, `CompletableFuture.cancel(true)` **không dùng interrupt để điều khiển thực thi**, và tham số `mayInterruptIfRunning` không có tác dụng. Cancel `CompletableFuture` có thể khiến `join()/get()` quan sát cancellation, nhưng không chứng minh một `supplyAsync` đang chạy đã bị ngắt.

### Parent Future không tự quản lý toàn bộ child

Giả sử:

~~~java
Future<String> child = childPool.submit(childTask);
Future<String> parent = parentPool.submit(() -> child.get());
~~~

Đây là snippet với các executor và task đã được định nghĩa. Khi `parent.cancel(true)`:
- Thread đang đợi `child.get()` có thể bị interrupt, khiến `get()` ném `InterruptedException`.
- **Child Future không tự nhận `cancel(true)`** chỉ vì parent ngừng chờ.
- Nếu child vẫn block I/O hoặc chờ queue, nó có thể giữ resource và chạy sau khi request đã hủy.
- **Coordinator/owner** phải quyết định có hủy child, đợi cleanup, hoặc cố ý chuyển child thành job độc lập.

## 5. Tầng thread: interrupt và việc hợp tác

`Thread.interrupt()` đặt interrupt status và một số primitive blocking sẽ phản hồi:
- `Thread.sleep`, `Object.wait`, `CountDownLatch.await`, `BlockingQueue.take`, `Condition.await` và `Future.get` thường ném `InterruptedException` khi chờ bị ngắt.
- Thread đang chạy CPU thường **không tự ném exception**; phải kiểm tra cờ interrupt.
- Việc chờ lấy intrinsic monitor `synchronized` không tự thành thao tác interruptible như `ReentrantLock.lockInterruptibly()`.
- Blocking I/O có semantics khác nhau tùy API/driver/native implementation; không thể tuyên bố mọi `InputStream.read` dừng ngay.

Mẫu CPU loop hợp tác:

~~~java
while (!Thread.currentThread().isInterrupted()) {
    processSmallBatch();
}
cleanupAfterCancellation();
~~~

Đây là snippet với các method được khai báo. Chia công việc thành batch nhỏ để latency phản hồi cancel nằm trong giới hạn chấp nhận được. Một lệnh CPU chạy 10 phút không kiểm tra status có thể tiếp tục đủ 10 phút dù Future đã cancelled.

### Hai phương thức kiểm tra cờ khác nhau

- `Thread.currentThread().isInterrupted()`: kiểm tra nhưng **không xóa** cờ.
- `Thread.interrupted()`: static method đọc **và xóa** cờ của thread hiện tại.

Đừng gọi `Thread.interrupted()` rồi bỏ qua giá trị chỉ để “thăm dò”: bạn có thể xóa yêu cầu hủy trước khi tầng sau đọc được.

### Propagate, restore hay xử lý?

Khi một method có thể ném `InterruptedException`, thường nên truyền tiếp nếu nó không có lý do nghiệp vụ để nuốt:

~~~java
String takeItem(BlockingQueue<String> queue)
        throws InterruptedException {
    return queue.take();
}
~~~

Nếu không thể truyền tiếp và phải thoát:

~~~java
try {
    performInterruptibleOperation();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
~~~

Snippet thứ hai nằm trong method `void`. Khôi phục cờ có ích để tầng bao ngoài tiếp tục thấy yêu cầu; nhưng **cũng phải dừng/đổi trạng thái**, không khôi phục cờ rồi tiếp tục xử lý như chưa có gì.

## 6. Ví dụ Java 17: Future cancelled và worker exited là hai việc

Tạo file **`InterruptBoundaryDemo.java`**:

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class InterruptBoundaryDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch exited = new CountDownLatch(1);

        try {
            Future<String> future = pool.submit(() -> {
                started.countDown();
                try {
                    Thread.sleep(60_000);
                    return "completed";
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return "stopped";
                } finally {
                    exited.countDown();
                }
            });

            started.await();
            boolean accepted = future.cancel(true);
            exited.await();

            System.out.println("cancelAccepted=" + accepted);
            System.out.println("futureCancelled=" + future.isCancelled());
            System.out.println("workerExited=" + (exited.getCount() == 0));

            try {
                future.get();
            } catch (CancellationException e) {
                System.out.println("get=CancellationException");
            }
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Chạy:

~~~bash
javac InterruptBoundaryDemo.java
java InterruptBoundaryDemo
~~~

Stdout trên đường thực thi không có interruption bên ngoài:

~~~text
cancelAccepted=true
futureCancelled=true
workerExited=true
get=CancellationException
~~~

Lập luận:
1. `started` xác nhận Callable đã bắt đầu. `Thread.sleep(60_000)` giữ nó chưa hoàn thành trước khi main hủy.
2. `cancel(true)` yêu cầu interrupt runner. Dù interrupt tới trước hay trong sleep, `sleep` sẽ phản hồi và thoát.
3. Worker đi tới `finally`, hạ latch `exited`. Main **đợi exited**, không dùng `future.isDone()` để suy worker đã dừng.
4. Dù Callable return `"stopped"` trong catch, Future đã cancelled nên `get()` ném `CancellationException`.

Lỗi thực tế là chỉ kiểm tra `future.isDone()` sau cancel rồi coi đã hoàn tất cleanup. Một Future bị hủy có thể done trước khi Callable rời stack, trả connection hoặc unlock. Khi yêu cầu xác nhận thực thi đã dừng, dùng lifecycle signal hoặc theo dõi termination của worker/executor với deadline.

## 7. Ví dụ Java 17: hủy parent không tự hủy child

Tạo file **`DetachedChildDemo.java`**:

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class DetachedChildDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService parents = Executors.newSingleThreadExecutor();
        ExecutorService children = Executors.newSingleThreadExecutor();

        CountDownLatch childStarted = new CountDownLatch(1);
        CountDownLatch releaseChild = new CountDownLatch(1);
        CountDownLatch childExited = new CountDownLatch(1);
        CountDownLatch parentWaiting = new CountDownLatch(1);
        CountDownLatch parentExited = new CountDownLatch(1);

        try {
            Future<Integer> child = children.submit(() -> {
                childStarted.countDown();
                try {
                    releaseChild.await();
                    return 7;
                } finally {
                    childExited.countDown();
                }
            });

            childStarted.await();

            Future<Integer> parent = parents.submit(() -> {
                parentWaiting.countDown();
                try {
                    return child.get() + 1;
                } finally {
                    parentExited.countDown();
                }
            });

            parentWaiting.await();
            boolean accepted = parent.cancel(true);
            parentExited.await();

            System.out.println("parentCancelAccepted=" + accepted);
            System.out.println("parentCancelled=" + parent.isCancelled());
            System.out.println("childCancelled=" + child.isCancelled());
            System.out.println("childExitedBeforeOwnCancel="
                    + (childExited.getCount() == 0));

            child.cancel(true);
            childExited.await();

            System.out.println("childCancelledNow=" + child.isCancelled());
            System.out.println("childExitedNow="
                    + (childExited.getCount() == 0));

            try {
                parent.get();
            } catch (CancellationException e) {
                System.out.println("parentGet=CancellationException");
            }
        } finally {
            releaseChild.countDown();
            parents.shutdownNow();
            children.shutdownNow();
            parents.awaitTermination(1, TimeUnit.MINUTES);
            children.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac DetachedChildDemo.java
java DetachedChildDemo
~~~

Stdout khi thực thi bình thường:

~~~text
parentCancelAccepted=true
parentCancelled=true
childCancelled=false
childExitedBeforeOwnCancel=false
childCancelledNow=true
childExitedNow=true
parentGet=CancellationException
~~~

**Vì sao?** Parent đang chờ `child.get()`, child bị giữ ở `releaseChild.await()`. Hủy parent có thể làm thread parent rời `get` qua `InterruptedException`, nhưng không tự cancel child. Child chỉ nhận yêu cầu dừng ở lời gọi `child.cancel(true)` riêng, rồi thoát và hạ latch.

Ví dụ cho thấy **cancellation của kết quả parent không có propagation tự động qua mọi Future trong chương trình**. Nếu child thuộc một request mà parent đang điều phối, việc bỏ quên child sau hủy là **orphan work**, có thể tiếp tục giữ thread, I/O hoặc sinh side effect. Ngược lại, nếu child thực sự là công việc nền độc lập/durable, nó có thể được cố ý tách khỏi parent: cần mô tả ownership và lifecycle rõ ràng.

## 8. Ví dụ Java 17: coordinator lan truyền hủy xuống child

Coordinator muốn **hủy các child do chính nó sở hữu** khi không còn tiếp tục được. Ví dụ tiếp theo tạo child rồi parent đợi kết quả. Nếu parent bị interrupt trong `child.get()`, nó chủ động gọi `child.cancel(true)`.

Tạo file **`CascadedCancelDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class CascadedCancelDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService parents = Executors.newSingleThreadExecutor();
        ExecutorService children = Executors.newSingleThreadExecutor();

        CountDownLatch childStarted = new CountDownLatch(1);
        CountDownLatch releaseChild = new CountDownLatch(1);
        CountDownLatch childExited = new CountDownLatch(1);
        CountDownLatch parentReady = new CountDownLatch(1);
        CountDownLatch parentExited = new CountDownLatch(1);

        AtomicReference<Future<String>> childHandle =
                new AtomicReference<>();

        try {
            Future<String> parent = parents.submit(() -> {
                Future<String> child = children.submit(() -> {
                    childStarted.countDown();
                    try {
                        releaseChild.await();
                        return "child-result";
                    } finally {
                        childExited.countDown();
                    }
                });

                childHandle.set(child);
                try {
                    childStarted.await();
                    parentReady.countDown();
                    return child.get();
                } catch (InterruptedException e) {
                    child.cancel(true);
                    Thread.currentThread().interrupt();
                    throw e;
                } finally {
                    parentExited.countDown();
                }
            });

            parentReady.await();
            boolean accepted = parent.cancel(true);

            parentExited.await();
            childExited.await();

            System.out.println("parentCancelAccepted=" + accepted);
            System.out.println("parentCancelled=" + parent.isCancelled());
            System.out.println("childCancelled="
                    + childHandle.get().isCancelled());
            System.out.println("childExited="
                    + (childExited.getCount() == 0));
        } finally {
            releaseChild.countDown();
            parents.shutdownNow();
            children.shutdownNow();
            parents.awaitTermination(1, TimeUnit.MINUTES);
            children.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Chạy:

~~~bash
javac CascadedCancelDemo.java
java CascadedCancelDemo
~~~

Stdout trên đường thực thi bình thường:

~~~text
parentCancelAccepted=true
parentCancelled=true
childCancelled=true
childExited=true
~~~

**Phân tích:** Parent tự giữ quyền sở hữu child Future. Khi `Future.get()` bị interrupt, catch của parent không nuốt exception: nó **hủy child**, restore interrupt status, rồi truyền tiếp. Child đang ở một thao tác chờ interruptible nên thoát và giảm `childExited`; main có tín hiệu riêng để quan sát thực thi đã kết thúc.

**Giới hạn:** Nếu parent có **nhiều** child Futures, phải quản lý tất cả. Nếu child không interruptible, `cancel(true)` không đủ để xác nhận dừng. Ví dụ minh họa đường **interrupted while awaiting**; trong ứng dụng thật cần thêm cleanup khi parent exception ở chỗ khác, cancellation trước khi child được submit, partial child creation và shutdown races.

### Mẫu quản lý nhiều child

~~~java
List<Future<?>> ownedChildren = new ArrayList<>();
try {
    ownedChildren.add(childPool.submit(stageA));
    ownedChildren.add(childPool.submit(stageB));
    // Chờ và tổng hợp.
} finally {
    if (requestNoLongerNeedsChildren) {
        for (Future<?> child : ownedChildren) {
            child.cancel(true);
        }
    }
}
~~~

Đây là **pseudocode Java** trong method đã có `childPool`, `stageA`, `stageB`, `requestNoLongerNeedsChildren`; không phải class độc lập. Không dùng `finally` để cancel **mọi** child khi nghiệp vụ yêu cầu một job đã tách ownership tiếp tục chạy. Mục tiêu là làm rõ quan hệ sở hữu: ai submit, ai chờ, ai cancel, ai cleanup và ai trả kết quả.

## 9. Cancellation token: truyền ý định hủy qua cây tác vụ

Không phải helper nào cũng có Future. Một **cancellation token** là một object thể hiện ý định dừng để các stage kiểm tra tại checkpoint.

Nhu cầu phổ biến:
- Request chạy qua nhiều method/helper.
- Một parent điều phối nhiều child task trên các executor khác nhau.
- CPU loop cần kiểm tra ý định hủy giữa các bước.
- Một child có thể bị hủy riêng mà **không** hủy các sibling hoặc parent.
- Parent hủy cần khiến mọi child còn phụ thuộc cùng request quan sát trạng thái cancelled.

### Ví dụ Java 17: token cha–con

Tạo file **`HierarchicalTokenDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class HierarchicalTokenDemo {
    static final class CancelToken {
        private final CancelToken parent;
        private final AtomicBoolean localCancelled = new AtomicBoolean();

        CancelToken(CancelToken parent) {
            this.parent = parent;
        }

        void cancel() {
            localCancelled.set(true);
        }

        boolean isCancelled() {
            return localCancelled.get()
                    || (parent != null && parent.isCancelled());
        }
    }

    public static void main(String[] args) throws Exception {
        CancelToken root = new CancelToken(null);
        CancelToken child = new CancelToken(root);
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);

        try {
            Future<String> task = pool.submit(() -> {
                started.countDown();
                while (!child.isCancelled()) {
                    Thread.sleep(10); // Chỉ giảm CPU trong demo.
                }
                return "stopped-by-token";
            });

            started.await();
            root.cancel();

            System.out.println("rootCancelled=" + root.isCancelled());
            System.out.println("childCancelled=" + child.isCancelled());
            System.out.println("result=" + task.get());
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Chạy:

~~~bash
javac HierarchicalTokenDemo.java
java HierarchicalTokenDemo
~~~

Stdout khi không có interruption ngoài ý muốn:

~~~text
rootCancelled=true
childCancelled=true
result=stopped-by-token
~~~

`AtomicBoolean` cung cấp visibility cho trạng thái token. Child đọc `isCancelled()` của nó và ancestor, nên parent hủy được quan sát ở child. Token giúp truyền **ý định hủy** từ scope cha; nó không tự gọi `Thread.interrupt()` hoặc đóng connection.

Trong demo, `Thread.sleep(10)` chỉ giúp tránh vòng CPU nóng; nó không phải phương tiện bảo đảm phản hồi tức thì. Nếu task bị kẹt ở một I/O không có timeout, nó không thể check token cho đến khi I/O trả về. Thiết kế thực thường phối hợp **token + interrupt/timed API/close**.

### Cancellation độc lập theo scope

Một token con được phép tự cancel mà không bắt buộc cha canceled; sibling khác có thể tiếp tục. Tuy nhiên nếu **mọi child** đều phụ thuộc kết quả chung all-or-nothing, coordinator có thể quyết định cancel root khi một child thất bại. Chính sách đó phải được viết ở **tầng orchestration**, không ngầm đoán từ token.

### Token và memory semantics

Một shared `boolean cancelled` thường không đủ nếu được truy cập đa luồng mà thiếu synchronized/volatile/atomic. Dùng `AtomicBoolean`, `volatile` hoặc giao thức memory visibility tương đương. Nếu token còn chứa reason/deadline, hãy công bố các field nhất quán (immutable cancellation state/atomic reference nếu cần). Không xây một tập cờ mutable rồi để reader thấy reason của lần hủy này và status của lần khác.

## 10. Deadline và ngân sách còn lại

Một request deadline có thể dùng một mốc nano-time nội bộ và truyền object Deadline qua các stage. Tất cả stage dùng **remaining time**, không tạo một timeout mới đầy đủ mỗi lần.

Tạo file **`DeadlineBudgetDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class DeadlineBudgetDemo {
    static final class Deadline {
        private final long deadlineNanos;

        Deadline(long timeout, TimeUnit unit) {
            deadlineNanos = System.nanoTime() + unit.toNanos(timeout);
        }

        long remainingNanos() {
            return Math.max(0L, deadlineNanos - System.nanoTime());
        }
    }

    static void awaitWithinBudget(
            CountDownLatch event, Deadline deadline)
            throws InterruptedException, TimeoutException {

        long remaining = deadline.remainingNanos();
        if (remaining == 0L
                || !event.await(remaining, TimeUnit.NANOSECONDS)) {
            throw new TimeoutException("overall deadline reached");
        }
    }

    public static void main(String[] args) throws Exception {
        Deadline deadline = new Deadline(20, TimeUnit.MILLISECONDS);
        CountDownLatch neverCompleted = new CountDownLatch(1);

        try {
            awaitWithinBudget(neverCompleted, deadline);
            System.out.println("eventArrived");
        } catch (TimeoutException e) {
            System.out.println("budgetTimedOut=true");
        }
    }
}
~~~

Chạy:

~~~bash
javac DeadlineBudgetDemo.java
java DeadlineBudgetDemo
~~~

Stdout nếu thread không bị interrupt:

~~~text
budgetTimedOut=true
~~~

Vì latch **không bao giờ count down**, nó không thể hoàn tất bình thường. Nếu deadline đã hết trước khi stage được chạy, method lập tức báo timeout; nếu chưa, nó chờ **chỉ phần còn lại** rồi báo timeout. Không in elapsed milliseconds do thời gian scheduling không cố định.

**Giới hạn rõ ràng:** ví dụ dùng deadline ngắn; code production cần validate timeout âm/cực lớn, tránh overflow khi cộng nano duration. `System.nanoTime()` phù hợp cho elapsed time **trong một JVM**, không là timestamp có thể gửi trực tiếp qua nhiều máy.

**Deadline object không tự thức tỉnh thread**: nó chỉ cho phép tính ngân sách. Khi stage block ở socket, lock, queue, remote call, phải truyền remaining budget vào API có timeout phù hợp hoặc dùng kênh hủy/close riêng. Đặt `Future.get(timeout)` ở tầng caller mà không đặt timeout cho I/O bên trong không giới hạn worker stop latency.

## 11. Blocking operations: mỗi tầng có cơ chế ngắt khác nhau

| Loại công việc | Phản hồi với interrupt | Cần thiết kế thêm |
| --- | --- | --- |
| `Thread.sleep` | Thường ném `InterruptedException` | Exit/restore/cleanup |
| `BlockingQueue.take` | Chờ interruptible | `poll(timeout)` nếu có deadline |
| `CountDownLatch.await` | Chờ interruptible | Bảo đảm latch release/shutdown |
| `Future.get` | Thread chờ có thể nhận `InterruptedException` | Cancel child Future riêng |
| `Condition.await` | Chờ interruptible, lấy lại lock trước khi thoát | while predicate, finally unlock |
| `ReentrantLock.lockInterruptibly` | Chờ lấy lock có thể bị interrupt | Chọn timeout khi cần |
| Tranh intrinsic monitor `synchronized` | Không tự ném `InterruptedException` khi đợi lock | Critical section ngắn, kiểm tra cờ sau khi vào |
| CPU loop | Không dừng nếu không có checkpoint | `isInterrupted()`/token giữa các batch |
| Blocking I/O | Khác nhau giữa stream, socket, channel, driver | Deadline đúng API, close theo contract |
| Remote commit | Local interrupt không đồng nghĩa remote rollback | Idempotency, trạng thái giao dịch |

**I/O không thể suy đoán:** Với một số `InterruptibleChannel`, interruption lúc blocking có thể làm channel đóng và ném `ClosedByInterruptException`; với nhiều stream/socket/driver khác, semantics phụ thuộc triển khai, timeout hoặc đóng tài nguyên. Đừng hứa mọi `InputStream.read()` trả về tức thì khi `Future.cancel(true)`.

### Timeout không hủy tác dụng phụ của remote service

Caller có thể mất kết nối hoặc timeout **sau khi server đã nhận và commit** request. Nếu retry mà không có idempotency key, có nguy cơ tạo hai bản ghi/thanh toán. Do đó propagation deadline không thay thế giao thức chống duplicate và reconciliation ở nơi thực sự tạo side effect.

## 12. Cleanup: hủy không được làm rò resource

Một task có thể nắm giữ `Semaphore` permit, lock, file, stream hoặc connection khi nhận interrupt. `Future.cancel(true)` không tự thay task chạy code cleanup; phải dùng `finally`/try-with-resources và đảm bảo state không bị bỏ ở trạng thái nửa cập nhật.

### Ví dụ Java 17: trả permit sau cancellation

Tạo file **`ResourceReleaseDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public class ResourceReleaseDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        Semaphore permits = new Semaphore(1);
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch neverReleased = new CountDownLatch(1);
        CountDownLatch exited = new CountDownLatch(1);

        try {
            Future<?> task = pool.submit(() -> {
                boolean acquired = false;
                try {
                    permits.acquire();
                    acquired = true;
                    started.countDown();
                    neverReleased.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                } finally {
                    if (acquired) {
                        permits.release();
                    }
                    exited.countDown();
                }
            });

            started.await();
            boolean accepted = task.cancel(true);
            exited.await();

            System.out.println("cancelAccepted=" + accepted);
            System.out.println("futureCancelled=" + task.isCancelled());
            System.out.println("availablePermits="
                    + permits.availablePermits());
            System.out.println("workerExited="
                    + (exited.getCount() == 0));
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Chạy:

~~~bash
javac ResourceReleaseDemo.java
java ResourceReleaseDemo
~~~

Stdout bình thường:

~~~text
cancelAccepted=true
futureCancelled=true
availablePermits=1
workerExited=true
~~~

`started` được hạ **sau khi acquire permit**, nên main chỉ hủy task khi nó đã vào vùng sở hữu permit. Interrupt làm `neverReleased.await()` kết thúc bằng `InterruptedException`; `finally` release permit và hạ `exited`. Main đợi `exited` trước khi kiểm tra số permit. Do đó kết quả in chứng minh tài nguyên local trong demo đã trả, không chỉ Future đã bị hủy.

**Production:** cleanup có thể ném exception, chậm hoặc block, vì thế việc đợi worker exited cũng cần deadline và cảnh báo. Nếu một permit được release hai lần do hai nhánh hủy cùng chạy cleanup, invariant tài nguyên cũng bị sai; đặt cleanup tại một owner và viết logic idempotent khi có nhiều đường kết thúc.

## 13. Ranh giới commit: tại sao kiểm tra interrupt chưa đủ?

Một task đã bắt đầu gọi external API, ghi database hoặc publish vào shared state có thể tiếp tục gây side effect sau khi caller hủy. Xét snippet:

~~~java
if (!Thread.currentThread().isInterrupted()) {
    commitToExternalSystem(result);
}
~~~

Đây là đoạn minh họa với `result` và `commitToExternalSystem` do ứng dụng định nghĩa. Có race:

~~~text
Worker                           Caller
------                           ------
check isInterrupted() -> false
                                 cancel(true)
commitToExternalSystem(result)
                                 Caller nghĩ tác vụ đã bỏ
~~~

Check và commit không phải một transaction. Ngay cả nếu worker được interrupt trước khi gửi, một remote request trước đó có thể đã commit tại server.

Các hướng xử lý khi kết quả muộn không được phép ghi:
- **Generation/version:** mỗi request/retry có version; kết quả cũ không thể ghi đè state của generation mới nếu publish kiểm tra version nguyên tử.
- **Commit ownership:** một component duy nhất được quyền chấp nhận kết quả và quyết định liệu cancellation đã thắng chưa.
- **Atomic state transition:** chuyển `RUNNING -> COMMITTING` dưới lock/CAS theo invariant cần giữ; định nghĩa nếu cancellation và commit cạnh tranh thì bên nào được chấp nhận.
- **Idempotency key:** hệ thống đích nhận diện các lần retry của cùng một business operation.
- **Transaction hoặc compensation:** nếu commit một phần không thể rollback nguyên tử, có cơ chế bù trừ và durable status.
- **Reconciliation:** khi caller timeout nhưng không biết remote đã làm gì, tra cứu trạng thái bằng request ID thay vì đoán “thất bại”.

**Cancellation token và interrupt flag không tự đảm bảo atomicity với commit ngoài JVM.** Nếu cần tính đúng mạnh, phải có giao thức ở chính nơi có side effect.

## 14. CompletableFuture và đồ thị phụ thuộc

Java 17 `CompletableFuture` tạo pipeline bằng `thenApply`, `thenCompose`, `allOf`, `anyOf`. Nhưng **cancel một CompletableFuture** không đồng nghĩa cancel mọi công việc nằm dưới stage:
- `cancel(true)` trên `CompletableFuture` không dùng interrupt để điều khiển worker trong Java 17.
- Một `supplyAsync` đang chạy có thể tiếp tục tạo side effect.
- Các dependent stages có thể nhận completion exceptional/cancellation theo hợp đồng CompletableFuture, nhưng không tự quản lý FutureTask/HTTP request mà callback đã tạo.
- Nếu cần hủy thực thi, phải chuyển token/deadline xuống callback hoặc giữ riêng task/I/O handles có chính sách cancel thích hợp.

### Snippet ứng dụng token trong pipeline

~~~java
CancelToken requestToken = new CancelToken(null);

CompletableFuture<String> result = CompletableFuture.supplyAsync(() -> {
    if (requestToken.isCancelled()) {
        return "cancelled-before-work";
    }

    String answer = computeWithCheckpoints(requestToken);

    if (requestToken.isCancelled()) {
        return "discarded";
    }
    return answer;
}, executor);

// Ở phía caller:
requestToken.cancel();
result.cancel(true);
~~~

Đây là **snippet**, dùng class `CancelToken` trong ví dụ trước cùng method `computeWithCheckpoints` và executor do ứng dụng định nghĩa. `result.cancel(true)` chỉ là cancellation ở tầng CompletableFuture; `requestToken.cancel()` làm ý định hủy có thể được callback tự quan sát. Bước publish cuối vẫn cần kiểm soát generation/commit, bởi cancellation có thể đến sau lần check cuối.

Không mặc định các API structured concurrency được giới thiệu trong phiên bản Java mới hơn có sẵn trên Java 17. Với API chuẩn Java 17, **ownership của Futures/child tasks** phải được quản lý tường minh.

## 15. Chính sách lỗi/hủy của coordinator

Khi một child thất bại, có phải hủy tất cả child còn lại? Không có một quy tắc cho mọi nghiệp vụ:

| Chính sách | Khi nào áp dụng | Tác vụ khác |
| --- | --- | --- |
| All-or-nothing | Mọi child cần thành công mới có kết quả hợp lệ | Hủy phần còn lại khi lỗi bắt buộc |
| Best-effort | Có thể trả kết quả không đầy đủ trong deadline | Tiếp tục child còn có giá trị |
| First-success | Một trong nhiều child cho kết quả hợp lệ là đủ | Hủy child thừa nếu an toàn |
| Durable background | Job phải tiếp tục dù caller disconnect | Tách quyền sở hữu và giám sát |
| Shared computation | Nhiều caller cần cùng một child | Một caller hủy không được hủy shared work của người khác bừa bãi |

Tầng coordinator cần giữ **danh sách những child do nó thực sự sở hữu**. Nếu một child được nhiều callers dùng chung, có thể cần lease/ref count hoặc một owner độc lập. Không được tùy tiện hủy task chung chỉ vì một caller mất hứng nhận kết quả.

### Đừng biến interruption thành “success mặc định”

Sai:

~~~java
try {
    return child.get();
} catch (InterruptedException ignored) {
    return defaultResult;
}
~~~

Đây là snippet bên trong method trả kiểu phù hợp. Nó có thể che yêu cầu hủy, khiến caller tưởng pipeline thành công và commit một giá trị sai. Hướng xử lý tốt hơn là xác định child ownership, cancel child nếu không còn cần, propagate `InterruptedException` hoặc restore status rồi trả trạng thái canceled rõ ràng.

### Khi worker đã cancelled nhưng vẫn chạy

Nếu một task bỏ qua interrupt hoặc đang ở I/O chưa kết thúc, nó có thể trở thành **orphan work**. Dù Future isCancelled true, không có bằng chứng resource đã được giải phóng. Cần log/metric phân biệt:
- Cancellation requested.
- Cancellation accepted by Future.
- Child cancellation dispatched.
- Worker actually exited.
- Cleanup completed.
- Business commit accepted/rejected.

## 16. Executor shutdown là tầng hệ thống khác với request cancellation

**`ExecutorService.shutdown()`**: từ chối task mới, cho phép task đã submit chạy theo hợp đồng.

**`shutdownNow()`**: cố dừng task đang chạy bằng interrupt và trả task chưa được bắt đầu, nhưng đây là hành động **best-effort**.

**`awaitTermination(timeout, unit)`**: chờ executor terminated sau shutdown, không tự khởi động shutdown.

Snippet:

~~~java
pool.shutdown();
try {
    if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
        pool.shutdownNow();
        if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
            // Ghi nhận task không hợp tác hoặc cleanup quá hạn.
        }
    }
} catch (InterruptedException e) {
    pool.shutdownNow();
    Thread.currentThread().interrupt();
}
~~~

Đây là snippet với `pool` là `ExecutorService` và `TimeUnit` đã import. Một yêu cầu bị cancel **không có quyền shutdown executor dùng chung** của cả ứng dụng; hãy cancel Futures/tokens thuộc request. Shutdown application mới có trách nhiệm phối hợp tất cả request scopes, drain/cancel, đợi cleanup và theo dõi noncooperative worker.

## 17. Checklist thiết kế phân tầng tín hiệu hủy

1. **Nguồn hủy là gì?** Người dùng, deadline, upstream error hay shutdown? Chính sách mỗi loại có khác nhau?
2. **Ai sở hữu các child?** Có danh sách Future/handle đầy đủ khi parent tạo nhiều nhánh không?
3. **Hủy có cần lan xuống không?** All-or-nothing hay job được phép tiếp tục độc lập?
4. **Mỗi stage nhận gì?** Interrupt, token, deadline, close, timeout API hoặc kết hợp?
5. **CPU stage có checkpoint không?** Một vòng tính toán quá dài có kéo cancel latency lên không?
6. **Blocking I/O có timeout/hủy thực sự không?** Không nhầm Future.get(timeout) với socket/DB timeout.
7. **Tầng trung gian có nuốt InterruptedException không?** Nếu không thể propagate, có restore flag và thoát không?
8. **Mỗi child có cleanup không?** Lock, permit, connection, stream trả trong finally/try-with-resources?
9. **Có trường hợp cleanup fail/treo không?** Có deadline giám sát, không đợi vô hạn khi shutdown?
10. **Có thể cancel khi đang commit không?** Cần quyền commit/state machine và idempotency.
11. **Kết quả muộn có thể ghi đè generation mới không?** Có CAS/version check ở nơi publish?
12. **Có child chia sẻ giữa nhiều callers không?** Một caller không tự hủy global work.
13. **Có cấu trúc token có memory visibility đúng không?** Dùng atomic/volatile hoặc immutable state.
14. **Có truyền ngân sách thời gian còn lại không?** Không khởi động lại toàn timeout mỗi stage.
15. **Metrics có phân biệt accept cancel và worker exit không?** Không báo “cancel hoàn tất” chỉ từ Future.isDone().
16. **Test có điều phối chính xác không?** Dùng latch/barrier thay vì sleep để ép điểm thực thi.
17. **Shutdown song song cancel có idempotent không?** Tránh double-release hoặc double-compensate.
18. **Đã đo liveness và throughput sau khi thêm cancellation chưa?** Một đường hủy không được gây deadlock mới.

## 18. Bài tập và câu hỏi tự kiểm tra

1. `parent.cancel(true)` có tự gọi `child.cancel(true)` không? **Không**, trừ khi abstraction/coordinator thiết kế lan truyền.
2. `Future.isDone()==true` sau cancel có chứng minh Callable đã thoát không? **Không**, cần lifecycle observation riêng.
3. `Future.get(timeout)` ném `TimeoutException` có hủy task không? **Không**.
4. `Thread.currentThread().isInterrupted()` khác `Thread.interrupted()` thế nào? **Hàm sau là static và xóa flag của thread hiện tại**.
5. Nếu CPU loop không check interrupt hay token, cancel có buộc nó dừng không? **Không**.
6. Token cha bị cancel thì token con như ví dụ có biết không? **Có**, vì đọc trạng thái ancestor.
7. Token đổi true có tự ngắt một lần `BlockingQueue.take()` đang block không? **Không**, cần interrupt/timed/wakeup protocol.
8. Tại sao parent đang đợi `child.get()` bị interrupt mà child vẫn chạy? **InterruptedException của parent không hủy child Future**.
9. Ai có trách nhiệm cancel child khi không cần nữa? **Owner/coordinator quản lý child**, trừ khi child đã tách ownership rõ ràng.
10. Có nên hủy task chia sẻ nếu một caller bỏ kết quả không? **Không mặc định**, phải xem ownership và yêu cầu của callers khác.
11. Trong Java 17, `CompletableFuture.cancel(true)` có luôn interrupt thread `supplyAsync` không? **Không; mayInterruptIfRunning không có tác dụng**.
12. `shutdownNow()` có buộc mọi task dừng tức thì không? **Không, chỉ best-effort**.
13. Tại sao cần deadline tổng xuyên nhiều stage? **Để không tái cấp nguyên timeout và vượt thời gian yêu cầu**.
14. `System.nanoTime()` có phải timestamp UTC có thể gửi sang server khác không? **Không**, là cơ sở đo duration tương đối trong process.
15. `Future.get(timeout)` có đủ để ngắt mọi socket read không? **Không**, phải dùng API I/O có timeout/close/cancel tương ứng.
16. Check interrupt ngay trước commit đã ngăn mọi commit sau cancel chưa? **Chưa**, còn race giữa check và commit.
17. Nếu server đã commit nhưng caller timeout, nên làm gì để tránh duplicate? **Idempotency key và tra cứu/reconcile trạng thái**.
18. Cancellation token có thay được cơ chế memory visibility không? **Không**, token phải dùng atomic/volatile/lock đúng cách.
19. Vì sao cleanup phải diễn ra trong `finally`? **Để exception/interruption vẫn dẫn tới giải phóng tài nguyên tại owner**.
20. Trong `DetachedChildDemo`, hủy parent có khiến child isCancelled true không? **Không**, chỉ lần hủy child riêng.
21. Trong `CascadedCancelDemo`, vì sao child isCancelled true? **Parent catch InterruptedException và chủ động gọi `child.cancel(true)`**.
22. Trong `ResourceReleaseDemo`, vì sao permit trở lại 1? **Worker chạy finally và release permit sau interruption, main đợi exited**.
23. Nếu cancellation và shutdown cùng đến, có thể release resource hai lần không? **Có nếu giao thức cleanup sai**, phải có owner/transition idempotent.
24. Có thể coi số lần `cancel(true)==true` là số lần business operation bị rollback không? **Không**, đây là hai metric khác.
25. Một child có thể cố ý chạy tiếp sau request cancel không? **Có**, nếu nó là job nền durable, nhưng phải tách ownership, quản lý tài nguyên và finality rõ ràng.

## 19. Kết luận

**Phân tầng tín hiệu hủy** là thiết kế đường truyền yêu cầu ngừng từ caller xuống coordinator, children, thread, API blocking và nơi commit; đồng thời xác định kết quả và trạng thái cleanup đi ngược lên. `Future.cancel(true)`, interrupt status, cancellation token và deadline **là những cơ chế bổ sung, không thay thế lẫn nhau**.

Một protocol đúng phải xác định:
- **Phạm vi sở hữu:** child nào thuộc parent và có cần hủy theo parent không.
- **Điểm kiểm tra:** stage nào hợp tác với interrupt/token, I/O nào có timeout/close.
- **Tài nguyên:** ai nhả lock, permit, connection và xác nhận worker exited.
- **Nghiệp vụ:** cancellation có thể ngăn commit nào, xử lý side effect đã hoàn tất và kết quả đến muộn ra sao.
- **Quan sát:** không nhầm Future cancelled với worker stopped và business finalized.

Hãy đo thành công của hủy bằng **tác vụ thật sự dừng, resource thật sự được trả và kết quả nghiệp vụ được xử lý đúng**, chứ không chỉ bằng giá trị trả về của `cancel(true)`.

## Tài liệu tham khảo Java SE 17

- [Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `cancel`, `isCancelled`, `get(timeout)`.
- [ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): `submit`, `shutdown`, `shutdownNow`, `awaitTermination`.
- [Thread](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): `interrupt`, `interrupted`, `isInterrupted`.
- [CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): điều phối giữa các stage.
- [CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): cancellation semantics.
- [BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): `take` và `poll(timeout)`.
- [ReentrantLock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): `lockInterruptibly` và `tryLock`.
- [InterruptibleChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/InterruptibleChannel.html): interruption với blocking channel.
- [Java Language Specification `17](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): happens-before và Java Memory Model.
