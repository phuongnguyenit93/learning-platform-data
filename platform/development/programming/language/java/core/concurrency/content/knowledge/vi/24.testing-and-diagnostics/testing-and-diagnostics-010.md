# Phân tích deadlock với ThreadMXBean trong Java

## 1. Mục tiêu

**Deadlock** là tình huống một nhóm thread bị kẹt vì mỗi thread đang đợi tài nguyên mà thread khác trong nhóm nắm giữ, tạo thành **chu trình chờ** không thể tự giải quyết bằng cách chờ lâu hơn. Với Java, một lỗi deadlock thường không gây exception ngay: chương trình có thể vẫn chạy, nhưng một số request hoặc công việc không bao giờ hoàn tất.

Java cung cấp **ThreadMXBean** trong module chuẩn **java.management**, có thể kiểm tra các thread, lấy stack trace và phát hiện một số dạng deadlock ngay trong JVM. Bài học này tập trung vào:

1. Hiểu chu trình chờ lock và phân biệt deadlock với các tình trạng thread chậm khác.
2. Sử dụng **ManagementFactory.getThreadMXBean()**, **findMonitorDeadlockedThreads()**, **findDeadlockedThreads()** và **getThreadInfo(...)**.
3. Đọc **ThreadInfo** để xác định **thread nào đang giữ lock**, **thread nào chờ lock** và **đoạn code nào liên quan**.
4. Thực hành tạo deadlock có kiểm soát trong Java 17+, chẩn đoán và sửa bằng quy tắc thứ tự lấy lock.
5. Nhận biết giới hạn phát hiện, chi phí vận hành và những bước xử lý phù hợp khi xảy ra sự cố thật.

Phạm vi là concurrency của **Java/JDK**, không phụ thuộc framework.

## 2. Deadlock hình thành như thế nào?

Xét hai monitor Java là **lockA** và **lockB**:

~~~text
Thread T1                            Thread T2
-----------                          -----------
synchronized(lockA)                  synchronized(lockB)
  đang giữ lockA                        đang giữ lockB
  muốn lấy lockB                        muốn lấy lockA
  => BLOCKED                            => BLOCKED

        T1 --đợi lockB--> T2
        T2 --đợi lockA--> T1
~~~

**T1** không thể lấy **lockB** vì **T2** đang giữ; **T2** không thể lấy **lockA** vì **T1** đang giữ. Mỗi thread phải thoát khỏi vùng synchronized mới nhả lock, nhưng chính chúng lại không thể đi tiếp. Đó là chu trình chờ.

Bốn điều kiện kinh điển khiến deadlock có thể xảy ra đồng thời:

- **Mutual exclusion:** tài nguyên chỉ có thể do một chủ thể nắm giữ tại một thời điểm.
- **Hold and wait:** thread giữ một tài nguyên trong khi chờ tài nguyên khác.
- **No preemption:** tài nguyên không tự bị lấy lại một cách an toàn từ chủ sở hữu.
- **Circular wait:** tồn tại vòng chờ giữa các chủ sở hữu tài nguyên.

Chỉ cần phá một điều kiện thích hợp bằng thiết kế là có thể tránh loại deadlock đó. Cách thường dùng với nhiều lock là **áp đặt một thứ tự lấy lock thống nhất**.

### 2.1. Deadlock không đồng nghĩa mọi WAITING/BLOCKED

| Hiện tượng | Dấu hiệu thường gặp | Có tự động là deadlock? |
|---|---|---|
| **BLOCKED** | Thread chờ vào monitor của **synchronized** do thread khác giữ. | Không; có thể chỉ chờ ngắn hạn. |
| **WAITING** | Thread đang chờ không giới hạn tại **Object.wait()**, **Thread.join()**, **LockSupport.park()** hoặc cơ chế khác. | Không; có thể đang chờ điều kiện bình thường. |
| **TIMED_WAITING** | Thread chờ có thời hạn, ví dụ **sleep()**, timed wait hoặc timed park. | Không; thường còn đường timeout. |
| **Starvation** | Một thread liên tục không được cấp tài nguyên hoặc thời gian xử lý cần thiết. | Không nhất thiết có chu trình sở hữu lock. |
| **Livelock** | Các thread vẫn hoạt động/đổi trạng thái nhưng không tạo được tiến triển. | Không nhất thiết bị kẹt ở lock. |
| **Deadlock** | Có vòng chờ mà các thread trong vòng không thể tiến lên. | Có, trong phạm vi loại lock được chẩn đoán. |

Vì vậy, **đừng kết luận deadlock chỉ từ một thread dump có nhiều dòng BLOCKED**. Cần dựng được quan hệ **thread → lock đang đợi → thread đang sở hữu** và xác định chu trình.

## 3. ThreadMXBean là gì?

**ThreadMXBean** là giao diện quản lý thread của JVM nằm trong **java.lang.management**. Một JVM cung cấp một MXBean đại diện cho thông tin quản lý thread của nó.

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;

// Đoạn mã minh họa, đặt bên trong một phương thức:
ThreadMXBean bean = ManagementFactory.getThreadMXBean();
~~~

Đây là **API JDK**, không yêu cầu thư viện bên ngoài. Nó phục vụ giám sát và chẩn đoán, không phải primitive để tự động giải phóng lock. **ThreadMXBean** cho biết các thread đang làm gì; sau khi xác định nguyên nhân, **lập trình viên phải sửa thứ tự lock hoặc thiết kế đồng bộ**.

### 3.1. Các API quan trọng

| API | Tác dụng | Lưu ý |
|---|---|---|
| **findMonitorDeadlockedThreads()** | Tìm nhóm thread nằm trong chu trình chờ **object monitor** của Java (**synchronized**). | Không bao gồm vòng chờ chỉ qua ownable synchronizer. |
| **findDeadlockedThreads()** | Tìm chu trình chờ **object monitor hoặc ownable synchronizer**. | Có thể báo **UnsupportedOperationException** nếu JVM không hỗ trợ thông tin ownable synchronizer. |
| **isSynchronizerUsageSupported()** | Kiểm tra JVM có hỗ trợ theo dõi **ownable synchronizer** hay không. | Dùng trước khi yêu cầu chi tiết tương ứng. |
| **isObjectMonitorUsageSupported()** | Kiểm tra hỗ trợ lấy thông tin monitor do thread đang giữ. | Có ích khi gọi overload của **getThreadInfo** yêu cầu locked monitors. |
| **getThreadInfo(ids, maxDepth)** | Lấy **ThreadInfo** và stack trace tới độ sâu được chỉ định. | Không tự điền danh sách mọi monitor/synchronizer mà thread giữ. |
| **getThreadInfo(ids, lockedMonitors, lockedSynchronizers)** | Lấy thông tin chi tiết gồm stack trace và, nếu yêu cầu/hỗ trợ, danh sách lock đang giữ. | Chọn các cờ theo khả năng JVM. |
| **dumpAllThreads(...)** | Thu thập thông tin các thread JVM mà API hỗ trợ, kể cả thread không nằm trong nhóm deadlock. | Đọc nhiều dữ liệu hơn và có thể tốn chi phí. |

Hai phương thức **find...DeadlockedThreads()** trả về mảng **long[]** chứa ID các thread tham gia deadlock, hoặc **null** khi không tìm thấy. **null không chứng minh ứng dụng chắc chắn không có vấn đề concurrency**, vì API chỉ phát hiện những chu trình thuộc các loại lock được hỗ trợ, tại thời điểm chụp trạng thái.

**Object monitor** là lock gắn với vùng **synchronized**. **Ownable synchronizer** là các bộ đồng bộ có quan hệ một thread sở hữu độc quyền, chẳng hạn cơ chế lock thuộc **AbstractOwnableSynchronizer** và **ReentrantLock**. Không phải mọi kiểu chờ trong ứng dụng đều thuộc hai nhóm đó.

### 3.2. Chọn phương thức phát hiện đúng

~~~java
// Đoạn mã minh họa đặt trong một phương thức:
ThreadMXBean bean = ManagementFactory.getThreadMXBean();

long[] deadlockedIds;
if (bean.isSynchronizerUsageSupported()) {
    deadlockedIds = bean.findDeadlockedThreads();
} else {
    deadlockedIds = bean.findMonitorDeadlockedThreads();
}

if (deadlockedIds == null) {
    System.out.println("Chưa phát hiện chu trình deadlock được hỗ trợ");
}
~~~

Nếu cần tìm cả các trường hợp dùng **ReentrantLock**, ưu tiên **findDeadlockedThreads()**. Nếu JVM không hỗ trợ thông tin ownable synchronizer, phương án dự phòng **findMonitorDeadlockedThreads()** có **phạm vi hẹp hơn**, không được diễn giải thành kết quả phủ mọi loại lock.

Trong thực tế, API tìm deadlock nhằm **troubleshooting**, không phải điều kiện kiểm soát luồng công việc cứ gọi sau mỗi thao tác cập nhật. Không dùng nó thay cho các cơ chế synchronized, lock, timeout hoặc protocol tránh deadlock.

## 4. Ví dụ chạy được: tạo deadlock rồi dùng ThreadMXBean phát hiện

Ví dụ cố tình tạo vòng chờ giữa hai **synchronized** monitor, sau đó yêu cầu **ThreadMXBean** tìm chu trình và lấy thông tin người sở hữu lock. Nó sử dụng **CountDownLatch** để bảo đảm cả hai worker đã nắm monitor đầu tiên trước khi cố lấy monitor thứ hai.

**Cảnh báo thực hành:** Đây là demo **cố tình tạo deadlock**. Hai worker được đặt **daemon** để JVM có thể kết thúc sau khi main in báo cáo; tuyệt đối không sao chép mô hình lấy lock đối nghịch này vào code xử lý request.

Tạo file **DeadlockAnalysis.java**:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.Arrays;
import java.util.Comparator;
import java.util.concurrent.CountDownLatch;

public final class DeadlockAnalysis {
    private static Runnable takeBoth(Object first, Object second,
                                     CountDownLatch bothHoldingOne) {
        return () -> {
            synchronized (first) {
                bothHoldingOne.countDown();
                try {
                    bothHoldingOne.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }
                synchronized (second) {
                    System.out.println("unreachable");
                }
            }
        };
    }

    public static void main(String[] args) throws InterruptedException {
        Object left = new Object();
        Object right = new Object();
        CountDownLatch ready = new CountDownLatch(2);

        Thread a = new Thread(takeBoth(left, right, ready), "A-then-B");
        Thread b = new Thread(takeBoth(right, left, ready), "B-then-A");

        a.setDaemon(true);
        b.setDaemon(true);
        a.start();
        b.start();

        ThreadMXBean mxBean = ManagementFactory.getThreadMXBean();
        long[] ids = null;

        // Chờ tối đa khoảng 2 giây để deadlock hình thành.
        for (int attempt = 0; attempt < 100 && ids == null; attempt++) {
            ids = mxBean.findMonitorDeadlockedThreads();
            if (ids == null) Thread.sleep(20);
        }

        if (ids == null) {
            System.out.println("No deadlock observed within timeout");
            return;
        }

        ThreadInfo[] info = mxBean.getThreadInfo(ids, 16);
        Arrays.sort(info, Comparator.comparing(ThreadInfo::getThreadName));

        System.out.println("Deadlocked threads: " + info.length);
        for (ThreadInfo t : info) {
            System.out.println(t.getThreadName() + ": " + t.getThreadState()
                    + "; waits for " + t.getLockOwnerName());
        }
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 DeadlockAnalysis.java
java DeadlockAnalysis
~~~

Khi JVM hỗ trợ theo dõi monitor và phát hiện trong thời hạn, output kỳ vọng:

~~~text
Deadlocked threads: 2
A-then-B: BLOCKED; waits for B-then-A
B-then-A: BLOCKED; waits for A-then-B
~~~

Nếu môi trường quá bận, quá khác biệt hoặc không phát hiện kịp, demo có thể in **No deadlock observed within timeout** thay vì in báo cáo. Đây là cách tránh cho **main** phải chờ vô hạn, không phải bằng chứng chắc chắn không có deadlock.

### 4.1. Phân tích diễn biến

1. **A-then-B** vào vùng **synchronized(left)**. **B-then-A** vào **synchronized(right)**.
2. Mỗi thread giảm latch **ready** rồi gọi **ready.await()** trong lúc vẫn giữ monitor đầu tiên. Khi cả hai đã tới đây, latch mở.
3. Thread A tìm **right** nhưng thread B giữ **right**; thread B tìm **left** nhưng A giữ **left**.
4. Cả hai bị **BLOCKED** tại câu lệnh **synchronized(second)**.
5. **findMonitorDeadlockedThreads()** thấy vòng chờ monitor. **getThreadInfo(ids, 16)** lấy trạng thái, tên và chủ sở hữu lock; sắp xếp theo tên giúp thứ tự output dễ đọc.
6. **setDaemon(true)** chỉ giúp quá trình demo kết thúc khi main xong. Nó **không giải phóng deadlock** hay sửa code sai. Trong ứng dụng thật, thread nắm lock bị deadlock vẫn là sự cố nghiêm trọng.

Ví dụ dùng **CountDownLatch** để tạo deadlock có thể lặp lại; chỉ thêm **Thread.sleep(...)** ngẫu nhiên vào hai worker sẽ khiến việc tái hiện không ổn định. Với một test tự động, cần timeout để tránh cả bộ test bị treo.

### 4.2. Quan sát trực quan chu trình

~~~text
       đang giữ LEFT                         đang giữ RIGHT
      +-------------+                        +-------------+
      | A-then-B    | ---- muốn RIGHT ---->  | B-then-A    |
      | BLOCKED     | <---- muốn LEFT -----  | BLOCKED     |
      +-------------+                        +-------------+

   A-then-B.getLockOwnerName() = "B-then-A"
   B-then-A.getLockOwnerName() = "A-then-B"
~~~

Tên thread chỉ là nhãn phục vụ chẩn đoán; **thread ID** mới là định danh dùng trong dữ liệu MXBean. Trong hệ thống thật, có thể có hàng chục thread, nhiều monitor và những chu trình dài hơn hai node.

## 5. Đọc ThreadInfo để tìm nguyên nhân gốc

Sau khi phát hiện ID, đừng dừng ở câu “có hai thread deadlock”. Cần xác định **điểm code chờ lock**, **lock đang chờ**, **ai đang giữ lock**, và **điểm code đã giữ lock trước đó**.

Các thông tin cốt lõi của **java.lang.management.ThreadInfo**:

| Method | Ý nghĩa khi điều tra |
|---|---|
| **getThreadId()**, **getThreadName()** | Định danh thread trong bản chụp trạng thái. |
| **getThreadState()** | **BLOCKED** thường biểu thị đợi object monitor; với ownable synchronizer có thể thấy **WAITING** khi parked. |
| **getLockInfo()**, **getLockName()** | Đối tượng lock mà thread đang chờ. Tên có thể chứa tên class và identity hash, **không** phải nhãn nghiệp vụ. |
| **getLockOwnerId()**, **getLockOwnerName()** | Thread sở hữu lock đang chờ, nếu xác định được; trường hợp không có owner có thể nhận **-1/null**. |
| **getStackTrace()** | Vị trí method và stack frame tại thời điểm lấy dữ liệu. |
| **getLockedMonitors()** | Monitor mà thread đang giữ **khi đã yêu cầu thu thập danh sách này**. |
| **getLockedSynchronizers()** | Ownable synchronizer đang giữ **khi đã yêu cầu thu thập danh sách này**. |

### 5.1. Lấy báo cáo chi tiết của đúng nhóm deadlock

Đây là **đoạn mã minh họa đặt trong phương thức**, với biến **bean** là một **ThreadMXBean** lấy từ **ManagementFactory**, và **ids** là mảng ID đã tìm được:

~~~java
boolean withMonitors = bean.isObjectMonitorUsageSupported();
boolean withSynchronizers = bean.isSynchronizerUsageSupported();
ThreadInfo[] details =
        bean.getThreadInfo(ids, withMonitors, withSynchronizers);

for (ThreadInfo t : details) {
    if (t == null) continue; // Thread có thể kết thúc giữa hai lần đọc.

    System.out.printf("Thread=%s id=%d state=%s%n",
            t.getThreadName(), t.getThreadId(), t.getThreadState());
    System.out.printf("Waiting for=%s owned by=%s (id=%d)%n",
            t.getLockInfo(), t.getLockOwnerName(), t.getLockOwnerId());

    for (StackTraceElement frame : t.getStackTrace()) {
        System.out.println("    at " + frame);
    }
    for (java.lang.management.MonitorInfo monitor : t.getLockedMonitors()) {
        System.out.println("    holds monitor " + monitor);
    }
    for (java.lang.management.LockInfo lock : t.getLockedSynchronizers()) {
        System.out.println("    holds synchronizer " + lock);
    }
}
~~~

**Lưu ý quan trọng:**

- Cờ **withMonitors** và **withSynchronizers** được lấy từ capability của JVM trước khi yêu cầu thông tin, tránh gọi overload không được hỗ trợ.
- **getThreadInfo(ids, 16)** lấy tối đa 16 stack frame mỗi thread, nhưng **không phải yêu cầu đầy đủ danh sách monitor/ownable synchronizer đang giữ**. Muốn xem danh sách này, gọi overload có các cờ tương ứng như trên.
- Thông tin là **bản chụp**. Giữa lúc tìm ID và đọc chi tiết, thread có thể kết thúc; khi đó phần tử tương ứng trong **ThreadInfo[]** có thể là **null**.
- Đừng chỉ ghi lại **getThreadState()**. Cần kết hợp **getLockInfo()**, **getLockOwnerId()** và **getStackTrace()** mới dựng được vòng chờ.
- Các stack frame cho biết **đường thực thi của thread tại lúc chụp**, không tự chứng minh dòng code nào lần đầu tạo ra lock hoặc nguyên nhân thiết kế. **getLockedMonitors()** có thể giúp chỉ ra frame đã giữ monitor, nhưng cần xem code và thứ tự lock để kết luận.

### 5.2. Trình tự điều tra một vụ deadlock

1. **Xác định triệu chứng:** request/task nào đứng lâu, thread pool có hết worker không, deadline nào bị vượt?
2. **Chụp trạng thái:** tìm deadlock và thu ThreadInfo/stack trace, ưu tiên lưu vào hệ thống chẩn đoán hiện có.
3. **Dựng đồ thị chờ:** với từng thread bị kẹt, ghi lock đang chờ và thread owner. Đi theo owner liên tiếp để tìm chu trình.
4. **Đọc từng stack:** xác định câu lệnh đang cố lấy lock thứ hai và đoạn code trước đó lấy lock thứ nhất.
5. **Tìm thứ tự đối nghịch:** ví dụ đường code 1 lấy **lockA → lockB**, đường code 2 lấy **lockB → lockA**.
6. **Sửa cấu trúc đồng bộ:** thống nhất thứ tự lock, giảm phạm vi khóa, bỏ lồng lock không cần thiết hoặc dùng giải pháp có timeout phù hợp.
7. **Tái hiện và kiểm thử hồi quy:** tạo nhiều interleaving, thêm timeout cho test để test thất bại có kiểm soát, theo dõi khả năng hoàn tất sau sửa.

## 6. Phân biệt synchronized và ReentrantLock khi phát hiện

### 6.1. Deadlock monitor với synchronized

Khi hai thread giữ và chờ lẫn nhau trên monitor của **synchronized**, trạng thái thường là **BLOCKED**. Cả **findMonitorDeadlockedThreads()** lẫn **findDeadlockedThreads()** có thể tìm thấy chu trình này nếu JVM hỗ trợ phương thức tương ứng.

### 6.2. Deadlock qua ownable synchronizer

Với **java.util.concurrent.locks.ReentrantLock**, thread không tranh chấp một monitor tại câu lệnh **synchronized**. Nó có thể đợi trên cơ chế **AbstractQueuedSynchronizer/LockSupport**, thường quan sát ở **WAITING** hoặc **TIMED_WAITING** tùy cách chờ.

Hai đường code lấy ReentrantLock theo thứ tự ngược nhau cũng có thể hình thành chu trình sở hữu lock:

~~~text
T1 nắm lockA (ReentrantLock) → gọi lockB.lock(), phải đợi T2
T2 nắm lockB (ReentrantLock) → gọi lockA.lock(), phải đợi T1
~~~

**findMonitorDeadlockedThreads()** không bao phủ một chu trình chỉ có ownable synchronizer. **findDeadlockedThreads()** có thể phát hiện dạng này **khi JVM hỗ trợ theo dõi ownable synchronizer**. Kiểm tra **isSynchronizerUsageSupported()** trước khi sử dụng.

**tryLock(timeout, unit)** có thể hỗ trợ thoát khỏi chờ vô hạn, nhưng cần xử lý khi hết hạn, nhả những lock đã lấy trong **finally** và quyết định retry/backoff phù hợp. Thay **lock()** bằng **tryLock()** mà không có quy tắc và dọn dẹp đúng có thể tạo lỗi khác.

### 6.3. Giới hạn cần nhớ

ThreadMXBean **không phải công cụ chứng minh toàn bộ chương trình không bị deadlock**. Chẳng hạn:

- Thread đợi **Future.get()**, **join()**, **CountDownLatch.await()**, **Condition.await()**, I/O hoặc một RPC có thể kẹt lâu vì logic chờ, nhưng không nhất thiết tạo chu trình lock owner mà các phương thức **find...DeadlockedThreads()** phát hiện.
- Việc đợi một dịch vụ bên ngoài hoặc deadlock trải qua **nhiều JVM/process** không thể suy ra chỉ từ một ThreadMXBean của một JVM.
- Native lock, protocol chờ tùy biến và các cách thực thi khác có thể không hiện dưới dạng monitor/ownable synchronizer được hỗ trợ.
- Với các phiên bản Java có **virtual thread**, cần kiểm tra giới hạn theo phiên bản: các phương thức deadlock detection của ThreadMXBean được mô tả cho **platform threads**; không được mặc định coi kết quả đó là báo cáo bao phủ mọi virtual thread.

Giữ ranh giới rõ: **“Không tìm thấy deadlock qua MXBean”** là kết quả của một phép kiểm tra cụ thể, **không** đồng nghĩa “không có deadlock, starvation hoặc hang”.

## 7. Chẩn đoán khi ứng dụng đang chạy

### 7.1. Bằng code JDK trong tiến trình

Ứng dụng có thể có lệnh chẩn đoán nội bộ được gọi khi cần, ví dụ trong một endpoint vận hành được bảo vệ hoặc lúc thu thập thông tin lỗi. Một đoạn cơ bản:

~~~java
// Ví dụ đoạn mã đặt bên trong phương thức chẩn đoán:
ThreadMXBean bean = ManagementFactory.getThreadMXBean();

long[] ids = bean.isSynchronizerUsageSupported()
        ? bean.findDeadlockedThreads()
        : bean.findMonitorDeadlockedThreads();

if (ids != null) {
    ThreadInfo[] infos = bean.getThreadInfo(
            ids,
            bean.isObjectMonitorUsageSupported(),
            bean.isSynchronizerUsageSupported()
    );
    for (ThreadInfo info : infos) {
        if (info != null) {
            System.err.println(info);
        }
    }
}
~~~

Để điều tra triệt để, lưu cả **ID**, **tên thread**, **thread state**, **lock owner** và **stack frames** như mục 5. Một số phương thức **toString()** có thể giới hạn số stack frame in ra; khi cần toàn bộ, duyệt **getStackTrace()** thay vì chỉ in **ThreadInfo.toString()**.

**Không gọi deadlock detection theo từng request**: việc quét thread/lock có chi phí và hướng tới troubleshooting. Nếu đưa vào giám sát định kỳ, lựa chọn tần suất thích hợp, đo overhead và có cơ chế tắt khi cần.

### 7.2. Dùng công cụ đi kèm JDK từ bên ngoài

Khi đã biết PID của JVM và có quyền truy cập tiến trình phù hợp, có thể thu thread dump bằng công cụ JDK (các lệnh sau là ví dụ terminal, thay PID bằng tiến trình thực):

~~~bash
jcmd <PID> Thread.print -l
~~~

Trong một số môi trường có thể dùng:

~~~bash
jstack -l <PID>
~~~

**-l** yêu cầu thêm thông tin lock mà công cụ hỗ trợ. Hãy đọc phần **Java-level deadlock** nếu công cụ tạo phần phân tích deadlock, đồng thời tự kiểm tra các stack/owner relation. Lệnh và đầu ra có thể khác theo bản JDK/JVM và môi trường; cần JDK tools thích hợp và quyền attach.

Một thread dump hữu ích thường có những phần tương tự sau, chỉ là **sơ đồ minh họa**, không phải output nguyên văn ổn định:

~~~text
"A-then-B" ... BLOCKED
  waiting to lock RIGHT, owned by B-then-A
  locked LEFT

"B-then-A" ... BLOCKED
  waiting to lock LEFT, owned by A-then-B
  locked RIGHT
~~~

Nếu cần so tình huống thay đổi theo thời gian, chụp nhiều lần cách nhau hợp lý. Một dump duy nhất có thể cho thấy thread **BLOCKED** trong một khoảnh khắc hoàn toàn bình thường; nhiều dump và quan hệ lock owner giúp phân biệt chờ ngắn hạn với treo dai dẳng.

### 7.3. JMX và bảo mật vận hành

Vì **ThreadMXBean** là MXBean, môi trường có thể truy cập qua **JMX/MBeanServer** theo cấu hình và quyền thích hợp. Trong ứng dụng thực tế, hãy hạn chế ai có thể kích hoạt thread dump hoặc lấy stack trace: tên method, tham số/chi tiết triển khai và đường dẫn có thể lộ thông tin nội bộ. Chỉ mở giao diện chẩn đoán ở phạm vi cần thiết.

Các phương thức này chủ yếu thu thập dữ liệu; chúng **không dừng thread** và **không tự sửa deadlock**.

## 8. Cách sửa: thống nhất thứ tự lấy lock

Trong ví dụ deadlock, một worker lấy **left → right** còn worker kia lấy **right → left**. Nếu cả hai luôn lấy theo thứ tự **left → right**, chu trình chờ trên hai monitor không thể hình thành từ đúng hai lời gọi đó.

Tạo file **OrderedLocks.java**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public final class OrderedLocks {
    public static void main(String[] args) throws InterruptedException {
        Object first = new Object();
        Object second = new Object();
        AtomicInteger finished = new AtomicInteger();

        Runnable job = () -> {
            synchronized (first) {
                synchronized (second) {
                    finished.incrementAndGet();
                }
            }
        };

        Thread a = new Thread(job, "A");
        Thread b = new Thread(job, "B");
        a.start();
        b.start();

        a.join();
        b.join();
        System.out.println("finished=" + finished.get());
    }
}
~~~

Chạy với Java 17+:

~~~bash
javac --release 17 -encoding UTF-8 OrderedLocks.java
java OrderedLocks
~~~

Output:

~~~text
finished=2
~~~

Giải thích: các thread có thể đợi **first** vì chỉ một thread giữ monitor tại một thời điểm, nhưng không có thread nào giữ **second** trong khi cố lấy **first**. Do đó, không tồn tại cặp thứ tự ngược gây chu trình như demo trước. **AtomicInteger** ở đây chỉ giúp đếm kết quả đã xử lý; phép cộng nằm trong vùng đồng bộ đã được bảo vệ.

**Trong code thực tế**, khi có nhiều object lock, phải xây quy tắc thứ tự **ổn định và nhất quán giữa mọi đường code**. Nếu sắp thứ tự theo một khóa so sánh, phải xử lý cả trường hợp hai khóa có giá trị so sánh bằng nhau; không tự xem **identityHashCode()** là khóa thứ tự tuyệt đối không bao giờ trùng.

Các cách giảm nguy cơ khác:

- **Giảm vùng giữ lock:** không giữ monitor khi thực hiện I/O, gọi callback ngoài hệ thống, truy vấn remote hoặc phép tính quá dài nếu không thực sự cần.
- **Tránh lồng nhiều lock:** tổ chức lại dữ liệu hoặc chuyển sang một điểm đồng bộ đơn giản hơn khi có thể.
- **Dùng timeout có kiểm soát:** với lock hỗ trợ **tryLock**, xử lý nhánh thất bại và nhả mọi lock trong **finally**.
- **Chọn cấu trúc thread-safe thích hợp:** ví dụ collection/concurrent abstraction của JDK có thể giảm số lock tự quản; vẫn phải xem tính nguyên tử của các thao tác kết hợp.
- **Không cố chữa deadlock bằng thêm sleep:** delay chỉ thay đổi interleaving, không loại bỏ vòng chờ có thể xảy ra.
- **Không dùng Thread.stop():** đây là cơ chế nguy hiểm vì có thể bỏ dở thao tác đang giữ invariant; cách đúng là sửa thiết kế lock và quản lý vòng đời.

## 9. Kiểm thử và chẩn đoán có tính lặp lại

### 9.1. Tạo interleaving có chủ đích

Dùng **CountDownLatch**, **CyclicBarrier** hoặc điều phối tương tự để ép các thread đi tới đúng mốc cạnh tranh. Với demo ở mục 4, latch bảo đảm cả hai thread giữ lock đầu tiên trước khi tìm lock thứ hai, vì vậy không lệ thuộc vào lịch CPU một cách ngẫu nhiên.

### 9.2. Ràng buộc thời gian kiểm thử

Một bài test sinh deadlock cố tình phải có **timeout**. Nếu chương trình gọi **join()** không giới hạn trên những thread đã deadlock, toàn bộ bài test có thể treo. Khi tái hiện một deadlock monitor, **interrupt()** thường **không tự giải phóng** việc thread đang chờ vào **synchronized**; không dùng interrupt như phép khôi phục đáng tin cho deadlock loại này.

Trong ví dụ, hai worker **daemon** giúp demo kết thúc sau khi main in xong. Đặt daemon chỉ thích hợp để biểu diễn hiện tượng trong bài học; với ứng dụng thật, thread daemon bị kẹt vẫn có thể gây mất công việc hoặc mất tính đúng đắn.

### 9.3. Những điều cần kiểm chứng sau khi sửa

- Không còn chu trình **lockA → lockB → lockA** trong mọi đường thực thi liên quan.
- Hai hoặc nhiều thread có thể hoàn tất công việc dưới stress test có timeout.
- Khi tải cao, thread **BLOCKED** trong khoảng thời gian hợp lý vẫn có thể bình thường; xem thêm throughput và độ trễ để phát hiện bottleneck.
- Kịch bản lỗi/interrupt/cancel không giữ lock lâu hơn cần thiết.
- Các thread pool, latch hoặc future phụ thuộc vào những worker liên quan vẫn có đường hoàn tất hoặc hủy rõ ràng.
- Nếu deadlock đã xảy ra trong production, đối chiếu stack trace với code ở phiên bản **đang chạy** (build/release thực tế), không chỉ bản code hiện tại trên nhánh phát triển.

## 10. Các lỗi thường gặp khi sử dụng ThreadMXBean

1. **Thấy nhiều BLOCKED rồi gọi đó là deadlock.** Cần chứng minh chu trình sở hữu lock; BLOCKED riêng lẻ có thể là tranh chấp bình thường.
2. **Chỉ gọi findMonitorDeadlockedThreads() để tìm deadlock ReentrantLock.** Hàm này chỉ tìm object monitor; dùng **findDeadlockedThreads()** khi ownable synchronizer được hỗ trợ.
3. **Nhận null rồi khẳng định chương trình không thể deadlock.** Kết quả null chỉ cho biết không tìm thấy deadlock thuộc phạm vi công cụ tại thời điểm lấy mẫu.
4. **Chỉ in tên thread và state, không lấy owner và stack.** Thiếu thông tin cần thiết để truy nguyên hai đường lấy lock đối nghịch.
5. **Đọc getLockedMonitors() sau khi chỉ gọi getThreadInfo(ids, depth).** Muốn danh sách lock đang giữ, phải yêu cầu overload có các cờ phù hợp.
6. **Coi mọi WAITING là deadlock.** WAITING có thể là chờ signal, worker queue hoặc timer; phải xem primitive và owner relation.
7. **Nhầm monitor với ownable synchronizer.** **synchronized** và **ReentrantLock** có thể biểu diễn trạng thái chờ khác nhau và cần cách quét phù hợp.
8. **Ném exception hoặc interrupt để mong synchronized tự nhả lock đang bị chờ.** Thread đang **BLOCKED** trên monitor không được cứu một cách tổng quát bằng interrupt.
9. **Giả định phát hiện deadlock đồng nghĩa tự khôi phục.** ThreadMXBean chỉ cung cấp chẩn đoán; cần sửa cấu trúc code hoặc quy trình khởi động lại có đánh giá tác động.
10. **Quét mọi thread liên tục mà không đo chi phí.** Thu thập stack và lock state có overhead; chỉ sử dụng khi cần và theo tần suất được kiểm soát.
11. **Bỏ qua những dạng chờ ngoài lock owner graph.** Future, latch, I/O, native code, hệ thống phân tán hay virtual thread ở những phiên bản Java khác có thể cần công cụ/phương pháp bổ sung.
12. **Viết test deadlock không có timeout.** Một bài test có thể treo vĩnh viễn dù lỗi đã được tái hiện thành công.

## 11. Checklist điều tra sự cố

- **Triệu chứng:** thread pool đứng im, request treo, CPU vẫn thấp hay thread block tăng?
- **Phạm vi:** ứng dụng dùng **synchronized**, **ReentrantLock** hoặc primitive chờ khác?
- **Khả năng JVM:** kiểm tra **isSynchronizerUsageSupported()** và **isObjectMonitorUsageSupported()** trước khi lấy locked synchronizers/monitors.
- **Kết quả phát hiện:** **findDeadlockedThreads()** hoặc phương án monitor-only cho ID nào? Có trả null không?
- **Tính đúng của dữ liệu:** đọc cùng nhóm ID từ **getThreadInfo(...)**; xử lý trường hợp thread đã kết thúc hoặc snapshot thay đổi.
- **Chu trình:** ghi cụ thể **thread A chờ lock do B giữ**, **B chờ lock do A giữ**, và các phần của chu trình dài hơn nếu có.
- **Stack trace:** có thông tin method/file/line cho nơi xin lock và các monitor/synchronizer đang giữ không?
- **Cách sửa:** có áp dụng một thứ tự lock thống nhất, giảm lồng khóa hoặc cơ chế timeout và nhả tài nguyên đúng chưa?
- **Xác minh:** có test mô phỏng interleaving với timeout và chạy stress đủ mức không?
- **Vận hành:** có lưu thread dump/bản chụp hợp lệ, kiểm soát quyền truy cập và hạn chế overhead chẩn đoán không?

**Kết luận:** **ThreadMXBean** giúp biến triệu chứng “thread không tiến lên” thành dữ liệu cụ thể gồm **thread, lock đang đợi, owner, stack trace** và, khi hỗ trợ, chu trình deadlock. Để sửa tận gốc, phải truy lại **thứ tự lấy lock** và thiết kế đồng bộ; công cụ chẩn đoán không thay thế cho điều đó.

## 12. Tài liệu JDK chính thức

- [ThreadMXBean — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html)
- [ThreadInfo — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadInfo.html)
- [ManagementFactory — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ManagementFactory.html)
- [ReentrantLock — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html)
- [CountDownLatch — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
