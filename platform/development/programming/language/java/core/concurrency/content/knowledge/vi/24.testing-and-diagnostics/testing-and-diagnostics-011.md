# Java Flight Recorder cho thread park, lock và allocation

## 1. Vì sao dùng JFR khi chẩn đoán Java concurrency?

Một chương trình nhiều thread có thể chậm dù CPU không đạt 100%: thread đang đợi lock, đợi tín hiệu, bị đánh thức quá nhiều, cấp phát đối tượng dày đặc làm tăng GC, hoặc bị nghẽn ở một đoạn `synchronized`. **Java Flight Recorder (JFR)** ghi lại các sự kiện trong JVM theo thời gian, giúp liên hệ *thread nào*, *đã xảy ra sự kiện gì*, *khi nào*, *mất bao lâu* và *stack trace nào có liên quan*.

JFR tích hợp trong JDK hiện đại, bao gồm Java 17+. Nó có thể ghi dữ liệu khi ứng dụng đang chạy, tạo tệp `.jfr` để phân tích bằng công cụ dòng lệnh `jfr` hoặc Java Mission Control (JMC). JFR phù hợp với chẩn đoán thực tế do chi phí thường thấp khi dùng cấu hình hợp lý, nhưng **không có cấu hình nào bảo đảm overhead bằng 0**. Sự kiện có stack trace, ngưỡng rất thấp hoặc theo dõi cấp phát chi tiết vẫn có thể tốn tài nguyên.

Phạm vi bài này là Java/JVM concurrency nói chung, không phụ thuộc framework ứng dụng.

Sau bài học, bạn cần biết:

1. Phân biệt **park**, **tranh chấp Java monitor**, **`Object.wait()`** và **allocation** bằng đúng loại JFR event.
2. Tạo recording trên Java 17+, đọc timeline, duration và stack trace mà không suy diễn quá mức.
3. Dùng JFR để khoanh vùng nguyên nhân contention và áp lực cấp phát, sau đó xác nhận bằng đo đạc/bằng chứng khác.
4. Điều chỉnh phạm vi ghi dữ liệu để tránh làm sai lệch workload hoặc thu quá nhiều sự kiện.

## 2. JFR lưu những gì? Sự kiện, thời gian và stack trace

JFR hoạt động theo mô hình **event**. Tùy từng loại event, bản ghi có thể gồm thời điểm bắt đầu, duration, tên/ID thread, class/đối tượng liên quan, thông tin thống kê và stack trace. Không phải sự kiện nào cũng có đầy đủ tất cả trường.

Có hai kiểu cần phân biệt:

- **Duration event:** mô tả một hoạt động kéo dài một khoảng thời gian, chẳng hạn `jdk.ThreadPark` hoặc `jdk.JavaMonitorEnter` khi bị tranh chấp. Sự kiện chỉ được ghi nếu đã bật và đáp ứng threshold/cấu hình tương ứng. Một duration dài có nghĩa thread đã trải qua khoảng thời gian đó; **không đồng nghĩa thread đang tiêu thụ CPU trong suốt khoảng đó**.
- **Sample/statistics event:** lấy mẫu hoặc thống kê theo thời điểm/chu kỳ, chẳng hạn `jdk.ObjectAllocationSample` hoặc `jdk.ThreadAllocationStatistics`. Dữ liệu này **không phải danh sách đầy đủ từng allocation** hay số liệu tức thời của mọi phép ghi bộ nhớ.

Một recording hữu ích phải có **khoảng thời gian đúng lúc sự cố xảy ra**. Nếu bắt đầu quá muộn, hết hạn quá sớm hoặc threshold cao hơn độ dài sự kiện, JFR có thể không ghi được dấu hiệu mong muốn. Ngược lại, vắng event không tự động chứng minh không có contention.

### Những công cụ thường dùng

| Công cụ | Vai trò |
| --- | --- |
| `jcmd <pid> JFR.start ...` | Bắt đầu recording cho JVM đang chạy, nếu có quyền attach |
| `jcmd <pid> JFR.check` | Kiểm tra các recording của JVM đích |
| `jcmd <pid> JFR.dump ...` | Ghi snapshot recording ra tệp `.jfr` |
| `jfr summary file.jfr` | Xem các loại event, số lượng và thông tin recording |
| `jfr print --events ... file.jfr` | In event cụ thể, gồm thời gian/thread/stack khi có |
| Java Mission Control | Phân tích timeline, các thread, lock/park và phân bổ cấp phát theo giao diện |

**Lưu ý phiên bản:** cú pháp và giao diện tính năng có thể phát triển giữa các bản JDK. Ví dụ `jfr view` có ở những JDK mới hơn, không nên mặc định có trong Java 17; các lệnh `jfr summary` và `jfr print` là lựa chọn phù hợp với Java 17.

## 3. Chọn đúng event cho park, lock và allocation

| Event JFR | Quan sát gì? | Kết luận có thể rút ra | Điều không được kết luận ngay |
| --- | --- | --- | --- |
| `jdk.ThreadPark` | Thread bị park qua cơ chế `LockSupport` và các synchronizer có dùng park | Thread đã chờ/đỗ, tìm call path đang chờ | Park luôn là lock contention hoặc deadlock |
| `jdk.JavaMonitorEnter` | **Contended** entry vào Java monitor của `synchronized` | Thread chờ vào monitor; tìm nơi giữ và nơi chờ monitor | Mọi lần vào `synchronized` đều phát event |
| `jdk.JavaMonitorWait` | Lời gọi `Object.wait()` trên monitor | Thread đợi notification/timeout, đã nhả monitor tương ứng khi wait | Đây là thời gian chờ để *vào* `synchronized` |
| `jdk.ObjectAllocationSample` | Mẫu allocation trên Java heap, với loại object/stack khi khả dụng | Những call path có khả năng gây nhiều allocation | Đã đếm chính xác từng object hoặc byte cấp phát |
| `jdk.ThreadAllocationStatistics` | Thống kê byte do thread cấp phát ở các mốc thu thập | Thread nào có lượng allocation tích lũy tăng mạnh | Từng allocation cụ thể hoặc toàn bộ nguyên nhân GC |
| `jdk.ObjectAllocationInNewTLAB`, `jdk.ObjectAllocationOutsideTLAB` | Các sự kiện liên quan cấp phát TLAB/ngoài TLAB khi được bật | Trợ giúp khảo sát đường cấp phát sâu hơn | Mặc nhiên là bộ đếm toàn bộ object ở chi phí thấp |

**Tên event là tên kỹ thuật JFR trên HotSpot/JDK tương ứng; luôn kiểm tra danh sách event thực tế của JVM đang dùng.** Event còn phụ thuộc việc được hỗ trợ và cấu hình có bật hay không.

### 3.1. `jdk.ThreadPark`: thời gian thread đỗ/chờ

`LockSupport.park()` hoặc `parkNanos()` có thể làm thread ngừng chạy cho tới lúc được `unpark`, bị interrupt, timeout (với dạng có thời hạn) hoặc trở về do *spurious wakeup*. Các cấu trúc `java.util.concurrent` như một số đường chờ của `ReentrantLock`, `Semaphore`, `CountDownLatch` và `BlockingQueue` có thể dùng cơ chế park bên dưới.

Sự kiện `jdk.ThreadPark` giúp thấy thời gian chờ, thread và stack liên quan. Stack có thể bắt đầu ở `LockSupport.park`, đi qua AQS (`AbstractQueuedSynchronizer`) và tới mã ứng dụng gọi `await()`/`take()`/`lock()`.

**Diễn giải theo ngữ cảnh:**

- Worker của thread pool đang rảnh, chờ việc, park hàng giây có thể là **hành vi bình thường**.
- Producer/consumer chờ queue rỗng hoặc đầy có thể phản ánh backpressure hay mất cân bằng thông lượng.
- Một request thread park lâu tại `ReentrantLock.lock()` có thể là dấu hiệu chờ lock; cần liên hệ ai đang giữ lock và thời điểm xảy ra.
- `Thread.sleep()` thường được quan sát qua **`jdk.ThreadSleep`**, không phải mặc nhiên `jdk.ThreadPark`.

Trạng thái `WAITING`/`TIMED_WAITING` trong thread dump cũng không đủ để gọi đó là lỗi: phải xác định **lý do chờ** và nó có nằm trên đường phục vụ request hay không.

### 3.2. `jdk.JavaMonitorEnter`: chờ vào `synchronized`

Một thread bước vào `synchronized (monitor)` cần sở hữu monitor. Khi monitor đang bị thread khác nắm giữ và việc vào monitor bị tranh chấp, JFR có thể ghi `jdk.JavaMonitorEnter` nếu event được bật và thời gian chờ vượt ngưỡng.

Dữ liệu có thể cho biết **event thread** (thread bị chặn), **monitor class**, duration, stack của nơi xin monitor, và thông tin **previous owner** khi JVM cung cấp. Nhưng stack của thread đang chờ **không tự nó nói được chính xác đoạn code nào trong thread giữ monitor đã làm chậm**. Có thể cần thêm thread dump/sự kiện cùng thời điểm để xác định critical section dài, I/O hoặc gọi callback dưới monitor.

Đây là **chờ để *vào* monitor**. Một đoạn `synchronized` chạy lâu nhưng không có thread khác tranh chấp có thể không tạo `jdk.JavaMonitorEnter` đáng chú ý. Muốn đo **hold time** của monitor, cần thêm instrumentation/benchmark hoặc profile path liên quan; không được xem duration của enter event như tổng thời gian monitor bị giữ.

### 3.3. `jdk.JavaMonitorWait`: `Object.wait()` không phải enter contention

Khi thread gọi `Object.wait()` trong lúc sở hữu monitor, nó nhả **monitor đó** và chờ notify/notifyAll, timeout hoặc interrupt. Trước khi `wait()` trả về bình thường hoặc do interrupt, thread phải lấy lại monitor tương ứng. Event `jdk.JavaMonitorWait` liên quan thời gian chờ trong thao tác này; nó **không đồng nghĩa** với việc thread luôn bị chặn khi cố vào một block `synchronized`.

Ví dụ consumer đang chờ điều kiện qua `wait()` có thể đợi hợp lệ. Cần kiểm tra vòng lặp điều kiện (`while (!condition) wait()`), thread làm `notify`/thay đổi condition, timeout, interruption và nguy cơ lost notification do thiết kế sai.

**Phân biệt quan trọng:** `Condition.await()` của `ReentrantLock` không phải `Object.wait()`; nhiều implementation dùng `LockSupport` và biểu hiện ở sự kiện park. Đừng gán mọi `WAITING` cho `jdk.JavaMonitorWait`.

### 3.4. Allocation: nơi tạo object và ảnh hưởng tới concurrency

Allocation rất nhanh trên nhiều đường chạy của HotSpot, nhưng tốc độ tạo object quá cao có thể làm tăng lưu lượng bộ nhớ, chi phí GC, contention ở allocator hoặc cache pressure. Những thread xử lý request có thể bị gián đoạn đáng kể do GC hoặc workload thu gom, dù chúng không tranh nhau monitor Java.

- **`jdk.ObjectAllocationSample`:** dùng để tìm loại object và call path đáng chú ý. Đây là sampling; số event phụ thuộc thuật toán lấy mẫu, cấu hình và workload. Không được đọc mỗi mẫu như "một object duy nhất trong hệ thống".
- **`jdk.ThreadAllocationStatistics`:** số byte cấp phát tích lũy theo thread tại các lần thu thập; lấy chênh lệch giữa các mẫu thích hợp để ước lượng tốc độ cấp phát, có tính đến thread lifecycle và khoảng thời gian. Không dùng một mốc đơn để suy ra tốc độ.
- **TLAB events:** thread-local allocation buffer (TLAB) giảm phần lớn tranh chấp trên đường cấp phát nhanh. Các sự kiện in-new-TLAB/outside-TLAB có thể giúp xem hành vi cấp phát ở mức sâu hơn, nhưng phải đánh giá overhead, sampling/cấu hình và không được dùng chúng như tổng kiểm kê object đầy đủ nếu chưa xác minh semantics.
- **GC events:** `jdk.GarbageCollection`, `jdk.GCPhasePause` và các event GC khác (tùy collector/JDK) bổ sung thời gian pause, số đợt GC; correlation theo timeline có ý nghĩa hơn kết luận "allocation = lock contention".

Không phải object trong source Java đều được cấp phát trên heap thật: JIT escape analysis/scalar replacement có thể loại bỏ một số allocation. Các sample chỉ phản ánh hoạt động runtime đã xảy ra trong recording, không phải đếm lệnh `new` trong source.

## 4. Thực hành có thể chạy trên Java 17+: chủ động tạo ba tín hiệu

Ví dụ dưới đây tạo **một recording JFR ngay trong JVM** bằng API `jdk.jfr`, rồi tạo các tình huống:

1. Một thread park khoảng 150 ms bằng `LockSupport.parkNanos`.
2. Một thread giữ Java monitor trong khi thread khác cố vào monitor đó.
3. Một thread thực hiện `Object.wait(120)`.
4. Main thread tạo nhiều mảng `byte[]` để có workload allocation quan sát được.

Ta bật event với ngưỡng nhỏ cho bài thực hành. Trong production, ngưỡng cần chọn cẩn thận để kiểm soát overhead và tập trung vào đuôi latency quan trọng.

**Tệp: `JfrThreadDiagnosticsDemo.java`**

```java
import jdk.jfr.Configuration;
import jdk.jfr.Recording;

import java.nio.file.Path;
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.LockSupport;

public final class JfrThreadDiagnosticsDemo {
    private static final Object MONITOR = new Object();
    private static final Object WAIT_MONITOR = new Object();

    // Giữ tham chiếu đi ra khỏi vòng lặp để JIT khó loại bỏ các cấp phát.
    private static volatile byte[] retained;

    private static void sleepInsideMonitor() {
        synchronized (MONITOR) {
            try {
                Thread.sleep(300);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path output = Path.of("thread-lock-allocation.jfr");

        try (Recording recording =
                new Recording(Configuration.getConfiguration("profile"))) {
            recording.setName("thread-lock-allocation");
            recording.enable("jdk.ThreadPark")
                    .withThreshold(Duration.ofMillis(1));
            recording.enable("jdk.JavaMonitorEnter")
                    .withThreshold(Duration.ofMillis(1));
            recording.enable("jdk.JavaMonitorWait")
                    .withThreshold(Duration.ofMillis(1));
            recording.enable("jdk.ObjectAllocationSample");
            recording.enable("jdk.ThreadAllocationStatistics")
                    .withPeriod(Duration.ofMillis(100));

            recording.start();

            Thread parker = new Thread(() ->
                    LockSupport.parkNanos(TimeUnit.MILLISECONDS.toNanos(150)),
                    "park-demo");

            CountDownLatch holderEntered = new CountDownLatch(1);
            Thread holder = new Thread(() -> {
                synchronized (MONITOR) {
                    holderEntered.countDown();
                    try {
                        Thread.sleep(300);
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    }
                }
            }, "monitor-holder");

            Thread contender = new Thread(() -> {
                try {
                    holderEntered.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }
                synchronized (MONITOR) {
                    // Chỉ vào được sau khi holder nhả monitor.
                }
            }, "monitor-contender");

            Thread waiter = new Thread(() -> {
                synchronized (WAIT_MONITOR) {
                    try {
                        WAIT_MONITOR.wait(120);
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    }
                }
            }, "object-wait-demo");

            parker.start();
            holder.start();
            contender.start();
            waiter.start();

            parker.join();
            holder.join();
            contender.join();
            waiter.join();

            for (int i = 0; i < 20_000; i++) {
                retained = new byte[4096];
            }

            recording.stop();
            recording.dump(output);
        }

        System.out.println("Saved: thread-lock-allocation.jfr");
    }
}
```

Lệnh biên dịch và chạy:

```bash
javac JfrThreadDiagnosticsDemo.java
java JfrThreadDiagnosticsDemo
```

Stdout từ chương trình (khi chạy thành công trong thư mục có quyền ghi):

```text
Saved: thread-lock-allocation.jfr
```

Tệp `thread-lock-allocation.jfr` được tạo cùng thư mục làm việc hiện hành, trừ khi bạn thay đổi đường dẫn `output`. Những con số duration/số lượng event trong recording **không cố định** do scheduling, JIT, sampling và ngưỡng. Chẳng hạn, nếu contender không được scheduler chạy trước khi holder nhả monitor, recording có thể không có sự kiện tranh monitor đúng như dự định; hãy chạy lại hoặc bổ sung đồng bộ thử nghiệm khi cần chứng minh một tình huống hiếm.

**Giải thích cơ chế của từng đoạn:**

- `parker` có call stack dẫn tới `LockSupport.parkNanos`, tương ứng `jdk.ThreadPark` nếu sự kiện đáp ứng threshold.
- `holder` giữ `MONITOR` trong khi `contender` đợi; đây là **contended entry** tương ứng `jdk.JavaMonitorEnter`. Việc `Thread.sleep` của holder không nhả monitor; vì vậy có thể tăng thời gian chờ của contender.
- `waiter` sử dụng `Object.wait(timeout)` và nhả `WAIT_MONITOR` trong khi đợi; đây là ví dụ `jdk.JavaMonitorWait`, không phải contention của `contender`.
- `retained` là một volatile reference được ghi mỗi vòng; mục đích là khiến mảng escape khỏi phép tính đơn giản, tránh benchmark chỉ đo mã đã bị JIT loại bỏ. Allocation sampling **không cam kết** mỗi lần tạo mảng đều có event.
- `recording.enable(...).withThreshold(...)` đặt threshold riêng cho các duration event; `ThreadAllocationStatistics` dùng period để thu thống kê. Với thiết lập học tập 1 ms, số event có thể lớn hơn thiết lập mặc định.
- `try (Recording ...)` bảo đảm đóng recording sau khi dump. Kết quả stdout chỉ in sau khi các thread hoàn tất và file dump thành công.

Bài thực hành không cố mô phỏng đầy đủ deadlock hoặc GC production. Trong một chương trình thật, không nên cố ý giữ monitor qua `Thread.sleep`; đoạn này tồn tại chỉ để tạo tín hiệu contention rõ ràng.

### Đọc kết quả bằng CLI

Trước tiên xem recording có những loại event nào:

```bash
jfr summary thread-lock-allocation.jfr
```

Sau đó lọc các event liên quan tới chờ thread/monitor:

```bash
jfr print --stack-depth 24 --events jdk.ThreadPark,jdk.JavaMonitorEnter,jdk.JavaMonitorWait thread-lock-allocation.jfr
```

Và phân tích nhóm cấp phát:

```bash
jfr print --stack-depth 24 --events jdk.ObjectAllocationSample,jdk.ThreadAllocationStatistics thread-lock-allocation.jfr
```

Đây là các lệnh có thể chạy bằng tiện ích `jfr` từ JDK 17+. Output thực tế phụ thuộc JDK/OS, mức sampling, thread scheduling và thời điểm ghi nên **không có một stdout JFR cố định cần chép lại**. Nếu cần xử lý máy móc, `jfr print --json --events ...` trả dạng JSON theo khả năng của phiên bản `jfr`; tránh kết luận từ một trường không chắc chắn có trên mọi JDK.

Nếu không thấy event mong đợi, hãy kiểm tra lần lượt:

1. Recording có đúng khoảng thời gian thao tác không?
2. Event có được JVM hỗ trợ và bật chưa? Threshold/period có lọc mất sự kiện ngắn không?
3. Đã tạo đúng tình huống chưa, ví dụ contention thật sự thay vì chỉ vào `synchronized` khi lock đang rảnh?
4. Có đang đọc đúng file dump, đúng JVM/PID và đúng tên thread không?
5. Đối với allocation sample, workload đã đủ lớn để được lấy mẫu chưa, JIT có loại bỏ allocation không?

## 5. Ghi JFR cho JVM đã chạy: cách dùng `jcmd`

Trong ứng dụng thật, thường không sửa source chỉ để tạo recording. Nếu có quyền truy cập vào process JVM và JDK tools, tìm PID:

```bash
jcmd -l
```

Bắt đầu một recording có thời lượng hữu hạn (ví dụ 60 giây) với profile settings:

```bash
jcmd <pid> JFR.start name=triage settings=profile duration=60s filename=triage.jfr
```

Kiểm tra trạng thái:

```bash
jcmd <pid> JFR.check
```

Có thể chủ động dump dữ liệu khi đang ghi:

```bash
jcmd <pid> JFR.dump name=triage filename=triage-now.jfr
```

Đọc file kết quả:

```bash
jfr summary triage-now.jfr
jfr print --events jdk.ThreadPark,jdk.JavaMonitorEnter,jdk.ObjectAllocationSample triage-now.jfr
```

Trong các lệnh trên, **`<pid>` là placeholder** cần thay bằng PID thực tế. Đường dẫn file có thể được JVM đích diễn giải theo working directory/quyền của process; nếu chẩn đoán một dịch vụ từ xa/container, hãy xác minh file thực sự được lưu ở đâu và có quyền truy cập. Khi dùng `duration`, recording sẽ tự kết thúc theo cấu hình; chỉ sử dụng `JFR.dump` sau khi file xuất hiện và có dữ liệu đúng khoảng cần phân tích.

`settings=profile` thường cho nhiều chi tiết hơn `settings=default`, đổi lại overhead có thể cao hơn. Không nên để ghi chi tiết vô hạn chỉ vì muốn tìm một event hiếm. Với trường hợp có yêu cầu đặc biệt, hãy dùng tệp cấu hình JFR `.jfc` đã kiểm chứng cho JVM đang chạy (tùy chọn event, threshold, stack trace, sampling/period) và đánh giá overhead trước khi áp dụng dài hạn.

### Dùng Java Mission Control

Mở file `.jfr` trong Java Mission Control, rồi:

1. Chọn đúng khoảng timeline trùng lúc latency tăng hoặc sự cố xuất hiện.
2. Tìm phần thread activity, Java monitor blocking, socket/file I/O, allocation và GC phù hợp với giao diện phiên bản JMC đang dùng.
3. Xác định thread/stack lặp lại tại thời điểm chờ lâu; lọc theo tên thread, duration, monitor class và method của ứng dụng.
4. Liên hệ với biểu đồ CPU/GC/throughput/latency, thay vì chỉ sắp xếp event theo duration rồi quy mọi chờ lâu là lỗi.
5. Đối chiếu trước/sau thay đổi với cùng workload và setting recording.

Tên trang/nhãn giao diện của JMC thay đổi theo phiên bản, nhưng nguyên tắc **timeline + thread + stack + event type** không đổi.

## 6. Quy trình điều tra: từ triệu chứng đến nguyên nhân

Giả sử một ứng dụng Java nhiều thread có request latency tăng. Một quy trình đủ thận trọng:

### Bước 1 — Xác định triệu chứng và cửa sổ thời gian

Ghi lại thời điểm latency cao, throughput, lượng request, CPU, heap/GC, số thread sống và các bất thường khác. Recording phải bao trùm cửa sổ đó; một bản ghi lúc hệ thống rảnh không chứng minh điều gì về lúc tải cao.

### Bước 2 — Tìm loại chờ tương ứng

- Nhiều `jdk.JavaMonitorEnter` duration dài, cùng monitor class và stack: có thể có **monitor contention**; xem critical section, thread owner, I/O hoặc callback dưới `synchronized`.
- Nhiều `jdk.ThreadPark` tại `ReentrantLock.lock` hoặc `Condition.await`: xem đường chờ của synchronizer, queue, điều kiện đánh thức, fairness và dữ liệu tải.
- Nhiều park ở worker idle queue lúc tải thấp: thường là **chờ công việc hợp lệ**; không nên tối ưu loại bỏ.
- `jdk.JavaMonitorWait` dài: kiểm tra điều kiện chờ, notify, timeouts và hợp đồng producer–consumer.
- Allocation/sample tăng mạnh rồi GC pause/tần suất GC tăng: có thể là vấn đề **allocation pressure** tác động đến latency, không đồng nghĩa tất cả thread bị block vì lock.

### Bước 3 — Xem stack và chủ thể liên quan

Tìm frame ứng dụng **gọi tới** API chờ, không dừng ở `Unsafe.park`/`LockSupport.park` hoặc nội bộ AQS. Nếu `JavaMonitorEnter` cung cấp previousOwner, dùng nó như manh mối, rồi so timeline, thread dump và code critical section. Dữ liệu JFR có thể bị sampling, threshold, JVM version và ngữ cảnh làm thiếu chi tiết; **không dựng chuỗi nhân quả chỉ từ một event**.

Ví dụ:

```text
request-thread-17
  -> OrderCoordinator.process()
  -> ReentrantLock.lock()
  -> LockSupport.park()                 [jdk.ThreadPark]

worker-thread-4
  -> CacheRefresher.refresh()
  -> synchronized (sharedMonitor)      [giữ monitor]

request-thread-22
  -> synchronized (sharedMonitor)      [jdk.JavaMonitorEnter]
```

Sơ đồ trên là **tình huống minh họa**, không phải output thực tế từ JFR. Hai đường chờ đầu tiên không tự chứng minh cùng một lock hay có deadlock. Chỉ khi xác định được object/lock, holder/waiter và vòng phụ thuộc mới có thể kết luận chính xác.

### Bước 4 — Xác nhận bằng phép đo độc lập

- Đối với monitor: đo critical section duration, giảm công việc không cần thiết trong lock, xem contention còn giảm không.
- Đối với park: kiểm tra nguồn dữ liệu mà thread đang chờ, contention thật trên `ReentrantLock`, queue size, signal rate hoặc vấn đề backpressure.
- Đối với allocation: dùng allocation profile theo loại object/stack, giảm allocation trong hot path, đo thêm GC/throughput; tránh chỉ dựa vào việc số sample giảm do JIT hay profile khác.
- Khi nghi deadlock, lấy thread dump/`jcmd <pid> Thread.print` để đối chiếu; một số vòng chờ liên quan tài nguyên bên ngoài hoặc giao thức tùy biến có thể không hiện thành deadlock monitor đơn giản.

### Bước 5 — Kiểm chứng sau thay đổi

Ghi cùng setting JFR, cùng tải và cửa sổ quan sát; so thời gian chờ phân phối theo thread/method, số event vượt threshold, số byte cấp phát theo khoảng thời gian, GC pause và **latency/throughput của hệ thống**. Giảm số event không có nghĩa đã tối ưu thành công nếu threshold, thời gian chạy hoặc workload thay đổi.

## 7. Hiểu đúng threshold, sampling và overhead

### Threshold của duration event

Một sự kiện có thể chỉ được ghi nếu duration đủ lớn. Ví dụ threshold 20 ms (một cấu hình có thể gặp, không phải mặc định bất biến) sẽ lọc bỏ các lần chờ 2 ms, dù hàng triệu lần chờ ngắn này có thể ảnh hưởng tổng throughput. Khi cần điều tra chúng, có thể hạ threshold trong một đợt ghi ngắn, nhưng phải quan sát overhead và tổng số event.

Ngược lại, threshold nhỏ trên production quá bận có thể sinh lượng dữ liệu lớn, làm nhiễu benchmark và tăng I/O/CPU/memory overhead. Hãy chọn ngưỡng theo câu hỏi đang điều tra: tail latency, tổng thời gian đợi, hay hotspot cụ thể.

### Sampling của allocation

`jdk.ObjectAllocationSample` là **mẫu**, không phải tất cả `new`. Không lấy `count(events)` làm tổng object; nếu event có thông tin weight/ước lượng, đọc đúng semantics của phiên bản JFR, không cộng thiếu kiểm chứng. Chênh lệch giữa hai bản ghi có thể đến từ JIT warmup, sampling và throughput. Muốn ước lượng bytes/thread, xem `jdk.ThreadAllocationStatistics` với khoảng thời gian hợp lý và liên hệ GC/runtime counters.

### Stack trace và khung thời gian

Một số sự kiện có thể tắt stack trace để giảm overhead; nếu không có frame ứng dụng, hãy kiểm tra setting thay vì nghĩ JVM không biết nguồn event. Thread name có thể được đổi hoặc tái sử dụng theo vòng đời; dùng thời điểm và thông tin thread định danh đi kèm khi đối chiếu. Một event park 5 giây không có nghĩa CPU bận 5 giây; một method xuất hiện nhiều stack sample cũng không chứng minh nó giữ lock trong toàn bộ thời gian.

### Recording profile

JFR là công cụ chẩn đoán có chi phí thấp tương đối khi cấu hình phù hợp. **Chi phí chính xác phụ thuộc recording settings, tần suất event, loại stack trace, JVM, workload và phần cứng.** Hãy cân bằng độ chi tiết với độ nhiễu; tránh dùng profile rất nặng trong thí nghiệm cần so vài phần trăm hiệu năng mà không đo overhead của profiler.

## 8. Những lỗi diễn giải phổ biến

**Lỗi 1: “Có nhiều ThreadPark, chắc chắn hệ thống đang deadlock.”**

Sai. Thread pool idle, blocking queue, latch, điều kiện chờ, rate limiter đều có thể park hợp lệ. Deadlock đòi hỏi bằng chứng một chu kỳ phụ thuộc không thể tiến triển, không chỉ một duration dài.

**Lỗi 2: “Không có JavaMonitorEnter thì không có lock contention.”**

Sai. Có thể event tắt, threshold cao, JFR không ghi đúng cửa sổ, hoặc contention thuộc `ReentrantLock`/synchronizer không phải Java monitor. Phải chọn cả park và monitor events phù hợp.

**Lỗi 3: “Duration JavaMonitorEnter bằng thời gian một thread giữ monitor.”**

Sai. Nó mô tả việc **thread đang vào bị chặn**. Thời gian monitor được giữ có thể chồng với duration đó nhưng không tương đương, nhất là khi nhiều waiter tranh nhau, có scheduling delay hoặc nhiều lần giữ/nhả.

**Lỗi 4: “JavaMonitorWait chính là LockSupport.park.”**

Sai. `Object.wait()` thuộc monitor API; `LockSupport` là primitive park. Các synchronizer xây trên AQS có thể dùng park nhưng không nhất thiết gọi `Object.wait()`.

**Lỗi 5: “Có 200 allocation sample nghĩa là chỉ tạo 200 object.”**

Sai. JFR lấy mẫu, và sampling rate/configuration tác động số event. Nhiều allocation không có event riêng; JIT còn có thể loại bỏ allocation trên heap.

**Lỗi 6: “Thấy allocation nhiều thì phải đổi sang object pool ngay.”**

Không đủ cơ sở. Object pool tăng độ phức tạp vòng đời, nguy cơ contention/giữ bộ nhớ và có thể làm GC khó tối ưu hơn. Phải xác nhận allocation nằm trên đường nóng và thay đổi đó thực sự cải thiện latency/throughput.

**Lỗi 7: “JFR phải luôn có cùng số event mỗi lần chạy demo.”**

Sai. JIT, scheduling, GC, thời gian recording, ngưỡng và sample khiến count không tất định. Điều cố định của demo là logic tạo tình huống và lệnh ghi file khi chạy thành công.

**Lỗi 8: “Thread bị WAITING thì không thể là bottleneck.”**

Không hẳn. Thread chờ có thể bình thường hoặc đang nằm trên critical path; điều quan trọng là chờ **cái gì**, **ai có thể làm nó tiếp tục**, và ảnh hưởng tới SLA. Thread state là điểm bắt đầu, còn JFR cung cấp bối cảnh và timeline để điều tra sâu.

## 9. Checklist thực hành

Trước khi ghi:

- Xác định JVM/PID/JDK đúng; bảo đảm có quyền và đủ không gian lưu file `.jfr`.
- Chọn recording window trùng lỗi hoặc tái hiện được workload.
- Chọn event: `ThreadPark` cho park/AQS, `JavaMonitorEnter` cho `synchronized` bị tranh, `JavaMonitorWait` cho `Object.wait`, allocation sample/statistics cho cấp phát.
- Kiểm tra ngưỡng, period, stack trace và sampling để vừa đủ giải đáp câu hỏi.

Khi phân tích:

- Xem thread, stack, start time, duration và event class; đọc **đúng semantics** của từng loại event.
- Liên hệ với CPU, GC, queue, throughput, latency và code đang giữ/tìm lock.
- Xác minh nguyên nhân bằng thread dump, profiler, instrumentation hoặc benchmark phù hợp.
- Phân biệt sự chờ **hợp lệ** của idle worker với chờ **trên critical path** của request.

Sau khi tối ưu:

- Chạy lại cùng workload/cấu hình ghi, so phân phối latency, contention, allocation rate, GC và throughput.
- Bảo đảm không phá tính đúng đắn của đồng bộ: không bỏ `synchronized`/`volatile`/`Lock` chỉ vì muốn giảm event.
- Giữ thời lượng recording và dữ liệu chẩn đoán ở phạm vi cần thiết; file JFR có thể chứa method, thread name, stack, class và metadata vận hành cần được quản lý phù hợp.

## 10. Câu hỏi ôn tập

**1. Một worker thread có event `jdk.ThreadPark` kéo dài 8 giây tại đường chờ task của thread pool. Có phải lỗi concurrency?**

Chưa đủ kết luận. Nếu pool đang rảnh, đó có thể là hành vi bình thường. Kiểm tra workload và xem thread có nằm trên đường phục vụ request đang trễ không.

**2. Thread A giữ `synchronized(lock)` để gọi hàm chậm; B bị chặn khi vào cùng monitor. Event nào trực tiếp cho biết B phải chờ monitor?**

`jdk.JavaMonitorEnter` của B khi contended entry vượt threshold. Để tìm vì sao A giữ lâu, xem code A và dữ liệu timeline/thread dump khác; duration event của B không trực tiếp bằng hold time của A.

**3. Thread C gọi `lock.wait(500)` trong block `synchronized(lock)`. Đây là `JavaMonitorEnter` hay `JavaMonitorWait`?**

Là kiểu `jdk.JavaMonitorWait` nếu event được bật và đạt threshold. `Object.wait` nhả monitor tương ứng trong thời gian wait; đây khác với chờ **đi vào** block synchronized.

**4. JFR ghi 100 `jdk.ObjectAllocationSample` cho `byte[]`. Có thể nói chương trình chỉ tạo 100 mảng không?**

Không. Đây là sampling; cần xem semantics/weight, thống kê allocated bytes và GC, đo cùng workload để đánh giá áp lực cấp phát.

**5. Vì sao một bản ghi không có `jdk.JavaMonitorEnter` vẫn có thể chứa bottleneck do `ReentrantLock`?**

`ReentrantLock` không phải monitor `synchronized`; đường chờ có thể dùng AQS và `LockSupport.park`, vì vậy hãy xem `jdk.ThreadPark` và call stack tương ứng.

**Ghi nhớ:** JFR là **bằng chứng theo thời gian** về những hoạt động JVM thực sự ghi nhận. Hãy kết hợp đúng event, stack, ngữ cảnh workload, threshold và phép đo đối chứng; việc nhìn thấy park, monitor wait hoặc allocation chỉ là khởi đầu của quá trình tìm nguyên nhân.