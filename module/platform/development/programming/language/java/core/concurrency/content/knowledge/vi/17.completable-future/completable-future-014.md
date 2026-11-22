# Giới hạn concurrency khi tạo hàng loạt future bằng CompletableFuture

## 1. Bài toán: hàng nghìn future không có nghĩa là hàng nghìn task nên chạy đồng thời

`CompletableFuture<T>` giúp biểu diễn một kết quả có thể hoàn tất trong tương lai, ghép các bước xử lý và thu thập lỗi. Khi cần xử lý nhiều đầu vào, cách viết thường thấy là:

```java
// Snippet: executor đã khai báo; items là List<Item>.
List<CompletableFuture<Result>> futures = items.stream()
        .map(item -> CompletableFuture.supplyAsync(
                () -> process(item), executor))
        .toList();

CompletableFuture.allOf(
        futures.toArray(new CompletableFuture<?>[0])
).join();
```

Đây **chỉ là snippet**: `Item`, `Result`, `items`, `executor`, `process` chưa được khai báo. Nó nêu rõ một vấn đề: **một vòng lặp có thể nộp toàn bộ task trước khi đợi chúng hoàn thành**.

Nếu danh sách có 100.000 phần tử:

- 100.000 `CompletableFuture` có thể được tạo và giữ trong bộ nhớ.
- Executor có thể chỉ có 8 worker, nhưng **queue** của nó vẫn có thể nhận rất nhiều task.
- Nếu mỗi task thực hiện I/O, tạo kết nối hoặc gọi downstream, giới hạn worker chưa chắc đã là giới hạn số thao tác ngoại vi **đã khởi phát** (đặc biệt với I/O bất đồng bộ).
- Bộ nhớ dùng cho task, lambda, captured objects, futures và metadata tăng theo số việc đã gửi; sự quá tải có thể xuất hiện **trước khi** worker xử lý xong.

**Mục tiêu của giới hạn concurrency** là giữ số tác vụ đang thực sự dùng một resource **không vượt một ngưỡng rõ ràng** và, khi cần, giữ cả số việc đang chờ được chấp nhận ở mức có kiểm soát.

Bài này tập trung vào **Java concurrency nói chung** với JDK **Java 17+**, không phụ thuộc Spring hoặc framework khác.

## 2. Phân biệt bốn đại lượng dễ bị đánh đồng

| Đại lượng | Ý nghĩa | Cơ chế kiểm soát |
| --- | --- | --- |
| **Số phần tử đầu vào** | Tổng lượng công việc cần giải quyết | Chia lô, luồng dữ liệu, phân trang |
| **Số future đã tạo** | Số đối tượng biểu diễn trạng thái tác vụ | Chỉ tạo trong cửa sổ giới hạn, tránh giữ kết quả vô hạn |
| **Số task đang được worker thực thi** | Công việc đã bắt đầu chạy trong executor | Kích thước pool, executor admission |
| **Số thao tác ngoại vi thực sự đang hoạt động** | Ví dụ HTTP request đã gửi hoặc database query chưa trả lời | Semaphore/bulkhead gắn với **vòng đời I/O thực tế** |

**Một `CompletableFuture` không nhất thiết là một thread.** Một future có thể đã hoàn tất sẵn, đang chờ task trên queue, đại diện cho bước `thenApply`, hoặc theo dõi một thao tác I/O không chặn worker.

Tương tự, **`CompletableFuture.allOf(...)` chỉ tổ hợp tín hiệu hoàn tất; nó không giới hạn concurrency**. `allOf` không điều chỉnh kích thước queue, không tạo backpressure và không đảm bảo mọi kết quả đều thành công.

### Concurrency, parallelism, throughput và rate limit

- **Concurrency**: số công việc đang tồn tại/chưa hoàn tất đồng thời tại một ranh giới được chọn.
- **Parallelism**: số công việc thực sự được thực thi song song, chẳng hạn trên nhiều CPU core.
- **Throughput**: số công việc hoàn tất trên mỗi giây, phụ thuộc thời gian và khả năng xử lý.
- **Rate limit**: giới hạn số công việc được bắt đầu trong một đơn vị thời gian (ví dụ yêu cầu/giây).

`Semaphore(10)` giới hạn **số permit có thể giữ cùng lúc**, không trực tiếp hứa “tối đa 10 request mỗi giây”. Nếu request trả rất nhanh, nó vẫn cho phép bắt đầu nhiều request trong một giây. Ngược lại, nếu request rất chậm, chỉ 10 request có thể còn đang hoạt động nhưng throughput thấp.

Một hệ thống thường cần **cả giới hạn concurrency lẫn tốc độ tạo yêu cầu, số kết nối và giới hạn queue**, tùy loại tài nguyên.

## 3. Vì sao fixed thread pool chưa giải quyết hết fan-out?

`Executors.newFixedThreadPool(8)` tạo executor với số worker cố định. Điều đó là hữu ích đối với **task blocking chạy trên worker**: cùng lúc không có hơn số worker đang thực thi task trong pool theo thiết kế.

Nhưng `newFixedThreadPool` thường có **work queue không giới hạn thực tế**. Một vòng lặp tạo hàng chục nghìn `supplyAsync` vẫn có thể đẩy hàng chục nghìn task vào queue:

```text
Producer nhanh:
  submit 1, 2, 3, ... 100000
               |
               v
  Executor: 8 worker đang chạy
            |
            +-- queue: rất nhiều task chưa được chạy
               |
               v
          Bộ nhớ / latency / backlog
```

Không nên suy:

- “Pool có 8 worker nên việc submit 100.000 task không tốn bộ nhớ đáng kể.”
- “Chỉ có 8 worker nên tối đa 8 future chưa hoàn tất.”
- “Mỗi khi `allOf.join()` trả về, mọi future đều thành công.” Nếu một input future lỗi, `allOf` cũng hoàn tất exceptional; phải xử lý lỗi.
- “Tăng kích thước pool sẽ luôn làm chương trình nhanh hơn.” Tăng song song có thể làm downstream quá tải, tăng context switching hoặc tranh chấp lock.

**Có hai lớp giới hạn khác nhau:** giới hạn **executing** (đang dùng worker/resource) và giới hạn **admission/backlog** (công việc được phép đi vào pipeline). Một bài toán lớn thường phải kiểm soát cả hai.

## 4. Cách 1: xử lý theo cửa sổ/batch cố định

Đây là cách dễ giải thích nhất: chỉ tạo tối đa `windowSize` future ở mỗi lô, đợi toàn lô xong, rồi mới tạo lô kế tiếp.

Ưu điểm:

- Số future “đang hoạt động trong một lô” được giới hạn rõ ràng.
- Dễ áp dụng khi dữ liệu đã được chia batch hoặc một lô cần đủ kết quả trước khi sang lô sau.
- Không cần semaphore, và dễ quản lý executor ở scope gọi.

Hạn chế:

- **Barrier ở cuối lô**: nếu một task trong lô rất chậm, các slot còn lại có thể rảnh trong lúc chờ task chậm đó. Vì vậy throughput có thể thấp hơn mô hình **rolling window** luôn bổ sung task khi có một task hoàn tất.
- Nếu input đã nạp toàn bộ vào List trong bộ nhớ, chia lô chỉ giới hạn số future chứ **không tự giới hạn bộ nhớ đầu vào**.
- `allOf.join()` không có timeout sẵn; nếu task có thể treo, thiết kế timeout và cleanup rõ.

### Ví dụ Java 17+ chạy độc lập: tối đa 4 future mỗi lô

Tạo file `WindowedBatchDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class WindowedBatchDemo {
    public static void main(String[] args) {
        ExecutorService executor = Executors.newFixedThreadPool(8);
        final int windowSize = 4;
        int total = 0;
        int batches = 0;

        try {
            for (int start = 1; start <= 10; start += windowSize) {
                List<CompletableFuture<Integer>> window =
                        new ArrayList<>();

                for (int value = start;
                     value < start + windowSize && value <= 10;
                     value++) {
                    final int input = value;
                    window.add(CompletableFuture.supplyAsync(
                            () -> input, executor));
                }

                CompletableFuture.allOf(
                        window.toArray(new CompletableFuture<?>[0])
                ).join();

                for (CompletableFuture<Integer> future : window) {
                    total += future.join();
                }
                batches++;
            }
        } finally {
            executor.shutdown();
        }

        System.out.println("Processed inputs: 10");
        System.out.println("Sum: " + total);
        System.out.println("Batches: " + batches);
    }
}
```

Biên dịch/chạy với JDK 17+:

```bash
javac WindowedBatchDemo.java
java WindowedBatchDemo
```

Đầu ra:

```text
Processed inputs: 10
Sum: 55
Batches: 3
```

Ba lô lần lượt chứa các input 1–4, 5–8 và 9–10. Mỗi lô chỉ tạo tối đa bốn future rồi chờ, nên không bao giờ chủ động gửi toàn bộ mười tác vụ cùng lúc. `total` là tổng các số 1 đến 10, bằng 55, không phụ thuộc thứ tự worker hoàn tất. Pool có tám worker nhưng **cửa sổ** chỉ cho tối đa bốn task của lô hiện tại.

**Lưu ý về lỗi:** ví dụ chỉ dùng các task luôn thành công. Nếu một future thất bại, `allOf(...).join()` có thể ném `CompletionException`; phải có chính sách đánh dấu lỗi, xử lý kết quả từng phần và dừng/tiếp tục lô. `finally` vẫn gọi `shutdown`, nhưng shutdown không phải chờ có deadline. Với task có thể kẹt, cần bổ sung timeout, cancellation và theo dõi termination.

## 5. Cách 2: Semaphore cấp permit **trước khi submit**

Để vẫn bổ sung công việc liên tục nhưng không tạo vô hạn future, có thể dùng một `Semaphore` biểu diễn “quyền có một tác vụ đang được nhận/chạy trong hệ thống”.

Pattern:

```text
Producer có item
      |
      v
permits.acquire()  <--- hết permit thì producer phải chờ
      |
      v
tạo CompletableFuture / gửi vào executor
      |
      v
supplier chạy và kết thúc (kể cả ném lỗi)
      |
      v
finally { permits.release(); }
      |
      v
producer có thể gửi item tiếp theo
```

**Điểm then chốt là vị trí `acquire()`:** thực hiện **trước** `supplyAsync()`, để producer **không thể tạo nhiều hơn giới hạn công việc chưa xong**. Nếu đưa `semaphore.acquire()` **bên trong** mỗi supplier sau khi đã `supplyAsync` hàng trăm nghìn lần, tất cả future/task vẫn được tạo và đưa vào queue; semaphore lúc đó chỉ giới hạn đoạn code bên trong supplier, **không phải lượng công việc đã submit**.

Một nguyên tắc khác: **nhả permit đúng một lần cho mỗi acquire thành công**. Nếu executor từ chối việc submit, producer phải trả lại permit. Nếu task bắt đầu và kết thúc bình thường hoặc ném exception, supplier nên nhả permit trong `finally`.

### Ví dụ Java 17+: giới hạn tối đa 3 task đã nhận/chưa kết thúc

Tạo file `SemaphoreFanOutDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class SemaphoreFanOutDemo {
    static CompletableFuture<Integer> submitBounded(
            int input,
            ExecutorService executor,
            Semaphore permits,
            AtomicInteger active,
            AtomicInteger peak) throws InterruptedException {

        permits.acquire(); // Chặn producer trước khi tạo future.

        try {
            return CompletableFuture.supplyAsync(() -> {
                int now = active.incrementAndGet();
                try {
                    peak.accumulateAndGet(now, Math::max);
                    return input * input;
                } finally {
                    active.decrementAndGet();
                    permits.release(); // Kết thúc thực thi supplier.
                }
            }, executor);
        } catch (RejectedExecutionException e) {
            permits.release(); // Executor không nhận task.
            throw e;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        final int maxInFlight = 3;
        Semaphore permits = new Semaphore(maxInFlight);
        ExecutorService executor = Executors.newFixedThreadPool(6);
        AtomicInteger active = new AtomicInteger();
        AtomicInteger peak = new AtomicInteger();
        List<CompletableFuture<Integer>> futures = new ArrayList<>();

        try {
            for (int input = 0; input < 12; input++) {
                futures.add(submitBounded(
                        input, executor, permits, active, peak));
            }

            CompletableFuture.allOf(
                    futures.toArray(new CompletableFuture<?>[0])
            ).join();

            int sum = futures.stream()
                    .mapToInt(CompletableFuture::join)
                    .sum();

            System.out.println("Results: " + futures.size());
            System.out.println("Sum of squares: " + sum);
            System.out.println("Peak <= 3: " + (peak.get() <= 3));
            System.out.println("Active after completion: "
                    + active.get());
            System.out.println("Available permits: "
                    + permits.availablePermits());
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
                throw new IllegalStateException("Executor did not stop");
            }
        }
    }
}
```

Chạy:

```bash
javac SemaphoreFanOutDemo.java
java SemaphoreFanOutDemo
```

Đầu ra khi task không bị hủy ngoài ý muốn:

```text
Results: 12
Sum of squares: 506
Peak <= 3: true
Active after completion: 0
Available permits: 3
```

Giải thích:

1. Mặc dù pool có tối đa sáu worker, **producer chỉ cấp tối đa ba permit**. Nó không tạo future thứ tư khi ba permit vẫn được giữ.
2. Supplier tính bình phương input từ 0 tới 11; tổng bình phương là 506.
3. `active` dùng để quan sát có bao nhiêu supplier đang chạy; `peak` ghi giá trị lớn nhất thấy được. Con số peak thực tế có thể là 1, 2 hoặc 3 theo scheduling, nên ví dụ chỉ assert **`peak <= 3`**, không in “peak chắc chắn bằng 3”.
4. `finally` của supplier nhả permit **trước khi future được hoàn tất**. Khi `allOf.join()` trở về bình thường, tất cả supplier đã hoàn tất, và số permit trở về 3.
5. Nếu `supplyAsync` bị executor **từ chối trước khi nhận task**, nhánh catch giải phóng permit đã lấy. Đây là mẫu dành cho executor có hợp đồng `RejectedExecutionException` thông thường.
6. `permits.acquire()` có thể ném `InterruptedException` trước khi cấp permit; trong trường hợp đó không được release vì producer chưa sở hữu permit.
7. `Semaphore` giới hạn số lần được nhận/chưa kết thúc trong logic này, không đo tốc độ bắt đầu theo giây. Fair semaphore tùy chọn có chi phí/semantics riêng, không tự đảm bảo công bằng toàn hệ thống.

**Giới hạn có chủ đích của ví dụ:** các future là nội bộ, không bị cancel giữa lúc đang đợi queue, và nhà sản xuất xử lý đầu vào hữu hạn. Với cancellation hoặc deadline phức tạp, phải thiết kế lại **quyền sở hữu permit** (phần 8). Không sao chép mẫu này thành một thư viện có `cancel()` tùy ý mà không xử lý đường task chưa bắt đầu.

## 6. Cách 3: Executor có queue giới hạn và rejection policy

Một chiến lược khác là **chặn admission** bằng cấu hình executor:

```java
ThreadPoolExecutor executor = new ThreadPoolExecutor(
        2, 2,
        0L, TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(16),
        new ThreadPoolExecutor.AbortPolicy()
);
```

Đây là snippet cần import các class tương ứng; resource owner phải shutdown executor. Cấu hình có tối đa hai worker và queue chứa tối đa 16 task. Khi worker và queue đều hết khả năng nhận thêm, `execute()` có thể bị từ chối theo rejection policy.

Các chính sách thường gặp:

| Policy | Khi pool bão hòa | Hệ quả cần nhớ |
| --- | --- | --- |
| `AbortPolicy` | Ném `RejectedExecutionException` | Caller biết đã từ chối và phải retry/báo quá tải đúng cách |
| `CallerRunsPolicy` | Nếu executor chưa shutdown, chạy task **trên caller thread** | Backpressure gián tiếp nhưng caller có thể bị chặn lâu; số worker không còn mô tả hết chỗ thực thi |
| `DiscardPolicy` | Bỏ task | Nếu caller không được thông báo, có thể mất công việc |
| `DiscardOldestPolicy` | Bỏ task cũ nhất đang chờ rồi thử lại | Cần chính sách rõ với task quan trọng và thời hạn |

**Cảnh báo riêng với `CompletableFuture.supplyAsync`:** nếu rejection handler **bỏ task nhưng không ném ngoại lệ**, một CompletableFuture được tạo ra có thể **không bao giờ hoàn tất**. Vì vậy đừng dùng `DiscardPolicy` hay các policy im lặng cho công việc cần kết quả mà không có giao thức hủy/timeout và chẩn đoán riêng.

`CallerRunsPolicy` làm tác vụ chạy ngay trên thread gửi, nên một supplier có thể chạy **đồng bộ trong chính lời gọi `supplyAsync`** khi pool bão hòa. Điều đó tạo backpressure nhưng có thể gây chậm producer hoặc deadlock nếu caller đang giữ lock mà task cần.

### Ví dụ Java 17+: chứng minh queue có giới hạn và rejection

Tạo file `BoundedQueueRejectionDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class BoundedQueueRejectionDemo {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy()
        );

        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger completed = new AtomicInteger();

        try {
            pool.execute(() -> {
                firstStarted.countDown();
                try {
                    release.await();
                    completed.incrementAndGet();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });

            firstStarted.await(); // Worker đang giữ slot thực thi.
            pool.execute(() -> completed.incrementAndGet()); // Queue có 1.
            boolean rejected = false;
            try {
                pool.execute(() -> completed.incrementAndGet());
            } catch (RejectedExecutionException expected) {
                rejected = true;
            }

            System.out.println("Third rejected: " + rejected);
        } finally {
            release.countDown();
            pool.shutdown();
        }

        if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
            pool.shutdownNow();
            throw new IllegalStateException("Pool did not stop");
        }
        System.out.println("Completed: " + completed.get());
    }
}
```

Chạy:

```bash
javac BoundedQueueRejectionDemo.java
java BoundedQueueRejectionDemo
```

Đầu ra trong điều kiện không có interrupt ngoài:

```text
Third rejected: true
Completed: 2
```

Vì task đầu đang đợi `release`, worker duy nhất chưa thể chạy task thứ hai; queue chỉ có một slot, nên task thứ ba không được nhận và `AbortPolicy` ném exception. Main mở gate trong `finally` để worker hoàn tất hai task đã được chấp nhận, rồi chờ pool terminated.

Ví dụ không cần `sleep()` để “ước lượng worker đã bận”. `CountDownLatch` đặt đúng mốc: worker đầu đã bắt đầu trước khi test submit task thứ hai.

**Giới hạn khác với Semaphore:** bounded queue có thể nhận **2 worker + 16 queued** tức tới 18 task trong cấu hình snippet, nhưng không tự chặn producer trước khi gọi submit nếu đang dùng `AbortPolicy`. Semaphore đặt **số in-flight tổng** ngay tại producer; bounded executor đặt **giới hạn admission và chính sách quá tải** ở executor. Có thể phối hợp hai cơ chế, nhưng không nên thêm nhiều lớp giới hạn mà không xác định ai sở hữu permit và việc bị từ chối được xử lý thế nào.

## 7. Vì sao semaphore bên trong supplier không đủ giới hạn lượng future?

Một anti-pattern:

```java
// Snippet minh họa VẤN ĐỀ về số task đã submit.
List<CompletableFuture<Result>> futures = items.stream()
        .map(item -> CompletableFuture.supplyAsync(() -> {
            permits.acquireUninterruptibly();
            try {
                return process(item);
            } finally {
                permits.release();
            }
        }, executor))
        .toList();
```

Đây không phải file độc lập, vì `Result`, `items`, `process`, `permits`, `executor` chưa được khai báo.

Dù chỉ có 5 permit, vòng stream vẫn có thể **tạo toàn bộ tương lai** và xếp tất cả supplier vào executor. Một số worker bị chiếm giữ **chỉ để chờ permit**, làm giảm hiệu quả worker. Với pool nhỏ, chính worker giữ permit và task đang chờ permit có thể gây áp lực/starvation nếu có phụ thuộc lẫn nhau.

**Giải pháp tùy yêu cầu:** lấy permit **trước** khi tạo/submit tác vụ (như phần 5), gửi theo window (phần 4) hoặc dùng executor admission có giới hạn (phần 6). Nếu là **thao tác I/O bất đồng bộ không chiếm worker**, đặt permit ở lúc **bắt đầu I/O thật**, release khi **I/O thật kết thúc**, chứ không chỉ khi future wrapper được xem là completed do timeout.

## 8. Cancellation: một lỗi tinh vi khi dùng permit với CompletableFuture

Mẫu `submitBounded` ở phần 5 cố tình đơn giản, nhưng **không phải mẫu cancellation-aware đầy đủ**. Điều này đặc biệt quan trọng khi hàng nghìn future được tạo và bên ngoài có quyền gọi `cancel(...)`.

### Trường hợp A: cancel future trước khi supplier được chạy

`CompletableFuture.cancel(...)` hoàn tất future với trạng thái cancelled, nhưng **không đảm bảo hủy tác vụ đang queue hoặc interrupt worker** như một số cách dùng `FutureTask`.

Với một future từ `CompletableFuture.supplyAsync`, nếu nó bị cancel **trước khi supplier bắt đầu**, executor vẫn có thể lấy runnable nội bộ nhưng nhận thấy future đã completed và **không gọi supplier**. Khi ấy `finally { permits.release(); }` **bên trong supplier không bao giờ chạy** → permit có thể **bị giữ mãi**.

### Trường hợp B: release permit ngay ở `whenComplete` của future bị cancel

Nếu gắn `future.whenComplete((value, error) -> permits.release())`, cancellation có thể làm callback chạy **ngay khi trạng thái future chuyển sang cancelled**, dù supplier thực tế **vẫn đang chạy và dùng resource**. Khi đó producer nhận permit quá sớm và khởi phát công việc mới, khiến **concurrency thực tế vượt giới hạn**.

Vì vậy:

- **Trạng thái CompletableFuture hoàn tất** có thể khác với **tác vụ thực sự đã ngừng dùng resource**.
- `cancel(true)` của `CompletableFuture` không có nghĩa worker chắc chắn bị interrupt; tham số `mayInterruptIfRunning` không điều khiển xử lý của implementation `CompletableFuture` theo kiểu `FutureTask`.
- `orTimeout(...)` / `completeOnTimeout(...)` thay đổi cách future hoàn tất, **không tự dừng I/O/CPU đang chạy**. Chúng có thể khiến `whenComplete` báo hoàn tất sớm hơn hoạt động vật lý.
- Muốn cancellation-aware admission chính xác, cần quản lý **trạng thái task thật** (queued/running/finished/cancelled), quyền sở hữu permit và cơ chế trả permit **chính xác một lần**, hoặc dùng executor/queue/cancellation policy chuyên biệt với hợp đồng rõ.

**Không khắc phục một cách máy móc bằng cách vừa release trong supplier finally vừa release ở khi future completed**: double release tăng số permit, phá vỡ giới hạn concurrency.

### Java 17+: timeout của future không phải kết thúc worker

Tạo file `FutureTimeoutVsWorkDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class FutureTimeoutVsWorkDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch workerFinished = new CountDownLatch(1);
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            CompletableFuture<String> future =
                    CompletableFuture.supplyAsync(() -> {
                        started.countDown();
                        try {
                            release.await();
                            return "done";
                        } catch (InterruptedException e) {
                            Thread.currentThread().interrupt();
                            return "interrupted";
                        } finally {
                            workerFinished.countDown();
                        }
                    }, executor);

            started.await();
            boolean timeoutSeen = false;
            try {
                future.orTimeout(20, TimeUnit.MILLISECONDS).join();
            } catch (CompletionException e) {
                if (!(e.getCause() instanceof TimeoutException)) {
                    throw e;
                }
                timeoutSeen = true;
            }

            System.out.println("Future timed out: " + timeoutSeen);
            System.out.println("Worker done before release: "
                    + (workerFinished.getCount() == 0L));

            release.countDown();
            if (!workerFinished.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Worker did not finish");
            }
            System.out.println("Worker done after release: true");
        } finally {
            release.countDown();
            executor.shutdownNow();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Executor did not terminate");
            }
        }
    }
}
```

Biên dịch/chạy:

```bash
javac FutureTimeoutVsWorkDemo.java
java FutureTimeoutVsWorkDemo
```

Đầu ra bình thường:

```text
Future timed out: true
Worker done before release: false
Worker done after release: true
```

**Giải thích:** worker đã báo `started` và chờ latch `release`. Future được phép hoàn tất exceptional với `TimeoutException` sau 20 ms, nhưng worker **vẫn đang chờ latch** vì thread main chưa mở cổng. Do đó `workerFinished` chưa về 0, mặc dù future đã timeout. Chỉ sau khi main mở gate, worker mới kết thúc và `workerFinished` xác nhận.

Tình huống này chứng minh: **chỉ nhìn vào future đã timeout/cancelled là không đủ để nhả slot của thao tác vật lý**, đặc biệt với HTTP/database/CPU task có side effect.

## 9. Hạn chế concurrency khi gọi I/O bất đồng bộ thực sự

Ví dụ `HttpClient.sendAsync` (Java 11+) có thể gửi request và trả một `CompletableFuture<HttpResponse<T>>` mà không chiếm một worker ứng dụng suốt thời gian chờ.

Với kiểu này, mục tiêu thường là **tối đa N request thực sự đang bay trên mạng**, không phải tối đa N supplier đang chạy trên thread pool.

Mô hình ý tưởng:

```text
Chưa gửi request
      |
      v
Xin quyền bắt đầu external operation
      |
      +-- chưa có slot: giữ item ở hàng chờ bounded
      |
      v
Bắt đầu I/O bất đồng bộ
      |
      v
I/O hoàn tất thật (success/failure/cleanup)
      |
      v
Ghi nhận outcome, trả slot, nạp item tiếp theo
```

**Lưu ý quan trọng:** callback của `CompletableFuture` có thể chạy trên thread hoàn tất stage hoặc thread đăng ký callback nếu stage đã hoàn tất. Đừng dùng callback để chạy việc blocking nặng trên thread I/O/event loop mà không kiểm soát executor.

Một pattern thông dụng là **rolling window**: giữ tối đa K operation thật đang hoạt động; mỗi khi một operation kết thúc, khởi phát tiếp một item chưa gửi. Cần queue đầu vào có giới hạn hoặc streaming iterator, xử lý error, timeout, cancellation và giới hạn tài nguyên mạng theo đúng API.

**Không dùng `supplyAsync(() -> httpClient.sendAsync(...))` rồi giải phóng permit khi supplier trả về**: supplier chỉ trả về **một future của request**, có thể kết thúc gần như tức thì trong khi HTTP request vẫn đang hoạt động. Nếu muốn biểu diễn kết quả ngoài, phải `thenCompose`/quản lý stage phản ánh **sự hoàn thành request thật**. Tuy nhiên, việc timeout/cancel stage wrapper vẫn đòi hỏi chính sách permit-ownership như phần 8.

### Completion callback và accounting

Với một thao tác không bị hoàn tất sớm giả tạo, callback `whenComplete` có thể tiện để ghi nhận lỗi và giải phóng slot sau khi công việc **thực sự** kết thúc. Nhưng phải xác định rõ **future nào là nguồn chân lý cho hoạt động vật lý**, ai có quyền cancel nó, và cơ chế hủy có hoàn tất cleanup chưa. Không được mặc nhiên gắn release vào một wrapper bị `orTimeout` thay đổi trạng thái rồi coi thao tác nền đã dừng.

## 10. Xử lý lỗi khi dùng `allOf` và thu thập kết quả

`CompletableFuture.allOf(f1, f2, ...)` trả một `CompletableFuture<Void>` hoàn tất khi các input future đã hoàn tất, nhưng:

- Nó không trả danh sách kết quả typed.
- Nếu ít nhất một future thất bại, future tổng **hoàn tất exceptional**; `join()` có thể ném `CompletionException`.
- Một input future hoàn tất bình thường không có nghĩa output nghiệp vụ đúng nếu code đã biến lỗi thành default value.
- `allOf` **không tự cancel** các công việc khác khi một future thất bại.
- Nó không giới hạn concurrency hay số future được giữ trong bộ nhớ.
- `CompletableFuture.join()` ném unchecked `CompletionException`/`CancellationException` theo trạng thái; `get()` dùng checked `ExecutionException`/`InterruptedException`.

### Thu thập outcome mà không để một lỗi che tất cả

```java
// Snippet: futures là List<CompletableFuture<String>> đã tạo.
List<CompletableFuture<String>> safe = futures.stream()
        .map(f -> f.handle((value, error) ->
                error == null ? "OK: " + value
                              : "FAIL: " + error.getClass().getSimpleName()))
        .toList();

CompletableFuture.allOf(
        safe.toArray(new CompletableFuture<?>[0])
).join();

for (CompletableFuture<String> future : safe) {
    System.out.println(future.join());
}
```

Đây là **snippet**: `futures` và imports chưa có. Mục đích là **chuyển mỗi outcome thành một giá trị** để có thể đọc đủ thành công/thất bại của từng item. `handle` ở đây chỉ phân biệt lỗi theo class để minh họa; production cần log nguyên nhân, giữ index/input ID và quyết định có retry hay không.

Nếu một task bị timeout/cancel, vẫn phải tách **trạng thái future** và **trạng thái xử lý thực tế** trước khi cấp lại slot.

## 11. Backpressure: ai phải chờ và chờ ở đâu?

Giới hạn concurrency chỉ có ý nghĩa thực tế khi xác định **ai chịu áp lực quá tải**.

**Các lựa chọn thường gặp:**

1. **Block producer:** lấy permit trước khi submit. Đơn giản với pipeline đồng bộ nhưng có thể chặn thread gọi (không phù hợp event loop).
2. **Reject sớm:** bounded executor và `AbortPolicy`. Caller phải có hợp đồng “không nhận thêm”, retry hoặc báo lỗi.
3. **Chia lô:** chỉ tạo K future, đợi xong cả lô. Đơn giản nhưng có thể lãng phí slot vì một task chậm.
4. **Rolling replenishment:** giữ K operation, khi một cái hoàn tất thì submit tiếp. Tận dụng slot tốt hơn, cần quản lý trạng thái và lỗi phức tạp hơn.
5. **Queue bounded upstream:** giữ tối đa M item đợi admission; khi đầy, chặn, drop có chính sách, hoặc từ chối. Tránh tạo vô hạn object đang chờ.
6. **Điều chỉnh lưu lượng:** ngoài concurrency limit, áp thêm rate limit khi downstream có quota theo giây/phút.

Không có con số K tối ưu cho mọi ứng dụng. Nó phụ thuộc thời gian giữ tài nguyên, latency mục tiêu, RAM, CPU, giới hạn kết nối, quota downstream và khả năng retry. Một K quá thấp có thể làm throughput thấp; K quá cao có thể tăng timeout, tail latency và tỷ lệ lỗi khi quá tải.

### Ước lượng bằng thời gian hoàn tất

Với hệ thống ở trạng thái ổn định, có một quan hệ định hướng giữa **số request đang xử lý**, **throughput** và **thời gian ở trong hệ thống** (Little's Law):

```text
Số công việc trung bình đang ở trong hệ thống
  ≈ throughput trung bình × latency trung bình
```

Đây là **ước lượng phân tích** ở điều kiện phù hợp, không phải công thức chọn semaphore permit chính xác cho mọi workload. Queueing, variance latency và giới hạn tài nguyên cần được đo dưới tải thật.

## 12. Interruption và deadline khi producer chờ permit

`Semaphore.acquire()` là thao tác **interruptible**. Nếu producer bị interrupt trước khi có permit, không có quyền release. Nếu API cần giới hạn thời gian đợi **admission**, có thể dùng:

```java
// Snippet: permits là Semaphore đã khai báo.
boolean admitted = permits.tryAcquire(
        200, TimeUnit.MILLISECONDS);
if (!admitted) {
    // Trả lời quá tải hoặc thử lại theo chính sách nghiệp vụ.
    return;
}
try {
    // Khởi phát operation đã được cấp slot.
} finally {
    // Chỉ release khi operation thực sự đã kết thúc,
    // không phải khi một wrapper timeout nhưng I/O vẫn chạy.
}
```

Snippet này **chưa phải chương trình độc lập**: phương thức bao quanh và operation chưa khai báo; phải định nghĩa chính xác ai sở hữu permit và khi nào release.

Nếu workflow có một deadline tổng, không dùng `tryAcquire(200ms)` rồi `future.get(200ms)` để suy ra tổng chỉ 200 ms: bạn đã cấp hai ngân sách riêng. Dùng `System.nanoTime()` để tính **thời gian còn lại** cho từng bước, và phân biệt deadline của caller với termination của tác vụ.

**Không nuốt `InterruptedException`** rồi tiếp tục tạo hàng nghìn future; truyền tiếp hoặc phục hồi cờ `Thread.currentThread().interrupt()` khi không thể truyền. Với công việc đã được submit, cần chính sách cleanup/cancellation; interruption của producer không tự undo task đã được gửi trước đó.

## 13. Những lỗi thường gặp

1. **“`CompletableFuture.allOf` giới hạn số future chạy.”** Sai: nó chỉ tổng hợp trạng thái hoàn tất.
2. **“Fixed thread pool 8 worker nghĩa chỉ có 8 task/future tồn tại.”** Sai: queue có thể chứa rất nhiều task.
3. **“Semaphore bên trong mỗi supplier ngăn tạo nhiều future.”** Sai: các future và queued task vẫn có thể được tạo hết.
4. **“`supplyAsync` luôn chạy trên một thread riêng.”** Sai: executor quyết định; có thể dùng lại worker hoặc policy chạy caller.
5. **“Cần giới hạn concurrency 5 là đủ hạn chế 5 request/giây.”** Sai: concurrency và rate khác nhau.
6. **“`orTimeout` sẽ interrupt mọi task nền.”** Sai: hoàn tất trạng thái future không đảm bảo dừng tác vụ thật.
7. **“`cancel(true)` của CompletableFuture luôn interrupt worker.”** Sai: `mayInterruptIfRunning` không có tác dụng đó theo implementation.
8. **“Supplier bị cancel trước khi chạy vẫn vào finally.”** Sai: supplier có thể không bao giờ được gọi, gây leak nếu nó là nơi duy nhất release permit.
9. **“Gắn `whenComplete` release permit là chắc chắn đúng.”** Không nếu future có thể completed/cancelled trước khi hoạt động vật lý kết thúc.
10. **“Release ở cả callback và finally để tránh leak.”** Sai: có thể double release, phá giới hạn.
11. **“Gọi `allOf.join` xong là tất cả business outcome thành công.”** Sai: lỗi phải được xử lý; timeout wrapper còn có thể kết thúc sớm.
12. **“Queue unbounded không đáng lo vì ít worker.”** Sai: backlog và memory vẫn tăng.
13. **“DiscardPolicy với supplyAsync an toàn vì future sẽ tự hiểu rejected.”** Sai: future có thể không hoàn tất.
14. **“CallerRunsPolicy luôn không gây tác dụng phụ cho caller.”** Sai: nó có thể chạy toàn bộ supplier trên thread gọi.
15. **“Chia batch luôn tối ưu throughput.”** Sai: một task chậm có thể chặn chuyển cả lô.
16. **“`Semaphore.availablePermits()` là một reservation atomic.”** Sai: đó là snapshot; dùng `acquire/tryAcquire` để lấy quyền.
17. **“Timeout admission chứng minh request ngoại vi đã dừng.”** Sai: chỉ nói không lấy được slot trong thời hạn.
18. **“Tăng K sẽ luôn tăng tốc.”** Sai: khi downstream bão hòa, tăng K có thể làm latency/lỗi xấu đi.
19. **“Một future hoàn tất nghĩa resource nó đại diện chắc chắn đã được đóng.”** Không khi future chỉ phản ánh tín hiệu wrapper hoặc task đã cancel.
20. **“Không cần shutdown executor tự tạo khi đủ future completed.”** Sai: owner vẫn phải quản lý vòng đời executor.

## 14. Checklist thiết kế bulk fan-out với CompletableFuture

1. **Xác định resource cần bảo vệ:** worker CPU, kết nối DB, HTTP request chưa trả lời, task được nhận hay future đang giữ RAM?
2. **Chọn đúng giới hạn:** worker count, số in-flight thực sự, queue capacity, tốc độ khởi phát và memory budget có thể là các ngưỡng riêng.
3. **Không tạo mọi future cùng lúc** nếu khối lượng đầu vào lớn; chọn window, rolling admission hoặc stream.
4. **Giữ permit trước submit** nếu mục tiêu là giới hạn số task đã được nhận. Không lấy sau khi đã tạo vô hạn future.
5. **Xác định ai sở hữu permit** qua các giai đoạn queued/running/finished/cancelled; chỉ release một lần.
6. **Kiểm tra submission failure:** `RejectedExecutionException` phải hoàn trả permit khi task chưa được nhận.
7. **Không release trên timeout wrapper** nếu hoạt động vật lý vẫn đang chạy.
8. **Nếu có cancellation**, phải thiết kế protocol riêng cho task chưa bắt đầu và task đang chạy; không chỉ gắn `whenComplete` tùy tiện.
9. **Xử lý từng outcome:** kết quả, exception, cancellation, timeout, retry; `allOf` không thay chính sách lỗi.
10. **Có timeout và deadline rõ ràng:** giới hạn cả admission và operation khi được API hỗ trợ; không reset ngân sách cho từng bước.
11. **Đo dưới tải thật:** in-flight, queue length, rejection, downstream errors, p95/p99 latency, memory và throughput.
12. **Quản lý executor lifecycle:** shutdown pool do mình sở hữu và theo dõi task chưa kết thúc; không đóng common pool.
13. **Tránh block event loop:** `Semaphore.acquire()` chặn thread caller; nếu caller là luồng sự kiện, cần cơ chế admission bất đồng bộ.
14. **Làm rõ tính chất retry/idempotency:** timeout không rollback side effect; chạy lại có thể gây trùng công việc.
15. **Viết test có kiểm soát:** dùng latch tạo worker đang giữ permit/queue, kiểm tra giới hạn mà không phải đoán bằng sleep.
16. **Chọn cách đơn giản nhất đáp ứng hợp đồng:** batch nếu nhỏ và độc lập; producer gating nếu có thể chờ; bounded executor nếu muốn reject; rolling async window khi cần sử dụng slot hiệu quả mà không block caller.

## 15. Tài liệu JDK tham khảo

- [CompletableFuture — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Semaphore — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html)
- [ThreadPoolExecutor — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Executors — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executors.html)
- [CountDownLatch — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)

**Kết luận:** tạo hàng loạt `CompletableFuture` dễ dẫn tới **fan-out không kiểm soát** dù executor chỉ có ít worker. `allOf` giúp đợi kết quả, **không giới hạn concurrency**. Muốn giới hạn số công việc đã nhận, hãy dùng batch/window, xin permit **trước khi submit**, hoặc dùng bounded executor/rejection đúng hợp đồng. Với I/O bất đồng bộ và cancellation, phải quản lý slot theo **thời điểm thao tác thật bắt đầu/kết thúc**, không chỉ theo trạng thái Future; nếu không có thể gây permit leak hoặc cấp permit sớm làm vượt giới hạn.