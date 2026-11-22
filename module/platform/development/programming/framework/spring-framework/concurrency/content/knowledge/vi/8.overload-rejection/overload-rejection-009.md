# Thực nghiệm nhóm luồng và hàng đợi cùng đạt giới hạn

## 1. Mục tiêu: chủ động tạo trạng thái quá tải

Trong Spring Framework, `ThreadPoolTaskExecutor` thường chạy các công việc được nộp qua `@Async` hoặc các lời gọi `TaskExecutor.execute(...)`. Khi hệ thống nhiều yêu cầu, một pool có thể có **tất cả worker đang bận** và **hàng đợi chưa chạy cũng đầy**. Nếu lại có một task mới, executor không thể nhận thêm theo cách thông thường: nó áp dụng **chính sách từ chối** (*rejection policy*).

Bài thực nghiệm này không chỉ nói “executor có giới hạn” mà tạo một tình huống có thể lặp lại để kiểm chứng:

- Task nào chạy trên worker, task nào nằm trong queue?
- Khi `corePoolSize` đã đạt, task mới được xếp hàng hay mở thêm thread?
- Khi queue đã đầy, pool có tiếp tục tăng tới `maxPoolSize` không?
- Khi **cả pool và queue cùng đầy**, task tiếp theo được xử lý thế nào?
- Làm sao chứng minh hiện tượng này mà không phụ thuộc vào sự ngẫu nhiên của `Thread.sleep(...)`?
- Trong Spring, `TaskRejectedException` và `RejectedExecutionHandler` liên quan ra sao?

Trọng tâm là **quá tải và từ chối**. Không nhầm một task **chưa được nhận** với một task **đã chạy nhưng thất bại trong logic nghiệp vụ**.

## 2. Quy tắc nhận việc của ThreadPoolExecutor

`ThreadPoolTaskExecutor` của Spring bọc một `java.util.concurrent.ThreadPoolExecutor`. Khi dùng queue hữu hạn, ba thông số phải xem cùng lúc:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `corePoolSize` | Số thread lõi executor ưu tiên tạo khi nhận các task đầu tiên |
| `maxPoolSize` | Trần số worker thread của pool |
| `queueCapacity` | Số task chưa chạy có thể chờ trong queue |
| `RejectedExecutionHandler` | Cách xử lý khi không còn khả năng nhận thêm task, hoặc pool đã shutdown |

Quy tắc của `execute(Runnable)` trong `ThreadPoolExecutor`, giản lược theo cấu hình thông thường:

1. **Số worker hiện có chưa đạt core:** tạo worker để chạy task mới.
2. **Đã đạt core:** thử đưa task mới vào queue.
3. **Queue không nhận được task:** thử tạo worker khác nếu chưa chạm max.
4. **Queue đầy và worker đã đạt max:** gọi rejection handler.
5. **Pool đã shutdown:** cũng có thể reject, **dù không bão hòa**. Vì vậy phải phân biệt hai nguyên nhân rejection.

Điều dễ nhầm: **max thread không nhất thiết được dùng trước queue**. Nếu core=1, max=10 và queue còn chỗ, các task nộp sau worker đầu có thể tiếp tục vào queue; executor chỉ mở thêm worker vượt core khi queue không nhận được việc.

Một queue gần như vô hạn khiến pool thường không cần mở rộng vượt core. Ngược lại, `queueCapacity=0` trong `ThreadPoolTaskExecutor` tương ứng chiến lược chuyển giao trực tiếp (`SynchronousQueue`), chứ không phải queue có thể chứa vô hạn task.

## 3. Dự đoán với core=1, max=2, queue=1

Dùng cấu hình nhỏ để hiểu từng bước:

```text
corePoolSize  = 1
maxPoolSize   = 2
queueCapacity = 1
handler       = AbortPolicy
```

Giả sử task #1 và #3 được **giữ chưa hoàn thành**, nên hai worker mà chúng chiếm vẫn bận. Task #2 ngắn nhưng phải xếp hàng.

| Lần submit | Hành vi | Số worker bận | Số task chờ |
| --- | --- | ---: | ---: |
| #1 | Tạo worker lõi, chạy task #1 | 1 | 0 |
| #2 | Worker lõi bận, queue nhận task #2 | 1 | 1/1 |
| #3 | Queue đầy, tạo worker thứ hai chạy task #3 | 2/2 | 1/1 |
| #4 | Worker và queue đều đầy, `AbortPolicy` từ chối | 2/2 | 1/1 |

Sau khi giải phóng hai worker, task #2 mới được lấy ra khỏi queue và chạy. **Tổng cộng 3 task được chấp nhận**, còn task #4 không được chạy.

```text
Sau khi submit task #3, trước khi submit task #4:

+-----------------------+  +-----------------------+
| worker 1: task #1     |  | worker 2: task #3     |
| đang chờ latch        |  | đang chờ latch        |
+-----------------------+  +-----------------------+
         active workers = 2/2

queue (capacity 1): [ task #2 ]
         queue size = 1/1

submit task #4
  -> không còn suất worker
  -> không còn chỗ trong queue
  -> AbortPolicy: RejectedExecutionException
```

Đây là **ảnh chụp tại một thời điểm** chứ không phải trạng thái tồn tại mãi: nếu task #1 kết thúc trước khi nộp #4 thì worker có thể lấy task #2, queue mở chỗ và task #4 không nhất thiết bị từ chối. Vì vậy phải tạo một thí nghiệm có kiểm soát.

## 4. Java 17 standalone: tái hiện rejection với CountDownLatch

Ví dụ sử dụng duy nhất thư viện chuẩn JDK 17. Nó không đòi hỏi Spring, Maven hoặc server. Các latch giúp xác nhận hai task thực sự đang chạy rồi **giữ chúng tại điểm chặn** cho tới sau lần submit cần thử.

Tạo tệp **`PoolQueueLimitDemo.java`**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class PoolQueueLimitDemo {
    private static void awaitOrFail(CountDownLatch latch, String stage)
            throws InterruptedException {
        if (!latch.await(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Timeout at " + stage);
        }
    }

    public static void main(String[] args) throws Exception {
        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch bothStarted = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger completed = new AtomicInteger();

        Runnable heldTask = () -> {
            firstStarted.countDown();
            bothStarted.countDown();
            try {
                release.await();
                completed.incrementAndGet();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        };
        Runnable shortTask = () -> {
            completed.incrementAndGet();
        };

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1,                             // corePoolSize
                2,                             // maxPoolSize
                30, TimeUnit.SECONDS,          // keepAlive ngoài core
                new ArrayBlockingQueue<>(1),   // queueCapacity = 1
                new ThreadPoolExecutor.AbortPolicy()
        );

        try {
            // Task #1: tạo worker lõi và giữ nó chưa hoàn thành.
            pool.execute(heldTask);
            awaitOrFail(firstStarted, "first started");

            // Task #2: worker lõi bận nên queue nhận 1 task.
            pool.execute(shortTask);

            // Task #3: queue đã đầy, pool phải tạo worker thứ hai.
            pool.execute(heldTask);
            awaitOrFail(bothStarted, "both started");

            // Cả hai worker còn chờ release, nên task #2 vẫn ở queue.
            int active = pool.getActiveCount();
            int queued = pool.getQueue().size();
            if (active != 2 || queued != 1) {
                throw new IllegalStateException(
                        "Unexpected state: " + active + "/" + queued);
            }
            System.out.println("active=" + active + ", queued=" + queued);

            boolean fourthRejected = false;
            try {
                // Task #4: max=2 và queue=1 đều đã hết chỗ.
                pool.execute(shortTask);
            } catch (RejectedExecutionException ex) {
                fourthRejected = true;
            }
            System.out.println("fourthRejected=" + fourthRejected);
        } finally {
            // Luôn trả quyền chạy cho worker, kể cả test thất bại.
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
                throw new IllegalStateException("Pool did not terminate");
            }
        }

        System.out.println("completed=" + completed.get());
    }
}
```

Chạy trong thư mục có tệp nguồn:

```bash
javac PoolQueueLimitDemo.java
java PoolQueueLimitDemo
```

**Standard output khi chương trình hoàn tất bình thường:**

```text
active=2, queued=1
fourthRejected=true
completed=3
```

### Tại sao kết quả ổn định?

- Main không nộp task #2 cho tới khi `firstStarted` xác nhận task #1 đã chạy. Task #1 còn đợi `release` nên worker thứ nhất chưa thể lấy task #2.
- Khi nộp task #2, hàng đợi 1 chỗ được lấp đầy. Nộp task #3 buộc pool tạo worker thứ hai, vì max còn cho phép.
- Main đợi `bothStarted` để biết **cả hai worker đã bắt đầu**. Cả hai đang đợi cùng `release`, nên trước khi mở latch, active giữ ở 2 và queue giữ ở 1.
- Nộp task #4 lúc đó chắc chắn đi qua nhánh rejection của `AbortPolicy`. Exception được ném trong **thread submit** (main) và bị bắt ở đó, không phải bên trong task #4.
- `finally` mở latch, hai held task kết thúc, task #2 đang chờ được worker xử lý. `awaitTermination(...)` bảo đảm ba task đã hoàn tất trước khi in `completed=3`.
- Task #4 chưa được chấp nhận nên không được tính vào `completed`.

Timeout 10 giây dùng để phát hiện môi trường thực thi quá chậm/bị treo, không phải timeout nghiệp vụ của executor. Nếu test timeout, nó báo lỗi thay vì giả vờ đạt kết quả. Trong đường chạy bình thường ở trên, dòng stdout xác định không phụ thuộc thứ tự worker.

### Vì sao chỉ dùng sleep là không đủ?

Ví dụ kém tin cậy nếu người viết chỉ cho mỗi task ngủ vài mili-giây rồi gửi bốn task liên tiếp: task đầu có thể kết thúc trước lần nộp #4. Khi đó pool có chỗ trống và không reject, dẫn tới kết quả chạy lần được lần không. Latch hoặc barrier phải dùng để **giữ tình huống đầy**, không chỉ tạo chậm trễ ước lượng.

## 5. Cấu hình cùng kịch bản trong Spring ThreadPoolTaskExecutor

`ThreadPoolTaskExecutor` là adapter/lớp cấu hình tiện dụng của Spring cho JDK thread pool. Đoạn dưới đây là **các class tích hợp vào ứng dụng Spring Framework/Spring Boot**, không phải chương trình `javac` chỉ dùng JDK. Chúng cần Spring context, scheduling và cấu hình application phù hợp.

**`AsyncConfiguration.java`**:

```java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncConfiguration {

    @Bean("boundedExecutor")
    public ThreadPoolTaskExecutor boundedExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(1);
        executor.setThreadNamePrefix("bounded-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}
```

Spring sẽ khởi tạo/đóng executor bean theo lifecycle. Ví dụ một service dùng đúng bean đó:

**`JobService.java`**:

```java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class JobService {

    @Async("boundedExecutor")
    public CompletableFuture<String> process(String id) {
        // Đây là công việc mẫu; thay bằng xử lý thực tế khi tích hợp.
        String result = "processed:" + id;
        return CompletableFuture.completedFuture(result);
    }
}
```

**Lưu ý khi chạy thực tế:**

1. `@EnableAsync` bật cơ chế gọi phương thức bất đồng bộ. `@Async("boundedExecutor")` chọn đúng executor, tránh nhầm với executor auto-configuration khác của Spring Boot.
2. Phải gọi `process(...)` **qua Spring-managed proxy**, ví dụ từ bean khác đã inject `JobService`. Tự gọi `this.process(...)` trong cùng bean ở proxy mode thường bỏ qua `@Async`.
3. Phương thức xử lý mẫu chạy rất nhanh, nên gửi bốn lời gọi liên tiếp **không bảo đảm** pool bão hòa. Để kiểm thử ở tầng Spring, cần giữ task bằng latch/dependency giả tương tự mục 4.
4. Với `ThreadPoolTaskExecutor`, Spring thường báo lỗi không nhận được task bằng `org.springframework.core.task.TaskRejectedException`, kế thừa `RejectedExecutionException`. Đây là lỗi **submit** có thể đi ra ngay ở lời gọi `@Async`, trước khi caller nhận `CompletableFuture`.
5. Nếu task đã được chấp nhận rồi gặp lỗi, caller quan sát qua Future/callback của công việc đã nhận; đó **không** phải rejection.
6. Nếu dùng `@Async void`, lỗi thực thi bên trong không có Future cho caller theo dõi và cần cấu hình cơ chế xử lý lỗi tương ứng.

Ví dụ **snippet tại biên caller**, với biến `jobService` đã được inject:

```java
try {
    CompletableFuture<String> future = jobService.process("A-100");
    future.whenComplete((value, error) -> {
        if (error != null) {
            // Task được nhận nhưng đã gặp lỗi lúc thực thi.
        }
    });
} catch (org.springframework.core.task.TaskRejectedException ex) {
    // Executor không nhận task: trả lỗi quá tải hoặc lưu/retry công việc.
}
```

Không nên catch rejection rồi im lặng bỏ qua việc nghiệp vụ quan trọng. Với công việc phải chạy ngay cả sau restart, cần hệ queue/job store bền vững và cơ chế idempotency, không chỉ executor queue ở RAM.

## 6. Rejection trong Java và Spring: bốn chính sách quan trọng

| Handler | Khi pool/queue đầy | Cần chú ý |
| --- | --- | --- |
| `AbortPolicy` | Ném `RejectedExecutionException`; Spring wrapper thường trả `TaskRejectedException` | Caller biết task chưa được nhận, phải xử lý |
| `CallerRunsPolicy` | Caller tự chạy task (nếu executor chưa shutdown) | Không reject kiểu exception, nhưng **chặn caller**; task chạy ngoài worker pool |
| `DiscardPolicy` | Bỏ task âm thầm | Dễ mất việc; Future có thể không hoàn thành như người đợi mong đợi |
| `DiscardOldestPolicy` | Bỏ task cũ ở đầu queue rồi thử nộp lại | Có thể mất việc cũ, sai thứ tự, cần xem kỹ semantics retry |

**Cảnh báo với CallerRunsPolicy:** nếu HTTP request thread gọi `execute(...)`, khi pool bão hòa request thread có thể tự chạy công việc chậm. Đây là một kiểu backpressure nhưng có thể làm độ trễ request tăng mạnh. Nếu caller là event-loop hoặc công việc nested phụ thuộc latch do chính caller mở, có thể gặp tình huống chặn hoặc deadlock.

Nếu thay `AbortPolicy` trong ví dụ Java bằng `CallerRunsPolicy`, task #4 sẽ chạy trong main (vì `shortTask` không bị chặn), nên **stdout phải thay đổi**. Không thể giữ `fourthRejected=true` trong kỳ vọng. Với DiscardPolicy, task #4 có thể bị bỏ mà không ném exception; phải đếm task thực thi để phát hiện mất việc.

Đừng diễn giải “không có exception” là “đã được nhận và xử lý thành công”.

## 7. Thay đổi tham số để suy luận kết quả

Muốn làm thực nghiệm có giá trị, hãy **dự đoán trạng thái trước khi chạy**, sau đó sửa đúng một thông số và kiểm tra. Giữ các worker ở latch để queue chưa được rút.

| Cấu hình | Thứ tự nộp việc khi worker giữ chỗ | Task đầu tiên bị AbortPolicy reject |
| --- | --- | --- |
| core=1, max=2, queue=1 | #1 chạy, #2 queue, #3 chạy, #4 reject | #4 |
| core=2, max=2, queue=1 | #1/#2 chạy, #3 queue, #4 reject | #4 |
| core=1, max=3, queue=1 | #1 chạy, #2 queue, #3/#4 chạy, #5 reject | #5 |
| core=2, max=4, queue=2 | #1/#2 chạy, #3/#4 queue, #5/#6 chạy, #7 reject | #7 |
| core=1, max=2, queue=0 | #1/#2 chạy, không có queue, #3 reject | #3 |

Bảng dự đoán giả định các task chạy đều **chưa hoàn thành**, không có worker rảnh, executor chưa shutdown và dùng AbortPolicy. Nếu task rảnh/kết thúc giữa các lần nộp, lần reject có thể khác.

### Trường hợp queue quá lớn

Giả sử core=1, max=8 và queueCapacity rất lớn. Task #1 chạy trên core, nhiều task tiếp theo sẽ được queue nhận. Pool có thể vẫn chỉ có một worker vì queue chưa đầy; max=8 **không buộc** pool tạo thêm bảy worker ngay.

Hậu quả: backlog dài, bộ nhớ tăng, p95/p99 latency có thể xấu đi, nhưng rejection diễn ra rất muộn hoặc không xảy ra cho tới khi chạm giới hạn khác. Vì vậy không đặt queue unbounded chỉ để “tránh lỗi quá tải”.

### Trường hợp queueCapacity = 0

Trong `ThreadPoolTaskExecutor`, giá trị 0 dùng `SynchronousQueue`. Nó không giữ task chờ. Task phải được chuyển cho worker có thể nhận hoặc mở worker mới nếu dưới max. Khi tất cả worker đã bận và max cũng đầy, submission sẽ reject theo handler.

Một pool như vậy phản ứng nhanh với tải tăng nhưng có thể mở nhiều thread nhanh; cần giới hạn max thích hợp và kiểm soát downstream.

## 8. Cần quan sát những chỉ số nào?

Tại thời điểm test được giữ bằng latch, quan sát:

```text
poolSize              số worker hiện tồn tại trong pool
activeCount           số worker đang chạy task
queueSize             số task chưa chạy đang chờ
queueRemaining        số chỗ queue còn lại
rejectedSubmissions   số task bị từ chối tại biên submit
completedTasks        số task đã chạy xong
```

Ở Spring `ThreadPoolTaskExecutor`, có thể xem `getPoolSize()`, `getActiveCount()`, `getQueueSize()`. Sau khi bean được khởi tạo, JDK executor nền qua `getThreadPoolExecutor()` cung cấp `getQueue()` và `getCompletedTaskCount()`. Các metric này phản ánh **trạng thái có thể biến động**; nhiều getter gọi liên tiếp không đảm bảo snapshot nguyên tử trong hệ đang chạy tự do.

Đặc biệt:

- `getPoolSize() == maxPoolSize` **chưa** chứng minh queue đầy.
- `getQueueSize() == queueCapacity` **chưa** chứng minh tất cả worker đã bận.
- Cả hai cùng đúng vẫn cần xem pool có đang shutdown, worker có sắp giải phóng và chính sách rejection.
- `getCompletedTaskCount()` là giá trị ước lượng của pool; không nhất thiết đếm task do `CallerRunsPolicy` thực thi ngoài pool.
- Muốn biết số reject chính xác, nên đếm tại chính rejection handler hoặc nơi bắt `TaskRejectedException`/`RejectedExecutionException`, có metric và log phù hợp.

Trong ứng dụng Spring Boot có Micrometer/Actuator, tùy cấu hình và cách binder nhận executor, có thể theo dõi active thread, queue depth, completed task, utilization, rejection và thời gian chờ. Đừng giả định mọi metric luôn tự xuất hiện; xác minh instrumentation thực tế.

## 9. Quy trình kiểm thử đáng tin cậy

1. **Cố định cấu hình và handler:** khai báo core, max, queueCapacity, AbortPolicy. Ghi rõ phiên bản JDK/Spring.
2. **Giữ worker bằng latch:** task thông báo “đã chạy” rồi đợi tín hiệu được thả. Kiểm thử không được phụ thuộc chủ yếu vào `Thread.sleep(100)`.
3. **Nạp đủ queue:** sau khi core worker bắt đầu, submit task ngắn vào queue trong khi core vẫn bị giữ; tiếp tục submit để mở rộng tới max.
4. **Xác nhận saturation:** đợi tất cả worker cần thiết bắt đầu; đo active worker và số phần tử queue trước khi nộp task bị thử reject.
5. **Kiểm tra exception đúng nơi:** catch lỗi từ `execute/submit` hoặc caller của Spring proxy. Đừng đặt catch bên trong task chưa được nhận.
6. **Giải phóng và kết thúc đúng:** mở latch trong `finally`, shutdown và đợi tất cả task hợp lệ hoàn thành. Một bài test có thể treo mãi nếu thiếu nhánh dọn dẹp.
7. **Đếm việc hoàn thành:** kiểm tra tổng task thực thi, không chỉ nhìn một dòng “rejected”. Với ba task được nhận và một task bị reject, không được đếm bốn thành công.
8. **Kiểm thử hồi phục:** sau khi worker giải phóng và queue rỗng, thử thêm task mới **trước khi shutdown** để chứng minh saturation là tạm thời. Nếu nộp task sau shutdown, rejection lúc đó không chứng minh pool vẫn đầy.
9. **Đổi handler và dự đoán lại:** CallerRuns, Discard và DiscardOldest có hành vi khác Abort; không tái sử dụng kết luận của AbortPolicy.
10. **Làm load test tích hợp:** thử với datasource, HTTP client và số pod thật. Saturation ở executor chỉ là một phần của hành vi hệ thống.

Nếu dùng JUnit, có thể viết các assertion tương ứng `assertEquals(2, active)`, `assertEquals(1, queueSize)` và `assertThrows(RejectedExecutionException.class, ...)` khi test JDK executor. Với Spring executor, catch/assert `TaskRejectedException`. Test runner cũng phải dùng timeout và teardown để tránh leak thread khi assertion fail.

## 10. Tác động khi đưa cấu hình lên production

Cấu hình nhỏ core=1, max=2, queue=1 dành cho minh họa, không phải giá trị mặc định nên dùng cho mọi ứng dụng. Chọn thông số dựa trên loại task:

- **CPU-bound:** quá nhiều worker tranh CPU, tăng context switch; cần cân nhắc số core máy và mức tải.
- **I/O-bound:** worker có thể chờ JDBC/HTTP rất lâu; tăng worker không tự tăng số DB connections hay quota downstream.
- **Tác vụ có thời hạn:** nếu nằm trong queue lâu hơn deadline, dù cuối cùng chạy thành công cũng có thể vô ích; nên có queue wait budget/admission policy.
- **Tác vụ quan trọng:** nếu bị reject và không được lưu lại ở tầng bền vững, công việc có thể bị mất. Cần retry có giới hạn, backoff, idempotency hoặc job queue.
- **Nhiều nguồn công việc:** background batch, HTTP request và event consumer có thể cần pool hoặc bulkhead riêng để không tranh hết suất lẫn nhau.
- **Nhiều instance:** giới hạn worker và queue là **mỗi executor trên mỗi JVM**; bốn pod cùng max=2 có thể có tám worker trên toàn dịch vụ, chưa kể executor khác.
- **Tải bùng nổ:** queue có thể giúp hấp thụ burst ngắn, nhưng không giải quyết được khi tốc độ đến liên tục lớn hơn tốc độ xử lý.

Ở thời điểm trạng thái hoàn toàn đầy và không có worker đang rảnh, pool có thể giữ tối đa **`maxPoolSize` task đang chạy + `queueCapacity` task đang đợi**. Đây là số task cùng tồn tại trong **một executor**, không phải tổng số task xử lý suốt vòng đời. Với CallerRunsPolicy, caller còn có thể thực thi task bên ngoài pool nên không được lấy công thức ấy làm trần mọi hoạt động của ứng dụng.

**Rejection sớm có thể là hành vi đúng:** thà trả phản hồi quá tải rõ ràng còn hơn nhận vô hạn công việc rồi timeout đồng loạt. Với API có thể trả HTTP 429 hoặc 503 tùy nguyên nhân/hợp đồng; với message consumer cần xử lý ack/nack và khả năng redelivery phù hợp.

## 11. Các lỗi thường gặp

**Lỗi: “Em tăng max nhưng active vẫn bằng core.”** Nếu queue còn nhận việc, pool ưu tiên xếp hàng trước khi mở rộng vượt core. Kiểm tra queueCapacity và queue depth.

**Lỗi: “Queue đầy nhưng task vẫn nhận, chắc Java sai.”** Nếu worker còn có thể mở rộng tới max, executor tạo thêm worker. Queue đầy **một mình** chưa phải lý do reject.

**Lỗi: “Pool chạm max nhưng task vẫn nhận.”** Queue còn chỗ thì task có thể vào queue. Phải xác định **cả hai** đều hết dung lượng.

**Lỗi: “Task #4 được reject nhưng chẳng thấy log bên trong run().”** Task không được chạy nên code trong `run()` không thể log. Bắt exception ở thread submit.

**Lỗi: “Chỉ dùng Thread.sleep nên test khi xanh khi đỏ.”** Khoảng ngủ không xác nhận worker đã đạt trạng thái. Sử dụng CountDownLatch/barrier và đợi các mốc cụ thể.

**Lỗi: “Tất cả request không bị reject nghĩa là hệ thống khỏe.”** Với queue lớn, backlog và latency có thể tăng nguy hiểm mà không reject. Đo queue waiting, heap, p95/p99 latency và throughput.

**Lỗi: “@Async luôn trả về ngay.”** Submit có thể ném `TaskRejectedException`; CallerRunsPolicy có thể chạy task ở caller. `@Async` không phải bảo đảm tuyệt đối về latency.

**Lỗi: “DiscardPolicy không báo exception nên đã xử lý xong.”** Không có exception có thể chỉ nghĩa là task đã bị bỏ. Không dùng policy bỏ việc âm thầm khi nghiệp vụ cần hoàn thành.

**Lỗi: “Task đang chạy ném lỗi là saturation.”** Lỗi trong worker khác với rejection tại cổng submit. Với `submit(...)`, lỗi worker thường được chứa trong `Future` và cần `get()`/callback để quan sát.

**Lỗi: “Test treo sau khi assert fail.”** Nếu không mở latch và shutdown trong `finally`, worker có thể đợi vô hạn. Dọn dẹp và timeout là một phần của bài kiểm thử.

**Lỗi: “Đã giới hạn executor là đủ để bảo vệ DB.”** Task có thể dùng nhiều connection, hoặc các thread khác cũng dùng DB. Phải phối hợp giới hạn của datasource, downstream, transaction duration và service quota.

## 12. Ghi nhớ và tài liệu chính thức

**Quy tắc cốt lõi:**

1. Chưa tới core → tạo worker.
2. Đã tới core, queue còn chỗ → đưa task vào queue.
3. Queue đầy, chưa tới max → tạo worker mới.
4. Queue đầy **và** max worker đã bận → áp dụng rejection handler.
5. `AbortPolicy` giúp quan sát sự kiện từ chối bằng exception ở phía submit.
6. Dùng `CountDownLatch` để thực nghiệm giữ worker chưa hoàn thành, tạo điều kiện bão hòa kiểm chứng được.
7. Spring `ThreadPoolTaskExecutor` cần được cấu hình hữu hạn; `@Async` phải đi qua đúng proxy và đúng executor.
8. Sau mỗi bài test phải release worker, shutdown pool, đợi task hợp lệ hoàn thành và đối chiếu số task thực thi.

**Tài liệu đối chiếu:**

- [Java SE 17 – ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): cơ chế core → queue → max → rejection và các policy.
- [Java SE 17 – CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): đồng bộ điểm bắt đầu/kết thúc để test ổn định.
- [Java SE 17 – ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): queue hữu hạn.
- [Spring Framework 6.2 – Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html): thread pool, queue và rejection trong Spring.
- [Spring Framework 6.2 – ThreadPoolTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): cấu hình và API giám sát.
- [Spring Framework 6.2 – TaskRejectedException Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/task/TaskRejectedException.html): exception của Spring TaskExecutor.

**Kết luận:** muốn chứng minh một pool từ chối vì quá tải, phải tạo được **đồng thời** hai điều kiện: worker đã dùng hết `maxPoolSize` và queue cũng không còn chỗ. Khi giữ trạng thái này bằng latch rồi nộp task mới, ta thấy rõ chính sách từ chối và có thể thiết kế hành vi quá tải phù hợp cho ứng dụng Spring.
