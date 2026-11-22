# Future.cancel(true) và cơ chế ngắt có tính hợp tác

**Hủy một Future không đồng nghĩa với cưỡng bức dừng một luồng Java.** Đây là nguyên tắc quan trọng nhất khi xử lý tác vụ hết hạn, người dùng hủy yêu cầu hoặc ứng dụng đóng bộ thực thi trong **Spring Framework - concurrency**.

Với Future được tạo bởi **ExecutorService.submit** và thường được triển khai bằng **FutureTask**, lời gọi **cancel(true)** cố chuyển Future sang trạng thái hủy; nếu công việc đã bắt đầu và implementation biết thread thực thi, nó có thể gửi yêu cầu **Thread.interrupt()** đến thread đó. Việc công việc có thực sự dừng nhanh và giải phóng tài nguyên hay không **phụ thuộc vào code của chính công việc và những API nó đang chờ**.

Tương phản rất quan trọng: **CompletableFuture.cancel(true)** của Java chuẩn coi hủy như một dạng **exceptional completion**; tham số true **không có tác dụng ngắt computation** trong implementation này. Vì thế không thể nhìn thấy tên phương thức cancel giống nhau rồi kết luận hai implementation có cùng hành vi đối với worker.

Bài học thuộc nhóm **Hết hạn và hủy**. Sau bài này, bạn cần có thể phân biệt trạng thái Future với sự sống còn của task, viết vòng lặp có kiểm tra ngắt, xử lý InterruptedException đúng, thiết kế deadline/cancellation trong Spring @Async và kiểm thử bằng đồng bộ xác định thay vì dựa vào Thread.sleep đoán thời điểm.

## 1. Ba khái niệm khác nhau: Future, tác vụ và luồng

Khi một request gửi tác vụ vào ThreadPoolTaskExecutor hoặc ExecutorService, có ít nhất ba thực thể:

1. **Future**: đối tượng đại diện cho kết quả hoặc trạng thái hủy/hoàn tất theo hợp đồng API.
2. **Task**: logic thực sự chạy; có thể đang nằm trong queue, đang thực thi, bị chặn I/O hoặc sắp kết thúc.
3. **Worker thread**: tài nguyên thực thi task; trong thread pool, worker thường được **tái sử dụng** cho những task tiếp theo.

~~~text
HTTP caller                         ExecutorService / ThreadPool
     |                                        |
     +-- submit(callable) ------------------->| queue/task
     |                                        |     |
     |<------------------------ Future<T> ----+     v
     |                                          worker chạy task
     |
     +-- future.cancel(true)
     |          |
     |          +-- đề nghị hủy Future
     |          +-- có thể interrupt worker nếu implementation hỗ trợ
     |
     +-- future.isCancelled() == true
                        |
                        +-- KHÔNG chứng minh worker đã ngừng mọi side effect
~~~

**isDone() == true** chỉ cho biết Future đã ở trạng thái hoàn tất theo hợp đồng, bao gồm **thành công, lỗi hoặc hủy**; đây không phải câu trả lời “mọi mã Java bên trong task đã thoát và đã dọn tài nguyên”.

Khi thiết kế nghiệp vụ, cần tách:

- **Cancellation requested**: một thành phần yêu cầu ngừng.
- **Future cancelled**: đối tượng Future đã đánh dấu hủy.
- **Execution stopped**: mã task đã thoát vòng xử lý hoặc kết thúc đoạn chặn.
- **Cleanup complete**: tài nguyên, lock, connection, file và trạng thái nghiệp vụ đã được thu hồi/xử lý.
- **Business effect committed**: tác động bên ngoài, ví dụ đã chuyển tiền hoặc ghi DB, có thể không đảo ngược chỉ vì caller hủy Future.

Một ứng dụng chỉ nhìn Future.isCancelled() để xác nhận tất cả các mức trên là sai về thiết kế.

## 2. Hợp đồng Future.cancel(mayInterruptIfRunning)

Java khai báo:

~~~java
boolean cancel(boolean mayInterruptIfRunning);
boolean isCancelled();
boolean isDone();
V get() throws InterruptedException, ExecutionException;
V get(long timeout, TimeUnit unit)
        throws InterruptedException, ExecutionException, TimeoutException;
~~~

Đây là **chữ ký tóm lược của interface Future<V>**, không phải file Java biên dịch độc lập.

Theo hợp đồng **Future**:

- Nếu công việc chưa bắt đầu, khi hủy thành công nó **không nên được chạy**.
- Nếu công việc đã bắt đầu, **mayInterruptIfRunning = true** cho phép implementation **yêu cầu interrupt thread đang thực thi**, khi implementation biết thread đó.
- Nếu **mayInterruptIfRunning = false**, không yêu cầu ngắt thread đang chạy; công việc đang thực thi có thể tiếp tục.
- Nếu task đã hoàn thành, việc hủy thường không còn tác dụng.
- Giá trị **boolean** do cancel trả về phản ánh kết quả nỗ lực hủy theo implementation; **đừng dùng riêng nó để suy luận worker đã dừng**. Dùng isCancelled() để xem trạng thái Future.
- Sau khi Future được hủy, **get()** hoặc **get(timeout, unit)** sẽ ném **CancellationException** (unchecked), không trả về kết quả tính toán.
- **isDone()** trả true cho Future đã hoàn tất bình thường, lỗi hoặc bị hủy; một task không thể được coi là “thành công” chỉ từ isDone().

### So sánh cancel(false) và cancel(true)

| Tình huống | cancel(false) | cancel(true) |
| --- | --- | --- |
| Task chưa bắt đầu | Có thể đánh dấu hủy để body không chạy | Tương tự |
| Task đang chạy trong FutureTask | Có thể đánh dấu Future đã hủy nhưng **không gửi interrupt** | Cố **interrupt** thread chạy task |
| Code đang chặn bằng sleep/wait/CountDownLatch.await | Không nhờ tham số false để đánh thức | Interrupt có thể làm API ném InterruptedException |
| Code tính toán CPU không kiểm tra cờ ngắt | Có thể tiếp tục chạy | **Vẫn có thể tiếp tục chạy** |
| Code có side effect đã commit | Không hoàn tác side effect | Không hoàn tác side effect |
| CompletableFuture chuẩn | Đánh dấu Future bị hủy | **Cùng semantics; true không điều khiển interrupt** |

**Đừng nhầm cancel(false) với “không thể hủy task đang chạy”.** Chẳng hạn, FutureTask có thể chuyển trạng thái Future sang cancelled mà **cho phép phần computation đang chạy tiếp tục**. Kết quả sau cùng không được Future trả cho caller, nhưng side effect bên trong task vẫn có thể xảy ra.

### Các trạng thái minh họa

~~~text
NEW (queued) --cancel--> CANCELLED  (body không nên chạy)
  |
  +--worker starts--> RUNNING --return--> SUCCESS
                            |
                            +--throws--> FAILURE
                            |
                            +--cancel(true)--> Future CANCELLED
                                                |
                                                +--worker may continue
                                                +--or cooperate and exit
~~~

Đây là mô hình khái niệm, **không phải enum trạng thái chuẩn của mọi Future implementation**.

## 3. Thread.interrupt() là tín hiệu, không phải Thread.stop()

Một lệnh interrupt gửi **yêu cầu hợp tác** tới một thread; nó không an toàn nếu hiểu như “tiêu diệt thread ngay lập tức”.

Khi Thread.interrupt() xảy ra, thường có hai tình huống:

1. **Thread đang chờ trong một API nhạy với interrupt**: ví dụ Thread.sleep(), Object.wait(), Thread.join() hoặc CountDownLatch.await(). API thường ném **InterruptedException**, đồng thời **xóa interrupt flag** theo hợp đồng của API.
2. **Thread đang chạy code CPU hoặc API không đáp ứng interrupt**: cờ interrupt được đặt; code phải **kiểm tra và thoát** tại điểm hợp lý, hoặc API đang chặn phải hỗ trợ interrupt theo hợp đồng riêng.

Interrupt có thể có hiệu ứng khác với NIO InterruptibleChannel, Selector và một số blocking operation chuyên biệt. Không được mặc định mọi socket client, JDBC driver, HTTP client hoặc native call đều ngừng ngay khi interrupt.

**Không dùng Thread.stop()** để “ép” task dừng. Cưỡng bức dừng luồng có thể để lại invariants không nhất quán và lock/tài nguyên ở trạng thái nguy hiểm. Thiết kế đúng thường yêu cầu signal + điểm kiểm tra ngắt + cleanup có chủ đích.

### Cờ interrupt và hai cách kiểm tra

~~~java
boolean interrupted = Thread.currentThread().isInterrupted();

boolean wasInterruptedAndClearFlag = Thread.interrupted();
~~~

Đây là **hai dòng minh họa**, không phải file Java độc lập.

- **isInterrupted()**: kiểm tra trạng thái mà **không xóa cờ**.
- **Thread.interrupted()**: phương thức static kiểm tra trạng thái của **thread hiện tại** và **xóa cờ interrupt**.

Vì vậy, trong một vòng CPU-bound có điều kiện ngắt, thường dùng:

~~~java
while (!Thread.currentThread().isInterrupted()) {
    performSmallUnitOfWork();
}
~~~

Đây là **đoạn minh họa** với performSmallUnitOfWork đã được định nghĩa. Nếu code dùng Thread.interrupted() nhiều lần không có lý do, nó có thể tiêu thụ tín hiệu ngắt rồi khiến tầng khác không quan sát được yêu cầu hủy.

## 4. InterruptedException: phải xử lý để hợp tác dừng

Nhiều API chặn ở Java có chữ ký **throws InterruptedException**. Khi nhận exception này, một trong hai hướng đúng thường là:

**A. Nếu method có thể khai báo throws InterruptedException, hãy truyền lên tầng sở hữu chính sách:**

~~~java
void waitForSignal(CountDownLatch latch)
        throws InterruptedException {
    latch.await();
}
~~~

Đây là **đoạn method minh họa** có import CountDownLatch. Việc truyền exception lên cho phép caller quyết định hủy và cleanup.

**B. Nếu không thể truyền InterruptedException (ví dụ run() của Runnable), hãy khôi phục cờ ngắt rồi thoát hợp lý:**

~~~java
@Override
public void run() {
    try {
        blockingOperation();
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        return; // Không coi gián đoạn là công việc hoàn tất thành công.
    } finally {
        releaseOwnedResources();
    }
}
~~~

Đây là **đoạn minh họa** trong class có blockingOperation và releaseOwnedResources.

Giải thích việc khôi phục cờ: nhiều API như **sleep/await** xóa interrupt status khi ném InterruptedException. Nếu không truyền exception lên được, gọi **Thread.currentThread().interrupt()** giúp bảo toàn thông tin có yêu cầu ngắt trước khi kết thúc method. **Không tiếp tục làm nghiệp vụ** như chưa có chuyện gì xảy ra.

**Cách sai:**

~~~java
try {
    Thread.sleep(1_000);
} catch (InterruptedException ignored) {
    // Nuốt mất tín hiệu và tiếp tục vòng lặp vô hạn.
}
~~~

Nếu đây là vòng lặp chạy nhiều lần, mỗi lần interrupt có thể bị nuốt rồi task vẫn tiếp tục giữ worker. Caller tưởng đã hủy nhưng hệ thống vẫn ghi log, gọi DB hoặc gửi request.

### Khi nào không nên đơn giản re-interrupt rồi tiếp tục?

- Khi method có thể **throw InterruptedException**: để caller có chính sách hủy rõ ràng thường tốt hơn.
- Khi phải hoàn tất một bước cleanup quan trọng có thể bị interrupt: đặt chiến lược cleanup cụ thể, deadline và quy tắc khôi phục cờ.
- Khi task sở hữu transaction/connection: tránh tiếp tục commit logic nghiệp vụ sau khi đã nhận hủy, trừ khi hợp đồng nghiệp vụ yêu cầu hoàn tất một bước đã bắt đầu.

Một catch chỉ ghi log “interrupted” rồi **không ngừng công việc** thường phá hợp đồng cancellation.

## 5. Ví dụ Java 17 đầy đủ: cancel(true) đánh thức task đang chặn

Ví dụ đầu tiên dùng **ExecutorService.submit()**, trả về Future của task, rồi hủy bằng **cancel(true)**. Task dùng CountDownLatch.await() để chờ; khi nhận interrupt, nó ghi nhận tín hiệu, khôi phục cờ ngắt, thoát và chạy cleanup trong finally.

Tạo file **CooperativeCancelDemo.java**:

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class CooperativeCancelDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch neverReleased = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        AtomicBoolean sawInterrupt = new AtomicBoolean(false);
        AtomicBoolean cleanup = new AtomicBoolean(false);

        try {
            Future<String> future = pool.submit(() -> {
                started.countDown();
                try {
                    neverReleased.await();
                    return "unreachable";
                } catch (InterruptedException e) {
                    sawInterrupt.set(true);
                    Thread.currentThread().interrupt();
                    return "ignored-result";
                } finally {
                    cleanup.set(true);
                    finished.countDown();
                }
            });

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker chưa bắt đầu");
            }

            boolean accepted = future.cancel(true);

            if (!finished.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Worker không thoát sau yêu cầu ngắt");
            }

            boolean cancelledGet = false;
            try {
                future.get();
            } catch (CancellationException expected) {
                cancelledGet = true;
            }

            System.out.println("cancel(true) thành công: " + accepted);
            System.out.println("Future isCancelled: "
                    + future.isCancelled());
            System.out.println("Future isDone: " + future.isDone());
            System.out.println("Worker thấy interrupt: "
                    + sawInterrupt.get());
            System.out.println("Cleanup đã chạy: " + cleanup.get());
            System.out.println("get ném CancellationException: "
                    + cancelledGet);
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Pool chưa kết thúc");
            }
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 17+**:

~~~bash
javac -encoding UTF-8 CooperativeCancelDemo.java
java CooperativeCancelDemo
~~~

**Stdout**, khi môi trường cho worker khởi động và thoát trong các thời hạn test:

~~~text
cancel(true) thành công: true
Future isCancelled: true
Future isDone: true
Worker thấy interrupt: true
Cleanup đã chạy: true
get ném CancellationException: true
~~~

**Vì sao ví dụ xác định?**

1. Main đợi **started**, bảo đảm task đã thực sự bắt đầu trước khi gọi cancel.
2. Task chờ ở **CountDownLatch.await()**, nên không thể tự hoàn thành nếu không có interrupt hoặc không có ai mở latch.
3. **FutureTask** do ExecutorService.submit điển hình dùng có khả năng interrupt thread đang chạy. **cancel(true)** gửi tín hiệu.
4. Lệnh await đáp ứng interrupt bằng InterruptedException; task đánh dấu **sawInterrupt**, chạy finally, rồi dừng.
5. Main đợi **finished** trước khi kiểm tra cleanup. Vì thế stdout **không bị race** giữa thread đang cleanup và thread đang in.
6. **future.get()** ném CancellationException vì trạng thái Future đã bị hủy. Giá trị **ignored-result** mà Callable có thể trả về **không được công bố như một kết quả thành công**.
7. Main đóng executor trong finally để tránh rò rỉ worker sau ví dụ.

**Giới hạn:** các boolean này xác nhận hành vi trong ví dụ đang dùng FutureTask và CountDownLatch. Chúng **không** là lời hứa rằng cancel(true) sẽ làm một lời gọi JDBC, HTTP client hoặc native I/O cụ thể ngừng ngay lập tức.

## 6. cancel(true) không đủ nếu code CPU không kiểm tra ngắt

Một tác vụ CPU-bound như parse file lớn, duyệt hàng triệu phần tử hoặc tính toán theo batch có thể chạy mà không gọi bất kỳ hàm chặn nào ném InterruptedException. Khi đó, interrupt chủ yếu làm **cờ interrupt của thread được đặt**. Nếu vòng lặp không kiểm tra cờ hoặc cancellation token, công việc có thể tiếp tục cho đến khi tự kết thúc.

Ví dụ về một vòng lặp hợp tác:

~~~java
long calculate(List<Integer> numbers) {
    long total = 0;

    for (int i = 0; i < numbers.size(); i++) {
        if (Thread.currentThread().isInterrupted()) {
            throw new java.util.concurrent.CancellationException(
                    "Bị yêu cầu dừng");
        }

        total += numbers.get(i);
    }

    return total;
}
~~~

Đây là **đoạn method minh họa**; cần import java.util.List. Vòng lặp kiểm tra interrupt ở mỗi bước, sau đó dừng tại checkpoint an toàn. Đối với phép toán rất nhỏ, kiểm tra cờ quá dày có thể tốn overhead; có thể kiểm tra theo từng khối, miễn deadline và khả năng dừng được chấp nhận.

**Điểm chính:** cancellation là một protocol giữa phía yêu cầu và phía xử lý. Đặt checkpoint tại ranh giới nghiệp vụ có thể dừng an toàn, không phải ở giữa một thao tác cần hoàn thành nguyên tử.

### Đừng suy từ Future.isDone() rằng vòng lặp đã thoát

Nếu một FutureTask được cancel trong khi task vẫn đang chạy một vòng lặp không kiểm tra cờ, **Future.isDone() có thể là true**, còn worker vẫn sử dụng CPU. Từ thời điểm bị cancel, Future có thể không còn cung cấp một kết quả hay tín hiệu “worker thật sự đã dừng” đáng tin. Nếu cần xác nhận cleanup, phải có **một tín hiệu hoàn tất thực thi riêng** hoặc quan sát lifecycle/resource.

## 7. Ví dụ Java 17: Future đã hủy nhưng task vẫn còn chạy

Ví dụ sau cố ý **bỏ qua cờ ngắt** trong vòng CPU để chứng minh khác biệt giữa **Future cancellation** và **kết thúc thực thi**. Nó có một AtomicBoolean riêng để main giải phóng task, tránh giữ worker vô hạn.

Tạo file **NonCooperativeCancelDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class NonCooperativeCancelDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        AtomicBoolean stop = new AtomicBoolean(false);

        try {
            Future<?> future = pool.submit(() -> {
                started.countDown();
                try {
                    while (!stop.get()) {
                        // Cố ý không kiểm tra interrupt.
                        Thread.onSpinWait();
                    }
                } finally {
                    finished.countDown();
                }
            });

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker chưa bắt đầu");
            }

            boolean cancelled = future.cancel(true);

            System.out.println("Future cancel(true): " + cancelled);
            System.out.println("Future isDone: " + future.isDone());
            System.out.println("Future isCancelled: "
                    + future.isCancelled());
            System.out.println("Worker vẫn đang chạy: "
                    + (finished.getCount() == 1));

            // Tín hiệu riêng cho phép vòng lặp kết thúc.
            stop.set(true);

            if (!finished.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker chưa thoát");
            }

            System.out.println("Worker đã kết thúc: true");
        } finally {
            stop.set(true);
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Pool chưa kết thúc");
            }
        }
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 NonCooperativeCancelDemo.java
java NonCooperativeCancelDemo
~~~

**Stdout** trong điều kiện thông thường:

~~~text
Future cancel(true): true
Future isDone: true
Future isCancelled: true
Worker vẫn đang chạy: true
Worker đã kết thúc: true
~~~

**Giải thích:**

- started xác nhận Runnable đã vào vòng xử lý trước khi main cancel.
- **cancel(true)** chuyển Future của công việc sang cancelled và có thể đặt interrupt flag trên worker.
- **Vòng lặp chỉ quan sát stop**, không kiểm tra cờ interrupt; nó tiếp tục chạy.
- Main kiểm tra **finished.getCount() == 1** trước khi set stop, nên có bằng chứng worker chưa vào finally ở thời điểm Future đã cancelled.
- Khi main set stop=true, worker thoát, đếm ngược finished và công việc vật lý kết thúc.

Đây là ví dụ **cố ý tiêu cực** nhằm minh họa điều không nên làm ở production: một vòng spin tiêu tốn CPU. Nó chỉ chạy rất ngắn trong test và có finally để giải phóng worker. Vòng tính toán thật nên dùng checkpoint hợp tác và không dùng busy-spin làm cơ chế chờ.

## 8. Hủy một tác vụ còn trong queue

FutureTask có thể được hủy **trước khi công việc bắt đầu**. Một worker sau đó lấy wrapper đã bị hủy từ queue thì phần Callable/Runnable thực sự không nên chạy.

Với **ExecutorService.newSingleThreadExecutor**, có thể kiểm chứng bằng cách giữ worker ở task đầu tiên, đẩy task thứ hai vào queue rồi cancel task thứ hai. Đây là cơ chế khác với interrupt thread đang chạy.

Tạo file **CancelQueuedDemo.java**:

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class CancelQueuedDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch releaseFirst = new CountDownLatch(1);
        AtomicBoolean secondRan = new AtomicBoolean(false);

        try {
            Future<?> first = pool.submit(() -> {
                firstStarted.countDown();
                try {
                    releaseFirst.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });

            if (!firstStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Task đầu chưa chạy");
            }

            Future<?> queued = pool.submit(
                    () -> secondRan.set(true));

            boolean cancelled = queued.cancel(false);

            releaseFirst.countDown();
            first.get(5, TimeUnit.SECONDS);

            // Barrier phía sau task bị hủy: xác nhận worker đã
            // xử lý hết các mục queue gửi trước barrier.
            Future<?> barrier = pool.submit(() -> { });
            barrier.get(5, TimeUnit.SECONDS);

            boolean getCancelled = false;
            try {
                queued.get();
            } catch (CancellationException expected) {
                getCancelled = true;
            }

            System.out.println("Hủy trước khi chạy: " + cancelled);
            System.out.println("Body task thứ hai đã chạy: "
                    + secondRan.get());
            System.out.println("get báo hủy: " + getCancelled);
        } finally {
            releaseFirst.countDown();
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Pool chưa kết thúc");
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 CancelQueuedDemo.java
java CancelQueuedDemo
~~~

**Stdout:**

~~~text
Hủy trước khi chạy: true
Body task thứ hai đã chạy: false
get báo hủy: true
~~~

**Ý nghĩa:** cancel(false) vẫn có thể hủy một task **chưa bắt đầu**. Không cần yêu cầu interrupt worker, bởi worker đầu tiên vẫn đang xử lý một task khác. Sau khi releaseFirst mở, wrapper task thứ hai đã hủy có thể được lấy khỏi hàng đợi nhưng **body không được chạy**.

**Đừng đồng nhất task không chạy với queue đã sạch ngay lập tức.** Việc hủy một FutureTask không nhất thiết xóa wrapper của nó ra khỏi **mọi implementation hàng đợi ngay tại thời điểm cancel**. Các loại executor (đặc biệt scheduled executor) có chính sách loại task hủy riêng. Cần quan sát queue retention/cleanup theo loại executor, không dựa vào một quy tắc chung.

## 9. Khác biệt quan trọng: CompletableFuture.cancel(true) không gửi interrupt

**CompletableFuture** của Java SE 17 cũng implements Future, nhưng Javadoc nêu rõ: cancellation ở implementation này tương đương một dạng **exceptional completion bằng CancellationException**, còn tham số **mayInterruptIfRunning không có tác dụng** vì interrupts không được dùng để điều khiển phần processing.

Ví dụ:

~~~java
CompletableFuture<String> result =
        CompletableFuture.supplyAsync(
                () -> blockingComputation(), executor);

result.cancel(true);
~~~

Đây là **đoạn minh họa** với blockingComputation và executor trong scope. Bạn **không thể suy ra** việc gọi cancel(true) trên CompletableFuture đã interrupt worker của blockingComputation. Kết quả Future có thể bị đánh dấu canceled, trong khi supplier vẫn chạy và có side effect.

### Ví dụ Java 17 xác định

Tạo file **CompletableCancelDemo.java**:

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class CompletableCancelDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        AtomicBoolean gotInterruptedException = new AtomicBoolean(false);

        try {
            CompletableFuture<String> future =
                    CompletableFuture.supplyAsync(() -> {
                        started.countDown();
                        try {
                            release.await();
                        } catch (InterruptedException e) {
                            gotInterruptedException.set(true);
                            Thread.currentThread().interrupt();
                        } finally {
                            finished.countDown();
                        }
                        return "physical-computation-finished";
                    }, pool);

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker chưa bắt đầu");
            }

            boolean cancelled = future.cancel(true);

            System.out.println("CompletableFuture cancel: "
                    + cancelled);
            System.out.println("CompletableFuture isCancelled: "
                    + future.isCancelled());
            System.out.println("Worker chưa thoát await: "
                    + (finished.getCount() == 1));

            release.countDown();

            if (!finished.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker chưa kết thúc");
            }

            boolean getCancelled = false;
            try {
                future.get();
            } catch (CancellationException expected) {
                getCancelled = true;
            }

            System.out.println("Worker bị interrupt do cancel: "
                    + gotInterruptedException.get());
            System.out.println("get báo CancellationException: "
                    + getCancelled);
        } finally {
            release.countDown();
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Pool chưa kết thúc");
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 CompletableCancelDemo.java
java CompletableCancelDemo
~~~

**Stdout:**

~~~text
CompletableFuture cancel: true
CompletableFuture isCancelled: true
Worker chưa thoát await: true
Worker bị interrupt do cancel: false
get báo CancellationException: true
~~~

**Diễn giải:**

1. Supplier chờ ở release.await, và main biết worker đã chạy từ started.
2. **future.cancel(true)** đổi trạng thái CompletableFuture thành canceled, **không interrupt worker** trong implementation chuẩn.
3. Worker vẫn đang đợi release, nên finished chưa về 0.
4. Main tự mở release để supplier kết thúc; việc supplier có trả một String không đổi trạng thái **đã canceled** của future.
5. **get()** ném CancellationException; output không phải physical-computation-finished.

**Không nên biến điều này thành nhận định “mọi API trả CompletableFuture không bao giờ có thể interrupt”.** Một framework/library có thể tạo thêm cơ chế cancellation bên ngoài hoặc một Future khác có quyền điều khiển task. Điều được chứng minh ở đây là **lời gọi CompletableFuture.cancel(true) trên implementation JDK chuẩn không tự gửi interrupt**.

## 10. Tác động lên các dependent stages của CompletableFuture

Một pipeline có nhiều bước:

~~~java
CompletableFuture<Integer> source =
        CompletableFuture.supplyAsync(
                () -> loadValue(), ioExecutor);

CompletableFuture<String> output = source
        .thenApply(n -> n * 2)
        .thenApplyAsync(n -> "score:" + n, cpuExecutor);
~~~

Đây là **đoạn minh họa** với các dependency trong scope.

Nếu hủy **source** trước khi source hoàn tất, những dependent stages chưa hoàn tất sẽ bị đưa vào **exceptional completion** theo semantics của CompletableFuture; có thể có **CompletionException với CancellationException làm nguyên nhân**.

Nếu hủy **output**, đó là thay đổi trạng thái của stage output. **Không mặc nhiên coi việc hủy output là lời yêu cầu interrupt/tự hủy toàn bộ công việc upstream**. Nhiều stage đã lên lịch vẫn có thể đang chạy hoặc có side effect.

Điều này ảnh hưởng tới việc sử dụng:

- **thenApply/thenCompose**: composition tạo quan hệ completion, không tự tạo một protocol physical stop cho toàn bộ cây task.
- **allOf**: tổng hợp completion của các futures, không phải “cancel all children” tự động.
- **anyOf**: một nhánh hoàn tất không mặc nhiên dừng những nhánh còn lại.
- **orTimeout**: chuyển trạng thái future khi quá hạn, **không tự interrupt các nguồn công việc đang chạy**.
- **completeOnTimeout**: có thể đặt giá trị fallback khi hết hạn, nhưng không tự dừng supplier I/O ở phía dưới.
- **exceptionally/handle**: hồi phục giá trị theo lỗi completion, không biến một việc đang chạy thành đã ngừng một cách vật lý.

Muốn **cancel nhiều công việc con**, bạn phải quản lý riêng các handles có khả năng cancel, deadline và tài nguyên của từng công việc. Nếu API bên dưới cung cấp cơ chế cancel riêng, gọi nó theo hợp đồng của API ấy và thu thập xác nhận cleanup thích hợp.

## 11. Timeout không đồng nghĩa cancellation

Một caller có thể chờ Future:

~~~java
try {
    return future.get(2, TimeUnit.SECONDS);
} catch (TimeoutException e) {
    // Caller không còn muốn đợi quá 2 giây.
}
~~~

Đây là **đoạn minh họa** trong phương thức có future và kiểu dữ liệu trả về phù hợp. **TimeoutException** nghĩa là **caller đợi quá thời hạn**, không đồng nghĩa task tự động ngừng. Nếu code bắt TimeoutException rồi trả response, worker có thể tiếp tục chạy trong background.

Nếu mục tiêu là **không chỉ ngừng đợi mà còn yêu cầu dừng task**, có thể chủ động gọi cancel(true) trên một Future phù hợp:

~~~java
try {
    return future.get(2, TimeUnit.SECONDS);
} catch (TimeoutException e) {
    future.cancel(true);
    throw e;
}
~~~

Đây là **đoạn minh họa**, không phải service hoàn chỉnh. **cancel(true)** vẫn chỉ là nỗ lực dừng có tính hợp tác, không bảo đảm ngắt được mọi I/O. Đồng thời cần phân biệt:

- Timeout **chờ kết quả** của người gọi.
- Timeout **HTTP client/JDBC/socket** của downstream.
- Timeout **queue wait** trước khi task bắt đầu.
- Timeout **hạn xử lý nghiệp vụ** (deadline), tính cả nhiều retry/hops.
- Timeout **shutdown** đợi worker hoàn thành.

Đặt timeout ở một tầng mà không ở tầng khác có thể khiến hệ thống vẫn giữ kết nối và worker vượt qua deadline. Một deadline chung nên được truyền dưới dạng dữ liệu immutable (ví dụ Instant) và được kiểm tra tại các checkpoint phù hợp.

### Race giữa completion và timeout

Ngay lúc get(timeout) trả TimeoutException, task có thể **vừa kịp hoàn thành** hoặc đang về đích. Gọi cancel(true) lúc đó có thể trả false hoặc có kết quả khác tùy Future implementation. Không được suy từ timeout rằng task chắc chắn chưa có side effect hoặc có thể hoàn tác giao dịch.

## 12. Hai loại dừng hợp tác: interrupt và cancellation token

**Thread interrupt** là tín hiệu ở mức **thread**, hữu dụng cho những API blocking có hỗ trợ. Nhưng có những công việc cần dừng theo **nghiệp vụ**, xuyên qua nhiều stage hoặc qua nhiều thread. Khi đó một **cancellation token** riêng có thể giúp chuyển ý định hủy tới các hàm sử dụng nhiều executor.

Ví dụ kiểu token đơn giản:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

public final class CancelToken {
    private final AtomicBoolean cancelled = new AtomicBoolean(false);

    public void cancel() {
        cancelled.set(true);
    }

    public boolean isCancelled() {
        return cancelled.get();
    }
}
~~~

Đây là **một tệp Java 17 độc lập tên CancelToken.java**, không có main. Token có thể được truyền vào các service đã biết quyền sở hữu công việc.

Một worker tính theo nhiều batch:

~~~java
for (Batch batch : batches) {
    if (token.isCancelled()
            || Thread.currentThread().isInterrupted()) {
        throw new java.util.concurrent.CancellationException(
                "Job đã bị hủy");
    }

    processBatch(batch);
}
~~~

Đây là **đoạn minh họa**, giả sử có Batch, batches và processBatch. Với mỗi batch, cần xác định công việc nào đã có side effect; dừng tại checkpoint sau một batch không tự hoàn tác batch trước.

**Hạn chế của token:**

- Một **AtomicBoolean** không tự interrupt thread đang chặn trong I/O.
- Future.cancel(true) **không tự set token**; phải thiết kế một owner của tác vụ gọi cả hai khi phù hợp.
- Token nằm trong JVM; khi chạy trên nhiều service/process, phải có trạng thái hủy được truyền qua giao thức/queue/store.
- Không phải lúc nào dừng ngay cũng an toàn; ví dụ đang cập nhật một cặp dữ liệu cần transaction hoặc compensate có thể phải hoàn thành bước đang tiến hành trước khi dừng.

Một API hủy có chất lượng nên xác định **được nhận yêu cầu hủy**, **đã ngừng nhận việc mới**, **đã ngừng phần tính toán** và **đã dọn xong** là những trạng thái khác nhau.

## 13. Thiết kế cleanup: finally, try-with-resources và transaction

Khi task dừng vì interrupt, nó vẫn phải thả resource mà nó sở hữu: lock, stream, file handle, connection, semaphore permit và những phần state tạm thời.

Mẫu logic:

~~~java
void work() throws InterruptedException {
    Resource resource = acquireResource();
    try {
        performSteps(resource);
    } finally {
        resource.close();
    }
}
~~~

Đây là **pseudocode Java** với Resource, acquireResource và performSteps do ứng dụng định nghĩa. Nó minh họa **ownership/cleanup**, không phải tệp chạy độc lập.

Với resource implements AutoCloseable, **try-with-resources** giúp đóng khi task thoát bình thường hoặc vì exception. Tuy nhiên, cleanup cũng có thể thất bại, bị chặn hoặc cần deadline; không nên mặc định một finally luôn thành công trong mọi hạ tầng.

### Tình huống có giao dịch

Một task đang ghi DB rồi nhận interrupt:

- Interrupt không tự động **ROLLBACK** mọi transaction bằng một quy tắc phổ quát.
- Nếu thực thi trong Spring **@Transactional**, việc transaction commit/rollback phụ thuộc exception, cấu hình rollback rules và ranh giới transaction thực tế.
- Khi task đã gửi request thanh toán hoặc gọi API bên ngoài, kết quả có thể đã được thực hiện ở downstream dù caller hủy Future.
- Retry sau cancellation phải có **idempotency key** và chiến lược kiểm tra trạng thái/compensation.

Đừng đặt một **catch(InterruptedException)** trả về trạng thái “success” rồi tiếp tục commit nghiệp vụ nếu yêu cầu dừng phải làm hủy tiến trình.

### Tài nguyên của task chưa từng bắt đầu

Nếu task bị hủy **khi còn trong queue**, **finally nằm bên trong body task có thể không bao giờ chạy**, vì body chưa khởi động. Các resource được phân bổ **trước lúc submit** cần owner và cleanup bên ngoài task hoặc trong cancellation callback riêng. Đây là lý do hạn chế mở connection/file handle trước khi task thực sự chạy và đẩy chúng vào queue lâu.

## 14. Spring @Async: khả năng cancel phụ thuộc loại Future và executor

Trong Spring, **@Async** dùng cơ chế proxy/interceptor để gửi method vào một executor. Bean cần được Spring quản lý, async support được bật và lời gọi phải đi **qua proxy**; tự gọi **this.method()** trong cùng bean thường bỏ qua proxy.

Khi method có kiểu trả về Future hoặc CompletableFuture, caller nhận một handle đại diện cho kết quả. Nhưng **khả năng interrupt tác vụ thực** không giống nhau cho mọi kiểu trả về và mọi adapter:

- Với một Future của **executor.submit(Callable)** được hiện thực bởi **FutureTask**, cancel(true) thường có khả năng interrupt worker đang chạy.
- Với **CompletableFuture** chuẩn, **cancel(true) không tự interrupt** supplier/body. Điều này vẫn quan trọng khi CompletableFuture được trả ra từ Spring @Async.
- Một framework có thể dùng wrapper khác, delegation hoặc executor-specific behavior; không khẳng định cancel trên một Future bên ngoài luôn truyền đúng tới task gốc mà không kiểm tra implementation.
- **@Async void** không trả Future cho caller để gọi cancel. Muốn hủy, phải thiết kế command/job handle, deadline, token hoặc API quản lý job riêng.

### Ví dụ cấu hình ThreadPoolTaskExecutor trong Spring

~~~java
package example.concurrent;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class WorkConfig {
    @Bean("workExecutor")
    public ThreadPoolTaskExecutor workExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("work-");
        return executor;
    }
}
~~~

Đây là **tệp cấu hình trong ứng dụng có Spring Context**, không thể biên dịch với javac thuần khi không có dependency Spring. Ví dụ chọn core/max/queue hữu hạn để mô tả pool; kích thước thực tế phải theo năng lực tài nguyên.

### Ví dụ gửi Callable để có Future có thể yêu cầu interrupt

~~~java
package example.concurrent;

import java.util.concurrent.Future;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    private final ThreadPoolTaskExecutor workExecutor;

    public ReportService(ThreadPoolTaskExecutor workExecutor) {
        this.workExecutor = workExecutor;
    }

    public Future<String> submitReport(String id) {
        return workExecutor.submit(() -> {
            try {
                return generateReport(id);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw e;
            }
        });
    }

    private String generateReport(String id)
            throws InterruptedException {
        Thread.sleep(1000);
        return "report:" + id;
    }
}
~~~

Đây là **tệp minh họa trong Spring application** dùng bean ThreadPoolTaskExecutor. Nó chủ động sử dụng **submit(Callable)** để trả Future; generateReport ngủ mô phỏng một thao tác chờ có hỗ trợ interruption. Trong production cần timeout và resource cleanup riêng, không dùng sleep để mô phỏng nghiệp vụ thật.

Caller có thể giữ Future của task rồi **cancel(true)**. Với implementation ThreadPoolTaskExecutor dựa trên ThreadPoolExecutor, handle có cơ chế hủy gần với FutureTask. Tuy nhiên, việc hủy ở giữa tác vụ không tự undo logic đã chạy trước đó.

**Cần tránh một suy luận sai:** dùng **@Async** trả **CompletableFuture** không giống với việc caller đang cầm trực tiếp FutureTask do executor.submit. Nếu mục tiêu là dừng worker thực sự, hãy kiểm tra cơ chế scheduling/cancellation của implementation và cân nhắc thiết kế quản lý job có token/deadline rõ.

## 15. Spring CompletableFuture, lỗi và thông báo kết quả

Một ví dụ method Spring:

~~~java
@Async("workExecutor")
public CompletableFuture<String> buildReport(String id) {
    String result = compute(id);
    return CompletableFuture.completedFuture(result);
}
~~~

Đây là **đoạn minh họa** trong bean có compute và imports tương ứng. Khi gọi qua Spring proxy, method được dispatch theo executor; bên trong body có thể trả completedFuture vì computation đã hoàn thành ở body thread. Caller quan sát future được proxy cung cấp.

Nếu caller gọi **future.cancel(true)** trên một **CompletableFuture** trả về, **đừng mặc định nó sẽ interrupt body thread**. Cancel ở tầng completion có thể chỉ đánh dấu kết quả đã hủy. Với task thật sự có side effect, hệ thống cần cancellation protocol riêng nếu muốn dừng physical processing.

### Các trạng thái lỗi phải phân biệt

| Sự kiện | Điều caller có thể quan sát | Ý nghĩa |
| --- | --- | --- |
| Executor không nhận task | Có thể ném **TaskRejectedException** ngay tại submit/proxy | Công việc có thể chưa được nhận |
| Worker ném exception | Future hoàn thành với lỗi, get thường cho **ExecutionException** | Task đã chạy và thất bại |
| Future bị hủy | **CancellationException**, isCancelled true | Handle đã canceled; chưa kết luận cleanup |
| Caller chờ quá deadline | **TimeoutException** từ get(timeout) | Caller hết thời gian chờ, task có thể còn chạy |
| CompletableFuture.orTimeout | Future hoàn thành ngoại lệ với timeout | Không tự interrupt supplier |
| Caller bị interrupt khi đợi get | **InterruptedException** ở caller | Đây là interrupt của thread đợi, không đồng nghĩa worker đã bị cancel |

**Không catch mọi exception rồi coi là task được cancel.** Điều này làm sai metrics và gây những vòng retry không cần thiết. Phân biệt exception ở **submit**, **wait** và **worker execution**.

## 16. Không interrupt bừa worker thread của pool

Khi dùng ThreadPoolTaskExecutor, worker có thể được tái sử dụng để phục vụ nhiều request khác nhau. Không nên **giữ trực tiếp Thread worker rồi tự Thread.interrupt()** như một cách hủy job chung nếu executor/framework đang quản lý thread đó.

Lý do:

- Bạn có thể gửi interrupt nhầm **task khác** sau khi worker đã kết thúc task ban đầu và được tái sử dụng.
- Bạn có thể phá protocol đồng bộ nội bộ của executor nếu bypass API.
- Bạn phải tự giải quyết tình huống race giữa lúc task hoàn thành và thread bắt đầu task tiếp.
- Không có hợp đồng quản lý ownership/interrupt nếu chỉ lưu tên thread hoặc tham chiếu Thread dùng chung.

**Ưu tiên hủy qua handle của công việc** (Future hợp lệ, job token, API của executor/cancelable task), không thao tác trực tiếp vào thread worker dùng chung.

### InterruptedException trong pool thread

Trong task, khi API blocking ném InterruptedException, hãy giữ ý nghĩa yêu cầu dừng. Nếu không thể propagate, khôi phục flag và thoát khỏi body. Không đặt Thread.interrupted() để “làm sạch” flag giữa chừng rồi tiếp tục xử lý. Việc reset trạng thái trước task tiếp theo thuộc trách nhiệm cấu trúc executor và quy tắc task, không phải giấy phép cho một task nuốt interrupt.

## 17. shutdown(), shutdownNow() và hủy riêng một task

Đây là ba thao tác khác nhau:

| API | Phạm vi | Hành vi chủ đạo |
| --- | --- | --- |
| **future.cancel(true)** | Một Future/task handle | Yêu cầu hủy, có thể interrupt đúng task theo implementation |
| **executor.shutdown()** | Cả ExecutorService | Ngừng nhận task mới, thông thường cho phép task đã nhận hoàn tất |
| **executor.shutdownNow()** | Cả ExecutorService | Cố ngừng những task đang thực thi (thường bằng interrupt), ngăn task chờ bắt đầu và trả danh sách task chưa chạy |

**shutdownNow() cũng là best effort**, không bảo đảm dừng mọi worker tức thì nếu task không hợp tác. Một ứng dụng có lifecycle đúng thường gọi shutdown, chờ một thời hạn, rồi cân nhắc shutdownNow khi quá deadline.

~~~java
pool.shutdown();
if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
    pool.shutdownNow();
}
~~~

Đây là **đoạn minh họa** trong một phương thức có pool và xử lý InterruptedException phù hợp. Nếu thread gọi awaitTermination bị interrupt, nó phải xử lý theo chính sách lifecycle (có thể shutdownNow rồi khôi phục flag) thay vì nuốt ngoại lệ.

Spring quản lý vòng đời ThreadPoolTaskExecutor theo cấu hình và lifecycle của ApplicationContext. **Không tự tắt shared Spring executor sau từng HTTP request**; như vậy có thể làm hỏng những request khác đang dùng pool. Hủy một công việc bằng handle/token của chính công việc đó; shutdown pool khi toàn ứng dụng hoặc component sở hữu pool dừng theo thiết kế.

## 18. HTTP disconnect, timeout request và business cancellation

Trong một web application, người dùng đóng trình duyệt, client ngắt kết nối hoặc gateway trả HTTP 504 **không đồng nghĩa worker do bạn tự gửi vào executor đã tự động dừng**.

Cần xác định:

- **HTTP request timeout** chỉ giới hạn phần giao tiếp theo cấu hình framework/container.
- **Future.get(timeout)** giới hạn thời gian đợi của một caller cụ thể.
- **Client socket disconnect** có thể báo lỗi ở tầng I/O nhưng không tự hủy job nghiệp vụ đã tách khỏi request.
- **Business cancellation** là một hành động có hợp đồng rõ: tìm job bằng jobId, xác thực quyền hủy, ghi trạng thái cancel requested và truyền tín hiệu đến worker/job processor.
- **Durable background job** thường cần trạng thái lưu trong DB/queue, vì một Future trong RAM mất ý nghĩa qua process restart hoặc khi job được xử lý bởi worker process khác.

Một API có thể trả lời:

~~~text
POST /reports       -> 202 Accepted, trả jobId (nếu đã lưu nhận việc)
DELETE /reports/{id} -> ghi nhận cancel requested
GET /reports/{id}    -> PENDING / RUNNING / CANCEL_REQUESTED /
                        CANCELLED / SUCCEEDED / FAILED
~~~

Đây là **phác thảo API**, không phải hợp đồng mặc định của Spring. Có thể cần trạng thái CANCEL_FAILED hoặc FINISHED_WITH_SIDE_EFFECT khi hủy quá muộn. **Cancel requested** và **cancelled** không nên bị coi như cùng một sự kiện.

Một HTTP endpoint trả **202 Accepted** sau khi một TaskExecutor đã reject là sai nếu ý nghĩa 202 là công việc đã được nhận. Cần kiểm tra trạng thái submit hoặc durable enqueue trước khi xác nhận.

## 19. Side effects và race khi cancel quá muộn

Ví dụ một tác vụ:

~~~text
[validate] -> [write DB] -> [call payment gateway] -> [send email]
                     ^
                     |
                cancel(true) ở thời điểm này
~~~

Nếu cancel xảy ra sau khi DB commit hoặc external API đã nhận lệnh, interrupt worker **không làm đảo ngược** tác động đã xảy ra.

Thiết kế đúng cho một workflow có side effect cần:

1. Chọn checkpoint có thể dừng an toàn **trước khi** bắt đầu một bước không đảo ngược.
2. Kiểm tra cả **deadline** và **cancel token** ở checkpoint.
3. Với step đã bắt đầu, quyết định **chờ kết quả, kiểm tra trạng thái hoặc compensate**; không mặc định “thread đã bị ngắt” nghĩa là downstream chưa chạy.
4. Dùng **idempotency key** khi retry hoặc khi caller có thể gửi lặp lại yêu cầu.
5. Lưu trạng thái/job version để tránh hai phía cùng báo CANCELLED và SUCCEEDED do race.
6. Ghi **sự kiện hoàn tất cleanup** khi worker đã thả tài nguyên, không chỉ khi Future.isDone.

**Câu hỏi nghiệp vụ bắt buộc:** “hủy có nghĩa là không bắt đầu bước mới, hay phải cố dừng cả bước đang chạy?” Hai hợp đồng này có tác động khác nhau lên timeout, compensation, quota và thông báo cho người dùng.

## 20. Kiểm thử cancellation không dựa vào may rủi scheduler

Một test đúng cần tạo được trạng thái trước khi cancel:

### Test task đang chạy và nhạy interrupt

1. Dùng **CountDownLatch started** để biết worker đã bắt đầu.
2. Đưa worker vào **await()**, bảo đảm chưa tự kết thúc.
3. Main gọi **Future.cancel(true)**.
4. Worker ghi nhận InterruptedException và thông báo cleanup bằng **finished** latch.
5. Main chờ finished có timeout rồi mới assert.
6. Xác minh Future.isCancelled() và Future.get() báo CancellationException.

Đó là mô hình của **CooperativeCancelDemo**.

### Test task không hợp tác

1. Task cố ý bỏ qua interrupt nhưng có **AtomicBoolean stop** riêng để cleanup.
2. Main đợi task bắt đầu, gọi cancel(true).
3. Assert Future.isDone/isCancelled true **nhưng finished vẫn chưa được signal**.
4. Set stop và đợi finished; tránh test rò worker.

Đó là mô hình của **NonCooperativeCancelDemo**.

### Test queued task

1. Pool một worker đang bận.
2. Task thứ hai nằm trong queue.
3. cancel(false) task thứ hai trước khi giải phóng worker.
4. Sau khi worker đầu hoàn tất, dùng một barrier task để đợi queue được xử lý.
5. Assert body task thứ hai **không chạy**.

Đó là mô hình của **CancelQueuedDemo**.

### Test CompletableFuture

1. Supplier chạy và chờ latch không tự hoàn tất.
2. Main gọi CompletableFuture.cancel(true).
3. Assert Future đánh dấu canceled **nhưng worker vẫn chờ**.
4. Tự mở latch, xác nhận worker hoàn tất và **không quan sát InterruptedException do cancellation**.
5. get vẫn báo CancellationException.

Đó là mô hình của **CompletableCancelDemo**.

**Không lấy Thread.sleep(100) làm bằng chứng task đã bắt đầu hay đã thoát.** Thread.sleep có thể dùng khi công việc thực sự cần delay, nhưng test concurrency phải có công cụ đồng bộ để đặt thứ tự sự kiện. Luôn đặt timeout cho await và get để CI không treo vĩnh viễn.

## 21. Các nhầm lẫn phổ biến

**“Future.cancel(true) giết task ngay lập tức.”** Sai. Với FutureTask, nó có thể yêu cầu interrupt; task phải hợp tác để dừng hoặc API đang chặn phải hỗ trợ interrupt.

**“cancel trả true chứng tỏ worker đã cleanup xong.”** Sai. Đó là kết quả nỗ lực hủy Future, không phải tín hiệu cleanup vật lý.

**“isDone() chỉ true khi task thành công.”** Sai. Exception và cancellation đều có thể khiến isDone true.

**“Future.cancel(false) không bao giờ hủy được task.”** Sai. Nó có thể hủy queued task, và FutureTask có thể đánh dấu canceled ngay cả khi task đang chạy mà không interrupt.

**“CompletableFuture.cancel(true) luôn interrupt supplier.”** Sai theo Javadoc Java 17: mayInterruptIfRunning **không có tác dụng** ở CompletableFuture chuẩn.

**“Thread.interrupt() giống Thread.stop().”** Sai. Interrupt là yêu cầu hợp tác; Thread.stop cưỡng bức dừng nguy hiểm và đã bị deprecated.

**“InterruptedException không quan trọng nên có thể nuốt.”** Sai. Nuốt exception rồi tiếp tục làm việc thường làm vô hiệu hóa hủy và gây nghẽn pool.

**“Thread.interrupted() chỉ đọc cờ, không đổi gì.”** Sai. Nó **đọc và xóa** interrupt flag của thread hiện tại.

**“Thread.currentThread().isInterrupted() cũng xóa cờ.”** Sai. Nó chỉ quan sát trạng thái.

**“get(timeout) hết hạn sẽ tự gọi cancel.”** Sai. Timeout chỉ giới hạn thời gian đợi; muốn cố dừng task cần hành động riêng.

**“CompletableFuture.orTimeout tự ngắt HTTP client/JDBC đang chặn.”** Sai. Nó điều khiển completion của future, không phải một cơ chế hủy mọi nguồn công việc bên dưới.

**“@Async trả CompletableFuture thì cancel(true) tương đương cancel FutureTask.”** Không thể giả định. Cần kiểm tra implementation và truyền cancellation token/deadline phù hợp.

**“Future canceled nghĩa là chưa commit side effect.”** Sai. Task có thể đã ghi DB, gửi email hoặc gọi dịch vụ ngoài trước khi bị hủy.

**“Có thể tự interrupt shared worker qua tên thread.”** Nguy hiểm. Worker có thể đang chạy task khác do thread pool tái sử dụng.

**“shutdownNow chắc chắn dừng mọi task tức thì.”** Sai. Đây là best-effort interruption, không ép task thiếu hợp tác ngừng vật lý.

**“Worker finally chắc chắn chạy khi hủy queued task.”** Sai. Nếu body chưa chạy, finally trong body không có cơ hội được thực thi.

**“HTTP client disconnect tự hủy job đã gửi qua executor.”** Không mặc nhiên. Job cần cancellation contract riêng.

## 22. Bài tập tự kiểm tra

**Bài 1.** Một Callable đang Thread.sleep(10_000), caller gọi cancel(true) trên FutureTask. Điều gì có khả năng xảy ra?

**Đáp án:** Future có thể chuyển thành cancelled, Thread.sleep nhận interrupt và ném InterruptedException; Callable cần dừng/cleanup hợp tác. Không khẳng định mọi API I/O khác cũng có phản ứng y hệt.

**Bài 2.** Future.isDone() và Future.isCancelled() đều true nhưng metrics CPU của worker vẫn tăng. Có mâu thuẫn không?

**Đáp án:** Không. Future có thể đã bị hủy về trạng thái, còn task chưa ngừng vì không kiểm tra ngắt hoặc không phản ứng.

**Bài 3.** Task đã nằm trong queue, chưa bắt đầu. cancel(false) có thể thành công không?

**Đáp án:** Có. Không cần interrupt một thread đang chạy chính task đó; queued task có thể bị đánh dấu cancelled để body không chạy.

**Bài 4.** Tại sao catch(InterruptedException) nên trả lại interrupt flag khi Runnable không thể propagate exception?

**Đáp án:** Nhiều API xóa cờ khi ném InterruptedException. Khôi phục flag bảo toàn tín hiệu ngắt cho tầng có thể quan sát nó, đồng thời body nên thoát có chủ đích.

**Bài 5.** Một CompletableFuture được tạo bằng supplyAsync đang chờ latch, gọi cf.cancel(true). Có chắc latch.await ném InterruptedException không?

**Đáp án:** Không. CompletableFuture chuẩn không dùng mayInterruptIfRunning để interrupt supplier. Muốn dừng chờ, phải có tín hiệu hoặc hủy nguồn khác.

**Bài 6.** Caller gọi Future.get(1, SECONDS) và bắt TimeoutException, nhưng không gọi cancel. Worker có tự dừng không?

**Đáp án:** Không được bảo đảm. Timeout ở get chỉ dừng chờ của caller.

**Bài 7.** Một tác vụ đã gửi yêu cầu thanh toán rồi bị cancel. Có được ghi trạng thái “chắc chắn chưa thanh toán” không?

**Đáp án:** Không. Phải kiểm tra kết quả ở hệ thống thanh toán, dùng idempotency/compensation theo hợp đồng nghiệp vụ.

**Bài 8.** Vì sao cần finished latch riêng sau cancel(true)?

**Đáp án:** Vì Future.isDone/isCancelled không chứng minh code cuối cùng/finally của worker đã chạy. Tín hiệu riêng cho phép xác minh hoàn tất thực thi hoặc cleanup.

**Bài 9.** Có nên dùng Thread.interrupted() trong mọi điều kiện vòng lặp dài thay cho isInterrupted()?

**Đáp án:** Không mặc nhiên. Thread.interrupted() xóa cờ, dễ làm tầng sau bỏ lỡ tín hiệu. isInterrupted() quan sát mà không xóa.

**Bài 10.** Spring @Async void có cung cấp Future cho caller để gọi cancel(true) không?

**Đáp án:** Không. Muốn hủy phải thiết kế job handle, token, deadline hoặc cơ chế quản lý công việc khác.

**Bài 11.** shutdown() và shutdownNow() khác nhau như thế nào?

**Đáp án:** shutdown không nhận task mới và cho phép task đã nhận tiếp tục theo hợp đồng; shutdownNow cố ngắt task đang chạy và ngăn task chờ bắt đầu, nhưng vẫn là best effort.

**Bài 12.** Một FutureTask đang chạy nhận cancel(false), sau đó Callable vẫn ghi database. Đây có phải lỗi của Java không?

**Đáp án:** Không. cancel(false) không yêu cầu interrupt worker; Future có thể đã canceled nhưng execution vẫn chạy. Thiết kế ứng dụng phải xử lý side effects và quyền hủy.

## 23. Checklist để triển khai hủy task an toàn

- [ ] Xác định Future implementation thực tế: **FutureTask, CompletableFuture hoặc wrapper framework**.
- [ ] Phân biệt **Future cancelled**, **execution stopped** và **cleanup complete**.
- [ ] Biết rõ **cancel(true)** có phát yêu cầu interrupt tới worker hay không trong implementation được dùng.
- [ ] Với task CPU dài: đặt **interrupt/cancel-token checkpoints** ở vị trí dừng an toàn.
- [ ] Với blocking operations: dùng API có **timeout/cancellation** được hỗ trợ, không tin chỉ interrupt.
- [ ] Khi bắt InterruptedException: **propagate hoặc khôi phục cờ và thoát**, không nuốt tín hiệu.
- [ ] Dùng **finally/try-with-resources** để cleanup resource đã được task sở hữu.
- [ ] Giải quyết resource được cấp phát **trước khi task bắt đầu**, vì queued task hủy có thể không chạy body/finally.
- [ ] Không tự interrupt worker của shared Spring thread pool ngoài hợp đồng task.
- [ ] Đặt **timeout tổng** và timeout riêng cho HTTP/DB/socket phù hợp.
- [ ] Với CompletableFuture, tách cancellation của **completion** khỏi cancellation của **computation**.
- [ ] Kiểm soát concurrency/rejection/queue để không giữ công việc quá deadline.
- [ ] Tạo trạng thái job **CANCEL_REQUESTED** khác **CANCELLED/CLEANED** nếu cần quan sát chính xác.
- [ ] Xác minh DB/external side effects, dùng idempotency và compensation khi cần.
- [ ] Test bằng **CountDownLatch** và Future.get(timeout), không chỉ sleep.
- [ ] Trong integration test Spring, xác định @Async proxy và executor đúng; kiểm tra hành vi cancel của handle thật.

## Kết luận

**Future.cancel(true) là lời yêu cầu hủy, không phải lệnh cưỡng bức dừng Java thread.** Với FutureTask do ExecutorService.submit thường tạo ra, phương thức có thể chuyển Future sang cancelled và cố interrupt worker đang thực thi; task muốn dừng nhanh phải **hợp tác** bằng việc phản ứng với InterruptedException, kiểm tra cờ interrupt hoặc cancellation token tại checkpoint an toàn, rồi cleanup. Với **CompletableFuture** chuẩn, **cancel(true) không interrupt computation** mà đánh dấu một exceptional completion bằng CancellationException.

Trong Spring, đừng chỉ nhìn return type Future/CompletableFuture rồi giả định khả năng cancel. Xác định executor, wrapper, proxy và hợp đồng ứng dụng; tách timeout chờ, yêu cầu ngừng, kết thúc vật lý và trạng thái side effect. Thiết kế tốt phải trả lời được **công việc đã bị yêu cầu hủy chưa, nó có thực sự dừng chưa và tài nguyên/đơn hàng liên quan đã ở trạng thái nhất quán chưa**.

**Tài liệu tham khảo chính thức:**

- Java SE 17 [Future API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html).
- Java SE 17 [FutureTask API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/FutureTask.html).
- Java SE 17 [Thread.interrupt, interrupted và isInterrupted](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html).
- Java SE 17 [ExecutorService shutdown, submit, cancel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html).
- Java SE 17 [CompletableFuture cancel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html).
- Spring Framework [Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html).
