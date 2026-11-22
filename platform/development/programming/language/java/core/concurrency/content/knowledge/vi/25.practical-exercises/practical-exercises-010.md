# Bài tập thực tế: Đọc thread dump và tìm vị trí chặn luồng

## Mục tiêu

Khi một ứng dụng Java còn sống nhưng một yêu cầu hoặc một worker không hoàn thành, **thread dump** cho thấy mỗi thread đang làm gì và call stack nào dẫn nó tới trạng thái hiện tại. Đây là công cụ phân tích của JDK, không phải cơ chế tự khôi phục tiến trình.

Kết thúc bài này, bạn cần thực hiện được quy trình: **tìm đúng JVM → lấy dump → tìm thread bị ảnh hưởng → đọc trạng thái và stack → tìm monitor/điều kiện đang đợi → lần theo chủ sở hữu hoặc bên phát tín hiệu → chỉ ra vị trí code cần kiểm tra → kiểm chứng cách sửa**.

Bài thực hành sử dụng Java 17+ và JDK tools, không sử dụng Spring.

## 1. Hiểu trạng thái và dữ liệu trong thread dump

Thread dump truyền thống có header cho từng thread, trạng thái, stack trace và tùy công cụ/phiên bản có thông tin monitor hoặc synchronizer.

| Trạng thái | Thường có nghĩa gì | Nên làm gì |
|---|---|---|
| **RUNNABLE** | Có khả năng chạy; cũng có thể ở native/I/O call. | Xem stack, CPU và thông tin I/O. |
| **BLOCKED** | Đang chờ lấy **object monitor** của synchronized. | Tìm monitor ID và thread đang giữ nó. |
| **WAITING** | Chờ không timeout ở wait, join, park, latch hoặc future. | Tìm ai phát tín hiệu hoặc hoàn thành tác vụ. |
| **TIMED_WAITING** | Chờ có timeout, ví dụ sleep hoặc timed park. | Kiểm tra deadline và hành vi sau timeout. |
| **NEW** | Thread chưa start. | Kiểm tra lifecycle. |
| **TERMINATED** | Thread đã xong. | Xem lỗi/lifecycle nếu liên quan. |

**BLOCKED không tự chứng minh deadlock.** Nó có thể là contention bình thường: một thread giữ monitor vài millisecond, thread khác tạm thời phải đợi. Tương tự **WAITING không nhất thiết là sự cố**; worker chờ queue rỗng có thể hoàn toàn đúng thiết kế.

Một điều dễ nhầm: **ReentrantLock.lock()** thường chờ thông qua **LockSupport.park()** nên có thể xuất hiện ở trạng thái **WAITING** thay vì **BLOCKED**. Phải đọc stack để nhận diện primitive chờ.

### Ví dụ dump rút gọn (minh họa, không phải output nguyên văn cố định)

~~~text
"worker-B" ... java.lang.Thread.State: BLOCKED (on object monitor)
    at sample.Cache.refresh(Cache.java:81)
    - waiting to lock <0xABC> (a java.lang.Object)

"worker-A" ... java.lang.Thread.State: WAITING (parking)
    at java.util.concurrent.CountDownLatch.await(...)
    at sample.Cache.hold(Cache.java:57)
    - locked <0xABC> (a java.lang.Object)
~~~

Từ hai đoạn này, **worker-B** không lấy được monitor định danh **0xABC**, trong khi **worker-A** đang giữ monitor đó và chờ latch. Vị trí bị chặn của B là **Cache.java:81**; nguyên nhân sâu hơn có thể nằm ở **Cache.java:57** hoặc ở thread chịu trách nhiệm mở latch. Chưa có đủ bằng chứng tồn tại vòng deadlock.

## 2. Lấy thread dump từ đúng tiến trình

Đầu tiên liệt kê JVM mà công cụ nhìn thấy:

~~~bash
jcmd -l
~~~

Đối chiếu PID với main class, tham số chạy và môi trường. Trong container, PID namespace, quyền attach và image chỉ chứa JRE có thể ảnh hưởng khả năng dùng công cụ.

Chụp dump với Java 17+ trên HotSpot:

~~~bash
jcmd <PID> Thread.print -l
~~~

**<PID>** là placeholder, thay bằng số PID thực. Tùy chọn **-l** yêu cầu in thêm thông tin lock thuộc java.util.concurrent mà công cụ hỗ trợ. Có thể ghi output vào file bằng redirect của terminal. Nếu máy có công cụ **jstack**, cũng có thể dùng:

~~~bash
jstack -l <PID>
~~~

Kiểm tra khả năng của JVM đích bằng:

~~~bash
jcmd <PID> help
~~~

Nếu lỗi không xuất hiện ở thời điểm chụp, dump có thể không chứa trạng thái cần tìm. Với lỗi kéo dài, lấy **2–3 dump** cách nhau theo khoảng phù hợp và đối chiếu cùng thread/stack. Không quét thread liên tục trong từng request vì việc thu dữ liệu có overhead.

### Java 21+ và virtual threads

Khi ứng dụng sử dụng virtual threads, JDK 21+ có lệnh:

~~~bash
jcmd <PID> Thread.dump_to_file -format=text threads.txt
jcmd <PID> Thread.dump_to_file -format=json threads.json
~~~

Dạng dump này hỗ trợ nhiều virtual threads nhưng cấu trúc và chi tiết lock khác **Thread.print -l**, nhất là ở các phiên bản JDK ban đầu. **Không áp dụng lệnh Thread.dump_to_file của Java 21+ cho Java 17** nếu chưa kiểm tra phiên bản/hỗ trợ của JVM mục tiêu.

## 3. Thực hành A: dựng tình huống thread bị chặn

Chúng ta tạo bốn thread:

- **demo-owner** nắm monitor **gate** trong lúc chờ một CountDownLatch.
- **demo-blocked** cố vào synchronized(gate), nên phải chờ demo-owner.
- **demo-waiting** đợi một latch riêng và không tranh chấp gate.
- **demo-sleeping** ngủ có thời hạn.

**Đây là bài thực hành có chủ đích, không phải đoạn code mẫu cho môi trường production.** Main có đường mở các latch, nên đây không phải deadlock bất biến.

Tạo file **DumpExercise.java**:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.concurrent.CountDownLatch;

public final class DumpExercise {
    static void hold(Object gate, CountDownLatch entered,
                     CountDownLatch release) {
        synchronized (gate) {
            entered.countDown();
            try {
                release.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }
    }

    static void enter(Object gate) {
        synchronized (gate) {
            // Chỉ chạy khi đã lấy được monitor.
        }
    }

    static void waitOnLatch(CountDownLatch signal) {
        try {
            signal.await();
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        }
    }

    public static void main(String[] args) throws Exception {
        Object gate = new Object();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch releaseOwner = new CountDownLatch(1);
        CountDownLatch releaseWaiter = new CountDownLatch(1);

        Thread owner = new Thread(
                () -> hold(gate, entered, releaseOwner), "demo-owner");
        Thread blocked = new Thread(
                () -> enter(gate), "demo-blocked");
        Thread waiting = new Thread(
                () -> waitOnLatch(releaseWaiter), "demo-waiting");
        Thread sleeping = new Thread(() -> {
            try {
                Thread.sleep(30_000);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "demo-sleeping");

        owner.start();
        entered.await();
        blocked.start();
        waiting.start();
        sleeping.start();

        ThreadMXBean mx = ManagementFactory.getThreadMXBean();
        long[] ids = {owner.getId(), blocked.getId(),
                      waiting.getId(), sleeping.getId()};

        try {
            ThreadInfo[] snapshot = null;
            boolean ready = false;
            for (int attempt = 0; attempt < 200; attempt++) {
                snapshot = mx.getThreadInfo(ids, 16);
                ready = snapshot[0] != null && snapshot[1] != null
                        && snapshot[2] != null && snapshot[3] != null
                        && snapshot[0].getThreadState() == Thread.State.WAITING
                        && snapshot[1].getThreadState() == Thread.State.BLOCKED
                        && snapshot[2].getThreadState() == Thread.State.WAITING
                        && snapshot[3].getThreadState() ==
                           Thread.State.TIMED_WAITING;
                if (ready) break;
                Thread.sleep(10);
            }

            if (!ready) {
                System.out.println("States not observed before timeout");
                return;
            }

            for (ThreadInfo t : snapshot) {
                String ownerName = t.getLockOwnerName();
                System.out.println(t.getThreadName() + ": "
                        + t.getThreadState() + "; owner="
                        + (ownerName == null ? "-" : ownerName));
            }

            if (args.length == 1 && "--capture".equals(args[0])) {
                System.out.println("Capture now; press Enter to release.");
                System.in.read();
            }
        } finally {
            releaseOwner.countDown();
            releaseWaiter.countDown();
            sleeping.interrupt();
            owner.join();
            blocked.join();
            waiting.join();
            sleeping.join();
        }
    }
}
~~~

Biên dịch/chạy với Java 17+:

~~~bash
javac --release 17 -encoding UTF-8 DumpExercise.java
java DumpExercise
~~~

Kết quả khi quan sát được các trạng thái dự kiến:

~~~text
demo-owner: WAITING; owner=-
demo-blocked: BLOCKED; owner=demo-owner
demo-waiting: WAITING; owner=-
demo-sleeping: TIMED_WAITING; owner=-
~~~

Trong môi trường quá bận hoặc không bắt được trạng thái đúng lúc, chương trình in **States not observed before timeout**. Thay vì dùng Thread.sleep để đoán khi nào worker đã giữ monitor, chương trình dùng latch **entered** để biết owner đã vào vùng synchronized. Khối **finally** mở latch, interrupt sleeper và join các worker khi main tới được khối này.

**Vì sao owner WAITING mà vẫn giữ lock?** **CountDownLatch.await()** không tự giải phóng những monitor synchronized bên ngoài. Vì vậy, khi owner đợi latch, blocked vẫn không lấy được gate. Điều này khác với **Object.wait()**, vốn nhả chính monitor đang wait trên đó theo hợp đồng API.

### Chụp dump từ terminal khác

Terminal thứ nhất:

~~~bash
java DumpExercise --capture
~~~

Khi màn hình in **Capture now; press Enter to release.**, giữ chương trình mở. Terminal thứ hai:

~~~bash
jcmd -l
jcmd <PID> Thread.print -l
~~~

Thay PID đúng của DumpExercise, tìm bốn tên thread. Sau khi chụp, nhấn Enter ở terminal đầu để giải phóng latch và kết thúc. Nếu sleep đã hết sau 30 giây hoặc stdin đóng/EOF, trạng thái có thể đổi trước lúc chụp; chạy lại nếu cần.

## 4. Thực hành B: tìm chính xác điểm bị BLOCKED

### Bước 1: tìm thread nghi vấn

Tìm **demo-blocked** trong text dump. Ví dụ cách hiển thị rút gọn:

~~~text
"demo-blocked" ... java.lang.Thread.State: BLOCKED (on object monitor)
    at DumpExercise.enter(DumpExercise.java:20)
    - waiting to lock <0xABC> (a java.lang.Object)
~~~

**Số dòng 20 và địa chỉ 0xABC ở đây chỉ là ví dụ.** Dòng quan trọng là frame ứng dụng **DumpExercise.enter(...)**, dẫn về đoạn:

~~~java
static void enter(Object gate) {
    synchronized (gate) { // Điểm đang xin monitor.
    }
}
~~~

Đây là **vị trí bị chặn** nhưng không nhất thiết là **nơi gây nguyên nhân**. Nếu xóa synchronized mà không kiểm tra invariant dữ liệu thì có thể tạo race condition.

### Bước 2: tìm monitor và chủ sở hữu

Tìm trong dump một thread có dòng **- locked** cùng định danh monitor. Với ví dụ, thread **demo-owner** giữ monitor gate trong **DumpExercise.hold(...)**. Chỉ dựa vào cùng tên class **java.lang.Object** là chưa đủ, vì nhiều instance Object có thể là các monitor khác nhau.

Trong API Java, **ThreadInfo.getLockOwnerName()** của demo-blocked trả **demo-owner** ở thời điểm quan sát. Sơ đồ phụ thuộc:

~~~text
demo-blocked chờ gate
        |
        v
demo-owner giữ gate
        |
        v
demo-owner chờ releaseOwner latch
        |
        v
main gọi releaseOwner.countDown()
~~~

Bằng chứng này cho thấy owner mới là nơi cần xem sâu. Trong bài tập, main mở latch khi kết thúc; nếu trong code production tín hiệu phải được phát bởi chính thread đang blocked thì có thể xuất hiện vòng phụ thuộc không thể hoàn tất.

### Bước 3: xem thread WAITING không có owner

**demo-waiting** có **owner=-** nhưng vẫn WAITING. Đây là chờ latch, không phải chờ monitor có một owner rõ ràng. Phải tìm phương thức phát **countDown()** chứ không suy ra “không có vấn đề”.

Với **Future.get()**, **CompletableFuture.join()**, **Condition.await()** hoặc I/O cũng vậy: nguồn giúp tiếp tục có thể là task, callback hoặc hệ thống bên ngoài, không nhất thiết là thread giữ một monitor.

## 5. Bảng nhận diện nguồn chờ từ stack

| Dấu hiệu | Ý nghĩa cần kiểm tra |
|---|---|
| **BLOCKED**, **waiting to lock** | Tìm monitor ID, **locked** ở thread khác và stack owner. |
| **Object.wait()** | Tìm predicate của điều kiện chờ và đường **notify/notifyAll**. |
| **CountDownLatch.await()** | Tìm mọi đường **countDown()** và trường hợp thất bại trước signal. |
| **Future.get() / join()** | Tìm task tạo kết quả, executor và các dependency của task. |
| **LockSupport.park()** | Xem frame phía dưới để phân biệt ReentrantLock, queue, semaphore hoặc condition. |
| **Thread.sleep()** | Kiểm tra thời gian ngủ, timeout, retry và deadline. |
| **RUNNABLE** ở socket/file read | Có thể đang trong native I/O; xem I/O timeout và peer. |
| **RUNNABLE** lặp ở code tính toán | Đối chiếu CPU, nhiều bản dump và điều kiện thoát vòng lặp. |

Đọc stack **từ phần cơ chế JDK tới frame ứng dụng gần nhất**. Frame **Unsafe.park** chỉ nói thread đang park, còn frame ứng dụng hoặc primitive ở phía dưới mới cho biết lý do nghiệp vụ.

## 6. Tự động lấy ThreadInfo từ ThreadMXBean

**ThreadMXBean** có thể trả thông tin thread ngay trong JVM. Trong method đã có **mx** và **ids** như bài thực hành A, đoạn sau in chi tiết hơn:

~~~java
ThreadInfo[] details = mx.getThreadInfo(ids, 32);
for (ThreadInfo t : details) {
    if (t == null) continue;
    System.out.printf("thread=%s id=%d state=%s%n",
            t.getThreadName(), t.getThreadId(), t.getThreadState());
    System.out.printf("waiting=%s owner=%s (%d)%n",
            t.getLockInfo(), t.getLockOwnerName(), t.getLockOwnerId());
    for (StackTraceElement frame : t.getStackTrace()) {
        System.out.println("    at " + frame);
    }
}
~~~

Đây là **snippet**, không phải chương trình độc lập. **getThreadInfo(ids, 32)** lấy tối đa 32 stack frames; thread đã kết thúc có thể cho phần tử **null**. Nếu muốn lấy danh sách lock mà thread đang giữ, cần overload có tham số tương ứng và kiểm tra khả năng JVM:

~~~java
boolean monitorSupport = mx.isObjectMonitorUsageSupported();
boolean synchronizerSupport = mx.isSynchronizerUsageSupported();
ThreadInfo[] richer = mx.getThreadInfo(
        ids, monitorSupport, synchronizerSupport);
~~~

Sau đó đọc **getLockedMonitors()** và **getLockedSynchronizers()**. Không giả định **getThreadInfo(ids, maxDepth)** mặc định đã trả tất cả danh sách này.

### Tìm deadlock

~~~java
// Đoạn minh họa đặt trong một method:
ThreadMXBean mx = ManagementFactory.getThreadMXBean();
long[] deadlocked = mx.isSynchronizerUsageSupported()
        ? mx.findDeadlockedThreads()
        : mx.findMonitorDeadlockedThreads();
if (deadlocked != null) {
    System.out.println("Deadlocked: " + deadlocked.length);
}
~~~

**findMonitorDeadlockedThreads()** tìm vòng chờ object monitor của synchronized; **findDeadlockedThreads()** có thể gồm cả ownable synchronizer như ReentrantLock nếu JVM hỗ trợ. Nếu không phát hiện được, điều đó **không chứng minh** ứng dụng không có hang do latch, future, I/O hoặc deadlock logic khác.

## 7. Phân biệt contention, deadlock, starvation

**Contention:** thread A giữ monitor trong thời gian ngắn; thread B bị BLOCKED nhưng sau đó tiếp tục. Thread dump chụp đúng thời điểm tranh chấp có thể trông đáng ngại, nhưng nếu throughput/latency phù hợp thì chưa chắc là sự cố.

**Deadlock:** thread A giữ LOCK-1 và chờ LOCK-2 do B giữ; B giữ LOCK-2 và chờ LOCK-1 do A giữ:

~~~text
A -> đợi B -> đợi A
~~~

Có vòng phụ thuộc trên cùng những lock. Cần khớp lock identity và stack của các thread để kết luận. Cách sửa phổ biến là thống nhất thứ tự lấy lock hoặc bỏ vùng lồng lock không cần thiết.

**Starvation:** worker A chờ future của task B, nhưng B nằm trong queue của một executor mà tất cả worker đang bận chờ. Có thể không tồn tại vòng sở hữu monitor để JVM báo deadlock. Cần xem task queue, số worker, dependency và thiết kế blocking wait.

**Livelock:** nhiều thread vẫn chạy/đổi trạng thái nhưng không tạo tiến triển. Một dump đơn lẻ thường không đủ; cần thêm quan sát theo thời gian.

## 8. Quy trình điều tra từ lỗi thật tới sửa code

1. **Ghi symptom:** request/job nào đứng, thời gian chờ, PID, JDK version và build đang chạy.
2. **Chụp dump đúng lúc:** khi triệu chứng còn xảy ra, bằng công cụ phù hợp platform/virtual threads.
3. **Tìm thread liên quan:** từ tên, stack method, log correlation hoặc task ID nếu có.
4. **Xác định frame ứng dụng:** tìm nơi gọi synchronized, await, join, lock, I/O read hoặc code CPU loop.
5. **Truy tài nguyên chờ:** nếu BLOCKED tìm monitor ID; nếu WAITING tìm điều kiện latch/future/queue.
6. **Truy owner hoặc nguồn signal:** thread nào đang giữ lock, task nào sẽ complete future, ai countDown?
7. **Lập đồ thị phụ thuộc:** có vòng chờ hay chỉ một đường chờ kéo dài?
8. **Đối chiếu thêm bằng chứng:** nhiều dumps, log, CPU theo thread, queue depth, throughput.
9. **Sửa nguyên nhân gốc:** giảm thời gian giữ lock, lock order nhất quán, tránh chờ blocking khi đang giữ tài nguyên cần thiết.
10. **Kiểm chứng:** test có timeout, ép interleaving bằng latch, thử dưới contention và kiểm tra tính đúng đắn của dữ liệu.

### Ví dụ: không giữ monitor khi đợi kết quả không cần thiết

Mẫu nguy hiểm (snippet giả định các biến đã khai báo):

~~~java
synchronized (sharedLock) {
    Result value = future.join();
    updateSharedState(value);
}
~~~

Nếu task hoàn thành future cần sharedLock, vòng phụ thuộc có thể phát sinh. Nếu invariant cho phép, đợi bên ngoài rồi chỉ bảo vệ phần cập nhật:

~~~java
Result value = future.join();
synchronized (sharedLock) {
    updateSharedState(value);
}
~~~

**Hai đoạn là snippet, không phải file runnable độc lập.** Phải đánh giá lại invariant: state có thể thay đổi giữa lúc đợi và lúc lấy lock. Không đơn giản xóa synchronized để làm thread bớt BLOCKED mà gây race condition mới.

Với ReentrantLock, nhả khóa bằng finally khi đã lấy được:

~~~java
lock.lock();
try {
    doProtectedWork();
} finally {
    lock.unlock();
}
~~~

**tryLock(timeout, unit)** có thể tránh chờ vô hạn nhưng phải xử lý failure và cleanup đúng.

## 9. Câu hỏi thực hành và đáp án

### Tình huống A

~~~text
"job-B" BLOCKED
    at app.Service.save(Service.java:80)
    - waiting to lock <0x123>

"job-A" WAITING
    at java.util.concurrent.CompletableFuture.join(...)
    at app.Service.flush(Service.java:54)
    - locked <0x123>
~~~

**Đáp án:** B bị chặn ở **save:80**; A giữ monitor trong khi chờ future ở **flush:54**. Cần tìm task hoàn thành future và xem nó có phụ thuộc B hoặc monitor này không. Chưa đủ chứng cứ kết luận deadlock.

### Tình huống B

~~~text
"consumer" WAITING
    at java.util.concurrent.locks.LockSupport.park(...)
    at java.util.concurrent.ArrayBlockingQueue.take(...)
    at app.Consumer.run(Consumer.java:31)
~~~

**Đáp án:** có thể chỉ là queue rỗng và consumer chờ hợp lệ. Nếu hệ thống báo đã gửi dữ liệu, kiểm tra đúng queue, đường put/offer, producer và vòng đời.

### Tình huống C

~~~text
"task-A" BLOCKED, waiting to lock <LOCK-B>, locked <LOCK-A>
"task-B" BLOCKED, waiting to lock <LOCK-A>, locked <LOCK-B>
~~~

**Đáp án:** A chờ B và B chờ A trên hai lock, là dấu hiệu rõ của deadlock nếu lock IDs tương ứng chính xác trong một bản dump. Tìm hai thứ tự khóa đối nghịch trong mã nguồn và thống nhất thứ tự.

## 10. Sai lầm phổ biến

1. **BLOCKED nghĩa là deadlock.** Sai: cần chứng minh chu trình, nhiều trường hợp chỉ là contention.
2. **WAITING luôn là bug.** Sai: queue rỗng hoặc chờ một sự kiện hợp lệ có thể bình thường.
3. **Chỉ xem thread bị ảnh hưởng.** Bỏ qua lock owner hoặc nguồn signal dễ sửa nhầm.
4. **Nhầm cùng class với cùng lock object.** Phải đối chiếu monitor identity.
5. **RUNNABLE luôn dùng CPU.** Sai: trạng thái này có thể xuất hiện với native I/O.
6. **Chỉ đọc Unsafe.park.** Cần truy caller/primitive và frame ứng dụng.
7. **Owner là null nghĩa không có điều kiện chờ.** Sai với latch, future và nhiều wait.
8. **Không tìm thấy deadlock qua MXBean nên ứng dụng khỏe.** Sai vì phạm vi phát hiện giới hạn.
9. **So dump với source khác build.** Tên method/line number có thể khác.
10. **Một dump duy nhất đủ chứng minh tình trạng kéo dài.** Cần so thời gian và telemetry.
11. **Sửa bằng thêm sleep hoặc thread.** Có thể che triệu chứng mà không bỏ dependency sai.
12. **Quên timeout và cleanup cho test.** Test concurrency có thể làm cả CI đứng vô hạn.
13. **Chụp dump liên tục dưới tải hoặc chia sẻ thiếu kiểm soát.** Có overhead và có thể lộ thông tin nội bộ.
14. **Dùng công cụ không đúng JDK hoặc thread loại khác.** Kiểm tra help và khả năng virtual thread.

## 11. Checklist điều tra

- [ ] Đúng PID, instance, JDK, build.
- [ ] Dump chụp lúc symptom tồn tại.
- [ ] Xác định thread và frame ứng dụng bị chặn.
- [ ] Nếu BLOCKED: tìm monitor ID và thread đang giữ.
- [ ] Nếu WAITING: tìm latch, future, queue, condition hoặc I/O.
- [ ] Truy owner/nguồn signal đến nguyên nhân gốc.
- [ ] Xác định có vòng deadlock hay chỉ chờ hợp lệ/contention.
- [ ] So thêm dump, log và metric.
- [ ] Sửa code đồng thời giữ đúng invariant.
- [ ] Kiểm thử có timeout và cleanup.

**Cách đọc nhớ nhanh:** **thread → state → stack → lock/điều kiện chờ → owner hoặc producer của tín hiệu → nguyên nhân → kiểm thử sửa lỗi**.

## 12. Tài liệu JDK

- [Thread.State (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.State.html)
- [ThreadMXBean (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html)
- [ThreadInfo (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadInfo.html)
- [CountDownLatch (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [jcmd (Java 21)](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Virtual Threads (Java 21)](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [Troubleshoot Process Hangs and Loops](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshoot-process-hangs-and-loops.html)
