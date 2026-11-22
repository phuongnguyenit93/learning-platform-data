# Xây executor có bounded queue và rejection policy trong Java

## 1. Bài toán thực tế: tránh hàng đợi tăng vô hạn

Giả sử một tiến trình Java nhận nhiều yêu cầu xử lý tệp. Mỗi yêu cầu mất khoảng 200 ms CPU. Nếu cứ nhận yêu cầu và đưa vào hàng đợi không giới hạn, khi tốc độ nhận lớn hơn tốc độ xử lý trong thời gian dài, số công việc chờ sẽ tăng: thời gian đợi lâu, giữ nhiều đối tượng trong heap, áp lực GC và cuối cùng có thể cạn tài nguyên.

Một `ThreadPoolExecutor` có **bounded queue** (hàng đợi giới hạn sức chứa) giúp thể hiện rõ khả năng tiếp nhận công việc:

- Tối đa bao nhiêu worker thực sự xử lý cùng lúc?
- Tối đa bao nhiêu task đã được chấp nhận nhưng chưa bắt đầu?
- Khi tất cả worker bận và queue đầy, phải **từ chối**, **đẩy công việc sang chính thread gọi**, hay thực hiện chính sách riêng?
- Khi đóng executor, những task đang chạy, đang chờ và các task nộp mới sẽ ra sao?

Mục tiêu thực hành là xây một executor bằng **Java SE 17+**, tạo tình huống quá tải có thể lặp lại, kiểm chứng chính sách từ chối, hiểu cách chọn giới hạn và dọn tài nguyên. Đây là kiến thức về Java concurrency nói chung; không cần container hay framework.

## 2. Kiến trúc và đường đi của một task

Có thể tạo `ThreadPoolExecutor` bằng constructor:

```java
// Minh họa cấu hình, không phải chương trình độc lập.
ThreadPoolExecutor executor = new ThreadPoolExecutor(
        2,                         // corePoolSize
        4,                         // maximumPoolSize
        30L, TimeUnit.SECONDS,     // keepAliveTime
        new ArrayBlockingQueue<>(8), // workQueue: tối đa 8 task chờ
        new ThreadPoolExecutor.AbortPolicy());
```

Ý nghĩa từng thành phần:

| Thành phần | Ý nghĩa và ràng buộc |
|---|---|
| `corePoolSize` | Mục tiêu số worker cơ bản; khi có task, pool thường tạo worker mới cho đến ngưỡng core (trừ cấu hình đặc biệt). |
| `maximumPoolSize` | Giới hạn số worker đồng thời mà executor tạo ra; phải `>= corePoolSize`. |
| `keepAliveTime` | Thời gian worker **vượt quá core** được phép rảnh trước khi thoát (mặc định core worker không timeout nếu chưa bật `allowCoreThreadTimeOut(true)`). |
| `workQueue` | Nơi giữ task **đã nhận nhưng chưa bắt đầu**; `ArrayBlockingQueue<>(capacity)` có sức chứa cố định. |
| `ThreadFactory` | Tùy chọn để tạo worker, đặt tên, cấu hình thread và hỗ trợ chẩn đoán. |
| `RejectedExecutionHandler` | Chính sách khi không tiếp nhận được task (do bão hòa tài nguyên hoặc executor đã shutdown). |

Với `ThreadPoolExecutor` đang chạy, trình tự tiếp nhận nhiệm vụ về cơ bản là:

1. Nếu số worker hiện có **nhỏ hơn `corePoolSize`**, thử tạo worker mới để chạy task.
2. Nếu đã có đủ core worker, **thử đưa task vào queue**.
3. Nếu queue không nhận được (ví dụ đầy), thử tạo thêm worker **đến `maximumPoolSize`**.
4. Nếu không thể thêm worker và queue cũng không nhận được, gọi `RejectedExecutionHandler`.

```text
execute(task)
    |
    +-- workers < corePoolSize ? -- yes --> tạo worker + chạy
    |                                   |
    no                                  v
    |
    +-- queue.offer(task) được ? -- yes --> chấp nhận vào queue
    |                               
    no
    |
    +-- workers < maximumPoolSize ? -- yes --> tạo worker bổ sung
    |
    no
    |
    +-- rejectedExecution(task, executor)
```

Sơ đồ là mô hình hành vi; implementation còn xử lý trạng thái shutdown và các race giữa việc enqueue, worker creation và đóng pool. Đặc biệt, **queue được thử trước khi tăng số worker vượt core**: không nên giả định cấu hình `core=2, max=8` sẽ lập tức có 8 thread khi có 8 task.

Ví dụ `core=2`, `max=4`, queue capacity 3, các task đều chặn worker:

| Số task được nộp | Phân bố lý tưởng khi tất cả task trước còn bận |
|---:|---|
| 1–2 | Tạo tối đa 2 core worker chạy task. |
| 3–5 | Hai worker vẫn bận, 3 task nằm trong queue. |
| 6–7 | Queue đầy; tạo thêm tối đa 2 worker, tổng 4 worker. |
| 8 trở đi | Pool đạt 4 worker, queue chứa 3: bắt đầu rejection. |

Bảng giả sử không có task nào hoàn tất trước khi task tiếp theo được nộp và không có shutdown hoặc thread-factory failure.

## 3. Bounded queue giải quyết điều gì, và không giải quyết điều gì?

`new ArrayBlockingQueue<Runnable>(k)` giới hạn **k task đang chờ trong queue**. Nó không tự giới hạn số yêu cầu đến từ bên ngoài, số object nằm trong từng task, số thread ở hệ thống khác hay lượng bộ nhớ do các kết quả đang xử lý giữ.

Nếu một pool có `maximumPoolSize=4`, queue capacity 8 và mọi worker đang bận, số task đã nhận chưa hoàn thành tại một thời điểm có thể xấp xỉ **4 đang chạy + 8 đang đợi = 12** (ngoài những task đã hoàn thành nhưng kết quả chưa được thu hồi ở nơi khác). Đây là giới hạn *admission* của executor theo giả định đơn giản, không phải một cam kết sử dụng bộ nhớ cố định.

Lựa chọn queue phổ biến:

| Queue | Đặc điểm cần biết |
|---|---|
| `ArrayBlockingQueue<>(capacity)` | Giới hạn cứng; mảng có số slot cố định; thứ tự FIFO; có thể chọn fairness cho thao tác queue nhưng điều đó không tạo cam kết FIFO hoàn chỉnh cho mọi thread/task trong hệ thống. |
| `LinkedBlockingQueue<>(capacity)` | Cũng có thể giới hạn nếu truyền capacity cụ thể; tạo node khi enqueue. Constructor không truyền capacity dùng giới hạn `Integer.MAX_VALUE`, về thực tế có thể tăng quá lớn. |
| `SynchronousQueue<>()` | Không lưu task chờ; chuyển giao trực tiếp giữa producer và worker; khi không có worker sẵn sàng, có thể cần tạo worker tới max hoặc reject. |
| `PriorityBlockingQueue<>()` | Về bản chất không có giới hạn số phần tử hữu dụng bằng constructor capacity; không dùng như bounded queue chỉ vì có tham số initial capacity. |

Khi dùng `Executors.newFixedThreadPool(n)`, queue nội bộ mặc định là `LinkedBlockingQueue` không giới hạn thực tế theo lượng công việc bình thường. Nếu yêu cầu là **bounded queue có rejection rõ ràng**, hãy tạo `ThreadPoolExecutor` trực tiếp.

## 4. Rejection policy: quyết định lúc bão hòa

Các handler mặc định của `ThreadPoolExecutor`:

| Policy | Khi executor đang hoạt động và đã bão hòa | Mối nguy / cách dùng |
|---|---|---|
| `AbortPolicy` | Ném `RejectedExecutionException` cho thread đang nộp task. | Phù hợp khi caller có thể trả thông báo quá tải, retry có giới hạn hoặc chuyển sang cơ chế khác. |
| `CallerRunsPolicy` | Chính thread gọi `execute` chạy task **đồng bộ** nếu executor chưa shutdown. | Tạo sức ép ngược lên caller, nhưng có thể làm caller bị chậm, giữ lock, hoặc thay đổi nơi thread-local/context được sử dụng. Nếu executor đã shutdown, policy này bỏ task mà không chạy. |
| `DiscardPolicy` | Bỏ task mà không báo lỗi. | Có thể làm mất công việc âm thầm; với `submit`, `Future` trả ra có thể mãi không hoàn thành. |
| `DiscardOldestPolicy` | Thử loại task **đầu queue**, rồi thử `execute` lại khi executor chưa shutdown. | Có thể bỏ công việc cũ chưa thực hiện; với `submit`, `Future` cũ có thể kẹt. Không dùng khi yêu cầu thứ tự/không mất dữ liệu hoặc cấu hình queue/policy tạo retry bất tận. |

Policy chỉ là một phần hợp đồng ứng dụng: phải quyết định rõ caller làm gì khi không nhận task, có retry hay không, tránh retry liên tục khiến hệ thống vốn quá tải càng nặng. Không có policy nào tự bảo đảm “không mất việc” nếu process chết hoặc task có side effect không idempotent.

### Khi nào nên chọn?

- **Cần báo quá tải tường minh:** thường bắt đầu với `AbortPolicy`, ghi nhận rejection và xử lý ở biên gọi.
- **Caller chấp nhận xử lý tại chỗ để tự giảm tốc độ nộp:** cân nhắc `CallerRunsPolicy`, nhưng chỉ khi thread gọi được phép thực thi loại task ấy, có timeout phù hợp và không gây deadlock.
- **Dữ liệu có thể mất theo chính sách được công bố:** cân nhắc drop với metric rõ ràng; chính sách bỏ im lặng không thích hợp cho công việc quan trọng.
- **Cần hành vi nghiệp vụ riêng:** cài `RejectedExecutionHandler` kiểm tra trạng thái executor và ném exception có thông tin, hoặc route sang nơi xử lý khác đã được thiết kế/kiểm thử.

## 5. Ví dụ đầy đủ Java 17: ép queue đầy và xác nhận rejection

Chương trình sau có hai bài test thực hành. Ta cố ý giữ worker bằng `CountDownLatch` để xác định được thời điểm pool đầy, không dựa vào `Thread.sleep()` hoặc tốc độ máy.

**Tệp:** `BoundedExecutorExercise.java`

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class BoundedExecutorExercise {
    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static void abortPolicyExample() throws Exception {
        // 2 worker, 2 chỗ chờ, không mở rộng quá 2 worker.
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                2, 2, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(2),
                new ThreadPoolExecutor.AbortPolicy());

        CountDownLatch started = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<String> a = pool.submit(() -> {
                started.countDown();
                release.await();
                return "A";
            });
            Future<String> b = pool.submit(() -> {
                started.countDown();
                release.await();
                return "B";
            });

            // Chỉ nộp tiếp khi cả hai worker đã vào task.
            check(started.await(5, TimeUnit.SECONDS),
                    "Workers did not start");

            Future<String> c = pool.submit(() -> "C");
            Future<String> d = pool.submit(() -> "D");

            // A/B đang giữ cả 2 worker; C/D phải ở trong queue.
            check(pool.getQueue().size() == 2,
                    "Expected two queued tasks");

            boolean rejected = false;
            try {
                pool.submit(() -> "E"); // Thứ 5: hết sức chứa.
            } catch (RejectedExecutionException expected) {
                rejected = true;
            }
            check(rejected, "Expected rejection");

            System.out.println("abort: queued=2");
            System.out.println("abort: rejected=true");

            release.countDown();
            String result = a.get(5, TimeUnit.SECONDS)
                    + b.get(5, TimeUnit.SECONDS)
                    + c.get(5, TimeUnit.SECONDS)
                    + d.get(5, TimeUnit.SECONDS);
            check("ABCD".equals(result), "Missing accepted task");
            System.out.println("abort: results=" + result);

            pool.shutdown();
            check(pool.awaitTermination(5, TimeUnit.SECONDS),
                    "Executor did not terminate");
            System.out.println("abort: terminated=true");
        } finally {
            release.countDown(); // Giải phóng worker nếu assertion lỗi.
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    private static void callerRunsExample() throws Exception {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.CallerRunsPolicy());

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        Thread caller = Thread.currentThread();
        AtomicBoolean executedByCaller = new AtomicBoolean(false);

        try {
            pool.execute(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });
            check(started.await(5, TimeUnit.SECONDS),
                    "Worker did not start");

            // Worker bận; task thứ hai chiếm slot queue.
            pool.execute(() -> { });
            check(pool.getQueue().size() == 1,
                    "Expected one queued task");

            // Task thứ ba: pool và queue đều đầy, chạy tại caller.
            pool.execute(() -> executedByCaller.set(
                    Thread.currentThread() == caller));
            check(executedByCaller.get(), "Caller did not run task");
            System.out.println("caller-runs: on-caller=true");

            release.countDown();
            pool.shutdown();
            check(pool.awaitTermination(5, TimeUnit.SECONDS),
                    "Executor did not terminate");
            System.out.println("caller-runs: terminated=true");
        } finally {
            release.countDown();
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    public static void main(String[] args) throws Exception {
        abortPolicyExample();
        callerRunsExample();
    }
}
```

Biên dịch và chạy:

```bash
javac BoundedExecutorExercise.java
java BoundedExecutorExercise
```

**Stdout chính xác nếu mọi assertion thành công:**

```text
abort: queued=2
abort: rejected=true
abort: results=ABCD
abort: terminated=true
caller-runs: on-caller=true
caller-runs: terminated=true
```

Hai worker có thể hoàn thành A hoặc B theo thứ tự nào cũng được. Đầu ra vẫn xác định vì phép cộng chuỗi gọi `get()` theo thứ tự A, B, C, D; không có `println()` cạnh tranh trong các task. Việc `CallerRunsPolicy` chạy task thứ ba trên thread chính được kiểm chứng bằng so sánh trực tiếp `Thread.currentThread()` với `caller`, chứ không chỉ nhìn tên thread.

**Điều kiện của test:** `started.await` xác nhận worker đã vào task; `release` vẫn đóng khiến worker không thể nhận task queue. Do đó kết quả rejection và caller-runs ổn định trên máy có tốc độ khác nhau. Timeout 5 giây là hàng rào để test thất bại hữu hạn nếu môi trường không tạo được worker; không phải thời gian quy định trong hợp đồng executor.

## 6. Giải thích sâu kết quả của chương trình

### 6.1. Tại sao task thứ năm bị từ chối?

Ở `abortPolicyExample()`:
1. A và B bắt đầu chạy, cùng chờ một latch.
2. C, D đã được chấp nhận nhưng nằm trong `ArrayBlockingQueue` có capacity 2.
3. `maximumPoolSize = 2`: pool không thể thêm worker thứ ba.
4. E không thể vào queue; `AbortPolicy` ném `RejectedExecutionException` **ngay trên thread nộp**.
5. Sau `release.countDown()`, các worker hoàn tất A/B và tiếp tục lấy C/D từ queue. Bốn `Future` đều hoàn thành bình thường.

**Rejection không đồng nghĩa executor đã shutdown.** Ở bước 4, pool vẫn hoạt động: nó từ chối vì quá tải. Nếu queue trống ra sau đó, các task nộp tiếp có thể lại được chấp nhận. Phân biệt `pool.isShutdown()` với quá tải ở một thời điểm.

### 6.2. Vì sao `CallerRunsPolicy` là backpressure thô?

Ở `callerRunsExample()`:
1. Worker duy nhất đang block.
2. Queue một slot đã đầy.
3. Caller nộp task thứ ba và **phải tự thực hiện** nó trước khi `execute` trả về.

Trong chương trình production, nếu task thứ ba mất 300 ms thì thread nộp task cũng mất gần chừng ấy thời gian thay vì tiếp tục đẩy task vào pool. Điều này có thể làm chậm producer, gọi là một dạng **feedback/backpressure**. Nhưng vì task thực thi trên caller, nó cũng có thể gây deadlock nếu caller đang giữ lock cần thiết, gây latency bất ngờ ở thread nhạy cảm, hoặc tạo sai lệch về thread-local/context.

**Ràng buộc quan trọng:** Java không cam kết `CallerRunsPolicy` giúp áp đặt hạn mức tốc độ chính xác. Nó chỉ là cơ chế fallback theo điều kiện bão hòa; nếu pool đã shutdown, policy này không chạy task và cũng không ném lỗi mặc định.

### 6.3. `execute()` và `submit()` có hệ quả khác khi drop

`execute(Runnable)` không trả `Future`. `submit(...)` bọc task trong một future để người gọi truy vấn trạng thái và kết quả. Với `AbortPolicy`, cả hai đường nộp đều nhận `RejectedExecutionException` ngay khi bị từ chối.

Với `DiscardPolicy`, `submit` có thể trả lại một `Future` chưa bao giờ được chạy và không hoàn thành; `future.get()` không timeout có thể chờ mãi. Với `DiscardOldestPolicy`, task cũ bị loại khỏi queue cũng có thể có `Future` còn pending. Bởi vậy policy bỏ task cần một chiến lược báo lỗi/hủy cho những bên đã được cấp `Future`.

Khi tự viết `RejectedExecutionHandler`, đừng vô tình “nuốt” rejection rồi trả về như thành công nếu caller phụ thuộc `Future` hoặc cần biết task đã được nhận.

## 7. Tự định nghĩa rejection handler để quan sát quá tải

Một `RejectedExecutionHandler` nhận cả task bị từ chối và executor hiện tại. Mẫu sau **là đoạn cấu hình minh họa**, đặt trong code đã khai báo các import phù hợp:

```java
AtomicLong rejectedCount = new AtomicLong();

RejectedExecutionHandler handler = (task, executor) -> {
    rejectedCount.incrementAndGet();

    // Phân biệt đóng pool với pool đang chạy nhưng bão hòa.
    String reason = executor.isShutdown()
            ? "executor is shutdown"
            : "executor queue and workers are saturated";

    throw new RejectedExecutionException(reason);
};
```

Các import cần có: `java.util.concurrent.RejectedExecutionHandler`, `java.util.concurrent.RejectedExecutionException`, `java.util.concurrent.atomic.AtomicLong`. Thay `new ThreadPoolExecutor.AbortPolicy()` bằng `handler` trong constructor.

Vì handler chạy trên luồng gọi `execute` và trong đường xử lý rejection, hãy giữ nó nhanh, không tạo công việc nặng, không thực hiện retry không giới hạn và không gọi `execute` đệ quy trở lại chính pool đang bão hòa. Metric `rejectedCount` là số lần phát sinh rejection, không nhất thiết bằng số yêu cầu nghiệp vụ thất bại nếu một yêu cầu thử nộp nhiều lần.

Có thể xuất thêm metric:
- `getActiveCount()`: ước lượng số thread đang thực thi task.
- `getPoolSize()` và `getLargestPoolSize()`: số worker hiện tại/mốc cao nhất.
- `getQueue().size()` và `getQueue().remainingCapacity()`: snapshot hàng chờ.
- `getCompletedTaskCount()` và `getTaskCount()`: giá trị thống kê xấp xỉ, không dùng làm kiểm chứng tuyệt đối dưới cập nhật đồng thời.

Đây là snapshot vận hành, **không phải cơ chế đồng bộ**. Ví dụ một test viết `while (pool.getActiveCount() != 2) { }` có thể vừa tốn CPU vừa có race. Dùng `CountDownLatch` để điều khiển trạng thái; dùng metric để quan sát.

## 8. Thiết kế giới hạn queue và thread dựa trên thực tế

Không có một bộ số `core/max/capacity` tối ưu cho mọi ứng dụng. Phải đo tốc độ đến, thời gian phục vụ, kích thước mỗi task, mức sử dụng CPU/I/O và mục tiêu latency. Cách tư duy:

1. **Xác định workload:** task CPU-bound, I/O-bound hay hỗn hợp? Đầu vào có dồn đợt không? Task dài bao lâu ở các percentile?
2. **Đặt giới hạn worker:** tác vụ CPU-bound thường bị giới hạn bởi số core và contention; tác vụ chờ I/O có thể hưởng lợi từ nhiều thread hơn nhưng vẫn bị giới hạn bởi tài nguyên bên ngoài. `availableProcessors()` chỉ là tham chiếu, không phải công thức bắt buộc.
3. **Đặt queue có giới hạn:** capacity 50 không có nghĩa thời gian chờ tối đa 50 ms. Nếu một worker xử lý 5 task/s, 50 task xếp hàng có thể tạo thời gian chờ lớn; cần đo hàng đợi và latency thực.
4. **Chọn rejection policy:** overload phải được phản ánh đến caller hoặc có chính sách bỏ/retry nhất quán. Nếu caller làm việc không được phép block, tránh dùng `CallerRunsPolicy` tùy tiện.
5. **Cấp deadline:** task đã được chấp nhận vẫn có thể chờ lâu; xử lý `Future.get(timeout)`, timeout của I/O và cancellation phù hợp. Timeout của `Future.get` không tự hủy task.
6. **Kiểm thử tải:** xác minh giới hạn số worker, queue, tỷ lệ rejection, thời gian chờ, độ trễ và tài nguyên khi đầu vào vượt năng lực xử lý.

### Một ước lượng năng lực đơn giản

Giả sử mỗi task mất trung bình 100 ms CPU hoàn toàn và có 4 core thật sự rảnh cho ứng dụng. Ở mô hình lý tưởng, 4 worker có thể xử lý khoảng `4 / 0,1 = 40 task/s`. Nếu producer liên tục nộp 100 task/s thì backlog tăng khoảng 60 task/s cho tới khi queue đầy và hệ thống từ chối hoặc chậm lại.

Con số 40 task/s chỉ là **ước lượng điều kiện lý tưởng**, không phải benchmark. Runtime thực có overhead, GC, chênh lệch task length và nhiều nguồn tranh chấp. Tăng queue từ 100 lên 10.000 không tạo năng lực xử lý mới; nó chủ yếu tăng số task được chấp nhận và thời gian chờ.

**Little's law**, `L = λ × W` (với hệ thống ổn định và cách đo nhất quán), giúp liên hệ số công việc trung bình `L`, tốc độ hoàn thành trung bình `λ` và thời gian lưu hệ thống trung bình `W`. Nó không tự chỉ ra “capacity đúng” trong tình huống overload không ổn định; cần dữ liệu đo, phân phối thời gian xử lý và giới hạn latency theo yêu cầu.

## 9. Vòng đời: nộp task, overload và shutdown

Một executor bounded vẫn cần được đóng đúng cách. `shutdown()` ngừng nhận task mới nhưng cho task đã được nhận (đang chạy và đang trong queue) có cơ hội hoàn tất. `shutdownNow()` cố gắng interrupt task đang chạy và trả về những task chưa bắt đầu; nó không đảm bảo mọi task dừng tức thì.

Mẫu dừng có deadline (đoạn minh họa nằm trong method phù hợp, với `pool` đã được khai báo):

```java
pool.shutdown();
try {
    if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
        java.util.List<Runnable> neverStarted = pool.shutdownNow();
        // Ứng dụng cần quyết định xử lý/cancel task chưa bắt đầu.
        if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
            System.err.println("Some tasks did not stop");
        }
    }
} catch (InterruptedException e) {
    pool.shutdownNow();
    Thread.currentThread().interrupt();
}
```

**Chú ý:** `shutdownNow()` có thể trả về các `FutureTask` do `submit` tạo; lấy task ra khỏi queue **không tự động đảm bảo** `Future` của task đó bị cancel. Nếu vẫn có người gọi chờ `Future.get()`, chính sách hủy/thông báo kết quả phải được xử lý rõ ràng.

`try/finally` trong ví dụ runnable đã chủ động giải phóng latch và gọi `shutdownNow()` để tránh giữ worker sống sau khi assertion lỗi. Với test nặng hơn, cần kiểm tra kết quả `awaitTermination` trong cleanup và báo failure nếu không dừng; không để test suite treo mãi vì thread không daemon.

## 10. Bộ kiểm thử nên có cho bài thực hành

| Ca kiểm thử | Dàn dựng xác định | Kỳ vọng |
|---|---|---|
| Pool còn chỗ | Chạy ít task hơn capacity. | Được nhận, chạy đúng một lần, `Future` có kết quả. |
| Đúng sát giới hạn | Giữ mọi worker bằng latch, điền đủ queue. | Tất cả task trước ngưỡng vẫn được nhận. |
| Quá tải với `AbortPolicy` | Tiếp tục nộp khi worker và queue đã đầy. | `RejectedExecutionException`; task bị từ chối không chạy. |
| Quá tải với `CallerRunsPolicy` | Giữ pool bão hòa, nộp từ thread test. | Task fallback chạy trên **caller** trước khi `execute` trả về. |
| Từ chối sau shutdown | `shutdown()`, rồi nộp task mới dưới `AbortPolicy`. | Task mới không được nhận; exception được quan sát. |
| Task được nhận trước shutdown | Nộp task, gọi `shutdown()`, chờ hoàn tất. | Task trước shutdown vẫn có thể chạy và cho kết quả. |
| Task đang chạy khi `shutdownNow()` | Block task ở primitive interruptible. | Task phản hồi interrupt theo code; pool chỉ terminate sau khi worker thoát. |
| Task nằm trong queue khi `shutdownNow()` | Dùng một worker block, nộp task chờ. | Task chưa bắt đầu được trả về; kiểm tra chính sách `Future` của caller. |
| Caller có context riêng | Dùng `ThreadLocal` trong task fallback. | Kiểm tra hệ quả chạy task trên caller; không phụ thuộc giả định rằng task luôn ở worker. |
| Tải lâu | Giữ producer nhanh hơn consumer một khoảng có kiểm soát. | Queue không vượt capacity, có số rejection/độ trễ quan sát được, không tăng backlog vô hạn trong executor. |

Các test về thứ tự và bão hòa nên dùng latch/barrier và `Future.get(timeout, unit)`, không dùng `Thread.sleep()` để “mong task đang chạy”. Các test tải có biến thiên hiệu năng phải được tách khỏi unit test xác định.

## 11. Sai lầm phổ biến

| Sai lầm | Hệ quả | Cách sửa |
|---|---|---|
| `Executors.newFixedThreadPool(8)` rồi nghĩ queue bounded. | Queue mặc định có thể lớn tới mức không kiểm soát trong thực tế. | Dùng `ThreadPoolExecutor` với `ArrayBlockingQueue<>(n)` hoặc queue có capacity rõ. |
| Chỉ đặt `maximumPoolSize=16` nhưng dùng queue gần như vô hạn. | Queue liên tục nhận task, pool thường không mở rộng quá core. | Hiểu thứ tự worker → queue → thêm worker → rejection. |
| Tăng queue capacity để chữa quá tải kéo dài. | Latency tăng, vẫn thiếu năng lực xử lý. | Đo throughput, giảm chi phí task, điều tiết producer hoặc reject rõ. |
| Dùng `CallerRunsPolicy` ở thread không được phép block. | Thread gọi bị chiếm; có thể gây latency/deadlock. | Dùng handler thông báo overload hoặc kiến trúc điều tiết khác. |
| Dùng `DiscardPolicy` cùng `submit` rồi `Future.get()` vô hạn. | Future có thể không bao giờ hoàn tất. | Ưu tiên rejection tường minh; nếu drop, phải có trạng thái hủy/thông báo. |
| Retry ngay trong handler bằng cách nộp lại cùng pool. | Có thể lặp vô hạn hoặc khuếch đại quá tải. | Retry hữu hạn có backoff/điều kiện, thường quản lý bên ngoài handler. |
| Tin `getActiveCount()` là tín hiệu đồng bộ test. | Giá trị snapshot có race. | Dùng latch cho các mốc test; metric chỉ để quan sát. |
| Gọi `shutdown()` rồi mặc định task hoàn tất. | Shutdown không đợi. | `Future.get(timeout)` và `awaitTermination`. |
| Dùng queue bounded nhưng mỗi task giữ mảng rất lớn. | Vẫn có thể tốn quá nhiều RAM. | Kiểm soát kích thước payload, bộ nhớ trên mỗi task, cả dữ liệu đang chạy. |

## 12. Bài tập mở rộng

**Bài 1 — Thay đổi core và max.** Sửa ví dụ đầu thành `corePoolSize=1`, `maximumPoolSize=3`, queue capacity 2. Giữ task đang chạy bằng latch; nộp đủ công việc sao cho queue lấp đầy và worker mở rộng đến 3. Dự đoán chính xác task thứ mấy bị reject. Hãy nhớ: task thứ hai và thứ ba có thể vào queue trước khi pool mở rộng.

**Bài 2 — Handler có metric.** Dùng `AtomicLong` đếm rejection rồi ném `RejectedExecutionException`. Viết assertion rằng mỗi lần submit vượt sức chứa làm tăng bộ đếm một đơn vị; vẫn kiểm chứng task đã nhận hoàn tất.

**Bài 3 — Thay `AbortPolicy` bằng `CallerRunsPolicy`.** Giữ worker blocked rồi nộp task thứ ba từ test thread. Đoạn `execute` sẽ chỉ trả về sau khi task fallback chạy; nếu task fallback chặn ở latch mà test thread phải mở, có thể tự gây deadlock. Giải thích vì sao cần thiết kế để caller có thể hoàn thành task đó.

**Bài 4 — Rejection khi shutdown.** Sau `pool.shutdown()`, nộp task mới dưới `AbortPolicy` và xác nhận `RejectedExecutionException`. Thử lại với `CallerRunsPolicy` để quan sát rằng fallback không chạy khi pool đã shutdown; thảo luận vì sao cần chính sách báo lỗi cho caller.

**Bài 5 — Kiểm soát deadline.** Cho task mất thời gian dài hơn timeout của người gọi. Dùng `Future.get(timeout, unit)`; khi có `TimeoutException`, quyết định có `cancel(true)` hay không. Kiểm chứng task thực sự phản hồi interrupt; **timeout của `get` không tự dừng task**.

## 13. Checklist hoàn thành bài thực hành

- Có `ThreadPoolExecutor` với `corePoolSize`, `maximumPoolSize`, bounded `BlockingQueue` và `RejectedExecutionHandler` được chọn có chủ đích.
- Hiểu thứ tự xử lý khi core đã đủ, queue chưa đầy, queue đầy và max workers đã đạt.
- Có test xác định **task đang chạy** và **task xếp hàng**, chứng minh đúng ngưỡng rejection.
- Không bỏ qua mất task âm thầm; `Future` của các task bị loại có chính sách rõ ràng.
- Có bằng chứng cho `CallerRunsPolicy` chạy trong thread gọi và hiểu tác động latency/reentrancy.
- Có timeout cho các thao tác chờ, `shutdown()`/`shutdownNow()` và cleanup trong `finally`.
- Có số liệu vận hành phù hợp: pool size, queue depth, rejection rate, latency, throughput.
- Đã benchmark bằng workload thực; cấu hình queue/thread không chỉ dựa trên số CPU hay cảm giác.

**Kết luận:** Bounded queue biến giới hạn tiếp nhận công việc thành một phần rõ ràng của thiết kế `ThreadPoolExecutor`. Khi pool và queue đầy, rejection policy quyết định overload được thể hiện ra bên ngoài thế nào. Một executor vận hành an toàn cần **giới hạn worker + giới hạn queue + chính sách quá tải tường minh + cleanup đúng + test xác định**. Tăng số thread hay độ dài queue không tự tạo thêm khả năng xử lý.

### Tài liệu Java SE 17

- [`ThreadPoolExecutor` và quy tắc xếp hàng/rejection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [`RejectedExecutionHandler`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RejectedExecutionHandler.html)
- [`ArrayBlockingQueue`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html)
- [`ExecutorService`, `shutdown()`, `shutdownNow()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [`Future`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
