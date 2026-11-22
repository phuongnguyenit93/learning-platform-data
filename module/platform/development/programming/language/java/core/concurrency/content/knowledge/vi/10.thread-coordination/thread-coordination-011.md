# Tránh busy waiting bằng blocking primitives trong Java

## 1. Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích **busy waiting**, **spinning**, **blocking wait** và vì sao vòng lặp kiểm tra liên tục thường lãng phí CPU, gây contention và có thể lỗi visibility.
- Chọn đúng công cụ Java theo điều kiện đang chờ: **CountDownLatch**, **BlockingQueue**, **Semaphore**, **Future.get()**, **Condition.await()** và các phương thức chờ kết thúc thread.
- Phân biệt **tín hiệu một lần**, **trao dữ liệu producer–consumer**, **giới hạn tài nguyên**, **chờ kết quả** và **chờ predicate có thể thay đổi**.
- Viết các chương trình Java 17+ sử dụng blocking primitives, kiểm soát đúng **interruption**, **timeout**, **cleanup** và **happens-before**.
- Nhận diện tình huống **blocking khi giữ lock**, deadlock, lost notification, lựa chọn nhầm queue hoặc timeout, và việc thay busy loop bằng sleep mà chưa có giao thức đồng bộ.
- Biết giới hạn của blocking: không hứa thời điểm thức dậy chính xác, không tự đồng nghĩa tác vụ nghiệp vụ thành công, và không tự xử lý kết quả đã commit bên ngoài JVM.

Bài thuộc chủ đề **Phối hợp luồng** trong **Java concurrency nói chung**. Các cơ chế điều phối riêng của Spring thuộc chương khác.

## 2. Busy waiting là gì?

**Busy waiting** là cách một thread liên tục kiểm tra điều kiện mà hầu như không có việc hữu ích để làm, thường bằng một vòng lặp:

~~~java
// Mã minh họa lỗi: ready là field thường được chia sẻ giữa các thread.
while (!ready) {
    // Kiểm tra liên tục, tiêu tốn CPU.
}
process();
~~~

Đoạn trên không phải chương trình độc lập: **ready** và **process()** là thành phần giả định.

Những vấn đề nổi bật:

1. **Tốn CPU**: thread vẫn thường xuyên được scheduler cho chạy chỉ để đọc lại cùng điều kiện.
2. **Gây tranh chấp cache/memory bus**: nhiều thread đọc một cờ chung liên tục có thể gây áp lực không cần thiết.
3. **Thiếu bảo đảm visibility** nếu ready là field thông thường: không có quan hệ happens-before, thread chờ có thể không thấy cập nhật từ thread khác; trình biên dịch/JIT còn có quyền tối ưu dựa trên JMM.
4. **Khó kiểm soát thời gian dừng**: nếu producer thất bại và không phát tín hiệu, vòng lặp không có timeout hoặc chính sách hủy rõ ràng.
5. **Tăng tải khi nhiều thread chờ**: polling theo chu kỳ ngắn có thể làm hệ thống bận nhưng không tiến triển.

Một vòng **while (!ready) {}** chỉ nên tồn tại trong những thuật toán spinning có thiết kế chuyên biệt, đã giải quyết memory ordering, chi phí CPU, fairness và phương án fallback. Nó không phải mặc định cho chờ sự kiện trong ứng dụng Java.

### Thay bằng volatile có đủ không?

~~~java
// Mã minh họa: volatile xử lý visibility của cờ, không xử lý lãng phí CPU.
private volatile boolean ready;

// Thread chờ:
while (!ready) {
    Thread.onSpinWait();
}
~~~

**Thread.onSpinWait()** chỉ là một *hint* rằng thread đang trong vòng spin; JVM/CPU có thể dùng hint để cải thiện cách thực thi. Nó **không block**, **không tự phát hiện tín hiệu** và **không đảm bảo thời điểm thức dậy hoặc tiến độ**. Volatile giúp nhìn thấy cập nhật, nhưng vòng lặp vẫn có thể tiêu tốn CPU.

## 3. Blocking primitive khác busy loop ở đâu?

Một **blocking primitive** cho phép thread **chờ theo một điều kiện/sự kiện đã được API quản lý**, thay vì tự đọc trạng thái chung liên tục. Hợp đồng API quyết định khi nào chờ được giải phóng, quan hệ bộ nhớ nào được thiết lập, và cách timeout/interrupt hoạt động.

Ví dụ chờ đúng một tín hiệu:

~~~java
// Mã minh họa trong phương thức khai báo throws InterruptedException:
CountDownLatch done = new CountDownLatch(1);

// Worker sau khi hoàn thành bước liên quan sẽ gọi done.countDown().
// Thread chờ:
done.await();
~~~

Ở đây **CountDownLatch** là kiểu thuộc java.util.concurrent (cần import). Đoạn minh họa không có main() và không tự chạy; ví dụ hoàn chỉnh nằm ở phần 6.

Cách hiểu hợp đồng: khi count giảm về 0, các thread đang await được phép tiếp tục. Runtime không phải thực hiện một vòng Java **while (latch.getCount() > 0)** tự viết liên tục. Cách triển khai nội bộ của primitive có thể có bước ngắn tối ưu, nhưng về mặt sử dụng đây là **blocking wait**, không phải busy-wait do ứng dụng tự làm.

### Sơ đồ

~~~text
Busy waiting:
  reader -> check -> check -> check -> check -> ... -> check -> tiếp tục
                  CPU có thể hoạt động gần như liên tục

Blocking:
  waiter -> await() -> [đợi tín hiệu / điều kiện / kết quả]
  producer ----------------------> signal / put / complete
  waiter -> được phép tiếp tục -> thực hiện bước tiếp theo
~~~

**Blocking không có nghĩa “chắc chắn chờ bằng 0 CPU” hoặc “tỉnh dậy ngay lập tức”.** Chi tiết phụ thuộc JVM, hệ điều hành, scheduler và API. Điểm chính là ứng dụng không tự duy trì vòng thăm dò điều kiện liên tục.

## 4. Chọn đúng primitive theo sự kiện đang đợi

| Nhu cầu | Primitive Java thường phù hợp | Điểm quan trọng |
| --- | --- | --- |
| Đợi N công việc báo xong | **CountDownLatch** | Đếm về 0; không reset |
| Các thread gặp nhau tại rào cản nhiều giai đoạn | **CyclicBarrier** hoặc **Phaser** | Có giao thức từng pha, xử lý broken barrier |
| Producer gửi phần tử cho consumer | **BlockingQueue** | **put/take** vừa truyền dữ liệu vừa phối hợp |
| Giới hạn số hoạt động đồng thời | **Semaphore** | Quản lý permit; acquire/release đúng quyền nghiệp vụ |
| Đợi một kết quả tính toán bất đồng bộ | **Future.get()** | Có giá trị, lỗi hoặc trạng thái hủy |
| Đợi một thread cụ thể kết thúc | **Thread.join()** | Kết thúc thread không đồng nghĩa thành công nghiệp vụ |
| Đợi predicate dưới explicit lock | **Condition.await()/signalAll()** | Luôn kiểm tra predicate trong while |
| Đợi predicate dưới intrinsic monitor | **Object.wait()/notifyAll()** | Phải sở hữu đúng monitor, luôn while |
| Đợi một permit park/unpark thấp tầng | **LockSupport.park()/unpark()** | Mức thấp, cần tự thiết kế predicate và unpark chính xác |

Đừng thay **BlockingQueue** bằng **CountDownLatch** chỉ vì cả hai đều có phương thức chờ: latch không mang phần tử. Đừng thay **Semaphore** bằng một boolean nếu bài toán thực sự yêu cầu tối đa K người vào cùng lúc.

## 5. Ví dụ đối chiếu: polling, sleep và block

### 5.1. Busy loop

~~~java
// Anti-pattern: cờ ordinary không có giao thức visibility.
while (!finished) {
    // spin
}
~~~

Không bảo đảm thấy finished=true; tiêu thụ CPU.

### 5.2. Polling với sleep

~~~java
// Minh họa: finished cần cơ chế visibility như volatile hoặc atomic.
while (!finished) {
    Thread.sleep(50);
}
~~~

Mẫu này **không còn đốt CPU liên tục** trong thời gian ngủ, nhưng vẫn là **periodic polling**:

- Có **độ trễ bổ sung** giữa lúc finished được đặt true và lần kiểm tra tiếp theo.
- Có chi phí thức dậy nhiều lần chỉ để kiểm tra.
- **Thread.sleep() không tự tạo happens-before** cho finished; cần volatile/atomic/lock phù hợp.
- Nó không có kênh báo lỗi hoặc biết producer đã chết mà chưa cập nhật cờ.
- Có thể bị InterruptedException và cần xử lý phù hợp.

Nếu API nguồn sự kiện cho phép **signal hoặc blocking wait**, hãy dùng nó. Polling có thể chấp nhận được khi tích hợp một API không hỗ trợ signal, với khoảng kiểm tra và deadline được chọn có chủ đích.

### 5.3. Đợi tín hiệu

~~~java
// Minh họa: done là một CountDownLatch đã được chia sẻ an toàn.
done.await();
~~~

Thread ngủ chờ sự kiện thay vì tự lặp kiểm tra. Giao thức completion do primitive quản lý; cần chắc chắn producer **luôn countDown() đúng lúc**, kể cả khi có lỗi nếu contract yêu cầu mọi waiter không bị kẹt.

## 6. Ví dụ 1: CountDownLatch thay vòng spin

Một chương trình chờ một worker báo rằng kết quả sẵn sàng. Ta chủ động dùng latch làm mốc công bố kết quả và chờ bằng await().

Tệp **LatchInsteadOfSpinDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class LatchInsteadOfSpinDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch ready = new CountDownLatch(1);
        AtomicInteger result = new AtomicInteger();

        Thread worker = new Thread(() -> {
            try {
                result.set(6 * 7);
            } finally {
                ready.countDown();
            }
        }, "worker");

        worker.start();
        ready.await();
        System.out.println("result = " + result.get());
        worker.join();
    }
}
~~~

~~~bash
javac -encoding UTF-8 LatchInsteadOfSpinDemo.java
java LatchInsteadOfSpinDemo
~~~

Stdout:

~~~text
result = 42
~~~

**Giải thích:**

1. Worker tính giá trị rồi gán vào AtomicInteger trước khi countDown.
2. **CountDownLatch.await()** của main chờ cho count về 0; không có vòng polling tự viết.
3. Với CountDownLatch, các hành động trước countDown của producer **happens-before** những hành động sau khi await thành công của consumer. AtomicInteger còn cung cấp hợp đồng bộ nhớ riêng của biến atomic.
4. **join()** ở cuối giúp thu hồi/đợi thread worker kết thúc; bản thân latch đã đủ để quan sát kết quả được công bố **trước countDown**, không nhất thiết bảo đảm toàn bộ code sau countDown đã kết thúc.
5. Nếu worker có thể thất bại, ứng dụng thật cần lưu **kết quả hoặc exception** và quy định latch báo “đã kết thúc giai đoạn” hay “đã thành công”. Latch về 0 **không tự nói nghiệp vụ thành công**.

Trong ví dụ, lỗi unchecked trong phép toán không xảy ra, nên đầu ra xác định.

### Latch có thể dùng nhiều người đợi

Với **new CountDownLatch(N)**, N lần countDown làm bộ đếm giảm đến 0. N có thể là số lượng worker hoặc số giai đoạn được thỏa. **countDown khi đã bằng 0 không làm số đếm âm**. Một latch sau khi về 0 sẽ tiếp tục cho các await sau đi qua, **không reset**; muốn vòng đời nhiều pha cần primitive khác.

## 7. Timeout: không chờ vô hạn nếu điều kiện có deadline

Hầu hết API đồng bộ hóa có một số overload chờ có timeout:

- **CountDownLatch.await(long, TimeUnit)**: trả boolean, true khi count về 0 trước khi hết chờ, false khi timeout.
- **Future.get(long, TimeUnit)**: trả kết quả hoặc ném TimeoutException; computation **không tự bị hủy** chỉ vì caller hết thời gian chờ.
- **BlockingQueue.poll(long, TimeUnit)**: trả phần tử hoặc null khi hết hạn mà chưa có phần tử.
- **Semaphore.tryAcquire(long, TimeUnit)**: trả true khi lấy permit được, false nếu timeout.
- **Condition.await(long, TimeUnit)**: trả giá trị theo thời gian chờ còn lại; predicate phải tự kiểm tra lại.
- **Thread.join(long)**: trở về khi thread đích kết thúc hoặc hết thời gian chờ; sau join(timeout) không được mặc nhiên coi thread đã chết.

### Ví dụ 2: timed await có kết quả dự đoán được

Tệp **LatchTimeoutDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class LatchTimeoutDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch neverSignaled = new CountDownLatch(1);

        boolean completed =
                neverSignaled.await(5, TimeUnit.MILLISECONDS);

        System.out.println("completed = " + completed);
        System.out.println("remaining = " + neverSignaled.getCount());
    }
}
~~~

~~~bash
javac -encoding UTF-8 LatchTimeoutDemo.java
java LatchTimeoutDemo
~~~

Stdout:

~~~text
completed = false
remaining = 1
~~~

Không thread nào gọi countDown(), nên await có timeout trả false và count còn 1. Timeout cho caller một **đường thoát có kiểm soát**, nhưng latch vẫn chưa hoàn tất. Với tác vụ thật, cần quyết định cảnh báo, retry, tiếp tục chờ, gửi yêu cầu hủy hoặc giải phóng tài nguyên theo policy.

**Không lấy thời gian chờ quá ngắn làm bảo đảm về latency**: JVM, scheduler và timer có sai số/granularity; timeout không phải cam kết thực thi đúng từng mili giây.

## 8. BlockingQueue: chờ phần tử thay vì chờ cờ ready

Bài toán producer–consumer tự nhiên cần **truyền dữ liệu**, không chỉ phát tín hiệu. **BlockingQueue<E>** cung cấp:

- **put(e)**: có thể chờ khi queue bị đầy (với queue có giới hạn).
- **take()**: chờ khi queue trống, trả phần tử khi có dữ liệu.
- **offer(e)**: thử thêm ngay, trả false nếu không thể thêm.
- **offer(e, timeout, unit)**: đợi có giới hạn để thêm.
- **poll()**: lấy ngay hoặc trả null nếu rỗng.
- **poll(timeout, unit)**: đợi có giới hạn để lấy.

**ArrayBlockingQueue** có dung lượng cố định; **LinkedBlockingQueue** có thể được cấu hình dung lượng nhưng constructor không chỉ định capacity dùng giới hạn lớn. Nếu muốn **backpressure** thực sự, xác định capacity thích hợp.

**BlockingQueue không cho phép phần tử null**, vì null thường mang ý nghĩa “không nhận được phần tử”. Nếu cần tín hiệu kết thúc, dùng một message đặc biệt hoặc protocol rõ ràng khác.

### Ví dụ 3: chờ bằng take(), không spin trên isEmpty()

Tệp **BlockingQueueDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class BlockingQueueDemo {
    private static final int END = -1;

    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<Integer> queue =
                new ArrayBlockingQueue<>(2);

        Thread producer = new Thread(() -> {
            try {
                queue.put(1);
                queue.put(2);
                queue.put(3);
                queue.put(END);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "producer");

        producer.start();

        int sum = 0;
        int count = 0;

        while (true) {
            int value = queue.take();
            if (value == END) {
                break;
            }
            sum += value;
            count++;
        }

        producer.join();
        System.out.println("processed = " + count);
        System.out.println("sum = " + sum);
    }
}
~~~

~~~bash
javac -encoding UTF-8 BlockingQueueDemo.java
java BlockingQueueDemo
~~~

Stdout:

~~~text
processed = 3
sum = 6
~~~

**Diễn giải:**

1. Producer đưa ba số vào queue FIFO, rồi đưa **END** để báo hết dữ liệu.
2. Consumer là main. **take()** đợi khi queue trống và tiếp tục khi producer put thêm phần tử; không tự spin trên **isEmpty()**.
3. Capacity 2 giới hạn số phần tử chưa được tiêu thụ; **put()** có thể chờ, tạo backpressure thay vì phát sinh queue vô hạn.
4. Sau END, main join producer rồi in tổng, nên stdout xác định.
5. Ví dụ dùng một producer, một consumer và một sentinel **không trùng giá trị dữ liệu hợp lệ**. Với nhiều producer/consumer, protocol kết thúc cần được thiết kế riêng (ví dụ số sentinel phù hợp hoặc đóng queue theo một giao thức), không thể tùy tiện đưa một END rồi giả định tất cả consumer dừng.

**Memory visibility:** Các hành động của thread trước khi **đưa object vào BlockingQueue** happens-before các hành động của thread khác **sau khi lấy object đó ra**. Nhưng điều đó **không tự biến object mutable thành immutable**: nếu producer vẫn sửa một đối tượng sau khi put, có thể xuất hiện race khi consumer đọc cùng object.

### Anti-pattern: isEmpty() + poll() / sleep()

~~~java
// Mã minh họa lỗi thiết kế, queue là shared queue đã tạo.
while (queue.isEmpty()) {
    Thread.sleep(10);
}
var item = queue.poll();
~~~

Queue có thể đổi ngay sau isEmpty(); item có thể là null khi một consumer khác lấy phần tử trước. Nếu cần chờ phần tử, dùng **take()**. Nếu không được block vô hạn, dùng **poll(timeout, unit)** rồi kiểm tra null.

## 9. Semaphore: chờ quyền truy cập tài nguyên

**Semaphore** quản lý một số lượng **permit**. Chỉ thread lấy đủ permit mới được đi vào phần công việc cần giới hạn concurrency.

- **acquire()**: đợi đến khi có permit, có thể ném InterruptedException.
- **tryAcquire()**: thử ngay, trả boolean.
- **tryAcquire(timeout, unit)**: đợi có giới hạn.
- **release()**: trả permit theo giao thức ứng dụng.

**Semaphore không có ownership theo thread như ReentrantLock**: API cho phép thread khác release permit, và release dư có thể khiến số permit vượt mức dự kiến. Vì vậy chính ứng dụng phải đảm bảo **mỗi lần acquire thành công có một release tương ứng**, trừ khi đang chủ ý thực hiện một giao thức chuyển giao permit.

### Ví dụ 4: giới hạn đồng thời tối đa hai tác vụ

Tệp **SemaphoreLimitDemo.java**:

~~~java
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicInteger;

public class SemaphoreLimitDemo {
    public static void main(String[] args) throws InterruptedException {
        Semaphore slots = new Semaphore(2);
        AtomicInteger active = new AtomicInteger();
        AtomicInteger maximum = new AtomicInteger();
        AtomicInteger completed = new AtomicInteger();

        Runnable work = () -> {
            boolean acquired = false;
            try {
                slots.acquire();
                acquired = true;

                int now = active.incrementAndGet();
                maximum.accumulateAndGet(now, Math::max);

                try {
                    int value = 6 * 7; // Ví dụ xử lý công việc hữu ích.
                    if (value == 42) {
                        completed.incrementAndGet();
                    }
                } finally {
                    active.decrementAndGet();
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            } finally {
                if (acquired) {
                    slots.release();
                }
            }
        };

        Thread[] threads = new Thread[4];
        for (int i = 0; i < threads.length; i++) {
            threads[i] = new Thread(work, "worker-" + i);
            threads[i].start();
        }

        for (Thread worker : threads) {
            worker.join();
        }

        System.out.println("completed = " + completed.get());
        System.out.println("capacity respected = " + (maximum.get() <= 2));
        System.out.println("permits = " + slots.availablePermits());
    }
}
~~~

~~~bash
javac -encoding UTF-8 SemaphoreLimitDemo.java
java SemaphoreLimitDemo
~~~

Stdout:

~~~text
completed = 4
capacity respected = true
permits = 2
~~~

**Vì sao đúng?**

- Mỗi thread phải acquire một permit trước khi tăng active.
- Chỉ tối đa hai thread có thể giữ permit đồng thời; **maximum <= 2** là một bất biến, không cần giả định chính xác maximum bằng 2 trong mọi lịch.
- **active** giảm trong finally sau khi làm việc; **slots.release()** chỉ chạy nếu thread đã acquire thành công.
- Sau khi join cả bốn thread, tất cả permit đã được trả và số task xử lý là 4.

**Cảnh giác:** Nếu catch InterruptedException khi chưa acquire mà vẫn gọi release(), semaphore có thể có **3 permit** thay vì 2 và đánh mất giới hạn. Cơ chế cleanup là một phần bắt buộc của giao thức.

**Fairness:** new Semaphore(permits, true) có chính sách fairness cho các acquisition theo hợp đồng API, nhưng không đảm bảo mỗi thread được CPU công bằng tuyệt đối; các lời gọi **tryAcquire() ngay** có thể vượt hàng theo quy tắc riêng.

## 10. Future.get(): chờ kết quả thay vì hỏi isDone liên tục

Nếu ứng dụng gửi một computation vào **ExecutorService**, **Future<T>** đại diện cho completion và kết quả.

Anti-pattern:

~~~java
// Mã minh họa: future là Future<Integer>.
while (!future.isDone()) {
    // Busy waiting hoặc gọi sleep theo chu kỳ.
}
int answer = future.get();
~~~

Trong khi đó:

~~~java
// Minh họa trong phương thức xử lý checked exceptions.
int answer = future.get(); // Block cho tới completion hoặc lỗi/hủy.
~~~

**Future.get()** có thể:

- Trả giá trị T khi computation hoàn tất bình thường.
- Ném **ExecutionException** khi task ném exception.
- Ném **CancellationException** khi Future đã bị hủy.
- Ném **InterruptedException** nếu thread đang chờ bị ngắt.
- Với overload có timeout, ném **TimeoutException** nếu caller chờ quá hạn; **task vẫn có thể chạy tiếp**.

**isDone() = true không đồng nghĩa thành công**; nó cũng đúng khi thất bại hoặc bị hủy. Nếu cần trạng thái nghiệp vụ, phải diễn giải kết quả/exception theo giao thức ứng dụng.

### Ví dụ 5: đợi Future trả kết quả

Tệp **FutureBlockingDemo.java**:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class FutureBlockingDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            Future<Integer> future = pool.submit(() -> 21 * 2);
            int result = future.get();

            System.out.println("result = " + result);
            System.out.println("done = " + future.isDone());
            System.out.println("cancelled = " + future.isCancelled());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 FutureBlockingDemo.java
java FutureBlockingDemo
~~~

Stdout:

~~~text
result = 42
done = true
cancelled = false
~~~

Caller **không tự polling** mà đợi kết quả qua get(). ExecutorService phải được shutdown để không giữ worker thread sống ngoài ý muốn. **Future.get()** trả kết quả hoặc báo lỗi; đây là hợp đồng ở tầng computation, không định nghĩa transaction nghiệp vụ bên ngoài.

**Đừng giữ monitor/ReentrantLock mà worker cần rồi gọi get()**: caller giữ khóa và đợi worker, worker đợi khóa của caller → có thể deadlock.

## 11. Condition: block khi đợi một predicate có thể đổi nhiều lần

Với **ReentrantLock**, API **Condition** phù hợp khi thread cần chờ **một điều kiện về state chung** và một thread khác cập nhật điều kiện đó. Chọn Condition khi cần logic đa bước mà queue/latch không diễn tả trực tiếp.

Quy tắc:

1. Tạo condition qua **lock.newCondition()**.
2. Caller phải đang giữ **chính lock liên kết** khi gọi await(), signal() hoặc signalAll().
3. Đặt predicate dưới cùng lock; thường dùng **while (!predicate) condition.await()**.
4. **await() nhả lock liên kết khi chờ**, rồi reacquire trước khi tiếp tục.
5. Có thể xảy ra **spurious wakeup**; không dùng if một lần để giả định điều kiện đã đúng.
6. Signal không có nghĩa thread chờ đã chạy ngay: nó còn phải lấy lại lock.

### Ví dụ 6: await khi chưa có điều kiện, signalAll khi sẵn sàng

Tệp **ConditionBlockingDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class ConditionBlockingDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        Condition readyCondition = lock.newCondition();
        boolean[] ready = {false};
        int[] result = {0};
        CountDownLatch started = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            lock.lock();
            try {
                started.countDown();
                while (!ready[0]) {
                    try {
                        readyCondition.await();
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        return;
                    }
                }
                result[0] = 42;
            } finally {
                lock.unlock();
            }
        }, "condition-worker");

        worker.start();
        started.await();

        lock.lock();
        try {
            ready[0] = true;
            readyCondition.signalAll();
        } finally {
            lock.unlock();
        }

        worker.join();

        lock.lock();
        try {
            System.out.println("ready = " + ready[0]);
            System.out.println("result = " + result[0]);
        } finally {
            lock.unlock();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConditionBlockingDemo.java
java ConditionBlockingDemo
~~~

Stdout:

~~~text
ready = true
result = 42
~~~

**Giải thích:**

- Worker đợi **predicate ready[0]**, không lặp thăm dò khi chưa sẵn sàng.
- **await()** nhả lock liên kết, cho main cập nhật ready và signalAll.
- Main không thể “bỏ lỡ” điều kiện chỉ vì signal đến trước await: nó phải giữ cùng lock để sửa ready, và worker luôn kiểm tra predicate trong while.
- Sau signal, worker lấy lại lock, kiểm tra ready, ghi result rồi nhả lock.
- main.join() đợi worker hoàn thành; main cũng đọc dưới cùng lock, nên kết quả cuối xác định.

**Không dùng condition như một message queue nếu không lưu predicate.** Lời gọi signal khi chưa có waiter không lưu một “tín hiệu cho tương lai”; predicate mới là nguồn sự thật. Nếu cần truyền từng message, BlockingQueue thường phù hợp hơn.

## 12. Object.wait()/notifyAll(): blocking với intrinsic monitor

Bên cạnh Condition, Java có **Object.wait()**, **notify()**, **notifyAll()**:

~~~java
// Minh họa với lock là Object monitor và ready là field chia sẻ.
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
    consume();
}
~~~

Thread sửa điều kiện:

~~~java
synchronized (lock) {
    ready = true;
    lock.notifyAll();
}
~~~

Hai mảnh trên không phải chương trình độc lập: cần khai báo lock, ready, consume() và xử lý InterruptedException.

**Khác nhau với sleep():**

- **Object.wait()** trên đúng object mà thread đang giữ monitor sẽ **nhả monitor của object đó trong thời gian chờ**, sau đó reacquire trước khi tiếp tục.
- **Thread.sleep()** không nhả monitor đang giữ.
- **notify/notifyAll không nhả monitor ngay**; waiter phải đợi notifier rời synchronized và tự giành lại monitor.
- Wait có thể thức dậy giả; **while** phải kiểm tra điều kiện lại.
- Gọi wait/notify mà không giữ đúng monitor gây **IllegalMonitorStateException**.

Nếu đang giữ nhiều monitor, wait chỉ nhả monitor **được gọi wait()**, không nhả mọi monitor khác. Vì vậy vẫn có nguy cơ deadlock nếu chờ trong khi giữ một khóa khác cần thiết cho producer.

## 13. Interrupt: chờ có thể bị hủy theo hợp đồng

Các lời gọi blocking phổ biến như **CountDownLatch.await()**, **BlockingQueue.take()/put()**, **Semaphore.acquire()**, **Condition.await()**, **Thread.join()** và **Future.get()** hỗ trợ **InterruptedException**.

Khi một thread đang chờ và nhận interrupt, lời gọi có thể ném InterruptedException; thông thường cờ interrupt bị xóa khi exception được ném. Code cần có chính sách hợp tác:

- Nếu **không thể xử lý tại tầng hiện tại**, thường **khôi phục cờ** bằng Thread.currentThread().interrupt() rồi kết thúc/đi lên tầng gọi theo hợp đồng.
- Nếu phương thức cho phép, có thể **propagate InterruptedException** cho caller.
- Không nuốt interrupt rồi **tiếp tục chờ vô hạn** nếu yêu cầu hủy cần được tôn trọng.
- Với permit/lock, trong finally **chỉ release/unlock những gì đã thực sự acquire**.

### Ví dụ 7: interruption giải phóng thread đang await()

Tệp **InterruptibleAwaitDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

public class InterruptibleAwaitDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch neverReleased = new CountDownLatch(1);
        CountDownLatch started = new CountDownLatch(1);
        AtomicBoolean interrupted = new AtomicBoolean();
        AtomicBoolean restored = new AtomicBoolean();

        Thread worker = new Thread(() -> {
            started.countDown();
            try {
                neverReleased.await();
            } catch (InterruptedException ex) {
                interrupted.set(true);
                Thread.currentThread().interrupt();
                restored.set(Thread.currentThread().isInterrupted());
            }
        }, "await-worker");

        worker.start();
        started.await();
        worker.interrupt();
        worker.join();

        System.out.println("interrupted = " + interrupted.get());
        System.out.println("flag restored = " + restored.get());
    }
}
~~~

~~~bash
javac -encoding UTF-8 InterruptibleAwaitDemo.java
java InterruptibleAwaitDemo
~~~

Stdout:

~~~text
interrupted = true
flag restored = true
~~~

Dù interrupt đến trước hay sau thời điểm worker thực sự vào await(), nếu cờ interrupt hiện diện khi await bắt đầu hoặc khi đang chờ, await() xử lý nó bằng InterruptedException. Worker khôi phục flag và kết thúc; main join rồi in trạng thái được AtomicBoolean ghi nhận.

**Interrupt không phải lệnh cưỡng chế kết thúc thread.** Nếu worker bỏ qua interrupt hoặc đang ở một thao tác không hỗ trợ hủy, nó có thể tiếp tục. Cần thiết kế code thực thi hợp tác và không giả định external side effect tự rollback.

## 14. Deadline và timeouts: chờ đúng cách khi có nhiều bước

Khi cần thực hiện nhiều bước chờ trong **một tổng deadline**, đừng cấp nguyên timeout cho từng bước:

~~~text
Deadline toàn bộ công việc: 1000 ms
Bước A chờ 1000 ms
Bước B lại chờ 1000 ms
=> Tổng thời gian có thể vượt budget ban đầu.
~~~

Nên tính **thời gian còn lại** từ một mốc đơn điệu (**System.nanoTime()**) cho từng bước chờ. Tránh tính deadline tương đối bằng **System.currentTimeMillis()** vì đồng hồ wall-clock có thể bị điều chỉnh.

Pseudocode minh họa (không phải chương trình độc lập):

~~~text
budget = 1 second
deadline = monotonicNow + budget

remaining = deadline - monotonicNow
if remaining <= 0 -> timeout
await(stepA, remaining)

remaining = deadline - monotonicNow
if remaining <= 0 -> timeout
await(stepB, remaining)
~~~

Lưu ý phép cộng deadline khi budget rất lớn có thể overflow nếu không xử lý phù hợp; API timeout của JDK có ngữ nghĩa riêng. Với bài toán thời gian thực, nên xác định SLA, sử dụng deadline/timeout có chủ đích và đo actual latency, không coi await(timeout) là một scheduler có độ chính xác tuyệt đối.

Nếu **Future.get(timeout)** ném TimeoutException, đó là **caller chờ quá lâu**, không chứng minh worker đã dừng. Nếu policy cần hủy, caller có thể yêu cầu **future.cancel(true)** và worker phải hỗ trợ interrupt; những side effect đã hoàn tất trước đó không được tự hoàn tác.

## 15. Tránh deadlock khi sử dụng blocking primitives

Blocking primitives giúp giảm busy waiting nhưng **không tự đảm bảo deadlock-free**.

### Giữ lock rồi đợi worker cần chính lock đó

~~~text
Main giữ lock L
  -> main gọi Future.get() hoặc Thread.join() chờ worker

Worker muốn synchronized(L) hoặc lock.lock()
  -> worker chờ main nhả L

=> Vòng chờ: main đợi worker, worker đợi L của main.
~~~

Giải pháp là xác định **thứ tự chờ và phạm vi lock**. Nếu công việc cần chờ không đòi lock được giữ, có thể nhả lock rồi await; khi lấy lại lock phải **kiểm tra lại điều kiện**, vì state đã có thể thay đổi. Không bỏ lock một cách tùy tiện nếu điều đó phá invariant.

### Worker pool tự chờ task cùng pool

Một pool chỉ có một worker đang thực thi task A. Nếu A gửi task B vào **cùng single-thread executor** rồi gọi **Future.get()** đợi B, B không được chạy vì worker duy nhất đang bị A chiếm. Đó là **thread-starvation deadlock** dù không có hai ReentrantLock.

Cách thiết kế khác: không blocking đợi công việc mà cùng một tài nguyên duy nhất cần thực hiện; dùng composition/chains hoặc bố trí worker độc lập theo yêu cầu. **Thêm timeout chỉ làm có đường thoát**, không chứng minh kiến trúc đúng.

### Full queue và chu trình chờ

Producer giữ một resource rồi **put()** vào queue đã đầy; consumer muốn lấy resource ấy trước khi **take()**. Producer chờ queue có chỗ, consumer chờ resource → có thể deadlock. Vì vậy không chỉ xét lock order mà còn xét **resource dependency graph** gồm permits, queue capacity và kết quả tác vụ.

## 16. Không phải lúc nào spinning cũng vô nghĩa

Có các trường hợp kỹ thuật rất ngắn, đã đo đạc, trong thuật toán lock-free hoặc low-latency, **spinning có giới hạn** có thể giảm chi phí park/unpark so với blocking. Tuy nhiên cần:

- Dùng cơ chế memory ordering phù hợp (**volatile**, atomic, VarHandle theo đúng mode).
- Giới hạn số vòng/thời gian và có fallback sang blocking nếu chờ kéo dài.
- Đo mức CPU tiêu thụ, tail latency, fairness và tác động tới các thread khác.
- Cẩn thận với một hoặc rất ít CPU core: spinner có thể chiếm CPU mà producer cần để hoàn thành.
- Không dùng **Thread.onSpinWait()** như một lời hứa JMM về visibility, thứ tự hoặc thức dậy.

Đối với phần lớn giao thức chờ dữ liệu, tín hiệu, completion hoặc permit trong ứng dụng thông thường, **blocking primitive đúng ngữ nghĩa dễ bảo trì hơn vòng spin tự viết**.

## 17. Hướng dẫn chọn primitive theo ngữ nghĩa

| Nếu bạn đang hỏi... | Hãy xem xét | Đừng làm |
| --- | --- | --- |
| “Bao giờ các worker đã xong một bước?” | CountDownLatch hoặc Future | Poll một cờ ordinary vô hạn |
| “Có phần tử để xử lý chưa?” | BlockingQueue.take()/poll(timeout) | isEmpty rồi sleep |
| “Có slot tài nguyên để vào không?” | Semaphore.acquire()/tryAcquire(timeout) | Counter thường và spin |
| “Computation trả giá trị hay lỗi gì?” | Future.get() / composition | while(!isDone()) rồi get |
| “Điều kiện dưới khóa đã thỏa chưa?” | Condition.await() trong while | await không giữ lock hoặc dùng if |
| “Thread cụ thể đã kết thúc chưa?” | Thread.join() | while(thread.isAlive()) không có sleep/hủy |
| “Tôi chỉ cần trao một signal cấp thấp?” | Primitive cấp cao; LockSupport khi thực sự cần | park mà không có state predicate |
| “Tôi cần tối ưu chờ cực ngắn?” | Đo đạc spin có giới hạn + fallback | Spin vô hạn và hy vọng scheduler |

**Quy tắc chọn:** xác định **thứ bạn muốn nhận** (tín hiệu, phần tử, permit, kết quả, predicate), **khi nào nó hợp lệ**, **ai cung cấp**, và **đường lỗi/timeout/interrupt**. Sau đó chọn primitive có hợp đồng gần nhất.

## 18. Lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Spin trên field thường | Data race/visibility và tiêu tốn CPU | Dùng blocking primitive hoặc giao thức volatile/atomic được chứng minh |
| Spin với volatile rồi cho rằng đã tối ưu | Vẫn tốn CPU | Dùng await/take/get khi thích hợp |
| Sleep rồi cho rằng có happens-before | Có thể không thấy dữ liệu đúng | Dùng primitive có memory consistency rõ |
| Dùng CountDownLatch để truyền object như queue | Latch chỉ mang sự kiện count | BlockingQueue hoặc Future |
| Không countDown trên đường lỗi | Waiter có thể treo | Hoàn thiện contract completion và finally |
| Dùng await(timeout) rồi xem false là thành công | Điều kiện chưa thỏa | Tách nhánh timeout |
| Cho rằng Future.isDone nghĩa là thành công | Done gồm cả exception/cancel | Kiểm tra Future.get và chính sách nghiệp vụ |
| Gọi Future.get timeout rồi giả định task dừng | Task có thể vẫn chạy | Cancel hợp tác theo policy |
| BlockingQueue không có capacity rõ | Có thể tăng bộ nhớ không kiểm soát | Chọn bounded queue và backpressure |
| put vào queue khi đang giữ lock mà consumer cần | Deadlock hoặc contention | Phân tích dependency, thay cấu trúc phối hợp |
| Tăng Semaphore permits do release dư | Phá giới hạn đồng thời | Release chính xác sau acquire thành công |
| Gọi Condition.signal ngoài lock | IllegalMonitorStateException | Giữ lock liên kết |
| Dùng if quanh Condition.await | Spurious wakeup, predicate bị thay đổi | while kiểm tra lại |
| Nuốt InterruptedException | Đường hủy không có hiệu lực | Propagate hoặc restore flag rồi dừng theo policy |
| Đợi Future trong single-worker task của cùng pool | Thread-starvation deadlock | Không block chờ task phụ thuộc cùng worker |
| Tin thread WAITING nghĩa là “không giữ khóa” | Có thể vẫn giữ lock khác | Rà soát tất cả khóa đang sở hữu |
| Tin blocking luôn tức thời hoặc công bằng | Scheduler/timer/contestion khác nhau | Đo latency, deadline và fairness thực tế |

## 19. Bài tập tự kiểm tra

**1. Vì sao vòng while (!flag) {} có thể sai cả khi worker chắc chắn gán flag=true?**  
Vì flag thông thường có thể bị data race/thiếu happens-before; reader không được bảo đảm thấy cập nhật. Dù flag volatile, vòng spin vẫn có thể tốn CPU.

**2. Khi chỉ cần biết N worker đã hoàn thành một giai đoạn, nên dùng gì?**  
CountDownLatch(N), mỗi worker countDown theo contract, caller await. Nếu cần truy xuất lỗi/kết quả từng worker, thêm cơ chế thu kết quả thích hợp hoặc dùng Future.

**3. Khi cần nhận từng phần tử từ producer, CountDownLatch có đủ không?**  
Không. Latch không mang dữ liệu; BlockingQueue cung cấp put/take và memory consistency cho phần tử được trao.

**4. Semaphore khác ReentrantLock ở điểm sở hữu khóa?**  
ReentrantLock yêu cầu owner unlock chính lock mình đã giữ. Semaphore quản lý permit và không buộc thread release là thread acquire; ứng dụng phải tự bảo toàn số permit.

**5. Có được đặt signalAll() ngoài lock để tránh contention không?**  
Không với Condition do ReentrantLock tạo: signalAll yêu cầu thread sở hữu lock liên kết. Hãy cập nhật predicate và signal dưới cùng lock.

**6. Future.get(timeout) ném TimeoutException có nói job đã bị hủy không?**  
Không. Đó chỉ là caller hết thời gian chờ; task có thể vẫn chạy.

**7. Nếu worker bị interrupt trong lúc CountDownLatch.await(), nên xử lý thế nào?**  
Theo contract: có thể propagate InterruptedException; nếu bắt mà không xử lý ở tầng hiện tại, khôi phục interrupt flag và kết thúc hợp tác, đồng thời cleanup tài nguyên đã acquire.

**8. Vì sao Thread.sleep(50) trong polling không phải giải pháp phối hợp tốt nhất?**  
Nó tạo độ trễ/tải thức dậy theo chu kỳ và không tự cung cấp memory visibility. Blocking primitive cho phép chờ đúng sự kiện.

**9. Một Condition.await() có nhả tất cả lock mà thread đang giữ không?**  
Không, chỉ nhả lock liên kết với Condition trong thời gian await. Nếu thread giữ lock khác, deadlock vẫn có thể xảy ra.

**10. BlockingQueue capacity 2 có chắc producer chỉ giữ tối đa hai object trong toàn chương trình không?**  
Không. Capacity chỉ giới hạn số phần tử **đang nằm trong queue**. Producer/consumer có thể giữ reference khác ngoài queue, và side effect/bộ nhớ liên quan không tự bị giới hạn bởi capacity.

## 20. Kết luận

**Tránh busy waiting** không đơn thuần là thêm sleep vào while; đó là **chuyển từ hỏi lại trạng thái liên tục sang chờ đúng sự kiện bằng một giao thức có bảo đảm đồng bộ hóa**.

- Dùng **CountDownLatch** để chờ mốc hoàn tất một lần.
- Dùng **BlockingQueue** để chờ và trao phần tử.
- Dùng **Semaphore** để chờ quyền truy cập tài nguyên có giới hạn.
- Dùng **Future.get()** để chờ kết quả computation, kể cả lỗi/hủy.
- Dùng **Condition.await()** hoặc **Object.wait()** cùng predicate trong while khi điều kiện được quản lý bởi lock/monitor.

Với mọi primitive, phải làm rõ **timeout, interrupt, resource cleanup, memory visibility, trạng thái nghiệp vụ và dependency graph**. Blocking làm giảm vòng thăm dò vô ích, nhưng chỉ một giao thức đúng mới đảm bảo chương trình vừa tiến triển vừa bảo toàn các bất biến.
