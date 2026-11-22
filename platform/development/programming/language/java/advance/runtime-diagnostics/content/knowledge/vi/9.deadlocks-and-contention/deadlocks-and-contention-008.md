# 9.8 — Kết hợp thread dump với JFR JavaMonitorEnter, JavaMonitorWait và ThreadPark

## 1. Tại sao cần cả thread dump lẫn JFR?

Khi Java application bị treo, độ trễ tăng hoặc thông lượng giảm, **thread dump** cho thấy trạng thái các Java thread **tại thời điểm chụp**: thread nào `BLOCKED`, `WAITING`, `TIMED_WAITING`; stack của nó nằm ở đâu; đang `waiting to lock` monitor nào; và thread nào `locked` monitor đó. Dữ liệu này rất tốt để tìm quan hệ chờ khóa, nhưng một dump đơn lẻ không tự đo được thời gian chờ trong nhiều phút trước đó.

**Java Flight Recorder (JFR)** bổ sung **dòng thời gian** gồm các events có `startTime`, `duration`, `eventThread`, `stackTrace` và các trường riêng cho từng kiểu chờ. Trên Java 17, ba event cốt lõi cho chủ đề treo và tranh chấp là:

- `jdk.JavaMonitorEnter`: thread **bị chặn khi cố vào một Java object monitor** qua `synchronized`.
- `jdk.JavaMonitorWait`: thread đã gọi `Object.wait(...)` và **đang chờ notification, timeout hoặc sự kiện đánh thức khác**; `wait` nhả monitor của object mà thread đang wait.
- `jdk.ThreadPark`: thread bị park qua `LockSupport.park`/`parkNanos`/`parkUntil`; có thể liên quan AQS/`ReentrantLock`, condition, `Future` hoặc thread pool đang rỗi.

**Một cách nhớ:** thread dump trả lời **“ngay bây giờ ai đợi ai?”**, còn JFR trả lời **“đoạn chờ nào đã xảy ra, kéo dài bao lâu, từ call path nào?”**. Hai nguồn hỗ trợ nhau nhưng không thay thế nhau.

Sau bài học, người học có thể:

1. Phân biệt chính xác ba loại chờ Java và ba event JFR tương ứng.
2. Thu thread dump bằng `jcmd Thread.print -l` cùng JFR recording trên đúng JVM.
3. Dùng thread identity, timestamp, stack, monitor information và duration để đối chiếu.
4. Hiểu khi nào event chưa được ghi do **chưa hoàn tất**, threshold hoặc thiếu recording.
5. Không nhầm contention, notification wait hoặc idle park với deadlock.
6. Chạy ví dụ Java 17 có thể biên dịch/chạy, tạo cả ba events và đọc file `.jfr` thật.

## 2. Hai loại bằng chứng có phạm vi khác nhau

| Thuộc tính | Thread dump | JFR |
| --- | --- | --- |
| Thời điểm | Snapshot tại lúc gọi command | Events trong khoảng recording |
| Trạng thái | `BLOCKED`, `WAITING`, `TIMED_WAITING`, `RUNNABLE` | Event của một loại chờ/contended acquisition cụ thể |
| Stack | Frames tại thời điểm chụp | `stackTrace` của event khi được bật |
| Chủ sở hữu khóa | `locked`, `waiting to lock`, ownable synchronizers, owner metadata | `previousOwner` chỉ có ở `JavaMonitorEnter`; không phải live owner graph đầy đủ |
| Thời lượng | Không chứng minh tổng thời gian chờ quá khứ từ một snapshot | `duration` cho event đã ghi |
| Khả năng tìm deadlock | Có thể dựng waiter → owner graph và thấy deadlock summary | Event dài **không** tự chứng minh có chu trình |
| Điều kiện thiếu dữ liệu | Thread biến mất/đổi state giữa các lần chụp | Event disabled, dưới threshold, nằm ngoài window hoặc chưa được commit |

Một thread ở `BLOCKED` khi dump được chụp có thể **chưa** có completed `JavaMonitorEnter` event trong file JFR: phần chờ vào monitor chưa kết thúc nên event chưa hoàn tất để được ghi. Đây là giới hạn quan trọng nhất khi kết hợp **snapshot trạng thái hiện tại** với **events theo duration**.

## 3. JavaMonitorEnter — tranh chấp khi vào monitor

Khi một thread gọi `synchronized(lock)` hoặc synchronized method mà monitor đã bị thread khác giữ, thread có thể chuyển sang `BLOCKED`. `jdk.JavaMonitorEnter` phản ánh **monitor contention**, **không phải mọi lần vào `synchronized` không tranh chấp**.

Các trường phổ biến của event trên OpenJDK/HotSpot Java 17:

| Field | Ý nghĩa | Cách đọc |
| --- | --- | --- |
| `startTime` | Bắt đầu giai đoạn contended monitor-enter | Đối chiếu thời điểm snapshot |
| `duration` | Thời lượng blocked để vào monitor | Không phải CPU time hay tổng thời gian trong synchronized block |
| `eventThread` | Thread **đang chờ vào monitor** | Là waiter, không phải owner |
| `monitorClass` | Class của monitor object | Nhiều object cùng class, không đủ để định danh một lock |
| `address` | Thông tin địa chỉ monitor theo runtime | Không mặc định bằng token trong mọi thread dump |
| `previousOwner` | Previous monitor owner theo thông tin event | Không khẳng định là owner tại một timestamp dump bất kỳ |
| `stackTrace` | Đường gọi gây contention | Có thể bị tắt, cắt ngắn hoặc phụ thuộc implementation |

Một event minh họa:

```text
jdk.JavaMonitorEnter {
  startTime = 16:32:10.545
  duration = 1.90 s
  monitorClass = java.lang.Object
  previousOwner = "lab-owner"
  eventThread = "lab-contender"
  stackTrace = [
    JfrLockTriadDemo.lambda$main$1(...)
    java.lang.Thread.run()
  ]
}
```

Đây là dạng rút gọn từ một lần thử thật; timestamp, thread IDs, addresses, source line và duration thay đổi giữa các JVM. `lab-contender` đã phải chờ trong khi `lab-owner` giữ monitor; event hoàn tất sau khi contender giành được lock.

### 3.1. Không coi previousOwner là live lock owner

`previousOwner` có nghĩa **chủ sở hữu trước đó** theo metadata JFR. Monitor có thể được nhả, chuyển owner hoặc thay đổi tình trạng giữa lúc event bắt đầu/kết thúc. Nếu mục tiêu là xác định **thread nào đang giữ monitor tại đúng thời điểm dump**, phải dùng dòng `- locked <L>` và `- waiting to lock <L>` trong **cùng một dump**, hoặc API `ThreadMXBean.getLockOwnerId()`.

Một `JavaMonitorEnter` event có duration lớn có nghĩa thread **đã bị tranh chấp** và event được ghi, không tự chứng minh có deadlock. Deadlock monitor thực không được giải quyết còn có thể khiến event contended enter **chưa kết thúc**, do đó JFR chưa ghi nó.

## 4. JavaMonitorWait — Object.wait và notification

`Object.wait` chỉ gọi được khi thread đang giữ monitor của object. Trong lúc chờ notification/timeout, thread **nhả monitor của chính object được wait**, rồi phải giành lại monitor trước khi tiếp tục. Vì vậy một thread `WAITING/TIMED_WAITING (on object monitor)` với `waiting on <L>` không tương đương với thread `BLOCKED` đang `waiting to lock <L>`.

Các trường chính:

| Field | Ý nghĩa | Không được hiểu sai |
| --- | --- | --- |
| `eventThread` | Thread gọi `Object.wait` | Không phải notifier |
| `monitorClass`, `address` | Monitor object được wait | Không tự chỉ ra ai đang giữ một lock khác |
| `duration` | Thời gian wait event được ghi | Không phải khoảng monitor bị giữ độc quyền |
| `timeout` | Thời gian chờ tối đa **được yêu cầu** | Không phải duration thực tế |
| `timedOut` | JVM báo wait có hết hạn không | `false` không luôn chứng minh một notifier cụ thể |
| `notifier` | Thread thực hiện notification nếu được ghi nhận | Có thể null/không có ở các tình huống khác |
| `stackTrace` | Call path đi tới `Object.wait` | Có thể có `Object.wait` và ứng dụng ở các frame sâu |

Ví dụ:

```text
jdk.JavaMonitorWait {
  duration = 901 ms
  monitorClass = java.lang.Object
  notifier = "lab-notifier"
  timeout = 1.70 s
  timedOut = false
  eventThread = "lab-waiter"
}
```

Ở đây `lab-waiter` được báo thức trước timeout. Thời lượng ~900 ms không có nghĩa một thread khác **giữ monitor này suốt 900 ms**. Phần lớn thời gian `Object.wait` đã nhả monitor. Việc được đánh thức còn có thể chịu ảnh hưởng interruption, spurious wakeup, scheduler và việc lấy lại monitor.

**Quy tắc dựng wait-for graph:** Không tự thêm cạnh waiter → owner từ dòng `- waiting on <L>`. Đó là *chờ notification*, không mặc nhiên là *chờ vào monitor do owner giữ*. Muốn tìm nguyên nhân wait kéo dài, kiểm tra code phát `notify`/`notifyAll`, logic condition, producer và đường thực thi sau signal.

## 5. ThreadPark — chờ qua LockSupport/AQS

`LockSupport` cung cấp `park`, `parkNanos` và `parkUntil`. Nhiều lớp `java.util.concurrent` dùng primitive này: `ReentrantLock`, `Condition`, `Future`, `BlockingQueue`, `ThreadPoolExecutor`. Vì thế `jdk.ThreadPark` có thể biểu thị **tranh chấp khóa** hoặc **pool đang rỗi**, tùy stack và ngữ cảnh.

| Field | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `eventThread` | Thread bị park | Chưa chắc là thread blocked vì ReentrantLock |
| `duration` | Thời gian park được ghi | Có thể kết thúc do unpark/timeout/interruption |
| `parkedClass` | Class của blocker object | Blocker không tự cung cấp owner |
| `address` | Địa chỉ liên quan blocker object | Không phải monitor-owner mapping phổ quát |
| `timeout` | Timeout của park nếu có | Có thể là `N/A` |
| `until` | Deadline với park-until nếu có | Có thể là `N/A` |
| `stackTrace` | Nơi xảy ra park | Cần đọc đủ frames AQS/pool để xác định mục đích |

Ví dụ:

```text
jdk.ThreadPark {
  duration = 1.30 s
  parkedClass = java.lang.String
  timeout = 1.30 s
  until = N/A
  eventThread = "lab-parker"
  stackTrace = [
    jdk.internal.misc.Unsafe.park(...)
    java.util.concurrent.locks.LockSupport.parkNanos(...)
    JfrLockTriadDemo.lambda$main$4(...)
  ]
}
```

Trong demo, `parkedClass=java.lang.String` vì chương trình dùng `"lab-park-blocker"` làm **blocker object** cho `LockSupport.parkNanos`. **String này không phải một lock đang bị thread khác sở hữu.** Do đó không suy ra `parkedClass` hoặc `address` là owner of monitor.

### 5.1. Park dài chưa chắc là treo

Thread ở `ThreadPoolExecutor.getTask` hoặc `BlockingQueue.take` có thể park rất lâu khi không có task. Nếu queue rỗng và throughput đúng kỳ vọng, đó là trạng thái idle hợp lệ. Ngược lại, nếu backlog tăng mà worker vẫn park, cần kiểm tra producer, signaling, task lifecycle hoặc pool shutdown. `ThreadPark` chỉ là điểm bắt đầu điều tra.

## 6. Bảng quy chiếu thread dump → JFR

| Dấu hiệu trong dump | Event tương ứng thường gặp | Bằng chứng hiện có | Cần kiểm tra thêm |
| --- | --- | --- | --- |
| `BLOCKED (on object monitor)` và `waiting to lock <L>` | `JavaMonitorEnter` | Đang cố enter Java monitor | Owner tại snapshot, lock identity, duration sau khi hoàn tất |
| `WAITING/TIMED_WAITING (on object monitor)` và `waiting on <L>` | `JavaMonitorWait` | Chờ `Object.wait` | Notifier, timeout, signal path |
| `WAITING/TIMED_WAITING (parking)` và `Unsafe.park` | `ThreadPark` | Park | AQS/condition/queue/idle, owner nếu có |
| `RUNNABLE` đang `locked <L>` | Có thể không có event cho owner | Đang giữ monitor | Code trong critical section, CPU/I/O |
| Không thấy thread `BLOCKED` ở ảnh chụp | Có thể có `JavaMonitorEnter` trước/sau dump | Contention có thể đã kết thúc | JFR timeline, frequency/threshold |
| Thread `BLOCKED` mãi nhưng không thấy completed event | Event chưa hoàn tất hoặc event disabled | Snapshot vẫn là bằng chứng block | Deadlock graph, JFR settings, next dumps |

**Không có tương quan bắt buộc một–một**. Trạng thái thread có thể thay đổi nhanh hơn tốc độ người vận hành chụp dump; JFR chỉ lưu events **đã ghi** trong recording window và vượt threshold đang áp dụng.

## 7. Kết hợp theo đúng JVM, thread ID và thời gian

Một bộ chứng cứ nên ghi đủ:

```text
host/pod: app-node-02 / orders-3
pid_namespace: container-app
pid: 18432
jvm_start_utc: 2026-10-29T08:15:00Z
jdk_version: 17.x
dump_capture_utc: 2026-10-29T08:21:04Z
jfr_start_utc: 2026-10-29T08:20:00Z
jfr_end_utc: 2026-10-29T08:22:00Z
incident: increased request latency
```

Đây là metadata **minh họa**, không phải output thực. PID có thể được tái sử dụng; phải dùng host, PID namespace và process start time để tránh ghép dump của phiên cũ với file JFR của JVM mới.

### 7.1. Phân biệt Java thread ID, native ID và tên thread

JFR `eventThread` có thể in `javaThreadId` và thread name. Thread dump HotSpot có tên thread, `#...`, `tid=...`, `nid=...`. `nid` thường là **native OS thread ID**, còn `tid` là định danh implementation, **không tự bằng `javaThreadId`**.

Ưu tiên ghép theo **Java thread ID trong cùng JVM instance**, dùng thread name và stack trace để đối chiếu. Tên như `worker-1` có thể trùng hoặc được tái sử dụng khi thread chết/tạo lại. Nếu không chắc loại ID nào được in, không ép phép join chỉ theo chuỗi tên.

### 7.2. Khoảng thời gian sự kiện có phủ mốc dump không?

Về mặt phân tích, một duration event thường có khoảng `[startTime, startTime + duration]`. Nếu `dump_capture_utc` rơi vào khoảng này **và** đúng eventThread/call path, nhiều khả năng đó là cùng đoạn chờ được thấy ở dump. Nhưng phải quy đổi timezone chính xác; `jfr print` có thể in giờ theo timezone tool đang chạy, trong khi hệ thống log dùng UTC.

Một `JavaMonitorEnter` chưa kết thúc tại thời điểm dump có thể xuất hiện **sau đó** khi recording được trích xuất sau lúc contention được giải phóng. Tránh suy luận thứ tự chỉ từ thời điểm file được lưu.

### 7.3. Vì sao không join bằng địa chỉ object một cách máy móc?

Thread dump có token `<0x...>`, còn JFR event có `address`. Cách biểu diễn địa chỉ monitor, đời sống object, GC, monitor inflation và khả năng tái sử dụng identity có thể khác giữa runtime. **Không có hợp đồng phổ quát rằng hai chuỗi hex luôn bằng nhau** hoặc ổn định giữa các snapshots.

Để ghép đáng tin hơn, dùng **JVM instance + thread ID + timestamp + stack + monitorClass** và dùng owner/lock identity chỉ khi được chứng minh trong cùng dump hoặc theo semantics runtime đã xác minh.

## 8. Quy trình chụp thread dump và recording JFR trên Java 17

### 8.1. Xác định đúng JVM

```bash
jcmd -l
jcmd <PID> VM.version
jcmd <PID> help Thread.print
jcmd <PID> help JFR.start
jcmd <PID> help JFR.dump
```

Thay `<PID>` bằng PID thật, không gõ dấu góc. `jcmd` cần quyền và môi trường attach thích hợp trên host/PID namespace của JVM đích; trong container, PID host và PID trong pod có thể khác nhau. Không dùng `jcmd 0` cho một JVM vì nó có thể gửi command tới nhiều JVM.

### 8.2. Bật JFR trước cửa sổ nghi vấn

```bash
jcmd <PID> JFR.start name=LockDiag settings=profile
jcmd <PID> JFR.check name=LockDiag verbose=true
```

`settings=profile` sử dụng một recording template của JDK. **Phải kiểm tra cấu hình thực tế**: ba events có được bật không, `threshold` bao nhiêu và có ghi `stackTrace` không. Các file `default.jfc` và `profile.jfc` của Java 17 thường lọc chờ rất ngắn bằng threshold ở mức hàng chục mili giây. Custom .jfc hoặc runtime/vendor khác có thể thay đổi.

Nếu JVM đã có recording phù hợp, không nhất thiết tạo thêm một recording mới. `JFR.check` giúp kiểm tra recording hiện có và, với `verbose=true`, settings của events.

### 8.3. Khi sự cố đang diễn ra: chụp dump

```bash
date -u +%Y-%m-%dT%H:%M:%SZ
jcmd <PID> Thread.print -l > dump-1.txt
```

Ví dụ cho **bash Linux**. `date -u` ghi timestamp UTC; redirect `>` tạo file trên máy shell thực thi `jcmd`. Nếu ứng dụng tiếp tục treo, lấy thêm 1–2 dumps có timestamp, cách nhau một khoảng hợp lý. Không dump quá dày khi JVM có nhiều thread hoặc đang kiệt tài nguyên.

`-l` giúp nhìn monitor và ownable synchronizers khi runtime hỗ trợ. Chụp dump mang chi phí phụ thuộc số thread và trạng thái JVM; đọc `help Thread.print`/impact trước khi thực hiện trên production.

### 8.4. Xuất recording và đọc events

```bash
jcmd <PID> JFR.dump name=LockDiag filename=/var/tmp/lockdiag.jfr
jcmd <PID> JFR.stop name=LockDiag
jfr summary /var/tmp/lockdiag.jfr
jfr print --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.ThreadPark --stack-depth 12 /var/tmp/lockdiag.jfr
```

`JFR.dump` ghi file theo filesystem của **JVM đích**, không nhất thiết cùng thư mục với shell client; trong container, đường dẫn thuộc container filesystem. `JFR.dump` không tự dừng recording; chỉ dùng `JFR.stop` nếu đã hoàn tất thu và quy trình cho phép. `jfr summary` giúp xem event counts/types, `jfr print` lọc events và in stack frames. Có thể mở file bằng **JDK Mission Control** để xem timeline.

Nếu file JFR được lấy quá sớm khi một thread vẫn `BLOCKED`, event liên quan có thể **chưa được commit**. Không xem một bản dump JFR tại thời điểm đang block như bản ghi bắt buộc chứa event chưa hoàn tất.

## 9. Phương pháp đối chiếu một tình huống thực tế

Giả sử một incident có:

- `request-17` ở `BLOCKED` chờ monitor `L` trong `Cache.get`.
- `cache-refresher` đang `locked <L>` ở code cập nhật cache.
- `pool-worker-4` ở `LockSupport.park` trong `ThreadPoolExecutor.getTask`.

Thread dump có đồ thị:

```text
request-17 --waiting for monitor L--> cache-refresher
pool-worker-4 --parking for task--> owner not proven
```

Sau khi sự cố kết thúc, JFR chứa các sự kiện minh họa:

```text
16:21:11.800 → 16:21:13.100
  JavaMonitorEnter, eventThread=request-17, duration≈1.30s
  monitorClass=CacheLock, previousOwner=cache-refresher

16:21:10.000 → 16:21:20.000
  ThreadPark, eventThread=pool-worker-4
  stack=BlockingQueue.take()/ThreadPoolExecutor.getTask()
```

Đây là **dữ liệu tình huống giả định**, không phải output chuẩn. Cách kết luận:

1. Dump chứng minh `request-17` đang đợi monitor `L` và owner tại thời điểm đó là `cache-refresher`.
2. `JavaMonitorEnter` bổ sung duration và call path, chứng minh request đã trải qua khoảng chờ dài.
3. `previousOwner` trong ví dụ khớp owner, nhưng **owner tại snapshot phải được kiểm chứng từ dump**, không suy từ event.
4. `pool-worker-4` có park dài ở code idle queue; chưa có bằng chứng nó là nguyên nhân latency.
5. Cần xét cùng window của request metrics, CPU/GC/I/O, queue depth và application logs trước khi chọn root cause.

**Kết quả cần bàn giao:** thread/call path bị ảnh hưởng, monitor hoặc điều kiện chờ, owner có bằng chứng, duration/frequency trong JFR, mức độ chắc chắn khi ghép hai nguồn và thay đổi code cụ thể.

## 10. Java 17+ demo: tạo đủ ba sự kiện trong cùng recording

Chương trình `JfrLockTriadDemo.java` chạy ba đường chờ **đồng thời**:

1. `lab-owner` giữ `ENTER_LOCK` khoảng 1,9 giây; `lab-contender` chờ vào `synchronized(ENTER_LOCK)`.
2. `lab-waiter` gọi `WAIT_LOCK.wait(1700)`; `lab-notifier` gọi `notifyAll()` sau khoảng 900 ms.
3. `lab-parker` gọi `LockSupport.parkNanos` với blocker là một `String` khoảng 1,3 giây.

Programmatic `Recording` bật ba events và `stackTrace`, đặt `threshold=0` cho **demo cục bộ**, sau đó ghi `triad-demo.jfr`. `RecordingFile` đọc file và chỉ xác minh events thuộc **đúng tên thread**; JFR runtime có thể còn ghi events nội bộ hoặc từ `Thread.join` của main thread.

### 10.1. File `JfrLockTriadDemo.java` hoàn chỉnh

```java
import java.nio.file.Path;
import java.time.Duration;
import java.util.Set;
import java.util.HashSet;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.LockSupport;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordingFile;
import jdk.jfr.consumer.RecordedEvent;

public class JfrLockTriadDemo {
    static final Object ENTER_LOCK = new Object();
    static final Object WAIT_LOCK = new Object();

    static void nap(long ms) {
        try {
            Thread.sleep(ms);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    static void await(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    public static void main(String[] args) throws Exception {
        Path file = Path.of(args.length == 0 ? "triad-demo.jfr" : args[0]);

        try (Recording r = new Recording()) {
            r.enable("jdk.JavaMonitorEnter")
             .withThreshold(Duration.ZERO).withStackTrace();
            r.enable("jdk.JavaMonitorWait")
             .withThreshold(Duration.ZERO).withStackTrace();
            r.enable("jdk.ThreadPark")
             .withThreshold(Duration.ZERO).withStackTrace();
            r.setToDisk(true);
            r.start();

            CountDownLatch ownerReady = new CountDownLatch(1);
            CountDownLatch waiterReady = new CountDownLatch(1);
            CountDownLatch parkReady = new CountDownLatch(1);

            Thread owner = new Thread(() -> {
                synchronized (ENTER_LOCK) {
                    ownerReady.countDown();
                    nap(1900);
                }
            }, "lab-owner");

            Thread contender = new Thread(() -> {
                await(ownerReady);
                synchronized (ENTER_LOCK) { }
            }, "lab-contender");

            Thread waiter = new Thread(() -> {
                synchronized (WAIT_LOCK) {
                    waiterReady.countDown();
                    try {
                        WAIT_LOCK.wait(1700);
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    }
                }
            }, "lab-waiter");

            Thread notifier = new Thread(() -> {
                await(waiterReady);
                nap(900);
                synchronized (WAIT_LOCK) {
                    WAIT_LOCK.notifyAll();
                }
            }, "lab-notifier");

            Thread parker = new Thread(() -> {
                parkReady.countDown();
                LockSupport.parkNanos("lab-park-blocker",
                    Duration.ofMillis(1300).toNanos());
            }, "lab-parker");

            owner.start();
            contender.start();
            waiter.start();
            notifier.start();
            parker.start();

            ownerReady.await();
            waiterReady.await();
            parkReady.await();

            boolean allWaiting = false;
            for (int i = 0; i < 100; i++) {
                allWaiting =
                    contender.getState() == Thread.State.BLOCKED &&
                    waiter.getState() == Thread.State.TIMED_WAITING &&
                    parker.getState() == Thread.State.TIMED_WAITING;
                if (allWaiting) break;
                Thread.sleep(10);
            }
            if (!allWaiting) {
                throw new IllegalStateException("states not observed");
            }
            System.out.println("SNAPSHOT_WINDOW");

            owner.join();
            contender.join();
            waiter.join();
            notifier.join();
            parker.join();

            r.stop();
            r.dump(file);
        }

        Set<String> found = new HashSet<>();
        try (RecordingFile read = new RecordingFile(file)) {
            while (read.hasMoreEvents()) {
                RecordedEvent e = read.readEvent();
                String kind = e.getEventType().getName();

                if (!kind.equals("jdk.JavaMonitorEnter") &&
                    !kind.equals("jdk.JavaMonitorWait") &&
                    !kind.equals("jdk.ThreadPark")) {
                    continue;
                }
                if (e.getThread("eventThread") == null) continue;

                String thread = e.getThread("eventThread").getJavaName();
                if (kind.equals("jdk.JavaMonitorEnter") &&
                    thread.equals("lab-contender")) {
                    found.add("Enter");
                }
                if (kind.equals("jdk.JavaMonitorWait") &&
                    thread.equals("lab-waiter")) {
                    found.add("Wait");
                }
                if (kind.equals("jdk.ThreadPark") &&
                    thread.equals("lab-parker")) {
                    found.add("Park");
                }
            }
        }

        System.out.println("JavaMonitorEnter=" + found.contains("Enter"));
        System.out.println("JavaMonitorWait=" + found.contains("Wait"));
        System.out.println("ThreadPark=" + found.contains("Park"));
    }
}
```

Đây là **chương trình Java hoàn chỉnh**, biên dịch được bằng `javac --release 17` và không dùng thư viện ngoài JDK. `Duration.ZERO` cho event threshold là 0 nhằm bắt các events ngắn trong **thử nghiệm**; không bật mặc định trên production vì có thể sinh số lượng events lớn.

### 10.2. Chạy và đọc stdout

```bash
javac --release 17 JfrLockTriadDemo.java
java JfrLockTriadDemo triad-demo.jfr
```

**Stdout chính xác của lần kiểm thử đã thực hiện:**

```text
SNAPSHOT_WINDOW
JavaMonitorEnter=true
JavaMonitorWait=true
ThreadPark=true
```

`SNAPSHOT_WINDOW` được in sau khi code xác nhận ba thread đang ở đúng trạng thái: một `BLOCKED`, hai `TIMED_WAITING`. Ba giá trị `true` được tính bằng việc đọc **file recording thật**, lọc theo event type và thread name; không phải dòng in cứng.

Trên JVM/vendor hoặc tải khác, thời lượng và ID có thể biến đổi; điều kiện trạng thái trong chương trình cũng có thể bị timeout ở môi trường cực kỳ chậm và ném `IllegalStateException`. Khi ấy cần tăng độ dài các khoảng chờ trong môi trường thử nghiệm, không sửa kết quả in giả.

### 10.3. In events và đối chiếu

```bash
jfr summary triad-demo.jfr
jfr print --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.ThreadPark --stack-depth 5 triad-demo.jfr
```

Trong một lần QA thực tế, file có:

- `lab-contender`: `JavaMonitorEnter` duration khoảng **1,9 giây**, `previousOwner=lab-owner`.
- `lab-waiter`: `JavaMonitorWait` duration khoảng **0,9 giây**, `notifier=lab-notifier` và `timedOut=false`.
- `lab-parker`: `ThreadPark` duration khoảng **1,3 giây**, `parkedClass=java.lang.String`.
- Một số events khác do JVM/JFR runtime và `Thread.join` của main thread tạo ra.

Những duration/addresses/thread IDs **không cố định giữa các lần chạy**. Quan trọng là sự liên hệ đúng **eventThread + event type + call path**.

### 10.4. Chụp thread dump khi demo đang chờ

Tại terminal khác, khi xuất hiện `SNAPSHOT_WINDOW` và JVM chưa kết thúc:

```bash
jcmd -l
jcmd <PID> Thread.print -l > snapshot.txt
```

Cửa sổ mẫu mặc định chỉ kéo dài **vài giây**, nên khi thao tác thủ công có thể cần **tăng các khoảng `nap(1900)`, `WAIT_LOCK.wait(1700)` và `parkNanos(1300 ms)` rồi biên dịch lại**; hoặc tự động hóa việc chụp ngay khi cửa sổ bắt đầu. Trong một phép thử live đã kiểm tra, `jcmd Thread.print -l` có thể nhìn thấy cùng ba tên thread trong JVM target.

Dạng trạng thái dự kiến **trong cửa sổ**:

| Thread | State trong dump | Dấu hiệu | Event tương ứng sau khi hoàn tất |
| --- | --- | --- | --- |
| `lab-contender` | `BLOCKED` | `waiting to lock` monitor do `lab-owner` giữ | `JavaMonitorEnter` |
| `lab-waiter` | `TIMED_WAITING (on object monitor)` | `Object.wait`, `waiting on` | `JavaMonitorWait` |
| `lab-parker` | `TIMED_WAITING (parking)` | `LockSupport.parkNanos` | `ThreadPark` |
| `lab-owner` | Thường `TIMED_WAITING (sleeping)` | `locked` monitor ở `synchronized` | Có thể không có monitor-enter contention event |
| `lab-notifier` | Có thể sleep hoặc đã notify xong | `notifyAll` sau một khoảng delay | Trường `notifier` trong `JavaMonitorWait` |

Không kết luận demo thất bại nếu một dump chụp **sau khi event đã kết thúc** không còn thấy thread chờ; JFR vẫn có thể giữ event trong file.

## 11. Thread dump và JFR khi nghi deadlock

Ví dụ wait-for graph của **object monitor deadlock**:

```text
Thread A --waits for monitor L2--> Thread B
Thread B --waits for monitor L1--> Thread A
```

Thread dump có thể cho hai dòng `- waiting to lock <...>` và `- locked <...>` phù hợp, hoặc phần `Found one Java-level deadlock`. Đây là bằng chứng dựng một vòng **waiter → owner trong cùng snapshot**.

JFR **không phải detector deadlock đầy đủ**: `JavaMonitorEnter` nói về contention event đã ghi, `JavaMonitorWait` nói về chờ notification, `ThreadPark` nói về park. Một deadlock chưa được giải phóng có thể khiến monitor-enter event **không bao giờ hoàn tất**, nên không có completed event để khẳng định cycle.

Khi có nghi vấn:

1. Từ dump, xác định mỗi thread **đang chờ lock nào** và **owner tại thời điểm chụp**.
2. Chỉ vẽ cạnh waiter → owner khi có cùng lock identity hoặc explicit owner metadata.
3. Truy vết tới khi dừng hoặc lặp: `A → B → C → A` là cycle.
4. Kiểm tra `ThreadMXBean.findMonitorDeadlockedThreads()`/`findDeadlockedThreads()` nếu JVM hỗ trợ; lưu ý phạm vi monitor và ownable synchronizers.
5. Dùng JFR phân tích **trước vòng treo**: code path nào tranh chấp thường xuyên, duration tăng từ lúc nào, bao nhiêu requests bị ảnh hưởng.
6. Với DB locks, network waits hoặc distributed locks, thread dump/JFR chỉ là một phần; cần dữ liệu từ hệ thống sở hữu tài nguyên.

## 12. Các tình huống chẩn đoán thường gặp

### A. Latency tăng nhưng dump không thấy `BLOCKED`

Snapshot có thể bỏ lỡ rất nhiều contention ngắn. JFR `JavaMonitorEnter` theo timeline cho biết code path và duration của những sự kiện **vượt threshold**. Nếu `threshold=20ms`, các tranh chấp 5–10ms có thể không có event. Đừng coi event count bằng 0 là không có tranh chấp.

### B. Nhiều thread pool đang `WAITING (parking)`

`ThreadPark` kéo dài trong `ThreadPoolExecutor.getTask`/`BlockingQueue.take` có thể chỉ là worker nhàn rỗi. Xem queue depth, active workers, task submissions và throughput. Nếu ứng dụng không có việc, park là hợp lệ; nếu backlog tăng, điều tra producer/scheduler/pool state.

### C. Thread `BLOCKED` nhưng không có `JavaMonitorEnter`

Kiểm tra `enabled`, threshold, recording window, file dump time và thread identity. Nếu contention đang diễn ra, event có thể **chưa commit**; cần snapshot owner hiện tại và có thể chờ sau khi giải tỏa để xem completed event. Nếu phát hiện cycle deadlock, không cần ép JFR có event để tin vào dump.

### D. `JavaMonitorWait` duration dài

`Object.wait` nhả monitor; event dài chưa chứng minh một thread giữ lock lâu. Xem `notifier`, `timedOut`, producer/signal path và điều kiện nghiệp vụ. Nếu `timedOut=false`, đừng mặc định chỉ có một nguyên nhân thức dậy.

### E. `ThreadPark` từ `ReentrantLock`/`Condition`

Stack có thể chứa `AbstractQueuedSynchronizer` hoặc `ConditionObject.await`. Cần phân biệt **chờ giành ReentrantLock** với **condition await đã nhả lock**. Với runtime hỗ trợ, dùng `ThreadInfo.getLockOwnerId()` và locked ownable synchronizers trong dump; `parkedClass` riêng lẻ không đủ tạo owner edge.

### F. Nhiều thread bị treo do database/network

JFR có thể cho `SocketRead`/`SocketWrite` hoặc ThreadPark, dump có stack I/O/Future; nhưng JVM không thấy owner Java thread của DB row lock hoặc remote service. Kết hợp DB lock graph, network traces, downstream logs và thời điểm client timeout. Không dựng Java monitor deadlock giả.

## 13. Threshold, recording window và overhead

JFR event settings gồm `enabled`, `threshold` và `stackTrace`. Các template `default.jfc`, `profile.jfc` của JDK có thể bật nhiều thread-stalling events và đặt threshold ở **mức hàng chục mili giây**, ví dụ 20ms trong một số default settings. Cấu hình JDK/vendor hoặc custom profile có thể khác; kiểm tra `JFR.check name=LockDiag verbose=true` thay vì giả định.

| Setting | Kết quả | Rủi ro |
| --- | --- | --- |
| `enabled=false` | Không ghi loại event | Không thể suy luận “không có wait” |
| `threshold=20ms` | Bỏ các events ngắn hơn 20ms | Bỏ sót contention ngắn lặp lại |
| `threshold=10ms` | Bắt thêm các events ngắn | Tăng event volume |
| `threshold=0ms` | Ghi cả events cực ngắn | Có thể tạo overhead và data volume rất lớn |
| `stackTrace=false` | Có duration nhưng không có call path | Khó truy nguyên code |
| `stackTrace=true` | Phân tích nhóm theo stack tốt hơn | Có thêm chi phí stack/data |

**Không mặc định đặt threshold 0 trên production.** Dùng recording có thời lượng, kích thước và phạm vi được phép; chỉ giảm threshold khi có câu hỏi điều tra rõ. File JFR và thread dumps có thể lộ class names, stack, command line, thông tin hệ thống hoặc dữ liệu nhạy cảm; lưu ở nơi giới hạn quyền, theo retention policy, redaction khi chia sẻ.

`jcmd Thread.print -l` có chi phí phụ thuộc số thread; chụp dump quá dày trên JVM nhiều thread cũng có thể ảnh hưởng latency. Cần tách điều tra một incident với monitoring thường xuyên.

## 14. Các lỗi suy luận phổ biến

| Sai lầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| “`JavaMonitorEnter` là mọi lần enter synchronized.” | Event chuyên về monitor contention. | Diễn giải đúng contended acquisition. |
| “Thread `BLOCKED` nhưng không có JFR event thì dump sai.” | Event chưa hoàn tất hoặc bị threshold/window lọc. | Tin snapshot cho state tại lúc chụp; kiểm tra settings. |
| “`JavaMonitorWait` là đang giữ monitor trong suốt wait.” | `Object.wait` nhả monitor đó. | Điều tra notifier/condition. |
| “`ThreadPark` luôn là ReentrantLock deadlock.” | Park có thể là idle queue/future/condition. | Xem stack/owner và tiến triển công việc. |
| “`previousOwner` là current owner trong dump.” | Semantics là **previous owner**. | Chủ sở hữu tại dump phải từ snapshot. |
| “`notifier` luôn có và `timedOut=false` chỉ có nghĩa notify.” | Có nhiều đường thức dậy và dữ liệu null. | Đối chiếu Javadoc và signal path. |
| “`address` trong JFR phải bằng token `<0x...>` của dump.” | Không có mapping bền vững phổ quát. | Ghép theo thread/time/stack và xác minh. |
| “`nid` bằng `javaThreadId`.” | `nid` thường là OS native ID. | Phân biệt Java vs native ID. |
| “Một park dài chứng minh deadlock.” | Có thể là pool idle bình thường. | Tìm cycle waiter → owner trong cùng snapshot. |
| “Không có event nghĩa không có contention.” | Threshold, disabled, window và event lifetime. | Kiểm tra cấu hình và thời gian. |
| “Ghép dump JVM A với JFR JVM B bằng cùng PID là đủ.” | PID có thể bị tái sử dụng. | Xác minh host/namespace/start time. |
| “`JFR.dump` tạo file trong thư mục shell client.” | File được ghi bởi JVM đích. | Kiểm tra filesystem/container path. |
| “Threshold 0 không ảnh hưởng hiệu năng.” | Event count/stack collection có thể rất lớn. | Chỉ dùng trong thử nghiệm hoặc điều tra giới hạn. |
| “Một JavaMonitorEnter dài chứng minh chu trình.” | Event completed không tự chứng minh cycle. | Dựng đồ thị từ dump/ThreadMXBean. |

## 15. Checklist điều tra end-to-end

- [ ] Đã xác nhận đúng **host, PID namespace, JVM PID, process start time, JDK/vendor**?
- [ ] Đã chụp thread dump `Thread.print -l` đúng cửa sổ triệu chứng và ghi UTC timestamp?
- [ ] Đã có JFR recording bao phủ cửa sổ và kiểm tra `enabled`/`threshold`/`stackTrace`?
- [ ] Đã dùng `jfr summary` và `jfr print --events ...` để xem có events thật?
- [ ] Khi ghép, dùng Java thread ID, tên và stack trên **cùng phiên JVM**, không nhầm `nid`/`tid`?
- [ ] Đã phân biệt `waiting to lock`, `waiting on` và `parking to wait for`?
- [ ] Với `JavaMonitorEnter`, xem eventThread/previousOwner nhưng kiểm chứng **live owner** từ dump?
- [ ] Với `JavaMonitorWait`, xem duration, timeout, timedOut, notifier và producer signal?
- [ ] Với `ThreadPark`, xem blocker/stack, pool idle hay AQS wait; không tự suy ra owner?
- [ ] Có xét khả năng event **chưa commit vì wait chưa kết thúc** không?
- [ ] Khi nghi deadlock, đã tìm **cycle waiter → owner trong một snapshot** chưa?
- [ ] Đã đối chiếu request latency, throughput, queue, CPU/GC/I/O và logs?
- [ ] Đã giới hạn recording duration, event threshold, dump frequency, dung lượng và quyền truy cập?
- [ ] Kết luận có đủ **bằng chứng → giả thuyết → kiểm chứng → hành động sửa**?

## 16. Tài liệu chính thức Java SE 17

- [Oracle — Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshoot-performance-issues-using-jfr.html): Java monitor blocked/wait, park, timeline và threshold.
- [Oracle — The jcmd Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `Thread.print`, `JFR.start`, `JFR.check`, `JFR.dump` và `JFR.stop`.
- [Oracle — The jfr Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html): `jfr summary`, `jfr print --events --stack-depth`.
- [Oracle — jdk.jfr package](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/package-summary.html): settings `enabled`, `threshold`, `stackTrace`.
- [Oracle — Recording](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Recording.html): programmatic recording, enable/stop/dump.
- [Oracle — RecordingFile](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): đọc `.jfr` events.
- [Oracle — ThreadMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html): thread owner/monitor deadlock detection.
- [Oracle — Object.wait](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#wait()): semantics nhả monitor/reacquire.
- [Oracle — LockSupport](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/LockSupport.html): parking, blocker và unpark.

**Kết luận:** Hãy dùng **thread dump để biết trạng thái và owner ngay lúc chụp** và **JFR để biết event duration/timeline/call path**. `JavaMonitorEnter` là chờ **vào monitor**, `JavaMonitorWait` là **`Object.wait`**, `ThreadPark` là **parking qua LockSupport/AQS**. Không gộp chúng thành một khái niệm “thread treo”; và chỉ gọi deadlock khi có đủ bằng chứng về **vòng waiter → owner**, không phải chỉ từ một event dài.