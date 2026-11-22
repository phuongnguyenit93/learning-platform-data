# Khả năng quan sát active count, queue size, completed tasks trong Java Executor Framework

## 1. Tại sao cần quan sát thread pool?

Khi sử dụng `ExecutorService`, chương trình giao task cho executor thay vì tự tạo từng `Thread`. Nhưng một hệ thống đang chạy cần biết: có bao nhiêu worker đang thực hiện task, bao nhiêu task đang đợi, bao nhiêu task đã kết thúc, pool đã chạm giới hạn hay chưa, và việc xử lý có đang chậm dần?

Với `java.util.concurrent.ThreadPoolExecutor`, ba phép quan sát thường gặp là:

- **`getActiveCount()`:** ước lượng số thread trong pool hiện đang **thực thi task**.
- **`getQueue().size()`:** số phần tử hiện có trong **work queue** của pool, thường là task đang chờ worker lấy ra, **không gồm task đang chạy**.
- **`getCompletedTaskCount()`:** ước lượng tổng số task đã **hoàn tất thực thi trong các worker của pool**, tính từ khi executor được tạo.

Những chỉ số này giúp phát hiện backlog, theo dõi tải và hỗ trợ điều chỉnh dung lượng. Tuy nhiên, chúng không phải một **snapshot nguyên tử của toàn bộ executor**, không phải kết quả nghiệp vụ “thành công” và **không thể tự dùng để quyết định chắc chắn** liệu một lần `execute()`/`submit()` tiếp theo có được chấp nhận hay không.

Bài học này thuộc chủ đề **Executor Framework** của Java concurrency nói chung, minh họa bằng Java 17+ và API JDK, không gắn với framework hoặc cấu hình ứng dụng cụ thể.

## 2. Nắm vòng đời task để đọc đúng số liệu

Một task trong `ThreadPoolExecutor` có thể đi qua các giai đoạn:

```text
Ứng dụng gửi task
       |
       v
Executor quyết định
       |
       +--> Worker nhận và thực thi ngay
       |
       +--> Work queue chờ worker trống
       |
       +--> Rejection handler (khi không thể nhận theo chính sách)
                    |
                    +--> Ném ngoại lệ / bỏ task / chạy ở caller / cách khác
                            
Task chạy trong worker --> Kết thúc run/call --> Completed-task accounting
```

**Không đồng nhất ba số đo:**

| Chỉ số | Đo điều gì | Không đo điều gì |
| --- | --- | --- |
| `getActiveCount()` | Ước lượng worker đang thực thi task | Không nhất thiết là số thread đang sử dụng CPU; task chờ I/O vẫn có thể được tính là active |
| `getQueue().size()` | Số task còn nằm trong work queue tại thời điểm lấy mẫu | Không bao gồm task đã được worker lấy khỏi queue; không phải độ trễ chờ |
| `getCompletedTaskCount()` | Ước lượng số task đã hoàn tất xử lý trong pool | Không cho biết bao nhiêu task thành công, bao nhiêu thất bại hay bao nhiêu kết quả đã được caller nhận |
| `getPoolSize()` | Số worker thread hiện có trong pool | Không phải số worker thực sự active |
| `getLargestPoolSize()` | Số worker lớn nhất từng tồn tại đồng thời trong pool | Không phải ngưỡng cấu hình tối đa hoặc mức tải hiện tại |
| `getTaskCount()` | Ước lượng số task từng được lập lịch cho pool | Không phải số request người dùng hoàn thành hoặc số task thực sự thành công |

Đặc biệt, `getCompletedTaskCount()` không nên đặt tên dashboard là “successful jobs”. Một task có thể kết thúc bằng exception, bị hủy, hoặc hoàn tất execution nhưng nghiệp vụ thất bại. `submit()` thường bọc task trong `FutureTask`: exception được lưu trong `Future` để caller gọi `get()` nhận `ExecutionException`; task vẫn có thể được tính đã hoàn tất bởi executor.

### “Active” có tính cả worker đang đợi bên trong task không?

Có thể có. Nếu worker **đang chạy `Runnable.run()`** nhưng bị chặn trong `queue.take()` khác, truy vấn I/O hoặc chờ lock, nó vẫn đang thực thi task của executor ở nghĩa quản lý worker. `getActiveCount()` không phải CPU utilization. Thread của pool **rảnh chờ lấy task kế tiếp** thì không tính active theo ý nghĩa của metric này.

Do đó nên đối chiếu active count với queue length, thời gian chạy task, độ trễ queue và sử dụng CPU, thay vì chỉ nhìn một số.

## 3. Đọc số liệu từ đâu?

`ExecutorService` là interface tổng quát, **không có** các phương thức `getActiveCount()`, `getCompletedTaskCount()` hay `getQueue()`. Những phép quan sát này là API của **`ThreadPoolExecutor`**.

Khởi tạo trực tiếp một pool cấu hình rõ ràng:

```java
ThreadPoolExecutor executor = new ThreadPoolExecutor(
        2,                         // corePoolSize
        4,                         // maximumPoolSize
        30, TimeUnit.SECONDS,      // keepAliveTime
        new ArrayBlockingQueue<>(20)
);

int active = executor.getActiveCount();
int queued = executor.getQueue().size();
long completed = executor.getCompletedTaskCount();
```

Đây là **snippet**, cần import `ThreadPoolExecutor`, `ArrayBlockingQueue` và `TimeUnit`, và phải shutdown executor khi xong. Không ép một `ExecutorService` bất kỳ thành `ThreadPoolExecutor` nếu không biết implementation: nó có thể là wrapper, một executor khác hoặc implementation không hỗ trợ các metric trên.

`Executors.newFixedThreadPool(n)` trong JDK thường tạo `ThreadPoolExecutor` phía dưới, nhưng API khai báo trả `ExecutorService`; nếu code cần metric triển khai cụ thể, tốt nhất **nắm trực tiếp tham chiếu `ThreadPoolExecutor` lúc khởi tạo** hoặc cung cấp một interface monitoring riêng, thay vì downcast tùy tiện.

`Executors.newWorkStealingPool()` dựa trên mô hình khác; `ForkJoinPool` có tập metric riêng như `getActiveThreadCount()`, `getQueuedTaskCount()`. Không áp nguyên xi cách hiểu queue và active của `ThreadPoolExecutor` cho mọi executor.

## 4. Java 17+: ví dụ quan sát pool với lịch chạy được kiểm soát

Để hiểu các số đo, ta tạo một pool **2 worker** và work queue chứa tối đa **3 task**. Năm task cùng có cổng chờ. Hai worker vào cổng, ba task còn lại nằm trong queue; main lấy số liệu rồi mới mở cổng cho chúng chạy hết.

Tạo file `ThreadPoolMetricsDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class ThreadPoolMetricsDemo {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                2, 2, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(3)
        );

        CountDownLatch twoStarted = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);

        Runnable task = () -> {
            twoStarted.countDown();
            try {
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        try {
            for (int i = 0; i < 5; i++) {
                pool.execute(task);
            }

            twoStarted.await();

            System.out.println("Submitted: 5");
            System.out.println("Queue size before release: "
                    + pool.getQueue().size());
            System.out.println("Active estimate before release: "
                    + pool.getActiveCount());
            System.out.println("Completed estimate before release: "
                    + pool.getCompletedTaskCount());
        } finally {
            release.countDown();
            pool.shutdown();
        }

        if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Pool did not terminate");
        }

        System.out.println("Final queue size: "
                + pool.getQueue().size());
        System.out.println("Final active estimate: "
                + pool.getActiveCount());
        System.out.println("Final completed estimate: "
                + pool.getCompletedTaskCount());
    }
}
```

Biên dịch và chạy:

```bash
javac ThreadPoolMetricsDemo.java
java ThreadPoolMetricsDemo
```

Đầu ra minh họa trong điều kiện thực thi thông thường:

```text
Submitted: 5
Queue size before release: 3
Active estimate before release: 2
Completed estimate before release: 0
Final queue size: 0
Final active estimate: 0
Final completed estimate: 5
```

**Phân tích và giới hạn bảo đảm:**

1. Pool có `corePoolSize = maximumPoolSize = 2`. Hai task đầu tiên được worker thực thi và chờ `release`; ba task còn lại có thể nằm trong queue dung lượng 3. Không có task thứ sáu nên không cần rejection.
2. `twoStarted.await()` xác nhận đã có **hai task bước vào `run()`**; vì cổng chưa mở, hai worker này chưa thể kết thúc bình thường. Ba task còn lại ở queue. Đây là lý do snapshot trước khi mở cổng thường có active ≈ 2, queued = 3, completed ≈ 0.
3. `getActiveCount()` và `getCompletedTaskCount()` được tài liệu hóa là **giá trị ước lượng**. Không dùng output mẫu này để tạo assertion rằng mọi implementation và mọi lần lấy mẫu đồng thời phải cho số chính xác tuyệt đối.
4. Khi `release.countDown()`, hai worker hoàn thành task đang chạy rồi lấy các task còn chờ. `shutdown()` từ chối task mới nhưng **tiếp tục chạy task đã nhận** theo cơ chế shutdown bình thường.
5. Sau `awaitTermination()` trả true, mọi worker đã dừng, queue được xử lý xong trong ví dụ. Vì năm task đều hoàn tất bình thường, snapshot cuối thông thường là active 0, queue 0, completed 5.
6. `finally` bảo đảm mở cổng và bắt đầu shutdown ngay cả khi main bị interrupt khi chờ cổng, tránh cố ý để worker mắc kẹt vì code đo metric.

Mấu chốt của ví dụ là **tách thời điểm lấy mẫu trước và sau khi task hoàn tất**. Trong ứng dụng thật, việc gọi ba getter không chụp một transaction thống nhất; những giá trị có thể đến từ các thời điểm hơi khác nhau khi pool đang thay đổi.

## 5. Độ tin cậy: các metric của ThreadPoolExecutor là snapshot/ước lượng

Javadoc mô tả `getActiveCount()`, `getCompletedTaskCount()` và `getTaskCount()` theo ngữ nghĩa **approximate**. `getQueue().size()` phản ánh số phần tử đang thấy trong queue tại thời điểm đọc, nhưng task có thể được lấy ra hoặc thêm vào ngay sau đó; cách `size()` hoạt động còn phụ thuộc implementation của queue.

Điều này dẫn đến ba quy tắc:

- **Không lấy snapshot để làm invariant concurrency:** ví dụ `if (pool.getQueue().size() < 100) pool.execute(task)` vẫn có race giữa lúc đọc size và lúc submit. Các thread khác có thể làm queue đầy ở khoảng giữa.
- **Không suy ra kết quả chính xác bằng cộng/trừ các metric đo khác lúc:** `getTaskCount() - getCompletedTaskCount() - getActiveCount()` không được đảm bảo bằng `queue.size()` do sampling không nguyên tử và cách đếm cụ thể.
- **Không chờ trạng thái bằng polling quá sát nếu API đã có chờ đúng:** thay vì lặp `while (getActiveCount() > 0)`, dùng `shutdown()` + `awaitTermination(timeout, unit)` để đợi pool kết thúc; thay vì tự chờ completed tăng, dùng `Future.get()`, `CountDownLatch` hoặc `invokeAll()` khi phù hợp.

Các metric vẫn rất hữu ích cho dashboard, xu hướng, SLO và phát hiện bất thường. “Ước lượng” không phải “vô dụng”; nghĩa là chúng thích hợp để **quan sát**, không để đồng bộ các luồng hoặc quyết định nhận task một cách atomic.

### Metric nào phản ánh “đang nghẽn”?

Ví dụ:

- **Active gần mức số worker hiện tại, queue tăng liên tục:** tốc độ nhận task có thể cao hơn năng lực xử lý, hoặc nhiều task bị kẹt trong I/O/lock.
- **Active thấp, queue gần như trống:** pool có thể đang rảnh, nhưng cũng có thể upstream không gửi được việc; cần đối chiếu lượng yêu cầu tới.
- **Completed tăng chậm, queue tăng:** có thể throughput xử lý suy giảm. Nếu active vẫn cao, xem thời gian chạy task, lock contention, downstream I/O.
- **Queue luôn trống nhưng latency cao:** task có thể đang bị chặn ở bước ngoài executor, trong bản thân task hoặc tại chỗ nhận yêu cầu; chỉ số queue không bao phủ cả pipeline.

Không kết luận “deadlock” hoặc “thiếu thread” chỉ từ một snapshot. Dùng thêm thread dump, JFR, thời gian chạy task, loại queue và trạng thái dependency.

## 6. Hiểu đúng queue size: bounded, unbounded và handoff

`ThreadPoolExecutor` có thể dùng các loại work queue khác nhau; ngữ nghĩa `size()` thay đổi theo loại:

| Loại queue | Đặc điểm | Cách diễn giải |
| --- | --- | --- |
| `ArrayBlockingQueue<>(capacity)` | Dung lượng cố định, phần tử được lưu trong queue | `size()` là backlog đang lưu, có thể đối chiếu với capacity |
| `LinkedBlockingQueue<>(capacity)` | Có giới hạn nếu truyền capacity rõ ràng | Theo dõi backlog, lưu ý cost/memory |
| `LinkedBlockingQueue<>()` mặc định | Dung lượng rất lớn (gần như unbounded theo mục đích sử dụng) | Queue có thể tăng đáng kể và tiêu tốn bộ nhớ trước khi có rejection do đầy |
| `SynchronousQueue` | Handoff trực tiếp, **không có dung lượng lưu phần tử** | `size()` thường luôn 0, **không đồng nghĩa không có áp lực tải** |
| `PriorityBlockingQueue` | Sắp xếp theo độ ưu tiên, không giới hạn cố định theo cách mặc định | `size()` không cho biết mức ưu tiên, tuổi task hoặc deadline |
| Queue của `ScheduledThreadPoolExecutor` | Có thể chứa task trì hoãn/chưa tới hạn và task định kỳ | `size()` không đơn giản là số request thường đang chờ worker |

### Lưu ý khi pool có hàng đợi rất lớn

Trong `ThreadPoolExecutor`, sau khi đạt `corePoolSize`, nếu queue vẫn nhận được task thì executor có thể **ưu tiên đưa task vào queue** thay vì tạo thêm worker cho tới `maximumPoolSize`. Với `LinkedBlockingQueue` không giới hạn thực tế, `maximumPoolSize` thường **không phát huy** như người mới nghĩ. Queue tăng là cảnh báo về backlog và nguy cơ bộ nhớ, không nhất thiết phản ánh pool đã mở rộng tối đa worker.

Với `SynchronousQueue`, vì không lưu task trong queue, `getQueue().size()` không mô tả backlog. Khi không có worker để nhận handoff và không thể thêm worker, submission có thể bị từ chối theo chính sách rejection. Cần quan sát cả rejection, latency và nguồn yêu cầu.

### Không tùy tiện sửa `getQueue()`

`getQueue()` trả về queue mà executor đang dùng. Javadoc lưu ý truy cập này chủ yếu phục vụ **monitoring và debugging**; sử dụng nó để thêm/xóa phần tử tùy tiện sẽ can thiệp cơ chế quản lý task của executor. Đừng gọi `pool.getQueue().clear()` như cách “xả tải” hoặc `queue.add(runnable)` để thay `execute()`.

Nếu cần chủ động loại một task đã được xếp hàng, xem các API được hỗ trợ như `remove(Runnable)`/`purge()` theo đúng hợp đồng, hoặc quản lý cancellation và ownership ở lớp bao quanh. Việc hủy task chưa chắc đồng nghĩa queue giảm ngay tức thì với mọi executor.

## 7. Completed task khác “successful task” như thế nào?

`getCompletedTaskCount()` theo dõi task **đã hoàn tất việc thực thi trong pool**, không phải giá trị nghiệp vụ thành công. Một `Runnable` có thể ném exception; một `Callable` được `submit()` có thể kết thúc bằng lỗi; một task có thể bị cancel hoặc kết thúc sớm.

### Java 17+: một task thất bại vẫn được tính completed

Tạo file `CompletedIsNotSuccess.java`:

```java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.Future;

public class CompletedIsNotSuccess {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new LinkedBlockingQueue<>()
        );

        boolean businessSuccess = true;
        try {
            Future<?> result = pool.submit(() -> {
                throw new IllegalStateException("business failed");
            });

            try {
                result.get();
            } catch (ExecutionException e) {
                businessSuccess = false;
                System.out.println("Failure observed via Future: "
                        + e.getCause().getClass().getSimpleName());
            }
        } finally {
            pool.shutdown();
        }

        if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Pool did not terminate");
        }

        System.out.println("Business success: " + businessSuccess);
        System.out.println("Completed tasks: "
                + pool.getCompletedTaskCount());
    }
}
```

Biên dịch và chạy:

```bash
javac CompletedIsNotSuccess.java
java CompletedIsNotSuccess
```

Đầu ra:

```text
Failure observed via Future: IllegalStateException
Business success: false
Completed tasks: 1
```

Lời gọi `submit` bọc công việc trong `Future`. `result.get()` ném `ExecutionException` với nguyên nhân là lỗi nghiệp vụ; executor vẫn đã thực thi và kết thúc một task nên completed count tăng. Nếu chỉ có completed count mà không xem kết quả `Future` hoặc metric riêng, dashboard có thể hiển thị “1 completed” và **không hề cho biết 1 thất bại**.

### Mối quan hệ giữa `execute()`, `submit()` và ngoại lệ

- `execute(Runnable)` thường chuyển `Runnable` trực tiếp cho worker. Một exception không bắt có thể đi qua cơ chế `afterExecute(Runnable, Throwable)` dưới dạng `Throwable` và làm worker kết thúc bất thường.
- `submit(Runnable/Callable)` thường sử dụng `FutureTask`, giữ exception **bên trong Future** để `get()` báo `ExecutionException`. Trong hook `afterExecute`, đối số `Throwable` có thể là null **dù tác vụ thất bại**.
- `Future.cancel(...)` ảnh hưởng trạng thái hủy của Future, nhưng không phải mọi cancellation đều đồng nghĩa worker đã kết thúc tức thì. Không dùng completed count để suy ra cancellation đã hoàn tất hoặc side effect đã rollback.

Muốn đếm thành công/thất bại, hãy xác định nghĩa **thành công của nghiệp vụ** rồi đo trực tiếp, ví dụ wrapper `Callable` ghi nhận outcome sau khi tác vụ trả kết quả hoặc ném exception. Không gán nhãn business success cho metric quản trị worker của `ThreadPoolExecutor`.

## 8. Rejection policy làm metric “submitted” và “completed” lệch nhau

Khi pool và queue không nhận thêm task, `RejectedExecutionHandler` quyết định cách xử lý. Một số policy chuẩn:

- `AbortPolicy`: ném `RejectedExecutionException` cho caller.
- `CallerRunsPolicy`: nếu executor chưa shutdown, chạy task **ngay trên thread gọi `execute`**, tạo backpressure; nếu shutdown có thể bỏ task.
- `DiscardPolicy`: bỏ task mà không báo lỗi.
- `DiscardOldestPolicy`: loại task cũ nhất đang chờ rồi thử submit lại; cần đặc biệt thận trọng với deadline/priority/retry.

**Hệ quả:** một task có thể được thực thi ở **caller thread** chứ không phải worker của pool. Task đó không phải hoàn tất “bởi pool worker”, nên không nên mong `getCompletedTaskCount()` phản ánh mọi công việc được xử lý bởi cả caller và worker.

### Java 17+: CallerRunsPolicy làm chênh lệch bộ đếm

Tạo file `CallerRunsMetrics.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class CallerRunsMetrics {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.CallerRunsPolicy()
        );

        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger callerExecuted = new AtomicInteger();
        Thread submitter = Thread.currentThread();

        try {
            pool.execute(() -> {
                entered.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });

            entered.await();           // Worker số 1 đang giữ slot chạy.
            pool.execute(() -> { });   // Task số 2 nằm trong queue đầy.
            pool.execute(() -> {       // Task số 3 chạy trong caller.
                if (Thread.currentThread() == submitter) {
                    callerExecuted.incrementAndGet();
                }
            });

            System.out.println("Executed in caller: "
                    + callerExecuted.get());
        } finally {
            release.countDown();
            pool.shutdown();
        }

        if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Pool did not terminate");
        }

        System.out.println("Completed by pool workers: "
                + pool.getCompletedTaskCount());
    }
}
```

Chạy:

```bash
javac CallerRunsMetrics.java
java CallerRunsMetrics
```

Đầu ra:

```text
Executed in caller: 1
Completed by pool workers: 2
```

Vì pool chỉ có một worker và queue chứa một phần tử, khi task thứ ba được gửi, cả worker và queue đều bận. `CallerRunsPolicy` thực thi task này ngay trên caller. Hai task còn lại chạy trong worker và hoàn tất sau khi `release` mở. Từ góc nhìn nghiệp vụ, **ba task đã được thực thi**; từ metric của pool, chỉ **hai task đã hoàn tất bởi worker**.

**Điểm cần đưa lên dashboard:** số yêu cầu **được gửi**, **được chấp nhận**, **chạy trong caller**, **bị từ chối/bỏ**, **thất bại nghiệp vụ** và **hoàn tất nghiệp vụ** có thể khác nhau. Hãy có các counter riêng nếu yêu cầu đo toàn bộ pipeline, không suy hết từ completed count.

## 9. Thiết kế một dashboard quan sát pool thực tế

Một bảng theo dõi hữu ích thường có hai nhóm:

### A. Các metric trạng thái của executor (gauge/snapshot)

| Metric | Loại | Câu hỏi trả lời |
| --- | --- | --- |
| `getActiveCount()` | Gauge ước lượng | Bao nhiêu worker hiện đang bận thực thi task? |
| `getPoolSize()` | Gauge | Pool hiện có bao nhiêu worker? |
| `getCorePoolSize()`/`getMaximumPoolSize()` | Cấu hình | Ngưỡng thiết kế là gì? |
| `getQueue().size()` | Gauge | Bao nhiêu phần tử còn đang chờ trong queue? |
| Queue remaining capacity, nếu queue hỗ trợ | Gauge | Còn bao nhiêu slot trong queue bounded? |
| `isShutdown()`, `isTerminating()`, `isTerminated()` | Trạng thái lifecycle | Pool đang nhận việc hay đang ngừng? |

Gauge thay đổi theo thời gian. Lấy mẫu quá thưa có thể bỏ lỡ spike ngắn; lấy mẫu quá dày có overhead và cũng không làm dữ liệu trở nên nguyên tử.

### B. Các metric tích lũy hoặc nghiệp vụ (counter/histogram)

| Metric | Nguồn | Tại sao cần |
| --- | --- | --- |
| `getCompletedTaskCount()` | Executor, **ước lượng tích lũy** | Xu hướng throughput thực thi của worker |
| `getTaskCount()` | Executor, **ước lượng tích lũy** | Tổng task được pool quản lý theo cách đếm của implementation |
| Submitted/accepted/rejected | Instrumentation tại điểm submit/rejection | Phát hiện quá tải và policy |
| Caller-runs count | Instrumentation ở `CallerRunsPolicy` hoặc wrapper | Thấy backpressure làm caller mất thời gian |
| Business success/failure/cancel | Wrapper task hoặc kết quả Future | Phân biệt outcome nghiệp vụ với “đã thực thi” |
| Queue wait duration | Thời điểm enqueue và bắt đầu chạy | Phát hiện backlog qua latency chứ không chỉ size |
| Execution duration | Thời điểm bắt đầu và kết thúc task | Xác định task chậm, I/O và contention |
| End-to-end latency | Tại ranh giới request/workflow | Thấy cả chờ queue, chạy task, retry và phản hồi |

**Công thức ước lượng throughput** trong một cửa sổ đo:

```text
completed_rate_per_second
    = (completed_at_t2 - completed_at_t1) / elapsed_seconds
```

Dùng thời gian trôi qua từ đồng hồ đơn điệu (`System.nanoTime()`) để đo khoảng lấy mẫu, không lấy wall-clock để tính elapsed nếu không cần. Vì completed count là estimate và snapshot không nguyên tử, tốc độ tính bằng hiệu số nên được xem là **ước lượng**, đặc biệt với khoảng lấy mẫu ngắn hoặc pool thay đổi/shutdown.

Không so sánh trực tiếp counter từ **hai instance executor khác nhau** hoặc sau khi pool đã được tạo lại: bộ đếm khởi động lại từ 0 nên delta có thể sai nếu không nhận biết vòng đời.

## 10. Lấy mẫu định kỳ mà không cản trở worker

Một hướng triển khai là dùng một scheduler/monitor **tách khỏi pool làm việc**, đọc metrics định kỳ rồi xuất ra log hoặc hệ thống metrics. Không để chính pool đang bão hòa làm nhiệm vụ duy nhất đo trạng thái của nó, vì khi hàng đợi đầy, task monitor cũng có thể bị chậm.

Ví dụ cấu trúc:

```java
// Snippet minh họa: pool là ThreadPoolExecutor, sampler
// là ScheduledExecutorService đã khởi tạo.
ScheduledFuture<?> monitor = sampler.scheduleAtFixedRate(
        () -> {
            int active = pool.getActiveCount();
            int queued = pool.getQueue().size();
            long completed = pool.getCompletedTaskCount();

            recordMetrics(active, queued, completed);
        },
        0, 1, TimeUnit.SECONDS
);

// Khi dừng monitoring:
monitor.cancel(false);
sampler.shutdown();
```

Đây là **snippet**, không phải file Java độc lập: `recordMetrics` và các biến được giả định đã định nghĩa. Đừng làm lệnh ghi log/network chậm hoặc bị chặn vô hạn trong callback lấy mẫu. Nếu một lượt sampler chạy quá lâu hoặc ném exception không được xử lý, lịch lấy mẫu có thể bị ảnh hưởng. `scheduleAtFixedRate` không bảo đảm lấy mẫu đúng mỗi giây dưới mọi lịch chạy.

Một bản monitoring production nên:

1. Gắn nhãn pool theo chức năng (ví dụ nhóm IO, CPU, background), không nhúng thông tin cá nhân vào metric tags.
2. Ghi trạng thái active, pool size, queue length, completed, rejected và latency cùng timestamp.
3. Tránh tag theo task ID/request ID có cardinality cực lớn.
4. Xử lý lỗi exporter/metrics backend độc lập với việc chạy task.
5. Khi pool đang shutdown, tiếp tục lấy mẫu đủ để thấy drain, rồi dừng sampler đúng vòng đời.
6. Cảnh báo theo **xu hướng có thời gian duy trì**, không theo một snapshot nhiễu duy nhất.

### Hook `beforeExecute`/`afterExecute`

Có thể subclass `ThreadPoolExecutor` và override `beforeExecute(Thread,Runnable)`/`afterExecute(Runnable,Throwable)` để đo vòng đời worker. Nhưng hook này chạy trên đường thực thi task, nên code đo cần nhẹ, thread-safe và không làm hỏng logic của executor.

- `beforeExecute` có thể ghi thời điểm bắt đầu, nhưng nếu dùng shared map phải quản lý ID và cleanup.
- `afterExecute` được gọi khi `run()` của task kết thúc trong worker. `Throwable` có thể null với `FutureTask` ngay cả khi user code lỗi: cần xem kết quả `Future` hoặc instrument trực tiếp wrapper nếu muốn success/failure chính xác.
- Nếu hook tự ném exception, worker có thể kết thúc bất thường và việc xử lý bị ảnh hưởng.
- `CallerRunsPolicy` có thể thực thi task ở caller mà **không qua worker hooks**, nên metrics dựa riêng trên hook cũng không bao quát tất cả task thực thi.

Với nhu cầu thông thường, bọc `Runnable`/`Callable` ngay ở biên submit để đo thời gian, status và error rõ ràng hơn là cố diễn giải completed count như business success.

## 11. Mẫu instrument outcome tại ranh giới task

Dưới đây là một ví dụ **chạy độc lập** để theo dõi thành công/thất bại nghiệp vụ bằng counter riêng, đồng thời đối chiếu với completed count. Tạo file `ExecutorOutcomeDemo.java`:

```java
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.Future;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.atomic.LongAdder;

public class ExecutorOutcomeDemo {
    private static final LongAdder succeeded = new LongAdder();
    private static final LongAdder failed = new LongAdder();

    static Runnable tracked(Runnable work) {
        return () -> {
            try {
                work.run();
                succeeded.increment();
            } catch (RuntimeException | Error e) {
                failed.increment();
                throw e;
            }
        };
    }

    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                2, 2, 0L, TimeUnit.MILLISECONDS,
                new LinkedBlockingQueue<>()
        );

        try {
            Future<?> ok = pool.submit(tracked(() -> { }));
            Future<?> bad = pool.submit(tracked(() -> {
                throw new IllegalArgumentException("invalid input");
            }));

            for (Future<?> future : new Future<?>[] {ok, bad}) {
                try {
                    future.get();
                } catch (ExecutionException ignored) {
                    // Lỗi đã được đếm trong wrapper; caller biết task lỗi.
                }
            }
        } catch (ExecutionException e) {
            throw new AssertionError(e);
        } finally {
            pool.shutdown();
        }

        if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Pool did not terminate");
        }

        System.out.println("Succeeded: " + succeeded.sum());
        System.out.println("Failed: " + failed.sum());
        System.out.println("Completed by pool: "
                + pool.getCompletedTaskCount());
    }
}
```

Chạy:

```bash
javac ExecutorOutcomeDemo.java
java ExecutorOutcomeDemo
```

Kết quả mong đợi:

```text
Succeeded: 1
Failed: 1
Completed by pool: 2
```

**Lưu ý về ví dụ:** `LongAdder.sum()` rất phù hợp để quan sát counter khi nhiều thread cập nhật, nhưng trong lúc cập nhật đồng thời, kết quả tổng không phải một snapshot nguyên tử. Ở đây ta gọi `sum()` **sau khi pool đã kết thúc**, nên kết quả cuối ổn định. Trong ứng dụng cần theo dõi nhiều loại lỗi, nên phân nhóm exception ở lớp nghiệp vụ thay vì chỉ phân biệt success/failure bằng một `RuntimeException`.

*Chi tiết về checked exception:* `Runnable.run()` không khai báo checked exception. Với `Callable` có checked exception, wrapper cần khai báo/propagate thích hợp và đếm lỗi tương ứng. Trong ví dụ trên, các task chỉ ném unchecked exception.

## 12. Khi nào méo số liệu hoặc thiếu số liệu?

### Task bị cancel trước khi worker chạy

Nếu một `Future` bị hủy lúc đang trong queue, wrapper của user code có thể chưa chạy lần nào. `FutureTask` hoặc cấu trúc queue có thể vẫn hiện diện cho tới lúc được dọn/worker lấy ra theo policy. `getQueue().size()` và completed count **không** tự cung cấp số task đã hủy trước khi chạy.

### Task chạy lâu hoặc bị treo

`getActiveCount()` có thể cao liên tục, trong khi completed count gần như không tăng. Đây có thể là task dài hợp lệ hoặc đang chặn I/O/lock. Đo execution duration và xem thread dump/JFR; không suy ra luôn deadlock.

### Rejected task

Task bị `AbortPolicy` từ chối có thể chưa từng vào queue hoặc worker. Nó không có nghĩa completed count phải tăng. Cần counter riêng ngay ở ranh giới submit và rejection handler, cùng chính sách retry.

### Task chạy trong caller

`CallerRunsPolicy` có thể làm throughput bị chi phối bởi thời gian caller bị chặn; metric active của pool không phản ánh caller đang chạy task. Theo dõi cả caller-run count và submit latency.

### Periodic task

`ScheduledThreadPoolExecutor` có task định kỳ có thể chạy nhiều lần từ cùng một đăng ký, và queue có thể chứa task trì hoãn. Không hiểu `getCompletedTaskCount()` của periodic executor như số bản ghi nghiệp vụ đã xử lý, cũng không so sánh trực tiếp queue size với pool thông thường mà không xét scheduler semantics.

### Pool bị shutdown

`shutdown()` cho phép hoàn tất các task đã được nhận theo cách bình thường nhưng không nhận task mới. `shutdownNow()` cố ngắt task đang chạy và trả danh sách task chờ chưa bắt đầu, **không bảo đảm** thread/task đang chạy dừng ngay. Sau shutdown, metric active/queue/completed vẫn có thể thay đổi trong giai đoạn drain. Dùng `awaitTermination()` để chờ pool kết thúc theo thời hạn thay vì chỉ nhìn active count.

## 13. Dùng metric để điều chỉnh pool: điều nên và không nên làm

**Nên làm:**

- Theo dõi active, queue, task latency, rejection và throughput trên cùng trục thời gian.
- Sử dụng bounded queue khi cần giới hạn backlog và memory; tính cả dung lượng worker và chiến lược rejection.
- Phân biệt tác vụ CPU-bound, I/O-bound và tác vụ chờ resource; cấu hình pool theo workload.
- Cảnh báo khi queue tăng lâu, thời gian chờ tăng hoặc rejection xuất hiện liên tục.
- So sánh kết quả trước/sau khi đổi `corePoolSize`, `maximumPoolSize`, queue và rejection policy qua benchmark/tải thật.

**Không nên làm:**

- Không dùng `if (getActiveCount() < max) execute(...)` để điều phối nguyên tử; trạng thái đổi ngay sau lúc đọc.
- Không dùng `getQueue().size() == 0` để kết luận tất cả task đã xong; worker có thể vẫn đang chạy.
- Không dùng `completed == submitted` nếu có rejection, task chạy ở caller, cancellation hoặc task được gửi trong nhiều thời điểm.
- Không dùng `getLargestPoolSize()` như số worker active hiện tại.
- Không nhầm `getPoolSize()` với `getActiveCount()`; worker idle vẫn nằm trong pool.
- Không gọi `getQueue().clear()` hay tự enqueue để “tối ưu” executor dựa trên một snapshot.
- Không cho metrics exporter blocking I/O làm giảm throughput của chính pool.
- Không dùng một điểm đo duy nhất để kết luận tối ưu số thread; cần xem CPU, I/O, độ dài task, memory, latency và contention.

## 14. Checklist triển khai khả năng quan sát Executor Framework

1. **Xác nhận executor implementation:** có thật là `ThreadPoolExecutor` không, hay một `ExecutorService` wrapper/`ForkJoinPool`/scheduled executor?
2. **Định nghĩa ý nghĩa metric:** active = worker đang thực thi task, queued = phần tử đang chờ, completed = task đã kết thúc thực thi trong pool, không phải business success.
3. **Phân biệt gauge và counter:** active/queue là snapshot; completed/task count là số liệu tích lũy ước lượng.
4. **Ghi rõ queue type/capacity:** queue bounded, unbounded, handoff hay delayed sẽ có ý nghĩa size khác nhau.
5. **Không dùng getter để quyết định atomic:** chính `execute`/`submit` và rejection policy mới xác định việc nhận task.
6. **Instrument submitted/accepted/rejected/caller-runs** khi hệ thống cần thống kê chính xác đường đi của task.
7. **Đếm outcome nghiệp vụ độc lập:** success, failure, retry, cancel phải được xác định ở layer quản lý task hoặc Future.
8. **Đo latency:** thời gian chờ queue, execution duration, end-to-end response và tail latency giúp giải thích queue length.
9. **Đo bằng sampler nhẹ, tách pool khi có thể:** tránh exporter gây áp lực ngược cho hệ thống.
10. **Đánh giá shutdown/restart:** counter reset khi đổi instance; snapshot còn thay đổi trong lúc drain.
11. **Kiểm thử các biên:** pool rảnh, bão hòa, task thất bại, caller-runs, rejection, cancellation, shutdown.
12. **Không tin vào một snapshot duy nhất:** xác minh xu hướng với JFR/thread dump và workload thực tế.

**Kết luận:** `ThreadPoolExecutor` cung cấp các thước đo hữu ích như `getActiveCount()`, `getQueue().size()` và `getCompletedTaskCount()` để hiểu mức tải và tiến độ worker. Nhưng chúng là **quan sát trạng thái đang thay đổi**, không phải thao tác đồng bộ hay số thành công nghiệp vụ. Hãy kết hợp chúng với rejection metrics, thời gian chờ/chạy task và thống kê outcome riêng để có bức tranh chính xác về Executor Framework.