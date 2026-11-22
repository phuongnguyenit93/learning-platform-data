# Nhận diện deadlock, chờ lâu và cạn luồng

## 1. “Ứng dụng đứng” là triệu chứng, chưa phải nguyên nhân

Một API không trả lời có thể do luồng đang chờ khóa, đợi dữ liệu mạng, đợi Future hoặc chưa được executor cấp worker. Các trường hợp ấy có thể nhìn giống nhau từ phía người dùng nhưng cần cách xử lý khác nhau.

Ba khái niệm cần phân biệt:

| Hiện tượng | Bản chất | Dấu hiệu cần tìm |
| --- | --- | --- |
| Bế tắc — deadlock | Một vòng phụ thuộc làm các bên không thể tự tiến triển theo giao thức hiện tại | Ai giữ tài nguyên nào, ai đợi ai, có vòng kín không |
| Chờ lâu | Một điều kiện chưa đạt trong thời gian dài | Bên có thể làm điều kiện đạt còn chạy không; có tiến triển không |
| Cạn luồng / thiếu worker khả dụng | Công việc cần luồng nhưng mọi worker phù hợp đã bận hoặc không thể tạo thêm luồng | Trạng thái pool, hàng đợi, tác vụ đang giữ worker, giới hạn hệ thống |

CPU thấp không chứng minh chương trình khỏe. Nhiều luồng cùng chờ nhau có thể khiến CPU thấp nhưng thông lượng gần bằng 0.

CPU cao cũng không loại trừ mọi vấn đề tiến triển. Một vòng lặp thử lại, quay chờ hoặc livelock có thể tiêu CPU mà không hoàn tất công việc nghiệp vụ.

Bài dùng API chẩn đoán còn phù hợp trên Java hiện đại, với ví dụ chạy trên Java 17+. Khi nhắc virtual thread, bài nêu rõ giới hạn của công cụ để không áp dụng kết luận dành cho platform thread một cách máy móc.

## 2. Đọc trạng thái luồng nhưng đừng kết luận chỉ từ tên trạng thái

| Trạng thái JVM | Điều có thể suy ra | Điều chưa thể suy ra |
| --- | --- | --- |
| BLOCKED | Đang đợi vào một monitor, thường liên quan synchronized | Chưa biết là deadlock hay tranh chấp ngắn hạn |
| WAITING | Đợi một hành động khác không có thời hạn tại điểm đó | Chưa biết bên phát tín hiệu có tồn tại và còn tiến triển không |
| TIMED_WAITING | Đợi với thời hạn theo API đang dùng | Không bảo đảm mọi tài nguyên sẽ được giải phóng đúng hạn |
| RUNNABLE | Đang ở trạng thái runnable của JVM | Không có nghĩa chắc chắn đang tiêu CPU hoặc làm việc hữu ích |

Một luồng đợi `ReentrantLock` thường xuất hiện với stack parking/chờ trong thư viện đồng bộ, không nhất thiết là BLOCKED. BLOCKED có ý nghĩa cụ thể về monitor; không dùng nó như tên chung của mọi việc chặn.

Worker của một pool nhàn rỗi đợi lấy việc từ hàng đợi có thể ở WAITING. Đây thường là bình thường. Worker ở WAITING trong `Future.get()` lại có thể đang giữ một slot executor trong lúc đợi kết quả.

Trạng thái chỉ là ảnh chụp tại một thời điểm. Cần ghép nó với stack, chủ khóa, dữ liệu hàng đợi và chuỗi ảnh chụp. Xem [Thread.State](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.State.html) để hiểu đúng phạm vi các trạng thái JVM.

## 3. Nhận diện deadlock bằng đồ thị phụ thuộc

Ví dụ hai khóa:

```text
Luồng A giữ khóa X -> đợi khóa Y
Luồng B giữ khóa Y -> đợi khóa X
```

Không bên nào rời điểm chờ để trả khóa người kia cần. Đồ thị tạo thành vòng:

```text
A -> Y do B giữ -> B -> X do A giữ -> A
```

Cần tìm **quyền sở hữu và cạnh đợi**, không chỉ đếm số luồng chờ.

Một đoạn thread dump có hình thức minh họa như sau, không phải output cố định của mọi JDK:

```text
"worker-A"
  waiting to lock <Y>
  locked <X>

"worker-B"
  waiting to lock <X>
  locked <Y>
```

Nếu dump có thông báo phát hiện Java-level deadlock, hãy xem phần liệt kê chuỗi khóa để xác định vòng. Không dừng ở dòng cảnh báo mà bỏ qua khóa và đoạn mã tạo thứ tự lấy khóa trái nhau.

### ThreadMXBean phát hiện được phạm vi nào?

`ThreadMXBean.findMonitorDeadlockedThreads()` nhắm tới vòng deadlock của monitor. `findDeadlockedThreads()` mở rộng tới monitor và các ownable synchronizer được JVM hỗ trợ, chẳng hạn cơ chế khóa có chủ sở hữu của ReentrantLock.

Cần kiểm tra hỗ trợ của JVM đối với thông tin synchronizer khi dùng những khả năng tương ứng. Kết quả null chỉ có nghĩa không phát hiện vòng thuộc phạm vi công cụ tại thời điểm ấy.

Nó không phải bộ giải mọi đồ thị phụ thuộc nghiệp vụ. Ví dụ, một tác vụ đợi Future của tác vụ đang kẹt trong hàng đợi có thể không được báo như deadlock khóa.

Trên Java hiện đại, [ThreadMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html) quản lý/quan sát platform thread và không hỗ trợ giám sát virtual thread theo cùng giao diện này. Không dùng kết quả “không phát hiện” của nó để kết luận mọi loại luồng trong ứng dụng đều không bế tắc.

## 4. Thí nghiệm deadlock có phát hiện và cleanup

Ví dụ cố tình lấy hai ReentrantLock theo thứ tự ngược nhau. Cả hai lần lấy khóa dùng `lockInterruptibly()`, nên chương trình có thể yêu cầu ngắt để giải phóng thí nghiệm sau khi chẩn đoán.

Lưu thành `DetectableDeadlockDemo.java`:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public class DetectableDeadlockDemo {
    private static void takeInOrder(
            ReentrantLock first,
            ReentrantLock second,
            CountDownLatch bothHolding) {
        try {
            first.lockInterruptibly();
            try {
                bothHolding.countDown();
                bothHolding.await();

                second.lockInterruptibly();
                try {
                    // Chỉ tới đây nếu lấy được cả hai khóa.
                } finally {
                    second.unlock();
                }
            } finally {
                first.unlock();
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    public static void main(String[] args) throws Exception {
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        if (!bean.isSynchronizerUsageSupported()) {
            throw new UnsupportedOperationException(
                    "ownable synchronizer diagnostics unavailable");
        }

        ReentrantLock left = new ReentrantLock();
        ReentrantLock right = new ReentrantLock();
        CountDownLatch bothHolding = new CountDownLatch(2);

        Thread first = new Thread(
                () -> takeInOrder(left, right, bothHolding),
                "deadlock-demo-A");
        Thread second = new Thread(
                () -> takeInOrder(right, left, bothHolding),
                "deadlock-demo-B");

        first.start();
        second.start();

        try {
            Set<String> expected = Set.of(
                    "deadlock-demo-A", "deadlock-demo-B");
            Set<String> detected = new HashSet<>();
            long started = System.nanoTime();
            long budget = TimeUnit.SECONDS.toNanos(5);

            while (System.nanoTime() - started < budget) {
                long[] ids = bean.findDeadlockedThreads();
                if (ids != null) {
                    for (ThreadInfo info :
                            bean.getThreadInfo(ids, true, true)) {
                        if (info != null
                                && expected.contains(info.getThreadName())) {
                            detected.add(info.getThreadName());
                        }
                    }
                }
                if (detected.size() == 2) {
                    break;
                }
                Thread.sleep(10);
            }

            if (detected.size() != 2) {
                throw new IllegalStateException(
                        "demo deadlock was not detected in time");
            }
            System.out.println("Detected demo threads: "
                    + detected.size());
        } finally {
            first.interrupt();
            second.interrupt();
            first.join(5_000);
            second.join(5_000);
        }

        System.out.println("Cleanup finished: "
                + (!first.isAlive() && !second.isAlive()));
    }
}
```

Chạy trên JDK có hỗ trợ chẩn đoán ownable synchronizer:

```shell
javac DetectableDeadlockDemo.java
java DetectableDeadlockDemo
```

Stdout trong lần chạy thành công:

```text
Detected demo threads: 2
Cleanup finished: true
```

Latch chỉ bảo đảm mỗi luồng đã giữ khóa đầu trước khi thử lấy khóa sau. Việc ngủ 10 ms nằm trong vòng lấy mẫu chẩn đoán để tránh quay liên tục; nó không tạo quan hệ đồng bộ hoặc sửa deadlock.

Không suy ra rằng có thể ngắt để thoát mọi deadlock. Đợi vào monitor của `synchronized` không có cùng cơ chế ngắt như `lockInterruptibly()`. Thí nghiệm chủ động chọn API có thể hủy để không để lại hai luồng treo.

## 5. Chờ lâu: truy tìm bên có thể làm điều kiện thay đổi

Chờ lâu có thể là bình thường hoặc bất thường:

| Điểm chờ | Bên/sự kiện làm nó tiến triển | Câu hỏi chẩn đoán |
| --- | --- | --- |
| Lấy khóa | Chủ khóa mở khóa | Chủ khóa đang làm gì và đã giữ bao lâu? |
| CountDownLatch.await | Đủ lần countDown | Có tác vụ nào lỗi hoặc chưa được chạy không? |
| Future.get | Phép tính hoàn tất/hủy | Tác vụ thật đang chạy ở đâu? |
| Semaphore.acquire | Có giấy phép được trả/cấp | Giấy phép có bị rò rỉ, trả sai hoặc giữ quá lâu không? |
| BlockingQueue.take | Có phần tử vào hàng đợi | Đầu vào đang vắng hay producer đã dừng? |
| Đọc mạng | Phía ngoài gửi dữ liệu hoặc I/O kết thúc | Thời hạn I/O, phía ngoài và kết nối đang thế nào? |

Một lần chờ 10 giây có thể phù hợp với tác vụ dài nhưng bất thường với đường xử lý vốn chỉ mất vài mili giây. Cần so với hợp đồng và dữ liệu nền của hệ thống, không dùng một ngưỡng tuyệt đối cho mọi dịch vụ.

Dấu hiệu hữu ích qua nhiều mẫu:

- Chủ khóa vẫn chạy và vị trí stack/CPU thay đổi: có thể là công việc dài hoặc vùng khóa quá rộng.
- Hàng đợi giảm và số tác vụ hoàn tất tăng: vẫn có tiến triển, dù chậm.
- Cùng một cạnh đợi kéo dài, không có bên phát tín hiệu sống: nghi lỗi giao thức.
- Tác vụ đợi I/O ngoài nhưng không có thời hạn: phụ thuộc có thể kéo dài vô hạn.
- Luồng RUNNABLE có CPU tăng mạnh mà không hoàn tất: xem vòng lặp, tính toán quá lớn hoặc quay chờ.

Nhiều dump có cùng stack chưa đủ để kết luận deadlock. Một tác vụ I/O hợp lệ hoặc worker nhàn rỗi cũng có thể nằm cùng vị trí trong thời gian dài.

## 6. Cạn worker trong pool khác với deadlock khóa

Xét executor chỉ có một worker:

```text
Tác vụ cha giữ worker duy nhất
       |
       +-> submit tác vụ con vào cùng pool
       |
       +-> get kết quả tác vụ con

Tác vụ con nằm trong hàng đợi
       |
       +-> cần worker để bắt đầu
```

Tác vụ cha chờ con, nhưng con không thể chạy trước khi cha nhường worker. Đây thường được gọi là **bế tắc do thiếu luồng thực thi (thread starvation deadlock)** trong trường hợp quan hệ bị kẹt ổn định như trên.

Không có hai monitor tạo vòng để bộ phát hiện khóa nhất thiết báo ra. Tài nguyên đang thiếu là khả năng chạy tác vụ trong executor.

### Thí nghiệm một worker, một tác vụ con trong hàng đợi

Lưu thành `PoolDependencyDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class PoolDependencyDemo {
    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0, TimeUnit.MILLISECONDS,
                new LinkedBlockingQueue<>());

        CountDownLatch childQueued = new CountDownLatch(1);
        AtomicReference<Future<Integer>> childRef =
                new AtomicReference<>();

        try {
            Future<Integer> parent = pool.submit(() -> {
                Future<Integer> child = pool.submit(() -> 42);
                childRef.set(child);
                childQueued.countDown();
                return child.get();
            });

            if (!childQueued.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("child not submitted");
            }

            System.out.println("Queued tasks: "
                    + pool.getQueue().size());
            System.out.println("Parent done: " + parent.isDone());

            System.out.println("Parent cancellation accepted: "
                    + parent.cancel(true));

            int childResult =
                    childRef.get().get(10, TimeUnit.SECONDS);
            System.out.println("Child result after freeing worker: "
                    + childResult);
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("pool did not terminate");
            }
        }
    }
}
```

Chạy:

```shell
javac PoolDependencyDemo.java
java PoolDependencyDemo
```

Stdout khi các thao tác hoàn tất trong thời hạn:

```text
Queued tasks: 1
Parent done: false
Parent cancellation accepted: true
Child result after freeing worker: 42
```

Tại thời điểm main đọc, cha vẫn giữ worker và không thể có kết quả vì con chưa được chạy. Main chủ động hủy cha với yêu cầu ngắt. Lần `child.get()` trong cha nhận ngắt, tác vụ cha rời worker; con mới có cơ hội chạy.

Đây là cách giải phóng **thí nghiệm**, không phải chính sách mặc định “hủy cha để con tiếp tục” cho mọi ứng dụng. Khi thiết kế thật, cần xác định hủy có lan sang con không và ai sở hữu kết quả con.

## 7. Phân biệt bão hòa tạm thời, cạn pool và cạn luồng hệ điều hành

Ba tình huống có cách xử lý khác nhau:

### Pool bão hòa do tải cao

Worker đang xử lý công việc hữu ích. Hàng đợi tăng vì tốc độ đến lớn hơn tốc độ hoàn tất. Vẫn có tiến triển, nhưng độ trễ tăng.

Xem thông lượng, thời gian phục vụ, giới hạn hàng đợi và chính sách tiếp nhận. Tăng worker chỉ có ích nếu tài nguyên CPU/I/O phía dưới còn khả năng đáp ứng.

### Worker bị giữ bởi các điểm chờ

Worker có thể đang đợi cùng cơ sở dữ liệu, khóa, giấy phép hoặc Future. Dù số worker “active” cao, chúng không nhất thiết tiêu CPU hay tạo kết quả.

Cần tìm phụ thuộc chung và khả năng tiến triển của nó. Thêm worker có thể chỉ tạo thêm người chờ hoặc làm quá tải dịch vụ bên dưới.

### Không thể tạo thêm platform thread

Đây là vấn đề giới hạn tài nguyên tiến trình/hệ điều hành: bộ nhớ, native stack, số thread hoặc cấu hình môi trường. Có thể đi kèm lỗi không tạo được native thread.

Không tái hiện bằng cách tạo vô hạn luồng trong một thí nghiệm học tập. Chẩn đoán dựa trên số lượng luồng, giới hạn tiến trình/container, bộ nhớ và nhật ký lỗi.

Một lượng lớn virtual thread trên Java 21+ không có nghĩa tương đương cùng số platform thread. Cần công cụ và mô hình phù hợp cho loại luồng; giảm chi phí luồng không làm tài nguyên bên ngoài như kết nối trở nên vô hạn.

## 8. Đọc số liệu ThreadPoolExecutor đúng cách

Các số liệu thường xem:

- `getPoolSize()`: số worker hiện có.
- `getActiveCount()`: ước lượng số worker đang thực thi tác vụ.
- `getQueue().size()`: số việc đang trong hàng đợi tại lúc đọc.
- `getCompletedTaskCount()`: số tác vụ đã hoàn tất theo thống kê.
- Cấu hình core/max, loại hàng đợi và chính sách từ chối.

“Active” không phải “đang dùng CPU”. Một tác vụ chặn trong get vẫn đang được worker thực thi theo góc nhìn pool.

Nhiều chỉ số là ước lượng hoặc ảnh chụp đang thay đổi; so sánh xu hướng qua thời gian, không dùng một bộ số đọc rời rạc làm bằng chứng tuyệt đối.

Với hàng đợi không giới hạn, cấu hình `maximumPoolSize` lớn không có nghĩa pool sẽ tự tăng tới mức đó khi hàng đợi đang nhận được việc. Cần hiểu thứ tự tạo worker và xếp hàng của [ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html).

Cũng không suy ra “completed” là “thành công nghiệp vụ”. Tác vụ có thể đã kết thúc với lỗi; phải xem Future hoặc kênh lỗi riêng.

## 9. Thu bằng chứng bằng thread dump

Một quy trình chẩn đoán ban đầu:

1. Xác định đúng tiến trình/JVM gặp triệu chứng.
2. Lấy vài thread dump cách nhau một khoảng phù hợp với vấn đề.
3. Ghi đồng thời độ trễ, thông lượng, CPU, pool/hàng đợi và lỗi.
4. Nhóm các stack giống nhau, tìm những điểm chờ chiếm nhiều worker.
5. Đi từ bên chờ tới chủ khóa/tác vụ/phía ngoài chịu trách nhiệm làm nó tiến triển.
6. Chỉ kết luận deadlock khi có bằng chứng về vòng phụ thuộc hoặc trạng thái không thể tiến triển.

Các lệnh mẫu trong shell:

```shell
jcmd -l
jcmd 12345 help Thread.print
jcmd 12345 Thread.print -l
```

Thay 12345 bằng PID đã xác minh. Không chạy nguyên PID minh họa. Cần dùng jcmd trong môi trường có quyền truy cập phù hợp với JVM đích và kiểm tra lệnh được JDK đó hỗ trợ.

Đầu ra thay đổi theo JDK, loại khóa và ứng dụng, nên không có stdout cố định cho các lệnh chẩn đoán này. `Thread.print -l` bổ sung thông tin khóa theo khả năng công cụ. Xem [jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html) về cú pháp và yêu cầu chạy.

Với ứng dụng có virtual thread, kiểm tra thêm các lệnh dump dành cho loại luồng ấy trên JDK đang dùng, thay vì giả định một bản dump truyền thống hay ThreadMXBean đã bao phủ hết.

## 10. Hướng sửa phải khớp nguyên nhân

| Bằng chứng | Hướng xử lý |
| --- | --- |
| Hai đường lấy nhiều khóa theo thứ tự ngược nhau | Thiết lập thứ tự khóa nhất quán hoặc giảm việc giữ đồng thời nhiều khóa |
| Giữ khóa trong lúc gọi I/O chậm | Xem lại phạm vi khóa và giao thức công bố trạng thái |
| Cha đợi con trong chính pool đã bị cha chiếm hết | Đổi cách điều phối; tránh chặn worker đang cần cho công việc phụ thuộc |
| Giấy phép không được trả | Sửa vòng đời lấy–trả và đường lỗi/hủy |
| Tải đến vượt năng lực lâu dài | Giới hạn hàng đợi/tiếp nhận, giảm tải hoặc tăng năng lực theo đo đạc |
| Phụ thuộc ngoài không có thời hạn | Đặt ngân sách chờ và chính sách xử lý hết hạn/hủy phù hợp |

Tách pool là một lựa chọn có điều kiện, không tự loại bỏ mọi vòng đợi giữa các pool. Tăng số worker cũng không phải chứng minh thuật toán đúng: mẫu cha–con vẫn có thể kẹt khi độ sâu hoặc số cha tăng.

Timeout giúp tạo đường thoát nhưng không tự hoàn tác công việc hay giải phóng tài nguyên mà tác vụ nền vẫn đang dùng. Sau hủy, cần quan sát khả năng dừng thực sự theo hợp đồng.

Không dùng cơ chế cưỡng chế dừng luồng không an toàn để mở khóa. Sửa giao thức sở hữu tài nguyên và cơ chế hủy hợp tác là hướng bền vững.

## 11. Tự kiểm tra

**Thấy nhiều WAITING có phải deadlock không?**  
Không. Có thể là worker nhàn rỗi, đợi dữ liệu hợp lệ hoặc một vấn đề phụ thuộc thật; phải đọc stack và bên chịu trách nhiệm đánh thức.

**findDeadlockedThreads trả null có chứng minh ứng dụng vẫn tiến triển không?**  
Không. Công cụ có phạm vi phát hiện cụ thể; đợi Future, thiếu giấy phép và thiếu worker có thể cần chẩn đoán khác.

**getActiveCount cao có nghĩa CPU cao không?**  
Không. Worker thực thi tác vụ có thể đang chặn.

**Tăng pool từ một lên hai luồng có sửa được mọi lỗi cha đợi con không?**  
Không. Nó có thể chỉ trì hoãn điểm bão hòa; cần xét đồ thị phụ thuộc của toàn bộ tải.

**Một lần dump đủ chưa?**  
Một dump có thể chỉ ra vòng khóa rõ ràng, nhưng chờ lâu và cạn pool thường cần nhiều mẫu cùng số liệu tiến triển.

Chẩn đoán luồng bắt đầu từ câu hỏi cụ thể: mỗi bên đang đợi điều gì, ai có thể đáp ứng điều đó, và bên ấy còn khả năng được chạy hoặc giải phóng tài nguyên hay không.
