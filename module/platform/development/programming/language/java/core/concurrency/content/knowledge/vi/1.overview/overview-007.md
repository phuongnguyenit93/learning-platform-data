# Safety, liveness, progress và starvation trong Java Concurrency

Khi nhiều thread cùng truy cập một trạng thái, chương trình có thể **tạo ra kết quả sai** hoặc **không bao giờ hoàn thành công việc**. Hai loại vấn đề này phải được đánh giá riêng: *safety* hỏi liệu có điều xấu xảy ra hay không; *liveness* hỏi liệu điều tốt cần xảy ra có thể tiếp tục xảy ra hay không. *Progress* mô tả mức bảo đảm tiến triển của thuật toán; *starvation* mô tả tình trạng một thread/tác vụ chờ mãi dù hệ thống vẫn hoạt động.

Bài học áp dụng cho **Java concurrency nói chung**: Java Memory Model, thread, intrinsic lock, `java.util.concurrent`, atomic operation và các thuật toán phối hợp. Những cơ chế tích hợp riêng với Spring nằm ngoài phạm vi.

## 1. Phân biệt bốn khái niệm cốt lõi

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Safety** (tính an toàn) | Có trạng thái/kết quả bị cấm nào có thể xuất hiện không? | Số dư tài khoản không được âm; mỗi công việc chỉ được xử lý một lần. |
| **Liveness** (tính sống) | Với những giả định tiến triển phù hợp, công việc có cơ hội hoàn thành cuối cùng không? | Thread đang đợi có thể được đánh thức; yêu cầu không kẹt vĩnh viễn. |
| **Progress** (bảo đảm tiến triển) | Trong tranh chấp, thuật toán bảo đảm tiến triển cho toàn hệ thống hay cho từng thread ở mức nào? | Lock-free bảo đảm tiến triển ở cấp hệ thống trong mô hình thuật toán; wait-free có giới hạn bước cho mỗi lời gọi. |
| **Starvation** (đói tài nguyên/lượt chạy) | Một tác vụ cụ thể có thể không được phục vụ vô hạn dù tác vụ khác vẫn chạy không? | Thread liên tục thua tranh chấp lock hoặc CAS. |

**Safety** thường được mô tả bằng một *invariant* (bất biến): điều kiện phải đúng trong mọi trạng thái có thể quan sát hợp lệ. Ví dụ, nếu hai thread cùng rút một đơn vị tiền từ tài khoản có số dư `1`, sau khi xử lý hợp lệ phải có tối đa một lần rút thành công và số dư không âm. Chỉ kiểm tra `balance > 0` trước khi trừ chưa đủ nếu bước kiểm tra và trừ có thể bị thread khác chen vào.

**Liveness** là tính chất theo thời gian: một công việc cần có khả năng tiến triển, thường được phát biểu với các giả định như thread tiếp tục được CPU lập lịch, tài nguyên cuối cùng được trả lại và các thread không bị dừng vĩnh viễn. Không có thuật toán Java nào tự bảo đảm hệ điều hành sẽ cấp CPU cho một thread mãi mãi bị bỏ qua.

**Progress** thường là mức bảo đảm được chứng minh ở cấp thuật toán trong một mô hình thực thi. Một chương trình có thể giữ được safety nhưng không có liveness; ví dụ, khóa được giữ đúng cách nên dữ liệu không hỏng, nhưng thread giữ khóa không bao giờ giải phóng. Ngược lại, mọi thread có vẻ chạy rất nhanh cũng không chứng minh safety nếu cập nhật dữ liệu bị race.

**Starvation** là vấn đề của từng tác vụ. Tổng thể hệ thống vẫn đạt throughput cao, nhưng một thread cụ thể không có tiến triển. Vì vậy “có progress toàn hệ thống” không đồng nghĩa “mọi thread đều hoàn thành”.

## 2. Safety: bảo vệ invariant, không chỉ bảo vệ từng biến

### 2.1 Race condition và thao tác ghép

Xét các thao tác:

```java
if (balance.get() > 0) {
    balance.decrementAndGet();
}
```

Ngay cả khi `balance` là `AtomicInteger`, phép đọc, so sánh và giảm là **ba bước riêng**. Hai thread có thể cùng đọc số dư dương rồi cùng giảm. Mỗi lần `decrementAndGet()` là atomic nhưng toàn bộ điều kiện nghiệp vụ “chỉ giảm khi còn tiền” không atomic. Đây là lỗi *check-then-act*.

Có ba vấn đề thường bị trộn lẫn:

- **Atomicity:** thao tác hoặc chuyển trạng thái quan trọng có bị thread khác chen vào ở giữa không?
- **Visibility:** thread khác có nhìn thấy lần ghi mới hay không?
- **Ordering:** JVM/compiler/CPU có thể sắp xếp lại những thao tác nào, và quan hệ *happens-before* nào ràng buộc việc quan sát?

Trong Java Memory Model, `volatile` cung cấp quan hệ visibility/ordering cần thiết cho các lần đọc/ghi tương ứng, nhưng `volatile int count` với `count++` vẫn có thể mất cập nhật vì `++` là read–modify–write. Một khối `synchronized` được dùng nhất quán cho cả đọc/ghi trạng thái liên quan, hoặc một thao tác CAS trên `AtomicInteger`, có thể giữ invariant phù hợp. Đừng dùng hai lock khác nhau cho cùng một invariant rồi giả định đã đồng bộ đúng.

### 2.2 Ví dụ Java 17+: vi phạm safety và sửa bằng CAS

Tạo tệp `SafetyLivenessDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class SafetyLivenessDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger unsafeBalance = new AtomicInteger(1);
        CountDownLatch bothChecked = new CountDownLatch(2);
        CountDownLatch startDecrement = new CountDownLatch(1);

        Runnable unsafeWithdraw = () -> {
            if (unsafeBalance.get() > 0) {
                bothChecked.countDown();
                try {
                    startDecrement.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }
                unsafeBalance.decrementAndGet();
            } else {
                bothChecked.countDown();
            }
        };

        Thread first = new Thread(unsafeWithdraw, "unsafe-1");
        Thread second = new Thread(unsafeWithdraw, "unsafe-2");
        first.start();
        second.start();
        bothChecked.await();
        startDecrement.countDown();
        first.join();
        second.join();

        AtomicInteger safeBalance = new AtomicInteger(1);
        AtomicInteger successfulWithdrawals = new AtomicInteger();
        Runnable safeWithdraw = () -> {
            while (true) {
                int current = safeBalance.get();
                if (current <= 0) {
                    return;
                }
                if (safeBalance.compareAndSet(current, current - 1)) {
                    successfulWithdrawals.incrementAndGet();
                    return;
                }
            }
        };

        Thread third = new Thread(safeWithdraw, "safe-1");
        Thread fourth = new Thread(safeWithdraw, "safe-2");
        third.start();
        fourth.start();
        third.join();
        fourth.join();

        System.out.println("Unsafe balance: " + unsafeBalance.get());
        System.out.println("Safe balance: " + safeBalance.get());
        System.out.println("Successful safe withdrawals: "
                + successfulWithdrawals.get());
    }
}
```

Biên dịch/chạy:

```bash
javac SafetyLivenessDemo.java
java SafetyLivenessDemo
```

Kết quả:

```text
Unsafe balance: -1
Safe balance: 0
Successful safe withdrawals: 1
```

**Vì sao kết quả đầu tiên xác định?** `CountDownLatch` buộc cả hai thread hoàn tất bước kiểm tra `> 0` trước khi một thread được phép giảm số dư. Do cả hai đọc giá trị ban đầu `1`, mỗi thread giảm đúng một đơn vị: `-1`. Latch chỉ phục vụ tái hiện race; nó không phải cách sửa invariant.

Ở nhánh an toàn, `compareAndSet(current, current - 1)` thực hiện chuyển trạng thái có điều kiện như một thao tác atomic. Nếu thread khác đã thay đổi số dư, CAS thất bại và vòng lặp đọc lại. Từ `1`, chỉ một thread có thể chuyển thành `0`; thread kia phát hiện `0` và dừng. `join()` bảo đảm main thread đợi các thread kết thúc trước khi in kết quả.

Vòng lặp CAS ở đây giải quyết **safety** cho một biến số dư đơn giản. Nó không tự chứng minh rằng một thread cụ thể sẽ thành công sau số bước hữu hạn khi tranh chấp kéo dài. Nếu invariant trải trên nhiều biến/tài nguyên, hãy thiết kế một giao thức đồng bộ chung, dùng lock đúng phạm vi, hoặc dùng cấu trúc dữ liệu có hợp đồng atomic phù hợp. Không thể biến một nghiệp vụ đa bước thành atomic chỉ bằng cách thay mọi trường bằng `AtomicInteger`.

### 2.3 Linearizability và điểm hiệu lực

Một lời gọi đồng thời *linearizable* nếu mỗi thao tác có thể được xem như có hiệu lực tại một điểm duy nhất nằm giữa lúc gọi và lúc trả về, đồng thời tôn trọng thứ tự thực tế của những lời gọi không chồng lấn. Trong ví dụ rút tiền an toàn, CAS thành công là điểm tuyến tính hóa của thao tác giảm số dư.

Linearizability là tiêu chuẩn safety hữu ích cho API concurrent; nó **không bảo đảm liveness hay fairness**. Một cấu trúc có thể trả lời đúng cho mọi lời gọi đã hoàn tất mà vẫn khiến một số lời gọi khác chờ vô hạn.

## 3. Liveness: công việc có tiếp tục tiến triển không?

Những dạng thất bại cần phân biệt:

| Hiện tượng | Điều gì xảy ra? | Dấu hiệu |
| --- | --- | --- |
| **Deadlock** | Một tập thread phụ thuộc vòng tròn vào tài nguyên/sự kiện mà nhau phải giải phóng. | Thread cùng đợi lock mãi, không thread nào trong vòng chờ tiến lên. |
| **Livelock** | Thread vẫn đổi trạng thái/chạy nhưng liên tục phản ứng khiến không hoàn thành việc hữu ích. | CPU hoạt động, số lần retry tăng, số tác vụ thành công không tăng. |
| **Starvation** | Một thread cụ thể liên tục bị bỏ qua trong khi thread khác có thể tiến triển. | Latency của một tác vụ tăng vô hạn; throughput chung có thể vẫn tốt. |
| **Blocking không có giới hạn** | Chờ một điều kiện, I/O hoặc thao tác đồng bộ không có thời hạn/đường thoát được bảo đảm. | Request treo, `await()`, `take()` hoặc lock acquisition kéo dài. |

**Deadlock điển hình:** thread A giữ lock `L1`, cần `L2`; thread B giữ `L2`, cần `L1`. Mỗi thread chờ một lock do đối phương giữ. Safety của dữ liệu được khóa có thể vẫn đúng, nhưng liveness thất bại.

**Livelock điển hình:** hai tác vụ nhường đường cho nhau theo cùng một nhịp và cùng thử lại ngay, không tác vụ nào thực sự đi qua. Một chính sách retry có backoff và jitter phù hợp có thể giảm khả năng lặp đồng bộ; vẫn cần giới hạn/thời hạn và đánh giá logic thực tế.

**Starvation điển hình:** một thread ưu tiên thấp, một yêu cầu nằm cuối hàng đợi không công bằng, hoặc một contender CAS liên tiếp thất bại vì thread khác luôn thắng. Starvation không cần deadlock: các thread khác vẫn hoàn tất.

Cần phân biệt “không có deadlock” với “có liveness”: bỏ vòng chờ lock chưa chứng minh không có starvation, chờ I/O vô hạn hoặc livelock.

## 4. Progress guarantee của thuật toán concurrent

Bốn mức thường gặp được mô tả trong mô hình bộ nhớ chung và với các giả định thực thi tương ứng:

| Mức | Bảo đảm chính | Có thể khiến một thread riêng lẻ chờ mãi? |
| --- | --- | --- |
| **Blocking** | Tiến triển có thể phụ thuộc một thread khác chạy/nhả lock. | Có; thread giữ lock bị dừng có thể chặn mọi contender. |
| **Obstruction-free** | Một thao tác có thể hoàn thành nếu được chạy đủ lâu mà không có tranh chấp từ thao tác khác. | Có. |
| **Lock-free** | Dưới việc thực thi tiếp tục, hệ thống có tiến triển: các thao tác không thể liên tục cản trở nhau mà không có lời gọi nào hoàn tất. | Có; một thread có thể luôn thua. |
| **Wait-free** | Mỗi lời gọi hoàn tất trong số bước của chính nó có giới hạn theo mô hình thuật toán. | Không, theo bảo đảm bước của thuật toán; thời gian thực vẫn phụ thuộc scheduling. |

Mối quan hệ khái niệm trong họ thuật toán không khóa là: **wait-free mạnh hơn lock-free, lock-free mạnh hơn obstruction-free**. `lock-free` không có nghĩa “không dùng bất kỳ cơ chế chờ nào ở hệ điều hành trong mọi tầng triển khai”, và một API có tên `Atomic*` không mặc nhiên chứng minh toàn bộ nghiệp vụ gọi nó là wait-free.

Với CAS retry:

```java
while (true) {
    int oldValue = counter.get();
    int newValue = oldValue + 1;
    if (counter.compareAndSet(oldValue, newValue)) {
        break;
    }
}
```

Nếu một CAS thất bại do giá trị đã đổi thì đã có một thay đổi do contender khác thành công. Đây là nền tảng thường gặp của lập luận tiến triển toàn hệ thống cho vòng lặp CAS đơn giản. Tuy nhiên thread đang chạy vòng lặp có thể thất bại nhiều lần, thậm chí bị starvation. Kết luận về thuật toán hoàn chỉnh còn phụ thuộc giả định, trạng thái chia sẻ, tác vụ trong vòng lặp và hành vi của tầng triển khai. Đừng tuyên bố `wait-free` khi chưa có giới hạn bước cho từng lời gọi.

**Mục tiêu thiết kế:** chọn mức progress theo yêu cầu. Một lock rõ ràng với timeout, phạm vi nhỏ và bất biến dễ chứng minh có thể phù hợp hơn vòng CAS phức tạp. Với yêu cầu độ trễ chặt, cần kiểm chứng cả phân phối latency, thời gian đợi lock và số lần retry, không chỉ throughput.

## 5. Starvation, fairness và chính sách cấp tài nguyên

*Fairness* mô tả cách phân phối cơ hội giữa các contender. Fair lock thường cố gắng ưu tiên những thread đã chờ lâu hơn; *nonfair lock* có thể cho contender mới lấy lock trước (*barging*) để cải thiện throughput trong một số tải.

Java cung cấp lựa chọn fairness cho một số primitive:

- `new ReentrantLock(true)`: dùng chính sách xếp hàng công bằng hơn cho các lần acquire lock thông thường; **không** bảo đảm tuyệt đối thứ tự thread chạy hay thời gian được CPU. `tryLock()` không thời hạn có thể lấy lock ngay cả khi còn thread chờ, kể cả lock fair.
- `new Semaphore(permits, true)`: dùng chính sách công bằng khi cấp permit tại các điểm xếp hàng được định nghĩa; không suy ra công bằng cho mọi hành động bên ngoài primitive.
- `synchronized`: không cung cấp hợp đồng FIFO/fairness để dựa vào khi thiết kế chống starvation.
- `Thread.yield()`, `Thread.setPriority()` và `Thread.sleep()`: không phải cơ chế bảo đảm fairness; lịch chạy tùy JVM/hệ điều hành.

Ví dụ quản lý lock an toàn, minh họa cú pháp Java 17:

```java
import java.util.concurrent.locks.ReentrantLock;

final class Inventory {
    private final ReentrantLock lock = new ReentrantLock(true);
    private int stock = 10;

    public boolean reserveOne() {
        lock.lock();
        try {
            if (stock == 0) {
                return false;
            }
            stock--;
            return true;
        } finally {
            lock.unlock();
        }
    }
}
```

Đây là **mảnh mã minh họa**, không phải chương trình có `main`. Phần `finally` bảo đảm nhả lock ngay cả khi phát sinh exception, giúp tránh giữ lock do sai sót. Cờ `true` tác động chính sách tranh chấp của lock nhưng không làm phương thức này thành wait-free và không bảo đảm latency tối đa. Trong hệ thống thực, cần đo throughput và tail latency trước khi bật fairness vì có thể có chi phí điều phối.

Starvation còn có thể đến từ **thread-pool starvation**: các tác vụ trong pool chờ kết quả của những tác vụ khác cũng được nộp vào chính pool đã kín thread chạy. Dù không có vòng chờ lock, không còn worker rảnh để thực hiện tác vụ được chờ. Hãy tránh cấu trúc chờ phụ thuộc như vậy, hoặc tách tài nguyên thực thi và xác định chính sách capacity/queue phù hợp.

## 6. Giảm nguy cơ deadlock và chờ vô hạn

### 6.1 Thứ tự lấy lock nhất quán

Nếu mọi đoạn mã cần cả `L1` lẫn `L2` đều lấy theo cùng thứ tự `L1` → `L2`, chúng loại bỏ được vòng chờ do **hai lock đó** đảo thứ tự. Quy tắc phải được áp dụng xuyên suốt các call path; phương thức ẩn lấy thêm lock có thể phá hỏng giả định. Tránh giữ lock trong lúc thực hiện I/O mạng, gọi callback không kiểm soát được hoặc chờ `Future.get()` dài hạn.

### 6.2 Chờ có thời hạn và xử lý interruption

Ví dụ thử lấy lock với timeout, đồng thời giữ đúng hợp đồng interruption:

```java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

final class TimedCriticalSection {
    private final ReentrantLock lock = new ReentrantLock();

    public boolean execute() throws InterruptedException {
        if (!lock.tryLock(200, TimeUnit.MILLISECONDS)) {
            return false;
        }
        try {
            // Thực hiện công việc ngắn, không chờ I/O vô hạn.
            return true;
        } finally {
            lock.unlock();
        }
    }
}
```

Đây cũng là **mảnh mã minh họa**. Timeout của acquire chỉ giới hạn thời gian **chờ lấy lock**, không giới hạn thời gian chạy trong critical section. Phương thức ném `InterruptedException` cho caller quyết định hủy/điều phối. Nếu bắt exception để kết thúc tác vụ, thông thường cần phục hồi cờ interruption bằng `Thread.currentThread().interrupt()` và thoát khỏi công việc. Không nuốt interruption rồi tiếp tục chờ vô hạn.

Dùng `Condition.await()` trong vòng `while` kiểm tra predicate, vì có thể có *spurious wakeup* và điều kiện có thể đã thay đổi sau khi thread tỉnh dậy:

```java
lock.lock();
try {
    while (!ready) {
        condition.await();
    }
    // Tiếp tục khi predicate ready còn đúng dưới lock.
} finally {
    lock.unlock();
}
```

Mảnh trên giả định `lock`, `condition` và `ready` đã được khai báo đúng và mọi thao tác với `ready` đều tuân thủ cùng giao thức đồng bộ. Chỉ gọi `signal()` không tự bảo đảm thread được đánh thức sẽ nhận CPU ngay hoặc hoàn thành kịp hạn.

Với producer/consumer, ưu tiên primitive có hợp đồng rõ như `BlockingQueue` và cân nhắc phiên bản có timeout (`offer(timeout)`, `poll(timeout)`) khi cần ngăn chờ vô hạn. Với `ExecutorService`, quy định rõ việc `shutdown()`, `awaitTermination(timeout)` và `shutdownNow()`; `shutdownNow()` chỉ cố gắng interruption, không ép task không hợp tác dừng ngay.

## 7. Cách kiểm chứng safety và liveness

### Kiểm chứng safety

1. Viết invariant bằng câu khẳng định có thể kiểm tra: “số dư không âm”, “mỗi ID chỉ chuyển trạng thái một lần”, “tổng số permit được cấp không vượt giới hạn”.
2. Xác định phạm vi atomic cần thiết: một biến, nhiều biến, hay cả một chuỗi trạng thái nghiệp vụ.
3. Lập luận mọi interleaving quan trọng có giữ invariant không; đánh dấu điểm tuyến tính hóa nếu API yêu cầu.
4. Dùng test đồng thời có điểm bắt đầu chung (`CountDownLatch`/`CyclicBarrier`) để tăng xác suất race; lặp stress test và kiểm tra trạng thái cuối. Test pass không phải chứng minh không có race.
5. Có thể dùng công cụ kiểm tra interleaving/JVM concurrency phù hợp khi cần bằng chứng sâu hơn; đừng suy từ một lần chạy ổn định rằng code an toàn.

### Kiểm chứng liveness/progress

1. Liệt kê tất cả nơi chờ: lock acquisition, `wait()`/`await()`, queue, `Future.get()`, I/O, `join()`, sleep, và task phụ thuộc lẫn nhau.
2. Với mỗi điểm chờ, xác định ai tạo điều kiện giải phóng, có thể bị chặn bởi chính người đang chờ không, và có timeout/cancellation không.
3. Đo thời gian đợi lock, số lần CAS retry, queue depth, throughput, tỉ lệ timeout và latency p95/p99 theo từng nhóm tác vụ; trung bình tốt có thể che giấu starvation.
4. Khi ứng dụng treo, thu thập thread dump (`jcmd <pid> Thread.dump_to_file ...` khi JVM hỗ trợ, hoặc `jstack <pid>` phù hợp với JDK/JVM). Xem trạng thái `BLOCKED`, `WAITING`, `TIMED_WAITING`, stack trace và quan hệ lock; một trạng thái `WAITING` đơn lẻ chưa chứng minh deadlock.
5. Java có `ThreadMXBean.findDeadlockedThreads()` để hỗ trợ tìm một số deadlock monitor/ownable synchronizer. Không tìm thấy deadlock bằng API này **không chứng minh** không có livelock, starvation, chờ I/O hoặc mọi loại vòng phụ thuộc.

Một thử nghiệm fairness thực tế cần áp dụng tải cạnh tranh đủ lâu và quan sát **mức phục vụ của từng thread**, không chỉ số thao tác mỗi giây toàn hệ thống. Đừng cố chứng minh “không bao giờ starvation” chỉ bằng một benchmark hữu hạn.

## 8. Chọn kỹ thuật theo bài toán

| Nhu cầu | Hướng thiết kế thường phù hợp | Điều vẫn phải kiểm tra |
| --- | --- | --- |
| Bảo vệ nhiều trường cùng một invariant | `synchronized` hoặc `Lock` chung cho mọi đường truy cập | Phạm vi lock, thứ tự lock, exception và contention |
| Một bộ đếm/trạng thái đơn giản cần cập nhật nguyên tử | `AtomicInteger`, `AtomicLong`, CAS phù hợp | Invariant đa bước, retry, khả năng starvation |
| Truyền tác vụ giữa producer và consumer | `BlockingQueue` có capacity phù hợp | Backpressure, shutdown, timeout, cancellation |
| Nhiều thread đọc, ít thread ghi | Cấu trúc concurrent phù hợp hoặc `ReadWriteLock` khi có lợi | Khả năng writer starvation, chi phí lock |
| Tài nguyên giới hạn số lượt truy cập | `Semaphore` và chính sách fairness khi cần | Permit leak, overflow tài nguyên, policy cấp permit |
| Phải hủy công việc khi quá thời gian | API timed wait/lock, interruption hợp tác | Mã bên trong có hợp tác hủy không; tài nguyên có được thu hồi không |

Đánh giá cả correctness lẫn performance. Fairness có thể cải thiện cơ hội phục vụ nhưng không bảo đảm thời hạn tuyệt đối; khóa ít hơn có thể tăng throughput nhưng làm lập luận safety khó hơn. Nếu không có yêu cầu đặc biệt, chọn primitive tiêu chuẩn có hợp đồng rõ và kiểm tra invariant trước khi tối ưu thuật toán.

## 9. Những hiểu lầm phổ biến

- **“Dùng `volatile` thì `count++` thread-safe.”** Sai: visibility không làm phép tăng ghép trở thành atomic.
- **“Mọi trường là `Atomic*` nên nghiệp vụ an toàn.”** Sai: invariant liên quan nhiều thao tác vẫn có thể bị chen vào.
- **“Không thấy race trong test tức là không có race.”** Sai: lịch xen kẽ hiếm có thể chưa xuất hiện.
- **“Không deadlock tức là chương trình có liveness.”** Sai: còn starvation, livelock, chờ I/O, chờ tín hiệu và task-pool starvation.
- **“Lock-free nghĩa là mọi thread đều nhanh.”** Sai: progress toàn hệ thống không bảo đảm một lời gọi riêng lẻ.
- **“Fair lock bảo đảm FIFO theo giờ tường và không có starvation trong mọi tình huống.”** Sai: còn JVM/OS scheduling, điểm tranh chấp, API lấy lock và lỗi logic bên ngoài.
- **“`sleep()` hoặc `yield()` sửa được race.”** Sai: thay đổi khả năng interleaving chứ không tạo atomicity hay quan hệ đồng bộ bắt buộc.
- **“Có timeout cho việc lấy lock thì toàn tác vụ có deadline.”** Sai: critical section và I/O bên trong vẫn có thể treo.

## 10. Tự kiểm tra kiến thức

1. Hai thread cùng gọi `if (atomic.get() > 0) atomic.decrementAndGet()`. Tính chất nào có thể bị vi phạm? **Safety**, vì check-then-act không atomic.
2. Thread A đợi `L2` khi đang giữ `L1`, B đợi `L1` khi đang giữ `L2`. Đó là gì? **Deadlock**, một thất bại liveness do phụ thuộc vòng tròn.
3. CAS loop vẫn có thao tác thành công, nhưng thread T liên tục thất bại. Điều gì có thể đúng? **Hệ thống có progress trong khi T bị starvation**.
4. `new ReentrantLock(true)` có bảo đảm mọi lời gọi kết thúc trong 100 ms không? **Không**: chính sách fairness không phải thời hạn thực thi và không kiểm soát OS scheduling.
5. Muốn chứng minh một thao tác wait-free, cần điều gì? **Giới hạn số bước của chính thao tác** theo các giả định thuật toán, thay vì chỉ thấy các thread khác vẫn hoàn thành.
6. Dữ liệu đúng nhưng một `Future.get()` không timeout chờ mãi. Safety hay liveness gặp vấn đề? **Liveness**, dù safety có thể vẫn được giữ.

**Ghi nhớ:** hãy bắt đầu bằng invariant để đánh giá safety, sau đó vẽ phụ thuộc chờ và chính sách cấp tài nguyên để đánh giá liveness. Phân biệt progress của *toàn hệ thống* với tiến triển của *từng thread*, và luôn kiểm tra khả năng starvation dưới tranh chấp thực tế.