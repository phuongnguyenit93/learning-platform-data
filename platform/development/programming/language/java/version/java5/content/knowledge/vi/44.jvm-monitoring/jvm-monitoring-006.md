# ThreadMXBean, ThreadInfo và thông tin luồng

## 1. Cần quan sát điều gì khi ứng dụng chậm hoặc có nhiều luồng?

Một ứng dụng có thể chậm vì nhiều nguyên nhân: luồng đang tính toán, chờ dữ liệu, chờ công việc mới hoặc tranh chấp khóa. Chỉ biết “có 200 luồng” chưa đủ để phân biệt các tình huống này.

Hai kiểu trong `java.lang.management` bổ sung cho nhau:

- **ThreadMXBean** là giao diện quản lý hệ thống luồng: đọc số lượng, lấy danh sách ID và yêu cầu thông tin của các luồng.
- **ThreadInfo** là ảnh chụp thông tin một luồng tại thời điểm thu thập: tên, ID, trạng thái, stack trace và thông tin khóa theo mức chi tiết được yêu cầu.

Điểm vào chuẩn:

~~~java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();
~~~

Đây là câu lệnh minh họa, cần import `java.lang.management.ThreadMXBean` và `java.lang.management.ManagementFactory`, rồi đặt trong phương thức.

**Giới hạn quan trọng trên Java hiện hành:** ThreadMXBean giám sát **luồng nền tảng (platform thread)**, không hỗ trợ giám sát/quản lý **luồng ảo (virtual thread)**. Vì vậy, không coi các bộ đếm hay danh sách ID của bean là tổng số mọi loại luồng trong ứng dụng. [ThreadMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ThreadMXBean.html)

## 2. Số liệu tổng hợp và thông tin từng luồng trả lời các câu hỏi khác nhau

| Phương thức | Câu hỏi được trả lời |
|---|---|
| `getThreadCount()` | Hiện có bao nhiêu platform thread còn sống, gồm daemon và non-daemon? |
| `getDaemonThreadCount()` | Hiện có bao nhiêu platform thread daemon còn sống? |
| `getPeakThreadCount()` | Mức đỉnh số platform thread sống từ khi JVM khởi động hoặc từ lần đặt lại đỉnh? |
| `getTotalStartedThreadCount()` | Đã có tổng cộng bao nhiêu platform thread được khởi chạy từ khi JVM khởi động? |
| `getAllThreadIds()` | Các ID platform thread đang sống lúc lấy danh sách là gì? |
| `getThreadInfo(...)` | Tình trạng cụ thể của các luồng được chọn là gì? |

Ví dụ suy luận: tổng số luồng đã khởi chạy tăng nhanh nhưng số luồng sống khá ổn định có thể cho thấy chương trình liên tục tạo và kết thúc luồng. Đây là gợi ý cần điều tra cách dùng executor hoặc tạo thread, chưa đủ để kết luận rò rỉ luồng.

Mức đỉnh là bộ đo khác với giá trị hiện tại. Không lấy “đỉnh 500” làm bằng chứng rằng hiện ứng dụng có 500 luồng.

## 3. Chọn đúng biến thể getThreadInfo

### Chỉ đọc thông tin cơ bản

~~~java
ThreadInfo info = bean.getThreadInfo(threadId);
~~~

Biến thể này không lấy stack trace, danh sách monitor đang giữ hay danh sách synchronizer đang giữ. Vì thế, `info.getStackTrace().length == 0` trong trường hợp này không chứng minh luồng không có stack.

### Đọc stack có giới hạn độ sâu

~~~java
ThreadInfo info = bean.getThreadInfo(threadId, 20);
~~~

Yêu cầu tối đa 20 frame. `maxDepth = 0` nghĩa là không lấy stack; `Integer.MAX_VALUE` yêu cầu toàn bộ stack. Giới hạn độ sâu giúp giữ bản thu thập vừa đủ cho mục đích chẩn đoán.

### Đọc nhiều luồng cùng một yêu cầu

~~~java
long[] ids = bean.getAllThreadIds();
ThreadInfo[] infos = bean.getThreadInfo(ids, 20);

for (int i = 0; i < ids.length; i++) {
    ThreadInfo info = infos[i];
    if (info == null) {
        continue;
    }
    System.out.println(
            info.getThreadName() + ": " + info.getThreadState());
}
~~~

Đây là đoạn tích hợp trong phương thức đã có `bean`, cần import `ThreadInfo`. Mỗi vị trí kết quả tương ứng với cùng vị trí ID đầu vào.

**Phải xử lý null.** Luồng có thể kết thúc giữa lúc lấy danh sách ID và lúc đọc thông tin. Với ID của virtual thread, luồng chưa sống, luồng đã kết thúc hoặc ID không tồn tại, API cũng trả về `null`. ID không hợp lệ như số không hay số âm gây `IllegalArgumentException`, không phải một kết quả “không tìm thấy”. [Các biến thể getThreadInfo](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ThreadMXBean.html#getThreadInfo(long,int))

Không dùng tên luồng làm định danh duy nhất: nhiều luồng có thể cùng tên, và tên có thể thay đổi. ID có ý nghĩa trong vòng đời luồng; không giả định một ID là danh tính vĩnh viễn qua nhiều phiên JVM.

## 4. Những trường hữu ích trong ThreadInfo

| Nhóm | Getter tiêu biểu | Cách đọc |
|---|---|---|
| Danh tính | `getThreadId()`, `getThreadName()` | Luồng nào được quan sát |
| Trạng thái | `getThreadState()` | Trạng thái JVM ở thời điểm lấy mẫu |
| Stack | `getStackTrace()` | Các frame đã yêu cầu và thu thập được |
| Khóa đang chờ | `getLockInfo()`, `getLockName()` | Đối tượng đồng bộ liên quan đến việc chờ, nếu có |
| Chủ sở hữu | `getLockOwnerId()`, `getLockOwnerName()` | Ai đang sở hữu khóa liên quan, nếu xác định được |
| Khóa đang giữ | `getLockedMonitors()`, `getLockedSynchronizers()` | Chỉ có dữ liệu khi cách lấy mẫu yêu cầu thông tin này |
| Thống kê | `getBlockedCount()`, `getWaitedCount()` | Số lần vào các dạng chờ tương ứng |
| Thời gian chờ | `getBlockedTime()`, `getWaitedTime()` | Thời gian tích lũy gần đúng khi chức năng đo tương ứng được hỗ trợ/bật |

`ThreadInfo` phục vụ giám sát, không phải công cụ điều khiển đồng bộ. Trạng thái có thể đổi ngay sau khi thu thập. Không dùng một ảnh chụp để quyết định “bây giờ chắc chắn không có ai giữ khóa nên mình được sửa dữ liệu chung”. [ThreadInfo](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ThreadInfo.html)

Khi cần xuất dữ liệu cho công cụ, đọc getter rõ ràng. Không phân tích chuỗi `ThreadInfo.toString()` như một định dạng ổn định: cách biểu diễn chuỗi phụ thuộc triển khai.

## 5. Hiểu trạng thái để không chẩn đoán nhầm

Các trạng thái là trạng thái của JVM, không phải ánh xạ trực tiếp sang trạng thái luồng của hệ điều hành:

| Trạng thái | Ý nghĩa và ví dụ |
|---|---|
| `NEW` | Đối tượng Thread chưa được khởi chạy |
| `RUNNABLE` | Luồng đang có thể thực thi trong JVM; có thể còn phải chờ tài nguyên hệ điều hành |
| `BLOCKED` | Đang chờ lấy hoặc lấy lại monitor của synchronized |
| `WAITING` | Chờ vô thời hạn, ví dụ `Object.wait()`, `Thread.join()` hoặc `LockSupport.park()` |
| `TIMED_WAITING` | Chờ có thời hạn, ví dụ `Thread.sleep(...)` hoặc các dạng wait/park có thời hạn |
| `TERMINATED` | Luồng đã kết thúc |

`getThreadInfo` chỉ lấy thông tin luồng còn sống nên không mong đợi lấy một `ThreadInfo` của luồng đã kết thúc rồi thấy `TERMINATED`; trường hợp đó thường được biểu diễn bằng `null`.

Ba cách đọc sai thường gặp:

1. **RUNNABLE không có nghĩa chắc chắn đang tiêu thụ CPU.** Phải xem stack, quan sát nhiều mẫu và dùng phép đo CPU phù hợp nếu cần.
2. **BLOCKED không bao gồm mọi loại chờ khóa.** Tranh chấp `ReentrantLock` thường có thể xuất hiện dưới dạng chờ park, khác với chờ monitor synchronized.
3. **WAITING không tự chứng minh deadlock.** Worker của pool đang chờ công việc hoặc một luồng chờ tín hiệu đúng thiết kế đều có thể bình thường.

Muốn biết có tiến triển hay không, cần ghép trạng thái với stack, chủ khóa và bối cảnh công việc. [Thread.State](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.State.html)

## 6. Phân biệt khóa đang chờ với khóa đang giữ

Một luồng có thể giữ khóa A trong khi chờ khóa B:

~~~text
Luồng T giữ A
    -> đang cố lấy B
    -> B do luồng U giữ
~~~

Trong ảnh chụp của T:

- `getLockInfo()` mô tả đối tượng T đang chờ trong tình huống được hỗ trợ.
- `getLockOwnerId()` có thể chỉ đến U; `-1` biểu thị không có/chưa xác định chủ sở hữu.
- `getLockedMonitors()` có thể chứa A nếu đã yêu cầu thu thập các monitor đang giữ.

Không có chủ sở hữu được báo cáo không có nghĩa dữ liệu lỗi; một số dạng chờ không có chủ sở hữu theo nghĩa monitor độc quyền.

`LockInfo` chứa tên lớp và identity hash của đối tượng khóa. Chuỗi kiểu `java.lang.Object@...` không phải địa chỉ bộ nhớ. `MonitorInfo` bổ sung vị trí stack nơi monitor được lấy; frame có thể không sẵn có. [LockInfo](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/LockInfo.html), [MonitorInfo](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/MonitorInfo.html)

Nếu cần các khóa đang giữ, chọn biến thể có yêu cầu thu thập chúng. Ví dụ dưới đây là đoạn tích hợp, đã có `bean`:

~~~java
boolean monitors = bean.isObjectMonitorUsageSupported();
boolean synchronizers = bean.isSynchronizerUsageSupported();

ThreadInfo[] dump = bean.dumpAllThreads(monitors, synchronizers);
~~~

Hai kiểm tra khả năng tránh yêu cầu chức năng JVM không hỗ trợ. Nếu không yêu cầu một loại khóa, mảng loại đó rỗng không chứng minh luồng chẳng giữ khóa nào. Việc lấy stack và toàn bộ khóa có thể tốn chi phí; nên phục vụ chẩn đoán có chủ đích.

## 7. Ví dụ chạy được: quan sát một luồng BLOCKED và luồng đã kết thúc

Ví dụ dùng **JDK 21 trở lên** để tạo platform thread tường minh và lấy ID bằng `Thread.threadId()`. Các API giám sát thuộc ThreadMXBean/ThreadInfo vẫn là trọng tâm; không dùng API Thread đã deprecated để lấy ID.

Tình huống được kiểm soát:

1. Luồng main giữ một monitor.
2. Worker báo đã bắt đầu, rồi cố vào cùng monitor.
3. Main lấy thông tin khi worker đang BLOCKED.
4. Main nhả monitor trước khi join, để worker hoàn tất.
5. Đọc lại ID của worker sau khi kết thúc và kiểm tra kết quả null.

Lưu thành `ThreadInfoDemo.java`:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class ThreadInfoDemo {
    private static ThreadInfo awaitBlocked(
            ThreadMXBean bean, long id) throws InterruptedException {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(2);
        while (System.nanoTime() < deadline) {
            ThreadInfo info = bean.getThreadInfo(id, 12);
            if (info != null
                    && info.getThreadState() == Thread.State.BLOCKED) {
                return info;
            }
            Thread.sleep(5);
        }
        throw new IllegalStateException("Worker did not become BLOCKED");
    }

    public static void main(String[] args) throws Exception {
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        Object monitor = new Object();
        CountDownLatch started = new CountDownLatch(1);

        Thread worker = Thread.ofPlatform()
                .name("mxbean-blocked-worker")
                .unstarted(() -> {
                    started.countDown();
                    synchronized (monitor) {
                        // Main releases this monitor before join.
                    }
                });

        try {
            synchronized (monitor) {
                worker.start();
                if (!started.await(2, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Worker did not start");
                }

                ThreadInfo info = awaitBlocked(bean, worker.threadId());
                System.out.println("name=" + info.getThreadName());
                System.out.println("state=" + info.getThreadState());
                System.out.println("owner.is.main="
                        + (info.getLockOwnerId()
                        == Thread.currentThread().threadId()));
                System.out.println("waiting.for.monitor="
                        + (info.getLockInfo() != null));
                System.out.println("stack.present="
                        + (info.getStackTrace().length > 0));
            }
        } finally {
            if (worker.isAlive()) {
                worker.join(2_000);
                if (worker.isAlive()) {
                    throw new IllegalStateException("Worker did not finish");
                }
            }
        }

        ThreadInfo after = bean.getThreadInfo(worker.threadId());
        System.out.println("thread.after.join="
                + (after == null ? "absent" : "present"));
    }
}
~~~

Biên dịch và chạy với JDK 21+:

~~~shell
javac ThreadInfoDemo.java
java ThreadInfoDemo
~~~

Stdout đã kiểm chứng trong một lần chạy OpenJDK 24:

~~~text
name=mxbean-blocked-worker
state=BLOCKED
owner.is.main=true
waiting.for.monitor=true
stack.present=true
thread.after.join=absent
~~~

Vì sao kết quả có ý nghĩa:

- Main giữ monitor xuyên suốt lúc quan sát, nên worker không thể vào khối synchronized trước khi main ra khỏi nó.
- Latch xác nhận worker đã bắt đầu nhưng **không tự bảo đảm worker đã BLOCKED**. Hàm `awaitBlocked` kiểm tra điều kiện quan sát với thời hạn.
- `getThreadInfo(id, 12)` yêu cầu stack, khác với biến thể chỉ nhận ID.
- `owner.is.main=true` xác nhận chủ monitor là main ở thời điểm lấy mẫu.
- `waiting.for.monitor=true` kiểm tra có thông tin khóa đang chờ, không phải danh sách tất cả khóa worker đang giữ.
- `finally` thực thi sau khi đã ra khỏi synchronized. Nếu main join worker khi vẫn giữ monitor, main sẽ chờ worker trong khi worker chờ main nhả khóa.
- Sau khi join hoàn tất, worker là platform thread đã kết thúc; kết quả null lúc này phù hợp hợp đồng API.
- Các thời hạn trong ví dụ giúp phát hiện môi trường không tiến triển như dự kiến. Đây là chương trình thí nghiệm trạng thái; không dùng vòng polling ThreadInfo để đồng bộ logic nghiệp vụ.

Các ID cụ thể, tên frame, số dòng và toàn bộ stack có thể khác giữa các JDK. Vì vậy ví dụ in các quan hệ cần kiểm chứng, không cố định một stack trace phụ thuộc triển khai.

## 8. Đọc thống kê chờ và CPU mà không trộn ý nghĩa

`getBlockedCount()` liên quan số lần luồng bị chặn để vào hoặc vào lại monitor. `getWaitedCount()` liên quan số lần chờ tương ứng với WAITING/TIMED_WAITING. Chúng không thay thế thống kê độ trễ của yêu cầu nghiệp vụ.

`getBlockedTime()` và `getWaitedTime()` tính bằng **mili giây**, phụ thuộc khả năng và việc bật đo tranh chấp luồng. Khi đo không được bật, giá trị thời gian là `-1`; không đổi thành 0 rồi kết luận không có chờ. Nếu JVM không hỗ trợ, thao tác liên quan có thể ném `UnsupportedOperationException`. Việc bật lại theo dõi cũng đặt lại thống kê thời gian tương ứng, nên không trừ hai mẫu qua ranh giới đó như cùng một bộ đếm liên tục.

Khả năng hỗ trợ và trạng thái hiện tại được kiểm tra qua `isThreadContentionMonitoringSupported()` và `isThreadContentionMonitoringEnabled()`. Bộ thu thập chỉ đọc không nên tự ý bật/tắt cấu hình này mỗi lần lấy mẫu.

Thời gian CPU không nằm trong ThreadInfo. Nó được đọc riêng qua ThreadMXBean, có các kiểm tra khả năng/trạng thái và giá trị không sẵn có riêng. Đơn vị CPU time là **nano giây**, khác với các thời gian chờ nêu trên. Tăng thời gian chờ không có nghĩa CPU đã tăng tương ứng.

## 9. Quy trình đọc một bản thông tin luồng

Với một yêu cầu chậm cụ thể, có thể đi theo thứ tự:

1. Xác định các platform thread liên quan bằng bối cảnh công việc và quy ước tên; không chọn chỉ vì tên nghe giống “worker”.
2. Thu thập thông tin cơ bản và stack có độ sâu đủ dùng.
3. Bỏ qua hoặc ghi nhận rõ kết quả null do vòng đời thay đổi; không xem đó là lỗi bất thường mặc định.
4. Với BLOCKED/chờ khóa, xem khóa đang chờ và luồng sở hữu; cần thì lấy thêm thông tin khóa đang giữ.
5. Lấy vài mẫu cách nhau theo mục đích chẩn đoán, đối chiếu trạng thái và stack để xem có tiến triển.
6. Ghép với tải, độ trễ, hàng đợi và phép đo CPU phù hợp trước khi kết luận.

Thông tin luồng toàn JVM có thể chứa tên lớp, tên luồng và đường đi thực thi. Khi đưa ra endpoint chẩn đoán hoặc log, giới hạn việc truy cập và lượng dữ liệu theo nhu cầu vận hành.

Không lấy mẫu toàn bộ stack ở tần suất cao trong mỗi yêu cầu ứng dụng. Ưu tiên số liệu tổng hợp để theo dõi thường xuyên; lấy ảnh chụp chi tiết khi cần giải thích một hiện tượng.

## 10. Tự kiểm tra kiến thức

| Quan sát | Kết luận đúng ở bước đầu |
|---|---|
| ThreadInfo trả null | Có thể do vòng đời luồng hoặc loại luồng ngoài phạm vi; kiểm tra nguồn ID |
| Stack rỗng sau `getThreadInfo(id)` | Chưa yêu cầu stack, không phải bằng chứng stack không tồn tại |
| Nhiều worker WAITING trong pool nhàn rỗi | Có thể là hành vi bình thường |
| Nhiều mẫu cùng thấy BLOCKED trên cùng monitor | Có dấu hiệu tranh chấp kéo dài cần điều tra chủ khóa |
| RUNNABLE trong một mẫu | Chưa đủ bằng chứng về CPU cao |
| Danh sách khóa đang giữ rỗng | Phải biết đã yêu cầu thu thập danh sách đó chưa |
| Số luồng sống không đổi nhưng tổng số đã bắt đầu tăng | Có thể có hoạt động tạo/hủy luồng liên tục |

Bài tập: mở rộng ví dụ để in tối đa ba frame từ `info.getStackTrace()`, rồi đối chiếu với kết quả của `getThreadInfo(id)` không truyền độ sâu. Tiếp theo, lấy ảnh chụp có thông tin monitor và tìm monitor main đang giữ. Giữ việc nhả monitor trước join và xử lý null trong mọi đoạn đọc thông tin.

Mục tiêu là giải thích được **luồng nào, đang ở đâu, chờ gì và ai liên quan**, đồng thời hiểu giới hạn của một ảnh chụp. ThreadMXBean cung cấp đường đọc; ThreadInfo cung cấp bằng chứng tại thời điểm đo để phục vụ suy luận đó.
