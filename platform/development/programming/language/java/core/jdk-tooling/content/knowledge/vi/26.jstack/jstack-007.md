# Waiting thread trong Java: hiểu trạng thái WAITING và chẩn đoán bằng jstack

**Waiting thread** là thread đang tạm dừng để chờ một hành động hoặc điều kiện từ thread khác. Trong Java, trạng thái này được biểu diễn bằng `Thread.State.WAITING`. Đây thường là hành vi bình thường của chương trình đa luồng: một worker chờ dữ liệu, một thread chờ thread khác kết thúc, hoặc một tác vụ chờ tín hiệu đồng bộ.

Vấn đề xuất hiện khi thread chờ mãi vì tín hiệu không bao giờ tới, điều kiện chia sẻ không được cập nhật đúng, thread giữ một lock cần thiết, hoặc toàn bộ worker trong một thread pool đều chờ các tác vụ mà chính pool đó phải thực hiện. Muốn phân biệt chờ bình thường với treo ứng dụng, cần hiểu cơ chế chờ, cách đánh thức thread và cách đọc thread dump bằng `jstack` hoặc `jcmd`.

## 1. Thread trong Java có những trạng thái nào?

`Thread.State` là enum mô tả trạng thái của một thread tại một thời điểm quan sát. Java định nghĩa sáu trạng thái:

| Trạng thái | Ý nghĩa | Ví dụ |
|---|---|---|
| NEW | Đã tạo nhưng chưa gọi `start()` | `new Thread(task)` |
| RUNNABLE | Đang thực thi hoặc sẵn sàng được JVM lập lịch | Đang chạy code Java |
| BLOCKED | Đang chờ lấy monitor lock để vào hoặc vào lại vùng `synchronized` | Thread khác đang giữ lock |
| WAITING | Chờ vô thời hạn một hành động từ thread khác | `Object.wait()`, `Thread.join()` |
| TIMED_WAITING | Chờ với thời hạn xác định | `sleep()`, `wait(timeout)` |
| TERMINATED | Đã kết thúc thực thi | `run()` hoàn tất |

Các trạng thái này là trạng thái ở mức JVM, không phải bản sao trực tiếp của trạng thái thread trong hệ điều hành. `RUNNABLE` cũng không bảo đảm thread đang chiếm CPU tại đúng thời điểm quan sát.

`Thread.getState()` trả về một snapshot. Trạng thái có thể thay đổi ngay sau khi đọc, vì vậy không dùng kết quả này làm cơ chế đồng bộ hoặc quyết định thay cho lock, condition hay queue.

## 2. Điều gì khiến thread đi vào WAITING?

Theo Java API, một thread có thể vào `WAITING` khi gọi một trong các phương thức sau mà không đặt timeout:

- `Object.wait()`: chờ thread khác gọi `notify()` hoặc `notifyAll()` trên cùng object, hoặc bị interrupt.
- `Thread.join()`: chờ thread được join kết thúc.
- `LockSupport.park()`: tạm dừng cho tới khi có permit/unpark, interrupt hoặc một lần return khác được cho phép.

Nhiều API đồng thời cấp cao cũng dùng cơ chế park ở bên dưới. Vì vậy, thread dump có thể hiển thị `WAITING (parking)` dù code ứng dụng không gọi trực tiếp `Object.wait()`.

Một số tình huống thường gặp:

- Worker của executor đang chờ task mới.
- Consumer đang chờ dữ liệu trong `BlockingQueue.take()`.
- Thread đang chờ `CountDownLatch.await()`.
- Thread đang chờ `Future.get()` hoặc `CompletableFuture.join()`.
- Thread đang chờ một lock condition qua `Condition.await()`.
- Main thread gọi `worker.join()` để đợi worker kết thúc.

Một thread ở trạng thái WAITING không tự động có nghĩa là lỗi. Cần xác định thread đang chờ điều kiện nào và ai có trách nhiệm làm điều kiện đó xảy ra.

## 3. Phân biệt WAITING, BLOCKED và TIMED_WAITING

Ba trạng thái này thường xuất hiện cạnh nhau trong thread dump nhưng mô tả các tình huống khác nhau.

| Trạng thái | Thread đang chờ | Có thời hạn? | Dấu hiệu thường gặp |
|---|---|---|---|
| WAITING | Một hành động/tín hiệu từ thread khác | Không | `Object.wait`, `Thread.join`, `LockSupport.park` |
| BLOCKED | Quyền sở hữu một intrinsic monitor | Không | `waiting to lock`, `BLOCKED (on object monitor)` |
| TIMED_WAITING | Một hành động hoặc thời gian hết hạn | Có | `Thread.sleep`, `wait(timeout)`, `join(timeout)` |

Ví dụ:

~~~java
synchronized (lock) {
    lock.wait();          // WAITING
}

Thread.sleep(1_000);      // TIMED_WAITING

synchronized (lock) {
    // Nếu thread khác đang giữ lock, thread này ở BLOCKED
}
~~~

`wait()` và `sleep()` không tương đương. `wait()` được gọi trên monitor và giải phóng monitor đó trong lúc chờ. `sleep()` tạm dừng thread nhưng không tự giải phóng bất kỳ monitor lock nào mà thread đang giữ.

## 4. Cơ chế Object.wait() hoạt động thế nào?

`wait()` phải được gọi bởi thread đang sở hữu monitor của object. Thông thường, lời gọi nằm bên trong khối `synchronized` trên chính object đó.

Khi gọi `lock.wait()`, JVM thực hiện các bước chính:

1. Kiểm tra thread hiện tại có sở hữu monitor của `lock` hay không.
2. Đưa thread vào wait set của object.
3. Giải phóng các quyền đồng bộ mà thread đang giữ trên chính object đó.
4. Tạm dừng thread cho tới khi được notify, notifyAll, interrupt, timeout hoặc thức dậy ngoài dự kiến.
5. Thread cạnh tranh để lấy lại monitor.
6. Chỉ sau khi lấy lại monitor, lời gọi `wait()` mới trả về hoặc ném `InterruptedException`.

Lưu ý quan trọng: `wait()` chỉ giải phóng monitor của object được gọi. Nếu thread đang giữ một lock khác, lock đó vẫn có thể bị giữ trong suốt thời gian chờ. Đây là nguồn gốc của nhiều tình huống deadlock khó nhận ra.

## 5. Vì sao notify() không làm thread chạy ngay?

`notify()` đánh thức một thread đang chờ trên monitor hiện tại. `notifyAll()` đánh thức tất cả thread đang chờ trên monitor đó.

Thread được đánh thức chưa thể tiếp tục ngay. Nó phải đợi thread đang sở hữu monitor nhả lock, sau đó mới cạnh tranh để lấy lock. Thứ tự thread được chọn bởi `notify()` không được bảo đảm.

Cả `notify()` và `notifyAll()` phải được gọi khi thread hiện tại sở hữu cùng monitor. Nếu không, JVM ném `IllegalMonitorStateException`.

Ví dụ:

~~~java
synchronized (lock) {
    ready = true;
    lock.notifyAll();
}
~~~

Cập nhật điều kiện và phát tín hiệu trong cùng critical section giúp tránh race condition. Không nên gọi notify trước rồi mới cập nhật trạng thái ở ngoài monitor.

## 6. Mẫu wait/notify đúng: kiểm tra điều kiện trong while

Không viết:

~~~java
synchronized (lock) {
    if (!ready) {
        lock.wait();
    }
    useResource();
}
~~~

Cách viết này sai vì thread có thể thức dậy ngoài dự kiến (spurious wakeup), hoặc một thread khác đã tiêu thụ điều kiện trước khi thread hiện tại chạy tiếp. Khi đó code có thể tiếp tục dù điều kiện chưa đúng.

Hãy dùng `while`:

~~~java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
    useResource();
}
~~~

Vòng lặp kiểm tra lại điều kiện sau mỗi lần thức dậy. Nếu điều kiện vẫn chưa đúng, thread tiếp tục chờ.

Producer cũng phải cập nhật trạng thái dưới cùng monitor:

~~~java
synchronized (lock) {
    ready = true;
    lock.notifyAll();
}
~~~

Monitor bảo đảm thao tác cập nhật và kiểm tra trạng thái được đồng bộ. Việc thoát khỏi khối synchronized của producer happens-before lần lấy lại cùng monitor của consumer, giúp consumer nhìn thấy cập nhật đã công bố.

## 7. Tránh lost notification

Một lỗi phổ biến là thread gửi tín hiệu trước khi consumer bắt đầu chờ. Nếu chỉ dùng notify mà không lưu trạng thái điều kiện, tín hiệu có thể bị mất.

Mẫu không an toàn:

~~~java
// Producer
lock.notify();

// Consumer
lock.wait();
~~~

`notify()` không phải một message được lưu lại để thread đến sau nhận được. Nó chỉ đánh thức thread đang nằm trong wait set tại thời điểm gọi.

Mẫu an toàn lưu trạng thái điều kiện:

~~~java
// Producer
synchronized (lock) {
    ready = true;
    lock.notifyAll();
}

// Consumer
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
}
~~~

Nếu producer chạy trước, consumer nhìn thấy `ready == true` và không cần chờ. Nếu consumer chạy trước, nó đưa mình vào wait set; producer cập nhật trạng thái và đánh thức nó. Hai bên dùng cùng monitor nên không có khoảng hở giữa kiểm tra và đăng ký chờ.

## 8. Vì sao nên dùng notifyAll() khi có nhiều loại waiter?

`notify()` chỉ chọn một waiter bất kỳ. Nếu nhiều thread chờ những điều kiện khác nhau trên cùng monitor, thread được chọn có thể không phải thread có thể tiếp tục xử lý điều kiện vừa thay đổi.

Ví dụ, một monitor có consumer chờ dữ liệu và producer chờ chỗ trống. Nếu notify đánh thức nhầm nhóm, thread đó có thể kiểm tra điều kiện rồi ngủ lại, trong khi thread cần chạy vẫn tiếp tục chờ.

`notifyAll()` đánh thức tất cả waiter để mỗi thread kiểm tra lại điều kiện trong vòng while. Cách này thường dễ đúng hơn khi nhiều điều kiện chia sẻ một monitor, dù có thể làm nhiều thread cùng thức dậy và tranh lock.

Với hệ thống có nhiều điều kiện độc lập, cân nhắc dùng `ReentrantLock` và nhiều `Condition` riêng, hoặc dùng các abstraction như queue và semaphore để thể hiện đúng mô hình.

## 9. Interrupt là một cách yêu cầu thread dừng chờ

`interrupt()` là tín hiệu yêu cầu thread hủy hoặc dừng hoạt động hiện tại. Nếu thread đang chờ trong `Object.wait()`, `Thread.sleep()` hoặc `Thread.join()`, nó thường nhận `InterruptedException`.

Khi `InterruptedException` được ném từ các phương thức này, interrupt status của thread bị xóa. Nếu catch exception và không truyền tiếp, code cần khôi phục trạng thái interrupt khi phù hợp:

~~~java
try {
    lock.wait();
} catch (InterruptedException exception) {
    Thread.currentThread().interrupt();
    return;
}
~~~

Nếu method có thể khai báo `throws InterruptedException`, thường nên truyền exception lên caller để tầng điều phối quyết định hủy tác vụ. Nếu không thể truyền, khôi phục interrupt status thay vì nuốt tín hiệu.

Không dùng `Thread.stop()` để kết thúc thread. Dùng interrupt và một quy trình shutdown có kiểm soát.

## 10. WAITING có timeout và TIMED_WAITING

Nếu chỉ muốn chờ trong một khoảng thời gian, dùng `wait(timeout)` hoặc API có timeout tương ứng. Thread khi đó thường ở `TIMED_WAITING`.

Ví dụ:

~~~java
synchronized (lock) {
    while (!ready) {
        lock.wait(2_000);
    }
}
~~~

Timeout không bảo đảm điều kiện đã đúng. Sau khi hết thời gian, thread vẫn phải kiểm tra lại trạng thái.

Nếu cần chờ một deadline tổng thể trong khi có thể thức dậy nhiều lần, tính thời gian còn lại bằng `System.nanoTime()`. Không lặp lại timeout đầy đủ sau mỗi lần spurious wakeup vì tổng thời gian chờ có thể dài hơn dự kiến.

~~~java
long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);

synchronized (lock) {
    while (!ready) {
        long remaining = deadline - System.nanoTime();
        if (remaining <= 0) {
            break;
        }
        TimeUnit.NANOSECONDS.timedWait(lock, remaining);
    }
}
~~~

Trong ứng dụng thực tế, cân nhắc dùng `Condition.awaitNanos()`, `CountDownLatch.await(timeout, unit)` hoặc API có deadline thay vì tự viết primitive đồng bộ hóa.

## 11. Dùng concurrency utility thay cho wait/notify thủ công

`wait/notify` hữu ích để hiểu monitor, nhưng nhiều bài toán có abstraction an toàn và dễ đọc hơn trong `java.util.concurrent`.

| API | Mô hình chờ | Khi phù hợp |
|---|---|---|
| CountDownLatch | Chờ một số sự kiện hoàn tất | Chờ nhiều bước khởi tạo |
| CyclicBarrier | Nhiều thread gặp nhau tại một điểm | Chia công việc theo pha |
| BlockingQueue | Consumer chờ phần tử; producer chờ chỗ trống | Pipeline producer/consumer |
| Semaphore | Chờ permit | Giới hạn số tác vụ đồng thời |
| ReentrantLock + Condition | Chờ điều kiện gắn với lock | Nhiều điều kiện đồng bộ |
| Future.get | Chờ kết quả tác vụ | Tích hợp API đồng bộ |
| CompletableFuture | Kết nối các bước bất đồng bộ | Pipeline async |
| Thread.join | Chờ thread kết thúc | Điều phối thread đơn giản |

Ví dụ consumer chờ queue:

~~~java
BlockingQueue<String> queue = new LinkedBlockingQueue<>();

String message = queue.take();
System.out.println("RECEIVED=" + message);
~~~

`take()` tự chờ khi queue rỗng và được đánh thức khi có phần tử. Điều này diễn đạt ý định rõ hơn việc tự quản lý monitor, cờ trạng thái và notify.

## 12. Thread pool có thể có WAITING thread bình thường

Thread pool thường giữ worker thread ở trạng thái chờ khi không có task. Thread dump có thể cho thấy worker đang park trong queue hoặc executor. Đây thường là trạng thái nhàn rỗi đúng thiết kế.

Tuy nhiên, thread pool có thể bị starvation nếu mọi worker đều chờ đồng bộ các task khác được submit vào chính pool đó.

Ví dụ về tình huống nguy hiểm:

1. Pool có hai worker.
2. Hai task cha chiếm cả hai worker.
3. Mỗi task cha submit một task con vào cùng pool.
4. Mỗi task cha gọi get() để đợi task con.
5. Không còn worker rảnh để chạy hai task con.

Các thread cha đều WAITING, task con nằm trong queue và không thể bắt đầu. Đây là thread starvation deadlock dù không nhất thiết có chu trình monitor deadlock.

Tránh chặn worker chờ tác vụ con trong cùng pool có giới hạn nhỏ. Dùng composition với `CompletableFuture`, tách executor theo loại công việc hoặc thiết kế pipeline không chặn khi phù hợp.

## 13. Đọc thread dump để tìm waiting thread

Thread dump là snapshot của stack trace và trạng thái các thread trong một JVM. Nó giúp trả lời:

- Thread nào đang WAITING?
- Thread đang chờ tại method nào?
- Nó đang chờ monitor, synchronizer hay kết quả task?
- Thread nào đang giữ lock mà thread khác cần?
- Stack trace có thay đổi giữa các lần chụp không?
- JVM có phát hiện Java-level deadlock không?

Trong dump, tìm tên thread trước rồi đọc trạng thái và stack trace ngay bên dưới. Ví dụ:

~~~text
"demo-waiter" #35 prio=5 ...
   java.lang.Thread.State: WAITING (on object monitor)
    at java.lang.Object.wait(...)
    at WaitingThreadDemo.lambda$main$0(WaitingThreadDemo.java:19)
    - waiting on <0x...> (a java.lang.Object)
~~~

Stack trace chỉ ra thread đang chờ tại `Object.wait()` trong `WaitingThreadDemo`. Nếu thread ở `WAITING (parking)`, tìm các frame như `LockSupport.park`, `AbstractQueuedSynchronizer`, `CountDownLatch` hoặc `FutureTask` để hiểu abstraction đang chờ.

## 14. Tìm JVM process bằng jcmd hoặc jps

Dùng `jcmd -l` để liệt kê JVM đang chạy:

~~~bash
jcmd -l
~~~

Hoặc:

~~~bash
jps -l
~~~

Kết quả thường có process ID và main class. Chọn đúng PID của ứng dụng cần kiểm tra. Nếu chạy trong container, PID namespace có thể khác với PID trên host; thực hiện lệnh trong đúng môi trường hoặc dùng cơ chế truy cập process phù hợp.

`jcmd` cần chạy trên cùng máy với JVM đích và thường cần cùng effective user/group đã khởi chạy JVM. Nếu attach bị từ chối, kiểm tra user, container, quyền hệ điều hành và cấu hình JVM thay vì kết luận ứng dụng không có thread.

## 15. Dùng jcmd Thread.print

Trên JDK hiện đại, Oracle khuyến nghị ưu tiên `jcmd` cho chẩn đoán JVM.

Lấy thread dump:

~~~bash
jcmd -l
jcmd 12345 Thread.print
~~~

Thêm `-l` để in thông tin về các lock của `java.util.concurrent`:

~~~bash
jcmd 12345 Thread.print -l
~~~

Trên PowerShell, có thể tìm PID theo tên main class:

~~~powershell
$jvm = jcmd -l | Select-String 'WaitingThreadDemo' | Select-Object -First 1
$javaPid = ($jvm.ToString() -split '\s+')[0]
jcmd $javaPid Thread.print -l
~~~

Thay tên class trong bộ lọc bằng tên ứng dụng đang chạy. Kiểm tra danh sách PID trước khi gửi lệnh để tránh đọc nhầm JVM.

## 16. Dùng jstack -l

`jstack` là công cụ JDK truyền thống để in stack trace của các thread trong JVM:

~~~bash
jstack -l 12345
~~~

Tùy chọn `-l` yêu cầu in thêm thông tin ownable synchronizer và lock của `java.util.concurrent`. Không có tùy chọn này, thread dump tập trung vào monitor.

Oracle JDK hiện khuyến nghị dùng `jcmd` cho chẩn đoán JVM thông thường. `jstack` vẫn hữu ích để học, đọc tài liệu cũ và xử lý môi trường đang dùng quy trình dựa trên công cụ này. Với core dump, công cụ tương ứng là `jhsdb jstack`.

Không chụp thread dump liên tục trong vòng lặp quá nhanh. Hãy lấy một vài snapshot cách nhau vài giây để xem thread đang tiến triển, thay đổi lock owner hay mắc kẹt ở cùng stack.

## 17. Nhận diện các dấu hiệu trong thread dump

| Dấu hiệu | Có thể đang xảy ra | Cần kiểm tra |
|---|---|---|
| `WAITING (on object monitor)` | Đang chờ `wait()` | Điều kiện, notify, lock owner |
| `WAITING (parking)` | Chờ synchronizer/park | Queue, latch, future, condition |
| `TIMED_WAITING (sleeping)` | Đang sleep | Có phải delay dự kiến hay retry loop? |
| `TIMED_WAITING (on object monitor)` | `wait(timeout)` hoặc cơ chế tương tự | Timeout, điều kiện sau khi thức dậy |
| `BLOCKED (on object monitor)` | Chờ vào synchronized | Thread đang giữ monitor và thời gian giữ lock |
| `RUNNABLE` với stack I/O | Có thể đang thực hiện hoặc chờ native I/O | Socket, filesystem, external service |
| Nhiều worker cùng chờ Future | Có thể starvation hoặc dependency chain | Executor size và task submission |

Một dòng `- waiting to lock` thường chỉ ra monitor mà thread đang cần. Dòng `- locked` chỉ ra monitor thread đang giữ tại frame tương ứng. Với synchronizer của `java.util.concurrent`, dùng dump có lock information để xem thêm owner/waiter khi JVM cung cấp.

## 18. Phân biệt chờ bình thường, treo và deadlock

Một thread WAITING có thể hoàn toàn bình thường nếu có thread khác sẽ đánh thức nó khi dữ liệu hoặc điều kiện xuất hiện.

Dấu hiệu đáng điều tra:

- Thread chờ lâu hơn SLA hoặc timeout dự kiến.
- Không còn producer/worker nào có thể tạo điều kiện mà consumer đang đợi.
- Tất cả worker của pool đều WAITING trong khi queue vẫn còn task.
- Nhiều thread chờ cùng một monitor và owner không tiến triển.
- Stack trace của các snapshot liên tiếp không thay đổi.
- Ứng dụng không phản hồi dù CPU thấp và không có I/O tiến triển.

Deadlock thường có chu trình phụ thuộc lock: thread A giữ lock 1 chờ lock 2, trong khi thread B giữ lock 2 chờ lock 1. Thread dump có thể in thông báo `Found one Java-level deadlock`.

Starvation hoặc chờ tín hiệu bị mất có thể làm ứng dụng treo mà không có monitor deadlock. Vì vậy, thông báo `No deadlocks found` không chứng minh toàn bộ ứng dụng đang khỏe mạnh.

## 19. Chụp nhiều snapshot và so sánh

Một thread dump là ảnh chụp tại một thời điểm. Để chẩn đoán, hãy chụp vài lần cách nhau một khoảng ngắn:

~~~bash
jcmd 12345 Thread.print -l > dump-1.txt
sleep 5
jcmd 12345 Thread.print -l > dump-2.txt
sleep 5
jcmd 12345 Thread.print -l > dump-3.txt
~~~

So sánh tên thread, trạng thái, stack frame, lock owner và queue/task count nếu ứng dụng có metrics. Nếu stack thay đổi, thread có thể đang tiến triển chậm. Nếu mọi snapshot giữ nguyên cùng một điểm chờ, cần truy tìm điều kiện đánh thức và thread chịu trách nhiệm phát tín hiệu.

Không đưa thread dump chứa dữ liệu nhạy cảm lên nơi công khai. Stack trace có thể để lộ tên class nội bộ, đường dẫn, URL hoặc thông tin môi trường.

## 20. Kiểm tra deadlock bằng ThreadMXBean

JDK Management API cung cấp cách phát hiện deadlock từ trong chương trình. Ví dụ sau kiểm tra monitor và ownable synchronizer:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;

public final class DeadlockCheck {
    private DeadlockCheck() {
    }

    public static void main(String[] args) {
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        long[] ids = bean.findDeadlockedThreads();

        if (ids == null || ids.length == 0) {
            System.out.println("DEADLOCKS=0");
            return;
        }

        ThreadInfo[] infos = bean.getThreadInfo(ids, true, true);
        for (ThreadInfo info : infos) {
            System.out.println("DEADLOCK_THREAD=" + info.getThreadName());
            System.out.println(info);
        }
    }
}
~~~

`findDeadlockedThreads()` tìm chu trình deadlock liên quan monitor hoặc ownable synchronizer. `findMonitorDeadlockedThreads()` chỉ tìm monitor deadlock. Đây là kiểm tra chẩn đoán; không thay thế thiết kế lock đúng hoặc giám sát thời gian chờ nghiệp vụ.

## 21. Virtual thread và trạng thái chờ

Virtual thread có từ Java 21. Chúng phù hợp với tác vụ có nhiều thời gian chờ I/O vì JVM có thể tạm unmount virtual thread khỏi carrier thread trong nhiều thao tác blocking được hỗ trợ.

Một virtual thread ở WAITING không nhất thiết chiếm một platform thread trong suốt thời gian chờ. Điều này giúp ứng dụng phục vụ nhiều tác vụ blocking với ít platform thread hơn.

Tuy nhiên, virtual thread không làm mất các vấn đề đồng bộ hóa: lost notification, deadlock, giữ lock quá lâu, starvation do tài nguyên hữu hạn hoặc chờ future không có deadline vẫn có thể xảy ra.

Công cụ và định dạng thread dump có thể khác theo phiên bản JDK. Trên JDK mới, `jcmd Thread.print` hiển thị platform thread và virtual thread đang mounted; `Thread.dump_to_file` có thể dùng để ghi dump ra file khi cần kiểm tra đầy đủ hơn theo hỗ trợ của runtime.

## 22. Ví dụ Java 17+: tạo một thread WAITING có kiểm soát

Ví dụ dưới đây tạo một thread tên `demo-waiter`. Thread này chờ trên một monitor cho đến khi main thread cập nhật điều kiện và gọi `notifyAll()`. Tham số `--interrupt` kiểm tra đường hủy bằng interrupt; `--hold` giữ thread chờ vài giây để có thời gian chụp thread dump.

File `WaitingThreadDemo.java`:

~~~java
import java.util.concurrent.TimeUnit;

public final class WaitingThreadDemo {
    private static final Object MONITOR = new Object();
    private static boolean released;

    private WaitingThreadDemo() {
    }

    public static void main(String[] args) throws InterruptedException {
        boolean holdForDump = args.length > 0 && "--hold".equals(args[0]);
        boolean interruptWaiter = args.length > 0 && "--interrupt".equals(args[0]);

        Thread waiter = new Thread(() -> {
            synchronized (MONITOR) {
                System.out.println("WAITER_READY");
                try {
                    while (!released) {
                        MONITOR.wait();
                    }
                    System.out.println("WAITER_RESUMED");
                } catch (InterruptedException exception) {
                    Thread.currentThread().interrupt();
                    System.out.println("WAITER_INTERRUPTED");
                    System.out.println("INTERRUPT_RESTORED="
                            + Thread.currentThread().isInterrupted());
                }
            }
        }, "demo-waiter");

        waiter.start();

        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while (waiter.getState() != Thread.State.WAITING
                && System.nanoTime() < deadline) {
            Thread.onSpinWait();
        }

        if (waiter.getState() != Thread.State.WAITING) {
            throw new IllegalStateException("Waiter did not enter WAITING state");
        }
        System.out.println("OBSERVED_STATE=" + waiter.getState());

        if (interruptWaiter) {
            waiter.interrupt();
        } else {
            if (holdForDump) {
                System.out.println("READY_FOR_THREAD_DUMP");
                Thread.sleep(5000);
            }

            synchronized (MONITOR) {
                released = true;
                MONITOR.notifyAll();
            }
        }

        waiter.join();
        System.out.println("MAIN_DONE");
    }
}
~~~

Biên dịch bằng JDK 17 trở lên:

~~~bash
javac --release 17 -Xlint:all -Werror WaitingThreadDemo.java
~~~

Chạy bình thường:

~~~bash
java WaitingThreadDemo
~~~

Output chính xác:

~~~text
WAITER_READY
OBSERVED_STATE=WAITING
WAITER_RESUMED
MAIN_DONE
~~~

Chạy đường interrupt:

~~~bash
java WaitingThreadDemo --interrupt
~~~

Output chính xác:

~~~text
WAITER_READY
OBSERVED_STATE=WAITING
WAITER_INTERRUPTED
INTERRUPT_RESTORED=true
MAIN_DONE
~~~

Chương trình dùng vòng spin rất ngắn chỉ để bài thực hành quan sát được trạng thái WAITING một cách xác định. Không dùng polling `Thread.getState()` như cơ chế phối hợp thread trong ứng dụng thật; hãy dùng latch, condition, queue hoặc lock.

## 23. Chụp jstack và jcmd cho ví dụ

Để giữ waiter ở trạng thái WAITING trong vài giây, chạy:

~~~bash
java WaitingThreadDemo --hold
~~~

Trong terminal khác, tìm PID:

~~~bash
jcmd -l
~~~

Sau đó chạy:

~~~bash
jcmd 12345 Thread.print -l
jstack -l 12345
~~~

Thay PID ví dụ bằng PID của tiến trình `WaitingThreadDemo`. Trên PowerShell có thể lọc PID tự động:

~~~powershell
$jvm = jcmd -l | Select-String 'WaitingThreadDemo' | Select-Object -First 1
$javaPid = ($jvm.ToString() -split '\s+')[0]
jcmd $javaPid Thread.print -l
jstack -l $javaPid
~~~

Trong output, tìm thread `demo-waiter`. Dòng quan trọng sẽ có dạng:

~~~text
"demo-waiter" #35 ...
   java.lang.Thread.State: WAITING (on object monitor)
    at java.lang.Object.wait(...)
    at WaitingThreadDemo.lambda$main$0(WaitingThreadDemo.java:...)
~~~

Sau khi chụp dump, chương trình tự đánh thức waiter và kết thúc. Với ứng dụng thật, không tự giả định một thread dump có thể chỉ ra nguyên nhân duy nhất; cần ghép stack trace với trạng thái lock, metrics và log của nghiệp vụ.

## 24. Lỗi phổ biến khi làm việc với waiting thread

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Gọi wait ngoài synchronized | IllegalMonitorStateException | Giữ đúng monitor khi gọi wait |
| Gọi notify trên object khác | Waiter không được đánh thức | Dùng cùng object làm monitor |
| Dùng if thay vì while | Tiếp tục dù điều kiện chưa đúng | Kiểm tra điều kiện trong while |
| Notify trước khi cập nhật trạng thái | Consumer có thể thấy trạng thái cũ | Cập nhật và notify trong cùng synchronized |
| Catch InterruptedException rồi bỏ qua | Mất tín hiệu hủy | Truyền tiếp hoặc restore interrupt |
| Giữ lock khác trong lúc wait | Thread khác có thể không lấy được lock cần thiết | Giảm phạm vi synchronized, tránh lồng lock |
| Dùng sleep để chờ thread khác | Race condition và test không ổn định | Dùng latch, condition hoặc join |
| Chờ Future trong cùng executor đã bão hòa | Thread starvation deadlock | Dùng async composition hoặc executor phù hợp |
| Thấy WAITING rồi kết luận deadlock | Chẩn đoán sai | Kiểm tra điều kiện chờ, owner và nhiều snapshot |
| Chỉ chụp một thread dump | Bỏ lỡ trạng thái thay đổi | So sánh nhiều snapshot theo thời gian |

## 25. Quy trình chẩn đoán waiting thread trong ứng dụng

Khi một request hoặc tác vụ bị treo, thực hiện lần lượt:

1. Xác định JVM process và thời điểm bắt đầu chậm.
2. Lấy thread dump bằng `jcmd Thread.print -l` hoặc `jstack -l`.
3. Tìm thread liên quan theo tên, request ID hoặc stack frame.
4. Ghi nhận trạng thái WAITING/BLOCKED/TIMED_WAITING.
5. Xác định API chờ: Object.wait, join, park, latch, queue hay Future.
6. Tìm thread có trách nhiệm phát tín hiệu hoặc hoàn thành task.
7. Kiểm tra lock owner, queue length, executor active count và timeout.
8. Chụp thêm snapshot sau vài giây để xác định thread có tiến triển không.
9. Kiểm tra deadlock và starvation; không chỉ tìm monitor cycle.
10. Tạo test tái hiện, sửa nguyên nhân và thêm regression test.

Nếu cần phân tích sự kiện theo thời gian, Java Flight Recorder và JDK Mission Control có thể bổ sung thread sample, lock profile và thông tin runtime. Thread dump là snapshot; JFR giúp quan sát hành vi trong một khoảng thời gian.

## 26. Checklist review code có waiting thread

- [ ] Mọi lời gọi `Object.wait()` nằm trong synchronized trên đúng object.
- [ ] Điều kiện chờ được kiểm tra trong vòng while.
- [ ] Producer cập nhật trạng thái và notify dưới cùng monitor.
- [ ] Không giữ lock không cần thiết trong khi chờ.
- [ ] Interrupt được truyền tiếp hoặc khôi phục đúng cách.
- [ ] Chờ có timeout/deadline khi nghiệp vụ yêu cầu giới hạn thời gian.
- [ ] Thread pool không bị bão hòa bởi các task chờ task con đồng bộ.
- [ ] API cấp cao như BlockingQueue, CountDownLatch hoặc Condition được cân nhắc.
- [ ] Thread được đặt tên để dễ nhận diện trong dump.
- [ ] Có cách chụp và đọc thread dump trong môi trường chạy.
- [ ] Deadlock, starvation và chờ tín hiệu bị mất được phân biệt.
- [ ] Test xác nhận cả đường đánh thức bình thường và đường interrupt.

## Tài liệu tham khảo

- Oracle Java SE 26 — [Thread.State](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Thread.State.html).
- Oracle Java SE 26 — [Object.wait(), notify() và notifyAll()](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Object.html).
- Oracle Java SE 26 — [Thread và Interruption](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Thread.html).
- Oracle JDK 26 — [The jcmd Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html).
- Oracle JDK 26 — [Diagnostic Tools: jstack, Thread Dumps và Deadlock Detection](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html).
- Dev.java — [Concurrency](https://dev.java/learn/concurrency/).
