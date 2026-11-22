# Chẩn đoán chờ khóa bằng thông tin luồng và MXBean

## 1. Bài toán: ứng dụng chậm nhưng chưa biết luồng đang chờ gì

Một dịch vụ có thể phản hồi chậm trong khi CPU không cao. Có luồng đang chờ khóa, có luồng đang đợi phần tử trong queue, có luồng đợi I/O và cũng có luồng nhàn rỗi đúng thiết kế.

Chỉ nhìn số lượng luồng hoặc thấy nhiều trạng thái WAITING chưa đủ để kết luận có lỗi.

Bài thực hành tập trung vào một câu hỏi có thể kiểm chứng:

> Luồng nào đang chờ một monitor, monitor đó thuộc về ai và chủ sở hữu đang làm gì?

Công cụ chính là `ThreadMXBean` lấy từ `ManagementFactory`, cùng các đối tượng `ThreadInfo`. Ví dụ tạo tranh chấp monitor có kiểm soát, thu bằng chứng rồi giải phóng các luồng bình thường; không cố tạo một deadlock không thể hủy trong tiến trình học tập.

Chương trình dùng Java 21+ để sử dụng `Thread.threadId()` hiện hành. Các kỹ thuật quan sát vẫn cần được hiểu theo giới hạn của JVM triển khai.

## 2. Đọc đúng trạng thái luồng

| Trạng thái | Ý nghĩa cần nhớ khi chẩn đoán |
| --- | --- |
| `RUNNABLE` | Có thể chạy/đang thực thi theo JVM; không đồng nghĩa đang dùng CPU liên tục |
| `BLOCKED` | Chờ lấy monitor để vào hoặc vào lại vùng synchronized |
| `WAITING` | Đợi một hành động khác, không có thời hạn trong thao tác đó |
| `TIMED_WAITING` | Đợi bằng một thao tác có thời hạn |
| `TERMINATED` | Luồng đã kết thúc |

Đây là trạng thái JVM, không phải bản sao trực tiếp của trạng thái luồng hệ điều hành. Các định nghĩa nằm trong [Thread.State API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.State.html).

Hai điểm dễ nhầm:

- Chờ `synchronized` thường thấy là `BLOCKED`.
- Chờ `ReentrantLock`, điều kiện hoặc nhiều cấu trúc đồng bộ dùng cơ chế park có thể thấy `WAITING`/`TIMED_WAITING`, không phải `BLOCKED`.

Một worker đang đợi công việc bằng `BlockingQueue.take()` có thể đang hoạt động đúng thiết kế. Muốn phân biệt với một điểm nghẽn, cần xem stack, đối tượng đang chờ và mức tải của hệ thống.

## 3. ThreadInfo cho biết những gì?

Lấy MXBean của JVM hiện tại:

```java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();
```

Lấy một snapshot kèm tối đa 32 frame:

```java
ThreadInfo info = bean.getThreadInfo(threadId, 32);
```

Nếu luồng đã kết thúc hoặc không có dữ liệu cho id đó, kết quả có thể là `null`. Không truy cập ngay các trường mà bỏ qua trường hợp này.

Những trường hữu ích:

| API | Cách dùng |
| --- | --- |
| `getThreadName()`, `getThreadId()` | Nhận diện luồng trong snapshot |
| `getThreadState()` | Xác định loại trạng thái đang quan sát |
| `getLockInfo()` | Đối tượng liên quan đến việc chờ, nếu có |
| `getLockOwnerId()`, `getLockOwnerName()` | Tìm chủ sở hữu khóa nếu thông tin có sẵn |
| `getStackTrace()` | Xem đường gọi tại thời điểm lấy mẫu |
| `getLockedMonitors()` | Monitor mà luồng đang giữ, nếu đã yêu cầu thu |
| `getLockedSynchronizers()` | Ownable synchronizer mà luồng đang giữ, nếu đã yêu cầu thu |

`getLockInfo()` có thể là đối tượng chờ notify hoặc park; không phải mọi giá trị ở đó đều là monitor đang có một chủ sở hữu hữu ích. Chủ sở hữu có thể không xác định, thể hiện bằng id `-1` hoặc tên null.

`ThreadInfo` dành cho quan sát, không phải điều khiển đồng bộ của chương trình. Hợp đồng các trường được mô tả trong [ThreadInfo API](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ThreadInfo.html).

## 4. Đi theo chuỗi chờ thay vì chỉ đếm BLOCKED

Một cách đọc snapshot:

```text
Luồng A chờ monitor M
          |
        M do B giữ
          |
  Xem stack và khóa B đang giữ/chờ
          |
  B chạy CPU, đợi I/O hay tiếp tục chờ C?
```

Ví dụ suy luận:

- Nhiều luồng cùng chờ một monitor, chủ sở hữu đang gọi I/O: có thể vùng khóa đang bao quá nhiều công việc.
- Chủ sở hữu đang chờ một Future mà Future đó cần chính monitor này: có thể có quan hệ chờ vòng về mặt thiết kế.
- Chủ sở hữu thay đổi qua các snapshot và công việc vẫn tiến triển: có thể là tranh chấp, chưa phải deadlock.
- Một pool đầy worker đều chờ công việc khác trong cùng pool chưa được chạy: có thể là thiếu năng lực thực thi, không phải vòng monitor mà API tìm deadlock phát hiện.

Không đồng nhất “chờ lâu” với “deadlock”. Tranh chấp kéo dài có thể làm hệ thống gần như đứng nhưng vẫn còn tiến triển; deadlock có chu kỳ phụ thuộc mà các bên không tự thoát được theo điều kiện hiện tại.

## 5. Tạo một tình huống monitor contention có kiểm soát

Thí nghiệm gồm:

1. Luồng `lock-owner` vào `synchronized(monitor)`.
2. Luồng đó báo đã giữ monitor bằng latch.
3. Trong lúc giữ monitor, nó chờ một latch khác.
4. Luồng `lock-contender` cố vào cùng monitor.
5. Main quan sát contender đang BLOCKED và biết owner tương ứng.
6. Main mở latch giải phóng owner; contender vào được rồi cả hai kết thúc.

Main không cần monitor đó để mở latch, nên có đường tiến triển rõ ràng.

Chờ latch trong lúc giữ monitor là cách **cố ý tạo triệu chứng** cho bài học, không phải gợi ý giữ khóa qua các tác vụ đợi lâu trong mã nghiệp vụ. Latch không tự giải phóng monitor ngoài đang giữ. Đừng nhầm với `Object.wait()`, vốn có quy tắc nhả/lấy lại monitor của chính đối tượng wait.

## 6. Chương trình Java 21+ chạy đầy đủ

Lưu thành `MonitorWaitDemo.java`:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.Arrays;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class MonitorWaitDemo {
    private static ThreadInfo awaitBlocked(
            ThreadMXBean bean, long id) throws InterruptedException {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while (System.nanoTime() < deadline) {
            ThreadInfo info = bean.getThreadInfo(id, 32);
            if (info == null) {
                throw new IllegalStateException("Contender disappeared");
            }
            if (info.getThreadState() == Thread.State.BLOCKED) {
                return info;
            }
            Thread.sleep(5);
        }
        throw new IllegalStateException("Did not observe BLOCKED");
    }

    public static void main(String[] args) throws InterruptedException {
        Object monitor = new Object();
        CountDownLatch ownerReady = new CountDownLatch(1);
        CountDownLatch releaseOwner = new CountDownLatch(1);
        AtomicBoolean contenderEntered = new AtomicBoolean();

        Thread owner = new Thread(() -> {
            synchronized (monitor) {
                ownerReady.countDown();
                try {
                    releaseOwner.await();
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "lock-owner");

        Thread contender = new Thread(() -> {
            synchronized (monitor) {
                contenderEntered.set(true);
            }
        }, "lock-contender");

        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        try {
            owner.start();
            if (!ownerReady.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Owner not ready");
            }
            contender.start();

            ThreadInfo blocked = awaitBlocked(bean, contender.threadId());
            System.out.println("state=" + blocked.getThreadState());
            System.out.println("ownerName=" + blocked.getLockOwnerName());
            System.out.println("ownerMatches="
                    + (blocked.getLockOwnerId() == owner.threadId()));
            System.out.println("lockClass="
                    + blocked.getLockInfo().getClassName());
            System.out.println("stackCaptured=" + Arrays.stream(
                    blocked.getStackTrace()).anyMatch(frame ->
                            frame.getClassName().equals(
                                    MonitorWaitDemo.class.getName())));

            long[] cycle = bean.findMonitorDeadlockedThreads();
            System.out.println("monitorDeadlock=" + (cycle != null));
        } finally {
            releaseOwner.countDown();
            owner.join(5_000);
            contender.join(5_000);
            if (owner.isAlive() || contender.isAlive()) {
                throw new IllegalStateException("Threads did not finish");
            }
        }
        System.out.println("contenderEntered=" + contenderEntered.get());
    }
}
```

Dùng chế độ chạy tệp nguồn trên JDK 21+:

```shell
java MonitorWaitDemo.java
```

Hoặc biên dịch rồi chạy:

```shell
javac MonitorWaitDemo.java
java MonitorWaitDemo
```

Stdout khi quan sát được tình huống trên JVM thông thường:

```text
state=BLOCKED
ownerName=lock-owner
ownerMatches=true
lockClass=java.lang.Object
stackCaptured=true
monitorDeadlock=false
contenderEntered=true
```

Chương trình đã kiểm tra snapshot đạt điều kiện BLOCKED, không giả định rằng ngủ một khoảng cố định là đủ để contender bị chặn.

Các lần `sleep(5)` trong `awaitBlocked()` chỉ giới hạn tần suất lấy mẫu của thí nghiệm. Latch điều khiển việc giữ/nhả khóa; đây không phải mô hình dùng ThreadInfo để đồng bộ nghiệp vụ. Có thời hạn 5 giây để không chờ vô hạn nếu môi trường không tạo được điều kiện quan sát.

### Cách đọc kết quả

- `state=BLOCKED`: contender đang chờ monitor.
- `ownerMatches=true`: id chủ sở hữu đúng là luồng ta chủ động tạo.
- `stackCaptured=true`: snapshot chứa frame của mã thí nghiệm.
- `monitorDeadlock=false`: không tìm thấy vòng monitor; hiện chỉ có quan hệ chờ một chiều.
- `contenderEntered=true`: sau khi mở latch, contender đã đi tiếp; đây là bằng chứng tiến triển sau khi giải phóng khóa.

Không in thread id, identity hash hoặc dòng stack cụ thể làm output chuẩn, vì chúng thay đổi giữa các lần chạy.

## 7. Thu thêm thông tin monitor và synchronizer

Một snapshot cơ bản không tự thu danh sách mọi khóa đang giữ. Khi cần chi tiết, kiểm tra khả năng JVM trước:

```java
// Đoạn minh họa cho việc thu snapshot chẩn đoán.
boolean monitors = bean.isObjectMonitorUsageSupported();
boolean synchronizers = bean.isSynchronizerUsageSupported();

ThreadInfo[] snapshot =
        bean.dumpAllThreads(monitors, synchronizers);

for (ThreadInfo info : snapshot) {
    // Phân tích trạng thái, stack, lock owner và danh sách khóa đã thu.
}
```

Tham số boolean có ý nghĩa yêu cầu thu dữ liệu tương ứng, không phải bật một kiểu khóa mới.

Snapshot có thể chứa nhiều luồng không liên quan đến yêu cầu đang chậm. Nên đặt tên luồng có ý nghĩa, liên hệ với vai trò pool và thu cùng dấu thời gian/tải hệ thống. Tránh biến một dump lớn thành một kết luận chỉ dựa trên một dòng có chữ “waiting”.

Việc thu stack và thông tin khóa có chi phí; không chạy dump toàn bộ quá dày chỉ vì có thể gọi API.

## 8. Số lần chờ và thời gian chờ phải đọc theo điều kiện thu thập

ThreadInfo còn có các chỉ số:

- `getBlockedCount()`: số lần vào trạng thái chờ monitor.
- `getBlockedTime()`: tổng thời gian chờ monitor được theo dõi.
- `getWaitedCount()` và `getWaitedTime()`: thống kê các trạng thái chờ liên quan theo hợp đồng API.

Thread contention monitoring có thể không được JVM hỗ trợ và mặc định có thể chưa bật. Kiểm tra:

```java
boolean supported = bean.isThreadContentionMonitoringSupported();
boolean enabled = supported
        && bean.isThreadContentionMonitoringEnabled();
```

Nếu monitoring bị tắt, thời gian chờ có thể là `-1`, không phải 0 mili giây. Bật lại monitoring có thể đặt lại thống kê thời gian, nên phải biết cửa sổ thu và trạng thái cấu hình trước khi so sánh.

Không tự bật/tắt một cấu hình toàn JVM liên tục trong endpoint chẩn đoán. Trên hệ thống thật, điều phối với cơ chế giám sát đang có và đánh giá chi phí.

`blockedTime` mô tả thời gian BLOCKED vì monitor; không dùng nó làm “tổng thời gian chờ mọi ReentrantLock” hoặc “độ trễ của yêu cầu”. Để đo một điểm nghẽn, cần lấy chênh lệch trên cùng luồng và khoảng quan sát phù hợp, rồi liên hệ stack/sự kiện.

Các khả năng đo và công tắc được định nghĩa trong [ThreadMXBean API](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ThreadMXBean.html).

## 9. Phát hiện deadlock và giới hạn của kết luận

Hai phương thức có phạm vi khác nhau:

| API | Loại chu kỳ tìm kiếm |
| --- | --- |
| `findMonitorDeadlockedThreads()` | Chu kỳ chờ object monitor |
| `findDeadlockedThreads()` | Chu kỳ liên quan monitor và ownable synchronizer được hỗ trợ |

Nếu muốn dùng phiên bản rộng hơn, kiểm tra khả năng theo dõi synchronizer của JVM. Không gọi một API có thể không hỗ trợ rồi diễn giải ngoại lệ thành “không có deadlock”.

Khi có id trả về, lấy thông tin và vẽ chuỗi chủ sở hữu/chờ để hiểu nguyên nhân. Khi trả null, chỉ kết luận **không tìm thấy loại chu kỳ trong phạm vi API tại thời điểm đó**.

Những trường hợp vẫn có thể làm hệ thống không tiến triển dù không có chu kỳ được phát hiện:

- Chờ I/O không có timeout.
- Pool thiếu luồng chạy tác vụ phụ thuộc.
- Luồng đợi điều kiện không bao giờ được phát.
- Quan hệ phụ thuộc qua dịch vụ ngoài.
- Vòng lặp hoạt động nhưng không làm việc hữu ích.

Không xử lý deadlock bằng cách tự ý dừng một luồng đang giữ khóa. Cần sửa thứ tự lấy khóa, ranh giới vùng khóa, quan hệ phụ thuộc hoặc cơ chế timeout/cancel phù hợp.

## 10. Giới hạn quan trọng trên JDK hiện đại: platform threads và virtual threads

ThreadMXBean hiện hỗ trợ giám sát và quản lý **platform threads**, không hỗ trợ đầy đủ virtual threads theo hợp đồng API hiện hành.

Vì vậy, một ứng dụng có rất nhiều virtual thread không thể được chẩn đoán bằng cách coi `getAllThreadIds()` hoặc `dumpAllThreads()` của MXBean là toàn bộ các luồng ứng dụng.

Ví dụ trong bài dùng `new Thread(...)`, tức platform thread. Kết quả quan sát không được suy rộng thành tuyên bố rằng cùng API sẽ liệt kê mọi virtual thread trong một dịch vụ dùng luồng ảo.

Khi chẩn đoán ứng dụng như vậy, chọn công cụ dump/sự kiện hỗ trợ virtual thread của đúng JDK triển khai. Không suy ra “không có luồng đang chờ” chỉ từ một nguồn dữ liệu không theo dõi loại luồng đó.

Thread id Java cũng không tự là id luồng hệ điều hành. Không ghép tùy ý id trong ThreadInfo với cột id của một công cụ OS mà chưa hiểu quy tắc ánh xạ.

## 11. Đối chiếu bằng công cụ ngoài tiến trình

Với JVM đang chạy và quyền truy cập phù hợp, có thể kiểm tra lệnh hỗ trợ bằng:

```shell
jcmd PID help Thread.print
jcmd PID Thread.print -l
```

`PID` ở đây là ký hiệu cần thay bằng pid thật, không phải một lệnh có thể chạy nguyên văn. Cần chọn đúng tiến trình, không dùng phạm vi “tất cả JVM” để lấy dữ liệu không liên quan.

Với lệnh dump hỗ trợ ở JDK hiện đại, có thể xem:

```shell
jcmd PID help Thread.dump_to_file
```

Sau đó dùng cú pháp và định dạng mà JDK mục tiêu công bố. Phạm vi thông tin và định dạng của các loại dump không nhất thiết giống ThreadMXBean.

Quyền truy cập, cách lấy help và các lệnh được mô tả trong [jcmd manual](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html).

Trong điều tra sự cố, thường hữu ích hơn khi lấy vài snapshot cách nhau một khoảng hợp lý, đối chiếu với CPU, độ trễ và độ dài hàng đợi. Một snapshot cho biết “đang ở đâu”; nhiều snapshot giúp biết “có tiến triển hay không”.

## 12. Quy trình đọc bằng chứng và chọn cách sửa

1. Xác nhận yêu cầu đang chậm và khoảng thời gian xảy ra.
2. Xác định phạm vi dữ liệu: JVM nào, loại luồng nào, stack có bị cắt quá ngắn không.
3. Nhóm các luồng cùng chờ một khóa/đường gọi.
4. Đi tới chủ sở hữu và xem nó đang giữ khóa để làm gì.
5. Thu thêm snapshot để phân biệt một lần chờ ngắn với trạng thái lặp kéo dài.
6. Kiểm tra chu kỳ deadlock trong phạm vi công cụ.
7. Liên hệ dữ liệu runtime với đoạn mã lấy/nhả khóa.
8. Sửa nguyên nhân rồi lặp lại phép đo dưới tải tương đương.

Hướng sửa có thể là chuyển I/O ra ngoài vùng khóa, thu hẹp dữ liệu được bảo vệ, tránh giữ khóa qua chờ Future hoặc thống nhất thứ tự lấy nhiều khóa. Không bỏ khóa chỉ vì thấy tranh chấp nếu khóa đang bảo vệ một bất biến cần thiết.

## 13. Bài tập mở rộng và tự kiểm tra

Các ca nên thực hiện:

| Ca | Kỳ vọng học được |
| --- | --- |
| Thu snapshot trước khi contender chạy | Không nhầm NEW/RUNNABLE với BLOCKED |
| Sau khi release owner | Contender kết thúc và id có thể không còn ThreadInfo |
| Thay monitor bằng ReentrantLock | Quan sát WAITING/park và thông tin synchronizer khác |
| Chỉ lấy stack depth 0 | Hiểu vì sao thiếu frame không chứng minh luồng không ở mã ứng dụng |
| Monitoring thời gian đang tắt | Xử lý -1 thay vì coi đó là 0 |
| Không tìm thấy deadlock | Vẫn kiểm tra điều kiện chờ và tiến triển |

Câu hỏi tự kiểm tra:

1. BLOCKED có nghĩa là mọi loại chờ khóa không? **Không; nó dành cho chờ monitor theo trạng thái JVM.**
2. Có lock owner thì đã biết nguyên nhân cuối chưa? **Chưa; phải xem chủ sở hữu đang làm gì và có chờ tiếp ai không.**
3. WAITING có luôn là lỗi không? **Không; nhiều luồng chờ công việc đúng thiết kế.**
4. ThreadInfo null có luôn là lỗi MXBean không? **Không; luồng có thể đã kết thúc.**
5. Thời gian chờ -1 có nghĩa không chờ không? **Không; có thể chưa bật thu thập.**
6. Không tìm thấy deadlock có nghĩa hệ thống khỏe không? **Không; phạm vi phát hiện có giới hạn.**
7. MXBean này có liệt kê mọi virtual thread không? **Không theo hợp đồng hiện hành.**
