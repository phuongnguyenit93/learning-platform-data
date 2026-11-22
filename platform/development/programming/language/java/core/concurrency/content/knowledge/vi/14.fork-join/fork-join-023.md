# ManagedBlocker.isReleasable(), block() và giới hạn bù luồng khi chặn trong Java Fork/Join

## 1. Vì sao cần ManagedBlocker?

`ForkJoinPool` được tối ưu cho công việc có thể chia nhỏ rồi kết hợp kết quả. Các worker lấy task trong hàng đợi và có thể **work-steal** khi rảnh. Khi một task đang chạy CPU, worker đóng góp tiến độ; khi task đang chờ `BlockingQueue.take()`, `ReentrantLock.lock()`, một tín hiệu từ thread khác hoặc I/O, worker có thể không làm việc hữu ích trong thời gian đó.

Nếu nhiều worker cùng bị chặn, lượng worker **còn chạy được** có thể ít hơn parallelism mục tiêu. Một số kiểu chờ nội bộ của Fork/Join đã có cơ chế hỗ trợ; nhưng **blocking tùy ý trong user code không được pool tự động nhận biết và bù đúng mọi trường hợp**.

`ForkJoinPool.ManagedBlocker` là interface cho phép task **khai báo một đoạn có thể chặn** để `ForkJoinPool.managedBlock(blocker)` có thông tin cân nhắc kích hoạt hoặc tạo worker thay thế nếu cần duy trì tiến độ. Hai phương thức của interface:

- `boolean isReleasable()` — cho biết **có thể tiếp tục mà không cần chặn nữa** hay chưa.
- `boolean block() throws InterruptedException` — thực hiện thao tác có thể chặn, rồi trả **true khi không cần chặn thêm nữa**.

**Thông điệp cốt lõi:** `managedBlock` **có thể** hỗ trợ bù parallelism, nhưng **không bảo đảm mỗi lần chặn tạo thêm một thread, không bảo đảm đủ thread thay thế và không biến I/O thành non-blocking**.

Bài học thuộc **Fork/Join** trong **Java Advance - concurrency**. Phạm vi là concurrency của **Java SE 17+ nói chung**, không sử dụng API hay cấu hình Spring vì phần liên quan Spring có chương riêng.

### Kết quả học tập

Sau bài, bạn sẽ:
1. Hiểu tại sao pool CPU-bound có thể giảm throughput/liveness nếu task chờ bên ngoài mà không thông báo.
2. Phân biệt `parallelism`, `pool size`, `running/active workers`, `managed blocking` và **compensation**.
3. Hiểu chính xác hợp đồng, vòng gọi lặp và thứ tự `isReleasable()` → `block()`.
4. Cài đặt blocker cho `BlockingQueue.take()` và `ReentrantLock`, xử lý đường fast-path/slow-path và quyền sở hữu resource.
5. Tránh gọi `isReleasable()` như một hàm có side effect lặp lại không kiểm soát.
6. Giải thích vì sao `block() == true` **không** có nghĩa nghiệp vụ đã thành công: timeout hoặc cancellation có thể là trạng thái kết thúc hợp lệ của một lần chờ.
7. Nhận diện giới hạn của việc bù worker: giới hạn pool, saturation, chi phí tạo thread, tài nguyên, deadlock, I/O và các ràng buộc do môi trường.
8. Kiểm thử và đo hiệu năng đúng cách mà không gán chắc một số lượng spare threads cho mọi JVM.
9. Chạy **năm chương trình Java 17+ độc lập** có stdout rõ ràng, không phụ thuộc thứ tự scheduler.

## 2. Blocking và giới hạn compensation

Worker trong `ForkJoinPool` được thiết kế để tiếp tục xử lý task còn sẵn sàng. Blocking bên ngoài fork/join làm giảm lượng worker có thể tiến triển. `ForkJoinPool.managedBlock(blocker)` cho pool cơ hội **cân nhắc bù worker**, không bảo đảm tạo đủ thread hoặc chữa deadlock.

Bài tập trung vào **`isReleasable()`, `block()`, điều kiện kết thúc và ownership**; compensation còn tùy giới hạn pool, timeout, interrupt và tài nguyên thực tế.
## 3. Hợp đồng chuẩn của ManagedBlocker

`ManagedBlocker` có hai method:

~~~java
interface ManagedBlocker {
    boolean isReleasable();
    boolean block() throws InterruptedException;
}
~~~

Đây là khai báo tối giản để học hợp đồng; interface thật nằm tại `ForkJoinPool.ManagedBlocker`.

### 3.1. isReleasable(): có thể đi tiếp mà không cần block không?

`isReleasable() == true` nghĩa là **lần chờ đã đạt điều kiện kết thúc**, hoặc **không cần chặn thêm**. Chẳng hạn:
- Queue đã cung cấp một phần tử.
- Lock đã lấy được.
- Event đã xảy ra.
- Một tác vụ đợi có deadline đã hết và sẽ trả trạng thái timeout.

`isReleasable() == false` có nghĩa là tại thời điểm kiểm tra, blocker còn cần thao tác chặn. Pool có thể gọi `isReleasable()` **nhiều lần** để theo dõi trạng thái và hạn chế tạo worker bù không cần thiết.

**Quy tắc:** Cài đặt phải chịu được việc gọi lặp lại, không giả định “isReleasable luôn được gọi đúng một lần”. Nếu nó thực hiện một thao tác như `queue.poll()`, phải **lưu kết quả** để không lấy mất nhiều item khi được gọi lại.

### 3.2. block(): thực hiện đoạn có khả năng chặn

`block()` có thể đợi khóa, lấy phần tử từ blocking queue, chờ condition... Kết quả:
- `true`: **không cần block thêm** đối với instance ManagedBlocker này.
- `false`: lần gọi chưa đạt trạng thái kết thúc, `managedBlock` có thể lặp và thử tiếp.

`block()` được phép ném `InterruptedException` nếu thao tác chờ tương ứng có contract interruptible; nó **không bắt buộc** mọi implementation đều ném khi bị interrupt.

**`true` không phải boolean “business operation succeeded”**. Ví dụ một timed poll đã hết hạn nhưng không lấy được item: blocker có thể đánh dấu `finished=true` và trả `true` vì không cần chờ nữa; caller sau đó đọc `timedOut` để phân biệt kết quả.

### 3.3. Vòng lặp do managedBlock điều phối

Về semantics, nếu không chạy trong `ForkJoinPool`, JavaDoc mô tả hành vi tương đương:

~~~java
while (!blocker.isReleasable()) {
    if (blocker.block()) {
        break;
    }
}
~~~

Đây là pseudocode mô tả hành vi, `blocker` do caller cung cấp. Khi chạy trong pool, thư viện có thể bổ sung logic cân nhắc compensation trước khi gọi `block()`, nhưng thứ tự hợp đồng vẫn là: **mỗi lần gọi block() đều có một lần isReleasable() trả false ngay trước đó**, và **sau khi một trong hai method trả true, không gọi thêm cả hai cho lần managedBlock ấy**.

Không giả định một số lần gọi cụ thể cho `isReleasable` khi có contention. Nó có thể được thử lại để tránh block khi trạng thái vừa chuyển sang ready.

### 3.4. Trạng thái một blocker phải thuộc về ai?

Một blocker thường gắn với **một lần chờ** và giữ trạng thái như:
- `item` đã lấy được từ queue.
- `acquired` khi đã nắm một ReentrantLock.
- `finished/timedOut` nếu đã chờ xong dù không có item.
- Deadline hoặc cờ hủy trong một giao thức đã xác định.

Không tái sử dụng cùng một blocker để xử lý nhiều request cùng lúc khi nó có state mutable như vậy, trừ khi thiết kế rõ thread safety. Một instance thường được tạo tại nơi cần chờ, dùng bởi **một caller**, sau đó caller đọc kết quả.

## 4. Ví dụ 1 — ManagedBlocker cho BlockingQueue

Ta triển khai mẫu tương tự JavaDoc Oracle: thử lấy item **không chặn** bằng `poll()` ở `isReleasable()`; nếu chưa có, `block()` thực hiện `take()` có thể chặn. Quan trọng: nếu đã lấy được item thì lưu nó để lần kiểm tra tiếp theo không ăn mất item thứ hai.

Tạo file **`ManagedQueueDemo.java`**:

~~~java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.Future;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.TimeUnit;

public class ManagedQueueDemo {
    static final class QueueTaker
            implements ForkJoinPool.ManagedBlocker {

        private final BlockingQueue<Integer> queue;
        private Integer item;

        QueueTaker(BlockingQueue<Integer> queue) {
            this.queue = queue;
        }

        @Override
        public boolean isReleasable() {
            return item != null || (item = queue.poll()) != null;
        }

        @Override
        public boolean block() throws InterruptedException {
            if (item == null) {
                item = queue.take();
            }
            return true;
        }

        Integer item() {
            return item;
        }
    }

    static final class TakeTask extends RecursiveTask<Integer> {
        private final BlockingQueue<Integer> queue;
        private final CountDownLatch entered;

        TakeTask(BlockingQueue<Integer> queue,
                 CountDownLatch entered) {
            this.queue = queue;
            this.entered = entered;
        }

        @Override
        protected Integer compute() {
            QueueTaker taker = new QueueTaker(queue);
            if (entered != null) {
                entered.countDown();
            }
            try {
                ForkJoinPool.managedBlock(taker);
                return taker.item();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("interrupted", e);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            BlockingQueue<Integer> ready =
                    new LinkedBlockingQueue<>();
            ready.add(5);

            int fast = pool.invoke(new TakeTask(ready, null));

            BlockingQueue<Integer> later =
                    new LinkedBlockingQueue<>();
            CountDownLatch entered = new CountDownLatch(1);

            Future<Integer> slow =
                    pool.submit(new TakeTask(later, entered));

            entered.await();
            later.put(7);

            System.out.println("fast=" + fast);
            System.out.println("slow=" + slow.get());
        } finally {
            pool.shutdown();
            pool.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Biên dịch/chạy trên JDK 17+:

~~~bash
javac ManagedQueueDemo.java
java ManagedQueueDemo
~~~

Stdout khi không có interruption bên ngoài:

~~~text
fast=5
slow=7
~~~

**Giải thích:**
1. `ready` đã có số 5; ở lần managedBlock đầu, `isReleasable()` có thể lấy được item bằng `poll()`. Không cần `take()`.
2. Với queue `later` ban đầu rỗng, `isReleasable()` có thể trả false và `block()` sử dụng `take()`. Main đợi latch `entered` rồi đưa số 7 vào queue.
3. Nếu main đã `put(7)` trước khi worker thực sự gọi `take()`, fast-path có thể lấy ngay 7. Dù lịch scheduler ra sao, kết quả **vẫn là 7**, không có lost notification.
4. `ForkJoinPool.managedBlock` xử lý giao thức isReleasable/block; caller đọc item từ chính instance sau khi chờ xong.
5. `Future.get()` chờ tác vụ trả kết quả. Chương trình không quan sát một con số threads-bù cố định, vì **compensation là hành vi động và không được bảo đảm**.

**Vì sao không viết `return queue.poll() != null` rồi quên lưu item?** `poll` lấy phần tử ra khỏi queue. Nếu `isReleasable` rút item nhưng không giữ reference, item đã bị tiêu thụ và chương trình có thể tiếp tục chờ hoặc mất dữ liệu. `QueueTaker` lưu item đúng một lần.

### Giới hạn

`LinkedBlockingQueue` tự có cơ chế đồng bộ và backpressure. Nếu chương trình bình thường có một producer/consumer thread rõ ràng, việc dùng `BlockingQueue.take()` trong **executor chuyên I/O** có thể đủ và đơn giản hơn. `ManagedBlocker` đặc biệt hữu ích khi bạn **bắt buộc** phải chờ từ một ForkJoin worker mà muốn pool có cơ hội nhận biết đoạn chặn.

## 5. Ví dụ 2 — isReleasable có thể bỏ qua hoàn toàn block

Nếu điều kiện đã đạt từ trước, `managedBlock` không cần gọi `block()`. Một blocker trả ready thật ngay ở `isReleasable` cho thấy fast-path này.

Tạo file **`AlreadyReadyDemo.java`**:

~~~java
import java.util.concurrent.ForkJoinPool;

public class AlreadyReadyDemo {
    static final class ReadyBlocker
            implements ForkJoinPool.ManagedBlocker {

        private int blockCalls;

        @Override
        public boolean isReleasable() {
            return true;
        }

        @Override
        public boolean block() {
            blockCalls++;
            return true;
        }

        int blockCalls() {
            return blockCalls;
        }
    }

    public static void main(String[] args) throws Exception {
        ReadyBlocker blocker = new ReadyBlocker();

        // Gọi từ main: không cần đang ở ForkJoin worker.
        ForkJoinPool.managedBlock(blocker);

        System.out.println("completed=true");
        System.out.println("blockCalls=" + blocker.blockCalls());
    }
}
~~~

Chạy:

~~~bash
javac AlreadyReadyDemo.java
java AlreadyReadyDemo
~~~

Stdout:

~~~text
completed=true
blockCalls=0
~~~

Một lần `isReleasable() == true` đã đủ để method kết thúc. **Không có block**, không có nghĩa đã tạo một worker bù hay đã chạy bất đồng bộ. Mẫu cũng chứng minh `managedBlock` có thể gọi từ thread không thuộc ForkJoinPool; khi đó nó vận hành theo giao thức chờ/lặp mà không sử dụng compensation của pool.

**Không dùng `isReleasable()` trả true một cách giả tạo chỉ để “né block”** nếu trạng thái thật chưa sẵn sàng; caller sẽ tiếp tục xử lý khi chưa đạt predicate, làm sai correctness.

## 6. Ví dụ 3 — ReentrantLock ManagedBlocker

JavaDoc cũng minh họa một blocker thử `ReentrantLock.tryLock()` trước; nếu chưa lấy được, `block()` mới chờ lock. Khi đã lấy được, caller cần **unlock trên đúng thread đang sở hữu lock**.

Tạo file **`ManagedLockDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public class ManagedLockDemo {
    static final class LockBlocker
            implements ForkJoinPool.ManagedBlocker {

        private final ReentrantLock lock;
        private boolean acquired;

        LockBlocker(ReentrantLock lock) {
            this.lock = lock;
        }

        @Override
        public boolean isReleasable() {
            return acquired || (acquired = lock.tryLock());
        }

        @Override
        public boolean block() throws InterruptedException {
            if (!acquired) {
                lock.lockInterruptibly();
                acquired = true;
            }
            return true;
        }

        boolean isAcquired() {
            return acquired;
        }

        void release() {
            if (acquired) {
                acquired = false;
                lock.unlock();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        ReentrantLock lock = new ReentrantLock();
        ForkJoinPool pool = new ForkJoinPool(1);
        CountDownLatch entered = new CountDownLatch(1);

        lock.lock(); // Main giữ khóa để task có thể phải chờ.
        Future<Boolean> future;
        try {
            future = pool.submit(() -> {
                LockBlocker blocker = new LockBlocker(lock);
                entered.countDown();
                try {
                    ForkJoinPool.managedBlock(blocker);
                    return blocker.isAcquired();
                } finally {
                    blocker.release();
                }
            });

            entered.await();
        } finally {
            lock.unlock(); // Nhả khóa do main sở hữu.
        }

        try {
            System.out.println("acquired=" + future.get());
            System.out.println("unlocked=" + !lock.isLocked());
        } finally {
            pool.shutdown();
            pool.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Chạy:

~~~bash
javac ManagedLockDemo.java
java ManagedLockDemo
~~~

Stdout trên đường thực thi bình thường:

~~~text
acquired=true
unlocked=true
~~~

**Điều cần thấy:**
- Main giữ lock trước khi submit task; worker nhận tín hiệu `entered` rồi thử `tryLock`.
- `tryLock` có thể thất bại khi main chưa unlock, hoặc thành công nếu main đã unlock trước khi worker kiểm tra; cả hai đường đều đúng.
- Khi cần chờ, `lockInterruptibly` cho phép phản hồi `InterruptedException`. Sau thành công, blocker ghi nhận `acquired=true` và trở về.
- `release()` chạy trong `finally` **trên worker sở hữu lock**, không phải main; main chỉ unlock lần giữ khóa của chính mình.
- Chờ managed không có nghĩa ReentrantLock tự được unlock khi task bị cancel. Logic vẫn phải trả tài nguyên đúng một lần, kể cả exception.

### Tại sao không dùng synchronized monitor thay thế?

`Object.wait()`, `synchronized` và `ReentrantLock` có ownership/interrupt semantics khác nhau. Một thread đang đợi **vào synchronized monitor** không thể tự bỏ cuộc chỉ nhờ `Thread.interrupt()`; với `ReentrantLock.lockInterruptibly()`, caller có đường phản hồi interrupt rõ ràng. Nếu đã chọn `ReentrantLock` để tích hợp `ManagedBlocker`, phải dùng `tryLock/lockInterruptibly` đúng và xử lý unlock trong finally.

Không nên gọi `ManagedBlocker.block()` từ một thread rồi dùng thread khác unlock `ReentrantLock`. Lock thuộc thread thực sự acquire; unlock sai thread có thể ném `IllegalMonitorStateException`.

## 7. Giới hạn compensation: pool không có năng lực vô hạn

Một thuật ngữ dễ gây hiểu nhầm là **“bù luồng”**. Bù worker không tương đương cứ có một blocked worker thì JVM tạo thêm một worker. Các ràng buộc cụ thể có thể bao gồm:

1. **Target parallelism:** `new ForkJoinPool(P)` thiết lập mức song song mục tiêu, không phải lời hứa “P worker luôn chạy task hữu ích”.
2. **Pool configuration:** giới hạn worker bổ sung và giới hạn tổng số worker có thể được cấu hình; common pool có cơ chế và system property riêng.
3. **Giới hạn tài nguyên hệ thống:** memory cho stack, native threads, CPU quota, container/process limits và khả năng tạo thread thật.
4. **Mức cần thiết theo quan sát của pool:** pool có thể không tạo worker bù khi nhận thấy còn worker khác đủ để tiến triển.
5. **Các task khác cũng bị chặn:** compensation không đảm bảo task được tạo thêm sẽ tìm thấy công việc có thể tiến triển.
6. **Saturation:** khi không thể cung cấp đủ worker theo chính sách đã đặt, `managedBlock` có thể thất bại theo contract/implementation, thay vì tạo vô hạn worker.
7. **Tài nguyên bị khóa bởi một task khác:** worker bù không thể tự mở khóa một monitor nếu chủ sở hữu lock không có đường chạy tiến triển.
8. **I/O thực sự chậm hoặc không interruptible:** thêm worker không làm dịch vụ đích phản hồi nhanh hơn và có thể làm tăng áp lực tải.
9. **Tăng số thread không tăng số lõi CPU:** nhiều worker thay phiên chạy nhưng không làm tổng CPU capacity của máy tăng.
10. **Trường hợp chờ tuần hoàn (deadlock):** thêm thread không sửa được quan hệ sở hữu tài nguyên sai.

### Common pool và custom pool

`ForkJoinPool.commonPool()` dùng chung trong một JVM và có system property `java.util.concurrent.ForkJoinPool.common.maximumSpares` để giới hạn spare threads theo triển khai Java 17; giá trị có thể khác theo cấu hình và môi trường. Không phải mọi ứng dụng đều được phép thay đổi property này và không nên nâng giới hạn vô hạn để che lỗi blocking.

Custom pool trên Java 17 có constructor nâng cao chứa các tham số như `corePoolSize`, `maximumPoolSize`, `minimumRunnable`, `saturate`, `keepAliveTime` và `TimeUnit`. Những tham số đó ảnh hưởng tới khả năng bù worker và hành vi khi saturation. Đây là công cụ nâng cao; thay đổi chúng mà không hiểu lifecycle và workload có thể gây chi phí/mất ổn định lớn hơn.

**Không hard-code trong logic nghiệp vụ rằng một lần `managedBlock` sẽ tạo “một thread thứ ba” hay số worker tăng đúng một.** Số worker phụ thuộc tình trạng pool, JDK và cấu hình.

### RejectedExecutionException khi không thể bù?

Các chính sách và giới hạn của ForkJoinPool có thể làm một yêu cầu compensation không đạt, và ở cấu hình cụ thể có thể xuất hiện `RejectedExecutionException` nếu không thể thay thế worker bị chặn theo hợp đồng của pool. Điều này **không xảy ra bắt buộc trong mọi lời gọi managedBlock**. Code production cần xác định cách xử lý khi resource/pool bị saturation: báo lỗi, timeout, fallback hoặc thiết kế lại để chặn ngoài CPU pool.

### Liveness khác throughput

Compensation không phải chỉ có mục tiêu tăng throughput. Đôi lúc nó giúp ngăn thiếu tiến triển khi tất cả worker đang chờ nhưng có task độc lập trong queue. Dù vậy, không được dùng nó như **bảo đảm tránh deadlock** khi có dependency vòng hoặc sở hữu lock sai.

## 8. Ví dụ 4 — Không phụ thuộc spare worker để bảo đảm kết thúc

Ví dụ tiếp theo có một ForkJoinPool parallelism=1:
- Task A vào managedBlock đợi một `CountDownLatch`.
- Task B là công việc độc lập được submit sau A.
- Main, nằm ngoài pool, chủ động mở latch.
- Dù pool có chọn bù worker hay không, hai task vẫn hoàn thành.

**Chúng ta không in số thread bù**, vì đó là hành vi runtime không cố định. Ví dụ nhằm chứng minh cách tổ chức đúng: **phải có đường giải phóng bên ngoài một pool bị chặn**, không coi compensation là điều kiện tiên quyết để giải deadlock.

Tạo file **`ExternalReleaseDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ExternalReleaseDemo {
    static final class GateBlocker
            implements ForkJoinPool.ManagedBlocker {

        private final CountDownLatch gate;

        GateBlocker(CountDownLatch gate) {
            this.gate = gate;
        }

        @Override
        public boolean isReleasable() {
            return gate.getCount() == 0;
        }

        @Override
        public boolean block() throws InterruptedException {
            gate.await();
            return true;
        }
    }

    public static void main(String[] args) throws Exception {
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch gate = new CountDownLatch(1);
        ForkJoinPool pool = new ForkJoinPool(1);

        try {
            Future<?> first = pool.submit(() -> {
                entered.countDown();
                try {
                    ForkJoinPool.managedBlock(new GateBlocker(gate));
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(e);
                }
            });

            entered.await();
            Future<Integer> second = pool.submit(() -> 2);

            gate.countDown(); // Main ngoài pool mở gate.
            first.get();
            int result = second.get();

            System.out.println("bothCompleted=true");
            System.out.println("secondResult=" + result);
        } finally {
            gate.countDown();
            pool.shutdown();
            pool.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Chạy:

~~~bash
javac ExternalReleaseDemo.java
java ExternalReleaseDemo
~~~

Stdout khi thực thi bình thường:

~~~text
bothCompleted=true
secondResult=2
~~~

**Vì sao code có thể hoàn tất ngay cả khi không có compensation?** Main là một thread ngoài pool và có thể hạ latch bất kể các ForkJoin worker đang làm gì. Task A không bị phụ thuộc vào việc Task B phải chạy trước để mở gate. Sau khi A thoát, worker có thể xử lý B; nếu runtime đã bổ sung worker, B có thể kết thúc sớm hơn. Kết quả logic là một, còn thứ tự/timing không được giả định.

**Anti-pattern:** Nếu thay `gate.countDown()` của main bằng một đoạn code chỉ chạy bên trong Task B, và toàn bộ worker bị chặn chờ Task B, bạn đã tạo dependency vào khả năng bù worker. ManagedBlocker có thể giúp trong một số cấu hình, nhưng không phải **bằng chứng liveness** ở mọi trạng thái saturation. Tốt hơn là thiết kế một event producer độc lập, asynchronous callback hoặc tránh chờ cùng pool khi cần.

## 9. Ví dụ 5 — Timed ManagedBlocker: kết thúc chờ không đồng nghĩa có kết quả

Một `ManagedBlocker` có thể được xây dựng để **hết hạn** thay vì chờ tới khi có item. Đây là chỗ thấy rõ tại sao `block() == true` không có nghĩa “đã lấy dữ liệu thành công”.

Tạo file **`TimedManagedQueueDemo.java`**:

~~~java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.TimeUnit;

public class TimedManagedQueueDemo {
    static final class TimedTaker
            implements ForkJoinPool.ManagedBlocker {

        private final BlockingQueue<String> queue;
        private String item;
        private boolean finished;

        TimedTaker(BlockingQueue<String> queue) {
            this.queue = queue;
        }

        @Override
        public boolean isReleasable() {
            if (finished) {
                return true;
            }

            item = queue.poll();
            if (item != null) {
                finished = true;
                return true;
            }
            return false;
        }

        @Override
        public boolean block() throws InterruptedException {
            if (!finished) {
                item = queue.poll(20, TimeUnit.MILLISECONDS);
                finished = true; // Có item HOẶC hết thời gian.
            }
            return true; // Không cần chờ thêm, kể cả khi item == null.
        }

        String result() {
            return item == null ? "TIMEOUT" : item;
        }
    }

    static final class WaitTask extends RecursiveTask<String> {
        private final BlockingQueue<String> queue;

        WaitTask(BlockingQueue<String> queue) {
            this.queue = queue;
        }

        @Override
        protected String compute() {
            TimedTaker blocker = new TimedTaker(queue);
            try {
                ForkJoinPool.managedBlock(blocker);
                return blocker.result();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return "INTERRUPTED";
            }
        }
    }

    public static void main(String[] args) {
        BlockingQueue<String> queue = new LinkedBlockingQueue<>();
        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            String result = pool.invoke(new WaitTask(queue));
            System.out.println("result=" + result);
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Chạy:

~~~bash
javac TimedManagedQueueDemo.java
java TimedManagedQueueDemo
~~~

Stdout bình thường, khi không có producer hoặc interrupt:

~~~text
result=TIMEOUT
~~~

Queue trống suốt thời gian chạy, vì vậy `queue.poll(20, MILLISECONDS)` trả `null`. Blocker đánh dấu `finished=true` và `block()` trả true: không cần tiếp tục chặn. Caller xem `result()` mới biết chưa có item.

**Đây là timeout cho một lần chờ của `block()`, không phải một deadline tổng tính từ khi request bắt đầu.** Nếu cần deadline end-to-end, hãy dùng `System.nanoTime()`/remaining budget và tính cả thời gian ở queue trước khi task chạy; tránh tái cấp đủ 20 ms ở từng stage.

**Lưu ý về interruption:** `block()` được phép ném `InterruptedException`. Ở ví dụ, task restore interrupt status rồi trả `"INTERRUPTED"`. Với hệ thống thực, có thể nên propagate hoặc báo failure/cancellation theo contract nghiệp vụ thay vì trả một chuỗi thông thường.

## 10. Những vấn đề tinh tế khi tự cài đặt ManagedBlocker

### 10.1. isReleasable phải an toàn khi gọi nhiều lần

Sai:

~~~java
public boolean isReleasable() {
    queue.poll(); // Rút mất một item rồi bỏ kết quả.
    return false;
}
~~~

Nếu có item, phương thức này vừa lấy mất dữ liệu vừa báo “chưa sẵn sàng”. `managedBlock` có thể gọi lại và làm mất thêm item. Mẫu đúng **lưu item** và trả true khi đã có:

~~~java
return item != null || (item = queue.poll()) != null;
~~~

Snippet giả định `item` và `queue` của cùng blocker, một caller duy nhất sở hữu instance.

### 10.2. Không gọi I/O nặng trong isReleasable

Thư viện có thể gọi `isReleasable` nhiều lần, nên method nên là **kiểm tra nhanh, không chặn lâu**. Nếu đặt `socket.read()` hoặc `Thread.sleep()` vào đó, pool không được thông báo đúng khoảng thực sự sắp chặn, làm mất lợi ích managed blocking.

Phép `queue.poll()` không chặn là ví dụ hợp lý. Với một số synchronizer, có thể thử `lock.tryLock()` không chặn, nhưng cần bảo đảm caller có thể phát hiện đã acquire và unlock đúng cách.

### 10.3. Một trạng thái completion phải có nghĩa rõ ràng

Không dùng chung một boolean `ready` để biểu diễn cả “đã có dữ liệu”, “đã timeout”, “đã cancel” và “đã lấy khóa”. Có thể dùng immutable enum/result hoặc các field rõ:
- `finished`: lần chờ kết thúc.
- `item`: dữ liệu nếu có.
- `timedOut`: hết ngân sách.
- `interrupted`/exception: bị yêu cầu hủy.
- `acquired`: lock thực sự được lấy.

`block()` trả true chỉ nói rằng **không cần block thêm**, không tự báo success/business outcome.

### 10.4. isReleasable và block có thể cùng thử lấy tài nguyên

Khi `isReleasable` trả false, resource có thể xuất hiện ngay trước `block`. Ví dụ producer gọi `offer` trước khi `queue.take()`. BlockingQueue xử lý trường hợp đó an toàn: `take()` trả ngay nếu queue có item. Vì thế việc chuyển từ fast-path sang slow-path **không cần tự xây một cờ “đã nhận notify”**.

Tuy nhiên với condition/monitor tự viết, phải bảo đảm predicate và chờ dùng **cùng giao thức đồng bộ**, tránh missed notification. ManagedBlocker **không sửa được một condition protocol sai**.

### 10.5. ReentrantLock và quyền sở hữu

`tryLock()` là một thao tác **có side effect có kiểm soát**: nếu thành công, thread trở thành owner của lock. Điều đó hợp lệ trong ManagedBlocker khi bạn **lưu `acquired`** và đảm bảo release đúng. Sai nếu isReleasable lấy lock xong nhưng lại bỏ flag, rồi block lấy thêm reentrant hold mà không unlock đủ lần.

`LockBlocker.release()` của ví dụ chỉ gọi `unlock()` nếu đã acquire; không phải bên cancel hoặc main unlock hộ.

### 10.6. Exception sau khi đã lấy tài nguyên

Giả sử `block()` lấy semaphore/lock rồi ném RuntimeException trước khi `managedBlock` trả. Caller vẫn phải cleanup trong `finally`, kể cả khi chưa thấy thành công. Với tài nguyên tự quản lý, tách state **đã acquire** khỏi state **đã hoàn tất nghiệp vụ**.

### 10.7. Interruption không tự rollback side effect

`ManagedBlocker.block()` có thể nhận `InterruptedException` từ `take()` hoặc `lockInterruptibly()`. Điều đó không có nghĩa giao dịch remote đã rollback, file đã đóng, hay một cập nhật trước đó đã được hoàn tác. Dùng `finally` và idempotency/transaction theo tầng tài nguyên thực tế.

### 10.8. Thread đang giữ lock khác khi block

Ví dụ parent giữ một lock A, rồi ManagedBlocker đợi lock B, trong khi owner của B cần A. Dù ForkJoinPool cố tạo worker bù, hai task vẫn deadlock vì thứ tự sở hữu khóa. **Bù thread không sửa được deadlock do lock ordering**.

### 10.9. Không dùng ManagedBlocker để tự tạo busy polling

Sai về hiệu năng:

~~~java
public boolean block() {
    return false; // Không chặn và cũng không hoàn thành.
}
~~~

Nếu `isReleasable` cũng liên tục false, `managedBlock` có thể lặp không tạo tiến độ, chiếm CPU và gây áp lực lên pool. Đừng cài đặt một vòng quay nóng thay vì một primitive chờ hiệu quả. Với event không có signal ngay, dùng `Condition.await()`, `BlockingQueue.take()`, latch hoặc timed wait theo contract.

### 10.10. Có thể gọi ngoài ForkJoinPool nhưng không có compensation

Nếu caller là main thread hoặc thread trong một executor khác, `ForkJoinPool.managedBlock` vẫn thực hiện giao thức gọi `isReleasable/block`; nhưng không vì thế nó tạo worker bù trong một ForkJoinPool không chứa caller. Muốn pool có cơ hội xử lý managed blocking, lời gọi phải diễn ra **trong worker ForkJoinPool tương ứng**.

## 11. So sánh các lựa chọn khi gặp chặn

| Cách xử lý | Lợi ích | Giới hạn | Khi phù hợp |
| --- | --- | --- | --- |
| Gọi thẳng `BlockingQueue.take()` trong ForkJoin worker | Đơn giản, code ngắn | Unmanaged blocking có thể làm giảm worker hữu ích | Chờ rất ngắn, đã đo liveness |
| `ForkJoinPool.managedBlock` | Pool có thể biết để cân nhắc bù worker | Không bảo đảm bù, phải viết blocker đúng | Cần chặn trong ForkJoin CPU pool vì lý do thiết kế |
| Dùng I/O executor riêng | Tách worker CPU và worker I/O | Cần queue/backpressure/ownership riêng | I/O hoặc chờ tương đối dài |
| Dùng async I/O / callback | Không giữ platform thread trong khi chờ nếu API hỗ trợ | Logic phối hợp phức tạp, vẫn có concurrency/timeout | Nhiều I/O đồng thời |
| Timed API như `poll(timeout)` | Giới hạn thời gian block | Không tự hủy remote business | Cần deadline/cancel |
| `ReentrantLock.lockInterruptibly` | Chờ khóa có thể nhận interrupt | Vẫn có lock contention/deadlock nếu thứ tự sai | Lock phải đáp ứng cancellation |
| `CompletableFuture` pipeline | Dễ compose async stages | Cancel future không đồng nghĩa ngắt worker | Khi có pipeline không cần block chờ kết quả |
| Thay đổi kiến trúc, không chờ child ở CPU worker | Giảm nguy cơ starvation | Có thể cần thiết kế result aggregator | Khi downstream có dependency phức tạp |

### Với Java 17 và virtual threads

Virtual threads là tính năng của các JDK mới hơn Java 17; **không có virtual-thread API ổn định trong Java 17**. Đừng viết ví dụ dùng `Executors.newVirtualThreadPerTaskExecutor()` rồi ghi “Java 17+ chạy được”. Khi chạy trên JDK mới, mô hình virtual threads có thể thay đổi trade-off của blocking I/O, nhưng nó **không thay thế** contract `ManagedBlocker` khi đang phân tích `ForkJoinPool` trên Java 17.

## 12. Kiểm thử correctness và liveness

Một demo chỉ chạy đúng trên máy của bạn không chứng minh rằng pool luôn bù worker. Test nên tách **correctness**, **liveness** và **hiệu năng**:

### Test correctness

- Fast path: queue đã có item trước lúc gọi, `isReleasable` trả true và dữ liệu không mất.
- Slow path: queue rỗng rồi producer `offer` sau, item được lấy đúng một lần.
- Nhiều lần kiểm tra: `isReleasable` không tiêu thụ nhiều item hoặc acquire lock nhiều lần.
- Lock path: `tryLock`/`lockInterruptibly` lấy khóa đúng thread, unlock đúng một lần.
- Timeout: `block()` trả true với trạng thái timedOut riêng; không báo success giả.
- Interruption: `InterruptedException` được propagate/restore/biến thành cancellation theo contract.
- Input/cấu hình pool: parallelism thấp, số task cao, không phụ thuộc một spare thread nhất định.

### Test liveness

- **Không xây test bắt buộc worker bù xuất hiện**: một JVM/pool có thể không chọn bù trong cùng lịch thực thi.
- Có thread/event producer độc lập để mở chờ, tránh test treo chỉ vì thiếu compensation.
- Mỗi lần đợi quan trọng có **timeout**; nếu quá hạn, test báo lỗi có thể chẩn đoán.
- Giữ quan hệ thứ tự bằng `CountDownLatch`, không bằng `Thread.sleep(100)` đoán worker đã chạy tới đâu.
- Với custom pool/giới hạn thấp, thử tình huống saturation; xác nhận code xử lý failure thay vì treo không hạn.
- Với blocking I/O, kiểm tra timeout/close theo đúng API và không coi interrupt là bảo đảm thoát tức thì.

### Test hiệu năng

- So sánh unmanaged vs managed blocking trên cùng workload thật, cùng input và pool configuration.
- Đo thời gian hoàn tất tác vụ hữu ích, tốc độ request, p95/p99 latency, số worker đang chạy và memory footprint.
- Warm-up Java code, JIT/GC, chạy nhiều lần; đừng lấy một mẫu nhỏ rồi khẳng định.
- Theo dõi `ForkJoinPool.getPoolSize()`, `getActiveThreadCount()`, `getRunningThreadCount()` và `getStealCount()` như **thông tin giám sát thay đổi theo thời điểm**, không làm bằng chứng một số worker bù cố định.
- Nếu đo throughput, giới hạn số outstanding requests và downstream capacity; compensation có thể tăng số request chờ I/O cùng lúc mà không tăng throughput thật.

### Ba loại giới hạn cần phân biệt

1. **Giới hạn CPU:** thêm worker không tăng physical cores, có thể tạo context switching.
2. **Giới hạn số worker:** pool/configuration/JVM có bound; không thể tạo vô tận spare threads.
3. **Giới hạn downstream:** connection pool, database, rate limit, remote service, socket/file descriptors. Một worker bổ sung không tạo thêm connection nếu connection pool đã cạn.

Đôi lúc cách đúng là **giảm concurrency và tăng backpressure**, không tăng worker count.

## 13. Những hiểu lầm hay gặp

1. **“ManagedBlocker tạo thêm thread chắc chắn.”** Sai; API cho phép pool cân nhắc, không bảo đảm.
2. **“Mỗi blocked worker có đúng một spare worker.”** Sai; bù dựa vào tình trạng pool, chính sách và resource.
3. **“isReleasable true nghĩa đã thành công.”** Sai; nó nghĩa không cần block nữa, timeout có thể là kết thúc.
4. **“block true nghĩa có item.”** Sai; caller phải đọc outcome được lưu.
5. **“isReleasable gọi đúng một lần.”** Sai; contract yêu cầu chịu được gọi lặp.
6. **“isReleasable nên thực hiện I/O chậm cho chắc.”** Sai; nó là kiểm tra nhanh, không chặn lâu.
7. **“isReleasable có thể queue.poll rồi bỏ kết quả.”** Sai; bạn đã làm mất item.
8. **“block luôn luôn được gọi.”** Sai; fast-path trả true có thể bỏ qua hoàn toàn block.
9. **“managedBlock chỉ dùng được bên trong pool.”** Sai; ngoài pool vẫn có semantics chờ nhưng không có pool compensation.
10. **“Giữ được ReentrantLock mà không cần unlock.”** Sai; phải release trên thread sở hữu.
11. **“Thread khác unlock hộ khi cancel.”** Sai; `ReentrantLock` kiểm tra owner.
12. **“ManagedBlocker giúp bất kỳ monitor deadlock nào tiến triển.”** Sai; deadlock do vòng phụ thuộc cần sửa thuật toán.
13. **“ManagedBlocker làm mọi I/O trả lời nhanh hơn.”** Sai; nó chỉ hỗ trợ pool điều phối worker, không thay đổi downstream latency.
14. **“Pool luôn giữ đúng P worker hoạt động.”** Sai; parallelism là mục tiêu, có hạn chế và blocking.
15. **“Tăng maximumPoolSize là luôn tốt.”** Sai; có thể tăng memory/CPU scheduling/downstream contention.
16. **“ForkJoinPool tự nhận biết mọi Thread.sleep hoặc socket read.”** Sai; unmanaged blocking không có bảo đảm điều chỉnh tương đương.
17. **“block false liên tục vẫn tốt.”** Sai; có thể biến thành busy loop không tiến triển.
18. **“Future.cancel(true) chắc chắn dừng ForkJoinTask.”** Sai; cancellation của ForkJoinTask có contract riêng, không được suy nó interrupt worker như FutureTask.
19. **“Đợi join trong khi giữ lock là ổn.”** Có thể gây deadlock nếu child cần lock.
20. **“Có thêm spare worker thì không cần backpressure.”** Sai; tài nguyên downstream vẫn hữu hạn.

## 14. Checklist triển khai trong ứng dụng

1. Workload này chủ yếu **CPU** hay **I/O/blocking**? Nếu I/O chiếm phần lớn, có nên tách executor?
2. Đoạn nào thực sự có thể block? Có API bất đồng bộ hoặc timed thay thế không?
3. `isReleasable()` có nhanh, không chặn và chịu được gọi lặp?
4. Nếu nó gọi `tryLock/poll` có lưu kết quả/ownership để không làm mất dữ liệu?
5. `block()` chỉ trả true khi **không cần chặn nữa**, không đánh đồng với success?
6. Có trạng thái riêng cho timeout, item nhận được, acquired lock và interruption?
7. Có đóng resource/unlock ở finally ngay cả khi managedBlock ném exception?
8. Có dùng deadline tổng thay vì tái cấp nguyên timeout ở từng call?
9. Nếu không có spare worker, có một đường tiến triển hợp lệ khác không?
10. Nếu pool chạm giới hạn/saturation, code có fail/timeout/fallback phù hợp?
11. Worker có đang giữ lock khác khi block, khiến deadlock do lock ordering không?
12. Tăng worker có làm downstream connection pool quá tải không?
13. Có test với parallelism=1/2 và nhiều tasks, nhưng không hard-code số threads bù?
14. Có quan sát shutdown/cleanup, không chỉ isDone của ForkJoinTask?
15. Có benchmark riêng cho latency/throughput và theo dõi memory/GC/native threads?
16. Có ghi rõ ownership của custom ForkJoinPool và không shutdown pool dùng chung theo từng request?
17. Có lỗi bất ngờ từ block/interrupt không? Chúng có được xử lý để không báo success giả?
18. Có thể thay managed blocking bằng một pipeline không chờ để giảm complexity không?
19. Các metric là snapshot/ước lượng hay số đo tích lũy? Không dùng chúng làm invariant?
20. Những giả định về JDK/version/common pool config đã được xác nhận trên môi trường chạy chưa?

## 15. Câu hỏi tự kiểm tra

1. `ManagedBlocker` có mấy phương thức? **Hai:** `isReleasable()` và `block()`.
2. Khi `isReleasable()` trả true, `managedBlock` có phải gọi `block()` không? **Không**.
3. Vì sao `isReleasable()` phải chịu được gọi nhiều lần? **Pool có thể kiểm tra lặp trước quyết định block/compensation**.
4. `block()` trả true nghĩa là gì? **Không cần chặn thêm**, không nhất thiết nghiệp vụ thành công.
5. `block()` có được ném `InterruptedException` không? **Có**, khi implementation chờ interruptible.
6. Có dùng `managedBlock` từ main thread không? **Có**, nhưng không có compensation của một pool không chứa main.
7. Tại sao QueueTaker lưu item trong `isReleasable`? **`poll` tiêu thụ item; không được đánh mất dữ liệu**.
8. Với `ReentrantLock`, ai unlock? **Thread thực sự lấy lock**.
9. `ForkJoinPool(2)` có bảo đảm mỗi thời điểm luôn hai worker CPU hữu ích không? **Không**.
10. Một managedBlock trong pool có tạo một worker mới không? **Có thể, không bảo đảm**.
11. Nếu pool đã chạm maximumPoolSize, có chắc bù được worker không? **Không**, còn phụ thuộc cấu hình saturation.
12. Nếu task chờ remote HTTP lâu, thêm worker có giảm latency của HTTP đó không? **Không**.
13. Nếu tất cả workers chờ trên một lock vòng phụ thuộc, spare worker có sửa deadlock không? **Không**.
14. Tại sao `isReleasable` không nên block lâu? **Pool cần cơ hội nhận biết đoạn có thể chặn ở `block()`**.
15. `block()` luôn phải trả true không? **Không**; false nghĩa cần thử chờ lại.
16. Nếu cả `isReleasable` và `block` trả false mãi, hậu quả? **Có thể lặp vô hạn/busy polling**.
17. `getRunningThreadCount` có là số worker bù chính xác không? **Không**, chỉ là metric trạng thái/ước lượng.
18. Khi timed poll trả null, blocker có thể trả true không? **Có**, nếu deadline đã hết và không cần chờ thêm; caller đọc status timeout riêng**.
19. ManagedBlocker có thay thế executor I/O chuyên dụng trong mọi trường hợp không? **Không**.
20. Khi nào nên ưu tiên tách I/O executor? **Khi công việc bị chặn dài/thường xuyên, cần quản lý queue, backpressure và tài nguyên downstream rõ**.
21. ForkJoinTask.cancel(true) có bảo đảm interrupt leaf không? **Không**, cancellation của ForkJoinTask có semantics riêng.
22. Nếu một task có thể chặn trong khi vẫn giữ lock khác, cần xét gì? **Thứ tự lock và liveness để tránh deadlock**.
23. Tại sao `queue.poll` trong isReleasable cần ghi state `item`? **Để idempotent qua các lần kiểm tra và không mất dữ liệu**.
24. Tại sao không in `pool.getPoolSize()==3` như stdout cố định? **Compensation tùy runtime và cấu hình**.
25. ManagedBlocker cải thiện điều gì chủ yếu? **Giúp ForkJoinPool có thông tin về khả năng chặn để cân nhắc duy trì parallelism khi có điều kiện**.

## 16. Kết luận

`ForkJoinPool.ManagedBlocker` cho phép code khai báo một thao tác có thể chặn để pool quản lý parallelism tốt hơn. `isReleasable()` kiểm tra **không cần block nữa hay chưa**, có thể được gọi nhiều lần; `block()` thực hiện chờ, có thể ném `InterruptedException`, trả true khi không cần chờ thêm. `ForkJoinPool.managedBlock()` điều phối hai method theo vòng lặp có contract rõ.

**Giới hạn quan trọng nhất:** compensation chỉ là **khả năng**, không phải bảo đảm luôn có worker bù hay một worker mới cho mỗi lần chặn. Nếu hệ thống có deadlock, resource limit, I/O treo, timeout không được cấu hình hoặc downstream quá tải, ManagedBlocker không tự sửa. Hãy thiết kế **liveness, resource ownership, backpressure, cancellation và deadline** trước, rồi chỉ dùng managed blocking khi mô hình Fork/Join và workload thực sự cần nó.

## Tài liệu tham khảo Java SE 17

- [ForkJoinPool.ManagedBlocker](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.ManagedBlocker.html): hợp đồng `isReleasable()` và `block()`, queue/lock examples.
- [ForkJoinPool](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): `managedBlock()`, compensation, parallelism, giới hạn, configuration và metrics.
- [ForkJoinTask](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinTask.html): task lifecycle và cancellation semantics.
- [BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): `poll`, `take`, `poll(timeout)`.
- [ReentrantLock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): `tryLock`, `lockInterruptibly`, `unlock`.
- [CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): đợi và release trong ví dụ.
- [Java Language Specification `17](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): Java memory model, happens-before.
