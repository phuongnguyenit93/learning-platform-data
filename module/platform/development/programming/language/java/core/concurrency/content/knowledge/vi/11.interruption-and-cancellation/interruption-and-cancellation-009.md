# `shutdown()`, `shutdownNow()` và `awaitTermination()` trong Java

## 1. Vì sao cần quản lý vòng đời ExecutorService?

Trong Java Concurrency, `ExecutorService` giúp ứng dụng nộp tác vụ thay vì tự tạo và quản lý mọi `Thread`. Ví dụ:

```java
ExecutorService executor = Executors.newFixedThreadPool(4);
executor.submit(() -> process());
```

Đây là đoạn minh họa, cần import các lớp trong `java.util.concurrent` và định nghĩa `process()`. Một executor thường **giữ các worker thread tồn tại** để xử lý nhiều tác vụ. Nếu nộp xong rồi bỏ mặc, ứng dụng có thể không thoát như mong đợi, không biết công việc đã xong chưa, hoặc bị mất dữ liệu trong lúc dừng.

Ba API cốt lõi cho vòng đời là:

- **`shutdown()`:** ngừng nhận tác vụ mới, cho những tác vụ **đã nộp** cơ hội hoàn thành.
- **`shutdownNow()`:** cố gắng dừng các tác vụ đang thực thi (thường bằng interrupt), không bắt đầu xử lý những tác vụ còn chờ, và trả về danh sách tác vụ đang chờ chưa được thực thi.
- **`awaitTermination(timeout, unit)`:** **chờ** executor kết thúc trong thời hạn cho phép; tự nó **không gửi yêu cầu shutdown**.

Điểm dễ nhầm nhất: **“đã gọi shutdown” không có nghĩa “mọi thread đã dừng”**. Phải phân biệt yêu cầu đóng, yêu cầu hủy và sự kiện đã kết thúc thật.

Bài này tập trung **Java Concurrency nói chung**, dùng `ExecutorService` và các primitive thuộc JDK. Không phụ thuộc framework.

## 2. Mô hình vòng đời dễ hiểu

Với một executor đang chạy:

```text
                  nhận submit/execute
                         |
                         v
                    RUNNING
                       |
         shutdown()    |    shutdownNow()
             |         |         |
             v                   v
    không nhận task mới     cố ngắt task đang chạy,
    đã nộp thì xử lý        ngừng xử lý task đang chờ
             |                   |
             +---------+---------+
                       |
      các worker kết thúc, không còn task phải chạy
                       |
                       v
                   TERMINATED
```

Đây là mô hình khái niệm. `ThreadPoolExecutor` có các trạng thái nội bộ chi tiết hơn, nhưng **không nên dựa vào state machine nội bộ** để dùng API. Với `ExecutorService`, các mốc quan sát qua giao diện là:

- `isShutdown()`: đã có yêu cầu shutdown. Nó có thể trả `true` ngay khi executor vẫn có worker đang chạy.
- `isTerminated()`: executor đã hoàn toàn kết thúc sau shutdown.
- `awaitTermination(...)`: đợi mốc terminated hoặc hết thời gian, có thể bị interrupt.

Tính chất cần nhớ:

```text
isShutdown() == true
       không suy ra
isTerminated() == true
```

Một task mất hàng phút hoặc không hợp tác với interrupt vẫn có thể giữ executor ở trạng thái chưa terminated rất lâu sau khi yêu cầu shutdown.

## 3. So sánh trực tiếp ba API

| API | Nhận task mới? | Task đã chạy | Task đang chờ trong queue | Có chờ trong caller? | Giá trị trả về |
| --- | --- | --- | --- | --- | --- |
| `shutdown()` | Dừng nhận mới | Được tiếp tục thực hiện bình thường | Được xử lý theo chính sách executor | Không | `void` |
| `shutdownNow()` | Dừng nhận mới | Cố gắng hủy bằng interrupt hoặc cơ chế thích hợp; **không bảo đảm dừng** | Không tiếp tục xử lý tác vụ chưa bắt đầu; được trả về trong danh sách pending theo hợp đồng | Không đợi toàn bộ task dừng | `List<Runnable>` |
| `awaitTermination(t, unit)` | Không thay đổi việc nhận task | Không tự hủy | Không tự dọn queue | **Có**, chờ tối đa thời hạn | `boolean`, hoặc `InterruptedException` |

**Lưu ý về phạm vi:** một `ExecutorService` có nhiều implementation. Với `ThreadPoolExecutor` thông thường, `shutdownNow()` cố interrupt worker và lấy các tác vụ chưa chạy ra khỏi queue. Việc interrupt có phát huy tác dụng hay không phụ thuộc vào **task có hợp tác hay không**, và một task đang nằm ở ranh giới “queued/running” có thể cạnh tranh với yêu cầu shutdown.

**`shutdownNow()` không có nghĩa “kill thread”.** Java không bảo đảm cưỡng bức kết thúc một task tùy ý khi gọi phương thức này.

## 4. `shutdown()`: đóng có trật tự (graceful shutdown)

Hãy dùng `shutdown()` khi muốn:

1. Không cho caller nộp thêm tác vụ.
2. Để các tác vụ đã nhận vào executor tiếp tục được hoàn thành.
3. Có thể đợi sự kiện hoàn tất ở bước sau bằng `awaitTermination()`.

`shutdown()` trả về **ngay sau khi khởi tạo quy trình đóng**, không đợi mọi worker hoàn thành.

Nếu caller tiếp tục gọi `execute()` hoặc `submit()` sau khi executor đã shutdown, executor sẽ **từ chối** tác vụ mới, thường bằng `RejectedExecutionException` tùy implementation và rejection policy. Đừng nghĩ `shutdown()` chỉ là một cờ “sau này sẽ dừng nhận”, còn có thể tiếp tục submit bình thường.

### Ví dụ 1: xử lý hết hai task đã nộp

Tạo tệp `GracefulShutdownDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class GracefulShutdownDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor();

        executor.execute(() -> System.out.println("task A"));
        executor.execute(() -> System.out.println("task B"));

        executor.shutdown();
        boolean terminated = executor.awaitTermination(10, TimeUnit.SECONDS);

        System.out.println("shutdown=" + executor.isShutdown());
        System.out.println("terminated=" + terminated);
    }
}
```

Biên dịch/chạy trên JDK 17+:

```bash
javac GracefulShutdownDemo.java
java GracefulShutdownDemo
```

Kết quả điển hình khi hai task hoàn thành trước thời hạn:

```text
task A
task B
shutdown=true
terminated=true
```

Vì executor có một worker, hai task được nộp lần lượt và chạy theo thứ tự trong FIFO queue của single-thread executor thông thường. `shutdown()` không hủy task A hoặc B. `awaitTermination()` chờ tối đa mười giây rồi trả về `true` nếu đã terminated.

Nếu máy bị trì hoãn bất thường đến mức hết thời hạn, dòng cuối có thể là `terminated=false`, **không có nghĩa task chắc chắn thất bại**: nó chỉ nói executor chưa đạt trạng thái terminated trong thời gian chờ. Ví dụ thời hạn mười giây là giá trị minh họa, không phải SLA cho mọi môi trường.

### Vì sao `shutdown()` không đủ để biết kết quả nghiệp vụ?

`shutdown()` chỉ yêu cầu lifecycle transition. Một `Runnable` đã được chạy có thể thất bại; một `Callable` trả giá trị có thể cần kiểm tra qua `Future.get()`. **Đợi executor terminated** và **kiểm tra outcome của từng task** là hai nhu cầu khác nhau.

Nếu ứng dụng phải biết từng task thành công hay thất bại, hãy lưu `Future`, truyền outcome qua một kênh, hoặc dùng cơ chế kết quả phù hợp. Đừng coi `isTerminated()==true` là tất cả nghiệp vụ đã thành công.

## 5. `awaitTermination()` chỉ quan sát, không tự shutdown

Chữ ký:

```java
boolean awaitTermination(long timeout, TimeUnit unit)
        throws InterruptedException;
```

Đây là chữ ký API rút gọn. Phương thức đợi cho đến khi **executor đã terminated**, **hết thời gian** hoặc **thread đang chờ bị interrupt**:

- Trả `true`: executor đã đạt trạng thái terminated.
- Trả `false`: hết thời hạn mà trạng thái terminated chưa đạt.
- Ném `InterruptedException`: thread gọi phương thức bị interrupt trong lúc đợi; cần propagate hoặc xử lý theo chính sách hủy.

Gọi `awaitTermination()` khi executor còn nhận task và không có ai gọi shutdown thường chỉ khiến caller đợi đến timeout: bản thân phương thức **không đóng executor**. Một thread khác vẫn có thể gọi shutdown trong lúc caller đang đợi, và khi executor kết thúc thì việc đợi mới có thể trả `true`.

### Ví dụ 2: timeout là false, sau khi nhả task là true

Dùng latch để giữ task chưa thể kết thúc trong lúc main thử timeout. Điều này chứng minh ngữ nghĩa thời hạn mà không dựa vào việc ngủ ngẫu nhiên.

Tạo tệp `AwaitTerminationDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class AwaitTerminationDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        executor.execute(() -> {
            entered.countDown();
            try {
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        entered.await();
        executor.shutdown();

        boolean first = executor.awaitTermination(
                50, TimeUnit.MILLISECONDS);
        System.out.println("before release=" + first);

        release.countDown();

        boolean second = executor.awaitTermination(
                10, TimeUnit.SECONDS);
        System.out.println("after release=" + second);
    }
}
```

```bash
javac AwaitTerminationDemo.java
java AwaitTerminationDemo
```

Kết quả khi không có interrupt ngoài ý muốn và task được lập lịch hoàn tất trong thời hạn thứ hai:

```text
before release=false
after release=true
```

`entered` đảm bảo task đã vào runnable. Vì `release` chưa được mở, task chưa thể hoàn tất trong lần chờ thứ nhất: `false` có ý nghĩa **đã hết thời gian chờ**. Main mở `release`, task kết thúc và executor có thể chuyển tới terminated; lần chờ thứ hai thường trả `true`.

Không nên xem một lần `awaitTermination(10, SECONDS)` là đảm bảo thời gian tuyệt đối: hệ điều hành có thể trì hoãn runnable, nên code production phải xử lý cả `false`.

### Phải làm gì khi `awaitTermination` trả `false`?

Tùy chính sách:

- Chờ thêm nếu độ trễ cho phép.
- Gọi `shutdownNow()` để yêu cầu cancel task còn chạy và lấy lại những task chưa bắt đầu.
- Ghi log/đánh dấu shutdown chưa hoàn tất và kích hoạt cảnh báo hoặc quá trình cleanup khác.
- Không được giả định rằng `false` có nghĩa thread đã kết thúc hoặc resource đã được trả lại.

Nếu một worker không thể hủy hợp tác, việc chờ lại có thể tiếp tục timeout. Không có phương thức nào trong ba API bảo đảm cưỡng bức hoàn tất một task bất kỳ.

## 6. `shutdownNow()`: cố hủy đang chạy và trả về pending tasks

Phương thức:

```java
List<Runnable> notStarted = executor.shutdownNow();
```

Nó **cố gắng**:

1. Ngừng chấp nhận task mới.
2. Đưa executor vào quy trình dừng ngay.
3. Cố gửi `interrupt()` đến các worker đang thực thi task (với thread pool thông thường).
4. Không bắt đầu những tác vụ còn ở queue; trả về danh sách `Runnable` của các task đang chờ chưa thực thi.

Từ **“Now”** ở đây là *yêu cầu ngay*, **không phải kết thúc hoàn toàn ngay**.

Cần hiểu danh sách trả về:

- Nó đại diện cho các task **đang chờ chưa bắt đầu** mà executor trả về tại lúc dừng.
- Nó **không chứa toàn bộ task đang chạy**; task đang chạy có thể cần tự phản hồi interrupt.
- Với `submit()`, executor có thể bọc `Callable`/`Runnable` trong `FutureTask` hoặc một wrapper khác. `List<Runnable>` không nhất thiết chứa đúng object task ban đầu bạn đã truyền vào.
- Không thể chỉ dựa vào danh sách đó để suy ra đã xử lý thành công bao nhiêu task trong toàn hệ thống. Task có thể đang ở ranh giới lấy khỏi queue, bắt đầu chạy hoặc đang cleanup.

Nếu ứng dụng muốn retry pending tasks, phải xác định **task có idempotent không, có còn hợp lệ không và cách tránh chạy hai lần**. Đừng gửi lại mọi `Runnable` một cách mù quáng.

### Ví dụ 3: một task đang chạy bị interrupt, một task pending được trả về

Tạo tệp `ShutdownNowDemo.java`:

```java
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class ShutdownNowDemo {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor executor = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1));

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch exited = new CountDownLatch(1);
        AtomicBoolean sawInterrupt = new AtomicBoolean(false);

        executor.execute(() -> {
            started.countDown();
            try {
                new CountDownLatch(1).await(); // Chờ đến khi bị interrupt.
            } catch (InterruptedException e) {
                sawInterrupt.set(true);
                Thread.currentThread().interrupt();
            } finally {
                exited.countDown();
            }
        });

        started.await();
        executor.execute(() ->
                System.out.println("queued task should not run"));

        List<Runnable> pending = executor.shutdownNow();
        exited.await();

        boolean terminated =
                executor.awaitTermination(10, TimeUnit.SECONDS);

        System.out.println("pending=" + pending.size());
        System.out.println("interrupt observed=" + sawInterrupt.get());
        System.out.println("terminated=" + terminated);
    }
}
```

```bash
javac ShutdownNowDemo.java
java ShutdownNowDemo
```

Kết quả khi worker phản hồi interrupt và hoàn tất trong thời hạn:

```text
pending=1
interrupt observed=true
terminated=true
```

**Tại sao kết quả có thể dự đoán:**

- Pool có đúng một worker và queue capacity 1.
- Main đợi `started` nên biết task thứ nhất đã chạy; task này block ở một latch **không bao giờ được mở**.
- Task thứ hai chỉ có thể nằm ở queue vì worker duy nhất chưa thoát.
- `shutdownNow()` yêu cầu interrupt worker. `await()` của task thứ nhất có thể bị ngắt, nên catch ghi nhận interrupt rồi rời.
- Task thứ hai bị lấy ra khỏi queue và được trả trong `pending`, không chạy.
- Main đợi `exited` rồi chờ executor terminated trước khi in kết quả.

Ví dụ này dùng latch không bao giờ được mở **chỉ để minh họa shutdownNow và interrupt**. Task thực tế nên có cả đường hủy, timeout và cleanup; đừng dùng đợi vô hạn mà không có phương án khôi phục.

## 7. `shutdownNow()` không bảo đảm dừng được task bỏ qua interrupt

Interrupt trong Java là một **tín hiệu hợp tác**. Nhiều thao tác chặn như `Thread.sleep()`, `BlockingQueue.take()`, `Object.wait()`, `Condition.await()` hay `Lock.lockInterruptibly()` có thể ném `InterruptedException`. Nhưng nếu một task chỉ làm việc CPU và không kiểm tra trạng thái interrupt, nó có thể tiếp tục chạy sau `shutdownNow()`.

Ví dụ sau **cố tình viết task không hợp tác** để minh họa giới hạn này. Không dùng kiểu busy-spin đó trong ứng dụng production.

Tạo `UncooperativeTaskDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class UncooperativeTaskDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        AtomicBoolean keepWorking = new AtomicBoolean(true);
        CountDownLatch started = new CountDownLatch(1);

        executor.execute(() -> {
            started.countDown();
            while (keepWorking.get()) {
                Thread.onSpinWait(); // Cố tình không kiểm tra interrupt.
            }
        });

        started.await();
        executor.shutdownNow();

        boolean first = executor.awaitTermination(
                50, TimeUnit.MILLISECONDS);
        System.out.println("terminated while task ignores interrupt=" + first);

        keepWorking.set(false);

        boolean second = executor.awaitTermination(
                10, TimeUnit.SECONDS);
        System.out.println("terminated after cooperative stop=" + second);
    }
}
```

```bash
javac UncooperativeTaskDemo.java
java UncooperativeTaskDemo
```

Kết quả nếu task được lập lịch kết thúc trong thời hạn thứ hai:

```text
terminated while task ignores interrupt=false
terminated after cooperative stop=true
```

Task không đọc cờ interrupt. Do đó `shutdownNow()` **không thể tự chấm dứt** vòng lặp. Chỉ khi main đặt `keepWorking=false`, worker mới thoát và executor có thể terminated.

Trong code thật, sử dụng cơ chế chờ/block phù hợp hoặc kiểm tra interrupt/token hủy tại những điểm an toàn. `Thread.onSpinWait()` chỉ là gợi ý tối ưu cho vòng spin; nó **không kiểm tra hủy, không ngủ và không nhả khóa**.

Nếu task bị kẹt trong I/O hoặc thư viện không hỗ trợ interrupt, `shutdownNow()` cũng có thể không kết thúc tác vụ sớm. Một số tài nguyên cần biện pháp khác như đóng socket/stream, deadline, timeout hoặc API cancellation phù hợp.

## 8. Mẫu đóng hai giai đoạn: graceful rồi fallback

Một chiến lược phổ biến:

1. **Gửi `shutdown()`** để ngừng nhận việc mới.
2. **Đợi có giới hạn** bằng `awaitTermination()`.
3. Nếu vẫn chưa kết thúc, **gọi `shutdownNow()`** để yêu cầu hủy các tác vụ còn chạy và lấy danh sách pending nếu cần.
4. **Đợi có giới hạn lần nữa**.
5. Nếu vẫn không kết thúc, báo trạng thái **shutdown chưa hoàn tất** thay vì giả định mọi thread đã dừng.
6. Nếu thread gọi phương thức shutdown bị interrupt trong lúc chờ, gửi yêu cầu `shutdownNow()` và **khôi phục trạng thái interrupt** hoặc propagate exception theo hợp đồng.

Mẫu Java 17+:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;

public final class ExecutorShutdown {
    private ExecutorShutdown() {}

    public static void stop(ExecutorService executor) {
        executor.shutdown();
        try {
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
                if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                    System.err.println("executor did not terminate");
                }
            }
        } catch (InterruptedException e) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
```

Đây là **lớp tiện ích hoàn chỉnh có thể biên dịch**, nhưng không có `main`, nên không chạy trực tiếp bằng `java ExecutorShutdown`. Nó minh họa mẫu shutdown hai giai đoạn; hai thời hạn năm giây chỉ là **giá trị ví dụ**, cần chọn phù hợp với SLA và yêu cầu cleanup của hệ thống.

**Không nhầm:** nếu `awaitTermination` thứ hai trả `false`, executor vẫn có thể còn thread sống. Hàm log lỗi để caller biết tình trạng, không thể ép thread dừng. Trong ứng dụng production nên truyền trạng thái kết thúc lên caller để nó đưa ra quyết định tiếp theo.

### Mẫu hai giai đoạn có cần xem danh sách pending không?

Nếu pending task là những tác vụ quan trọng (ghi hóa đơn, thanh toán, lưu dữ liệu), không được mặc định rằng có thể **bỏ chúng** sau `shutdownNow()`. Có thể phải persist, retry có kiểm soát hoặc báo lỗi cho chủ sở hữu. Ngược lại, với task thăm dò đã lỗi thời, có thể chấp nhận hủy.

Chính sách xử lý phần việc chưa chạy là **quyết định nghiệp vụ**, không phải một lựa chọn `ExecutorService` tự làm giúp.

## 9. `InterruptedException` trong lúc đợi termination

`awaitTermination(timeout, unit)` là thao tác có thể bị interrupt. Khi thread đang chờ bị ngắt, phương thức ném `InterruptedException`.

Có hai chiến lược hợp lệ tùy tầng API:

**Truyền tiếp:**

```java
void stopAndWait(ExecutorService executor)
        throws InterruptedException {
    executor.shutdown();
    if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
        executor.shutdownNow();
    }
}
```

Đây là đoạn minh họa. Việc propagate cho tầng gọi quyết định có thử thêm, đóng tài nguyên khác hay báo lỗi.

**Không thể propagate thì khôi phục cờ:**

```java
try {
    executor.shutdown();
    executor.awaitTermination(5, TimeUnit.SECONDS);
} catch (InterruptedException e) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
}
```

Đây cũng là đoạn minh họa. `Thread.currentThread().interrupt()` khôi phục trạng thái ngắt của thread **đang gọi shutdown**, vì một thao tác chặn thường xóa cờ khi ném `InterruptedException`.

Không “nuốt” interrupt bằng `catch (InterruptedException ignored) {}` rồi tiếp tục đợi vô hạn, nếu hệ thống cần khả năng hủy hoặc shutdown responsive.

Một lưu ý: `Thread.currentThread().isInterrupted()` đọc mà không xóa cờ; `Thread.interrupted()` (static) đọc và **xóa** cờ. Sử dụng có chủ đích, tránh làm mất tín hiệu hủy.

## 10. Task phải hợp tác với interrupt ra sao?

Trong code chạy bởi executor, điều quan trọng không chỉ là caller gọi `shutdownNow()` mà **task có đáp ứng yêu cầu hủy**.

### Task chặn ở API interruptible

Ví dụ `BlockingQueue.take()`:

```java
try {
    while (!Thread.currentThread().isInterrupted()) {
        Work item = queue.take();
        process(item);
    }
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
} finally {
    cleanup();
}
```

Đây là đoạn minh họa, với `Work`, `queue`, `process` và `cleanup` do ứng dụng định nghĩa. Khi shutdownNow gửi interrupt, `take()` có thể ném `InterruptedException`; task thoát vòng, cleanup trong finally và khôi phục cờ.

**Không nhất thiết phải khôi phục rồi lại lặp tiếp.** Trong runnable, một đường catch interrupt nên kết thúc tác vụ hoặc chuyển thành kết quả hủy theo hợp đồng. Nếu chỉ khôi phục rồi trở về một vòng tiếp tục gọi các API chặn, có thể tạo vòng exception vô ích.

### Task CPU-bound

Nếu task tính toán lâu, không gọi API chặn, cần kiểm tra tín hiệu trong vòng lặp:

```java
for (int i = 0; i < batches.size(); i++) {
    if (Thread.currentThread().isInterrupted()) {
        return;
    }
    processBatch(batches.get(i));
}
```

Đây là đoạn minh họa. Kiểm tra interrupt ở điểm phù hợp; phải chắc rằng việc thoát giữa chừng **không phá invariant** hoặc để resource đang giữ bị rò rỉ.

### Task đã bắt đầu thay đổi nhiều field

Interrupt không rollback phép gán đã thực hiện. Nếu task dừng giữa một giao dịch trong bộ nhớ hoặc I/O nhiều bước, dữ liệu có thể không nhất quán. Cần chia công việc thành **các đơn vị commit hợp lệ**, hoàn thành/rollback một đơn vị trước khi phản hồi hủy.

## 11. `Future.cancel(true)` khác `shutdownNow()` ở đâu?

Cả hai có thể sử dụng interrupt, nhưng phạm vi khác nhau:

- `Future.cancel(true)` yêu cầu hủy **một task cụ thể**; khi task đang chạy, executor có thể cố interrupt thread thực hiện task đó theo hợp đồng tương ứng.
- `shutdownNow()` yêu cầu dừng **cả executor**, từ chối nộp mới, xử lý các worker đang chạy và trả về pending tasks.
- `Future.cancel(false)` không yêu cầu interrupt task đang chạy. Một Future bị đánh dấu canceled không chứng minh worker đã xong cleanup.
- `shutdown()` khác cả hai: không yêu cầu hủy những task đã nhận.

Ví dụ nếu có ba request độc lập trên cùng pool, chỉ request B hết hạn thì `futureB.cancel(true)` có thể phù hợp hơn shutdown toàn bộ pool. Nếu ứng dụng đóng và không còn chấp nhận công việc, cần xử lý lifecycle ở cấp executor.

Sau khi `Future` bị cancel, gọi `future.get()` thường ném `CancellationException`. Điều đó không phải một cơ chế đợi chắc chắn cho cleanup của task đã chạy. Nếu cần biết tài nguyên thật sự được nhả, dùng một tín hiệu hoàn tất riêng hoặc quản lý vòng đời ở tầng task/executor.

## 12. Nộp task sau shutdown và RejectedExecutionException

Ngay sau khi executor đã shutdown, yêu cầu nộp mới không còn được chấp nhận.

Ví dụ dùng `execute()`:

```java
ExecutorService executor = Executors.newSingleThreadExecutor();
executor.shutdown();

try {
    executor.execute(() -> System.out.println("not accepted"));
} catch (RejectedExecutionException e) {
    System.out.println("rejected");
}
```

Đây là **đoạn minh họa** cần import `ExecutorService`, `Executors` và `RejectedExecutionException`; với executor tiêu chuẩn, output là:

```text
rejected
```

Nếu dùng `ThreadPoolExecutor` với một `RejectedExecutionHandler` tùy biến, tác động của rejection policy có thể khác, ví dụ chạy task trên caller, loại bỏ task hoặc ném exception. Đừng viết code phụ thuộc mù quáng vào việc **mọi implementation đều ném exception** nếu bạn cho phép cấu hình handler khác.

Lỗi concurrency thường gặp khi một thread bắt đầu shutdown trong lúc thread khác tiếp tục submit: không có gì bảo đảm “kiểm tra `!isShutdown()` rồi submit” là atomic, bởi executor có thể shutdown giữa hai thao tác. Caller cần xử lý rejection như một khả năng bình thường của lifecycle transition.

## 13. `isShutdown()` và `isTerminated()` là quan sát trạng thái, không là barrier cho nghiệp vụ

`isShutdown()` cho biết một yêu cầu shutdown đã xảy ra. Nó không nói rằng queue trống, không nói rằng mọi worker đã exit, và không nói rằng file/network/database đã được flush hoàn tất.

`isTerminated()` cho biết executor đã terminated; nhưng vẫn không nói **mọi task đã thành công**. Một worker có thể ném exception rồi kết thúc, executor vẫn hoàn tất lifecycle.

Một mẫu sai:

```java
executor.shutdown();
if (executor.isShutdown()) {
    saveResults(); // Sai nếu assume task đã hoàn tất.
}
```

Đây là đoạn phản ví dụ. Khi cần kết quả chắc chắn, lưu `Future` và chờ `get()`, dùng `awaitTermination()` theo chính sách, hoặc cơ chế kết quả/bàn giao khác.

**Memory visibility:** quan hệ happens-before được đặc tả rõ cho việc nộp task vào executor và việc nhận kết quả qua `Future.get()`. Nếu task ghi một kết quả cho caller cần đọc, `Future.get()` là cách rõ ràng để vừa biết outcome vừa có hợp đồng bộ nhớ phù hợp. Không nên dùng một cờ trạng thái lifecycle thay cho mọi giao thức chia sẻ mutable state.

## 14. Timeout, deadline và shutdown budget

Một timeout trong `awaitTermination` là **thời hạn chờ tối đa của lời gọi đó**, không phải lời hứa task sẽ thực hiện xong đúng lúc. Nếu gọi:

```java
executor.shutdown();
if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
    executor.shutdownNow();
    executor.awaitTermination(5, TimeUnit.SECONDS);
}
```

thì tổng thời gian chờ theo hai lời gọi có thể tới **khoảng mười giây** (cộng overhead). Nếu hệ thống có deadline shutdown tổng thể, cần lập ngân sách thời gian cho các pha và các tài nguyên khác; đừng lặng lẽ cộng thời hạn nhiều lần vượt yêu cầu.

Ví dụ ý tưởng:

```text
Shutdown deadline tổng: 8 giây
0s         5s               8s
|----------|----------------|
 graceful      cố hủy và cleanup
```

Code production có thể tính thời gian còn lại bằng `System.nanoTime()` (để đo khoảng thời gian đơn điệu) rồi truyền phần còn lại cho các lệnh chờ. Không dựa vào `System.currentTimeMillis()` để đo duration nếu hệ thống có thể chỉnh đồng hồ.

Ngay cả khi deadline hết, **task có thể vẫn chạy**. Phải quyết định chính sách ứng dụng: báo lỗi, ghi log/metric, tiếp tục cleanup không chặn, hoặc yêu cầu hệ thống quản lý process xử lý theo giới hạn. Ba phương thức `ExecutorService` không cung cấp lệnh “kill bất kỳ Java thread nào ngay lập tức”.

## 15. Xử lý các task pending sau shutdownNow

Danh sách `List<Runnable>` từ `shutdownNow()` không phải là một kết quả nghiệp vụ đầy đủ. Với `execute(runnable)`, danh sách có thể chứa chính task chưa bắt đầu; với `submit(...)`, các tác vụ có thể được bọc trong `RunnableFuture`/`FutureTask`.

Cần quyết định:

- **Discard:** chấp nhận hủy những task không còn cần.
- **Retry:** chỉ khi task còn hợp lệ và logic an toàn khi thử lại.
- **Persist:** lưu yêu cầu chưa thực thi ra kho bền vững nếu không được phép mất.
- **Fail request:** báo rõ cho caller thay vì để Future/chờ phản hồi treo vô hạn.
- **Reconcile:** nếu một task có thể đã bắt đầu, cần kiểm tra kết quả đã commit trước khi retry để tránh xử lý trùng.

Một queue trong bộ nhớ **không phải durable job queue**. Nếu process crash, danh sách pending có thể không còn. Nếu công việc quan trọng như thanh toán hoặc ghi sổ, cần idempotency, transaction, durable queue hoặc một giao thức recovery ở tầng tương ứng.

## 16. Khi nào `shutdown()` là đủ, khi nào cần `shutdownNow()`?

Chọn `shutdown()` nếu:

- Muốn **xử lý hết công việc đã nhận**.
- Task có thời lượng dự kiến phù hợp với thời hạn dừng.
- Hệ thống muốn graceful drain hơn là hủy ngay.
- Công việc không nên bị bỏ giữa chừng.

Chọn `shutdownNow()` khi:

- Không còn thời gian chờ graceful.
- Task còn chạy không còn cần thiết hoặc được thiết kế hỗ trợ cancel.
- Cần lấy lại những task còn queued để xử lý theo chính sách khác.
- Hệ thống ưu tiên giải phóng tài nguyên sớm nhưng chấp nhận bản chất best-effort.

Dùng `awaitTermination()` khi:

- Caller cần **biết executor đã dừng thật chưa**.
- Muốn triển khai deadline/graceful fallback.
- Cần đồng bộ vòng đời trước khi đóng các resource phụ thuộc vào worker.

Không nhất thiết lúc nào cũng gọi `shutdownNow()` ngay sau `shutdown()`. Nếu shutdownNow được gọi quá sớm, các task đang hoạt động có thể bị interrupt trước khi hoàn thành; điều đó đi ngược mục tiêu graceful.

## 17. Resource cleanup và thứ tự đóng

Executor thường không đứng một mình. Task có thể dùng database connection, file, socket, queue hoặc service khác. Thứ tự đóng sai có thể làm task thất bại ngay cả khi executor được dừng “đúng” về mặt thread lifecycle.

Một chuỗi thường hợp lý:

1. Ngừng **nhận yêu cầu mới** tại đầu vào của hệ thống.
2. Đảm bảo không còn producer mới nộp task vào executor.
3. Yêu cầu executor `shutdown()`.
4. Đợi graceful trong thời hạn.
5. Nếu cần, gọi `shutdownNow()` và đợi lại.
6. Sau khi worker ngừng dùng resource, đóng các resource liên quan.
7. Nếu một worker không dừng được, xử lý trạng thái không chắc chắn thay vì đóng bừa mọi thứ rồi tuyên bố đã hoàn tất.

Ví dụ, **đóng database connection pool trước khi task cuối kết thúc** có thể khiến task đang commit thất bại. Ngược lại, nếu task đang kẹt trong I/O, việc đóng resource có thể là một phần cần thiết của quy trình hủy — nhưng phải căn cứ vào hợp đồng của resource đó.

Không có thứ tự đóng duy nhất cho mọi hệ thống. Điều quan trọng là biết dependency và quyền sở hữu tài nguyên.

## 18. ScheduledExecutorService và các implementation đặc thù

`ScheduledExecutorService` mở rộng `ExecutorService` nên cũng có `shutdown()`, `shutdownNow()` và `awaitTermination()`. Nhưng task có lịch chạy trì hoãn hoặc lặp lại có thể chịu **chính sách shutdown riêng của implementation**.

Với `ScheduledThreadPoolExecutor`, có các lựa chọn như chính sách tiếp tục thực thi delayed tasks đã tồn tại hoặc không tiếp tục periodic tasks sau shutdown. Đừng giả định toàn bộ delayed/periodic task luôn có cùng hành vi như một queue FIFO của `ThreadPoolExecutor` thông thường.

Khi dùng scheduled executor, hãy xem rõ:

- Task đã lên lịch nhưng chưa đến hạn có được chạy sau `shutdown()` không?
- Periodic task có tiếp tục không?
- Future tương ứng sẽ ở trạng thái gì khi shutdown?
- Task chưa chạy được trả về dưới dạng nào khi `shutdownNow()`?

Lời giải tổng quát vẫn là **đọc hợp đồng của implementation và kiểm tra cancellation/termination theo yêu cầu**. `shutdown()` không có nghĩa mọi loại công việc đều lập tức ngừng.

## 19. Các lỗi thường gặp

### 19.1. Chỉ gọi `shutdown()` rồi nghĩ mọi worker đã dừng

Sai. `shutdown()` không chờ. Dùng `awaitTermination` nếu cần xác nhận vòng đời đã kết thúc.

### 19.2. Gọi `awaitTermination()` mà không shutdown

Nếu không có thread khác gọi shutdown, executor có thể tiếp tục hoạt động và lời gọi chỉ hết timeout. `awaitTermination` không chủ động ngừng nhận công việc.

### 19.3. Nghĩ `shutdownNow()` ép mọi task chết ngay

Sai. Nó thường gửi interrupt; task không hợp tác vẫn có thể chạy. Có thể phải xử lý I/O, interrupt và cleanup theo hợp đồng riêng.

### 19.4. Bỏ qua danh sách pending và làm mất công việc quan trọng

`shutdownNow()` trả các task chưa bắt đầu theo hợp đồng; phải quyết định discard/retry/persist, không mặc nhiên giả định chúng đã hoàn thành.

### 19.5. Gửi shutdownNow rồi không đợi hoặc không kiểm tra hậu quả

Có thể còn task đang cleanup và resource chưa được trả. Khi cần xác nhận, đợi termination có giới hạn và báo cáo nếu vẫn chưa xong.

### 19.6. Nuốt `InterruptedException` trong worker

Worker bị ngắt ở `sleep` hoặc `take` rồi catch rỗng và tiếp tục vòng lặp có thể làm `shutdownNow()` không có hiệu lực. Propagate hoặc khôi phục cờ và dừng tại điểm an toàn.

### 19.7. Chỉ kiểm tra `isShutdown()` trước khi submit

Có race: executor có thể shutdown giữa kiểm tra và submit. Cần xử lý rejection.

### 19.8. Cho rằng `isTerminated()` chứng minh mọi tác vụ thành công

Task có thể kết thúc bằng exception hoặc cancellation. Kiểm tra `Future`/outcome nghiệp vụ riêng.

### 19.9. Gọi shutdown bên trong một task rồi tự đợi executor terminated

Nếu chính task đang chạy đợi executor terminated, còn executor phải chờ task đó kết thúc mới terminated, có thể tạo **self-wait/deadlock** hoặc timeout. Việc shutdown và chờ nên do một coordinator bên ngoài vòng công việc cần kết thúc điều phối.

### 19.10. Đóng tài nguyên trước khi worker hoàn tất

Các task đã được nộp nhưng đang chạy có thể còn sử dụng resource. Thiết kế thứ tự đóng dựa trên dependency, không chỉ dựa trên thứ tự dòng code thuận tiện.

### 19.11. Dùng `Thread.sleep` để đoán task đã kết thúc

Lịch chạy thread không xác định. Sử dụng `Future.get`, `CountDownLatch`, `awaitTermination`, hoặc tín hiệu hoàn tất được thiết kế cho mục tiêu đó.

## 20. Câu hỏi tự kiểm tra

**Câu 1.** Đã gọi `shutdown()` thì một task đang chạy có bị interrupt ngay không?

**Trả lời:** Không. `shutdown()` yêu cầu đóng có trật tự; task đã nhận vào được phép tiếp tục.

**Câu 2.** `shutdown()` có đợi tất cả worker kết thúc không?

**Trả lời:** Không. Nó trả về sau khi khởi tạo shutdown. Dùng `awaitTermination` hoặc một cơ chế chờ kết quả phù hợp.

**Câu 3.** `awaitTermination(2, SECONDS)` trả `false` nghĩa là gì?

**Trả lời:** Executor chưa terminated trong thời hạn hai giây. Không suy ra mọi task thất bại hoặc executor đã dừng.

**Câu 4.** `shutdownNow()` trả `List<Runnable>` chứa các task đang chạy hay pending?

**Trả lời:** Các task đang chờ chưa được thực thi theo hợp đồng; task đang chạy được yêu cầu dừng best-effort chứ không phải tất cả nằm trong danh sách.

**Câu 5.** Task CPU-bound không đọc interrupt có chắc chắn dừng khi `shutdownNow()` không?

**Trả lời:** Không. Interrupt là tín hiệu hợp tác; task có thể tiếp tục chạy.

**Câu 6.** Khi một task bị hủy qua `Future.cancel(true)`, có thể dùng `future.get()` để chờ chắc chắn cleanup xong không?

**Trả lời:** Không. Future bị hủy có thể ném `CancellationException` trong khi code cleanup còn đang chạy. Cần cơ chế xác nhận cleanup riêng nếu bắt buộc.

**Câu 7.** Executor đã `isShutdown()==true` nhưng `isTerminated()==false` có mâu thuẫn không?

**Trả lời:** Không. Nó đã bắt đầu quy trình đóng nhưng còn task hoặc worker chưa kết thúc.

**Câu 8.** Tại sao chiến lược hai giai đoạn gọi `shutdown()` trước và chỉ dùng `shutdownNow()` nếu chờ quá lâu?

**Trả lời:** Để ưu tiên hoàn tất task đã nhận, nhưng vẫn có fallback yêu cầu hủy nếu vượt thời hạn graceful.

**Câu 9.** Hai producer cạnh tranh: thread A kiểm tra `!executor.isShutdown()`, thread B shutdown, thread A submit. Điều gì có thể xảy ra?

**Trả lời:** Submit có thể bị từ chối. Kiểm tra và submit không phải thao tác nguyên tử; xử lý rejection.

**Câu 10.** Nếu cần giữ các job chưa chạy cho lần khởi động sau, `shutdownNow()` và `List<Runnable>` đã đủ chưa?

**Trả lời:** Không. List tồn tại trong bộ nhớ của process, có thể chứa wrapper; cần xác định danh tính, trạng thái, idempotency và lưu bền vững nếu cần phục hồi qua crash.

**Câu 11.** Một task đã bắt đầu ghi hai trường quan hệ với nhau rồi nhận interrupt. Có được dừng giữa chừng không?

**Trả lời:** Không nếu làm vậy khiến invariant sai. Cần commit/rollback ở điểm an toàn trước khi thoát và giải phóng resource.

## 21. Tổng kết

**`shutdown()` = ngừng nhận mới, để các tác vụ đã nhận hoàn thành. `shutdownNow()` = cố ngắt tác vụ đang chạy, không tiếp tục xử lý pending và trả về danh sách pending. `awaitTermination()` = chờ executor thật sự kết thúc hoặc hết thời hạn; bản thân nó không hủy hay shutdown.**

Một ứng dụng Java cần lifecycle rõ ràng thường dùng **shutdown hai giai đoạn**: graceful trước, đợi có hạn, fallback hủy bằng interrupt nếu cần, rồi đợi lần nữa và báo cáo khi chưa terminated. Nhưng kết thúc worker **không đồng nghĩa** mọi task thành công, và cancel **không đồng nghĩa** cleanup đã xong. Luôn xem xét outcome qua Future hoặc giao thức nghiệp vụ, tính nhất quán khi hủy, xử lý pending tasks, thời hạn shutdown và thứ tự đóng các resource phụ thuộc.
