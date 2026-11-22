# Phân biệt deadlock, chờ khóa và JVM đang thực hiện công việc nền

## 1. Bài toán: thấy thread không chạy tiếp có chắc JVM deadlock?

Trong Java, một ứng dụng có thể “đứng yên”, một HTTP request có thể mất hàng chục giây, hoặc một thread dump có rất nhiều dòng **WAITING**, **TIMED_WAITING**, **BLOCKED** mà **không hề xảy ra deadlock**. Ngược lại, một deadlock thực có thể chỉ liên quan đến hai application threads; những GC threads hoặc compiler threads của JVM vẫn hoạt động bình thường.

Cần phân biệt ít nhất bốn loại hiện tượng:

1. **Deadlock:** có một vòng phụ thuộc chờ tài nguyên, trong đó các threads liên quan không thể tiến triển để nhả những locks đang giữ nếu không có can thiệp bên ngoài hoặc thay đổi điều kiện thích hợp.
2. **Lock contention / chờ khóa:** thread muốn acquire một monitor hoặc lock nhưng tạm thời thread khác đang giữ; owner vẫn có thể hoàn tất, release, cho waiter tiếp tục. Chờ khóa không tự động là deadlock.
3. **Chờ điều kiện / I/O / completion:** thread có thể đang chờ tín hiệu, một task, dữ liệu mạng hoặc timeout theo đúng thiết kế; chưa có bằng chứng về lock cycle.
4. **JVM background work:** GC, JIT compilation, reference processing, service/runtime work và những threads phục vụ JVM có thể chạy, ngủ hoặc chờ theo chu kỳ mà không biểu thị ứng dụng bị kẹt.

Tình huống giả định:

~~~text
Dịch vụ trả HTTP chậm hơn bình thường.

Thread dump lúc 10:00:
  http-worker-1     BLOCKED trên object monitor A
  http-worker-2     RUNNABLE
  background-poller WAITING trên BlockingQueue
  C2 CompilerThread RUNNABLE
  G1 concurrent GC thread RUNNABLE

Điều cần biết:
  Ai đang giữ monitor A?
  Owner đang làm gì?
  Có vòng chờ hay chỉ cần owner nhả monitor?
  Queue/poller đang chờ việc hay thiếu tín hiệu?
  GC/JIT chỉ đang chạy công việc nền hay thực sự chiếm CPU?
  HTTP chậm vì DB/network, lock, GC pause, CPU starvation, hay việc khác?
~~~

**Không kết luận deadlock chỉ từ một từ BLOCKED hoặc WAITING.** Phải dựng được một quan hệ chờ cụ thể, tìm owner và xác định nó có đường tiến triển hay không.

### Mục tiêu học tập

Sau bài, bạn cần:

- Đọc đúng **Thread.State** của Java 17: NEW, RUNNABLE, BLOCKED, WAITING, TIMED_WAITING, TERMINATED.
- Phân biệt **intrinsic object monitors (synchronized)** và **ownable synchronizers** như ReentrantLock; biết khi nào thread dump/JMX có thể tìm deadlock.
- Vẽ **wait-for graph** để phân biệt một cạnh chờ thông thường với chu trình deadlock.
- Nhận diện **starvation, livelock, condition-wait hang, thread-pool starvation** và **I/O wait** không nhất thiết được deadlock detector của JVM báo.
- Biết rằng **Object.wait() tạm nhả receiver monitor**, còn **Thread.sleep()** và **LockSupport.park() không tự nhả intrinsic monitors**.
- Hiểu JVM **GC/JIT/background threads**, safepoints và tại sao một JVM vẫn dùng CPU dù business threads đang chờ.
- Dùng **jcmd Thread.print**, **jstack**, **ThreadMXBean**, **jcmd Compiler.queue**, **GC logs** và **JFR** để phân tích.
- Chạy các ví dụ Java 17+ và giải thích stdout xác định so với snapshot timing-dependent.
- Thiết kế **lock ordering, timeouts, cancellation, condition predicates** và instrumented diagnostics phù hợp.

**Phiên bản:** kiến thức cốt lõi theo Java SE 17; ví dụ/flags chẩn đoán dựa trên **HotSpot Java 17**. Các internals, thread names, GC algorithms, virtual-thread handling và diagnostic outputs khác nhau theo JDK version/vendor/OS. Java 17 chưa có virtual threads như tính năng production; Java 21+ cần đối chiếu tài liệu runtime tương ứng.

## 2. Từ “ứng dụng đứng” đến mô hình nguyên nhân

Một dịch vụ không đáp ứng request có thể vẫn có JVM tiến triển:

~~~text
Client request
      |
      v
  HTTP worker
      |
      +-- đang BLOCKED chờ synchronized(lock)
      |
      +-- đang WAITING chờ Future/get()/join()
      |
      +-- đang TIMED_WAITING do sleep/timeout
      |
      +-- RUNNABLE nhưng dùng CPU trong vòng lặp nóng
      |
      +-- RUNNABLE nhưng native socket read đang chờ I/O
      |
      +-- đang bị hạn chế CPU bởi container/OS scheduler
      |
      +-- gặp GC safepoint, allocation stalls hoặc backpressure
      |
      +-- bị kẹt trong deadlock cycle nhiều locks
~~~

Một JVM vẫn có thể ghi GC logs, chạy compiler, dọn references hoặc cập nhật metrics trong khi những threads nghiệp vụ hoàn toàn không tạo thêm kết quả.

**Cần điều tra nguyên nhân cụ thể**, không đặt nhãn “JVM deadlock” cho tất cả hiện tượng không tiến triển.

### 2.1. Safety và liveness

- **Safety:** không có kết quả sai như đọc state inconsistent, mất cập nhật, vi phạm invariant.
- **Liveness:** chương trình cuối cùng có thể tiến triển/hoàn tất trong những điều kiện được giả định.
- **Deadlock:** thất bại về liveness do vòng chờ.
- **Starvation:** một thread có thể không được cấp CPU/lock/permit đủ lâu dù threads khác vẫn tiến triển.
- **Livelock:** các threads vẫn hoạt động/chuyển trạng thái nhưng tương tác khiến không hoàn thành công việc hữu ích.
- **Condition wait kéo dài:** thread chờ predicate hoặc event chưa xảy ra; đôi khi đây là behavior mong đợi, đôi khi là bug.

Không có bảo đảm “vì chương trình thread-safe nên luôn tiến triển”: code có thể tránh data races nhưng vẫn deadlock hoặc starve.

## 3. Thread.State của Java 17: đọc đúng ý nghĩa

**Thread.State** là tập enum states của Java-level thread. Đây **không phải** các trạng thái native kernel scheduler một-một.

| State | Ý nghĩa Java-level | Ví dụ thường gặp | Có tự chứng minh deadlock? |
| --- | --- | --- | --- |
| **NEW** | Đã tạo Thread object, chưa start | new Thread(task) | Không |
| **RUNNABLE** | Đang thực thi hoặc sẵn sàng trong VM; có thể chờ tài nguyên OS | CPU loop, phần native I/O | Không |
| **BLOCKED** | Chờ **intrinsic object monitor** | Đợi synchronized(lock) | Không |
| **WAITING** | Chờ hành động khác, không có timeout xác định | Object.wait(), join(), LockSupport.park() | Không |
| **TIMED_WAITING** | Chờ với deadline/timeout | Thread.sleep, wait(timeout), join(timeout), parkNanos | Không |
| **TERMINATED** | Đã kết thúc thực thi | run() kết thúc | Không |

### 3.1. RUNNABLE không đồng nghĩa dùng CPU 100%

Một RUNNABLE thread có thể:

- Đang chạy Java code trên CPU.
- Sẵn sàng chạy nhưng đang đợi scheduler.
- Đang ở native code hoặc một hoạt động I/O tùy implementation.
- Chạy trong vòng spin tiêu tốn CPU.
- Bị container CPU throttling làm thực tế ít có tiến độ.

Cần đối chiếu **CPU usage per thread**, stack frames, native I/O, profiling và nhiều snapshots trước khi nói một RUNNABLE thread “là thủ phạm”.

### 3.2. BLOCKED có nghĩa rất cụ thể

**BLOCKED** là Java thread đang chờ **object monitor** của synchronized statement/method, hoặc chờ reacquire monitor sau Object.wait(). Nó không phải state generic cho “đang chờ bất cứ lock nào”.

Một thread đang chờ **ReentrantLock.lock()** có thể xuất hiện như **WAITING** hoặc **TIMED_WAITING** liên quan LockSupport.park/AQS; không mặc nhiên là BLOCKED. Phải xem lock owner và stack.

### 3.3. WAITING có thể hoàn toàn bình thường

Các trạng thái có thể là thiết kế hợp lệ:

- Thread pool worker đợi task trong BlockingQueue.take().
- Consumer đợi CountDownLatch.await().
- Main thread đợi worker.join().
- Object.wait() đợi predicate/notify.
- LockSupport.park() dùng để quản lý lịch công việc.
- Scheduled executor đang chờ lần chạy tiếp theo.

Nếu task chưa đến và không có request chờ response bị ảnh hưởng, thread WAITING là trạng thái “nghỉ đúng chỗ”, không phải lỗi.

### 3.4. TIMED_WAITING không hứa thời gian chính xác

**Thread.sleep(100)** đặt một yêu cầu ngủ khoảng thời gian, nhưng elapsed duration có thể bị tác động bởi OS scheduler, timer precision, GC hoặc CPU contention. Nếu Thread đang sleep trong synchronized block, nó **vẫn sở hữu monitor** đó.

Không dùng thread state polling như một coordination protocol: **getState() chỉ là snapshot**, trạng thái có thể đổi ngay sau khi đọc.

## 4. Một cạnh chờ chưa phải deadlock

Ví dụ có hai threads:

~~~text
Thread T1:
  owns monitor M
  performs 10 ms work
  releases M

Thread T2:
  tries synchronized(M)
  BLOCKED while T1 owns M
  then enters after T1 unlocks
~~~

Đây là **lock contention bình thường**. T2 chưa tiến triển tại khoảnh khắc quan sát, nhưng T1 có đường hoàn tất và giải phóng resource.

Mô hình quan hệ:

~~~text
T2 --waits-for M--> T1 (owner)
T1 --doing work--> eventually unlock(M)

Wait-for graph:
  T2 ----> T1
          (không có cycle)
~~~

Dù T2 đã chờ vài giây, vẫn cần xem T1 đang làm gì. T1 có thể thực hiện tác vụ lâu bất hợp lý hoặc bị treo I/O — nhưng **không tự động có một vòng deadlock monitor**.

### 4.1. Lock convoy

Khi nhiều threads cùng cần một global lock, owner kế tiếp có thể liên tục làm hàng đợi kéo dài:

~~~text
T1 owns M
T2 waits for M
T3 waits for M
T4 waits for M

T1 releases -> one contender acquires -> others continue waiting
~~~

Đây có thể là **throughput bottleneck/lock contention**, không có circular wait. Tăng số threads có thể làm contention nặng hơn; thường cần rút ngắn critical section hoặc phân vùng state/locks.

### 4.2. Owner giữ lock trong lúc ngủ hoặc I/O

~~~java
// Minh họa trong một method, không phải class độc lập.
synchronized (lock) {
    Thread.sleep(300);
}
~~~

Thread vẫn giữ monitor trong lúc ngủ. Các threads khác đang cố synchronized(lock) có thể BLOCKED. Một thao tác như DB call trong synchronized cũng kéo dài lock hold time.

Để sửa, kiểm tra thiết kế invariant rồi chuyển I/O hoặc các phần không cần độc quyền ra ngoài critical section khi an toàn.

## 5. Demo Java 17+ #1: chờ monitor rồi tiếp tục, không deadlock

Tạo **MonitorContentionDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class MonitorContentionDemo {
    public static void main(String[] args)
            throws InterruptedException {
        Object lock = new Object();
        CountDownLatch holderReady = new CountDownLatch(1);
        CountDownLatch releaseHolder = new CountDownLatch(1);
        AtomicInteger completedSections = new AtomicInteger();

        Thread holder = new Thread(() -> {
            synchronized (lock) {
                holderReady.countDown();
                try {
                    releaseHolder.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    return;
                }
                completedSections.incrementAndGet();
            }
        }, "lock-holder");

        Thread contender = new Thread(() -> {
            synchronized (lock) {
                completedSections.incrementAndGet();
            }
        }, "lock-contender");

        holder.start();
        holderReady.await();
        contender.start();

        releaseHolder.countDown();

        holder.join();
        contender.join();

        System.out.println("completedSections="
                + completedSections.get());
        System.out.println("bothTerminated="
                + (!holder.isAlive() && !contender.isAlive()));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 -encoding UTF-8 MonitorContentionDemo.java
java MonitorContentionDemo
~~~

**Stdout chính xác khi không có external interruption và tiến trình được cấp CPU để hoàn tất:**

~~~text
completedSections=2
bothTerminated=true
~~~

Giải thích:

1. Holder acquire lock, phát **holderReady**, rồi chờ releaseHolder **trong khi vẫn sở hữu intrinsic monitor**.
2. Main chỉ start contender sau khi holderReady đã được phát. Contender cần cùng lock nên không thể vào trước khi holder release.
3. Main phát releaseHolder; holder chạy tiếp, tăng counter rồi ra synchronized.
4. Contender acquire lock, tăng counter rồi thoát.
5. Main join cả hai và in kết quả xác định.

**Không có circular wait:** holder chờ latch do main điều khiển; main không cần monitor lock để phát tín hiệu. Nếu holder chỉ chờ mãi mà main không phát, chương trình có thể treo do thiếu tín hiệu nhưng chưa có bằng chứng intrinsic-monitor deadlock cycle.

**Quan sát timing:** Không cố định rằng tại một System.out.println cụ thể contender chắc đang ở state BLOCKED, vì có thể chưa được scheduler cho chạy hoặc holder đã release. Muốn chụp state phải giữ workload ở một mốc đủ lâu với công cụ chẩn đoán; không dùng một lần getState() làm chứng minh.

## 6. Deadlock là một vòng chờ: wait-for graph

Mẫu monitor deadlock kinh điển:

~~~text
Thread T1:
    synchronized (A) {      // owns A
        synchronized (B) {  // waits B held by T2
            ...
        }
    }

Thread T2:
    synchronized (B) {      // owns B
        synchronized (A) {  // waits A held by T1
            ...
        }
    }
~~~

Nếu T1 đã giữ A và T2 đã giữ B, sau đó cả hai cùng cố acquire lock của bên kia:

~~~text
        owns A                   owns B
         T1                       T2
          |                        |
          +-- waits for B -------->+
          <-------- waits for A ---+

Wait-for graph:
     T1 ------> T2
      ^         |
      |         v
      +---------+
      CYCLE
~~~

T1 không thể acquire B vì T2 không release trước khi thoát block; T2 không thể acquire A vì T1 không release trước khi thoát block. Với intrinsic monitor entry, bình thường các threads đang chờ lock không thể tự giải quyết chỉ nhờ một timeout do synchronized không có API **tryLock(timeout)**.

### 6.1. Bốn điều kiện kinh điển

Các điều kiện Coffman thường dùng để giải thích resource deadlock:

1. **Mutual exclusion:** resource không thể dùng đồng thời theo kiểu độc quyền.
2. **Hold and wait:** thread giữ ít nhất một resource và đợi resource khác.
3. **No preemption:** resource không thể đơn giản tước từ owner bất kỳ mà vẫn giữ invariant.
4. **Circular wait:** các owners tạo một vòng phụ thuộc chờ.

Nếu loại bỏ ít nhất một điều kiện bằng thiết kế đúng, có thể ngăn kiểu deadlock liên quan. Ví dụ **global lock ordering** ngăn circular wait cho tập locks được tuân thủ.

### 6.2. Không nhầm deadlock với “thread A bị chặn lâu”

T1 đợi B do T2 giữ nhưng T2 đang tính toán rồi sẽ release B: **chưa phải một deadlock cycle**.

T1 đợi B, T2 đợi A, mỗi thread đang giữ monitor bên kia: **có vòng đợi**; nếu không có đường nhả hợp lệ, đây là deadlock.

T1 giữ A rồi **Object.wait() trên B** trong khi vẫn giữ A; T2 muốn acquire A để có thể notify B: có thể gây **condition/lock dependency deadlock** dù trạng thái trên dump có sự kết hợp WAITING và BLOCKED, không chỉ hai BLOCKED.

### 6.3. Deadlock là tính chất của toàn bộ tập phụ thuộc

Một thread dump cho thấy “waiting to lock B owned by T2” mới cho một cạnh. Cần điều tra T2 đang chờ gì, rồi tiếp tục đến khi:

- Thấy một vòng về thread đã ghé qua ⇒ có circular wait.
- Gặp thread owner không chờ resource khác ⇒ có đường khả dĩ để tiến triển.
- Gặp wait trên external system/condition không quan sát được ⇒ chưa thể kết luận; cần logs, runtime state hoặc external-system diagnostics.

## 7. Phân biệt object monitor và ReentrantLock

Java có nhiều cơ chế đồng bộ hóa:

| Cơ chế | Cách acquire | Chờ thường thấy | Cơ chế release |
| --- | --- | --- | --- |
| **synchronized(obj)** | JVM monitorenter/implicit method monitor | Contender thường BLOCKED | Tự exit block/method |
| **ReentrantLock.lock()** | java.util.concurrent.locks | Thường dùng AQS/LockSupport.park, có thể WAITING | Programmer gọi unlock trong finally |
| **ReentrantLock.lockInterruptibly()** | Interruptible acquisition | Có thể xử lý interruption | unlock trong finally sau khi acquire |
| **ReentrantLock.tryLock(timeout)** | Timed attempt | Có thể timed wait | unlock khi acquire thành công |
| **ReadWriteLock** | Read/write lock permits | Tùy implementation và mode | unlock tương ứng |

**Java Thread.State.BLOCKED chỉ nói về object monitor**; chờ java.util.concurrent synchronizer có thể được báo là WAITING/TIMED_WAITING. Việc chọn ReentrantLock không tự ngăn deadlock; hai ReentrantLocks vẫn có thể tạo vòng wait.

### 7.1. Ownable synchronizer

Một số synchronizers có khái niệm owner (ví dụ ReentrantLock và ReentrantReadWriteLock.WriteLock). JVM management APIs có khả năng tìm deadlocks liên quan **object monitors** và **ownable synchronizers** ở mức hỗ trợ.

Không suy từ tên lock nào cũng được **ThreadMXBean** nhận biết: custom locks, semaphores, latches, distributed locks, futures hoặc external resources không nhất thiết hiện dưới dạng cycle của Java monitor/ownable-synchronizer graph.

### 7.2. Reentrant monitor không tự deadlock với chính nó

Thread đã sở hữu intrinsic monitor M có thể reenter synchronized(M) nhiều lần; JVM theo dõi reentrant depth cho đến khi exits cân bằng. Vì thế:

~~~java
synchronized (lock) {
    synchronized (lock) {
        // Cùng owner thread tái nhập cùng monitor: hợp lệ.
    }
}
~~~

Không phải deadlock chỉ vì nested synchronized. Nhưng nếu nested locks **A rồi B** ở thread này và **B rồi A** ở thread khác, circular wait vẫn có thể xảy ra.

## 8. ThreadMXBean: Java API để chẩn đoán deadlocks

**java.lang.management.ThreadMXBean** cung cấp:

- **findMonitorDeadlockedThreads():** tìm cycles liên quan object monitors.
- **findDeadlockedThreads():** tìm cycles liên quan object monitors **và ownable synchronizers** mà implementation hỗ trợ.
- **getThreadInfo(...):** thread details, lock owner, stack trace và monitor/synchronizer metadata theo overload.
- **dumpAllThreads(...):** snapshot threads với stack traces và lock information khi VM hỗ trợ.
- **getThreadCpuTime(...):** CPU time theo thread nếu bật/hỗ trợ.

**Null** từ deadlock finder nghĩa là **không phát hiện một cycle thuộc phạm vi kiểm tra ở thời điểm lấy mẫu**, không phải bằng chứng chương trình hoàn toàn không có liveness bugs.

### 8.1. Runnable Java 17 demo: chẩn đoán các cycles hiện có

Tạo **DeadlockInspector.java**:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.Arrays;

public class DeadlockInspector {
    public static void main(String[] args) {
        ThreadMXBean bean =
                ManagementFactory.getThreadMXBean();

        long[] ids = bean.findMonitorDeadlockedThreads();

        System.out.println("monitorCycleDetected="
                + (ids != null && ids.length > 0));

        if (ids != null) {
            System.out.println("affectedThreadCount="
                    + ids.length);
            ThreadInfo[] infos =
                    bean.getThreadInfo(ids, true, true);
            for (ThreadInfo info : infos) {
                if (info != null) {
                    System.out.println(
                            "thread=" + info.getThreadName());
                    System.out.println(
                            "state=" + info.getThreadState());
                    System.out.println(
                            "lock=" + info.getLockName());
                    System.out.println(
                            "owner=" + info.getLockOwnerName());
                }
            }
        }

        try {
            long[] allTypes = bean.findDeadlockedThreads();
            System.out.println("broaderCycleDetected="
                    + (allTypes != null
                    && allTypes.length > 0));
        } catch (UnsupportedOperationException unsupported) {
            System.out.println("broaderCycleSupported=false");
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 DeadlockInspector.java
java DeadlockInspector
~~~

**Không có một stdout tuyệt đối cho mọi JVM** vì counts và thread names phản ánh trạng thái tiến trình và khả năng quản lý synchronizers. Trong một JVM bình thường không có deadlock:

~~~text
monitorCycleDetected=false
broaderCycleDetected=false
~~~

Đây là **output thường gặp trong môi trường không có deadlock**, không phải contract tuyệt đối. Một JVM có thể hỗ trợ monitor detection nhưng không hỗ trợ broad ownable-synchronizer detection, hoặc có background/runtime state bất thường. Nếu code in tên threads, thứ tự/names khác nhau theo run.

**Quan trọng:** demo này chỉ kiểm tra **JVM của chính chương trình**. Chạy một chương trình inspector hoàn toàn mới không thể tìm deadlock ở process server khác. Để chẩn đoán server, dùng **jcmd/jstack/JMX trong process đích** hoặc tích hợp ThreadMXBean trong service có thẩm quyền.

### 8.2. Vì sao getThreadInfo thêm thông tin?

ThreadInfo có thể cung cấp:

- Thread name, ID, state.
- Lock name chờ acquire/wait.
- Lock owner name/ID khi biết.
- Stack trace tại snapshot.
- Locked monitors và ownable synchronizers theo overload.

Nhưng dump có race: thread có thể release/acquire lock ngay sau khi snapshot. Không có public API bảo đảm một bản dump là lịch sử mọi interleavings.

## 9. Một số hiện tượng không phải Java monitor deadlock

### 9.1. Chờ điều kiện chưa xảy ra

Thread A chờ CountDownLatch.await() và thread B chưa xử lý xong task. Nếu B còn khả năng hoàn thành và countDown, đó có thể là **legitimate waiting**. Nếu producer quên countDown, hệ có thể treo vì **missing signal**; deadlock detector không nhất thiết báo cycle.

### 9.2. Thread-pool starvation/self-deadlock

Giả sử ExecutorService chỉ có **một worker thread**. Task A chạy trên worker ấy, submit task B vào **cùng executor**, rồi gọi **futureB.get()**. Task B nằm trong queue, không có worker khác để chạy; A chờ B, B chờ worker mà A đang chiếm.

~~~text
Single-thread executor:
 Worker-1 executes Task A
    |
    +-- submits Task B to same executor
    |
    +-- waits Future.get(B) indefinitely

 Task B stays queued:
    cannot start because Worker-1 blocked in Task A
~~~

Đây là **executor starvation deadlock** theo nghĩa liveness của hệ, **không nhất thiết là monitor/ownable-lock deadlock** mà ThreadMXBean.findDeadlockedThreads nhận diện.

Cách tránh: không block trong một task để đợi task khác chỉ có thể chạy trên cùng pool không còn capacity; dùng completion composition, worker capacity phù hợp, hoặc tách executor theo resource constraints.

### 9.3. External resource deadlock

Hai requests có thể bị deadlock ở database row locks, distributed locks hoặc file locks. JVM stack có thể chỉ cho thấy socket I/O chờ DB response, thường không tạo Java-level lock ownership cycle. Cần DB deadlock graphs, slow queries và resource-level diagnostics.

### 9.4. Starvation

Một thread có thể chờ lock hoặc CPU rất lâu vì lock thường được những threads khác giành được trước hoặc process bị CPU-throttled. Không có circular wait không có nghĩa latency đã đạt yêu cầu.

### 9.5. Livelock

Hai threads đều “nhường đường” và retry theo quy tắc không hiệu quả, liên tục thay đổi trạng thái nhưng không hoàn tất. Chúng có thể hiển thị RUNNABLE thay vì BLOCKED/WAITING. CPU có thể cao.

### 9.6. Busy spin

~~~java
// Minh họa lỗi, không dùng làm solution:
while (!ready) {
    // ready là ordinary non-volatile field.
}
~~~

Có thể gây CPU cao, không bảo đảm visibility do data race, và không tạo một wait-for graph. **Thread.onSpinWait** là performance hint chứ không biến ordinary read thành volatile read.

## 10. Demo Java 17+ #2: WAITING hợp lệ qua CountDownLatch

Tạo **LegitimateWaitingDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class LegitimateWaitingDemo {
    public static void main(String[] args)
            throws InterruptedException {
        CountDownLatch workerReady = new CountDownLatch(1);
        CountDownLatch mayProceed = new CountDownLatch(1);
        AtomicInteger result = new AtomicInteger();

        Thread worker = new Thread(() -> {
            workerReady.countDown();
            try {
                mayProceed.await();
                result.set(7);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "legitimate-waiter");

        worker.start();
        workerReady.await();

        mayProceed.countDown();
        worker.join();

        System.out.println("result=" + result.get());
        System.out.println("terminated=" + !worker.isAlive());
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 LegitimateWaitingDemo.java
java LegitimateWaitingDemo
~~~

**Stdout nếu không có external interruption và chạy thành công:**

~~~text
result=7
terminated=true
~~~

Worker có thể chuyển sang WAITING khi chờ latch, nhưng snapshot thread state không được chương trình in và **không nên gán một expected intermediate state cố định** vì main có thể countDown rất sớm. Điều quan trọng là **worker có đường hoàn tất** sau tín hiệu, và main dùng join để nhận kết quả xác định.

### 10.1. Vì sao dùng latch chứ không sleep?

CountDownLatch có protocol và memory consistency effects: actions trước countDown **happens-before** actions sau successful await tương ứng. **Thread.sleep** chỉ ngừng thread một thời gian, không bảo đảm bên kia đã đến milestone hay publish kết quả.

### 10.2. Timeout là công cụ chẩn đoán, không phải sửa correctness

~~~java
// Minh họa cần import TimeUnit:
boolean signaled =
        latch.await(5, java.util.concurrent.TimeUnit.SECONDS);
if (!signaled) {
    throw new IllegalStateException("Wait exceeded deadline");
}
~~~

Timeout có thể giúp service tránh chờ vô hạn, nhưng không tự làm producer phát signal. Khi timed await trả false, không dựa vào success HB contract của latch.

## 11. Object.wait(), Thread.sleep() và LockSupport.park() khác nhau

| API | Trạng thái thường gặp | Có tự nhả intrinsic monitor hiện đang giữ? | Ghi chú |
| --- | --- | --- | --- |
| **Object.wait()** trên M | WAITING/TIMED_WAITING | **Có, với receiver monitor M** | Cần thread sở hữu M; reacquire M trước khi return |
| **Thread.sleep()** | TIMED_WAITING | **Không** | Không có synchronization semantics riêng |
| **LockSupport.park()** | WAITING | **Không tự nhả intrinsic monitors** | Có thể được unpark/interrupt hoặc spuriously return |
| **Thread.join()** | WAITING/TIMED_WAITING | **Không tự nhả monitors tùy ý** | Completion synchronization với target thread |
| **CountDownLatch.await()** | Thường WAITING/TIMED_WAITING qua AQS | **Không tự nhả intrinsic monitors** | Latch signal dùng coordination protocol |
| **ReentrantLock Condition.await()** | Thường WAITING/TIMED_WAITING | Nhả **associated ReentrantLock** theo contract | Khác với intrinsic monitor; dùng đúng lock discipline |

### 11.1. Một deadlock khó nhìn từ wait()

~~~java
// Mô hình lỗi: giữ A khi chờ điều kiện trên B.
synchronized (a) {
    synchronized (b) {
        b.wait();
    }
}
~~~

**Object.wait() trên B** tạm nhả các acquisition của B rồi reacquire trước return, nhưng **không nhả A**. Nếu notifier cần synchronized(a) trước mới có thể thực hiện synchronized(b) và b.notifyAll(), toàn hệ có thể bị kẹt vì vòng phụ thuộc trên A và tín hiệu B.

Không nói “wait() nhả mọi locks mà thread sở hữu”. Nó nhả **monitor của receiver object**, không tự nhả unrelated locks.

### 11.2. notifyAll không trao monitor ngay

~~~java
synchronized (lock) {
    ready = true;
    lock.notifyAll();
    // Notifier vẫn giữ monitor tới khi block kết thúc.
}
~~~

Các waiters thức dậy phải reacquire lock trước khi return khỏi wait. Nếu notifier tiếp tục làm việc dài trong synchronized, waiters vẫn chưa tiến triển.

### 11.3. Condition predicate phải được kiểm tra lại

~~~java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
}
~~~

Dùng **while**, không chỉ if, vì spurious wakeups, nhiều waiters và condition có thể thay đổi trước khi thread reacquire. Đây là correctness protocol, không phải performance tuning.

## 12. Demo Java 17+ #3: monitor wait có đường kết thúc

Tạo **MonitorWaitDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;

public class MonitorWaitDemo {
    public static void main(String[] args)
            throws InterruptedException {
        Object monitor = new Object();
        CountDownLatch entered = new CountDownLatch(1);
        boolean[] ready = {false};
        boolean[] observed = {false};

        Thread waiter = new Thread(() -> {
            synchronized (monitor) {
                entered.countDown();
                while (!ready[0]) {
                    try {
                        monitor.wait();
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        return;
                    }
                }
                observed[0] = true;
            }
        }, "monitor-waiter");

        waiter.start();
        entered.await();

        synchronized (monitor) {
            ready[0] = true;
            monitor.notifyAll();
        }

        waiter.join();
        System.out.println("condition=" + ready[0]);
        System.out.println("observed=" + observed[0]);
        System.out.println("terminated=" + !waiter.isAlive());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 -encoding UTF-8 MonitorWaitDemo.java
java MonitorWaitDemo
~~~

**Stdout xác định khi không external interrupt và hoàn thành:**

~~~text
condition=true
observed=true
terminated=true
~~~

Các synchronization edges:

- Waiter gọi entered.countDown khi còn giữ monitor.
- Main entered.await(), sau đó muốn synchronized(monitor). Nếu waiter chưa gọi wait, main sẽ chờ; khi waiter wait nó nhả monitor.
- Main set ready=true và notifyAll.
- Waiter reacquire monitor rồi đọc ready, đi tiếp và cập nhật observed.
- Main join đảm bảo nhìn kết quả sau waiter kết thúc.

Nếu waiter bị spurious wakeup trước khi ready=true, vòng while kiểm tra lại điều kiện nên không đi tiếp sai.

## 13. JVM background threads: có thể RUNNABLE hoặc WAITING hoàn toàn bình thường

Một JVM HotSpot thường có threads phục vụ runtime, ví dụ:

| Nhóm | Vai trò | Điều không được suy |
| --- | --- | --- |
| **GC worker/concurrent threads** | Thu gom, đánh dấu, xử lý heap, đôi khi concurrent với application | RUNNABLE GC thread không đồng nghĩa GC deadlock |
| **C1/C2 CompilerThread** | Biên dịch hot bytecode thành native machine code | Dùng CPU JIT không chứng minh business thread bị deadlock |
| **Reference Handler** | Phục vụ cơ chế xử lý references theo thiết kế VM | WAITING không mặc nhiên là hỏng |
| **Finalizer (nếu tồn tại)** | Hỗ trợ finalization lịch sử đã bị discourage/deprecate | Không dùng tên thread làm cam kết mọi JDK có finalizer |
| **Common-Cleaner / cleaners** | Dọn resource qua cleaning mechanisms | WAITING khi chưa có task là bình thường |
| **Service Thread / VM Thread** | Công việc và coordination nội bộ VM | Thread name/states khác theo build |
| **Attach Listener (nếu được tạo)** | Phục vụ các thao tác chẩn đoán/attach | Không phải HTTP worker nghiệp vụ |
| **Signal Dispatcher** | Xử lý signaling/runtime events trên nền tảng hỗ trợ | Trạng thái WAITING thường hợp lệ |
| **Sweeper / code-cache support** | Theo dõi một số phần của compiled code cache khi có | Không đồng nghĩa app đã hoàn tất warm-up |
| **User-created background pool threads** | Scheduled tasks, HTTP clients, executor maintenance | Không phải tự động là JVM internal threads |

**Tên thực tế thay đổi theo JDK, collector, architecture, flags và tình trạng khởi tạo subsystem.** Đừng yêu cầu thread dump phải chứa chính xác một danh sách trên mới gọi là Java 17.

### 13.1. GC đồng thời không phải stop-the-world toàn thời gian

Ví dụ collector có **concurrent mark threads** đang chạy trong lúc mutators cũng chạy. GC thread dùng CPU nhưng không đồng nghĩa application threads bị dừng suốt giai đoạn đó.

Ngược lại khi JVM có **GC STW pause/safepoint**, nhiều application threads có thể đồng thời không tiến triển trong một khoảng, nhưng đó **không phải deadlock giữa application locks**. Cần đối chiếu GC logs/safepoint logs với p99 latency và timestamps.

### 13.2. JIT compiler có thể tiêu tốn CPU mà ứng dụng vẫn đúng

C1/C2 compiler threads tạo optimized native code khi methods trở nên hot. Trong warm-up, CPU JIT có thể cao và application response time dao động do resource competition.

Nếu application mất throughput, phải phân biệt:

- JIT đang compile rất nhiều methods và giữ CPU?
- Code cache full khiến compilation bị hạn chế?
- CPU quota/cgroup throttling?
- GC cùng chiếm CPU?
- Chính business code đang busy-spin?

**CompilerThread RUNNABLE không là một dấu hiệu deadlock.** Dùng JFR, compiler logs, jcmd Compiler.queue/codecache để kiểm chứng JIT activity.

### 13.3. Những thread nền chờ công việc là bình thường

Một pool thread có stack tại **LinkedBlockingQueue.take** hoặc **ScheduledThreadPoolExecutor delayed queue** có thể đang idle đúng thiết kế.

Nếu không có backlog và requests vẫn xử lý bình thường, chưa có issue. Nếu task queue tăng mãi mà workers đều đang WAITING theo cách bất thường, cần xác nhận có producer/consumer handoff, permits, cancellation hoặc task submission bug.

## 14. Daemon threads và JVM process lifetime

**Daemon thread** là một thuộc tính ảnh hưởng điều kiện JVM kết thúc khi không còn non-daemon threads đang sống. Daemon **không đồng nghĩa** “thread của JVM nội bộ” hoặc “thread được ưu tiên CPU thấp”.

Các điểm đúng:

- Application có thể tự tạo daemon threads.
- JVM có runtime threads với policies khác nhau.
- Một daemon thread WAITING có thể hoàn toàn bình thường.
- JVM có thể kết thúc khi chỉ còn daemon threads, không chờ chúng hoàn tất công việc nghiệp vụ.
- Một non-daemon thread WAITING vô hạn có thể khiến JVM process vẫn sống.
- Một daemon thread bị deadlock vẫn là bug nếu công việc cần nó bị ảnh hưởng, dù daemon status khác.

Không chỉnh tất cả threads thành daemon để “chữa treo khi shutdown”; cần sửa lifecycle, task cancellation và executor shutdown protocol.

### 14.1. Shutdown issues khác deadlock

Một server không thoát sau shutdown request có thể vì:

- Non-daemon executor worker chưa shutdown.
- Scheduled task vẫn active.
- Consumer chờ queue không được signal/cancel.
- Socket listener chưa đóng.
- A thread giữ monitor bị kẹt, có thể deadlock hoặc long wait.
- Shutdown hook chờ external resource.
- JVM thật đang thực hiện work mà application chưa accounting.

Dùng thread dumps tại shutdown và kiểm tra executor shutdownNow/awaitTermination theo protocol; **không tự gọi System.exit** để che root cause trong thiết kế thư viện.

## 15. JVM còn đang làm việc: cách đối chiếu logs với thread dumps

Một tình huống thực tế:

~~~text
14:00:00 Request starts
14:00:01 HTTP thread waiting
14:00:02 JIT/compiler activity
14:00:03 GC concurrent mark
14:00:04 Request still waiting
14:00:05 New thread dump
~~~

Điều này **không chứng minh** JIT hoặc GC là nguyên nhân request chưa xong. Hãy dựng timeline dựa trên dữ liệu:

1. Request trace cho biết nó đang chờ lock, DB, socket, future hay task?
2. Thread dump cho biết waiting location và lock owner?
3. GC log có STW pause đúng thời gian không, duration bao nhiêu?
4. CPU profile có compiler/GC thread đang chiếm phần lớn CPU quota không?
5. Service metrics có queue backlog, connection pool exhausted hoặc request concurrency spike không?
6. Thread states có giống nhau qua nhiều snapshots cách nhau một khoảng có chủ đích không?

**Correlation chưa đủ causation.** GC/JIT có thể đồng thời hiện diện như background noise trong incident do deadlock của ứng dụng.

## 16. jcmd: bước đầu tiên để xem JVM đang sống

Trên HotSpot JDK 17, từ máy/process namespace thích hợp:

~~~bash
jcmd
jcmd <PID> help
jcmd <PID> VM.version
jcmd <PID> VM.uptime
jcmd <PID> Thread.print
jcmd <PID> Thread.print -l
~~~

**<PID>** là placeholder cần thay bằng process ID thực, không phải literal string. Quyền attach thường cần cùng user/permissions phù hợp; trong containers phải chú ý PID namespace. Nếu jcmd command không được hỗ trợ, đọc **jcmd <PID> help** trên build đích.

**Thread.print -l** có thể bổ sung thông tin java.util.concurrent ownable synchronizers. Thread dump có overhead (impact thường medium, phụ thuộc thread count); tránh chụp quá dày trên máy nhiều threads.

### 16.1. jstack

~~~bash
jstack <PID>
jstack -l <PID>
~~~

jstack có thể in full thread dumps và lock details tùy JDK build/attach support. Dùng **jcmd Thread.print** như lựa chọn quan sát ban đầu với HotSpot hiện đại; không coi jstack đã deprecated/không tồn tại ở mọi Java17 distributions.

### 16.2. Cách đọc một stack fragment

~~~text
"http-worker-7" ... java.lang.Thread.State: BLOCKED
    at com.example.Service.update(Service.java:77)
    - waiting to lock <0xABC> (a java.lang.Object)

"http-worker-3" ... java.lang.Thread.State: RUNNABLE
    at com.example.Service.persist(Service.java:32)
    - locked <0xABC> (a java.lang.Object)
~~~

Đây là **thread-dump example minh họa**, không phải một output được lấy từ JVM thật. Nó cho biết worker-7 muốn acquire monitor **0xABC**, worker-3 đang giữ monitor đó tại lúc dump.

Để chẩn đoán, tiếp tục điều tra worker-3 đang thực hiện gì, đang chờ I/O hay locks khác không, sau bao lâu nó release.

### 16.3. Thread dump ID/lock identity

- Thread name do application/JVM đặt, có thể trùng hoặc đổi.
- Thread ID trong Java API khác **native OS thread ID** theo nền tảng.
- Một stack có thể hiển thị **nid** hexadecimal và **tid** dạng VM ID/native pointer tùy dump format.
- Lock identity trong thread dump thường là VM object identity/address-like token, **không phải Java reference public API**.
- Không so sánh chỉ theo tên object class khi xác định same monitor; cần đúng lock identity.

### 16.4. Multi-snapshot: hai hoặc ba thời điểm

Chụp một bản dump, chờ khoảng thời gian hữu ích với service (ví dụ 5–10 giây nếu phù hợp), rồi chụp tiếp:

~~~bash
jcmd <PID> Thread.print -l
# Sau một khoảng quan sát thích hợp:
jcmd <PID> Thread.print -l
~~~

Mục tiêu:

- Same thread vẫn waiting on same lock?
- Lock owner thay đổi hay không?
- Owner stack thay đổi hay “đứng” trên một call?
- Có cùng monitor cycle nhiều snapshots?
- Request queue backlog tăng/giảm?
- GC/JIT background activity thay đổi?
- CPU per-thread counters/stack sampling cho biết thread thực sự làm việc?

**Không lấy “stack giống nhau hai lần” làm bằng chứng tuyệt đối deadlock.** Một blocking read hoặc polling loop cũng có thể có stack giống qua nhiều lần chụp.

## 17. Quy trình dựng wait-for graph từ thread dump

Giả sử dump có:

~~~text
T1: BLOCKED waiting to lock B; owns A
T2: BLOCKED waiting to lock C; owns B
T3: BLOCKED waiting to lock A; owns C
~~~

Vẽ:

~~~text
T1 --waits for B owned by--> T2
T2 --waits for C owned by--> T3
T3 --waits for A owned by--> T1

Cycle: T1 -> T2 -> T3 -> T1
~~~

Nếu lock infos đáng tin và không có thay đổi phá cycle, đây là một Java monitor deadlock.

### 17.1. Kiểm chứng theo từng bước

1. Chọn thread bị ảnh hưởng trực tiếp đến request/SLA.
2. Ghi lock identity mà thread đang cố acquire.
3. Tìm owner thread của lock ấy ở snapshot.
4. Đọc owner stack và resource mà owner đang chờ.
5. Tiếp tục theo quan hệ owner→waiter đến khi có vòng, dead end hoặc external wait.
6. Nếu có vòng, đối chiếu với **ThreadMXBean.findDeadlockedThreads()**/dump diagnostic khi có.
7. Nếu không có vòng, điều tra long-held lock, I/O, starvation hoặc missing signal.
8. So với timeline request/GC/CPU để xác định tác động thật.

### 17.2. Deadlock detection không bao quát toàn bộ thế giới

Những tình huống có thể thoát khỏi detector chuẩn:

- Thread-pool starvation do Future.get() trên cùng worker pool.
- Distributed lock/DB row deadlocks ngoài JVM.
- Missing CountDownLatch countdown.
- Logical condition cycles không biểu diễn bằng ownable lock owners.
- Một deadlock chỉ xảy ra trong thời gian ngắn rồi được xử lý bằng timeout/interrupt.
- Mismatch giữa JMX visibility và virtual-thread implementations ở JDK mới.

Vì vậy **findDeadlockedThreads()==null không có nghĩa mọi threads có progress guarantee**.

## 18. Java Flight Recorder (JFR) để đo lock contention và waiting

JFR hỗ trợ ghi events để liên hệ thread behavior với timeline. Tùy Java 17 recording settings:

- **jdk.JavaMonitorEnter**: các sự kiện contended monitor entry phù hợp.
- **jdk.JavaMonitorWait**: Object.wait related.
- **jdk.ThreadPark**: LockSupport park-related events.
- **GC events**: GC pauses/concurrent phases.
- **Execution/CPU samples**: business or compiler/GC CPU activity khi event tương ứng được bật.

Ví dụ khởi động một app main class:

~~~bash
java -XX:StartFlightRecording=filename=thread-diag.jfr,duration=60s,settings=profile MyService
~~~

Cần có class MyService thực và môi trường hỗ trợ JFR. Nếu app dừng trước 60s, recording duration và output phụ thuộc lifecycle/settings.

Đọc bằng CLI:

~~~bash
jfr summary thread-diag.jfr
jfr print --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.ThreadPark thread-diag.jfr
~~~

**Không có event không chứng minh code không có synchronized hoặc park.** Event có thể bị tắt, threshold lọc duration, hoặc không xuất hiện trong sampling interval.

### 18.1. Quan sát tiến trình đã chạy bằng jcmd JFR

~~~bash
jcmd <PID> JFR.start name=threadcase settings=profile duration=60s filename=threadcase.jfr
jcmd <PID> JFR.check
~~~

Cú pháp options tùy HotSpot JDK build; đọc **jcmd <PID> help JFR.start** để xác nhận. Recording có chi phí CPU/disk/storage theo cấu hình, vì vậy cần quản lý retention.

### 18.2. Dùng JFR để đo thay vì đếm BLOCKED snapshots

Một request có thể BLOCKED 2 ms mỗi lần nhưng xảy ra hàng nghìn lần/s, gây throughput problems; một snapshot mỗi 10s có thể không trúng thời điểm BLOCKED. JFR duration-based events giúp nhìn contention frequency/time distribution tốt hơn khi được bật với thresholds thích hợp.

## 19. GC logs và safepoints: phân biệt JVM pause với application lock wait

Trên HotSpot Java 17, bật Unified Logging có chọn lọc:

~~~bash
java -Xlog:gc=info -Xlog:safepoint=info MyService
~~~

**MyService** là class minh họa có main. Tag availability/format xác nhận bằng:

~~~bash
java -Xlog:help
~~~

Khi JVM làm một stop-the-world GC phase, application threads có thể tạm dừng để GC xử lý. Những threads ấy **không thể tự tạo lock cycle** chỉ từ việc GC pause.

### 19.1. GC overhead vs application stall

| Quan sát | Khả năng | Cần thêm chứng cứ |
| --- | --- | --- |
| GC pause log trùng request p99 spike | Có thể do STW GC | Request trace, duration correlation |
| GC concurrent marking kéo dài | Có thể GC dùng CPU đồng thời | CPU profile, GC logs và app throughput |
| Nhiều BLOCKED trên cùng monitor | Lock contention | Owner stack, hold time, wait-for graph |
| WAITING tại BlockingQueue.take | Có thể idle hợp lệ | Task queue depth, producers, pending requests |
| RUNNABLE C2 CompilerThread | JIT đang tiêu CPU | Compiler.queue/codecache, CPU load |
| CPU bị container throttle | Thiếu CPU progress | cgroup/OS metrics |
| JVM heap gần max và allocation stalls | Memory pressure | GC/heap telemetry |
| Future.get() chờ task trên single-thread pool | Pool starvation | Executor queue và worker stacks |

### 19.2. “JVM đang hoạt động” không chứng minh request progressing

GC/JIT/Reference Handler threads có thể còn làm việc, trong khi HTTP threads deadlocked. Process vẫn có thể trả health check bằng một thread pool khác, che sự cố của đường nghiệp vụ.

Do đó health checks nên kiểm tra readiness/end-to-end components phù hợp, không chỉ “JVM PID tồn tại”.

## 20. JIT work: theo dõi compiler queue và code cache

Trong Java 17 HotSpot:

~~~bash
jcmd <PID> Compiler.queue
jcmd <PID> Compiler.codecache
jcmd <PID> Compiler.codelist
~~~

- **Compiler.queue:** compilation tasks đang đợi hoặc được quản lý theo tool.
- **Compiler.codecache:** layout/usage của generated native code cache.
- **Compiler.codelist:** compiled methods đang sống được tool in ra.

CompilerThread RUNNABLE có thể là JIT warm-up hợp lệ. Nếu compiler queue backlog kéo dài và JIT CPU chiếm resource nhiều, request throughput có thể bị ảnh hưởng dù không deadlock.

**Không lấy một snapshot queue trống làm chứng minh JVM không chạy JIT.** Tasks có thể đã xử lý xong; code cache vẫn chứa compiled methods.

### 20.1. Background thread chiếm CPU nhưng không gây deadlock

Có thể do:

- Startup/warm-up compilation.
- GC marking concurrent.
- Reference processing backlog.
- Scheduled internal VM operations.
- Application logging/metrics daemon threads.
- An application busy loop disguised as daemon service.

Cần thread CPU samples theo tên/native thread ID và stack, không chỉ xem Thread.State.

### 20.2. CPU throttling không tạo Java monitor cycle

Một owner thread có thể mất nhiều wall-clock time để release lock vì không được OS scheduler cấp CPU. Waiters sẽ BLOCKED lâu, nhưng vấn đề root cause là CPU quota/oversubscription, không phải lock-order inversion. Điều này đặc biệt quan trọng trong containers với cgroup quotas.

## 21. Cách tránh deadlock: thiết kế lock ordering

Một cách phòng deadlock nhiều object monitors là **global lock order**.

Giả sử hai locks cố định A và B, mọi threads luôn acquire A trước B, và release theo lexical nesting:

~~~java
synchronized (a) {
    synchronized (b) {
        // Cập nhật state liên quan cả a và b.
    }
}
~~~

Không cho một code path acquire B rồi A; nếu tuân thủ nhất quán, vòng chờ kiểu A→B/B→A không thể hình thành cho hai locks ấy.

### 21.1. Demo Java 17+ #4: nhiều threads nhưng có lock order

Tạo **OrderedLocksDemo.java**:

~~~java
public class OrderedLocksDemo {
    private static final Object FIRST = new Object();
    private static final Object SECOND = new Object();
    private static int count;

    private static void increment() {
        synchronized (FIRST) {
            synchronized (SECOND) {
                count++;
            }
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Thread[] workers = new Thread[4];

        for (int t = 0; t < workers.length; t++) {
            workers[t] = new Thread(() -> {
                for (int i = 0; i < 2_000; i++) {
                    increment();
                }
            });
        }

        for (Thread thread : workers) {
            thread.start();
        }
        for (Thread thread : workers) {
            thread.join();
        }

        System.out.println("count=" + count);
        System.out.println("expected=" + (4 * 2_000));
        System.out.println("correct="
                + (count == 4 * 2_000));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 -encoding UTF-8 OrderedLocksDemo.java
java OrderedLocksDemo
~~~

**Stdout chính xác khi kết thúc bình thường:**

~~~text
count=8000
expected=8000
correct=true
~~~

- Mỗi worker thực hiện 2.000 increments.
- Mỗi increment acquire FIRST rồi SECOND, không có code path đảo thứ tự.
- count++ nằm trong critical section chung nên không lost updates.
- Main join tất cả threads rồi đọc count.
- **Output không chứng minh mọi thiết kế khác của hệ đều không deadlock**, chỉ cho thấy ví dụ này có ordering và progress bình thường.

### 21.2. Nếu locks phụ thuộc object identity động?

Nếu cần acquire hai account locks dựa trên objects động, hãy chọn một **stable total order** như account ID duy nhất và luôn acquire từ ID nhỏ đến lớn. Tránh dùng hashCode/identityHashCode đơn độc như total order nếu có nguy cơ collision; khi collision, cần tie-breaker lock hoặc một giải pháp deterministic bổ sung. Việc chỉ sắp xếp theo tên biến a,b trong mỗi caller không đủ nếu callers đảo arguments.

## 22. ReentrantLock: timeouts và interruption

Với intrinsic synchronized, **không có built-in tryLock(timeout)** và một thread đang BLOCKED chờ monitor entry không tự thoát chỉ vì bạn gọi interrupt như với một interruptible lock API.

ReentrantLock hỗ trợ:

~~~java
// Ví dụ phương thức trong class có ReentrantLock lock:
if (lock.tryLock(100,
        java.util.concurrent.TimeUnit.MILLISECONDS)) {
    try {
        // Critical section.
    } finally {
        lock.unlock();
    }
} else {
    // Timeout: log, retry/backoff hoặc fail fast theo hợp đồng.
}
~~~

Cần catch/declare InterruptedException phù hợp. TryLock timeout cho đường **không acquire được lock** một kết quả có thể xử lý, nhưng không tự khắc phục tất cả deadlocks: nếu thread giữ A rồi timeout B, bạn vẫn phải **release A đúng trong finally** và xử lý state consistency.

### 22.1. lockInterruptibly

**ReentrantLock.lockInterruptibly()** cho phép bỏ chờ lock khi có interrupt, khác intrinsic synchronized entry. Một thiết kế cancellation tốt có thể dùng method này, nhưng phải đảm bảo khi đã acquire thì unlock trong finally.

### 22.2. Đừng nới synchronization bằng cách xóa lock

Nếu app deadlock vì lock order sai, bỏ synchronized có thể tạo data races, mất cập nhật hoặc corrupted state. Cần sửa protocol: thống nhất ordering, giảm scope, dùng immutable messages, actor pattern/queues hoặc locks có timeout và rollback logic đúng.

## 23. Long-held locks và I/O trong critical section

Một pattern không tốt:

~~~java
synchronized (lock) {
    databaseCall(); // Có thể block vì DB/network.
    cache.put(key, value);
}
~~~

Nếu databaseCall mất 20 giây, các threads khác cần lock sẽ chờ suốt 20 giây. Đó có thể là **lock convoy do blocking I/O**, không phải circular deadlock trong JVM.

Cân nhắc:

~~~java
Result result = databaseCall();

synchronized (lock) {
    cache.put(key, result);
}
~~~

Nhưng chỉ làm vậy nếu **business invariant** không đòi DB call và cache update phải nằm trong cùng một atomic protocol. Nếu có yêu cầu ordering/versioning/transactions, cần thiết kế lại kỹ thay vì chuyển code ra ngoài lock một cách máy móc.

### 23.1. Lock scope là vấn đề correctness lẫn latency

- Scope quá rộng: contention, tail latency, khả năng giữ lock qua I/O.
- Scope quá hẹp: phá invariants và tạo check-then-act races.
- Nested locks không nhất quán: deadlock risk.
- Calling externally supplied callbacks dưới lock: khó đoán locks mà code ngoài có thể acquire.
- Synchronized on public objects/String literals: nguy cơ code không liên quan vô tình share monitor.

Hãy ghi rõ state nào thuộc lock nào và transaction boundary ở đâu.

## 24. Một thread dump cho biết gì và không cho biết gì?

**Có thể giúp tìm:**

- Thread names/IDs và trạng thái tại snapshot.
- Stack frame hiện tại.
- Địa điểm chờ acquire monitor/ownable synchronizer.
- Lock owner/held locks khi JVM/tool cung cấp.
- Một số Java-level deadlock cycles.
- JVM runtime/background threads đang hiện diện.

**Không đủ để khẳng định:**

- Tổng CPU usage trong nhiều phút.
- Hoạt động I/O downstream có hoàn thành không.
- Deadlock ở external DB row locks.
- Root cause chính xác của mọi request latency.
- Một WAITING thread là leak hoặc deadlock.
- Background JVM thread đang RUNNABLE nghĩa application threads bị dừng.
- Không có output mới nghĩa Java heap GC ngừng hoạt động.
- Lock acquisition order đã đúng ở mọi code path.

Cần ghép dump với logs, traces, counters và điều kiện cụ thể của service.

## 25. Phương pháp điều tra production theo thứ tự ưu tiên

### Bước 1 — Ghi triệu chứng và phạm vi

- Cả JVM mất response hay chỉ một endpoint?
- Các requests mới còn được nhận?
- Throughput bằng 0 hay chỉ giảm?
- Health check phản ánh đúng business readiness?
- CPU%, RSS, heap/GC, network/DB state?
- Sự cố xảy ra từ deploy/change traffic nào?

### Bước 2 — Ghi JDK và cấu hình

~~~bash
java -version
jcmd <PID> VM.version
jcmd <PID> VM.flags
jcmd <PID> VM.uptime
~~~

VM.flags có thể chứa options liên quan GC/JIT/logging/CPU. Đừng dùng danh sách HotSpot background thread names của một JDK khác làm tiêu chuẩn.

### Bước 3 — Thu nhiều thread dumps an toàn

~~~bash
jcmd <PID> Thread.print -l
~~~

Lưu output kèm timestamp; sau một khoảng hữu ích lại lấy snapshot. Tránh ghi credentials hoặc request payload nhạy cảm vào báo cáo vì stack/dump có thể chứa class names, identifiers và business context.

### Bước 4 — Phân loại affected threads

- BLOCKED trên object monitor nào?
- WAITING tại wait/join/park/latch/future?
- RUNNABLE trong business loop hay native I/O?
- TIMED_WAITING theo timeout bình thường?
- Thread nào là app workers, thread nào là JVM internal?
- Có một owner giữ nhiều locks không?

### Bước 5 — Dựng wait-for graph

Theo các lock owners để tìm cycles. Nếu có cycle, kiểm tra ThreadMXBean/jcmd deadlock report và class/method order dẫn tới inversion.

### Bước 6 — Nếu không thấy cycle, tìm missing progress

- Một future/task đang chờ pool có worker trống không?
- Producer có quên countDown/notify/completion không?
- I/O có timeout và circuit breaker không?
- CPU quota có đang throttle owner thread không?
- Thread đang spin hay có blocking state hợp lệ?
- GC/safepoint pauses hoặc allocation stalls có trùng p99?

### Bước 7 — So timeline JVM vs service

- GC log/safepoint log.
- JFR monitor enter/wait/park, CPU samples.
- Request traces, queue depth và DB timings.
- Compiler.queue/codecache nếu nghi JIT warm-up.
- Thread CPU consumption theo tool phù hợp.

### Bước 8 — Đưa biện pháp đúng nguyên nhân

- Deadlock lock order → thống nhất global order, giảm nesting.
- Long-held lock → giảm I/O trong critical section nếu an toàn.
- Missing signal → sửa predicate/cancellation/notifyAll protocol.
- Pool starvation → loại synchronous dependency trong same pool hoặc tăng capacity phù hợp.
- CPU throttling → sửa quotas/scaling/expensive work, không đổ lỗi “synchronized deadlock”.
- GC pause → tune/giảm allocation, nhưng chỉ sau khi logs xác nhận.
- JIT overhead → warm-up/CPU budget/diagnostics, không xóa synchronized tùy tiện.
- External DB locks → xử lý transaction order ở DB layer.

### Bước 9 — Ngăn tái phát

- Viết stress/liveness tests có timeouts hợp lý.
- Instrument lock wait time, queue age, pending futures, executor active/queued tasks.
- Alert trên request p99, throughput, CPU throttling, GC pauses, backlog.
- Gắn thread names với subsystem ownership.
- Dùng graceful shutdown/cancellation.
- Code review lock graphs khi thêm synchronization mới.

## 26. Tình huống chẩn đoán có lời giải

### Tình huống A — Một thread BLOCKED 2 giây, owner đang xử lý

**Dữ kiện:** T2 chờ M của T1, T1 chưa chờ lock khác; T1 đang persist dữ liệu. Đây là **contention/long-held lock**, chưa chứng minh deadlock. Kiểm tra I/O duration, critical section scope, T1 progress; nếu T1 release thì T2 có thể chạy.

### Tình huống B — Hai thread đều BLOCKED trên monitor của nhau

**Dữ kiện:** T1 holds A waits B; T2 holds B waits A. Có circular wait, là **monitor deadlock** nếu dependencies vẫn tồn tại. Sửa lock ordering, tránh hold-and-wait.

### Tình huống C — 100 pool workers WAITING tại BlockingQueue.take()

**Dữ kiện:** Queue trống, không có requests tồn đọng. Có thể là **idle đúng thiết kế**. Không cần chữa deadlock.

### Tình huống D — 100 workers WAITING nhưng queue requests đang tăng

**Dữ kiện:** Có mismatch giữa incoming tasks và dispatch/permits/wakeup. Cần kiểm tra có đang nhìn đúng queue và đúng executor, producer flow, task submission và pool lifecycle. Không vội kết luận JVM deadlock.

### Tình huống E — G1 concurrent GC thread RUNNABLE, HTTP thread WAITING

**Dữ kiện:** Có thể hai điều kiện độc lập. GC thread làm việc nền; HTTP thread có thể chờ future. Dùng timestamps/GC logs/CPU data để kiểm chứng quan hệ nhân quả.

### Tình huống F — C2 CompilerThread dùng 80% một CPU

**Dữ kiện:** Có thể warm-up hoặc compilation churn; không phải deadlock. Xem Compiler.queue, codecache, JFR/CPU profile, JVM uptime và throughput.

### Tình huống G — Single-thread executor A chờ B do chính pool thực thi

**Dữ kiện:** A giữ sole worker và Future.get chờ B đang queued; đây là **thread-pool starvation deadlock**, không nhất thiết được monitor deadlock detector báo. Sửa task dependency architecture hoặc executor capacity.

### Tình huống H — Thread.sleep trong synchronized

**Dữ kiện:** Thread vẫn giữ monitor, các contenders có thể BLOCKED. Đó là lock contention/possibly poor design, không phải sleep nhả lock.

### Tình huống I — Thread đang Object.wait()

**Dữ kiện:** Waiter đã tạm release receiver monitor, và phải reacquire trước khi return. Nếu notifier quên phát predicate/signal, đây là missing condition progress. Nếu notifier bị kẹt trên một unrelated lock mà waiter vẫn giữ, có thể thành liveness deadlock.

### Tình huống J — findDeadlockedThreads trả null, service vẫn đứng

**Dữ kiện:** Không thấy covered owner cycles tại thời điểm đo, nhưng có thể external resource wait, pool starvation, condition wait, livelock, starvation hoặc CPU/GС problems. Tiếp tục điều tra.

### Tình huống K — HTTP worker RUNNABLE ở native socketRead

**Dữ kiện:** RUNNABLE không phải nhất định busy CPU loop. Có thể thread đang chờ I/O theo implementation; kiểm tra socket/DB/network timeout.

### Tình huống L — JVM chỉ còn daemon threads và sắp thoát

**Dữ kiện:** Đây là process lifetime semantics, không tự chứng minh deadlock. Kiểm tra business tasks nào đang chạy trong daemon workers và liệu shutdown có cancel đúng.

## 27. 25 câu hỏi tự kiểm tra có đáp án

**Câu 1.** Một thread BLOCKED có chứng minh deadlock không?

**Đáp án:** Không. BLOCKED nghĩa chờ object monitor; có thể là contention nếu owner sẽ release.

**Câu 2.** Deadlock monitor kinh điển cần gì ngoài một thread chờ lock?

**Đáp án:** Cần vòng chờ, ví dụ T1 owns A waits B và T2 owns B waits A.

**Câu 3.** RUNNABLE nghĩa thread chắc đang chạy CPU 100%?

**Đáp án:** Không; có thể sẵn sàng chạy, đang native I/O hoặc chưa được scheduler cấp CPU.

**Câu 4.** Thread pool idle thường có WAITING có phải bug?

**Đáp án:** Không nếu đang chờ task/condition hợp lệ và không có backlog bị bỏ quên.

**Câu 5.** Thread.sleep có nhả monitor hiện giữ không?

**Đáp án:** Không.

**Câu 6.** Object.wait có nhả monitor không?

**Đáp án:** Có, nhả receiver monitor theo rules và phải reacquire trước return; không nhả unrelated locks.

**Câu 7.** notifyAll có trao monitor lập tức cho waiter không?

**Đáp án:** Không; notifier vẫn giữ monitor tới khi unlock.

**Câu 8.** WAITING tại Future.get trên single-thread executor có thể là liveness bug gì?

**Đáp án:** Thread-pool starvation/self-deadlock khi task đang chạy chờ task queued vào chính sole worker pool.

**Câu 9.** JVM background GC thread RUNNABLE có chứng minh toàn JVM STW không?

**Đáp án:** Không; concurrent GC work có thể chạy cùng application threads.

**Câu 10.** C2 CompilerThread tiêu CPU có phải monitor deadlock?

**Đáp án:** Không; nó có thể đang biên dịch code.

**Câu 11.** ReentrantLock.lock() wait luôn là BLOCKED?

**Đáp án:** Không; AQS/LockSupport có thể hiển thị WAITING/TIMED_WAITING.

**Câu 12.** API nào tìm monitor-only deadlock cycle?

**Đáp án:** ThreadMXBean.findMonitorDeadlockedThreads().

**Câu 13.** API nào tìm thêm ownable synchronizers khi được hỗ trợ?

**Đáp án:** ThreadMXBean.findDeadlockedThreads().

**Câu 14.** findDeadlockedThreads trả null chứng minh không có liveness bug?

**Đáp án:** Không; detector không bao quát external locks, missing signals, pool starvation và mọi conditions.

**Câu 15.** Dùng jcmd gì in thread dump?

**Đáp án:** jcmd <PID> Thread.print; thêm -l để quan sát java.util.concurrent locks khi hỗ trợ.

**Câu 16.** Vì sao cần nhiều snapshots?

**Đáp án:** Phân biệt temporary wait với trạng thái kéo dài, xác định owner progress và đối chiếu timeline.

**Câu 17.** Biết lock class là Object có đủ xác định same monitor không?

**Đáp án:** Không; cần đúng object identity/lock token, không chỉ class type.

**Câu 18.** Synchronized nested cùng monitor của owner có tự deadlock không?

**Đáp án:** Không, Java intrinsic monitors reentrant.

**Câu 19.** Nested A→B so với B→A tạo rủi ro gì?

**Đáp án:** Lock-order inversion, circular wait deadlock nếu xảy ra interleaving phù hợp.

**Câu 20.** Lock ordering phòng deadlock như thế nào?

**Đáp án:** Mọi paths acquire nhiều locks theo một total order, ngăn hình thành cycles cho các locks liên quan.

**Câu 21.** Chờ DB row lock có được Java monitor detector thấy chắc chắn không?

**Đáp án:** Không; cần DB diagnostics/external resource waits.

**Câu 22.** Một thread ngủ trong synchronized 30s khiến 50 threads BLOCKED. Root cause phù hợp?

**Đáp án:** Long-held monitor do sleep/I/O trong critical section, chưa chắc circular deadlock.

**Câu 23.** Điều gì xảy ra với daemon threads khi chỉ còn chúng trong JVM?

**Đáp án:** JVM có thể kết thúc mà không chờ daemon tasks hoàn tất theo process lifetime semantics.

**Câu 24.** Thread dump hiển thị WAITING trên BlockingQueue và queue trống: sửa gì?

**Đáp án:** Có thể không cần sửa gì; đây là idle hợp lệ. Kiểm tra đúng executor/task backlog.

**Câu 25.** Ba nhóm dữ liệu chính để phân tích một service không tiến triển?

**Đáp án:** Thread dumps/wait-for graph, application traces/queue/resource state, và JVM/OS metrics như CPU/GC/JIT/safepoint timing.

## 28. Checklist cuối bài

- **Deadlock ≠ BLOCKED ≠ WAITING**; các từ biểu thị những lớp thông tin khác nhau.
- Một cạnh waiter→owner chưa phải deadlock; tìm **cycle**.
- **Thread.State** không map 1–1 sang native OS thread states.
- WAITING trên idle queue, join hoặc latch thường là hợp lệ.
- **Thread.sleep không release monitor** và không tạo synchronization.
- **Object.wait release receiver monitor** rồi reacquire trước return.
- **Intrinsic synchronized reentrant**; nested cùng lock không self-deadlock.
- **ReentrantLock** wait có thể hiển thị WAITING/TIMED_WAITING, không nhất thiết BLOCKED.
- **ThreadMXBean** tìm monitor/ownable-synchronizer cycles trong phạm vi hỗ trợ; null không chứng minh toàn hệ live.
- **JVM GC/JIT/runtime background threads** có thể tiếp tục hoạt động khi application workers không tiến triển.
- JIT/GC CPU activity không là bằng chứng nguyên nhân request latency nếu thiếu timeline.
- **jcmd Thread.print -l** và JFR giúp quan sát, nhưng snapshots/events cần được diễn giải đúng.
- **Global lock ordering** là một biện pháp phòng circular wait quan trọng.
- **Missing signal/pool starvation/external DB locks** có thể treo dù Java deadlock detector không báo.
- Giữ lock scope hợp lý, tránh I/O chậm dưới global lock và có cancellation/timeout khi phù hợp.
- Sau khi chẩn đoán, sửa nguyên nhân thực và đo lại throughput/p99/liveness, không chỉ đổi JVM flags.

### Tài liệu chính thức

- **Java SE 17 — Thread.State enum:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.State.html
- **Java SE 17 — Thread API, sleep, join, daemon threads:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html
- **Java SE 17 — ThreadMXBean deadlock detection:** https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html
- **Java SE 17 — ThreadInfo (lock owner, monitor info):** https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadInfo.html
- **Java SE 17 — jcmd command and Thread.print:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- **Java SE 17 — jstack command:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstack.html
- **Java SE 17 — jfr command:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html
- **Java SE 17 — Java Flight Recorder guide:** https://docs.oracle.com/en/java/javase/17/jfapi/
- **Java SE 17 — Object.wait/notify:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html
- **Java SE 17 — LockSupport:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/LockSupport.html
- **Java SE 17 — ReentrantLock:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html
- **Java SE 17 — CountDownLatch:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html
- **JLS SE 17 — Threads and Locks:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html
- **OpenJDK — JEP 444 Virtual Threads (JDK 21):** https://openjdk.org/jeps/444

**Kết luận:** Một ứng dụng Java có thể có nhiều threads BLOCKED/WAITING, có GC/JIT threads RUNNABLE và vẫn không deadlock. **Deadlock thực đòi xác định một vòng phụ thuộc chờ tài nguyên**; còn chờ monitor tạm thời, điều kiện chưa được phát, pool starvation, I/O chậm và JVM background work có nguyên nhân/biện pháp khác nhau. Quy trình đúng là **đọc thread dump, lần theo owner và wait-for graph, đối chiếu nhiều snapshots với request/GC/JIT/CPU timeline**, rồi sửa đúng lock ordering, signals, pool design hoặc resource bottleneck thay vì chẩn đoán từ một Thread.State đơn lẻ.
