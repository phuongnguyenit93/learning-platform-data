# Work queue: ArrayBlockingQueue và LinkedBlockingQueue trong Executor Framework

Khi gọi `execute()` hoặc `submit()` trên một `ThreadPoolExecutor`, không phải mọi tác vụ đều lập tức có thread chạy. Nếu số worker hiện có đang bận, executor có thể đưa những `Runnable` chưa bắt đầu vào **work queue**. Hai loại queue quan trọng của Java là `ArrayBlockingQueue` và `LinkedBlockingQueue`. Sự khác biệt về **dung lượng**, **cách lưu phần tử**, cùng thuật toán tiếp nhận tác vụ của `ThreadPoolExecutor` ảnh hưởng đến số worker được tạo, độ trễ hàng chờ, bộ nhớ và quyết định từ chối task khi quá tải.

- `ArrayBlockingQueue<E>`: queue FIFO dựa trên **mảng có dung lượng cố định** ngay từ constructor.
- `LinkedBlockingQueue<E>`: queue FIFO sử dụng cấu trúc liên kết; có constructor **bounded** và constructor mặc định có capacity **`Integer.MAX_VALUE`**, thường được mô tả là *effectively unbounded*.
- Cả hai triển khai `BlockingQueue<E>`, có các phương thức chờ/không chờ khi thêm hoặc lấy phần tử.
- Trong `ThreadPoolExecutor`, **work queue đầy không có nghĩa thread nộp task sẽ tự chờ**. Executor thường dùng `offer()`: nếu thất bại, nó thử tạo thêm worker tới `maximumPoolSize`; nếu không thể, áp dụng `RejectedExecutionHandler`.

Đây là bài về Java concurrency và Executor Framework của JDK, không dùng framework khác. Các ví dụ độc lập dùng JDK 17+.

## 1. Work queue làm gì trong executor?

Một cách nhìn đơn giản:

```text
execute(task) / submit(task)
           |
           v
    ThreadPoolExecutor
       /        \
      v          v
   Workers    BlockingQueue<Runnable>
   chạy task  giữ các task chưa chạy
      ^          |
      +----------+
           |
           v
  Rejection nếu không thể nhận việc
```

**Task đang chạy** thuộc worker; **task chờ** nằm trong queue. Queue có thể chứa `Runnable` do caller gửi hoặc wrapper task do `submit()` tạo ra. Một task xếp hàng lâu vẫn giữ tham chiếu tới dữ liệu/đối tượng mà nó capture; vì vậy queue tăng liên tục có thể gây **GC pressure**, tăng thời gian chờ và dẫn đến cạn heap.

Tham số thiết lập pool thường gồm:

```java
ThreadPoolExecutor executor = new ThreadPoolExecutor(
        2, 4, 30, TimeUnit.SECONDS,
        new ArrayBlockingQueue<Runnable>(10),
        new ThreadPoolExecutor.AbortPolicy()
);
```

Đây là **trích đoạn minh họa**, cần import `java.util.concurrent.*`. Pool có tối thiểu `corePoolSize = 2` worker theo mục tiêu khi có tác vụ, tối đa `maximumPoolSize = 4` worker, và queue chứa tối đa 10 task chưa được worker lấy. Chính sách `AbortPolicy` ném `RejectedExecutionException` nếu không tiếp nhận được task.

**Quan trọng:** constructor không tự khởi động đủ core thread. Worker thường được tạo theo nhu cầu; có API `prestartCoreThread()` hoặc `prestartAllCoreThreads()` nếu cần tạo trước.

## 2. API quan trọng của BlockingQueue

`BlockingQueue<E>` phân biệt rõ cách ứng xử khi queue **đầy** hoặc **rỗng**:

| Thao tác | Khi có thể thực hiện | Khi chưa thể thực hiện |
|---|---|---|
| `add(e)` | Thêm phần tử và trả `true`. | Ném `IllegalStateException` nếu đầy. |
| `offer(e)` | Thêm và trả `true`. | Trả `false` ngay nếu đầy. |
| `put(e)` | Thêm phần tử. | **Chờ** tới khi có chỗ, có thể bị interrupt. |
| `offer(e, timeout, unit)` | Chờ có giới hạn rồi thêm. | Trả `false` khi hết hạn, hoặc ném `InterruptedException`. |
| `remove()` | Lấy và xóa phần tử đầu. | Ném `NoSuchElementException` nếu rỗng. |
| `poll()` | Lấy và xóa phần tử đầu. | Trả `null` ngay nếu rỗng. |
| `take()` | Lấy phần tử. | **Chờ** tới khi có dữ liệu, có thể bị interrupt. |
| `poll(timeout, unit)` | Chờ có giới hạn rồi lấy. | Trả `null` khi hết hạn, hoặc bị interrupt. |
| `peek()` | Xem phần tử đầu, không xóa. | Trả `null` nếu rỗng. |

Hai queue này đều cấm phần tử `null`; kết quả `null` từ `poll()` vì vậy có thể biểu thị không có item. `size()` và `remainingCapacity()` chỉ mô tả trạng thái ở **thời điểm đọc**. Không viết `if (remainingCapacity() > 0) add(item)` rồi cho rằng thao tác chắc chắn thành công: producer khác có thể chen vào. Hãy gọi trực tiếp `offer()` hoặc `put()` theo hợp đồng.

Trong producer–consumer, `put()` và `take()` thường có ích; trong đường tiếp nhận tác vụ bình thường của `ThreadPoolExecutor`, executor dùng `offer()` để không chặn caller tại queue.

## 3. ArrayBlockingQueue: mảng cố định và capacity rõ ràng

Tạo một queue có giới hạn:

```java
BlockingQueue<String> queue = new ArrayBlockingQueue<>(100);
```

Đoạn này là trích đoạn, cần import `BlockingQueue` và `ArrayBlockingQueue`. Dung lượng 100 được xác định khi tạo, không tự động tăng. Khi đủ 100 phần tử: `offer()` trả false; `put()` đợi; `offer(timeout,...)` có thể đợi tới hạn.

Đặc tính:

- **FIFO:** phần tử trong queue được lấy theo thứ tự enqueue; không bảo đảm task được nhiều worker thực thi và **hoàn thành** theo đúng thứ tự.
- **Array được cấp phát theo capacity:** không tạo một node liên kết mới cho mỗi phần tử như cấu trúc linked. Tổng hiệu năng phụ thuộc workload và contention, không nên kết luận “array luôn nhanh hơn”.
- **Fairness tùy chọn:** `new ArrayBlockingQueue<>(capacity, true)` yêu cầu chính sách công bằng khi các thread tranh quyền truy cập queue, thường đánh đổi throughput. Nó **không** hứa sự công bằng toàn bộ của `ThreadPoolExecutor`.
- **Bounded backlog:** giúp giới hạn số task **đang chờ** và làm quá tải biểu hiện rõ qua queue full/rejection.

Khi dùng queue bounded, phải quyết định cách xử lý nếu pool đạt `maximumPoolSize` và queue hết chỗ. Bounded queue **không** đồng nghĩa mọi task đều được chấp nhận.

## 4. LinkedBlockingQueue: giới hạn rõ hoặc capacity rất lớn

Hai constructor:

```java
BlockingQueue<Runnable> defaultCapacity =
        new LinkedBlockingQueue<>();

BlockingQueue<Runnable> bounded =
        new LinkedBlockingQueue<>(100);
```

Đây là trích đoạn, cần import `java.util.concurrent.*`.

- Không truyền capacity: `LinkedBlockingQueue` mặc định có capacity `Integer.MAX_VALUE`. “Unbounded” là cách gọi tắt; không có nghĩa RAM vô hạn. Nếu task được nộp liên tục nhanh hơn xử lý, queue có thể chiếm rất nhiều heap trước khi đạt giới hạn số nguyên.
- Có truyền capacity: queue giữ tối đa số phần tử đó. Với `LinkedBlockingQueue<>(100)`, `offer()` trả `false` khi đã có 100 phần tử chưa bị lấy khỏi queue.
- Dùng linked nodes nên có chi phí bộ nhớ/cấp phát tương ứng các phần tử và cách implementation. Không có constructor `fair` giống `ArrayBlockingQueue`.
- FIFO theo thứ tự enqueue. Với nhiều thread cùng submit, thứ tự được chấp nhận phụ thuộc lịch chạy, không phải luôn thứ tự các dòng log của caller.

**Điểm khác biệt ở executor:** `LinkedBlockingQueue<>()` mặc định thường **tiếp nhận gần như mọi task đến sau core workers vào queue**, khiến executor không có lý do tăng worker tới `maximumPoolSize` trong đường admission bình thường. Một `LinkedBlockingQueue<>(boundedCapacity)` khi đầy **cũng có thể khiến pool tạo thêm worker**, giống ArrayBlockingQueue bounded.

## 5. Ví dụ 1 — Quan sát bounded capacity qua API queue

Tạo tệp **`BlockingQueueBasics.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;

public class BlockingQueueBasics {
    public static void main(String[] args) throws InterruptedException {
        ArrayBlockingQueue<String> array =
                new ArrayBlockingQueue<>(1);
        System.out.println("Array offer A: " + array.offer("A"));
        System.out.println("Array offer B: " + array.offer("B"));
        System.out.println("Array size: " + array.size());
        System.out.println("Array take: " + array.take());

        LinkedBlockingQueue<String> linked =
                new LinkedBlockingQueue<>(2);
        System.out.println("Linked offer X: " + linked.offer("X"));
        System.out.println("Linked offer Y: " + linked.offer("Y"));
        System.out.println("Linked offer Z: " + linked.offer("Z"));
        System.out.println("Linked remaining: "
                + linked.remainingCapacity());

        List<String> removed = new ArrayList<>();
        linked.drainTo(removed);
        System.out.println("Drained: " + removed);
        System.out.println("Linked size: " + linked.size());
    }
}
```

```bash
javac BlockingQueueBasics.java
java BlockingQueueBasics
```

Kết quả:

```text
Array offer A: true
Array offer B: false
Array size: 1
Array take: A
Linked offer X: true
Linked offer Y: true
Linked offer Z: false
Linked remaining: 0
Drained: [X, Y]
Linked size: 0
```

Ví dụ đơn luồng cố ý dùng `offer()` ở thời điểm queue đầy để **không treo chương trình** như `put()`. `drainTo()` chuyển các item hiện có sang danh sách, **không chờ** dữ liệu mới. `ArrayBlockingQueue` và `LinkedBlockingQueue` đều hỗ trợ các thao tác `BlockingQueue`; điểm cần hiểu ở đây là việc capacity làm `offer()` thất bại.

## 6. Quy tắc admission: core → queue → maximum → rejection

Khi caller gọi `ThreadPoolExecutor.execute(command)`, mô hình hoạt động thông thường là:

1. Nếu số worker **nhỏ hơn `corePoolSize`**, pool cố tạo worker mới để chạy task.
2. Nếu đã đạt core, pool thử **`workQueue.offer(command)`**.
3. Nếu offer thành công, task nằm trong queue chờ worker. Pool cũng **kiểm tra lại trạng thái chạy/shutdown** và điều kiện có worker nhằm xử lý các race đồng thời.
4. Nếu queue không nhận task, pool thử tạo thêm worker tới **`maximumPoolSize`**.
5. Nếu không thể thêm worker hoặc executor đã shutdown, dùng `RejectedExecutionHandler`.

```text
                    execute(task)
                         |
                 workers < core ?
                    /         \
                  yes         no
                   |           |
              create worker   queue.offer(task)?
                                 /           \
                               yes           no
                                |             |
                            queue waits   workers < max?
                                            /       \
                                          yes       no
                                           |         |
                                      create worker  reject
```

Đây là mô hình đơn giản hóa; các quyết định thực tế cần đối phó với concurrent shutdown và thay đổi worker count.

**Hệ quả hay bị bỏ qua:** `maximumPoolSize` thường **chỉ có tác dụng khi queue không nhận thêm được**. Nếu queue có capacity rất lớn, nhiều task sẽ chờ trong queue trong khi số worker vẫn gần `corePoolSize`. Tăng maximum từ 4 lên 100 **không tự rút ngắn** queue đang tăng nếu LinkedBlockingQueue mặc định luôn nhận thêm task.

Ví dụ với `core=1`, `max=2`, queue capacity 1:

- Task thứ nhất → tạo core worker.
- Task thứ hai → vào queue.
- Task thứ ba → queue đầy, tạo worker thứ hai.
- Task thứ tư → nếu hai worker đều bận và queue vẫn đầy, **reject**.

**Không nhầm** `newFixedThreadPool(n)` với queue bounded: implementation thông thường sử dụng một `LinkedBlockingQueue` không giới hạn nhỏ theo ứng dụng, nên tải vượt năng lực xử lý có thể tạo backlog lớn; chọn factory/config phù hợp theo mục tiêu.

## 7. Ví dụ 2 — Bounded ArrayBlockingQueue làm pool mở thêm worker

Dùng `CountDownLatch` để giữ task #1 và #3 đang chạy, trong khi task #2 nằm trong queue. Nhờ đó ta kiểm tra chính xác pool đã mở thêm worker ở bước nào mà không phụ thuộc tình cờ vào thread scheduler.

Tạo tệp **`ExecutorBoundedAdmission.java`**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class ExecutorBoundedAdmission {
    static void awaitRelease(CountDownLatch release) {
        try {
            release.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor executor = new ThreadPoolExecutor(
                1, 2, 30, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy()
        );
        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch thirdStarted = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            executor.execute(() -> {
                firstStarted.countDown();
                awaitRelease(release);
            });
            firstStarted.await();

            executor.execute(() -> { }); // Task thứ hai đợi trong queue.

            executor.execute(() -> {
                thirdStarted.countDown();
                awaitRelease(release);
            });
            thirdStarted.await();

            System.out.println("Pool size: " + executor.getPoolSize());
            System.out.println("Active workers: " + executor.getActiveCount());
            System.out.println("Queued tasks: " + executor.getQueue().size());
        } finally {
            release.countDown();
            executor.shutdown();
        }

        boolean terminated = executor.awaitTermination(
                5, TimeUnit.SECONDS);
        System.out.println("Terminated: " + terminated);
        System.out.println("Completed tasks: "
                + executor.getCompletedTaskCount());
    }
}
```

```bash
javac ExecutorBoundedAdmission.java
java ExecutorBoundedAdmission
```

Kết quả trong lần chạy bình thường, không bị interrupt từ bên ngoài:

```text
Pool size: 2
Active workers: 2
Queued tasks: 1
Terminated: true
Completed tasks: 3
```

Task #1 chiếm core worker và đợi latch; task #2 xếp hàng vì queue còn chỗ; task #3 làm `offer()` thất bại do queue đầy, vì vậy pool tạo worker thứ hai (không vượt max). Main đợi cả task #1 và #3 đạt trạng thái đang chạy trước khi đọc metrics, nên hàng đợi vẫn chứa task #2. Khi `release.countDown()`, executor hoàn tất các task được chấp nhận, rồi shutdown đúng hợp đồng.

Trong ứng dụng thực tế, `getActiveCount()` và queue size là các giá trị chẩn đoán có thể thay đổi tức thì; ở ví dụ này chúng ổn định vì latch giữ task lại.

## 8. Ví dụ 3 — LinkedBlockingQueue mặc định giữ task ở queue

Dùng pool `corePoolSize=1`, `maximumPoolSize=3` nhưng `LinkedBlockingQueue<>()` capacity mặc định. Khi core worker đang bận, hai task tiếp theo **được enqueue**; pool thường không mở thêm worker.

Tạo tệp **`ExecutorUnboundedQueue.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class ExecutorUnboundedQueue {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor executor = new ThreadPoolExecutor(
                1, 3, 30, TimeUnit.SECONDS,
                new LinkedBlockingQueue<>()
        );
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            executor.execute(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });
            started.await();

            executor.execute(() -> { });
            executor.execute(() -> { });

            System.out.println("Pool size: " + executor.getPoolSize());
            System.out.println("Active workers: " + executor.getActiveCount());
            System.out.println("Queued tasks: " + executor.getQueue().size());
        } finally {
            release.countDown();
            executor.shutdown();
        }

        boolean terminated = executor.awaitTermination(
                5, TimeUnit.SECONDS);
        System.out.println("Terminated: " + terminated);
        System.out.println("Completed tasks: "
                + executor.getCompletedTaskCount());
    }
}
```

```bash
javac ExecutorUnboundedQueue.java
java ExecutorUnboundedQueue
```

Kết quả:

```text
Pool size: 1
Active workers: 1
Queued tasks: 2
Terminated: true
Completed tasks: 3
```

Chỉ core worker được tạo vì queue nhận các task mới thành công. `maximumPoolSize=3` là trần, **không phải mục tiêu tự mở tới ba worker**. Nếu đổi thành `new LinkedBlockingQueue<Runnable>(1)`, queue có thể đầy và khi đó pool có cơ hội mở non-core worker giống ví dụ ArrayBlockingQueue.

## 9. Saturation và RejectedExecutionHandler

Khi worker đạt max và queue đầy, executor dùng rejection policy:

| Policy | Ứng xử | Chú ý |
|---|---|---|
| `AbortPolicy` | Ném `RejectedExecutionException`. | Mặc định; caller cần xử lý lỗi hoặc giới hạn retry. |
| `CallerRunsPolicy` | Nếu executor chưa shutdown, chạy task ngay trong **thread gọi `execute()`**. | Có thể tạo backpressure nhưng làm chậm caller; khi executor đã shutdown, task có thể bị bỏ. |
| `DiscardPolicy` | Bỏ task mà không ném. | Chỉ dùng khi có thể chấp nhận mất việc. |
| `DiscardOldestPolicy` | Thử bỏ task ở đầu queue rồi thử execute lại. | Có thể mất công việc đã chờ; không phù hợp với mọi policy/queue. |

Queue bounded giúp giới hạn backlog nhưng **không tự cung cấp backpressure mong muốn**. Cần chọn policy có chủ đích: báo lỗi có thể quan sát, caller-runs khi thích hợp, retry có giới hạn hoặc giảm tốc nhà sản xuất task.

### Ví dụ 4 — CallerRunsPolicy chạy task trên thread nộp

Tạo tệp **`CallerRunsBackpressure.java`**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class CallerRunsBackpressure {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor executor = new ThreadPoolExecutor(
                1, 1, 0, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.CallerRunsPolicy()
        );
        Thread caller = Thread.currentThread();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicBoolean ranOnCaller = new AtomicBoolean();

        try {
            executor.execute(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });
            started.await();

            executor.execute(() -> { }); // Một task ở queue.
            executor.execute(() -> {
                ranOnCaller.set(Thread.currentThread() == caller);
            });

            System.out.println("Third ran on caller: "
                    + ranOnCaller.get());
        } finally {
            release.countDown();
            executor.shutdown();
        }

        boolean terminated = executor.awaitTermination(
                5, TimeUnit.SECONDS);
        System.out.println("Terminated: " + terminated);
        System.out.println("Pool completed: "
                + executor.getCompletedTaskCount());
    }
}
```

```bash
javac CallerRunsBackpressure.java
java CallerRunsBackpressure
```

Kết quả trong lần chạy bình thường:

```text
Third ran on caller: true
Terminated: true
Pool completed: 2
```

Task thứ ba chạy **đồng bộ trong caller**, không phải thread của pool. Vì vậy `getCompletedTaskCount()` chỉ đếm hai task worker đã hoàn tất, không đếm task chạy ngoài pool. Nếu caller là thread xử lý yêu cầu nhạy cảm latency hoặc event loop, `CallerRunsPolicy` có thể làm nghẽn đường nhận yêu cầu. Cân nhắc bối cảnh trước khi chọn.

## 10. FIFO queue khác FIFO hoàn thành

Hai queue có ngữ nghĩa FIFO cho các phần tử **đã nằm trong queue**. Nhưng `ThreadPoolExecutor` không hứa “task submit trước luôn hoàn tất trước”:

- Có nhiều worker, task bắt đầu trước có thể mất thời gian lâu hơn task bắt đầu sau.
- Nếu bounded queue đầy, task mới có thể được giao **thẳng cho non-core worker** dù task cũ còn trong queue. Trong ví dụ pool có core=1,max=2, task #3 có thể bắt đầu trước task #2.
- Các caller đồng thời submit tạo ra thứ tự enqueue phụ thuộc lịch chạy.
- `CallerRunsPolicy` chạy task tại submitter, không phải qua hàng đợi chờ worker.

Nếu yêu cầu nghiệp vụ có thứ tự nghiêm ngặt, cần thiết kế serialization/order riêng. Một single-thread executor loại bỏ xử lý song song trên worker nhưng rejection policy, cancellation và các callback ngoài executor vẫn cần được xét; không suy ordering chỉ từ tên FIFO của BlockingQueue.

## 11. Khi nào chọn ArrayBlockingQueue hoặc LinkedBlockingQueue?

| Tiêu chí | `ArrayBlockingQueue` | `LinkedBlockingQueue` |
|---|---|---|
| Lưu trữ | Mảng dung lượng cố định. | Node liên kết theo phần tử. |
| Capacity mặc định | Phải truyền vào. | `Integer.MAX_VALUE` khi không truyền. |
| Bounded | Luôn bounded. | Bounded nếu chỉ định capacity. |
| FIFO | Có. | Có. |
| `put/take/offer/poll` | Có. | Có. |
| Fairness trong constructor | Có option `fair`. | Không có option tương đương. |
| Hậu quả queue đầy với executor | Có thể tạo thêm worker tới max rồi reject. | Cũng vậy **nếu bounded**; bản mặc định khó đầy trước khi bộ nhớ trở thành vấn đề. |
| Bảo trì/hiệu năng | Dễ dự toán bộ nhớ slots; ít overhead cấp phát node. | Có overhead node và khả năng tăng queue khi không bounded; đo trong workload thật. |

**Chọn capacity trước khi chọn implementation.** Nếu mục tiêu là memory/latency budget rõ ràng, cả `ArrayBlockingQueue<>(n)` và `LinkedBlockingQueue<>(n)` đều cung cấp giới hạn. Khác biệt hiệu năng/locking của implementation phải được đo đạc với workload thực tế; không có quy tắc “Linked luôn nhanh hơn Array”.

## 12. Thiết kế capacity, throughput và backpressure

Giả sử hệ thống nhận **500 task/giây** nhưng các worker ổn định chỉ xử lý **300 task/giây**. Trong thời gian quá tải, backlog tăng khoảng **200 task/giây**. Tăng queue capacity chỉ **trì hoãn** lúc đầy, không tạo thêm năng lực xử lý; task xếp hàng lâu có thể hết thời hạn nghiệp vụ trước khi chạy.

Một queue quá lớn thường gây:

- Độ trễ trước khi task bắt đầu tăng.
- Giữ hàng loạt object được task tham chiếu, tăng bộ nhớ và GC.
- Che giấu overload thay vì buộc caller giảm tốc.
- Tác vụ bị hủy/không còn ý nghĩa vẫn có thể nằm trong queue chờ xử lý.

Queue quá ngắn cùng maxPoolSize nhỏ có thể reject sớm; điều này không nhất thiết sai nếu policy bên gửi biết giảm tải. Queue càng bounded và max càng cao không đồng nghĩa throughput tốt hơn: quá nhiều worker tranh CPU, kết nối database hoặc hệ thống ngoài có thể làm chậm hơn.

Khi đặt thông số, hãy quan sát **arrival rate**, **service rate**, thời gian task chờ, thời gian chạy, active workers, queue depth, rejection count, heap và latency p95/p99. Với task CPU-bound, số worker thường phải phù hợp tài nguyên CPU; với task I/O-bound, số worker có thể khác nhưng vẫn bị giới hạn bởi downstream và bộ nhớ.

## 13. Không thao tác trực tiếp work queue như một API submit

`executor.getQueue()` cho phép quan sát queue. Nhưng không nên tự gọi `executor.getQueue().put(task)` để nộp công việc vì việc này có thể **bỏ qua cơ chế** `execute()`: kiểm tra shutdown, tạo worker, chính sách reject và một số logic quản lý task.

Dùng `execute()` hoặc `submit()` để gửi nhiệm vụ. Các metric như:

```java
int queued = executor.getQueue().size();
int active = executor.getActiveCount();
long completed = executor.getCompletedTaskCount();
int capacity = executor.getQueue().remainingCapacity();
```

là trích đoạn cần `executor` đã khai báo, và là **quan sát tức thời/xấp xỉ**, không phải giao thức ra quyết định nguyên tử. Không xây code `if (getQueue().size() < limit) executor.execute(...)` rồi giả định chắc chắn còn chỗ: state có thể đổi trước lời `execute()`.

`drainTo()` không phải “chờ executor chạy hết task”; nó chuyển các phần tử còn trong queue sang collection đích. Việc can thiệp queue trực tiếp để xóa/hủy cần thiết kế rất cẩn thận vì có thể phá hợp đồng hoàn tất/quan sát task của caller.

## 14. Shutdown, cancellation và task chờ

Executor không “đóng” work queue bằng một lời `BlockingQueue.close()` tổng quát. Chủ sở hữu quản lý vòng đời qua:

- `shutdown()`: ngừng nhận task mới, các task đã được chấp nhận có thể chạy cho tới hoàn tất.
- `shutdownNow()`: cố interrupt các task đang chạy, ngừng xử lý task còn chờ và trả những task chưa bắt đầu; không bảo đảm thread sẽ ngừng ngay.
- `awaitTermination(timeout, unit)`: đợi pool thật sự terminated, trả boolean cho biết đã hoàn tất trước hạn không.
- `Future.cancel(true)`: yêu cầu hủy task; với task đang chạy có thể cố interrupt nhưng không bảo đảm cleanup đã hoàn tất ngay khi method trả về.
- `getQueue().size()` chỉ cho biết backlog hiện tại, không phản ánh task đang thực thi.

Task đã hủy có thể còn được queue giữ cho tới khi được lấy hoặc dọn bằng cơ chế phù hợp. `ThreadPoolExecutor.purge()` có thể loại bỏ một số task Future đã cancel khỏi queue, nhưng không phải công cụ thay cho capacity và lifecycle đúng. Task giữ object lớn trong lúc queued là yếu tố phải dự toán memory.

Với `submit()`, ngoại lệ của tác vụ được đưa vào `Future` và thường được phát hiện qua `get()`; với `execute()`, cách exception ảnh hưởng worker và nơi xử lý lỗi có khác. Không thiết kế hệ thống coi một queue chưa đầy là bằng chứng nhiệm vụ chắc chắn thành công.

## 15. Java Memory Model và chuyển giao dữ liệu qua BlockingQueue

Hợp đồng memory consistency của `BlockingQueue` cung cấp quan hệ **happens-before**: hành động trong producer **trước khi đưa một object vào queue** happens-before hành động của consumer **sau khi truy cập/lấy object đó ra**. Điều này giúp chuyển giao dữ liệu được xây dựng trước enqueue.

Ví dụ ý tưởng:

```java
// Producer:
Message message = new Message();
message.value = 42;
queue.put(message);

// Consumer trong thread khác:
Message result = queue.take();
System.out.println(result.value);
```

Đây là **trích đoạn** cần class `Message` và queue phù hợp, không phải chương trình độc lập. Không cần `volatile` trên mọi field của payload chỉ để chuyển giao **một chiều đúng cách** qua queue. Nhưng nếu producer tiếp tục sửa cùng object sau enqueue trong khi consumer đọc, quan hệ queue không bảo vệ các mutation cạnh tranh đó; ưu tiên payload immutable hoặc quy tắc chuyển quyền sở hữu rõ ràng.

Đối với executor, tác vụ được submit thường mang tham chiếu tới dữ liệu mà nó cần. An toàn dữ liệu trong các worker vẫn dựa trên Java Memory Model và giao thức đồng bộ hóa thích hợp; queue không biến mọi object mutable được capture thành thread-safe.

## 16. Checklist và tự kiểm tra

Checklist trước khi đưa executor vào hệ thống:

1. Xác định `corePoolSize`, `maximumPoolSize`, tốc độ đến và thời gian chạy task.
2. Chọn queue bounded hay effectively unbounded **có chủ đích**, không để mặc định vì tiện.
3. Ước lượng memory và latency chờ dựa trên số queued task và object graph chúng giữ.
4. Hiểu admission **core → offer queue → maximum → rejection**.
5. Chọn rõ `RejectedExecutionHandler`; xử lý overload theo hợp đồng nghiệp vụ.
6. Không dùng queue FIFO như lời hứa thứ tự thực thi/hoàn thành.
7. Không submit tác vụ bằng `getQueue().add()`/`put()`.
8. Quản lý shutdown, cancellation, timeout và cleanup.
9. Theo dõi queue depth, active workers, rejection, task duration và GC.
10. Stress-test khi task bị block, queue đầy và executor shutdown đồng thời.

Câu hỏi kiểm tra:

1. **ArrayBlockingQueue có constructor không truyền capacity không?** Không, capacity phải xác định khi tạo.
2. **LinkedBlockingQueue không tham số có capacity gì?** `Integer.MAX_VALUE` — không phải RAM vô hạn.
3. **LinkedBlockingQueue có thể bounded không?** Có, dùng constructor nhận capacity.
4. **Tại sao `maximumPoolSize=20` vẫn có thể chỉ dùng 2 worker?** Vì queue còn nhận thêm task sau khi core có 2 worker, nên không có lý do mở non-core trong đường admission bình thường.
5. **Executor có gọi `queue.put(task)` và chặn caller khi queue đầy không?** Đường admission thông thường dùng `offer()`; queue đầy khiến pool thử tạo thêm worker hoặc reject.
6. **Queue FIFO có bảo đảm thứ tự task hoàn tất không?** Không, vì nhiều worker, thời lượng task khác nhau và task mới có thể được giao trực tiếp cho worker.
7. **CallerRunsPolicy có thể tạo backpressure ra sao?** Task bị reject có thể chạy ngay trên caller, làm caller không thể tiếp tục submit cho tới khi task kết thúc.
8. **Khi shutdown(), những task đã ở queue có tự bị bỏ hết không?** Không. `shutdown()` cho phép task đã nhận được chạy cho tới khi executor kết thúc; `shutdownNow()` là cơ chế cố dừng khác.
9. **Đọc `remainingCapacity()` rồi `add()` có an toàn trong cạnh tranh không?** Không; dùng `offer()` hoặc `put()` theo contract.
10. **Vì sao queue rất lớn có thể làm hệ thống chậm và hết heap?** Backlog giữ object trong RAM và tạo queue wait time, không làm service rate tự tăng.

**Ghi nhớ:** `ArrayBlockingQueue` luôn bounded; `LinkedBlockingQueue` có thể bounded nhưng mặc định có capacity rất lớn. Trong `ThreadPoolExecutor`, hiểu chính xác **core → queue.offer → maximum → rejection** để chọn queue, capacity và policy theo ngân sách tài nguyên và độ trễ.
