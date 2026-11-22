# `lockInterruptibly()` và hỗ trợ hủy khi chờ lock trong Java

## 1. Bài toán: thread cần khóa nhưng không thể chờ mãi

Trong một chương trình Java đồng thời, nhiều thread có thể cần truy cập tài nguyên chung. `Lock` và `ReentrantLock` giúp bảo vệ critical section, nhưng có tình huống một thread **chưa lấy được khóa** vì thread khác đang giữ nó.

Nếu chỉ gọi `lock.lock()`, thread sẽ tiếp tục chờ cho đến khi chiếm được khóa, kể cả khi có yêu cầu `interrupt()` trong lúc chờ. Điều này có thể không phù hợp với tác vụ cần **hủy kịp thời**: người dùng đã hủy thao tác, request đã hết hạn, dịch vụ đang shutdown, hoặc một nhánh tính toán không còn cần thiết.

`Lock.lockInterruptibly()` là phương thức lấy khóa **có thể bị ngắt khi đang chờ**. Nó cho phép thread phản ứng với `Thread.interrupt()` bằng `InterruptedException` thay vì phải tiếp tục đợi khóa được giải phóng.

Ví dụ về nhu cầu:

- Worker A giữ khóa của một cấu trúc dữ liệu và làm một công việc tương đối lâu.
- Worker B cần cùng khóa nên phải chờ.
- Hệ thống yêu cầu hủy B trước khi B lấy được khóa.
- Nếu B dùng `lockInterruptibly()`, yêu cầu ngắt có thể làm B thoát khỏi bước chờ mà không vào critical section.
- Nếu B dùng `lock()`, yêu cầu ngắt **không tự kết thúc việc chờ khóa**; B có thể chỉ lấy được khóa sau khi A nhả và sau đó code phải tự kiểm tra trạng thái ngắt.

**Phạm vi:** hành vi các API khóa và cơ chế interrupt của **Java concurrency nói chung**, không phụ thuộc framework. Bài này giải thích rõ **hủy khi đang đợi khóa** chứ không đánh đồng interrupt với việc JVM cưỡng chế kết thúc thread.

## 2. API và hợp đồng cốt lõi

`java.util.concurrent.locks.Lock` định nghĩa:

```java
void lock();
void lockInterruptibly() throws InterruptedException;
boolean tryLock();
boolean tryLock(long time, TimeUnit unit)
        throws InterruptedException;
void unlock();
```

Đây là **chữ ký API rút gọn để minh họa**, không phải một lớp Java độc lập. `TimeUnit` thuộc `java.util.concurrent`.

Với implementation phổ biến `ReentrantLock`:

1. `lockInterruptibly()` cố lấy khóa. Nếu có thể lấy và không có yêu cầu interrupt cần xử lý, nó trả về bình thường và caller **đã sở hữu khóa**.
2. Nếu khóa đang do thread khác giữ, caller chờ theo cơ chế của lock; khi thread chờ bị interrupt, nó có thể thoát khỏi hàng chờ bằng `InterruptedException`.
3. Nếu thread đã có trạng thái interrupted khi gọi `lockInterruptibly()`, nó ném `InterruptedException` ngay cả trong trường hợp khóa đang sẵn sàng; thao tác này ưu tiên phản ứng với interrupt hơn việc lấy khóa bình thường/tái nhập theo hợp đồng của `ReentrantLock`.
4. Nếu `lockInterruptibly()` ném `InterruptedException` do việc chờ lấy khóa, caller **không được coi mình đã lấy được khóa từ lời gọi đó**; tuyệt đối không gọi `unlock()` một cách vô điều kiện.
5. Nếu `lockInterruptibly()` trả về thành công, caller phải **luôn nhả khóa** sau critical section, thường bằng `try/finally`.

Mẫu chuẩn:

```java
lock.lockInterruptibly();    // Có thể ném InterruptedException trước khi lấy lock.
try {
    // Chỉ đến đây khi đã lấy được lock.
    updateSharedState();
} finally {
    lock.unlock();
}
```

Đây là đoạn minh họa trong phương thức đã khai báo hoặc xử lý `InterruptedException`; `lock` và `updateSharedState()` do ứng dụng định nghĩa. Chú ý `try` chỉ bắt đầu **sau** khi `lockInterruptibly()` thành công. Nếu đưa `lockInterruptibly()` vào bên trong một khối `try/finally` rồi gọi `unlock()` vô điều kiện, exception có thể khiến code cố nhả khóa chưa hề sở hữu và phát sinh `IllegalMonitorStateException`.

## 3. So sánh `lock()`, `lockInterruptibly()` và hai dạng `tryLock()`

| API | Nếu khóa đang bận | Phản ứng với interrupt khi chờ | Timeout | Kết quả |
| --- | --- | --- | --- | --- |
| `lock.lock()` | Chờ đến khi lấy được khóa | Với `ReentrantLock`, tiếp tục chờ; khôi phục/giữ trạng thái interrupt khi trả về | Không | `void`; trả về nghĩa là đã lấy khóa |
| `lock.lockInterruptibly()` | Chờ khóa với khả năng ngắt | Ném `InterruptedException` và thoát bước chờ | Không | `void`; trả về bình thường nghĩa là đã lấy khóa |
| `lock.tryLock()` | **Không chờ**, trả về ngay | Không phải API chờ có thể bị ngắt | Không | `true` nếu lấy được, `false` nếu không |
| `lock.tryLock(timeout, unit)` | Chờ tối đa khoảng thời gian yêu cầu | Ném `InterruptedException` khi đang chờ hoặc khi đã bị ngắt trước khi gọi | Có | `true` nếu lấy được; `false` nếu hết thời hạn |

**Không nhầm:** `lockInterruptibly()` **không tự đặt timeout**. Nếu không ai gọi `interrupt()` và không ai nhả khóa, thread vẫn có thể chờ vô hạn. Muốn tự giới hạn thời gian, dùng `tryLock(timeout, unit)` và xử lý cả `false` lẫn `InterruptedException`.

Với `ReentrantLock`, `lock()` là phương thức lấy khóa không hủy được *trong giai đoạn đợi khóa*. Nếu bị interrupt khi đang chờ, nó vẫn có thể đợi đến lúc lấy được khóa; trạng thái interrupt được giữ/khôi phục để code sau đó quan sát. Điều này **không có nghĩa** `interrupt()` hoàn toàn vô hiệu: lời gọi interrupt là một tín hiệu hợp tác mà các API khác hoặc code sau khi lấy khóa có thể xử lý.

Với `synchronized(monitor)`, việc **đợi vào monitor** cũng không có overload có thể hủy bằng `InterruptedException` hoặc deadline. Không thể trực tiếp thay `synchronized` bằng một cú pháp “interruptibly”. Khi yêu cầu khả năng hủy đợi khóa, `ReentrantLock` có lợi thế về API.

## 4. `Thread.interrupt()` là yêu cầu hợp tác, không phải cưỡng chế dừng

`Thread.interrupt()` đánh dấu trạng thái interrupt hoặc làm một số thao tác đang chờ theo cơ chế interruptible ném `InterruptedException`. Nó **không** cưỡng chế thread bị dừng ngay, không rollback các cập nhật đã làm, và không tự giải phóng khóa mà thread đang giữ.

Phân biệt ba thời điểm:

### 4.1. Interrupt trước khi lấy khóa

Nếu worker đang đợi tại `lockInterruptibly()`, yêu cầu interrupt cho phép nó ném `InterruptedException` và rời hàng chờ. Worker không vào phần xử lý cần khóa.

### 4.2. Interrupt sau khi đã lấy khóa

`lockInterruptibly()` đã **trả về bình thường** thì worker đang sở hữu khóa. Một lần interrupt tiếp theo **không tự nhả khóa** và không tự dừng critical section. Worker phải hợp tác: kiểm tra tín hiệu, xử lý `InterruptedException` từ các phương thức chặn khác, giữ bất biến dữ liệu, sau đó rời `try/finally` để nhả khóa.

### 4.3. Interrupt trong lúc chờ API khác

`Thread.sleep()`, `Object.wait()`, `Thread.join()`, `Condition.await()` và các phương thức chờ có thể bị ngắt khác có hợp đồng interrupt riêng. Mọi đường thoát khỏi critical section do exception đều phải được quản lý để `finally` nhả lock đã lấy.

**Ví dụ quan trọng:** worker đã vào critical section và đang gọi `Thread.sleep()`. Nếu bị interrupt, `sleep` ném `InterruptedException`; luồng phải thoát qua `finally` để `unlock()`. Dùng `lockInterruptibly()` lúc đầu chỉ giải quyết việc **đợi lấy khóa**, không thay công việc thiết kế logic hủy ở bên trong critical section.

## 5. Ví dụ xác định: hủy worker đang đợi `lockInterruptibly()`

Chương trình dưới dùng `CountDownLatch` để điều phối: **main giữ khóa**, worker chuẩn bị lấy khóa, main phát yêu cầu interrupt, worker kết thúc đường chờ, và main kiểm tra rằng nó vẫn giữ lock. Không dựa vào `Thread.sleep` để đoán khi nào worker đã thực sự bị block.

Tạo tệp `InterruptibleLockDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.ReentrantLock;

public class InterruptibleLockDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        CountDownLatch attempting = new CountDownLatch(1);

        lock.lock(); // Main cố tình giữ khóa khi worker bắt đầu.
        try {
            Thread worker = new Thread(() -> {
                attempting.countDown();

                try {
                    lock.lockInterruptibly();
                } catch (InterruptedException e) {
                    System.out.println("worker: bị hủy khi xin khóa");
                    Thread.currentThread().interrupt();
                    return;
                }

                try {
                    System.out.println("worker: đã vào vùng bảo vệ");
                } finally {
                    lock.unlock();
                }
            }, "worker");

            worker.start();
            attempting.await();
            worker.interrupt();
            worker.join();

            System.out.println("main giữ khóa: "
                    + lock.isHeldByCurrentThread());
        } finally {
            lock.unlock();
        }
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac InterruptibleLockDemo.java
java InterruptibleLockDemo
```

Kết quả khi không có yêu cầu interrupt bên ngoài dành cho main:

```text
worker: bị hủy khi xin khóa
main giữ khóa: true
```

Lập luận theo thứ tự:

1. Main gọi `lock.lock()` trước khi tạo worker và **không nhả lock trước `worker.join()`**.
2. Worker phát tín hiệu `attempting.countDown()` rồi gọi `lock.lockInterruptibly()`.
3. Main nhận `attempting.await()`, gọi `worker.interrupt()`.
4. Nếu worker chưa kịp gọi `lockInterruptibly()`, cờ interrupted đã được đặt và lời gọi sắp tới ném exception. Nếu worker đã đứng chờ khóa, interrupt đánh thức thao tác chờ và khiến nó ném exception. **Cả hai trường hợp đều không để worker lấy khóa từ main.**
5. Worker in dòng hủy, khôi phục trạng thái interrupt và kết thúc runnable. `join()` bảo đảm main in sau worker.
6. Main vẫn giữ lock cho đến `finally`. Vì vậy dòng “worker: đã vào vùng bảo vệ” không thể xuất hiện trên đường chạy này.

**Tại sao `lock.unlock()` ở worker không bị gọi khi cancel?** Vì khối `try/finally` giải phóng nằm **sau** khi `lockInterruptibly()` trả về thành công. Khi có `InterruptedException`, worker rời khỏi nhánh bắt lỗi; nó không sở hữu lock nên không được `unlock()`.

Ví dụ đặt `Thread.currentThread().interrupt()` trước khi `return` để tầng gọi (nếu có) không mất thông tin hủy. Với một method cho phép `throws InterruptedException`, cách sạch hơn thường là **truyền tiếp exception**, không nhất thiết phải bắt và khôi phục cờ tại mọi tầng.

## 6. So sánh bằng ví dụ: `lock()` vẫn chờ dù bị interrupt

Trong ví dụ tiếp theo, main tiếp tục giữ khóa khi gửi interrupt. Worker dùng `lock()`, nên interrupt **không làm bước xin khóa trả về bằng exception**. Sau khi main nhả khóa, worker mới có thể vào critical section và kiểm tra cờ interrupt.

Tạo tệp `NonInterruptibleLockDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.ReentrantLock;

public class NonInterruptibleLockDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        CountDownLatch attempting = new CountDownLatch(1);

        lock.lock();
        Thread worker = new Thread(() -> {
            attempting.countDown();
            lock.lock();
            try {
                System.out.println("worker đã lấy khóa, interrupted="
                        + Thread.currentThread().isInterrupted());
            } finally {
                lock.unlock();
            }
        }, "worker");

        try {
            worker.start();
            attempting.await();
            worker.interrupt();

            System.out.println("main: sẽ nhả khóa");
        } finally {
            lock.unlock();
        }

        worker.join();
        System.out.println("main: worker đã xong");
    }
}
```

```bash
javac NonInterruptibleLockDemo.java
java NonInterruptibleLockDemo
```

Kết quả với `ReentrantLock`, khi main không bị interrupt từ bên ngoài:

```text
main: sẽ nhả khóa
worker đã lấy khóa, interrupted=true
main: worker đã xong
```

Giải thích:

- Main còn giữ khóa lúc gọi `worker.interrupt()` nên worker chưa thể chiếm khóa sớm.
- Worker dùng `lock()`, vì vậy nó không ném `InterruptedException` từ thao tác xin khóa.
- Với `ReentrantLock`, nếu bị interrupt trong lúc chờ, phương thức tiếp tục đợi rồi trả về với trạng thái interrupt được giữ/khôi phục. Cờ được thấy ở code sau khi khóa đã được lấy.
- Main in trước khi nhả khóa trong `finally`, nên thứ tự ba dòng là xác định nhờ `join()` và lock.

**Không diễn giải sai:** vì worker đã có trạng thái interrupted sau khi `lock()` trả về, một lời gọi `Thread.sleep()` tiếp theo có thể ném `InterruptedException` ngay. Code không được lờ đi việc này nếu nó cần khả năng hủy an toàn.

Nếu nghiệp vụ thật sự không cho phép hủy khi xin khóa, `lock()` có thể đúng. Nhưng nếu một task đang chờ rất lâu hoặc bị khóa bởi tài nguyên khác, chọn `lockInterruptibly()` làm hệ thống phản hồi yêu cầu hủy tốt hơn.

## 7. Khi nào dùng `tryLock(timeout, unit)`?

`lockInterruptibly()` không có deadline riêng. Một task chỉ cần chờ **tối đa một khoảng thời gian** có thể dùng:

```java
boolean acquired = lock.tryLock(250, TimeUnit.MILLISECONDS);
if (!acquired) {
    // Hết thời gian chờ, chưa lấy được khóa.
    return;
}
try {
    updateSharedState();
} finally {
    lock.unlock();
}
```

Đây là đoạn minh họa bên trong phương thức đã xử lý `InterruptedException`, có `lock` và `updateSharedState()`. Khác `lockInterruptibly()`, API có thể trả về `false` khi deadline hết. Nó **vẫn hỗ trợ interrupt** trong khi chờ, và có thể ném `InterruptedException`.

### Ví dụ không phụ thuộc may rủi của timeout

Tạo tệp `TimedTryLockDemo.java`:

```java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public class TimedTryLockDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();

        lock.lock();
        try {
            Thread worker = new Thread(() -> {
                boolean acquired;
                try {
                    acquired = lock.tryLock(100, TimeUnit.MILLISECONDS);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    System.out.println("worker: bị ngắt");
                    return;
                }

                if (!acquired) {
                    System.out.println("worker: hết thời gian chờ");
                    return;
                }

                try {
                    System.out.println("worker: đã lấy khóa");
                } finally {
                    lock.unlock();
                }
            }, "worker");

            worker.start();
            worker.join(); // Main vẫn giữ khóa cho đến khi worker kết thúc.
        } finally {
            lock.unlock();
        }

        System.out.println("main: hoàn thành");
    }
}
```

```bash
javac TimedTryLockDemo.java
java TimedTryLockDemo
```

Kết quả khi không có interrupt ngoài ý muốn:

```text
worker: hết thời gian chờ
main: hoàn thành
```

Vì main giữ lock suốt lúc `worker.join()`, worker chắc chắn không lấy được lock trong thời hạn và phải nhận `false`. Đây là một phép thử minh họa deadline, **không nên mô phỏng cách tổ chức hệ thống thật bằng cách giữ khóa trong lúc đợi worker không thể tiến triển**. Với công việc có tài nguyên được chia sẻ, cần tránh giữ khóa rộng hơn mức cần thiết.

Một điểm tinh tế: timeout đo **khoảng chờ tối đa theo hợp đồng API, phụ thuộc lịch chạy và thời gian hệ thống**; mã ứng dụng không nên xem `100 ms` là một mốc tuyệt đối chính xác. Đừng dùng các phép `sleep(100)` để xác minh logic concurrency trong bài test.

### `tryLock()` không timeout là một lựa chọn khác

`lock.tryLock()` cố lấy khóa ngay và trả về `true` hoặc `false`. Nếu ứng dụng có phương án fallback tức thời, đây có thể là API rõ nhất:

```java
if (lock.tryLock()) {
    try {
        doWork();
    } finally {
        lock.unlock();
    }
} else {
    doSomethingElse();
}
```

Đây là minh họa, chưa phải chương trình độc lập. `tryLock()` không đợi đến khi có interrupt. Thêm nữa, trên một `ReentrantLock` được cấu hình fair, `tryLock()` không tham gia hoàn toàn chính sách công bằng hàng chờ; nó có thể “barging” khi lock rảnh. Nếu yêu cầu fairness của hàng chờ, cần hiểu hợp đồng riêng của `tryLock(timeout, unit)`.

## 8. Phân biệt interrupt khi chờ khóa và interrupt trong critical section

Không nên viết:

```java
lock.lockInterruptibly();
try {
    performLongRunningTask();
} finally {
    lock.unlock();
}
```

rồi kết luận rằng `performLongRunningTask()` chắc chắn dừng ngay khi có `Thread.interrupt()`. Một khi lock đã được lấy, hành vi hủy của task phụ thuộc vào **nội dung method đó**.

Nếu công việc CPU-bound lặp nhiều lần, cân nhắc kiểm tra trạng thái ngắt ở những điểm an toàn:

```java
lock.lockInterruptibly();
try {
    for (int i = 0; i < batches.size(); i++) {
        if (Thread.currentThread().isInterrupted()) {
            throw new InterruptedException("cancelled during work");
        }
        processBatch(batches.get(i));
    }
} finally {
    lock.unlock();
}
```

Đây là mã minh họa trong phương thức khai báo `throws InterruptedException`; `batches` và `processBatch` là dữ liệu/logic của ứng dụng. Việc ném exception trong `try` vẫn dẫn tới `finally` và nhả lock.

Tuy nhiên, **không được bỏ dở một thay đổi dữ liệu nhiều bước ở trạng thái sai** chỉ vì thread bị interrupt. Trong các critical section chứa invariant, hãy thiết kế một trong các hướng:

- Kiểm tra interrupt **trước khi bắt đầu giao dịch nội bộ**;
- Hoàn thành hoặc rollback một đơn vị thay đổi cần nguyên tử trước khi phản hồi hủy;
- Chia công việc thành các phần nhỏ có điểm commit nhất quán;
- Dùng giao dịch/compensation tương ứng nếu có tài nguyên ngoài JVM.

`ReentrantLock` chỉ cung cấp loại trừ lẫn nhau và quan hệ bộ nhớ; nó không rollback thay đổi đang thực hiện khi có exception hay interrupt.

### Cờ interrupt cũng là dữ liệu điều khiển

`Thread.currentThread().isInterrupted()` đọc trạng thái của thread **không xóa cờ**. `Thread.interrupted()` là phương thức static, đọc và **xóa cờ** của thread hiện tại. Chúng không thay thế nhau một cách tùy tiện.

Ví dụ:

```java
if (Thread.currentThread().isInterrupted()) {
    // Có tín hiệu hủy, cờ vẫn được giữ.
}
```

Ngược lại, gọi `Thread.interrupted()` nhiều lần khi không có interrupt mới có thể trả về `true` lần đầu rồi `false` lần sau. Nếu không có lý do rõ ràng, đừng vô ý tiêu thụ trạng thái ngắt trước khi thành phần khác có cơ hội xử lý.

## 9. `InterruptedException` và việc khôi phục trạng thái interrupt

Khi một API chờ có khả năng bị ngắt ném `InterruptedException`, trạng thái interrupt của thread thường được **xóa khi exception được phát ra** theo hợp đồng của API đó (bao gồm `ReentrantLock.lockInterruptibly()`). Điều này tránh truyền cùng một tín hiệu theo hai cơ chế khác nhau mà không có ý định.

Có hai cách xử lý phổ biến:

**Cách A — truyền exception lên tầng gọi** khi chữ ký phương thức cho phép:

```java
void transfer() throws InterruptedException {
    lock.lockInterruptibly();
    try {
        updateBalances();
    } finally {
        lock.unlock();
    }
}
```

**Cách B — khôi phục cờ và kết thúc công việc** khi không thể khai báo exception tại tầng hiện tại:

```java
void runTask() {
    try {
        lock.lockInterruptibly();
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        return;
    }
    try {
        updateBalances();
    } finally {
        lock.unlock();
    }
}
```

Đây là **hai đoạn minh họa**, với `lock` và `updateBalances()` được khai báo ở lớp thích hợp. Cách B khôi phục cờ vì `Runnable.run()` không thể khai báo thêm checked exception `InterruptedException`.

Lỗi phổ biến:

```java
try {
    lock.lockInterruptibly();
} catch (InterruptedException ignored) {
    // Bỏ qua rồi vẫn tiếp tục thao tác như đã có khóa: SAI.
}
updateBalances(); // Có thể truy cập state mà chưa giữ lock.
```

Đừng bắt exception rồi **đi tiếp như thể đã chiếm khóa**. Khi bị ngắt ở lúc xin khóa, phải rời task, truyền exception lên trên hoặc có một cơ chế retry được thiết kế rõ. Nếu tự retry vô hạn bất kể interrupt, bạn đã làm mất khả năng hủy vốn là lý do chọn `lockInterruptibly()`.

Ngoài ra, việc bắt và khôi phục cờ *không đủ* nếu code vẫn chạy tiếp và thực hiện các API chặn khác ngoài dự kiến. Hãy xác định rõ trạng thái “canceled” và đường thoát của tác vụ.

## 10. Hủy một task của `ExecutorService` bằng `Future.cancel(true)`

Trong Java, nhiều task được gửi vào `ExecutorService` thay vì tự tạo từng `Thread`. Nếu muốn hủy task đang thực thi, `Future.cancel(true)` **yêu cầu interrupt thread đang chạy task** (khi executor hỗ trợ theo hợp đồng tương ứng). Khi task đợi tại `lockInterruptibly()`, yêu cầu interrupt có thể khiến nó rời bước chờ.

Tạo tệp `FutureLockCancellationDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.locks.ReentrantLock;

public class FutureLockCancellationDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        CountDownLatch attempting = new CountDownLatch(1);
        CountDownLatch taskExited = new CountDownLatch(1);
        ExecutorService executor = Executors.newSingleThreadExecutor();

        lock.lock(); // Main cố ý giữ lock khi task được gửi vào.
        try {
            Future<?> future = executor.submit(() -> {
                try {
                    attempting.countDown();
                    lock.lockInterruptibly();
                    try {
                        System.out.println("task: đã lấy khóa");
                    } finally {
                        lock.unlock();
                    }
                } catch (InterruptedException e) {
                    System.out.println("task: dừng chờ khóa");
                    Thread.currentThread().interrupt();
                } finally {
                    taskExited.countDown();
                }
            });

            attempting.await();
            boolean cancelled = future.cancel(true);
            taskExited.await();
            System.out.println("future cancelled=" + cancelled);
        } finally {
            lock.unlock();
            executor.shutdown();
        }
    }
}
```

```bash
javac FutureLockCancellationDemo.java
java FutureLockCancellationDemo
```

Kết quả khi không có yêu cầu interrupt bên ngoài dành cho main:

```text
task: dừng chờ khóa
future cancelled=true
```

Lý do kết quả xác định:

1. Main đã giữ `lock` nên task không thể lấy khóa trước khi có hủy.
2. `attempting.countDown()` bảo đảm main chỉ gọi `cancel(true)` sau khi task đã bắt đầu runnable.
3. `future.cancel(true)` đánh dấu yêu cầu hủy và gửi interrupt tới thread thực thi task. Task phản ứng ở `lockInterruptibly()`, đi vào `catch` và rời đường chờ.
4. `taskExited.await()` buộc main chờ khối `finally` của task thực thi, nên thông báo của task in trước dòng kết quả.
5. Main chỉ nhả khóa và gọi `executor.shutdown()` sau các bước đó.

**Cảnh báo:** `Future.isCancelled() == true` hoặc `cancel(true)` trả về `true` **không đồng nghĩa task đã thực sự ngừng và dọn dẹp xong** trong mọi chương trình. Future có thể chuyển sang trạng thái canceled trước khi worker hoàn tất cleanup; nếu task bỏ qua interrupt, nó còn có thể tiếp tục. Trong ví dụ có `taskExited` để xác nhận một điểm dọn dẹp cụ thể. Đừng chỉ dựa vào `Future.get()` sau cancellation để chờ phần cleanup xong, vì `get()` trên Future bị hủy ném `CancellationException`.

`cancel(false)` không yêu cầu interrupt task đang chạy; vì vậy không thể kỳ vọng nó đánh thức một task bị chặn tại `lockInterruptibly()`. `ExecutorService.shutdownNow()` cũng gửi tín hiệu interrupt theo khả năng của executor, nhưng không bảo đảm mọi task lập tức ngừng. Việc thiết kế task **hợp tác với interrupt** là trách nhiệm của code ứng dụng.

## 11. `lockInterruptibly()` có giúp tránh deadlock không?

**Có thể giúp một thread thoát khỏi đợi khóa khi bị hủy**, nhưng không tự phát hiện hay ngăn mọi deadlock.

Ví dụ hai tài nguyên có hai `ReentrantLock`:

```text
Thread A: giữ lock X ───> chờ lock Y
Thread B: giữ lock Y ───> chờ lock X
```

Nếu các bước đợi khóa thứ hai đều dùng `lockInterruptibly()`, hệ thống có thể **gửi interrupt có chủ đích** tới một trong hai thread đang chờ. Thread đó bắt `InterruptedException`, thoát các `finally` để nhả những khóa nó đã lấy, nhờ đó có thể phá vòng chờ.

Nhưng phải có đủ điều kiện:

- Có một thành phần phát hiện timeout, nhận yêu cầu hủy hoặc quyết định interrupt thread cần hủy. `lockInterruptibly()` tự nó **không phát hiện deadlock**.
- Mỗi lock đã lấy được phải nhả trong `finally`, kể cả khi bước lấy lock tiếp theo bị ngắt.
- Không được để một tác vụ vẫn giữ lock ở chỗ khác vì xử lý exception sai hoặc vì đang chờ một hoạt động **không hỗ trợ interrupt**.
- Không làm hỏng invariant khi thoát từ giữa một thao tác cập nhật nhiều bước.

Mẫu lấy hai khóa với đường dọn dẹp rõ:

```java
first.lockInterruptibly();
try {
    second.lockInterruptibly();
    try {
        changeBothResources();
    } finally {
        second.unlock();
    }
} finally {
    first.unlock();
}
```

Đây là đoạn minh họa, giả định `first` và `second` là `Lock` và `changeBothResources()` được định nghĩa trong ứng dụng. Nếu bị interrupt khi chờ `second`, chỉ `first` đã lấy được nên `finally` ngoài nhả nó. Nếu bị interrupt khi chờ `first`, chưa vào khối `try` nào nên không gọi `unlock()`.

**Biện pháp phòng deadlock ưu tiên vẫn là thứ tự lấy khóa nhất quán** (ví dụ luôn khóa theo ID tài nguyên tăng dần) và giảm việc giữ nhiều lock lồng nhau. Interruptible acquisition là một lớp hỗ trợ hủy/khôi phục, không thay thế thiết kế khóa đúng.

## 12. Hợp đồng `ReentrantLock`, fairness và reentrancy

`ReentrantLock` là một implementation reentrant của `Lock`. Thread đã giữ khóa có thể lấy lại cùng lock (hold count tăng), và phải nhả tương ứng số lần đã lấy. Với `lockInterruptibly()`, **nếu thread đã bị interrupted**, lời gọi có thể ném `InterruptedException` ngay thay vì tái nhập khóa theo hợp đồng ưu tiên xử lý ngắt. Không nên viết code giả định lời gọi này chắc chắn thành công chỉ vì chính mình đang giữ lock.

Với `ReentrantLock(true)` (fair lock), việc chờ khóa của `lock()` và `lockInterruptibly()` thường tuân theo chính sách ưu tiên thread chờ lâu hơn trong điều kiện contention. Tuy nhiên:

- Fairness không bảo đảm thứ tự task được CPU lập lịch hoặc độ trễ tối đa.
- `tryLock()` không timeout có thể lấy khóa ngay nếu nó đang rảnh, kể cả có thread khác chờ, theo hợp đồng của `ReentrantLock`.
- Fair locking thường có tradeoff về throughput; chọn dựa trên đo lường và yêu cầu ứng dụng.
- Reentrancy không thay đổi yêu cầu `unlock()` đúng số lần và thuộc về đúng thread đang giữ lock.

`isLocked()` chỉ cho biết tại thời điểm kiểm tra có thread đang giữ lock hay không. Nó **không** nói rằng thread hiện tại được phép nhả. `isHeldByCurrentThread()` giúp chẩn đoán quyền sở hữu của thread hiện tại, nhưng nên thiết kế nhánh lấy/nhả cho đúng thay vì phụ thuộc vào kiểm tra trạng thái để chữa một giao thức khóa sai.

## 13. Trạng thái thread khi đợi `ReentrantLock`

Khi một thread đợi `ReentrantLock`, implementation Java thường chặn qua cơ chế đồng bộ của `java.util.concurrent.locks` (ví dụ `LockSupport.park`). Trạng thái quan sát qua `Thread.getState()` có thể là `WAITING`, hoặc `TIMED_WAITING` với thời hạn.

**Đừng mặc định mọi thread chờ lock đều ở `BLOCKED`.** Theo ý nghĩa của `Thread.State`, `BLOCKED` dùng cho thread chờ monitor của `synchronized`. Một thread chờ `ReentrantLock` không bắt buộc biểu hiện như thread đang xin intrinsic monitor.

Dù `getState()` hữu ích khi chẩn đoán, đây chỉ là một snapshot. Không kiểm tra `worker.getState() == WAITING` rồi suy ra worker chắc chắn đã gọi đúng API. Để viết test xác định, sử dụng `CountDownLatch`/`Phaser`/điều phối phù hợp, sau đó khẳng định hành vi mong muốn qua kết quả, như ví dụ trong bài.

Sự khác biệt giữa platform thread và virtual thread (Java 21+) không đổi **hợp đồng của `Lock.lockInterruptibly()`**: thread chờ có thể phản ứng với interrupt. Cơ chế JVM sử dụng carrier thread khi virtual thread chờ là chi tiết lập lịch; không nên dùng nó để bỏ qua kiểm tra cancel hoặc logic nhả khóa. Khả năng interrupt và tình huống blocking thực tế vẫn cần được kiểm tra trên thư viện, JDK và workload sử dụng.

## 14. Quan hệ với `Condition.await()`

`ReentrantLock` thường kết hợp với `Condition` để chờ một **điều kiện dữ liệu**, không chỉ chờ lấy khóa. Hai hành động này khác nhau:

1. **`lock.lockInterruptibly()`:** chờ quyền sở hữu **lock**.
2. **`condition.await()`:** caller **đã giữ lock**, tạm nhả lock và chờ điều kiện được báo hiệu; khi trở về, caller lấy lại lock trước khi tiếp tục theo hợp đồng Condition.

Ví dụ minh họa:

```java
lock.lockInterruptibly();
try {
    while (!ready) {
        condition.await();
    }
    consumeReadyData();
} finally {
    lock.unlock();
}
```

Đây là đoạn minh họa với `lock`, `condition` được tạo từ `lock.newCondition()`, còn `ready` và `consumeReadyData()` do ứng dụng định nghĩa.

`Condition.await()` thường cũng có thể bị ngắt và ném `InterruptedException`. Vì vậy dù ngắt xảy ra ở **giai đoạn xin khóa** hay **giai đoạn đợi điều kiện sau khi đã có khóa**, code cần xử lý hợp đồng cho đúng:

- Nếu `lockInterruptibly()` ném exception, **không có lock** để nhả.
- Nếu `condition.await()` ném exception, caller đã lấy lock trước đó; theo hợp đồng `Condition` phù hợp, việc chờ đã quản lý nhả/lấy lại lock trước khi trở về/throw; khối `finally` ngoài vẫn phải `unlock()`.
- Kiểm tra điều kiện dưới `while` chứ không chỉ `if`, vì wakeup không đồng nghĩa condition đã đúng.

Không dùng `Thread.sleep()` trong lúc giữ `ReentrantLock` để chờ thread khác sửa `ready` dưới cùng lock: `sleep` không nhả lock, khiến thread kia không thể cập nhật dữ liệu. `Condition.await()` mới là cơ chế chờ điều kiện phù hợp với `ReentrantLock`.

## 15. Hủy có trách nhiệm: resource cleanup và tính nhất quán

Hỗ trợ hủy nhanh là mục tiêu quan trọng, nhưng **không đánh đổi bằng trạng thái dữ liệu sai**.

### 15.1. Đặt điểm hủy ở ranh giới an toàn

Nếu task chỉ cần đọc hoặc làm việc độc lập, có thể kiểm tra interrupt thường xuyên. Nếu task giữ lock để cập nhật nhiều trường liên quan, hãy xác định một đơn vị nguyên tử nghiệp vụ (một transaction trong bộ nhớ hoặc một batch) và chỉ hủy tại các điểm không phá invariant.

### 15.2. Không nhả lock khi chưa lấy được

Code nhả khóa phải chỉ chạy trên đường lấy khóa thành công:

```java
try {
    lock.lockInterruptibly();
    try {
        doWork();
    } finally {
        lock.unlock();
    }
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
}
```

Đoạn này minh họa cách đặt `try/finally` lồng nhau. Nó hợp lệ về mặt unlock vì `finally` trong chỉ được vào sau `lockInterruptibly()` đã trả về. Nếu catch xong mà task còn việc cần lock, phải dừng chứ không được tiếp tục vào vùng dữ liệu bảo vệ mà không có khóa.

### 15.3. Không giữ lock khi làm I/O không kiểm soát

Nếu critical section bao trùm gọi mạng, đợi Future, thao tác file chậm hoặc callback tùy ý, thread khác có thể chờ khóa rất lâu. Điều này tăng nhu cầu cancellation và có thể gây vòng chờ. Khi có thể, tính toán hoặc thực hiện I/O bên ngoài critical section, rồi lấy lock ngắn để kiểm tra/commit dữ liệu. Nhưng **đừng chia nhỏ critical section làm vi phạm invariant**.

### 15.4. Chính sách hủy nên được mô tả rõ

Trong API của một worker hoặc service, trả lời:

- Request hủy đi qua kênh nào: `Future.cancel(true)`, `Thread.interrupt()` hay token riêng?
- Nếu chưa lấy được lock, có bỏ task hoàn toàn không?
- Nếu đang giữ lock, có điểm rollback/commit an toàn không?
- Nếu deadline hết, trả về trạng thái gì và ai chịu trách nhiệm retry?
- Exception có được propagate hay chuyển thành response lỗi có cấu trúc?
- Có xác nhận tài nguyên/lock được dọn xong trước khi báo “đã dừng” không?

Không sử dụng `Thread.stop()` để cưỡng chế kết thúc thread đang giữ khóa; đây là API không an toàn và đã bị deprecated từ lâu.

## 16. Các lỗi phổ biến

### Lỗi 1 — gọi `unlock()` dù `lockInterruptibly()` đã ném exception

```java
try {
    lock.lockInterruptibly();
    update();
} finally {
    lock.unlock();  // Có thể chưa lấy được lock!
}
```

**Sai.** Đặt lời gọi `lockInterruptibly()` bên ngoài `try/finally` bảo vệ critical section hoặc dùng biến `acquired` được quản lý cẩn thận.

### Lỗi 2 — bắt `InterruptedException` rồi nuốt tín hiệu

```java
try {
    lock.lockInterruptibly();
} catch (InterruptedException ignored) {
    // Không báo lên và cũng không khôi phục interrupt.
}
```

**Sai nếu ứng dụng yêu cầu khả năng hủy.** Truyền exception lên tầng gọi, hoặc khôi phục cờ và kết thúc công việc khi không thể propagate. Không tiếp tục thao tác cần lock mà chưa có lock.

### Lỗi 3 — nghĩ `lockInterruptibly()` sẽ ngừng mọi code sau khi lấy khóa

Phương thức chỉ giải quyết giai đoạn acquisition. Sau khi đã lấy lock, task phải tự hợp tác với interrupt, chịu trách nhiệm invariant và unlock.

### Lỗi 4 — dùng `lock()` rồi trông chờ `Future.cancel(true)` dừng ngay

Một task đang đợi `ReentrantLock.lock()` có thể tiếp tục đợi dù đã interrupt. Nếu cần cancel khi đang chờ, dùng `lockInterruptibly()` hoặc timed `tryLock` có hợp đồng phù hợp.

### Lỗi 5 — không phân biệt timeout và interrupt

`tryLock(timeout, unit)` trả về `false` khi hết thời gian nhưng **ném `InterruptedException`** khi bị ngắt. Hai tình huống có thể cần kết quả nghiệp vụ khác nhau; đừng gom cả hai thành một trạng thái chung mà mất thông tin.

### Lỗi 6 — đoán thứ tự thread bằng `sleep()`

Lịch chạy CPU không được cam kết. Trong unit test concurrency, dùng latch/phaser/điều phối để chứng minh precondition và việc kết thúc. Tránh viết test dựa trên “sleep 50 ms chắc worker đã chờ lock”.

### Lỗi 7 — tưởng `cancel(true)` là task đã sạch tài nguyên

`Future` có thể được đánh dấu canceled trước khi task thực sự hoàn thành cleanup. Khi cần xác minh dọn dẹp, có một tín hiệu hoặc cơ chế giám sát riêng như `CountDownLatch` ở `finally` của task.

### Lỗi 8 — dùng `lockInterruptibly()` nhưng mọi thread lấy nhiều khóa theo thứ tự đảo ngược

Thread có thể thoát vòng chờ khi bị interrupt, nhưng **deadlock vẫn có thể xảy ra** nếu không có interrupt hoặc nếu code không nhả khóa đã giữ. Quy định thứ tự lấy khóa nhất quán vẫn là nguyên tắc chính.

### Lỗi 9 — hủy giữa một cập nhật nhiều trường

Ngay cả khi finally nhả khóa đúng, dữ liệu có thể ở trạng thái không hợp lệ nếu một nửa giao dịch đã chạy. Cần hoàn tất hoặc rollback đơn vị cập nhật trước khi rời critical section.

## 17. Bài tập tự kiểm tra

**Câu 1.** Main giữ một `ReentrantLock`, worker gọi `lockInterruptibly()` và chờ. Main gọi `worker.interrupt()` nhưng chưa nhả lock. Worker có phải chờ đến khi main nhả lock không?

**Trả lời:** Không nhất thiết. Với `ReentrantLock.lockInterruptibly()`, interrupt làm worker ném `InterruptedException` và thoát bước chờ mà không cần lấy được lock. Worker phải rời task đúng cách; nó không được `unlock()` nếu chưa hề lấy lock.

**Câu 2.** Thay `lockInterruptibly()` bằng `lock()` trong tình huống trên. `interrupt()` có lập tức hủy việc chờ không?

**Trả lời:** Không. Với `ReentrantLock.lock()`, worker có thể tiếp tục đợi cho đến khi lấy được lock. Trạng thái interrupt được giữ/khôi phục để code tiếp theo có thể xử lý.

**Câu 3.** `lockInterruptibly()` có thể ném `InterruptedException` dù khóa hiện đang rảnh không?

**Trả lời:** Có. Nếu thread đã bị interrupted trước khi gọi, `ReentrantLock.lockInterruptibly()` có thể ưu tiên đáp ứng interrupt và ném exception thay vì lấy khóa.

**Câu 4.** Một worker đã lấy được lock và đang cập nhật ba trường liên quan. Main gửi interrupt. Lock có tự nhả và dữ liệu có tự rollback không?

**Trả lời:** Không. Interrupt là tín hiệu hợp tác. Worker phải xử lý ở điểm an toàn, hoàn thành/rollback cập nhật và thoát qua `finally` để nhả khóa.

**Câu 5.** `tryLock(100, TimeUnit.MILLISECONDS)` trả `false` có đồng nghĩa worker bị interrupt không?

**Trả lời:** Không. `false` nghĩa là không lấy được khóa trong thời hạn. Nếu thao tác bị interrupt khi chờ, phương thức có thể ném `InterruptedException`.

**Câu 6.** Vì sao `Future.cancel(true)` không phải bằng chứng chắc chắn task đã cleanup xong?

**Trả lời:** Việc đánh dấu Future canceled và gửi interrupt có thể xảy ra trước khi task thực sự dừng. Task có thể bỏ qua interrupt hoặc cần thời gian nhả tài nguyên; nên có cơ chế xác nhận cleanup nếu hợp đồng yêu cầu.

**Câu 7.** Một thread đã chiếm khóa A, rồi gọi `B.lockInterruptibly()` và bị ngắt. Phải nhả khóa nào?

**Trả lời:** Nó chưa có khóa B do lời gọi bị ngắt. Phải nhả khóa A đã lấy trong `finally`; không được gọi `B.unlock()` khi chưa chiếm được B.

**Câu 8.** Với `ReentrantLock` và `Condition`, `lockInterruptibly()` khác `condition.await()` ở đâu?

**Trả lời:** `lockInterruptibly()` chờ **lấy quyền sở hữu lock**. `await()` dùng khi caller **đã giữ lock**, rồi nhả lock tạm thời để chờ điều kiện và chiếm lại trước khi trở về theo hợp đồng. Cả hai có thể phản ứng với interrupt nhưng phục vụ các giai đoạn khác nhau.

**Câu 9.** Một ứng dụng luôn cần hủy nếu đợi lock quá 2 giây mà không có thread nào gọi `interrupt()`. Nên dùng `lockInterruptibly()` riêng lẻ hay `tryLock(2, TimeUnit.SECONDS)`?

**Trả lời:** Timed `tryLock` cung cấp timeout cần thiết, đồng thời vẫn có thể bị interrupt. `lockInterruptibly()` không tự hết thời hạn nếu không có yêu cầu ngắt.

## 18. Tóm tắt

`lockInterruptibly()` cho phép **hủy hợp tác ngay trong giai đoạn chờ lấy khóa**, nhờ đó phù hợp với task có vòng đời yêu cầu cancel, shutdown hoặc phản ứng với interrupt. Khác `lock()`, một thread đang chờ `ReentrantLock.lockInterruptibly()` có thể ném `InterruptedException` mà không cần đợi khóa được nhả.

Bốn quy tắc thực hành phải luôn đi cùng nhau:

1. **Chỉ gọi `unlock()` sau khi đã lấy được lock thành công.**
2. **Không nuốt `InterruptedException`**: propagate hoặc khôi phục cờ và thoát task.
3. **Không nhầm hủy khi đợi lock với hủy khi đang làm việc**: phần thân critical section vẫn phải kiểm tra tín hiệu ở điểm an toàn và giữ nguyên invariant.
4. **Chọn API theo chính sách chờ**: `lock()` nếu thực sự cần đợi không hủy tại acquisition, `lockInterruptibly()` nếu cần phản ứng với interrupt, `tryLock(timeout, unit)` nếu cần cả thời hạn và ngắt.

Khi kết hợp xử lý interrupt đúng, `try/finally`, giao thức khóa tránh deadlock và cơ chế quản lý task, ứng dụng Java có thể hủy công việc đang chờ tài nguyên mà không làm rò rỉ khóa hoặc phá hỏng dữ liệu dùng chung.
