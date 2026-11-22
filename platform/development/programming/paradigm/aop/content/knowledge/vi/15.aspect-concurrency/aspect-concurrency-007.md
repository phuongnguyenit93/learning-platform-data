# Khóa trong advice và nguy cơ deadlock hoặc tăng tranh chấp

## 1. Khi concern cắt ngang vô tình trở thành nút thắt

Trong lập trình hướng khía cạnh (**Aspect-Oriented Programming — AOP**), **pointcut** chọn các *join point* mà công cụ cho phép can thiệp; **advice** bổ sung hành vi tại các điểm ấy, chẳng hạn logging, audit, metrics, phân quyền, retry, cache hoặc quản lý tài nguyên. Một aspect có thể được áp cho rất nhiều target methods và nhiều threads đồng thời. Vì vậy, chỉ một thao tác khóa tưởng như nhỏ trong advice cũng có thể trở thành **điểm nghẽn của cả ứng dụng**.

Ví dụ một around advice đo thời gian nhưng sử dụng **một khóa dùng chung**:

~~~text
Request A ----> [LOCK global] ---> advice.before
                                   |
                                   +-- proceed() ----> Target A
                                   |                   (gọi DB/HTTP, mất 500 ms)
                                   |
                                   +-- advice.after ---> [UNLOCK]

Request B ----> [WAIT global] ------------------------> chỉ được vào sau A
Request C ----> [WAIT global] ------------------------> chờ sau B ...
~~~

Nếu giữ khóa **xuyên suốt lời gọi `proceed()`**, mọi hoạt động mục tiêu — kể cả I/O hoặc lời gọi tới aspect khác — trở thành **một phần của critical section**. Thời gian nắm giữ khóa không còn chỉ là thời gian cập nhật biến đếm; nó phụ thuộc thời gian của toàn bộ nghiệp vụ.

Hai hậu quả lớn:

1. **Contention (tranh chấp):** nhiều requests cùng cần khóa nên phải chờ, throughput giảm và tail latency tăng.
2. **Deadlock (bế tắc):** hai hoặc nhiều threads giữ khóa/tài nguyên khác nhau rồi chờ vòng tròn; nếu không có cơ chế timeout/interrupt/recovery tương ứng, tiến trình xử lý có thể đứng mãi.

Ngoài ra còn có **starvation (đói tài nguyên)**, **priority inversion**, lock convoys và các failure modes liên quan shutdown/async. Bài học phân tích chúng trong ngữ cảnh **khóa được sử dụng bên trong advice hoặc interceptor**, không giới hạn ở một công nghệ AOP cụ thể.

**Nguyên tắc quan trọng:** thiết kế advice nên coi `proceed()` là **mã không nằm dưới quyền kiểm soát trực tiếp của advice**. Nếu giữ một lock qua `proceed()`, advice đang giữ lock trong khi gọi một thành phần có thể gọi lại, chờ I/O, lấy lock khác, ném ngoại lệ hoặc chuyển việc sang thread khác.

## 2. Các thuật ngữ và sự khác biệt

| Khái niệm | Ý nghĩa chính | Dấu hiệu |
| --- | --- | --- |
| **Lock / mutex** | Điều phối quyền vào critical section của một tài nguyên | Một thread giữ, thread khác phải đợi hoặc bị từ chối |
| **Critical section** | Đoạn code phải được bảo vệ vì truy cập trạng thái chia sẻ | Đọc-sửa-ghi cấu trúc mutable |
| **Lock scope** | Phạm vi thời gian từ acquire đến release | Scope càng rộng, càng dễ contention |
| **Lock ownership** | Thread/ngữ cảnh đang chịu trách nhiệm release | Phải rõ ai nắm và ai mở |
| **Contention** | Nhiều bên cạnh tranh cùng một lock | BLOCKED/WAITING, queue, p95/p99 tăng |
| **Deadlock** | Các bên mắc kẹt trong chu trình chờ tài nguyên | Không có progress dù công việc còn |
| **Starvation** | Một bên không được phục vụ đủ lâu vì scheduling hoặc cạnh tranh | Một số requests trễ bất thường |
| **Priority inversion** | Bên ưu tiên cao bị kẹt sau bên ưu tiên thấp đang giữ tài nguyên | Tính phản hồi trái kỳ vọng |
| **Reentrancy** | Cùng thread có thể lấy lại cùng lock hỗ trợ tái nhập | Tránh self-deadlock một loại, không chữa lock inversion |
| **Lock ordering** | Quy tắc thứ tự nhất quán khi cần nhiều locks | Luôn lấy A trước B |
| **Try-lock / timed acquire** | Không chờ vô hạn; thất bại/timeout nếu không lấy được lock | Giúp tránh chờ không kiểm soát |
| **Lock convoy** | Nhiều threads nối hàng sau một holder chậm | Latency tăng dây chuyền |
| **Happens-before** | Quan hệ bộ nhớ theo Java Memory Model | Giúp thấy write, không đồng nghĩa deadlock-free |

### 2.1. Contention không phải deadlock

Nếu A đang giữ khóa 50 ms, B chờ 50 ms rồi tiếp tục, đó là contention bình thường. Nếu A giữ khóa X chờ Y, còn B giữ Y chờ X, cả hai có thể không bao giờ đi tiếp: đó là deadlock thực.

Một **timeout** có thể giải phóng hoặc báo lỗi cho một phía, nhưng nó không làm thuật toán tự đúng: retry ngay có thể tạo livelock hoặc làm tăng tải. Cần hợp đồng xử lý khi không lấy được khóa.

### 2.2. Starvation cũng khác deadlock

Một thread có thể chờ rất lâu vì các thread khác liên tục thắng lock dù ứng dụng vẫn có progress. Đây là **starvation**, không nhất thiết có vòng chờ bế tắc. `ReentrantLock` có tùy chọn fairness nhưng lock công bằng thường có đánh đổi về throughput; `tryLock()` không tham gia cùng mọi chính sách fairness như blocking acquisition.

### 2.3. Scope của khóa khác scope của aspect

Một aspect instance có thể là global/shared, per-target hoặc per-invocation; nhưng **một lock object cụ thể** mới quyết định ai cạnh tranh với ai. Hai aspects khác nhau có thể cùng dùng một lock; hai instances của cùng aspect có thể giữ các locks riêng. Ngược lại, một static lock có thể bao nhiều target trong cùng vùng classloader/runtime scope.

Không được suy từ “có một aspect definition” rằng “chỉ có một mutex toàn hệ thống”.

## 3. Cấu trúc advice rủi ro nhất: giữ khóa qua `proceed()`

Đoạn sau là **pseudocode Java**, không phải chương trình độc lập:

~~~java
Object around(Proceed next) throws Throwable {
    globalLock.lock();
    try {
        auditBefore();
        Object result = next.proceed();
        auditAfter(result);
        return result;
    } finally {
        globalLock.unlock();
    }
}
~~~

Trông có vẻ cẩn thận vì đã `unlock()` trong `finally`. Nó giải quyết việc **rò lock khi method ném lỗi bình thường**, nhưng **không** giải quyết vấn đề **nắm khóa quá lâu**.

Trong lúc giữ `globalLock`:

- `auditBefore()` có thể gọi một client logging chậm.
- `next.proceed()` có thể gọi DB, network hoặc chờ một lock khác.
- Một advice bên trong có thể thực hiện retry và gọi target nhiều lần.
- Target có thể gọi ngược vào code cần `globalLock` từ **thread khác**.
- Một callback bất đồng bộ có thể phải chờ `globalLock` trước khi đánh thức thread đang giữ nó.
- `auditAfter()` có thể gửi dữ liệu ra ngoài và làm kéo dài thời gian giữ khóa.

Vì vậy, **dùng `finally` là điều kiện cần để release đúng, không phải bằng chứng critical section đã thiết kế hợp lý**.

### 3.1. Phạm vi khóa nên đủ nhỏ để bảo vệ invariant

Một mẫu tốt hơn cho metrics đơn giản:

~~~java
long startNanos = System.nanoTime();
try {
    return next.proceed();
} finally {
    durationCounter.add(System.nanoTime() - startNanos);
}
~~~

Đây là **mã minh họa**: `next` và `durationCounter` cần được cung cấp; giả sử `durationCounter` là một cấu trúc cập nhật đồng thời phù hợp (ví dụ `LongAdder`). Thời điểm đo là **local variable theo invocation**, không cần lock giữ qua toàn target.

Nếu thật sự cần cập nhật shared state phức tạp, hãy **chỉ khóa khi đọc-sửa-ghi phần state đó**, rồi release **trước khi** gọi `proceed()` nếu hợp đồng nghiệp vụ cho phép. Không giải phóng sớm khi nó phá invariant cần bảo vệ; khi không thể làm hẹp scope, có thể phải đổi kiến trúc hoặc ownership thay vì chỉ xóa lock.

## 4. Lock-order inversion: cách deadlock phát sinh từ nhiều aspect

Giả sử hai concerns có khóa riêng:

- `Lock A` dùng để bảo vệ audit registry.
- `Lock B` dùng để bảo vệ cache metadata.

Hai đường gọi có thể tạo thứ tự đối nghịch:

~~~text
Thread T1 (call path X)        Thread T2 (call path Y)
----------------------         ----------------------
acquire A                      acquire B
proceed -> ask for B           proceed -> ask for A
WAIT for B                     WAIT for A
(holding A)                    (holding B)
~~~

Đây là **circular wait**. Không quan trọng khóa được đặt trong hai aspects riêng hay target; đường gọi tổng thể mới quyết định thứ tự thực.

### 4.1. Bốn điều kiện thường dùng để nhận diện deadlock

Bộ điều kiện Coffman mô tả deadlock tài nguyên có thể xảy ra khi cùng tồn tại:

1. **Mutual exclusion**: một tài nguyên không được chia sẻ đồng thời.
2. **Hold and wait**: đang giữ tài nguyên này trong khi chờ tài nguyên khác.
3. **No preemption**: tài nguyên không bị thu hồi cưỡng bức an toàn.
4. **Circular wait**: có chu trình bên giữ/chờ lẫn nhau.

Phá một điều kiện là một chiến lược phòng tránh; trong ứng dụng Java, chiến lược hay dùng là **thống nhất thứ tự khóa** hoặc **không giữ khóa trong lúc chờ lời gọi ngoài/lock khác**.

### 4.2. Thứ tự khóa nhất quán

Nếu mọi đường đi cần cả A và B đều làm:

~~~text
acquire A
  acquire B
    critical operation
  release B
release A
~~~

thì chu trình A→B và B→A bị loại bỏ **đối với chính hai khóa và mọi đường tuân thủ quy tắc này**.

Lưu ý: một quy tắc lock ordering **không tự phòng deadlock trên tài nguyên khác**, ví dụ DB locks hoặc thread pool, nếu các đường chờ đó vẫn có vòng. Cần xem toàn bộ đồ thị phụ thuộc ở mức hệ thống.

### 4.3. Trật tự advice có thể tạo trật tự khóa

Giả sử `AUDIT` bao `CACHE`:

~~~text
AUDIT: lock A
   proceed() -> CACHE: lock B
   CACHE: unlock B
AUDIT: unlock A
~~~

Đường này có thứ tự A→B. Nếu ở một join point khác `CACHE` đứng ngoài `AUDIT`, đường thứ hai có thể yêu cầu B→A và tạo deadlock khi chạy đồng thời.

Vì vậy **precedence của các aspects** không chỉ đổi thứ tự log; nó có thể đổi lock graph. Không được giả định source declaration order luôn là precedence; phải kiểm tra engine và cấu hình thứ tự thực sự.

## 5. Reentrancy: khóa tái nhập không có nghĩa an toàn mọi nơi

Java intrinsic monitor (qua `synchronized`) là **reentrant**. `ReentrantLock` cũng cho phép **cùng thread** nắm lại lock của mình, giữ một hold count rồi release tương ứng.

Ví dụ minh họa:

~~~java
synchronized void first() {
    second();
}
synchronized void second() {
    // Cùng monitor trên this: cùng thread có thể vào lại.
}
~~~

Đoạn này nằm trong ngữ cảnh instance class và dùng để minh họa cú pháp, không phải chương trình độc lập. Nếu `first()` và `second()` đều khóa trên `this` của **cùng object**, cùng thread có thể vào `second` khi còn giữ monitor.

Nhưng:

- **Reentrant không có nghĩa không deadlock:** T1 giữ A cần B; T2 giữ B cần A vẫn có thể kẹt.
- **Reentrant không có nghĩa không contention:** threads khác vẫn phải chờ holder.
- **Reentrant không có nghĩa trạng thái advice theo invocation tự an toàn:** một instance dùng chung có thể có field mutable bị recursion ghi đè.
- **Reentrant không sửa được callback khác thread:** nếu một thread giữ lock rồi chờ Future mà Future completion cần lock từ thread khác, callback có thể không chạy.
- **Reentrancy không chống lỗi đếm hold:** với `ReentrantLock`, mỗi lần lock thành công cần một lần unlock phù hợp.

Với recursion hoặc nested join points, ngoài lock cần kiểm tra **per-invocation context và ordering** để tránh advice tái nhập vô hạn.

## 6. Trong advice có nên dùng `synchronized` hay `ReentrantLock`?

| Thuộc tính | Intrinsic monitor (`synchronized`) | `ReentrantLock` |
| --- | --- | --- |
| Tái nhập trên cùng thread | Có | Có |
| Thả khi thoát critical section | JVM thả khi ra khỏi monitor block/method | Người viết phải gọi `unlock` trong `finally` |
| Timed lock acquisition | Không có tham số timeout trực tiếp cho `synchronized` | Có `tryLock(timeout, unit)` |
| Lock interruptibly | Không hỗ trợ interrupt blocking monitor acquisition theo cách `lockInterruptibly` | Có `lockInterruptibly()` |
| Nonblocking attempt | Không có `tryMonitorEnter` trong API Java thông thường | Có `tryLock()` |
| Fairness option | Không đặt fairness bằng tham số monitor | `ReentrantLock(boolean fair)` |
| Condition variables | `wait/notify/notifyAll` trên monitor | `newCondition()` với `await/signal` |
| Diagnostic/metrics | Có trạng thái monitor trong thread dumps | Ownable synchronizers có thể được JVM tooling quan sát |
| Nguy cơ thiết kế | Hold quá rộng, lock order inversion, deadlock | Tương tự, cộng thêm lỗi quên `unlock` |

**Không có lựa chọn nào tự tốt hơn trong mọi tình huống.** Nếu một counter dùng `LongAdder` hay `AtomicLong` là đủ, mutex còn có thể không cần. Nếu cần một invariant nhiều fields, mutex hoặc một cấu trúc immutable publication có thể thích hợp hơn.

### 6.1. `tryLock()` không đồng nghĩa giữ an toàn tự động

~~~java
if (!lock.tryLock()) {
    throw new IllegalStateException("busy");
}
try {
    updateProtectedState();
} finally {
    lock.unlock();
}
~~~

Đây là **pseudocode Java không độc lập** vì `lock` và `updateProtectedState()` chưa được định nghĩa. Nó cho thấy nonblocking acquisition, nhưng việc **thất bại lấy lock** là một nhánh chức năng mới. Với thao tác tiền tệ hay quyền truy cập, không thể trả success giả hoặc bỏ update vì `tryLock()` thất bại; cần chính sách rõ: retry, queue, error/busy response hoặc một cách tổ chức khác.

### 6.2. Timed lock acquisition

~~~java
boolean acquired = lock.tryLock(200, TimeUnit.MILLISECONDS);
if (!acquired) {
    throw new TimeoutException("lock acquisition timed out");
}
try {
    updateProtectedState();
} finally {
    lock.unlock();
}
~~~

Mã là **minh họa không độc lập**, cần imports, `lock` và method body phù hợp. `tryLock(timeout, unit)` có thể ném `InterruptedException`, vì vậy một API chứa đoạn này phải khai báo hoặc xử lý; `TimeoutException` trong `java.util.concurrent` cũng là checked exception.

Timeout giúp **giới hạn thời gian chờ** trong một đường code nhưng **không chứng minh thao tác đã/ chưa commit** ở những tài nguyên khác. Đừng timeout rồi gọi lại một operation có side effects mà không biết trạng thái.

## 7. Bốn nguy cơ khi khóa được lắp vào concern cắt ngang

### 7.1. Tạo khóa global ngoài ý định

Một metrics advice có thể được gắn vào mọi repository/service method. Nếu tất cả dùng cùng `static synchronized` method để ghi sample, hàng trăm đường gọi độc lập trở thành một queue cho một monitor.

**Hệ quả:** throughput của toàn ứng dụng phụ thuộc một critical section, dù nghiệp vụ thực tế có thể xử lý song song.

Giải pháp có thể là **LongAdder**, per-thread/per-core buffering, batch export, hoặc một worker tiếp nhận events qua queue. Phải đánh giá độ chính xác của counters, backpressure và memory, không mặc định queue luôn tốt hơn.

### 7.2. Giữ lock khi làm I/O

Bên trong advice có thể ghi log đến disk, gửi HTTP telemetry hoặc gọi một secret provider. I/O có tail latency rất lớn; nếu còn giữ lock, các request khác phải chờ theo thời gian của call chậm nhất.

Giải pháp: snapshot dữ liệu tối thiểu dưới lock, release, sau đó thực hiện I/O nếu hợp đồng cho phép. Nếu cần bảo đảm thứ tự/atomicity giữa update và I/O, dùng cơ chế queue/outbox/sequence chuyên biệt chứ không chỉ mở rộng một Java mutex qua network.

### 7.3. Gọi callback hoặc `proceed()` trong lock

Callback có thể thực thi bất kỳ code đã đăng ký, lấy lock khác hoặc gọi quay về component ban đầu. `proceed()` còn có thể chứa toàn bộ aspect chain.

Vì vậy **khóa trước khi gọi code bên ngoài phạm vi kiểm soát** là một rủi ro lớn. Chỉ làm vậy khi đã phân tích toàn bộ lock graph, có yêu cầu nhất quán cụ thể và không tồn tại cách thiết kế hẹp hơn.

### 7.4. Khóa để “sửa” race nhưng làm nghẽn cả hệ thống

Một mutable field `startedAt` trên shared timing aspect có thể bị threads ghi đè. Bọc **toàn target** trong khóa đúng là làm hai calls không xen kẽ, nhưng cũng phá concurrency của target.

Giải pháp đúng về scope là **lưu mốc thời gian trong local variable per invocation**. Cần sửa mô hình trạng thái trước khi tăng đồng bộ hóa cưỡng bức.

## 8. Ví dụ Java 17 hoàn chỉnh: contention, lock inversion và giải pháp

Ví dụ này dùng **JDK thuần**, không sửa bytecode và không tự nhận là một AOP engine. Hàm `lockedAdvice` đóng vai một around wrapper để minh họa vì sao nắm khóa xuyên `next.call()` có hại.

Bốn kiểm thử:

1. **HELD_ACROSS_PROCEED:** thread A giữ `gate` khi `next.call()` chờ tín hiệu; thread chính thử lấy cùng `gate` bằng `tryLock` và bị từ chối. Đây là **contention có kiểm soát**.
2. **EXCEPTION:** `next.call()` ném `IllegalArgumentException`; `finally` vẫn release `gate`, caller nhận lỗi gốc.
3. **INVERSION:** hai threads giữ hai locks khác nhau, sau đó mỗi bên `tryLock` khóa đang bị bên kia giữ. Cả hai lần thử thất bại. Nếu thay `tryLock` bằng blocking `lock` ở chính hai vị trí, đường chờ sẽ có nguy cơ deadlock. Demo **không để hai threads thật sự deadlock**.
4. **ORDERED:** hai threads cùng lấy lock theo thứ tự trái→phải; cả hai hoàn tất mà không có lock-order inversion trong phép thử.

`CountDownLatch` buộc những điểm tương tranh diễn ra xác định để output không phụ thuộc việc `Thread.sleep()` may mắn tạo race. Lệnh `join(5000)` và chờ latch hữu hạn giúp test không treo vô hạn trong điều kiện chạy bình thường.

Tạo file `AdviceLockingDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.locks.ReentrantLock;

public final class AdviceLockingDemo {
    @FunctionalInterface
    interface Proceed { String call() throws Exception; }

    static String lockedAdvice(ReentrantLock gate, Proceed next)
            throws Exception {
        gate.lock();
        try {
            return next.call();
        } finally {
            gate.unlock();
        }
    }

    static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    static void await(CountDownLatch latch) throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new AssertionError("latch timeout");
        }
    }

    static void inverseAttempt(ReentrantLock first, ReentrantLock second,
                               CountDownLatch firstHeld,
                               CountDownLatch bothAttempted,
                               AtomicInteger refused,
                               AtomicReference<Throwable> error) {
        first.lock();
        try {
            firstHeld.countDown();
            await(firstHeld);
            boolean acquired = second.tryLock();
            if (acquired) {
                second.unlock();
                throw new AssertionError("unexpected second lock acquisition");
            }
            refused.incrementAndGet();
            bothAttempted.countDown();
            await(bothAttempted);
        } catch (Throwable t) {
            error.compareAndSet(null, t);
        } finally {
            first.unlock();
        }
    }

    static void ordered(ReentrantLock first, ReentrantLock second,
                        AtomicInteger completed) {
        first.lock();
        try {
            second.lock();
            try {
                completed.incrementAndGet();
            } finally {
                second.unlock();
            }
        } finally {
            first.unlock();
        }
    }

    public static void main(String[] args) throws Exception {
        ReentrantLock gate = new ReentrantLock();
        CountDownLatch inside = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicReference<String> result = new AtomicReference<>();
        AtomicReference<Throwable> workerError = new AtomicReference<>();
        Thread worker = new Thread(() -> {
            try {
                result.set(lockedAdvice(gate, () -> {
                    inside.countDown();
                    await(release);
                    return "done";
                }));
            } catch (Throwable t) {
                workerError.set(t);
            }
        }, "locked-advice");
        worker.start();
        await(inside);
        boolean competitorBlocked = !gate.tryLock();
        if (!competitorBlocked) gate.unlock();
        release.countDown();
        worker.join(5000);
        require(!worker.isAlive(), "worker did not stop");
        require(workerError.get() == null, "worker failed");
        require(competitorBlocked && "done".equals(result.get()),
                "lock was not held across proceed");
        System.out.println("HELD_ACROSS_PROCEED competitorBlocked=true");

        String errorMessage;
        try {
            lockedAdvice(gate, () -> {
                throw new IllegalArgumentException("invalid");
            });
            throw new AssertionError("expected business exception");
        } catch (IllegalArgumentException ex) {
            errorMessage = ex.getMessage();
        }
        require(!gate.isLocked(), "lock leaked after exception");
        System.out.println("EXCEPTION lockReleased=true error=" + errorMessage);

        ReentrantLock left = new ReentrantLock();
        ReentrantLock right = new ReentrantLock();
        CountDownLatch bothHeld = new CountDownLatch(2);
        CountDownLatch bothTried = new CountDownLatch(2);
        AtomicInteger refused = new AtomicInteger();
        AtomicReference<Throwable> inversionError = new AtomicReference<>();
        Thread a = new Thread(() -> inverseAttempt(left, right, bothHeld,
                bothTried, refused, inversionError), "left-then-right");
        Thread b = new Thread(() -> inverseAttempt(right, left, bothHeld,
                bothTried, refused, inversionError), "right-then-left");
        a.start();
        b.start();
        a.join(5000);
        b.join(5000);
        require(!a.isAlive() && !b.isAlive(), "inversion threads stuck");
        require(inversionError.get() == null, "inversion test failed");
        require(refused.get() == 2, "expected two refusals");
        System.out.println("INVERSION tryLockFailures=2");

        AtomicInteger completed = new AtomicInteger();
        Thread c = new Thread(() -> ordered(left, right, completed));
        Thread d = new Thread(() -> ordered(left, right, completed));
        c.start();
        d.start();
        c.join(5000);
        d.join(5000);
        require(!c.isAlive() && !d.isAlive(), "ordered threads stuck");
        require(completed.get() == 2, "expected two ordered completions");
        System.out.println("ORDERED completed=2");
        System.out.println("ALL ASSERTIONS PASSED");
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 AdviceLockingDemo.java
java AdviceLockingDemo
~~~

Đầu ra đã được kiểm chứng bằng biên dịch và chạy thực:

~~~text
HELD_ACROSS_PROCEED competitorBlocked=true
EXCEPTION lockReleased=true error=invalid
INVERSION tryLockFailures=2
ORDERED completed=2
ALL ASSERTIONS PASSED
~~~

### 8.1. Tại sao `competitorBlocked=true`?

`lockedAdvice` giữ `gate` và gọi `next.call()`. Code target mô phỏng báo `inside.countDown()`, sau đó chờ `release`. Main thread đã biết worker ở **bên trong `proceed`** khi thử `gate.tryLock()`.

Vì lock vẫn thuộc worker, main thread không lấy được lock. Đây là phép kiểm trực tiếp việc một advice giữ lock trong lúc target bị chặn. Không cần gây deadlock để chứng minh contention: chỉ một target chậm đã đủ khiến đường khác chờ.

### 8.2. Vì sao exception không làm leak lock?

`lockedAdvice` dùng `try/finally`. Khi `next.call()` ném `IllegalArgumentException`, stack unwinding đi qua `finally { gate.unlock(); }`. Caller bắt được lỗi `"invalid"` và `gate.isLocked()` là false.

**Bài học:** `finally` quan trọng để không rò lock, nhưng không làm mất rủi ro giữ khóa quá rộng khi target chạy lâu.

### 8.3. Vì sao cả hai lần `tryLock` đều thất bại?

Thread A giữ `left`; B giữ `right`. `bothHeld` bảo đảm cả hai đã lấy khóa đầu tiên. Sau đó A thử `right`, B thử `left`, đều đang thuộc thread còn lại.

`bothTried` khiến mỗi thread **tiếp tục giữ khóa đầu tiên** cho đến khi cả hai đã thử khóa thứ hai; nhờ đó không có race làm một thread release sớm rồi thread khác bất ngờ lấy được lock.

`tryLock()` ở đây không chờ. Nó trả false, nên hai threads có thể dọn dẹp và thoát. Nếu dùng `second.lock()` để chờ không giới hạn ở cùng vị trí, có thể tạo vòng chờ thật.

### 8.4. `ORDERED completed=2` nghĩa là gì?

Cả hai threads gọi `ordered(left,right,completed)`, nghĩa là luôn lấy **left rồi right**. Thread có thể phải chờ `left` nhưng không tạo đường `right→left` trong hai worker này. Khi mỗi thread vào cả hai critical sections, counter tăng; cuối test bằng 2.

Không suy rộng kết quả này thành “mọi hệ thống sẽ deadlock-free”: còn callback, locks khác, DB locks hoặc asynchronous dependencies nằm ngoài hai khóa được test.

### 8.5. Giới hạn của demo

- Đây là code Java trực tiếp mô phỏng around wrapper, **không phải bytecode weaving** và không có pointcut engine.
- Nó cố ý **không tạo deadlock thật**. Dùng blocking `lock()` thay `tryLock()` trong thử nghiệm inversion có thể khiến cả tiến trình treo; không làm vậy trong test suite bình thường.
- Các timeouts 5 giây giúp test có ngưỡng thoát, không phải SLA latency sản phẩm.
- `AtomicReference` và `AtomicInteger` dùng để chuyển status/đếm giữa threads trong demo; chúng không bảo vệ mọi business invariant.
- Nội dung output được in bởi main sau các joins nên không phụ thuộc thứ tự scheduling của các threads.
- Test không đo throughput thực tế. Performance phải được benchmark riêng dưới tải đại diện.
- Với failure khiến thread ở lại sau `join(5000)`, test ném `AssertionError`; một test harness sản xuất nên có timeout/cleanup cấp process để tránh có worker không kết thúc do bug mới.

## 9. Rút ngắn critical section đúng cách

Sai lầm hay gặp:

~~~java
globalLock.lock();
try {
    long start = System.nanoTime();
    Object value = next.proceed();
    metrics.add(System.nanoTime() - start);
    return value;
} finally {
    globalLock.unlock();
}
~~~

Đây là pseudocode chưa độc lập. Khóa đã bọc `proceed`, khiến một tác vụ DB/HTTP chậm chặn mọi caller cần cùng lock.

Nếu metrics chỉ cần cập nhật counter độc lập:

~~~java
long start = System.nanoTime();
try {
    return next.proceed();
} finally {
    metrics.add(System.nanoTime() - start);
}
~~~

Ở đây giả định `metrics.add` có concurrency contract phù hợp. Không có lock giữ qua target; `start` chỉ thuộc một invocation.

Nếu update cần đọc-sửa-ghi nhiều field:

~~~text
1. Lấy dữ liệu đầu vào cần thiết
2. Acquire lock bảo vệ state chung
3. Update invariant nhanh, không I/O
4. Release lock trong finally
5. Gọi external observer hoặc proceed ngoài lock, nếu hợp đồng cho phép
~~~

Thứ tự trên **không phải luôn hoán đổi được**. Nếu business yêu cầu một lock bảo vệ toàn operation, phải xem xét **phân vùng state, transaction resource, message passing hoặc thiết kế lại API**. Không chỉ “đưa proceed ra ngoài lock” mà vô tình phá atomicity bảo mật hay dữ liệu.

### 9.1. Snapshot rồi xuất event

Một advice ghi audit có thể copy một **snapshot bất biến** của metadata dưới lock, sau đó release rồi gửi tới queue. Việc gửi queue có thể lỗi: cần policy backpressure/drop/retry và phân biệt “đã xếp hàng” với “đã giao thành công”.

### 9.2. Granularity: một khóa global hay khóa theo key?

Nếu các invocations liên quan nhiều target độc lập, một lock toàn cục gây contention không cần thiết. Khóa theo `accountId`, `tenantId` hoặc target identity có thể cho phép parallelism giữa các keys.

Nhưng keyed locks cũng có các nguy cơ:

- Không được tạo vô hạn locks trong registry mà không có eviction.
- Nếu một operation cần nhiều keys, phải áp dụng **thứ tự ổn định** cho toàn bộ keys.
- Eviction trong lúc có thread đang dùng có thể tạo **hai locks khác nhau cho cùng key**, phá mutual exclusion.
- Hash-striping giảm số lock objects nhưng có thể gây **false contention** khi hai keys trùng stripe.
- Key phải chuẩn hóa và không chứa dữ liệu nhạy cảm trong logs.
- Với nhiều JVM nodes, per-key lock trong RAM không bảo vệ các node khác; có thể cần DB constraint/transaction/distributed coordination.

### 9.3. Dùng cấu trúc concurrency thay vì khóa thủ công

Nhu cầu | Gợi ý cân nhắc | Giới hạn cần nhớ
--- | --- | ---
Đếm sự kiện | `LongAdder` hoặc `AtomicLong` | LongAdder không phải một snapshot tuyến tính hóa hoàn hảo khi updates đang diễn ra
Giữ immutable config | `final`, immutable objects, safe publication | Thay cấu hình runtime cần chiến lược phiên bản hóa
Map concurrent | `ConcurrentHashMap` | Các cập nhật qua nhiều keys/objects không tự atomic cùng nhau
Serialize việc theo owner | Actor/single-thread queue | Queue tạo backlog/backpressure, tăng latency
Cập nhật nhiều fields đồng bộ | Lock có scope hẹp hoặc immutable snapshot | Phải đảm bảo mọi writer/readers cùng contract
Cross-process uniqueness | Database unique constraint/transaction | Phụ thuộc isolation và failure recovery
Giới hạn số tác vụ đồng thời | Semaphore/bulkhead | Đây là điều phối concurrency, không tự tạo atomicity nghiệp vụ

Không dùng một kỹ thuật chỉ vì nó “lock-free”. Các thuật toán CAS/retry cũng có thể tranh chấp mạnh, thất bại dưới tải cao hoặc không giữ invariant cần thiết.

## 10. Đổi lock order do advice precedence

Khi hai around advices cùng khớp method:

~~~text
Order 1: AUDIT(lock A) -> CACHE(lock B) -> TARGET
Order 2: CACHE(lock B) -> AUDIT(lock A) -> TARGET
~~~

Một công cụ AOP có thể có quy tắc precedence cho toàn bộ aspect hoặc advice. Cần kiểm:

- Thứ tự bên ngoài/bên trong của từng lời gọi.
- Có các pointcuts khác nhau áp thứ tự khác không.
- Một advice có short-circuit, nên đôi lúc **không bao giờ vào lớp trong**.
- Retry có gọi `proceed` nhiều lần trong lúc giữ outer lock không.
- Class đang được woven hay caller đi qua proxy nào.
- Aspect ở ranh giới call có thể gọi một method khác và tái nhập pointcut hay không.

Thứ tự lớp advice **chính là một phần của lock acquisition graph** nếu advice lấy lock. Thay đổi version/cấu hình của weaving hoặc proxy chain cần chạy lại các bài test lock-order và integration.

## 11. Self-invocation, recursion và advice tự gọi lại

Một proxy chỉ quan sát lời gọi đi qua wrapper; method `this.otherMethod()` bên trong target có thể bypass proxy ngoài trong nhiều mô hình. Trong khi đó, code weaving ở execution join point có thể chạy cả khi self-invocation nếu class đã instrument đúng.

Điều này ảnh hưởng locks:

- Một lần vào advice thực tế có thể lấy lock một lần.
- Recursion hoặc execution weaving có thể gọi lại **chính advice** ở mức sâu hơn.
- Với reentrant lock, cùng thread lấy lại được, nhưng hold count tăng; phải unlock tương ứng.
- Với một non-reentrant mutex tùy thư viện, self-acquisition có thể treo ngay cả trên một thread.
- Nếu advice tự gọi một method cũng match pointcut mà không có điều kiện loại trừ, recursion có thể lặp vô hạn.

**Không sửa vấn đề bằng một cờ `boolean inAdvice` toàn cục** nếu nhiều threads cần can thiệp độc lập. Nếu dùng guard, phải xác định scope (thread, invocation, control flow), restore trong `finally` và xét async propagation.

## 12. Lock và các công việc bất đồng bộ

Một lỗi thiết kế nguy hiểm:

~~~text
Thread A:
  acquire LOCK
  submit asynchronous task
  wait Future.get()

Worker thread B:
  run task
  attempt acquire LOCK
  blocked

Thread A vẫn chờ Future -> vòng chờ qua khóa + Future
~~~

Ngay cả khi không có hai khóa A/B cổ điển, **wait graph** vẫn có chu trình qua executor, callback, latch hoặc Future. Một thread có thể giữ lock và đợi callback, còn callback cần chính lock đó.

Một advice gọi `proceed()` rồi `join()` một Future trong lúc giữ lock có nguy cơ tạo vòng chờ tương tự. Vì vậy:

- Không giữ mutex qua `Future.get()`/`join()` trừ khi đã chứng minh dependency graph an toàn.
- Không gọi callback do người dùng đăng ký trong critical section một cách tùy tiện.
- Nếu trả `CompletableFuture`, “method return” chưa phải task completion; quản lý trạng thái riêng cho completion nếu advice cần.
- Không `unlock()` `ReentrantLock` từ thread khác: lock có **thread ownership** và cách đó không hợp lệ.
- `ThreadLocal` context không tự lan sang mọi executor; nếu cần propagation phải có cơ chế chuyên biệt.
- Nếu cần bounded concurrency, semaphore, queue hoặc executor limits có thể phù hợp hơn mutex giữ xuyên một workflow bất đồng bộ.

### 12.1. Cẩn thận với `synchronized` và asynchronous callbacks

Mặc dù Java monitors là reentrant trên cùng thread, callback chạy ở một thread khác **không được hưởng reentrancy** của holder. Thực tế bug có thể chỉ xuất hiện khi callback đổi từ synchronous sang asynchronous.

## 13. Ngoại lệ, timeout, interrupt và bảo toàn hợp đồng

### 13.1. Mỗi acquire thành công phải có release tương ứng

Mẫu cơ bản với `ReentrantLock`:

~~~java
lock.lock();
try {
    runProtectedOperation();
} finally {
    lock.unlock();
}
~~~

Đây là pseudocode chưa độc lập. Nếu `runProtectedOperation()` return, throw hoặc bị ngắt bởi exception thông thường, `unlock()` vẫn chạy khi Java unwinds scope.

**Không** dùng:

~~~java
lock.lock();
runProtectedOperation();
lock.unlock();
~~~

Nếu operation throw, lock bị giữ lại và có thể làm requests sau chờ mãi.

### 13.2. Không unlock khi chưa lấy được lock

Với `tryLock()`:

~~~java
boolean acquired = lock.tryLock();
if (!acquired) {
    return failedToAcquireResult();
}
try {
    return runProtectedOperation();
} finally {
    lock.unlock();
}
~~~

Đây là pseudocode. Nếu `tryLock` trả false mà vẫn gọi `unlock()`, có thể ném `IllegalMonitorStateException` hoặc làm lỗi luồng xử lý. Nhớ rõ nhánh acquired.

### 13.3. Xử lý interrupt đúng ngữ nghĩa

Các API blocking như `lockInterruptibly()` và `tryLock(timeout, unit)` có thể ném `InterruptedException`. Nếu advice bắt và xử lý mà không ném lại, cần khôi phục interrupt flag khi phù hợp bằng `Thread.currentThread().interrupt()`, để tầng ngoài nhận biết cancellation.

Không catch rồi bỏ qua interrupt, tiếp tục chờ vô hạn; có thể làm shutdown bị treo.

### 13.4. Có timeout không có nghĩa an toàn retry

Một timeout chờ lock không cho biết target đã commit từ một attempt trước hay chưa. Khi retry logic và lock coordination cùng tồn tại, phải phân biệt:

- **Timeout trước khi vào critical section:** target có thể chưa chạy trên lần thử hiện tại.
- **Timeout khi đang chờ kết quả operation khác:** effect có thể đã xảy ra.
- **Timeout sau khi commit nhưng trước ACK:** outcome có thể chưa rõ.

Idempotency/reconciliation cần được thiết kế tại ranh giới nghiệp vụ, không thể giải quyết chỉ bằng `tryLock(100, MILLISECONDS)`.

## 14. Chẩn đoán deadlock và contention trong JVM

Khi một hệ thống chậm, đừng chỉ xem CPU. Một chương trình bị deadlock có thể có **CPU thấp**, nhưng requests không tiến triển.

### 14.1. Thread dump và lock owners

Một thread dump có thể cho biết:

- Thread ở `BLOCKED` khi chờ intrinsic monitor.
- Thread đang `WAITING` hoặc `TIMED_WAITING` trên condition, park, Future hoặc synchronizer.
- Stack traces cho biết advice/target đang nắm hoặc chờ tài nguyên.
- Ownable synchronizers/monitor ownership khi JVM tooling có dữ liệu.
- Một vòng chờ locks nếu diagnostic có hỗ trợ phát hiện.

**Không kết luận mọi `WAITING` là deadlock.** Một worker có thể chờ queue rỗng theo thiết kế, một Future có thể chưa completed hợp lệ. Cần kết hợp owner, stack traces, tiến triển và thời gian.

### 14.2. `ThreadMXBean` và các giới hạn

Java `java.lang.management.ThreadMXBean` có các chức năng để phát hiện một số dạng deadlock giữa monitors và ownable synchronizers, ví dụ `findDeadlockedThreads()` trên JVM hỗ trợ. `findMonitorDeadlockedThreads()` tập trung vào deadlock monitor.

Nhưng một vòng chờ qua HTTP, DB, message queue hoặc callbacks có thể **không được phát hiện như JVM monitor deadlock**. Không dùng `null` từ một detector làm bằng chứng hệ thống không thể deadlock.

### 14.3. Quan sát performance

Một số tín hiệu:

- Thread blocked time và số contention events.
- Lock wait time, hold time và hàng đợi đợi.
- Throughput theo requests/second.
- P50, P95, P99 latency của từng API boundary.
- Số in-flight requests, executor queue, available workers.
- Tỷ lệ timeouts/acquisition failures và số retries.
- Độ trễ của sink metrics/audit trong khi advice giữ lock.
- Contended locks theo target/key và theo pointcut/aspect.

Java Flight Recorder hoặc profiler có thể giúp quan sát một số sự kiện monitor/park theo khả năng cấu hình. Nếu bật tracing lock mức chi tiết cao trong production, cần đánh giá overhead và tránh log payload nhạy cảm.

### 14.4. Ghi nhận ngữ cảnh AOP đúng cách

Nếu nghi lock trong advice, log/trace nên có:

- Tên aspect/advice hoặc interceptor layer.
- Join point signature/kind khi hệ thống cung cấp.
- Định danh invocation không nhạy cảm.
- Lock identity/lock category không chứa thông tin bí mật.
- Thời điểm acquire attempt/acquired/released.
- Đường đi `proceed` hoặc callback đang chờ.
- Trạng thái timeout, interrupt, exception.

Chỉ ghi “method X slow” thường không đủ để biết thời gian ở **lock wait**, **target** hay **sink I/O**.

## 15. Ước lượng vì sao một khóa global làm tăng latency

Giả sử một advice có một khóa dùng chung và **phần giữ khóa trung bình** là `H` giây. Dù target có thể xử lý song song, critical section được phục vụ **tối đa khoảng 1/H lượt mỗi giây** trong mô hình đơn giản lý tưởng, trước khi tính overhead và scheduling.

Ví dụ nếu `H=0,05s` (50 ms), throughput cực đại của **khóa tuần tự** khoảng 20 lượt/s. Nếu một lời gọi giữ lock qua một HTTP request kéo dài 500 ms, các requests đứng sau có thể phải chờ theo đuôi rất dài, dù CPU còn rảnh.

Đây là **ước lượng minh họa**, không phải SLA bảo đảm: contention phụ thuộc arrivals, variability, number of cores, lock implementation và queueing. Tail latency có thể tăng mạnh khi utilization tiến gần capacity; p99 quan trọng hơn chỉ nhìn trung bình.

**Tối ưu đúng:** giảm **thời gian nắm khóa** và giảm **số bên cần cùng khóa**. Chỉ tăng thread pool có thể làm nhiều threads cùng tranh chấp hơn mà throughput vẫn bị lock giới hạn.

### 15.1. Một shared lock tạo hiệu ứng toàn cục

Nếu cùng một metrics aspect bao hàng nghìn methods, một nút chậm có thể làm trễ mọi method không liên quan. Đôi khi người vận hành nhầm đây là DB saturation vì stack traces của nhiều requests nằm trong business methods. Hãy kiểm lock owner và thứ tự advice trước khi tăng connection pool.

### 15.2. Số lock nhiều hơn không phải lúc nào cũng tốt

Sharding locks theo keys có thể tăng parallelism, nhưng cũng phức tạp hóa ownership, eviction và multi-lock operations. Một concurrent data structure tốt hoặc thiết kế không chia sẻ state thường đơn giản và an toàn hơn.

## 16. Lock ordering và transaction/database locks

Một lời advice mở database transaction rồi gọi target trong lúc giữ Java mutex có thể tạo thứ tự tài nguyên:

~~~text
Thread A: Java lock X -> DB row lock Y
Thread B: DB row lock Y -> callback needs Java lock X
~~~

Chương trình có thể deadlock **xuyên qua JVM và database**. `ThreadMXBean` có thể nhìn thấy thread chờ DB client nhưng không tự đọc được DB lock owners để phát hiện chu trình đầy đủ.

Cần:

- Định nghĩa thứ tự lấy locks qua Java, DB và resources.
- Không làm external I/O khi giữ Java mutex nếu có thể.
- Giữ transactions ngắn và sử dụng isolation phù hợp.
- Sử dụng DB deadlock detection/timeout theo database cụ thể.
- Xử lý rollback/retry đúng loại lỗi và idempotency.
- Không retry toàn bộ thao tác khi timeout mà không rõ commit outcome.

**Vị trí của transaction advice** và `proceed` có thể thay đổi thời điểm resource được nắm giữ. Điều đó phải nằm trong kiểm thử integration, không chỉ unit test của từng aspect.

## 17. Test matrix cho khóa trong advice

| Ca thử | Điều cần chứng minh |
| --- | --- |
| Advice đo metrics, target chạy chậm | Thread khác không bị lock global nếu không cần |
| Advice giữ lock xuyên `proceed` | Competitor phải chờ hoặc `tryLock` báo busy, như demo |
| Target throw | Lock release trong `finally`; exception gốc được bảo toàn |
| Advice before throw | Có cleanup cho resource đã acquire trước lúc before |
| Advice after throw | Lock vẫn release; caller outcome theo contract |
| Đường A→B và B→A | Có policy ngăn lock inversion |
| Hai threads lấy locks theo cùng order | Hoàn tất, không circular wait trong test |
| Timeout khi lấy lock | Nhánh failure không `unlock` lock chưa sở hữu |
| Thread bị interrupt | Exit/cancellation theo contract; không giữ lock |
| Recursion cùng thread | Hold count/reentrancy và state không hỏng |
| Callback chạy trên thread khác | Không có vòng lock↔Future/condition |
| Many concurrent requests | P95/p99, throughput và wait time đáp ứng mục tiêu |
| One slow external sink | Không chặn hàng loạt nghiệp vụ không liên quan |
| Cache/short-circuit | Không giữ khóa ngoài ý định; target không chạy khi bị chặn |
| Retry nhiều attempts | Lock hold time không phình theo tất cả attempts nếu không chủ đích |
| Proxy bypass | Test đúng đường caller, không giả định advice luôn chạy |
| Class đã woven | Kiểm scope pointcut, advice precedence và join points thật |
| Shutdown in-flight | Không release resource sai thread hoặc làm treo shutdown |

### 17.1. Phải kiểm concurrency thật

Unit test advice trên một thread có thể chứng minh logic `finally`, nhưng **không chứng minh** không có deadlock khi hai threads lấy khóa theo thứ tự ngược. Dùng latches, barriers hoặc controlled scheduler để ép interleavings cần khảo sát.

Không dùng `Thread.sleep(10)` như bằng chứng chắc chắn tạo được tình huống đối đầu. Nếu test tạo real deadlock để kiểm detector, nên cách ly trong process có watchdog/timeout và chẩn đoán rõ, tránh làm treo cả CI suite.

### 17.2. Assert outcome, không chỉ logs

Một test khóa tốt cần xác minh:

- Caller result/exception vẫn đúng.
- Target thực thi đúng số lần; retry không làm duplicate side effect.
- Lock được release khi success và exceptional exit.
- No progress stall sau timeout hoặc cancellation.
- Những callers không liên quan không bị serialized ngoài ý định.
- Shared state giữ invariant.
- Không có long-lived registry/ThreadLocal rò references sau request.

## 18. Quy trình review một aspect có khóa

1. **Tìm tất cả đường acquire:** `synchronized`, `ReentrantLock.lock`, `tryLock`, condition wait, semaphore hoặc locks ẩn trong client.
2. **Xác định lock identity:** global, per-classloader, per-target, per-key hay per-invocation?
3. **Vẽ critical section:** từ acquire tới release; đánh dấu `proceed()`, external calls, callbacks, `join/get`, retry.
4. **Liệt kê state/invariant được bảo vệ:** nếu chỉ một counter, cân nhắc atomic/concurrent primitive.
5. **Lập đồ thị thứ tự khóa:** locks trong advice, target, DB, event bus và callback.
6. **Kiểm reentrancy:** method được pointcut chọn có thể gọi lại advice không?
7. **Kiểm exception path:** mọi acquire thành công có release trong `finally` không?
8. **Kiểm interrupt/timeout:** nhánh không lấy được lock làm gì? Có làm đổi policy bảo mật/nhất quán không?
9. **Kiểm async:** có thread khác cần khóa khi caller đang chờ Future không?
10. **Kiểm scope AOP thật:** pointcut match đúng, proxy/weaver không bypass, precedence phù hợp.
11. **Đo dưới tải:** contention, tail latency, throughput và wait/hold time.
12. **Giữ regression tests:** đổi thứ tự aspect hoặc cập nhật agent/interceptor phải chạy lại kịch bản lock inversion.
13. **Kiểm shutdown:** không dùng unlock sai thread, không block vô hạn khi drain in-flight calls.
14. **Tài liệu hóa hợp đồng:** lock chỉ bảo vệ tài nguyên nào, chính sách khi busy, số attempts và failure semantics.

## 19. Những sai lầm phổ biến

1. **“Có `finally` thì advice giữ lock qua target an toàn hoàn toàn.”** Sai: vẫn có contention và deadlock do code bên trong.
2. **“Khóa global chỉ chậm concern metrics.”** Sai: nếu khóa bao `proceed`, mọi target được chọn có thể bị serialized.
3. **“`ReentrantLock` không thể deadlock.”** Sai: reentrancy chỉ xử lý self-acquisition cùng thread; lock inversion vẫn nguy hiểm.
4. **“`synchronized` xấu còn `ReentrantLock` luôn nhanh.”** Không có kết luận chung.
5. **“`tryLock()` thất bại thì cứ coi request success.”** Sai nếu invariant nghiệp vụ chưa được đảm bảo.
6. **“Timeout bảo đảm operation chưa commit.”** Sai nếu đang chờ outcome từ tài nguyên khác.
7. **“Thay `lock()` bằng `tryLock()` tự giải quyết mọi vấn đề.”** Không: nhánh busy và retry cần thiết kế.
8. **“`unlock()` từ callback thread khác được.”** `ReentrantLock` có ownership theo thread; không unlock tùy tiện.
9. **“Hai aspect khác nhau không thể deadlock với nhau.”** Sai nếu chúng giữ khóa trong nested call graph.
10. **“Order pointcut không ảnh hưởng khóa.”** Sai: precedence có thể đảo thứ tự A→B thành B→A.
11. **“Thread WAITING chắc là deadlock.”** Không; có thể là chờ công việc hợp lệ.
12. **“Detector không thấy deadlock nghĩa là hệ thống an toàn.”** Không nếu vòng chờ qua DB/network/Future.
13. **“Nhiều threads hơn luôn tăng throughput.”** Không khi một khóa global giới hạn critical section.
14. **“Lock per-key không thể leak.”** Registry có thể tích lũy hoặc xóa key sai thời điểm.
15. **“Java lock bảo vệ mọi process.”** Không bảo vệ các JVM khác.
16. **“Dùng ThreadLocal để lưu lock holder sẽ tự theo async task.”** Không có bảo đảm chung.
17. **“Một metrics aspect cần field `startedAt` shared.”** Dùng local per invocation thường đúng hơn.
18. **“Giữ lock qua I/O cho chắc thứ tự event.”** Có thể làm latency rất lớn; cần cơ chế order/delivery phù hợp.
19. **“Lock timeout và retry không ảnh hưởng business side effects.”** Có thể tạo repeated executions hoặc unknown outcome.
20. **“Recursion chỉ xảy ra trong target.”** Advice có thể tự gọi method cũng match pointcut, tạo reentrancy.
21. **“Không bao giờ cần đo lock hold time.”** Chỉ đo target duration có thể bỏ sót delay trong advice.
22. **“Khóa công bằng luôn tốt hơn.”** Fairness có tradeoff với throughput/scheduling.
23. **“Mọi AOP engine hỗ trợ cùng loại join point.”** Phụ thuộc proxy/weaver và phạm vi instrumentation.
24. **“Unit test advice đơn luồng chứng minh deadlock-free.”** Cần concurrency integration tests.
25. **“Unlock trong finally tạo atomicity cho thao tác.”** Release mutex không phải rollback transaction.
26. **“Mọi advice chỉ chạy một lần khi có một logical request.”** Retry/recursion/nested join points có thể tạo nhiều entries.
27. **“Mọi lock contention có thể giải quyết bằng timeouts ngắn.”** Có thể gây lỗi hàng loạt và retry storm.
28. **“Ghi lỗi lock nên log mọi payload.”** Có nguy cơ lộ dữ liệu nhạy cảm và tăng I/O đúng lúc hệ thống đang nghẽn.

## 20. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `globalLock.lock(); try { proceed(); } finally { unlock(); }` có thể làm chậm toàn ứng dụng?  
**Đáp án:** Vì lock bị giữ xuyên suốt target và các advice bên trong, cả khi có I/O chậm hoặc chờ lock khác.

**Câu 2.** `finally` giải quyết vấn đề gì và không giải quyết vấn đề gì?  
**Đáp án:** Giúp release lock khi unwinding bình thường, nhưng không rút ngắn critical section hay tự ngăn circular wait.

**Câu 3.** T1 giữ A chờ B, T2 giữ B chờ A. Đây là loại lỗi gì?  
**Đáp án:** Lock-order inversion tạo circular wait và nguy cơ deadlock.

**Câu 4.** Vì sao reentrant lock không đảm bảo deadlock-free?  
**Đáp án:** Tái nhập chỉ cho cùng thread lấy lại lock nó sở hữu; không ngăn nhiều threads chờ chéo các locks khác nhau.

**Câu 5.** Trong ví dụ Java, vì sao `INVERSION tryLockFailures=2` không khiến ứng dụng treo?  
**Đáp án:** Cả hai thread dùng nonblocking `tryLock()` cho lock thứ hai, nhận false rồi release; latches giữ trạng thái ổn định khi thử.

**Câu 6.** Vì sao `ORDERED completed=2`?  
**Đáp án:** Hai workers lấy các locks theo cùng thứ tự left→right, hoàn tất cả hai calls mà không có inversion trong test.

**Câu 7.** Một shared timer aspect có field `start`. Có cần khóa toàn target để đo đúng không?  
**Đáp án:** Thường không; dùng local start time theo invocation tránh race mà không serialize nghiệp vụ.

**Câu 8.** Có nên lấy `ReentrantLock` rồi chờ `CompletableFuture.join()` khi callback cần cùng khóa?  
**Đáp án:** Không; có thể tạo chu trình chờ lock ↔ Future qua các threads.

**Câu 9.** `tryLock` trả false. Có được gọi `unlock` không?  
**Đáp án:** Không, trừ khi thread đang sở hữu lock từ một acquisition khác có hợp đồng rõ. Thông thường chỉ unlock nếu lần lấy này thành công.

**Câu 10.** `ThreadMXBean.findDeadlockedThreads()` trả null có chứng minh không có deadlock qua DB lock không?  
**Đáp án:** Không. Nó không thấy đầy đủ mọi tài nguyên ngoài JVM.

**Câu 11.** Khi hai pointcuts có thứ tự precedence khác nhau, cần kiểm tra gì thêm ngoài logs?  
**Đáp án:** Đồ thị lock acquisition, critical section, đường retry/short-circuit, contention và tác dụng phụ nghiệp vụ.

**Câu 12.** Lock per-key có hai rủi ro đặc trưng nào?  
**Đáp án:** Registry leak hoặc eviction sai làm hai locks riêng xuất hiện cho cùng key; multi-key operations cũng có thể deadlock khi order không nhất quán.

**Câu 13.** Tại sao throughput không nhất thiết tăng khi mở rộng thread pool?  
**Đáp án:** Nếu một lock global giới hạn số critical sections hoàn tất mỗi giây, thêm threads chủ yếu tăng số bên xếp hàng.

**Câu 14.** Kiểm thử nào phù hợp để phát hiện lock inversion mà không làm treo CI?  
**Đáp án:** Dùng latches/barriers tạo hai locks được giữ đồng thời, thử lock thứ hai bằng nonblocking `tryLock` rồi assert cả hai thất bại và dọn dẹp; bổ sung monitoring và integration tests cho chain thật.

## 21. Tổng kết

**Một khóa đặt trong advice có phạm vi ảnh hưởng rộng hơn vẻ ngoài của nó**, vì aspect có thể áp lên nhiều methods/targets và `proceed()` có thể chạy toàn bộ nghiệp vụ cùng những concerns khác. Giữ khóa quá rộng làm tăng contention, giảm throughput, tăng tail latency và mở đường cho deadlock qua lock-order inversion, callbacks, Future hoặc tài nguyên bên ngoài JVM.

Hướng tiếp cận an toàn là **định nghĩa state/invariant thực sự cần bảo vệ**, dùng **scope khóa ngắn nhất đúng hợp đồng**, tránh giữ lock qua I/O hay gọi code không kiểm soát, thống nhất thứ tự lấy nhiều locks, release trong `finally`, và xử lý timeout/interrupt một cách có chủ đích. Ưu tiên local state per invocation, concurrent counters hoặc thiết kế ownership phù hợp thay vì dùng mutex toàn cục để che race của một field shared.

Sau cùng, phải **kiểm thử trên đường AOP thực tế**: đúng proxy/weaving coverage, đúng precedence, concurrency interleavings và failure paths. Một test chạy đơn luồng có thể chứng minh logic advice nhưng không chứng minh deadlock-free hoặc throughput đủ tốt. Kết hợp kiểm thử hữu hạn có điều khiển với thread dumps, lock wait/hold metrics và benchmarks dưới tải đại diện để tránh biến một concern bổ sung thành nút thắt cổ chai của hệ thống.