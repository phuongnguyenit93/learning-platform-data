# Khôi phục interrupt flag khi không thể truyền ngoại lệ trong Java

Trong Java, **interruption** là một cơ chế yêu cầu thread hợp tác dừng hoặc thay đổi công việc đang thực hiện. Nó không cưỡng ép thread kết thúc. Một thread có thể đang chờ trong `Thread.sleep()`, `Object.wait()`, `Thread.join()`, `BlockingQueue.take()` hay một thao tác blocking có hỗ trợ interruption. Khi thread được interrupt, các phương thức này thường **ném `InterruptedException` và đồng thời xóa interrupt status** theo hợp đồng của chúng.

Nếu một phương thức đang xử lý có quyền khai báo `throws InterruptedException`, cách đơn giản nhất thường là **truyền ngoại lệ lên tầng gọi** để tầng đó quyết định việc hủy. Nhưng có những ranh giới API **không cho phép khai báo checked exception**, chẳng hạn `Runnable.run()`, `Consumer.accept()`, nhiều callback, phương thức override interface không có `throws InterruptedException` hoặc một public API cố ý không khai báo ngoại lệ đó.

Trong trường hợp **không thể truyền ngoại lệ**, quy tắc mặc định rất quan trọng là:

> **Sau khi bắt `InterruptedException`, nếu chưa xử lý hoàn toàn yêu cầu interrupt ở tầng hiện tại, hãy khôi phục trạng thái bằng `Thread.currentThread().interrupt()`, rồi dừng hoặc trả quyền điều khiển phù hợp.** Không được bắt rồi im lặng tiếp tục làm việc như thể chưa hề có yêu cầu hủy.

Bài Knowledge này thuộc nhóm **Interrupt & Hủy** trong **Java concurrency nói chung**, tập trung vào Java SE 17+, không dùng cơ chế riêng của Spring Framework.

## 1. Interrupt flag là gì?

Mỗi `Thread` có **interrupt status**: một trạng thái logic có thể được đặt khi ai đó gọi `thread.interrupt()`. Thread được yêu cầu ngắt thường tự kiểm tra trạng thái hoặc đang gọi một API có hợp đồng xử lý interruption.

Ba lời gọi cần phân biệt:

| Lời gọi | Đối tượng chịu tác động | Ngữ nghĩa |
| --- | --- | --- |
| `targetThread.interrupt()` | `targetThread` | Đặt/yêu cầu interrupt; nếu target đang đợi bằng API interruptible, API có thể đánh thức bằng exception |
| `targetThread.isInterrupted()` | `targetThread` | Đọc interrupt status; **không xóa** status |
| `Thread.interrupted()` | **Thread hiện tại** | Đọc và **xóa** interrupt status của current thread khi trả về true |

`Thread.interrupted()` là **static method**; không phải phương thức kiểm tra trạng thái của một thread bất kỳ. Tránh viết `otherThread.interrupted()` với hy vọng nó kiểm tra `otherThread`: cách gọi static đó vẫn thao tác trên **current thread**. Muốn xem status của một thread cụ thể, dùng `otherThread.isInterrupted()`.

Cần phân biệt **request** và **completion**:

- `interrupt()` đặt yêu cầu; không bảo đảm method `run()` đã kết thúc.
- `isInterrupted()` trả flag; không chứng minh thread đã dừng, đã cleanup hay task thành công.
- `Thread.join()`, `Future.get()` hoặc tín hiệu completion riêng là cơ chế phù hợp để biết công việc đã hoàn tất theo hợp đồng.
- Thread có thể bỏ qua interrupt, xử lý thành công hoặc kết thúc; kết quả phụ thuộc code và API blocking đang dùng.

## 2. Tại sao `InterruptedException` có thể làm mất interrupt flag?

Nhiều API blocking của Java hỗ trợ interruption theo kiểu **ném checked exception**. Khi ném `InterruptedException` do bị ngắt, các API điển hình như `Thread.sleep()` và `Object.wait()` **xóa interrupt status** trước khi control được chuyển vào `catch`.

Ví dụ logic:

```text
Trước yêu cầu:
  interrupt flag = false
  worker đang sleep

Thread khác:
  worker.interrupt()

Worker:
  sleep() phát hiện interruption
  sleep() ném InterruptedException
  interrupt status được xóa như một phần của hợp đồng
  catch (InterruptedException e) { ... }
```

Việc xóa status ở đây có chủ ý: **ngoại lệ chính là cách báo cho code rằng sự kiện interrupt đã xảy ra**. Nếu code bắt ngoại lệ rồi chỉ log và bỏ qua, tín hiệu có thể không còn đường truyền lên tầng điều phối.

Không nên suy rộng rằng **mọi** API hoặc **mọi** interruption đều luôn xóa flag. Một số thao tác có thể giữ trạng thái, phản hồi bằng giá trị khác, hoặc không chấp nhận interruption trong lúc block. Phải đọc hợp đồng của API cụ thể.

Đặc biệt, `Thread.interrupted()` **chủ động xóa** flag khi dùng để kiểm tra; `Thread.currentThread().isInterrupted()` thì không.

## 3. Khi nào nên truyền tiếp, khi nào nên khôi phục?

Ba tình huống quan trọng:

### Trường hợp A — phương thức được khai báo `throws InterruptedException`

Nếu contract của method cho phép, **truyền ngoại lệ** thường là cách đúng nhất:

```java
static String receive(
        java.util.concurrent.BlockingQueue<String> queue)
        throws InterruptedException {
    return queue.take();
}
```

Đây là phương thức minh họa, không phải chương trình có `main`. Nó không bắt interruption và không biến task bị hủy thành một lần nhận thành công.

Trong code cần cleanup:

```java
static String receiveWithCleanup(
        java.util.concurrent.BlockingQueue<String> queue)
        throws InterruptedException {
    try {
        return queue.take();
    } finally {
        // Giải phóng tài nguyên thuộc phạm vi phương thức, nếu có.
    }
}
```

Đây vẫn là đoạn minh họa. Nếu caller muốn biết và quyết định cách hủy, có thể để exception đi lên. **Không bắt buộc vừa gọi `interrupt()` vừa truyền tiếp `InterruptedException`**; ngoại lệ đã là tín hiệu cho tầng tiếp theo. Việc đồng thời khôi phục status có thể thích hợp theo contract đặc biệt, nhưng không phải quy tắc bắt buộc khi đã propagate.

### Trường hợp B — không thể khai báo `throws InterruptedException`

`Runnable.run()` không khai báo checked exception này. Một thread đang chạy `Runnable` phải bắt ngoại lệ nếu gọi API như `sleep()` hay `take()`. Nếu muốn nhường quyền quyết định cho tầng ngoài thông qua flag, dùng:

```java
@Override
public void run() {
    try {
        doInterruptibleWork();
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        return;
    }
}
```

Đây là đoạn minh họa trong class implement `Runnable`, với `doInterruptibleWork()` là phương thức giả định. `Thread.currentThread().interrupt()` **khôi phục status của thread đang xử lý**, sau đó `return` kết thúc `run`. Nếu tiếp tục một vòng xử lý dài sau catch, flag có thể đã được bật nhưng task vẫn làm việc sai ý định hủy.

### Trường hợp C — tầng hiện tại đã xử lý trọn vẹn interruption theo contract

Một API đặc biệt có thể **cố ý tiêu thụ** interrupt nếu trách nhiệm của nó là chấm dứt hoạt động và công bố kết quả hủy bằng cơ chế khác, và contract xác định rõ điều này. Khi đó không có quy tắc tuyệt đối phải restore trong mọi catch.

Tuy nhiên, **đừng tự nhận "đã xử lý" chỉ vì đã log exception**. Nếu việc hủy vẫn cần được người gọi hoặc framework executor nhận biết, restore là lựa chọn an toàn hơn khi không thể propagate. Cần phân biệt việc xử lý tín hiệu có chủ ý với việc vô tình làm mất tín hiệu.

## 4. Vì sao `catch (InterruptedException e) { }` là anti-pattern?

Sai:

```java
while (true) {
    try {
        queue.take();
    } catch (InterruptedException ignored) {
        // Bỏ qua yêu cầu hủy và tiếp tục chờ.
    }
}
```

Đây là anti-pattern với biến `queue` giả định. Hậu quả:

1. `take()` có thể đã xóa interrupt flag trước khi ném.
2. Catch rỗng loại bỏ thông tin về yêu cầu hủy.
3. Vòng lặp quay lại `take()` và chờ vô thời hạn, dù caller mong worker thoát.
4. `Future.cancel(true)` hoặc shutdown hợp tác có thể trở nên vô hiệu về mặt dừng task.
5. Hệ thống khó phân biệt worker bận, worker kẹt và worker cố tình bỏ qua hủy.

Cũng không đủ nếu chỉ viết:

```java
catch (InterruptedException e) {
    System.err.println("Interrupted: " + e);
}
```

Logging không thay thế propagation hoặc status restoration. Nếu sau catch code còn tiếp tục bình thường, người dùng API có thể tưởng tác vụ chưa bị hủy. **Đúng hơn:** quyết định rõ "truyền tiếp", "khôi phục và kết thúc", hay "chuyển sang cancellation state theo contract".

## 5. Ví dụ Java 17+: khôi phục interrupt flag trong `Runnable`

Lưu thành `InterruptRestoreDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

public class InterruptRestoreDemo {
    public static void main(String[] args)
            throws InterruptedException {
        CountDownLatch entered = new CountDownLatch(1);
        AtomicBoolean clearedWhenCaught = new AtomicBoolean();
        AtomicBoolean restoredInsideCatch = new AtomicBoolean();

        Thread worker = new Thread(() -> {
            try {
                entered.countDown();
                Thread.sleep(60_000);
            } catch (InterruptedException e) {
                // sleep() đã xử lý interruption bằng exception
                // và xóa flag theo hợp đồng.
                clearedWhenCaught.set(
                        !Thread.currentThread().isInterrupted());

                // Không thể throws InterruptedException từ Runnable.run().
                Thread.currentThread().interrupt();
                restoredInsideCatch.set(
                        Thread.currentThread().isInterrupted());
                return;
            }
        }, "interrupt-restore-worker");

        worker.start();
        entered.await();

        worker.interrupt();
        worker.join();

        System.out.println("Flag cleared in catch: "
                + clearedWhenCaught.get());
        System.out.println("Flag restored in catch: "
                + restoredInsideCatch.get());
        System.out.println("Worker terminated: "
                + !worker.isAlive());
    }
}
```

Biên dịch/chạy:

```bash
javac InterruptRestoreDemo.java
java InterruptRestoreDemo
```

Stdout chính xác trên đường chạy bình thường:

```text
Flag cleared in catch: true
Flag restored in catch: true
Worker terminated: true
```

Tại sao đáng tin?

- `entered` chỉ thông báo worker đã đến trước lời gọi `sleep()`. Nếu main interrupt trước lúc worker thật sự sleep, sleep vẫn phản hồi với interrupt status; nếu worker đang sleep, nó được đánh thức bằng `InterruptedException`. Không phụ thuộc một lần `Thread.sleep(100)` ở main để đoán lịch chạy.
- Khi `InterruptedException` được ném từ `sleep`, interrupt flag đã được xóa; `clearedWhenCaught` nhận true.
- Worker đặt lại flag bằng `Thread.currentThread().interrupt()`, đo được true trong catch rồi **kết thúc `run()`**.
- Main gọi `join()` để đợi worker kết thúc trước khi đọc hai `AtomicBoolean` và trạng thái thread.
- **Không lấy `worker.isInterrupted()` từ main sau `join()` để làm kiểm chứng bắt buộc**. Khi thread đã kết thúc, không nên dựa vào trạng thái interrupt hậu vòng đời để chuyển ý nghĩa business. Ví dụ ghi nhận flag ngay trong worker để kiểm tra ý nghĩa ở đúng thời điểm.

Đây là ví dụ cho cách **bảo toàn yêu cầu hủy** qua ranh giới API không cho phép throws; nó không ép thread phải bị kill.

## 6. `Thread.interrupted()` xóa flag, còn `isInterrupted()` thì không

Lưu thành `InterruptFlagMethodsDemo.java`:

```java
public class InterruptFlagMethodsDemo {
    public static void main(String[] args) {
        Thread current = Thread.currentThread();

        current.interrupt();

        System.out.println("Before check: "
                + current.isInterrupted());
        System.out.println("Static check: "
                + Thread.interrupted());
        System.out.println("After static check: "
                + current.isInterrupted());

        current.interrupt(); // Khôi phục một lần nữa.
        System.out.println("Restored: "
                + current.isInterrupted());

        // Dọn interrupt status để kết thúc bài demo.
        Thread.interrupted();
    }
}
```

```bash
javac InterruptFlagMethodsDemo.java
java InterruptFlagMethodsDemo
```

Stdout chính xác:

```text
Before check: true
Static check: true
After static check: false
Restored: true
```

`Thread.interrupted()` là lời gọi **static** và kiểm tra **current thread**, sau đó xóa flag khi đang bật. Ngược lại `current.isInterrupted()` không xóa flag. Cuối chương trình có một lần `Thread.interrupted()` chỉ để cleanup trong ví dụ **có chủ đích**; không được dùng cách "kiểm tra rồi vô tình xóa" trong code nghiệp vụ đang muốn chuyển tiếp yêu cầu hủy.

Đối với vòng xử lý hợp tác, có thể kiểm tra:

```java
while (!Thread.currentThread().isInterrupted()) {
    processOneUnit();
}
```

Đây là mẫu minh họa; `processOneUnit` không xác định. Nếu hàm bên trong có thể block/throw `InterruptedException`, phải kết hợp xử lý ngoại lệ để thoát vòng đúng lúc. Kiểm tra flag không tự đánh thức lời gọi blocking.

## 7. Vì sao restore xong thường phải thoát, không chỉ tiếp tục?

Một lỗi tinh vi:

```java
while (true) {
    try {
        performBlockingOperation();
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        // Nhưng lại chạy vòng lặp tiếp.
    }
}
```

Nếu `performBlockingOperation` phản hồi ngay khi thấy interrupt flag đang bật, vòng sau có thể liên tục ném `InterruptedException`, tạo **busy loop** tiêu thụ CPU. Nếu API khác không kiểm tra flag, code lại có thể tiếp tục làm việc dù đã nhận yêu cầu hủy.

Mẫu thường tốt hơn:

```java
while (!Thread.currentThread().isInterrupted()) {
    try {
        performBlockingOperation();
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        break;
    }
}
```

Hai đoạn trên là minh họa, `performBlockingOperation` giả định.

**Tách hai quyết định:** phục hồi flag để giữ thông tin interruption, và **dừng/từ chối công việc mới** để thực sự hợp tác hủy. Chỉ có thao tác đầu mà thiếu thao tác thứ hai có thể làm trạng thái "interrupted" tồn tại trên một thread vẫn đang xử lý nghiệp vụ.

Nếu method bắt exception nằm sâu trong một stack, có thể khôi phục và `return` trạng thái hủy cho caller để caller không tiếp tục; nếu API có kiểu trả về, phải định nghĩa rõ sentinel hoặc result type đại diện việc hủy.

## 8. Ví dụ Java 17+: worker chờ queue và dừng hợp tác

Lưu thành `CooperativeQueueWorkerDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

public class CooperativeQueueWorkerDemo {
    public static void main(String[] args)
            throws InterruptedException {
        BlockingQueue<Integer> queue = new ArrayBlockingQueue<>(1);
        CountDownLatch started = new CountDownLatch(1);
        AtomicBoolean stoppedOnInterrupt = new AtomicBoolean();
        AtomicBoolean restored = new AtomicBoolean();

        Thread worker = new Thread(() -> {
            started.countDown();

            try {
                while (!Thread.currentThread().isInterrupted()) {
                    queue.take(); // Có thể block khi queue rỗng.
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                restored.set(Thread.currentThread().isInterrupted());
                stoppedOnInterrupt.set(true);
            }
        }, "queue-worker");

        worker.start();
        started.await();

        worker.interrupt();
        worker.join();

        System.out.println("Stopped: " + stoppedOnInterrupt.get());
        System.out.println("Flag at exit: " + restored.get());
    }
}
```

```bash
javac CooperativeQueueWorkerDemo.java
java CooperativeQueueWorkerDemo
```

Stdout chính xác:

```text
Stopped: true
Flag at exit: true
```

Lịch chạy có thể khác nhau:

- Nếu worker đã vào `queue.take()`, interruption thường làm `take` ném `InterruptedException`, catch đặt lại flag, rồi control đi vào `finally`.
- Nếu main interrupt trước lúc worker vào `take()`, vòng lặp có thể nhìn thấy flag và thoát trực tiếp; hoặc lần `take` có thể phát hiện interrupt và ném. Cả hai đều dẫn đến kiểm tra trạng thái true tại điểm kết thúc.
- Queue luôn rỗng, nên không có trường hợp worker thực hiện một tác vụ mới rồi thoát mà làm stdout thay đổi.
- `join` bảo đảm main đợi worker hoàn tất trước khi đọc kết quả.

`stoppedOnInterrupt` trong ví dụ ghi true khi worker rời khối xử lý; nó là flag quan sát cho bài demo, **không phải contract completion đầy đủ** cho ứng dụng phức tạp. Nếu cần lấy lỗi/kết quả task, `Future` hoặc một kiểu kết quả phù hợp thường rõ hơn.

Trong production, cần phân biệt lỗi khác với interruption. Một task kết thúc bình thường hoặc gặp exception khác cũng sẽ chạy `finally`; không nên dùng duy nhất "đã vào finally" để kết luận lý do kết thúc nếu code có nhiều nhánh.

## 9. Ranh giới thường gặp: `Runnable.run()`

`Runnable.run()` có chữ ký:

```java
void run();
```

Đây là chữ ký của interface, không khai báo checked `InterruptedException`. Code trong `run` phải xử lý ngoại lệ nếu nó gọi các API interruptible.

Mẫu thông dụng:

```java
final class Worker implements Runnable {
    private final java.util.concurrent.BlockingQueue<String> queue;

    Worker(java.util.concurrent.BlockingQueue<String> queue) {
        this.queue = queue;
    }

    @Override
    public void run() {
        try {
            while (true) {
                String message = queue.take();
                handle(message);
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            // Trả về từ run() để dừng thread/task.
        }
    }

    private void handle(String message) {
        // Xử lý không block hoặc có chính sách lỗi riêng.
    }
}
```

Class này không có `main`, nhưng dùng Java SE thuần. Nếu `handle` có thể block, ném exception, hoặc cập nhật state ngoài process, nó cần thêm hợp đồng hủy và xử lý partial side effect.

Vì API `Runnable` là một ranh giới không cho phép khai báo checked exception, **restore rồi return** là lựa chọn thường gặp. Nếu framework executor có chính sách quan sát exception theo future, có thể cân nhắc wrapping thành unchecked exception **khi contract yêu cầu**; vẫn phải xác định trạng thái interrupt và cách báo lỗi. Không tự động biến mọi interruption thành lỗi "business failure" mà không kiểm tra contract.

## 10. Ranh giới thường gặp: `Consumer<T>`, listener và callback

Ví dụ callback:

```java
import java.util.function.Consumer;

Consumer<String> listener = event -> {
    try {
        Thread.sleep(1_000);
        System.out.println(event);
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        return;
    }
};
```

Đây là đoạn minh họa trong một context hợp lệ có import; không phải file có `main`. `Consumer.accept` không khai báo checked `InterruptedException`, nên callback phải xử lý.

**Hai rủi ro:**

1. Callback bị interrupt có thể dừng riêng callback nhưng **publisher vẫn tiếp tục gọi callback khác**, tùy contract của publisher. Vì thế cần định nghĩa caller có quan tâm status của thread đang chạy callback không và callback nên chuyển kết quả hủy bằng cách nào.
2. Nếu callback chạy trên **thread dùng chung**, interrupt status được khôi phục trên thread đó. Điều này là thông tin chính xác tại ranh giới callback, nhưng caller/dispatcher cần có chính sách không tiếp tục chạy tác vụ bình thường bất chấp status.

Không giả định callback chắc chắn chạy trên thread riêng. Một listener có thể được gọi **đồng bộ trên thread gọi**, hoặc bởi executor; cơ chế tương tác quyết định ai sở hữu thread đang được interrupt. Trong public API, document threading model, cancellation behavior và failure propagation.

### Phương thức override không cho thêm checked exception

Nếu interface quy định:

```java
interface Listener {
    void onMessage(String message);
}
```

implementation không thể tùy ý thêm `throws InterruptedException` vào chữ ký override. Nếu việc xử lý phải block, có thể:

- Catch, restore flag rồi **return/abort** theo contract.
- Đổi API do mình kiểm soát để cho phép checked interruption hoặc trả trạng thái hủy.
- Dùng một callback riêng có chữ ký `throws InterruptedException` nếu thực sự có quyền thay đổi interface.
- Tách công việc blocking sang một layer có thể truyền exception theo `Callable`/future phù hợp.

Đừng biến một hạn chế chữ ký thành cớ để **nuốt interruption**.

## 11. `Callable<V>` và sự khác nhau khi có thể propagate

`Callable.call()` có chữ ký:

```java
V call() throws Exception;
```

Nó cho phép truyền `InterruptedException` (là subclass của `Exception`), khác với `Runnable.run()`.

Ví dụ:

```java
Callable<String> task = () -> queue.take();
```

Đây là đoạn minh họa, giả định `queue` là `BlockingQueue<String>` và đã import `java.util.concurrent.Callable`.

Khi task được gửi tới `ExecutorService.submit`, ngoại lệ từ `call` được thu nhận trong `Future`; caller dùng `Future.get()` có thể gặp `ExecutionException` bao nguyên nhân. Cần phân biệt:

- `InterruptedException` ném **trong worker task**.
- `InterruptedException` ném **trong caller đang chờ `future.get()`** vì **caller thread** bị interrupt.
- `CancellationException` khi future đã được cancel theo contract.
- `ExecutionException` khi task kết thúc bằng exception.

Đây là các đường diễn tiến khác nhau. Caller không nên bắt một `InterruptedException` từ `future.get()` rồi mặc định worker cũng đã bị interrupt; nó báo **thread gọi `get` đang bị yêu cầu ngắt trong lúc chờ**.

Nếu chính `Callable.call` có thể truyền ngoại lệ lên tầng quản lý, **không cần mặc định bắt lại để restore**. Nếu `call` bắt chỉ để cleanup rồi propagate, phải giữ nguyên thông tin hủy, không biến thành successful result.

## 12. Ví dụ Java 17+: Future và hai loại interruption

Chương trình sau kiểm chứng **caller của `Future.get()` bị interrupt**, còn task chỉ được giải phóng sau đó bằng một tín hiệu riêng. Không suy luận sai rằng interrupt caller đồng nghĩa interrupt worker.

Lưu thành `FutureWaitInterruptionDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicBoolean;

public class FutureWaitInterruptionDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch allowTaskToFinish = new CountDownLatch(1);
        CountDownLatch aboutToGet = new CountDownLatch(1);
        AtomicBoolean callerRestored = new AtomicBoolean();

        try {
            Future<Integer> future = pool.submit(() -> {
                allowTaskToFinish.await();
                return 42;
            });

            Thread caller = new Thread(() -> {
                try {
                    aboutToGet.countDown();
                    future.get();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    callerRestored.set(
                            Thread.currentThread().isInterrupted());
                } catch (Exception e) {
                    throw new IllegalStateException(e);
                }
            }, "future-caller");

            caller.start();
            aboutToGet.await();
            caller.interrupt();
            caller.join();

            // Task chưa bị cancel hoặc interrupt bởi thao tác trên caller.
            allowTaskToFinish.countDown();
            System.out.println("Caller flag restored: "
                    + callerRestored.get());
            System.out.println("Task result: " + future.get());
        } finally {
            allowTaskToFinish.countDown();
            pool.shutdownNow();
        }
    }
}
```

```bash
javac FutureWaitInterruptionDemo.java
java FutureWaitInterruptionDemo
```

Stdout chính xác trên đường chạy bình thường:

```text
Caller flag restored: true
Task result: 42
```

**Lý do deterministic:**

- Task worker đợi `allowTaskToFinish`, chưa thể hoàn tất trong lúc thread caller chờ `future.get()`.
- Caller thông báo đã tới điểm trước `get()`; main có thể interrupt trước hoặc trong `get()`. Nếu interrupt đến trước lời gọi chờ thực tế, `get()` vẫn thấy interrupt status khi phải chờ trên future chưa hoàn thành.
- `future.get()` ném `InterruptedException` trên **caller**, catch khôi phục flag của caller.
- `caller.join()` đợi thread caller thoát, rồi main giải phóng task. Chỉ lúc này `future.get()` trong main lấy kết quả 42.
- `finally` bảo đảm main mở latch nếu có lỗi trên đường đi, sau đó gửi yêu cầu shutdown.

Không dùng ví dụ này để kết luận `Future.get()` luôn phản hồi interruption theo đúng một thời điểm: nó là API chờ có thể bị ngắt, còn nếu future đã hoàn tất trước khi caller bắt đầu chờ, các điều kiện có thể khác. Việc giữ task chưa hoàn tất trong demo giúp kết quả ổn định.

## 13. `Future.cancel(true)` không phải là "đã xử lý xong"

`Future.cancel(true)` là một yêu cầu hủy có thể cho phép gửi interrupt đến worker nếu task đang chạy và có thể bị interrupt theo implementation. Giá trị trả về cho biết việc cancel request có được chấp nhận theo contract của future; nó **không cam kết mọi side effect đã dừng ngay** hay resource đã cleanup hoàn tất.

Nếu worker:

```java
try {
    blockingOperation();
} catch (InterruptedException e) {
    // Nuốt ngoại lệ rồi tiếp tục.
    continueWorking();
}
```

thì cancellation có thể không khiến code dừng như caller mong muốn. Mẫu trên là anti-pattern minh họa với phương thức giả định.

Nếu worker restore rồi thoát, đó là **cooperative cancellation** đúng mục tiêu hơn. Tuy vậy, cần phân biệt:

- **Future cancelled** không có nghĩa executor đã hoàn toàn giải phóng mọi tài nguyên của task.
- **Thread interrupted** không có nghĩa task chưa để lại partial side effect.
- **Thread terminated** không có nghĩa operation đã thành công.
- Khi dùng `CompletableFuture.cancel(...)`, theo hợp đồng của `CompletableFuture`, tham số `mayInterruptIfRunning` không dùng để điều khiển underlying processing; đừng mặc định cancellation sẽ interrupt một tác vụ đang chạy như một số Future do executor quản lý.

Để đợi lifecycle thực sự hoàn tất, cần một contract completion/cleanup rõ ràng, future hoặc latch riêng nếu trạng thái canceled không đủ biểu diễn điểm cleanup.

## 14. Khôi phục flag trong utility method không khai báo throws

Một helper đôi khi có chữ ký không cho đổi, như:

```java
boolean awaitQuietly(CountDownLatch latch);
```

Từ "quietly" dễ khiến người viết chọn bỏ qua interruption. Nếu không thể truyền checked exception, có thể trả `false` và restore flag, **nhưng chỉ khi contract định nghĩa `false` là bị hủy/chưa hoàn thành**.

Mẫu Java:

```java
static boolean awaitOrCancel(
        java.util.concurrent.CountDownLatch latch) {
    try {
        latch.await();
        return true;
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        return false;
    }
}
```

Đây là phương thức minh họa, không phải chương trình có `main`.

**Quan trọng:** caller phải kiểm tra kết quả:

```java
if (!awaitOrCancel(latch)) {
    return; // Không tiếp tục vào nhánh yêu cầu latch đã hoàn tất.
}
performAfterCompletion();
```

Đây là đoạn minh họa khác với `latch` và `performAfterCompletion` giả định. Nếu caller bỏ qua `false` rồi vẫn làm việc, lời hứa "return false khi chưa sẵn sàng" không giúp duy trì invariant.

API rõ hơn có thể dùng enum kết quả `COMPLETED`/`INTERRUPTED`, hoặc tách method interruptible với wrapper no-throws có chính sách cụ thể.

## 15. Ví dụ Java 17+: trả kết quả hủy và giữ interrupt flag

Lưu thành `NoThrowsBoundaryDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

public class NoThrowsBoundaryDemo {
    static boolean awaitOrCancel(CountDownLatch gate) {
        try {
            gate.await();
            return true;
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return false;
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        CountDownLatch gate = new CountDownLatch(1);
        CountDownLatch ready = new CountDownLatch(1);
        AtomicBoolean result = new AtomicBoolean(true);
        AtomicBoolean restored = new AtomicBoolean();

        Thread worker = new Thread(() -> {
            ready.countDown();
            result.set(awaitOrCancel(gate));
            restored.set(Thread.currentThread().isInterrupted());
        });

        worker.start();
        ready.await();
        worker.interrupt();
        worker.join();

        System.out.println("Gate passed: " + result.get());
        System.out.println("Flag restored: " + restored.get());
    }
}
```

```bash
javac NoThrowsBoundaryDemo.java
java NoThrowsBoundaryDemo
```

Stdout chính xác:

```text
Gate passed: false
Flag restored: true
```

Gate **không bao giờ được mở**, nên nếu không bị interrupt, worker sẽ tiếp tục chờ. Main yêu cầu interrupt; helper catch, restore rồi trả `false`. Cả hai AtomicBoolean cho phép main đọc sau `join`, dù chính `join` đã đủ thiết lập happens-before cho việc đọc các kết quả worker ghi.

Ví dụ minh họa cách định nghĩa **contract của wrapper**: `false` không có nghĩa gate đã hoàn tất; nó có nghĩa method không thể đợi thành công. Tầng gọi cần quyết định chấm dứt công việc khi nhận false.

## 16. Có nên rethrow bằng unchecked exception?

Khi API không cho `throws InterruptedException`, một số hệ thống chọn:

```java
try {
    doInterruptibleWork();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Interrupted while working", e);
}
```

Đây là đoạn minh họa, không phải công thức dùng chung cho mọi tầng.

Ưu điểm: **không giả vờ thành công**; thông tin lỗi có thể đi tới exception handler hoặc future. Rủi ro: unchecked exception có thể được hệ thống coi là application failure thay vì cancellation; nó có thể làm thay đổi contract public API và khiến listener dispatch dừng đột ngột.

Nếu chọn cách này, tài liệu phải nói rõ:

- Exception nào đại diện interruption/cancellation?
- Caller có dựa vào interrupt flag đã restore không?
- Có resource cleanup cần làm trước khi throw không?
- Task có bị retry vì runtime exception không; retry có thể nhân đôi side effect không?

Cách đơn giản cho `Runnable.run()` thường là **restore rồi return** khi nhiệm vụ chỉ cần dừng. Cách dùng unchecked exception phù hợp khi tầng điều phối cần nhận failure bằng exception và contract đã định nghĩa rõ.

## 17. Cleanup, `finally` và thời điểm khôi phục flag

Khi bị interrupt, code vẫn có thể phải giải phóng khóa, permit, file hoặc resource đang sở hữu. Quy tắc **không bỏ cleanup** và **không làm mất interruption** đều quan trọng.

Nếu cleanup đơn giản và không có blocking operation:

```java
try {
    doInterruptibleWork();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
} finally {
    releaseOwnedResource();
}
```

Đây là ví dụ minh họa. `finally` chạy khi control rời `try/catch`, kể cả khi catch `return`; nhưng **không thể bảo đảm mọi cleanup sẽ thành công** nếu chính cleanup ném exception.

Nếu cleanup **có thể block và hỗ trợ interruption**, khôi phục flag **trước** cleanup có thể làm lời gọi cleanup ném `InterruptedException` ngay, cản trở việc dọn tài nguyên. Trong một số thiết kế, cần tạm **ghi nhớ việc đã bị interrupt**, làm cleanup có giới hạn theo contract, rồi **khôi phục flag trong `finally` sau cleanup**:

```java
boolean interrupted = false;

try {
    doInterruptibleWork();
} catch (InterruptedException e) {
    interrupted = true;
    // Không tiếp tục công việc nghiệp vụ bình thường.
} finally {
    try {
        cleanupWithDefinedPolicy();
    } finally {
        if (interrupted) {
            Thread.currentThread().interrupt();
        }
    }
}
```

Đây là pseudo-flow minh họa; `doInterruptibleWork` và `cleanupWithDefinedPolicy` là phương thức giả định. Nó chỉ thích hợp khi tầng hiện tại **thực sự sở hữu cleanup** và việc trì hoãn restore là chủ ý, không phải nuốt tín hiệu. Nếu cleanup cũng bị interrupt, policy phải quyết định timeout/retry/propagate như thế nào. Không được thực hiện **retry vô hạn không interruptible** chỉ để "cleanup cho bằng được".

Đặc biệt, `synchronized` tự nhả monitor khi rời block; `Lock` thủ công phải `unlock()` trong `finally`. Restoration không thay thế việc nhả lock.

## 18. Khi cleanup cũng bị interrupt, phải xử lý ra sao?

Xem tình huống utility có hai pha:

1. Chờ công việc hoàn tất.
2. Khi bị interrupt, cố ghi nhận/trả tài nguyên và thoát.

Nếu cả pha cleanup cũng gọi API blocking, một số cách ứng xử tùy contract:

- **Best-effort cleanup có deadline:** thử trong khoảng thời gian hữu hạn, rồi ghi nhận thất bại hoặc trả về state lỗi; khôi phục flag khi kết thúc.
- **Cleanup không interruptible nhưng ngắn:** thực thi thao tác giải phóng nội bộ bảo đảm rồi restore.
- **Propagate một ngoại lệ cao hơn:** nếu tầng hiện tại được phép, truyền interruption hoặc failure kèm nguyên nhân thích hợp; tránh làm mất original cause.
- **Đóng resource để đánh thức waiter:** tùy hợp đồng cụ thể của queue/channel/resource, không tự giả định `Thread.interrupt()` đã dừng mọi I/O.

Một anti-pattern khác là lặp:

```java
while (true) {
    try {
        cleanupBlocking();
        break;
    } catch (InterruptedException ignored) {
        // Cố chờ vô hạn, không lưu lại trạng thái và không timeout.
    }
}
```

Đây là đoạn minh họa sai: nó có thể bỏ qua yêu cầu hủy lâu dài, không còn giới hạn tiến độ. Nếu buộc phải hoàn tất cleanup, hãy thiết kế protocol có deadline và ghi lại điều kiện interrupt; không mặc nhiên "cleanup quan trọng nên bỏ qua mọi interrupt".

## 19. Một cờ `AtomicBoolean` không tương đương interrupt flag

Nhiều ứng dụng có:

```java
AtomicBoolean stopRequested = new AtomicBoolean();
stopRequested.set(true);
```

Một cờ atomic/volatile giúp worker thấy yêu cầu khi chủ động kiểm tra. Nhưng cờ không tự đánh thức thread đang `BlockingQueue.take()` hoặc `Object.wait()`. Interruption là cơ chế riêng mà nhiều API blocking hiểu để **thoát khỏi lời gọi chờ**.

Ngược lại, chỉ gọi `thread.interrupt()` không tự định nghĩa kết quả business: task có thể dừng một phần, bỏ qua request hoặc hoàn tất đúng. Thường cần kết hợp:

- Một cancellation policy của task.
- Một đường signaling (interrupt, sentinel, close, timeout hoặc cancellation token).
- Một completion signal để caller biết cleanup đã xong.
- Một cách báo lỗi hoặc trạng thái hủy cho người gọi.

Khi restore flag, bạn **bảo toàn thông tin yêu cầu interrupt**, không tự xây toàn bộ lifecycle protocol.

## 20. Không phải mọi blocking I/O đều phản hồi interruption như `sleep()`

Một số API trong `java.nio.channels` có semantics đóng channel khi thread bị interrupt, hoặc phản hồi qua exception khác. Một số thao tác legacy I/O có thể không dừng kịp khi chỉ gọi `interrupt()`. Các thư viện network, driver hoặc native code có hợp đồng riêng.

Vì vậy:

- Không áp dụng máy móc "mọi blocking I/O đều ném `InterruptedException`".
- Nếu một API trả exception khác do interruption, đọc hợp đồng để quyết định preserve status/cancellation signal đúng.
- Thiết kế timeout, resource close và cancellation path thích hợp.
- Nếu không thể hủy một thao tác, document giới hạn và giám sát thread/resource bị kẹt.
- Tránh giữ monitor trong lúc thực hiện I/O có thể block lâu, vì việc dừng/cleanup có thể cần một thread khác vào monitor đó.

Bài học về **restore interrupt flag** chủ yếu áp dụng tình huống **một interruptible call đã ném `InterruptedException` và làm clear status**, rồi code của bạn không thể truyền checked exception lên. Với API khác, không suy đoán semantics khi chưa đọc contract.

## 21. Interrupt flag và Java Memory Model

Interruption có các bảo đảm liên quan happens-before trong JMM: một lời gọi `interrupt()` trên thread target **synchronizes-with** điểm một thread phát hiện nó đã bị interrupt theo hợp đồng (ví dụ nhận `InterruptedException`, hoặc kiểm tra trạng thái bằng API thích hợp).

Nhưng một interrupt request **không thay thế khóa bảo vệ shared mutable state**. Nếu bạn có:

```java
sharedList.add(item);
worker.interrupt();
```

thì không được chỉ dựa vào `interrupt()` để kết luận mọi thao tác concurrent của `ArrayList` đã an toàn. Quan hệ ordering của một interrupt signal không biến list thành concurrent collection hoặc tạo transaction giữa nhiều thao tác.

Tương tự, interrupt status không cung cấp:

- Atomicity cho `count++`.
- Mutual exclusion cho nhiều writer.
- Guaranteed fairness khi có nhiều task.
- Một thông báo kết quả task thành công.
- Khả năng rollback side effect bên ngoài JVM.

**Restoration là phép bảo toàn tín hiệu**, không phải cách sửa một thuật toán đang có data race.

## 22. Tương tác với executor và thread pool

Khi task chạy trong executor, thread thực thi có thể được **tái sử dụng**. Interruption là trạng thái của **thread**, trong khi cancellation/failure/completion của một task là **trạng thái nghiệp vụ khác**.

Cần chú ý:

1. Một `Runnable` bị interrupt nên **thoát có kiểm soát**, không tiếp tục tiêu thụ task tiếp theo như thể bình thường.
2. Nếu task bắt `InterruptedException` rồi bỏ qua, `shutdownNow()` hoặc `cancel(true)` có thể không giúp task dừng nhanh như mong đợi.
3. Khôi phục flag giúp giữ yêu cầu hủy tại ranh giới task, nhưng **không bảo đảm executor sẽ công bố flag đó ra caller**; hãy dùng future/result hoặc cancellation state để báo lifecycle.
4. Không dựa vào trạng thái interrupt còn lại trên pooled thread cho **task kế tiếp**; thread-pool implementation có thể xử lý/reset status theo logic của nó. Mỗi task phải có contract độc lập.
5. Nếu task phải tự dừng do interruption, đừng thực hiện I/O, callback hoặc side effect mới sau khi restore rồi mới nhận ra đã bị hủy.
6. Nếu API quản lý task có policy riêng về interruption, tuân thủ policy đó thay vì tự quyết định "nuốt cho đỡ log".

Với thread pool, lỗi "nuốt interrupt" đặc biệt khó tìm vì pool vẫn sống, future có thể đã bị cancel, nhưng worker có thể tiếp tục nắm tài nguyên hoặc làm việc không cần thiết.

## 23. Các lỗi thường gặp

| Mẫu lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| `catch (InterruptedException ignored) {}` | Xóa tín hiệu, tiếp tục bình thường | Propagate nếu có thể; nếu không, restore rồi dừng theo contract |
| Catch chỉ log | Log không chuyển yêu cầu hủy tới tầng trên | Restore/propagate, xác định exit path |
| Restore rồi tiếp tục vòng while vô hạn | Có thể busy-loop hoặc làm thêm việc sau khi bị hủy | `break`/`return`, hoặc logic kiểm tra cờ rõ |
| Gọi `Thread.interrupted()` để "kiểm tra" nhưng không muốn clear | Static method xóa flag | Dùng `isInterrupted()` |
| Gọi `otherThread.interrupted()` | Static method vẫn tác động current thread | Dùng `otherThread.isInterrupted()` |
| Tự động restore kể cả khi propagate | Có thể tạo hai kênh tín hiệu không cần thiết và làm caller khó xử lý | Nếu truyền `InterruptedException` lên được, thường cứ truyền |
| Dùng `AtomicBoolean` thay interrupt của blocking call | Flag không đánh thức API đang block | Thêm interrupt/timeout/close hoặc giao thức signaling |
| Gọi interrupt rồi giả định worker đã chết | Interrupt chỉ là yêu cầu | Đợi completion bằng `join`/future/latch theo contract |
| Dùng `Future.cancel(true)` như bảo đảm side effect đã rollback | Cancellation không là transaction | Quản lý idempotency, cleanup và completion |
| Bọc thành RuntimeException nhưng bỏ cause | Làm mất nguồn gốc interruption | Giữ cause, document failure/cancellation policy |
| Restore trước blocking cleanup rồi lặp vô hạn | Cleanup có thể bị interrupt liên tục | Có chính sách cleanup và deadline, restore đúng thời điểm |
| Bỏ qua interruption vì "chỉ là test" | Test có thể treo và che race | Bảo toàn/propagate đúng, giới hạn thời gian chờ |

## 24. Khi nào **không** nên dùng `Thread.currentThread().interrupt()`?

Không phải mọi tình huống liên quan concurrency đều cần restore:

- **Không bắt `InterruptedException`:** nếu phương thức khai báo `throws InterruptedException`, cứ để exception đi lên.
- **Một cancellation contract đã được xử lý hoàn toàn** ở đúng tầng chịu trách nhiệm, có outcome rõ, và chính sách xác định signal không cần chuyển tiếp qua interrupt status; đây là ngoại lệ có chủ đích, không phải im lặng.
- **Đang xử lý một exception không liên quan tới interruption:** đừng tùy ý bật interrupt flag chỉ để "báo lỗi".
- **Chỉ muốn dừng một task khác:** không gọi `Thread.currentThread().interrupt()` để ngắt worker ở thread khác. Gọi `targetThread.interrupt()` hoặc cancellation API của task cần hủy.
- **Đang truyền một kết quả hủy qua cơ chế khác mà caller cần phân biệt:** có thể chọn một giao thức trả kết quả cụ thể, nhưng cần document rõ điều gì xảy ra với interrupt status ở ranh giới hiện tại.

Tuy nhiên, khi **đã catch `InterruptedException` do một lời gọi interruptible và không thể rethrow**, restore thường là **lựa chọn mặc định an toàn nhất** trừ khi contract nói rõ đã xử lý hoàn toàn.

## 25. Checklist review một catch `InterruptedException`

Trước khi chấp nhận code, tự hỏi:

1. **Câu lệnh nào ném `InterruptedException`?** API đó có clear interrupt flag khi ném không?
2. **Phương thức hiện tại có thể khai báo `throws InterruptedException` không?** Nếu có, ưu tiên propagate.
3. **Nếu không thể throws, đã gọi `Thread.currentThread().interrupt()` chưa?**
4. **Sau khi restore, execution path có kết thúc hoặc abort công việc đúng cách không?** Hay lại tiếp tục vòng chờ?
5. **Có cleanup cần thiết không?** Cleanup có block/interruptible không; restore trước hay sau được chọn có chủ đích không?
6. **Caller biết task bị hủy bằng cách nào?** Result/exception/future/state cần được document.
7. **Có side effect đã xảy ra trước interrupt không?** Retry hoặc rollback có yêu cầu idempotency không?
8. **Có nhầm caller interrupt với worker interrupt không?** `Future.get()` có thể ném trên thread đang đợi.
9. **Có dùng `Thread.interrupted()` làm mất flag không?** Nếu chỉ muốn kiểm tra, dùng `isInterrupted()`.
10. **Có blocking operation không hỗ trợ interrupt không?** Cần timeout/close riêng thay vì chỉ restore.
11. **Có thread pool tái sử dụng worker không?** Không dựa vào interrupt flag làm kênh completion cho task kế tiếp.
12. **Có kiểm thử cả interrupt đến sớm và đến trong lúc block không?** Dùng latch/condition điều phối, không dựa vào sleep phỏng đoán.
13. **Có tests chặn treo vô hạn không?** Với đường lỗi, dùng timeout ở test harness và shutdown cleanup rõ ràng.
14. **Status có được đọc ở đúng thời điểm không?** Để kiểm chứng restoration, đo trong chính worker trước khi task kết thúc, đừng dựa vào state hậu termination.

## 26. Câu hỏi tự kiểm tra

**1. Vì sao `Thread.sleep()` có thể khiến `Thread.currentThread().isInterrupted()` trả false trong `catch (InterruptedException e)`?**

Vì `sleep` xử lý interruption bằng cách ném `InterruptedException` và clear interrupt status theo hợp đồng. Nếu chưa xử lý hoàn toàn yêu cầu hủy, code catch nên restore trước khi nhường quyền.

**2. `Runnable.run()` có thể khai báo `throws InterruptedException` không?**

Không thể thêm checked exception đó khi override `Runnable.run()`. Trong `run` phải catch, restore rồi dừng hoặc dùng failure policy thích hợp.

**3. Tại sao `catch (...) { Thread.currentThread().interrupt(); }` chưa chắc đủ?**

Vì code vẫn có thể tiếp tục làm nghiệp vụ sau catch hoặc vào lại một blocking call. Cần thêm một đường `return`, `break` hoặc cancellation handling rõ.

**4. `Thread.interrupted()` và `isInterrupted()` khác nhau thế nào?**

`Thread.interrupted()` kiểm tra **current thread** và xóa status nếu đang bật. `isInterrupted()` đọc status của receiver mà không xóa.

**5. Nếu method đã `throws InterruptedException`, có cần catch để restore rồi throw tiếp không?**

Không cần mặc định. Truyền exception lên caller thường đủ để giữ tín hiệu cancellation. Restore thêm có thể là yêu cầu của contract cụ thể nhưng không phải quy tắc chung.

**6. Tại sao `Future.get()` ném `InterruptedException` không chứng minh worker đã bị interrupt?**

Vì ngoại lệ có thể xảy ra ở **caller đang chờ future**, trong khi task worker vẫn chạy. Cần phân biệt thread nào nhận interrupt.

**7. Restore interrupt flag có tự đánh thức một lời gọi I/O không hỗ trợ interruption không?**

Không. Cần hiểu hợp đồng I/O cụ thể và có thể cần timeout, close/cancel hoặc cơ chế khác.

**8. Cờ `AtomicBoolean stopRequested` có thay toàn bộ interruption được không?**

Không. Cờ hỗ trợ visibility của trạng thái do ứng dụng tự kiểm tra, không tự làm `BlockingQueue.take()` hay `Thread.sleep()` thức dậy.

**9. Sau khi restore flag, có nên tiếp tục retry cùng blocking operation vô hạn không?**

Thông thường không. Có thể tạo busy loop hoặc làm việc trái với yêu cầu hủy. Nên thoát hoặc chuyển sang policy cancellation đã document.

**10. Vì sao có thể cần restore **sau cleanup** thay vì ngay đầu catch?**

Vì một số cleanup có thể block và phản hồi ngay với interrupt status đang bật. Nếu có chủ đích, giữ lại thông tin interruption, thực hiện cleanup theo deadline/chính sách rồi restore trong finally.

## 27. Tổng kết

- **Interrupt là yêu cầu hợp tác**, không phải lệnh cưỡng ép dừng thread hay rollback công việc.
- Khi một API blocking ném `InterruptedException`, nhiều API chuẩn đã **clear interrupt flag**; nếu catch rồi bỏ qua, có thể đánh mất yêu cầu hủy.
- **Có thể propagate thì thường propagate.** Với `Runnable`, `Consumer`, callback hoặc method không cho thêm checked exception, **restore bằng `Thread.currentThread().interrupt()` rồi dừng/abort đúng contract**.
- **`isInterrupted()` đọc mà không clear; `Thread.interrupted()` đọc và clear current thread.** Không dùng nhầm.
- Restore flag **không tự kết thúc task**. Đường control flow phải hợp tác hủy; riêng blocking I/O cần policy thích hợp.
- Cleanup, timeout, exception propagation, trạng thái future và side effect đã xảy ra phải được thiết kế riêng; restore signal không giải quyết hết lifecycle.
- Không dựa vào lịch chạy hoặc `Thread.sleep` để test interruption. Dùng latch và timeout phù hợp; kiểm tra restoration trong worker và completion bằng cơ chế được bảo đảm.

Khi gặp `catch (InterruptedException e)` trong Java, câu hỏi trọng tâm là **"Ai chịu trách nhiệm xử lý yêu cầu hủy tiếp theo, và thông tin interrupt có được bảo toàn đến ranh giới đó không?"**. Nếu có thể truyền ngoại lệ, hãy truyền. Nếu không thể, **đặt lại interrupt flag trên current thread và thoát công việc theo giao thức rõ ràng**, thay vì vô tình nuốt tín hiệu.