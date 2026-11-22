# corePoolSize, maximumPoolSize và keepAliveTime trong Java ThreadPoolExecutor

## 1. Mục tiêu bài học

Một Java application xử lý nhiều công việc đồng thời thường không muốn tạo một `new Thread(...)` vô hạn cho mỗi yêu cầu. `ThreadPoolExecutor` quản lý các **worker threads**, **hàng đợi công việc (work queue)** và chính sách **từ chối task (rejection)** để điều tiết việc thực thi.

Ba tham số `corePoolSize`, `maximumPoolSize` và `keepAliveTime` là nền tảng, nhưng **không thể hiểu tách rời queue**. Người mới thường nghĩ: “core=2, max=10, vậy khi có 10 request pool sẽ chạy 10 thread”. Đây là nhận định **không đúng trong nhiều cấu hình**: với queue có thể nhận thêm task, pool ưu tiên **xếp hàng sau khi đủ core**, chứ không lập tức tăng lên max.

Sau bài học, bạn có thể:

- Diễn giải chính xác `corePoolSize` (ngưỡng worker lõi), `maximumPoolSize` (trần worker) và `keepAliveTime` (thời gian idle của worker đủ điều kiện được thu hồi).
- Mô tả thứ tự ra quyết định khi `execute(task)`: **tạo core worker → ưu tiên queue → thêm non-core worker khi không queue được → reject khi không còn khả năng nhận**.
- Phân biệt queue **không giới hạn**, queue **có dung lượng giới hạn** và `SynchronousQueue` (handoff trực tiếp) và hiểu vì sao chúng thay đổi hẳn ý nghĩa thực tế của maximumPoolSize.
- Hiểu việc worker được **tạo lười** (lazily), `prestartCoreThread()`, `prestartAllCoreThreads()`, `allowCoreThreadTimeOut(true)` và các giới hạn cấu hình.
- Viết code Java 17+ tạo, quan sát, shutdown một `ThreadPoolExecutor` có giới hạn; tái hiện queue, mở rộng tới max và rejection **không dựa vào sleep để đoán lịch chạy**.
- Biết tác động tới latency, throughput, memory, backpressure, blocking I/O, CPU-bound work và cancellation.
- Tránh lỗi đặt `maximumPoolSize` rất lớn nhưng dùng unbounded queue, giữ worker không cần thiết, bỏ qua `RejectedExecutionException` hoặc để task/blocking chiếm hết pool.

**Phạm vi:** Java SE, `java.util.concurrent` và Executor Framework; không phụ thuộc thư viện hoặc framework bên ngoài. Ví dụ chạy với Java 17+.

## 2. Cấu trúc tổng quan của ThreadPoolExecutor

Một constructor thường gặp:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

ThreadPoolExecutor executor = new ThreadPoolExecutor(
        2,                         // corePoolSize
        4,                         // maximumPoolSize
        30,                        // keepAliveTime
        TimeUnit.SECONDS,          // đơn vị
        new ArrayBlockingQueue<>(8) // workQueue, tối đa 8 task đang đợi
);
~~~

Đây là **đoạn trích dùng trong một method**. Sau khi hoàn tất sử dụng, cần gọi `shutdown()`/`awaitTermination()` phù hợp. Bản thân constructor không tự khởi chạy toàn bộ 2 thread lõi nếu chưa có công việc hoặc chưa prestart.

Hình dung:

~~~text
                      ThreadPoolExecutor
                   ┌──────────────────────────┐
execute(task) ────►│ admission / quyết định   │
                   │                          │
                   │  Worker đang chạy        │
                   │  ┌────────────────────┐  │
                   │  │ core (<= 2)        │  │
                   │  │ extra (<= tổng 4)  │  │
                   │  └────────────────────┘  │
                   │                          │
                   │  Work queue (capacity 8) │
                   │  ┌────────────────────┐  │
                   │  │ task đợi          │  │
                   │  └────────────────────┘  │
                   │                          │
                   │  Reject nếu không nhận   │
                   └──────────────────────────┘
~~~

**Số thread tổng cộng không vượt maximumPoolSize** theo hợp đồng cấu hình (trừ chi tiết vận hành thay thế worker đã chết trong quá trình quản lý, không nên dựa vào snapshot metrics để khẳng định một mốc tức thời tuyệt đối). Task queue và worker pool là **hai thành phần riêng**: queue chứa task chưa chạy; worker đang giữ task có thể đang chạy, block hoặc đợi tài nguyên ngoài.

Để tính đúng capacity và latency, không chỉ nhìn số worker; phải nhìn cả **thời gian thực thi task**, queue capacity, tốc độ task đến, throughput và rejection policy.

## 3. corePoolSize: ngưỡng worker lõi

`corePoolSize` là số lượng worker mà executor cố duy trì khi có công việc, trừ khi chính sách core timeout cho phép chúng chết do idle.

Các quy tắc:

1. Khi `execute(task)` và số worker **ít hơn corePoolSize**, executor ưu tiên tạo thêm một worker để chạy task **ngay cả khi có worker hiện tại đang idle** và chưa vượt ngưỡng core. Đây là mô tả chính sách từ JDK; trên một thread-pool cụ thể, trạng thái workers có thể biến đổi đồng thời.
2. Worker lõi thường được tạo **lazily khi task được submit**, không có nghĩa gọi constructor là đã có đủ core threads.
3. Khi worker count đã đạt corePoolSize, executor thường **thử queue task** trước khi tạo thêm non-core worker.
4. Theo mặc định, core workers không chết chỉ vì idle; nhưng chúng có thể được tạo/thay thế khi bị lỗi, khi pool shutdown hoặc khi bật `allowCoreThreadTimeOut(true)`.
5. `corePoolSize` không phải trần số thread; có thể tăng đến `maximumPoolSize` nếu queue không nhận được task và điều kiện cho phép.

Đừng nhầm `corePoolSize=2` với “luôn tồn tại đúng 2 thread ngay từ lúc khởi tạo” hoặc “chỉ được chạy 2 task”. Pool có thể có 0 worker lúc mới tạo, 2 worker khi tải thấp, và tới max trong điều kiện queue đầy.

### Prestart: khởi chạy core workers trước khi có request

~~~java
executor.prestartCoreThread();     // cố khởi chạy một core thread
executor.prestartAllCoreThreads(); // khởi chạy những core threads còn thiếu
~~~

`prestartCoreThread()` trả boolean tùy có tạo được worker mới hay không, `prestartAllCoreThreads()` trả số worker được khởi chạy thêm. Có thể hữu ích nếu muốn giảm chi phí khởi tạo worker khi request đầu đến, hoặc queue đã có task trước. Tuy nhiên, prestart có chi phí thread/stack và không tự làm các task nhanh hơn về mặt thuật toán.

### corePoolSize bằng 0 có hợp lệ không?

Có, `corePoolSize` được phép là 0 nếu các điều kiện constructor khác hợp lệ (`maximumPoolSize > 0` và không nhỏ hơn core). Khi đó cơ chế nhận công việc và bảo đảm có worker xử lý queue có các chi tiết riêng; không nên suy ra “queue có task nhưng pool sẽ không bao giờ chạy”. Với các bài toán thông thường, chọn một cấu hình core dương giúp dễ dự đoán và theo dõi hơn.

## 4. maximumPoolSize: trần worker, không phải số worker mong muốn

`maximumPoolSize` là **giới hạn trên** của số worker mà pool có thể tạo để phục vụ task trong điều kiện admission phù hợp. Điều kiện cấu hình:

~~~text
0 <= corePoolSize <= maximumPoolSize
maximumPoolSize > 0
~~~

Khi pool đã có core workers và queue vẫn nhận task, nó thường **không tạo thêm worker** dù max lớn. Chỉ khi queue **không nhận thêm task** (ví dụ đã đầy với bounded queue hoặc direct handoff không thể hoàn thành) executor mới thử tạo thêm worker đến trần max.

Do đó:

~~~java
new ThreadPoolExecutor(
        2, 100, 60, TimeUnit.SECONDS,
        new java.util.concurrent.LinkedBlockingQueue<>()
);
~~~

Với `LinkedBlockingQueue` không truyền capacity, giới hạn danh nghĩa rất lớn (`Integer.MAX_VALUE`). Trong hoạt động bình thường, queue tiếp tục nhận task; pool thường chỉ có khoảng core workers, và cấu hình `maximumPoolSize=100` **gần như không được sử dụng để giải quyết backlog**. Queue có thể tăng lớn, tiêu thụ heap và làm request chờ lâu.

Đây là một trong những lỗi cấu hình phổ biến nhất: tăng maximumPoolSize nhưng **quên queue capacity**.

### Khi nào maximumPoolSize thực sự có tác dụng?

Ví dụ `core=2, max=4` và queue capacity 3:
- Hai task đầu được giao cho core workers.
- Các task tiếp theo xếp hàng đến khi đủ 3 task đang đợi.
- Nếu cả hai worker vẫn bận và queue đã đầy, task đến tiếp theo có thể tạo worker thứ 3 rồi thứ 4.
- Khi tổng worker đã bằng 4 và queue vẫn đầy, task đến tiếp theo không thể nhận theo chính sách thường và phải **reject** hoặc xử lý qua một `RejectedExecutionHandler`.

Không nên biến thứ tự trên thành lời hứa “task số 6 luôn chạy ngay trước task số 3”: lịch chạy, thời gian hoàn tất task, và thời điểm worker lấy task từ queue có thể thay đổi. Đây là **quy tắc admission**, không phải trình tự completion/FIFO tuyệt đối cho toàn hệ thống.

## 5. keepAliveTime: giữ worker idle trong bao lâu?

`keepAliveTime` là thời gian một worker **không nhận thêm task** trong khi đang idle có thể được giữ lại trước khi bị thu hồi, với những điều kiện của pool.

Mặc định:
- Khi pool có **nhiều hơn corePoolSize workers**, các worker **vượt core** có thể bị kết thúc sau khi idle quá keepAliveTime.
- Các core workers **không bị thu hồi chỉ vì idle**, trừ khi bật `allowCoreThreadTimeOut(true)`.
- Keep-alive áp dụng cho **thời gian worker chờ công việc mới**, **không** giới hạn thời gian một task đang chạy.
- Khi worker đang làm I/O 1 phút, `keepAliveTime=30s` không khiến task bị ngắt sau 30 giây.
- Khi worker xong việc và tiếp tục lấy được task trong thời hạn, nó có thể tiếp tục được dùng; idle timer không phải TTL tuyệt đối của Thread object.

Ví dụ:

~~~java
ThreadPoolExecutor pool = new ThreadPoolExecutor(
        2, 5,
        30, TimeUnit.SECONDS,
        new ArrayBlockingQueue<>(10)
);
~~~

Nếu pool tạm có 5 workers, khi tải giảm về 0, các worker dư trên core có thể kết thúc sau khi idle đủ 30 giây. Theo chính sách mặc định, các core workers vẫn tồn tại để chờ công việc mới cho tới khi shutdown hoặc thay đổi cấu hình. **Không suy đoán số worker tại đúng mốc 30.000ms** vì scheduler và các thread đang thực thi công việc/đọc queue không có deadline chính xác đến từng mili giây.

### Bật core-thread timeout

~~~java
pool.allowCoreThreadTimeOut(true);
~~~

Khi true, **cả core workers** có thể bị thu hồi sau thời gian idle. Điều kiện: `keepAliveTime` phải **lớn hơn 0**; nếu không, `allowCoreThreadTimeOut(true)` ném `IllegalArgumentException`. Đặt chính sách này **trước khi pool chịu tải** thường dễ hiểu và ít biến động.

Lưu ý `keepAliveTime=0` có thể là cấu hình hợp lệ khi **không** bật core timeout: extra workers được phép kết thúc khi không có việc chờ. Nhưng không thể đặt keepAlive=0 trong lúc core-thread timeout đang bật.

## 6. Thứ tự quyết định quan trọng nhất: execute và workQueue

Tài liệu `ThreadPoolExecutor` mô tả **ba quy tắc tương tác giữa worker size và queue**:

1. **Nếu đang có ít hơn `corePoolSize` workers:** ưu tiên tạo worker mới để chạy task vừa submit, thay vì đưa ngay vào queue.
2. **Nếu đã có ít nhất core workers:** ưu tiên thử đưa task vào `workQueue`, thay vì tạo thêm worker.
3. **Nếu queue không nhận được task:** thử tạo worker mới, miễn tổng worker chưa đạt `maximumPoolSize`; nếu cả điều kiện này cũng thất bại thì áp dụng **rejection handler**.

Sơ đồ admission đơn giản hóa:

~~~text
                   execute(task)
                        |
             workerCount < corePoolSize ?
                 /               \
               có                không
               |                   |
        tạo core worker        queue.offer(task)
        để chạy task             /      \
                              được     không được
                               |          |
                             queued    workerCount < max ?
                                          /       \
                                        có        không
                                        |           |
                               tạo extra worker  reject / handler
                               để chạy task

* Thực tế phải xử lý shutdown, race giữa workers và queue,
  lỗi tạo worker, và việc worker đã biến mất.
~~~

Đây là **mô hình học tập** cho luồng admission. Implementation thực tế có kiểm tra lại trạng thái RUNNING/SHUTDOWN sau queue offer và kiểm soát worker count qua CAS; không nên viết lại sơ đồ trên như một implementation thread-safe đầy đủ.

### Bảng trạng thái với core=2, max=4, queue capacity=3

Giả sử mọi worker xử lý task lâu, không task nào hoàn thành trong lúc submit:

| Task mới | Hành vi điển hình | Worker count | Số task đang chờ |
|---|---|---:|---:|
| #1 | Tạo core worker thứ 1 | 1 | 0 |
| #2 | Tạo core worker thứ 2 | 2 | 0 |
| #3 | Queue | 2 | 1 |
| #4 | Queue | 2 | 2 |
| #5 | Queue | 2 | 3 |
| #6 | Queue đã đầy → tạo extra worker thứ 3 | 3 | 3 |
| #7 | Queue đầy → tạo extra worker thứ 4 | 4 | 3 |
| #8 | Worker đạt max + queue đầy → reject | 4 | 3 |

Các con số này **phụ thuộc giả thiết tất cả workers đang bận**. Nếu worker hoàn tất sớm, nó có thể lấy task từ queue, giải phóng capacity và thay đổi quyết định cho những submit kế tiếp.

## 7. Queue làm thay đổi ý nghĩa ba tham số ra sao?

### 7.1. Unbounded queue: core đóng vai trò chính, max ít được dùng

~~~java
new java.util.concurrent.LinkedBlockingQueue<Runnable>()
~~~

Hàng đợi này có giới hạn danh nghĩa rất lớn, nên `offer(task)` thường thành công. Hệ quả:
- Sau khi có đủ core workers, task đến tiếp tục xếp hàng.
- `maximumPoolSize` thường không tác động tới số worker trong điều kiện bình thường.
- Backlog có thể tăng và tiêu thụ heap khi arrival rate cao hơn processing rate.
- Tail latency có thể rất lớn dù hệ thống không ném RejectedExecutionException.

`Executors.newFixedThreadPool(n)` dùng kiểu queue không giới hạn thực tế và số worker cố định n: phù hợp khi bạn **đã kiểm soát lượng submit**, nhưng không tự tạo backpressure khi producer quá nhanh.

### 7.2. Bounded queue: có trần backlog, max có vai trò khi queue đầy

~~~java
new java.util.concurrent.ArrayBlockingQueue<Runnable>(100)
~~~

Hàng đợi giới hạn 100 task chờ. Khi đã đạt core workers, tasks được queue trước. Chỉ khi queue không còn chỗ, executor mới thử tạo thêm workers tới maximumPoolSize. Nếu đã hết cả hai nguồn capacity, rejection policy bắt đầu phát huy.

Bounded queue giúp **cắt đà tăng memory backlog**, nhưng cần định nghĩa hệ thống phản ứng ra sao với overload. Nếu rejection bị nuốt hoặc được chuyển thành retry không giới hạn, tải vẫn không được điều tiết an toàn.

### 7.3. SynchronousQueue: handoff, không giữ backlog trong queue

~~~java
new java.util.concurrent.SynchronousQueue<Runnable>()
~~~

`SynchronousQueue` không có dung lượng chứa task; nó chỉ **handoff trực tiếp** task cho một worker đang chờ nhận. Nếu không có worker sẵn sàng nhận, `offer` không lưu task để chờ, executor có thể tạo thêm worker đến maximumPoolSize. Khi đạt max mà không có worker nhận, task mới có thể bị reject.

Cấu hình này thường khiến max có tác động rõ hơn; đồng thời có thể làm tăng số threads nhanh nếu tải burst lớn. Cần chọn max và rejection policy phù hợp. `Executors.newCachedThreadPool()` về mặt triển khai dùng mô hình direct handoff với max rất lớn, nên nếu producer không có giới hạn, có thể tạo quá nhiều platform threads.

### So sánh nhanh

| Queue | Đặc điểm | Hệ quả với core/max/keepAlive | Nguy cơ |
|---|---|---|---|
| `LinkedBlockingQueue<>` không truyền capacity | Gần như unbounded | Queue ưu tiên nhận task, max ít phát huy | Backlog/heap, tail latency |
| `ArrayBlockingQueue<>(capacity)` | Bounded | Khi đầy mới tạo extra tới max | Rejection nếu overload, cần policy |
| `SynchronousQueue<>` | Không lưu backlog | Tạo extra sớm hơn khi không handoff được | Bùng nổ số worker nếu max quá cao |
| `LinkedBlockingQueue<>(capacity)` | Bounded linked queue | Tương tự bounded queue, đặc điểm allocation khác | Chi phí memory/queue contention |

Không có queue “tốt nhất” trong mọi workload. Hàng đợi là một **phần bắt buộc của quyết định sizing**, không thể chọn core/max/keepAlive trước rồi bỏ qua queue.

## 8. Ví dụ Java 17+ xác định: core → queue → extra → reject

Chương trình dùng `CountDownLatch` để giữ worker 1 và worker 2 đang bận. Lúc đó queue capacity 1 chứa đúng một task. Submit thêm task thứ 4 sẽ bị reject theo `AbortPolicy`.

Lưu tệp **ThreadPoolSizingDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class ThreadPoolSizingDemo {
    private static void awaitGate(CountDownLatch gate) {
        try {
            gate.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 2,
                10, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy()
        );

        CountDownLatch coreStarted = new CountDownLatch(1);
        CountDownLatch extraStarted = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        boolean rejected = false;
        try {
            // Task 1: tạo core worker, giữ nó bận.
            pool.execute(() -> {
                coreStarted.countDown();
                awaitGate(release);
            });
            coreStarted.await();

            // Task 2: core đã bận -> vào queue capacity 1.
            pool.execute(() -> { });

            // Task 3: queue đầy -> tạo worker thứ 2 (extra).
            pool.execute(() -> {
                extraStarted.countDown();
                awaitGate(release);
            });
            extraStarted.await();

            // Task 4: core/extra đều bận, queue vẫn đầy -> reject.
            try {
                pool.execute(() -> { });
            } catch (RejectedExecutionException e) {
                rejected = true;
            }

            System.out.println("poolSize=" + pool.getPoolSize());
            System.out.println("queued=" + pool.getQueue().size());
            System.out.println("rejected=" + rejected);
        } finally {
            // Giải phóng cả hai workers trên mọi đường đi.
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }

        System.out.println("completed=" + pool.getCompletedTaskCount());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ThreadPoolSizingDemo.java
java ThreadPoolSizingDemo
~~~

Output trong điều kiện các task không bị interrupt ngoài và executor kết thúc bình thường:

~~~text
poolSize=2
queued=1
rejected=true
completed=3
~~~

**Giải thích tính xác định:**

1. Main đợi `coreStarted.await()`: task 1 đang ở worker lõi và chưa thể kết thúc vì `release` còn đóng.
2. Task 2 được submit khi core worker đang bận, nên được đưa vào queue có capacity 1; chưa có worker nào được giải phóng để lấy task này.
3. Task 3 đến khi queue đã đầy. Pool còn dưới maximumPoolSize=2 nên tạo worker thứ hai. Main đợi `extraStarted` để chắc chắn worker thứ hai đã bắt đầu và đang chờ release.
4. Task 4 không thể đưa vào queue và cũng không thể tạo worker thứ ba, nên `AbortPolicy` ném `RejectedExecutionException`; main bắt và ghi rejected=true.
5. Trước khi mở latch, pool có đúng 2 workers bận và 1 task chờ; hai metrics `poolSize` và `queued` phản ánh điều kiện cố định trong ví dụ.
6. Trong `finally`, main mở gate, shutdown graceful, đợi pool kết thúc. Ba task được nhận (1, 2, 3) hoàn thành; task 4 bị từ chối không chạy. Vì thế completed=3.

**Điểm thực hành:** Latch trong ví dụ này **được dùng để dựng lịch chạy và chứng minh admission policy**, không phải cấu trúc chung phải đưa vào mọi production pool. Trong thực tế task có thể hoàn tất trước khi task kế tiếp được submit nên không nên suy số workers/queue từ **số thứ tự request**.

### Tại sao không dùng sleep để ép queue đầy?

`Thread.sleep(100)` chỉ khiến thread hiện tại nghỉ một khoảng, không bảo đảm task nào đã bắt đầu hoặc còn đang bận trên máy khác. `CountDownLatch` tạo thứ tự rõ ràng, cho phép chương trình minh họa chính sách sizing chứ không dựa vào may rủi scheduler.

## 9. Ví dụ đối chứng: unbounded queue không tự mở rộng tới maximum

Với `LinkedBlockingQueue<>` mặc định, khi core worker đang bận, các task khác vào queue thay vì kích hoạt extra workers. Ta có thể kiểm chứng bằng ví dụ ngắn.

Lưu tệp **UnboundedQueueDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class UnboundedQueueDemo {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 5,
                30, TimeUnit.SECONDS,
                new LinkedBlockingQueue<>()
        );

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            pool.execute(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });
            started.await();

            // Worker lõi đang bận. Hai task này được xếp hàng.
            pool.execute(() -> { });
            pool.execute(() -> { });

            System.out.println("poolSize=" + pool.getPoolSize());
            System.out.println("queued=" + pool.getQueue().size());
            System.out.println("maximum=" + pool.getMaximumPoolSize());
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac UnboundedQueueDemo.java
java UnboundedQueueDemo
~~~

Output trong trường hợp bình thường:

~~~text
poolSize=1
queued=2
maximum=5
~~~

Dù maximum=5, pool **không cần tạo thêm** workers khi queue vẫn có thể tiếp nhận task. Đây là lý do cần kiểm tra `workQueue` trước khi tăng maximumPoolSize trong một ứng dụng có backlog lớn.

## 10. Ví dụ cấu hình keepAliveTime và core timeout

Ví dụ dưới đây minh họa API cấu hình, tránh dùng `sleep` rồi đo chính xác worker count tại một thời điểm dễ bị ảnh hưởng bởi scheduler.

Lưu tệp **CoreTimeoutConfigDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class CoreTimeoutConfigDemo {
    public static void main(String[] args) {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                2, 4, 15, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(8)
        );

        try {
            pool.allowCoreThreadTimeOut(true);

            System.out.println("core=" + pool.getCorePoolSize());
            System.out.println("max=" + pool.getMaximumPoolSize());
            System.out.println("keepAliveSeconds=" +
                    pool.getKeepAliveTime(TimeUnit.SECONDS));
            System.out.println("coreCanTimeOut=" +
                    pool.allowsCoreThreadTimeOut());
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac CoreTimeoutConfigDemo.java
java CoreTimeoutConfigDemo
~~~

Output:

~~~text
core=2
max=4
keepAliveSeconds=15
coreCanTimeOut=true
~~~

Phần cấu hình trên **không** yêu cầu pool đã tạo đủ hai core workers. Vì không submit task và không gọi prestart, số worker có thể vẫn bằng 0. `allowCoreThreadTimeOut(true)` chỉ thay **chính sách tồn tại của core workers sau khi idle**, không ra lệnh hủy workers đang chạy.

### Khi nào bật core timeout?

Có thể hữu ích khi:
- Tải đến theo các đợt cách xa nhau, mỗi đợt sử dụng nhiều platform threads.
- Muốn giảm tài nguyên khi idle lâu, chấp nhận chi phí tái tạo worker khi traffic quay lại.
- Không cần duy trì threads warm để tối thiểu hóa thời gian khởi động task kế tiếp.

Không nên bật chỉ vì “tiết kiệm thread” mà bỏ qua độ trễ cold-start hoặc burst latency. Cần đo workload thực tế và cân nhắc `ThreadFactory`, công việc đầu tiên cần làm, tài nguyên hệ điều hành và memory.

## 11. Rejection policy là phần thiết kế capacity, không phải chi tiết phụ

Nếu pool vẫn chạy nhưng **queue đã không nhận thêm task** và **worker count đã đạt max**, một task mới được xử lý qua `RejectedExecutionHandler`. Executor cũng có thể reject task khi đã shutdown.

Các handler tích hợp:

| Handler | Hành vi điển hình khi reject | Cần lưu ý |
|---|---|---|
| `AbortPolicy` (mặc định) | Ném `RejectedExecutionException` | Caller phải xử lý quá tải / lỗi rõ ràng. |
| `CallerRunsPolicy` | Caller chạy task **trong thread gọi submit**, nếu executor chưa shutdown | Tạo backpressure gián tiếp nhưng có thể kéo dài latency và làm code chạy ở thread bất ngờ. Nếu shutdown, task bị bỏ. |
| `DiscardPolicy` | Bỏ task mà không ném | Nguy hiểm nếu task là công việc bắt buộc; dễ mất dữ liệu im lặng. |
| `DiscardOldestPolicy` | Bỏ task đầu queue rồi thử gửi task mới | Có thể mất task cũ; với priority queue và một số cấu hình, hành vi có thể đặc biệt nguy hiểm. Cần xem shutdown và retry. |

Không có handler nào tự đảm bảo mọi yêu cầu nghiệp vụ được xử lý “exactly once”. Nếu task là đơn hàng, giao dịch hoặc công việc phải được lưu bền vững, cần đường tiếp nhận và lưu queue đáng tin cậy ở đúng tầng hệ thống. Trong một JVM, rejected task chưa được nhận/commit không nên bị log thành thành công.

### CallerRunsPolicy có ý nghĩa backpressure như thế nào?

Khi pool quá tải, thread submit phải **trực tiếp chạy task**, nên nó không thể tiếp tục submit thật nhanh. Điều này có thể giúp cân bằng tốc độ producer/consumer. Nhưng nếu thread submit là event loop hoặc thread cần phản hồi nhanh, tác vụ chạy tại đó sẽ **chặn đường xử lý chính**. Không dùng CallerRunsPolicy theo thói quen mà không xác định caller thread có được phép chạy công việc đó hay không.

### AbortPolicy là lựa chọn minh bạch

Một ứng dụng có thể bắt `RejectedExecutionException` và báo “quá tải / thử lại sau” hoặc chuyển công việc sang kênh xử lý khác. Không retry vô hạn ngay tại thread đã submit: retry lập tức tạo thêm contention và không giảm áp lực hệ thống.

## 12. keepAliveTime không phải timeout của task

Đây là ba giới hạn thời gian hoàn toàn khác nhau:

| Cấu hình/API | Điều gì bị giới hạn? | Có hủy task đang chạy? |
|---|---|---|
| `keepAliveTime` | Thời gian worker **idle** có thể đợi task mới trước khi được thu hồi theo policy | **Không** |
| `Future.get(timeout, unit)` | Thời gian **caller chờ kết quả** | **Không** tự hủy task |
| `Future.cancel(true)` | Yêu cầu hủy Future và cố interrupt worker khi phù hợp | Chỉ **nỗ lực** hủy; cần task hợp tác |
| Timeout tại I/O API | Thời gian đợi của **hoạt động I/O tương ứng** | Tùy API/loại tài nguyên |
| `awaitTermination(timeout, unit)` | Thời gian đợi **executor kết thúc** | Không tự kill worker |

Ví dụ một task giữ worker để chờ network 90 giây không bị `keepAliveTime=10s` cưỡng bức dừng giữa chừng. Vì task **không idle**, clock keep-alive không giải quyết long-running tasks.

Nếu muốn deadline nghiệp vụ, cần thiết kế timeout ở nơi task đang block, cancellation và cleanup phù hợp. Không dùng việc tăng/giảm keepAlive để thay thế quản lý timeout của request.

## 13. corePoolSize và CPU-bound vs blocking workload

### CPU-bound work

Các task tính toán liên tục sử dụng CPU:
- Không nên mở quá nhiều platform worker threads so với khả năng CPU chỉ để tăng số “threads”.
- Khi số runnable threads vượt số core CPU quá nhiều, overhead context switching có thể tăng và throughput không nhất thiết tốt hơn.
- Một pool gần với số CPU cores hữu ích là **điểm bắt đầu để benchmark**, không phải công thức cứng.
- Bounded queue có thể giúp giữ memory ổn định khi nguồn task đến nhanh hơn tốc độ tính toán.

Ví dụ:

~~~java
int cores = Runtime.getRuntime().availableProcessors();
int workers = Math.max(1, cores);
~~~

Đây là đoạn trích minh họa; `availableProcessors()` phụ thuộc môi trường/container và không tự biết workload thật. Việc chọn size nên xét CPU quota, parallelism của các module khác, GC, contention và yêu cầu latency.

### Blocking I/O workload

Nếu worker thường **chờ I/O** hơn là tính toán, việc có nhiều workers hơn số CPU cores đôi khi cải thiện concurrency:
- Tuy nhiên, mỗi platform thread vẫn có stack, scheduler và resource overhead.
- Quá nhiều worker có thể làm quá tải connection pool, disk, remote service hoặc memory.
- Với I/O blocking, giới hạn **downstream resource concurrency** và queue capacity thường quan trọng không kém thread count.
- Đo active threads, queue depth, thời gian I/O, rejection, external service saturation và tail latency.

Trong Java 21+, **virtual threads** cung cấp mô hình khác cho nhiều nhiệm vụ blocking: `Executors.newVirtualThreadPerTaskExecutor()` tạo virtual thread cho mỗi task thay vì giữ một pool platform workers cố định. Nhưng đó **không** phải cách tự điều tiết độ lớn connection pool hoặc quota của tài nguyên ngoài. Khi cần giới hạn số yêu cầu đồng thời, sử dụng semaphore, bounded work admission hoặc quota tương ứng. `corePoolSize`/`maximumPoolSize`/`keepAliveTime` vẫn là các tham số trực tiếp của `ThreadPoolExecutor` cho workers theo mô hình pool.

## 14. Quan sát pool: giá trị cấu hình vs metrics tại một thời điểm

Các API thường dùng:

~~~java
pool.getCorePoolSize();
pool.getMaximumPoolSize();
pool.getKeepAliveTime(TimeUnit.SECONDS);
pool.getPoolSize();
pool.getActiveCount();
pool.getQueue().size();
pool.getCompletedTaskCount();
pool.getLargestPoolSize();
pool.getTaskCount();
~~~

Các số có thể chia thành hai nhóm:

**Thông số cấu hình:** corePoolSize, maximumPoolSize, keepAliveTime, loại queue, policy cho core timeout, RejectedExecutionHandler.

**Metrics biến động:** poolSize (workers hiện tại), activeCount (ước lượng workers đang chạy task), completedTaskCount (ước lượng số task đã xong), taskCount (ước lượng tổng task), queue size (số task đang đợi tại thời điểm quan sát).

**Đừng coi các API thống kê là snapshot transaction đồng thời.** Pool hoạt động liên tục; trong lúc bạn đọc activeCount rồi queue size, task có thể được hoàn thành/submit. Các hàm thống kê của `ThreadPoolExecutor` cung cấp dữ liệu để monitoring/tuning, không phải primitive đồng bộ cho quy tắc admission.

Một số metrics giúp chẩn đoán:

| Triệu chứng | Quan sát cần kiểm tra | Hướng suy luận |
|---|---|---|
| Queue dài, worker không tăng tới max | Queue unbounded hoặc vẫn còn chỗ | Executor ưu tiên queue sau core |
| ActiveCount luôn gần poolSize, queue tăng | Task chậm, downstream block, arrival cao | Đo service time, workload và bounded capacity |
| Pool tăng max rồi reject nhiều | Tải vượt capacity | Admission/backpressure, timeouts, rate limit |
| Pool thường chỉ còn core sau idle | Non-core workers bị thu hồi theo keepAlive | Hành vi thường đúng policy |
| Pool về 0 sau idle dù core > 0 | Đã bật core-thread timeout? | Kiểm tra `allowsCoreThreadTimeOut()` |
| Latency rất cao mà ít rejection | Unbounded queue backlog | Tăng max chưa chắc giải quyết nếu queue vẫn nhận |
| “Task biến mất” khi đầy | DiscardPolicy/DiscardOldest/CallerRuns khi shutdown | Kiểm tra handler và ghi nhận accepted/rejected |

## 15. Thay đổi cấu hình khi pool đang chạy

`ThreadPoolExecutor` có setter:

~~~java
pool.setCorePoolSize(newCore);
pool.setMaximumPoolSize(newMax);
pool.setKeepAliveTime(20, TimeUnit.SECONDS);
pool.allowCoreThreadTimeOut(true);
~~~

Đoạn này là minh họa trong một method có `pool` và các biến cấu hình. Những method setter có thể được gọi khi pool hoạt động nhưng **không thay đổi mọi worker cùng một lúc theo kiểu transaction**. Các worker có thể được bổ sung, bị thu hồi khi idle hoặc có công việc chờ tùy chính sách.

### Ràng buộc cấu hình

- `corePoolSize` phải >= 0.
- `maximumPoolSize` phải > 0 và >= corePoolSize.
- `keepAliveTime` phải >= 0; nếu core timeout đang bật thì không được đặt keepAlive=0.
- `allowCoreThreadTimeOut(true)` đòi keepAlive > 0.
- Các phép thay đổi thứ tự setter cần tôn trọng ràng buộc **tại từng bước**.

Ví dụ hiện tại `core=4, max=8` và muốn đổi thành `core=10, max=12`. Không thể gọi `setCorePoolSize(10)` **trước** khi tăng maximum lên ít nhất 10. Ngược lại, khi muốn thu max dưới core hiện tại, phải giảm core trước. Nếu nhiều thread cấu hình executor đồng thời, cần một giao thức quản trị rõ ràng để tránh các trạng thái trung gian không hợp lệ.

### Không dựa vào tuning để sửa bug correctness

Điều chỉnh core/max/queue chỉ ảnh hưởng cách sắp lịch và giới hạn công việc. Nó **không làm một shared counter++ tự atomic**, không sửa race trong task, không biến state mutable thành thread-safe và không giảm tính phức tạp của transaction bên ngoài. Task logic vẫn cần synchronization/ownership phù hợp.

## 16. shutdown đúng cách và vòng đời worker

Một pool cần được quản lý vòng đời để tránh thread leak hoặc khiến JVM không kết thúc.

~~~java
ThreadPoolExecutor pool = new ThreadPoolExecutor(
        2, 4, 30, TimeUnit.SECONDS,
        new ArrayBlockingQueue<>(50)
);

try {
    pool.execute(() -> System.out.println("work"));
} finally {
    pool.shutdown();
    try {
        if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                System.err.println("Some tasks did not terminate");
            }
        }
    } catch (InterruptedException e) {
        pool.shutdownNow();
        Thread.currentThread().interrupt();
    }
}
~~~

Đây là đoạn trong một method Java hợp lệ. `shutdown()` ngừng nhận tasks mới nhưng các tasks đã nhận tiếp tục được xử lý theo policy. `shutdownNow()` **chỉ nỗ lực** dừng workers đang chạy (thường thông qua interrupt) và trả về các tasks chưa khởi động mà nó lấy khỏi queue; nó không bảo đảm mọi tác vụ bất kỳ lập tức chấm dứt.

Khi task đang block ở API không interruptible, shutdownNow có thể không giải phóng được nó. Cần dùng timeout, đóng tài nguyên hoặc cancellation hook theo hợp đồng của tác vụ. Không nhầm `keepAliveTime` với thời gian đợi shutdown, cũng không nhầm timeout của `awaitTermination` với lệnh cưỡng bức kill.

### Trách nhiệm của task

- Phản ứng `InterruptedException` phù hợp, không nuốt interrupt rồi chạy mãi.
- Cleanup trong `finally`/`try-with-resources`.
- Giữ shared state nhất quán nếu bị cancel.
- Tránh giữ lock trong khi blocking lâu nếu không cần.
- Không tạo task phụ vô hạn trong cùng pool nhỏ khiến task cha chờ task con mà pool không còn worker rảnh (thread-starvation deadlock).

## 17. Sai lầm thường gặp: task chờ Future khác trong cùng pool

Ví dụ:
- Pool có core=max=1, một worker duy nhất.
- Task A chạy trên worker đó và submit task B vào **cùng pool**.
- Task A gọi `futureB.get()`, đợi B kết thúc.
- B nằm trong queue, nhưng worker duy nhất đang bị A giữ và chờ B.

Nếu không có worker khác để thực thi B, ứng dụng có thể **bị treo**. Tăng maximumPoolSize sẽ không cứu được nếu queue unbounded nhận B nhưng executor không tạo thêm worker. Đây là ví dụ điển hình cho việc queue semantics tác động tới liveness, không chỉ throughput.

Giải pháp cần cân nhắc:
- Tránh chờ đồng bộ task con trong cùng fixed-size pool.
- Thiết kế composition bất đồng bộ hoặc phân tách pools có trách nhiệm rõ ràng.
- Điều chỉnh capacity/queue đúng mô hình dependency, nhưng không phụ thuộc vào việc “max lớn là đủ”.
- Nếu cần blocking để đợi kết quả, đảm bảo pool có khả năng tiến triển mà không vòng phụ thuộc chờ nhau.

## 18. Cấu hình tối ưu có công thức cố định không?

Không có một bộ ba core/max/keepAlive tối ưu cho mọi workload. Cần xét:

1. **Task duration:** CPU time vs thời gian chờ.
2. **Arrival rate:** số task đến mỗi giây, burstiness.
3. **SLO:** p95/p99 latency và tỷ lệ lỗi/rejection chấp nhận.
4. **Queue budget:** memory cho backlog, độ trễ tối đa trước khi task bắt đầu.
5. **Downstream limits:** DB connections, remote API quotas, file handles.
6. **CPU/GC:** số cores thực tế, heap, thread stack, allocation rate.
7. **Timeout/cancellation:** request quá hạn có được hủy khỏi queue hay vẫn chiếm memory?
8. **Rejection handling:** có đủ điều kiện chấp nhận việc mất/thử lại task?
9. **Thay đổi theo tải:** traffic đều hay theo burst, cần worker warm hay thu hồi nhanh?
10. **Quan sát thực tế:** queue length, activeCount, task service time, completed count, timeout/rejection và tail latency.

Một cách thử có trách nhiệm:
- Xác định tối đa số task được phép **đồng thời xử lý** và tối đa số task được phép **đợi**.
- Chọn bounded queue và rejection/backpressure theo ý nghĩa nghiệp vụ.
- Bắt đầu từ core/max phù hợp workload; đo workload thật hoặc load test có tính đại diện.
- Đánh giá keepAliveTime theo burst spacing và chi phí khởi tạo worker, không dùng keepAlive để điều khiển runtime task.
- Kiểm tra shutdown và overload behavior, không chỉ kịch bản tải vừa phải.

## 19. Các lỗi phổ biến và cách sửa

**Lỗi 1 — “max=50 nên pool sẽ tạo 50 worker khi có 50 task.”** Không nếu queue tiếp tục nhận task. Sau core, queue được ưu tiên.

**Lỗi 2 — Đặt unbounded queue rồi ngạc nhiên vì poolSize gần core.** Đó là hệ quả admission policy. Dùng bounded queue/queue khác nếu cần max phát huy đúng với contract của workload.

**Lỗi 3 — Dùng keepAliveTime để giới hạn thời gian thực thi một task.** Sai. Keep-alive là idle-worker policy; task timeout phải xử lý riêng.

**Lỗi 4 — Coi corePoolSize là số workers được tạo ngay ở constructor.** Core workers mặc định lazily created; dùng prestart nếu cần.

**Lỗi 5 — Đặt keepAlive=0 rồi bật allowCoreThreadTimeOut(true).** Không hợp lệ; phải có keepAlive > 0 cho core timeout.

**Lỗi 6 — Chọn max vô cùng lớn với SynchronousQueue rồi coi pool tự bảo vệ tài nguyên.** Pool có thể tạo quá nhiều threads, gây quá tải hệ thống. Cần ràng buộc thực.

**Lỗi 7 — Chọn AbortPolicy nhưng không bắt RejectedExecutionException.** Task có thể không được nhận; caller phải hiểu và báo outcome.

**Lỗi 8 — Dùng DiscardPolicy cho công việc bắt buộc.** Có nguy cơ mất task im lặng. Phải có giao thức không mất dữ liệu phù hợp.

**Lỗi 9 — Dùng CallerRunsPolicy mà không kiểm tra caller context.** Caller có thể chạy task blocking và kéo dài latency của request/event loop.

**Lỗi 10 — Dùng queue vô hạn để “tránh reject”.** Thường chỉ chuyển lỗi overload thành memory pressure và latency kéo dài.

**Lỗi 11 — Không shutdown pool.** Workers có thể giữ resource và vòng đời JVM; cần ownership rõ ràng.

**Lỗi 12 — Cho rằng shutdownNow kill mọi task.** Nó nỗ lực interrupt, nhưng task phải hợp tác. Cần cleanup/await/deadline.

**Lỗi 13 — Tăng max để sửa thread-starvation deadlock nhưng queue vẫn unbounded.** Queue vẫn nhận task con trong khi worker cha chờ; phải xem mô hình dependency.

**Lỗi 14 — Tin rằng activeCount/queueSize là snapshot bất biến.** Metrics đổi liên tục; dùng cho monitoring, không cho check-then-act correctness.

**Lỗi 15 — Đổi core/max theo thứ tự khiến core > max tạm thời.** Setter có validation; phải lên kế hoạch thứ tự phù hợp.

**Lỗi 16 — Cho rằng CPU-bound và I/O-bound dùng cùng bộ tham số.** Đặc điểm block và downstream resource làm lựa chọn khác nhau.

**Lỗi 17 — Dùng thread pool để che race condition trong task.** Executor quản lý lịch chạy, không tự đồng bộ mutable state mà tasks cùng sửa.

**Lỗi 18 — Nhầm queue size với tổng task đang hoạt động.** Queue chỉ có tasks **chưa chạy**; active workers đang xử lý tasks ngoài queue.

## 20. Checklist review một ThreadPoolExecutor

- Xác định rõ `corePoolSize`, `maximumPoolSize`, `keepAliveTime` và `TimeUnit`.
- Có biết loại `BlockingQueue` và **capacity thật sự** không?
- Có hiểu quy tắc **core → queue → extra → reject** trong tải giả định không?
- Với unbounded queue, đã biết maximumPoolSize thường không giúp backlog chưa?
- Với bounded queue, đã mô tả behavior khi queue đầy và worker đạt max chưa?
- Đã xác định policy cho rejected tasks, tránh mất việc im lặng chưa?
- `allowCoreThreadTimeOut` có bật không, keepAlive có >0 khi bật không?
- Có cần prestart core workers hay chấp nhận lazy startup?
- Workers làm CPU-bound, blocking I/O hay hỗn hợp? Có downstream concurrency limit?
- Có task cha chờ task con trong cùng pool? Có nguy cơ starvation deadlock?
- Có policy timeout/cancellation riêng cho task, không dùng keepAlive thay thế?
- Có metrics về active workers, queue depth, rejection, task duration và tail latency?
- Đã thiết kế `shutdown`, `awaitTermination`, `shutdownNow` và cleanup an toàn?
- Đã load-test cả burst và overload, không chỉ happy path?

## 21. Câu hỏi tự luyện và đáp án

**Câu 1.** Pool có core=2, max=16, queue `LinkedBlockingQueue<>` mặc định. Sau khi có hai worker, submit thêm 100 task lâu. Pool có tự tăng lên 16 worker không?

**Đáp án:** Thông thường không. Queue tiếp tục nhận task, nên executor ưu tiên queue sau core. MaximumPoolSize có rất ít tác dụng nếu queue hầu như không đầy.

**Câu 2.** Pool có core=2, max=4, bounded queue capacity=3. Hai worker đang bận, queue đang có 3 task, thêm 1 task thì sao?

**Đáp án:** Executor có thể tạo worker thứ 3 để chạy task đến, vì queue không nhận thêm và tổng worker còn dưới max.

**Câu 3.** Nếu pool đã có 4 workers đều bận, queue capacity=3 đã đầy, một task mới đến thì sao?

**Đáp án:** Executor áp dụng `RejectedExecutionHandler`, hoặc ném `RejectedExecutionException` nếu dùng AbortPolicy.

**Câu 4.** keepAlive=5 giây, một task đang chạy 30 giây. Task có bị tự ngắt ở giây thứ 5 không?

**Đáp án:** Không. Keep-alive áp dụng thời gian worker **idle**, không giới hạn thời gian task đang chạy.

**Câu 5.** core=3 nhưng gọi constructor xong chưa submit task. Có chắc poolSize=3 không?

**Đáp án:** Không. Workers được tạo lazily; có thể poolSize=0 nếu chưa prestart.

**Câu 6.** Bật allowCoreThreadTimeOut(true) khi keepAliveTime=0 được không?

**Đáp án:** Không. API yêu cầu keepAliveTime > 0 cho core-thread timeout.

**Câu 7.** Vì sao CallerRunsPolicy có thể tạo backpressure nhưng lại nguy hiểm cho một event-loop thread?

**Đáp án:** Khi pool quá tải, caller trực tiếp chạy task, làm nó không submit tiếp được nhanh; nhưng event-loop sẽ bị chiếm bởi task, ảnh hưởng latency và khả năng phục vụ các sự kiện khác.

**Câu 8.** `Future.get(100, MILLISECONDS)` timeout có khiến worker pool thu hồi thread hay hủy task ngay không?

**Đáp án:** Không. Đây chỉ là timeout của caller khi chờ Future, độc lập với keepAlive/worker lifecycle và cancellation.

**Câu 9.** Nếu dùng `SynchronousQueue`, queue có thể giữ 100 task chờ không?

**Đáp án:** Không. Đây là direct-handoff queue, không lưu backlog; khi không handoff được, pool có thể tăng workers tới max hoặc reject tùy cấu hình.

**Câu 10.** Pool có một worker đang chạy task A; A submit B vào cùng pool rồi gọi Future.get(), trong khi B chờ trong queue. Nguy cơ gì?

**Đáp án:** Thread-starvation deadlock: worker duy nhất đợi B, nhưng B không có worker để chạy. Phải thay thiết kế dependency hoặc capacity/admission phù hợp.

## 22. Tài liệu tham khảo chính thức

- **ThreadPoolExecutor — Java SE 21:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- **ExecutorService — Java SE 21:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html
- **BlockingQueue — Java SE 21:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/BlockingQueue.html
- **ArrayBlockingQueue — Java SE 21:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html
- **LinkedBlockingQueue — Java SE 21:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/LinkedBlockingQueue.html
- **SynchronousQueue — Java SE 21:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/SynchronousQueue.html
- **ThreadPoolExecutor.RejectedExecutionHandler — Java SE 21:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/RejectedExecutionHandler.html
- **TimeUnit — Java SE 21:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/TimeUnit.html

**Kết luận:** Ba tham số **`corePoolSize`**, **`maximumPoolSize`** và **`keepAliveTime`** chỉ có ý nghĩa đúng khi đặt cạnh **workQueue** và **rejection policy**. Pool thường tạo tới core, sau đó queue, khi queue không nhận nữa mới mở rộng tới max, và cuối cùng reject khi cả workers lẫn queue đã hết capacity. Keep-alive thu hồi **worker idle**, không hủy task dài. Cấu hình đúng phải bảo vệ đồng thời **throughput, độ trễ, memory, tài nguyên ngoài và hành vi khi quá tải**.
