# Chọn Phaser theo cấu trúc phối hợp của bài toán

> **Bài học trong nhóm Phaser — Java 7:** Chọn `java.util.concurrent.Phaser` dựa trên **hình dạng phối hợp công việc**, thay vì mặc định dùng Phaser cho mọi bài toán nhiều luồng. Xác định công việc chỉ phải gặp nhau một lần hay nhiều lần, số bên tham gia cố định hay biến đổi, cần chờ hay chỉ báo arrival, có các nhóm con cùng chung một nhịp không, và hành vi khi một worker lỗi. `Phaser` có từ Java 7 và **vẫn là API hiện hành trong Java 17+**. Mười một chương trình Java 17 độc lập trong bài được biên dịch/chạy thật bằng `javac --release 17`; các ví dụ concurrency được thiết kế để tránh phụ thuộc thứ tự scheduler. Không đưa API đã legacy vào lời khuyên triển khai.

## 1. Vấn đề chính: Chọn cấu trúc đồng bộ trước khi chọn class

Không phải mọi hệ thống có nhiều worker đều cần một barrier. Hãy xét **đường đi của công việc**:

- Hai truy vấn chạy đồng thời, kết quả được ghép **một lần**: một dependency graph/result combination, thường hợp `CompletableFuture` hơn `Phaser`.
- Hai worker cùng một coordinator phải hoàn tất **một đợt**: `CountDownLatch` hoặc `Future` có thể đủ.
- Ba bên chạy **nhiều vòng**, tất cả phải đến trước khi sang vòng tiếp theo và số bên cố định: `CyclicBarrier` rất tự nhiên.
- Nhiều vòng nhưng có workers được thêm/rút giữa các vòng, hoặc coordinator có thể chỉ theo dõi: `Phaser` thể hiện đúng điều kiện.
- Hàng trăm/hàng nghìn parties chia thành **nhóm**, mỗi nhóm phải hoàn thành vòng của mình trước khi toàn hệ thống chuyển vòng: một cây `Phaser` có thể giảm contention, nhưng phức tạp hơn flat Phaser.
- Producer đẩy dữ liệu liên tục cho consumer theo tốc độ riêng: `BlockingQueue`/flow control, không nên buộc mọi message đi qua một Phaser.
- Giới hạn tối đa bao nhiêu requests chạy song song: `Semaphore`, không phải Phaser.
- Một bài toán chia và gộp công việc không có checkpoint cố định giữa các workers: `ForkJoinPool`/`RecursiveTask` thường hợp hơn barrier thủ công.

**Câu hỏi đầu tiên không phải “dùng `Phaser` kiểu nào?” mà là “có thực sự cần các bên chờ một ranh giới phase chung hay không?”**

### 1.1. Bảng quyết định chọn công cụ

| Hình dạng phối hợp | Công cụ nên cân nhắc | Vì sao |
| --- | --- | --- |
| Một lần chờ N tín hiệu hoàn tất | `CountDownLatch` | Đơn giản; count về zero là xong, không reset |
| Một lần chờ kết quả có kiểu từ tác vụ | `Future` hoặc `CompletableFuture` | Truyền kết quả/exception tự nhiên, không cần party counter riêng |
| N parties cố định lặp qua nhiều vòng | `CyclicBarrier` | Barrier lặp lại, cấu hình số bên cố định |
| N parties biến đổi giữa/cùng các phase | **`Phaser`** | `register`, `bulkRegister`, `arriveAndDeregister` |
| Một bên chỉ quan sát phase mà không được chặn phase | **`Phaser.awaitAdvance`** | Observer không cần trở thành registered party |
| Nhiều nhóm con đồng bộ chung checkpoint | **Tiered `Phaser`** | Child phasers và parent, tự phối hợp registration |
| Cần tự quyết định dừng sau K phase | **`Phaser.onAdvance`** | Quy định termination ở ranh giới phase |
| DAG: A, B chạy rồi C dùng kết quả | `CompletableFuture.thenCombine/allOf` | Không cần mọi task gặp cùng một barrier |
| Producer/consumer có backpressure | `BlockingQueue`, mô hình stream thích hợp | Không khóa chặt tiến độ vào một phase toàn cục |
| Chặn mức concurrency | `Semaphore` hoặc giới hạn executor | Không phải bài toán đếm arrivals |
| Chia để chạy song song rồi gộp kết quả | `ForkJoinPool`, `RecursiveTask` | Recursive join thay vì barrier lặp cố định |

Công cụ có thể phối hợp cùng nhau: `ExecutorService` chạy tasks; `Phaser` điều phối ranh giới các vòng; `Future` mang completion/error của mỗi task; `CountDownLatch` dùng riêng cho test startup. Nhưng thêm đồng bộ hóa mà không có dependency thật làm hệ thống khó debug hơn.

### 1.2. Sơ đồ quyết định nhanh

```text
Các tác vụ có cần gặp nhau tại một ranh giới chung?
   |
   +-- KHÔNG --> Dùng Future/CompletableFuture, queue, semaphore...
   |
   +-- CÓ
       |
       +-- Chỉ một lần, đếm hoàn thành? --> CountDownLatch / Future
       |
       +-- Lặp nhiều lần?
           |
           +-- Số bên cố định, cấu trúc phẳng --> CyclicBarrier
           |
           +-- Đăng ký/rút động hoặc observer? --> Phaser phẳng
           |
           +-- Nhiều nhóm có checkpoint chung, contention cao?
                 |
                 +-- Có và đã đo lợi ích --> Phaser phân cấp
                 +-- Không --> Phaser phẳng
```

Đây là **heuristic thiết kế**, không phải phép chứng minh một class sẽ nhanh nhất. Độ phức tạp xử lý lỗi, cancellation và ownership quan trọng không kém hiệu năng.

## 2. “Phase” của Phaser nghĩa là gì?

`Phaser` là một *reusable synchronization barrier*. Nó có các số liệu:
- `getPhase()`: số phase hiện tại (bắt đầu từ 0, âm nếu terminated).
- `getRegisteredParties()`: số **logical parties** đã đăng ký.
- `getUnarrivedParties()`: số parties chưa báo arrival trong phase hiện tại.
- `getArrivedParties()`: số parties đã báo arrival trong phase hiện tại.

Khi tất cả các parties còn có trách nhiệm ở phase đó đã đến, Phaser thực hiện phase advance. Một party là **suất đăng ký**, không phải identity của `Thread`. API không kiểm soát mỗi Thread là một party hay chặn tất cả lỗi “thread này deregister hai lần”.

### 2.1. Từ ngữ chính xác cần nhớ

| API | Tác dụng | Có chờ không? | Có rút khỏi nhóm không? |
| --- | --- | --- | --- |
| `register()` | Thêm một unarrived party | Có thể chờ transition nội bộ | Không |
| `bulkRegister(n)` | Thêm n parties | Có thể chờ transition nội bộ | Không |
| `arrive()` | Ghi nhận arrival ở phase hiện tại | Không chờ các bên khác | Không |
| `arriveAndAwaitAdvance()` | Arrive rồi đợi phase advance | Có | Không |
| `arriveAndDeregister()` | Arrive và rút cho các phase sau | Không chờ các bên khác | **Có** |
| `awaitAdvance(phase)` | Chỉ quan sát/đợi phase đổi | Có, nếu phase chưa đổi | Không |
| `awaitAdvanceInterruptibly(phase,timeout,unit)` | Đợi với interrupt/timeout | Có giới hạn | Không |
| `forceTermination()` | Buộc Phaser terminated, thả waiters | Không chờ các arrivals | **Không giảm registered count** |

`arriveAndDeregister()` là lựa chọn tự nhiên khi một worker **không còn tham gia vòng sau**. Một worker chỉ đến nhưng vẫn phải làm vòng sau nên chọn `arrive()` hoặc `arriveAndAwaitAdvance()` tùy nhu cầu chờ.

### 2.2. Giá trị trả về và termination

Arrival methods trả phase mà arrival được ghi nhận; `awaitAdvance(phase)` đợi **tới khi current phase khác phase đã cho**. `arriveAndAwaitAdvance()` có thể trả một giá trị phase không âm trong lần call vừa làm phase chuyển, kể cả khi `onAdvance` vừa quyết định termination; vì vậy khi cần xác định dừng hãy kiểm tra `isTerminated()` hoặc `getPhase()<0`.

Không suy rằng mọi giá trị âm từ một phương thức là exception: Phaser dùng phase âm để biểu diễn trạng thái terminated. Cũng không suy từ mọi return value không âm rằng vòng sau vẫn hoạt động.

### 2.3. Snapshot không phải điều khiển đồng bộ

`getRegisteredParties/getUnarrivedParties/getArrivedParties` hữu ích cho logging/diagnostics, nhưng trên workload concurrent chúng có thể phản ánh một thời điểm giữa các arrivals. Đừng viết busy-wait `while (phaser.getUnarrivedParties() != 0) {}` và cho rằng nó tương đương một barrier hợp lệ. Hãy dùng arrival/await methods và timeout/cancellation policy.

## 3. Một lần đợi hoàn thành: chọn CountDownLatch trước

Khi chỉ muốn chờ hai công việc kết thúc, không có vòng phase thứ hai và không cần thêm/rút parties trong khi chạy, `CountDownLatch(2)` thường dễ hiểu hơn tạo một Phaser. Mỗi job gọi `countDown()`; coordinator `await()`. Latch về zero thì vẫn zero: **không reset** để chạy vòng hai.

### 3.1. Chương trình 1 — one-shot latch, không tạo Phaser

Lưu `OneShotLatchDemo.java`:

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public class OneShotLatchDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch done = new CountDownLatch(2);
        AtomicInteger processed = new AtomicInteger();
        ExecutorService workers = Executors.newFixedThreadPool(2);
        try {
            Future<?> a = workers.submit(() -> {
                processed.incrementAndGet();
                done.countDown();
            });
            Future<?> b = workers.submit(() -> {
                processed.incrementAndGet();
                done.countDown();
            });
            if (!done.await(2, TimeUnit.SECONDS))
                throw new AssertionError("latch did not reach zero");
            a.get(2, TimeUnit.SECONDS);
            b.get(2, TimeUnit.SECONDS);
            System.out.println("processed=" + processed.get());
            System.out.println("countAfterCompletion=" + done.getCount());
            System.out.println("awaitAgainImmediately=" +
                    done.await(1, TimeUnit.MILLISECONDS));
        } finally {
            workers.shutdownNow();
            if (!workers.awaitTermination(3, TimeUnit.SECONDS))
                throw new AssertionError("worker pool did not terminate");
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 OneShotLatchDemo.java
java OneShotLatchDemo
```

Stdout đã kiểm chứng:

```text
processed=2
countAfterCompletion=0
awaitAgainImmediately=true
```

**Vì sao không phải Phaser?** Coordinator chỉ cần nhận hai tín hiệu một lần. Việc `awaitAgainImmediately=true` cho thấy latch đã về zero sẽ không bắt đầu “phase mới”. Ở code production, nếu task có thể ném exception, nên có `countDown()` trong `finally` nếu contract là “đã kết thúc dù thành công hay thất bại”, đồng thời đọc `Future` để phân biệt lỗi với hoàn tất thành công. Đừng coi latch về zero là mọi kết quả đều đúng.

### 3.2. Khi one-shot vẫn có thể cần Phaser

Nếu số jobs chỉ được biết **khi đang đăng ký**, và coordinator phải giữ cổng chưa mở cho đến khi đã tạo đủ jobs, có thể dùng `Phaser(1)` cho coordinator rồi `register()` từng job, cuối cùng coordinator deregister để mở cổng. Nhưng nếu số jobs đã biết và chỉ cần đếm hoàn tất, latch ít moving parts hơn.

## 4. Barrier lặp với số bên cố định: CyclicBarrier đơn giản hơn

Khi đúng ba bên phải gặp nhau ở cuối mỗi vòng, **không ai rút hoặc thêm**, và muốn lặp nhiều vòng, `CyclicBarrier(3)` thể hiện số participants cố định. Barrier tự reset sau mỗi generation khi tất cả đã await. Nếu participant bị interrupt/timeout, barrier có thể chuyển sang broken state và các bên khác nhận `BrokenBarrierException`.

Phaser cũng có thể thực hiện mô hình này, nhưng đòi hỏi bạn hiểu registered counts/phase state/termination, nên không nhất thiết cần thiết.

### 4.1. Chương trình 2 — fixed-participant barrier

Lưu `FixedCyclicBarrierDemo.java`:

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public class FixedCyclicBarrierDemo {
    public static void main(String[] args) throws Exception {
        CyclicBarrier barrier = new CyclicBarrier(3);
        AtomicInteger workCount = new AtomicInteger();
        ExecutorService workers = Executors.newFixedThreadPool(2);
        try {
            Future<?> a = workers.submit(() -> runTwoRounds(barrier, workCount));
            Future<?> b = workers.submit(() -> runTwoRounds(barrier, workCount));
            for (int round = 0; round < 2; round++) {
                barrier.await(3, TimeUnit.SECONDS);
            }
            a.get(3, TimeUnit.SECONDS);
            b.get(3, TimeUnit.SECONDS);
            System.out.println("barrierParties=" + barrier.getParties());
            System.out.println("workerOperations=" + workCount.get());
            System.out.println("barrierBroken=" + barrier.isBroken());
        } finally {
            barrier.reset();
            workers.shutdownNow();
            if (!workers.awaitTermination(3, TimeUnit.SECONDS))
                throw new AssertionError("worker pool did not terminate");
        }
    }
    static void runTwoRounds(CyclicBarrier barrier, AtomicInteger count) {
        try {
            for (int round = 0; round < 2; round++) {
                count.incrementAndGet();
                barrier.await(3, TimeUnit.SECONDS);
            }
        } catch (Exception ex) {
            throw new RuntimeException(ex);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 FixedCyclicBarrierDemo.java
java FixedCyclicBarrierDemo
```

Stdout đã kiểm chứng:

```text
barrierParties=3
workerOperations=4
barrierBroken=false
```

Hai worker mỗi bên làm hai lượt; main là participant thứ ba và phải gọi `await` hai lần. `barrierParties=3` không đổi vì CyclicBarrier không có `arriveAndDeregister()`. Nếu số workers giảm sau vòng đầu, CyclicBarrier cấu hình 3 sẽ đợi bên đã rời cho tới khi timeout/broken. Khi cần rút động, đó là dấu hiệu để dùng Phaser.

### 4.2. Khác nhau khi có lỗi

`CyclicBarrier` có cơ chế *broken barrier* nếu wait bị ngắt/timeout theo hợp đồng. `Phaser.awaitAdvanceInterruptibly` ném `InterruptedException`/`TimeoutException` nhưng **không tự thay đổi counts hoặc force termination**. Nếu chọn Phaser, phải thiết kế rollback/abort rõ, không mong nó tự “break” giống CyclicBarrier.

## 5. Flat Phaser: nhiều vòng với coordinator là party

Nếu mỗi vòng cần các workers tạo ra một phần trạng thái và coordinator phải chỉ chuyển sang vòng tiếp theo khi toàn bộ workers đã đến, dùng một **Phaser phẳng** là lựa chọn dễ kiểm toán.

```text
              Phaser phase k
       /             |             \
 worker A        worker B       coordinator
    |                |               |
 arriveAndAwait  arriveAndAwait  arriveAndAwait
       \             |            /
        +-- cả 3 đến --> phase k+1
```

- Coordinator đăng ký party của chính mình; nếu quên arrival, mọi workers đợi.
- Mỗi worker sở hữu đúng một registration; khi hoàn tất vòng cuối và sang phase mới có thể deregister.
- Nên tạo `ExecutorService` đủ resources để mọi parties có thể tiến tới barrier; nếu chỉ có 1 worker thread cho 2 tasks cùng chờ, task chưa chạy có thể không bao giờ tới barrier.
- Đăng ký đủ parties **trước** khi submit tasks để tránh root phaser advance sớm.
- Khi worker lỗi mà dữ liệu phase không còn hợp lệ, `forceTermination` là một policy fail-fast.

### 5.1. Chương trình 3 — 2 workers + coordinator, 3 vòng

Lưu `FlatPhaserRoundsDemo.java`:

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public class FlatPhaserRoundsDemo {
    public static void main(String[] args) throws Exception {
        Phaser phaser = new Phaser(1); // Coordinator
        phaser.bulkRegister(2);        // Two worker parties
        AtomicInteger completed = new AtomicInteger();
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<?> first = pool.submit(() -> runThreeRounds(phaser, completed));
            Future<?> second = pool.submit(() -> runThreeRounds(phaser, completed));
            for (int round = 0; round < 3; round++) {
                int next = phaser.arriveAndAwaitAdvance();
                if (next < 0) throw new AssertionError("unexpected termination");
            }
            first.get(3, TimeUnit.SECONDS);
            second.get(3, TimeUnit.SECONDS);
            System.out.println("completedWorkerRounds=" + completed.get());
            System.out.println("phase=" + phaser.getPhase());
            System.out.println("coordinatorOnly=" +
                    (phaser.getRegisteredParties() == 1));
            phaser.arriveAndDeregister();
            System.out.println("terminated=" + phaser.isTerminated());
        } finally {
            phaser.forceTermination();
            pool.shutdownNow();
            if (!pool.awaitTermination(3, TimeUnit.SECONDS))
                throw new AssertionError("worker pool did not terminate");
        }
    }
    static void runThreeRounds(Phaser phaser, AtomicInteger completed) {
        try {
            for (int round = 0; round < 3; round++) {
                completed.incrementAndGet();
                int next = phaser.arriveAndAwaitAdvance();
                if (next < 0) throw new AssertionError("unexpected termination");
            }
            phaser.arriveAndDeregister(); // Phase 3: no more worker rounds
        } catch (RuntimeException | Error failure) {
            phaser.forceTermination(); // Do not double-arrive on a failed phase
            throw failure;
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 FlatPhaserRoundsDemo.java
java FlatPhaserRoundsDemo
```

Stdout đã kiểm chứng:

```text
completedWorkerRounds=6
phase=3
coordinatorOnly=true
terminated=true
```

**Diễn giải:** `Phaser(1)` giữ một suất cho coordinator; `bulkRegister(2)` thêm hai worker parties. Mỗi worker làm 3 vòng và cùng coordinator `arriveAndAwaitAdvance`, tổng có 6 worker operations. Sau phase 3, workers deregister; coordinator còn một mình. Coordinator deregister lần cuối làm Phaser mặc định terminated.

### 5.2. Vì sao exception path không tự deregister?

Trong ví dụ, khi một worker gặp lỗi runtime, nó gọi `forceTermination()` rồi ném lại lỗi. Nó **không** đặt `arriveAndDeregister()` mù quáng trong finally, vì worker có thể đã gọi `arrive()` ở phase hiện tại; deregister lần nữa có thể tạo **double arrival**, làm barrier tiến sai. Trong workflow có output bắt buộc từ mọi worker, abort cả nhóm đáng tin hơn giả vờ worker lỗi đã hoàn tất.

### 5.3. Cần một coordinator là party hay chỉ observer?

Nếu coordinator phải **cho phép** phase mới bắt đầu sau khi nó xử lý/checkpoint, nó cần là party. Nếu coordinator chỉ ghi log khi workers hoàn tất mà **không được làm chậm** phase, không đăng ký coordinator; dùng `awaitAdvance(phase)` như một observer (xem chương trình 5). Đây là quyết định về dependency, không phải tối ưu hiệu năng nhỏ.

## 6. Dynamic Phaser: workers tham gia/rút trong suốt vòng đời

Đây là tình huống mà `Phaser` có lợi thế rõ nhất so với CyclicBarrier: số registered parties có thể thay đổi.

Một worker làm hai rounds, một worker làm bốn rounds. Nếu cố dùng `CyclicBarrier(3)` suốt bốn rounds, sau khi worker ngắn rời thì coordinator và worker dài chờ một bên không bao giờ tới. Với Phaser, worker ngắn gọi `arriveAndDeregister()` trong phase cuối cùng nó tham gia.

```text
Phase 0: coordinator + worker-ngắn + worker-dài  (3 parties)
Phase 1: coordinator + worker-ngắn + worker-dài  (3 parties)
          worker-ngắn deregister ở phase 1
Phase 2: coordinator + worker-dài                 (2 parties)
Phase 3: coordinator + worker-dài                 (2 parties)
Phase 4: worker-dài deregister; coordinator rút   (termination)
```

Điểm khó là quản lý **party identity và phase state**: Phaser giữ counts, không lưu danh sách Thread IDs đã register. Một logical party không được arrive/deregister hai lần trong cùng phase.

### 6.1. Chương trình 4 — workers có số vòng khác nhau

Lưu `DynamicPartyCountDemo.java`:

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public class DynamicPartyCountDemo {
    public static void main(String[] args) throws Exception {
        Phaser p = new Phaser(1); // Coordinator
        p.bulkRegister(2);
        AtomicInteger early = new AtomicInteger();
        AtomicInteger longRunning = new AtomicInteger();
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<?> shortWorker = pool.submit(() -> {
                try {
                    for (int round = 0; round < 2; round++) {
                        early.incrementAndGet();
                        if (round == 1) {
                            p.arriveAndDeregister(); // Leave after second round
                        } else {
                            int next = p.arriveAndAwaitAdvance();
                            if (next < 0) throw new AssertionError("terminated");
                        }
                    }
                } catch (RuntimeException | Error failure) {
                    p.forceTermination();
                    throw failure;
                }
            });
            Future<?> longWorker = pool.submit(() -> {
                try {
                    for (int round = 0; round < 4; round++) {
                        longRunning.incrementAndGet();
                        int next = p.arriveAndAwaitAdvance();
                        if (next < 0) throw new AssertionError("terminated");
                    }
                    p.arriveAndDeregister(); // At phase 4
                } catch (RuntimeException | Error failure) {
                    p.forceTermination();
                    throw failure;
                }
            });
            for (int round = 0; round < 4; round++) {
                if (p.arriveAndAwaitAdvance() < 0)
                    throw new AssertionError("terminated unexpectedly");
            }
            shortWorker.get(3, TimeUnit.SECONDS);
            longWorker.get(3, TimeUnit.SECONDS);
            System.out.println("shortRounds=" + early.get());
            System.out.println("longRounds=" + longRunning.get());
            System.out.println("finalPhase=" + p.getPhase());
            System.out.println("registeredBeforeCoordinatorLeaves=" +
                    p.getRegisteredParties());
            p.arriveAndDeregister();
            System.out.println("terminated=" + p.isTerminated());
        } finally {
            p.forceTermination();
            pool.shutdownNow();
            if (!pool.awaitTermination(3, TimeUnit.SECONDS))
                throw new AssertionError("worker pool did not terminate");
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 DynamicPartyCountDemo.java
java DynamicPartyCountDemo
```

Stdout đã kiểm chứng:

```text
shortRounds=2
longRounds=4
finalPhase=4
registeredBeforeCoordinatorLeaves=1
terminated=true
```

Sau vòng thứ hai, worker ngắn rút **trong phase mà nó hoàn thành công việc**, nên các phase sau không chờ worker này. Worker dài tiến qua đủ bốn phases. Khi cả hai worker deregister, còn coordinator có một suất; coordinator rút cuối, Phaser terminated.

### 6.2. Mở rộng thành thêm workers giữa các phases

`register()` thêm một unarrived party ở **phase mà registration áp dụng**, không nhất thiết đúng thời điểm ứng dụng muốn worker bắt đầu. Nếu cho phép thêm task vào giữa phase:
- Coordinator cần lock/ownership protocol rõ để không register muộn sau khi phase đã advance.
- Worker mới không nên dùng phase number cũ rồi chờ/arrive như thể đã có mặt từ đầu.
- Nếu nhiệm vụ mới chỉ thuộc phase **kế tiếp**, tốt nhất lập kế hoạch đăng ký ở ranh giới phase có quản lý rõ ràng.
- `bulkRegister(n)` có lợi khi biết cả nhóm sẽ cùng tham gia; giảm số lệnh register nhưng không tự giải quyết race với phase advance.
- Với task submission thất bại, caller cần xử lý suất đã register; một task không bao giờ được chạy không tự deregister.

## 7. Observer không bắt buộc làm party

Một use case thường gặp: trang quản trị hiển thị phase hiện tại, hoặc một coordinator chỉ muốn biết giai đoạn được hoàn tất **sau khi workers tự phối hợp**.

Nếu observer được register nhầm thành party nhưng **không bao giờ gọi arrive**, toàn bộ barrier bị chặn. Đây là lỗi thiết kế phổ biến. `Phaser.awaitAdvance(phase)` cho phép một thread bất kỳ **quan sát** phase chuyển, không cần party registration và không làm một arrival.

```text
Worker A ---- arrive()
                        \
                         phase 0 -> 1 ----> Observer được đánh thức
                        /
Worker B ---- arrive()

Observer: awaitAdvance(0)   [không tính vào 2 parties]
```

### 7.1. Chương trình 5 — observer không giữ barrier

Lưu `ObserverPhaseDemo.java`:

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public class ObserverPhaseDemo {
    public static void main(String[] args) throws Exception {
        Phaser p = new Phaser(2); // Two logical worker parties
        CountDownLatch observerReady = new CountDownLatch(1);
        AtomicInteger observed = new AtomicInteger(Integer.MIN_VALUE);
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            Future<?> observer = pool.submit(() -> {
                observerReady.countDown();
                observed.set(p.awaitAdvance(0)); // Observer is not a party.
            });
            if (!observerReady.await(2, TimeUnit.SECONDS))
                throw new AssertionError("observer not ready");
            p.arrive(); // Logical first worker in phase 0
            p.arrive(); // Logical second worker in phase 0
            observer.get(2, TimeUnit.SECONDS);
            System.out.println("observedPhase=" + observed.get());
            System.out.println("registeredAfterObservation=" +
                    p.getRegisteredParties());
            p.arriveAndDeregister(); // First logical worker leaves in phase 1
            p.arriveAndDeregister(); // Second leaves in phase 1
            System.out.println("terminated=" + p.isTerminated());
        } finally {
            p.forceTermination();
            pool.shutdownNow();
            if (!pool.awaitTermination(3, TimeUnit.SECONDS))
                throw new AssertionError("worker pool did not terminate");
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 ObserverPhaseDemo.java
java ObserverPhaseDemo
```

Stdout đã kiểm chứng:

```text
observedPhase=1
registeredAfterObservation=2
terminated=true
```

Hai logical worker parties được main đại diện bằng hai `arrive()` trong phase 0. Observer đợi phase 0 đổi rồi thức dậy, trong khi `registeredAfterObservation` vẫn bằng 2. Đến phase 1, main đại diện cho hai parties deregister; Phaser terminated.

### 7.2. Nếu observer đến sau khi phase đã đổi?

`awaitAdvance(phase)` **trả ngay** nếu current phase đã khác argument. Nếu observer đọc một phase rồi ngừng xử lý quá lâu, nhiều phases có thể đã đi qua trước khi observer gọi await. Không coi một lần `awaitAdvance` là hàng đợi mọi sự kiện phase. Nếu cần consume **từng sự kiện** với không mất message, nên dùng event queue hoặc kết quả có sequence numbers, không dựa vào phase integer như event log.

### 7.3. Observer muốn timeout

Dùng `awaitAdvanceInterruptibly(phase,timeout,unit)`. Nếu chờ hết giờ, nó ném `TimeoutException`; **Phaser không tự đổi state** và observer không trở thành party. Nếu observer có trách nhiệm quản lý vòng đời cả nhóm, nó có thể chủ động `forceTermination` theo SLA; nếu chỉ là dashboard, timeout quan sát không nên tự đóng pipeline của người khác.

## 8. Khi nào Phaser phẳng không đủ tốt?

Một flat Phaser rất dễ dùng: mọi party cùng đăng ký một instance. Với số parties lớn và **phase bodies rất nhỏ**, nhiều threads cùng cập nhật một bộ đếm/phase state có thể gây contention. Tiered Phaser cho phép chia các workers thành nhóm con; mỗi child tính toán local arrivals, rồi parent đại diện checkpoint toàn cục.

**Chọn tiered khi cấu trúc tự nhiên thật sự có nhóm hoặc profiling cho thấy flat contention đáng kể.** Không mặc định tạo cây 3 tầng chỉ vì API hỗ trợ. Phân cấp có overhead phức tạp hơn, khó debug hơn, và không phải luôn nhanh hơn.

### 8.1. Cây Phaser ví dụ

```text
                          root Phaser
                     /         |         \
                coordinator  child-East  child-West
                    (1)         (1)         (1)
                                 / \         / \
                             East1 East2 West1 West2
                             (2 local)   (2 local)

root parties = 3, không phải 5
child-East parties = 2
child-West parties = 2
```

Child khi có registered parties >0 sẽ tự đăng ký **một party** với parent; khi child rút hết về 0, nó tự deregister khỏi parent. Không gọi `root.arriveAndDeregister()` “thay” child bằng tay nếu không sở hữu chính party đó.

### 8.2. Chương trình 6 — hai nhóm con phải đồng bộ trên root

Lưu `TieredTeamPhaserDemo.java`:

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public class TieredTeamPhaserDemo {
    static void teamWorker(Phaser team, AtomicInteger work) {
        try {
            for (int round = 0; round < 2; round++) {
                work.incrementAndGet();
                int next = team.arriveAndAwaitAdvance();
                if (next < 0) throw new AssertionError("unexpected termination");
            }
            team.arriveAndDeregister(); // Worker leaves at new phase
        } catch (RuntimeException | Error failure) {
            team.forceTermination();
            throw failure;
        }
    }
    public static void main(String[] args) throws Exception {
        Phaser root = new Phaser(1); // Coordinator party
        Phaser east = new Phaser(root, 2);
        Phaser west = new Phaser(root, 2);
        AtomicInteger completed = new AtomicInteger();
        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            System.out.println("rootPartiesInitially=" + root.getRegisteredParties());
            Future<?> e1 = pool.submit(() -> teamWorker(east, completed));
            Future<?> e2 = pool.submit(() -> teamWorker(east, completed));
            Future<?> w1 = pool.submit(() -> teamWorker(west, completed));
            Future<?> w2 = pool.submit(() -> teamWorker(west, completed));
            for (int round = 0; round < 2; round++) {
                int next = root.arriveAndAwaitAdvance();
                if (next < 0) throw new AssertionError("unexpected termination");
            }
            for (Future<?> f : new Future<?>[]{e1,e2,w1,w2})
                f.get(3, TimeUnit.SECONDS);
            System.out.println("workerOperations=" + completed.get());
            System.out.println("rootPhase=" + root.getPhase());
            System.out.println("eastParties=" + east.getRegisteredParties());
            System.out.println("westParties=" + west.getRegisteredParties());
            System.out.println("rootPartiesAfterTeamsLeave=" +
                    root.getRegisteredParties());
            root.arriveAndDeregister();
            System.out.println("rootTerminated=" + root.isTerminated());
        } finally {
            root.forceTermination();
            pool.shutdownNow();
            if (!pool.awaitTermination(3, TimeUnit.SECONDS))
                throw new AssertionError("worker pool did not terminate");
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 TieredTeamPhaserDemo.java
java TieredTeamPhaserDemo
```

Stdout đã kiểm chứng:

```text
rootPartiesInitially=3
workerOperations=8
rootPhase=2
eastParties=0
westParties=0
rootPartiesAfterTeamsLeave=1
rootTerminated=true
```

Mỗi nhóm có 2 workers × 2 rounds = 4 operations, nên tổng 8. Root có **3 parties** ban đầu: coordinator + đại diện East + đại diện West. Khi East/West workers đều rút sau vòng cuối, hai children tự dereg khỏi root; root còn một coordinator, và coordinator dereg cuối cùng. Không có “root 5 parties” cho bốn worker vì hai children gộp trạng thái tới parent.

### 8.3. Những điều cần biết về tiering

- `new Phaser(parent,n)` với n>0 tạo một child đã registered; parent tự nhận một party từ child.
- Child n=0 có thể chưa đăng ký ở parent cho đến khi có child party đầu tiên.
- Khi child về zero do `arriveAndDeregister`, parent tự giảm suất child.
- `getParent()` và `getRoot()` giúp xác định cấu trúc.
- `onAdvance` trong tree được gọi tại **root**, không phải mỗi child trên mọi phase.
- `forceTermination` ở một phần của tree có thể làm toàn bộ các related phasers terminated.
- Đừng dùng hai layers của Phaser nếu hai nhóm có các phases **độc lập**: một parent chung vô tình tạo rào cản chéo giữa các nhóm.
- Nếu worker rút hết trong một child, đừng tự dereg parent hộ child thêm lần.
- Với hàng ngàn tasks nhỏ/phase, có thể benchmark tiering theo groups và iteration rate; nhưng vẫn cần quản lý thread pool và không tạo một OS thread cho mọi logical party.

### 8.4. Khi nào tách ra hai Phaser độc lập?

Nếu nhóm A cập nhật mỗi 100 ms, nhóm B mỗi 5 giây, không có yêu cầu checkpoint chung, **không nên ép chúng lên một root**. Dùng hai Phaser độc lập hoặc mô hình events/queues để không làm nhóm nhanh chờ nhóm chậm. Tree chỉ phù hợp nếu sự phụ thuộc giữa nhóm là thật.

## 9. Có yêu cầu kết thúc sau số phase cố định? Dùng onAdvance

Một use case quan trọng là *simulation* hoặc *iterative computation* chạy chính xác K vòng. `Phaser` cho phép override `protected boolean onAdvance(int phase,int registeredParties)`, trả true để kết thúc khi chuẩn bị sang phase sau. Khác với callback lặp ở mỗi worker, đây là một action duy nhất khi tất cả parties đến.

```java
Phaser p = new Phaser(3) {
    @Override protected boolean onAdvance(int phase, int registeredParties) {
        return phase >= 4 || registeredParties == 0; // terminate after 5 phases
    }
};
```

Đây là snippet có thể nằm trong method Java phù hợp; `phase` bắt đầu từ 0. Khi phase 4 hoàn tất thì `onAdvance(4,...)` trả true. Không gọi `register`/`arrive`/`await` của **cùng** Phaser từ `onAdvance`: Javadoc nói behavior không xác định. Giữ callback ngắn, không chặn mạng/database hoặc sleep, vì thread làm arrival cuối cùng thực thi callback này.

### 9.1. Chương trình 7 — kết thúc sau đúng hai phase

Lưu `OnAdvancePolicyDemo.java`:

```java
import java.util.concurrent.Phaser;

public class OnAdvancePolicyDemo {
    public static void main(String[] args) {
        Phaser p = new Phaser(3) {
            @Override protected boolean onAdvance(int phase, int parties) {
                return phase >= 1 || parties == 0; // Two completed phases
            }
        };
        p.arrive();  // Logical A
        p.arrive();  // Logical B
        int afterFirst = p.arriveAndAwaitAdvance(); // Logical C
        System.out.println("afterFirstPhase=" + afterFirst);
        System.out.println("terminatedAfterFirst=" + p.isTerminated());
        p.arrive();
        p.arrive();
        int afterSecond = p.arriveAndAwaitAdvance();
        System.out.println("secondReturnArrivalPhase=" + afterSecond);
        System.out.println("terminatedAfterSecond=" + p.isTerminated());
        System.out.println("currentPhaseNegative=" + (p.getPhase() < 0));
        System.out.println("registeredNotAutoDeregistered=" +
                p.getRegisteredParties());
    }
}
```

```bash
javac -encoding UTF-8 --release 17 OnAdvancePolicyDemo.java
java OnAdvancePolicyDemo
```

Stdout đã kiểm chứng trên JDK 17:

```text
afterFirstPhase=1
terminatedAfterFirst=false
secondReturnArrivalPhase=2
terminatedAfterSecond=true
currentPhaseNegative=true
registeredNotAutoDeregistered=3
```

Ở lần advance thứ hai, `onAdvance(1,3)` quyết định termination. Trong chính thử nghiệm này, lời gọi cuối `arriveAndAwaitAdvance()` trả `2` nhưng `isTerminated()==true` và `getPhase()<0` ngay sau đó. Không dựa duy nhất vào việc return value âm hay không để kết luận phase tiếp theo còn chạy; phải kiểm tra chính sách termination. Đây là **quan sát được kiểm thử**, phù hợp việc caller cuối có thể hoàn tất transition; các waiting callers khác có thể trả giá trị biểu thị termination.

Khi terminate bằng `onAdvance` mà không deregister, `registeredParties` vẫn 3 trong ví dụ. **Termination không phải tự động deregister mỗi logical party**, và count không phải dấu hiệu còn ba threads sống.

### 9.2. Nếu muốn tái sử dụng Phaser khi parties về 0

`new Phaser(0)` lúc mới tạo là active và có thể register. Nhưng Phaser mặc định đã có parties rồi **rút hết** thì `onAdvance` mặc định terminate. Nếu chủ đích cho phép “đợt này rút hết, đợt sau register lại”, có thể override `onAdvance` trả false và tự quản lý shutdown bằng `forceTermination()`. Đừng đặt policy đó nếu một phase rỗng sẽ làm ứng dụng treo vì không còn owner.

## 10. Lỗi worker: có thể cần forceTermination thay vì giảm party count

Khi worker bị lỗi ở một phase yêu cầu **đủ kết quả của tất cả workers**, việc coi worker đó đã “hoàn tất” bằng cách deregister có thể cho phép các parties khác qua barrier với dữ liệu sai. **Fatal failure** thường nên làm cả nhóm abort.

`Phaser.forceTermination()`:
- Chuyển Phaser sang trạng thái terminated;
- Giải phóng những waiters hiện tại;
- Không tự giảm số registered parties;
- Với tiered group, termination có thể lan tới toàn bộ cấu trúc;
- Không tự lưu `Throwable` hay làm mọi tasks đang chạy dừng CPU/I/O; application phải cancel/cleanup riêng.

Trong thiết kế fail-fast, mỗi worker khi phát hiện fatal failure gửi cause vào `Future`/error channel, gọi `forceTermination()`, và coordinator/worker còn lại khi thấy terminated phải dừng một cách có kiểm soát.

### 10.1. Chương trình 8 — coordinator không chờ vô hạn khi worker lỗi

Lưu `AbortOnFailureDemo.java`:

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicReference;

public class AbortOnFailureDemo {
    public static void main(String[] args) throws Exception {
        Phaser phaser = new Phaser(2);
        AtomicReference<Throwable> failure = new AtomicReference<>();
        Thread worker = new Thread(() -> {
            try {
                throw new IllegalStateException("test computation failed");
            } catch (RuntimeException cause) {
                failure.set(cause);
                phaser.forceTermination();
            }
        }, "bad-worker");
        worker.start();
        int result = phaser.arriveAndAwaitAdvance(); // Coordinator
        worker.join(2_000);
        if (worker.isAlive()) throw new AssertionError("worker stuck");
        System.out.println("observedFailure=" + (failure.get() != null));
        System.out.println("awaitReturnNegative=" + (result < 0));
        System.out.println("terminated=" + phaser.isTerminated());
        System.out.println("registeredStillTwo=" +
                (phaser.getRegisteredParties() == 2));
    }
}
```

```bash
javac -encoding UTF-8 --release 17 AbortOnFailureDemo.java
java AbortOnFailureDemo
```

Stdout đã kiểm chứng:

```text
observedFailure=true
awaitReturnNegative=true
terminated=true
registeredStillTwo=true
```

Worker gặp lỗi và ép termination, khiến coordinator thức dậy với phase âm. `registeredStillTwo=true` không có nghĩa cả hai workers còn sống: `forceTermination()` không giảm registrations. Muốn biết tasks đã kết thúc thật sự, phải kết hợp `Future.get()/Thread.join`, executor lifecycle và cleanup.

### 10.2. Vì sao không để mọi catch đều gọi arriveAndDeregister?

Nếu worker đã `arrive()` trước khi bị interrupt/time out trong lúc đợi, gọi tiếp `arriveAndDeregister()` **ở cùng phase** có thể được tính như arrival của một logical party khác. Phaser không lưu Thread IDs để ngăn double arrival. Khi không thể quyết định trạng thái một party an toàn, fail-fast `forceTermination()` tốt hơn việc âm thầm phá barrier. Với kết thúc sớm **bình thường**, `arriveAndDeregister()` vẫn đúng.

## 11. Timeout và interruption: không tự thay đổi số parties

`awaitAdvanceInterruptibly(phase, timeout, TimeUnit)` dành cho thread muốn có deadline, nhưng khi nó ném `TimeoutException`:
- Việc chờ hết hạn, **không đồng nghĩa** Phaser đã phase advance;
- Không tự deregister party;
- Không tự forceTerminate;
- Nếu caller trước đó đã gọi `arrive()`, nó đã báo một arrival nhưng vẫn registered;
- Phải có state machine/owner quyết định chờ tiếp, abort cả nhóm hoặc tiếp tục sau phase advance.

Đây là khác biệt quan trọng với `CyclicBarrier` có broken barrier semantics.

### 11.1. Chương trình 9 — timeout không tự rút registration

Lưu `TimedObservationDemo.java`:

```java
import java.util.concurrent.*;

public class TimedObservationDemo {
    public static void main(String[] args) throws Exception {
        Phaser p = new Phaser(2);
        int phase = p.arrive(); // Logical A has arrived at phase 0
        boolean timedOut = false;
        try {
            p.awaitAdvanceInterruptibly(phase, 50, TimeUnit.MILLISECONDS);
        } catch (TimeoutException expected) {
            timedOut = true;
        }
        System.out.println("timedOut=" + timedOut);
        System.out.println("registeredAfterTimeout=" + p.getRegisteredParties());
        System.out.println("unarrivedAfterTimeout=" + p.getUnarrivedParties());
        p.arriveAndDeregister(); // B withdraws in phase 0
        System.out.println("phaseAfterBLeaves=" + p.getPhase());
        p.arriveAndDeregister(); // A withdraws in phase 1, not twice in phase 0
        System.out.println("terminated=" + p.isTerminated());
    }
}
```

```bash
javac -encoding UTF-8 --release 17 TimedObservationDemo.java
java TimedObservationDemo
```

Stdout đã kiểm chứng:

```text
timedOut=true
registeredAfterTimeout=2
unarrivedAfterTimeout=1
phaseAfterBLeaves=1
terminated=true
```

Ở phase 0, party A đã arrive, party B chưa đến. Timeout observer không làm count từ 2 xuống 1; party B phải thực sự arrive hoặc deregister. Khi B rút, phase chuyển sang 1; A có thể rút ở phase 1, **không phải arrival thứ hai cho phase 0**.

### 11.2. Anti-pattern rất nguy hiểm

```java
int phase = phaser.arrive();
try {
    phaser.awaitAdvanceInterruptibly(phase, 100, TimeUnit.MILLISECONDS);
} catch (TimeoutException timeout) {
    phaser.arriveAndDeregister(); // SAI: có thể double-arrive ở phase đó
}
```

Đây là **mẫu sai minh họa**, không chạy riêng. Khi cần abort vì timeout, coordinator quản lý `forceTermination()` và cleanup, không gọi dereg tự phát sau khi đã arrive. `Phaser` không bảo đảm phát hiện đúng mọi trường hợp “unregistered party arrival” ngay tại lời gọi gây lỗi.

## 12. Registration timing: thứ tự đăng ký là một phần cấu trúc phối hợp

Giả sử main tạo `Phaser(1)`, cho coordinator `arrive()`, và **sau đó** mới register worker. Phase 0 đã có thể tiến tới phase 1, nên worker vào quá muộn không tham gia checkpoint phase 0. Điều này thường là bug nếu mục tiêu là “đợi tất cả workers từ vòng đầu”.

### 12.1. Chương trình 10 — đăng ký muộn áp dụng ở phase sau

Lưu `RegistrationOrderingDemo.java`:

```java
import java.util.concurrent.Phaser;

public class RegistrationOrderingDemo {
    public static void main(String[] args) {
        Phaser p = new Phaser(1); // Coordinator alone for now
        int phaseAfterCoordinatorArrives = p.arrive(); // Advances to phase 1
        System.out.println("initialArrivalPhase=" + phaseAfterCoordinatorArrives);
        System.out.println("phaseBeforeLateRegister=" + p.getPhase());
        int registeredIn = p.register();
        System.out.println("lateRegisteredInPhase=" + registeredIn);
        System.out.println("partiesAfterLateRegister=" +
                p.getRegisteredParties());
        p.arriveAndDeregister(); // Logical late worker
        p.arriveAndDeregister(); // Coordinator
        System.out.println("terminated=" + p.isTerminated());
    }
}
```

```bash
javac -encoding UTF-8 --release 17 RegistrationOrderingDemo.java
java RegistrationOrderingDemo
```

Stdout đã kiểm chứng:

```text
initialArrivalPhase=0
phaseBeforeLateRegister=1
lateRegisteredInPhase=1
partiesAfterLateRegister=2
terminated=true
```

Coordinator đã hoàn tất phase 0 một mình. Worker register sau đó mới được tính ở phase 1. **Phaser không “quay ngược” phase** để thêm worker cho một checkpoint đã qua.

### 12.2. Quy tắc thực tế cho submit tasks

Một pattern an toàn với N tasks đã biết:
1. Coordinator đăng ký party của mình (nếu cần tham gia barrier).
2. Đăng ký N worker parties **trước khi** bất kỳ phase nào được coordinator cho tiến.
3. Submit tasks vào executor phù hợp.
4. Task được chấp nhận phải nắm đúng một party; nếu `execute/submit` bị từ chối, caller vẫn sở hữu suất đó và phải giải quyết registration.
5. Worker báo arrival/deregister **tương ứng phase hiện tại**, không gọi hai lần.
6. Nếu worker bị cancel trước khi chạy, đừng giả định `Future.cancel` tự deregister; caller cần xử lý ownership của registration và có thể abort toàn workflow.
7. Fatal errors phải chuyển thành failure result/termination, không được im lặng.
8. Nếu nhiệm vụ cần tham gia **chỉ từ phase kế tiếp**, thiết kế một registration checkpoint riêng, không tự do register muộn khi nhiều threads đang advance.

### 12.3. `new Phaser(0)` khác Phaser terminated với 0 parties

`new Phaser()` hoặc `new Phaser(0)` ban đầu có phase 0 và chưa terminated, nên `register` sau đó hợp lệ. Ngược lại, một Phaser mặc định đã có parties, rồi party cuối gọi `arriveAndDeregister` khiến số parties về 0, thì `onAdvance` mặc định cho **terminated**. `register` sau termination trả phase âm, không thể tự khởi động lại. Nếu cần tái sử dụng zero-party phaser, override `onAdvance` hoặc tạo instance mới theo vòng đời ứng dụng.

## 13. Task dependency graph: chọn CompletableFuture nếu không có barrier thật

Một pipeline một lần gồm hai computation song song rồi kết hợp thành kết quả thứ ba là **đồ thị phụ thuộc**, không phải ba parties phải đồng bộ lặp theo phase.

`CompletableFuture.thenCombine` thể hiện phụ thuộc rất rõ: C chỉ tính khi A và B đều hoàn thành. Có thể truyền result/exception qua completion stages mà không cần người lập trình tự quản registered/unarrived counters.

### 13.1. Chương trình 11 — phối hợp kết quả không dùng Phaser

Lưu `CompletableFutureGraphDemo.java`:

```java
import java.util.concurrent.*;

public class CompletableFutureGraphDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            CompletableFuture<Integer> a =
                    CompletableFuture.supplyAsync(() -> 20, pool);
            CompletableFuture<Integer> b =
                    CompletableFuture.supplyAsync(() -> 22, pool);
            CompletableFuture<Integer> result =
                    a.thenCombine(b, Integer::sum);
            System.out.println("combined=" + result.get(2, TimeUnit.SECONDS));
            System.out.println("phaserRequired=false");
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(3, TimeUnit.SECONDS))
                throw new AssertionError("worker pool did not terminate");
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 CompletableFutureGraphDemo.java
java CompletableFutureGraphDemo
```

Stdout đã kiểm chứng:

```text
combined=42
phaserRequired=false
```

Các stages truyền kết quả kiểu `Integer` một lần và không phải tham gia checkpoint lặp. Một Phaser sẽ thêm complexity (register, arrive, await, deregister) mà không làm dependency dễ hiểu hơn. Khi thêm lỗi hoặc timeout, dùng APIs của CompletableFuture với error handling/result paths thay vì biến count thành điều kiện hoàn tất giả tạo.

## 14. Phân loại cấu trúc bài toán chi tiết hơn

### 14.1. Kết thúc một batch một lần

**Dấu hiệu:** Không có vòng hai; cần chờ hoàn tất N tasks. Ưu tiên `CountDownLatch` hoặc `Future`. Nếu N thay đổi trước khi bắt đầu và cần “cổng khởi động”, Phaser có thể hữu ích, nhưng không phải mặc định.

### 14.2. Vòng lặp đồng bộ có số worker cố định

**Dấu hiệu:** Một simulation 8 workers, mỗi vòng phải tính đủ state rồi sang vòng sau, tất cả luôn tham gia. `CyclicBarrier(8)` thể hiện tốt. Phaser chỉ đáng dùng nếu cần phase numbers, observer độc lập hoặc onAdvance/termination logic phong phú.

### 14.3. Vòng lặp có workers rời/đến

**Dấu hiệu:** Một worker hết việc ở vòng 3, nhóm còn lại tới vòng 10; đôi khi thêm workers từ batch mới. Dùng Phaser với `arriveAndDeregister/register`. Coordinator phải bảo đảm registration áp dụng đúng phase; party identity do ứng dụng quản lý.

### 14.4. Coordinator là một participant bắt buộc

**Dấu hiệu:** Coordinator kiểm tra dữ liệu/kết quả phase rồi mới đồng ý sang vòng sau. Đăng ký coordinator như party. Nó phải call arrive ở **mọi** phase còn tham gia, và deregister lúc không còn làm checkpoint.

### 14.5. Coordinator chỉ quan sát hoặc báo cáo

**Dấu hiệu:** UI/monitor chỉ cần nhận thay đổi phase, không được giữ workers. Dùng `getPhase`/`awaitAdvance` **không đăng ký party**. Nếu cần không bỏ sót sự kiện, dùng event queue/sequence IDs, không chỉ phase observer.

### 14.6. Nhiều nhóm có global checkpoint

**Dấu hiệu:** Mỗi nhóm con có các workers độc lập, toàn hệ thống chỉ tiến khi tất cả nhóm hoàn thành. Dùng tiered Phaser có root và children. Nếu không có global dependency, giữ nhóm độc lập.

### 14.7. Không có điểm đồng bộ toàn nhóm

**Dấu hiệu:** Streaming, pipeline liên tục, task graph không đều, asynchronous completion. Không ép Phaser vì khi thêm một slow participant, nó có thể chặn toàn bộ. Chọn queues/stages/futures, giới hạn buffer/backpressure, propagating errors theo luồng dữ liệu.

## 15. Một Phaser cho tất cả hay nhiều Phaser?

Một root Phaser cho mọi workers tạo một điểm đồng bộ toàn hệ thống. Điều này tốt khi thật sự muốn **global invariant** (chẳng hạn mọi component đã ghi xong snapshot K trước khi đọc snapshot K+1). Nhưng nếu nhóm A chỉ cập nhật UI còn nhóm B tính aggregation, ép chúng chung phase làm chúng phụ thuộc nhau không cần thiết.

Cách chọn:
- **Một Phaser phẳng:** số parties vừa phải, một ranh giới phase chung, đơn giản nhất.
- **Một Phaser phân cấp:** một ranh giới phase chung nhưng many parties và/hoặc cấu trúc đội nhóm tự nhiên, đã đo contention đủ để giải thích tiering.
- **Nhiều Phaser độc lập:** nhiều ranh giới phase không phụ thuộc.
- **Không Phaser:** công việc không có ranh giới vòng, dùng futures/queues.

### 15.1. Nếu một child bị lỗi

Trong tiered tree, `forceTermination` ở child có thể chấm dứt cấu trúc liên quan; các nhóm khác không thể tiếp tục như không có lỗi nếu business invariant yêu cầu global checkpoint. Nếu mỗi nhóm phải được phép tự phục hồi, cân nhắc không nối chúng vào cùng root hoặc thiết kế error isolation ở tầng ứng dụng. Không sử dụng tiering chỉ như cách chia CPU workers nếu không có synchronization dependency.

## 16. Memory visibility và tính đúng kết quả

Theo Javadoc Phaser, các actions trước một dạng `arrive` *happen-before* corresponding phase advance và `onAdvance` (nếu có), rồi happens-before các actions sau phase advance. Điều này giúp workers trao đổi dữ liệu qua ranh giới phase khi dùng đúng lifecycle.

**Tuy nhiên:**
- `arriveAndDeregister()` **không chờ**; party đã rút không đương nhiên thấy dữ liệu mà worker khác sẽ ghi **sau** thời điểm nó rút.
- Nếu party rút rồi vẫn cần đợi toàn nhóm hoàn tất phase hiện tại, có thể gọi `awaitAdvance(arriveAndDeregister())`; lời gọi await chỉ quan sát phase, không re-register.
- Một shared mutable collection vẫn cần cấu trúc quyền sở hữu, thread safety và publication semantics; Phaser không tự sửa data race xảy ra **giữa** hai checkpoints.
- `getRegisteredParties()` chỉ là snapshot; không thay thế đồng bộ trên dữ liệu nghiệp vụ.
- Không dùng `Thread.sleep` như một memory barrier.

### 16.1. onAdvance và memory visibility

Mọi worker đến checkpoint rồi `onAdvance` có thể tổng hợp trạng thái của phase trước nhờ synchronization semantics; nhưng phải tránh override callback làm logic quá nặng/block và tái nhập cùng Phaser. Nếu kết quả tổng hợp có thể lỗi, xác định cơ chế failure và termination; unchecked exception từ `onAdvance` được propagate tới thread đang làm phase advance và có thể khiến phase không advance, nên không được bỏ qua.

## 17. Cancellation, timeout, registration ownership

Một Phaser không cấp object “PartyToken” sẵn để chứng minh ai đang registered. Vì vậy ứng dụng cần:
- Một logical party owner cho mỗi suất.
- Đăng ký trước khi giao việc; xử lý task submission bị từ chối.
- Tại mỗi phase, phân biệt party chưa arrive, đã arrive, đã deregister.
- Nếu có hai cancellation callbacks cạnh tranh, dùng state guard để chỉ một bên hoàn tất cleanup.
- Không gọi `arriveAndDeregister()` lần thứ hai trong cùng phase sau `arrive()`.
- Trong fatal failure, `forceTermination` và ghi cause thay vì làm phase advance với dữ liệu thiếu.
- Đóng executor/threads/resources theo owner, không coi `isTerminated` là JVM task đã dừng.

### 17.1. Anti-pattern: đăng ký worker sau phase đã bắt đầu

```java
Phaser p = new Phaser(1);
p.arrive();       // Chỉ coordinator -> phase 0 đã hoàn tất
p.register();     // Worker mới chỉ bắt đầu từ phase 1
```

Đây là snippet **chỉ dùng để giải thích lỗi**, không phải mẫu triển khai. Nếu muốn worker tham gia phase 0, phải register trước khi coordinator arrive lần đầu.

### 17.2. Anti-pattern: tới rồi rút hai lần

```java
int phase = p.arrive();
try {
    p.awaitAdvanceInterruptibly(phase, 100, TimeUnit.MILLISECONDS);
} catch (TimeoutException failure) {
    p.arriveAndDeregister(); // SAI nếu đó vẫn là cùng phase
}
```

Đây cũng là anti-pattern snippet. `TimeoutException` không tự thay đổi counts; call thêm arrival trên cùng logical party có thể phá invariants, kể cả khi một operation sau này mới ném `IllegalStateException`. Khi workflow không thể tiếp tục đúng, coordinator dùng forceTermination theo policy.

### 17.3. Interrupted wait có tự “break” Phaser?

Không. `awaitAdvance(phase)` thông thường đợi bất kể thread bị interrupt; `awaitAdvanceInterruptibly` có thể ném InterruptedException, nhưng Phaser counts không tự điều chỉnh. Đừng nhầm với `CyclicBarrier` broken semantics. Nếu method nuốt InterruptedException thay vì propagate, nên restore `Thread.currentThread().interrupt()` và có quyết định cleanup rõ ràng.

### 17.4. Khi task bị cancel trước khi chạy

Nếu caller đã `register()` rồi `submit` task, nhưng Future bị cancel trước khi task thực thi, **không ai chắc chắn sẽ gọi arrival**. Phải quản lý register/accept/cancel như một protocol có owner. Với batch mà một kết quả bắt buộc bị hủy, fail-fast `forceTermination` có thể dễ chứng minh tính đúng hơn cố deregister tất cả các phantom parties từ nhiều callbacks.

## 18. Hiệu năng: flat vs tiered và số threads cần thiết

Phaser hỗ trợ parties linh hoạt nhưng không miễn phí:
- Mỗi arrival liên quan đồng bộ bộ đếm.
- Nhiều threads cùng đến một flat Phaser có thể contention khi work mỗi phase quá nhỏ.
- Tiered Phaser chia contention nhưng có thêm cập nhật ở cấp parent.
- Chọn số group/parties per child theo **benchmark** trên workload thật, không theo một hằng số phổ quát.
- Pool có ít worker threads hơn số tasks đồng thời **block tại barrier** có thể gây starvation (task chưa chạy không đến barrier được). Javadoc lưu ý khả năng tiến triển khi parallelism đủ đáp ứng số parties bị block đồng thời.
- Với `ForkJoinPool`, Phaser có hỗ trợ phối hợp; nhưng pool/thread quotas và blocking work vẫn phải được thiết kế, không phải mọi trường hợp đều “auto-scale”.
- Nếu work mỗi phase quá nhỏ, synchronization overhead có thể lớn hơn useful computation.
- Nếu một worker làm việc nặng hơn, barrier làm cả nhóm chờ; cần cân bằng partitioning, không phải luôn thay flat bằng tiered.
- Đừng đo bằng `getUnarrivedParties()` polling liên tục; dùng profiler/metrics sampling ngoài hot path.

### 18.1. Khi nào benchmark tiered Phaser?

Chỉ khi bạn có workload lớn, nhiều parties, phase frequency cao và bằng chứng contention. So sánh:
1. Flat Phaser đơn giản.
2. Tiered Phaser với vài mức parties mỗi nhóm.
3. End-to-end throughput và p95/p99 latency.
4. CPU utilization, thread scheduling, GC, contention và cleanup complexity.

Nếu kết quả tương đương hoặc tiered chậm hơn, ưu tiên flat vì dễ kiểm chứng. Tối ưu chỉ số microbenchmark mà làm production error handling khó hơn không phải tự động là cải tiến.

## 19. Exceptions và cách đọc trạng thái

| Tình huống | Hành vi/ngoại lệ | Phương án xử lý |
| --- | --- | --- |
| Party arrival nhiều hơn số unarrived | Có thể `IllegalStateException` (đôi khi chỉ phát hiện ở operation sau) | Sửa party ownership/double arrival |
| `register/bulkRegister` vượt capacity của implementation | `IllegalStateException` | Thiết kế tiered phasers hoặc giảm parties |
| `awaitAdvanceInterruptibly` hết hạn | `TimeoutException` | Không tự dereg; quyết định abort policy |
| Thread chờ interruptible await bị ngắt | `InterruptedException` | Propagate/restore interrupt, không double arrive |
| `onAdvance` ném unchecked error | Error tới party gây advance, transition có thể không xảy ra | Không để callback block/lỗi không kiểm soát |
| Last party `arriveAndDeregister` | Default `onAdvance` khiến terminated | Đúng khi job kết thúc hoàn toàn |
| `register` khi terminated | Trả phase âm, không tăng parties | Tạo Phaser mới hoặc policy reuse |
| `forceTermination` | Thả waiters, không giảm registered | Báo lỗi qua Future/channel riêng |
| Worker không được executor chạy | Registered party không tới barrier | Đăng ký trước submit và xử lý rejection/cancel |
| Observer lỡ register | Barrier chờ cả observer | Dùng `awaitAdvance` không đăng ký |
| Child không còn party | Child tự deregister khỏi parent | Không dereg child ở parent thủ công |
| Worker quá chậm | Toàn nhóm chờ dù code đúng | Repartition workload/timeout, giảm coupling |

**Không** dùng exception như công cụ duy nhất để phát hiện sai party identity: Phaser không kiểm tra Thread IDs, nên một số lỗi sẽ làm phase advance sai mà không ném ngay.

### 19.1. Giới hạn parties và phase numbers

Javadoc Java SE 17 nêu implementation giới hạn tối đa **65.535 registered parties trên mỗi Phaser**. Với rất nhiều tasks, dùng tiered tree hoặc tổ chức lại cấu trúc. `getPhase()` tăng và wrap về 0 sau `Integer.MAX_VALUE`; nếu hệ thống chạy rất lâu, không dùng một phép so sánh integer đơn giản làm global sequence number vĩnh viễn không wrap.

## 20. Cách chọn trong năm tình huống gần với thực tế

### Tình huống A — Xử lý một đợt upload ảnh

Có 20 ảnh chuyển đổi song song, trả response sau khi 20 ảnh xong một lần. **Nên:** `CompletableFuture.allOf` hoặc latch + Futures để thu kết quả/lỗi. **Không cần:** Phaser nếu không có phase thứ hai.

### Tình huống B — Tính toán simulation mỗi frame

Có đúng 8 workers mô phỏng vật lý, không ai thay đổi, mỗi frame phải xong mới sang frame kế. **Nên:** `CyclicBarrier(8)` hoặc Phaser phẳng nếu cần observer/onAdvance. Nếu số workers cố định và muốn fail-fast broken semantics, CyclicBarrier dễ hiểu hơn.

### Tình huống C — Crawl theo nhiều vòng với workers rút dần

Một số workers hết tài liệu sau hai vòng, số khác còn nhiều vòng. **Nên:** Phaser, mỗi logical party deregister ở vòng cuối. Nếu thêm tasks động, cần controller quản lý registration gắn với đúng phase.

### Tình huống D — Hai nhóm xử lý đồng bộ một snapshot

East và West mỗi bên có một nhóm workers, cùng phải công bố kết quả snapshot k trước khi root đổi sang k+1. **Nên:** Phaser phân cấp nếu việc nhóm có ý nghĩa và contention đáng kể. Nếu chỉ 4 workers, một flat Phaser có thể đã đủ; không tạo tree vì tính năng đẹp.

### Tình huống E — Luồng sự kiện producer → consumer

Producer không phải đợi mọi consumer xong **mỗi message**; mỗi consumer có tốc độ riêng. **Nên:** queue/stream với backpressure và retry protocol, không đặt một Phaser ở từng message. Nếu có checkpoint thật sau mỗi batch lớn, có thể dùng một Phaser **riêng cho checkpoint**, không thay toàn bộ queue.

## 21. Quy trình thiết kế một Phaser mới

**Bước 1 — Vẽ dependency graph.** Ghi rõ ở mỗi vòng ai phải chờ ai, ai chỉ quan sát, ai có thể rút và có yêu cầu global checkpoint không.

**Bước 2 — Quyết định có thật sự cần Phaser.** Nếu chỉ một đợt, fixed barrier hay dependency chain, dùng công cụ đơn giản hơn theo bảng ở đầu bài.

**Bước 3 — Chọn flat hay tiered.** Bắt đầu bằng flat; tier khi có nhóm rõ hoặc profiling contention. Đừng nối các workflows độc lập vào cùng root.

**Bước 4 — Định nghĩa logical party owner.** Ai register, ai arrive, ai deregister, ai forceTerminate, ai release executor. Không có Thread identity bên trong Phaser.

**Bước 5 — Đăng ký trước khi tiến phase.** Sử dụng `Phaser(1)` cho coordinator nếu nó cần checkpoint, `bulkRegister(n)` cho workers, hoặc `new Phaser(0)` nếu chưa muốn một owner ban đầu.

**Bước 6 — Chọn method của từng vai trò.** Worker lặp: `arriveAndAwaitAdvance`; worker rút: `arriveAndDeregister`; coordinator chỉ quan sát: `awaitAdvance`; chỉ arrival: `arrive`. Không dùng một method cho tất cả.

**Bước 7 — Định nghĩa termination.** Last party dereg mặc định terminate; nếu cần K rounds hoặc reuse zero-party, override `onAdvance` với policy rõ; nếu fatal failure, forceTermination và error propagation.

**Bước 8 — Thiết kế cancellation/timeout.** Timed await không tự dereg; không double arrival. Quy định recovery path cho task bị reject, cancel pre-start, timeout sau arrival, và một participant chết.

**Bước 9 — Kiểm thử với bounded waits.** Dùng `Future.get(timeout)`, `Thread.join(timeout)`, `CountDownLatch` để ổn định thứ tự khởi động; có cleanup trong finally, không dựa vào `Thread.sleep` để tạo race.

**Bước 10 — Đo production workload.** Benchmark số parties, phase rate, slow participants, pool size, contention; giữ flat nếu không có lợi ích đo được từ tiering.

### 21.1. Một checklist ngắn cho owner của coordinator

- Coordinator là party hay observer?
- Nếu là party, nó sẽ `arrive` đúng **mỗi phase** chứ?
- Có thể shutdown trong khi workers đang chờ không?
- Nếu lỗi xảy ra khi worker đã arrive, có tránh dereg cùng phase không?
- Có error channel và call forceTermination không?
- Có xử lý executor rejection/pre-start cancellation không?
- Khi phase cuối hoàn tất, còn party nào đăng ký không?
- Nếu cần re-register, Phaser đã terminated chưa?
- Parent/child có được tự động quản lý đúng không?

## 22. Kiểm thử concurrency có thể lặp lại

### 22.1. Tránh assert theo thứ tự println

Scheduler có thể chạy bất kỳ worker trước/sau. Các chương trình bài dùng `Future.get(timeout)`, `CountDownLatch` và kiểm tra trạng thái ở những điểm đã đồng bộ. Trong ứng dụng thật, không test bằng cách “sleep 50 ms, mong worker đã đến”. Một test có sleep có thể đúng trên máy dev nhưng flake trên CI.

### 22.2. Tách kiểm thử thuật toán và kiểm thử coordination

- **Algorithm test:** từng worker xử lý đúng dữ liệu khi chạy một mình?
- **Barrier test:** tất cả parties đều phải đến trước khi cho phase mới?
- **Dynamic membership test:** một worker rút không còn bị chờ các phase sau?
- **Failure test:** một worker lỗi có giải phóng waiters và propagate cause?
- **Cancellation test:** task bị cancel trước start không để lại phantom party?
- **Tiering test:** child zero tự dereg parent; một nhóm không bỏ qua nhóm khác?
- **Observer test:** observer không làm tăng registered parties?
- **Termination test:** last party dereg, onAdvance policy, forced termination đúng contract?
- **Resource test:** executor threads hết sau test, không để JVM treo?

### 22.3. Những thuộc tính cần kiểm chứng

Phaser không nên tạo trạng thái “vượt phase” khi dữ liệu chưa sẵn sàng. Với một workload xử lý k phases, ghi một invariant business rõ, ví dụ “snapshot k của mọi nhóm hoàn tất trước khi bất kỳ worker dùng snapshot k+1”. Nếu invariant không đúng trong stress test, tăng timeouts hoặc thêm sleep chỉ che bug; cần sửa đăng ký, arrival hoặc dữ liệu chia sẻ.

## 23. Checklist code review

1. Bài toán có ranh giới phase chung thật hay chỉ có task dependencies?
2. Nếu một lần đợi, đã cân nhắc CountDownLatch/Future chưa?
3. Nếu fixed recurring, đã cân nhắc CyclicBarrier chưa?
4. Nếu số parties thay đổi, đã xác định Phaser registration policy?
5. Nếu có coordinator, nó là party hay observer?
6. Có tránh register observer khiến barrier chờ không?
7. Có biết `awaitAdvance` không tự arrive?
8. Có biết `arrive` không tự chờ?
9. Có biết `arriveAndDeregister` không chờ và rút future phases?
10. Có quản lý mỗi logical party đúng một registration owner?
11. Có tránh double arrival/double dereg trong cùng phase?
12. Có register đủ parties trước khi phase đầu advance?
13. Có xử lý late registration đúng phase?
14. Có quản lý task bị executor từ chối?
15. Có xử lý task cancel trước khi thực thi?
16. Có error channel để báo failure thay vì coi Phaser terminated là success?
17. Nếu một worker fatal failure, có `forceTermination`?
18. Có hiểu forceTermination không làm registered counts về 0?
19. Có kiểm tra `isTerminated`/`getPhase` trong termination policy?
20. Có phân biệt last-party default termination và zero-party initial state?
21. Nếu override `onAdvance`, callback có ngắn và không tái nhập chính Phaser?
22. Có timeout policy mà không double arrive sau timed wait?
23. Có xử lý interrupt mà không phá party counts?
24. Nếu dùng tiered, có hiểu parent chỉ đếm một party cho mỗi child?
25. Có tránh tự dereg parent thay cho child?
26. Các nhóm nối root có thật sự có global checkpoint?
27. Có đo flat vs tiered trước khi thêm cấu trúc cây?
28. Worker pool có đủ parallelism cho tasks chờ barrier?
29. Có tránh dùng phase number như event queue không mất sự kiện?
30. Có kiểm thử memory visibility/data races quanh phase?
31. Có giới hạn số parties và xử lý phase wrap khi chạy rất lâu?
32. Có bounded Future/Thread joins trong tests?
33. Có cleanup phaser/executor/tasks ngay cả khi test lỗi?
34. Có ghi tài liệu rõ ai owns coordinator/root/children?
35. Các API sử dụng có phải API Java 17 hiện hành không?

## 24. Câu hỏi tự kiểm tra và đáp án

**1. Khi nào không nên dùng Phaser?** Khi không có phase barrier thật, ví dụ one-shot result graph hoặc streaming queue.

**2. CountDownLatch khác Phaser ở đâu?** Latch là one-shot countdown, không reset/dynamic phases; Phaser có reusable phases và dynamic registration.

**3. CyclicBarrier phù hợp khi nào?** Số participants cố định và gặp nhau ở nhiều rounds.

**4. Phần mạnh nhất của Phaser so với CyclicBarrier?** Register/deregister parties động, phase numbers, observers và tiering.

**5. Registered party có đồng nghĩa một Thread?** Không, Phaser chỉ giữ counts.

**6. Coordinator chỉ quan sát phase có phải register?** Không; gọi `awaitAdvance` với phase quan sát được.

**7. Coordinator cần cho phép chuyển phase có phải register?** Có, nếu nó là một participant bắt buộc trong dependency.

**8. Worker kết thúc sau vòng 2 mà nhóm còn vòng 3?** Worker `arriveAndDeregister()` ở vòng cuối mình tham gia.

**9. `arrive()` có chờ không?** Không.

**10. `arriveAndAwaitAdvance()` có rút membership không?** Không.

**11. Child có hai workers được root đếm thành bao nhiêu party?** Một party đại diện cho child khi child registered>0.

**12. Child rút hết thì parent cần dereg thêm bằng tay?** Không, child tự dereg khỏi parent.

**13. `onAdvance` được gọi ở child hay root của tree?** Ở root cho mỗi global phase advance.

**14. Khi nào nên chọn tiered?** Có grouping/checkpoint chung và contention đủ lớn để phân cấp có lợi.

**15. Khi timed await ném TimeoutException, parties có tự giảm?** Không.

**16. `arrive()` rồi timed out có nên `arriveAndDeregister()` trong cùng phase?** Không; có thể double arrival.

**17. Worker fatal error có nên bình thường dereg như success?** Thường không, nếu workflow cần output đầy đủ; forceTermination và propagate error.

**18. `forceTermination` có giảm registeredParties về 0?** Không.

**19. `register()` sau terminated có tạo party mới?** Không, trả phase âm.

**20. `new Phaser(0)` có mặc định terminated?** Không.

**21. Có thể “quay ngược” phase để thêm worker đã register muộn?** Không.

**22. `awaitAdvance(phase)` có luôn trả chính xác một lần cho mỗi phase event?** Không, không phải hàng đợi events.

**23. Tại sao không dùng Phaser cho CompletableFuture.thenCombine?** Hai results tạo dependency một lần, không có reusable group barrier.

**24. Một barrier với 4 parties nhưng executor chỉ chạy được 2 blocking workers có vấn đề gì?** Có thể starvation/deadlock vì các tasks chưa được chạy không đến barrier.

**25. Khi onAdvance quyết định terminate, chỉ nhìn return value không âm có đủ?** Không, kiểm tra isTerminated/current phase.

**26. Vì sao không polling getUnarrivedParties để làm barrier?** Đó là snapshot đang thay đổi, không phải synchronization primitive.

**27. `Phaser` hiện hành ở Java 17 không?** Có, thuộc `java.util.concurrent`, có từ Java 7.

**28. Cách biết tất cả worker tasks thực sự dừng?** Future/Thread/executor lifecycle, không chỉ isTerminated hay party count.

## 25. Bài tập thực hành

### A. Bỏ Phaser khi không có barrier

Chạy `OneShotLatchDemo` và `CompletableFutureGraphDemo`. Giải thích vì sao hai task chỉ gặp nhau một lần không bắt buộc dùng Phaser.

### B. Fixed barrier

Chạy `FixedCyclicBarrierDemo`, thay 2 rounds bằng 3 rounds và kiểm chứng số worker operations. Sau đó đặt một worker không đến vòng 3; dùng timed await và giải thích broken barrier.

### C. Flat Phaser

Chạy `FlatPhaserRoundsDemo`, tăng lên 4 workers và giữ coordinator; đăng ký đầy đủ trước khi submit và dùng đủ executor threads. Kiểm tra completedWorkerRounds và final registered count.

### D. Dynamic parties

Chạy `DynamicPartyCountDemo`, đổi worker ngắn sang 1 hoặc 3 rounds. Xác minh coordinator và worker dài không chờ party đã rút.

### E. Observer

Chạy `ObserverPhaseDemo`. Thử register thêm một observer nhưng không cho nó arrive; giải thích vì sao phải forceTermination hoặc dereg đúng party để tránh treo.

### F. Tiered teams

Chạy `TieredTeamPhaserDemo`. Thêm một child thứ ba có 2 workers và kiểm tra parent count ban đầu tăng một, không tăng hai.

### G. Flat vs tiered benchmark

Với phase work thực, so sánh flat và tiered khi có nhiều parties và nhiều rounds, dùng cùng pool/hardware. Theo dõi contention, throughput, memory, không suy tốc độ từ một run.

### H. onAdvance

Chạy `OnAdvancePolicyDemo`, đổi termination condition sang phase>=2 (3 rounds). Quan sát giá trị return của last caller, isTerminated và getPhase.

### I. Fatal failure

Chạy `AbortOnFailureDemo`. Thêm một worker bình thường đang chờ và cho coordinator nhận failure cause; bảo đảm tất cả waiters thoát mà không giả vờ success.

### J. Timed wait

Chạy `TimedObservationDemo`. Giải thích vì sao party đã arrive không được “rút bằng một arrival nữa” trong cùng phase khi timeout.

### K. Registration race

Chạy `RegistrationOrderingDemo` rồi sửa để register worker **trước** coordinator arrive. So sánh phase advance và registered counts.

### L. Task rejected

Viết test với executor đã shutdown: register rồi submit task để nhận `RejectedExecutionException`; cleanup suất chưa chuyển giao hoặc abort toàn phaser nếu workflow đã không thể tiếp tục.

### M. Khung phối hợp độc lập

Thiết kế hai nhóm có chu kỳ 100 ms và 1 giây mà không có global checkpoint. Chứng minh vì sao hai Phasers độc lập hoặc queue tốt hơn một root chung.

### N. Coordinator party vs observer

Tạo bài toán coordinator đọc snapshot sau khi workers phase0 hoàn tất; so sánh phiên bản coordinator là registered party để xác nhận checkpoint với observer dùng awaitAdvance. Nêu rõ invariant khác nhau.

## 26. Tài liệu Java chính thức

- [Java SE 17 — Phaser](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Phaser.html): dynamic registration, arrivals, waiting, deregistration, termination, tiering và memory consistency.
- [Java SE 17 — CyclicBarrier](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CyclicBarrier.html): fixed-party reusable barrier và broken semantics.
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): one-shot countdown.
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): dependency graph, completion stages và kết hợp results.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): task submission, Futures và lifecycle.
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): result/error/cancellation.
- [Java SE 17 — ForkJoinPool](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): parallelism, tasks và cách quản lý blocking.
- [Java SE 17 — BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): dữ liệu qua pipeline producer/consumer.
- [Java SE 17 — Semaphore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html): giới hạn số concurrent accesses.

**Tóm lại:** `Phaser` phù hợp khi bài toán có **barrier nhiều giai đoạn với party count có thể thay đổi, observer không là member, policy termination theo phase, hoặc nhóm phân cấp cùng checkpoint**. Nếu chỉ đếm hoàn tất một lần, chọn latch/futures; nếu fixed-party repeated barrier, cân nhắc CyclicBarrier; nếu dependency graph hoặc queue stream, không ép Phaser. Bất kỳ thiết kế Phaser nào cũng phải quy định rõ đăng ký trước phase, owner của mỗi logical party, arrival/deregistration đúng một lần mỗi phase, failure/timeout policy và cơ chế shutdown. Bắt đầu từ cấu trúc phẳng, chỉ thêm tiering nếu có lý do nghiệp vụ hoặc số đo contention thuyết phục.
