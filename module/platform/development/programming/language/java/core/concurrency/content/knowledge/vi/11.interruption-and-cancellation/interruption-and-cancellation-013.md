# Vì sao tránh Thread.stop(), suspend() và resume(): rủi ro khóa và tính nhất quán

Trong ứng dụng Java đa luồng, một yêu cầu “dừng công việc ngay”, “tạm dừng luồng” hoặc “cho luồng chạy tiếp” có thể làm thay đổi tính đúng đắn của cả hệ thống. Ba API cũ `Thread.stop()`, `Thread.suspend()` và `Thread.resume()` từng cho phép thread khác can thiệp trực tiếp vào luồng đang chạy mà không cần luồng mục tiêu tự chọn **điểm an toàn (safe point)**. Điều này nguy hiểm khi luồng đang giữ monitor, cập nhật nhiều trường trong cùng invariant, thao tác với tài nguyên hoặc đợi một tác vụ khác.

Giải pháp hiện đại không phải tìm API “kill thread nhanh hơn” mà là thiết kế **cooperative cancellation**, **pause/resume theo trạng thái**, **commit/rollback hợp lệ** và **xác nhận hoàn tất**. `Thread.interrupt()` và `Future.cancel(true)` là tín hiệu yêu cầu hủy chứ không phải công cụ tự động ép mọi dòng mã đang chạy dừng tức thời.

Bài này thuộc chủ đề **Interrupt & Hủy, Java Concurrency nói chung**. Nó trình bày semantics chính xác theo phiên bản JDK, nguyên nhân rủi ro khóa/tính nhất quán, thay thế an toàn, ví dụ Java 17+ chạy được và cách kiểm thử. Các cơ chế chuyên biệt của Spring nằm ngoài phạm vi.

## 1. Phân biệt dừng, tạm dừng và tiếp tục

| Yêu cầu | Ý nghĩa nghiệp vụ | Hợp đồng nên thiết kế |
| --- | --- | --- |
| **Stop/cancel** | Không tiếp tục công việc, giải phóng tài nguyên, cho caller nhận biết đã kết thúc. | Controller yêu cầu → worker nhận biết → kết thúc/rollback operation → cleanup → hoàn tất. |
| **Pause** | Giữ worker còn sống nhưng chưa bắt đầu bước mới trong khi đang tạm dừng. | Worker tự chờ tại safe point, không giữ lock nghiệp vụ mà controller hoặc thread khác cần. |
| **Resume** | Cho worker tiếp tục sau pause. | Cập nhật một predicate như `paused=false` rồi signal; worker kiểm tra trạng thái trước khi đợi. |
| **Timeout** | Caller không được chờ quá một khoảng xác định. | Hết deadline → trả trạng thái timeout/cancel request; không tự đồng nghĩa worker đã chết. |
| **Shutdown** | Hệ thống không nhận thêm việc, giải phóng và chờ các task đang chạy. | Chính sách owner cho executor, thread, queue, file/socket và data lifecycle. |

Sự khác nhau quan trọng là **một thread không chỉ chứa CPU instructions**: nó có thể sở hữu lock, tài nguyên, object graph chưa nhất quán và một transaction đang diễn ra. Controller ở bên ngoài thường không biết ranh giới nào có thể dừng an toàn.

## 2. Các API cũ đã thay đổi theo phiên bản JDK

Không thể viết rằng “`Thread.stop` luôn gây `ThreadDeath`” mà không nêu phiên bản Java. Tình trạng chính xác:

| API | JDK 17 (hành vi lịch sử) | Từ JDK 20 trở đi |
| --- | --- | --- |
| `Thread.stop()` | Deprecated; từng ép thread mục tiêu nhận `ThreadDeath` bất đồng bộ. Khi stack unwind, các monitor được nhả. | **Luôn ném `UnsupportedOperationException`** tại lời gọi; khả năng ép stop đã bị loại bỏ. |
| `Thread.suspend()` | Deprecated, for removal; từng đình chỉ một thread, kể cả khi nó đang giữ monitor. | **Luôn ném `UnsupportedOperationException`**. |
| `Thread.resume()` | Deprecated, for removal; từng tiếp tục một thread đã suspend. | **Luôn ném `UnsupportedOperationException`**. |

Chúng đã bị deprecated từ JDK 1.2 (1998). Đến JDK 20, khả năng stop/suspend/resume kiểu cũ bị loại bỏ; các method còn trong API để tương thích về ký hiệu nhưng ném exception. Vì vậy **không chạy thử các lời gọi này** như một chiến lược kiểm soát luồng. Trên JVM cũ, chúng có thể phá tính đúng đắn; trên JVM mới, chúng không còn thực hiện tác dụng mà code cũ mong muốn.

Tài liệu chính thức: [Thread JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html), [Thread JDK 20](https://docs.oracle.com/en/java/javase/20/docs/api/java.base/java/lang/Thread.html), [Oracle JDK 20 Release Notes](https://www.oracle.com/java/technologies/javase/20-relnote-issues.html), [Java Thread Primitive Deprecation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/doc-files/threadPrimitiveDeprecation.html).

Tất cả ví dụ runnable ở các phần sau dùng Java 17+ **không gọi** ba API cũ. Các đoạn mô tả sai chỉ để phân tích failure mode, không phải code nên đưa vào sản phẩm.

## 3. Nguyên nhân Thread.stop() lịch sử làm hỏng dữ liệu

Giả sử hai trường đại diện cho hai tài khoản nội bộ, invariant là `accountA + accountB == 100`. Một operation chuyển 30 đơn vị:

~~~java
synchronized (lock) {
    accountA -= 30;
    accountB += 30;
}
~~~

Đây là mảnh code minh họa, giả định các field và `lock` đã được khai báo. Khi operation chạy đầy đủ và mọi reader/writer tuân thủ cùng monitor, hai bước có thể được quan sát như một thay đổi logic.

Nhưng trên JDK 17, `Thread.stop()` lịch sử có thể ép thread đang chạy ném `ThreadDeath` tại một điểm bất đồng bộ:

~~~text
Worker sở hữu monitor L              Controller / Observer
------------------------              ----------------------
lock(L)
accountA = 70
                                      stop(worker) theo semantics cũ
ThreadDeath khiến stack unwind
monitor L được nhả
accountB vẫn = 0
                                      observer lấy được L
                                      thấy A=70, B=0, tổng=70
~~~

Khi exception unwind stack, monitor bị nhả như quy tắc của `synchronized`. Đây là một đặc điểm tốt cho exception thông thường, nhưng cực kỳ nguy hiểm khi việc chấm dứt bị áp đặt giữa những phép ghi thuộc một invariant: **object bị công bố trong trạng thái dở dang**.

Điểm mấu chốt:

- **Mutual exclusion không tự tạo rollback.** Monitor ngăn hai thread chen ngang khi đang được giữ, nhưng không hoàn tác các assignment khi thread sở hữu thoát bất thường.
- **Happens-before không sửa dữ liệu sai.** Unlock → lock sau đó có thể giúp reader thấy những phép ghi đã xảy ra, kể cả một cặp trạng thái đã bị hỏng.
- **Lỗi có thể xuất hiện muộn.** Một object dở dang có thể tiếp tục được sử dụng và chỉ gây lỗi ở operation khác rất lâu sau lần stop.
- **Ngoại lệ bị chèn không đúng điểm nghiệp vụ.** Code không thể dựa vào giả định “sau validation thì các phép gán primitive không ném exception” khi cơ chế bên ngoài có thể ngắt tại bất kỳ chỗ không được thiết kế.

### 3.1 Vì sao finally không phải phép chữa tự động?

~~~java
synchronized (lock) {
    try {
        accountA -= 30;
        accountB += 30;
    } finally {
        closeTemporaryResource();
    }
}
~~~

Đây là mảnh giả định `closeTemporaryResource()` tồn tại. `finally` có thể chạy khi stack unwind, nhưng nó **không tự biết** bước nào của nghiệp vụ đã commit và không có cách chung để đảo:

- Các phép ghi vào nhiều object;
- Một message đã phát hoặc email đã gửi;
- Lệnh gọi remote đã thành công nhưng caller chỉ thấy timeout;
- Một file đã ghi được một phần;
- Callback hoặc state machine khác đã quan sát dữ liệu trung gian.

Kể cả tự viết rollback, rollback có thể gặp lỗi hoặc đua với các thread khác. Trong JVM cũ, việc cố bắt `ThreadDeath` cũng không tạo chiến lược chung an toàn; `ThreadDeath` kế thừa `Error`, thường không bị bắt bởi `catch (Exception)` và có thể bị code `catch (Throwable)` xử lý sai.

**Kết luận:** không có phương pháp tổng quát để ép thread dừng tại bất kỳ instruction nào nhưng vẫn bảo đảm mọi invariant và tài nguyên còn đúng.

## 4. Vì sao Thread.suspend() và resume() lịch sử dễ deadlock?

Trái với `stop()`, cơ chế `suspend()` trước đây **không nhả những monitor mà thread đang sở hữu**. Một thread bị đình chỉ có thể đang giữ lock của queue, cache, bộ đếm, class initialization hoặc cấu trúc dữ liệu chia sẻ. Tất cả contender của monitor ấy phải đợi.

~~~text
Thread A / worker                     Thread B / controller
-----------------                     ---------------------
synchronized (L) {
    ... giữ monitor L ...
}
A bị suspend khi vẫn giữ L
                                      synchronized (L) {
                                          // muốn gọi resume(A)
                                      }
                                      B BLOCKED chờ L

A không tiến triển vì bị suspend.
B không lấy được L để gửi resume.
=> Vòng phụ thuộc; deadlock / ứng dụng "đóng băng".
~~~

Đây là **sơ đồ phân tích lịch sử**, không phải code cần thực thi.

Rủi ro không chỉ có hai thread trong sơ đồ. Worker có thể giữ nhiều monitor của thư viện mà controller không biết; pause một thread vào thời điểm không kiểm soát có thể chặn cả thread đang cố thu hồi tài nguyên.

### 4.1 Resume sớm không phải tín hiệu được lưu

Nếu controller gửi một lệnh “resume” khi worker chưa suspended, điều đó không đồng nghĩa cấp một permit bền vững cho lần suspend tương lai. Một lần suspend xảy ra sau đó vẫn có thể khiến worker đứng im, không có lần resume tiếp theo.

Một giao thức pause/resume an toàn phải **lưu trạng thái mong muốn** vào predicate như `paused`, rồi thread tự kiểm tra và chờ. Tín hiệu signal chỉ để đánh thức thread **đang chờ**; **state** mới là nguồn sự thật cho thread đến sau.

### 4.2 Không dùng busy waiting thay suspend

~~~java
while (paused) {
    // Poll liên tục, không làm việc hữu ích.
}
~~~

Đây là mảnh mã không nên dùng cho pause lâu. Nếu `paused` là field thường, có thể thiếu visibility; nếu volatile, thread vẫn chiếm CPU khi spin. Chọn `Condition.await()` hoặc `Object.wait()` để worker nhả đúng lock điều khiển và block trong lúc chờ.

## 5. Cooperative cancellation: controller yêu cầu, worker tự kết thúc

Thay vì cưỡng ép dừng thread, hãy thiết kế một vòng đời hợp tác:

~~~text
Controller                        Worker
----------                        -------------------------
request stop / interrupt()
       |                           làm việc ở current unit
       |-------------------------> kiểm tra yêu cầu ở safe point
                                   hoàn tất/rollback operation
                                   đóng resource đang sở hữu
                                   thoát run()/call()
caller join()/awaitTermination()   TERMINATED / task completed
~~~

Một **safe point ở cấp ứng dụng** là ranh giới nơi task có thể quyết định không làm thêm việc mà không phá invariant. Nó không phải “JVM safepoint” nội bộ cho GC.

Cách triển khai:

1. Controller ghi nhận yêu cầu dừng bằng `interrupt()`, flag `volatile`/`AtomicBoolean` hoặc state được bảo vệ bởi lock.
2. Worker kiểm tra yêu cầu ở những ranh giới đủ thường xuyên (giữa các unit of work).
3. Nếu đang chờ API interruptible, controller dùng `interrupt()` để đánh thức theo hợp đồng API ấy.
4. Worker hoàn tất/rollback transaction đang dở và đóng resource trong `finally`/`try-with-resources`.
5. Worker thoát; controller `join()` hoặc kiểm tra completion của task.
6. Nếu worker không hợp tác, có deadline, log chẩn đoán và cách cô lập task, **không gọi stop cũ**.

Cơ chế này có thể không dừng tức thì, nhưng **cho phép chọn ranh giới an toàn**. Một hệ thống yêu cầu “kill ngay code không tin cậy” thường cần **process isolation** và policy thu hồi process/resource bên ngoài thread.

## 6. Thread.interrupt(): tín hiệu, không phải thao tác kill

`Thread.interrupt()` đặt trạng thái interruption hoặc làm một số blocking API phản ứng bằng exception. Nó **không trực tiếp kết thúc Java thread** đang tính toán.

| Trạng thái của worker | Hành vi khi interrupt | Cần xử lý |
| --- | --- | --- |
| CPU-bound loop | Interrupted status được đặt; worker chỉ dừng khi tự kiểm tra. | `isInterrupted()`/flag ở safe point. |
| `Thread.sleep`, `Object.wait`, `Thread.join` | Có thể ném `InterruptedException`, thường xóa interrupted status lúc ném. | Propagate hoặc restore rồi thoát. |
| `CountDownLatch.await`, `BlockingQueue.take` | Có thể ném `InterruptedException`. | Cleanup theo contract, không nuốt lỗi. |
| `ReentrantLock.lockInterruptibly()` | Có thể bỏ chờ lấy lock khi bị interrupt. | Không unlock nếu chưa acquire. |
| `synchronized` đang `BLOCKED` chờ monitor | Không có interruptible acquisition tương đương. | Không kỳ vọng thoát chờ monitor ngay. |
| I/O | Tùy channel, stream, driver và platform. | Dùng timeout hoặc đóng resource theo hợp đồng API cụ thể. |

Không hứa rằng `interrupt()` sẽ ngắt mọi thao tác I/O ngay. Một số API hỗ trợ cancellation bằng interruption, một số cần đóng socket/channel, và một số có hành vi phức tạp.

### 6.1 isInterrupted() so với Thread.interrupted()

~~~java
boolean flag1 = Thread.currentThread().isInterrupted();
boolean flag2 = Thread.interrupted();
~~~

Mảnh code trên không độc lập. `isInterrupted()` đọc status **không xóa flag**. `Thread.interrupted()` là static method, đọc rồi **xóa flag của current thread**. Việc dùng `Thread.interrupted()` trong loop mà không lưu kết quả có thể vô tình xóa thông tin hủy.

Để hủy CPU loop:

~~~java
while (!Thread.currentThread().isInterrupted()) {
    doOneBoundedStep();
}
~~~

Đây là mảnh code giả định `doOneBoundedStep()` có thời gian hữu hạn và không tự phá invariant. Nếu mỗi bước có thể chạy hàng giờ, cancellation latency vẫn cao.

## 7. Ví dụ Java 17+: interrupt worker đang chờ

Tạo file `CooperativeCancelDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;

public final class CooperativeCancelDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch neverReleased = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            try {
                entered.countDown();
                neverReleased.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                System.out.println("Cancel observed");
            } finally {
                System.out.println("Cleanup executed");
            }
        }, "worker");

        worker.start();
        entered.await();
        worker.interrupt();
        worker.join();

        System.out.println("Alive: " + worker.isAlive());
    }
}
~~~

Lệnh JDK 17+:

~~~bash
javac CooperativeCancelDemo.java
java CooperativeCancelDemo
~~~

Stdout nếu không có tác nhân ngoài can thiệp:

~~~text
Cancel observed
Cleanup executed
Alive: false
~~~

Giải thích:

- `entered.countDown()` báo mốc worker đã bắt đầu; main không cần sleep để đoán thời gian.
- Main có thể interrupt trước **hoặc sau** khi worker thực sự vào `neverReleased.await()`. Cả hai trường hợp đều được blocking wait nhận biết.
- `InterruptedException` là đường thoát hợp tác; worker restore flag bằng `Thread.currentThread().interrupt()` và ra khỏi task.
- `finally` hoàn tất trước khi thread kết thúc; main `join()` nên in trạng thái `Alive: false` sau các dòng worker.
- Trong sản phẩm, thay `System.out.println("Cleanup executed")` bằng cleanup resource thật: đóng file/socket/transaction handle theo hợp đồng. In log không tự là cleanup.

Không dùng thử `Thread.stop()` để “so sánh” trong chương trình: nó không có lợi ích học tập nào đáng với nguy cơ trên JDK cũ và ném exception ở JDK mới.

## 8. Cách xử lý InterruptedException đúng

Có hai lựa chọn thường gặp:

**Truyền tiếp exception** nếu method có thể khai báo:

~~~java
void runBlockingTask() throws InterruptedException {
    queue.take();
}
~~~

Mảnh minh họa giả định `queue` đã khai báo. Caller sở hữu task có thể quyết định shutdown/cancel tiếp.

**Khôi phục interrupted status rồi thoát** khi đang trong `Runnable.run()` không khai báo checked exception:

~~~java
try {
    blockingOperation();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
~~~

Mảnh này nằm trong method trả `void`, giả định `blockingOperation()` được định nghĩa. Nhiều blocking API xóa interrupted flag lúc ném `InterruptedException`, nên restore flag cho phép tầng cleanup/caller biết yêu cầu hủy từng xuất hiện.

Sai lầm phổ biến:

~~~java
try {
    blockingOperation();
} catch (InterruptedException ignored) {
    // Bỏ qua rồi tiếp tục chạy.
}
~~~

Đoạn này làm cancellation mất hiệu lực nếu không có protocol khác. Nếu task đã quyết định **thật sự xử lý xong** interruption và tiếp tục, phải có lý do nghiệp vụ và trạng thái rõ ràng; đừng âm thầm swallow.

## 9. Không kiểm tra cờ hủy giữa một operation phải atomic

Giả sử chuyển tiền A→B:

~~~java
synchronized (lock) {
    accountA -= amount;
    if (Thread.currentThread().isInterrupted()) {
        return; // Sai: đã trừ A nhưng chưa cộng B.
    }
    accountB += amount;
}
~~~

Đây là **mảnh lỗi**, giả định method trả `void` và các biến có sẵn. Mặc dù `synchronized` tự nhả monitor khi return, state sau đó đã sai invariant. **Cooperative cancellation cũng có thể sai** nếu chọn safe point giữa hai bước thuộc cùng một transaction.

Mẫu thiết kế tốt hơn:

~~~text
kiểm tra cancel
      |
acquire monitor
validate input và state
tính nextA, nextB
commit A và B trong một critical section ngắn
release monitor
      |
kiểm tra cancel trước unit tiếp theo
~~~

Một critical section không chứa blocking operation và có thời gian nhỏ thường không cần ngắt giữa chừng. Nếu phải gọi API có thể throw hoặc block bên trong, cần chuẩn bị rollback hoặc cấu trúc lại work boundary. `finally` nhả lock **không tự rollback** các phép ghi đã thực hiện.

## 10. Ví dụ Java 17+: dừng ở ranh giới giao dịch an toàn

Tạo `SafeCommitCancelDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;

public final class SafeCommitCancelDemo {
    private record Snapshot(long a, long b) {
        long total() {
            return Math.addExact(a, b);
        }
    }

    private static final class Ledger {
        private final Object lock = new Object();
        private long a = 100;
        private long b;

        void transfer(long amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount");
            }
            synchronized (lock) {
                if (a < amount) {
                    throw new IllegalArgumentException("insufficient");
                }
                long nextA = a - amount;
                long nextB = Math.addExact(b, amount);
                a = nextA;
                b = nextB;
            }
        }

        Snapshot snapshot() {
            synchronized (lock) {
                return new Snapshot(a, b);
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Ledger ledger = new Ledger();
        CountDownLatch committed = new CountDownLatch(1);
        CountDownLatch afterCommitWait = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            try {
                ledger.transfer(30);
                committed.countDown();
                afterCommitWait.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "transfer-worker");

        worker.start();
        committed.await();
        worker.interrupt();
        worker.join();

        Snapshot s = ledger.snapshot();
        System.out.println("A: " + s.a());
        System.out.println("B: " + s.b());
        System.out.println("Total: " + s.total());
        System.out.println("Alive: " + worker.isAlive());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac SafeCommitCancelDemo.java
java SafeCommitCancelDemo
~~~

Stdout:

~~~text
A: 70
B: 30
Total: 100
Alive: false
~~~

**Vì sao an toàn trong phạm vi ví dụ?**

- `ledger.transfer(30)` tính số dư mới, kiểm tra `Math.addExact` trước khi sửa state, rồi commit cả hai field dưới cùng monitor.
- `committed.countDown()` chỉ được phát sau khi method transfer kết thúc. Main đợi mốc này rồi mới gửi interruption.
- Worker xử lý interruption khi đang hoặc sắp chờ `afterCommitWait.await()`, bên ngoài critical section. Không rời đi giữa debit và credit.
- Main gọi `join()` trước khi đọc `snapshot()`. Snapshot cũng lấy cùng lock bảo vệ state.
- Dữ liệu cuối thỏa invariant `A+B=100`, không phụ thuộc thứ tự scheduling giữa yêu cầu interrupt và lời gọi await.

Ví dụ này là **in-memory transaction**, không phải database transaction. Nếu debit/credit là các external service calls, cần giao thức dữ liệu/transaction và idempotency tương ứng.

## 11. Pause/resume hợp tác bằng Condition và predicate

Một thread nên tự kiểm tra **pause flag** tại safe point, rồi chờ nếu controller yêu cầu. Cơ chế `ReentrantLock` + `Condition` phù hợp vì:

- Predicate `paused/stopped` được bảo vệ bởi lock.
- `Condition.await()` nhả **lock của Condition** trong lúc chờ, rồi reacquire trước khi trả về.
- `signalAll()` thức những waiter đang chờ, nhưng **không lưu signal** cho waiter đến sau; predicate lưu trạng thái mới.
- Vòng `while` kiểm tra lại điều kiện sau spurious wakeup hoặc khi có thay đổi trạng thái.
- `stopRequested` có ưu tiên hơn pause, tránh worker bị kẹt ở paused khi cần shutdown.

Mẫu state machine:

~~~text
RUNNING --requestPause--> PAUSE_REQUESTED
PAUSE_REQUESTED --worker reaches safe point--> PAUSED
PAUSED --requestResume--> RUNNING
RUNNING/PAUSED --requestStop--> STOP_REQUESTED
STOP_REQUESTED --worker cleanup--> TERMINATED
~~~

`pause()` trả về không có nghĩa worker đã **acknowledge** rằng nó đang PAUSED. Nếu application cần mạnh hơn (“worker đã ra khỏi tất cả critical section”), phải thiết kế acknowledgement riêng.

## 12. Ví dụ Java 17+: SafePauseResumeDemo

Tạo file `SafePauseResumeDemo.java`:

~~~java
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public final class SafePauseResumeDemo {
    private static final class Gate {
        private final ReentrantLock lock = new ReentrantLock();
        private final Condition changed = lock.newCondition();
        private boolean paused;
        private boolean stopped;

        void pause() {
            lock.lock();
            try {
                if (!stopped) {
                    paused = true;
                }
            } finally {
                lock.unlock();
            }
        }

        void resume() {
            lock.lock();
            try {
                paused = false;
                changed.signalAll();
            } finally {
                lock.unlock();
            }
        }

        void stop() {
            lock.lock();
            try {
                stopped = true;
                paused = false;
                changed.signalAll();
            } finally {
                lock.unlock();
            }
        }

        boolean awaitRunning() throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (paused && !stopped) {
                    changed.await();
                }
                return !stopped;
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Gate first = new Gate();
        first.pause();
        first.resume(); // Signal trước khi worker đến.

        Thread early = new Thread(() -> {
            try {
                if (first.awaitRunning()) {
                    System.out.println("Early resume preserved");
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });
        early.start();
        early.join();

        Gate second = new Gate();
        second.pause();
        Thread cancelled = new Thread(() -> {
            try {
                if (!second.awaitRunning()) {
                    System.out.println("Stop while paused");
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });
        cancelled.start();
        second.stop(); // Có thể trước hoặc sau await.
        cancelled.join();

        System.out.println("Done");
    }
}
~~~

Chạy JDK 17+:

~~~bash
javac SafePauseResumeDemo.java
java SafePauseResumeDemo
~~~

Stdout:

~~~text
Early resume preserved
Stop while paused
Done
~~~

**Giải thích:**

1. Với gate thứ nhất, `resume()` chạy **trước** khi worker tới. State `paused=false` được lưu; worker đọc predicate và không chờ. Không có “lost resume”.
2. Với gate thứ hai, worker bắt đầu trong trạng thái `paused=true`. Dù controller `stop()` được thực thi trước hay sau khi worker gọi await, `stopped=true` vẫn được lưu và `signalAll` đánh thức đúng khi cần. Worker trả `false`.
3. `awaitRunning()` dùng `while (paused && !stopped)` để chống spurious wakeup và race khi nhiều controller thay state.
4. Gate dùng `lockInterruptibly()` khi acquire lock; nếu worker bị interrupt, nó có thể thoát khỏi chờ acquisition theo contract.
5. `stop()` ở đây là **method của ứng dụng Gate**, không phải `Thread.stop()`. Nó chỉ thay trạng thái, hoàn toàn không cưỡng bức dừng thread.

**Giới hạn:** ví dụ mô tả một gate cho một task, chưa có acknowledgement thực sự đã pause, chưa có job queue, và không có resource cleanup phức tạp. Trong một worker loop, hãy đặt `gate.awaitRunning()` ở ranh giới **trước unit of work**, không gọi khi đang giữ một monitor nghiệp vụ khác.

## 13. Object.wait()/notifyAll() là một lựa chọn khác

Không nhất thiết phải dùng `ReentrantLock`. Một controller dựa trên intrinsic monitor cũng hợp lệ:

~~~java
private final Object controlLock = new Object();
private boolean paused;
private boolean stopped;

void requestPause() {
    synchronized (controlLock) {
        if (!stopped) {
            paused = true;
        }
    }
}

void requestResume() {
    synchronized (controlLock) {
        paused = false;
        controlLock.notifyAll();
    }
}

void requestStop() {
    synchronized (controlLock) {
        stopped = true;
        paused = false;
        controlLock.notifyAll();
    }
}

boolean awaitPermission() throws InterruptedException {
    synchronized (controlLock) {
        while (paused && !stopped) {
            controlLock.wait();
        }
        return !stopped;
    }
}
~~~

Đây là **mảnh code để đặt trong một class**, không có `main`. Cùng một monitor bảo vệ tất cả predicate và tín hiệu, nên “resume trước wait” không mất state. `Object.wait()` chỉ nhả **monitor controlLock**, không nhả bất kỳ monitor khác mà worker đang sở hữu. Vì vậy tuyệt đối tránh:

~~~java
synchronized (businessLock) {
    gate.awaitPermission(); // Có thể pause nhưng vẫn giữ businessLock!
}
~~~

Đây là mảnh code **nguy hiểm**: worker chờ ở gate nhưng vẫn giữ lock nghiệp vụ, khiến các thread khác có thể bị block vô hạn. Đặt pause gate **ngoài** critical section nghiệp vụ:

~~~java
while (gate.awaitPermission()) {
    doOneCompleteBusinessOperation();
}
~~~

Hai mảnh giả định `gate` và các object đã được khai báo; method xử lý `InterruptedException`.

## 14. Future.cancel(true) quản lý task, không giết worker

Trong `ExecutorService`, worker thread thuộc executor; task được biểu diễn bởi `Future`. Nên yêu cầu hủy task thay vì điều khiển Thread của pool trực tiếp.

~~~java
Future<?> future = executor.submit(task);
boolean cancelled = future.cancel(true);
~~~

Đây là mảnh mã minh họa. `cancel(true)` yêu cầu hủy, có thể interrupt worker đang thực thi; `Future` chuyển sang trạng thái cancelled nếu lệnh hủy thành công theo contract. **Future cancelled không chứng minh mọi dòng user code đã dừng ngay.** Task bỏ qua interruption có thể tiếp tục chạy.

### 14.1 Ví dụ Java 17+: task nhận cancellation

Tạo `FutureCancelDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class FutureCancelDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch blocker = new CountDownLatch(1);

        try {
            Future<?> future = executor.submit(() -> {
                try {
                    entered.countDown();
                    blocker.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });

            entered.await();
            boolean requested = future.cancel(true);
            System.out.println("Cancel accepted: " + requested);
            System.out.println("Future cancelled: " + future.isCancelled());
        } finally {
            executor.shutdownNow();
            executor.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
~~~

Chạy:

~~~bash
javac FutureCancelDemo.java
java FutureCancelDemo
~~~

Stdout khi không có external interruption:

~~~text
Cancel accepted: true
Future cancelled: true
~~~

Task đã vào runnable và chờ trên latch, nên trước lúc hủy nó chưa tự hoàn tất. `cancel(true)` đánh dấu hủy và yêu cầu interruption. Task nhận `InterruptedException`, restore flag rồi thoát. `shutdownNow()` trong finally vẫn là **best effort**; `awaitTermination` có deadline 5 giây nhưng ví dụ không giả vờ rằng mọi task không hợp tác đều phải dừng.

Không can thiệp trực tiếp `Thread.stop()` vào worker của executor: có thể phá state của task hoặc pool trên JVM cũ, và trên JDK 20+ lời gọi không còn có chức năng đó.

## 15. Executor shutdown: lifecycle riêng của tập hợp task

Một ứng dụng sở hữu executor cần quy trình shutdown:

- `shutdown()` ngừng nhận task mới, cho các task đã chấp nhận tiếp tục.
- `awaitTermination(timeout, unit)` đợi tới khi executor terminated; trả `false` nếu hết thời gian mà chưa hoàn tất.
- `shutdownNow()` cố gắng hủy task đang chạy (thường qua interruption), trả các task chưa được thực thi trong queue; **không bảo đảm dừng mọi task**.
- `Future.cancel(true)` nhắm tới một task, không tương đương tắt executor.
- `Thread.interrupt()` nhắm tới một Thread do application sở hữu, không thay shutdown của pool.

Mẫu điển hình:

~~~java
executor.shutdown();
try {
    if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
        executor.shutdownNow();
        if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
            System.err.println("Executor did not terminate");
        }
    }
} catch (InterruptedException e) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
}
~~~

Đây là mảnh code minh họa, giả định `executor` là `ExecutorService` và đã import `TimeUnit`. Timeout là ví dụ API, không phải SLA chung. Nếu một task kẹt trong I/O không có timeout hoặc không hợp tác với interruption, executor vẫn có thể không dừng ngay.

## 16. Vì sao timeout không đồng nghĩa terminate?

Các API có timeout **giới hạn thời gian caller đợi**, không tự ép thread mục tiêu biến mất:

| API | Khi hết thời gian chờ | Task/Thread mục tiêu |
| --- | --- | --- |
| `Thread.join(timeout)` | Trả về, cần kiểm tra `isAlive()`. | Có thể vẫn đang chạy. |
| `Future.get(timeout, unit)` | Ném `TimeoutException`. | Có thể vẫn đang chạy, chưa bị cancel. |
| `Condition.await(timeout, unit)` | Báo trạng thái hết hạn theo overload. | Producer/worker khác không bị dừng. |
| `ReentrantLock.tryLock(timeout, unit)` | Trả false nếu không lấy được lock. | Holder tiếp tục giữ lock nếu chưa nhả. |
| `ExecutorService.awaitTermination(timeout, unit)` | Trả false nếu executor chưa terminated. | Worker có thể vẫn hoạt động. |

Nếu contract yêu cầu deadline, có thể dùng các bước **timeout → cancel request → chờ cleanup thêm có giới hạn → báo trạng thái**. Không tuyên bố “đã dừng” chỉ vì đã gửi interrupt hoặc cancel.

## 17. Khi interrupt chưa có hiệu lực: tìm đúng nguyên nhân

### 17.1 CPU loop không kiểm tra trạng thái

~~~java
while (true) {
    computeNext();
}
~~~

Nếu `computeNext()` không tự kiểm tra cancellation và không ném exception, `interrupt()` chỉ đặt flag. Thay bằng bounded units và check:

~~~java
while (!Thread.currentThread().isInterrupted()) {
    computeOneBoundedUnit();
}
~~~

Đây là mảnh code minh họa.

### 17.2 Đợi vào intrinsic monitor

Thread đang `BLOCKED` để vào `synchronized(lock)` **không có interruptible acquisition** như `ReentrantLock.lockInterruptibly()`. Nếu cancellation khi đợi lock là yêu cầu thật, cân nhắc đổi primitive, giữ nguyên invariants/lock ordering.

### 17.3 I/O không phản hồi interruption

Socket, channel, file I/O, native library và các driver khác nhau có semantics riêng. Có API phản hồi bằng exception, có API cần đóng resource để đánh thức, có API chỉ hỗ trợ timeout. Dựa vào tài liệu của **đúng I/O API**. Không hứa “mọi I/O bị interrupt là dừng ngay”.

### 17.4 Nuốt InterruptedException

~~~java
try {
    queue.take();
} catch (InterruptedException ignored) {
    // Bỏ qua rồi tiếp tục làm việc.
}
~~~

Đây là mảnh lỗi. Nếu task lặp lại vô hạn, cancellation request có thể bị bỏ mất. Propagate hoặc restore flag và thoát ở ranh giới hợp lệ.

### 17.5 Pause trong khi đang giữ lock khác

`Condition.await()` chỉ nhả lock **liên kết với Condition**, không nhả một `businessLock` khác. Nếu worker gọi gate khi giữ businessLock, mọi waiter của businessLock có thể bị chặn tới lúc resume. Đưa gate ra ngoài critical section.

## 18. Invariant, exception safety và tính nhất quán

Để dừng an toàn, phải xác định những state nào được phép publish:

| State | Invariant cần giữ | Điểm hủy an toàn |
| --- | --- | --- |
| Hai tài khoản A/B | `A + B == total`, không âm | Trước transfer hoặc sau khi hai số dư đã commit. |
| Đơn hàng và thanh toán | `PAID` chỉ khi có kết quả thanh toán hợp lệ | Sau transaction/state-machine transition đã được chứng minh. |
| Queue và bộ đếm | Phần tử trong queue/counter khớp contract | Sau operation đồng bộ trên queue/counter. |
| File đích | Không công bố file mới chỉ được ghi một phần | Ghi file tạm, validate, publish qua thao tác phù hợp filesystem. |
| Tài nguyên lock | Không giữ lock khi task đã dừng | Nhả trong `finally` khi đã acquire; không tự dừng giữa bất kỳ instruction. |
| Callback ngoài | Không gọi code không kiểm soát khi đang giữ lock quan trọng | Chụp snapshot dưới lock rồi callback bên ngoài với protocol ordering rõ. |

Một exception đồng bộ có thể được phòng tránh bằng **validate/calculate trước commit**, ví dụ gọi `Math.addExact` trước khi gán hai field. `Thread.stop()` lịch sử phá giả định đó vì có thể xen vào giữa các phép gán mà tác giả không dự đoán.

Trong hệ thống nhiều process/database, lock JVM không tạo giao dịch bền vững; cần transaction, versioning, idempotency/compensation theo failure model riêng. Đừng suy từ `synchronized` rằng external side effect đã rollback.

## 19. Visibility và happens-before của cờ hủy

Một thread có thể đặt flag:

~~~java
private volatile boolean stopRequested;

void requestStop() {
    stopRequested = true;
}

void runLoop() {
    while (!stopRequested) {
        doOneBoundedUnit();
    }
}
~~~

Đây là mảnh class minh họa. `volatile` thiết lập semantics memory visibility/ordering của Java Memory Model; worker có thể quan sát thay đổi flag đúng theo quan hệ **happens-before** phù hợp khi đọc volatile. Nếu chỉ dùng field thường không đồng bộ, có thể không có bảo đảm visibility cần thiết.

Tuy nhiên `volatile` **không đánh thức** một thread đang block trong `CountDownLatch.await()` hoặc `BlockingQueue.take()`. Nếu cần cancellation trong lúc chờ:

~~~java
stopRequested = true;
worker.interrupt();
~~~

Đây là mảnh code minh họa; phải có policy rõ để một nguồn stop request và interrupt không mâu thuẫn. Nếu đang paused trên Condition, controller phải cập nhật `stopped=true` và `signalAll()` trong đúng lock để worker tỉnh dậy/thoát.

Phân biệt ba tầng:

1. **Visibility:** worker thấy có yêu cầu dừng.
2. **Wakeup:** worker thoát khỏi wait để kiểm tra yêu cầu.
3. **Safe completion:** worker giữ invariant và giải phóng resource.

Mỗi tầng có thể cần một cơ chế khác nhau.

## 20. Race giữa pause, resume và stop

Khi nhiều controller có thể ra lệnh cùng lúc, phải xác định thứ tự và ưu tiên:

- `pause()` trong lúc worker đang commit chỉ **yêu cầu pause ở safe point tiếp theo**; không cắt ngang operation.
- `resume()` đến trước `await()` phải được nhớ bằng predicate `paused=false`, không dựa vào một signal không lưu.
- `stop()` trong lúc worker đang paused phải đặt `stopped=true` và `signalAll()` để worker thoát.
- `resume()` đến **sau stop** không được xóa `stopped=true`; task không được “hồi sinh” do tín hiệu resume.
- Nếu hai controller cùng pause/resume, lock điều khiển xác định thứ tự các phép thay state. Muốn guarantee thêm fairness/acknowledgement phải thiết kế riêng.

Nếu API cần “pause xong mọi worker đã thực sự đứng yên”, không thể chỉ dùng request flag. Cần worker gửi **acknowledgement** khi đã tới safe point và không giữ business lock. Có thể dùng latch/Condition riêng để controller chờ xác nhận với timeout.

## 21. Deadlock, starvation và task không hợp tác

Không nên dùng stop cũ để xử lý một thread bị kẹt. Hãy chẩn đoán:

- **Deadlock:** A giữ L1 chờ L2, B giữ L2 chờ L1; giải pháp là lock ordering, ownership hoặc cấu trúc đồng bộ khác.
- **Thread pool starvation:** tất cả worker chờ những task đang nằm trong queue của chính pool; phải sửa đồ thị phụ thuộc và capacity.
- **Blocking I/O:** dùng timeout và resource-specific cancellation/close.
- **Missed signal:** waiter ngủ sau khi signal đã xảy ra; phải lưu predicate và kiểm tra dưới cùng lock/Condition.
- **Busy loop:** kiểm tra interrupt hoặc flag tại safe points.
- **Long critical section:** đưa tính toán thuần/I/O ra ngoài lock nhưng giữ validation/commit nguyên tử.
- **Không tin cậy hoặc cố ý không hợp tác:** dùng process/container isolation và quản lý process cấp cao khi cần cưỡng chế.

Một thread `WAITING` trong dump không tự chứng minh lỗi; có thể nó đang chờ đúng điều kiện. Một thread `BLOCKED` chờ monitor cũng không tự là deadlock. Cần biết **lock owner, predicate, ai có thể signal, và dependency graph**.

## 22. Testing an toàn thay vì gọi API cũ

Kiểm thử cancellation nên tạo **interleaving xác định** chứ không dựa vào một số millisecond ngẫu nhiên:

1. **Interrupt trước khi worker vào await.** Dùng latch cho biết worker đã đến mốc; gửi interrupt và assert worker thoát.
2. **Interrupt sau khi worker vào await.** Giữ worker chờ trên interruptible API, gửi interrupt rồi join.
3. **Pause trước resume sớm.** Gọi `pause` rồi `resume` trước khi worker start; worker phải không bị kẹt.
4. **Stop khi paused.** Worker phải thoát kể cả khi stop tới trước/đúng lúc chờ Condition.
5. **Invariant sau cancellation.** Chèn cancellation request ngay sau một transaction logic và kiểm tra snapshot; không ngắt bằng `Thread.stop`.
6. **Exception safety.** Gây overflow/validation failure trước commit; assert không có partial mutation.
7. **Future cancellation.** Assert `Future.isCancelled()` và kiểm tra task cooperation/lifecycle nếu cần.
8. **Timeout.** Dùng `join(timeout)` hoặc Future with timeout, kiểm tra kết quả và cleanup trong `finally` để không leak non-daemon threads.
9. **Không nuốt interrupt.** Test đường catch và verify task rời loop đúng policy.
10. **JDK compatibility.** Dò code cũ gọi `stop/suspend/resume` và test nâng cấp runtime; không dùng chúng trong application logic.

Một test pass không chứng minh mọi interleaving đều đúng. Review theo invariant, lock ownership, happens-before, interruption contract và safe points vẫn cần thiết.

## 23. Những ngộ nhận thường gặp

| Ngộ nhận | Sự thật |
| --- | --- |
| “`Thread.stop()` chỉ yêu cầu thread tự dừng.” | Trên JDK 17, nó từng ép `ThreadDeath`; từ JDK 20 luôn ném UOE. |
| “Đã `synchronized` thì stop không thể phá dữ liệu.” | Stop lịch sử có thể unwind và nhả monitor khi dữ liệu còn dở dang. |
| “`finally` chắc chắn rollback hết.” | Finally giúp cleanup theo code đã viết, không tự khôi phục mọi invariant/external side effect. |
| “`suspend()` nhả lock khi pause.” | Không theo hành vi cũ; đó chính là rủi ro deadlock. |
| “`resume()` được ghi nhớ cho một lần suspend sau.” | Không có predicate/state bảo đảm như protocol pause hợp tác. |
| “`interrupt()` là stop ngay.” | Không; đó là tín hiệu. Worker/API blocking cần hợp tác. |
| “Một vòng CPU bất tận tự thoát khi interrupt.” | Không nếu không kiểm tra status/cancel flag. |
| “Chờ `synchronized` sẽ ném InterruptedException.” | Intrinsic monitor acquisition không interruptible kiểu `lockInterruptibly`. |
| “Future cancelled nghĩa task đã cleanup xong.” | Không nhất thiết; future state và user code lifecycle khác nhau. |
| “Gọi `pause()` trả về tức worker đã đứng yên.” | Không; cần acknowledgement ở safe point khi hợp đồng yêu cầu. |
| “`Condition.await()` nhả mọi lock của thread.” | Chỉ nhả lock liên kết, không nhả monitor/lock khác. |
| “Timeout trong `join()` sẽ terminate worker.” | Không; nó chỉ giới hạn thời gian caller chờ. |
| “Dùng virtual threads thì có thể dùng stop/suspend an toàn.” | Không; vẫn cần cooperative lifecycle và invariant. |

## 24. Checklist thiết kế task có thể hủy

- [ ] Thread/task **owner** được xác định; không tự can thiệp worker của executor.
- [ ] Yêu cầu hủy được truyền bằng interrupt, flag được publish đúng hoặc Future cancel.
- [ ] Worker có **safe points** trước/sau mỗi đơn vị công việc.
- [ ] Không check cancel giữa hai bước thuộc cùng invariant mà không rollback.
- [ ] Các phép tính có thể throw được thực hiện trước commit khi có thể.
- [ ] `InterruptedException` được propagate hoặc restore và rời task an toàn.
- [ ] Blocking operations có timeout/cancellation/close policy phù hợp.
- [ ] Pause/resume lưu predicate dưới lock; `await` dùng while.
- [ ] Worker không pause hoặc chờ completion khi còn giữ lock nghiệp vụ cần cho tiến triển.
- [ ] Stop khi paused làm signalAll và không cho resume hồi sinh task.
- [ ] Nếu cần pause acknowledgement, có tín hiệu xác nhận worker đã tới safe point.
- [ ] Caller phân biệt cancellation requested, task completed và executor terminated.
- [ ] Tests kiểm tra interrupt trước/sau await, cancelled while paused và invariant.
- [ ] Code không còn dùng `Thread.stop()`, `suspend()`, `resume()` để điều khiển thread.
- [ ] Phiên bản JDK được ghi rõ khi giải thích hành vi deprecated/UOE.

## 25. Câu hỏi tự kiểm tra

**1.** Vì sao `Thread.stop()` trên JDK 17 có thể làm hỏng một object dùng synchronized?  
**Đáp:** `ThreadDeath` bất đồng bộ có thể khiến thread nhả monitor khi mới ghi một nửa state; thread khác sau đó đọc state sai.

**2.** Từ JDK 20, ba method stop, suspend và resume còn thực hiện chức năng cũ không?  
**Đáp:** Không. Chúng ném `UnsupportedOperationException`.

**3.** Vì sao suspend một thread đang giữ monitor dẫn tới deadlock?  
**Đáp:** Holder đứng yên nhưng không nhả monitor; controller có thể cần chính monitor đó trước khi resume, tạo vòng chờ.

**4.** `Thread.interrupt()` có trực tiếp giết thread đang tính CPU không?  
**Đáp:** Không. Worker cần kiểm tra status/flag hoặc gặp API interruptible rồi chủ động kết thúc.

**5.** Khi catch InterruptedException trong Runnable mà không thể ném tiếp, hướng thường dùng?  
**Đáp:** Restore interrupted status, cleanup và thoát theo chính sách task.

**6.** `Thread.interrupted()` khác `isInterrupted()` như thế nào?  
**Đáp:** Static method kiểm tra rồi xóa cờ current thread; instance method chỉ đọc.

**7.** Vì sao không đặt `if (interrupted) return` giữa debit và credit?  
**Đáp:** Nó có thể để invariant tổng tiền bị phá và nhả lock với state sai.

**8.** Một `pause()` request có bảo đảm worker đã PAUSED không?  
**Đáp:** Không. Worker còn có thể đang làm unit trước; cần acknowledgement khi yêu cầu xác nhận.

**9.** Resume đến trước Condition.await có thể bị bỏ lỡ không?  
**Đáp:** Không nếu thiết kế kiểm tra predicate `paused` dưới cùng lock; state đã lưu là nguồn sự thật.

**10.** Nếu stop xảy ra khi worker paused, cần làm gì?  
**Đáp:** Ghi stopped=true, signalAll dưới lock để worker thức và thoát, không chờ resume.

**11.** Future.cancel(true) trả true có nghĩa task đã hoàn tất cleanup không?  
**Đáp:** Không. Cancellation flag của future và completion của user code là hai điều khác nhau.

**12.** Khi worker bị kẹt ở I/O không phản ứng interrupt, giải pháp tổng quát là gì?  
**Đáp:** Không có mẹo Thread chung; dùng timeout/đóng resource/cô lập process theo API và failure model.

**13.** Dùng `Thread.sleep` trong `synchronized` có nhả monitor không?  
**Đáp:** Không. Sleep vẫn giữ monitor, có thể chặn contender.

**14.** Vì sao một test chỉ dựa vào sleep để “đợi cancellation” không đáng tin?  
**Đáp:** Sleep không bảo đảm trạng thái worker hay happens-before; cần latch, join/Future và assert completion.

**15.** Khi nào nên thay code dùng stop bằng một state machine?  
**Đáp:** Khi vòng đời có pause/resume/stop, nhiều worker hoặc cleanup phức tạp; state machine giúp chỉ rõ các transition/safe points.

**16.** Điều quan trọng nhất khi thay `Thread.stop()` là gì?  
**Đáp:** Bảo vệ invariant và chọn ranh giới commit/cleanup hợp lệ, không chỉ đổi tên API.

**Ghi nhớ:** Cưỡng bức dừng hoặc đóng băng một thread ở vị trí bất kỳ không cho phép bảo đảm các monitor và trạng thái nghiệp vụ còn an toàn. `Thread.stop()` lịch sử có thể nhả monitor khi state chưa nhất quán; `suspend()/resume()` lịch sử có thể deadlock vì lock không được nhả. Từ JDK 20, cả ba ném `UnsupportedOperationException`. Hướng thiết kế đúng là **cooperative cancellation bằng interrupt/flag/Future**, **pause/resume theo predicate tại safe point**, **transaction commit/cleanup rõ ràng** và **xác nhận kết thúc**.