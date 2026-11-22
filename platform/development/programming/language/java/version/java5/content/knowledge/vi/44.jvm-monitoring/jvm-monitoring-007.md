# Phát hiện luồng chờ khóa và deadlock trong phạm vi được hỗ trợ

## 1. Chờ khóa chưa đủ kết luận deadlock

Một ứng dụng đứng yên có thể đang chờ máy chủ bên ngoài, chờ tác vụ khác hoàn tất hoặc tranh chấp khóa. Cần phân biệt **chờ tạm thời** với **bế tắc (deadlock)**: các luồng giữ tài nguyên mà luồng khác trong chu trình cần, khiến không luồng nào tự tiếp tục được.

Ví dụ hai luồng:

```text
A giữ khóa L1, chờ L2 do B giữ
B giữ khóa L2, chờ L1 do A giữ

Quan hệ chờ theo chủ sở hữu: A -> B -> A
```

Nếu A chỉ chờ B giữ một khóa và B vẫn có thể hoàn thành để nhả khóa, đó có thể là tranh chấp bình thường. Một luồng ở trạng thái chờ lâu là tín hiệu cần điều tra, chưa phải bằng chứng của chu trình.

Trong Java, `ThreadMXBean` cung cấp dữ liệu luồng và phép tìm một số chu trình chờ khóa. Phải biết **loại luồng, loại khóa và khả năng JVM** trước khi diễn giải kết quả. [ThreadMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html).

## 2. Phân biệt trạng thái chờ và loại khóa

| Tình huống | Trạng thái thường thấy | Điều cần đọc tiếp |
| --- | --- | --- |
| Chờ vào khối/phương thức `synchronized` | `BLOCKED` | Monitor nào và luồng nào đang sở hữu |
| Chờ `ReentrantLock` bằng cơ chế đỗ luồng | Thường là `WAITING` hoặc `TIMED_WAITING` nếu có thời hạn | Stack, khóa và chủ sở hữu |
| Chờ thông báo qua `Object.wait()` | `WAITING` hoặc `TIMED_WAITING` | Điều kiện nào cần được thay đổi |
| Chờ tác vụ, latch hoặc kết quả | Có thể là trạng thái chờ | Tác vụ hoặc bên phát tín hiệu có còn tiến triển không |

`BLOCKED` trong `Thread.State` có nghĩa cụ thể là chờ **monitor lock**, không phải nhãn chung cho mọi thao tác không tiến triển. `RUNNABLE` cũng không chứng minh luồng đang tiêu thụ CPU liên tục: nó có thể chờ tài nguyên hệ điều hành. Các trạng thái này là trạng thái của JVM, không phải bản sao trực tiếp trạng thái luồng hệ điều hành. [Thread.State](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.State.html).

`Object.wait()` nhả monitor của chính đối tượng được gọi trong khi chờ và phải lấy lại nó trước khi tiếp tục. Không giả định luồng vẫn giữ monitor đó suốt thời gian `wait()`; nó có thể vẫn giữ những khóa khác bên ngoài. Tương tự, `Condition.await()` nhả khóa liên kết theo hợp đồng condition. Việc chờ một tín hiệu không tự tạo một chủ sở hữu khóa để detector nối thành chu trình. [Object.wait](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Object.html), [Condition](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/Condition.html).

## 3. Hai loại khóa mà detector có thể nhận biết

**Monitor đối tượng** là khóa nội tại dùng bởi `synchronized`. Thông tin monitor có thể đi kèm vị trí stack nơi nó được giữ, thông qua `MonitorInfo`. [MonitorInfo](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MonitorInfo.html).

**Bộ đồng bộ có chủ sở hữu độc quyền (ownable synchronizer)** là cấu trúc có một luồng sở hữu độc quyền và công bố quan hệ đó qua hạ tầng hỗ trợ. `ReentrantLock` và khóa ghi của `ReentrantReadWriteLock` là các ví dụ; khóa đọc của read-write lock không nằm trong ví dụ sở hữu độc quyền này. Không suy từ tên `java.util.concurrent` rằng mọi công cụ đồng bộ trong package đều được phát hiện giống nhau. [LockInfo](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/LockInfo.html).

Cơ sở `AbstractOwnableSynchronizer` cho phép triển khai ghi nhận chủ sở hữu. Bản thân nó không tự quản lý mọi quy tắc khóa; mã triển khai phải duy trì thông tin đúng để công cụ chẩn đoán sử dụng được. Một khóa tự viết, một khóa trong thư viện native hoặc một giao thức nghiệp vụ không mặc nhiên được JVM hiểu như ownable synchronizer. [AbstractOwnableSynchronizer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/AbstractOwnableSynchronizer.html).

## 4. Chọn phép phát hiện đúng phạm vi

Lấy bean trong JVM hiện tại:

```java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();
```

Hai phương thức tìm chu trình khác nhau:

| API | Phạm vi phát hiện |
| --- | --- |
| `findMonitorDeadlockedThreads()` | Chu trình luồng nền tảng chờ monitor đối tượng |
| `findDeadlockedThreads()` | Chu trình luồng nền tảng chờ monitor và/hoặc ownable synchronizer |

`findDeadlockedThreads()` yêu cầu JVM hỗ trợ giám sát ownable synchronizer; kiểm tra `isSynchronizerUsageSupported()`. Nếu không hỗ trợ, có thể dùng phép tìm monitor nhưng phải ghi rõ phạm vi đã thu hẹp. Không đổi tên kết quả đó thành “không có deadlock trong ứng dụng”.

Mã minh họa chọn chế độ:

```java
boolean synchronizers = bean.isSynchronizerUsageSupported();
long[] ids = synchronizers
        ? bean.findDeadlockedThreads()
        : bean.findMonitorDeadlockedThreads();
```

`null` có nghĩa không tìm thấy chu trình thuộc phạm vi phép gọi ở thời điểm kiểm tra. Nó không phải mảng một phần tử, không phải lỗi tự động và không bảo đảm ứng dụng đang tiến triển. Các phép tìm này dành cho chẩn đoán, có thể có chi phí; không dùng chúng làm cơ chế điều phối lấy khóa trong nghiệp vụ. [ThreadMXBean: deadlock detection](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html#findDeadlockedThreads()).

## 5. Đọc ThreadInfo để dựng quan hệ chờ

Sau khi có ID, lấy ảnh chụp chi tiết. Đoạn minh họa sau dành cho Java 17+ và cần biến `ids` không `null`:

```java
boolean monitors = bean.isObjectMonitorUsageSupported();
boolean synchronizers = bean.isSynchronizerUsageSupported();
ThreadInfo[] infos =
        bean.getThreadInfo(ids, monitors, synchronizers, 64);
```

Chỉ yêu cầu danh sách monitor hoặc synchronizer đang giữ khi JVM hỗ trợ loại thông tin đó. Không bật cờ `true, true` trên mọi JVM rồi bỏ qua ngoại lệ. Giới hạn stack depth giúp kiểm soát lượng dữ liệu; chọn độ sâu đủ để thấy đường gọi ứng dụng.

Các trường hữu ích:

| Trường | Cách dùng |
| --- | --- |
| `getThreadId()`, `getThreadName()` | Nhận diện luồng của ảnh chụp |
| `getThreadState()` | Bối cảnh thực thi tại thời điểm lấy mẫu |
| `getLockInfo()` | Đối tượng khóa/chờ liên quan, nếu có |
| `getLockOwnerId()`, `getLockOwnerName()` | Nối tới luồng sở hữu, khi xác định được |
| `getLockedMonitors()` | Các monitor đang giữ nếu đã yêu cầu thông tin |
| `getLockedSynchronizers()` | Các ownable synchronizer đang giữ nếu đã yêu cầu |
| `getStackTrace()` | Tìm đường gọi ứng dụng dẫn tới việc chờ |

Tên luồng hỗ trợ đọc log; ID giúp nối các nút trong cùng lần quan sát. `getLockOwnerId() == -1` hoặc chủ sở hữu `null` không được diễn giải thành “khóa thuộc luồng -1”. Đó là trạng thái không có chủ sở hữu xác định theo hợp đồng dữ liệu. [ThreadInfo](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadInfo.html).

Ảnh chụp có thể không còn phản ánh hiện tại khi bạn xử lý xong. Phần tử `ThreadInfo` có thể `null` nếu luồng không còn sống, không tồn tại hoặc không thuộc phạm vi hỗ trợ. Cũng đừng thấy mảng khóa rỗng rồi kết luận luồng không giữ khóa nếu lần gọi trước đó không yêu cầu thu thập phần đó.

`LockInfo` mô tả lớp và identity hash của đối tượng khóa; nó không cung cấp tham chiếu đối tượng để công cụ tùy tiện nhả khóa. Giá trị hash phục vụ nhận diện trong chẩn đoán, không phải địa chỉ bộ nhớ ổn định dùng xuyên nhiều JVM. [LockInfo](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/LockInfo.html).

## 6. Ví dụ chạy hoàn chỉnh: phát hiện rồi kết thúc sạch

Chương trình dùng **Java 21+**, tạo rõ hai luồng nền tảng qua `Thread.ofPlatform()`. Hai luồng cố ý lấy hai `ReentrantLock` theo thứ tự ngược nhau.

`CountDownLatch` bảo đảm cả hai đã lấy khóa đầu trước khi cố lấy khóa thứ hai. Nó loại việc đoán lịch chạy bằng một khoảng ngủ tùy ý. Latch về 0 sau đủ lần `countDown()`, rồi các bên đang `await()` có thể tiếp tục. [CountDownLatch](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CountDownLatch.html).

Lưu thành `SupportedDeadlockDemo.java`:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.Arrays;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public class SupportedDeadlockDemo {
    static void work(ReentrantLock first, ReentrantLock second,
                     CountDownLatch firstLocksHeld) {
        try {
            first.lockInterruptibly();
            try {
                firstLocksHeld.countDown();
                firstLocksHeld.await();
                second.lockInterruptibly();
                try {
                    // Chỉ quan sát quyền sở hữu khóa, không xử lý nghiệp vụ.
                } finally {
                    second.unlock();
                }
            } finally {
                first.unlock();
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        }
    }

    static boolean contains(long[] ids, long id) {
        return ids != null && Arrays.stream(ids).anyMatch(v -> v == id);
    }

    public static void main(String[] args) throws Exception {
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        if (!bean.isSynchronizerUsageSupported()) {
            System.out.println("SKIPPED: ownable synchronizers not supported");
            return;
        }

        ReentrantLock lockOne = new ReentrantLock();
        ReentrantLock lockTwo = new ReentrantLock();
        CountDownLatch firstLocksHeld = new CountDownLatch(2);

        Thread a = Thread.ofPlatform().daemon().name("worker-A")
                .unstarted(() -> work(lockOne, lockTwo, firstLocksHeld));
        Thread b = Thread.ofPlatform().daemon().name("worker-B")
                .unstarted(() -> work(lockTwo, lockOne, firstLocksHeld));

        try {
            a.start();
            b.start();
            long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
            boolean found = false;
            while (System.nanoTime() - deadline < 0) {
                long[] ids = bean.findDeadlockedThreads();
                if (contains(ids, a.threadId()) && contains(ids, b.threadId())) {
                    found = true;
                    break;
                }
                Thread.sleep(20);
            }
            if (!found) {
                throw new IllegalStateException("Detection deadline exceeded");
            }

            System.out.println("Deadlock found=true");
            ThreadInfo[] infos = bean.getThreadInfo(
                    new long[] {a.threadId(), b.threadId()}, false, true);
            for (ThreadInfo info : infos) {
                if (info == null) {
                    throw new IllegalStateException("Thread snapshot unavailable");
                }
                System.out.println(info.getThreadName() +
                        " waits for " + info.getLockOwnerName());
            }
        } finally {
            a.interrupt();
            b.interrupt();
            a.join(2000);
            b.join(2000);
            if (a.isAlive() || b.isAlive()) {
                throw new IllegalStateException("Demo cleanup failed");
            }
        }
        System.out.println("Demo threads terminated=true");
    }
}
```

Chạy trong một JVM riêng:

```shell
javac SupportedDeadlockDemo.java
java SupportedDeadlockDemo
```

Trên JVM hỗ trợ ownable synchronizer, đầu ra khi phát hiện thành công:

```text
Deadlock found=true
worker-A waits for worker-B
worker-B waits for worker-A
Demo threads terminated=true
```

Nếu JVM không hỗ trợ, chương trình chỉ in:

```text
SKIPPED: ownable synchronizers not supported
```

Nếu lịch chạy hoặc môi trường khiến phát hiện không hoàn tất trong hạn, chương trình báo lỗi `Detection deadline exceeded` thay vì in một kết luận sai. Khoảng ngủ 20 ms chỉ giảm nhịp thăm dò; sự phối hợp để tạo chu trình do latch thực hiện.

### Vì sao ví dụ tự kết thúc được?

Chỗ lấy khóa thứ hai dùng `lockInterruptibly()`. Khi luồng chính đã thu bằng chứng, nó ngắt hai luồng; luồng chờ có thể nhận `InterruptedException`, đi qua `finally` và nhả khóa đang giữ. Chương trình `join()` có hạn rồi kiểm tra hai luồng đã kết thúc. Việc đặt daemon là lớp dự phòng cho tiến trình minh họa, không phải cách sửa deadlock. [ReentrantLock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html).

Khả năng ngắt có hợp tác là một phần thiết kế cụ thể của ví dụ. Detector **không** tự giải phóng khóa. Nếu đổi thành `synchronized` đang chờ vào monitor hoặc một cơ chế chờ không hỗ trợ ngắt, không được giả định `interrupt()` sẽ phá chu trình tương tự. `Lock` phân biệt lấy khóa thường, có ngắt và có thời hạn; cần đọc hợp đồng từng triển khai. [Lock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/Lock.html).

## 7. Không đồng nhất thống kê tranh chấp với phát hiện deadlock

`getBlockedCount()` đếm số lần luồng bị chặn khi vào hoặc vào lại monitor. `getBlockedTime()` là thời gian tích lũy liên quan tới monitor kể từ khi bật theo dõi tranh chấp; có thể không có giá trị đo hợp lệ nếu theo dõi bị tắt.

Nó không phải tổng mọi thời gian chờ `ReentrantLock`, chờ mạng hoặc chờ cơ sở dữ liệu. Không xếp hạng “luồng giữ mọi thứ lâu nhất” bằng cách gom các chỉ số này mà bỏ qua loại chờ. [ThreadInfo](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadInfo.html).

Phát hiện chu trình không đòi hỏi bật đo thời gian tranh chấp. Nếu cần thống kê đó cho điều tra khác, kiểm tra hỗ trợ trước khi bật, cân nhắc chi phí và ghi nhận mốc bắt đầu. Giá trị lớn cho thấy lịch sử chờ; nó không chứng minh tại thời điểm đọc có một chu trình bế tắc.

## 8. Những điểm mù phải ghi rõ trong kết luận

### Luồng ảo

`ThreadMXBean` giám sát luồng nền tảng, không quản lý luồng ảo. Chu trình có luồng ảo không được `findDeadlockedThreads()` phát hiện theo hợp đồng API. Không lấy số luồng nền tảng hoặc kết quả `null` rồi suy rộng cho toàn bộ tác vụ dùng luồng ảo.

Khi cần dữ liệu luồng ảo, dùng công cụ tương ứng với JDK đang triển khai. Tài liệu Java 21 mô tả `jcmd Thread.dump_to_file` có cả luồng nền tảng và luồng ảo, nhưng dạng dump này không có toàn bộ thông tin khóa như dump truyền thống. Nhìn thấy các stack không tự đồng nghĩa có detector khóa đầy đủ. [Virtual Threads: Debugging](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html).

### Chờ kết quả hoặc điều kiện nghiệp vụ

`Future.get()` có thể chờ kết quả tác vụ khác. Một nhóm worker cùng chờ các tác vụ chưa có worker để chạy có thể làm hệ thống không tiến triển mà không tạo chu trình monitor/ownable synchronizer.

Tương tự, chờ latch không được giảm, condition không được phát tín hiệu, tài nguyên cơ sở dữ liệu hoặc lời gọi từ xa không mặc nhiên nằm trong đồ thị khóa mà API này hiểu. Cần điều tra tác vụ, hàng đợi, tài nguyên và bên phát tín hiệu theo cơ chế thực tế. [Future](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html), [Condition](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/Condition.html).

### Thiếu dữ liệu hoặc thiếu khả năng

JVM không hỗ trợ phần giám sát, yêu cầu thu thập không đúng hoặc truy cập thất bại phải được báo là “không thu được bằng chứng đầy đủ”. Không bắt mọi ngoại lệ rồi trả `false` với nhãn “không có deadlock”.

## 9. Quy trình điều tra trong ứng dụng thật

1. **Xác định phạm vi:** JVM đích, phiên bản, luồng nền tảng hay luồng ảo và khả năng giám sát.
2. **Chụp bằng chứng:** thời điểm, phương thức detector đã dùng, ID, trạng thái, stack và quan hệ chủ sở hữu.
3. **Dựng chu trình:** với mỗi luồng, chỉ rõ nó đang giữ gì và chờ gì; đối chiếu đường gọi nghiệp vụ.
4. **Lấy thêm mẫu hợp lý:** phân biệt một đợt tranh chấp với hệ thống tiếp tục đứng yên; tránh dump toàn bộ luồng liên tục.
5. **Chọn phục hồi theo thiết kế ứng dụng:** hủy có hợp tác, giải phóng tài nguyên và xử lý lại giao dịch khi phù hợp; nếu cần khởi động lại thì vẫn lưu bằng chứng để sửa nguyên nhân.

Khi không sửa được mã đang chạy, trên JDK hỗ trợ có thể bắt đầu bằng:

```shell
jcmd <pid> help Thread.print
jcmd <pid> Thread.print -l
```

`<pid>` là ID tiến trình Java cần điều tra. `-l` yêu cầu thông tin khóa `java.util.concurrent` trong dump truyền thống. Dùng `help` của JVM đích để xác minh lệnh và chọn công cụ đúng loại luồng; thao tác dump có chi phí theo quy mô. [jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).

## 10. Sửa nguyên nhân thay vì chỉ phát hiện

Với trường hợp hai khóa trong ví dụ, quy định cùng một thứ tự lấy khóa ở mọi đường gọi có thể loại việc A lấy L1→L2 còn B lấy L2→L1. Nếu thứ tự dựa trên tài nguyên động, cần quy tắc ổn định và cách xử lý hòa; không chỉ đổi thứ tự trong một phương thức rồi bỏ sót đường khác.

Thu hẹp vùng giữ khóa và tránh gọi mã ngoài quyền kiểm soát khi đang giữ khóa, nhất là I/O hoặc callback có thể quay lại ứng dụng. Khi dùng khóa tường minh, luôn nhả trong `finally` sau khi thực sự lấy được khóa. [ReentrantLock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html).

`tryLock(timeout, unit)` có thể hỗ trợ thiết kế bỏ cuộc và thử lại, nhưng không tự bảo đảm tính đúng đắn. Phải nhả các khóa đã lấy nếu không lấy đủ, quyết định cách hủy/hoàn tác và tránh các bên thử lại đồng bộ gây không tiến triển. “Chuyển sang khóa công bằng” cũng không sửa một chu trình lấy khóa ngược thứ tự.

Tự kiểm tra:

- **Một luồng WAITING có chắc deadlock không?** Không; cần cơ chế chờ và quan hệ phụ thuộc.
- **Hai luồng ReentrantLock mắc vòng chờ có chắc xuất hiện trong phép tìm chỉ monitor không?** Không; cần phép tìm và khả năng hỗ trợ phù hợp.
- **Detector trả null có chứng minh không có chu trình chứa luồng ảo không?** Không.
- **Có ID deadlock thì có thể từ luồng quản trị nhả mọi khóa không?** Không; phải phục hồi theo quyền sở hữu và hợp đồng đồng bộ.

Một kết luận chẩn đoán tốt phải nói được **đã quan sát loại luồng nào, loại khóa nào, tại thời điểm nào và còn thiếu bằng chứng gì**. Nhờ đó, kết quả phát hiện giúp tìm nguyên nhân mà không tạo cảm giác bảo đảm vượt phạm vi API.
