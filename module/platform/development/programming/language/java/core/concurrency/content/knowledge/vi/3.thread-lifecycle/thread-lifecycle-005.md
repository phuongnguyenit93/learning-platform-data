# Quan sát trạng thái Thread bằng `Thread.getState()` trong Java

Khi một chương trình Java chạy đồng thời nhiều công việc, ta thường muốn trả lời: thread đã khởi động chưa, đang có cơ hội chạy, đang chờ khóa, đang chờ tín hiệu, đang chờ có giới hạn thời gian hay đã kết thúc? **`Thread.getState()`** là API quan sát nhanh vòng đời của một `Thread`. Tuy nhiên, trạng thái được trả về là **ảnh chụp tại một thời điểm**, không phải nhật ký đầy đủ hay cam kết thread vẫn ở trạng thái đó khi ta xử lý kết quả.

Bài học tập trung vào concurrency của **Java nói chung**, qua `java.lang.Thread` và các tiện ích đồng bộ trong `java.util.concurrent`. Trọng tâm là biết **đọc đúng sáu giá trị `Thread.State`**, tạo được tình huống quan sát, hiểu giới hạn và dùng trạng thái để hỗ trợ chẩn đoán. Không dùng cơ chế riêng của Spring.

## 1. `Thread.getState()` trả về gì?

Chữ ký:

```java
public Thread.State getState()
```

Đây là **chữ ký API**, không phải một chương trình Java độc lập. `getState()` trả về một phần tử của enum lồng `Thread.State`, mô tả trạng thái của **thread được gọi** tại thời điểm quan sát:

```java
Thread worker = new Thread(() -> doWork());
Thread.State snapshot = worker.getState();
```

Đoạn trên là minh họa ý tưởng; `doWork()` là tên phương thức giả định. Có thể gọi `getState()` trước hoặc sau `start()`, trong khi thread chạy, hoặc khi nó đã kết thúc. Không cần `synchronized` chỉ để gọi phương thức quan sát này.

Có **sáu** giá trị:

| `Thread.State` | Cách đọc | Tình huống tiêu biểu |
| --- | --- | --- |
| `NEW` | Đã tạo đối tượng `Thread` nhưng chưa `start()` | `new Thread(task)` vừa được gọi |
| `RUNNABLE` | Đang có khả năng thực thi trong JVM, có thể đang chạy hoặc chờ được cấp CPU/tài nguyên hệ điều hành | Thread đã `start()` và đang thực hiện công việc hoặc sẵn sàng chạy |
| `BLOCKED` | Đang chờ **monitor lock** để vào hoặc trở lại một vùng `synchronized` | Hai thread tranh chấp cùng monitor |
| `WAITING` | Đang chờ vô thời hạn theo một cơ chế chờ, tới khi được đánh thức/hoàn tất/interrupt tùy API | `Object.wait()` không timeout, `Thread.join()` không timeout, `LockSupport.park()` |
| `TIMED_WAITING` | Đang chờ với thời hạn hoặc khoảng thời gian được chỉ định | `Thread.sleep(...)`, `Object.wait(timeout)`, `Thread.join(timeout)`, `LockSupport.parkNanos(...)` |
| `TERMINATED` | Hàm `run()` đã kết thúc, dù kết thúc bình thường hay bởi uncaught exception | Thread đã hoàn tất |

**Không có `RUNNING`, `SLEEPING`, `PARKED` hay `DEAD` trong enum này.** Những cách gọi đó đôi khi xuất hiện trong sơ đồ dạy học hoặc công cụ chẩn đoán, nhưng không phải giá trị trả về của `Thread.getState()`.

`RUNNABLE` là trường hợp dễ hiểu sai nhất: nó **không chứng minh thread thực sự chiếm CPU tại lúc quan sát**. Tài liệu Java mô tả một thread ở trạng thái này có thể đang thực thi trong JVM nhưng vẫn chờ những tài nguyên ở mức hệ điều hành, chẳng hạn bộ xử lý. Từ một ảnh chụp `RUNNABLE` không suy ra CPU usage.

## 2. Sơ đồ vòng đời: trạng thái có thể chuyển đổi ra sao?

Sơ đồ khái quát:

```text
new Thread(...) 
      |
      v
     NEW
      |
      | start()
      v
  RUNNABLE <----------------------------------------------+
      |                                                  |
      | tranh monitor / synchronized                      |
      +-------> BLOCKED ----- lấy được monitor -----------+
      |                                                  |
      | wait/park/join không timeout                      |
      +-------> WAITING ----- được phép tiếp tục ---------+
      |                                                  |
      | sleep/wait/park/join có timeout                   |
      +-------> TIMED_WAITING -- timeout/tín hiệu --------+
      |
      | run() trả về hoặc kết thúc do uncaught exception
      v
 TERMINATED
```

Đây là **sơ đồ tư duy**, không phải một máy trạng thái mô tả đầy đủ mọi chuyển tiếp của JVM. Ví dụ thread được `notify()` sau `Object.wait()` có thể phải **chờ lấy lại monitor** trước khi tiếp tục, nên đôi lúc được quan sát là `BLOCKED`. Sau `interrupt()`, thread có thể trở về `RUNNABLE` để xử lý ngắt, chứ không tự động thành `TERMINATED`.

Những nguyên tắc cơ bản:

1. Tạo bằng constructor chỉ cho trạng thái `NEW`; **gọi `run()` trực tiếp** là gọi phương thức bình thường trên caller thread, không `start()` một thread mới.
2. `start()` yêu cầu JVM bắt đầu vòng đời thread, chỉ được gọi **một lần trên cùng đối tượng `Thread`**. Gọi lại sau khi đã start, kể cả khi thread kết thúc, dẫn tới `IllegalThreadStateException`.
3. Thread có thể đi từ `RUNNABLE` sang chờ rồi quay lại `RUNNABLE` nhiều lần; **không cần đi qua tất cả sáu trạng thái**.
4. Khi `run()` kết thúc, trạng thái cuối là `TERMINATED`. Muốn thực hiện thêm công việc trên thread khác thì tạo thread mới hoặc gửi task tới executor; không tái khởi động cùng `Thread`.

## 3. Ví dụ Java 17+: quan sát `NEW`, `RUNNABLE`, `TERMINATED`

Ví dụ đầu tiên dùng một worker chạy vòng lặp có cờ dừng `volatile`. Nhờ không đặt điểm chờ blocking trong vòng lặp, ta có thể kiểm tra `RUNNABLE` một cách có kiểm soát. Đoạn spin này **chỉ để học và chẩn đoán**, không nên biến thành cách chờ công việc trong ứng dụng thực.

Lưu thành `BasicThreadStateDemo.java`:

```java
import java.util.concurrent.TimeUnit;

public class BasicThreadStateDemo {
    private static volatile boolean stopRequested;

    private static void awaitState(Thread thread, Thread.State expected) {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(3);

        while (System.nanoTime() - deadline < 0) {
            if (thread.getState() == expected) {
                return;
            }
            Thread.onSpinWait();
        }

        throw new IllegalStateException(
                "Did not observe " + expected + "; last=" + thread.getState());
    }

    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(() -> {
            while (!stopRequested) {
                Thread.onSpinWait();
            }
        }, "demo-worker");

        System.out.println("Before start: " + worker.getState());

        worker.start();
        try {
            awaitState(worker, Thread.State.RUNNABLE);
            System.out.println("While active: " + worker.getState());
        } finally {
            stopRequested = true;
            worker.join();
        }

        System.out.println("After join: " + worker.getState());
    }
}
```

Lệnh chạy trên JDK 17 trở lên:

```bash
javac BasicThreadStateDemo.java
java BasicThreadStateDemo
```

Với lần chạy bình thường, khi `RUNNABLE` được quan sát trước thời hạn, stdout:

```text
Before start: NEW
While active: RUNNABLE
After join: TERMINATED
```

**Giải thích:**

- Trước `start()`, đối tượng worker là `NEW`.
- `worker.start()` bắt đầu thread mới; worker đọc cờ `volatile stopRequested` trong vòng lặp. Cờ volatile giúp worker nhìn thấy yêu cầu dừng từ main.
- `awaitState` **lấy mẫu lặp có giới hạn ba giây**, tránh giả định cứ gọi `getState()` ngay sau `start()` sẽ nhìn thấy trạng thái mong muốn. Thời điểm scheduler chạy worker vẫn không được cam kết; nếu máy bị treo lâu hoặc JVM không lập lịch kịp, ví dụ báo lỗi thay vì khẳng định sai.
- Trong ví dụ này worker không chờ monitor, queue hay sleep và cờ chưa được bật, nên khi đã bắt đầu hoạt động nó nằm ở `RUNNABLE`. Trạng thái không đồng nghĩa có cả một lõi CPU dành riêng.
- `stopRequested = true` yêu cầu worker thoát, `worker.join()` **đợi kết thúc thật sự**. Chỉ sau `join()` thành công, việc in `TERMINATED` mới có căn cứ mạnh. `getState()` một mình không phải phép đợi hoàn thành.

Vì `Thread.onSpinWait()` có thể tiêu tốn CPU trong lúc chờ, đây chỉ là đoạn kiểm chứng ngắn phục vụ việc học. Trong code thực tế, dùng `CountDownLatch`, `BlockingQueue`, `Future` hoặc cơ chế signaling tương ứng khi cần chờ sự kiện.

## 4. Phân biệt ba kiểu chờ: `BLOCKED`, `WAITING` và `TIMED_WAITING`

Ba trạng thái trông giống nhau vì thread chưa tiếp tục công việc, nhưng **nguyên nhân chờ khác nhau**.

### `BLOCKED`: chờ intrinsic monitor lock

Giả sử thread A đang ở:

```java
synchronized (monitor) {
    // Giữ monitor trong critical section.
}
```

Nếu thread B cũng muốn vào vùng `synchronized (monitor)` khi A chưa nhả monitor, B có thể ở `BLOCKED`. Cả hai phải tranh **cùng một đối tượng monitor** thì mới có tranh chấp đó.

`BLOCKED` gắn với **monitor entry/re-entry**. Không nên hiểu mọi thao tác "đang block" theo tiếng Anh là `Thread.State.BLOCKED`:

- `Thread.sleep(...)` thường cho `TIMED_WAITING`.
- `Object.wait()` nhả monitor khi chờ và thường cho `WAITING`.
- `BlockingQueue.take()` thường đỗ thread qua cơ chế trong `java.util.concurrent.locks`, do đó thường cho `WAITING` nếu không timeout.
- `ReentrantLock.lock()` dưới tranh chấp có thể chờ thông qua `LockSupport.park()`, thường quan sát là `WAITING`, **không phải `BLOCKED`** theo nghĩa monitor.

Không suy luận trực tiếp loại tài nguyên đang chờ từ tên "blocked" trong tài liệu nghiệp vụ. Phải đối chiếu API và stack trace.

### `WAITING`: đợi tín hiệu hoặc điều kiện vô thời hạn

Thread có thể ở `WAITING` khi gọi `Object.wait()`, `Thread.join()`, `LockSupport.park()` hoặc các API đồng bộ dùng parking mà chưa đặt timeout.

"Vô thời hạn" chỉ có nghĩa **không thiết lập thời hạn tự đánh thức ngay trong lời gọi**. Không có nghĩa thread sẽ không bao giờ được đánh thức; nó có thể được `notify/notifyAll`, unpark, điều kiện đồng bộ hoàn thành hoặc interruption tùy API. `Object.wait()` và `Condition.await()` còn có thể thức dậy giả (spurious wakeup), nên phải kiểm tra lại điều kiện theo hợp đồng của API.

### `TIMED_WAITING`: chờ có khoảng thời gian/thời hạn

`Thread.sleep(1_000)` đưa thread hiện tại vào trạng thái `TIMED_WAITING` trong phần thời gian ngủ. Các ví dụ khác là `wait(timeout)`, `join(timeout)` và `LockSupport.parkNanos(...)`.

**Có timeout không có nghĩa thread chắc chắn trở lại `RUNNABLE` vào đúng mốc thời gian.** Thời gian hết hạn, scheduling, việc tranh khóa và interrupt đều có thể ảnh hưởng lúc thread thực sự tiếp tục. `Thread.sleep(...)` cũng **không giải phóng monitor** mà thread đang giữ.

## 5. Ví dụ Java 17+: tạo tình huống quan sát ba trạng thái chờ

Ví dụ tiếp theo dùng nguyên nhân chờ có kiểm soát: một monitor đang bị giữ cho `BLOCKED`, một latch chưa mở cho `WAITING`, và `Thread.sleep` cho `TIMED_WAITING`. Thay vì gọi `sleep` ở thread main để **đoán** lúc worker chuyển trạng thái, chương trình lấy mẫu giới hạn thời gian rồi giải phóng từng worker.

Lưu thành `WaitingStatesDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class WaitingStatesDemo {
    private static Thread.State observe(
            Thread thread, Thread.State expected) {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(3);

        while (System.nanoTime() - deadline < 0) {
            Thread.State current = thread.getState();
            if (current == expected) {
                return current;
            }
            Thread.onSpinWait();
        }

        throw new IllegalStateException(
                "Expected " + expected + ", last=" + thread.getState());
    }

    public static void main(String[] args) throws InterruptedException {
        // 1. Một thread khác đang giữ intrinsic monitor.
        Object monitor = new Object();
        CountDownLatch aboutToContend = new CountDownLatch(1);
        Thread contender = new Thread(() -> {
            aboutToContend.countDown();
            synchronized (monitor) {
                // Chỉ vào được sau khi main nhả monitor.
            }
        }, "contender");

        synchronized (monitor) {
            contender.start();
            aboutToContend.await();
            System.out.println("Monitor: "
                    + observe(contender, Thread.State.BLOCKED));
        }
        contender.join();

        // 2. Thread chờ latch mở, không đặt timeout.
        CountDownLatch gate = new CountDownLatch(1);
        Thread waiter = new Thread(() -> {
            try {
                gate.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "waiter");

        waiter.start();
        try {
            System.out.println("Latch: "
                    + observe(waiter, Thread.State.WAITING));
        } finally {
            gate.countDown();
            waiter.join();
        }

        // 3. Thread đang sleep với khoảng thời gian cho trước.
        Thread sleeper = new Thread(() -> {
            try {
                Thread.sleep(30_000);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "sleeper");

        sleeper.start();
        try {
            System.out.println("Sleep: "
                    + observe(sleeper, Thread.State.TIMED_WAITING));
        } finally {
            sleeper.interrupt();
            sleeper.join();
        }
    }
}
```

Chạy:

```bash
javac WaitingStatesDemo.java
java WaitingStatesDemo
```

Khi ba trạng thái được quan sát thành công trước thời hạn, stdout chính xác:

```text
Monitor: BLOCKED
Latch: WAITING
Sleep: TIMED_WAITING
```

**Vì sao ví dụ cố tình giữ trạng thái ổn định?**

- Main giữ `monitor` trong khi thread `contender` cố vào cùng monitor. `aboutToContend` xác nhận worker đã chạy đến trước đoạn tranh khóa; vòng `observe` chờ nhìn thấy `BLOCKED` thay vì đặt một lần `sleep` và hy vọng.
- `gate` chưa được `countDown()` trong lúc quan sát, nên worker gọi `gate.await()` sẽ chờ. Trên JDK thông dụng, latch sử dụng cơ chế parking nên ta quan sát `WAITING`. Sau đó main gọi `countDown()` để worker có thể thoát.
- `sleeper` bắt đầu khoảng `sleep` dài để main có cơ hội lấy mẫu `TIMED_WAITING`. `interrupt()` trong `finally` giúp kết thúc nhanh; nó **không cưỡng bức giết thread**, mà làm `sleep` phản hồi bằng `InterruptedException`.
- `join()` dùng để thu dọn worker sau từng trường hợp. Không cần dùng `getState()` để quyết định lúc giải phóng tài nguyên.

Đây vẫn là một ví dụ đo trạng thái theo lịch chạy thực tế: nếu JVM hoặc hệ điều hành chậm bất thường, vòng `observe` có thể hết thời gian và ném `IllegalStateException`. Timeout là **giới hạn chờ để bài không treo vô tận**, không phải lời cam kết scheduler luôn đặt worker vào đúng trạng thái trong ba giây.

## 6. Vì sao `getState()` chỉ là ảnh chụp, không phải công cụ đồng bộ?

Xét đoạn code:

```java
if (worker.getState() == Thread.State.WAITING) {
    // ...
}
```

Ngay sau khi `getState()` trả về, một thread khác có thể đánh thức worker; hoặc worker bị interrupt, timeout hay thay đổi trạng thái vì một sự kiện khác. Câu `if` chỉ nói **đã quan sát `WAITING`**, không chứng minh điều kiện vẫn đúng ở câu lệnh tiếp theo.

Đây là một dạng **time-of-check to time-of-use race**: trạng thái có thể thay đổi giữa lúc kiểm tra và lúc sử dụng thông tin. Không nên viết logic nghiệp vụ dựa vào kết luận "nếu thread đang WAITING thì chắc chắn có thể thao tác X an toàn".

So sánh hai cách chờ kết thúc:

```java
// Không nên dùng vòng đọc trạng thái như cơ chế chờ hoàn tất.
while (worker.getState() != Thread.State.TERMINATED) {
    Thread.onSpinWait();
}
```

và:

```java
// Cách chuẩn để đợi Thread kết thúc.
worker.join();
```

`join()` có ngữ nghĩa **đợi thread hoàn tất**, hỗ trợ interruption và cung cấp quan hệ happens-before: mọi hành động trong worker xảy ra trước các hành động của thread gọi sau khi `join()` thành công. `getState()` là API quan sát; không được sử dụng như một primitive đồng bộ thay thế `join()`.

Tương tự, nếu muốn đợi một nhiệm vụ trong executor, dùng `Future.get()` hoặc `CompletableFuture.join()` theo ngữ nghĩa cần thiết. Muốn biết nhiều worker đã tới mốc xử lý, dùng `CountDownLatch` hoặc barrier phù hợp. Muốn chờ dữ liệu, dùng queue/condition. Các API đó biểu diễn **điều kiện công việc**, trong khi `Thread.State` chỉ mô tả trạng thái thread.

### `getState()` và `isAlive()` khác nhau thế nào?

`Thread.isAlive()` trả về `true` sau khi thread đã được start và **chưa** chết. Nó là câu hỏi hai trạng thái tổng quát hơn:

| Quan sát | `getState()` | `isAlive()` |
| --- | --- | --- |
| Trước `start()` | `NEW` | `false` |
| Sau `start()`, chưa kết thúc | Một trong `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING` | `true` |
| Sau `join()` thành công | `TERMINATED` | `false` |

Vì hai lệnh đọc là hai thời điểm khác nhau, code không được dựa vào việc chúng luôn phản ánh **cùng một thời điểm**. `isAlive()` cũng không chứng minh worker đang tạo tiến độ hữu ích: thread có thể đang chờ hoặc mắc kẹt.

### `getState()` không biểu diễn interrupt flag

`Thread.interrupt()` là cơ chế yêu cầu ngắt. Trạng thái `WAITING` hoặc `TIMED_WAITING` có thể thay đổi khi một lời gọi chờ hỗ trợ interruption ném `InterruptedException`; bản thân **interrupt flag không phải giá trị `Thread.State`**. Dùng `isInterrupted()` hoặc `Thread.interrupted()` đúng ngữ nghĩa nếu cần kiểm tra ngắt; lưu ý `Thread.interrupted()` là phương thức static kiểm tra **thread hiện tại** và xóa interrupt flag khi trả về `true`.

## 7. Cùng là chờ nhưng nguyên nhân khác: đọc state và stack trace cùng nhau

Không thể xác định chính xác "đang chờ gì" chỉ từ enum:

- `WAITING` có thể là worker đang chờ task mới trong pool, thread đang `join()` thread khác, đang `Object.wait()`, hoặc đang bị `park()` bởi một công cụ đồng bộ.
- `TIMED_WAITING` có thể là sleep chủ động, chờ tín hiệu có timeout hoặc chờ một thao tác lập lịch theo khoảng thời gian.
- `BLOCKED` chỉ ra chờ monitor, nhưng **một lần quan sát `BLOCKED` không chứng minh deadlock**. Đây có thể là tranh khóa rất ngắn, hoàn toàn hợp lệ.
- `RUNNABLE` có thể đang thực thi mã CPU-bound hoặc chờ tài nguyên hệ điều hành; cần thêm thông tin để kết luận vì sao hệ thống chậm.

Nếu cần điều tra, kết hợp **thread name**, **stack trace**, **thời điểm lấy mẫu**, **monitor/lock liên quan** và chỉ số tiến độ của công việc.

Ví dụ chụp stack bằng Java:

```java
Thread.State state = worker.getState();
StackTraceElement[] frames = worker.getStackTrace();
```

Đây là đoạn minh họa sử dụng biến `worker` đã có, không phải chương trình độc lập. Stack trace cũng là một ảnh chụp có thể không hoàn toàn trùng thời điểm với lần đọc state. Nếu thread thay đổi trong khoảng giữa hai lời gọi, stack có thể phản ánh một vị trí thực thi khác; không nên diễn giải đây là một snapshot đồng bộ tuyệt đối.

Với chẩn đoán JVM, Java có `java.lang.management.ThreadMXBean` để lấy thông tin về thread, stack, một số chỉ số/owner của lock tùy khả năng nền tảng. Khi kiểm tra deadlock, `findDeadlockedThreads()` có thể phát hiện chu trình chờ liên quan monitor và ownable synchronizers được JVM hỗ trợ. Kết quả `null` trong một lần kiểm tra **không bảo đảm chương trình không thể deadlock trong tương lai**. Thread dump và công cụ như `jcmd Thread.print` cũng hữu ích khi xác định vị trí chờ, nhưng cần đối chiếu nhiều mẫu và bối cảnh tải thực tế.

## 8. Khi nào nên lấy mẫu trạng thái theo chu kỳ?

`getState()` hữu ích trong **chẩn đoán**, ví dụ:

1. Xác nhận một thread mới tạo chưa được start (`NEW`).
2. Thấy một thread đã hoàn tất sau khi điều phối thành công (`TERMINATED`).
3. Nhận diện một worker đang tranh monitor (`BLOCKED`) để xem có critical section quá dài hay không.
4. Kiểm tra worker đang chờ tín hiệu hay chờ timeout (`WAITING`/`TIMED_WAITING`), từ đó xem điều kiện và nguồn đánh thức.
5. Xác định các thread cùng thay đổi trạng thái qua nhiều lần quan sát, rồi đối chiếu với log và thread dump.

Lấy **một** trạng thái của **một** thread chỉ đủ cho kết luận hẹp. Khi cần hiểu xu hướng, nên lấy nhiều mẫu có mốc thời gian rồi so với số task hoàn thành, thời gian queue, CPU, lock contention và stack.

Ví dụ nếu 20 worker đều `WAITING` và hàng đợi rỗng, đây có thể là một pool nhàn rỗi khỏe mạnh. Nếu hàng đợi còn hàng nghìn task nhưng worker `WAITING` lâu và không có task hoàn thành, cần xem điều kiện đồng bộ, tín hiệu và cách đẩy công việc. Chỉ đếm số thread `WAITING` sẽ bỏ qua bối cảnh.

**Đừng dùng polling trạng thái liên tục trong production** để quyết định vòng đời task. Nó tốn chi phí, dễ đua trạng thái và không cung cấp causal semantics. Đặt metric cho tiến độ công việc và sử dụng các primitive đồng bộ để điều khiển thay cho polling trạng thái.

## 9. Quan sát current thread và worker thread

`Thread.currentThread()` trả về thread đang thực thi câu lệnh hiện tại. Vì vậy:

```java
Thread current = Thread.currentThread();
System.out.println(current.getName());
System.out.println(current.getState());
```

Nếu gọi trong `main` và thread main đang thực thi lệnh in, thông thường `getState()` tại thời điểm đọc sẽ là `RUNNABLE`, nhưng **tên thread** phụ thuộc cách chạy chương trình, và việc in/đọc stdout có thể khiến trạng thái thay đổi sau đó. Không nên ghi cứng tên hay các số đo thời gian trong tài liệu như cam kết toàn cục.

Phải phân biệt:

```java
Thread worker = new Thread(() -> {
    // Tại đây currentThread() là worker sau khi start().
});
System.out.println(worker.getState()); // Có thể vẫn là NEW.
worker.start();
```

Trong khi phương thức `run()` chạy trên worker mới sau `start()`, thread main tiếp tục độc lập. Một lệnh `getState()` ngay sau `start()` ở main **không đảm bảo** sẽ thấy `RUNNABLE`; nếu worker kết thúc cực nhanh, main có thể thấy `TERMINATED`.

Nếu thay `worker.start()` bằng `worker.run()`, Java chỉ thực thi `run()` như phương thức bình thường trên main; `worker` vẫn là `NEW`, dù code bên trong đã được chạy một lần trên thread khác. Đây là lỗi đặc biệt dễ làm người học hiểu sai vòng đời.

## 10. Những tình huống dễ chẩn đoán sai

### Trường hợp A: "Một thread ở `BLOCKED` nên ứng dụng deadlock"

Không đủ dữ kiện. `BLOCKED` nghĩa là đang chờ monitor; nếu thread giữ monitor sớm giải phóng, đó chỉ là contention. Deadlock cần quan hệ chờ vòng tròn hoặc bằng chứng hệ thống không thể tiến triển. Cần đối chiếu lock owner, stack trace và tiến độ qua thời gian.

### Trường hợp B: "Một worker trong pool ở `WAITING` là bị treo"

Không nhất thiết. Worker rảnh có thể đợi job mới bằng queue, và điều đó là bình thường. Phải xem tình trạng queue, số worker hoạt động, số task hoàn thành và chính sách pool.

### Trường hợp C: "`RUNNABLE` là đang chạy 100% CPU"

Sai. `RUNNABLE` không phải CPU meter. Thread có thể chưa được cấp CPU hoặc đang chờ tài nguyên hệ điều hành. Muốn kiểm tra CPU dùng CPU profiling/CPU time từ công cụ chẩn đoán phù hợp, không suy ra từ state.

### Trường hợp D: "`TIMED_WAITING` nghĩa là thread sắp kết thúc"

Sai. Nó chỉ cho biết thread chờ có giới hạn; sau khi hết hạn hoặc bị interrupt, nó có thể quay lại làm việc và lặp lại chu kỳ nhiều lần.

### Trường hợp E: "Thread đã `TERMINATED` có thể gọi `start()` lại"

Sai. Đối tượng `Thread` đã start không thể start lần hai. Hãy tạo thread mới hoặc gửi task vào executor.

### Trường hợp F: "Gọi `getState()` liên tục là cách chuẩn để đợi thread xong"

Sai. Sử dụng `join()` hoặc kết quả từ future/latch. `getState()` dùng cho quan sát; việc tự spin trên state gây lãng phí CPU và không thay thế bảo đảm đồng bộ mong muốn.

### Trường hợp G: "Gọi `interrupt()` sẽ làm thread thành `TERMINATED`"

Không nhất thiết. Interruption chỉ là yêu cầu. Khi thread đang `sleep()` hoặc chờ hỗ trợ interruption, nó có thể ném `InterruptedException`, thực thi nhánh catch rồi tiếp tục. Trạng thái cuối phụ thuộc logic `run()`.

### Trường hợp H: "Chờ bằng `ReentrantLock.lock()` chắc chắn là `BLOCKED`"

Không chính xác. `BLOCKED` trong `Thread.State` gắn với **intrinsic monitor**, không bao trùm mọi loại lock. Khóa tường minh có thể dùng parking nên thường được thấy ở `WAITING`. Đọc stack để hiểu đúng API và cơ chế thực tế.

## 11. Virtual threads có làm thay đổi cách hiểu không?

Trên Java 21+, virtual threads cũng là các đối tượng `Thread` và có thể được quan sát bằng `getState()`. Tuy nhiên, virtual thread được JVM lên lịch lên carrier platform thread; vì vậy **không được đồng nhất trạng thái của virtual thread với một thread hệ điều hành đang chạy trên một CPU cụ thể**. Các thời điểm parking, waiting và scheduling có thể có chi tiết khác với platform threads.

Hai chương trình Java 17+ trong bài dùng platform threads để minh họa rõ vòng đời nền tảng. Nếu ứng dụng dùng virtual threads trên Java 21+, ý nghĩa quan sát vẫn theo `Thread.State`, còn việc đánh giá hiệu năng hoặc scheduler phải xét riêng. Không suy luận số lượng carrier threads từ số virtual threads đang `RUNNABLE`.

## 12. Câu hỏi tự kiểm tra

**1. Vì sao gọi `worker.getState()` ngay sau `worker.start()` có thể cho kết quả khác nhau giữa các lần chạy?**

Vì scheduler và thời lượng công việc quyết định thời điểm chuyển trạng thái, trong khi `getState()` chỉ chụp một thời điểm. Với worker chạy rất ngắn, main có thể quan sát `RUNNABLE` hoặc thậm chí `TERMINATED` khi đọc.

**2. `BLOCKED` và `WAITING` khác nhau ở điểm nào quan trọng nhất?**

`BLOCKED` liên quan trực tiếp đến chờ **intrinsic monitor**. `WAITING` là chờ không timeout theo cơ chế như `wait/park/join`, không đồng nghĩa chờ monitor entry. Một API dùng `ReentrantLock` có thể park và hiện là `WAITING`.

**3. `Thread.sleep(1000)` có nhả khóa `synchronized` mà thread đang giữ không?**

Không. `sleep` không giải phóng monitor. Vì thế một thread khác có thể bị `BLOCKED` trong khi chủ monitor ở `TIMED_WAITING`.

**4. Nếu thread ở `WAITING` thì có chắc ứng dụng lỗi?**

Không. Thread có thể đang chờ công việc mới hoặc chờ tín hiệu hợp lệ. Cần xem điều kiện chờ, nguồn tín hiệu, số task trong queue và các mẫu trạng thái/stack theo thời gian.

**5. Tại sao `join()` được dùng sau khi lấy mẫu ở các ví dụ?**

Vì `join()` thực sự đợi worker kết thúc và thiết lập quan hệ đồng bộ sau khi hoàn tất. `getState()` chỉ giúp quan sát, không đợi và không giữ trạng thái cố định.

**6. Cơ chế nào nên dùng nếu muốn biết ba task đã xong, và `getState()` đóng vai trò gì?**

Dùng `CountDownLatch`, future hoặc cơ chế đợi hoàn tất phù hợp để điều phối ba task. `getState()` chỉ hỗ trợ chẩn đoán thread nào đang ở trạng thái gì trong quá trình đó.

## 13. Nguyên tắc ghi nhớ

- `Thread.getState()` trả về **một** trong sáu trạng thái `NEW`, `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING`, `TERMINATED`.
- `RUNNABLE` **không đồng nghĩa đang tiêu thụ CPU**; `BLOCKED` chỉ chờ monitor; `WAITING` và `TIMED_WAITING` mô tả chờ không timeout hoặc có giới hạn.
- `getState()` là **ảnh chụp có thể lỗi thời ngay lập tức**. Đừng dựa vào một lần quan sát để xác định điều kiện nghiệp vụ hoặc chứng minh deadlock.
- Khi cần **đợi hoàn thành**, dùng `join()`, `Future` hay primitive đồng bộ khác. Khi cần **tìm nguyên nhân chờ**, kết hợp trạng thái với stack trace, monitor/lock và tiến độ công việc.
- Hãy thiết kế ví dụ quan sát bằng điều kiện có kiểm soát, xác nhận trạng thái bằng polling **có timeout**, và luôn có đường cleanup cho thread được khởi động.

Hiểu các giới hạn này giúp `getState()` trở thành công cụ quan sát hữu ích khi học, kiểm thử và xử lý sự cố Java concurrency, thay vì một nguồn suy luận sai về scheduler hoặc về sự hoàn tất của công việc.