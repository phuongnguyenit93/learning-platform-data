# Kiểm soát số task đang chờ và backpressure trong Java Executor Framework

## 1. Vấn đề: producer có thể nhanh hơn consumer

Trong mô hình Executor Framework của Java, **producer** gọi `execute(...)` hoặc `submit(...)` để giao công việc, còn các **worker thread** thực thi tác vụ. Khi tốc độ công việc đi vào lớn hơn năng lực xử lý trong một khoảng thời gian đủ dài, tác vụ sẽ tích lại trong hàng đợi.

Ví dụ: hệ thống nhận trung bình 200 tác vụ/giây nhưng các worker chỉ hoàn thành trung bình 120 tác vụ/giây. Khi tốc độ này duy trì, hàng đợi tăng khoảng 80 tác vụ/giây (chưa xét thay đổi tốc độ và các giới hạn khác). Sau một phút, đã có thể có hàng nghìn tác vụ chờ. Tăng dung lượng queue chỉ trì hoãn thời điểm gặp giới hạn, **không làm tăng năng lực xử lý thực sự**.

Hệ quả:
- **Độ trễ tăng:** task đã được nhận nhưng phải đợi lâu mới chạy; timeout ở phía yêu cầu có thể xảy ra trước khi worker bắt đầu.
- **Bộ nhớ tăng:** mỗi `Runnable`, `Callable`, closure và dữ liệu mà nó tham chiếu còn được giữ khi nằm trong queue; nguy cơ `OutOfMemoryError`.
- **Công việc lỗi thời:** dữ liệu hoặc kết quả không còn giá trị khi được xử lý quá muộn.
- **Hiệu ứng dây chuyền:** producer vẫn nạp thêm việc, tạo áp lực đến downstream, disk, network hoặc dịch vụ khác.

**Backpressure** là cách chuyển tín hiệu “consumer không theo kịp” về phía producer, để producer **chậm lại, chờ, bị từ chối hoặc chủ động giảm tải**. Nó là một chính sách kiểm soát lưu lượng và số công việc tồn đọng; không đồng nghĩa với việc chỉ cấu hình `maximumPoolSize` lớn hơn.

Bài này tập trung vào **Java Concurrency nói chung**, đặc biệt là `ThreadPoolExecutor`, `BlockingQueue`, `Semaphore` và cơ chế admission control, không phụ thuộc framework.

## 2. Phân biệt các số lượng cần kiểm soát

| Đại lượng | Ý nghĩa | Cách giới hạn thường dùng |
| --- | --- | --- |
| Task đang chạy (running) | Công việc worker hiện đang thực thi | Kích thước pool, giới hạn tài nguyên hoặc semaphore |
| Task đang xếp hàng (queued) | Công việc đã được executor chấp nhận nhưng chưa bắt đầu | `BlockingQueue` có capacity hữu hạn |
| Task đang tồn tại trong hệ (in-flight/outstanding) | Tùy hợp đồng: thường bao gồm task đã nhận nhưng chưa hoàn tất, tức running + queued | Semaphore hoặc cơ chế cấp phép trước khi enqueue |
| Producer đang chờ nộp task | Lời gọi bị block trước admission; task chưa vào pool | `Semaphore.acquire()`, `tryAcquire(timeout, unit)`, bounded input queue |
| Task bị từ chối hoặc bỏ | Công việc không được pool nhận hoặc bị chính sách loại | Handler, metric, timeout, fallback và hợp đồng lỗi |

Không nên đánh đồng **giới hạn độ dài queue** với **giới hạn tổng số tác vụ**. Ví dụ pool có 4 worker và queue 100 phần tử có thể giữ khoảng 104 tác vụ đang chạy/chờ cùng lúc trong trạng thái đầy thông thường. Trong lúc hệ thống đồng thời hoạt động, số đếm và thời điểm chuyển giữa running/queued là biến động; con số “104” là mô hình capacity, không phải giao dịch nhận việc nguyên tử cho mọi lời gọi.

`getQueue().size()` và `getActiveCount()` chủ yếu phục vụ quan sát; dùng chúng để tự kiểm tra “nếu size nhỏ thì submit” là **check-then-act race**: producer khác có thể chiếm chỗ ngay giữa hai thao tác.

## 3. ThreadPoolExecutor quyết định xếp hàng như thế nào?

Với `ThreadPoolExecutor(corePoolSize, maximumPoolSize, keepAliveTime, unit, workQueue, threadFactory, handler)`, luồng điều khiển tổng quát của `execute(command)` là:

1. Nếu số worker nhỏ hơn `corePoolSize`, ưu tiên tạo worker mới để chạy task.
2. Nếu đã đạt ngưỡng core và executor còn nhận việc, thử `offer` task vào `workQueue`.
3. Nếu queue không nhận, thử mở thêm worker đến `maximumPoolSize`.
4. Nếu không nhận được hoặc executor đã shutdown, chuyển cho `RejectedExecutionHandler`.

Sau thao tác enqueue còn có bước kiểm tra lại trạng thái executor để xử lý trường hợp shutdown xảy ra đồng thời. Vì vậy, việc “queue có chỗ” chưa phải lời hứa chắc chắn tác vụ sẽ được chấp nhận.

### Tác động của loại queue

| Loại queue | Hành vi dưới tải | Lưu ý |
| --- | --- | --- |
| `ArrayBlockingQueue<>(capacity)` | Queue hữu hạn, producer có thể gặp rejection khi worker và queue đều đầy | Dễ đặt giới hạn rõ ràng, không tự block caller trong `execute` |
| `LinkedBlockingQueue<>(capacity)` | Cũng có giới hạn khi truyền capacity | Có cách quản lý nút và chi phí bộ nhớ khác `ArrayBlockingQueue` |
| `LinkedBlockingQueue<>()` | Giới hạn mặc định rất lớn (`Integer.MAX_VALUE`), thường tích tụ task trước khi đạt limit | `Executors.newFixedThreadPool(n)` dùng mô hình này; `maximumPoolSize` gần như không giúp nở pool khi queue tiếp tục nhận |
| `SynchronousQueue<>` | Không lưu task chờ, phải chuyển giao trực tiếp tới worker | Dễ tạo nhiều worker tới maximum; khi không thể chuyển giao hoặc mở worker thì rejection |
| `PriorityBlockingQueue<>`, `DelayQueue<>` | Thường không có capacity hữu hạn do ứng dụng đặt qua constructor chuẩn | Độ ưu tiên/độ trễ không thay thế kiểm soát lượng task |

**Điểm rất dễ nhầm:** `ThreadPoolExecutor.execute` dùng đường nhận việc không block lâu để chờ chỗ trong queue. Dùng `ArrayBlockingQueue<>(100)` **không tự biến lời gọi `execute` thành `put()`**; lúc quá tải nó sẽ thử nở pool rồi gọi rejection handler. Muốn chờ có kiểm soát, producer phải thực hiện admission control riêng, hoặc chấp nhận một handler như `CallerRunsPolicy`.

Không nên tự gọi `executor.getQueue().put(task)` để “ép” công việc vào pool: thao tác này đi vòng qua các kiểm tra trạng thái và quy tắc tạo worker của `execute`, có thể tạo task tồn đọng khi pool đóng hoặc không có worker nhận việc.

## 4. Các chiến lược backpressure chính

### 4.1. Bounded queue + AbortPolicy: từ chối có thể quan sát

`ArrayBlockingQueue` hoặc `LinkedBlockingQueue` với dung lượng hữu hạn đặt trần cho công việc đang chờ. `AbortPolicy` (mặc định của `ThreadPoolExecutor`) ném `RejectedExecutionException` khi executor không thể nhận task.

```java
// Fragment cấu hình: executor cần được shutdown khi không còn dùng.
ThreadPoolExecutor executor = new ThreadPoolExecutor(
        2, 4,
        30, TimeUnit.SECONDS,
        new ArrayBlockingQueue<>(100),
        new ThreadPoolExecutor.AbortPolicy());
```

Khi đã có 2 worker bận, task mới thường đi vào queue trước. Khi queue đầy, pool có thể tăng lên tối đa 4 worker. Sau đó, task mới bị từ chối. Với pool vừa tạo, thứ tự này giải thích vì sao đặt `maximumPoolSize=4` **không có nghĩa** pool tự mở 4 worker trước khi dùng queue.

Phù hợp khi producer hoặc tầng gọi có thể phản ứng với lỗi: trả “busy”, retry với giới hạn/thời gian lùi, chuyển sang kênh lưu bền vững hoặc ghi nhận tác vụ không được nhận. Đừng bắt exception rồi im lặng bỏ qua, vì như vậy đánh mất ưu điểm của chính sách này.

### 4.2. Bounded queue + CallerRunsPolicy: producer tự chịu chi phí

Khi quá tải **và executor vẫn đang chạy**, `CallerRunsPolicy` thực thi `Runnable.run()` ngay trên **thread đang gọi `execute`**. Producer phải chờ tác vụ đó hoàn tất trước khi nạp tiếp, nên tốc độ đầu vào bị kéo xuống một cách tự nhiên.

Phù hợp nếu caller được phép chạy tác vụ và chịu thời gian block. Cần thận trọng nếu caller là event loop, UI thread, một worker đang giữ lock hoặc thread đòi hỏi độ trễ phản hồi nghiêm ngặt: nó có thể bị chặn lâu hoặc phát sinh deadlock do phụ thuộc lẫn nhau.

Những giới hạn quan trọng:
- Khi executor **đã shutdown**, `CallerRunsPolicy` bỏ task; nó không thực thi fallback.
- Task chạy trên thread gọi, nên môi trường `ThreadLocal`, context, tên luồng và quản lý lỗi có thể khác worker.
- Nếu task chạy trực tiếp ném unchecked exception, đường truyền exception của `execute` có thể khác task chạy trên worker; không mặc định rằng mọi exception đều bị executor lưu lại.
- Khi producer là thread chính nhưng lại phải phục vụ nhiệm vụ ưu tiên cao, việc tự chạy task có thể tạo chậm trễ dây chuyền.

### 4.3. Semaphore: giới hạn số task outstanding trước khi gửi

`Semaphore` giữ một số **permit** hữu hạn. Producer phải lấy permit **trước khi gửi** task; permit được trả khi task hoàn tất. Nếu có 20 permit, thiết kế đang hướng tới tối đa 20 task đã được nhận nhưng chưa hoàn tất (bao gồm task đang chạy và đang chờ). Permit không tăng số worker; nó giới hạn lượng công việc mà ứng dụng cho phép tiếp nhận.

Ba cách phổ biến:

- `acquire()`: đợi cho tới khi có permit hoặc bị interrupt; cung cấp backpressure bằng blocking.
- `tryAcquire()`: trả `false` ngay khi không có permit; cung cấp fast-fail/admission rejection.
- `tryAcquire(timeout, unit)`: đợi tối đa một khoảng thời gian, rồi trả `false`; thường có ích khi có deadline.

Quy tắc quan trọng: **lấy permit → gửi task → trả permit khi task kết thúc; nếu gửi bị từ chối thì trả permit ngay**. Đưa `release()` vào `finally` của phần thực thi để tránh rò permit khi task ném exception. Với `AbortPolicy`, có thể xử lý `RejectedExecutionException` từ lời gọi `execute` để trả lại permit trước khi báo lỗi cho producer.

```java
// Fragment: dùng ThreadPoolExecutor với AbortPolicy;
// truyền permits và work vào từ nơi cấu hình.
static boolean trySubmit(ThreadPoolExecutor executor,
                         Semaphore permits,
                         Runnable work) {
    if (!permits.tryAcquire()) {
        return false; // Chưa gửi vào executor.
    }

    try {
        executor.execute(() -> {
            try {
                work.run();
            } finally {
                permits.release();
            }
        });
        return true;
    } catch (RejectedExecutionException rejected) {
        permits.release(); // Task không được executor nhận.
        return false;
    }
}
```

Ở ví dụ này, `false` có nghĩa hệ thống **không nhận task**: hoặc không có permit, hoặc executor từ chối. Khi cần báo rõ nguyên nhân, hãy trả về loại kết quả cụ thể hơn thay vì chỉ dùng boolean.

**Phân biệt hai giới hạn:** số permit nên được chọn theo khả năng chấp nhận task của hệ thống, không nhất thiết phải bằng `maximumPoolSize + queueCapacity`. Ngay cả khi hai giới hạn bằng nhau, semaphore không bảo đảm 100% rằng `execute` không thể bị từ chối: shutdown, producer không dùng cùng semaphore, hoặc chuyển giao permit sát thời điểm worker kết thúc đều có thể tạo race. Vẫn cần handler và hoàn permit khi rejection.

### 4.4. Giới hạn tổng tải trước khi tạo executor task

Có thể đặt `Semaphore` ở đầu pipeline thay vì ngay trước pool. Producer nhận tín hiệu không còn công suất **trước khi tạo một lượng lớn object/task**, đọc dữ liệu hoặc phát lời gọi phụ. Nếu dữ liệu đầu vào phải được lưu bền vững, áp dụng admission tại ranh giới thích hợp và thiết kế nơi nhận lại các công việc chưa xử lý. Đừng tạo vô hạn producer thread chỉ để chúng block trên `acquire()`: như vậy chuyển sự tích tụ từ queue sang tập thread đang chờ.

### 4.5. Giảm tải có chủ đích (load shedding)

Nếu công việc không bắt buộc thực hiện đầy đủ, producer có thể:
- Bỏ mẫu/sự kiện không thiết yếu và tăng metric dropped.
- Gộp các cập nhật trùng khóa, chỉ giữ trạng thái mới nhất (coalescing).
- Áp dụng deadline: không nhận task đã hết giá trị trước khi bắt đầu.
- Ưu tiên công việc thiết yếu; tách pool/capacity giữa các loại workload để giảm ảnh hưởng lẫn nhau.

`DiscardPolicy` âm thầm bỏ task mới, còn `DiscardOldestPolicy` bỏ phần tử đầu queue rồi thử nộp task mới. Hai chính sách này không phải backpressure đáng tin cậy cho công việc cần phản hồi: `submit()` có thể trả một `Future` chưa bao giờ hoàn tất khi task bị bỏ. `DiscardOldestPolicy` cũng có rủi ro retry lặp lại với queue không lưu phần tử như `SynchronousQueue`. Thường nên thiết kế việc “thay task cũ” và phản hồi/hủy `Future` một cách tường minh.

## 5. Ví dụ Java 17 chạy độc lập: hai cách kiểm soát tải

Chương trình minh họa:

1. **`CallerRunsPolicy`** với 1 worker và queue 1 chỗ: A đang chạy, B đang chờ, C sẽ phải chạy trên `main`.
2. **`Semaphore(2)` + `AbortPolicy`**: chỉ chấp nhận 2 task outstanding. Khi A đang chạy và B đã nhận, task C bị chặn ở bước admission (`tryAcquire() == false`), chưa đưa vào executor.

`CountDownLatch` giữ A đang chạy để tạo trạng thái quá tải **có kiểm soát**, tránh phụ thuộc `Thread.sleep` và tốc độ máy. Lưu tệp `BackpressureDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class BackpressureDemo {
    public static void main(String[] args) throws Exception {
        callerRunsExample();
        semaphoreExample();
    }

    private static void callerRunsExample() throws Exception {
        List<String> events =
                Collections.synchronizedList(new ArrayList<>());
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch releaseA = new CountDownLatch(1);

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.CallerRunsPolicy());

        try {
            pool.execute(() -> {
                events.add("A running");
                started.countDown();
                awaitUninterruptiblyForDemo(releaseA);
                events.add("A done");
            });

            started.await(); // A chiếm worker.
            pool.execute(() -> events.add("B done")); // B trong queue.
            events.add("before C");
            pool.execute(() ->
                    events.add("C on " + Thread.currentThread().getName()));
            events.add("after C");
        } finally {
            releaseA.countDown();
            pool.shutdown();
        }

        if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
            throw new AssertionError("CallerRuns pool did not terminate");
        }
        System.out.println("CallerRuns: " + String.join(" | ", events));
    }

    private static void semaphoreExample() throws Exception {
        List<String> events =
                Collections.synchronizedList(new ArrayList<>());
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch releaseA = new CountDownLatch(1);
        Semaphore permits = new Semaphore(2);

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy());

        try {
            boolean a = trySubmit(pool, permits, () -> {
                events.add("A running");
                started.countDown();
                awaitUninterruptiblyForDemo(releaseA);
                events.add("A done");
            });
            started.await(); // A chạy, chiếm permit đầu tiên.

            boolean b = trySubmit(
                    pool, permits, () -> events.add("B done"));
            boolean c = trySubmit(
                    pool, permits, () -> events.add("C done"));

            events.add("accepted=" + a + "," + b + "," + c);
        } finally {
            releaseA.countDown();
            pool.shutdown();
        }

        if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
            throw new AssertionError("Semaphore pool did not terminate");
        }
        System.out.println("Semaphore: " + String.join(" | ", events));
    }

    // Dùng với AbortPolicy: rejection tại execute() nghĩa là không nhận task.
    private static boolean trySubmit(ThreadPoolExecutor pool,
                                     Semaphore permits,
                                     Runnable work) {
        if (!permits.tryAcquire()) {
            return false;
        }
        try {
            pool.execute(() -> {
                try {
                    work.run();
                } finally {
                    permits.release();
                }
            });
            return true;
        } catch (RejectedExecutionException rejected) {
            permits.release();
            return false;
        }
    }

    // Chỉ phục vụ demo: giữ trạng thái A cho tới khi main mở latch.
    private static void awaitUninterruptiblyForDemo(CountDownLatch latch) {
        boolean interrupted = false;
        while (true) {
            try {
                latch.await();
                break;
            } catch (InterruptedException e) {
                interrupted = true;
            }
        }
        if (interrupted) {
            Thread.currentThread().interrupt();
        }
    }
}
```

Biên dịch và chạy bằng Java 17+:

```bash
javac BackpressureDemo.java
java BackpressureDemo
```

Stdout:

```text
CallerRuns: A running | before C | C on main | after C | A done | B done
Semaphore: A running | accepted=true,true,false | A done | B done
```

Trong nhánh đầu, `execute(C)` không xếp được vào queue và `CallerRunsPolicy` thực thi C trên `main` trước khi lệnh gửi việc kết thúc. Trong nhánh sau, C không có permit nên `trySubmit` trả `false` mà không đưa C vào queue. Hai nhánh chứng minh hai vị trí khác nhau của backpressure: **ngay trong handler sau saturation** và **trước lúc gửi task vào pool**.

Hàm đợi latch trong demo cố tình khôi phục interrupt flag sau khi hoàn tất chờ để chứng minh thứ tự sự kiện. Code sản phẩm thường phải có đường xử lý interrupt/shutdown phù hợp, không nên sao chép cơ chế đợi không ngắt này cho một worker thực tế.

## 6. Blocking admission có timeout và interruption

Đối với tác vụ yêu cầu chờ chỗ một thời gian nhất định, có thể thay `permits.tryAcquire()` bằng:

```java
// Fragment trong một method có throws InterruptedException:
boolean admitted = permits.tryAcquire(200, TimeUnit.MILLISECONDS);
if (!admitted) {
    // Quá hạn chờ nhận việc: báo busy/deadline exceeded.
    return;
}
try {
    executor.execute(() -> {
        try {
            work.run();
        } finally {
            permits.release();
        }
    });
} catch (RejectedExecutionException rejected) {
    permits.release();
    throw rejected;
}
```

Đoạn này giả định `executor` được cấu hình `AbortPolicy`, `permits` và `work` đã khởi tạo. Nếu bị interrupt **trong khi chờ permit**, `tryAcquire(timeout, unit)` ném `InterruptedException` và **không có permit nào cần hoàn lại**. Phương thức gọi thường nên truyền tiếp interrupt hoặc xử lý theo hợp đồng cancellation của ứng dụng; không âm thầm nuốt interrupt rồi chờ mãi.

Một producer có thể đặt deadline tổng thể và trừ đi thời gian đã tiêu tốn để tránh thời gian chờ admission + thời gian chạy vượt quá hạn định. Nếu producer timeout sau khi task đã được executor nhận, cần có chiến lược hủy/đối chiếu trạng thái riêng: timeout ở phía producer **không tự dừng worker**.

`Semaphore` mặc định không bảo đảm fairness. `new Semaphore(n, true)` ưu tiên thứ tự chờ theo cơ chế fairness của semaphore, đổi lấy chi phí/throughput có thể khác; các lệnh `tryAcquire()` không timeout có thể giành permit ngay cả khi đã có luồng chờ trong semaphore fair. Nếu thực sự cần tuân thủ hàng chờ công bằng, chọn API và kiểm thử semantics tương ứng; fairness không thay thế hạn chờ.

## 7. Thiết kế permit không bị rò rỉ

Mẫu `trySubmit` ở trên thích hợp để dạy về đường **nhận–chạy–hoàn tất** khi dùng `AbortPolicy` và `execute`. Trong hệ thống thật, cần xem xét vòng đời task đầy đủ:

- **Exception từ task:** `finally` trong wrapper vẫn trả permit khi `Runnable.run()` ném lỗi.
- **Rejection trước khi nhận:** phải trả permit tại luồng nộp task, nếu không capacity sẽ giảm vĩnh viễn.
- **`shutdown()`:** từ chối task mới nhưng các task đã nhận được chạy tiếp theo trình tự shutdown có kiểm soát; permit được trả khi chúng chạy xong.
- **`shutdownNow()`:** có thể trả về danh sách task **chưa bắt đầu** trong queue. Wrapper của chúng chưa chạy, nên `finally` của wrapper **không được gọi** và permit vẫn bị chiếm. Cần đối chiếu các task bị lấy ra và hoàn lại permit/hủy trạng thái một lần; đồng thời phối hợp interrupt cho task đang chạy.
- **`remove(runnable)`, `purge()`, hủy Future/đường hủy tùy biến:** nếu task không bao giờ chạy, cơ chế chỉ trả permit khi task chạy sẽ rò permit. Nếu dùng `submit`, executor có thể bọc task thành `FutureTask`; việc gắn ownership và cleanup cần được thiết kế nhất quán.
- **Đường chuyển sang CallerRuns:** nếu đổi handler thành `CallerRunsPolicy`, task có thể chạy ngay trên luồng gọi; việc ném `RejectedExecutionException` từ **bên trong task** có thể khiến đoạn `catch` của producer hiểu nhầm là executor từ chối và release permit **hai lần**. Không dùng máy móc wrapper dành cho `AbortPolicy` khi thay handler.

Để production hóa vòng đời nhiều trường hợp, dùng token/handle trạng thái có thao tác hoàn permit **đúng một lần** (ví dụ `AtomicBoolean.compareAndSet(false, true)`), cơ chế đăng ký task trước khi enqueue và đường cleanup cho queued task bị hủy. Nếu không thể chứng minh được toàn bộ đường kết thúc, đừng tuyên bố rằng semaphore bao được mọi trường hợp.

## 8. Backpressure khác rate limiting như thế nào?

**Rate limiting** giới hạn số request hoặc task đến trong một khoảng thời gian (ví dụ token bucket 100/s). **Concurrency limiting** giới hạn lượng công việc đồng thời. **Queue bounding** giới hạn số task đang đợi. **Backpressure** là cơ chế để phản ứng khi tài nguyên phía sau không theo kịp: block, trả tín hiệu chậm lại, timeout hoặc reject.

Một hệ thống có thể cần cả ba loại giới hạn: rate limit để kiềm chế đỉnh đến, semaphore để tránh quá nhiều tác vụ đang tồn tại, queue hữu hạn để tránh tích tụ bộ nhớ. Có rate limit nhưng tác vụ xử lý chậm bất ngờ thì vẫn có thể backlog. Có queue hữu hạn nhưng caller tiếp tục retry không giới hạn thì có thể tạo áp lực ngược lên hệ thống bên ngoài.

Theo định luật Little ở **trạng thái ổn định**, quan hệ trung bình `L = λ × W` liên hệ số công việc trong hệ (`L`), thông lượng (`λ`) và thời gian lưu trong hệ (`W`). Ví dụ throughput 100 task/giây và thời gian tồn tại trung bình 0,5 giây tương ứng khoảng 50 task đang tồn tại trung bình. Đây là **quan hệ quan sát tại trạng thái ổn định**, không phải công thức đặt capacity tuyệt đối cho burst, timeout, tài nguyên hạn chế hay overload kéo dài.

Đối với workload CPU-bound, tăng worker quá số lõi khả dụng có thể làm tranh CPU và context switch nhiều hơn. Với I/O-bound, số tác vụ chờ I/O có thể lớn hơn, nhưng phải xét connection pool, memory, giới hạn bên ngoài và deadline. Dung lượng queue phụ thuộc mức burst muốn hấp thụ và ngân sách độ trễ, không nên chọn tùy ý quá lớn.

## 9. Quan sát, kiểm thử và vận hành

### Chỉ số nên theo dõi

- **Admission:** số task gửi, nhận, từ chối, timeout chờ permit, bị drop; phân loại rejection do shutdown và saturation khi có thể.
- **Độ sâu queue:** `getQueue().size()`, queue capacity, xu hướng tăng và thời gian chờ task trước khi bắt đầu.
- **Pool:** `getActiveCount()`, `getPoolSize()`, `getCompletedTaskCount()`, thời gian xử lý và bão hòa thực tế.
- **Producer:** thời gian bị chặn do semaphore/`CallerRunsPolicy`, số producer đang chờ, số timeout phía caller.
- **End-to-end:** độ trễ p95/p99, lỗi, request bị hủy, độ tuổi task khi được thực thi và số công việc còn tồn đọng trong pipeline.

Các getter của `ThreadPoolExecutor` là số liệu tức thời hoặc gần đúng khi chạy concurrent, hữu ích cho monitoring nhưng không dùng làm điều kiện kiểm soát nhận việc kiểu đọc rồi gửi. Mọi nhánh drop/rejection cần metric hoặc tín hiệu rõ ràng; nếu chỉ đo queue size có thể bỏ sót công việc đã bị loại.

### Tình huống kiểm thử cần có

1. Một worker bận + queue đầy: xác nhận pool kích hoạt handler mong đợi.
2. Producer nộp nhanh trong thời gian dài: xác nhận queue và số task outstanding không tăng vượt mục tiêu; độ trễ còn chấp nhận.
3. Task ném exception: permit phải quay lại.
4. Chờ permit bị interrupt/timeout: không nộp task, không release nhầm.
5. Shutdown và shutdownNow: xác nhận nơi nào trả task chưa chạy, task nào được hủy, permit và Future nào cần cleanup.
6. Nhiều producer cạnh tranh: kiểm tra race admission, retry có giới hạn, không tạo duplicate hoặc lost task ngoài hợp đồng.
7. Task phụ thuộc kết quả của task khác cùng pool: kiểm tra deadlock, nhất là khi `CallerRunsPolicy` hoặc producer đang giữ khóa.

Có thể dùng `CountDownLatch` như ví dụ để tạo trạng thái queue đầy một cách xác định; `Thread.sleep` đơn lẻ không bảo đảm task nào đang chạy hoặc đang chờ. Load test thực tế cần có burst, tốc độ tăng giảm, service time biến động và downstream chậm.

## 10. Lỗi thiết kế thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Chỉ tăng `LinkedBlockingQueue` rất lớn để né rejection | Backlog và độ trễ/bộ nhớ tăng âm thầm | Đặt capacity theo ngân sách độ trễ và giới hạn tổng tải |
| Cho rằng queue hữu hạn tự block `execute` | Khi đầy pool có thể ném `RejectedExecutionException` hoặc gọi handler | Đặt cơ chế backpressure cụ thể: abort/CallerRuns/semaphore |
| Chỉ kiểm tra `queue.size() < limit` trước khi gửi | Check-then-act race dưới nhiều producer | Dùng `Semaphore.tryAcquire`/`acquire` hoặc cơ chế admission nguyên tử |
| Dùng `CallerRunsPolicy` cho luồng không được block | Luồng gọi bị chiếm, tăng latency hoặc deadlock | Chọn fast-fail, timeout hoặc chuyển admission sang boundary phù hợp |
| Nuốt `RejectedExecutionException` | Mất việc nhưng không có tín hiệu | Ghi metric và phản hồi/retry có giới hạn/lưu bền vững |
| Dùng `DiscardPolicy` với `submit` rồi chờ `Future.get()` | Future có thể không hoàn tất bao giờ | Dùng chính sách rõ lỗi hoặc quản lý hủy Future |
| `release()` chỉ nằm trong task, bỏ qua reject/cancel queued task | Rò permit, hệ thống ngừng nhận việc sau một thời gian | Bảo đảm cleanup đúng một lần trên mọi đường kết thúc |
| Retry liên tục trên cùng pool đang bão hòa | Tăng áp lực CPU, tạo vòng lặp và khiến overload kéo dài | Backoff có jitter, budget retry, deadline hoặc báo busy |
| Tăng tối đa số thread mà không xét downstream | Tranh tài nguyên, latency cao, lỗi hàng loạt | Đo bottleneck, giới hạn concurrency theo tài nguyên thật |

## 11. Câu hỏi tự kiểm tra

**1. Một pool 2 core, 4 maximum, queue 10 chỗ. Khi có 2 worker bận và queue còn trống, executor ưu tiên mở worker thứ 3 không?**  
Thông thường không; `execute` ưu tiên enqueue sau khi đã đạt core, rồi mới thêm worker khi queue không nhận task.

**2. Queue hữu hạn có tự làm producer chờ không?**  
Không. `ThreadPoolExecutor.execute` thử nhận bằng queue rồi có thể tăng worker hoặc gọi rejection handler; cần `CallerRunsPolicy`, semaphore hoặc admission khác nếu muốn làm chậm producer.

**3. Semaphore(20) giới hạn chính xác điều gì?**  
Giới hạn số permit được cấp đồng thời. Nếu mọi producer đều lấy permit trước khi gửi và release đúng một lần khi task kết thúc, nó biểu diễn tối đa 20 task outstanding theo hợp đồng đó. Nó không tự giới hạn những task bỏ qua semaphore và không bảo đảm pool luôn nhận.

**4. Vì sao shutdownNow có thể làm rò permit?**  
Task chưa chạy bị lấy khỏi queue sẽ không đi vào wrapper có `finally { permits.release(); }`. Caller cần xử lý danh sách task chưa bắt đầu và cơ chế cleanup.

**5. Backpressure có nhất thiết là chặn producer không?**  
Không. Nó có thể là chạy công việc trên caller, trả lỗi bận, chờ có timeout, giảm tải hoặc chuyển sang kênh có khả năng tiếp nhận riêng. Chọn hành vi dựa trên giá trị công việc, deadline, tính bền vững và tác động tới producer.

## Tài liệu tham khảo

- [Java SE 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Java SE 17 — BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html)
- [Java SE 17 — Semaphore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html)
- [Java SE 17 — RejectedExecutionHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RejectedExecutionHandler.html)
