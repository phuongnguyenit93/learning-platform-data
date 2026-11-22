# Phân tích lock contention bằng Java Flight Recorder

**Lock contention** xảy ra khi nhiều thread cùng cần một tài nguyên đồng bộ, nhưng tại một thời điểm chỉ một thread được quyền đi qua vùng bảo vệ bởi lock. Thread còn lại phải chờ lock được nhả. Nếu thời gian chờ dài hoặc xảy ra thường xuyên, throughput giảm, latency tăng và các request có thể xếp hàng dù CPU không bận.

**Java Flight Recorder (JFR)** giúp tìm vị trí và thời lượng thread bị chặn hoặc bị park trong lúc chờ đồng bộ. Recording có thể cho biết thread nào đang chờ, loại monitor/lock nào liên quan, thread nào vừa sở hữu monitor và stack trace tại nơi thread phải chờ. Kết hợp dữ liệu này với JDK Mission Control (JMC), thread dump và workload thực tế sẽ giúp xác định đoạn code đang giữ lock quá lâu.

Lock contention khác với deadlock. Với contention thông thường, thread giữ lock cuối cùng sẽ nhả lock và các thread đang chờ tiếp tục chạy. Deadlock là tình trạng các thread chờ lẫn nhau theo một chu trình và không còn thread nào có thể tiến triển. JFR giúp phân tích thời gian chờ; thread dump là dữ liệu quan trọng khi nghi ngờ deadlock.

## 1. Lock contention ảnh hưởng tới ứng dụng như thế nào?

Một vùng critical section được bảo vệ bằng lock bảo đảm các thao tác dùng chung không chạy đồng thời ngoài ý muốn. Tuy nhiên, nếu nhiều request cùng đi qua một lock, chúng phải xếp hàng.

Ví dụ:

~~~java
public synchronized void updateSharedState() {
    loadDataFromRemoteService();
    updateCache();
    writeAuditLog();
}
~~~

Phương thức trên giữ monitor trong toàn bộ thời gian gọi dịch vụ từ xa, cập nhật cache và ghi log. Nếu thao tác I/O kéo dài, các thread khác gọi cùng phương thức phải chờ dù phần cập nhật dữ liệu thực tế chỉ cần vài mili giây.

Các triệu chứng thường gặp:

- Request latency tăng khi traffic tăng.
- Throughput không tăng dù đã tăng số thread hoặc số worker.
- Nhiều thread ở trạng thái BLOCKED hoặc PARKED.
- CPU có thể thấp vì thread đang chờ thay vì thực thi code.
- Một số lock hoặc class monitor xuất hiện lặp lại trong recording.
- Một nhóm request chậm cùng lúc vì cùng chờ một tài nguyên dùng chung.

Không nên kết luận có contention chỉ vì nhìn thấy nhiều thread ở trạng thái WAITING/BLOCKED. Cần xác định thread đang chờ điều gì, thời gian chờ có đáng kể không và việc chờ đó có ảnh hưởng tới request hoặc workload quan trọng hay không.

## 2. Các JFR event cần phân biệt

JFR có một số event liên quan tới đồng bộ. Chọn đúng event giúp tránh nhầm giữa việc chờ vào monitor, chờ điều kiện và thread được park.

| Event | Ý nghĩa | Khi nào xem |
|---|---|---|
| **jdk.JavaMonitorEnter** | Thread bị chặn khi cố vào một Java monitor, thường là vùng synchronized | Tìm thread chờ lấy intrinsic monitor |
| **jdk.JavaMonitorWait** | Thread đang ở trong thao tác Object.wait(), chờ notify hoặc timeout; Thread.join() cũng dùng cơ chế monitor wait | Phân tích chờ điều kiện, join hoặc wait/notify |
| **jdk.ThreadPark** | Thread bị park qua cơ chế LockSupport.park() | Phân tích ReentrantLock, AQS, semaphore, future và các cơ chế park khác |
| **jdk.ThreadSleep** | Thread chủ động ngủ trong một khoảng thời gian | Phân biệt sleep có chủ đích với lock wait |
| **jdk.SocketRead / jdk.FileRead** | Thread chờ thao tác I/O | Kiểm tra bottleneck do network hoặc file thay vì lock |

Không phải tất cả event đều có cùng ý nghĩa. Cần đọc duration, thread, class và stack trace trước khi kết luận.

### 2.1. JavaMonitorEnter: chờ vào synchronized monitor

**jdk.JavaMonitorEnter** có label trong JFR là **Java Monitor Blocked**. Event này ghi nhận thời gian thread bị chặn khi cố lấy monitor đã có thread khác sở hữu.

Các trường quan trọng:

- **duration:** thời gian thread bị chặn trước khi vào được monitor.
- **monitorClass:** class của object đang được dùng làm monitor.
- **previousOwner:** thread vừa sở hữu monitor trước khi thread đang chờ lấy được nó.
- **eventThread:** thread gặp contention.
- **stackTrace:** stack trace tại vị trí thread cố vào monitor.
- **address:** địa chỉ monitor, hữu ích khi nhóm các event liên quan tới cùng lock instance trong một recording.

Stack trace trong JavaMonitorEnter là vị trí của **thread đang chờ**. Trường previousOwner cho biết thread sở hữu monitor trước đó; để biết owner đang làm gì trong thời gian giữ lock, hãy đối chiếu thread timeline, stack trace ở các event khác hoặc thread dump.

### 2.2. JavaMonitorWait: chờ Object.wait hoặc Thread.join

**jdk.JavaMonitorWait** là event cho thao tác chờ trên monitor. Khi gọi **Object.wait()**, thread phải sở hữu monitor; JVM tạm nhả monitor trong lúc chờ notify hoặc timeout, rồi thread cần lấy lại monitor trước khi tiếp tục.

Event có thể chứa:

- **duration:** thời gian chờ.
- **monitorClass:** class của object được chờ.
- **notifier:** thread gửi notify nếu xác định được.
- **timeout** và **timedOut:** thời gian chờ tối đa và việc chờ có hết hạn hay không.
- **eventThread** và **stackTrace:** thread và vị trí thực hiện thao tác wait.

Không coi JavaMonitorWait là event thay thế cho JavaMonitorEnter. Một thread bị chặn khi vào synchronized được biểu diễn bằng JavaMonitorEnter; một thread chủ động gọi wait() được biểu diễn bằng JavaMonitorWait. Ví dụ, Thread.join() cũng có thể xuất hiện dưới dạng JavaMonitorWait vì implementation của nó dùng monitor wait.

### 2.3. ThreadPark: chờ qua LockSupport và AQS

Nhiều API đồng bộ không dùng intrinsic monitor trực tiếp. ReentrantLock, Semaphore và nhiều thành phần dựa trên AbstractQueuedSynchronizer có thể park thread bằng LockSupport.park().

**jdk.ThreadPark** thường có các trường:

- **duration:** thời gian thread bị park.
- **parkedClass:** class của đối tượng mà thread đang park.
- **eventThread:** thread bị park.
- **stackTrace:** đường gọi dẫn tới thao tác park.

Không phải mọi ThreadPark đều là lock contention. Thread có thể park để chờ công việc, chờ future, chờ queue hoặc đang idle trong một pool. Hãy đọc parkedClass và stack trace để biết thread đang chờ ReentrantLock, queue, scheduler hay một cơ chế khác.

## 3. Đọc event để xác định lock đang gây nghẽn

Khi tìm thấy event đáng chú ý, hãy xem đồng thời các trường sau:

1. **Duration:** thời gian chờ. Một event kéo dài 150 ms có thể ảnh hưởng đáng kể tới request nếu xảy ra trên đường xử lý chính.
2. **Event thread:** thread đang bị chặn hoặc park.
3. **Monitor class / parked class:** loại object hoặc cơ chế đồng bộ liên quan.
4. **Previous owner / notifier:** thread sở hữu monitor trước đó hoặc thread gửi notify, nếu event cung cấp.
5. **Stack trace:** vị trí code đang cố lấy lock hoặc thực hiện wait/park.
6. **Start time:** thời điểm xảy ra để đối chiếu với latency, throughput, log và workload.

Ví dụ một event:

~~~text
jdk.JavaMonitorEnter {
  startTime = 19:48:02.375
  duration = 102 ms
  monitorClass = java.lang.Object
  previousOwner = "monitor-owner-5" (javaThreadId = 59)
  eventThread = "monitor-waiter-5" (javaThreadId = 60)
  stackTrace = [
    LockProbe.lambda$monitorContention$1(CountDownLatch) line: 28
    java.lang.Thread.run() line: 1447
  ]
}
~~~

Đây là output minh họa từ thử nghiệm JDK 24.0.2. Thread monitor-waiter-5 đã chờ khoảng 102 ms để lấy monitor mà monitor-owner-5 đang giữ. Stack trace trỏ tới vị trí waiter cố vào vùng synchronized.

Không chỉ xem event có duration dài nhất. Hãy xem cả số lần xảy ra và tổng thời gian chờ. Một lock có hàng nghìn lần chờ 10–20 ms có thể gây ảnh hưởng tổng thể lớn hơn một lần chờ 200 ms. Khi so sánh, nhớ rằng JFR có thể loại bỏ event ngắn hơn threshold đang cấu hình.

## 4. Bắt đầu recording để phân tích lock contention

Xác định PID của JVM:

~~~sh
jcmd -l
~~~

Xem các tùy chọn recording mà JVM đích hỗ trợ:

~~~sh
jcmd <pid> help JFR.start
~~~

Bắt đầu một recording ngắn với cấu hình profile và hạ threshold cho các event đồng bộ:

~~~sh
jcmd <pid> JFR.start name=LockStudy settings=profile disk=true maxage=2m maxsize=64m jdk.JavaMonitorEnter#threshold=5ms jdk.JavaMonitorEnter#stackTrace=true jdk.JavaMonitorWait#threshold=5ms jdk.JavaMonitorWait#stackTrace=true jdk.ThreadPark#threshold=5ms jdk.ThreadPark#stackTrace=true
~~~

Ý nghĩa:

- **name=LockStudy:** đặt tên recording để sử dụng trong các lệnh check, dump và stop.
- **settings=profile:** dùng template profile để thu thập dữ liệu phân tích chi tiết.
- **disk=true:** cho phép ghi dữ liệu xuống disk trong lúc recording.
- **maxage=2m:** giới hạn tuổi dữ liệu lưu trên disk repository.
- **maxsize=64m:** giới hạn dung lượng dữ liệu lưu trên disk repository.
- **#threshold=5ms:** ghi event có thời gian từ ngưỡng 5 ms trở lên.
- **#stackTrace=true:** yêu cầu ghi stack trace cho event tương ứng.

Trong JDK 24, nhiều Java Application duration event mặc định chỉ được ghi khi thời gian vượt 20 ms. Template cụ thể có thể đặt ngưỡng khác; hãy kiểm tra cấu hình đang dùng. Hạ threshold giúp thu được nhiều lần chờ ngắn hơn, nhưng cũng làm recording lớn hơn và có thể tăng overhead. Chỉ hạ ngưỡng trong recording ngắn khi cần điều tra sâu, đồng thời theo dõi hiệu năng ứng dụng.

Kiểm tra recording:

~~~sh
jcmd <pid> JFR.check name=LockStudy
~~~

Dump dữ liệu hiện tại ra file:

~~~sh
jcmd <pid> JFR.dump name=LockStudy filename=lock-contention.jfr
~~~

Lệnh dump tạo file để phân tích; recording có thể tiếp tục chạy. Khi không cần thu thập nữa, dừng recording:

~~~sh
jcmd <pid> JFR.stop name=LockStudy
~~~

Nếu cần tự động kết thúc sau một khoảng thời gian, có thể thêm **duration=30s** vào lệnh JFR.start. Xem help của JVM đích để xác nhận các tùy chọn đang có.

## 5. Phân tích file bằng jfr CLI

Bắt đầu bằng summary:

~~~sh
jfr summary lock-contention.jfr
~~~

Summary cho biết thời lượng recording và số event từng loại. Kiểm tra xem file có chứa jdk.JavaMonitorEnter, jdk.JavaMonitorWait và jdk.ThreadPark hay không.

In các event đồng bộ:

~~~sh
jfr print --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.ThreadPark lock-contention.jfr
~~~

Chỉ in monitor contention:

~~~sh
jfr print --events jdk.JavaMonitorEnter lock-contention.jfr
~~~

Chỉ in thread park:

~~~sh
jfr print --events jdk.ThreadPark lock-contention.jfr
~~~

Khi đọc output:

- Tìm event có duration cao.
- Nhóm event theo monitorClass, parkedClass hoặc địa chỉ monitor.
- Xem thread nào thường xuyên bị chặn.
- Đọc stack trace để tìm phương thức và call path tạo contention.
- Đối chiếu previousOwner để tìm thread đã giữ monitor trước đó.
- Xem timestamp để đối chiếu với request chậm, batch job hoặc thời điểm traffic tăng.

Ví dụ ThreadPark của ReentrantLock có thể trông như sau:

~~~text
jdk.ThreadPark {
  startTime = 19:45:56.025
  duration = 121 ms
  parkedClass = java.util.concurrent.locks.ReentrantLock$NonfairSync
  eventThread = "reentrant-waiter-3"
  stackTrace = [
    jdk.internal.misc.Unsafe.park(boolean, long)
    java.util.concurrent.locks.LockSupport.park(Object)
    java.util.concurrent.locks.AbstractQueuedSynchronizer.acquire(...)
    java.util.concurrent.locks.ReentrantLock$Sync.lock()
  ]
}
~~~

Stack trace cho thấy thread đang park trong đường gọi của ReentrantLock. Hãy lần tiếp lên các frame thuộc ứng dụng để tìm vị trí gọi lock() và hiểu vì sao lock bị giữ lâu.

## 6. Phân tích bằng JDK Mission Control

JDK Mission Control (JMC) cung cấp giao diện đồ họa để xem recording. Mở file lock-contention.jfr và tập trung vào các khu vực sau:

| Khu vực | Cách sử dụng |
|---|---|
| Automated Analysis Results | Xem cảnh báo hoặc dấu hiệu contention mà JMC phát hiện |
| Threads / Contention | Xem thread bị block, lock liên quan và stack trace |
| Lock Instances | Xem lock instance xuất hiện trong contention và drill down vào thread/stack |
| Latencies | Xem loại event gây latency như monitor blocked, monitor wait hoặc thread park |
| Thread Timeline | Đối chiếu khoảng thời gian thread chạy, chờ, park hoặc bị block |

Trong Contention hoặc Lock Instances, ưu tiên các lock có tổng thời gian blocked cao, số lần contention lớn hoặc xuất hiện trên thread xử lý request quan trọng. Khi chọn một lock hoặc thread, xem stack trace để tìm phương thức đang chờ.

Để hiểu thread sở hữu lock đang làm gì, chọn thread owner trên timeline và đối chiếu các event/stack trace khác trong cùng thời gian. Stack trace của JavaMonitorEnter là stack của waiter; nó không tự động thay thế stack của owner.

## 7. Tìm nguyên nhân gốc từ stack trace

Sau khi xác định lock đáng chú ý, hãy lần từ frame thuộc ứng dụng lên call path và tìm đoạn code giữ lock. Các mẫu thường gặp:

### 7.1. Critical section quá dài

Một phương thức synchronized thực hiện nhiều phép tính hoặc duyệt collection lớn. Mọi thread cần cùng monitor phải chờ toàn bộ phần xử lý kết thúc.

Cách xử lý:

- Giữ trong critical section đúng thao tác cần bảo vệ.
- Tính toán dữ liệu độc lập trước khi lấy lock.
- Chuẩn bị dữ liệu bên ngoài lock rồi cập nhật trạng thái dùng chung trong khoảng ngắn.
- Không gọi callback tùy ý khi đang giữ lock nếu callback có thể chạy lâu hoặc lấy lock khác.

### 7.2. I/O hoặc logging bên trong lock

Ghi file, gọi database, network, remote service hoặc logging đồng bộ có thể mất nhiều thời gian. Nếu các thao tác này chạy khi đang giữ monitor, các thread khác phải chờ I/O hoàn tất.

Cách xử lý:

- Thu thập dữ liệu cần ghi khi giữ lock, sau đó nhả lock trước khi thực hiện I/O nếu tính đúng đắn cho phép.
- Dùng queue và worker riêng cho thao tác I/O có thể xử lý bất đồng bộ.
- Tránh gọi remote service hoặc ghi log có thể block trong critical section.
- Kiểm tra lock có đang bao quanh thao tác logging chung hay không.

### 7.3. Một global lock bảo vệ quá nhiều dữ liệu

Một static synchronized hoặc một monitor toàn cục có thể khiến các request không liên quan phải xếp hàng cùng nhau.

Cách xử lý:

- Chia lock theo phạm vi dữ liệu khi có thể.
- Dùng cấu trúc dữ liệu concurrent phù hợp với kiểu truy cập.
- Cân nhắc partition/sharding để các nhóm dữ liệu độc lập không tranh cùng một lock.
- Đánh giá tính nhất quán và thứ tự cập nhật trước khi thay đổi cơ chế đồng bộ.

### 7.4. Thread giữ lock trong khi chờ tài nguyên khác

Một thread giữ lock A rồi chờ lock B, database hoặc network có thể khiến nhiều thread khác bị chặn ở A. Nhiều lớp lock lồng nhau còn tạo nguy cơ deadlock nếu các thread lấy lock theo thứ tự khác nhau.

Cách xử lý:

- Chuẩn hóa thứ tự lấy nhiều lock.
- Không chờ I/O hoặc future trong khi giữ lock dùng chung.
- Tránh gọi code bên ngoài module khi vẫn đang giữ lock nội bộ.
- Đặt timeout hoặc cơ chế hủy phù hợp cho thao tác có thể chờ lâu.

### 7.5. Contention do thiết kế logging hoặc cache

Logging đồng bộ dùng chung appender, cache có một lock toàn cục hoặc registry cập nhật thường xuyên có thể trở thành bottleneck bất ngờ.

Cách xử lý:

- Xem lock instance và stack trace để xác định component.
- Đo lại sau khi chuyển sang logging bất đồng bộ hoặc cấu trúc cache phù hợp.
- Kiểm tra giới hạn queue và chính sách backpressure khi dùng bất đồng bộ.
- Không chỉ đổi synchronized thành ReentrantLock mà không thay đổi phạm vi hoặc thời gian giữ lock; thay loại lock không tự loại bỏ contention.

## 8. Phân biệt contention, wait, sleep, park và deadlock

| Trạng thái / event | Điều thread đang làm | Cách kiểm tra |
|---|---|---|
| JavaMonitorEnter | Đang chờ lấy monitor | Xem monitor class, previous owner, duration và stack |
| JavaMonitorWait | Đang chờ notify/timeout trong Object.wait hoặc API dùng monitor wait | Xem notifier, timeout, timedOut và stack |
| ThreadPark | Đang park qua LockSupport hoặc cơ chế dùng nó | Xem parked class và stack trace |
| ThreadSleep | Đang ngủ theo yêu cầu của code | Xem nơi gọi sleep và thời lượng |
| SocketRead / FileRead | Đang chờ I/O | Xem remote endpoint/file và duration |
| Deadlock | Các thread chờ lock theo chu trình, không thể tiến triển | Dùng thread dump và kiểm tra deadlock report |

JFR duration event thường chỉ xuất hiện sau khi thao tác kết thúc. Nếu một thread bị deadlock và không bao giờ lấy được monitor, không nên chờ một event JavaMonitorEnter hoàn chỉnh mới điều tra. Lấy thread dump để xem toàn bộ trạng thái chờ và quan hệ lock.

Chạy thread dump:

~~~sh
jcmd <pid> Thread.print
~~~

Để in thêm thông tin về các lock thuộc java.util.concurrent:

~~~sh
jcmd <pid> Thread.print -l
~~~

Trong thread dump, tìm thông báo deadlock nếu JVM phát hiện được, thread state, lock đang chờ, lock đang sở hữu và stack trace của các thread liên quan. JFR và thread dump bổ sung cho nhau: recording cho timeline và thời lượng; thread dump cho snapshot trạng thái tại thời điểm lấy.

## 9. Ví dụ Java 17+ tạo lock contention

Chương trình dưới đây tạo hai kiểu contention có kiểm soát:

- Nhiều thread tranh cùng một intrinsic monitor qua synchronized.
- Nhiều thread tranh cùng một ReentrantLock, thường đi qua LockSupport.park và AQS.

Tạo file LockProbe.java:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.ReentrantLock;

public class LockProbe {
    private static final Object monitor = new Object();
    private static final ReentrantLock reentrant = new ReentrantLock();

    public static void main(String[] args) throws Exception {
        System.out.println("lock-probe-ready");

        for (int i = 0; i < 20; i++) {
            monitorContention(i);
            reentrantContention(i);
        }

        Thread.sleep(30_000);
    }

    private static void monitorContention(int round) throws Exception {
        CountDownLatch held = new CountDownLatch(1);

        Thread owner = new Thread(() -> {
            synchronized (monitor) {
                held.countDown();
                sleep(100);
            }
        }, "monitor-owner-" + round);

        Thread waiter = new Thread(() -> {
            await(held);
            synchronized (monitor) {
                // Chờ lấy monitor rồi thoát critical section.
            }
        }, "monitor-waiter-" + round);

        owner.start();
        waiter.start();
        owner.join();
        waiter.join();
    }

    private static void reentrantContention(int round) throws Exception {
        CountDownLatch held = new CountDownLatch(1);

        Thread owner = new Thread(() -> {
            reentrant.lock();
            try {
                held.countDown();
                sleep(100);
            } finally {
                reentrant.unlock();
            }
        }, "reentrant-owner-" + round);

        Thread waiter = new Thread(() -> {
            await(held);
            reentrant.lock();
            try {
                // Lấy lock rồi thoát critical section.
            } finally {
                reentrant.unlock();
            }
        }, "reentrant-waiter-" + round);

        owner.start();
        waiter.start();
        owner.join();
        waiter.join();
    }

    private static void sleep(long ms) {
        try {
            Thread.sleep(ms);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    private static void await(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
~~~

Biên dịch bằng Java 17 trở lên:

~~~sh
mkdir -p out
javac --release 17 -d out LockProbe.java
~~~

Chạy chương trình:

~~~sh
java -Xms128m -Xmx128m -cp out LockProbe
~~~

Stdout chính xác khi chương trình khởi động:

~~~text
lock-probe-ready
~~~

Giữ terminal này mở. Chương trình tạo contention trong vài giây rồi giữ JVM chạy thêm 30 giây để bạn có thời gian lấy recording. Mở terminal thứ hai, tìm PID:

~~~sh
jcmd -l
~~~

Giả sử PID là 49060. Bắt đầu recording:

~~~sh
jcmd 49060 JFR.start name=LockStudy settings=profile disk=true maxage=2m maxsize=64m jdk.JavaMonitorEnter#threshold=5ms jdk.JavaMonitorWait#threshold=5ms jdk.ThreadPark#threshold=5ms
~~~

Kiểm tra và dump:

~~~sh
jcmd 49060 JFR.check name=LockStudy
jcmd 49060 JFR.dump name=LockStudy filename=lock-study.jfr
~~~

Đọc các event:

~~~sh
jfr summary lock-study.jfr
jfr print --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.ThreadPark lock-study.jfr
~~~

Dừng recording:

~~~sh
jcmd 49060 JFR.stop name=LockStudy
~~~

Trong thử nghiệm với JDK 24.0.2, chương trình biên dịch bằng javac --release 17 và in chính xác lock-probe-ready. Recording profile tạo thành công và chứa cả JavaMonitorEnter, JavaMonitorWait và ThreadPark event. Một monitor contention event kéo dài khoảng 102 ms, ghi nhận previousOwner=monitor-owner-5 và stack trace tới LockProbe.monitorContention. Một ThreadPark event của ReentrantLock kéo dài khoảng 100 ms, với stack trace qua LockSupport.park và AbstractQueuedSynchronizer.acquire. Số event và thời lượng thay đổi theo máy và thời điểm bắt đầu recording.

Khi hoàn tất, JVM tự kết thúc sau khoảng 30 giây. Nếu muốn dừng sớm, quay lại terminal chạy chương trình và nhấn Ctrl+C.

## 10. Kiểm chứng hiệu quả sau khi tối ưu

Sau khi thay đổi code, hãy ghi một recording mới với cùng template, threshold, thời lượng và workload tương đương. So sánh trước/sau:

| Chỉ số | Cần quan sát |
|---|---|
| Số JavaMonitorEnter event | Số lần contention được ghi nhận ở cùng threshold |
| Tổng thời gian blocked | Tổng thời gian các thread bị chặn trong tập event đã ghi |
| Duration lớn nhất / phân bố duration | Các lần chờ dài đã giảm chưa |
| Lock instance xuất hiện nhiều nhất | Lock gây nghẽn trước đó còn là bottleneck không |
| Thread và stack trace | Thread xử lý request còn chờ ở cùng vị trí không |
| Request latency và throughput | Người dùng có nhận được cải thiện thực tế không |
| CPU và I/O | Bottleneck có chuyển sang CPU, network hoặc database không |

Không chỉ dựa vào số event để kết luận. Nếu threshold là 5 ms, các lần chờ ngắn hơn ngưỡng có thể không xuất hiện trong recording. Hãy giữ nguyên threshold khi so sánh để phép đo có ý nghĩa. Kết hợp JFR với metric ứng dụng và benchmark có workload tương đương.

Nếu contention giảm nhưng latency không cải thiện, hãy kiểm tra bottleneck khác như I/O, GC hoặc CPU. Một ứng dụng có thể đồng thời có nhiều bottleneck.

## 11. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không thấy JavaMonitorEnter | Không có monitor contention vượt threshold hoặc event bị tắt | Kiểm tra event setting, hạ threshold trong recording ngắn và tái hiện workload |
| Chỉ thấy một vài event | Phần lớn thời gian chờ ngắn hơn threshold | Kiểm tra template/threshold và thử ngưỡng thấp hơn trong thời gian ngắn |
| Thấy nhiều JavaMonitorWait nhưng không thấy monitor blocked | Thread đang dùng Object.wait hoặc Thread.join | Đọc stack trace và trường notifier/timeout để phân biệt với JavaMonitorEnter |
| Thấy nhiều ThreadPark | Thread đang park trong AQS, queue, future hoặc pool | Xem parkedClass và stack trace; không coi mọi park là lock contention |
| Event có duration dài nhưng không rõ owner | Stack trace thuộc waiter; event chỉ cung cấp previousOwner | Đối chiếu thread owner trên JMC timeline hoặc lấy thread dump |
| Không có event cho deadlock | Thread chưa bao giờ lấy lại được lock nên duration event có thể chưa kết thúc | Chạy jcmd <pid> Thread.print -l và kiểm tra chu trình lock |
| Recording quá nhiều event | Threshold quá thấp hoặc thời gian recording quá dài | Tăng threshold, giới hạn duration/maxage/maxsize và chỉ bật event cần thiết |
| Không attach được vào JVM | PID sai, khác user hoặc attach bị vô hiệu hóa | Kiểm tra PID, quyền truy cập và cấu hình JVM |
| Contention vẫn còn sau khi đổi loại lock | Phạm vi critical section và thời gian giữ lock không thay đổi | Giảm thời gian giữ lock hoặc thay đổi thiết kế chia sẻ tài nguyên |

## 12. Quy trình điều tra lock contention

1. Xác định triệu chứng bằng latency, throughput và thread state.
2. Xác định JVM/PID bằng jcmd -l.
3. Bắt đầu JFR recording với event monitor/park và threshold phù hợp.
4. Tái hiện workload hoặc thu recording trong khoảng thời gian có vấn đề.
5. Dump file và kiểm tra bằng jfr summary.
6. Lọc JavaMonitorEnter, JavaMonitorWait và ThreadPark.
7. Nhóm theo lock/monitor, xem duration, thread, owner và stack trace.
8. Dùng JMC Contention/Lock Instances để drill down vào lock gây nghẽn.
9. Kiểm tra code giữ lock, I/O trong critical section, lock lồng nhau và cấu trúc dữ liệu dùng chung.
10. Nếu nghi deadlock, lấy jcmd <pid> Thread.print -l ngay.
11. Sửa nguyên nhân và đo lại với cùng workload/recording settings.
12. Xác nhận cả contention lẫn latency/throughput đã cải thiện.

### Checklist

- [ ] Đã xác định đúng JVM/PID.
- [ ] Đã bật các event đồng bộ cần thiết.
- [ ] Đã hiểu threshold và giới hạn event được ghi.
- [ ] Đã phân biệt JavaMonitorEnter, JavaMonitorWait và ThreadPark.
- [ ] Đã xác định thread waiter và lock/monitor liên quan.
- [ ] Đã đọc stack trace và đối chiếu previousOwner khi có.
- [ ] Đã kiểm tra critical section có I/O hoặc logging hay không.
- [ ] Đã phân biệt contention thông thường với deadlock.
- [ ] Đã dùng JMC hoặc jfr CLI để phân tích recording.
- [ ] Đã so sánh trước/sau bằng cùng workload và threshold.
- [ ] Đã xác nhận latency và throughput thực tế cải thiện.

JFR giúp xác định thread nào phải chờ, chờ lock nào và thời gian chờ xuất hiện ở call path nào. Khi phân biệt đúng JavaMonitorEnter, JavaMonitorWait và ThreadPark, rồi đối chiếu owner, stack trace và thread timeline, bạn có thể tìm critical section gây nghẽn, sửa nguyên nhân và xác nhận hiệu quả bằng recording trước/sau.

## Tài liệu tham khảo

- [Oracle JDK 24 — Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- [Oracle JDK 24 — The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- [Oracle JDK 24 — The jfr Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jfr.html)
- [Oracle JDK 24 — JFR Event API](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/jdk/jfr/Event.html)
- [Oracle — Java Mission Control and Flight Recorder Demo Series](https://www.oracle.com/webfolder/technetwork/tutorials/obe/java/mc-jfr/index.html)