# Semaphore giới hạn truy cập tài nguyên hữu hạn trong Java

## 1. Vấn đề: nhiều thread, tài nguyên có số lượng giới hạn

Giả sử một ứng dụng có 100 tác vụ đồng thời nhưng một hệ thống downstream chỉ cho phép **5 yêu cầu đang xử lý**. Nếu mỗi task tự gọi downstream ngay khi được chạy, số kết nối hoặc luồng yêu cầu có thể vượt mức tài nguyên cho phép, làm tăng timeout, lock contention và nguy cơ sập dịch vụ.

**`java.util.concurrent.Semaphore`** là synchronizer dùng một số nguyên không âm biểu thị **số permit hiện có**. Trước khi bước vào phần công việc sử dụng tài nguyên hữu hạn, task phải **acquire một permit**; khi không còn cần giữ quyền truy cập, task **release permit**. Nếu tất cả permit đang được giữ, một caller muốn acquire theo kiểu blocking sẽ chờ cho tới khi có permit được release hoặc xảy ra interruption.

~~~text
              Semaphore(3)
           [permit] [permit] [permit]
               |        |        |
           worker A  worker B  worker C    -> được vào vùng giới hạn
                                         
           worker D, E, F                  -> đang chờ permit
               |
       khi A release một permit
               |
         một waiter có thể acquire
~~~

**Điểm cần nhớ:** Semaphore **không đại diện cho tài nguyên vật lý** (connection, socket, thiết bị...). Nó chỉ quản lý *quyền được bắt đầu sử dụng* theo quy ước. Ứng dụng vẫn phải đảm bảo tài nguyên thực sự có sẵn, giải phóng đúng lúc và các worker tuân thủ giao thức acquire/release.

Bài học tập trung vào Java Concurrency chuẩn, không phụ thuộc framework khác.

## 2. Permit, acquire, release và bất biến cốt lõi

Tạo semaphore:

~~~java
Semaphore slots = new Semaphore(3);
~~~

Đây là **đoạn minh họa** trong ngữ cảnh đã import `java.util.concurrent.Semaphore`, không phải class độc lập.

- **`new Semaphore(n)`** bắt đầu với n permit.
- **`acquire()`** cần một permit. Nếu còn permit, số permit hiện có giảm đi một và caller tiếp tục; nếu không còn, caller chờ và có thể bị interrupt.
- **`release()`** tăng số permit hiện có thêm một và có thể đánh thức một caller đang chờ.
- **`tryAcquire()`** thử ngay, trả `true` khi lấy được permit và `false` nếu không lấy được ngay.
- **`tryAcquire(timeout, unit)`** chờ có hạn; trả `false` nếu hết thời gian mà chưa lấy được permit; có thể ném `InterruptedException`.
- **`availablePermits()`** trả snapshot số permit đang có tại thời điểm gọi, **không đặt chỗ** cho bước acquire kế tiếp.

Với **n permit ban đầu**, nếu code tuân thủ một acquire thành công ↔ một release tương ứng, số tác vụ đang giữ permit không vượt n. Đây là **bất biến do ứng dụng duy trì**; Semaphore tự nó không theo dõi chủ sở hữu permit.

Ví dụ:

~~~text
Semaphore(2)
Ban đầu: available=2
Task A acquire thành công: available=1
Task B acquire thành công: available=0
Task C tryAcquire(): false
Task A release(): available=1
Task C acquire thành công: available=0
Task B release(), C release(): available=2
~~~

Đừng suy ra rằng một thread giữ permit thì chỉ thread đó mới được release: Java Semaphore **không có khái niệm ownership như ReentrantLock**. Điều này hữu dụng cho handoff giữa thread nhưng cũng khiến bug **release thừa** hoặc release mà chưa acquire dễ xuất hiện.

### Quan hệ bộ nhớ (happens-before)

Theo hợp đồng Java Semaphore, hành động trong một thread **trước khi gọi release** xảy ra *happens-before* hành động trong thread khác **sau khi acquire thành công** trên cùng semaphore. Đó là cơ chế đồng bộ hữu ích, nhưng **không biến mọi thao tác trên shared data thành thread-safe**. Với n lớn hơn 1, nhiều task có thể vẫn truy cập cùng dữ liệu trong vùng được giới hạn; nếu các task cùng sửa một biến/cấu trúc không thread-safe, vẫn cần đồng bộ hoặc phân chia dữ liệu thích hợp.

## 3. Bốn kiểu acquire và lựa chọn theo deadline

| API | Hành vi khi hết permit | Giá trị trả về | Interruption |
|---|---|---|---|
| `acquire()` | Chờ tới khi có permit | `void` | Có, `InterruptedException` |
| `acquireUninterruptibly()` | Chờ tới khi có permit | `void` | Không ném vì interrupt trong lúc chờ; giữ lại trạng thái interrupt khi kết thúc |
| `tryAcquire()` | Trả về ngay | `boolean` | Không chờ nên không phải API chờ interruptible |
| `tryAcquire(timeout, unit)` | Chờ tối đa timeout | `boolean` | Có, `InterruptedException` |

Ngoài ra có các overload cho nhiều permit:

~~~java
slots.acquire(2);
slots.release(2);
boolean accepted = slots.tryAcquire(2);
boolean timed = slots.tryAcquire(2, 100, TimeUnit.MILLISECONDS);
~~~

Các dòng trên là **mã minh họa** với `slots` là Semaphore và `TimeUnit` đã import; `acquire(2)` có thể ném InterruptedException. Acquire nhiều permit yêu cầu đủ toàn bộ số lượng permit theo hợp đồng, không nhận một phần rồi trả về. Tránh yêu cầu quá nhiều permit khiến task nhỏ khó được phục vụ.

### Chọn cách nào?

- **`acquire()`:** khi producer có thể chờ và task phải được xử lý, nhưng phải có kế hoạch shutdown/interrupt. Nếu caller là thread request có deadline ngắn, chờ vô hạn thường không thích hợp.
- **`tryAcquire()`:** dùng cho admission control **fail-fast**, ví dụ trả lỗi quá tải hoặc bỏ công việc ít quan trọng. Bắt buộc kiểm tra boolean.
- **`tryAcquire(timeout)`:** cho phép đợi ngắn để hấp thụ burst nhưng giữ **giới hạn latency**. Khi trả false, task chưa vào vùng cần permit; không được release.
- **`acquireUninterruptibly()`:** chỉ dùng khi có lý do mạnh để không bỏ cuộc khi nhận interrupt. Trong shutdown, nó có thể làm worker chờ rất lâu; không phải lựa chọn mặc định.

**Không dùng `availablePermits() > 0` làm bước kiểm tra trước rồi tự tin sẽ acquire ngay**: nhiều thread có thể đồng thời thấy cùng snapshot. Chỉ kết quả `tryAcquire()` hoặc acquire hoàn tất mới xác nhận đã giữ quyền truy cập.

## 4. Quy tắc an toàn: acquire thành công rồi mới release trong finally

Mẫu thực hành quan trọng nhất:

~~~java
boolean acquired = false;
try {
    acquired = slots.tryAcquire(200, TimeUnit.MILLISECONDS);
    if (!acquired) {
        // Quyết định reject/defer: không gọi downstream.
        return;
    }
    useLimitedResource();
} finally {
    if (acquired) {
        slots.release();
    }
}
~~~

Đây là **mã minh họa bên trong một phương thức**, với `slots` đã khai báo và `useLimitedResource()` đại diện cho xử lý nghiệp vụ; không phải file Java độc lập. Overload có timeout có thể ném `InterruptedException`.

Với blocking `acquire()`:

~~~java
slots.acquire(); // Có thể ném InterruptedException.
try {
    useLimitedResource();
} finally {
    slots.release();
}
~~~

**Đặt `acquire()` trước khối try/finally** giúp không release nếu acquire chưa thành công và ném InterruptedException. Sau khi đã acquire, finally chạy dù công việc bên trong ném exception unchecked.

Nếu cần acquire nhiều permit, **release đúng số đã lấy**. Một lỗi rất khó phát hiện là `release()` cả trong catch lẫn finally, khiến available permit tăng vượt capacity ban đầu: về sau hệ thống có thể chạy nhiều công việc đồng thời hơn giới hạn đặt ra.

**Semaphore không giới hạn số permit tối đa khi release.** Nó không tự bác bỏ một release thừa chỉ vì đã đạt số permit ban đầu. Có thể kiểm thử bất biến này ở cấp application bằng metric hoặc semaphore wrapper, nhưng không dùng snapshot `availablePermits()` như cơ chế khóa chính.

## 5. Ví dụ Java 17: chỉ hai tác vụ được xử lý đồng thời

Chương trình dùng **Semaphore(2)** và hai worker giữ permit trong khi đợi một latch. Thread main thử acquire permit thứ ba: chắc chắn nhận `false` vì hai permit đang được giữ. Khi cho hai worker hoàn tất, permit được trả về.

Lưu **SemaphoreLimitDemo.java**:

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public class SemaphoreLimitDemo {
    public static void main(String[] args) throws Exception {
        Semaphore slots = new Semaphore(2);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch bothEntered = new CountDownLatch(2);
        CountDownLatch finishWork = new CountDownLatch(1);

        try {
            Callable<String> first = () -> {
                slots.acquire();
                try {
                    bothEntered.countDown();
                    finishWork.await();
                    return "task-A";
                } finally {
                    slots.release();
                }
            };
            Callable<String> second = () -> {
                slots.acquire();
                try {
                    bothEntered.countDown();
                    finishWork.await();
                    return "task-B";
                } finally {
                    slots.release();
                }
            };

            Future<String> a = pool.submit(first);
            Future<String> b = pool.submit(second);

            if (!bothEntered.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Workers not ready");
            }

            boolean thirdAccepted = slots.tryAcquire();
            System.out.println("third accepted=" + thirdAccepted);
            if (thirdAccepted) {
                slots.release(); // Phòng vệ nếu điều kiện ví dụ thay đổi.
            }

            finishWork.countDown();
            System.out.println("results=" + a.get() + "," + b.get());
            System.out.println("available after=" + slots.availablePermits());
        } finally {
            finishWork.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac SemaphoreLimitDemo.java
java SemaphoreLimitDemo
~~~

Stdout dự kiến:

~~~text
third accepted=false
results=task-A,task-B
available after=2
~~~

**Vì sao kết quả ổn định?** `bothEntered.await(...)` chỉ tiếp tục khi cả hai worker đã acquire thành công và đi đến latch. Lúc đó mỗi worker đang chờ `finishWork`, nên cả hai permit vẫn được giữ. Main gọi `tryAcquire()` trước khi thả latch; tất yếu không có permit rảnh. Sau khi release latch và `Future.get()` của cả hai task hoàn tất, hai `finally` đã release permit. Thứ tự chạy của hai worker không ảnh hưởng thứ tự `a.get(), b.get()` được in từ main.

**Chú ý:** `pool.shutdownNow()` trong finally là bước phòng vệ khi ví dụ có lỗi; trong hệ thống thật cần quy trình graceful shutdown có thời hạn và kiểm tra kết quả dừng.

## 6. Ví dụ Java 17: giới hạn thời gian chờ permit

Với một tài nguyên chỉ cho phép một request đồng thời, main giữ permit trước. Worker khác không thể acquire trong thời hạn ngắn, nên `tryAcquire(timeout)` trả `false`. Sau khi main release, một lần thử mới thành công. Đây là mẫu admission control có timeout.

Lưu **SemaphoreTimeoutDemo.java**:

~~~java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public class SemaphoreTimeoutDemo {
    public static void main(String[] args) throws Exception {
        Semaphore slots = new Semaphore(1);

        slots.acquire(); // Giả lập tài nguyên đang bị chiếm.
        try {
            boolean accepted = slots.tryAcquire(
                    30, TimeUnit.MILLISECONDS);
            System.out.println("accepted while busy=" + accepted);
            if (accepted) {
                slots.release();
            }
        } finally {
            slots.release();
        }

        boolean acceptedAfterRelease = slots.tryAcquire(
                30, TimeUnit.MILLISECONDS);
        System.out.println("accepted after release=" + acceptedAfterRelease);
        if (acceptedAfterRelease) {
            slots.release();
        }
        System.out.println("available=" + slots.availablePermits());
    }
}
~~~

Chạy:

~~~bash
javac SemaphoreTimeoutDemo.java
java SemaphoreTimeoutDemo
~~~

Stdout:

~~~text
accepted while busy=false
accepted after release=true
available=1
~~~

**Timeout không phải auto-retry**: `tryAcquire(timeout)` trả false nghĩa là caller chưa có permit sau thời hạn chờ, nên chưa được bắt đầu công việc downstream. Caller phải có chính sách: trả lỗi quá tải, bỏ/defer nếu được phép hoặc retry có budget và backoff phù hợp.

Ở đây cũng không dùng sleep để ép kết quả: main giữ permit trong toàn bộ thời gian gọi timed tryAcquire, nên kết quả false là xác định.

## 7. Ví dụ Java 17: interrupt một worker đang chờ permit

`Semaphore.acquire()` là **interruptible**. Ví dụ này cho main giữ permit, worker bắt đầu chờ rồi bị yêu cầu dừng bằng `Future.cancel(true)`. CountDownLatch xác nhận worker đã vào logic chờ, còn main vẫn giữ permit, vì thế worker không thể đi qua acquire. Worker bắt `InterruptedException`, đánh dấu đã nhận ngắt và không release permit mà nó chưa acquire.

Lưu **SemaphoreInterruptDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class SemaphoreInterruptDemo {
    public static void main(String[] args) throws Exception {
        Semaphore slots = new Semaphore(1);
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        AtomicBoolean interrupted = new AtomicBoolean();

        slots.acquire(); // Main giữ permit; worker không thể lấy.
        try {
            Future<?> waiter = pool.submit(() -> {
                boolean acquired = false;
                try {
                    entered.countDown();
                    slots.acquire();
                    acquired = true;
                } catch (InterruptedException ex) {
                    interrupted.set(true);
                    Thread.currentThread().interrupt();
                } finally {
                    if (acquired) {
                        slots.release();
                    }
                    finished.countDown();
                }
            });

            if (!entered.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Waiter not started");
            }
            boolean cancelled = waiter.cancel(true);
            if (!finished.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Waiter did not stop");
            }

            System.out.println("cancel accepted=" + cancelled);
            System.out.println("waiter interrupted=" + interrupted.get());
            System.out.println("waiter cancelled=" + waiter.isCancelled());
        } finally {
            slots.release();
            pool.shutdownNow();
        }
        System.out.println("available=" + slots.availablePermits());
    }
}
~~~

Chạy:

~~~bash
javac SemaphoreInterruptDemo.java
java SemaphoreInterruptDemo
~~~

Stdout:

~~~text
cancel accepted=true
waiter interrupted=true
waiter cancelled=true
available=1
~~~

**Điểm phân biệt:** `Future.cancel(true)` gửi yêu cầu interrupt tới worker đang chạy của ExecutorService. Worker được chặn trong `Semaphore.acquire()` nên `InterruptedException` xảy ra; worker có thể thoát sạch. Tuy nhiên, không có quy tắc chung rằng mọi tác vụ Java lập tức dừng khi cancel(true): việc dừng các thao tác khác vẫn phụ thuộc chúng có hỗ trợ interrupt và code có hợp tác không.

Cờ `acquired` bảo đảm chỉ release nếu thực sự đã acquire. Main release permit **chỉ một lần** trong finally; tổng số permit trở về 1.

## 8. Fairness: Semaphore công bằng hay không?

Mặc định `new Semaphore(permits)` dùng chế độ **nonfair**. Có thể tạo semaphore có thứ tự phục vụ công bằng:

~~~java
Semaphore fair = new Semaphore(3, true);
~~~

Với chế độ fair, các lời gọi acquire **blocking** được phục vụ theo thứ tự đến tại **những điểm ordering nội bộ của cơ chế acquisition**. Điều này giúp hạn chế nguy cơ thread chờ lâu bị vượt mặt, nhưng **không cam kết thời điểm thread hoàn tất, thứ tự bắt đầu ngay khi gọi method, hay độ trễ cố định** do OS scheduler, thời gian thực hiện task và cuộc đua trước điểm ordering còn tác động.

Một chi tiết dễ bỏ sót: **`tryAcquire()` không có timeout có thể lấy permit ngay khi thấy rảnh, kể cả khi fairness=true và có thread đang chờ** (*barging*). Với mã cần tôn trọng fairness, overload **`tryAcquire(0, TimeUnit.SECONDS)`** là cách thử ngay có tham gia chính sách fairness (nhưng interruptible).

| Thuộc tính | Nonfair (mặc định) | Fair |
|---|---|---|
| Chiến lược acquire khi cạnh tranh | Có thể barging, thường thiên về throughput | Thường phục vụ theo thứ tự waiting tại điểm cấp permit |
| Mục tiêu | Giảm overhead, throughput cao | Giảm starvation cho waiter |
| Chi phí | Thường thấp hơn | Có thể tốn đồng bộ hơn, giảm throughput |
| Cam kết thứ tự log | Không | **Cũng không** |
| `tryAcquire()` không timeout | Có thể barging | **Vẫn có thể barging** |

Fairness không thay thế deadline, starvation monitoring hoặc quản lý workload. Nếu một thread giữ permit rất lâu, các thread khác vẫn chờ dù chế độ fair=true.

## 9. Binary semaphore khác gì ReentrantLock?

**Binary semaphore** (`new Semaphore(1)`) giới hạn vùng truy cập còn **một task tại một thời điểm**, nên nhìn giống mutex. Tuy nhiên:

| Tiêu chí | `Semaphore(1)` | `ReentrantLock` |
|---|---|---|
| Số holder logic | 1 khi tuân thủ giao thức | 1 owner thread |
| Ownership bắt buộc | **Không**: thread khác cũng có thể release | **Có**: chỉ owner được unlock |
| Reentrant | **Không** theo nghĩa lock: acquire lần hai cần permit khác | **Có**: owner có thể lock nhiều lần |
| `release` / `unlock` thừa | Có thể tăng permit không mong muốn | `unlock` không phải owner ném IllegalMonitorStateException |
| Chuyển quyền giữa thread | Có thể dùng để handoff/signal | Không có cùng mô hình release khác thread |
| Dùng chính | Giới hạn quyền truy cập tài nguyên đồng thời | Bảo vệ critical section có owner thread |

Nếu mục tiêu là **bảo vệ một biến chia sẻ** với một lock độc quyền và cần ownership, `ReentrantLock` (hoặc `synchronized`) thường biểu đạt rõ hơn. Nếu mục tiêu là **N thao tác được phép đồng thời**, Semaphore là primitive tự nhiên.

Binary semaphore còn có thể khởi tạo bằng **0 permit** để dùng như tín hiệu một lần/handoff, nhưng cần quản lý release tránh tích lũy permit nếu tín hiệu lặp lại. Với chờ đến một sự kiện hoặc nhiều worker cùng hoàn tất, có thể cân nhắc CountDownLatch, Phaser hoặc Condition tùy bài toán.

## 10. Semaphore và connection pool/resource pool

Giả sử có **10 kết nối** hoặc **10 thiết bị** vật lý:

- Semaphore(10) giới hạn **không quá 10 vùng xử lý có permit**.
- Nhưng bạn vẫn cần một **bộ quản lý 10 tài nguyên thực**: ai lấy connection nào, kiểm tra connection còn dùng được, khi nào trả lại và điều gì xảy ra nếu lỗi.
- Semaphore không tự tạo connection, không theo dõi connection đang hỏng và không làm thao tác quản lý tài nguyên thành thread-safe.

Ví dụ logic:

~~~text
acquire permit
    |
  borrow actual resource
    |
  use resource with timeout
    |
  return/close actual resource
    |
release permit
~~~

Thứ tự giải phóng nên đảm bảo **không trả permit trước khi tài nguyên thật sự sẵn sàng cho lượt mới**. Với `try-with-resources`, phải hiểu semantics của `close()`: có nơi close trả connection về pool, có nơi close đóng kết nối vật lý. Nếu một resource bị hỏng, cần xử lý thay thế hoặc giảm khả năng cấp phát thực tế thay vì vẫn cấp quyền cho 10 task mặc dù chỉ còn 9 resource hợp lệ.

**Không nên đặt hai cơ chế chờ cạnh nhau mà không rõ ràng**: chẳng hạn acquire Semaphore trước rồi chờ lâu trên một queue connection có capacity khác có thể giữ permit vô ích. Nếu thư viện resource pool đã có giới hạn concurrency/borrow timeout đáng tin, cân nhắc sử dụng chính nó thay vì thêm semaphore không cần thiết.

### Sizing permits

Một giới hạn hợp lý phải dựa trên **năng lực downstream** và yêu cầu độ trễ, không chỉ số thread của ứng dụng:

- Database cho phép bao nhiêu connection hoạt động và mỗi query tốn bao lâu?
- Dịch vụ ngoài áp giới hạn **in-flight**, rate limit hoặc cả hai?
- Một task có thể giữ đồng thời nhiều permit từ nhiều tài nguyên hay không?
- Có nhiều instance ứng dụng cùng dùng chung downstream không?

**Semaphore chỉ giới hạn concurrency, không trực tiếp giới hạn requests/giây.** Nếu mỗi request hoàn thành nhanh, 5 permit vẫn có thể cho rất nhiều requests/giây. Nếu downstream áp rate limit theo cửa sổ thời gian, cần rate limiter/token bucket hoặc cơ chế quota khác. Một giới hạn 10 permit **mỗi instance** cũng không tự tạo giới hạn toàn cụm 10 khi ứng dụng chạy trên 20 instance.

## 11. Semaphore và bounded queue/backpressure

Khi producer liên tục nhận công việc, chỉ đặt Semaphore ở đoạn gọi downstream có thể khiến **rất nhiều task đang chờ acquire** tích lũy ở bên trong executor hoặc tạo thread, dù số task đang dùng downstream được giới hạn.

Vì vậy cần phân biệt:

- **Semaphore:** giới hạn **số task được đi vào vùng dùng tài nguyên**.
- **Bounded BlockingQueue:** giới hạn **số task chờ** trong queue nếu có chính sách admission phù hợp.
- **ThreadPoolExecutor:** giới hạn số worker và điều phối queue/rejection khi saturated, tùy cấu hình.
- **Rate limiter:** giới hạn tốc độ bắt đầu công việc theo thời gian.
- **Deadline/cancellation:** giới hạn thời gian task chờ và ngừng những công việc không còn hữu ích.

~~~text
Incoming requests
       |
 admission / bounded queue / reject
       |
 worker thực thi
       |
 tryAcquire(timeout) trên Semaphore(N)
       |
   N thao tác downstream đang active
       |
 release đúng một permit
       |
 hoàn tất
~~~

**Nếu chỉ có Semaphore mà thiếu admission control**, nguy cơ backlog tăng và request timeout ở tầng trên vẫn còn. Backpressure thực sự cần **tác động ngược đến producer** khi hệ thống đầy, ví dụ trả lỗi quá tải, chờ ngắn hoặc trì hoãn có giới hạn.

Khi dùng Semaphore bên trong một worker pool nhỏ, nhiều worker có thể cùng bị chặn ở `acquire()\), làm worker không còn phục vụ tác vụ khác. Đôi khi nên đặt semaphore tại điểm admission hoặc thiết kế async queue để tránh dùng worker chỉ để chờ permit.

## 12. Deadlock, starvation và acquire nhiều tài nguyên

### Deadlock do giữ permit rồi chờ tài nguyên khác

Giả sử Task A đã giữ semaphore X nhưng đang chờ Y, Task B giữ Y nhưng chờ X. Cả hai có thể deadlock dù mỗi semaphore hoạt động đúng. Cách phòng tránh thường là **thứ tự acquire thống nhất**, deadline và không giữ permit lâu trong khi chờ các tài nguyên khác.

~~~text
Task A: acquire(X) -> wait(Y)
Task B: acquire(Y) -> wait(X)
=> vòng chờ
~~~

### Self-deadlock với một permit

Một method đang giữ `Semaphore(1)` rồi gọi method khác tiếp tục `acquire()` trên cùng semaphore có thể tự chờ mãi, vì Semaphore **không reentrant**. Không áp dụng mẫu reentrant lock một cách máy móc cho Semaphore.

### Hoạt động quá lâu trong vùng được bảo vệ

Một task giữ permit trong khi đợi I/O vô thời hạn, hoặc ghi log đồng bộ chậm, có thể khiến các waiter khác bị đói tài nguyên. Đặt timeout I/O, giới hạn critical section và phát hiện **permit hold duration** bất thường.

### Nhiều permit cùng lúc

`acquire(2)` thuận tiện khi một công việc thực sự dùng hai slot, nhưng nếu nhiều task nhỏ chỉ cần một permit, một tác vụ đòi nhiều permit có thể chờ lâu, đặc biệt trong chế độ nonfair. Cân nhắc fairness và scheduler workload khi yêu cầu permit rất không đồng đều.

**`reducePermits` và `drainPermits`:** các phương thức nâng cao để giảm hoặc rút permit hiện có, không phải API quản lý resource pool phổ thông; chúng có thể đưa semaphore vào trạng thái ít permit hoặc âm permit trong những trường hợp điều chỉnh chuyên biệt. Không dùng chúng tùy tiện như cách giải phóng tài nguyên hoặc xử lý shutdown, vì chúng làm khó bảo đảm số task được phép chạy.

## 13. Interruption, cancellation và graceful shutdown

Thread đang chờ `acquire()` hoặc `tryAcquire(timeout)` có thể bị interrupt, ném `InterruptedException`. Khi code bắt exception nhưng **không truyền tiếp**, thông thường nên khôi phục cờ interrupt bằng `Thread.currentThread().interrupt()` và thoát sớm để tầng trên biết có yêu cầu ngừng.

**Không release nếu chưa acquire thành công.** Đây là lỗi điển hình khi đặt release trong finally bao quanh cả lệnh acquire.

Nếu caller dùng `Future.cancel(true)`, việc dừng thực sự của task còn phụ thuộc vào nơi task đang chờ hoặc đang chạy. Một task đang chờ `Semaphore.acquire()` sẽ đáp ứng interrupt theo hợp đồng; một task đang xử lý thư viện I/O không interruptible có thể không dừng ngay.

**Semaphore không có thao tác `close()` tổng quát để đánh thức mọi waiter và chặn acquire mới.** Khi shutdown service, component cần có chính sách riêng:

1. Ngừng nhận task mới vào pipeline.
2. Hủy/interrupt công việc đang chờ theo deadline.
3. Cho công việc đang giữ permit kết thúc hoặc escalate có kiểm soát.
4. Bảo đảm mọi release cuối cùng hoàn tất, không tự tăng permit để “đánh thức” waiter nếu điều đó vô tình cho phép công việc mới vào vùng giới hạn.
5. Đảm bảo nguồn tài nguyên thực được đóng **sau** khi các task không còn dùng chúng, hoặc có kế hoạch cleanup cho trường hợp task không dừng.

Nếu cần giám sát shutdown, phân biệt số task đang chờ, số permit hiện có, số task đang giữ permit và trạng thái thực tế của connection/resource. `availablePermits()` một mình không cho biết đã an toàn để đóng mọi tài nguyên.

## 14. Fairness không có nghĩa không bao giờ starvation

Một semaphore fair giúp giảm việc một waiter bị vượt mặt lặp đi lặp lại, nhưng **không bảo đảm** từng task sẽ hoàn thành trong một thời gian cụ thể. Ví dụ một task giữ permit quá lâu, OS scheduler tạm ngừng worker, hay API `tryAcquire()` liên tục barging, vẫn có thể tạo độ trễ lớn.

Theo dõi:

- **Wait time** để acquire permit, ví dụ p50/p95/p99;
- số lượng task đang chờ (`getQueueLength()` là **ước lượng**, không phải số chính xác để quyết định admission);
- tỷ lệ timed `tryAcquire` thất bại và reject;
- **hold duration** từ sau acquire đến release;
- số permit tối đa, số đang dùng, tài nguyên downstream thực sự đang active;
- callback/exception khiến release bị bỏ sót;
- saturation ở queue/worker khác.

Nên tránh `if (sem.getQueueLength() == 0) ...` như điều kiện quyết định an toàn: nó chỉ là một ước lượng tại thời điểm quan sát. Nếu muốn fail-fast, dùng `tryAcquire()` và quyết định rõ khi false.

## 15. Những lỗi phổ biến

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| `release()` khi `acquire()` chưa thành công | Permit tăng thừa, phá giới hạn concurrency | Đặt acquire trước try/finally hoặc dùng cờ acquired |
| Quên release khi công việc ném exception | Rò permit; nhiều waiter chờ mãi | Release trong finally sau acquire thành công |
| Gọi `availablePermits() > 0` rồi tin đã giữ slot | Race, kiểm tra và dùng không nguyên tử | Dùng `tryAcquire()` |
| `tryAcquire()` trả false mà vẫn gọi downstream | Vượt giới hạn | Không vào vùng hạn chế nếu không có permit |
| Dùng `acquireUninterruptibly()` cho tác vụ cần dừng | Thread kẹt khi shutdown | Dùng acquire interruptible hoặc timed |
| Dùng Semaphore để bảo vệ biến dùng chung như lock có ownership | Side effect và lỗi release từ thread khác | Dùng `ReentrantLock` nếu cần ownership |
| Dùng `Semaphore(N)` mà mặc định mọi truy cập shared state an toàn | Có thể vẫn có data race giữa N task | Đồng bộ state hoặc chia dữ liệu |
| Giới hạn N permit mỗi instance mà tưởng là N toàn hệ thống | Nhiều instance cùng vượt capacity downstream | Phân chia ngân sách hoặc giới hạn tại downstream |
| Giữ permit trong lúc chờ queue/resource khác | Giảm hiệu suất hoặc deadlock | Rút ngắn vùng giữ permit, thống nhất thứ tự acquire |
| Nghĩ fairness=true bảo đảm thứ tự tuyệt đối mọi API | Không xét barging của `tryAcquire()` | Hiểu điểm ordering và overload timeout |
| Chỉ dùng Semaphore mà không giới hạn backlog | Thread/task đang đợi tăng không kiểm soát | Kết hợp bounded queue, rejection và deadline |
| Tin `release()` chỉ có thể do owner gọi | Không có ownership, dễ release sai | Kiểm soát bằng API wrapper và finally |

## 16. Bài toán thực tế: chọn permit và backpressure

Một dịch vụ chỉ cho tối đa **8 outbound call đồng thời trên một JVM**:

1. Tạo `Semaphore(8)` dùng chung cho **tất cả code path** gọi tài nguyên đó.
2. Ở boundary của request, áp **deadline toàn request** và dùng `tryAcquire(remainingTime, unit)`.
3. Nếu false, trả kết quả overload hoặc defer công việc theo policy rõ; **không** gọi downstream.
4. Khi acquire thành công, đo **thời gian giữ permit**, gọi downstream có timeout I/O, release trong finally.
5. Nếu ingress lớn hơn năng lực xử lý bền vững, đặt bounded queue/admission và backpressure ở đầu vào.
6. Nếu triển khai 4 instance, kiểm tra tổng budget downstream: 8 × 4 = 32 call có thể đồng thời. Nếu downstream chỉ cho 20, quota 8 mỗi instance là quá lớn.

**Giới hạn concurrency khác giới hạn rate.** Với 8 permit và mỗi call mất 10 ms, tốc độ có thể cao hơn nhiều so với 8 request/giây. Nếu API giới hạn 100 request/phút, một semaphore đơn thuần không đủ: cần rate limiter riêng.

**Nguyên tắc quan trọng:** permission boundary phải bao trùm phần thật sự sử dụng tài nguyên, không bao luôn preprocessing dài không cần thiết. Đồng thời nếu release quá sớm trước khi transaction/I/O thực sự hoàn tất, giới hạn không còn ý nghĩa.

## 17. Checklist để áp dụng đúng

Trước khi dùng Semaphore, hãy trả lời:

1. **Tài nguyên hữu hạn nào cần bảo vệ?** Connection, outbound request, thiết bị, task CPU-bound hay bộ nhớ?
2. Số permit có dựa trên năng lực tài nguyên thật không? Giới hạn theo JVM hay toàn hệ thống?
3. Người gọi có thể chờ bao lâu? Chọn acquire, tryAcquire hay timed tryAcquire?
4. Mọi đường đi đều có **đúng một release sau một acquire thành công** chưa?
5. Có khả năng nested acquire cùng semaphore, nhiều semaphore hoặc deadlock vòng chờ không?
6. Có cần fairness không? Có hiểu `tryAcquire()` không timeout có thể barging không?
7. Có bounded queue, policy overload, retry budget và deadline hay semaphore đang che giấu backlog?
8. Task đang giữ permit có timeout I/O và cleanup hợp lý khi exception/interrupt không?
9. Có đo wait time, hold time, rejection và downstream saturation không?
10. Đã test trường hợp mọi permit bị giữ, timeout, interrupt, double release và shutdown chưa?

**Tóm tắt:** Java `Semaphore` giới hạn **số tác vụ đồng thời được phép đi vào một vùng sử dụng tài nguyên** bằng cơ chế permit. Hãy **acquire trước – làm việc trong try – release trong finally**, chọn timeout theo deadline, hiểu fairness/ownership và kết hợp bounded queue/backpressure khi lưu lượng đến vượt khả năng xử lý. Semaphore giúp tránh quá tải đồng thời, nhưng không tự tạo tài nguyên, không tự bảo vệ shared state và không thay thế rate limiting hay quản lý lifecycle.
