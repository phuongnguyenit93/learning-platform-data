# Bulkhead: giới hạn tải theo loại tài nguyên trong Java

## 1. Mục tiêu và phạm vi

Bulkhead là một mẫu thiết kế bảo vệ hệ thống đồng thời: **phân chia sức chứa cho các nhóm công việc** để một nhóm đang chậm hoặc quá tải không chiếm hết tài nguyên cần cho nhóm khác. Sau bài này, bạn có thể nhận diện tranh chấp thread/connection/queue, chọn cơ chế cô lập thích hợp, cài đặt giới hạn trong Java, xử lý quá tải và kiểm thử khả năng cô lập.

Bài học xét **Java concurrency nói chung**, với API `java.util.concurrent` và tài nguyên JVM; không yêu cầu framework hoặc cơ chế cấu hình của Spring.

## 2. Tại sao cần bulkhead?

Một ứng dụng xử lý ba luồng công việc: gọi dịch vụ thanh toán chậm qua mạng, truy vấn cơ sở dữ liệu và xử lý dữ liệu trong bộ nhớ. Nếu tất cả dùng chung 20 worker, 20 lời gọi thanh toán bị kẹt sẽ khiến hai luồng còn lại xếp hàng dù chúng vẫn khỏe. Khi request mới đến nhanh hơn tốc độ hoàn tất, hàng đợi, độ trễ và bộ nhớ sử dụng có thể tăng liên tục.

Đó là **cascading failure qua tài nguyên chung**: lỗi của một dependency lan sang tính năng khác do thread, kết nối hoặc queue bị giữ hết. Bulkhead mượn ý tưởng các khoang kín trên tàu: một khoang bị ngập không làm ngập toàn tàu. Mỗi nhóm công việc có giới hạn riêng; khi nhóm A bão hòa, tải mới của A bị xếp hàng trong giới hạn hoặc bị từ chối, còn B có khả năng tiếp tục phục vụ.

```text
Không cô lập:
    Thanh toán ─┐
    Truy vấn DB ├──> Executor chung (20 worker) ──> nghẽn mọi loại việc
    Tính toán ──┘

Có bulkhead:
    Thanh toán ──> Pool A (8 worker, queue 16) ──> API thanh toán
    Truy vấn DB ─> Pool B (6 worker, queue 12) ──> Database
    Tính toán ───> Pool C (4 worker, queue 8) ────> CPU
```

Những con số trên chỉ là minh họa, không phải cấu hình mặc định. Cần kiểm tra giới hạn tài nguyên thực tế trước khi chọn kích thước.

## 3. Chia theo tài nguyên thực sự bị tranh chấp

| Tài nguyên / nhóm tải | Cơ chế phù hợp | Ngân sách cần quan sát |
| --- | --- | --- |
| Platform thread cho tác vụ blocking | `ThreadPoolExecutor` riêng với queue hữu hạn | Worker đang chạy, việc đang chờ, rejection |
| Request đang gọi API/backend | `Semaphore` theo downstream | Số lời gọi in-flight, latency, timeout |
| JDBC/HTTP/socket connection | Connection pool hữu hạn; semaphore trước khi mượn connection nếu cần | Kết nối đang dùng, thời gian chờ, quota |
| Công việc CPU-bound | Executor theo năng lực CPU | CPU saturation, context switching |
| Bộ nhớ và buffer sự kiện | Bounded queue, giới hạn số phần tử hoặc byte | Queue depth, heap, backlog age |

Một tác vụ có thể đồng thời chiếm thread, connection và memory. Chia thành hai executor sẽ **không cô lập được** hai nhóm nếu cả hai vẫn tranh nhau cùng một JDBC pool quá nhỏ; cũng không làm tăng CPU vật lý. Chọn ranh giới theo **bottleneck quan sát được** và tính ngân sách của tài nguyên chung.

Bulkhead giới hạn **số hoạt động đồng thời**; rate limiter giới hạn **tốc độ khởi tạo** hoạt động theo thời gian. Ví dụ hai permit có thể xử lý hàng trăm request/giây nếu mỗi request kết thúc cực nhanh, hoặc chỉ vài request/giây khi downstream chậm. Có thể cần cả hai.

## 4. Hai kiểu bulkhead trong Java

### 4.1. Thread-pool bulkhead

Tạo executor riêng cho mỗi nhóm công việc cần cô lập, bao gồm **số worker tối đa, queue hữu hạn và chính sách khi đầy**. Tác vụ của A không thể chiếm worker hoặc slot chờ của B. Với `ThreadPoolExecutor`, `corePoolSize`, `maximumPoolSize` và `BlockingQueue` quyết định sức chứa; `RejectedExecutionHandler` xử lý yêu cầu mới khi không nhận thêm được.

Chú ý: `Executors.newFixedThreadPool(n)` dùng hàng đợi không giới hạn dung lượng theo cấu hình. Vì vậy nó có giới hạn worker nhưng **không có giới hạn backlog hữu hạn**; lượng việc đang đợi có thể tăng đến khi bộ nhớ trở thành vấn đề. Muốn fail-fast rõ ràng, tạo `ThreadPoolExecutor` với queue bounded như `ArrayBlockingQueue` và `AbortPolicy`.

Pool riêng có chi phí thread, heap và vận hành; tạo hàng chục pool kích thước quá lớn có thể làm hệ thống tệ hơn. Đồng thời quản lý vòng đời bằng `shutdown()`, `awaitTermination()` và `shutdownNow()` phù hợp.

### 4.2. Semaphore bulkhead

`Semaphore(k)` cho phép tối đa `k` hoạt động đồng thời giữ permit, rất phù hợp để chặn số lời gọi in-flight tới cùng một API hoặc cùng nhóm connection. Các caller có thể xuất phát từ executor khác nhau nhưng vẫn dùng một semaphore chia sẻ.

Semaphore **không cấp thread**, không tách scheduler, không tự dừng lời gọi đang chạy. Với caller blocking, `acquire()` không hạn thời gian có thể làm caller chờ vô hạn; thường nên dùng `tryAcquire(timeout)` rồi từ chối có kiểm soát. Nếu tất cả caller đều bị kẹt trong một executor chung, còn permit cũng không đảm bảo một tác vụ mới được lên lịch.

## 5. Ví dụ runnable Java 17+: cô lập pool chậm và pool khỏe

Ví dụ làm đầy pool `slow` có một worker và queue chứa một task. Task thứ ba bị từ chối; pool `fast` vẫn xử lý được. Latch kiểm soát thứ tự để kết quả có thể kiểm chứng.

Lưu đúng tên tệp **`BulkheadDemo.java`**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class BulkheadDemo {
    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor slow = newPool("slow");
        ThreadPoolExecutor fast = newPool("fast");
        CountDownLatch slowStarted = new CountDownLatch(1);
        CountDownLatch releaseSlow = new CountDownLatch(1);

        try {
            Future<String> running = slow.submit(() -> {
                slowStarted.countDown();
                releaseSlow.await();
                return "slow: running completed";
            });

            slowStarted.await(); // Worker slow đang chạy và giữ latch.
            Future<String> queued = slow.submit(() -> "slow: queued completed");

            try {
                slow.submit(() -> "will be rejected");
                throw new AssertionError("Expected rejection");
            } catch (RejectedExecutionException expected) {
                System.out.println("slow: rejected");
            }

            Future<String> healthy = fast.submit(() -> "fast: OK");
            System.out.println(healthy.get(2, TimeUnit.SECONDS));

            releaseSlow.countDown();
            System.out.println(running.get());
            System.out.println(queued.get());
        } finally {
            releaseSlow.countDown();
            slow.shutdownNow();
            fast.shutdownNow();
        }
    }

    private static ThreadPoolExecutor newPool(String name) {
        return new ThreadPoolExecutor(
                1, 1,
                0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                task -> new Thread(task, "bulkhead-" + name),
                new ThreadPoolExecutor.AbortPolicy()
        );
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac BulkheadDemo.java
java BulkheadDemo
```

Output:

```text
slow: rejected
fast: OK
slow: running completed
slow: queued completed
```

**Giải thích:** Sau `slowStarted.await()`, task đầu đã giữ worker của `slow` và đợi latch. Task thứ hai vào queue một chỗ. Task thứ ba vượt cả hai giới hạn nên `AbortPolicy` ném `RejectedExecutionException` ngay khi `submit()`. Trong lúc đó `fast` có worker riêng nên hoàn tất. Mở latch cho `slow` xử lý hai task cũ; `Future.get()` bảo đảm thứ tự in kết quả.

`shutdownNow()` trong demo đơn giản hóa việc dọn dẹp khi có exception. Nó cố gắng interrupt task, **không bảo đảm** mọi API blocking/I/O sẽ dừng tức thì. Trong hệ thống thực, ưu tiên lifecycle có thời hạn: `shutdown()`, đợi một khoảng hữu hạn, rồi cân nhắc `shutdownNow()` và quan sát task chưa dừng.

## 6. Ví dụ Semaphore: giới hạn hai lời gọi đồng thời

Đây là **lớp thành phần** dùng trong ứng dụng (không có `main()`; không chạy riêng bằng `java SemaphoreBulkhead`):

```java
import java.util.concurrent.Callable;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

final class SemaphoreBulkhead {
    private final Semaphore slots = new Semaphore(2);

    public <T> T execute(Callable<T> action) throws Exception {
        if (!slots.tryAcquire(100, TimeUnit.MILLISECONDS)) {
            throw new RejectedExecutionException("Bulkhead full");
        }
        try {
            return action.call();
        } finally {
            slots.release();
        }
    }
}
```

Giả sử `bulkhead` là một instance dùng chung, người gọi có thể dùng `bulkhead.execute(() -> remoteClient.fetch())`. **Không tạo instance mới cho từng request**, vì mỗi instance có hai permit riêng và sẽ không hạn chế tổng concurrency của dependency.

Lưu ý vòng đời permit:

- `tryAcquire` trả `false` khi hết thời gian đợi; nếu bị interrupt trước khi nhận permit, nó ném `InterruptedException`. Chỉ khi đã lấy thành công mới vào `try/finally` và `release()`.
- `finally` trả permit dù `action.call()` thành công hay ném exception. Không `release()` hai lần: điều đó làm tăng số permit ngoài mức thiết kế.
- Timeout **chờ permit** không phải timeout **thực thi lời gọi**. Phải thiết lập connection/read/request timeout tại client và deadline tổng nếu cần.
- Có thể yêu cầu công bằng tương đối với `new Semaphore(2, true)`, nhưng fairness không thay thế deadline và có thể làm giảm throughput.
- Nếu `action.call()` chỉ khởi chạy một `CompletableFuture` rồi trả về trước khi công việc hoàn thành, wrapper đồng bộ này thả permit **quá sớm**. Khi viết phiên bản asynchronous, giữ permit cho tới callback hoàn tất thật và bảo đảm release đúng một lần kể cả lỗi/hủy.

## 7. Đặt giới hạn: concurrency, queue và latency budget

Giới hạn phải lấy từ phép đo và khả năng chịu tải của downstream.

**Bước 1: Xác định ngân sách.** Nhóm nào giữ thread/connection/CPU, nhóm nào có thể chậm, nhóm nào cần ưu tiên? Bao nhiêu kết nối DB hoặc request đồng thời thật sự được downstream hỗ trợ? Phải tính cả các instance khác đang chia sẻ nó.

**Bước 2: Ước lượng concurrency.** Ở trạng thái ổn định, định luật Little đưa ra quan hệ `L = λ × W` (số việc trung bình trong hệ thống = thông lượng trung bình × thời gian trung bình trong hệ thống). Chẳng hạn 40 request/giây với thời gian chiếm tài nguyên trung bình 0,2 giây tương đương khoảng 8 hoạt động đang chiếm tài nguyên. Đây chỉ là điểm khởi đầu: phải xét burst, tail latency, retry, giới hạn connection/CPU, và bảo đảm `W` đo đúng phần đang giới hạn.

**Bước 3: Chọn worker/permit.** Với CPU-bound, thường cân nhắc gần mức CPU khả dụng rồi đo context switching và throughput. Với I/O blocking, có thể cần nhiều thread hơn CPU nhưng không vượt quá ngân sách dependency. Với virtual thread, giới hạn connection/remote call vẫn cần cơ chế độc lập.

**Bước 4: Chọn queue bounded theo thời gian chờ có thể chấp nhận.** Nếu 100 task/giây được gửi đến một pool đang chỉ xử lý được 20 task/giây, backlog tăng xấp xỉ 80 task/giây. Queue có 160 chỗ có thể đầy sau khoảng hai giây khi bắt đầu rỗng, nếu mức chênh lệch duy trì. Tăng queue chỉ trì hoãn rejection và có thể tăng độ trễ; không tự tăng throughput.

**Bước 5: Chọn phản ứng khi đầy.** Có thể từ chối ngay, cho đợi rất ngắn, trả kết quả dự phòng an toàn hoặc giảm ưu tiên. Với ứng dụng HTTP, mã như 429 hoặc 503 phụ thuộc hợp đồng API và nguyên nhân; không mặc định dùng cùng một mã cho tất cả. Producer phải biết dừng, giảm tốc hoặc xử lý lỗi thay vì retry ngay vô hạn.

**Bước 6: Load test và tinh chỉnh.** Đo p95/p99 latency, queue wait, rejection, CPU, connection wait và nhất là độ trễ của nhóm khỏe khi một nhóm bị cố ý làm chậm.

## 8. Timeout, hủy, retry và backpressure

Bulkhead chỉ có ích khi đường đi quá tải được thiết kế tường minh:

1. **Giới hạn thời gian chờ chỗ:** dùng `tryAcquire(timeout)` hoặc queue bounded với rejection; không để caller chờ vô hạn khi dependency ngừng phản hồi.
2. **Giới hạn thời gian thực thi:** đặt timeout tại socket, HTTP hoặc JDBC driver và truyền deadline từ request đầu vào khi phù hợp. `Future.get(timeout)` chỉ giới hạn thời gian **đợi future**, không tự dừng tác vụ bên trong. `cancel(true)` yêu cầu interrupt, còn việc dừng thực sự tùy task và thư viện.
3. **Không thả permit sớm khi cancel:** nếu task vẫn đang dùng connection sau khi caller ngừng đợi, permit phải phản ánh công việc thực sự còn đang chiếm tài nguyên. Tránh tạo thêm tải bằng việc cho request khác vào khi task cũ chưa dừng.
4. **Backpressure/load shedding:** chặn từ đầu hoặc từ chối nhanh khi nguồn lực bão hòa, thay vì dồn backlog lên heap.
5. **Retry có ngân sách:** chỉ retry các tình huống có thể phục hồi, giới hạn số lần, thời gian, dùng backoff/jitter thích hợp; retry tức thì lúc bulkhead đầy thường tạo retry storm.
6. **Fallback cũng phải có giới hạn:** không chuyển toàn bộ yêu cầu lỗi sang một pool chung khác rồi làm nghẽn nó.

`CallerRunsPolicy` chạy task bị đẩy ra trên thread gọi trong một số tình huống, giúp giảm tốc producer nhưng có thể lây độ trễ sang caller và phá mục tiêu cô lập. `DiscardPolicy` và `DiscardOldestPolicy` có thể làm thất lạc công việc; đặc biệt khi dùng `submit()`, future của task bị bỏ có thể không bao giờ hoàn thành. Chỉ dùng nếu semantics mất việc đã được thiết kế rõ. `AbortPolicy` cho phép phản ứng và ghi nhận rejection dễ thấy.

## 9. CompletableFuture, virtual thread và deadlock

`CompletableFuture.supplyAsync(supplier)` không truyền executor thường dùng `ForkJoinPool.commonPool()` theo cấu hình mặc định. Nếu cần cô lập blocking task theo dependency, dùng `CompletableFuture.supplyAsync(supplier, dedicatedExecutor)`; nhớ xử lý lỗi khi scheduling bị từ chối và quản lý vòng đời executor. Không coi việc tách future là đã tạo ra một bulkhead.

Java 21 hỗ trợ virtual thread với chi phí luồng thấp hơn cho nhiều thao tác blocking, nhưng virtual thread **không tạo thêm** kết nối DB, quota API hay CPU. Vẫn cần semaphore hoặc pool giới hạn theo tài nguyên thực, timeout và cancellation. Bài code chính dùng Java 17 để chạy được trên JDK 17+.

Nếu task phải lấy nhiều permit/lock, quy định thứ tự lấy nhất quán và tránh giữ một tài nguyên khan hiếm khi chờ tài nguyên khác quá lâu. Ví dụ các task A giữ permit DB rồi đợi permit API, còn task B làm ngược lại có thể tạo vòng chờ. Chỉ giữ tài nguyên trong đoạn mã thật sự cần nó.

## 10. So sánh với cơ chế bảo vệ khác

| Cơ chế | Giải quyết điều gì? | Ví dụ |
| --- | --- | --- |
| **Bulkhead** | Giới hạn số tác vụ của từng nhóm chiếm tài nguyên đồng thời | 8 in-flight cho backend A, sức chứa B tách riêng |
| **Rate limiter** | Giới hạn số yêu cầu được khởi tạo theo thời gian | 100 request/giây |
| **Circuit breaker** | Tạm không gọi backend đang thất bại liên tục theo chính sách | Mở mạch khi lỗi cao |
| **Timeout/deadline** | Giới hạn thời gian chờ/thực thi | Request deadline 500 ms |
| **Load shedding** | Bỏ bớt tải để giữ năng lực phục vụ | Từ chối việc ít ưu tiên khi bão hòa |

Các cơ chế bổ sung cho nhau. Bulkhead không tự phát hiện dependency đã hỏng, timeout không tự cấp quota theo nhóm, còn circuit breaker không tự phân vùng thread pool.

## 11. Quan sát và kiểm thử sự cô lập

Theo dõi metric **riêng từng bulkhead**, gồm active worker/permit, queue depth, thời gian chờ, rejection count/rate, timeout, cancellation, latency p95/p99 và thời gian giữ connection. Theo dõi thêm CPU, heap, GC, DB connection sử dụng chung: có thể hai bulkhead vẫn chia sẻ bottleneck vật lý.

Thử nghiệm có ý nghĩa:

- Giữ mọi slot của nhóm A bằng `CountDownLatch` hoặc server giả lập chậm; gửi thêm tải vượt queue A.
- Trong cùng thời gian, liên tục đưa công việc hợp lệ vào nhóm B. Kiểm tra B vẫn hoàn tất trong ngưỡng latency đã đặt.
- Kiểm tra A bị từ chối đúng chính sách, không rò permit khi exception/interruption/cancel, và có thể phục hồi sau khi hết nghẽn.
- Thử cả trường hợp downstream chậm, timeout, burst, retry, shutdown. Dùng latch để điều phối thay vì phụ thuộc `Thread.sleep()` và lịch scheduling ngẫu nhiên.

Nếu nhóm B cũng chậm nghiêm trọng, kiểm tra tài nguyên thật đang được chia sẻ: CPU, heap, DB pool, socket, log I/O, khóa, hoặc executor khác.

## 12. Các lỗi thường gặp

- Dùng một executor chung cho tất cả tác vụ blocking: dependency chậm chiếm hết worker.
- Dùng `newFixedThreadPool` và mặc định backlog được giới hạn: queue có thể tăng không kiểm soát.
- Tăng thread tùy ý mà không tăng sức chịu downstream: tăng chuyển ngữ cảnh và contention.
- Tạo `Semaphore` cho từng request: quota tổng không có tác dụng.
- `release()` trước khi async operation thật sự hoàn tất, hoặc release nhiều lần: phá giới hạn.
- Chỉ đặt timeout khi lấy permit nhưng quên timeout I/O sau khi lấy permit.
- Retry tức thì khi từ chối: dồn thêm tải vào phần đang bão hòa.
- Tách executor nhưng không đo DB connection/CPU/heap vẫn dùng chung.
- Không đo rejection và queue wait theo nhóm: không thể biết bulkhead có bảo vệ được hay không.
- Quên shutdown, xử lý interruption, hoặc giữ permit khi thao tác đã kết thúc.

## 13. Checklist áp dụng

1. Vẽ đường đi của từng nhóm và chỉ ra đúng tài nguyên tranh chấp.
2. Chọn pool riêng để tách worker/queue; chọn semaphore để giới hạn in-flight; giới hạn connection ở tầng sở hữu connection.
3. Đặt ngân sách concurrency, queue hữu hạn, timeout, cancellation và phản ứng quá tải.
4. Chia sẻ đúng instance giới hạn; bảo đảm trả permit/tài nguyên ở mọi đường thoát.
5. Làm nghẽn một nhóm có kiểm soát và kiểm chứng nhóm còn lại vẫn khỏe; giám sát rồi điều chỉnh.

**Cốt lõi:** bulkhead thu hẹp **phạm vi ảnh hưởng** của một phần hệ thống chậm hoặc quá tải. Thành công được đo bằng sức chứa hữu hạn, độ trễ có kiểm soát và khả năng phục vụ các nhóm không bị lỗi, không phải bằng việc cố tránh mọi rejection.
