# Condition, semaphore và primitive đồng bộ tương thích với virtual thread

Virtual thread trong Java 21 có thể chờ trên nhiều primitive đồng bộ tiêu chuẩn mà không cần giữ một platform thread trong suốt thời gian chờ. Các API như `ReentrantLock` kết hợp `Condition`, `Semaphore`, `CountDownLatch` và `BlockingQueue` phù hợp để phối hợp tác vụ blocking. Khi virtual thread phải chờ, các primitive này thường park virtual thread để carrier thread có thể chạy virtual thread khác.

Điều đó không có nghĩa mọi cách đồng bộ đều có hành vi giống nhau. Cần hiểu primitive nào phù hợp với bài toán, cách giải phóng tài nguyên, cách xử lý interruption và giới hạn pinning của runtime Java 21. Đặc biệt, không nên giữ monitor hoặc lock trong lúc thực hiện I/O lâu, vì điều đó có thể làm giảm khả năng mở rộng của ứng dụng.

## 1. Virtual thread chờ mà không chiếm carrier thread

Virtual thread được lập lịch trên các platform thread gọi là carrier thread. Khi virtual thread thực hiện một thao tác blocking được JDK hỗ trợ, runtime có thể park virtual thread và unmount nó khỏi carrier. Carrier thread sau đó có thể chạy một virtual thread khác.

Các primitive trong `java.util.concurrent` như `Semaphore`, `CountDownLatch`, `BlockingQueue` và các lock dựa trên `AbstractQueuedSynchronizer` sử dụng cơ chế park/unpark để chờ và đánh thức thread. Vì vậy, khi virtual thread chờ permit, chờ latch, chờ queue hoặc chờ `Condition`, nó thường có thể nhường carrier thay vì giữ carrier trong trạng thái chờ.

Ví dụ, nhiều virtual thread có thể cùng chờ một semaphore:

```java
Semaphore slots = new Semaphore(10);

void callService() throws InterruptedException {
    slots.acquire();
    try {
        invokeRemoteService();
    } finally {
        slots.release();
    }
}
```

Nếu đã có 10 task giữ permit, virtual thread tiếp theo chờ ở `acquire()`. Khi một task gọi `release()`, một thread đang chờ có thể được đánh thức để tiếp tục. Việc chờ này không đồng nghĩa với việc một platform thread phải nằm yên chờ permit.

Dù vậy, các virtual thread đang chờ vẫn tồn tại và tiêu thụ bộ nhớ cùng trạng thái tác vụ. Nếu ứng dụng tạo lượng công việc không giới hạn, số virtual thread chờ vẫn có thể quá lớn. Khả năng unmount không thay thế giới hạn concurrency, admission control hoặc backpressure.

## 2. Condition phối hợp dựa trên một điều kiện dùng chung

`Condition` thuộc `java.util.concurrent.locks` và được tạo từ một đối tượng `Lock`. Nó cho phép một thread tạm dừng cho đến khi một điều kiện về trạng thái dùng chung có thể được thỏa mãn.

Một lock có thể tạo nhiều condition riêng, ví dụ một condition cho biết buffer không rỗng và một condition cho biết buffer chưa đầy. Cách này giúp mô hình hóa producer-consumer rõ ràng hơn so với việc dùng một tín hiệu chung cho nhiều trạng thái.

Các phương thức quan trọng:

| Phương thức | Ý nghĩa |
|---|---|
| `await()` | Giải phóng lock và chờ được signal hoặc bị interrupt |
| `awaitNanos(nanos)` | Chờ có giới hạn thời gian và trả về thời gian còn lại |
| `await(timeout, unit)` | Chờ tối đa một khoảng thời gian, trả về kết quả có đạt tín hiệu trước timeout hay không |
| `signal()` | Đánh thức một thread đang chờ trên condition |
| `signalAll()` | Đánh thức tất cả thread đang chờ trên condition |

Thread phải giữ lock tương ứng khi gọi `await()`, `signal()` hoặc `signalAll()`. Nếu không sở hữu lock theo yêu cầu của implementation, thao tác có thể ném `IllegalMonitorStateException`.

### Ví dụ buffer một phần tử

```java
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.Lock;
import java.util.concurrent.locks.ReentrantLock;

final class OneSlotBuffer<T> {
    private final Lock lock = new ReentrantLock();
    private final Condition notEmpty = lock.newCondition();
    private final Condition notFull = lock.newCondition();

    private T value;
    private boolean occupied;

    void put(T item) throws InterruptedException {
        lock.lockInterruptibly();
        try {
            while (occupied) {
                notFull.await();
            }

            value = item;
            occupied = true;
            notEmpty.signal();
        } finally {
            lock.unlock();
        }
    }

    T take() throws InterruptedException {
        lock.lockInterruptibly();
        try {
            while (!occupied) {
                notEmpty.await();
            }

            T result = value;
            value = null;
            occupied = false;
            notFull.signal();
            return result;
        } finally {
            lock.unlock();
        }
    }
}
```

Trong ví dụ:

- Producer gọi `put()`. Nếu buffer đang có dữ liệu, producer chờ trên `notFull`.
- Consumer gọi `take()`. Nếu buffer rỗng, consumer chờ trên `notEmpty`.
- Khi producer thêm dữ liệu, nó gọi `notEmpty.signal()` để đánh thức một consumer.
- Khi consumer lấy dữ liệu, nó gọi `notFull.signal()` để đánh thức một producer.

Vòng lặp `while` là bắt buộc về mặt thiết kế. Một thread có thể thức dậy do spurious wakeup, do một thread khác đã thay đổi trạng thái trước khi nó lấy lại lock, hoặc do nhiều thread cùng được đánh thức. Sau khi thức dậy và lấy lại lock, thread phải kiểm tra điều kiện một lần nữa.

### await() nhả lock và lấy lại lock

Khi gọi `await()`, thread giải phóng lock liên kết với condition và chuyển sang trạng thái chờ. Khi được signal hoặc bị interrupt, nó phải lấy lại lock trước khi `await()` trả về hoặc ném `InterruptedException`.

Với `ReentrantLock`, cơ chế chờ của condition dựa trên cơ chế park/unpark. Virtual thread đang chờ có thể unmount khỏi carrier. Đoạn code giữ lock trước khi gọi `await()` vẫn cần ngắn và không được giữ thêm lock không cần thiết.

### signal() và signalAll()

`signal()` đánh thức một thread chờ; `signalAll()` đánh thức tất cả thread đang chờ trên condition đó. Chọn phương thức nào phụ thuộc vào invariant và số lượng thread có thể tiếp tục:

- Dùng `signal()` khi một thay đổi trạng thái chỉ cho phép một waiter tiến lên, và một waiter được đánh thức là đủ để tiếp tục tiến trình.
- Dùng `signalAll()` khi nhiều waiter có thể đủ điều kiện sau một thay đổi hoặc khi cần để tất cả waiter tự kiểm tra lại điều kiện.

Đánh thức thread không có nghĩa điều kiện đã chắc chắn đúng khi thread đó chạy tiếp. Thread phải lấy lại lock và kiểm tra predicate trong vòng lặp.

## 3. Semaphore giới hạn số tác vụ đi vào vùng tài nguyên

`Semaphore` quản lý một số lượng permit. Task phải lấy permit trước khi vào vùng công việc bị giới hạn và trả permit sau khi hoàn thành. Đây là primitive phù hợp để giới hạn số thao tác đồng thời tới database, HTTP service hoặc tài nguyên có capacity hữu hạn.

```java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

final class RemoteServiceGate {
    private final Semaphore permits = new Semaphore(20);

    String invoke() throws Exception {
        if (!permits.tryAcquire(100, TimeUnit.MILLISECONDS)) {
            throw new IllegalStateException("Service is busy");
        }

        try {
            return callRemoteService();
        } finally {
            permits.release();
        }
    }
}
```

Tối đa 20 task có thể giữ permit và gọi dịch vụ cùng lúc. Task không lấy được permit trong 100 ms có thể bị từ chối hoặc chuyển sang fallback theo chính sách ứng dụng.

Các phương thức thường dùng:

- `acquire()`: chờ đến khi lấy được permit hoặc bị interrupt.
- `acquireUninterruptibly()`: chờ không phản hồi interruption; chỉ dùng khi hợp đồng tác vụ thực sự yêu cầu.
- `tryAcquire()`: thử lấy permit ngay, không chờ.
- `tryAcquire(timeout, unit)`: chờ có giới hạn thời gian.
- `release()`: trả permit để task khác có thể tiếp tục.

Semaphore không theo dõi quyền sở hữu permit theo thread. Một thread khác vẫn có thể gọi `release()`. Vì vậy, ứng dụng phải tự bảo đảm mỗi permit được trả đúng số lần; trả thừa permit làm tăng capacity hiệu dụng ngoài dự kiến.

Có thể tạo semaphore công bằng bằng `new Semaphore(permits, true)`. Chế độ fair phục vụ waiter theo thứ tự FIFO trong các điểm chọn hàng đợi được semaphore bảo đảm, nhưng thường có chi phí throughput. `tryAcquire()` không có timeout không tuân thủ fairness và có thể lấy permit ngay cả khi waiter khác đang chờ. Chỉ bật fairness khi thứ tự chờ là yêu cầu thực tế.

### Semaphore không phải rate limiter

Semaphore giới hạn số tác vụ đang giữ permit cùng lúc. Nếu mỗi thao tác hoàn tất rất nhanh, một semaphore 10 permit vẫn có thể cho phép hàng nghìn request bắt đầu trong một giây. Muốn giới hạn số request theo thời gian, cần thêm rate limiter hoặc cơ chế quota.

Không giữ permit trong lúc thực hiện công việc không thuộc dependency bị giới hạn. Hãy lấy permit ngay trước thao tác cần bảo vệ và trả permit ngay khi thao tác đó kết thúc.

## 4. CountDownLatch chờ một nhóm tác vụ hoàn tất

`CountDownLatch` cho phép một hoặc nhiều thread chờ cho đến khi bộ đếm về 0. Mỗi task hoàn tất gọi `countDown()`; thread điều phối gọi `await()`.

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class BatchExample {
    public static void main(String[] args) throws InterruptedException {
        int taskCount = 3;
        CountDownLatch done = new CountDownLatch(taskCount);

        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            for (int i = 0; i < taskCount; i++) {
                int taskId = i;
                executor.submit(() -> {
                    try {
                        process(taskId);
                    } finally {
                        done.countDown();
                    }
                });
            }

            done.await();
            System.out.println("All tasks reached completion");
        }
    }
}
```

`finally` bảo đảm bộ đếm giảm ngay cả khi task kết thúc do exception. Tuy nhiên, latch chỉ báo rằng task đã kết thúc phần xử lý được bọc; nó không tự truyền exception từ các Future về thread đang chờ. Nếu cần thu thập lỗi, hãy giữ Future và gọi `get()`, hoặc dùng một cơ chế kết hợp kết quả phù hợp.

`CountDownLatch` là one-shot: sau khi bộ đếm về 0, nó không thể reset để dùng cho đợt công việc mới. Nếu cần đồng bộ nhiều vòng lặp, cân nhắc `CyclicBarrier` hoặc `Phaser`.

Virtual thread chờ ở `await()` có thể park và nhường carrier. Điều này giúp thread điều phối có thể chờ mà không chiếm một carrier chỉ để ngủ.

## 5. BlockingQueue và hàng đợi có capacity

`BlockingQueue` cung cấp thao tác chờ khi queue rỗng hoặc đầy. Với queue có giới hạn, producer bị chặn khi không còn chỗ và consumer bị chặn khi chưa có phần tử. Đây là một cách tạo backpressure đơn giản giữa hai nhóm tác vụ.

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

BlockingQueue<Job> queue = new ArrayBlockingQueue<>(100);

// Producer
void publish(Job job) throws InterruptedException {
    queue.put(job);
}

// Consumer
Job nextJob() throws InterruptedException {
    return queue.take();
}
```

`put()` chờ cho đến khi có chỗ; `take()` chờ cho đến khi có phần tử. Các thao tác chờ này trong implementation chuẩn của JDK tương thích với virtual thread. Queue giới hạn 100 phần tử giúp lượng công việc đang chờ không tăng vô hạn.

Khi không muốn chờ vô thời hạn, có thể dùng:

- `offer(item)`: thử thêm ngay, trả `false` nếu queue đầy.
- `offer(item, timeout, unit)`: chờ có giới hạn.
- `poll()`: lấy ngay nếu có phần tử, nếu không trả `null`.
- `poll(timeout, unit)`: chờ có giới hạn để lấy phần tử.

Chọn chính sách khi queue đầy: từ chối request, trả lỗi overload, giảm tốc độ producer hoặc lưu vào hệ thống bền vững. Không nên chuyển sang một queue không giới hạn chỉ để tránh producer bị block, vì điều đó có thể chuyển overload thành vấn đề bộ nhớ.

## 6. CyclicBarrier và Phaser cho phối hợp theo pha

Khi nhiều task cần chờ nhau tới cùng một điểm trước khi tiếp tục, có thể dùng barrier thay vì tự quản lý cờ trạng thái.

`CyclicBarrier` cho phép một nhóm thread chờ tại barrier cho đến khi đủ số bên tham gia. Barrier có thể tái sử dụng cho các vòng tiếp theo.

```java
import java.util.concurrent.CyclicBarrier;

CyclicBarrier barrier = new CyclicBarrier(3);

void runPhase() throws Exception {
    loadPartition();
    barrier.await();
    calculateFromAllPartitions();
}
```

Ví dụ, ba task tải ba phân vùng dữ liệu độc lập. Mỗi task chờ tại barrier; chỉ khi cả ba đến nơi, chúng mới tiếp tục tính toán giai đoạn kế tiếp. Nếu một thread đang chờ bị interrupt, hết timeout hoặc barrier action thất bại, barrier chuyển sang trạng thái broken và các bên chờ có thể nhận `BrokenBarrierException`. Nếu một task thất bại trước khi gọi `await()`, barrier không tự biết việc đó; các task còn lại có thể chờ mãi nếu không đặt timeout hoặc có cơ chế hủy phối hợp.

`Phaser` phù hợp hơn khi số bên tham gia thay đổi theo thời gian hoặc cần nhiều phase. Các task đăng ký tham gia, hoàn tất một phase bằng `arrive()` hoặc `arriveAndAwaitAdvance()`, rồi chuyển sang phase tiếp theo. Chọn barrier theo đúng cấu trúc phối hợp; không dùng chúng để thay thế semaphore giới hạn tài nguyên.

Các phương thức chờ của `CyclicBarrier` và `Phaser` dựa trên cơ chế đồng bộ của JDK và có thể được dùng từ virtual thread. Vẫn cần xác định timeout, interruption và cách xử lý khi một bên tham gia không bao giờ đến barrier.

## 7. ReentrantLock và synchronized trong Java 21

Cả `synchronized` và `ReentrantLock` đều bảo vệ vùng trạng thái dùng chung, nhưng có khác biệt về API và hành vi khi virtual thread bị block.

`ReentrantLock` cung cấp:

- `lockInterruptibly()` để chờ lấy lock và có thể phản hồi interrupt.
- `tryLock()` để thử lấy lock ngay.
- `tryLock(timeout, unit)` để chờ lấy lock có giới hạn.
- Nhiều `Condition` để chờ các predicate khác nhau.
- `unlock()` tường minh, thường được đặt trong `finally`.

Ví dụ:

```java
Lock lock = new ReentrantLock();

void update() throws InterruptedException {
    lock.lockInterruptibly();
    try {
        updateSharedState();
    } finally {
        lock.unlock();
    }
}
```

Trong Java 21, virtual thread bị pin vào carrier khi đang thực thi trong một vùng `synchronized` hoặc native method. Pinning trở thành vấn đề về khả năng mở rộng khi virtual thread thực hiện thao tác blocking trong lúc bị pin: nó không thể unmount khỏi carrier trong thời gian đó. Nếu vùng synchronized chứa I/O blocking hoặc thao tác chờ lâu, carrier có thể bị giữ lại.

Vì vậy, với runtime Java 21, nên giữ vùng `synchronized` ngắn và không thực hiện I/O hoặc chờ dependency bên trong monitor. Nếu cần chờ lock có thể bị tranh chấp hoặc chờ condition trong thời gian dài, `ReentrantLock` và `Condition` thường là lựa chọn phù hợp hơn vì cơ chế park/unpark cho phép virtual thread nhường carrier.

Không cần thay tất cả `synchronized` bằng `ReentrantLock`. Các vùng synchronized ngắn, không block thường vẫn đơn giản và phù hợp. Chỉ chọn lock khác khi cần timeout, interruptible acquisition, nhiều condition hoặc cần tránh pinning trong workload Java 21.

Lưu ý về phiên bản: phần pinning ở đây mô tả runtime Java 21. JDK 24 đã cải thiện việc đồng bộ monitor để virtual thread không còn bị pin chỉ vì block trong synchronized theo cách của Java 21. Khi ứng dụng chạy trên JDK mới hơn, hãy kiểm tra hành vi theo phiên bản runtime thực tế thay vì áp dụng nguyên xi giới hạn pinning của Java 21.

## 8. Những thao tác cần tránh khi dùng virtual thread

Một số thiết kế có thể làm mất lợi ích của virtual thread hoặc tạo contention:

- Giữ monitor hoặc lock trong lúc gọi HTTP, truy vấn database hoặc chờ một dịch vụ từ xa.
- Dùng một lock toàn cục cho mọi request dù các request có thể xử lý độc lập.
- Giữ semaphore permit trong toàn bộ request dù chỉ một đoạn ngắn cần truy cập dependency.
- Dùng queue không giới hạn và tạo task nhanh hơn tốc độ consumer.
- Gọi `await()` nhưng không kiểm tra lại predicate trong vòng `while`.
- Bỏ qua `InterruptedException` hoặc không trả permit/unlock trong `finally`.
- Dùng `CountDownLatch` như primitive tái sử dụng cho nhiều vòng.
- Dùng `CyclicBarrier` hoặc `Phaser` cho bài toán chỉ cần giới hạn số thao tác đồng thời.

Một virtual thread có thể bị park mà không giữ carrier, nhưng nếu nó đang giữ lock, permit, connection hoặc transaction thì tài nguyên đó vẫn bị giữ. Tối ưu đồng bộ không chỉ là giải phóng carrier; còn phải rút ngắn thời gian giữ tài nguyên dùng chung.

## 9. Quan sát pinning và điểm nghẽn

Trong Java 21, Java Flight Recorder có event `jdk.VirtualThreadPinned` để ghi nhận trường hợp virtual thread bị pin trong một khoảng thời gian đủ dài theo ngưỡng cấu hình. Có thể dùng JFR để xác định stack trace và vị trí code gây pinning.

Khi điều tra hiệu năng, theo dõi đồng thời:

| Chỉ số | Điều cần quan sát |
|---|---|
| Số virtual thread đang chạy/chờ | Phát hiện lượng task tích tụ |
| Carrier utilization | Xem carrier có bị giữ bởi blocking hoặc pinning hay không |
| Thời gian chờ lock | Xác định lock contention |
| Semaphore permit usage | Kiểm tra giới hạn dependency có thường xuyên hết permit |
| Queue depth | Đo lượng công việc đang chờ |
| Request latency và timeout | Phát hiện ảnh hưởng đến người dùng |
| Connection pool usage | Xác định tài nguyên ngoài JVM đang bị bão hòa |

Không tăng số carrier thread chỉ để che một vùng code bị pinning kéo dài. Trước hết, xác định đoạn blocking, rút ngắn vùng giữ monitor hoặc chuyển sang primitive phù hợp. Sau thay đổi, đo lại bằng workload đại diện.

## 10. Chọn primitive theo bài toán

| Nhu cầu | Primitive phù hợp |
|---|---|
| Chờ một điều kiện về trạng thái dùng chung | `ReentrantLock` + `Condition` |
| Giới hạn số thao tác đồng thời | `Semaphore` |
| Chờ một nhóm task hoàn tất một lần | `CountDownLatch` |
| Producer-consumer với hàng đợi có capacity | `BlockingQueue` |
| Nhiều task đồng bộ tại cùng một phase | `CyclicBarrier` |
| Nhiều phase với số bên tham gia có thể thay đổi | `Phaser` |
| Bảo vệ vùng cập nhật ngắn và đơn giản | `synchronized` hoặc `Lock` |

Hãy chọn primitive theo invariant cần bảo vệ, số lượng bên tham gia, khả năng hủy, timeout và nhu cầu tái sử dụng. Không chọn primitive chỉ vì nó “tương thích virtual thread”; điều quan trọng là nó thể hiện đúng mô hình phối hợp và không giữ tài nguyên lâu hơn cần thiết.

## Kết luận

Trong Java 21, `Condition`, `Semaphore`, `CountDownLatch`, `BlockingQueue`, `CyclicBarrier` và `Phaser` là các primitive hữu ích để phối hợp virtual thread. Các thao tác chờ dựa trên cơ chế park/unpark của JDK thường cho phép virtual thread nhường carrier trong lúc chờ. Dùng `Condition` với predicate trong vòng `while`, trả semaphore permit và lock trong `finally`, giới hạn queue và xử lý interruption rõ ràng. Với Java 21, tránh blocking lâu trong vùng `synchronized` vì có thể pin carrier; khi cần chờ lâu, cân nhắc `ReentrantLock` và `Condition`.

## Tài liệu tham khảo

- [Java SE 21 API — Condition](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/Condition.html)
- [Java SE 21 API — ReentrantLock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html)
- [Java SE 21 API — Semaphore](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Semaphore.html)
- [Java SE 21 API — CountDownLatch](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [Java SE 21 API — BlockingQueue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/BlockingQueue.html)
- [Java SE 21 API — CyclicBarrier](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CyclicBarrier.html)
- [Java SE 21 API — Phaser](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Phaser.html)
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444)
- [JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491)
