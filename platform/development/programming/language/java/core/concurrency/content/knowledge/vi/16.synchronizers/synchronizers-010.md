# Sử dụng synchronizer trong test concurrency của Java

## 1. Vì sao kiểm thử đa luồng khó hơn kiểm thử tuần tự?

Trong một phép thử tuần tự, các dòng lệnh chạy theo thứ tự tương đối dễ suy luận. Khi nhiều thread cùng truy cập state, lịch thực thi phụ thuộc scheduler, CPU, lock, I/O, JIT và các quan hệ đồng bộ. Một bài test chỉ chạy thành công một lần **không chứng minh** chương trình luôn đúng dưới mọi interleaving.

Ví dụ có hai worker cùng thực hiện phép tăng `counter++` trên một trường thường. Phép tăng là tổ hợp **đọc → tính → ghi**, không phải một transaction nguyên tử. Nếu chạy thử 100 lần và lần nào cũng nhận kết quả đúng, lỗi **lost update** vẫn có thể tồn tại nhưng chưa xuất hiện do lịch chạy.

Mục tiêu của bài này là sử dụng các **synchronizer trong `java.util.concurrent`** để:

1. Cho nhiều worker tới cùng một **điểm bắt đầu** mà không phải đoán thời gian bằng `Thread.sleep()`.
2. Chủ động buộc một số **interleaving** xảy ra, qua đó tái hiện bug.
3. Chờ kết thúc bằng **tín hiệu có timeout**, tránh test treo vô hạn.
4. Ghi nhận exception từ worker và **làm test thất bại** ở thread kiểm thử.
5. Kiểm tra một số **bất biến** về dữ liệu, số lượt xử lý và giới hạn concurrent access.
6. Phân biệt **deterministic coordination test** với stress test và những công cụ chuyên sâu kiểm tra Java Memory Model.

Đây là kiến thức **Java concurrency nói chung**, dùng ví dụ **Java 17+** và API JDK; không phụ thuộc Spring hay framework kiểm thử cụ thể.

## 2. Synchronizer là gì trong một bài test?

Các công cụ đồng bộ không chỉ phục vụ production; chúng cũng giúp test biểu diễn chính xác mối quan hệ **“A phải xảy ra trước B”**.

| Công cụ | Vai trò hữu ích trong test | Điểm cần tránh |
| --- | --- | --- |
| `CountDownLatch` | Đợi N worker đến mốc; phát một tín hiệu bắt đầu chung; chờ N tác vụ xong | Latch chỉ đi từ count ban đầu về 0, **không reset** |
| `CyclicBarrier` | Buộc N participant gặp nhau ở **nhiều vòng/phases** | Một participant bị lỗi/timeout có thể làm barrier **broken** |
| `Phaser` | Điều phối nhiều phase, số participant có thể **register/deregister** động | Dùng `arriveAndAwaitAdvance()` vô hạn có thể làm test treo |
| `Semaphore` | Kiểm tra tối đa N tác vụ cùng dùng một resource | Chỉ release permit đã acquire; đừng suy chỉ số active từ số thread |
| `BlockingQueue` | Chuyển dữ liệu/sự kiện giữa worker và test thread, chờ có hạn bằng `poll` | Queue rỗng tại một thời điểm không chứng minh toàn pipeline hoàn tất |
| `Future` / `ExecutorService` | Thu kết quả và lỗi worker qua `get()`; giới hạn chờ và gửi cancellation | `get(timeout)` hết hạn **không tự hủy** task |
| `ReentrantLock` + `Condition` | Dàn dựng predicate/condition và kiểm tra wakeup | `await` cần kiểm tra predicate trong **while**, không chỉ `if` |

**Synchronizer không kiểm soát toàn bộ scheduler.** Một latch xác nhận worker đã tới vị trí được đánh dấu; nó không ép worker tiếp tục chạy ngay lập tức sau khi mở cổng và không cho phép suy ra một thứ tự tùy ý chưa được đồng bộ.

### Tên các mốc hữu ích trong test

- **Ready gate:** tất cả worker đã chuẩn bị xong, sắp đợi lệnh bắt đầu.
- **Start gate:** main/test thread mở để các worker được phép đi tiếp.
- **Done gate:** tất cả worker đã đi qua khối cần kiểm tra (kể cả đường lỗi, nếu thiết kế đúng).
- **Phase barrier:** chỉ cho các participant đi qua khi tất cả tới một mốc của **cùng vòng**.
- **Release gate:** giữ worker tại vị trí đã biết cho đến khi test quyết định giải phóng.

Bằng cách nêu rõ các mốc, ta kiểm tra đúng **hợp đồng đồng thời** thay vì so sánh một lượng mili-giây tình cờ.

## 3. Tại sao `Thread.sleep()` không phải cơ chế phối hợp test?

Mẫu dễ gặp:

```java
// Snippet có race: không bảo đảm worker đã thực hiện việc cần thiết.
worker.start();
Thread.sleep(100);
assertState();
```

Đây là snippet, `worker` và `assertState` chưa khai báo. Sleep 100 ms **không xác nhận** worker đã bắt đầu, tới critical section hoặc hoàn tất. Máy CI chậm, GC pause hoặc scheduler bị tải có thể khiến test **flaky**. Ngược lại, trên máy nhanh test có thể luôn pass mà không tạo interleaving cần bắt lỗi.

**Thay bằng một tín hiệu có nghĩa:** worker `ready.countDown()` tại vị trí muốn quan sát; main gọi `ready.await(timeout, unit)` và kiểm tra kết quả. Sau đó nếu muốn cho worker chạy, main mở `start.countDown()`. Tín hiệu thể hiện sự kiện cụ thể, không phải dự đoán thời gian.

Sleep vẫn có thể dùng khi chính **thời gian** là đối tượng kiểm thử, nhưng không nên dùng nó làm bằng chứng ngầm rằng một thread đã đạt một trạng thái logic.

## 4. Pattern cơ bản: ready → start → done với CountDownLatch

Để cho N worker chuẩn bị rồi cùng nhận lệnh bắt đầu:

```text
Main/test                            Worker 1 ... Worker N
---------                            ----------------------
Tạo ready(N), start(1), done(N)
                                     ready.countDown()
                                     start.await()
ready.await(timeout) ----------->    mọi worker đã tới start gate
start.countDown() -------------->    bắt đầu khối cần đo
                                     work()
                                     done.countDown() trong finally
done.await(timeout) ----------->     tất cả đã kết thúc khối
kiểm tra invariant + worker errors
```

**Đừng nhầm** “mở cổng cùng lúc” với “thực thi cùng một thời điểm CPU”. Sau `start.countDown()`, scheduling vẫn bất định. Pattern chỉ đảm bảo các worker **không đi qua start gate trước khi main cho phép**.

### Java 17+ hoàn chỉnh: phép kiểm thử tăng atomic

Tạo file `LatchStartTest.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class LatchStartTest {
    public static void main(String[] args) throws InterruptedException {
        int workers = 4;
        CountDownLatch ready = new CountDownLatch(workers);
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(workers);
        AtomicInteger counter = new AtomicInteger();
        AtomicReference<Throwable> workerFailure = new AtomicReference<>();
        Thread[] threads = new Thread[workers];

        for (int i = 0; i < workers; i++) {
            threads[i] = new Thread(() -> {
                try {
                    ready.countDown();
                    if (!start.await(5, TimeUnit.SECONDS)) {
                        throw new AssertionError("Start gate timed out");
                    }
                    counter.incrementAndGet();
                } catch (Throwable error) {
                    workerFailure.compareAndSet(null, error);
                    if (error instanceof InterruptedException) {
                        Thread.currentThread().interrupt();
                    }
                } finally {
                    done.countDown();
                }
            }, "worker-" + i);
            threads[i].start();
        }

        try {
            if (!ready.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Workers not ready");
            }
            start.countDown();
            if (!done.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Workers did not finish");
            }
            if (workerFailure.get() != null) {
                throw new AssertionError("Worker failed", workerFailure.get());
            }
            if (counter.get() != workers) {
                throw new AssertionError("Wrong counter");
            }
            System.out.println("Ready workers: " + workers);
            System.out.println("Atomic increments: " + counter.get());
        } finally {
            start.countDown(); // Không để worker kẹt do test thất bại.
            for (Thread thread : threads) {
                thread.interrupt();
            }
            for (Thread thread : threads) {
                thread.join();
            }
        }
    }
}
```

Biên dịch/chạy:

```bash
javac LatchStartTest.java
java LatchStartTest
```

Đầu ra khi không có interrupt từ bên ngoài và test pass:

```text
Ready workers: 4
Atomic increments: 4
```

**Các điểm quan trọng:**

1. Worker báo `ready` **trước** khi đợi `start`, nên main có thể xác nhận chúng đã đến cổng.
2. `AtomicInteger.incrementAndGet()` là một phép cập nhật nguyên tử. Kết quả cuối luôn là 4 nếu cả bốn phép tăng đã chạy thành công.
3. `done.countDown()` nằm trong `finally`, nên một worker ném exception vẫn có thể báo **đã kết thúc đường xử lý**, tránh main chờ vô hạn do thiếu tín hiệu.
4. Exception được ghi vào `AtomicReference<Throwable>` để main **đọc lại và làm test fail**. Exception ở thread phụ không tự biến thành failure của thread main.
5. Mọi `await` nhạy với tiến triển đều có timeout. `finally` mở start gate, gửi interrupt, rồi `join` để giảm nguy cơ bỏ lại worker.
6. Demo này kiểm tra một lần theo lịch đã phối hợp, **không chứng minh** toàn bộ thuật toán concurrent đúng với mọi interleaving.

Trong test production, khi worker có thể cố tình không phản hồi interrupt, `join()` không timeout cuối cùng cũng có nguy cơ treo. Có thể dùng timed join, executor shutdown có deadline và theo dõi thread còn sống; một timeout test không có nghĩa Java có thể cưỡng ép dừng thread một cách an toàn.

## 5. Dựng interleaving để tái hiện lost update một cách xác định

Một phương pháp học hiệu quả là **cố tình viết code sai**, rồi dùng synchronizer **ép hai thread cùng đọc một giá trị cũ trước khi bất kỳ thread nào được phép ghi**.

Giả sử giá trị ban đầu bằng 1. Hai thread đều làm:

```java
int snapshot = counter.value;
counter.value = snapshot + 1;
```

Đây là snippet, `counter` chưa khai báo. Nếu tách read và write bằng latch, cả hai thread có thể cùng đọc 1 rồi đều ghi 2. Kết quả 2 **thay vì 3** là lỗi lost update có thể tái hiện mà **không cần ngủ/đoán scheduling**.

### Java 17+ hoàn chỉnh: chứng minh volatile không biến RMW thành atomic

Tạo file `LostUpdateTest.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class LostUpdateTest {
    private static final class Counter {
        volatile int value = 1;
    }

    public static void main(String[] args) throws InterruptedException {
        Counter counter = new Counter();
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch mayWrite = new CountDownLatch(1);
        AtomicReference<Throwable> failure = new AtomicReference<>();

        Runnable nonAtomicIncrement = () -> {
            try {
                int old = counter.value;
                bothRead.countDown();
                if (!mayWrite.await(5, TimeUnit.SECONDS)) {
                    throw new AssertionError("Write gate timeout");
                }
                counter.value = old + 1;
            } catch (Throwable error) {
                failure.compareAndSet(null, error);
                if (error instanceof InterruptedException) {
                    Thread.currentThread().interrupt();
                }
            }
        };

        Thread left = new Thread(nonAtomicIncrement, "left");
        Thread right = new Thread(nonAtomicIncrement, "right");
        left.start();
        right.start();

        try {
            if (!bothRead.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Both reads not reached");
            }
            mayWrite.countDown();
            left.join();
            right.join();

            if (failure.get() != null) {
                throw new AssertionError("Worker failed", failure.get());
            }
            System.out.println("Observed after two increments: "
                    + counter.value);
            System.out.println("Expected with atomic increments: 3");
        } finally {
            mayWrite.countDown();
            left.interrupt();
            right.interrupt();
        }
    }
}
```

Biên dịch/chạy:

```bash
javac LostUpdateTest.java
java LostUpdateTest
```

Đầu ra:

```text
Observed after two increments: 2
Expected with atomic increments: 3
```

**Tại sao kết quả 2 là xác định?**

- Mỗi worker chụp `old = counter.value` **trước** `bothRead.countDown()`.
- Main chỉ mở `mayWrite` **sau khi cả hai worker đã countDown**, tức cả hai đã đọc giá trị cũ.
- Vì chưa có writer nào được đi qua `mayWrite.await()`, cả hai snapshot đều là **1**.
- Hai worker viết cùng giá trị 2 theo mọi thứ tự; final `value` là 2.
- `volatile` đảm bảo các tính chất visibility/ordering của từng truy cập nhưng **không làm cặp đọc–ghi thành một thao tác atomic**.

Đây là một **test chứng minh bug**: việc in `2` là hành vi có chủ đích, không phải kết quả đúng của thuật toán tăng. Khi sửa production code, dùng `AtomicInteger.incrementAndGet()`, `getAndAdd()`, khóa phù hợp hoặc CAS loop. Không cố “sửa” bằng cách chèn `Thread.sleep` giữa hai dòng.

**Một cảnh báo về test orchestration:** `mayWrite` là đồng bộ **chỉ dùng để dựng lịch**. Nó không đại diện cho cơ chế bảo vệ counter trong code production. Hãy tránh đưa các gate dành cho test vào public API của đối tượng nghiệp vụ nếu có thể dùng injection/hook nội bộ hoặc harness kiểm thử tách biệt.

## 6. CyclicBarrier: nhiều lượt phối hợp, không phải CountDownLatch dùng lại

`CountDownLatch` là một cổng **một lần**: count về 0 thì luôn mở. Nếu test cần worker gặp nhau qua nhiều vòng, `CyclicBarrier` thường phù hợp hơn.

`new CyclicBarrier(parties, barrierAction)` cho phép **N participant** cùng gọi `await()`. Khi participant cuối đến, barrier action chạy trước khi những waiter được thả; barrier được dùng lại cho **generation tiếp theo**.

- `await()` có thể ném `InterruptedException` hoặc `BrokenBarrierException`.
- `await(timeout, unit)` có thể ném thêm `TimeoutException`.
- Nếu một participant bị interrupt/timeout, barrier có thể chuyển sang **broken state**. Các participant khác nhận lỗi tương ứng; test phải có cleanup.
- `getNumberWaiting()` chỉ là snapshot để quan sát, không nên dùng làm cơ sở duy nhất để ra quyết định logic test.

### Java 17+: hai worker và main qua hai phase

Tạo file `BarrierRoundsTest.java`:

```java
import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class BarrierRoundsTest {
    public static void main(String[] args) throws Exception {
        AtomicInteger completedRounds = new AtomicInteger();
        AtomicInteger workerSteps = new AtomicInteger();
        AtomicReference<Throwable> failure = new AtomicReference<>();

        CyclicBarrier barrier = new CyclicBarrier(
                3, completedRounds::incrementAndGet);

        Runnable worker = () -> {
            try {
                for (int round = 0; round < 2; round++) {
                    workerSteps.incrementAndGet();
                    barrier.await(5, TimeUnit.SECONDS);
                }
            } catch (Throwable error) {
                failure.compareAndSet(null, error);
            }
        };

        Thread first = new Thread(worker, "first");
        Thread second = new Thread(worker, "second");
        first.start();
        second.start();

        try {
            for (int round = 0; round < 2; round++) {
                barrier.await(5, TimeUnit.SECONDS);
            }
            first.join();
            second.join();

            if (failure.get() != null) {
                throw new AssertionError("Worker failed", failure.get());
            }
            System.out.println("Barrier rounds: "
                    + completedRounds.get());
            System.out.println("Worker steps: " + workerSteps.get());
        } finally {
            barrier.reset();
            first.interrupt();
            second.interrupt();
            first.join();
            second.join();
        }
    }
}
```

Chạy:

```bash
javac BarrierRoundsTest.java
java BarrierRoundsTest
```

Đầu ra khi không có interrupt bên ngoài:

```text
Barrier rounds: 2
Worker steps: 4
```

**Phân tích:**

- Barrier có **3 parties**: main + hai worker.
- Mỗi worker tăng `workerSteps` trước khi chạm barrier ở mỗi phase; tổng 2 × 2 = 4.
- Barrier action tăng `completedRounds` **một lần cho mỗi generation thành công**; có hai generation nên tổng bằng 2.
- Không cần biết worker nào chạy trước.
- Nếu worker bỏ cuộc hoặc một lời gọi đợi quá hạn, main không được tiếp tục báo test pass. Phải làm test thất bại, reset/break barrier và dọn thread.

`barrier.reset()` trong `finally` chỉ là cleanup của demo sau khi main đã hoàn thành hoặc gặp lỗi; **không** thay thế cơ chế recovery đúng của một thuật toán production đang dùng barrier.

### Dùng barrier để phát hiện lỗi nào?

- Hai giai đoạn ghi/đọc dữ liệu phải hoàn thành trước khi bước sang round tiếp.
- Chặn worker ở các checkpoint được biết trước để kiểm tra trạng thái trung gian.
- Tạo áp lực chạy đồng thời mà không phụ thuộc `sleep`.
- Xác nhận số lần một phase hoàn tất; thử các đường exception/timeout của participant.

Tuy nhiên, barrier không kiểm tra tự động rằng dữ liệu chia sẻ được bảo vệ đúng. Sau mỗi phase, **vẫn cần assertion** về invariant theo Java Memory Model và hợp đồng của hệ thống.

## 7. Phaser: nhiều phase và số participant thay đổi

`Phaser` phù hợp khi số worker tham gia thay đổi theo thời điểm. Các API:

- `register()` / `bulkRegister(n)`: đăng ký participant.
- `arriveAndAwaitAdvance()`: báo đã tới phase hiện tại và chờ chuyển phase.
- `arriveAndDeregister()`: báo đã tới và **rút khỏi những phase tiếp theo**.
- `getPhase()`: phase hiện tại; khi terminated có thể trả giá trị âm theo hợp đồng.
- `awaitAdvanceInterruptibly(phase, timeout, unit)`: đợi một phase thay đổi bằng một lần chờ hỗ trợ interrupt/timeout.

**Điểm khác:** `arriveAndAwaitAdvance()` có đường chờ **uninterruptible** theo hợp đồng, nên không tự coi đây là wait có timeout. Nếu một participant biến mất mà không arrive/deregister, phase có thể không tiến triển.

### Ví dụ Java 17+ hoàn chỉnh: đăng ký worker động

Tạo file `PhaserRegistrationTest.java`:

```java
import java.util.concurrent.Phaser;
import java.util.concurrent.atomic.AtomicInteger;

public class PhaserRegistrationTest {
    public static void main(String[] args) throws InterruptedException {
        Phaser phaser = new Phaser(1); // Main là một party.
        AtomicInteger operations = new AtomicInteger();
        Thread[] workers = new Thread[2];

        for (int i = 0; i < workers.length; i++) {
            phaser.register();
            workers[i] = new Thread(() -> {
                try {
                    operations.incrementAndGet();
                    phaser.arriveAndAwaitAdvance();
                } finally {
                    phaser.arriveAndDeregister();
                }
            }, "phase-worker-" + i);
            workers[i].start();
        }

        // Đợi cả main và hai worker đều tới phase 0.
        phaser.arriveAndAwaitAdvance();
        phaser.arriveAndDeregister();

        for (Thread worker : workers) {
            worker.join();
        }

        System.out.println("Operations: " + operations.get());
        System.out.println("All parties deregistered: "
                + phaser.isTerminated());
    }
}
```

Chạy:

```bash
javac PhaserRegistrationTest.java
java PhaserRegistrationTest
```

Đầu ra khi cả hai worker không lỗi:

```text
Operations: 2
All parties deregistered: true
```

**Giải thích:** main bắt đầu là một party, rồi đăng ký hai worker. Mỗi worker thực hiện một operation rồi arrive phase 0. Main cũng arrive; khi cả ba đã tới thì phase có thể advance. Sau đó mỗi participant `arriveAndDeregister()`, cuối cùng không còn party đăng ký nên phaser kết thúc.

**Cảnh báo ứng dụng:** demo này ưu tiên cho thấy cơ chế register/deregister. Trong test production, nếu một worker ném exception trước `arriveAndAwaitAdvance` hoặc bị kẹt, main có thể chờ vô hạn. Khi cần deadline chắc chắn, dùng đường `arrive()` rồi `awaitAdvanceInterruptibly(phase, timeout, unit)`, kèm `forceTermination()` và cleanup khi test thất bại; đồng thời nhớ **ghi nhận lỗi worker** ở thread kiểm thử. Không dùng `Thread.sleep` để “chắc” worker đã tới phase.

## 8. Semaphore: kiểm tra trần mức đồng thời của tài nguyên

`Semaphore` đặc biệt hữu ích để test **không bao giờ có hơn N tác vụ cùng vào vùng sử dụng tài nguyên**. Một Semaphore với 2 permit giới hạn tối đa hai người giữ permit tại cùng thời điểm **nếu mọi đường vào đều thực hiện acquire và mọi đường ra release đúng quy tắc**.

Dùng hai worker chiếm hết permit, đồng thời đặt worker thứ ba đang chờ. Test kiểm tra worker thứ ba **không thể vào trước khi main giải phóng** hai worker đầu.

### Java 17+: mô phỏng tài nguyên có hai slot

Tạo file `SemaphoreLimitTest.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class SemaphoreLimitTest {
    public static void main(String[] args) throws InterruptedException {
        Semaphore slots = new Semaphore(2);
        CountDownLatch twoInside = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch thirdAttempted = new CountDownLatch(1);
        CountDownLatch thirdEntered = new CountDownLatch(1);
        AtomicInteger current = new AtomicInteger();
        AtomicInteger peak = new AtomicInteger();
        AtomicReference<Throwable> failure = new AtomicReference<>();

        Runnable occupant = () -> {
            boolean acquired = false;
            try {
                slots.acquire();
                acquired = true;
                int now = current.incrementAndGet();
                peak.accumulateAndGet(now, Math::max);
                twoInside.countDown();
                if (!release.await(5, TimeUnit.SECONDS)) {
                    throw new AssertionError("Release gate timed out");
                }
            } catch (Throwable error) {
                failure.compareAndSet(null, error);
                if (error instanceof InterruptedException) {
                    Thread.currentThread().interrupt();
                }
            } finally {
                if (acquired) {
                    current.decrementAndGet();
                    slots.release();
                }
            }
        };

        Thread a = new Thread(occupant, "a");
        Thread b = new Thread(occupant, "b");
        Thread c = new Thread(() -> {
            boolean acquired = false;
            try {
                thirdAttempted.countDown();
                slots.acquire();
                acquired = true;
                thirdEntered.countDown();
            } catch (InterruptedException e) {
                failure.compareAndSet(null, e);
                Thread.currentThread().interrupt();
            } finally {
                if (acquired) {
                    slots.release();
                }
            }
        }, "c");

        a.start();
        b.start();

        try {
            if (!twoInside.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("First two did not enter");
            }
            c.start();
            if (!thirdAttempted.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Third did not attempt");
            }
            System.out.println("Third entered before release: "
                    + (thirdEntered.getCount() == 0));
            release.countDown();

            a.join();
            b.join();
            c.join();
            if (failure.get() != null) {
                throw new AssertionError("Worker failed", failure.get());
            }
            System.out.println("Peak occupied: " + peak.get());
            System.out.println("Available permits: "
                    + slots.availablePermits());
        } finally {
            release.countDown();
            a.interrupt();
            b.interrupt();
            c.interrupt();
            a.join();
            b.join();
            if (c.getState() != Thread.State.NEW) {
                c.join();
            }
        }
    }
}
```

Chạy:

```bash
javac SemaphoreLimitTest.java
java SemaphoreLimitTest
```

Đầu ra bình thường:

```text
Third entered before release: false
Peak occupied: 2
Available permits: 2
```

**Tại sao giá trị trước release phải là false?** Main chỉ tạo worker c sau khi `twoInside` đã về 0: hai worker a/b đã **acquire và chưa release** permit, vì còn chờ cổng `release`. Worker c có thể đã bắt đầu gọi `acquire` hoặc đang sắp gọi, nhưng không thể lấy permit khi `availablePermits == 0`. Do đó `thirdEntered` chưa được countDown trước khi main mở cổng.

**Tại sao peak bằng 2?** Chỉ hai worker a/b tăng bộ đếm `current` sau acquire; với việc release đúng sau sử dụng, không có lượt tăng thứ ba. Ví dụ kiểm tra giới hạn slot, không cố dùng scheduling để tăng peak.

Trong hệ thống thật, muốn theo dõi **toàn bộ** việc dùng resource, mọi caller (kể cả worker c) phải cập nhật metric theo cùng giao thức. Demo này chỉ đo occupancy của hai worker được thiết kế để giữ slot và quan sát worker thứ ba có được vào sớm hay không.

**Quy tắc permit:** chỉ `release()` nếu `acquire()` đã thành công. Nếu release khi chưa acquire, semaphore có thể tăng permit vượt mức dự định và test cho kết quả sai.

## 9. Future.get(timeout): quan sát lỗi worker và không để test chờ mãi

`Thread.start()` không tự mang exception trong worker về thread test. Nếu worker ném `AssertionError` trong một thread khác, test main **không nhất thiết fail** chỉ vì stack trace được in ra. Có hai cách phổ biến:

- Với `Thread` trực tiếp: catch `Throwable` trong worker, lưu vào `AtomicReference<Throwable>` rồi throw `AssertionError` ở main sau khi `join` hoặc `done.await`.
- Với `ExecutorService.submit(Callable/Runnable)`: giữ `Future`, gọi `get(timeout, unit)` để nhận giá trị hoặc exception. Nếu task thất bại, `get` ném `ExecutionException` và có `getCause()`. Nếu quá hạn, `get` ném `TimeoutException`.

**Lưu ý:** `get(timeout)` **không tự cancel** task. Caller phải xác định có nên `future.cancel(true)`, `executor.shutdownNow()` hoặc chờ/cleanup bằng cơ chế khác.

### Java 17+ hoàn chỉnh: timeout và hủy task chờ latch

Tạo file `FutureTimeoutTest.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class FutureTimeoutTest {
    public static void main(String[] args) throws Exception {
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch gate = new CountDownLatch(1);
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            Future<String> result = executor.submit(() -> {
                started.countDown();
                gate.await();
                return "released";
            });

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Task never started");
            }

            boolean timedOut = false;
            try {
                result.get(20, TimeUnit.MILLISECONDS);
            } catch (TimeoutException expected) {
                timedOut = true;
            }

            System.out.println("Timed out: " + timedOut);
            boolean cancelRequested = result.cancel(true);
            System.out.println("Cancellation accepted: "
                    + cancelRequested);
            System.out.println("Future cancelled: "
                    + result.isCancelled());
        } finally {
            gate.countDown();
            executor.shutdownNow();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Executor did not stop");
            }
        }
    }
}
```

Biên dịch/chạy:

```bash
javac FutureTimeoutTest.java
java FutureTimeoutTest
```

Đầu ra trong lần chạy bình thường:

```text
Timed out: true
Cancellation accepted: true
Future cancelled: true
```

Cổng `gate` không mở trước lần `get(20ms)`, nên task không thể trả `released` trước timeout. Sau đó `cancel(true)` gửi yêu cầu hủy và chuyển Future sang trạng thái cancelled. `gate.countDown()` trong `finally` đảm bảo ví dụ không cố giữ worker chờ nếu tình huống thay đổi.

**Không kết luận:** `Future.isCancelled() == true` không chứng minh mã task đã dừng tại **đúng thời điểm đọc cờ** hay mọi side effect được hoàn tác. `awaitTermination()` cho executor một khoảng để kết thúc, còn code task phải hợp tác với interrupt nếu cần hủy nhanh.

### Ví dụ ngắn về exception từ Future

```java
// Snippet trong phương thức có executor và imports thích hợp.
Future<?> failed = executor.submit(() -> {
    throw new IllegalStateException("bad task");
});
try {
    failed.get(1, TimeUnit.SECONDS);
} catch (java.util.concurrent.ExecutionException e) {
    throw new AssertionError("Worker failed", e.getCause());
}
```

Đoạn này chưa là file độc lập. Nếu một task ném `IllegalStateException`, `Future.get` sẽ phản ánh nó bằng `ExecutionException`. Phương thức bao quanh cũng cần xử lý `InterruptedException` và `TimeoutException`; ví dụ chỉ tập trung vào việc **không bỏ qua lỗi worker**.

## 10. Latch, barrier và Phaser bảo đảm visibility gì?

Synchronizer không chỉ chặn/đánh thức; các API trong `java.util.concurrent` có các **memory-consistency effects** giúp tạo quan hệ happens-before.

### CountDownLatch

Các hành động **trước** `countDown()` của một thread happens-before các hành động **sau khi** `await()` tương ứng trở về thành công ở thread khác.

Ví dụ writer:

```java
data = 42;
ready.countDown();
```

Reader:

```java
ready.await();
int snapshot = data;
```

Đây là hai snippet không độc lập; giả sử `data` và `ready` có cùng ownership/giao thức. Khi reader đã chờ latch về 0, các ghi trước `countDown()` được công bố theo hợp đồng. Tuy nhiên, nếu writer **tiếp tục sửa data sau đó**, latch không đóng băng object thành snapshot; cần đồng bộ cho lần cập nhật tiếp theo.

### CyclicBarrier

Các hành động của participant trước `await()` được công bố theo hợp đồng của `CyclicBarrier` đối với barrier action, và từ barrier action tới các hành động sau `await()` thành công của các participant. Dùng barrier giúp tách các **phase công việc**; nhưng nếu một participant thoát trước barrier, phải xử lý broken barrier, không giả vờ dữ liệu đã ở phase mới.

### Phaser

`Phaser` có các bảo đảm về việc hoàn thành phase và những hành động được công bố khi phase advance. Khi dùng `arriveAndAwaitAdvance` hoặc `awaitAdvanceInterruptibly`, hãy bảo đảm participant **đúng phase**; việc gọi đợi với phase đã qua có thể trả về ngay. Không suy rằng một lần `arrive` tương đương chờ các party khác xong.

### Semaphore

Release và acquire của `Semaphore` có các quan hệ memory-consistency phù hợp, nhưng semaphore cũng cần **số permit đúng**. Không dùng `availablePermits()` như một phép quyết định nguyên tử cho việc sử dụng tài nguyên; hãy dùng `acquire`/`tryAcquire` thật.

**Điểm dạy cốt lõi:** chính **giao thức đồng bộ** tạo ra trật tự/visibility, không phải chỉ vì các thread “đợi đủ lâu”. Vì vậy test kiểm tra dữ liệu sau `await/join/get` có cơ sở mạnh hơn test ngủ một lượng thời gian rồi đọc state.

## 11. Thiết kế test để không treo và không làm nhiễm test khác

Một test concurrency nên có **chính sách lỗi và dọn dẹp** rõ ràng:

1. **Timeout cho mọi wait có thể chặn vô hạn:** `latch.await(timeout)`, `barrier.await(timeout)`, `future.get(timeout)`, `executor.awaitTermination(timeout)`, hoặc timed join.
2. **Mở các cổng quan trọng trong `finally`** nếu test thất bại trước khi release. Latch không phải resource được tự dọn; một gate bị quên có thể giữ worker mãi.
3. **Gửi interrupt/cancellation** khi cần, nhưng hiểu rằng đây là yêu cầu hợp tác, không phải kill thread.
4. **Không giữ lock trong khi đợi worker cần chính lock đó.** Một test có thể tự tạo deadlock không liên quan bug mục tiêu.
5. **Không dùng `Thread.sleep` để “đợi đủ lâu”.** Dùng mốc và điều kiện thực.
6. **Gom lỗi worker về test thread.** Đừng chỉ xem log/stack trace rồi cho test pass.
7. **Đặt giới hạn tối đa cho số worker**, đặc biệt khi thử tải; tránh làm cạn CPU/RAM của máy CI.
8. **Khôi phục interrupt status** khi bắt `InterruptedException` và không truyền tiếp, tùy tầng sở hữu lifecycle.
9. **Phân biệt timeout do lỗi thuật toán và timeout do môi trường CI quá tải.** Timeout là failure để điều tra, không phải kết luận ngay nguyên nhân.
10. **Đảm bảo test độc lập:** tạo executor/queue/state mới ở mỗi test, không để static mutable state từ test trước ảnh hưởng test sau.

### Pattern shutdown ExecutorService sau test

```java
// Snippet cho executor do test tạo và sở hữu.
executor.shutdown();
try {
    if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
        executor.shutdownNow();
        if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
            throw new AssertionError("Executor did not terminate");
        }
    }
} catch (InterruptedException e) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
    throw new AssertionError("Test interrupted", e);
}
```

Đây là snippet, `executor` chưa khai báo. Hai lần timeout là **hai giai đoạn chờ riêng**, không phải một deadline tổng 5 giây. Nếu test có deadline tổng, tính `remaining` từ `System.nanoTime()` để không cấp lại toàn bộ ngân sách mỗi lượt.

**Lưu ý:** worker không hợp tác interruption vẫn có thể tồn tại sau khi test báo lỗi. Với các test rủi ro cao (ví dụ deliberately deadlock/loop), nên cô lập test trong một process riêng để harness bên ngoài có thể kill **process** khi quá hạn; không dùng `Thread.stop()`.

## 12. Deterministic test, stress test và kiểm tra Java Memory Model

Không có một bộ synchronizer nào bao phủ **mọi lịch thread**. Cần phối hợp nhiều kỹ thuật:

| Loại test | Ý tưởng | Nên kiểm tra |
| --- | --- | --- |
| **Deterministic scenario** | Latch/barrier tạo ra interleaving đã biết | Một bug cụ thể, invariant tại checkpoint |
| **Repeated concurrency test** | Chạy nhiều lần với số worker và data seed khác nhau | Tính ổn định của invariant trên nhiều lịch |
| **Stress test** | Tăng tranh chấp, tạo nhiều thao tác xen kẽ | Race, lost update, deadlock, tài nguyên bị rò |
| **JMM litmus test** | Tập trung visibility, ordering, atomicity | Các outcome hợp lệ/không hợp lệ theo JMM |
| **Performance benchmark** | Đo throughput/latency với workload đại diện | Hiệu năng, không phải chứng minh absence of data race |

### jcstress và JMH: hai mục tiêu khác nhau

- **jcstress** là công cụ thuộc hệ sinh thái OpenJDK giúp thử nhiều interleaving và outcomes của các phép kiểm tra concurrency/JMM.
- **JMH** phục vụ microbenchmark hiệu năng có kiểm soát. Nó **không phải** công cụ chứng minh thuật toán concurrent luôn đúng.
- Các test phối hợp bằng latch giúp dựng **một số lịch cụ thể**, còn jcstress giúp khảo sát nhiều outcome; chúng bổ trợ nhau.
- Thread Sanitizer/hệ thống phân tích race có thể có mức hỗ trợ/phạm vi khác nhau; không suy rằng không có cảnh báo nghĩa mã an toàn trên mọi JVM.

Nếu bắt buộc chứng minh formal correctness, cần suy luận theo Java Memory Model/happens-before, linearizability hoặc kiểm chứng thuật toán thích hợp; stress test chỉ tăng khả năng phát hiện lỗi, không tạo chứng minh toán học về mọi interleaving.

### Tránh dùng `yield()` như một cơ chế test chắc chắn

`Thread.yield()` là **hint** cho scheduler, không ép thread khác được chạy. `Thread.sleep(1)` cũng không đặt được một thứ tự happens-before mong muốn. Chúng có thể tăng biến thiên lịch trong thử tải, nhưng không nên là assertion hoặc barrier.

## 13. Ví dụ kiểm tra không làm mất dữ liệu bằng BlockingQueue

`BlockingQueue` thường có semantics thread-safe, nhưng test vẫn cần kiểm tra đúng **số item đã gửi và nhận**, tránh dựa vào `queue.isEmpty()` đơn lẻ khi producer còn chạy.

Một pattern tốt:

```text
Producer đưa 100 item và báo done.
Consumer lấy item, ghi nhận ID nhận được.
Main chờ producer done + consumer done.
Main kiểm tra:
  số lượng = 100
  ID không trùng
  mọi ID nằm trong tập kỳ vọng
```

Nếu hệ thống cần đúng-once processing, phải xác định rõ retry, cancellation, failure, ack và thời điểm nào một item được xem “đã xử lý”. `BlockingQueue.take` chỉ bảo đảm lấy phần tử theo hợp đồng queue; nó không tự bảo đảm side effect nghiệp vụ là exactly once.

### Chờ bằng `poll(timeout)`

`queue.poll(timeout, unit)` trả `null` khi không nhận được phần tử trong khoảng chờ. `null` **không phải** bằng chứng producer đã kết thúc vĩnh viễn. Để nhận biết kết thúc stream, dùng một tín hiệu riêng (như latch, completion Future) hoặc một sentinel hợp lệ được đưa vào queue theo giao thức.

Tránh viết `while (!queue.isEmpty())` để quyết định consumer dừng khi producer còn đang hoạt động; khoảng trống tạm thời có thể làm mất cơ hội nhận item tới sau.

## 14. Những lỗi test concurrency phổ biến

1. **“Đã `sleep(100)` thì worker chắc chắn tới dòng mong muốn.”** Sai: scheduling không có cam kết như vậy.
2. **“Tạo nhiều thread là chắc có race.”** Sai: cần kiểm soát contention/interleaving; test một lần pass không chứng minh gì nhiều.
3. **“Một worker ném AssertionError thì test main tự fail.”** Sai: phải chuyển lỗi về main hoặc đọc Future.
4. **“Latch có thể reset cho test round tiếp theo.”** Sai: `CountDownLatch` một lần; dùng `CyclicBarrier` hoặc `Phaser` cho nhiều phase.
5. **“`CountDownLatch.await(timeout)` trả false nghĩa worker đã xong.”** Sai: false báo timeout khi chưa đủ tín hiệu.
6. **“Đặt `done.countDown()` ở cuối try là đủ.”** Không đủ nếu giữa chừng ném lỗi; đặt trong `finally`.
7. **“Barrier một bên hỏng vẫn có thể coi phase đã xong.”** Sai: broken barrier cần làm test fail/cleanup.
8. **“`CyclicBarrier` tự mở khi một thread bỏ cuộc.”** Sai: có thể treo nếu số participant không đủ và không có timeout.
9. **“Phaser.arriveAndAwaitAdvance() là interruptible timed wait.”** Sai: muốn interrupt/timeout, dùng API tương ứng.
10. **“Có permit nghĩa dữ liệu được bảo vệ mọi nơi.”** Sai: chỉ những đường tuân thủ acquire/release mới được giới hạn.
11. **“`availablePermits()` là một quyết định admission atomic.”** Sai: đây là trạng thái quan sát có thể đổi ngay.
12. **“Future.get(timeout) hết hạn thì task đã hủy.”** Sai: timeout chỉ giới hạn chờ caller.
13. **“Cancel(true) chứng minh worker đã dừng và cleanup xong.”** Sai: cần chờ/vòng đời phù hợp.
14. **“Nếu tất cả thread join xong thì shared int++ chắc chắn không mất lượt.”** Sai: join chỉ chờ hoàn tất; phép cập nhật có thể đã race.
15. **“Volatile làm tăng `x++` nguyên tử.”** Sai: volatile chỉ cho semantics của từng truy cập.
16. **“`isEmpty()` của queue sau một thời điểm là đủ xác nhận pipeline xong.”** Sai: producer có thể gửi thêm.
17. **“Dùng thật nhiều delay để giảm flaky test.”** Không bền vững: nên dùng điều kiện/synchronizer thật.
18. **“Stress test pass 1 triệu lượt chứng minh không có data race.”** Sai: không bao quát mọi lịch và mọi JVM/hardware.
19. **“Test phải giả định số CPU luôn bằng số worker.”** Sai: concurrency không đồng nghĩa chạy song song trên mọi core.
20. **“Tạo pool trong test nhưng không shutdown cũng được.”** Có thể để lại thread/tài nguyên, ảnh hưởng những test khác.

## 15. Checklist viết test concurrency đáng tin cậy

1. **Viết rõ invariant**: kết quả nào phải đúng với mọi lịch, kết quả nào chỉ là kỳ vọng của một lịch cụ thể?
2. **Chọn checkpoint có nghĩa** thay cho sleep: ready, start, done, phase, release hoặc future completed.
3. **Kiểm soát số participant**: latch count/barrier parties/phaser registration phải trùng với worker thực tế.
4. **Timeout mọi điểm chờ có nguy cơ treo**; xem đây là tín hiệu test failure cần điều tra.
5. **Chuyển exception từ worker về main** bằng Future hoặc AtomicReference rồi assert.
6. **Đưa countDown/deregister/permit release vào finally** khi đúng hợp đồng sở hữu, tránh thiếu tín hiệu.
7. **Không release semaphore khi chưa acquire**; không double countDown hoặc quên deregister khiến phase sai.
8. **Kiểm tra data invariant sau mốc đồng bộ thích hợp**; tránh đọc state khi writer vẫn đang sửa mà không có giao thức bảo vệ.
9. **Sửa lỗi timing ở kiến trúc test**, không chỉ tăng timeout hoặc thêm sleep.
10. **Đặt cleanup trong finally** và quản lý thread/executor do test tạo; timeout/cancel không phải kill cưỡng chế.
11. **Dựng đường lỗi riêng**: worker ném exception, participant thiếu, barrier broken, interrupt giữa lúc đợi, timeout và quá tải.
12. **Chạy lặp trên nhiều môi trường** nhưng không lấy số lần pass làm bằng chứng hình thức.
13. **Dùng jcstress khi kiểm tra JMM outcome**, JMH khi đo hiệu năng; đừng nhầm mục tiêu.
14. **Không đưa test-only gate làm thay đổi thuật toán production** theo cách che bug; sử dụng hook/injection hợp lý và review tác động.
15. **Ghi rõ test thành công nghĩa gì**: tái hiện lịch cố định, kiểm tra invariant, hay phát hiện race theo xác suất.

## 16. Tham khảo API JDK

- [CountDownLatch — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [CyclicBarrier — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CyclicBarrier.html)
- [Phaser — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Phaser.html)
- [Semaphore — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html)
- [Future — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [java.util.concurrent package — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html)

**Kết luận:** test concurrency tốt cần biến những mốc vô hình của nhiều thread thành **sự kiện có thể quan sát và phối hợp**. `CountDownLatch` dựng ready/start/done, `CyclicBarrier` chia nhiều vòng, `Phaser` quản lý participant thay đổi, `Semaphore` kiểm tra giới hạn truy cập, còn `Future` đưa kết quả/lỗi về main. Synchronizer giúp tái hiện một số interleaving và kiểm chứng invariant với dữ liệu được công bố đúng cách, nhưng không bao quát mọi lịch: cần kết hợp suy luận JMM, kiểm thử lặp/stress và quản lý timeout, interruption, cleanup để bài test vừa hữu ích vừa không gây treo chương trình.