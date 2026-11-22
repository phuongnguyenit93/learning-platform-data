# Phối hợp trạng thái luồng với số liệu hàng đợi và khóa

## 1. Một trạng thái luồng chưa giải thích được hệ thống đang chậm vì đâu

Khi ứng dụng phản hồi chậm, ta có thể thấy nhiều luồng ở `WAITING`, `TIMED_WAITING` hoặc `RUNNABLE`. Tuy nhiên, mỗi nhãn chỉ mô tả một mặt của tình huống.

Một luồng `WAITING` có thể đang:

- Nhàn rỗi, chờ tác vụ mới từ hàng đợi.
- Chờ quyền vào một `ReentrantLock`.
- Chờ kết quả của một tác vụ khác.
- Chờ một tín hiệu phối hợp mà ứng dụng chưa phát.

Những tình huống đó cần cách xử lý khác nhau. Chẩn đoán có ích phải nối được ba câu hỏi:

1. **Luồng đang ở đâu và đang chờ điều gì?**
2. **Công việc đang dồn ở hàng đợi nào, có được xử lý tiếp không?**
3. **Tài nguyên hoặc khóa nào đang ngăn tiến triển, và ai có thể giải phóng nó?**

Mục tiêu không phải xếp loại trạng thái “tốt” hoặc “xấu”, mà là dựng được chuỗi phụ thuộc của công việc.

## 2. Đọc đúng ý nghĩa trạng thái

| Trạng thái | Ý nghĩa cần nhớ khi chẩn đoán |
| --- | --- |
| `RUNNABLE` | Có thể đang thực thi hoặc sẵn sàng thực thi ở mức JVM; không tự chứng minh đang dùng nhiều CPU |
| `BLOCKED` | Đang đợi vào monitor của `synchronized` |
| `WAITING` | Đang chờ không có thời hạn cho một hành động khác |
| `TIMED_WAITING` | Đang chờ có thời hạn |
| `NEW` | Chưa được bắt đầu |
| `TERMINATED` | Đã kết thúc; cần xem kết quả hoặc lỗi để biết thành công hay thất bại |

Đây là trạng thái JVM, không phải bản sao một-một của trạng thái bộ lập lịch hệ điều hành. Xem [Thread.State](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.State.html).

Một điểm đặc biệt quan trọng: chờ `ReentrantLock` thường biểu hiện bằng cơ chế đỗ luồng, nên có thể thấy `WAITING` hoặc `TIMED_WAITING` tùy cách chờ, chứ không phải `BLOCKED` như chờ monitor.

Stack trace giúp phân biệt:

```text
WAITING + BlockingQueue.take(...)
→ có thể đang chờ công việc mới

WAITING + LockSupport.park(...) + ReentrantLock/AQS
→ có thể đang đợi khóa

WAITING + FutureTask.get(...)
→ đang đợi một kết quả tính toán
```

Các dòng trên là dấu hiệu định hướng. Cần đọc cả stack gọi lên từ mã ứng dụng và ngữ cảnh tài nguyên; chỉ thấy `park` chưa xác định được nguyên nhân nghiệp vụ.

## 3. Ghép với số liệu hàng đợi và nhóm thực thi

Với `ThreadPoolExecutor`, các số liệu thường hữu ích gồm:

- Số luồng trong nhóm và giới hạn luồng đã cấu hình.
- Số luồng đang thực hiện tác vụ, qua `getActiveCount()`.
- Số tác vụ đang xếp hàng, qua `getQueue().size()`.
- Số tác vụ đã hoàn tất, qua `getCompletedTaskCount()`.
- Số tác vụ bị từ chối, được ghi nhận theo chính sách từ chối của ứng dụng.

Các số đếm hoạt động và hoàn tất được API mô tả là xấp xỉ; `getQueue()` phục vụ theo dõi và chẩn đoán, không phải lý do để tự ý lấy hoặc sửa tác vụ trong hàng đợi. Xem [ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html).

Cần phân biệt ba trạng thái:

```text
Tác vụ chưa được nhận → có thể bị từ chối hoặc chạy theo chính sách khác
Tác vụ nằm trong queue → chưa được luồng của nhóm lấy ra
Tác vụ đang chạy trên worker → có thể đang tính hoặc đang chờ tài nguyên
```

Một tác vụ xếp hàng chưa có luồng riêng, nên không thể tìm nó như một stack trace độc lập. Ngược lại, worker được tính là đang thực hiện tác vụ vẫn có thể đang chờ khóa hoặc I/O.

### Số lượng và xu hướng trả lời các câu hỏi khác nhau

`queueSize=500` tại một thời điểm chưa đủ kết luận quá tải. Cần biết:

- Hàng đợi đang tăng hay giảm?
- Bao lâu thì số tác vụ hoàn tất tăng thêm?
- Tác vụ cũ nhất đã chờ bao lâu?
- Lưu lượng nhận vào và tốc độ hoàn tất thay đổi thế nào?
- Hàng đợi có dung lượng giới hạn không, và khi đầy áp dụng chính sách nào?

Một hàng đợi lớn nhưng đang thoát nhanh khác với một hàng đợi nhỏ chứa tác vụ bị kẹt nhiều phút. Vì vậy nên đo cả thời gian chờ từ lúc gửi đến lúc bắt đầu và thời gian xử lý sau khi bắt đầu.

## 4. Ghép với số liệu khóa

Với `ReentrantLock`, có thể dùng các phương thức quan sát như:

- `isLocked()`: khóa có đang bị giữ tại thời điểm đọc không?
- `hasQueuedThreads()`: có dấu hiệu luồng đang đợi nhận khóa không?
- `hasQueuedThread(thread)`: một luồng cụ thể có đang trong hàng đợi khóa không?
- `getQueueLength()`: ước lượng số luồng đang đợi nhận khóa.

Các số liệu hàng đợi khóa là thông tin quan sát, không phải quyền nhận khóa hoặc một ảnh chụp nguyên tử của toàn hệ thống. Xem [các API quan sát ReentrantLock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html).

Đừng nhầm **hàng đợi tác vụ** với **hàng đợi khóa**:

```text
Executor queue:
    tác vụ B, C chưa được worker lấy ra

Worker đang thực hiện tác vụ A:
    đợi ReentrantLock L

Lock queue của L:
    worker đang chạy A
```

Trong mô hình này, chỉ một worker trực tiếp đợi khóa, nhưng nhiều tác vụ phía sau cùng chịu chậm dây chuyền.

Một `Condition` có tập bên đang chờ điều kiện riêng. Chờ điều kiện và chờ nhận khóa không phải cùng một việc. Không dùng một số đếm hàng đợi khóa để suy ra tổng mọi luồng đang liên quan đến đối tượng khóa.

## 5. Ví dụ chạy đầy đủ: khóa làm hàng đợi tác vụ không tiến triển

Chương trình sau chủ động giữ khóa trong luồng chính:

1. Một worker bắt đầu tác vụ đầu và chờ khóa.
2. Hai tác vụ khác được đưa vào hàng đợi của nhóm một luồng.
3. Luồng chính quan sát trạng thái worker, hàng đợi khóa và hàng đợi tác vụ.
4. Luồng chính thả khóa; cả ba tác vụ kết thúc.

Tệp `QueueLockDiagnosticDemo.java`, chạy trên JDK 17 trở lên:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.locks.ReentrantLock;

public class QueueLockDiagnosticDemo {
    private static Thread.State observeWaiting(
            Thread worker, ReentrantLock lock) throws InterruptedException {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        do {
            Thread.State state = worker.getState();
            if (state == Thread.State.WAITING && lock.hasQueuedThread(worker)) {
                return state;
            }
            Thread.sleep(1);
        } while (System.nanoTime() - deadline < 0);
        throw new IllegalStateException("Waiting state was not observed");
    }

    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        CountDownLatch entered = new CountDownLatch(1);
        AtomicReference<Thread> workerRef = new AtomicReference<>();
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(2),
                runnable -> {
                    Thread thread = new Thread(runnable, "diagnostic-worker");
                    workerRef.set(thread);
                    return thread;
                });

        try {
            lock.lock();
            try {
                pool.execute(() -> {
                    entered.countDown();
                    lock.lock();
                    try {
                        // The diagnostic task has no further work.
                    } finally {
                        lock.unlock();
                    }
                });

                if (!entered.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Worker did not start");
                }
                pool.execute(() -> {});
                pool.execute(() -> {});

                Thread worker = workerRef.get();
                Thread.State observed = observeWaiting(worker, lock);
                System.out.println("observedState=" + observed);
                System.out.println("lockWaiter=" + lock.hasQueuedThread(worker));
                System.out.println("queuedTasks=" + pool.getQueue().size());
                System.out.println("completedTasks=" + pool.getCompletedTaskCount());
            } finally {
                lock.unlock();
            }

            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Pool did not terminate");
            }
            System.out.println("completedAfterRelease="
                    + pool.getCompletedTaskCount());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Biên dịch và chạy:

```shell
javac QueueLockDiagnosticDemo.java
java QueueLockDiagnosticDemo
```

Kết quả khi quan sát thành công trong thời hạn:

```text
observedState=WAITING
lockWaiter=true
queuedTasks=2
completedTasks=0
completedAfterRelease=3
```

`observeWaiting()` lặp có giới hạn để bắt một ảnh chụp worker đang `WAITING` và nằm trong hàng đợi khóa. Khoảng ngủ ngắn chỉ phục vụ **quan sát trong ví dụ**, không phải cơ chế đồng bộ nghiệp vụ hoặc cách điều khiển chương trình thật.

Tính xác định của tình huống đến từ việc luồng chính đang giữ khóa và worker không thể hoàn tất tác vụ đầu trước khi khóa được thả. `CountDownLatch` xác nhận tác vụ đầu đã bắt đầu; không dùng thời gian ngủ để đoán tác vụ đã được nhận.

Kết luận trong trường hợp dựng sẵn này:

- `WAITING` không có nghĩa worker nhàn rỗi.
- Có hai tác vụ chưa chạy vì worker duy nhất đang đợi khóa.
- `completedTasks=0` phù hợp với việc chưa tác vụ nào vượt qua điểm kẹt.
- Sau khi giải phóng tài nguyên đang được chờ, số hoàn tất tăng lên 3.

Không nên biến số liệu của ví dụ thành một quy tắc “thấy WAITING và queue tăng là lỗi khóa”. Trong ứng dụng thật phải xác nhận stack, đối tượng khóa và bên giữ khóa.

## 6. Một số tổ hợp bằng chứng thường gặp

| Bằng chứng kết hợp | Giả thuyết cần kiểm tra tiếp |
| --- | --- |
| Nhiều worker chờ `BlockingQueue.take`, queue rỗng, lưu lượng thấp | Nhóm có thể đang nhàn rỗi bình thường |
| Queue tăng, worker `RUNNABLE`, CPU tăng, số hoàn tất vẫn tăng chậm | Có thể thiếu năng lực CPU hoặc có công việc tính toán nặng |
| Queue tăng, worker đợi cùng một khóa, bên giữ khóa làm việc lâu | Tranh chấp hoặc vùng giữ khóa quá lớn |
| Queue tăng, worker đợi mạng/đĩa, CPU thấp | Có thể bị giới hạn bởi I/O hoặc dịch vụ phía sau |
| Worker đợi `Future.get`, tác vụ sinh ra Future còn nằm trong cùng queue | Có thể có vòng phụ thuộc do thiếu chỗ thực thi |
| Nhiều lần chụp vẫn cùng các quan hệ chờ và số hoàn tất không tăng | Có dấu hiệu đình trệ cần dựng đồ thị phụ thuộc |
| Queue nhỏ nhưng thời gian chờ rất dài | Có thể có tác vụ bị kẹt hoặc phân phối không đều; kích thước queue không đủ giải thích |

Đây là các giả thuyết chẩn đoán, không phải kết luận tự động. Ví dụ CPU thấp còn có thể liên quan hạn mức container, chờ mạng hoặc ứng dụng thiếu dữ liệu đầu vào.

Cũng cần xem chính sách executor: một chính sách chạy tác vụ trên luồng gửi có thể giữ queue nhỏ nhưng đẩy thời gian xử lý sang luồng tiếp nhận yêu cầu. Số liệu của worker đơn thuần sẽ bỏ sót phần việc đó.

## 7. Thu thập cùng cửa sổ thời gian

Một cách làm thực tế:

1. Ghi thời điểm, tên nhóm thực thi và định danh tài nguyên.
2. Chụp số worker, active, queue, completed và số từ chối.
3. Chụp stack của những luồng liên quan.
4. Ghi thông tin khóa đang chờ và bên đang giữ nếu công cụ cung cấp.
5. Lặp một vài lần trong khoảng thời gian phù hợp với độ dài tác vụ.
6. So sánh mức thay đổi, không chỉ các giá trị riêng lẻ.

```text
t0: queue=40, completed=1000
t1: queue=65, completed=1000
t2: queue=90, completed=1000
```

Đây là số liệu minh họa, không phải stdout của chương trình. Nó gợi ý công việc tiếp tục được đưa vào nhưng không có tác vụ hoàn tất trong khoảng quan sát. Vẫn cần kiểm tra worker đang tính một tác vụ dài hay đang chờ điều kiện không thể xảy ra.

Các lời gọi quan sát riêng lẻ không lấy mẫu ở đúng cùng một nano giây. Một luồng có thể đổi trạng thái giữa lúc đọc queue và lúc chụp stack. Vì vậy nên gắn mốc thời gian và dùng nhiều mẫu để kiểm tra tính nhất quán của giả thuyết.

Không dùng `Thread.getState()`, kích thước queue hoặc ước lượng số luồng chờ như một điều kiện đồng bộ mới trong mã nghiệp vụ. Chẩn đoán quan sát trạng thái; tính đúng đắn vẫn cần khóa, biến nguyên tử, latch hoặc giao thức kết quả phù hợp.

## 8. Dùng thread dump và công cụ quản lý đúng phạm vi

Trên một JVM phù hợp, có thể dùng `jcmd` để lấy thông tin chẩn đoán:

```shell
jcmd -l
jcmd 12345 help Thread.print
jcmd 12345 Thread.print -l
```

`12345` là PID ví dụ, phải thay bằng tiến trình cần kiểm tra. Kiểm tra lệnh hỗ trợ bằng `help` trên chính JVM đích và chạy với điều kiện truy cập phù hợp. Thread dump cùng thông tin khóa giúp nối luồng chờ với tài nguyên và bên giữ khóa. Xem [tài liệu jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).

Trong ứng dụng, `ThreadMXBean` có các khả năng lấy thông tin luồng, đo thời gian CPU khi JVM hỗ trợ và phát hiện một số kiểu deadlock. Cần kiểm tra khả năng hỗ trợ, trạng thái bật đo và dữ liệu không khả dụng thay vì coi mọi số 0 hoặc giá trị âm là một kết luận hiệu năng. Xem [ThreadMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html).

Một số giới hạn quan trọng:

- Phát hiện deadlock của monitor và bộ đồng bộ có chủ sở hữu không bao phủ mọi vòng phụ thuộc tác vụ.
- Chu kỳ “worker đợi Future, Future cần tác vụ đang xếp hàng sau worker” có thể không xuất hiện như một chu kỳ sở hữu khóa.
- Thời gian chặn monitor không phải tổng thời gian tranh chấp mọi loại khóa.
- Thời gian CPU và thời gian trôi qua là hai đại lượng khác nhau.
- `ThreadMXBean` hỗ trợ luồng nền tảng, không cung cấp đầy đủ quản lý/giám sát luồng ảo.

Nếu ứng dụng dùng luồng ảo, chọn công cụ chụp luồng và số liệu phù hợp với JDK đang chạy. Không lấy số worker của một nhóm luồng nền tảng hoặc một API không hỗ trợ luồng ảo để kết luận số tác vụ đồng thời của toàn ứng dụng.

## 9. Dựng chuỗi phụ thuộc đến nơi có thể tạo tiến triển

Giả sử nhiều worker đang đợi khóa L. Bước tiếp theo không chỉ là tăng số worker:

```text
Yêu cầu chậm
    ↓
Tác vụ nằm trong executor queue
    ↓
Các worker hiện có đang đợi khóa L
    ↓
Bên giữ L đang chờ gọi dịch vụ bên ngoài
    ↓
Dịch vụ bên ngoài chậm hoặc không phản hồi
```

Trong chuỗi này, tăng worker có thể chỉ tạo thêm bên chờ L. Vấn đề cần xem xét là vì sao giữ L qua một thao tác ngoài có thời gian chờ dài và có thể tách giao thức đó ra sao mà vẫn bảo vệ tính đúng đắn.

Một chuỗi khác:

```text
Worker A giữ khóa L và đợi kết quả tác vụ B
Tác vụ B cần khóa L để hoàn tất
```

Ở đây đã có vòng phụ thuộc về tài nguyên. Cần thay đổi thứ tự hoặc phạm vi giữ tài nguyên, không chỉ tăng timeout.

Không kết luận một khóa là nút thắt chỉ vì nó xuất hiện trong stack. Một khóa có thể bị giữ rất ngắn và không làm tăng thời gian chờ đáng kể. Cần bằng chứng về tần suất, thời gian giữ, số bên chờ và ảnh hưởng đến tiến triển.

## 10. Kiểm chứng thay đổi bằng cả kết quả và số liệu

Sau khi có giả thuyết, chỉ thay một phần đủ nhỏ để kiểm chứng:

- Nếu giảm phạm vi giữ khóa, kiểm tra bất biến dữ liệu còn đúng.
- Nếu thay cấu hình nhóm, đo số hoàn tất và độ trễ thay vì chỉ thấy nhiều luồng hơn.
- Nếu giảm tải đầu vào hoặc giới hạn hàng đợi, quan sát cả số từ chối và trải nghiệm yêu cầu.
- Nếu xử lý timeout, xác minh tài nguyên được giải phóng và tác vụ nền không tiếp tục gây tác dụng phụ ngoài dự kiến.

Đối chiếu cùng loại tải trước và sau. Queue giảm nhưng tỷ lệ từ chối tăng mạnh không đồng nghĩa năng lực xử lý đã tăng. Active giảm cũng có thể do ít yêu cầu được nhận, không phải do khóa tốt hơn.

## 11. Bài tập suy luận

1. Trong ví dụ, tăng số worker từ 1 lên 3. Hai tác vụ rỗng có thể hoàn tất trong lúc tác vụ đầu còn chờ khóa; vì sao queue nhỏ hơn chưa chứng minh khóa không còn gây chậm tác vụ đầu?
2. Thay tác vụ đầu bằng thao tác chờ một tín hiệu `CountDownLatch`. Trạng thái vẫn có thể là `WAITING`, nhưng bằng chứng hàng đợi `ReentrantLock` không còn phù hợp.
3. Nếu mọi worker chờ lấy tác vụ, queue luôn rỗng và dịch vụ ít yêu cầu, có cần “sửa WAITING” không? Không, đó có thể là hành vi nhàn rỗi bình thường.
4. Nếu số hoàn tất đứng yên trong ba lần lấy mẫu, cần thêm gì trước khi gọi đó là deadlock? Cần tìm các quan hệ chờ, bên có khả năng giải phóng và một chu kỳ hoặc điều kiện không thể tiến triển.

Một chẩn đoán thuyết phục nối được **stack của luồng → nơi công việc đang chờ → tài nguyên hoặc tác vụ phải tạo tiến triển**, rồi kiểm chứng chuỗi đó bằng quan sát theo thời gian.
