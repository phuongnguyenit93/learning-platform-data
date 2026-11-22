# Interrupt là tín hiệu hợp tác, không phải dừng cưỡng bức trong Java

## 1. Mục tiêu và mô hình tư duy

Giả sử một thread đang tính toán lâu, một tác vụ đang chờ kết quả từ hàng đợi, hoặc một worker đang chờ khóa. Khi không cần công việc đó nữa, thread khác có thể gọi `interrupt()` để **yêu cầu** worker dừng hoặc hủy hoạt động đang thực hiện. Nhưng khác với một lệnh “kill process”, **`Thread.interrupt()` không cưỡng bức chấm dứt thread**.

Trong Java, interruption là một **giao thức hợp tác (cooperative cancellation)**: bên yêu cầu hủy phát tín hiệu; code chạy trong thread mục tiêu phải chủ động nhận diện tín hiệu và kết thúc theo một cách an toàn, hoặc API blocking mà nó gọi phải hỗ trợ interruption để giải phóng việc chờ.

Sau bài này, bạn sẽ:

- Phân biệt **gửi interrupt**, **trạng thái interrupt**, **phát sinh InterruptedException** và **thread thật sự kết thúc**.
- Dùng chính xác `interrupt()`, `isInterrupted()`, `Thread.interrupted()`, `Thread.currentThread()` và `join()`.
- Hiểu tại sao các API như `sleep()`, `wait()`, `join()`, `BlockingQueue.take()` hay `ReentrantLock.lockInterruptibly()` có thể phản ứng bằng `InterruptedException`.
- Chọn giữa **ném tiếp exception**, **khôi phục cờ bằng `Thread.currentThread().interrupt()`**, và **cleanup rồi thoát**.
- Thiết kế CPU-bound loops, blocking worker và executor tasks hỗ trợ hủy mà không mất dữ liệu hoặc tài nguyên.
- Phân biệt `Future.cancel(true)`, `shutdown()`, `shutdownNow()`, timeout và interrupt; không tuyên bố task đã dừng chỉ từ một yêu cầu.
- Biên dịch và chạy các ví dụ Java 17+ có thứ tự được kiểm soát bằng `CountDownLatch` và `join()`.

**Phạm vi:** Java SE/JVM concurrency nói chung; không phụ thuộc framework. Tất cả chương trình đầy đủ trong bài tương thích **JDK 17+**.

## 2. Interrupt là yêu cầu, không phải nút dừng cưỡng bức

Mỗi `Thread` có một **interrupted status** (trạng thái/cờ interrupt). Thread khác có thể gọi:

~~~java
worker.interrupt();
~~~

Lời gọi này **không tự bảo đảm** rằng `worker` chuyển ngay sang `TERMINATED`. Nó báo hiệu cho worker rằng có yêu cầu ngừng/hủy hoạt động hiện tại. Phản ứng thực tế phụ thuộc worker đang làm gì:

1. **Worker đang chạy CPU calculation không kiểm tra interrupt:** có thể tiếp tục chạy dù cờ đã được đặt.
2. **Worker chủ động kiểm tra `isInterrupted()`:** có thể thoát khỏi vòng lặp, rollback phần việc chưa commit hoặc cleanup rồi kết thúc.
3. **Worker đang chờ ở API interruptible:** API có thể thoát khỏi trạng thái chờ và ném `InterruptedException`; nhiều API clear cờ khi ném.
4. **Worker đang block ở API không hỗ trợ interruption:** có thể **không tỉnh dậy chỉ vì** interrupt; phải dùng timeout, đóng tài nguyên hoặc cơ chế cancel được API đó hỗ trợ.
5. **Worker đã hoàn thành:** gọi interrupt không đưa nó trở lại trạng thái chạy; không thể dùng interrupt để đảo ngược side effects đã xảy ra.

Bởi vậy, cần tách **ba sự kiện**:

~~~text
Thread điều phối             Thread worker
      │                           │
      ├─ worker.interrupt() ──────►│  1. nhận yêu cầu hủy (tín hiệu)
      │                           │
      │                           ├─ kiểm tra flag / API trả InterruptedException
      │                           │  2. phát hiện tín hiệu
      │                           │
      │                           ├─ cleanup / kết thúc an toàn
      │                           │  3. worker thật sự hoàn thành
      │                           ▼
      └─ worker.join() ◄───── TERMINATED
~~~

Lời gọi `interrupt()` là **request**; `join()` hoặc một cơ chế completion khác mới giúp caller biết thread đã thực sự kết thúc. Chúng không đồng nghĩa với nhau.

## 3. Ba API thường bị nhầm: interrupt, isInterrupted và interrupted

| API | Đối tượng tác động | Ý nghĩa | Có xóa cờ không? |
|---|---|---|---|
| `someThread.interrupt()` | Thread được tham chiếu bởi `someThread` | Gửi yêu cầu interrupt, tùy trạng thái có thể khiến API blocking phản ứng | Không phải phương thức kiểm tra/clear cờ; API blocking có thể clear trong lúc ném exception |
| `someThread.isInterrupted()` | Thread `someThread` | Kiểm tra trạng thái interrupt hiện tại | **Không** |
| `Thread.interrupted()` | **Thread đang gọi** phương thức static | Kiểm tra cờ interrupt của thread hiện tại | **Có**, clear cờ khi kiểm tra |

`Thread.interrupted()` là **static method** và **không** kiểm tra một thread bất kỳ. Kể cả khi viết `worker.interrupted()` (Java cho phép gọi static qua reference nhưng gây hiểu nhầm), method vẫn kiểm tra **current thread**, không phải worker. Luôn viết `Thread.interrupted()` khi thật sự muốn kiểm tra **và clear** interrupt flag của current thread.

Ví dụ ngắn:

~~~java
Thread me = Thread.currentThread();
me.interrupt();

System.out.println(me.isInterrupted());  // true
System.out.println(Thread.interrupted()); // true; đồng thời clear
System.out.println(me.isInterrupted());  // false
~~~

Đoạn mã trên là **minh họa chạy trong một method**. Nó giả định không có interrupt mới đến giữa các lời gọi. Đừng vô tình clear interrupt flag của thread thực hiện test trong framework hoặc worker pool trừ khi đó là một phần có chủ đích của giao thức xử lý.

### Câu hỏi quan trọng

**Nếu worker chỉ gọi isInterrupted() mà không clear, cờ có còn không?** Có, miễn không có hoạt động khác clear hoặc thay đổi trạng thái. Worker có thể nhận biết yêu cầu ở nhiều điểm kiểm tra.

**Nếu code gọi Thread.interrupted() trong một vòng, cờ có còn ở lần sau?** Lần gọi đầu có thể trả true rồi clear. Nếu không có interrupt tiếp theo, lần gọi sau trả false; nếu code không thoát ngay khi thấy true, nó có thể **vô tình tiếp tục** hoạt động như chưa bị yêu cầu hủy.

## 4. Interruption khi đang chạy CPU-bound work

Một vòng tính toán không đi qua API blocking sẽ **không tự dừng** khi caller gọi `interrupt()`. Tác vụ cần **định kỳ kiểm tra** cờ và dừng theo chính sách của nó.

~~~java
long compute(long items) throws InterruptedException {
    long sum = 0;
    for (long i = 0; i < items; i++) {
        if (Thread.currentThread().isInterrupted()) {
            throw new InterruptedException("Calculation cancelled");
        }
        sum += i;
    }
    return sum;
}
~~~

Đây là một **method minh họa**, không phải chương trình độc lập. Điểm đáng chú ý:
- Worker không chờ JVM “giết” mình; nó tự kiểm tra điều kiện hủy.
- Dùng `isInterrupted()` để kiểm tra **không clear** cờ.
- Ném `new InterruptedException(...)` thủ công **không tự clear** interrupt flag. Việc clear cờ là đặc tính của những blocking operations cụ thể ném InterruptedException, không phải phép màu của constructor exception. Caller cần có protocol rõ ràng.
- Nếu vòng lặp chạy quá nhanh, có thể không cần kiểm tra từng iteration; kiểm tra theo từng batch có thể giảm overhead, nhưng tăng độ trễ phản ứng hủy. Chọn theo workload và deadline.
- Tác vụ phải tránh commit một phần kết quả chưa nhất quán. Nếu đã thay đổi tài nguyên bên ngoài, interrupt không rollback những thay đổi đó.

### Ví dụ độc lập 1: CPU-bound loop dừng khi tự kiểm tra interrupt

Lưu tệp **CooperativeCpuDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

public class CooperativeCpuDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch started = new CountDownLatch(1);
        AtomicBoolean noticed = new AtomicBoolean(false);

        Thread worker = new Thread(() -> {
            started.countDown();
            while (true) {
                if (Thread.currentThread().isInterrupted()) {
                    noticed.set(true);
                    return;
                }
                Thread.onSpinWait();
            }
        }, "cpu-worker");

        worker.start();
        started.await();
        worker.interrupt();
        worker.join();

        System.out.println("noticed=" + noticed.get());
        System.out.println("alive=" + worker.isAlive());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac CooperativeCpuDemo.java
java CooperativeCpuDemo
~~~

Output trong điều kiện hoạt động bình thường:

~~~text
noticed=true
alive=false
~~~

**Phân tích:**

1. `started.await()` bảo đảm worker đã bắt đầu thực thi. Nó **không** bắt worker phải chạy đủ số vòng; đây chỉ là tín hiệu bắt đầu.
2. Main gọi `worker.interrupt()`. Nếu worker đang ở vòng lặp, `isInterrupted()` của nó cuối cùng thấy true; nếu interrupt đến ngay sau countDown và trước lượt kiểm tra đầu tiên, lượt đầu cũng thấy true.
3. Worker **tự return** khỏi Runnable, không bị Thread.interrupt cưỡng bức kết thúc.
4. `worker.join()` chờ thread hoàn tất rồi main in; vì vậy cả hai dòng không phụ thuộc thứ tự chạy giữa main và worker.
5. `Thread.onSpinWait()` chỉ là gợi ý cho vòng đợi ngắn, không phải cơ chế dừng hoặc đồng bộ. Trong production, tránh busy spin dài; ví dụ cố tình đơn giản để làm rõ interrupt flag.

**Điểm học tập:** Nếu bỏ câu `if (isInterrupted())` và không có điều kiện thoát nào khác, worker có thể tiếp tục chạy mãi dù main đã gọi interrupt. Đó là lý do gọi interrupt **không phải cưỡng bức dừng**.

## 5. InterruptedException: API blocking phản ứng như thế nào?

Nhiều API chờ theo hợp đồng Java phản ứng với interruption bằng `InterruptedException`. Các trường hợp quen thuộc:

| API | Khi bị interrupt trong pha chờ | Lưu ý |
|---|---|---|
| `Thread.sleep(...)` | Ném `InterruptedException` | Không nhả intrinsic monitor đang giữ; cờ được clear khi ném. |
| `Object.wait(...)` | Ném `InterruptedException` khi có interrupt theo hợp đồng | Wait sử dụng monitor và nhả monitor trong lúc chờ; phải lấy lại trước khi tiếp tục xử lý. |
| `Thread.join(...)` | Ném `InterruptedException` ở **thread đang join** | Không nhất thiết ngắt thread được join. |
| `CountDownLatch.await()` | Ném `InterruptedException` | Mục đích đợi latch, không đảm bảo tác vụ đích dừng. |
| `BlockingQueue.take()/put()` | Ném `InterruptedException` nếu bị hủy khi đang chờ | Có thể dùng vòng đời producer/consumer rõ ràng. |
| `ReentrantLock.lockInterruptibly()` | Ném `InterruptedException` trong lúc chờ lock | Khác `lock()` không ném checked exception trong pha acquire. |
| `ReentrantLock.tryLock(timeout, unit)` | Có thể ném `InterruptedException` | Phân biệt bị hủy với trả `false` do timeout. |
| `Future.get()` | Có thể ném `InterruptedException` ở **caller đang chờ** | Không đồng nghĩa Future task đã bị hủy. |

**Cần đọc hợp đồng từng API:** không phải mọi block đều interruptible. Một số kênh I/O từ `java.nio.channels.InterruptibleChannel` phản ứng bằng cách đóng channel và ném `ClosedByInterruptException` (thuộc `IOException`), chứ không nhất thiết bằng `InterruptedException`. Các socket/I/O, native calls, filesystem và thư viện bên ngoài có thể có hành vi khác nhau theo loại API và bản JDK. Không được hứa “interrupt luôn đánh thức mọi blocking call”.

### Khi InterruptedException được ném, cờ thường đã bị clear

Ví dụ với `Thread.sleep`:

~~~java
try {
    Thread.sleep(60_000);
} catch (InterruptedException e) {
    System.out.println(Thread.currentThread().isInterrupted());
    // false đối với trường hợp sleep đã clear cờ trước khi ném
}
~~~

Đây là đoạn method minh họa. Việc clear cờ cho phép caller **quyết định tiếp**: ném lại để truyền yêu cầu hủy lên trên; hoặc khôi phục cờ và kết thúc khi interface không cho phép ném checked exception.

Không phát biểu máy móc rằng “mọi API ném InterruptedException đều luôn clear flag đúng cùng một thời điểm” mà không đọc contract. Nhưng các API JDK phổ biến như `sleep`, `wait` và `join` có quy định rõ về việc clear khi ném.

## 6. Xử lý InterruptedException: ném tiếp, restore flag, hoặc thoát

### Cách A — Ném tiếp khi chữ ký cho phép

~~~java
void fetchWork(java.util.concurrent.BlockingQueue<String> queue)
        throws InterruptedException {
    String item = queue.take();
    process(item);
}
~~~

Đây là method minh họa; `process(item)` là logic do ứng dụng định nghĩa. Khi `take()` bị interrupt trong lúc chờ, exception truyền về caller. Caller có thể quyết định hủy tác vụ, log hoặc shutdown; không cần nuốt exception rồi âm thầm chạy tiếp.

### Cách B — Khôi phục cờ nếu không thể ném checked exception

Một `Runnable.run()` không khai báo `throws InterruptedException`:

~~~java
@Override
public void run() {
    try {
        workQueue.take();
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt(); // khôi phục tín hiệu
        return; // chấm dứt tác vụ hoặc thoát vòng xử lý
    }
}
~~~

Đây là đoạn trích trong một class có `BlockingQueue<?> workQueue`. Sau khi `take()` ném exception và clear cờ, gọi `currentThread().interrupt()` bảo tồn thông tin hủy cho tầng trên. `return` cho thấy tác vụ **chọn dừng** thay vì tiếp tục.

### Cách C — Cleanup tài nguyên trong finally

~~~java
void processOneTask() throws InterruptedException {
    Resource resource = acquireResource();
    try {
        performInterruptibleWork(resource);
    } finally {
        resource.close();
    }
}
~~~

Đoạn trên giả định `Resource`, `acquireResource` và `performInterruptibleWork` do ứng dụng định nghĩa và `close()` phù hợp với chữ ký. Ý tưởng là tài nguyên đã acquire phải được giải phóng kể cả khi `InterruptedException` thoát khỏi phương thức. Cần xác định hành vi nếu cleanup tự ném exception; có thể dùng `try-with-resources` với tài nguyên implements `AutoCloseable` để quản lý suppressed exceptions.

**Tại sao không “catch rồi bỏ qua”?**

~~~java
while (true) {
    try {
        taskQueue.take();
    } catch (InterruptedException ignored) {
        // Sai khi shutdown cần dừng: cứ quay lại đợi như không có tín hiệu.
    }
}
~~~

Nếu `take` clear flag, vòng lặp lặp lại và tiếp tục chờ; caller đã yêu cầu hủy nhưng worker có thể **bỏ qua hoàn toàn**. Đôi khi ứng dụng có lý do cụ thể để bỏ qua interruption và hoàn thành một thao tác bắt buộc, nhưng phải **document policy**, thường khôi phục interrupt flag trước khi thoát vùng không thể bị hủy. Mặc định, không nuốt tín hiệu.

## 7. Ví dụ độc lập 2: sleep ném exception và clear cờ

Chương trình chủ động bảo đảm worker đã đến sát điểm chờ bằng latch. Main interrupt worker. Dù interrupt đến **trước** khi worker thực hiện sleep hay khi nó đang sleep, lời gọi `sleep` sẽ ném `InterruptedException` trong điều kiện này.

Lưu tệp **InterruptedSleepDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

public class InterruptedSleepDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch started = new CountDownLatch(1);
        AtomicBoolean caught = new AtomicBoolean();
        AtomicBoolean clearedInCatch = new AtomicBoolean();
        AtomicBoolean restoredInCatch = new AtomicBoolean();

        Thread worker = new Thread(() -> {
            started.countDown();
            try {
                Thread.sleep(60_000);
            } catch (InterruptedException e) {
                caught.set(true);
                clearedInCatch.set(!Thread.currentThread().isInterrupted());
                Thread.currentThread().interrupt();
                restoredInCatch.set(Thread.currentThread().isInterrupted());
            }
        }, "sleep-worker");

        worker.start();
        started.await();
        worker.interrupt();
        worker.join();

        System.out.println("caught=" + caught.get());
        System.out.println("cleared=" + clearedInCatch.get());
        System.out.println("restored=" + restoredInCatch.get());
        System.out.println("alive=" + worker.isAlive());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac InterruptedSleepDemo.java
java InterruptedSleepDemo
~~~

Output kỳ vọng, khi không có interrupt ngoài hoặc thao tác khác can thiệp:

~~~text
caught=true
cleared=true
restored=true
alive=false
~~~

Phân tích:

1. Worker phát `started.countDown()` ngay trước sleep, nên main biết worker đã vào Runnable. `started` không phải tín hiệu rằng worker chắc chắn đang ở trạng thái `TIMED_WAITING`.
2. Nếu interrupt đến trước sleep, cờ đã được set; khi sleep kiểm tra interrupted status, nó ném exception. Nếu worker đã sleep, interrupt đánh thức nó qua exception.
3. `Thread.sleep` clear interrupt status khi ném `InterruptedException`, vì vậy `isInterrupted()` ở đầu catch là false và biến `clearedInCatch` được ghi true.
4. Worker gọi `Thread.currentThread().interrupt()` để khôi phục tín hiệu, rồi `isInterrupted()` trả true.
5. Main dùng `join()`, nên các biến đã được worker ghi được quan sát sau khi kết thúc. `AtomicBoolean` là lựa chọn minh họa dễ đọc, không phải vì `join()` tự thiếu visibility.

**Giới hạn:** Trong môi trường sản xuất, không nên phụ thuộc vào một `sleep(60_000)` chỉ để mô phỏng synchronization. Ở đây thời lượng dài là cách minh họa API; chương trình dựa vào latch/interrupt/join, **không** dựa vào chờ hết 60 giây.

## 8. join(), interrupted status và hành động của thread đang đợi

Giả sử main gọi:

~~~java
worker.join();
~~~

Điều này yêu cầu **main đợi worker kết thúc**. Nếu thread khác interrupt **main** trong khi main chờ join, `join` có thể ném `InterruptedException` trong main; nó không có nghĩa worker tự động bị dừng.

Trong mã điều phối, cần suy nghĩ:
- Có muốn hủy worker khi main bị interrupt không? Nếu có, chủ động gọi `worker.interrupt()` hoặc hủy task theo protocol.
- Có cần chờ worker cleanup trước khi thoát? Có thể chờ theo deadline, nhưng phải xử lý trường hợp chính thread điều phối đã bị interrupt.
- Có thể rời bỏ quyền sở hữu task không? Một worker non-daemon không được quản lý có thể vẫn giữ process sống.
- Nếu caller quyết định ném tiếp InterruptedException từ join, tác vụ đích vẫn có thể tiếp tục nếu không có yêu cầu hủy riêng.

`join()` có memory consistency/happens-before cho trường hợp thread được join đã hoàn tất, nhưng **không phải cơ chế cưỡng bức hủy**.

## 9. Interrupt và thao tác chờ trong synchronized, Lock, Condition

### 9.1. synchronized không hỗ trợ hủy khi đang chờ lấy monitor

Một thread đang cố vào:

~~~java
synchronized (sharedLock) {
    updateState();
}
~~~

nếu monitor đang do thread khác giữ, việc gọi interrupt trên thread đang **tranh monitor** không làm JVM tự ném `InterruptedException` và rời bỏ yêu cầu lấy monitor. Interrupted status có thể được ghi nhận, nhưng thread vẫn cần acquire monitor trước khi thực thi block theo hợp đồng của intrinsic monitor.

**Đừng nhầm** với `Object.wait()`: `wait` được gọi **bên trong vùng synchronized** và là một API chờ interruptible; khi wait, thread nhả monitor trong lúc chờ và phải lấy lại trước khi tiếp tục. Hai pha “chờ để **vào** monitor” và “đang ở monitor rồi gọi `wait`” khác nhau.

### 9.2. ReentrantLock hỗ trợ pha acquire có thể hủy

~~~java
import java.util.concurrent.locks.ReentrantLock;

void work(ReentrantLock lock) throws InterruptedException {
    lock.lockInterruptibly();
    try {
        updateState();
    } finally {
        lock.unlock();
    }
}
~~~

Đây là method minh họa; `updateState()` thuộc ứng dụng. `lockInterruptibly()` cho phép thread dừng **pha đợi lock** bằng `InterruptedException`. Chỉ vào `try/finally` sau khi lock được acquire thành công, nên không gọi `unlock()` nếu acquisition thất bại do interrupt.

Đối với `tryLock(timeout, unit)`, cần phân biệt:
- Trả `true`: đã acquire lock, phải unlock sau khi xong.
- Trả `false`: hết thời gian chờ mà không acquire được.
- Ném `InterruptedException`: bị hủy trong pha chờ, **không phải** kết quả timeout thông thường.

### 9.3. Condition.await có thể bị interrupt

Với `Condition` tạo từ `Lock`, `await()` là cơ chế chờ có thể bị interrupt. Code cần đặt điều kiện trong vòng lặp `while` để xử lý spurious wakeup và thay đổi trạng thái cạnh tranh. Khi `await()` trả/throw, thread đã được yêu cầu reacquire lock theo hợp đồng của Condition trước khi rời await; các khía cạnh cụ thể của API cần được đọc khi xây dựng protocol. Đừng viết một vòng gọi `sleep` bên trong monitor để thay thế Condition, vì `sleep` không nhả monitor đang giữ.

## 10. Future.cancel(true): thử hủy task, không bảo đảm Thread đã chết

Trong `ExecutorService`, caller thường không nắm trực tiếp Thread chạy tác vụ. Thay vào đó, caller giữ `Future`:

~~~java
Future<?> future = executor.submit(task);
boolean requested = future.cancel(true);
~~~

Hợp đồng cơ bản:
- `cancel(true)` **cố gắng hủy** Future. Nếu task đã chạy, khi biết worker thread, executor có thể interrupt thread để yêu cầu dừng.
- `cancel(false)` không yêu cầu interrupt task đang chạy, nhưng có thể ngăn task chưa khởi động được thực thi.
- `Future.isCancelled()` phản ánh Future đã ở trạng thái cancelled theo contract, **không chứng minh** side effects của worker đã dừng hoặc cleanup xong tại đúng thời điểm đó.
- `future.get()` sau khi Future thực sự cancelled có thể ném `CancellationException`; không phải vì task “trả về” exception đó như kết quả bình thường.
- `future.get(timeout, unit)` hết thời gian chờ trả kết quả sẽ ném `TimeoutException`; **timeout khi đợi kết quả không tự động hủy task**. Nếu muốn hủy, caller phải quyết định gọi `cancel(...)`.
- Với những API không nhận biết interrupt, worker có thể không phản hồi kịp hoặc tiếp tục làm side effects sau khi Future bị đánh dấu cancelled.

### Ví dụ mô hình code

~~~java
java.util.concurrent.ExecutorService pool =
        java.util.concurrent.Executors.newSingleThreadExecutor();

java.util.concurrent.Future<?> future = pool.submit(() -> {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            performOneStep();
        }
    } finally {
        cleanupResources();
    }
});

try {
    future.get(500, java.util.concurrent.TimeUnit.MILLISECONDS);
} catch (java.util.concurrent.TimeoutException e) {
    future.cancel(true); // yêu cầu hủy, không phải cưỡng bức chấm dứt
} finally {
    pool.shutdown();
}
~~~

Đây là **đoạn tích hợp**: `performOneStep()` và `cleanupResources()` là hàm ứng dụng; cần xử lý `InterruptedException` và `ExecutionException` của `Future.get` theo contract ở phương thức bao quanh. Điều quan trọng là `performOneStep()` phải có chiến lược thoát khi bị interrupt hoặc có timeout riêng; vòng kiểm tra chỉ chạy **sau khi** nó trả về.

Trong production, sau `shutdown()` có thể cần `awaitTermination` có deadline và fallback `shutdownNow`, cùng báo cáo nếu còn tác vụ chưa kết thúc. Đừng dựa vào một Future cancelled để cam kết mọi file/connection đã được đóng.

## 11. Ví dụ độc lập 3: cancel Future, worker tự xử lý interrupt

Ví dụ này dùng `CountDownLatch` để biết task đã chạy, rồi gọi `cancel(true)`. Worker đang chờ bằng `Thread.sleep()`; khi bị interrupt, nó đi vào catch, ghi nhận yêu cầu hủy và kết thúc. Caller không dùng `Future.get()` để chứng minh cleanup; thay vào đó dùng một latch kết thúc riêng.

Lưu **FutureCancellationDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class FutureCancellationDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        AtomicBoolean detected = new AtomicBoolean(false);

        try {
            Future<?> future = pool.submit(() -> {
                try {
                    started.countDown();
                    Thread.sleep(60_000);
                } catch (InterruptedException e) {
                    detected.set(true);
                    Thread.currentThread().interrupt();
                } finally {
                    finished.countDown();
                }
            });

            started.await();
            boolean cancelled = future.cancel(true);
            finished.await();

            System.out.println("cancelled=" + cancelled);
            System.out.println("futureCancelled=" + future.isCancelled());
            System.out.println("workerDetected=" + detected.get());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac FutureCancellationDemo.java
java FutureCancellationDemo
~~~

Output khi task chưa hoàn tất trước yêu cầu hủy và không có interruption bên ngoài:

~~~text
cancelled=true
futureCancelled=true
workerDetected=true
~~~

**Cách lập luận:**
1. `started.await()` cho main biết task đã chạy tới điểm báo hiệu. Worker chuẩn bị `sleep()`, có thể đã ngủ hoặc chưa.
2. `future.cancel(true)` yêu cầu interrupt worker khi task đang chạy. Trong tình huống này, `sleep` phát hiện interrupt dù tín hiệu đến trước hay trong lúc ngủ, rồi ném `InterruptedException`.
3. Worker bắt exception, ghi `detected=true`, khôi phục cờ và gọi `finished.countDown()` trong finally.
4. `finished.await()` bảo đảm caller **chờ logic cleanup trong Runnable đã đi qua finally**; điều này cung cấp sự quan sát ổn định cho biến detected. Cũng cần phân biệt `finished.countDown()` với thread pool worker thực sự kết thúc: pool có thể giữ worker để thực hiện task tiếp theo.
5. `pool.shutdown()` ngừng nhận task mới; `awaitTermination` giới hạn thời gian chờ executor đóng. `shutdownNow()` chỉ nỗ lực ngắt các worker còn chạy, không cưỡng bức kết thúc mọi task.

**Lưu ý về lịch chạy:** Nếu nguồn tác vụ cực ngắn đã hoàn tất **trước** khi caller `cancel(true)`, `cancel` có thể trả false. Ví dụ cố định lựa chọn tác vụ sleep dài và latch bắt đầu nên trong thực thi bình thường task chưa thể hoàn thành trước khi main yêu cầu hủy. Đây không phải benchmark hay cam kết định thời tuyệt đối trên mọi môi trường.

## 12. ExecutorService.shutdown và shutdownNow khác nhau

| API | Ý nghĩa | Có interrupt các task đang chạy? |
|---|---|---|
| `shutdown()` | Ngừng nhận tác vụ mới; các task đã submit tiếp tục theo chính sách executor | **Không** yêu cầu interrupt chỉ do shutdown |
| `shutdownNow()` | Nỗ lực ngừng các task đang chạy và ngăn/thu hồi task chưa khởi động | **Thường** dùng interrupt, nhưng không cam kết mọi task lập tức dừng |
| `awaitTermination(timeout, unit)` | Chờ executor kết thúc tối đa thời gian định trước | Không tự thực hiện cancellation của worker |
| `Future.cancel(true)` | Yêu cầu hủy **một task** và có thể interrupt thread đang chạy task đó | Có, khi khả thi và task còn chạy |
| `Future.cancel(false)` | Yêu cầu hủy nhưng không cố interrupt thread đang chạy | Không |

`shutdownNow()` trả về danh sách những task đang chờ chưa bắt đầu trong executor phù hợp. Nó **không phải danh sách toàn bộ tác vụ chưa hoàn tất** trong mọi ý nghĩa nghiệp vụ. Một số task đang chạy vẫn có thể tiếp tục nếu không phản hồi interrupt.

### Một mẫu shutdown có deadline

~~~java
pool.shutdown();
try {
    if (!pool.awaitTermination(3, TimeUnit.SECONDS)) {
        pool.shutdownNow();
        if (!pool.awaitTermination(3, TimeUnit.SECONDS)) {
            System.err.println("Some tasks did not terminate");
        }
    }
} catch (InterruptedException e) {
    pool.shutdownNow();
    Thread.currentThread().interrupt();
}
~~~

Đây là **đoạn trích** bên trong method có `ExecutorService pool` và import `TimeUnit`, phù hợp hướng dẫn shutdown executor thường gặp trong JDK. Việc giữ lại interrupt status của thread điều phối khi bắt InterruptedException là quan trọng; song cũng phải ghi nhận nếu worker vẫn không kết thúc. Một chính sách production có thể dùng deadline toàn cục thay vì hai khoảng chờ độc lập.

## 13. Timeout và interrupt không phải cùng một điều

Một thread có thể muốn dừng vì:
- **Interrupt:** một bên khác chủ động gửi yêu cầu hủy.
- **Timeout:** một phép chờ vượt quá thời gian giới hạn.
- **Business cancellation:** trạng thái nghiệp vụ không còn yêu cầu thực thi.
- **Shutdown:** lifecycle executor/application đang kết thúc.

Các trường hợp có thể liên quan nhau nhưng không giống nhau:
- `Future.get(100, MILLISECONDS)` ném `TimeoutException` chỉ cho biết **caller đã chờ quá thời hạn**, không nói task đã bị hủy.
- `Thread.sleep(100)` hoàn tất bình thường vì đủ thời gian ngủ không có nghĩa thread nhận yêu cầu hủy.
- `lock.tryLock(100, MILLISECONDS)` trả false nghĩa là **không lấy được lock trong hạn**, không phải do thread bị interrupt. Nếu bị interrupt, nó có thể ném `InterruptedException`.
- `Future.cancel(true)` có thể đánh dấu Future cancelled, nhưng các side effects đã thực hiện không tự rollback.
- `Thread.interrupt()` có thể phát tín hiệu ngay cả khi worker chưa tới điểm kiểm tra, và việc phát hiện/dừng có độ trễ.

Để yêu cầu deadline **toàn nghiệp vụ**, cần truyền ngân sách thời gian qua nhiều bước, đặt timeout tương ứng cho I/O, hàng đợi, khóa và phần xử lý cần thiết. Một interrupt flag riêng không cung cấp deadline thời gian thực.

## 14. Thread.stop không phải giải pháp thay thế

`Thread.stop()` là API không an toàn đã bị loại khỏi thực hành hiện đại và trong JDK hiện hành bị đánh dấu/triển khai theo hướng **không còn hỗ trợ**; với JDK 17+, không dùng nó để cưỡng bức thread ngừng. Lý do căn bản của việc dừng bất đồng bộ là có thể phá vỡ bất biến dữ liệu khi code đang giữ tài nguyên hoặc đang cập nhật một nửa trạng thái.

`Thread.suspend()`/`resume()` cũng không phải cách hủy đáng tin: có thể làm treo thread đang sở hữu monitor, gây deadlock. Không xây dựng cơ chế hủy bằng các API nguy hiểm/đã deprecated này.

Giải pháp chuẩn là **cooperative cancellation**:
1. Task có điều kiện hủy được kiểm tra tại những điểm an toàn.
2. Blocking operation phải có đường interrupt/timeout/cancel phù hợp.
3. Task có cleanup và giao thức hoàn tất rõ ràng.
4. Caller đợi completion hoặc xử lý tình huống task chưa dừng sau deadline.

## 15. Interrupt và trạng thái thread không phải một bản đồ một-một

Các trạng thái `NEW`, `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING` và `TERMINATED` mô tả trạng thái execution/thread-lifecycle ở mức JVM. **Interrupted status là một thuộc tính khác**. Một thread có thể:
- Ở `RUNNABLE` với interrupted status true mà vẫn đang tính toán.
- Bị interrupt khi đang `TIMED_WAITING` ở sleep và đi qua InterruptedException.
- Chờ lấy monitor intrinsic (`BLOCKED`), nhận interrupt request nhưng vẫn phải chờ monitor.
- Đã xử lý interrupt và thoát khỏi Runnable, chuyển `TERMINATED` sau khi cleanup.

`interrupt()` không phải một lệnh “setState(TERMINATED)”. Khi debug, nhìn cả stack trace, trạng thái interrupt, điều kiện chờ và nơi xử lý exception; chỉ thấy `isInterrupted()==true` không chứng minh nhiệm vụ đã kết thúc.

### Lưu ý với virtual threads trong Java 21+

Virtual threads cũng là `Thread` và có interrupt status, nên các quy tắc cooperative cancellation của Java vẫn áp dụng. Nhưng khả năng một hoạt động blocking cụ thể phản ứng/thoát nhanh phụ thuộc API và phiên bản JDK, không phải mọi I/O, native call hay thư viện đều có cùng cách xử lý.

Virtual thread là daemon theo đặc tính thiết kế; vì vậy nếu ứng dụng tạo nhiều virtual threads nhưng không có cơ chế chờ task hoàn tất, JVM có thể kết thúc trước khi các task hoàn thành. Interrupt không thay thế `Future.get`, `join`, structured lifecycle hoặc đóng executor có kiểm soát. Ví dụ trong bài dùng Java 17+ platform threads để tập trung vào ngữ nghĩa chung của Thread API.

## 16. Hủy ở ranh giới tài nguyên và tính đúng của nghiệp vụ

Cooperative cancellation không đơn giản là “bất cứ khi nào có interrupt thì return ngay”. Bạn cần xác định **safe cancellation point**:

- **Trước khi bắt đầu bước có side effect:** có thể kiểm tra cờ và bỏ qua công việc nếu chưa có gì commit.
- **Trong lúc chờ tài nguyên:** dùng API interruptible và cleanup ownership đúng (không unlock nếu chưa acquire; không release permit nếu chưa lấy).
- **Trong critical section:** phải giữ invariant; không return giữa việc cập nhật hai field mà để trạng thái nửa chừng.
- **Sau khi đã commit side effect ra ngoài:** interrupt không tự rollback email đã gửi, file đã ghi hay giao dịch đã commit. Cần idempotency/compensation protocol riêng nếu muốn hủy nghiệp vụ.
- **Khi giữ lock:** dùng `finally` để unlock kể cả khi exception; tránh hủy bỏ nửa chừng mà không dọn tài nguyên.

Ví dụ với semaphore:

~~~java
boolean acquired = false;
try {
    semaphore.acquire();       // có thể bị interrupt trước khi lấy permit
    acquired = true;
    performWork();             // logic ứng dụng
} finally {
    if (acquired) {
        semaphore.release();   // chỉ trả permit mình đã lấy
    }
}
~~~

Đây là **đoạn trích** trong method có `Semaphore semaphore` và `performWork()`, method cần khai báo/handle InterruptedException. Tại sao dùng biến `acquired`? Nếu `acquire` ném InterruptedException **trước khi được cấp permit**, code không được release permit của thread khác. Cùng nguyên tắc áp dụng cho `ReentrantLock.lockInterruptibly()`: chỉ unlock sau khi đã acquire.

### Không ép hard stop với tài nguyên chung

Trong một hệ thống nhiều threads, việc một thread bị buộc dừng giữa lúc giữ monitor hoặc thay đổi state có thể làm các threads khác quan sát trạng thái bất nhất hoặc chờ mãi. Thiết kế cancellation tốt luôn kèm **ownership + cleanup + completion protocol**, không chỉ flag.

## 17. Tránh các lỗi phổ biến

**Lỗi 1 — Gọi interrupt là coi worker đã dừng.** Không có bảo đảm. Cần worker hợp tác và caller quan sát completion bằng join/Future/latch thích hợp.

**Lỗi 2 — Catch InterruptedException rồi để trống.** Nhiều API clear cờ trước khi throw; nuốt exception có thể khiến worker tiếp tục vô hạn và bỏ qua yêu cầu hủy.

**Lỗi 3 — Gọi Thread.interrupted() thay isInterrupted() trong polling rồi tiếp tục.** Static method clear cờ. Nếu không thoát ngay, tín hiệu bị mất.

**Lỗi 4 — Nghĩ `Thread.interrupted()` kiểm tra object đứng trước dấu chấm.** Đây là static method kiểm tra current thread, không phải Thread tùy ý.

**Lỗi 5 — Nghĩ `Thread.sleep()` dừng được worker đang tranh synchronized monitor.** Sleep không nhả monitor đang giữ và không làm acquire intrinsic lock trở thành interruptible.

**Lỗi 6 — Quên finally khi một blocking method bị hủy.** Tài nguyên đã lấy trước đó có thể bị giữ, gây leak hoặc deadlock.

**Lỗi 7 — Gọi unlock/release khi acquire bị interrupt trước thành công.** Có thể ném IllegalMonitorStateException hoặc tăng permit sai; theo dõi ownership đúng.

**Lỗi 8 — Dùng Future.isCancelled như chứng cứ side effects đã chấm dứt.** Future cancellation và actual worker termination là hai mốc khác nhau.

**Lỗi 9 — Cho rằng get(timeout) timeout sẽ hủy task.** Timeout chỉ áp dụng cho caller đợi kết quả. Muốn hủy, cần cancel và protocol worker phù hợp.

**Lỗi 10 — Retry vô hạn sau interrupt.** Tác vụ bị yêu cầu hủy có thể không bao giờ dừng; cần kiểm tra cancellation/deadline và không retry theo cách bỏ tín hiệu.

**Lỗi 11 — Dùng interrupt để xử lý một API không hỗ trợ interrupt.** Đọc contract cụ thể; dùng timeout, close hoặc cancellation hook đúng loại tài nguyên.

**Lỗi 12 — Dùng Thread.stop hoặc suspend/resume.** Chúng không bảo đảm trạng thái/tài nguyên an toàn và không phải cách quản lý concurrency hiện đại.

**Lỗi 13 — Nghĩ sleep/yield tạo happens-before.** Không. Đồng bộ visibility cần Lock/volatile/latch/join/Future hoặc protocol JMM thích hợp.

**Lỗi 14 — Cho rằng khôi phục cờ và tiếp tục tính vô hạn là đã xử lý hủy.** Restore giúp bảo tồn tín hiệu, nhưng còn phải **thoát/chuyển quyết định**. Nếu code tiếp tục bỏ qua flag, cancellation vẫn không diễn ra.

**Lỗi 15 — Lẫn interrupt giữa caller và callee.** Nếu main bị interrupt trong `future.get`, task không mặc nhiên bị hủy; nếu worker bị interrupt thì main không nhất thiết nhận InterruptedException của chính main.

**Lỗi 16 — Hủy giữa nhiều cập nhật nghiệp vụ rồi mặc định rollback.** Interrupt không phải transaction. Các bất biến và cơ chế compensation cần thiết kế riêng.

## 18. Quy trình thiết kế cancellation an toàn

~~~text
Caller không cần kết quả nữa
       |
       v
Yêu cầu cancel: worker.interrupt() / future.cancel(true)
       |
       v
Worker có điểm kiểm tra hay API chờ interruptible?
       |                         \
      Có                          Không
       |                           |
       v                           v
Phát hiện tín hiệu           Có thể tiếp tục chạy
       |                    → cần timeout/close/cancel hook
       v
Dừng ở safe point, giữ invariant
       |
       v
finally/try-with-resources cleanup
       |
       v
Runnable/Callable thực sự kết thúc
       |
       v
Caller đợi/ghi nhận completion và kiểm tra outcome
~~~

Tại từng bước, hỏi thêm:

1. **Ai sở hữu task?** Caller có còn giữ Thread/Future để yêu cầu hủy và quan sát kết thúc không?
2. **Ai có quyền interrupt?** Có thể người điều phối chỉ được phát yêu cầu theo contract của executor, không nên tự interrupt thread pool workers tùy tiện.
3. **Task đang làm CPU hay chờ blocking?** CPU work cần polling định kỳ; blocking work cần API hỗ trợ interrupt/timeout.
4. **Khi bắt InterruptedException thì sao?** Ném tiếp, restore flag và return, hay xử lý chính sách cụ thể có lý do?
5. **Tài nguyên nào cần cleanup?** Lock, permit, stream, file, connection, temp state.
6. **Các side effects đã commit chưa?** Có cần idempotency, compensation hay kết quả “partial success” không?
7. **Ai chờ hoàn tất?** Có deadline và logic khi worker vẫn chạy sau khi yêu cầu hủy không?
8. **Có metric và log phân biệt timeout, cancellation, failure không?** Không gộp mọi kết quả vào “lỗi hệ thống”.

## 19. Bài tập tự kiểm tra

**Câu 1.** Thread A tính toán trong vòng `while(true)` không kiểm tra interrupt. B gọi `A.interrupt()`. A có bắt buộc dừng không?

**Đáp án:** Không. Interrupt không cưỡng bức kết thúc CPU code. A phải chủ động kiểm tra flag/điểm hủy hoặc gọi API phản ứng với interrupt.

**Câu 2.** Khi `Thread.sleep()` ném InterruptedException, `Thread.currentThread().isInterrupted()` trong catch thường cho gì?

**Đáp án:** False đối với `Thread.sleep` theo hợp đồng: cờ được clear trước khi ném. Nếu muốn bảo tồn tín hiệu khi không ném tiếp, gọi `Thread.currentThread().interrupt()`.

**Câu 3.** `Thread.interrupted()` và `Thread.currentThread().isInterrupted()` khác gì?

**Đáp án:** Cả hai kiểm tra current thread nếu gọi đúng như trên, nhưng `Thread.interrupted()` **clear flag**, còn `isInterrupted()` không clear.

**Câu 4.** Main bị interrupt khi đang `worker.join()`. Điều này chứng minh worker đã bị interrupt chưa?

**Đáp án:** Không. Interruption tác động thread đang chờ join là main. Muốn yêu cầu hủy worker, main phải dùng một hành động riêng phù hợp với ownership/protocol.

**Câu 5.** `Future.get(200, MILLISECONDS)` bị timeout. Task đã tự bị cancel chưa?

**Đáp án:** Chưa. Đây chỉ là timeout của thao tác chờ kết quả. Caller có thể chọn `future.cancel(true)` nếu muốn phát yêu cầu hủy.

**Câu 6.** Khi `lock.lockInterruptibly()` bị interrupt trước khi lock thành công, có gọi `lock.unlock()` trong finally không?

**Đáp án:** Không. Chỉ unlock nếu đã acquire. Viết try/finally **sau** lời acquire thành công hoặc dùng một biến ghi nhận ownership.

**Câu 7.** Vì sao `shutdownNow()` không bảo đảm mọi task của executor đã kết thúc?

**Đáp án:** Nó chỉ cố dừng/interrupt workers và trả về các task chưa bắt đầu trong phạm vi contract. Worker không phản hồi interruption có thể vẫn chạy.

**Câu 8.** Một thread bị interrupt sau khi ghi file nhưng trước khi gửi event. Có tự rollback file không?

**Đáp án:** Không. Interrupt chỉ là tín hiệu hủy; file write là side effect riêng. Phải có protocol nghiệp vụ cho partial completion, idempotency và recovery.

## 20. Tài liệu chính thức

- **Thread (Java 21), mục Thread Interruption:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html
- **Future (Java 21), mục cancel:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html
- **ExecutorService (Java 21), mục shutdown/shutdownNow/awaitTermination:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html
- **ReentrantLock (Java 21), lockInterruptibly:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html
- **BlockingQueue (Java 21):** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/BlockingQueue.html
- **JLS `17, Threads and Locks:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html

**Kết luận:** `interrupt()` chỉ **gửi yêu cầu hủy**, không “giết” thread. Worker phải **hợp tác nhận diện**, chọn điểm dừng an toàn, cleanup và thực sự kết thúc; caller cần quan sát completion. `InterruptedException` thường là cách các API blocking chuyển yêu cầu hủy thành luồng điều khiển, còn `Future.cancel(true)` và `shutdownNow()` cũng chỉ nỗ lực hủy. Tính đúng của hệ thống đến từ **giao thức cancellation, ownership, cleanup và invariant**, không đến từ một lời gọi interrupt đơn lẻ.
