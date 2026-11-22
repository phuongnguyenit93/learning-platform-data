# Lock contention, starvation và fairness trade-off trong Java

## 1. Bối cảnh và mục tiêu

Một chương trình dùng nhiều thread không tự động chạy nhanh hơn. Nếu nhiều thread thường xuyên tranh cùng một lock, phần lớn thời gian có thể bị tiêu tốn để chờ, chuyển ngữ cảnh hoặc đánh thức thread thay vì làm công việc hữu ích. Đó là **lock contention**. Trong một số cách lập lịch hoặc chính sách cấp lock, có thread phải chờ rất lâu dù các thread khác vẫn liên tục tiến lên: đó là **starvation**. Đổi từ lock không công bằng (*nonfair*) sang lock công bằng (*fair*) có thể cải thiện khả năng được phục vụ theo thứ tự, nhưng thường phải đánh đổi hiệu năng.

Bài này tập trung vào **Java concurrency nói chung**: `synchronized`, `ReentrantLock`, `ReentrantReadWriteLock` và các kỹ thuật đo/giảm cạnh tranh; không phụ thuộc framework.

Sau bài học, bạn có thể:

- Nhận diện lock contention trong code và trong số liệu runtime.
- Phân biệt contention, starvation, deadlock, livelock và hiện tượng chậm do CPU hoặc I/O.
- Giải thích khác biệt giữa khóa fair và nonfair, cùng giới hạn của từng chính sách.
- Dùng `ReentrantLock(true)` đúng cách, nhận biết ngoại lệ với `tryLock()`.
- Chọn biện pháp tối ưu dựa trên throughput, tail latency, khả năng tiến triển và tính đúng đắn.

## 2. Lock contention diễn ra thế nào?

**Critical section** là đoạn code chỉ một thread (hoặc số thread được phép) truy cập tại một thời điểm để bảo vệ trạng thái chung. Khóa càng bao quanh nhiều thao tác, thời gian giữ khóa (*hold time*) càng dài. Khi nhiều thread cần cùng một lock, chúng phải phối hợp quyền vào vùng bảo vệ.

```text
Thread A: [lấy lock] [đọc/sửa state........] [nhả lock]
Thread B:     [muốn lock] [----- chờ -----] [lấy] [sửa] [nhả]
Thread C:          [muốn lock] [----------- chờ ----------] ...
```

Chờ có thể biểu hiện dưới dạng:

- Thread chờ monitor của `synchronized` thường có trạng thái `BLOCKED` trong thread dump.
- Thread chờ `ReentrantLock` thường được park thông qua cơ chế đồng bộ của `java.util.concurrent.locks`; snapshot có thể thấy `WAITING` hoặc `TIMED_WAITING`, không nhất thiết `BLOCKED`.
- Một số lần lấy lock không phải chờ vì khóa đang rảnh; một số lần có tranh chấp ngắn chỉ gây chi phí điều phối nhỏ.
- Có thể tồn tại vòng lặp retry trong thuật toán không khóa (*lock-free*), nhưng đó là dạng cạnh tranh khác; không nên gọi mọi retry là lock contention.

Các yếu tố làm contention tăng:

1. **Tần suất lấy lock cao:** nhiều thao tác nhỏ đều phải vào cùng critical section.
2. **Thời gian giữ lock dài:** xử lý nặng, I/O, log đồng bộ, chờ mạng, sleep hoặc gọi callback khi vẫn giữ lock.
3. **Nhiều thread cùng chạm một state:** một global counter, một map hoặc một hàng đợi chia sẻ.
4. **Độ lệch tải:** một key nóng hoặc một nhóm tác vụ liên tục giữ lock trong khi nhóm khác chờ.
5. **Tổ hợp nhiều lock:** thread giữ khóa A rồi chờ B khiến A bị chiếm lâu hơn, có thể tạo chuỗi chờ.

Contended lock tạo một điểm **tuần tự hóa**: tăng thread không làm critical section chạy song song. Nếu phần code bắt buộc tuần tự chiếm tỷ lệ lớn, tốc độ tổng không thể tăng tuyến tính theo số lõi. Việc tạo thêm thread còn có thể làm chậm hệ thống.

## 3. Contention, starvation, deadlock và livelock

| Hiện tượng | Dấu hiệu chính | Hệ thống còn tiến triển? | Cách tiếp cận |
| --- | --- | --- | --- |
| **Contention** | Nhiều thread phải chờ cùng lock; lock queue hoặc thời gian blocked/park tăng. | Thường có; các thread vẫn lần lượt hoàn thành. | Giảm thời gian giữ khóa, tần suất khóa, state chia sẻ và đo lại. |
| **Starvation** | Một thread hoặc một nhóm không được cấp cơ hội chạy/lấy lock trong thời gian rất dài. | Có thể: thread khác vẫn hoàn thành. | Xem chính sách fairness, mức ưu tiên, nguồn tải liên tục và thiết kế scheduler/queue. |
| **Deadlock** | Chu kỳ phụ thuộc tài nguyên: A giữ L1 chờ L2, B giữ L2 chờ L1. | Các thread trong chu kỳ không tiến triển nếu không có can thiệp. | Quy định thứ tự lấy lock, giảm nested locks, timeout và phân tích thread dump. |
| **Livelock** | Thread liên tục phản ứng/thử lại nhưng vẫn không hoàn thành công việc có ích. | Có hành động nhưng không hoàn tất. | Backoff, giới hạn retry, giảm đối xứng và điều phối tiến trình. |

**Starvation không đồng nghĩa với “chờ lâu một lần”.** Một lần chờ lâu có thể do critical section tốn thời gian, GC pause, CPU thiếu, I/O hoặc hệ điều hành lập lịch. Muốn kết luận starvation phải nhìn **mẫu lặp lại và chênh lệch quyền tiến triển**: có thread liên tục được phục vụ trong khi thread khác kéo dài hoặc không có cơ hội.

Ví dụ điển hình: T1 đang đợi một `ReentrantLock` nonfair. Mỗi khi lock được nhả, thread mới vừa chạy có thể giành được lock trước T1. Việc này lặp lại đủ lâu sẽ làm T1 bị đói tài nguyên. Đây là **rủi ro**, không có nghĩa nonfair lock luôn gây starvation.

Starvation cũng có thể đến từ thread priority, executor thiếu worker, task chiếm pool hoặc hệ điều hành không cấp CPU; dùng fair lock chỉ xử lý **một phần** bài toán.

## 4. Fairness của Java lock có nghĩa gì?

### `synchronized` và monitor

`synchronized` bảo đảm mutual exclusion và những quan hệ *happens-before* khi unlock/lock cùng monitor. Đặc tả Java **không bảo đảm** thread vào monitor theo FIFO. Không nên coi thread nào chờ lâu nhất sẽ luôn được chọn tiếp.

```java
private final Object monitor = new Object();

void update() {
    synchronized (monitor) {
        // Chỉ đoạn thật sự bảo vệ state chung.
    }
}
```

Ưu điểm của `synchronized` là ngắn gọn, dễ đọc, tự nhả monitor khi ra khỏi khối kể cả khi có ngoại lệ. Không có tham số fair/nonfair và không có API `tryLock` hay timed lock acquisition tương đương `ReentrantLock`.

### `ReentrantLock` nonfair (mặc định)

`new ReentrantLock()` tương đương lock với chính sách không công bằng; khi đang tranh chấp, một thread mới đến có thể **barging**: lấy lock trước thread chờ lâu hơn. Điều này có thể giảm chi phí chuyển giao trực tiếp giữa những thread đang chờ và tăng throughput trong một số workload, nhưng không cam kết thứ tự phục vụ hay giới hạn thời gian chờ của một thread cụ thể.

### `ReentrantLock(true)` fair

`new ReentrantLock(true)` sử dụng chính sách ưu tiên thread đã chờ lâu hơn **khi có tranh chấp**, áp dụng cho các phương thức lấy lock chịu chính sách fairness. Đây là chính sách tương đối FIFO tại hàng đợi lock, không phải lời hứa mỗi thread sẽ được CPU lập lịch công bằng hoặc có thời gian chờ tối đa cố định.

```java
import java.util.concurrent.locks.ReentrantLock;

ReentrantLock lock = new ReentrantLock(true);

lock.lock();
try {
    // Truy cập state dùng chung.
} finally {
    lock.unlock();
}
```

Đoạn trên chỉ minh họa cách dùng trong một class/method; nó **không phải chương trình Java độc lập**.

**Ngoại lệ dễ bỏ sót:** `tryLock()` **không tham số** có thể lấy ngay lock đang rảnh **bất kể** lock được cấu hình fair hay nonfair; nó có thể chen trước các thread đang chờ. Khi cần tuân thủ chính sách fair cho một thử lấy lock có timeout, dùng `tryLock(timeout, TimeUnit)`, kể cả `tryLock(0, TimeUnit.SECONDS)` nếu muốn thử tức thì nhưng vẫn tôn trọng fairness. Việc dùng `lockInterruptibly()` cũng cho phép phản ứng với interrupt khi chờ khóa.

```java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

// Biến lock đã được khởi tạo ở nơi sở hữu:
boolean acquired = lock.tryLock(100, TimeUnit.MILLISECONDS);
if (acquired) {
    try {
        // Xử lý ngắn, không chặn I/O khi có thể tránh.
    } finally {
        lock.unlock();
    }
} else {
    // Không lấy được lock trong thời hạn; retry/backoff/fail theo yêu cầu.
}
```

Lời gọi `tryLock(timeout, unit)` có thể ném `InterruptedException`, vì vậy đoạn minh họa phải nằm trong method khai báo `throws InterruptedException` hoặc xử lý ngoại lệ. Mọi lần lấy lock thành công phải ghép với `unlock()` trong `finally`.

## 5. Fairness đánh đổi điều gì?

Một cách nhìn thực tế là tách các tiêu chí, vì **“công bằng hơn” không nhất thiết “nhanh hơn”**.

| Tiêu chí | Nonfair lock | Fair lock |
| --- | --- | --- |
| Thứ tự cấp lock | Cho phép barging, không ưu tiên nghiêm ngặt theo thời gian đợi. | Ưu tiên thread chờ lâu hơn khi tranh chấp, với các API tuân thủ fairness. |
| Throughput | Có thể cao hơn khi giữ lock ngắn và tranh chấp lớn. | Thường thấp hơn dưới contention do việc điều phối/đánh thức và chuyển quyền. |
| Độ biến thiên thời gian chờ | Một số thread có thể bị lấn át lặp lại, tail latency cao. | Có thể giảm chênh lệch thời gian chờ lấy lock giữa các thread. |
| Starvation | Không có bảo đảm tránh starvation. | Giảm rủi ro starvation do barging; không giải quyết starvation do CPU scheduler hoặc tác vụ bên ngoài. |
| Khi ít tranh chấp | Khác biệt có thể nhỏ. | Khác biệt có thể nhỏ; cần đo trên workload thật. |
| Bảo đảm thời gian chờ tối đa | Không có. | Vẫn **không** có giới hạn thời gian chờ tuyệt đối. |

Fair lock có thể khiến nhiều thread phải chuyển quyền theo thứ tự chờ thay vì cho thread vừa đang chạy chiếm lock ngay. Việc đó làm tăng chi phí đánh thức/chuyển ngữ cảnh và giảm cache locality trong một số tình huống. Tuy nhiên, cả kết quả throughput lẫn tail latency đều phụ thuộc số thread, độ dài critical section, CPU, lịch chạy, tần suất GC và workload; không có tỉ lệ nhanh/chậm cố định.

**Đừng chọn fairness như một tham số “để cho an toàn” mà không có yêu cầu.** Xác định trước vấn đề cần sửa: thông lượng không đạt, một nhóm request bị đói, deadline khó đáp ứng, hay số lượng thread blocked tăng? Khi tính đúng đắn đã đảm bảo, so sánh cả throughput và phân phối thời gian chờ, đặc biệt p95/p99, thay vì chỉ nhìn average.

Cũng không nên đánh đồng fairness cấp lock với công bằng về **business priority**: ví dụ đơn hàng ưu tiên cần một hàng đợi điều phối có chính sách ưu tiên riêng, không thể diễn đạt chỉ bằng `ReentrantLock(true)`.

## 6. Chương trình Java 17+: cùng một công việc với fair và nonfair lock

Ví dụ sau tạo bốn worker cùng tăng một counter. Chúng bắt đầu gần nhau nhờ `CountDownLatch`, mỗi lần tăng phải chiếm cùng lock. Chạy lần lượt với `ReentrantLock(false)` và `ReentrantLock(true)` để quan sát rằng **cả hai đều bảo đảm giá trị counter**, còn thứ tự và tốc độ thực tế có thể khác nhau. Chúng ta cố ý **không in timing cố định** vì scheduling không xác định và ví dụ nhỏ không phải benchmark.

Tạo file **`LockContentionDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public class LockContentionDemo {
    private static final int WORKERS = 4;
    private static final int UPDATES_PER_WORKER = 4_000;

    private static final class Counter {
        private final ReentrantLock lock;
        private long count;

        Counter(boolean fair) {
            this.lock = new ReentrantLock(fair);
        }

        void increment() {
            lock.lock();
            try {
                count++;
            } finally {
                lock.unlock();
            }
        }

        long valueAfterWorkersFinish() {
            return count;
        }
    }

    private static long runCase(boolean fair) throws Exception {
        Counter counter = new Counter(fair);
        ExecutorService pool = Executors.newFixedThreadPool(WORKERS);
        CountDownLatch ready = new CountDownLatch(WORKERS);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<?>> futures = new ArrayList<>();

        try {
            for (int worker = 0; worker < WORKERS; worker++) {
                futures.add(pool.submit(() -> {
                    ready.countDown();
                    start.await();

                    for (int i = 0; i < UPDATES_PER_WORKER; i++) {
                        counter.increment();
                    }
                    return null;
                }));
            }

            if (!ready.await(30, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Workers chưa sẵn sàng");
            }

            start.countDown();

            for (Future<?> future : futures) {
                future.get(); // Chờ worker xong và nhận lỗi nếu task thất bại.
            }

            return counter.valueAfterWorkersFinish();
        } finally {
            start.countDown(); // Tránh kẹt worker nếu nhánh trước phát lỗi.
            pool.shutdown();
            if (!pool.awaitTermination(30, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("nonfair: " + runCase(false));
        System.out.println("fair: " + runCase(true));
    }
}
```

Biên dịch và chạy:

```bash
javac LockContentionDemo.java
java LockContentionDemo
```

Output khi hai lượt hoàn tất bình thường:

```text
nonfair: 16000
fair: 16000
```

**Vì sao output có thể xác định?** Mỗi worker thực hiện đúng `4_000` lần tăng, tổng `4 × 4_000 = 16_000`, và `Future.get()` chỉ trả về sau khi tác vụ kết thúc. Các thao tác trước khi task hoàn tất được nhìn thấy sau `Future.get()`; không có race khi main đọc count. `ReentrantLock` bảo vệ thao tác `count++` khỏi lost update.

**Vì sao output không chứng minh hiệu năng?** Chương trình không đo thời gian, và số lượt cập nhật quá nhỏ để đưa ra kết luận ổn định. Trong workload khác, hai chính sách có thể gần bằng nhau; fair lock thường chịu thêm overhead khi contention tăng. Để benchmark cho ra quyết định, dùng JMH với warmup, nhiều lần đo, fork JVM, nhiều mức thread và xử lý nhiễu GC/JIT; đo kèm phân phối latency và mức contention thực tế.

**Nhìn kỹ việc dọn tài nguyên:** `pool.shutdown()` và `awaitTermination(...)` được gọi trong `finally`; `shutdownNow()` chỉ cố gắng interrupt những task còn chạy. Với ví dụ này, các task phản ứng được với interrupt khi đang chờ `CountDownLatch`. Trong code tổng quát, cần thêm chính sách chờ/khôi phục interrupt và quản lý task bị hủy.

## 7. Giảm contention thường hiệu quả hơn chỉ đổi sang fair lock

Trước khi chọn fairness, hãy tìm phần thời gian giữ lock có thể bỏ hoặc giảm.

### 7.1. Rút ngắn critical section

**Không phù hợp:** giữ lock trong cả thao tác I/O hay tính toán không cần bảo vệ.

```java
synchronized (monitor) {
    // Lấy state cần thiết...
    // Gọi HTTP, đọc file, ghi log chậm hoặc tính toán dài.
    // Cập nhật state...
}
```

**Tốt hơn khi logic cho phép:** chụp giá trị cần dùng trong critical section, xử lý độc lập bên ngoài, rồi cập nhật kết quả dưới lock ngắn. Phải kiểm tra lại điều kiện khi ghi kết quả nếu state có thể thay đổi trong lúc tính toán.

```java
long snapshot;
synchronized (monitor) {
    snapshot = sharedValue;
}

long result = expensivePureComputation(snapshot);

synchronized (monitor) {
    // Chỉ áp dụng result nếu điều kiện/version vẫn hợp lệ.
    // Nếu không, retry hoặc xử lý conflict theo quy tắc nghiệp vụ.
}
```

Đây là mã minh họa nằm trong class/method có các biến và hàm tương ứng. Không thể tách mọi atomic transaction thành hai vùng khóa mà vẫn giữ đúng semantics; cần kiểm chứng invariant và tính nhất quán.

### 7.2. Giảm chia sẻ state

- **Thread confinement:** mỗi worker xử lý state riêng, chỉ tổng hợp sau khi hoàn tất.
- **Partition/sharding:** chia dữ liệu theo key hoặc nhóm độc lập, tránh một global lock.
- **Immutable snapshot:** đọc bản bất biến và cập nhật bằng cơ chế phù hợp để giảm khóa đọc.
- **`LongAdder`:** hữu ích cho bộ đếm được cập nhật cạnh tranh mạnh, khi không cần một snapshot tuyến tính hóa chính xác cùng các state khác. `sum()` trong khi có cập nhật đồng thời không phải snapshot nguyên tử.
- **`ConcurrentHashMap`:** thay một map được khóa toàn cục khi nhu cầu chủ yếu là thao tác concurrent theo key. Không tự động làm atomic cho chuỗi nhiều bước ngoài API cung cấp.

Dùng `AtomicInteger`/`AtomicLong` có thể bỏ lock cho một cập nhật đơn lẻ, nhưng với nhiều biến cần giữ invariant chung, chuyển sang atomics rời rạc có thể làm sai logic.

### 7.3. Đổi phạm vi lock hoặc kiểu đồng bộ

- `ReentrantReadWriteLock`: cho phép nhiều reader cùng giữ read lock, writer độc quyền. Có thể tăng throughput khi tỷ lệ read cao và critical section đủ lớn; nếu write nhiều hoặc read rất ngắn, overhead có thể làm chậm hơn.
- `StampedLock`: hỗ trợ optimistic read với `validate(stamp)`, nhưng API phức tạp, không reentrant và không bảo đảm công bằng; không nên chọn chỉ để “chống starvation”.
- `Semaphore`: giới hạn số thao tác đồng thời. `Semaphore(true)` có chính sách FIFO cho những phương thức lấy permit chịu fairness, nhưng `tryAcquire()` không timeout vẫn có thể barging.
- `BlockingQueue` hoặc mô hình worker sở hữu state: đưa cập nhật qua một hàng đợi để một nơi xử lý tuần tự, khi phù hợp với yêu cầu thứ tự và độ trễ.

Đổi primitive phải dựa trên semantics của dữ liệu. Nếu cần một transaction bảo vệ nhiều field, thay `ReentrantLock` bằng `ConcurrentHashMap` không tự động bảo vệ transaction đó.

## 8. Phát hiện contention và starvation trong JVM

### 8.1. Dấu hiệu cần quan sát

- Throughput đứng yên hoặc giảm khi số worker tăng.
- p95/p99 latency tăng, nhiều thread chờ khóa hoặc đợi executor.
- CPU có thể chưa dùng hết mà request vẫn chậm vì thread đợi nhau; ngược lại CPU cao cũng không chứng minh contention.
- Một nhóm thread có số lần hoàn thành quá thấp so với nhóm khác trong cùng điều kiện tải.
- Một monitor hoặc stack frame xuất hiện liên tục tại điểm chờ trong nhiều thread dump.

### 8.2. Thread dump

Có thể dùng `jcmd <pid> Thread.print -l` để xem trạng thái và stack các thread (thay `<pid>` bằng PID thật). Ví dụ một thread đang đợi monitor:

```text
"worker-7" ... java.lang.Thread.State: BLOCKED (on object monitor)
    at example.Inventory.update(Inventory.java:42)
    - waiting to lock <...> (a java.lang.Object)
```

Đoạn thread dump trên chỉ minh họa; tên thread và địa chỉ monitor trong JVM thật sẽ khác. Hãy tìm nhiều thread cùng chờ ở một lock và thread đang giữ lock đó. Với `ReentrantLock`, thread dump có thể cho thấy `LockSupport.park` và `AbstractQueuedSynchronizer` thay cho trạng thái `BLOCKED`.

Thread dump là **ảnh chụp thời điểm**. Một ảnh có thread đang đợi không đủ chứng minh starvation; cần nhiều mẫu theo thời gian hoặc telemetry dài hơn.

### 8.3. Java Flight Recorder (JFR)

JFR hữu ích để thu sự kiện liên quan khóa và lập lịch với chi phí hợp lý. Trên JDK hỗ trợ, có thể bật recording trong quá trình chạy bằng một lệnh như:

```bash
jcmd <pid> JFR.start name=locks settings=profile duration=60s filename=locks.jfr
```

Mở file `locks.jfr` bằng Java Mission Control hoặc công cụ đọc JFR tương thích. Các event đáng xem gồm:

- `jdk.JavaMonitorEnter`: chờ vào monitor do `synchronized`.
- `jdk.JavaMonitorWait`: chờ qua `Object.wait()` (khác với tranh chấp để *vào* monitor).
- `jdk.ThreadPark`: thời gian park có thể liên quan `ReentrantLock`, `Condition`, queue hoặc nhiều cơ chế chờ khác; cần xem stack trace để xác định nguồn.

Khả năng hiển thị, ngưỡng sự kiện và overhead phụ thuộc cấu hình JFR; không coi một event đơn lẻ là chứng cứ starvation. Thử nghiệm trên môi trường phù hợp trước khi bật profile trong production.

### 8.4. Metrics từ API

`ReentrantLock.getQueueLength()` ước tính số thread đang chờ lấy lock; đây là **ước lượng tức thời**, không phải số chính xác hay cam kết ổn định cho logic điều phối. `ReentrantLock.hasQueuedThreads()` cũng chỉ phản ánh trạng thái quan sát tại thời điểm gọi. Không viết thuật toán đúng/sai dựa trên giá trị ước lượng này.

`ThreadMXBean` hỗ trợ truy vấn trạng thái thread và, khi được JVM hỗ trợ/bật, thời gian blocked/waited. Các số liệu này không thay thế hoàn toàn event chuyên biệt hay profiler. Với một service nhiều loại chờ, hãy kết hợp traces, histogram latency, số task hoàn thành và số lượng thread ở từng trạng thái.

## 9. Khi nào nên bật fair lock?

Xem xét `ReentrantLock(true)` khi:

1. Có bằng chứng lặp lại rằng một số thread thường xuyên bị barging trong hàng chờ lock và tiến triển không chấp nhận được.
2. Yêu cầu đảm bảo tương đối về thứ tự tiếp cận tài nguyên quan trọng hơn tối đa hóa tổng throughput.
3. Đã đo và chấp nhận tác động đến throughput/latency trong tải mục tiêu.
4. Các đoạn code sử dụng lock tuân thủ policy; không lẫn với `tryLock()` không timeout một cách vô ý.

**Không nên bật fairness chỉ vì thấy nhiều thread đang chờ.** Nếu một lock giữ quá lâu, chuyển thành fair vẫn để mọi thread phải tuần tự hóa trên critical section đó. Đầu tiên đo lock hold time, giảm công việc dưới lock và giảm mức chia sẻ.

Đối với tác vụ có deadline, timed acquisition cho phép phản hồi thất bại có kiểm soát:

```java
if (!lock.tryLock(200, TimeUnit.MILLISECONDS)) {
    throw new IllegalStateException("Không lấy được lock trong hạn");
}
try {
    updateSharedState();
} finally {
    lock.unlock();
}
```

Mã trên cần biến `lock`, hàm `updateSharedState()` và xử lý/khai báo `InterruptedException` trong method bao ngoài. Timeout không tự làm yêu cầu thành công; nó tạo ra **đường xử lý khi không lấy được lock**. Nếu bị interrupt, ưu tiên để ngoại lệ truyền lên hoặc khôi phục interrupt status khi bắt ngoại lệ và không ném lại.

## 10. Benchmark và cách đánh giá công bằng đúng cách

Một thí nghiệm có ích cần quan sát cả **lợi ích và giá phải trả**:

| Chỉ số | Vì sao đo? |
| --- | --- |
| Throughput (operations/s) | Fairness có làm giảm tổng khối lượng công việc hoàn tất không? |
| Average và p50/p95/p99 acquisition latency | Ai phải chờ lâu; tail latency có tăng hoặc giảm? |
| Số operation hoàn thành theo từng worker | Phát hiện mất cân bằng và thread tiến triển quá chậm. |
| Phân phối hold time | Giải thích tắc nghẽn do critical section dài. |
| Số thread chờ, JFR lock event | Xác nhận bottleneck thực sự ở khóa nào. |
| CPU, GC, scheduler/park activity | Phân biệt lock contention với nguyên nhân khác. |

Giữ nguyên logic và kích thước critical section giữa hai phép thử; thay đổi duy nhất chính sách fair/nonfair khi cần đánh giá riêng fairness. Kiểm tra nhiều mức tải: ít thread hơn lõi, xấp xỉ số lõi và vượt số lõi. Dùng JMH để hạn chế sai lệch do warmup, dead-code elimination và JIT. Với benchmark chia sẻ tài nguyên, JMH có cấu hình state/threads phù hợp; đừng lấy một lần chạy `System.nanoTime()` làm bằng chứng quyết định.

Trong ứng dụng thật, đánh giá theo SLA: đôi khi giảm starvation quan trọng hơn throughput; đôi khi một lựa chọn giúp tăng throughput nhưng làm p99 tệ hơn lại không đáp ứng yêu cầu dịch vụ.

## 11. Lỗi phổ biến và cách sửa

1. **Cho rằng fair lock bảo đảm không starvation ở toàn hệ thống.** Nó chỉ tác động chính sách cấp lock; thread scheduling, priority, executor và những lock khác vẫn có thể khiến task bị đói.
2. **Cho rằng fair = FIFO tuyệt đối cho mọi lần gọi.** `tryLock()` không tham số của `ReentrantLock` fair vẫn có thể barging.
3. **Bật fairness để chữa critical section giữ lock quá lâu.** Chưa xử lý nguyên nhân; hãy đo và thu hẹp vùng khóa.
4. **Bỏ `unlock()` khi gặp exception.** Luôn dùng `try/finally`. Việc quên unlock có thể làm mọi thread khác chờ vô hạn.
5. **Đặt I/O, callback không kiểm soát hoặc `Thread.sleep` bên trong lock.** Giữ lock lâu, tăng tail latency và rủi ro deadlock/reentrancy.
6. **Nhầm thread `BLOCKED` với mọi kiểu chờ đồng bộ.** `ReentrantLock` thường park thread; xem stack và JFR thay vì chỉ lọc trạng thái `BLOCKED`.
7. **Kết luận từ một thread dump hoặc benchmark đơn lẻ.** Contention thay đổi theo tải; thu nhiều mẫu, dùng profiler và so sánh thống kê.
8. **Thay lock bằng atomics mà quên invariant nhiều biến.** Có thể nhanh hơn nhưng sai dữ liệu; tính đúng đắn luôn đứng trước tối ưu.
9. **Dùng busy-spin `while (!lock.tryLock()) { }` vô hạn.** Lãng phí CPU, gây áp lực cạnh tranh và làm các thread khác khó chạy; sử dụng blocking lock, timeout hoặc backoff thích hợp.
10. **Lẫn lộn starvation với deadlock.** Starvation có thể chỉ ảnh hưởng một thread trong khi hệ thống vẫn tiến triển; deadlock là chu kỳ chờ không thể tự phá.
11. **Tăng thread vô hạn khi throughput giảm.** Nếu lock là điểm nghẽn tuần tự, thêm thread thường tăng chờ và chuyển ngữ cảnh.
12. **Tắt toàn bộ cơ chế bảo vệ để lấy hiệu năng.** Race condition và dữ liệu sai khó phát hiện hơn vài microsecond tiết kiệm được.

## 12. Checklist quyết định và bài tập

Khi gặp latency cao nghi do lock, hãy lần lượt tự hỏi:

1. Lock nào bị tranh chấp? Có dấu vết từ thread dump/JFR hay chỉ là giả định?
2. Bao nhiêu phần trăm thời gian nằm trong critical section và chờ lock?
3. Có thể chuyển I/O/tính toán/callback ra ngoài lock không?
4. Có thể chia state, batch cập nhật hoặc dùng một primitive phù hợp hơn không?
5. Nếu vẫn cần một lock chung, yêu cầu của hệ thống là throughput cao nhất hay tiến triển tương đối công bằng?
6. Có đoạn code dùng `tryLock()` không timeout làm phá giả định fairness?
7. Thử nghiệm fair/nonfair ở tải thật cho kết quả throughput, p95/p99 và tiến triển từng worker như thế nào?
8. Chương trình có đường timeout, interrupt và cleanup để tránh giữ lock ngoài ý muốn không?

**Bài tập thực hành:** mở rộng `LockContentionDemo`: mỗi worker đo tổng thời gian chờ từ trước `lock.lock()` đến ngay sau khi lấy lock, đếm số lần tiến triển, rồi chạy với số thread khác nhau. Không in phép đo từ mỗi vòng lặp (I/O sẽ làm sai kết quả); tổng hợp sau khi tất cả worker kết thúc. So sánh fair/nonfair trên nhiều lần chạy và diễn giải cả throughput lẫn sự chênh lệch giữa các worker. Đừng xem thứ tự in ra ở một lần chạy là bảo đảm API.

## 13. Ghi nhớ

- **Contention:** nhiều thread cạnh tranh cùng lock, gây chờ và giới hạn song song.
- **Starvation:** một thread ít hoặc không được tiến triển dù các thread khác vẫn làm việc.
- **Fairness:** chính sách giảm khả năng thread chờ lâu bị chen ngang; `ReentrantLock(true)` ưu tiên người chờ lâu khi tranh chấp nhưng không bảo đảm lịch chạy CPU hay thời gian chờ tối đa.
- **Trade-off:** fairness có thể cải thiện phân phối cơ hội lấy lock, nhưng tăng chi phí chuyển giao và giảm throughput.
- **Ưu tiên thực tế:** kiểm chứng tính đúng đắn → đo contention → giảm vùng khóa/chia sẻ state → cân nhắc fair lock khi có yêu cầu tiến triển và số liệu ủng hộ.

**Tài liệu Java API:**

- [`ReentrantLock` — Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html)
- [`ReentrantReadWriteLock` — Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.html)
- [`StampedLock` — Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/StampedLock.html)
- [`ThreadMXBean` — Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html)
- [`Semaphore` — Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Semaphore.html)