# tryLock() và timeout khi tranh chấp khóa trong Java

## 1. Mục tiêu bài học

Khi nhiều thread cần truy cập cùng trạng thái, dùng `synchronized` hoặc `Lock` có thể bảo vệ critical section. Nhưng trong hệ thống chịu tải, **chờ khóa mãi** không luôn là lựa chọn phù hợp: người gọi có thể muốn thử một lần, chờ tối đa một khoảng thời gian, từ chối sớm hoặc chuyển sang tác vụ khác.

`ReentrantLock` cung cấp hai phương thức quan trọng:

~~~java
boolean acquired = lock.tryLock();                 // thử ngay, không chờ
boolean acquired = lock.tryLock(200, TimeUnit.MILLISECONDS);
// chờ lấy khóa tối đa một khoảng cho trước, có thể bị interrupt
~~~

Sau bài này, bạn có thể:

- Phân biệt `lock()`, `lockInterruptibly()`, `tryLock()` và `tryLock(long, TimeUnit)` theo khả năng chờ, timeout, interrupt và kết quả.
- Xác định đúng thread nào đang sở hữu `ReentrantLock`; chỉ `unlock()` sau khi chính thread đó đã lấy khóa thành công.
- Giải thích chính xác khi nào timed tryLock trả `true`, `false` hoặc ném `InterruptedException`; tránh nhầm timeout lấy khóa với timeout toàn bộ nghiệp vụ.
- Thiết kế một nhánh fallback có chủ đích khi lock đang bận, thay vì bỏ qua công việc quan trọng một cách âm thầm.
- Hiểu sự khác biệt giữa fair lock và non-fair lock, đặc biệt việc `tryLock()` **không tôn trọng fairness setting**.
- Sử dụng giới hạn thời gian, deadline, cancellation và logging/metric phù hợp; tránh lỗi deadlock, double unlock và mất interrupt.
- Chạy chương trình Java 17+ tái hiện cạnh tranh khóa **xác định**, không phụ thuộc vào việc đoán lịch chạy bằng `sleep()`.

**Phạm vi:** Java SE, `java.util.concurrent.locks` và Java Memory Model. Các ví dụ độc lập với thư viện bên ngoài, dùng Java 17 trở lên.

## 2. ReentrantLock và quyền sở hữu khóa

`ReentrantLock` là mutual exclusion lock: một thời điểm chỉ **một thread** sở hữu lock. Khi thread đã giữ lock, cùng thread đó có thể lấy lại khóa theo tính **reentrant**, và mỗi lần lấy thêm phải được cân bằng bằng lần nhả tương ứng.

~~~java
import java.util.concurrent.locks.ReentrantLock;

class Counter {
    private final ReentrantLock lock = new ReentrantLock();
    private int value;

    void increment() {
        lock.lock();
        try {
            value++;
        } finally {
            lock.unlock();
        }
    }

    int get() {
        lock.lock();
        try {
            return value;
        } finally {
            lock.unlock();
        }
    }
}
~~~

Đây là class Java hợp lệ nhưng chưa có `main`, minh họa giao thức: **mọi đường đọc/ghi biến value cùng dùng một lock**. Khi một thread khóa thành công và thoát với `unlock()`, thao tác của thread đó có memory synchronization effect tương đương thành công của monitor unlock; thread khác thành công khi acquire cùng lock có quan hệ visibility/ordering theo hợp đồng `Lock` và JMM.

Khác `synchronized`, `ReentrantLock` **không tự nhả** khi method kết thúc. Nếu quên `unlock()`, thread khác có thể đợi vô hạn. Vì thế phải luôn đặt việc nhả khóa trong `finally`, với điều kiện thread hiện tại thực sự sở hữu khóa.

`tryLock` **không đồng nghĩa chỉ đọc trạng thái lock**: khi trả `true`, nó đã **acquire** lock và tạo trách nhiệm `unlock()`. Khi trả `false`, caller **không nhận thêm quyền sở hữu** lock.

## 3. Bốn hình thức lấy khóa cần phân biệt

| API | Chờ khi khóa do thread khác giữ? | Interrupt khi đang đợi | Hợp đồng kết quả |
|---|---|---|---|
| `lock()` | Chờ cho đến khi có thể lấy | Không ném `InterruptedException` trong lúc chờ | Trả về `void` sau khi lấy được. |
| `lockInterruptibly()` | Chờ, nhưng có thể hủy bằng interrupt | Ném `InterruptedException` (nếu bị interrupt theo hợp đồng) | `void` khi lấy được, exception khi bị ngắt. |
| `tryLock()` | **Không chờ** | Không có pha đợi interruptible; không ném `InterruptedException` | `true` nếu lấy được ngay, `false` nếu thread khác đang giữ. |
| `tryLock(timeout, unit)` | Chờ tối đa khoảng yêu cầu nếu cần | **Có**, ném `InterruptedException` | `true` nếu lấy được; `false` nếu hết thời gian trước khi lấy; exception nếu bị interrupt. |

Điểm cần nắm: mọi API trên đều có thể thành công **ngay khi khóa đang rảnh**; `tryLock` không có nghĩa “đợi rồi có thể bỏ cuộc” trong mọi trường hợp, vì overload không tham số **không đợi**.

### Sơ đồ của timed tryLock

~~~text
             gọi tryLock(timeout, unit)
                         |
          đã bị interrupt tại entry?
                  /               \
               có                 không
               |                   |
      InterruptedException     khóa có thể acquire?
                                   /        \
                                 có          chưa
                                 |            |
                              true       đợi tối đa
                              |          thời gian
                       vào critical       |
                           section      ┌─┴───────────┐
                           /            |             |
                        unlock()     acquire         interrupt
                                       |             |
                                      true         exception
                                                   |
                                               hết hạn trước
                                                   |
                                                 false
~~~

Đây là sơ đồ logic cho điều kiện và kết quả, **không quy định scheduler phải đánh thức hoặc hoàn tất tác vụ đúng tại mốc thời gian**. Khi chờ, nhiều sự kiện có thể đến gần như đồng thời. `ReentrantLock` ưu tiên phản hồi interrupt theo contract, nên ứng dụng phải xử lý nhánh đó độc lập với timeout.

## 4. tryLock(): thử một lần, phản hồi ngay

Đối với `ReentrantLock`, `tryLock()`:

1. Nếu lock chưa bị thread khác giữ, acquire ngay rồi trả `true`.
2. Nếu **thread hiện tại đã sở hữu lock**, acquire reentrantly, tăng hold count rồi trả `true`.
3. Nếu thread khác đang giữ lock, trả `false` **ngay**, không đăng ký chờ lock được nhả.
4. Không khai báo `throws InterruptedException` và không cung cấp cơ chế đợi có thể hủy bằng interrupt.

Mẫu chuẩn:

~~~java
import java.util.concurrent.locks.ReentrantLock;

class NonBlockingCounter {
    private final ReentrantLock lock = new ReentrantLock();
    private int count;

    boolean tryIncrement() {
        if (!lock.tryLock()) {
            return false; // bận: caller quyết định bỏ qua, thử lại hoặc báo lỗi
        }
        try {
            count++;
            return true;
        } finally {
            lock.unlock();
        }
    }
}
~~~

**Điều kiện nghiệp vụ phải rõ:** `false` ở đây biểu thị “không nhận lock ngay”, **không** nhất thiết là “tác vụ thất bại vĩnh viễn”. Nếu counter ghi nhận giao dịch bắt buộc, im lặng bỏ qua lần tăng có thể làm **mất dữ liệu nghiệp vụ**. Caller cần quyết định queue, retry có giới hạn, trả trạng thái quá tải hoặc cơ chế đáng tin cậy khác.

### Tại sao kiểm tra isLocked() rồi lock() là sai?

~~~java
if (!lock.isLocked()) {
    lock.lock(); // vẫn có thể bị chờ!
    try {
        doWork();
    } finally {
        lock.unlock();
    }
}
~~~

`isLocked()` chỉ trả một quan sát nhất thời, không reserve khóa. Thread khác có thể acquire giữa `isLocked()` và `lock()`: một lỗi **check-then-act**. `tryLock()` gộp “kiểm tra khả dụng + acquire” thành **một thao tác nguyên tử theo hợp đồng lock**. Các phương thức `isLocked()`, `hasQueuedThreads()`, `getQueueLength()` thích hợp hơn cho quan sát/monitoring, không dùng để quyết định chắc chắn thread tiếp theo có lấy được lock.

## 5. Ví dụ chạy độc lập 1: một thread đang giữ lock

Chương trình này dàn dựng đúng tình huống: main giữ lock, thread khác thử lấy lock. Vì main chỉ nhả sau khi thread kia hoàn tất, kết quả `tryLock() = false` không phụ thuộc lịch chạy.

Lưu tệp **ImmediateTryLockDemo.java**:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.locks.ReentrantLock;

public class ImmediateTryLockDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        AtomicBoolean acquiredByWorker = new AtomicBoolean(true);

        lock.lock(); // main sở hữu lock
        try {
            Thread worker = new Thread(() -> {
                boolean acquired = lock.tryLock();
                acquiredByWorker.set(acquired);
                if (acquired) {
                    try {
                        // Có thể xử lý shared state ở đây.
                    } finally {
                        lock.unlock();
                    }
                }
            }, "worker");

            worker.start();
            worker.join(); // main vẫn giữ lock trong lúc worker thử
            System.out.println("whileMainHolds=" + acquiredByWorker.get());
        } finally {
            lock.unlock(); // main nhả quyền sở hữu của chính mình
        }

        boolean acquiredAfterRelease = lock.tryLock();
        try {
            System.out.println("afterRelease=" + acquiredAfterRelease);
        } finally {
            if (acquiredAfterRelease) {
                lock.unlock();
            }
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac ImmediateTryLockDemo.java
java ImmediateTryLockDemo
~~~

Kết quả:

~~~text
whileMainHolds=false
afterRelease=true
~~~

**Giải thích:**

- main gọi `lock.lock()` và giữ lock trong khối `try`.
- worker là thread khác, nên `worker.tryLock()` phải trả `false` khi main chưa unlock.
- `worker.join()` hoàn tất trước khi main đi vào `finally` nhả lock, loại bỏ khả năng worker được chạy sau thời điểm nhả.
- Sau khi nhả lock, main thử lại và thành công, vì không có contender khác. `AtomicBoolean` được dùng lưu kết quả worker; kết quả cũng được quan sát sau `join()`. `AtomicBoolean` không phải cơ chế sửa quyền sở hữu khóa.
- Ví dụ cố ý không dùng `sleep()` hay suy đoán thread sẽ chạy trước/sau theo thời gian thực.

Cách viết `try/finally` sau lần `tryLock()` thành công cần được giữ đúng trong code sản xuất. Trường hợp `false` không được phép gọi `unlock()` nếu thread không nắm quyền sở hữu.

## 6. tryLock(long timeout, TimeUnit unit): chờ có giới hạn

Overload có thời gian:

~~~java
boolean acquired =
        lock.tryLock(150, TimeUnit.MILLISECONDS);
~~~

Các tính chất quan trọng:

- `timeout` là một khoảng chờ **để lấy khóa**, không phải deadline toàn bộ công việc sau khi đã lấy.
- Nếu lock rảnh và không có rào cản như fairness queue, phương thức có thể trả `true` ngay.
- Nếu thread khác giữ lock, caller có thể đợi **tối đa khoảng yêu cầu** theo cơ chế của lock; nếu không acquire được trước khi hết hạn, trả `false`.
- Nếu thread đang bị interrupt khi vào hoặc bị interrupt trong lúc cố acquire, `ReentrantLock` ném `InterruptedException` và **xóa interrupted status tại thời điểm ném**.
- Với `timeout <= 0`, phương thức không đợi. Đây vẫn là overload có ngữ nghĩa kiểm tra interrupt; trên fair lock còn tôn trọng fairness.
- `TimeUnit` phải khác `null`; dùng `null` sẽ dẫn đến `NullPointerException`.
- Giá trị trả về không quy định tổng thời gian thực tế method caller hoàn tất. Scheduling, GC pause và phần xử lý sau acquire có thể làm độ trễ tổng khác mốc timeout.

Mẫu dùng điển hình:

~~~java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

class BoundedCounter {
    private final ReentrantLock lock = new ReentrantLock();
    private int count;

    boolean tryIncrement(long timeout, TimeUnit unit)
            throws InterruptedException {
        if (!lock.tryLock(timeout, unit)) {
            return false;
        }
        try {
            count++;
            return true;
        } finally {
            lock.unlock();
        }
    }
}
~~~

**Lưu ý:** Đây là method hợp lệ của class nhưng chưa có `main`. Caller phải quyết định ý nghĩa của `false`. Thread có thể không lấy được lock vì contention chứ không phải dữ liệu được bảo vệ không hợp lệ. Tăng `timeout` có thể giảm số lần trả `false` nhưng tăng tail latency, số thread đang chờ và áp lực tài nguyên.

## 7. Ví dụ chạy độc lập 2: timeout được xác định bằng ownership

Ví dụ sau không dựa vào may rủi thread nào chạy trước. Main giữ lock cho tới khi worker kết thúc timed tryLock. Worker không thể lấy lock và phải trả `false` khi hết thời gian chờ.

Lưu tệp **TimedTryLockDemo.java**:

~~~java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.locks.ReentrantLock;

public class TimedTryLockDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        AtomicReference<String> result = new AtomicReference<>();

        lock.lock();
        try {
            Thread waiter = new Thread(() -> {
                try {
                    boolean acquired =
                            lock.tryLock(40, TimeUnit.MILLISECONDS);
                    if (!acquired) {
                        result.set("timeout");
                        return;
                    }
                    try {
                        result.set("acquired");
                    } finally {
                        lock.unlock();
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    result.set("interrupted");
                }
            }, "timed-waiter");

            waiter.start();
            waiter.join(); // khóa vẫn do main giữ khi waiter timeout
        } finally {
            lock.unlock();
        }

        System.out.println("result=" + result.get());
    }
}
~~~

Chạy:

~~~bash
javac TimedTryLockDemo.java
java TimedTryLockDemo
~~~

Output khi không bị interrupt ngoài:

~~~text
result=timeout
~~~

**Đối chiếu:**
- Main lấy lock đầu tiên, chỉ nhả trong `finally` sau khi đã `join()` worker.
- Worker không thể acquire khi main sở hữu; sau khoảng chờ nó nhận `false`, set `"timeout"` và thoát.
- Worker không gọi `unlock()` nếu nhận `false`.
- Khi worker kết thúc, main nhả khóa của mình và mới in. Dù scheduler chậm hơn 40ms hay gây thêm delay, kết quả logic vẫn là timeout trong điều kiện thực thi bình thường.
- Đây là phép thử **behavior**. Không được suy luận rằng method luôn trả sau đúng 40ms trên mọi hệ điều hành hoặc JVM.

## 8. Interrupt không phải timeout

Timed `tryLock` **interruptible**. Một thread đang chờ có thể bị hủy bởi `Thread.interrupt()`. Theo `ReentrantLock`, nếu bị interrupt khi vào method hoặc trong lúc đợi, nó ném `InterruptedException`. Đây **không phải** kết quả `false`, và code không nên xử lý như một timeout thông thường.

Mẫu xử lý trong một `Runnable`:

~~~java
try {
    if (!lock.tryLock(500, TimeUnit.MILLISECONDS)) {
        handleContentionTimeout();
        return;
    }
    try {
        performProtectedWork();
    } finally {
        lock.unlock();
    }
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Dừng hoặc chuyển thông tin hủy lên tầng gọi.
}
~~~

Đây là **đoạn trích minh họa**, trong đó các method `handleContentionTimeout()` và `performProtectedWork()` do ứng dụng định nghĩa. Khi có thể khai báo `throws InterruptedException` và caller xử lý, cũng có thể truyền exception lên trên.

Tại sao thường khôi phục cờ? `InterruptedException` thường **xóa interrupted status** khi ném. Nếu code bắt mà không truyền tiếp, `Thread.currentThread().interrupt()` giúp tầng trên nhận biết yêu cầu hủy. Điều này không có nghĩa mọi nghiệp vụ đều phải tiếp tục chạy sau khi khôi phục; nên kết thúc hoặc làm theo hợp đồng task.

### Ví dụ chạy độc lập 3: interrupt khi một thread đang tranh khóa

Lưu **InterruptibleTryLockDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.locks.ReentrantLock;

public class InterruptibleTryLockDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        CountDownLatch ready = new CountDownLatch(1);
        AtomicReference<String> outcome = new AtomicReference<>();

        lock.lock();
        try {
            Thread waiter = new Thread(() -> {
                ready.countDown();
                try {
                    if (lock.tryLock(10, TimeUnit.SECONDS)) {
                        try {
                            outcome.set("acquired");
                        } finally {
                            lock.unlock();
                        }
                    } else {
                        outcome.set("timeout");
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    outcome.set("interrupted");
                }
            }, "interruptible-waiter");

            waiter.start();
            ready.await();
            waiter.interrupt();
            waiter.join();
        } finally {
            lock.unlock();
        }

        System.out.println("result=" + outcome.get());
    }
}
~~~

Chạy:

~~~bash
javac InterruptibleTryLockDemo.java
java InterruptibleTryLockDemo
~~~

Output trong điều kiện không có tác động hủy phụ khác:

~~~text
result=interrupted
~~~

Giải thích kết quả:
- Main giữ lock cho đến khi waiter kết thúc. Waiter không thể acquire sớm.
- `ready` bảo đảm worker đã chạy ít nhất tới câu lệnh phát tín hiệu. Main gọi interrupt ngay sau đó; kể cả nếu tín hiệu interrupt đến **trước** lời gọi tryLock timed, overload timed vẫn phát hiện trạng thái interrupt và ném `InterruptedException`.
- Catch khôi phục cờ; kết quả `"interrupted"` được ghi rồi main `join()` quan sát.
- Thử nghiệm không cần đoán sleep bao lâu. Nó phân biệt nhánh hủy với hết thời gian chờ.
- Trong ứng dụng thật, một yêu cầu hủy không nên bị chuyển thành retry vô hạn; phải đi theo lifecycle của task.

## 9. Quyền sở hữu, try/finally và lỗi unlock sai

Mẫu chuẩn, khi timed tryLock có thể ném exception:

~~~java
boolean acquired = false;
try {
    acquired = lock.tryLock(timeout, unit);
    if (!acquired) {
        return;
    }

    // Chỉ thread đã acquire mới được thay đổi shared state.
    updateSharedState();
} finally {
    if (acquired) {
        lock.unlock();
    }
}
~~~

Đây là **đoạn trích trong một method** có thể ném `InterruptedException`; `timeout`, `unit` và `updateSharedState()` đến từ caller. Cách khác là kiểm tra kết quả trước, rồi đưa `try/finally` **bên trong nhánh true**, như các ví dụ ở trên. Cả hai bảo đảm không unlock khi không sở hữu.

### Không làm thế này

~~~java
try {
    if (lock.tryLock()) {
        useSharedState();
    }
} finally {
    lock.unlock(); // SAI nếu tryLock() trả false
}
~~~

Nếu thread không giữ lock, `ReentrantLock.unlock()` ném `IllegalMonitorStateException`; nó **không giải phóng** lock của thread khác. Đó là dấu hiệu vi phạm ownership contract, không phải “đảm bảo dọn dẹp”.

Các bẫy liên quan:
- `tryLock() == true` tạo quyền sở hữu cho **thread hiện tại**. Không trao quyền `unlock()` cho thread khác, kể cả thread đó có cùng reference đến `ReentrantLock`.
- Lock reentrant: cùng thread gọi `tryLock()` hai lần thành công thì phải cân bằng **hai lần** `unlock()`. Một lần unlock chỉ giảm hold count.
- Không bỏ quên `unlock()` khi code trong critical section ném exception.
- Không dùng `synchronized(lock)` thay cho `lock.lock()` rồi gọi `lock.unlock()`; intrinsic monitor của object Lock và giao thức Lock API là **hai loại khóa khác nhau**.
- `isHeldByCurrentThread()` và `getHoldCount()` hữu ích để kiểm tra/chẩn đoán, không nên tạo protocol “thử đoán ownership” thay vì giữ boolean từ lời gọi acquire.

## 10. Timeout có ý nghĩa chính xác đến đâu?

Giả sử caller đặt:

~~~java
lock.tryLock(100, TimeUnit.MILLISECONDS)
~~~

Mốc 100ms chỉ giới hạn **pha cố acquire lock**, **không** có nghĩa:

- Toàn bộ thao tác nghiệp vụ phải xong trong 100ms.
- Caller chắc chắn được scheduler chạy đúng lúc để quan sát deadline.
- Chủ lock sẽ bị cưỡng bức nhả khi có waiter timeout.
- Tác vụ vừa giữ lock vừa làm I/O dài sẽ tự bị cắt ngắn.
- Không còn ai cạnh tranh sau khi caller nhận `true`.
- `false` luôn có nghĩa hệ thống hỏng; có thể chỉ là chính sách từ chối có chủ đích.

Nếu cần kiểm soát **end-to-end deadline**, phải truyền ngân sách thời gian từ điểm bắt đầu nghiệp vụ qua các bước: đợi lock, gọi tài nguyên ngoài, chờ queue, retry. Với thời lượng đo trong JVM, `System.nanoTime()` thích hợp để tính **elapsed duration**; không dùng `System.currentTimeMillis()` làm đồng hồ monotonic cho deadline vì đồng hồ tường có thể thay đổi.

### Ví dụ chia sẻ một time budget

~~~java
long startedAt = System.nanoTime();
long budgetNanos = TimeUnit.MILLISECONDS.toNanos(500);

// Bước một diễn ra trước khi thử khóa.
prepareInput();

long elapsed = System.nanoTime() - startedAt;
long remaining = Math.max(0L, budgetNanos - elapsed);

if (!lock.tryLock(remaining, TimeUnit.NANOSECONDS)) {
    throw new IllegalStateException("lock unavailable within budget");
}
try {
    applyPreparedInput();
} finally {
    lock.unlock();
}
~~~

Đây là **đoạn trích minh họa**, các method và lock thuộc context ứng dụng. Nó trừ thời gian `prepareInput()` khỏi ngân sách đợi lock, **nhưng chưa giới hạn thời gian `applyPreparedInput()`**. Hợp đồng thực tế phải đặt deadline riêng hoặc truyền remaining budget đến những bước có khả năng block.

Với nghiệp vụ dài, chú ý tràn số khi cộng deadline nanos hoặc chuyển đổi đơn vị quá lớn. Khi cần so sánh elapsed, pattern trừ từ `System.nanoTime()` và thời lượng trong khoảng hỗ trợ thường dễ đúng hơn cộng timestamp tuyệt đối.

## 11. Fair lock: tryLock() có thể “chen hàng”

Khởi tạo `ReentrantLock`:

~~~java
ReentrantLock defaultLock = new ReentrantLock();      // non-fair
ReentrantLock fairLock = new ReentrantLock(true);     // fair
~~~

Fairness setting làm thay đổi chính sách ưu tiên các thread đang chờ khi tranh lock, nhưng:

**Quan trọng:** `fairLock.tryLock()` **vẫn có thể lấy lock ngay khi nó rảnh, dù các thread khác đã xếp hàng**. Đây là hành vi *barging* được JDK ghi rõ. Điều đó không đồng nghĩa chương trình sai; nhưng bạn không thể dùng `tryLock()` rồi khẳng định mọi thread tuân FIFO.

Ngược lại, `fairLock.tryLock(timeout, unit)` **tôn trọng fairness setting** khi có những waiter khác đang chờ. Nếu cần hành vi thử ngay gần tương đương nhưng vẫn tôn trọng fairness và kiểm tra interrupt, có thể dùng:

~~~java
boolean acquired = fairLock.tryLock(0, TimeUnit.SECONDS);
~~~

Vẫn phải xử lý `InterruptedException`. Nếu cùng thread đã sở hữu lock, việc reentrant acquisition là trường hợp riêng, không cần xếp hàng sau các thread khác.

### Có nên luôn tạo fair lock?

Không. Fairness của lock **không bảo đảm fairness của thread scheduling** và không cam kết deadline cho từng task. Fair lock có thể giảm biến động thời gian chờ trong một số tải nhưng thường có throughput thấp hơn vì ít cho phép barging; chi phí thực tế phụ thuộc workload. Không chọn `new ReentrantLock(true)` chỉ vì tên nghe “công bằng”.

Chọn policy theo yêu cầu:
- Nếu fairness là invariant quan trọng, đánh giá fair lock và sử dụng những API acquire tôn trọng fairness.
- Nếu cần throughput cao và việc chen hàng chấp nhận được, non-fair lock mặc định có thể phù hợp.
- Nếu yêu cầu latency deadline nghiêm ngặt, fairness một mình không đủ; còn phải giới hạn contention, thời gian giữ lock và các nguồn blocking khác.

## 12. Tránh deadlock khi cần nhiều khóa

Khi thao tác cần giữ hai lock A và B, deadlock có thể xuất hiện:

~~~text
Thread T1: giữ A ── chờ B
Thread T2: giữ B ── chờ A

Hai bên chờ vô hạn nếu dùng lock() và không có đường giải phóng.
~~~

Timed tryLock cho phép **bỏ cuộc và nhả những khóa đã giữ**, nhưng chỉ khi code viết đúng finally. Nó không tự động làm thuật toán miễn deadlock nếu một bước khác vẫn chờ vô hạn hoặc nếu caller luôn retry theo cách gây livelock.

Mẫu minh họa lấy hai lock với các bounded attempts:

~~~java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

class TwoResources {
    private final ReentrantLock first = new ReentrantLock();
    private final ReentrantLock second = new ReentrantLock();

    boolean tryUseBoth(long timeout, TimeUnit unit)
            throws InterruptedException {
        long budgetNanos = unit.toNanos(timeout);
        long startedAt = System.nanoTime();

        if (!first.tryLock(budgetNanos, TimeUnit.NANOSECONDS)) {
            return false;
        }
        try {
            long elapsed = System.nanoTime() - startedAt;
            long left = Math.max(0L, budgetNanos - elapsed);
            if (!second.tryLock(left, TimeUnit.NANOSECONDS)) {
                return false;
            }
            try {
                // Thao tác trên cả hai resource dưới đúng hai lock.
                return true;
            } finally {
                second.unlock();
            }
        } finally {
            first.unlock();
        }
    }
}
~~~

Đây là class minh họa, chưa có main và không có tài nguyên thật. Tại sao nó an toàn về **quyền sở hữu**?
1. Nếu không lấy được first, trả false ngay, không unlock first.
2. Sau khi first thành công, mọi đường đi khỏi outer try đều unlock first.
3. Nếu second không lấy được trong ngân sách còn lại, trả false nhưng vẫn nhả first qua outer finally.
4. Chỉ khi second thành công mới được vào nested try và finally nhả second.
5. Nếu bị interrupt trong khi chờ second, exception đi ra và outer finally nhả first.

**Giới hạn:** Nếu các thread khác không tuân theo cùng lock protocol, invariant vẫn có thể hỏng. Nếu có nhiều đường lấy A/B theo thứ tự khác nhau, cần lock ordering hoặc thiết kế có timeout/retry phù hợp. Việc retry quá tích cực giữa hai thread có thể tạo **livelock**, nên khi cần thử lại hãy giới hạn số lần/thời gian và cân nhắc backoff có kiểm soát. Với các phép tính phải kết thúc trong budget, tiếp tục kiểm soát thời gian critical section sau khi acquire.

## 13. Timeout khác Condition.await và timeout của Future

Các khoảng đợi có thể cùng dùng `TimeUnit` nhưng **bảo vệ những vấn đề khác nhau**:

| Lời gọi | Chờ điều gì? | Khi timeout |
|---|---|---|
| `lock.tryLock(t, unit)` | Quyền sở hữu lock | Trả `false` nếu không acquire được. |
| `condition.await(t, unit)` | Tín hiệu/điều kiện trong khi phối hợp qua lock | Trả boolean theo hợp đồng await; phải **kiểm tra lại predicate** khi tỉnh. |
| `future.get(t, unit)` | Task hoàn tất và có kết quả | Ném `TimeoutException` nếu chưa hoàn tất trong hạn. |
| `semaphore.tryAcquire(t, unit)` | Permit từ semaphore | Trả `false` khi không có permit trong hạn. |

Không nhầm thời gian chờ acquire lock với thời gian chờ một predicate đúng. Dùng `Condition` khi thread cần chờ **trạng thái được bảo vệ bởi lock** thay đổi; `Condition.await` được thiết kế nhả lock trong lúc đợi và acquire lại trước khi return. Đừng dùng vòng gọi `tryLock()` liên tục để mô phỏng một queue có condition, vì dễ gây CPU spinning hoặc starvation.

## 14. Tranh chấp khóa và thiết kế fallback

`tryLock()` và timed `tryLock` hữu ích khi ứng dụng có hành vi rõ ràng trong ba trường hợp:

1. **Đã lấy khóa:** thao tác trạng thái chung trong critical section rồi nhả khóa.
2. **Hết thời gian mà không lấy được:** trả mã bận, thử lại có giới hạn, chuyển sang queue hoặc báo một kết quả có ý nghĩa nghiệp vụ.
3. **Bị interrupt:** dừng hoặc truyền cancellation signal; tuyệt đối không biến request bị hủy thành retry vô hạn.

Ví dụ API nghiệp vụ không gộp hết các lỗi vào `false`:

~~~java
enum ReserveResult {
    RESERVED, NOT_ENOUGH, LOCK_BUSY
}
~~~

Đặt kết quả nghiệp vụ (`NOT_ENOUGH`) khác contention (`LOCK_BUSY`). Một lần acquire thành công vẫn có thể gặp dữ liệu không đáp ứng điều kiện. Khi không phân biệt hai trường hợp, caller khó quyết định retry nên hay không.

### Ví dụ class hoàn chỉnh: reserve dưới lock với timeout

~~~java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public final class InventoryCounter {
    public enum Result {
        RESERVED, NOT_ENOUGH, LOCK_BUSY
    }

    private final ReentrantLock lock = new ReentrantLock();
    private int available;

    public InventoryCounter(int initial) {
        if (initial < 0) {
            throw new IllegalArgumentException("negative initial stock");
        }
        available = initial;
    }

    public Result reserve(int amount, long timeout, TimeUnit unit)
            throws InterruptedException {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }

        if (!lock.tryLock(timeout, unit)) {
            return Result.LOCK_BUSY;
        }

        try {
            if (available < amount) {
                return Result.NOT_ENOUGH;
            }
            available -= amount;
            return Result.RESERVED;
        } finally {
            lock.unlock();
        }
    }

    public int available() {
        lock.lock();
        try {
            return available;
        } finally {
            lock.unlock();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        InventoryCounter inventory = new InventoryCounter(5);

        System.out.println(inventory.reserve(
                2, 100, TimeUnit.MILLISECONDS));
        System.out.println(inventory.reserve(
                4, 100, TimeUnit.MILLISECONDS));
        System.out.println("available=" + inventory.available());
    }
}
~~~

Tệp: **InventoryCounter.java**, chạy:

~~~bash
javac InventoryCounter.java
java InventoryCounter
~~~

Output khi main chạy tuần tự, không bị interrupt ngoài:

~~~text
RESERVED
NOT_ENOUGH
available=3
~~~

Giải thích:
- Lần đầu reserve(2) được lock và giảm 5 xuống 3.
- Lần sau reserve(4) vẫn lấy được lock nhưng không đủ hàng; phương thức trả `NOT_ENOUGH` và **không** làm giảm available.
- `LOCK_BUSY` chỉ xảy ra khi contention khiến không acquire được trong thời gian yêu cầu.
- Điều kiện kiểm tra `available < amount` và phép giảm đều nằm trong cùng critical section nên không có check–then–act race giữa các caller tuân thủ cùng protocol.
- Đây là state **trong một JVM**. Nếu nguồn hàng do nhiều tiến trình hoặc hệ thống ngoài cùng cập nhật, `ReentrantLock` của một process không đủ làm giao dịch phân tán.

### Khi fallback là retry

Retry cần một ngân sách tổng và điều kiện dừng. Đừng gọi lặp `tryLock()` không ngừng trong vòng while để “đợi tới khi có khóa”: đó là busy spin và có thể đốt CPU. Nếu yêu cầu chờ, dùng overload timed hoặc `lockInterruptibly()`. Nếu retry vì contention, dùng hạn mức thời gian, số lần thử, backoff và khả năng cancel. Chú ý rằng retry toàn bộ nghiệp vụ có thể không idempotent nếu một bước bên ngoài critical section đã tạo side effect.

## 15. Reentrant acquisition và hold count

Tên `ReentrantLock` cho biết thread đang sở hữu lock có thể acquire nó lần nữa:

~~~java
ReentrantLock lock = new ReentrantLock();

lock.lock();                  // hold count = 1
try {
    boolean second = lock.tryLock(); // true; hold count = 2
    try {
        System.out.println(second);  // true
        System.out.println(lock.getHoldCount()); // 2
    } finally {
        lock.unlock();        // hold count = 1
    }
} finally {
    lock.unlock();            // hold count = 0; lock được nhả
}
~~~

Đây là đoạn mã minh họa đặt trong một method/khối hợp lệ. Nếu main thực thi mà không có contender khác, các dòng in là `true` và `2`. Nó nhấn mạnh rằng `tryLock()` **không trả false chỉ vì isLocked()==true**: nếu thread hiện tại là owner, acquire lại được.

`getHoldCount()` biểu thị số lần thread **hiện tại** đang giữ lock, không phải tổng số thread đang đợi. Nếu quên một lần unlock khi acquire reentrantly, lock sẽ vẫn bị giữ dù code đã rời một tầng gọi; các worker khác có thể bị chặn.

## 16. Quan sát contention đúng cách

Khi không lấy được lock, thay vì tăng timeout tùy tiện, hãy đo:

- **Lock acquisition wait time:** thời gian từ bắt đầu tryLock đến thành công hoặc timeout.
- **Timeout ratio:** bao nhiêu request nhận `false` so với tổng attempts; phân tách theo operation.
- **Critical-section duration:** lock được giữ trong bao lâu; có I/O/slow callback trong lock không.
- **Interrupt/cancellation:** bao nhiêu yêu cầu đợi lock bị hủy, có khôi phục/lan truyền tín hiệu đúng không.
- **Throughput và tail latency:** số nghiệp vụ hoàn tất và các phân vị p95/p99.
- **Thread state/CPU:** `WAITING`, `TIMED_WAITING`, `BLOCKED`, CPU saturation, GC pauses.
- **Invariants:** dữ liệu có chính xác không sau timeout/retry, có bỏ sót nghiệp vụ hoặc xử lý trùng không.

`ReentrantLock.getQueueLength()` chỉ trả **ước lượng** số thread có thể đang đợi acquire; `hasQueuedThreads()` cũng là thông tin quan sát dễ thay đổi. Không dùng chúng như phép kiểm tra atomic để quyết định chắc chắn rằng việc acquire tiếp theo sẽ thành công.

Java Flight Recorder (JFR) có thể giúp nghiên cứu contention; Java thread dumps giúp xem call stack và trạng thái. Khả năng hiển thị chi tiết `java.util.concurrent.locks` tùy JDK/công cụ. Không suy luận lock đã được giải phóng chỉ vì thread dump không ghi một thread đang chờ tại thời điểm chụp.

## 17. Lỗi phổ biến cần nhận diện

**Lỗi 1 — unlock khi tryLock trả false.** Thread không sở hữu lock; `IllegalMonitorStateException` có thể xuất hiện. Chỉ unlock sau acquire thành công.

**Lỗi 2 — Không đặt unlock trong finally.** Exception hoặc return sớm có thể giữ lock mãi, gây treo các thread khác.

**Lỗi 3 — Xem timeout lấy lock là timeout nghiệp vụ.** Sau khi acquire, code trong critical section vẫn có thể chạy/đợi rất lâu. Dùng deadline xuyên suốt nếu yêu cầu độ trễ toàn end-to-end.

**Lỗi 4 — Đánh đồng timeout với interrupt.** Timed overload ném `InterruptedException` khi bị hủy; `false` là kết quả không lấy được khóa trong khoảng chờ. Chính sách xử lý khác nhau.

**Lỗi 5 — Bỏ mất interrupt.** Catch rồi retry mãi làm request khó hủy. Truyền exception lên hoặc khôi phục cờ và thoát theo lifecycle.

**Lỗi 6 — Dùng isLocked() trước lock().** Check và acquire không phải một thao tác atomic. Dùng tryLock.

**Lỗi 7 — Cho rằng tryLock() tuân thủ fairness.** Trên fair ReentrantLock, untimed tryLock vẫn có thể barging. Dùng timed form theo yêu cầu fairness.

**Lỗi 8 — Lặp tryLock() không nghỉ.** Busy spin có thể tiêu tốn CPU và gây contention thêm; ưu tiên chờ có giới hạn hoặc có backoff.

**Lỗi 9 — Khóa không cùng identity.** Mỗi thread giữ một ReentrantLock instance khác nhau sẽ không đồng bộ trên cùng state. Đưa lock chung vào đúng object sở hữu state.

**Lỗi 10 — Dùng synchronized(lock) cùng với lock.lock().** Hai cơ chế không có ràng buộc thay thế nhau; chúng acquire **hai khóa khác nhau về ngữ nghĩa**.

**Lỗi 11 — Nhả khóa từ thread khác.** Lock ownership theo thread. Không chuyển trách nhiệm unlock sang callback chạy ở worker khác.

**Lỗi 12 — Thử nhiều khóa theo thứ tự trái ngược rồi quên nhả khóa đầu khi khóa thứ hai timeout.** Cần nested try/finally và chính sách lock order/retry rõ ràng.

**Lỗi 13 — Cho rằng tryLock tự bảo vệ mọi dữ liệu.** Chỉ các thao tác tuân thủ cùng lock protocol mới có mutual exclusion. Đường đọc/ghi không dùng lock có thể làm sai invariant.

**Lỗi 14 — Dùng timeouts làm giải pháp duy nhất cho overload.** Timeout làm người gọi ngừng chờ nhưng không giải quyết nguyên nhân contention; xem critical section quá dài, queue, CPU/IO và tải admission.

## 18. Checklist chọn API

~~~text
Có shared mutable state cần exclusive access?
  |
  +-- Không --> tránh lock nếu trạng thái thực sự độc lập/immutable
  |
  +-- Có
       |
       +-- Có thể chờ cho đến khi lấy được?
       |      |
       |      +-- Có, không cần interrupt trong pha đợi
       |      |       → lock() + finally unlock()
       |      |
       |      +-- Có, nhưng phải hủy được
       |              → lockInterruptibly() + finally unlock()
       |
       +-- Không thể chờ?
       |       → tryLock()
       |       → false: fallback có chủ đích
       |
       +-- Chỉ được chờ một khoảng giới hạn?
               → tryLock(timeout, unit)
               → true: vào critical section + finally unlock()
               → false: timeout/fallback
               → InterruptedException: propagate hoặc restore + cancel
~~~

Trước khi đưa vào production, tự trả lời:

1. Lock reference có ổn định, thuộc đúng shared state và dùng chung bởi tất cả writer/reader không?
2. Có xử lý riêng thành công, timeout, interrupt? Caller có biết khi nào công việc không được thực hiện không?
3. Có đảm bảo unlock đúng số lần và đúng thread trên mọi đường return/exception không?
4. Timeout là ngân sách cho lock hay cho toàn tác vụ? Các bước khác có thời hạn không?
5. Fairness có phải yêu cầu thật? Dùng untimed tryLock trên fair lock có chủ đích không?
6. Nếu retry, có trần thời gian/số lần và cơ chế tránh spin/livelock không?
7. Nếu dùng nhiều lock, có lock-order policy, release on failure và kiểm tra deadlock không?
8. Đã đo contention, thời gian giữ khóa, timeout ratio và tail latency trên tải thật chưa?

## 19. Câu hỏi luyện tập

**Câu 1.** Thread A giữ lock, thread B gọi `tryLock()`. B sẽ nhận gì?

**Đáp án:** B nhận `false` ngay (nếu B không phải chính owner). Không chờ A nhả.

**Câu 2.** Nếu B gọi `tryLock(100, MILLISECONDS)` và A giữ quá 100ms, B sẽ nhận gì?

**Đáp án:** Nếu không có interrupt và B không acquire được, nó trả `false` khi hết hạn. Không có bảo đảm độ trễ tường chính xác tới mili giây.

**Câu 3.** B bị interrupt trong lúc chờ timed tryLock. Nên xử lý giống false không?

**Đáp án:** Không. Nó ném `InterruptedException` và xóa interrupted flag ở thời điểm ném; code cần propagate hoặc khôi phục flag rồi kết thúc theo cancellation policy.

**Câu 4.** Khi `tryLock()` trả true và trong critical section xảy ra exception, có cần unlock?

**Đáp án:** Có, trong `finally` sau khi acquire thành công.

**Câu 5.** Với `new ReentrantLock(true)`, `tryLock()` có tuân thủ hàng chờ fair không?

**Đáp án:** Không bắt buộc; overload untimed có thể barging. Timed overload tôn trọng fairness setting.

**Câu 6.** Cùng một thread đang giữ ReentrantLock lại gọi `tryLock()` thì sao?

**Đáp án:** Trả true, tăng hold count. Phải unlock đủ lần để nhả hoàn toàn.

**Câu 7.** Một service nhận `false` từ timed tryLock rồi silently return trong nhiệm vụ chuyển trạng thái bắt buộc. Có đúng không?

**Đáp án:** Chưa đủ. Phải quyết định nghĩa vụ xử lý: retry có giới hạn, đưa vào queue hoặc báo trạng thái thất bại rõ ràng. Timeout chỉ mô tả không acquire được lock, không xóa yêu cầu nghiệp vụ.

**Câu 8.** Có thể dùng `synchronized(myLock)` để khóa cùng quyền sở hữu như `myLock.lock()` không?

**Đáp án:** Không. Monitor nội tại của object Lock và giao thức Lock API không tự tương đương.

## 20. Tài liệu gốc

- `ReentrantLock` (Java SE 21): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html
- `Lock` interface (Java SE 21): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/Lock.html
- `TimeUnit`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/TimeUnit.html
- `Thread.interrupt`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html#interrupt()
- JLS `17.4 (Java Memory Model): https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html#jls-17.4

**Ghi nhớ:** `tryLock()` giúp quyết định **ngay** có vào critical section được không; `tryLock(timeout, unit)` cho phép **chờ có giới hạn và phản ứng interrupt**. Khi acquire thành công, thread phải unlock trong finally. Khi thất bại, trả về trạng thái có ý nghĩa nghiệp vụ; timeout không thay thế việc xử lý contention, deadline toàn nghiệp vụ hoặc thiết kế locking đúng đắn.
