# Đo lock contention trong Java

**Đo lock** là việc thu thập số liệu về thời gian thread chờ lấy khóa, số lần xảy ra tranh chấp, thời gian giữ khóa và ảnh hưởng của khóa đến throughput/latency. Mục tiêu là tìm critical section hoặc lock khiến nhiều thread phải chờ, sau đó giảm thời gian chờ mà vẫn giữ đúng tính nhất quán dữ liệu.

Một lock có thể hoạt động đúng nhưng vẫn trở thành nút thắt hiệu năng. Ví dụ, một cache dùng chung được bảo vệ bởi `synchronized`; khi số request đồng thời tăng, nhiều thread phải xếp hàng để vào cùng một khối code. Nếu critical section thực hiện I/O, tính toán dài hoặc gọi service khác, thời gian chờ của các thread còn lại có thể tăng mạnh.

Không có một chỉ số duy nhất mô tả đầy đủ lock contention. Cần phân biệt **thời gian chờ lấy lock**, **thời gian giữ lock**, **số lần phải chờ**, **độ dài hàng đợi** và **latency của request**. Dùng thread dump để xác định thread/lock liên quan, JFR để đo thời lượng và stack trace theo thời gian, ThreadMXBean để lấy thống kê contention của platform thread, và JMH để benchmark trong môi trường kiểm soát.

## 1. Lock và lock contention là gì?

Lock là cơ chế điều phối quyền truy cập vào tài nguyên dùng chung. Java có nhiều cơ chế đồng bộ:

- Intrinsic monitor thông qua `synchronized` trên method hoặc block.
- Explicit lock như `ReentrantLock` và `ReentrantReadWriteLock`.
- Các synchronizer dựa trên `AbstractQueuedSynchronizer` (AQS), thường dùng `LockSupport.park` khi thread phải chờ.
- `Semaphore`, `CountDownLatch`, `Phaser` và `Condition` điều phối quyền hoặc tín hiệu giữa các thread; không phải tất cả đều là exclusive lock.

**Lock contention** xảy ra khi nhiều thread muốn dùng cùng một lock và ít nhất một thread phải chờ thread khác nhả khóa hoặc cho phép tiếp tục.

Ví dụ:

```java
private final Object lock = new Object();

public void update() {
    synchronized (lock) {
        updateSharedState();
    }
}
```

Nếu một thread đang ở trong `synchronized (lock)`, các thread khác muốn vào cùng monitor phải đợi. Nếu critical section ngắn và số thread thấp, thời gian chờ có thể không đáng kể. Khi số thread cạnh tranh tăng hoặc công việc bên trong lock kéo dài, contention có thể trở thành nút thắt.

## 2. Phân biệt monitor, explicit lock và thread state

Cần biết loại lock trước khi chọn công cụ:

| Cơ chế | Cách thread thường chờ | Bằng chứng phù hợp |
|---|---|---|
| `synchronized` | Thread có thể ở trạng thái `BLOCKED` khi đợi monitor | Thread dump, `ThreadMXBean`, JFR `jdk.JavaMonitorEnter` |
| `Object.wait()` | Thread ở `WAITING` hoặc `TIMED_WAITING`, chờ notification/timeout | Thread dump, JFR `jdk.JavaMonitorWait` |
| `ReentrantLock` | Thread có thể park qua `LockSupport` trong AQS | JFR `jdk.ThreadPark`, thread dump, lock instrumentation |
| `Condition.await()` | Thread park cho đến khi được signal hoặc timeout | JFR `jdk.ThreadPark`, thread dump |
| `Semaphore`/`CountDownLatch` | Thread thường park khi chờ permit hoặc tín hiệu | JFR `jdk.ThreadPark`, thread dump |

`BLOCKED` có ý nghĩa cụ thể: thread đang chờ vào hoặc vào lại intrinsic monitor. `WAITING` và `TIMED_WAITING` rộng hơn; chúng có thể do `Object.wait`, `LockSupport.park`, `Thread.join`, `Condition.await` hoặc các cơ chế chờ khác. Không coi mọi thread `WAITING` là đang tranh chấp lock.

Với `ReentrantLock`, thread chờ thường được park, vì vậy không nên chỉ tìm trạng thái `BLOCKED` trong thread dump. Hãy xem stack trace, blocker, ownable synchronizer và JFR events.

## 3. Những số liệu cần đo

Một phép đo lock hữu ích nên có các số liệu sau:

| Chỉ số | Ý nghĩa | Cách diễn giải |
|---|---|---|
| Acquisition count | Số lần lấy lock | Cho biết tần suất lock được dùng |
| Contended acquisition count | Số lần phải chờ trước khi lấy lock | Tỷ lệ cao cho thấy nhiều thread cạnh tranh |
| Wait time | Thời gian từ lúc bắt đầu yêu cầu lock đến khi lấy được lock | Phản ánh chi phí chờ của caller |
| Hold time | Thời gian từ khi lấy lock đến khi nhả lock | Critical section dài có thể làm tăng hàng đợi |
| Queue length | Số thread đang chờ hoặc ước lượng số thread chờ | Giúp nhận diện lock đang có nhiều waiter |
| Throughput | Số thao tác hoàn thành trong một đơn vị thời gian | Có thể giảm khi contention tăng |
| Latency percentiles | p50, p95, p99 của thao tác | Giúp thấy tail latency do chờ lock |
| CPU và context switch | CPU time, chuyển ngữ cảnh, runnable threads | Phân biệt lock wait với CPU-bound workload |

Hai đại lượng quan trọng nhất là wait time và hold time:

- **Wait time** bắt đầu trước thao tác acquire và kết thúc ngay sau khi lấy được lock.
- **Hold time** bắt đầu sau khi acquire thành công và kết thúc khi unlock/ra khỏi synchronized block.

Nếu hold time cao, hãy rút ngắn critical section. Nếu hold time thấp nhưng wait time vẫn cao, có thể có quá nhiều thread cùng tranh chấp hoặc lock được dùng quá thường xuyên.

Không lấy thời gian của cả method làm wait time. Method có thể còn thực hiện validation, I/O, tính toán hoặc xử lý kết quả bên ngoài lock.

## 4. Quy trình đo lock contention

Một quy trình thực tế:

1. Xác định endpoint, job hoặc thao tác có latency tăng.
2. Ghi lại workload, concurrency, thời điểm và phiên bản JVM.
3. Thu thập nhiều thread dump trong khoảng thời gian xảy ra vấn đề.
4. Xác định lock object, owner thread, waiter threads và stack frame liên quan.
5. Bật JFR recording ngắn để đo thời lượng monitor enter và thread park.
6. Phân tích event theo thread, stack trace, lock class, owner và thời gian.
7. Nếu cần số liệu trong ứng dụng, bật ThreadMXBean contention monitoring hoặc instrument acquisition/hold time.
8. Tái hiện workload bằng JMH nếu cần so sánh các cách triển khai lock.
9. Thử thay đổi một yếu tố và đo lại cùng workload.
10. So sánh throughput, p95/p99, wait time, hold time và CPU trước/sau.

Nên giữ nguyên dữ liệu đầu vào, số thread, thời gian warm-up và cấu hình máy khi so sánh. Nếu workload thay đổi đáng kể, số liệu lock trước/sau không còn trực tiếp so sánh được.

## 5. Dùng thread dump để tìm lock đang bị tranh chấp

Bắt đầu bằng cách tìm PID:

```sh
jcmd -l
```

Lấy thread dump có thông tin lock:

```sh
jcmd 24680 Thread.print -l
```

Có thể yêu cầu thêm thông tin mở rộng:

```sh
jcmd 24680 Thread.print -e -l
```

Thay `24680` bằng PID của JVM đích. Kiểm tra trợ giúp trên đúng JVM bằng `jcmd 24680 help Thread.print`; `Thread.print` có impact Medium, phụ thuộc số lượng thread.

Ví dụ một phần thread dump:

```text
"worker-2" #42 prio=5 os_prio=0 tid=0x... nid=0x... BLOCKED
   java.lang.Thread.State: BLOCKED (on object monitor)
    at com.example.Cache.update(Cache.java:48)
    - waiting to lock <0x0000000712345678> (a java.lang.Object)
    at com.example.OrderService.process(OrderService.java:91)

"worker-1" #41 prio=5 os_prio=0 tid=0x... nid=0x... RUNNABLE
    at com.example.Cache.rebuild(Cache.java:27)
    - locked <0x0000000712345678> (a java.lang.Object)
    at com.example.OrderService.refresh(OrderService.java:55)
```

Trong ví dụ:

- `worker-2` đang `BLOCKED`, chờ lấy monitor.
- `worker-1` đang giữ monitor có cùng object identity.
- Stack trace cho biết waiter đang gọi `Cache.update`, còn owner đang chạy `Cache.rebuild`.
- Critical section của owner là điểm cần kiểm tra trước tiên.

Object address trong thread dump chỉ có ý nghĩa trong snapshot đó; không dùng nó làm ID ổn định giữa các lần dump hoặc các lần JVM khởi động.

### Lấy nhiều thread dump

Một snapshot chỉ cho biết trạng thái tại một thời điểm. Lấy thêm hai hoặc ba snapshot cách nhau vài giây:

```sh
jcmd 24680 Thread.print -l > thread-01.txt
```

Sau khoảng vài giây:

```sh
jcmd 24680 Thread.print -l > thread-02.txt
```

Và tiếp tục:

```sh
jcmd 24680 Thread.print -l > thread-03.txt
```

So sánh các snapshot:

- Cùng waiter liên tục chờ cùng owner/lock: contention có thể kéo dài.
- Owner thay đổi nhưng waiter vẫn tăng: nhiều thread đang nối tiếp giữ lock.
- Thread không còn chờ trong snapshot tiếp theo: có thể contention chỉ xảy ra ngắn.
- Nhiều thread chờ cùng một lock: lock đó có thể là điểm tuần tự hóa của workload.

Không kết luận deadlock chỉ từ nhiều thread `BLOCKED`. Deadlock cần có chu trình phụ thuộc lock; contention thông thường vẫn có owner đang chạy và cuối cùng sẽ nhả khóa.

## 6. Đo synchronized monitor bằng JFR

Java Flight Recorder (JFR) ghi event có timestamp và duration. Các event hữu ích khi đo lock:

| JFR event | Dùng để quan sát |
|---|---|
| `jdk.JavaMonitorEnter` | Thời gian thread chờ để vào intrinsic monitor, thường liên quan `synchronized` |
| `jdk.JavaMonitorWait` | Thời gian thread chờ trong `Object.wait()` |
| `jdk.ThreadPark` | Thời gian thread bị park qua `LockSupport`, thường gặp với AQS, `ReentrantLock` và `Condition` |
| `jdk.JavaMonitorInflate` | Sự kiện monitor inflation; hữu ích trong một số phân tích monitor, không phải phép đo tổng contention |

Không nhầm `JavaMonitorWait` với `JavaMonitorEnter`: một event theo dõi chờ notification/timeout qua `Object.wait`, event còn lại theo dõi thời gian chờ lấy monitor.

JFR event có thể được lọc theo threshold. Nếu threshold là `10 ms`, event ngắn hơn ngưỡng có thể không được ghi. Giảm threshold giúp quan sát các lần chờ ngắn hơn nhưng sẽ tạo nhiều event và dữ liệu hơn. Stack trace giúp xác định code path gây contention.

## 7. Bắt đầu JFR recording cho lock

Tìm PID:

```sh
jcmd -l
```

Kiểm tra command:

```sh
jcmd 24680 help JFR.start
```

Bắt đầu một recording ngắn với cấu hình `profile` và đặt threshold riêng cho các event lock:

```sh
jcmd 24680 JFR.start name=lock-profile settings=profile duration=60s filename=lock-profile.jfr jdk.JavaMonitorEnter#threshold=1ms jdk.JavaMonitorEnter#stackTrace=true jdk.JavaMonitorWait#threshold=1ms jdk.ThreadPark#threshold=1ms jdk.ThreadPark#stackTrace=true
```

Giải thích:

- `name=lock-profile`: tên recording để kiểm tra và dump.
- `settings=profile`: thu thập nhiều dữ liệu hơn cấu hình `default`; phù hợp với phiên điều tra ngắn.
- `duration=60s`: recording tự kết thúc sau 60 giây.
- `filename=lock-profile.jfr`: file được ghi khi recording dừng.
- `jdk.JavaMonitorEnter#threshold=1ms`: ghi monitor enter event có duration từ ngưỡng này trở lên.
- `stackTrace=true`: lưu stack trace cho event tương ứng.
- `jdk.ThreadPark`: giúp xem các lần park khi thread chờ lock/synchronizer.

Nếu cần xem recording đang chạy:

```sh
jcmd 24680 JFR.check name=lock-profile verbose=true
```

Có thể dump snapshot trước khi recording kết thúc:

```sh
jcmd 24680 JFR.dump name=lock-profile filename=lock-snapshot.jfr begin=-30s
```

`JFR.dump` tạo file snapshot và recording vẫn tiếp tục chạy. Nếu dùng `duration=60s`, recording sẽ tự dừng khi hết thời gian và ghi file `lock-profile.jfr`.

Nếu cần recording dài hơn, cân nhắc `settings=default`, giới hạn thời gian/dung lượng và chỉ bật event cần thiết. Không dùng cấu hình profiling chi tiết trong thời gian dài khi chưa đánh giá overhead.

## 8. Phân tích JFR bằng JDK Mission Control và jfr CLI

Mở `lock-profile.jfr` bằng JDK Mission Control (JMC). Tập trung vào:

- Lock instances và monitor contention nếu phiên bản JMC cung cấp trang tương ứng.
- Event `Java Monitor Enter` và `Thread Park`.
- Duration và phân bố thời gian chờ.
- Thread name/ID của waiter.
- Stack trace tại nơi bắt đầu chờ.
- Monitor class, previous owner hoặc blocker nếu event cung cấp.
- Timeline để đối chiếu thời điểm contention với latency spike.

Có thể kiểm tra file từ command line:

```sh
jfr summary lock-profile.jfr
```

In monitor enter events:

```sh
jfr print --events jdk.JavaMonitorEnter lock-profile.jfr
```

In thread park events:

```sh
jfr print --events jdk.ThreadPark lock-profile.jfr
```

In monitor wait events:

```sh
jfr print --events jdk.JavaMonitorWait lock-profile.jfr
```

Không nên in toàn bộ recording lớn ra terminal. Lọc theo event cần phân tích, rồi dùng JMC để nhóm theo thread, class, stack trace và duration.

Khi không thấy event mong đợi, kiểm tra `JFR.check ... verbose=true`, threshold, enabled setting và recording window. Không có event trong file không chứng minh rằng lock chưa từng bị tranh chấp; thời gian chờ có thể ngắn hơn threshold hoặc event đã bị tắt.

## 9. Dùng ThreadMXBean để đo contention của platform thread

`ThreadMXBean` thuộc `java.lang.management`. Nó cung cấp số lần và thời gian thread ở trạng thái bị block để vào monitor, cùng thông tin thread đang giữ hoặc chờ lock.

Lấy bean:

```java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();
```

Thread contention monitoring được tắt mặc định. Kiểm tra hỗ trợ và bật khi cần:

```java
if (bean.isThreadContentionMonitoringSupported()) {
    bean.setThreadContentionMonitoringEnabled(true);
}
```

Các method quan trọng trong `ThreadInfo`:

| Method | Ý nghĩa |
|---|---|
| `getBlockedCount()` | Tổng số lần thread bị `BLOCKED` để vào hoặc vào lại monitor |
| `getBlockedTime()` | Thời gian tích lũy gần đúng, tính bằng millisecond, ở trạng thái `BLOCKED` kể từ khi bật contention monitoring |
| `getWaitedCount()` | Số lần thread ở `WAITING` hoặc `TIMED_WAITING` |
| `getWaitedTime()` | Thời gian tích lũy gần đúng ở `WAITING`/`TIMED_WAITING` kể từ khi bật monitoring |
| `getLockOwnerName()` | Tên thread đang giữ object mà thread hiện tại chờ |
| `getStackTrace()` | Stack trace của thread |
| `getLockedMonitors()` | Các intrinsic monitor thread đang giữ |
| `getLockedSynchronizers()` | Các ownable synchronizer thread đang giữ |

`getBlockedTime()` chỉ đo thời gian thread ở trạng thái `BLOCKED` để lấy intrinsic monitor; nó không phải thời gian giữ lock. `getWaitedTime()` bao gồm trạng thái `WAITING` và `TIMED_WAITING`, nên không thể coi toàn bộ giá trị đó là thời gian chờ acquire lock.

Các giá trị thời gian là gần đúng. Khi bật lại contention monitoring, thống kê thời gian được reset. Chỉ bật khi cần đo và nhớ tắt sau phiên điều tra nếu không muốn duy trì overhead đo lường.

Trong JDK 21, `ThreadMXBean` giám sát platform threads; nó không cung cấp số liệu quản lý tương đương cho virtual threads. Với ứng dụng virtual-thread, kết hợp JFR và instrumentation ở cấp ứng dụng.

## 10. Ví dụ Java 17+: đo monitor contention và ReentrantLock

Ví dụ sau tạo hai tình huống:

1. Một thread giữ `synchronized` trong một khoảng thời gian, thread khác phải chờ monitor.
2. Một thread giữ `ReentrantLock`, thread khác phải park để chờ lock.

Chương trình bật ThreadMXBean contention monitoring, đợi đến khi waiter ở trạng thái `BLOCKED`, rồi đọc `blockedCount` và xác nhận `blockedTime` có sẵn.

Tạo file `LockMeasurementDemo.java`:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public class LockMeasurementDemo {
    private static void pause() {
        try {
            Thread.sleep(1_200);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    private static void measureMonitor(ThreadMXBean bean)
            throws InterruptedException {
        Object monitor = new Object();
        CountDownLatch entered = new CountDownLatch(1);

        Thread holder = new Thread(() -> {
            synchronized (monitor) {
                System.out.println("MONITOR_HOLDER_ENTERED");
                entered.countDown();
                pause();
                System.out.println("MONITOR_HOLDER_EXITING");
            }
        }, "monitor-holder");

        Thread waiter = new Thread(() -> {
            try {
                entered.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }

            synchronized (monitor) {
                System.out.println("MONITOR_WAITER_ACQUIRED");
            }
        }, "monitor-waiter");

        holder.start();
        waiter.start();

        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while (waiter.getState() != Thread.State.BLOCKED
                && System.nanoTime() < deadline) {
            Thread.sleep(1);
        }

        if (waiter.getState() != Thread.State.BLOCKED) {
            throw new IllegalStateException("Waiter did not block on monitor");
        }

        ThreadInfo info = bean.getThreadInfo(waiter.getId());
        if (info == null) {
            throw new IllegalStateException("Waiter ThreadInfo is unavailable");
        }

        System.out.println("MONITOR_BLOCKED_COUNT=" + info.getBlockedCount());
        System.out.println("MONITOR_BLOCKED_TIME_AVAILABLE="
                + (info.getBlockedTime() >= 0));

        holder.join();
        waiter.join();
    }

    private static void measureReentrantLock() throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        CountDownLatch entered = new CountDownLatch(1);

        Thread holder = new Thread(() -> {
            lock.lock();
            try {
                System.out.println("REENTRANT_HOLDER_ENTERED");
                entered.countDown();
                pause();
                System.out.println("REENTRANT_HOLDER_EXITING");
            } finally {
                lock.unlock();
            }
        }, "reentrant-holder");

        Thread waiter = new Thread(() -> {
            try {
                entered.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }

            lock.lock();
            try {
                System.out.println("REENTRANT_WAITER_ACQUIRED");
            } finally {
                lock.unlock();
            }
        }, "reentrant-waiter");

        holder.start();
        waiter.start();
        holder.join();
        waiter.join();
    }

    public static void main(String[] args) throws InterruptedException {
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        if (!bean.isThreadContentionMonitoringSupported()) {
            throw new UnsupportedOperationException(
                    "Thread contention monitoring is not supported");
        }

        bean.setThreadContentionMonitoringEnabled(true);
        measureMonitor(bean);
        measureReentrantLock();
        System.out.println("DONE");
    }
}
```

Biên dịch:

```sh
javac LockMeasurementDemo.java
```

Chạy:

```sh
java LockMeasurementDemo
```

Stdout trên HotSpot JDK có hỗ trợ contention monitoring:

```text
MONITOR_HOLDER_ENTERED
MONITOR_BLOCKED_COUNT=1
MONITOR_BLOCKED_TIME_AVAILABLE=true
MONITOR_HOLDER_EXITING
MONITOR_WAITER_ACQUIRED
REENTRANT_HOLDER_ENTERED
REENTRANT_HOLDER_EXITING
REENTRANT_WAITER_ACQUIRED
DONE
```

`MONITOR_BLOCKED_COUNT=1` cho biết waiter đã vào trạng thái `BLOCKED` một lần trong ví dụ. `MONITOR_BLOCKED_TIME_AVAILABLE=true` xác nhận thời gian blocked có thể đọc được; giá trị millisecond cụ thể thay đổi theo lịch chạy và thời điểm lấy snapshot.

Trong phần `ReentrantLock`, waiter thường park qua `LockSupport`. Vì vậy, số `blockedCount` của ThreadMXBean không phải thước đo đầy đủ cho thời gian chờ `ReentrantLock`; dùng JFR `jdk.ThreadPark` hoặc đo thời gian acquire ở cấp ứng dụng.

Ví dụ này tạo contention có chủ đích để học cách đo. Không dùng thời gian sleep trong critical section như một cách mô phỏng hiệu năng production; workload thực tế cần đại diện cho công việc mà ứng dụng đang thực hiện.

## 11. Đo wait time và hold time trong code

Nếu cần số liệu theo từng lock ở cấp ứng dụng, có thể đo bằng `System.nanoTime()`. Dùng đồng hồ monotonic để đo khoảng thời gian; không dùng `System.currentTimeMillis()` cho duration.

Ví dụ với `ReentrantLock`:

```java
long waitStarted = System.nanoTime();
lock.lock();
long acquiredAt = System.nanoTime();

long holdNanos;
try {
    updateSharedState();
} finally {
    holdNanos = System.nanoTime() - acquiredAt;
    lock.unlock();
}

long waitNanos = acquiredAt - waitStarted;
metrics.recordLockWait("account-cache", waitNanos);
metrics.recordLockHold("account-cache", holdNanos);
```

Trong ví dụ, metrics được ghi sau khi unlock để thao tác metrics không kéo dài critical section. Trong code production, bảo đảm hàm ghi metrics không làm mất exception gốc và nên dùng histogram để đo phân bố thay vì chỉ lưu trung bình.

Với `synchronized`, có thể ghi timestamp trước khi vào block và ngay sau khi vào thành công; ghi metric sau khi ra khỏi block để tránh kéo dài thời gian giữ monitor.

Đừng ghi log cho mọi lần acquire trong đường code nóng. Logging có thể tạo I/O, lock riêng và allocation, làm thay đổi chính contention mà bạn đang đo. Ưu tiên histogram/counter có overhead thấp, sampling hoặc JFR.

## 12. Đo lock queue và trạng thái ReentrantLock

`ReentrantLock` cung cấp một số method quan sát:

| Method | Ý nghĩa |
|---|---|
| `isLocked()` | Có thread đang giữ lock hay không |
| `isHeldByCurrentThread()` | Thread hiện tại có giữ lock không |
| `hasQueuedThreads()` | Có thread đang chờ lock không |
| `getQueueLength()` | Ước lượng số thread đang chờ |
| `isFair()` | Lock có dùng chính sách fairness không |

`getQueueLength()` là ước lượng, không phải số liệu chính xác tại mọi thời điểm. Các method quan sát queue phù hợp cho diagnostics, không nên dùng làm điều kiện synchronization hoặc business logic.

Fair `ReentrantLock` cố gắng cấp quyền theo thứ tự chờ, nhưng có thể giảm throughput. Non-fair lock thường có throughput tốt hơn trong một số workload nhưng có thể khiến thread chờ lâu hơn. Hãy benchmark và kiểm tra tail latency trước khi thay đổi fairness.

## 13. Benchmark lock bằng JMH

JFR và thread dump dùng để điều tra ứng dụng đang chạy. Khi muốn so sánh hai cách triển khai lock trong workload có kiểm soát, dùng Java Microbenchmark Harness (JMH).

JMH hỗ trợ warm-up, measurement iterations, fork và group threads. Ví dụ dưới đây so sánh intrinsic monitor với `ReentrantLock` trong một benchmark project đã cấu hình JMH:

```java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Group;
import org.openjdk.jmh.annotations.GroupThreads;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;
import org.openjdk.jmh.annotations.Mode;

@BenchmarkMode(Mode.SampleTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 8)
@Fork(2)
public class LockBench {
    @State(Scope.Group)
    public static class MonitorState {
        long value;
    }

    @State(Scope.Group)
    public static class ReentrantState {
        final ReentrantLock lock = new ReentrantLock();
        long value;
    }

    @Benchmark
    @Group("monitor")
    @GroupThreads(4)
    public void monitor(MonitorState state) {
        synchronized (state) {
            state.value++;
        }
    }

    @Benchmark
    @Group("reentrant")
    @GroupThreads(4)
    public void reentrant(ReentrantState state) {
        state.lock.lock();
        try {
            state.value++;
        } finally {
            state.lock.unlock();
        }
    }
}
```

Chạy benchmark từ project JMH đã cấu hình:

```sh
mvn clean package
```

```sh
java -jar target/benchmarks.jar '.*LockBench.*'
```

`Mode.SampleTime` giúp xem phân bố latency của từng operation; output JMH có thể cung cấp các percentile. `@State(Scope.Group)` chia sẻ state giữa các thread trong cùng group, còn `@GroupThreads(4)` tạo bốn thread cạnh tranh trên state đó.

Benchmark trên chỉ là workload nhỏ để minh họa. Khi benchmark thực tế, hãy đưa cùng một critical-section workload vào hai implementation, dùng dữ liệu đại diện, giữ số thread và môi trường giống nhau, chạy đủ warm-up/fork và kiểm tra cả throughput lẫn p95/p99. Không đưa log hoặc I/O vào critical section trừ khi đó chính là workload cần mô phỏng.

Không chọn `ReentrantLock` chỉ vì một benchmark micro nhỏ nhanh hơn `synchronized`. Khác biệt có thể thay đổi theo JVM, CPU, critical section, số thread, fairness và cách ứng dụng dùng lock.

## 14. Nhận diện các mẫu contention thường gặp

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Một lock có nhiều waiter | Nhiều thread cùng truy cập một tài nguyên dùng chung | Chia nhỏ lock hoặc partition dữ liệu |
| Hold time dài | Critical section chứa tính toán/I/O hoặc xử lý không cần khóa | Di chuyển việc không cần bảo vệ ra ngoài lock |
| Wait time p99 cao nhưng trung bình thấp | Một số request gặp queue dài hoặc owner giữ lock lâu bất thường | Xem percentile, owner thread và event timeline |
| Nhiều thread chờ lock của một cache | Cache có điểm ghi/cập nhật tuần tự | Dùng cache concurrent, immutable snapshot hoặc sharding |
| Lock được giữ khi gọi network/database | I/O chậm kéo dài thời gian giữ khóa | Lấy dữ liệu ngoài lock, kiểm tra lại state rồi cập nhật ngắn |
| Nhiều lock lồng nhau | Thứ tự acquire không thống nhất hoặc critical section phức tạp | Chuẩn hóa thứ tự lock, giảm nesting |
| ReentrantLock park nhiều | Nhiều thread chờ synchronizer hoặc Condition | Xem `jdk.ThreadPark`, queue và logic signal |
| CPU thấp nhưng latency cao | Thread chủ yếu chờ lock/I/O | Đo wait time, thread state và owner |
| CPU cao cùng contention | Lock convoy, retry, spin hoặc critical section nặng | Đối chiếu JFR, CPU profile và lock timeline |

Các dấu hiệu trên chỉ tạo giả thuyết. Kiểm tra event và stack trace để tìm đường code thực tế trước khi thay đổi kiến trúc.

## 15. Phân biệt contention với deadlock

Contention nghĩa là thread phải chờ lock, nhưng lock cuối cùng vẫn được nhả. Deadlock là chu trình chờ không thể tự tiến triển.

Có thể kiểm tra deadlock qua `ThreadMXBean`:

```java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();

long[] deadlocked = bean.findDeadlockedThreads();
if (deadlocked == null) {
    System.out.println("NO_DEADLOCK");
} else {
    System.out.println("DEADLOCK_THREADS=" + deadlocked.length);
}
```

`findDeadlockedThreads()` tìm chu trình chờ trên object monitors và ownable synchronizers mà JVM hỗ trợ. API này được thiết kế cho troubleshooting, không dùng làm cơ chế điều phối synchronization; thao tác có thể tốn kém và chỉ xét platform threads.

`findMonitorDeadlockedThreads()` chỉ tìm deadlock liên quan object monitors. Nếu cần xét cả `ReentrantLock`/ownable synchronizer, dùng `findDeadlockedThreads()`.

Không chạy deadlock detection liên tục ở tần suất cao. Dùng khi có dấu hiệu treo hoặc khi thu thập incident diagnostics.

## 16. Virtual threads và lock contention

Virtual threads thay đổi cách JVM lập lịch thread, nhưng không loại bỏ vấn đề lock contention. Nhiều virtual threads vẫn có thể tranh chấp cùng một monitor hoặc synchronizer.

Một số điểm cần nhớ:

- `ThreadMXBean` trong JDK 21 chỉ giám sát platform threads, không quản lý virtual threads.
- Thread dump và JFR có thể cung cấp góc nhìn khác về thread/park events; kiểm tra công cụ và JDK version cụ thể.
- `synchronized` có thể tạo tình huống pinning trong một số đường chạy virtual thread và native/monitor interaction; JFR có event `jdk.VirtualThreadPinned` để điều tra pinning trên JDK hỗ trợ virtual threads.
- Lock contention và carrier-thread pinning là hai vấn đề khác nhau; không gộp chúng thành một chỉ số.

Khi dùng virtual threads, đo latency ở cấp operation và JFR events. Kiểm tra cả lock wait lẫn pinning nếu throughput giảm bất thường.

## 17. Giảm contention sau khi đo

Sau khi xác định đúng lock và code path, cân nhắc các hướng sau:

- Rút ngắn critical section: chỉ giữ lock quanh phần đọc/ghi state thực sự cần bảo vệ.
- Tránh I/O, logging, gọi network hoặc callback bên ngoài khi đang giữ lock.
- Chia dữ liệu thành nhiều partition để giảm số thread dùng chung một lock.
- Dùng concurrent collections khi semantics phù hợp.
- Dùng immutable snapshot hoặc copy-on-write khi workload đọc nhiều, ghi ít.
- Giảm tần suất cập nhật shared state bằng batching hoặc aggregation.
- Dùng `ReadWriteLock` khi workload đọc/ghi và đặc tính fairness phù hợp; benchmark trước khi đổi.
- Dùng `tryLock`/timeout khi cần tránh chờ vô hạn và có cách xử lý timeout đúng.
- Chuẩn hóa thứ tự lấy nhiều lock để tránh deadlock.
- Đánh giá fairness dựa trên tail latency và starvation, không chỉ throughput.

Không loại bỏ lock nếu dữ liệu vẫn cần bảo vệ. Thay đổi synchronization phải giữ đúng atomicity, visibility và invariants của ứng dụng.

## 18. Overhead và giới hạn của công cụ

Mỗi công cụ đo một góc khác nhau:

| Công cụ | Đo tốt | Giới hạn |
|---|---|---|
| Thread dump | Thread state, stack, monitor owner và lock đang chờ | Snapshot tức thời, không cung cấp phân bố latency |
| JFR | Duration event, thread, stack trace và timeline | Phụ thuộc event settings/threshold; cấu hình chi tiết tạo nhiều dữ liệu hơn |
| ThreadMXBean | Blocked count/time và thread synchronization info | Contention monitoring tắt mặc định; `blockedTime` tập trung vào intrinsic monitor |
| JConsole/JMX | Quan sát Threading MXBean và runtime metrics | Không tự cung cấp histogram wait/hold cho từng lock ứng dụng |
| JMH | So sánh throughput/latency dưới workload kiểm soát | Không đại diện đầy đủ cho production nếu workload không giống thực tế |
| Application instrumentation | Wait/hold time theo lock hoặc operation cụ thể | Đo sai vị trí hoặc ghi metrics trong critical section có thể làm lệch kết quả |

Đo lường cũng có chi phí. Thread dump lớn, JFR profile recording, stack trace và instrumentation quá chi tiết đều có thể làm tăng overhead. Bắt đầu với thời lượng ngắn và event cần thiết; mở rộng khi đã biết câu hỏi cần trả lời.

## 19. Lỗi thường gặp khi đo lock

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không thấy thread `BLOCKED` nhưng latency cao | Ứng dụng dùng `ReentrantLock`, `Condition` hoặc cơ chế park | Kiểm tra `WAITING`/`TIMED_WAITING`, `ThreadPark` và JFR |
| `blockedTime` trả `-1` | Thread contention monitoring chưa bật | Kiểm tra hỗ trợ và gọi `setThreadContentionMonitoringEnabled(true)` |
| `blockedTime` bằng 0 | Snapshot quá sớm, wait quá ngắn hoặc chưa vào `BLOCKED` | Lấy mẫu lại và dùng JFR threshold phù hợp |
| Không có JFR `JavaMonitorEnter` | Event tắt, threshold cao hoặc không có monitor contention | Kiểm tra `JFR.check verbose=true` và event settings |
| Không có `ThreadPark` | Wait ngắn hơn threshold hoặc event chưa được bật | Kiểm tra event threshold và stack trace setting |
| `getWaitedTime()` rất lớn | Thread chờ notification, park hoặc timeout | Không coi toàn bộ là lock-acquisition time; xem blocker và stack |
| Queue length dao động mạnh | Đây là ước lượng tại thời điểm gọi | Dùng nhiều mẫu và JFR timeline, không dùng làm điều kiện đồng bộ |
| Benchmark cho kết quả khác production | Workload, số thread, CPU, JVM hoặc critical section khác | Tái tạo workload gần thực tế và so sánh bằng JFR |
| Fair lock có throughput thấp hơn | Fairness có thể giảm barging và thay đổi scheduling | So sánh throughput cùng p95/p99 và starvation |
| JFR file không có stack trace | Event setting không bật stackTrace hoặc recording dùng cấu hình khác | Bật stack trace cho event cần đo và ghi lại lần nữa |

## 20. Runbook đo lock trong một incident

1. Ghi lại thời điểm và request/operation có latency tăng.
2. Xác định PID bằng `jcmd -l`.
3. Lấy `jcmd PID Thread.print -l` vài lần cách nhau vài giây.
4. Tìm waiter threads, lock owner và stack frame lặp lại.
5. Bắt đầu JFR recording ngắn với `jdk.JavaMonitorEnter` và `jdk.ThreadPark`.
6. Dump file `.jfr` và mở bằng JMC.
7. Nhóm event theo duration, thread, stack trace và monitor/blocker.
8. Đo thêm wait/hold time ở cấp ứng dụng nếu cần phân biệt acquire wait với critical-section duration.
9. Xác định code path giữ lock và lý do lock phải được giữ.
10. Thử một thay đổi nhỏ trong staging hoặc workload kiểm soát.
11. Đo lại cùng số thread, workload và JVM settings.
12. So sánh throughput, p95/p99, wait time, hold time và CPU.
13. Ghi lại kết quả, JDK version, event threshold và command đã dùng.

## 21. Checklist

- [ ] Đã xác định lock là intrinsic monitor hay explicit synchronizer.
- [ ] Đã phân biệt `BLOCKED` với `WAITING`/`TIMED_WAITING`.
- [ ] Đã đo wait time và hold time riêng biệt.
- [ ] Đã lấy nhiều thread dump để xác định owner/waiter.
- [ ] Đã dùng `jcmd Thread.print -l` khi cần thông tin lock.
- [ ] Đã kiểm tra `jdk.JavaMonitorEnter`, `jdk.JavaMonitorWait` và `jdk.ThreadPark`.
- [ ] Đã xác nhận threshold và stack trace settings của JFR.
- [ ] Đã biết ThreadMXBean contention monitoring tắt mặc định.
- [ ] Đã hiểu `getBlockedTime()` không phải thời gian giữ lock và không đại diện cho mọi `ReentrantLock` wait.
- [ ] Đã dùng JMH khi cần benchmark lock có kiểm soát.
- [ ] Đã so sánh throughput cùng p95/p99 và workload tương đương.
- [ ] Đã đánh giá overhead của thread dump, JFR và instrumentation.
- [ ] Đã kiểm tra deadlock riêng với contention thông thường.
- [ ] Đã giữ nguyên correctness và memory visibility sau khi tối ưu.

## 22. Tài liệu tham khảo

- Oracle JDK 21 Tool Reference — The jcmd Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Java SE 21 API — ThreadMXBean: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html
- Java SE 21 API — ThreadInfo: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadInfo.html
- Java SE 21 API — jdk.jfr package and event settings: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html
- OpenJDK JFR default.jfc event configuration: https://github.com/openjdk/jdk/blob/master/src/jdk.jfr/share/conf/jfr/default.jfc
- OpenJDK JMH project: https://github.com/openjdk/jmh

Đo lock contention hiệu quả cần kết hợp snapshot và số liệu theo thời gian. Thread dump giúp tìm thread đang chờ và owner; JFR đo duration và stack trace của monitor/park events; ThreadMXBean cung cấp blocked count/time cho platform threads; JMH giúp so sánh lock trong workload có kiểm soát. Sau khi tìm đúng critical section, hãy đo lại cùng workload để xác nhận cả throughput và tail latency đã cải thiện.