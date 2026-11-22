# Các trạng thái BLOCKED, WAITING và TIMED_WAITING trong vòng đời Thread của Java

Ba trạng thái `BLOCKED`, `WAITING` và `TIMED_WAITING` đều cho thấy một thread hiện không tiến hành công việc Java thông thường như một thread `RUNNABLE`. Tuy nhiên, **nguyên nhân chờ, tài nguyên liên quan và cách đánh thức hoàn toàn khác nhau**. Phân biệt chính xác ba trạng thái giúp đọc thread dump, nhận diện lock contention, deadlock và thiết kế phối hợp thread đúng. Nội dung dưới đây nói về Java concurrency nói chung, không phụ thuộc framework.

## 1. Đặt ba trạng thái vào toàn bộ vòng đời

`java.lang.Thread.State` là một `enum` gồm sáu giá trị:

| Trạng thái | Ý nghĩa tóm tắt |
| --- | --- |
| `NEW` | Đã tạo đối tượng `Thread` nhưng chưa gọi `start()`. |
| `RUNNABLE` | Thread sẵn sàng hoặc đang thực thi trong JVM; **không đồng nghĩa** đang chiếm CPU ở mọi thời điểm. |
| `BLOCKED` | Đang chờ lấy **intrinsic monitor lock** để vào hoặc quay lại một vùng đồng bộ bằng `synchronized`. |
| `WAITING` | Đang chờ vô thời hạn theo một cơ chế chờ cụ thể, cho tới khi có sự kiện cho phép tiến triển. |
| `TIMED_WAITING` | Đang chờ theo cơ chế có thời hạn, có thể kết thúc vì sự kiện đánh thức hoặc hết thời gian. |
| `TERMINATED` | Phương thức `run()` đã kết thúc, bình thường hoặc bởi exception không được xử lý. |

Không có giá trị `RUNNING`, `SLEEPING` hoặc `DEADLOCKED` trong `Thread.State`. Chẳng hạn “sleeping” thể hiện qua `TIMED_WAITING`; deadlock là một tình trạng hệ thống có thể biểu hiện bằng `BLOCKED` hoặc những trạng thái chờ khác. Một thread có thể đi qua nhiều trạng thái trước khi kết thúc; **đây là snapshot tại một thời điểm, không phải lịch sử đầy đủ của thread**.

Ba trạng thái trọng tâm:

| Tiêu chí | `BLOCKED` | `WAITING` | `TIMED_WAITING` |
| --- | --- | --- | --- |
| Đợi điều gì? | Được quyền sở hữu monitor lock | Tín hiệu/sự kiện, không đặt thời hạn ở thao tác chờ | Tín hiệu/sự kiện **hoặc** mốc thời gian |
| Ví dụ trực tiếp | Vào `synchronized(lock)` khi thread khác đang giữ `lock` | `Object.wait()`, `Thread.join()`, `LockSupport.park()` | `Thread.sleep(ms)`, `Object.wait(ms)`, `Thread.join(ms)`, `LockSupport.parkNanos(ns)` |
| Có timeout tự kết thúc? | Không có timeout trong thao tác lấy monitor bằng `synchronized` | Không có timeout được chỉ định | Có, nhưng không đảm bảo được chạy ngay đúng mốc |
| Có thể giữ khóa khác không? | Có | Có, tùy API; riêng `Object.wait()` nhả monitor của đối tượng đang đợi | Có, ví dụ `sleep` không nhả monitor đang giữ |
| Điều nên điều tra | Ai giữ monitor? Giữ bao lâu? Có vòng chờ deadlock? | Đang chờ điều kiện nào? Ai phát tín hiệu? | Hạn chờ gì? Có timeout hoặc signal đúng không? |

## 2. BLOCKED: chờ lấy intrinsic monitor

Ví dụ:

```java
Object lock = new Object();

Thread first = new Thread(() -> {
    synchronized (lock) {
        // Tác vụ A giữ monitor của lock.
    }
});
Thread second = new Thread(() -> {
    synchronized (lock) {
        // Tác vụ B phải chờ nếu A đang giữ monitor.
    }
});
```

Đây là **mảnh minh họa**, không phải chương trình hoàn chỉnh. Nếu `first` đang trong `synchronized (lock)` khi `second` cố vào cùng monitor, `second` có thể ở `Thread.State.BLOCKED` cho tới khi lấy được khóa. Chỉ khai báo hai thread như trên **chưa làm chúng chạy**: cần `start()`; và không được khẳng định chúng chắc chắn tranh chấp nếu không có phối hợp/thời điểm phù hợp.

### Monitor là gì?

Mỗi object Java có thể đóng vai trò monitor nội tại. `synchronized (object)` yêu cầu thread sở hữu monitor trước khi vào critical section; `synchronized` trên instance method dùng monitor của `this`; `static synchronized` dùng monitor của đối tượng `Class` tương ứng. Khi monitor do thread khác nắm giữ, thread chưa lấy được monitor sẽ chờ ở `BLOCKED`.

- Monitor nội tại có tính **reentrant**: cùng một thread có thể vào lại `synchronized` của cùng monitor mà không tự khóa chính mình.
- Rời `synchronized` bình thường hay qua exception đều nhả monitor theo cơ chế Java.
- Nếu thread giữ monitor để làm I/O dài, `sleep`, gọi service chậm hoặc tính toán lâu, các thread khác có thể xếp hàng ở `BLOCKED`.
- `BLOCKED` **không có nghĩa** đang đợi mạng/đĩa. Với `ReentrantLock`, `Condition` hoặc nhiều cấu trúc dựa trên `AbstractQueuedSynchronizer`, việc chờ thường được triển khai bằng `LockSupport.park` và có thể hiện `WAITING` hoặc `TIMED_WAITING`; không nhất thiết hiện `BLOCKED`.
- Không có `synchronized.tryLock(timeout)`; nếu cần thời gian chờ hữu hạn để lấy lock, cân nhắc API `Lock.tryLock(timeout, unit)` và xử lý thất bại rõ ràng.

### BLOCKED có phải deadlock?

Không. Tranh chấp ngắn hạn là bình thường. **Deadlock** xảy ra khi có quan hệ chờ vòng, ví dụ A giữ `lock1`, đợi `lock2` còn B giữ `lock2`, đợi `lock1`. Khi đó hai thread có thể đều `BLOCKED` mãi. Nhưng một thread ở `BLOCKED` trong 2 ms vẫn có thể chỉ đang chờ critical section hợp lệ. Để điều tra, cần xem **monitor đang chờ, thread hiện sở hữu monitor đó và chuỗi phụ thuộc**, thay vì chỉ đếm số thread `BLOCKED`.

## 3. WAITING: chờ vô thời hạn theo điều kiện hoặc tín hiệu

`WAITING` nghĩa là phương thức chờ hiện tại không quy định hạn kết thúc. Các nguồn phổ biến:

- `Object.wait()`: thread phải đang giữ monitor của object, sau đó **nhả monitor của chính object đó** và vào wait set để chờ `notify`/`notifyAll`, interrupt hoặc thức dậy không có tín hiệu (spurious wakeup). Trước khi `wait()` trả về bình thường hoặc ném `InterruptedException`, thread phải lấy lại monitor đó.
- `Thread.join()` không timeout: đợi thread đích kết thúc nếu nó còn sống; thread gọi `join` mới là thread đang chờ. Không nhầm thread “bị join” với thread đang ở `WAITING`.
- `LockSupport.park()`: park thread cho tới khi có `unpark`, interrupt hoặc trở lại vì lý do được API cho phép. `park` **không tự động nhả monitor lock** mà caller đang giữ.
- Một số thao tác chờ không timeout như `CountDownLatch.await()`, `Future.get()`, `Condition.await()`: khi thực sự phải chờ, chúng thường dùng cơ chế đỗ thread và có thể hiện `WAITING`. Trạng thái thực tế là snapshot; đừng dựa vào tên API để khẳng định trạng thái tại mọi nanogiây.

**Vô thời hạn không có nghĩa là không thể thoát.** Có thể có tín hiệu, điều kiện được đáp ứng, thread bị interrupt, kết quả async hoàn tất, hoặc API cho phép spurious wakeup. Ngược lại, nếu sự kiện dự kiến không bao giờ xảy ra, thread có thể chờ vô hạn.

### `Object.wait()` khác `Thread.sleep()` ở việc nhả khóa

Đây là một điểm rất dễ nhầm:

- Khi gọi `lock.wait()` trong `synchronized(lock)`, thread **nhả monitor của `lock`** để thread khác có thể vào `synchronized(lock)`, thay đổi điều kiện và gọi `notifyAll()`.
- Khi gọi `Thread.sleep(...)` trong `synchronized(lock)`, thread **vẫn giữ monitor**. Thread khác muốn vào cùng monitor sẽ `BLOCKED` trong lúc nó ngủ.
- `wait()` chỉ nhả monitor của đối tượng được gọi `wait`; nếu thread đang giữ các monitor khác, chúng **không tự được nhả**.
- `notify()` đánh thức một waiter đủ điều kiện trong wait set, nhưng không đảm bảo chọn đúng thread mà lập trình viên muốn. `notifyAll()` thông báo mọi waiter trên monitor đó; các thread sau đó **vẫn phải tranh quyền lấy lại monitor**.

### Mẫu chuẩn: chờ một điều kiện bằng vòng `while`

`Object.wait()` chỉ là cơ chế chờ; điều kiện nghiệp vụ mới quyết định thread được tiếp tục. Do có thể thức dậy không mong đợi, điều kiện phải luôn được kiểm tra trong **`while`** thay vì giả định một lần `notify` đồng nghĩa có dữ liệu.

Ví dụ Java 17 độc lập, lưu thành `WaitNotifyExample.java`:

```java
public class WaitNotifyExample {
    public static void main(String[] args) throws InterruptedException {
        Object lock = new Object();
        boolean[] ready = {false};

        Thread consumer = new Thread(() -> {
            synchronized (lock) {
                while (!ready[0]) {
                    try {
                        lock.wait();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        return;
                    }
                }
                System.out.println("Da nhan tin hieu");
            }
        });

        consumer.start();

        synchronized (lock) {
            ready[0] = true;
            lock.notifyAll();
        }

        consumer.join();
        System.out.println("Hoan tat");
    }
}
```

Chạy bằng Java 17+:

```bash
javac WaitNotifyExample.java
java WaitNotifyExample
```

Stdout xác định:

```text
Da nhan tin hieu
Hoan tat
```

Dữ liệu `ready` chỉ được đọc/ghi khi giữ `lock` nên có bảo đảm đồng bộ và visibility. Nếu producer vào monitor trước consumer, consumer thấy `ready=true` và không cần `wait()`; nếu consumer vào trước, nó gọi `wait()` để **nhả** monitor, rồi producer có thể thay đổi điều kiện và `notifyAll()`. Hai đường đi đều đúng, không bị mất tín hiệu vì kiểm tra điều kiện và chờ diễn ra trong cùng critical section. Ví dụ này minh họa giao thức `wait/notifyAll`, **không đảm bảo** consumer đi qua `WAITING` ở mọi lần chạy.

**Đừng gọi `wait()/notify()/notifyAll()` nếu không sở hữu monitor của object**: thao tác sẽ ném `IllegalMonitorStateException`. Nên tránh dùng `wait` trực tiếp khi `BlockingQueue`, `CountDownLatch`, `Condition` hoặc primitive đồng bộ cấp cao diễn đạt đúng yêu cầu và ít rủi ro hơn.

## 4. TIMED_WAITING: chờ với thời gian giới hạn

Các thao tác điển hình:

| API | Ý nghĩa | Tác động lên monitor |
| --- | --- | --- |
| `Thread.sleep(1000)` | Tạm dừng ít nhất khoảng 1.000 ms theo cơ chế lập lịch, nếu không bị interrupt | **Không** nhả monitor đang giữ |
| `lock.wait(1000)` | Đợi trên wait set của `lock` tối đa khoảng thời gian tương ứng, có thể được báo thức sớm | Nhả monitor của `lock` trong thời gian đợi và lấy lại trước khi trả về |
| `otherThread.join(1000)` | Chờ thread đích kết thúc trong tối đa thời hạn | Không phải thao tác nhả tất cả monitor đang giữ của caller |
| `LockSupport.parkNanos(nanos)` | Park tối đa khoảng nanos dương | Không tự nhả monitor |
| `future.get(timeout, unit)` hoặc `latch.await(timeout, unit)` | Đợi kết quả/điều kiện có thời hạn | Không mặc định nhả intrinsic monitor caller đang giữ |

`TIMED_WAITING` chỉ cho thấy caller hiện đang đợi bằng thao tác có thời hạn, **không chứng minh** nó đang bị “treo” hoặc đã vi phạm SLA. Thời gian chờ thực tế bị ảnh hưởng bởi scheduling; hết timeout không có nghĩa caller lập tức giành được CPU. Một số API có thể kết thúc trước hạn vì tín hiệu, hoàn thành, interrupt hoặc spurious wakeup. `Thread.sleep` đặc biệt có thể bị ngắt bởi interrupt, nhưng không dùng nó làm cơ chế phối hợp điều kiện.

**Lưu ý Java API:** `Object.wait(0)` là đợi *vô thời hạn*, không phải chờ 0 ms rồi kết thúc ngay; `Thread.join(0)` cũng là chờ vô thời hạn. Trong ngữ cảnh thời hạn dương, dùng phiên bản có timeout và biết rõ quy ước đơn vị (milliseconds/nanoseconds). `Thread.sleep(0)` không tạo một khoảng `TIMED_WAITING` hữu ích để chờ điều kiện.

## 5. Thí nghiệm chạy được: quan sát cả ba trạng thái trên Java 17

Chạy một chương trình có phối hợp để tạo ba trạng thái mục tiêu. Đối với `BLOCKED`, main giữ monitor rồi tạo contender. Với `WAITING`, thread dùng `LockSupport.park()`. Với `TIMED_WAITING`, thread dùng `sleep` có thời hạn. Chương trình kiểm tra `getState()` ở thời điểm biết lý do chờ; nó không suy luận từ tốc độ máy hay thứ tự ngẫu nhiên.

Tạo `ThreadStatesExample.java`:

```java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.locks.LockSupport;

public class ThreadStatesExample {
    private static void awaitState(Thread thread, Thread.State expected)
            throws InterruptedException {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while (thread.getState() != expected) {
            if (!thread.isAlive() || System.nanoTime() >= deadline) {
                throw new IllegalStateException(
                        "Khong quan sat duoc: " + expected);
            }
            Thread.sleep(1);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Object lock = new Object();

        Thread contender = new Thread(() -> {
            synchronized (lock) {
                // Vào được sau khi main nhả monitor.
            }
        }, "monitor-contender");

        synchronized (lock) {
            contender.start();
            awaitState(contender, Thread.State.BLOCKED);
            System.out.println("Da quan sat: BLOCKED");
        }
        contender.join();

        AtomicBoolean done = new AtomicBoolean(false);
        Thread parked = new Thread(() -> {
            while (!done.get()) {
                LockSupport.park();
            }
        }, "parked-worker");

        parked.start();
        awaitState(parked, Thread.State.WAITING);
        System.out.println("Da quan sat: WAITING");
        done.set(true);
        LockSupport.unpark(parked);
        parked.join();

        Thread sleeper = new Thread(() -> {
            try {
                Thread.sleep(10_000);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "sleeping-worker");

        sleeper.start();
        awaitState(sleeper, Thread.State.TIMED_WAITING);
        System.out.println("Da quan sat: TIMED_WAITING");
        sleeper.interrupt();
        sleeper.join();
    }
}
```

```bash
javac ThreadStatesExample.java
java ThreadStatesExample
```

Stdout khi các trạng thái được quan sát trong thời hạn kiểm tra:

```text
Da quan sat: BLOCKED
Da quan sat: WAITING
Da quan sat: TIMED_WAITING
```

**Giải thích thí nghiệm:**

1. Main giữ `lock`. Contender gọi `synchronized(lock)` nhưng chưa lấy được monitor nên `BLOCKED`. Sau khi main rời khối đồng bộ, contender có thể vào monitor và hoàn thành.
2. Worker gọi `LockSupport.park()` khi chưa có permit, nên có thể đi vào `WAITING`. Main đặt cờ `done` rồi gọi `unpark`; vòng lặp quanh `park` xử lý trường hợp `park` tự thức dậy không do `unpark`. `AtomicBoolean` đảm bảo visibility của cờ.
3. Worker ngủ tối đa 10 giây. Main quan sát `TIMED_WAITING`, rồi `interrupt()` để kết thúc sớm; không cần chờ đủ 10 giây.

`awaitState` chỉ dùng cho **thí nghiệm**. Nó polling snapshot có deadline và có thể ném exception nếu máy cực kỳ bận hoặc thread bị tác động ngoài dự kiến. Trong production, **không viết logic điều khiển ứng dụng bằng cách đoán thread state với `getState()`**; dùng `join`, `CountDownLatch`, `Future`, `Condition` hoặc các cơ chế phối hợp theo điều kiện thực tế. Các trạng thái có thể đổi rất nhanh giữa hai lần đọc.

## 6. Chuyển trạng thái thường gặp

### Tranh chấp monitor

```text
Thread A: RUNNABLE --vào synchronized(lock) thành công--> RUNNABLE
Thread B: RUNNABLE --không lấy được monitor lock--> BLOCKED
Thread A: ... ra khỏi synchronized(lock), nhả monitor ...
Thread B: BLOCKED --lấy được monitor--> RUNNABLE
```

Đây là luồng diễn giải logic; việc lấy monitor và đổi trạng thái có thể diễn ra rất nhanh, nên sampling không bảo đảm bắt được mọi trạng thái.

### `wait()/notifyAll()`

```text
Consumer giữ monitor M và thấy condition=false
Consumer gọi M.wait(): nhả M, có thể vào WAITING
Producer lấy M, cập nhật condition=true, gọi M.notifyAll()
Consumer được đánh thức nhưng phải lấy lại M
Consumer có thể BLOCKED trong lúc producer còn giữ M
Producer nhả M; consumer lấy lại M, kiểm tra while rồi tiếp tục
```

**`notifyAll()` không trao monitor ngay** cho waiter. Nếu producer tiếp tục giữ `M` lâu, consumer chưa thể chạy phần sau `wait()` dù đã được thông báo. Sau khi nhận thông báo, waiter cũng có thể không phải là thread được scheduler chọn ngay lập tức. Dùng `while` vì tín hiệu chỉ bảo thread kiểm tra lại điều kiện; không thay thế điều kiện.

### Chờ có hạn

```text
RUNNABLE --Thread.sleep(200)--> TIMED_WAITING
TIMED_WAITING --hết thời hạn hoặc interrupt--> RUNNABLE
```

Với `wait(timeout)` hay `join(timeout)`, kết thúc thời hạn **không bảo đảm** điều kiện đã thỏa mãn. Với `wait(timeout)`, thread còn phải lấy lại monitor; với `join(timeout)`, cần kiểm tra `isAlive()` nếu phải biết thread đích có thực sự kết thúc.

## 7. Điều gì xảy ra khi interrupt?

`Thread.interrupt()` là **tín hiệu yêu cầu phối hợp dừng/chuyển hướng**, không phải lệnh giết thread ngay lập tức.

| Hoạt động | Phản ứng điển hình |
| --- | --- |
| `Object.wait()`, `Thread.sleep()`, `Thread.join()` | Ném `InterruptedException` nếu bị interrupt khi chờ và trạng thái interrupt thường bị xóa khi exception được ném |
| `CountDownLatch.await()`, `Future.get()` | Có thể ném `InterruptedException` theo hợp đồng API |
| `LockSupport.park()` | Có thể trở về và giữ cờ interrupt; không ném `InterruptedException` |
| Đang đợi monitor của `synchronized` (`BLOCKED`) | Không thể dùng interrupt để hủy việc lấy intrinsic monitor bằng cú pháp `synchronized` |
| `ReentrantLock.lockInterruptibly()` | Có thể phản hồi interrupt khi chờ lock; khác với `synchronized` |

Khi bắt `InterruptedException` mà không ném tiếp, mã thường nên khôi phục cờ bằng `Thread.currentThread().interrupt()` rồi thoát hoặc chuyển lỗi phù hợp. Không tạo vòng `while(true)` tiếp tục đợi và nuốt interrupt vô hạn. Khi dùng `LockSupport.park()`, chú ý nếu cờ interrupt vẫn đang bật, lần `park()` sau có thể trở về ngay; cần có điều kiện thoát rõ ràng.

## 8. Đọc thread dump đúng cách

Trên HotSpot/OpenJDK, có thể lấy thread dump của JVM bằng JDK diagnostic tools, ví dụ (thay PID thực tế):

```bash
jcmd <PID> Thread.print -l
```

Các đoạn sau **minh họa cấu trúc thông tin thường gặp**, không phải stdout cố định của JDK ở mọi phiên bản:

```text
"worker-1" ... java.lang.Thread.State: BLOCKED (on object monitor)
    - waiting to lock <...> (a java.lang.Object)
"worker-2" ... java.lang.Thread.State: WAITING (parking)
    at jdk.internal.misc.Unsafe.park(...)
"worker-3" ... java.lang.Thread.State: TIMED_WAITING (sleeping)
    at java.lang.Thread.sleep(...)
```

Cần đọc kèm stack trace, monitor/synchronizer đang chờ, thread sở hữu lock, và dấu vết từ các lần dump khác nhau:

- **Nhiều `BLOCKED` trên cùng monitor:** tìm thread đang giữ monitor, vị trí khóa được lấy và thời gian critical section. Nếu nhiều thread tranh cùng một lock lâu, cân nhắc giảm phạm vi `synchronized` hoặc loại bỏ blocking I/O trong critical section.
- **`WAITING` tại `Object.wait`:** xác định condition, đường đi `notify/notifyAll`, liệu producer có thể chạy, có kiểm tra lại condition không.
- **`WAITING` tại `LockSupport.park`:** xem thư viện đồng bộ ở stack trace (`Future`, `ReentrantLock`, queue, pool worker idle...). Thread pool worker rảnh và đang park có thể **hoàn toàn bình thường**.
- **`TIMED_WAITING` tại `sleep`:** tìm lý do ngủ (retry, backoff, lịch, hay code vô tình chặn). `TIMED_WAITING` tại timed queue poll hoặc connection wait có ý nghĩa khác; đọc frame gọi và deadline.
- **Deadlock:** xác định chu trình giữa các thread và lock. `ThreadMXBean.findDeadlockedThreads()` giúp phát hiện một số deadlock liên quan object monitors và ownable synchronizers, nhưng không thay thế phân tích các chu trình chờ logic, mạng, DB hoặc resource bên ngoài.

`Thread.getState()`, thread dump và metrics là công cụ **quan sát**, không dùng để đảm bảo giao thức đồng bộ. Thread state ở cấp Java cũng không tương ứng 1:1 với trạng thái scheduler của hệ điều hành: ví dụ thread ở `RUNNABLE` vẫn có thể đang chờ xử lý tài nguyên hệ điều hành. Sự hiện diện của `WAITING` hoặc `TIMED_WAITING` không tự chứng minh một lỗi hiệu năng.

Trong Java 21+, **virtual thread** cũng có các trạng thái Java ở cấp API, nhưng cơ chế mount/unmount trên carrier và cách các công cụ JVM hiển thị virtual threads có thể khác platform threads. Không suy ra số OS threads chỉ bằng cách đếm virtual threads đang chờ; đọc diagnostics phù hợp với phiên bản JDK. Bài này không dùng API/framework riêng ngoài Java core và Java concurrent utilities.

## 9. Phân biệt chờ monitor với chờ điều kiện

Một tình huống dễ gây khó hiểu:

```java
synchronized (lock) {
    lock.wait();
}
```

Trước lúc gọi `wait`, thread đã **sở hữu monitor**. Khi vào `wait`, nó nhả monitor rồi ở `WAITING`; sau `notifyAll`, nó phải quay lại lấy monitor. Trong khoảng nó cố lấy lại monitor nhưng chưa thành công, trạng thái có thể là `BLOCKED`. Vì vậy, **một thread có thể xuất hiện ở `WAITING` rồi chuyển sang `BLOCKED` trong cùng một chu trình phối hợp**, không có mâu thuẫn.

Ngược lại:

```java
synchronized (lock) {
    Thread.sleep(500);
}
```

Thread đang ngủ có thể ở `TIMED_WAITING` **nhưng vẫn giữ `lock`**. Những thread khác muốn vào `synchronized(lock)` sẽ `BLOCKED`. Đây thường là lý do cần tránh ngủ, gọi HTTP, đọc file hay chờ `Future` dài hạn trong critical section.

Với `ReentrantLock` và `Condition`, `condition.await()` nhả **lock tương ứng với condition** khi đợi và lấy lại trước khi tiếp tục, tương tự mục đích phối hợp của `Object.wait` nhưng API khác. Không suy luận “không thấy `BLOCKED` tức là không có tranh chấp lock”: nhiều lock hiện đại park thread và thể hiện trong `WAITING`.

## 10. Những lỗi thường gặp và cách sửa

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Xem mọi `BLOCKED` là deadlock | Tranh chấp monitor ngắn có thể bình thường | Tìm owner và chu trình chờ; so nhiều thread dump |
| Xem mọi `WAITING` là thread treo | Worker rảnh, chờ queue/signal là trạng thái hợp lệ | Xem stack, điều kiện thoát, thời gian, tải hệ thống |
| Cho rằng `WAITING` chỉ đến từ `Object.wait` | `join`, `park` và nhiều synchronizer cũng chờ | Đọc frame thực tế và tài nguyên liên quan |
| Cho rằng `TIMED_WAITING` là timeout đã xảy ra | Đây là trạng thái **trong lúc** đang chờ có hạn | Kiểm tra kết quả trả về/exception và deadline |
| Gọi `notify` rồi nghĩ waiter có monitor ngay | Waiter còn phải tranh lấy lại monitor | Giữ critical section ngắn và dùng condition-loop |
| Dùng `if (conditionFalse) wait()` | Spurious wakeup, nhiều consumer, condition thay đổi | Dùng `while` kiểm tra điều kiện sau khi thức |
| Gọi `wait` ngoài `synchronized` | `IllegalMonitorStateException` | Giữ đúng monitor trước khi `wait` |
| Cho rằng `sleep` hoặc `park` nhả monitor | Chúng không tự nhả intrinsic monitor | Tránh sleep/I/O/long waits khi giữ monitor |
| Nuốt `InterruptedException` | Bỏ tín hiệu hủy, shutdown khó | Propagate hoặc restore interrupt và thoát hợp lý |
| Dựa vào `getState()` để điều phối production | Race giữa thời điểm đọc và hành động | Dùng `Future`/`CountDownLatch`/queue/condition |
| Dùng `wait(0)` như timeout zero | `wait(0)` có nghĩa đợi vô thời hạn | Dùng timeout dương, kiểm tra đơn vị và deadline |
| Nhầm `ReentrantLock` contention luôn là `BLOCKED` | Có thể dùng park/`WAITING` | Đọc stack và lock metadata |

## 11. Một vài câu hỏi kiểm tra hiểu

**1. Hai thread đều `BLOCKED` có chắc deadlock?** Không. Chúng có thể chờ một thread thứ ba nhả monitor. Chỉ xác nhận deadlock khi có chu trình chờ không thể tiến triển hoặc phát hiện phù hợp qua diagnostics.

**2. Thread gọi `join()` sẽ ở trạng thái gì?** Nếu thread đích còn chạy và caller thực sự phải đợi không timeout, caller có thể ở `WAITING`. `join(timeout dương)` có thể dẫn đến `TIMED_WAITING`. Nếu target đã kết thúc, caller không cần vào trạng thái chờ.

**3. `notifyAll()` có đưa thread từ `WAITING` vào `RUNNABLE` ngay không?** Không nhất thiết. Thread được đánh thức phải lấy lại monitor của `wait`, nên có thể thấy `BLOCKED` trước khi chạy tiếp. Sau khi chạy tiếp vẫn phải kiểm tra condition trong `while`.

**4. `Thread.sleep(1000)` trong `synchronized` giúp thread khác vào monitor không?** Không. Thread ngủ không tự nhả monitor. Thread khác có thể `BLOCKED` trong lúc nó `TIMED_WAITING`.

**5. Thread ở `TIMED_WAITING` có chắc sẽ kết thúc tác vụ sau 1 giây không?** Không. Mốc thời gian chỉ giới hạn một thao tác chờ cụ thể; scheduler, việc lấy lại lock và các bước còn lại của tác vụ có thể làm thời gian tổng dài hơn.

**6. Nhiều `WAITING` trong thread pool có phải đang quá tải?** Không thể kết luận. Worker đang rảnh và đợi việc mới là bình thường. Cần xem active workers, queue depth, throughput, latency, lỗi và stack.

## 12. Checklist áp dụng khi debug Java concurrency

1. Ghi lại **state, stack trace, lock identity và lock owner** của thread liên quan tại nhiều thời điểm.
2. Nếu `BLOCKED`, xác định monitor nào đang bị tranh và vì sao thread giữ monitor lâu.
3. Nếu `WAITING`, xác định cơ chế chờ (monitor, park, join, Future, latch, queue) và điều kiện/tác nhân giải phóng.
4. Nếu `TIMED_WAITING`, xác định timeout được cấu hình, đơn vị, điều kiện kết thúc sớm và hành động khi timeout.
5. Xác minh có giữ monitor khi `sleep`, chờ I/O hoặc park hay không; kiểm tra deadlock lẫn logical stall.
6. Đánh giá interrupt, cancellation, condition-loop, timeout và việc giải phóng tài nguyên.
7. Kết luận từ **nhiều bằng chứng** (thread dumps, JFR, logs, CPU/lock metrics), không từ một giá trị `getState()` đơn lẻ.

**Ghi nhớ:** `BLOCKED` là tranh lấy **intrinsic monitor**; `WAITING` là chờ không đặt hạn trên một cơ chế phối hợp; `TIMED_WAITING` là chờ có thời hạn. Điều quan trọng nhất khi xử lý sự cố là **thread đang đợi điều gì, ai/cái gì làm nó tiến triển, và nó có đang giữ tài nguyên gây nghẽn thread khác không**.