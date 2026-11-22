# LockSupport.park()/unpark() và permit trong Java

`java.util.concurrent.locks.LockSupport` cung cấp các thao tác **park** để một thread tự tạm dừng, và **unpark** để một thread khác cấp quyền cho thread đích tiếp tục. Nó là một **primitive chờ/đánh thức cấp thấp**, thường được sử dụng bên dưới các cấu trúc đồng bộ khác trong Java, không phải queue, mutex hay bộ đếm công việc.

Khái niệm cốt lõi là **permit**: mỗi thread có tối đa **một** permit. `LockSupport.unpark(thread)` làm permit của thread đích có sẵn; `LockSupport.park()` của thread đó có thể tiêu thụ permit và trở về. Vì permit không tích lũy, nhiều lần unpark trước park **không** tạo nhiều lượt park được phép đi tiếp. `park` cũng có thể trở về khi bị interrupt hoặc vì *spurious return*, nên code đúng cần **predicate riêng, vòng kiểm tra lại và memory visibility hợp lệ**.

Bài học này thuộc Java concurrency nói chung, không phụ thuộc một framework riêng.

## 1. Mô hình permit một-bit

Hình dung permit của một thread là trạng thái logic 0 hoặc 1:

| Sự kiện | Permit | Ý nghĩa |
| --- | --- | --- |
| Thread được khởi tạo, chưa nhận tín hiệu | 0 | Chưa có permit chờ sẵn |
| Thread khác gọi `unpark(T)` | 1 | T được cấp quyền cho một lần park |
| Thread khác gọi `unpark(T)` thêm một lần | Vẫn 1 | Không cộng dồn thành 2 |
| T gọi `park()` khi permit đã có | 0 sau khi tiêu thụ | Lời gọi có thể trở về ngay |
| T gọi `park()` khi chưa có permit | Có thể chờ | Đợi unpark, interrupt hoặc trở về vì nguyên nhân khác được API cho phép |

Mô hình này để **lý giải behavior**, không phải field `boolean` có thể đọc từ API. Không có `LockSupport.hasPermit()` hay thao tác “nhận số lượng permit”; không thể dùng permit thay một queue chứa job.

Một vài lịch thực thi:

```text
A: unpark(B)            -> permit(B) có sẵn
B: park()               -> tiêu thụ permit, trở về

A: unpark(B)
A: unpark(B)            -> vẫn chỉ một permit
B: park()               -> tiêu thụ một permit
B: park()               -> có thể phải chờ tín hiệu mới

B: park()               -> có thể tạm dừng
A: unpark(B)            -> B có thể được đánh thức
```

Không nói rằng lần `park` thứ hai **bắt buộc chờ mãi**: `park` có thể trở về vì interrupt/spurious return. Điều quan trọng là không được dựa vào lần `unpark` thứ hai như một permit tích lũy riêng.

## 2. `unpark` có thể xảy ra trước `park`

Với `Object.notify()`, nếu code sai giao thức và thông báo xảy ra trước khi thread vào wait set, thông báo đó không tự được ghi nhớ thành “vé đợi”. `LockSupport` có cơ chế permit, cho phép thread được unpark trước rồi mới park.

```text
Main thread                         Worker thread
--------------------------------    ------------------------------
Worker đã start                     chưa gọi park()
unpark(worker)                      permit = 1
                                    park() tiêu thụ permit
                                    tiếp tục thực thi
```

**Nhưng có hai giới hạn đáng nhớ.** Thứ nhất, permit **không được bảo đảm giữ lại qua `Thread.start()` xen vào**; không dựa vào `unpark` một thread chưa start. Thứ hai, **một lời gọi park trung gian** của code thư viện có thể tiêu thụ permit trước khi code của bạn tới `park` dự kiến. Vì vậy không lưu permit như một token bảo đảm tồn tại xuyên qua các lời gọi blocking tùy ý.

### Ví dụ Java 17: cấp permit trước khi worker gọi park

Tạo tệp `PreUnparkExample.java`:

```java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.locks.LockSupport;

public class PreUnparkExample {
    public static void main(String[] args) throws InterruptedException {
        AtomicBoolean started = new AtomicBoolean(false);
        AtomicBoolean proceed = new AtomicBoolean(false);
        AtomicBoolean returned = new AtomicBoolean(false);

        Thread worker = new Thread(() -> {
            started.set(true);
            while (!proceed.get()) {
                Thread.onSpinWait();
            }
            LockSupport.park();
            returned.set(true);
        }, "worker");

        worker.start();
        long deadline =
                System.nanoTime() + TimeUnit.SECONDS.toNanos(5);

        while (!started.get()) {
            if (System.nanoTime() >= deadline) {
                worker.interrupt();
                throw new IllegalStateException("Worker not started");
            }
            Thread.onSpinWait();
        }

        LockSupport.unpark(worker);
        proceed.set(true);

        worker.join(5_000);
        if (worker.isAlive()) {
            worker.interrupt();
            throw new IllegalStateException("Worker still parked");
        }
        System.out.println("parkReturned=" + returned.get());
    }
}
```

```bash
javac PreUnparkExample.java
java PreUnparkExample
```

Stdout khi hoàn thành bình thường:

```text
parkReturned=true
```

**Giải thích:** worker đã khởi động và báo `started` trước khi main unpark. Trong lúc chờ `proceed`, worker chỉ spin, **không dùng một primitive park khác** có thể tiêu thụ permit. Main cấp permit rồi mở cổng. Worker gọi `park` với permit đã có nên không cần unpark mới. `join` bảo đảm main in sau khi worker hoàn tất.

Busy-spin ở đây **chỉ để tạo checkpoint minh họa** và có deadline; không phải mô hình chờ khuyến nghị trong production. Một lần chạy in dòng trên cũng không chứng minh park không bao giờ spurious return; hợp đồng permit mới là cơ sở để hiểu.

## 3. Vì sao unpark không đếm job?

Giả sử producer tạo 100 tác vụ rồi gọi `unpark(consumer)` 100 lần; nếu consumer chưa gọi `park`, những lần unpark chỉ tạo **một permit**. Một consumer viết “100 lần park, mỗi lần xử lý một job” có thể kẹt sau lần đầu.

```java
// Cách diễn đạt sai về nghiệp vụ:
for (int i = 0; i < 100; i++) {
    LockSupport.unpark(consumer);
}

// Phía consumer, cũng sai nếu coi một park = một job:
for (int i = 0; i < 100; i++) {
    LockSupport.park();
    processOneJob();
}
```

Đây là **snippet minh họa thiết kế sai**; `consumer` và `processOneJob` chưa được định nghĩa. Permit không phải queue và không chứa payload. Thiết kế đúng phải lưu công việc trong một **queue thread-safe**, hoặc dùng `BlockingQueue` đã có `put/take`. Khi cần N giấy phép truy cập tài nguyên, dùng `Semaphore`: permit của semaphore được đếm theo hợp đồng khác hẳn một-bit permit của LockSupport.

## 4. `park` có thể trở về mà không được `unpark`

Ngoài unpark, `park` có thể trở về vì **interrupt** hoặc **spurious return**. Với các overload timed, nó còn có thể trở về vì hết thời gian. Do đó đoạn:

```java
LockSupport.park();
processJob();
```

sai nếu `processJob` chỉ được thực hiện khi một điều kiện nghiệp vụ thật đã xảy ra.

Cần một predicate độc lập:

```java
while (!ready.get()) {
    LockSupport.park();
    if (Thread.currentThread().isInterrupted()) {
        return;
    }
}
processJob();
```

Đây là snippet trong method `void`, `ready` là `AtomicBoolean` và `processJob()` là nghiệp vụ. Nếu park thức sớm mà `ready=false`, thread chờ lại. Nếu bị interrupt, nó thoát theo policy hủy của ví dụ.

**Quan trọng:** `LockSupport.park()` không ném `InterruptedException` và không tự xóa interrupt flag. Khi cờ interrupt đang bật, park có thể liên tục trả ngay; nếu vòng lặp chỉ kiểm tra predicate false mà không xử lý interrupt, worker có thể **spin nóng và chiếm CPU**.

## 5. Java 17: phối hợp bằng predicate và permit

Producer phải **công bố trạng thái**, sau đó **unpark đúng thread**. Consumer chờ trên predicate chứ không tin rằng `park` trở về tự mang nghĩa “có dữ liệu”.

Tạo `ParkPredicateExample.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.locks.LockSupport;

public class ParkPredicateExample {
    public static void main(String[] args) throws Exception {
        AtomicBoolean ready = new AtomicBoolean(false);
        AtomicInteger received = new AtomicInteger(-1);
        CountDownLatch started = new CountDownLatch(1);
        int[] payload = {0};

        Thread consumer = new Thread(() -> {
            started.countDown();

            while (!ready.get()) {
                LockSupport.park("waiting-for-payload");
                if (Thread.currentThread().isInterrupted()) {
                    return;
                }
            }
            received.set(payload[0]);
        }, "consumer");

        consumer.start();

        if (!started.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Consumer not started");
        }

        payload[0] = 42;
        ready.set(true);
        LockSupport.unpark(consumer);

        consumer.join(5_000);
        if (consumer.isAlive()) {
            consumer.interrupt();
            throw new IllegalStateException("Consumer did not finish");
        }
        System.out.println("received=" + received.get());
    }
}
```

```bash
javac ParkPredicateExample.java
java ParkPredicateExample
```

Stdout bình thường:

```text
received=42
```

**Vì sao đúng?** Producer ghi `payload[0]=42`, sau đó `ready.set(true)`. Consumer chỉ đọc payload sau khi `ready.get()` quan sát giá trị true. Các thao tác atomic/volatile của `ready` mang memory-consistency semantics cần thiết để công bố payload. `unpark` chỉ để worker đang park có cơ hội chạy và **kiểm tra lại cờ**; bản thân permit không làm một object mutable trở nên thread-safe.

Xét ba lịch:

- Consumer park trước → producer unpark → consumer thức và thấy cờ true.
- Producer công bố trước khi consumer đọc cờ → consumer thấy true và bỏ qua park.
- Consumer đọc false, producer công bố/unpark, rồi consumer mới park → permit đã cấp giúp park đi tiếp, consumer kiểm tra lại và thấy true.

Nếu `park` spurious return khi cờ vẫn false, vòng tiếp tục chờ. Nếu consumer bị interrupt trước khi thấy cờ, code thoát theo policy của ví dụ.

**Ghi chú:** tham số string của `park(blocker)` chỉ là **metadata để debug**, không phải lock, payload hay object cần unpark. `unpark` vẫn nhận chính `Thread` đích.

## 6. Không nhả monitor khi gọi `park`

Khác với `Object.wait()` và `Condition.await()`, `LockSupport.park()` **không nhả monitor hoặc `ReentrantLock` mà caller đang giữ**.

Ví dụ dễ deadlock:

```java
synchronized (lock) {
    while (!ready) {
        LockSupport.park();
    }
}
```

Snippet này giả định producer cũng cần `synchronized(lock)` để chuyển `ready=true`. Worker đang park nhưng **vẫn sở hữu monitor `lock`**, nên producer bị BLOCKED và không thể thay state để giúp worker đi tiếp.

Mẫu phù hợp với intrinsic monitor là:

```java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
}
```

Đoạn nằm trong method có `throws InterruptedException`. `Object.wait()` nhả đúng monitor của object được gọi `wait`, sau đó lấy lại monitor trước khi trở về. Producer thay predicate và `lock.notifyAll()` trong cùng monitor.

Với `ReentrantLock` và `Condition`:

```java
lock.lock();
try {
    while (!ready) {
        condition.await();
    }
} finally {
    lock.unlock();
}
```

Snippet nằm trong method khai báo `throws InterruptedException`; `condition` được tạo bằng `lock.newCondition()`. `await()` nhả associated lock trong lúc chờ và lấy lại trước khi return. **Không thay `await` bằng `park` bên trong critical section** mà hy vọng nó cũng nhả lock.

## 7. Java 17: interrupt đánh thức park mà không ném exception

Tạo tệp `ParkInterruptExample.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.locks.LockSupport;

public class ParkInterruptExample {
    public static void main(String[] args) throws Exception {
        CountDownLatch started = new CountDownLatch(1);
        AtomicBoolean sawInterrupt = new AtomicBoolean(false);

        Thread worker = new Thread(() -> {
            started.countDown();
            while (!Thread.currentThread().isInterrupted()) {
                LockSupport.park();
            }
            sawInterrupt.set(true);
        }, "worker");

        worker.start();
        if (!started.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Worker not started");
        }

        worker.interrupt();
        worker.join(5_000);
        if (worker.isAlive()) {
            throw new IllegalStateException("Worker did not stop");
        }

        System.out.println("interruptObserved=" + sawInterrupt.get());
    }
}
```

```bash
javac ParkInterruptExample.java
java ParkInterruptExample
```

Stdout khi hoàn thành bình thường:

```text
interruptObserved=true
```

Nếu main interrupt **trước** khi worker gọi park, cờ đã bật và vòng có thể thoát ngay. Nếu interrupt xảy ra **trong lúc** worker park, park trở về và điều kiện vòng thấy cờ true. Nếu park tự thức dậy sớm, điều kiện vẫn false rồi worker chờ tiếp. Kết quả không dựa vào việc scheduler chọn chính xác mốc nào.

`Thread.currentThread().isInterrupted()` chỉ đọc cờ; `Thread.interrupted()` đọc **và xóa** cờ của thread hiện tại. Đừng vô ý dùng method thứ hai khiến code gọi bên ngoài bỏ lỡ yêu cầu hủy.

## 8. `parkNanos`, `parkUntil` và thời hạn chờ

Các overload:

| API | Ý nghĩa |
| --- | --- |
| `LockSupport.park()` | Chờ không chỉ định thời hạn |
| `LockSupport.park(Object blocker)` | Chờ và gắn blocker cho diagnostics |
| `LockSupport.parkNanos(long nanos)` | Chờ theo khoảng thời gian **tương đối dương** |
| `LockSupport.parkNanos(Object blocker, long nanos)` | Tương tự, có blocker |
| `LockSupport.parkUntil(long deadline)` | Chờ tới mốc **epoch milliseconds tuyệt đối** |
| `LockSupport.parkUntil(Object blocker, long deadline)` | Tương tự, có blocker |
| `LockSupport.unpark(Thread t)` | Cấp permit cho t, có thể làm park đang chờ trở về |

**`parkNanos(0)` không giống `Object.wait(0)`.** Với `parkNanos`, duration không dương không tạo khoảng park hữu ích; `Object.wait(0)` lại có nghĩa chờ vô thời hạn.

Nếu muốn timeout 200 ms theo duration, dùng monotonic `System.nanoTime()`, tính remaining sau mỗi lần thức:

```java
long deadline =
        System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(200);

while (!ready.get()) {
    long remaining = deadline - System.nanoTime();
    if (remaining <= 0) {
        return false;
    }
    LockSupport.parkNanos(remaining);
    if (Thread.currentThread().isInterrupted()) {
        return false;
    }
}
return true;
```

Snippet trong method `boolean` với `ready` là `AtomicBoolean`, cần import `TimeUnit` và `LockSupport`. `parkNanos` có thể trở về **trước** khi timeout vì unpark, interrupt hoặc spurious return; phải kiểm tra predicate và thời gian mỗi vòng. Scheduler không bảo đảm sẽ chạy thread **ngay đúng** mốc timeout. Với timeout cực lớn cần xét overflow của `nanoTime()+timeout`.

`parkUntil(deadline)` dùng epoch milliseconds (thường tính từ `System.currentTimeMillis()`), không phải duration nanoseconds. Vì dùng mốc đồng hồ lịch, việc điều chỉnh wall clock có thể ảnh hưởng chờ; khi đo duration tương đối, `parkNanos` và `nanoTime` thường dễ suy luận hơn.

## 9. `park(blocker)` và `getBlocker` chỉ phục vụ quan sát

Ví dụ:

```java
LockSupport.park(waitQueue);
Object blocker = LockSupport.getBlocker(worker);
```

Đây là snippet, `waitQueue` là object mô tả lý do chờ, `worker` là thread đích. `blocker` **không phải monitor đang được khóa**, không chứa permit và không phải tham số dùng cho `unpark`. Nó giúp JFR/thread dump và người debug hiểu worker đang đợi điều gì.

`getBlocker(worker)` có thể trả object blocker khi worker đang park qua overload có blocker, hoặc `null` nếu worker không còn park, vừa đổi trạng thái hay park không có blocker. **Không dùng getBlocker làm tín hiệu đồng bộ**, vì chỉ là snapshot và có race.

Một thread đang đợi trong `LockSupport.park()` thường có trạng thái Java `WAITING (parking)`; timed park có thể xuất hiện `TIMED_WAITING`. Không kết luận deadlock chỉ từ một lần thấy WAITING: thread pool worker rảnh đang park là bình thường. Đọc stack trace, blocker, predicate và nguồn phát tín hiệu.

## 10. So sánh với các primitive Java khác

| Cơ chế | Gắn với gì? | Nhả lock khi chờ? | Có đếm nhiều phần tử/permit không? |
| --- | --- | --- | --- |
| `park/unpark` | Permit một-bit của **thread** | **Không** | Không |
| `Object.wait/notifyAll` | Wait set của object monitor | Nhả đúng monitor được gọi `wait` | Không chứa queue job |
| `Condition.await/signalAll` | Condition gắn với `Lock` | Nhả associated lock, lấy lại sau | Không chứa queue job |
| `Thread.sleep` | Khoảng thời gian | Không | Không |
| `Thread.join` | Vòng đời thread khác | Không tự nhả mọi monitor caller đang giữ | Không |
| `CountDownLatch` | Bộ đếm một chiều | Không nhả monitor tùy ý | Có counter tới 0 |
| `Semaphore` | Giấy phép truy cập tài nguyên | Không nhả monitor tùy ý | **Có** permit số lượng |
| `BlockingQueue` | Queue chứa payload | Quản lý synchronization bên trong | **Có** phần tử |

**Ưu tiên abstraction cấp cao**: muốn truyền nhiều công việc thì dùng `BlockingQueue`; giới hạn N task thì dùng `Semaphore`; đợi N sự kiện hoàn tất thì `CountDownLatch`; chờ predicate dưới mutex thì `Condition` hoặc `wait`. `LockSupport` phù hợp khi xây một synchronizer cấp thấp, có cơ chế state và waiter queue riêng.

Các implementation dựa trên `AbstractQueuedSynchronizer` có thể dùng park/unpark bên trong để đỗ worker, nhưng chúng còn cần atomic state, queue waiter, cancellation, interruption và memory semantics. **Không thể chỉ thay một synchronized block bằng một lệnh park để tạo được mutex**.

## 11. Race giữa kiểm tra predicate và park

Giả sử consumer thực hiện:

```java
while (!hasWork.get()) {
    LockSupport.park();
}
```

Producer thực hiện:

```java
hasWork.set(true);
LockSupport.unpark(worker);
```

Đây là hai snippets, `hasWork` là `AtomicBoolean`; `worker` đã start và không có lời gọi park trung gian bất ngờ.

- Producer đặt true trước khi consumer đọc → consumer không park.
- Consumer đọc false, producer đặt true/unpark, rồi consumer park → permit cấp sớm giúp nó trở về và kiểm tra lại true.
- Consumer park trước → producer unpark, consumer tỉnh và đọc true.
- Consumer spurious return → nếu false, nó park lại.
- Consumer bị interrupt → phải xử lý interruption, nếu không vòng có thể spin do park trả ngay.

Một permit **còn dư** nếu consumer thấy true mà không cần park có thể làm một lời gọi park khác về sau trả ngay một lần. Đây không phải một job thừa. Thuật toán chính xác luôn tin **predicate** thay vì số lần thức dậy.

**Không xem cờ boolean là queue đa phần tử.** Nếu nhiều producer/consumer cùng sửa số lượng job, cần một queue/counter có atomicity phù hợp, chứ không chỉ cờ và permit.

## 12. Memory ordering: permit không thay Java Memory Model

Một chương trình đúng cần hai tầng:

1. **Trạng thái được công bố an toàn:** dùng `volatile`, atomic, synchronized, lock hoặc operation của concurrent collection với memory consistency được JDK quy định.
2. **Cơ chế đánh thức:** gọi unpark đúng thread có thể đang chờ để nó kiểm tra lại trạng thái.

Ví dụ:

```java
// Producer:
payload = 42;
ready.set(true);
LockSupport.unpark(consumer);

// Consumer:
while (!ready.get()) {
    LockSupport.park();
}
consume(payload);
```

Đây là snippet, với `ready` là `AtomicBoolean`. Ghi payload trước `ready.set(true)` và đọc `ready.get()==true` trước khi dùng payload tạo happens-before cần thiết. Chỉ có `unpark` mà không có giao thức visibility cho mutable state thì không thể suy luận mọi thao tác đọc/ghi đều an toàn.

Nếu payload tiếp tục bị sửa sau khi ready true, công bố một lần **không** làm các lần sửa sau trở thành an toàn. Cần immutable snapshot, queue, lock hoặc atomic update đúng phạm vi invariant.

## 13. Java 21+ virtual threads và LockSupport

Virtual threads vẫn phải tuân thủ Java Memory Model. `park/unpark` có ý nghĩa với việc chờ/đánh thức virtual thread, trong khi runtime có thể quản lý mount/unmount trên carrier thread khác cách platform thread chờ OS. Chi tiết pinning và diagnostics phụ thuộc phiên bản JDK; **không suy ra mỗi virtual thread park tương ứng một OS thread bị khóa**.

Dù là virtual hay platform thread, các nguyên tắc không đổi: predicate có visibility, xử lý spurious return/interrupt, không giữ khóa producer cần khi park, và đo đạc trên đúng runtime. Các chương trình của bài dùng Java 17, không cần virtual-thread API.

## 14. Những lỗi phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Gọi unpark N lần để ghi nhớ N công việc | Permit không cộng dồn | Queue/counter lưu job |
| Park trả về rồi làm việc ngay | Spurious return/interrupt | `while` kiểm tra predicate |
| Dùng field thường làm predicate không đồng bộ | Thiếu visibility | Volatile/atomic/lock |
| Park khi còn giữ monitor cần cho producer | Deadlock | `wait/Condition.await` hoặc nhả khóa |
| Nghĩ park tự nhả `ReentrantLock` | Khóa vẫn bị giữ | Chờ ngoài critical section |
| Unpark thread chưa start | Permit không được bảo đảm qua start | Start trước signal |
| Giữ permit qua blocking API khác | Park trung gian có thể tiêu thụ | Dựa vào predicate |
| Bỏ qua interrupt | Vòng chờ có thể spin nóng | Xử lý cancellation |
| Dùng `Thread.interrupted()` khi chỉ muốn xem flag | Vô tình xóa cờ | `isInterrupted()` |
| `parkNanos(0)` như `Object.wait(0)` | Quy ước zero khác | Dùng `park()` khi không timeout |
| Truyền duration vào `parkUntil` | Sai đơn vị/ý nghĩa | Epoch milliseconds tuyệt đối |
| `getBlocker` như điều kiện quyết định | Snapshot không ổn định | Primitive đồng bộ thật |
| Dùng park/unpark như mutex | Không có mutual exclusion | `synchronized`/`Lock`/atomic |
| Dùng `Thread.sleep` để ép interleaving | Scheduling ngẫu nhiên | Latch/barrier |
| Thấy `WAITING` và kết luận deadlock | Worker idle vẫn có thể park | Đọc stack, blocker và predicate |

## 15. Debug thread park lâu: checklist

1. **Đang chờ predicate nào?** Có job, chờ khóa, chờ result, hay chờ shutdown?
2. **Ai đổi predicate?** Có mã producer chắc chắn thay đúng state trước khi signal không?
3. **Ai unpark?** Có target đúng `Thread` instance, đã start và còn sống?
4. **Có park trung gian?** Permit cấp sớm có bị một lời gọi park trong thư viện khác tiêu thụ?
5. **Predicate có visibility?** Atomic/volatile hoặc lock/happens-before đúng chưa?
6. **Thread có giữ lock?** Một worker đang park có đang giữ monitor/Lock producer cần?
7. **Interrupt flag?** Nếu bật, park trả ngay làm CPU nóng; nếu code nuốt interrupt, shutdown khó.
8. **Timed wait?** Đơn vị thời gian và deadline tính đúng chưa? Có tính lại remaining sau return?
9. **Diagnostics?** Xem `getBlocker`, JFR/thread dump, nhiều snapshot và trạng thái ứng dụng.
10. **Test điều phối?** Kiểm tra unpark-before-park, park-before-unpark, interrupt và spurious return giả lập bằng vòng kiểm tra predicate.
11. **Có thể dùng primitive JDK cao cấp hơn?** Tránh tự cài synchronizer nếu không thật sự cần.

## 16. Câu hỏi tự kiểm tra

**1. `unpark(T)` ba lần rồi `T.park()` ba lần, có chắc cả ba đi tiếp ngay?** Không. Permit tối đa một. Lần park sau có thể chờ (dù có thể tự trở về spurious).

**2. Unpark trước park có phải luôn an toàn?** Permit có thể cấp trước park, nhưng phải xét thread đã start, không có park trung gian tiêu thụ và predicate được đồng bộ.

**3. Park trở về có chắc có job?** Không. Có thể do permit, interrupt hoặc spurious return. Dùng predicate thật.

**4. Park có nhả monitor không?** Không. `Object.wait`/`Condition.await` mới nhả associated lock theo API.

**5. `park` có ném `InterruptedException`?** Không. Nó có thể trở về với interrupt flag vẫn bật.

**6. `parkNanos(0)` giống `Object.wait(0)`?** Không. `parkNanos` không chờ hữu ích với thời lượng không dương; `Object.wait(0)` là vô thời hạn.

**7. Blocker trong `park(blocker)` có phải object để unpark?** Không. `unpark` nhận `Thread`, blocker chỉ giúp diagnostics.

**8. `Semaphore` permit khác `LockSupport` permit ra sao?** Semaphore đếm giấy phép tài nguyên; LockSupport chỉ có permit một-bit trên mỗi thread cho park.

**9. Có thể dùng LockSupport để bảo vệ `count++` không?** Không. Nó không tạo mutual exclusion hay atomic read–modify–write.

**10. Worker bị interrupt và vòng chỉ viết `while (!ready) park()` có thể tốn CPU?** Có. Vì park có thể trả ngay khi interrupt flag đang bật.

**11. Vì sao cần atomic/volatile flag trước khi unpark?** Để công bố dữ liệu/điều kiện theo Java Memory Model; permit chỉ là wakeup.

**12. Vì sao `BlockingQueue` dễ dùng hơn tự ghép ArrayList và permit?** Nó cung cấp lưu item, phối hợp thread và memory consistency trong cùng hợp đồng, tránh lost work và race trên collection.

## 17. Tổng kết áp dụng

**LockSupport permit không phải job, mutex hoặc quota.** Nó là **quyền chờ/đánh thức tối đa một lần chưa tiêu thụ cho một thread**. `unpark` đến trước `park` vẫn có tác dụng theo hợp đồng, nhưng không tích nhiều permit và có thể bị tiêu thụ bởi một park trung gian. `park` không nhả khóa đang giữ, không ném `InterruptedException` và có thể tự trở về.

Để dùng đúng, cần **predicate được công bố an toàn**, kiểm tra điều kiện bằng vòng `while` sau khi park, chính sách interrupt/timeout rõ ràng và một data structure thực sự lưu trạng thái nghiệp vụ. Khi có thể, ưu tiên `BlockingQueue`, `Semaphore`, `CountDownLatch` hoặc `Condition`; dùng `LockSupport` trực tiếp khi có lý do thiết kế synchronizer cấp thấp.