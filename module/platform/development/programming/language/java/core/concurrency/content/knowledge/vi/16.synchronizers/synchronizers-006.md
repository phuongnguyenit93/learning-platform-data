# Các thao tác timeout và interruption trong Java Synchronizers

## 1. Vì sao các synchronizer phải có timeout và interruption?

Khi nhiều thread phối hợp bằng `CountDownLatch`, `CyclicBarrier`, `Semaphore`, `Phaser` hoặc `Exchanger`, một thread thường cần **đợi** thread khác, chờ đủ participant, chờ tài nguyên hay chờ một phase hoàn tất. Vấn đề là: một partner có thể bị lỗi, không được schedule, không bao giờ count down hoặc không bao giờ trả lại permit.

Nếu chờ **vô thời hạn**, ứng dụng có thể bị treo. Nếu một request đã hết hiệu lực mà worker vẫn tiếp tục chờ, ta lãng phí thread và tài nguyên. Hai khả năng then chốt của Java concurrency là:

- **Timeout:** chờ tối đa một khoảng thời gian (hoặc tới deadline của một operation) và nhận kết quả/exception tương ứng khi chưa đạt điều kiện.
- **Interruption:** một thread khác gọi `Thread.interrupt()` để **yêu cầu** thread đang chờ hủy công việc. Đây là tín hiệu hợp tác, **không phải dừng cưỡng bức**.

**Điều rất quan trọng:** cùng là “hết thời gian chờ”, nhưng **mỗi synchronizer có hợp đồng khác nhau**. Ví dụ:
- `CountDownLatch.await(timeout, unit)` trả **false** nếu chưa đếm về 0.
- `Semaphore.tryAcquire(timeout, unit)` trả **false** nếu không lấy được permit.
- `CyclicBarrier.await(timeout, unit)` ném **TimeoutException** và **làm hỏng barrier của generation hiện tại**.
- `Phaser.awaitAdvanceInterruptibly(phase, timeout, unit)` ném **TimeoutException**, nhưng **không tự thay đổi trạng thái của Phaser**.
- `Exchanger.exchange(value, timeout, unit)` ném **TimeoutException** nếu chưa có partner.

Không thể dùng chung một catch/return policy cho cả năm API mà không xét những hậu quả này.

### Mục tiêu sau bài học

1. Nắm chính xác API timeout/interruption của các synchronizers Java SE.
2. Phân biệt **false/null**, **TimeoutException**, **InterruptedException** và **BrokenBarrierException**.
3. Biết khi nào timeout/interrupt chỉ ảnh hưởng thread đang chờ và khi nào **lan sang các thread khác**.
4. Dùng `finally` và biến sở hữu permit để tránh **release sai** khi acquire chưa thành công.
5. Hiểu `Thread.interrupted()` xóa cờ trong khi `isInterrupted()` không xóa; biết lúc nào restore bằng `Thread.currentThread().interrupt()`.
6. Xây cancellation và deadline nhất quán, không tạo một timeout mới đầy đủ cho từng bước.
7. Viết Java 17+ runnable demos có output dự đoán được, không dựa `sleep()` để “ép” scheduler.
8. Biết điều kiện khôi phục `CyclicBarrier`, xử lý party rời đi ở `Phaser` và tránh wait-for cycles.

**Phạm vi:** Java concurrency nói chung trong `java.util.concurrent`; không phụ thuộc framework.

## 2. Timeout, interruption và hoàn tất bình thường: ba con đường

Giả sử một thread cần chờ resource hoặc một nhóm workers:

~~~text
               bắt đầu chờ
                    |
          +---------+----------+
          |         |          |
    Điều kiện đạt  timeout   bị interrupt
          |         |          |
    thành công     false/      InterruptedException
                  Timeout...    (nếu API hỗ trợ)
          |         |          |
       dùng kết     fallback   propagate hoặc
       quả đúng     /cleanup   restore+thoát
~~~

**Completion:** điều kiện thực sự đã đạt, có thể tiếp tục phần việc kế tiếp.

**Timeout:** chưa đạt điều kiện trong thời gian cho phép. Tùy API, caller nhận boolean false hoặc một `TimeoutException`; timeout không chứng minh partner đã chết hoặc task đã bị hủy.

**Interruption:** thread đang chờ được yêu cầu hủy. Các API chờ **interruptible** có thể ném `InterruptedException` và thường **clear interrupted status khi ném** theo contract cụ thể. Caller cần có chính sách tiếp theo.

Không phải mọi API “chờ” đều interruptible. Ví dụ `Semaphore.acquireUninterruptibly()` chủ động bỏ qua interrupt trong pha chờ và sẽ bảo tồn trạng thái interrupt sau khi cuối cùng lấy được permit; `Phaser.awaitAdvance(phase)` là **non-interruptible**. Vì vậy nếu muốn hủy có deadline, phải chọn đúng overload ngay từ đầu.

## 3. Bảng nhanh: API nào trả false, API nào ném exception?

| Synchronizer | Chờ không timeout | Chờ có timeout | Khi timeout | Khi bị interrupt |
|---|---|---|---|---|
| `CountDownLatch` | `await()` | `await(long, TimeUnit)` | Trả `false` nếu count chưa về 0 | `InterruptedException` |
| `CyclicBarrier` | `await()` | `await(long, TimeUnit)` | `TimeoutException`, barrier bị broken | `InterruptedException`; có thể làm barrier broken và khiến waiter khác nhận `BrokenBarrierException` |
| `Semaphore` | `acquire()` | `tryAcquire(long, TimeUnit)` | Trả `false` nếu chưa có permit | `InterruptedException` |
| `Phaser` | `awaitAdvance(int)` (non-interruptible) | `awaitAdvanceInterruptibly(int, long, TimeUnit)` | `TimeoutException`; không tự break phaser | Bản interruptible: `InterruptedException`; phaser vẫn giữ state |
| `Exchanger<V>` | `exchange(V)` | `exchange(V, long, TimeUnit)` | `TimeoutException` nếu chưa ghép được với partner | `InterruptedException` |

**Các giá trị cần phân biệt:** `await(timeout)` của CountDownLatch trả boolean; `await(timeout)` của CyclicBarrier trả **int arrival index khi thành công**, và ném exception khi timeout. Không có một kiểu trả về timeout chung cho mọi synchronizer.

Các overload đã liệt kê thuộc Java SE 17. Một số class có thêm variants như `Semaphore.tryAcquire()` không chờ hoặc `Semaphore.acquireUninterruptibly()`, cần đọc contract từng method.

## 4. CountDownLatch: chờ một lần, timeout không “phá” latch

`CountDownLatch` có một count khởi tạo. Các thread gọi `countDown()` để giảm count; khi count về 0, tất cả waiters được giải phóng. **Count không reset được.**

Hai API:

~~~java
latch.await();
boolean ready = latch.await(500, TimeUnit.MILLISECONDS);
~~~

- `await()`: chờ cho tới count=0, hoặc ném `InterruptedException`.
- `await(timeout, unit)`: trả `true` nếu count về 0 trước khi hết thời gian; trả `false` nếu hết hạn khi count vẫn lớn hơn 0.
- Khi timeout, **count không tự giảm**, latch không bị broken và những waiter khác có thể tiếp tục đợi.
- Nếu lúc gọi count đã bằng 0, timed await trả true ngay.
- Nếu thời gian <= 0 và count chưa về 0, timed await trả false ngay; không chờ.
- Nếu thread đang chờ bị interrupt, method ném InterruptedException và clear flag theo contract; count **không đổi chỉ vì interruption**.
- `countDown()` khi count đã về 0 không làm count âm.

### Ví dụ thực hành: chờ công việc hoàn tất nhưng có thời hạn

~~~java
CountDownLatch completed = new CountDownLatch(3);
// Workers đảm bảo gọi completed.countDown() khi công việc tương ứng xong.
boolean allDone = completed.await(2, TimeUnit.SECONDS);
if (!allDone) {
    reportIncomplete(completed.getCount());
}
~~~

Đây là đoạn method minh họa; `reportIncomplete()` do ứng dụng định nghĩa. **Điều kiện quan trọng:** workers cần gọi `countDown()` ở đúng điểm hoàn tất, thường trong `finally` để không làm caller chờ mãi khi công việc lỗi. Tuy nhiên, countDown trong finally chứng minh **task đã rời vùng xử lý**, không đồng nghĩa kết quả thành công; lỗi cần được truyền bằng cơ chế riêng.

### Ví dụ runnable 1: timeout trả false và interrupt không giảm count

Lưu **CountDownLatchTimeoutInterruptDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class CountDownLatchTimeoutInterruptDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch gate = new CountDownLatch(1);

        // Timeout bằng 0: không đo timing/scheduler.
        boolean completed = gate.await(0, TimeUnit.MILLISECONDS);

        CountDownLatch started = new CountDownLatch(1);
        AtomicBoolean interrupted = new AtomicBoolean(false);
        Thread waiter = new Thread(() -> {
            started.countDown();
            try {
                gate.await();
            } catch (InterruptedException e) {
                interrupted.set(true);
                Thread.currentThread().interrupt();
            }
        }, "latch-waiter");

        waiter.start();
        started.await();
        waiter.interrupt();
        waiter.join();

        System.out.println("completed=" + completed);
        System.out.println("interrupted=" + interrupted.get());
        System.out.println("count=" + gate.getCount());

        gate.countDown(); // một lần phát tín hiệu thực sự, sau khi test
        System.out.println("afterCountDown=" + gate.getCount());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac CountDownLatchTimeoutInterruptDemo.java
java CountDownLatchTimeoutInterruptDemo
~~~

Output trong môi trường không có external interruption:

~~~text
completed=false
interrupted=true
count=1
afterCountDown=0
~~~

**Lý do kết quả ổn định:** gate có count=1 và không thread nào countDown trước khi main in. `await(0)` trả false ngay. Waiter có thể đã vào `await()` hoặc chưa khi main gọi interrupt; trong cả hai lịch chạy, `await` phát hiện flag và ném exception. `join()` làm main chờ waiter xong. Chỉ câu `gate.countDown()` cuối mới hạ count về 0.

**Không kết luận:** “Timeout nghĩa là tác vụ producer đã dừng”. Nó chỉ nói thread caller **chưa quan sát đủ countDown trong deadline**.

## 5. CyclicBarrier: timeout của một party ảnh hưởng cả nhóm

`CyclicBarrier` dùng khi có một số lượng cố định `parties` phải cùng tới điểm đồng bộ trước khi tất cả được tiếp tục. Barrier được tái sử dụng qua nhiều **generations** nếu các lần chờ thành công.

~~~java
CyclicBarrier barrier = new CyclicBarrier(3);
int index = barrier.await(1, TimeUnit.SECONDS);
~~~

Một lần `await` thành công trả **arrival index**, không phải boolean:
- Giá trị 0 thuộc thread đến sau cùng trong generation (thread này có thể thực thi barrier action nếu có).
- Khi tất cả parties đến, barrier trip, các waiters cùng được giải phóng và generation mới có thể bắt đầu.
- Nếu một party timeout trong khi chờ, nó ném `TimeoutException` và barrier **chuyển sang broken state**.
- Những thread khác đang chờ ở generation đó thường nhận `BrokenBarrierException`.
- Nếu một party bị interrupt khi chờ, nó ném `InterruptedException`, interrupted status được clear; barrier broken và có thể khiến các waiters khác nhận BrokenBarrierException.
- `reset()` có thể đưa barrier về trạng thái ban đầu, nhưng reset đồng thời với waiting có thể gây BrokenBarrierException cho những waiter còn lại; không nên reset tùy tiện trước khi cả nhóm có protocol đồng thuận.

Đó là **all-or-none breakage**: nếu một participant không thể tiếp tục vòng phối hợp, những participant khác không bị để lại chờ một generation đã không thể hoàn thành.

### Ví dụ runnable 2: một party timeout làm barrier broken

Lưu **CyclicBarrierTimeoutDemo.java**:

~~~java
import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class CyclicBarrierTimeoutDemo {
    public static void main(String[] args) throws InterruptedException {
        CyclicBarrier barrier = new CyclicBarrier(2);
        boolean timedOut = false;
        boolean otherBroken = false;

        // Chỉ có 1 party, timeout 0: chắc chắn chưa đủ 2 parties.
        try {
            barrier.await(0, TimeUnit.MILLISECONDS);
        } catch (TimeoutException e) {
            timedOut = true;
        } catch (BrokenBarrierException e) {
            throw new AssertionError("Unexpected pre-broken barrier", e);
        }

        boolean broken = barrier.isBroken();

        // Party tiếp theo không thể hoàn thành generation đã broken.
        try {
            barrier.await();
        } catch (BrokenBarrierException e) {
            otherBroken = true;
        }

        System.out.println("timedOut=" + timedOut);
        System.out.println("broken=" + broken);
        System.out.println("otherBroken=" + otherBroken);
    }
}
~~~

Lệnh:

~~~bash
javac CyclicBarrierTimeoutDemo.java
java CyclicBarrierTimeoutDemo
~~~

Stdout:

~~~text
timedOut=true
broken=true
otherBroken=true
~~~

**Giải thích:** chưa có party thứ hai, timeout=0, `await` ném TimeoutException rồi barrier được đánh dấu broken. Lời `await()` sau đó không đợi vô hạn vì đã broken; nó ném BrokenBarrierException. Chương trình cố ý tránh dùng sleep hoặc tạo waiters không có điểm thoát.

### Phân biệt với CountDownLatch

- CountDownLatch timeout **không hỏng latch** và không thay đổi count.
- CyclicBarrier timeout **làm broken barrier**, một thay đổi có ảnh hưởng đến cả nhóm.
- CountDownLatch là **one-shot**; CyclicBarrier có thể **reuse generation** khi không bị broken (hoặc sau reset có giao thức phù hợp).
- CountDownLatch chờ những `countDown` được phát; CyclicBarrier chờ **đủ parties cùng gọi await ở một generation**.

### Nếu một worker lỗi trước khi tới barrier?

Nếu một party thoát khỏi computation **trước khi gọi await**, các party còn lại có thể chờ mãi. Timed await giúp giới hạn thời gian. Caller cần hiểu rằng việc worker không đến là một thất bại ở cấp group, không chỉ retry chính thread đã timeout. Cần propagate lỗi/cancellation và quyết định tạo barrier mới hoặc dừng generation thay vì reset không kiểm soát.

## 6. Semaphore: timeout là false, interrupt phải giữ đúng ownership

`Semaphore` quản lý một số permit. Thread cần permit để vào vùng giới hạn concurrency. Những API quan trọng:

~~~java
semaphore.acquire();
boolean acquired = semaphore.tryAcquire(500, TimeUnit.MILLISECONDS);
semaphore.acquireUninterruptibly();
boolean immediate = semaphore.tryAcquire();
~~~

- `acquire()` chờ nếu không có permit, **interruptible**.
- `tryAcquire(timeout, unit)` chờ có hạn và trả `true` nếu lấy được permit, `false` nếu hết hạn. Có thể ném `InterruptedException`.
- `tryAcquire()` không tham số thử ngay, không chờ và **có thể barge** khi fairness=true, vì không tôn trọng việc các waiter khác đã đứng chờ theo kiểu timed acquire.
- `acquireUninterruptibly()` tiếp tục cố lấy permit dù bị interrupt khi đang chờ, sau đó bảo tồn interrupted status; không dùng khi lifecycle phải phản hồi cancel ngay.
- `release()` thêm permit trở lại; **Semaphore không tự biết thread nào sở hữu permit** như mutex. Nếu release sai, availablePermits có thể tăng không đúng protocol.

### Quy tắc quan trọng: chỉ release khi thật sự acquire thành công

~~~java
boolean acquired = false;
try {
    acquired = semaphore.tryAcquire(300, TimeUnit.MILLISECONDS);
    if (!acquired) {
        handleOverload();
        return;
    }
    doWorkWithPermit();
} finally {
    if (acquired) {
        semaphore.release();
    }
}
~~~

Đây là đoạn method tích hợp; `handleOverload` và `doWorkWithPermit` do ứng dụng định nghĩa, method phải handle/throws InterruptedException.

Nếu `tryAcquire` ném InterruptedException **trước khi nhận permit**, `acquired` vẫn false; finally không release. Nếu timeout trả false, cũng không release. Nếu true, dù work lỗi, finally release đúng một permit.

**Không viết:**

~~~java
try {
    semaphore.acquire();
    process();
} finally {
    semaphore.release(); // SAI nếu acquire đã ném InterruptedException
}
~~~

Đoạn sai trên nằm trong method có `throws InterruptedException` và các biến do ứng dụng cung cấp. Khi acquire thất bại vì interrupt, release sẽ tạo **permit không thuộc lần acquire đó**, phá giới hạn concurrency. Đối với acquire() không trả boolean, có thể đặt `acquire()` **trước** try/finally để chỉ vào finally sau khi acquire thành công.

### Ví dụ runnable 3: interrupt trước khi lấy permit

Lưu **SemaphoreTimeoutInterruptDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class SemaphoreTimeoutInterruptDemo {
    public static void main(String[] args) throws InterruptedException {
        Semaphore permits = new Semaphore(1, true);
        permits.acquire(); // main giữ permit duy nhất
        boolean timedAcquired =
                permits.tryAcquire(0, TimeUnit.MILLISECONDS);

        CountDownLatch started = new CountDownLatch(1);
        AtomicBoolean interrupted = new AtomicBoolean(false);
        Thread waiter = new Thread(() -> {
            started.countDown();
            try {
                permits.acquire();
                try {
                    throw new AssertionError("No permit should be available");
                } finally {
                    permits.release();
                }
            } catch (InterruptedException e) {
                interrupted.set(true);
                Thread.currentThread().interrupt();
            }
        }, "semaphore-waiter");

        try {
            waiter.start();
            started.await();
            waiter.interrupt();
            waiter.join();

            System.out.println("timedAcquired=" + timedAcquired);
            System.out.println("interrupted=" + interrupted.get());
            System.out.println("permitsWhileOwned=" +
                    permits.availablePermits());
        } finally {
            permits.release(); // main trả lại permit mình đã lấy
        }

        System.out.println("permitsAfterRelease=" +
                permits.availablePermits());
    }
}
~~~

Chạy:

~~~bash
javac SemaphoreTimeoutInterruptDemo.java
java SemaphoreTimeoutInterruptDemo
~~~

Stdout (không có interruption từ bên ngoài):

~~~text
timedAcquired=false
interrupted=true
permitsWhileOwned=0
permitsAfterRelease=1
~~~

**Lập luận:** main giữ permit duy nhất, nên timed tryAcquire(0) không thể thành công. Thread waiter báo started rồi thử acquire, nhưng main chưa release permit khi gửi interrupt; dù signal đến trước hoặc trong lúc acquire chờ, method ném InterruptedException. Main join waiter trước khi in. Semaphore count vẫn 0 cho tới finally của main và bằng 1 sau release.

**Lưu ý:** Phần trong waiter có một `AssertionError` cố ý đánh dấu đường thành công không mong muốn. Nó không chạy trong điều kiện ví dụ đã mô tả. Trong production, thay bằng logic nghiệp vụ thật và quản lý ownership trong finally.

## 7. Phaser: timeout/interrupt không tự phá trạng thái phaser

`Phaser` phối hợp nhiều **registered parties** qua các **phases**, cho phép register/deregister linh hoạt hơn CyclicBarrier. Một party gọi `arrive()` để báo đã tới phase hiện tại; `arriveAndAwaitAdvance()` báo tới và đợi phase chuyển. Phaser có thể bị terminate chủ động bằng `forceTermination()` hoặc theo lifecycle.

Các phương thức cần phân biệt:

| API | Đã báo arrive? | Có interruptible? | Có timeout? |
|---|---|---|---|
| `arrive()` | Có | Không phải thao tác chờ | Không |
| `arriveAndDeregister()` | Có và rời khỏi group | Không phải thao tác chờ | Không |
| `arriveAndAwaitAdvance()` | Có rồi chờ advance | **Non-interruptible** | Không |
| `awaitAdvance(phase)` | **Không** tự arrive; chỉ đợi phase đổi | **Non-interruptible** | Không |
| `awaitAdvanceInterruptibly(phase)` | Không tự arrive | Có | Không |
| `awaitAdvanceInterruptibly(phase, timeout, unit)` | Không tự arrive | Có | Có |

**Hai lỗi đặc biệt nguy hiểm:**

1. Gọi `awaitAdvanceInterruptibly(phase)` mà tưởng nó tự báo arrive; nếu không ai gọi `arrive`, phase có thể không bao giờ chuyển.
2. Một party đã `arrive()` rồi timeout khi đợi phase tiếp theo, sau đó lập tức gọi `arriveAndDeregister()` cho **cùng phase** một cách tùy tiện. Việc arrive thêm lần nữa trong cùng phase không phải lối dọn dẹp chung an toàn. Phải xây protocol quản lý registration/termination theo vòng đời thực tế.

### Khác biệt lớn so với CyclicBarrier

Theo Javadoc `Phaser`, **interruption và timeout khi đợi bằng các phương thức interruptible/timed không tự làm thay đổi state của phaser**. Không có mô hình barrier broken tự động tương đương CyclicBarrier.

Hệ quả:
- Caller có thể nhận TimeoutException, nhưng `getPhase()` vẫn giữ nguyên.
- Các registered parties khác vẫn có thể đang chờ phase này.
- Nếu quyết định hủy cả group, cần một coordinator xử lý `forceTermination()` hoặc deregistration/protocol khác đúng thời điểm.
- `forceTermination()` có thể khiến các waiters được giải phóng với **phase âm** báo termination; code phải kiểm tra kết quả thay vì mặc định đã tới phase kế tiếp thành công.
- `awaitAdvance(phase)` và `arriveAndAwaitAdvance()` **không chấm dứt việc chờ chỉ vì interrupt**, nên không dùng khi yêu cầu phản hồi cancel ngay mà không có đường termination khác.

### Ví dụ runnable 4: Phaser timeout không bị broken

Lưu **PhaserTimeoutDemo.java**:

~~~java
import java.util.concurrent.Phaser;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class PhaserTimeoutDemo {
    public static void main(String[] args) throws InterruptedException {
        Phaser phaser = new Phaser(2);
        int originalPhase = phaser.getPhase();

        boolean timedOut = false;
        try {
            // Không party nào arrive, phase chưa thể advance.
            phaser.awaitAdvanceInterruptibly(
                    originalPhase, 0, TimeUnit.MILLISECONDS);
        } catch (TimeoutException e) {
            timedOut = true;
        }

        System.out.println("timedOut=" + timedOut);
        System.out.println("samePhase=" +
                (phaser.getPhase() == originalPhase));
        System.out.println("terminated=" + phaser.isTerminated());

        phaser.forceTermination(); // chủ động đóng group trong ví dụ
        System.out.println("afterForceTermination=" +
                phaser.isTerminated());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac PhaserTimeoutDemo.java
java PhaserTimeoutDemo
~~~

Output:

~~~text
timedOut=true
samePhase=true
terminated=false
afterForceTermination=true
~~~

**Vì sao?** Phaser có 2 registered parties, chưa ai gọi arrive. Bản timed await với timeout=0 ném TimeoutException, **không sửa phase hay tự terminate**. Sau đó main gọi forceTermination theo quyết định chủ động. Đây là khác biệt cốt lõi với `CyclicBarrier.await(0, unit)` vốn làm broken barrier khi timeout.

### Timeout khi đang là một registered party

Khi một registered party timeout sau khi đã arrive, muốn cleanup cần biết:
- Party đó đã arrive ở phase nào?
- Có task nào đang chờ nó ở phase tiếp theo?
- Group sẽ **fail fast toàn bộ** hay có thể tiếp tục với ít parties hơn?
- Ai được phép deregister/forceTermination?
- Có thread đang chờ bản non-interruptible không?
- Có nguy cơ một thread đến phase mới trong khi party cũ chưa rời lifecycle?

`Phaser` linh hoạt nhưng dễ mắc lỗi registration-count nếu phần dừng/hủy không được thiết kế rõ ràng. Không “cứ catch TimeoutException rồi return” nếu vẫn để những registered parties khác đợi vĩnh viễn.

## 8. Exchanger: chờ một partner, timeout ném exception

`Exchanger<V>` ghép **hai threads** để trao đổi giá trị. Mỗi thread gọi `exchange(value)` và nhận lại giá trị của partner khi hai bên gặp nhau.

~~~java
Exchanger<String> exchanger = new Exchanger<>();

String partnerValue = exchanger.exchange(
        "my-value", 500, TimeUnit.MILLISECONDS);
~~~

- Nếu có partner tương ứng kịp thời, method trả về object từ partner.
- Nếu chưa có partner trong deadline, ném `TimeoutException`.
- Nếu bị interrupt khi đang chờ, ném `InterruptedException` và clear interrupted status theo contract.
- Không có khái niệm **broken state kéo dài** như CyclicBarrier. Một lần timeout không tự biến Exchanger thành một đối tượng không thể dùng lại.
- Dù một bên timeout, bên kia có thể đến sau và phải chờ một partner mới hoặc timeout theo contract của chính nó.
- Không mặc định dữ liệu đã chuyển cho partner hay chưa nếu ứng dụng bắt/điều phối các side effects ngoài exchange; xác định điểm thành công bằng **return bình thường** từ exchange.

### Ví dụ runnable 5: exchange timeout nếu không có partner

Lưu **ExchangerTimeoutDemo.java**:

~~~java
import java.util.concurrent.Exchanger;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class ExchangerTimeoutDemo {
    public static void main(String[] args) throws InterruptedException {
        Exchanger<String> exchanger = new Exchanger<>();
        boolean timedOut = false;

        try {
            exchanger.exchange("A", 0, TimeUnit.MILLISECONDS);
        } catch (TimeoutException e) {
            timedOut = true;
        }

        System.out.println("timedOut=" + timedOut);
    }
}
~~~

Lệnh:

~~~bash
javac ExchangerTimeoutDemo.java
java ExchangerTimeoutDemo
~~~

Stdout:

~~~text
timedOut=true
~~~

Chỉ có main thread gọi exchange, không có partner; timeout=0 khiến method không chờ và ném TimeoutException. Dùng thời hạn 0 ở ví dụ giúp kiểm chứng hành vi mà không cần tạo race dựa trên sleep.

### Khi partner có thể biến mất

Một thread chờ trao đổi có thể bị bỏ lại nếu partner throw exception hoặc branch return trước khi gọi exchange. Vì vậy:
- Timed exchange thường phù hợp hơn vô hạn trong workflow có failure.
- Caller cần xử lý TimeoutException và cancellation rõ ràng.
- Không dùng Exchanger như một message queue nhiều phần tử hay broadcast primitive: mỗi lần ghép chỉ trao đổi giữa **hai participants**.
- Nếu cần nhiều producers/consumers không hẹn nhau theo cặp, `BlockingQueue` hoặc coordination abstraction khác có thể phù hợp hơn.

## 9. Interruption: xử lý thế nào để không làm mất tín hiệu?

Các thao tác interruptible như `CountDownLatch.await`, `CyclicBarrier.await`, `Semaphore.acquire`, `Phaser.awaitAdvanceInterruptibly`, `Exchanger.exchange` có thể ném `InterruptedException` khi thread bị interrupt trong lúc chờ.

### Hai phương pháp tốt

**Cách 1: Propagate checked exception khi method cho phép**

~~~java
void waitForWorkers(CountDownLatch latch)
        throws InterruptedException {
    latch.await();
}
~~~

Method trên để caller tự quyết định cancellation/fallback.

**Cách 2: Restore interrupt flag khi không ném được**

~~~java
@Override
public void run() {
    try {
        semaphore.acquire();
        try {
            doWork();
        } finally {
            semaphore.release();
        }
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        return;
    }
}
~~~

Đây là fragment trong một class có `Semaphore semaphore` và method `doWork()`. `Runnable.run()` không thể khai báo `throws InterruptedException`, nên restore flag rồi return bảo tồn ý nghĩa yêu cầu hủy cho tầng trên.

**Tránh:**

~~~java
try {
    gate.await();
} catch (InterruptedException ignored) {
    // Sai khi yêu cầu hủy cần được tôn trọng:
    // bỏ qua rồi tiếp tục vòng chờ như không có gì xảy ra.
}
~~~

Với nhiều synchronizer, `InterruptedException` được ném và interrupted status bị **clear** khi ném. Nếu nuốt exception, yêu cầu hủy có thể hoàn toàn bị mất.

### isInterrupted() vs Thread.interrupted()

| API | Kiểm tra thread nào? | Có clear interrupted status? |
|---|---|---|
| `thread.isInterrupted()` | Thread được tham chiếu | Không |
| `Thread.currentThread().isInterrupted()` | Current thread | Không |
| `Thread.interrupted()` (static) | **Current thread** | **Có** |
| `thread.interrupt()` | Gửi tín hiệu interrupt tới thread | Không phải kiểm tra/clear flag |

Đừng gọi `Thread.interrupted()` trong polling rồi vô tình tiếp tục công việc mà không xử lý giá trị true: nó clear flag nên những lần kiểm tra sau có thể không còn thấy yêu cầu hủy.

### Interrupt khác timeout

- Timeout = điều kiện chưa đạt trong khoảng thời gian.
- Interruption = bên điều phối/caller khác yêu cầu hủy.
- Timeout không tự set interrupted status.
- Interruption không phải một countdown/timer và không có bảo đảm dừng ngay đối với code không kiểm tra.
- Với CyclicBarrier, **cả hai** có thể làm broken barrier; với Phaser, việc wait bị interrupt/timeout **không tự thay đổi phaser**.
- Trong chương trình thực tế, những trạng thái này cần metrics/logs khác nhau.

## 10. Quy tắc thời gian: timeout của từng bước không phải deadline tổng

Giả sử workflow có ba bước chờ:
1. Chờ một permit tối đa 300ms.
2. Chờ latch tối đa 300ms.
3. Chờ partner Exchanger tối đa 300ms.

Nếu mỗi bước được cấp **300ms mới tinh**, workflow có thể đợi gần **900ms** chưa kể thời gian xử lý. Nếu SLA tổng chỉ 300ms thì code không đúng.

Giải pháp: tạo **deadline bằng đồng hồ đơn điệu** (`System.nanoTime()`), rồi ở mỗi bước tính **remaining budget**.

~~~java
long budget = TimeUnit.MILLISECONDS.toNanos(300);
long deadline = System.nanoTime() + budget;

long remaining = deadline - System.nanoTime();
if (remaining <= 0L) {
    throw new TimeoutException("No time left");
}
boolean acquired = semaphore.tryAcquire(
        remaining, TimeUnit.NANOSECONDS);
if (!acquired) {
    throw new TimeoutException("Permit wait expired");
}
~~~

Đây là đoạn minh họa trong method có `semaphore`, imports và exception handling. Với deadline cực dài có thể cần xử lý overflow, nhưng với ngân sách ngắn hợp lệ thì phép trừ trên monotonic nanoTime là cách thường dùng. Khi đã acquire thành công, phải release trong `finally`.

**Lưu ý:** Nếu ba bước không thể bị hủy ngay khi timeout bởi một remote I/O blocking không hỗ trợ interrupt, timeout của synchronizer không biến thành hard deadline của toàn hệ thống. Phải cấu hình deadline ở từng dependency.

### Khác biệt giữa timeout và absolute timestamp

`System.currentTimeMillis()` là wall-clock và có thể đổi do điều chỉnh đồng hồ. `System.nanoTime()` dùng để đo **elapsed time** và so sánh các mốc tương đối trong cùng JVM; không dùng giá trị đó làm Unix timestamp. Các timed APIs dùng `TimeUnit` để biểu đạt đơn vị thời gian rõ ràng.

## 11. Hủy một member: ảnh hưởng “toàn nhóm” rất khác nhau

| Primitive | Nếu một thread timeout | Những thread khác |
|---|---|---|
| CountDownLatch | Waiter nhận false, latch count không đổi | Có thể tiếp tục chờ countDown; không bị đánh thức chỉ vì waiter khác timeout |
| Semaphore | Waiter không lấy permit, trả false | Các threads khác vẫn chờ/tìm permit theo chính sách |
| CyclicBarrier | Barrier bị broken | Những waiter cùng generation nhận BrokenBarrierException; các lần await sau cũng thất bại tới khi reset/đổi barrier |
| Phaser | Timed await thất bại, state phaser không tự đổi | Các parties khác có thể vẫn chờ; coordinator phải quyết định deregister/terminate |
| Exchanger | Một trao đổi chưa ghép được bị timeout | Partner tới sau có thể phải tiếp tục chờ/tự timeout; không có broken state lâu dài |

**Đừng coi timeout là “không còn ai cần cleanup”.** Nếu waiter thoát nhưng một resource hoặc một group đã được đăng ký, hãy xác định ownership và giao thức đóng.

### Lưu ý memory visibility

Các synchronizers cũng có memory consistency effects:
- `CountDownLatch`: actions trước `countDown` happen-before actions sau một `await` trả thành công ở thread khác.
- `CyclicBarrier`: actions trước `await` happen-before barrier action và actions sau `await` **thành công** ở party khác theo Javadoc.
- `Semaphore`: actions trước `release` happen-before actions sau một `acquire` thành công ở thread khác.
- `Exchanger`: các actions trước `exchange` của mỗi bên happen-before actions sau một cặp trao đổi thành công ở bên kia.

**Không tự áp dụng kết luận visibility của một lần đồng bộ thành công cho một lần timeout.** Ví dụ `latch.await(timeout)==false` không chứng minh tất cả workers đã publish kết quả; `BrokenBarrierException` không phải một completed generation bình thường. Nếu cần dữ liệu hoàn chỉnh, phải có protocol công bố kết quả hợp lệ và chỉ đọc sau điểm đồng bộ thích hợp.

## 12. Khôi phục sau timeout và tránh deadlock

Một lần timeout chỉ nói **điều kiện chưa đạt đúng thời hạn**. Sau đó bạn cần quyết định:
- Có tiếp tục với **partial result** không?
- Có retry không? Nếu có, còn bao nhiêu ngân sách và có làm tăng tải không?
- Có hủy toàn bộ nhóm không? Ai gửi tín hiệu?
- Có child/participant nào còn chạy không?
- Có permit/lock/resource nào phải release?
- Với Phaser, ai deregister hoặc forceTermination?
- Với CyclicBarrier, ai được phép reset/khởi tạo generation mới?
- Có nên log nguyên nhân timeout/interrupt riêng với task failure?

### Một vòng đợi gây deadlock điển hình

~~~text
Thread A: giữ permit P cuối cùng
          rồi đợi latch L về 0

Thread B: cần permit P trước khi countDown L

A đợi B countDown L.
B đợi A release P.
=> wait-for cycle; timeout chỉ giúp A thoát nếu A dùng timed await
   và release P trong finally.
~~~

Không sửa vấn đề bằng cách tăng timeout vô hạn. Cách đúng là **không giữ tài nguyên mà thread khác cần khi chờ completion của chính nó**, hoặc tổ chức lại lifecycle/ownership.

### Những lỗi phá invariant khi recover

- `Semaphore.release()` khi chưa acquire thành công tạo permit thừa.
- `Phaser.arriveAndDeregister()` sau một lần arrive đã được tính cho phase hiện tại mà không xét trạng thái phase có thể báo arrive hai lần.
- `CyclicBarrier.reset()` trong khi các waiters còn tham gia làm họ nhận BrokenBarrierException, không phải “cứu” generation đã lỗi một cách trong suốt.
- Nuốt InterruptedException khiến group tưởng cancellation đã được xử lý nhưng worker tiếp tục chờ.
- Retry sau timeout với full budget mới có thể vượt quá deadline chung.
- Một party nhận TimeoutException rồi tiếp tục đọc shared results như thể mọi bên đã đồng bộ xong.

## 13. Các phép chờ liên quan nhưng không đồng nghĩa

Các API Java SE liên quan:

| API | Khi hết hạn | Interruption | Liên hệ |
|---|---|---|---|
| `BlockingQueue.offer(e, timeout, unit)` | Trả false | InterruptedException | Chờ slot để đưa item vào queue |
| `BlockingQueue.poll(timeout, unit)` | Trả null | InterruptedException | Chờ item có sẵn |
| `Condition.await(timeout, unit)` | Trả boolean | InterruptedException | Có spurious wakeup; luôn kiểm tra predicate dưới lock |
| `ReentrantLock.tryLock(timeout, unit)` | Trả false | InterruptedException | Chờ lock, chỉ unlock nếu đã acquire |
| `Future.get(timeout, unit)` | TimeoutException | InterruptedException | Chờ Future; timeout không tự cancel task |
| `Thread.join(timeout)` | Trả bình thường kể cả do timeout | InterruptedException | Cần kiểm tra `thread.isAlive()` để biết thread còn sống |
| `LockSupport.parkNanos` | Trở về sau park/spurious wakeup/interrupt | Không ném InterruptedException | Phải kiểm tra predicate/flag, không là synchronizer completion |
| `Phaser.awaitAdvance(phase)` | Không có timeout | **Không ném** InterruptedException | Phải có đường termination/advance nếu cần dừng |

Đừng gộp “method trả bình thường” với “điều kiện đã đạt” nếu API không báo riêng kết quả. Ví dụ `Thread.join(timeout)` có thể trở về vì hết timeout; caller cần kiểm tra `isAlive()`. Với `LockSupport.parkNanos`, spurious return là hợp lệ nên luôn dùng một condition/predicate rõ ràng.

## 14. Lỗi thường gặp khi dùng timeout và interruption

**Lỗi 1 — Bắt TimeoutException cho CountDownLatch.await(timeout).** API trả **boolean false**, không ném TimeoutException.

**Lỗi 2 — Nghĩ CyclicBarrier.await(timeout) trả false.** Nó ném TimeoutException và làm barrier broken.

**Lỗi 3 — Nghĩ Phaser timeout tự làm mọi parties rời group.** State phaser không đổi; cần lifecycle/recovery rõ.

**Lỗi 4 — Đợi Phaser bằng awaitAdvance() rồi chờ interrupt phá đợi.** Đây là non-interruptible method.

**Lỗi 5 — Gọi awaitAdvanceInterruptibly() mà quên arrive() theo protocol.** Method chỉ đợi phase, không tự báo party đã tới.

**Lỗi 6 — Release semaphore permit trong finally dù chưa acquire.** Có thể tạo thêm permit và phá giới hạn concurrency.

**Lỗi 7 — Bắt InterruptedException rồi bỏ qua.** Nhiều API clear flag, tín hiệu cancellation bị mất.

**Lỗi 8 — Gọi Thread.interrupted() khi chỉ cần kiểm tra.** Static method clear cờ.

**Lỗi 9 — Tưởng timeout tự cancel các thread khác.** Thông thường timeout chỉ kết thúc phép chờ; riêng CyclicBarrier có cơ chế breakage của group, nhưng không giết threads.

**Lỗi 10 — Tự reset barrier khi có nhiều callers đang chờ mà thiếu protocol.** Có thể làm generation mới/old lẫn lộn, hoặc gây BrokenBarrierException ngoài dự kiến.

**Lỗi 11 — Dùng Exchanger không timeout khi partner có thể mất.** Một thread có thể chờ mãi.

**Lỗi 12 — Gộp timeout của mỗi bước thành deadline tổng mà không trừ thời gian đã tiêu.** Có thể vượt SLA.

**Lỗi 13 — Dùng wall clock để đo elapsed và không xử lý thay đổi thời gian hệ thống.** Ưu tiên System.nanoTime với budget hợp lý.

**Lỗi 14 — Coi await(timeout)==false là mọi worker thất bại.** Nó chỉ nói count chưa về zero trong thời hạn; outcome từng worker cần theo dõi riêng.

**Lỗi 15 — Nghĩ fair Semaphore.tryAcquire() luôn tôn trọng thứ tự chờ.** Bản không tham số có thể barging.

**Lỗi 16 — Nghĩ semaphore biết owner như ReentrantLock.** Semaphore permits không gắn ownership thread; release sai nguy hiểm.

**Lỗi 17 — Khi barrier broken vẫn đọc data của generation như success.** BrokenBarrierException báo phối hợp đã thất bại, không có completed generation hợp lệ.

**Lỗi 18 — Gọi Phaser.arriveAndDeregister hai lần trong cùng phase để “sửa” timeout.** Có thể làm lệch số party/arrivals.

**Lỗi 19 — Coi timeout=0 là luôn nhận kết quả thất bại kể cả khi điều kiện đã sẵn sàng.** Nếu latch count đã 0 hoặc semaphore có permit, API có thể thành công ngay; timeout=0 chỉ bỏ phần **chờ**.

**Lỗi 20 — Dùng Thread.sleep để điều phối test.** Sleep không bảo đảm thread đang đợi ở API mong muốn; dùng latch/timeout 0/điểm kiểm tra rõ.

## 15. Checklist code review và vận hành

- [ ] Đã xác định primitive đúng: latch, barrier, permits, phases hay exchange?
- [ ] Đã đọc return type và exception của **đúng overload**?
- [ ] Timeout trả false, null hay ném TimeoutException?
- [ ] Interruption có ném InterruptedException hay method non-interruptible?
- [ ] Timeout/interrupt có ảnh hưởng trạng thái **toàn nhóm** không?
- [ ] CyclicBarrier broken có được lan lỗi tới các parties khác?
- [ ] Phaser có registration/arrival/termination protocol nếu party hủy?
- [ ] Semaphore chỉ release đúng số permits đã acquire?
- [ ] Thread caller cần propagate hay restore interrupt flag?
- [ ] Các consumer/partners bị mất có làm thread khác chờ mãi?
- [ ] Có deadline tổng với remaining budget thay vì timeout mỗi bước?
- [ ] Sau timeout có task/worker nào tiếp tục chạy và dùng tài nguyên không?
- [ ] Có log metric phân biệt completed, timed out, interrupted, broken?
- [ ] Có tránh giữ lock/permit trong lúc đợi một task cần chính resource đó?
- [ ] Test có dùng CountDownLatch hoặc timeout=0 thay vì sleep và timing assumptions?
- [ ] Khi dùng shutdownNow/cancel, đã hiểu đây là **yêu cầu hủy**?
- [ ] Có bảo đảm memory visibility trước khi dùng shared results?
- [ ] Có xác định ai sở hữu executor, barrier/phaser và cleanup?

## 16. Bài tập luyện tập có đáp án

**Câu 1.** CountDownLatch count=2, gọi `await(0, MILLISECONDS)` và chưa có countDown. Kết quả?

**Đáp án:** false, không chờ; count vẫn là 2.

**Câu 2.** CyclicBarrier có 3 parties, chỉ một party chờ rồi timeout. Hai parties khác sẽ nhận gì nếu đang chờ generation đó?

**Đáp án:** Những waiters còn lại thường nhận BrokenBarrierException, barrier broken. Cần recovery protocol; reset không tự an toàn cho mọi tình huống.

**Câu 3.** Semaphore permit=0, `tryAcquire(100, MILLISECONDS)` không có ai release. Kết quả?

**Đáp án:** false sau khi không lấy được permit trong thời hạn (trừ khi thread bị interrupt, khi đó ném InterruptedException).

**Câu 4.** Semaphore.acquire() ném InterruptedException trước khi lấy permit. Có gọi release không?

**Đáp án:** Không. Chỉ release nếu đã acquire thành công.

**Câu 5.** Phaser có 2 parties, một thread timeout trong `awaitAdvanceInterruptibly(phase, timeout, unit)`. Phaser có tự broken như CyclicBarrier không?

**Đáp án:** Không. Timeout/interrupt của phép đợi không tự thay đổi phaser state; recovery/termination cần do ứng dụng quyết định.

**Câu 6.** Gọi `awaitAdvance(phase)`, bên khác interrupt waiter. Có bắt buộc ném InterruptedException không?

**Đáp án:** Không. Đây là phiên bản non-interruptible; nếu cần phản hồi cancel khi đợi, dùng awaitAdvanceInterruptibly và protocol lifecycle phù hợp.

**Câu 7.** Exchanger chỉ có một thread gọi `exchange("A", 0, MILLISECONDS)`. Kết quả?

**Đáp án:** TimeoutException nếu không có partner, không phải false hoặc null.

**Câu 8.** Một thread bị interrupt trong lúc `CountDownLatch.await()`. Count có tự giảm không?

**Đáp án:** Không. Interrupt chỉ kết thúc phép chờ của thread đó; countDown phải được phát bởi bên chịu trách nhiệm.

**Câu 9.** Workflow có ba bước mỗi bước timeout 300ms, SLA tổng 300ms. Vấn đề?

**Đáp án:** Tổng thời gian chờ có thể gần 900ms. Phải dùng deadline chung và remaining budget.

**Câu 10.** CyclicBarrier đã broken. Gọi await tiếp tục có thể thành công bình thường mà không reset không?

**Đáp án:** Không. Await sẽ ném BrokenBarrierException cho tới khi có chính sách reset/tạo barrier mới phù hợp.

**Câu 11.** Thread.interrupted() có giống currentThread().isInterrupted() không?

**Đáp án:** Đều kiểm tra current thread nếu viết đúng, nhưng Thread.interrupted() **clear flag**, còn isInterrupted() không clear.

**Câu 12.** Timeout của Future.get(timeout) có tự hủy Future task không?

**Đáp án:** Không. Đây là timeout của caller đang chờ kết quả. Muốn hủy phải quyết định cancel theo hợp đồng Future.

## 17. Tài liệu tham khảo chính thức

- **CountDownLatch (Java SE 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html
- **CyclicBarrier (Java SE 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CyclicBarrier.html
- **Semaphore (Java SE 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html
- **Phaser (Java SE 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Phaser.html
- **Exchanger (Java SE 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Exchanger.html
- **TimeUnit (Java SE 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/TimeUnit.html
- **Thread (Java SE 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html
- **JLS 17, Threads and Locks:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html

**Tóm tắt:** Timeout và interruption cho phép **chờ có giới hạn và hủy hợp tác**, nhưng từng synchronizer có contract riêng: **latch/semaphore trả boolean false; barrier timeout ném exception và làm broken; phaser timeout ném exception nhưng không tự đổi state; exchanger timeout ném exception khi không có partner**. Xử lý đúng bao gồm deadline tổng, bảo toàn interrupted status, ownership/cleanup permit, khôi phục trạng thái nhóm và tránh vòng chờ tài nguyên.
