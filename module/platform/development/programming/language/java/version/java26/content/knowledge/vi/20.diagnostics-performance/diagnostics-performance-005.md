# Thông tin chủ sở hữu park blocker trong thread dump

Khi một thread chờ lấy khóa, stack trace thường cho biết thread đang dừng tại LockSupport.park() hoặc một phương thức của AbstractQueuedSynchronizer. Trước đây, thread dump do một số công cụ HotSpot tạo ra có thể cho biết object khiến thread park nhưng không hiển thị trực tiếp thread đang sở hữu object đó. JDK 26 cải thiện thông tin này: thread dump từ HotSpotDiagnosticMXBean.dumpThreads() và lệnh jcmd Thread.dump_to_file có thể ghi thêm owner thread ID của park blocker nếu blocker là một AbstractOwnableSynchronizer.

Thông tin này giúp lần theo quan hệ chờ khóa: tìm thread đang đợi, lấy ID owner từ dump, rồi tìm stack trace của owner để biết nó đang giữ khóa trong đoạn xử lý nào. Đây là cải tiến chẩn đoán của HotSpot, không phải API ngôn ngữ mới hay preview feature. Thay đổi được ghi nhận trong JDK-8365057; nó cũng đã được backport vào JDK 25.0.4.

## 1. Park blocker là gì?

LockSupport cung cấp các phương thức park() để tạm dừng thread cho đến khi có permit, có lời gọi unpark(), thread bị interrupt hoặc park() tự trả về không theo một lý do cụ thể. Vì vậy, code dùng park() phải kiểm tra lại điều kiện trong vòng lặp. Các overload nhận tham số blocker cho phép bên gọi gắn một object giải thích vì sao thread đang park:

~~~java
LockSupport.park(blocker);
LockSupport.parkNanos(blocker, nanos);
LockSupport.parkUntil(blocker, deadline);
~~~

Object truyền vào được ghi nhận như park blocker trong lúc thread bị park. Có thể xem blocker hiện tại của một thread bằng:

~~~java
Object blocker = LockSupport.getBlocker(thread);
~~~

getBlocker() chỉ trả về object blocker. Nó không tự cung cấp thread ID của chủ sở hữu object.

Các thư viện đồng bộ hóa như ReentrantLock thường dùng LockSupport.park(this) bên trong cơ chế chờ. Trong trường hợp đó, blocker thường là synchronizer object quản lý hàng đợi chờ khóa.

Một thread đang park thường ở trạng thái WAITING hoặc TIMED_WAITING. Điều này khác với BLOCKED, là trạng thái thread đang chờ vào một intrinsic monitor do synchronized quản lý.

## 2. AbstractOwnableSynchronizer lưu thông tin chủ sở hữu thế nào?

java.util.concurrent.locks.AbstractOwnableSynchronizer là lớp cơ sở cho synchronizer có thể được sở hữu độc quyền bởi một thread. Lớp này cung cấp hai phương thức protected:

- setExclusiveOwnerThread(Thread): ghi nhận thread đang sở hữu quyền truy cập độc quyền; truyền null để xóa owner.
- getExclusiveOwnerThread(): đọc thread được ghi nhận là owner gần nhất.

Bản thân AbstractOwnableSynchronizer không tự quản lý trạng thái khóa. Lớp con và công cụ chẩn đoán sử dụng thông tin owner do implementation cập nhật. Tài liệu AbstractQueuedSynchronizer khuyến khích implementation duy trì owner để công cụ monitoring và diagnostics có thể xác định thread giữ khóa.

ReentrantLock là ví dụ phổ biến. Nó dùng synchronizer dựa trên AbstractQueuedSynchronizer và ghi nhận thread đã lấy khóa. Khi một thread khác gọi lock() trong lúc khóa đang được giữ, thread chờ có thể park với synchronizer làm blocker. Thread dump JDK 26 có thể hiển thị owner ID của synchronizer đó.

Không phải mọi object được truyền vào LockSupport.park() đều là AbstractOwnableSynchronizer. Nếu blocker là một object thông thường, Condition hoặc một synchronizer không ghi nhận owner độc quyền, dump có thể chỉ hiển thị blocker mà không có owner.

## 3. Chính xác thay đổi nào có trong JDK 26?

JDK-8365057 bổ sung thông tin owner của park blocker cho hai nguồn thread dump:

| Nguồn dump | JDK 26 có owner của park blocker? | Ghi chú |
|---|---|---|
| HotSpotDiagnosticMXBean.dumpThreads() | Có | Có thể xuất plain text hoặc JSON |
| jcmd <pid> Thread.dump_to_file | Có | Có thể xuất plain text hoặc JSON |
| ThreadMXBean / ThreadInfo | Đã có API đọc owner từ trước | getLockOwnerId() và getLockOwnerName() không phải API mới của JDK 26 |
| Công cụ thread dump khác | Phụ thuộc công cụ và phiên bản | Không mặc định mọi công cụ đều có cùng định dạng |

Đây là cải tiến đầu ra chẩn đoán. Không có thay đổi cú pháp Java cần bật bằng --enable-preview. Ứng dụng không cần sửa code khóa để dùng ReentrantLock chuẩn của JDK.

Về phiên bản:

- JDK 26 có thay đổi này trong release chính.
- JDK 25.0.4 đã nhận backport của JDK-8365057.
- JDK 25.0.3 trở về trước không có bảo đảm từ bản sửa này.
- Với bản phân phối JDK của nhà cung cấp khác, hãy kiểm tra release notes của build cụ thể để xác nhận backport.

## 4. Đọc owner trong plain-text thread dump

Dùng jcmd để yêu cầu JVM tạo dump ra file:

~~~powershell
jcmd -l
jcmd <pid> Thread.dump_to_file -format=plain C:\dumps\threads.txt
~~~

Thay <pid> bằng process ID của JVM cần kiểm tra. Chạy jcmd trên cùng máy với JVM và bằng cùng effective user/group đã khởi chạy JVM. Thư mục đích phải tồn tại và file đích chưa được tạo. Nếu cần ghi đè file cũ, có thể dùng tùy chọn -overwrite=true.

Một phần output minh họa:

~~~text
"lock-waiter" #24 WAITING
    at java.base/jdk.internal.misc.Unsafe.park(Native Method)
    at java.base/java.util.concurrent.locks.LockSupport.park(LockSupport.java:...)
    at java.base/java.util.concurrent.locks.AbstractQueuedSynchronizer.acquire(...)
    - parking to wait for <java.util.concurrent.locks.ReentrantLock$NonfairSync@4a12bc>, owner #23
    at java.base/java.util.concurrent.locks.ReentrantLock.lock(...)
    at example.ParkBlockerOwnerDemo.lambda$main$1(ParkBlockerOwnerDemo.java:...)
~~~

Cách đọc:

- lock-waiter là thread đang chờ.
- WAITING cho biết thread đang chờ được đánh thức.
- ReentrantLock$NonfairSync là blocker object của lần park.
- owner #23 cho biết thread có ID 23 đang được ghi nhận là chủ sở hữu độc quyền của synchronizer.
- Tìm thread có ID #23 trong cùng dump để xem stack trace của owner.

ID owner trong dòng plain text là Java thread ID, không phải PID của tiến trình và cũng không phải native OS thread ID.

Nếu không có phần owner #..., dump vẫn có thể hiển thị park blocker. Điều đó xảy ra khi blocker không phải AbstractOwnableSynchronizer hoặc synchronizer không cung cấp thông tin owner độc quyền.

## 5. Đọc owner trong JSON thread dump

JSON phù hợp khi cần tự động phân tích hoặc tích hợp dữ liệu chẩn đoán vào công cụ nội bộ:

~~~powershell
jcmd <pid> Thread.dump_to_file -format=json C:\dumps\threads.json
~~~

Một phần object thread minh họa theo schema JDK 26:

~~~json
{
  "tid": "24",
  "time": "2026-11-27T16:00:00Z",
  "name": "lock-waiter",
  "state": "WAITING",
  "parkBlocker": {
    "object": "java.util.concurrent.locks.ReentrantLock$NonfairSync@4a12bc",
    "owner": "23"
  },
  "stack": [
    "java.base/jdk.internal.misc.Unsafe.park(Native Method)",
    "java.base/java.util.concurrent.locks.LockSupport.park(LockSupport.java:...)",
    "java.base/java.util.concurrent.locks.AbstractQueuedSynchronizer.acquire(...)"
  ]
}
~~~

Trong schema JSON JDK 26:

| Trường | Ý nghĩa |
|---|---|
| threads[].tid | Java thread ID |
| threads[].name | Tên thread |
| threads[].state | Trạng thái thread |
| threads[].parkBlocker.object | Identity string của blocker object |
| threads[].parkBlocker.owner | Thread ID của exclusive owner nếu blocker là AbstractOwnableSynchronizer và owner được ghi nhận |
| threads[].stack | Stack trace, phần tử đầu là frame trên cùng |

Điểm cần chú ý:

- owner là trường tùy chọn nằm bên trong parkBlocker.
- Trong schema JDK 26, tid và parkBlocker.owner được biểu diễn dưới dạng chuỗi.
- parkBlocker.object là identity string để chẩn đoán, không phải định danh ổn định để lưu lâu dài hoặc dùng làm khóa nghiệp vụ.
- JSON còn có trường owner ở cấp threadContainers để mô tả thread sở hữu một thread container. Trường đó khác với threads[].parkBlocker.owner, vốn là chủ sở hữu synchronizer.
- Schema và các trường tùy chọn có thể tiến hóa giữa các JDK. Parser nên bỏ qua trường không biết và xử lý trường owner như dữ liệu tùy chọn.

Không viết parser giả định mọi thread WAITING đều có parkBlocker hoặc mọi parkBlocker đều có owner.

## 6. Tạo dump bằng HotSpotDiagnosticMXBean

Có thể tạo thread dump từ bên trong ứng dụng hoặc qua JMX bằng HotSpotDiagnosticMXBean:

~~~java
import com.sun.management.HotSpotDiagnosticMXBean;
import java.lang.management.ManagementFactory;
import java.nio.file.Path;

public class ThreadDumpWriter {

    public static void writeJsonDump() throws Exception {
        HotSpotDiagnosticMXBean bean =
                ManagementFactory.getPlatformMXBean(
                        HotSpotDiagnosticMXBean.class);

        if (bean == null) {
            throw new IllegalStateException(
                    "HotSpotDiagnosticMXBean is unavailable");
        }

        Path output = Path.of("threads.json").toAbsolutePath();

        bean.dumpThreads(
                output.toString(),
                HotSpotDiagnosticMXBean.ThreadDumpFormat.JSON);
    }
}
~~~

Nếu ứng dụng dùng named module, module-info.java cần đọc module jdk.management:

~~~java
module example.app {
    requires jdk.management;
}
~~~

Lưu ý:

- outputFile phải là đường dẫn tuyệt đối.
- File đích phải chưa tồn tại.
- Phương thức có thể ném IOException.
- Implementation mặc định của MXBean có thể ném UnsupportedOperationException nếu runtime không hỗ trợ thao tác này.
- Đây là extension quản trị của HotSpot, không phải API portable cho mọi JVM implementation.

ThreadDumpFormat có hai lựa chọn: TEXT_PLAIN và JSON. Cả hai định dạng đều được bổ sung thông tin owner của park blocker trong implementation JDK 26 có thay đổi JDK-8365057.

## 7. Ví dụ tái hiện một thread đang chờ ReentrantLock

Ví dụ sau tạo hai thread: lock-owner lấy khóa rồi chờ tín hiệu; lock-waiter cố lấy cùng khóa và phải park. Chương trình in PID và giữ trạng thái đủ lâu để có thể chụp dump từ terminal khác.

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public class ParkBlockerOwnerDemo {

    private static final ReentrantLock LOCK = new ReentrantLock();
    private static final CountDownLatch OWNER_HAS_LOCK =
            new CountDownLatch(1);
    private static final CountDownLatch RELEASE_OWNER =
            new CountDownLatch(1);

    public static void main(String[] args) throws InterruptedException {
        Thread owner = Thread.ofPlatform()
                .name("lock-owner")
                .start(() -> {
                    LOCK.lock();
                    try {
                        OWNER_HAS_LOCK.countDown();
                        RELEASE_OWNER.await();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    } finally {
                        LOCK.unlock();
                    }
                });

        OWNER_HAS_LOCK.await();

        Thread waiter = Thread.ofPlatform()
                .name("lock-waiter")
                .start(() -> {
                    LOCK.lock();
                    try {
                        System.out.println("waiter acquired lock");
                    } finally {
                        LOCK.unlock();
                    }
                });

        System.out.println(
                "PID=" + ProcessHandle.current().pid());
        System.out.println(
                "Capture a thread dump during the next 90 seconds.");

        try {
            Thread.sleep(TimeUnit.SECONDS.toMillis(90));
        } finally {
            RELEASE_OWNER.countDown();
        }

        owner.join();
        waiter.join();
    }
}
~~~

Chạy chương trình:

~~~powershell
javac ParkBlockerOwnerDemo.java
java ParkBlockerOwnerDemo
~~~

Mở terminal thứ hai và dùng PID mà chương trình in ra:

~~~powershell
jcmd <pid> Thread.dump_to_file -format=plain C:\dumps\park-blocker.txt
~~~

Trong dump, tìm lock-waiter. Dòng parking to wait for sẽ chỉ ra synchronizer object và owner ID. Tìm lock-owner theo ID đó để xem thread đang giữ khóa thực hiện công việc gì.

Sau khoảng 90 giây, chương trình tự giải phóng latch; lock-owner nhả khóa và lock-waiter có thể tiếp tục. Nếu muốn quan sát lâu hơn, tăng thời gian chờ trong ví dụ.

## 8. Dùng ThreadInfo để lấy owner bằng code

ThreadInfo đã có getLockOwnerId() và getLockOwnerName() từ các phiên bản Java trước. JDK 26 không thêm hai phương thức này; thay đổi mới là đưa thông tin tương tự vào hai dạng thread dump nói trên.

Ví dụ đọc thông tin của các platform thread:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;

public class LockOwnerInspector {

    public static void printOwners() {
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();

        for (long threadId : bean.getAllThreadIds()) {
            ThreadInfo info = bean.getThreadInfo(threadId);

            if (info == null) {
                continue;
            }

            long ownerId = info.getLockOwnerId();

            if (ownerId >= 0) {
                System.out.printf(
                        "thread=%s waitsOn=%s owner=%s ownerId=%d%n",
                        info.getThreadName(),
                        info.getLockName(),
                        info.getLockOwnerName(),
                        ownerId);
            }
        }
    }
}
~~~

getLockOwnerId() trả về -1 nếu thread không chờ một object có owner hoặc owner không được xác định. getLockInfo() cho biết object mà thread đang chờ. Với trường hợp LockSupport.park(), object này là blocker do LockSupport.getBlocker() trả về.

Giới hạn của ThreadMXBean trong JDK 26:

- ThreadMXBean quản lý platform threads; không cung cấp monitoring và management cho virtual threads.
- getAllThreadIds() và dumpAllThreads() chỉ liệt kê platform threads.
- getLockOwnerId() có thể phản ánh owner của object mà thread đang park chờ, nhưng không biến ThreadMXBean thành bộ thu thập đầy đủ virtual thread dump.
- Khi cần quan sát toàn bộ virtual thread, ưu tiên jcmd Thread.dump_to_file.

## 9. Phân biệt park blocker với monitor và các dạng chờ khác

Không phải mọi thread chờ đều sử dụng park blocker. Hãy phân biệt:

| Trạng thái/tình huống | Cơ chế | Thông tin thường xem |
|---|---|---|
| BLOCKED | Chờ vào synchronized monitor | Object monitor và stack frame tại điểm tranh chấp |
| WAITING do Object.wait() | Chờ notify/notifyAll hoặc interrupt | Object đang chờ và stack trace |
| WAITING do LockSupport.park() | Chờ permit/unpark hoặc điều kiện khác | parkBlocker object; owner nếu đủ điều kiện |
| TIMED_WAITING do parkNanos/parkUntil | Park có thời hạn | parkBlocker và stack trace |
| WAITING do CountDownLatch.await() | AQS shared synchronization | Blocker có thể là synchronizer, nhưng không nhất thiết có exclusive owner |
| WAITING do Condition.await() | Chờ tín hiệu Condition | Blocker có thể là ConditionObject; không mặc định có owner |

Dòng owner mới không có nghĩa JVM đã thêm owner cho mọi monitor hoặc mọi loại chờ. JDK-8365057 tập trung vào thread park trên object thuộc AbstractOwnableSynchronizer.

Một số synchronizer dùng shared mode, ví dụ Semaphore hoặc read lock. Nhiều thread có thể cùng được phép truy cập nên không có một exclusive owner duy nhất để ghi vào trường owner. Việc thiếu owner trong trường hợp đó không phải bằng chứng dump bị lỗi.

## 10. Quy trình điều tra khi có nhiều thread chờ cùng một khóa

Khi một ứng dụng bị treo hoặc độ trễ tăng vì tranh chấp khóa, có thể làm theo quy trình sau:

1. Tạo dump JSON hoặc plain text bằng jcmd Thread.dump_to_file.
2. Tìm các thread có trạng thái WAITING/TIMED_WAITING và có parkBlocker.
3. Ghi nhận identity string của blocker và owner ID nếu có.
4. Gom các thread cùng chờ một blocker object để xác định điểm tranh chấp tập trung.
5. Tìm thread có tid trùng owner ID.
6. Đọc stack trace của owner để xác định nó đang chạy CPU, chờ I/O, gọi database, gọi dịch vụ từ xa hay chờ một khóa khác.
7. Tìm các waiter khác đang chờ cùng owner hoặc cùng synchronizer.
8. Chụp thêm dump sau một khoảng thời gian để xem owner có thay đổi và waiter có tiến triển hay không.
9. Nếu owner đang chờ một khóa khác, lần theo owner của blocker tiếp theo để dựng chuỗi chờ.
10. Kiểm tra mã nguồn quanh vùng lấy/nhả khóa, đặc biệt try/finally, lock ordering và các thao tác I/O trong critical section.

Ví dụ một tình huống thường gặp:

~~~text
request-1  --park--> ReentrantLock A --owner--> worker-7
request-2  --park--> ReentrantLock A --owner--> worker-7
request-3  --park--> ReentrantLock A --owner--> worker-7

worker-7 đang giữ A và chờ database response.
~~~

Trong tình huống này, owner ID cho thấy nhiều request đang chờ cùng worker-7. Nếu worker-7 giữ khóa trong khi chờ database, thời gian I/O có thể làm toàn bộ waiter bị kéo dài. Hãy đánh giá xem có thể thu hẹp critical section, tách I/O ra khỏi vùng giữ khóa hoặc thay đổi mô hình đồng bộ hay không.

Không kết luận deadlock chỉ vì nhiều thread cùng park trên một lock. Owner có thể đang xử lý hợp lệ và sẽ nhả khóa sau đó.

## 11. Kết hợp với phát hiện deadlock

Thông tin owner giúp lần theo quan hệ chờ nhưng bản thân nó không chứng minh có chu trình deadlock. Một thread giữ khóa lâu có thể gây contention nghiêm trọng mà không tạo deadlock.

Có thể kiểm tra deadlock của platform threads bằng ThreadMXBean:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.util.Arrays;

ThreadMXBean bean = ManagementFactory.getThreadMXBean();

if (bean.isSynchronizerUsageSupported()) {
    long[] deadlocked = bean.findDeadlockedThreads();

    if (deadlocked == null) {
        System.out.println("No platform-thread deadlock detected");
    } else {
        System.out.println(
                "Deadlocked platform thread IDs: " +
                Arrays.toString(deadlocked));
    }
}
~~~

findDeadlockedThreads() phát hiện chu trình chờ trên object monitors và ownable synchronizers. findMonitorDeadlockedThreads() chỉ kiểm tra object monitors.

Giới hạn quan trọng: ThreadMXBean trong JDK 26 không giám sát virtual threads và các phương thức phát hiện deadlock này không tìm được chu trình có virtual thread. Vì vậy, với ứng dụng dùng nhiều virtual thread, hãy kết hợp thread dump đầy đủ từ jcmd, quan sát tiến trình qua nhiều lần chụp và công cụ giám sát khác. Không dùng kết quả null từ ThreadMXBean để kết luận chắc chắn toàn bộ JVM không có deadlock.

## 12. Các giới hạn cần hiểu đúng

Thông tin owner là dữ liệu chẩn đoán tại thời điểm lấy snapshot, không phải cam kết đồng bộ để điều khiển ứng dụng.

- Owner có thể nhả khóa ngay sau khi dump được chụp.
- Thread ID có thể không còn xuất hiện nếu thread kết thúc trong lúc thu thập hoặc dump không chứa thread đó.
- Nếu implementation synchronizer không ghi nhận exclusive owner bằng setExclusiveOwnerThread(), công cụ không có owner để hiển thị.
- Blocker object identity string không phải ID ổn định giữa các lần chạy.
- Một thread có thể park vì lý do khác ngoài tranh chấp khóa độc quyền.
- Một owner đang WAITING không tự động là lỗi; cần xem nó đang chờ điều kiện nào.
- Thread dump là dữ liệu quan sát, không nên được dùng để quyết định thread nào được phép gọi unlock().

Với thread dump cho virtual threads, tài liệu JDK lưu ý snapshot có thể không nhất quán theo một thời điểm duy nhất và không thực hiện deadlock detection. Mỗi thread có timestamp riêng; hãy đối chiếu nhiều dump nếu cần xác định một trạng thái kéo dài.

## 13. Các lỗi thường gặp khi đọc park blocker owner

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Có parkBlocker nhưng không có owner | Blocker không phải AbstractOwnableSynchronizer hoặc không có exclusive owner | Xem loại blocker và API của synchronizer |
| Owner ID không tìm thấy trong dump | Thread đã kết thúc, dump thiếu thread hoặc trạng thái thay đổi trong lúc thu thập | Chụp lại dump và kiểm tra threadCount/virtual thread coverage |
| Nhiều waiter có cùng owner | Một thread giữ synchronizer trong lúc nhiều thread chờ | Kiểm tra stack trace owner và thời gian giữ khóa |
| Owner không tiến triển | Owner đang chờ I/O, khóa khác hoặc điều kiện không được phát tín hiệu | Lần theo stack của owner và chuỗi blocker tiếp theo |
| Không có owner cho Semaphore | Semaphore dùng shared acquisition, không có một exclusive owner duy nhất | Kiểm tra producer/consumer và trạng thái permit |
| Không thấy virtual thread trong ThreadMXBean | ThreadMXBean chỉ hỗ trợ platform threads | Dùng jcmd Thread.dump_to_file |
| JSON parser không tìm thấy owner | Đọc nhầm threads[].owner thay vì threads[].parkBlocker.owner | Theo schema và đọc đúng cấp object |
| Parser lỗi khi field owner vắng mặt | owner là trường tùy chọn | Xử lý null/absent và không giả định mọi blocker có owner |
| Thread đang BLOCKED nhưng không có parkBlocker | Đang tranh chấp intrinsic monitor, không phải LockSupport park | Xem blockedOn/monitor information |
| Kết luận deadlock từ một dump | Owner có thể vẫn đang xử lý và sẽ nhả khóa | Chụp nhiều dump, dựng chu trình chờ và dùng công cụ deadlock detection phù hợp |

## 14. Khác biệt phiên bản và khả năng tương thích

| Phiên bản | Tình trạng owner của park blocker trong file dump |
|---|---|
| JDK 25.0.3 trở về trước | Không có thay đổi JDK-8365057 trong các bản này |
| JDK 25.0.4 trở lên | Có backport của JDK-8365057 trong các bản phát hành đã tích hợp sửa lỗi |
| JDK 26 | Có trong release chính thức |
| JDK 26 update releases | Tiếp tục có; luôn ưu tiên update còn được hỗ trợ và có security fixes |

ThreadInfo.getLockOwnerId() và getLockOwnerName() đã có từ các phiên bản Java trước. JDK 26 không thêm các phương thức đó; điểm mới là đầu ra từ HotSpotDiagnosticMXBean.dumpThreads() và jcmd Thread.dump_to_file được bổ sung trường owner cho park blocker phù hợp.

Đây là tính năng của HotSpot diagnostics. Nếu triển khai trên JVM khác hoặc một JDK vendor có patch set riêng, hãy kiểm tra tài liệu release và thử dump trên đúng runtime mục tiêu. Không suy luận rằng mọi lệnh jstack, Thread.print, IDE hoặc công cụ APM đều xuất cùng định dạng.

## 15. Bài thực hành tổng hợp

Thực hiện bằng JDK 26 hoặc JDK 25.0.4 trở lên có backport tương ứng:

1. Chạy ParkBlockerOwnerDemo để tạo lock-owner và lock-waiter.
2. Lấy PID và dùng jcmd Thread.dump_to_file -format=plain để tạo dump.
3. Tìm dòng parking to wait for và ghi nhận owner ID.
4. Tìm thread header có ID tương ứng và đọc stack trace của owner.
5. Tạo JSON dump và xác nhận trường threads[].parkBlocker.owner.
6. Kiểm tra một thread đang chờ CountDownLatch hoặc Semaphore; quan sát trường owner có thể không xuất hiện.
7. Chụp hai hoặc ba dump cách nhau vài giây và xác nhận trạng thái owner/waiter có thể thay đổi.
8. Gọi ThreadInfo.getLockOwnerId() trong chương trình để so sánh với ID trong dump.
9. Thử ThreadMXBean.findDeadlockedThreads() trên một tình huống có chu trình khóa trong platform threads.
10. Ghi lại sự khác nhau giữa BLOCKED do synchronized và WAITING do LockSupport.park().
11. Nếu ứng dụng dùng virtual threads, kiểm tra thread dump JSON và đối chiếu giới hạn của ThreadMXBean.
12. Thử trên JDK 25.0.3 và JDK 25.0.4 hoặc JDK 26 để nhận biết ảnh hưởng của backport.

**Tiêu chí hoàn thành:** giải thích được park blocker và AbstractOwnableSynchronizer; xác định được phạm vi thay đổi JDK-8365057; tạo được dump plain text và JSON; đọc đúng owner ID và tìm thread sở hữu khóa; phân biệt park blocker với intrinsic monitor; hiểu trường owner là tùy chọn; dùng ThreadInfo khi cần đọc owner bằng code; biết giới hạn của ThreadMXBean với virtual threads; không nhầm contention kéo dài với deadlock.

## 16. Tài liệu tham khảo chính thức

- [JDK 26 Release Notes – JDK-8365057](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html) — xác nhận HotSpotDiagnosticMXBean.dumpThreads() và jcmd Thread.dump_to_file bổ sung owner của park blocker.
- [Consolidated JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26all-relnotes.html) — ghi nhận thay đổi trong nhóm hotspot/svc.
- [JDK 25.0.4 Release Notes](https://www.oracle.com/java/technologies/javase/25-0-4-relnotes.html) — xác nhận backport JDK-8365057 vào dòng JDK 25.
- [The jcmd Command – JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html) — cú pháp Thread.dump_to_file và các định dạng plain/json.
- [HotSpotDiagnosticMXBean – Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.management/com/sun/management/HotSpotDiagnosticMXBean.html) — API tạo thread dump.
- [Thread Dump JSON Schema – JDK 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.management/com/sun/management/doc-files/threadDump.schema.json) — định nghĩa threads[].parkBlocker.object và threads[].parkBlocker.owner.
- [AbstractOwnableSynchronizer – Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/AbstractOwnableSynchronizer.html) — setExclusiveOwnerThread() và getExclusiveOwnerThread().
- [AbstractQueuedSynchronizer – Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/AbstractQueuedSynchronizer.html) — cơ chế synchronizer và khuyến nghị duy trì owner để phục vụ monitoring/diagnostics.
- [LockSupport – Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/LockSupport.html) — park blocker, park() và getBlocker().
- [ThreadInfo – Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ThreadInfo.html) — getLockOwnerId(), getLockOwnerName() và thông tin thread đang chờ.
- [ThreadMXBean – Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ThreadMXBean.html) — monitoring platform threads và deadlock detection.
- [Virtual Threads – JDK 26](https://docs.oracle.com/en/java/javase/26/core/virtual-threads.html) — tạo dump cho virtual threads và giới hạn snapshot.

Owner của park blocker giúp xác định nhanh thread nào đang giữ synchronizer khiến thread khác phải chờ. Hãy dùng ID này để nối waiter với owner trong cùng dump, rồi đọc stack trace của owner và kiểm tra nhiều snapshot trước khi kết luận có deadlock.
